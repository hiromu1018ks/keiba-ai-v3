# ruff: noqa: E501
"""ステップ2 手順2: A1 を is_primary=True・既存 postreview-v2 を is_primary=False に切替 (D-10).

**D-10 聖域**: is_primary 切替は人間承認の別アクション。``--confirm`` 必須 (確認なし実行禁止)。
本スクリプトは ``--dry-run`` で切替内容 (before/after) を表示し・ユーザー承認後に ``--confirm`` で実行する。

同一トランザクション (etl write_cursor) で:
  1. ``set_primary_model(A1)`` → A1 スコープ (fs_id=20260625-1a-speedfigure-v1 +
     as_of=FIXED_REPRODUCE_TS) で reset→True (post-condition REVIEW HIGH#7: 当該スコープで
     is_primary=true が1 model_type のみ・>=1 行)。
  2. ``UPDATE prediction.fukusho_prediction SET is_primary=false WHERE model_version=
     '20260620-1a-postreview-v2-lgb-v1'`` → 既存デプロイ主モデル (postreview-v2 lightgbm・
     別スコープ) を降ろす (受入基準1「他 model_version は False」厳密満たす)。

結果: 全 model_version で A1 (20260625-1a-speedfigure-v1-lgb-v1) のみ is_primary=True。

注意: ``set_primary_model`` は ``feature_snapshot_id + as_of_datetime`` スコープ限定で reset する
ため・別スコープの postreview-v2 (is_primary=True) は Step1 では残る。Step2 で明示的に False 化
する (受入基準1・設計判断3)。lightgbm_rr は既に False で触らない。

Usage::

    uv run python scripts/switch_primary_model.py --dry-run    # 切替内容表示 (DB 変更無し)
    uv run python scripts/switch_primary_model.py --confirm    # 実行 (D-10 承認後のみ)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor, write_cursor  # noqa: E402
from src.db.prediction_load import set_primary_model  # noqa: E402
from src.model.orchestrator import FIXED_REPRODUCE_TS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("switch_primary_model")

PRIMARY_MODEL_TYPE = "lightgbm"
PRIMARY_MODEL_VERSION = "20260625-1a-speedfigure-v1-lgb-v1"
PRIMARY_FEATURE_SNAPSHOT_ID = "20260625-1a-speedfigure-v1"
# 既存デプロイ主モデル (受入基準1 で False 化・lightgbm_rr は既に False で触らない)
DEMOTED_MODEL_VERSION = "20260620-1a-postreview-v2-lgb-v1"


def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()


def _show_is_primary_state(cur, label: str) -> None:
    cur.execute(
        """
        SELECT model_version, feature_snapshot_id, is_primary, count(*) AS n
        FROM prediction.fukusho_prediction
        GROUP BY 1, 2, 3
        ORDER BY feature_snapshot_id, model_version
        """
    )
    logger.info("=== is_primary 状態 [%s] ===", label)
    for r in cur.fetchall():
        logger.info("  model_version=%s fs_id=%s is_primary=%s n=%s", *r)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A1 を is_primary=True・postreview-v2 を False に切替 (ステップ2 手順2・D-10)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="切替内容表示のみ (DB 変更無し)")
    mode.add_argument("--confirm", action="store_true", help="切替実行 (D-10 承認後のみ)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()
    logger.info("etl DSN: %s", settings.etl_dsn_masked)
    logger.info(
        "切替内容: PRIMARY=%s (fs_id=%s as_of=%s) / DEMOTE=%s / mode=%s",
        PRIMARY_MODEL_VERSION,
        PRIMARY_FEATURE_SNAPSHOT_ID,
        FIXED_REPRODUCE_TS.isoformat(),
        DEMOTED_MODEL_VERSION,
        "confirm(実行)" if args.confirm else "dry-run(表示のみ)",
    )

    readonly_pool = make_pool(settings, role="readonly", configure=_configure_statement_timeout)

    try:
        # --- before 状態表示 ---
        with readonly_cursor(readonly_pool) as cur:
            _show_is_primary_state(cur, "BEFORE")

        if not args.confirm:
            logger.info("--dry-run: DB 変更無し。実行する場合は --confirm (D-10 承認後)。")
            logger.info(
                "実行される操作: (1) set_primary_model(%s) → A1 True / (2) UPDATE %s → False",
                PRIMARY_MODEL_VERSION,
                DEMOTED_MODEL_VERSION,
            )
            return 0

        # --- 切替実行 (同一トランザクション・D-10 承認済み) ---
        etl_pool = make_pool(settings, role="etl", configure=_configure_statement_timeout)
        try:
            with write_cursor(etl_pool) as write_cur:
                # Step 1: set_primary_model (A1 スコープ reset→True・post-condition REVIEW HIGH#7)
                set_primary_model(
                    write_cur,
                    primary_model_type=PRIMARY_MODEL_TYPE,
                    primary_model_version=PRIMARY_MODEL_VERSION,
                    feature_snapshot_id=PRIMARY_FEATURE_SNAPSHOT_ID,
                    as_of_datetime=FIXED_REPRODUCE_TS,
                )
                logger.info(
                    "Step1 set_primary_model 完了: %s → is_primary=True (post-condition REVIEW HIGH#7 pass)",
                    PRIMARY_MODEL_VERSION,
                )
                # Step 2: 既存 postreview-v2 を降ろす (受入基準1・別スコープのため set_primary_model では触れない)
                write_cur.execute(
                    "UPDATE prediction.fukusho_prediction SET is_primary = false "
                    "WHERE model_version = %s",
                    (DEMOTED_MODEL_VERSION,),
                )
                demoted_n = write_cur.rowcount
                logger.info(
                    "Step2 DEMOTE 完了: %s → is_primary=False (rows=%d)",
                    DEMOTED_MODEL_VERSION,
                    demoted_n,
                )
            # write_cursor context exit で commit
            logger.info("切替 commit 完了 (同一トランザクション)")
        finally:
            etl_pool.close()

        # --- after 状態表示・受入基準1 検証 ---
        with readonly_cursor(readonly_pool) as cur:
            _show_is_primary_state(cur, "AFTER")
            cur.execute(
                """
                SELECT model_version, count(*) AS n
                FROM prediction.fukusho_prediction
                WHERE is_primary
                GROUP BY 1
                """
            )
            primaries = cur.fetchall()
            logger.info("=== 受入基準1 検証: is_primary=True の model_version ===")
            for r in primaries:
                logger.info("  is_primary=True: model_version=%s n=%s", *r)
            if len(primaries) == 1 and primaries[0][0] == PRIMARY_MODEL_VERSION:
                logger.info(
                    "受入基準1 PASS: A1 (%s) のみ is_primary=True (他は全て False)",
                    PRIMARY_MODEL_VERSION,
                )
                return 0
            logger.error(
                "受入基準1 FAIL: is_primary=True が %d 件 (期待: A1 のみ1件): %s",
                len(primaries),
                primaries,
            )
            return 2
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        readonly_pool.close()


if __name__ == "__main__":
    sys.exit(main())
