# Phase 2: Fukusho Labels - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 7（新規 5 / 修正 2）
**Analogs found:** 7 / 7（全て Phase 1 成果物からの直接再利用）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/etl/fukusho_label.py` 【新規】 | ETL service | ETL (read-raw → pandas transform → idempotent write) | `src/etl/normalize.py` | exact |
| `src/etl/label_reconcile.py` 【新規】 | quality gate (data check) | reconciliation (SELECT-only audit) | `src/etl/quality_gate.py` | exact |
| `src/config/label_spec.yaml` 【新規】 | static config (YAML) | declarative (load at runtime) | `src/config/class_normalization.yaml` + `src/config/code_tables.yaml` | role-match |
| `src/db/schema.py` 【修正】 | schema config (DDL/GRANT constants) | declarative (applied via `run_apply_schema.py`) | `src/db/schema.py` 自己拡張 | exact |
| `src/db/connection.py` 【修正】 | connection factory | config (search_path 拡張) | `src/db/connection.py` 自己拡張 | exact |
| `tests/test_fukusho_label.py` 【新規】 | unit/integration test | LABEL-01/02/04 + D-03 | `tests/test_normalized_etl.py` + `tests/conftest.py` fixtures | role-match |
| `tests/test_label_reconcile.py` 【新規】 | unit/integration test (hybrid gate) | LABEL-03 / §10.5 6検査 BLOCK/INFO | `tests/test_quality_gate.py` | exact |

---

## Pattern Assignments

### `src/etl/fukusho_label.py` (ETL service, read→transform→idempotent write)

**Analog:** `src/etl/normalize.py`（全文読込済み・1-675 行）

**構成上の指針:** `normalize.py` と同じ3層構造を踏襲する：
1. `_select_raw_harai(read_cur)` / `_select_se_state(read_cur)` — readonly pool からの raw SELECT
2. `compute_fukusho_labels(hr_df, se_df)` — pandas による明示キャスト + ラベル計算
3. `run_label_etl(read_pool, write_pool)` — `label.fukusho_label` への idempotent load

**Imports パターン** — `normalize.py:27-39` に完全一致：
```python
from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from psycopg import Cursor
from psycopg_pool import ConnectionPool
from src.etl.filters import PROJECT_WINDOW_FILTER  # CR-06 single source of truth
logger = logging.getLogger(__name__)
```

**HR raw SELECT パターン（明示キャスト）** — `normalize.py:178-184, 234-240` の `_select_raw_race` / `_select_raw_uma_race` の写し：
```python
# normalize.py:178-184
def _select_raw_race(read_cur: Cursor) -> pd.DataFrame:
    """raw ``public.n_race`` から JRA 限定で SELECT（Pitfall 2/4）。"""
    cols = ", ".join(_RACE_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM public.n_race WHERE {_JRA_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_RACE_SELECT_COLUMNS)
```
適用：`_select_raw_harai` は `f"SELECT {cols} FROM public.n_harai WHERE {PROJECT_WINDOW_FILTER}"`。**`timediff`（実カラム名・`TimeDIFN` でない）を SE 側で SELECT する**（RESEARCH Pitfall 1）。

**明示キャスト transform パターン** — `normalize.py:316-350` の `_transform_uma_race_df` の `pd.to_numeric(errors="coerce")` を HR/SE 読込後に適用：
```python
# normalize.py:340-342
int_cols = ["year", "wakuban", "umaban", ...]
for c in int_cols:
    if c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
```
適用：`compute_fukusho_labels` 内で `kakuteijyuni` / `torokutosu` / `bataijyu` を `pd.to_numeric(errors="coerce")`。`payfukusyounmaban1..5` は `'00'`/`''` を `pd.NA` に変換（RESEARCH Pattern 2・A3）。

**Idempotent staging-swap load パターン** — `normalize.py:356-441` の `_idempotent_load` を `label` スキーマ向けに再利用。`normalize.py` の `normalized.<table>` を `label.<table>` に置換したコピー、または汎用化（`schema` 引数追加）。
```python
# normalize.py:385-402 — advisory_xact_lock + 空入力拒否（CR-04）を踏襲
write_cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"label.{table}",))
if not rows:
    raise RuntimeError(f"_idempotent_load('{table}'): refusing to swap to empty ...")
```
ステップ順序（`normalize.py:368-373`）：`CREATE _staging (LIKE)` → `TRUNCATE _staging` → `INSERT INTO _staging` → `executemany rowcount 検証`（CR-04(c)）→ `DROP <table>` → `RENAME _staging TO <table>` → `GRANT SELECT TO PUBLIC`。

**ETL entrypoint パターン** — `normalize.py:624-663` の `run_normalized_etl(read_pool, write_pool)` 署名・戻り値 dict 構造を写す：
```python
# normalize.py:659-663
return {
    "rows_inserted": rows_inserted,
    "class_unresolved_count": unresolved_total,  # → "label_unresolved_count"
    "raw_touched": False,  # 成功基準#2 不変指示・label ETL も常に False
}
```

**`_df_to_tuples` パターン** — `normalize.py:520-585` の `pd.NaT` / `pd.NA` / `Int64 → int|None` 変換ロジックを `label.fukusho_label` のカラム型（boolean / smallint / varchar / date）向けに適用。boolean カラム（`is_model_eligible` 等）は `normalize.py:576-580` の `is_grade_race` 分岐を参照。

**Pitfall 2 JRA フィルタ** — `normalize.py:51` の `_JRA_FILTER = PROJECT_WINDOW_FILTER` を再利用（CR-06）。三重定義禁止。

---

### `src/etl/label_reconcile.py` (quality gate, SELECT-only reconciliation)

**Analog:** `src/etl/quality_gate.py`（全文読込済み・1-633 行）

**構成上の指針:** `quality_gate.py` の `CheckResult` dataclass + `run_quality_gate(cur)` 統合エントリ + BLOCK/INFO verdict 集計パターンを、§10.5 の 6 検査に適用。RESEARCH「§10.5 の 6 検査の構造/量化対応表」が各検査の severity を確定済み。

**`CheckResult` dataclass** — `quality_gate.py:91-106` をそのまま再利用（import または複製）：
```python
# quality_gate.py:91-106
@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # "block" or "info"（D-01）
    detail: dict[str, Any] = field(default_factory=dict)
```

**検査関数の構造** — `quality_gate.py:160-175` の `_check_table_exists` が最小テンプレ。各検査は cursor を受け取り `CheckResult` を返す：
```python
# quality_gate.py:160-175
def _check_table_exists(cur: Cursor, table: str) -> CheckResult:
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE ...", (table,))
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name=f"table_exists:{table}",
        passed=cnt > 0,
        severity="block",
        detail={"table": table, "exists": cnt > 0, "matches": cnt},
    )
```
適用：6 検査それぞれを同形式で実装（例：`_check_payout_table_contains_all_validated` / `_check_no_scratch_mislabeled` / ...）。D-02 + RESEARCH 対応表に基づき全 6 検査を `severity="block"`、量化(drift/status 割合等)を `severity="info"` に設定。

**統合エントリ + verdict 集計** — `quality_gate.py:533-617` の `run_quality_gate` を `reconcile_against_payout(cur) -> dict` として複製：
```python
# quality_gate.py:583
verdict = "pass" if all(r.passed for r in results if r.severity == "block") else "fail"
# quality_gate.py:613-617
return {
    "verdict": verdict,
    "checks": [asdict(r) for r in results],
    "degraded_checks_count": degraded_checks_count,  # WR-05 silent degradation 監視
}
```

**セキュリティ（T-02-02）** — `quality_gate.py:544-555` の通り、各 check dict は `name/passed/severity/detail` のみ。DSN/password 等の認証情報は一切含めない（AC 拡張時も維持）。

**YAML 読込（allowed-code-set）** — `quality_gate.py:114-152` の `_load_allowed_codes()` は `class_normalization.yaml` + `code_tables.yaml` から set を構築。`label_spec.yaml` から `syubetucd` 障害/新馬コードや `label_generation_version` を読む際は同パターン。silent fallback 禁止（T-02-01）・YAML 読込失敗時は `RuntimeError`。

---

### `src/config/label_spec.yaml` (static config, declarative YAML)

**Analog:** `src/config/class_normalization.yaml` + `src/config/code_tables.yaml`

**構造パターン** — `class_normalization.yaml:1-15` のヘッダコメント慣行（由来・実測根拠・CODE.md 不使用明記・Pitfall 番号）を写す：
```yaml
# class_normalization.yaml:1-6
# Keiba AI v3 — DATA-03 の正: クラス正規化完全対応表（実データ検証済み）
#
# 由来: PostgreSQL everydb2 に直接接続し、2015-01-01 以降の JRA データ
# （jyocd BETWEEN '01' AND '10'）の jyokencd5 × gradecd × year を集計して導出
# （01-RESEARCH.md §クラス正規化完全対応表）。CODE.md は不完全（D-10）のため
# 実データ SELECT DISTINCT のみを正とする。本ファイルが DATA-03 の正。
```

適用：`label_spec.yaml` には以下を記載：
- `label_generation_version: "v1.0.0"`（Open Question #1 推奨・セマンティック採番）
- `payout_places_rules`（`torokutosu >= 8 → 3` / `5 <= torokutosu <= 7 → 2` / その他 → 0）
- `model_ineligibility_syubetucd: ["11","12","18","19"]`（§7.3 障害/新馬）
- `status_values: [validated, inferred, dead_heat, unresolved]`（D-04 固定4値）
- `se_marker_rules`（取消/中止/除外の SE 識別条件・RESEARCH Pitfall 4 対応表）

**Loader パターン** — `class_normalize.py:36-51` の `load_class_config()` が `yaml.safe_load` + 必須キー欠落時 `ValueError` のテンプレ。`label_spec.yaml` 用の `load_label_spec()` として再利用：
```python
# class_normalize.py:44-51
with Path(path).open(encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
reform_str = cfg.get("post_2019_class_system_reform_date")
if reform_str is None:
    raise ValueError("class_normalization.yaml に ... が未設定")
```

---

### `src/db/schema.py` 【修正】 (schema config, GRANT 拡張)

**Analog:** `src/db/schema.py` 自己拡張（全文読込済み・1-156 行）

**修正点1: `GRANT_ETL_SQL` 拡張** — `schema.py:88-98` の現行定義（`normalized` のみ USAGE+CREATE）に `label` スキーマ行を追記：
```python
# schema.py:88-98（現行）
GRANT_ETL_SQL = """
GRANT USAGE ON SCHEMA public TO {etl};
GRANT USAGE ON SCHEMA raw_everydb2 TO {etl};
GRANT USAGE, CREATE ON SCHEMA normalized TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA raw_everydb2 TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA normalized TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA normalized
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
"""
```
追加する3行（Pitfall 6 対策）：
```sql
GRANT USAGE, CREATE ON SCHEMA label TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA label TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA label
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
```

**修正点2: `GRANT_READER_SQL` 拡張** — `schema.py:76-86` に下流 Phase 3-5 の readonly ロール読込用：
```sql
GRANT USAGE ON SCHEMA label TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA label TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA label GRANT SELECT ON TABLES TO {reader};
```

**`{reader}` / `{etl}` プレースホルダ** — `schema.py:18-19` の通り `scripts/run_apply_schema.py` が `psycopg.sql.Identifier` で安全に置換（MEDIUM #3）。修正後 `uv run python scripts/run_apply_schema.py` の再実行が計画必須（RESEARCH Pitfall 6・AC 変更点 #3）。

**`SCHEMAS` リスト** — `schema.py:26` に `label` は既に含まれる（`CREATE SCHEMA IF NOT EXISTS label` 済み）。スキーマ作成不要・GRANT のみ追加。

---

### `src/db/connection.py` 【修正】 (connection factory, search_path 拡張)

**Analog:** `src/db/connection.py` 自己拡張（全文読込済み・1-77 行）

**修正点:** `make_pool(role="etl")` の `search_path` に `label` を追加。`connection.py:40-43` の現行：
```python
# connection.py:40-43
elif role == "etl":
    conninfo = settings.etl_dsn
    search_path = f"{settings.db_schema_normalized},public"
```
修正後（`db_schema_label` を `settings.py` に `= "label"` で追加・または固定文字列）：
```python
elif role == "etl":
    conninfo = settings.etl_dsn
    search_path = f"{settings.db_schema_label},{settings.db_schema_normalized},public"
```
`db_schema_label: str = "label"` を `src/config/settings.py:39` の近傍に追加（`db_schema_raw` / `db_schema_normalized` と対称）。

`role="readonly"` 側は `search_path=public`（`connection.py:38-39`）のままでよい — readonly ロールは `label.fukusho_label` を schema 修飾（`label.fukusho_label`）で SELECT するため。ただし GRANT は `GRANT_READER_SQL` 拡張で付与必要（上記 schema.py 修正）。

`readonly_cursor` / `write_cursor` context manager（`connection.py:55-76`）は変更不要。`_idempotent_load` が `label.<table>` を schema 修飾 SQL で発行するため、search_path 依存性は低いが、GRANT と整合させるため拡張推奨。

---

### `tests/test_fukusho_label.py` 【新規】 (unit/integration test)

**Analog:** `tests/test_normalized_etl.py` + `tests/conftest.py`（fixtures 再利用）

**Fixture 再利用** — `conftest.py:22-63` の `settings` / `pg_pool` (readonly) / `write_pool` (etl) / `readonly_cur` / `write_cur` をそのまま使用。session/function scope も同じ。新規 fixture 不要（`@pytest.mark.requires_db` で DB skip policy も `conftest.py:66-78` に従う）。

**テスト構造** — `test_quality_gate.py:11-26` の import パターン（private 関数も含めて直接 import する慣行）を踏襲：
```python
# test_quality_gate.py:17-26
from src.etl.quality_gate import (
    REAL_CAST_COLUMNS,
    _check_cast_success,
    _check_code_value_anomalies,
    ...
    run_quality_gate,
)
```

**Mock cursor パターン（unit test 用）** — `test_quality_gate.py:33-61` の `_mock_cursor(fetch_map)` ファクトリを、HR/SE の SELECT 結果を模擬する unit test で再利用（`compute_fukusho_labels` pure transform のテスト）。

**Integration test 構造** — `test_raw_immutability.py:46-60` の「before fingerprint → ETL 実行 → after fingerprint 比較」パターンを `run_label_etl` 前後の raw 不変性検証に適用（RESEARCH Validation Architecture「raw 不変性」拡張）：
```python
# test_raw_immutability.py:55-57
before = compute_raw_fingerprint(readonly_cur)
readonly_cur.connection.rollback()
run_normalized_etl(pg_pool, write_pool, ...)
```
`run_label_etl` 版でも `compute_raw_fingerprint` 前後で raw が不変であることを assert。

**LABEL-04 エッジケーステスト** — RESEARCH Pitfall 4 の識別条件表（取消956/中止3554/全体中止376/dead_heat 97）を行単位で構築した DataFrame を `compute_fukusho_labels` に通して期待 status/`is_model_eligible` を assert（pure unit test・DB 不要）。

---

### `tests/test_label_reconcile.py` 【新規】 (unit/integration test, hybrid gate)

**Analog:** `tests/test_quality_gate.py`（全文読込済み・冒頭 1-80 行）

**Mock cursor + CheckResult 検証** — `test_quality_gate.py:33-61` の `_mock_cursor` を §10.5 の 6 検査分の `fetch_map` に拡張して使用。各検査関数が `CheckResult(name, passed, severity, detail)` を返すことを assert。

**BLOCK/INFO verdict 集計テスト** — `test_quality_gate.py:69-77` の「BLOCK 1件でも passed=False → verdict="fail"」パターンを `reconcile_against_payout` に適用。`>99.9%` agreement テスト（`test_gt_999_pct_agreement`）は held-out 10% サンプルに対するレース単位の馬集合完全一致を assert（RESEARCH Open Question #3 推奨）。

**degraded_checks_count（WR-05）** — `quality_gate.py:585-611` の `_has_error(detail)` 走査ロジックを `reconcile_against_payout` 戻り値でも検証（silent degradation 監視）。

---

## Shared Patterns

### readonly/etl 2ロール pool 使い分け（D-06 / HIGH #6）
**Source:** `src/db/connection.py:21-52`
**Apply to:** `src/etl/fukusho_label.py`, `src/etl/label_reconcile.py`, 全テストファイル
```python
# read: make_pool(settings, role="readonly") → public.n_* / raw_everydb2 に SELECT-only
# write: make_pool(settings, role="etl")    → label スキーマに INSERT/UPDATE/TRUNCATE
read_pool = make_pool(settings, role="readonly")
write_pool = make_pool(settings, role="etl")
```
label ETL は raw に一切 UPDATE/DELETE/INSERT を発行しない（成功基準#2 raw 不変・RESEARCH Security V4）。

### JRA + 2015 filter（CR-06 single source of truth）
**Source:** `src/etl/filters.py:31, 36`
**Apply to:** `src/etl/fukusho_label.py`, `src/etl/label_reconcile.py`
```python
# filters.py:36
PROJECT_WINDOW_FILTER = "jyocd BETWEEN '01' AND '10' AND year::int >= 2015"
```
全 SELECT で再利用。三重定義禁止（normalize.py が過去に犯したバグ・CR-06）。

### 明示キャスト（Pitfall 1）
**Source:** `src/etl/normalize.py:340-348`
**Apply to:** `src/etl/fukusho_label.py` の HR/SE 読込後 transform
```python
out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")  # int 系
out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)    # real 系
```
EveryDB2 raw は全 varchar。`payfukusyounmaban` の `'00'`/`''` は `pd.NA` 化（A3・silent mislabeling 防止）。

### silent fallback 禁止（D-13）
**Source:** `src/etl/class_normalize.py:13-14`, `src/etl/quality_gate.py:131-133`
**Apply to:** 全新規ファイル。未知コード・HR 欠損・不成立は `unresolved` / `is_model_eligible=False` で明示隔離。`RuntimeError` で fail に傾く（YAML 読込失敗時など）。
```python
# quality_gate.py:131-133
except (OSError, yaml.YAMLError) as exc:
    raise RuntimeError(f"failed to load allowed-code config from {_CONFIG_DIR}: {exc}") from exc
```

### Raw 不変性検証（成功基準#2 / MEDIUM #2）
**Source:** `src/etl/raw_fingerprint.py` + `tests/test_raw_immutability.py`
**Apply to:** `tests/test_fukusho_label.py` 拡張
```python
before = compute_raw_fingerprint(readonly_cur)
readonly_cur.connection.rollback()
run_label_etl(pg_pool, write_pool)
# after fingerprint を取得して assert_raw_unchanged(before, after)
```
label ETL 追加後も raw(public.n_*) が不変であることを再検証（RESEARCH Validation Architecture 拡張）。

### ETL ロール GRANT + REVOKE 二重保護（HIGH #4 / HIGH #6）
**Source:** `src/db/schema.py:88-117`
**Apply to:** `src/db/schema.py` 拡張 + `scripts/run_apply_schema.py` 再実行タスク
- ETL ロールに `label` スキーマの `USAGE, CREATE` + `SELECT, INSERT, UPDATE, DELETE, TRUNCATE` を付与
- reader ロールに `label` スキーマの `USAGE` + `SELECT` のみ付与
- public / raw_everydb2 に対する書込権は引き続き REVOKE（label 拡張で変更しない）

---

## No Analog Found

該当なし。Phase 2 の全ファイルは Phase 1 成果物（trust-foundation）の直接再利用でカバーされる。RESEARCH「Don't Hand-Roll」表の通り、idempotent load / hybrid gate / JRA filter / pool 使い分け / class 正規化 / raw fingerprint すべて Phase 1 で解決済み。

---

## Metadata

**Analog search scope:**
- `/Users/hart/develop/keiba-ai-v3/src/etl/`（normalize.py / quality_gate.py / filters.py / raw_fingerprint.py / class_normalize.py）
- `/Users/hart/develop/keiba-ai-v3/src/db/`（connection.py / schema.py）
- `/Users/hart/develop/keiba-ai-v3/src/config/`（settings.py / *.yaml）
- `/Users/hart/develop/keiba-ai-v3/tests/`（conftest.py / test_quality_gate.py / test_raw_immutability.py / test_normalized_etl.py）
- `/Users/hart/develop/keiba-ai-v3/scripts/run_apply_schema.py`

**Files scanned:** 11（5 ソース + 2 config + 4 テスト）
**Pattern extraction date:** 2026-06-17
**Key insight:** Phase 2 は Phase 1 のインフラ（idempotent staging-swap / CheckResult BLOCK/INFO / 2ロール pool / JRA filter / explicit cast / YAML config）の直接踏襲が 100%。新規パターンは HR 払戻テーブル読込と dead_heat/取消/中止の SE マーカー識別ロジックのみ — これらは RESEARCH の Code Examples が実測ロジックを提供済み。
