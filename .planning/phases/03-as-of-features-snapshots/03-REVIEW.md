---
phase: 03-as-of-features-snapshots
reviewed: 2026-06-19T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - scripts/run_feature_build.py
  - scripts/run_label_race_date_backfill.py
  - src/config/feature_availability.yaml
  - src/etl/label_race_date_backfill.py
  - src/features/__init__.py
  - src/features/availability.py
  - src/features/builder.py
  - src/features/category_map_consumer.py
  - src/features/rolling.py
  - src/features/running_style.py
  - src/features/snapshot.py
  - tests/features/__init__.py
  - tests/features/conftest.py
  - tests/features/test_allowlist.py
  - tests/features/test_builder.py
  - tests/features/test_category_map_consumer.py
  - tests/features/test_pit_cutoff.py
  - tests/features/test_rolling.py
  - tests/features/test_running_style.py
  - tests/features/test_snapshot_repro.py
  - tests/test_label_race_date_backfill.py
findings:
  critical: 4
  warning: 9
  info: 5
  total: 18
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-19
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 3 is the leak-safety-critical phase and the implementation is unusually disciplined: strict `<` cutoff semantics, per-observation `obs_id` rolling windows, train-only category-map fitting, byte-reproducible Parquet writes, and staging-swap idempotency are all present and well-tested. The defensive engineering (advisory locks, rowcount re-verify, `assert_raw_unchanged`, disjoint banned/allowed column sets, fail-loud registry checks) is the strongest part of the codebase.

However, adversarial review surfaced four BLOCKER-tier defects:

1. **`rolling_babacd_*` and `rolling_timediff_*` features are silently always `__MISSING__`** — the rolling `babacd`/`timediff` source columns are never materialised into the history DataFrame (only `days_since_prev` is derived; `babacd`/`timediff` are not in `_HISTORY_DB_SELECT_COLUMNS` and not constructed in `_construct_derived_columns`). Eight registered feature columns (6 of which the registry lists as real features) will be written to Parquet as all-sentinel, defeating the column's purpose while still passing all registry/column-registration checks.
2. **`_fetch_feature_sources` does not apply `project_window_filter('nr')`** — the observation/history JOINs filter only the `ur` alias, so the JOIN against `normalized.n_race` is unfiltered. Any pre-2015 or NAR rows that leaked into `normalized.n_race` would multiply observation rows or add bogus races.
3. **`build_frozen_category_maps` train-window mask can silently expand to ALL rows** — if `race_date` is missing from the feature matrix (any future code path that builds from a synthetic/reduced frame), `train_mask` is set to all-`True`, fitting the map on val/test rows. This is a leak-safety regression waiting to happen and contradicts the module's own §14.3 contract.
4. **`load_category_maps` uses `joblib.load` on an untrusted path** — arbitrary code execution on Phase 4 model load; the same Phase that loaded the Parquet.

Plus nine warnings covering type-mismatch JOINs, missing `feature_cutoff_datetime` assertions in rolling, `estimated_running_style` built from non-cutoff-filtered history, the rolling `count_5` columns being in the reserved allowlist but the corresponding `mean_5/latest_5/sd_5` being separately registered (inconsistent contract surface), and others.

The leak-safety *invariants that are tested* (cutoff, race_id grouping, byte-repro) are sound. The defects below are in the *untested or under-tested* paths: feature coverage, JOIN filter scope, fallback branches, and the artifact-loading trust boundary.

---

## Critical Issues

### CR-01: `rolling_babacd_*` and `rolling_timediff_*` features are silently never populated (always `__MISSING__`)

**File:** `src/features/builder.py:73-91`, `src/features/builder.py:119-124`, `src/features/rolling.py:66-75`
**Issue:**

The `rolling` module reads source columns per `_SYSTEM_SOURCE`:
```python
_SYSTEM_SOURCE = {
    ...
    "timediff": ("timediff",),
    "babacd":   ("babacd",),
    ...
}
```
For these systems to produce real values, the `history` DataFrame passed to `build_rolling_features` must contain a `timediff` column and a `babacd` column. But:

1. `_HISTORY_DB_SELECT_COLUMNS` (builder.py:73-88) does **not** SELECT `timediff` or `babacd`.
2. `_DERIVED_HISTORY_COLUMN_NAMES` (builder.py:119-124) **claims** `timediff`/`babacd` are derived — but `_construct_derived_columns` (builder.py:162-204) only constructs `race_nkey`, `as_of_datetime`, and `days_since_prev`. It never constructs `timediff` or `babacd`.
3. The builder's own comment (builder.py:65-66) admits: *"timediff / babacd は normalized 層に存在しないため SELECT せず、当該 rolling 系統は rolling.py の D-13 sentinel 経路で `__MISSING__` 扱いとなる."*

Consequence: **six registered feature columns** (`rolling_timediff_{mean,latest,sd}_5`, `rolling_babacd_{mean,latest,sd}_5`) — listed in `feature_availability.yaml:193-213` and `285-305` as legitimate `history_allowed_post_race` features — are written to every snapshot as **always-`__MISSING__`** (NaN after the snapshot coercion). They will then be silently dropped or treated as missing by Phase 4 models, while the §12.4 metadata, manifest, registry, and `assert_matrix_columns_registered` all report them as real features.

This is silent feature corruption: the snapshot claims to carry 24 rolling features (8 systems × 3 axes) but in practice only 18 (6 systems × 3) ever carry signal. The contract is violated without any test catching it, because `test_rolling.py` only exercises `timediff` against the **synthetic** `_build_adversarial_rolling_rows` fixture (which hard-codes a `timediff` key into the dict) — it never exercises the end-to-end builder path.

The `timediff` value (勝馬差 / `TimeDIFN`) is also one of the more informative rolling features per the Phase design notes, so its absence degrades model quality.

**Fix:** Either (a) add `timediff`/`babacd` to `_HISTORY_DB_SELECT_COLUMNS` if they exist under different names in the normalized layer (and document the aliasing), or (b) derive them in `_construct_derived_columns` from columns that DO exist, or (c) if they genuinely cannot be sourced in Phase 1-A, **remove the six entries from `feature_availability.yaml`** and add a `Deferred` note rather than registering features that are structurally guaranteed to be sentinel. Option (c) is the minimum correctness fix. Add a unit test that builds a snapshot from a synthetic DB-mock and asserts `rolling_timediff_mean_5` is **not universally NaN** when the underlying source has signal.

```python
# Minimum fix (option c): remove the six entries from feature_availability.yaml
# and from _ROLLING_SYSTEMS / _SYSTEM_SOURCE so the registry and the rolling
# impl agree. Document the deferral in 03-VERIFICATION.md.
```

---

### CR-02: Observation/history JOINs do not apply `project_window_filter('nr')` — JOIN side is unfiltered

**File:** `src/features/builder.py:392-397` (`_fetch_feature_sources`), `src/features/builder.py:439-444` (`_fetch_history`)
**Issue:**

Both SELECT queries build:
```python
obs_sql = (
    f"SELECT {obs_cols} FROM normalized.n_uma_race ur "
    f"JOIN normalized.n_race nr ON (...) "
    f"WHERE {project_window_filter('ur')}"   # only ur filtered
)
```
The `WHERE` clause filters only `ur` (year ≥ 2015, JRA jyocd 01–10). The joined `nr` (normalized.n_race) side is constrained only by the JOIN keys. CR-06 explicitly mandates `project_window_filter` on **both sides** of every JOIN — see `label_race_date_backfill.py:140-149` which applies `project_window_filter('fl')` AND `project_window_filter('nr')`, and `test_label_race_date_backfill.py:106-119` which asserts both.

If `normalized.n_race` ever contains a row whose `(year, jyocd, kaiji, nichiji, racenum)` matches a `ur` row but whose own `year`/`jyocd` columns carry a different value (possible if the normalization ETL ever leaves a duplicate-keyed or pre-2015/NAR row in `n_race`), the JOIN would still succeed and emit a row whose `nr.race_date` / `nr.race_start_datetime` are sourced from the unfiltered side. The `class_code_normalized` column (also from `nr`) would likewise be unfiltered.

The Phase-3 feature tests use synthetic DataFrames and never exercise this SQL, so the gap is invisible to CI.

**Fix:** Apply the filter to both aliases, matching the backfill module's CR-06 contract:
```python
obs_sql = (
    f"SELECT {obs_cols} FROM normalized.n_uma_race ur "
    f"JOIN normalized.n_race nr ON (...) "
    f"WHERE {project_window_filter('ur')} AND {project_window_filter('nr')}"
)
```
Add a structural test (`inspect.getsource(_fetch_feature_sources)` contains `project_window_filter('nr')`) mirroring the backfill test.

---

### CR-03: `build_frozen_category_maps` falls back to ALL-rows training when `race_date` is absent — silent test-composition leak

**File:** `src/features/category_map_consumer.py:176-186`
**Issue:**

```python
race_date_col = (
    pd.to_datetime(feature_matrix["race_date"])
    if "race_date" in feature_matrix.columns
    else None
)
if race_date_col is not None:
    train_mask = race_date_col.between(train_window[0], train_window[1])
else:
    # race_date が無い場合は全行を train 扱い（unit test の合成 DataFrame 向け）。
    train_mask = pd.Series([True] * len(feature_matrix))
```

The else-branch silently fits the category map on **the entire frame** whenever `race_date` is missing. This is documented as "for unit tests" but the function is the **public API** called from `scripts/run_feature_build.py:154` on the production feature matrix. If any future refactor (or a partial-frame DataFrame path) drops the `race_date` column before this call, the map will be fit on val/test rows with no error raised — exactly the §14.3 leak the rest of the module exists to prevent. Fail-loud is the project's stated contract ("D-13 silent fallback 禁止"); this is a silent fallback that violates it.

The same anti-pattern appears in `builder.py:348-353` for the canonical-key assertion (silently skipped if `race_nkey` not in columns) — but there the consequence is a missing assertion, not a leak. Here the consequence is a leak.

**Fix:** Require `race_date` and fail loud:
```python
if "race_date" not in feature_matrix.columns:
    raise ValueError(
        "build_frozen_category_maps: feature_matrix に race_date 列が無い "
        "(train 窓 mask を計算できない・Pitfall 3.4 / §14.3・D-13 fail-loud)"
    )
race_date_col = pd.to_datetime(feature_matrix["race_date"])
train_mask = race_date_col.between(train_window[0], train_window[1])
```
Unit tests that need synthetic frames should add a `race_date` column inside the train window.

---

### CR-04: `load_category_maps` uses `joblib.load` on an attacker-controllable artifact path (arbitrary code execution)

**File:** `src/features/category_map_consumer.py:255-257`
**Issue:**

```python
def load_category_maps(artifact_path: str | Path) -> dict[str, FrozenCategoryMap]:
    """永続化された frozen category maps を読み込む（Phase 4 モデル学習時使用）。"""
    return joblib.load(artifact_path)
```

`joblib.load` (which internally uses `pickle.load`) executes arbitrary code in the unpickled object's `__reduce__` / `__setstate__`. The category-map artifact (`snapshots/category_map_<snapshot_id>.joblib`) is therefore a code-execution vector. While the snapshot directory is currently local-only, the project's reproducibility model (§19.1) explicitly contemplates sharing snapshots across machines/runs, and the manifest records the artifact path as a reproducibility handle. A tampered or substituted `.joblib` would execute on Phase 4 load with the training process's privileges.

By contrast, the Parquet snapshot is loaded via PyArrow (no arbitrary code). The category map is the one pickle-shaped artifact in the Phase-3 output set.

**Fix:** Persist the category maps as JSON (they are `dict[str, dict[str, int]]`) and load with `json.load`. `FrozenCategoryMap` already exposes `.items()` / dict-style access — JSON round-trip is trivial:

```python
import json

def persist_category_maps(maps, artifact_path):
    Path(artifact_path).parent.mkdir(parents=True, exist_ok=True)
    serialisable = {col: dict(m.items()) for col, m in maps.items()}
    Path(artifact_path).write_text(json.dumps(serialisable, sort_keys=True), encoding="utf-8")

def load_category_maps(artifact_path):
    raw = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    return {col: FrozenCategoryMap(m) for col, m in raw.items()}
```
This also makes the artifact byte-reproducible (the current joblib output is not asserted to be deterministic, unlike the Parquet) and human-auditable.

---

## Warnings

### WR-01: `estimated_running_style` is computed from non-cutoff-filtered history — uses ALL past races including those after the observation's cutoff

**File:** `src/features/builder.py:329-339`
**Issue:**

```python
if len(history) > 0 and "kettonum" in history.columns and len(feature_matrix) > 0:
    style_map: dict[Any, str] = {}
    for kn, group in history.groupby("kettonum"):
        rows = group[["jyuni3c", "jyuni4c"]].to_dict(orient="records") ...
        style_map[kn] = estimate_running_style(rows)
    feature_matrix["estimated_running_style"] = (
        feature_matrix["kettonum"].map(style_map).fillna("__MISSING__")
    )
```

The `history` DataFrame here is the raw `_fetch_history` output (all races for each horse). For a target observation on race_date D, the `style_map` for that horse is computed from **all** of the horse's historical rows **including races after D** (e.g., a horse with target obs in 2020 gets a running-style estimate informed by its 2023 races). This is a look-ahead leak — the running-style feature is supposed to be `history_allowed_post_race` per the registry (i.e., past races only, with the same `as_of < cutoff` PIT filter that rolling applies).

The rolling module applies the cutoff filter; this code path does not. The `feature_availability.yaml:355-361` entry declares `estimated_running_style` as `cutoff_rule: "race_date - 1 day (strict < cutoff)"` — the implementation violates its own declared cutoff rule.

**Fix:** Apply the same PIT pre-filter before computing the style map. Either (a) build the per-horse history windows via the same `obs_id`/cutoff logic rolling uses, or (b) at minimum, for each observation, filter `history[history.as_of_datetime < obs.feature_cutoff_datetime]` before grouping. Option (a) is correct; (b) requires per-observation computation.

### WR-02: `build_rolling_features` does not assert `feature_cutoff_datetime` dtype consistency before the `<` comparison

**File:** `src/features/rolling.py:193-195`
**Issue:**

```python
history_filtered = expanded[
    expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
].copy()
```

If either column is object-dtype (e.g., strings from a mis-built synthetic frame) the `<` comparison falls back to lexicographic string ordering, which is correct for ISO8601 strings but **wrong** for mixed/naive formats. The function validates column *presence* (`missing_obs` / `missing_hist`) but not dtype. `builder._construct_derived_columns` does call `pd.to_datetime(...)`, but rolling is a public API also exercised directly by tests with hand-built frames (see `test_rolling.py:33`, which builds `feature_cutoff_datetime` from `pd.Timestamp` — safe; but the contract is not enforced).

**Fix:** Add a dtype check at the top of `build_rolling_features`:
```python
for col in ("feature_cutoff_datetime",):
    s = observations[col]
    if not pd.api.types.is_datetime64_any_dtype(s):
        observations[col] = pd.to_datetime(observations[col])
for col in ("as_of_datetime",):
    if not pd.api.types.is_datetime64_any_dtype(history[col]):
        history[col] = pd.to_datetime(history[col])
```

### WR-03: `blood_sql` (`public.n_uma`) is unfiltered — no JRA / project-window filter, no NULL-handling beyond `kettonum`

**File:** `src/features/builder.py:400-404`
**Issue:**

```python
blood_sql = (
    "SELECT kettonum::int AS kettonum, ketto3infohansyokunum1, "
    "ketto3infohansyokunum2 FROM public.n_uma "
    "WHERE kettonum IS NOT NULL AND kettonum ~ '^[0-9]+$'"
)
```

`public.n_uma` is a **raw**-layer table (it appears in `feature_availability.yaml:97,104` as `source_table: public.n_uma`). Reading it without any project-window filter means bloodline IDs (`sire_id`, `bms_id`) are sourced from the full EveryDB2 horse master, including horses that never appear in any JRA race. This is benign for the LEFT JOIN (extra `n_uma` rows just don't match), but it (a) pulls unnecessary data, (b) means a `sire_id`/`bms_id` could in principle be present for a non-JRA-context horse and silently populate the feature, and (c) is inconsistent with the project's "every raw SELECT is window-filtered" stance.

More concretely: `kettonum::int` cast will fail at runtime if any `kettonum` value exceeds int32 range or is non-numeric-but-passes the regex (the regex `^[0-9]+$` is fine, but the cast happens before the WHERE in the planner's reading order is not guaranteed; in practice Postgres evaluates WHERE first, so this is OK — but worth a comment).

**Fix:** This is a WARNING not a BLOCKER because the LEFT JOIN absorbs the impact. Add a comment justifying the unfiltered read, or apply a `EXISTS (SELECT 1 FROM normalized.n_uma_race ur WHERE ur.kettonum::int = n_uma.kettonum::int AND <window_filter>)` subquery to limit to JRA-context horses.

### WR-04: `kettonum` JOIN type-mismatch: `n_uma.kettonum` (varchar) cast to int vs `n_uma_race.kettonum` (integer) — silent row drop on cast failure

**File:** `src/features/builder.py:399-404, 421-422`
**Issue:**

The comment states the cast is needed to align types, and the regex guard prevents cast failure on the `n_uma` side. But the subsequent merge `obs_df.merge(blood_df, on="kettonum", how="left")` (builder.py:422) joins on `kettonum` as pandas sees it — `obs_df.kettonum` is whatever type `ur.kettonum` returned as (likely int from normalized layer), and `blood_df.kettonum` is the cast-to-int. If types differ (e.g., `obs_df.kettonum` is `Int64` nullable and `blood_df.kettonum` is `int64`), the merge can silently produce NaN bloodline IDs for matching horses. The `Int64`/`int64` mismatch is a known pandas merge footgun.

**Fix:** Explicitly cast both sides to the same nullable dtype before merge:
```python
obs_df["kettonum"] = pd.to_numeric(obs_df["kettonum"], errors="coerce").astype("Int64")
blood_df["kettonum"] = pd.to_numeric(blood_df["kettonum"], errors="coerce").astype("Int64")
```

### WR-05: `running_style.estimate_running_style_batch` has unreachable/undefined type annotation (`pd.Series` referenced before `import pandas`)

**File:** `src/features/running_style.py:104-129`
**Issue:**

```python
def estimate_running_style_batch(
    history_by_horse: Any,
) -> pd.Series:  # noqa: F821 (pandas import below for type only)
    ...
    import pandas as pd
    def _per_group(group: pd.DataFrame) -> str:  # noqa: F821
        ...
```

The `-> pd.Series` and `pd.DataFrame` annotations reference `pd` before the function-body `import pandas as pd`. At function *definition* time Python evaluates annotations lazily only if `from __future__ import annotations` is active (it is — line 15), so the annotation is stored as a string and does not raise. But the function is also **never called**: `builder.py:330-337` implements its own inline `groupby` + `estimate_running_style(rows)` loop rather than calling `estimate_running_style_batch`. This is dead code with a misleading "vectorized 版" docstring claiming it's the builder's path.

**Fix:** Either delete `estimate_running_style_batch` (it's unused) or wire the builder to actually call it. Dead code claiming to be the production path is a maintenance trap.

### WR-06: `assert_matrix_columns_registered` allows `*_code` for **any** column name, not just `_CATEGORY_COLUMNS`

**File:** `src/features/availability.py:259-262`
**Issue:**

```python
allowed |= {f"{c}_code" for c in _CATEGORY_COLUMNS}
```
This is correctly scoped. **However**, the next check:
```python
banned_leak = TARGET_OBS_BANNED_COLUMNS & allowed
```
only checks `TARGET_OBS_BANNED_COLUMNS`. A column like `kyakusitukubun_code` would **not** be in `allowed` (since `kyakusitukubun` is not in `_CATEGORY_COLUMNS`), so it would be rejected — good. But the registry check has no guard against a future `_CATEGORY_COLUMNS` addition that accidentally overlaps a banned source name (e.g., someone adds `"odds"` to `_CATEGORY_COLUMNS`, producing `odds_code` as an allowed output). There's no `assert _CATEGORY_COLUMNS.isdisjoint(TARGET_OBS_BANNED_COLUMNS)` invariant.

**Fix:** Add at module load:
```python
assert _CATEGORY_COLUMNS.isdisjoint(TARGET_OBS_BANNED_COLUMNS), (
    "_CATEGORY_COLUMNS と TARGET_OBS_BANNED_COLUMNS が交差している (HIGH #3 fail-loud 無意味化)"
)
```

### WR-07: `run_feature_build.py` writes the snapshot twice to the **same path** — second write silently overwrites the first, and the byte-repro assertion cannot detect a single-write corruption

**File:** `scripts/run_feature_build.py:171-198`
**Issue:**

```python
sha1 = write_snapshot(coded_matrix, out_dir=_SNAPSHOTS_DIR, snapshot_id=args.snapshot_id, ...)
sha2 = write_snapshot(coded_matrix, out_dir=_SNAPSHOTS_DIR, snapshot_id=args.snapshot_id, ...)
assert sha1 == sha2, ...
```
Both writes target `feature_matrix_{snapshot_id}.parquet` — the same file. The second `open(parquet_path, "wb")` truncates and overwrites. The byte-repro check therefore proves only that `write_snapshot` is deterministic **in-buffer**, not that the on-disk file matches the in-buffer SHA. A filesystem-level corruption between `buf.getvalue().to_pybytes()` and `f.write(data)` (e.g., disk full, signal interruption) on write #2 would corrupt the file while `sha2` (computed from the buffer) still matches `sha1`. The on-disk file is never re-hash-verified.

**Fix:** After writing, re-read the file and re-hash:
```python
with open(parquet_path, "rb") as f:
    on_disk_sha = hashlib.sha256(f.read()).hexdigest()
assert on_disk_sha == sha1, (
    f"on-disk Parquet SHA256 mismatch: {on_disk_sha} != {sha1}"
)
```
This is the actual byte-reproducibility guarantee the manifest's `sha256` field promises. Remove the redundant double-write or write to two distinct temp paths and compare.

### WR-08: `run_feature_build.py` swallows `MemoryError` and returns exit 4 without cleanup of partial snapshot files

**File:** `scripts/run_feature_build.py:243-251`
**Issue:**

On `MemoryError`, the script returns 4 and logs an "escape hatch" message, but if the OOM occurs **after** `write_snapshot` #1 has already written `feature_matrix_{snapshot_id}.parquet` (and before the manifest is written), the snapshot directory is left with a half-written artefact: Parquet present, manifest absent, category map absent. The next run might pick up the orphan Parquet assuming it's complete. The `finally: read_pool.close()` cleans up the pool but not the filesystem.

**Fix:** Wrap the build steps in a try/except that, on any failure after the first `write_snapshot`, deletes `feature_matrix_{snapshot_id}.*` and `category_map_{snapshot_id}.*` to avoid orphan artefacts. Or use atomic write-then-rename (`tmp` → final) so a crash never leaves a final-named partial.

### WR-09: `feature_availability.yaml` registers `rolling_*_count_5` columns only in the `availability._RESERVED_NON_FEATURE_COLUMNS` allowlist — but rolling.py **emits** them as output columns, so they are quasi-features with no registry entry describing their semantics

**File:** `src/config/feature_availability.yaml` (entire `features:` list), `src/features/availability.py:144-160`, `src/features/rolling.py:163-168`
**Issue:**

The 8 `rolling_<system>_count_5` columns are emitted by `build_rolling_features` and placed in `_RESERVED_NON_FEATURE_COLUMNS` (availability.py:160) so they bypass the registry check. But they are feature-shaped (per-observation numeric values consumed by the model) and are not key/audit columns like `race_nkey` / `feature_snapshot_id`. The reserved-allowlist mechanism was designed for true management columns; using it for `count_5` blurs the contract. The `mean_5`/`latest_5`/`sd_5` variants **are** registered as features; the `count_5` variant is not, despite all four being emitted by the same code path with the same source-role semantics.

**Fix:** Either register all 8 `rolling_<system>_count_5` entries in `feature_availability.yaml` (consistent with the 24 mean/latest/sd entries), or document explicitly in the YAML why `count_5` is reserved rather than registered. The current state is an inconsistency that future readers will trip over.

---

## Info

### IN-01: `_ROLLING_SYSTEMS_FOR_RESERVED` duplicates `_ROLLING_SYSTEMS` from `rolling.py`

**File:** `src/features/availability.py:127-138`
**Issue:** The comment explains the duplication as "avoiding a circular import," but `availability.py` already imports nothing from `rolling`, and `rolling.py` imports `CUTOFF_SEMANTICS` from `availability` (one-directional). Adding `from src.features.rolling import _ROLLING_SYSTEMS` would not create a cycle. The duplication means a future edit to one tuple (e.g., dropping `babacd` per CR-01) must be mirrored manually in two files; if forgotten, the reserved-allowlist will silently disagree with the rolling impl.
**Fix:** Import `_ROLLING_SYSTEMS` from `rolling` in `availability`, or move the canonical tuple to a third tiny module both import.

### IN-02: `make_race_nkey` zero-pads `nichiji` to 2 digits — but `nichiji` semantics (回日 vs 開催日) may exceed 99

**File:** `src/features/builder.py:135-159`
**Issue:** `nichiji` is zero-filled to width 2. JRA `kaiji`/`nichiji` are typically small (≤ 12), so 2 digits is safe for current JRA data, but there is no assertion guarding against a wider value silently truncating the zero-fill semantics (a 3-digit value would just not be zero-padded, breaking fixed-width key equality). Low risk in practice.
**Fix:** Add a comment documenting the assumed domain (`nichiji < 100`) or assert it during build.

### IN-03: `snapshot.py` `_coerce_rolling_columns_for_parquet` silently converts `__MISSING__` to NaN — information loss at the Parquet boundary

**File:** `src/features/snapshot.py:79-102`
**Issue:** The D-13 contract distinguishes `__MISSING__` (5-starts-under / new horse) from a numeric value. At Parquet-write time, `__MISSING__` is collapsed to NaN, so Phase 4 cannot distinguish "feature genuinely missing" from "feature computed as NaN due to coerce failure." This is documented but worth flagging: the §14.5 "distinguish missing reasons" guarantee does not survive into the Parquet. If Phase 4 needs the distinction, a parallel boolean column (`<col>_was_missing`) would be needed.
**Fix:** Document this loss explicitly in the snapshot docstring and in 03-VERIFICATION.md as a known tradeoff, or add `_was_missing` companion columns if Phase 4 needs it.

### IN-04: `conftest.py:_build_adversarial_rolling_rows` adds a non-DB column `row_label` that flows into the rolling DataFrame

**File:** `tests/features/conftest.py:124-126`
**Issue:** The `row_label` column is harmless (rolling only reads `_SYSTEM_SOURCE` columns) but it ends up in the `history` DataFrame passed to `build_rolling_features`, and could mask a bug where rolling accidentally propagates unknown columns. Not a production issue (test fixture only).
**Fix:** Optionally drop `row_label` before passing to rolling, or assert rolling output does not contain it.

### IN-05: `label_race_date_backfill._RACE_LEVEL_JOIN_KEYS` comment claims "1:N JOIN で行増殖は起きない" but the staging INSERT SELECT has no DISTINCT — relies entirely on join-key cardinality

**File:** `src/etl/label_race_date_backfill.py:57-62`
**Issue:** The comment is correct (`race_date` is race-level constant, so even a 1:N JOIN produces N rows with the same `race_date` per key — but the INSERT column list is the **full** `fukusho_label` row including SE-level `umaban`, so the row count is preserved). The reasoning is sound but fragile: if `normalized.n_race` ever has duplicate race-level keys (a normalization bug), the JOIN would multiply rows and the WR-06 rowcount check would catch it. Good defense in depth; flagging only because the comment's certainty ("起きない") is stronger than the code's guarantee.
**Fix:** Soften comment to "rowcount verify (WR-06) catches any accidental multiplication."

---

_Reviewed: 2026-06-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
