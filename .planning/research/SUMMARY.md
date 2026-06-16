# Project Research Summary

**Project:** Keiba AI v3 — JRA horse-racing prediction ML (複勝 / fukusho place-bet payout-eligibility probability `p_fukusho_hit` + EV evaluation + fixed-rule virtual-purchase backtest + minimal Streamlit UI + CSV export)
**Domain:** Leakage-critical, reproducibility-critical time-series panel ML over a decade of JRA starts (Phase 1 = implementation-verification scope, no real betting)
**Researched:** 2026-06-16
**Confidence:** HIGH (stack versions verified against PyPI 2026-06-16; JRA rules anchored to authoritative requirements v1.3; architecture/pitfalls grounded in industry-standard leakage-prevention primitives)

---

## Executive Summary

Keiba AI v3 is a single-Mac, single-user research pipeline that estimates per-horse place-bet payout-eligibility probability (`p_fukusho_hit`) and evaluates expected value against a fixed-snapshot odds policy. Experts build this class of system as a **layered, append-mostly, point-in-time-correct pipeline**: raw → normalized → label → features → prediction → backtest → presentation, with every layer boundary also serving as a leakage checkpoint. The four researches converge on one unmistakable message — **the competitive moat here is discipline, not model sophistication.** Public horse-racing ML projects almost universally fail at exactly the points this system must defend (correct sales-start-time labels, leakage-free as-of features, race-grouped time-series splits, fixed-odds-snapshot backtests, honest refund/dead-loss accounting, calibrated probabilities, and reproducibility version-stamping). Lean into that discipline as the differentiator story; "we also use LightGBM" is not the story.

The recommended approach is fixed by the requirements doc and validated by this research: LightGBM 4.6 + CatBoost 1.2.10 (both in leak-safe categorical modes), scikit-learn 1.9 for calibration/metrics/baselines, PostgreSQL 15 as system of record, Parquet for immutable versioned snapshots, DuckDB 1.5 as an ephemeral analytical engine, `pandas.merge_asof(direction='backward')` as the point-in-time join primitive, `mlxtend.GroupTimeSeriesSplit` for race_id-grouped time-series CV, and `CalibratedClassifierCV(cv='prefit')` on a strictly-later disjoint calibration slice. Phase 1-A features are **odds-free** (ability/EV separation); odds enter only at the EV layer at a pre-registered fixed `odds_snapshot_policy` (30-min-before or 10-min-before compared, never hindsight-selected).

The dominant risks are **silent** — a pipeline that runs, emits numbers, shows great ROI, and is wrong at every digit. The three highest-blast-radius failure modes are: (1) future-information leakage in past-performance aggregates (same-day stats, unbounded windows, post-race columns via `SELECT *`), (2) fukusho label corruption from using `final_starter_count` instead of restored `sales_start_entry_count` with payout-table priority, and (3) hindsight odds-snapshot selection that turns the backtest into fiction. Mitigation is structural: build the leakage-prevention infrastructure **first** as a stack bootstrap (frozen category maps, PIT joiner, race_id-grouped splitter, prefit chronological calibrator) and back it with adversarial audit tests that catch what functional tests cannot. The build order is a strict DAG — do not interleave model work before labels and features are locked.

---

## Key Findings

### Recommended Stack

The requirements doc (§17.1) fixes the stack; this research verifies each component's 2026 version, interop, and — critically — the leakage-prevention configuration. Every version below was verified against the PyPI JSON API on 2026-06-16 and all ship Python 3.12 wheels. See `STACK.md` for full rationale and "What NOT to Use".

**Core technologies:**

- **Python 3.12 (NOT 3.13)** — runtime sweet spot; LightGBM/CatBoost/DuckDB all stable on 3.12. `requires-python = ">=3.12,<3.13"`.
- **uv ≥0.11** — dependency + venv + Python management; `uv.lock` gives byte-reproducible installs (directly serves §19.1 reproducibility). Use `uv sync --frozen` in CI.
- **LightGBM 4.6.0** — primary GBDT for `p_fukusho_hit`. Native categorical splitting (Fisher optimal partition on values only) is **structurally incapable of target-encoding leakage**. Use pandas `category` dtype with explicit `__MISSING__`/`__UNSEEN__` sentinels (avoid NaN→-1 codes). Frozen category maps per `feature_snapshot_id`.
- **CatBoost 1.2.10** — comparison GBDT and the **provably leak-safe categorical baseline** (ordered target statistics + ordered boosting, NeurIPS 2018). **`has_time=True` is mandatory** on every Pool (disables random permutation; without it, a row's encoding is informed by future rows). Sort Pool by `race_start_datetime`.
- **scikit-learn 1.9.0** — `CalibratedClassifierCV(cv='prefit', method='isotonic')` on a strictly-later disjoint calibration slice (NEVER default K-fold — it shuffles and leaks), `brier_score_loss`, `log_loss`, BL-4 logistic baseline. Note: `TimeSeriesSplit` is **NOT group-aware** (sklearn #19072 open) — do not use it on rows.
- **PostgreSQL 15.x** — system of record (raw/normalized/label/prediction/backtest layers). Raw EveryDB2 tables are immutable.
- **DuckDB 1.5.3 (Python wheel)** — **auxiliary only**, never a persistence layer. Bulk scans over Parquet, as-of aggregations, Postgres→Parquet materialization via `COPY ... TO '*.parquet'` + `postgres_scanner`.
- **Parquet via PyArrow 24.0.0** — immutable versioned snapshots; embed §12.4 metadata block (`dataset_version`, `feature_snapshot_id`, `label_version`, `feature_cutoff_datetime`, `prediction_timing`, train/val periods).
- **Streamlit 1.58.0** — local read-only UI; `st.cache_data` for reads, never `st.session_state` for derived data.

**Leakage-prevention-critical supporting libraries (build these patterns FIRST as stack bootstrap):**

- **pandas 3.0.3 `merge_asof(direction='backward', by=<entity>)`** — the 5-line PIT join primitive that replaces a heavyweight feature store. Always `.sort_values()` immediately before (raises if unsorted).
- **mlxtend `GroupTimeSeriesSplit`** — REQUIRED for race_id-level integrity. Fills the gap sklearn `TimeSeriesSplit` leaves (it can split rows of the same `race_id` across train/test, violating §8.4/§15.4).
- **CalibratedClassifierCV prefit pattern** — calibrator fit on a chronological slice disjoint from training and strictly later in time; unit-test the assertion `max(train.race_date) < min(calib.race_date)`.
- **Frozen category maps** — fit on training window only, persist, apply same map to val/test; unknown IDs map to `__UNSEEN__` (not NaN).

### Expected Features

Phase 1 scope is tightly bounded by the authoritative requirements v1.3. The MVP is the full table-stakes list **plus** the must-have differentiators (calibration, as-of leakage prevention, sales-start label, fixed-odds-snapshot policy, refund/dead-loss accounting, reproducibility version-stamping). See `FEATURES.md` for the full prioritization matrix.

**Must have (table stakes — Core Value guardians; missing any = the system cannot answer "did the model add value, leak-free, reproducibly?"):**

- EveryDB2 → PostgreSQL raw data quality check (§6.4: tables, counts, date range ≥2015-01-01, NULLs, dup keys, mojibake, code anomalies) — **gates everything**; first thing built.
- `normalized` layer ETL with **code-based class normalization** (by `race_condition_code`, NOT name string — the 2019 reform left the code unchanged) + `post_2019_class_system_flag`.
- **Fukusho label generation + payout-table reconciliation** (§10) — `sales_start_entry_count` (direct or restored), `fukusho_hit_raw` vs `fukusho_hit_validated`, `label_validation_status` taxonomy (`validated`/`inferred`/`dead_heat`/`unresolved`), dead-heat + cancellation/refund handling.
- **As-of feature management** (§13) — `as_of_datetime`, `feature_cutoff_datetime`, `feature_availability_version`, per-feature `available_from_timing` + `leakage_risk_level`. Phase 1-A may ONLY use entry/post_position timing.
- Phase 1-A model producing `p_fukusho_hit` (LightGBM + CatBoost, odds-free, categorical rules §14.3/§14.4, missing-reason taxonomy §14.5).
- Baselines BL-1..BL-5 (BL-3 odds-inverse interpreted as **market reference only**, NOT same-info comparison).
- EV_lower/EV_upper at fixed `odds_snapshot_policy`; `recommend_rank` S/A/B/C/D from EV+p+odds_lower only (no immature confidence — that's Phase 2).
- Fixed-rule virtual-purchase backtest (`fukusho_ev_v1`: 100 yen/bet, EV_lower≥1.05, p≥0.15, odds_lower≥1.5, top-2/race, no re-bets) with refund/dead-loss accounting.
- race_id-unit time-series split (rolling/expanding/fixed-holdout); train/test leakage across same race_id FORBIDDEN.
- Evaluation suite: hit rate, recovery rate, P/L, max drawdown, bet count, Brier, LogLoss, calibration curve (overall + per-segment), **sum(p) distribution check**, stability-by-segment.
- Reproducibility version-stamping on every artifact (`model_version`, `feature_snapshot_id`, `label_generation_version`, `odds_snapshot_policy`, `backtest_strategy_version`, `as_of_datetime`, `odds_snapshot_at`).
- Minimum tests (§17.3); Streamlit minimal UI (§16.1); CSV export (§16.2 — pinned column lists).

**Should have (differentiators — where quality is won or lost; the literature under-discusses these, which is itself the moat):**

- **Probability calibration with acceptance criteria** (§15.2/§15.3) — yearly calibration curve has no extreme inversions; per-bin monotone-ish; per-axis (popularity/odds/course/field-size/year). Crown jewel of EV trustworthiness.
- **`sum(p)` distribution check per race** — sanity that probabilities aggregate to theoretical payout-places (~3.0 for ≥8-horse, ~2.0 for 5–7). Cheap, very high signal, rarely done.
- **Leakage-free as-of validation with `feature_availability` taxonomy** — the discipline itself, not any single component.
- **Sales-start-time fukusho label + payout-table priority** with the `label_validation_status` taxonomy — prevents large-scale label corruption.
- **Fixed `odds_snapshot_policy` with hindsight-selection ban** + `odds_missing_policy = no_bet` for Phase 1.
- **Refund vs dead-loss accounting** — scratch/exclusion → `effective_stake=0`; breakdown (競走中止) → dead-loss (-100). Load-bearing for honest recovery rate.
- **Ability-prediction / EV-evaluation separation** — odds NEVER in model features (Phase 1-A); research confirms place/show pools are LESS efficient than win pools (exploitable via separation).
- **Stability-by-segment evaluation** — aggregate recovery rate hides segment collapse.

**Defer (v2+ — DO NOT start in Phase 1):**

- Race-day-morning model (B), body-weight-announced model (C), pre-start odds model (D).
- Prediction-confidence score (variance/calibration error/similar-sample count) feeding `recommend_rank`.
- Wide (ワイド) candidates + wide EV; trifecta (三連複) EV (combinatorial explosion).
- MLflow / Optuna (§21 — after Phase 1 stabilizes).
- Calibration improvement pass; Streamlit display extensions; auto-retrain pipeline.

**Anti-features (explicitly excluded — see FEATURES.md §Anti-Features table):**

- **Real-money betting / auto-voting / auto-purchase** (§3.3, §19.3 — out of scope, safety + legal).
- Hindsight odds-timepoint selection; final odds as decision input (FORBIDDEN §11.2).
- Final starter count as label basis; breakdown exclusion from backtest (FORBIDDEN §10.6).
- Same-day race-condition aggregates in Phase 1-A (§13.4); post-race columns as features (§9.3).
- Obstacle/newcomer/non-fukusho-sale races in model (§7.3 — data saved, model excluded); overseas racing (§2.1).
- Phase 2/3 ticket types in Phase 1; target/mean encoding (banned §14.3); Optuna/MLflow in Phase 1.
- Wide/upset-index/comment-generation in Phase 1 UI (§16.1).
- Using BL-3 as a same-information-condition comparison (§14.2 caveat — it's a market reference only).

### Architecture Approach

A **single-direction, append-mostly, layered pipeline** in which each layer writes only to itself or downward, and each layer boundary is a leakage checkpoint that requires a timestamp assertion. PostgreSQL is the persistent source of truth; Parquet holds immutable versioned snapshots that models train on (never the live DB); DuckDB is an ephemeral analytical engine over Parquet/Postgres. The as-of join (`merge_asof(direction='backward')`), race_id-grouped time-ordered splitter, and snapshot manifest (`model_version`/`feature_snapshot_id`/`label_generation_version`/`odds_snapshot_policy`/`backtest_strategy_version`) are the architectural backbone, not optimizations. A heavyweight feature store (Feast/Hopsworks) is deliberately rejected for Phase 1 (single-node, data volumes fit in memory per snapshot, §12.1 "keep it simple").

**Major components (`src/` folder mirrors data-flow layers):**

1. **`etl/`** — raw → normalized only (type/code conversion, class normalization by `race_condition_code` + reform flag). MUST NOT read label/feature tables.
2. **`labels/`** — normalized → label layer: payout reconciliation, `sales_start_entry_count` restoration, `label_validation_status`, dead-heat/scratch/DNF handling. **Highest-risk layer.**
3. **`features/`** — normalized + label(as target only) → PIT-correct feature rows. Enforces `feature_cutoff_datetime` per row; reads as-of catalog from `config/`.
4. **`models/`** — training (BL-1..BL-5, LightGBM, CatBoost). **Reads Parquet snapshots only — never live DB** (anti-leakage + train/serve-skew prevention).
5. **`prediction/`** — scoring (odds-free → `p_fukusho_hit`) + EV module (odds at fixed snapshot → EV/rank). Separate modules so "odds never enters features" is auditable at the boundary.
6. **`backtest/`** — race_id-grouped splitter (Pattern 2) + virtual-purchase simulator owning `odds_snapshot_policy` enforcement, refund/scratch/DNF/dead-heat accounting.
7. **`evaluation/`** — calibration, Brier, LogLoss, sum(p) distribution, stability slices (acceptance gates).
8. **`snapshots/`** — Parquet writers + metadata stamping (the immutability boundary).
9. **`config/`** — single source of truth for all versioned knobs (`odds_snapshot_policy`, `backtest_strategy_version`, prediction-timing declarations, as-of catalog seed).

### Critical Pitfalls

Top pitfalls by blast radius (see `PITFALLS.md` for all 10 + recovery costs + "Looks Done But Isn't" acceptance checklist). All are **silent** — the pipeline runs and emits wrong numbers. None are caught by "does it run" testing; all require adversarial audit tests.

1. **Future-information (lookahead) leakage in past-performance aggregates** — same-day "当日ここまで" stats, unbounded windows, recomputed-at-build-time rolling aggregates, `SELECT *` pulling 通過順/上がり/確定着順/確定払戻. **Prevent:** `feature_cutoff_datetime` as a hard filter (not a column), `feature_availability` registry with a fail-loud allowlist test (no `post_race_only`/`odds_snapshot_available`/`body_weight_announced`/`race_day_morning` feature in Phase 1-A matrix), time-bounded (not count-bounded) windows, explicit column allowlists, same-day isolation.
2. **Hindsight odds-snapshot selection** — picking the most profitable snapshot post-hoc; the #1 way racing backtests lie, invisible in code. **Prevent:** pre-register candidate policies + selection rule on a validation period disjoint from test; `odds_missing_policy = no_bet` (never substitute); report ALL candidate policies × BT configs, not the winner; version on change.
3. **Fukusho label-definition errors (wrong payout-places basis)** — using `final_starter_count` instead of restored `sales_start_entry_count`; conflating "top-3" with "payout-eligible" for 5–7 horse fields (only top 2 pay). **Prevent:** §10.4 priority chain (payout table > `sales_start_entry_count` > 着順 > final count), `label_validation_status` tracking, gate the phase — no model training until payout-table reconciliation >99.9% on sample.
4. **Target-encoding / categorical-encoding leakage** — pre-target-encoding categoricals (esp. then handing numerics to CatBoost, defeating Ordered TS); negative LightGBM codes dropping real categories; no smoothing for rare IDs. **Prevent:** native categorical handling in both GBDTs; never pre-encode then pass to CatBoost; non-negative codes with explicit `__MISSING__` sentinel; leak diagnostic (rare categories should shrink toward mean, not match their own label).
5. **Time-series validation leaks — same `race_id` and same-day info crossing train/test** — random/KFold split; `TimeSeriesSplit` at row level without grouping; `GroupKFold` without temporal order. **Prevent:** split unit is `race_id`, ordered by `race_start_datetime`; `mlxtend.GroupTimeSeriesSplit`; hard assertion `set(train_races).isdisjoint(test_races)` for every fold.

(Honorable mentions: Pitfall 6 DNF exclusion inflating ROI; Pitfall 7 2019 class-reform mishandling — normalize by code not name; Pitfall 8 miscalibration breaking EV; Pitfall 9 non-reproducibility from un-versioned artifacts; Pitfall 10 mean-only `sum(p)` check hiding tail failures.)

---

## Implications for Roadmap

Phase 1 is a single milestone (the MVP) but decomposes internally into a **strict dependency DAG**, not a wish list. Each layer trusts the one below — do not interleave model work before labels and features are locked. The build order below is the single most roadmap-relevant output of this research; it directly drives phase decomposition.

### Build-Order DAG (the source of truth for phase cuts)

```
1. raw quality gate (§6.4)                 ── TRUST GATE: nothing below runs until this passes
        ▼
2. normalized ETL (§12.2, §12.3)            ── class normalization by race_condition_code + reform flag
        ▼
3. label generation + payout reconciliation (§10) + sales_start_entry_count restoration
        │                                  ── LONG POLE; incl. label_validation_status, dead-heat, scratch handling
        │                                  ── gate: payout-table reconciliation >99.9% on sample
        ▼
4. as-of catalog + feature builder (§13)    ── feature_cutoff_datetime, available_from_timing enforcement
        │                                  ── Phase 1-A timing only initially
        ▼
5. Parquet snapshot layer + version manifest (§12.4, §19.1)
        ▼
6. baselines + Phase 1-A model (§14)        ── BL-1..BL-5, then LightGBM/CatBoost off snapshots
        ▼
7. prediction/scoring → p_fukusho_hit (§8.2) ── stamped with model_version, feature_snapshot_id, as_of
        ▼
8. EV module + recommend rank (§8.3, §11.1, §11.5)  ── odds_snapshot_policy fixed
        ▼
9. backtest splitter (race_id-grouped) + simulator (§11.4–11.6, §15.4)
        │                                  ── refund/scratch/DNF/dead-heat; fixed odds policy
        ▼
10. evaluation + acceptance gates (§15)     ── calibration, Brier, LogLoss, sum(p) distribution, stability slices
        ▼
11. Streamlit + CSV export (§16)            ── read-only presentation; built last (no architectural deps into it)
```

### Phase 1: Trust & Foundation (DAG steps 1–2)

**Rationale:** Trust in raw data is the foundation; requirements explicitly make §6.4 checks a gate. Building on unvalidated raw data wastes every downstream effort. Class normalization by `race_condition_code` (§12.3) is a label/feature input, not cosmetic — Pitfall 7 lives here.
**Delivers:** Quality-checked raw layer; `normalized` layer with typed/coded columns + `post_2019_class_system_flag` + `class_level_numeric`.
**Addresses:** Raw quality check table-stakes feature; `normalized` ETL table-stakes.
**Avoids:** Pitfall 7 (class-system reform mishandling); Pitfall 9 foundations (raw immutability).
**Stack:** PostgreSQL 15, psycopg3, DuckDB for §6.4 audits.

### Phase 2: Labels (DAG step 3) — HIGHEST RISK, OWN PHASE

**Rationale:** The label layer is the single highest-risk layer for label leakage and mislabeling (Pitfalls 3 and 6 live here). The model cannot be trusted until labels are correct and reconciled. This is the **long pole** of Phase 1 and deserves its own phase with heavy testing. `sales_start_entry_count` restoration logic cannot be specified without inspecting actual EveryDB2/JRA-VAN columns.
**Delivers:** `fukusho_hit_raw`, `fukusho_hit_validated`, restored `sales_start_entry_count`, `label_validation_status` taxonomy, payout-table reconciliation, dead-heat/scratch/DNF handling.
**Addresses:** Fukusho label generation + payout reconciliation (table-stakes); `sales_start_entry_count` acquisition/restoration (table-stakes).
**Avoids:** Pitfall 3 (label basis); Pitfall 6 (DNF exclusion — DNF kept as `fukusho_hit = 0`).
**Gate:** No model training until payout-table reconciliation >99.9% agreement on sample; `unresolved` fraction reported and low.

### Phase 3: Features & Snapshots (DAG steps 4–5) — LEAKAGE-PREVENTION BACKBONE

**Rationale:** The as-of catalog and `feature_cutoff_datetime` enforcement are the leak firewall (Pitfall 1 primary prevention). Snapshots freeze already-as-of-correct features; you cannot build a trustworthy snapshot without the as-of filter already enforcing. The `available_from_timing` mapping depends on exact JRA-VAN data availability timings — schema-grounded, not generic.
**Delivers:** `feature_def` as-of catalog; PIT-correct feature builder (`merge_asof(direction='backward')`); Parquet snapshot layer with §12.4 metadata manifest; frozen category maps.
**Addresses:** As-of feature management (table-stakes); reproducibility version-stamping foundations.
**Avoids:** Pitfall 1 (lookahead leakage — fail-loud feature-allowlist test passes); Pitfall 9 (snapshot immutability + manifest).
**Gate:** Feature-allowlist test passes (no banned timing features in Phase 1-A matrix); PIT-join sortedness unit test.

### Phase 4: Model (DAG steps 6–7)

**Rationale:** Models train off stamped Parquet snapshots only (anti-leakage + train/serve-skew prevention). Encoding strategy and calibration live here. The reproduce-smoke-test (Pitfall 9) is wired here.
**Delivers:** BL-1..BL-5 baselines; LightGBM 4.6 (native categoricals, `__MISSING__`/`__UNSEEN__` sentinels, frozen maps) and CatBoost 1.2.10 (`cat_features` + `has_time=True`, chronologically sorted Pool); `CalibratedClassifierCV(cv='prefit', method='isotonic')` on a strictly-later disjoint slice; prediction/scoring module emitting `p_fukusho_hit` with provenance.
**Addresses:** Phase 1-A model + baselines + prediction (table-stakes); calibration (differentiator).
**Avoids:** Pitfall 4 (target-encoding leak — native handling); Pitfall 8 (calibration — held-out calibrator, EV reads calibrated p); Pitfall 9 (fixed seeds, reproduce test).

### Phase 5: EV & Backtest (DAG steps 8–10) — HONEST VERDICT

**Rationale:** EV consumes `p_fukusho_hit` (step 7→8). Backtest simulates virtual purchases using EV/rank (step 8→9) and reuses the exact prediction pipeline (no separate backtest model). Evaluation metrics are computed over backtest + prediction outputs (step 9→10). All candidate `odds_snapshot_policy` × BT configs reported, never the winner alone.
**Delivers:** EV module (fixed `odds_snapshot_policy`, `odds_missing_policy = no_bet`); recommend_rank S/A/B/C/D; race_id-grouped backtest splitter + simulator (refund/scratch/DNF/dead-heat; `effective_stake` accounting); evaluation suite with acceptance gates (calibration curve overall + per-axis, Brier, LogLoss, sum(p) distribution mean/median/std/p10/p90 by field-size bucket, stability-by-segment).
**Addresses:** EV + recommend_rank + backtest + evaluation (table-stakes); fixed-odds-snapshot policy + refund/dead-loss accounting + stability-by-segment (differentiators).
**Avoids:** Pitfall 2 (hindsight odds — pre-registration, all-policies reporting); Pitfall 5 (split leak — `GroupTimeSeriesSplit`, disjoint assertion); Pitfall 6 (effective_stake); Pitfall 8 (per-axis calibration gate); Pitfall 10 (`sum(p)` distribution gate).
**Gate:** Acceptance criteria §15.2/§15.3 verified before presentation.

### Phase 6: Presentation (DAG step 11)

**Rationale:** Streamlit/CSV are leaf nodes — zero architectural dependencies point into them. Built last because the acceptance gates in Phase 5 are what make the displayed numbers trustworthy. Column schemas (§16.2) designed early so ETL writes to compatible shapes, but UI built last.
**Delivers:** Streamlit minimal UI (§16.1 column list including all snapshot/reproducibility metadata inline); CSV export (§16.2 pinned column lists, prediction + backtest).
**Addresses:** Streamlit UI + CSV export (table-stakes).
**Avoids:** UX pitfalls (showing `p` without `odds_snapshot_policy`/`as_of_datetime`; ROI without `backtest_strategy_version`; raw uncalibrated `p`; rank without EV/p/odds inputs; no per-year/per-course slicing).

### Phase Ordering Rationale

- **Why this order (dependencies):** Layer trust flows strictly downward. (1) must precede everything; (2) precedes (3) and (4) — labels/features need typed, class-normalized data; (3) precedes (4) and (5) — features use label as target, snapshots need stable label definition; (3) precedes (9) — backtest outcome accounting depends on correct label/validation; (4) precedes (5) — snapshots freeze as-of-correct features; (5) precedes (6) — models train off snapshots; (7)→(8)→(9)→(10)→(11) is a linear prediction→EV→backtest→eval→presentation chain.
- **Why this grouping (architecture patterns):** Phases mirror the `src/` folder structure — a developer reading a path knows which layer they're in; a reviewer can ask "does this folder write upward?". Phase 3 is the leakage-prevention backbone (Patterns 1 + 4). Phase 5 owns Patterns 2 + 3 enforcement at the backtest boundary.
- **How this avoids pitfalls:** Phases 1–3 are the **leakage-critical foundation** as a single gated sequence — no model work interleaved before labels and features are locked. Each phase has an explicit gate tied to a Pitfall verification. Pitfalls 1/3/4/5 are undetectable by functional testing — budget explicit time for adversarial audit tests in Phases 2/3/4/5, not just feature implementation.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase <N>`):

- **Phase 2 (Labels):** Highest complexity. The `sales_start_entry_count` restoration logic (§10.3) **cannot be specified without inspecting actual EveryDB2/JRA-VAN columns** — exact payout-table schema, withdrawal-announcement timestamps, dead-heat representation. Schema-grounded research against real data, not generic patterns.
- **Phase 3 (Features & Snapshots):** The `available_from_timing` mapping depends on exact JRA-VAN data availability timings. Needs schema-grounded research on what timings EveryDB2 actually exposes (entry_confirmed, post_position_confirmed, race_day_morning, body_weight_announced, odds_snapshot_available).

Phases with standard patterns (skip research-phase):

- **Phase 1 (Trust & Foundation):** §6.4 quality checks + class normalization are well-specified by requirements; Pitfall 7 is well-documented (code spans both eras).
- **Phase 4 (Model):** Standard GBDT patterns; leakage-prevention configuration fully specified in STACK.md. The leak diagnostic and reproduce-smoke-test are well-understood.
- **Phase 5 (EV & Backtest):** Rolling/expanding/fixed-holdout + group split are well-understood primitives. **Caveat:** odds-snapshot-policy mechanics depend on what odds snapshots EveryDB2 actually stores (timing granularity) — this is the one sub-question that may need a mini-research spike inside Phase 5.
- **Phase 6 (Presentation):** Standard Streamlit + CSV patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI JSON API 2026-06-16; all ship Python 3.12 wheels. Leakage-prevention guidance cross-checked against official LightGBM/CatBoost/scikit-learn docs and the CatBoost NeurIPS 2018 paper. |
| Features | HIGH | Phase 1 scope tightly bounded by authoritative requirements v1.3; competitor/validation literature strongly supports the table-stakes vs differentiator split (place/show pools less efficient than win = academic consensus). |
| Architecture | HIGH | Industry-standard primitives (PIT joins, group-aware time-series split, snapshot reproducibility, Postgres+Parquet+DuckDB division of labor) corroborated by multiple authoritative sources. |
| Pitfalls | HIGH (JRA-rule), MEDIUM (generic ML) | JRA-rule pitfalls anchored to requirements v1.3 §10/§11/§13 + official JRA/JRA-VAN sources. Generic ML-leakage/calibration/CV claims are well-established practitioner consensus but web-sourced (single provider) — verify against current docs during implementation. |

**Overall confidence:** HIGH. The research is unusually well-aligned because the requirements doc is authoritative and prescriptive. The risk is not in *what* to build but in *discipline of execution* — every pitfall is a silent failure mode.

### Gaps to Address (defer to Phase 1 implementation-time research against real data)

These cannot be resolved by literature research; they require inspecting actual EveryDB2/JRA-VAN data during Phase 1. Each gates a specific sub-step.

- **Exact payout-table schema (Phase 2):** Column names/types for 払戻 table; how dead-heats are represented; how refunds are recorded. Gates label reconciliation logic.
- **`sales_start_entry_count` availability + restoration path (Phase 2):** Whether EveryDB2 exposes it as a direct column (§10.3 path 1) or it must be reconstructed from entry list + scratch/除外 announcement timestamps (path 2). Gates the entire label layer — if reconstruction is needed, the logic is non-trivial and the `unresolved` fraction must be reported.
- **Withdrawal-announcement timestamps (Phase 2):** Granularity and field names for scratch/除外/取消 events. Gates refund vs dead-loss accounting (Pitfall 6).
- **`available_from_timing` for each candidate feature (Phase 3):** Which JRA-VAN columns are confirmed at entry_confirmed / post_position_confirmed / race_day_morning / body_weight_announced / odds_snapshot_available / post_race_only. Gates the as-of catalog and the Phase 1-A feature-allowlist test.
- **Odds-snapshot timing granularity (Phase 5):** What snapshots EveryDB2 actually stores (30-min-before? 10-min-before? final? at what granularity?). Gates the candidate `odds_snapshot_policy` set and the `no_bet` missing-policy.
- **Backtest threshold tuning (Phase 5):** EV_lower≥1.05, p≥0.15, odds_lower≥1.5, top-2/race are explicit in §11.5 but **treat as tunable via backtest** — final values decided on validation period (not test), nested temporal split.

---

## Cross-Cutting Themes (synthesis — not a concatenation of the four files)

1. **Discipline is the moat.** All four researches independently converge: the edge is not a fancier model, it is correct labels, leakage-free as-of, fixed-odds-snapshot backtest, honest refund accounting, calibrated probabilities, and reproducibility stamps. The competitor table in FEATURES.md shows public racing-ML projects fail at exactly these points. The roadmap should make discipline visible (gates, audit tests, version stamps) rather than invisible infrastructure.

2. **Build leakage-prevention infrastructure FIRST as a stack bootstrap.** Before any feature/model work, the project needs: frozen category maps, `pandas.merge_asof` PIT joiner, `mlxtend.GroupTimeSeriesSplit` race_id-grouped splitter, `CalibratedClassifierCV(cv='prefit')` chronological calibrator, and the `feature_availability` registry with a fail-loud allowlist test. These are 5-line primitives that replace heavyweight infrastructure (feature stores) and close the silent-leak surfaces. Budget Phase 1/3 time for these explicitly.

3. **Two highest-risk complexity centers gate the entire downstream chain:**
   - **Fukusho label generation (Phase 2):** `sales_start_entry_count` restoration + payout-table reconciliation + dead-heat + `label_validation_status` taxonomy. This is the long pole and the foundation — nothing downstream is trustworthy until labels are correct. Gate: payout-table reconciliation >99.9%.
   - **As-of / `feature_availability` taxonomy (Phase 3):** THE leakage-prevention mechanism. Most failure-prone area for backtest integrity. Gate: feature-allowlist test (no banned-timing feature in Phase 1-A matrix).

4. **Adversarial audit tests catch what functional tests cannot.** Pitfalls 1/3/4/5 are undetectable by "does it run" testing. The §17.3 minimum test set is exactly the high-leakage-risk surface. Budget explicit test-writing time in each phase, not as an afterthought. The "Looks Done But Isn't" checklist in PITFALLS.md is the Phase-1 acceptance gate.

5. **Phase 1 is implementation-verification scope — no real betting.** Recommendations are reference only (§19.3). This shapes the UI (label as 参考) and excludes auto-voting hooks. The verdict the system delivers is "did the model add value, leak-free, reproducibly?" — not "bet these horses."

---

## Sources

### Primary (HIGH confidence)

- **Authoritative requirements:** `docs/keiba_ai_requirements_v1.3.md` — sections 1.1, 2.1–2.2, 3.1–3.3, 5–6, 7.3, 8.1–8.4, 9.2–9.3, 10.1–10.6, 11.1–11.6, 12.1–12.5, 13.1–13.5, 14.1–14.5, 15.1–15.5, 16.1–16.2, 17.1–17.3, 18, 19.1–19.3, 20, 21. (Project's own authoritative source for all JRA rules, scope, and stack.)
- **Project context:** `.planning/PROJECT.md` — Core Value, Active/Out-of-Scope, Key Decisions.
- **PyPI JSON API (2026-06-16):** version verification for LightGBM 4.6.0, CatBoost 1.2.10, scikit-learn 1.9.0, pandas 3.0.3, pyarrow 24.0.0, DuckDB 1.5.3, psycopg3 3.3.4, Streamlit 1.58.0, mlxtend 4.x, pytest 9.1.0, ruff 0.15.17.
- **Official library docs:** LightGBM Advanced Topics (categorical non-negative int32); CatBoost NeurIPS 2018 paper (ordered TS + ordered boosting, prediction shift); scikit-learn 1.9 `CalibratedClassifierCV` (`cv='prefit'`, ≥1000-sample isotonic rule); pandas 3.0.3 `merge_asof` (`direction='backward'`, sorted-input); mlxtend `GroupTimeSeriesSplit`; DuckDB `postgres_scanner` + `COPY ... TO '*.parquet'`; psycopg3; uv (lockfile, frozen sync).
- **scikit-learn issues:** #19072 (group-aware `TimeSeriesSplit` still open — the gap `GroupTimeSeriesSplit` fills); #15013 (sigmoid under-corrects GBDTs → isotonic often better).
- **Academic (pari-mutuel market efficiency):** JSTOR (Efficiency in Pari-Mutuel Betting Markets); Wharton/Berkeley (The Favorite-Longshot Midas); Thaler JEP/AEA (Anomalies: Parimutuel Betting Markets); NBER (Explaining the FLB). Establishes place/show pools are LESS efficient than win pools — directly validates fukusho focus + ability/EV separation.

### Secondary (MEDIUM confidence)

- **Industry primitives (PIT joins, group-aware splits, reproducibility):** Hopsworks, Databricks Feature Store, ApXML, Towards Data Science, AWS SageMaker (point-in-time correctness); mlxtend/Kaggle/StackOverflow (GroupTimeSeriesSplit); CMU MLiP, DVC, arXiv (versioning/provenance/reproducibility); Nubank, Aerospike (train-serve skew).
- **Postgres + Parquet + DuckDB division of labor:** EthicalAds, Motherduck, Crunchy Data, pg_duckdb discussions.
- **JRA 2019 class reform:** JRA rules page; JRA-VAN developer forum topic 305; JRA-VAN data-change notice 2018-12-05 (code 005 spans 500万下/1勝クラス — corroborated across three sources).
- **Racing-ML methodology gaps (calibration, leakage, time-series backtest under-discussed):** r/MachineLearning, gmalbert/horse-racing-predictions, CodeWorks, DS StackExchange. Hobbyist-dominated; the gaps are themselves the signal.
- **EV/Kelly/backtest pitfalls:** Analytics.Bet, r/quant, Downey, arXiv (consistent warnings about estimated-vs-actual edge and backtest overstatement).
- **Streamlit + CSV patterns:** gmalbert, Streamlit app gallery, ethan-eplee, StableBet retrospective.

### Tertiary (LOW confidence — verify against docs during implementation)

- **Generic ML-leakage/calibration/CV web claims** (single provider, not cross-verified in PITFALLS.md): treat as well-established practitioner consensus, verify against current LightGBM/CatBoost/scikit-learn docs and the Niculescu-Mizil & Caruana ICML 2005 paper during implementation.
- **JRA fukusho refund/scratch/dead-heat mechanics from non-JRA sources:** websearch returned mostly non-JRA bookmaker rules; cross-check against JRA official rules (jra.go.jp) during implementation.

---
*Research completed: 2026-06-16*
*Ready for roadmap: yes*
