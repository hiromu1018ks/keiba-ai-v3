---
phase: 05-ev-backtest
reviewed: 2026-06-21T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - scripts/run_apply_schema.py
  - scripts/run_backtest.py
  - src/config/settings.py
  - src/db/backtest_load.py
  - src/db/connection.py
  - src/db/schema.py
  - src/ev/__init__.py
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
  critical: 5
  warning: 8
  info: 4
  total: 17
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-21
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 5 (EV & Backtest) の 17 ファイルを標準深度で審査した。リーク防止の構造的ブロック（`merge_asof(direction='backward')` / `category_map` BT-train-only refit / `race_id` disjoint guard / `backtest_id` scoped staging-swap）は概ね堅牢に実装されている。しかし、**実データパス（`--synthetic` を外した運用実行）において複数の致命的バグが存在し、パイプラインが最後まで走らない**。これらは合成データ E2E smoke では発覚しない（合成 mock が欠損列を補っているため）点で特に危険。

主要懸念:
1. `race_key` 形式が `fetch_jodds` (6要素) と label/pred/harai/market (5要素) で不整合 → 実データでオッズ merge が全件 NaN 化
2. `load_labels` 戻り値に `race_key` 列が無いのに `label_df[["race_key","umaban"]]` で merge → `KeyError`
3. `select_bets` が label 由来列 (`is_model_eligible`/`is_fukusho_sale_available`) を要求するが label merge 前に呼ばれる → `KeyError`
4. `fetch_market_data` 戻り値に `race_date` 列が無いのに `compute_backtest_metrics` が sort に使用 → `KeyError`
5. coverage ログの `%.2%%` フォーマット文字列が Python で解釈不可 → `ValueError` で pipeline 停止

CLAUDE.md のリーク防止聖域（`odds_snapshot_policy` 固定 / race_id grouping / `effective_stake` honest 会計）自体はコード上で遵守されているため、これら実行時バグの修正後でも Core Value は維持される。

## Critical Issues

### CR-01: `fetch_jodds` の `race_key` 形式が他の全テーブルと不整合（実データでオッズが全件 NaN 化）

**File:** `src/ev/odds_snapshot.py:134-138`
**Issue:** `fetch_jodds` は `race_key = f"{year}-{monthday}-{jyocd}-{kaiji}-{nichiji}-{racenum}"`（6要素・`monthday` 挿入）を生成するが、他のすべてのモジュール（`src/model/data.py:make_race_key` / `scripts/run_backtest.py:_fetch_harai_race_level:1175-1179` / `fetch_market_data` の暗黙 race_key）は `race_key = f"{year}-{jyocd}-{kaiji}-{nichiji}-{racenum}"`（5要素・`monthday` 無し）を使用する。

結果として `select_odds_snapshot` が `merge_asof(by=['race_key','umaban'])` を呼んでも jodds 側の `race_key` と `pred_df` 側の `race_key` が **絶対に一致しない**。実データパスでは全馬の `fuku_odds_lower/upper` が NaN になり、`select_bets` の事前 filter (`fuku_odds_lower.notna()`) で候補0件となる。回収率 0.0 の空 backtest が静かに生成される（§19.1 再現性聖域違反・BACK-04 後知恵排除の観点で「都合の良い別時点への差し替え」と同等の silent failure）。

合成データ (`--synthetic`) は `_build_synthetic_jodds_df` が `feature_df_test["race_key"]` をそのまま copy するためこの不整合を踏まず、テストが通ってしまう点が特に悪質。

**Fix:** `fetch_jodds` の race_key 構築を `make_race_key` と同一形式に統一する。

```python
# src/ev/odds_snapshot.py:134-138 を以下に置換
from src.model.data import make_race_key
# ...
df["race_key"] = make_race_key(df)
```

`make_race_key` は `(year, jyocd, kaiji, nichiji, racenum)` を期待するため、`fetch_jodds` の SELECT で `year/jyocd/kaiji/nichiji/racenum` が適切な方で揃えること（現在 SELECT に `monthday` 含む・race_key には `monthday` を含めない）。

### CR-02: 実データ `load_labels` 戻り値に `race_key` 列が無いのに merge で要求（`KeyError`）

**File:** `scripts/run_backtest.py:596-601`（主モデル）, `scripts/run_backtest.py:721-727`（BL-3）
**Issue:** `src/model/data.py:load_labels` の SELECT (`src/model/data.py:308-330`) は `race_key` を取得せず、`year/jyocd/kaiji/nichiji/racenum/umaban/kettonum + label 列` のみを返す。一方 `_run_main_model_backtest` / `_run_bl3_backtest` は `label_df[["race_key", "umaban"] + label_cols]` で merge を試みる。

実データパスでは即座に `KeyError: "['race_key'] not in index"` で停止する。`_filter_label_by_period` も同様に `race_date` 列を要求するが、`load_labels` は `race_date` を SELECT に含むため問題ない（race_key のみ欠落）。

合成データは `_build_synthetic_label_df` が `feature_df_test[label_cols]` を copy し `label_cols` に `race_key` を含むためこの不整合を踏まない。

**Fix:** `run_backtest` 側で `label_df` に `make_race_key` で `race_key` を付与してから merge する。

```python
# scripts/run_backtest.py: _filter_label_by_period の直後あたり、または取得直後
from src.model.data import make_race_key
if "race_key" not in label_df.columns:
    label_df = label_df.copy()
    label_df["race_key"] = make_race_key(label_df)
```

または `load_labels` の SELECT に `race_key` を計算列として追加する（`make_race_key` は純粋関数なので run 側で付与する方がクリーン）。

### CR-03: `select_bets` が label 由来列を要求するが label merge 前に呼ばれる（`KeyError`）

**File:** `scripts/run_backtest.py:564`（`select_bets(pred_with_ev)` の呼び出し位置）
**Issue:** `select_bets` (`src/ev/purchase_simulator.py:86-91`) は `df["is_fukusho_sale_available"]` と `df["is_model_eligible"]` で事前 filter を行う。これらの列は label 由来（`load_labels` 戻り値）だが、`_run_main_model_backtest` は `select_bets(pred_with_ev)` を呼ぶのは **HARAI merge (579行) → label merge (596行) の前** の 564 行。

実データ `pred_df` は `PREDICTION_COLUMNS` のみ（`src/model/predict.py:62-81`・`is_model_eligible` / `is_fukusho_sale_available` / `race_start_datetime` は含まれない）。よって `select_bets` 内の `df["is_fukusho_sale_available"]` で `KeyError`。

合成データは `_build_synthetic_pred_df` が `feature_df_test` から `is_fukusho_sale_available` / `is_model_eligible` を含めて copy するためこの問題を踏まない。

**Fix:** label merge を `select_bets` の前に移動する。`compute_ev_and_rank` は `p_fukusho_hit` と `fuku_odds_lower/upper` のみ消費するので、HARAI merge → label merge → compute_ev_and_rank → select_bets の順に並び替える。

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
# 3. compute_ev_and_rank (p_fukusho_hit × fuku_odds_lower/upper)
pred_with_ev = compute_ev_and_rank(full_candidate_with_label)
# 4. select_bets (is_fukusho_sale_available / is_model_eligible が既に存在)
selected = select_bets(pred_with_ev)
```

### CR-04: 実データ BL-3 `market_df` に `race_date` 列が無いのに `compute_backtest_metrics` が sort で使用（`KeyError`）

**File:** `scripts/run_backtest.py:1146-1151`（`_build_synthetic_market_df` は `race_date` を含むが `fetch_market_data` は含まない）, `scripts/run_backtest.py:749-750`（`compute_backtest_metrics` 呼び出し）
**Issue:** `fetch_market_data` (`src/model/baseline.py:500-520`) の SELECT は `o.year, o.jyocd, o.kaiji, o.nichiji, o.racenum, o.umaban, n.kettonum, o.fukuoddslow, o.fukuoddshigh, n.ninki` のみで `race_date` を含まない。

一方 `compute_backtest_metrics` (`src/ev/metrics.py:82-84`) は `df.sort_values(["race_date", "race_key", "umaban"])` を呼ぶ。BL-3 実データパスは `_run_bl3_backtest` が `market_df.copy()` して `full_candidate` を構築し、HARAI merge（race_key 単位で `race_date` 付かない）→ label merge を経て `compute_backtest_metrics` に渡す。`market_df` / HARAI / label のいずれの merge も `race_date` を付与しないため、BL-3 実データで `KeyError: 'race_date'`。

合成データは `_build_synthetic_market_df` が明示的に `["race_key", "umaban", "race_date", "is_fukusho_sale_available"]` を select するためこの不整合を踏まない。

**Fix:** `_run_bl3_backtest` で `race_date` を付与する。market_df の PK から `make_race_key` で race_key を構築した上で、`label_df` または `harai_race_df` から `race_date` を持ってくる。最も単純には `market_df` に `race_date` を JOIN する（label_df 側に `race_date` があるため race_key+umaban で持ってくる）。

```python
# _run_bl3_backtest 内: market_df を label_df から race_date 補完
date_map = label_df.drop_duplicates("race_key")[["race_key", "race_date"]]
market_df = market_df.merge(date_map, on="race_key", how="left")
```

### CR-05: coverage ログの `%.2%%` フォーマット文字列が Python で解釈不可（`ValueError`）

**File:** `scripts/run_backtest.py:1034`
**Issue:** `logger.info("coverage %s/%s: horse=%.2%% race=%.2%% [%s]", ...)` は Python の `%`-format で `%.2%` を解釈しようとし `ValueError: unsupported format character '%' (0x25) at index N` で停止する（実証済み・`python3 -c "print('%.2%%' % 0.5)"` で同エラー再現）。

実データパスで coverage gate が走るたびに pipeline が落ちる。CR-01〜04 を全て修正しても本バグで停止する。

**Fix:** 正しいフォーマット指定子 `%.2f%%` に修正（`%` リテラルは `%%`・小数2桁は `%.2f`）。

```python
logger.info(
    "coverage %s/%s: horse=%.2f%% race=%.2f%% [%s]",
    bt.name, policy,
    cov["horse_level_coverage"] * 100, cov["race_level_coverage"] * 100, cov["status"],
)
```

## Warnings

### WR-01: `_run_main_model_backtest` / `_run_bl3_backtest` で `etl_pool.connection().__enter__().__exit__()` の手動コンテキスト管理が例外安全でない

**File:** `scripts/run_backtest.py:1046-1070`（主モデル）, `scripts/run_backtest.py:1080-1101`（BL-3）
**Issue:** `write_cur_ctx = etl_pool.connection().__enter__().cursor().__enter__()` のように `with` 文を使わず `__enter__/__exit__` を手動呼び出しし、`finally` で `__exit__(None, None, None)` する。`finally` ブロック内で `cursor().__exit__()` が成功しても `etl_pool.connection().__exit__()` が別例外を投げると `except Exception: pass` で握りつぶされる。さらに backtest_id ごとに別 connection を取得しているが、`load_backtest` がトランザクション内で advisory lock を取るため・並行 backtest の順序保証が効かない（直列化は advisory lock で担保されるが connection pool の misuse リスク）。

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

### WR-02: `_assert_jodds_coverage_horse_level` の `no_bet_reasons` set にコード上現れない `'fukusyoflag_not_normal_sale'` が含まれる（デッド値・coverage 過小リスク低・誤解誘発）

**File:** `scripts/run_backtest.py:831`
**Issue:** `no_bet_reasons = {"no_bet", "no_bet_empty", "special_value", "fukusyoflag_not_normal_sale"}` と定義しているが、`select_odds_snapshot` (`src/ev/odds_snapshot.py:288-301`) の戻り値 `odds_missing_reason` は `'no_bet_empty' / 'no_bet' / None` の3値のみで `'special_value'` も `'fukusyoflag_not_normal_sale'` も決して生成されない。

`fukusyoflag` 異常値は `_NO_BET_FUKUSYOFLAGS = {'0','1','3'}` に該当すると `'no_bet'` に分類される（`odds_snapshot.py:294-299`）。docstring は `'special_value'` sentinel を言及しているが実装は存在しない。coverage 計算は `'no_bet'` を含むため実害は無いが、docstring と実装の乖離が将来のデバッグを誘発する。

**Fix:** `_assert_jodds_coverage_horse_level` の docstring / `no_bet_reasons` set を実装と一致させる（`'special_value'` と `'fukusyoflag_not_normal_sale'` を削除、または `odds_snapshot.py` 側でこれら sentinel を生成するよう拡張）。

### WR-03: `metrics.compute_backtest_metrics` の `profit_loss` 集計式と `sum(row.profit)` 不変量が refund=100 の返還系で破れる場合がある

**File:** `src/ev/metrics.py:78-79`
**Issue:** `profit_loss = int(total_payout + total_refund - total_stake)` と集計式で定義している。一方 `refund_accounting.determine_stake_payout` の返還系（取消/除外/不成立/レース中止）は `{"stake": 100, "refund": 100, "payout": 0, "profit": 0, "effective_stake": 0}` を返す。

行 profit = `payout + refund - stake = 0 + 100 - 100 = 0` で正しい。集計式 `sum(payout) + sum(refund) - sum(stake) = 0 + 100 - 100 = 0` で一致する。**ただし** `_zero_out_non_selected_accounting` (`scripts/run_backtest.py:499-514`) が `non_selected_mask` の行の `stake` / `refund` を 0 化する。non-selected 行の `profit` も 0 化されるので不変量は保たれるが、`compute_backtest_metrics` は selected_flag=True の行のみで呼ばれるため影響しない。

潜在的リスク: `_zero_out_non_selected_accounting` が `stake` を 0 化するが `effective_stake` も 0 化するため recovery_rate の分母整合は保たれる。ただし `refund_flag` / `refund_amount` の非選択行ゼロ化は明示的に行われていない（`zero_cols` に `refund` を含むが `refund_flag` / `refund_amount` を含まない）。これにより非選択行の `refund_flag=True` / `refund_amount=100` が残り、report の `refund_count` が選択行ベースで計算される（metrics は selected 行のみ）ため直接の矛盾は出ないが、`backtest.fukusho_backtest` テーブルに永続化される非選択行の `refund_flag=True, refund_amount=100, refund=0, stake=0, effective_stake=0` という不整合状態が残る（CHECK 制約は無いため DB は受け入れるが監査性を損なう）。

**Fix:** `_zero_out_non_selected_accounting` の `zero_cols` に `refund_flag` (False) と `refund_amount` (0) を追加する。

```python
# scripts/run_backtest.py:509-510
zero_cols = ["stake", "effective_stake", "payout", "refund", "profit",
             "refund_amount", "payout_amount"]
# bool は別途
out.loc[non_selected_mask, "refund_flag"] = False
```

### WR-04: `_carve_calib_from_train_tail` の calib carve で BT-4/5 rolling 窓の train 期間が短くなりすぎる可能性（calib_months=6 固定）

**File:** `scripts/run_backtest.py:174-216`
**Issue:** BT-4 train_start='2021-01-01' / train_end='2023-12-31' で calib_months=6 の場合、carve 後 train=('2021-01-01','2023-06-30') / calib=('2023-07-01','2023-12-31')。これは正常。しかし BT-5 train_start='2019-01-01' / train_end='2023-12-31' でも同一 calib 区間となる。

より重大なのは `_DEFAULT_CALIB_MONTHS = 6` が定数で、短い train 窓（将来 BT 追加で train < 6ヶ月）の場合に train_end_carved が train_start より前になる可能性。`split_3way` の完全時系列条件 guard が catch するが、`train_max < calib_min` ではなく「train が空」で `ValueError` になるためエラーメッセージが分かりにくい。

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

### WR-05: `_filter_label_by_period` が空結果の場合に未 filter の `label_df` を返す（silent フォールバック・§19.1 聖域リスク）

**File:** `scripts/run_backtest.py:1183-1193`
**Issue:** `out = label_df.loc[mask].copy(); return out if len(out) > 0 else label_df` と、filter 結果が空の場合に未 filter の全体を返す。これは BT窓 test 期間外のラベルまで backtest 対象になる silent leak 経路。

ラベルの race_date が BT窓 test 期間と完全に重ならない（例: snapshot の race_date が test 期間外・データ破損・race_date 型不正）場合に、本関数が全体を返すため backtest が「全期間ラベル」で走る。CLAUDE.md が禁止する silent fallback に該当する可能性。

**Fix:** 空結果は `ValueError` で fail-loud にする（Phase 3/4 の `filter_eligible` と同一パターン）。

```python
def _filter_label_by_period(label_df, start, end):
    if "race_date" not in label_df.columns:
        return label_df
    mask = label_df["race_date"].between(start, end)
    out = label_df.loc[mask].copy()
    if len(out) == 0:
        raise ValueError(
            f"_filter_label_by_period: test 期間 ({start}..{end}) に該当する label 行が0件 "
            "(silent フォールバック禁止・race_date 型または BT窓区間を確認)"
        )
    return out
```

### WR-06: `refund_accounting.determine_stake_payout` の特払 (tokubarai) 処理が `payfukusyopay1` を無条件で参照し、slot1 の馬番が選択馬と不一致の場合に誤払戻になる

**File:** `src/ev/refund_accounting.py:151-157`
**Issue:** 特払時 `payout = int(str(row.get("payfukusyopay1", "0")).strip())` は `payfukusyoumaban1` が何であっても（例えば '00' でなく '05' など）`payfukusyopay1` を選択馬の払戻として計上する。

特払の JRA ルールでは「複勝特別払戻」は発売条件により対象馬のオッズに拠らず一律の特払金（通常50円 or 100円）を支払うが・コードは slot1 を無条件参照している。もし `payfukusyoumaban1='05'` で選択馬が `umaban=3` の場合・誤って slot1（=05番の払戻）を 3番馬の払戻として計上する。特払時は `PayFukusyoUmaban1..5` が '00' になる前提だが docstring のみで assert が無い。

**Fix:** 特払時は `payfukusyoumaban1..5` 全てが '00' であることを assert する、または `_lookup_payfukusyo_pay` の通常 path と同様に slot 照合を経由させる（特払フラグ時のみ '00' slot の pay を fallback として扱う）。

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

### WR-07: `orchestrator._apply_category_map` が `feature_df` を copy せず in-place で `_code` 列を上書き（呼出元 frame の副作用）

**File:** `src/model/orchestrator.py:105-161`
**Issue:** `_apply_category_map` は `category_map is None` の場合のみ `feature_df` をそのまま返すが、`category_map` 指定時は `feature_df[code_col] = apply_category_map(...)` で呼び出し元の DataFrame を in-place 更新する。

`train_and_predict` は `feature_df = _apply_category_map(feature_df, category_map)` で受けるが、呼び出し側の `run_backtest._run_pipeline` は BT窓ループ内で `feature_df = _prepare_feature_df(args, readonly_pool)` を最初の BT窓で一度だけ取得し（実は BT窓ループ内で毎回 `_prepare_feature_df` を呼ぶため実害は小さい）。しかし `_assert_deterministic` (`orchestrator.py:763-782`) は同一 `feature_df` で2回 `train_and_predict` を呼ぶため、1回目の `_apply_category_map` が `feature_df` を書き換え、2回目は既に変換済みの生 ID 列に対して再変換を試みる。生 ID 列が str で残っていれば冪等だが・数値化されている場合は `apply_category_map` 内の `series.astype(str)` で異なるコードになる可能性がある。

**Fix:** `_apply_category_map` の冒頭で `feature_df = feature_df.copy()` する。

```python
def _apply_category_map(feature_df, category_map):
    if category_map is None:
        return feature_df
    feature_df = feature_df.copy()  # 呼出元 frame 保護
    from src.utils.category_map import apply_category_map
    # ...
```

### WR-08: `odds_snapshot.select_odds_snapshot` の `datakubun` filter が `'1'` 文字列比較のみで NaN / 数値を考慮しない

**File:** `src/ev/odds_snapshot.py:223-224`
**Issue:** `jodds = jodds[jodds["datakubun"].astype(str) == "1"].copy()` は `datakubun` が NaN の行（`float('nan')` → `'nan'` 文字列）を除外する。`fetch_jodds` の JOIN で head 側の `datakubun` が NULL の場合（JOIN ミスマッチ）、`astype(str)` で `'nan'` となり filter で除外される。これは結果的に安全側に倒れるが・JOIN ミスマッチ自体は静かに発生し得る（race_key 形式不整合 CR-01 がまさにこの経路）。

さらに `datakubun` が `int` で取得された場合（`1` 数値）も `astype(str) == "1"` で一致するため問題ないが・psycopg3 が varchar を `str` / 数値を `int` で返すかはカラム定義に依存し・現状は varchar(2) なので `str` のはず。ただし将来のスキーマ変更で破綻する。

**Fix:** `pd.NA` / NaN を明示的に除外してから比較する。

```python
if "datakubun" in jodds.columns:
    dk = jodds["datakubun"]
    jodds = jodds[dk.notna() & (dk.astype(str).str.strip() == "1")].copy()
```

## Info

### IN-01: `report._format_coverage_table_md` が `threshold` 列を `_format_float` で表示するが、threshold は 0.90/0.95 等の少数なので OK、ただし `report._format_comparison_table_md` の `selected` / `effective_bet` / `refund` の `int(v)` 失敗時 `'0'` は誤表示リスク

**File:** `src/ev/report.py:127-131`
**Issue:** `int(v)` が NaN に対して `ValueError` → `'0'` を返す。NaN は本来「値が無い」ので `'0'` 表示は誤解（0件と同義に見える）。report の数値は `compute_backtest_metrics` が常に int を返すため実害は無いが・`None` を返す future 拡張で破綻する。
**Fix:** `'nan'` または `'-'` を返す方が安全。

### IN-02: `backtest_load._df_to_backtest_tuples` が `df.iterrows()` で行単位ループ（パフォーマンス・大規模 backtest で顕著）

**File:** `src/db/backtest_load.py:206-259`
**Issue:** `prediction_load.py` と同一パターンだが・backtest は25候補×数万行/候補になる可能性があり・`iterrows()` は pandas で最も遅い iter 手法。性能は v1 scope 外（本 review では指摘のみ）。
**Fix:** 将来 vectorize する（列ごとに `_INT_COLS` / `_FLOAT_COLS` / `_BOOL_COLS` を一括変換して zip）。現状は機能的正確性優先で許容。

### IN-03: `run_apply_schema._build_rendered_sql` が `sql.SQL(sql_text)` を使い・`sql_text` に PostgreSQL の `$N` パラメータが含まれると psycopg3 が誤解釈する可能性

**File:** `scripts/run_apply_schema.py:58-64`
**Issue:** `schema_module.CREATE_ROLES_SQL` 内に `DO $$ ... $$` プラック（PostgreSQL ドル引用符）が含まれる。psycopg3 の `sql.SQL().format()` は `{...}` のみを placeholder として解釈するため `$$` は無害だが・docstring のコメントで `{reader}` を文字列として含む行があると誤展開されるリスクがある。現状は `_RENDER_DRY_RUN` と `_build_rendered_sql` の両方で安全に処理されるため機能的正確性は保たれる。
**Fix:** 特に不要。psycopg3 の `sql.SQL` は `{...}` のみ placeholder 扱いなので `$$` は安全。

### IN-04: `ev_rank._rank` が行単位 `df.apply(_rank, axis=1)` で呼ばれ・大規模予測でパフォーマンス低下

**File:** `src/ev/ev_rank.py:112`
**Issue:** `compute_ev_and_rank` は `EV_lower` / `EV_upper` をベクトル化するが rank 判定のみ `apply(axis=1)`。予測行数が多い（数十万）場合に顕著。性能 v1 scope 外。
**Fix:** 将来 `np.select` でベクトル化。

---

_Reviewed: 2026-06-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
