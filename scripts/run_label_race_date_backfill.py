# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""label.fukusho_label.race_date backfill エントリポイント（Phase 2 負債解消 / Phase 3 cutoff 前提）。

起動フロー（``scripts/run_label_etl.py`` lines 46-127 と同一構造・HIGH #3 / HIGH #6 / MEDIUM #1）:
  1. ``Settings`` から ``dsn_masked`` / ``etl_dsn_masked`` をログ出力（パスワードは *** で保護）
  2. ``make_pool(role='readonly')`` と ``make_pool(role='etl')`` を構築（HIGH #6）
  3. ``backfill_label_race_date`` を **2回連続実行**（HIGH #3 idempotent 検証）
     - ``result1["rows_backfilled"] == result2["rows_backfilled"]`` を assert
     - ``result1["checksum"] == result2["checksum"]`` を assert
     - ``result2["raw_touched"] is False`` を assert（D-06）
  4. 各 backfill run 内部で raw fingerprint before/after + assert_raw_unchanged
     を実行し raw 不変性を二重保護
  5. non_null_race_date_count == rows_backfilled を assert（T-03-08 全行非 NULL 証明）

Usage::

    uv run python scripts/run_label_race_date_backfill.py

Exit codes:
  - 0: 全検証 PASS（idempotent・raw 不変・race_date 全行非 NULL・reader GRANT）
  - 2: raw 不変性違反
  - 3: DB error
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
from src.etl.label_race_date_backfill import backfill_label_race_date  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_label_race_date_backfill")


def main() -> int:
    """label.fukusho_label.race_date backfill を2回連続実行し idempotent 性と
    raw 不変性・race_date 全行非 NULL を検証する。"""
    settings = Settings()
    # MEDIUM #1 / HIGH #6: 生 DSN は絶対に出力しない（masked のみ・T-01-01 / T-02-12）
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)

    read_pool = make_pool(settings, role="readonly")
    etl_pool = make_pool(settings, role="etl")

    try:
        # --- backfill 1回目実行 ---
        result1 = backfill_label_race_date(read_pool, etl_pool)
        logger.info(
            "backfill run #1: rows_backfilled=%d, non_null_race_date_count=%d, "
            "raw_touched=%s, checksum=%s",
            result1["rows_backfilled"],
            result1["non_null_race_date_count"],
            result1["raw_touched"],
            result1["checksum"],
        )

        # --- backfill 2回目実行（HIGH #3 idempotent 検証）---
        result2 = backfill_label_race_date(read_pool, etl_pool)
        logger.info(
            "backfill run #2 (idempotent verify): rows_backfilled=%d, "
            "non_null_race_date_count=%d, raw_touched=%s, checksum=%s",
            result2["rows_backfilled"],
            result2["non_null_race_date_count"],
            result2["raw_touched"],
            result2["checksum"],
        )

        # HIGH #3 idempotent assertion: rows_backfilled 一致
        assert result1["rows_backfilled"] == result2["rows_backfilled"], (
            f"idempotent violation (rows_backfilled): "
            f"{result1['rows_backfilled']} != {result2['rows_backfilled']}"
        )
        # HIGH #3 idempotent assertion: checksum 一致（INCLUDING ALL・reader GRANT 再発行で同一結果）
        assert result1["checksum"] == result2["checksum"], (
            f"idempotent checksum violation: {result1['checksum']} != {result2['checksum']}"
        )
        # raw 不変性（2回実行でも raw には触れない・D-06）
        assert result2["raw_touched"] is False, (
            "raw_touched=True on run #2: backfill が raw に書込んだ (D-06 違反)"
        )
        # T-03-08: race_date が全行非 NULL（silent data loss 検証）
        assert result2["non_null_race_date_count"] == result2["rows_backfilled"], (
            f"race_date 非NULL件数 ({result2['non_null_race_date_count']}) != "
            f"総行数 ({result2['rows_backfilled']}): JOIN 結合漏れ・NULL 残存の可能性 (T-03-08)"
        )
        logger.info(
            "idempotent 検証 PASS: rows_backfilled=%d, checksum=%s (HIGH #3)",
            result2["rows_backfilled"],
            result2["checksum"],
        )
        logger.info("raw 不変性確認: PASS（row-hash + row-count + pg_stat 全て不変）")
        logger.info(
            "race_date 全行非 NULL: PASS (%d / %d 行が非 NULL・T-03-08)",
            result2["non_null_race_date_count"],
            result2["rows_backfilled"],
        )

        return 0
    except AssertionError as e:
        logger.error("検証 FAIL: %s", e)
        return 2
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        read_pool.close()
        etl_pool.close()


if __name__ == "__main__":
    sys.exit(main())
