---
phase: 7
reviewers: [codex]
reviewed_at: 2026-06-24T07:58:00Z
plans_reviewed:
  - 07-01-PLAN.md
  - 07-02-PLAN.md
  - 07-03-PLAN.md
cycle: 3
cycle_1_high_count: 5
cycle_1_actionable_count: 10
cycle_2_high_count: 2
cycle_2_actionable_count: 7
---

# Cross-AI Plan Review — Phase 7 (Cycle 3, Final Convergence Verification)

> **Cycle 3 of 3 (final) in a plan-review-convergence loop.** Cycle 1 (commit 4f9b988, Codex) found 5 HIGH + 10 actionable. Cycle 2 (commit cae1c38, Codex) verified cycle-1 resolved but found the cycle-1 revision (a8ed494) had introduced NEW internal contradictions (2 HIGH + 7 actionable: NEW-H1/H2/M1/M2/M3/M5/L1/L2). The planner did a target fix in commit `abf2d6a` to incorporate all cycle-2 NEW concerns. **This cycle verifies the cycle-2 NEW concerns are actually resolved in the revised PLAN.md AND surfaces any NEW concerns the cycle-3 revision itself introduced.**
>
> Reviewers invoked: Codex (codex-cli 0.139.0, model gpt-5.5). Gemini / Cursor / Qwen / Antigravity / CodeRabbit not installed. Claude self-CLI skipped per independence rule. OpenCode available but not requested (`--codex` flag only).
>
> **Methodology:** Codex's cycle-3 pass was independently re-verified by the orchestrator against the revised PLAN.md text AND the live source contracts (`src/ev/odds_snapshot.py`, `src/model/data.py`, `src/ev/ev_rank.py`, `src/db/schema.py`, `src/db/backtest_load.py`). Every verdict cites a concrete anchor; every NEW concern was confirmed by reading the cited source file line-by-line. **The orchestrator independently arrived at the same 3 findings as Codex before reading Codex's output — the two passes corroborate each other.**

## Codex Review (Cycle 3)

### Verdict

**Cycle 3 is NOT converged.** 7 of the 8 cycle-2 NEW concerns are fully resolved into PLAN.md structure (tasks / actions / acceptance_criteria / must_haves / threat-model / prohibitions / artifacts). But the target fix for NEW-M3 introduced a **HIGH-severity factual error against the live source contract**: PLAN.md now claims the existing `race_key` is 6-segment (`year-monthday-jyocd-kaiji-nichiji-racenum`), while the actual codebase explicitly uses a 5-segment canonical form and documents the 6-segment form as a deprecated bug that caused "オッズ全件 NaN 化". Two smaller stale-wording spots from the NEW-M2 / NEW-L2 fixes also remain in trust-boundary prose and Test 4 behavior spec. None re-opens a cycle-1 or cycle-2 HIGH at the contract level, but the factual error must be corrected before `/gsd-execute-phase`.

### Cycle-2 NEW Concern Resolution (verified against revised PLAN.md + live codebase)

| ID | Severity | Status | Evidence (PLAN.md anchor + source verification) |
|---|---|---|---|
| NEW-H1 | HIGH | FULLY RESOLVED | `07-02-PLAN.md` L26 (`must_haves.truths`) pins the `--odds-snapshot-policy` CLI flag with default/choices and the `load_predictions(..., odds_snapshot_policy=args.odds_snapshot_policy)` hand-off; L158 (artifacts), L277 (Test 6), L287 (parse_args action: `--odds-snapshot-policy` + `choices=["30min_before","10min_before"]`), L288 (`main` passes `odds_snapshot_policy=args.odds_snapshot_policy`), L311/L315/L316 (acceptance grep gates). §11.2 hindsight-odds ban honored. |
| NEW-H2 | HIGH | FULLY RESOLVED | `07-03-PLAN.md` L339 (checkpoint:human-verify step 6) now reads `fukusho_odds_lower/fukusho_odds_upper` and explicitly annotates "NEW-H2: 内部名 `fuku_odds_*` でなく外部 canonical 名 `fukusho_odds_*`". Matches column_config (L209), Test 5b (L276), Test spec (L293). The stale internal-name reference is gone. |
| NEW-M1 | MEDIUM | FULLY RESOLVED | `07-02-PLAN.md` L200 declares the pure/cached separation; L204/L217/L221 define `load_predictions`/`load_backtests`/`load_segment_json` as **pure functions** (`@st.cache_data` なし); L223-L226 define the three `*_cached` wrappers with `@st.cache_data(hash_funcs={ConnectionPool: id})`; L286 CLI imports the pure `load_predictions`. The decoration contradiction is gone. |
| NEW-M2 | MEDIUM | PARTIALLY RESOLVED — 2 stale spots remain | Core locations fixed: L33 (`must_haves`), L228 (`build_prediction_csv_bytes` action), L275 (Test 4), L342 (T-07-09), L351 (verification) all say `raise ValueError`/`ValueError`. **BUT** L331 (Trust Boundary "DB→CSV bytes" prose) and `07-03-PLAN.md` L369 (Trust Boundary "UI→CSV bytes" prose) still say `PREDICTION_CSV_COLUMNS/BACKTEST_CSV_COLUMNS の assert で列欠落を fail-loud`. The word `assert` here is descriptive (not an instruction to use the `assert` statement), but an executor could read it as license to use `assert`. → raised as C3-NEW-M1 below. |
| NEW-M3 | MEDIUM | PARTIALLY RESOLVED — factual error introduced | `07-02-PLAN.md` L201 now states a `race_id` vs `race_key` relationship (the *intent* — display label vs join key separation — is correct and valuable). **BUT** the stated source contract is factually wrong: it claims existing `race_key` is **6-segment** `year-monthday-jyocd-kaiji-nichiji-racenum` and cites `src/ev/odds_snapshot.py L93`. Live code says the opposite. → raised as C3-NEW-H1 below. |
| NEW-M5 | MEDIUM | FULLY RESOLVED | `07-03-PLAN.md` L305 scopes `test_dataframe_uses_selection_mode` to the race-list master dataframe (`race_list_df` を第一引数に取る `st.dataframe` Call) and explicitly excludes detail/scalar/backtest dataframes. LOW-1 re-introduction avoided. |
| NEW-L1 | LOW | FULLY RESOLVED | `07-02-PLAN.md` L157 makes `normalize_date_range` single-home in `src/ui/loaders.py`; `07-03-PLAN.md` L131 (artifacts), L187 (imports), L201 (action), L252-L253 (acceptance grep gates: `from src.ui.loaders import normalize_date_range` required + `! grep 'def normalize_date_range' src/ui/app.py`). Duplicate definition structurally prevented. |
| NEW-L2 | LOW | PARTIALLY RESOLVED — Test 4 behavior spec stale | Acceptance contradiction fixed: L253 now carries the static-SELECT exception matching L237 (action). **BUT** L194 (Test 4 behavior spec) still describes the check as "AST で `cur.execute` Call の第二引数 args の存在を検証" unconditionally — without the `%s`/`WHERE`/`VALUES` carve-out. An executor writing Test 4 from the behavior spec alone would over-reject parameterless static SELECTs. → raised as C3-NEW-L1 below. |

### NEW Concerns Introduced by the Cycle-3 Revision

| ID | Severity | Concern | Location | PLAN.md change still needed |
|---|---|---|---|---|
| C3-NEW-H1 | HIGH | **Factual source-contract error.** The NEW-M3 fix (`07-02-PLAN.md` L201) states the existing `race_key` is **6-segment** `year-monthday-jyocd-kaiji-nichiji-racenum` and cites `src/ev/odds_snapshot.py L93` as evidence. The live codebase says the opposite: `src/ev/odds_snapshot.py` L138-L143 constructs `race_key` via `make_race_key(df)` and documents the canonical form as **5-segment** `year-jyocd-kaiji-nichiji-racenum` (no `monthday`); the 6-segment (monthday-inserted) form is explicitly documented as the **old buggy implementation** that caused "実データでオッズ全件 NaN 化" (all-odds-NaN) and was unified away. `src/model/data.py` L182-L204 (`make_race_key`) returns `year-jyocd-kaiji-nichiji-racenum` — 5 elements, `monthday` absent. **Risk:** an executor following PLAN.md L201 literally may (a) construct `race_times.race_key` with `monthday` and silently break the JODDS `merge_asof` join (re-introducing the exact all-NaN-odds bug the codebase already fixed in CR-01), or (b) believe `race_id` and `race_key` are different formats when they are actually the same 5-segment form (so the "display vs join" distinction the PLAN draws is real in *role* but false in *format*). The design intent (display label vs join key) is correct; only the factual claim about the format is wrong. | `07-02-PLAN.md` L201 (NEW-M3 parenthetical); contradicted by `src/ev/odds_snapshot.py` L138-L145 and `src/model/data.py` L182-L204 | Rewrite the NEW-M3 parenthetical at L201 to: state `race_key` is **5-segment** `year-jyocd-kaiji-nichiji-racenum` (constructed by `src.model.data.make_race_key`, used by `src/ev/odds_snapshot.py`); note that `build_race_id` produces the **same 5-segment form** and the distinction is *role only* (`race_id` = human-readable CSV/UI display column derived in the loader; `race_key` = the existing join key consumed inside `select_odds_snapshot` / `compute_ev_and_rank`); delete the `monthday` claim and the L93 citation. One-sentence edit. |
| C3-NEW-M1 | MEDIUM | Stale `assert` wording in Trust Boundary prose. The NEW-M2 fix replaced `assert`/`AssertionError` with `raise ValueError` in `must_haves`/action/threat T-07-09/verification, but two Trust Boundary rows still describe the column check as "`... の assert で列欠落を fail-loud`". An executor could read this as license to use the `assert` statement, reintroducing the `python -O` silent-disable risk NEW-M2 was meant to close. | `07-02-PLAN.md` L331 (Trust Boundary "DB→CSV bytes"); `07-03-PLAN.md` L369 (Trust Boundary "UI→CSV bytes") | Replace `assert` with "必須列検証（`raise ValueError`）" in both Trust Boundary rows so the descriptive prose matches the implemented `raise ValueError`. |
| C3-NEW-L1 | LOW | Test 4 behavior spec still contradicts the action/acceptance static-SELECT exception. L194 (behavior) says the AST check verifies "第二引数 args の存在" for every `cur.execute` call, with no carve-out; L237 (action) and L253 (acceptance) correctly allow parameterless static SELECTs (`%s`/`WHERE`/`VALUES` absent). An executor writing Test 4 from the behavior block alone would over-reject legitimate static SELECTs and the test would fail against correct code. | `07-02-PLAN.md` L194 (Test 4 behavior) | Reword L194 to mirror L237/L253: "第二引数 args は SQL が `%s`/`WHERE`/`VALUES` を含む場合に必須・それ以外の parameterless 静的 SELECT は省略可（文字列結合 BinOp は全ケースで禁止）". |

### Cross-Plan Consistency

External contract is consistent and correct across all 3 plans:
- External CSV/UI odds columns: `fukusho_odds_lower` / `fukusho_odds_upper` (all 3 plans, all tests, checkpoint).
- Internal JODDS/EV columns: `fuku_odds_lower` / `fuku_odds_upper` (matches `src/ev/ev_rank.py` L109-110, `src/ev/odds_snapshot.py` L211/L323).
- Bridge helper: `normalize_prediction_export_columns` (rename map pinned at `07-02` L154/L210).
- CLI flag: `--odds-snapshot-policy` (NEW-H1 resolved).
- Strategy version: `EV_STRATEGY_VERSION = "fukusho_ev_v1"` (matches `src/db/schema.py` L189 CHECK).
- Loader/cached-wrapper separation: clean (NEW-M1 resolved).

Inconsistent spots to fix before execution: C3-NEW-H1 (race_key format factual error), C3-NEW-M1 (2 Trust Boundary `assert` wording), C3-NEW-L1 (Test 4 behavior spec). All are one-line edits.

### Overall Risk Assessment

**Overall risk: LOW.** All cycle-1 HIGHs (5) and cycle-2 NEW HIGHs (2) are resolved at the contract level. The single remaining HIGH (C3-NEW-H1) is a **one-sentence factual correction** — the design intent is right, only the cited format is wrong, and the machine-checked contracts (grep gates, AST tests) do not reference the wrong format. The two actionable items (C3-NEW-M1/M-l, C3-NEW-L1) are doc/spec wording alignment. None of these blocks execution in the sense of requiring re-architecture; they block execution in the sense that an executor reading the wrong line could introduce a subtle bug (C3-NEW-H1) or a false-positive test failure (C3-NEW-L1). The codebase contracts (`ev_rank.py`, `odds_snapshot.py`, `model/data.py`, `schema.py`) were independently verified line-by-line by both Codex and the orchestrator.

---

## Consensus Summary

Single-reviewer cycle (Codex cycle 3 + orchestrator independent verification). The orchestrator's independent pass produced the identical 3 findings (C3-NEW-H1/M1/L1) with the same severity assignments and the same cited source-line evidence before reading Codex's output. Consensus = unanimous between the two passes.

### Agreed Strengths (carry-over, confirmed intact)

- All 5 cycle-1 HIGHs remain resolved at the contract level (must_haves / artifacts / threat-model / prohibitions).
- 6 of 8 cycle-2 NEW concerns fully resolved (NEW-H1/H2/M1/M5/L1 + the actionable subset of M2/M3/L2).
- CLI flag provenance (`--odds-snapshot-policy`), pure/cached loader separation, single-home `normalize_date_range`, external canonical `fukusho_odds_*` naming — all structurally pinned.
- Codebase contracts independently verified: `src/ev/ev_rank.py` L109-110 (consumes `fuku_odds_*`), `src/ev/odds_snapshot.py` L138-L145/L211/L213/L323-L326 (5-segment `race_key` via `make_race_key` + returns `fuku_odds_*` + `odds_snapshot_at` from `happyo_datetime`), `src/model/data.py` L182-L204 (`make_race_key` = 5-segment), `src/db/schema.py` L32/L148/L182/L189 (`n_race` / CHECK `backtest_strategy_version = 'fukusho_ev_v1'` / `odds_snapshot_at`), `src/db/backtest_load.py` L77-L116 (no `fuku_odds_*`).

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 | Cycle 2 | Cycle 3 |
|---|---|---|---|
| HIGHs at contract level | 5 | 0 (all 5 resolved) | 0 |
| NEW HIGHs introduced by revision | — | 2 (NEW-H1/H2) | **1** (C3-NEW-H1 — factual error in the NEW-M3 fix) |
| Actionable MEDIUM/LOW unresolved | 10 | 7 | **2** (C3-NEW-M1 Trust Boundary `assert` wording; C3-NEW-L1 Test 4 behavior spec) + 2 PARTIALLY RESOLVED cycle-2 items whose partial state is exactly C3-NEW-M1/C3-NEW-L1 |

The convergence is nearly complete: 7/8 cycle-2 NEW concerns are fully resolved, and the remaining work is three one-line edits (one factual correction, two wording alignments). C3-NEW-H1 is classified HIGH because a wrong source-format claim can trigger the exact all-NaN-odds regression the codebase already fixed, but it is a one-sentence doc fix — no re-architecture.

### Divergent Views

Not applicable (single reviewer + orchestrator independent verification, unanimous).

---

## Verification Coverage

The source-grounding requirement is satisfied by artifact paths and line references throughout. Cycle-2 resolution verdicts cite concrete PLAN.md anchors: `must_haves.truths` (`07-02` L26/L33, `07-03` L24/L25), `<artifacts_this_phase_produces>` (`07-02` L152/L157/L158, `07-03` L131), Task action steps (`07-02` L200/L201/L204/L217/L221/L223-L226/L228/L287/L288, `07-03` L187/L201/L305/L339), prohibitions (`07-02` L83-L88, `07-03` L70-L83), threat-model rows (T-07-09 `07-02` L342, T-07-11 L344, T-07-20 `07-03` L384), Trust Boundaries (`07-02` L331, `07-03` L369), behavior specs (`07-02` L194), and acceptance_criteria (`07-02` L253/L315/L316, `07-03` L252/L253). NEW concerns cite exact contradictory line numbers. **Codebase claims were verified line-by-line by both Codex and the orchestrator** against: `src/ev/odds_snapshot.py` L138-L145 (`race_key` = 5-segment via `make_race_key`, 6-segment documented as deprecated NaN-bug form) + L211/L213/L323-L326 (returns `fuku_odds_*` + `odds_snapshot_at` from `happyo_datetime`); `src/model/data.py` L182-L204 (`make_race_key` returns `year-jyocd-kaiji-nichiji-racenum`, 5 elements, no `monthday`); `src/ev/ev_rank.py` L109-L110 (consumes `fuku_odds_*`); `src/db/schema.py` L32 (`n_race`) + L148/L189 (CHECK `backtest_strategy_version = 'fukusho_ev_v1'`); `src/db/backtest_load.py` L77-L116 (BACKTEST_COLUMNS, no `fuku_odds_*`); commit `abf2d6a` diff (cycle-3 target fix scope).
