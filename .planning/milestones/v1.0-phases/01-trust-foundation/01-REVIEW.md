---
phase: 01-trust-foundation
reviewed: 2026-06-17T00:00:00Z
depth: deep
files_reviewed: 36
files_reviewed_list:
  - reports/.gitkeep
  - scripts/apply_schema.sql
  - scripts/run_apply_schema.py
  - scripts/run_normalized_etl.py
  - scripts/run_quality_report.py
  - src/__init__.py
  - src/config/__init__.py
  - src/config/class_normalization.yaml
  - src/config/code_tables.yaml
  - src/config/feature_availability.yaml
  - src/config/settings.py
  - src/db/__init__.py
  - src/db/connection.py
  - src/db/schema.py
  - src/etl/__init__.py
  - src/etl/class_normalize.py
  - src/etl/normalize.py
  - src/etl/quality_gate.py
  - src/etl/raw_fingerprint.py
  - src/utils/__init__.py
  - src/utils/calibrator.py
  - src/utils/category_map.py
  - src/utils/group_split.py
  - src/utils/pit_join.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_bootstrap.py
  - tests/test_class_normalization.py
  - tests/test_normalized_etl.py
  - tests/test_quality_gate.py
  - tests/test_raw_immutability.py
  - tests/utils/__init__.py
  - tests/utils/test_calibrator.py
  - tests/utils/test_category_map.py
  - tests/utils/test_group_split.py
  - tests/utils/test_pit_join.py
findings:
  critical: 5
  warning: 9
  info: 6
  total: 20
status: issues_found
---

# Phase 01: Code Review Report (deep)

**Reviewed:** 2026-06-17
**Depth:** deep (cross-file analysis)
**Files Reviewed:** 36
**Status:** issues_found

## Summary

This phase implements the trust foundation: raw-immutability fingerprinting, normalized ETL, class normalization, quality gates, and four leak-safe utility primitives (PIT join, prefit calibrator, group-aware time-series split, frozen category map). The leak-prevention primitives themselves (`pit_join_backward`, `fit_prefit_calibrator`, `race_id_time_series_split`, `apply_category_map`) are implemented carefully — guards use `raise ValueError` (not `assert`), sortedness is checked before any sort, and disjoint/strict-chronological invariants are enforced. The prior CR-01/CR-02 fixes for `pd.NaT` and `futan` decimal pattern are correctly applied.

However, deep cross-file review surfaced **5 BLOCKER-class defects** that materially weaken the trust guarantees this phase is supposed to provide:

1. **CR-03 — Raw fingerprint is defeatable**: hash uses `t::text` (column-order sensitive) and only covers JRA rows; non-JRA tampering that preserves row count is invisible.
2. **CR-04 — `_idempotent_load` silently swaps to empty `normalized.*` when input rows = 0** and has no advisory lock guarding the staging-swap critical section against concurrent ETL runs.
3. **CR-05 — `_check_cast_success` never executes an actual CAST**: the "cast_success_pct" is a regex match that cannot detect out-of-range integers or sign issues, is INFO-only (never gates), and the silent `pd.to_numeric(errors='coerce')` path in normalize means corrupted raw values reach `normalized.*` as NULL with no gate failure.
4. **CR-06 — `_JRA_FILTER` is defined three different ways** in three modules (raw_fingerprint, quality_gate, normalize) — divergent scopes, no shared constant, CLAUDE.md calls out this exact risk.
5. **CR-07 — `_validate_by_group_sorted` is redundant given the global check, but the misleading docstring + redundancy will cause a future maintainer to drop the global check and introduce silent leakage** — a trust-foundation primitive must not rely on "happens to be correct today".

Plus 9 warnings (logic edge cases, test correctness gaps, error swallowing, schema-drift) and 6 info items.

---

## Critical Issues

### CR-03: Raw fingerprint is defeatable — `t::text` is column-order sensitive and only JRA rows are hashed

**File:** `src/etl/raw_fingerprint.py:55-73`
**Issue:**

The "primary proof" hash is built per-year via `md5(string_agg(t::text, ',' ORDER BY t::text))` with `WHERE jyocd BETWEEN '01' AND '10'`. Several defeatability problems:

**(a) `t::text` is not column-order stable.** Postgres's row-to-text cast emits columns in their **physical attribute order** (attnum). If anyone `ALTER TABLE n_race ADD COLUMN ...` (DBA, migration, EveryDB2 sync), `t::text` changes for *every* row even when data is byte-identical, **silently invalidating the fingerprint across runs** (false positive — flags an unchanged table as mutated). Conversely the cast can change format after `VACUUM FULL` + attribute rewrite. The fingerprint's claim to be a *reproducible* raw-immutability proof is undermined because it depends on physical layout, not logical content.

**(b) The hash intentionally excludes NAR rows (`jyocd >= '30'`)**, but `row_count[table]["total"]` at line 69 (`SELECT count(*) FROM public.{table}` with no filter) counts *everything*. A tampering actor who deletes one NAR row and inserts a different NAR row keeps both `row_hash` (JRA scope — unchanged) and `row_count["total"]` (constant) identical — the tampering is invisible. The "raw immutability" guarantee is therefore only **JRA-immutability** plus a coarse total-row count — not what the docstring promises.

**(c) `n_tup_upd` / `n_tup_del` / `n_tup_ins` are reset by `VACUUM`/`TRUNCATE`** (acknowledged in docstring). In a real DB under autovacuum, the supplementary signal between two fingerprint snapshots is essentially noise — a real UPDATE followed by VACUUM between snapshots produces a false-negative (auxiliary check passes).

**Net effect:** the assertion can be defeated by balanced delete/insert on NAR rows, masked by column-order changes, or noise-washed by autovacuum. For a *trust foundation*, the fingerprint must hash a deterministic, column-name-keyed representation.

**Fix:**
```python
# Stable column list per table — don't depend on t::text
_RACE_HASH_COLS = "year, monthday, jyocd, kaiji, nichiji, racenum, kyori, hassotime, ..."
sql = (
    f"SELECT year, md5(string_agg("
    f"concat_ws('|', {_RACE_HASH_COLS}), ',' "
    f"ORDER BY year, monthday, jyocd, kaiji, nichiji, racenum"
    f")) FROM public.{table} WHERE {_JRA_FILTER} GROUP BY year ORDER BY year"
)
# Also hash the non-JRA partition so NAR-only tampering is detectable,
# OR drop the total count and document JRA-only coverage honestly.
```

---

### CR-04: `_idempotent_load` silently swaps `normalized.*` to empty when input rows = 0; no advisory lock against concurrent ETL

**File:** `src/etl/normalize.py:333-382, 519-556`
**Issue:**

**(a) Empty-input data loss.** At line 365 `if rows:` — when `rows` is empty (caused by a read-pool timeout returning `[]`, a transform bug returning 0 rows, or a misconfigured filter), the code `TRUNCATE`s staging, **skips INSERT**, then `DROP`s `normalized.n_race` and `RENAME`s the empty staging to `n_race`. `normalized.n_race` is now **completely empty**, `_idempotent_load` returns `len(rows)` = 0, `_load_race` returns `(0, 0)`, and `run_normalized_etl` returns successfully with `rows_inserted={"n_race": 0}`. For a trust foundation this is silent data loss.

**(b) No concurrency guard.** The "atomic swap" is two separate statements (`DROP` then `RENAME`) inside a transaction — fine for single-writer, but two concurrent ETL runs (CI + manual, or re-trigger) both `CREATE TABLE IF NOT EXISTS normalized.n_race_staging`, both `TRUNCATE` it, both `DROP` the target — the final state is whichever swap lands last, with rows from either run. There is no `pg_advisory_xact_lock` guarding this critical section.

**(c) Return-value trust.** `_idempotent_load` returns `len(rows)` unconditionally — it does not verify `cursor.rowcount == len(rows)` after `executemany`. If psycopg3's `executemany` ever returns without raising but inserts fewer rows (e.g. trigger-suppressed), the caller logs an inflated count.

**Fix:**
```python
def _idempotent_load(write_cur, table, rows, columns):
    # (1) Serialize concurrent ETL runs on the same table
    write_cur.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        (f"normalized.{table}",),
    )
    # (2) Refuse to swap-empty — never silently wipe normalized.*
    if not rows:
        raise RuntimeError(
            f"_idempotent_load('{table}'): refusing to swap to empty (0 rows). "
            "Investigate read pool / transform — silent data loss prevented."
        )
    # ... rest as before
    # (3) Verify rowcount
    actual = write_cur.rowcount
    if actual != len(rows):
        raise RuntimeError(
            f"_idempotent_load('{table}'): executemany inserted {actual}, expected {len(rows)}"
        )
```

---

### CR-05: `_check_cast_success` does not actually CAST — Pitfall-1 corruption is undetectable and never gates

**File:** `src/etl/quality_gate.py:357-410`
**Issue:**

The function name is `_check_cast_success` and the returned field is `cast_success_pct`, but the SQL is a regex match (`{c} !~ %s`), not a CAST. This is more than naming — the regex cannot detect the corruption scenarios Pitfall 1 exists to prevent:

| Value | Regex `^[0-9]+$` | Actual `CAST(x AS integer)` |
|-------|------------------|------------------------------|
| `'99999999999999999999999'` | matches → "success" | `ERROR: integer out of range` |
| `'+57'` | no match → "fail" | would parse to 57 |
| `'57.0'` (real pattern matches) | → "success" | integer column: `ERROR: invalid input syntax` |

Compounding defects:
1. The check is `severity="info"` and `passed=True` always (line 407) — it never gates `verdict`.
2. The normalize ETL uses `pd.to_numeric(errors='coerce')` which **silently converts garbage to NaN/NULL** — so corrupted raw flows into `normalized.*` as NULLs with no quality gate ever failing.
3. No test asserts `cast_fail > 0` for bad data — `test_check_cast_success_uses_decimal_pattern_for_real_columns` only verifies the *pattern string*, not the semantics.

**Net: a `kyori='ZZZZZ'` row in raw passes the quality gate (verdict=pass) and reaches `normalized.n_race` with `kyori=NULL`, and no test catches this.** This is the exact silent data corruption the trust foundation must prevent.

**Fix:**
1. Either run a real CAST inside a `SAVEPOINT` per-row, or rename to `_check_numeric_pattern` and stop calling the field "cast_success".
2. Add a BLOCK-level gate that fails when `cast_success_pct < 99%` for `kyori`/`kakuteijyuni`/`futan`/`bataijyu`.
3. Add a test feeding `'ZZZZZ'` and asserting `cast_fail > 0`.
4. Make normalize's `pd.to_numeric(errors='coerce')` count coercions and emit a BLOCK-level warning when coercion rate exceeds a threshold.

---

### CR-06: `_JRA_FILTER` defined three different ways across modules — divergent scopes, no shared constant

**File:** `src/etl/raw_fingerprint.py:26`, `src/etl/quality_gate.py:44`, `src/etl/normalize.py:46`
**Issue:**

Three different "JRA filter" definitions coexist:

| Module | Filter |
|--------|--------|
| `raw_fingerprint.py:26` (`_JRA_FILTER`) | `jyocd BETWEEN '01' AND '10'` (no year filter) |
| `quality_gate.py:44` (`JRA_ONLY_FILTER`) | `jyocd BETWEEN '01' AND '10'` (no year filter) |
| `normalize.py:46` (`_JRA_FILTER`) | `jyocd BETWEEN '01' AND '10' AND year::int >= 2015` |

Requirements (§6.1) state the project data window is 2015-01-01 onwards. Normalize correctly applies `year::int >= 2015`. But:

1. `raw_fingerprint.compute_raw_fingerprint` hashes **all years** of JRA data (including 2014, 2010…). If EveryDB2 amends a pre-2015 row, the raw-hash changes and `assert_raw_unchanged` raises — but the change has **no effect on training data** (normalize excludes pre-2015). Conversely, the hash doesn't cover NAR inserts at all. The trust guarantee is both too-strict (flags irrelevant pre-2015 changes) and too-lax (ignores NAR).
2. `quality_gate._check_jra_since_2015` uses `(year||monthday) >= '20150101'`, but `_check_n_race_pk_unique` and `_check_null_rates` use `JRA_ONLY_FILTER` (no year filter) — so they audit pre-2015 rows too. Inconsistent.
3. The same logical filter is implemented three times in three files. A future edit to one will not propagate. CLAUDE.md calls out this exact risk.

**Fix:** Single source of truth:
```python
# src/etl/filters.py (new) or src/config/constants.py
JRA_FILTER = "jyocd BETWEEN '01' AND '10'"
PROJECT_WINDOW_FILTER = "jyocd BETWEEN '01' AND '10' AND year::int >= 2015"
```
Have `raw_fingerprint`, `quality_gate`, and `normalize` all import from it. Decide explicitly: should raw-immutability cover pre-2015? Document and align all three.

---

### CR-07: `_validate_by_group_sorted` is redundant given the global check; misleading docstring will cause future regression

**File:** `src/utils/pit_join.py:84-116`
**Issue:**

The docstring claims "merge_asof の by= はグループ内ソートを要求". This is **partially wrong**. Per pandas docs/source, `merge_asof(by=...)` requires the **`on=` column to be globally sorted (monotonic increasing) across the whole frame** — per-group sortedness is implied by global but is **not sufficient** alone.

The implementation enforces both:
1. Global `is_monotonic_increasing` of `on_cutoff`/`on_asof` (lines 73-82) — **this is the real contract**.
2. `_validate_by_group_sorted` — checks per-group monotonic (redundant given #1).

The danger: a future maintainer reading the misleading docstring and seeing two checks "simplifies" by dropping the global check (lines 73-82), thinking the per-group check covers it. They would introduce **silent leakage** — a globally-unsorted-but-per-group-sorted frame would pass `merge_asof`'s own sortedness check on some pandas versions (it only raises for global non-monotonic) and silently produce wrong joins. For a primitive whose entire purpose is preventing silent leakage, "happens to be correct today" is insufficient.

There is also no regression test constructing a per-group-sorted-but-globally-unsorted input to assert the global check is the load-bearing one.

**Fix:**
1. Remove `_validate_by_group_sorted` (redundant given the global check) OR document clearly that it is belt-and-suspenders, not primary.
2. Fix the docstring: "merge_asof(by=...) requires **global** sortedness of the `on=` column; per-group sortedness is implied but not sufficient."
3. Add a regression test:
```python
def test_globally_unsorted_but_per_group_sorted_raises():
    obs = pd.DataFrame({
        "feature_cutoff_datetime": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-03"]),
        "horse_id": ["h1", "h2", "h1"],
    })
    # h1=[Jan2,Jan3] OK; h2=[Jan1] OK; global=[Jan2,Jan1,Jan3] NOT monotonic
    hist = pd.DataFrame({
        "as_of_datetime": pd.to_datetime(["2024-01-01"]),
        "horse_id": ["h1"], "value": ["A"],
    })
    with pytest.raises(ValueError, match="observations must be sorted"):
        pit_join_backward(obs, hist)
```

---

## Warnings

### WR-01: `normalize_race_classes` uses `out.at[i, col]` with `enumerate` index — breaks if upstream frame has non-default index

**File:** `src/etl/class_normalize.py:159-222` (called from `src/etl/normalize.py:299`)
**Issue:** `out.at[i, col]` uses the `enumerate` index `i` as a label. If the upstream frame passed in has a non-RangeIndex (after a filter, concat, or reset_index(drop=False) anywhere in the call chain), `out.at[i, col]` silently mis-aligns — assigning to wrong rows or raising `KeyError`. Current call path uses RangeIndex, so it works today; the contract is unenforced.

**Fix:** `out = df.reset_index(drop=True).copy()` at the top, and document.

---

### WR-02: `_safe_parse_hassotime` annotation references `pd._TSNA` (private API) and lies about return type

**File:** `src/etl/normalize.py:248-259`
**Issue:** Annotation says `pd.Timestamp | pd._TSNA` but actually returns `datetime.time` (from `.time()`) or `pd.NaT`. `pd._TSNA` is a private symbol (leading underscore) that may move in pandas 3.0 (CLAUDE.md stack). Runtime behavior is fine; the annotation is misleading and fragile.

**Fix:** Annotate as `Any` or `datetime.time | None`; return `None` for invalid instead of `pd.NaT`; drop `pd._TSNA`.

---

### WR-03: `_row_to_tuple` empty-string→None coercion is per-column undocumented

**File:** `src/etl/normalize.py:513`
**Issue:** `vals.append(v if v != "" else None if c in {"hondai", "bamei", "banusiname"} else v)` — parses as `v if v != "" else (None if c in {...} else v)`. Only 3 specific columns get empty→None; other text columns (`kisyuryakusyo`, `chokyosiryakusyo`) keep `""` and become Postgres `""`. The inconsistency is undocumented and will surprise downstream feature engineering.

**Fix:** Either consistently convert `""` to `None` for all text columns, or lift the per-column allowlist to a named constant with a comment.

---

### WR-04: `race_id_time_series_split` is expanding-window only — cannot express BT-1..BT-5 rolling/fixed-window backtests despite docstring claim

**File:** `src/utils/group_split.py:88-92`
**Issue:** The split `test_start = (k/(n_splits+1))*n` always has train starting at index 0 (expanding window). CLAUDE.md §15.5 specifies BT-1..BT-5 with concrete year ranges (e.g. BT-1: train 2019-06→2022, test 2023) — these are not all expanding-window. The docstring claims §15.4/§15.5 coverage which it does not provide. The `mlxtend.GroupTimeSeriesSplit` "副 API" is exposed but no BT-specific helper ships in this phase. Fine for Phase 1 if Phase 4 adds it, but the docstring overpromises.

Off-by-one risk: with `n_splits == n-1` and `n=2`, fold k=1 → `test_start=0`, train=[] — caught by the empty-train guard. OK.

**Fix:** Update docstring to honestly state expanding-window semantics; defer BT-1..BT-5 helper to Phase 4.

---

### WR-05: Quality-gate INFO checks swallow all exceptions and never escalate — a broken query is masked as benign

**File:** `src/etl/quality_gate.py:271, 298-299, 345-346, 402-403, 435-436, 501-502, 522-523`
**Issue:** Seven separate `except Exception as exc: columns[t] = {"error": str(exc)}` patterns record the error as a string and continue; none re-raise or escalate severity. If a column is renamed in raw, the report shows `kyori_error: "column ... does not exist"` and `verdict` is still `pass`. For a trust-foundation quality gate, silent degradation is dangerous — a malicious or buggy upstream change becomes invisible.

**Fix:** Either escalate the first INFO-check error to BLOCK severity, or emit `degraded_checks_count` and fail when it exceeds a threshold.

---

### WR-06: `_load_allowed_codes` only excludes `"note"` from `syubetucd` — brittle; jyokencd5/gradecd/jyocd have no exclusion at all

**File:** `src/etl/quality_gate.py:138-141`
**Issue:** `set(str(k) for k in syubetucd_map.keys() if k != "note")`. The exclusion works today because `note` is the only metadata key under `syubetucd`. If anyone adds another metadata key (description, _comment, source), it would be silently treated as a "valid code". The jyokencd5/gradecd/jyocd maps (lines 138-140) have no exclusion at all. There is no test guarding this.

**Fix:** Whitelist by regex (`re.fullmatch(r"\d+", k)` or `r"[A-Z]"` for gradecd) instead of blacklisting `note`.

---

### WR-07: `test_etl_role_cannot_write_public` skips rollback on failure — leaves polluted row in `public.n_race` if test ever fails

**File:** `tests/test_raw_immutability.py:86-102`
**Issue:**
```python
with pytest.raises(psycopg.errors.InsufficientPrivilege):
    write_cur.execute("INSERT INTO public.n_race ...")
write_cur.connection.rollback()  # outside the with-block
```
If the INSERT ever *succeeds* (e.g. role misconfiguration grants write), `pytest.raises` raises `Failed`, the `rollback()` line is **skipped**, and the inserted row remains in `public.n_race`. This is exactly the scenario the test exists to catch, and the failure mode would then break `test_raw_unchanged_after_etl` (row-hash mismatch). Cascading test pollution.

**Fix:**
```python
try:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        write_cur.execute("INSERT INTO public.n_race ...")
finally:
    write_cur.connection.rollback()
```

---

### WR-08: `conftest.pg_pool` session-scoped + function-scoped `readonly_cur` risk pool exhaustion / deadlocks under parallel tests

**File:** `tests/conftest.py:28-44`
**Issue:** `pg_pool` (session, max_size=8). `readonly_cur` borrows per test function. ETL tests hold connections across multiple queries and call `readonly_cur.connection.rollback()` to release locks (see `test_normalized_etl.py:228-229` comment about DROP TABLE deadlock). Risk of pool exhaustion or deadlocks if tests run in parallel. The comment in `test_etl_idempotent_rerun` is evidence this has already bitten.

**Fix:** Document that pytest-xdist is unsupported, or set `min_size=2, max_size=4` with fixture-finalization ensuring connections are returned.

---

### WR-09: `_create_normalized_tables` + `_idempotent_load` silently ignore schema drift — code change to `_RACE_COLUMNS` does not propagate to DB until manual DROP

**File:** `src/etl/normalize.py:144-151, 352-360`
**Issue:** First ETL run creates `normalized.n_race` from `_RACE_COLUMNS`. Subsequent runs `CREATE TABLE staging (LIKE normalized.n_race INCLUDING ALL)`. If someone later adds a column to `_RACE_COLUMNS`, the existing `normalized.n_race` retains the *old* schema; staging inherits old schema; the pandas rows' extra column is dropped at INSERT (column-list explicit). **Schema migration is silent.** For §19.1 reproducibility, a code change to `_RACE_COLUMNS` doesn't propagate without manual `DROP`.

**Fix:** Compare expected schema (from `_RACE_COLUMNS`) to actual via `information_schema.columns` at ETL start; raise if drift detected. Or schema-version + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

---

## Info

### IN-01: `apply_schema.sql` is not directly executable — `{reader}` placeholders make it a template, not runnable SQL

**File:** `scripts/apply_schema.sql:22-31`
**Issue:** The `.sql` extension and presence in `scripts/` is misleading — `psql -f` will fail on the `DO $$` block with `{reader_literal}` literal. Header notes "実行は run_apply_schema.py 経由" but discoverability is poor.

**Fix:** Rename to `apply_schema.sql.template`, or add a build step producing a runnable `.sql`.

---

### IN-02: `run_quality_report.py` JSON output uses `default=str` — fallback serializer, not a security boundary

**File:** `scripts/run_quality_report.py:107, 204`
**Issue:** The allowlist filter at line 53 is the real defense; `default=str` is fallback. Currently `CheckResult.detail` contains only primitives. Low risk but worth a comment so future maintainers don't rely on `default=str` for safety.

**Fix:** Add a comment noting `default=str` is serialization fallback, not security boundary.

---

### IN-03: `class_normalize.py:34` uses relative path — breaks when invoked from non-repo-root CWD

**File:** `src/etl/class_normalize.py:34`
**Issue:** `_DEFAULT_CONFIG_PATH = Path("src/config/class_normalization.yaml")` is relative. `quality_gate.py:83` correctly uses `Path(__file__).resolve().parent.parent / "config"` — absolute. Inconsistency means `load_class_config()` from a Streamlit app launched elsewhere fails.

**Fix:** `Path(__file__).resolve().parent.parent.parent / "src" / "config" / "class_normalization.yaml"` (or compute from module file).

---

### IN-04: `_check_jra_since_2015` string comparison assumes zero-padded `monthday`

**File:** `src/etl/quality_gate.py:182-188`
**Issue:** `(year||monthday) >= '20150101'` works only because monthday is varchar(4) and zero-padded. `'2015'||'101' = '2015101'` (7 chars) would compare wrong. Assumption is undocumented.

**Fix:** `(year || lpad(monthday, 4, '0')) >= '20150101'` or split into year/monthday numeric comparison.

---

### IN-05: `audit_gradecd_d_by_syubetucd` has unused `config` parameter (suppressed with `noqa: ARG001`)

**File:** `src/etl/class_normalize.py:225-229`
**Issue:** Signature accepts `config` but never uses it. Either remove or wire through (e.g. to filter allowed syubetucd codes).

**Fix:** Remove unused parameter, or use it.

---

### IN-06: `tests/utils/test_calibrator.py` imports pandas inside helper — minor cosmetic inconsistency

**File:** `tests/utils/test_calibrator.py:185-188`
**Issue:** `pd_date_range_starting` imports pandas locally. Works, but unusual. No fix needed unless tests grow.

**Fix:** Optional `import pandas as pd` at module top for clarity.

---

## Cross-File Call-Chain Notes

- **Import graph is acyclic**: `src.etl.normalize` → `src.etl.class_normalize` → `src/config/class_normalization.yaml`. No circular deps.
- **`scripts/run_apply_schema.py:32-42`** inserts only `src/` into sys.path and imports `from db import schema` — inconsistent with `run_normalized_etl.py` and `run_quality_report.py` which insert repo root and import `from src.config.settings`. Maintenance footgun.
- **`raw_fingerprint`** imported only by `tests/test_raw_immutability.py` and `scripts/run_normalized_etl.py`. `run_normalized_etl.py:75-80` swallows `AssertionError` and returns exit code 2 — fail-closed. Good.
- **`pit_join_backward` is NOT called anywhere in the current codebase** — utility for Phase 4. CR-07 defects will not surface until Phase 4. Right time to catch them.

---

## Test Quality Assessment

The test suite is strong on *literal* leak-prevention invariants (HIGH #1/#2/#3 directly verified, including a subprocess test for `python -O` survival — excellent). However, the following critical gaps allow CR-03 through CR-07 to evade CI:

- **`test_raw_unchanged_after_etl`** does not test that *non-JRA* tampering is detectable — CR-03 untested.
- **`test_etl_idempotent_rerun`** tests 2 sequential runs, not concurrent or empty-input — CR-04 untested.
- **`_check_cast_success` has no test asserting `cast_fail > 0` for bad data** — CR-05 untested.
- **No test asserts that `_JRA_FILTER` is consistent across modules** — CR-06 untested.
- **No test constructs a per-group-sorted-but-globally-unsorted frame** — CR-07 regression risk unguarded.

These gaps are why the CR findings were not caught despite the test suite passing.

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
