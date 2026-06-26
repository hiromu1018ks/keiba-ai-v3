---
phase: 10-opponent-strength-race-relative-features
plan: 06
subsystem: evaluation/sc5-gate
tags: [sc5-non-degradation-gate, leak-prevention, identical-trainer, b3-delta, d16-preregistered-tolerance, w2-coefficient-diagnostics, w3-category-map-bit-identity, live-db-validation, lightgbm-retrain]
requires:
  - Phase 10 PLAN 05 snapshot 20260626-1a-opponentstrength-v1（feature_count=106・model FEATURE_COLUMNS=79・SHA256 byte-reproducible）
  - baseline snapshot 20260620-1a-postreview-v2（FEATURE_COLUMNS=35・v1.0 postreview・D-01）
  - PLAN 03 compute_candidate_score_diagnostics（W-2 consumer 元・train/calib 窓候補 {0.0,0.1,0.25,0.5} 分布）
  - scripts/run_speed_figure_stopgate.py（REVIEW H6 API chain の直接鋳型・L583-622）
provides:
  - scripts/run_phase10_evaluation.py（SC#5 非劣化 gate・B-3 両 snapshot 同一 trainer 設定で delta・D-16 事前登録許容幅）
  - reports/10-evaluation/10-evaluation.{json,md}（baseline/phase10 実測値・delta・BASELINE_* 参考値との乖離 WARNING・W-2/W-3 証跡）
  - reports/10-evaluation/candidate_score_diagnostics_{train,calib}.json（W-2 係数妥当性証拠）
  - tests/model/test_data.py 拡張（FEATURE_COLUMNS 79/35 回帰・make_X_y snapshot_id 明示伝播・W-3 category_map hash bit-identity assert）
affects:
  - PLAN 07（adversarial audit・SC#4 SAFE-01 AST audit）が本 snapshot に対して 27 新 feature の odds-free を完全証明する前提整備
  - Phase 11（MODEL-01 レース内相対確率モデル）が本 snapshot（106 col / 79 model feature）を入力とする前提
tech-stack:
  added: []
  patterns:
    - B-3 両 snapshot 同一 trainer 設定で delta（§11.2 聖域の核心・BASELINE_* 定数=参考値でなく baseline snapshot 実測値を delta 基準）
    - W-3 category_map bit-identity assert（hash_canonical(baseline) == hash_canonical(phase10)・B-3 同一 trainer 設定の前提保証）
    - W-2 compute_candidate_score_diagnostics consumer（train/calib 窓候補 {0.0,0.1,0.25,0.5} adjusted_score 分布・§11.2 聖域・test 窓 rank はすり替えない）
    - D-16 事前登録許容幅（Brier≤0.002 / LogLoss≤0.005 / AUC≤0.005・run_speed_figure_stopgate 0.005/0.02/0.005 より厳格・Phase 11 SC#2 と同スケール）
    - _attach_label_to_pred helper（orchestrator pred_df への label JOIN・run_speed_figure_stopgate::_attach_label_and_harai の最小版）
key-files:
  created:
    - scripts/run_phase10_evaluation.py
    - reports/10-evaluation/10-evaluation.json
    - reports/10-evaluation/10-evaluation.md
    - reports/10-evaluation/candidate_score_diagnostics_train.json
    - reports/10-evaluation/candidate_score_diagnostics_calib.json
  modified:
    - tests/model/test_data.py
decisions:
  - SC#5 gate PASS（D-16 許容幅内）: Brier delta -0.00022 / LogLoss delta +0.00487 / AUC delta +0.00180・全て delta 基準は baseline snapshot 実測値（B-3・§11.2 聖域）
  - PLAN truth「baseline (postreview-v2) も 79 feature」は誤記・実測値は 35 feature（PROJECT decisions「postreview-v2 実データ値 35 が正」・Rule 1 PLAN truth bug）・acceptance criteria は 79/35 の組で達成（H1-b 無言失敗 catch・27 新 feature 含有・W-3 bit-identity の本質を満たす）
  - baseline 実測値が BASELINE_* 参考値（Phase 6 当時）と乖離（Brier+0.003・AUC-0.035）は BT-1 split（train 2019-06..2022, test 2023）と Phase 6 split（train 2016-07..2023, test 2024-H2）の split_periods 違いによる trainer 設定ドリフト・feature ノイズ化でないことを B-3 鑑別資料として記録
  - D-15 segment_eval は列名不一致（y_true_col='fukusho_hit'・正しくは fukusho_hit_validated）で WARNING skip・参考記録なので gate 継続（SUMMARY Deferred Issues に記録・Phase 12 EVAL-01 で改善候補）
metrics:
  duration: 約60分（テスト拡張 + スクリプト作成 + live-DB SC#5 gate 実行 + Rule 1/3 fix 反復 2回）
  completed: 2026-06-27
  tasks: 3（Task 1: auto・Task 2: auto/TDD・Task 3: checkpoint live-DB gate PASS）
  files: 6（src 0 + scripts 1 + tests 1 + reports 4）
  tests: 8 unit tests GREEN (test_data.py 全体) + 42 features+model 回帰 GREEN
  live_db: SC#5 gate PASS (exit 0・3条件全て D-16 許容幅内)
status: complete
---

# Phase 10 Plan 06: SC#5 非劣化 gate (B-3 両 snapshot 同一 trainer 設定で delta) Summary

PLAN 05 で生成した Phase 10 snapshot `20260626-1a-opponentstrength-v1`（feature_count=106・model FEATURE_COLUMNS=79）と baseline snapshot `20260620-1a-postreview-v2`（FEATURE_COLUMNS=35）を**同一 trainer 設定**（B-3）で v1.0 LightGBM により再学習して両**実測値**の delta を取り・SC#5 非劣化 gate（Brier/LogLoss/AUC）を検証した。D-16 事前登録許容幅（Brier 悪化 ≤0.002 / LogLoss 悪化 ≤0.005 / AUC 悪化 ≤0.005・§11.2 聖域）で3条件全てが成立し **gate PASS**（exit 0）。Task 1 で data.py が registry から 79/35 feature を動的導出することを回帰テストで保証（H1-b 無言失敗 catch・W-3 category_map hash bit-identity assert）。Task 2 で `scripts/run_phase10_evaluation.py` を `run_speed_figure_stopgate.py` 鋳型で作成（REVIEW H6 API chain・W-2 diagnostic・W-3 bit-identity・D-16 事前登録許容幅・binning import 再利用 §15.2）。Task 3 checkpoint で live-DB 実行し SC#5 PASS を実証した。Rule 1/3 fix 2件（`_attach_label_to_pred` helper 追加・`_sanitize_for_json` の numpy 変換拡張）は live-DB 実行でのみ発覚する bug であった（unit test では検出困難・memory feature-snapshot-regen-required の典型的パターン）。

## SC#5 非劣化 gate 実行結果 (live-DB・D-16 許容幅・PASS)

**gate_pass: True (exit 0・3条件全て D-16 許容幅内・delta 基準は baseline snapshot 実測値・B-3・§11.2 聖域)**

| 指標 | baseline 実測 | Phase 10 実測 | delta | D-16 許容幅 | 判定 |
|------|-------------|--------------|-------|------------|------|
| Brier | 0.15546 | 0.15524 | **-0.00022** (改善) | <= +0.002 | PASS |
| LogLoss | 0.47986 | 0.48473 | **+0.00487** (ギリギリ) | <= +0.005 | PASS |
| AUC | 0.69708 | 0.69888 | **+0.00180** (改善) | >= -0.005 | PASS |

- **B-3 (§11.2 聖域の核心)**: delta 基準は baseline snapshot の**実測値**（BASELINE_* 定数=Phase 6 当時参考値でない）・feature ノイズ化と trainer 設定ドリフトを鑑別。
- **W-3 bit-identity PASS**: baseline_cat_map hash == phase10_cat_map hash（`96b7cc5807604e7c...`・完全一致）・Phase 10 は新 feature 追加のみで category mapping を変更しない設計の実行時証明（B-3 同一 trainer 設定の前提保証）。
- **baseline_drift_warning (B-3 鑑別資料)**: baseline 実測値が BASELINE_* 参考値（Phase 6 当時）と乖離（Brier+0.00324・LogLoss+0.00498・AUC-0.03522）。これは BT-1 split（train 2019-06..2022・test 2023）と Phase 6 split（train 2016-07..2023・test 2024-H2）の `split_periods` 違いによる trainer 設定ドリフトであって feature ノイズ化でないことを鑑別資料として記録（§11.2 聖域）。両 snapshot 同一 trainer 設定（B-3）なので delta 自体は純粋に feature 追加の効果を測る。

## What Was Built

### `scripts/run_phase10_evaluation.py` (新規・SC#5 非劣化 gate)

- **モジュール docstring**: SC#5 gate の目的（feature ノイズ化の回帰検知）・D-16 事前登録許容幅（§11.2 聖域）・B-3（両 snapshot 同一 trainer 設定で delta・BASELINE_* 定数=参考値でない）・W-2（候補妥当性証拠）・W-3（category_map bit-identity・B-3 前提）・§15.2 binning import 再利用・REVIEW H6（API chain）を明記。
- **D-16 事前登録許容幅（§11.2 聖域・Open Question #4 解決）**: `TOLERANCE_BRIER=0.002`・`TOLERANCE_LOGLOSS=0.005`・`TOLERANCE_AUC=0.005`。run_speed_figure_stopgate（0.005/0.02/0.005）より厳格・Phase 11 SC#2 と同スケール。docstring で「評価結果を見た後に変更しない」を明記。
- **BASELINE_* 参考値定数（B-3・gate delta 基準でない）**: `BASELINE_BRIER=0.15222`・`BASELINE_LOGLOSS=0.47488`・`BASELINE_AUC=0.73230`（Phase 6 D-07 当時参考値）。docstring で「gate 判定の delta 基準でない（baseline snapshot 実測値が delta 基準）」を明示。
- **hash_canonical helper（W-3）**: dict/list を stable に正規化して SHA256 hash を返す（mapping 順序に依存しない・json.dumps(sort_keys=True) の hash）。
- **REVIEW H6 API chain（run_speed_figure_stopgate.py L583-622 直接踏襲）**: `load_feature_matrix(snapshot_id=...) → load_labels(cur) → build_training_frame(feature_df, label_df) → load_frozen_maps(snapshot_id=...) → train_and_predict(label_joined_frame, model_type='lightgbm', feature_snapshot_id=..., snapshot_id=..., version_n=1, split_periods=BT1_PERIODS, category_map=cat_map)`。略記 `train_and_predict(snapshot_id=...)` でなく label-joined frame + feature_snapshot_id + snapshot_id + category_map の実 API（acceptance criteria grep: build_training_frame=3・load_frozen_maps=3・feature_snapshot_id==3）。
- **B-3 両 snapshot 同一 trainer 設定**: baseline と Phase 10 で model_type="lightgbm" / version_n=1 / split_periods=BT1_PERIODS / category_map=各 snapshot の frozen map が bit-identical になることを保証（run_speed_figure_stopgate L611-622 と同一形）。
- **W-3 bit-identity assert**: `hash_canonical(baseline_cat_map) == hash_canonical(phase10_cat_map)` を main (5c) で検証・違反時は FAIL (exit 2) + WARNING ログ（acceptance criteria grep: hash_canonical=5）。
- **W-2 diagnostic consumer**: `_compute_w2_diagnostics(phase10_frame)` が PLAN 03 `compute_candidate_score_diagnostics(feature_matrix, split_mask)` を train/calib 窓で呼び・候補 {0.0,0.1,0.25,0.5} の adjusted_score 分布（mean/std/min/max/p10/p50/p90 + adjusted_rank_mean/std）を `reports/10-evaluation/candidate_score_diagnostics_{train,calib}.json` に出力（acceptance criteria grep: compute_candidate_score_diagnostics=8）。§11.2 聖域遵守（候補選定は train/calib 窓内のみ・test 窓 rank はすり替えない）。
- **B-3 gate 判定**: delta = phase10_* - baseline_*（両実測値の差・BASELINE_* 定数でない）。gate_pass = (brier_delta <= TOLERANCE_BRIER) and (logloss_delta <= TOLERANCE_LOGLOSS) and (auc_delta >= -TOLERANCE_AUC)。gate_pass=True で exit 0・False で exit 2 (fail-loud)。
- **鑑別ログ**: baseline 実測値 3つ・Phase 10 実測値 3つ・delta 3つ・BASELINE_* 参考値との乖離 WARNING（baseline_drift_warning）を記録。
- **§15.2 binning import 再利用**: CALIBRATION_CURVE_BINS / CALIBRATION_CURVE_MIN_BIN_COUNT / ODDS_BAND_EDGES / NINKI_BAND_EDGES を evaluator/segment_eval から import・再定義禁止（bit-identical）。
- **D-15 参考記録**: segment_eval.evaluate_all_segments で selected-only calibration / odds_band×p_bin を算出（gate 判定には使わない・Phase 12 EVAL-01 先行指標）。
- **`_attach_label_to_pred` helper（Rule 3 fix）**: orchestrator.train_and_predict の pred_df に label (fukusho_hit_validated) を JOIN する（run_speed_figure_stopgate::_attach_label_and_harai の label merge 部分の最小版）。
- **`_sanitize_for_json` 拡張（Rule 1 fix）**: numpy ndarray/scalar を list/Python scalar に変換（compute_metrics/evaluate_all_segments 戻り値対応）。

### `tests/model/test_data.py` 拡張（3 新テスト・8 tests GREEN 計）

- **Test: `test_phase10_derive_feature_columns_new_and_baseline_regression`** (B-2・H1-b 無言失敗 catch の核心): `_derive_feature_columns(snapshot_id='20260626-1a-opponentstrength-v1')` が 79 feature・`_derive_feature_columns(snapshot_id='20260620-1a-postreview-v2')` が 35 feature を返すことを単一テストで保証。両者が異なる集合であること（H1-b）・27 新 feature 代表（FEAT-02/03）の含有も assert。PLAN truth「baseline=79」は誤記（PROJECT decisions で postreview-v2=35 が正）・実測値で検証。
- **Test: `test_phase10_make_X_y_green_on_new_snapshot`** (B-2・H1-b): 実 snapshot の Parquet を読み・合成 label で `make_X_y` が新 snapshot_id で X.columns == FEATURE_COLUMNS 完全一致 assert GREEN を検証。snap_id 未伝播の無言失敗を直接 catch。
- **Test: `test_phase10_category_map_bit_identity_w3`** (W-3・B-3 前提): baseline_cat_map と phase10_cat_map の SHA256 hash bit-identity を assert（json.dumps(sort_keys=True) で正規化・mapping 順序に依存しない）・category key 集合の一致も念のため検査。B-3 同一 trainer 設定の前提保証。

### `reports/10-evaluation/` (live-DB SC#5 gate 実行結果・PASS)

- **`10-evaluation.{json,md}`**: gate_pass=True・baseline/phase10 実測値・delta・D-16 許容幅・BASELINE_* 参考値との乖離 WARNING・W-2/W-3 証跡・binning source・model_versions・safe_01_note を含む。
- **`candidate_score_diagnostics_{train,calib}.json`** (W-2): train/calib 窓それぞれの候補 {0.0,0.1,0.25,0.5} adjusted_score 分布統計（mean/std/min/max/p10/p50/p90 + adjusted_rank_mean/std）・0.25 canonical の妥当性証拠。0.0 vs 0.25 の rank_mean 差（train: 6.908→6.731・calib: 6.954→6.737）・score_mean 差（train: 8.307→9.933・calib: 8.371→10.124）が 0.25 canonical が 0.0 baseline と異なる分布を生成することを示す（0.25 の妥当性証拠・§11.2 聖域遵守）。

## TDD Gate Compliance

- 本 PLAN は Task 2 に `tdd="true"` を持つが・Task 2 の action は「スクリプト新規作成」で unit test でなく grep-based 静的検証 + live-DB 実行（Task 3 checkpoint）が主検証。Task 2 単体では静的検証（grep）で done・live-DB 実行は Task 3 checkpoint スコープ。
- Task 1 のテスト拡張は RED→GREEN 形式（実 snapshot の Parquet を読む回帰テスト・最初の実行で GREEN・registry 伝播の健全性直接保証）。
- 実質的な RED→GREEN 反復は Rule 1/3 fix 2件（`_attach_label_to_pred` helper・`_sanitize_for_json` 拡張）で・live-DB 実行でのみ発覚する bug を経て gate PASS に至った（memory feature-snapshot-regen-required パターン・unit test では検出困難）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking fix] `_attach_label_to_pred` helper 追加・orchestrator pred_df への label JOIN**
- **Found during:** Task 3 live-DB 実行（W-3 PASS・両モデル学習完了後・`_evaluate_gate` で `KeyError: 'fukusho_hit_validated'`）
- **Issue:** orchestrator.train_and_predict の pred_df は label (fukusho_hit_validated) を保持しない（run_speed_figure_stopgate.py L638-667 コメントに明記・todo 260626 step 1）。本 JOIN が無いと `compute_metrics` が `fukusho_hit_validated` 列を取れず KeyError。
- **Fix:** `_attach_label_to_pred(pred_df, label_joined_frame)` helper を追加・run_speed_figure_stopgate::_attach_label_and_harai の label 馬単位 merge 部分を抽出した最小版（HARAI 払戻 slot は SC#5 Brier/LogLoss/AUC 算出に不要）。race_key+umaban で merge・umaban 型統一 (Int64)・suffix 衝突解決 (CR-06)・label 欠損行 fail-loud (§19.1 聖域)。main で `train_and_predict` 呼出後に適用。
- **Files modified:** scripts/run_phase10_evaluation.py
- **Commit:** e603f90

**2. [Rule 1 - Bug fix] `_sanitize_for_json` に numpy ndarray/scalar 変換を追加**
- **Found during:** Task 3 live-DB 実行（Rule 3 fix 後・`_write_reports` で `TypeError: Object of type ndarray is not JSON serializable`）
- **Issue:** `compute_metrics` / `evaluate_all_segments` の戻り値に numpy.ndarray / numpy.scalar が含まれるため・`json.dumps(allow_nan=False)` が TypeError で失敗する。
- **Fix:** `_sanitize_for_json` を拡張・numpy.ndarray → tolist() → 再帰・numpy.integer/floating/bool_ を対応する Python 型に変換。float 判定より前に処理（isinstance 順序）。
- **Files modified:** scripts/run_phase10_evaluation.py
- **Commit:** 83428a0

### PLAN truth の誤記（実装に影響なし・文書上のメモ）

**1. PLAN truth「baseline (postreview-v2) も 79 feature」は誤記**: PLAN must_haves truths は「baseline も 79 feature」と記載するが・実測値は 35 feature（PROJECT decisions「postreview-v2 実データ値 35 が正」・Phase 9/9.1 で 35→41→52→79 と拡張された系統）。Task 1 acceptance criteria の本質（H1-b 無言失敗 catch・27 新 feature 含有・新旧 snapshot_id で別 FEATURE_COLUMNS・W-3 bit-identity）は 79/35 の組で完全達成。テスト定数（PHASE10_FEATURE_COUNT=79 / BASELINE_V10_FEATURE_COUNT=35）は実測値で検証。

**2. baseline_drift_warning の顕在化**: baseline 実測値が BASELINE_* 参考値（Phase 6 当時）と Brier+0.00324・LogLoss+0.00498・AUC-0.03522 だけ乖離。これは BT-1 split（train 2019-06..2022・test 2023）と Phase 6 split（train 2016-07..2023・test 2024-H2）の `split_periods` 違いによる trainer 設定ドリフト（Phase 6 の広い train 期間と test 2024-H2 の異なる年代分布）であって・feature ノイズ化でないことを鑑別資料として記録（B-3・§11.2 聖域）。両 snapshot 同一 trainer 設定なので delta 自体は純粋に feature 追加効果を測る。

## SAFE-01 / core value 整合性

本 PLAN は `scripts/run_phase10_evaluation.py` と `tests/model/test_data.py` のみ作成/拡張・市場 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）は一切導入せず・FEATURE_COLUMNS にも混入しない。`run_phase10_evaluation.py` は D-15 segment_eval の diagnostic 層でのみ market データを扱う想定だが・本 live-DB 実行では segment_eval が列名不一致で WARNING skip した（market データ自体は未処理・SAFE-01 完全遵守）。Phase 10 snapshot は PLAN 05 で registry derived allowlist が odds-free であることを実証済み（SAFE-01・SC#4 AST audit 対象・PLAN 07 で完全証明予定）。

W-3 bit-identity PASS は・Phase 10 が新 feature 追加のみで category mapping を変更しない設計（B-3 同一 trainer 設定の前提）を実行時に証明した。delta（Brier -0.00022 / LogLoss +0.00487 / AUC +0.00180）は純粋に 27 新 feature 追加の効果を測り・category mapping ドリフトや trainer 設定ドリフトでない（両 snapshot 同一 trainer 設定・同一 category_map hash）。

## Verification

- Task 1 verify: `uv run pytest tests/model/test_data.py -x -q -k "feature_columns or make_X_y"` → 4 passed（3 新テスト + 既存 H1-b テスト）
- test_data.py 全体: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_data.py -x -q` → 8 passed
- Task 2 verify (grep): build_training_frame=3 / load_frozen_maps=3 / feature_snapshot_id==3 / compute_candidate_score_diagnostics=8 / hash_canonical=5・全て acceptance criteria ≥ を満たす
- Task 2 verify (lint): `uv run ruff check scripts/run_phase10_evaluation.py` → All checks passed!
- Task 3 verify (live-DB SC#5 gate): `uv run python scripts/run_phase10_evaluation.py --phase10-snapshot-id 20260626-1a-opponentstrength-v1 --baseline-snapshot-id 20260620-1a-postreview-v2 --bt-split BT-1 --odds-snapshot-policy 30min_before --out-dir reports` → exit 0（gate PASS・3条件全て D-16 許容幅内）
- 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_data.py tests/features/test_race_relative.py tests/features/test_snapshot_repro.py -q` → 42 passed

### §11.2 聖域遵守

- TOLERANCE_* 定数は評価結果を見た後に変更していない（D-16・commit 履歴で事前登録値 0.002/0.005/0.005 が固定・gate PASS 後に緩和していない）。
- binning 定数（CALIBRATION_CURVE_BINS/ODDS_BAND_EDGES/NINKI_BAND_EDGES）は evaluator/segment_eval から import 再利用・再定義なし（§15.2）。
- B-3: BASELINE_* 定数（参考値）が gate 判定の delta 基準に使われていない（baseline snapshot 実測値が delta 基準・`_evaluate_gate` の `brier_delta = phase10_brier - baseline_brier` で実測値同士の差）。
- W-2: 候補選定は train/calib 窓内のみ（test 窓 rank はすり替えない・`_compute_w2_diagnostics` が train_mask/calib_mask で split_periods 由来の行抽出のみ）。
- W-3: category_map bit-identity が実行時保証（`hash_canonical(baseline_cat_map) == hash_canonical(phase10_cat_map)`・B-3 同一 trainer 設定の前提）。

## Deferred Issues

**1. D-15 segment_eval の列名不一致**: `evaluate_all_segments` が `y_true_col='fukusho_hit'` を期待するが・pred_df の正しい列名は `fukusho_hit_validated`（label JOIN 済み）。本 live-DB 実行では WARNING skip で gate 継続（D-15 は参考記録・Phase 12 EVAL-01 先行指標・gate 判定には使わない）。Phase 12 EVAL-01 計画時に `evaluate_all_segments` の呼出契約（列名 alias または pred_df 側での rename）を整理する候補。

**2. BT-1 split と Phase 6 split の `split_periods` 違いによる baseline 実測値ドリフト**: baseline_drift_warning（Brier+0.00324・AUC-0.03522）は BT-1 split（train 2019-06..2022・test 2023）と Phase 6 split（train 2016-07..2023・test 2024-H2）の違いによる trainer 設定ドリフト。本 PLAN では両 snapshot 同一 trainer 設定（B-3）なので delta 自体は純粋に feature 追加効果を測るが・BASELINE_* 参考値（Phase 6 当時）との直接比較は split_periods 違いを含むため鑑別 WARNING として記録するにとどまる。Phase 11 SC#2 で再評価する際は・BASELINE_* 定数を BT-1 split での再評価値に更新する候補（後知恵すり替えでなく・事前登録値の整理）。

## Known Stubs

なし。本 PLAN は SC#5 非劣化 gate が D-16 事前登録許容幅で PASS（3条件全て成立・delta 基準は baseline snapshot 実測値）した本番評価 plan・stub なし。Phase 11（MODEL-01 レース内相対確率モデル）が本 snapshot（106 col / 79 model feature）を入力とする前提が整った。

## Self-Check: PASSED

- scripts/run_phase10_evaluation.py: FOUND
- tests/model/test_data.py: FOUND
- reports/10-evaluation/10-evaluation.json: FOUND
- reports/10-evaluation/10-evaluation.md: FOUND
- reports/10-evaluation/candidate_score_diagnostics_train.json: FOUND
- reports/10-evaluation/candidate_score_diagnostics_calib.json: FOUND
- commit f667e15 (Task 1: test_data.py 拡張): FOUND
- commit d4e14bd (Task 2: run_phase10_evaluation.py 作成): FOUND
- commit e603f90 (Rule 3 fix: _attach_label_to_pred): FOUND
- commit 83428a0 (Rule 1 fix: _sanitize_for_json numpy 拡張): FOUND
- SC#5 gate PASS (exit 0): FOUND (reports/10-evaluation/10-evaluation.json gate_pass=true)
