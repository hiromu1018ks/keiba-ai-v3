#!/usr/bin/env python3
"""Keiba AI v3 — 5層スキーマ + raw 不変性保護 SQL の適用エントリポイント。

管理者接続（KEIBA_ADMIN_DSN）で CREATE SCHEMA / CREATE ROLE / GRANT / REVOKE を実行。
ロール名（KEIBA_DB_USER / KEIBA_ETL_DB_USER）は psycopg.sql.Identifier で安全に quote
する（MEDIUM #3・SQL injection / identifier 文法エラー回避）。

`.env` を `load_dotenv()` で os.environ にロードしてから環境変数を読む（`uv run` では
`.env` が自動ロードされない・Task 2 の Settings に依存せず循環回避）。

D-06 二重保護必須化（REVIEWS HIGH #4/#6）:
  KEIBA_ADMIN_DSN / KEIBA_DB_USER / KEIBA_ETL_DB_USER が未設定の場合は
  skip + WARNING ではなく即座に RuntimeError で fail する。

Usage:
    uv run python scripts/run_apply_schema.py [--sql-file scripts/apply_schema.sql] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# `.env` を os.environ にロード（uv run 対策・Task 2 の Settings に依存しない）
from dotenv import load_dotenv

# scripts/ から src.db.schema を import するためパス追加
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from psycopg import (  # noqa: E402
    connect,
    sql,  # psycopg.sql.Identifier / Literal
)

# load_dotenv を先に実行してから schema を import
load_dotenv(_REPO_ROOT / ".env")

from db import schema as schema_module  # noqa: E402

LOG = logging.getLogger("run_apply_schema")


def _build_rendered_sql(reader: str, etl: str, sql_text: str) -> sql.Composed:
    """``{reader}`` / ``{etl}`` プレースホルダを psycopg.sql.Identifier で安全に置換。

    SQL 文字列内の ``{reader}`` と ``{etl}`` をそれぞれ Identifier(reader) / Identifier(etl)
    に置換した Composed を返す。MEDIUM #3: ロール名を直接 string-substitute せず Identifier で
    quote することで SQL injection と identifier 文法エラーを回避する。
    """
    # {reader}, {etl} を PostgreSQL の Identifier として順に置換
    # psycopg.sql.SQL("{a}").format(a=sql.Identifier(name)) の形で安全に埋め込む
    # ただし SQL ファイル内に複数回出現するため、プレースホルダを %s 風の専用 token に置換してから
    # SQL.format() を呼ぶ。ここでは psycopg.sql.SQL の format 機能を利用。
    template = sql.SQL(sql_text)
    return template.format(
        reader=sql.Identifier(reader),
        etl=sql.Identifier(etl),
        reader_literal=sql.Literal(reader),
        etl_literal=sql.Literal(etl),
    )


def _render_dry_run(reader: str, etl: str, sql_text: str) -> str:
    """dry-run 表示用に {reader}/{etl}/{reader_literal}/{etl_literal} を置換した平文を返す。"""
    quoted_reader = '"' + reader.replace('"', '""') + '"'
    quoted_etl = '"' + etl.replace('"', '""') + '"'
    rendered = sql_text
    rendered = (
        rendered.replace("{reader_literal}", "'" + reader.replace("'", "''") + "'")
        .replace("{etl_literal}", "'" + etl.replace("'", "''") + "'")
        .replace("{reader}", quoted_reader)
        .replace("{etl}", quoted_etl)
    )
    return rendered


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is required to apply REVOKE + CREATE ROLE + GRANT; "
            "D-06 raw read-only protection is mandatory (REVIEWS HIGH #4/#6)"
        )
    return value


def _mask_dsn(dsn: str) -> str:
    """DSN のパスワードを *** でマスクした表示用文字列を返す（T-01-01 / MEDIUM #1）。"""
    if "://" not in dsn:
        return "***"
    scheme, rest = dsn.split("://", 1)
    if "@" not in rest:
        return f"{scheme}://***"
    creds, host_part = rest.rsplit("@", 1)
    if ":" in creds:
        user, _pw = creds.split(":", 1)
    else:
        user = creds
    return f"{scheme}://{user}:***@{host_part}"


def apply(dsn: str, reader: str, etl: str, sql_text: str, dry_run: bool) -> None:
    LOG.info("connecting with admin DSN: %s", _mask_dsn(dsn))
    if dry_run:
        LOG.info("=== DRY RUN: rendered SQL (Identifier-quoted) ===")
        print(_render_dry_run(reader, etl, sql_text))
        LOG.info("=== DRY RUN end ===")
        return

    with connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for step_name, step_sql in [
                ("create_schemas", schema_module.CREATE_SCHEMAS_SQL),
                ("create_roles", schema_module.CREATE_ROLES_SQL),
                ("create_raw_views", schema_module.CREATE_RAW_VIEWS_SQL),
                # Phase 4: prediction_table DDL を GRANT の直前に適用
                # （schema.py APPLY_ORDER と同期・review HIGH#1/Cross-Plan #3 の
                #  11カラム PK + CHECK 制約）
                ("prediction_table", schema_module.PREDICTION_TABLE_DDL),
                # Phase 6 Plan 06-04 Rule 3 fix: is_primary 列追加 ALTER も適用
                # （schema.py APPLY_ORDER と同期・REVIEW HIGH#8 NOT NULL DEFAULT false 明示）
                ("prediction_add_is_primary", schema_module.PREDICTION_ADD_IS_PRIMARY_SQL),
                # Phase 11 Plan 11-05: SC#5 §19.1 metadata 3列追加（codex HIGH#3・DEFAULT
                # 'unspecified' sentinel・codex cycle-2 NEW HIGH#3・idempotent）。ALTER TABLE は
                # owner 権限が必要なため run_apply_schema.py（admin）で適用（Phase 6 idiom・
                # run_phase11_evaluation.py の etl cursor では InsufficientPrivilege・deviation）。
                ("prediction_add_provenance", schema_module.PREDICTION_ADD_PROVENANCE_SQL),
                # Phase 11 Plan 11-05: model_type_domain CHECK 制約 lightgbm_rr/catboost_rr 拡張
                # （codex cycle-2 NEW HIGH#1・DROP IF EXISTS + ADD idempotent migration）。
                (
                    "prediction_extend_model_type_domain",
                    schema_module.PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL,
                ),
                # Phase 12 Plan 12-01 SC#1 p_lower 列追加 ALTER
                # （schema.py APPLY_ORDER と同期・idempotent・owner/admin 権限・
                #  memory: migration-privilege-admin-required・review C-12-01-1 HIGH:
                #  APPLY_ORDER だけでは run_apply_schema.py は適用しない・ハードコード step list への挿入が必須）
                (
                    "prediction_add_p_lower",
                    schema_module.PREDICTION_ADD_P_LOWER_SQL,
                ),
                # Phase 5: backtest_table DDL も GRANT の直前に適用
                # （schema.py APPLY_ORDER と同期・BACK-03 backtest_id 8カラム PK + CHECK・T-05-13）
                ("backtest_table", schema_module.BACKTEST_TABLE_DDL),
                ("grant_reader", schema_module.GRANT_READER_SQL),
                ("grant_etl", schema_module.GRANT_ETL_SQL),
                ("revoke_raw_writes_public", schema_module.REVOKE_RAW_WRITES_PUBLIC_SQL),
                ("revoke_raw_writes_view", schema_module.REVOKE_RAW_WRITES_VIEW_SQL),
            ]:
                rendered = _build_rendered_sql(reader, etl, step_sql)
                LOG.info("applying step: %s", step_name)
                cur.execute(rendered)

            # HIGH #6: ALTER ROLE PASSWORD はパラメータ化し SQL ファイルに書かない
            reader_pw = os.environ.get("KEIBA_DB_PASSWORD")
            etl_pw = os.environ.get("KEIBA_ETL_DB_PASSWORD")
            if reader_pw:
                stmt = sql.SQL("ALTER ROLE {role} WITH PASSWORD {pw}").format(
                    role=sql.Identifier(reader), pw=sql.Literal(reader_pw)
                )
                cur.execute(stmt)
                LOG.info("ALTER ROLE %s PASSWORD set (reader)", reader)
            if etl_pw:
                stmt = sql.SQL("ALTER ROLE {role} WITH PASSWORD {pw}").format(
                    role=sql.Identifier(etl), pw=sql.Literal(etl_pw)
                )
                cur.execute(stmt)
                LOG.info("ALTER ROLE %s PASSWORD set (etl)", etl)

    LOG.info("schema applied successfully")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_sql = _REPO_ROOT / "scripts" / "apply_schema.sql"
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=default_sql,
        help=f"SQL file to apply (default: {default_sql})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the SQL with Identifier-quoted role names and print without executing",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    admin_dsn = _require_env("KEIBA_ADMIN_DSN")
    reader = _require_env("KEIBA_DB_USER")
    etl = _require_env("KEIBA_ETL_DB_USER")

    sql_text = args.sql_file.read_text(encoding="utf-8")

    try:
        apply(admin_dsn, reader, etl, sql_text, args.dry_run)
    except Exception as exc:  # noqa: BLE001
        LOG.error("apply failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
