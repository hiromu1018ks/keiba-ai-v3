# ruff: noqa: E501  (docstring / help 文の日本語行長は緩和・src/db/prediction_load.py と同一慣例)
"""OUT-02 backtest CSV 出力 CLI（D-04 LOCKED・§16.2 pin 16列・UTF-8 BOM + CRLF）。

Phase 7 Presentation のバッチ出力経路。Plan 01 の ``BACKTEST_CSV_COLUMNS`` と
Task 1 の ``load_backtests`` / ``build_backtest_csv_bytes`` 純粋関数を DRY 共有し (D-04)・
UI (Plan 03) と同一の loader・列定数を使うことで列揺れを構造的に排除する。

**Pitfall 3 (16列):**

CONTEXT D-04 の「14列」表記は errata・§16.2 原典 (16列) を正とする (CLAUDE.md「要件優先」)。
``BACKTEST_CSV_COLUMNS`` は 16列で・test_backtest_csv_header_16_columns が機械検証する。

**read-only 保証 (D-03):**

``make_pool(role="readonly")`` のみ使用・``settings.dsn_masked`` のみを logger 出力する
(生 DSN 絶対禁止・T-07-08 ASVS V8・Shared Pattern 8)。

Usage::

    # 全件出力
    uv run python scripts/run_export_backtest_csv.py --output reports/07-backtest.csv

    # 単一 backtest_id
    uv run python scripts/run_export_backtest_csv.py --backtest-id BT-1-30min_before-lightgbm

参照: 07-02-PLAN.md Task 2 / 07-PATTERNS.md §scripts/run_export_*.py /
      scripts/run_backtest.py (argparse/Settings/masked DSN analog) /
      src/ui/loaders.py::load_backtests (純粋 loader・REVIEW MEDIUM-4)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加 (run_backtest.py L40-43 と同一)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool  # noqa: E402
from src.ui.csv_columns import BACKTEST_CSV_COLUMNS  # noqa: E402
from src.ui.loaders import build_backtest_csv_bytes, load_backtests  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_export_backtest_csv")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """OUT-02 backtest CSV 出力 CLI の引数を解析する。"""
    parser = argparse.ArgumentParser(
        description=(
            "Backtest CSV 出力 (OUT-02 / §16.2 pin 16列・UTF-8 BOM + CRLF)。"
            " Plan 01 BACKTEST_CSV_COLUMNS と Task 1 load_backtests 純粋 loader を DRY 共有 (D-04)。"
            " (Pitfall 3: 16列・CONTEXT D-04 「14列」は errata)"
        )
    )
    parser.add_argument(
        "--output",
        default="reports/07-backtest.csv",
        help="出力 CSV パス (default: reports/07-backtest.csv・UTF-8 BOM + CRLF)",
    )
    parser.add_argument(
        "--backtest-id",
        default=None,
        help="単一 backtest_id で絞り (例: BT-1-30min_before-lightgbm・省略時は全件)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """OUT-02 backtest CSV を生成するメイン処理。"""
    args = parse_args(argv)
    settings = Settings()
    # 生 DSN 絶対禁止・dsn_masked のみ (T-07-08 ASVS V8・Shared Pattern 8)
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("backtest_id filter=%s", args.backtest_id)

    pool = make_pool(settings, role="readonly")
    try:
        # 純粋関数 load_backtests を import (cached wrapper でなく・REVIEW MEDIUM-4)
        df = load_backtests(pool, backtest_id=args.backtest_id)
        logger.info("backtest DataFrame 行数: %d", len(df))
        csv_bytes = build_backtest_csv_bytes(df)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_bytes(csv_bytes)  # UTF-8 BOM 付き bytes・to_csv で BOM 付与済
        logger.info(
            "OUT-02 backtest CSV 出力完了: %s (§16.2 pin %d列・UTF-8 BOM + CRLF)",
            args.output,
            len(BACKTEST_CSV_COLUMNS),
        )
        return 0
    except PsycopgError as exc:
        logger.error("DB エラーで OUT-02 出力失敗: %s", exc)
        return 3
    except Exception as exc:
        # WR-07: PsycopgError 以外の例外 (ValueError/FileNotFoundError/ParserError 等) を握り潰さず・
        # 一意の exit code で返す。CI で exit code を区別する場合に DB エラー (3) とそれ以外 (2) を
        # 分離できるようにする。sys.exit(main()) で traceback 表示 → exit 1 になる経路も回避。
        logger.error("OUT-02 出力失敗（DB 以外のエラー）: %s", exc, exc_info=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
