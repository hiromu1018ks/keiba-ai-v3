---
phase: 7
reviewers: [codex]
reviewed_at: 2026-06-24T08:35:00Z
plans_reviewed:
  - 07-01-PLAN.md
  - 07-02-PLAN.md
  - 07-03-PLAN.md
cycle: 4
cycle_1_high_count: 5
cycle_1_actionable_count: 10
cycle_2_high_count: 2
cycle_2_actionable_count: 7
cycle_3_high_count: 1
cycle_3_actionable_count: 2
cycle_4_high_count: 0
cycle_4_actionable_count: 0
converged: true
---

# Cross-AI Plan Review — Phase 7 (Cycle 4, Convergence Verification — CONVERGED)

> **Cycle 4 (CONVERGED) of a plan-review-convergence loop, extended past MAX_CYCLES (3) with operator approval.** Cycle 3 (commit 56fb0df, Codex + orchestrator independent verification) found 3 remaining doc/prose inconsistencies (1 HIGH + 2 actionable — all 1-line edits): C3-NEW-H1 (race_key 6部→5部 factual error), C3-NEW-M1 (Trust Boundary `assert`→`raise ValueError`), C3-NEW-L1 (Test 4 behavior spec static-SELECT exception). The planner applied a cycle-4 target fix in commit `8ea7ba2` (3 edits across `07-02-PLAN.md` L194/L201/L331 and `07-03-PLAN.md` L369). **This cycle verifies the 3 cycle-3 concerns are actually resolved in the revised PLAN.md AND scans for any NEW concerns the cycle-4 revision itself introduced (4th revision — fresh contradictions watch).**
>
> Reviewers invoked: Codex (codex-cli 0.139.0, model gpt-5.5). Gemini / Cursor / Qwen / Antigravity / CodeRabbit not installed. Claude self-CLI skipped per independence rule. OpenCode available but not requested (`--codex` flag only).
>
> **Methodology:** Codex's cycle-4 pass was independently re-verified by the orchestrator against the revised PLAN.md text AND the live source contracts. The orchestrator read the full cycle-4 diff (commit 8ea7ba2), the affected PLAN.md lines (07-02 L194/L201/L228/L237/L253/L331, 07-03 L369), and re-verified every source contract line-by-line (`src/model/data.py` L182-204, `src/ev/odds_snapshot.py` L138-145/L211-214/L323-326, `src/ev/ev_rank.py` L109-110, `src/db/schema.py` L188-190). The orchestrator also scanned all remaining `assert` occurrences across the 3 PLAN.md files (25 hits) to confirm none are Trust-Boundary fail-loud mechanisms (all are pytest assertions, verify-command inline asserts, or the LOW-05 "presence assert" pattern name — none in the production CSV-missing-column code path). **The orchestrator independently arrived at the same verdict (converged, 0 NEW concerns) as Codex before reading Codex's output — the two passes corroborate each other.**

## Codex Review (Cycle 4)

### Verdict

**Cycle 4 is CONVERGED.** The three cycle-3 concerns are fully resolved in the revised PLAN text, and no new actionable contradiction was introduced by the cycle-4 edits. The edited `race_key` prose (07-02 L201) now matches the live 5-segment source contract (`year-jyocd-kaiji-nichiji-racenum`) and explicitly rejects the deprecated 6-segment `year-monthday-...` NaN-bug form. Both Trust Boundary rows (07-02 L331, 07-03 L369) now specify `raise ValueError` with the `python -O` rationale. Test 4 (07-02 L194) now consistently includes the static parameterless `SELECT` exception across behavior / action / acceptance text. The phase is ready for `/gsd-execute-phase`.

### Cycle-3 Concern Resolution (verified against revised PLAN.md + live codebase)

| ID | Severity | Status | Evidence (PLAN.md anchor post-cycle-4 + source verification) |
|---|---|---|---|
| C3-NEW-H1 | HIGH | FULLY RESOLVED | `07-02-PLAN.md` L201 now states `race_key` is **5-segment** `year-jyocd-kaiji-nichiji-racenum` and explicitly rejects the deprecated 6-segment `year-monthday-jyocd-kaiji-nichiji-racenum` form as the CR-01 "オッズ全件 NaN 化" bug. Source matches: `src/model/data.py` L182-204 documents and builds `(year,jyocd,kaiji,nichiji,racenum)` via `make_race_key` (5 elements, no `monthday`); `src/ev/odds_snapshot.py` L138-145 documents the 5-element/no-monthday canonical form and calls `make_race_key(df)` at L145. The stale L93 citation is gone; the new citation (`src/model/data.py::make_race_key` L195-205 + `src/ev/odds_snapshot.py` L138-145) is accurate. Design intent (race_id = display label, race_key = JOIN key — same 5-seg format, different role) now factually correct. |
| C3-NEW-M1 | MEDIUM | FULLY RESOLVED | `07-02-PLAN.md` L331 (Trust Boundary "DB→CSV bytes") now says `必須列検証（raise ValueError）で列欠落を fail-loud（NEW-M2: assert でなく raise ValueError・python -O でも無効化されない）`. `07-03-PLAN.md` L369 (Trust Boundary "UI→CSV bytes") carries the identical `raise ValueError` wording. Both rows now match the implemented action (L228 `raise ValueError`, L231 `raise ValueError`), T-07-09 (L342), and verification (L351). The `python -O` silent-disable risk NEW-M2 closed is now fully eliminated from all Trust Boundary prose. |
| C3-NEW-L1 | LOW | FULLY RESOLVED | Test 4 behavior at `07-02-PLAN.md` L194 now reads "AST で `cur.execute` Call を走査・**ただし `%s`/`WHERE`/`VALUES` を含まない parameterless 静的 SELECT（例: `SELECT 1`・`SELECT version()`・schema 問合せ）は第二引数 args の省略を許容**・文字列結合 BinOp は全ケースで禁止・action L237 / acceptance L253 の NEW-L2 例外と同一基準". This mirrors L237 (action) and L253 (acceptance) exactly. An executor writing Test 4 from the behavior block alone will no longer over-reject legitimate static SELECTs. |

### NEW Concerns Introduced by the Cycle-4 Revision

None. The cycle-4 target fix (commit `8ea7ba2`, 3 edits across 2 files) is narrow and surgical. The orchestrator independently scanned for:

1. **Stale `race_key`/`race_id`/`monthday`/6部 references** — only the corrected L201 mentions the 6-seg form, and only as the explicitly-rejected deprecated implementation. L96/L100 reference "RACE_KEY 7" which is the **physical PK column count** (`year/jyocd/kaiji/nichiji/racenum/umaban/kettonum` = 7 columns), a different concept from the 5-element `race_key` join string — no contradiction.
2. **Residual `assert` in fail-loud production paths** — all 25 remaining `assert` occurrences across the 3 PLAN.md files are (a) pytest assertions inside test functions, (b) `uv run python -c "...; assert ..."` verify-command inline checks, or (c) the "presence assert" LOW-05 pattern name. None are in the Trust Boundary CSV-missing-column code path that NEW-M2 closed.
3. **Cross-plan drift** — external canonical `fukusho_odds_*`, internal `fuku_odds_*`, `EV_STRATEGY_VERSION = "fukusho_ev_v1"` (matches `src/db/schema.py` L189 CHECK), `--odds-snapshot-policy` CLI flag, pure/cached loader separation — all remain consistent across 07-01/07-02/07-03.

The cycle-4 revision introduced zero new internal contradictions.

### Cross-Plan Consistency

External contract is consistent and correct across all 3 plans (re-confirmed post-cycle-4):
- External CSV/UI odds columns: `fukusho_odds_lower` / `fukusho_odds_upper` (all 3 plans, all tests, checkpoint).
- Internal JODDS/EV columns: `fuku_odds_lower` / `fuku_odds_upper` (matches `src/ev/ev_rank.py` L109-110, `src/ev/odds_snapshot.py` L211/L323).
- Bridge helper: `normalize_prediction_export_columns` (rename map pinned at `07-02` L154/L210).
- CLI flag: `--odds-snapshot-policy` (NEW-H1 resolved, unchanged by cycle-4).
- Strategy version: `EV_STRATEGY_VERSION = "fukusho_ev_v1"` (matches `src/db/schema.py` L189 CHECK).
- Loader/cached-wrapper separation: clean (NEW-M1 resolved, unchanged by cycle-4).
- `race_key` canonical form: 5-segment `year-jyocd-kaiji-nichiji-racenum` (C3-NEW-H1 resolved — now factually correct in PLAN.md L201 and matching `src/model/data.py` L182-204 / `src/ev/odds_snapshot.py` L138-145).

No inconsistent spots remain.

### Overall Risk Assessment

**Overall risk: LOW.** All cycle-1 HIGHs (5), cycle-2 NEW HIGHs (2), and cycle-3 NEW HIGH (1) are resolved at the contract level. The cycle-4 revision is three one-line doc/prose corrections that now align with the real codebase contracts. No re-architecture, no structural change, no new dependency. The phase is ready for `/gsd-execute-phase`.

---

## Consensus Summary

Single-reviewer cycle (Codex cycle 4 + orchestrator independent verification). The orchestrator's independent pass produced the identical verdict (converged, 0 NEW concerns, all 3 cycle-3 concerns FULLY RESOLVED) with the same cited source-line evidence before reading Codex's output. Consensus = unanimous between the two passes.

### Agreed Strengths (carry-over, confirmed intact through cycle 4)

- All 5 cycle-1 HIGHs remain resolved at the contract level (must_haves / artifacts / threat-model / prohibitions).
- All 2 cycle-2 NEW HIGHs (NEW-H1/H2) remain resolved.
- All 8 cycle-2 NEW concerns fully resolved (NEW-H1/H2/M1/M2/M3/M5/L1/L2).
- All 3 cycle-3 NEW concerns fully resolved (C3-NEW-H1/M1/L1).
- CLI flag provenance (`--odds-snapshot-policy`), pure/cached loader separation, single-home `normalize_date_range`, external canonical `fukusho_odds_*` naming, `race_key` 5-segment canonical form, `raise ValueError` fail-loud (no `assert` in production paths), Test 4 static-SELECT exception — all structurally pinned and factually accurate.
- Codebase contracts independently verified line-by-line by both Codex and the orchestrator: `src/ev/ev_rank.py` L109-110 (consumes `fuku_odds_*`), `src/ev/odds_snapshot.py` L138-L145/L211/L213/L323-L326 (5-segment `race_key` via `make_race_key` + returns `fuku_odds_*` + `odds_snapshot_at` from `happyo_datetime`), `src/model/data.py` L182-L204 (`make_race_key` = 5-segment), `src/db/schema.py` L32/L148/L182/L189 (`n_race` / CHECK `backtest_strategy_version = 'fukusho_ev_v1'` / `odds_snapshot_at`), `src/db/backtest_load.py` L77-L116 (no `fuku_odds_*`).

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 | Cycle 2 | Cycle 3 | Cycle 4 |
|---|---|---|---|---|
| HIGHs at contract level | 5 | 0 (all 5 resolved) | 0 | 0 |
| NEW HIGHs introduced by revision | — | 2 (NEW-H1/H2) | 1 (C3-NEW-H1 — factual error) | **0** |
| Actionable MEDIUM/LOW unresolved | 10 | 7 | 2 (C3-NEW-M1/L1) | **0** |
| Convergence status | Not converged | Not converged | Not converged (3 one-line edits) | **CONVERGED** |

The 4-cycle plan-review-convergence loop is complete. Total concerns raised and resolved: 5 HIGH + 10 actionable (cycle 1) → 2 HIGH + 7 actionable (cycle 2 NEW) → 1 HIGH + 2 actionable (cycle 3 NEW) → 0 NEW (cycle 4). All 20 concerns across the 4 cycles are now fully resolved with verification.

### Divergent Views

Not applicable (single reviewer + orchestrator independent verification, unanimous on convergence).

---

## Verification Coverage

The source-grounding requirement is satisfied by artifact paths and line references throughout. Cycle-3 resolution verdicts cite concrete post-cycle-4 PLAN.md anchors: `07-02-PLAN.md` L194 (Test 4 behavior — static-SELECT exception added), L201 (race_id/race_key — 5-seg factual correction with `src/model/data.py::make_race_key` L195-205 + `src/ev/odds_snapshot.py` L138-145 citations), L228/L231 (action `raise ValueError`), L237 (action static-SELECT exception), L253 (acceptance static-SELECT exception), L331 (Trust Boundary DB→CSV `raise ValueError`), `07-03-PLAN.md` L369 (Trust Boundary UI→CSV `raise ValueError`). **Codebase claims were verified line-by-line by both Codex and the orchestrator** against: `src/model/data.py` L182-204 (`make_race_key` returns `year-jyocd-kaiji-nichiji-racenum`, 5 elements, no `monthday`); `src/ev/odds_snapshot.py` L138-L145 (`race_key` = 5-segment via `make_race_key`, 6-segment documented as deprecated NaN-bug form); `src/ev/odds_snapshot.py` L211/L213/L323-L326 (returns `fuku_odds_*` + `odds_snapshot_at` from `happyo_datetime`); `src/ev/ev_rank.py` L109-L110 (consumes `fuku_odds_*`); `src/db/schema.py` L32/L148/L189 (`n_race` / CHECK `backtest_strategy_version = 'fukusho_ev_v1'`); `src/db/backtest_load.py` L77-L116 (BACKTEST_COLUMNS, no `fuku_odds_*`); commit `8ea7ba2` diff (cycle-4 target fix scope — 3 edits across `07-02-PLAN.md` L194/L201/L331 and `07-03-PLAN.md` L369). The orchestrator additionally scanned all 25 residual `assert` occurrences across the 3 PLAN.md files (pytest assertions / verify-command inline asserts / LOW-05 pattern name — none in production fail-loud paths).
