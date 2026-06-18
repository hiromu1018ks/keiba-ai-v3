# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""label ETL エントリポイント（HIGH #6: ETL ロール・MEDIUM #1: masked DSN・HIGH #3: idempotent）。

起動フロー:
  1. ``Settings`` から ``dsn_masked`` / ``etl_dsn_masked`` をログ出力（パスワードは *** で保護）
  2. ``make_pool(role='readonly')`` と ``make_pool(role='etl')`` を構築（HIGH #6）
  3. raw fingerprint before 取得（readonly pool）
  4. ``run_label_etl(read_pool, write_pool)`` を **2回連続実行**（HIGH #3 idempotent 検証）
     - ``result1["rows_inserted"] == result2["rows_inserted"]`` を assert
     - ``result1["checksum"] == result2["checksum"]`` を assert（INCLUDING ALL・reader role 明示 GRANT）
  5. raw fingerprint after 取得・``assert_raw_unchanged(before, after)`` で raw 不変性証明（D-06）

Usage::

    uv run python scripts/run_label_etl.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool  # noqa: E402
from src.etl.fukusho_label import run_label_etl  # noqa: E402
from src.etl.raw_fingerprint import (  # noqa: E402
    assert_raw_unchanged,
    compute_raw_fingerprint,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_label_etl")


def main() -> int:
    """複勝ラベル ETL を2回連続実行し idempotent 性と raw 不変性を検証する。"""
    settings = Settings()
    # MEDIUM #1 / HIGH #6: 生 DSN は絶対に出力しない（masked のみ・T-01-01 / T-02-12）
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)

    read_pool = make_pool(settings, role="readonly")
    write_pool = make_pool(settings, role="etl")

    try:
        # --- ETL 前: raw の指紋（D-06 raw read-only 保護の主証明の基準値）---
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                before = compute_raw_fingerprint(cur)
        logger.info(
            "raw fingerprint before label ETL: row_counts=%s",
            {k: v for k, v in before["row_count"].items()},
        )
        # readonly transaction を閉じる（ETL の raw SELECT とロック衝突回避）
        with read_pool.connection() as conn:
            conn.rollback()

        # --- ETL 1回目実行 ---
        result1 = run_label_etl(read_pool, write_pool, settings=settings)
        logger.info(
            "label ETL run #1: rows_inserted=%d, label_unresolved=%d, "
            "raw_touched=%s, checksum=%s",
            result1["rows_inserted"],
            result1["label_unresolved_count"],
            result1["raw_touched"],
            result1["checksum"],
        )

        # --- ETL 2回目実行（HIGH #3 idempotent 検証）---
        result2 = run_label_etl(read_pool, write_pool, settings=settings)
        logger.info(
            "label ETL run #2 (idempotent verify): rows_inserted=%d, "
            "label_unresolved=%d, raw_touched=%s, checksum=%s",
            result2["rows_inserted"],
            result2["label_unresolved_count"],
            result2["raw_touched"],
            result2["checksum"],
        )

        # HIGH #3 idempotent assertion: rows_inserted 一致
        assert result1["rows_inserted"] == result2["rows_inserted"], (
            f"idempotent violation (rows_inserted): "
            f"{result1['rows_inserted']} != {result2['rows_inserted']}"
        )
        # HIGH #3 idempotent assertion: checksum 一致（INCLUDING ALL で PK/インデックス継承・
        # reader role 明示 GRANT 再発行で2回目も同一結果）
        assert result1["checksum"] == result2["checksum"], (
            f"idempotent checksum violation: {result1['checksum']} != {result2['checksum']}"
        )
        # raw 不変性（2回実行でも raw には触れない・成功基準#2）
        assert result2["raw_touched"] is False, (
            "raw_touched=True on run #2: label ETL が raw に書込んだ (D-06 違反)"
        )
        logger.info(
            "idempotent 検証 PASS: rows_inserted=%d, checksum=%s (HIGH #3)",
            result2["rows_inserted"],
            result2["checksum"],
        )

        # --- ETL 後: raw の指紋（不変確認・D-06 二重保護）---
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
