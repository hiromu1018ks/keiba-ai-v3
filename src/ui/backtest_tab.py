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
    ``odds_snapshot_policy`` / ``recovery_rate`` / ``selected_count`` /
    ``latest_race_date``。

    ``recovery_rate`` は §11.6 に従い ``effective_stake`` を分母とする（返還馬=
    ``effective_stake=0`` は分母から控除・``src/ev/metrics.py::compute_backtest_metrics``
    と同口径・前回 CR-01 修正）。``stake`` 分母では返還馬が分母に含まれ回収率が過小評価される。

    **CR-01 (deep review): 代表値の「最新」確定のため ``race_date`` DESC で事前整列する。**
    ``_select_backtests`` の SQL は ``ORDER BY`` を持たないため・groupby ``.iloc[0]`` の
    取得行が時系列最新とは限らない（``backtest_id`` 辞書順 ≠ 作成順・``BT-10`` が ``BT-2``
    より前に来る等）。本関数は groupby 前に ``race_date`` DESC で整列することで・
    (1) 各 group の ``first`` が race_date 最大行になること・
    (2) 表示順（``latest_race_date`` DESC）が最新 backtest 先頭になること・
    を保証する。呼出元の ``summary.iloc[0]`` は race_date 最大の backtest を示す。
    """
    empty_cols = [
        "backtest_id",
        "backtest_strategy_version",
        "train_period",
        "odds_snapshot_policy",
        "recovery_rate",
        "selected_count",
        "latest_race_date",
    ]
    if len(bt_df) == 0:
        return pd.DataFrame(columns=empty_cols)
    # WR-08 (deep review Warning): 必須列の存在を fail-loud 検証。
    # 従来 group.get("effective_stake", pd.Series([0])) の fallback は列欠損を silent に握り潰し
    # total_effective_stake=0 → recovery=NaN → UI に N/A 表示 になる経路を残していた。loaders 契約
    # (load_backtests が BACKTEST_COLUMNS 全列 SELECT) 上は実害はないが・将来 BACKTEST_COLUMNS から
    # effective_stake が外れた場合に silent に回収率が N/A になるのを防ぐため・compute_backtest_metrics
    # (df["effective_stake"].sum() で列不在時は KeyError) と同様に fail-loud で落とす。
    REQUIRED_COLS = ("effective_stake", "payout_amount", "selected_flag")
    missing = [c for c in REQUIRED_COLS if c not in bt_df.columns]
    if missing:
        raise ValueError(
            f"backtest DataFrame に必須列がない: {missing} (loaders 契約違反・"
            f"BACKTEST_COLUMNS の全列 SELECT が期待される)"
        )
    # CR-01: race_date DESC で事前整列（groupby .iloc[0] が最新 race_date 行になるよう保証）。
    # _select_backtests の SQL は ORDER BY を持たないため・ここで明示整列しないと
    # groupby(sort=True 既定) は backtest_id 辞書順を返し「最新」と乖離する。
    # mergesort で stable sort（同 race_date 内の既存順序を保持）。
    if "race_date" in bt_df.columns:
        bt_df = bt_df.sort_values("race_date", ascending=False, kind="mergesort").reset_index(
            drop=True
        )
    rows = []
    # sort=False: 事前整列済の bt_df の出現順を維持（辞書順でなく時系列順）。
    for bt_id, group in bt_df.groupby("backtest_id", dropna=False, sort=False):
        first = group.iloc[0]  # race_date DESC 整列済なので group 内の最新 race_date 行
        # §11.6 回収率は effective_stake 分母（返還馬=effective_stake=0 を分母から控除・
        # src/ev/metrics.py::compute_backtest_metrics と同口径・前回 CR-01 修正）。
        total_effective_stake = float(group.get("effective_stake", pd.Series([0])).fillna(0).sum())
        total_payout = float(group.get("payout_amount", pd.Series([0])).fillna(0).sum())
        recovery = (
            (total_payout / total_effective_stake) if total_effective_stake > 0 else float("nan")
        )
        selected_count = int(
            group.get("selected_flag", pd.Series(dtype=object)).fillna(False).astype(bool).sum()
        )
        latest_race = group["race_date"].max() if "race_date" in group.columns else None
        rows.append(
            {
                "backtest_id": bt_id,
                "backtest_strategy_version": first.get("backtest_strategy_version", ""),
                "train_period": first.get("train_period", ""),
                "odds_snapshot_policy": first.get("odds_snapshot_policy", ""),
                "recovery_rate": recovery,
                "selected_count": selected_count,
                "latest_race_date": latest_race,
            }
        )
    summary = pd.DataFrame(rows, columns=empty_cols)
    # 表示順も最新（latest_race_date 最大）の backtest が先頭になるよう整列。
    # これで render_backtest_tab の summary.iloc[0] が最新 backtest の暫定値を指す。
    if len(summary) > 0 and "latest_race_date" in summary.columns:
        summary = summary.sort_values(
            "latest_race_date", ascending=False, kind="mergesort"
        ).reset_index(drop=True)
    return summary


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
    st.caption(
        "推奨ランクは参考情報であり、購入判断を強制するものではありません（§19.3・実馬券購入はスコープ外）。"
    )

    bt_df = load_backtests_cached(pool)
    if len(bt_df) == 0:
        st.info("backtest データがありません。Phase 5 の backtest 実行後に表示されます。")
        return

    summary = _build_backtest_summary(bt_df)

    # --- メトリクス表示（UI-SPEC Component Inventory・任意・honest 注記と併記）---
    # CR-01: summary は latest_race_date DESC で整列済・iloc[0] は最新 backtest を指す。
    if len(summary) > 0:
        latest = summary.iloc[0]
        latest_date = latest.get("latest_race_date")
        latest_date_label = (
            f"（最新 backtest: {latest_date}）" if latest_date is not None else "（最新 backtest）"
        )
        col1, col2 = st.columns(2)
        with col1:
            rec = latest.get("recovery_rate")
            st.metric(
                f"recovery_rate（暫定）{latest_date_label}",
                value=f"{rec:.3f}" if rec == rec else "N/A",  # NaN チェック (rec != rec)
            )
        with col2:
            st.metric(
                f"selected_count{latest_date_label}",
                value=int(latest.get("selected_count", 0)),
            )

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
