---
phase: 12
plan: 03
subsystem: evaluation/diagnostic layer (falsification + market_implied calibrator + Phase 12 WARN gate + ROI binning + slippage)
tags: [eval, falsification, calibration-gate, wave3, eval-01, eval-02, safe-01, statsmodels, byte-reproducible]
requires:
  - "Phase 12 Plan 01 (compute_p_lower_conformal_shrinkage + statsmodels==0.14.6 + race_relative constants)"
  - "Phase 12 Plan 02 (orchestrator p_lower integration + EV layer p_col swap)"
provides:
  - "src/eval/falsification.py: run_falsification_test (race_id clustered SE・Holm 補正・logit clipping・事前登録評価回帰)"
  - "src/eval/falsification.py: fit_market_implied_calibrator (train/calib 2-window・FrozenEstimator・C-12-03-4)"
  - "src/eval/falsification.py: write_falsification_spec ヘルパー (byte-reproducible・theta/q_shrink.json idiom)"
  - "src/eval/falsification.py: constants block 集約 (C-12-04-3・C3-12-03-1・Q_LEVEL_SHRINKAGE/Q_LEVEL_FALSIFICATION/HOLM_ALPHA/LOGIT_CLIP_EPS/ODDS_CLIP_MIN/MAX/MARKET_CALIB_SAMPLE_THRESHOLD/PHASE12_*_THRESHOLD)"
  - "src/model/evaluator.py: check_phase12_warn_gate 分離関数 (SC#4 WARN gate・§15.2 gate 完全不変・C-12-03-2 選択 A)"
  - "src/model/segment_eval.py: compute_roi_by_bin 別関数 (EV-decile/disagreement ROI・evaluate_segment_axis 不変・C-12-03-3)"
  - "src/ev/refund_accounting.py: compute_snapshot_final_slippage (payout_amount 版 + row ベース版・C-12-03-5)"
affects:
  - "Plan 04: scripts/run_phase12_evaluation.py が falsification/calibrator/WARN gate/binning/slippage/constants を import して統合"
  - "Plan 05: 対抗的監査 test_audit_p_lower_falsification.py が SAFE-01 AST 拡張で本 plan の src/eval/ を含む"
tech_stack:
  added: []
  patterns:
    - "事前登録評価回帰 (pre-registered evaluation regression): run_falsification_test 仕様を test 窓評価前に write_falsification_spec で事前書き出し (§11.2 聖域の threshold dredging 監査)"
    - "race_id clustered SE: statsmodels Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id}) (Pitfall 4 正しい API・GitHub #6287)"
    - "Holm 補正: multipletests(method='holm') は bin/odds_band サブ解析のみ (主検定 model_p 単一係数は Holm 不要・D-05)"
    - "logit clipping LOGIT_CLIP_EPS=1e-6 (Pitfall 6・race_relative.P_CAL_CLIP_EPSILON と同一契約・inf 回避)"
    - "[C-12-03-4] base=train・calibrator=calib 2-window 分離: FrozenEstimator + CalibratedClassifierCV (sklearn 1.9.0 prefit idiom・utils/calibrator.py L12-15 disjoint 注記)"
    - "[C-12-03-2 選択 A] §15.2 gate と Phase 12 WARN gate の完全分離 (check_phase12_warn_gate・D-06 違反リスク最小)"
    - "[C-12-03-3] evaluate_segment_axis (calibration curve 用 API) と compute_roi_by_bin (ROI 集計) の API 分離 (bit-identical binning 契約保護)"
    - "[C-12-03-5] row ベース版 + payout_amount 受け取り版の 2 種類 signature で slot lookup 二重/欠落回避"
    - "constants block 集約: Phase 12 定数を falsification.py に一元化・重複定義回避 (Phase 11 idiom 踏襲)"
    - "silent fallback 禁止: statsmodels ConvergenceWarning・groups 長不一致は RuntimeError (Shared Pattern 4)"
    - "SAFE-01-ALLOW マーカー: odds/market_implied/model_p 引数の docstring に feature 構築経路からの切り離しを明示 (compute_overprediction_penalty idiom)"
key_files:
  created:
    - "src/eval/__init__.py (新規・空パッケージ)"
    - "src/eval/falsification.py (新規・run_falsification_test + fit_market_implied_calibrator + write_falsification_spec + constants block + logit_clip)"
    - "tests/evaluation/__init__.py (新規・空パッケージ)"
    - "tests/evaluation/test_falsification.py (新規・EVAL-02 unit・23 テスト)"
    - "tests/evaluation/test_extended_metrics.py (新規・EVAL-01 unit・14 テスト)"
    - "tests/model/test_evaluator_phase12_gate.py (新規・SC#4 WARN gate unit・14 テスト)"
  modified:
    - "src/model/evaluator.py (check_phase12_warn_gate 分離関数追加・check_acceptance_gate は完全不変)"
    - "src/model/segment_eval.py (compute_roi_by_bin 別関数追加・evaluate_segment_axis は不変・__all__ 拡張)"
    - "src/ev/refund_accounting.py (compute_snapshot_final_slippage + compute_snapshot_final_slippage_from_row 追加)"
decisions:
  - "[C-12-03-1 HIGH] run_falsification_test docstring は「pre-registered evaluation regression fitted on the test window」と正確に表現・旧来の不正確な否定表現「学習しない」は src/eval/falsification.py で 0 件 (grep -c == 0)"
  - "[C-12-03-2 HIGH 選択 A・推奨] §15.2 gate と Phase 12 WARN gate を完全分離: check_acceptance_gate signature 完全不変・check_phase12_warn_gate 分離関数で SC#4 WARN gate を提供 (D-06 違反リスク最小)"
  - "[C-12-03-3 MEDIUM] EV-decile/disagreement ROI は evaluate_segment_axis (calibration curve 用) でなく compute_roi_by_bin 別関数・binning は pd.qcut(duplicates='drop') のみ"
  - "[C-12-03-4 MEDIUM] fit_market_implied_calibrator は base=train・calibrator=calib の 2-window 分離 (FrozenEstimator・同一 calib slice で二重 fit しない)"
  - "[C-12-03-5 MEDIUM] compute_snapshot_final_slippage は row ベース版 (_lookup_payfukusyo_pay を呼ぶ) と payout_amount 受け取り版の 2 種類 (slot lookup 二重/欠落回避)"
  - "[C-12-04-3 / C3-12-03-1] Phase 12 定数を falsification.py constants block に集約 (evaluator/segment_eval/refund_accounting/run_phase12_evaluation は import)・Q_LEVEL_SHRINKAGE=0.90 を追加 (C3-12-03-1 producer/consumer 整合)"
  - "verdict='feature_gap' (model_p pvalue<α) / 'structural_limit' (>=α) は過度な保証主張でない (D-05・D-01 修正文・market 条件付き residual の α=0.05 事前登録検出)"
  - "Phase 12 WARN gate は BLOCK でなく WARN (D-06・Phase 12 は切替判断材料フェーズ・v1.0 の 4 倍過大を catch する gate)"
metrics:
  duration: 45min
  completed: "2026-06-27"
  tasks: 2
  files: 9
  tests_added: 51
status: complete
---

# Phase 12 Plan 03: src/eval/falsification.py 新規 + evaluator WARN gate + segment_eval ROI + refund_accounting slippage Summary

Phase 12 Wave 3: Plan 01/02 の基盤 (statsmodels==0.14.6・`compute_p_lower_conformal_shrinkage`・orchestrator p_lower 生成・EV 層 p_col 切替) を消費し・Phase 12 の**評価・診断専用層**を構築した。(1) `src/eval/falsification.py` (新規) で事前登録評価回帰 `logit(outcome) ~ logit(market_implied) + logit(model_p)` の race_id clustered SE ロジット回帰 (D-05・EVAL-02) と `market_implied` 再校正 (D-04・train/calib 2-window) を提供し、(2) `evaluator.check_phase12_warn_gate` 分離関数 (C-12-03-2 選択 A) で Phase 12 専用 WARN gate (§15.2 gate 完全不変・D-06)、(3) `segment_eval.compute_roi_by_bin` 別関数 (C-12-03-3) で EV-decile/disagreement ROI、(4) `refund_accounting.compute_snapshot_final_slippage` 2 種類 (C-12-03-5) で snapshot→final payout slippage を整えた。聖域 (§11.2 test 窓・SAFE-01 odds proxy 排除・§15.2 事前登録指標不変・byte-reproducible) を保った。

## What Was Built

### Task 1: src/eval/falsification.py 新規 (run_falsification_test + fit_market_implied_calibrator・statsmodels clustered SE・§11.2 聖域)

- **`run_falsification_test(y_outcome_test, market_implied_test, model_p_test, race_id_test, *, field_size_test=None, odds_band_test=None, holm_alpha=HOLM_ALPHA, alpha=Q_LEVEL_FALSIFICATION) -> dict`** を実装。`logit(outcome) ~ logit(market_implied) + logit(model_p) [+ field_size]` のロジット回帰を `statsmodels.Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id_test}, disp=0, maxiter=200)` で fit する (**Pitfall 4 正しい API**・`groups=` 直接渡しは error・GitHub #6287)。
- **verdict**: `model_p_pvalue < α` → `'feature_gap'` (特徴量不足候補・市場 residual が残る) / `>= α` → `'structural_limit'` (core value 維持での黒字化棄却候補・market 係数が model を包摂) (D-05・EVAL-02・鏡像 D-01 修正文)。verdict は「モデルが市場を打つ保証」でなく・α=0.05 で market 条件付きでも model_p に residual が観測されたという正直な統計的所見。
- **Holm 補正** (`multipletests method='holm'`): bin/odds_band サブ解析のみ (主検定 model_p 単一係数は Holm 不要・D-05)。odds_band サブ解析は `_odds_band` (segment_eval import 再利用・codex HIGH#2 bit-identical) で 4 band に分け・各 band で model_p pvalue を計算し Holm 補正。
- **[C-12-03-1 HIGH] 事前登録評価回帰・正確な表現**: docstring は「**事前登録評価回帰 (pre-registered evaluation regression) を test 窓に fit する最終検定**」と正確に表現。旧来の不正確な否定表現「学習しない」系の曖昧な語は `src/eval/falsification.py` で 0 件 (`grep -c '学習しない' == 0`・Test 2 検証)。回帰仕様は `write_falsification_spec` ヘルパーで `reports/12-evaluation/falsification-spec.json` として byte-reproducible (`sort_keys=True, ensure_ascii=False, allow_nan=False`) に書き出し可能 (theta/q_shrink.json 事前書き出し idiom・§11.2 聖域の threshold dredging 監査)。**実際の書き出し実行は Plan 04 run_phase12_evaluation.py が test 窓評価前に行う**。
- **`fit_market_implied_calibrator(odds_train, y_train, odds_calib, y_calib, *, calib_sample_size) -> CalibratedClassifierCV`** を実装。D-04: 1/odds を outcome に calibration (isotonic/sigmoid) し・overround・FLB・複勝プール歪みを除去した「真の市場暗示確率」を構築。
- **[C-12-03-4 MEDIUM] base/calibrator 2-window 分離**: base (LogisticRegression) を `odds_train`/`y_train` で fit し・calibrator (CalibratedClassifierCV) を `odds_calib`/`y_calib` で fit する。`FrozenEstimator` で base を凍結してから `CalibratedClassifierCV` に渡すことで・calibrator の fit が base を再 fit しないことを構造的保証 (sklearn 1.9.0 prefit idiom・utils/calibrator.py L12-15 disjoint 注記・Pitfall 5 過学習リスク低減)。シグネチャは train/calib の 2-window (test 窓 outcome 系引数なし・§11.2 聖域・Shared Pattern 6・Test 1 検証)。
- **isotonic vs sigmoid 切替** (Pitfall 5・sklearn docs): `calib_sample_size >= MARKET_CALIB_SAMPLE_THRESHOLD=1000` → `method='isotonic'` / `< 1000` → `method='sigmoid'`。
- **`logit_clip(p, eps=LOGIT_CLIP_EPS)` helper**: `np.clip(p, eps, 1-eps)` してから `log(p/(1-p))` を計算。p=0/p=1 でも ±13.8 範囲 (Pitfall 6 inf 回避・race_relative.P_CAL_CLIP_EPSILON と同一契約)。
- **[C-12-04-3 / C3-12-03-1] constants block 集約**: 本モジュール (falsification.py) に Phase 12 事前登録定数を一元化。`Q_LEVEL_SHRINKAGE: float = 0.90` (q_shrink 用下側信頼水準・D-02・§11.2 聖域・Plan 04 が import・**C3-12-03-1 で Plan 03 constants block に追加**・Plan 04 との producer/consumer 整合)・`Q_LEVEL_FALSIFICATION = 0.05` (α・主検定)・`HOLM_ALPHA = 0.05` (bin/odds_band サブ解析)・`LOGIT_CLIP_EPS = 1e-6` (Pitfall 6)・`ODDS_CLIP_MIN = 1.0` / `ODDS_CLIP_MAX = 100.0` (D-05 (c))・`MARKET_CALIB_SAMPLE_THRESHOLD = 1000` (Pitfall 5)・`PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD = 0.10` / `PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD = 0.15` (evaluator と共有)。evaluator.py / segment_eval.py / refund_accounting.py / scripts/run_phase12_evaluation.py (Plan 04) は本 constants block から import する (Phase 11 idiom・重複定義回避・閾値 drift 防止・§19.1)。
- **fail-loud (Shared Pattern 4)**: statsmodels ConvergenceWarning・groups 配列長不一致は RuntimeError (silent fallback 禁止・`warnings.catch_warnings()` + `simplefilter('error')` + RuntimeError wrap・Test 9 検証)。
- **SAFE-01-ALLOW マーカー**: `fit_market_implied_calibrator` / `run_falsification_test` の docstring に `SAFE-01-ALLOW: odds / market_implied / model_p` マーカーを明示 (compute_overprediction_penalty idiom・feature 構築経路からの切り離し機械保証)。本モジュールは FEATURE_COLUMNS / build_training_frame / load_feature_matrix を import しない (Test 8 AST 検証・0 violations)。

### Task 2: evaluator WARN gate 拡張 + segment_eval ROI binning + refund_accounting slippage

- **[C-12-03-2 HIGH 選択 A・推奨] `check_phase12_warn_gate(*, selected_only_calib_max_dev, odds_band_calib_max_dev, selected_only_threshold=None, odds_band_threshold=None) -> dict`** を `src/model/evaluator.py` に分離関数として追加。`check_acceptance_gate` (§15.2 gate) の signature・return dict は**完全不変** (`inspect.signature` params == `['metrics_dict', 'sum_p_check']`・Test 1 検証)。§15.2 gate return dict に Phase 12 専用 keys (`phase12_warn_triggered` 等) は混入しない (Test 3 検証)。呼出側 (Plan 04 `run_phase12_evaluation.py`) が `check_acceptance_gate` と `check_phase12_warn_gate` を段階的に呼び・両結果を report に併載する想定。
- **Phase 12 WARN gate**: (a) `selected_only_calib_max_dev > PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD` (0.10) → 投票層過大予測 WARN・(b) 各 odds_band で `conditional calib_max_dev > PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD` (0.15) → 該当 band の WARN。**BLOCK でなく WARN** (D-06・`phase12_block_triggered` は常に False・Test 4 検証)。band 順序は `ODDS_BAND_LABELS` に従う (決定論的・bit-identical・codex HIGH#2)。
- **[C-12-04-3 / C2-12-03-4] threshold の遅延 import**: `selected_only_threshold` / `odds_band_threshold` の default 値は falsification.py constants block から関数内 import する (循環参照回避: `src.eval.falsification → src.model.segment_eval → src.model.evaluator` chain)。呼出側が明示的に threshold を渡せば import 発生しない。evaluator.py での再定義 (代入) はない (Test 7 AST 検証)。
- **byte-reproducible** (Test 5): 同一入力で 2 回呼出しると完全同一の dict を返す (決定論的)。
- **[C-12-03-3 MEDIUM] `compute_roi_by_bin(df, *, bin_col, n_bins=10) -> pd.DataFrame`** を `src/model/segment_eval.py` に別関数として追加。EV-decile (`pd.qcut(EV_lower, 10, duplicates='drop')`)・model-market disagreement (`pd.qcut(|logit(model_p) - logit(market_implied)|, 5, duplicates='drop')`・logit_clip は falsification と同一契約 LOGIT_CLIP_EPS=1e-6) の binning で各 bin の `recovery_rate = sum(payout_amount)/sum(effective_stake)`・`profit_loss = sum(profit)`・`hit_rate = mean(fukusho_hit)` を計算 (compute_backtest_metrics の group-by 適用と同等)。`evaluate_segment_axis` (calibration curve 用 API・C-12-03-3 契約保護) は**完全不変** (`inspect.signature` に `bin_col` 引数なし・Test 4 検証)。binning は `pd.qcut(duplicates='drop')` のみ (独自 binning 禁止・codex HIGH#2)。D-07: gate 化しない・switch_recommendation (D-09) 入力 + 報告のみ。
- **[C-12-03-5 MEDIUM] `compute_snapshot_final_slippage` 2 種類** を `src/ev/refund_accounting.py` に追加 (D-07):
  - **(1) `compute_snapshot_final_slippage_from_row(row, fuku_odds_lower) -> float`** (row ベース版): 内部で `_lookup_payfukusyo_pay(row)` を呼んで slot を解決し・`compute_snapshot_final_slippage(payout_amount=...)` に渡す。
  - **(2) `compute_snapshot_final_slippage(*, payout_amount, fuku_odds_lower) -> float`** (payout_amount 受け取り版): 呼出側が `_lookup_payfukusyo_pay` 等で slot 解決済みの `payout_amount` を渡す想定。
  - 測定式 (CONTEXT Claude's Discretion 事前登録): `payout/100 - fuku_odds_lower` (100 円あたり payout を倍率単位に揃える)。docstring で「slot lookup は (1) が自動で行う・(2) は呼出側が解決済みの値を渡す・二重 slot lookup を避けるためどちらかを使う」を明示 (silent バグ回避・C-12-03-5)。NaN 伝播 (payout=0 no_bet や odds=NaN) は呼出側で filter する想定・関数は NaN をそのまま返す (silent fallback 禁止・Shared Pattern 4)。
- **SAFE-01**: evaluator / segment_eval / refund_accounting の Phase 12 拡張は FEATURE_COLUMNS / build_training_frame / load_feature_matrix を import しない (Test 6 AST 検証・0 violations)。evaluation 層は odds/market_implied を消費するが feature 構築経路から切り離されている (層分離・domain-analysis §5)。

## Tests Added

### tests/evaluation/test_falsification.py (23 tests・KEIBA_SKIP_DB_TESTS=1 GREEN)

- `test_fit_market_implied_calibrator_signature_no_test_outcome` (§11.2 聖域・シグネチャ検証)
- `test_run_falsification_test_docstring_precise_language` ([C-12-03-1 HIGH] docstring 正確な表現)
- `test_run_falsification_test_no_imprecise_negation_in_source` ([C-12-03-1 HIGH] 曖昧否定表現 0 件)
- `test_run_falsification_test_uses_clustered_se_returns_verdict` (clustered SE・verdict)
- `test_run_falsification_test_clustered_se_source_uses_cov_kwds` (Pitfall 4 ソース検証)
- `test_verdict_feature_gap_when_model_p_significant` (D-05 feature_gap)
- `test_verdict_structural_limit_when_model_p_not_significant` (D-05 structural_limit)
- `test_sub_analyses_holm_correction` (Holm 補正・odds_band サブ解析)
- `test_holm_alpha_default_source` (HOLM_ALPHA=0.05 事前登録)
- `test_logit_clip_helper_bounds` (LOGIT_CLIP_EPS=1e-6・Pitfall 6)
- `test_run_falsification_test_with_edge_probabilities_no_inf` (端値 inf 回避)
- `test_fit_market_implied_calibrator_isotonic_when_large_sample` (Pitfall 5 isotonic・≥1000)
- `test_fit_market_implied_calibrator_sigmoid_when_small_sample` (Pitfall 5 sigmoid・<1000)
- `test_falsification_no_feature_pipeline_import` (SAFE-01 AST 検証)
- `test_market_implied_args_have_safe01_allow_marker` (SAFE-01-ALLOW マーカー)
- `test_run_falsification_test_fail_loud_on_convergence_warning` (Shared Pattern 4・ソース検証)
- `test_run_falsification_test_groups_length_mismatch_fail_loud` (groups 長不一致 RuntimeError)
- `test_fit_market_implied_calibrator_two_window_separation` ([C-12-03-4] 2-window 分離)
- `test_fit_market_implied_calibrator_source_uses_frozen_estimator` ([C-12-03-4] sklearn 1.9.0 prefit idiom)
- `test_write_falsification_spec_byte_reproducible` ([C-12-03-1 HIGH] byte-reproducible)
- `test_write_falsification_spec_contains_pre_registered_fields` ([C-12-03-1 HIGH] 事前登録仕様)
- `test_write_falsification_spec_allow_nan_false_strict` (RFC 8259 strict)
- `test_constants_block_aggregated_in_falsification_module` (C-12-04-3・C3-12-03-1 集約)

### tests/evaluation/test_extended_metrics.py (14 tests・KEIBA_SKIP_DB_TESTS=1 GREEN)

- `test_compute_roi_by_bin_exists_in_segment_eval` ([C-12-03-3] 別関数存在)
- `test_evaluate_segment_axis_signature_unchanged` ([C-12-03-3] 既存 API 不変)
- `test_compute_roi_by_bin_ev_decile_deterministic` (bit-identical)
- `test_compute_roi_by_bin_contains_recovery_rate_profit_hit_rate` (集計契約)
- `test_compute_roi_by_bin_disagreement_logit_clip` (disagreement ROI・logit_clip)
- `test_compute_roi_by_bin_uses_odds_band_no_custom_binning` (pd.qcut duplicates='drop')
- `test_compute_snapshot_final_slippage_payout_amount_version_exists` ([C-12-03-5])
- `test_compute_snapshot_final_slippage_from_row_version_exists` ([C-12-03-5] row 版)
- `test_compute_snapshot_final_slippage_formula_payout_amount` (D-07 測定式)
- `test_compute_snapshot_final_slippage_formula_negative` (負値)
- `test_compute_snapshot_final_slippage_from_row_uses_lookup` (_lookup_payfukusyo_pay 経路)
- `test_compute_snapshot_final_slippage_from_row_no_hit_returns_nan_like` (不的中 slot lookup=0)
- `test_compute_snapshot_final_slippage_docstring_explains_two_versions` (二重 slot lookup 回避 docstring)
- `test_segment_eval_no_feature_pipeline_import` / `test_refund_accounting_no_feature_pipeline_import` (SAFE-01 AST)
- `test_odds_band_edges_unchanged` (codex HIGH#2 bit-identical)

### tests/model/test_evaluator_phase12_gate.py (14 tests・KEIBA_SKIP_DB_TESTS=1 GREEN)

- `test_check_acceptance_gate_signature_unchanged` ([C-12-03-2 HIGH] signature 不変)
- `test_check_acceptance_gate_block_unchanged_on_identical_input` (§15.2 gate regression)
- `test_check_acceptance_gate_return_keys_no_phase12_keys` (D-06・Phase 12 keys 混入なし)
- `test_check_phase12_warn_gate_exists` ([C-12-03-2 選択 A] 分離関数)
- `test_check_phase12_warn_gate_selected_only_warn` (selected-only WARN)
- `test_check_phase12_warn_gate_selected_only_pass_when_below_threshold` (threshold 以下 PASS)
- `test_check_phase12_warn_gate_odds_band_warn` (odds-band WARN)
- `test_check_phase12_warn_gate_odds_band_partial_dict` (一部 band 欠損)
- `test_phase12_warn_gate_never_blocks` (D-06・BLOCK でなく WARN)
- `test_check_phase12_warn_gate_byte_reproducible` (deterministic)
- `test_evaluator_no_feature_pipeline_import` (SAFE-01 AST)
- `test_evaluator_imports_phase12_thresholds_from_falsification` (C-12-04-3 重複定義回避)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] isotonic 単調性テストの確率軸が逆順だった**
- **Found during:** Task 1 GREEN 実行時・`test_fit_market_implied_calibrator_isotonic_when_large_sample`
- **Issue:** `isotonic` calibration curve は base 確率 (1/odds) の昇順で単調非減少になるが・初期テストでは odds 昇順 (1/odds 降順) で `predict_proba` を呼び・単調性が逆に見えた。
- **Fix:** odds 降順 grid (= 1/odds 昇順) を作って `predict_proba` を呼ぶようテストを修正。実装・機能は不変 (calibrator の振る舞いは正しい)。
- **Files modified:** tests/evaluation/test_falsification.py
- **Commit:** ef80cac (Task 1 GREEN commit に取り込み)

**2. [Rule 1 - Bug] docstring に「再学習しない」という曖昧否定表現が残存**
- **Found during:** Task 1 GREEN 実行時・`test_run_falsification_test_no_imprecise_negation_in_source`
- **Issue:** `fit_market_implied_calibrator` docstring / コメントで「calibrator.fit が base を再学習しない」という表現を使ったが・これは [C-12-03-1 HIGH] が削除を指示した「学習しない」系の曖昧否定表現に該当した。
- **Fix:** 「base を再 fit しない」という precise 表現に置換 (2 箇所)。C-12-03-4 2-window 分離の意味は不変 (FrozenEstimator で base を凍結)。
- **Files modified:** src/eval/falsification.py (docstring + コメント)
- **Commit:** ef80cac (Task 1 GREEN commit に取り込み)

None - plan executed exactly as written (機能面)・上記はテスト・docstring 表記上の auto-fix (Rule 1)。

## Known Stubs

None - 本 plan は evaluation・診断層の関数提供が目的で・実装は完了 (stub なし)。Plan 04 `run_phase12_evaluation.py` が本 plan の関数を呼び出して統合する。

## Threat Flags

None - 本 plan のファイルは `<threat_model>` の T-12-11..T-12-17 を全て mitigate 済み。新規に脅威面を導入していない。

- T-12-11 mitigate: `fit_market_implied_calibrator` シグネチャが `{odds_train, y_train, odds_calib, y_calib, calib_sample_size}` の train/calib 2-window (test 窓 outcome 系引数なし・Test 1)。
- T-12-12 mitigate: `run_falsification_test` は予測モデル `p` の再学習を行わない (事前登録評価回帰を test 窓に fit する最終検定・C-12-03-1 docstring + Test 2)。
- T-12-13 mitigate: falsification.py / evaluator.py / segment_eval.py / refund_accounting.py は FEATURE_COLUMNS 構築経路を import しない (SAFE-01-ALLOW マーカー + AST 検証・Test 8/Task 2 Test 6)。
- T-12-14 mitigate: `check_acceptance_gate` の block_reasons/block_triggered は §15.2 gate のまま一切触らない (Test 1/2/3 regression)。
- T-12-15 mitigate: verdict feature_gap/structural_limit は過度な保証主張でない (docstring に α=0.05 事前登録・Holm 補正・clustered SE で race 内相関統制を明記・D-05/D-01 修正文)。
- T-12-16 mitigate: `compute_roi_by_bin` は pd.qcut(duplicates='drop') のみ (codex HIGH#2・独自 binning 禁止・Test 4 検証)。
- T-12-17 mitigate: `cov_kwds={'groups': race_id_array}` が正しい API (Pitfall 4・Test 3 ソース検証)。

## Sanctuaries Honored

- **§11.2 test 窓聖域**: `fit_market_implied_calibrator` は train/calib 窓のみで fit・test 窓 outcome 系引数を取らない (Shared Pattern 6・シグネチャ検証・Test 1)。`run_falsification_test` は事前登録評価回帰を test 窓に fit する最終検定 (予測モデル `p` の再学習は行わない・C-12-03-1 docstring)。回帰仕様は `write_falsification_spec` で事前書き出し可能 (theta/q_shrink.json idiom・threshold dredging 監査・Plan 04 が test 窓評価前に実行)。
- **SAFE-01 odds proxy 排除**: falsification.py / evaluator.py / segment_eval.py / refund_accounting.py は FEATURE_COLUMNS / build_training_frame / load_feature_matrix 構築経路を import しない (AST 検証・0 violations)。odds/market_implied/model_p 引数は SAFE-01-ALLOW マーカーで evaluation 専用層の境界を明示 (compute_overprediction_penalty idiom)。
- **§15.2 事前登録指標不変 (D-06)**: `check_acceptance_gate` の signature・return dict・block_reasons/block_triggered は §15.2 gate のまま完全不変 (regression test・Test 1/2/3)。Phase 12 WARN gate は分離関数 `check_phase12_warn_gate` で提供 (選択 A・推奨)・BLOCK でなく WARN (`phase12_block_triggered` は常に False・Test 4)。
- **byte-reproducible §19.1**: `write_falsification_spec` は `sort_keys=True, ensure_ascii=False, allow_nan=False` で byte-reproducible (Test 11)。`compute_roi_by_bin` は 2 回呼出で bit-identical (pd.qcut は決定論的・Test 4)。`check_phase12_warn_gate` は deterministic (Test 5)。statsmodels==0.14.6 厳密固定 (Plan 01・uv.lock 反映済)。
- **C-12-03-4 2-window 分離**: `fit_market_implied_calibrator` は base (LogisticRegression) を train 窓・calibrator (CalibratedClassifierCV) を calib 窓で fit (FrozenEstimator・sklearn 1.9.0 prefit idiom・utils/calibrator.py L12-15 disjoint 注記・Pitfall 5 過学習リスク低減・Test 10 検証)。
- **C-12-04-3 / C3-12-03-1 constants 集約**: Phase 12 定数を falsification.py constants block に一元化・evaluator.py / segment_eval.py / refund_accounting.py は import (重複定義回避)。`Q_LEVEL_SHRINKAGE=0.90` は C3-12-03-1 で Plan 03 constants block に追加済み (commit 4fb64db)・Plan 04 の `from src.eval.falsification import Q_LEVEL_SHRINKAGE` が解決可能 (producer/consumer 整合)。
- **silent fallback 禁止 (Shared Pattern 4)**: statsmodels ConvergenceWarning・groups 長不一致は RuntimeError (Test 9)。`compute_snapshot_final_slippage` は NaN をそのまま返す (呼出側で filter・0/100 - odds 等の計算結果をそのまま返すことで呼出側が filter 条件を明示することを強要)。
- **Pitfall 4 (cov_kwds API)**: `Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id_test})` が正しい API・`groups=` 直接渡しは error (GitHub #6287・Test 3 ソース検証)。
- **Pitfall 5 (isotonic 1000 rule)**: `calib_sample_size >= 1000` で isotonic / `< 1000` で sigmoid (sklearn docs・Test 7)。
- **Pitfall 6 (logit clipping)**: `LOGIT_CLIP_EPS=1e-6` で `np.clip(p, eps, 1-eps)` してから logit (race_relative.P_CAL_CLIP_EPSILON と同一契約・Test 6)。
- **循環参照回避**: `src.eval.falsification → src.model.segment_eval → src.model.evaluator` chain があるため・evaluator.py から falsification.py constants への import は関数内 (遅延 import) で実装 (C-12-04-3 集約を維持しつつ循環参照を回避)。

## Self-Check: PASSED

### 作成ファイルの存在確認

- FOUND: src/eval/__init__.py
- FOUND: src/eval/falsification.py
- FOUND: tests/evaluation/__init__.py
- FOUND: tests/evaluation/test_falsification.py
- FOUND: tests/evaluation/test_extended_metrics.py
- FOUND: tests/model/test_evaluator_phase12_gate.py

### コミットの存在確認

- FOUND: 1ad7619 (test(12-03): add failing test for src/eval/falsification.py (EVAL-02 RED))
- FOUND: ef80cac (feat(12-03): src/eval/falsification.py 事前登録評価回帰 + market_implied 再校正 (EVAL-02 GREEN))
- FOUND: 71c24b2 (test(12-03): add failing tests for Phase 12 WARN gate + ROI binning + slippage (RED))
- FOUND: 39598c8 (feat(12-03): Phase 12 WARN gate + ROI binning + slippage (EVAL-01/SAFE-01 GREEN))

### done criteria grep 検証

- `grep -c "pre-registered evaluation regression\|事前登録評価回帰" src/eval/falsification.py` == 9 (>= 1) ✓
- `grep -c "学習しない" src/eval/falsification.py` == 0 ([C-12-03-1 HIGH]) ✓
- `inspect.signature(fit_market_implied_calibrator).parameters` == {odds_train, y_train, odds_calib, y_calib, calib_sample_size} (test 窓 outcome 系なし) ✓
- `inspect.signature(check_acceptance_gate).parameters` == [metrics_dict, sum_p_check] (§15.2 不変) ✓
- `hasattr(evaluator, 'check_phase12_warn_gate')` == True (選択 A) ✓
- `inspect.signature(evaluate_segment_axis).parameters` に bin_col なし (C-12-03-3・calibration curve 用 API 不変) ✓
- `grep -c "def compute_roi_by_bin" src/model/segment_eval.py` == 1 ✓
- `grep -n "^def compute_snapshot_final_slippage" src/ev/refund_accounting.py` == L195 (payout_amount 版) + L233 (row 版) ✓
- AST 検証: falsification/evaluator/segment_eval/refund_accounting の FEATURE_COLUMNS/build_training_frame/load_feature_matrix import 0 violations (SAFE-01) ✓
- AST 検証: evaluator.py の PHASE12_*_THRESHOLD 再定義 0 件 (C-12-04-3 重複定義回避) ✓
- KEIBA_SKIP_DB_TESTS=1 full suite: 708 passed, 48 skipped (regression なし) ✓
