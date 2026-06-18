---
phase: 02-fukusho-labels
reviewed: 2026-06-18T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - scripts/apply_schema.sql
  - scripts/run_label_etl.py
  - scripts/run_label_reconcile.py
  - src/config/label_spec.yaml
  - src/config/settings.py
  - src/db/connection.py
  - src/db/schema.py
  - src/etl/fukusho_label.py
  - src/etl/label_reconcile.py
  - tests/test_fukusho_label.py
  - tests/test_label_reconcile.py
  - tests/test_raw_immutability.py
findings:
  critical: 5
  warning: 9
  info: 4
  total: 18
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 2 は本プロジェクトで最もリーク-sensitive な表面（`fukusho_hit_validated` = 予測目標の正）を生成する。実装は全体的に丁寧で、staging-swap idempotency、raw read-only 二重保護、reader ロール明示 GRANT、psycopg3 採用、sentinel-based marker 正規化など多くの必修要件を満たしている。

しかし**予測目標の正しさに直結する BLOCKER が 5 件**存在する。中でも最も重大なのは:

1. **`_check_raw_validated_drift` が `severity='info'` に格下げされている**（CR-01）。HIGH #2 の「tautology 回避」は precision/recall 検査が HR↔label 直接照合で正当性を保証するからこそ成立する議論だが、`validated` status での SE↔HR source 不一致を INFO に回す判断は、label が間違っている可能性（HR payout slot と SE KakuteiJyuni が矛盾する=どちらかが誤り）を検知しないことを意味する。`fukusho_hit_validated` は予測目標そのものであり、これを「参考レポート」扱いするのは Core Value（リーク防止と同等の聖域）に反する。
2. **`_compute_race_level_agreement` の SQL injection**（CR-02）。`held_out_list` の PK 値を f-string で直接 SQL に展開している。DB 由来の値とはいえ defense-in-depth 違反で、プロジェクトのパラメータ化クエリ原則に反する。
3. **`_payout_places` で `torokutosu_i` が異常値（例: 負数・1000超）のとき無限ループに近い状態にはならないが `int(t)` が ValueError で落ちる**（CR-03）。`pd.to_numeric(errors="coerce")` で NaN になる場合は `_is_na` で捕捉できるが、`pd.NA` と整数の比較 `min_torokutosu <= pd.NA <= 7` は pandas でエラーになる経路がある。
4. **`fukusho_hit_raw` が race_cancelled / fuseiritu レースでも `kakuteijyuni` ベースで算出される**（CR-04）。これらのレースでは outcome が非確定（`unresolved`）にも関わらず `fukusho_hit_raw=1` となる行が存在し得る。`_check_raw_validated_drift` はこれを INFO で処理するが、Phase 3 が誤って `fukusho_hit_raw` を使った場合の silent leak 源になる。
5. **`_check_payout_precision` / `_check_payout_recall` の JOIN が HR 側の `monthday` を無視**しており、同じ (year, jyocd, kaiji, nichiji, racenum) で `monthday` が異なるレースが存在した場合に cross-join で誤照合する可能性がある（CR-05）。コメントは「race-key PK で一意」と主張するが、`normalized.n_race` 側の PK 仕様の保証を HR 側に暗黙転嫁している。

さらに WARNING 9 件（`_check_payout_recall` が `dead_heat` でない非対象馬を検知できない等）、INFO 4 件。

---

## Critical Issues

### CR-01: `_check_raw_validated_drift` が `severity='info'` に格下げ — label 誤り検知の空洞化

**File:** `src/etl/label_reconcile.py:429-504`
**Issue:**
`_check_raw_validated_drift` の docstring は「`validated` status での SE↔HR source 不一致」を INFO に回す理由として「label は HR payout を権威として正しく採用している」と主張する。しかしこれは論理的に逆転している:

- `fukusho_hit_raw` は SE `KakuteiJyuni` 由来
- `fukusho_hit_validated` は HR `PayFukusyoUmaban` 由来
- 両者が矛盾する（drift する）場合、**どちらかが誤り**でなければならない
- label が HR を「権威として採用」したからといって、SE と HR の矛盾が「正常」とは言えない — HR 側のデータ欠陥の可能性がある

HIGH #2 の本来の意图は「precision/recall の HR↔label 直接照合（BLOCK）だけでなく、独立ソース（SE KakuteiJyuni）との cross-check を BLOCK で併用して tautology を回避する」だった。これを「drift のうち dead_heat 以外は INFO」に変えると、**SE と HR が矛盾している validated レース（= label が間違っている可能性があるレース）をゲートが素通りする**。`fukusho_hit_validated` は予測目標そのものであり、Core Value（リーク防止と同等の聖域）に照らせば、drift は量ではなく質の問題である。

特に `non_dead_heat_drift_count > 0` は SE と HR が矛盾する行が存在することを意味し、これを verdict に反映しない設計は、**ラベル誤りが混入しても SC#2 ゲートが pass する**ことを許す。

**Fix:**
`non_dead_heat_drift_count > 0` を BLOCK 条件に格上げする（少なくとも `validated`/`inferred` status での drift）。`unresolved` の drift（race_cancelled で KakuteiJyuni が無い馬が HR payout に含まれる等）は D-04-legitimate なので INFO のままで良い。

```python
# 例: validated/inferred status での drift のみ BLOCK 扱い
if non_dead_heat_drift_count > 0:
    # validated/inferred の drift は label 誤りのシグナル
    cur.execute("""
        SELECT count(*) FROM label.fukusho_label
        WHERE {filt}
          AND fukusho_hit_raw != fukusho_hit_validated
          AND label_validation_status IN ('validated', 'inferred')
    """.format(filt=PROJECT_WINDOW_FILTER))
    serious_drift = int(cur.fetchone()[0])
else:
    serious_drift = 0

return CheckResult(
    name="raw_validated_drift",
    passed=serious_drift == 0,         # ← True 固定を撤廃
    severity="block" if serious_drift > 0 else "info",
    ...
)
```

---

### CR-02: `_compute_race_level_agreement` で SQL injection 可能な f-string 展開

**File:** `src/etl/label_reconcile.py:701-715`
**Issue:**
`where_race_keys` を `held_out_list`（DB 由来の PK tuple）から f-string で構築し、SQL に直接埋め込んでいる:

```python
where_race_keys = " OR ".join(
    f"(hr.year::int={rk[0]} AND hr.jyocd='{rk[1]}' AND hr.kaiji::int={rk[2]} "
    f"AND hr.nichiji='{rk[3]}' AND hr.racenum::int={rk[4]})"
    for rk in held_out_list
)
```

インラインコメントは「DB から取得した PK 値（SQL injection source ではない）」と主張するが、これは defense-in-depth の原則違反である。プロジェクト全体（`src/db/schema.py`, `apply_schema.sql`, `run_label_reconcile.py` の allowlist filter 等）がパラメータ化クエリと `psycopg.sql.Identifier` で一貫している中で、ここだけ文字列展開に逃げるのは:

1. **将来のリファクタで held_out_list が外部入力に繋がった場合の silent vulnerability**
2. **`jyocd` / `nichiji` が varchar であり、万一 DB に `'\''` のような値が混入した場合（EveryDB2 のデータ品質に依存）にクエリが破壊される**
3. **CLAUDE.md の silent fallback 禁止（D-13）と projct のセキュリティ原則への違反**

**Fix:**
psycopg3 のパラメータ埋め込み（`cur.execute(sql, params)`）または `ANY(ARRAY[...])` と `UNNEST` を使った set-based の比較を使う。

```python
# 例: UNNEST で set-based に
years = [rk[0] for rk in held_out_list]
jyocds = [rk[1] for rk in held_out_list]
# ... 他の PK カラムも同様
cur.execute(
    """
    SELECT year, jyocd, kaiji, nichiji, racenum,
           payfukusyoumaban1, payfukusyoumaban2, payfukusyoumaban3,
           payfukusyoumaban4, payfukusyoumaban5
    FROM public.n_harai
    WHERE {filt}
      AND (year::int, jyocd, kaiji::int, nichiji, racenum::int) IN (
          SELECT * FROM unnest(%s::int[], %s::text[], %s::int[], %s::text[], %s::int[])
          AS t(year, jyocd, kaiji, nichiji, racenum)
      )
    """.format(filt=PROJECT_WINDOW_FILTER),
    (years, jyocds, kaijis, nichijis, racenums),
)
```

---

### CR-03: `_payout_places` で `pd.NA` と整数の比較が pandas で例外になる経路

**File:** `src/etl/fukusho_label.py:627-635`
**Issue:**
`_payout_places` は `torokutosu_i`（`pd.to_numeric(errors="coerce")` の結果）を受け取る。`pd.to_numeric` は失敗時に `float('nan')` ではなく **`np.float64(nan)` または `pd.NA`（入力 dtype 依存）** を返す場合がある。

```python
def _payout_places(t: Any) -> int:
    if t is None or _is_na(t):
        return no_sale
    ti = int(t)             # ← np.float64(nan) は通るが、pd.NA は int() で TypeError
    if ti >= 8:
        return places_8plus
    if min_torokutosu <= ti <= 7:    # ← pd.NA との比較は pd-errors で例外
        return places_5_7
    return no_sale
```

`_is_na` は `pd.isna(v)` を `try/except (TypeError, ValueError)` で包んでいるが、`pd.isna(pd.NA)` は `True` を返すため最初の分岐で捕捉できるはず — ただし `pd.NA` の `int()` 変換が `TypeError` になるケース（pandas の nullable integer dtype 経由等）が完全に閉じているかは入力経路に依存する。実DBの `torokutosu` varchar が異常値（空文字・英字混じり等）の場合に `pd.to_numeric(errors="coerce")` が `float nan` を返す経路は `_is_na` で捕捉できるが、ユニットテストが `float("nan")` と `None` しかカバーしておらず、実データでの `pd.NA` 経路が未検証。

加えて、`_raw_hit` の `int(pp)` (`pp = r["fukusho_payout_places"]`) は `_payout_places` の戻り値（常に int）なので安全だが、`_is_dh` の `int(pp)` / `int(pc)` は `pc = r.get("payout_count", 0)` が DataFrame 上で `np.int64`/`pd.NA` 混在になり得るため、こちらも `pd.NA` 経路で `TypeError` を起こし得る。

**Fix:**
`_payout_places` と `_is_dh` の冒頭で `_is_na` 後に明示的に `float()` を挟んで `int()` に回すか、pandas nullable dtype を経由しないよう `pd.to_numeric(...).astype("Int64")` 後に `.fillna(-1)` 等で sentinel 化する。さらにユニットテストに `pd.NA` / `np.float64(nan)` / `""` 入力の regression を追加する。

```python
def _payout_places(t: Any) -> int:
    if t is None or _is_na(t):
        return no_sale
    try:
        ti = int(float(t))      # pd.NA 経由でも float() で TypeError を回避
    except (TypeError, ValueError):
        return no_sale          # D-13: silent fallback 禁止だが、異常 torokutosu は
                                # 既に unresolved に分類される経路があるため no_sale で安全
    if ti >= 8:
        return places_8plus
    if min_torokutosu <= ti <= 7:
        return places_5_7
    return no_sale
```

---

### CR-04: `fukusho_hit_raw` が race_cancelled / fuseiritu / tokubarai(空) レースでも `kakuteijyuni` ベースで算出され、`fukusho_hit_raw=1` の行が残る

**File:** `src/etl/fukusho_label.py:651-662`
**Issue:**
`fukusho_hit_raw` は `fukusho_payout_places > 0 AND 1 <= kakuteijyuni <= payout_places` だけで算出され、`label_validation_status` や `is_race_cancelled` を見ない。そのため以下のケースで `fukusho_hit_raw=1` になり得る:

- **race_cancelled** (HR DataKubun='9'): SE 側に `kakuteijyuni=1,2,3` が入ったままの中止レース（EveryDB2 で実際に発生し得る）では、`fukusho_hit_raw=1` だが `label_validation_status=unresolved`
- **fuseiritu** (HR FuseirituFlag2='1'): 複勝不成立でも SE の着順は存在するため `fukusho_hit_raw=1` になり得る
- **tokubarai 空対象**: 同上

これは `_check_raw_validated_drift` を INFO にした CR-01 と組み合わさって**致命的**になる: drift 行（`raw=1, valid=0`）が `unresolved` status で INFO 扱いされ、Phase 3 が誤って `fukusho_hit_raw` を目的変数に使った場合（仕様違反だがヒューマンエラーで起こり得る）に、race_cancelled の偽正例が学習データに混入する silent leak 源になる。

D-13（silent fallback 禁止）と Core Value に照らせば、outcome が確定しないレースでは `fukusho_hit_raw` も NULL または 0 に正規化すべきである。

**Fix:**
`_raw_hit` の冒頭で `label_validation_status` を見て unresolved 系なら 0 を返すか、`compute_fukusho_labels` の最後で unresolved レースの `fukusho_hit_raw` を 0 に上書きする。ただし `fukusho_hit_raw` は「純粋な KakuteiJyuni 由来」の audit 列という意味付けもあるため、より安全なのは **`label_validation_status='unresolved'` の行は `fukusho_hit_raw=NULL`** にすること（NOT NULL 制約を外すか、別途 `fukusho_hit_raw_safe` 列を設ける）。

```python
# compute_fukusho_labels の最後で:
mask_unresolved = merged["label_validation_status"] == "unresolved"
# raw 列は audit のために値を保持するが、outcome 非確定レースでは NULL で格納
# （schema 側で fukusho_hit_raw smallint NULLable に変更必要）
```

---

### CR-05: `_check_payout_precision` / `_check_payout_recall` の JOIN が `monthday` を無視 — 複数レースの cross-join 誤照合リスク

**File:** `src/etl/label_reconcile.py:177-198` (`_check_payout_precision`) および `230-251` (`_check_payout_recall`)
**Issue:**
両検査の JOIN 条件は:

```sql
ON (l.year = hr.year::int
    AND l.jyocd = hr.jyocd
    AND l.kaiji = hr.kaiji::int
    AND l.nichiji = hr.nichiji
    AND l.racenum = hr.racenum::int)
```

`monthday` が含まれていない。コメントは「race-key PK (year, jyocd, kaiji, nichiji, racenum) は JRA+2015 で一意（実測 39,580 = 39,580 distinct）」と主張するが:

1. **EveryDB2 仕様上 `monthday` は自然キーの一部**であり、同一 (year, jyocd, kaiji, nichiji, racenum) で `monthday` が異なるレースが将来导入された場合に即座に壊れる
2. **`label.fukusho_label` 側は `race_date` を持つが `monthday` 列を持たない**（`_LABEL_TABLE_COLUMNS` 参照）ため、JOIN に使えない構造的欠陥がある
3. `normalized.n_race` の PK 一意性検査（quality_gate.py）は `monthday` を含んでいないため、「race-key で一意」という主張の検証は実際には `monthday` 抜きで行われている

`_compute_race_level_agreement` でも同様の JOIN を使うが、こちらは「ホールドアウト集合を完全一致比較」するため誤照合しても disagree として検出される。しかし precision/recall は count-based のため、誤照合があっても気づかず pass してしまう可能性がある。

**Fix:**
`label.fukusho_label` に `monthday` 列を追加（または `race_date` から復元）、もしくは JOIN に `normalized.n_race` を経由して `monthday` を含める。

```sql
-- 修正例: n_race を経由して monthday を取得
SELECT count(*) FROM label.fukusho_label l
JOIN normalized.n_race nr
  ON (l.year = nr.year AND l.jyocd = nr.jyocd AND l.kaiji = nr.kaiji
      AND l.nichiji = nr.nichiji AND l.racenum = nr.racenum)
JOIN public.n_harai hr
  ON (nr.year = hr.year::int AND nr.monthday = hr.monthday
      AND nr.jyocd = hr.jyocd AND nr.kaiji = hr.kaiji::int
      AND nr.nichiji = hr.nichiji AND nr.racenum = hr.racenum::int)
WHERE ...
```

---

## Warnings

### WR-01: `_check_payout_recall` は dead_heat レースの非対象馬を検知できない

**File:** `src/etl/label_reconcile.py:222-268`
**Issue:**
`_check_payout_recall` は「HR payout set に含まれるが `fukusho_hit_validated=0` の馬」を検知する。しかし dead_heat レースでは、`compute_fukusho_labels` が HR payout slot を全て `validated=1` にする（D-04: 払戻テーブル全対象馬を正例）ため、この検査は dead_heat レースでは常に 0 になる。つまり **dead_heat レースで HR payout slot に含まれていない馬が不当に `validated=1` になっているケース**（逆方向の汚染）は `payout_precision` で検知できるが、**`dead_heat` フラグの誤設定で非対象馬が payout set 扱いになっているケース**は両検査で見えない。

`_check_dead_heat_integrity` が status↔flag の整合を検査するが、`is_dead_heat` と payout set の実内容の整合（slot4/5 が本当に埋まっているか）は検査していない。

**Fix:**
`is_dead_heat=True` のレースで `payout_count`（HR payout slot の非空数）と `fukusho_payout_places` の比較を追加検査する。

---

### WR-02: `_check_no_scratch_mislabeled` の `fukusho_hit_validated == 1` が pandas の `==` で int と str の比較になるリスク

**File:** `src/etl/label_reconcile.py:335`
**Issue:**
```python
viol_df = df[(df["recomputed_is_scratch"] == True) & (df["fukusho_hit_validated"] == 1)]
```

`fukusho_hit_validated` は SQL から取得され `label.fukusho_label.fukusho_hit_validated smallint` だが、psycopg3 は `smallint` を Python `int` で返すため通常は問題ない。ただし NULL が混入した場合、`NULL == 1` は `NULL`（pandas では `False` 扱い）になり、違反行が見逃される可能性がある。`_recompute_scratch_markers` の SELECT が `fukusho_hit_validated` をそのまま返すため、NULL が入り得る。

**Fix:**
`df["fukusho_hit_validated"].fillna(0).astype(int) == 1` 等で NULL-safe にする。

---

### WR-03: `_check_dead_loss_not_excluded` の正当理由リストと `label_spec.yaml.ineligibility_reason_codes` が重複定義

**File:** `src/etl/label_reconcile.py:68-76` および `src/config/label_spec.yaml:225-232`
**Issue:**
`_VALID_INELIGIBILITY_REASONS` が `label_reconcile.py` 内にハードコードされており、`label_spec.yaml.ineligibility_reason_codes` と同一内容だが別管理。CR-06（JRA filter の単一真の源）と同じ問題で、将来 reason code を追加した場合に両者の同期が壊れる。

インラインコメントは「ハードコードで安全性確保・D-13」と主張するが、D-13 は「未知コードを silent fallback しない」であって「単一の源を持つな」ではない。`label_spec.yaml` を load して set 構築すれば同じ安全性が保てる。

**Fix:**
`_check_dead_loss_not_excluded` 内で `load_label_spec()["ineligibility_reason_codes"]` を読み込んで set 化する。

---

### WR-04: `compute_fukusho_labels` の `is_fukusho_sale_available` が `torokutosu >= 5` で評価するが、`fukusho_payout_places` は `min_torokutosu <= ti <= 7` で `places_5_7` を返す境界ずれ

**File:** `src/etl/fukusho_label.py:639-649` および `627-635`
**Issue:**
`is_fukusho_sale_available` は `torokutosu >= 5 AND fuseirituflag2 != '1'`。
`_payout_places` は `min_torokutosu(=5) <= ti <= 7` で `places_5_7(=2)` を返し、`ti >= 8` で `places_8plus(=3)`、それ以外（ti < 5）で `no_sale(=0)`。

`ti = 5,6,7` で `is_fukusho_sale_available=True` かつ `fukusho_payout_places=2`（整合）。
`ti < 5` で `is_fukusho_sale_available=False` かつ `fukusho_payout_places=0`（整合）。
境界自体は整合しているが、`min_torokutosu`（=5）が `is_fukusho_sale_available` の閾値としても `_payout_places` の下限としても使われており、**2つの異なる概念（「複勝発売の有無」と「払戻対象数の境界」）に同じ定数を使う**構造的脆さがある。Pitfall 3 コメントは「境界は HR PayFukusyoUmaban/FuseirituFlag2 の観測事実で最終確定」とするが、実装は `torokutosu` のみで判定しているため、spec と実装がずれている。

**Fix:**
`label_spec.yaml` に `fukusho_sale_min_torokutosu` と `payout_places` 境界を分離して定義する。

---

### WR-05: `_select_se_state` の 2回 SELECT が同一トランザクションでない場合の一貫性リスク

**File:** `src/etl/fukusho_label.py:183-230`
**Issue:**
`_select_se_state` は `public.n_uma_race` から基本状態と timediff を2回別々に SELECT して pandas で merge する。両 SELECT は同一 readonly cursor（=同一トランザクション）で実行されるため通常は一貫するが、`run_label_etl` は `with read_pool.connection() as conn:` ブロック内で `_select_raw_harai`, `_select_se_state`, `_select_race_meta` を順に呼ぶ — 同一 connection なので一貫する。ただし、`_select_se_state` 内の2回の SELECT が両方とも `datakubun IN ('7','9')` でフィルタされていることが前提で、片方だけフィルタが違った場合に行数不一致を起こす。

テスト `test_select_se_state_no_row_multiplication_on_timediff_merge` は正規表現で '7' と '9' の両方を含むことを検査するが、**両 SELECT が同じフィルタを持つことを直接 assert していない**。片方の SELECT だけ '7' 単独に退化した場合、merge 後の行数 assertion で検知できる場合もあるが、timediff_df が空集合の場合（`datakubun='9'` のみ存在など）には検知できない。

**Fix:**
2つの SELECT を `UNION` または単一 SELECT に統合する。`timediff` / `dochakukubun` / `dochakutosu` が `normalized.n_uma_race` に無い問題は、`public.n_uma_race` から一回の SELECT で両方の列を取得すれば解決する。

---

### WR-06: `_idempotent_load_label` の `executemany` rowcount 検証が psycopg3 で信用できない

**File:** `src/etl/fukusho_label.py:898-908`
**Issue:**
```python
write_cur.executemany(
    f"INSERT INTO label.fukusho_label_staging ({cols_sql}) VALUES ({placeholders})",
    rows,
)
actual = write_cur.rowcount if write_cur.rowcount is not None else len(rows)
```

psycopg3 の `executemany` は `rowcount` を「最後に実行されたクエリの影響行数」として返す場合と「全クエリの累積」として返す場合が実装依存で、psycopg3 では DEFAULT では `rowcount` は最後のクエリの影響行数になる。`rows` がバッチ化されている場合、`rowcount != len(rows)` が常に真になって RuntimeError で落ちるか、あるいは逆に全行成功でも `rowcount == len(rows)` にならずに検証が形骸化する可能性がある。

psycopg3 では `executemany` の後 `cursor.rowcount` は「全バッチ合計」を返す仕様だが、これは libpq の `PQcmdTuples` の挙動に依存し、PostgreSQL バージョンや pipeline mode の有無で変わる。

**Fix:**
`rowcount` に頼らず、INSERT 後に `SELECT count(*) FROM label.fukusho_label_staging` で検証する（既に最後の方で `count(*) FROM label.fukusho_label` を取得しているので、staging のカウントも取得して比較する）。

---

### WR-07: `run_label_etl` の checksum が `string_agg(... ORDER BY ...)` で巨大テーブルでメモリ爆発の可能性

**File:** `src/etl/fukusho_label.py:1051-1057`
**Issue:**
```python
wcur.execute(
    "SELECT md5(string_agg(md5(row(r.*)::text), '' "
    "ORDER BY year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)) "
    "FROM label.fukusho_label r"
)
```

`string_agg` は全行をメモリに蓄えるため、55万行を超えると PostgreSQL サーバ側で work_mem を消費し、ディスクソートに落ちる可能性がある。性能問題（review scope 外）だが、**機能問題**: `row(r.*)::text` は列順序に依存し、将来 `ALTER TABLE label.fukusho_label ADD COLUMN` した瞬間に checksum が変わり、idempotent 検証が「同じデータでも別 checksum」を返すようになる。

**Fix:**
列を明示的に列挙する（`md5(string_agg(md5(row(r.year, r.jyocd, ...)::text), ...))`）、または `pg_md5_hash` 系の集計関数を使う。

---

### WR-08: `run_label_etl` の `with read_pool.connection() as conn:` ブロックが SELECT 後に明示的 rollback/close を持たない

**File:** `src/etl/fukusho_label.py:1024-1029`
**Issue:**
```python
with read_pool.connection() as conn:
    with conn.cursor() as cur:
        hr_df = _select_raw_harai(cur)
        se_df = _select_se_state(cur)
        race_df = _select_race_meta(cur)
```

context manager 抜け時に connection は pool に戻るが、READ COMMITTED で長時間トランザクションが残ると ETL の write_pool とロック衝突する。`scripts/run_label_etl.py:66-68` では明示的に `conn.rollback()` しているが、`run_label_etl` 本体では明示的なトランザクション終了が無く、`test_raw_unchanged_after_label_etl` から呼ばれた際に振る舞いが異なる。

**Fix:**
`with read_pool.connection() as conn:` ブロックの最後に `conn.rollback()`（または `conn.commit()` — SELECT only なので等価）を明示する。

---

### WR-09: `run_label_etl` の `settings=None` のとき `Settings()` をデフォルト構築すると reader_role が常に警告ログになる

**File:** `src/etl/fukusho_label.py:1015-1022`
**Issue:**
```python
if settings is None:
    settings = Settings()
reader_role = getattr(settings, "db_reader_role", None) or "keiba_readonly"
if not getattr(settings, "db_reader_role", None):
    logger.warning("Settings.db_reader_role が未設定のため default 'keiba_readonly' を使用します ...")
```

`Settings` は `db_reader_role: str = "keiba_readonly"`（settings.py:46）なので、`getattr(settings, "db_reader_role", None)` は常に `"keiba_readonly"` を返し、警告は決して発火しない。これはデッドロジックである。`Settings` が明示的に `db_reader_role=None` を許容しない以上、この警告分岐は到達不能コード。

**Fix:**
デッドロジックを削除し、`reader_role = settings.db_reader_role` に単純化する。または `.env` でロール名を上書きできるようにする意図なら `Optional[str] = None` にして明示的な未設定状態を区別する。

---

## Info

### IN-01: `compute_is_model_eligible` のステップ (f) で `class_level_numeric` が `pd.NA` のとき `int(class_level) < int(min_class)` が `TypeError`

**File:** `src/etl/fukusho_label.py:478-481`
**Issue:**
`class_level = row.get("class_level_numeric")` が `pd.NA` の場合、`_is_na(class_level)` で捕捉されるため `int(class_level)` には進まない。ただし pandas nullable dtype (`Int64`) の場合、`_is_na(pd.NA)` は `True` を返すため安全。ユニットテストで `class_level_numeric=None` はカバーされているが `pd.NA` は未カバー。
**Fix:** テストに `pd.NA` ケースを追加。

---

### IN-02: `test_check_payout_recall` の mock cursor が `EXISTS` SQL を正しく識別できない可能性

**File:** `tests/test_label_reconcile.py:236-248`
**Issue:**
`_mock_cursor` の `_fetchone` は SQL 部分文字列マッチで戻り値を決める。`_check_payout_recall` の SQL は `fukusho_hit_validated = 0 AND EXISTS (...)` を含むが、`_check_payout_precision` の SQL は `fukusho_hit_validated = 1 AND NOT EXISTS (...)` を含む。両者の SQL には `fukusho_hit_validated = 1` という共通部分文字列が含まれるため、mock の部分文字列マッチが誤ヒットする可能性がある。実際には `"fukusho_hit_validated = 0"` と `"fukusho_hit_validated = 1"` で区別されるが、順序依存性がある。
**Fix:** mock をより厳密な SQL パターンマッチにする。

---

### IN-03: `label_spec.yaml` の `time_sentinels_absent: ["0", "0.0", "", "9999", "9999.0"]` に `"00"` / `"000"` 等の zero-pad 表現が無い

**File:** `src/config/label_spec.yaml:121`
**Issue:**
`time` 列が varchar の場合、EveryDB2 は `"0"` を返すかもしれないが `"00"` や `"0.00"` を返す可能性もあり、sentinel 集合が完全でない場合 `_canonicalize_value` を通った後に `time_sentinels_absent` に入らず `time_present=True` になるリスクがある。`bataijyu_sentinels_scratch` は `"000"` を含むのに対し、`time_sentinels_absent` の網羅性が不十分。
**Fix:** `"00"`, `"000"`, `"0.00"`, `"0000"` 等のバリエーションを追加、または正規表現ベースの zero 判定に切り替える。

---

### IN-04: `scripts/run_label_reconcile.py` の `KEIBA_SKIP_DB_TESTS=1` チェックが reconcile 本体のロジックバグを隠す

**File:** `scripts/run_label_reconcile.py:92-96`
**Issue:**
`KEIBA_SKIP_DB_TESTS=1` 設定時に exit 0 でスキップする。CI で「DB 無し環境を許可」する意図だが、この環境変数が誤って本番 CI に設定されていた場合、LABEL-03 gate が常に pass してしまう。silently passing gate は Core Value に照らして危険。
**Fix:** skip 時は exit 0 ではなく、明示的な `SKIP` verdict を出力し、CI 側で `SKIP` を検知して別ジョブを trigger する等の運用にする。

---

_Reviewed: 2026-06-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
