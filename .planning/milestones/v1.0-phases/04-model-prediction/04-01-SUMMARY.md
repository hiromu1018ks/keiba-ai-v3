---
phase: 04-model-prediction
plan: 01
subsystem: model-foundation
tags: [phase-04, foundation, schema, deps, red-stubs, drift-fix]
requires:
  - "Phase 03.1 stamped Parquet snapshot (postreview-v2)"
provides:
  - "lightgbm==4.6.0 / catboost==1.2.10 pin (pyproject.toml + uv.lock)"
  - "prediction.fukusho_prediction テーブル (11カラム PK + 3 CHECK 制約)"
  - "ETL/reader ロールの prediction スキーマ GRANT"
  - "Settings.db_schema_prediction + connection.py etl search_path 拡張"
  - "tests/model/ 7ファイル 20 RED stub (SC#1/#3/#4/MODL-02/D-05 検証契約)"
  - "PROJECT.md/STATE.md v3→postreview-v2 ドリフト修正"
affects:
  - "後続 wave 02-06: trainer/calibrator/baseline/predict/prediction_load 実装が本 stub を GREEN 化"
  - "Phase 5/6/7: prediction.fukusho_prediction テーブルを SQL 照会"
tech-stack:
  added:
    - "lightgbm==4.6.0"
    - "catboost==1.2.10"
    - "plotly==6.8.0 (catboost 推移依存)"
    - "graphviz==0.21 (catboost 推移依存)"
  patterns:
    - "PREDICTION_TABLE_DDL (label スキーマ DDL パターンの prediction 版複製 + review HIGH#1 強化)"
    - "staging-swap idempotent load 用 GRANT USAGE+CREATE 拡張 (PATTERNS.md Shared Pattern 4)"
    - "RED stub = import pytest + docstring + pytest.fail (collection は成功し実行で RED)"
key-files:
  created:
    - "tests/model/__init__.py"
    - "tests/model/test_data.py"
    - "tests/model/test_trainer.py"
    - "tests/model/test_calibrator.py"
    - "tests/model/test_baseline.py"
    - "tests/model/test_predict.py"
    - "tests/model/test_prediction_load.py"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - "src/db/schema.py"
    - "src/db/connection.py"
    - "src/config/settings.py"
    - "scripts/run_apply_schema.py"
    - ".planning/PROJECT.md"
    - ".planning/STATE.md"
decisions:
  - "D-11: lightgbm==4.6.0 / catboost==1.2.10 を pyproject.toml + uv.lock に pin (uv lock --check exit 0)"
  - "review HIGH#1/Cross-Plan #3: PREDICTION_TABLE_DDL PK を 11カラム (model_type/model_version/feature_snapshot_id/as_of_datetime + RACE_KEY 7) + 3 CHECK 制約 (p_fukusho_hit ∈ [0,1] / model_type IN (...) / calib_method IN (...)) で定義"
  - "D-05/D-12: ETL ロールに prediction スキーマ USAGE+CREATE+書込 GRANT・reader ロールに USAGE+SELECT GRANT"
  - "review MEDIUM#3: RED stub 件数を 13+ から厳密値 20件 (4+4+3+6+2+1) に修正"
  - "D-01: PROJECT.md/STATE.md の v3(63・fa0.2.0) 参照を postreview-v2(62・fa0.3.0) に修正・D-02 rolling_jyocd rename 注記追加"
  - "Rule 3 (blocking fix): scripts/run_apply_schema.py の apply() 内ハードコードリストに prediction_table を同期挿入 (schema.py APPLY_ORDER のみ更新では DDL が適用されない)"
metrics:
  duration: 12m
  completed: 2026-06-20
  tasks: 3
  files_created: 7
  files_modified: 8
status: complete
---

# Phase 4 Plan 01: Model Foundation Summary

**LightGBM 4.6.0 / CatBoost 1.2.10 pin + prediction.fukusho_prediction DDL (11カラム PK + 3 CHECK 制約) + tests/model/ 20 RED stub + v3→postreview-v2 ドリフト修正**

Phase 4 の基盤（Wave 0）を整備した。後続 wave (02-06) の trainer/calibrator/baseline/predict/prediction_load 実装が依存する DB スキーマ・ロール権限・依存ライブラリ・test コレクションを先に確立し、実装 task が全て「GREEN 化」に専念できる状態を作った。review HIGH#1/Cross-Plan #3 で指摘された「PK 不足で異 snapshot/再実行の予測が互いに上書きされる silent 履歴破壊」を DDL 段階（11カラム PK に feature_snapshot_id と as_of_datetime を含める）で防止した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | 依存ライブラリ pin + prediction DDL/GRANT/Settings 拡張 | `ae81d5d` | pyproject.toml, uv.lock, src/db/schema.py, src/db/connection.py, src/config/settings.py, scripts/run_apply_schema.py |
| 2 | tests/model/ RED stubs 作成 (20件厳密値 = 4+4+3+6+2+1) | `1358e0b` | tests/model/{__init__,test_data,test_trainer,test_calibrator,test_baseline,test_predict,test_prediction_load}.py |
| 3 | PROJECT.md / STATE.md の v3(63) ドリフトを postreview-v2(62) に修正 | `f5344f8` | .planning/PROJECT.md, .planning/STATE.md |

## What Was Built

### Task 1: 依存ライブラリ pin + prediction DDL/GRANT

- **pyproject.toml + uv.lock**: `lightgbm==4.6.0` / `catboost==1.2.10` を `[project].dependencies` に pin。`requires-python = ">=3.12,<3.13"` 維持。`uv lock --check` exit 0（review MEDIUM#4・意図せぬ推移依存アップグレードなし）。推移依存で plotly 6.8.0 / graphviz 0.21 追加（catboost 由来）。
- **src/db/schema.py**: `PREDICTION_TABLE_DDL` 定数追加（prediction.fukusho_prediction）。
  - **PK = 11カラム**（model_type, model_version, feature_snapshot_id, as_of_datetime, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum）。review HIGH#1 で指摘された「9カラム PK では異 snapshot/再実行の provenance 履歴を不可視に上書きする §19.1 聖域違反」を、feature_snapshot_id と as_of_datetime を PK に含めることで防止。
  - **3 CHECK 制約**（review HIGH#1/Cross-Plan #3）: `prediction_fukusho_hit_range CHECK (p_fukusho_hit >= 0 AND p_fukusho_hit <= 1)` / `prediction_model_type_domain CHECK (model_type IN ('lightgbm','catboost','logreg'))` / `prediction_calib_method_domain CHECK (calib_method IN ('isotonic','sigmoid'))`（Cycle 3 NEW-L2: Phase 4 の LightGBM/CatBoost は両方必ずキャリブレーションするため 'none' は除外・将来未キャリブレーション baseline は別テーブル/別 model_type で扱う）。
  - COMMENT ON TABLE で D-05 provenance・staging-swap idempotent 由来・PK に feature_snapshot_id+as_of_datetime 含む理由（異 snapshot/再実行で履歴破壊防止）を明記。
- **GRANT_ETL_SQL / GRANT_READER_SQL 拡張**: 既存 label ブロックの直後に prediction ブロックを追記。ETL ロールには `USAGE, CREATE ON SCHEMA prediction` + `SELECT, INSERT, UPDATE, DELETE, TRUNCATE`（staging-swap idempotent load が staging テーブル作成に CREATE を必要とするため）。reader ロールには `USAGE` + `SELECT`（Phase 7 Streamlit が SQL 照会）。
- **APPLY_ORDER**: `("prediction_table", PREDICTION_TABLE_DDL)` を `create_raw_views` と `grant_reader` の間に挿入。`__all__` に `PREDICTION_TABLE_DDL` を追加。
- **src/config/settings.py**: `db_schema_prediction: str = "prediction"` フィールド追加（db_schema_label と対称）。
- **src/db/connection.py**: `make_pool(role='etl')` の search_path に `settings.db_schema_prediction` を label と normalized の間に挿入。
- **scripts/run_apply_schema.py** (Rule 3 blocking fix): `apply()` 内のハードコードリストに `("prediction_table", schema_module.PREDICTION_TABLE_DDL)` を挿入。schema.py APPLY_ORDER を更新するだけでは run_apply_schema.py が別リストを使っているため DDL が適用されない不具合を発見・修正。
- **live DB 適用**: `uv run python scripts/run_apply_schema.py` を実行し GRANT 拡張を live DB に反映（CREATE TABLE IF NOT EXISTS + idempotent GRANT）。`\dt prediction.*` / `\dp prediction.fukusho_prediction` / `\d prediction.fukusho_prediction` で PK 11カラム + 3 CHECK 制約 + keiba_etl=arwdD / keiba_readonly=r GRANT を確認。

### Task 2: tests/model/ RED stubs

7ファイル・20 RED stub（review MEDIUM#3 厳密値）を作成。各 stub は `import pytest` + docstring（SC#/D-XX 検証契約を明記）+ `pytest.fail("Wave 0 RED stub - implemented in PLAN 0X")` のみ。実装・本番モジュール import は書かない（後続 wave で GREEN 化）。これにより collection は成功し全 RED 状態で実行される。

| File | stubs | 検証契約 |
| ---- | ----- | -------- |
| test_data.py | 4 | SC#1 stamped Parquet / raw ID 除外 / banned_features 空 / race_id 3way disjoint |
| test_trainer.py | 4 | SC#3 LightGBM 非負 code / CatBoost has_time / target encoding 非混入 diagnostic / eval set 分離 |
| test_calibrator.py | 3 | SC#4 strict-later disjoint / reproduce bit-identical / isotonic>=1000 sigmoid<1000 |
| test_baseline.py | 6 | BL-1..5 厳密定義 / D-08 市場データ源 |
| test_predict.py | 2 | provenance 列 / D-10 model_version 採番 (feature_snapshot_id 全体を prefix) |
| test_prediction_load.py | 1 (@requires_db) | D-05 staging-swap idempotent checksum match |

### Task 3: v3 → postreview-v2 ドリフト修正

- **PROJECT.md** Phase 3.1 履歴: feature_count=63 の中間 snapshot で実証した歴史的事実を保持しつつ、**Phase 4 入力の正は D-01 で `20260620-1a-postreview-v2`（feature_count=62・fa_version 0.3.0・SHA256 `26c685f0…ecbdd2`・`byte_reproducible_scope=parquet_data_only_metadata_excluded`）に確定**した移行文脈に言い換え。
- **D-02 由来注記**: feature 63→62 は CR-02 で `rolling_jyocd_mean_5`→`mode_5`(rename) + `rolling_jyocd_sd_5`(remove)（commit 43bd81f・jyocd はカテゴリカル値で mean/sd は無意味・§13.4 odds-free allowlist 違反なし・D-02 で研究者が git+実データで確定）。
- **STATE.md** decisions L116-117: 同様に postreview-v2 に更新。`feature_count 24→63` を `24→62` に修正。
- `grep -rn '20260619-1a-v3' .planning/PROJECT.md .planning/STATE.md` が空（v3 参照 0 件）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Fix] scripts/run_apply_schema.py のハードコードリストに prediction_table を同期挿入**
- **Found during:** Task 1 (schema 適用検証時)
- **Issue:** PLAN は `schema.py` の `APPLY_ORDER` への挿入のみを指示。しかし `scripts/run_apply_schema.py::apply()` は `APPLY_ORDER` を参照せずハードコードリストを使う（117-125 行）。schema.py のみ更新しても DDL が live DB に適用されない。
- **Fix:** `apply()` 内のハードコードリストにも `("prediction_table", schema_module.PREDICTION_TABLE_DDL)` を `create_raw_views` と `grant_reader` の間に挿入。
- **Files modified:** scripts/run_apply_schema.py
- **Commit:** ae81d5d

**2. [Rule 2 - Critical Documentation] PROJECT.md/STATE.md の歴史的事実を保持しつつ D-01 移行文脈に言い換え**
- **Found during:** Task 3 (ドリフト修正時)
- **Issue:** PLAN acceptance は「`grep -rn '20260619-1a-v3' .planning/PROJECT.md .planning/STATE.md` が空」を要求。しかし PROJECT.md L104 の Phase 3.1 完了履歴は「snapshot-id=20260619-1a-v3 で完了した」歴史的事実の記録。単純削除は履歴改竄になる。
- **Fix:** 履歴の趣旨（何が行われたか）を保ちつつ、「当初の完了時点では feature_count=63 の中間 snapshot で実証したが、Phase 4 入力の正は D-01 で postreview-v2(62) に確定」という移行文脈に言い換え。feature_count=63 の言及は D-02 由来注記（63→62 の理由説明）として残し、acceptance「63 を正として主張している記載は空」を実質満たす。
- **Files modified:** .planning/PROJECT.md, .planning/STATE.md
- **Commit:** f5344f8

## Verification Results

### 自動検証

- `uv run python -c "import lightgbm, catboost; ..."`: lightgbm 4.6.0 / catboost 1.2.10 ✓
- `uv lock --check`: exit 0 ✓
- `grep -c 'lightgbm==4.6.0' pyproject.toml` == 1 / `grep -c 'catboost==1.2.10' pyproject.toml` == 1 ✓
- `grep -c 'models/' .gitignore` >= 1 ✓
- `uv run pytest tests/model/ --collect-only -q | grep -c "::test_"` == 20 ✓
- `uv run pytest tests/model/ -q` == "20 failed" (全 RED・collection error なし) ✓
- `uv run pytest --ignore=tests/model -q` == "225 passed" (既存テスト回帰なし) ✓
- `grep -rn '20260619-1a-v3' .planning/PROJECT.md .planning/STATE.md` == empty ✓

### live DB 検証

- `\dt prediction.*`: `prediction | fukusho_prediction | table | hart` ✓
- `\dp prediction.fukusho_prediction`: `keiba_etl=arwdD` (insert/select/update/delete/truncate) / `keiba_readonly=r` (select) ✓
- `pg_constraint` で PK `fukusho_prediction_pkey` = 11カラム (model_type/model_version/feature_snapshot_id/as_of_datetime/year/jyocd/kaiji/nichiji/racenum/umaban/kettonum) ✓
- `pg_constraint` で 3 CHECK 制約 (prediction_fukusho_hit_range / prediction_model_type_domain / prediction_calib_method_domain) ✓

### Settings/Connection 検証

- `Settings().db_schema_prediction == "prediction"` ✓
- `connection.py make_pool` のソースに `db_schema_prediction` が etl search_path 行に出現 ✓

## Known Stubs

本 PLAN は RED stub の作成自体が目的であり、stub は後続 wave 02-06 で GREEN 化される予定。以下は意図的な stub（ Wave 0 契約）:

| File | stub | GREEN 化する PLAN |
| ---- | ---- | ----------------- |
| tests/model/test_data.py | 4 stubs (SC#1/raw ID/allowlist/race_id disjoint) | PLAN 02 |
| tests/model/test_trainer.py | 4 stubs (SC#3 leak diagnostic/has_time/nonneg/eval set) | PLAN 03 |
| tests/model/test_calibrator.py | 3 stubs (SC#4 strict-later/reproduce/isotonic sigmoid) | PLAN 02 / 05 |
| tests/model/test_baseline.py | 6 stubs (BL-1..5 / market data source) | PLAN 03 |
| tests/model/test_predict.py | 2 stubs (provenance / model_version numbering) | PLAN 04 |
| tests/model/test_prediction_load.py | 1 stub (@requires_db・idempotent checksum) | PLAN 04 |

これらは後続 wave の検証契約であり、本 PLAN の完了を阻害しない（PLAN の goal は「後続 wave が依存する基盤の確立」だから）。

## Threat Flags

本 PLAN で作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている（T-04-SC / T-04-01..05）。新たなセキュリティ表面の追加は無い:

- パッケージインストール境界 (uv add lightgbm/catboost): T-04-SC で Package Legitimacy Audit 済・mitigate
- ETL ロール GRANT 境界 (prediction スキーマ): T-04-01 で mitigate（label ブロックと同一権限 scope・SUPERUSER 不与）
- search_path injection 境界 (etl pool): T-04-02 で mitigate（動的文字列結合なし・settings 由来）
- PREDICTION_TABLE_DDL tampering: T-04-03 で mitigate（11カラム PK + 3 CHECK 制約・CREATE TABLE IF NOT EXISTS idempotent）
- run_apply_schema.py DDL エラーログの information disclosure: T-04-04 で accept（既存 logger・DSN は dsn_masked・新規 PII なし）
- 後続 wave GREEN 化順序の repudiation: T-04-05 で mitigate（各 stub が docstring で SC#/D-XX 明記・VALIDATION.md Per-Task Map が追跡）

## Self-Check: PASSED

- FOUND: pyproject.toml (lightgbm/catboost pin)
- FOUND: uv.lock (lightgbm/catboost pin)
- FOUND: src/db/schema.py (PREDICTION_TABLE_DDL, GRANT_ETL_SQL/GRANT_READER_SQL prediction ブロック, APPLY_ORDER prediction_table, __all__)
- FOUND: src/db/connection.py (db_schema_prediction in etl search_path)
- FOUND: src/config/settings.py (db_schema_prediction フィールド)
- FOUND: scripts/run_apply_schema.py (prediction_table 挿入)
- FOUND: tests/model/{__init__,test_data,test_trainer,test_calibrator,test_baseline,test_predict,test_prediction_load}.py
- FOUND: .planning/PROJECT.md (postreview-v2)
- FOUND: .planning/STATE.md (postreview-v2)
- FOUND: commit ae81d5d
- FOUND: commit 1358e0b
- FOUND: commit f5344f8
