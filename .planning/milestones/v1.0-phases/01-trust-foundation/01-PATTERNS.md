# Phase 1: Trust & Foundation - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 25 new files（greenfield — 既存 `src/` コードなし）
**Analogs found:** 0 / 25（in-repo analogs なし — 全ファイルが新規作成）

> **本フェーズの特性:** Phase 1 は本プロジェクトの最初のフェーズであり、コードベースは空である（CONTEXT.md `<code_context>` 参照）。従って** in-repo analog は1件も存在しない**。各ファイルの「パターンソース」は、(a) `01-RESEARCH.md` の検証済みモジュール仕様＋コード例、(b) `CLAUDE.md` のリーク防止設定、(c) `docs/keiba_ai_requirements_v1.3.md` §17.2（`src/` パッケージレイアウト）、および (d) PyPI で検証済みの標準ライブラリ API（`pandas.merge_asof` / `mlxtend.GroupTimeSeriesSplit` / `CalibratedClassifierCV` / psycopg3）である。planner は各ファイルの「推奨イディオム」と「根拠となる仕様セクション」を直接 PLAN.md の action に転記すること。

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | config | — | NEW (no existing analog — greenfield) | none |
| `.gitignore` | config | — | NEW (no existing analog — greenfield) | none |
| `.env.example` | config | — | NEW (no existing analog — greenfield) | none |
| `src/config/settings.py` | config | request-response (`.env`→DSN) | NEW (no existing analog — greenfield) | none |
| `src/config/class_normalization.yaml` | config | transform (code→class_level) | NEW (no existing analog — greenfield) | none |
| `src/config/code_tables.yaml` | config | transform (code→name) | NEW (no existing analog — greenfield) | none |
| `src/config/feature_availability.yaml` | config | registry (§13.3) | NEW (no existing analog — greenfield) | none |
| `src/db/connection.py` | db | request-response (pool/conn) | NEW (no existing analog — greenfield) | none |
| `src/db/schema.py` | db | DDL (5層スキーマ作成) | NEW (no existing analog — greenfield) | none |
| `src/etl/quality_gate.py` | etl | PostgreSQL SELECT → report | NEW (no existing analog — greenfield) | none |
| `src/etl/normalize.py` | etl | raw(`n_*`) → normalized | NEW (no existing analog — greenfield) | none |
| `src/etl/class_normalize.py` | etl | code変換（`jyokencd5`+`gradecd`） | NEW (no existing analog — greenfield) | none |
| `src/utils/pit_join.py` | utility | `merge_asof` backward join | NEW (no existing analog — greenfield) | none |
| `src/utils/group_split.py` | utility | CV generator (group-aware) | NEW (no existing analog — greenfield) | none |
| `src/utils/category_map.py` | utility | fit/apply (frozen map) | NEW (no existing analog — greenfield) | none |
| `src/utils/calibrator.py` | utility | fit prefit calibrator | NEW (no existing analog — greenfield) | none |
| `scripts/run_quality_report.py` | report-script | ETL → `reports/*.md`+`.json` | NEW (no existing analog — greenfield) | none |
| `scripts/run_normalized_etl.py` | report-script | ETL runner | NEW (no existing analog — greenfield) | none |
| `tests/conftest.py` | test | pytest fixtures | NEW (no existing analog — greenfield) | none |
| `tests/test_quality_gate.py` | test | unit/integration | NEW (no existing analog — greenfield) | none |
| `tests/test_normalized_etl.py` | test | integration | NEW (no existing analog — greenfield) | none |
| `tests/test_raw_immutability.py` | test | integration (raw hash assert) | NEW (no existing analog — greenfield) | none |
| `tests/test_class_normalization.py` | test | unit | NEW (no existing analog — greenfield) | none |
| `tests/utils/test_pit_join.py` | test | smoke (sortedness raise) | NEW (no existing analog — greenfield) | none |
| `tests/utils/test_group_split.py` | test | smoke (race_id disjoint) | NEW (no existing analog — greenfield) | none |
| `tests/utils/test_category_map.py` | test | smoke (`__UNSEEN__` fallback) | NEW (no existing analog — greenfield) | none |
| `tests/utils/test_calibrator.py` | test | smoke (時系列順序 assert) | NEW (no existing analog — greenfield) | none |

> 計 27 ファイル（主要 `src/` 8 + `scripts/` 2 + `tests/` 8 + ルート設定 4 + config YAML 4 + pyproject 1 = 27。分類表の代表 27 行）。

---

## Pattern Assignments

> 全ファイル greenfield のため、analog は「仕様根拠（spec citation）＋推奨ライブラリイディオム」で代用する。各エントリの **Spec根拠** が planner が PLAN.md の action に書くべき正情報。

### `pyproject.toml` (config)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `docs/keiba_ai_requirements_v1.3.md` §17.1, `01-RESEARCH.md`「Standard Stack」+「Installation」, CLAUDE.md「Recommended Stack」
**推奨イディオム:**
```toml
[project]
requires-python = ">=3.12,<3.13"        # §17.1 固定。3.13 は CatBoost wheel ラグで回避

[tool.uv]
# uv sync --frozen で byte 再現性（§19.1）

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
# §17.1 単一設定。line-length 等は planner で決定
```
**依存（Phase 1 サブセット）:** `psycopg[binary]==3.3.4`, `psycopg-pool==3.3.1`, `pandas==3.0.3`, `pyarrow==24.0.0`, `duckdb==1.5.3`, `scikit-learn==1.9.0`, `mlxtend==0.25.0`, `pydantic`, `pydantic-settings==2.14.1` / dev: `ruff==0.15.17`, `pytest==9.1.0`（`01-RESEARCH.md` Standard Stack 表の version を厳守。LightGBM/CatBoost/Streamlit/plotly は Phase 1 では追加しない）

---

### `.gitignore` (config)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** CLAUDE.md「What NOT to Use」（`__pycache__`/Parquet/models を Git から除外）, §19.1（再現性は code + `uv.lock` + Postgres + snapshot metadata）
**推奨内容:** `.env`, `data/`, `models/`, `__pycache__/`, `.venv/`, `*.parquet`, `.pytest_cache/`, `.ruff_cache/`。`reports/` は成果物なので**除外しない**（`01-RESEARCH.md`「Recommended Project Structure」明示）。

---

### `.env.example` (config)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** CONTEXT.md「Claude's Discretion 接続設定管理」, anti-pattern #20（機密値は `.env` のみ、planning 文書に書かない）, `01-RESEARCH.md`「Wave 0 Gaps」
**推奨イディオム:**（値はプレースホルダ、実パスワード禁止）
```dotenv
# .env.example（雛形のみ。実値はローカル .env に限定）
KEIBA_DB_NAME=everydb2
KEIBA_DB_USER=<readonly role>
KEIBA_DB_PASSWORD=<your-password-here>
KEIBA_DB_HOST=localhost
KEIBA_DB_PORT=5432
KEIBA_DB_SCHEMA_RAW=public          # n_* 確定テーブルが存在する物理スキーマ
KEIBA_DB_SCHEMA_NORMALIZED=normalized
```
**注意:** planner は実際の `everydb2` 配置（`public.n_*`、`01-RESEARCH.md` Sources で検証済み）と論理 `raw_everydb2` のマッピングを `src/db/schema.py` で解決する。

---

### `src/config/settings.py` (config, request-response)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `01-RESEARCH.md`「Don't Hand-Roll」表（DB接続 → psycopg3 + psycopg_pool + pydantic-settings）, anti-pattern #20
**推奨イディオム:**
```python
# pydantic-settings 2.14.1（01-RESEARCH.md Standard Stack Supporting 表）
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KEIBA_", env_file=".env", extra="ignore")

    db_name: str
    db_user: str
    db_password: SecretStr       # ログ出力でマスク（01-RESEARCH.md「Threat Patterns」）
    db_host: str = "localhost"
    db_port: int = 5432
    db_schema_raw: str = "public"
    db_schema_normalized: str = "normalized"

    @property
    def dsn(self) -> str:
        pw = self.db_password.get_secret_value()
        return f"postgresql://{self.db_user}:{pw}@{self.db_host}:{self.db_port}/{self.db_name}"
```
**キャッチすべき失敗:** DSN のログ出力（Information Disclosure）→ `SecretStr` でマスク。

---

### `src/config/class_normalization.yaml` (config, transform)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `01-RESEARCH.md`「クラス正規化完全対応表（実データ検証済み）」, DATA-03 / D-09/D-11/D-12/D-13, `docs/keiba_ai_requirements_v1.3.md` §12.3
**推奨内容:**（本 RESEARCH の対応表を直接転記。これが DATA-03 の「正」。planner は行を省略せず全コード値を含めること）
```yaml
# DATA-03 の正。01-RESEARCH.md「クラス正規化完全対応表」より直接転記。
post_2019_class_system_reform_date: "2019-06-08"   # D-11 実測確認（夏季競馬開催初日）

jyokencd5_map:                # 実測: JRA限定（jyocd BETWEEN '01' AND '10'）の6値
  "701": {class_level_numeric: 0, class_name_normalized: "新馬",       note: "§7.3 モデル対象外だが保存"}
  "703": {class_level_numeric: 0, class_name_normalized: "未勝利",     note: "§7.3 モデル対象外だが保存"}
  "005": {class_level_numeric: 1, class_name_normalized: "1勝クラス",  note: "2019年前: 500万下"}
  "010": {class_level_numeric: 2, class_name_normalized: "2勝クラス",  note: "2019年前: 1000万下"}
  "016": {class_level_numeric: 3, class_name_normalized: "3勝クラス",  note: "2019年前: 1600万下"}
  "999": {class_level_numeric: 4, class_name_normalized: "OP・重賞",   note: "gradecd で細分"}

gradecd_map:                  # 実測10値。gradecd 単独から機械導出（D-12、名称マッチ不使用）
  "A": {grade_numeric: 1, is_grade_race: true,  is_listed: false}
  "B": {grade_numeric: 2, is_grade_race: true,  is_listed: false}
  "C": {grade_numeric: 3, is_grade_race: true,  is_listed: false}
  "D": {grade_numeric: 3, is_grade_race: true,  is_listed: false, note: "A1: 障害G3可能性。ETLでsyubetucd交差確認推奨"}
  "L": {grade_numeric: null, is_grade_race: false, is_listed: true}
  "E": {grade_numeric: null, is_grade_race: false, is_listed: false, is_open_class: true}  # 999+E のみ
  "":  {grade_numeric: null, is_grade_race: false, is_listed: false, is_open_class: false}  # 一般条件戦
# F/G/H（障害等）は個別確認 → unresolved 扱い候補（D-13）

unresolved_strategy: "error_and_isolate"   # D-13 silent fallback 禁止
```

---

### `src/config/code_tables.yaml` (config, transform)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** CONTEXT.md canonical_refs（`docs/everydb2/CODE.md` は不完全 D-10）、`01-RESEARCH.md` Pitfall 3（CODE.md 過信禁止）
**推奨イディオム:** track code (`jyocd` 01-10)、`syubetucd`（障害=18/19 は §7.3 除外）等の補助コード表。ただし** CODE.md を正とせず**、実データ `SELECT DISTINCT` で裏取りした値のみ記載（Pitfall 3）。planner は実装タスクで `SELECT jyocd, count(*) FROM n_race GROUP BY jyocd` 等を実行して値を確定すること。

---

### `src/config/feature_availability.yaml` (config, registry)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `docs/keiba_ai_requirements_v1.3.md` §13.3-13.5, D-15（Phase 1 は枠＋項目定義のみ、本格運用と allowlist test は Phase 3）
**推奨内容:**（Phase 1 は空エントリのスキーマ定義のみ）
```yaml
# §13.3 項目: feature_name / feature_group / available_from_timing /
#            source_table / cutoff_rule / leakage_risk_level
# Phase 1 では schema のみ。実エントリと allowlist test は Phase 3。
features: []
# 例（Phase 3 で追加）:
#   - feature_name: jockey_win_rate_1y
#     feature_group: jockey
#     available_from_timing: 1A   # 出馬表確定後
#     source_table: normalized.n_uma_race
#     cutoff_rule: "race_date - 1 day"
#     leakage_risk_level: low
schema_version: "0.1.0"
```

---

### `src/db/connection.py` (db, request-response)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `01-RESEARCH.md`「Don't Hand-Roll」表, §12.1（PostgreSQL が system of record）, CLAUDE.md（psycopg3 固定・legacy psycopg2 禁止）
**推奨イディオム:**
```python
# psycopg3 + psycopg_pool 3.3.1（01-RESEARCH.md Standard Stack）
from contextlib import contextmanager
from psycopg import connect
from psycopg_pool import ConnectionPool
from src.config.settings import Settings

def make_pool(settings: Settings, min_size: int = 1, max_size: int = 8) -> ConnectionPool:
    return ConnectionPool(
        conninfo=settings.dsn,
        min_size=min_size, max_size=max_size,
        kwargs={"options": f"-c search_path={settings.db_schema_raw},public"},
        # raw スキーマは読取専用ロールで接続（D-06 二重保護）
    )

@contextmanager
def readonly_cursor(pool: ConnectionPool):
    with pool.connection() as conn:
        # D-06: raw への UPDATE/DELETE をロールベースで防止（REVOKE UPDATE,DELETE）
        with conn.cursor() as cur:
            yield cur
```
**キャッチすべき失敗:** ETL 書込接続と raw 読取接続を混ぜる → 接続を使い分ける設計（raw は readonly ロール、normalized への書込は別ロール）。

---

### `src/db/schema.py` (db, DDL)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-02 / D-05（PostgreSQL 別スキーマ5層、§12.2 論理層に1:1）, `01-RESEARCH.md`「Pattern 2: raw read-only 二重保護」
**推奨イディオム:**
```python
# 5層スキーマ作成DDL。raw_everydb2 は VIEW（public.n_* を論理参照、read-only）
SCHEMAS = ["raw_everydb2", "normalized", "label", "prediction", "backtest"]

CREATE_RAW_VIEW = """
CREATE SCHEMA IF NOT EXISTS raw_everydb2;
-- raw_everydb2.n_race は public.n_race への VIEW（D-05/01-RESEARCH.md Architectural Responsibility Map）
CREATE OR REPLACE VIEW raw_everydb2.n_race AS SELECT * FROM public.n_race;
-- 他の n_* テーブルも同様
"""

CREATE_NORMALIZED = """
CREATE SCHEMA IF NOT EXISTS normalized;
-- normalized 層のテーブル定義は src/etl/normalize.py 側で型付き CREATE TABLE
"""

REVOKE_RAW_WRITES = """
-- D-06 二重保護（ロールベース）
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM etl_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2
  REVOKE UPDATE, DELETE, TRUNCATE FROM etl_role;
"""
```

---

### `src/etl/quality_gate.py` (etl, PostgreSQL SELECT → report)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-01 / D-01/D-02/D-03/D-04, `docs/keiba_ai_requirements_v1.3.md` §6.4（品質チェック9項目）, `01-RESEARCH.md`「Pattern 1: Hybrid Quality Gate」+「Example 1」+ Pitfall 1/2/4
**推奨イディオム:**（`01-RESEARCH.md` Example 1 をほぼそのまま採用。planner は action に Example 1 のコードを引用すること）
```python
# 01-RESEARCH.md「Code Examples / Example 1」より
from dataclasses import dataclass, asdict
from psycopg import Cursor

@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str            # "block" | "info"  — D-01 ハイブリッドゲート
    detail: dict

# BLOCK（D-01 構造的欠陥 = pytest/CI fail）
#   - 主要5系統テーブル存在: n_race/n_uma_race/n_harai/n_hyosu/n_odds_tanpuku
#   - jra_since_2015_exists（成功基準#1）
#   - n_race PK 一意（実測: 39,593件 全件 unique）
#   - n_uma_race 自然キー一意 (year||jyocd||kaiji||nichiji||racenum||umaban||kettonum)
# INFO（量的異常 = 参考レポート）: NULL率・文字化け・code=0 割合

# Pitfall 2 必須: 全クエリで WHERE jyocd BETWEEN '01' AND '10'（JRA限定）
# Pitfall 4 必須: n_* のみ、s_*（速報）は対象外
# Pitfall 1 対応: 数値カラム（kyori/futan/hassotime）のキャスト成功率を INFO で出力

def run_quality_gate(cur: Cursor) -> dict:
    ...
    verdict = "pass" if all(r.passed for r in results if r.severity == "block") else "fail"
    return {"verdict": verdict, "checks": [asdict(r) for r in results]}
```
**出力:** D-04 — `reports/quality_report.md`（人間用）+ `reports/quality_report.json`（機械判定用、`verdict` 含む）

---

### `src/etl/normalize.py` (etl, raw→normalized)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-02 / D-06/D-08, `docs/keiba_ai_requirements_v1.3.md` §12.1-12.2, `01-RESEARCH.md` Pitfall 1（全 varchar の明示キャスト）, D-08（psycopg3 + Python 明示実装、DuckDB は補助のみ）
**推奨イディオム:**
```python
# D-08: psycopg3 + Python で明示的実装。可読・テスト可能。
# Pitfall 1: 全 varchar → 明示的キャストを最初のステップで実施
#   kyori      → CAST(kyori AS integer)
#   futan      → CAST(CAST(futan AS numeric)/10.0 AS real)   (単位 0.1kg)
#   hassotime  → to_timestamp(...)
#   year||monthday → date

# raw から SELECT（readonly ロール）→ pandas/psycopg3 で型変換 → normalized スキーマへ INSERT
# raw は絶対に UPDATE/DELETE しない（成功基準#2、tests/test_raw_immutability.py で保証）
```
**キャッチすべき失敗:** DuckDB で永続化（§12.1 禁止）。DuckDB は集計の補助のみ。

---

### `src/etl/class_normalize.py` (etl, code変換)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-03 / D-09/D-10/D-11/D-12/D-13, `01-RESEARCH.md`「クラス正規化完全対応表」, Pitfall 7（`hondai` 名称マッチ禁止・`jyokencd5`+`gradecd`+`year` 機械導出）
**推奨イディオム:**
```python
# src/config/class_normalization.yaml を読込 → 適用
# 入力: normalized.n_race の jyokencd5, gradecd, year, monthday, jyocd, syubetucd
# 出力列: class_code_normalized / class_name_normalized / class_level_numeric /
#         post_2019_class_system_flag / is_grade_race / is_listed / is_open_class /
#         grade_numeric / class_normalization_status

# post_2019_class_system_flag:
#   race_date >= "2019-06-08"  (定数、01-RESEARCH.md 実測確認)

# D-13: 未知コード（jyokencd5/gradecd が対応表にない）→
#   class_normalization_status='unresolved' として記録・隔離
#   WARNING ログ + 件数レポート（silent fallback 禁止）

# Pitfall 7 核心: 名称（hondai）の regex マッチは一切使わない
```

---

### `src/utils/pit_join.py` (utility, merge_asof backward join)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#4 / D-14/D-16/D-17, CLAUDE.md「 Leakage-prevention configuration §3」, `01-RESEARCH.md`「Example 2」, Pitfall 5（sortedness 未チェック）
**推奨イディオム:**（`01-RESEARCH.md` Example 2 をほぼそのまま。**planner は Example 2 のコードブロック全文を PLAN.md action に引用すること**）
```python
# 01-RESEARCH.md「Code Examples / Example 2」より（全体を転記）
import pandas as pd

def pit_join_backward(
    observations: pd.DataFrame,    # feature_cutoff_datetime, horse_id, ...
    history: pd.DataFrame,         # as_of_datetime, horse_id, feature_value
    on_cutoff: str = "feature_cutoff_datetime",
    on_asof: str = "as_of_datetime",
    by: str | list[str] = "horse_id",
    tolerance: pd.Timedelta | None = None,
) -> pd.DataFrame:
    """merge_asof(direction='backward') のリーク防止 wrapper。未来情報が cutoff を跨がないことを保証（§13）。"""
    obs = observations.sort_values(on_cutoff)
    hist = history.sort_values(on_asof)
    # D-17 sortedness raise smoke test 対象
    if not obs[on_cutoff].is_monotonic_increasing:
        raise ValueError(f"observations must be sorted by {on_cutoff}")
    if not hist[on_asof].is_monotonic_increasing:
        raise ValueError(f"history must be sorted by {on_asof}")
    return pd.merge_asof(
        obs, hist,
        left_on=on_cutoff, right_on=on_asof,
        by=by, direction="backward",
        tolerance=tolerance,
    )
```
**smoke test 要件（D-17）:** 未ソート入力で `ValueError` が raise されること。

---

### `src/utils/group_split.py` (utility, CV generator)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#4 / D-14/D-16/D-17, CLAUDE.md「§5 Time-series validation」, `01-RESEARCH.md`「Example 3」, §8.4（同一 race_id の train/test またぎ禁止）
**推奨イディオム:**（2系統の実装候補。planner は mlxtend を主、カスタムを副に）
```python
# 主: mlxtend.evaluate.GroupTimeSeriesSplit（01-RESEARCH.md Standard Stack, version 0.25.0）
#   sklearn.TimeSeriesSplit は group 非対応（#19072 open）のため使用禁止
from mlxtend.evaluate import GroupTimeSeriesSplit
# splitter = GroupTimeSeriesSplit(...)
# groups=race_id を渡す

# 副: 01-RESEARCH.md「Example 3」のカスタム race_id_time_series_split も実装
#   （mlxtend の policy が BT-1..BT-5 に合わない場合の fallback）
#   D-17: yield 前に assert set(train_rids).isdisjoint(set(test_rids))
```
**smoke test 要件（D-17）:** race_id が train/test で disjoint である assert。

---

### `src/utils/category_map.py` (utility, fit/apply frozen map)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#4 / D-14/D-16/D-17, CLAUDE.md「§1 Categorical handling — LightGBM」+「Leakage-prevention configuration」, `01-RESEARCH.md`「Example 4」, §14.3/14.5
**推奨イディオム:**（`01-RESEARCH.md` Example 4 をほぼそのまま）
```python
# 01-RESEARCH.md「Code Examples / Example 4」より
import pandas as pd

UNSEEN = "__UNSEEN__"
MISSING = "__MISSING__"

def fit_category_map(series: pd.Series) -> dict[str, int]:
    """訓練窓でのみ fit。未知/欠損の sentinel を含む安定マップを返す。"""
    cats = sorted(series.dropna().astype(str).unique().tolist())
    code = {c: i for i, c in enumerate(cats)}
    code[UNSEEN] = len(code)
    code[MISSING] = len(code)       # §14.5 欠損理由区別
    return code

def apply_category_map(series: pd.Series, code: dict[str, int]) -> pd.Series:
    s = series.astype(str).where(series.notna(), MISSING)
    return s.map(code).fillna(code[UNSEEN]).astype("int32")  # §14.3 非負 int32
```
**smoke test 要件（D-17）:** 未知値が `__UNSEEN__` にフォールバックすること。コードが非負 int32 であること。

---

### `src/utils/calibrator.py` (utility, fit prefit calibrator)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#4 / D-14/D-16/D-17, CLAUDE.md「§4 Calibration」, `01-RESEARCH.md`「Example 5」, §15.2/15.3
**推奨イディオム:**（`01-RESEARCH.md` Example 5 をほぼそのまま。sklearn 1.9.0 の `estimator=` 引数に注意）
```python
# 01-RESEARCH.md「Code Examples / Example 5」より
from sklearn.calibration import CalibratedClassifierCV

def fit_prefit_calibrator(
    base_estimator,            # 既に TRAIN で fit 済み
    X_calib, y_calib, race_dates_calib,
    train_max_date, method: str = "isotonic",   # <1000 sample なら "sigmoid"
):
    # D-17 時系列順序 assert
    assert train_max_date < race_dates_calib.min(), (
        "calibration slice must be strictly later than training "
        f"(train_max={train_max_date}, calib_min={race_dates_calib.min()})"
    )
    cal = CalibratedClassifierCV(estimator=base_estimator, method=method, cv="prefit")
    cal.fit(X_calib, y_calib)
    return cal
```
**smoke test 要件（D-17）:** `train_max_date >= calib.min()` で AssertionError。本物の LightGBM 不要（dummy estimator で検証可、`01-RESEARCH.md` Standard Stack 注記）。

---

### `scripts/run_quality_report.py` (report-script, ETL → reports/)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** D-04（`reports/` の Markdown+JSON 出力）, `01-RESEARCH.md`「Architecture Patterns / System Architecture Diagram」
**推奨イディオム:** `src.etl.quality_gate.run_quality_gate(cur)` を呼び出し → `reports/quality_report.md`（人間用 Markdown）+ `reports/quality_report.json`（機械判定用、`verdict` 含む）を書き出し。`argparse` で `--output-dir reports/` 等のオプション。CI から `verdict == "pass"` でなければ exit 1。

---

### `scripts/run_normalized_etl.py` (report-script, ETL runner)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** D-08（psycopg3 Python ETL）, `01-RESEARCH.md`「Recommended Project Structure」
**推奨イディオム:** `src.etl.normalize` + `src.etl.class_normalize` を順次起動するエントリポイント。raw readonly pool と normalized 書込接続を使い分け。実行前後で `tests/test_raw_immutability.py` の指紋取得ロジックを呼び出し raw 不変をログ出力（成功基準#2）。

---

### `tests/conftest.py` (test, fixtures)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** `01-RESEARCH.md`「Wave 0 Gaps」, §17.3
**推奨イディオム:**
```python
import pytest
from src.db.connection import make_pool
from src.config.settings import Settings

@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()           # .env から読込

@pytest.fixture(scope="session")
def pg_pool(settings):
    pool = make_pool(settings)
    yield pool
    pool.close()

@pytest.fixture
def readonly_cur(pg_pool):
    with pg_pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
```
**セキュリティ:** 実 DB パスワードは `.env` のみ（anti-pattern #20）。CI では別途 secret injection。

---

### `tests/test_quality_gate.py` (test, unit/integration)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-01 / D-01, `01-RESEARCH.md`「Validation Architecture / Test Map」, §17.3
**推奨テスト:**
- `test_blocking_checks` — 構造的欠陥（2015以降なし/PK重複）で BLOCK / `verdict=="fail"`
- `test_pass_when_clean` — 実 DB に対し `verdict=="pass"` を確認（integration）
- `test_jra_only_filter` — Pitfall 2（`jyocd BETWEEN '01' AND '10'`）で NAR 除外を確認

---

### `tests/test_normalized_etl.py` (test, integration)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-02 / D-08, §17.3
**推奨テスト:**
- 型キャスト成功（Pitfall 1）: `kyori` が int、`futan` が real
- code 変換: `jyocd='05'` → track_name="東京"
- normalized テーブル件数 ≈ raw の JRA 件数

---

### `tests/test_raw_immutability.py` (test, integration — 成功基準#2)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#2 / D-06, `01-RESEARCH.md`「Pattern 2: raw read-only 二重保護」
**推奨イディオム:**（`01-RESEARCH.md` Pattern 2 のコードを採用。全表 string_agg は重いので注意書き通り代表サンプル＋`pg_stat_user_tables.n_tup_upd/n_tup_del==0` の組み合わせ）
```python
# 01-RESEARCH.md「Pattern 2」より（概念）
def test_raw_unchanged_after_etl(pg_pool):
    # ETL 前: 代表サンプル（例: 特定日の n_race 全行）の md5 指紋
    # ETL 実行: scripts/run_normalized_etl.py 相当
    # ETL 後: 同じ指紋 → assert before == after
    # 補助: pg_stat_user_tables で n_tup_upd==0, n_tup_del==0 を確認
```

---

### `tests/test_class_normalization.py` (test, unit)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** DATA-03 / D-09/D-11/D-12/D-13, §17.3（クラス正規化テスト明示）, `01-RESEARCH.md`「Validation Architecture / Test Map」, Pitfall 7
**推奨テスト:**
- `test_code_005_spans_reform` — `jyokencd5='005'` が 2018/2019 で同じ `class_level_numeric=1`（Pitfall 7 核心）
- `test_reform_date` — `post_2019_class_system_flag` が `2019-06-08` 境界で切り替わる
- `test_grade_derivation` — `gradecd='A'` → `is_grade_race=True, grade_numeric=1`
- `test_unresolved_code_isolated` — 未知コード → `class_normalization_status='unresolved'`、silent fallback なし（D-13）

---

### `tests/utils/test_pit_join.py`, `test_group_split.py`, `test_category_map.py`, `test_calibrator.py` (test, smoke)

**Analog:** NEW (no existing analog — greenfield)
**Spec根拠:** 成功基準#4 / D-14/D-17, `01-RESEARCH.md`「Validation Architecture / Test Map」
**推奨テスト（各ファイルの D-17 assert）:**
- `test_pit_join.py`: 未ソート入力 → `ValueError`
- `test_group_split.py`: `set(train) ∩ set(test) == ∅` の assert
- `test_category_map.py`: 未知値 → `__UNSEEN__`、NaN → `__MISSING__`、コード非負 int32
- `test_calibrator.py`: `train_max_date >= calib.min()` → AssertionError。dummy estimator 使用（本物 LightGBM 不要）

---

## Shared Patterns

> 全ファイル greenfield のため、共有パターンは「プロジェクト横断的なイディオム」として定義する。planner は該当ファイルの PLAN.md action にこれらを引用すること。

### 1. DB 接続・設定（anti-pattern #20 準拠）

**Apply to:** `src/config/settings.py`, `src/db/connection.py`, `tests/conftest.py`, `scripts/*.py`
**根拠:** CONTEXT.md「Claude's Discretion 接続設定管理」, `01-RESEARCH.md`「Don't Hand-Roll」, CLAUDE.md「Supporting Libraries」
**イディオム:**
```python
# pydantic-settings BaseSettings + SecretStr
# psycopg3 + psycopg_pool（legacy psycopg2 禁止）
# raw は readonly ロール、normalized 書込は別ロール（D-06 二重保護）
```

### 2. raw 不変性（成功基準#2）

**Apply to:** `src/etl/normalize.py`, `src/etl/class_normalize.py`, `tests/test_raw_immutability.py`, `src/db/schema.py`
**根拠:** D-05/D-06, §12.2, `01-RESEARCH.md`「Pattern 2」
**イディオム:**
- raw (`public.n_*`) を VIEW として `raw_everydb2` から参照（UPDATE/DELETE 発行不可）
- ETL ロールに `REVOKE UPDATE, DELETE, TRUNCATE`
- pytest で代表サンプルの行ハッシュ + `pg_stat_user_tables` で ETL 前後不変を assert

### 3. EveryDB2 固有の varchar・NAR・s_*/n_* 対策

**Apply to:** `src/etl/quality_gate.py`, `src/etl/normalize.py`, `src/etl/class_normalize.py`
**根拠:** `01-RESEARCH.md` Pitfall 1/2/4
**イディオム:**
- **Pitfall 1（全 varchar）:** 最初のステップで明示的キャスト（`CAST(kyori AS integer)`, `futan` は `/10.0` 等）
- **Pitfall 2（NAR 混入）:** 全クエリで `WHERE jyocd BETWEEN '01' AND '10'`
- **Pitfall 4（s_*/n_*）:** `n_*`（確定）のみ扱い、`s_*`（速報）は対象外

### 4. リーク防止 assert（成功基準#4 / D-17）

**Apply to:** `src/utils/*.py`, `tests/utils/test_*.py`
**根拠:** CLAUDE.md「Leakage-prevention configuration」, `01-RESEARCH.md` Pitfall 5 + Examples 2-5
**イディオム:**
- `pit_join`: sortedness 事前チェック → `raise ValueError`
- `group_split`: `set(train_rids).isdisjoint(set(test_rids))` assert
- `category_map`: 非負 int32 + `__UNSEEN__`/`__MISSING__` sentinel
- `calibrator`: `train_max_date < calib.min()` assert（時系列分離）

### 5. クラス正規化はコード基準・名称不使用（Pitfall 7）

**Apply to:** `src/etl/class_normalize.py`, `src/config/class_normalization.yaml`, `tests/test_class_normalization.py`
**根拠:** DATA-03 / D-09/D-12/D-13, `01-RESEARCH.md`「クラス正規化完全対応表」, `.planning/research/PITFALLS.md` Pitfall 7
**イディオム:**
- `jyokencd5`+`gradecd`+`year`（+ `monthday`/`jyocd`）の機械導出
- `hondai`（レース名）の regex マッチは**一切使用しない**
- 未知コードは `class_normalization_status='unresolved'` で隔離（D-13 silent fallback 禁止）
- `post_2019_class_system_flag` は定数 `2019-06-08` 基準

### 6. レポート出力フォーマット（D-04）

**Apply to:** `src/etl/quality_gate.py`, `scripts/run_quality_report.py`
**根拠:** D-04, §6.4
**イディオム:**
- `reports/quality_report.md`（人間用 Markdown）
- `reports/quality_report.json`（機械判定用、`{"verdict": "pass"|"fail", "checks": [...]}`）
- `reports/` は `.gitignore` 対象外（成果物）

---

## No Analog Found

**全 27 ファイルが in-repo analog なし（greenfield）。** planner は本 PATTERNS.md の「Spec根拠」と「推奨イディオム」と `01-RESEARCH.md` の Code Examples（Example 1-5）を正として PLAN.md を構成すること。外部ライブラリのドキュメント（`pandas.merge_asof`, `mlxtend.GroupTimeSeriesSplit`, `CalibratedClassifierCV`, psycopg3）は context7 MCP 経由で最新 API を要確認（特に sklearn 1.9.0 の `estimator=` 引数、psycopg3 の `psycopg_pool.ConnectionPool` API）。

---

## Metadata

**Analog search scope:** `/Users/hart/develop/keiba-ai-v3/`（コードベース全体）。`src/`・`tests/`・`scripts/` いずれも存在せず、`pyproject.toml`・`uv.lock` も未作成を `ls`/Glob 相当で確認済み（CONTEXT.md `<code_context>`「Reusable Assets: なし。コードベースは空」が正）。
**Files scanned:** 0（既存ソースコードなし）
**Pattern extraction date:** 2026-06-17
**External authority sources（analog 代用）:**
- `01-RESEARCH.md` Code Examples（Example 1-5）— 全 utils と quality_gate の直接ソース
- `CLAUDE.md` Leakage-prevention configuration §1-5 — utils 設計の権威
- `docs/keiba_ai_requirements_v1.3.md` §6.4 / §12.1-12.4 / §13.3-13.5 / §14.3-14.5 / §17.1-17.3 — 各ファイルの仕様根拠
- `docs/everydb2/03-RACE.md`（RA 110フィールド）— quality_gate / normalize / class_normalize のカラム参照元
- PyPI verified versions（2026-06-17）— pyproject.toml の dependency pin 根拠
