#!/usr/bin/env python3
"""Hybrid Quality Gate のレポート出力エントリポイント（plan 01-02 Task 2）。

``src.config.settings.Settings`` から DB 接続情報を読み、``src.db.connection.make_pool``
で readonly pool を作成、``readonly_cursor`` 経由で ``src.etl.quality_gate.run_quality_gate``
を呼出。戻り値を2形式で ``reports/`` に出力する:

  - ``reports/quality_report.json``: 機械判定用。最上位に ``verdict`` を含む。
    CI は ``jq -r .verdict`` で pass/fail を判定し fail なら exit 1（D-01 ブロッキング要件）。
  - ``reports/quality_report.md``: 人間用 Markdown。verdict と各 check の一覧を表示。

セキュリティ（T-02-02・REVIEWS HIGH #8）:
  - allowlist filter: 各 check dict を ``name/passed/severity/detail`` のみに限定。
    DSN/password 等の認証情報は絶対に含めない。
  - ``Settings()`` の validation error（``.env`` 未設定等）は skip + WARNING ではなく
    exit code 2 で fail する（fail-by-default policy・HIGH #8）。
  - ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみレポート生成自体を skip し exit 0（CI で明示的に
    DB 無し環境を許可する場合のみ）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
# src.* の dotted import を使うため src/ ではなくリポジトリルートを追加する点に注意
# （plan 01-01 scripts/run_apply_schema.py は src 内モジュールを直接 import するため
#  src/ を追加していたが、本スクリプトは src.etl.* / src.config.* の dotted import を
#  使うのでリポジトリルートを追加）。
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# `.env` を os.environ にロード（uv run 対策・Task 2 の Settings に依存しない）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

# report allowlist（T-02-02）: CheckResult.asdict() のキーと完全一致。
# 未知のキーが混入しても絶対に素通ししない。
ALLOWED_CHECK_KEYS = frozenset({"name", "passed", "severity", "detail"})


def _filter_check(check: dict[str, Any]) -> dict[str, Any]:
    """T-02-02 allowlist filter。CheckResult dict を許容キーのみに絞る。

    DSN / password 等の認証情報が萬が一混入しても除去される二重防御。
    """
    return {k: v for k, v in check.items() if k in ALLOWED_CHECK_KEYS}


def _build_json_report(result: dict[str, Any]) -> dict[str, Any]:
    """JSON 出力用 dict を構築（allowlist filter 済み）。

    最上位は ``{"verdict": ..., "checks": [...]}``。``checks`` の各要素は
    ``name/passed/severity/detail`` のみのキーを持つ（T-02-02）。
    """
    return {
        "verdict": result.get("verdict"),
        "checks": [_filter_check(c) for c in result.get("checks", [])],
    }


def _build_markdown_report(result: dict[str, Any]) -> str:
    """人間用 Markdown を構築。verdict を冒頭に表示し各 check をテーブルで一覧。

    HIGH #7 で追加した mojibake / code_value_anomalies の件数も INFO 欄に表示される。
    """
    verdict = result.get("verdict", "unknown")
    badge = "PASS" if verdict == "pass" else "FAIL"
    checks = result.get("checks", [])

    lines: list[str] = []
    lines.append(f"# Quality Report — {badge}")
    lines.append("")
    lines.append(f"**Verdict:** `{verdict}`")
    lines.append("")
    lines.append("| Check | Severity | Passed | Detail |")
    lines.append("|-------|----------|--------|--------|")

    for c in checks:
        fc = _filter_check(c)
        name = fc.get("name", "")
        sev = fc.get("severity", "")
        passed = "yes" if fc.get("passed") else "no"
        detail = fc.get("detail", {})
        # detail が dict の場合は主要値を短縮表示（件数/率中心）
        detail_str = _format_detail(detail)
        lines.append(f"| `{name}` | {sev} | {passed} | {detail_str} |")

    lines.append("")
    lines.append("## INFO details")
    lines.append("")
    for c in checks:
        fc = _filter_check(c)
        if fc.get("severity") != "info":
            continue
        name = fc.get("name", "")
        detail = fc.get("detail", {})
        lines.append(f"### {name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _format_detail(detail: Any) -> str:
    """detail を Markdown テーブル1セル用に短縮表示。"""
    if not isinstance(detail, dict):
        return str(detail)[:80]
    # 主要な数値キーだけ抜粋
    parts: list[str] = []
    for key in ("count", "duplicates", "total", "distinct", "exists"):
        if key in detail:
            parts.append(f"{key}={detail[key]}")
    # mojibake / code-anomaly の集計値
    if "total_mojibake_rows" in detail:
        parts.append(f"mojibake={detail['total_mojibake_rows']}")
    columns = detail.get("columns", {})
    if isinstance(columns, dict) and columns:
        # code_value_anomalies の異常件数合計
        anom_sum = sum(
            v.get("count", 0)
            for v in columns.values()
            if isinstance(v, dict) and isinstance(v.get("count"), int)
        )
        if anom_sum and "total_mojibake_rows" not in detail:
            parts.append(f"anomaly_rows={anom_sum}")
    return ", ".join(parts) if parts else "(see INFO section)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run hybrid quality gate and write Markdown + JSON reports."
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Output directory for quality_report.{md,json} (default: reports/).",
    )
    parser.add_argument(
        "--fail-on-block",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit 1 when verdict=='fail' (default: True). Use --no-fail-on-block to disable.",
    )
    args = parser.parse_args(argv)

    # REVIEWS HIGH #8: KEIBA_SKIP_DB_TESTS=1 の時のみレポート生成を skip し exit 0。
    # それ以外（デフォルト・CI 含む）は .env 未設定時も Settings() の validation
    # error で exit 2 で fail する（fail-by-default policy）。
    if os.environ.get("KEIBA_SKIP_DB_TESTS") == "1":
        print(
            "[quality_report] KEIBA_SKIP_DB_TESTS=1 set — skipping report generation.",
            file=sys.stderr,
        )
        return 0

    # Settings の validation error（.env 未設定等）は例外で伝播 → exit 2 で fail。
    # conftest の autouse skip は pytest 専用なので、この CLI では自前で catch して
    # exit code 2 に正規化する（HIGH #8）。
    try:
        from src.config.settings import Settings
        from src.db.connection import make_pool, readonly_cursor
        from src.etl.quality_gate import run_quality_gate
    except Exception as exc:  # noqa: BLE001
        print(f"[quality_report] import error: {exc}", file=sys.stderr)
        return 2

    try:
        settings = Settings()
    except Exception as exc:  # noqa: BLE001
        print(
            f"[quality_report] Settings validation failed (.env 未設定の可能性): {exc}",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        pool = make_pool(settings, role="readonly")
        try:
            with readonly_cursor(pool) as cur:
                result = run_quality_gate(cur)
        finally:
            pool.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[quality_report] quality gate execution failed: {exc}", file=sys.stderr)
        return 2

    # JSON 出力（allowlist filter 済み・T-02-02）
    json_report = _build_json_report(result)
    json_path = output_dir / "quality_report.json"
    json_path.write_text(
        json.dumps(json_report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Markdown 出力（人間用・HIGH #7 の mojibake/code-anomaly 含む）
    md_report = _build_markdown_report(result)
    md_path = output_dir / "quality_report.md"
    md_path.write_text(md_report, encoding="utf-8")

    verdict = result.get("verdict", "fail")
    print(f"[quality_report] verdict={verdict} → {json_path}, {md_path}")

    if args.fail_on_block and verdict != "pass":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
