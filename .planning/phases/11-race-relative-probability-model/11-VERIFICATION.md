---
phase: 11-race-relative-probability-model
verified: 2026-06-27T17:30:00+09:00
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
---

# Phase 11: Race-Relative Probability Model — 検証レポート

**Phase Goal:** MODEL-01 レース内相対確率モデル（race-relative probability model）。logit temperature θ + per-race α_r 二分探索の race-relative 補正層を実装し・v1.0 binary とリークなく（§11.2 聖域・theta 選択は calib slice の事前登録固定値のみ・test 窓選び直し禁止）比較できること。SC#1-5 聖域・D-01〜D-10・§19.1 再現性を機械保証すること。
**Verified:** 2026-06-27T17:30:00+09:00
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### 観察可能 truths（ROADMAP SC#1-5 + MODEL-01/SAFE-01 聖域）

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | SC#1: モデルが race_id 単位で `sum(p)=払戻対象数` を満たす構造を持ち・train→calib→test が GroupTimeSeriesSplit（race_id group）で時系列厳守・calib は `fit_prefit_calibrator` で later-disjoint strict `<` | ✓ VERIFIED | `src/model/race_relative.py::apply_race_relative_correction` が race 毎 `np.unique(race_ids)` で独立ループ・`solve_alpha_for_race` が brentq(xtol=1e-9) で α_r を解き `sum(sigmoid(s/θ+α))=k` を厳密達成（実測精度 4.44e-16）。`test_pipeline_sum_p_invariant`/`test_alpha_monotonic_unique_solution` GREEN。calib later-disjoint は `src/model/orchestrator.py::_calibrate_catboost_manual` (L844-852) と `fit_prefit_calibrator` が strict `<` guard で保証（Phase 4/6 から不変）。`split_3way` は既存 race_id group 時系列分割を踏襲 |
| 2 | SC#2: 新モデル `p_fukusho_hit` が §15.2 事前登録指標（calibration_max_dev 不変・binning は evaluator/segment_eval import 再利用）で評価され・D-04 非劣化マージン内・selected-only/odds-band 改善 gate を test 窓一回評価 | ✓ VERIFIED | `reports/11-evaluation/11-evaluation.md` に test 窓一回評価が honest 記録（D-04 PASS・D-05 改善 gate の条件2/3 PASS・条件1 overprediction penalty は odds-free 1-A 構造的制約で NaN）。binning 定数（CALIBRATION_CURVE_BINS=10/ODDS_BAND_EDGES/NINKI_BAND_EDGES）は `run_phase11_evaluation.py` L102-118 で import 再利用・再定義0件（codex HIGH#2 解消）。**SC#2 gate FAIL は honest 記録自体が §11.2 聖域遵守**（θ を test 窓で選び直して gate を通す後知恵すり替えをしていない）。race-relative model の D-04 非劣化（Brier -0.00323/LogLoss -0.01355/AUC +0.01896 全改善）は達成 |
| 3 | SC#3: 新モデルが LightGBM・CatBoost 両方で bit-identical（FIXED_REPRODUCE_TS + 固定 thread/seed + np.array_equal） | ✓ VERIFIED | `src/model/orchestrator.py::_assert_deterministic` が theta 引数対応（codex HIGH#8）・`run_phase11_evaluation.py` L392-401 で lightgbm_rr の deterministic smoke PASS を live-DB 実証。「同一モデル同一 seed の再現性」であって cross-family 同一性でないことは codex MEDIUM 指摘通り docstring/scope 明示（SC#3 原文「両方で構築でき bit-identical」の正しい解釈）。LightGBM race-relative model の prediction 行が永続化済み |
| 4 | SC#4: 特徴量に odds/人気/過去人気/過去オッズ proxy が混入しないこと・`.cat.codes.min()>=0` fail-loud を adversarial で証明 | ✓ VERIFIED | `tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy` が `src/model/race_relative.py` の AST を Name/Attribute/SQL 文字列定数で走査し禁止 proxy トークン 0 件を証明（SC#4 静的証明）。race_relative モジュールは純粋 logit 演算のみ。`.cat.codes.min()>=0` guard は既存（Phase 1〜）・Phase 11 で回帰なし。全套 unit pytest 608 passed / 0 failed（KEIBA_SKIP_DB_TESTS=1） |
| 5 | SC#5: 新 prediction テーブルが §19.1 再現性 metadata 付きで model_version-scoped idempotent swap で永続化 | ✓ VERIFIED | `src/db/schema.py` L85-87/91: PREDICTION_TABLE_DDL に `label_version`/`odds_snapshot_policy`/`backtest_strategy_version` 3列 DEFAULT 'unspecified' sentinel 追加・CHECK 制約 lightgbm_rr/catboost_rr 拡張（codex cycle-2 NEW HIGH#1/#3 解消）。`src/model/predict.py` L92-94: PREDICTION_COLUMNS 19列化。`run_phase11_evaluation.py` L414-428: `load_predictions` public wrapper（codex HIGH#4）で2回実行 checksum bit-identical=2af03124... PASS・as_of_datetime=FIXED_REPRODUCE_TS 固定（codex cycle-2 NEW HIGH#2 解消）・3 metadata 列が sentinel でなく事前登録値（label_version=v1.0/odds_snapshot_policy=30min_before/backtest_strategy_version=BT-1）を live-DB psql で確認 |

**Score:** 5/5 truths verified（0 present-behavior-unverified）

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/model/race_relative.py` | α_r 二分探索・apply 補正・overprediction penalty pure 関数 | ✓ VERIFIED | 3関数全実装（NotImplementedError 0件・docstring 内言及のみ）・brentq xtol=1e-9・SC#4 AST 監査対象・THETA_CANDIDATES 事前登録定数 |
| `src/model/orchestrator.py` | train_and_predict に theta/score_split/3 metadata 引数・_normalize_model_type・双方向 guard | ✓ VERIFIED | L431-456: _normalize_model_type + theta/model_type 双方向 guard + score_split 入力検証。L696-744: theta 指定時に apply_race_relative_correction 呼出。L754-771: predict_p_fukusho に 3 metadata 伝播 |
| `src/db/schema.py` | PREDICTION_TABLE_DDL provenance 3列・CHECK制約 lightgbm_rr/catboost_rr 拡張 | ✓ VERIFIED | L85-91: 3列 DEFAULT 'unspecified' + CHECK 拡張。L147-180: ALTER migration 定数（idempotent DROP+ADD） |
| `src/model/predict.py` | PREDICTION_COLUMNS 19列・predict_p_fukusho 新3引数 sentinel 既定 | ✓ VERIFIED | L92-94: 3列追記・L192-194: sentinel 既定値・L318-320: DataFrame 構築で3列付与 |
| `scripts/run_phase11_evaluation.py` | SC#2 gate + θ 選択経路（calib slice）+ theta-selection.json 事前書き出し + load_predictions swap | ✓ VERIFIED | 1228行・θ 選択は score_split='calib' のみ（codex HIGH#1）・L329-332 theta-selection.json 事前 atomic write・L414-428 idempotent swap |
| `tests/model/test_race_relative.py` | MODEL-01 13 unit test（α_r/clip/sum(p)=k/bit-identical/overprediction/k 決定/fail-loud/pipeline） | ✓ VERIFIED | 13 test 全 GREEN（KEIBA_SKIP_DB_TESTS=1 で 0.97s）・VALIDATION.md Test Map の全契約覆盖 |
| `tests/audit/test_audit_race_relative.py` | D-10 α_r 自己完結性・cross-race leak・SC#4 AST・false-positive 検出力 | ✓ VERIFIED | 4 adversarial test GREEN・inspect.signature で solve_alpha_for_race が outcome を引数に取らない構造的保証 |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| orchestrator.train_and_predict | race_relative.apply_race_relative_correction | theta 指定時に `pred_proba.to_numpy()` →補正→ `pd.Series(p_final)` 再注入 | ✓ WIRED | orchestrator.py L738-744 |
| orchestrator | predict_p_fukusho | pred_proba 注入（Cycle 2 NEW HIGH-1）+ 3 metadata 引数伝播 | ✓ WIRED | orchestrator.py L754-771 |
| run_phase11_evaluation | orchestrator（θ 選択経路） | `train_and_predict(score_split="calib")` のみ・test 窓に触れない構造的聖域ブロック | ✓ WIRED | run_phase11_evaluation.py L308-327 + orchestrator score_split guard L449-456 |
| run_phase11_evaluation | db.prediction_load.load_predictions | public wrapper で idempotent swap・as_of_datetime=FIXED_REPRODUCE_TS 固定 | ✓ WIRED | run_phase11_evaluation.py L414-428 |
| race_relative.compute_overprediction_penalty | evaluator/segment_eval binning | CALIBRATION_CURVE_BINS・_compute_calibration_curve_bins・_odds_band import 再利用 | ✓ WIRED | race_relative.py L42-46・codex HIGH#2 解消・np.linspace 独自 binning 0件 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `race_relative.apply_race_relative_correction` | `p_final` | orchestrator から注入される `pred_proba`（calibrated binary model の実予測）+ race_df_score の sales_start_entry_count | ✓ FLOWING | live-DB 実証：race-relative 行 22793行・v1.0 binary 行 22213行 永続化済み |
| `run_phase11_evaluation` gate | baseline/race-relative metrics | orchestrator.train_and_predict の pred_df に label JOIN（_attach_label_to_pred） | ✓ FLOWING | reports/11-evaluation/11-evaluation.json に実測 Brier/LogLoss/AUC 記録 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| α_r 二分探索が sum(p)=k を厳密達成 | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_race_relative.py -x` | 13 passed / 0 failed (0.97s) | ✓ PASS |
| SC#4 AST odds/ninki proxy 0件 | 同上（test_audit_race_relative.py 含む）| 4 passed / 0 failed | ✓ PASS |
| D-10 α_r 自己完結性（outcome swap 不変） | 同上 | test_alpha_self_contained_outcome_swap GREEN | ✓ PASS |
| 全 unit スイート回帰なし | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q` | 608 passed / 48 skipped / 0 failed (43.99s) | ✓ PASS |
| SC#2 gate（live-DB） | `run_phase11_evaluation.py` 実行済み（orchestrator 直接実行）| reports に honest 記録：D-04 PASS・D-05 条件1 NaN FAIL・全套 pytest 651 passed / 5 skipped / 0 failed | ✓ PASS（honest 記録自体が聖域遵守） |
| SC#3 bit-identical（live-DB） | 同上 | theta=1.0 race-relative deterministic smoke PASS | ✓ PASS |
| SC#5 idempotent swap（live-DB） | 同上 | load_predictions 2回 checksum bit-identical | ✓ PASS |

live-DB フルスイート（KEIBA_SKIP_DB_TESTS unset）は本検証プロセスでは実行せず・11-05-SUMMARY.md に記録された orchestrator 直接実行結果（651 passed / 0 failed・SC#3/SC#5 PASS）を証拠として採用（Step 7b 制約：サーバ起動不要・実行済み成果物を参照）。

### Probe Execution

該当なし・本 Phase は scripts/*/tests/probe-*.sh を宣言していない（model/DB 層・pytest が検証手段）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| MODEL-01 | 11-01〜11-05 | レース内相対確率モデル（sum(p)=払戻対象数・race-level top-k calibration 的）導入 | ✓ SATISFIED | race_relative.py + orchestrator theta 統合 + §19.1 metadata + live-DB 永続化全て実装・SC#1/3/5 PASS・SC#2 honest 記録 |
| SAFE-01 | 11-01/11-04 | モデル変更時のリーク/市場回帰ガード（odds/ninki proxy 排除・.cat.codes.min()>=0） | ✓ SATISFIED | tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy が AST 静的証明・market_signal は evaluation 専用層のみで FEATURE_COLUMNS 不混入 |

REQUIREMENTS.md で Phase 11 にマップされるのは MODEL-01 と SAFE-01 の2つのみ（.planning/REQUIREMENTS.md L91）・孤立 requirement なし。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| （該当なし） | — | — | — | Phase 11 で変更された全ファイル（race_relative/orchestrator/predict/schema/run_phase11_evaluation）に TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER 0件・NotImplementedError 0件（docstring 内の歴史的言及のみ） |

### codex review HIGHs 解消確認

| HIGH | Status | Evidence |
| --- | --- | --- |
| cycle-1 HIGH#1（θ test 窓聖域） | ✓ FULLY RESOLVED | orchestrator score_split guard L449-456 + θ 選択 score_split='calib' only + theta-selection.json 事前書き出し |
| cycle-1 HIGH#2（binning import 再利用） | ✓ FULLY RESOLVED | race_relative.py L42-46 で evaluator/segment_eval から import |
| cycle-1 HIGH#3（§19.1 metadata 3層） | ✓ FULLY RESOLVED | script→orchestrator→predict_p_fukusho→PREDICTION_COLUMNS の4層ワイヤリング |
| cycle-1 HIGH#4（load_predictions public wrapper） | ✓ FULLY RESOLVED | run_phase11_evaluation.py L417-418 で public wrapper 使用 |
| cycle-1 HIGH#5（task 順序） | ✓ FULLY RESOLVED | 11-05 Task1→2→3 順（実装が checkpoint に先行） |
| cycle-1 HIGH#6（sales_start_entry_count fallback） | ✓ FULLY RESOLVED | orchestrator.py L705-736 で列必須取得 + race 内一意性 guard |
| cycle-2 NEW HIGH#1（CHECK制約 lightgbm_rr/catboost_rr） | ✓ FULLY RESOLVED | schema.py L91/180 CHECK 拡張 + live-DB 実証 |
| cycle-2 NEW HIGH#2（固定 as_of_datetime） | ✓ FULLY RESOLVED | run_phase11_evaluation.py L350/374 FIXED_REPRODUCE_TS 固定 |
| cycle-2 NEW HIGH#3（sentinel 既定値） | ✓ FULLY RESOLVED | predict.py L192-194 'unspecified' sentinel・NOT NULL 違反回避 |
| cycle-3 収束 | ✓ convergence | 11-REVIEWS.md cycle-3: 4/4 HIGH + 3/3 MEDIUM/LOW FULLY RESOLVED・0 NEW problems |

### D-01 聖域（binary 本体不変）確認

`src/model/trainer.py` / `src/model/calibrator.py` / `src/model/segment_eval.py` / `src/model/data.py` / `src/model/evaluator.py` / `src/model/artifact.py` の最終変更コミットは Phase 4/6（b73599f/06faf02/c6c04a2 等）であり・Phase 11 コミット（277d049..5e6a275 等）では一切変更されていない。binary LightGBM/CatBoost 本体は不変・補正層のみ追加（D-01 聖域遵守）。

### 11-05 Deviations 評価

| Deviation | 評価 |
| --- | --- |
| migration 適用経路変更（etl cursor → run_apply_schema.py owner 権限） | 構造的必然（ALTER TABLE は owner 権限必要・etl ロールで InsufficientPrivilege）・Phase 6 idiom 踏襲・機能的等価 |
| PREDICTION_TABLE_DDL（CREATE TABLE）への provenance 3列追加 | Task 1 漏れの回復・test_prediction_columns_matches_ddl_count が正しく検出・CREATE TABLE 19列化は §19.1 再現性強化 |
| stage2 NaN-safe（odds-free 1-A で overprediction penalty 計算不能） | odds-free 1-A 構造的制約（D-15 参考記録に一貫）・全候補 NaN の場合は stage3 tiebreak で決定・§11.2 聖域（test 窓を見ない）遵守 |
| markdown None-safe（θ 候補表 overprediction NaN 表示） | 表示のみの整形・gate 判定への影響なし |
| test_is_primary_flag.py regression 修正 | Phase 11 schema 変更（PREDICTION_COLUMNS 19列）への当然の追従・helper に provenance 追加 + assert 16→19 |

全 deviation は構造的制約による必然的逸脱であり・聖域（§11.2/§19.1/D-01/D-07）への違反なし。

### Human Verification Required

（該当なし）

自動検証で全 must-have が覆盖された。SC#2 gate FAIL は honest 記録であり Phase 11 goal 未達でない（race-relative model の評価結果・Phase 12 の is_primary 切替判断材料）。visual/UX/performance feel の human verify 項目も Phase 11 スコープ外（Streamlit UI は Phase 7・is_primary 切替は Phase 12）。

### Gaps Summary

gap なし。Phase 11 goal（race-relative 補正層の実装・v1.0 binary とのリークない比較・SC#1-5 聖域・D-01〜D-10・§19.1 再現性の機械保証）は完全に達成された。

SC#2 gate が FAIL となったことは Phase 11 goal の未達ではなく・race-relative model（θ=1.0）の実評価結果である。goal は「リークなく比較できること・聖域を機械保証すること」であり・「race-relative model が v1.0 binary より全指標で優れること」でない。honest 記録自体（θ を test 窓で選び直して gate を通す後知恵すり替えをしなかったこと）が §11.2 聖域遵守の証拠。race-relative model は D-04 非劣化（Brier/LogLoss/AUC 全改善）を達成し・D-05 改善 gate の条件1（overprediction penalty）のみ odds-free 1-A 構造的制約で NaN FAIL・条件2/3 は PASS。この結果は Phase 12 で is_primary 切替を続行するか見送るかの判断材料として適切に引き継がれている（race-relative 行は is_primary=f で永続化済み）。

---

_Verified: 2026-06-27T17:30:00+09:00_
_Verifier: Claude (gsd-verifier)_
