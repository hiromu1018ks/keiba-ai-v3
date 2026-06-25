---
phase: 05-ev-backtest
reviewed: 2026-06-21T00:00:00Z
depth: deep
files_reviewed: 17
files_reviewed_list:
  - reports/05-backtest.json
  - reports/05-backtest.md
  - scripts/run_apply_schema.py
  - scripts/run_backtest.py
  - src/config/settings.py
  - src/db/backtest_load.py
  - src/db/connection.py
  - src/db/schema.py
  - src/ev/bl3_betting.py
  - src/ev/ev_rank.py
  - src/ev/metrics.py
  - src/ev/odds_snapshot.py
  - src/ev/purchase_simulator.py
  - src/ev/refund_accounting.py
  - src/ev/report.py
  - src/model/data.py
  - src/model/orchestrator.py
  - src/utils/group_split.py
findings:
  critical: 8
  warning: 12
  info: 7
  total: 27
status: issues_found
---

# Phase 5: Code Review Report (deep)

**Reviewed:** 2026-06-21
**Depth:** deep
**Files Reviewed:** 17 (src + scripts + reports)
**Status:** issues_found

## Summary

Phase 5 (EV & Backtest) の17ファイルを **deep** 深度で審査した。クロスファイル解析として `orchestrator.py → data.py → ev/* → metrics.py → report.py → run_backtest.py → backtest_load.py` のデータフローを追い、リーク防止聖域（§8.4/§13/§15.2/§15.5/§19.1/§11.2/§10.6）の健全性を検証した。

構造的リーク防止ブロック（`merge_asof(direction='backward')` / `category_map` BT-train-only refit / `race_id` disjoint guard / `split_3way` 完全時系列条件 / `backtest_id` scoped staging-swap / 固定 `odds_snapshot_policy` / 特払 semantics）は概ね堅牢に実装されている。これは Phase 5 の Core Value（リーク防止）がコード上で保たれていることを意味する。

しかし、**実データパス（`--synthetic` を外した運用実行）において複数の致命的バグが存在し、パイプラインが最後まで走らない**。これらは合成データ E2E smoke では発覚しない（合成 mock が欠損列や閾値を補っているため）点で特に危険。既存 standard レビューの critical 5 件（CR-01〜05）を全て検証し誤報でないことを確認した上で、deep 分析による新規 critical 3 件（CR-06〜08）と新規 warning/info を追加した。

特に深刻な新規発見:
- **CR-06**（新規）: `_run_main_model_backtest` が `selected_flag` を `pred_with_ev` の (race_key, umaban) でルックアップしているが、**HARAI merge で `race_key` 列が `race_key_label` に suffix リネームされる経路**が存在し、ラベル merge の `suffixes=("", "_label")` と重なると `race_key` の参照が曖昧になる silent 障害経路。
- **CR-07**（新規）: `_filter_label_by_period` の silent fallback（WR-05 既述）に加え、実データでは `load_labels` が `race_date` を返すが BT-4/BT-5 (test=2024) で `race_date` 列が Timestamp 型の際 `between` の境界で片側閉区間の境界日が test_start/test_end に含まれ、silent に1日分欠損または重複するリスク。
- **CR-08**（新規）: `orchestrator._apply_category_map` が `feature_df[code_col] = ...` で呼出元 frame を in-place 破壊し、`_assert_deterministic` が同一 `feature_df` で2回呼ぶと2回目が1回目の変換済み列に対して再変換を試みる（WR-07 既述の deep 拡張・`fit_category_map` の idempotency 非保証に起因）。

上位3件（最優先で修正すべき）:
1. **CR-05**: `run_backtest.py:1034` の `%.2%%` フォーマット文字列 — Python で解釈不可（実証済み）。実データパスで確実に pipeline 停止。最も単純で最も致命的。
2. **CR-01**: `odds_snapshot.py:134-138` の `race_key` 形式不整合 — JODDS 6要素 vs 他全テーブル5要素。実データでオッズ全件 NaN 化。
3. **CR-03**: `run_backtest.py:564` の `select_bets` が label merge 前に呼ばれる — 実データ pred_df に必須列が無く `KeyError`。

既存のリーク防止聖域（CLAUDE.md が規定する Core Value）自体はコード上で遵守されているため、これら実行時バグの修正後でも Core Value は維持される。ただし CR-01 の「実データでオッズが全件 NaN 化し回収率0.0の空 backtest が静かに生成される」経路は、§19.1 再現性聖域の観点で「都合の良い別時点への差し替え」と同等の silent failure であり、リーク防止聖域の**精神**（silent fallback 禁止）に抵触する。

---

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `fetch_jodds` の `race_key` 形式が他の全テーブルと不整合（実データでオッズが全件 NaN 化）

**File:** `src/ev/odds_snapshot.py:134-138`
**Issue:** `fetch_jodds` は `race_key = f"{year}-{monthday}-{jyocd}-{kaiji}-{nichiji}-{racenum}"`（6要素・`monthday` 挿入）を生成するが、他のすべてのモジュール（`src/model/data.py:make_race_key` / `scripts/run_backtest.py:_fetch_harai_race_level:1175-1179` / `fetch_market_data` の暗黙 race_key）は `race_key = f"{year}-{jyocd}-{kaiji}-{nichiji}-{racenum}"`（5要素・`monthday` 無し）を使用する。

結果として `select_odds_snapshot` が `merge_asof(by=['race_key','umaban'])` を呼んでも jodds 側の `race_key` と `pred_df` 側の `race_key` が **絶対に一致しない**。実データパスでは全馬の `fuku_odds_lower/upper` が NaN になり、`select_bets` の事前 filter (`fuku_odds_lower.notna()`) で候補0件となる。回収率 0.0 の空 backtest が静かに生成される（§19.1 再現性聖域違反・BACK-04 後知恵排除の観点で「都合の良い別時点への差し替え」と同等の silent failure）。

合成データ (`--synthetic`) は `_build_synthetic_jodds_df` が `feature_df_test["race_key"]` をそのまま copy するためこの不整合を踏まず、テストが通ってしまう点が特に悪質。deep 分析で cross-file 検証した結果、`make_race_key`（`src/model/data.py:182-202`）が正準形式であり、これと全て揃える必要がある。

**Fix:** `fetch_jodds` の race_key 構築を `make_race_key` と同一形式に統一する。

```python
# src/ev/odds_snapshot.py:134-138 を以下に置換
from src.model.data import make_race_key
# ...
df["race_key"] = make_race_key(df)
```

`make_race_key` は `(year, jyocd, kaiji, nichiji, racenum)` を期待するため、`fetch_jodds` の SELECT 列は `monthday` を含んだまま race_key 構築には使わない形（`monthday` は happyo_datetime 計算用に別途保持）にする。`_fetch_harai_race_level:1175-1179` も `make_race_key` 経由に切り替えることで単一 source of truth 化する。

### CR-02: 実データ `load_labels` 戻り値に `race_key` 列が無いのに merge で要求（`KeyError`）

**File:** `scripts/run_backtest.py:596-601`（主モデル）, `scripts/run_backtest.py:721-727`（BL-3）
**Issue:** `src/model/data.py:load_labels:308-330` の SELECT は `race_key` を取得せず、`year/jyocd/kaiji/nichiji/racenum/umaban/kettonum + label 列` のみを返す。一方 `_run_main_model_backtest` / `_run_bl3_backtest` は `label_df[["race_key", "umaban"] + label_cols]` で merge を試みる。

実データパスでは即座に `KeyError: "['race_key'] not in index"` で停止する。`_filter_label_by_period` は `race_date` 列を要求するが、`load_labels` は `race_date` を SELECT に含むため問題ない（race_key のみ欠落）。合成データは `_build_synthetic_label_df` が `feature_df_test[label_cols]` を copy し `label_cols` に `race_key` を含むためこの不整合を踏まない。

**Fix:** `run_backtest` 側で `label_df` に `make_race_key` で `race_key` を付与してから merge する。

```python
# scripts/run_backtest.py: load_labels 取得直後（_run_pipeline 内・readonly cursor block 直後）
from src.model.data import make_race_key
if "race_key" not in label_df.columns:
    label_df = label_df.copy()
    label_df["race_key"] = make_race_key(label_df)
```

### CR-03: `select_bets` が label 由来列を要求するが label merge 前に呼ばれる（`KeyError`）

**File:** `scripts/run_backtest.py:564`（`select_bets(pred_with_ev)` の呼び出し位置）
**Issue:** `select_bets` (`src/ev/purchase_simulator.py:86-91`) は `df["is_fukusho_sale_available"]` と `df["is_model_eligible"]` で事前 filter を行う。これらの列は label 由来（`load_labels` 戻り値）だが、`_run_main_model_backtest` は `select_bets(pred_with_ev)` を呼ぶのは **HARAI merge (581行) → label merge (596行) の前** の 564 行。

実データ `pred_df` は `PREDICTION_COLUMNS` のみ（`src/model/predict.py`・`is_model_eligible` / `is_fukusho_sale_available` は含まれない）。よって `select_bets` 内の `df["is_fukusho_sale_available"]` で `KeyError`。合成データは `_build_synthetic_pred_df` がこれらの列を含めて copy するためこの問題を踏まない。

deep 分析の cross-file 検証: `compute_ev_and_rank` は `p_fukusho_hit` と `fuku_odds_lower/upper` のみ消費し、`select_bets` が要求する label 系列には依存しない。よって merge 順序を入れ替えても EV 計算の正確性は保たれる。

**Fix:** label merge を `select_bets` の前に移動する。

```python
# 現在: compute_ev_and_rank → select_bets → HARAI merge → label merge
# 修正: HARAI merge → label merge → compute_ev_and_rank → select_bets

# 1. HARAI race-level merge (race_key 単位)
full_candidate_with_harai = pred_with_odds.merge(
    harai_race_df, on=["race_key"], how="left", validate="many_to_one"
)
# 2. label 馬単位 merge (race_key, umaban)
full_candidate_with_label = full_candidate_with_harai.merge(
    label_df, on=["race_key", "umaban"], how="left", suffixes=("", "_label")
)
# 3. compute_ev_and_rank
pred_with_ev = compute_ev_and_rank(full_candidate_with_label)
# 4. select_bets (is_fukusho_sale_available / is_model_eligible が既に存在)
selected = select_bets(pred_with_ev)
```

### CR-04: 実データ BL-3 `market_df` に `race_date` 列が無いのに `compute_backtest_metrics` が sort で使用（`KeyError`）

**File:** `scripts/run_backtest.py:1146-1151`（`_build_synthetic_market_df` は `race_date` を含むが `fetch_market_data` は含まない）, `scripts/run_backtest.py:749-750`（`compute_backtest_metrics` 呼び出し）
**Issue:** `fetch_market_data` (`src/model/baseline.py:500-520`) の SELECT は `o.year, o.jyocd, o.kaiji, o.nichiji, o.racenum, o.umaban, n.kettonum, o.fukuoddslow, o.fukuoddshigh, n.ninki` のみで `race_date` を含まない（deep で cross-file 検証済み）。

一方 `compute_backtest_metrics` (`src/ev/metrics.py:82-84`) は `df.sort_values(["race_date", "race_key", "umaban"])` を呼ぶ。BL-3 実データパスは `_run_bl3_backtest` が `market_df.copy()` して `full_candidate` を構築し、HARAI merge（race_key 単位で `race_date` 付かない）→ label merge を経て `compute_backtest_metrics` に渡す。`market_df` / HARAI / label のいずれの merge も `race_date` を付与しないため、BL-3 実データで `KeyError: 'race_date'`。

合成データは `_build_synthetic_market_df:1146-1151` が明示的に `["race_key", "umaban", "race_date", "is_fukusho_sale_available"]` を select するためこの不整合を踏まない。

**Fix:** `_run_bl3_backtest` で `race_date` を付与する。`label_df` 側に `race_date` があるため race_key 単位で持ってくる。

```python
# _run_bl3_backtest 内: market_df を label_df から race_date 補完
date_map = label_df.drop_duplicates("race_key")[["race_key", "race_date"]]
market_df = market_df.merge(date_map, on="race_key", how="left")
```

BL-3 は race_key + umaban 単位だが `race_date` は race 単位（全馬同値）のため race_key 単位の map で安全。`label_df` に `race_date` が無い場合は `make_race_key` + `fetch_race` で race_date を取得する経路を別途用意。

### CR-05: coverage ログの `%.2%%` フォーマット文字列が Python で解釈不可（`ValueError`）

**File:** `scripts/run_backtest.py:1034`
**Issue:** `logger.info("coverage %s/%s: horse=%.2%% race=%.2%% [%s]", ...)` は Python の `%`-format で `%.2%` を解釈しようとし `ValueError: unsupported format character '%' (0x25) at index N` で停止する（deep で実証済み・`python3 -c "print('%.2%%' % 0.5)"` で同一エラー再現）。

実データパスで coverage gate が走るたびに pipeline が落ちる。CR-01〜04 を全て修正しても本バグで停止するため、最優先修正対象。

**Fix:** 正しいフォーマット指定子 `%.2f%%` に修正（`%` リテラルは `%%`・小数2桁は `%.2f`）。

```python
logger.info(
    "coverage %s/%s: horse=%.2f%% race=%.2f%% [%s]",
    bt.name, policy,
    cov["horse_level_coverage"] * 100, cov["race_level_coverage"] * 100, cov["status"],
)
```

### CR-06: `_run_main_model_backtest` の HARAI merge `suffixes=("", "_label")` が label merge の suffix と重複し、`race_key` 列参照が曖昧になる silent 障害経路（deep 新規）

**File:** `scripts/run_backtest.py:581-606`
**Issue:** deep 分析で発見。`_run_main_model_backtest` は以下の順で merge する:
1. 581行: HARAI race-level merge — `on=["race_key"]`, `suffixes` 指定無し（pandas default `("_x","_y")`）。HARAI に `race_key` と `fuseirituflag2` 等がある。
2. 596行: label 馬単位 merge — `on=["race_key","umaban"]`, `suffixes=("", "_label")`。

label merge の `suffixes=("", "_label")` は、両フレームに同名列がある場合に左側を無修飾・右側を `_label` にする。左側（`full_candidate_with_harai`）に既に label 系列の同名列が存在する場合（例えば事前 join 済み snapshot 経由で伝播した `fukusho_hit_validated` 等）、右側 label の同名列が `fukusho_hit_validated_label` となり、後続の `_attach_accounting` → `determine_stake_payout` が `row.get("fukusho_hit_validated")` を呼ぶと左側（古い/誤）の値を参照する。

現在の実データパスでは `pred_df` は `PREDICTION_COLUMNS` のみ（label 系列を持たない）ため衝突しないが、将来 `pred_df` に label 列が混入（例: デバッグ用 join）した瞬間に silent に誤扱いになる。これは CLAUDE.md が禁止する silent leak 経路の潜在リスク。

加えて、`full_candidate` 構築で `selected_flag` を `(rk, um) in selected_keys` でルックアップする際、`selected` DataFrame が label merge 後でないと `is_fukusho_sale_available` が無く `select_bets` が落とす（CR-03 と同じ根因）。CR-03 修正で merge 順序を入れ替えた場合、上記 suffix 衝突リスクが顕在化する可能性がある。

**Fix:** merge の suffix を明示的に衝突回避し、かつ left frame に label 系列が残らないよう drop する。

```python
# 596-601 label merge を以下に置換
# label 側の列名に必ず _label suffix を付与（左側無修飾を許さない）
full_candidate_with_label = full_candidate_with_harai.merge(
    label_df[["race_key", "umaban"] + label_cols],
    on=["race_key", "umaban"],
    how="left",
    suffixes=("_left", "_label"),  # "" でなく "_left" を明示
)
# label 系列は _label 付き列のみを正とする・_left は破棄
for col in label_cols:
    left_col = f"{col}_left"
    label_col = f"{col}_label"
    if left_col in full_candidate_with_label.columns and label_col in full_candidate_with_label.columns:
        full_candidate_with_label[col] = full_candidate_with_label[label_col]
        full_candidate_with_label = full_candidate_with_label.drop(columns=[left_col, label_col])
```

### CR-07: `_filter_label_by_period` の `between` が Timestamp 型と文字列型混在で境界日を silent に欠損/重複（deep 新規・WR-05 拡張）

**File:** `scripts/run_backtest.py:1183-1193`
**Issue:** deep 分析で発見。`_filter_label_by_period` は `label_df["race_date"].between(start, end)` を呼ぶが、`start`/`end` は文字列（`periods["test"][0]` は `"2024-01-01"` 等・`_carve_calib_from_train_tail` の戻り値）。一方 `label_df["race_date"]` は `load_labels` が PostgreSQL の `date` 型を返すため pandas では `Timestamp` または `datetime.date`。

`Timestamp.between("2024-01-01", "2024-12-31")` は pandas が暗黙に文字列を Timestamp に変換するため通常は動くが、`datetime.date` オブジェクトが混入した場合は `TypeError: Cannot compare naive and aware` または silent に全件 NaN になるリスクがある。また、`between` は両側閉区間（`>=` かつ `<=`）のため、test_end='2024-12-31' の場合 12/31 開催レースが含まれる（これは仕様通り）が、train と test が 1/1 と 12/31 で接する BT-3/BT-4 で境界日が両方の窓に入るリスクがある（実際には `_carve_calib_from_train_tail` が `train_end = calib_start - 1day` で厳密に分離するため問題ないが、guard が無いと将来の改修で破綻する）。

より重大なのは WR-05 既述の silent fallback（`return out if len(out) > 0 else label_df`）。deep 分析で、この fallback は「test 期間に該当する label が0件の場合に全期間 label を返す」ため、race_date 型不正・snapshot の race_date 分布異常・BT窓設定ミスで test 期間が空になった場合に backtest が「全期間 label」で走る silent leak 経路になることを確認した。CLAUDE.md が禁止する silent fallback に該当する。

**Fix:** 空結果は `ValueError` で fail-loud にし、`between` 前に型を `pd.to_datetime` で正規化する。

```python
def _filter_label_by_period(label_df, start, end):
    if "race_date" not in label_df.columns:
        return label_df
    # 型正規化（文字列・date・Timestamp 混在を統一）
    label_df = label_df.copy()
    label_df["race_date"] = pd.to_datetime(label_df["race_date"], errors="coerce")
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    mask = label_df["race_date"].between(start_ts, end_ts)
    out = label_df.loc[mask].copy()
    if len(out) == 0:
        raise ValueError(
            f"_filter_label_by_period: test 期間 ({start}..{end}) に該当する label 行が0件 "
            "(silent フォールバック禁止・race_date 型または BT窓区間を確認・§19.1 聖域)"
        )
    return out
```

### CR-08: `orchestrator._apply_category_map` の in-place mutation が `_assert_deterministic` の 2 回呼出で破壊的（deep 新規・WR-07 拡張）

**File:** `src/model/orchestrator.py:105-161`, `src/model/orchestrator.py:763-793`
**Issue:** deep 分析で発見。`_apply_category_map` は `category_map is None` の場合のみ `feature_df` をそのまま返すが、`category_map` 指定時は `feature_df[code_col] = apply_category_map(...)` で呼び出し元の DataFrame を in-place 更新する（`orchestrator.py:159`）。

`train_and_predict` は `feature_df = _apply_category_map(feature_df, category_map)` で受けるが（line 355）、これは単なる再代入であり元の DataFrame オブジェクトは同じ。`_assert_deterministic`（line 763-793）は同一 `feature_df` で2回 `train_and_predict` を呼ぶ。1回目の `_apply_category_map` が `feature_df[code_col]` を書き換えると、2回目は既に変換済みの `_code` 列（int 化済み）に対して再変換を試みる。

`apply_category_map` は内部で `series.astype(str)` を行うため、1回目: `"J001" → 0`（int）、2回目: `0 → "0"` → `__UNSEEN__` code（`0` は frozen map に無いため）。結果として 2 回の `train_and_predict` の `p_fukusho_hit` が bit-identical にならず、`_assert_deterministic` が `RuntimeError` を raise する（SC#4 違反・§19.1 構造的ブロック違反）。

実データの `--check-reproduce` 実行で発覚する。合成データは `--check-reproduce` が `_prepare_feature_df` を呼び `FileNotFoundError` になるため（`test_check_reproduce_smoke` コメント参照）この経路を踏まない。

**Fix:** `_apply_category_map` の冒頭で `feature_df = feature_df.copy()` する。

```python
def _apply_category_map(feature_df, category_map):
    if category_map is None:
        return feature_df  # no-op のみ copy しない（A5 互換・呼出側で copy 済み前提）
    feature_df = feature_df.copy()  # 呼出元 frame 保護（CR-08）
    from src.utils.category_map import apply_category_map
    # ...（既存ロジック）
    return feature_df
```

## Warnings

### WR-01: `_run_main_model_backtest` / `_run_bl3_backtest` で `etl_pool.connection().__enter__().__exit__()` の手動コンテキスト管理が例外安全でない

**File:** `scripts/run_backtest.py:1046-1070`（主モデル）, `scripts/run_backtest.py:1080-1101`（BL-3）
**Issue:** `write_cur_ctx = etl_pool.connection().__enter__().cursor().__enter__()` のように `with` 文を使わず `__enter__/__exit__` を手動呼び出しし、`finally` で `__exit__(None, None, None)` する。`finally` ブロック内で `cursor().__exit__()` が成功しても `etl_pool.connection().__exit__()` が別例外を投げると `except Exception: pass` で握りつぶされる。さらに `etl_pool.connection()` を2回呼んでおり（cursor 用と exit 用）、別 connection オブジェクトになっているため cursor の commit/rollback が exit 側 connection に伝播しない可能性がある。これは backtest 書込のトランザクション一貫性を損なう（§19.1 再現性聖域違反の潜在リスク）。

**Fix:** `with etl_pool.connection() as conn: with conn.cursor() as cur: ...` の標準パターンを使う。

```python
if etl_pool is not None:
    with etl_pool.connection() as conn:
        with conn.cursor() as cur:
            row = _run_main_model_backtest(
                bt, policy, mt, ...,
                write_cur=cur,
                no_write_db=False,
            )
else:
    row = _run_main_model_backtest(..., write_cur=None, no_write_db=True)
```

### WR-02: `_assert_jodds_coverage_horse_level` の `no_bet_reasons` set にコード上現れない sentinel 値が含まれる

**File:** `scripts/run_backtest.py:831`
**Issue:** `no_bet_reasons = {"no_bet", "no_bet_empty", "special_value", "fukusyoflag_not_normal_sale"}` と定義しているが、`select_odds_snapshot` (`src/ev/odds_snapshot.py:288-301`) の戻り値 `odds_missing_reason` は `'no_bet_empty' / 'no_bet' / None` の3値のみで `'special_value'` も `'fukusyoflag_not_normal_sale'` も決して生成されない（deep cross-file 検証済み）。

`fukusyoflag` 異常値は `_NO_BET_FUKUSYOFLAGS = {'0','1','3'}` に該当すると `'no_bet'` に分類される。coverage 計算は `'no_bet'` を含むため実害は無いが、docstring と実装の乖離が将来のデバッグを誘発する。

**Fix:** `no_bet_reasons` set を実装と一致させる（`'special_value'` と `'fukusyoflag_not_normal_sale'` を削除、または `odds_snapshot.py` 側で生成するよう拡張）。

### WR-03: `metrics.compute_backtest_metrics` の `profit_loss` 集計式と non-selected ゼロ化の整合性で `refund_flag` / `refund_amount` が未ゼロ化（監査性低下）

**File:** `src/ev/metrics.py:78-79`, `scripts/run_backtest.py:499-514`
**Issue:** `_zero_out_non_selected_accounting` が `non_selected_mask` の行の `stake` / `refund` を 0 化するが、`zero_cols` は `["stake", "effective_stake", "payout", "refund", "profit"]` のみで `refund_flag` / `refund_amount` / `payout_amount` を含まない。これにより非選択行の `refund_flag=True` / `refund_amount=100` / `payout_amount=200` が残り、`backtest.fukusho_backtest` テーブルに永続化される非選択行が `stake=0, effective_stake=0, refund=0, refund_flag=True, refund_amount=100` という不整合状態になる（CHECK 制約は無いため DB は受け入れるが監査性を損なう・MEDIUM-04 監査性聖域違反の潜在リスク）。

metrics は selected_flag=True 行のみで計算されるため直接の矛盾は出ないが、report の `refund_count` 集計で非選択行の refund_flag=True が混入する経路が存在する。

**Fix:** `_zero_out_non_selected_accounting` の `zero_cols` に数値系会計列を全て追加し、bool 系は別途 False 化する。

```python
zero_cols = ["stake", "effective_stake", "payout", "refund", "profit",
             "refund_amount", "payout_amount"]
zero_cols = [c for c in zero_cols if c in out.columns]
out.loc[non_selected_mask, zero_cols] = 0
out.loc[non_selected_mask, "refund_flag"] = False
```

### WR-04: `_carve_calib_from_train_tail` の calib_months=6 固定で短い train 窓の BT で train が空になる silent リスク

**File:** `scripts/run_backtest.py:174-216`
**Issue:** BT-4 train_start='2021-01-01' / train_end='2023-12-31' で calib_months=6 の場合、carve 後 train=('2021-01-01','2023-06-30') / calib=('2023-07-01','2023-12-31')。これは正常。しかし BT-5 train_start='2019-01-01' / train_end='2023-12-31' でも同一 calib 区間となる。

より重大なのは `_DEFAULT_CALIB_MONTHS = 6` が定数で、短い train 窓（将来 BT 追加で train < 6ヶ月）の場合に `train_end_carved` が `train_start` より前になる silent リスク。`split_3way` の完全時系列条件 guard が catch するが、`train_max < calib_min` でなく「train が空」で `ValueError` になるためエラーメッセージが分かりにくい。

deep 分析で、現状の BT-1..5 では全て train 期間が 3 年以上あるため問題ないが、将来的な BT 追加で発覚する潜在リスク。

**Fix:** calib_months が train 期間より長い場合の早期検証を追加。

```python
train_start_ts = pd.Timestamp(bt.train_start)
train_duration_months = (bt_train_end.year - train_start_ts.year) * 12 + (
    bt_train_end.month - train_start_ts.month
)
if calib_months >= train_duration_months:
    raise ValueError(
        f"_carve_calib_from_train_tail: calib_months={calib_months} >= "
        f"train duration ({train_duration_months} months) for {bt.name}"
    )
```

### WR-05: `_filter_label_by_period` が空結果の場合に未 filter の `label_df` を返す（silent フォールバック・§19.1 聖域リスク・CR-07 で fail-loud 化を推奨）

**File:** `scripts/run_backtest.py:1183-1193`
**Issue:** `out = label_df.loc[mask].copy(); return out if len(out) > 0 else label_df` と、filter 結果が空の場合に未 filter の全体を返す。これは BT窓 test 期間外のラベルまで backtest 対象になる silent leak 経路。CR-07 で詳細化済み。

**Fix:** CR-07 を参照（fail-loud 化）。

### WR-06: `refund_accounting.determine_stake_payout` の特払 (tokubarai) 処理が `payfukusyopay1` を無条件参照し slot1 馬番不一致で誤払戻リスク

**File:** `src/ev/refund_accounting.py:151-157`
**Issue:** 特払時 `payout = int(str(row.get("payfukusyopay1", "0")).strip())` は `payfukusyoumaban1` が何であっても（例えば '00' でなく '05' など）`payfukusyopay1` を選択馬の払戻として計上する。

特払の JRA ルールでは「複勝特別払戻」は発売条件により対象馬のオッズに拠らず一律の特払金を支払うが、コードは slot1 を無条件参照する。もし `payfukusyoumaban1='05'` で選択馬が `umaban=3` の場合、誤って slot1（=05番の払戻）を 3番馬の払戻として計上する。特払時は `PayFukusyoUmaban1..5` が '00' になる前提だが assert が無い。deep で `test_refund_tokubarai_harai_fixture` を確認したが、同テストは全 slot '00' の fixture のみ検証し、'05' 混入ケースをカバーしていない。

**Fix:** 特払時は `payfukusyoumaban1..5` 全てが '00' であることを assert する、または `_lookup_payfukusyo_pay` の通常 path と同様に slot 照合を経由させる。

```python
if tokubarai:
    # 特払: 全 slot の umaban が '00' であることを検証
    for slot in range(1, 6):
        uv = row.get(f"payfukusyoumaban{slot}")
        if uv is not None and str(uv).strip() not in ("", "00"):
            # 通常の中り馬番が存在するなら特払ではなく通常扱い
            payout = _lookup_payfukusyo_pay(row)
            break
    else:
        try:
            payout = int(str(row.get("payfukusyopay1", "0")).strip())
        except (ValueError, TypeError):
            payout = 0
```

### WR-07: `orchestrator._apply_category_map` が `feature_df` を copy せず in-place で `_code` 列を上書き（CR-08 で詳細化）

**File:** `src/model/orchestrator.py:105-161`
**Issue:** `_apply_category_map` は `category_map is None` の場合のみ `feature_df` をそのまま返すが、`category_map` 指定時は `feature_df[code_col] = apply_category_map(...)` で呼び出し元の DataFrame を in-place 更新する。CR-08 で詳細化済み。

**Fix:** CR-08 を参照（copy 追加）。

### WR-08: `odds_snapshot.select_odds_snapshot` の `datakubun` filter が `'1'` 文字列比較のみで NaN を考慮しない

**File:** `src/ev/odds_snapshot.py:223-224`
**Issue:** `jodds = jodds[jodds["datakubun"].astype(str) == "1"].copy()` は `datakubun` が NaN の行（`float('nan')` → `'nan'` 文字列）を除外する。`fetch_jodds` の JOIN で head 側の `datakubun` が NULL の場合（JOIN ミスマッチ）、`astype(str)` で `'nan'` となり filter で除外される。これは結果的に安全側に倒れるが、JOIN ミスマッチ自体は静かに発生し得る（race_key 形式不整合 CR-01 がまさにこの経路）。

さらに `datakubun` が `int` で取得された場合（`1` 数値）も `astype(str) == "1"` で一致するため問題ないが、psycopg3 が varchar を `str` で返すかはカラム定義に依存する。将来のスキーマ変更で破綻するリスク。

**Fix:** `pd.NA` / NaN を明示的に除外してから比較する。

```python
if "datakubun" in jodds.columns:
    dk = jodds["datakubun"]
    jodds = jodds[dk.notna() & (dk.astype(str).str.strip() == "1")].copy()
```

### WR-09: `metrics.compute_backtest_metrics` の `hit_count` が `fukusho_hit_validated.sum()` で返還/中止行を含む集計になり得る（deep 新規）

**File:** `src/ev/metrics.py:97`
**Issue:** deep 分析で発見。`hit_count = int(df["fukusho_hit_validated"].sum())` は `selected_flag=True` 行のみ（`run_backtest.py:617-619` で filter 済み）で呼ばれるが、返還系（`is_scratch_cancel` 等）の行は `fukusho_hit_validated=0` であり effective_stake=0 で `effective_bet_count` からは除外される。しかし `hit_count` の分母である `effective_bet_count` と分子 `hit_count` の対応が、「返還馬の `fukusho_hit_validated=0` が hit_count を下げる」状態になる。

これは仕様上正しい（返馬は不的中扱いで hit_count に寄与しない）が、`hit_rate = hit_count / effective_bet`（`run_backtest.py:644`）の分母が返還を含まない一方で分子も返還を含まないため、返還馬が多いレースで hit_rate が見かけ上高くなる（返還馬分母除外効果）リスクがある。report の hit_rate を見る利用者がこの仕様を理解していないと誤認する。

**Fix:** docstring で明記、または `hit_rate` 計算時に `fukusho_hit_validated` の定義を明確化する。

```python
# metrics.py docstring に追記
"""hit_count は selected_flag=True かつ fukusho_hit_validated=1 の件数。
返還系（effective_stake=0）の行は selected_flag=True でも hit_count に含まれない
（fukusho_hit_validated=0 のため）。hit_rate = hit_count / effective_bet は
返還を分母から除外した比率であり・返還馬が多いレースで見かけ上高くなる。"""
```

### WR-10: `ev_rank._rank` が行単位 `df.apply(_rank, axis=1)` で大規模予測でパフォーマンス低下（deep 確認）

**File:** `src/ev/ev_rank.py:112`
**Issue:** `compute_ev_and_rank` は `EV_lower` / `EV_upper` をベクトル化するが rank 判定のみ `apply(axis=1)`。予測行数が多い（数十万）場合に顕著。性能は v1 scope 外だが、Phase 6 のキャリブ指標再設計で大規模 backtest を回す際に顕在化する可能性あり（user memory: `calib-metric-phase6-rework-inputs`）。

**Fix:** 将来 `np.select` でベクトル化する。現状は機能的正確性優先で許容。

### WR-11: `select_odds_snapshot` の `assert len(result_df) == n_expected` が `python -O` で削除される（HIGH #3 違反・deep 新規）

**File:** `src/ev/odds_snapshot.py:323-325`
**Issue:** deep 分析で発見。`select_odds_snapshot` の末尾に `assert len(result_df) == n_expected, ...` がある。これは行数不変条件の guard だが、CLAUDE.md / HIGH #3 / `group_split.py` の規約（リーク防止 guard は `assert` でなく `raise ValueError`・`python -O` で削除されない）に違反する。

`merge_asof` が稀に cutoff_sorted の重複キーで行数を変えることがあり、その場合 `python -O` 実行で行数不変条件が silent に破れる（HIGH-1 馬単位 odds 保証の silent 回帰リスク）。

**Fix:** `assert` を `raise RuntimeError` に変更。

```python
if len(result_df) != n_expected:
    raise RuntimeError(
        f"select_odds_snapshot 行数不変条件違反: expected {n_expected}, got {len(result_df)} "
        "(merge_asof の by= グループ内重複の可能性・HIGH-1 馬単位 odds 保証違反)"
    )
```

### WR-12: `_attach_accounting` が `df.apply(determine_stake_payout, axis=1, result_type="expand")` で行単位処理（deep 確認・性能）

**File:** `scripts/run_backtest.py:472-496`, `scripts/run_backtest.py:729-731`
**Issue:** `_attach_accounting` と BL-3 インライン会計付与が `apply(axis=1)` で行単位に `determine_stake_payout` を呼ぶ。大規模 backtest（数万行 × 25候補）で顕著な性能低下。性能は v1 scope 外だが、Phase 6 で大規模 backtest を回す際に顕在化する可能性あり。

**Fix:** 将来ベクトル化する。現状は機能的正確性優先で許容。

## Info

### IN-01: `report._format_comparison_table_md` の `int(v)` 失敗時 `'0'` は NaN を誤表示リスク

**File:** `src/ev/report.py:127-131`
**Issue:** `int(v)` が NaN に対して `ValueError` → `'0'` を返す。NaN は本来「値が無い」ので `'0'` 表示は誤解（0件と同義に見える）。report の数値は `compute_backtest_metrics` が常に int を返すため実害は無いが・`None` を返す future 拡張で破綻する。

**Fix:** `'nan'` または `'-'` を返す方が安全。

### IN-02: `backtest_load._df_to_backtest_tuples` が `df.iterrows()` で行単位ループ（性能）

**File:** `src/db/backtest_load.py:206-259`
**Issue:** `prediction_load.py` と同一パターンだが、backtest は25候補×数万行/候補になる可能性があり、`iterrows()` は pandas で最も遅い iter 手法。性能は v1 scope 外（本 review では指摘のみ）。

**Fix:** 将来 vectorize する。現状は機能的正確性優先で許容。

### IN-03: `run_apply_schema._build_rendered_sql` が `sql.SQL(sql_text)` を使い PostgreSQL の `$$` ドル引用符を含む（deep 確認・安全）

**File:** `scripts/run_apply_schema.py:58-64`
**Issue:** `schema_module.CREATE_ROLES_SQL` 内に `DO $$ ... $$` プラック（PostgreSQL ドル引用符）が含まれる。psycopg3 の `sql.SQL().format()` は `{...}` のみを placeholder として解釈するため `$$` は無害。deep で確認した結果、現状は安全に処理される。

**Fix:** 特に不要。psycopg3 の `sql.SQL` は `{...}` のみ placeholder 扱いなので `$$` は安全。

### IN-04: `group_split.BT_WINDOWS` の BT-4/BT-5 が test_start=2024 で同一期間（deep 確認）

**File:** `src/utils/group_split.py:219-235`
**Issue:** BT-4 (rolling 3年 train) と BT-5 (rolling 5年 train) が共に test='2024-01-01..2024-12-31'。これは仕様（CLAUDE.md §15.5・D-03 + planner A2 で test 年を 2024 に揃える）通りだが、同一 test 期間で train 期間のみ異なる比較となる。report を見る利用者が BT-4 と BT-5 の差が train 期間差のみであることを理解していないと誤認する。docstring で明記済みだが report にも注記があると親切。

**Fix:** 特に不要（仕様通り）。report の注記に「BT-4/BT-5 は同一 test 期間で train 期間のみ異なる rolling 比較」と追記してもよい。

### IN-05: `orchestrator._ManualCatBoostCalibrated` が `calibrated_classifiers_ = [self]` で artifact.py の参照を模倣（deep 確認）

**File:** `src/model/orchestrator.py:655-674`
**Issue:** `_ManualCatBoostCalibrated.__init__` が `self.calibrated_classifiers_ = [self]` を設定し、`artifact.py` が CalibratedClassifierCV の属性を参照するのを模倣している。これは循環参照（`self.calibrated_classifiers_[0] == self`）になり、pickle 化で問題を起こす可能性がある。現状の `artifact.save_native_artifact` が `[0]` のみ参照するため動くが、将来の sklearn API 変更で破綻するリスク。

**Fix:** 循環参照を避けるため `[object()]` 等のダミーにするか、artifact.py 側で `_ManualCatBoostCalibrated` を特別扱いする。現状は動作するため許容。

### IN-06: `refund_accounting._lookup_payfukusyo_pay` が slot 1-5 を順次走査し最初の一致を返す（deep 確認）

**File:** `src/ev/refund_accounting.py:38-75`
**Issue:** 同着で slot 2-5 に同じ umaban が入った場合、最初の slot の pay を返す。JRA の同着拡張払戻では各 slot の pay が異なる場合があり（例: 3着同着で slot3=150円 / slot4=200円）、本来は選択馬が該当する全 slot の合計または最大を返すべきだが、コードは最初の一致のみ。deep で `test_refund_deadheat` を確認したが、同テストは単一 slot のみ検証し、複数 slot 同一馬番のケースをカバーしていない。

**Fix:** JRA 同着拡張払戻の公式ルールを確認し、必要なら合計または最大を返すよう修正。現状の実DB観測値では同着拡張は稀なため許容。

### IN-07: `data.make_X_y` の categorical 復元リスト `_categorical_feature_cols` が trainer と重複定義（deep 確認・DRY 違反）

**File:** `src/model/data.py:434-445`
**Issue:** `make_X_y` 内の `_categorical_feature_cols` set が `trainer.HIGH_CARD_CODE_COLS` + low-card categorical と重複定義されている。trainer 側で列追加があった場合、data.py 側も更新が必要で、更新漏れで silent に str→numeric 復元がスキップされるリスクがある。

**Fix:** `_categorical_feature_cols` を trainer 側から import する、または共通定数モジュールに切り出す。現状は動作するため許容。

---

_Reviewed: 2026-06-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
