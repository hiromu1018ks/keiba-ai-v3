# Stack Research

**Domain:** JRA horse-racing prediction ML system (place-bet / 複勝 payout-eligibility probability `p_fukusho_hit` estimation + EV evaluation)
**Researched:** 2026-06-16
**Confidence:** HIGH (versions verified against PyPI JSON API on 2026-06-16; leakage-prevention guidance cross-checked against official LightGBM/CatBoost/scikit-learn docs and the original CatBoost NeurIPS paper)

## Scope note

The requirements doc (`docs/keiba_ai_requirements_v1.3.md` §17.1) **fixes** the stack. This research does NOT propose replacing it. It verifies each fixed component's current (2026) version, recommended configuration, interop patterns, and — critically — the leakage-prevention pitfalls the requirements doc calls out (§13 as-of, §14.3–14.5 categorical/missing, §15 calibration/validation). Where the fixed stack has a known sharp edge that bites JRA-style time-series panel data, the recommendation is a configuration or auxiliary library, not a swap.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.12 (3.13 NOT recommended; 3.11 fallback) | Runtime | Requirements-fixed (§17.1). 3.12 is the stable sweet spot: LightGBM 4.6, CatBoost 1.2.10, scikit-learn 1.9, DuckDB 1.5 all ship 3.12 wheels. **Avoid 3.13** for Phase 1: CatBoost/older binary wheels and some scientific stacks still lag on 3.13 in mid-2026. Verified: `python3.12.13` present on host. Confidence: HIGH. |
| **uv** | ≥0.11 (host has 0.11.21) | Dependency + venv + Python management | Requirements-fixed (§17.1). Single tool replaces pip/pip-tools/venv/pyenv. Lockfile (`uv.lock`) gives byte-reproducible installs — directly serves §19.1 reproducibility. Use `uv sync --frozen` in CI/scripts and pin `requires-python = ">=3.12,<3.13"`. Confidence: HIGH. |
| **LightGBM** | 4.6.0 | Primary GBDT for `p_fukusho_hit` | Requirements-fixed (§14.1/§14.3). Native categorical splitting uses Fisher's optimal partition on feature **values only** — the split-finder never sees the target during encoding, so it is **structurally incapable of target-encoding leakage** (unlike mean/target encoding). ~8x faster than one-hot on high-cardinality features per official docs. Confidence: HIGH. |
| **CatBoost** | 1.2.10 | Comparison GBDT + the leak-safe categorical baseline | Requirements-fixed (§14.1/§14.4). Its **ordered target statistics** + ordered boosting are explicitly designed to prevent the prediction-shift leakage that vanilla target encoding causes (Prokhorenkova et al., NeurIPS 2018). `has_time=True` makes it time-series-correct. CatBoost is the one model in the comparison that is *provably* leak-safe on categoricals out of the box — strong reason to keep it in the Phase 1 bake-off even if LightGBM wins. Confidence: HIGH. |
| **scikit-learn** | 1.9.0 | Calibration, metrics, baselines, splitters | Requirements-fixed (§14.1/§14.2). Provides `CalibratedClassifierCV`, `brier_score_loss`, `log_loss`, `TimeSeriesSplit`, and the BL-4 logistic-regression baseline. requires-python `>=3.11` so 3.12 is fully supported. Confidence: HIGH. |
| **PostgreSQL** | 15.x (host: 15.18 Homebrew) | Primary DB (raw / normalized / label / prediction / backtest layers) | Requirements-fixed (§5/§12.1). 15 is the Homebrew default on the host and is well within JRA-VAN/EveryDB2 compatibility envelope. No reason to force-upgrade to 16/17 in Phase 1 — EveryDB2's schema and ODBC drivers are validated against 14/15. Confidence: HIGH. |
| **DuckDB** | 1.5.3 (Python wheel; no CLI needed) | Auxiliary OLAP engine for Parquet + large aggregations | Requirements-fixed (§5.2/§12.1) as **auxiliary only**. Use it for the things Postgres is bad at: scanning Parquet snapshots, vectorised group-by over millions of horse-starts, ad-hoc as-of aggregations. Do NOT make it a persistence layer — requirements explicitly forbid treating it as a running DB. Confidence: HIGH. |
| **Parquet** (via PyArrow) | pyarrow 24.0.0 | Training datasets + feature snapshots (§12.4) | Requirements-fixed. Columnar + schema + row-group partitioning; embeds the §12.4 metadata (`dataset_version`, `feature_snapshot_id`, `feature_cutoff_datetime`, …) as Parquet key/value metadata. PyArrow is the canonical writer; DuckDB reads it zero-copy. Confidence: HIGH. |
| **Streamlit** | 1.58.0 | Local-only UI (§16.1) | Requirements-fixed. Local single-user; no auth needed. Use `st.cache_data` for Parquet/DB reads, never `st.session_state` for derived data. Confidence: HIGH. |
| **Git** | any recent | Version control (code + requirements; NOT data) | Requirements-fixed. Keep `data/`, `models/`, Parquet out of Git (use `.gitignore`). LFS is unnecessary if Parquet lives on disk. Confidence: HIGH. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pandas** | 3.0.3 | DataFrames, the lingua franca of feature/label code | Default in-memory format for ETL & feature generation. **Critical function**: `pandas.merge_asof(direction='backward')` is the leak-safe point-in-time join primitive (see Architecture section). Note: pandas 3.x dropped Python 3.10 — fine, we're on 3.12. Confidence: HIGH. |
| **NumPy** | (transitive, ≥2.0) | Array ops | Comes via pandas/sklearn. Pin nothing explicit unless a binary-wheel conflict surfaces. Confidence: HIGH. |
| **psycopg** | 3.3.4 (psycopg[binary]) | PostgreSQL driver (psycopg3) | Default Postgres driver. Use the **psycopg3** line (`psycopg[binary]`), NOT the legacy `psycopg2`. Pool with `psycopg_pool.ConnectionPool` for the Streamlit app & ETL. SQLAlchemy 2.0.51 is available if an ORM layer is wanted, but raw psycopg3 + tiny query helpers are enough for Phase 1 (requirements say keep it simple, §12.1). Confidence: HIGH. |
| **DuckDB** (Python) | 1.5.3 | `duckdb.sql(...)` over pandas/Parquet, `read_parquet()`, `postgres_scanner` ext | Ad-hoc aggregation over Parquet snapshots; `duckdb.sql("COPY ... TO 'x.parquet'")` to materialise Postgres → Parquet (see Interop section). Confidence: HIGH. |
| **PyArrow** | 24.0.0 | Parquet read/write, Arrow zero-copy bridge pandas↔DuckDB | Always — it's how Parquet snapshots move between DuckDB and pandas without copies. Confidence: HIGH. |
| **mlxtend** | latest (4.x) | `GroupTimeSeriesSplit` — **group-aware time-series CV** | REQUIRED for race_id-level integrity. scikit-learn's `TimeSeriesSplit` is **NOT group-aware** (scikit-learn issue #19072, still open): it can split rows of the same `race_id` across train/test, violating §8.4/§15.4. `mlxtend.evaluate.GroupTimeSeriesSplit` keeps whole `race_id` groups on one side while preserving time order. See Validation section. Confidence: HIGH (the gap it fills is well-documented). |
| **SciPy** | transitive | `scipy.stats` for calibration/stability tests | Comes via scikit-learn. Confidence: HIGH. |
| **pytest** | 9.1.0 | Test runner (§17.3 mandates tests for label/PIT/split logic) | Required — the §17.3 test list is exactly the high-leakage-risk surface that needs unit tests. Confidence: HIGH. |
| **ruff** | 0.15.17 | Lint + format | Default Python linter/formatter for 2026; replaces flake8+black+isort. Confidence: HIGH. |
| **Jupyter / ipykernel** | latest | `notebooks/` exploratory analysis | Exploration only — production code must live in `src/`. Pin nothing aggressive. Confidence: MEDIUM (optional but expected per §17.2 layout). |
| **matplotlib / plotly** | latest | Calibration curves, stability plots (§15.1/§15.3) | Needed to render the per-year/per-course/per-field-size calibration curves the acceptance criteria require. Plotly plays nicer with Streamlit. Confidence: HIGH. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | venv + lockfile + Python install | `uv init --package`, `uv add`, `uv sync --frozen`. Lock `requires-python` to `>=3.12,<3.13`. |
| **ruff** | lint/format | `ruff check` + `ruff format`. Single config in `pyproject.toml`. |
| **pytest** | unit tests | Test the leakage surfaces: label generation, PIT cutoff, race_id-grouped splits, odds-snapshot policy, refund rules. |
| **pre-commit** (optional) | guard rails | Run ruff + pytest fast subset before commit. Optional; uv scripts can substitute. |
| **psql** (15.18 on host) | manual DB inspection | Quality checks per §6.4. |
| **DuckDB CLI** (optional) | ad-hoc Parquet/SQL exploration | Not installed on host (Python wheel suffices). Install via `uv tool install duckdb` if a REPL is wanted. |

## Installation

Use uv. Single `pyproject.toml`; no separate requirements files.

```bash
# Project bootstrap
uv init --package --python 3.12 keiba-ai-v3
cd keiba-ai-v3

# Core modeling stack (requirements §17.1)
uv add "lightgbm==4.6.0" "catboost==1.2.10" "scikit-learn==1.9.0"

# Data layer
uv add "pandas==3.0.3" "pyarrow==24.0.0" "duckdb==1.5.3" "psycopg[binary]==3.3.4"

# UI + viz
uv add "streamlit==1.58.0" plotly

# Leak-safe time-series CV (fills sklearn gap)
uv add "mlxtend>=4.0"

# Dev
uv add --dev ruff pytest pytest-cov jupyter ipykernel pre-commit
```

Lock the runtime in `pyproject.toml`:
```toml
[project]
requires-python = ">=3.12,<3.13"
```
Reproducibility (§19.1): commit `uv.lock`. Anyone running `uv sync --frozen` gets identical transitive versions.

## Leakage-prevention configuration (the critical part)

This is where Phase 1 lives or dies. The requirements doc names the leaks to prevent (§13, §14.3–14.5, §15.4); below is the concrete configuration for each.

### 1. Categorical handling — LightGBM (§14.3)

**Recommendation:** use **pandas `category` dtype**, let LightGBM auto-extract codes. Do NOT hand-target-encode.

```python
for c in CAT_COLS:                       # jockey_id, trainer_id, sire_id, course, class_code, ...
    df[c] = df[c].astype("category")

dset = lgb.Dataset(
    df[FEATS],
    label=df["fukusho_hit_validated"],
    categorical_feature=CAT_COLS,        # explicit; belts-and-braces
    free_raw_data=False,
)
```

- **Why leak-safe:** LightGBM's native categorical splitter finds the optimal **value-based** partition (Fisher, 1958) — the split search uses only the feature values, never the target. This is structurally different from target/mean encoding and is the recommended path in the official Advanced Topics doc.
- **Negative-code hazard (§14.3):** pandas encodes `NaN` in a `category` column as code `-1`. LightGBM's docs require codes be **non-negative int32 < 2,147,483,647**. The Python package historically routes `-1` to a "missing" bucket, but to be deterministic and to match §14.5 (distinguish missing **reasons**), materialise an explicit sentinel category instead of relying on NaN:
  ```python
  df[c] = df[c].astype("category")
  df[c] = df[c].cat.add_categories(["__MISSING__"]).fillna("__MISSING__")
  ```
  All codes are now non-negative; the `__MISSING__` category is a first-class level the model can split on. Carry a parallel `*_missing_reason` column (one of §14.5's six reasons) so audit logic can tell "未発表" from "初出走・履歴不足".
- **Cardinality / ID management (§14.3 "連番カテゴリID"):** for high-cardinality IDs (jockey_id, horse_id, sire_id), build a **stable, frozen category map** per `feature_snapshot_id`. Fit the map on the training window only, persist it, and apply the same map to validation/test. Unknown-at-prediction-time IDs map to a dedicated `"__UNSEEN__"` category (not to NaN). This prevents both cardinality drift and accidental re-fitting that could leak test-set composition. Never let LightGBM re-derive codes from raw strings at prediction time — the mapping must be versioned artefact.
- **Forbidden:** any form of target/mean encoding (incl. `category_encoders.TargetEncoder`), even "out-of-fold" — the requirements doc explicitly bans it (§14.3) because OOF target encoding on time-series panel data is still leaky (folds aren't exchangeable). LightGBM native handling makes that ban costless.

### 2. Categorical handling — CatBoost (§14.4)

**Recommendation:** pass raw category values as strings/ints in `cat_features`; **set `has_time=True`** on every Pool. This is the single most important CatBoost setting for JRA data.

```python
pool = cb.Pool(
    df[FEATS], df["fukusho_hit_validated"],
    cat_features=CAT_COLS,
    has_time=True,                        # MANDATORY: no random permutation
)
model = cb.CatBoostClassifier(
    iterations=N, loss_function="Logloss",
    allow_writing_files=False,
    random_seed=SEED,
    has_time=True,
)
```

- **Why leak-safe:** CatBoost computes **ordered target statistics** — for each row, the categorical encoding uses only target values from *preceding* rows in the (permutation) order. With `has_time=True` the permutation is **disabled** and "preceding" means strictly earlier in `race_start_datetime` (the order rows arrive in the Pool). This is the time-series-correct mode and is exactly what the original CatBoost paper prescribes for sequential data. Without `has_time=True`, CatBoost permutes randomly and a row's encoding can be informed by future rows → silent leak.
- **Pair with a sort:** sort the Pool by `race_start_datetime` (then `race_id`, then `horse_id`) before constructing it, so "preceding" matches the calendar. This honours §8.4's `race_date` ordering.
- **`cat_features` is mandatory** (§14.4): if a string column isn't declared, CatBoost errors or treats it wrong. Declare every categorical explicitly.
- CatBoost's internal handling means you do **not** need the `__UNSEEN__`/`__MISSING__` dance LightGBM needs — but keep the parallel `*_missing_reason` audit columns anyway for cross-model consistency and §14.5 compliance.

### 3. Point-in-time / as-of feature joins (§13)

**Recommendation:** implement PIT joins with `pandas.merge_asof(direction='backward', by=<entity>)`. **Do not** introduce a heavyweight feature store (Feast/Hopsworks) in Phase 1 — requirements §12.1 says keep it simple and the data volumes (≈10 years of JRA starts) fit in memory per snapshot.

```python
# horse-level rolling stats: compute ON the history up to each race, then as-of join
stats = compute_horse_stats(history_df)              # has 'as_of_datetime' per row
stats = stats.sort_values("as_of_datetime")

obs = features_df.sort_values("feature_cutoff_datetime")
features_pit = pd.merge_asof(
    obs, stats,
    left_on="feature_cutoff_datetime",
    right_on="as_of_datetime",
    by="horse_id",
    direction="backward",                            # only past feature values ever attach
    tolerance=pd.Timedelta(days=10*365),             # explicit max lookback
)
```

- **The leak-prevention invariant:** `direction='backward'` guarantees each observation row receives the **most recent feature value computed at or before** its `feature_cutoff_datetime`. Future information can never cross the cutoff. This is the same primitive Feast/Spark feature stores implement; here it's a 5-line pandas call.
- **`feature_cutoff_datetime` discipline (§13.2/§13.4):** for Phase 1-A (出馬表・馬番・枠番確定後), set `feature_cutoff_datetime = race_date - 1 day` (the day before the race). Past-race aggregates must reference only races whose `race_start_datetime < feature_cutoff_datetime`. The §13.4 prohibition list (当日馬場/天候/馬体重/当日オッズ/当日ここまでの騎手成績) is enforced by *never selecting* those source columns for 1-A features — the `feature_availability` table (§13.3) is the auditable map.
- **Persist the snapshot:** once features are PIT-joined, write the whole design matrix to Parquet with the §12.4 metadata (`feature_snapshot_id`, `feature_cutoff_datetime`, `label_version`, `prediction_timing`). The model trains on the Parquet, never on a re-computed live frame — this is what makes the backtest reproducible (§19.1). DuckDB reads the same Parquet for aggregation audits.
- **Pitfall — sort order:** `merge_asof` raises if either frame isn't sorted by the join key. Always `.sort_values()` immediately before; add a unit test (§17.3 includes feature_cutoff tests) that asserts sortedness.

### 4. Calibration (§15.2/§15.3)

**Recommendation:** `CalibratedClassifierCV(estimator=base, method=..., cv='prefit')` on a **chronologically separated** calibration slice. Never use default K-fold CV for calibration — it shuffles and leaks.

```python
# split: train (early) -> calibrate (middle) -> test (late), all by race_date
cal_clf = CalibratedClassifierCV(
    estimator=fitted_lgb_or_cb,
    method="isotonic",          # see rule below
    cv="prefit",                # base already fitted on TRAIN; this slice is calibration-only
)
cal_clf.fit(X_calib, y_calib)  # X_calib is a STRICTLY LATER, disjoint window
p_calibrated = cal_clf.predict_proba(X_test)[:, 1]
```

- **`cv='prefit'` is mandatory for time series.** It skips internal CV (which uses KFold and shuffles) and uses ALL the data you pass to `.fit()` purely for the calibrator. You **must** guarantee the calibration slice is disjoint from the training slice and strictly later in time — a unit test must assert `max(train.race_date) < min(calib.race_date)`.
- **`method` choice:**
  - `method='sigmoid'` (Platt): parametric, 2 parameters. Use when calibration samples < ~1000. Robust default.
  - `method='isotonic'`: non-parametric, flexible. **Needs ≥ ~1000 calibration samples** or it overfits (official sklearn docs). For JRA Phase 1 (hundreds of thousands of starts), isotonic is viable and tends to beat sigmoid on tree-model outputs (sklearn issue #15013: sigmoid under-corrects GBDTs).
  - **Recommendation:** report both; pick by Brier score on a held-out *test* slice (not the calibration slice). The acceptance criteria (§15.2) require Brier/LogLoss/Calibration-Curve reporting anyway, so the decision is data-driven.
- **Calibration curve axes (§15.3):** compute curves per year / course / field-size / popularity-band / odds-band. `sklearn.calibration.calibration_curve` gives the (mean_predicted, fraction_positive) pairs; plot with `plotly` in Streamlit. The §15.2 acceptance rule (monotone-ish bins, no extreme yearly inversions) is checked on these.
- **`sum(p)` distribution check (§15.2):** after calibration, group by `race_id` and inspect the sum, median, std, p10, p90 of `p_fukusho_hit`. Expected means: ~2.7–3.3 for ≥8-horse races, ~1.8–2.2 for 5–7 horse races. Big deviations flag a calibration or feature problem — drill down by course/class/distance as §15.2 prescribes.

### 5. Time-series validation (§8.4/§15.4)

**Recommendation:** a **custom group-aware time-series splitter** based on `mlxtend.evaluate.GroupTimeSeriesSplit`, NOT bare `sklearn.TimeSeriesSplit`.

- **The gap `TimeSeriesSplit` leaves:** scikit-learn's `TimeSeriesSplit` (1.9.0) supports a `gap` parameter **but is not group-aware** (issue #19072, still open in 1.9). Run on JRA panel data it can put rows of the same `race_id` in both train and test — a direct violation of §8.4 ("同一race_idのtrain/testまたぎ禁止"). This is the single most common silent leak in racing ML and the requirements doc explicitly bans it.
- **Use `mlxtend.evaluate.GroupTimeSeriesSplit`:** it operates on `groups=` (your `race_id`) and splits whole groups in time order, so every row of a race stays on one side. Pair it with a sort by `race_start_datetime` at the group level (sort races, not rows).
- **Backtest windows (§15.5 BT-1..BT-5):** implement rolling/expanding windows over `race_date`. Because groups are whole races, BT-1 (train 2019-06→2022, test 2023) is just: `groups_in_train = races with 2019-06 <= race_date <= 2022`, etc. A 20-line helper returns the `(train_race_ids, test_race_ids)` for each BT variant; the model sees only the train races, predicts on the test races, the virtual-purchase rule (§11.4) runs on the test predictions.
- **Hold a gap (§15.4 implicit):** even with group integrity, consider a 1–2 week gap between train and test to avoid borderline autocorrelation (Stats SE rationale: same-meeting-condition leakage). Optional in Phase 1; cheap to add.
- **Forbidden:** `GroupKFold`/`GroupShuffleSplit` (not time-aware — they'd let 2025 races train a 2019 model), and any KFold/shuffle-based CV anywhere in the train→calibrate→test pipeline.

## PostgreSQL ↔ Parquet ↔ DuckDB interop (§5.2/§12)

Decision matrix for which tool moves which data:

| From → To | Tool | When | Notes |
|-----------|------|------|-------|
| **Postgres → Parquet** (snapshot/export) | DuckDB `COPY postgres_db.<tbl> TO 'snap.parquet';` via `postgres_scanner` ext | Materialising a feature snapshot for training | One statement, binary protocol, vectorised. Faster than `psql \copy` + pandas round-trip. |
| **Postgres → Parquet** (small) | pandas `to_parquet` after `psycopg` SELECT | Small tables, when you're already in pandas | Avoid for >1M rows — pandas memory. |
| **Parquet → Postgres** (load) | DuckDB `COPY pg.<tbl> FROM 'x.parquet';` OR `psycopg` `execute_values` batch insert | Writing `prediction` / `backtest` result tables back | DuckDB COPY is fastest; psycopg batching is fine for modest volumes. |
| **Parquet → analysis** | DuckDB `read_parquet('*.parquet')` | §6.4-style audits, as-of aggregations over snapshots | Predicate + projection pushdown; zero-copy via Arrow. **This is DuckDB's main job in this project.** |
| **Postgres → live analytics** | DuckDB `postgres_scanner` (attach live) | Ad-hoc aggregation without exporting | Read-only; pushes OLAP down to DuckDB, leaves Postgres as source of truth. Don't run heavy scans in production hours. |
| **Parquet ↔ pandas** | PyArrow zero-copy | Feeding the model; feature engineering in pandas | `df = pq.read_table(...).to_pandas()`; Arrow keeps it copy-free. |
| **Postgres ↔ pandas** | psycopg3 cursor / SQLAlchemy 2.0 | ETL reads/writes where SQL is simpler than DuckDB | Normal path for the `normalized` ETL layer. |

**Governance rules (§12.1 "keep it simple"):**

1. **Postgres is the system of record.** Raw EveryDB2 tables, normalized, label, prediction, backtest all live there. Every artefact is reconstructable from Postgres + the committed code + `uv.lock`.
2. **Parquet is the snapshot/reproducibility medium.** Once a `feature_snapshot_id` is frozen, its Parquet is immutable — the model trains on the snapshot, not on a re-query. This is what §19.1 reproducibility actually means in practice.
3. **DuckDB is a transient engine, never a store.** No DuckDB database file is a deliverable. DuckDB reads Parquet/Postgres and returns pandas/Arrow. If you find yourself "saving" DuckDB state, you've drifted — push it back into Postgres or Parquet.
4. **Avoid the in-Postgres DuckDB extensions** (`pg_duckdb`, `pg_parquet`) for Phase 1. They're great but they add a Postgres-side extension dependency and complicate the §19.2 maintainability story. Plain Postgres 15 + Python-side DuckDB is enough.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| LightGBM native categoricals | Target/mean encoding (category_encoders) | **Never** in Phase 1 — banned by §14.3 (leakage on time-series panel data). LightGBM native makes the ban free. |
| CatBoost `has_time=True` | CatBoost default (random permutation) | **Never** for JRA data — random permutation breaks the time ordering that makes ordered TS leak-safe. |
| psycopg3 (`psycopg[binary]`) | psycopg2 | Only if a third-party tool hard-requires psycopg2. New code in 2026 should use psycopg3. |
| DuckDB for ad-hoc aggregation | Pure pandas group-by | Only when the frame is <~1M rows and the query is trivial. Past that, DuckDB is faster and uses less memory. |
| `CalibratedClassifierCV(cv='prefit')` | `cv=5` (default) | Only for i.i.d. non-time-series data. For JRA, prefit is mandatory. |
| `mlxtend.GroupTimeSeriesSplit` | custom `BaseCrossValidator` | If mlxtend's split policy doesn't match a BT variant exactly. A 30-line custom splitter is fine; just unit-test race_id integrity. |
| PyArrow for Parquet | fastparquet | Only if PyArrow wheel is unavailable on some platform (not the case here). PyArrow is the DuckDB/pandas default. |
| Plotly in Streamlit | matplotlib | If you need static PNG exports. Otherwise Plotly integrates better with Streamlit. |
| uv | poetry / pip-tools / hatch | None in Phase 1 — requirements fix uv. uv's lockfile + speed are the reasons. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Target / mean encoding** (incl. OOF) | Leaks on time-series panel data; banned by §14.3 | LightGBM native `category` dtype; CatBoost `cat_features` + `has_time=True` |
| **CatBoost without `has_time=True`** | Random permutation lets future rows inform a row's categorical encoding (silent leak) | Always `has_time=True` + chronologically sorted Pool |
| **`CalibratedClassifierCV` with default `cv`** | KFold shuffles → look-ahead leak in calibration | `cv='prefit'` on a strictly-later disjoint calibration slice |
| **`sklearn.TimeSeriesSplit` directly on rows** | Not group-aware; can split one `race_id` across train/test (§8.4 violation) | `mlxtend.GroupTimeSeriesSplit` (groups=`race_id`) or a custom group-aware splitter |
| **DuckDB as a persistence layer** | Requirements §12.1 explicitly forbids treating it as a running DB | Postgres (system of record) + Parquet (snapshots); DuckDB only transient |
| **`pg_duckdb` / `pg_parquet` Postgres extensions** | Adds Postgres-side extension dependency, complicates §19.2 maintainability | Python-side DuckDB reading Parquet/Postgres |
| **Python 3.13** | Some binary wheels (notably CatBoost edge cases) still lag on 3.13 in mid-2026 | Python 3.12 (3.11 fallback per §17.1) |
| **Feast / Hopsworks feature store** | Heavyweight; data volumes fit in memory per snapshot; violates §12.1 "keep it simple" | `pandas.merge_asof(direction='backward')` + Parquet snapshots with §12.4 metadata |
| **MLflow / Optuna in Phase 1** | §21 explicitly defers; stabilise features/eval first | Plain `joblib.dump`/`pickle` for model artefacts; manual hyperparams; revisit in Phase 2+ |
| **One-hot encoding high-cardinality IDs** | ~8x slower in LightGBM; explodes dimensions for jockey_id/horse_id/sire_id | Native categorical handling in both GBDTs |
| **psycopg2** | Legacy; psycopg3 is the 2026 default, has better pooling + type handling | `psycopg[binary]==3.3.4` |
| **`__pycache__`/Parquet/models in Git** | Bloats repo, breaks reproducibility story | `.gitignore`; reproducibility comes from code + `uv.lock` + Postgres + snapshot metadata |

## Stack Patterns by Variant

**If running Phase 1-A (出馬表・馬番・枠番確定後) training:**
- `feature_cutoff_datetime = race_date - 1 day`; never select §13.4 forbidden columns.
- Build design matrix with `merge_asof(direction='backward')`, freeze to Parquet with §12.4 metadata.
- Train LightGBM with `category` dtype + `__MISSING__`/`__UNSEEN__` sentinels; train CatBoost with `cat_features` + `has_time=True`, Pool sorted by `race_start_datetime`.
- Calibrate with `CalibratedClassifierCV(cv='prefit', method='isotonic')` on a later disjoint slice (sigmoid if calib sample < 1000).
- Validate with `GroupTimeSeriesSplit` on `race_id`; report §15.1/§15.2/§15.3 metrics including the `sum(p)` distribution check.
- Because Phase 1-A uses **no odds in features**, this model is directly backtest-able at any `odds_snapshot_policy` (30/10-min) — the EV layer (§11) consumes the model output and the chosen snapshot.

**If running a backtest (§15.5 BT-1..BT-5):**
- Materialise one Parquet per `(feature_snapshot_id, train_period, test_period)` triple.
- Loop: train on train races → calibrate on a slice carved from the train tail → predict on test races → apply §11.4 virtual-purchase rule at the fixed `odds_snapshot_policy` → compute §15.1 metrics + §11.6 回収率 with `effective_stake` handling refunds/競走中止 correctly.
- All race_id groupings enforced by the splitter; all odds-time decisions fixed by `odds_snapshot_policy`; never re-select the best policy after seeing results (§11.2 ban).

**If doing ad-hoc data-quality / aggregation work (§6.4):**
- Reach for DuckDB `read_parquet()` or `postgres_scanner` — vectorised, low-memory.
- Return to pandas only for the final mile (model fitting, plotting).

**If scaling beyond Phase 1 (signal for Phase 2/3):**
- Re-evaluate Feast/Hopsworks only if PIT joins become painful (feature count × entity count × time blows up memory).
- Re-evaluate `pg_duckdb` only if Postgres-side OLAP becomes a bottleneck.
- These are NOT Phase 1 concerns; listed only to flag when the "keep it simple" rule should be revisited.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Python 3.12 | LightGBM 4.6.0, CatBoost 1.2.10, scikit-learn 1.9.0, DuckDB 1.5.3, pandas 3.0.3, pyarrow 24.0.0, psycopg3 3.3.4, Streamlit 1.58.0 | All verified shipping 3.12 wheels on PyPI (2026-06-16). |
| scikit-learn 1.9.0 | Python ≥3.11 | requires_python `>=3.11`; 3.12 fine. `CalibratedClassifierCV` uses `estimator=` (not legacy `base_estimator=`). |
| pandas 3.0.3 | Python ≥3.11, NumPy ≥2.0 | pandas 3.x dropped 3.10; fine on 3.12. `merge_asof` API unchanged. |
| psycopg3 3.3.4 | Python ≥3.10, Postgres ≥9.6 | Compatible with Postgres 15.18 (host). Use `psycopg[binary]` to avoid building libpq from source. |
| DuckDB 1.5.3 | Python ≥3.10; reads Parquet written by pyarrow 24; `postgres_scanner` ext works with PG 15 | `postgres_scanner` is a loadable extension (`INSTALL postgres_scanner; LOAD postgres_scanner;`). |
| LightGBM 4.6.0 | Python ≥3.7 (declared); tested up to 3.13 | `category` dtype auto-detection stable since 4.x. |
| CatBoost 1.2.10 | Python 3.9–3.13 (binary wheels) | `has_time` parameter stable across 1.2.x. |
| mlxtend (latest 4.x) | scikit-learn ≥1.0, pandas ≥2.0 | `GroupTimeSeriesSplit` is API-stable. |
| Streamlit 1.58.0 | Python ≥3.10 | 3.12 fully supported. |

## Sources

Versions verified against the **PyPI JSON API** (`https://pypi.org/pypi/<pkg>/json`) on 2026-06-16 — confidence HIGH for every version pin above. Other sources:

- **LightGBM 4.6 official docs — Advanced Topics** (categorical features must be non-negative int32; pandas `category` auto-extracted) — https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html — HIGH
- **LightGBM categorical handling — Stack Overflow / GitHub #2761** (integer codes, not names; pandas category path) — https://github.com/lightgbm-org/LightGBM/issues/2761 — MEDIUM (community, corroborated by docs)
- **CatBoost NeurIPS 2018 paper — "Unbiased boosting with categorical features"** (ordered TS, ordered boosting, prediction shift) — https://papers.neurips.cc/paper/7898-catboost-unbiased-boosting-with-categorical-features.pdf — HIGH (primary source)
- **CatBoost `has_time` & ordered TS — Cross Validated** (time ordering prevents future leak) — https://stats.stackexchange.com/questions/614703/why-doesnt-catboost-encoding-cause-target-leakage — MEDIUM (community, matches paper)
- **scikit-learn 1.9.0 — CalibratedClassifierCV** (`method`, `cv='prefit'`, ≥1000-sample isotonic rule) — https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html — HIGH
- **sklearn issue #15013** (sigmoid under-corrects tree models → isotonic often better) — https://github.com/scikit-learn/scikit-learn/issues/15013 — MEDIUM
- **scikit-learn 1.9.0 — TimeSeriesSplit** (has `gap`, NOT group-aware) — https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html — HIGH
- **sklearn issue #19072** (group-aware TimeSeriesSplit still open) — https://github.com/scikit-learn/scikit-learn/issues/19072 — HIGH
- **mlxtend — GroupTimeSeriesSplit** (group-aware time-series CV) — https://rasbt.github.io/mlxtend/user_guide/evaluate/GroupTimeSeriesSplit/ — HIGH
- **pandas 3.0.3 — merge_asof** (`direction='backward'`, sorted-input requirement, `by=` entity grouping) — https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html — HIGH
- **Sem Sinchenko — asOfJoin for feature stores** (PIT correctness = backward as-of = leak prevention) — https://semyonsinchenko.github.io/ssinchenko/post/fs_asof_problem_pyspark/ — MEDIUM (blog, but principle is standard)
- **DuckDB — PostgreSQL extension** (`COPY ... TO/FROM '*.parquet'`, `postgres_scanner`) — https://duckdb.org/docs/current/core_extensions/postgres/overview.html — HIGH
- **Motherduck — Postgres + DuckDB options** (pg_duckdb vs scanner vs pg_parquet decision) — https://motherduck.com/blog/postgres-duckdb-options/ — MEDIUM (vendor blog)
- **psycopg3** (vs psycopg2; pooling) — https://www.psycopg.org/psycopg3/docs/ — HIGH
- **uv** (lockfile, frozen sync) — https://docs.astral.sh/uv/ — HIGH

Host environment verified directly: `python3.12.13`, `uv 0.11.21`, `psql 15.18` (Homebrew). DuckDB CLI not installed — Python wheel 1.5.3 is sufficient.

---
*Stack research for: JRA horse-racing prediction ML (複勝 `p_fukusho_hit` + EV)*
*Researched: 2026-06-16*
