---
phase: 02-fukusho-labels
reviewed: 2026-06-18T00:00:00Z
depth: deep
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
  critical: 7
  warning: 11
  info: 5
  total: 23
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** deep（per-file + cross-file call-chain / import graph / spec↔impl 整合性 / テストカバレッジ）
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 2 は本プロジェクトで最もリーク-sensitive な表面（`fukusho_hit_validated` = 予測目標の正）を生成する。実装は全体的に丁寧で、staging-swap idempotency（advisory lock + 空入力拒否 + rowcount 検証）、raw read-only 二重保護、reader ロール明示 GRANT、psycopg3 採用、sentinel-based marker 正規化、`psycopg.sql.Identifier` によるロール名 quote など多くの必修要件を満たしている。

しかし deep 分析で**予測目標の正しさ/リーク/セキュリティに直結する BLOCKER が 7 件**存在する。本レビューは既存 standard review を検証・維持しつつ、cross-file 視点で新規発見を追加した。

### 既存 standard review の検証結果（CR-01〜CR-05, WR-01〜WR-09, IN-01〜IN-04）

全て妥当であり**維持**する。今回の deep 分析で特に強化した点:

- **CR-01（`_check_raw_validated_drift` の `severity='info'` 格下げ）**: 既存レビューの指摘は妥当だが、さらに `label_spec.yaml` の §10.5 / D-04 設計意図と照合すると「label 自体は HR payout を権威として正しく採用」という主張（label_reconcile.py:445-447）が**循環論法**になっていることを確認した。`fukusho_hit_validated` が HR payout から作られ、それを HR payout と再 JOIN する precision/recall 検査で「正当性を保証」は tautology であり、SE `KakuteiJyuni` との独立 cross-check が BLOCK であることの重要性は既存レビュー指摘通り。**維持・強化**。
- **CR-02（SQL injection f-string）**: 既存レビュー通り。`held_out_list` は `cur.fetchall()` 由来（label_reconcile.py:643）であり source は DB 内部だが、`jyocd`/`nichiji` が varchar で EveryDB2 のデータ品質に依存するため、defense-in-depth 違反は妥当。**維持**。
- **CR-03（`_payout_places` の pd.NA 経路）**: 既存レビュー通り。実際に `_is_na(pd.NA)` は `True` を返すため先頭分岐で捕捉されるが、`_is_dh` の `int(pc)` で `pc = r.get("payout_count", 0)` が DataFrame 上で `pd.NA` になる経路は `compute_fukusho_labels` 内で `merged["payout_count"]` が `pd.NA` を含み得る（HR merge が left join で HR 欠損行）。**維持**。
- **CR-04（race_cancelled で raw=1 残留）**: 既存レビュー通り、かつ §10.5 acceptance gate がこの silent leak を検知しない経路（CR-01 と相乗）を確認した。**維持**。
- **CR-05（`monthday` JOIN 欠落）**: 既存レビュー通り。**維持**。
- **WR-01〜WR-09 / IN-01〜IN-04**: 全て妥当。**維持**。

### 今回の deep 分析で追加した新規発見

cross-file 視点で新たに **CR-06, CR-07, WR-10, WR-11, IN-05** を追加した:

- **CR-06**: `_check_payout_precision` / `_check_payout_recall` の `_LABEL_WINDOW_FILTER` は `l.year::int >= 2015` を使うが、`label.fukusho_label.year` の DDL は `int`（fukusho_label.py:792）。`int::int` は無害だが、precision/recall の JOIN 条件 `l.year = hr.year::int` と整合している。一方 `PROJECT_WINDOW_FILTER`（`filters.py`）は `year::int >= 2015` で `public.n_harai.year`（varchar）を前提としている。`label.fukusho_label` 側で `PROJECT_WINDOW_FILTER` をそのまま使うと `label.year::int::int >= 2015` となるため `_LABEL_WINDOW_FILTER` を別途定義したのは正しいが、**両フィルタの同期が人の手に依存し、`label_validation_status` 集計（label_reconcile.py:456, 467, 480 等）は `PROJECT_WINDOW_FILTER` を使っている**。`label.fukusho_label.year` は int なので `year::int` は Postgres の暗黙キャストで通るが、フィルタの単一ソース原則（CR-06 single source of truth in filters.py docstring）に反する二重管理。
- **CR-07**: `tests/test_label_reconcile.py:443-465` の `test_verdict_pass_when_all_block_pass` が、実コードでは `severity="info"` な `_check_raw_validated_drift` を `monkeypatch` で `severity="block"` に上書きして「全 BLOCK pass」と主張している。これは **CR-01 の再検査テストが、CR-01 が修正された場合（drift を BLOCK に格上げ）にのみ意味を持つ状態**であり、現在の実装（INFO）では verdict pass を過剰に模倣している。テストが実装のバグ（CR-01）を隠蔽する方向に作用している。
- **WR-10**: `_select_se_state` の merge は `how="left"` だが、timediff_df 側に SE 側に無い `datakubun` 値の行が存在した場合、post_len == pre_len でも「timediff が欠損したまま進む」経路がある。`merge.assert` は行数増殖のみ検知し、右側の余剰行（left-only で捨てられる）を検知しない。
- **WR-11**: `scripts/run_label_etl.py:66-68` で `read_pool.connection()` を取ってすぐ `rollback()` しているが、これは直前の `with read_pool.connection() as conn:` ブロック（line 58-60）と別 connection を取得している。psycopg_pool は pool から借りた connection をブロック抜けで自動 commit/rollback するため、この2回目の connection 取得+rollback は無意味なデッドコード。
- **IN-05**: `scripts/run_label_etl.py` が `KEIBA_SKIP_DB_TESTS` を見ないため、CI で `KEIBA_SKIP_DB_TESTS=1` を設定しても ETL スクリプトは実行されてしまう。`run_label_reconcile.py:92` だけが skip するため、ETL 実行 → reconcile skip の不整合が起きる。

---

## Critical Issues

### CR-01: `_check_raw_validated_drift` が `severity='info'` に格下げ — label 誤り検知の空洞化（循環論法）

**File:** `src/etl/label_reconcile.py:429-504`
**Issue:**
`_check_raw_validated_drift` の docstring（429-452）は「label 自体の正当性は precision/recall BLOCK 検査（label↔HR 直接照合）が保証する」と主張する。しかし deep 分析でこの主張は**循環論法**であることを確認した:

- `fukusho_hit_validated` は `compute_fukusho_labels` で HR `PayFukusyoUmaban1..5` から直接生成（fukusho_label.py:675-681）
- `_check_payout_precision` / `_check_payout_recall` は `fukusho_hit_validated` を再び HR `PayFukusyoUmaban` と JOIN して照合（label_reconcile.py:177-198, 230-251）
- つまり「HR payout から作った label を HR payout と比較して一致」は **tautology** であり、HR payout の誤り（例: 本来 `payfukusyoumaban3='03'` のべきが `'30'` に入力ミス）は precision/recall 検査では検知できない
- SE `KakuteiJyuni` との cross-check（HIGH #2 の本来の意图）だけが独立ソースによる検証になる
- `non_dead_heat_drift_count > 0` は「SE と HR が矛盾する行が存在」=「どちらかが誤り」を意味する

`label_reconcile.py:449-451` の「D-02 一貫: 構造的欠陥=BLOCK（precision/recall）・量化ドリフト=INFO（drift）」という区分は、precision/recall が tautology である事実を無視している。Core Value（リーク防止と同等の聖域）に照らせば、予測目標 `fukusho_hit_validated` が間違っている可能性を INFO で処理する設計は、LABEL-03 gate が label 誤りを素通りさせることを許す。

特に `validated` status での drift（`label_reconcile.py:444-447` が「source data quality issue → INFO レポートが適切」と主張）は、**HR payout slot と SE 着順が矛盾する = label が間違っている可能性がある**行を含み、これを gate が素通りする構造は予測目標の正しさを保証できない。

**Fix:**
`validated` / `inferred` status での drift（`non_dead_heat_drift_count` のうち `validated`/`inferred` のみ）を BLOCK 条件に格上げする。`unresolved` の drift（race_cancelled で KakuteiJyuni が無い馬が HR payout に含まれる等・D-04-legitimate）と `dead_heat`（payout 拡張・正当）は INFO のままで良い。

```python
# _check_raw_validated_drift 内で non_dead_heat_drift_count を計算した後:
# validated/inferred status での drift のみ BLOCK 対象
cur.execute(
    f"""
    SELECT count(*) FROM label.fukusho_label
    WHERE {PROJECT_WINDOW_FILTER}
      AND fukusho_hit_raw != fukusho_hit_validated
      AND label_validation_status IN ('validated', 'inferred')
    """
)
serious_drift = int(cur.fetchone()[0])

return CheckResult(
    name="raw_validated_drift",
    passed=serious_drift == 0,           # 現状の passed=True 固定を撤廃
    severity="block" if serious_drift > 0 else "info",
    detail=columns,
)
```

---

### CR-02: `_compute_race_level_agreement` で SQL injection 可能な f-string 展開

**File:** `src/etl/label_reconcile.py:701-715`
**Issue:**
`held_out_list`（DB 由来 PK tuple）を f-string で直接 SQL に展開:

```python
where_race_keys = " OR ".join(
    f"(hr.year::int={rk[0]} AND hr.jyocd='{rk[1]}' AND hr.kaiji::int={rk[2]} "
    f"AND hr.nichiji='{rk[3]}' AND hr.racenum::int={rk[4]})"
    for rk in held_out_list
)
```

インラインコメント（705-707）は「DB から取得した PK 値（SQL injection source ではない）」と主張するが:

1. **defense-in-depth 違反** — プロジェクト全体（`schema.py`, `apply_schema.sql`, `fukusho_label.py:843` の `psycopg.sql.Identifier`, `run_label_reconcile.py:47` の allowlist filter）がパラメータ化を一貫している中、ここだけ文字列展開に逃げている
2. **`jyocd` / `nichiji` が varchar** であり、EveryDB2 のデータ品質に依存する（万が一 `'\''` のような値が混入した場合クエリが破壊される）
3. **将来のリファクタで `held_out_list` が外部入力に繋がった場合の silent vulnerability**

CLAUDE.md「silent fallback 禁止（D-13）」とプロジェクトのセキュリティ原則に違反。

**Fix:**
psycopg3 のパラメータ埋め込みと `UNNEST` を使った set-based 比較に変更。

```python
years = [rk[0] for rk in held_out_list]
jyocds = [rk[1] for rk in held_out_list]
kaijis = [rk[2] for rk in held_out_list]
nichijis = [rk[3] for rk in held_out_list]
racenums = [rk[4] for rk in held_out_list]

cur.execute(
    f"""
    SELECT year, jyocd, kaiji, nichiji, racenum,
           payfukusyoumaban1, payfukusyoumaban2, payfukusyoumaban3,
           payfukusyoumaban4, payfukusyoumaban5
    FROM public.n_harai hr
    WHERE {PROJECT_WINDOW_FILTER}
      AND (hr.year::int, hr.jyocd, hr.kaiji::int, hr.nichiji, hr.racenum::int)
          IN (SELECT * FROM unnest(%s::int[], %s::text[], %s::int[], %s::text[], %s::int[])
              AS t(year, jyocd, kaiji, nichiji, racenum))
    """,
    (years, jyocds, kaijis, nichijis, racenums),
)
```

---

### CR-03: `_payout_places` / `_is_dh` で `pd.NA`・異常 torokutosu 経路の TypeError リスク

**File:** `src/etl/fukusho_label.py:627-635`（`_payout_places`）, `694-701`（`_is_dh`）, `478-481`（`compute_is_model_eligible`）
**Issue:**
deep 分析で3箇所の `int()` 変換経路を確認した:

```python
def _payout_places(t: Any) -> int:
    if t is None or _is_na(t):
        return no_sale
    ti = int(t)            # (1) pd.NA は _is_na で捕捉されるが、pd.NA が nullable Int64 を経由した場合は要検証
    ...
```

`_is_na(pd.NA)` は `pd.isna(pd.NA)` → `True` を返すため通常は捕捉される。しかし:

1. **(1) `_payout_places`**: 実DBの `torokutosu` varchar が異常値（空文字・英字混じり）の場合、`pd.to_numeric(errors="coerce")`（fukusho_label.py:545）は `np.float64(nan)` を返し `_is_na` で捕捉される。ただし `pd.NA` を直接 map に渡した場合（`Int64` nullable dtype 経由等）、`int(pd.NA)` は `TypeError`。`_is_na` の `pd.isna(pd.NA) == True` で先に抜けるため実経路上は安全だが、**ユニットテスト（test_fukusho_label.py）が `float("nan")` と `None` しかカバーしておらず、`pd.NA` / `np.float64(nan)` の regression が未検証**。

2. **(2) `_is_dh` の `int(pc)`**（fukusho_label.py:696, 701）: `pc = r.get("payout_count", 0)` は `merged["payout_count"]` から来る。`payout_count` は `compute_fukusho_labels` 内で `payout_counts` list（行毎の `len(s)`）から構築されるため常に int だが、HR merge が `how="left"` で HR 欠損行（test_unresolved_triggers_hr_missing シナリオ）では `payout_count` カラムが NaN になる可能性がある。実際には `compute_fukusho_labels:572` で `hr["payout_count"] = payout_counts` が設定された後に left merge され、HR 欠損行では NaN になる。`_is_dh` は `if pc is None or _is_na(pc): return False`（699-700）で保護されているが、`int(pp)`（701）の `pp = r["fukusho_payout_places"]` が `pd.NA` の場合の経路が `_is_na` で保護されているとはいえ、`payout_count` が `0`（HR 欠損で NaN ではなくデフォルト）の場合の `int(pp) > 0` の挙動も要検証。

3. **(3) `compute_is_model_eligible` の `int(class_level)`**（fukusho_label.py:479）: `class_level = row.get("class_level_numeric")` が `pd.NA` の場合、`_is_na(class_level)` で捕捉されるが、`Int64` nullable dtype で `pd.NA` が入った場合の `int(pd.NA)` は `TypeError`。`_is_na` が先に True を返すため安全だが、**`pd.NA` 入力のテストカバレッジが不足**。

加えて `_raw_hit` の `int(pp)`（fukusho_label.py:655）は `_payout_places` の戻り値（常に int）なので安全、`int(kj)`（659）の `kj = r["kakuteijyuni_i"]` は `pd.to_numeric` 結果（NaN 可能）だが `if kj is None or _is_na(kj): return 0`（657-658）で保護されている。

**Fix:**
`_payout_places` と `_is_dh` の冒頭で `_is_na` 後に `float()` を挟んで `int()` に回す、または `pd.to_numeric(...).astype("Int64").fillna(-1)` で sentinel 化する。テストに `pd.NA` / `np.float64(nan)` / `""` 入力の regression を追加する。

```python
def _payout_places(t: Any) -> int:
    if t is None or _is_na(t):
        return no_sale
    try:
        ti = int(float(t))   # pd.NA 経路でも float() で TypeError を回避
    except (TypeError, ValueError):
        return no_sale
    if ti >= 8:
        return places_8plus
    if min_torokutosu <= ti <= 7:
        return places_5_7
    return no_sale
```

---

### CR-04: `fukusho_hit_raw` が race_cancelled / fuseiritu / tokubarai 空レースでも `kakuteijyuni` ベースで算出され、`fukusho_hit_raw=1` の行が残留

**File:** `src/etl/fukusho_label.py:651-662`
**Issue:**
`fukusho_hit_raw` は `fukusho_payout_places > 0 AND 1 <= kakuteijyuni <= payout_places` のみで算出され、`label_validation_status` / `is_race_cancelled` を見ない。cross-file で以下を確認した:

- `_select_se_state`（fukusho_label.py:183-230）は `datakubun IN ('7', '9')` で SE を SELECT するため、race_cancelled（`datakubun='9'`）の SE 行も含まれる
- race_cancelled レースでも EveryDB2 の SE `kakuteijyuni` には `1,2,3` 等が入り得る（レース中止前に確定着順が記録されたケース、または中止レースでも着順が便宜的に入るケース）
- これらの行で `fukusho_hit_raw=1` になり得る（`kakuteijyuni <= payout_places` を満たすため）
- 一方 `label_validation_status='unresolved'` となり、`fukusho_hit_validated=0`（HR payout が無いため）
- つまり **`raw=1, valid=0` の drift 行**が unresolved status で発生

この drift 行は CR-01 の INFO 格下げと組み合わさって致命的になる:
- LABEL-03 gate は `non_dead_heat_drift_count > 0` を INFO で処理（CR-01）
- Phase 3 が誤って `fukusho_hit_raw` を目的変数に使った場合（仕様違反だがヒューマンエラーで起こり得る）、race_cancelled の偽正例が学習データに混入する silent leak 源になる

D-13（silent fallback 禁止）と Core Value に照らせば、outcome が確定しないレースでは `fukusho_hit_raw` も NULL または 0 に正規化すべき。

加えて **`fukusho_payout_places` 自体も race_cancelled レースで `torokutosu >= 5` なら `places_8plus` 等の正の値になる**（`_payout_places` は status を見ない）。これは「複勝発売が実際には無かった（中止）レースで `is_fukusho_sale_available=True` になる」可能性を含み、`_check_no_fukusho_sale_not_in_training`（label_reconcile.py:400-423）の「`is_model_eligible=True AND is_fukusho_sale_available=False`」検査では捕捉できない逆方向の汚染（中止レースで `is_fukusho_sale_available=True` になる）を生む。

**Fix:**
`compute_fukusho_labels` の最後で `label_validation_status='unresolved'` の行の `fukusho_hit_raw` を 0 に上書きする（schema の `fukusho_hit_raw smallint NOT NULL` 制約（fukusho_label.py:808）を維持するなら 0 が安全）。`is_fukusho_sale_available` も race_cancelled では False に正規化する。

```python
# compute_fukusho_labels の status 計算の後:
mask_unresolved = merged["label_validation_status"] == "unresolved"
merged.loc[mask_unresolved, "fukusho_hit_raw"] = 0
# race_cancelled では複勝発売も実際には無いため False に正規化
mask_race_cancelled = merged["is_race_cancelled"] == True  # noqa: E712
merged.loc[mask_race_cancelled, "is_fukusho_sale_available"] = False
merged.loc[mask_race_cancelled, "fukusho_payout_places"] = 0
```

---

### CR-05: `_check_payout_precision` / `_check_payout_recall` の JOIN が `monthday` を無視 — cross-join 誤照合リスク

**File:** `src/etl/label_reconcile.py:177-198`（`_check_payout_precision`）, `230-251`（`_check_payout_recall`）
**Issue:**
両検査の JOIN 条件は `(year, jyocd, kaiji, nichiji, racenum)` で `monthday` を含まない。cross-file で検証した:

1. **`label.fukusho_label` 側は `race_date` を持つが `monthday` 列を持たない**（`_LABEL_TABLE_COLUMNS`, fukusho_label.py:790-822）— JOIN に使えない構造的欠陥
2. **`PROJECT_WINDOW_FILTER`（`filters.py`）は `jyocd + year >= 2015` のみ**で、race-key 一意性を主張しない
3. **`_compute_race_level_agreement`（label_reconcile.py:626-642）は `normalized.n_race` を経由して `race_date` を取得**しているが、precision/recall は `label.fukusho_label` と `public.n_harai` を直接 JOIN するため `monthday` を使えない
4. コメント（label_reconcile.py:174-176, 228）は「race-key PK (year, jyocd, kaiji, nichiji, racenum) は JRA+2015 で一意（実測 39,580 = 39,580 distinct）」と主張するが、この検証は `quality_gate.py` の `N_RACE_PK_COLS = "year, jyocd, kaiji, nichiji, racenum"` で行われたものであり、**`public.n_harai` 側の一意性は `label` 側 PK 一意性とは別物**（HR は同一 race-key で `datakubun='1'` 速報と `'2'` 月曜確定の複数行を持ち得る）

EveryDB2 仕様上 `monthday` は自然キーの一部であり、同一 (year, jyocd, kaiji, nichiji, racenum) で `monthday` が異なるレースが将来導入された場合に即座に壊れる。precision/recall は count-based のため誤照合があっても気づかず pass する。

`_compute_race_level_agreement` は完全一致比較（race-set reconstruction）なので誤照合が disagree として検出されるが、precision/recall は count のみのため silent failure になる。

**Fix:**
`label.fukusho_label` に `monthday` 列を追加（schema 変更要）、または `normalized.n_race` を経由して `monthday` を取得する。

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

### CR-06: `_LABEL_WINDOW_FILTER` / `PROJECT_WINDOW_FILTER` の二重管理 — フィルタの単一ソース原則違反

**File:** `src/etl/label_reconcile.py:87`（`_LABEL_WINDOW_FILTER`）, `src/etl/filters.py:46`（`PROJECT_WINDOW_FILTER`）
**Issue:**
cross-file 分析で発見。`filters.py` の docstring は:

> CR-06 found that the "JRA filter" was defined three different ways in three modules with three different scopes ... This module is the single source of truth; downstream modules import from here.

と明記している。しかし `label_reconcile.py:87` は `_LABEL_WINDOW_FILTER = "l.jyocd BETWEEN '01' AND '10' AND l.year::int >= 2015"` を**ハードコード**で再定義している。これは:

1. **`filters.py` の単一ソース原則に明確に違反** — `filters.py` 自身が CR-06 で三重管理を統一した経緯があるのに、Phase 2 で新たな二重管理を導入している
2. **`label.fukusho_label.year` は DDL で `int`（fukusho_label.py:792）** — `_LABEL_WINDOW_FILTER` の `l.year::int >= 2015` は `int::int` となり無害だが、これは `PROJECT_WINDOW_FILTER`（`year::int >= 2015`）を `l.` 修飾と `::int` 重複キャストで複製したに過ぎない
3. **将来 `PROJECT_WINDOW_FILTER` の期間や JRA 範囲を変更した場合、`_LABEL_WINDOW_FILTER` が追随されない silent drift 源**

実際、`label_reconcile.py` 内では `_LABEL_WINDOW_FILTER` と `PROJECT_WINDOW_FILTER` が混在している:
- `_check_payout_precision` / `_check_payout_recall`（JOIN クエリ）→ `_LABEL_WINDOW_FILTER`
- `_check_dead_heat_integrity` / `_check_raw_validated_drift` / `_check_label_status_distribution`（単一テーブル）→ `PROJECT_WINDOW_FILTER`

`label.fukusho_label` に `PROJECT_WINDOW_FILTER`（`year::int`）を適用すると `int::int` となるが Postgres は暗黙キャストするため機能的には問題ない。つまり `_LABEL_WINDOW_FILTER` の存在意義は「`l.` 修飾」のみであり、これは JOIN クエリ側で `l.year::int` と書けば済む話。

**Fix:**
`_LABEL_WINDOW_FILTER` を廃止し、JOIN クエリでは `PROJECT_WINDOW_FILTER` を `l.` / `hr.` 修飾に展開するか、`filters.py` に `project_window_filter(alias: str = "")` のような helper を追加する。

```python
# filters.py に追加:
def project_window_filter(alias: str = "") -> str:
    """PROJECT_WINDOW_FILTER を alias 修飾で返す（JOIN クエリ用）。"""
    p = f"{alias}." if alias else ""
    return f"{p}jyocd BETWEEN '01' AND '10' AND {p}year::int >= 2015"

# label_reconcile.py で:
from src.etl.filters import project_window_filter
sql = f"... WHERE {project_window_filter('l')} AND ..."
```

---

### CR-07: `test_verdict_pass_when_all_block_pass` が CR-01 のバグを隠蔽する方向に作用

**File:** `tests/test_label_reconcile.py:442-469`
**Issue:**
cross-file 分析で発見。`test_verdict_pass_when_all_block_pass` は:

```python
pass_checks = {
    "_check_payout_precision",
    "_check_payout_recall",
    "_check_dead_heat_integrity",
    "_check_no_scratch_mislabeled",
    "_check_dead_loss_not_excluded",
    "_check_no_fukusho_sale_not_in_training",
    "_check_raw_validated_drift",   # ← 実コードは severity="info" だが…
}
for name in pass_checks:
    monkeypatch.setattr(
        label_reconcile, name,
        lambda cur, _n=name: CheckResult(name=_n, passed=True, severity="block", detail={}),  # ← "block" で上書き
    )
```

`_check_raw_validated_drift` の実コード（label_reconcile.py:499-504）は `severity="info"` だが、テストは `severity="block"` で上書きしている。これは:

1. **現在の実装（INFO）では、このテストが monkeypatch で `_check_raw_validated_drift` を BLOCK にしないと verdict pass を再現できない** — つまり実コードでは `reconcile_against_payout` の `r.severity == "block"` 集計（label_reconcile.py:831）に `_check_raw_validated_drift` が含まれないため、このテストの pass は「CR-01 が修正された場合（drift を BLOCK に格上げ）の想定」を模倣しているに過ぎない
2. **現在の実装（CR-01 の INFO 格下げ）のテストカバレッジが実質無い** — drift 検査が verdict に影響しないことの回帰テストが欠落
3. **テストが CR-01 のバグ（INFO 格下げ）を正常状態として前提している** — テストを修正せずに CR-01 を修正すると、このテストが壊れる（`_check_raw_validated_drift` を BLOCK にすると monkeypatch の `severity="block"` と一致して pass するが、現在は mock が BLOCK を与えているだけ）

これは deep 視点で重要: テストが実装のバグを固定化する方向に作用しており、CR-01 を修正する際にテストも同時に見直す必要がある。テストの意図（「全 BLOCK pass で verdict pass」）自体は正しいが、現在の実装と乖離している。

**Fix:**
テストを現在の実装に合わせる（`_check_raw_validated_drift` を `severity="info"` で模倣）か、CR-01 を修正して BLOCK に格上げした上でこのテストの monkeypatch `severity="block"` を維持する。CR-01 修正が推奨されるため、このテストは現状維持で良いが、テストの docstring に「CR-01 修正後の想定テスト」である旨を明記すべき。

```python
def test_verdict_pass_when_all_block_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 BLOCK 検査 passed=True の場合、verdict='pass'。

    NOTE: CR-01 修正（_check_raw_validated_drift の BLOCK 格上げ）を前提としたテスト。
    現状の実装（INFO）では _check_raw_validated_drift は verdict に影響しないため、
    このテストの monkeypatch は「BLOCK 格上げ後」の振る舞いを模倣している。
    """
    ...
```

---

## Warnings

### WR-01: `_check_payout_recall` は dead_heat レースの非対象馬の不当 validated=1 を検知できない

**File:** `src/etl/label_reconcile.py:222-268`
**Issue:**
`_check_payout_recall` は「HR payout set に含まれるが `fukusho_hit_validated=0` の馬」を検知する。しかし dead_heat レースでは `compute_fukusho_labels` が HR payout slot を全て `validated=1` にするため、この検査は dead_heat レースでは常に 0 になる。つまり:

- **dead_heat フラグ誤設定で非対象馬が不当に `validated=1` になっているケース**（slot4/5 に含まれていないのに `is_dead_heat=True` で処理された等）は `_check_payout_precision`（`validated=1` だが payout set に無い）で検知できる
- しかし逆方向（`is_dead_heat` が誤って False で、本来対象の slot4/5 馬が `validated=0`）は `_check_payout_recall` で検知できる
- **`is_dead_heat` フラグの誤設定で非対象馬が不当に payout set 扱いになっているケース**は両検査で見えない

`_check_dead_heat_integrity`（label_reconcile.py:274-314）は status↔flag の整合を検査するが、`is_dead_heat` と payout set の実内容（slot4/5 が本当に埋まっているか）の整合は検査しない。

**Fix:**
`is_dead_heat=True` のレースで `payout_count`（HR payout slot の非空数）と `fukusho_payout_places` の比較、および「`is_dead_heat=True` なのに slot4/5 が空」の逆方向検査を `_check_dead_heat_integrity` に追加する。

---

### WR-02: `_check_no_scratch_mislabeled` の `fukusho_hit_validated == 1` が NULL で違反見逃し

**File:** `src/etl/label_reconcile.py:335`
**Issue:**
```python
viol_df = df[(df["recomputed_is_scratch"] == True) & (df["fukusho_hit_validated"] == 1)]  # noqa: E712
```

`fukusho_hit_validated` は `label.fukusho_label.fukusho_hit_validated smallint`（fukusho_label.py:809）。`_recompute_scratch_markers`（label_reconcile.py:125-138）の SELECT は `l.fukusho_hit_validated` をそのまま返す。schema 上は `smallint`（NOT NULL 制約は明記されていない）のため、万が一 NULL が混入した場合、`NULL == 1` は pandas で `False` 扱いになり違反行が見逃される。

**Fix:**
```python
viol_df = df[
    (df["recomputed_is_scratch"] == True)  # noqa: E712
    & (df["fukusho_hit_validated"].fillna(0).astype(int) == 1)
]
```

---

### WR-03: `_VALID_INELIGIBILITY_REASONS` と `label_spec.yaml.ineligibility_reason_codes` の重複定義

**File:** `src/etl/label_reconcile.py:68-76`, `src/config/label_spec.yaml:225-232`
**Issue:**
`_VALID_INELIGIBILITY_REASONS` が `label_reconcile.py` 内にハードコードされており、`label_spec.yaml.ineligibility_reason_codes` と同一内容だが別管理。将来 reason code を追加した場合に両者の同期が壊れる。これは「ラベル定義の単一の正（D-07）」原則に反する。

インラインコメント（label_reconcile.py:67）は「ハードコードで安全性確保・D-13」と主張するが、D-13 は「未知コードを silent fallback しない」であって「単一の源を持つな」ではない。`label_spec.yaml` を load して `frozenset(...)` で構築すれば同じ安全性が保てる。

**Fix:**
```python
def _valid_ineligibility_reasons() -> frozenset[str]:
    spec = load_label_spec()
    return frozenset(spec["ineligibility_reason_codes"])
```

---

### WR-04: `is_fukusho_sale_available` / `_payout_places` の境界値が `min_torokutosu` で結合されている構造的脆さ

**File:** `src/etl/fukusho_label.py:639-649`（`is_fukusho_sale_available`）, `627-635`（`_payout_places`）
**Issue:**
`is_fukusho_sale_available` は `torokutosu_i >= min_torokutosu AND fuseirituflag2 != '1'`（min_torokutosu=5）。`_payout_places` は `min_torokutosu(5) <= ti <= 7` で `places_5_7`、`ti >= 8` で `places_8plus`、それ以外で `no_sale`。

境界自体は整合しているが、`min_torokutosu`（=5）が「複勝発売の有無」と「払戻対象数の下限」の2つの異なる概念に使われており、将来の仕様変更で片方だけ変えた場合に同期が壊れる構造的脆さがある。

加えて `label_spec.yaml:33-46`（`payout_places_rules`）の `note` は「境界は HR PayFukusyoUmaban/FuseirituFlag2 の観測事実で最終確定する（D-01 厳格）」と明記するが、実装は `torokutosu` のみで判定しているため **spec と実装がずれている**。Pitfall 3 コメント（fukusho_label.py:626）は「`fukusho_payout_places` 境界は torokutosu（登録頭数＝出馬表発表時）のみで決定」と主張するが、これは `label_spec.yaml` の `note`（HR 観測事実で確定）と矛盾する。

**Fix:**
`label_spec.yaml` に `fukusho_sale_min_torokutosu`（発売有無の閾値）と `payout_places` 境界（5-7 / 8+）を分離して定義する。または spec の `note` を torokutosu ベースの実装に合わせて訂正する。

---

### WR-05: `_select_se_state` の 2回 SELECT が同一フィルタであることの直接 assert が無い

**File:** `src/etl/fukusho_label.py:183-230`
**Issue:**
`_select_se_state` は基本状態（`_SE_SELECT_COLUMNS`）と timediff（`_SE_TIMEDIFF_SELECT_COLUMNS`）を別々に SELECT して merge する。両 SELECT は共に `datakubun IN ('7', '9')` でフィルタする前提だが:

1. テスト `test_select_se_state_no_row_multiplication_on_timediff_merge`（test_fukusho_label.py:731-774）は正規表現で `datakubun IN ('7','9')` を検出するが、**両 SELECT が同じフィルタを持つことを直接 assert していない** — 片方だけ `datakubun IN ('7')` に退化しても、もう片方に `'9'` が含まれていれば正規表現は通る
2. merge 後の行数 assertion（`if len(merged) != pre_len: raise`）は行数増殖のみ検知する。timediff_df 側が SE 側より**行が少ない**場合（timediff 側だけフィルタが厳しい場合）、`how="left"` で post_len == pre_len になり assertion を通過するが、**timediff が NaN のまま進む**経路がある（詳しくは WR-10）
3. merge キーに `datakubun` を含めているため、片側だけ `'9'` を欠いた場合、`datakubun='9'` 行の timediff が NaN になる

deep 分析では、両 SELECT のフィルタ一致をコードレビューで確認した（両方とも `f"WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')"`）。しかしテストカバレッジとしては不十分。

**Fix:**
2つの SELECT を1つに統合する（`_SE_SELECT_COLUMNS` に `timediff`/`dochakukubun`/`dochakutosu` を含める）。または両 SELECT の SQL 文字列を比較する assertion を追加する。

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
if actual != len(rows):
    raise RuntimeError(...)
```

psycopg3 の `executemany` の `rowcount` は「全バッチ合計」を返す仕様（psycopg3 docs）だが、pipeline mode の有無や PostgreSQL バージョンで `PQcmdTuples` の挙動が変わる。psycopg3 は `executemany` を内部的に pipeline で実行するため、`rowcount` が「最後のクエリの影響行数」になる場合がある。

加えて `rows` が大きい（55万行）場合、psycopg3 は自動的にバッチ化するため、`rowcount` と `len(rows)` の比較が常に成立するとは限らない。

**Fix:**
`rowcount` に頼らず、INSERT 後に `SELECT count(*) FROM label.fukusho_label_staging` で検証する。

```python
write_cur.execute("SELECT count(*) FROM label.fukusho_label_staging")
actual = int(write_cur.fetchone()[0])
if actual != len(rows):
    raise RuntimeError(
        f"_idempotent_load_label: staging table has {actual} rows, "
        f"expected {len(rows)} (CR-04 rowcount verification)"
    )
```

---

### WR-07: `run_label_etl` の checksum が `row(r.*)::text` で列順序依存 — ALTER TABLE で checksum が変わる

**File:** `src/etl/fukusho_label.py:1051-1057`
**Issue:**
```python
wcur.execute(
    "SELECT md5(string_agg(md5(row(r.*)::text), '' "
    "ORDER BY year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)) "
    "FROM label.fukusho_label r"
)
```

`row(r.*)::text` は列順序に依存する。将来 `ALTER TABLE label.fukusho_label ADD COLUMN ...` した瞬間に checksum が変わり、**同じデータでも別 checksum** を返すようになる。これは idempotent 検証（`result1["checksum"] == result2["checksum"]`）を破壊する。

加えて `string_agg` は全行をメモリに蓄えるため、55万行を超えると PostgreSQL の work_mem を消費しディスクソートに落ちる可能性がある（性能問題は scope 外だが、機能問題として checksum の正しさに影響）。

**Fix:**
列を明示的に列挙する、または `pg_md5_hash` 系の集計関数を使う。

```python
# 列明示版（_LABEL_INSERT_COLUMNS を使う）
cols_csv = ", ".join(_LABEL_INSERT_COLUMNS)
wcur.execute(
    f"SELECT md5(string_agg(md5(row({cols_csv})::text), '' "
    f"ORDER BY year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)) "
    f"FROM label.fukusho_label"
)
```

---

### WR-08: `run_label_etl` の read connection ブロックが明示的 rollback を持たない

**File:** `src/etl/fukusho_label.py:1024-1029`
**Issue:**
```python
with read_pool.connection() as conn:
    with conn.cursor() as cur:
        hr_df = _select_raw_harai(cur)
        se_df = _select_se_state(cur)
        race_df = _select_race_meta(cur)
# ← conn.rollback() / commit() が無い
```

context manager 抜け時に connection は pool に戻るが、READ COMMITTED で長時間トランザクションが残ると ETL の write_pool とロック衝突する可能性がある。`scripts/run_label_etl.py:66-68` では明示的に `conn.rollback()` しているが、`run_label_etl` 本体（fukusho_label.py:1024-1029）では明示的なトランザクション終了が無い。

`test_raw_unchanged_after_label_etl`（test_raw_immutability.py:70-92）から呼ばれた際、`run_label_etl` 内の read connection と `compute_raw_fingerprint` の readonly_cur が同一 pool から別々に借りられるため、トランザクション分離レベルによっては見え方が異なる。

**Fix:**
`with read_pool.connection() as conn:` ブロックの最後に `conn.rollback()` を明示する（SELECT only なので commit と等価）。

---

### WR-09: `run_label_etl` の `settings=None` デフォルト構築で reader_role 警告が到達不能

**File:** `src/etl/fukusho_label.py:1015-1022`
**Issue:**
```python
if settings is None:
    settings = Settings()
reader_role = getattr(settings, "db_reader_role", None) or "keiba_readonly"
if not getattr(settings, "db_reader_role", None):
    logger.warning("Settings.db_reader_role が未設定のため default 'keiba_readonly' を使用します ...")
```

`Settings` は `db_reader_role: str = "keiba_readonly"`（settings.py:46）。`getattr(settings, "db_reader_role", None)` は常に `"keiba_readonly"` を返し、`not "keiba_readonly"` は `False`。つまり**警告は決して発火しない**デッドロジック。

**Fix:**
デッドロジックを削除して `reader_role = settings.db_reader_role` に単純化する。または `.env` でロール名を上書きできる意図なら `db_reader_role: str | None = None` にして明示的な未設定状態を区別する。

---

### WR-10: `_select_se_state` の `how="left"` merge で timediff 側の余剰行が検知されない

**File:** `src/etl/fukusho_label.py:218-229`
**Issue:**
cross-file 分析で発見。`merged = se_df.merge(timediff_df, on=merge_keys, how="left")` は左結合のため:

1. **timediff_df 側に SE 側に無い行が存在した場合**（例: timediff 側だけフィルタが緩く `datakubun='1'` 速報行が混入）、`how="left"` で右側の余剰行は捨てられ、`post_len == pre_len` になる。つまり**timediff 側の汚染が検知されないまま進む**
2. **逆方向**（timediff 側が SE 側より行が少ない、例: timediff 側だけフィルタが厳しい）も、`how="left"` で `timediff` 列が NaN になり `post_len == pre_len`。行数 assertion は通過するが **timediff が NaN のままラベル計算に進む**

`merge.assert` は行数増殖のみを検知し、左右の不整合を検知しない。`_canonicalize_value` は NaN を `__MISSING__` sentinel にマップするため、timediff が NaN でも `marker_active` 計算で sentinel 集合比較に回り、結果的に `marker_active=False` になるため直ちに crash はしない。しかし**timediff が本来あるべき値（例: '9999'）で無く NaN になることで、競走中止馬が正常馬に誤分類される silent leak 源**になる可能性がある。

`compute_fukusho_labels` の `_canonicalize_markers` は `timediff` が NaN の場合、`marker_active=False` → `is_dead_loss=False` とする。つまり本来 `timediff='9999'` で `is_dead_loss=True` になるべき競走中止馬が、merge の左結合で timediff が欠損した場合に `is_dead_loss=False` になり、**学習データに紛れ込む**。

**Fix:**
`how="left"` を `how="inner"` に変更し、両側の行が完全一致することを強制する。または merge 後に `timediff` 列の NaN 数を assert する。

```python
# inner merge で両側一致を強制:
merged = se_df.merge(timediff_df, on=merge_keys, how="inner")
if len(merged) != pre_len:
    raise RuntimeError(
        f"_select_se_state: timediff merge で行数が不一致 "
        f"(se={pre_len}, merged={len(merged)})。timediff_df 側に "
        f"SE 側と一致しない行が存在する可能性（NEW HIGH #2）"
    )
# timediff が全て非 NaN であることも assert
if merged["timediff"].isna().any():
    raise RuntimeError(
        f"_select_se_state: merge 後の timediff に NaN が {merged['timediff'].isna().sum()} 件存在"
    )
```

---

### WR-11: `scripts/run_label_etl.py` の read connection 取得+即 rollback がデッドコード

**File:** `scripts/run_label_etl.py:58-67`
**Issue:**
cross-file 分析で発見:

```python
# (1) 1回目の connection 取得
with read_pool.connection() as conn:
    with conn.cursor() as cur:
        before = compute_raw_fingerprint(cur)
logger.info(...)
# (2) 2回目の connection 取得 + 即 rollback
with read_pool.connection() as conn:
    conn.rollback()
```

psycopg_pool の `ConnectionPool.connection()` context manager は抜ける際に自動で `conn.rollback()` または `commit()` を発行する（psycopg3 仕様）。つまり (1) の `with` ブロックを抜けた時点で read transaction は閉じられている。(2) の2回目の connection 取得+rollback は**無意味なデッドコード**。

コメント（line 65「readonly transaction を閉じる（ETL の raw SELECT とロック衝突回避）」）の意図は理解できるが、psycopg_pool の挙動を誤解している。(1) のブロックを抜けた時点で目的は達成されている。

**Fix:**
(2) のブロックを削除する。

```python
with read_pool.connection() as conn:
    with conn.cursor() as cur:
        before = compute_raw_fingerprint(cur)
logger.info(
    "raw fingerprint before label ETL: row_counts=%s",
    {k: v for k, v in before["row_count"].items()},
)
# psycopg_pool は context manager 抜けで自動 rollback するため
# 明示的な2回目 connection 取得+rollback は不要（削除）

# --- ETL 1回目実行 ---
result1 = run_label_etl(read_pool, write_pool, settings=settings)
```

---

## Info

### IN-01: `compute_is_model_eligible` の `class_level_numeric` が `pd.NA` のときの regression 未カバー

**File:** `src/etl/fukusho_label.py:478-481`
**Issue:**
`class_level = row.get("class_level_numeric")` が `pd.NA` の場合、`_is_na(class_level)` で捕捉されるため `int(class_level)` には進まない。ユニットテスト（test_fukusho_label.py:658-683）は `class_level_numeric=0` と `class_level_numeric=1` のみカバーし、`pd.NA` は未カバー。
**Fix:** テストに `class_level_numeric=pd.NA` ケースを追加する。

---

### IN-02: `test_label_reconcile.py` の mock cursor が SQL 部分文字列マッチで順序依存

**File:** `tests/test_label_reconcile.py:61-87`
**Issue:**
`_mock_cursor` の `_fetchone` は SQL 部分文字列マッチで戻り値を決める。`fetch_map` のキー順序に依存する。`_check_payout_precision`（`fukusho_hit_validated = 1 AND NOT EXISTS`）と `_check_payout_recall`（`fukusho_hit_validated = 0 AND EXISTS`）の SQL は共通部分文字列を含むため、`fetch_map` のキー順序で誤ヒットする可能性がある。実際には `"fukusho_hit_validated = 1"` と `"fukusho_hit_validated = 0"` で区別されるが、順序依存性がある。
**Fix:** mock をより厳密な SQL パターンマッチ（正規表現）にする。

---

### IN-03: `time_sentinels_absent` に `"00"` / `"000"` / `"0.00"` 等の zero-pad 表現が無い

**File:** `src/config/label_spec.yaml:121`
**Issue:**
`time_sentinels_absent: ["0", "0.0", "", "9999", "9999.0"]` に対し、`bataijyu_sentinels_scratch` は `"000"` を含む。EveryDB2 の `time` varchar が `"00"` / `"0.00"` / `"000"` 等の zero-pad 表現を返した場合、sentinel 集合外となり `time_present=True` になるリスクがある。
**Fix:** `"00"`, `"000"`, `"0.00"`, `"0000"` 等のバリエーションを追加、または正規表現ベースの zero 判定に切り替える。

---

### IN-04: `KEIBA_SKIP_DB_TESTS=1` が reconcile gate を silently pass させる

**File:** `scripts/run_label_reconcile.py:92-96`
**Issue:**
`KEIBA_SKIP_DB_TESTS=1` 設定時に exit 0 でスキップする。CI で「DB 無し環境を許可」する意図だが、この環境変数が誤って本番 CI に設定されていた場合、LABEL-03 gate が常に pass してしまう。silently passing gate は Core Value に照らして危険。

加えて cross-file で `scripts/run_label_etl.py` は `KEIBA_SKIP_DB_TESTS` を見ない（IN-05 参照）。

**Fix:** skip 時は exit 0 ではなく、明示的な `SKIP` verdict を出力し、CI 側で `SKIP` を検知して別ジョブを trigger する等の運用にする。

---

### IN-05: `scripts/run_label_etl.py` が `KEIBA_SKIP_DB_TESTS` を見ない — reconcile との不整合

**File:** `scripts/run_label_etl.py`（全体）
**Issue:**
cross-file 分析で発見。`scripts/run_label_reconcile.py:92-96` は `KEIBA_SKIP_DB_TESTS=1` で reconcile を skip するが、`scripts/run_label_etl.py` には同等の skip ロジックが無い。CI で `KEIBA_SKIP_DB_TESTS=1` を設定した場合:

- `run_label_etl.py` は実行される（DB 接続を試み、接続失敗で exit 3）
- `run_label_reconcile.py` は skip される（exit 0）

この不整合により、CI の LABEL gate（reconcile）だけが skip され、ETL の raw 不変性・idempotency 検証だけが走る（または両方失敗する）状態になる。これは CI の意図（「DB 無し環境では LABEL 系を全て skip」）と整合しない。

**Fix:**
`run_label_etl.py` にも `KEIBA_SKIP_DB_TESTS=1` チェックを追加する。または skip ポリシーを `conftest.py`（pytest 側）と scripts 側で共通化する。

---

_Reviewed: 2026-06-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
