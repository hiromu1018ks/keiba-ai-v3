---
phase: 11
reviewers: [codex]
cycles:
  - cycle: 1
    reviewed_at: 2026-06-27T12:30:00+09:00
    plans_reviewed: [11-01-PLAN.md, 11-02-PLAN.md, 11-03-PLAN.md, 11-04-PLAN.md, 11-05-PLAN.md]
    verification_method: "codex review output cross-checked against live source by reviewer agent (8/8 HIGH claims traced to file:line)"
    outcome: "6 HIGH + 4 MEDIUM raised; planner revised all 5 PLAN.md (commits dcde63c + d86fcd6)"
  - cycle: 2
    reviewed_at: 2026-06-27T15:10:00+09:00
    plans_reviewed: [11-01-PLAN.md, 11-02-PLAN.md, 11-03-PLAN.md, 11-04-PLAN.md, 11-05-PLAN.md]
    revision_base: "dcde63c + d86fcd6 (post cycle-1 revisions)"
    verification_method: "codex (gpt-5.2, xhigh) re-reviewed revised plans; reviewer agent re-traced all 3 new HIGH + 3 MEDIUM/LOW claims against src/ (all VALID)"
    outcome: "5/6 cycle-1 HIGHs FULLY RESOLVED, 1 PARTIALLY; 3 NEW HIGH live-DB blockers found; 3 actionable MEDIUM/LOW remain"
    current_high: 4
    current_actionable: 3
---

# Cross-AI Plan Review — Phase 11 (Race-Relative Probability Model)

> Reviewer: **Codex** (codex-cli, `codex exec --ephemeral --skip-git-repo-check`).
> Source-grounding: Codex ran inside the repo working tree and cited `file:line` evidence. An independent verification pass re-traced each HIGH claim against the live source (7/8 VALID, 1 PARTIAL, plus 1 Codex-asserted numerical concern disproven). Verified findings are folded into the consensus below; the one Codex error (brentq bracket) is recorded under Divergent Views.

---

## Codex Review

### Overall Assessment

The plan set has a strong core architecture: keep the v1.0 binary learners intact and add a pure race-relative correction layer. That fits the repo's existing separation of trainer/calibrator/predict/persistence responsibilities. The biggest issues are not the `brentq` math; they are **integration and leakage controls**. In particular, the current `orchestrator.train_and_predict` only emits test-split predictions, so the planned theta-selection loop can easily select θ on the test window unless a new calib-scoring path is added. SC#5 also has concrete API/schema mismatches: the plan calls the private persistence function with the wrong input type, and the prediction table columns do not currently contain all required §19.1 metadata.

### Plan-by-Plan Review

#### 11-01 (Wave 0: stub + TDD RED)

**Summary:** Solid TDD setup plan. It correctly isolates the new API in `src/model/race_relative.py` and does not touch the binary model stack. Main risk is that some test contracts are weak or ambiguous, especially around AST scanner scope and "bit-identical" wording.

**Strengths:**
- The plan's binary-invariant boundary is sound: `trainer.py` owns binary LightGBM/CatBoost config today, including `objective="binary"` and deterministic thread settings in `src/model/trainer.py:83` and `src/model/trainer.py:96`.
- Reusing the existing audit pattern is appropriate; the Phase 10 scanner already checks forbidden market tokens through AST traversal in `tests/audit/test_audit_field_strength.py:49` and `tests/audit/test_audit_field_strength.py:91`.
- The planned module does not need to touch feature construction; `make_X_y` already enforces the registered feature allowlist and banned-feature guard in `src/model/data.py:478`.

**Concerns:**
- **MEDIUM:** The plan says SC#4 checks only Name/Attribute tokens, while the existing audit scanner also inspects string constants in `tests/audit/test_audit_field_strength.py:91`. If copied inconsistently, the new audit may either be weaker than the established pattern or fail on harmless docstrings.
- **MEDIUM:** The planned "both models bit-identical" test is ambiguous. Existing deterministic tests compare repeated runs, not LightGBM predictions against CatBoost predictions, e.g. `tests/model/test_orchestrator.py:328`.
- **LOW:** The stub does not plan invalid-input contracts for `theta`, `k`, or per-race `k` consistency; those should be part of the API contract before Wave 1.

**Suggestions:**
- Define SC#3 as "same model + same inputs + same seed produces identical output," not LightGBM equals CatBoost.
- Add RED tests for `theta <= 0`, `k <= 0`, `k >= n`, non-finite logits, and inconsistent `k_per_race` within a race.
- Match the established scanner behavior explicitly: either Name/Attribute only by requirement, or string constants with a whitelist.

**Risk:** LOW-MEDIUM.

#### 11-02 (Wave 1: race_relative.py implementation)

**Summary:** The core correction math is mostly sound, and the planned `brentq` bounds are wide enough for the preregistered θ range. The main weakness is the "bit-identical binning" claim: the plan recreates p-bin logic locally instead of actually reusing the evaluator's calibration-bin helper.

**Strengths:**
- The `brentq` bracket is numerically reasonable for `P_CAL_CLIP_EPSILON=1e-6` and θ in `{0.5, 0.75, 1.0, 1.25, 1.5}`: clipped logits are about ±13.8, so even at θ=0.5, α bounds ±100 force sums near 0 and near n.
- The k rule is consistent with existing code: `src/model/baseline.py:78` implements `>=8 -> 3`, `5-7 -> 2`, and raises below 5.
- The intended odds-band source exists and is deterministic: `_odds_band` delegates to fixed `ODDS_BAND_EDGES` in `src/model/segment_eval.py:151`.

**Concerns:**
- **HIGH:** `compute_overprediction_penalty` plans to create a local `_p_bin` with `np.linspace`. The actual reusable contract is `_compute_calibration_curve_bins` in `src/model/evaluator.py:386`, and `segment_eval` already imports it at `src/model/segment_eval.py:53`. Local binning may be equivalent today, but it is not true import-level parity.
- **MEDIUM:** The plan checks finite `p_cal`, but not `theta > 0`, `0 < k < n`, non-empty race groups, or race-level `k_per_race` uniqueness. Those are fail-loud conditions for this phase.
- **MEDIUM:** `test_theta_zero_divergence` can be brittle unless the logits are constructed to force bracket failure; θ=1e-3 does not universally prove divergence for every synthetic vector.

**Suggestions:**
- Build overpayment penalty by grouping odds bands, then calling `_compute_calibration_curve_bins(..., strategy="uniform", n_bins=CALIBRATION_CURVE_BINS)` per band.
- Add explicit guards before `brentq`, and raise `RuntimeError` or `ValueError` with D-09 wording.
- Keep k determination out of `race_relative.py` unless a small tested helper is added; otherwise assert the caller-provided k is valid.

**Risk:** MEDIUM.

#### 11-03 (Wave 2: orchestrator integration + artifact metadata + predict short)

**Summary:** The integration point is correct: `orchestrator` already computes calibrated probabilities and injects them into `predict_p_fukusho`. However, the plan under-specifies model-type normalization and uses a risky fallback for k.

**Strengths:**
- `predict_p_fukusho` already supports injected probabilities via `pred_proba` and validates index/length in `src/model/predict.py:222`, which is the right hook for the corrected p.
- The LightGBM and CatBoost prediction paths are clearly separated and line up with the plan: LightGBM at `src/model/orchestrator.py:524`, CatBoost at `src/model/orchestrator.py:534`.
- `train_and_predict` returns a dict at `src/model/orchestrator.py:599`, so adding `race_relative_theta` provenance is straightforward.

**Concerns:**
- **HIGH:** Current `orchestrator` only accepts `model_type == "lightgbm"` or `"catboost"` and raises otherwise in `src/model/orchestrator.py:448` and `src/model/orchestrator.py:488`. *(Verification: raise confirmed at :487-491. However, 11-03 Task 2 L150-154 DOES specify a `_normalize_model_type` helper to be added in Task 1 — so the concern is real for execution but the plan does contain the mitigation. Reviewer should ensure the normalization lands in Task 1, not just Task 2.)*
- **HIGH:** The fallback from `sales_start_entry_count` to race group size is unsafe. `sales_start_entry_count` is already selected by `load_labels` in `src/model/data.py:361` and carried through `build_training_frame` in `src/model/data.py:393`; missing/inconsistent values should fail loud, not infer from filtered rows. *(Verification: VALID — column is always present when labels are loaded; fallback branch is dead code that weakens D-08/D-09.)*
- **MEDIUM:** Artifact metadata is added to `save_native_artifact`, but no call site is updated to pass `race_relative_theta`; existing artifact saving in `scripts/run_train_predict.py:322` would still write `None`.
- **MEDIUM:** SC#5 metadata is not fully addressed. `PREDICTION_COLUMNS` in `src/model/predict.py:63` does not include `label_version`, `odds_snapshot_policy`, or `backtest_strategy_version`.

**Suggestions:**
- Add `base_model_type = normalize_model_type(model_type)` and use base type for training/calibration branches, while preserving original model type for version/provenance.
- Require `sales_start_entry_count` and assert one k per race.
- Add a theta=None regression test that monkeypatches `apply_race_relative_correction` and proves it is not called.
- Decide where §19.1 metadata lives: prediction schema, artifact metadata, or report. If it must be in DB rows, plan a migration.

**Risk:** HIGH.

#### 11-04 (Wave 3: D-10 adversarial + run_phase11_evaluation.py)

**Summary:** This is the riskiest plan. The evaluation script is where the test-window sanctuary must be enforced, but the current orchestrator only produces test predictions. As written, θ selection can accidentally use the test window. The selected/high-EV gate also lacks a clear odds/EV construction path.

**Strengths:**
- The plan correctly uses existing metric machinery: `compute_metrics` computes Brier, LogLoss, AUC, sum(p), and calibration metrics in `src/model/evaluator.py:172`.
- The Phase 10 script is a good pattern for loading features/labels/maps and calling `train_and_predict`, as seen in `scripts/run_phase10_evaluation.py:347` and `scripts/run_phase10_evaluation.py:429`.
- Not calling `set_primary_model` is consistent with D-07; that mutating function is separate in `src/db/prediction_load.py:447`.

**Concerns:**
- **HIGH (critical):** Current `train_and_predict` predicts only `X_test`: the split is made at `src/model/orchestrator.py:378`, `X_test` is built at `src/model/orchestrator.py:390`, and `predict_p_fukusho(... split_label="test")` is called at `src/model/orchestrator.py:566`. A θ loop using BT-1 directly would select on the test window. *(Verification: VALID and load-bearing — this is a §11.2 sanctuary violation if executed as written. There is no calib-scoring path in the current API.)*
- **HIGH:** D-05 selected/high-EV metrics require fixed odds and EV selection. Existing EV logic depends on odds columns in `src/ev/ev_rank.py:80`, and purchase selection thresholds are in `src/ev/purchase_simulator.py:85`. The plan does not specify the odds snapshot join or selected-flag construction.
- **MEDIUM:** `test_alpha_self_contained_outcome_swap` has weak detection power if it only repeats `solve_alpha_for_race` and inspects the signature. A leak in orchestrator or in a global side channel would still pass.
- **LOW:** The plan says report writes are atomic, but the Phase 10 analogue uses direct `write_text` at `scripts/run_phase10_evaluation.py:735`.
- **LOW:** The acceptance grep for `set_primary_model` conflicts with documenting "do not call set_primary_model"; a docstring mention would make the grep nonzero.

**Suggestions:**
- Add an explicit calib-scoring path before this script: either `predict_split="calib"` or a helper that trains on train and scores the original calib slice only.
- Write `theta-selection.json` before any test-window evaluation and include the source split dates.
- Reuse the existing odds/backtest loading path and `compute_ev_and_rank`/`select_bets` to define selected/high-EV consistently.
- Strengthen D-10 tests with interleaved race IDs and a monkeypatch/source scan proving no outcome columns are referenced.

**Risk:** HIGH.

#### 11-05 (Wave 4: live-DB SC#2/SC#3/SC#5 checkpoint)

**Summary:** The live-DB goals are right, but the plan has concrete sequencing and API mismatches. The checkpoint asks the user to verify persistence before the plan has added persistence, and it calls the private idempotent loader incorrectly.

**Strengths:**
- The persistence layer can support model-version scoped replacement: delete scope is constrained to one `model_type/model_version` in `src/db/prediction_load.py:312`.
- The public wrapper already performs DataFrame-to-row conversion and checksum return in `src/db/prediction_load.py:373`.
- `_assert_deterministic` is a reasonable reproducibility hook; it already runs `train_and_predict` twice and compares probabilities in `src/model/orchestrator.py:773`.

**Concerns:**
- **HIGH:** Task ordering is broken. Task 1 asks the user to verify SC#5 persistence, but Task 2 is where persistence is added. Wave 3 explicitly leaves live persistence to Wave 4. *(Verification: VALID — 11-05 Task 1 L102-108 verifies idempotent swap; Task 2 L147 adds the call. Inverted.)*
- **HIGH:** `_idempotent_load_prediction` takes `rows: list[tuple]`, not a prediction DataFrame, at `src/db/prediction_load.py:191`. The plan should call `load_predictions` at `src/db/prediction_load.py:373` or convert rows explicitly. *(Verification: VALID — 11-05 Task 2 L149-150 imports the private fn and passes pred_df directly. Wrong API.)*
- **HIGH:** Prediction rows cannot currently carry all requested SC#5 metadata. `src/model/predict.py:63` lists the table columns and does not include `label_version`, `odds_snapshot_policy`, or `backtest_strategy_version`. *(Verification: VALID — PREDICTION_COLUMNS L63-86 confirmed missing the three §19.1 keys.)*
- **MEDIUM:** `files_modified` omits `src/model/orchestrator.py`, but Task 2 modifies `_assert_deterministic`. That violates the plan's own change declaration. *(Verification: VALID — 11-05 frontmatter L8-10 lists only run_phase11_evaluation.py and test_race_relative.py.)*
- **MEDIUM:** The LightGBM/CatBoost bit-identical wording is ambiguous. It should mean repeatability within each model family, not equality across model families.

**Suggestions:**
- Move the idempotent persistence and deterministic smoke implementation before the human checkpoint.
- Use `load_predictions`, not `_idempotent_load_prediction`, unless rows are explicitly built with the existing converter.
- Add a schema migration or change SC#5 wording to store missing metadata in artifact/report only.
- Add `src/model/orchestrator.py` to `files_modified` if `_assert_deterministic` is changed.

**Risk:** HIGH.

### Cross-Plan Concerns

- **Theta selection leakage is the top issue.** Existing code only scores the test split through `train_and_predict`; without a calib-scoring path, D-03 can be violated even if the script docstring says otherwise.
- **D-01 is mostly honored, but not perfectly documented.** Plans avoid `trainer.py`, `calibrator.py`, `data.py`, `evaluator.py`, and `segment_eval.py`; however 11-05 plans an orchestrator edit not declared in frontmatter.
- **Bit-identical binning is overstated.** Importing `_odds_band` is good, but local p-bin code is not the same as reusing `_compute_calibration_curve_bins`.
- **k should be fail-loud.** The repo already provides `sales_start_entry_count`; fallback to group size weakens D-08/D-09.
- **SC#5 is not currently achievable as written.** Persistence API usage, metadata columns, and task ordering all need correction.

### Risk Assessment

Overall risk is **HIGH** until the calib-only θ selection path and SC#5 persistence/metadata design are fixed. The race-relative correction layer itself is a reasonable low-to-medium-risk addition, but the evaluation and DB checkpoint plans currently have enough leakage and reproducibility gaps to undermine Phase 11's core value.

---

## Reviewer Verification Pass (source-grounding audit)

Each HIGH claim in the Codex review was re-traced against the live source. Result:

| # | Claim | Code reference | Verdict |
|---|-------|----------------|---------|
| 1 | 11-02 local `_p_bin` via `np.linspace` not `_compute_calibration_curve_bins` | `evaluator.py:386-393`, `segment_eval.py:54-61` import it; 11-02 Task 2 L152-154 defines local `_p_bin` | **VALID** — plan action contradicts its own must_haves "import 再利用 bit-identical" |
| 2 | 11-03 orchestrator raises on unknown model_type | `orchestrator.py:448/466/487-491` raise confirmed | **PARTIAL** — raise behavior VALID; but 11-03 Task 2 L150-154 DOES specify a `_normalize_model_type` helper (mitigation exists in plan, must land in Task 1) |
| 3 | 11-03 `sales_start_entry_count` fallback unsafe | `data.py:361/371/393` column always present via label JOIN | **VALID** — fallback branch is dead code, weakens D-08/D-09 |
| 4 | 11-03 PREDICTION_COLUMNS missing §19.1 metadata | `predict.py:63-86` confirmed: no `label_version`/`odds_snapshot_policy`/`backtest_strategy_version` | **VALID** |
| 5 | 11-04 θ selection would score test window | `orchestrator.py:380-383/390/566-577`; no calib-scoring path exists | **VALID (critical)** — executing 11-04 as written violates §11.2 sanctuary / D-03 |
| 6 | 11-05 `_idempotent_load_prediction` takes `rows: list[tuple]` not DataFrame | `prediction_load.py:191-196`; public wrapper `load_predictions` at `:373` | **VALID** — 11-05 Task 2 L149-150 uses wrong API |
| 7 | 11-05 Task ordering inversion (verify before build) | 11-05 Task 1 L102-108 vs Task 2 L147 | **VALID** |
| 8 | 11-05 `files_modified` omits orchestrator.py | 11-05 frontmatter L8-10 vs Task 2 L156 modifies `_assert_deterministic` | **VALID** |
| — | brentq bracket `(-100,100)` too narrow | math: clipped logits ±13.8 × θ ∈ {0.5..1.5} × k ∈ {2,3} always gives f(-100)<0<f(100) | **INVALID (Codex error)** — bracket is sound; concern rejected |

**Bottom line:** 7/8 HIGH claims VALID, 1 PARTIAL, 1 additional Codex numerical concern disproven. The review is high-signal and the HIGHs must be addressed before execution.

---

## Consensus Summary

### Agreed Strengths (plan gets these right)

- **D-01 binary invariant boundary** is correctly drawn: `trainer.py` owns `objective='binary'` and deterministic thread settings (`trainer.py:83/96`), and all five plans keep `files_modified` inside the new layer (`race_relative.py`, `orchestrator.py`, `artifact.py`, `predict.py`, eval script, tests). The binary core (`trainer/calibrator/data/evaluator/segment_eval`) is untouched in 11-01/11-02/11-03/11-04.
- **TDD RED-then-GREEN discipline** in Wave 0/1 is structurally sound: stub raises `NotImplementedError`, tests assert contracts first, Wave 1 fills in.
- **brentq numerics** are sound for the preregistered θ range and clip ε; the bracket `(-100, 100)` provably bounds the root for all θ/k/n combinations used (verification pass disproved the one numerical concern).
- **D-07 `is_primary` discipline** is correctly maintained — no plan calls `set_primary_model` (`prediction_load.py:447`), preserving v1.0 binary as the live model until Phase 12.
- **Persistence layer capability** for model_version-scoped swap exists (`prediction_load.py:312` DELETE scope + `:373` public wrapper), so SC#5 is achievable once the API is called correctly.
- **AST forbidden-token audit** reuses the Phase 8/10 5-stage template from `tests/audit/test_audit_field_strength.py`.

### Agreed Concerns (HIGH — must address before execution)

1. **θ selection leaks into the test window (§11.2 / D-03 violation)** — `orchestrator.train_and_predict` only scores `X_test` (`orchestrator.py:390/566`). 11-04 Task 2 instructs "call `train_and_predict(theta=θ_i)` on the calib slice" but the API has no calib-scoring path. As written, the θ loop scores the test window and violates the project's core sanctuary. **Fix:** add a `score_split="calib"` (or equivalent helper) to `train_and_predict` in 11-03, and have 11-04 use only that path for θ selection; write `theta-selection.json` before any test-window evaluation.

2. **`compute_overprediction_penalty` "bit-identical binning" is overstated** — 11-02 Task 2 L152-154 defines a local `_p_bin` via `np.linspace`, while the actual reusable contract is `_compute_calibration_curve_bins` (`evaluator.py:386`, already imported by `segment_eval.py:54-61`). The plan's must_haves claims "import 再利用 bit-identical" but the action does not. **Fix:** reuse `_compute_calibration_curve_bins(..., strategy="uniform", n_bins=CALIBRATION_CURVE_BINS)` per odds band, or extract shared bin edges.

3. **SC#5 §19.1 metadata cannot be persisted in prediction rows** — `PREDICTION_COLUMNS` (`predict.py:63-86`) lacks `label_version`, `odds_snapshot_policy`, `backtest_strategy_version`. **Fix:** either add a schema migration to 11-05, or explicitly relocate those three fields to artifact metadata / report and reword SC#5 accordingly.

4. **11-05 calls the wrong persistence API** — `_idempotent_load_prediction` (`prediction_load.py:191`) takes `rows: list[tuple]`, not a DataFrame; 11-05 Task 2 L149-150 imports the private fn and passes `pred_df`. **Fix:** call the public `load_predictions` (`prediction_load.py:373`) which does the DataFrame→row conversion.

5. **11-05 task ordering inversion** — Task 1 (human checkpoint) asks the user to verify SC#5 idempotent swap, but Task 2 is where the swap call is added. **Fix:** move the persistence + deterministic-smoke implementation into a pre-checkpoint task, or reorder Task 1/Task 2.

6. **11-03 `sales_start_entry_count` fallback is unsafe dead code** — the column is always present via `load_labels` (`data.py:361/371`) and `build_training_frame` (`data.py:393`). The "fallback to groupby size" branch can never fire legitimately and silently weakens D-08/D-09 if it ever does. **Fix:** require the column and fail loud on missing/inconsistent values.

### Divergent Views (reviewer vs plan)

- **brentq bracket `(-100, 100)`:** Codex flagged this as potentially risky; the verification pass disproved the concern mathematically (f(-100)<0<f(100) for all θ ∈ {0.5..1.5}, k ∈ {2,3}, n ∈ {5,8,18}, and extreme clipped-logit vectors). **No change needed.**
- **11-03 model_type normalization:** Codex flagged that the orchestrator raises on unknown model_type and the plan doesn't address it. The plan DOES specify a `_normalize_model_type` helper (Task 2 L150-154), so this is a PARTIAL — the mitigation exists but the acceptance criteria must guarantee it lands in Task 1 (where `train_and_predict` is edited), not be deferred to Task 2.

---

## Verification coverage

The table below maps each HIGH concern to where it must be resolved (PLAN.md task) so `/gsd-execute-phase` cannot proceed without addressing it.

| HIGH concern | Owning plan | Required PLAN.md change |
|---|---|---|
| θ selection leaks into test window | 11-03 (API) + 11-04 (use) | 11-03 Task 1: add `score_split="calib"` (or helper) to `train_and_predict` + acceptance test; 11-04 Task 2: use only the calib-scoring path for θ loop, write `theta-selection.json` before test eval |
| `_p_bin` not truly reusing `_compute_calibration_curve_bins` | 11-02 | Task 2 action: replace local `_p_bin` with call to `_compute_calibration_curve_bins(..., strategy="uniform", n_bins=CALIBRATION_CURVE_BINS)` per odds band; update must_haves to match |
| §19.1 metadata missing from PREDICTION_COLUMNS | 11-05 | Add schema migration task OR explicitly relocate the three fields to artifact/report and reword SC#5 acceptance |
| Wrong persistence API (`_idempotent_load_prediction` vs `load_predictions`) | 11-05 | Task 2 action: call `load_predictions` (public) instead; update import + acceptance |
| 11-05 task ordering inversion | 11-05 | Reorder: move persistence + deterministic-smoke implementation before the `checkpoint:human-verify` task |
| `sales_start_entry_count` fallback unsafe | 11-03 | Task 1 action: require column, fail loud on missing; delete the groupby-fallback branch |

---

# Cycle 2 Review — REVISED plans (post dcde63c + d86fcd6)

> Reviewer: **Codex** (codex-cli 0.142.1, `codex exec --ephemeral --skip-git-repo-check -s read-only`, model gpt-5.2, reasoning xhigh).
> Method: Codex re-reviewed the revised PLAN.md set against the live source tree. An independent verification pass by the reviewer agent re-traced every claim below against `src/` — all 3 new HIGHs and all 3 actionable items are **VALID** (file:line confirmed). The 6 cycle-1 HIGHs were re-adjudicated against the revised plan text.
>
> **Bottom line:** 5 of 6 cycle-1 HIGHs are FULLY RESOLVED in the revised plans; 1 (HIGH#3 SC#5 metadata) is PARTIALLY RESOLVED (schema/columns/wiring now planned, but the loader-compatibility sub-issue is newly discovered). 3 NEW HIGHs were found — all are live-DB blockers that would prevent SC#5 from being demonstrated. Overall risk remains **HIGH**.

---

## Cycle-1 HIGH re-adjudication (revised PLAN.md vs live source)

| # | Cycle-1 HIGH | Verdict | Evidence (revised plan + live source) |
|---|---|---|---|
| 1 | θ selection leaks into test window | **FULLY RESOLVED** | 11-03 adds `score_split="calib"` routing `X_calib`/`race_df_score` (11-03-PLAN.md:89-107); 11-04 θ loop calls `score_split="calib"` only + writes `theta-selection.json` before test eval (11-04-PLAN.md:171-173). Live: orchestrator builds `X_calib`/`X_test` at orchestrator.py:388-390, scores only `X_test` today at orchestrator.py:524-577 — plan targets the right seam. |
| 2 | `_p_bin` not truly reusing `_compute_calibration_curve_bins` | **FULLY RESOLVED** | 11-02 imports `CALIBRATION_CURVE_BINS`/`_compute_calibration_curve_bins`/`_odds_band`, forbids local `_p_bin`/`np.linspace` (11-02-PLAN.md:156-170); acceptance greps `np.linspace` count == 0 (11-02-PLAN.md:184). Live: `_compute_calibration_curve_bins` at evaluator.py:386-393; `_odds_band` at segment_eval.py:151-158. |
| 3 | §19.1 metadata missing from `PREDICTION_COLUMNS` | **PARTIALLY RESOLVED** | 11-05 Task 1 adds the 3 columns to schema + `PREDICTION_COLUMNS` + `predict_p_fukusho` (11-05-PLAN.md:109-125); Task 2 wires orchestrator→predict_p_fukusho (11-05-PLAN.md:192-216). Live: `PREDICTION_COLUMNS` still 16 cols ending at `is_primary` (predict.py:63-86); DDL lacks the columns (schema.py:59-85). **Remaining sub-issue (now New HIGH#3):** the plan's `""` defaults are converted to `None` by the loader before INSERT — see below. |
| 4 | 11-05 calls wrong persistence API | **FULLY RESOLVED** | 11-05 Task 2 calls `load_predictions(write_cur, prediction_df=pred_df, reader_role=...)` (11-05-PLAN.md:232-234); acceptance bans `_idempotent_load_prediction` (11-05-PLAN.md:286). Live: private fn takes `rows: list[tuple]` (prediction_load.py:191-196); public wrapper takes a DataFrame (prediction_load.py:373-411). |
| 5 | 11-05 task ordering inversion | **FULLY RESOLVED** | 11-05 reorders: Task 1 schema/predict → Task 2 orchestrator/script wiring → Task 3 live-DB checkpoint (11-05-PLAN.md:59-63, 299-303). Implementation now precedes verification. |
| 6 | `sales_start_entry_count` fallback unsafe | **FULLY RESOLVED** | 11-03 Task 1 requires the column from `race_df_score` and forbids group-size fallback (11-03-PLAN.md:109-112); acceptance uses inspect-based check (11-03-PLAN.md:136). Live: column selected by `load_labels` (data.py:361-382), carried through `build_training_frame` (data.py:410-428). |

---

## New HIGH Concerns (Cycle 2 — all VALID, all live-DB blockers)

### New HIGH#1 — DB CHECK constraint rejects `lightgbm_rr` / `catboost_rr`

The plans introduce and persist `model_type="lightgbm_rr"` / `"catboost_rr"` for race-relative
models (11-03-PLAN.md:175-181, 11-04-PLAN.md:173, 11-05-PLAN.md:235). But the live DDL only
permits `('lightgbm','catboost','logreg')`:

```
src/db/schema.py:83:  CONSTRAINT prediction_model_type_domain CHECK (model_type IN ('lightgbm','catboost','logreg')),
```

11-05 Task 1's schema migration only `ADD COLUMN IF NOT EXISTS` the three metadata columns and
does **not** drop/recreate `prediction_model_type_domain` (11-05-PLAN.md:109-113, 162-168).
Result: even if `predict.py` accepts the new model type, the live-DB load of race-relative rows
in 11-05 Task 3 will fail the CHECK constraint. SC#5 cannot be demonstrated.

**Required PLAN.md change (11-05 Task 1):** extend the schema migration to also
`ALTER TABLE ... DROP CONSTRAINT IF EXISTS prediction_model_type_domain` then
`ADD CONSTRAINT prediction_model_type_domain CHECK (model_type IN ('lightgbm','catboost','logreg','lightgbm_rr','catboost_rr'))`
(idempotent). Add an acceptance check that asserts the revised constraint exists.

### New HIGH#2 — SC#5 idempotent checksum is not bit-identical unless `as_of_datetime` is fixed

The Phase 11 persistence/test calls shown in the plan omit `as_of_datetime`
(11-04-PLAN.md:170-173, 11-05-PLAN.md:234), while claiming two-run checksum identity
(11-05-PLAN.md:324-327, 390-393). Live source defaults a missing `as_of_datetime` to
`datetime.now(UTC)`:

```
src/model/orchestrator.py:363-364:  if as_of_datetime is None: as_of_dt = datetime.now(UTC)
```

`predict_p_fukusho` writes `as_of_datetime` into each row (predict.py:270-272), it is part of
the 11-column PK (schema.py:80), and the idempotent checksum `ORDER BY`-s all `PREDICTION_COLUMNS`
(prediction_load.py:347-350). Two executions at different wall-clock times therefore yield
**different checksums**, breaking the SC#5 "2回実行で checksum bit-identical" claim.

**Required PLAN.md change (11-05 Task 2):** the `train_and_predict(theta=selected_theta, score_split="test", ...)`
call that feeds `load_predictions` MUST pass an explicit fixed `as_of_datetime` (e.g.
`FIXED_REPRODUCE_TS` at orchestrator.py:88, or a Phase 11 constant). Add an acceptance that the
persistence path uses a fixed timestamp (grep/inspect), and document in the Task 3 how-to-verify
that the two-run checksum comparison uses the same fixed timestamp on both runs.

### New HIGH#3 — New NOT NULL metadata columns with `""` defaults are inserted as NULL by the existing loader

Plan adds `TEXT NOT NULL DEFAULT ''` columns and default runtime args of `""`
(11-05-PLAN.md:110-125) and claims `theta=None` + empty defaults preserves existing v1.0 calls
(11-05-PLAN.md:216). But the existing loader converts any empty string to `None` before INSERT:

```
src/db/prediction_load.py:175-176:  elif isinstance(v, str):
                                       vals.append(v if v != "" else None)
```

…then `executemany` explicitly inserts that value into staging with the column enumerated
(prediction_load.py:290-297), so the DB-level `DEFAULT ''` never applies. Result: existing v1.0
binary prediction loads (which pass no metadata args → `""` → `None`) will violate `NOT NULL` on
the three new columns. This also undermines the 11-05 "A5 後方互換・既存テスト GREEN" claim.

**Required PLAN.md change (11-05 Task 1 or Task 2):** pick one and make it explicit in PLAN.md:
(a) change the loader (`_df_to_prediction_tuples`) to preserve `""` for the three provenance
columns (not convert to `None`), **or** (b) change the new columns to nullable (`TEXT` without
`NOT NULL`) and rely on the application layer for provenance, **or** (c) give the columns no DB
default but make the orchestrator/predict layer always pass a non-empty sentinel (e.g. `"v1.0"` /
`"none"` / `"BT-1"`) so the loader never sees `""`. Add an acceptance that a v1.0 binary load
(theta=None, default args) still succeeds after the migration.

---

## Actionable MEDIUM/LOW (Cycle 2 — not yet incorporated into PLAN.md)

- **MEDIUM:** `theta=float` with `model_type="lightgbm"` (not `"lightgbm_rr"`) is not forbidden.
  The plan only rejects race-relative model types paired with `theta=None` (11-03-PLAN.md:100).
  Since `model_version` is derived from `model_type` (orchestrator.py:413), a caller that passes
  `theta=0.75` with `model_type="lightgbm"` would stamp corrected probabilities as the binary
  `lgb` model — a silent provenance/sanctuary hole. **PLAN.md change needed:** in 11-03 Task 1,
  add a guard: `theta is not None` requires `model_type` to end with `_rr`; otherwise `ValueError`.

- **LOW:** 11-04/11-05 use brittle `set_primary_model` substring greps as acceptance checks while
  also asking docs/comments to say "do not call set_primary_model" (11-04-PLAN.md:185, 202, 237;
  11-05-PLAN.md:273-274). A docstring mention would make the grep non-zero and fail the gate
  spuriously. **PLAN.md change needed:** replace substring greps with AST/call-site checks
  (e.g. `ast.walk` for `Call` nodes whose `func.attr == "set_primary_model"`).

- **LOW:** 11-04 still contains stale private-persistence references despite 11-05 fixing the API
  (11-04-PLAN.md:32, 185). 11-04 defers persistence to 11-05 so it is not a blocker, but it is
  misleading. **PLAN.md change needed:** update 11-04's `key_links` and Task 2 docstring to
  reference `load_predictions` (public) for consistency with 11-05.

---

## Verification Pass (Cycle 2 — source-grounding audit by reviewer agent)

Each Codex claim was re-traced against the live source by the reviewer agent:

| # | Claim | Code reference | Verdict |
|---|---|---|---|
| C2-1 | `prediction_model_type_domain` rejects `lightgbm_rr`/`catboost_rr` | schema.py:83 `CHECK (model_type IN ('lightgbm','catboost','logreg'))`; 11-05 migration adds cols only | **VALID (HIGH#1)** |
| C2-2 | `as_of_datetime=None` → `datetime.now(UTC)` → unstable checksum | orchestrator.py:363-364; PK at schema.py:80; checksum ORDER BY at prediction_load.py:347-350 | **VALID (HIGH#2)** |
| C2-3 | `_df_to_prediction_tuples` converts `""` → `None`; explicit INSERT bypasses DB DEFAULT | prediction_load.py:175-176 (`v if v != "" else None`); executemany at :290-297 | **VALID (HIGH#3)** |
| C2-4 | `theta=float` + `model_type="lightgbm"` not forbidden; `model_version` from `model_type` | 11-03-PLAN.md:100 (only rejects `_rr` + `theta=None`); orchestrator.py:413 | **VALID (MEDIUM)** |
| C2-5 | cycle-1 HIGH#1 score_split added; targets X_calib not X_test | 11-03-PLAN.md:89-107; orchestrator.py:388-390,524-577 | **VALID — FULLY RESOLVED** |
| C2-6 | cycle-1 HIGH#2 import reuse + `np.linspace` ban | 11-02-PLAN.md:156-170,184; evaluator.py:386-393; segment_eval.py:151-158 | **VALID — FULLY RESOLVED** |
| C2-7 | cycle-1 HIGH#4 `load_predictions` public wrapper used; private banned | 11-05-PLAN.md:232-234,286; prediction_load.py:191-196,373-411 | **VALID — FULLY RESOLVED** |
| C2-8 | cycle-1 HIGH#5 task ordering fixed (impl before checkpoint) | 11-05-PLAN.md:59-63,299-303 | **VALID — FULLY RESOLVED** |
| C2-9 | cycle-1 HIGH#6 `sales_start_entry_count` required; no fallback | 11-03-PLAN.md:109-112,136; data.py:361-382,410-428 | **VALID — FULLY RESOLVED** |

**Result:** 3 new HIGHs VALID, 1 MEDIUM VALID, 2 LOWs VALID. 5/6 cycle-1 HIGHs FULLY RESOLVED,
1 PARTIALLY RESOLVED (HIGH#3 — same root cause area as New HIGH#3).

---

## Cycle 2 Consensus Summary

### Resolved (cycle-1 — no further action)

- **HIGH#1 (θ sanctuary):** the `score_split="calib"` structural block in 11-03 + θ-selection.json
  pre-write in 11-04 closes the test-window leak at the API seam, not just in docstrings.
- **HIGH#2 (bit-identical binning):** 11-02 now imports the canonical helpers and bans local
  `np.linspace` bin edges, with an acceptance grep enforcing count == 0.
- **HIGH#4 (persistence API):** 11-05 Task 2 calls the public `load_predictions` wrapper and the
  acceptance bans the private `_idempotent_load_prediction`.
- **HIGH#5 (task ordering):** 11-05 reorders to Task 1 (schema/predict) → Task 2 (orchestrator/
  script wiring) → Task 3 (live-DB checkpoint) — implementation precedes verification.
- **HIGH#6 (`sales_start_entry_count`):** 11-03 requires the column and forbids group-size
  fallback, with an inspect-based acceptance.

### Remains unresolved (must address before /gsd-execute-phase)

- **HIGH (cycle-1 #3 PARTIAL):** SC#5 §19.1 metadata wiring is planned, but loader compatibility
  is not (overlaps New HIGH#3).
- **New HIGH#1:** `prediction_model_type_domain` CHECK constraint rejects `lightgbm_rr`/
  `catboost_rr` — schema migration in 11-05 Task 1 must also update the constraint.
- **New HIGH#2:** `as_of_datetime` must be fixed (e.g. `FIXED_REPRODUCE_TS`) on the persistence
  path or the SC#5 two-run checksum cannot be bit-identical.
- **New HIGH#3:** `_df_to_prediction_tuples` converts `""` → `None`; new NOT NULL columns will
  reject v1.0 binary loads unless the loader, the column nullability, or the default sentinel is
  changed.
- **MEDIUM:** `theta=float` + non-`_rr` `model_type` is a silent provenance hole — add a guard.
- **LOW ×2:** replace `set_primary_model` substring greps with AST checks; update 11-04 stale
  private-persistence references.

### Overall Risk: **HIGH**

The race-relative math layer (11-01/11-02) and the orchestrator θ/score_split integration
(11-03/11-04) are sound and the cycle-1 sanctuary/leakage HIGHs are genuinely resolved. However,
11-05's SC#5 live-DB demonstration has three newly-discovered blockers (CHECK constraint,
checksum stability, NOT NULL vs loader) that would cause the live-DB checkpoint to fail even if
all preceding code is correct. These must be folded into 11-05 (Task 1 and/or Task 2) before
execution.
