---
phase: 7
reviewers: [codex]
reviewed_at: 2026-06-24T05:58:36Z
plans_reviewed:
  - 07-01-PLAN.md
  - 07-02-PLAN.md
  - 07-03-PLAN.md
cycle: 1
---

# Cross-AI Plan Review — Phase 7

> Reviewers invoked: Codex (codex-cli 0.139.0). Gemini / Cursor / Qwen / Antigravity / CodeRabbit not installed. Claude self-CLI skipped per independence rule (running inside Claude Code). OpenCode available but not requested (`--codex` flag only).

## Codex Review

### Summary

The three-wave plan is generally coherent and traceable to UI-01, OUT-01, and OUT-02. The strongest part is the contract-first approach: pinned CSV columns, read-only checks, Streamlit API guardrails, and explicit handling of the 14-vs-16 backtest CSV erratum. The main risk is Wave 2: it introduces nontrivial data assembly for predictions, odds snapshots, EV/rank recomputation, labels, race timestamps, and stamps, but several column-name and source-of-truth details are still under-specified or inconsistent. If those are not tightened before implementation, Wave 3 can render a polished UI over incorrect or missing data.

### 07-01-PLAN.md

**Strengths**

- Good foundation wave: `src/ui/csv_columns.py`, `jyocd_map.py`, Streamlit dependency, theme config, and tests are appropriate prerequisites for later plans.
- Correctly treats `BACKTEST_CSV_COLUMNS` as 16 columns and locks this with tests.
- Good use of `src/config/code_tables.yaml` for `jyocd` mapping instead of duplicating a UI dict.
- Read-only and Streamlit API tests are useful early tripwires for later waves.
- Segment JSON schema contract is a good bridge from Phase 6 to Phase 7.

**Concerns**

- **MEDIUM:** `must_haves` says reproducibility stamp "5項目" must be included in constants, but `PREDICTION_CSV_COLUMNS` only has four of the five: no `backtest_strategy_version`. This is okay for OUT-01 if requirements omit it, but the wording is contradictory.
- **MEDIUM:** `csv_columns.py` docstring is planned to say `odds_snapshot_at` comes from "backtest テーブル JOIN", which conflicts with later corrected guidance that it comes from JODDS `select_odds_snapshot`.
- **LOW:** `test_streamlit_api_usage.py` may be awkward if it requires every `st.dataframe` call to have `selection_mode`. Only the race-list dataframe should require selection; detail/scalar tables should not.
- **LOW:** `test_readonly_guarantee.py` keyword scanning can produce false positives if comments/docstrings contain SQL words like `update`.

**Suggestions**

- Clarify stamp policy:
  - Prediction CSV: four prediction stamps plus `prediction_created_at`.
  - UI row display: five stamps including `backtest_strategy_version`.
  - Backtest CSV: `backtest_strategy_version` but not `model_version`/`feature_snapshot_id`.
- Remove or correct the "backtest JOIN" mention in `csv_columns.py` docstring.
- Make `test_streamlit_api_usage.py` target only explicitly marked selectable dataframes, for example by checking `selection_mode` appears at least once and `selection=` appears nowhere.
- Keep read-only keyword checks focused on SQL string literals, or accept known false-positive exceptions for comments.

**Risk Assessment:** **LOW to MEDIUM.** The wave is mostly contracts and scaffolding. Risk is mainly inconsistency in wording around stamps and odds-source documentation, not core implementation.

### 07-02-PLAN.md

**Strengths**

- Correctly rejects the earlier "backtest JOIN for odds" path and uses JODDS snapshot plus `compute_ev_and_rank`.
- Good emphasis on `is_primary = true`, parameterized SQL, `dsn_masked`, and fail-loud CSV column assertions.
- UI and CLI sharing `src/ui/loaders.py` and `src/ui/csv_columns.py` is the right DRY boundary.
- UTF-8 BOM + CRLF is explicitly tested, which is important for Excel-JP workflows.

**Concerns**

- **HIGH:** Column naming is inconsistent: plans alternate between `fuku_odds_lower/upper` and `fukusho_odds_lower/upper`. OUT-01 columns are `fukusho_odds_lower/upper`, while JODDS/EV references use `fuku_odds_lower/upper`. This needs an explicit rename step.
- **HIGH:** `race_start_datetime` source is not specified enough. `select_odds_snapshot` needs race start times, but the plan does not clearly identify the table/JOIN that provides them.
- **HIGH:** `race_id` construction is under-specified. CSV and UI require `race_id`, but loaders mainly discuss RACE_KEY parts. Define the exact formatter once.
- **HIGH:** `backtest_strategy_version` in prediction UI is hand-waved as "latest backtest" or default `fukusho_ev_v1`. That can silently misrepresent provenance if multiple strategies/policies exist.
- **MEDIUM:** Creating and closing a `ConnectionPool` inside Streamlit app reruns conflicts with cache effectiveness. Since `@st.cache_data` keys on `ConnectionPool: id`, a new pool id per rerun means frequent cache misses.
- **MEDIUM:** `@st.cache_data` for DB reads without TTL or manual refresh can show stale live DB results. That may be acceptable, but should be explicit.
- **MEDIUM:** AST test requiring every `cur.execute` to have a second arg can reject valid static parameterless SELECTs, while still not fully proving SQL injection safety.
- **MEDIUM:** CLI scripts import Streamlit-decorated loader functions. This can work, but it couples batch export to Streamlit runtime behavior and cache decorators.
- **LOW:** `assert` for production fail-loud CSV validation can be disabled under `python -O`. Prefer explicit `if missing: raise ValueError`.

**Suggestions**

- Add a mapping section in `load_predictions`:
  - JODDS/internal: `fuku_odds_lower`, `fuku_odds_upper`
  - CSV/UI: `fukusho_odds_lower`, `fukusho_odds_upper`
- Define helpers:
  - `build_race_id(year, jyocd, kaiji, nichiji, racenum) -> str`
  - `format_period(start, end) -> str`
  - `normalize_prediction_export_columns(df) -> DataFrame`
- Specify the source for `race_start_datetime` and test that the resulting prediction export contains no nulls for required fields unless there is an explicit missing-data policy.
- Do not infer `backtest_strategy_version` from "latest backtest" unless the UI labels it as a display context. Better: set a fixed strategy constant used by EV/rank recomputation, or include a separate `ev_strategy_version`.
- Use `st.cache_resource` for the pool in Streamlit, and keep `@st.cache_data` for pure data loads keyed by primitive filter args plus an explicit refresh/TTL.
- Replace `assert not missing` with `raise ValueError(...)`.
- Consider separating pure loader/export functions from Streamlit cache wrappers, so CLI does not depend on Streamlit caching.

**Risk Assessment:** **HIGH.** This is the critical wave. It must reconstruct prediction exports from multiple sources, and the current plan has unresolved practical seams around odds column names, race timestamps, race IDs, and `backtest_strategy_version` provenance.

### 07-03-PLAN.md

**Strengths**

- Strong alignment with UI-01: race list, per-horse detail, EV, odds, rank, stamps, filters, download buttons, and calibration tab are all covered.
- Correct Streamlit row selection API: `selection_mode="single-row"` and `on_select="rerun"`.
- Honest backtest warning is explicit and testable.
- Good explicit exclusion of Phase 2 UI items: wide bets, upset index, generated comments.
- Plotly calibration tab consumes Phase 6 JSON and includes scalar metrics, matching the Phase 6 handoff.

**Concerns**

- **HIGH:** `app.py` creates a pool and closes it in `finally` on every Streamlit rerun. With cached functions keyed by pool id, this can reduce cache value and may interact poorly with Streamlit rerun lifecycle.
- **HIGH:** UI test requires SC#1 columns `fuku_odds_lower/upper`, while CSV contract says `fukusho_odds_lower/upper`. This can let the UI and export diverge.
- **MEDIUM:** `st.date_input("日付範囲", [])` may not have stable return shape. Streamlit date range widgets usually need explicit tuple defaults or careful normalization.
- **MEDIUM:** Plan says derived race list should go through `@st.cache_data`, but also says not to use `session_state`. That is fine, but the task does not define a cached race-list helper. Recomputing from 22k rows is probably okay, but the text is inconsistent.
- **MEDIUM:** `st.dataframe` detail table plus `st.download_button(data=build_prediction_csv_bytes(horse_df))` exports only the selected race, while Phase success criteria may expect filtered prediction CSV export. The plan should state whether UI download is selected-race or current-filter export.
- **MEDIUM:** Tests are mostly AST/string checks. They confirm code shape, not that the app actually renders valid data with real schemas.
- **LOW:** "Rank S accent color" appears in human verification but not in implementation/test details. Streamlit dataframe row styling is not trivial with `st.dataframe`.

**Suggestions**

- Define Streamlit resource lifecycle clearly:
  - `@st.cache_resource def get_pool(): return make_pool(..., role="readonly")`
  - Do not close the pool each rerun; rely on process shutdown or add an explicit cleanup path.
- Standardize odds display/export names to `fukusho_odds_lower/upper` at UI and CSV boundary.
- Normalize date range in a helper:
  - empty -> no bounds
  - one date -> same-day range
  - two dates -> from/to
- Decide UI download scope:
  - selected race only, or
  - all currently filtered predictions.
  The phase wording suggests filtered prediction CSV may be more useful; selected-race CSV is acceptable only if documented.
- Add at least one lightweight integration test with mocked loader DataFrames that calls `render_prediction_tab` enough to catch missing column names.
- If rank coloring is required, specify the implementation path, e.g. `pandas.Styler` compatibility with `st.dataframe`, or downgrade it to non-blocking polish.

**Risk Assessment:** **MEDIUM.** The UI plan is well-scoped and mostly achievable, but it depends heavily on Wave 2 data correctness. Streamlit lifecycle and column-name mismatches are the main implementation risks.

### Overall Risk Assessment

**Overall risk: MEDIUM-HIGH.** The phase goals are achievable, and the plans are unusually thorough on contracts, CSV pinning, and read-only posture. The main risk is not UI complexity; it is data provenance and naming consistency in `src/ui/loaders.py`. Before execution, tighten four contracts: exact odds column rename, exact `race_id` formatter, exact `race_start_datetime` source, and exact meaning/source of `backtest_strategy_version` in prediction rows. Once those are fixed, the plan should be solid.

---

## Consensus Summary

Single-reviewer cycle (Codex). Consensus = Codex findings. A second independent reviewer (Gemini / Claude external / OpenCode) was not available this cycle; the planner may rerun `/gsd-review --gemini` or `--all` once another CLI is installed to cross-check the HIGHs below before execution.

### Agreed Strengths

- Contract-first scaffolding (pinned CSV columns, read-only guardrails, Streamlit API tripwires, 14-vs-16 backtest CSV erratum handling).
- DRY boundary: UI and CLI share `src/ui/loaders.py` + `src/ui/csv_columns.py`.
- Correct Streamlit row selection API and explicit Phase 2 UI exclusions.
- Plotly calibration tab cleanly consumes Phase 6 JSON.

### Agreed Concerns (highest priority)

The four HIGHs cluster around **one root cause: Wave 2 data-provenance contracts are under-specified**, which then propagates a matching HIGH into Wave 3.

1. **[HIGH] Odds column-name drift** (`fuku_odds_lower/upper` vs `fukusho_odds_lower/upper`) — appears in both Wave 2 and Wave 3; UI test contract and CSV contract currently disagree. Without an explicit rename/normalization step the UI can pass while the exported CSV is wrong (or vice versa).
2. **[HIGH] `race_start_datetime` source undefined** — `select_odds_snapshot` needs race start times but the JOIN/table is not pinned. Risk of nulls or wrong snapshot rows.
3. **[HIGH] `race_id` formatter not pinned** — loaders discuss RACE_KEY parts but never the single canonical formatter; CSV/UI both need `race_id`.
4. **[HIGH] `backtest_strategy_version` provenance** — "latest backtest" / default `fukusho_ev_v1` inference can silently mislabel reproducibility provenance when multiple strategies/policies exist.
5. **[HIGH] Streamlit `ConnectionPool` lifecycle** — pool created + closed per rerun defeats `@st.cache_data` (keyed on pool `id`); also flagged independently in Wave 3 `app.py`.

### Divergent Views

Not applicable (single reviewer). Flag for re-review: items 1-4 are exactly the kind of cross-cutting contract a second reviewer should confirm before `/gsd-execute-phase`.

---

## Verification Coverage

The source-grounding requirement is satisfied by the artifact paths and section references above. All HIGH/MEDIUM/LOW findings cite specific plan files (`07-01-PLAN.md`, `07-02-PLAN.md`, `07-03-PLAN.md`) and concrete symbols (`PREDICTION_CSV_COLUMNS`, `BACKTEST_CSV_COLUMNS`, `csv_columns.py`, `load_predictions`, `select_odds_snapshot`, `compute_ev_and_rank`, `app.py`, `render_prediction_tab`, `@st.cache_data`, `@st.cache_resource`).
