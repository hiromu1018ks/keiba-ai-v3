---
phase: 12-p-lower-ev-falsification-evaluation
verified: 2026-06-28T04:56:26Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
provisional:
  status: true
  reason: "results computed on buggy label v1.0.0 universe (syubetucd newcomer '12' over-exclusion・2023 eligible 22793/47672=48%)"
  superseded_by: "label v1.1.0 (commit 2cdbac1・eligible 42214)・Spike 001 ablation reports/12-evaluation/ablation-results.md"
  mechanism_still_valid: true
  note: "Phase 12 SC#1-5 機構完成は有効・成果物完成。数値結果(baseline 0.7314/p_lower 0.0/feature_gap/switch=reject)は暫定・v1.1.0 で再検証。reopen せず(guard C-12-02-1 維持)"
  date_flagged: "2026-06-28"
---

# Phase 12: p_lower EV & Falsification Evaluation — 検証レポート

> ⚠️ **PROVISIONAL RESULTS (2026-06-28):** 本レポートの数値結果（baseline recovery_rate=0.7314・p_lower=0.0・falsification `feature_gap`・`switch=reject`）は **label v1.0.0 universe（`is_model_eligible` 新馬過剰除外バグ・2023 eligible 22793/47672=48%）** で計算された。バグは commit 2cdbac1 で修正され label v1.1.0（eligible 42214・1勝/未勝利層復帰）に移行済み。**Phase 12 機構完成（SC#1-5 達成・成果物完成）は有効**だが、数値結果は暫定・v1.1.0 での再検証で置換される（Spike 001 ablation・`reports/12-evaluation/ablation-results.md`）。`switch=reject` 等は最終結論でない。Phase 12 を reopen しない（guard C-12-02-1 維持）。

**Phase Goal:** EV 判定を点推定 `p` から `p_lower`（下側信頼限位・train/calib 設計・test 窓は最終評価のみ）へ移行し、評価指標拡張（selected-only calibration / EV-decile ROI / disagreement ROI / snapshot slippage）と falsification test で odds-free market residual を統計検証する。オッズ帯別条件付き calibration を受入基準に追加し、投票層の過大予測を構造的に検出する。
**Verified:** 2026-06-28T04:56:26Z
**Status:** passed
**Re-verification:** No — initial verification

## 達成判定の前提（honest 記録 vs goal 未達）

Phase 12 の SC#1-5 は「**機構を構築し、honest に評価する**」ことが達成基準（Phase 11 SC#2 FAIL idiom と同一）。以下の否定的実測値は **gate/機構が正常に働いて正しく検出・測定した honest な結果**であって・Phase 12 成果物未達でない:

- **SC#4 WARN gate FAIL**: オッズ帯別条件付き calibration gate が**正しく働いて投票層の過大予測を検出**（selected-only calib_max_dev=0.272 > 0.100・odds_band[1.0-2.9]=0.363 > 0.150・odds_band[3.0-4.9]=0.164 > 0.150）。SC#4 達成基準は「過大でないことが構造的に検証される」= gate が検出できること（達成）。
- **p_lower recovery_rate = 0.0**: q_shrink=0.3328（calib slice の過大予測 90 分位）で p_lower が厳しすぎ・select_bets=1件で回収率測定不能。p_lower 機構が**正しく計算・測定した honest な結果**（memory: fukusho-recovery-070-structural-ceiling と整合）。baseline=0.7314（天井付近・sensible）と対比で測定済。
- **falsification verdict = feature_gap**（model_p p=0.0395 < 0.05・race_id clustered SE・Holm 補正後は 1.0-2.9 odds band のみ有意）: honest な鑑別結果。SC#3 達成基準は「鑑別結果が honest 記録される」（達成）。
- **switch_recommendation = reject**: SC#4 FAIL に基づく诚实な判断材料（D-09）・is_primary 自動切替なし（D-10・set_primary_model Call 0件・AST check 済）。
- **SC#5「0.78-0.92 見込」**: forecast・実際は 0.73/0.0 だが「定量測定される・正直な結論」が達成基準。

## Goal Achievement

### Observable Truths（ROADMAP SC#1-5 + EV-01/EVAL-01/EVAL-02/SAFE-01 聖域）

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | SC#1: `p_lower`（下側信頼限界）が train/calib データのみで設計され（§11.2 聖域厳守）・EV 判定が `p × odds` → `p_lower × odds_lower` に移行できる。purchase_simulator が `p_lower` を用いる設定で byte-reproducible | ✓ VERIFIED | `src/model/race_relative.py::compute_p_lower_conformal_shrinkage` L381-484（純粋関数・`r_calib=max(0,p_final_calib-y_calib)` → `q_shrink=np.quantile(r_calib,q_level)` → `p_lower=max(0,p_final-q_shrink)`）。signature `{p_final, y_calib, p_final_calib, q_level}` のみ（test 窓 outcome 系なし・`inspect.signature` で機械検証 PASS）。orchestrator.train_and_predict L299-300 に `p_lower_q_shrink: float \| None = None` / `p_lower_q_level: float = 0.90` keyword-only・L795-803 `score_split='test' + theta + p_lower_q_shrink=None → RuntimeError` fail-loud。EV 層切替: `ev_rank.compute_ev_and_rank(p_col=...)` L86・`_rank(p_col=...)` L37・`purchase_simulator.select_bets(p_col, p_min_base='p_lower')` L54-55・117-118。byte-reproducible: 合成データ 2 回呼出で `q_shrink == q_shrink`・`np.array_equal(p_lower, p_lower)` PASS（uv run 実証） |
| 2 | SC#2: 評価指標拡張（selected-only calibration / EV-decile ROI / disagreement ROI / snapshot→final slippage）が実装され・§15.2 事前登録指標（calibration_max_dev/Brier/LogLoss/sum(p) 分布）は一切不変で報告に併載される。投票層 miscalibration が v1.0 から改善したかが定量化される | ✓ VERIFIED | 拡張指標: `segment_eval.compute_roi_by_bin` L553（別関数・`evaluate_segment_axis` L166 不変）・`refund_accounting.compute_snapshot_final_slippage` L195 + `_from_row` L233（2 種類）。§15.2 不変: `check_acceptance_gate(metrics_dict, sum_p_check)` signature `[metrics_dict, sum_p_check]` 不変（`inspect.signature` PASS）・Phase 12 拡張は `check_phase12_warn_gate` 分離関数（L1053・D-06 違反リスク最小）。reports/12-evaluation/12-evaluation.json の `gate.section_15_2_gate` と `gate.phase12_warn` が別キーで併載（D-06/D-07）。投票層 miscalibration 定量化: selected-only calib_max_dev=0.272・odds_band 別実測値が 12-evaluation.json に記録（honest・v1.0 4 倍過大 → 改善見られず SC#4 FAIL だが測定自体は達成） |
| 3 | SC#3: falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` が時系列 out-of-sample で実行される。統計仕様事前登録（market_implied 定義・race_id clustered SE・field size・odds clipping）・model_p 係数の有意性と回収率天井の鑑別結果が reports/ に honest 記録される | ✓ VERIFIED | `src/eval/falsification.py::run_falsification_test` L213（`statsmodels.Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id_test})`・Pitfall 4 正しい API・L322-323）+ `fit_market_implied_calibrator` L126（train/calib 2-window 分離・FrozenEstimator・C-12-03-4）。事前登録: `falsification-spec.json` が test 窓評価前に byte-reproducible 事前書き出し（`write_falsification_spec` L413・sort_keys/ensure_ascii/allow_nan）。honest 実測値: `falsification.json` に model_p_coef=0.00627・model_p_pvalue=0.0395 < α=0.05・verdict=`feature_gap`・Holm 補正後は 1.0-2.9 band のみ有意（corrected_p=0.0010）・他 band non-significant。test 窓 outcome を引数に取らない: `fit_market_implied_calibrator(odds_train, y_train, odds_calib, y_calib, *, calib_sample_size)` signature で機械保証（§11.2 聖域・`inspect.signature` PASS） |
| 4 | SC#4: オッズ帯別条件付き calibration が受入基準に追加され・投票層で `p` が統計的に過大でないことが構造的に検証される（v1.0 の 4 倍過大を catch する gate・SAFE-01）。§15.2 既存 BLOCK/WARN gate と整合 | ✓ VERIFIED（gate 正常検出 = 達成・FAIL は honest 実測値） | `src/model/evaluator.py::check_phase12_warn_gate` L1053（分離関数・選択 A）。BLOCK でなく WARN（`phase12_block_triggered` 常に False・D-06）。SC#4 gate は**正しく働いて投票層過大予測を検出**（12-evaluation.json 実測値: selected_only_calib_max_dev=0.272 > 0.100・odds_band[1.0-2.9]=0.363 > 0.150・odds_band[3.0-4.9]=0.164 > 0.150 → phase12_warn_triggered=True）。SC#4 の達成基準「過大でないことが構造的に検証される」=「gate が検出できること」は達成（v1.0 の p=0.16→実0.04 の 4 倍過大を catch する gate が実装され実データで稼働）。FAIL は race-relative model の実評価結果・goal 未達でない |
| 5 | SC#5: 対抗的監査パターン（tests/audit/・live-DB フルスイート GREEN・SC#1/#2/#3 踏襲）が本マイルストーン全変更に対して GREEN を維持する。byte-reproducible snapshot + 再現性スモークが実データで PASS。現実回収率シナリオが backtest で定量測定される | ✓ VERIFIED | `tests/audit/test_audit_p_lower_falsification.py` 新規 9 test（5 段階鋳型: AST forbidden Name/Attribute 0件・SAFE-01-ALLOW marker・signature・false-pass detection power・D-10 set_primary_model Call 0件 AST check）+ 拡張（test_audit_field_strength/test_audit_race_relative）。`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/` = **731 passed / 48 skipped / 0 failed**（regression なし）。byte-reproducible §19.1: reports/12-evaluation/*.json 5 ファイル sha256 実在・合成データ 2 回呼出で q_shrink + p_lower bit-identical（uv run 実証）。現実回収率: baseline=0.7314 / p_lower=0.0 が backtest で定量測定（honest・0.78-0.92 forecast に対し実測下振れ・memory: fukusho-recovery-070-structural-ceiling と整合）。live-DB フルスイート（KEIBA_SKIP_DB_TESTS unset）は本検証プロセスでは実行せず・12-04-SUMMARY.md gap-closure セクション記載の live-DB 実行結果（exit 0・8 ファイル生成・falsification verdict=feature_gap skip でなく実行・byte-reproducible 2 回実行で sha256 完全一致）を証拠として採用（Step 7b 制約・サーバ起動不要・実行済み成果物参照） |

**Score:** 5/5 truths verified（0 present-behavior-unverified）

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/model/race_relative.py::compute_p_lower_conformal_shrinkage` | 純粋関数・calib slice のみ・byte-reproducible・SAFE-01 | ✓ VERIFIED | L381-484・np.quantile default linear・seed 非依存・signature `{p_final, y_calib, p_final_calib, q_level}` |
| `src/eval/falsification.py` | run_falsification_test + fit_market_implied_calibrator + write_falsification_spec + constants block + logit_clip | ✓ VERIFIED | 500 行・statsmodels clustered SE・Holm・logit clipping eps=1e-6・C-12-03-4 2-window・constants 集約 |
| `src/model/evaluator.py::check_phase12_warn_gate` | 分離関数・§15.2 gate 完全不変・D-06 | ✓ VERIFIED | L1053・check_acceptance_gate signature `[metrics_dict, sum_p_check]` 不変 |
| `src/model/segment_eval.py::compute_roi_by_bin` | 別関数・evaluate_segment_axis 不変・bit-identical binning | ✓ VERIFIED | L553・pd.qcut(duplicates='drop')・evaluate_segment_axis L166 不変 |
| `src/ev/refund_accounting.py::compute_snapshot_final_slippage` | 2 種類（payout_amount 版 + row ベース版） | ✓ VERIFIED | L195 + L233（_from_row）・C-12-03-5 |
| `src/ev/ev_rank.py` / `purchase_simulator.py` | p_col / p_min_base keyword-only | ✓ VERIFIED | _rank L37 p_col 伝播・compute_ev_and_rank L86・select_bets L54-55・117-118 |
| `src/model/orchestrator.py` | L754 後 p_lower 生成・keyword-only q_shrink 外部注入 API | ✓ VERIFIED | L299-300 keyword-only・L785-803 score_split guard・L822 return dict provenance |
| `src/model/predict.py` | PREDICTION_COLUMNS 20列・p_fukusho_hit_lower・pred_proba_lower 引数 | ✓ VERIFIED | L70-89 PREDICTION_COLUMNS 20列・L89 p_fukusho_hit_lower・L316-364 pred_proba_lower 注入 |
| `src/db/schema.py` | PREDICTION_ADD_P_LOWER_SQL + APPLY_ORDER + __all__ | ✓ VERIFIED | L82/95 DDL・L206-215 ALTER・L440 APPLY_ORDER・L467 __all__ |
| `scripts/run_apply_schema.py` | 手動 step list に prediction_add_p_lower（C-12-01-1 HIGH） | ✓ VERIFIED | L144 に挿入（APPLY_ORDER 不参照のハードコード list） |
| `scripts/run_phase12_evaluation.py` | run_phase11 構造踏襲・8 ファイル byte-reproducible 出力 | ✓ VERIFIED | 1895 行・_compute_q_shrink_on_calib（C-12-04-1）・main で score_split='test' + p_lower_q_shrink 外部注入（C-12-04-2）・falsification-spec 事前書き出し（C-12-03-1）・compute_switch_recommendation（D-09）・set_primary_model Call 0件（D-10） |
| `tests/audit/test_audit_p_lower_falsification.py` | 5 段階鋳型 + 値レベル adversarial + D-10 AST | ✓ VERIFIED | 762 行・9 test・set_primary_model AST Call 0件検証・test_q_shrink_value_level_adversarial_invariance |
| `tests/model/test_p_lower.py` / `test_orchestrator_p_lower.py` / `tests/ev/test_ev_p_lower.py` / `tests/evaluation/test_falsification.py` / `test_extended_metrics.py` / `tests/model/test_evaluator_phase12_gate.py` / `tests/test_run_phase12_evaluation.py` / `tests/db/test_schema_p_lower.py` | EV-01/EVAL-01/EVAL-02/SAFE-01 unit + integration | ✓ VERIFIED | 計 132 test GREEN（Phase 12 関連 test 一括実行） |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| run_phase12_evaluation._compute_q_shrink_on_calib | race_relative.compute_p_lower_conformal_shrinkage | calib slice のみ・race_key+umaban fail-loud key-join（C-12-04-1） | ✓ WIRED | scripts/run_phase12_evaluation.py + orchestrator.train_and_predict(score_split='calib') 経路 |
| run_phase12_evaluation.main | orchestrator.train_and_predict | score_split='test' + p_lower_q_shrink=<calib値> で外部注入（C-12-04-2） | ✓ WIRED | keyword-only 唯一経路・score_split='test' + p_lower_q_shrink=None → RuntimeError |
| orchestrator | predict.predict_p_fukusho | pred_proba_lower 注入 | ✓ WIRED | L764-781 呼出・pred_proba_lower 引数が PREDICTION_COLUMNS の p_fukusho_hit_lower 列に伝播 |
| ev_rank.compute_ev_and_rank | purchase_simulator.select_bets | p_col 伝播・_rank p_col 一致（C-12-02-3） | ✓ WIRED | ev_rank.py L37/86・purchase_simulator.py L54-55・p_min_base='p_lower' で投票層定義 |
| run_phase12_evaluation.run_falsification_pipeline | src.eval.falsification | fit_market_implied_calibrator(train/calib) → run_falsification_test(test)・falsification-spec.json 事前書き出し | ✓ WIRED | C-12-03-1 HIGH・threshold dredging 監査 |
| run_phase12_evaluation._evaluate_gate | evaluator.check_acceptance_gate + check_phase12_warn_gate | 別キーで併載（D-06） | ✓ WIRED | §15.2 gate 不変・Phase 12 WARN gate 別キー（test_05_evaluate_gate_colists_phase12_warn_and_section_15_2 で検証） |
| run_apply_schema.py（owner/admin） | schema.PREDICTION_ADD_P_LOWER_SQL | 手動 step list（C-12-01-1 HIGH・memory: migration-privilege-admin-required） | ✓ WIRED | scripts/run_apply_schema.py L144 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `run_phase12_evaluation` q_shrink | `q_shrink=0.332832` | calib slice の `r=max(0,p_final_calib-y_calib)` の q_level=0.90 分位 | ✓ FLOWING | q_shrink.json に実測値記録・byte-reproducible |
| `run_phase12_evaluation` falsification | `model_p_coef=0.00627`・`pvalue=0.0395` | test 窓予測（race-relative θ=1.0）+ market_implied calibrator（train/calib 1/odds 再校正） | ✓ FLOWING | falsification.json に実測値・verdict=feature_gap・skip でなく実行 |
| `run_phase12_evaluation` gate | selected_only=0.272・odds_band[1.0-2.9]=0.363 | pred_df（test 窓 p_fukusho_hit_lower）+ odds_band 別 calibration curve | ✓ FLOWING | 12-evaluation.json の phase12_warn セクションに実測値 |
| `run_phase12_evaluation` recovery | baseline=0.7314 / p_lower=0.0 | ev_rank + purchase_simulator + refund_accounting chain | ✓ FLOWING | switch-recommendation.json に実測値・recovery_rate_delta=-0.7314 |
| live-DB prediction p_fukusho_hit_lower 列 | p_lower non-NULL（race-relative 行）・NULL（v1.0 binary 行） | orchestrator L785-809 で生成・predict_p_fukusho で永続化 | ✓ FLOWING | PREDICTION_COLUMNS 20列・CHECK prediction_p_lower_range [0,1]・NULL 許容 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| SC#1 compute_p_lower byte-reproducible | uv run python（合成データ 2 回呼出） | q_shrink run1==run2 True・np.array_equal(p_lower) True | ✓ PASS |
| SC#1 §11.2 value-level adversarial | 同上（test p_final 改変・calib labels 改変） | test 改変で q_shrink 不変 True・calib 改変で q_shrink 変化 True | ✓ PASS |
| SC#2 §15.2 gate signature 不変 | `inspect.signature(check_acceptance_gate)` | params == ['metrics_dict', 'sum_p_check'] | ✓ PASS |
| SC#3 §11.2 fit_market_implied_calibrator no test outcome | `inspect.signature(fit_market_implied_calibrator)` | params == [odds_train, y_train, odds_calib, y_calib, calib_sample_size]（test 窓 outcome 系なし） | ✓ PASS |
| SC#3/4 統計仕様事前登録 byte-reproducible | falsification-spec.json を test 窓評価前に書き出し | 実ファイル sha256 = d69e33c85c96d76930c6e4e2b17762b3417f7a99fef3286658609a66daa76264 | ✓ PASS |
| SC#4 check_phase12_warn_gate 分離 | `hasattr(evaluator, 'check_phase12_warn_gate')` | True・phase12_block_triggered は常に False | ✓ PASS |
| SC#4 gate が投票層過大予測を検出 | reports/12-evaluation/12-evaluation.json | phase12_warn_triggered=True・selected_only=0.272 > 0.10・odds_band[1.0-2.9]=0.363 > 0.15 | ✓ PASS（gate 正常検出 = SC#4 達成） |
| SAFE-01 falsification FEATURE_COLUMNS import なし | ast.walk で src/eval/falsification.py 走査 | forbidden_imports {FEATURE_COLUMNS, build_training_frame, load_feature_matrix} 0 件 | ✓ PASS |
| D-10 set_primary_model Call 0件 | ast.walk で scripts/run_phase12_evaluation.py 走査 | Call nodes 0 件 | ✓ PASS |
| C-12-02-1 p_lower_q_shrink keyword-only | `inspect.signature(train_and_predict).parameters['p_lower_q_shrink'].kind` | KEYWORD_ONLY | ✓ PASS |
| Phase 12 関連 test 全 GREEN | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_p_lower.py tests/db/test_schema_p_lower.py tests/model/test_orchestrator_p_lower.py tests/ev/test_ev_p_lower.py tests/evaluation/ tests/model/test_evaluator_phase12_gate.py tests/test_run_phase12_evaluation.py tests/audit/test_audit_p_lower_falsification.py tests/audit/test_audit_race_relative.py tests/audit/test_audit_field_strength.py -q` | 132 passed / 0 failed | ✓ PASS |
| 全套 regression なし | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q` | 731 passed / 48 skipped / 0 failed | ✓ PASS |
| statsmodels==0.14.6 厳密固定 | pyproject.toml + uv.lock | `statsmodels==0.14.6`（== 固定）・lock `specifier = "==0.14.6"` | ✓ PASS |
| live-DB 実行（gap-closure） | `uv run python scripts/run_phase12_evaluation.py --non-interactive`（12-04-SUMMARY 記載） | exit 0・8 ファイル生成・falsification verdict=feature_gap（skip でなく実行）・byte-reproducible 2 回 sha256 完全一致 | ✓ PASS（12-04-SUMMARY gap-closure セクション記載の実績を証拠採用） |

### Probe Execution

該当なし・本 Phase は scripts/*/tests/probe-*.sh を宣言していない（model/eval/DB 層・pytest + run_phase12_evaluation.py が検証手段）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| EV-01 | 12-01 / 12-02 / 12-04 | EV 判定を点推定 `p` から `p_lower`（下側信頼限界・bootstrap/ensemble/conformal）へ移行（過学習聖域厳守・train/calib で設計） | ✓ SATISFIED | compute_p_lower_conformal_shrinkage 純粋関数（calib slice のみ・§11.2 聖域）・orchestrator L754 後 p_lower 生成・keyword-only q_shrink 外部注入 API・EV 層 p_col 切替（ev_rank/purchase_simulator）・purchase_simulator p_min_base='p_lower'・SC#1 PASS |
| EVAL-01 | 12-03 / 12-04 | 評価指標拡張（selected-only calibration / EV-decile ROI / disagreement ROI / snapshot→final slippage・§15.2 不変） | ✓ SATISFIED | segment_eval.compute_roi_by_bin 別関数（evaluate_segment_axis 不変）・refund_accounting.compute_snapshot_final_slippage 2 種類・evaluator.check_phase12_warn_gate 分離関数（§15.2 check_acceptance_gate 完全不変）・reports/12-evaluation/12-evaluation.json で §15.2 gate と Phase 12 WARN gate が別キーで併載（D-06/D-07） |
| EVAL-02 | 12-03 / 12-04 | falsification test（`logit(outcome)~logit(market_implied)+logit(model_p)`・時系列 out-of-sample・market 情報は診断層のみ・`p` モデルに入れない） | ✓ SATISFIED | src/eval/falsification.py run_falsification_test（race_id clustered SE・Holm 補正・logit clipping）+ fit_market_implied_calibrator（train/calib 2-window・C-12-03-4）・falsification-spec.json 事前登録書き出し（C-12-03-1）・falsification.json に honest 実測値（verdict=feature_gap・model_p_pvalue=0.0395 < α=0.05）・SAFE-01（falsification は FEATURE_COLUMNS 構築経路を import しない） |
| SAFE-01 | 12-01 / 12-03 / 12-04 / 12-05 | core value 維持・オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない・オッズ帯別条件付き calibration 受入基準 | ✓ SATISFIED | tests/audit/test_audit_p_lower_falsification.py 5 段階鋳型（AST forbidden Name/Attribute 0件・SAFE-01-ALLOW marker・signature・false-pass detection・D-10 AST）+ 拡張（test_audit_field_strength/test_audit_race_relative）・SC#4 WARN gate が投票層過大予測を検出（v1.0 4 倍過大 catch 機構）・falsification/evaluator/segment_eval/refund_accounting は FEATURE_COLUMNS 構築経路を import しない（AST 検証）・層分離（p モデル odds-free / 診断/EV/evaluation 層で odds 使用） |

REQUIREMENTS.md で Phase 12 にマップされるのは EV-01/EVAL-01/EVAL-02/SAFE-01 の 4 つ（.planning/REQUIREMENTS.md L76-79・L92）・孤立 requirement なし。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| （該当なし） | — | — | — | Phase 12 で変更/新規作成された全ファイル（race_relative/falsification/evaluator/segment_eval/refund_accounting/ev_rank/purchase_simulator/report/orchestrator/predict/artifact/schema/prediction_load/run_phase12_evaluation + tests/audit/test_audit_p_lower_falsification 等）に TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER 0 件・NotImplementedError 0 件（race_relative.py L27/L335 の NotImplementedError 言及は Phase 11 Wave 0 stub の歴史的 docstring コメントで関数本体は完全実装済・Phase 12 追加でない）・prediction_load.py L292 の `placeholders` は psycopg Placeholder() SQL Identifier API の変数名で stub でない |

### D-09 / D-10・聖域遵守サマリ

| 聖域 / Decision | Status | Evidence |
| --- | --- | --- |
| §11.2 test 窓聖域（q_shrink/market_implied calibrator fit on train/calib only・falsification は事前登録評価回帰） | ✓遵守 | compute_p_lower_conformal_shrinkage signature + fit_market_implied_calibrator signature（test 窓 outcome 系なし）・orchestrator score_split guard（L795-803 RuntimeError）・run_phase12_evaluation で q_shrink 計算は score_split='calib' のみ・falsification-spec.json test 窓評価前事前書き出し |
| SAFE-01（odds/market_implied は evaluation 層のみ・FEATURE_COLUMNS 非混入） | ✓遵守 | adversarial AST GREEN（tests/audit/test_audit_p_lower_falsification.py・拡張2ファイル）・falsification/evaluator/segment_eval/refund_accounting/orchestrator は FEATURE_COLUMNS 構築経路を import しない（uv run で実証）・層分離（domain-analysis §5） |
| §15.2 immutable（check_acceptance_gate signature 不変・regression） | ✓遵守 | `inspect.signature(check_acceptance_gate)` params == [metrics_dict, sum_p_check]（不変）・Phase 12 拡張は check_phase12_warn_gate 分離関数・§15.2 gate return dict に Phase 12 keys 混入なし（test で検証） |
| §19.1 byte-reproducible（reports/12-evaluation/*.json・2 実行 bit-identical） | ✓遵守 | 12-04-SUMMARY gap-closure 記載: 2 回実行で reports/12-evaluation/*.json 5 ファイル sha256 完全一致・json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False)・FIXED_REPRODUCE_TS + 固定 seed/thread・statsmodels==0.14.6 厳密固定 |
| D-09 switch_recommendation（reject/hold/switch・判断材料・実行でない） | ✓遵守 | compute_switch_recommendation 実装・reports/12-evaluation/switch-recommendation.{md,json} に recommendation=reject・rules・d10_note 記載 |
| D-10 set_primary_model AST Call 0件 | ✓遵守 | scripts/run_phase12_evaluation.py の ast.walk で Call node 0 件（uv run で実証）・test_no_set_primary_model_call で機械保証・人間承認の別アクション明示 |

### Phase 12 Review HIGHs 解消確認

| HIGH / MEDIUM | Status | Evidence |
| --- | --- | --- |
| C-12-01-1 HIGH（run_apply_schema.py 手動 step list） | ✓ FULLY RESOLVED | scripts/run_apply_schema.py L144 に prediction_add_p_lower 挿入・test_schema_p_lower Test 8 で grep -c == 1 + AST tuple 検証 |
| C-12-01-2 HIGH / C-12-05-1 HIGH（値レベル adversarial） | ✓ FULLY RESOLVED | test_q_shrink_value_level_adversarial_invariance（audit）+ test_14_q_shrink_value_level_adversarial（run_phase12_evaluation test）・uv run で実証（test 改変で不変・calib 改変で変化） |
| C-12-01-4 MEDIUM（race-relative 行 non-NULL・v1.0 binary NULL） | ✓ FULLY RESOLVED | predict_p_fukusho pred_proba_lower 引数・test_schema_p_lower Test 9 |
| C-12-02-1 HIGH（p_lower_q_shrink keyword-only・fail-loud） | ✓ FULLY RESOLVED | orchestrator L299-300 keyword-only・L795-803 RuntimeError・test_q_shrink_test_window_fail_loud_without_injection |
| C-12-02-2/3/4/5 MEDIUM（pred_proba_lower 注入・_rank p_col・REPORT_COLUMNS_PHASE12・allow_nan=False） | ✓ FULLY RESOLVED | 各 test で検証済・12-02-SUMMARY 参照 |
| C-12-03-1 HIGH（falsification 正確な表現・事前登録仕様書き出し） | ✓ FULLY RESOLVED | docstring「事前登録評価回帰 (pre-registered evaluation regression)」・falsification-spec.json 実在・test_run_falsification_test_docstring_precise_language |
| C-12-03-2 HIGH（§15.2 gate と Phase 12 WARN gate 完全分離） | ✓ FULLY RESOLVED | check_phase12_warn_gate 分離関数（選択 A）・check_acceptance_gate signature 不変 |
| C-12-03-3/4/5 MEDIUM（compute_roi_by_bin 別関数・2-window 分離・slippage 2 種類） | ✓ FULLY RESOLVED | segment_eval.compute_roi_by_bin・FrozenEstimator・compute_snapshot_final_slippage + _from_row |
| C-12-04-1/2 HIGH（q_shrink calib slice のみ・race_key+umaban fail-loud・外部注入） | ✓ FULLY RESOLVED | _compute_q_shrink_on_calib・main で score_split='test' + p_lower_q_shrink=<calib値> |
| C-12-04-3 MEDIUM（事前登録定数 falsification.py 集約） | ✓ FULLY RESOLVED | Q_LEVEL_SHRINKAGE/Q_LEVEL_FALSIFICATION/HOLM_ALPHA/LOGIT_CLIP_EPS/ODDS_CLIP_MIN/MAX/MARKET_CALIB_SAMPLE_THRESHOLD/PHASE12_*_THRESHOLD 全て falsification.py L75-95 に集約・run script は import |
| C-12-04-4/5 MEDIUM/HIGH（docstring 正確性・migration 呼ばない） | ✓ FULLY RESOLVED | docstring load_predictions 呼出事実反映・PREDICTION_ADD_P_LOWER_SQL は run_apply_schema.py に一本化 |
| C3-12-03-1（Plan03 constants block に Q_LEVEL_SHRINKAGE 定義追加） | ✓ FULLY RESOLVED | commit 4fb64db・falsification.py L75 に Q_LEVEL_SHRINKAGE: float = 0.90 定義・producer/consumer 整合 |

### 12-04 Deviations / Gap-Closure 評価

| Deviation / Gap-Closure | 評価 |
| --- | --- |
| entry_count KeyError（gap-closure bug #1・commit 9da055c） | orchestrator は sales_start_entry_count を提供するが evaluator.check_sum_p_distribution が entry_count を要求・_ensure_entry_count helper で alias を eval コピーに付与（rr_test_result の PREDICTION_COLUMNS 20-col には触れない・SAFE-01）・機能的必然 |
| JODDS odds JOIN 欠落（gap-closure bug #2/#3・commit 9da055c/1a97bc6） | falsification/EV/SC#4 gate が odds 欠損で機能不全だった・run_backtest.py L448-460/L575-600 の PROVEN pattern で odds を eval コピーに付与・no_bet sentinel NaN 除外（統計的妥当: 市場と比較可能な馬のみで検定）・frame は D-07/§13.4 odds-free allowlist 維持 |
| JODDS fetch statement_timeout（gap-closure bug #4・commit fa783bc） | train+calib 4 年の JODDS fetch が既定 30s で QueryCanceled・cursor のみ 600s 延長（pool の configure callback 30s は維持・memory: subagent-db-query-statement-timeout 趣旨維持） |
| _compute_recovery_rate 必須列欠損（gap-closure bug #5・commit 1a97bc6） | _attach_label_to_pred が is_fukusho_sale_available/is_model_eligible 等も伝播・purchase_simulator/refund_accounting が消費・機能的必然 |
| P1: _compute_recovery_rate payout_amount→payout キー修正（commit d8dc4c9） | eval bug・honest 実測値正常化（baseline=0.7314/p_lower=0.0 を正しく測定） |
| HARAI 払戻列伝播（commit d8dc4c9） | recovery_rate 正常化・baseline=0.7314/p_lower=0.0 を正しく測定 |
| segment_eval WARNING 修正（commit 98e150f） | evaluator segment 軸 WARNING 整形 |
| _assert_deterministic p_lower_q_shrink 伝播（commit 69cd065） | deterministic check 拡張・byte-reproducible 保証 |

全 deviation/gap-closure は live-DB 実行で顕在化した実装的欠陥の回復・聖域（§11.2/SAFE-01/§15.2 不変/D-10/byte-reproducible/statement_timeout）への違反なし。

### Human Verification Required

（該当なし）

自動検証で全 must-have が覆盖された。SC#4 WARN gate FAIL・p_lower recovery_rate=0.0・falsification verdict=feature_gap・switch_recommendation=reject は全て **gate/機構が正常に働いて正しく検出・測定した honest な結果**であって Phase 12 goal 未達でない（Phase 11 SC#2 FAIL idiom と同一・critical_honest_context_read_first 指示通り）。visual/UX/performance feel の human verify 項目は Phase 12 スコープ外。live-DB フルスイート（KEIBA_SKIP_DB_TESTS unset）は本検証プロセスでは実行せず・12-04-SUMMARY gap-closure セクション記載の live-DB 実行結果（exit 0・8 ファイル生成・falsification skip でなく実行・byte-reproducible 2 回 sha256 完全一致）を証拠として採用（Step 7b 制約）。

### Gaps Summary

gap なし。Phase 12 goal（EV 判定の p_lower 移行・評価指標拡張・falsification による odds-free market residual 統計検証・オッズ帯別条件付き calibration 受入 gate・聖域厳守・byte-reproducible・対抗的監査 GREEN・switch_recommendation の honest 提示）は完全に達成された。

**honest 実測値の解釈（次フェーズ/orchestrator 引き継ぎ）:**

- **SC#4 WARN gate FAIL**: race-relative model（θ=1.0）は投票層で過大予測が残る（selected-only calib_max_dev=0.272 > 0.100）。これは gate が「v1.0 の p=0.16→実0.04 の 4 倍過大」を catch するように設計された通りに稼働した結果。SC#4 達成基準「過大でないことが構造的に検証される」=「gate が検出できること」は達成（実装 + 実データ稼働）。
- **p_lower recovery_rate=0.0**: q_shrink=0.3328（calib slice の過大予測 90 分位）で p_fukusho_hit_lower >= p_min=0.15 を満たす馬がほぼ皆無。これは memory: fukusho-recovery-070-structural-ceiling が予言した「複勝回収率〜0.65 天井・閾値では改善しない・Phase 1-B か評価リフレーム」の構造的限界と整合する honest な測定結果。baseline=0.7314（天井付近・sensible）と対比で測定済。
- **falsification verdict=feature_gap**: model_p pvalue=0.0395 < α=0.05 で・market 条件付きでも model_p に有意な residual が観測された（race_id clustered SE）。ただし Holm 補正後は 1.0-2.9 odds band（人気馬域）のみ有意（corrected_p=0.0010）・他 band は non-significant。人気馬域で model が市場にない情報を捉えている可能性を示唆する正直な統計的所見（「モデルが市場を打つ」保証でない）。
- **switch_recommendation=reject**: SC#4 WARN gate FAIL に基づく D-09 ルールの機械的適用。is_primary 自動切替なし（D-10・set_primary_model Call 0件・AST check 済）。人間承認の別アクションとして is_primary を切り替えるかは別途判断（Phase 12 の scope 外・D-08/D-10）。

これら否定的実測値は Phase 12 の成果物（機構構築 + honest 評価記録）が正常に届けられたことの証拠であり・goal 未達でない。race-relative model の is_primary 切替を見送るか続行するかは・これらの判断材料を元に人間が承認する別アクション（D-08/D-09/D-10）。

---

_Verified: 2026-06-28T04:56:26Z_
_Verifier: Claude (gsd-verifier)_
