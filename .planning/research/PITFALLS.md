# Pitfalls Research

**Domain:** JRA horse-racing prediction ML — 複勝 (fukusho / place-bet) payout-eligibility probability estimation + expected-value evaluation
**Researched:** 2026-06-16
**Confidence:** HIGH for JRA-rule pitfalls (anchored to `docs/keiba_ai_requirements_v1.3.md` sections 10/11/13 and official JRA/JRA-VAN sources); MEDIUM for the JRA 2019 class-reform code detail (corroborated by JRA-VAN developer forum + data-change notice); LOW for generic ML-leakage/calibration/CV claims (single web source, not cross-verified — these are well-established practitioner consensus but should be treated as starting hypotheses)

> **How to read this file.** Pitfalls are ordered by **blast radius** (leakage first — it silently invalidates every downstream number), then by likelihood. Each pitfall maps to a Phase 1 sub-area: **data quality → ETL → label generation → feature/as-of → model → EV → backtest → UI/CSV**. The "Warning signs" are deliberately concrete so they double as test cases. Where a pitfall extends requirements-doc §20, it is marked `[extends §20: <row>]`.

---

## Critical Pitfalls

These cause **silent** failure: the pipeline runs, numbers come out, ROI looks great — and every number is wrong. They are the highest-priority work in Phase 1 because they cannot be detected by "does it run" testing, only by adversarial audit.

---

### Pitfall 1: Future-information (lookahead) leakage in past-performance aggregates

**What goes wrong:**
A feature that looks historical actually includes information that would not have been available at the Phase 1-A prediction time (entry/post-position confirmed). The model learns to exploit it, validation looks fantastic, and live/backtest performance collapses — or, worse, the backtest *also* leaks so the collapse is invisible and you ship a worthless model believing it works.

**Why it happens (the JRA-specific vectors — this is where it bites):**
- **"当日ここまで" aggregates.** Rider/trainer/course/track-condition stats computed "up to and including today's earlier races" sneak same-day future-of-the-target-race info into the feature. Requirements §13.4 explicitly bans this; it is the single easiest leak to introduce by accident because "today's stats" feels natural.
- **Past-performance windows with no upper time bound.** "Last 5 starts" computed by row-count or date-count rather than `finish_datetime < feature_cutoff_datetime`. For a horse whose 5th-most-recent start was *earlier today* (a same-day double-entry, rare but real), that start is in the feature but its result is contemporaneous/future relative to the target race's decision point.
- **Rolling aggregates recomputed at dataset-build time using the full history.** Building "jockey strike rate" by grouping the *entire* table then joining — the row for target race R sees jockey results from races after R.
- **Field-strength / class-strength features.** Any feature that summarizes "the quality of horses in this race" (average earnings, average rating) uses data only fully known at final entry, which is fine for Phase 1-A — but a "net rating after today's result" variant is a leak.
- **Post-race-only columns silently present.** 通過順 (passing positions), 上がり (final 3f time), 走破タイム (race time), 確定着順 (final finish order), 確定払戻 (final payouts). Requirements §9.3 bans all of these. They are in the raw table next to the safe columns and a `SELECT *` pulls them in.

**How to avoid (concrete, layered):**
1. **Make `feature_cutoff_datetime` a hard filter, not a column.** Every past-performance query ends with `AND race_finish_datetime < :feature_cutoff`. The cutoff is set per-row to the Phase 1-A decision time (post-position confirmed). Make it impossible to query past-performance without the cutoff (wrap in a single feature-builder function).
2. **Build a `feature_availability` registry** (requirements §13.3) as a first-class artifact: `{feature_name, source_table, available_from_timing, cutoff_rule, leakage_risk_level}`. **Write a unit test that asserts no feature with `available_from_timing in {race_day_morning, body_weight_announced, odds_snapshot_available, post_race_only}` is selected for the Phase 1-A feature matrix.** This test should fail-loud if anyone adds a banned feature.
3. **Past-performance windows are time-bounded, not count-bounded.** "Starts with `finish < cutoff`, take last N" — never "last N starts" by row number.
4. **Never `SELECT *` from raw result tables into features.** Explicit column allowlists, generated from the `feature_availability` registry.
5. **Same-day isolation.** For every target race, exclude *all* races on the same `race_date` from past-performance/aggregates — even ones with an earlier post time. Requirements §15.4 forbids "同一開催日の未来レース情報利用"; the safe enforcement is to ban the entire day's data from the target's features (Phase 1-A does not use any same-day info anyway, per §13.4/§9.3).

**Warning signs (detect early):**
- Validation LogLoss/Brier suspiciously lower than the BL-4 logistic / BL-5 minimal-LightGBM baselines by a margin that feels too good (requirements §14.2). A model that "crushes" the baseline on first try usually has a leak — beats are normally incremental.
- A single feature dominates gain-split importance and it is an aggregate (jockey/course strike rate) — check its cutoff.
- Per-horse past-start count in the feature matrix is > 0 for a horse whose only starts are on/after the target `race_date`.
- Training AUC on a *randomly shuffled* (non-temporal) split is much higher than on a temporal split. The gap is the leak.

**Phase to address:**
**Feature/as-of** (primary — build the registry + cutoff enforcement + the fail-loud feature-allowlist test here). Verified again in **backtest** (temporal-split numbers must agree with held-out evaluation). `[extends §20: 未来情報リーク]`

---

### Pitfall 2: Hindsight odds-snapshot selection (cherry-picking the profitable snapshot)

**What goes wrong:**
After running the backtest, the implementer notices "発走30分前" yields 92% ROI and "発走10分前" yields 71%, and selects the 30-min policy. Or they re-run with "前日発売終了時点" because it "looks more stable." The reported ROI is an artifact of selection, not strategy. This is the most common way sports-betting backtests lie, and it is invisible in the code — the lie lives in the choice, not the data.

**Why it happens:**
- Optimizing `odds_snapshot_policy` on the test period's payout is *exactly* data snooping over a one-dimensional hyperparameter. With 7+ candidate snapshots (requirements §11.2 lists 7), the chance one looks great by luck is high.
- "The 30-min snapshot was missing for some races, so I substituted the 10-min for those" — post-hoc, race-specific, and the substituted races are disproportionately the ones where it mattered.
- Final odds (締切直前 / 最終オッズ) used as the decision odds. Final odds incorporate late money which is *correlated with the outcome* — this is the canonical lookahead.
- Reporting the best of several `odds_snapshot_policy` runs without correction for multiple comparisons.

**How to avoid:**
1. **Pre-register the candidate `odds_snapshot_policy` set and the selection rule before looking at test-period ROI.** Selection criterion must be defined on a *validation* period disjoint from the reported *test* period (nested temporal split), not on the test period itself.
2. **`odds_missing_policy = no_bet` for Phase 1** (requirements §11.3) — do not substitute. Missing odds ⇒ not bet. Substitution is the leak vector.
3. **Never use final/締切 odds as a decision input in Phase 1.** It is allowed only as a *post-hoc market baseline* (BL-3, §14.2), explicitly not a same-information comparison.
4. **Persist `odds_snapshot_policy` and `odds_snapshot_at` on every prediction and every backtest row** (requirements §11.2, §16.2). A backtest result without these is unverifiable.
5. **Treat `odds_snapshot_policy` as a versioned artifact**, not a knob. Changing it after seeing results = new `backtest_strategy_version`, old version preserved.
6. **Report all candidate policies, not the winner.** A table of {30-min, 10-min} × {BT-1..BT-5} (requirements §15.5) is the honest deliverable. Picking one and reporting it alone is the failure mode.

**Warning signs:**
- ROI varies wildly (>20pp) across candidate `odds_snapshot_policy` for the same model. Genuine EV edge should be moderately stable across nearby snapshots; huge swings suggest the edge is sample noise being mined.
- The chosen policy is one the implementer cannot actually execute (e.g., "発走5分前" when the pipeline runs hourly).
- Missing-odds handling was "tuned" — i.e., the policy changed during debugging.
- Backtest ROI >> what a no-skill BL-1/BL-2 baseline produces on the *same* policy. If the edge is real it should survive on the boring policy too.

**Phase to address:**
**EV** (define policy + missing-odds handling) and **backtest** (pre-registration, all-policies reporting, versioning). `[extends §20: 後知恵オッズ選択, オッズ時点不明]`

---

### Pitfall 3: 複勝 (fukusho) label-definition errors — wrong payout-places basis

**What goes wrong:**
The label `fukusho_hit` is built from the **final starter count** instead of the **sales-start entry count**. A race that opened for betting with 9 entries (→ 3 payout places) but had 2 scratchings running down to 7 final starters gets labeled as a 2-payout-places race. Horses that finished 3rd are mislabeled as `fukusho_hit = 0`. Or the reverse: a race that *opened* with 4 entries (no fukusho sold at all) but picked up late entries to 6 starters is labeled as a valid 2-payout race that should have been excluded entirely. Every model trained on it, every calibration curve, every ROI number is contaminated.

**Why it happens:**
- The raw table's headline count is usually the final/starting count — the sales-start count is a derived/historical field that has to be reconstructed (requirements §10.3). It is easier to reach for the count that's sitting in the row.
- JRA-VAN/EveryDB2 may not expose `sales_start_entry_count` as a direct column, requiring reconstruction from the entry list + scratch/排除 announcement timestamps (§10.3 path 2). Implementers skip this and fall back to `final_starter_count` (§10.4 priority 4 — lowest priority).
- Conflating "3着以内" (top-3 by finish) with "複勝払戻対象" (payout-eligible). For 5–7 horse fields only the **top 2** pay; a generic "top-3" label silently corrupts ~20% of small-field races.
- Ignoring that **fukusho is not sold at all** for fields of ≤4 — these races must be excluded (§7.3), not labeled with 0 payout places.

**How to avoid:**
1. **Implement the §10.4 priority chain strictly**, with `label_validation_status` tracking which path produced each label: `payout_table` > `sales_start_entry_count` > `着順` > `final_starter_count`. `final_starter_count`-only labels must be flagged `inferred` or `unresolved`, never silently promoted.
2. **`sales_start_entry_count` reconstruction (§10.3):** try direct column → reconstruct from entry list + scratch/除外 announcement timestamps → if unreconstructable, `label_validation_status = unresolved` and **exclude from Phase 1 train/eval** (§10.3 path 3, §10.4). Never default to `final_starter_count` to "fill the gap."
3. **`fukusho_payout_places` from sales-start count:** ≥8 → 3, 5–7 → 2, ≤4 → no sale (exclude). Requirements §10.2.
4. **Primary label is `fukusho_hit_validated` against the payout table** (§10.4, §10.5), not the finish-order-derived `fukusho_hit_raw`. The payout table is ground truth for who actually got paid.
5. **Reconciliation tests (§10.5, make these hard assertions):**
   - `fukusho_hit_validated = 1` ⇒ horse present in payout table.
   - Horse present in payout table ⇒ `fukusho_hit_validated = 1`.
   - Cancelled/除外 horse never `= 1`.
   - 競走中止 (DNF) horse **kept** in the dataset as `= 0` (see Pitfall 6) — verify it is not silently dropped.
   - No-fukusho-sale race (≤4 sales-start entries) is excluded, not labeled.
6. **Flag and segregate `inferred`/`unresolved`** labels; report the fraction. A high `unresolved` fraction means the reconstruction logic is broken, not that you should lower the bar.

**Warning signs:**
- Fraction of 2-payout-places labels is far below the empirical fraction of small-field races (roughly: ~10–15% of JRA flat races are 5–7 horse fields). If you see ~0%, you are using final count and mislabeling small fields as 3-payout.
- Any `fukusho_hit = 1` for a horse that finished worse than the payout-places rank in its (correct) field size.
- Calibration curve looks *too good* because small-field noise was removed by mislabeling.
- High `unresolved` rate (> a few %) — investigate before proceeding.

**Phase to address:**
**Label generation** (the entire §10 spec lives here). This is the foundation — nothing downstream is trustworthy until labels are correct. Gate the phase: do not start model training until reconciliation tests pass at >99.9% agreement (payout-table vs derived label) on a sample. `[extends §20: 複勝ラベル誤定義, 最終出走頭数だけでラベル生成]`

---

### Pitfall 4: Target-encoding / categorical-encoding label leakage

**What goes wrong:**
Categorical features (jockey, trainer, sire, dam-sire, course, class) are encoded using the target. The encoding for the validation/test row is computed from a statistic that includes that row's own label (or labels near in time), so the feature "knows" the answer. Validation scores are inflated; the model appears to learn jockey/trainer skill that is actually leakage. Deployed/backtest performance is materially worse.

**Why it happens (LightGBM vs CatBoost differ — this matters):**
- **LightGBM native categorical handling (`categorical_feature` / `category` dtype) does NOT do target encoding** — it uses a much simpler histogram-based split on integer codes. The leak enters only if you *additionally* pre-encode categoricals with target means (e.g., `category_encoders.TargetEncoder`). Doing that encoder fit on the full dataset (train+val+test) before splitting is the classic blunder.
- **CatBoost does its own Ordered Target Statistics** (NeurIPS 2018): a random permutation; each row's category is encoded using only rows before it in the permutation; plus Ordered Boosting (residuals from models that never saw that row). This is *designed* to prevent the leak — but it assumes you pass `cat_features` correctly and let CatBoost own the encoding. If you pre-target-encode and *then* hand CatBoost the encoded numeric column, you have removed CatBoost's protection and re-introduced the leak.
- **Same-permutation problem:** even "out-of-fold" target encoding leaks if the encoding fold and the model's CV fold do not align — a row's label can still influence a near neighbor's encoding.
- **Negative-value category codes (§14.3)** in LightGBM are interpreted as missing — silently dropping a real category.
- **Horse/jockey IDs with tiny sample sizes** get noisy target means; without smoothing the encoding is essentially a copy of the label for rare categories (a one-start horse's jockey "mean" = that horse's result).

**How to avoid:**
1. **Requirements §14.3/§14.4 already forbid validation-data target encoding.** Enforce it: do not pre-target-encode categoricals. Let LightGBM use native `categorical_feature` (integer/category codes, no negatives per §14.3) and let CatBoost use `cat_features` with its native Ordered TS.
2. **If target encoding is ever added later, it must be K-fold out-of-fold** with fold alignment matching the model's CV, plus smoothing (Bayesian prior) for low-count categories, and the encoder fit on the *training fold only*, transformed onto val/test.
3. **Never pre-encode then pass numeric columns to CatBoost** — this defeats Ordered TS. Pass raw categorical columns and declare `cat_features`.
4. **Category codes: non-negative integers, missing = NaN (not -1).** LightGBM treats -1 as missing; CatBoost handles missing natively. (§14.3)
5. **Distinguish missing reasons (§14.5):** unposted, not-applicable, data-gap, first-start, aggregation-insufficient, unavailable-at-prediction-time. A single NULL bucket conflates "first-start horse" (signal) with "data bug" (noise).
6. **Leak diagnostic test:** train on full data, score the *training* set, and compute per-category mean of `p_fukusho_hit` vs the category's actual target mean. A near-perfect correlation for rare categories = leakage. After a correct CatBoost/LightGBM-native setup, rare categories should regress toward the global mean, not match their own label.

**Warning signs:**
- Rare jockey/trainer categories get extreme probability predictions (near 0 or 1). With correct handling they should be shrunk toward the mean.
- Big gap between validation LogLoss and temporal-test LogLoss — much bigger than the train/val gap would predict. The excess is leakage.
- Adding the categorical feature moves the metric *more* than a domain expert would expect (jockey matters, but if it's the single biggest mover on a cold start, suspect leak).
- Train-set predictions perfectly separate categories — the model has memorized the label via the encoding.

**Phase to address:**
**Model** (encoding strategy + the leak diagnostic). Decide LightGBM-native vs CatBoost-native encoding here; write the diagnostic into the evaluation suite. `[extends §20: カテゴリ処理ミス]`

---

### Pitfall 5: Time-series validation mistakes — same `race_id` and same-day info crossing train/test

**What goes wrong:**
The backtest split is not actually temporal at the race level. Either the same `race_id` appears in both train and test (the model has seen the answer's neighborhood), or rows from the same race-day leak future-of-the-target-race information across the split. Reported metrics are optimistic; the real generalization gap is hidden. This compounds with Pitfalls 1 and 4.

**Why it happens (the three distinct mistakes):**
1. **Random / K-Fold split.** `train_test_split` or `KFold` shuffles rows. Horses from the same race land in both folds; the model learns race-level invariants (track condition, field strength) from the test race's other entrants. Catastrophic.
2. **`TimeSeriesSplit` at row level without grouping.** scikit-learn's `TimeSeriesSplit` preserves order *but a single date (group) can appear in both train and test* (Kaggle TS-10; StackOverflow 51963713). For panel data like racing — many rows per race-day — this leaks same-day info across the boundary even though order is "respected."
3. **`GroupKFold` on `race_id` without temporal order.** Keeps races separate (good) but shuffles across time (bad) — trains on 2024 to test 2022, which is unrealistic and can still leak via slowly-drifting features (jockey form computed using future races).
4. **Group leakage at the day level.** Splitting by `race_id` but allowing train to include *later races on the same day* as a target test race. Phase 1-A uses no same-day info (§13.4), so this is currently a non-issue — but the temptation grows in Phase 2 when morning track condition becomes available.

**How to avoid:**
1. **Split unit is `race_id`; ordering is `race_start_datetime` ascending (requirements §15.4).** Implement as a custom splitter: sort distinct `race_id`s by their `race_start_datetime`, then split the *race list* (not the row list). Both `TimeSeriesSplit` semantics (rolling/expanding) and fixed holdout operate on this race list.
2. **Equivalent to mlxtend `GroupTimeSeriesSplit` with group = `race_id`, time = `race_start_datetime`.** Either adopt mlxtend's implementation or write a `BaseCrossValidator` that: (a) takes unique races ordered by start time, (b) yields train races / test races with no overlap and strictly later test races.
3. **Hard assertion in the splitter:** `assert set(train_race_ids).isdisjoint(set(test_race_ids))` for every fold. Add a test that verifies this on a small fixture.
4. **Purge any feature built from a race whose `race_start_datetime >= min(test_race_start_datetime)`** from the test rows' past-performance. This is the cutoff filter from Pitfall 1, applied at split time as defense-in-depth.
5. **Requirements §15.5 candidates (BT-1..BT-5)** all use temporal splits with train-before-test. Keep the rolling/expanding window logic in one place; do not let each backtest reimplement it.
6. **Phase 2 prep:** when morning track condition becomes a feature, also enforce *same-day* isolation at the splitter (train cannot see any race on the test race's date). Build the hook now even if unused.

**Warning signs:**
- The same `race_id` shows up in a `train` Parquet and a `test` Parquet for the same fold. (Write the assertion; this should be impossible to merge.)
- Temporal-split metrics are dramatically worse than random-split metrics — that gap is the leakage the random split was hiding. Investigate before "fixing" the temporal split.
- A model trained on 2019–2022 and tested on 2023 shows suspiciously low error in early 2023 that degrades through the year — could indicate a feature that drifts and was tuned on near-2023 data.
- Per-year stability (requirements §15.1) is non-monotonic in weird ways — a sign the split boundary is leaking.

**Phase to address:**
**Backtest** (the splitter is a backtest artifact). But the *defense* (cutoff filter) is in **feature/as-of** — they must agree on the cutoff semantics. Write the splitter and the disjoint-race assertion here; do not begin BT-1 until it passes. `[extends §20: 同一レースのtrain/testまたぎ]`

---

### Pitfall 6: Excluding 競走中止 (DNF / did-not-finish) runners, inflating ROI

**What goes wrong:**
DNF horses (競走中止 — fell, pulled up, eased, ran off course) are dropped from the backtest because "they didn't finish, so the bet is ambiguous." This removes a class of real-money losses from the track record. Backtest ROI rises; the edge is fictional. Requirements §10.6 and §11.6 are explicit: DNF = loss (not refunded), must stay in.

**Why it happens:**
- DNF status lives in a result column that's easy to filter on (`WHERE finish_rank IS NOT NULL` drops them). The WHERE clause is the leak.
- "Refund" is conflated with "loss." 出走取消/競走除外 (scratched before the start) *are* refunded (§10.6); 競走中止 (DNF after the start) is *not* refunded and *is* a loss. The three outcomes are distinct in JRA rules but look similar in code.
- Implementers reason "the horse didn't really lose, it didn't finish" and exclude — a well-intentioned but wrong heuristic.

**How to avoid:**
1. **DNF is `fukusho_hit = 0`, kept in train and test (§10.6).** No filter on finish status beyond excluding cancelled/除外 (which are prediction-target-excluded entirely, §10.6).
2. **Three-way runner outcome taxonomy in the label/backtest tables:**
   - `started_and_finished` → label by finish vs payout places.
   - `started_and_dnf` (競走中止) → `fukusho_hit = 0`, included everywhere, bet = loss if selected.
   - `scratched_or_excluded` (取消/除外) → excluded from prediction targets; if a bet was virtually placed before the scratch, it is refunded (`effective_stake = 0`, §11.6).
3. **Reconciliation test (§10.5):** 競走中止 horse is **not** dropped from the label table; assert the count of DNF rows in labels == count in raw results.
4. **Backtest `effective_stake` rule (§11.6):** refunded bets have `effective_stake = 0` (so they don't distort 回収率 = payout / effective_stake); DNF bets have `effective_stake = 100`, `profit = -100`. Test both paths.
5. **ROI cross-check:** compute ROI two ways — (a) including all selected bets with DNF as losses, (b) excluding DNF. If (b) >> (a), the published number must be (a). Log both for transparency.

**Warning signs:**
- Backtest `selected_count` ≈ `effective_bet_count` (i.e., almost no refunds and no DNF losses). Real racing has both; near-zero means filtering.
- The number of DNF horses in the backtest results table is much smaller than in the raw results for the same period.
- ROI looks "too clean" — JRA place-bet ROI for a real edge is usually low single digits to ~10%, not 50%+.
- A horse known to have broken down / been pulled up in a famous race is missing from its backtest row.

**Phase to address:**
**Label generation** (DNF taxonomy) and **backtest** (effective_stake / refund logic). Write the DNF-not-dropped assertion in label tests; write the refund-vs-loss path in backtest tests. `[extends §20: 競走中止の除外]`

---

### Pitfall 7: Class-system change mishandling (JRA 2019 summer reform)

**What goes wrong:**
Class is normalized by string-matching the race-condition name. Before 2019-06, "500万下"; after, "1勝クラス". String matching produces two separate classes for what is structurally the same class, splitting a continuous population and either (a) creating spurious "class" features that encode the date, or (b) under-training each half. Conversely, treating them as identical without the reform flag hides a real competitive-balance shift (the abolition of 4yo demotion materially changed field strength in 1勝–3勝クラス).

**Why it happens (the trap is subtle):**
- The **race-condition code did NOT change** in the 2019 reform. JRA-VAN/EveryDB2 code `005` maps to *both* "500万以下" and "1勝クラス" (the spec was deliberately left unchanged to preserve historical cumulative data; JRA-VAN developer forum topic 305; data-change notice 2018-12-05). So a code-based normalization *correctly* groups them — but then the implementer, seeing the code is the same, may conclude "no reform happened" and omit the reform flag entirely.
- Conversely, a name-based normalization sees two strings and splits them — the more common blunder.
- The demotion abolition (降級制度廃止) changed the *strength distribution* of these classes over time even though the code is constant. A feature that says "class = 1勝クラス, year = 2020" carries different information than "class = 500万下, year = 2018" — the model needs the reform flag to know.

**How to avoid:**
1. **Normalize by `race_condition_code` (requirements §12.3), not by name string.** This correctly groups 500万下/1勝クラス under one `class_code_normalized`.
2. **Add `post_2019_class_system_flag` and `class_level_numeric` (§12.3).** The flag is the feature that lets the model learn the reform's effect; without it, post-2019 1勝クラス is silently treated as identical-strength to pre-2019 500万下.
3. **Backfill the flag from `race_date >= 2019 summer meet`**, not from a name heuristic. The summer-meet start date is the official cutover.
4. **Stratify evaluation by the flag** (add to the §15.1 stability axes: pre-2019 vs post-2019). If the model's calibration differs materially across the flag, the reform is a real distribution shift to track.
5. **Primary train period candidates (§6.3) include "2019年夏季競馬以降" and "2016年後半以降全期間"** — the former sidesteps the reform entirely (recommended for the first model); the latter requires the flag. Make the choice deliberate.

**Warning signs:**
- `class_name_normalized` has separate buckets for "500万下" and "1勝クラス" — you normalized by name.
- Calibration shifts discontinuously at the 2019 summer boundary for 1勝–3勝クラス but not forオープン/未勝利.
- Training on pre-2019 only and testing on post-2019 gives much worse metrics than same-era splits — the reform is a distribution break the model can't bridge without the flag.
- The number of distinct class codes is small (~6) but distinct class *names* is large (~12) — a sign the code is the right key.

**Phase to address:**
**ETL** (class normalization, §12.3) — this is a one-time transformation in the normalized layer. Add the reform flag and the per-flag evaluation axis in **evaluation**. `[extends §20: クラス制度変更]`

---

### Pitfall 8: Probability calibration mistakes breaking EV judgments

**What goes wrong:**
`p_fukusho_hit` is not calibrated — a horse with predicted 0.30 actually hits 0.22 (over-confident) or 0.38 (under-confident) of the time. EV = p × odds is then systematically wrong. Over-confidence ⇒ over-betting on longshots ⇒ real-money-style losses. Under-confidence ⇒ missing edges. The model's ranking may be fine while its EV is broken, so "good AUC" does not rescue this.

**Why it happens (GBM-specific):**
- **GBMs (LightGBM, CatBoost, XGBoost) produce distorted, often over-confident probabilities** that need post-hoc calibration (Niculescu-Mizil & Caruana ICML 2005; practitioner consensus). Raw LightGBM `predict_proba` is *not* calibrated by default.
- **Wrong calibration method for the distortion shape.** Platt (sigmoid) assumes sigmoid distortion; for GBMs the distortion is often irregular/high-variance and Platt is a poor fit (DSSE reports calibration worsening the model when naively applied). Isotonic handles irregular distortion but overfits with limited data.
- **Calibration fit on data that leaks** (same fold as training) — the calibrator memorizes.
- **Calibration drift over time.** A calibrator fit on 2019–2022 and applied to 2024 may have drifted (jockey population changes, rule changes). The §15.1 per-year calibration axis is exactly the diagnostic.
- **`sum(p)` drift (§15.2).** Per-race probability sum drifting from the theoretical payout-places (2.7–3.3 for ≥8-horse fields) means the model is collectively over- or under-confident in a race — even if individual calibration looks ok.
- **EV uses un-calibrated `p`.** The EV pipeline reads the raw model output, not the calibrated one.

**How to avoid:**
1. **Always calibrate** `p_fukusho_hit` before EV. Compare Platt (sigmoid) vs isotonic on a reliability diagram (§15.3) and pick the one that monotonizes the curve without overfitting.
2. **Fit the calibrator on a held-out temporal split** disjoint from both training and the reported test period — nested temporal splits. Never fit the calibrator on the same fold the model trained on.
3. **Use enough data for isotonic** — it's flexible and overfits on small sets. For low-volume categories (rare courses), prefer Platt or pooled data.
4. **Make `sum(p)` a first-class acceptance criterion (§15.2).** Per ≥8-horse race, mean `sum(p_fukusho_hit)` should be ~2.7–3.3; for 5–7 horse fields ~1.8–2.2. Inspect median, std, p10, p90 — not just mean. Large spread or out-of-range ⇒ investigate by field-size/course/distance/class before trusting EV.
5. **Per-axis calibration (§15.3):** overall, by popularity band, odds band, course, field size, year. EV-eligible bets typically come from specific bands; miscalibration in *those bands* breaks EV even if overall calibration is fine.
6. **Recalibrate when retraining** and track calibration drift across model versions — a stability metric.
7. **EV reads the calibrated `p`.** Wire this explicitly; document which `p` (raw vs calibrated) EV uses in the prediction table.

**Warning signs:**
- Reliability curve is sigmoid-shaped but you applied Platt — and it got worse. Try isotonic.
- `sum(p)` mean is in range but p10/p90 are extreme (e.g., p10=2.1, p90=3.9 for ≥8 fields) — the model is unstable across races.
- Per-year calibration curves diverge sharply — drift; recalibrate or shorten training window.
- Backtest ROI is much more sensitive to the EV threshold than it should be — a sign `p` is mis-scaled (a 0.05 miscalibration flips many borderline EVs).
- The model has good ranking (AUC) but poor Brier — ranking-calibrated but not value-calibrated.

**Phase to address:**
**Model** (calibration method, held-out calibrator) and **EV** (use calibrated p) and **evaluation** (sum(p) + per-axis calibration as acceptance gates). `[extends §20: — new row, "確率校正ミス"]`

---

### Pitfall 9: Non-reproducibility — un-versioned features / labels / odds-snapshot / strategy

**What goes wrong:**
Six months later, a stakeholder asks "why did the June model recommend horse X?" and nobody can reproduce it. The features have been regenerated (underlying data patched), the label definition was silently tweaked, the odds snapshot policy changed, the strategy threshold moved. The "model" is a floating snapshot of many unsynchronized versions. Backtests cannot be re-run; results cannot be compared across time.

**Why it happens:**
- The pipeline mutates shared tables in place. `normalized` and `label` tables get overwritten on each ETL run. There is no `feature_snapshot_id` pointing at a frozen Parquet.
- `label_generation_version`, `odds_snapshot_policy`, `backtest_strategy_version`, `model_version`, `feature_snapshot_id` (requirements §11.4, §12.4, §13.2, §19.1) are *documented* but not *enforced* — they're missing from rows, so joins are ambiguous.
- Ad-hoc notebooks recompute features with subtly different SQL (a `WHERE` changed) and the "same" feature has two definitions in the wild.
- Random seeds not fixed; LightGBM/CatBoost nondeterminism on multithreaded training.

**How to avoid:**
1. **Persist the five version keys on every prediction, every backtest row, every Parquet (§19.1):** `model_version`, `feature_snapshot_id`, `label_version` (`label_generation_version`), `odds_snapshot_policy`, `backtest_strategy_version`. Plus `as_of_datetime`, `feature_cutoff_datetime`, `odds_snapshot_at` (§13.2, §11.2).
2. **Feature snapshots are immutable Parquet** (§12.4) with the metadata block (dataset_version, feature_snapshot_id, label_version, prediction_timing, feature_cutoff_datetime, train_period, validation_period, created_at). To retrain, point at a snapshot ID, never at a live table.
3. **Label generation is itself versioned** (`label_generation_version`, §10.3) — the reconstruction logic for `sales_start_entry_count` changes the label set; bump the version when it does.
4. **Raw EveryDB2 tables are never mutated in place** (§19.2). Normalized/label/prediction layers are additive or snapshot-based.
5. **Fix random seeds** for LightGBM (`seed`, `feature_fraction_seed`, `bagging_seed`, `drop_seed`) and CatBoost (`random_seed`, plus `thread_count=-1` is *not* deterministic on some platforms — use fixed `thread_count`). Document the seed in `model_version`.
6. **A "reproduce" smoke test:** given a `feature_snapshot_id` + `model_version` + `label_version`, the pipeline produces predictions bit-identical to the stored ones (within float tolerance). Run on CI for one small race.

**Warning signs:**
- Retraining "the same model" on "the same data" gives different metrics — versioning is broken or seeds are unset.
- A prediction row has null `feature_snapshot_id` or `odds_snapshot_policy`.
- The `label` table's row count changes between two unsnapshotted runs with no code change — someone mutated it.
- Two analysts get different "ROI for 2023" from "the same" backtest — they are pointing at different versions.
- Notebooks proliferate with copy-pasted SQL; no canonical feature definition.

**Phase to address:**
Cross-cutting, but the **contracts are established in data quality / ETL / label / feature** (versioning scheme + snapshot table) and **enforced in model + backtest** (write the keys, run the reproduce test). `[extends §20: 仮想購入ルール未定義 (strategy versioning portion), オッズ時点不明]`

---

### Pitfall 10: `sum(p)` distribution sanity neglect

**What goes wrong:**
The model's per-race probability sums are checked only by mean, and the mean is in range — but the *distribution* is broken (a long tail of races where `sum(p)` is 1.5 or 4.5). EV thresholds then fire on races where the model is collectively confused, and the backtest silently includes these broken-race bets. Mean-in-range hides the tail.

**Why it happens:**
- Mean of `sum(p)` is the only reported metric. Requirements §4 (v1.3) and §15.2 already call for median, std, p10, p90 — but it's easy to skip.
- A model with good per-horse ranking but bad per-race normalization can pass Brier/LogLoss while having wild `sum(p)`.
- Small-field races (5–7 horses, 2 payout places) are pooled with large fields in the metric, washing out the signal.
- Post-calibration `sum(p)` is never re-checked — the calibrator fixes marginal calibration but can distort race-level sums.

**How to avoid:**
1. **Report mean, median, std, p10, p90 of `sum(p)` by field-size bucket (≥8 and 5–7 separately)** as a hard gate (§15.2).
2. **Outlier-race triage:** for races with `sum(p)` outside [2.5, 3.5] (≥8) or [1.6, 2.4] (5–7), group by course / distance / class / field-size and find the offending slice.
3. **Cross-check `sum(p)` against the theoretical payout-places** — if `E[sum(p)]` ≫ 3 for ≥8 fields, the model is over-confident collectively; if ≪ 2.7, under-confident.
4. **Re-check `sum(p)` *after* calibration** — Platt/isotonic can move it. Apply a per-race renormalization only if explicitly justified and versioned.

**Warning signs:**
- Mean `sum(p)` in range but std > 0.5 for ≥8 fields.
- A specific course/class consistently produces out-of-range `sum(p)`.
- Many of the EV-eligible bets come from out-of-range-`sum(p)` races — the model is most "confident" exactly where it is least reliable.

**Phase to address:**
**Evaluation** (the acceptance gate). Make `sum(p)` distribution a CI-checked artifact alongside Brier/LogLoss/calibration. `[extends §20: — new row, "sum(p) 分布チェックの軽視"]`

---

## Technical Debt Patterns

Shortcuts that seem reasonable in a one-developer research codebase but create long-term reproducibility problems. For this project, most are **never acceptable** because reproducibility is the Core Value (PROJECT.md).

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Mutate `normalized`/`label` tables in place on each ETL | Faster iteration, less storage | Cannot reproduce any past result; `label_version` becomes meaningless | **Never** for this project — use additive snapshots |
| `SELECT *` from raw result tables into features | Quick to write | Pulls post-race columns (通過順/上がり/確定着順) → Pitfall 1 leak | **Never** — explicit allowlists from `feature_availability` |
| Random train/test split "just to try the model" | Faster first model | Leaks race-level info, produces wildly optimistic numbers | **Never** — even for sanity checks, use temporal split |
| Final odds as decision odds | "It's the most accurate market signal" | Classic lookahead; inflates ROI | **Never** in Phase 1 — only as BL-3 baseline reference |
| Hardcoding `odds_snapshot_policy` deep in EV code | Less plumbing | Cannot version/compare policies | **Never** — pass as explicit, persisted parameter |
| `final_starter_count` to fill missing `sales_start_entry_count` | Avoids `unresolved` rows | Mislabels scratch-affected races (Pitfall 3) | **Never** — mark `unresolved`, exclude |
| LightGBM/CatBoost without fixed seeds | Faster multithreaded training | Non-reproducible; can't run the "reproduce" smoke test | **Never** — fix all seeds, cap threads if needed |
| Computing jockey/trainer stats on the full table then joining | One query, "good enough" | Target/lookahead leakage (Pitfalls 1, 4) | **Never** — time-bound by `feature_cutoff_datetime` |
| Skipping target-encoding CV (just mean-encode globally) | Simpler pipeline | Validation leak (Pitfall 4) | **Never** — or avoid target encoding entirely (use native categorical) |
| Storing predictions without `feature_snapshot_id` | Less schema | Untraceable predictions (Pitfall 9) | **Never** — non-null constraint |
| One-off notebook feature definitions | Exploratory speed | Multiple "definitions" of the same feature coexist | Exploratory only; promote to versioned feature module before training |

## Integration Gotchas

Connecting to EveryDB2 / JRA-VAN / PostgreSQL / DuckDB / Parquet.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| EveryDB2 → Mac PostgreSQL | Assuming EveryDB2 data is clean — codes, NULLs, duplicates unverified | Run §6.4 quality checks first; gate Phase 1 on them |
| JRA-VAN race-condition code | Treating 005 as either "only 500万下" or "only 1勝クラス" by name | Code 005 spans both eras — normalize by code, add `post_2019_class_system_flag` (Pitfall 7) |
| JRA-VAN field counts | Using final starter count as the headline count | Reconstruct `sales_start_entry_count`; final count is §10.4 priority 4 (Pitfall 3) |
| JRA-VAN payout table | Ignoring it, deriving labels from finish order only | Payout table is ground truth (§10.4 priority 1); reconcile (§10.5) |
| JRA-VAN DNF flag | Filtering `WHERE finish_rank IS NOT NULL` | Drops DNF (競走中止) — keep them as `fukusho_hit = 0` (Pitfall 6) |
| JRA-VAN odds snapshots | Substituting a different snapshot when the policy one is missing | `odds_missing_policy = no_bet`; never substitute (Pitfall 2, §11.3) |
| JRA-VAN same-day info | "It's earlier in the day so it's fine" | Phase 1-A uses no same-day info at all (§13.4); exclude the entire `race_date` from features |
| LightGBM categorical | Passing target-encoded numerics; -1 codes | Native `categorical_feature`, non-negative codes, NaN for missing (Pitfall 4) |
| CatBoost categorical | Pre-encoding then passing numerics (defeats Ordered TS) | Raw categoricals + `cat_features`, let CatBoost own encoding (Pitfall 4) |
| DuckDB | Using it as the primary store | PostgreSQL is primary (§5.2); DuckDB is read-only analysis over Parquet |
| Parquet snapshots | Regenerating without bumping `feature_snapshot_id` | Snapshot ID is the join key; every regen = new ID + metadata block (§12.4) |
| scikit-learn `TimeSeriesSplit` | Using it directly on panel rows | Same group can appear in train and test (Pitfall 5); use `GroupTimeSeriesSplit` semantics on `race_id` |

## Performance Traps

This is a single-user local research pipeline, not a high-QPS service — most "scalability" traps are irrelevant. The relevant ones are about *data volume over the 2015–present full JRA history*.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-row Python feature computation (loops over horses) | Feature build takes hours/days; cannot iterate | Vectorized SQL (PostgreSQL/DuckDB over Parquet) for aggregates; per-row only for non-decomposable calcs | > 1 full season of features |
| Recomputing all past-performance features per target race | O(races × horses × history) blow-up | Incremental/rolling aggregates keyed by `(horse_id, cutoff)`; cache intermediate tables | Any backtest spanning years |
| Loading full Parquet into memory for each fold | OOM or thrashing on M2 Pro | Per-fold Parquet partitions by `race_date`; stream with DuckDB | Full 2015–present history in one DataFrame |
| Unindexed PostgreSQL joins on `race_id` / `horse_id` | Queries take minutes | Index foreign keys before ETL; EXPLAIN before assuming "slow DB" | Any join across the full history |
| Isotonic calibration on a tiny slice | Calibrator overfits; wild probabilities | Use Platt or pool data when calibrator-fit slice is small (Pitfall 8) | Rare-course / rare-class calibration |
| Many `odds_snapshot_policy` × many BT configs run naively | Backtest grid takes a weekend | Materialize per-(model, snapshot) prediction once; reuse across strategies | > 2 policies × > 3 BT configs |

## Security Mistakes

Domain-specific. This project is local-only, no real betting (§19.3), no PII — so "security" is narrow. The real risks are *integrity* risks to the research, covered above. Listing for completeness:

| Mistake | Risk | Prevention |
|---------|------|------------|
| Letting a "tuned" backtest result influence the published `odds_snapshot_policy` (Pitfall 2) | Published ROI is fictional | Pre-registration; report all policies; version on change |
| Treating `effective_stake` accounting loosely (Pitfall 6) | ROI inflated by silent DNF exclusion / refund miscount | Three-way runner taxonomy; tested refund vs loss paths |
| Shipping "the model recommends horse X" without `feature_snapshot_id` (Pitfall 9) | Unverifiable, unreproducible claims | Non-null version keys; reproduce smoke test |
| Confusing "参考情報" recommendation with actionable bet advice (§19.3) | Scope creep toward real betting, which is explicitly excluded | UI must label recommendations as reference only; no auto-voting hooks |
| Storing EveryDB2 credentials in notebooks | Credential leak on notebook share | Env vars / `.env` (gitignored); no hardcoded connection strings |

## UX Pitfalls

The Streamlit UI (§16.1) is for the single developer/researcher. Pitfalls are about *not misleading yourself*:

| Pitfall | User (developer) Impact | Better Approach |
|---------|-------------------------|-----------------|
| Showing `p_fukusho_hit` without `odds_snapshot_policy` / `as_of_datetime` | You forget which snapshot a number came from; compare apples to oranges | Always show the version keys inline with predictions (§16.1) |
| Showing ROI without `backtest_strategy_version` and split periods | "ROI is 90%" with no context → overconfidence | Surface strategy version, train/test periods, and policy alongside ROI |
| Showing raw uncalibrated `p` as if it were a calibrated probability | EV judgments on bad probabilities (Pitfall 8) | Label which `p` (raw vs calibrated) is shown; default to calibrated for EV |
| Recommendation rank shown without the EV/probability/odds inputs | Opque "S rank" → you trust a number you can't audit | Show EV_lower, p, odds_lower next to the rank (§11.5) |
| No "sum(p) for this race" indicator | You can't see when the model is collectively confused (Pitfall 10) | Show race-level `sum(p)` and flag out-of-range |
| Backtest charts without per-year/per-course breakdown | Aggregate hides drift and slice problems | Default to sliced views (§15.1, §15.3) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing the critical piece that makes them trustworthy. Use this as a Phase-1 acceptance gate.

- [ ] **Feature matrix:** Often missing the `feature_availability` allowlist test — verify no `post_race_only`/`odds_snapshot_available`/`body_weight_announced` feature is in the Phase 1-A matrix.
- [ ] **`fukusho_hit` label:** Often missing payout-table reconciliation — verify `fukusho_hit_validated = 1` ⇔ present in payout table, on a sample; verify DNF horses present; verify no-sale races excluded.
- [ ] **`sales_start_entry_count`:** Often silently defaulted to final count — verify `label_validation_status` has non-trivial `unresolved`/`inferred` counts OR a documented reconstruction; verify the `final_starter_count`-only path is never used silently.
- [ ] **Past-performance features:** Often missing the `feature_cutoff_datetime` hard filter — verify no target row sees a feature built from a race finishing after its cutoff; verify same-day exclusion.
- [ ] **Categorical encoding:** Often pre-target-encoded then handed to CatBoost — verify raw categoricals reach CatBoost `cat_features`; verify no negative LightGBM codes.
- [ ] **Backtest splitter:** Often `TimeSeriesSplit` on rows, not races — verify `set(train_races).isdisjoint(set(test_races))` for every fold; verify test races are strictly later than train.
- [ ] **Odds snapshot:** Often substituted on missing — verify `odds_missing_policy = no_bet`; verify `odds_snapshot_policy` is non-null on every backtest row.
- [ ] **DNF handling:** Often filtered out — verify DNF count in backtest == DNF count in raw results for the period; verify `effective_stake = 100` for DNF bets.
- [ ] **Calibration:** Often skipped or fit on training fold — verify a held-out calibrator; verify reliability diagram monotonized; verify EV uses calibrated `p`.
- [ ] **`sum(p)` check:** Often mean-only — verify median/std/p10/p90 reported by field-size bucket; verify out-of-range races triaged.
- [ ] **Class normalization:** Often name-based — verify normalization keys on `race_condition_code`; verify `post_2019_class_system_flag` present.
- [ ] **Reproducibility:** Often missing version keys — verify non-null `feature_snapshot_id`, `model_version`, `label_version`, `odds_snapshot_policy`, `backtest_strategy_version` on predictions and backtest rows; verify reproduce smoke test passes.
- [ ] **Recommendation rank:** Often shown without inputs — verify EV_lower/p/odds_lower shown alongside rank (§11.5); verify no "prediction confidence" used in Phase 1 rank (§11.5, §4).

## Recovery Strategies

When a pitfall is discovered despite prevention, how expensive is the fix?

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Pitfall 1 (lookahead leak) | **HIGH** | Identify the leaking feature (gain importance + cutoff audit), drop/rebuild it, regenerate feature snapshots with new `feature_snapshot_id`, retrain, re-backtest. Every prior result is suspect. |
| Pitfall 2 (hindsight odds) | **MEDIUM** | Re-decide `odds_snapshot_policy` on a validation-only period (not test), re-run all BT configs for all policies, publish all policies. Old reported ROI retracted. |
| Pitfall 3 (label basis) | **HIGH** | Reconstruct `sales_start_entry_count` for affected races, regenerate labels with new `label_version`, re-reconcile against payout table, retrain. Foundation-level; everything downstream redone. |
| Pitfall 4 (target-encoding leak) | **MEDIUM** | Switch to native categorical handling (LightGBM `categorical_feature` / CatBoost `cat_features`), drop pre-encoded columns, retrain. |
| Pitfall 5 (split leak) | **MEDIUM** | Replace splitter with `GroupTimeSeriesSplit`-on-`race_id`, re-run all folds. Metrics will drop — that's the honest number. |
| Pitfall 6 (DNF exclusion) | **LOW–MEDIUM** | Add DNF back as `fukusho_hit = 0`, fix `effective_stake`/refund logic in backtest, re-run. ROI drops. |
| Pitfall 7 (class reform) | **LOW–MEDIUM** | Re-normalize by code, add flag, retrain. If trained pre-2019 only, may be unaffected. |
| Pitfall 8 (calibration) | **MEDIUM** | Add held-out calibrator, rewire EV to calibrated `p`, re-evaluate. May shift which bets are EV-eligible. |
| Pitfall 9 (non-reproducibility) | **HIGH** | Backfill version keys is easy; reconstructing *what versions produced past results* may be impossible. Treat past results as invalidated. |
| Pitfall 10 (`sum(p)` neglect) | **LOW** | Add the distribution report and outlier triage. May reveal deeper model issues (Pitfall 8). |

## Pitfall-to-Phase Mapping

Maps each pitfall to the Phase 1 sub-area that must **prevent** it, and how to **verify** prevention during that phase. Phase 1 sub-areas per PROJECT.md Active list: data quality, ETL, label generation, feature/as-of, model, EV, backtest, UI/CSV.

| Pitfall | Primary Prevention Phase | Verification |
|---------|--------------------------|--------------|
| 1. Lookahead leakage in features | **Feature/as-of** (registry + cutoff filter); defense-in-depth in **backtest** | `feature_availability` allowlist test passes; temporal-split metrics ≈ random-split metrics (within reason); no past-start with `finish >= cutoff` |
| 2. Hindsight odds selection | **EV** (policy + missing-odds) + **backtest** (pre-registration, all-policies) | All candidate policies reported; `odds_snapshot_policy` non-null on every backtest row; selection decided on validation only |
| 3. Fukusho label basis | **Label generation** | Payout-table reconciliation >99.9% on sample; `unresolved` fraction reported; DNF present; no-sale races excluded |
| 4. Target/categorical leakage | **Model** (native encoding) | Leak diagnostic (rare-category shrinkage toward mean) passes; temporal-test LogLoss within expected gap of validation |
| 5. Time-series split leak | **Backtest** (splitter) | `set(train_races).isdisjoint(test_races)` for every fold; test races strictly later; same-day isolation hook present |
| 6. DNF exclusion | **Label generation** + **backtest** | DNF count in labels == raw; `effective_stake`/refund paths tested; ROI gap between with/without DNF logged |
| 7. Class-system reform | **ETL** (normalization) + **evaluation** (per-flag axis) | Normalization keys on `race_condition_code`; `post_2019_class_system_flag` present; per-flag calibration reported |
| 8. Probability calibration | **Model** (calibrator) + **EV** (use calibrated p) + **evaluation** (reliability gate) | Reliability curve monotonized on held-out; EV reads calibrated p; per-axis calibration reported |
| 9. Non-reproducibility | **Data quality / ETL / label / feature** (contracts) + **model / backtest** (enforce + reproduce test) | Version keys non-null on predictions/backtest; reproduce smoke test passes bit-identical |
| 10. `sum(p)` neglect | **Evaluation** (distribution gate) | mean/median/std/p10/p90 reported by field-size bucket; out-of-range races triaged |

## Phase-Ordering Implications

The pitfalls dictate a strict ordering for Phase 1, because each layer trusts the one below:

1. **Data quality / ETL** first — including class normalization (Pitfall 7). Everything downstream depends on clean, correctly-typed, code-keyed data.
2. **Label generation** next — Pitfalls 3 and 6 live here. The model cannot be trusted until labels are correct and reconciled. Gate: do not proceed until payout-table reconciliation passes.
3. **Feature/as-of** — Pitfalls 1 and (part of) 9. The `feature_availability` registry and cutoff filter are the leak firewall. Gate: allowlist test passes.
4. **Model** — Pitfalls 4 and 8. Encoding and calibration. The reproduce-smoke-test (Pitfall 9) is wired here.
5. **EV** — Pitfall 2 (policy + missing-odds) and Pitfall 8 (use calibrated p).
6. **Backtest** — Pitfalls 2 (all-policies reporting), 5 (splitter), 6 (effective_stake), 9 (version keys). The honest ROI is computed here.
7. **UI/CSV** — last; surfaces the version keys and sliced metrics so the developer cannot fool themselves.

**Implication for the roadmap:** the first three sub-areas (data quality → label generation → feature/as-of) are the leakage-critical foundation and should be a single, gated sequence — do not interleave model work before labels and features are locked. Pitfalls 1, 3, 4, 5 are *undetectable by "does it run" testing* and require adversarial audit tests; budget explicit time for those tests, not just feature implementation.

## Sources

Confidence per `classify-confidence --provider websearch` is **LOW** for all web-sourced claims (single provider, not cross-verified). JRA-rule claims are anchored to the authoritative requirements doc and official JRA/JRA-VAN sources and are **HIGH** confidence on the rules themselves. Treat the generic ML-leakage/calibration/CV claims as well-established practitioner consensus to verify against current docs during implementation.

- **Requirements (authoritative for JRA rules):** `docs/keiba_ai_requirements_v1.3.md` — §4 (v1.3 revisions), §9.3 (Phase 1 unused info), §10 (label spec), §11 (EV/odds/virtual-purchase), §13 (as-of), §15 (evaluation/backtest), §20 (risks table). [HIGH]
- **JRA 2019 class reform (race-condition code unchanged, code 005 spans 500万下/1勝クラス):** JRA rules page (jra.go.jp/keiba/rules/class.html); JRA-VAN developer forum topic 305; JRA-VAN data-change notice 2018-12-05 (jra-van.jp/dlb/sdv/ml/20181205a.html). [MEDIUM — corroborated across three JRA/JRA-VAN sources]
- **CatBoost Ordered Target Statistics / Ordered Boosting (Pitfall 4):** Prokhorenkova et al., "CatBoost: unbiased boosting with categorical features," NeurIPS 2018 (papers.neurips.cc/paper/7898); CatBoost docs — algorithm-main-stages_cat-to-numberic. [LOW via websearch; the NeurIPS paper is the primary source — verify against the paper directly during implementation]
- **LightGBM native categorical handling (no target encoding by default, -1 treated as missing) (Pitfall 4):** LightGBM Advanced Topics docs. [LOW via websearch; verify against current LightGBM docs]
- **GBM probability distortion & calibration (Pitfall 8):** Niculescu-Mizil & Caruana, "Predicting Good Probabilities With Supervised Learning," ICML 2005 (cs.cornell.edu/~alexn/papers/calibration.icml05); scikit-learn probability calibration docs; obtaining calibrated probabilities from boosting (arXiv 1207.1403). [LOW via websearch; ICML paper is primary]
- **TimeSeriesSplit group leakage, GroupTimeSeriesSplit (Pitfall 5):** scikit-learn TimeSeriesSplit docs; mlxtend GroupTimeSeriesSplit docs (rasbt.github.io/mlxtend); Kaggle "TS-10 validation methods for time series"; StackOverflow 51963713 (cross-validation for grouped time-series panel data). [LOW via websearch; verify against scikit-learn/mlxtend current docs]
- **Backtest biases (look-ahead, survivorship, hindsight, data snooping) (Pitfall 2):** AnalystPrep CFA L2 problems-in-backtesting; Hedge Fund Alpha backtesting-mistakes guide; Sharpely point-in-time data article. [LOW via websearch — quant-finance consensus, cross-domain analogy]
- **Reproducibility / versioning (Pitfall 9):** CMU MLiP book ch.24 (versioning, provenance, reproducibility); Martin Fowler CD4ML. [LOW via websearch]
- **JRA fukusho refund/scratch/dead-heat rules (Pitfalls 3, 6):** websearch returned mostly non-JRA bookmaker rules; JRA-specific mechanics per requirements §10.5, §10.6, §11.6 are authoritative. Cross-check against JRA official rules (jra.go.jp) during implementation.

---
*Pitfalls research for: JRA horse-racing prediction ML (fukusho / place-bet payout-eligibility + EV)*
*Researched: 2026-06-16*
