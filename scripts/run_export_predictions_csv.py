# ruff: noqa: E501  (docstring / help 文の日本語行長は緩和・src/db/prediction_load.py と同一慣例)
"""OUT-01 予測CSV 出力 CLI（D-04 LOCKED・§16.2 pin 20列・UTF-8 BOM + CRLF）。

Phase 7 Presentation のバッチ出力経路。Plan 01 の ``PREDICTION_CSV_COLUMNS`` と
Task 1 の ``load_predictions`` / ``build_prediction_csv_bytes`` 純粋関数を DRY 共有し
(D-04)・UI (Plan 03) と同一の loader・列定数を使うことで列揺れを構造的に排除する。

**Open Question #1/#2 解決経路 (BLOCKER-1 正経路):**

``load_predictions`` が prediction SELECT (is_primary=true) → JODDS snapshot
(``fetch_jodds`` + ``select_odds_snapshot(policy)``) → ``compute_ev_and_rank`` で
EV/rank 再計算 → ``normalize_prediction_export_columns`` で ``fuku_*`` → ``fukusho_*`` rename
の経路で OUT-01 の20列を構築する (odds/EV/rank/odds_snapshot_at は backtest JOIN でなく
JODDS snapshot + 再計算で取得・backtest テーブルに odds 値カラムは不存在のため構造的不可能)。

**NEW-H1: ``--odds-snapshot-policy`` CLI flag (§11.2 hindsight-odds 禁止):**

``odds_snapshot_policy`` は事前固定 (default ``"30min_before"``・enum
``"30min_before"``/``"10min_before"``)。事後の grep による最良 policy 再選択は §11.2 で
禁止・再現性は出力 CSV の ``odds_snapshot_policy`` 列で保証される。

**read-only 保証 (D-03):**

``make_pool(role="readonly")`` のみ使用・``settings.dsn_masked`` のみを logger 出力する
(生 DSN 絶対禁止・T-07-08 ASVS V8・Shared Pattern 8)。

Usage::

    uv run python scripts/run_export_predictions_csv.py \\
        --output reports/07-predictions.csv \\
        --date-from 2024-01-01 --date-to 2024-12-31 \\
        --odds-snapshot-policy 30min_before

参照: 07-02-PLAN.md Task 2 / 07-PATTERNS.md §scripts/run_export_*.py /
      scripts/run_backtest.py (argparse/Settings/masked DSN analog) /
      src/ui/loaders.py::load_predictions (純粋 loader・REVIEW MEDIUM-4)
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
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS  # noqa: E402
from src.ui.loaders import build_prediction_csv_bytes, load_predictions  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_export_predictions_csv")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """OUT-01 予測CSV 出力 CLI の引数を解析する。

    ``--odds-snapshot-policy`` (NEW-H1・§11.2 hindsight-odds 禁止) は事前固定 policy を指定。
    """
    parser = argparse.ArgumentParser(
        description=(
            "予測CSV 出力 (OUT-01 / §16.2 pin 20列・UTF-8 BOM + CRLF)。"
            " Plan 01 PREDICTION_CSV_COLUMNS と Task 1 load_predictions 純粋 loader を DRY 共有 (D-04)。"
        )
    )
    parser.add_argument(
        "--output",
        default="reports/07-predictions.csv",
        help="出力 CSV パス (default: reports/07-predictions.csv・UTF-8 BOM + CRLF)",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        help="race_date 期間フィルタ開始 (ISO YYYY-MM-DD・省略時は bounds なし)",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="race_date 期間フィルタ終了 (ISO YYYY-MM-DD・省略時は bounds なし)",
    )
    parser.add_argument(
        "--jyocd",
        nargs="*",
        default=None,
        help="競馬場コードフィルタ (例: 01 05・省略時は全場)",
    )
    parser.add_argument(
        "--odds-snapshot-policy",
        default="30min_before",
        choices=["30min_before", "10min_before"],
        help=(
            "JODDS snapshot 取得の policy (default: 30min_before・enum 30min_before/10min_before)。"
            " 事後の grep による最良 policy 再選択は §11.2 で禁止・再現性は odds_snapshot_policy 列で保証。"
            " (NEW-H1・§11.2 hindsight-odds 禁止・OUT-01 policy 再現性)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """OUT-01 予測CSV を生成するメイン処理。"""
    args = parse_args(argv)
    settings = Settings()
    # 生 DSN 絶対禁止・dsn_masked のみ (T-07-08 ASVS V8・Shared Pattern 8)
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info(
        "odds_snapshot_policy=%s (§11.2 hindsight-odds 禁止・事前固定)",
        args.odds_snapshot_policy,
    )

    pool = make_pool(settings, role="readonly")
    try:
        # 純粋関数 load_predictions を import (cached wrapper でなく・REVIEW MEDIUM-4)
        # NEW-H1: odds_snapshot_policy= を必ず渡す (省略すると loader 既定値と args の不整合で再現性が崩れる)
        df = load_predictions(
            pool,
            date_from=args.date_from,
            date_to=args.date_to,
            jyocd_list=args.jyocd,
            odds_snapshot_policy=args.odds_snapshot_policy,
        )
        logger.info("予測 DataFrame 行数: %d (is_primary=true 主モデル絞り)", len(df))
        csv_bytes = build_prediction_csv_bytes(df)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_bytes(csv_bytes)  # UTF-8 BOM 付き bytes・to_csv で BOM 付与済
        logger.info(
            "OUT-01 予測CSV 出力完了: %s (§16.2 pin %d列・UTF-8 BOM + CRLF)",
            args.output,
            len(PREDICTION_CSV_COLUMNS),
        )
        return 0
    except PsycopgError as exc:
        logger.error("DB エラーで OUT-01 出力失敗: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
