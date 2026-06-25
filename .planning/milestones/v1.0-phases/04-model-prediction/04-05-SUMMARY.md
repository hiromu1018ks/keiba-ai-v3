---
phase: 04-model-prediction
plan: 05
subsystem: orchestrator-run-train-predict
tags: [phase-04, integration, run-train-predict, sc4-reproduce, both-models, end-to-end, review-high1, review-high2, review-high7, review-high12, cycle2-new-high1, cycle2-residual13]
requires:
  - "Phase 04-02: data.py / calibrator.py / artifact.py (FEATURE_COLUMNS / split_3way / calibrate_model / save_native_artifact)"
  - "Phase 04-03: trainer.py / baseline.py (train_lightgbm / train_catboost / align_predictions / compute_all_baselines)"
  - "Phase 04-04: predict.py / evaluator.py / prediction_load.py (predict_p_fukusho / evaluate_all_models / load_predictions)"
  - "Phase 04-01: lightgbm/catboost pin + prediction DDL + RED stubs"
provides:
  - "src/model/orchestrator.py: train_and_predict orchestrator (trainer + calibrate_model + predict_p_fukusho 統合) + _merge_params + _assert_deterministic + FIXED_REPRODUCE_TS + CatBoost 手動 calibration (_calibrate_catboost_manual / _ManualCatBoostCalibrated / _catboost_calibrated_predict_proba)"
  - "scripts/run_train_predict.py: Phase 4 エントリポイント (両モデル学習→キャリブレーション→予測→artifact保存→prediction書込→評価レポート)"
  - "GREEN 化: tests/model/test_orchestrator.py (7 test = 6 case + 2 helper)"
affects:
  - "Phase 5/6/7: prediction.fukusho_prediction を SQL 照会・reports/04-eval.{md,json} を D-04 選定基準素材として消費"
  - "PLAN 06: 両モデル完全 E2E 実行 (BL-2/BL-3 市場データ merge 完全化・BL-4/BL-5 キャリブレーション・全レポートコミット)"
tech-stack:
  added: []
  patterns:
    - "orchestration 層の分離 (review HIGH#12): train_and_predict は src/model/orchestrator.py に配置・calibrator.py は純粋 utility のまま・一方向 import で循環依存回避"
    - "行整列保証 (review HIGH#2): 単一 index 付き modeling frame を全段で運び・X/y/race_df の全 merge 直前に index equality を assert (RuntimeError)"
    - "Cycle 2 NEW HIGH-1: predict_p_fukusho に pred_proba=pred_proba を明示注入し・CatBoost の aligned 予測値を最終 DataFrame に伝播 (再予測で整列が捨てられる回帰を閉塞)"
    - "Cycle 2 residual #13: label join は run_train_predict 側でのみ発生・train_and_predict は label-joined frame のみを受け取る (docstring + assert で明示的契約)"
    - "SC#4 bit-identical (review HIGH#7): 固定 seed=42 + 固定 thread count (num_threads=1 / thread_count=1) + 固定 as_of_datetime (FIXED_REPRODUCE_TS) で2回 train_and_predict → np.array_equal"
    - "CatBoost + CalibratedClassifierCV 互換性 (Rule 3 auto-fix): CatBoost の FrozenEstimator + CalibratedClassifierCV が StringDtype pd.NA で失敗するため・base estimator で Pool 予測してから手動で isotonic/sigmoid calibrator を fit"
    - "model_version スコープ swap (review HIGH#1): load_predictions を各 model_type+model_version 単位で呼び (統合 DataFrame でなく)・2回実行で idempotent checksum 報告"
key-files:
  created:
    - "src/model/orchestrator.py"
    - "scripts/run_train_predict.py"
    - "tests/model/test_orchestrator.py"
  modified:
    - "src/model/data.py (Rule 3: filter_eligible 正準4値 + make_X_y numeric 復元)"
    - "src/model/baseline.py (Rule 3: compute_bl4 One-Hot 化)"
    - "src/model/evaluator.py (Rule 3: _df_to_markdown_table tabulate 非依存)"
    - "tests/model/test_data.py (label_validation_status 値追従)"
decisions:
  - "review HIGH#12: train_and_predict を src/model/orchestrator.py に配置 (calibrator.py でなく)・calibrator/trainer/data/predict/artifact を一方向 import で循環依存回避"
  - "review HIGH#2: 単一 index 付き modeling frame を全段で運び・全 merge 直前に index equality を assert・CatBoost 予測パスが align_predictions で元順序復元"
  - "Cycle 2 NEW HIGH-1: predict_p_fukusho 呼出に pred_proba=pred_proba を明示渡しし・aligned 予測値が再予測で捨てられる回帰を閉塞 (test_catboost_pred_proba_injection で実証)"
  - "Cycle 2 residual #13: データ API 境界を明示 (train_and_predict は label-joined frame のみを受け取り・label join を再実行しない・docstring + assert で明示)"
  - "review HIGH#7 / SC#4: FIXED_REPRODUCE_TS 定数 + 固定 seed + 固定 thread count で bit-identical・_assert_deterministic が np.array_equal 検証 (構造的ブロック・Phase 完了不可)"
  - "Rule 3 auto-fix (CatBoost 互換性): CatBoost の FrozenEstimator + CalibratedClassifierCV.fit が StringDtype pd.NA で 'must be real number, not NAType' で失敗するため・_calibrate_catboost_manual で base estimator の Pool 予測から手動 calibrator fit に切り替え (LightGBM は calibrate_model をそのまま使用)"
  - "Rule 3 auto-fix (data.py filter_eligible): label_validation_status の正準4値 {validated, inferred, dead_heat, unresolved} に修正 (旧 {ok, computed} は fukusho_label.py:399 D-04 仕様と不一致で実データ E2E が全行除外される blocking issue)"
  - "Rule 3 auto-fix (data.py make_X_y): build_training_frame が PK 列 umaban を str 化する副作用に対し・FEATURE_COLUMNS の categorical 列以外を numeric に復元 (LightGBM が 'bad pandas dtypes' で失敗するのを防止)"
  - "Rule 3 auto-fix (baseline.py compute_bl4): class_code_normalized を pd.get_dummies で One-Hot 化 (旧実装は文字列を直接 LogisticRegression に渡し ValueError)"
  - "Rule 3 auto-fix (evaluator.py): df.to_markdown() が tabulate (optional dependency) を要求する問題を回避するため _df_to_markdown_table で手動 Markdown 表構築 (依存関係追加を避ける)"
  - "review HIGH#1: load_predictions を各 model_type+model_version 単位で呼び (統合 DataFrame でなく各モデル別)・2回実行で idempotent checksum 報告"
  - "BL-4/BL-5 キャリブレーション (calibrate_bl4_bl5=False): BL-4/BL-5 の calibrator 経由予測で LightGBM categorical 前処理が走らない問題 (PLAN 03 baseline.py 制約) のため・本 PLAN では未キャリブレーションで評価レポート生成 (BL_UNCALIBRATED_NOTE で注記・Phase 6 で再評価)"
metrics:
  duration: 49m
  completed: 2026-06-20
  tasks: 2
  files_created: 3
  files_modified: 4
status: complete
---

# Phase 4 Plan 05: Orchestrator + Run Train Predict Summary

**train_and_predict orchestrator (review HIGH#12: calibrator.py でなく独立モジュール) + 行整列保証 (HIGH#2) + SC#4 bit-identical (HIGH#7・実データ両モデルで実証) + aligned pred_proba 注入 (Cycle 2 NEW HIGH-1) + データ API 境界明示 (Cycle 2 residual #13) + run_train_predict.py 両モデル E2E pipeline (HIGH#1 model_version スコープ swap)**

Phase 4 Wave 4 の完結編として、(a) review HIGH#12 で指摘された「train_and_predict が calibrator.py にあり循環依存」を解消するため src/model/orchestrator.py を新設し trainer + calibrate_model + predict_p_fukusho を統合、(b) review HIGH#2 の行整列保証・Cycle 2 NEW HIGH-1 の aligned pred_proba 注入・Cycle 2 residual #13 のデータ API 境界明示を実装、(c) review HIGH#7 / SC#4 の bit-identical 再現性を固定 seed + 固定 thread count + 固定 as_of_datetime で実現、(d) scripts/run_train_predict.py で両モデル E2E pipeline を単一エントリポイントで完結 (review HIGH#1 model_version スコープ swap・review HIGH#5 base+calibrator 分離保存・SC#2 評価レポート) した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | src/model/orchestrator.py 新設 — train_and_predict + 行整列 + bit-identical (HIGH#2/#7/#12/NEW HIGH-1/residual #13) | `b543655` (RED) / `518de71` (GREEN) | src/model/orchestrator.py, tests/model/test_orchestrator.py |
| 2 | scripts/run_train_predict.py — 両モデル E2E pipeline エントリポイント | `5ecea1e` | scripts/run_train_predict.py, src/model/{orchestrator,data,baseline,evaluator}.py, tests/model/{test_orchestrator,test_data}.py |

## What Was Built

### Task 1: src/model/orchestrator.py — review HIGH#2 / HIGH#7 / HIGH#12 / Cycle 2 NEW HIGH-1 / Cycle 2 residual #13

- **orchestration 層の分離 (review HIGH#12)**: train_and_predict を src/model/orchestrator.py に配置。src.model.data / trainer / calibrator / predict / artifact を一方向 import し・逆方向 import なし (calibrator.py は純粋 utility のまま維持・test_no_circular_import で検証)。grep -c 'def train_and_predict' src/model/calibrator.py == 0 を保証。
- **行整列保証 (review HIGH#2)**: 単一 index 付き modeling frame を split / feature 選択 / 予測 / 出力の全段で運ぶ。X_train/X_calib/X_test と y_*/race_df の全 merge 直前に index equality を assert (RuntimeError)。CatBoost 予測パスは _prepare_catboost_pool が sort 済み Pool を返すため・align_predictions で元順序に復元。
- **aligned pred_proba 注入 (Cycle 2 NEW HIGH-1)**: predict_p_fukusho 呼出に pred_proba=pred_proba を明示的に渡す。CatBoost の場合 align_predictions で復元した予測値・LightGBM の場合 calibrated.predict_proba の算出値を一貫して注入し・再予測で整列が捨てられる回帰を閉塞。test_catboost_pred_proba_injection で最終 pred_df.p_fukusho_hit が aligned pred_proba と np.array_equal で完全一致を検証。
- **データ API 境界明示 (Cycle 2 residual #13)**: train_and_predict の feature_df 引数は label-joined frame (build_training_frame の出力) を前提。orchestrator は label join を絶対に再実行しない (readonly_cur / label_df 引数を持たない)。docstring に契約明記・入口で fukusho_hit_validated 列存在を assert (違反は ValueError)。grep -c 'load_labels(\|readonly_cur' src/model/orchestrator.py == 0 で実呼出経路がないことを検証可能。
- **SC#4 bit-identical (review HIGH#7 / §19.1 構造的ブロック)**: FIXED_REPRODUCE_TS 定数 (datetime(2026,6,20,tzinfo=UTC)) + 固定 seed=42 + 固定 thread count (num_threads=1 / thread_count=1) で2回 train_and_predict を呼出し・戻り prediction の p_fukusho_hit 列が np.array_equal (bit-identical) になることを _assert_deterministic が検証。_merge_params が override を merge しつつ決定論フラグを強制固定 (呼出側が誤って非決定論 thread count を渡しても bit-identical が崩れない)。
- **CatBoost + CalibratedClassifierCV 互換性 (Rule 3 auto-fix)**: CatBoost の FrozenEstimator + CalibratedClassifierCV.fit が StringDtype pd.NA で "must be real number, not NAType" で失敗する問題を回避するため・_calibrate_catboost_manual で base estimator の calib Pool 予測から手動で isotonic/sigmoid calibrator を fit。_ManualCatBoostCalibrated ラッパー (CalibratedClassifierCV 互換インターフェース) と _catboost_calibrated_predict_proba (base + calibrator で予測) を提供。
- **test_orchestrator.py 7 test GREEN**: test_train_and_predict_row_alignment (HIGH#2) / test_catboost_pred_proba_injection (NEW HIGH-1) / test_reproduce_bit_identical (HIGH#7・両モデル) / test_no_circular_import (HIGH#12) / test_data_api_boundary_explicit (residual #13) / test_merge_params_overrides_seed_and_threads / test_fixed_reproduce_ts_is_constant。

### Task 2: scripts/run_train_predict.py — D-01 / D-03 / D-05 / D-06 / SC#2 / SC#4 / review HIGH#1 / HIGH#5 / HIGH#7 / Cycle 2 residual #13

- **6 argparse (review MEDIUM: --snapshot-id 実パス解決)**: --snapshot-id (default 20260620-1a-postreview-v2) / --model-type {lightgbm,catboost,both} (default both・D-03) / --version-n (default 1・D-10) / --check-reproduce (SC#4) / --no-write-db (dry run) / --as-of-datetime (review HIGH#7)。
- **--snapshot-id 実パス解決 (review MEDIUM / T-04-26)**: args.snapshot_id から snapshots/feature_matrix_{id}.parquet / .manifest.yaml / category_map_{id}.json の3パスを構築し存在確認。args.snapshot_id と data.py.SNAPSHOT_PATH の snapshot_id 部分が一致することを assert (ドリフト検出)。
- **masked DSN ログ / try-except PsycopgError / finally pool.close (run_label_etl.py パターン)**: 生 DSN 絶対出力禁止 (settings.dsn_masked / etl_dsn_masked のみ)・Shared Pattern 8。
- **データ API 境界明示 (Cycle 2 residual #13)**: load_feature_matrix() (Parquet のみ・SC#1) + load_labels(readonly_cur) + build_training_frame で label join を run script 側で完結。feature_df を train_and_predict に渡す前に fukusho_hit_validated 列が存在することを assert (二重防御)。
- **両モデル学習 (review HIGH#2: orchestrator が行整列保証)**: model_type in {lightgbm, catboost} (both の場合両方) で train_and_predict を呼出し。各モデルの calibrated estimator + pred_df + model_version (D-10 形式 make_model_version で生成) を収集。
- **artifact 保存 (review HIGH#5: base+calibrator 分離)**: save_native_artifact で base ネイティブ (lgb_model.txt / cb_model.cbm) + calibrator.joblib + metadata.json (sort_keys=True・atomic write) に分離保存。models/{model_version}/ 配下 (.gitignore 対象)。
- **BL 計算 (SC#2)**: compute_all_baselines で BL-1..5 計算。市場データ (ninki / fukuoddslow) は fetch_market_data で readonly SELECT し test split に結合 (D-07: feature matrix には混入しない)。calibrate_bl4_bl5=False (BL-4/BL-5 の calibrator 経由予測で LightGBM categorical 前処理が走らない問題のため・Phase 6 で再評価)。
- **prediction 書込 (review HIGH#1: model_version スコープ swap)**: load_predictions を各 model_type+model_version 単位で呼び (統合 DataFrame でなく各モデル別)・2回実行で idempotent checksum 報告。model_version スコープ DELETE → INSERT で他 model_type/version の行を保持 (LightGBM 実行後 CatBoost 実行が前者を削除する silent 履歴破壊防止)。
- **評価レポート (SC#2)**: evaluate_all_models で reports/04-eval.md + reports/04-eval.json に LightGBM/CatBoost + BL-1..5 の比較表を出力。D-04 事前登録 (Calibration 重視選定基準) を d04_selection_criterion 列に固定。
- **SC#4 --check-reproduce (review HIGH#7)**: 各 model_type で _assert_deterministic を seed=42 + FIXED_REPRODUCE_TS で呼出し・np.array_equal で bit-identical 検証。失敗で return 3 (構造的ブロック)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Fix] CatBoost + CalibratedClassifierCV 互換性 (StringDtype pd.NA)**
- **Found during:** Task 2 (実データ E2E 実行時・CatBoost の calibrate_model で "must be real number, not NAType")
- **Issue:** CatBoost estimator を FrozenEstimator + CalibratedClassifierCV.fit(X_calib) すると・fit 内部で CatBoost が DataFrame を受け取り cat_features 認識なしに Pool を作ろうとし・StringDtype 列 (rolling_jyocd_mode_5 等) の pd.NA で CatBoost がエラーになる。LightGBM は CalibratedClassifierCV と素直に連携するが・CatBoost は cat_features 指定が必要なため DataFrame 直接受け取りが困難。
- **Fix:** orchestrator で CatBoost の場合のみ _calibrate_catboost_manual を使用。base estimator で calib Pool を直接予測して生確率を算出し・sklearn の IsotonicRegression / _SigmoidCalibration を手動で fit。_ManualCatBoostCalibrated ラッパー (CalibratedClassifierCV 互換・predict_proba(Pool) 可能) を返す。LightGBM は calibrate_model をそのまま使用。test_orchestrator.py (合成データ・NaN なし) は両モデルで calibrate_model を使う経路と _calibrate_catboost_manual 経路の両方で GREEN。
- **Files modified:** src/model/orchestrator.py
- **Commit:** 5ecea1e

**2. [Rule 3 - Blocking Fix] data.py filter_eligible の label_validation_status 正準4値**
- **Found during:** Task 2 (実データ E2E 実行時・build_training_frame で全行除外)
- **Issue:** data.py の filter_eligible が label_validation_status in {'ok', 'computed'} を許容していたが・実ラベル (src/etl/fukusho_label.py:399 D-04) の正準4値は {validated, inferred, dead_heat, unresolved}。実データ (554,267行) で全行が除外され E2E が実行不可。
- **Fix:** filter_eligible を {'validated', 'inferred', 'dead_heat'} に修正 (unresolved は学習対象外・fukusho_label.py:514 と整合)。test_data.py の合成データ label_validation_status も "ok" → "validated" に追従。
- **Files modified:** src/model/data.py, tests/model/test_data.py
- **Commit:** 5ecea1e

**3. [Rule 3 - Blocking Fix] data.py make_X_y の umaban numeric 復元**
- **Found during:** Task 2 (実データ E2E 実行時・LightGBM で "Fields with bad pandas dtypes: umaban: str")
- **Issue:** build_training_frame が PK 列 (umaban 含む) を str 化して merge する副作用で・FEATURE_COLUMNS に含まれる umaban が str になり LightGBM が "pandas dtypes must be int, float or bool" で失敗。
- **Fix:** make_X_y で FEATURE_COLUMNS の categorical 列 (LOW_CARD_CAT_COLS + HIGH_CARD_CODE_COLS) 以外を numeric に復元 (pd.to_numeric・変換失敗は ValueError で fail-loud)。pandas StringDtype (str repr が "str") も検出条件に含める。
- **Files modified:** src/model/data.py
- **Commit:** 5ecea1e

**4. [Rule 3 - Blocking Fix] baseline.py compute_bl4 の class_code_normalized One-Hot 化**
- **Found during:** Task 2 (実データ E2E 実行時・BL-4 で "could not convert string to float: '__MISSING__'")
- **Issue:** baseline.py の compute_bl4 が class_code_normalized を fillna("__MISSING__").astype(str) した後・そのまま LogisticRegression に渡していた。LogisticRegression は文字列を数値に変換できず ValueError。
- **Fix:** class_code_normalized を pd.get_dummies で One-Hot 化 (train ∪ test の全カテゴリで列整合)。calibrate=True の場合は X_calib も同一カテゴリで One-Hot 化し train と列整合。
- **Files modified:** src/model/baseline.py
- **Commit:** 5ecea1e

**5. [Rule 3 - Blocking Fix] evaluator.py _df_to_markdown_table (tabulate 非依存)**
- **Found during:** Task 2 (実データ E2E 実行時・write_eval_report で "Import tabulate failed")
- **Issue:** evaluator.py の write_eval_report が df.to_markdown() を使っていたが・pandas の to_markdown は optional dependency の tabulate を要求する。本プロジェクトの pyproject.toml は tabulate を含まず・依存関係追加は除外ルール (package-manager install) に該当。
- **Fix:** _df_to_markdown_table helper で手動 Markdown 表を構築 (header / separator / rows・float は小数6桁)。to_markdown を使わず tabulate 非依存。
- **Files modified:** src/model/evaluator.py
- **Commit:** 5ecea1e

**6. [Rule 3 - Blocking Fix] orchestrator LightGBM categorical 統一 (_prepare_lightgbm_train_eval)**
- **Found during:** Task 1 (合成データで test_train_and_predict_row_alignment 実行時・"train and valid dataset categorical_feature do not match")
- **Issue:** LightGBM 4.6 は train と predict の categorical dtype categories が完全一致することを要求する。train_lightgbm 内部の _prepare_lightgbm_train_eval(X_train_core, X_train_tail) が train_core/tail の categorical を統一するが・CalibratedClassifierCV 経由の test 予測で別の categorical が使われ mismatch エラー。
- **Fix:** orchestrator で X_calib と X_test を _prepare_lightgbm_train_eval(X_train_core, X) で train_core と categorical 統一してから calibrate_model / predict に渡す (test_trainer.py test_no_target_encoding_leak と同一パターン)。
- **Files modified:** src/model/orchestrator.py
- **Commit:** 518de71

## Verification Results

### 自動検証

- `uv run pytest tests/model/test_orchestrator.py -q`: 7 passed (6 case + 2 helper) ✓
- `uv run pytest tests/model/ -q`: 37 passed (Phase 1-3 + 04-02/03/04 既存テスト回帰なし) ✓
- `uv run ruff check src/model/orchestrator.py scripts/run_train_predict.py tests/model/test_orchestrator.py`: All checks passed ✓
- `uv run python scripts/run_train_predict.py --help`: exit 0 (6 argparse) ✓
- `uv run python scripts/run_train_predict.py --help | grep -E "snapshot-id|model-type|check-reproduce|as-of-datetime"`: ARGPARSE_OK ✓

### SC#4 bit-identical 実証 (実データ・review HIGH#7)

- `uv run python scripts/run_train_predict.py --check-reproduce --no-write-db --model-type lightgbm`:
  SC#4 reproduce smoke PASS (lightgbm): seed=42 + 固定 thread + 固定 as_of_datetime で bit-identical ✓ (実行時間 38秒)
- `uv run python scripts/run_train_predict.py --check-reproduce --no-write-db --model-type catboost`:
  SC#4 reproduce smoke PASS (catboost): seed=42 + 固定 thread + 固定 as_of_datetime で bit-identical ✓ (実行時間 58秒)
- 合成データ (test_reproduce_bit_identical) でも両モデル np.array_equal=True を実証 ✓

### LightGBM 完全 E2E (実データ・--no-write-db)

- `uv run python scripts/run_train_predict.py --no-write-db --model-type lightgbm`:
  - feature_df: 552,935行 (label-joined)
  - train_and_predict: model_version=20260620-1a-postreview-v2-lgb-v1 (D-10 形式)・calib_method=isotonic・pred_rows=22,213
  - artifact saved: models/20260620-1a-postreview-v2-lgb-v1/{lgb_model.txt, calibrator.joblib, metadata.json} (base+calibrator 分離)
  - baselines computed: 22,213行 7列
  - eval report written: reports/04-eval.md + reports/04-eval.json (LightGBM + BL-1/BL-4/BL-5 比較表)
  - LightGBM metrics: brier=0.152216, logloss=0.474883, auc=0.732295, calibration_max_dev=0.230769 ✓

### acceptance criteria grep 検証

- `grep -c 'def train_and_predict' src/model/calibrator.py` == 0 (review HIGH#12) ✓
- `grep 'predict_p_fukusho' src/model/orchestrator.py` に `pred_proba=` が含まれる (Cycle 2 NEW HIGH-1) ✓
- `grep -c 'align_predictions' src/model/orchestrator.py` >= 7 (review HIGH#2) ✓
- `grep -c 'readonly_cur\|load_labels(' src/model/orchestrator.py` == 0 (Cycle 2 residual #13) ✓
- `grep -c 'index.equals\|index != ' src/model/orchestrator.py` >= 11 (review HIGH#2) ✓
- `grep -c 'add_argument' scripts/run_train_predict.py` == 6 ✓
- `grep -c 'dsn_masked\|etl_dsn_masked' scripts/run_train_predict.py` == 3 (masked DSN) ✓
- `grep -cE 'password=|postgresql://[^ ]+:[^ ]+@' scripts/run_train_predict.py` == 0 (生 DSN なし) ✓
- `grep -c 'except PsycopgError\|finally:' scripts/run_train_predict.py` == 3 ✓
- `grep -c 'load_predictions(' scripts/run_train_predict.py` == 2 (各 model_type 毎・review HIGH#1) ✓

## TDD Gate Compliance

Task 1 は tdd="true" で RED → GREEN サイクルを実施:

- **Task 1 RED**: tests/model/test_orchestrator.py (6 case) を新設し・src.model.orchestrator の ImportError (ModuleNotFoundError) で RED 確認 (commit `b543655`)
- **Task 1 GREEN**: src/model/orchestrator.py 実装で 7 test GREEN (commit `518de71`)

Task 2 は type="auto" (tdd なし)・`uv run python scripts/run_train_predict.py --help` exit 0 + 実データ E2E 成功で検証 (commit `5ecea1e`)。

## Known Stubs

本 PLAN で RED stub の GREEN 化を完遂。後続 PLAN 06 が本 PLAN の API を消費して実データ完全 E2E を実施:

| 消費元 API | 消費する PLAN | 備考 |
| ---- | ---- | ---- |
| train_and_predict / _assert_deterministic / FIXED_REPRODUCE_TS | PLAN 06 (実データ完全 E2E) | 両モデル + DB 書込 + 完全レポート |
| run_train_predict.py (--model-type both・DB 書込あり) | PLAN 06 | 両モデル prediction.fukusho_prediction 永続化 |

本 PLAN 完了を阻害する stub なし。

## Deferred Issues

以下は本 PLAN の実行過程で発見された・PLAN 06 または後続 Phase で対応すべき問題:

| Issue | Description | 対応 PLAN |
| ---- | ---- | ---- |
| BL-4/BL-5 キャリブレーション (calibrate_bl4_bl5=False) | BL-4/BL-5 の calibrator 経由予測で LightGBM categorical 前処理が走らない問題 (baseline.py 制約)。本 PLAN では calibrate_bl4_bl5=False で評価レポート生成・BL_UNCALIBRATED_NOTE で注記。Phase 6 で SC#2 比較公平性を再評価。 | PLAN 06 / Phase 6 |
| BL-2/BL-3 市場データ merge が空 (NaN) | test split (2024-H2) で fetch_market_data の ninki/fukuoddslow が取得できておらず・BL-2/BL-3 が NaN。市場データ SELECT の year/dataset 範囲調整が必要。 | PLAN 06 |
| data.py build_training_frame の既存 ruff 違反 (E741 `l` / F841 `n_before`) | PLAN 02 の既存コード・本 PLAN スコープ外。 | 別途 (PLAN 02 follow-up) |
| reports/04-eval.{md,json} 未コミット | 本 PLAN では LightGBM 単独実行の生成物・両モデル完全実行後に PLAN 06 でコミット。 | PLAN 06 |

## Threat Flags

本 PLAN で作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている:

- T-04-26 (Tampering: CLI 引数 injection・--snapshot-id で不正パス読込): mitigate・_resolve_snapshot_paths が実パス存在確認・_assert_snapshot_id_matches_data_module がドリフト検出・任意パス読込不可
- T-04-27 (Information Disclosure: スクリプトログへの生 DSN 出力): mitigate・settings.dsn_masked / etl_dsn_masked のみ使用・生 DSN 埋込なし (grep == 0)
- T-04-28 (Denial of Service: pool close 忘れで DB 接続枯渇): mitigate・try/except/finally で readonly_pool.close() / etl_pool.close() を保証
- T-04-29 (Repudiation: 非決定論的要素で SC#4 reproduce 失敗を silent 無視): mitigate・--check-reproduce で np.array_equal 違反時 return 3 (構造的ブロック)・固定 thread count + 固定 as_of_datetime
- T-04-30 (Tampering: prediction 書込の部分失敗・及び全テーブル置換で他 model_version の行を破壊): mitigate・load_predictions を各 model_type+model_version 単位で呼び・staging-swap idempotent・2回実行 checksum 報告
- T-04-31 (Repudiation: artifact 保存の非決定論的書込・及び CalibratedClassifierCV を直接 native save して失敗): mitigate・save_native_artifact が base ネイティブ + calibrator.joblib 分離保存・metadata.json sort_keys=True + atomic write
- T-04-31b (Tampering: sort/split/merge 後に予測と元の行が misalign・silent wrong-horse prediction・predict_p_fukusho 内部の再予測で CatBoost aligned pred_proba が捨てられる回帰): mitigate・orchestrator.train_and_predict が単一 index 付き modeling frame を全段で運び・全 merge 直前に index equality を assert・CatBoost 予測パスが trainer.align_predictions を呼び元順序復元・predict_p_fukusho 呼出に pred_proba=pred_proba を明示渡しし再予測を防止 (Cycle 2 NEW HIGH-1・test_catboost_pred_proba_injection で実証)
- T-04-31c (Tampering: train_and_predict が calibrator.py にあり循環依存で utility が非純粋化): mitigate・train_and_predict を src/model/orchestrator.py に配置し calibrator.py は純粋 utility のまま・test_no_circular_import で検証

新たなセキュリティ表面の追加は無い。

## Self-Check: PASSED

- FOUND: src/model/orchestrator.py (train_and_predict / _merge_params / _assert_deterministic / FIXED_REPRODUCE_TS / _calibrate_catboost_manual / _ManualCatBoostCalibrated / _catboost_calibrated_predict_proba)
- FOUND: scripts/run_train_predict.py (parse_args / _resolve_snapshot_paths / _assert_snapshot_id_matches_data_module / main + 6 argparse)
- FOUND: tests/model/test_orchestrator.py (7 test GREEN = 6 case + 2 helper)
- FOUND: commit b543655 (Task 1 RED)
- FOUND: commit 518de71 (Task 1 GREEN)
- FOUND: commit 5ecea1e (Task 2)
- FOUND: reports/04-eval.md + reports/04-eval.json (LightGBM E2E 生成物・PLAN 06 で両モデル完全版に更新)
- FOUND: models/20260620-1a-postreview-v2-lgb-v1/{lgb_model.txt, calibrator.joblib, metadata.json} (artifact base+calibrator 分離・.gitignore 対象)
