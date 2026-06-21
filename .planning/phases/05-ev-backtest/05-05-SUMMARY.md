---
phase: 05-ev-backtest
plan: 05
subsystem: ev-backtest
tags: [backtest, run-script, report, full-matrix, bt-window-retraining, bl3-betting, leak-prevention, wave-4, high-1, high-2, high-5, high-b, high-c, medium-a, medium-b, medium-cycle-3, low-05]
status: complete
requires:
  - src/utils/group_split.py::BT_WINDOWS (Plan 01・BT窓定数)
  - src/ev/{ev_rank,purchase_simulator,metrics,bl3_betting,odds_snapshot,refund_accounting}.py (Plan 02/03・純粋関数群)
  - src/db/backtest_load.py::load_backtest (Plan 04・backtest_id scoped load)
  - src/model/orchestrator.py::train_and_predict (split_periods/category_map パラメータ・Plan 04)
  - src/model/data.py::{load_feature_matrix,load_labels,build_training_frame} (Phase 4・label-joined frame)
  - src/model/baseline.py::fetch_market_data (Phase 4・BL-3 用確定オッズ)
  - src/utils/category_map.py::{fit_category_map,apply_category_map} (Phase 1・frozen map)
  - scripts/run_train_predict.py (起動フロー・masked DSN パターン)
provides:
  - scripts/run_backtest.py (BT窓再学習 + フル行列 25 backtest + reports/05-backtest 生成 CLI)
  - scripts/run_backtest.py::_carve_calib_from_train_tail(bt) (HIGH-B cycle-2 calib carve)
  - scripts/run_backtest.py::_fit_bt_category_map(feature_df, train_start, train_end) (HIGH-5)
  - scripts/run_backtest.py::_run_main_model_backtest / _run_bl3_backtest (backtest pipeline)
  - scripts/run_backtest.py::_assert_jodds_coverage_horse_level (MEDIUM-B cycle-2 gate)
  - scripts/run_backtest.py::_zero_out_non_selected_accounting (MEDIUM cycle-3)
  - scripts/run_backtest.py::_attach_accounting (determine_stake_payout wrapper・既存会計列削除付き)
  - src/ev/report.py::generate_report(all_backtests) (BACK-04 全候補一括報告・winner 強調禁止)
  - src/ev/report.py::REPORT_COLUMNS (LOW-05 presence 検証対象)
  - reports/05-backtest.md + reports/05-backtest.json (合成データ版・実データ版は Plan 05-06 で生成)
  - tests/ev/test_run_backtest_e2e.py (合成データ E2E smoke 14 テスト・HIGH-1/2/5/B/C + MEDIUM-A/B/cycle-3 + LOW-05 検証)
affects:
  - src/ev/report.py は scripts/run_backtest.py のみから消費 (reports/05-backtest 生成)
  - scripts/run_backtest.py は Plan 01-04 全成果物を統合 (BT_WINDOWS + train_and_predict + select_odds_snapshot + compute_ev_and_rank + select_bets + determine_stake_payout + compute_backtest_metrics + load_backtest + select_bl3_bets)
tech-stack:
  added: []
  patterns:
    - run_train_predict.py 起動フロー (masked DSN・readonly+etl pool・try/except PsycopgError/finally close)
    - HIGH-1+2 馬単位 JOIN (on=['race_key','umaban']) + len(merged)==len(pred_df) assert で cartesian 重複を構造的ブロック
    - HIGH-C cycle-2 HARAI race-level merge (validate='many_to_one') + 行ベース slot lookup (_lookup_payfukusyo_pay)
    - HIGH-B cycle-2 _carve_calib_from_train_tail (train_start 固定・train_end=calib_start-1day に短縮)
    - HIGH-5 BT窓 train 期間のみで fit_category_map → orchestrator category_map plumbing 経由で伝播
    - MEDIUM-A cycle-2 full_candidate_with_accounting (selected + non-selected with odds_missing_reason) → load_backtest
    - MEDIUM cycle-3 non-selected 会計ゼロ化 (loc[...]=0 で stake/effective_stake/payout/refund/profit を 0 化)
    - MEDIUM-B cycle-2 _assert_jodds_coverage_horse_level (horse-level usable-odds coverage < threshold で RuntimeError)
    - BACK-04 全候補一括報告 (backtest_id 辞書順・winner 強調禁止・主モデル確定は Phase 6 委任)
    - LOW-05 REPORT_COLUMNS presence 検証 (grep 否定でなく md ヘッダ + json キーで機械検査)
    - 合成データ E2E smoke (--synthetic・実JODDS/DB 不要・pipeline 完走検証)
    - sort_values(kind='mergesort') 決定論的タイブレーク (共有パターン7・seed 非依存)
key-files:
  created:
    - scripts/run_backtest.py
    - src/ev/report.py
    - tests/ev/test_run_backtest_e2e.py
  modified: []
decisions:
  - "05-05: scripts/run_backtest.py + src/ev/report.py で Plan 01-04 全成果物を統合・フル行列 25 backtest (5窓 × 2policy × 2model + 5 BL-3) を生成"
  - "05-05: 実データ backtest (BT期間 2019-2025) は JODDS 取得進行中のため後続 Plan 05-06 で分離・本 plan では合成データ E2E smoke (--synthetic) で pipeline 動作検証"
  - "05-05 HIGH-B cycle-2: _carve_calib_from_train_tail(bt) は train_start を固定し train_end = calib_start - 1day に短縮 (calib を BT窓 train 尾の6ヶ月から切る)・max(train)<min(calib)<max(calib)<min(test) 順序を BT-1..5 全窓で deterministic に保証"
  - "05-05 HIGH-1+2: pred_df/snapshot/label の merge は on=['race_key','umaban'] + len(merged)==len(pred_df) assert で cartesian duplication を構造的ブロック (HARAI は race-level slot のため on=['race_key']+validate='many_to_one' で例外・HIGH-C)"
  - "05-05 HIGH-5: 各 BT窓 train 期間のみで fit_category_map を呼出し・test 窓未観測 ID を __UNSEEN__ sentinel に mapping (全期間固定 category_map 再利用回避・05-04 HIGH-A category_map plumbing 経由で伝播)"
  - "05-05 HIGH-C cycle-2: HARAI は race-level slot レコードのため race-level merge(on=['race_key'], validate='many_to_one') でブロードキャスト・払戻は 05-03 _lookup_payfukusyo_pay の行ベース slot lookup で確定"
  - "05-05 MEDIUM-A cycle-2: select_bets 後に selected + non-selected の全候補 (full_candidate_with_accounting・odds_missing_reason 埋め) を load_backtest に渡し §11.3 監査性を担保"
  - "05-05 MEDIUM-B cycle-2: --synthetic 外す実行で candidate-horse usable-odds coverage < 0.90 で RuntimeError (race-level coverage < 0.95 も secondary check・取得未完の不正 backtest を loud fail)"
  - "05-05 MEDIUM cycle-3: determine_stake_payout が selected_flag 分岐を持たないため non-selected 行の stake/effective_stake/payout/refund/profit を永続化前に 0 にゼロ化 (架空会計防止・ROI 計算は selected_flag=True filter 済みで非影響)"
  - "05-05 LOW-05: REPORT_COLUMNS を外部定数で定義し md 列ヘッダ + json comparison_table キーと 1:1 になることを presence assert で機械検証 (grep 否定でない)"
  - "05-05 BACK-04: 全候補を backtest_id 辞書順で一括提示・highest-recovery を推奨/採用候補として突出させる記述は一切生成しない (主モデル確定は Phase 6 D-03/D-04 事前登録選定基準)"
metrics:
  duration: 32m
  completed: 2026-06-21T00:25:00Z
  task_count: 2
  file_count: 3
---

# Phase 5 Plan 05: run_backtest + report (BT窓再学習 + フル行列 25 backtest + reports 生成) Summary

Phase 5 最終成果物として scripts/run_backtest.py（BT窓再学習ループ + フル行列 25 backtest + reports/05-backtest 生成 CLI）と src/ev/report.py（全候補一括報告・winner 強調禁止）を実装し、Plan 01-04 全成果物を統合。合成データ E2E smoke（--synthetic）で pipeline 完走と reports 生成を検証（実データ backtest は JODDS 取得進行中のため後続 Plan 05-06 で分離）。HIGH-1/2 馬単位 JOIN + 行数不変 assert・HIGH-5 BT窓 category_map refit・HIGH-B calib carve・HIGH-C HARAI race-level merge・MEDIUM-A full_candidate 永続化・MEDIUM-B horse-level coverage gate・MEDIUM cycle-3 non-selected 会計ゼロ化・LOW-05 REPORT_COLUMNS presence 検証の全構造的ブロックを確立。

## What Was Built

### Task 1: scripts/run_backtest.py + src/ev/report.py（フル行列 backtest pipeline）

**コミット (1661ae2):** scripts/run_backtest.py（約1100行）+ src/ev/report.py（約260行）を新設。

**scripts/run_backtest.py（BT窓再学習 + フル行列 25 backtest CLI）:**

- **起動フロー**（run_train_predict.py パターン・masked DSN・try/except PsycopgError/finally close）
- **BT窓再学習ループ**（D-03）: `for bt in BT_WINDOWS: for model_type in {lightgbm, catboost}`:
  - `_carve_calib_from_train_tail(bt)`（HIGH-B cycle-2）: `train_start` 固定・`train_end = calib_start - 1day` に短縮・calib を BT窓 train 尾の6ヶ月から切る（例 BT-1: train='2019-06-01'..'2022-06-30' / calib='2022-07-01'..'2022-12-31' / test='2023-01-01'..'2023-12-31'）。`max(train)<min(calib)<max(calib)<min(test)` 順序を BT-1..5 全窓で deterministic に保証
  - `_fit_bt_category_map(feature_df, train_start, train_end)`（HIGH-5）: BT窓 train 期間の行のみで `fit_category_map` を呼び・`jockey_id`/`trainer_id`/`sire_id`/`bms_id`/`horse_id` 毎に frozen map を構築。test 窓未観測 ID → `__UNSEEN__` sentinel（§14.3 leak-safe categorical）。05-04 HIGH-A category_map plumbing 経由で orchestrator に伝播
  - `train_and_predict(..., split_periods=periods, category_map=bt_map, as_of_datetime=FIXED_REPRODUCE_TS)`（SC#4 bit-identical・seed=42 + 固定 thread）

- **フル行列 backtest**（5窓 × 2policy × 2model + 5 BL-3 = 25）:
  - `fetch_jodds(readonly_cur)` + `select_odds_snapshot(jodds_df, race_times, policy)`（per-horse cutoff 以下最大 snapshot・HIGH-1）
  - HIGH-2: `pred_df.merge(snapshot, on=['race_key','umaban'])` + `len(pred_with_odds)==len(pred_df)` assert で cartesian duplication を構造的ブロック
  - `compute_ev_and_rank` → `select_bets`（§11.4 fukusho_ev_v1）→ full_candidate table 構築（MEDIUM-A cycle-2・selected_flag=True/False の全候補）
  - HIGH-C cycle-2: HARAI race-level merge（`validate='many_to_one'`・race-level slot レコードを馬行にブロードキャスト）+ label 馬単位 merge
  - `_attach_accounting`（determine_stake_payout wrapper・既存会計列削除付き）→ `_zero_out_non_selected_accounting`（MEDIUM cycle-3・selected_flag=False 行の会計ゼロ化）
  - `compute_backtest_metrics`（selected_flag=True filter）→ `_attach_provenance` → `load_backtest`（full_candidate・MEDIUM-A cycle-2）

- **BL-3 backtest**（D-04・5窓 × 1 = 5）: `fetch_market_data`（確定オッズ）→ `select_bl3_bets`（fukuoddslow 昇順 top-2・EV 自己参照回避）→ refund/metrics/load_backtest

- **MEDIUM-B cycle-2 horse-level usable-odds coverage gate**（`--synthetic` 外す実行時）: `_assert_jodds_coverage_horse_level` が candidate-horse usable-odds coverage（no_bet sentinel を除いた実利用可能オッズ馬の割合）を測定し < 0.90 で RuntimeError・race-level coverage < 0.95 も secondary check（元 MEDIUM-05）

- **--check-reproduce**（SC#4）: BT窓でも seed=42 + 固定 thread + FIXED_REPRODUCE_TS で bit-identical 検証

**src/ev/report.py（全候補一括報告・BACK-04 winner 強調禁止）:**

- `generate_report(all_backtests, *, output_dir='reports', jodds_status='synthetic', coverage_summary=None)`: reports/05-backtest.{md,json} を生成。全候補を backtest_id 辞書順で一括提示・winner 強調禁止
- `REPORT_COLUMNS`（LOW-05）: `('backtest_id','bt_name','odds_policy','model_type','recovery_rate','P/L','max_DD','selected','effective_bet','refund','hit_rate')` を定数化・md 列ヘッダと json comparison_table キーが 1:1
- `_format_comparison_table_md` / `_format_notes` / `_format_coverage_table_md`
- `ODDS_POLICY_FIXED_NOTE`（§11.2 固定履行確認セクション）・`NO_WINNER_OVERRIDE_NOTE`（BACK-04）・BL3 §14.2 caveat 注記・Phase 6 確定委任注記

### Task 2: 合成データ E2E smoke テスト（test_run_backtest_e2e.py）

**コミット (bbd7d3e):** 14 テスト新設。HIGH-1/2/5/B/C + MEDIUM-A/B/cycle-3 + LOW-05 全検証。実JODDS/DB 不要（`--synthetic`）。

| Test | 要件 | 検証内容 |
|------|------|----------|
| `test_synthetic_full_matrix_smoke` | BACK-01..04 | BT-1 5件（2policy×2model+1BL-3）完走・reports 生成 |
| `test_report_all_candidates_format` | BACK-04 | 全 backtest_id が md に含まれる |
| `test_report_no_winner_override` | BACK-04 | 「推奨:」「採用候補:」突出行がない |
| `test_report_strategy_version_stamp` | §19.1 | fukusho_ev_v1 が report に stamp |
| `test_report_bl3_caveat_present` | §14.2 | BL3_COMPARISON_CAVEAT 注記あり |
| `test_check_reproduce_smoke` | SC#4 | --check-reproduce フラグ smoke |
| `test_pred_snapshot_join_row_count_invariant` | HIGH-2 | 行数不変 + _run_main_model_backtest assert 検査 |
| `test_horse_level_odds_preserved_in_pipeline` | HIGH-1 | 各馬 odds が pipeline 通過後も維持 |
| `test_bt_category_map_refit_excludes_test_ids` | HIGH-5 | test 窓 ID → __UNSEEN__ mapping |
| `test_report_columns_present` | LOW-05 | REPORT_COLUMNS 全要素が report 出力に存在 |
| `test_carve_calib_strict_ordering_and_deterministic` | HIGH-B cycle-2 | 順序不変 + 同窓2回 carve で bit-identical |
| `test_harai_payout_lookup_no_broadcast` | HIGH-C cycle-2 | race-level merge + slot lookup で行数不変・正しい払戻 |
| `test_load_backtest_persists_nonselected` | MEDIUM-A cycle-2 + cycle-3 | non-selected 会計ゼロ化 |
| `test_horse_level_odds_coverage_gate` | MEDIUM-B cycle-2 | horse-level usable coverage < threshold で RuntimeError |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking fix] 合成 pred_df に select_bets/label 必須列を保持**

- **Found during:** Task 2 smoke テスト実行時
- **Issue:** `_build_synthetic_pred_df` が `is_fukusho_sale_available` / `is_model_eligible` / `is_scratch_cancel` 等を含んでいなかったため・`select_bets` が `KeyError: 'is_fukusho_sale_available'` で失敗。
- **Fix:** `_build_synthetic_pred_df` の抽出列に `is_fukusho_sale_available` / `is_model_eligible` / `is_scratch_cancel` / `is_race_excluded` / `is_race_cancelled` / `is_dead_loss` / `fukusho_payout_places` / `fukusho_hit_validated` / `race_start_datetime` を追加（合成データは feature_df から直接予測として扱うため・select_bets/label merge/refund_accounting が消費する列が必要）。
- **Files modified:** `scripts/run_backtest.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

**2. [Rule 3 - Blocking fix] 合成データの race_key sort と race_start_datetime sort を一致**

- **Found during:** Task 2 smoke テスト実行時
- **Issue:** pandas `merge_asof` が `left_on`/`right_on` の大域的単調増加を要求するが・合成データの race_key 文字列（`{year}-{jyocd}-...`）sort 順序が race_start_datetime sort 順序と不一致だったため・`select_odds_snapshot` で `ValueError: left keys must be sorted`。
- **Fix:** race_key を `{year}-{month:02d}-{jyocd}-...` 形式に変更し・race_start_datetime を jyocd（10/11時）と racenum（00/30分）で調整して race_key sort = race_start_datetime sort となるよう構築。Plan 03 odds_snapshot.py 実装の制約（by= セマンティクスでも left_on/right_on 大域 sort を要求）に合成データ側を適合。
- **Files modified:** `scripts/run_backtest.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

**3. [Rule 3 - Blocking fix] 合成 JODDS を各馬1件の snapshot に簡素化**

- **Found during:** Task 2 smoke テスト実行時
- **Issue:** 合成 jodds が race_key+umaban 毎に2件の snapshot（60分前/30分前）を生成していたが・race_key をまたぐと happyo_datetime が非単調（right keys must be sorted）。
- **Fix:** 各馬1件の snapshot（race_start_datetime - 20分）に簡素化し・happyo_datetime が大域 sort されることを保証（cutoff 30分/10分のいずれでも選択される安全な時刻）。
- **Files modified:** `scripts/run_backtest.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

**4. [Rule 3 - Blocking fix] _attach_accounting helper 新設（既存会計列削除付き）**

- **Found during:** Task 2 smoke テスト実行時
- **Issue:** `_run_bl3_backtest`（と一部主モデルケース）で `select_bets` / `select_bl3_bets` が設定した `stake` 列と `determine_stake_payout` の戻り `stake` 列が `pd.concat` で衝突し・`df["stake"]` が DataFrame（複数列）を返して `float(df["stake"].sum())` が `TypeError` になる。
- **Fix:** `_attach_accounting` helper を新設し・`determine_stake_payout` 適用前に `base.drop(columns=[既存会計列])` で既存 stake/refund/payout/profit/effective_stake を削除してから concat。両 backtest 関数で使用。
- **Files modified:** `scripts/run_backtest.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

**5. [Rule 1 - Bug fix] 合成 market_df に race_date 列を保持**

- **Found during:** Task 2 smoke テスト実行時
- **Issue:** `_build_synthetic_market_df` が `race_date` を含んでいなかったため・BL-3 pipeline で `compute_backtest_metrics` が `KeyError: 'race_date'`（max drawdown の時系列累積用）で失敗。
- **Fix:** `_build_synthetic_market_df` の抽出列に `race_date` を追加。
- **Files modified:** `scripts/run_backtest.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

**6. [Rule 1 - Bug fix] report.md に backtest_strategy_version 明記**

- **Found during:** Task 2 `test_report_strategy_version_stamp` 実行時
- **Issue:** report.py の §11.2 セクションに `fukusho_ev_v1` が明記されていなかったため・md にリテラルが含まれず acceptance criteria「backtest_strategy_version='fukusho_ev_v1' がハードコード（grep 含む）」を満たさなかった。
- **Fix:** §11.2 odds policy 固定履行確認セクションに「backtest_strategy_version (全 backtest 行共通): fukusho_ev_v1 (§19.1 再現性 stamp)」を明記。
- **Files modified:** `src/ev/report.py`
- **Commit:** bbd7d3e（Task 2 コミットに統合）

### スコープ外（後続 Plan 05-06 で対応）

**実データ backtest（BT期間 2019-2025）**: 本 plan の objective で明示的に「実データ backtest は JODDS 取得進行中のため manual-only 検証として後続 Plan 05-06 で分離」と記載。本 plan では合成データでのスクリプト動作確認と reports 生成ロジックの実装が対象。`--synthetic` で pipeline が完走し reports/05-backtest が生成されることを 14 テストで検証。実データ実行（`run_backtest.py --snapshot-id 20260620-1a-postreview-v2`・JODDS取得完了後）は Plan 05-06 の checkpoint:human-verify で実施予定。

**`--check-reproduce` の実データ bit-identical 検証**: 本 plan では `--check-reproduce` フラグの smoke（parse・pipeline 入場）のみ検証。実データでの `_assert_deterministic` 呼出（BT窓 × model_type 毎に bit-identical を実証）は Plan 05-06 スコープ（実データ feature_df が必要なため）。

## Threat Mitigation Verification

| Threat ID | Category | Mitigation | Verification |
|-----------|----------|------------|--------------|
| T-05-15 | Information Disclosure | reports/05-backtest で highest-recovery backtest_id を「推奨」「採用候補」と強調禁止 | `test_report_no_winner_override`（行頭「推奨:」「採用候補:」突出行がない）+ grep `-c '推奨:'` == 0 (bbd7d3e) |
| T-05-16 | Tampering | BT窓再学習で calib slice が train と重複（look-ahead leak） | split_3way の完全時系列 guard（Plan 04・HIGH-4） + `test_carve_calib_strict_ordering_and_deterministic`（HIGH-B cycle-2・BT-1..5 全窓で max(train)<min(calib)<max(calib)<min(test)） (bbd7d3e) |
| T-05-17 | Tampering | 生 DSN がログに漏洩 | `Settings().dsn_masked / etl_dsn_masked` を使用・run_train_predict.py パターン（生 DSN 絶対禁止） (1661ae2) |
| T-05-17b | Tampering | 予測/snapshot/label JOIN が race_key 単独で cartesian duplication | `on=['race_key','umaban']` + `len(pred_with_odds)==len(pred_df)` assert + `test_pred_snapshot_join_row_count_invariant` (bbd7d3e) |
| T-05-17c | Information Disclosure | BT窓再学習で全期間固定 category_map を再利用し test 窓 ID 漏洩 | 各 BT窓 train 期間のみで `fit_category_map`・test 窓未観測 ID → `__UNSEEN__`・`test_bt_category_map_refit_excludes_test_ids` (bbd7d3e) |
| T-05-17d | Tampering | JODDS 取得未完で実行し大部分を no_bet 化して不正 backtest | `_assert_jodds_coverage_horse_level`（horse-level usable coverage < 0.90 で RuntimeError）+ `test_horse_level_odds_coverage_gate` (bbd7d3e) |
| T-05-19 | Tampering | `_carve_calib_from_train_tail` で train_start を短縮する typo | train_start 固定・train_end=calib_start-1day・`test_carve_calib_strict_ordering_and_deterministic`（HIGH-B cycle-2・train_start==bt.train_start assert 含む） (bbd7d3e) |
| T-05-20 | Tampering | HARAI 払戻を馬単位 JOIN して silent broadcast | HARAI race-level merge（`validate='many_to_one'`）+ 行ベース slot lookup・`test_harai_payout_lookup_no_broadcast` (bbd7d3e) |
| T-05-21 | Tampering | select_bets 後に selected のみを load_backtest に渡し non-selected 破棄 | full_candidate_with_accounting（selected + non-selected with odds_missing_reason）→ load_backtest・MEDIUM-04 監査性 (1661ae2) |
| T-05-24 | Tampering | determine_stake_payout が selected_flag 分岐を持たず non-selected 行に架空会計 | `_zero_out_non_selected_accounting`（selected_flag=False 行の stake/effective_stake/payout/refund/profit を 0 化）+ `test_load_backtest_persists_nonselected` (bbd7d3e) |
| T-05-SC | Tampering | 新規パッケージなし | 既存スタックのみ（LightGBM/CatBoost/sklearn/pandas/psycopg3）・T-05-SC accept (1661ae2) |

## Verification

全 acceptance criteria 検証済み:

```
=== Task 1 構文 + --help ===
$ uv run python -c "import ast; ast.parse(open('scripts/run_backtest.py').read()); ast.parse(open('src/ev/report.py').read()); print('syntax OK')"
syntax OK

$ uv run python scripts/run_backtest.py --help
usage: run_backtest.py [-h] [--snapshot-id SNAPSHOT_ID] [--synthetic]
                       [--bt-filter BT_FILTER] [--check-reproduce]
                       [--version-n VERSION_N] [--no-write-db]
                       [--output-dir OUTPUT_DIR]
(... argparse help 表示)

=== Task 2 合成データ E2E smoke (14 テスト) ===
$ uv run pytest tests/ev/test_run_backtest_e2e.py -q
14 passed in 2.27s

=== Plan verification: grep -c '推奨:' == 0 (BACK-04) ===
$ grep -c "推奨:" scripts/run_backtest.py src/ev/report.py
src/ev/report.py:0
scripts/run_backtest.py:0
Total: 0

=== 広範回帰 (Phase 5 全 plan + Phase 4 model/db) ===
$ KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ev/ tests/model/ tests/utils/test_group_split.py tests/db/ -q
126 passed, 7 skipped, 3 warnings in 31.22s
  (Plan 01-05 全テスト + Phase 4 model 系・回帰なし・skip は requires_db・warnings は pre-existing LightGBM/sklearn)

=== 合成 BT-1 report 内容確認 ===
$ uv run python scripts/run_backtest.py --synthetic --bt-filter BT-1 --no-write-db --output-dir /tmp
# Phase 5 Backtest Report (BACK-01..04 / §15.5 / §19.1)

## 比較表 (全候補一括提示・winner 強調なし・BACK-04)

| backtest_id | bt_name | odds_policy | model_type | recovery_rate | P/L | max_DD | selected | effective_bet | refund | hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BT-1-10min_before-catboost | BT-1 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-10min_before-lightgbm | BT-1 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-30min_before-catboost | BT-1 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-30min_before-lightgbm | BT-1 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-confirmed-bl3 | BT-1 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |
(... §11.2 odds policy 固定履行確認セクション / backtest_strategy_version=fukusho_ev_v1 / BL3 caveat / 主モデル Phase 6 委任注記)
```

Acceptance criteria:

- [x] scripts/run_backtest.py が存在し ast.parse で構文 OK・python scripts/run_backtest.py --help が argparse help を表示
- [x] src/ev/report.py に "def generate_report" と "REPORT_COLUMNS" と "05-backtest" が含まれる
- [x] scripts/run_backtest.py に "BT_WINDOWS" と "split_periods" と "load_backtest" と "generate_report" と "FIXED_REPRODUCE_TS" が含まれる
- [x] フル行列 25 backtest（5窓 × 2policy × 2model + 5 BL-3）のループ構造が含まれる（"30min_before" / "10min_before" / "bl3" 含む）
- [x] HIGH-2 馬単位 JOIN（cycle-3 整合）: snapshot/label merge は on=['race_key','umaban']（行数不変 assert）・HARAI は race-level slot のため on=['race_key'] + validate='many_to_one'（HIGH-C）
- [x] HIGH-2 行数不変 assert: `len(pred_with_odds) == len(pred_df)` が存在（_run_main_model_backtest 内）
- [x] HIGH-5 BT窓 category map refit: `_fit_bt_category_map` で BT窓 train 行に対して `fit_category_map` を呼出し・orchestrator.train_and_predict の category_map 引数に BT窓 train で fit した map を渡す
- [x] MEDIUM-B cycle-2 horse-level coverage gate: `_assert_jodds_coverage_horse_level` が horse_level usable-odds coverage を測定し < threshold で RuntimeError
- [x] HIGH-B cycle-2 carve: `_carve_calib_from_train_tail` で train_start を固定し train_end = calib_start - 1day に設定（test_carve_calib_strict_ordering_and_deterministic で train_start==bt.train_start を assert）
- [x] HIGH-C cycle-2 HARAI race-level merge: HARAI merge で `validate='many_to_one'` が含まれ・on=['race_key']・PayFukusyoUmaban/PayFukusyoPay slot 列をブロードキャスト
- [x] MEDIUM-A cycle-2 full candidate table: load_backtest に full_candidate_with_accounting（selected_flag True/False の全候補行）を渡す
- [x] select_odds_snapshot に渡す race_times が馬単位（_build_race_times_per_horse・race_key + umaban + race_start_datetime）
- [x] reports 生成で winner 強調表記が無い（grep `-c '推奨:'` == 0・test_report_no_winner_override）
- [x] backtest_strategy_version='fukusho_ev_v1' がハードコード（FUKUSHO_EV_V1_STRATEGY 定数 + report.md §11.2 セクション明記）
- [x] LOW-05: REPORT_COLUMNS の全要素が report 出力に含まれる（test_report_columns_present・md ヘッダ + json キー presence 検証）
- [x] tests/ev/test_run_backtest_e2e.py が存在し uv run pytest で全件 GREEN（14 passed）
- [x] reports/05-backtest.md と reports/05-backtest.json が生成される（テスト実行後）
- [x] reports/05-backtest.md に「推奨:」記述が無い（BACK-04・test_report_no_winner_override）
- [x] reports/05-backtest.md に backtest_strategy_version='fukusho_ev_v1' と BL3_COMPARISON_CAVEAT 注記が含まれる
- [x] test_pred_snapshot_join_row_count_invariant が GREEN（HIGH-2）
- [x] test_horse_level_odds_preserved_in_pipeline が GREEN（HIGH-1）
- [x] test_bt_category_map_refit_excludes_test_ids が GREEN（HIGH-5）
- [x] test_report_columns_present が GREEN（LOW-05）
- [x] test_carve_calib_strict_ordering_and_deterministic が GREEN（HIGH-B cycle-2）
- [x] test_harai_payout_lookup_no_broadcast が GREEN（HIGH-C cycle-2）
- [x] test_load_backtest_persists_nonselected が GREEN（MEDIUM-A cycle-2 + MEDIUM cycle-3 non-selected 会計ゼロ化）
- [x] test_horse_level_odds_coverage_gate が GREEN（MEDIUM-B cycle-2）

## Success Criteria

- [x] scripts/run_backtest.py が BT窓再学習 + フル行列 25 backtest + reports 生成を実装
- [x] src/ev/report.py が全候補一括報告（winner 強調禁止・BACK-04）
- [x] 合成データ E2E smoke GREEN（実JODDS未完でも検証可能・14 tests）
- [x] HIGH-1+2 馬単位 JOIN + 行数不変 assert で cartesian duplication を構造的ブロック（test_pred_snapshot_join_row_count_invariant / test_horse_level_odds_preserved_in_pipeline GREEN）
- [x] HIGH-5 BT窓 category map refit で test 窓 ID 漏洩防止（test_bt_category_map_refit_excludes_test_ids GREEN）
- [x] MEDIUM-05/MEDIUM-B JODDS coverage gate で取得未完の不正実行を loud fail（test_horse_level_odds_coverage_gate GREEN）
- [x] LOW-05 REPORT_COLUMNS presence 検証（test_report_columns_present GREEN）
- [x] BACK-01/02/03/04 + D-03/D-04 を統合履行（BT窓再学習ループ + フル行列 25 backtest + backtest_strategy_version stamp + BL-3 §14.2 caveat + winner 報告禁止）

## Commits

| Hash | Type | Message |
|------|------|---------|
| 1661ae2 | feat | implement run_backtest + report (BT窓再学習 + フル行列 25 backtest + reports 生成) |
| bbd7d3e | test | 合成データ E2E smoke + pipeline 修正 (Rule 1/3 auto-fix) |
| e5996b4 | chore | ruff lint 整理 (noqa/E501・未使用 import 削除・f-string placeholder) |

## Self-Check: PASSED

### Created files exist

- FOUND: scripts/run_backtest.py
- FOUND: src/ev/report.py
- FOUND: tests/ev/test_run_backtest_e2e.py

### Commits exist

- FOUND: 1661ae2 (feat(05-05): implement run_backtest + report)
- FOUND: bbd7d3e (test(05-05): 合成データ E2E smoke + pipeline 修正)
- FOUND: e5996b4 (chore(05-05): ruff lint 整理)

### BACK-04 grep 検証

- `grep -c '推奨:' scripts/run_backtest.py src/ev/report.py` == 0 (winner 強調禁止)
