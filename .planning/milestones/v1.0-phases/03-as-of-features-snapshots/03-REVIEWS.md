---
phase: 3
reviewers: [codex]
cycles:
  - cycle: 1
    reviewers: [codex]
    reviewed_at: 2026-06-18T14:38:32Z
    plans_reviewed: [03-01-PLAN.md, 03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md]
    high_count: 6
    status: superseded (revisions applied: commits 3ed8c84, c8795f6, 26fe3a1)
  - cycle: 2
    reviewers: [codex]
    reviewed_at: 2026-06-19T07:10:00Z
    plans_reviewed: [03-01-PLAN.md, 03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md]
    plans_revision_head: 26fe3a1
    high_count: 3   # unresolved HIGHs remaining this cycle (see CYCLE_SUMMARY in Consensus)
  - cycle: 3
    reviewers: [codex]
    reviewed_at: 2026-06-19T07:30:00Z
    plans_reviewed: [03-01-PLAN.md, 03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md]
    plans_revision_head: cabfa9d
    high_count: 0   # convergence achieved — all 6 cycle-1 HIGHs now CLOSED
    status: APPROVED (convergence-loop final cycle, 0 HIGH remaining)
---

# Cross-AI Plan Review — Phase 3

> Phase 3 is the leakage-prevention backbone of Keiba AI v3: point-in-time-correct
> feature generation (FEAT-01) and immutable reproducible Parquet snapshots (FEAT-02).
> Reviewers were asked to be rigorous about leakage vectors, since reproducibility
> and leakage prevention are the project's non-negotiable core value.

---

# CYCLE 1 (2026-06-18) — original plans

> Retained verbatim for traceability. The cycle-1 HIGHs were addressed by two
> planner revision passes (commits `3ed8c84` → `c8795f6` → `26fe3a1`, HEAD).
> Cycle 2 below re-evaluates the *revised* plans against these same 6 HIGHs.

## Codex Review

### Summary

The four-plan set is directionally strong and clearly treats Phase 3 as the
leakage-prevention backbone: it establishes an availability registry first, fixes
the `race_date` prerequisite, then builds PIT rolling features, and finally writes
reproducible Parquet snapshots with frozen category maps. The wave ordering is
mostly sound and the plans repeatedly encode the right invariants: no banned Phase
1-A timings, `feature_cutoff_datetime = race_date - 1 day`, train-only category
maps, deterministic Parquet, and fail-loud tests. The main risk is that several
critical tests are described as source-code/`inspect.getsource` guards rather than
behavioral leak tests, and the rolling/PIT implementation in `03-03-PLAN.md` is
underspecified enough that future rows could still sneak in despite the stated
intent.

### Strengths

- Clear dependency ordering:
  - `03-01-PLAN.md` creates the registry and RED tests.
  - `03-02-PLAN.md` fixes `label.fukusho_label.race_date`, which is required before cutoff computation.
  - `03-03-PLAN.md` builds the feature matrix.
  - `03-04-PLAN.md` handles snapshot immutability and category maps.

- `03-01-PLAN.md` correctly makes the Phase 1-A allowlist a structural gate using `available_from_timing` and banned timings.

- `03-02-PLAN.md` correctly treats the `race_date` backfill as a prerequisite for FEAT-01, and includes idempotency, raw immutability, and reader GRANT checks.

- `03-03-PLAN.md` explicitly rejects `SELECT *`, banned columns, same-day leakage, `kyakusitukubun`, `harontimel4`, and `umaban` as key.

- `03-04-PLAN.md` correctly emphasizes deterministic Parquet writes, sorted row order, fixed metadata, SHA256 verification, and train-window-only frozen category maps.

- Cold-start and missingness are at least recognized: `__MISSING__`, `__UNSEEN__`, rolling count, and non-negative int32 category codes are all called out.

### Concerns (Cycle 1)

- **HIGH — Rolling PIT logic in `03-03-PLAN.md` is not concretely safe enough.**
  The plan says to use `pit_join_backward`, but also describes "get latest 5 starts"
  in vague ways. A single backward as-of join only retrieves one latest row, not
  five. If the implementation precomputes rolling windows per horse without
  `closed='left'` and without observation-specific cutoff filtering, the target race
  or same-day races can leak. This needs an explicit algorithm: for each observation,
  use only history rows where `history.as_of_datetime < observation.feature_cutoff_datetime`,
  then take latest 5.

- **HIGH — `feature_cutoff_datetime = race_date - 1 day` prevents same-day leakage, but only if every history feature uses strict `< cutoff`, not `<= cutoff`.**
  Several places say "cutoff 以前" while acceptance criteria mention `<`. For
  `race_date - 1 day`, using `<=` includes races on the previous day, which is
  acceptable if cutoff means end-of-previous-day, but the metadata must define
  whether cutoff is midnight or end-of-day. If represented as `YYYY-MM-DD 00:00:00`,
  `<=` will exclude most previous-day races unless `as_of_datetime` is date-only.
  This ambiguity can cause either leakage or accidental data loss.

- **HIGH — `03-01-PLAN.md` allowlist can pass while banned source columns still enter under "allowed" feature names.**
  The test checks `available_from_timing`, but does not require that every output
  matrix column maps to a registry entry. A developer could add
  `same_day_track_condition` with `entry_confirmed`, or include an unregistered
  output column, and pass the timing test. The fail-loud test must validate actual
  matrix columns against the registry and reject unregistered columns.

- **HIGH — `03-03-PLAN.md` includes `babacd` rolling from past races but `03-01-PLAN.md` says `sibababacd`/`dirtbabacd` must not appear in sources.**
  Past-race track condition is allowed only as historical feature, but the blanket
  banned-column test may reject it entirely. The plan needs a precise distinction:
  source columns are banned for the target race observation SELECT, but may be
  allowed in history SELECT if joined strictly before cutoff and named as rolling
  historical features.

- **HIGH — Category-map train-only fit in `03-04-PLAN.md` risks row-composition leakage if the full matrix includes raw ID columns unchanged.**
  If `horse_id`, `jockey_id`, etc. remain as raw string/object columns alongside
  `_code` columns in the snapshot, Phase 4 could accidentally train on raw IDs or
  refit later. The snapshot should either drop raw categorical ID feature columns
  after coding or mark them as key/audit-only and enforce model-input column
  selection.

- **HIGH — Snapshot reproducibility conflicts with manifest `created_at`.**
  `03-04-PLAN.md` says schema metadata `created_at` is fixed, but manifest includes
  real `created_at`. That is okay only if byte reproducibility applies to Parquet
  bytes, not manifest bytes. The success criteria should explicitly distinguish
  "Parquet byte hash reproducible" from "manifest records run time and is not
  byte-reproducible."

- MEDIUM — `03-02-PLAN.md` staging-swap for a one-column backfill is high blast radius.
- MEDIUM — `03-02-PLAN.md` is marked `depends_on: []`, but `03-03-PLAN.md` should depend on both `03-01` and `03-02`.
- MEDIUM — Tests rely too much on `inspect.getsource`.
- MEDIUM — Rolling features with `__MISSING__` string sentinels in numeric columns may create mixed dtypes.
- MEDIUM — `03-04-PLAN.md` row group size likely misunderstands PyArrow units.
- MEDIUM — `03-04-PLAN.md` deterministic PyArrow writes may still vary if schema inference varies.
- LOW — "25 features" vs "43 entries" is confusing.
- LOW — Warm-up exclusion is not fully enforced.

### Risk Assessment (Cycle 1)

**Overall risk: HIGH.** The phase plan is strong in intent but this is the project's
leakage-prevention backbone, and the original plans still left dangerous
implementation ambiguity around rolling PIT joins, actual matrix-column
allowlisting, historical-vs-target banned column semantics, and deterministic
schema writing.

### Cycle 1 Action Items (addressed by revisions)

1. [HIGH] Pin the exact rolling PIT algorithm in `03-03-PLAN.md`.
2. [HIGH] Define `feature_cutoff_datetime` semantics explicitly.
3. [HIGH] Strengthen the allowlist test to validate actual matrix output columns.
4. [HIGH] Split banned columns into `_OBS_BANNED` vs `_HISTORY_ALLOWED_POST_RACE_SOURCE`.
5. [HIGH] Decide raw ID column disposition in the snapshot.
6. [HIGH] Clarify the SHA256 scope.
7. [MEDIUM] Reconsider the staging-swap in `03-02-PLAN.md`.
8. [MEDIUM] Add `03-02` as an explicit dependency of `03-03-PLAN.md`.
9. [MEDIUM] Add behavioral adversarial tests alongside the source guards.
10. [MEDIUM] Fix `row_group_size` units and require an explicit fixed Arrow schema.

---

# CYCLE 2 (2026-06-19) — re-review of revised plans (HEAD: 26fe3a1)

> The planner applied three revision commits to address cycle-1 HIGHs and plan-checker
> BLOCKERs. This cycle re-evaluates the **current** plans against the 6 prior HIGHs —
> confirming each is genuinely closed (backed by a mechanical mechanism + test, not
> just described) — and surfaces any NEW leakage concerns the revisions introduced.

## Codex Review (Cycle 2)

### Summary

The revision genuinely closes HIGH #3, #4, and #6 with concrete mechanisms and
tests. HIGH #2 and #5 are close but still have a consistency/contract gap that must
be fixed. HIGH #1 is **NOT** genuinely closed: the concrete rolling algorithm, as
specified, groups by horse (`kettonum`) rather than by observation row, so when a
horse appears in multiple target races with different cutoffs the per-observation
window is not mechanically enforced — and the adversarial test only covers a single
observation, so it would not catch the multi-observation regression. Phase 3
implementation should not proceed until the rolling algorithm is changed to an
`obs_id`-scoped latest-K and the cutoff invariant is made single-source.

### Per-Prior-HIGH Verdict

- **HIGH #1 — STILL OPEN.** The revised plan correctly rejects single `merge_asof` and adds adversarial tests, but the specified algorithm is not actually per-observation safe when there are multiple observations for the same horse. It says:

  > "strict `< cutoff` pre-filter → `sort_values(["kettonum","race_start_datetime"], ascending=[True,False])` → `groupby("kettonum").head(5)`"

  That groups only by `kettonum`, not by observation row. If the same horse appears
  in multiple target races, a single global latest-5 per horse can be reused
  incorrectly across different cutoffs. The prose elsewhere says "各 observation 毎",
  but the concrete vectorized algorithm does not mechanically enforce that. The 5-row
  adversarial test appears to cover one observation only, so it would not catch
  multi-observation leakage/regression.

  Required closure: create an observation id, join/cross-filter history per
  `(obs_id, kettonum)`, apply `history.as_of_datetime < obs.feature_cutoff_datetime`,
  sort within `obs_id`, then `groupby(obs_id).head(5)`. Add a test with the same
  horse in two target observations with different cutoffs and verify each gets a
  different latest-5 window.

- **HIGH #2 — PARTIALLY RESOLVED.** A strong mechanism exists:

  > `comparison_operator: "strict_less_than"`
  > `history.as_of_datetime < observation.feature_cutoff_datetime`
  > `previous_day_row ... as_of_datetime == feature_cutoff_datetime ... strict < なので必ず除外`

  Test exists: `test_cutoff_excludes_previous_day_race_strict_less_than`.

  However, `03-01-PLAN.md:30` (must_have truth) describes a **different** semantics:
  `feature_cutoff_datetime = race_date - 1 day` ... "PIT join is strict
  `< feature_cutoff_datetime + 1 day` i.e. `< midnight of race_date`" — i.e., the
  previous day IS allowed. The revised plan body instead uses strict
  `< feature_cutoff_datetime`, which excludes the entire previous day. Both are
  leak-safe in different ways, but they produce **different feature values**, and the
  spec is internally inconsistent (`< cutoff` in availability.py/tests/builder vs
  `< cutoff + 1 day` in the must_have truth). Closure for leakage is OK; closure for
  spec consistency is partial until one canonical invariant is normalized everywhere
  (YAML, tests, builder, rolling, CLAUDE.md references).

- **HIGH #3 — CLOSED.** Mechanism: `assert_matrix_columns_registered(spec, output_columns)`,
  with builder integration calling it on `list(feature_matrix.columns)`. Tests:
  `test_matrix_rejects_unregistered_column`,
  `test_matrix_rejects_banned_timing_column_under_allowed_name`,
  `test_builder_output_columns_all_registered_in_registry`. This is the right level —
  actual output columns, not only registry timing metadata.

- **HIGH #4 — CLOSED (with one cosmetic caveat).** Mechanism: `source_role` field
  (`target_obs_banned / history_allowed_post_race / both_allowed`), with
  `TARGET_OBS_BANNED_COLUMNS = {... sibababacd, dirtbabacd ...}` and
  `HISTORY_ALLOWED_POST_RACE_COLUMNS = {... babacd ...}`, plus the
  `_TARGET_OBS_BANNED_COLUMNS.isdisjoint(_HISTORY_SELECT_COLUMNS)` startup assert.
  Tests: `test_target_obs_banned_columns_not_in_registry_features`,
  `test_history_allowed_babacd_rolling_present`, `test_banned_columns_not_selected`.
  Caveat (non-blocking): the `TARGET_OBS_AND_HISTORY_BANNED` name is misnamed
  (it implies history-allowed columns are banned). The actual enforcement split is
  sound; only the name is confusing.

- **HIGH #5 — PARTIALLY RESOLVED.** Mechanism: `apply_frozen_category_maps` ... `.drop(columns=list(_CATEGORY_COLUMNS))`, leaving only `_code` suffix columns. Tests: `test_apply_frozen_maps_drops_raw_id_columns`, `test_apply_frozen_maps_no_raw_id_in_output_schema`.

  New risk (contract fragility): the plan says the builder should
  `rename(columns={... "kettonum": "horse_id"})`, while also preserving canonical
  key `kettonum`. A pandas `rename` is destructive — it cannot both rename AND
  preserve the original column. Later snapshot sorting requires
  `_SNAPSHOT_SORT_KEYS = ("race_date", "jyocd", "racenum", "kettonum")`. If
  `kettonum` is dropped/renamed before snapshot, canonical sorting and key checks
  can break. Closure requires an explicit **copy-not-rename** contract:
  `feature_matrix["horse_id"] = feature_matrix["kettonum"]`; never rename/drop
  `kettonum` until after all key/snapshot operations, and only drop
  `_CATEGORY_COLUMNS`, not key columns.

- **HIGH #6 — CLOSED.** Mechanism: "SHA256 scope は Parquet bytes のみ",
  `hashlib.sha256(data).hexdigest()` where `data = buf.getvalue().to_pybytes()`,
  manifest has `created_at_real` and `byte_reproducible_scope: "parquet_bytes_only"`.
  Tests: `test_sha256_covers_parquet_bytes_only`, `test_manifest_created_at_varies_between_runs`.
  This cleanly separates reproducible Parquet bytes from non-reproducible run metadata.

### New Concerns (introduced or newly surfaced by the revisions)

- **NEW HIGH (NEW-1) — rolling latest-5 must group by observation, not horse.**
  This is the main blocker and is the same defect as HIGH #1 (re-stated as a new
  finding because the cycle-1 closure did not fix the root cause). The plan's current
  concrete algorithm can leak or miscompute when a horse has multiple target
  observations. Fix the algorithm to `obs_id`-scoped latest-K and add a two-observation
  adversarial test (same horse, two target races, two different cutoffs, verify each
  gets a different latest-5 window).

- **NEW HIGH (NEW-2) — cutoff semantics conflict must be resolved before implementation.**
  Pick one canonical invariant (`< feature_cutoff_datetime` OR `< feature_cutoff_datetime + 1 day`)
  and update YAML, must_have truths, tests, builder, rolling, and CLAUDE.md references
  consistently. Both are leak-safe but produce different feature values.

- **NEW MEDIUM/HIGH (NEW-3) — `kettonum`/`horse_id` rename contract can break canonical keys and snapshot sorting.**
  Do not rename `kettonum` destructively. Copy to `horse_id` for category encoding,
  preserve `kettonum` for keys and snapshot ordering, and add a test that both
  `kettonum` remains and raw `horse_id` is dropped after encoding.

### Overall Verdict (Cycle 2)

The revision genuinely closes HIGH #3, #4, and #6. HIGH #2 and #5 are close but
need consistency/contract fixes. HIGH #1 is still open because the specified
latest-5 algorithm is not mechanically per-observation despite the prose claiming it
is. Phase 3 implementation should not be approved until the rolling algorithm is
changed to `obs_id`-scoped latest-K and the cutoff invariant is made single-source
and unambiguous.

### Cycle 2 Action Items for Planner (`/gsd-plan-phase 3 --reviews`)

1. **[HIGH, re-open of #1 / NEW-1]** Rewrite the rolling algorithm in `03-03-PLAN.md`
   to be mechanically per-observation: introduce an `obs_id` (= canonical observation
   key `(race_nkey, kettonum)`), cross-filter history per `(obs_id, kettonum)` with
   `as_of_datetime < feature_cutoff_datetime`, sort DESC within `obs_id`, then
   `groupby("obs_id").head(5)`. Replace every `groupby("kettonum")` in the rolling
   window step with `groupby("obs_id")`. Add a two-observation adversarial test
   (same horse in two target races with different cutoffs) asserting each observation
   gets a distinct latest-5 window.
2. **[HIGH, partial #2 / NEW-2]** Resolve the cutoff-semantics conflict to a single
   canonical invariant. Update `03-01-PLAN.md` must_have truth (line 30), the
   `CUTOFF_SEMANTICS` constant, the `cutoff_semantics` YAML block, builder/rolling
   filter code, and the CLAUDE.md reference so they all agree on either
   `< feature_cutoff_datetime` or `< feature_cutoff_datetime + 1 day`. State which
   one is chosen and why.
3. **[HIGH, partial #5 / NEW-3]** Fix the `kettonum`→`horse_id` contract to
   copy-not-rename: `feature_matrix["horse_id"] = feature_matrix["kettonum"]`, never
   drop `kettonum` until after all canonical-key/snapshot operations, and only drop
   `_CATEGORY_COLUMNS`. Add a test asserting `kettonum` is preserved AND raw
   `horse_id` is absent after encoding.
4. **[LOW, cosmetic, HIGH #4 closure cleanup]** Rename the misnamed
   `TARGET_OBS_AND_HISTORY_BANNED` set so it does not imply history-allowed columns
   are banned.

---

## Consensus Summary (Cycle 2)

> Only one external reviewer (Codex) was invoked in this cycle (same as cycle 1;
> `--codex` was the requested reviewer and Gemini/other CLIs are unavailable). The
> verdicts below reflect Codex's re-evaluation of the revised plans, and were
> independently spot-checked against the plan source by the orchestrator (the HIGH #1
> groupby defect, the HIGH #2 `< cutoff` vs `< cutoff + 1 day` inconsistency, and the
> HIGH #5 destructive-rename contradiction are all confirmed present in the current
> plan text).

### Status of the 6 Cycle-1 HIGHs (this cycle)

| # | Concern | Cycle-2 Verdict | Why |
|---|---------|-----------------|-----|
| 1 | Rolling PIT algorithm under-specified | **STILL OPEN** | Concrete algo groups by `kettonum` (horse), not observation; single-obs adversarial test cannot catch multi-obs regression. |
| 2 | cutoff `<` vs `<=` ambiguity | **PARTIALLY RESOLVED** | Mechanism + boundary test exist, but `< cutoff` (body) vs `< cutoff + 1 day` (must_have truth) produce different feature values; spec inconsistent. |
| 3 | Allowlist lets banned columns sneak in | **CLOSED** | `assert_matrix_columns_registered` on actual output columns + 3 tests. |
| 4 | `babacd` conflated with `sibababacd`/`dirtbabacd` | **CLOSED** (cosmetic naming caveat) | `source_role` taxonomy + disjoint assert + 3 tests. |
| 5 | Raw ID columns linger, Phase 4 refit risk | **PARTIALLY RESOLVED** | `.drop(columns=_CATEGORY_COLUMNS)` + tests exist, but destructive `rename(kettonum→horse_id)` contradicts preserving `kettonum` as canonical key / snapshot sort key. |
| 6 | SHA256 vs manifest `created_at` | **CLOSED** | SHA256 scoped to Parquet bytes; manifest `created_at_real` + `byte_reproducible_scope` + 2 tests. |

### Agreed Strengths (this cycle)

- Genuinely closed HIGH #3 / #4 / #6 with mechanical mechanisms and adversarial/unit tests — not just prose.
- The documented, audit-trailed deviation from `merge_asof(direction='backward')` for the rolling window is the correct call (single backward join returns latest-1, not latest-5); the replacement pre-filter preserves leak-safety *if* made per-observation.
- SHA256 scope and the Parquet-bytes-vs-manifest distinction are now precisely specified and testable.

### Agreed Concerns (this cycle — unresolved HIGHs)

1. **HIGH #1 re-open / NEW-1** — rolling algorithm groups by horse, not observation.
2. **HIGH #2 partial / NEW-2** — cutoff-semantics conflict (`< cutoff` vs `< cutoff + 1 day`) produces different feature values and the spec is inconsistent.
3. **HIGH #5 partial / NEW-3** — destructive `kettonum`→`horse_id` rename breaks the canonical-key / snapshot-sort contract.

### Divergent Views

(Single reviewer across both cycles — no cross-reviewer divergence. Re-running with a
second reviewer would strengthen consensus, but Codex's three open HIGHs were each
independently confirmed against the plan source by the orchestrator.)

### CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=3

## Current HIGH Concerns

- **HIGH #1 (re-open) / NEW-1 — rolling latest-5 groups by horse, not observation.** The concrete algorithm in `03-03-PLAN.md` (`sort_values(["kettonum","race_start_datetime"]).groupby("kettonum").head(5)`) groups the per-observation-filtered history by `kettonum` (horse), not by observation row. When a horse appears in multiple target races with different cutoffs, the per-observation window is not mechanically enforced and a single global latest-5 can be reused across cutoffs. The single-observation 5-row adversarial test (`test_per_observation_latest_5_excludes_target_same_day_previous_future`) cannot detect this. Fix: group by `obs_id` (= `(race_nkey, kettonum)`), and add a two-observation adversarial test.
- **HIGH #2 (partial) / NEW-2 — cutoff-semantics conflict.** `03-01-PLAN.md` must_have truth (line 30) specifies `< feature_cutoff_datetime + 1 day` (previous day allowed; `< midnight of race_date`), while the availability.py `CUTOFF_SEMANTICS`, the builder filter, the rolling pre-filter, and `test_cutoff_excludes_previous_day_race_strict_less_than` all use strict `< feature_cutoff_datetime` (previous day excluded). Both are leak-safe but produce different feature values. One canonical invariant must be chosen and normalized across YAML, tests, builder, rolling, and CLAUDE.md.
- **HIGH #5 (partial) / NEW-3 — destructive `kettonum`→`horse_id` rename contract.** The builder contract states `feature_matrix.rename(columns={"kettonum": "horse_id", ...})` while also requiring `kettonum` to remain as the canonical key and `_SNAPSHOT_SORT_KEYS = ("race_date","jyocd","racenum","kettonum")` for snapshot ordering. `pd.DataFrame.rename` is destructive — it cannot both rename and preserve the column. As written, snapshot sorting / canonical-key uniqueness checks can break. Fix: copy-not-rename (`feature_matrix["horse_id"] = feature_matrix["kettonum"]`), preserve `kettonum` through all key/snapshot operations, drop only `_CATEGORY_COLUMNS`, and add a test that `kettonum` is preserved and raw `horse_id` is absent post-encoding.

---

# CYCLE 3 (2026-06-19) — convergence-loop final cycle, re-review of revised plans (HEAD: cabfa9d)

> The planner applied commit `7928b50` ("revise plans (CYCLE-2) — close HIGH #1/#2/#5")
> followed by `cabfa9d` (mark phase planned) to address the 3 cycle-2 HIGHs:
> per-observation `obs_id` rolling + two-observation adversarial test (#1), strict
> `< feature_cutoff_datetime` normalized across all surfaces (#2), copy-not-rename
> preserving `kettonum` (#5). This cycle is the **final** cycle of the 3-cycle
> convergence loop. Its job is an independent verification — not a rubber stamp — that
> the 3 cycle-2 HIGHs are NOW genuinely closed (mechanism + adversarial test that
> would mechanically fail under the old buggy implementation), that the previously
> closed HIGHs #3/#4/#6 and the 8-system/40-entry reconciliation did not regress,
> and that the revisions did not introduce any NEW leakage HIGH.

## Codex Review (Cycle 3)

### Summary

The 3 previously-open cycle-2 HIGHs are now genuinely closed in the revised current
plans (HEAD `cabfa9d`). HIGH #1 has a real per-observation fan-out mechanism plus a
two-observation boundary adversarial test; HIGH #2 is consistently normalized to strict
`< feature_cutoff_datetime`; HIGH #5 now uses copy-not-rename and preserves `kettonum`
through encoding. No regressions on the closed HIGH #3/#4/#6, and the 8-system/40-entry
reconciliation is internally consistent. No NEW HIGH concerns were introduced by the
revisions. The convergence loop has achieved its goal: **0 HIGHs remain**.

### Per-Prior-HIGH Verdict (this cycle)

- **HIGH #1 — CLOSED.**
  Mechanism: `obs_id = list(zip(observations["race_nkey"], observations["kettonum"]))`;
  expanded history is built (step 1b) by joining
  `observations[["obs_id","kettonum","feature_cutoff_datetime"]]` to `history` on
  `kettonum`; the strict `<` cutoff filter (step 2) is applied **after** fan-out as
  `history_filtered = expanded[expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]]`;
  latest-5 uses `sort_values(["obs_id","race_start_datetime"], ascending=[True,False]).groupby("obs_id").head(lookback)`.
  Test: `test_two_observation_window_is_per_observation_not_per_horse` — obs_A cutoff
  `2023-06-03`, obs_B cutoff `2023-06-10`, and a boundary row `obs_B_only_pre` with
  `as_of="2023-06-05"` that must be excluded from obs_A (post its cutoff) and included
  in obs_B (pre its cutoff).
  Adversarial reasoning: a horse-grouped `groupby("kettonum").head(5)` implementation
  would either share one window across both observations or fail to produce obs-specific
  windows, so obs_A would be contaminated by the obs_B-only boundary row, or both
  observations would collapse to the same aggregate. The cutoff is read per expanded row
  (not once before expansion), which is what makes per-observation safety mechanical
  rather than aspirational. This test would catch the old bug. **CLOSED.**

- **HIGH #2 — CLOSED.**
  Mechanism: `CUTOFF_SEMANTICS = {"comparison_operator": "strict_less_than", ...
  "pit_filter": "history.as_of_datetime < observation.feature_cutoff_datetime"}`,
  mirrored in YAML `cutoff_semantics` block; builder computes
  `feature_cutoff_datetime = pd.to_datetime(race_date) - pd.Timedelta(days=1)`; rolling
  filters with strict `<`; the cycle-2 must_have truth (line 30) was rewritten to the
  canonical strict `< feature_cutoff_datetime` form and the deprecated `+ 1 day` form is
  explicitly marked abolished.
  Test: `test_cutoff_excludes_previous_day_race_strict_less_than`, where the
  `previous_day_row` has `as_of_datetime == '2023-06-03'` exactly equal to
  `feature_cutoff_datetime`.
  Adversarial reasoning: an old `< feature_cutoff_datetime + 1 day` or
  `<= feature_cutoff_datetime` implementation would include the equality row; strict `<`
  excludes it. The only remaining `+ 1 day` mentions in the repo are in REVIEWS.md's own
  archived cycle-1/2 history, which are not active rules. No active plan surface uses the
  `+ 1 day` form. **CLOSED.**

- **HIGH #5 — CLOSED.**
  Mechanism: builder uses copy-not-rename —
  `feature_matrix["horse_id"] = feature_matrix["kettonum"]`, plus analogous copies for
  jockey/trainer/sire/bms. Category consumer defines
  `_CATEGORY_COLUMNS = ("jockey_id","trainer_id","sire_id","bms_id","horse_id")` (exactly
  5 elements, excludes `kettonum`), drops only `list(_CATEGORY_COLUMNS)`, and explicitly
  states `kettonum` is preserved. Snapshot sort key remains
  `_SNAPSHOT_SORT_KEYS = ("race_date","jyocd","racenum","kettonum")`.
  Test: `test_apply_frozen_maps_preserves_kettonum_canonical_key`, asserting
  `assert "kettonum" in result.columns and "horse_id" not in result.columns` after
  `apply_frozen_category_maps`.
  Adversarial reasoning: a destructive `rename(columns={"kettonum": "horse_id"})` would
  remove `kettonum`, so this test would fail after encoding. No plan body now contains a
  destructive `rename` of the live feature matrix. **CLOSED.**

### Regression Check

- **HIGH #3 — still CLOSED.** `assert_matrix_columns_registered(spec, output_columns)`
  validates actual output columns, and the builder is required to call
  `assert_matrix_columns_registered(spec, list(feature_matrix.columns))`. The revised
  `_code` auto-whitelist (`{c + "_code" for c in _CATEGORY_COLUMNS}`) is limited to the
  closed 5-tuple `_CATEGORY_COLUMNS`, so an arbitrary `evil_leak_code` column cannot pass
  unless a future developer expands `_CATEGORY_COLUMNS`. This is a future-governance
  surface, not a current leakage HIGH — flagged as LOW below.
- **HIGH #4 — still CLOSED.** `TARGET_OBS_BANNED_COLUMNS` includes
  `sibababacd`/`dirtbabacd`; `HISTORY_ALLOWED_POST_RACE_COLUMNS` includes `babacd`; the
  disjointness startup assert is intact; the 3 tests
  (`test_target_obs_banned_columns_not_in_registry_features`,
  `test_history_allowed_babacd_rolling_present`, `test_banned_columns_not_selected`)
  remain.
- **HIGH #6 — still CLOSED.** SHA256 computed from `buf.getvalue().to_pybytes()` only;
  manifest has `created_at_real` + `byte_reproducible_scope: "parquet_bytes_only"`; tests
  `test_sha256_covers_parquet_bytes_only` and `test_manifest_created_at_varies_between_runs`.
- **8-system / 40-entry reconciliation — consistent.** Both `_ROLLING_SYSTEMS_FOR_RESERVED`
  (03-01) and `_ROLLING_SYSTEMS` (03-03) list the same 8 systems (`kakuteijyuni`,
  `timediff`, `harontimel3`, `jyuni3c_jyuni4c`, `kyori`, `babacd`, `jyocd`,
  `days_since_prev`). Count is internally consistent: 15 static + 8×3 rolling (24) + 1
  running-style = 40 registry feature entries. The 8 `rolling_<system>_count_5` audit
  columns are reserved non-feature columns, correctly excluded from the 40.

### New Concerns (this cycle — none HIGH)

- **MEDIUM — expanded-history dedup guard.** The expanded-history fan-out (HIGH #1 fix)
  should explicitly deduplicate `observations` by `(race_nkey, kettonum)` and `history`
  by its past-race natural key before aggregation. The builder has a canonical-key
  uniqueness assert, but `rolling.py` itself does not state a `drop_duplicates` guard.
  Duplicate history rows would inflate rolling aggregates — a reproducibility/data-quality
  risk, not a direct leakage HIGH. Non-blocking; suggested as an implementation-time hardening.
- **MEDIUM — previous-day feature-value drop.** Strict `< feature_cutoff_datetime` with
  cutoff at previous-day midnight intentionally drops races whose `as_of_datetime` falls
  on the previous calendar date. This is leak-safe, but it discards legitimately
  available previous-day results that the (now-abolished) `+ 1 day` form would have
  included. This is a feature-value regression risk, not a leakage blocker; the plan
  knowingly chose this invariant for unambiguous leak-safety, which is the correct call
  given the project's core value.
- **LOW — `_code` auto-whitelist governance.** Safe today because `_CATEGORY_COLUMNS` is a
  fixed 5-tuple, but future additions to `_CATEGORY_COLUMNS` would automatically bypass
  the registry for `<col>_code`. Keep the exact-5-element test asserting
  `_CATEGORY_COLUMNS == ("jockey_id","trainer_id","sire_id","bms_id","horse_id")`.
- **LOW — tuple-valued `obs_id`.** A tuple-valued column is hashable and works in pandas
  `groupby`, but an encoded string key (e.g. `f"{race_nkey}:{kettonum}"`) may be easier to
  inspect/debug in Parquet snapshots. Not a blocker.

### Action Items for Planner

None required for HIGH. Suggested non-blocking hardening (may be deferred to execution):
add an explicit `drop_duplicates` / uniqueness assertion on the expanded-history inputs
in `rolling.py` (addresses the MEDIUM dedup concern).

### Overall Verdict (Cycle 3)

**APPROVE.** All 6 cycle-1 HIGHs are now genuinely closed with mechanical mechanisms and
adversarial tests. No regressions. No NEW HIGH. The convergence loop has converged.

### CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

---

*Review methodology: Codex (OpenAI, gpt-5.5) invoked via
`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check` on the
full revised plan set (HEAD cabfa9d) + project context + requirements. Cycle-3 prompt
required an explicit CLOSED / PARTIALLY RESOLVED / STILL OPEN verdict per prior HIGH,
with the exact mechanism + test + adversarial-input reasoning justifying each verdict,
plus a regression check on the closed HIGH #3/#4/#6 and the 8-system/40-entry
reconciliation, plus a scan for NEW leakage concerns introduced by the cycle-2
revisions. The orchestrator independently verified the HIGH #1 fan-out-order claim
(cutoff applied after expanded-history join, step 1b before step 2) and the
two-observation boundary-row presence (`obs_B_only_pre`, as_of="2023-06-05") against the
current plan source before recording APPROVE.*
