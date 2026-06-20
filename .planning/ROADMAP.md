# Roadmap: Keiba AI v3

## Overview

Phase 1 (v1 milestone) is a single milestone — a leakage-critical, reproducibility-critical pipeline that estimates per-horse 複勝払戻対象確率 `p_fukusho_hit`, evaluates EV against a fixed-snapshot odds policy, runs a race_id-unit time-series backtest with honest refund/dead-loss accounting, and presents results through a minimal Streamlit UI + CSV. The phases below mirror the strict dependency DAG from the research build order (raw gate → normalized ETL → labels → as-of features → model → prediction → EV → backtest → evaluation → presentation), with each layer boundary also serving as a leakage checkpoint. The competitive moat is discipline (correct labels, leakage-free as-of, fixed-odds-snapshot backtest, calibrated probabilities, reproducibility stamps) — every phase has an explicit gate tied to a silent-failure-mode verification. No model work interleaves before labels and features are locked. A final cross-cutting adversarial-audit phase consolidates the leakage-prevention test suite before presentation.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Trust & Foundation** - Raw quality gate + normalized ETL + leakage-prevention stack bootstrap (completed 2026-06-17)
- [x] **Phase 2: Fukusho Labels** - Sales-start-time labels with payout-table reconciliation (highest-risk, long pole) (completed 2026-06-18)
- [x] **Phase 3: As-of Features & Snapshots** - PIT-correct feature builder + immutable versioned Parquet snapshots (4/4 plans executed + 1 gap-closure plan 03-05 COMPLETE; CR-01/02/03/04 + WR-01 全解消・live-DB snapshot rebuild で registry↔実体 parity 実証) (completed 2026-06-19)
- [x] **Phase 3.1: Timediff/Babacd Rolling Restoration (INSERTED)** - normalized ETL 拡張 (timediff/baba3) + rolling 8系統化 + advisory 4件 hardening + live snapshot rebuild (snapshot-id=20260619-1a-v3・feature_count=63・SHA256 byte-repro・216 passed) (completed 2026-06-19)
- [ ] **Phase 4: Model & Prediction** - Baselines BL-1..BL-5 + Phase 1-A LightGBM/CatBoost + calibrated p_fukusho_hit
- [ ] **Phase 5: EV & Backtest** - EV/rank module + race_id-grouped virtual-purchase simulator with fixed odds policy
- [ ] **Phase 6: Evaluation & Calibration Gates** - Acceptance criteria (Brier/LogLoss/calibration/sum(p)/stability)
- [ ] **Phase 7: Presentation** - Streamlit minimal UI + prediction/backtest CSV export
- [ ] **Phase 8: Adversarial Audit Suite** - Cross-cutting leakage-prevention test set spanning all critical surfaces

## Phase Details

### Phase 1: Trust & Foundation

**Goal**: All downstream work runs on quality-checked, typed, class-normalized raw data, with the leakage-prevention primitives (frozen category maps, PIT joiner, race_id-grouped splitter, prefit chronological calibrator, feature_availability registry) bootstrapped and available before any feature/label code runs
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):

  1. A developer can run the raw data quality report and see per-table counts, date range (≥2015-01-01 present), NULL rates, primary/natural-key duplicates, mojibake flags, and code-value anomalies with a pass/fail verdict
  2. A developer can read a `normalized` table whose columns are typed, code-converted, and NEVER populated by mutating the raw layer (raw is read-only) — proven by an assertion that raw row hashes are unchanged after ETL
  3. Class normalization is driven by `race_condition_code` (not name strings), producing `class_code_normalized` / `class_name_normalized` / `class_level_numeric` / `post_2019_class_system_flag` where code 005 correctly spans both the pre-2019 (500万下) and post-2019 (1勝クラス) eras without collision
  4. The leakage-prevention primitives exist as importable utilities: `merge_asof(direction='backward', by=<entity>)` PIT joiner (with sortedness pre-check that raises if unsorted), `GroupTimeSeriesSplit` race_id-grouped splitter, frozen-category-map fitter (training-window-only fit, `__UNSEEN__` fallback), and `CalibratedClassifierCV(cv='prefit')` chronological calibrator — each with a passing smoke test

**Plans**: 3 plans in 3 waves
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Wave 1 基盤（uv/接続/5層スキーマ/class_normalization.yaml）— DATA-03

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Wave 2 品質ゲート（hybrid gate, reports/ Markdown+JSON）— DATA-01
- [x] 01-04-PLAN.md — Wave 2 リーク防止プリミティブ4種（pit_join/group_split/category_map/calibrator）— 成功基準#4

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Wave 3 normalized ETL + クラス正規化 + raw 不変性 pytest（成功基準#2/#3）— DATA-02/DATA-03

### Phase 2: Fukusho Labels

**Goal**: The single source of truth for the prediction target — `fukusho_hit_validated` — is correct, reconciled against the official payout table, and uses sales-start-time basis (not final starter count) with dead-heat, scratch, and dead-loss (競走中止) handled per JRA rules
**Depends on**: Phase 1
**Requirements**: LABEL-01, LABEL-02, LABEL-03, LABEL-04
**Success Criteria** (what must be TRUE):

  1. A developer can read a label row containing both `fukusho_hit_raw` (着順-derived first pass) and `fukusho_hit_validated` (payout-table-reconciled), with `label_validation_status` ∈ {`validated`, `inferred`, `dead_heat`, `unresolved`} on every row
  2. The payout-table reconciliation test passes at >99.9% agreement on a held-out sample: every `fukusho_hit_validated=1` horse exists in the payout table's 複勝払戻対象 with no missing/extra positives, no scratch/除外 horse mislabeled positive, and 複勝発売なし races are excluded from the model-eligible set
  3. `sales_start_entry_count` is populated on every eligible race — either from a direct column OR restored from entry-list + 取消/競走除外 announcement timestamps, with the `unresolved` fraction reported and the `unresolved` rows excluded from training/evaluation
  4. Dead-heat races label ALL payout-table 複勝対象 horses as positive; 取消/除外 horses are prediction-excluded (and refund-handled later); 競走中止 horses remain in-training and are labeled `fukusho_hit=0` (no exclusion) — verified by a unit test that constructs each scenario and asserts the label

**Plans**: 5 plans in 4 waves (4 original + 1 gap-closure)
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Wave 1 基盤（label_spec.yaml / GRANT 拡張 / search_path / run_apply_schema 再実行）— LABEL-01/02/03/04 前提
- [x] 02-02-PLAN.md — Wave 1 unit test 集群（LABEL-01/02/04・合成 DataFrame・mock cursor・18テスト RED）— LABEL-01/02/04

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Wave 2 label ETL 本体（fukusho_label.py・idempotent load・raw 不変性拡張）— LABEL-01/02/04

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — Wave 3 払戻テーブル突合ゲート（label_reconcile.py・§10.5 6検査 BLOCK/INFO・>99.9% agreement）— LABEL-03

### Phase 3: As-of Features & Snapshots

**Goal**: The leakage-prevention backbone is enforced — every feature row is point-in-time correct via `feature_cutoff_datetime` and the `feature_availability` taxonomy, the Phase 1-A allowlist forbids banned timings (post-race, same-day, body-weight-announced, race-day-morning, odds), and the immutable Parquet snapshots carry the full reproducibility manifest
**Depends on**: Phase 2
**Requirements**: FEAT-01, FEAT-02
**Success Criteria** (what must be TRUE):

  1. A feature row carries `as_of_datetime`, `feature_cutoff_datetime`, `feature_snapshot_id`, and `feature_availability` (`available_from_timing`, `leakage_risk_level`) on every column, and the PIT join uses `merge_asof(direction='backward')` so a horse's feature value at prediction time T uses only data known strictly before T
  2. The fail-loud feature-allowlist test passes: the Phase 1-A feature matrix contains ZERO features tagged `post_race_only` / `odds_snapshot_available` / `body_weight_announced` / `race_day_morning` / `same_day_aggregate` (当日馬場/天候/馬体重/当日オッズ/人気集中度/レース後通過順・上がり・走比タイム/当日レース結果由来集計 all excluded)
  3. A developer can write a Parquet snapshot whose embedded metadata block contains `dataset_version`, `feature_snapshot_id`, `label_generation_version`, `feature_cutoff_datetime`, `prediction_timing`, and train/val period bounds — and re-reading the snapshot reproduces identical bytes (immutability verified by hash)
  4. Frozen category maps are fit on the training window only, persisted alongside the snapshot, and applied to val/test with unknown IDs mapping to `__UNSEEN__` (not NaN)

**Plans**: 5 plans in 4 waves (4 original + 1 gap-closure)
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Wave 1 基盤（features package + feature_availability.yaml 25エントリ source_role taxonomy + cutoff_semantics strict_less_than + availability loader + assert_matrix_columns_registered + 5-row adversarial rolling builder + RED テスト stub 集群 SC#1-#4/D-03/D-04/D-05/D-06/D-09 + REVIEWS HIGH #1/#2/#3/#4/#5/#6）— FEAT-01/02
- [x] 03-02-PLAN.md — Wave 1 Phase 2 負債解消（label_race_date_backfill.py・staging-swap idempotent・cutoff 前提・MEDIUM #7 disposition 追加）— FEAT-01 前提（実 DB で race_date 全 554267 行 backfill 済・2回実行 idempotent verify + raw 不変性 PASS）

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-03-PLAN.md — Wave 2 feature builder 本体（builder.py + rolling.py 9系統×3軸 per-observation latest-K algorithm + running_style.py 推定脚質・明示カラム SELECT・target-obs/history taxonomy・出力カラム registry 検査・SC#1/#2 GREEN・REVIEWS HIGH #1/#2/#3/#4）— FEAT-01/02

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-04-PLAN.md — Wave 3 snapshot writer + category_map_consumer + CLI（PyArrow 決定論的書込・§12.4 metadata・SHA256 byte-repro scope=parquet bytes only・raw ID 列 drop・train窓fit/__UNSEEN__・SC#3/#4 GREEN・REVIEWS HIGH #5/#6 + MEDIUM #10）— FEAT-01/02

**Wave 4** *(gap-closure — blocked on Wave 3 completion)*

- [x] 03-05-PLAN.md — Wave 4 gap-closure（CR-01 rolling_timediff_*/rolling_babacd_* 6エントリ削除 + registry↔rolling↔reserved 3者 parity + end-to-end regression guard test・WR-01 estimated_running_style PIT pre-filter・CR-02 JOIN 右側 nr に project_window_filter('nr')・CR-03 race_date 欠損 fail-loud・CR-04 joblib.load → JSON 移行で pickle ACE 解消・artifact 拡張子 .joblib → .json）— FEAT-01/02 — **COMPLETE** (3 tasks・191 tests GREEN・live-DB snapshot rebuild で parity 実証)

### Phase 03.1: Timediff/Babacd Rolling Restoration (INSERTED — COMPLETE)

**Goal**: Phase 3 gap-closure (03-05) で silent-empty breach を解消するために一時削除した `rolling_timediff_*` / `rolling_babacd_*` 計6 feature を復元する。Phase 2 normalized ETL を拡張して `timediff`（勝馬差）・`babacd`（過去走馬場状態）の source カラムを `normalized.n_uma_race` に取り込み、Phase 3 の rolling 系統（`_ROLLING_SYSTEMS` / `_SYSTEM_SOURCE` / availability reserved）に6系統を再登録して、Phase 1-A rolling features を 18 → 24（8系統×3軸）に拡張する。registry↔rolling↔Parquet parity を維持したまま、Phase 4（Model & Prediction）が利用可能な feature を増やす。PIT-correctness は rolling.py の既存 strict `< cutoff` + per-observation window で保たれ、新規 leak は生じない（03-05 の end-to-end regression guard が検出）。**併せて Phase 03 code review advisory 4件（WR-01' silent no-filter fallback・WR-02 `_fetch` except→空DF・CR-01新 manifest→persist 順序依存・WR-03 rolling `groupby().apply` pandas 3.x 非推奨）の hardening を実施する**（同ファイル群 `builder.py` / `rolling.py` / `run_feature_build.py` を編集するため効率的・Phase 4 学習前のリーク防止・再現性 defense-in-depth・todo `phase3-advisory-hardening.md` 参照）。
**Depends on**: Phase 3（gap-closure 03-05 完了後・03-CONTEXT.md Deferred note 参照）
**Requirements**: FEAT-01
**Success Criteria** (what must be TRUE):

  1. `normalized.n_uma_race` に `timediff` / `babacd` カラムが存在し、Phase 2 の staging-swap idempotent ETL で `raw_everydb2` から機械的に取り込まれる（§19.1 再現性・raw 不変性維持）
  2. `rolling_timediff_{mean,latest,sd}_5` / `rolling_babacd_{mean,latest,sd}_5` の6 feature が `feature_availability.yaml`（registry）・`rolling.py::_ROLLING_SYSTEMS`/`_SYSTEM_SOURCE`・`availability.py::_ROLLING_SYSTEMS_FOR_RESERVED` の三者で再登録され、3者 parity test（`test_registry_rolling_systems_match_rolling_impl`）が GREEN
  3. 新 snapshot で6 feature 列が（source が存在する行で）non-null を持ち、end-to-end regression guard test（`test_no_registered_feature_column_all_nan_end_to_end`）が GREEN を維持
  4. manifest `feature_count` が rolling 18 → 24 を反映し、registry↔Parquet parity（宣言 feature 数 == populated feature 列数）が保たれる

**Plans**: 4/4 plans executed (COMPLETE)

Plans:
**Wave 1**

- [x] 03.1-01-PLAN.md — Wave 1: normalize.py ETL 拡張（n_uma_race に timediff(varchar4)・n_race に baba3(sibababacd/dirtbabacd/trackcd・全varchar) を SELECT/DDL/INSERT 定義に追加・raw 不変・staging-swap idempotent 再利用）
- [x] 03.1-02-PLAN.md — Wave 1: run_feature_build.py CR-01新（persist→manifest 順序化 + exists assert + repo-root 相対パス）+ test_snapshot_repro.py（stale 参照整理 + CR-01新 回帰テスト）

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03.1-03-PLAN.md — Wave 2: feature core + advisory hardening（builder.py: timediff parse + babacd trackcd 分岐派生 + WR-01'/WR-02 fail-loud・rolling.py: 8系統化 + WR-03 vector化・availability/yaml×2: 3者 parity 再登録・label_spec: sentinel 0000・テスト5関数更新）— Plan 01 に依存

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03.1-04-PLAN.md — Wave 3: live snapshot rebuild + SC#3/SC#4 検証（checkpoint:human-verify・許可済み live-DB で ETL 再実行 + snapshot rebuild + byte-repro + parity・SC#1-#4 実証・snapshot-id=20260619-1a-v3・feature_count=63・216 passed・人間 approved）— Plan 01/02/03 に依存 — **COMPLETE**

### Phase 4: Model & Prediction

**Goal**: A calibrated `p_fukusho_hit` estimate produced from odds-free Phase 1-A features, where the model adds measurable value over simple baselines and the market reference, with full reproducibility
**Depends on**: Phase 3
**Requirements**: MODL-01, MODL-02, MODL-03
**Success Criteria** (what must be TRUE):

  1. A developer can train the Phase 1-A model (LightGBM 4.6 + CatBoost 1.2.10) off a stamped Parquet snapshot ONLY — never the live DB — and score new horses to emit `p_fukusho_hit` with provenance (`model_version`, `feature_snapshot_id`, `as_of_datetime`)
  2. Baselines BL-1 (頭数別一定) through BL-5 (LightGBM minimal features) are evaluated alongside the primary model, producing a comparison table that answers "does the AI model add value over simple models and the BL-3 odds-inverse market reference?"
  3. Categorical/missing handling is leak-safe: LightGBM uses native categorical with non-negative codes and explicit `__MISSING__`/`__UNSEEN__` sentinels (NaN→-1 forbidden); CatBoost uses `cat_features` + `has_time=True` on a Pool sorted by `race_start_datetime`; NO target/mean encoding anywhere (verified by a leak diagnostic where rare categories shrink toward the mean rather than match their own label)
  4. Calibration uses `CalibratedClassifierCV(cv='prefit', method='isotonic')` on a strictly-later disjoint slice, with a unit test asserting `max(train.race_date) < min(calib.race_date)` — and a reproduce-smoke-test (fixed seeds → identical predictions on re-run) passes

**Plans**: 5/6 plans executed

Plans:
**Wave 1**

- [x] 04-01-PLAN.md — 基盤（lightgbm/catboost pin + prediction DDL/GRANT + RED stubs + v3 ドリフト修正）

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — data.py + calibrator.py + artifact.py（SC#1 stamped Parquet・3way split・prefit wrapper・review HIGH#9/MEDIUM#5/MEDIUM#6/HIGH#5 全対応）

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-03-PLAN.md — trainer.py + baseline.py（SC#3 leak diagnostic・LightGBM native + CatBoost has_time・BL-1..5）
- [x] 04-04-PLAN.md — predict.py + prediction_load.py + evaluator.py（provenance・staging-swap・比較表）

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 04-05-PLAN.md — run_train_predict.py + SC#4 reproduce smoke（両モデル統合・bit-identical）

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 04-06-PLAN.md — SC#3/SC#4 構造的ブロック GREEN + ROADMAP 更新（Phase 4 完了宣言）

### Phase 5: EV & Backtest

**Goal**: The honest verdict — EV/rank computation against a fixed `odds_snapshot_policy`, and a race_id-grouped time-series virtual-purchase backtest with refund/scratch/dead-loss accounting that cannot be inflated by hindsight odds selection
**Depends on**: Phase 4
**Requirements**: EV-01, EV-02, BACK-01, BACK-02, BACK-03, BACK-04
**Success Criteria** (what must be TRUE):

  1. A developer can compute `EV_lower = p × odds_lower` and `EV_upper = p × odds_upper` and assign `recommend_rank` (S/EV≥1.20, A/EV≥1.10, B/EV≥1.05, C/EV≥1.00, D/otherwise) using ONLY EV, probability, and odds_lower — no immature confidence score feeds the rank
  2. The backtest splitter groups by `race_id` and orders by `race_date`/`race_start_datetime` ascending, with a hard assertion `set(train_races).isdisjoint(test_races)` for every fold (via `mlxtend.GroupTimeSeriesSplit`) — no row-level split is permitted
  3. The virtual-purchase simulator applies the fixed rule (EV_lower≥1.05, p≥0.15, odds_lower≥1.5, top-2/race, 100 yen/bet, fukusho-only) and reports recovery rate, P/L, max drawdown, selected_count, effective_bet_count, and refund_count stamped with `backtest_strategy_version`
  4. Refund/dead-loss accounting is honest: 取消/除外 → `effective_stake=0` (refund); 競走中止 → `effective_stake=100` counted as a loss (no exclusion inflating ROI) — verified by a unit test that builds a race with each scenario and asserts the stake/payout
  5. The `odds_snapshot_policy` is fixed (30-min-before or 10-min-before), `odds_missing_policy = no_bet` (never substitutes a convenient snapshot), and ALL candidate policies × BT configs are reported together — never the post-hoc winner alone

**Plans**: TBD

### Phase 6: Evaluation & Calibration Gates

**Goal**: The probability quality acceptance criteria are verified before any result is shown to a user — calibration, Brier, LogLoss, sum(p) distribution, and stability-by-segment all pass the §15.2/§15.3 gates
**Depends on**: Phase 5
**Requirements**: EVAL-01, EVAL-02, EVAL-03
**Success Criteria** (what must be TRUE):

  1. A developer can run the evaluation suite and receive 複勝的中率, 回収率, 損益, 最大ドローダウン, 購入点数, Brier Score, LogLoss, and Calibration Curve (overall)
  2. The acceptance gate passes: yearly calibration curves have NO extreme inversions, per-bin observed rates are monotonically-increasing-ish, LogLoss/Brier beat the baselines, `sum(p)` mean matches the theoretical payout-places per field-size bucket (~3.0 for ≥8-horse, ~2.0 for 5–7), with median/SD/p10/p90 reported
  3. Stability-by-segment evaluation produces per-year, per-month, per-競馬場, per-頭数, per-人気帯, per-オッズ帯 Calibration Curves so segment collapse (hidden by aggregate recovery rate) is visible

**Plans**: TBD

### Phase 7: Presentation

**Goal**: A user can inspect the model's verdict — predictions, EV, recommendations, and backtest results — through a read-only Streamlit UI and reproducible CSV exports that surface every reproducibility stamp inline
**Depends on**: Phase 6
**Requirements**: UI-01, OUT-01, OUT-02
**Success Criteria** (what must be TRUE):

  1. A user can open the Streamlit app and view a race list with per-horse `p_fukusho_hit`, 複勝オッズ下限/上限, `EV_lower`/`EV_upper`, `recommend_rank`, AND inline `odds_snapshot_policy` / `odds_snapshot_at` / `model_version` / `feature_snapshot_id` / `backtest_strategy_version` on every prediction (ワイド/荒れ指数/コメント生成 NOT shown)
  2. A user can export a prediction CSV with the pinned column list (race_id/race_date/race_start_datetime/競馬場/レース番号/horse_id/horse_name/枠番/馬番/p_fukusho_hit/オッズ下限上限/EV/recommend_rank/スナップショット情報)
  3. A user can export a backtest CSV with the pinned column list (backtest_id/戦略バージョン/学習検証期間/odds_snapshot_policy/race_id/horse_id/selected_flag/stake/refund_flag/payout_amount/profit/fukusho_hit_validated/recommend_rank/EV)

**Plans**: TBD
**UI hint**: yes

### Phase 8: Adversarial Audit Suite

**Goal**: The cross-cutting leakage-prevention test suite (TEST-01) — adversarial audit tests for every silent-failure-mode surface — is consolidated and green, serving as the "Looks Done But Isn't" acceptance gate before the milestone ships
**Depends on**: Phase 7
**Requirements**: TEST-01
**Success Criteria** (what must be TRUE):

  1. A developer can run the full test suite and see green on every leakage-prevention surface: fukusho label generation + payout-table reconciliation, 取消/除外/競走中止 handling, fixed-odds-snapshot enforcement (hindsight selection rejected), virtual-purchase rules, `feature_cutoff_datetime` enforcement, race_id-unit split disjointness, class normalization (2019 reform code continuity), categorical/missing handling (no target encoding, no NaN→-1)
  2. The suite includes adversarial audit tests that catch what functional tests cannot: a synthetic-lookahead injection (a feature value at T using data from T+1) is detected and fails; a payout-table-positive horse missing from labels is detected; a fold whose train/test share a race_id is detected
  3. The test suite is wired into the reproducibility smoke-test path — running it confirms the full pipeline reproduces identical predictions/backtest numbers from stamped snapshots under fixed seeds

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Trust & Foundation | 4/4 | Complete    | 2026-06-17 |
| 2. Fukusho Labels | 4/4 | Complete    | 2026-06-18 |
| 3. As-of Features & Snapshots | 5/5 | Complete    | 2026-06-19 |
| 3.1 Timediff/Babacd Rolling Restoration (INSERTED) | 4/4 | Complete    | 2026-06-19 |
| 4. Model & Prediction | 5/6 | In Progress|  |
| 5. EV & Backtest | 0/TBD | Not started | - |
| 6. Evaluation & Calibration Gates | 0/TBD | Not started | - |
| 7. Presentation | 0/TBD | Not started | - |
| 8. Adversarial Audit Suite | 0/TBD | Not started | - |
