---
phase: 5
cycle: 2
reviewers: [codex]
reviewed_at: 2026-06-21T07:35:00Z
plans_reviewed: [05-01-PLAN.md, 05-02-PLAN.md, 05-03-PLAN.md, 05-04-PLAN.md, 05-05-PLAN.md, 05-06-PLAN.md]
reviewer_command: "codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check"
context_files_included: [PROJECT.md (1-80), ROADMAP Phase 5 section, 6 revised PLAN.md files, cycle-1 HIGH/MEDIUM/LOW index]
prior_cycle_high_resolved: [HIGH-1 (RESOLVED), HIGH-2 (RESOLVED), HIGH-3 (RESOLVED), HIGH-4 (RESOLVED)]
prior_cycle_high_partial: [HIGH-5 (PARTIALLY RESOLVED → re-raised as cycle-2 HIGH-A)]
---

# Cross-AI Plan Review — Phase 5 (EV & Backtest)

> **Cycle 2.** Single external reviewer (Codex / OpenAI gpt-5.5) per `--codex` flag.
> Cycle 1 surfaced 5 HIGH + 8 actionable concerns. The 6 PLAN.md files were revised (commit `2311f78`) to incorporate them. This cycle verifies the revisions actually resolve the cycle-1 HIGHs and surfaces NEW concerns introduced by the revision.
>
> **Cycle-2 verdict: 4 of 5 cycle-1 HIGHs are FULLY RESOLVED with concrete tests/acceptance criteria. HIGH-5 is PARTIALLY RESOLVED and re-raises as a NEW integration-layer HIGH (orchestrator `category_map` plumbing is unspecified & untested). Two additional NEW HIGHs surfaced in the integration script (`_carve_calib` typo/under-specification, HARAI join ambiguity). 5 actionable MEDIUMs remain.**

## Codex Review

### Summary

The revised plans resolve most cycle-1 HIGH concerns at the specification level, especially the horse-level odds snapshot, `race_key + umaban` merge contract, `0999 = no_bet`, and the overlapping train/calib example. The main remaining weakness is HIGH-5: the plans now say category maps are refit per BT train window, but the actual orchestrator plumbing is not convincingly specified or tested. Several new risks were introduced around the final integration script: `_carve_calib_from_train_tail` is underspecified, HARAI payout joining is ambiguous, `selected_flag=False` audit rows are promised by persistence but appear dropped by the pipeline, and the JODDS coverage gate may be too coarse to catch horse-level missing odds.

### Cycle-1 HIGH Resolution Verdict

| Concern | Verdict | Evidence (verified against revised plans by orchestrator) |
|---|---|---|
| HIGH-1 — horse-level odds lost via `race_key`-only `merge_asof` | **RESOLVED** | 05-03 must_haves line 19 + acceptance line 112: `by=['race_key','umaban']` in `merge_asof`; `test_odds_snapshot_multi_horse` asserts 3 horses → 3 rows with preserved odds. 05-05 line 103 builds `race_times` per-prediction-horse. |
| HIGH-2 — Cartesian duplication from `pred_df.merge(snapshot, on='race_key')` | **RESOLVED** | 05-05 line 105: `pred_df.merge(snapshot, on=['race_key','umaban'], how='left')` + `assert len(pred_with_odds)==len(pred_df)` loud-fail. Line 108 repeats for label/HARAI joins. `test_pred_snapshot_join_row_count_invariant` (line 172). |
| HIGH-3 — `0999` policy contradiction | **RESOLVED** | 05-03 must_haves line 20: canonical rule `0999=no_bet sentinel`, RESEARCH line 89 "99.9+" discarded for this module. `test_odds_snapshot_0999_is_no_bet` (line 83). Threat T-05-07b documents the decision. |
| HIGH-4 — overlapping train/calib example in 05-04 | **RESOLVED** | 05-04 line 88 example is now non-overlapping: `train=('2019-06-01','2022-06-30')`, `calib=('2022-07-01','2022-12-31')`, `test=('2023-01-01','2023-12-31')`. `test_split_3way_periods_strict_later_guard` (line 89) asserts overlap → `ValueError`. Threat T-05-14b. |
| HIGH-5 — BT-window category-map refit | **PARTIALLY RESOLVED → re-raised as cycle-2 HIGH-A below** | 05-05 lines 96/174 call `fit_category_map(train_feature_df)` per BT window and add `test_bt_category_map_refit_excludes_test_ids`. BUT 05-04 only adds `split_periods` to `train_and_predict` — it does **not** add or test a `category_map` parameter. 05-05 line 97 calls `train_and_predict(..., category_map=bt_fit_map)` but no plan establishes the orchestrator accepts/uses it. **Orchestrator verified:** `as_of_datetime` already exists (Phase 4), `category_map` does NOT. |

### Strengths confirmed in revision

- 05-03 now mandates `by=['race_key','umaban']` in `merge_asof` with a real multi-horse test and per-horse race_times contract.
- 05-03 canonicalizes `0999=no_bet` and explicitly discards the contradicting RESEARCH line in the threat register.
- 05-04 fixes the period example to be strictly-ordered and adds the `strict_later_guard` test plus threat T-05-14b.
- 05-05 adds a `len(pred_with_odds)==len(pred_df)` loud-fail assertion and an E2E test (`test_pred_snapshot_join_row_count_invariant`) that constructs multi-horse multi-race inputs.
- MEDIUM-02 (row/aggregate profit invariant), MEDIUM-04 (audit-row persistence), MEDIUM-05 (JODDS coverage gate), LOW-05 (column-presence assertion) are all now present as named tests / acceptance criteria.

### New concerns introduced by the revision

- **HIGH-A — Category-map plumbing is not actually specified end-to-end (HIGH-5 not closed).**
  05-05 line 97 assumes `train_and_predict(..., as_of_datetime=FIXED_REPRODUCE_TS, category_map=bt_fit_map)`, but 05-04 (the plan that extends `train_and_predict`) only adds `split_periods`. Orchestrator verified: `as_of_datetime` already exists from Phase 4, but there is no `category_map` parameter and no plan adds one. No test proves the supplied BT-train-only map reaches model preprocessing and is used (not silently ignored). Until 05-04 adds the `category_map` parameter + a plumbing test, HIGH-5 is not closed.

- **HIGH-B — `_carve_calib_from_train_tail(bt)` is underspecified and contains a likely typo.**
  05-05 line 94 says "train_start は calib_start-1day に短縮"; semantically that should be `train_end` (you shorten the train window's *end* to make room for calib, you don't move its start). There is no acceptance test proving the carve is deterministic for BT-1..BT-5 and always yields `max(train) < min(calib) < max(calib) < min(test)`. A typo'd carve silently violates the strict-later guard's intent.

- **HIGH-C — HARAI join contract is ambiguous and may be wrong.**
  05-05 line 108 joins `harai_pay_df[['race_key','umaban', ...pay_cols...]]` on `on=['race_key','umaban']`, treating HARAI as horse-level. But HARAI's `PayFukusyoUmaban1..5` / `PayFukusyoPay1..5` are **race-level slot records** (RESEARCH §2 confirms: one HARAI row per race with 5 payout slots). Joining a race-level HARAI row to horse-level predictions on `(race_key, umaban)` will either fail (no `umaban` column on HARAI) or silently broadcast. Either pre-expand HARAI to horse-level (one row per paying umaban) with a uniqueness test, or merge race-level HARAI with `validate='many_to_one'` and row-count assertions.

- **MEDIUM-A — `selected_flag=False` audit rows are promised but likely dropped by the pipeline.**
  05-04 acceptance (line 145/182) + threat T-05-14c require `load_backtest` to persist no-bet/excluded candidates with `selected_flag=False` and `odds_missing_reason`. But 05-05 line 107 does `selected = select_bets(pred_with_ev)` (which filters) then line 113 `load_backtest(etl_cur, selected_with_accounting)` — only selected rows survive into the load. MEDIUM-04 auditability is broken unless the pipeline builds a full candidate table (selected + non-selected with reasons) and loads that, not only bets.

- **MEDIUM-B — JODDS coverage gate measures race-level, not horse-level usable coverage.**
  05-05 line 117 defines coverage as "JODDS snapshot exists for BT test races". The leak-critical failure mode is **horse-level, policy-specific usable snapshot coverage after `select_odds_snapshot`** — i.e. excluding `no_bet`/special-odds/`FukusyoFlag`≠'7' rows. A race can pass the gate while most of its horses are `no_bet`, silently producing a degenerate backtest. Gate should measure candidate-horse usable-odds coverage per `BT window × policy`.

- **MEDIUM-C — `merge_asof` sort order may be insufficient for multi-race inputs.**
  05-03 sorts by `['race_key','umaban','happyo_datetime']`. Pandas `merge_asof` requires the `on` key (`happyo_datetime`/`cutoff_datetime`) to be globally sorted; with overlapping timestamps across races the sort by race_key-first can violate this. Add a multi-race test (not only the same-race multi-horse test) and either sort by the `on` key or use `by=` correctly with a pre-sort on the `on` key.

- **MEDIUM-D — Special payout (特払) accounting not fully proven.**
  `tokubaraiflag2=='1'` is routed through `_lookup_payfukusyo_pay(row)`, but special-payout slot semantics may differ from normal hit-slot lookup (RESEARCH line 289 notes 特払 = "no winning horse but payout exists"). Add a real HARAI-shaped fixture for 特払 with the expected payout/refund treatment asserted, not just the normal-slot path.

- **LOW-A — 05-01 test-count drift persists.**
  05-01 acceptance line 118 says "既存 + 新規6件" but behavior lists 7 BT-window tests (`test_bt_window_*` × 6 + `test_bt_window_equivalent_to_group_ts_split`). Minor precision issue.

### Remaining gaps

- Add explicit `train_and_predict(..., category_map=None)` contract in 05-04 with a test proving the map is passed into preprocessing/training and used (HIGH-A).
- Add deterministic tests for `_carve_calib_from_train_tail` across all BT windows; fix the `train_start`→`train_end` typo (HIGH-B).
- Pre-expand HARAI to horse-level OR use `validate='many_to_one'` for race-level HARAI joins (HIGH-C).
- Ensure the backtest table receives all candidate rows needed for audit, including `no_bet`, missing odds, no-sale, and non-selected candidates (MEDIUM-A).
- Strengthen JODDS coverage to horse-level usable snapshot coverage per `BT window × policy` (MEDIUM-B).

### Risk Assessment

**Residual risk: MEDIUM.**

The core cycle-1 odds and merge-key defects are now directly addressed with good tests (HIGH-1..4 closed). The remaining risk is concentrated in the **integration layer** (05-05's `run_backtest.py`): the final pipeline promises several correctness properties — BT-window category-map refit, deterministic calib carve, horse-level HARAI payout join, full-candidate audit persistence — that are not yet backed by clear function signatures (orchestrator `category_map` param missing), robust acceptance tests, or unambiguous data-shape contracts. HIGH-5 should not be considered closed until category-map refit is wired through the orchestrator and proven with a real preprocessing-path test.

---

## Consensus Summary

Single-reviewer cycle (Codex only, per `--codex` flag). Consensus = Codex findings, cross-verified by the orchestrator against the revised PLAN files and the live `src/model/orchestrator.py` signature.

### Agreed Strengths (verified present in revised plans)

- HIGH-1/2/3/4 fully closed with concrete acceptance_criteria + named tests + threat-register entries (05-03 lines 19/20/112/117/118; 05-04 lines 88/89/118/119; 05-05 lines 105/108/172).
- Snake-case odds-column contract (`fuku_odds_lower`/`fuku_odds_upper`) made explicit cross-plan (05-03 line 21/103/114; threat T-05-SC2).
- MEDIUM-02 row/aggregate profit invariant test (`test_metrics_profit_invariant`, 05-02 line 136).
- MEDIUM-04 audit-row persistence design note (05-04 line 152) + threat T-05-14c.
- MEDIUM-05 JODDS coverage gate (`_assert_jodds_coverage`, 05-05 line 117) + threat T-05-17d.
- LOW-05 column-presence assertion replacing grep-negation (05-05 line 149/175).

### Agreed Concerns (HIGH — blocking for `/gsd-execute-phase 5` unless resolved in cycle 3)

All three cycle-2 HIGHs were verified against the revised PLAN files and the live codebase by the orchestrator:

1. **HIGH-A — Orchestrator `category_map` plumbing unspecified (HIGH-5 re-raised).**
   VERIFIED: `src/model/orchestrator.py:154` `train_and_predict` signature has `as_of_datetime` (Phase 4) but **no `category_map` parameter**. PLAN 05-04 (the plan that extends `train_and_predict`) only adds `split_periods` (lines 24/40/104/117) — it never adds `category_map`. PLAN 05-05 line 97 calls `train_and_predict(..., category_map=bt_fit_map)` assuming the parameter exists. `test_bt_category_map_refit_excludes_test_ids` (05-05 line 174) asserts the *map contents* but cannot prove the orchestrator *uses* it. Fix: 05-04 must add `category_map: dict | None = None` to `train_and_predict`, document how it flows into preprocessing, and add a plumbing test.

2. **HIGH-B — `_carve_calib_from_train_tail` typo + no deterministic test.**
   VERIFIED: 05-05 line 94 reads "train_start は calib_start-1day に短縮" — should be `train_end` (you carve calib from the *tail* of train, so train's *end* moves back, not its start). No test asserts the carve is deterministic for BT-1..BT-5 or that it satisfies `max(train)<min(calib)<max(calib)<min(test)`. Fix: correct the typo, add `_carve_calib_from_train_tail` unit test across all 5 BT windows.

3. **HIGH-C — HARAI join treats race-level slot records as horse-level.**
   VERIFIED: 05-05 line 108 merges `harai_pay_df[['race_key','umaban', ...pay_cols...]]` on `on=['race_key','umaban']`. RESEARCH §2 (lines 221-222) confirms HARAI is **one row per race** with `PayFukusyoUmaban1..5` + `PayFukusyoPay1..5` slot columns — there is no `umaban` column on raw HARAI. 05-03's `_lookup_payfukusyo_pay(row)` already does slot lookup correctly *within a row*, so HARAI must be joined **race-level** (one row per race, broadcast to that race's horse rows via `validate='many_to_one'`), OR pre-expanded to horse-level (one row per paying umaban) before the horse-level merge. The current `on=['race_key','umaban']` contract is unimplementable against raw HARAI.

### Actionable MEDIUM/LOW concerns (not yet incorporated into PLAN.md)

- **MEDIUM-A** — Pipeline drops non-selected candidates before `load_backtest`, breaking MEDIUM-04 auditability. Fix: 05-05 must build a full candidate table (selected + non-selected with `odds_missing_reason`) and pass that to `load_backtest`, not just `selected_with_accounting`.
- **MEDIUM-B** — JODDS coverage gate is race-level; should be horse-level usable-odds coverage per `BT window × policy`.
- **MEDIUM-C** — `merge_asof` multi-race sort-order test missing.
- **MEDIUM-D** — 特払 special-payout HARAI fixture + assertion missing.
- **LOW-A** — 05-01 test-count "6件" vs 7 listed tests drift.

### Divergent Views

N/A — single reviewer this cycle. The orchestrator independently verified all 3 NEW HIGHs and all 5 MEDIUMs against the revised PLAN files and the live `src/model/orchestrator.py`, confirming they are genuine gaps (not misreadings).

### Recommended next step

`/gsd-plan-phase 5 --reviews` → incorporate the 3 cycle-2 HIGHs as concrete plan changes:
- **05-04**: add `category_map` parameter to `train_and_predict` + plumbing test (HIGH-A).
- **05-05**: fix `_carve_calib` typo + add carve determinism test (HIGH-B); fix HARAI join to race-level `validate='many_to_one'` or pre-expand (HIGH-C); rework candidate persistence to keep non-selected rows (MEDIUM-A); strengthen coverage gate to horse-level (MEDIUM-B).

Then proceed to `/gsd-execute-phase 5`.

---

## Verification coverage (cycle 2)

| Cycle-2 HIGH concern | Source location (verified) | Affected plans |
|---|---|---|
| HIGH-A — orchestrator `category_map` param missing | `src/model/orchestrator.py:154` (no `category_map`); 05-04 lines 24/40/104/117 (only `split_periods`); 05-05 line 97 (assumes `category_map=` kwarg) | 05-04 (add param+test), 05-05 (consumer) |
| HIGH-B — `_carve_calib` typo + no determinism test | 05-05 line 94 ("train_start は calib_start-1day に短縮" — should be `train_end`); no `_carve_calib` test in acceptance | 05-05 |
| HIGH-C — HARAI join shape mismatch | 05-05 line 108 (`on=['race_key','umaban']` on HARAI); RESEARCH §2 lines 221-222 (HARAI = race-level slot records, no `umaban` col) | 05-05 (and 05-03 `_lookup_payfukusyo_pay` already correct within-row) |

| Cycle-2 MEDIUM concern | Affected plans | PLAN.md change still needed |
|---|---|---|
| MEDIUM-A — non-selected candidates dropped before load | 05-05 lines 107/113 | Build full candidate table (selected + non-selected w/ `odds_missing_reason`) and load that; add `test_load_backtest_persists_nonselected` |
| MEDIUM-B — coverage gate race-level not horse-level | 05-05 line 117 | Change `_assert_jodds_coverage` to measure horse-level usable-odds coverage per `BT × policy`; raise threshold default if needed |
| MEDIUM-C — `merge_asof` multi-race sort test missing | 05-03 | Add `test_odds_snapshot_multi_race` covering ≥2 races with overlapping `happyo_datetime` |
| MEDIUM-D — 特払 HARAI fixture + assertion missing | 05-03 | Add real HARAI-shaped 特払 fixture asserting payout/refund treatment |
| LOW-A — 05-01 test-count drift | 05-01 line 118 | Correct "6件" → "7件" (or align behavior list) |

---

## Orchestrator source-grounding (cycle 2)

Existing Phase-4-and-earlier symbols that the revised plans depend on / extend:

| Symbol | Kind | Verdict | Evidence |
|---|---|---|---|
| `src/model/orchestrator.py::train_and_predict` signature | function | VERIFIED + GAP | `src/model/orchestrator.py:154` — has `as_of_datetime: datetime \| None = None` (Phase 4), does **NOT** have `category_map`. PLAN 05-04 extends it with `split_periods` only; PLAN 05-05 calls it with `category_map=`. → HIGH-A |
| `src/model/data.py::split_3way` | function | VERIFIED | `src/model/data.py:502` — PLAN 05-04 `periods` extension target is real |
| `src/ev/*`, `src/db/backtest_load.py`, `BTWindow`/`BT_WINDOWS`/`get_bt_race_ids`, `REPORT_COLUMNS`/`BACKTEST_COLUMNS` | NEW artifacts | DECLARED NEW | produced by this phase (not pre-existing) — no hard-block |
| `pandas.merge_asof(direction='backward', by=...)`, `mlxtend.evaluate.GroupTimeSeriesSplit`, `CalibratedClassifierCV(cv='prefit')`, CatBoost `has_time=True` | upstream APIs | UNCHECKABLE under grep | well-known upstream APIs, no project-symbol hard-block |

Result: **0 MISSING existing-project symbols** → no hard-block. The 3 cycle-2 HIGHs are integration-layer logic/contract defects (missing orchestrator parameter, carve typo, HARAI shape mismatch), not hallucinated symbol references, so they route to the revision loop rather than aborting the cycle.

---

## Cycle-over-cycle delta

| Metric | Cycle 1 | Cycle 2 |
|---|---|---|
| HIGH severity (unresolved) | 5 | 3 |
| Actionable MEDIUM/LOW (unresolved) | 8 | 5 |
| Fully resolved HIGHs | 0 | 4 (HIGH-1/2/3/4) |
| Partially resolved HIGHs | 0 | 1 (HIGH-5 → HIGH-A) |

Net progress: 4 of 5 cycle-1 HIGHs fully closed; HIGH-5 narrowed from "category-map refit not an acceptance criterion" to "orchestrator `category_map` parameter plumbing unspecified" (a smaller, more actionable gap). 3 NEW HIGHs surfaced in the integration layer (05-05 `run_backtest.py`) that were not visible in cycle 1 because cycle 1 focused on the per-module contracts (05-03/04) before the integration script existed in reviewable form.
