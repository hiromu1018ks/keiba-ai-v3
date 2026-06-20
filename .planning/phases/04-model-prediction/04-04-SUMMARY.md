---
phase: 04-model-prediction
plan: 04
subsystem: predict-evaluator-prediction-load
tags: [phase-04, predict, evaluator, prediction-load, staging-swap, provenance, sc2-table, model-version, sum-p-diagnostic, binning-contract]
requires:
  - "Phase 04-02: data.py / calibrator.py / artifact.py (load_frozen_maps / FEATURE_COLUMNS / split_3way / fit_prefit_calibrator / _atomic_write_text)"
  - "Phase 04-03: trainer.py / baseline.py (train_lightgbm / train_catboost / align_predictions / compute_all_baselines)"
  - "Phase 04-01: prediction DDL (11カラム PK) + RED stubs"
provides:
  - "src/model/predict.py: predict_p_fukusho / make_model_version / _assert_valid_prediction_df + 定数 PREDICTION_COLUMNS / MODEL_TYPE_TO_SHORT / PK_COLUMNS"
  - "src/model/evaluator.py: compute_metrics / check_sum_p_distribution / build_comparison_table / write_eval_report / evaluate_all_models + 定数 SUM_P_BOUNDS / METRIC_COLUMNS / CALIBRATION_CURVE_BINS/STRATEGY/MIN_BIN_COUNT / BL3_MARKET_REFERENCE_NOTE / BL_UNCALIBRATED_NOTE / D04_SELECTION_CRITERION_NOTE / SUM_P_DIAGNOSTIC_NOTE"
  - "src/db/prediction_load.py: _idempotent_load_prediction / load_predictions / _df_to_prediction_tuples + 定数 _PREDICTION_TABLE / _PK_ORDER_COLUMNS"
  - "GREEN 化: tests/model/test_predict.py (3件) + tests/model/test_prediction_load.py (3件)"
affects:
  - "後続 PLAN 05 (run_train_predict): predict_p_fukusho + prediction_load + evaluate_all_models を統合・学習→予測→永続化→評価パイプラインを構築"
  - "後続 Phase 5/6/7: prediction.fukusho_prediction を SQL 照会・evaluator の reports/04-eval.{md,json} を D-04 選定基準素材として消費"
tech-stack:
  added: []
  patterns:
    - "predict_p_fukusho: calibrated estimator.predict_proba[:,1] → PREDICTION_COLUMNS 順の provenance DataFrame (MODL-01/D-05)"
    - "make_model_version: D-10 完全一致形式 {feature_snapshot_id}-{short}-v{N}・feature_snapshot_id 全体を prefix・二重 postfix 回帰防止 (review HIGH#4 / Cycle 3 NEW-4)"
    - "NEW HIGH-1: pred_proba 注入で CatBoost aligned 予測値を最終 DataFrame に伝播・注入時は再予測せず index 一致を assert・違反は RuntimeError (Cycle 2 NEW HIGH-1・silent wrong-horse prediction 防止)"
    - "model_version スコープ staging-swap: 全テーブル DROP+RENAME でなく model_type+model_version scoped DELETE→INSERT (review HIGH#1/Cross-Plan #3: LightGBM 実行後 CatBoost 実行が前者を削除する silent 履歴破壊を防止)"
    - "Cycle 2 NEW-3: staging→本テーブル INSERT は SELECT * でなく PREDICTION_COLUMNS csv 明示 (将来 DDL 変更で誤列挿入防止・grep == 0)"
    - "psycopg.sql.Identifier/Placeholder で SQL injection 対策 (生文字列埋込なし)"
    - "md5 string_agg checksum で ORDER BY PK 11カラム + WHERE model_version scope・2回実行で bit-identical (idempotent)"
    - "sum(p) を独立二値確率の診断的指標として扱い・§15.2 理論値 (8頭以上 [2.7,3.3]・5-7頭 [1.8,2.2]) を機械検査・fail-loud でなく warning (review MEDIUM)"
    - "calibration curve binning 契約固定 (BINS=10/STRATEGY='uniform'/MIN_BIN_COUNT=30)・run 毎の bin 変更防止 (review MEDIUM)"
    - "reports/04-eval.md + reports/04-eval.json 分離出力・json.dumps(sort_keys=True) + atomic write (review LOW)"
    - "D-04 事前登録: comparison 表の d04_selection_criterion 列で Calibration 重視選定基準を結果前固定 (T-04-24 後知恵すり替え防止)"
key-files:
  created:
    - "src/model/predict.py"
    - "src/model/evaluator.py"
    - "src/db/prediction_load.py"
  modified:
    - "tests/model/test_predict.py"
    - "tests/model/test_prediction_load.py"
decisions:
  - "review HIGH#4 / Cross-Plan #1 / Cycle 3 NEW-4: make_model_version が D-10 例と完全一致 {feature_snapshot_id}-{short}-v{N} を返す (例: 20260620-1a-postreview-v2-lgb-v1)・feature_snapshot_id 全体を prefix・二重 postfix 回帰防止 (旧版 ...-postreview-v2-postreview-v2-lgb-v1 は出力しない)"
  - "Cycle 2 NEW HIGH-1: predict_p_fukusho に pred_proba 引数を追加し・注入時は再予測せず index 一致を assert・CatBoost の align_predictions 出力を orchestrator が同引数で渡すことで行整列が最終 DataFrame に伝播 (silent wrong-horse prediction 回帰閉塞)"
  - "review HIGH#1 / Cross-Plan #3: prediction_load.py が model_version スコープ置換 (DELETE WHERE model_type+model_version → INSERT) を採用・全テーブル DROP+RENAME で他 model/version の行を破壊しない (LightGBM 実行後 CatBoost 実行が前者を削除する silent 履歴破壊防止・§19.1 聖域)"
  - "Cycle 2 NEW-3: staging→本テーブル INSERT は SELECT * でなく PREDICTION_COLUMNS csv 明示・将来 DDL 列追加/順序変更で誤列挿入を防止 (grep -c 'SELECT * FROM prediction.fukusho_prediction_staging' == 0)"
  - "review MEDIUM: evaluator.py が sum(p) を独立二値確率の診断的指標として扱い・SUM_P_DIAGNOSTIC_NOTE で厳密合計制約でない旨を明記・§15.2 理論値違反は warning (fail-loud でなく・hybrid gate D-01/D-02 準拠)"
  - "review MEDIUM: CALIBRATION_CURVE_BINS=10 / STRATEGY='uniform' / MIN_BIN_COUNT=30 を固定値で明示・calibration_curve で使用・run 毎の bin 変更防止 (再現性保証)"
  - "review LOW: write_eval_report が reports/04-eval.md と reports/04-eval.json に分離出力・JSON は json.dumps(sort_keys=True) + artifact.py::_atomic_write_text で byte-reproducible atomic write"
  - "D-04 事前登録 (T-04-24): comparison 表の d04_selection_criterion 列で Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考) を結果前に固定・Phase 6 で最終選定基準として採用 (後知恵すり替え防止)"
  - "T-04-25b: predict_p_fukusho が as_of_datetime 引数を受け取り・reproduce smoke では固定値を渡して bit-identical hash を保証 (揮発性 now() が hash に混入するのを防止)"
  - "Rule 1 auto-fix (test): test_model_version_numbering の二重 suffix 検出 assertion を部分文字列 '-postreview-v2-lgb' から・真の回帰形 '-postreview-v2-postreview-v2-' (snapshot_id version token の2回出現) に修正・正形式 '-lgb-v1' は許容"
metrics:
  duration: 38m
  completed: 2026-06-20
  tasks: 3
  files_created: 3
  files_modified: 2
status: complete
---

# Phase 4 Plan 04: Predict / Evaluator / Prediction Load Summary

**provenance 付き予測 DataFrame (MODL-01/D-05/D-10) + model_version スコープ staging-swap idempotent load (review HIGH#1/Cross-Plan #3) + Brier/LogLoss/Calibration/sum(p) BL比較表 (SC#2/§15.1/§15.2)**

Phase 4 Wave 3 (PLAN 03 と並列) の完結編として、(a) calibrated estimator から provenance 付き予測 DataFrame を構築する predict.py (D-05/D-10・NEW HIGH-1 pred_proba 注入で CatBoost 行整列伝播)、(b) src/etl/fukusho_label.py::_idempotent_load_label パターンを基にしつつ全テーブル破壊でなく model_version スコープ置換を採用する prediction_load.py (review HIGH#1・2回実行で checksum bit-identical)、(c) Brier/LogLoss/Calibration/sum(p) を計算し BL-1..5 + 主モデルの比較表を reports/04-eval.{md,json} に分離出力する evaluator.py (SC#2・review MEDIUM binning 契約固定・sum(p) 診断的扱い) を実装した。review HIGH#1/HIGH#4 + Cross-Plan #1/#3 + Cycle 2 NEW HIGH-1/NEW-3 + Cycle 3 NEW-4 残渣 + review MEDIUM/LOW の全項目を実行可能契約に変換した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | src/model/predict.py — provenance DataFrame + make_model_version (MODL-01/D-05/D-10/HIGH#4/NEW HIGH-1) | `f5ce21c` | src/model/predict.py, tests/model/test_predict.py |
| 2 | src/db/prediction_load.py — model_version スコープ staging-swap idempotent load (D-05/HIGH#1/Cross-Plan #3) | `eeb1a6c` | src/db/prediction_load.py, tests/model/test_prediction_load.py |
| 3 | src/model/evaluator.py — Brier/LogLoss/Calibration/sum(p) + BL比較表 (SC#2/§15.1/§15.2/MEDIUM/LOW) | `9e913ec` | src/model/evaluator.py |

## What Was Built

### Task 1: src/model/predict.py — MODL-01 / D-05 / D-10 / review HIGH#4 / Cycle 2 NEW HIGH-1

- **PREDICTION_COLUMNS 定数 (review HIGH#1: 11カラム PK)**: schema.py PREDICTION_TABLE_DDL の列順と 1:1 (provenance 5 + PK RACE_KEY 7 + 予測値 1 + 補助メタ 2 = 15 列)。prediction_load.py がこの順序で INSERT する。
- **make_model_version (review HIGH#4 / Cross-Plan #1 / Cycle 3 NEW-4)**: `f"{feature_snapshot_id}-{MODEL_TYPE_TO_SHORT[model_type]}-v{version_n}"`。例: `make_model_version("20260620-1a-postreview-v2", "lightgbm", 1)` → `"20260620-1a-postreview-v2-lgb-v1"`。**feature_snapshot_id 全体をそのまま prefix** として使い・二重 postfix (旧版 `...-postreview-v2-postreview-v2-lgb-v1`) は出力しない。MODEL_TYPE_TO_SHORT = `{"lightgbm":"lgb", "catboost":"cb", "logreg":"logreg"}`。
- **predict_p_fukusho (MODL-01 / D-05 / Cycle 2 NEW HIGH-1)**: calibrated estimator の `predict_proba(X)[:, 1]` から `p_fukusho_hit` を算出し・race_df (PK 7カラム + race_date) と結合して PREDICTION_COLUMNS 列順の DataFrame を構築。provenance 5列 (model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method) を付与。
- **NEW HIGH-1 pred_proba 注入 (Cycle 2 NEW HIGH-1・silent wrong-horse prediction 回帰閉塞)**: `pred_proba` 引数 (None デフォルト) で呼出側から aligned 予測値を注入可能。`None` の場合は `calibrated_estimator.predict_proba(X)[:, 1]` を算出 (LightGBM 標準パス)。`np.ndarray` / `pd.Series` で渡された場合は**再予測せず注入値を使用**。`len(pred_proba) == len(X)` と `pred_proba.index.equals(X.index)` (Series の場合) を assert・違反は `RuntimeError` (silent wrong-horse prediction 防止・CatBoost の align_predictions 出力を orchestrator が同引数で渡すことで行整列が最終 DataFrame に伝播)。
- **as_of_datetime 制御可能 (review MEDIUM / T-04-25b)**: 引数が None の場合は `datetime.now(UTC)`、固定値を渡すことで reproduce smoke で bit-identical hash を保証 (揮発性 now() が hash に混入するのを防止)。
- **_assert_valid_prediction_df (T-04-20)**: 列順序一致・5 provenance 列 NOT NULL・p_fukusho_hit ∈ [0,1]・PK 11カラム一意を検証・違反で ValueError (fail-loud・silent fallback 禁止)。
- **test_predict.py 3 test GREEN**: test_provenance_columns (列順序/provenance NOT NULL/[0,1]/PK 11一意) / test_predict_uses_injected_pred_proba (注入値使用 + index 不一致 RuntimeError) / test_model_version_numbering (lightgbm-v1/catboost-v1/v2 + 二重 postfix 回帰検出)。

### Task 2: src/db/prediction_load.py — D-05 / review HIGH#1 / Cross-Plan #3 / Cycle 2 NEW-3

- **model_version スコープ staging-swap (review HIGH#1 / Cross-Plan #3)**: src/etl/fukusho_label.py::_idempotent_load_label パターンを基にするが・**全テーブル DROP+RENAME でなく model_version スコープ DELETE → INSERT** を採用。同一 model_type+model_version の行のみ置換し・他 model_type/version の行は保持 (LightGBM 実行後 CatBoost 実行が前者を削除する silent 履歴破壊防止・§19.1 聖域)。
- **11 step staging-swap (fukusho_label.py パターン踏襲)**: advisory lock (`pg_advisory_xact_lock(hashtext('prediction.fukusho_prediction'))`) → 空入力拒否 (RuntimeError) → model_version 単一性 assert (複数混在は ValueError) → CREATE staging INCLUDING ALL → TRUNCATE → executemany INSERT → SELECT count(*) verify (WR-06) → **DELETE WHERE model_type+model_version from 本テーブル (他 version 保持)** → **INSERT staging → 本テーブル (Cycle 2 NEW-3: cols_sql 明示・`SELECT *` 使用禁止)** → DROP staging → md5 string_agg checksum 返却 (ORDER BY PK 11カラム・WHERE model_version scope)。
- **Cycle 2 NEW-3 明示的列リスト**: staging → 本テーブル INSERT は `INSERT INTO prediction.fukusho_prediction (cols_sql) SELECT cols_sql FROM prediction.fukusho_prediction_staging`・cols_sql は PREDICTION_COLUMNS csv。`grep -c 'SELECT * FROM prediction.fukusho_prediction_staging' == 0` を満たす (将来 DDL 変更で誤列挿入防止)。
- **SQL injection 対策**: psycopg.sql.Identifier/Placeholder を全 SQL 構築に使用・生文字列埋込なし (HIGH #3)。
- **load_predictions 公開 API**: `_df_to_prediction_tuples` + `_idempotent_load_prediction` の薄い wrapper・reader_role が None なら `Settings().db_reader_role` から取得。呼出側は**1 model_type+model_version 単位**で呼ぶ前提 (複数混在は ValueError・run_train_predict は model_type 毎に呼出)。
- **test_prediction_load.py 3 test GREEN (requires_db・live DB)**: test_idempotent_checksum_match (2回実行で checksum bit-identical + 重複なし + staging 残存なし) / test_model_version_scoped_swap_preserves_other_models (lightgbm 書込後 catboost 書込で lightgbm 10行残る・catboost も10行) / test_df_to_prediction_tuples_column_order (unit・列順序 + 型変換)。

### Task 3: src/model/evaluator.py — SC#2 / §15.1 / §15.2 / D-04 / review MEDIUM / review LOW

- **compute_metrics (§15.1)**: brier_score_loss / log_loss(labels=[0,1]) / roc_auc_score (single-class は NaN) + sum(p) 分布 (mean/median/p10/p90 via race_key groupby) + calibration_max_dev。`sum_p_note` キーで SUM_P_DIAGNOSTIC_NOTE (独立二値性質・厳密合計制約でなく診断的指標) を付与 (review MEDIUM)。
- **check_sum_p_distribution (§15.2・review MEDIUM・診断的)**: race_key groupby で sum(p) を計算・8頭以上は [2.7,3.3]・5-7頭は [1.8,2.2] を機械検査・違反 race_key リスト + violation_rate を返す。fail-loud でなく warning (量的異常は参考レポート・hybrid gate D-01/D-02 準拠)。`diagnostic_note` キーで独立二値性質を明記 (false alarm 防止)。
- **binning 契約固定 (review MEDIUM・再現性保証)**: CALIBRATION_CURVE_BINS=10 / CALIBRATION_CURVE_STRATEGY="uniform" / CALIBRATION_CURVE_MIN_BIN_COUNT=30 を定数で明示。`_compute_calibration_max_dev` が calibration_curve でこれらを使用・run 毎の bin 変更を防止。
- **build_comparison_table (SC#2・D-04 事前登録)**: METRIC_COLUMNS + model_name + market_reference (BL-3 §14.2 注記) + bl_calib_note (BL-4/5 未キャリブレーション注記) + **d04_selection_criterion** 列 (D-04 事前登録: Calibration 重視・calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考・Phase 6 で最終選定基準・T-04-24 後知恵すり替え防止) を持つ比較表。
- **write_eval_report (review LOW・.md + .json 分離)**: reports/04-eval.md (比較表 + §15.2 sum(p) 検査 + BL-3/4/5 注記 + binning 契約) + reports/04-eval.json (metrics_dict + comparison_table + constants + notes・`json.dumps(sort_keys=True)` + artifact.py::_atomic_write_text で byte-reproducible atomic write) に分離出力。
- **evaluate_all_models (PLAN 05 消費)**: predictions_by_model + y_true_by_split を統合評価・test split を主評価 (§15.4)・reports/04-eval.{md,json} を出力・metrics_dict を返す。
- **smoke 検証 GREEN**: `uv run python -c "...compute_metrics(y,p); assert 'brier' in m and 'logloss' in m; assert CALIBRATION_CURVE_BINS == 10; print('EVALUATOR_OK')"` → `EVALUATOR_OK`。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_model_version_numbering の二重 suffix 検出 assertion 設計修正**
- **Found during:** Task 1 GREEN 化 (test_model_version_numbering 実行時・`-postreview-v2-lgb` 部分文字列が正形式 `20260620-1a-postreview-v2-lgb-v1` に含まれるため assert が false fail)
- **Issue:** 元の assertion `assert "-postreview-v2-lgb" not in mv` は・feature_snapshot_id が `-v2` で終わる場合・正しい形式 `20260620-1a-postreview-v2-lgb-v1` の中にも部分文字列として現れてしまう。これは実装のバグでなく・テスト assertion の設計ミス。
- **Fix:** 真の回帰形 (二重 postfix) を検出するよう assertion を修正: (a) `mv.startswith(fsid + "-")` (snapshot_id 全体が prefix)、(b) `"-postreview-v2-postreview-v2-" not in mv` (snapshot_id の version token が model_type short の直前に2回現れない)、(c) `mv.endswith("-lgb-v1")` (model_type short は末尾に1回)。実装 (`make_model_version`) は修正不要・テスト assertion のみ修正。
- **Files modified:** tests/model/test_predict.py
- **Commit:** f5ce21c

**2. [Rule 2 - Missing Critical Functionality] ruff lint/format 適用 (CLAUDE.md 準拠)**
- **Found during:** Task 1/2 実装後・ruff check で E501 (line too long) / UP017 (datetime.UTC alias) / I001 (import sort) が検出
- **Issue:** CLAUDE.md が `ruff==0.15.17` をデフォルト linter/formatter として指定。本 PLAN の新規ファイル (predict.py / prediction_load.py / evaluator.py / test 2件) が ruff 違反だとプロジェクト品質基準違反。
- **Fix:** (a) fukusho_label.py パターン踏襲で `# ruff: noqa: E501` をファイル先頭に付与 (SQL リテラル・長 docstring は行長緩和)、(b) `ruff check --fix` で UP017 (timezone.utc → UTC) / I001 (import sort) を自動修正、(c) `ruff format` を全ファイルに適用。`ruff check` / `ruff format --check` 共に All checks passed。
- **Files modified:** src/model/predict.py, src/db/prediction_load.py, tests/model/test_predict.py, tests/model/test_prediction_load.py
- **Commit:** eeb1a6c

## Verification Results

### 自動検証

- `uv run pytest tests/model/test_predict.py -q`: 3 passed ✓
- `uv run pytest tests/model/test_prediction_load.py -q`: 3 passed ✓ (requires_db・live DB で idempotent checksum 一致 + model_version スコープ保存を実証)
- `uv run pytest tests/model/test_predict.py tests/model/test_prediction_load.py -q`: 6 passed ✓
- `uv run pytest --ignore=tests/model/test_predict.py --ignore=tests/model/test_prediction_load.py -q`: 249 passed in 314s (Phase 1-3 + 04-02 + 04-03 既存テスト回帰なし) ✓
- `uv run python -c "from src.model.evaluator import ...; print('EVALUATOR_OK')"`: EVALUATOR_OK ✓
- `uv run ruff check src/model/{predict,evaluator}.py src/db/prediction_load.py tests/model/{test_predict,test_prediction_load}.py`: All checks passed ✓
- `uv run ruff format --check` (同上): All checks passed ✓

### acceptance criteria grep 検証

**Task 1 (predict.py):**
- `PREDICTION_COLUMNS` 定数が schema.py PREDICTION_TABLE_DDL と一致: ✓ (15列・順序含む)
- 5 provenance 列付与 (`model_type`/`model_version`/`feature_snapshot_id`/`as_of_datetime`/`calib_method`): ✓
- `_assert_valid_prediction_df` + `raise ValueError` guard: ✓
- `pred_proba=None` キーワード引数 (NEW HIGH-1)・注入時は再予測せず index 一致 assert・違反 RuntimeError: ✓
- `make_model_version` が D-10 形式 `{feature_snapshot_id}-{short}-v{N}`: ✓ (`20260620-1a-postreview-v2-lgb-v1` 等)

**Task 2 (prediction_load.py):**
- `pg_advisory_xact_lock('prediction.fukusho_prediction')`: ✓ (2 件)
- 空入力拒否 `raise RuntimeError`: ✓ (1 件)
- `DELETE FROM prediction.fukusho_prediction WHERE model_type = %s AND model_version = %s` (model_version スコープ): ✓ (review HIGH#1)
- `CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction_staging (LIKE prediction.fukusho_prediction INCLUDING ALL)`: ✓
- staging → 本テーブル INSERT + DROP staging クリーンアップ: ✓
- `SELECT * FROM prediction.fukusho_prediction_staging` grep == 0 (Cycle 2 NEW-3 明示的列リスト): ✓
- `psycopg.sql.Identifier/Placeholder` SQL injection 対策: ✓ (31 件)
- md5 string_agg checksum + ORDER BY PK 11カラム + WHERE model_version scope: ✓
- 単一 model_type+model_version で2回連続実行で checksum bit-identical: ✓ (test_idempotent_checksum_match で実証)
- lightgbm 書込後 catboost 書込で lightgbm 行が残る: ✓ (test_model_version_scoped_swap_preserves_other_models で実証)

**Task 3 (evaluator.py):**
- 5 関数 (compute_metrics / check_sum_p_distribution / build_comparison_table / write_eval_report / evaluate_all_models) 存在: ✓
- SUM_P_BOUNDS = {"large": (2.7,3.3), "small": (1.8,2.2)} §15.2 一致: ✓
- CALIBRATION_CURVE_BINS/STRATEGY/MIN_BIN_COUNT 定数定義・calibration_curve で使用: ✓ (review MEDIUM binning 契約明示)
- build_comparison_table が BL-3 §14.2 注記 + BL-4/5 未キャリブレーション注記を含む: ✓ (review MEDIUM)
- write_eval_report が reports/04-eval.md + reports/04-eval.json に分離出力・json.dumps(sort_keys=True): ✓ (review LOW)
- compute_metrics が brier/logloss/auc/sum_p 分布/calibration_max_dev + sum_p_note を計算: ✓
- check_sum_p_distribution が違反 race_key リスト + diagnostic_note を返す: ✓ (review MEDIUM)
- D-04 事前登録「Calibration 重視」選定基準素材が d04_selection_criterion 列に固定: ✓ (T-04-24)

## TDD Gate Compliance

本 PLAN は `type: execute` (TDD gate 強制なし・per-task tdd="true") だが・Task 1 と Task 2 は tdd="true" であり RED → GREEN サイクルを実施:

- **Task 1 RED**: tests/model/test_predict.py 3 stub を完全実装化し・src.model.predict の ImportError (ModuleNotFoundError) で RED 確認
- **Task 1 GREEN**: src/model/predict.py 実装で 3 test GREEN (commit `f5ce21c`)
- **Task 2 RED**: tests/model/test_prediction_load.py 2 stub を完全実装化し・src.db.prediction_load の ImportError で RED 確認
- **Task 2 GREEN**: src/db/prediction_load.py 実装で 3 test GREEN (commit `eeb1a6c`)
- **Task 3**: type="auto" (tdd なし)・smoke 検証 (EVALUATOR_OK) で検証 (commit `9e913ec`)

gate 順序: test (...) コミットは無いが・RED (fail stub) → GREEN (実装) の実質サイクルは各 Task 内で実施済み。type: execute なので test/feat 分離コミットは必須でない。

## Known Stubs

本 PLAN で RED stub の GREEN 化を完遂。後続 PLAN 05 (run_train_predict) が本 PLAN の API を統合して消費する:

| 消費元 API | 消費する PLAN |
| ---- | ---- |
| predict_p_fukusho / make_model_version / PREDICTION_COLUMNS | PLAN 05 (run_train_predict) |
| load_predictions / _idempotent_load_prediction | PLAN 05 (run_train_predict) |
| evaluate_all_models / compute_metrics / build_comparison_table | PLAN 05 (run_train_predict) |

本 PLAN 完了を阻害する stub なし。

## Threat Flags

本 PLAN で作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている:

- T-04-20 (Repudiation: provenance 列欠損で再現性崩壊): mitigate・`_assert_valid_prediction_df` で全 provenance 列 NOT NULL を ValueError guard・unit test で NaN なしを assert (§19.1)
- T-04-20b (Tampering: model_version 形式が D-10 と不一致で二重 suffix): mitigate・`make_model_version` が D-10 例と完全一致 `{feature_snapshot_id}-{short}-v{N}` を返す・unit test で lightgbm/catboost/v2 + 二重 postfix 回帰検出を assert (review HIGH#4/Cross-Plan #1/Cycle 3 NEW-4)
- T-04-21 (Tampering: 全テーブル置換で他 model_version の行を破壊): mitigate・**model_version スコープ置換** (advisory lock → staging INCLUDING ALL → TRUNCATE → INSERT staging → count verify → DELETE WHERE model_type+model_version → INSERT cols_sql 明示 → DROP staging) で他 model_version の行を保持・test_idempotent_checksum_match + test_model_version_scoped_swap_preserves_other_models で実証 (review HIGH#1/Cross-Plan #3)
- T-04-21b (Tampering: staging→本テーブル INSERT の SELECT * が DDL 変更で誤列挿入): mitigate・INSERT 文に明示的列リスト (PREDICTION_COLUMNS csv) を pin・`grep 'SELECT * FROM prediction.fukusho_prediction_staging' == 0` で検証可能 (Cycle 2 NEW-3)
- T-04-22 (Elevation of Privilege: reader ロールへの過剰 GRANT): mitigate・GRANT は schema.py の ALTER DEFAULT PRIVILEGES でカバー・TO PUBLIC 不使用・psycopg.sql.Identifier/Placeholder で SQL injection 対策 (HIGH #3)
- T-04-23 (Tampering: checksum SQL の列順序依存で非決定論的): mitigate・md5 string_agg で ORDER BY PK 11カラム安定・列順は PREDICTION_COLUMNS 固定・WHERE model_version scope (review HIGH#1)
- T-04-24 (Information Disclosure: 後知恵で選定基準すり替え): mitigate・D-04 事前登録: comparison 表の d04_selection_criterion 列で「Calibration 重視」を結果前に固定・Phase 6 で最終判定
- T-04-25 (Tampering: sum(p) 理論値違反を silent 無視・または独立二値性質で false alarm): mitigate・check_sum_p_distribution が違反 race_key リスト + diagnostic_note で独立二値性質を明記 (review MEDIUM)・fail-loud でなく warning・§15.2 受入基準違反は Phase 6 ゲートでブロック (本 PLAN では warning・hybrid gate D-01/D-02 準拠)
- T-04-25b (Repudiation: bit-identical hash に揮発性 as_of_datetime = now() が混入): mitigate・predict_p_fukusho が as_of_datetime 引数を受け取り・reproduce smoke では固定値を渡す (review MEDIUM)
- T-04-25c (Tampering: predict_p_fukusho 内部の再予測で CatBoost aligned pred_proba が捨てられ silent wrong-horse prediction): mitigate・predict_p_fukusho に `pred_proba` 引数を追加し・注入時は再予測せず index 一致を assert・test_predict_uses_injected_pred_proba で注入値使用と index 不一致 RuntimeError を実証 (Cycle 2 NEW HIGH-1)

新たなセキュリティ表面の追加は無い。

## Self-Check: PASSED

- FOUND: src/model/predict.py (predict_p_fukusho/make_model_version/_assert_valid_prediction_df + 定数 PREDICTION_COLUMNS/MODEL_TYPE_TO_SHORT/PK_COLUMNS)
- FOUND: src/model/evaluator.py (compute_metrics/check_sum_p_distribution/build_comparison_table/write_eval_report/evaluate_all_models + 定数 SUM_P_BOUNDS/METRIC_COLUMNS/CALIBRATION_CURVE_BINS/STRATEGY/MIN_BIN_COUNT/BL3_MARKET_REFERENCE_NOTE/BL_UNCALIBRATED_NOTE/D04_SELECTION_CRITERION_NOTE/SUM_P_DIAGNOSTIC_NOTE)
- FOUND: src/db/prediction_load.py (_idempotent_load_prediction/load_predictions/_df_to_prediction_tuples + 定数 _PREDICTION_TABLE/_PK_ORDER_COLUMNS)
- FOUND: tests/model/test_predict.py (3 test GREEN)
- FOUND: tests/model/test_prediction_load.py (3 test GREEN・requires_db 2件 + unit 1件)
- FOUND: commit f5ce21c (Task 1)
- FOUND: commit eeb1a6c (Task 2)
- FOUND: commit 9e913ec (Task 3)
