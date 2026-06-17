---
phase: 01-trust-foundation
reviewed: 2026-06-17T00:00:00Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - scripts/apply_schema.sql
  - scripts/run_apply_schema.py
  - scripts/run_normalized_etl.py
  - scripts/run_quality_report.py
  - src/config/settings.py
  - src/db/connection.py
  - src/db/schema.py
  - src/etl/class_normalize.py
  - src/etl/normalize.py
  - src/etl/quality_gate.py
  - src/etl/raw_fingerprint.py
  - src/utils/calibrator.py
  - src/utils/category_map.py
  - src/utils/group_split.py
  - src/utils/pit_join.py
  - tests/conftest.py
  - tests/test_bootstrap.py
  - tests/test_class_normalization.py
  - tests/test_normalized_etl.py
  - tests/test_quality_gate.py
  - tests/test_raw_immutability.py
  - tests/utils/test_calibrator.py
  - tests/utils/test_category_map.py
  - tests/utils/test_group_split.py
  - tests/utils/test_pit_join.py
findings:
  critical: 2
  warning: 9
  info: 6
  total: 17
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-17
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

The Trust Foundation phase implements the five-layer schema, raw immutability (REVOKE + fingerprint), normalized ETL (staging-swap), quality gate, and the four leak-prevention primitives (PIT join, group-aware splitter, frozen category map, prefit calibrator). The leak-prevention primitives are implemented correctly: `pit_join_backward` rejects unsorted input before calling `merge_asof`, `race_id_time_series_split` enforces strict `<` between train and test boundaries, `fit_category_map`/`apply_category_map` map unknown/missing to sentinels and return non-negative int32, and `fit_prefit_calibrator` uses `FrozenEstimator` + `raise ValueError` for the look-ahead guard.

However, the review surfaced two BLOCKER defects and nine WARNINGs. The most severe are (1) `normalize.py:_row_to_tuple` mishandles `pd.NaT` on the `race_date` column — `pd.NaT` has an `isoformat` attribute, so the current guard lets it leak through as a non-None value into the `date` column; (2) `quality_gate._check_cast_success` uses `!~ '^[0-9]+$'` for a `real` column (`futan`), so every decimal weight like `57.5` is miscounted as a cast failure. Additional defects include: `apply_category_map` re-stringifies `NaN` to `'nan'` for the `astype(str)` call (worked around by a later `.where(notna, MISSING)`, but fragile); staging-swap lacks cross-table atomicity between `n_race` and `n_uma_race`; `GRANT SELECT TO PUBLIC` over-grants; `_safe_parse_hassotime` references non-existent `pd._TSNA` in its annotation; and `_transform_race_df` imports `datetime` inside a per-row loop.

## Critical Issues

### CR-01: `_row_to_tuple` mishandles `pd.NaT` on `race_date` — corrupted `date` column or INSERT failure

**File:** `src/etl/normalize.py:474-480`
**Issue:**
The `race_date` branch only guards `v is None or isinstance(v, float)`. But `pd.to_datetime(..., errors="coerce").dt.date` yields `pd.NaT` (not `None`, not `float`) when `(year, monthday)` produces an invalid date such as `"20200000"` (empty `monthday`).

`pd.NaT` has an `isoformat` attribute (`hasattr(pd.NaT, "isoformat") == True`; `pd.NaT.isoformat()` returns the literal string `"NaT"`). The current code therefore takes the `elif hasattr(v, "isoformat")` branch and appends `pd.NaT` to the tuple. psycopg3 has no registered adapter for `pd.NaT` on a `date` column, so this either errors mid-swap (the staging-swap transaction then rolls back, leaving `normalized.n_race` in the pre-swap state — silent ETL failure) or, if any string fallback is hit, writes the literal `"NaT"` into a `date` column (silent data corruption).

This bug differs structurally from the `race_start_datetime` branch (line 482-485), which correctly uses `pd.isna(v)`. The asymmetry is the smoking gun.

**Fix:**
```python
if c == "race_date":
    if v is None or pd.isna(v):
        vals.append(None)
    elif hasattr(v, "isoformat"):
        vals.append(v)
    else:
        vals.append(None)
```

Use `pd.isna(v)` (as the `race_start_datetime` branch already does) instead of the `isinstance(v, float)` check, because `pd.isna` correctly returns True for `pd.NaT`, `None`, `NaN`, and `pd.NA`.

### CR-02: `_check_cast_success` miscounts decimal `real` values as cast failures (futan = 57.5 flagged)

**File:** `src/etl/quality_gate.py:369-383`
**Issue:**
The check uses the regex `!~ '^[0-9]+$'` to flag rows that would fail an explicit cast. The comment says this is "CAST(kyori AS integer) と同等" (integer-only equivalent). The problem: `CAST_COLUMNS_N_UMA_RACE = ("futan",)`, and per `normalize.py` the schema is `"futan real"` (負担重量, 0.1kg unit). Every decimal weight value like `'57.5'`, `'54.0'`, `'58.5'` matches the `!~ '^[0-9]+$'` predicate because `.` is not in `[0-9]`.

As a result, the INFO report will declare ~100% of `futan` rows as cast failures on real data even though `CAST('57.5' AS real)` succeeds. This is not a verdict-failing BLOCK check (severity is `info`), but it makes the gate output misleading and undermines trust in the gate as a leak/correctness signal — exactly the kind of false-positive that erodes the gate's value as a Phase-1 acceptance signal. Worse, it could mask a *real* future regression: if all values look "broken", no one notices when one truly is.

**Fix:**
Use a numeric regex that accepts decimals (and optionally a leading sign) for `real` columns, or split the targets by type:
```python
# At module scope
CAST_REGEX_BY_TYPE = {
    "integer": r'^[0-9]+$',
    "real":    r'^[0-9]+(\.[0-9]+)?$',
}

# In _check_cast_success, look up the regex per (table, col)
col_type = "real" if (table, c) in {("n_uma_race", "futan")} else "integer"
pattern = CAST_REGEX_BY_TYPE[col_type]
cur.execute(
    f"""
    SELECT count(*) FROM {table}
    WHERE {JRA_ONLY_FILTER}
      AND {c} IS NOT NULL
      AND {c} !~ %s
    """,
    (pattern,),
)
```
Note also that the regex literal should ideally be passed via `%s` rather than f-string interpolation to keep the parameterization story consistent with the rest of the file.

## Warnings

### WR-01: `apply_category_map` relies on `astype(str)` to convert `NaN` → `'nan'`, then a later `.where(notna, MISSING)` masks it — fragile, and breaks if a category literally named `"nan"` ever appears

**File:** `src/utils/category_map.py:73-76`
**Issue:**
The implementation does:
```python
s = series.astype(str).where(series.notna(), MISSING)
```
Order matters: `astype(str)` runs first, converting `NaN` → the string `'nan'`. The subsequent `.where(notna, MISSING)` then replaces those positions with `MISSING` because their `notna` mask is False. This works *only* because `where`'s condition is checked on the **original** `series.notna()`, not on the post-`astype` string.

There are two fragility concerns:
1. If a future maintainer refactors to `s = series.where(series.notna(), MISSING).astype(str)` (a natural-looking reorder), `MISSING` would survive, but a real value `'nan'` in the source data would be indistinguishable from a converted NaN — they would both map to `code['__MISSING__']` because the second `astype(str)` happens after the substitution and there is no `MISSING` key in `code` until applied via `.map(code)`. Wait, `MISSING` IS a key in `code` so that's fine. But the inverse — calling `.fillna(MISSING)` before `astype(str)` — would still work. The real fragility is: **a legitimate category value of literally `"nan"` in training data would be encoded as a regular category by `fit_category_map`, but on the apply side, any actual NaN (whose `astype(str)` happens to produce `"nan"`) would collide with that legitimate category.** The current code's `.where(notna, MISSING)` happens to mask this because it replaces before `.map`, so NaNs become MISSING before the map lookup — but a maintainer who removes the `.where` line (since it looks redundant: "we already have a `__MISSING__` sentinel, why do we need a substitution?") would silently introduce NaN→`'nan'`→legitimate-category leakage.

2. The defensive intent is hidden behind an obscure two-step. The clearer pattern is `series.fillna(MISSING).astype(str).map(code).fillna(code[UNSEEN])`.

**Fix:**
```python
# Replace NaN with MISSING FIRST, then stringify, then map. No post-hoc .where needed.
s = series.fillna(MISSING).astype(str)
return s.map(code).fillna(code[UNSEEN]).astype("int32")
```
This removes the ordering dependency and makes the sentinel substitution explicit at the start of the pipeline. Add a unit test `test_apply_nan_string_not_confused_with_real_nan_category` that fits on a series containing a literal `"nan"` string and verifies that real NaNs still map to `MISSING` (not to the `"nan"` category).

### WR-02: `_idempotent_load` is atomic per-table but `n_race` + `n_uma_race` are not atomic together — partial-failure leaves inconsistent normalized state

**File:** `src/etl/normalize.py:515-552` (and `run_normalized_etl:579-588`)
**Issue:**
`_load_race` opens its own write connection and commits; `_load_uma_race` then opens another and commits. If `_load_uma_race` fails partway (e.g. PK violation on staging INSERT, OOM on the pandas side, connection drop), the normalized schema is left with a fresh `n_race` but a stale `n_uma_race` from a previous run (or no `n_uma_race` at all if it's the first run). The `§19.1` reproducibility requirement implies `(feature_snapshot_id, train_period, test_period)` triples, and a torn normalized state breaks the assumption that `n_race.row_count == n_uma_race.row_count_at_corresponding_races`.

**Fix:**
Either (a) document explicitly in the module docstring that `run_normalized_etl` is per-table-atomic and downstream consumers must treat the two tables as eventually-consistent, or (b) wrap both loads in a single write transaction:
```python
def run_normalized_etl(read_pool, write_pool, *, tables=None):
    ...
    with write_pool.connection() as wconn:
        with wconn.cursor() as wcur:
            if "n_race" in tables:
                # read+transform outside, but do all writes on wconn
                ...
                _create_normalized_tables(wcur)
                cnt_race = _idempotent_load(wcur, "n_race", rows_race, cols_race)
            if "n_uma_race" in tables:
                _create_normalized_tables(wcur)
                cnt_uma = _idempotent_load(wcur, "n_uma_race", rows_uma, cols_uma)
        wconn.commit()
```
Refactor `_idempotent_load` to accept a cursor and not manage its own connection.

### WR-03: `_idempotent_load` issues `GRANT SELECT ON normalized.{table} TO PUBLIC` — overbroad grant

**File:** `src/etl/normalize.py:380`
**Issue:**
`TO PUBLIC` grants SELECT to every role in the database, including the admin role, any future untrusted role, and the `PUBLIC` meta-role. The intent is to give the **reader** role access (because `ALTER DEFAULT PRIVILEGES` in `apply_schema.sql` does not cover tables created by the ETL role). The comment explains the workaround is needed because staging-swap creates a new OID each time.

For a local-only Streamlit single-user deployment this is low-impact, but it weakens the privilege story: any role that can connect to the DB now reads normalized data, including any role created for future label/prediction phases. This also doesn't extend the `REVOKE UPDATE/DELETE/TRUNCATE` from `apply_schema.sql` (which only applied to admin-created tables in `public`/`raw_everydb2`, not ETL-created `normalized.*` tables — so a misconfigured future role could in principle write to normalized, though that's not a raw-immutability concern).

**Fix:**
Pass the reader role name (from `Settings.db_user` or an explicit env var) into `_idempotent_load` and grant to that role specifically:
```python
write_cur.execute(
    sql.SQL("GRANT SELECT ON normalized.{} TO {}").format(
        sql.Identifier(table), sql.Identifier(reader_role)
    )
)
```
If that's too invasive for Phase 1, at minimum document that `TO PUBLIC` is intentional for the local-only deployment and add a TODO for Phase 2 (multi-user) hardening.

### WR-04: `_safe_parse_hassotime` annotation references non-existent `pd._TSNA`

**File:** `src/etl/normalize.py:248`
**Issue:**
```python
def _parse(v: Any) -> pd.Timestamp | pd._TSNA:  # noqa: SLF001
```
`pandas._TSNA` is not a public attribute and `hasattr(pd, "_TSNA")` returns `False`. The annotation is referenced at function definition time; under `from __future__ import annotations` (which this module uses) annotations are lazy-evaluated strings, so it doesn't crash at import. But it's misleading, unreachable as a real type, and breaks any runtime annotation introspection (e.g. `typing.get_type_hints` raises `AttributeError`).

**Fix:**
```python
def _parse(v: Any) -> pd.Timestamp | type(pd.NaT):
```
or simpler: `-> pd.Timestamp | None` since the function semantically returns either a valid `time` object or `pd.NaT` (which the caller treats as null).

### WR-05: `_transform_race_df` performs `import datetime as _dt` inside a per-row for-loop

**File:** `src/etl/normalize.py:289-291`
**Issue:**
```python
for d, t in zip(out["race_date"], time_parts, strict=False):
    ...
    else:
        import datetime as _dt
        race_dt.append(_dt.datetime.combine(d, t))
```
Python caches the import after the first iteration, so this is not a correctness bug, but it's a code smell that signals missing module-level hygiene. It also puts the slowest possible `import` lookup on the hot path of a per-row loop over potentially millions of JRA rows.

**Fix:**
Move `import datetime as _dt` to the top of the module (or use `from datetime import datetime`), then call `_dt.datetime.combine(d, t)` directly in the loop.

### WR-06: `_check_table_counts` and other INFO checks swallow exceptions and emit `{"error": str(exc)}` — error strings may leak SQL fragments into the report

**File:** `src/etl/quality_gate.py:261-268, 293-295, 340-341, 392-393, 425-426, 491-492, 512-513`
**Issue:**
Several INFO checks wrap their SQL execution in `try/except Exception` and store `str(exc)` into the check detail. The `_filter_check` allowlist in `scripts/run_quality_report.py` only filters top-level keys (`name/passed/severity/detail`), so raw exception strings still pass through to the JSON/Markdown report. PostgreSQL exception messages can contain schema-qualified table names, partial queries, and (if a future maintainer accidentally interpolates) other identifiers. The "T-02-02 二重防御" claim that the report "絶対に認証情報は含めない" is technically about credentials, but the same trust assumption (sanitized output) extends to any internal SQL structure that would aid an attacker.

This is a WARNING rather than a BLOCKER because the current SQL is parameterized for the high-risk checks (`_check_table_exists`, `_check_code_value_anomalies`), and the only thing in the error string is the user-controlled table name from `TARGET_TABLES` (a code constant). But the pattern is fragile.

**Fix:**
Replace `str(exc)` with a sanitized error code or a generic message:
```python
except Exception:  # noqa: BLE001
    columns[t] = {"error": "query_failed"}
    continue
```
If debug detail is needed for ops, route it through `logger.exception(...)` to stderr, not to the report.

### WR-07: `audit_gradecd_d_by_syubetucd` is exposed as a public API and runs raw SQL with f-string interpolation of `('C','D')` — works, but establishes a precedent that downstream query helpers can f-string SQL

**File:** `src/etl/class_normalize.py:242-248`
**Issue:**
The function builds and executes:
```python
sql = (
    "SELECT gradecd, syubetucd, count(*) AS count "
    "FROM public.n_race "
    "WHERE jyocd BETWEEN '01' AND '10' AND gradecd IN ('C','D') "
    "GROUP BY 1, 2 ORDER BY 1, 2"
)
read_cur.execute(sql)
```
There are no user-supplied parameters here, so there's no immediate injection vector. But this is the only public function in the ETL/utils layer that bypasses psycopg3 parameterization entirely. Future maintainers who copy this pattern with a parameter (e.g. `gradecd IN ({user_input})`) would introduce an injection sink. The project's MEDIUM #3 / T-02-02 mitigation story depends on **all** SQL going through `%s`/`Identifier` formatting.

**Fix:**
```python
read_cur.execute(
    "SELECT gradecd, syubetucd, count(*) AS count "
    "FROM public.n_race "
    "WHERE jyocd BETWEEN '01' AND '10' AND gradecd = ANY(%s) "
    "GROUP BY 1, 2 ORDER BY 1, 2",
    (["C", "D"],),
)
```

### WR-08: `conftest.readonly_cur` is function-scope and never explicitly commits/rolls back — long-running read transactions across tests

**File:** `tests/conftest.py:39-44`
**Issue:**
The `readonly_cur` fixture yields a cursor inside `pool.connection()` / `cursor()` context managers. psycopg3 starts a transaction on first execute and does not commit/rollback automatically when the cursor context exits (only the connection context commits/rolls back). The fixture exits the cursor context but not the connection context until the function-scope teardown, so each test using `readonly_cur` holds an open read transaction for the entire test body.

This is exactly why `test_etl_idempotent_rerun` (lines 221, 234) and `test_raw_unchanged_after_etl` (lines 57, 63) call `readonly_cur.connection.rollback()` manually — they need to release the snapshot before the ETL can `DROP TABLE normalized.n_race` without lock waits. The pattern is documented in those tests' comments, but it's a per-test landmine: any new test that runs ETL after a `readonly_cur.execute(...)` without explicit `rollback()` will hang on `DROP TABLE`.

**Fix:**
Add a finalizer to the `readonly_cur` fixture that rolls back the connection on teardown:
```python
@pytest.fixture
def readonly_cur(pg_pool):
    with pg_pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
        conn.rollback()  # release snapshot regardless of test outcome
```
Or, alternatively, configure the readonly pool's connections with `AUTOCOMMIT` since they're read-only.

### WR-09: `_check_cast_success` mixes `f-string` interpolated identifiers (`{table}`, `{c}`) without `sql.Identifier` quoting — relies on constants only, but inconsistent with project's parameterization story

**File:** `src/etl/quality_gate.py:328, 332, 367, 376-382, 416-421, 462, 476-483, 498-503`
**Issue:**
Every INFO check interpolates `{table}` and `{c}` (column names) via f-strings into the SQL. The values come from the constants `TARGET_TABLES`, `MOJIBAKE_COLUMNS_*`, `CAST_COLUMNS_*`, `table_cols`, and `code_columns`, all of which are code constants — so there is no immediate injection. But the same module also uses proper `%s` parameterization for `ANY(%s::text[])` and for `information_schema.tables WHERE table_name = %s`, creating an inconsistent style. A future maintainer who adds a parameterized column name from a YAML config or user input would have to remember which SQL template to follow.

**Fix:**
Either standardize on `psycopg.sql.SQL(...).format(sql.Identifier(table), sql.Identifier(c))` for all dynamic identifiers in this module, or add a `_assert_safe_identifier(name)` helper that rejects anything outside `[A-Za-z_][A-Za-z0-9_]*` and call it at every f-string site. The latter is cheaper for INFO queries.

## Info

### IN-01: `_mask_dsn` and `Settings.dsn_masked` mask the password but log the username + host + db in plaintext

**File:** `scripts/run_apply_schema.py:91-103`, `src/config/settings.py:73-87`
**Issue:**
The mask replaces only the password with `***`. The username, host, port, and database name are still logged. For the local-only single-user deployment this is intentional (the docstrings document this), but ASVS V8 typically treats the DB username as semi-sensitive. Worth noting for Phase 2 multi-user hardening.

**Fix:** Document this trade-off explicitly in `Settings.dsn_masked` docstring (it's already implicit) or add an `even_more_masked` property for verbose logs.

### IN-02: `run_apply_schema.py` uses bare `except Exception` and returns exit 1 with only `LOG.error` — stack trace is lost

**File:** `scripts/run_apply_schema.py:176-181`
**Issue:**
The top-level `try/except Exception` swallows the traceback. Operational debugging of DDL failures (e.g. role creation conflicts, permission errors) becomes harder.

**Fix:**
```python
except Exception:
    LOG.exception("apply failed")
    return 1
```
`LOG.exception` includes the traceback in the log output.

### IN-03: `_check_jra_since_2015` uses `(year||monthday) >= '20150101'` — works for the all-numeric varchar case, but is fragile to any non-digit padding in `monthday`

**File:** `src/etl/quality_gate.py:177-184`
**Issue:**
The string-concat-then-compare idiom assumes `year` is 4 digits and `monthday` is 4 digits (zero-padded). EveryDB2's `monthday` is varchar(4); if any value is unpadded (`'101'` for January 1st) the comparison silently misbehaves (`'2015101' >= '20150101'` is True but `'20150001'` would also be True due to lex order). The ETL side correctly uses `.str.zfill(4)` (`normalize.py:276`); the quality gate does not.

**Fix:**
Either `WHERE lpad(year, 4, '0') || lpad(monthday, 4, '0') >= '20150101'`, or filter on `year::int >= 2015 AND (year::int > 2015 OR monthday::int >= 101)` — but the cleanest is to use the ETL's `race_date` column from `normalized.n_race` once it exists.

### IN-04: `test_class_normalization.test_code_005_spans_reform` calls `normalize_class("005", "", date(2018, 6, 1))` — but the empty `gradecd` requires the `""` key to exist in `gradecd_map`

**File:** `tests/test_class_normalization.py:60-67`
**Issue:**
The test relies on `gradecd_map` containing an `""` (empty string) key. `class_normalization.yaml:89` does have it. This is an implicit contract between test and YAML; if a future maintainer removes the `""` entry (thinking it's a YAML oddity), the test breaks without an obvious cause.

**Fix:** Add an assertion in `load_class_config` that the empty-string gradecd entry exists, or add a test that explicitly asserts `"" in gradecd_map`.

### IN-05: `scripts/run_normalized_etl.py` swallows the AssertionError from `assert_raw_unchanged` and returns exit 2 — but the assertion message itself is logged with `%s`, losing traceback

**File:** `scripts/run_normalized_etl.py:75-80`
**Issue:**
The control flow is correct (return 2 on immutability failure), but `logger.error("raw 不変性確認: FAIL — %s", e)` discards the traceback. For a security-critical check (raw immutability is the inviolable core value per CLAUDE.md), losing the traceback makes incident response slower.

**Fix:** Use `logger.exception(...)` instead of `logger.error(..., e)` to capture the full stack.

### IN-06: `apply_schema.sql` declares `GRANT USAGE, CREATE ON SCHEMA normalized TO {etl}` in both the file (line 65) and `GRANT_ETL_SQL` constant — duplication between SQL file and Python module

**File:** `scripts/apply_schema.sql:65`, `src/db/schema.py:91`
**Issue:**
The same DDL is maintained in two places: `scripts/apply_schema.sql` (the human-edited source of truth) and `src/db/schema.py` (the programmatic constants used by `run_apply_schema.py`). `run_apply_schema.py` actually uses the Python constants, NOT the SQL file, even though it accepts `--sql-file` as a CLI argument and reads its contents (`sql_text = args.sql_file.read_text(...)`) — and then **ignores** `sql_text` entirely (look at line 174: it reads it; line 177: `apply(admin_dsn, reader, etl, sql_text, args.dry_run)` passes it; but `apply` only uses `sql_text` for `--dry-run` printing, the live execution uses `schema_module.CREATE_*_SQL` constants).

This means the `apply_schema.sql` file is decorative — editing it has no effect on what's applied unless `--dry-run` is passed. A maintainer who fixes a privilege issue in `apply_schema.sql` thinking it'll take effect will be surprised.

**Fix:**
Either (a) make `apply()` actually execute the parsed SQL from the file (split by `;` and apply each statement, with placeholder substitution), or (b) delete `scripts/apply_schema.sql` and document that `src/db/schema.py` is the single source of truth, or (c) generate `apply_schema.sql` from the constants in `schema.py` so they can't drift.

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
