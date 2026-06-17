"""raw → normalized ETL エントリポイント（HIGH #6: ETL ロール使用・MEDIUM #1: masked DSN）。

起動フロー:
  1. ``Settings`` から ``dsn_masked`` / ``etl_dsn_masked`` をログ出力（パスワードは *** で保護）
  2. ``make_pool(role='readonly')`` と ``make_pool(role='etl')`` を構築（HIGH #6）
  3. ``run_normalized_etl(read_pool, write_pool)`` を呼出
  4. ETL 前後で ``compute_raw_fingerprint`` を呼出し raw 不変をログ出力（成功基準#2）

Usage::

    uv run python scripts/run_normalized_etl.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError

from src.config.settings import Settings
from src.db.connection import make_pool
from src.etl.normalize import run_normalized_etl
from src.etl.raw_fingerprint import assert_raw_unchanged, compute_raw_fingerprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_normalized_etl")


def main() -> int:
    """ETL を実行し raw 不変を検証する。"""
    settings = Settings()
    # MEDIUM #1 / HIGH #6: 生 DSN は絶対に出力しない（masked のみ）
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)

    read_pool = make_pool(settings, role="readonly")
    write_pool = make_pool(settings, role="etl")

    try:
        # ETL 前: raw の指紋
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                before = compute_raw_fingerprint(cur)
        logger.info(
            "raw fingerprint before ETL: row_counts=%s",
            {k: v for k, v in before["row_count"].items()},
        )

        # ETL 実行
        result = run_normalized_etl(read_pool, write_pool)
        logger.info(
            "ETL result: rows_inserted=%s, class_unresolved=%d, raw_touched=%s",
            result["rows_inserted"],
            result["class_unresolved_count"],
            result["raw_touched"],
        )

        # ETL 後: raw の指紋（不変確認）
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                after = compute_raw_fingerprint(cur)
        try:
            assert_raw_unchanged(before, after)
            logger.info("raw 不変性確認: PASS（row-hash + row-count + pg_stat 全て不変）")
        except AssertionError as e:
            logger.error("raw 不変性確認: FAIL — %s", e)
            return 2

        return 0
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        read_pool.close()
        write_pool.close()


if __name__ == "__main__":
    sys.exit(main())
