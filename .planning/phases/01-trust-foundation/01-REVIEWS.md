---
phase: 1
reviewers: [codex]
reviewed_at: 2026-06-17T13:45:00+09:00
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
  - 01-04-PLAN.md
  - 01-03-PLAN.md
reviewer_model: gpt-5.5 (Codex CLI v0.139.0)
source_grounding: true
---

# Cross-AI Plan Review — Phase 1 (Trust & Foundation)

> Cycle 1. Single external reviewer: **Codex** (gpt-5.5). Gemini/Claude/Cursor/AGY CLIs not
> detected on host. Findings below have been source-grounded against the actual PLAN.md text
> (line references in parentheses) — every HIGH was verified to exist in the plan, not just
> asserted by the reviewer.
>
> Phase 1's #1 priority is **leakage prevention**. A HIGH in this phase that touches a leak
> surface, raw immutability, or reproducibility is a "must fix before execution" item.

---

## Codex Review

### Overall Assessment

The plans are directionally strong, but they still contain several "looks safe but isn't" issues.
The highest-risk gaps are: 01-04's PIT sortedness check sorts *before* checking (making the raise
unreachable — a direct Success Criterion #4 failure); 01-04's race splitter only asserts race_id
disjointness and never enforces `max(train_time) < min(test_time)`; 01-01/01-03's raw immutability
proof checks `raw_everydb2` VIEWs while the ETL/quality-gate read `public.n_*` directly (so the
physical raw tables can remain mutable); and 01-03's normalized ETL lacks idempotency and a
clearly-defined write role. These can create false-green tests while leakage or raw mutation
remains possible.

---

### Plan 01-01: uv / DB connection / 5-layer schema / class_normalization.yaml

**Summary.** A reasonable foundation: pinned uv environment, pydantic-settings, psycopg3 pool,
five logical schemas, and the code-based class normalization YAML. The class mapping is well
grounded and making `KEIBA_ADMIN_DSN` mandatory is good. The critical weakness is the raw
read-only story: revoking writes on the `raw_everydb2` VIEW schema does not prove the physical
`public.n_*` tables are protected, and every downstream plan reads `public.n_*` directly.

**Strengths.**
- `uv.lock` + `requires-python >=3.12,<3.13` supports §19.1 reproducibility.
- Five logical schemas established early.
- `KEIBA_ADMIN_DSN` made mandatory (no silent skip of REVOKE).
- `class_normalization.yaml` in Git-controlled config with the verified `2019-06-08` reform date
  and code-based mapping (no `hondai` regex).
- `feature_availability.yaml` 6-key schema bootstrapped early.

**Concerns.**

- **HIGH** — Raw write protection targets `raw_everydb2` VIEWs, but later plans read from
  `public.n_*`. The REVOKE in Task 3
  (`REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2`, plan 01-01 L223) and the
  privilege test in 01-03 (`WHERE table_schema='raw_everydb2'`, plan 01-03 L272) cover ONLY the
  view layer. The physical `public.n_race` / `public.n_uma_race` tables have **no** REVOKE applied.
  If `KEIBA_DB_USER` retains any write grant on `public.n_*`, raw can still be mutated while every
  catalog check passes. *(Grounded: 01-01 L220/223/272 read `raw_everydb2`; 01-02 L17/L40 and
  01-03 L46/L112/L196 read `everydb2.public.n_*` / `public.n_race` — never `raw_everydb2` for data
  reads.)*
- **HIGH** — `CREATE OR REPLACE VIEW raw_everydb2.n_race AS SELECT * FROM public.n_race`
  (01-01 L220, L235) does not by itself make raw immutable. PostgreSQL simple views are updatable
  when the underlying base-table grants allow it; immutability must be enforced on BOTH the views
  and the underlying `public.n_*` tables.
- **HIGH** — Task 3's verification query
  (`grantee=current_setting('role')` against the admin DSN, 01-01 L231) checks the **admin**
  role's grants, not `KEIBA_DB_USER`'s. A false pass is likely. The 01-03 L272 test
  (`grantee = current_user` connected as `KEIBA_DB_USER`) is the correct probe — they are
  inconsistent.

**Suggestions.**
- REVOKE and test write privileges on **both** `public.n_*` and `raw_everydb2.*`.
- Use `has_table_privilege(:role, 'public.n_race', 'UPDATE')` instead of relying solely on
  `information_schema.role_table_grants`.
- Define separate read/write roles (`KEIBA_RAW_DB_USER` / `KEIBA_ETL_DB_USER`); see Plan 01-03.
- Quote role identifiers safely in `scripts/apply_schema.sql` via `psycopg.sql.Identifier`
  (the plan's `<KEIBA_DB_USER>` literal cannot appear in static SQL without templating).

**Risk Assessment: HIGH.** Raw immutability can be falsely certified because permission checks
target the wrapper schema while ETL uses `public.n_*`.

---

### Plan 01-02: Hybrid quality gate

**Summary.** Correct hybrid-gate shape (structural = block, quantitative = info). Covers table
existence, date range, counts, PK/natural-key duplicates, NULL/cast rates. The gap is Success
Criterion #1 coverage: **mojibake flags** and **code-value anomalies** are mentioned in the
objective but never concretely implemented in the action.

**Strengths.**
- Clean `block` vs `info` separation.
- `jyocd BETWEEN '01' AND '10'` enforced on data checks (Pitfall 2).
- JSON + Markdown reports with top-level `verdict`; CI-friendly `--fail-on-block` exit 1.
- `s_*` (速報) correctly out of scope; `n_*` only (Pitfall 4).
- Explicit `CAST(kyori AS integer)` cast-success checks (Pitfall 1).

**Concerns.**

- **HIGH** — Mojibake detection is not concretely implemented. Success Criterion #1 requires
  mojibake flags; the action (01-02 L97) only lists NULL/code=0/cast rates. *(Grounded: the
  objective L48 claims §6.4's 9 items incl. "文字化け" but Task 1's BLOCK/INFO checklist (L92-97)
  has no mojibake check.)*
- **HIGH** — Code-value anomalies are underspecified. For DATA-01, `jyokencd5` / `gradecd` /
  `jyocd` / `syubetucd` should be validated against the allowed values in
  `class_normalization.yaml` and `code_tables.yaml`. The action only checks "code=0 or 空白の割合".
- **HIGH** — DB-integration tests are allowed to skip when `.env` is missing
  (01-02 L108 "`.env` 未設定時 skip", L121 "skip 可"). This **contradicts** 01-01 Task 2's policy
  (L184-186: default **fail** unless `KEIBA_SKIP_DB_TESTS=1`). A green suite without a live DB
  hides an unverified `verdict=pass`.

**Suggestions.**
- Add a concrete mojibake check (e.g. count of `U+FFFD` replacement chars / invalid-encoding bytes
  in `bamei`, `kisyu`, `hondai`).
- Add config-driven allowed-code checks using the YAML code tables.
- Make DB tests fail by default unless `KEIBA_SKIP_DB_TESTS=1` (align with 01-01).
- Replace string-concatenated PK distincts (`year||jyocd||kaiji...`, L95-96) with
  `COUNT(DISTINCT (year, jyocd, kaiji, ...))` or delimited `concat_ws` to avoid theoretical
  collisions.

**Risk Assessment: MEDIUM.** Gate shape is good, but it does not fully satisfy DATA-01 until
mojibake/code-anomaly checks and non-skippable integration verification are tightened.

---

### Plan 01-04: 4 leakage-prevention primitives (THE CORE DELIVERABLE)

**Summary.** This is the load-bearing plan for Phase 1's Core Value, and it needs the most
correction. The four primitives are correctly identified, but the PIT joiner sortedness check is
**broken**: it sorts *before* checking monotonicity, so the `raise` is unreachable for unsorted
input. The race splitter prevents race_id overlap but never proves train is strictly before test
in time. The calibrator boundary is correct but relies on `assert` (disabled under `python -O`).

**Strengths.**
- Correctly wraps `pd.merge_asof(direction="backward")`.
- `__UNSEEN__` / `__MISSING__` non-negative int32 sentinels (NaN→-1 forbidden, §14.3/14.5).
- `CalibratedClassifierCV(..., cv="prefit")` with `estimator=` arg (sklearn 1.9.0, not legacy
  `base_estimator=`).
- Smoke tests for all four primitives.

**Concerns.**

- **HIGH** — **PIT sortedness check is unreachable.** Plan 01-04 L122: the action says
  `obs = observations.sort_values(on_cutoff)`, `hist = history.sort_values(on_asof)` **first**,
  *then* `if not obs[on_cutoff].is_monotonic_increasing: raise ValueError(...)`. Because
  `sort_values` always produces a monotonic series, the check can never fire for unsorted caller
  input. This directly fails Success Criterion #4 ("sortedness pre-check that raises if unsorted").
  Notably the plan's own `<behavior>` (L106-107) and threat model T-04-01 (L238 "事前チェック" =
  pre-check) describe the *correct* intent, so the `<action>` text contradicts the behavior +
  threat model. *(The RESEARCH Example 2 has a separate but related bug: it checks
  `obs.index.is_monotonic_increasing` after a column `sort_values`, which also never fires.)*
- **HIGH** — The PIT sortedness check must validate **caller-provided input before any sort**,
  otherwise downstream code can silently pass unsorted data and never learn it violated the
  contract. Recommended implementation:
  ```python
  if not observations[on_cutoff].is_monotonic_increasing:
      raise ValueError(f"observations must be sorted by {on_cutoff}")
  if not history[on_asof].is_monotonic_increasing:
      raise ValueError(f"history must be sorted by {on_asof}")
  # only then optionally sort, OR require pre-sorted input and never sort silently
  ```
- **HIGH** — `race_id_time_series_split` only asserts race_id disjointness (01-04 L113, L127
  `assert set(train_rids).isdisjoint(set(test_rids))`). It does **not** assert
  `max(train.race_start_datetime) < min(test.race_start_datetime)`. If multiple races share the
  same `race_start_datetime` timestamp (e.g. same post time at different tracks), the time-order
  boundary is not enforced — a fold could place a later-clock-time race in train and an
  earlier-clock-time race in test so long as the race_ids differ. The plan's `test_time_order`
  (L137) only checks "以下" (`<=`), not strict `<`. §8.4/§15.4 require strict chronological
  separation.
- **HIGH** — Leakage-critical `assert` statements (01-04 L113 race_id disjoint, L188 calibrator
  `assert train_max_date < race_dates_calib.min()`) are disabled under `python -O`.
  Leakage-prevention guards must `raise ValueError` (or a custom exception), never `assert`.

**Suggestions.**
- Implement PIT check on the original inputs before sorting (see snippet above); add a test that
  an unsorted input raises *before* any merge occurs.
- Add splitter guards: non-empty train/test per fold, `max(train_time) < min(test_time)`, and
  document/test how equal-timestamp races are handled.
- Replace all leakage-critical `assert` with `raise ValueError`.
- `pd.merge_asof` with `by=` requires within-group sortedness, not just global time monotonicity —
  validate or document the accepted sort.
- `fit_category_map` should return provenance metadata (fit window dates, source split id,
  category hash) so accidental re-fit on validation/test is detectable.

**Risk Assessment: HIGH.** As written, a correctly-written `test_sortedness_raises` smoke test
should *fail*; if it passes, the implementation is almost certainly testing the wrong behavior
(the unreachable branch). This is a direct leakage-prevention blocker.

---

### Plan 01-03: normalized ETL + class normalization + raw immutability pytest

**Summary.** Correct end-state intent: typed normalized tables, code-based class normalization,
JRA filtering, raw-immutability tests. Several load-bearing gaps: the ETL is not idempotent,
`n_uma_race` is far less specified than `n_race`, raw immutability can be defeated by direct
`public.n_*` grants, and single-date row hashing can miss mutations outside the sample. The class
normalization tests (especially `test_code_005_spans_reform`) are excellent.

**Strengths.**
- Explicitly forbids name-based (`hondai`) normalization; tests `005` across the 2019 reform
  (Pitfall 7 core).
- Handles `hassotime='0'` (EveryDB2 initial value) → `NaT` instead of crashing ETL (Warning #5).
- `jyocd BETWEEN '01' AND '10'` for JRA-only ETL (Pitfall 2).
- `class_normalization_status='unresolved'` for unknown codes (D-13, no silent fallback).
- Direct raw-immutability tests before/after ETL; avoids DuckDB persistence (§12.1).

**Concerns.**

- **HIGH** — **ETL idempotency is unspecified.** `_create_normalized_tables` uses
  `CREATE TABLE IF NOT EXISTS normalized.n_race (...)` then `INSERT INTO normalized` (01-03 L188,
  L196, grep gate L219). Re-running `run_normalized_etl` will **duplicate rows**. No
  `TRUNCATE`, `ON CONFLICT DO UPDATE/NOTHING`, staging-table-swap, or reload semantics are
  specified anywhere in the plan. This breaks reproducibility (§19.1) on the second run.
- **HIGH** — **Write role is undefined.** Plan 01-01 defines `KEIBA_DB_USER` as raw read-only,
  but 01-03's `scripts/run_normalized_etl.py` needs a "normalized 書込ロール" (L201) to
  `INSERT INTO normalized`. No `KEIBA_ETL_*` env var, no `Settings` field for a write DSN, and no
  GRANT to `normalized` schema for any role is defined. The ETL cannot run as specified.
- **HIGH** — Raw immutability tests check `raw_everydb2` grants (01-03 L272) but ETL reads
  `public.n_*` (L196, L112). Direct write grants on `public.n_*` are never ruled out (same root
  cause as 01-01 HIGH #1).
- **HIGH** — `pg_stat_user_tables.n_tup_upd/n_tup_del` is insufficient proof (01-03 L259, L260).
  These stats reset on `VACUUM`, can lag, and miss `TRUNCATE`+`INSERT` mutation patterns. The
  row-hash check is the stronger signal; the pg_stat check should be supplementary, and
  `n_tup_ins` + a before/after row-count delta should also be compared.
- **HIGH** — Fixed-sample hashing with `sample_date="20240101"` (01-03 L256) can miss mutations
  outside that date, and if 2024-01-01 has no JRA races the hash is meaningless. Either hash all
  JRA rows for key columns or use per-table/year-partitioned aggregate checksums.
- **HIGH** — `n_uma_race` normalized ETL is underdescribed (01-03 L195 "同様に
  `normalized.n_uma_race` を作成"). Phase 2 labels depend heavily on `n_uma_race` (kakuteijyuni,
  kettonum, etc.); the casts, keys, and rowcount-check must be specified now, not deferred.

**Suggestions.**
- Define normalized-table primary keys and deterministic reload semantics: `TRUNCATE
  normalized.n_race, normalized.n_uma_race` inside a transaction, or staging tables + atomic
  rename, or `INSERT ... ON CONFLICT (...) DO UPDATE`.
- Add a `KEIBA_ETL_DB_USER` / `KEIBA_ETL_DB_PASSWORD` (or explicitly GRANT `KEIBA_DB_USER`
  write only on `normalized`) and a `Settings` field for the write DSN.
- Compute raw fingerprints over all JRA rows for key columns (or per-year aggregate checksums).
- Add direct privilege tests for `public.n_*`: no INSERT/UPDATE/DELETE/TRUNCATE.
- Expand `n_uma_race` casts/validation now (Phase 2 depends on it).
- `normalize_class` unresolved case (01-03 L124) should still compute
  `post_2019_class_system_flag` from `race_date` — do not null it just because the class code is
  unknown.
- `date.fromisoconfig(...)` (01-03 L118) is a typo for `date.fromisoformat(...)`.

**Risk Assessment: HIGH.** The ETL could be non-reproducible on rerun, and the raw-immutability
proof can pass while the actual `public.n_*` tables remain mutable.

---

### Cross-Plan Consistency

- **HIGH** — **Raw schema mismatch.** Plan 01-01 creates/protects `raw_everydb2` VIEWs; Plans
  01-02 and 01-03 query `public.n_*` directly. Permission tests on `raw_everydb2` do not prove
  `public.n_*` is immutable. **Pick one canonical read path** — either all code reads
  `raw_everydb2` (and the physical `public.n_*` tables are also REVOKE'd), or the grants/tests
  protect `public.n_*` directly.
- **HIGH** — **Role mismatch.** Plan 01-01 defines `KEIBA_DB_USER` as raw read-only; Plan 01-03
  needs a `normalized`-write connection. No separate write role / env var is defined.
- **HIGH** — **DB-test skip policy conflict.** Plan 01-01 says DB tests **fail by default** unless
  `KEIBA_SKIP_DB_TESTS=1`; Plans 01-02 and 01-03 repeatedly say `.env` missing → **skip**. A green
  suite without a live DB certifies `verdict=pass` unverified.
- **HIGH** — Plan 01-04's PIT acceptance expects a sortedness raise, but the planned
  implementation sorts before checking, making the raise logically unreachable.
- **MEDIUM** — `gradecd` F/G/H are observed in research but inconsistently handled in 01-01's YAML
  ("未記載または unresolved", 01-01 L271). Decide: valid unresolved codes or supported mappings,
  and test accordingly.
- **MEDIUM** — Plan 01-01 says `raw_everydb2` is the raw layer, but quality gate and ETL use
  `public` as raw. Canonical-path decision (see above) resolves this.
- **MEDIUM** — `scripts/apply_schema.sql` needs runtime substitution for `KEIBA_DB_USER`; the
  split between static SQL and Python templating is unclear (identifier quoting via
  `psycopg.sql.Identifier`).
- **LOW** — Plan 01-04 is tagged `requirements: [DATA-03]` (frontmatter L19) but it is really
  Success Criterion #4 / leakage infrastructure, not DATA-03. Cosmetic but worth fixing for
  traceability.

### Top Fixes Before Execution

1. **Fix Plan 01-04 PIT sortedness:** check the *original* caller inputs before sorting (or
   require pre-sorted input and never sort silently). Add a test that unsorted input raises
   *before* any merge.
2. **Enforce strict chronological split:** `max(train_time) < min(test_time)`; decide/document
   equal-timestamp handling.
3. **Align raw access:** either all code reads `raw_everydb2` AND the physical `public.n_*`
   tables are also REVOKE'd, or all grants/tests protect `public.n_*` directly.
4. **Define a separate DB role for raw-read vs normalized-write** (+ env vars / Settings fields).
5. **Make normalized ETL idempotent** (PKs + TRUNCATE-in-tx / staging-swap / `ON CONFLICT`).
6. **Add concrete mojibake and code-value anomaly checks** to Plan 01-02.
7. **Replace all leakage-critical `assert`** with explicit `raise ValueError`.
8. **Unify the DB-test skip policy** to fail-by-default across 01-01/01-02/01-03.

---

## Consensus Summary

(Single-reviewer cycle — no inter-reviewer agreement/divergence to synthesize. The above Codex
findings are the cycle-1 consensus.)

### Agreed Strengths (Codex, plus planner self-assessment)
- Code-based class normalization with verified `2019-06-08` reform date and `005` reform-spanning
  test is the strongest part of the phase (Pitfall 7 correctly neutralized).
- The four primitives are correctly *identified*; the leakage-prevention *intent* is right.
- REVOKE-on-admin-DSN + mandatory `KEIBA_ADMIN_DSN` is a real improvement over silent-skip.
- DuckDB correctly excluded from persistence (§12.1).

### Agreed Concerns (highest priority, all HIGH)
1. **PIT sortedness raise unreachable** (01-04) — silent leak path; the smoke test will false-pass.
2. **Raw immutability proof checks the wrong schema** (`raw_everydb2` views vs `public.n_*`
   physical tables) across 01-01/01-02/01-03 — raw can mutate while every check is green.
3. **Race splitter lacks strict chronological assertion** (01-04) — equal-timestamp races can
   cross the train/test boundary.
4. **Leakage guards use `assert`** (01-04) — disabled under `python -O`.
5. **ETL not idempotent** (01-03) — duplicates on rerun, breaks reproducibility.
6. **No normalized-write role defined** (01-01 vs 01-03) — ETL cannot run as specified.
7. **DB-test skip policy contradicts** across plans — false-green risk.
8. **Quality gate missing concrete mojibake + code-value-anomaly checks** (01-02) — DATA-01 not
   fully met.

### Divergent Views
None (single reviewer).

---

## Cycle Status

- **Reviewer invoked:** Codex (gpt-5.5) — succeeded, 16.2 KB structured output.
- **Other CLIs:** gemini / claude / cursor / agy not detected on host.
- **Source grounding:** all 8 HIGHs verified against PLAN.md line numbers (see inline citations).
- **Next step:** feed this REVIEWS.md into `/gsd-plan-phase 1 --reviews` to drive a replan, then
  re-run `/gsd-review` (Cycle 2) until `current_high=0`.

---

## Verification Coverage (orchestrator source-grounding pass)

Authority: `grep` (config `plan_review.source_grounding_authority`). Pass run by the
plan-review-convergence orchestrator after the Cycle-1 review.

**Scope finding:** this is a greenfield project — the only project source file is `CLAUDE.md`
(no `src/` code, git-tracked non-doc files = `CLAUDE.md` only). Every symbol the plans cite
falls into one of three buckets, none of which are verifiable against existing project source:

- **New artifacts (excluded by policy):** all `src/keiba_ai/...` modules, `pyproject.toml`,
  `alembic.ini`, `class_normalization.yaml`, conftest fixtures, etc. — these are *created by*
  this phase, not references to existing code. Not verified (correctly).
- **External library APIs (UNCHECKABLE under grep):** `pandas.merge_asof`,
  `mlxtend.evaluate.GroupTimeSeriesSplit`, `sklearn.calibration.CalibratedClassifierCV`,
  `lightgbm`/`catboost` (`has_time=True`), `psycopg`/`duckdb` — resolved against PyPI packages,
  not project source. Their signatures are UNCHECKABLE under the `grep` authority.
- **PostgreSQL schema objects (UNCHECKABLE under grep):** `n_uma_race`, `n_umag`, `raw_everydb2`
  views, `public.n_*` physical tables — these live in the DB, not the repo. Existence/typing is
  a runtime DB concern (already flagged where under-specified, e.g. `n_uma_race` columns → MEDIUM).

**Verdict:** no **MISSING** or **AMBIGUOUS** project-source symbols (none exist to verify).
grep-verifiable existing project-source symbols: **0** (greenfield). This clean result is
structural, not a coverage gap — there is no existing implementation code for the plans to
hallucinate references into. The substantive grounding happened at the PLAN.md-line level inside
the review (all 8 HIGHs cited to line numbers above).
