# Phase 4: Model & Prediction - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 18（新設 14 / 修正 4）
**Analogs found:** 17 / 18（1件 = `src/model/calibrator.py` wrapper は既存 `src/utils/calibrator.py` を薄く wrap するのみ・新規パターン無し、残り全て強い analog あり）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/model/__init__.py` | package marker | — | `src/features/__init__.py` / `src/utils/__init__.py` | exact |
| `src/model/data.py` | service (data prep) | transform | `src/features/builder.py` + `src/features/category_map_consumer.py` + `src/features/availability.py` | role-match (複合) |
| `src/model/trainer.py` | service (training) | transform | （新規・コード analog なし。sklearn/LightGBM/CatBoost API の直接利用。参考: `src/utils/calibrator.py` の estimator 取回し） | no analog |
| `src/model/calibrator.py` | service (wrapper) | transform | `src/utils/calibrator.py`（薄い wrapper・`fit_prefit_calibrator` に sigmoid/isotopic 切替を加える程度） | exact |
| `src/model/baseline.py` | service | transform | （新規・コード analog なし。pandas group-by + sklearn LogisticRegression の直接実装） | no analog |
| `src/model/evaluator.py` | service | transform | （新規・コード analog なし。sklearn brier/log_loss + pandas group-by） | no analog |
| `src/model/artifact.py` | utility | file-I/O | `src/features/snapshot.py`（決定論的 save/load・atomic write の意図は同一） | role-match |
| `src/model/predict.py` | service | transform | （新規・コード analog なし。`calibrated.predict_proba` + provenance 列付与） | no analog |
| `src/db/schema.py` (修正) | config (DDL) | — | 既存 `src/db/schema.py`（`label` スキーマ DDL/GRANT パターンの prediction 版に複製） | exact |
| `src/db/connection.py` (修正) | config (pool) | — | 既存 `src/db/connection.py`（`make_pool` search_path 拡張） | exact |
| `src/db/prediction_load.py` | service (ETL write) | batch / DB write | `src/etl/fukusho_label.py`（`_idempotent_load_label`・staging-swap） | exact |
| `scripts/run_train_predict.py` | script (entrypoint) | batch | `scripts/run_feature_build.py` / `scripts/run_label_etl.py` | exact |
| `tests/model/__init__.py` | test marker | — | `tests/features/__init__.py` | exact |
| `tests/model/test_data.py` | test | — | `tests/features/test_allowlist.py` + `tests/features/test_category_map_consumer.py` | role-match |
| `tests/model/test_trainer.py` | test (adversarial) | — | `tests/utils/test_calibrator.py`（smoke + leak-guard ValueError 検証パターン） | role-match |
| `tests/model/test_calibrator.py` | test | — | `tests/utils/test_calibrator.py`（そのまま流用可能） | exact |
| `tests/model/test_baseline.py` | test | — | `tests/features/test_builder.py`（pandas assert パターン） | role-match |
| `tests/model/test_predict.py` | test | — | `tests/features/test_snapshot_repro.py`（provenance / hash assert） | role-match |
| `tests/model/test_prediction_load.py` | test (integration) | DB write | `tests/test_fukusho_label.py`（idempotent verify・`requires_db` マーク） | exact |
| `pyproject.toml` (修正) | config | — | 既存 `pyproject.toml`（dependencies 配列に pin 追加） | exact |

---

## Pattern Assignments

### `src/model/data.py` (service, transform)

**Analog:** `src/features/builder.py`（Parquet 読込 + PK merge）+ `src/features/category_map_consumer.py`（frozen map 消費）+ `src/features/availability.py`（allowlist 検査）

**複製すべきパターン:**

1. **Parquet 読込（`load_feature_matrix`）** — 直接 import せず `pyarrow.parquet.read_table().to_pandas()` を呼ぶ。SC#1 = stamped Parquet のみ。
2. **PK join で label を結合** — `src/etl/fukusho_label.py:629` の `merge(on=_RACE_KEY, how="left")` パターン。PK は7カラム（`year, jyocd, kaiji, nichiji, racenum, umaban, kettonum`）。label 側の型が date/datetime/str 混在するため merge 前に `astype(str)` で両側を揃える（`fukusho_label.py:641-644`）。
3. **raw ID 原列の drop** — `_RAW_ID_KEPT_COLUMNS`（`src/features/availability.py:131-137`）を参考に、`prepare_model_matrix()` で明示的に `drop(columns=[...])`。unit test で除外を assert（Pitfall 4）。
4. **allowlist 検査** — `assert_matrix_columns_registered(spec, output_columns)`（`availability.py:301`）をそのまま呼び出し、banned features（`banned_features(spec)` が返すリスト）が空であることを assert（D-07 / SC#1）。
5. **frozen category map の適用（再 fit 禁止）** — `load_category_maps("snapshots/category_map_20260620-1a-postreview-v2.json")` を呼ぶのみ。`apply_category_map` は呼ばない（既に snapshot 内で `_code` int32 化済み・`apply_frozen_category_maps` が builder 内で実行済み・`category_map_consumer.py:200-240` 参照）。

**注意すべき差分:**
- builder は live DB から feature を計算するが、Phase 4 の data.py は **stamped Parquet のみ**を読む（live DB から feature 再計算は SC#1 違反）。label と BL-2/BL-3 の odds/ninki だけが DB から来る。
- 3way 分割は `race_id_time_series_split`（`src/utils/group_split.py`）を直接使わず、D-02b 推奨案（train 2016-07..2023 / calib 2024-H1 / test 2024-H2 / 2025+ 温存）の暦年 mask で分離する。`race_id_time_series_split` は expanding-window のみ生成するため（`group_split.py:38-46` の honesty note 参照）。

**Imports（複製元）:**
```python
import pyarrow.parquet as pq
import pandas as pd
from src.features.availability import (
    assert_matrix_columns_registered,
    banned_features,
    load_feature_availability,
    _RAW_ID_KEPT_COLUMNS,  # public 昇格を検討（現状はモジュール private）
)
```

---

### `src/model/trainer.py` (service, transform)

**Analog:** コード analog なし。sklearn/LightGBM/CatBoost 公式 API を直接使用。参照すべき既存契約は `src/utils/calibrator.py`（estimator 取回し）と CLAUDE.md §14.3/§14.4。

**複製すべきパターン:**

1. **固定 seed / 決定論的フラグ** — LightGBM は `seed=42, deterministic=True, force_col_wise=True, bagging_seed=42, feature_fraction_seed=42`（D-06）。CatBoost は `random_seed=42, has_time=True`（permutation 無効化で決定論的）。
2. **Pool sort** — CatBoost は `X_train.sort_values(["race_start_datetime", "race_id"])` してから Pool 構築（`has_time=True` が入力順序を使用・CLAUDE.md §14.4）。
3. **early stopping eval set の分離（Pitfall 5 / D-04）** — eval set は train slice の時系列末尾（例: 2023年 Q3-Q4）から切り出す。unit test で `set(eval_races).isdisjoint(set(calib_races))` と `isdisjoint(set(test_races))` を assert。
4. **leak diagnostic（SC#3 / D-05）** — 合成データで希少カテゴリ `'RARE_X'` の label を全て 1 に設定し、native categorical なら予測が global mean（0.21 程度）に縮むことを assert（target encoding 混入なら 1.0 近く）。RESEARCH.md:516-529 の擬似コードを忠実に実装。

**複製すべき契約（`src/utils/calibrator.py` から）:**
- estimator は train slice で `.fit()` したものをそのまま `fit_prefit_calibrator` へ渡す（再 fit 禁止・prefit semantics）。

---

### `src/model/calibrator.py` (service, wrapper)

**Analog:** `src/utils/calibrator.py`（そのまま再利用）

**複製すべきパターン:**

- このファイルは **薄い wrapper** に過ぎない。`fit_prefit_calibrator` を直接 import し、calib sample 件数で `method` を切り替えるロジックを1行加えるのみ。
- 既存 `fit_prefit_calibrator`（`src/utils/calibrator.py:41-103`）は strict-later ValueError guard + `FrozenEstimator` + `CalibratedClassifierCV` を内蔵済み。Phase 4 は **再実装しない**。

**実装例（RESEARCH.md:323-336 から直接）:**
```python
from src.utils.calibrator import fit_prefit_calibrator

calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"  # CLAUDE.md §15.2
calibrated = fit_prefit_calibrator(
    base_estimator=fitted_lgb,
    X_calib=X_calib, y_calib=y_calib,
    race_dates_calib=calib_df["race_date"],
    train_max_date=train_df["race_date"].max(),
    method=calib_method,
)
```

---

### `src/model/baseline.py` (service, transform)

**Analog:** コード analog なし。pandas group-by + sklearn LogisticRegression の直接実装。

**複製すべきパターン:**

1. **BL-1 頭数別一定** — `sales_start_entry_count`（`label.fukusho_label`・`src/etl/fukusho_label.py:890` の列定義参照）と `fukusho_payout_places`（同・line 896）を使用。8頭以上は `3/count`、5-7頭は `2/count`。
2. **BL-2/BL-3 レース内正規化（D-07）** — pandas group-by で `p_i = (1/odds_i) / sum(1/odds) * payout_places`。`sum(p) = 払戻対象数` になるよう正規化。`banned_features` との整合を unit test で assert（odds/ninki は feature には混入せず BL 独立ベンチマークとしてのみ）。
3. **BL-4 LogisticRegression** — `sklearn.linear_model.LogisticRegression(max_iter=1000, random_state=42)`。少数特徴量（barei/futan/umaban/wakuban/class_code_normalized）で `predict_proba`。
4. **BL-5 LightGBM 最小特徴量** — trainer.py の `train_lightgbm` を feature subset で呼出。

**注意すべき差分:**
- BL-2/BL-3 の市場データは `n_odds_tanpuku.fukuoddslow` / `n_uma_race.ninki` から取得（D-08）。readonly pool で SELECT のみ。

---

### `src/model/evaluator.py` (service, transform)

**Analog:** コード analog なし。sklearn 評価指標の直接利用。

**複製すべきパターン:**

1. **Brier/LogLoss** — `sklearn.metrics.brier_score_loss` / `log_loss`。
2. **`sum(p)` 理論値チェック（§15.2）** — pandas group-by `race_id` で sum/median/std/p10/p90 を計算。8頭以上は [2.7, 3.3]、5-7頭は [1.8, 2.2] の区間を機械検査。
3. **比較表出力** — JSON + Markdown で `reports/04-eval.md` へ。CLAUDE.md「Phase 4 では evaluator 出力は JSON/Markdown 主体（plotly はオプション）」。

---

### `src/model/artifact.py` (utility, file-I/O)

**Analog:** `src/features/snapshot.py`（決定論的 save/load・atomic write）

**複製すべきパターン:**

1. **atomic write** — `src/features/category_map_consumer.py:263-272` の `persist_category_maps` パターン（tmp file → `os.replace`）。モデル artifact が partial-failure で破損するのを防止。
2. **native 形式（D-06）** — LightGBM は `booster.save_model("lgb_model.txt")`・CatBoost は `model.save_model("cb_model.cbm")`・sklearn は `joblib.dump(calibrator, "calibrator.joblib")`。pickle は使わない（Phase 3 CR-04 pickle ACE 回避思想）。
3. **metadata.json** — `model_version` / `feature_snapshot_id` / `hyperparams` / `seed` / `train_calib_test_periods` を JSON（`sort_keys=True`・byte-reproducible）で書出（`persist_category_maps` の `json.dumps(..., sort_keys=True)` パターン・`category_map_consumer.py:268`）。
4. **ディレクトリ作成** — `Path(out_dir).mkdir(parents=True, exist_ok=True)`（`snapshot.py:274-275`）。

**注意すべき差分:**
- snapshot.py の SHA256 計算は Parquet bytes に固有。モデル artifact の bit-identical 再現性は `deterministic=True`/`has_time=True` で保証し、artifact.py 側では hash を計算しない（SC#4 reproduce smoke が予測配列の bit-identical で検証）。

---

### `src/model/predict.py` (service, transform)

**Analog:** コード analog なし。`calibrated.predict_proba` + provenance 列付与。

**複製すべきパターン:**

1. **provenance 列の付与（D-05 / §19.1）** — `model_type` / `model_version` / `feature_snapshot_id` / `as_of_datetime` / `calib_method`。D-10 採番方式: `{feature_snapshot_id}-{model_type_short}-v{N}`（例: `20260620-1a-postreview-v2-lgb-v1`・Cycle 3 NEW-4: feature_snapshot_id 全体を prefix・`lgb`/`cb` は model_type_short）。
2. **PK 列の保持** — `label.fukusho_label` と同一7カラム PK（`src/etl/fukusho_label.py:882-888`）。

---

### `src/db/schema.py` (修正)

**Analog:** 既存 `src/db/schema.py` の `label` スキーマ実装（そのまま prediction 版へ複製）

**複製すべきパターン:**

1. **PREDICTION_TABLE_DDL 追加** — `label.fukusho_label` の CREATE TABLE パターン（`src/etl/fukusho_label.py:880-919` の `_LABEL_TABLE_COLUMNS` + `_create_label_table`・line 928-935）を参考に、D-12 の DDL（`prediction.fukusho_prediction`）を `src/db/schema.py` に定数追加。
2. **`GRANT_ETL_SQL` 拡張** — 既存 `label` ブロック（`schema.py:103-108`）をコピーして `prediction` 用に書換:
```sql
GRANT USAGE, CREATE ON SCHEMA prediction TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA prediction TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
```
3. **`GRANT_READER_SQL` 拡張** — 既存 `label` reader ブロック（`schema.py:88-90`）をコピー:
```sql
GRANT USAGE ON SCHEMA prediction TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA prediction TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction GRANT SELECT ON TABLES TO {reader};
```
4. **APPLY_ORDER への追加** — `prediction` スキーマは `CREATE_SCHEMAS_SQL` で既に作成済み（`schema.py:26` の `SCHEMAS` 配列に含まれる）。新規 DDL の適用順序を `APPLY_ORDER`（`schema.py:142-150`）に追加する場合は `grant_etl` の前に挿入。

**注意すべき差分:**
- `prediction.fukusho_prediction` の PK は provenance 含む9カラム（`model_type, model_version, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum`）。`label.fukusho_label` の PK は7カラム（provenance 無し）。

---

### `src/db/connection.py` (修正)

**Analog:** 既存 `src/db/connection.py::make_pool` の `etl` ロール search_path（`label` を先頭に追加した Phase 2 パターン）

**複製すべきパターン:**

1. **search_path 拡張** — `make_pool` の `role == "etl"` ブロック（`connection.py:40-44`）で `prediction` を search_path に追加:
```python
search_path = (
    f"{settings.db_schema_label},"
    f"{settings.db_schema_prediction},"  # 新規・Settings に db_schema_prediction="prediction" を追加
    f"{settings.db_schema_normalized},public"
)
```
2. **Settings へのフィールド追加** — `src/config/settings.py:38-41` に `db_schema_label` が既にあるので、`db_schema_prediction: str = "prediction"` を同パターンで追加。

---

### `src/db/prediction_load.py` (service, batch / DB write)

**Analog:** `src/etl/fukusho_label.py::_idempotent_load_label`（line 945-1019）— **ほぼそのまま複製**

**複製すべきパターン（`fukusho_label.py:945-1019` を1:1 で写す）:**

1. **advisory lock** — `SELECT pg_advisory_xact_lock(hashtext('prediction.fukusho_prediction'))`（line 971・CR-04(b)）。
2. **空入力拒否** — `if not rows: raise RuntimeError(...)`（line 974-978・CR-04(a)・silent data loss 防止）。
3. **CREATE staging (INCLUDING ALL)** — `CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction_staging (LIKE prediction.fukusho_prediction INCLUDING ALL)`（line 984-987）。PK/インデックス/NOT NULL/コメントが継承される。
4. **TRUNCATE → executemany INSERT** — `write_cur.executemany(f"INSERT INTO ... _staging ({cols_sql}) VALUES ({placeholders})", rows)`（line 991-996）。
5. **rowcount verify via SELECT count(\*)** — `executemany` の rowcount は psycopg3 で信用できないため `SELECT count(*) FROM staging` で検証（line 1000-1006・WR-06）。
6. **atomic swap** — `DROP TABLE IF EXISTS prediction.fukusho_prediction` → `ALTER TABLE ... _staging RENAME TO fukusho_prediction`（line 1009-1010）。
7. **reader role GRANT 再発行** — `GRANT SELECT ON prediction.fukusho_prediction TO {reader_role}` を `psycopg.sql.SQL` + `Identifier(reader_role)` で（line 1012-1014・HIGH #3・PUBLIC 不使用）。
8. **checksum 返却** — `SELECT md5(string_agg(md5(row(cols_csv)::text), '' ORDER BY ...))`（`fukusho_label.py:1153-1158`・idempotent 実行確認用・列順序非依存）。
9. **`_df_to_tuples_label` に相当する変換ヘルパー** — `fukusho_label.py:1048-1087` の `_BOOL_COLS` / `_INT_COLS` / `_is_na` パターンを prediction 用に複製（`p_fukusho_hit` は float・provenance は str・PK は int）。

**注意すべき差分:**
- 対象テーブルは `label.fukusho_label` → `prediction.fukusho_prediction`。
- reader ロール名は `settings.db_reader_role`（`keiba_readonly`）から取得（`fukusho_label.py:1118` と同一）。

---

### `scripts/run_train_predict.py` (script, batch)

**Analog:** `scripts/run_feature_build.py`（構造が最も近い・readonly + 学習 + artifact 保存 + 評価レポート）

**複製すべきパターン:**

1. **sys.path への repo-root 追加** — `run_feature_build.py:38-41` のリポジトリルート挿入イディオム。
2. **logging.basicConfig** — `run_label_etl.py:39-43` と同一フォーマット。
3. **masked DSN ログ** — `logger.info("readonly DSN: %s", settings.dsn_masked)`（`run_label_etl.py:50-51`・生 DSN は絶対に出さない・MEDIUM #1）。
4. **pool 構築** — `make_pool(settings, role="readonly")`（feature 読込・BL odds/ninki 取得用）+ `make_pool(settings, role="etl")`（prediction 書込用）。`run_label_etl.py:53-54` と同一。
5. **argparse** — `run_feature_build.py:65-103` の `parse_args` パターン。`--snapshot-id`（D-01 の `20260620-1a-postreview-v2` をデフォルト）・`--model-type {lightgbm,catboost,both}` を追加。
6. **try / except PsycopgError / finally pool.close** — `run_label_etl.py:56-127` と同一構造。
7. **idempotent verify** — prediction_load を2回実行し checksum が一致することを assert（`run_label_etl.py:90-99` の2回実行パターンを予測書込に適用）。

---

### `tests/model/test_*.py` (test)

**Analog:** `tests/utils/test_calibrator.py`（smoke + leak-guard ValueError）+ `tests/features/test_allowlist.py` + `tests/features/test_snapshot_repro.py` + `tests/test_fukusho_label.py`

**複製すべきパターン:**

1. **conftest fixtures の再利用** — `tests/conftest.py` の `settings` / `pg_pool` / `readonly_cur` / `write_pool` / `write_cur` をそのまま使用。`@pytest.mark.requires_db` マークで DB-test を明示（line 41, 59）。
2. **ValueError guard 検証** — `tests/utils/test_calibrator.py:1-60` の「`raise ValueError` を検証 + `python -O` で生存確認するサブプロセステスト」パターン。SC#3/SC#4 の guard にそのまま適用。
3. **synthetic DataFrame での unit test** — `tests/features/test_snapshot_repro.py:20-34` の `_build_synthetic_matrix` パターン。SC#3 leak diagnostic は合成希少カテゴリ DataFrame で実装。
4. **byte-identical 再現性検証** — `tests/features/test_snapshot_repro.py:40-52` の2回呼出 + hash 比較パターン。SC#4 は2回 train_and_predict を呼出し `np.array_equal(pred1, pred2)` で検証。
5. **idempotent 検証** — `tests/test_fukusho_label.py`（参考・2回実行で checksum 一致）を prediction_load に適用。
6. **`requires_db` マーク** — `pyproject.toml:40-42` で定義済み。DB 接続が必要な test に付与。

---

### `pyproject.toml` (修正)

**Analog:** 既存 `pyproject.toml [project].dependencies`（line 10-22）

**複製すべきパターン:**

- `dependencies` 配列に `lightgbm==4.6.0` / `catboost==1.2.10` を追加（D-11・順序は alphabetical でなく既存の論理グループ順）。`uv add "lightgbm==4.6.0" "catboost==1.2.10"` で `uv.lock` も更新。
- `requires-python = ">=3.12,<3.13"` は維持（line 9・CLAUDE.md）。
- `[tool.hatch.build.targets.wheel] packages`（line 28-29）に `src/model` を追加するか検討（wheel 配布対象・現在は `src/config`, `src/db` のみ）。ローカル実行のみなら不要。

---

## Shared Patterns

### 1. ファイル冒頭 docstring + `from __future__ import annotations`
**Source:** 全 `src/` ファイル（例: `src/utils/calibrator.py:1-28` / `src/features/snapshot.py:1-35`）
**Apply to:** 全新設 `src/model/*.py` ファイル

```python
"""<モジュール概要>（成功基準#X / §YY / D-ZZ）。

<設計要点・リーク防止根拠・参照 commit>
"""

from __future__ import annotations
```

### 2. リーク防止 guard = `raise ValueError`（`assert` 不使用）
**Source:** `src/utils/calibrator.py:86-94` / `src/utils/group_split.py:76-128`
**Apply to:** `src/model/data.py`（3way split guard）・`src/model/trainer.py`（eval set 分離 guard）・`src/model/calibrator.py`（strict-later・既存関数が内蔵済み）

```python
if not (train_max_ts < calib_min):
    raise ValueError(
        "calibration slice must be strictly later than training "
        f"(train_max={...}, calib_min={...}); look-ahead leak prevented (§15.2)"
    )
```
`python -O` で削除されないよう `assert` ではなく `raise ValueError`。

### 3. silent fallback 禁止（D-13 / sentinel 明示）
**Source:** `src/utils/category_map.py:20-21`（`UNSEEN = "__UNSEEN__"` / `MISSING = "__MISSING__"`）+ `src/features/category_map_consumer.py:140-142`
**Apply to:** `src/model/data.py`（categorical 列の `fillna("__MISSING__")`）・`src/model/trainer.py`（LightGBM category dtype の NaN→-1 ハザード回避）

```python
for c in LIGHTGBM_CAT_COLS:
    df[c] = df[c].fillna("__MISSING__").astype("category")
```

### 4. DB ロール分離（readonly / etl）+ raw read-only 保護
**Source:** `src/db/schema.py:76-128`（GRANT / REVOKE）+ `src/db/connection.py:21-54`（`make_pool`）
**Apply to:** `scripts/run_train_predict.py`（readonly pool で feature/label/odds SELECT、etl pool で prediction 書込）・`src/db/prediction_load.py`

- feature 読込は `role="readonly"`（`public.n_*` / `raw_everydb2` / `label` に SELECT-only）
- prediction 書込は `role="etl"`（`prediction` スキーマに INSERT/DROP/RENAME/GRANT）

### 5. staging-swap idempotent load（atomic 替換・2回実行で同一 checksum）
**Source:** `src/etl/fukusho_label.py:945-1019`（`_idempotent_load_label`）
**Apply to:** `src/db/prediction_load.py`（そのまま複製・対象テーブル名のみ書換）

9ステップ: advisory lock → 空入力拒否 → CREATE staging (INCLUDING ALL) → TRUNCATE → executemany INSERT → SELECT count(*) verify → DROP → RENAME → GRANT 再発行。

### 6. byte-reproducible / 決定論的フラグの全箇所固定
**Source:** `src/features/snapshot.py:206-269`（PyArrow `use_dictionary=False` / `compression="zstd"` / `row_group_size=100_000`）
**Apply to:** `src/model/trainer.py`（LightGBM `seed=42, deterministic=True, force_col_wise=True, bagging_seed=42, feature_fraction_seed=42` / CatBoost `random_seed=42, has_time=True`）

### 7. atomic write（partial-failure 抑止）
**Source:** `src/features/category_map_consumer.py:263-272`（`persist_category_maps`・tmp file → `os.replace`）
**Apply to:** `src/model/artifact.py`（metadata.json / model artifact の書込）

### 8. masked DSN ログ（生 DSN は絶対に出さない）
**Source:** `scripts/run_label_etl.py:50-51` / `scripts/run_feature_build.py:117`
**Apply to:** `scripts/run_train_predict.py`

```python
logger.info("readonly DSN: %s", settings.dsn_masked)
logger.info("etl      DSN: %s", settings.etl_dsn_masked)
```

### 9. pytest conftest fixtures + `requires_db` マーク
**Source:** `tests/conftest.py:22-78`（`settings` / `pg_pool` / `readonly_cur` / `write_pool` / `write_cur` fixtures + `pytest_collection_modifyitems` で `KEIBA_SKIP_DB_TESTS=1` 時のみ skip）
**Apply to:** 全 `tests/model/test_*.py`

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/model/trainer.py` | service (training) | transform | 学習パイプライン自体は初出。LightGBM/CatBoost API を直接使用。リーク防止ロジックは既存プリミティブ（calibrator/group_split/category_map）を消費するが、学習ループ自体の analog は存在しない。RESEARCH.md の Code Examples（line 461-513）と CLAUDE.md §14.3/§14.4 を直接参照。 |
| `src/model/baseline.py` | service | transform | BL-1..5 実装は初出。pandas group-by + sklearn LogisticRegression の直接実装。RESEARCH.md D-08 確定事項（line 629-643）を参照。 |
| `src/model/evaluator.py` | service | transform | 評価指標の集計は初出。sklearn metrics の直接利用。§15.1/§15.2/§15.3 を参照。 |

planner は上記3ファイルについて RESEARCH.md の Code Examples と確定事項セクション（D-02b〜D-12）を直接アクションに展開すること。

---

## Metadata

**Analog search scope:**
- `/Users/hart/develop/keiba-ai-v3/src/`（config, db, etl, features, utils の全ディレクトリ）
- `/Users/hart/develop/keiba-ai-v3/scripts/`（既存 entrypoint 3件）
- `/Users/hart/develop/keiba-ai-v3/tests/`（conftest + features + utils + トップレベル）

**Files scanned:** 18（CONTEXT/RESEARCH から抽出）・既存 analog 12ファイルを読込んでコード抜粋

**Pattern extraction date:** 2026-06-20

**Key insight:** Phase 4 の新設ファイルのうち、**予測永続化（prediction_load.py）と DB 設定（schema.py / connection.py）とエントリポイント（run_train_predict.py）は既存 `fukusho_label.py` / `run_label_etl.py` / `run_feature_build.py` のほぼ1:1 複製**で実装できる。学習・ベースライン・評価の3モジュールのみコード analog がなく、RESEARCH.md の確定事項（D-02b〜D-12）と CLAUDE.md §14.3/§14.4/§15.2 を直接アクションに展開する必要がある。リーク防止プリミティブ（calibrator / group_split / category_map / availability）は既存契約をそのまま消費し、再実装しないことが再現性とリーク防止の両立の鍵。
