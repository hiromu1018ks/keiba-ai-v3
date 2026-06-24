# ruff: noqa: E501  (テストの日本語 docstring/assert メッセージが長いため行長は緩和・Plan 01/02 と同一慣例)
"""Phase 7 UI 描画契約の AST/文字列検証（UI-SPEC Layout/Component Inventory/Copywriting/Color・§16.1 除外）。

UI-SPEC が承認した Layout/Component Inventory/Copywriting/Color 契約がコード上で遵守されていることを
AST と文字列検証で機械保証する（Phase 8 TEST-01 前提）。Streamlit 描画の実 E2E 起動検証は
Plan 03 Task 3 checkpoint:human-verify で実施する（本テストは AST/文字列レベルの契約検証）。

**検証対象（behavior Test 1-13 + W2 trace 数 + REVIEW MEDIUM-7 統合）:**

- app.py: ``st.title`` 1回・文字列「Keiba AI v3 — 複勝予測分析」/ ``st.tabs`` 3ラベル / sidebar フィルタ（D-02）
- prediction_tab.py: ``selection_mode`` 正引数 / ``NumberColumn(format='%.3f')`` / SC#1 の6数値列（BLOCKER-4・HIGH-1 fukusho_*）/ download label
- backtest_tab.py: ``st.warning`` honest 注記（JODDS 再検証 subject・暫定値）/ download label
- calibration_tab.py: ``st.plotly_chart`` + ``use_container_width=True`` / 6軸（D-12）
- 全 src/ui/: ``unsafe_allow_html=True`` 不存在（V13）/ §16.1 除外項目（ワイド/荒れ指数/コメント生成）不存在
- W2: ``build_calibration_figure`` trace 数検証（segment curve + 完全予測線 = len+1）
- REVIEW MEDIUM-7: ``render_prediction_tab`` モック DataFrame 統合テスト

参照: 07-03-PLAN.md <behavior> Task 2 / 07-UI-SPEC.md §Copywriting/§Component Inventory / 07-RESEARCH.md §Pitfall 1
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

UI_DIR = Path("src/ui")
APP_PY = UI_DIR / "app.py"
PREDICTION_TAB_PY = UI_DIR / "prediction_tab.py"
BACKTEST_TAB_PY = UI_DIR / "backtest_tab.py"
CALIBRATION_TAB_PY = UI_DIR / "calibration_tab.py"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read(path), filename=str(path))


def _st_calls(tree: ast.Module, attr_name: str) -> list[ast.Call]:
    """AST を走査し ``st.<attr_name>(...)`` の Call ノードを収集する。"""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == attr_name:
            # st.XXX 形式（value が st 名義・Name node の id="st" または st.column_config のような連鎖）
            calls.append(node)
    return calls


def _first_arg_constants(call: ast.Call) -> list[str]:
    """Call の第一引数が list/tuple of Constant の場合その文字列要素を返す。単一 Constant は1要素で返す。"""
    if not call.args:
        return []
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return [first.value]
    if isinstance(first, (ast.List, ast.Tuple)):
        out: list[str] = []
        for el in first.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                out.append(el.value)
        return out
    return []


def _keyword_value(call: ast.Call, kw_name: str) -> ast.expr | None:
    """Call の keyword 引数の値ノードを返す（なければ None）。"""
    for kw in call.keywords:
        if kw.arg == kw_name:
            return kw.value
    return None


def _all_constant_str_in(node: ast.AST) -> list[str]:
    """AST サブツリー内の全ての str Constant ノードの値を収集する（dict key・value・list 要素含む）。"""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _collect_text_call_constants(py_path: Path) -> list[str]:
    """ファイル内の st.markdown/st.write/st.caption/st.title/st.header/st.subheader の
    第一引数（定数文字列のみ・変数は対象外）を収集する（§16.1 除外項目検証用）。"""
    tree = _parse(py_path)
    targets = {"markdown", "write", "caption", "title", "header", "subheader"}
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in targets:
            # 第一引数が定数文字列の場合のみ収集
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.append(arg.value)
    return out


# ---------------------------------------------------------------------------
# Test 1: app.py st.title 1回・文字列
# ---------------------------------------------------------------------------


def test_app_title_once_with_ja():
    """app.py の ``st.title`` Call が1回・定数文字列が「Keiba AI v3 — 複勝予測分析」を含む（UI-SPEC Typography）。"""
    tree = _parse(APP_PY)
    title_calls = _st_calls(tree, "title")
    assert len(title_calls) == 1, f"st.title は1回のみ（UI-SPEC）・実際: {len(title_calls)}回"
    constants = _first_arg_constants(title_calls[0])
    assert constants, "st.title の第一引数が定数文字列でない"
    assert "Keiba AI v3 — 複勝予測分析" in constants[0], (
        f"st.title 文字列がページタイトルでない: {constants[0]!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: app.py st.tabs 3ラベル
# ---------------------------------------------------------------------------


def test_app_tabs_three_labels():
    """app.py の ``st.tabs`` Call の第一引数（list）に3ラベル「予測一覧」「Backtest」「Segment Calibration」が全て含まれる。"""
    tree = _parse(APP_PY)
    tabs_calls = _st_calls(tree, "tabs")
    assert tabs_calls, "st.tabs 呼出が存在しない（UI-SPEC Layout・3タブ固定）"
    labels = _first_arg_constants(tabs_calls[0])
    required = {"予測一覧", "Backtest", "Segment Calibration"}
    assert required <= set(labels), (
        f"st.tabs のラベルに3タブが全て含まれない・実際: {labels}・必要: {required}"
    )


# ---------------------------------------------------------------------------
# Test 3: app.py sidebar フィルタ（D-02）
# ---------------------------------------------------------------------------


def test_app_sidebar_filters():
    """app.py に ``st.sidebar``（with 文または Attribute access）・``st.date_input``・``st.multiselect`` が存在（D-02）。"""
    source = _read(APP_PY)
    assert "st.sidebar" in source, "st.sidebar が存在しない（D-02 LOCKED）"
    assert "st.date_input" in source, "st.date_input が存在しない（D-02 日付範囲フィルタ）"
    assert "st.multiselect" in source, "st.multiselect が存在しない（D-02 競馬場/ランクフィルタ）"


# ---------------------------------------------------------------------------
# Test 5: prediction_tab.py NumberColumn + %.3f
# ---------------------------------------------------------------------------


def test_prediction_tab_number_column_format():
    """prediction_tab.py のソースに ``st.column_config.NumberColumn`` と ``%.3f`` が含まれる（UI-SPEC Typography）。"""
    source = _read(PREDICTION_TAB_PY)
    assert "st.column_config.NumberColumn" in source, (
        "st.column_config.NumberColumn が存在しない（UI-SPEC Typography・小数点以下3桁）"
    )
    assert "%.3f" in source, "format='%.3f' が存在しない（UI-SPEC Typography・小数点以下3桁）"


# ---------------------------------------------------------------------------
# Test 5b (BLOCKER-4): prediction_tab.py column_config SC#1 の6数値列（HIGH-1 fukusho_*）
# ---------------------------------------------------------------------------


# SC#1 の6数値列（BLOCKER-4・REVIEW HIGH-1・外部 canonical 名 fukusho_*）
REQUIRED_SC1_COLUMNS = {
    "p_fukusho_hit",
    "EV_lower",
    "EV_upper",
    "fukusho_odds_lower",
    "fukusho_odds_upper",
    "recommend_rank",
}


def test_prediction_tab_column_config_has_six_sc1_columns():
    """prediction_tab.py の column_config に SC#1 の6数値列（HIGH-1 fukusho_*）が全て含まれる（BLOCKER-4）。

    どれか1つでも欠けると SC#1（user-observable truth・UI-01）達成不可。AST で column_config
    keyword の dict keys を収集し・変数で渡している場合はソース内に6列名が文字列として出現することを
    fallback 検証する。
    """
    tree = _parse(PREDICTION_TAB_PY)
    df_calls = _st_calls(tree, "dataframe")
    # 馬詳細 dataframe の column_config を持つ呼出を探す
    found_keys: set[str] = set()
    for call in df_calls:
        cfg_node = _keyword_value(call, "column_config")
        if cfg_node is None:
            continue
        # dict のキー（定数文字列のみ）を収集
        if isinstance(cfg_node, ast.Dict):
            for key in cfg_node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found_keys.add(key.value)
        # dict を変数で渡している場合も AST 内の文字列を拾う（fallback 用）
        found_keys.update(_all_constant_str_in(cfg_node))

    # column_config の dict keys に6列が全て含まれるか（AST 直接）
    missing = REQUIRED_SC1_COLUMNS - found_keys
    if missing:
        # 変数で渡している可能性: ソース全体に6列名が文字列として出現するか fallback 検証
        source = _read(PREDICTION_TAB_PY)
        source_has = {c for c in REQUIRED_SC1_COLUMNS if f'"{c}"' in source or f"'{c}'" in source}
        still_missing = REQUIRED_SC1_COLUMNS - source_has
        assert not still_missing, (
            f"prediction_tab.py の column_config/ソースに SC#1 の6数値列が欠落（BLOCKER-4）・"
            f"missing={still_missing}・found_keys={found_keys}"
        )


# ---------------------------------------------------------------------------
# Test 6: prediction_tab.py download label
# ---------------------------------------------------------------------------


def test_prediction_tab_download_label():
    """prediction_tab.py の ``st.download_button`` Call の label 文字列に「予測CSVをダウンロード」が含まれる。"""
    tree = _parse(PREDICTION_TAB_PY)
    dl_calls = _st_calls(tree, "download_button")
    assert dl_calls, "st.download_button 呼出が存在しない（UI-SPEC Copywriting・D-04）"
    labels: list[str] = []
    for call in dl_calls:
        # label= keyword または第一引数
        label_node = _keyword_value(call, "label")
        if label_node is not None:
            if isinstance(label_node, ast.Constant) and isinstance(label_node.value, str):
                labels.append(label_node.value)
        elif call.args:
            first = call.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                labels.append(first.value)
    assert any("予測CSVをダウンロード" in lbl for lbl in labels), (
        f"download_button label に「予測CSVをダウンロード」がない・labels={labels}"
    )


# ---------------------------------------------------------------------------
# Test 7: backtest_tab.py honest warning
# ---------------------------------------------------------------------------


def test_backtest_tab_honest_warning():
    """backtest_tab.py の ``st.warning`` Call の文字列に honest 注記（JODDS 再検証 subject または暫定値）が含まれる。"""
    tree = _parse(BACKTEST_TAB_PY)
    warn_calls = _st_calls(tree, "warning")
    assert warn_calls, "st.warning 呼出が存在しない（UI-SPEC Copywriting・Pitfall 6・必須）"
    # warning の全引数から定数文字列を収集（複数文字列結合の場合もあるため）
    all_text = ""
    for call in warn_calls:
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                all_text += arg.value
    assert ("JODDS オッズ取得完了後に再検証する subject" in all_text) or ("暫定値" in all_text), (
        f"st.warning 文字列に honest 注記がない・actual={all_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 8: backtest_tab.py download label
# ---------------------------------------------------------------------------


def test_backtest_tab_download_label():
    """backtest_tab.py の ``st.download_button`` label に「Backtest CSVをダウンロード」が含まれる。"""
    tree = _parse(BACKTEST_TAB_PY)
    dl_calls = _st_calls(tree, "download_button")
    assert dl_calls, "st.download_button 呼出が存在しない（UI-SPEC Copywriting・D-04）"
    labels: list[str] = []
    for call in dl_calls:
        label_node = _keyword_value(call, "label")
        if label_node is not None and isinstance(label_node, ast.Constant):
            if isinstance(label_node.value, str):
                labels.append(label_node.value)
        elif call.args:
            first = call.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                labels.append(first.value)
    assert any("Backtest CSVをダウンロード" in lbl for lbl in labels), (
        f"download_button label に「Backtest CSVをダウンロード」がない・labels={labels}"
    )


# ---------------------------------------------------------------------------
# Test 9: calibration_tab.py plotly
# ---------------------------------------------------------------------------


def test_calibration_tab_plotly():
    """calibration_tab.py に ``st.plotly_chart`` と ``use_container_width=True`` が含まれる（D-05）。"""
    source = _read(CALIBRATION_TAB_PY)
    assert "st.plotly_chart" in source, "st.plotly_chart が存在しない（D-05 LOCKED）"
    assert "use_container_width=True" in source, (
        "use_container_width=True が存在しない（UI-SPEC Performance Contract・D-05）"
    )


# ---------------------------------------------------------------------------
# Test 10: calibration_tab.py 6軸（D-12）
# ---------------------------------------------------------------------------


def test_calibration_tab_six_axes():
    """calibration_tab.py の ``st.selectbox`` options に6軸（D-12）が全て含まれる。

    ``SEGMENT_AXES`` モジュール定数として定義され・selectbox に変数で渡される場合もあるため・
    AST で selectbox 呼出の存在を確認した上で・モジュール全体の str Constant から6軸が
    全て出現することを検証する（変数渡しの fallback 検証）。
    """
    tree = _parse(CALIBRATION_TAB_PY)
    sb_calls = _st_calls(tree, "selectbox")
    assert sb_calls, "st.selectbox 呼出が存在しない（UI-SPEC Layout・6軸切替）"
    # selectbox の引数/options から直接定数を拾う
    found: set[str] = set()
    for call in sb_calls:
        for arg in call.args[1:3]:
            found.update(_all_constant_str_in(arg))
        opt_node = _keyword_value(call, "options")
        if opt_node is not None:
            found.update(_all_constant_str_in(opt_node))
    required = {"year", "month", "jyocd", "entry_count", "ninki", "odds_band"}
    if not (required <= found):
        # 変数渡しの場合: モジュール全体の str Constant から6軸が全て出現するか fallback
        all_strs = set(_all_constant_str_in(tree))
        missing = required - all_strs
        assert not missing, (
            f"selectbox options/モジュール定数に6軸が全て含まれない・missing={missing}・"
            f"found={found}・all_strs_has={required & all_strs}"
        )


# ---------------------------------------------------------------------------
# Test 11: 全 src/ui/ に unsafe_allow_html=True 不存在（V13）
# ---------------------------------------------------------------------------


def test_no_unsafe_allow_html():
    """src/ui/ 配下の全 .py ファイルに ``unsafe_allow_html=True`` が含まれない（V13・UI-SPEC Registry Safety）。"""
    offenders: list[str] = []
    for py in sorted(UI_DIR.rglob("*.py")):
        source = _read(py)
        if "unsafe_allow_html=True" in source:
            offenders.append(str(py))
    assert not offenders, f"unsafe_allow_html=True を使用しているファイル: {offenders}（V13 違反）"


# ---------------------------------------------------------------------------
# Test 12: §16.1 除外項目（ワイド/荒れ指数/コメント生成）不存在
# ---------------------------------------------------------------------------


def test_no_excluded_section16_1_terms():
    """src/ui/ 配下の st.markdown/st.write/st.caption/st.title/st.header/st.subheader の
    文字列リテラル（定数のみ）に「ワイド」「荒れ指数」「コメント生成」が含まれない（§16.1 除外・UI-SPEC 設計原則4）。

    変数名等で偶発的に出現する可能性を考慮し・検査は描画関数の文字列リテラル（AST Constant）のみに限定する。
    """
    excluded = ["ワイド", "荒れ指数", "コメント生成"]
    offenders: list[str] = []
    for py in sorted(UI_DIR.rglob("*.py")):
        texts = _collect_text_call_constants(py)
        for text in texts:
            for term in excluded:
                if term in text:
                    offenders.append(f"{py}: {term!r} in {text!r}")
    assert not offenders, f"§16.1 除外項目が UI 文字列リテラルに含まれる: {offenders}（Phase 2 以降）"


# ---------------------------------------------------------------------------
# Test 13 (W2): build_calibration_figure trace 数検証
# ---------------------------------------------------------------------------


def test_build_calibration_figure_trace_count():
    """``build_calibration_figure`` に合成 seg_data を渡し trace 数が len(segments)+1 になる（W2・空 Figure/trace 欠落検出）。

    完全予測線（dash gray）1本 + 各 segment curve = 3+1 = 4 trace になることを検証する。
    """
    try:
        from src.ui.calibration_tab import build_calibration_figure
    except ImportError:
        pytest.skip("src.ui.calibration_tab が import 不可（Plan 03 Task 1 未完了・W2 skip）")

    seg_data: dict[str, Any] = {
        "axis_name": "year",
        "segments": [
            {
                "segment_value": "2022",
                "curve": {
                    "count": [10, 10, 10, 10],
                    "frac_pos": [0.1, 0.3, 0.55, 0.9],
                    "mean_pred": [0.12, 0.28, 0.58, 0.88],
                },
                "scalar": {
                    "ece_quantile": 0.02,
                    "ece_uniform": 0.03,
                    "max_dev_guarded": 0.05,
                    "mce_guarded": 0.08,
                    "n_samples": 40,
                },
            },
            {
                "segment_value": "2023",
                "curve": {
                    "count": [10, 10, 10, 10],
                    "frac_pos": [0.08, 0.32, 0.62, 0.92],
                    "mean_pred": [0.10, 0.30, 0.60, 0.90],
                },
                "scalar": {
                    "ece_quantile": 0.01,
                    "ece_uniform": 0.02,
                    "max_dev_guarded": 0.04,
                    "mce_guarded": 0.07,
                    "n_samples": 40,
                },
            },
            {
                "segment_value": "2024",
                "curve": {
                    "count": [10, 10, 10, 10],
                    "frac_pos": [0.12, 0.28, 0.58, 0.85],
                    "mean_pred": [0.14, 0.27, 0.61, 0.87],
                },
                "scalar": {
                    "ece_quantile": 0.03,
                    "ece_uniform": 0.04,
                    "max_dev_guarded": 0.06,
                    "mce_guarded": 0.09,
                    "n_samples": 40,
                },
            },
        ],
    }
    fig = build_calibration_figure(seg_data)
    expected = len(seg_data["segments"]) + 1  # 各 segment curve + 完全予測線1本
    assert len(fig.data) == expected, (
        f"build_calibration_figure の trace 数が期待と不一致・expected={expected}・actual={len(fig.data)}"
    )


# ---------------------------------------------------------------------------
# REVIEW MEDIUM-7: render_prediction_tab 統合テスト（モック DataFrame・軽量）
# ---------------------------------------------------------------------------


def _build_mock_pred_df() -> "Any":
    """SC#1 表示に必要な列を含むモック予測 DataFrame（3レース×各5馬）を構築する。

    PREDICTION_CSV_COLUMNS 全20列を含む。DB に依存しない（REVIEW MEDIUM-7・軽量統合テスト）。
    """
    import pandas as pd

    from src.ui.csv_columns import PREDICTION_CSV_COLUMNS

    rows = []
    for race_idx in range(3):
        race_id = f"2024-01-01-0{race_idx + 1}-01"
        for umaban in range(1, 6):
            row = {col: None for col in PREDICTION_CSV_COLUMNS}
            row["race_id"] = race_id
            row["race_date"] = "2024-01-01"
            row["race_start_datetime"] = "2024-01-01T10:00:00"
            row["競馬場"] = "札幌"
            row["レース番号"] = race_idx + 1
            row["horse_id"] = f"H{race_idx}{umaban:03d}"
            row["horse_name"] = f"馬{race_idx}{umaban}"
            row["枠番"] = umaban
            row["馬番"] = umaban
            row["p_fukusho_hit"] = 0.1 * umaban
            row["fukusho_odds_lower"] = 1.5 + 0.1 * umaban
            row["fukusho_odds_upper"] = 2.5 + 0.1 * umaban
            row["EV_lower"] = 0.15 + 0.01 * umaban
            row["EV_upper"] = 0.25 + 0.01 * umaban
            row["recommend_rank"] = ["S", "A", "B", "C", "D"][umaban - 1]
            row["odds_snapshot_policy"] = "30min_before"
            row["odds_snapshot_at"] = "2024-01-01T09:30:00"
            row["model_version"] = "lgbm_v1"
            row["feature_snapshot_id"] = "feat_v1"
            row["prediction_created_at"] = "2024-01-01T08:00:00"
            rows.append(row)
    return pd.DataFrame(rows)


def test_render_prediction_tab_with_mocked_df(monkeypatch):
    """``render_prediction_tab`` をモック DataFrame で呼出し・st.dataframe が例外なく呼出されることを検証（MEDIUM-7）。

    ``load_predictions_cached`` を合成 DataFrame（PREDICTION_CSV_COLUMNS 全20列・3レース×各5馬）に
    差し替え・``streamlit.dataframe`` と ``streamlit.download_button`` を patch して描画を捕まえる。
    DB pool は mock・実際の SQL/DB に依存しない。missing column による KeyError を統合的に捕捉する。
    """
    import pandas as pd
    import streamlit as st

    from src.ui import prediction_tab

    mock_df = _build_mock_pred_df()
    captured: dict[str, Any] = {"dataframes": [], "download_data": []}

    def _fake_load_predictions_cached(*args, **kwargs):
        return mock_df.copy()

    def _fake_dataframe(data, *args, **kwargs):
        # DataFrameSelection を模倣（.selection.get("rows", []) を持つ）
        captured["dataframes"].append(data)

        class _Sel:
            rows: list[int] = []

            def get(self, key, default=None):
                return self.rows

        class _Event:
            selection = _Sel()

        return _Event()

    def _fake_download_button(*args, **kwargs):
        captured["download_data"].append(kwargs.get("data"))

    monkeypatch.setattr(prediction_tab, "load_predictions_cached", _fake_load_predictions_cached)
    monkeypatch.setattr(st, "dataframe", _fake_dataframe)
    monkeypatch.setattr(st, "download_button", _fake_download_button)
    # st.info / st.subheader / st.columns / st.caption 等の描画も no-op 化
    monkeypatch.setattr(st, "info", lambda *a, **k: None)
    monkeypatch.setattr(st, "subheader", lambda *a, **k: None)
    monkeypatch.setattr(st, "warning", lambda *a, **k: None)
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)

    class _FakeCol:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(st, "columns", lambda n: [_FakeCol() for _ in range(n)])

    # レース一覧が描画されること（master dataframe 呼出）
    try:
        prediction_tab.render_prediction_tab(
            pool=None,  # type: ignore[arg-type]  # mock・DB 非依存
            date_from=None,
            date_to=None,
            selected_jyocd=[],
            selected_ranks=["S", "A", "B"],
        )
    except Exception as e:
        pytest.fail(f"render_prediction_tab が例外で失敗（missing column 等の KeyError の可能性）: {e}")

    # master dataframe が少なくとも1回呼ばれた（レース一覧）
    assert len(captured["dataframes"]) >= 1, "st.dataframe が呼ばれなかった（レース一覧 master）"


# ---------------------------------------------------------------------------
# Test 4 (streamlit_api_usage.py 側で強化): selection_mode 検証は別ファイル
# ここでは legacy selection= 引数が prediction_tab に存在しないことを AST で二重検証
# ---------------------------------------------------------------------------


def test_prediction_tab_no_legacy_selection_arg():
    """prediction_tab.py の ``st.dataframe`` Call が古い ``selection=`` 引数を持たない（RESEARCH Pitfall 1）。"""
    tree = _parse(PREDICTION_TAB_PY)
    df_calls = _st_calls(tree, "dataframe")
    for call in df_calls:
        for kw in call.keywords:
            if kw.arg == "selection":
                pytest.fail(
                    "prediction_tab.py: st.dataframe が古い 'selection=' 引数を使用（Pitfall 1・"
                    "selection_mode= + on_select= を使用すること）"
                )
