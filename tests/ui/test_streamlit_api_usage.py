# ruff: noqa: E501  (docstring の日本語行長は緩和・src/ev/report.py と同一慣例)
"""Streamlit API 正引数使用の事前検証土俵（RESEARCH Pitfall 1・selection_mode/on_select）。

Streamlit 1.58.0 の ``st.dataframe`` 行選択 API は ``selection=``（古い・廃止）でなく
``selection_mode=`` + ``on_select=`` を使用する（UI-SPEC Component Inventory L228 の
``selection="single-row"`` は古い API 表記・RESEARCH Pitfall 1 で正引数を確定）。

本テストは src/ui/ 配下の ``st.dataframe`` 呼出を AST 走査し・
- ``selection=`` キーワード引数（古い API）が存在しないこと
- ``selection_mode=`` を持つ ``st.dataframe`` が少なくとも1箇所存在すること（緩和基準・
  詳細/スカラー表の ``st.dataframe`` は ``selection_mode`` 不要・Plan 03 実装後）

を検証する土俵として機能する（Task 2 時点では ``st.dataframe`` 呼出がないため green）。

参照: 07-01-PLAN.md Task 2 / 07-PATTERNS.md §tests/ui/test_streamlit_api_usage.py /
      07-RESEARCH.md §Common Pitfalls #1
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI_DIR = Path("src/ui")


def _collect_dataframe_calls() -> list[tuple[Path, ast.Call]]:
    """src/ui/ 配下の全 ``st.dataframe(...)`` Call ノードを (file, call) のリストで返す。"""
    calls: list[tuple[Path, ast.Call]] = []
    if not UI_DIR.exists():
        return calls
    for py in sorted(UI_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # st.dataframe(...) 形式（Attribute access・attr == "dataframe"）
            if isinstance(func, ast.Attribute) and func.attr == "dataframe":
                calls.append((py, node))
    return calls


def test_no_legacy_selection_arg():
    """src/ui/ の ``st.dataframe`` 呼出は古い ``selection=`` 引数を持たない（RESEARCH Pitfall 1）。

    Task 2 時点では ``st.dataframe`` 呼出がないため green（Plan 03 実装時に検出）。
    """
    for py, call in _collect_dataframe_calls():
        for kw in call.keywords:
            if kw.arg == "selection":
                raise AssertionError(
                    f"{py}: st.dataframe が古い 'selection=' 引数を使用している（RESEARCH Pitfall 1・"
                    "selection_mode= + on_select= を使用すること）"
                )


def test_dataframe_uses_selection_mode():
    """``selection_mode=`` を持つ ``st.dataframe`` が存在するか（緩和基準・REVIEW LOW-1 解決）。

    Plan 03 実装後にレース一覧の ``st.dataframe`` が ``selection_mode="single-row"`` を持つことを
    検証する土俵。Task 2 時点では ``st.dataframe`` 呼出がないため skip（呼出が存在する場合のみ検証）。
    """
    calls = _collect_dataframe_calls()
    if not calls:
        pytest.skip(
            "src/ui/ に st.dataframe 呼出がない（Plan 03 実装後に有効化・REVIEW LOW-1 緩和基準）"
        )
    has_selection_mode = any(
        any(kw.arg == "selection_mode" for kw in call.keywords) for _, call in calls
    )
    assert has_selection_mode, (
        "st.dataframe 呼出が存在するが selection_mode= を持つ呼出がない（RESEARCH Pitfall 1・"
        "レース一覧の行選択には selection_mode='single-row' が必要）"
    )
