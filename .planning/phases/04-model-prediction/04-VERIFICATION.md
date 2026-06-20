---
phase: 04-model-prediction
verified: 2026-06-20T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 1
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
behavior_unverified_items:
  - truth: "SC#3 leak diagnostic が live-data で target encoding 非混入を証明する（合成データでの対抗的構造診断は現状・Phase 8 で live-data 検証予定）"
    test: "live-data feature matrix で category_encoders 系 import 静的走査 + 実推論経路で target 由来 encoding 値が混入しないことを adversarial audit で検証"
    expected: "Phase 8 Adversarial Audit Suite が本件を別途検証し GREEN になること"
    why_human: "Phase 4 の test_no_target_encoding_leak は合成データでの対抗的構造診断（review HIGH#3 で live-data 証明と称さない）・静的 grep / unit test では live-data 経路の完全証明はスコープ外"
---

# Phase 4: Model & Prediction Verification Report

**Phase Goal:** A calibrated `p_fukusho_hit` estimate produced from odds-free Phase 1-A features, where the model adds measurable value over simple baselines and the market reference, with full reproducibility (ROADMAP.md L143)
**Verified:** 2026-06-20
**Status:** passed
**Re-verification:** No — initial verification

## Verification Posture

This verification treated the phase's two Core Values — **leak-free estimation** and **bit-identical reproducibility** — as load-bearing, not the SUMMARY's task-completion narrative. The SC#2 "beats baselines?" question is honestly unproven on the pre-registered gold metric (Calibration) and is by-design a Phase-6 gate decision per review HIGH#8 — NOT a Phase-4 blocker. Leak-prevention and reproducibility are verified against actual code and live DB, and they hold.

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth (SC)                                                                                                                                                                                                                                                                                  | Status     | Evidence (verified against codebase, not SUMMARY)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Train Phase 1-A model (LightGBM + CatBoost) off a **stamped Parquet snapshot ONLY** (never live DB); emit `p_fukusho_hit` with provenance (`model_version`, `feature_snapshot_id`, `as_of_datetime`)                                                                                          | ✓ VERIFIED | `src/model/data.py::load_feature_matrix()` arity-0 DB-free (`pq.read_table(SNAPSHOT_PATH)` only) — confirmed by grep (orchestrator `load_labels(`/`readonly_cur` count = 0). `FEATURE_COLUMNS` registry-derived allowlist; `make_X_y` asserts `X.columns == FEATURE_COLUMNS`. `test_load_from_parquet_only` / `test_raw_ids_excluded` / `test_no_banned_features` all PASS. Live DB `prediction.fukusho_prediction` has provenance columns populated: lightgbm=22,213 rows + catboost=22,213 rows with `model_version=20260620-1a-postreview-v2-{lgb,cb}-v1` (queried directly via psycopg). `predict.py` defines `PREDICTION_COLUMNS` with model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method.                                                                                                                                                                                                                                                                                  |
| 2   | BL-1..BL-5 evaluated alongside primary model producing a comparison table that answers "does the AI model add value over simple models and BL-3 market reference?"                                                                                                                          | ✓ VERIFIED (honest partial) | `reports/04-eval.md` + `reports/04-eval.json` contain the full comparison table (LightGBM + CatBoost + BL-1..5 with brier/logloss/auc/sum(p)/calibration_max_dev). `test_baseline.py` 8 tests PASS. **Honest annotation (review HIGH#8):** main model WINS on Brier/LogLoss/AUC (LightGBM best: brier=0.152216, logloss=0.474883, auc=0.732295) but LOSES on the pre-registered D-04 gold metric Calibration (`calibration_max_dev`: LightGBM=0.230769, CatBoost=0.257893 vs BL-1=0.001426, BL-4=0.044928). Documented as "AI 付加価値 部分証明" — correctly scoped to Phase-6 gate decision per HIGH#8. BL-2/BL-3 NaN (test-split market-data gap) and BL-4/BL-5 uncalibrated (`calibrate_bl4_bl5=False`) are honestly flagged in the report's notes + `bl_calib_note`/`market_reference` columns as Phase-6 items, NOT hidden. |
| 3   | Leak-safe categorical/missing handling: LightGBM native categorical non-negative codes + `__MISSING__`/`__UNSEEN__` sentinels (NaN→-1 forbidden); CatBoost `cat_features` + `has_time=True` on Pool sorted by `race_start_datetime`; NO target/mean encoding (verified by leak diagnostic) | ✓ VERIFIED | `src/model/trainer.py`: `LGB_INIT_PARAMS` has `deterministic=True/force_col_wise=True/num_threads=1`; `CB_INIT_PARAMS` has `has_time=True/thread_count=1/allow_writing_files=False`. `_prepare_lightgbm_matrix` asserts `.cat.codes.min() >= 0` for ALL_CAT_COLS (fail-loud on NaN→-1). `_prepare_catboost_pool` sorts by `["race_start_datetime","race_key"]` and casts HIGH_CARD_CODE_COLS via `astype(str)` into `cat_features` (HIGH#6: prevents imposing ordinal structure on IDs — MODL-03). **Target-encoding ban structurally enforced:** `test_no_target_encoding_imports_in_trainer_module` PASS; grep hits for `target_encoding`/`TargetEncoder` in `trainer.py`/`orchestrator.py` are docstring/comment-only (ban rules + test-name refs) — 0 actual API calls. `test_no_target_encoding_leak` PASS (adversarial structural diagnosis on synthetic data — honestly labeled, not live-data proof). |
| 4   | Calibration uses `CalibratedClassifierCV(cv='prefit', method='isotonic')` on strictly-later disjoint slice with unit test asserting `max(train.race_date) < min(calib.race_date)`; reproduce-smoke-test (fixed seeds → identical predictions on re-run) passes                                | ✓ VERIFIED | `src/model/calibrator.py` wraps `fit_prefit_calibrator` (isotonic≥1000 / sigmoid<1000). `split_3way` raises ValueError on `train_max < calib_min < calib_max < test_min <= test_max` violation (grep confirms guards in `data.py`). `test_strict_later_disjoint` PASS. `FIXED_REPRODUCE_TS = datetime(2026,6,20,tzinfo=UTC)` + `num_threads=1`/`thread_count=1` + `seed=42` in orchestrator. `test_reproduce_bit_identical` PASS (both models `np.array_equal`). `--check-reproduce` reported PASS for both models on live data (VALIDATION L104-106). **Behavior-dependent truth, behavioral evidence produced** (single named test PASSES). |

**Score:** 4/4 truths verified (1 with honest Phase-6-deferred calibration caveat on SC#2; 1 behavior-unverified caveat on SC#3 live-data proof)

### Deferred Items (Step 9b — explicitly addressed in later milestone phases)

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | SC#2 final verdict — main model loses on pre-registered Calibration metric | Phase 6 (Evaluation & Calibration Gates) | ROADMAP Phase 6 Goal: "probability quality acceptance criteria are verified before any result is shown to a user — calibration, Brier, LogLoss..." + 04-06-SUMMARY "SC#2 AI 付加価値 最終判定 ... Phase 6" |
| 2 | BL-2/BL-3 market-data NaN (test-split data-availability gap) | Phase 6 | 04-06-SUMMARY Deferred Issues table; reports/04-eval.md `market_reference` note |
| 3 | BL-4/BL-5 calibration fairness (`calibrate_bl4_bl5=False`) | Phase 6 | 04-06-SUMMARY Deferred Issues; reports/04-eval.md `bl_calib_note` |
| 4 | SC#3 live-data target-encoding audit | Phase 8 (Adversarial Audit Suite) | 04-06-SUMMARY: "SC#3 live-data target encoding 検証 ... Phase 8"; SC#3 explicitly labeled "対抗的構造診断" not live-data proof |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/model/data.py` | Parquet-only loader + FEATURE_COLUMNS + 3way split + SHA256 verify | ✓ VERIFIED | 29k; `load_feature_matrix` arity-0; `RAW_ID_COLUMNS` excluded; `split_3way` raise-guards; `verify_snapshot_sha256` metadata-excluded scope |
| `src/model/calibrator.py` | `fit_prefit_calibrator` wrapper + isotonic/sigmoid switch | ✓ VERIFIED | 5.0k; imports `fit_prefit_calibrator`; thin wrapper per PATTERNS |
| `src/model/artifact.py` | base+calibrator split save + load roundtrip | ✓ VERIFIED | 18k; `save_native_artifact`/`load_native_artifact`; calibrator.joblib required (FileNotFoundError) |
| `src/model/trainer.py` | LightGBM native cat + CatBoost has_time + leak diagnostic | ✓ VERIFIED | 43k; non-negative code assert; `has_time=True`; `_prepare_catboost_pool` sort; `align_predictions` 5-cond guard |
| `src/model/baseline.py` | BL-1..5 + market-data source | ✓ VERIFIED | 24k; `compute_bl1..5` + `compute_all_baselines` + `fetch_market_data` |
| `src/model/predict.py` | provenance DataFrame + make_model_version | ✓ VERIFIED | 16k; `PREDICTION_COLUMNS`; `pred_proba` injection (NEW HIGH-1); `as_of_datetime` controllable |
| `src/model/evaluator.py` | metrics + comparison table + report writer | ✓ VERIFIED | 21k; `CALIBRATION_CURVE_BINS=10`; `SUM_P_BOUNDS`; D-04 `d04_selection_criterion` column |
| `src/model/orchestrator.py` | train_and_predict + bit-identical + no circular import | ✓ VERIFIED | 33k; `FIXED_REPRODUCE_TS`; `_assert_deterministic`; one-direction imports; 0 `load_labels(`/`readonly_cur` |
| `src/db/prediction_load.py` | model_version-scoped staging-swap idempotent | ✓ VERIFIED | 17k; `DELETE WHERE model_type+model_version` (preserves other models); advisory lock; `SELECT *` count = 0 (NEW-3) |
| `scripts/run_train_predict.py` | both-models E2E entrypoint | ✓ VERIFIED | 25k; 6 argparse; masked DSN; `--check-reproduce` |
| `reports/04-eval.md` + `reports/04-eval.json` | comparison table + honest notes | ✓ VERIFIED | both on disk; BL-2/3 NaN + BL-4/5 uncalibrated + D-04 pre-registered criterion all annotated |
| `models/{version}/` artifacts | base + calibrator + metadata | ✓ VERIFIED | on disk (.gitignored); 6 files across lgb-v1 + cb-v1; SHA256 recorded in VALIDATION |
| `prediction.fukusho_prediction` (live DB) | both models persisted | ✓ VERIFIED | queried directly: catboost 22,213 + lightgbm 22,213 rows with correct model_version |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `data.py` | snapshot Parquet | `pq.read_table(SNAPSHOT_PATH)` | ✓ WIRED | SC#1 Parquet-only |
| `data.py` | `features/availability.py` | `assert_matrix_columns_registered` + `banned_features(spec)==[]` | ✓ WIRED | double-check; MODL-01 odds-free |
| `orchestrator.py` | `trainer.py` + `calibrator.py` + `predict.py` | one-direction imports | ✓ WIRED | `test_no_circular_import` PASS |
| `orchestrator.py` | `predict.py` (aligned pred_proba) | `predict_p_fukusho(..., pred_proba=pred_proba)` | ✓ WIRED | NEW HIGH-1; `test_catboost_pred_proba_injection` PASS |
| `prediction_load.py` | `prediction.fukusho_prediction` (live DB) | staging-swap idempotent | ✓ WIRED | 2-run checksum bit-identical (VALIDATION L114) |
| `run_train_predict.py` | orchestrator + load_predictions + evaluator | integration | ✓ WIRED | exit 0 on `--model-type both --check-reproduce` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `prediction.fukusho_prediction` (live) | `p_fukusho_hit` | trained LightGBM/CatBoost on 552,935-row feature_df → 22,213 test predictions | ✓ Real (checksum `72713b7a...`/`268687d5...`) | ✓ FLOWING |
| `reports/04-eval.{md,json}` | comparison table metrics | `evaluate_all_models` on predictions_by_model | ✓ Real (numeric metrics, not static) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| SC#1 Parquet-only / raw-ID / banned-features / race_id disjoint | `pytest tests/model/test_data.py::{those 4}` (subset of 6-test run) | 6 passed in 18.09s | ✓ PASS |
| SC#3 leak diagnostic (no target encoding) | `pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x` | passed (part of 6-test run) | ✓ PASS |
| SC#4 reproduce bit-identical | `pytest tests/model/test_orchestrator.py::test_reproduce_bit_identical -x` | passed (part of 6-test run) | ✓ PASS |
| SC#4 strict-later disjoint | `pytest tests/model/test_calibrator.py::test_strict_later_disjoint -x` | passed (part of 6-test run) | ✓ PASS |
| live DB prediction persistence | psycopg `SELECT model_type, model_version, count(*)` | catboost=22,213 + lightgbm=22,213 | ✓ PASS |
| target-encoding API ban (static) | `grep -rE "TargetEncoder\|category_encoders"` in src/model | only docstring/comment hits, 0 actual API calls | ✓ PASS |

### Probe Execution

Phase 4 has no `scripts/*/tests/probe-*.sh` conventional probes. The functional equivalent — `KEIBA_SKIP_DB_TESTS unset && uv run pytest` — was run during PLAN 06 and recorded in 04-VALIDATION.md (262 passed / 0 skipped / 0 failed, 315–321s). Spot-checked named tests re-run during this verification (6 passed). SKIPPED per Phase-4 verification contract.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| MODL-01 | 04-01/02/04/05/06 | Phase 1-A model (odds-free features) training/prediction | ✓ SATISFIED | `load_feature_matrix` Parquet-only; `FEATURE_COLUMNS` allowlist; `banned_features==[]`; live prediction table 22,213×2 rows; tests PASS |
| MODL-02 | 04-03/04/05/06 | BL-1..5 evaluation + comparison table | ✓ SATISFIED (partial, honestly deferred to Phase 6) | `compute_bl1..5` + `compute_all_baselines`; `reports/04-eval.{md,json}` comparison table; AI beats BL on Brier/LogLoss/AUC, loses on Calibration (D-04) — Phase-6 final verdict |
| MODL-03 | 04-02/03/05/06 | Time-series-safe categorical/missing handling (no target encoding, non-neg codes, has_time) | ✓ SATISFIED | `trainer.py` LightGBM native cat + non-neg code assert; CatBoost `has_time=True` + `cat_features` with `_code` as `str`; `test_no_target_encoding_imports_in_trainer_module` PASS |

No orphaned requirements — all MODL-01/02/03 IDs claimed in PLAN frontmatter are present in REQUIREMENTS.md and mapped to Phase 4.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No TBD/FIXME/XXX/PLACEHOLDER/empty-return patterns in src/model, src/db/prediction_load.py, scripts/run_train_predict.py | — | Code is clean |

### Human Verification Required

None mandatory. The one behavior-unverified item (SC#3 live-data target-encoding audit) is explicitly deferred to Phase 8 Adversarial Audit Suite (ROADMAP SC#1: "categorical/missing handling (no target encoding, no NaN→-1)" is a Phase-8 acceptance criterion) and is NOT a Phase-4 gap. Phase 4's SC#3 evidence is honestly labeled "対抗的構造診断" (adversarial structural diagnosis on synthetic data) per review HIGH#3, not overclaimed as live-data proof.

### Honest Caveats (NOT gaps — correctly scoped to later phases)

1. **SC#2 is honestly partial.** The main model beats BL-1/BL-4/BL-5 on Brier/LogLoss/AUC (ordering ability) but loses on the pre-registered D-04 gold metric Calibration (`calibration_max_dev`). This is honestly annotated as "AI 付加価値 部分証明" and explicitly routed to Phase 6 for the final verdict. Phase 4 does NOT overclaim model victory. Per the user's explicit instruction and review HIGH#8, this is a Phase-6 gate decision and NOT a Phase-4 blocker.

2. **BL-2/BL-3 produce NaN** on the 2024-H2 test split due to a genuine market-data availability gap (not a bug). Honestly annotated in `reports/04-eval.md` (`market_reference` note) + `04-eval.json` and deferred to Phase 6.

3. **BL-4/BL-5 are uncalibrated** (`calibrate_bl4_bl5=False`) due to a baseline.py constraint (LightGBM categorical preprocessing doesn't run through the calibrator path). Honestly annotated in `bl_calib_note` column and deferred to Phase 6 for fair comparison.

4. **SC#3 leak diagnostic is synthetic-data adversarial structural diagnosis**, not live-data proof. Honestly labeled per review HIGH#3; live-data audit deferred to Phase 8 (ROADMAP Phase 8 SC#1 explicitly covers "categorical/missing handling (no target encoding, no NaN→-1)").

5. **REQUIREMENTS.md status-table drift** (cosmetic): the traceability table at L123-125 still lists MODL-01/MODL-03 as "In Progress" while the checklist at L32-34 marks them `[x]` complete. Implementation is complete (verified); the table is stale. Non-blocking.

### Gaps Summary

**No gaps found.** All 4 success criteria are verified against actual code and live DB. The two Core Values of the phase — leak-free estimation and bit-identical reproducibility — are demonstrably achieved in code with passing behavioral tests. The SC#2 "beats baselines?" question is honestly partial on the pre-registered Calibration metric and is by-design a Phase-6 gate decision, not a Phase-4 blocker (per user instruction and review HIGH#8). SC#3's live-data target-encoding audit is honestly deferred to Phase 8.

Phase 4 goal (calibrated leak-free reproducible `p_fukusho_hit` pipeline with honest evaluation) is **achieved**.

---

_Verified: 2026-06-20_
_Verifier: Claude (gsd-verifier)_
