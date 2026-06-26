---
phase: 10
reviewers: [codex]
reviewed_at: 2026-06-26T09:28:55Z
plans_reviewed:
  - 10-01-PLAN.md
  - 10-02-PLAN.md
  - 10-03-PLAN.md
  - 10-04-PLAN.md
  - 10-05-PLAN.md
  - 10-06-PLAN.md
  - 10-07-PLAN.md
source_grounding: codex (gpt-5.5, xhigh reasoning) — ran inside the project git working tree; file:line citations verified against the live repo
---

# Cross-AI Plan Review — Phase 10 (Opponent Strength & Race-Relative Features)

> Single-reviewer cycle (Codex / gpt-5.5). Each finding below is source-grounded —
> the reviewer opened the referenced files and cited `path:line` evidence.
> The planner should treat every HIGH as a planning-level defect that must be
> incorporated into PLAN.md (or explicitly deferred with rationale) before
> `/gsd-execute-phase` — otherwise it is invisible to the executor.

---

## Codex Review

**Summary**

Overall risk is **HIGH until Plan 10-01 and 10-07 are tightened**. The wave structure is
coherent, and many guardrails correctly reuse existing project patterns: strict `< cutoff`,
`obs_id`-scoped rolling windows, registry parity, dynamic `FEATURE_COLUMNS`, and measured
baseline-vs-scenario evaluation. The main leak risk is in `field_strength`: the plan assumes
`history` already contains `rolling_speed_figure_mean_5`, but current code only creates rolling
speed features for the target `feature_matrix`, not for historical source races. Worse, current
speed figures are expanded relative to the target observation cutoff, so reusing them for
source-race opponent ability can leak races that occurred after the source race but before the
target race.

### Plan 10-01 (FEAT-02 field_strength stage 1)

**Strengths**
- The strict as-of choice is aligned with the existing invariant: `CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"` in `src/features/availability.py:45`, and both speed/rolling PIT helpers enforce `<` at `src/features/speed_figure.py:98` and `src/features/rolling.py:114`.
- The starter rule `kakuteijyuni > 0` matches the Phase 10 context decision to exclude unstarted horses but include stopped/DNF starters, `.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md:28`.
- The 8-value opponent profile matches the registered design: mean, median, top3/top5, max, sd, valid count, coverage at `.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md:27`.

**Concerns**
- **HIGH:** The plan requires `rolling_speed_figure_mean_5` in `history` (`10-01-PLAN.md:111`), but current `compute_speed_figure_for_history` adds `speed_figure` and `available_at`, not rolling columns (`src/features/speed_figure.py:681`, `src/features/speed_figure.py:697`). Rolling speed features are produced later by `build_rolling_features` and merged only into `feature_matrix` (`src/features/builder.py:531`, `src/features/builder.py:535`). The planner does not establish how opponent `rolling_speed_figure_mean_5` lands in `history` for source-race profile computation.
- **HIGH:** Strict `_opp_available_at < source.available_at` is necessary but not sufficient. Current speed-figure expansion is observation-cutoff based: it expands history against target observations (`src/features/speed_figure.py:579`) and filters by `feature_cutoff_datetime` (`src/features/speed_figure.py:640`). For field strength, opponent ability must be evaluated as of each **source race**, not the later target cutoff. Reusing target-cutoff-expanded `speed_figure` values for opponents can silently include opponent races that occurred after the source race but before the target race — a lookahead leak that the strict `<` guard between opponent and source does not catch.
- **MEDIUM:** The performance claim depends on vectorization, but the suggested top-k aggregation uses per-group custom functions (`10-PATTERNS.md:104`). That may be acceptable, but the 6.7M-pair concern is real and explicitly called out in research (`10-RESEARCH.md:425`).

**Suggestions**
- Materialize an opponent ability table keyed by `(source_race_nkey, opponent_kettonum)` with `feature_cutoff_datetime = source_race.available_at`, then compute latest-K speed ability from rows strictly before that source race.
- Add an adversarial test where an opponent has a strong race after the source race but before the target race; field strength must ignore it.

**Risk: HIGH.** This is the foundational feature, and the current plan can either fail mechanically or leak target-cutoff future information into source-race strength.

### Plan 10-02 (FEAT-02 stage 2 — 21 rolling features)

**Strengths**
- The plan's `obs_id` latest-K design matches existing rolling behavior: `obs_id` is synthesized from `(race_nkey, kettonum)` at `src/features/rolling.py:297`, strict prefilter happens at `src/features/rolling.py:370`, and latest-5 is selected with deterministic sort plus `groupby("obs_id").head(5)` at `src/features/rolling.py:375`.
- The count/coverage "do not sentinel" rule is consistent with the existing speed-count behavior, where count columns are set directly (`src/features/rolling.py:448`, `src/features/rolling.py:515`) and sentinel thresholds are applied separately (`src/features/rolling.py:524`).
- It correctly does not force `merge_asof` for latest-K. Existing rolling docs explicitly reject single `merge_asof` because it only solves latest-1 (`src/features/rolling.py:23`).

**Concerns**
- **HIGH:** This plan inherits Plan 10-01's dataflow risk. If `field_strength_*` profiles are not source-race PIT-correct, then all 21 rolling features are contaminated. The dependency chain makes 10-02 a downstream carrier of the 10-01 leak.
- **MEDIUM:** "Symmetric with speed_figure" is structurally true, but not identical. Speed figure axes are registered at `src/features/rolling.py:136`; field-strength names like `valid_count_mean_5` and `coverage_mean_5` need explicit tests through Parquet coercion because snapshot handling parses rolling names heuristically (`src/features/snapshot.py:116`).
- **LOW:** Existing rolling code still has row-wise update loops for older systems (`src/features/rolling.py:640`, `src/features/rolling.py:687`). The field-strength branch should stay in the vectorized speed-figure section, as planned.

**Suggestions**
- Gate Plan 10-02 on a test proving Plan 10-01's profile values are computed at source-race cutoff.
- Include snapshot dtype tests for every new rolling name, not only representative columns.

**Risk: MEDIUM-HIGH**, mostly due to dependency on Plan 10-01.

### Plan 10-03 (FEAT-03 race-relative features)

**Strengths**
- Target-only race-relative computation matches D-07: race-relative features should be computed on target observations only (`10-CONTEXT.md:34`), and current builder preserves `race_nkey` until late in the pipeline (`src/features/builder.py:618`).
- Competition ranking with `method="min"` and `na_option="keep"` is the right mechanism for same-rank ties and missing values; this is exactly what the plan specifies (`10-03-PLAN.md:20`).
- The coefficient is pre-registered with candidate set and canonical value (`10-CONTEXT.md:39`, `10-03-PLAN.md:26`), and the plan explicitly drops candidate-derived temporary columns (`10-03-PLAN.md:96`).

**Concerns**
- **MEDIUM:** `gap_to_3rd` is ambiguous under ties. With values `[100, 95, 95, 90]`, competition ranks are `[1,2,2,4]`; there is no rank 3. The plan should state whether "3rd" means third sorted non-null runner or rank value `3` (`10-03-PLAN.md:23`, `10-03-PLAN.md:119`).
- **MEDIUM:** The AST audit plans warn not to place forbidden romanized tokens in docstrings, which is necessary because current scanner examines `ast.Constant` strings (`tests/audit/test_audit_speed_figure.py:100`). Comments are not scanned by AST, so comments cannot create AST false positives but also cannot be audited this way.
- **LOW:** `field_strength_adjusted_score = speed + 0.25 * field_strength` may mix differently scaled values. The plan protects against test-window retuning, but it should log train-window distribution sanity before accepting the coefficient.

**Suggestions**
- Define `gap_to_3rd` as "third sorted non-null value" or "rank == 3" and add a tie test.
- Add scale diagnostics for the additive score on train/calib only.

**Risk: MEDIUM.**

### Plan 10-04 (builder integration + registry)

**Strengths**
- Moving rolling after field-strength profile generation is necessary. Current builder computes speed figures at `src/features/builder.py:525` and immediately calls rolling at `src/features/builder.py:531`; Plan 10-04 correctly inserts field strength before rolling (`10-04-PLAN.md:20`).
- Registry parity is well-grounded: current builder already calls `assert_matrix_columns_registered` at `src/features/builder.py:644`, and that function rejects unregistered columns and banned target-observation columns (`src/features/availability.py:314`, `src/features/availability.py:333`).
- Adding `field_strength` to reserved rolling systems is consistent with the current reserved-system list ending at `"speed_figure"` (`src/features/availability.py:143`) and the special speed exclusion logic at `src/features/availability.py:188`.

**Concerns**
- **MEDIUM:** Step 7b drops raw `field_strength_*` columns from `feature_matrix` (`10-04-PLAN.md:22`), but Plan 10-01 adds those columns to `history`, and current rolling merge only brings `rolling_` columns into `feature_matrix` (`src/features/builder.py:535`). This drop may be redundant unless another step merges raw profile columns.
- **MEDIUM:** The plan uses `feature_count 79 -> 106` (`10-04-PLAN.md:29`), but current snapshot manifest writes full DataFrame column count (`scripts/run_feature_build.py:232`), while model feature columns are derived separately (`src/model/data.py:179`). The plan must clarify "model feature count" vs "Parquet column count."
- **MEDIUM:** Registry entries with `source_role: both_allowed` do not themselves prove leak freedom. The mechanism still depends on builder ordering and race-relative tests.

**Suggestions**
- Add an explicit test that final `feature_matrix` contains no non-rolling `field_strength_*` columns.
- Rename the count assertion to `model_feature_count == 106` if that is the intended metric.

**Risk: MEDIUM.**

### Plan 10-05 (snapshot byte-reproducibility)

**Strengths**
- The plan correctly identifies the dtype risk: snapshot coercion currently only handles columns starting with `rolling_` (`src/features/snapshot.py:99`), so FEAT-03 non-rolling float columns need separate coverage.
- Byte reproducibility is grounded in existing deterministic write behavior: sort keys at `src/features/snapshot.py:221`, metadata-excluded SHA at `src/features/snapshot.py:236`, and deterministic Parquet writer settings at `src/features/snapshot.py:273`.
- Live-DB verification is justified because the research notes Parquet dtype bugs may not appear in unit tests (`10-RESEARCH.md:455`).

**Concerns**
- **HIGH:** Metadata key name is wrong in the plan. It expects `feature_availability_schema_version` (`10-05-PLAN.md:25`), but current snapshot metadata uses `feature_availability_version` (`src/features/snapshot.py:62`, `src/features/snapshot.py:266`). Tests asserting the wrong key will false-pass or fail loudly at runtime.
- **MEDIUM:** The proposed command includes `--bt-split BT-1` (`10-05-PLAN.md:151`), but `scripts/run_feature_build.py` has no such CLI option; it supports `--snapshot-id`, `--label-version`, `--fa-version`, periods, and `--created-at` (`scripts/run_feature_build.py:65`).
- **MEDIUM:** `FIXED_REPRODUCE_TS` wording does not match this script. `run_feature_build.py` defaults `created_at` from the current date (`scripts/run_feature_build.py:119`), though the SHA excludes metadata.
- **MEDIUM:** Same `feature_count=106` ambiguity as Plan 10-04.

**Suggestions**
- Update tests and wording to use `feature_availability_version`, or deliberately rename the code and all downstream readers.
- Fix the live command and pass `--fa-version 0.6.0`; pass `--created-at` if cross-day byte identity is required.

**Risk: MEDIUM.**

### Plan 10-06 (SC#5 non-inferiority gate)

**Strengths**
- The measured-delta gate is well designed. Comparing Phase 10 against a baseline snapshot re-run under the same settings protects §11.2 better than comparing to hardcoded Phase 6 numbers (`10-06-PLAN.md:29`, `10-06-PLAN.md:192`).
- This matches the existing stopgate pattern, which loads both snapshots (`scripts/run_speed_figure_stopgate.py:583`) and trains both through `train_and_predict` with explicit snapshot IDs (`scripts/run_speed_figure_stopgate.py:611`, `scripts/run_speed_figure_stopgate.py:622`).
- Dynamic feature derivation is real: `_derive_feature_columns(snapshot_id)` reads registry and Parquet schema (`src/model/data.py:179`), and `make_X_y` asserts exact `X.columns` equality (`src/model/data.py:487`).

**Concerns**
- **HIGH:** The plan's shorthand says call `orchestrator.train_and_predict(snapshot_id=...)` (`10-06-PLAN.md:44`), but the actual function requires a label-joined `feature_df` and `feature_snapshot_id` (`src/model/orchestrator.py:234`). Missing labels fail loud (`src/model/orchestrator.py:353`). The implementation must copy the stopgate's load/join flow.
- **MEDIUM:** "Category map bit-identical" is asserted (`10-06-PLAN.md:29`), but the existing stopgate loads maps per snapshot (`scripts/run_speed_figure_stopgate.py:596`). If this is part of the gate, compare category-map hashes explicitly.
- **MEDIUM:** Constants prevent accidental drift in code, but they do not mechanically prove tolerances were not changed after seeing results. The report should record tolerance values and the script git hash before live execution.
- **LOW:** Selected-only calibration and odds-band diagnostics are useful but require market columns; segment axes expect `odds_band`/`ninki_band` style inputs (`src/model/segment_eval.py:81`). Keep them diagnostic-only as planned.

**Suggestions**
- Base `run_phase10_evaluation.py` directly on `run_speed_figure_stopgate.py`'s snapshot-load, label-join, frozen-map, and train-call flow.
- Write a pre-run manifest containing tolerance constants, snapshot IDs, trainer params, category-map hashes, and git commit.

**Risk: MEDIUM.**

### Plan 10-07 (SAFE-01 adversarial audit + perf)

**Strengths**
- Reusing the existing adversarial audit pattern is appropriate. The scanner already checks AST `Name`/`Attribute` nodes (`tests/audit/test_audit_speed_figure.py:86`) and has a false-pass injection test (`tests/audit/test_audit_speed_figure.py:309`).
- The lookahead monkeypatch target is a good pattern because strict PIT helpers exist and are isolated (`src/features/speed_figure.py:98`, `src/features/rolling.py:114`).
- A pre-registered performance budget is useful because the research explicitly flags field-strength pair explosion (`10-RESEARCH.md:425`) and only assigns medium confidence to runtime (`10-RESEARCH.md:626`).

**Concerns**
- **HIGH:** The current string-literal proxy scanner intentionally excludes `"odds"` from substring checks (`tests/audit/test_audit_speed_figure.py:39`). Plan 10-07 claims SQL literals containing `odds` are detected (`10-07-PLAN.md:19`), but direct reuse of the current scanner would miss SQL text containing only `odds`. The plan's claim "SQL 文字列リテラルに odds/ninki/... の word-boundary 部分一致が0件" is not mechanically enforced by the existing scanner.
- **MEDIUM:** The current scanner checks all `ast.Constant` strings, not just SQL (`tests/audit/test_audit_speed_figure.py:100`). That means romanized forbidden words in docstrings can false-positive, while comments are not scanned at all.
- **HIGH:** The proposed lookahead injection focuses on changing `<` to `<=` (`10-07-PLAN.md:22`). It must also catch the more important Plan 10-01 risk: opponent races after the source race but before the target cutoff. The current monkeypatch plan only proves the source-vs-opponent guard, not the source-vs-target-cutoff guard.
- **LOW:** "No Python loop in cProfile top 3" can be brittle with pandas internals. Static checks for `iterrows`, `itertuples`, row-wise `apply`, plus wall-clock budget, are more stable.

**Suggestions**
- Update the audit scanner to include `odds` in SQL-like string checks, with an explicit whitelist for harmless prose such as `odds-free`.
- Add an adversarial source-vs-target cutoff test.
- Keep cProfile output as evidence, but make wall-time and static anti-pattern checks the hard gates.

**Risk: HIGH.**

### Overall Risk Assessment

Overall Phase 10 plan risk is **HIGH** right now. The architecture and sequencing are mostly
sound, but the core leakage surface is unresolved: `field_strength` must be computed from
opponent ability available strictly before each **source race**, and current code does not
provide that table. Fix that dataflow, strengthen the SAFE-01 SQL scanner, and correct the
snapshot/evaluation API mismatches before implementation.

---

## Consensus Summary (single-reviewer cycle)

This cycle invoked Codex only (per `--codex`). There is no second reviewer to converge or
diverge with, so the summary below restates the single reviewer's findings ranked by severity
and leakage relevance. The planner should treat these the same way as multi-reviewer consensus
HIGHs — incorporate into PLAN.md or explicitly defer with rationale.

### Agreed (single-reviewer) Strengths
- Strict `< cutoff` PIT invariant is consistently anchored to existing code (`availability.py:45`, `speed_figure.py:98`, `rolling.py:114`).
- `obs_id`-scoped latest-K rolling design and sentinel/count rules reuse the speed_figure idiom faithfully (`rolling.py:297/375/524`).
- Registry parity and dynamic `FEATURE_COLUMNS` derivation already exist and are correctly leveraged (`builder.py:644`, `availability.py:314`, `data.py:179/487`).
- Measured baseline-vs-Phase10 delta gate (B-3) is a genuine improvement over hardcoded Phase 6 thresholds for §11.2 protection.
- Byte-reproducibility machinery (`snapshot.py:221/236/273`) is correctly identified and reused.

### Agreed (single-reviewer) Concerns — ranked
1. **HIGH (10-01, leakage):** `history` lacks `rolling_speed_figure_mean_5`; the plan does not specify how opponent rolling ability is produced per source race.
2. **HIGH (10-01, leakage):** Target-cutoff-expanded `speed_figure` values, if reused for source-race opponent ability, leak races between source and target dates. The strict `<` guard only covers opponent-vs-source, not source-vs-target-cutoff.
3. **HIGH (10-07, SAFE-01 unsoundness):** Existing scanner excludes `"odds"` from string substring checks, so the plan's claim that SQL `odds` literals are detected is not enforced by direct reuse.
4. **HIGH (10-07, audit gap):** Lookahead injection only tests source-vs-opponent (`<` → `<=`); the source-vs-target-cutoff leak path is untested.
5. **HIGH (10-05, spec mismatch):** Metadata key `feature_availability_schema_version` does not exist in code; the real key is `feature_availability_version`.
6. **HIGH (10-06, API mismatch):** `orchestrator.train_and_predict` requires a label-joined `feature_df`, not just a `snapshot_id`; the plan's shorthand will fail loud or silently short-circuit.
7. **MEDIUM (10-03):** `gap_to_3rd` ambiguous under ties (no rank-3 in `[1,2,2,4]`).
8. **MEDIUM (10-04/10-05/10-06):** `feature_count == 106` is ambiguous between Parquet column count and model feature count.
9. **MEDIUM (10-02):** Inherits the 10-01 leak; needs an explicit source-cutoff gate test.
10. **MEDIUM (10-06):** Category-map bit-identity is asserted but not mechanically verified.

### Divergent Views
- (Single reviewer — no divergence this cycle. A second reviewer in a later cycle could
  either corroborate the leakage severity or argue the source-race cutoff is implicitly
  handled by a downstream step the reviewer did not trace.)

### Cross-cycle leakage-priority call-out
The two 10-01 HIGHs and the two 10-07 HIGHs are the four findings that bear directly on the
project's core value (leakage prevention). They must be resolved at the planning level — not
deferred to execution-time discovery — because a leak that passes the adversarial audit will
not be caught again until the model is trained.

---

## Verification coverage

| Plan | Source-grounded evidence cited | Leakage-relevant finding? |
|------|-------------------------------|---------------------------|
| 10-01 | `availability.py:45`, `speed_figure.py:98/579/640/681/697`, `rolling.py:114`, `builder.py:531/535`, `10-CONTEXT.md:27/28`, `10-RESEARCH.md:425`, `10-PATTERNS.md:104` | YES (HIGH ×2) |
| 10-02 | `rolling.py:23/136/297/370/375/448/515/524/640/687`, `snapshot.py:116` | YES (inherits 10-01) |
| 10-03 | `10-CONTEXT.md:34/39`, `builder.py:618`, `10-03-PLAN.md:20/23/26/96/119`, `tests/audit/test_audit_speed_figure.py:100` | partial (gap_to_3rd ambiguity, AST docstring scope) |
| 10-04 | `builder.py:525/531/535/644/618`, `availability.py:143/188/314/333`, `scripts/run_feature_build.py:232`, `data.py:179`, `10-04-PLAN.md:20/22/29` | no (parity/feature_count ambiguity) |
| 10-05 | `snapshot.py:62/99/116/221/236/266/273`, `10-RESEARCH.md:455`, `scripts/run_feature_build.py:65/119/232`, `10-05-PLAN.md:25/151` | no (metadata key + CLI flag mismatch) |
| 10-06 | `10-06-PLAN.md:29/44/192`, `scripts/run_speed_figure_stopgate.py:583/596/611/622`, `data.py:179/487`, `orchestrator.py:234/353`, `segment_eval.py:81` | no (API mismatch; §11.2 protection) |
| 10-07 | `tests/audit/test_audit_speed_figure.py:39/86/100/309`, `speed_figure.py:98`, `rolling.py:114`, `10-RESEARCH.md:425/626`, `10-07-PLAN.md:19/22` | YES (HIGH ×2 — SQL scanner gap, lookahead scope) |
