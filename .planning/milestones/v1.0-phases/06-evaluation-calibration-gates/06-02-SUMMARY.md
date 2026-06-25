---
phase: 06-evaluation-calibration-gates
plan: 02
subsystem: evaluation
tags: [evaluator, calibration, quantile, ece, mce, acceptance-gate, hybrid-gate, d-05, d-02, d-03]
requires:
  - Phase 4 evaluator.py（compute_metrics / _compute_calibration_max_dev(_guarded) / check_sum_p_distribution / METRIC_COLUMNS / CALIBRATION_CURVE_*）
  - Plan 06-01 Wave 0 基盤（tests/model/test_evaluator.py 事前登録指標固定化テスト・plotly/scipy 依存）
  - reports/04-eval.json（事前登録指標の実データ値: lightgbm calibration_max_dev=0.23076923... / logloss=0.47488... / brier=0.15222...）
provides:
  - src/model/evaluator.py 拡張: _compute_calibration_curve_bins / _compute_quantile_max_dev / _compute_ece / _compute_mce / check_acceptance_gate / compute_monotonicity_warn / compute_yearly_inversion_warn + METRIC_COLUMNS_EXTENDED / SUM_P_BLOCK_THRESHOLD / COMPARABLE_BASELINES 定数 + scipy.stats.spearmanr import
  - tests/model/test_evaluator.py 拡張: 新キャリブ指標の10テスト追加（Plan 06-01 の7テスト + 本 plan 10テスト = 17テスト・16 passed/1 skipped）
  - tests/model/test_evaluator_gate.py 新規: ゲート判定ロジックの13テスト（全 GREEN・DB 不要・純粋関数）
affects:
  - Plan 06-05（run_evaluation.py: check_acceptance_gate / compute_monotonicity_warn / compute_yearly_inversion_warn を呼び reports/06-evaluation.{md,json} のゲート判定 + WARN セクション生成）
  - Plan 06-03/06-04（segment_eval.py: _compute_calibration_curve_bins / _compute_ece / _compute_mce を import して再利用）
  - Phase 8（対抗的監査: 受入ゲート BLOCK 発火ロジック・condition_flags・SC#2/BLOCK 対称性の監査）
tech-stack:
  added: []
  patterns:
    - D-04 事前登録指標不変（calibration_max_dev / calibration_max_dev_guarded / METRIC_COLUMNS / CALIBRATION_CURVE_* は一切変更せず・新指標を ADDITIVE に追加・T-04-24 後知恵すり替え回避）
    - 純 NumPy bit-identical binning（np.linspace + np.digitize + np.bincount + np.clip・pandas.groupby/sort 不使用・strategy='quantile' は np.unique(np.quantile(...)) で重複 edge 削除）
    - hybrid gate AND 条件（BLOCK = baselines_all_lose AND sum_p_violation の両立・片方は WARN・REVIEW HIGH#2）
    - block_reasons / warn_reasons / condition_flags の3分離戻り値（監査性・Phase 8 対抗的監査で再現可能）
key-files:
  created:
    - tests/model/test_evaluator_gate.py
  modified:
    - src/model/evaluator.py
    - tests/model/test_evaluator.py
decisions:
  - D-guarded-skip: reports/04-eval.json に calibration_max_dev_guarded 列が不存在（C6 stale）のため test_guarded_value_pinned_to_report は skip（Plan 06-01 D-report-regen-deferred の延長・Plan 06-05 run_evaluation.py で再生成時に有効化）
  - D-spearmanr-import-task1: scipy.stats.spearmanr の import を Task 1 に含め（Plan action 通り）・Task 2 の compute_monotonicity_warn で消費（Task 1 コミット時点で一時的 F401 は Task 2 で解消）
  - D-and-condition-strict: REVIEW HIGH#2 に基づき check_acceptance_gate の BLOCK 判定を baselines_all_lose AND sum_p_violation の厳密な両立とし・片方のみは warn_reasons 記録で WARN（PATTERNS.md 実装例 lines 152-189 の OR 風記述を Plan の AND 指示で上書き）
metrics:
  duration: 約25分
  completed: 2026-06-23
  tasks: 2
  files_created: 1
  files_modified: 2
  tests_added: 23
status: complete
---

# Phase 6 Plan 02: Wave 1 評価本体（quantile_max_dev/ECE/MCE + 受入ゲート + 単調性 WARN） Summary

evaluator.py を D-05 新キャリブ指標（quantile_max_dev/ECE/MCE・純 NumPy bit-identical）と D-01/D-02 構造的 BLOCK / D-03 曖昧 WARN の受入ゲート（check_acceptance_gate・compute_monotonicity_warn・compute_yearly_inversion_warn）で拡張し・事前登録指標 calibration_max_dev（D-04・T-04-24）は一切変更せずに ADDITIVE に追加した EVAL-01/02 service 層。

## What Was Built

### Task 1: evaluator.py 拡張 — quantile_max_dev/ECE/MCE + _compute_calibration_curve_bins ヘルパー（commit 6f58d3d）

**src/model/evaluator.py 新規関数・定数（既存関数は一切変更せず）:**

| 追加要素 | 役割 | 設計根拠 |
|----------|------|----------|
| `_compute_calibration_curve_bins(y_true, y_pred, *, strategy, n_bins, min_bin_count)` | 純 NumPy binning ヘルパー・`strategy='uniform'` / `'quantile'` 切替 | 既存 `_compute_calibration_max_dev_guarded` lines 296-306 のパターン切出し・np.unique で重複 edge 削除（BL-1 離散値・Pitfall 1）・np.clip で y_pred==1.0 対処（Pitfall 2・Specialist (b)）・整列 assert（Specialist (c)） |
| `_compute_quantile_max_dev(y_true, y_pred, *, n_bins)` | quantile bin worst-case max\|dev\|・**MIN_BIN_COUNT ガードなし** | REVIEW C5: MCE（ガード付き）と定義分離・事前登録 calibration_max_dev との対比 |
| `_compute_ece(y_true, y_pred, *, strategy, n_bins)` | ECE = Σ(n_m/N)\|frac_pos - mean_pred\|（Naeini 2015・重み付け平均） | D-05 robust 指標・worst-case bin に支配されない |
| `_compute_mce(y_true, y_pred, *, strategy, n_bins, min_bin_count)` | MCE = max\|dev\|（MIN_BIN_COUNT ガード付き・worst-case） | D-05 worst-case・極小サンプル bin ノイズ除外 |
| `METRIC_COLUMNS_EXTENDED` | METRIC_COLUMNS + ["quantile_max_dev", "ece", "mce"] | D-05 新指標・事前登録 9 列は不変（別名で拡張リスト定義） |
| `SUM_P_BLOCK_THRESHOLD = 0.30` | D-02 BLOCK 条件2 閾値 | §15.2 [2.7,3.3]/[1.8,2.2] から 30% 超違反で BLOCK・REVIEW HIGH#5: 仮置き・Plan 06-05 で実データ検証 |
| `COMPARABLE_BASELINES = ("bl1", "bl4", "bl5")` | D-02 BLOCK 条件1 比較対象 | BL-2 (NaN) / BL-3 (§14.2 caveat) 除外 |

**compute_metrics 戻り値拡張:** `quantile_max_dev` / `ece` / `mce` キーを追加（既存 `calibration_max_dev` / `calibration_max_dev_guarded` / `sum_p_*` / `brier` / `logloss` / `auc` は不変・D-04）。

**imports 拡張:** `from scipy.stats import spearmanr` 追加（Task 2 の compute_monotonicity_warn で消費）。

**tests/model/test_evaluator.py テスト追加（10テスト・Plan 06-01 の7テスト + 10 = 17テスト・16 passed/1 skipped）:**

| テスト | 検証内容 | 根拠 |
|--------|----------|------|
| `test_quantile_max_dev_bit_identical` | _compute_quantile_max_dev が同一入力で同値 | 純 NumPy bit-identical（Phase 4 SC#4 延長） |
| `test_ece_weighted_average` | 手計算可能な小サンプルで Naeini 2015 定義と一致 | ECE = Σ(n_m/N)\|frac_pos - mean_pred\| |
| `test_mce_worst_case_guarded` | MIN_BIN_COUNT 未満 bin 除外後 max\|dev\| | D-05 worst-case ガード付き |
| `test_quantile_duplicate_edges_bl1` | BL-1 離散値で np.unique が重複 edge 削除 | Pitfall 1・n_bins_actual < n_bins |
| `test_compute_metrics_returns_extended_keys` | 戻り値に quantile_max_dev/ece/mce 追加 | 既存キー不変 |
| `test_uniform_max_dev_unchanged_after_extension` | reports/04-eval.json の calibration_max_dev 値が不変 | Pitfall 3・T-04-24 |
| `test_compute_calibration_curve_bins_alignment` | mean_pred/frac_pos/counts が同長 | Specialist 指摘 (c) |
| `test_guarded_value_pinned_to_report` | reports の LightGBM guarded 値と一致（**SKIP: C6 stale で guarded 列不存在**） | REVIEW C14・Plan 06-05 で再有効化 |
| `test_quantile_max_dev_unguarded_vs_mce_guarded` | quantile_max_dev（ガードなし）≠ mce（ガード付き） | REVIEW C5・定義分離 |
| `test_extended_constants` | METRIC_COLUMNS_EXTENDED / SUM_P_BLOCK_THRESHOLD / COMPARABLE_BASELINES 定数 | D-05/D-02 |

### Task 2: check_acceptance_gate + compute_monotonicity_warn + compute_yearly_inversion_warn（commit cc8eee0）

**src/model/evaluator.py 新規関数:**

| 関数 | 役割 | 設計根拠 |
|------|------|----------|
| `check_acceptance_gate(metrics_dict, sum_p_check)` | §15.2 受入ゲート判定（D-01/D-02 BLOCK / D-03 WARN） | REVIEW HIGH#2: BLOCK = baselines_all_lose AND sum_p_violation の厳密な両立・片方は warn_reasons 記録で WARN |
| `compute_monotonicity_warn(bins_dict)` | Spearman 順位相関 + bin 逆転数 | D-03 曖昧 WARN・scipy.stats.spearmanr（nan_policy='omit'）・frac_pos 長さ<2 は NaN |
| `compute_yearly_inversion_warn(year_segment_results)` | 各年 curve に compute_monotonicity_warn を適用 | D-03 年次要素・SC#2 機械的 WARN レポート化・空入力で空 dict（安全網） |

**check_acceptance_gate 戻り値（7キー・3分離）:**
- `block_triggered` (bool) / `block_reasons` (list) / `warn_reasons` (list) / `gate_verdict` ("BLOCK"|"WARN")
- `comparable_baselines` (list) / `sum_p_block_threshold` (float) / `condition_flags` ({baselines_all_lose, sum_p_violation})
- REVIEW C15: docstring に SC#2「beat all baselines」と BLOCK 条件1「baselines 全敗」の対称性注記（Phase 8 監査での解釈曖昧性排除）

**tests/model/test_evaluator_gate.py 新規（13テスト・全 GREEN・DB 不要・純粋関数）:**

| テスト | 検証内容 | 根拠 |
|--------|----------|------|
| `test_block_baselines_all_lose_AND_sum_p_ok` | baselines 全敗単独では BLOCK しない | REVIEW HIGH#2 AND 条件 |
| `test_block_sum_p_divergence_AND_baselines_ok` | sum(p) 著乖離単独では BLOCK しない | REVIEW HIGH#2 AND 条件 |
| `test_block_triggered_when_both_conditions_met` | 両条件成立時のみ BLOCK | D-02 AND 条件の忠実な実装 |
| `test_block_not_triggered_normal` | reports/04-eval.json 実データで BLOCK 発火せず | 現データ LightGBM 優位 |
| `test_bl2_bl3_excluded_from_comparable` | BL-2/BL-3 が比較対象から除外 | COMPARABLE_BASELINES |
| `test_bl1_single_loss_not_block_nor_warn` | LogLoss のみ劣る（Brier 優位）→ baselines_all_lose=False | 両方劣る必要 |
| `test_warn_monotonicity_spearman` | Spearman + bin 逆転数 | D-03 |
| `test_warn_monotonicity_short_array` | frac_pos 長さ<2 で NaN | 境界ケース |
| `test_gate_verdict_field` | gate_verdict が "BLOCK"/"WARN" のいずれか | T-06-05 |
| `test_yearly_inversion_warn_applies_monotonicity_per_year` | 各年 curve に monotonicity 適用 | D-03 年次要素 |
| `test_yearly_inversion_warn_handles_empty` | 空入力で空 dict | 安全網 |
| `test_block_reasons_vs_warn_reasons_separation` | block/warn/condition_flags の3分離 | REVIEW HIGH#2 監査性 |
| `test_audit_fields_present` | comparable_baselines / sum_p_block_threshold / condition_flags 含まれる | T-06-04/T-06-05 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] test_guarded_value_pinned_to_report の skip 対応（REVIEW C14）**
- **Found during:** Task 1（reports/04-eval.json 読込時）
- **Issue:** PLAN Task 1 Test 8（test_guarded_value_pinned_to_report）は reports/04-eval.json の LightGBM guarded 値と `_compute_calibration_max_dev_guarded` の再計算値が一致することを assert する。しかし reports/04-eval.json は Phase 4 生成時点の 8 列（C6 stale・calibration_max_dev_guarded 列不存在）。Wave 0（Plan 06-01）でも再生成されず D-report-regen-deferred で Plan 06-02 または 06-05 に委譲済み。
- **対応:** レポートに guarded 列が存在しない場合は `pytest.skip` でスキップ（Plan 06-05 run_evaluation.py でレポート再生成時に自動的に有効化）。リファクタ（`_compute_calibration_curve_bins` 切出し）時の境界処理差分が silent に漂うのを検知する目的は・レポート再生成後に達成される。現状でも test_compute_metrics_uniform_max_dev_unchanged / test_calibration_max_dev_report_value_match / test_uniform_max_dev_unchanged_after_extension で事前登録指標（unguarded）の回帰固定化は達成済み。
- **Files modified:** tests/model/test_evaluator.py（test_guarded_value_pinned_to_report に skip ロジック追加）
- **Commit:** 6f58d3d

**2. [Rule 1 - Bug] check_acceptance_gate の BLOCK 判定を PATTERNS.md 実装例（OR 風）から Plan 指示（AND 厳密）に修正**
- **Found during:** Task 2（check_acceptance_gate 実装時）
- **Issue:** 06-PATTERNS.md lines 152-189 の実装例は block_reasons に baselines 全敗と sum(p) 違反を個別に append しており・条件1 OR 条件2 で BLOCK する風に見える。しかし PLAN Task 2 action と truths は REVIEW HIGH#2 に基づき「BLOCK は D-02 AND 条件（両立）でのみ発火・片方だけでは warn_reasons 記録」と明示する。
- **対応:** PATTERNS.md 実装例を参考にしつつ・Plan の AND 条件指示を優先。`block_triggered = baselines_all_lose and sum_p_violation` の厳密な両立とし・片方のみ成立の場合は warn_reasons に記録（D-03 参考レポート）。test_block_baselines_all_lose_AND_sum_p_ok / test_block_sum_p_divergence_AND_baselines_ok / test_block_triggered_when_both_conditions_met で AND 条件を固定化。
- **Files modified:** src/model/evaluator.py（check_acceptance_gate の BLOCK 判定ロジック）
- **Commit:** cc8eee0

**3. [Rule 3 - Blocking] ruff の一時的 F401（scipy.stats.spearmanr）許容**
- **Found during:** Task 1 コミット時
- **Issue:** PLAN Task 1 action ステップ1 は imports に `from scipy.stats import spearmanr` を追加する（Task 2 の compute_monotonicity_warn で消費）。Task 1 コミット時点では spearmanr が未使用のため ruff F401 が発生。
- **対応:** Plan の指示（Task 1 で imports 拡張）に従い・Task 1 コミット時に一時的 F401 を許容（`# noqa` 付与せず）・Task 2 の compute_monotonicity_warn 実装で解消。最終状態（Task 2 コミット後）で F401 は解消済み。
- **Files modified:** なし（Task 1 → Task 2 の連続コミットで自然解消）

## Verification

- `uv run pytest tests/model/test_evaluator.py tests/model/test_evaluator_gate.py -v` → **29 passed, 1 skipped in 0.90s**
  - test_evaluator.py: 17テスト（16 passed / 1 skipped・Plan 06-01 の7テスト + Task 1 の10テスト）
  - test_evaluator_gate.py: 13テスト（全 passed・Task 2 新規）
- 事前登録指標（calibration_max_dev 実データ値 lightgbm=0.23076923076923073 / catboost=0.25789298770355484 / bl1=0.0014259639516354672）が不変（test_calibration_max_dev_report_value_match / test_uniform_max_dev_unchanged_after_extension GREEN・D-04・T-04-24）
- 新規 quantile_max_dev/ECE/MCE が純 NumPy bit-identical（test_quantile_max_dev_bit_identical / test_compute_calibration_curve_bins_alignment GREEN）
- check_acceptance_gate が D-02 AND 条件を忠実に実装（test_block_baselines_all_lose_AND_sum_p_ok / test_block_sum_p_divergence_AND_baselines_ok / test_block_triggered_when_both_conditions_met GREEN・REVIEW HIGH#2）
- BL-2/BL-3 が比較対象から除外（test_bl2_bl3_excluded_from_comparable GREEN・COMPARABLE_BASELINES）
- compute_monotonicity_warn が Spearman + bin 逆転数を返す（test_warn_monotonicity_spearman GREEN・D-03）
- ruff check: 私が追加したコードは GREEN（test_evaluator.py の E501 は Plan 06-01 由来の pre-existing・SCOPE BOUNDARY で対象外）

## Open Question #1（segment 軸）Status

Plan 06-01 で解決済み（test_segment_axis_columns.py GREEN）。本 plan は evaluator.py の純粋関数拡張のため segment 軸は直接消費せず・Plan 06-03/06-05 で segment_eval.py が `_compute_calibration_curve_bins` / `_compute_ece` / `_compute_mce` を import して再利用する。

## Self-Check: PASSED

- [x] src/model/evaluator.py に _compute_calibration_curve_bins / _compute_quantile_max_dev / _compute_ece / _compute_mce / check_acceptance_gate / compute_monotonicity_warn / compute_yearly_inversion_warn が追加される
- [x] METRIC_COLUMNS_EXTENDED / SUM_P_BLOCK_THRESHOLD=0.30 / COMPARABLE_BASELINES=("bl1","bl4","bl5") 定数が追加される
- [x] compute_metrics 戻り値に quantile_max_dev / ece / mce キーが追加される（既存キー不変）
- [x] tests/model/test_evaluator_gate.py が存在（13テスト・全 GREEN）
- [x] commit 6f58d3d 存在（Task 1）
- [x] commit cc8eee0 存在（Task 2）
- [x] reports/04-eval.json の calibration_max_dev 値が不変（test_calibration_max_dev_report_value_match GREEN）

## Self-Check Result: PASSED

検証コマンド `for f in src/model/evaluator.py tests/model/test_evaluator.py tests/model/test_evaluator_gate.py .planning/.../06-02-SUMMARY.md; do [ -f "$f" ] && echo FOUND; done` → 全て FOUND。
`git log --oneline --all | grep -q 6f58d3d` → FOUND・`grep -q cc8eee0` → FOUND。
`grep -c "^def _compute_calibration_curve_bins\|^def _compute_quantile_max_dev\|^def _compute_ece\|^def _compute_mce\|^def check_acceptance_gate\|^def compute_monotonicity_warn\|^def compute_yearly_inversion_warn" src/model/evaluator.py` → 7（全関数存在）。
