# Phase 3: As-of Features & Snapshots - Pattern Map

**Mapped:** 2026-06-18
**Files analyzed:** 14 (新規 10 + 変更 2 + label backfill UPDATE 1 + CLI script 1)
**Analogs found:** 13 / 14 （PyArrow 決定論的書込のみ codebase 類似なし → 03-RESEARCH.md Pattern 2 を引用）

本 map は Phase 1-2 で確立済みの ETL / leak-prevention / pytest / config の各イディオムを、Phase 3 が**そのまま消費**する方法を示す。Phase 3 は新規プリミティブを発明せず、既存の `pit_join_backward` / `fit_category_map` / `_idempotent_load` / YAML loader / `make_pool(role='readonly'|'etl')` を組み合わせるだけ（03-RESEARCH.md Don't Hand-Roll 節）。

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/features/__init__.py` | package | — | `src/etl/__init__.py` / `src/utils/__init__.py` | exact |
| `src/features/availability.py` | config loader | transform (YAML→dataclass/dict) | `src/etl/class_normalize.py:load_class_config` / `src/etl/fukusho_label.py:load_label_spec` | exact |
| `src/features/builder.py` | service (builder) | transform (DB SELECT → DataFrame feature 化) | `src/etl/normalize.py:run_normalized_etl` / `src/etl/fukusho_label.py:compute_fukusho_labels` | role-match |
| `src/features/rolling.py` | utility (transform) | transform (PIT as-of rolling) | `src/utils/pit_join.py:pit_join_backward` (消費元) | exact (consumer) |
| `src/features/running_style.py` | utility (transform) | transform (閾値ルール分類) | `src/etl/class_normalize.py:normalize_class` (dict/閾値ルール分類) | role-match |
| `src/features/snapshot.py` | utility (file I/O) | file-I/O (PyArrow deterministic write) | （codebase に Parquet 書込なし）→ 03-RESEARCH.md Pattern 2 | no analog |
| `src/features/category_map_consumer.py` | utility (transform) | transform (frozen map fit/apply) | `src/utils/category_map.py` (消費元) | exact (consumer) |
| `src/config/feature_availability.yaml` (modify) | config | — | `src/config/label_spec.yaml` / `class_normalization.yaml` | exact |
| `scripts/run_feature_build.py` (新規想定) | CLI script | request-response (ETL CLI) | `scripts/run_label_etl.py` / `scripts/run_normalized_etl.py` | exact |
| `src/etl/label_race_date_backfill.py` (新規・Phase 2 負債解消) | ETL (UPDATE) | CRUD (UPDATE backfill) | `src/etl/fukusho_label.py:_idempotent_load_label` (staging-swap idempotent) | role-match |
| `tests/features/__init__.py` + `conftest.py` | test infra | — | `tests/conftest.py` + `tests/utils/__init__.py` | exact |
| `tests/features/test_allowlist.py` | test (BLOCK gate) | — | `src/etl/label_reconcile.py` BLOCK verdict pattern / `tests/test_label_reconcile.py` | role-match |
| `tests/features/test_pit_cutoff.py` | test (unit) | — | `tests/utils/test_pit_join.py` | exact |
| `tests/features/test_rolling.py` | test (unit) | — | `tests/utils/test_category_map.py` / `tests/test_fukusho_label.py:_build_se_row` synthetic builders | exact |
| `tests/features/test_running_style.py` | test (unit) | — | `tests/test_class_normalization.py` (閾値ルール分類テスト) | role-match |
| `tests/features/test_snapshot_repro.py` | test (unit + property) | — | （新規・PyArrow）03-RESEARCH.md Example byte-repro | no analog |
| `tests/features/test_category_map_consumer.py` | test (unit) | — | `tests/utils/test_category_map.py` | exact |
| `tests/features/test_builder.py` | test (unit + property) | — | `tests/test_normalized_etl.py` (モジュール import/signature + idempotent) | role-match |

---

## Pattern Assignments

### `src/features/__init__.py` (package)

**Analog:** `src/etl/__init__.py` / `src/utils/__init__.py`

空パッケージマーカー。`__all__` で公開 API を明示するパターン（Phase 1 D-16 utils/ 集約）。各サブモジュールの公開関数を再エクスポートしない（明示的 import を強制・`from src.features.builder import build_feature_matrix` 形式）。

---

### `src/features/availability.py` (config loader, YAML→dict)

**Analog:** `src/etl/fukusho_label.py:load_label_spec` (lines 82-110) + `src/etl/class_normalize.py:load_class_config` (lines 37-51)

**Imports pattern** (`fukusho_label.py:59-74`):
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
```

**Loader 本体** (`fukusho_label.py:82-110`) — これをほぼ複製:
```python
_REQUIRED_SPEC_KEYS = (
    "schema_version",
    "feature_schema",
    "features",
)
_DEFAULT_CONFIG_PATH = Path("src/config/feature_availability.yaml")

def load_feature_availability(path: str | Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """feature_availability.yaml を読込 dict で返す（D-13 silent fallback 禁止）。

    必須キーが1つでも欠損した場合は ValueError で fail-fast（label_spec パターン踏襲）。
    """
    with Path(path).open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(f"feature_availability.yaml は dict でなければなりません: {type(spec)!r}")
    missing = [k for k in _REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(
            f"feature_availability.yaml に必須キーが欠損: {missing} (D-13 silent fallback 禁止)"
        )
    return spec
```

**allowlist 検査ヘルパー**（同モジュール内に定義）:
```python
BANNED_TIMINGS = frozenset({
    "race_day_morning", "body_weight_announced",
    "odds_snapshot_available", "post_race_only", "same_day_aggregate",
})
ALLOWED_TIMINGS = frozenset({"entry_confirmed", "post_position_confirmed"})  # D-07

def banned_features(spec: dict[str, Any]) -> list[str]:
    """SC#2 fail-loud 検査用: 禁止 timing に該当する feature 名を返す（0件期待）。"""
    return [
        f["feature_name"]
        for f in spec.get("features", [])
        if f.get("available_from_timing") in BANNED_TIMINGS
    ]
```

---

### `src/features/builder.py` (service, DB→DataFrame transform)

**Analog:** `src/etl/normalize.py:run_normalized_etl` (lines 624-663) + `src/etl/fukusho_label.py` raw SELECT helpers

**Imports pattern** (`normalize.py:27-37` + `fukusho_label.py:59-73`):
```python
from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from psycopg import Cursor
from psycopg_pool import ConnectionPool
from src.etl.filters import PROJECT_WINDOW_FILTER  # CR-06 single source
```

**Public API シグネチャ**（`run_normalized_etl` lines 624-663 を踏襲）:
```python
def build_feature_matrix(
    read_pool: ConnectionPool,                       # make_pool(role='readonly') のみ
    *,
    snapshot_id: str,                                 # §12.4 feature_snapshot_id
    label_version: str,                               # label_spec.yaml label_generation_version
    fa_version: str,                                  # feature_availability.yaml schema_version
    train_period: tuple[str, str] = ("2016-07-01", "2023-12-31"),  # D-09
    validation_period: tuple[str, str] = ("2024-01-01", "2024-12-31"),  # D-09
) -> dict[str, Any]:
    """readonly pool から SELECT のみで PIT-correct feature matrix を構築。

    Returns:
        {"feature_matrix": pd.DataFrame, "snapshot_id": str,
         "raw_touched": False,  # 常に False（raw read-only・D-06）
         "feature_count": int, "row_count": int}
    """
```

**readonly SELECT の raw 取得イディオム** (`normalize.py:178-184`, 234-240):
```python
def _select_uma_race_history(read_cur: Cursor) -> pd.DataFrame:
    """normalized.n_uma_race から JRA 限定・明示カラム SELECT（SELECT * 禁止）。"""
    cols = ", ".join(_HISTORY_SELECT_COLUMNS)   # 明示カラム（anti-pattern: SELECT *）
    sql = f"SELECT {cols} FROM normalized.n_uma_race WHERE {PROJECT_WINDOW_FILTER}"
    read_cur.execute(sql)
    return pd.DataFrame(read_cur.fetchall(), columns=_HISTORY_SELECT_COLUMNS)
```

**禁止カラム select 義務**（CONTEXT SC#2 / RESEARCH Pitfall 3.1・Pitfall 1）:
明示カラムリスト（`_HISTORY_SELECT_COLUMNS`）に `kyakusitukubun` / 当日 `timediff` / `harontimel3` 当日行 / `bataijyu` 当日 / `odds` / `ninki` / `sibababacd` / `dirtbabacd` / `tenkocd` / `harontimel4`（distinct=1・Pitfall 3.6）は**絶対に含めない**。許可カラムは `feature_availability.yaml` が監査可能 map（§13.3）。

**静的属性 transform**（`normalize.py:_transform_uma_race_df` lines 316-350 のキャスト イディオム）:
```python
out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")  # int 系
out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)    # real 系
```

**cutoff 計算**（D-06）:
```python
observations["feature_cutoff_datetime"] = (
    pd.to_datetime(observations["race_date"]) - pd.Timedelta(days=1)
)
# race_start_datetime は必須項目として保持するが cutoff 基準には使わない（D-06）
```

---

### `src/features/rolling.py` (utility, PIT as-of rolling — consumer)

**Analog (消費元):** `src/utils/pit_join.py:pit_join_backward` (lines 19-104)

**Imports**:
```python
from src.utils.pit_join import pit_join_backward
from src.utils.category_map import MISSING   # "__MISSING__" sentinel（5走未満明示・D-13）
```

**呼出契約（必読）** — `pit_join.py:32-36, 75-94`:
- `observations` は `feature_cutoff_datetime` 昇順に、`history` は `as_of_datetime` 昇順に**事前ソート済み**で渡す（caller 責任）。
- 本関数は入力を再ソートしない。未ソート入力は即 `raise ValueError`（HIGH #1）。
- ガードは `assert` ではなく `raise ValueError`（`python -O` で削除されない・HIGH #3）。

**呼出イディオム**（`pit_join.py:96-104` の `merge_asof(direction="backward")` を消費）:
```python
# Step 1: caller 側で sort（pit_join_backward の契約）
history_sorted = history.sort_values(["kettonum", "as_of_datetime"])
obs_sorted = observations.sort_values(["kettonum", "feature_cutoff_datetime"])

# Step 2: defense-in-depth — history 側でも cutoff 以前のみ残す（Pitfall 3.1）
#   対象レース自身の当日行が row_number で混入するのを防ぐ二重化

# Step 3: cutoff 以前の最新行を付与
joined = pit_join_backward(
    observations=obs_sorted,
    history=history_sorted,
    on_cutoff="feature_cutoff_datetime",
    on_asof="as_of_datetime",
    by="kettonum",                 # 馬単位（D-02: horse_id=kettonum 採用）
    # tolerance は設定しない（5走 window は別途 row_number/cumcount で管理）
)
```

**3軸集約（D-04）+ sentinel（D-03/D-13）** — 03-RESEARCH.md Example 1 (lines 384-439) をそのまま適用:
```python
recent5 = joined[["kakuteijyuni_1", ..., "kakuteijyuni_5"]]
result["rolling_kakuteijyuni_mean_5"] = recent5.mean(axis=1)
result["rolling_kakuteijyuni_latest_5"] = recent5["kakuteijyuni_1"]
result["rolling_kakuteijyuni_sd_5"] = recent5.std(axis=1, ddof=1)
starts_count = recent5.notna().sum(axis=1)
result["rolling_kakuteijyuni_count_5"] = starts_count
# 5走未満（starts_count==0）→ 3軸とも __MISSING__（silent fill 禁止）
# sd は n<2 で定義不能 → __MISSING__（Pitfall 3.3）
```

---

### `src/features/running_style.py` (utility, 閾値ルール分類)

**Analog:** `src/etl/class_normalize.py:normalize_class` (lines 63-118) — dict/閾値ルールで分類し未対象は `unresolved` 相当（`__MISSING__`）で隔離。

**アルゴリズム** — 03-RESEARCH.md Example 2 (lines 444-481) をそのまま適用:
```python
def estimate_running_style(history_5starts: pd.DataFrame) -> str:
    """過去走 jyuni3c/jyuni4c の平均位置から逃/先/差/追を事前推定（D-05）。

    当日 kyakusitukubun (SE #73, post_race_only) は使用禁止（D-05・Pitfall: 当日リーク）。
    jyuni1c は57% が 0/NULL（短距離で1コーナー不存在）のため主軸にしない（Pitfall 3.2）。
    """
    if len(history_5starts) == 0:
        return "__MISSING__"                    # 新馬・D-13
    valid = history_5starts[
        (history_5starts["jyuni3c"] > 0) & (history_5starts["jyuni4c"] > 0)
    ]
    if len(valid) == 0:
        return "__MISSING__"                    # Pitfall 3.2
    avg_position = (valid["jyuni4c"].mean() + valid["jyuni3c"].mean()) / 2
    if avg_position <= 2.0:   return "逃"
    elif avg_position <= 3.5: return "先"
    elif avg_position <= 5.5: return "差"
    else:                     return "追"
```

---

### `src/features/snapshot.py` (utility, file I/O — PyArrow deterministic write)

**Analog:** **なし**（codebase に Parquet 書込実装が存在しない・`grep -rn "to_parquet\|pyarrow"` で src/scripts 配下は0件）。

**一次ソース:** 03-RESEARCH.md Pattern 2 (lines 254-296) + Example の byte-repro 実証。

**実装テンプレート**（03-RESEARCH.md Pattern 2 を正とする）:
```python
import hashlib
from datetime import datetime
import pyarrow as pa
import pyarrow.parquet as pq

def write_snapshot(
    df: pd.DataFrame,
    snapshot_id: str,
    parquet_path: str,
    *,
    label_version: str,
    fa_version: str,
    train_period: str,
    validation_period: str,
    created_at: datetime,            # 決定論的 sha256 のため manifest 側で実タイムスタンプを別管理
) -> str:
    """§12.4 8項目+sha256 を schema metadata に埋め込んだ byte-reproducible Parquet を書込。

    Returns: sha256 hexstring（manifest YAML に保存）
    """
    # 1. 決定論的 sort（row order 固定・canonical key は race_date,jyocd,racenum,kettonum）
    df_sorted = df.sort_values(
        ["race_date", "jyocd", "racenum", "kettonum"]
    ).reset_index(drop=True)
    # 2. schema metadata に §12.4 8項目を埋込
    schema = pa.Schema.from_pandas(df_sorted, preserve_index=False)
    schema = schema.with_metadata({
        b"dataset_version":            b"v1.0.0",
        b"feature_snapshot_id":        snapshot_id.encode(),
        b"label_version":              label_version.encode(),
        b"prediction_timing":          b"1A",                    # Phase 1-A 固定
        b"feature_cutoff_rule":        b"race_date - 1 day",     # D-06
        b"train_period":               train_period.encode(),
        b"validation_period":          validation_period.encode(),
        b"created_at":                 created_at.isoformat().encode(),
        b"feature_availability_version": fa_version.encode(),
    })
    table = pa.Table.from_pandas(df_sorted, schema=schema, preserve_index=False)
    # 3. 決定論的書込オプション（Pitfall 3.5）
    buf = pa.BufferOutputStream()
    pq.write_table(
        table, buf,
        use_dictionary=False,         # True だと辞書構築順で非決定論的になる可能性
        compression="zstd",
        write_statistics=True,
        row_group_size=128 * 1024 * 1024,   # 128 MiB（DuckDB zero-copy 読込効率）
    )
    data = buf.getvalue().to_pybytes()
    sha256 = hashlib.sha256(data).hexdigest()
    with open(parquet_path, "wb") as f:
        f.write(data)
    return sha256
```

**Pitfall 3.5 防止（unit test 必須）:** 同一 DataFrame から2回 write_snapshot を呼び、sha256 が完全一致することを assert（03-RESEARCH.md で実証済）。`created_at` を実タイムスタンプにすると非決定論的になるため、snapshot_id 生成時に固定タイムスタンプを渡し、manifest 側で実タイムスタンプを別管理。

**manifest YAML 構造**（planner が定義・`snapshots/feature_matrix_<id>.manifest.yaml`）:
```yaml
feature_snapshot_id: "20260618-1a-v1"
parquet_path: "snapshots/feature_matrix_20260618-1a-v1.parquet"
sha256: "<write_snapshot の戻り値>"
byte_size: <int>
row_count: <int>
feature_count: <int>
label_version: "v1.0.0"
feature_availability_version: "0.2.0"
prediction_timing: "1A"
feature_cutoff_rule: "race_date - 1 day"
train_period: "2016-07-01/2023-12-31"
validation_period: "2024-01-01/2024-12-31"
created_at: "<real timestamp>"     # 実タイムスタンプは此処のみ
category_map_artifact: "snapshots/category_map_20260618-1a-v1.joblib"
```

**`.gitignore` 対応:** Parquet バイナリ（`snapshots/*.parquet`）と joblib（`snapshots/*.joblib`）は必ず git 管理外。manifest YAML のみ git 管理候補（planner 判断・Open Question #2）。

---

### `src/features/category_map_consumer.py` (utility, frozen map fit/apply — consumer)

**Analog (消費元):** `src/utils/category_map.py` (lines 19-77)

**契約（必読）** — `category_map.py:24-50, 53-77`:
- `fit_category_map(series)` は**訓練窓 series のみ**で呼ぶ（test 構成リーク防止・§14.3）。
- val/test には `apply_category_map(series, code)` のみ（再 fit 禁止）。
- 未知値 → `__UNSEEN__`、NaN → `__MISSING__`、戻り値は**非負 int32**（pandas `category` dtype の `-1` ハザード回避・§14.3）。

**消費イディオム（Pitfall 3.4 回避）**:
```python
from src.utils.category_map import fit_category_map, apply_category_map

# train 窓（D-09: 2016H2-2023）の series のみで fit
train_mask = feature_matrix["race_date"].between("2016-07-01", "2023-12-31")
jockey_code = fit_category_map(
    feature_matrix.loc[train_mask, "kisyucode"].astype(str)
)   # 訓練窓 cardinality 実測: 358 騎手 / 398 調教師 / 42395 馬

# train/val/test 全行に同一 map を適用（train に無い ID は __UNSEEN__ へ自動フォールバック）
feature_matrix["jockey_id_code"] = apply_category_map(
    feature_matrix["kisyucode"].astype(str), jockey_code
)
# 18101 馬（train 窓外）は __UNSEEN__ になる（理論上上限・unit test で検査）
```

**永続化:** `joblib.dump({"jockey": jockey_code, "trainer": ..., ...}, "snapshots/category_map_<snapshot_id>.joblib")`。Parquet snapshot と同 snapshot_id で紐付け。

---

### `src/config/feature_availability.yaml` (modify — 枠から25エントリに拡充)

**Analog:** `src/config/label_spec.yaml` (構造・バージョン管理・実データ検証ノート) / `src/config/class_normalization.yaml` (map 形式)

**現在の枠**（`src/config/feature_availability.yaml:1-47`）:
- `schema_version: "0.1.0"`（Phase 3 で `"0.2.0"` に bump）
- `feature_schema:` 6項目スキーマ定義済み（`feature_name`/`feature_group`/`available_from_timing`/`source_table`/`cutoff_rule`/`leakage_risk_level`）
- `features: []` 空（Phase 1 D-15）

**拡充内容** — 03-RESEARCH.md Example 3 (lines 485-621) に drop-in 可能な25+エントリ一覧表あり。planner は同 Example を YAML へ転記:
- 静的属性 15種（`barei`/`sexcd`/`futan`/`jockey_id`/`trainer_id`/`sire_id`/`bms_id`/`jyocd`/`kyori`/`trackcd`/`course_kubun`/`class_code_normalized`/`umaban`/`wakuban`/`horse_id`）
- 過去走ローリング 9系統 × 3軸 = 27エントリ（`rolling_*_mean_5` / `rolling_*_latest_5` / `rolling_*_sd_5`）
- 推定脚質 1エントリ（`estimated_running_style`）

**全エントリ制約:**
- `available_from_timing ∈ {entry_confirmed, post_position_confirmed}` のみ（D-07）。禁止5種は登場させない。
- `cutoff_rule: "race_date - 1 day"` で一律（D-06）。
- `leakage_risk_level`: `low` または `medium`（horse_id のみ medium・高基数冷起動リスク）。
- `source_table` は `normalized.n_*` または `raw_everydb2.n_*`（readonly SELECT 許容範囲・D-06）。`sibababacd`/`dirtbabacd`/`tenkocd`/`odds`/`ninki` 等の禁止カラムは**エントリ自体を作らない**（allowlist が保護）。

**バージョン bump の意味:** `schema_version: "0.2.0"` は Phase 3 で features を初めて埋めたことを示す。snapshot metadata の `feature_availability_version` に同値を埋め込む（§19.1 再現性）。

---

### `scripts/run_feature_build.py` (CLI script — 新規想定)

**Analog:** `scripts/run_label_etl.py` (lines 1-131) — ほぼ同一構造。

**テンプレート**（`run_label_etl.py:46-127` を踏襲）:
```python
def main() -> int:
    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)   # masked のみ（生 DSN は出力厳禁）
    read_pool = make_pool(settings, role="readonly")        # feature builder は readonly のみ
    try:
        # raw 不変性は ETL ロールを使わないため不要だが、
        # label backfill も実行する場合は etl pool も構築して fingerprint before/after
        result = build_feature_matrix(read_pool, snapshot_id=..., ...)
        logger.info("feature matrix: rows=%d features=%d sha256=%s",
                    result["row_count"], result["feature_count"], result["sha256"])
        # SC#3 byte-reproducibility verify: もう1回書いて sha256 一致を assert
        return 0
    finally:
        read_pool.close()
```

**Imports** (`run_label_etl.py:24-37`): `_REPO_ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(_REPO_ROOT))` の sys.path 調整イディオムを必ず入れる（`scripts/` から `src.*` を import するため）。

---

### `src/etl/label_race_date_backfill.py` (ETL UPDATE — Phase 2 負債解消)

**Analog:** `src/etl/fukusho_label.py:_idempotent_load_label` (lines 940-1014) — staging-swap idempotent UPDATE パターン。

**背景:** `label.fukusho_label.race_date` は全 554267 行 NULL（Phase 2 負債・02-VERIFICATION.md Deferred #1）。Phase 3 の cutoff（D-06）に必要。

**アプローチ:** staging-swap で atomic に置換（UPDATE 直書きでなく、`normalized.n_race` と JOIN した結果を staging に積んで RENAME）。これにより再実行で重複せず、失敗時は元テーブルが残る。

**手順（`_idempotent_load_label` lines 964-1014 と同一構造）:**
1. `SELECT pg_advisory_xact_lock(hashtext('label.fukusho_label'))`（並行実行の直列化）
2. `CREATE TABLE label.fukusho_label_staging (LIKE label.fukusho_label INCLUDING ALL)`
3. `INSERT INTO label.fukusho_label_staging SELECT ..., nr.race_date FROM label.fukusho_label fl JOIN normalized.n_race nr ON (PK 結合)`
4. `SELECT count(*) FROM label.fukusho_label_staging` で rowcount 検証（元テーブルと一致・WR-06 idiom）
5. `DROP TABLE label.fukusho_label; ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label`
6. `GRANT SELECT ON label.fukusho_label TO {reader_role}`（psycopg.sql.Identifier・TO PUBLIC 不使用・HIGH #3）

**ロール:** `make_pool(role='etl')`（label スキーマ UPDATE 権限・Phase 2 GRANT_ETL_SQL）。search_path = `label,normalized,public`（`connection.py:44`）で `n_race` も解決可能。

**注意:** 既存 `fukusho_label` の PK/NOT NULL/comment は `INCLUDING ALL` で staging に継承される。列追加なし（`race_date date NULL` は既存）。

---

## Shared Patterns

### readonly ロール・raw read-only（D-06）

**Source:** `src/db/connection.py:make_pool` (lines 21-54) + `tests/conftest.py:readonly_cur` (lines 39-44)

**Apply to:** `src/features/builder.py`, `src/features/rolling.py`（history SELECT）, `scripts/run_feature_build.py`

```python
read_pool = make_pool(settings, role="readonly")  # search_path=public,normalized,label
with read_pool.connection() as conn:
    with conn.cursor() as cur:
        cur.execute(f"SELECT ... FROM normalized.n_uma_race WHERE {PROJECT_WINDOW_FILTER}")
```

feature builder は**全工程で readonly ロール**。DB への書込は `label_race_date_backfill.py` のみ（etl ロール）。

### JRA フィルタ単一ソース（CR-06）

**Source:** `src/etl/filters.py` (lines 31-60)

**Apply to:** 全 DB SELECT（`builder.py` / `rolling.py` / backfill JOIN）

```python
from src.etl.filters import PROJECT_WINDOW_FILTER, project_window_filter
# 単一テーブル: WHERE {PROJECT_WINDOW_FILTER}
# JOIN:        WHERE {project_window_filter('fl')} AND {project_window_filter('nr')}
```

三重定義禁止。`raw_fingerprint` は `JRA_FILTER`（year 制限なし）・ETL SELECT は `PROJECT_WINDOW_FILTER`（year>=2015）を使い分ける既存規約を維持。

### silent fallback 禁止（D-13 / Phase 1）

**Source:** `src/etl/fukusho_label.py:load_label_spec` (ValueError on missing keys) + `src/utils/category_map.py:MISSING` sentinel

**Apply to:** `availability.py`（必須キー欠損で ValueError）, `rolling.py`（5走未満は `__MISSING__`・pandas `mean()` の NaN 無視に頼らない）, `running_style.py`（新馬/通過順なしは `__MISSING__`）, `snapshot.py`（空入力は RuntimeError・`_idempotent_load` CR-04(a) 踏襲）

```python
# 必須キー検査（fukusho_label.py:107-109 パターン）
missing = [k for k in _REQUIRED_SPEC_KEYS if k not in spec]
if missing:
    raise ValueError(f"必須キー欠損: {missing} (D-13 silent fallback 禁止)")

# sentinel 明示（category_map.py:21 パターン）
from src.utils.category_map import MISSING   # "__MISSING__"
result.loc[no_starts, col] = MISSING         # NaN や 0 で埋めない
```

### リーク防止ガードは `raise ValueError`（HIGH #3）

**Source:** `src/utils/pit_join.py:86-94` + `tests/utils/test_pit_join.py:test_pit_join_no_assert_statement` (lines 167-172)

**Apply to:** `rolling.py`（未ソート入力検知は pit_join_backward が担当・builder 側でも sort 後に `is_monotonic_increasing` を assert しない）, `snapshot.py`（空入力・rowcount 不一致は RuntimeError）

`assert` は `python -O` で削除されるため、リーク防止・idempotent 保証のガードには使わない。`raise ValueError`/`RuntimeError` のみ。

### YAML loader パターン（Phase 1 D-07）

**Source:** `src/etl/class_normalize.py:load_class_config` (lines 37-51) + `src/etl/fukusho_label.py:load_label_spec` (lines 97-110)

**Apply to:** `src/features/availability.py:load_feature_availability`

```python
from pathlib import Path
import yaml
_DEFAULT_CONFIG_PATH = Path("src/config/feature_availability.yaml")

def load_feature_availability(path: str | Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(...)
    # 必須キー検査
    return spec
```

### staging-swap idempotent（HIGH #5 / HIGH #3）

**Source:** `src/etl/normalize.py:_idempotent_load` (lines 356-441) + `src/etl/fukusho_label.py:_idempotent_load_label` (lines 940-1014)

**Apply to:** `src/etl/label_race_date_backfill.py`（UPDATE を直書きせず staging-swap で冪等化）

コアステップ: advisory lock → 空入力拒否 → `CREATE _staging (LIKE ... INCLUDING ALL)` → TRUNCATE → INSERT → `SELECT count(*)` rowcount 検証 → DROP+RENAME → `GRANT SELECT TO {reader_role}`（Identifier・PUBLIC 不使用）。

### pytest パターン（KEIBA_SKIP_DB_TESTS + synthetic DataFrame + mock cursor）

**Source:** `tests/conftest.py` (lines 1-79) + `tests/utils/test_pit_join.py` + `tests/test_fukusho_label.py:_build_se_row` (lines 50-96) + `tests/test_normalized_etl.py:test_idempotent_load_refuses_empty_input_to_prevent_silent_data_loss` (lines 29-53)

**Apply to:** 全 `tests/features/test_*.py`

**1. DB skip policy（conftest.py:66-79）:**
```python
@pytest.mark.requires_db
def test_feature_matrix_real_db(readonly_cur): ...   # KEIBA_SKIP_DB_TESTS=1 で skip
```
`tests/features/conftest.py` は新設するが、DB skip policy はルート `tests/conftest.py` の `pytest_collection_modifyitems` が継承されるため再定義不要。共通 fixture（合成 uma_race / n_race DataFrame）のみ features 用 conftest に定義。

**2. synthetic DataFrame builder（test_fukusho_label.py:50-96 パターン）:**
```python
def _build_se_history_row(kettonum: int, race_date: str, **overrides) -> dict:
    """合成 n_uma_race history 行。実DBに依存せず deterministic に rolling を検証。"""
    row = {
        "kettonum": kettonum, "race_date": race_date,
        "kakuteijyuni": 1, "timediff": 0, "harontimel3": 1.0,
        "jyuni3c": 1, "jyuni4c": 1, "as_of_datetime": race_date,
    }
    row.update(overrides)
    return row
```

**3. mock cursor で idempotent/fail-fast を検証（test_normalized_etl.py:29-53）:**
```python
from unittest.mock import MagicMock
def test_backfill_refuses_empty_input():
    cur = MagicMock()
    with pytest.raises(RuntimeError, match="refusing to swap to empty"):
        _idempotent_load_label(cur, [], [...], reader_role="keiba_readonly")
```

**4. inspect.getsource で implementation guard（test_pit_join.py:81-97, 167-172）:**
```python
import inspect
def test_no_select_star_in_builder():
    """SC#2: builder が SELECT * を使わない（明示カラムのみ・Pitfall 1）。"""
    from src.features import builder
    src = inspect.getsource(builder)
    assert "SELECT *" not in src, "明示カラム SELECT のみ許可（anti-pattern）"
```

**5. parametrize で全エントリ網羅（allowlist test）:**
```python
@pytest.mark.parametrize("timing", list(BANNED_TIMINGS))
def test_no_banned_timing_in_yaml(timing, load_feature_availability):
    spec = load_feature_availability()
    matches = [f["feature_name"] for f in spec["features"]
               if f.get("available_from_timing") == timing]
    assert matches == [], f"禁止 timing {timing} の feature が存在: {matches} (SC#2)"
```

### masked DSN のみログ出力（MEDIUM #1 / HIGH #6）

**Source:** `src/config/settings.py:dsn_masked` (lines 80-94) + `scripts/run_label_etl.py:50-51`

**Apply to:** `scripts/run_feature_build.py`

```python
logger.info("readonly DSN: %s", settings.dsn_masked)   # *** マスク付き
# settings.dsn / settings.etl_dsn は絶対にログに出さない
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/features/snapshot.py` (PyArrow deterministic write) | utility | file-I/O | codebase に Parquet/PyArrow 書込実装が存在しない（`grep` で0件）。03-RESEARCH.md Pattern 2 (lines 254-296) が一次ソース。byte-repro 実証済み。 |
| `tests/features/test_snapshot_repro.py` (byte-reproducibility by hash) | test | — | 対応する既存テストパターンなし。SC#3 の「同一 DataFrame から同一 SHA256」を2回 write して assert する新規テスト。PyArrow のみ。 |

それ以外の13ファイルは全て codebase に exact または role-match の analog が存在する。Phase 3 は新規プリミティムを発明せず、Phase 1-2 のリーク防止 util（`pit_join_backward`/`fit_category_map`）と ETL イディオム（`_idempotent_load`/YAML loader/`make_pool`）を消費して組み合わせる設計（03-RESEARCH.md Don't Hand-Roll 節・"Phase 3 は既存の実証済契約に乗ることが最も安全"）。

---

## Metadata

**Analog search scope:**
- `/Users/hart/develop/keiba-ai-v3/src/**/*.py`（utils/・etl/・db/・config/）
- `/Users/hart/develop/keiba-ai-v3/tests/**/*.py`（conftest・utils/・test_normalized_etl・test_fukusho_label）
- `/Users/hart/develop/keiba-ai-v3/scripts/*.py`（run_label_etl・run_normalized_etl・run_apply_schema）
- `/Users/hart/develop/keiba-ai-v3/src/config/*.yaml`（label_spec・class_normalization・feature_availability・code_tables）

**Files scanned:** 14 ソースファイル + 4 YAML + 2 VERIFICATION.md（Phase 1/2）

**Pattern extraction date:** 2026-06-18

**Key insight for planner:** Phase 3 の実装難所は (a) `pit_join_backward` の事前ソート契約を builder/rolling が遵守すること、(b) 明示カラム SELECT で禁止カラムを構造的に排除すること（allowlist が監査）、(c) PyArrow 決定論的書込オプション（`use_dictionary=False`, `compression="zstd"`, sorted input）を厳守すること、(d) `fit_category_map` を train 窓のみで呼ぶこと（test 構成リーク防止）。これら4点は unit test で構造的に検証可能（SC#1-#4 + Pitfall 3.1-3.6 対応）。
