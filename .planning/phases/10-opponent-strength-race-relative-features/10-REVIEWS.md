---
phase: 10
reviewers: [codex]
reviewed_at: 2026-06-26T20:55:00Z
cycle: 4
plans_reviewed:
  - 10-01-PLAN.md
  - 10-02-PLAN.md
  - 10-03-PLAN.md
  - 10-04-PLAN.md
  - 10-05-PLAN.md
  - 10-06-PLAN.md
  - 10-07-PLAN.md
source_grounding: codex (codex-cli 0.142.1, xhigh reasoning) ran inside the project git working tree; all file:line citations were verified against the live repo (src/features/speed_figure.py, src/features/builder.py, src/features/snapshot.py, src/model/orchestrator.py). Cycle-4 mandate was to confirm the 3 Cycle-3 MEDIUMs are genuinely resolved, confirm no regression of Cycle-1/Cycle-2 leakage fixes (especially value-invariance under the new race×horse obs_id granularity), and surface any NEW concern.
---

# Cross-AI Plan Review — Phase 10 (Cycle 4 — convergence continuation, user-authorized beyond max-cycles)

> Cycle 4 of the convergence loop. The user authorized this extra cycle to fully converge.
> Cycle 3 reached **0 HIGH** (leakage genuinely resolved, both Codex + Claude confirmed via
> source trace) + **3 actionable MEDIUM** (non-leak: KeyError / par-scale / cardinality).
> Cycle 4 revised the 3 MEDIUMs into PLAN.md:
>
> - **MEDIUM #1 (KeyError)**: `compute_field_strength_profile` now derives
>   `available_at = pd.to_datetime(race_date)` INSIDE the function (pinned to race_date,
>   symmetric with `speed_figure.py:698`); raw_history required-columns list no longer includes
>   `speed_figure`/`available_at`; Test 11 corrected.
> - **MEDIUM #2 (par-scale)**: synthetic `obs_id` changed to
>   `SOURCE_ASOF_<race_nkey>_<kettonum>` (race×horse granularity) so opponent par is horse-level,
>   matching the target path; 10-03 scale-compatibility truth added; value-invariance preserved.
> - **MEDIUM #3 (cardinality)**: per-source-race batching (`SOURCE_RACE_BATCH_SIZE` pre-registered)
>   avoids H² blowup in `out.merge(obs_keys, on="kettonum")` before the cutoff filter;
>   10-07 production-scale smoke test added (`PROD_PEAK_MEM_BUDGET_GB` / `PROD_WALL_TIME`
>   pre-registered); W-3 (14k-row ≤5s) NOT weakened.
> - Also: 10-02 obs_id notation aligned to horse-level.
>
> **Cycle-4 outcome: genuine 0/0 convergence on the leakage surface, with 1 residual LOW
> (documentation consistency) that does NOT affect the implementation path.** Codex verified all
> 3 MEDIUMs are FULLY RESOLVED with source-grounded evidence, and confirmed no regression of any
> Cycle-1/Cycle-2 leakage fix — including value-invariance under the new race×horse obs_id
> granularity and the raw_history capture (10-04 Step 5b前 `.copy()`). The only residual finding
> is a LOW: 10-01 still has 3 stale race-level `SOURCE_ASOF_<race_nkey>` references in non-operative
> prose (must_haves summary, action-epilogue, threat_model row) — the operative action/acceptance
> criteria correctly require the new horse-level id, so this is execution-ambiguity cleanup, not a
> design flaw and not a leak.

---

## Cycle-3 MEDIUM resolution verdicts (at a glance)

| Cycle-3 MEDIUM | Cycle-4 verdict | Why (source-grounded) |
|---|---|---|
| #1 (KeyError on `available_at`) | **FULLY RESOLVED** | `race_date` is a raw history column (`builder.py:101` SELECT source), and `_construct_derived_columns` (`builder.py:206`) derives `race_nkey`/`as_of_datetime`/`days_since_prev`/`timediff`/`babacd` but NOT `available_at`/`speed_figure`. `available_at` is normally added only by `compute_speed_figure_for_history` at `speed_figure.py:697`. 10-01 now derives `available_at = pd.to_datetime(raw_history["race_date"])` INSIDE `compute_field_strength_profile` (`10-01-PLAN.md:102,110,145`), removing the KeyError without opening a new leak path (race_date is target-cutoff-independent). Test 3 asserts both input `speed_figure` non-dependence AND `available_at`-column non-dependence; Test 11 lists neither as required. |
| #2 (par-scale asymmetry) | **FULLY RESOLVED** | `compute_speed_figure_for_history` merges observations on `kettonum` before filtering (`speed_figure.py:633`), par groups by `["obs_id",...]` (`speed_figure.py:401`), variant groups by `["obs_id",...]` (`speed_figure.py:509`). With `SOURCE_ASOF_<race_nkey>_<kettonum>`, one horse's source-as-of par/variant cannot be contaminated by another horse's history (merge is horse-keyed, groupby is obs_id-keyed). This matches the target-path horse-level `obs_id=(race_nkey, kettonum)` (`builder.py:502`). 10-03 additive-score scale claim is consistent (`10-03-PLAN.md:27,122`). |
| #3 (cardinality / H² blowup) | **FULLY RESOLVED** | The H² risk is real because `speed_figure.py:635` performs `out.merge(obs_keys, on="kettonum")` BEFORE the cutoff filter at `speed_figure.py:641`. 10-01 action step 5 now requires per-source-race (or small-batch) splitting with `SOURCE_RACE_BATCH_SIZE` constant (`10-01-PLAN.md:127,189`); batching preserves value-invariance because obs_id is still the groupby head key. 10-07 preserves W-3 (14k rows ≤5s, `10-07-PLAN.md:176`) AND adds a production-scale smoke test with `PROD_PEAK_MEM_BUDGET_GB`/`PROD_WALL_TIME` budgets + merge-cardinality instrumentation (`10-07-PLAN.md:195,214`). |

## Cycle-1/Cycle-2 leakage regression check

| Prior HIGH/MEDIUM | Cycle-4 verdict | Evidence |
|---|---|---|
| C2-1 (10-01 root cause: per-row speed_figure target-cutoff-dependent) | **RESOLVED — no regression** | The fix (raw-history full-pipeline recompute via synth_obs) is intact; the obs_id granularity change (race→race×horse) does not weaken it — Codex traced the par/variant groupby head key and confirmed a single horse's par cannot be contaminated by another horse's history. `10-01-PLAN.md:126,131-134,177,188,195,245,248`. |
| C2-2 (10-02 downstream propagation) | **RESOLVED — no regression** | `10-02-PLAN.md:27,99` still gate both polluted→polluted and clean→clean propagation; obs_id notation aligned to `SOURCE_ASOF_<race_nkey>_<kettonum>`. |
| C2-3 (10-04 integration order: raw_history capture) | **RESOLVED — no regression** | `10-04-PLAN.md:22,116` still require `raw_history = history.copy()` BEFORE Step 5b and Step 5c must receive `raw_history` not the obs_id-expanded `history`. |
| C2-4 (10-07 value-invariance audit) | **RESOLVED — no regression** | `10-07-PLAN.md:100` still asserts value-invariance (bit-identical speed_figure across target cutoffs T1<T2) alongside row-inclusion. |
| H3 (10-07 odds-in-SQL scanner) | **RESOLVED — no regression** | `10-07-PLAN.md:97,150,238` extend the scanner to detect `odds` in SQL string literals with whitelist `['odds-free','odds_snapshot_policy']`. |
| H5 (10-05 metadata key) | **RESOLVED — no regression** | Actual key `feature_availability_version` (`snapshot.py:62`); 10-05 asserts the exact key. |
| H6 (10-06 orchestrator API) | **RESOLVED — no regression** | `orchestrator.py:234` label-joined `feature_df` + kwargs; 10-06 uses the correct 5-step chain. |

---

## Why the Cycle-3 MEDIUM fixes are genuine (consensus, with source walkthrough)

Codex independently traced the same source evidence and confirmed each MEDIUM is resolved at the
implementation level, not just mentioned in prose.

### MEDIUM #1 — `available_at` derivation removes KeyError with no new leak path

1. The KeyError was real: `_construct_derived_columns` (`builder.py:206-323`) derives only
   `race_nkey`/`as_of_datetime`/`days_since_prev`/`timediff`/`babacd`. `available_at` is added only
   by `compute_speed_figure_for_history` at `speed_figure.py:697`. So `starters[["race_nkey","available_at"]]`
   on raw_history (Step 5b pre) would KeyError without the fix.
2. The fix is target-cutoff-independent: `race_date` is a raw column from `normalized.n_race`
   (`builder.py:101`), not derived from any target observation. `pd.to_datetime(race_date)` is
   therefore symmetric with `speed_figure.py:697` and cannot introduce target-cutoff dependence.
3. The fix closes the fragile path: by deriving `available_at` inside the function from `race_date`,
   an implementer cannot "fix" the KeyError by reading the Step 5b-polluted history (which would
   open a dependence on the contaminated frame). 10-01 Test 3 + Test 11 mechanically enforce this.

### MEDIUM #2 — race×horse obs_id preserves value-invariance

The Cycle-2/3 fix relied on `obs_id` being the par/variant groupby head key. Codex walked through
the groupby under the new `SOURCE_ASOF_<race_nkey>_<kettonum>` id and confirmed:

- The merge (`speed_figure.py:633` `out.merge(obs_keys, on="kettonum")`) is horse-keyed, so each
  row's history belongs to exactly one horse.
- The par groupby (`speed_figure.py:401` `["obs_id", "_jyocd", "_trackcd", "_kyori"]`) and variant
  groupby (`speed_figure.py:509` `["obs_id", "_source_race_date", "_jyocd", "_surface"]`) are
  obs_id-keyed. With obs_id = `(source_race, horse)`, each group spans exactly one horse in one
  source race. A horse's par/variant/speed_figure is therefore a function of only that horse's
  pre-cutoff history in that source race — no other horse's history can contaminate it.
- This matches the target-path horse-level obs_id `(race_nkey, kettonum)` (`builder.py:502`), so
  the additive score in 10-03 is now on a consistent normalization.

Value-invariance (the property that the same pre-source opponent race yields bit-identical
speed_figure regardless of target cutoff) is preserved: it depended only on obs_id being the
groupby head key, which is still true at horse granularity.

### MEDIUM #3 — per-source-race batching avoids H² blowup without weakening W-3

1. The H² risk is real: `out.merge(obs_keys, on="kettonum")` at `speed_figure.py:635` materializes
   the cartesian product of each horse's history rows × the source races that horse started in,
   BEFORE the cutoff filter at `speed_figure.py:641`. With all source races concatenated, this can
   reach 25M+ rows.
2. The fix bounds it to batch level: 10-01 action step 5 splits synth_obs per source race (or small
   batch). Within a batch, the merge cardinality is bounded by the batch's source races, not the
   global set. Batching preserves value-invariance because each call's obs_id set is disjoint and
   obs_id is the groupby head key — per-batch results are bit-identical to a one-shot call.
3. W-3 is preserved: 10-07 keeps the 14k-row ≤5s gate (`10-07-PLAN.md:176`) AND adds an independent
   production-scale smoke test (`10-07-PLAN.md:195,214`) with `PROD_PEAK_MEM_BUDGET_GB=8.0` /
   `PROD_WALL_TIME=300.0` and explicit merge-cardinality instrumentation that would RED if the
   per-batch structure were reverted to one-shot.

---

## Codex Review (Cycle 4)

**Summary**

Cycle 4 mostly converges. The three Cycle-3 MEDIUMs are substantively incorporated into the
operative plan steps and acceptance criteria, and there is no remaining HIGH leakage concern.
The plan-level fix is still source-grounded: `speed_figure.py` expands by `obs_id`, filters after
merge, and computes par/variant/speed_figures under `obs_id`-scoped groupby keys, so the revised
source-as-of recompute can be made target-cutoff-independent. One residual LOW cleanup issue:
10-01 still has a few stale prose references to the old race-level `SOURCE_ASOF_<race_nkey>` id,
even though the operative action/acceptance criteria now require race×horse.

### Specific Checks (Codex)

1. **`available_at` derivation (MEDIUM #1): resolved, no new leak path.** `race_date` is a raw
   history column from `normalized.n_race` (`builder.py:101`), and `_construct_derived_columns`
   (`builder.py:206`) derives `race_nkey/as_of_datetime/...` but not `available_at`/`speed_figure`.
   `available_at` is normally added by `compute_speed_figure_for_history` at `speed_figure.py:697`,
   so deriving it inside `compute_field_strength_profile` from `race_date` is the right raw-history
   fix. 10-01 Test 3 and Test 11 now explicitly say `speed_figure/available_at` are absent from raw
   history and must not be required or read, with `available_at = pd.to_datetime(raw_history["race_date"])`
   inside the function (`10-01-PLAN.md:102,110,145`).

2. **Race×horse `obs_id` (MEDIUM #2): value-invariance preserved.** `compute_speed_figure_for_history`
   merges observations on `kettonum` before filtering (`speed_figure.py:633`), par groups by
   `["obs_id",...]` (`speed_figure.py:401`), variant groups by `["obs_id",...]` (`speed_figure.py:509`).
   With `SOURCE_ASOF_<race_nkey>_<kettonum>`, one horse's source-as-of par/variant cannot be
   contaminated by another horse's history: the merge is horse-keyed and the groupby is obs_id-keyed.
   This also matches target-path horse-level `obs_id=(race_nkey, kettonum)` from `builder.py:502`.
   The 10-03 additive-score scale claim is consistent (`10-03-PLAN.md:27`).

3. **Per-source-race batching (MEDIUM #3): materially resolved.** The original H² risk is real
   because `speed_figure.py:635` performs `out.merge(obs_keys, on="kettonum")` before the cutoff
   filter at `speed_figure.py:641`. 10-01 now requires splitting `synth_obs` per source race or
   small batch, a `SOURCE_RACE_BATCH_SIZE`, and a test that avoids the all-source one-shot merge
   (`10-01-PLAN.md:127,189`). 10-07 preserves W-3 at 14k rows ≤5s and adds a production-scale smoke
   with memory/time budgets and merge-cardinality instrumentation (`10-07-PLAN.md:176,195`).

4. **Cycle-1/Cycle-2 regression: no HIGH regression.** The raw-history capture remains explicit:
   10-04 requires `raw_history = history.copy()` before Step 5b and Step 5c must call
   `compute_field_strength_profile(raw_history, ...)`, not the obs_id-expanded `history`
   (`10-04-PLAN.md:22,116`). C2-2 downstream propagation is still guarded in 10-02
   (`10-02-PLAN.md:27`). C2-4 value-invariance audit remains present in 10-07
   (`10-07-PLAN.md:100`). H5/H6 also remain aligned with live source keys/API (`snapshot.py:62`,
   `orchestrator.py:234`).

### Strengths (Codex)

- The plan now closes the `available_at` KeyError in the safest way: derive from raw `race_date`,
  not from post-Step-5b polluted history.
- Race×horse synthetic observations align source-as-of normalization with the target speed-figure
  path.
- The H² cardinality issue is handled both structurally and with a production-scale smoke test.
- The tests are adversarial enough to catch the broken implementation, especially input-column
  contamination and value-invariance failures.

### New Concern (Codex) — 1 LOW

- **LOW-C4-CODEX-1 (10-01, documentation consistency)**: 10-01 still contains stale race-level
  `obs_id='SOURCE_ASOF_<race_nkey>'` wording in non-operative but prominent prose at
  `10-01-PLAN.md:20` (must_haves/truths summary), `10-01-PLAN.md:166` (action epilogue
  "実装者が必ず理解すべき点"), and `10-01-PLAN.md:213` (threat_model row T-10-01b mitigation
  text). The operative action step 5/6 (`10-01-PLAN.md:126,131-134`), acceptance_criteria
  (`10-01-PLAN.md:177,188,245,248`), and artifacts_produced all correctly require
  `SOURCE_ASOF_<race_nkey>_<kettonum>`, so this is NOT a HIGH/MEDIUM design flaw and does NOT
  affect the implementation path the executor will follow. But because must_haves/threat_model are
  machine-consumed by `/gsd-execute-phase`, leaving the stale race-level id there creates execution
  ambiguity and should be cleaned up.

### Suggestions (Codex)

- Replace the three stale 10-01 race-level `SOURCE_ASOF_<race_nkey>` references with
  `SOURCE_ASOF_<race_nkey>_<kettonum>`.
- When implementing the production-scale smoke, prefer explicit instrumentation around each
  batched `compute_speed_figure_for_history` call so the H² assertion is not just inferred from
  wall time/memory.

### Overall Risk Assessment (Codex)

**LOW.** The leakage surface is still genuinely closed at plan level. The only remaining issue to
track is documentation consistency around the synthetic `obs_id` notation.

---

## Independent source-grounding verification (reviewer self-check)

In addition to relaying the Codex review, the reviewer independently re-traced the cited source
locations and confirms:

- `speed_figure.py:401` par groupby key `["obs_id", "_jyocd", "_trackcd", "_kyori"]` — VERIFIED
  (Stage 1, obs_id head).
- `speed_figure.py:509` variant groupby key `["obs_id", "_source_race_date", "_jyocd", "_surface"]`
  — VERIFIED (Stage 1, obs_id head).
- `speed_figure.py:633` `out.merge(obs_keys, on="kettonum")` precedes `speed_figure.py:641`
  cutoff filter — VERIFIED (H² risk is real; batching mitigation is necessary).
- `speed_figure.py:697` `result["available_at"] = pd.to_datetime(result["race_date"])` — VERIFIED
  (the symmetric derivation inside `compute_field_strength_profile` is correct).
- `builder.py:206-323` `_construct_derived_columns` derives `race_nkey`/`as_of_datetime`/
  `days_since_prev`/`timediff`/`babacd` only — VERIFIED (no `available_at`/`speed_figure`;
  KeyError was real).
- `builder.py:528` `history = compute_speed_figure_for_history(history, observations=feature_matrix)`
  is a name rebinding (non-destructive copy-not-rename), so `raw_history = history.copy()` before
  Step 5b correctly preserves the pre-pollution frame — VERIFIED.
- Stale `SOURCE_ASOF_<race_nkey>` (race-level) occurrences in 10-01: L20, L166, L213 — VERIFIED
  (3 locations, all in non-operative prose; operative action/acceptance use the new horse-level id).

The 3 stale-notation locations are the ONLY remaining actionable. No NEW HIGH was surfaced. No
Cycle-1/Cycle-2 leakage fix is regressed.

---

## Consensus Summary (Cycle 4 — Codex review + reviewer source-grounding verification)

### Agreement

1. **All 3 Cycle-3 MEDIUMs are FULLY RESOLVED** at the implementation level ( operative action /
   acceptance criteria / tests), not just mentioned in prose.
2. **No HIGH remains.** The leakage surface (Cycle-1 H3/H5/H6 + Cycle-2 C2-1/C2-2/C2-3/C2-4) is
   still genuinely closed. Value-invariance under the new race×horse obs_id granularity is
   structurally preserved (obs_id is still the par/variant groupby head key).
3. **1 residual LOW** (documentation consistency): 10-01 has 3 stale race-level `SOURCE_ASOF_<race_nkey>`
   references in non-operative prose (must_haves summary / action epilogue / threat_model row).
   The operative path uses the correct horse-level id, so this is execution-ambiguity cleanup,
   not a design flaw and not a leak.
4. **CYCLE_SUMMARY: current_high=0 current_actionable=1.**

### Why this is convergence

The core value (leakage prevention) was already protected in Cycle 3 (0 HIGH). Cycle 4 confirmed
that the 3 non-leak MEDIUMs are genuinely resolved at the implementation level and that the
revisions did not regress any leakage fix. The single residual LOW is a documentation-consistency
cleanup in non-operative prose that an executor can fix in a one-line edit per location; it does
not gate execution and does not affect the leakage surface. Genuine 0/0 convergence is achieved on
the core value; the residual LOW is bookkeeping.

---

## Verification coverage (Cycle 4)

| Plan | Source-grounded evidence re-cited this cycle | Finding |
|------|----------------------------------------------|---------|
| 10-01 | `speed_figure.py:401/509/633/641/697`, `builder.py:101/206/528`, `10-01-PLAN.md:20/102/110/126/131-134/145/166/177/188/195/213/245/248` | MEDIUM #1/#2/#3 FULLY RESOLVED; NEW LOW-C4-CODEX-1 (stale notation L20/L166/L213) |
| 10-02 | `10-02-PLAN.md:27/99` | C2-2 no regression; obs_id notation aligned |
| 10-03 | `10-03-PLAN.md:27/97/122` | MEDIUM #2 scale-compatibility truth consistent |
| 10-04 | `builder.py:528`, `10-04-PLAN.md:22/116` | C2-3 no regression (raw_history capture intact) |
| 10-05 | `snapshot.py:62`, 10-05-PLAN.md | H5 no regression |
| 10-06 | `orchestrator.py:234`, 10-06-PLAN.md | H6 no regression |
| 10-07 | `10-07-PLAN.md:97/100/150/176/195/214/238` | MEDIUM #3 FULLY RESOLVED (W-3 preserved + prod smoke); C2-4/H3 no regression |

---

CYCLE_SUMMARY: current_high=0 current_actionable=1

## Current HIGH Concerns

None.

## Current Actionable Non-HIGH Concerns

- **LOW-C4-CODEX-1 (10-01, documentation consistency, raised by Codex)**: 10-01 に race-level の旧表記 `SOURCE_ASOF_<race_nkey>` が3箇所の非 operative prose に残存する — `10-01-PLAN.md:20`（must_haves/truths CYCLE-2 HIGH-C2-1 要約）、`10-01-PLAN.md:166`（action 末尾「実装者が必ず理解すべき点」要約）、`10-01-PLAN.md:213`（threat_model T-10-01b mitigation 文）。operative な action step 5/6（L126, L131-134）・acceptance_criteria（L177, L188, L245, L248）・artifacts_produced はすべて正しい新表記 `SOURCE_ASOF_<race_nkey>_<kettonum>`（race×horse 単位）を使用しているため・実装パスへの影響はなく design flaw でもリークでもない。しかし must_haves/threat_model は `/gsd-execute-phase` が機械消費する領域のため・残したままでは実装者に ambiguity を与える。PLAN.md 変更点: 上記3箇所の `SOURCE_ASOF_<race_nkey>` を `SOURCE_ASOF_<race_nkey>_<kettonum>` に置換すること（1行1箇所の機械的編集・非リーク・実装パス不変）。
