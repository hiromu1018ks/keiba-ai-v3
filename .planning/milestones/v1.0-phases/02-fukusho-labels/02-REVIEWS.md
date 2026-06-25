---
phase: 2
reviewers: [codex]
reviewed_at: 2026-06-18T11:55:00Z
cycle: 3
prior_cycle_commit: 99fd1a6
plans_reviewed:
  - 02-01-PLAN.md
  - 02-02-PLAN.md
  - 02-03-PLAN.md
  - 02-04-PLAN.md
---

# Cross-AI Plan Review — Phase 2: Fukusho Labels (Cycle 3 — FINAL re-review of cycle-2 revised plans)

> **Reviewer selection:** `--codex` requested. Claude CLI skipped (review running inside Claude Code → `SELF_CLI=claude`). Gemini / Qwen / Cursor / Antigravity CLIs not installed. Single external reviewer: **Codex**.
>
> **This is cycle 3, the FINAL cycle of the plan-convergence loop.**
> - Cycle 1 raised 7 HIGHs on the original plans.
> - Cycle 1 replan (`8800fdc`) resolved all 7.
> - Cycle 2 confirmed 7/7 cycle-1 HIGHs FULLY RESOLVED and raised **3 NEW HIGHs** (NULL-safe padded `umaban` payout SQL; `timediff` merge row-multiplication; missing-time misclassification).
> - Cycle 2 replan (`99fd1a6`) claims to resolve all 3 NEW HIGHs and added regression tests (Plan 02: 25→27 tests; Plan 04: 17→18 tests).
>
> **Convergence result (cycle 3):** All 3 cycle-2 NEW HIGHs are **FULLY RESOLVED** by the cycle-2 revised plans. No cycle-1/cycle-2 resolution regressed. No genuinely NEW HIGH concern was introduced on the leakage-critical label surface.
>
> **CYCLE_SUMMARY: current_high=0 → CONVERGE.**

---

## Codex Review (Cycle 3)

### Per-HIGH Verdicts — the 3 cycle-2 NEW HIGHs

**Cycle-2 NEW HIGH #1 — Plan 04 payout precision/recall SQL unsafe (`NOT IN` with NULLs + unpadded `umaban`): FULLY RESOLVED**

Evidence (from the cycle-2 revised plan text):
- Plan 04 objective explicitly requires replacing `NOT IN (NULLIF(...))` with a NULL-safe set comparison and zero-padding both sides:
  - "`NOT IN (NULLIF)` ではなく `NOT EXISTS` / `EXCEPT` / `IS DISTINCT FROM`"
  - "両側 `LPAD(...::text, 2, '0')` で zero-pad"
- Plan 04 Task 1 gives concrete SQL for `_check_payout_precision`:
  - `AND NOT EXISTS (SELECT 1 FROM (VALUES (LPAD(NULLIF(hr.payfukusyounmaban1,'00')::text, 2, '0')), ...) AS t(umaban_padded) WHERE t.umaban_padded IS NOT NULL AND t.umaban_padded = LPAD(l.umaban::text, 2, '0'))`
  - This closes BOTH defects: `NOT EXISTS` is immune to three-valued-logic UNKNOWN (NULL payout slots are filtered by `IS NOT NULL` and simply never match → correct FALSE rather than silent UNKNOWN); and both sides are LPAD'd to 2 chars so int `1` and varchar `'01'` compare equal.
- `_check_payout_recall` uses the inverse `EXISTS (...)` with the same `LPAD` + `NULLIF` + `IS NOT NULL` construction (NULL-safe + padded).
- Named regression test: `test_check_payout_precision_null_safe_padded_umaban` — asserts via `inspect.getsource` that `LPAD(` is present in BOTH `_check_payout_precision` and `_check_payout_recall`, and that at least one of `NOT EXISTS` / `EXCEPT` / `IS DISTINCT FROM` is present (i.e. not relying on `NOT IN` alone). Mock-cursor scenarios cover: (i) int `umaban=1` matching `'01'`, (ii) NULL/empty payout slots not causing silent skip, (iii) `umaban=12` matching slot2 `'12'`.

Verdict rationale: the required fix (`LPAD` + `NOT EXISTS`/`EXCEPT` over a NULL-filtered payout set) is present as a concrete SQL contract with a regression test that demonstrably closes both the three-valued-logic and padding failure modes. **FULLY RESOLVED.**

**Cycle-2 NEW HIGH #2 — Plan 03 `_select_se_state` `timediff` merge row-multiplication: FULLY RESOLVED**

Evidence (from the cycle-2 revised plan text):
- Plan 03 Task 1 requires the normalized SE select to filter `datakubun`:
  - `FROM normalized.n_uma_race WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')`
- The public-side `timediff` select is now ALSO filtered and joined on `datakubun`:
  - `FROM public.n_uma_race WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7','9')`
  - Merge key explicitly includes `datakubun`: `(year, jyocd, kaiji, nichiji, racenum, umaban, kettonum, datakubun)`
- This structurally guarantees 1:1: because both frames are constrained to the same two `datakubun` values AND `datakubun` is part of the merge key, a normalized row with `datakubun='7'` can only ever join the single public row with the same PK + `datakubun='7'`. The one-to-many risk is eliminated by construction, not by a fragile post-hoc dedup.
- A fail-fast cardinality assertion is required in code: `len(se_df) == len(merged_df)` after merge; mismatch raises `RuntimeError` (D-13 — no silent fallback).
- Named regression test: `test_select_se_state_no_row_multiplication_on_timediff_merge` — asserts via `inspect.getsource` that `_select_se_state` contains (a) `FROM public.n_uma_race`, (b) a `datakubun IN ('7','9')` filter, (c) `datakubun` in the merge key, and (d) a merge-before/after row-count assertion.

Verdict rationale: the fix addresses the root cause (both sides filtered + `datakubun` in join key = strict 1:1) rather than a symptom, and is pinned by a regression test plus a runtime cardinality assert. **FULLY RESOLVED.**

**Cycle-2 NEW HIGH #3 — Plan 03 missing/null `time` misclassified as `is_dead_loss`: FULLY RESOLVED**

Evidence (from the cycle-2 revised plan text):
- Plan 01 adds the config sentinel: `se_marker_canonicalization.missing_value_sentinel: "__MISSING__"` (with a grep/python acceptance criterion asserting `cfg['se_marker_canonicalization'].get('missing_value_sentinel') == '__MISSING__'`).
- Plan 03 Task 1 requires `_canonicalize_markers` to guard BEFORE string conversion:
  - `canonicalized = "__MISSING__" if pd.isna(v) else str(v).strip()`
  - This converts `NaN`/`pd.NA`/`None` to `"__MISSING__"` instead of the leaky `str()` outputs (`'nan'`, `'<NA>'`, `'None'`).
- `time_present` is defined to exclude the sentinel first:
  - `time_present = (canonicalized_time != missing_value_sentinel) AND (canonicalized_time not in time_sentinels_absent) AND (canonicalized_time != '')`
  - So missing `time` → `canonicalized_time == '__MISSING__'` → `time_present=False`.
  - `is_dead_loss = marker_active AND time_present` → missing-time rows are NOT dead-loss.
  - `is_race_excluded = marker_active AND not time_present` → missing-time rows fall here (or to `unresolved`), never to dead-loss. This prevents the silent corruption of the `fukusho_hit=0` training target.
- Named regression test: `test_canonicalize_markers_missing_time` — covers 3 variants (`time=None`, `time=np.nan`, `time=pd.NA`), each with `harontimel3='999.0'` / `timediff='9999'` (marker_active=True), asserting `is_dead_loss == False` and `is_race_excluded == True`. The test explicitly documents that without the `pd.isna` guard the `str()` outputs would fall outside the sentinel set and flip the row to `is_dead_loss=True`.

Verdict rationale: the failure mode (missing time → false dead-loss → `fukusho_hit=0` training pollution) is closed by an explicit `pd.isna` guard feeding a dedicated sentinel, with a 3-variant regression test that demonstrably catches the bug. **FULLY RESOLVED.**

### Regression Check — did any cycle-1/cycle-2 resolution regress?

**No regression found.** Spot-checked the carry-forward invariants:
- HIGH #1 (source/confidence conflation): still separated — `sales_start_entry_count_confidence` column and `label_validation_status` remain independent (Plan 01 config + Plan 03 schema, with Plan 02 `test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status`).
- HIGH #2 (tautological reconciliation): still addressed — `_check_raw_validated_drift` + SQL-side payout-set reconstruction + `_compute_race_level_agreement` all retained (Plan 04).
- HIGH #3 (staging-swap privilege/idempotency, no `TO PUBLIC`): still addressed — `INCLUDING ALL`, explicit reader-role `GRANT`, idempotent checksum, `test_label_etl_idempotent` retained (Plan 01/03).
- HIGH #4 (race-cancelled `DataKubun='9'` rows): still protected — `datakubun IN ('7','9')` retained and reinforced by the NEW HIGH #2 fix which now also filters the public side (Plan 03; Plan 02 `test_select_se_state_includes_datakubun_9`).
- HIGH #5 (brittle marker comparisons): still sentinel-based — `_canonicalize_markers` uses `se_marker_canonicalization` sentinel sets (Plan 03; Plan 02 raw/numeric tests retained and augmented by the missing-time test).
- HIGH #6 (Check #5 too broad): still constrained — `_check_dead_loss_not_excluded` fails only `is_dead_loss=true AND is_model_eligible=false AND (ineligibility_reason IS NULL OR ... NOT IN (...legitimate reasons...))` (Plan 04).
- HIGH #7 (scratch check payout-set contamination): still independent — `_recompute_scratch_markers` recomputes from raw `bataijyu` using sentinels and explicitly avoids `label.is_scratch_cancel` (Plan 04; Plan 02 `test_recompute_scratch_markers_uses_sentinel` + `test_check_no_scratch_mislabeled_raw_marker`).

The cycle-2 revisions (NEW HIGH #1/#2/#3) sit on top of these without disturbing them.

### NEW HIGH Concerns (Cycle 3)

**None.**

The cycle-2 revisions introduced no genuinely NEW HIGH concern on the leakage-critical label surface. Reviewer specifically scrutinized: (a) the new `public.n_uma_race.timediff` raw read for any new raw-immutability or column-availability risk (covered by Plan 03's existing raw-immutability extension and a `timediff` column-presence acceptance criterion); (b) the new `__MISSING__` sentinel for any interaction with the existing raw-string/numeric-cast canonicalization contract (the 3-variant test suite unifies all three representations); (c) the `NOT EXISTS` + `LPAD` rewrite for any new set-comparison edge case (NULL payout slots are filtered by `IS NOT NULL` inside the VALUES table). None rise to HIGH. Residual items remain at MEDIUM/LOW (see cycle-2 notes: `_recompute_scratch_markers` reads `normalized.n_uma_race.bataijyu` not raw; stale-staging `INCLUDING ALL` repair edge case; `dochachutosu` test wording) — none leakage-critical, none newly introduced by cycle-2.

### Final Tally

**`CYCLE_SUMMARY: current_high=0`**

All 3 cycle-2 NEW HIGHs are FULLY RESOLVED with concrete, verifiable fixes (named SQL contracts + named regression tests). No carry-over HIGHs. No newly-raised cycle-3 HIGHs.

### Convergence Recommendation

**CONVERGE.** The three cycle-2 HIGHs now have concrete implementation requirements (specific SQL/functions) plus named regression tests, and the reviewer found no leakage-critical regression and no new HIGH. The plan is ready to exit the convergence loop and proceed to execution.

---

## Consensus Summary

> Single-reviewer cycle (Codex only). No divergent views. The summary below is Codex's cycle-3 findings structured for the convergence loop.

### Agreed Strengths (cycle-2 revisions)
- All 3 cycle-2 NEW HIGHs are closed at the root cause, not the symptom: NEW HIGH #2 uses a structural 1:1 join (both sides filtered + `datakubun` in key) rather than post-hoc dedup; NEW HIGH #1 uses `NOT EXISTS` over a NULL-filtered set rather than a defensive `COALESCE`; NEW HIGH #3 inserts the `pd.isna` guard before `str()` so the leaky string forms are never produced.
- Each fix is paired with a named regression test that demonstrably fails on the buggy implementation (`test_check_payout_precision_null_safe_padded_umaban`, `test_select_se_state_no_row_multiplication_on_timediff_merge`, `test_canonicalize_markers_missing_time`) plus, where applicable, a runtime fail-fast assertion (NEW HIGH #2's `len()` cardinality check).
- The cycle-2 revisions reinforce rather than disturb prior resolutions (e.g. NEW HIGH #2's public-side `datakubun IN ('7','9')` filter reinforces HIGH #4; NEW HIGH #3's `__MISSING__` sentinel reinforces HIGH #5's sentinel approach).

### Agreed Concerns (HIGH priority)
None remaining.

### Divergent Views
None (single reviewer).

### Next Step
Exit the convergence loop. Proceed to plan execution (`/gsd-execute-phase 2`) or whatever the orchestrator's converge-branch dictates. No further replan cycle is required.
