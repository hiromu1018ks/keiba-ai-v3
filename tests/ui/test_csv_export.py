# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・src/db/prediction_load.py と同一慣例)
"""CSV export CLI と bytes 生成の契約検証（OUT-01/OUT-02・D-04 DRY・UI-SPEC CSV Export Contract）。

``scripts/run_export_predictions_csv.py`` / ``scripts/run_export_backtest_csv.py`` と
``src/ui/loaders.py::build_*_csv_bytes`` が以下を満たすことを検証する:

- CSV bytes が UTF-8 BOM + CRLF (Excel 互換・UI-SPEC CSV Export Contract)
- ヘッダ1行目が PREDICTION_CSV_COLUMNS (20列) / BACKTEST_CSV_COLUMNS (16列) と完全一致 (順序含む)
- 必須列欠落時に ``raise ValueError`` で fail-loud (REVIEW LOW-3・silent 欠落回避)
- CLI が Plan 01 列定数と Task 1 純粋 loader を DRY 共有 (D-04)
- ``--odds-snapshot-policy`` CLI flag が事前固定 policy を指定 (NEW-H1・§11.2 hindsight 禁止)
- ``settings.dsn_masked`` のみ logger 出力・生 DSN は出力しない (T-07-08 ASVS V8)

参照: 07-02-PLAN.md Task 2 <behavior> / 07-UI-SPEC.md §CSV Export Contract /
      07-PATTERNS.md §scripts/run_export_*.py (shared pattern 3)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.ui.csv_columns import BACKTEST_CSV_COLUMNS, PREDICTION_CSV_COLUMNS
from src.ui.loaders import build_backtest_csv_bytes, build_prediction_csv_bytes

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRED_CLI = REPO_ROOT / "scripts" / "run_export_predictions_csv.py"
BT_CLI = REPO_ROOT / "scripts" / "run_export_backtest_csv.py"


# ---------------------------------------------------------------------------
# Test 1-3: 予測 CSV bytes の BOM/CRLF/ヘッダ契約
# ---------------------------------------------------------------------------


def test_prediction_csv_bom_crlf() -> None:
    """``build_prediction_csv_bytes`` が BOM で始まり CRLF 改行を含む (UI-SPEC CSV Export Contract)。"""
    df = pd.DataFrame(columns=list(PREDICTION_CSV_COLUMNS), data=[[None] * 20])
    b = build_prediction_csv_bytes(df)
    assert b.startswith(b"\xef\xbb\xbf"), "予測 CSV が UTF-8 BOM (\\xef\\xbb\\xbf) で始まらない"
    assert b"\r\n" in b, "予測 CSV が CRLF (\\r\\n) 改行を含まない"


def test_prediction_csv_header_matches_columns() -> None:
    """予測 CSV 1行目ヘッダが ``PREDICTION_CSV_COLUMNS`` を結合した文字列と完全一致 (順序含む)。"""
    df = pd.DataFrame(columns=list(PREDICTION_CSV_COLUMNS), data=[[None] * 20])
    b = build_prediction_csv_bytes(df)
    text = b.decode("utf-8-sig")  # BOM 除きデコード
    header_line = text.split("\r\n", 1)[0]
    expected = ",".join(PREDICTION_CSV_COLUMNS)
    assert header_line == expected, (
        f"予測 CSV ヘッダが PREDICTION_CSV_COLUMNS と不一致 (順序含む・§16.2 pin):\n"
        f"  got:      {header_line!r}\n  expected: {expected!r}"
    )


def test_prediction_csv_uses_crlf() -> None:
    """予測 CSV が CRLF 改行を使用する (Excel 互換)。"""
    df = pd.DataFrame(
        columns=list(PREDICTION_CSV_COLUMNS),
        data=[[None] * 20, [None] * 20],
    )
    b = build_prediction_csv_bytes(df)
    assert b"\r\n" in b


# ---------------------------------------------------------------------------
# Test 4: 予測 CSV 必須列欠落時 raise ValueError (REVIEW LOW-3・T-07-09 mitigate)
# ---------------------------------------------------------------------------


def test_prediction_csv_missing_column_asserts() -> None:
    """``build_prediction_csv_bytes`` に PREDICTION_CSV_COLUMNS の一部列のみ渡すと ``ValueError`` (LOW-3)。"""
    partial = list(PREDICTION_CSV_COLUMNS)[:10]  # 20列のうち10列のみ
    df = pd.DataFrame(columns=partial)
    with pytest.raises(ValueError):
        build_prediction_csv_bytes(df)


# ---------------------------------------------------------------------------
# Test 5: backtest CSV ヘッダ 16列 (Pitfall 3)
# ---------------------------------------------------------------------------


def test_backtest_csv_header_16_columns() -> None:
    """backtest CSV 1行目ヘッダが BACKTEST_CSV_COLUMNS (16列) と完全一致 (Pitfall 3)。"""
    df = pd.DataFrame(columns=list(BACKTEST_CSV_COLUMNS), data=[[None] * 16])
    b = build_backtest_csv_bytes(df)
    text = b.decode("utf-8-sig")
    header_line = text.split("\r\n", 1)[0]
    expected = ",".join(BACKTEST_CSV_COLUMNS)
    assert header_line == expected, (
        f"backtest CSV ヘッダが BACKTEST_CSV_COLUMNS と不一致 (16列・Pitfall 3):\n"
        f"  got:      {header_line!r}\n  expected: {expected!r}"
    )
    # 16列であることも機械検証 (CONTEXT D-04 「14列」errata・Pitfall 3)
    assert len(BACKTEST_CSV_COLUMNS) == 16


# ---------------------------------------------------------------------------
# Test 6-7: CLI --help が exit 0 で所定 flag を含む (NEW-H1・§11.2 hindsight 禁止)
# ---------------------------------------------------------------------------


def test_run_export_predictions_help() -> None:
    """``run_export_predictions_csv.py --help`` が exit 0 で所定 flag を含む (NEW-H1)。

    ``--odds-snapshot-policy`` は §11.2 hindsight-odds 禁止・事前固定 policy の再現性を担保。
    """
    result = subprocess.run(
        [sys.executable, str(PRED_CLI), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"--help が exit 0 でない (returncode={result.returncode}): {result.stderr}"
    )
    stdout = result.stdout
    for flag in ("--output", "--date-from", "--date-to", "--odds-snapshot-policy"):
        assert flag in stdout, f"予測 CLI --help に {flag} が含まれない (NEW-H1)"


def test_run_export_backtest_help() -> None:
    """``run_export_backtest_csv.py --help`` が exit 0 で所定 flag を含む。"""
    result = subprocess.run(
        [sys.executable, str(BT_CLI), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"--help が exit 0 でない: {result.stderr}"
    stdout = result.stdout
    for flag in ("--output", "--backtest-id"):
        assert flag in stdout, f"backtest CLI --help に {flag} が含まれない"


# ---------------------------------------------------------------------------
# Test 8: 両 CLI が Plan 01 列定数と Task 1 純粋 loader を DRY 共有 (D-04)
# ---------------------------------------------------------------------------


def test_cli_imports_shared_constants() -> None:
    """両 CLI が ``from src.ui.csv_columns import`` と ``from src.ui.loaders import`` を含む (D-04 DRY)。

    REVIEW MEDIUM-4: ``_cached`` suffix の付かない純粋関数を import していることも検証
    (CLI は Streamlit runtime 非依存・cached wrapper でなく純粋 loader を import)。
    """
    pred_src = PRED_CLI.read_text(encoding="utf-8")
    bt_src = BT_CLI.read_text(encoding="utf-8")

    # 予測 CLI: csv_columns と loaders の純粋関数を import
    assert "from src.ui.csv_columns import" in pred_src, (
        "予測 CLI が src.ui.csv_columns を import しない (D-04 DRY)"
    )
    assert "PREDICTION_CSV_COLUMNS" in pred_src
    assert "from src.ui.loaders import" in pred_src, (
        "予測 CLI が src.ui.loaders を import しない (D-04 DRY)"
    )
    # 純粋関数 load_predictions (cached wrapper でなく) を import
    assert "load_predictions" in pred_src
    assert "build_prediction_csv_bytes" in pred_src

    # backtest CLI: csv_columns と loaders の純粋関数を import
    assert "from src.ui.csv_columns import" in bt_src
    assert "BACKTEST_CSV_COLUMNS" in bt_src
    assert "from src.ui.loaders import" in bt_src
    assert "load_backtests" in bt_src
    assert "build_backtest_csv_bytes" in bt_src


# ---------------------------------------------------------------------------
# Test 9: 両 CLI が dsn_masked を使い生 DSN を logger に出さない (T-07-08 ASVS V8)
# ---------------------------------------------------------------------------


def test_cli_uses_dsn_masked() -> None:
    """両 CLI が ``settings.dsn_masked`` を含み 生 ``settings.dsn`` を直接 logger 出力しない (T-07-08)。

    生 DSN はパスワード (KEIBA_DB_PASSWORD) を含むため logger.info 等の引数に直接渡してはならない
    (ASVS V8 Information Disclosure・Shared Pattern 8)。
    """
    pred_src = PRED_CLI.read_text(encoding="utf-8")
    bt_src = BT_CLI.read_text(encoding="utf-8")

    for name, src in (("predictions", pred_src), ("backtest", bt_src)):
        assert "dsn_masked" in src, f"{name} CLI に dsn_masked が含まれない (T-07-08 ASVS V8)"
        # 生 settings.dsn を logger の引数に直接渡す記述がないか (大まかな文字列検証)
        # 許容: settings.dsn_masked のみ。禁止: logger.*(settings.dsn) の直接渡し
        for forbidden in (
            "logger.info(settings.dsn)",
            "logger.error(settings.dsn)",
            "logger.warning(settings.dsn)",
            "logger.debug(settings.dsn)",
            'logger.info(f"%s", settings.dsn)',
            "logger.info(f{settings.dsn}",
        ):
            assert forbidden not in src, (
                f"{name} CLI に生 settings.dsn の logger 出力 '{forbidden}' が含まれる (T-07-08)"
            )
