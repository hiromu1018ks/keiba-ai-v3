# Feature Research

**Domain:** JRA horse-racing prediction ML — 複勝 (fukusho / place-bet) payout-eligibility probability estimation + expected-value evaluation + fixed-rule virtual-purchase backtest + minimal Streamlit UI + CSV export
**Researched:** 2026-06-16
**Confidence:** HIGH (Phase 1 scope is tightly bounded by the authoritative v1.3 requirements doc; competitor/validation literature strongly supports the table-stakes vs differentiator split)
**Scope note:** Phase 1 = fukusho ONLY (requirements §3.3, §8.1). Wide (Phase 2) and trifecta (Phase 3) features are listed under Future/Anti only for boundary clarity. The requirements doc is authoritative; this file operationalizes it for roadmap planning.

---

## Feature Landscape

The requirements doc is unusually prescriptive — most features are already specified. Research's job here is not to invent features but to (a) classify each into table-stakes / differentiator / anti-feature, (b) flag complexity and dependencies that affect phase ordering, and (c) note where the doc leaves room (Phase 2+ candidates, thresholds to tune via backtest).

### Categorization Principle

- **Table stakes** = the system is unusable or untrustworthy without it. These are the "if Core Value fails, nothing else matters" items (requirements Core Value = leakage-free reproducible backtest).
- **Differentiator** = the features that distinguish this system from naive `predict-win-probability-and-bet` tutorials. These are where quality is won or lost.
- **Anti-feature** = explicitly excluded by requirements (§3.3, §7.3, §19.3) or by sound ML/betting hygiene that the doc endorses.

### Table Stakes (Users Expect These — Core Value Guardians)

Features the user (the solo developer-analyst) assumes exist. Missing any = the system cannot answer "did the model add value, leak-free, reproducibly?" — which is the entire point of Phase 1.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| EveryDB2→PostgreSQL raw data quality check | Without confirming the prereq data is sound, every downstream number is suspect. Doc §3.2/§6.4 lists exact checks (tables, counts, date range ≥2015-01-01, NULLs, dup keys, garbled chars, code anomalies). | MEDIUM | First thing built; gates everything. Must be idempotent/re-runnable as EveryDB2 updates flow in. |
| `normalized` layer ETL (type/code conversion, class normalization) | Raw JRA-VAN codes are unusable directly; class system changed in 2019 summer (doc §12.3). | MEDIUM | Class normalization MUST be by `race_condition_code`, not string. Carry `post_2019_class_system_flag`. Common under-specified pitfall. |
| Fukusho label generation + payout-table reconciliation | `fukusho_hit` is the target variable — get it wrong and the model learns the wrong thing (doc §10). Sales-start-time basis, NOT final starter count. | HIGH | Hardest correctness problem in Phase 1. Requires `sales_start_entry_count` (direct or restored from scratch/cancellation timestamps), `fukusho_hit_raw` (finish-order derived) vs `fukusho_hit_validated` (payout-table derived), `label_validation_status` taxonomy (`validated` / `inferred` / `dead_heat` / `unresolved`). Dead-heat and cancellation/refund handling must be correct. |
| As-of feature management (`as_of_datetime`, `feature_cutoff_datetime`, `feature_availability`) | This is THE leakage-prevention mechanism. Core Value depends on it. Doc §13. | HIGH | Per-feature `available_from_timing` (entry_confirmed, post_position_confirmed, race_day_morning, body_weight_announced, odds_snapshot_available, post_race_only). Phase 1-A may ONLY use entry/post_position timing. Most failure-prone area for backtest integrity. |
| Phase 1-A model producing `p_fukusho_hit` (post-entry / post-position model) | The prediction itself — without it nothing else matters. Doc §8.2/§9. | HIGH | LightGBM + CatBoost + sklearn baselines (§14). Categorical handling rules are strict (no negative codes for LightGBM; explicit `cat_features` for CatBoost; no target encoding on validation data). Missing-reason taxonomy (§14.5). |
| EV computation (`EV_lower` / `EV_upper`) at fixed odds snapshot | Core Value #2 — separates ability-prediction from market evaluation. Doc §11.1. | LOW | Trivial math: `EV = p × odds`. But the *policy discipline* (fixed snapshot, no hindsight swap) is what makes it table-stakes for trustworthiness. |
| Fixed-rule virtual-purchase backtest (`backtest_strategy_version: fukusho_ev_v1`) | Core Value #3 — the reproducible verdict on whether the model adds value. Doc §11.4/§15. | HIGH | 100 yen/bet, EV_lower ≥1.05, p ≥0.15, odds_lower ≥1.5, top-2 per race, no re-bets. Refund (scratch/exclusion → effective_stake=0) vs dead-loss (breakdown → -100) distinction is load-bearing. |
| race_id-unit time-series split (no train/test leakage across same race) | Without this, the backtest is fiction. Doc §8.4/§15.4. | MEDIUM | rolling / expanding / fixed-holdout. Same race_id in train AND test is FORBIDDEN. Same-day future-race info is FORBIDDEN. |
| Recommendation rank (S/A/B/C/D from EV + p + odds_lower only) | Users expect the model to surface candidates ranked. Doc §11.5. | LOW | Initial rule-based, NOT prediction-confidence-based (that's Phase 2). Thresholds are explicit in §11.5; treat as tunable via backtest. |
| Evaluation metrics suite (hit rate, recovery rate, P/L, max drawdown, bet count, Brier, LogLoss, calibration curve) | Without these, you cannot answer "is the model any good?". Doc §15.1. | MEDIUM | Calibration curve is the crown jewel (see Differentiator). Stability-by-segment (year/month/track/field-size/popularity-band/odds-band) is table-stakes because aggregate metrics hide segment collapse. |
| Streamlit minimal UI (race list, p, odds, EV, rank, snapshot metadata) | Phase 1 deliverable explicitly named in §16.1. Users expect to see the predictions. | MEDIUM | Read-only, local. Must show `odds_snapshot_policy`, `odds_snapshot_at`, `model_version`, `feature_snapshot_id`, `backtest_strategy_version` — the metadata IS the feature, because it proves reproducibility. |
| CSV export (prediction CSV + backtest CSV, exact column lists in §16.2) | Phase 1 deliverable; offline analysis/export is mandatory. Doc §16.2. | LOW | Column lists are pinned in the doc. Do not invent extra columns in Phase 1. |
| Reproducibility metadata persisted on every artifact (`prediction_version`, `feature_snapshot_id`, `model_version`, `label_generation_version`, `as_of_datetime`, `odds_snapshot_at`, `backtest_strategy_version`) | Core Value hygiene. Same conditions → same numbers. Doc §19.1. | MEDIUM | The hardest table-stakes item to retrofit if skimped on Day 1 — design the schema before writing ETL. |
| Baseline models (BL-1 constant-by-field-size, BL-2 popularity-rank, BL-3 odds-inverse, BL-4 logistic, BL-5 minimal LightGBM) | Cannot claim the model adds value without baselines. Doc §14.2. | MEDIUM | BL-3 (odds-inverse) is explicitly a *market reference*, NOT a same-information-condition comparison — interpret carefully (§14.2 caveat). |
| Minimum tests (label generation, payout reconciliation, scratch/exclusion/breakdown handling, odds-snapshot fixing, virtual-purchase rules, feature_cutoff, metric calc, race_id split, class normalization, categoricals/missing) | Without tests, you cannot trust the backtest. Doc §17.3. | HIGH | Phase 1 has a LOT of invariant-able logic (refund rules, label priority, as-of cutoffs). Tests are how you defend "leakage-free" to yourself. |

### Differentiators (Competitive Advantage / Quality Signal)

These are NOT expected by users of a generic "horse racing predictor". They are what make this system's verdicts trustworthy enough to act on. The racing-ML literature under-discusses most of these (per research), which is itself the differentiator.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Probability calibration (and acceptance criteria)** | A miscalibrated `p_fukusho_hit` makes EV meaningless — `EV = p × odds` only rewards you if `p` is honest. Doc §15.2/§15.3. | HIGH | Acceptance criteria: yearly calibration curve has no extreme inversions; per-bin actual rate roughly monotonic; LogLoss/Brier beats baselines. Calibration sliced by popularity-band, odds-band, track, field-size, year. This is where most horse-racing ML projects are silent. |
| **`sum(p)` distribution check per race** | Sanity check that probabilities aggregate to the theoretical payout-places count (≈3.0 for 8+ horse races, ≈2.0 for 5–7). Catches degenerate models that under/over-predict globally. Doc §15.2 (v1.3 addition). | LOW | Inspect mean, median, std, p10, p90. Cheap to compute, very high signal — flag this as a differentiator because few public projects do it. |
| **Leakage-free as-of validation with `feature_availability` taxonomy** | Most racing-ML backtests leak (post-race aggregates, future-race same-day info, final odds as decision odds). This system's strict as-of discipline is a genuine quality moat. Doc §13. | HIGH | The *discipline* is the differentiator, not any single component. Documented `leakage_risk_level` per feature. Detectable via invariant tests on `feature_cutoff_datetime`. |
| **Sales-start-time fukusho label (not final starter count) + payout-table priority** | Naive labels break when horses scratch after betting opens (changes payout-places) or dead-heats occur. Doc §10 (v1.3 hardening). The validation taxonomy (`validated` / `inferred` / `dead_heat` / `unresolved`) is rare in hobbyist projects. | HIGH | `sales_start_entry_count` restoration from scratch/exclusion timestamps when direct field absent. Phase 1 explicitly excludes `unresolved` races from train/eval. This single feature prevents large-scale label corruption. |
| **Fixed `odds_snapshot_policy` with hindsight-selection ban + missing-policy rules** | Picking the best odds-timepoint post-hoc is the #1 way racing backtests become fiction. Doc §11.2/§11.3 forbids it; Phase 1 default missing-policy = `no_bet`. | MEDIUM | Compare 30-min-before and 10-min-before fixed snapshots. The *policy enforcement* (can't swap timepoints after seeing results) is the differentiator. |
| **Refund vs dead-loss accounting (`effective_stake`, refund on scratch/exclusion, dead-loss on breakdown)** | Real-world JRA refunds scratches but NOT breakdowns. Naive backtests either refund everything (overstates recovery) or nothing (understates). Doc §10.6/§11.6 (v1.3). | MEDIUM | `effective_stake=0` on refund so recovery rate isn't distorted by refunded volume. Correct handling of breakdowns as losses is non-obvious and load-bearing. |
| **Ability-prediction / EV-evaluation separation (no odds in model features)** | Standard "put odds in the model" approaches bake in the favorite-longshot bias and can't detect genuine model edge. Doc §2.2. Research confirms place/show pools are LESS efficient than win pools — separation lets you exploit that. | HIGH | Odds used ONLY for EV. Phase 1-A features are odds-free. Phase 3 may relax with a separate market-correction model. |
| **Stability-by-segment evaluation (year/month/track/field-size/popularity/odds-band)** | Aggregate recovery rate can hide that the model only "works" in one sub-segment. Doc §15.1/§15.3. | MEDIUM | Calibration curve per segment. Reveals which conditions the model is trustworthy under — feeds Phase 2 confidence design. |
| **`recommend_rank` derived from EV + p + odds only (no immature prediction-confidence)** | Resists the temptation to ship a fake-confidence score. Doc §11.5. | LOW | Discipline-driven. Phase 2 will add real confidence (variance, calibration error, similar-sample count). |
| **Reproducibility version-stamping on every artifact** | Lets you re-derive any past verdict. Doc §19.1. Most racing projects are "I ran a notebook once." | MEDIUM | `model_version` + `feature_snapshot_id` + `label_generation_version` + `odds_snapshot_policy` + `backtest_strategy_version`. Parquet datasets carry the same metadata. |

### Anti-Features (Commonly Requested, Explicitly Excluded)

Doc §3.3, §7.3, §19.3, §21 are explicit. Several others are excluded by sound ML hygiene that the doc endorses.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-money ticket purchase / auto-voting / auto-purchase tool integration | "If the model is good, why not let it bet?" | Doc §3.3/§19.3 explicitly out-of-scope. The system does NOT guarantee profit; ranks are reference only. Safety + legal + scope-creep. | Virtual-purchase backtest with fixed rules. Real betting is a separate decision outside this system. |
| Phase 1 wide (ワイド) / trifecta (三連複) models | "More ticket types = more value." | Doc §3.3/§8.1: Phase 2/3. Wide needs pairwise joint place-probability; trifecta has combinatorial explosion. Bloating Phase 1 delays validation. | Phase 1 fukusho-only. Wide in Phase 2, trifecta in Phase 3. |
| Obstacle (障害) races, newcomer (新馬) races, non-fukusho-sale races in the model | "More data = better model." | Doc §7.3: data saved but model excluded. Different running dynamics, different fukusho availability. | Save data; exclude from Phase 1 train/eval. |
| Overseas racing | "More data / cross-market edges." | Doc §2.1: different race structures, ticket types, odds formation, takeout, data formats, track/class systems. | Japan-only. Adopt only transferable methodology (calibration, time-series CV, leakage prevention, categorical handling). |
| Hindsight odds-timepoint selection ("the 5-min-before odds gave the best recovery, use those") | "Optimize the backtest." | Doc §11.2: FORBIDDEN. This is the single biggest backtest-overstatement failure mode in racing ML. | Pre-declared fixed `odds_snapshot_policy`. Compare candidates, but never re-pick after results. |
| Using final odds / confirmed payouts / confirmed finish as features | "Best information = best model." | Future-information leakage. Doc §9.3/§13.4/§15.4 explicitly forbidden. | Strict as-of features; post-race data tagged `post_race_only` and excluded from Phase 1-A. |
| Same-day race-condition aggregates (today's jockey stats so far, today's track-bias, today's inside/outside bias) | "Free signal." | Doc §13.4: forbidden in Phase 1-A — uses future info from earlier same-day races. | Phase 1-A: only past-race (pre-race-day) aggregates. |
| Excluding breakdown (競走中止) horses from backtest | "They didn't really lose — they didn't finish." | Doc §10.6: FORBIDDEN. Excluding them erases real-world losses and overstates recovery rate. | Treat breakdown as a dead loss (-100). Only scratches/exclusions get refunds. |
| Final starter count as the fukusho label basis | "Simpler — just count who actually started." | Doc §10.2: WRONG. Post-betting-open scratches change payout-places; final count mislabels. | Sales-start-time `sales_start_entry_count` + payout-table priority. |
| Auto-hyperparameter tuning (Optuna) in Phase 1 | "Optimize everything." | Doc §21: defer. Premature optimization before features/eval are stable produces brittle models. | Manual/baseline configs in Phase 1. Optuna after Phase 1 stabilizes. |
| MLflow experiment tracking in Phase 1 | "Standard MLOps." | Doc §21: defer. Adds infra overhead before the value is proven. | Parquet datasets with stamped metadata in Phase 1. MLflow after stabilization. |
| Prediction-confidence-based `recommend_rank` in Phase 1 | "Show me how sure the model is." | Doc §11.5: confidence design is Phase 2. An immature confidence score misleads. | Rule-based rank from EV + p + odds_lower in Phase 1. Real confidence (variance, calibration error, similar-sample count) in Phase 2. |
| Wide candidates / wide EV / "upset index" (荒れ指数) / comment generation in Phase 1 UI | "Richer dashboard." | Doc §16.1: deferred. Upset index that uses odds would violate the no-odds-in-features rule for Phase 1-A. | Display only fukusho fields in Phase 1. Phase 2 adds wide/upset index (when odds-dependent features are in scope). |
| Predicting 1st-place winners (esp. longshots) as the primary objective | "Picking winners is the point of racing AI." | Doc §1.1: this system's primary purpose is undervalued fukusho-eligibility detection, NOT win prediction. | `p_fukusho_hit` as the headline output. Winner prediction is out of scope for Phase 1's value prop. |
| Using odds-inverse baseline (BL-3) as a same-information-condition model comparison | "Beat the market or go home." | Doc §14.2 caveat: BL-3 is a market reference, NOT a same-info comparison (it uses odds the Phase 1-A model is forbidden from using). | Compare against BL-1/BL-2/BL-4/BL-5 for "does the model beat simple predictors?" Use BL-3 only as a "is the AI vs market gap exploitable for EV?" reference. |

---

## Feature Dependencies

```
EveryDB2 raw quality check
    └──requires──> (prereq: EveryDB2 + PostgreSQL setup, done before project start)
    └──enables──> normalized ETL

normalized ETL (incl. class normalization)
    └──requires──> raw quality check
    └──enables──> fukusho label generation

fukusho label generation + payout reconciliation
    └──requires──> normalized ETL
    └──requires──> sales_start_entry_count (direct field OR restoration logic)
    └──requires──> payout (払戻) table
    └──enables──> model dataset (Parquet, metadata-stamped)

as-of feature management
    └──requires──> normalized ETL
    └──enables──> leak-free feature snapshots
    └──enables──> backtest integrity (invariant tests)

Phase 1-A model → p_fukusho_hit
    └──requires──> label generation
    └──requires──> as-of feature management
    └──requires──> baseline models (BL-1..BL-5) for comparison

EV computation (EV_lower / EV_upper)
    └──requires──> p_fukusho_hit
    └──requires──> fixed odds_snapshot_policy (no hindsight)
    └──enables──> recommend_rank

recommend_rank (S/A/B/C/D)
    └──requires──> EV computation
    └──requires──> p_fukusho_hit
    └──requires──> fukusho_odds_lower

virtual-purchase backtest
    └──requires──> recommend_rank (or EV directly)
    └──requires──> fixed odds snapshot
    └──requires──> payout table (for actual payout_amount)
    └──requires──> scratch/exclusion/breakdown handling (effective_stake)
    └──requires──> race_id-unit time-series split
    └──enables──> evaluation metrics
    └──enables──> recovery-rate / P/L / max drawdown

evaluation metrics suite
    └──requires──> backtest results
    └──requires──> baseline models (for LogLoss/Brier comparison)
    └──enables──> calibration curve / sum(p) check / stability-by-segment
    └──enables──> threshold tuning (EV/p/odds/max-bets-per-race)

Streamlit UI
    └──requires──> prediction outputs (p, EV, rank)
    └──requires──> snapshot metadata columns
    └──enhances──> user trust via visible reproducibility metadata

CSV export
    └──requires──> prediction + backtest tables in the §16.2 schema
    └──conflicts──> ad-hoc extra columns (resist in Phase 1)

calibration acceptance criteria
    └──requires──> evaluation metrics
    └──enhances──> trust in p_fukusho_hit → trust in EV
    └──enables──> Phase 2 confidence design

Conflicts:
  odds-as-feature ──conflicts──> ability/EV separation (Core Value)
  final-starter-count label ──conflicts──> sales-start-time label (correctness)
  breakdown exclusion ──conflicts──> honest recovery rate
  hindsight odds timepoint ──conflicts──> reproducible backtest
  same-day aggregates ──conflicts──> as-of leakage prevention
  Phase 2/3 ticket types ──conflicts──> Phase 1 scope discipline
```

### Dependency Notes

- **Everything requires the raw quality check first** — there is no Phase 1 deliverable that can be trusted if the source data is bad. The quality check is also the first thing to re-run after EveryDB2 updates.
- **Label generation is the long pole** — it requires `sales_start_entry_count` (which may need restoration), payout-table reconciliation, dead-heat handling, and a `label_validation_status` taxonomy. Schedule research/prototyping time here. It blocks the model dataset.
- **As-of management is a horizontal dependency** — every feature consumer needs it. Design the schema and the `feature_availability` taxonomy BEFORE writing feature code, not after.
- **Backtest requires the full chain** — p → EV → rank → fixed snapshot → payout table → refund/dead-loss accounting → race_id split. Skipping any link corrupts the verdict.
- **Streamlit/CSV are leaf nodes** — they only require the prediction/backtest tables to exist. Build them last but design their column schemas (§16.2) early so ETL writes to compatible shapes.
- **Calibration is the differentiator that ENABLES Phase 2** — Phase 2's "prediction confidence" depends on having trustworthy per-bin error rates. Under-investing in calibration in Phase 1 cripples Phase 2.

---

## MVP Definition

### Phase 1 = MVP (this milestone)

The requirements doc pins Phase 1 scope precisely. The MVP is the full table-stakes list plus the must-have differentiators (calibration, as-of leakage prevention, sales-start label, fixed-odds-snapshot policy, refund/dead-loss accounting, reproducibility version-stamping).

- [ ] Raw quality check (gates everything)
- [ ] `normalized` ETL with code-based class normalization + `post_2019_class_system_flag`
- [ ] Fukusho label generation: `sales_start_entry_count` (direct or restored), `fukusho_hit_raw` vs `fukusho_hit_validated`, payout-table priority, dead-heat handling, `label_validation_status` taxonomy
- [ ] As-of feature management: `as_of_datetime`, `feature_cutoff_datetime`, `feature_availability_version`, per-feature `available_from_timing` + `leakage_risk_level`
- [ ] Phase 1-A model producing `p_fukusho_hit` (LightGBM + CatBoost, odds-free features, categorical rules per §14.3/§14.4, missing-reason taxonomy per §14.5)
- [ ] Baselines BL-1 through BL-5 (BL-3 interpreted as market-reference only)
- [ ] EV_lower / EV_upper at fixed `odds_snapshot_policy` (30-min-before and 10-min-before compared)
- [ ] `recommend_rank` S/A/B/C/D from EV + p + odds_lower
- [ ] Fixed-rule virtual-purchase backtest (`fukusho_ev_v1`, with refund/dead-loss accounting)
- [ ] race_id-unit time-series split, train/test leakage forbidden
- [ ] Evaluation: hit rate, recovery rate, P/L, max drawdown, bet count, Brier, LogLoss, calibration curve (overall + by segment), sum(p) distribution (mean/median/std/p10/p90), stability-by-segment
- [ ] Calibration acceptance criteria (§15.2) verified
- [ ] Streamlit minimal UI (§16.1 column list, incl. snapshot metadata)
- [ ] CSV export (§16.2 column lists, prediction + backtest)
- [ ] Reproducibility version-stamping on all artifacts
- [ ] Minimum tests (§17.3 list)

### Add After Phase 1 Validation (Phase 2 candidates — DO NOT start in Phase 1)

- [ ] Race-day-morning model (B) — uses morning track condition + weather
- [ ] Body-weight-announced model (C) — uses body weight + delta
- [ ] Prediction-confidence score (variance, calibration error, similar-sample count) feeding `recommend_rank`
- [ ] Wide (ワイド) candidates + wide EV (requires pairwise joint place-probability)
- [ ] Calibration improvement pass
- [ ] Streamlit display extensions (wide candidates, wide EV, upset index when odds-in-features is in scope, comment generation)
- [ ] MLflow / Optuna evaluation (doc §21: after Phase 1 stabilizes)

### Future Consideration (Phase 3+)

- [ ] Pre-start odds model (D) with time-series odds + vote-flow features
- [ ] Market-correction model (odds-dependent, separate from ability model)
- [ ] Trifecta (三連複) EV model — beware combinatorial explosion (doc §21)
- [ ] Automated model retraining pipeline

---

## Feature Prioritization Matrix

Priority key: P1 = Phase 1 must-have; P2 = Phase 2; P3 = Phase 3+.

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| Raw quality check | HIGH | MEDIUM | P1 | 1 |
| `normalized` ETL + class normalization | HIGH | MEDIUM | P1 | 1 |
| Fukusho label + payout reconciliation | HIGH | HIGH | P1 | 1 |
| `sales_start_entry_count` acquisition/restoration | HIGH | HIGH | P1 | 1 |
| As-of feature management | HIGH | HIGH | P1 | 1 |
| Phase 1-A model → `p_fukusho_hit` | HIGH | HIGH | P1 | 1 |
| Baselines BL-1..BL-5 | HIGH | MEDIUM | P1 | 1 |
| EV_lower / EV_upper (fixed snapshot) | HIGH | LOW | P1 | 1 |
| `recommend_rank` (rule-based) | MEDIUM | LOW | P1 | 1 |
| Virtual-purchase backtest | HIGH | HIGH | P1 | 1 |
| Refund/dead-loss accounting | HIGH | MEDIUM | P1 | 1 |
| race_id time-series split | HIGH | MEDIUM | P1 | 1 |
| Evaluation metrics suite | HIGH | MEDIUM | P1 | 1 |
| Calibration curve + acceptance criteria | HIGH | MEDIUM | P1 | 1 (differentiator) |
| sum(p) distribution check | MEDIUM | LOW | P1 | 1 (differentiator) |
| Stability-by-segment eval | HIGH | MEDIUM | P1 | 1 (differentiator) |
| Reproducibility version-stamping | HIGH | MEDIUM | P1 | 1 (differentiator) |
| Streamlit minimal UI | MEDIUM | MEDIUM | P1 | 1 |
| CSV export | MEDIUM | LOW | P1 | 1 |
| Minimum tests (§17.3) | HIGH | HIGH | P1 | 1 |
| Prediction-confidence rank | MEDIUM | HIGH | P2 | 2 |
| Race-day-morning model | MEDIUM | HIGH | P2 | 2 |
| Body-weight model | MEDIUM | HIGH | P2 | 2 |
| Wide candidates + EV | HIGH | HIGH | P2 | 2 |
| Calibration improvement pass | MEDIUM | HIGH | P2 | 2 |
| Streamlit extensions | LOW | MEDIUM | P2 | 2 |
| MLflow / Optuna | LOW | MEDIUM | P2 | 2 (eval only) |
| Pre-start odds model | MEDIUM | HIGH | P3 | 3 |
| Market-correction model | MEDIUM | HIGH | P3 | 3 |
| Trifecta EV | MEDIUM | HIGH | P3 | 3 |
| Auto-retrain pipeline | LOW | HIGH | P3 | 3 |
| Real-money betting | — (anti) | — | — | NEVER (anti-feature) |
| Auto-voting | — (anti) | — | — | NEVER (anti-feature) |
| Overseas racing | — (anti) | — | — | NEVER (anti-feature) |
| Obstacle/newcomer model | — (anti) | — | — | NEVER (anti-feature, data only) |

---

## Competitor / Reference Approach Analysis

Based on web research (confidence MEDIUM — public racing-ML projects are mostly hobbyist; academic literature is more rigorous). The point is not "feature parity" but "where does this system's discipline outperform typical projects".

| Capability | Typical public racing-ML project | Academic literature | This system (Phase 1) |
|---------|---------|---------|---------|
| Prediction target | Win probability (sometimes top-3) | Win, place, show (Harville-derived) | **`p_fukusho_hit`** = place-payout-eligibility, sales-start-time defined, payout-table-validated |
| Label basis | Final starter count / finish order | Varies | **Sales-start-time + payout-table priority** with `label_validation_status` |
| Odds usage | Often a model feature | Often a feature or the comparison | **Odds ONLY for EV**, never a Phase 1-A feature (ability/EV separation) |
| Calibration | Rarely assessed | Assessed in rigorous work (e.g., gmalbert repo compares implied vs actual) | **Acceptance criteria + multi-segment calibration curves** (table-stakes quality gate) |
| sum(p) sanity check | Not done | Rarely | **Mandatory** (mean/median/std/p10/p90 vs theoretical payout-places) |
| Leakage prevention | Often leaks (future races, final odds) | Discussed but under-implemented | **Strict as-of** with per-feature `available_from_timing` + `leakage_risk_level` |
| Backtest split | Random / chronological-by-row | Time-series, sometimes race-grouped | **race_id-unit, time-series, no train/test cross-race** |
| Odds timepoint | Final odds or "best" | Varies | **Fixed `odds_snapshot_policy`**, hindsight-selection forbidden |
| Refund handling | Often ignored or refunded-all | Discussed in JRA-specific work | **Scratch/exclusion → refund (effective_stake=0); breakdown → dead-loss** |
| Baselines | Often missing | Standard | **BL-1..BL-5**, with BL-3 (odds-inverse) correctly scoped as market-reference |
| EV / recommendation | Win-bet or none | Kelly / edge-based | **EV_lower/EV_upper vs fixed odds**, rule-based S/A/B/C/D rank (no immature confidence) |
| UI | Often notebook-only | N/A | **Streamlit minimal UI** with full reproducibility metadata exposed |
| Reproducibility | "I ran a notebook" | Sometimes versioned | **Version-stamped Parquet + every artifact carries model/feature/label/odds/backtest versions** |

**Strategic takeaway:** This system's edge is not a fancier model. It is *discipline*: correct labels, leakage-free as-of, fixed-odds-snapshot backtest, honest refund accounting, calibrated probabilities, and reproducibility stamps. The literature shows these are exactly where typical racing-ML projects fail. Lean into them as the differentiator story, not into "we use LightGBM too".

---

## Sources

- Requirements (authoritative): `docs/keiba_ai_requirements_v1.3.md` — sections 1.1, 2.1, 2.2, 3.1–3.3, 7.3, 8.1–8.4, 9.2–9.3, 10.1–10.6, 11.1–11.6, 12.3, 13.1–13.5, 14.1–14.5, 15.1–15.5, 16.1–16.2, 17.1–17.3, 18.1–18.3, 19.1–19.3, 21. **Confidence: HIGH** (project's own authoritative source).
- Project context: `.planning/PROJECT.md` — Core Value, Active/Out-of-Scope, Key Decisions. **Confidence: HIGH**.
- Research — racing ML methodology (calibration, leakage, time-series backtest under-discussed): [Beating the Odds: ML for Horse Racing (r/MachineLearning)](https://www.reddit.com/r/MachineLearning/comments/e508p7/project_beating_the_odds_machine_learning_for/), [gmalbert/horse-racing-predictions (GitHub)](https://github.com/gmalbert/horse-racing-predictions), [Horse Racing Prediction: A ML Approach Part 2 (CodeWorks)](https://www.codeworks.fr/articles/use-case-3-horse-racing-prediction-a-machine-learning-approach-part-2), [Time Series of Odds in Race (DS StackExchange)](https://datascience.stackexchange.com/questions/40461/timeseries-of-odds-in-race-how-to-pick-a-model). **Confidence: MEDIUM** — hobbyist-dominated; calibration/leakage gaps are themselves the signal.
- Research — pari-mutuel market efficiency & place/show bias (supports fukusho focus + ability/EV separation): [Efficiency in Pari-Mutuel Betting Markets (JSTOR)](https://www.jstor.org/stable/20111861), [The Favorite-Longshot Midas (Wharton/Berkeley)](https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2018/08/The-Favorite-Longshot-Midas.pdf), [Anomalies: Parimutuel Betting Markets (Thaler, JEP/AEA)](https://pubs.aeaweb.org/doi/pdf/10.1257%2Fjep.2.2.161), [Explaining the FLB (NBER)](https://www.nber.org/system/files/working_papers/w15923/w15923.pdf). **Confidence: HIGH** — established academic consensus that place/show pools are LESS efficient than win pools (directly validates fukusho focus).
- Research — EV/Kelly/backtest pitfalls (supports anti-features around hindsight odds and over-claiming edge): [Reasons to Ignore the Kelly Criterion (Analytics.Bet)](https://analytics.bet/articles/reasons-to-ignore-the-kelly-criterion/), [Applying Kelly Criterion: 18-month backtest (r/quant)](https://www.reddit.com/r/quant/comments/1o2wzfh/applying_kelly_criterion_to_sports_betting_18/), [Why fractional Kelly? Simulations (Downey)](https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html), [Kelly Betting as Bayesian Model Evaluation (arXiv)](https://arxiv.org/html/2602.09982v1). **Confidence: MEDIUM-HIGH** — consistent warnings about estimated-vs-actual edge and backtest overstatement.
- Research — Streamlit + CSV export + backtest dashboard patterns (validates minimal-UI approach): [gmalbert/horse-racing-predictions (GitHub)](https://github.com/gmalbert/horse-racing-predictions), [Horse Racing Predictor (Streamlit app)](https://klkp5xtyxp5xzc3bq9uemd.streamlit.app/), [ethan-eplee/HorseRacePrediction (GitHub)](https://github.com/ethan-eplee/HorseRacePrediction), [We Built an AI Horse Racing Model — retrospective (StableBet)](https://stablebet.co.uk/betting/strategies/ai-prediction-models/). **Confidence: MEDIUM** — establishes that minimal Streamlit + CSV is the standard pattern; no project combines all of this system's discipline.

---
*Feature research for: JRA fukusho place-bet prediction + EV + virtual-purchase backtest (Phase 1)*
*Researched: 2026-06-16*
