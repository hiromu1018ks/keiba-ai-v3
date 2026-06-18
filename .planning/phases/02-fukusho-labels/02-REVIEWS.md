---
phase: 2
reviewers: [codex]
reviewed_at: 2026-06-18T00:00:00Z
plans_reviewed:
  - 02-01-PLAN.md
  - 02-02-PLAN.md
  - 02-03-PLAN.md
  - 02-04-PLAN.md
---

# Cross-AI Plan Review — Phase 2: Fukusho Labels

> Reviewer selection: `--codex` requested. Claude CLI skipped (review running inside Claude Code → `SELF_CLI=claude`). Gemini / Qwen / Cursor / Antigravity CLIs not installed; OpenCode available but not requested. Single external reviewer: **Codex**.
>
> This is the first cross-AI review cycle for Phase 2. No prior REVIEWS.md existed (`has_reviews: false`).

## Codex Review

**Summary**

The plans are strong on intent and generally aligned with the Phase 2 "sacred surface" requirements: two-layer labels, payout-table priority, `TorokuTosu` over `SyussoTosu`, D-13 explicit isolation, raw immutability, and a reconciliation gate are all explicitly planned. However, several details are brittle enough to matter for a leakage-critical label surface. The biggest risks are inconsistent status semantics around `inferred`, fragile marker representations such as `harontimel3 == '999.0'`, staging-swap privilege/idempotency issues, and a reconciliation test design that can become tautological if it compares labels derived from HR back to HR without independently checking the ETL joins and exclusion flags. Overall the plan is promising but not yet low-risk.

**Strengths**

- The 3-wave dependency structure is sound: config/GRANT foundation → RED unit tests → ETL → reconciliation gate.
- Pitfall 3 is correctly addressed: `fukusho_payout_places` uses `TorokuTosu`, not `SyussoTosu`, with an explicit regression test in Plan 02.
- Pitfall 1 is repeatedly called out with real names: `bataijyu`, `harontimel3`, `timediff`, `payfukusyounmaban1..5`.
- Plan 02 has good synthetic coverage for LABEL-04: dead heat, scratch/cancel, individual dead-loss, race cancelled, no-sale, and `tokubaraiflag2`.
- D-13 is mostly respected: unresolved/special branches are explicit rather than silently falling through.
- Plan 03 includes raw fingerprint checks and a dedicated raw immutability test, which is appropriate for D-06.
- Plan 04 correctly chooses race-level payout-set equality rather than row-level accuracy alone.
- `tokubaraiflag2` is handled even though live count is zero, which is the right future-proofing posture.

**Concerns**

- **HIGH — Plan 02/03 status semantics conflict for `sales_start_entry_count`.** Plan 01 says `sales_start_entry_count.proxy_status: "inferred"`, but Plan 03 status logic says HR `DataKubun='2'` rows become `validated`. Plan 02's `test_sales_start_entry_count_proxy` even notes this ambiguity. This conflates "sales_start count source inferred" with `label_validation_status`. Keep these as separate concepts or downstream filtering may misinterpret `inferred`.

- **HIGH — Reconciliation may be tautological.** Plan 03 derives `fukusho_hit_validated` directly from `PayFukusyoUmaban1..5`; Plan 04 then checks it against the same HR fields. That catches ETL bugs, but it does not independently validate the label against finishing order, scratch/dead-loss classification, or sales-start boundary except via auxiliary checks. The >99.9% gate should explicitly include raw-vs-validated drift classification and independent race-set reconstruction from label rows.

- **HIGH — Staging swap can drop grants/indexes/comments.** Plan 03's `DROP TABLE label.fukusho_label` then rename staging may lose grants/default privileges depending on ownership/default privilege state. The plan adds `GRANT SELECT ON label.fukusho_label TO PUBLIC`, which is both too broad and inconsistent with reader-role-only access. This threatens D-06/least privilege and idempotent correctness.

- **HIGH — Race cancellation handling is underspecified in ETL joins.** Plan 03 primarily selects `normalized.n_uma_race`, while race-cancelled rows may have `DataKubun='9'` and not `DataKubun='7'`. If normalized ETL filtered to confirmed SE only, race-cancelled rows can be lost before label generation. The plan must prove `_select_se_state` includes both `DataKubun='7'` and `DataKubun='9'`.

- **HIGH — `dead_loss` marker uses fragile string/float comparisons.** Plans use examples like `harontimel3 == '999.0'`, `time='9990.0'`, `time NOT IN ('0.0','','9999')`. If source columns are strings in raw and normalized has numeric conversions, equality may fail silently. Normalize marker columns to canonical strings or numeric sentinels before classification and test both raw-style and normalized-style representations.

- **HIGH — Reconciliation Check #5 may incorrectly require every dead-loss horse to be model-eligible.** §10.6 says individual 競走中止 should not be excluded because of dead-loss itself. But a dead-loss horse in an obstacle race, newcomer race, no-sale race, or unresolved race should still be `is_model_eligible=False` for other reasons. Plan 04's `_check_dead_loss_not_excluded`: `is_dead_loss=True AND is_model_eligible=False` is too broad. It must check "excluded solely due to dead_loss" or constrain to otherwise eligible races.

- **HIGH — Scratch/cancel check may miss payout-set contamination.** Plan 04 checks `is_scratch_cancel=True AND fukusho_hit_validated=1`, but if scratch classification fails, the horse may not be flagged. A stronger check joins SE marker conditions directly, not just label booleans.

- **MEDIUM — Plan 02 claims 18 tests but later defines 20+.** This is not a functional bug, but acceptance criteria and Plan 03 verify regexes mention `18 passed|19 passed`, while Plan 02 adds 20 tests including `tokubaraiflag2`. This can make the implementation "pass" with missing tests.

- **MEDIUM — `dochachutosu == '1'` dead-heat detection is suspicious.** Research says slot4/5 usage and payout_count > theoretical places are reliable. Depending on EveryDB2 semantics, `DochacoTosu=1` may not mean "there is a dead heat"; it may be a count field or per-order count. Payout-table expansion should be authoritative.

- **MEDIUM — `tokubaraiflag2` branch is reasonable but underconstrained.** Plan 03 validates if payout exists, unresolved if payout set empty. It should also assert `FuseirituFlag2 != '1'` precedence and distinguish `PayFukusyoUmaban='00'` from empty slots. Plan currently says fuseiritu branch comes first, which is good, but tests should lock this precedence.

- **MEDIUM — Plan 04 says all §10.5 six checks are BLOCK, but D-02 originally allows quantitative drift as INFO.** The six structural checks being BLOCK is defensible. But "agreement <99.9%" must itself be BLOCK, not just metadata under `agreement`. The plan does not clearly say the verdict fails when agreement is below threshold.

- **MEDIUM — Held-out design is more complex than useful for deterministic labels.** Time-series holdout + stratification is not harmful, but for label reconciliation this is not model evaluation. The real risk is implementation correctness, not overfitting to a split. Full-dataset reconciliation should be the primary gate; held-out should be a secondary smoke check.

- **MEDIUM — `class_level_numeric_minimum: 1` may exclude 未勝利 despite project text saying "2歳未勝利以上".** The context is internally ambiguous: §7.2 includes 2歳未勝利以上, but Plan 01 says minimum 1 means 1勝クラス. This could accidentally exclude intended maiden races. Needs requirement confirmation against `docs/keiba_ai_requirements_v1.3.md §7.2`.

- **MEDIUM — `GRANT ... TO PUBLIC` in Plan 03 conflicts with Plan 01 reader role design.** This is unnecessary privilege expansion. Use `keiba_readonly` or rely on default privileges, not PUBLIC.

- **MEDIUM — `settings.py` adds `db_schema_label`, but Plan 03 hard-codes `label` in many SQL statements.** That weakens configurability and can diverge from settings. Either use settings consistently or explicitly declare label schema non-configurable.

- **LOW — `label_spec.yaml` includes observed counts as config.** Expected counts like 956/3554/97 are useful documentation but risky as config. Future DB updates will invalidate them. Keep as comments or monitoring baselines, not behavioral config.

- **LOW — `scripts/apply_schema.sql` synchronization is ambiguous.** Plan 01 says dry-run then manually sync or maybe source-of-truth is `schema.py`. Pick one. Ambiguity invites stale SQL artifacts.

**Suggestions**

- Split `label_validation_status` from `sales_start_entry_count_source_status`. Example: `label_validation_status='validated'`, `sales_start_entry_count_source='torokutosu_proxy'`, `sales_start_entry_count_confidence='inferred'`.

- Make the reconciliation verdict fail if `agreement_pct < 99.9`, and run agreement on the full dataset as the primary gate. Keep latest-10% stratified holdout as an additional report.

- Replace Plan 04 Check #5 with: dead-loss horses in otherwise model-eligible races must remain eligible and have `fukusho_hit_validated=0`; dead-loss in ineligible race classes may be excluded for the other reason.

- In reconciliation checks, recompute scratch/dead-loss/race-cancelled markers from raw SE/HR columns, not only from label table boolean flags.

- Avoid `GRANT SELECT ... TO PUBLIC`; grant to the reader role explicitly after staging rename.

- Strengthen idempotent staging swap: preserve indexes, primary key, owner, grants, and comments; verify two consecutive ETL runs produce identical row counts and a deterministic label-table checksum.

- Normalize marker fields before classification: canonicalize `bataijyu`, `harontimel3`, `timediff`, `time`, and `datakubun` into strings or numeric sentinels once, then classify from those canonical fields.

- Add tests for mixed reasons: dead-loss in obstacle/newcomer/no-sale races, scratch in no-sale race, race-cancelled with HR missing, and `tokubaraiflag2=1` plus `fuseirituflag2=1`.

- Confirm §7.2 class eligibility before implementing `class_level_numeric_minimum=1`; the "2歳未勝利以上" language may require allowing `class_level_numeric=0` for 未勝利.

- Treat observed-count baselines as INFO checks, not config behavior. Example: report `scratch_count`, `dead_loss_count`, `race_cancelled_count`, but do not assert exact counts except in research snapshots.

**Risk Assessment**

Overall risk: **MEDIUM**.

The architecture is directionally correct and covers the major domain pitfalls, especially `TorokuTosu`, payout-table priority, dead heat, and D-13. The remaining risks are not scope creep; they are correctness risks on the sacred label surface. The highest-risk areas are semantic ambiguity around `inferred`, tautological reconciliation, brittle marker normalization, and staging-swap grants. Fixing those before implementation would likely reduce the phase to LOW/MEDIUM risk.

---

## Consensus Summary

> Single-reviewer cycle (Codex only). The "consensus" below is Codex's findings, prioritized for the convergence loop. No divergent views exist (only one reviewer).

### Agreed Strengths
- 3-wave dependency structure is sound (config/GRANT → RED tests → ETL → reconcile).
- Pitfall 1 (real column names) and Pitfall 3 (`TorokuTosu` not `SyussoTosu`) correctly handled with regression tests.
- Strong LABEL-04 synthetic coverage (dead heat / scratch / dead-loss / race-cancelled / no-sale / `tokubaraiflag2`).
- D-13 explicit-isolation posture and raw-immutability (D-06) tests are present.
- Reconciliation uses race-level payout-set equality (correct over row-level accuracy).

### Agreed Concerns (HIGH priority — must resolve before GREEN implementation)
1. **`inferred` status semantics conflation** between `label_validation_status` and `sales_start_entry_count` source. Separate the two concepts. (Plan 01/02/03)
2. **Reconciliation is at risk of being tautological** — `fukusho_hit_validated` is derived from `PayFukusyoUmaban`, then reconciled back to the same field. Must add independent cross-checks (raw-vs-validated drift, marker reconstruction from raw, race-set reconstruction from label rows). (Plan 04)
3. **Staging-swap `GRANT SELECT ... TO PUBLIC`** is over-broad and inconsistent with reader-role least privilege; risks losing indexes/grants/comments on DROP+RENAME. (Plan 03)
4. **Race-cancelled rows (`DataKubun='9'`) may be silently dropped** by `normalized.n_uma_race` if the normalized ETL filtered to confirmed SE only. Prove `_select_se_state` includes them. (Plan 03)
5. **`dead_loss` / scratch / race-cancelled marker comparisons are brittle** (string `'999.0'` vs numeric, `time NOT IN ('0.0','','9999')`). Canonicalize markers before classification. (Plan 02/03)
6. **Reconciliation Check #5 (`is_dead_loss=True AND is_model_eligible=False`) is too broad** — dead-loss in obstacle/newcomer/no-sale races is legitimately ineligible for other reasons. Restrict to "excluded solely due to dead_loss". (Plan 04)
7. **Scratch check relies on label booleans, not raw markers** — if scratch classification fails, contamination goes undetected. Recompute from raw SE/HR. (Plan 04)

### Divergent Views
None (single reviewer).

### Open Question for Planner
- Confirm `class_level_numeric_minimum=1` against `docs/keiba_ai_requirements_v1.3.md §7.2` — "2歳未勝利以上" may require allowing `class_level_numeric=0` (未勝利), which would change D-03 eligibility. (Plan 01 / MEDIUM)
