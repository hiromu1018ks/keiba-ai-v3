# Architecture Research

**Domain:** Leakage-sensitive time-series ML system for JRA horse-racing prediction (複勝 place-bet payout-eligibility probability `p_fukusho_hit` + expected-value evaluation)
**Researched:** 2026-06-16
**Confidence:** HIGH

This document informs roadmap phase decomposition. It is opinionated: every architectural choice below has a stated reason and a stated alternative that was rejected. The requirements doc (`docs/keiba_ai_requirements_v1.3.md`) is treated as authoritative; this research validates and refines it against industry patterns rather than reopening decisions already made in v1.3.

---

## Standard Architecture

### System Overview

The system is a **layered, append-mostly, point-in-time-correct pipeline**. Information flows strictly downward (raw → normalized → label → features → prediction → backtest). No layer ever writes back to a layer above it. Each layer boundary is also a **leakage checkpoint**: crossing it requires a timestamp assertion.

```
┌─────────────────────────────────────────────────────────────────────┐
│  EXTERNAL SOURCE (read-only, project start precondition, §3.1)        │
│  EveryDB2 → Mac PostgreSQL (raw_everydb2 tables)                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (no project code touches this; immutable)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  POSTGRESQL — persistent source of truth (§5.1, §12.1)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ raw_everydb2 │→ │  normalized  │→ │    label     │               │
│  │ (immutable)  │  │ (typed/coded)│  │ (validated)  │               │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘               │
│                           │                 │                         │
│                           ▼                 │                         │
│                  ┌────────────────┐         │                         │
│                  │ feature_def    │         │                         │
│                  │ (as-of catalog)│         │                         │
│                  └────────┬───────┘         │                         │
│                           │                 │                         │
│  ┌──────────────┐  ┌──────▼───────┐  ┌──────▼───────┐               │
│  │  prediction  │  │  backtest    │  │  versioning  │               │
│  │ (p, EV, rank)│  │ (virtual bet)│  │ (model/feat/ │               │
│  │              │  │              │  │  label/odds) │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (snapshot export, one-way)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PARQUET — immutable snapshots (§12.4)                                │
│  feature_snapshot / training_dataset / validation_dataset            │
│  (each file carries dataset_version, feature_snapshot_id,            │
│   label_version, as_of_datetime, feature_cutoff_datetime)            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (read-only bulk scan/join)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DUCKDB — auxiliary analytical engine (§12.1)                         │
│  bulk aggregation over Parquet & normalized tables only              │
│  NEVER a source of truth; results not persisted here                 │
└─────────────────────────────────────────────────────────────────────┘

  PRESENTATION
┌─────────────────────────────────────────────────────────────────────┐
│  Streamlit (read-only consumer of prediction + backtest tables)      │
│  CSV export (prediction CSV, backtest CSV)                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `raw_everydb2` layer | Immutable EveryDB2-origin tables. Never modified by project code (§19.2). | Existing PostgreSQL tables, treated read-only. |
| `normalized` layer | Type conversion, code conversion, class normalization by `race_condition_code` (§12.3). | Python ETL writing to PostgreSQL. |
| `label` layer | `fukusho_hit_raw`, `fukusho_hit_validated`, `sales_start_entry_count` restoration, payout-table reconciliation, `label_validation_status` (§10). | Python label generator + payout-table join; tests required (§17.3). |
| `feature_def` (as-of catalog) | One row per feature declaring `available_from_timing`, `source_table`, `cutoff_rule`, `leakage_risk_level` (§13.3). | Declarative table/registry in PostgreSQL; consumed by feature builder. |
| `features` builder | Computes point-in-time-correct features for a given `prediction_timing` (e.g. Phase 1-A `entry_confirmed`+`post_position_confirmed`), enforcing `feature_cutoff_datetime` per row (§13.4). | Python; reads normalized + as-of catalog; outputs feature rows tagged with `as_of_datetime`. |
| `prediction` layer | `p_fukusho_hit`, `EV_lower/EV_upper`, recommend rank, with full provenance (`model_version`, `feature_snapshot_id`, `odds_snapshot_policy`, `odds_snapshot_at`) (§8.2–8.3, §11). | Python model scoring + EV module. |
| `backtest` layer | race_id-unit, time-ordered splits; virtual purchase with fixed rules; refund/scratch/dead-heat handling; reproducible recovery-rate metrics (§11.4–11.6, §15.4). | Python splitter + simulator. |
| `versioning` | `model_version`, `feature_snapshot_id`, `label_generation_version`, `odds_snapshot_policy`, `backtest_strategy_version` persisted alongside every artifact (§19.1). | Conventional columns on every output table + Parquet metadata. |
| Parquet snapshots | Immutable training/validation/feature snapshots for reproducibility (§12.4). | Parquet with embedded metadata. |
| DuckDB | Ad-hoc bulk aggregation / Parquet scans only (§12.1). | Embedded DuckDB; optional. |

---

## Recommended Project Structure

Mapping §17.2 to responsibilities and leakage boundaries. The folder structure mirrors the data-flow layers — this is intentional: a developer reading a path can tell which layer they are in, and a reviewer can ask "does this folder write upward?".

```
src/
├── config/              # Prediction-timing declarations, as-of catalog seed,
│                        #   odds_snapshot_policy, backtest_strategy_version constants.
│                        #   Single source of truth for all versioned knobs.
├── db/                  # Connection management, schema helpers, raw read-only accessors.
├── etl/                 # raw → normalized only. MUST NOT read label/feature tables.
├── labels/              # normalized → label layer. Payout reconciliation, count restoration.
├── features/            # normalized + label(as target only) → PIT-correct feature rows.
│                        #   Enforces feature_cutoff_datetime. Reads config/as-of catalog.
├── models/              # Training (LightGBM/CatBoost/sklearn baselines).
│                        #   Reads Parquet snapshots only — never live DB.
├── prediction/          # Scoring → p_fukusho_hit; EV module → EV/rank.
│                        #   EV module is odds-aware but model-feature-free.
├── backtest/            # Splitter (race_id-unit, time-ordered) + virtual-purchase simulator.
│                        #   Owns odds_snapshot_policy enforcement.
├── evaluation/          # Calibration, Brier, LogLoss, sum(p) distribution, stability slices.
├── snapshots/           # Parquet writers + metadata stamping (dataset_version etc.).
└── utils/               # Datetime/timing, code maps, logging. No domain logic.
scripts/                 # CLI entry points tying the above into reproducible runs.
notebooks/               # Exploration only. Never imported by src/.
streamlit_app/           # Read-only views over prediction + backtest tables.
tests/                   # §17.3 minimum test set lives here.
data/parquet/            # Generated snapshots (gitignored, content-addressed).
models/                  # Trained artifacts + their provenance manifest.
reports/                 # Evaluation outputs (CSV/figures).
```

### Structure Rationale

- **`config/` is the only place versioned knobs live.** `odds_snapshot_policy`, `backtest_strategy_version`, prediction-timing definitions, and the as-of catalog seed are all data, not code scattered through modules. This makes "what changed between two runs" answerable by diffing config.
- **`etl/` is forbidden from reading `label/` or `features/`.** A unidirectional dependency rule enforced by review (and optionally import linting) prevents accidental upward writes.
- **`models/` reads Parquet only, never the live DB.** This is the single most important anti-leakage rule: training must consume an immutable, already-as-of-correct snapshot, not a mutable table whose rows may have been patched.
- **`prediction/` splits scoring from EV.** Scoring uses odds-free features; EV consumes odds at a fixed snapshot. Keeping them in separate modules makes "odds never enters features" auditable at the module boundary.

---

## Architectural Patterns

### Pattern 1: Point-in-time (as-of) feature correctness

**What:** Every feature row carries `as_of_datetime` and `feature_cutoff_datetime`, and a feature is only eligible to be computed for a (race_id, horse_id) prediction if its `available_from_timing` is satisfied **strictly before** the prediction is made. Feature construction uses an as-of join: only source rows whose event timestamp ≤ `feature_cutoff_datetime` are admitted.

**When to use:** Always, in every prediction timing. This is the architectural backbone — not an optimization.

**Trade-offs:** Slightly more complex than a naive "race_date ascending" pipeline, but it is the only mechanism that catches the genuinely dangerous leaks (same-day jockey/course aggregates, body-weight, odds, post-race aggregates). Industry consensus: point-in-time-correct joins are the standard solution for future-leakage in time-series training sets; feature stores (Feast, Hopsworks, Databricks, SageMaker) all implement exactly this primitive. We implement it as an explicit Python-side as-of filter rather than adopting a full feature store, because the requirements (§21) defer MLflow/Optuna and the system is single-node.

**Example:**
```python
# Phase 1-A feature eligibility check (conceptual)
def eligible(feature_def, prediction_timing):
    # available_from_timing must be met by the prediction_timing
    return TIMING_ORDER[feature_def.available_from_timing] <= TIMING_ORDER[prediction_timing]

# As-of join when building past-performance aggregates
past = races_df.filter(
    (races_df.race_start_datetime < target.feature_cutoff_datetime)   # strict future-exclusion
    & (races_df.confirmation_status == "confirmed")                    # only finalized races
)
```

### Pattern 2: race_id-grouped, time-ordered split with no group crossing

**What:** Cross-validation and backtest splits are made at the **race_id** granularity, ordered by `race_date` / `race_start_datetime`. All horses in one race live in either train or test — never split across both. This is exactly the "group leakage" failure mode that vanilla `TimeSeriesSplit` fails to prevent.

**When to use:** All model selection and backtest evaluation.

**Trade-offs:** Standard `sklearn.TimeSeriesSplit` is record-level and will silently leak horses from the same race into both sides. `mlxtend.GroupTimeSeriesSplit` (or an equivalent in-house splitter) is the correct primitive; it supports both rolling and expanding windows and respects group boundaries. Requirements §15.4 mandates rolling, expanding, and fixed-holdout variants; implement the splitter once as race_id-aware and reuse for all three.

**Leakage this prevents:** A horse in the validation race appearing in training (record-level leakage), and the same race_id contributing to both sides (group leakage).

### Pattern 3: Single-direction, append-mostly layered pipeline

**What:** Layers flow raw → normalized → label → features → prediction → backtest. Each layer writes only to itself or downward. Outputs are immutable once published and stamped with a version manifest.

**When to use:** Always.

**Trade-offs:** Forces full re-runs when an upstream layer changes (e.g., a label fix). This is a feature, not a bug: it guarantees reproducibility. Re-running a layer produces a new version rather than mutating an old one.

### Pattern 4: Snapshot-based reproducibility manifest

**What:** Every artifact that crosses the DB→Parquet→model boundary carries a manifest: `model_version`, `feature_snapshot_id`, `label_generation_version`, `prediction_timing`, `feature_cutoff_datetime`, `odds_snapshot_policy`, `backtest_strategy_version`. The manifest is the unit of reproducibility — given the same manifest values and the same code commit, the run must be byte-reproducible (modulo RNG seeds, which are also stamped).

**When to use:** On every training run, every prediction batch, every backtest run.

**Trade-offs:** More columns/metadata to maintain than a "just train it" script. But this is what makes "did this backtest use the fixed 30-min-before odds or the final odds?" answerable months later — which §11.2 explicitly demands.

---

## Data Flow

### Build-time (training) flow

```
raw_everydb2 (immutable)
    │
    ▼  etl/                        [quality gate §6.4 MUST pass first]
normalized (typed, class-normalized)
    │
    ├──────────────────────────────► label/ ──► label layer
    │                                  │        (fukusho_hit_validated,
    │                                  │         sales_start_entry_count,
    │                                  │         payout reconciliation)
    │                                  ▼
    │                              label layer (validated)
    │                                  │
    ▼                                  │
features/ ◄── as-of catalog ──────────┘  (label is target only)
    │   (PIT join: rows with event_ts ≤ feature_cutoff_datetime)
    ▼
feature rows (tagged as_of_datetime, feature_snapshot_id)
    │
    ▼  snapshots/   ──►  Parquet training/validation dataset
    │                     (stamped: dataset_version, feature_snapshot_id,
    │                      label_version, prediction_timing, train/val periods)
    ▼
models/  ──► trained model + provenance manifest
                       (model_version, feature_snapshot_id, label_generation_version)
```

### Predict-time (inference) flow

```
trained model (versioned)
    │
    ▼
prediction/scoring  ◄── features/ (same as-of logic as training)
    │   → p_fukusho_hit  (per race_id, horse_id; stamped with
    │                      model_version, feature_snapshot_id, as_of_datetime)
    ▼
prediction/ev   ◄── odds at FIXED snapshot (odds_snapshot_policy)
    │   → EV_lower, EV_upper, recommend_rank
    │     (stamped with odds_snapshot_policy, odds_snapshot_at)
    ▼
prediction layer (PostgreSQL) ──► Streamlit / CSV export
```

### Backtest flow

```
backtest/splitter
    │   (race_id-grouped, time-ordered; train/test race_id sets DISJOINT)
    ▼
per-fold trained model  ──►  prediction/scoring  ──►  p_fukusho_hit
    │
    ▼
backtest/simulator
    │   (fixed odds_snapshot_policy; no hindsight odds swap; §11.2/§11.3)
    │   (refund on scratch/exclude; loss on DNF; dead-heat per payout table; §10.6/§11.6)
    ▼
backtest layer (PostgreSQL) ──► evaluation/ ──► metrics + stability slices ──► CSV
```

### Key Data Flows

1. **Raw → Normalized:** One-time + incremental ETL. The quality gate (§6.4: table existence, counts, date range, NULLs, duplicate keys, mojibake, code anomalies) **must** pass before anything downstream trusts the data. This is the trust boundary — nothing downstream should run if it fails.
2. **Normalized → Label:** This is the highest-risk layer for label leakage and mislabeling. Order of authority (§10.4): payout table → `sales_start_entry_count` → finishing order → final starter count. Output `label_validation_status` distinguishes `validated` / `inferred` / `unresolved` / `dead_heat`. Unresolved races are excluded from train+eval.
3. **Normalized + Label → Features:** The as-of join lives here. The label participates **only as the target column**, never as a feature. `feature_cutoff_datetime` is computed per (race, horse) from the prediction timing.
4. **Features → Parquet snapshot:** Snapshot is frozen, content-addressable, and stamped. The snapshot is what models train on.
5. **Parquet → Model:** Training reads only snapshots. This is the train/serve-skew prevention boundary: the same feature definition produces both the snapshot and the live prediction features.
6. **Model + Odds → Prediction/EV:** EV consumes a fixed `odds_snapshot_policy`. Missing odds → `no_bet` (§11.3), never a convenient substitute.
7. **Prediction → Backtest:** Backtest reuses the exact prediction pipeline (no separate "backtest model") and applies the virtual-purchase rules (§11.4) and recovery-rate math (§11.6).

---

## Where Leakage Can Sneak In — and How the Architecture Prevents It

This is the most roadmap-critical section. Each row is a layer boundary; the architecture must close every one.

| Boundary | Leakage that can sneak in | Architectural prevention |
|----------|---------------------------|--------------------------|
| raw → normalized | Subtle type/code drift silently changes features | Immutable raw layer (§19.2); normalized is the only transform target; quality gate (§6.4) before downstream trust. |
| normalized → label | Using **final** starter count instead of **sales-start** count → mislabels after scratches; payout table missing → inferred labels pollute training | `sales_start_entry_count` restoration logic + payout-table priority (§10.3–10.4); `label_validation_status` gates train/eval inclusion; tests required (§17.3). |
| label → features | Label value (or a column derived from the target race's outcome) leaking as a feature | Features consume label **only as target**; code review + tests; the label table is not a permissible feature `source_table` except for the target column. |
| features (past-performance) | Same-day aggregates (today's jockey stats, today's course bias, today's going) — the classic race-day leak | `available_from_timing` catalog (§13.3) forbids `race_day_morning`+ for Phase 1-A; as-of filter excludes any event with `event_ts > feature_cutoff_datetime`. |
| features (odds) | Odds (final or conveniently chosen) entering the model as a feature | Odds are **not** in the feature catalog for Phase 1-A; EV module is separate from scoring module; module boundary makes this auditable (§2.2, §9.3). |
| train/test split | Same race_id split across sides; record-level `TimeSeriesSplit` splitting horses of one race | race_id-grouped splitter (Pattern 2); explicit race_id disjointness assertion in tests (§17.3). |
| backtest odds selection | Hindsight selection of the most profitable odds snapshot | `odds_snapshot_policy` fixed as a run parameter (§11.2); missing → `no_bet`, never substitution (§11.3); results stamped with the policy used. |
| backtest outcomes | Excluding DNF horses inflates recovery rate | DNF treated as loss (§10.6); refund only for pre-race scratch/exclude; `effective_stake` accounting (§11.6). |
| calibration / sum(p) check | A model that passes overall metrics but is miscalibrated per slice | sum(p) distribution check + per-slice calibration (§15.2–15.3) as acceptance gate, not afterthought. |

---

## Storage Division of Labor

When does data move between PostgreSQL / Parquet / DuckDB? The rule is one-directional and tied to immutability:

| Store | Role | Mutable? | When data enters it | When data leaves it |
|-------|------|----------|---------------------|---------------------|
| **PostgreSQL** | Persistent source of truth for raw, normalized, label, prediction, backtest tables (§5.1, §12.1) | Mutable by the owning layer only (append/update by that layer's code); raw is strictly immutable | ETL writes here as the canonical pipeline runs | Read by feature builder, prediction, backtest, Streamlit |
| **Parquet** | Immutable, versioned snapshots for training/validation/feature freeze (§12.4) | Immutable once written | When `snapshots/` freezes a feature/training/validation dataset with its manifest | Read by `models/` for training; read by DuckDB for bulk analysis |
| **DuckDB** | Auxiliary analytical engine only — bulk aggregation and Parquet scans (§12.1) | Never persists results; ephemeral per query/session | (data is not stored here) | Results either return to caller or are written **back to PostgreSQL** by the owning layer if they are canonical |

**Move rules of thumb (informed by community practice for the Postgres + Parquet + DuckDB pattern):**

1. **PostgreSQL → Parquet:** Move when freezing a training/validation/feature snapshot. This is the immutability boundary. Industry guidance confirms the pattern: keep Postgres as the OLTP source of truth and export to Parquet when you need a decoupled, open-format analytical/snapshot layer.
2. **Parquet → DuckDB:** Read-only bulk scans/joins/aggregations. DuckDB reads Parquet natively and is the right tool for ad-hoc analytical queries over snapshots without round-tripping through Postgres.
3. **PostgreSQL ↔ DuckDB:** Use DuckDB (or the DuckDB Postgres extension / `pg_duckdb`) when an aggregation would stress Postgres OLTP performance — e.g., computing per-jockey/per-course aggregates across a decade of races. If the result is canonical, write it back into the normalized/feature layer in Postgres; if exploratory, keep it ephemeral.
4. **Never:** Parquet is not the source of truth (PostgreSQL is). DuckDB is not a source of truth (results are not persisted there). Parquet never writes back into PostgreSQL as a "correction" — corrections happen via the owning Python layer with a new version stamp.

**Why not a full feature store (Feast/Hopsworks)?** They implement the same as-of-correctness pattern this system needs, but §21 defers MLflow/Optuna and the system is single-node on a single Mac. An explicit Python as-of filter plus the as-of catalog table gives the leakage protection without the operational weight. This is a deliberate scope decision, not a capability gap.

---

## Anti-Patterns

### Anti-Pattern 1: Training directly off the live PostgreSQL feature/label tables

**What people do:** Skip the Parquet snapshot; have the model training query the (mutable) feature table directly.
**Why it's wrong:** The feature table can be patched after the fact (label fix, feature recompute). The "training data" then silently changes between runs, destroying reproducibility — the project's stated core value (PROJECT.md Core Value). It also reopens train/serve skew.
**Do this instead:** Train only off stamped Parquet snapshots. `models/` is forbidden from reading the live DB.

### Anti-Pattern 2: Record-level `TimeSeriesSplit`

**What people do:** Use scikit-learn's `TimeSeriesSplit` on a flattened horse-row dataset.
**Why it's wrong:** It splits at the record level, so horses from the same race land on both sides of train/test. The model then "sees" teammates/opponents during training and validation — a textbook group-leakage failure that inflates all metrics. This is the exact failure the requirements (§15.4) prohibit.
**Do this instead:** Use a race_id-grouped, time-ordered splitter (Pattern 2; `mlxtend.GroupTimeSeriesSplit` or equivalent). Assert race_id disjointness between folds in tests.

### Anti-Pattern 3: Final-odds or hindsight-odds backtesting

**What people do:** Backtest with final odds, or after seeing results pick the odds snapshot that maximizes recovery rate.
**Why it's wrong:** Both are future information at decision time. Recovery rates become irreproducible and inflated (§11.2, §20).
**Do this instead:** Fix `odds_snapshot_policy` (30-min-before / 10-min-before) as a run parameter; missing → `no_bet`; never substitute; stamp the policy on every result.

### Anti-Pattern 4: Final-starter-count labeling

**What people do:** Label `fukusho_hit` using the number of horses that actually started.
**Why it's wrong:** Scratches/withdrawals after sales-start change the headcount and thus the payout-eligibility count (3 places vs 2). Labeling on final count mislabels races with post-sales-start withdrawals (§10.2, §20).
**Do this instead:** Use `sales_start_entry_count` (restored if necessary), payout-table priority, and `label_validation_status` to gate inclusion.

### Anti-Pattern 5: Using DuckDB as a persistent store

**What people do:** Run aggregations in DuckDB, leave the results there, and have downstream code read them back.
**Why it's wrong:** DuckDB is positioned as an analytical engine, not a source of truth (§12.1). Persisting canonical results there creates a second, unsynchronized truth and breaks the single-source-of-truth invariant.
**Do this instead:** If an aggregation result is canonical, write it back into the owning PostgreSQL layer with a version stamp; DuckDB stays ephemeral.

---

## Scaling Considerations

This is a single-Mac, single-user analysis tool, not a web service. "Scaling" here means data-volume scaling over a decade of JRA races, not user-load scaling.

| Scale | Architecture Adjustment |
|-------|--------------------------|
| 2015–now (decade of JRA data, single Mac) | PostgreSQL source of truth + Parquet snapshots + DuckDB for bulk scans. No cluster needed. |
| + Phase 2/3 (wide/三連複, more timings, time-series odds) | More feature rows and more snapshots; Parquet partitioning by `race_date` becomes valuable; DuckDB scans over partitioned Parquet. Architecture unchanged. |
| + Many model variants / hyperparameter search (Optuna, §21) | Add MLflow/DVC for experiment tracking (deferred per §21). Architecture's version-manifest pattern makes this a drop-in addition, not a restructure. |

### Scaling Priorities

1. **First bottleneck:** Feature recomputation cost as feature count grows. Mitigation: incremental feature materialization into the feature layer in PostgreSQL; snapshot to Parquet only for the training freeze, not for every exploratory query.
2. **Second bottleneck:** Snapshot storage volume if many model variants are retained. Mitigation: content-addressed snapshots (reuse identical feature snapshots across model versions); keep label_version and feature_snapshot_id as dedup keys.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| EveryDB2 → Mac PostgreSQL | Read-only consumption of existing tables (§3.1). Project never writes to EveryDB2-side. | Setup is a project precondition; if incomplete, Phase 1 cannot start. |
| JRA-VAN Data Lab. (via EveryDB2) | Indirect only — data already landed in PostgreSQL. | No direct integration from project code. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| raw ↔ normalized | Unidirectional ETL; normalized reads raw only. | Raw is immutable (§19.2). |
| normalized ↔ label | Unidirectional; label reads normalized. | Label uses payout table as authority (§10.4). |
| normalized + label ↔ features | Features read normalized; read label **only as target**. | As-of catalog gates eligibility (§13.3). |
| features ↔ Parquet snapshot | One-way freeze; snapshots are immutable. | Manifest stamped on write (§12.4). |
| Parquet ↔ models | Models read snapshots only. | No live DB access from `models/`. |
| prediction (scoring) ↔ prediction (EV) | Scoring outputs `p_fukusho_hit`; EV consumes p + fixed-odds snapshot. | Odds never enter scoring (§2.2). |
| prediction ↔ backtest | Backtest reuses the prediction pipeline with fixed rules. | No separate backtest-time model. |
| All layers ↔ Streamlit/CSV | Read-only over prediction + backtest tables. | No write path from UI. |

---

## Suggested Build Order (dependency graph → phase decomposition)

This is the single most roadmap-relevant section. Build order is a strict DAG; nothing downstream can be trusted without its upstream being trustworthy. This maps directly onto recommended phases.

```
1. raw quality gate (§6.4)                 ── TRUST GATE: nothing below runs until this passes
        │
        ▼
2. normalized ETL (§12.2, §12.3)           ── class normalization, type/code conversion
        │
        ▼
3. label generation + payout reconciliation (§10) + sales_start_entry_count restoration
        │                                    ── incl. label_validation_status, dead-heat, scratch handling
        │                                    ── tests: label correctness, payout match, scratch/DNF
        ▼
4. as-of catalog + feature builder (§13)    ── feature_cutoff_datetime, available_from_timing enforcement
        │                                    ── Phase 1-A timing only initially
        ▼
5. Parquet snapshot layer + version manifest (§12.4, §19.1)
        │                                    ── feature_snapshot_id, label_version, etc.
        ▼
6. baselines + Phase 1-A model (§14)        ── BL-1..BL-5, then LightGBM/CatBoost
        │                                    ── trained off snapshots only
        ▼
7. prediction/scoring (p_fukusho_hit) (§8.2) ── stamped with model_version, feature_snapshot_id, as_of
        │
        ▼
8. EV module + recommend rank (§8.3, §11.1, §11.5)
        │                                    ── odds_snapshot_policy fixed
        ▼
9. backtest splitter (race_id-grouped) + simulator (§11.4–11.6, §15.4)
        │                                    ── refund/scratch/DNF/dead-heat; fixed odds policy
        ▼
10. evaluation + acceptance gates (§15)     ── calibration, Brier, LogLoss, sum(p) distribution, stability slices
        │
        ▼
11. Streamlit + CSV export (§16)            ── read-only presentation over prediction + backtest
```

### Ordering rationale (dependencies)

- **(1) must precede everything:** Trust in raw data is the foundation. The requirements explicitly make quality checks a gate (§6.4). Building on unvalidated raw data wastes every downstream effort.
- **(2) precedes (3) and (4):** Label and features both depend on typed, class-normalized, code-converted data. Class normalization by `race_condition_code` (§12.3) is a label/feature input, not cosmetic.
- **(3) precedes (4) and (5):** Features use the label as target; snapshots need a stable label definition. The label layer's `label_generation_version` is a snapshot input.
- **(3) precedes (9):** Backtest outcome accounting (refund, DNF, dead-heat) depends on a correct label/validation layer.
- **(4) precedes (5):** Snapshots freeze already-as-of-correct features. You cannot build a trustworthy snapshot without the as-of filter already enforcing.
- **(5) precedes (6):** Models train off snapshots. No snapshot → no reproducible training.
- **(7) precedes (8):** EV consumes `p_fukusho_hit`.
- **(8) precedes (9):** Backtest simulates virtual purchases using EV/rank.
- **(9) precedes (10):** Evaluation metrics are computed over backtest outputs and prediction outputs.
- **(10) precedes (11):** Streamlit is presentation only; it should be built last because it has zero architectural dependencies pointing into it, and the acceptance gates in (10) are what make the displayed numbers trustworthy.

### Phase implications for the roadmap

A natural phase decomposition follows the build order. Recommended rough cuts (the roadmap agent will refine):

- **Phase 1: Trust & foundation** → steps 1–2 (raw gate, normalized ETL). Without this, nothing is trustworthy.
- **Phase 2: Labels** → step 3 (label generation, payout reconciliation, count restoration, status flags). The single highest-risk layer; deserves its own phase and heavy testing.
- **Phase 3: Features & snapshots** → steps 4–5 (as-of catalog, feature builder, Parquet snapshot layer, version manifest). The leakage-prevention backbone.
- **Phase 4: Model** → steps 6–7 (baselines, Phase 1-A model, prediction/scoring).
- **Phase 5: EV & backtest** → steps 8–10 (EV, race_id-grouped backtest, evaluation/acceptance gates).
- **Phase 6: Presentation** → step 11 (Streamlit, CSV export).

**Research flags for phases:**

- **Label phase (2):** Highest complexity per requirements. Likely needs deeper phase-specific research on EveryDB2/JRA-VAN schema details (payout table columns, withdrawal announcement timestamps) before implementation. The `sales_start_entry_count` restoration logic (§10.3) in particular cannot be specified without inspecting actual columns.
- **Feature phase (3):** The as-of catalog and `available_from_timing` mapping depend on the exact JRA-VAN data availability timings. Needs schema-grounded research, not generic patterns.
- **Backtest phase (5):** Standard patterns (rolling/expanding/fixed-holdout, group split) are well-understood; unlikely to need deep research. The odds-snapshot-policy mechanics depend on what odds snapshots EveryDB2 actually stores (timing granularity).
- **Model/EV/presentation phases (4, 6):** Standard patterns; unlikely to need phase-specific research.

---

## Sources

- Point-in-time correctness / as-of joins (leakage prevention): [Hopsworks — point-in-time correct joins](https://www.hopsworks.ai/dictionary/point-in-time-correct-joins); [Databricks Feature Store — time-series feature tables](https://docs.databricks.com/aws/en/machine-learning/feature-store/time-series); [ApXML feature store course — point-in-time correctness](https://apxml.com/courses/feature-stores-for-ml/chapter-3-data-consistency-quality/point-in-time-correctness); [Towards Data Science — point-in-time correctness in real-time ML](https://towardsdatascience.com/point-in-time-correctness-in-real-time-machine-learning-32770f322fb1/); [AWS — point-in-time queries with SageMaker Feature Store (GoDaddy)](https://aws.amazon.com/blogs/machine-learning/build-accurate-ml-training-datasets-using-point-in-time-queries-with-amazon-sagemaker-feature-store-and-apache-spark/). Confidence: HIGH (industry-standard primitive, multiple independent authoritative sources).
- Training-serving skew / single feature definition: [Aerospike — feature stores](https://aerospike.com/blog/feature-store/); [Nubank Engineering — train-serve skew](https://building.nubank.com/dealing-with-train-serve-skew-in-real-time-ml-models-a-short-guide/); [Hopsworks — feature store (online-offline skew)](https://www.hopsworks.ai/dictionary/feature-store). Confidence: HIGH.
- Group-aware time-series splitting (race_id group leakage): [mlxtend — GroupTimeSeriesSplit](https://rasbt.github.io/mlxtend/user_guide/evaluate/GroupTimeSeriesSplit/); [Kaggle — Found the Holy Grail: GroupTimeSeriesSplit](https://www.kaggle.com/code/jorijnsmit/found-the-holy-grail-grouptimeseriessplit); [Stack Overflow — cross-validation for grouped time-series](https://stackoverflow.com/questions/51963713/cross-validation-for-grouped-time-series-panel-data); [Towards Data Science — blocked time series split](https://towardsdatascience.com/reduce-bias-in-time-series-cross-validation-with-blocked-split-4ecbfc88f5a4/). Confidence: HIGH.
- DuckDB + PostgreSQL + Parquet division of labor: [EthicalAds — DuckDB and PostgreSQL make a great pair](https://www.ethicalads.io/blog/2025/02/duckdb-and-postgresql-make-a-great-pair-for-analytical-processing/); [Motherduck — DuckDB vs Postgres for embedded analytics](https://motherduck.com/learn/duckdb-vs-postgres-embedded-analytics/); [Crunchy Data — Parquet and Postgres in the data lake](https://www.crunchydata.com/blog/parquet-and-postgres-in-the-data-lake); [pg_duckdb](https://github.com/duckdb/pg_duckdb/discussions/886); [DuckLake lakehouse format](https://dataengineeringcentral.substack.com/p/duckdb-enters-the-lake-house-race). Confidence: HIGH (consistent community guidance).
- ML reproducibility / feature & label versioning / immutable snapshots: [Feature versioning strategies in feature stores (apxml)](https://apxml.com/courses/feature-stores-for-ml/chapter-5-governance-security-mlops/feature-versioning-strategies); [CMU MLiP — versioning, provenance, reproducibility](https://mlip-cmu.github.io/book/24-versioning-provenance-and-reproducibility.html); [DVC — versioning data and models](https://doc.dvc.org/example-scenarios/versioning-data-and-models); [arXiv — reproducibility in ML-based research](https://arxiv.org/html/2406.14325v3). Confidence: HIGH.
- Authoritative project sources (treated as ground truth, not web research): `.planning/PROJECT.md`; `docs/keiba_ai_requirements_v1.3.md` (sections 5, 10, 11, 12, 13, 15, 17).

---
*Architecture research for: JRA horse-racing 複勝 prediction ML system (leakage-sensitive time-series)*
*Researched: 2026-06-16*
