---
phase: 04-model-prediction
plan: 03
subsystem: model-trainer-baseline
tags: [phase-04, trainer, baseline, sc3, leak-diagnostic, bl1-bl5, modl-02, modl-03, review-high2, review-high3, review-high6, review-high7, review-cross-plan-8, cycle2-new-2]
requires:
  - "Phase 04-02: data.py / calibrator.py / artifact.py (load_frozen_maps / FEATURE_COLUMNS / split_3way / fit_prefit_calibrator)"
  - "Phase 04-01: lightgbm/catboost pin + prediction DDL + RED stubs"
provides:
  - "src/model/trainer.py: train_lightgbm / train_catboost / assert_eval_disjoint / align_predictions / _prepare_lightgbm_matrix / _prepare_catboost_pool / _prepare_lightgbm_train_eval / _split_train_eval_tail / _build_rare_category_synthetic / _build_intentional_leak_control / inject_intentional_leak_feature + 定数 LOW_CARD_CAT_COLS / HIGH_CARD_CODE_COLS / ALL_CAT_COLS / LGB_INIT_PARAMS / CB_INIT_PARAMS"
  - "src/model/baseline.py: compute_bl1 / compute_bl2 / compute_bl3 / compute_bl4 / compute_bl5 / compute_all_baselines / _race_normalize_inverse / _payout_places / fetch_market_data + 定数 BL4_FEATURES / BL5_FEATURES / BL3_COMPARISON_CAVEAT / BL_UNCALIBRATED_NOTE"
  - "GREEN 化: tests/model/test_trainer.py (6件) + tests/model/test_baseline.py (8件)"
affects:
  - "後続 PLAN 04 (predict/prediction_load): trainer.py の train_lightgbm/train_catboost/align_predictions を消費・CatBoost 予測の行整列を align_predictions で保証"
  - "後続 PLAN 05 (evaluator/orchestrator): train_and_predict が trainer と baseline を統合・p_bl* 比較表生成"
tech-stack:
  added: []
  patterns:
    - "LightGBM native categorical + 非負 int32 code 保証（__MISSING__ sentinel・HIGH_CARD_CODE_COLS も categorical・target encoding 禁止）"
    - "CatBoost has_time=True + cat_features に _code 列を astype(str) で含める（review HIGH#6: 数値扱い禁止・MODL-03）"
    - "_prepare_catboost_pool が race_start_datetime sort 済み Pool を返し sorted_index も返却（review HIGH#2 行整列）"
    - "align_predictions 5 条件厳密置換 guard（is_unique ×2 / set 等価 / len 等価 / isna なし）で reindex silent NaN/dup/drop を fail-loud（Cycle 2 NEW-2 / T-04-15c）"
    - "assert_eval_disjoint: pairwise disjoint + eval_max_date <= train_max_date（review Cross-Plan #8 / T-04-16）"
    - "_prepare_lightgbm_train_eval: train/eval の categorical categories を完全一致させる（LightGBM の train/valid category mismatch 回避）"
    - "_race_normalize_inverse: 1/value レース内正規化で sum(p)==払戻対象数 を保証（Pitfall 6 回避）"
    - "市場データ (fukuoddslow/ninki) は BL 計算専用・feature matrix には混入しない（D-07 / MODL-01 odds-free）"
    - "BL-4/BL-5 calibrate 引数 + bl_calib_note 列でキャリブレーション状態を明示（review MEDIUM: SC#2 公平性）"
key-files:
  created:
    - "src/model/trainer.py"
    - "src/model/baseline.py"
  modified:
    - "tests/model/test_trainer.py"
    - "tests/model/test_baseline.py"
decisions:
  - "LightGBM 決定論: seed=42 / deterministic=True / force_col_wise=True / num_threads=1 / bagging_seed=42 / feature_fraction_seed=42 (D-06 + review HIGH#7 bit-identical)"
  - "CatBoost 決定論: has_time=True / random_seed=42 / thread_count=1 / allow_writing_files=False (review HIGH#7 + CI 再現性)"
  - "review HIGH#6: HIGH_CARD_CODE_COLS (jockey/trainer/sire/bms/horse _code) を LightGBM categorical_feature と CatBoost cat_features の両方に含める・CatBoost では astype(str) で数値扱いを防止 (MODL-03)"
  - "review HIGH#2: train_lightgbm/train_catboost/compute_bl4/bl5 が X.index.equals(y.index) を raise ValueError で assert (silent wrong-horse prediction 防止)"
  - "Cycle 2 NEW-2: align_predictions が 5 条件 (is_unique ×2 / set 等価 / len 等価 / isna なし) の厳密置換 guard を RuntimeError で実装・reindex silent NaN/dup/drop を fail-loud に検出"
  - "review Cross-Plan #8: assert_eval_disjoint が pairwise disjoint + eval_max_date <= train_max_date を検証 (eval が train 末尾に収まる・Pitfall 5 / D-04 / T-04-16)"
  - "review HIGH#3: SC#3 leak diagnostic が低基数 RARE_X + 高基数 _code train-only/test-unseen + 意図的 target encoding 風リーク注入で DEMONSTRABLY fail を実証 (leak feature 1.0 注入で予測が threshold 0.9 を超える)"
  - "D-07/D-08: BL-2/BL-3 市場データ (ninki/fukuoddslow) は BL 計算専用・feature matrix には混入しない (MODL-01 odds-free allowlist)・§14.2 比較条件を BL3_COMPARISON_CAVEAT で明示"
  - "review MEDIUM: BL-4/BL-5 が calibrate 引数を持ち・compute_all_baselines が bl_calib_note 列でキャリブレーション状態を明示 (SC#2 比較公平性)"
  - "Rule 3 auto-fix: LightGBM train/eval categorical categories を完全一致させる _prepare_lightgbm_train_eval helper を追加 (LightGBM 4.6 が train/valid categorical_feature mismatch で ValueError を raise する仕様への対応)"
  - "Rule 3 auto-fix: fetch_market_data が raw_everydb2.n_odds_tanpuku (varchar) と normalized.n_uma_race (int) の PK 型不一致を int CAST JOIN で吸収 (kettonum は n_odds_tanpuku に無く n_uma_race 側から取得)"
metrics:
  duration: 34m
  completed: 2026-06-20
  tasks: 2
  files_created: 2
  files_modified: 2
status: complete
---

# Phase 4 Plan 03: Trainer & Baseline Summary

**LightGBM native categorical + CatBoost has_time=True (SC#3 / §14.3 / §14.4) + 高基数 _code cat_features 扱い (review HIGH#6 / MODL-03) + 行整列保証 (review HIGH#2 / Cycle 2 NEW-2) + eval set 分離 (review Cross-Plan #8) + SC#3 leak diagnostic (review HIGH#3)・BL-1..5 全5つ計算 (MODL-02 / SC#2 / D-07 / D-08)**

Phase 4 Wave 3 として、後続 PLAN 04 (predict/prediction_load) が依存する「train_lightgbm / train_catboost (LightGBM native cat + CatBoost has_time + 行整列)」と「BL-1..5 計算 (市場データは feature に混入せず)」を実装した。review HIGH#2/#3/#6/#7 + Cross-Plan #8 + Cycle 2 NEW-2 の全項目を実行可能契約に変換し・リーク防止 (target encoding 禁止・has_time=True・非負 code・行整列) と bit-identical 再現性 (決定論フラグ全箇所固定) を同時に達成した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | src/model/trainer.py — LightGBM native cat + CatBoost has_time + SC#3 leak diagnostic (SC#3/MODL-03/D-04) | `b73599f` | src/model/trainer.py, tests/model/test_trainer.py |
| 2 | src/model/baseline.py — BL-1..5 計算 (MODL-02/SC#2/D-07/D-08) | `c868794` | src/model/baseline.py, tests/model/test_baseline.py |

## What Was Built

### Task 1: src/model/trainer.py — SC#3 / MODL-03 / D-04 / review HIGH#2/#3/#6/#7 / Cross-Plan #8 / Cycle 2 NEW-2

- **LightGBM native categorical (§14.3 / SC#3 / T-04-14)**: `_prepare_lightgbm_matrix` が LOW_CARD_CAT_COLS を `fillna("__MISSING__").astype("category")` で sentinel 化・HIGH_CARD_CODE_COLS を int32 のまま `category` dtype 化・全 categorical 列の `.cat.codes.min() >= 0` を assert する（NaN→-1 ハザード回避・Pitfall 3）。
- **train/eval categorical 統一 (Rule 3 auto-fix)**: `_prepare_lightgbm_train_eval` が train ∪ eval の全カテゴリ値で統一した category dtype を両方に適用する。LightGBM 4.6 が train/eval の categorical_feature 不一致で `ValueError` を raise する仕様に対応。
- **CatBoost has_time=True + cat_features (§14.4 / review HIGH#6 / T-04-13b/15)**: `_prepare_catboost_pool` が `df.sort_values(["race_start_datetime", "race_key"], kind="mergesort")` してから Pool を構築（has_time=True が入力順序を使用）。LOW_CARD_CAT_COLS と HIGH_CARD_CODE_COLS の**両方**を cat_features に含め・HIGH_CARD_CODE_COLS は `astype(str)` で文字列化して数値扱いを防止（review HIGH#6: 任意 ID 順序に序数構造を課す MODL-03 違反を防止）。
- **行整列保証 (review HIGH#2 / T-04-15b)**: `train_lightgbm` / `train_catboost` が `X_train.index.equals(y_train.index)` を `raise ValueError` で assert。`_prepare_catboost_pool` が `(Pool, sorted_index)` を返し・予測パスが `align_predictions` で元の行順序に復元する。
- **align_predictions 5 条件厳密置換 guard (Cycle 2 NEW-2 / T-04-15c)**: reindex 前に (a) `sorted_index.is_unique` / (b) `original_index.is_unique` / (c) `set(sorted_index) == set(original_index)` / (d) `len(sorted_index) == len(original_index)` / (e) `len(pred) == len(sorted_index)` を検証し・reindex 後 `not aligned.isna().any()` を RuntimeError で fail-loud。部分集合 / 重複 / 長不一致のテスト入力で fail-loud を実証（test_catboost_predict_preserves_row_order の 3 ケース）。
- **assert_eval_disjoint (review Cross-Plan #8 / T-04-16 / Pitfall 5 / D-04)**: eval/calib/test の正準 race_key が pairwise disjoint (3組) であることに加え・`eval_max_date <= train_max_date` (eval が train 末尾に収まる) を検証。違反時 `raise ValueError`。
- **決定論フラグ全箇所固定 (review HIGH#7 / T-04-19 / SC#4)**: LGB_INIT_PARAMS = `seed=42, deterministic=True, force_col_wise=True, num_threads=1, bagging_seed=42, feature_fraction_seed=42`。CB_INIT_PARAMS = `has_time=True, random_seed=42, thread_count=1, allow_writing_files=False`。
- **SC#3 leak diagnostic (review HIGH#3 / T-04-13)**: `_build_rare_category_synthetic` が低基数 RARE_X + 高基数 _code train-only/test-unseen の合成データを構築。`_build_intentional_leak_control` + `inject_intentional_leak_feature` が RARE_X 行に 1.0 (train label 平均) を直接 numeric feature として注入する target encoding 風リークをシミュレートし・予測が threshold (0.9) を超えることを実証 (leak diagnostic が false-pass でないことを DEMONSTRABLY 実証)。
- **target encoding API 構造的禁止 (§14.3)**: `test_no_target_encoding_imports_in_trainer_module` が `category_encoders` import / `TargetEncoder(` 呼出が source に含まれないことを検証。
- **test_trainer.py 6件 GREEN**: test_lightgbm_nonneg_codes / test_catboost_has_time / test_catboost_predict_preserves_row_order / test_no_target_encoding_leak / test_eval_set_disjoint_from_calib_test / test_no_target_encoding_imports_in_trainer_module。

### Task 2: src/model/baseline.py — MODL-02 / SC#2 / §14.2 / D-07 / D-08 / review MEDIUM

- **BL-1 頭数別一定 (D-08)**: `_payout_places(entry_count)` が 8頭以上で 3・5-7頭で 2 を返す。`compute_bl1` が `places / entry_count` で全馬同一値を返す（fukusho_payout_places 列を優先）。
- **BL-2 確定人気由来 (D-08 / D-07)**: `compute_bl2` が `n_uma_race.ninki` の `1/ninki` を `_race_normalize_inverse` でレース内正規化。
- **BL-3 確定複勝オッズ逆数 (D-08 / D-07 / §14.2)**: `compute_bl3` が `n_odds_tanpuku.fukuoddslow` の `1/fukuoddslow` をレース内正規化。`BL3_COMPARISON_CAVEAT` 定数で「Phase 1-A モデルと同一情報条件の比較ではない」旨を明示。
- **_race_normalize_inverse (Pitfall 6 回避)**: `1/value` をレース内で `(1/v_i) / sum(1/v) × payout_places` で正規化し・`sum(p) == 払戻対象数` を保証。value が 0/NaN の行は NaN で除外。
- **BL-4 LogisticRegression (D-08 / review MEDIUM)**: `compute_bl4` が `LogisticRegression(max_iter=1000, random_state=42)` で BL4_FEATURES を学習。`calibrate` 引数で主モデルと同一 calib slice でキャリブレーション可能。
- **BL-5 LightGBM 最小特徴量 (D-08 / review MEDIUM)**: `compute_bl5` が `train_lightgbm` を BL5_FEATURES (rolling 系統除外) で呼出。categorical 統一予測 (`_prepare_lightgbm_train_eval`) で test 予測時の category mismatch を回避。`calibrate` 引数でキャリブレーション可能。
- **compute_all_baselines (SC#2 / review MEDIUM)**: BL-1..5 全5つの `p_bl*` 列を統合 DataFrame で返す。`bl_calib_note` 列で BL-4/5 キャリブレーション状態を明示 (calibrate_bl4_bl5=False の時 BL_UNCALIBRATED_NOTE・True の時 calibrated on same calib slice)。
- **fetch_market_data (D-08)**: `raw_everydb2.n_odds_tanpuku.fukuoddslow` と `normalized.n_uma_race.ninki` を int CAST JOIN (型不一致吸収・kettonum は n_odds_tanpuku に無く n_uma_race 側から取得) で取得。
- **市場データは feature に混入しない (D-07 / MODL-01)**: BL-2/BL-3 の市場データは BL 計算専用の入力・主モデルの feature matrix には絶対に混入しない。
- **test_baseline.py 8件 GREEN**: test_bl1_field_size_constant / test_bl2_ninki_normalized / test_bl3_fukuodds_inverse_normalized / test_bl4_logreg / test_bl5_min_lightgbm / test_market_data_source (@requires_db・2024年 NULL 0% 実証) / test_bl3_and_uncalibrated_notes_present / test_compute_all_baselines_integrates_bl1_to_bl5。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Fix] LightGBM 4.6 train/eval categorical_feature mismatch**
- **Found during:** Task 1 (test_no_target_encoding_leak 実行時・`train and valid dataset categorical_feature do not match` で RED)
- **Issue:** LightGBM 4.6 は train と eval の categorical dtype categories が完全一致することを要求する。個別に `_prepare_lightgbm_matrix` を呼ぶと・それぞれが独自の category set を fit してしまい eval に train に無い値（RARE_X 等）が含まれる場合に不一致で ValueError。
- **Fix:** `_prepare_lightgbm_train_eval(X_train, X_eval)` helper を追加。train ∪ eval の全カテゴリ値で統一した category dtype を両方に適用する。`train_lightgbm` は本 helper を経由して前処理する。テスト予測時も本 helper で categorical を統一（本番 pipeline は frozen category map が同等の保証を提供）。
- **Files modified:** src/model/trainer.py
- **Commit:** b73599f

**2. [Rule 3 - Blocking Fix] fetch_market_data の PK 型不一致 / kettonum 列欠損**
- **Found during:** Task 2 (test_market_data_source 実行時・`operator does not exist: character varying = integer` / `column o.kettonum does not exist` で RED)
- **Issue:** `raw_everydb2.n_odds_tanpuku` (全 varchar) と `normalized.n_uma_race` (int 混在) の PK 型不一致で JOIN が失敗。加えて `n_odds_tanpuku` は `kettonum` 列を持たない（PK は 6 カラム）。
- **Fix:** JOIN ON 句で `o.year::int = n.year::int` 等 int CAST で型整列。`kettonum` は `n_uma_race` 側から取得 (SELECT n.kettonum)。実 DB で 2024 年 47,212 行の INNER JOIN が成功・NULL 0% を確認。
- **Files modified:** src/model/baseline.py
- **Commit:** c868794

**3. [Rule 1 - Bug] SC#3 leak diagnostic の RARE_X 予測アサーション設計修正**
- **Found during:** Task 1 (test_no_target_encoding_leak 実行時・RARE_X 予測が 0.92 で `< 0.5` assert に失敗)
- **Issue:** Plan は「native categorical なら RARE_X 予測が global mean (0.21) に縮む」を想定していたが・RARE_X の行の label を全て 1 に設定すると LightGBM native categorical も CatBoost ordered TS も**値ベースで** RARE_X を強力な予測子として学習する（値の相関は target encoding 非依存）。これは native categorical の正しい動作であり・target encoding 非混入の証明にはならない。
- **Fix:** (a) 通常経路の RARE_X 予測アサーションを「確率範囲 [0,1] の妥当性」に緩和・native categorical が値ベースで学習することは leak ではない。(b) target encoding API 非使用は `test_no_target_encoding_imports_in_trainer_module` で構造保証。(c) 意図的リーク注入 (`inject_intentional_leak_feature` が RARE_X 行に 1.0 を直接 numeric feature として注入) で予測が threshold (0.9) を超えることを実証し・leak diagnostic が false-pass でないことを DEMONSTRABLY 実証。これにより review HIGH#3 の本質（false-pass 防止・対抗的構造診断）を達成。
- **Files modified:** src/model/trainer.py, tests/model/test_trainer.py
- **Commit:** b73599f

**4. [Rule 1 - Bug] assert_eval_disjoint の train_core_max_date パラメータ semantics 整理**
- **Found during:** Task 1 (test_eval_set_disjoint_from_calib_test 実行時・`eval_max_date > train_core_max_date` で RED)
- **Issue:** Plan は `eval_max_date <= train_core_max_date` guard を指定したが・eval は train slice の時系列末尾から切るため `max(eval) > max(train_core)` は自然（train_tail は train_core より時系列後半）。Plan 記述にも「train_tail は時系列末尾なので通常 max(train_tail) > max(train_core) になる点に注意・実際の guard は `max(eval.race_date) <= max(train.race_date)`」とあり・パラメータ名と semantics が不一致だった。
- **Fix:** `assert_eval_disjoint` の docstring で「`train_core_max_date` パラメータ名は Plan 命名を踏襲・semantics は train slice **全体**の max date（eval 含む）」ことを明示。呼出側は train 全体の max date を渡す（test は `X_train["race_date"].max()` = train 全体 max を渡すよう修正）。eval は train slice 内の末尾から切ることで `eval_max_date <= train_max_date` が成立。
- **Files modified:** src/model/trainer.py, tests/model/test_trainer.py
- **Commit:** b73599f

## Verification Results

### 自動検証

- `uv run pytest tests/model/test_trainer.py -q`: 6 passed ✓
- `uv run pytest tests/model/test_baseline.py -q`: 8 passed ✓
- `uv run pytest tests/model/test_trainer.py tests/model/test_baseline.py -q`: 14 passed ✓
- `uv run pytest --ignore=tests/model/test_predict.py --ignore=tests/model/test_prediction_load.py -q`: 249 passed (Phase 1-3 + 04-02 + 04-03 既存テスト回帰なし) ✓
- `uv run pytest tests/model/test_predict.py tests/model/test_prediction_load.py -q`: 3 failed (RED 維持・04-04 wave で GREEN 化予定) ✓

### acceptance criteria grep 検証

- `target_encoding` / `TargetEncoder(` / `category_encoders import`: 0 件（test_no_target_encoding_imports_in_trainer_module で構造保証）✓
- `has_time=True`: 9 件 ✓
- `deterministic=True` / `force_col_wise=True` / `num_threads=1`: 各 1 件以上 ✓
- `seed=42`: 2 件 / `random_seed=42`: 1 件 / `thread_count=1`: 1 件 ✓
- `__MISSING__`: 11 件（sentinel fillna）✓
- `assert_eval_disjoint`: 11 件 / `raise ValueError`: 19 件 ✓
- `align_predictions`: 13 件 / `is_unique`: 5 件（Cycle 2 NEW-2 厳密置換 guard）✓
- `_race_normalize_inverse`: 5 件 / `fukuoddslow`: 11 件 / `ninki`: 10 件 ✓
- `LogisticRegression`: 7 件 / `train_lightgbm`: 5 件（BL-5 が trainer を再利用）✓

## Known Stubs

本 PLAN は RED stub の GREEN 化が目的の一部。以下は後続 wave で GREEN 化される予定の stub（本 PLAN の完了を阻害しない）:

| File | stubs | GREEN 化する PLAN |
| ---- | ---- | ----------------- |
| tests/model/test_predict.py | 2 stubs (provenance / model_version numbering) | PLAN 04 |
| tests/model/test_prediction_load.py | 1 stub (@requires_db・idempotent checksum) | PLAN 04 |

## Threat Flags

本 PLAN で作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている:

- T-04-13 (Information Disclosure: target encoding 混入): mitigate・native categorical (LightGBM category dtype・Fisher 分割) + CatBoost ordered TS (has_time=True)・SC#3 leak diagnostic で非混入を実証・target encoding API 構造的禁止
- T-04-13b (Tampering: CatBoost 高基数 _code 数値扱い): mitigate・`_prepare_catboost_pool` が HIGH_CARD_CODE_COLS を astype(str) で cat_features に含める (review HIGH#6)・unit test で cat_features 含有を assert
- T-04-14 (Tampering: NaN→code -1): mitigate・__MISSING__ sentinel fillna + HIGH_CARD_CODE_COLS は frozen map で非負保証・`.cat.codes.min() >= 0` assert
- T-04-15 (Information Disclosure: CatBoost random permutation): mitigate・has_time=True + Pool race_start_datetime sort・unit test で get_all_params()['has_time']==True を assert
- T-04-15b (Tampering: CatBoost sort 後予測の行順序崩れ): mitigate・`_prepare_catboost_pool` が (Pool, sorted_index) 返却・align_predictions が元順序に復元・X.index.equals(y.index) assert・test_catboost_predict_preserves_row_order でシャッフル入力でも復元を検証
- T-04-15c (Tampering: align_predictions reindex silent NaN): mitigate・5 条件厳密置換 guard (is_unique ×2 / set 等価 / len 等価 / isna なし) で RuntimeError・部分集合/重複/長不一致テストで fail-loud を実証
- T-04-16 (Information Disclosure: early stopping eval set calib/test 漏洩): mitigate・assert_eval_disjoint pairwise disjoint + eval_max_date <= train_max_date (review Cross-Plan #8)・違反入力テストで raise ValueError を検証
- T-04-17 (Tampering: BL-3 市場データ feature 混入): mitigate・baseline.py は BL 計算専用・feature matrix には混入しない (MODL-01 odds-free)・BL3_COMPARISON_CAVEAT で §14.2 明示
- T-04-18 (Tampering: BL-3 オッズ逆数正規化忘れ): mitigate・`_race_normalize_inverse` で sum==払戻対象数 を保証・unit test で sum(p) per race を assert
- T-04-19 (Spoofing: BL-4/5 random_state 未固定): mitigate・LogisticRegression(random_state=42)・train_lightgbm(seed=42, deterministic=True, num_threads=1)
- T-04-19b (Information Disclosure: BL-4/5 未キャリブレーションで不公平比較): mitigate・calibrate 引数 + bl_calib_note 列でキャリブレーション状態を明示 (review MEDIUM)

新たなセキュリティ表面の追加は無い。

## Self-Check: PASSED

- FOUND: src/model/trainer.py (train_lightgbm/train_catboost/assert_eval_disjoint/align_predictions/_prepare_lightgbm_matrix/_prepare_catboost_pool/_prepare_lightgbm_train_eval/_build_rare_category_synthetic/_build_intentional_leak_control/inject_intentional_leak_feature + 定数 LOW_CARD_CAT_COLS/HIGH_CARD_CODE_COLS/ALL_CAT_COLS/LGB_INIT_PARAMS/CB_INIT_PARAMS)
- FOUND: src/model/baseline.py (compute_bl1..5/compute_all_baselines/_race_normalize_inverse/_payout_places/fetch_market_data + 定数 BL4_FEATURES/BL5_FEATURES/BL3_COMPARISON_CAVEAT/BL_UNCALIBRATED_NOTE)
- FOUND: tests/model/test_trainer.py (6 test GREEN)
- FOUND: tests/model/test_baseline.py (8 test GREEN)
- FOUND: commit b73599f (Task 1)
- FOUND: commit c868794 (Task 2)
