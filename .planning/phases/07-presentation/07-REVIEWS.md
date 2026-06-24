---
phase: 7
reviewers: [codex]
reviewed_at: 2026-06-24T06:41:07Z
plans_reviewed:
  - 07-01-PLAN.md
  - 07-02-PLAN.md
  - 07-03-PLAN.md
cycle: 2
cycle_1_high_count: 5
cycle_1_actionable_count: 10
---

# Cross-AI Plan Review — Phase 7 (Cycle 2, Convergence Verification)

> **Cycle 2 of a plan-review-convergence loop.** Cycle 1 (commit 4f9b988, Codex) found 5 HIGH + 10 actionable non-HIGH concerns. The planner revised all three PLAN.md files in commit a8ed494 to incorporate them. This cycle verifies each cycle-1 concern is resolved in PLAN.md **structure** (task / action / acceptance_criteria / verify / must_haves / threat-model / artifact / explicit-deferral — not just prose acknowledgment) and surfaces NEW concerns the revision introduced.
>
> Reviewers invoked: Codex (codex-cli 0.139.0, model gpt-5.5). Gemini / Cursor / Qwen / Antigravity / CodeRabbit not installed. Claude self-CLI skipped per independence rule (running inside Claude Code). OpenCode available but not requested (`--codex` flag only).
>
> **Methodology:** Codex's cycle-2 pass was independently verified by the orchestrator against the revised PLAN.md text and the live codebase contracts (`src/ev/ev_rank.py`, `src/ev/odds_snapshot.py`, `src/db/schema.py`, `src/db/backtest_load.py`, `docs/keiba_ai_requirements_v1.3.md` §16.2). Every FULLY/PARTIALLY verdict below cites a concrete PLAN.md anchor; every NEW concern was confirmed by grep against the revised files.

## Codex Review (Cycle 2)

### Verdict

Cycle-2 revisions resolve most cycle-1 blockers at the artifact / must_haves / threat-model level. The remaining issues are **internal contradictions inside the revised PLAN.md itself** — places where the must_haves or threat-model says one thing and the task action / acceptance says another, or where a flag is declared in the artifact list but omitted from the CLI task body. These are exactly the kind of inconsistencies that `/gsd-execute-phase` executors resolve by guessing, and that tests then lock in the wrong choice. None re-open a cycle-1 HIGH at the contract level; they are NEW findings.

### Cycle-1 Concern Resolution (verified against revised PLAN.md)

#### 07-01-PLAN.md

| Cycle-1 Concern | Status | Evidence (PLAN.md anchor) |
|---|---|---|
| HIGH-1 odds name drift | FULLY RESOLVED | `must_haves.truths` row pins external `fukusho_odds_lower/upper`; `<artifacts_this_phase_produces> > docstring 方針` (L135) states internal `fuku_*` is normalized to external `fukusho_*` via `normalize_prediction_export_columns` and that `odds_snapshot_at` comes from JODDS `happyo_datetime` (not backtest JOIN). Task 2 Test 2 asserts the canonical name. |
| MEDIUM-1 stamp 5項目 wording | FULLY RESOLVED | `must_haves.truths` row (L28) explicitly distinguishes prediction-CSV 4 stamps + `prediction_created_at` from UI-row 5 stamps (adds `backtest_strategy_version`), and states `backtest_strategy_version` is excluded from CSV constants because the prediction table has no such column. |
| LOW-1 selection_mode on every dataframe | FULLY RESOLVED | Task 2 Test 6 (L190) defines a **relaxed** criterion: assert `selection_mode=` appears at least once and `selection=` appears nowhere — not "every `st.dataframe` must have `selection_mode`". |
| LOW-2 readonly keyword false positives | FULLY RESOLVED | Task 2 action step 5 (L211) restricts the readonly scan to **SQL string literals that are the first arg of `cur.execute`** (AST `ast.Constant` whose parent is a `cur.execute` Call), with a `# planner-discipline-allow:` escape hatch for the test's own keyword strings. |

#### 07-02-PLAN.md

| Cycle-1 Concern | Status | Evidence (PLAN.md anchor) |
|---|---|---|
| HIGH-1 odds name drift | FULLY RESOLVED | `must_haves.truths` (L23) + Step 2.5 (L209) + Step 3 ordering note (L210) + prohibition (L85) + artifact `normalize_prediction_export_columns` (L153). The rename runs **after** `compute_ev_and_rank` (which expects internal `fuku_*`), confirmed against `src/ev/ev_rank.py` L109-110. Threat T-07-11 covers the leak-safety rationale. |
| HIGH-2 `race_start_datetime` source | FULLY RESOLVED | Task 1 Step 2 (L206) pins the source to `normalized.n_race`, requires `race_times = race_times.dropna(subset=["race_start_datetime"])`, and marks `odds_snapshot_at` NULL rows with `odds_missing_reason="no_snapshot"`. Prohibition (L87) forbids silently leaving NULL rows. `normalized.n_race` confirmed present in `src/db/schema.py` L32. |
| HIGH-3 `race_id` formatter | FULLY RESOLVED | Artifact `build_race_id(year, jyocd, kaiji, nichiji, racenum) -> str` (L152); Task 1 action (L200) pins `_RACE_ID_DELIM = "-"`, 2-digit zero-pad, example `2024-01-05-01-09`; prohibition (L86) forbids alternate formatters. (See NEW-M3 below for a related cross-contract gap, but the formatter itself is pinned.) |
| HIGH-4 `backtest_strategy_version` provenance | FULLY RESOLVED | Artifact `EV_STRATEGY_VERSION = "fukusho_ev_v1"` (L154); Task 1 action (L201) explicitly forbids "latest backtest" inference; prohibition (L84) reinforces. Value confirmed against `src/db/schema.py` L189 CHECK constraint `backtest_strategy_version = 'fukusho_ev_v1'`. |
| HIGH-5 pool lifecycle | FULLY RESOLVED (in 07-03) | 07-02 defines `@st.cache_data(hash_funcs={ConnectionPool: id})` wrappers (L203); the rerun-close anti-pattern is resolved in 07-03 via `@st.cache_resource def get_pool()` (07-03 L129, L197, prohibition L80). Cross-plan handoff is explicit. |
| MEDIUM-3 static SELECT exception | PARTIALLY RESOLVED | Test 4 spec (L231) correctly carves the exception ("`%s` or `WHERE` or `VALUES` absent → second arg may be omitted"), **but** `must_haves.truths` (L29) and acceptance criterion (L247) still say "全 SQL が ... `cur.execute(sql, params)` を使用" / "全て第二引数を持つ" unconditionally — contradicting the test spec. See NEW-M2. |
| MEDIUM-4 CLI imports Streamlit-decorated loaders | PARTIALLY RESOLVED | Artifacts (L150) and Task 2 (L280) correctly say CLI imports the **pure** `load_predictions` (no `@st.cache_data`), but Task 1 action (L203) then defines `load_predictions` itself with `@st.cache_data(...)` decoration — same symbol name, contradictory decoration. See NEW-M1. |
| LOW-3 `assert` disabled under -O | PARTIALLY RESOLVED | Task 1 action (L223) and Test 4 (L269, L292) correctly use `raise ValueError`. **But** `must_haves.truths` (L32), threat T-07-09 (L334), and verification item 2 (L343) still say `assert` / `AssertionError`. See NEW-M2. |

#### 07-03-PLAN.md

| Cycle-1 Concern | Status | Evidence (PLAN.md anchor) |
|---|---|---|
| HIGH-1 odds name drift (propagated) | MOSTLY RESOLVED — one stale doc spot | `must_haves.truths` (L24, L25), Task 1 column_config (L209), Test 5b (L274), and Test spec (L291) all use `fukusho_odds_lower/upper`. **However** Task 3 `checkpoint:human-verify` step 6 (L337) still tells the human to verify `fuku_odds_lower/upper` in the UI — the internal name. See NEW-M4. |
| HIGH-5 pool lifecycle | FULLY RESOLVED | `artifacts_this_phase_produces` (L129) and Task 1 action (L197) define `@st.cache_resource def get_pool()`, prohibit rerun-close; prohibition (L80) and threat T-07-20 reinforce. |
| MEDIUM-2 TTL/refresh | FULLY RESOLVED | Task 1 sidebar action (L195) adds `st.button("キャッシュ更新")` → `st.cache_data.clear()`; prohibition (L81). |
| MEDIUM-5 date_input shape | FULLY RESOLVED | `normalize_date_range` helper (L201) handles empty / 1-date / 2-date; prohibition (L82). (Location duplicated vs 07-02 — see NEW-L1.) |
| MEDIUM-6 download scope | FULLY RESOLVED | Task 1 action (L211) pins scope to "選択レースのみ" with explicit `help=` text; prohibition (L83). |
| MEDIUM-7 integration test | FULLY RESOLVED | Task 2 Test spec `test_render_prediction_tab_with_mocked_df` (L300) uses `unittest.mock.patch` on `load_predictions_cached` + Streamlit `AppTest`/`patch("streamlit.dataframe")` to catch missing-column KeyErrors. |
| LOW-4 Rank S color path | FULLY RESOLVED | Task 1 action (L213) specifies `pandas.Styler` attempt with explicit fallback to `st.caption` and **non-blocking polish** designation (also reflected in Task 3 step 6 L338). |

### NEW Concerns Introduced by the Revision

| ID | Severity | Concern | Location | PLAN.md change still needed |
|---|---|---|---|---|
| NEW-H1 | HIGH | `--odds-snapshot-policy` is declared in the 07-02 artifact list (L157) and `must_haves` (L25, L102), **but Task 2's `parse_args` action body (L281) only lists `--output`/`--date-from`/`--date-to`/`--jyocd`** — the flag is missing from the argparse definition, and `main()` (L282) does not pass `odds_snapshot_policy=args.odds_snapshot_policy` to `load_predictions`. An executor following the task body literally will build a CLI that silently uses the loader default and cannot reproduce the 10min_before policy, undermining §11.2 (hindsight-odds ban) and OUT-01 provenance. | 07-02 Task 2 action (L281-283) | Add `--odds-snapshot-policy` (default `30min_before`, choices `30min_before`/`10min_before`) to `parse_args`, and pass `odds_snapshot_policy=args.odds_snapshot_policy` into `load_predictions(...)` in `main()`. Add a grep assertion in acceptance_criteria mirroring the existing `--date-from` check. |
| NEW-H2 | HIGH (downgradable to MEDIUM — see note) | 07-03 Task 3 `checkpoint:human-verify` step 6 (L337) instructs the human to verify `fuku_odds_lower/upper` (internal name) in the UI, contradicting the canonical external `fukusho_odds_lower/upper` pinned everywhere else (L24, L25, L209, L274, L291). A human following this checklist could sign off on a UI that displays the wrong column names. **Orchestrator note:** the machine-checked contracts (column_config Test 5b, acceptance grep) are correct, so the implementation will be right; only the human-verification document is stale. Classified HIGH by Codex because it can produce a wrong sign-off, but the orchestrator judges MEDIUM is more proportionate since no code/test references the stale name. Filed as HIGH to honor the cross-AI finding; the fix is a one-line doc edit. | 07-03 Task 3 step 6 (L337) | Change `fuku_odds_lower/upper` → `fukusho_odds_lower/upper` in the how-to-verify text. |
| NEW-M1 | MEDIUM | Pure-loader vs cached-wrapper contradiction on the symbol `load_predictions`. Artifacts (L150) and Task 1 intro (L199) declare `load_predictions` is a **pure** function (no `@st.cache_data`) with a separate `load_predictions_cached` wrapper. But Task 1 action (L203) then defines `@st.cache_data(...) 付き load_predictions(...)` — decorating the same name. An executor will not know whether to decorate. This re-opens MEDIUM-4 (CLI/Streamlit coupling) by ambiguity. | 07-02 Task 1 action (L203, L216) | Rename the decorated entry to `load_predictions_cached` in the action body (L203, L216) so it matches the artifact declaration (L150-151). The pure `load_predictions` must have no `@st.cache_data`. |
| NEW-M2 | MEDIUM | Failure-mode keyword is inconsistent between the action (which correctly says `raise ValueError`) and the must_haves / threat-model / verification block (which still say `assert` / `AssertionError`). Under `python -O` the assert form is stripped, so the threat-model row T-07-09 (L334) describes a protection that the action does not actually provide. | 07-02 must_haves (L32), threat T-07-09 (L334), verification item 2 (L343) | Replace `assert`/`AssertionError` with `raise ValueError`/`ValueError` in L32, L334, L343 so the threat model matches the implemented `raise ValueError`. |
| NEW-M3 | MEDIUM | `build_race_id` produces a **5-segment** id (`year-jyocd-kaiji-nichiji-racenum`, e.g. `2024-01-05-01-09`), but the existing `race_key` used throughout the codebase as the JODDS/EV join key (`src/ev/odds_snapshot.py` L93, `src/model/trainer.py` L744) is **6-segment**: `year-monthday-jyocd-kaiji-nichiji-racenum`. The PLAN never states how `race_id` (display) and `race_key` (join) relate — Step 2 (L205) says the snapshot is selected by `(race_key, umaban)`, but Step 1 builds `race_id` from `(year, jyocd, kaiji, nichiji, racenum)` without `monthday`. An executor cannot tell whether `race_id` is a truncated display label or whether `build_race_id` should include `monthday` to match `race_key`. Requirements §16.2 lists `race_id` as a column but does not define its format, so this is a design decision the PLAN must make explicit rather than leave ambiguous. | 07-02 Task 1 action (L200, L205) | Add one sentence to the `build_race_id` action (L200) stating the relationship: either (a) `race_id` is a display-only label and the JODDS join uses the existing `race_key` helper from `src/ev/odds_snapshot.py` (so `build_race_id` is purely cosmetic and must not be used as a join key), or (b) `build_race_id` must include `monthday` to match `race_key`. Recommend (a) and name the join-key source explicitly. |
| NEW-M5 | MEDIUM | 07-03 Task 2 `test_dataframe_uses_selection_mode` (L303) says "if any `st.dataframe` exists, require `selection_mode=`" — which re-introduces LOW-1 (forcing `selection_mode` on detail/scalar dataframes that should not be selectable). 07-01 correctly relaxed this, but 07-03's extension tightens it again. | 07-03 Task 2 action (L303) | Scope the assertion to the **race-list** dataframe only (e.g. by AST-identifying the `st.dataframe` whose result is assigned to `event`/uses `on_select="rerun"`), mirroring 07-01's relaxed criterion. |
| NEW-L1 | LOW | `normalize_date_range` helper location is inconsistent: 07-02 artifacts (L156) place it in `src/ui/loaders.py`; 07-03 artifacts (L130) and Task 1 action (L201) place it in `app.py`, with "duplicate helper language". Two definitions risk drift. | 07-02 L156 vs 07-03 L130/L201 | Pick one home (recommend `loaders.py` since CLI may also want it) and have the other import it. |
| NEW-L2 | LOW | 07-02 acceptance (L247) says "全て第二引数を持つ" unconditionally, contradicting the MEDIUM-3 static-SELECT exception in Test 4 (L231). | 07-02 acceptance_criteria (L247) | Reword to "全ての `cur.execute` が文字列結合でなく・`%s`/`WHERE`/`VALUES` を含む SQL は第二引数を持つ" to match Test 4. |

### Cross-Plan Consistency

Mostly consistent after the revision. The agreed external contract:

- External CSV/UI odds columns: `fukusho_odds_lower` / `fukusho_odds_upper` (all 3 plans, all tests).
- Internal JODDS/EV columns: `fuku_odds_lower` / `fuku_odds_upper` (matches `src/ev/ev_rank.py` L109-110, `src/ev/odds_snapshot.py` L211/L323).
- Bridge helper: `src.ui.loaders.normalize_prediction_export_columns` (rename map pinned).
- Canonical race formatter: `src.ui.loaders.build_race_id(year, jyocd, kaiji, nichiji, racenum)`.
- Strategy version source: `src.ui.loaders.EV_STRATEGY_VERSION = "fukusho_ev_v1"` (matches `src/db/schema.py` L189 CHECK).

Inconsistent spots to fix before execution: NEW-H1 (CLI flag), NEW-H2 (human-verify doc), NEW-M1 (loader decoration), NEW-M2 (assert vs ValueError), NEW-M5 (selection_mode scope).

### Overall Risk Assessment

**Overall risk: LOW-MEDIUM.** All 5 cycle-1 HIGHs are resolved at the contract level (must_haves / artifacts / threat-model / prohibitions). The remaining findings are internal PLAN.md contradictions that a careful executor could reconcile, but which `/gsd-execute-phase` will not catch on its own. None of them re-opens a cycle-1 HIGH. The highest-impact fix is NEW-H1 (`--odds-snapshot-policy` CLI flag), because it directly affects §11.2 reproducibility; the rest are doc/test-spec consistency edits. The codebase contracts (`ev_rank.py`, `odds_snapshot.py`, `schema.py`) were independently verified and match the PLAN's claims.

---

## Consensus Summary

Single-reviewer cycle (Codex cycle 2 + orchestrator verification). Consensus = Codex findings, each independently confirmed by grep against the revised PLAN.md and against the live source contracts.

### Agreed Strengths (carry-over from cycle 1, confirmed intact)

- Contract-first scaffolding survives: pinned CSV columns, readonly guardrails, Streamlit API tripwires, 14-vs-16 backtest CSV erratum handling.
- DRY boundary: UI and CLI share `src/ui/loaders.py` + `src/ui/csv_columns.py` (once NEW-M1 is resolved).
- Correct Streamlit row-selection API and explicit Phase 2 UI exclusions.
- Plotly calibration tab cleanly consumes Phase 6 JSON; trace-count test (W2) added.

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 | Cycle 2 |
|---|---|---|
| HIGHs at contract level | 5 (odds drift, race_start_datetime source, race_id formatter, strategy provenance, pool lifecycle) | **0** — all 5 resolved into must_haves/artifacts/threat-model/prohibitions |
| NEW HIGHs introduced by revision | — | 2 (NEW-H1 CLI flag omission; NEW-H2 human-verify stale name — H2 is a doc typo with correct machine contracts) |
| Actionable MEDIUM/LOW unresolved | 10 | 7 (NEW-M1/M2/M3/M5 + NEW-L1/L2 + the PARTIALLY RESOLVED MEDIUM-3/4 whose partial state is already captured as NEW-M1/NEW-L2) |

The convergence is real: the planner addressed every cycle-1 HIGH in PLAN.md structure. The remaining work is reconciliation of internal contradictions inside the revised PLAN.md (NEW-H1/M1/M2/M5 + NEW-L1/L2) plus the race_id vs race_key clarification (NEW-M3). None requires re-thinking the architecture.

### Divergent Views

Not applicable (single reviewer + orchestrator verification). The orchestrator independently confirmed each Codex finding against the PLAN.md text and the codebase; no disagreements.

---

## Verification Coverage

The source-grounding requirement is satisfied by the artifact paths and section references throughout. Cycle-1 resolution verdicts cite concrete PLAN.md anchors: `must_haves.truths` rows (L23-L32 in 07-02, L24-L25 in 07-03, L28 in 07-01), `<artifacts_this_phase_produces>` blocks (L135/L150-L156 in 07-02, L129/L130/L142-L148 in 07-03), Task action steps (07-02 L200/L201/L203/L206/L209/L223/L281, 07-03 L195/L197/L209/L211/L213/L337), prohibitions (07-02 L84-L87, 07-03 L80-L83), threat-model rows (T-07-09 L334, T-07-11 L336, T-07-20 L382), and acceptance_criteria (07-02 L247). NEW concerns cite the exact contradictory line numbers. Codebase claims were verified against `src/ev/ev_rank.py` L109-110 (consumes `fuku_odds_*`), `src/ev/odds_snapshot.py` L93/L211/L213/L323-L326 (returns `fuku_odds_*` + `odds_snapshot_at` from `happyo_datetime`), `src/db/schema.py` L32 (`n_race`) + L182 (`odds_snapshot_at`) + L189 (CHECK `backtest_strategy_version = 'fukusho_ev_v1'`), `src/db/backtest_load.py` L108-L111 (no `fuku_odds_*`), and `docs/keiba_ai_requirements_v1.3.md` §16.2 L1093-L1133 (race_id column listed, format undefined).
