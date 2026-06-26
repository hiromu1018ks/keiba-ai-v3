---
phase: 10
reviewers: [codex, claude]
reviewed_at: 2026-06-26T10:22:29Z
cycle: 2
plans_reviewed:
  - 10-01-PLAN.md
  - 10-02-PLAN.md
  - 10-03-PLAN.md
  - 10-04-PLAN.md
  - 10-05-PLAN.md
  - 10-06-PLAN.md
  - 10-07-PLAN.md
source_grounding: codex (default model, xhigh reasoning) AND claude (cycle-2 lead) — both ran inside the project git working tree; file:line citations verified against the live repo. Both reviewers independently reached the same critical finding on plan 10-01.
---

# Cross-AI Plan Review — Phase 10 (Cycle 2 — re-review of REVISED plans)

> Cycle 2 of a convergence loop. Cycle 1 raised 6 HIGH + 5 actionable MEDIUM/LOW findings
> on leakage surfaces. The plans were revised in reviews mode (added `_compute_opponent_rolling_mean5`,
> `_source_race_cutoff_gate`, odds-in-SQL scanner, corrected metadata key, fixed orchestrator
> API chain). A gsd-plan-checker then VERIFIED the plans PASS.
>
> **Cycle-2 outcome: the plan-checker's structural pass did NOT catch a content-level leak.**
> Both reviewers (Codex + Claude) independently discovered that the revised 10-01's central
> premise — that history's `speed_figure` values are "raw race_date-derived, not target-cutoff-
> expanded" — is **directly contradicted by `src/features/speed_figure.py`**. The H2 fix is
> structurally insufficient and the H4 adversarial test has a blind spot that lets the leak pass.
> Overall risk remains **HIGH**. See the Cycle-2 NEW HIGH below.

---

## Cycle-1 HIGH resolution verdicts (at a glance)

| Cycle-1 HIGH | Cycle-2 verdict | Why |
|---|---|---|
| H1 (10-01 dataflow: history lacks rolling_speed_figure_mean_5) | **PARTIALLY RESOLVED** | Revision correctly removes the dependency on the existing rolling column, BUT recomputes the rolling mean from `speed_figure` values that are themselves target-cutoff-contaminated (NEW HIGH-C2-1). |
| H2 (10-01 source-vs-target-cutoff lookahead) | **UNRESOLVED — NEW HIGH-C2-1 introduced/confirmed** | The row-level cutoff gate is insufficient: per-row `speed_figure` already depends on the target obs's `feature_cutoff_datetime` via per-`obs_id` par/variant. |
| H3 (10-07 SQL scanner excludes "odds") | **RESOLVED** | Plan extends odds to SQL literal check for field_strength/race_relative with whitelist; existing scanner gap at `tests/audit/test_audit_speed_figure.py:39-48` acknowledged and fixed. |
| H4 (10-07 lookahead scope misses source-vs-target) | **PARTIALLY RESOLVED** | New `test_source_vs_target_cutoff_lookahead_injection_detected` is added, but it only tests row inclusion in (S,T]; it does NOT test that the same pre-S opponent row gets different `speed_figure` values under different target cutoffs (the actual leak vector). |
| H5 (10-05 metadata key) | **RESOLVED** | `feature_availability_version` matches `src/features/snapshot.py:62,71`; plan asserts the wrong key is absent. |
| H6 (10-06 orchestrator API) | **RESOLVED** | 5-step flow matches `orchestrator.py:234-258` and mirrors `run_speed_figure_stopgate.py:583-629`. |

---

## Codex Review (Cycle 2)

**Summary**

The revised plans do not pass independent review. H3, H5, and H6 are substantively resolved,
and 10-03's tie/additive-score clarifications are good. But the critical 10-01 claim is false
against current `speed_figure.py`: `compute_speed_figure_for_history(..., observations=...)`
returns an `obs_id`-expanded frame whose `par_sec`, `variant_sec`, and therefore `speed_figure`
are target-cutoff-dependent. Filtering those already-contaminated `speed_figure` values by
`source_available_at` does not make them source-race safe. Overall risk remains **HIGH**.

### Plan 10-01 — **HIGH (NEW Cycle-2 HIGH-C2-1): source-race opponent ability still leaks through target-expanded `speed_figure` values**

The plan claims `_compute_opponent_rolling_mean5` consumes `speed_figure` values that are
"not target cutoff expanded" and are raw race_date-derived (`10-01-PLAN.md:44`, also `:96`).
Actual code contradicts this.

`compute_speed_figure_for_history` merges history to observations by `kettonum`, carrying
`obs_id` and each target observation's `feature_cutoff_datetime` (`speed_figure.py:579`, `:635`).
It then filters by that target cutoff (`speed_figure.py:640`), computes par/variant on the
expanded frame, and sets `result = with_variant`, explicitly preserving the expanded frame
(`speed_figure.py:653`, `:655-657`).

`_compute_pit_par` is explicitly per-observation: its docstring says `obs_id` is part of the
group key and different cutoffs must not share par medians (`speed_figure.py:343`, `:350-362`).
Stage 1 uses `["obs_id", "_jyocd", "_trackcd", "_kyori"]` (`speed_figure.py:401-402`). Variant
is also per-`obs_id` (`speed_figure.py:453`, `:509-510`). Finally, `speed_figure` is computed
from those obs-specific `par_sec` and `variant_sec` (`speed_figure.py:691`).

Existing tests confirm this is intentional: "result は展開されている" and `O_early`/`O_late`
get different `par_sec` under different cutoffs (`tests/features/test_speed_figure_pit.py:197`).

**Leak mechanism**: an opponent race before source race `S` can carry a `speed_figure`
computed under target cutoff `T`, where `(S, T]` rows influenced par/variant.
`_compute_opponent_rolling_mean5` can filter selected rows to `< S`, but the selected row's
value is already contaminated.

**Why planned Test 2 would miss it** (`10-01-PLAN.md:95`): it only tests whether rows in
`(S,T]` are included in the rolling window. It does not assert that the same opponent race
has the same `speed_figure` under different target cutoffs. The adversarial test treats
injected (S,T] opponent `speed_figure` values as legitimate fixed numbers — it never tests
that those numbers would differ under another target's cutoff.

**Correct fix**: compute opponent speed figures from scratch with `source_available_at` as
the cutoff, including par/variant, not just the rolling mean. Concretely, preserve raw history
before Step 5b, or add a source-as-of speed-figure path keyed by source race/available_at,
then compute opponent rolling ability from those source-cutoff-specific values.

### Plan 10-02 — **HIGH (NEW Cycle-2 HIGH-C2-2): downstream gate documents propagation but does not protect against it**

The revised plan admits Plan 02 depends on Plan 01's source-safe profile (`10-02-PLAN.md:27`).
Test 9 only demonstrates that polluted profiles pollute rolling outputs (`10-02-PLAN.md:99`).
Since 10-01 still consumes target-dependent `speed_figure`, all 21 downstream rolling
field-strength features remain at risk.

### Plan 10-03 — LOW: revised tie/additive-score concerns look resolved

`gap_to_3rd` tie behavior is now explicit: rank `3` must exist under competition ranking,
otherwise all `gap_to_3rd` are `NaN` (`10-03-PLAN.md:93`, `:122-124`, Test 5b at `:94`).
Additive-score diagnostics are planned for train/calib only (`:29`, `:138` — the W-2
`compute_candidate_score_diagnostics` helper).

### Plan 10-04 — **HIGH (NEW Cycle-2 HIGH-C2-3): integration order feeds 10-01 the contaminated frame**

Current builder Step 5b assigns `history = compute_speed_figure_for_history(history,
observations=feature_matrix)` (`builder.py:525`). Plan 04 inserts
`compute_field_strength_profile(history, observations=feature_matrix)` after Step 5b
(`10-04-PLAN.md:113`). That means field strength receives the already target-expanded
`history`, unless the plan is changed to preserve/recompute from raw history.

### Plan 10-05 — RESOLVED: metadata key correction is grounded in code

Actual metadata key is `feature_availability_version`, not `feature_availability_schema_version`
(`snapshot.py:62`, `:71`). The revised plan uses the real key and asserts the wrong key is
absent (`10-05-PLAN.md:94`, `:114`). CLI flags `--snapshot-id/--label-version/--fa-version/--created-at`
match `scripts/run_feature_build.py:65-103`; `--bt-split` correctly dropped.

### Plan 10-06 — RESOLVED: orchestrator API flow is now correct

Actual `train_and_predict` requires `feature_df` plus keyword args, including
`feature_snapshot_id` and optional `snapshot_id` (`orchestrator.py:234`). It requires a
label-joined frame (`orchestrator.py:253-258`). The revised plan specifies the correct
five-step flow and mirrors the working stopgate script (`10-06-PLAN.md:50`,
`run_speed_figure_stopgate.py:583-629`). Category-map bit-identity assertion (W-3) added,
`load_frozen_maps` is per-snapshot (`data.py:707-722`).

### Plan 10-07 — PARTIAL: H3 fixed, H4 test still has the 10-01 blind spot

Existing scanner excludes `odds` from SQL literal checks
(`test_audit_speed_figure.py:39-48`). Plan 07 explicitly adds odds-in-SQL detection for new
modules with whitelist (`10-07-PLAN.md:19`, `:94`). That resolves H3.

But the source-vs-target lookahead test still checks inclusion of `(S,T]` opponent rows
(`10-07-PLAN.md:97`). It does not test that `speed_figure` for the same pre-`S` opponent row
is invariant across target cutoffs. The H4 test inherits 10-01's false premise and would
GREEN even though the leak persists.

### Overall Risk Assessment (Codex)

**HIGH.** The architectural fixes for H3/H5/H6 are real, but the central leakage surface
(10-01's source-race opponent ability) is not actually closed — the revision added a gate
that controls *which rows* enter the rolling window without recognizing that the *values on
those rows* are already target-cutoff-dependent. Three new HIGHs (C2-1/C2-2/C2-3) follow
from this single root cause.

---

## Claude Review (Cycle 2 lead — independent corroboration)

**Summary**

I independently verified the revised 10-01 plan's core premise against the source and reached
the same conclusion as Codex: the plan's claim that history's `speed_figure` is "raw
race_date-derived, not target-cutoff-expanded" (`10-01-PLAN.md:44, :96, :22`) is **false**.
`compute_speed_figure_for_history` returns an `obs_id`-expanded frame (`speed_figure.py:655-658`,
`:700`) where each row's `speed_figure` depends on `obs_id`-scoped par/variant
(`speed_figure.py:350-362`, `:401-402`, `:509-510`, `:691`). The `_compute_opponent_rolling_mean5`
fix therefore filters contaminated values by a clean cutoff — the leak persists.

The non-10-01 HIGHs (H3/H5/H6) are genuinely resolved with verifiable source grounding.
10-03's tie/diagnostic clarifications are correct and incorporated. The new concerns are all
consequences of the single root cause below.

### NEW Cycle-2 HIGHs (root cause + downstream)

**HIGH-C2-1 (10-01, leakage — root cause): per-row `speed_figure` is target-cutoff-dependent; the revision's row-level cutoff gate is insufficient.**

Evidence (all `src/features/speed_figure.py`):
- L635: `expanded = out.merge(obs_keys, on="kettonum", how="inner", ...)` — joins each history
  row to ALL target observations for that horse.
- L641: `expanded_filtered = _pit_cutoff_prefilter(expanded)` — uses the TARGET's
  `feature_cutoff_datetime` (L116-118: `expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]`).
- L402 / L350-362: par groupby key is `["obs_id", "_jyocd", "_trackcd", "_kyori"]` — par is
  scoped per target observation; the docstring explicitly states "observation 毎に独立した par".
- L509-510: variant groupby key is `["obs_id", "_source_race_date", "_jyocd", "_surface"]` —
  also per-target-observation.
- L691: `sf_values = (result["par_sec"] - result["time_sec"] + result["variant_sec"]) * pps_per_row`
  — `speed_figure` inherits the obs-specific par/variant.
- L655-657 comment: "obs_id 毎に par/variant が異なるため・元 history 行 × observation の
  組み合わせで保持" — the author confirms the expanded shape is intentional.

Consequence for the revision: `_compute_opponent_rolling_mean5(history_with_sf=history,
source_available_at=...)` receives the expanded frame where the SAME opponent source-race
appears multiple times (once per target obs sharing that horse), each row carrying a DIFFERENT
`speed_figure` value because par/variant were computed under a different target cutoff. The
plan does not specify which obs_id copy to use, and even if it picks one, that value was
computed using a target cutoff — filtering by `source_available_at` cannot un-contaminate it.

The adversarial Test 2 (`10-01-PLAN.md:95`) would GREEN despite the leak: it injects (S,T]
opponent races and assigns them fixed `speed_figure` values, then asserts the gate excludes
them. It never tests that a pre-S opponent race receives different `speed_figure` values under
two different target cutoffs — which is the actual leak vector.

**Required fix (for the planner)**: `_compute_opponent_rolling_mean5` must NOT consume the
`obs_id`-expanded `speed_figure` from `compute_speed_figure_for_history`. It must instead
recompute opponent ability from the RAW history (pre-Step-5b) using `source_available_at` as
the cutoff for the *entire* speed-figure pipeline (par + variant + speed_figure), or maintain
a separate "source-as-of speed_figure" path keyed by `(source_race, opponent)` that runs
`compute_speed_figure_for_history` with a synthetic observation whose `feature_cutoff_datetime
= source_available_at`. Anything short of this leaves the per-row value contaminated.

Also: the adversarial test must assert value-invariance — "the same pre-S opponent race
yields the same `speed_figure` regardless of which target observation triggers the field
strength computation" — not just row-inclusion in (S,T].

**HIGH-C2-2 (10-02, leakage — downstream carrier): all 21 rolling_field_strength_* features inherit the C2-1 contamination.**

10-02 correctly states it depends on 10-01's source-race PIT-correctness (`10-02-PLAN.md:27`).
But its Test 9 (`10-02-PLAN.md:99`) only demonstrates that *if* the profile is polluted then
the rolling output is polluted — it does not verify the profile is clean. Since 10-01 does
not actually produce a clean profile (C2-1), all 21 downstream features are at risk. Gating
10-02 on 10-01's adversarial test is necessary but, given C2-1, not sufficient.

**HIGH-C2-3 (10-04, leakage — integration order): builder Step 5b replaces `history` with the obs_id-expanded frame BEFORE Step 5c (field_strength) consumes it.**

`builder.py:525` does `history = compute_speed_figure_for_history(history,
observations=feature_matrix)`. Plan 04 inserts `compute_field_strength_profile(history,
observations=feature_matrix)` as Step 5c AFTER this reassignment (`10-04-PLAN.md:113`). So
field strength receives the already-target-expanded history unless the plan preserves raw
history or recomputes from it. This is the integration-level manifestation of C2-1 and must
be addressed at the builder ordering level, not only inside field_strength.py.

### Cycle-2 MEDIUM/LOW (actionable)

- **MEDIUM-C2-4 (10-07, audit blind spot)**: the new
  `test_source_vs_target_cutoff_lookahead_injection_detected` (`10-07-PLAN.md:97`) inherits
  10-01's false premise. It must additionally assert that a pre-S opponent row's `speed_figure`
  is invariant across target cutoffs (value-level leak, not just row-inclusion). Without this,
  the SAFE-01 audit will GREEN even though the leak persists. PLAN.md change needed: add a
  value-invariance assertion to Test 7 in 10-07 (and to Test 2 in 10-01).

- All other Cycle-1 MEDIUM/LOW concerns are incorporated into PLAN.md:
  - MEDIUM-7 gap_to_3rd tie (`10-03-PLAN.md:94, :122-124`) — RESOLVED.
  - MEDIUM-8 feature_count ambiguity (`10-04-PLAN.md:28-29, :207`) — RESOLVED.
  - MEDIUM (10-06 category-map bit-identity, `10-06-PLAN.md` W-3) — RESOLVED.
  - LOW additive-score scale diagnostic (`10-03-PLAN.md:29-30, :138` W-2 helper) — RESOLVED.
  - LOW cProfile brittleness (`10-07-PLAN.md` W-3 wall-clock + static anti-pattern) — RESOLVED.

---

## Consensus Summary (Cycle 2 — two reviewers)

### Agreement

Both reviewers (Codex + Claude) independently and unanimously identified the same root-cause
HIGH: the revised 10-01 plan's central factual premise about `speed_figure` provenance is
contradicted by the code, and therefore the H2 fix is structurally insufficient. Both
reviewers cited the same evidence chain (`speed_figure.py:579/635/640/655/402/350-362/509/691`
+ `test_speed_figure_pit.py:197`). Both agree H3/H5/H6 are genuinely resolved and 10-03 is
good. No divergence on any finding.

### Cross-cycle leakage-priority call-out

Cycle 2 confirms that Cycle-1 H1/H2 were **not** resolved by the revision — they were
re-expressed in a way that passes a structural plan-checker (the helper names and adversarial
tests exist) but fails content-level source-grounding (the values being filtered are already
contaminated). The plan-checker's PASS was correct on plan *structure* but could not catch a
claim that is false against the source. The single root cause (C2-1) generates two downstream
HIGHs (C2-2, C2-3). Fixing C2-1 at the 10-01/10-04 boundary (recompute opponent speed_figure
under source_available_at, not target cutoff) will close all three.

### Why the plan-checker passed but Cycle-2 fails

The plan-checker verified that the plans *mention* `_compute_opponent_rolling_mean5`,
`_source_race_cutoff_gate`, and the adversarial tests. It did not — and structurally cannot —
verify the plan's prose claim that history's `speed_figure` is "raw race_date-derived." That
claim is load-bearing for the entire H2 fix, and it is false. This is exactly the kind of
content-level leak that adversarial cross-AI review exists to catch.

---

## Verification coverage (Cycle 2)

| Plan | Source-grounded evidence re-cited this cycle | Leakage-relevant finding? |
|------|----------------------------------------------|---------------------------|
| 10-01 | `speed_figure.py:579/635/640/655-657/691/697-698/350-362/401-402/509-510`, `test_speed_figure_pit.py:197`, `10-01-PLAN.md:22/44/95/96` | YES (HIGH-C2-1, root cause) |
| 10-02 | `10-02-PLAN.md:27/99` | YES (HIGH-C2-2, downstream) |
| 10-03 | `10-03-PLAN.md:29/93/94/122-124/138` | no (RESOLVED — tie + diagnostic) |
| 10-04 | `builder.py:525`, `10-04-PLAN.md:113` | YES (HIGH-C2-3, integration order) |
| 10-05 | `snapshot.py:62/71`, `run_feature_build.py:65-103`, `10-05-PLAN.md:94/114` | no (RESOLVED) |
| 10-06 | `orchestrator.py:234-258`, `run_speed_figure_stopgate.py:583-629`, `data.py:707-722`, `10-06-PLAN.md:50` | no (RESOLVED) |
| 10-07 | `test_audit_speed_figure.py:39-48`, `10-07-PLAN.md:19/94/97` | partial (MEDIUM-C2-4 audit blind spot) |

---

CYCLE_SUMMARY: current_high=3 current_actionable=1

## Current HIGH Concerns

- **HIGH-C2-1 (10-01, leakage root cause)**: The revised plan's premise that history's `speed_figure` is "raw race_date-derived, not target-cutoff-expanded" is false. `compute_speed_figure_for_history` returns an `obs_id`-expanded frame (`speed_figure.py:655-658`) where each row's `speed_figure` depends on the target observation's `feature_cutoff_datetime` via per-`obs_id` par/variant (`speed_figure.py:350-362, 401-402, 509-510, 691`). `_compute_opponent_rolling_mean5`'s row-level cutoff gate filters already-contaminated values; the H2 leak persists. Adversarial Test 2 (`10-01-PLAN.md:95`) does not catch it because it tests row-inclusion, not value-invariance. Fix: recompute opponent speed_figure from raw history with `source_available_at` as the cutoff for the FULL par+variant+speed_figure pipeline.
- **HIGH-C2-2 (10-02, leakage downstream)**: All 21 `rolling_field_strength_*` features inherit the C2-1 contamination. 10-02's Test 9 only documents propagation, it does not verify the profile is clean.
- **HIGH-C2-3 (10-04, leakage integration order)**: builder.py:525 reassigns `history` to the obs_id-expanded frame before Plan 04's Step 5c `compute_field_strength_profile(history, ...)` consumes it (`10-04-PLAN.md:113`), unless the plan is changed to preserve/recompute from raw history.

## Current Actionable Non-HIGH Concerns

- **MEDIUM-C2-4 (10-07, audit blind spot)**: The new `test_source_vs_target_cutoff_lookahead_injection_detected` (`10-07-PLAN.md:97`) inherits 10-01's false premise — it tests row-inclusion in (S,T] but not that a pre-S opponent row's `speed_figure` is invariant across target cutoffs. PLAN.md change needed: add a value-invariance assertion ("same pre-S opponent race yields the same `speed_figure` regardless of target obs") to Test 7 in 10-07 AND to Test 2 in 10-01. Without this the SAFE-01 audit GREENs while the leak persists.
