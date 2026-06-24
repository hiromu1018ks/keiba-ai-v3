# ruff: noqa: E501  (docstring の日本語行長は緩和・src/ev/report.py と同一慣例)
"""Streamlit API 正引数使用の検証（RESEARCH Pitfall 1・selection_mode/on_select・Plan 03 で本格化）。

Streamlit 1.58.0 の ``st.dataframe`` 行選択 API は ``selection=``（古い・廃止）でなく
``selection_mode=`` + ``on_select=`` を使用する（UI-SPEC Component Inventory L228 の
``selection="single-row"`` は古い API 表記・RESEARCH Pitfall 1 で正引数を確定）。

本テストは src/ui/ 配下の ``st.dataframe`` 呼出を AST 走査し・
- ``selection=`` キーワード引数（古い API）が存在しないこと
- **NEW-M5**: race-list master dataframe（``race_list_df`` 等のレース一覧を指す変数を第一引数に取る
  ``st.dataframe`` のみ）が ``selection_mode=`` を持つこと。詳細表/スカラー表/backtest 一覧表の
  ``st.dataframe`` は ``selection_mode`` 不要・対象外（Plan 01 が解決した LOW-1 を再導入しない）。

Plan 01 では skip していた緩和基準を Plan 03 実装完了後に本格化（REVIEW LOW-1 解決）。

参照: 07-01-PLAN.md Task 2 / 07-03-PLAN.md <behavior> Test 4・<action> 2 / 07-PATTERNS.md §tests/ui/test_streamlit_api_usage.py /
      07-RESEARCH.md §Common Pitfalls #1
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI_DIR = Path("src/ui")

# レース一覧（master dataframe）を指す変数名の候補（NEW-M5・スコープ限定）。
# prediction_tab.py の _build_race_list_df 戻りを st.dataframe に渡す変数名を想定。
_RACE_LIST_VAR_CANDIDATES = {"race_list_df", "race_df", "master_df"}


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


def _first_arg_name(call: ast.Call) -> str | None:
    """Call の第一引数が変数参照（ast.Name）の場合その id を返す。それ以外は None。"""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Name):
        return first.id
    return None


def test_no_legacy_selection_arg():
    """src/ui/ の ``st.dataframe`` 呼出は古い ``selection=`` 引数を持たない（RESEARCH Pitfall 1）。

    Plan 03 実装後に ``st.dataframe`` 呼出が存在する状態で検証を本格化。
    """
    for py, call in _collect_dataframe_calls():
        for kw in call.keywords:
            if kw.arg == "selection":
                raise AssertionError(
                    f"{py}: st.dataframe が古い 'selection=' 引数を使用している（RESEARCH Pitfall 1・"
                    "selection_mode= + on_select= を使用すること）"
                )


def test_dataframe_uses_selection_mode():
    """**NEW-M5**: race-list master dataframe の ``st.dataframe`` が ``selection_mode=`` を持つ（REVIEW LOW-1 解決）。

    レース一覧（``race_list_df`` 等の変数を第一引数に取る ``st.dataframe`` のみ）を対象とし・
    ``selection_mode=`` キーワード引数を持つことを検証する。詳細表/スカラー表/backtest 一覧表の
    ``st.dataframe`` は ``selection_mode`` 不要・対象外（Plan 01 が解決した LOW-1 を再導入しない）。
    """
    calls = _collect_dataframe_calls()
    if not calls:
        pytest.skip(
            "src/ui/ に st.dataframe 呼出がない（Plan 03 実装後に有効化・REVIEW LOW-1 緩和基準）"
        )
    # race-list master dataframe 呼出を抽出（第一引数が _RACE_LIST_VAR_CANDIDATES のいずれか）
    race_list_calls = [
        (py, call) for py, call in calls if _first_arg_name(call) in _RACE_LIST_VAR_CANDIDATES
    ]
    if not race_list_calls:
        pytest.skip(
            "race-list master dataframe の st.dataframe 呼出が見つからない"
            f"（第一引数が {_RACE_LIST_VAR_CANDIDATES} のいずれかでない）"
        )
    for py, call in race_list_calls:
        has_selection_mode = any(kw.arg == "selection_mode" for kw in call.keywords)
        assert has_selection_mode, (
            f"{py}: race-list master dataframe の st.dataframe が selection_mode= を持たない"
            f"（第一引数={_first_arg_name(call)}・RESEARCH Pitfall 1・selection_mode='single-row' が必要）"
        )
