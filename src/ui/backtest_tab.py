# ruff: noqa: E501  (UI 文言の日本語 docstring が長いため行長は緩和・src/ui/loaders.py と同一慣例)
"""Phase 7 Backtest タブ（UI-SPEC Layout・honest 注記・OUT-02 表示元・Pitfall 6）。

backtest 一覧を ``st.dataframe`` で表示し・回収率/選定数のメトリクス（``st.metric``）と
CSV ダウンロード（OUT-02・``build_backtest_csv_bytes``）を提供する。

**honest 注記（UI-SPEC Copywriting・Pitfall 6・Phase 5 manual-only 整合）:**

backtest の odds 正確性は JODDS オッズ取得完了後の再検証 subject である旨を
``st.warning`` で必ず表示する（確定ニュアンスの語を使わない・常に「暫定」「参考」修飾）。
``test_backtest_tab_honest_warning`` で文字列検証する。

参照: 07-03-PLAN.md <action> Task 1.3 / 07-UI-SPEC.md §Layout Contract L69-77 / 07-PATTERNS.md §backtest_tab.py /
      src/ui/loaders.py::load_backtests_cached / build_backtest_csv_bytes
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from psycopg_pool import ConnectionPool

from src.ui.loaders import build_backtest_csv_bytes, load_backtests_cached


def _build_backtest_summary(bt_df: pd.DataFrame) -> pd.DataFrame:
    """backtest DataFrame を backtest_id 単位で groupby してメトリクス一覧を構築する。

    列: ``backtest_id`` / ``backtest_strategy_version`` / ``train_period`` /
    ``odds_snapshot_policy`` / ``recovery_rate`` / ``selected_count``。
    """
    if len(bt_df) == 0:
        return pd.DataFrame(
            columns=[
                "backtest_id",
                "backtest_strategy_version",
                "train_period",
                "odds_snapshot_policy",
                "recovery_rate",
                "selected_count",
            ]
        )
    rows = []
    for bt_id, group in bt_df.groupby("backtest_id", dropna=False):
        first = group.iloc[0]
        total_stake = float(group.get("stake", pd.Series([0])).fillna(0).sum())
        total_payout = float(group.get("payout_amount", pd.Series([0])).fillna(0).sum())
        recovery = (total_payout / total_stake) if total_stake > 0 else float("nan")
        selected_count = int(
            group.get("selected_flag", pd.Series(dtype=object)).fillna(False).astype(bool).sum()
        )
        rows.append(
            {
                "backtest_id": bt_id,
                "backtest_strategy_version": first.get("backtest_strategy_version", ""),
                "train_period": first.get("train_period", ""),
                "odds_snapshot_policy": first.get("odds_snapshot_policy", ""),
                "recovery_rate": recovery,
                "selected_count": selected_count,
            }
        )
    return pd.DataFrame(rows)


def render_backtest_tab(pool: ConnectionPool) -> None:
    """Backtest タブを描画する（honest 注記・メトリクス・CSV download）。

    Parameters
    ----------
    pool : ConnectionPool
        ``get_pool()``（``@st.cache_resource``）由来の readonly pool。
    """
    # --- honest 注記（UI-SPEC Copywriting・Pitfall 6・必須・確定ニュアンスの語を使わない）---
    st.warning(
        "注意: この backtest の odds 正確性は JODDS オッズ取得完了後に再検証する subject です。"
        "現状の回収率は暫定値であり、確定後に入れ替わる可能性があります。"
    )
    st.caption("推奨ランクは参考情報であり、購入判断を強制するものではありません（§19.3・実馬券購入はスコープ外）。")

    bt_df = load_backtests_cached(pool)
    if len(bt_df) == 0:
        st.info("backtest データがありません。Phase 5 の backtest 実行後に表示されます。")
        return

    summary = _build_backtest_summary(bt_df)

    # --- メトリクス表示（UI-SPEC Component Inventory・任意・honest 注記と併記）---
    if len(summary) > 0:
        latest = summary.iloc[0]
        col1, col2 = st.columns(2)
        with col1:
            rec = latest.get("recovery_rate")
            st.metric(
                "recovery_rate（暫定）",
                value=f"{rec:.3f}" if rec == rec else "N/A",  # NaN チェック (rec != rec)
            )
        with col2:
            st.metric("selected_count", value=int(latest.get("selected_count", 0)))

    st.subheader("backtest 一覧")
    st.dataframe(summary, hide_index=True)

    # --- CSV download（OUT-02・D-04・build_backtest_csv_bytes）---
    st.download_button(
        label="Backtest CSVをダウンロード",
        data=build_backtest_csv_bytes(bt_df),
        file_name="backtest.csv",
        mime="text/csv",
        help="backtest 全行の OUT-02 CSV（16列・UTF-8 BOM + CRLF）を出力します。",
    )
