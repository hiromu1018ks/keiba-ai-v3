---
phase: 5
cycle: 1
reviewers: [codex]
reviewed_at: 2026-06-20T22:13:58Z
plans_reviewed: [05-01-PLAN.md, 05-02-PLAN.md, 05-03-PLAN.md, 05-04-PLAN.md, 05-05-PLAN.md, 05-06-PLAN.md]
reviewer_command: "codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check"
context_files_included: [PROJECT.md (1-80), ROADMAP.md (Phase 5 section), REQUIREMENTS.md (EV/BACK), 05-CONTEXT.md, 6 PLAN.md files]
---

# Cross-AI Plan Review — Phase 5 (EV & Backtest)

> Cycle 1. Single external reviewer (Codex / OpenAI) per `--codex` flag.
> This phase is leakage-critical: EV/rank + race_id-grouped time-series virtual-purchase backtest with refund/dead-loss accounting. Every HIGH below must be resolved before `/gsd-execute-phase 5`.

## Codex Review

**Summary**

The phase is directionally strong and covers the right invariants: fixed odds policies, race-level time splits, EV/rank purity, refund/dead-loss accounting, strategy stamping, and all-candidate reporting. However, as written, the phase still has several leakage/correctness hazards that must be fixed before implementation. The biggest issues are per-horse odds snapshot alignment, joining odds/labels only by `race_key`, an explicit contradiction on `0999` handling, and ambiguous/overlapping train/calib period examples. These are not cosmetic: they can corrupt EV, duplicate rows, inflate or deflate ROI, or create train/calib leakage.

**Strengths**

- **05-01** establishes `BTWindow` / `BT_WINDOWS` and explicit disjoint + chronological guards with `raise ValueError`, which is the right structural protection for BACK-01.
- **05-02** cleanly separates pure EV/rank/purchase/metrics functions from DB access, which makes EV math and purchase rules easy to test.
- **05-03** correctly centers BACK-04 on `merge_asof(direction='backward')`, fixed `30min_before` / `10min_before`, and `no_bet` instead of fallback odds.
- **05-03** explicitly tests refund, scratch, race exclusion, dead-loss, no-sale, special payout, and dead-heat payout slots.
- **05-04** uses backtest-id scoped staging swap instead of replacing the whole backtest table, preserving other candidate runs.
- **05-05 / 05-06** correctly require all candidate policies/configs to be reported together and defer model selection to Phase 6.

**Concerns**

- **HIGH — 05-03 Task 1 / 05-05 Task 1: odds snapshot appears race-level, but odds are horse-level.**
  `select_odds_snapshot(jodds_df, race_times, policy)` is described as merging `race_times` to JODDS by `race_key` only. JODDS odds are per horse/umaban. This can return one arbitrary horse's odds per race or otherwise lose per-horse odds. The snapshot selection must be keyed by `race_key + umaban` or full race PK + `umaban`.

- **HIGH — 05-05 Task 1: `pred_df.merge(snapshot, on='race_key', how='left')` can create cartesian duplication.**
  Predictions are horse-level and snapshots are horse-level. Joining only on `race_key` will multiply every predicted horse by every odds row in the race. This corrupts EV, top-2 selection, accounting, and all metrics. Same concern applies to "selected + label フラグ + HARAI … race_key JOIN"; labels are horse-level and must join on race + horse identity.

- **HIGH — 05-03 conflicts with the provided Phase 5 decision on `0999`.**
  Context D-02 says `----` / `****` / `0000` / `0999` are all `no_bet`. Plan 05-03 says `0999` is valid odds as 99.9. That is a direct policy contradiction in a leakage-critical odds module. Pick one canonical rule before implementation; based on the supplied context, `0999` should be `no_bet`.

- **HIGH — 05-04 Task 1 has an overlapping train/calib example.**
  The behavior section gives `train=('2019-06-01','2022-12-31')` and `calib=('2022-07-01','2022-12-31')`, which overlap. That violates the stated guard `max(train) < min(calib)`. The later 05-05 carve-out says train should end at `calib_start - 1 day`, but 05-04's test spec is contradictory and could normalize leakage.

- **HIGH — 05-05 does not make BT-window category-map refit an acceptance criterion.**
  The context says category maps must be fit on each BT train period only. The plans mention this in read-first context, but the executable acceptance criteria do not prove that test-period category information is excluded. If the existing snapshot/category map fitted on broader data is reused, that is test-period leakage.

- **MEDIUM — 05-01 says BACK-01 via `mlxtend.GroupTimeSeriesSplit`, but the plan implements fixed date windows directly.**
  Direct fixed windows are acceptable if guarded, but the roadmap explicitly names `mlxtend.GroupTimeSeriesSplit`. The plan should either use it or document why fixed BT windows supersede it while preserving group-disjoint semantics.

- **MEDIUM — 05-03 Task 1 needs stronger tests for multi-horse races.**
  Existing tests check backward/future/no-bet behavior, but the critical failure mode is selecting correct odds for multiple horses in the same race at the same cutoff. Add a test with at least three `umaban` rows where each horse has distinct odds and assert row-preserving output.

- **MEDIUM — 05-03 FukusyoFlag mapping is asserted but not independently guarded.**
  The plan treats `FukusyoFlag` values as no-bet for `0/1/3`. Given the high impact of misclassifying sale availability, add tests based on the EveryDB2 manual values and include at least one normal-sale flag case.

- **MEDIUM — 05-04 persists only selected rows, weakening auditability of `odds_missing_policy=no_bet`.**
  If no-bet candidates are dropped before persistence, later audits cannot easily verify how many candidates were excluded due to missing/special odds. Either persist candidate-level rows with `selected_flag=false`, or add per-backtest exclusion summaries/counts.

- **MEDIUM — 05-05 / 05-06 lack a real-data JODDS coverage gate.**
  Since JODDS acquisition is in progress, `scripts/run_backtest.py` should refuse non-synthetic execution unless coverage for all BT test races and policies is explicitly checked and reported. Otherwise a "real" backtest could silently become mostly no_bet due to incomplete ingestion.

- **MEDIUM — 05-02 metrics and 05-03 accounting should align on `profit`.**
  05-02 computes `profit_loss = sum(payout_amount) + sum(refund_amount) - sum(stake)`, while 05-03 returns per-row `profit`. These should be asserted equivalent. Otherwise refund rows or no-sale rows could diverge between row-level and aggregate accounting.

- **LOW — 05-01 has inconsistent RED-stub counts.**
  It says 8 test files in some places and lists 9+ files elsewhere. Minor, but this kind of mismatch makes phase tracking noisier.

- **LOW — 05-05 acceptance says `grep "fuku_odds_lower" run_backtest.py` should not appear.**
  Avoiding a rename is good, but forbidding the column name entirely is brittle. The orchestrator may reasonably validate required columns.

**Suggestions**

- Fix the core contract: odds snapshots must be horse-level. Use full race key plus `umaban` for `select_odds_snapshot`, prediction joins, label joins, and accounting joins.
- Add a multi-horse odds snapshot unit test and an E2E test that asserts input prediction row count is not multiplied after odds merge.
- Resolve `0999` policy before coding. If the canonical Phase 5 context stands, treat `0999` as `no_bet` and test it.
- Correct 05-04's period-injection example so train and calib never overlap.
- Add explicit tests proving BT-window category maps/encoders are fit using train rows only.
- Add a non-synthetic JODDS completeness gate: fail loud if required BT race/policy coverage is below an agreed threshold or if acquisition is incomplete.
- Persist or report no-bet exclusion counts by reason: missing snapshot, special odds, no sale, invalid odds, scratch/cancel.
- Add one accounting invariant test: `sum(row.profit) == sum(payout_amount) + sum(refund_amount) - sum(stake)`.

**Risk Assessment**

Overall risk: **HIGH**.

The plan has the right architecture, but the current written contracts leave open two severe correctness bugs: horse-level odds alignment and race-key-only joins. Either one can invalidate EV and ROI. The `0999` contradiction and overlapping train/calib example are also unacceptable in a leakage-critical phase. Once those are corrected and covered by tests, the phase risk would likely drop to medium or low.

---

## Consensus Summary

Single-reviewer cycle (Codex only). Consensus = Codex findings, cross-verified by the orchestrator against the PLAN files.

### Agreed Strengths (verified present in plans)

- BT-window helper with hard disjoint + chronological guards (05-01)
- Pure-function separation for EV/rank/purchase/metrics (05-02)
- `merge_asof(direction='backward')` + `no_bet` sentinel + fixed 30min/10min policy (05-03)
- Explicit 6-scenario refund/scratch/dead-loss/dead-heat accounting test matrix (05-03)
- Backtest-id scoped staging swap preserving parallel candidate runs (05-04)
- All-candidate-policy reporting + model-selection deferral to Phase 6 (05-05 / 05-06)

### Agreed Concerns (HIGH — all 5 are blocking for `/gsd-execute-phase 5`)

All five HIGHs were verified against the PLAN files by the orchestrator:

1. **Horse-level odds lost via `race_key`-only merge_asof** — VERIFIED. PLAN 03 line 89 specifies `pd.merge_asof(..., by='race_key', direction='backward')` with no `umaban` in the `by=`. RESEARCH line 87 confirms JODDS PK is `Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum, HappyoTime, Umaban` (8 cols, horse-level). This will return ONE arbitrary horse's odds per race.
2. **Cartesian duplication in `pred_df.merge(snapshot, on='race_key')`** — VERIFIED. PLAN 05 line 100 joins predictions (horse-level) to snapshot (horse-level) on `race_key` only; line 103 repeats the same for label JOIN. Every horse gets multiplied by every odds row in the race.
3. **`0999` policy contradiction** — VERIFIED, and worse than Codex reported: it is a THREE-way contradiction. CONTEXT.md D-02 (line 25) and RESEARCH §1.1 (line 13) say `0999` → `no_bet`. RESEARCH line 89 says `0999=99.9倍以上`. RESEARCH line 189 and PLAN 03 lines 19/80/90/105/109 say `0999` is valid odds. Must be resolved to ONE rule before coding.
4. **Overlapping train/calib example** — VERIFIED. PLAN 04 line 88 test spec: `train=('2019-06-01','2022-12-31')`, `calib=('2022-07-01','2022-12-31')` — 6-month overlap. Violates the `max(train) < min(calib)` guard the same plan claims to inherit.
5. **BT-window category-map refit not an acceptance criterion** — VERIFIED. CONTEXT requires per-BT-train-only category-map fitting; plans mention it only in read-first context, not in executable `verify`/`acceptance_criteria`/`must_haves`.

### Divergent Views

N/A — single reviewer this cycle. To strengthen signal, a follow-up cycle with a second CLI (gemini or claude) is recommended after these 5 HIGHs are addressed.

### Recommended next step

`/gsd-plan-phase 5 --reviews` → incorporate the 5 HIGHs as acceptance criteria / verify commands in the affected plans (03, 04, 05) before re-running review or proceeding to execute.

---

## Verification coverage

| HIGH concern | Source location (verified) | Affected plans |
|---|---|---|
| Horse-level odds lost in `race_key`-only merge_asof | PLAN 03 line 89 (`by='race_key'`, no `umaban`); RESEARCH line 87 (PK includes `Umaban`) | 05-03, 05-05 |
| Cartesian duplication `merge(on='race_key')` | PLAN 05 line 100 (snapshot), line 103 (label) | 05-05 |
| `0999` three-way contradiction | CONTEXT D-02 line 25; RESEARCH lines 13/89/189; PLAN 03 lines 19/80/90/105/109 | 05-03 (canonicalize) |
| Overlapping train/calib example | PLAN 04 line 88 (`train 2019-06..2022-12`, `calib 2022-07..2022-12`) | 05-04 |
| BT-window category-map refit not in acceptance | 05-05 `verify` / `acceptance_criteria` (absent) | 05-05 |

| MEDIUM concern | Affected plans |
|---|---|
| GroupTimeSeriesSplit vs fixed-window documentation gap | 05-01 |
| Multi-horse odds snapshot test missing | 05-03 |
| FukusyoFlag normal-sale positive test missing | 05-03 |
| No-bet exclusion counts not persisted/reported | 05-04 |
| Real-data JODDS coverage gate missing | 05-05, 05-06 |
| Row vs aggregate `profit` invariant test missing | 05-02, 05-03 |

| LOW concern | Affected plans |
|---|---|
| RED-stub count inconsistency (8 vs 9+) | 05-01 |
| `grep "fuku_odds_lower" run_backtest.py` acceptance brittle | 05-05 |
