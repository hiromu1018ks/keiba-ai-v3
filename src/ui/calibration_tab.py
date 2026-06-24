# ruff: noqa: E501  (UI 文言の日本語 docstring が長いため行長は緩和・src/ui/loaders.py と同一慣例)
"""Phase 7 Segment Calibration タブ（UI-SPEC Layout・D-05 Plotly 動的描画・D-12 の6軸）。

``reports/06-segments/<axis>.json`` を読込み・Plotly で calibration curve を重ね描きする
（D-05 LOCKED・UI-SPEC Performance Contract・``width="stretch"``）。scalar 指標表
（ECE/MCE/max_dev_guarded/n_samples・D-11）を ``st.dataframe`` で併記する。

DB pool 不要・reports/06-segments/*.json のみ消費する（stamped 成果物・再集計しない・§19.1）。

**6軸（D-12 LOCKED）:** ``year`` / ``month`` / ``jyocd`` / ``entry_count`` / ``ninki`` / ``odds_band``。

**empty state（UI-SPEC Copywriting）:** segment JSON 未生成時は ``st.info`` で案内。

参照: 07-03-PLAN.md <action> Task 1.4 / 07-UI-SPEC.md §Layout Contract L78-84 / 07-PATTERNS.md §calibration_tab.py /
      src/ui/loaders.py::load_segment_json_cached / reports/06-segments/*.json (入力スキーマ)
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st

from src.ui.loaders import load_segment_json_cached

# D-12 LOCKED: segment 軸6種
SEGMENT_AXES: tuple[str, ...] = (
    "year",
    "month",
    "jyocd",
    "entry_count",
    "ninki",
    "odds_band",
)


def build_calibration_figure(seg_data: dict[str, Any]) -> go.Figure:
    """segment データから calibration curve 重ね描き Figure を構築する（D-05・RESEARCH Code Examples L458-485）。

    各 segment の ``curve`` (``mean_pred`` vs ``frac_pos``) を ``go.Scatter`` で重ね描きし・
    完全予測線（``y=x``・dash gray）を1本追加する。戻り値の ``len(fig.data)`` は
    ``len(seg_data["segments"]) + 1``（各 segment curve + 完全予測線1本）になる
    （``test_build_calibration_figure_trace_count`` で検証・W2・空 Figure や trace 欠落を fail-loud）。

    Parameters
    ----------
    seg_data : dict[str, Any]
        ``load_segment_json(axis)`` の戻り値。``axis_name`` + ``segments[]``
        (各 ``curve``/``scalar``/``segment_value``) を持つ。
    """
    fig = go.Figure()
    segments = seg_data.get("segments", [])
    for seg in segments:
        curve = seg.get("curve", {})
        sv = seg.get("segment_value", "")
        n = seg.get("scalar", {}).get("n_samples", 0)
        label = f"{sv} (n={n:,})"
        fig.add_trace(
            go.Scatter(
                x=curve.get("mean_pred", []),
                y=curve.get("frac_pos", []),
                mode="lines+markers",
                name=label,
                hovertemplate=f"{label}<br>予測: %{{x:.3f}}<br>実測: %{{y:.3f}}<extra></extra>",
            )
        )
    # 完全予測線（y=x・dash gray・showlegend=False）
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(dash="dash", color="gray"),
            name="完全予測",
            showlegend=False,
            hovertemplate="完全予測<br>予測: %{x:.3f}<br>実測: %{y:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="予測確率 (mean_pred)",
        yaxis_title="実測頻度 (frac_pos)",
        xaxis_range=[0, 1],
        yaxis_range=[0, 1],
        legend_title=seg_data.get("axis_name", ""),
    )
    return fig


def render_calibration_tab() -> None:
    """Segment Calibration タブを描画する（6軸 selectbox・Plotly 動的描画・scalar 表）。

    DB pool 不要・``reports/06-segments/*.json`` のみ消費（stamped・§19.1）。
    """
    axis = st.selectbox("segment 軸", SEGMENT_AXES)
    seg_data = load_segment_json_cached(axis)

    if not seg_data:
        st.info(
            "segment データが未生成です。scripts/run_evaluation.py を実行して "
            "reports/06-segments/ を生成してください。"
        )
        return

    # --- Plotly 動的描画（D-05・width="stretch"・fig.show() でない）---
    fig = build_calibration_figure(seg_data)
    st.plotly_chart(fig, width="stretch")

    # --- scalar 指標表（D-11・ECE/MCE/max_dev_guarded/n_samples）---
    scalar_rows = []
    for seg in seg_data.get("segments", []):
        row: dict[str, Any] = {"segment_value": seg.get("segment_value", "")}
        row.update(seg.get("scalar", {}))
        scalar_rows.append(row)
    if scalar_rows:
        st.subheader("scalar 指標")
        st.dataframe(pd_safe(scalar_rows), hide_index=True)


def pd_safe(rows: list[dict[str, Any]]) -> object:
    """``pd.DataFrame`` への変換を遅延 import で包む helper（module top-level の pandas import を避ける）。"""
    import pandas as pd

    return pd.DataFrame(rows)
