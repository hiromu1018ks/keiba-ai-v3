#!/usr/bin/env python3
# ruff: noqa: E501  (docstring・ログメッセージを保持するため行長は緩和)
"""LABEL-03 払戻テーブル突合ゲートの CLI エントリポイント（plan 02-04 Task 2）。

``src.config.settings.Settings`` から DB 接続情報を読み、``src.db.connection.make_pool``
で readonly pool を作成、``readonly_cursor`` 経由で ``src.etl.label_reconcile.reconcile_against_payout``
を呼出。戻り値を INFO ログに出力し、``--json`` 指定時は stdout に JSON も出力する。

verdict=='fail' の場合 exit code 1・'pass' の場合 0。CI は exit code で pass/fail を判定
（D-02 ブロッキング要件）。

セキュリティ（T-02-02・T-01-01）:
  - allowlist filter: 各 check dict を ``name/passed/severity/detail`` のみに限定。
    DSN/password 等の認証情報は絶対に含めない。
  - ``Settings()`` の validation error（``.env`` 未設定等）は exit code 2 で fail
    （fail-by-default policy・HIGH #8）。
  - ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ reconcile 実行自体を skip し exit 0（CI で明示的に
    DB 無し環境を許可する場合のみ）。
  - masked DSN のみ INFO ログ出力（T-01-01・``settings.dsn_masked``）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# `.env` を os.environ にロード（uv run 対策）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

logger = logging.getLogger("run_label_reconcile")

# report allowlist（T-02-02）: CheckResult.asdict() のキーと完全一致。
ALLOWED_CHECK_KEYS = frozenset({"name", "passed", "severity", "detail"})


def _filter_check(check: dict[str, Any]) -> dict[str, Any]:
    """T-02-02 allowlist filter。CheckResult dict を許容キーのみに絞る。

    DSN / password 等の認証情報が萬が一混入しても除去される二重防御。
    """
    return {k: v for k, v in check.items() if k in ALLOWED_CHECK_KEYS}


def _build_json_output(result: dict[str, Any]) -> dict[str, Any]:
    """JSON 出力用 dict を構築（allowlist filter 済み・T-02-02）。"""
    return {
        "verdict": result.get("verdict"),
        "checks": [_filter_check(c) for c in result.get("checks", [])],
        "degraded_checks_count": result.get("degraded_checks_count"),
        "agreement": result.get("agreement"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LABEL-03 払戻テーブル突合ゲート（SC#2 >99.9% agreement・D-02 hybrid gate）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="stdout に JSON 形式でも結果を出力する（CI 用）",
    )
    parser.add_argument(
        "--sample-pct",
        type=float,
        default=0.1,
        help="時系列ホールドアウトの割合（デフォルト 0.1 = 10%）",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="DEBUG レベルのログを出力"
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # CI で明示的に DB 無し環境を許可する場合のみ skip（exit 0）
    if os.environ.get("KEIBA_SKIP_DB_TESTS") == "1":
        logger.warning(
            "KEIBA_SKIP_DB_TESTS=1 のため reconcile 実行を skip します（CI 許容モード）"
        )
        return 0

    # Settings をロード（.env 未設定時は validation error で exit 2・HIGH #8）
    try:
        from src.config.settings import Settings
        from src.db.connection import make_pool
        from src.etl.label_reconcile import reconcile_against_payout
    except Exception:  # noqa: BLE001
        logger.exception("必要なモジュールの import に失敗しました")
        return 2

    try:
        settings = Settings()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Settings() の validation に失敗しました（.env を確認してください・HIGH #8）"
        )
        return 2

    # T-01-01: masked DSN のみ INFO ログ出力（認証情報マスク）
    logger.info("reconcile 開始・readonly pool 構築 (dsn_masked=%s)", settings.dsn_masked)

    try:
        read_pool = make_pool(settings, role="readonly")
    except Exception:  # noqa: BLE001
        logger.exception("readonly pool の構築に失敗しました")
        return 2

    try:
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                result = reconcile_against_payout(cur)
    except Exception:  # noqa: BLE001
        logger.exception("reconcile_against_payout の実行中に例外が発生しました")
        return 2
    finally:
        read_pool.close()

    verdict = result.get("verdict", "unknown")
    checks = result.get("checks", [])
    degraded = result.get("degraded_checks_count", 0)
    agreement = result.get("agreement", {})

    # verdict と各 check の結果を INFO ログ出力
    logger.info("=== LABEL-03 reconcile 結果 ===")
    logger.info("verdict: %s", verdict)
    logger.info("degraded_checks_count: %d", degraded)
    for check in checks:
        name = check.get("name", "?")
        passed = check.get("passed")
        severity = check.get("severity", "?")
        detail = check.get("detail", {})
        count = detail.get("count") if isinstance(detail, dict) else None
        logger.info(
            "  check[%s] passed=%s severity=%s count=%s",
            name,
            passed,
            severity,
            count,
        )
    # agreement の要約
    agreement_pct = agreement.get("agreement_pct") if isinstance(agreement, dict) else None
    agree_count = agreement.get("agree_count") if isinstance(agreement, dict) else None
    total_held_out = agreement.get("total_held_out") if isinstance(agreement, dict) else None
    logger.info(
        "agreement: agreement_pct=%s agree_count=%s total_held_out=%s",
        agreement_pct,
        agree_count,
        total_held_out,
    )
    if isinstance(agreement, dict) and agreement.get("disagree_races"):
        logger.warning(
            "disagree_races (先頭5件): %s", agreement["disagree_races"][:5]
        )

    # --json 指定時は stdout に JSON 出力（CI 用・allowlist filter 済み）
    if args.json:
        print(json.dumps(_build_json_output(result), ensure_ascii=False, default=str))

    # verdict で exit code 分岐（D-02 ブロッキング要件）
    if verdict == "pass":
        logger.info("verdict=pass・exit 0")
        return 0
    logger.error("verdict=%s・exit 1（LABEL-03 gate fail）", verdict)
    return 1


if __name__ == "__main__":
    sys.exit(main())
