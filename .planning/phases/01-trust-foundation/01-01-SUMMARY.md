---
phase: 01-trust-foundation
plan: 01
subsystem: trust-foundation (DB bootstrap, schema, settings, code dictionaries)
tags: [phase-01, foundation, postgresql, psycopg3, pydantic-settings, yaml-config, raw-immutability]
requires: []
provides:
  - "uv プロジェクト（Python 3.12 固定・Phase 1 サブセット依存・uv.lock commit）"
  - "src/config/settings.Settings（2ロール DSN + dsn_masked/etl_dsn_masked）"
  - "src/db/connection.make_pool(role='readonly'|'etl') + readonly_cursor / write_cursor"
  - "src/db/schema（5層スキーマ DDL・raw 二重保護 REVOKE・ETL ロール CREATE/GRANT）"
  - "scripts/run_apply_schema.py（KEIBA_ADMIN_DSN 必須・load_dotenv・psycopg.sql.Identifier quoting）"
  - "src/config/class_normalization.yaml（DATA-03 の正・実データ検証済み対応表 verbatim・F/G/H unresolved）"
  - "src/config/code_tables.yaml（jyocd/syubetucd・実データ SELECT DISTINCT 方針）"
  - "src/config/feature_availability.yaml（§13.3 6項目スキーマ・features: []）"
  - "tests/conftest.py fixtures（settings/pg_pool/readonly_cur/write_pool/write_cur）"
  - "fail-by-default DB-test skip policy（KEIBA_SKIP_DB_TESTS=1 のみ skip）"
affects:
  - "01-02 (quality gate): src/db/connection と Settings に依存"
  - "01-03 (normalized ETL): write_pool/write_cur と ETL ロール権限に依存"
  - "01-04 (utils primitives): pyproject.toml の依存に依存"
tech-stack:
  added:
    - "Python 3.12 (requires-python >=3.12,<3.13)"
    - "uv 0.11.21 + uv.lock"
    - "psycopg[binary]==3.3.4 / psycopg-pool==3.3.1（legacy psycopg2 禁止）"
    - "pandas==3.0.3 / pyarrow==24.0.0 / duckdb==1.5.3"
    - "scikit-learn==1.9.0 / mlxtend==0.25.0（CLAUDE.md の '4.x' 表記は PyPI で誤りと確認）"
    - "pydantic / pydantic-settings==2.14.1 / python-dotenv==1.1.0 / pyyaml"
    - "ruff==0.15.17 / pytest==9.1.0 (dev)"
    - "hatchling ビルドバックエンド（src/config, src/db を wheel packages 化）"
  patterns:
    - "pydantic SecretStr + dsn_masked によるログ安全（ASVS V8）"
    - "psycopg3 + psycopg_pool で readonly/etl 2ロールを使い分け"
    - "psycopg.sql.Identifier / Literal でロール名を安全に SQL へ quote"
    - "ALTER DEFAULT PRIVILEGES ... ON TABLES 構文で raw 不変性を未来のテーブルにも拡張"
    - "load_dotenv() で .env を os.environ へ（uv run 対策・Settings に依存せず循環回避）"
key-files:
  created:
    - pyproject.toml
    - uv.lock
    - .gitignore
    - .env.example
    - README.md
    - src/__init__.py
    - src/config/__init__.py
    - src/config/settings.py
    - src/config/class_normalization.yaml
    - src/config/code_tables.yaml
    - src/config/feature_availability.yaml
    - src/db/__init__.py
    - src/db/connection.py
    - src/db/schema.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_bootstrap.py
    - scripts/apply_schema.sql
    - scripts/run_apply_schema.py
decisions:
  - "hatchling ビルドバックエンドを採用（uv_init 既定の uv_build は src/keiba_ai_v3/ フラットレイアウトを強制するため、src/config・src/db を個別 package として扱うため切替）"
  - "EveryDB2 実DB確認で n_odds_fukusho テーブルが存在しないことを確認。複勝オッズは n_odds_tanpuku（単複共用）に含まれるため、raw_everydb2 VIEW 対象から n_odds_fukusho を除外（planner の推測を実測で訂正）"
  - "pg_roles.rolname 比較は文字列リテラルで行い {reader_literal}/{etl_literal} プレースホルダを psycopg.sql.Literal で置換（Identifier との二重使用を回避）"
  - "ConnectionPool に open=True を明示（psycopg-pool 将来リリースのデフォルト切替に備える）"
metrics:
  duration: "約64分"
  completed: "2026-06-17"
  tasks_total: 4
  files_created: 19
  commits: 4
---

# Phase 01 Plan 01: Trust Foundation Summary

uv プロジェクト初期化（Python 3.12 固定・Phase 1 サブセット依存・uv.lock commit）・pydantic-settings による2ロール DB 接続設定（raw 読取 / ETL 書込・`dsn_masked` でログ安全）・psycopg3 ConnectionPool と readonly/etl 2ロール使い分け・5層 PostgreSQL スキーマ DDL（`raw_everydb2` を `public.n_*` への VIEW として作成・物理 `public.n_*` と VIEW の両方に REVOKE を発行する二重保護・ETL ロール CREATE/GRANT）・`psycopg.sql.Identifier` でロール名を安全に quote する適用スクリプト（`KEIBA_ADMIN_DSN` 未設定時は即座に fail）・DATA-03 の正となる `class_normalization.yaml`（実データ検証済み対応表 verbatim・F/G/H も unresolved で明示）・`code_tables.yaml` と `feature_availability.yaml` の枠（§13.3 の6項目スキーマ定義付き）・fail-by-default DB-test skip policy の conftest を構築し、実 DB 上で keiba_readonly と keiba_etl の両ロールが `public` / `raw_everydb2` の両スキーマ上で UPDATE/DELETE/TRUNCATE 権限 = 0 であることを `information_schema` で証明した。

## Tasks Completed

| Task | Name | Commit | Key files |
|------|------|--------|-----------|
| 1 | uv プロジェクト初期化 + Phase 1 依存 + pytest/ruff 設定 | bc3fb87 | pyproject.toml, uv.lock, .gitignore, .env.example, README.md, src/{__init__,config/__init__,db/__init__}.py, tests/__init__.py |
| 3 | 5層スキーマ DDL + 二重保護 REVOKE + ETL ロール CREATE/GRANT + 適用スクリプト（Identifier quoting） | b68ffa0 | src/db/schema.py, scripts/apply_schema.sql, scripts/run_apply_schema.py |
| 2 | pydantic-settings 2ロール DSN + psycopg3 pool + bootstrap tests | 81c1c26 | src/config/settings.py, src/db/connection.py, tests/conftest.py, tests/test_bootstrap.py |
| 4 | class_normalization.yaml verbatim + code_tables/feature_availability 枠 | b8909ad | src/config/class_normalization.yaml, src/config/code_tables.yaml, src/config/feature_availability.yaml |

実行順序は plan の注記（Task 1 → Task 3 → Task 2 → Task 4）に従い、Task 3 で keiba_readonly / keiba_etl ロールを先に CREATE してから Task 2 の接続テストを実行した。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] hatchling ビルドバックエンドへの切替**
- **Found during:** Task 1
- **Issue:** `uv init --package` 既定の `uv_build` バックエンドは `src/keiba_ai_v3/__init__.py` フラットレイアウトを強制する。plan が要求する `src/config/`, `src/db/`, `src/__init__.py` の階層構造と衝突し `uv sync` が `Expected a Python module at: src/keiba_ai_v3/__init__.py` で fail した。
- **Fix:** ビルドバックエンドを hatchling に切替え、`[tool.hatch.build.targets.wheel] packages = ["src/config", "src/db"]` で plan が要求する階層をそのまま wheel package 化。`[project.scripts]` エントリポイントは plan が要求していないため削除。
- **Files modified:** pyproject.toml
- **Commit:** bc3fb87

**2. [Rule 1 - Bug] n_odds_fukusho テーブルが実DBに存在しない**
- **Found during:** Task 3
- **Issue:** plan と 01-RESEARCH.md の主要5系統リストに `n_odds_fukusho` が含まれていたが、実DB（everydb2.public）には存在しない。実DB確認で JRA の複勝オッズは `n_odds_tanpuku`（単勝・複勝共用テーブル）に含まれることが判明。`CREATE VIEW raw_everydb2.n_odds_fukusho AS SELECT * FROM public.n_odds_fukusho` が `relation does not exist` で fail。
- **Fix:** `src/db/schema.py` の `RAW_VIEW_TABLES` と `scripts/apply_schema.sql` の CREATE VIEW リストから `n_odds_fukusho` を削除。VIEW 対象を5表（n_race / n_uma_race / n_harai / n_hyosu / n_odds_tanpuku）に変更。コメントで「JRA の単複は同テーブル」の実測根拠を明記。
- **Files modified:** src/db/schema.py, scripts/apply_schema.sql
- **Commit:** b68ffa0

**3. [Rule 1 - Bug] ALTER DEFAULT PRIVILEGES の SQL 構文エラー（ON TABLES 欠落）**
- **Found during:** Task 3
- **Issue:** plan / 01-PATTERNS.md で提示された `ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE, DELETE, TRUNCATE FROM <role>;` は PostgreSQL として文法不正（`syntax error at or near "FROM"`）。正しい構文は `... REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM <role>;`（`ON TABLES` が必須）。
- **Fix:** `REVOKE_RAW_WRITES_PUBLIC_SQL` / `REVOKE_RAW_WRITES_VIEW_SQL` 両方と `scripts/apply_schema.sql` の該当4行に `ON TABLES` を追加。GRANT 側（GRANT_READER_SQL / GRANT_ETL_SQL）は元から `ON TABLES` を持っていたため無修正。
- **Files modified:** src/db/schema.py, scripts/apply_schema.sql
- **Commit:** b68ffa0

**4. [Rule 1 - Bug] CREATE ROLE 内 DO ブロックで Identifier を文字列リテラル比較に誤使用**
- **Found during:** Task 3
- **Issue:** `CREATE_ROLES_SQL` の DO ブロック `WHERE rolname = '{reader}'` を `_build_rendered_sql` で `psycopg.sql.Identifier` 置換すると、`Identifier` が文字列リテラル内に `"reader"` のように展開され `'reader' != '"reader"'` でロール重複判定が壊れる。
- **Fix:** プレースホルダを `{reader}` と `{reader_literal}` に分離。`{reader}`（bare）は Identifier 置換、`{reader_literal}` は `psycopg.sql.Literal` 置換（PostgreSQL 文字列リテラルとして安全）。etl も同様。`_render_dry_run` も両プレースホルダ対応。
- **Files modified:** src/db/schema.py, scripts/run_apply_schema.py
- **Commit:** b68ffa0

### Plan-as-Written に対する他の調整

- **依存に pyyaml を追加:** plan の Task 4 が `yaml.safe_load` を verify/assert で使用するが、Task 1 の依存リストに `pyyaml` が含まれていなかった。Rule 3（blocking）として `uv add pyyaml` で追加。
- **ConnectionPool に `open=True` を明示:** psycopg-pool が将来リリースで `open` デフォルトを False に切替える予定で DeprecationWarning が出るため明示的に `open=True` を渡した。
- **mlxtend version 確認:** CLAUDE.md の「mlxtend (latest 4.x)」は PyPI で誤りと確認（01-RESEARCH.md で既に訂正済み）。`mlxtend==0.25.0` を pin。

## Threat Flags

該当なし。plan の `<threat_model>` で挙げられた T-01-01..T-01-06, T-01-SC は全て mitigated 状態で実装済み。新規に plan 外の security-relevant な表面は導入していない。

## Known Stubs

該当なし。`features: []`（feature_availability.yaml）は plan が明示的に Phase 1 では空と規定（D-15・Phase 3 で本格運用）。stub ではなく「枠のみ」という設計仕様。

## Verification Results

- `uv sync --frozen`: OK（37 packages・lockfile 整合）
- `uv run python -c "import psycopg, pandas, sklearn, mlxtend, pyarrow, duckdb, pydantic_settings; print('deps OK')"`: OK
- `uv run pytest tests/test_bootstrap.py -v`: **3 passed**（.env 設定済み環境）
  - `test_dsn_masks_password`: `dsn_masked` から生パスワードが除去されていることを assert
  - `test_etl_dsn_uses_etl_role`: `settings.etl_dsn` に `KEIBA_ETL_DB_USER` が含まれることを assert
  - `test_readonly_cur_can_select_n_race`: 実 DB の `n_race` から `jyocd BETWEEN '01' AND '10'` で JRA レース件数 >0 を確認
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest ...::test_readonly_cur_can_select_n_race`: SKIPPED（HIGH #8 policy 動作確認）
- `uv run python scripts/run_apply_schema.py --dry-run`: `CREATE SCHEMA / CREATE ROLE / CREATE OR REPLACE VIEW raw_everydb2 / REVOKE UPDATE / GRANT INSERT` を含む Identifier-quote 済み SQL を出力
- `uv run python scripts/run_apply_schema.py`（実 DB）: 全ステップ成功。`information_schema.role_table_grants` で `keiba_readonly` と `keiba_etl` の両ロールが `public` と `raw_everydb2` の両スキーマ上で UPDATE/DELETE/TRUNCATE 権限 = 0 であることを確認（HIGH #4・plan 01-03 Task 3 の `test_raw_role_has_no_update_grant` と同一対象）
- class_normalization.yaml assert（F/G/H unresolved 含む）: OK
- feature_availability.yaml assert（§13.3 6項目スキーマ存在）: OK
- ruff lint: All checks passed

## Self-Check: PASSED

### Created files exist
- pyproject.toml: FOUND
- uv.lock: FOUND
- .gitignore: FOUND
- .env.example: FOUND
- README.md: FOUND
- src/__init__.py: FOUND
- src/config/__init__.py: FOUND
- src/config/settings.py: FOUND
- src/config/class_normalization.yaml: FOUND
- src/config/code_tables.yaml: FOUND
- src/config/feature_availability.yaml: FOUND
- src/db/__init__.py: FOUND
- src/db/connection.py: FOUND
- src/db/schema.py: FOUND
- tests/__init__.py: FOUND
- tests/conftest.py: FOUND
- tests/test_bootstrap.py: FOUND
- scripts/apply_schema.sql: FOUND
- scripts/run_apply_schema.py: FOUND

### Commits exist
- bc3fb87: FOUND
- b68ffa0: FOUND
- 81c1c26: FOUND
- b8909ad: FOUND
