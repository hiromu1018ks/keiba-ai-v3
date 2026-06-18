---
phase: 2
reviewers: [codex]
reviewed_at: 2026-06-18T02:24:39Z
cycle: 2
prior_cycle_commit: 8800fdc
plans_reviewed:
  - 02-01-PLAN.md
  - 02-02-PLAN.md
  - 02-03-PLAN.md
  - 02-04-PLAN.md
---

# Cross-AI Plan Review — Phase 2: Fukusho Labels (Cycle 2 — Re-review of REVISED plans)

> **Reviewer selection:** `--codex` requested. Claude CLI skipped (review running inside Claude Code → `SELF_CLI=claude`). Gemini / Qwen / Cursor / Antigravity CLIs not installed. Single external reviewer: **Codex**.
>
> **This is cycle 2 of a plan-convergence loop.** Cycle 1 raised 7 HIGH concerns on the original Phase 2 plans. The plans were then REPLANNED in reviews-mode to resolve those 7 HIGHs and committed as `8800fdc` ("docs(02): replan phase 2 with cross-AI review feedback (7 HIGH resolved)"). This cycle re-reviews the **current (revised)** PLAN.md files to determine how many HIGH concerns remain unresolved.
>
> **Convergence result:** All 7 cycle-1 HIGHs are **FULLY RESOLVED** by the revised plans. However, Codex raised **3 NEW HIGH concerns** introduced by the revisions. Net HIGHs remaining: **3**.
>
> **CYCLE_SUMMARY: current_high=3**

---

## Codex Review (Cycle 2)

### Cycle-1 HIGH Verdicts (1-7)

For each of the 7 cycle-1 HIGHs, Codex judged the revised plan against a FULLY/PARTIALLY/UNRESOLVED bar.

1. **HIGH #1 (`inferred` status semantics conflation) — FULLY RESOLVED.**
   Plan 01 explicitly separates `label_validation_status='inferred'` from `sales_start_entry_count.source_confidence='inferred'` as independent YAML keys, and Plan 03 requires separate table columns `sales_start_entry_count_source` and `sales_start_entry_count_confidence`. Plan 02 adds `test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status`, asserting `label_validation_status == 'validated'` while `sales_start_entry_count_confidence == 'inferred'` on the same row. Carry-over: no.

2. **HIGH #2 (reconciliation may be tautological) — FULLY RESOLVED** *(but see NEW HIGH #1 below for a SQL-level gap in the implementation of these checks)*.
   Plan 04 adds the required independent checks: `_check_raw_validated_drift` for raw-vs-validated drift, `_compute_race_level_agreement` for race-set reconstruction from label rows, and SQL-side payout-set reconstruction inside `_check_payout_precision` / `_check_payout_recall`. The original tautology concern is addressed at the plan-contract level. Carry-over: no.

3. **HIGH #3 (staging-swap privilege/idempotency + `GRANT ... TO PUBLIC`) — FULLY RESOLVED** *(but see NEW HIGH #2/MEDIUM note for a stale-staging edge case)*.
   Plan 01 removes `PUBLIC` grants and introduces explicit `{reader}` grants for the `label` schema. Plan 03 requires `CREATE TABLE ... (LIKE label.fukusho_label INCLUDING ALL)`, post-rename `GRANT SELECT ... TO {reader_role}`, no `TO PUBLIC`, and two-run rowcount/checksum idempotency verification via `scripts/run_label_etl.py` and `test_label_etl_idempotent`. Carry-over: no.

4. **HIGH #4 (race-cancelled `DataKubun='9'` rows dropped by `_select_se_state`) — FULLY RESOLVED.**
   Plan 01 codifies `se_datakubun_inclusion.required_se_datakubun_values: ["7", "9"]`; Plan 02 adds `test_select_se_state_includes_datakubun_9`; Plan 03 requires the `_select_se_state` SQL to contain `datakubun IN ('7', '9')`. This directly proves race-cancelled SE rows are not silently filtered out. Carry-over: no.

5. **HIGH #5 (brittle marker string/float comparisons) — FULLY RESOLVED** *(but see NEW HIGH #3 below for a null-canonicalization gap in the same code path)*.
   Plan 01 defines `se_marker_canonicalization` sentinel sets covering both string and numeric forms. Plan 02 tests raw-string and numeric-cast forms (`test_canonicalize_markers_raw_string_form` / `test_canonicalize_markers_numeric_cast_form`) asserting identical results. Plan 03 implements `_canonicalize_markers` using sentinel-set membership rather than single string/float equality. Carry-over: no.

6. **HIGH #6 (reconciliation Check #5 too broad) — FULLY RESOLVED.**
   Plan 04 rewrites `_check_dead_loss_not_excluded` to fail only rows where `is_dead_loss=true AND is_model_eligible=false AND (ineligibility_reason IS NULL OR ineligibility_reason NOT IN (...legitimate reasons...))`. The legitimate-reason list matches Plan 03's `compute_is_model_eligible` outputs (`obstacle`, `newcomer`, `no_fukusho_sale`, `unresolved`, `race_or_horse_cancelled`, `class_below_minimum`, `status_not_eligible`). Dead-loss in an otherwise-legitimately-ineligible race no longer raises a false alarm. Carry-over: no.

7. **HIGH #7 (scratch check misses payout-set contamination via label booleans) — FULLY RESOLVED.**
   Plan 04 requires `_check_no_scratch_mislabeled` to call `_recompute_scratch_markers`, which recomputes scratch from raw SE `bataijyu` using `label_spec.yaml` sentinels and explicitly does NOT use `label.is_scratch_cancel`. Tests include the failure mode where `label.is_scratch_cancel=False` but raw `bataijyu='000'` (`test_check_no_scratch_mislabeled_raw_marker`), plus an `inspect.getsource` regression assert (`test_recompute_scratch_markers_uses_sentinel`). Carry-over: no.

**Cycle-1 outcome: 7/7 FULLY RESOLVED → 0 carry-over HIGHs.**

### New HIGH Concerns (cycle 2)

These are NEW HIGHs raised on the revised plans. Each represents either a latent bug in newly-added code paths or a cross-plan contract mismatch the revisions introduced.

- **NEW HIGH #1 (newly raised, cycle 2) — `_check_payout_precision` / `_check_payout_recall` SQL is unsafe: `NOT IN` with NULLs + unpadded `umaban`.** [Plan 04]
  Plan 04's `_check_payout_precision` SQL sketch uses `l.umaban::varchar NOT IN (NULLIF(hr.payfukusyounmaban1, '00'), NULLIF(hr.payfukusyounmaban2, '00'), ...)`. Two compounding defects:
  (a) **`NOT IN` with NULLs** — if any payout slot is NULL/empty after `NULLIF`, SQL three-valued logic makes `NOT IN` evaluate to UNKNOWN, which can silently fail to flag extra positives. This undermines the most important reconciliation gate (LABEL-03 / SC#2).
  (b) **`umaban` padding mismatch** — `l.umaban` is an integer in `label.fukusho_label`, so `1::varchar = '1'`, while HR `payfukusyounmaban1` is zero-padded (`'01'`). The string comparison will produce false mismatches (or mask real ones) depending on how the query is structured.
  **Required fix:** use `LPAD(l.umaban::text, 2, '0')` on the label side and a `NOT EXISTS` over an unnested, NULL-filtered payout set (or equivalent `EXCEPT`-based set comparison) rather than `NOT IN`. This must be added as a concrete acceptance criterion + test in Plan 04 before the cycle can converge.

- **NEW HIGH #2 (newly raised, cycle 2) — `_select_se_state` `timediff` merge can multiply SE rows (one-to-many).** [Plan 03]
  Plan 03's `_select_se_state` selects `normalized.n_uma_race WHERE datakubun IN ('7','9')`, then **separately** selects `public.n_uma_race.timediff` with **no `datakubun` filter** and merges on horse/race PK `(year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)` — which does NOT include `datakubun`. The CONTEXT/RESEARCH states SE can have multiple `DataKubun` records per horse. If `public.n_uma_race` carries multiple rows per horse (different `datakubun`), the merge becomes one-to-many, duplicating label rows and corrupting marker assignment downstream (and thus the `is_dead_loss` / `is_scratch_cancel` classifications that depend on `timediff`/`time`).
  Plan 03 explicitly chose "public 側の全 DataKubun 行から timediff を拾える方が安全" but did not specify a de-duplication/priority rule. This is ambiguous and unverifiable from the plan text.
  **Required fix:** either filter `public.n_uma_race.timediff` to `datakubun IN ('7','9')` and join on `datakubun` too, or specify an explicit priority rule (e.g., prefer `datakubun='7'`, fall back to max `datakubun`) and add a unit test asserting no row multiplication.

- **NEW HIGH #3 (newly raised, cycle 2) — `_canonicalize_markers` treats null/missing `time` as "present", mislabeling as `is_dead_loss`.** [Plan 03]
  Plan 03's `_canonicalize_markers` normalizes each marker column via `str(v).strip()` and computes `time_present = canonicalized_time not in time_sentinels_absent AND canonicalized_time != ''` where `time_sentinels_absent: ["0", "0.0", "", "9999", "9999.0"]`. For a missing `time` (`NaN`, `pd.NA`, `None`), `str()` yields `'nan'`, `'<NA>'`, or `'None'` — none of which are in the sentinel set. Such a row is therefore classified as `time_present=True`, and combined with `marker_active=True` becomes `is_dead_loss=True` (競走中止), when the correct classification for a missing/unknown time is almost certainly `is_race_excluded` or unresolved. This is label-critical: dead-loss horses are kept in training as `fukusho_hit=0` (§10.6), so a false `is_dead_loss` directly corrupts the training target.
  Note Plan 02's `test_canonicalize_markers_*` tests cover raw-string and numeric-cast forms but NOT the null/missing form, so the bug would slip through the current RED→GREEN cycle.
  **Required fix:** add explicit `pd.isna(v)` handling before string conversion (treat missing as absent/excluded, not present), and add a `test_canonicalize_markers_missing_time` test covering `None`/`NaN`/`pd.NA`.

### MEDIUM/LOW Notes

- **MEDIUM — `test_dochachukubun_dead_heat_detection` wording is internally inconsistent** [Plan 02]. The test text says `dochachutosu='1'` should make `dead_heat`, then immediately says payout slot4/5 is authoritative and `DochacoTosu` alone should not trigger it. The latter is correct (matches Plan 01's `dead_heat_rules.detection`); tighten the test wording so the implementation does not accidentally gate on `dochachutosu`.
- **MEDIUM — stale staging table can bypass `INCLUDING ALL` repair** [Plan 03]. `CREATE TABLE IF NOT EXISTS label.fukusho_label_staging (LIKE ... INCLUDING ALL)` will not repair a pre-existing staging table left over from an older implementation with different columns/indexes. Prefer `DROP TABLE IF EXISTS label.fukusho_label_staging` before creating staging, or assert staging indexes/constraints match the target before use. This is adjacent to the (resolved) HIGH #3 idempotency work.
- **MEDIUM — `_recompute_scratch_markers` reads `normalized.n_uma_race.bataijyu`, not raw** [Plan 04]. The docstring/plan text says "raw SE marker" but the SQL targets `normalized.n_uma_race`. This is acceptable only if normalized preserves `bataijyu` byte-for-byte enough for sentinel checks (no trimming/case-folding). Otherwise it should read `public.n_uma_race.bataijyu`. Pin the source explicitly and add an assertion that normalized `bataijyu` is identical to raw for the sentinel values.

### Summary and Tally

The revisions materially address **all 7 cycle-1 HIGH concerns** (7/7 FULLY RESOLVED, 0 carry-over). However, the revised plans introduce **3 NEW HIGH concerns** that can independently break reconciliation (NEW HIGH #1) or label classification (NEW HIGH #2, #3):

- NEW HIGH #1 — unsafe payout precision/recall SQL (`NOT IN` NULLs + `umaban` padding) → can miss reconciliation violations.
- NEW HIGH #2 — `timediff` merge row multiplication → can duplicate labels and corrupt marker assignment.
- NEW HIGH #3 — null/missing `time` misclassified as present → false `is_dead_loss` → corrupted training target.

**Final tally (PARTIALLY/UNRESOLVED cycle-1 HIGHs + newly-raised cycle-2 HIGHs): 3 HIGH concerns remain.**

Convergence is NOT yet reached. Another replan cycle is needed to close NEW HIGH #1/#2/#3 (the three are all in Plan 03/04 and are concrete, mechanical fixes: SQL set-comparison, merge-key/priority rule, and `pd.isna` guard + test).

---

## Consensus Summary

> Single-reviewer cycle (Codex only). No divergent views. The summary below is Codex's cycle-2 findings structured for the convergence loop.

### Agreed Strengths (carried forward from cycle 1, now verified in revisions)
- 3-wave dependency structure remains sound (config/GRANT → RED tests → ETL → reconcile).
- All 7 cycle-1 HIGHs have concrete, verifiable fixes in the revised plans (separate columns/keys, independent drift check, INCLUDING ALL + reader-role GRANT + idempotent checksum, `datakubun IN ('7','9')`, sentinel-set canonicalization, dead_loss_only constraint, raw-marker scratch recomputation).
- Cross-plan contract for the legitimate-ineligibility-reason list (HIGH #6) is consistent between Plan 03 (`compute_is_model_eligible`) and Plan 04 (`_check_dead_loss_not_excluded`).
- Sentinel-set approach (HIGH #5) is consistently referenced across Plan 01 (config), Plan 02 (tests), Plan 03 (`_canonicalize_markers`), and Plan 04 (`_recompute_scratch_markers`).

### Agreed Concerns (HIGH priority — must resolve before convergence)
1. **NEW HIGH #1** — `_check_payout_precision` / `_check_payout_recall` SQL uses `NOT IN` with NULLs + unpadded `umaban` (Plan 04). Replace with `LPAD` + `NOT EXISTS`/`EXCEPT` set comparison. (newly raised, cycle 2)
2. **NEW HIGH #2** — `_select_se_state` `timediff` merge from `public.n_uma_race` (no `datakubun` filter) can multiply SE rows (Plan 03). Filter on `datakubun IN ('7','9')` + join on `datakubun`, or specify a priority rule + no-row-multiplication test. (newly raised, cycle 2)
3. **NEW HIGH #3** — `_canonicalize_markers` misclassifies null/missing `time` as present → false `is_dead_loss` (Plan 03). Add `pd.isna` guard + `test_canonicalize_markers_missing_time`. (newly raised, cycle 2)

### Divergent Views
None (single reviewer).

### Open Questions for the Next Replan Cycle
- Pin the exact SQL for payout-set comparison (Plan 04) — is `EXCEPT`-based set equality preferred over `NOT EXISTS` for the race-level agreement helper too?
- Pin the `timediff` source (Plan 03): filter `public.n_uma_race` to `datakubun IN ('7','9')` and join on `datakubun`, or pull `timediff` from `normalized.n_uma_race` instead (requires Phase 1 `normalize.py` to start selecting `timediff`)?
- Confirm normalized `bataijyu` (Plan 04 `_recompute_scratch_markers` source) is byte-identical to raw for sentinel values, or switch to `public.n_uma_race`.
