---
phase: 3
reviewers: [codex]
reviewed_at: 2026-06-18T14:38:32Z
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
---

# Cross-AI Plan Review — Phase 3

> Phase 3 is the leakage-prevention backbone of Keiba AI v3: point-in-time-correct
> feature generation (FEAT-01) and immutable reproducible Parquet snapshots (FEAT-02).
> Reviewers were asked to be rigorous about leakage vectors, since reproducibility
> and leakage prevention are the project's non-negotiable core value.

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

### Concerns

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

- **MEDIUM — `03-02-PLAN.md` staging-swap for a one-column backfill is high blast radius.**
  Dropping and renaming `label.fukusho_label` can lose grants, comments, indexes,
  privileges, dependencies, or table OIDs if not perfectly replicated. It is
  defensible for idempotency, but for a leakage-critical prerequisite, a narrower
  transactional `UPDATE ... FROM normalized.n_race` plus rowcount/checksum may be
  safer unless prior project convention strongly requires staging-swap.

- **MEDIUM — `03-02-PLAN.md` is marked `depends_on: []`, but `03-03-PLAN.md` should depend on both `03-01` and `03-02`.**
  The Wave 2 plan lists only `depends_on: ['03-01']`. Since feature cutoff depends
  on non-null label race_date, `03-03-PLAN.md` should explicitly depend on `03-02`.

- **MEDIUM — Tests rely too much on `inspect.getsource`.**
  Source inspection for `SELECT *`, banned words, and `.sort_values()` is useful as
  a guard, but it does not prove behavior. The leakage-critical tests should
  include adversarial synthetic rows where the only possible wrong answer comes from
  future/same-day/target-race data.

- **MEDIUM — Rolling features with `__MISSING__` string sentinels in numeric columns may create mixed dtypes.**
  This can harm PyArrow schema stability and later model ingestion. Prefer separate
  missing indicators plus numeric nulls, or a typed sentinel strategy that is
  compatible with LightGBM/CatBoost and deterministic Parquet schemas.

- **MEDIUM — `03-04-PLAN.md` row group size likely misunderstands PyArrow units.**
  `row_group_size` is number of rows, not bytes. `128 * 1024 * 1024` means 134M rows
  per group, not 128 MiB. This affects memory/performance and should be corrected.

- **MEDIUM — `03-04-PLAN.md` deterministic PyArrow writes may still vary if schema inference varies.**
  `pa.Schema.from_pandas` can be sensitive to pandas dtypes, mixed object columns,
  column order, timezone handling, and null representation. The plan should require
  an explicit fixed schema and column order.

- **LOW — "25 features" vs "43 entries" is confusing.**
  The plan alternates between 25 feature candidates and 43 registry entries. This
  is understandable due to rolling axes, but acceptance criteria should name "43
  feature columns/entries" consistently.

- **LOW — Warm-up exclusion is not fully enforced.**
  Context says 2015-2016H1 is warm-up and learning/evaluation starts 2016H2. Plans
  mention train starts 2016-07-01, but the builder/snapshot should explicitly include
  warm-up rows only as history and exclude pre-2016H2 observations from model-ready
  rows unless intentionally retained as audit rows.

### Suggestions

- In `03-03-PLAN.md`, specify the rolling algorithm exactly:
  - For each `(race_nkey, kettonum)` observation, filter `history.kettonum == observation.kettonum`.
  - Require `history.as_of_datetime < observation.feature_cutoff_datetime`.
  - Sort descending by `as_of_datetime`.
  - Take head 5.
  - Aggregate mean/latest/sd/count.
  - Unit-test with target race, same-day prior race, same-day later race, previous-day race, and future race.

- Add a matrix-level allowlist test in `03-01-PLAN.md` / `03-03-PLAN.md`:
  - Every model feature column must appear in `feature_availability.yaml`.
  - Every registry feature must have a known timing.
  - No unregistered model-input columns are allowed.
  - Key/audit columns must be separately classified.

- Split banned columns by context:
  - Target observation banned: odds, popularity, body weight announced, race-day weather/going, same-day aggregates, post-race fields.
  - Historical source allowed only through rolling: previous `timediff`, previous `harontimel3`, previous passing order, previous going.
  - Enforce this with separate `_OBS_BANNED_COLUMNS` and `_HISTORY_ALLOWED_POST_RACE_SOURCE_COLUMNS`.

- Make `03-03-PLAN.md` depend on `03-02` explicitly.

- Replace source-inspection-only tests with behavioral adversarial tests:
  - Future row with absurd `timediff=-99` must not affect feature.
  - Same-day row with absurd value must not affect feature.
  - Target row with absurd value must not affect feature.
  - Unknown category appearing only in validation must map to `__UNSEEN__`.

- In `03-04-PLAN.md`, require:
  - Fixed column order.
  - Explicit Arrow schema.
  - Stable timestamp passed as parameter for Parquet metadata.
  - SHA256 over final Parquet bytes only.
  - Manifest records the Parquet SHA256 and may have non-deterministic run metadata.

- Correct `row_group_size`: choose a row count, e.g. `row_group_size=100_000` or similar, rather than `128 * 1024 * 1024`.

- Decide whether raw categorical ID columns remain in the Parquet. If they remain, add metadata like `role: key_only` / `role: audit_only` and enforce Phase 4 model-input selection from encoded columns only.

- Add warm-up assertions:
  - History may include 2015-2016H1.
  - Model-ready observation rows start at `2016-07-01`.
  - No train/val/test split includes warm-up target rows unless explicitly marked.

### Risk Assessment

**Overall risk: HIGH.**

The phase plan is strong in intent and covers the four success criteria, but this
is the project's leakage-prevention backbone, and the current plans still leave
dangerous implementation ambiguity around rolling PIT joins, actual matrix-column
allowlisting, historical-vs-target banned column semantics, and deterministic
schema writing. These are fixable before implementation, but if implemented as
written, a superficially GREEN test suite could still allow future data leakage or
non-reproducible snapshots. The risk should be treated as HIGH until the behavioral
adversarial tests and stricter snapshot/schema contracts are added.

---

## Consensus Summary

> Only one external reviewer (Codex) was invoked in this cycle, so the consensus
> below reflects Codex's findings. Gemini/other CLIs were unavailable (`gemini`
> binary not installed; `--codex` was the only requested reviewer). To strengthen
> consensus, re-run `/gsd-review --phase 3 --gemini` once the Gemini CLI is
> installed.

### Agreed Strengths

(single reviewer — these are Codex's stated strengths)

- Wave/dependency ordering is sound: registry → race_date backfill → feature builder → snapshot writer.
- The Phase 1-A allowlist is treated as a structural gate (not just a convention).
- Deterministic Parquet writes, SHA256 verification, and train-window-only frozen category maps are all explicitly called out in `03-04-PLAN.md`.
- Cold-start / missingness sentinels (`__MISSING__`, `__UNSEEN__`) are recognized.

### Agreed Concerns

The 6 HIGH concerns below are the highest-priority items to address before
implementation. They cluster into two themes:

1. **PIT join correctness is under-specified.** The single biggest risk is that
   `pit_join_backward` (one backward as-of join) cannot by itself retrieve a
   "latest 5" rolling window — the rolling algorithm must be stated explicitly
   with strict `< cutoff` filtering per observation (HIGH #1), and the cutoff
   semantics (midnight vs end-of-day; `<` vs `<=`) must be pinned (HIGH #2).

2. **The allowlist test can pass while banned columns enter.** Two related gaps:
   the test checks feature *timings* but not that every *output matrix column* is
   registered (HIGH #3), and there is no distinction between "banned for the target
   observation SELECT" vs "allowed as a historical rolling source" — so a past-race
   `babacd`/going feature could be wrongly rejected or wrongly allowed (HIGH #4).

3. **Snapshot/category-map edge cases.** Raw ID columns lingering alongside `_code`
   columns could let Phase 4 accidentally train on or refit raw IDs (HIGH #5), and
   the byte-reproducibility contract must explicitly exclude the manifest's
   run-time `created_at` from the SHA256 scope (HIGH #6).

### Divergent Views

(Single reviewer — no cross-reviewer divergence this cycle. Re-running with a
second reviewer would surface any disagreement.)

---

## Action Items for Planner (`/gsd-plan-phase 3 --reviews`)

Feed this REVIEWS.md back into planning. Priority order:

1. **[HIGH]** Pin the exact rolling PIT algorithm in `03-03-PLAN.md` (per-observation strict `< cutoff`, latest-5, with the 5 adversarial test rows: target / same-day-prior / same-day-later / previous-day / future).
2. **[HIGH]** Define `feature_cutoff_datetime` semantics explicitly (timezone, midnight vs end-of-day, `<` vs `<=`) and make it a documented invariant in metadata.
3. **[HIGH]** Strengthen the allowlist test to validate *actual matrix output columns* against the registry and reject unregistered columns (matrix-level, not just timing-level).
4. **[HIGH]** Split banned columns into `_OBS_BANNED` (target SELECT) vs `_HISTORY_ALLOWED_POST_RACE_SOURCE` (rolling history) so past-race going/`babacd`/`timediff` are correctly permitted as historical features.
5. **[HIGH]** Decide raw ID column disposition in the snapshot: drop after coding, or tag `role: key_only`/`audit_only` and enforce Phase 4 model-input selection from `_code` columns.
6. **[HIGH]** Clarify the SHA256 scope: Parquet bytes are byte-reproducible; the manifest records run-time `created_at` and is intentionally NOT byte-reproducible.
7. **[MEDIUM]** Reconsider the staging-swap in `03-02-PLAN.md` for a one-column backfill (consider transactional `UPDATE ... FROM n_race`).
8. **[MEDIUM]** Add `03-02` as an explicit dependency of `03-03-PLAN.md`.
9. **[MEDIUM]** Add behavioral adversarial tests alongside (not instead of) the `inspect.getsource` source guards.
10. **[MEDIUM]** Fix `row_group_size` units (rows, not bytes) and require an explicit fixed Arrow schema + column order in `03-04-PLAN.md`.
