# ruff: noqa: E501  (UI 文言の日本語 docstring が長いため行長は緩和・src/ui/loaders.py と同一慣例)
"""Phase 7 予測一覧タブ（UI-SPEC Layout・マスター・ディテール・D-01・Pitfall 1 正引数）。

レース一覧（master）``st.dataframe`` の行選択で下部に各馬詳細（detail）を展開する
マスター・ディテール構造（UI-SPEC Layout L57-67）。

**Pitfall 1 正引数（RESEARCH A1 確定）:**

UI-SPEC Component Inventory の ``selection="single-row"`` は Streamlit の古い API 表記。
Streamlit 1.58.0 では ``selection_mode="single-row"`` + ``on_select="rerun"`` が正引数。
``selection=`` 引数を使用すると ``StreamlitAPIException`` になるため・本モジュールは
``selection_mode`` / ``on_select`` のみを使用する（``test_no_legacy_selection_arg`` で検証）。

**SC#1 の6数値列（BLOCKER-4・REVIEW HIGH-1 外部 canonical 名 fukusho_*）:**

選択レースの各馬 ``st.dataframe`` の ``column_config`` は以下6数値列を
``st.column_config.NumberColumn(format="%.3f")`` で表示する（UI-SPEC Typography・小数点以下3桁）:

- ``p_fukusho_hit`` / ``EV_lower`` / ``EV_upper``
- ``fukusho_odds_lower`` / ``fukusho_odds_upper``（REVIEW HIGH-1・内部名 fuku_odds_* でなく外部 canonical 名）
- ``recommend_rank``

loaders 側で ``normalize_prediction_export_columns`` により既に ``fukusho_*`` に rename 済みの
DataFrame を受け取るため・column_config の key は ``fukusho_odds_lower``/``fukusho_odds_upper`` を使用する。

**再現性スタンプ5項目 inline 表示（§19.1 聖域・UI-SPEC L231）:**

選択レースの代表値を ``st.columns(5)`` + ``st.caption`` で inline 表示:
``odds_snapshot_policy`` / ``odds_snapshot_at`` / ``model_version`` /
``feature_snapshot_id`` / ``backtest_strategy_version``（REVIEW HIGH-4・EV_STRATEGY_VERSION 定数値）。

**派生データは @st.cache_data のみ（CLAUDE.md・Pitfall 4）:**

フィルタ結果・馬 DataFrame 等・st.session_state に保持しない。

参照: 07-03-PLAN.md <action> Task 1.2 / 07-UI-SPEC.md §Layout Contract L57-67 / 07-PATTERNS.md §prediction_tab.py /
      src/ui/loaders.py::load_predictions_cached / build_prediction_csv_bytes
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from psycopg_pool import ConnectionPool

from src.ui.csv_columns import REPRODUCIBILITY_STAMPS
from src.ui.loaders import build_prediction_csv_bytes, load_predictions_cached

# 馬詳細 dataframe の column_config に指定する SC#1 の6数値列（REVIEW HIGH-1・外部 canonical 名 fukusho_*）
_SC1_NUMBER_COLUMNS: tuple[str, ...] = (
    "p_fukusho_hit",
    "EV_lower",
    "EV_upper",
    "fukusho_odds_lower",
    "fukusho_odds_upper",
    "recommend_rank",
)


def _build_race_list_df(pred_df: pd.DataFrame) -> pd.DataFrame:
    """予測 DataFrame を race_id 単位で groupby してレース一覧（master）を構築する。

    派生データは ``@st.cache_data`` を通す前提・st.session_state には保持しない（Pitfall 4）。
    デフォルトソートは ``race_date`` DESC（最新日優先・UI-SPEC Interaction Contract）。

    WR-05 (deep review Warning): Streamlit 1.58 の ``st.dataframe`` は列ヘッダクリックで
    ユーザが column sort を行えるが・sort 後の ``event.selection["rows"]`` は表示順の行 index
    を返すのに対し ``race_list_df.iloc[selected_idx]`` は内部 DataFrame 行位置を参照するため・
    column sort 後は選択したレースと異なる race_id が選ばれるリスクがある。本関数は race_date
    DESC で整列済の初期表示を保証するが・column sort 後の選択ズレは Streamlit 1.58 では column
    sort 無効化フラグがないため構造的に完全防止できない。``render_prediction_tab`` 側では
    ``race_list_df`` の ``race_id`` が groupby で一意である前提で race_id 逆引きし・
    column sort で選択がズレた場合でも race_id が一意である限り最終的な詳細表示は race_id で
    一意に定まる設計を維持する。利用者は column sort 後の選択ズレに注意すること
    (現在の Streamlit API では sort 無効化フラグ不在・docstring 注意書きで運用上カバー)。
    """
    if len(pred_df) == 0:
        return pd.DataFrame(columns=["race_id", "race_date", "競馬場", "レース番号", "頭数", "件数"])
    grouped = (
        pred_df.groupby(["race_id", "race_date", "競馬場", "レース番号"], dropna=False)
        .agg(頭数=("馬番", "count"), 件数=("race_id", "count"))
        .reset_index()
    )
    # race_date DESC（最新日優先・UI-SPEC Interaction Contract）
    grouped = grouped.sort_values("race_date", ascending=False).reset_index(drop=True)
    return grouped


def _build_column_config() -> dict[str, Any]:
    """馬詳細 dataframe の ``column_config`` を構築する（SC#1 の6数値列・%.3f・HIGH-1 fukusho_*）。

    ``p_fukusho_hit`` / ``EV_lower`` / ``EV_upper`` / ``fukusho_odds_lower`` /
    ``fukusho_odds_upper`` / ``recommend_rank`` を ``st.column_config.NumberColumn(format="%.3f")`` で表示。
    """
    config: dict[str, Any] = {}
    for col in _SC1_NUMBER_COLUMNS:
        config[col] = st.column_config.NumberColumn(format="%.3f")
    return config


def _render_reproducibility_stamps(race_pred_df: pd.DataFrame) -> None:
    """選択レースの再現性スタンプ5項目を inline 表示する（§19.1 聖域・UI-SPEC L231）。

    ``odds_snapshot_policy`` / ``odds_snapshot_at`` / ``model_version`` /
    ``feature_snapshot_id`` / ``backtest_strategy_version`` の代表値（先頭行）を
    ``st.columns(5)`` + ``st.caption`` で inline 表示する。
    """
    if len(race_pred_df) == 0:
        return
    first = race_pred_df.iloc[0]
    cols = st.columns(len(REPRODUCIBILITY_STAMPS))
    for col, stamp in zip(cols, REPRODUCIBILITY_STAMPS, strict=True):
        with col:
            st.caption(stamp)
            value = first.get(stamp, "")
            st.caption(str(value) if value is not None and str(value) != "" else "（欠落）")


def render_prediction_tab(
    pool: ConnectionPool,
    date_from: str | None,
    date_to: str | None,
    selected_jyocd: list[str],
    selected_ranks: list[str],
) -> None:
    """予測一覧タブを描画する（マスター・ディテール・Pitfall 1 正引数・SC#1 の6数値列）。

    Parameters
    ----------
    pool : ConnectionPool
        ``get_pool()``（``@st.cache_resource``）由来の readonly pool。
    date_from, date_to : str | None
        ``normalize_date_range`` で正規化済みの ISO 日付（``"YYYY-MM-DD"``）・``None`` で全件。
    selected_jyocd : list[str]
        サイドバーで選択された競馬場コード（空リストで全場）。
    selected_ranks : list[str]
        サイドバーで選択された推奨ランク（空リストで全ランク）。
    """
    # --- 予測 DataFrame 取得（loaders・@st.cache_data・is_primary 絞り済み・fukusho_* rename 済み）---
    pred_df = load_predictions_cached(
        pool,
        date_from=date_from,
        date_to=date_to,
        jyocd_list=selected_jyocd or None,
    )

    # --- 推奨ランクフィルタ（recommend_rank が selected_ranks に含まれる行のみ・空時は全件）---
    if selected_ranks and "recommend_rank" in pred_df.columns:
        pred_df = pred_df[pred_df["recommend_rank"].isin(selected_ranks)]

    st.subheader("レース一覧")
    if len(pred_df) == 0:
        st.info(
            "表示対象のレースがありません。フィルタ条件（日付範囲・競馬場・推奨ランク）を"
            "確認してください。直近の予測日をデフォルト表示しています。"
        )
        return

    race_list_df = _build_race_list_df(pred_df)

    # --- master dataframe・Pitfall 1 正引数（selection_mode + on_select）---
    event = st.dataframe(
        race_list_df,
        selection_mode="single-row",
        on_select="rerun",
        hide_index=False,
    )
    selection = event.selection
    rows = selection.get("rows", [])  # single-row でも list で返る（Pitfall 1）

    if not rows:
        st.info("レースを 1 行選択すると各馬の詳細が表示されます。")
        return

    selected_idx = rows[0]
    selected_race = race_list_df.iloc[selected_idx]
    selected_race_id = selected_race["race_id"]
    # WR-05: race_list_df は _build_race_list_df で race_id 単位の groupby により race_id が一意
    # (1行=1レース)。column sort 後に selection["rows"] が表示順で返っても・race_id 逆引きで
    # pred_df 側を再度フィルタするため・最終的な詳細表示は選択された race_id で一意に定まる。
    # (ただし column sort 後は表示上の選択行と内部 DataFrame 行がズレうるので・ユーザは列 sort
    # 後の選択に注意。Streamlit 1.58 では sort 無効化フラグ不在で構造的完全防止は不可)

    # --- detail: 選択レースの各馬 DataFrame（p_fukusho_hit DESC・確率高い順・UI-SPEC Interaction）---
    race_pred_df = pred_df[pred_df["race_id"] == selected_race_id].copy()
    if "p_fukusho_hit" in race_pred_df.columns:
        race_pred_df = race_pred_df.sort_values("p_fukusho_hit", ascending=False).reset_index(
            drop=True
        )

    st.subheader(f"選択レースの各馬予測: {selected_race_id}")

    # --- 再現性スタンプ5項目 inline（§19.1 聖域）---
    _render_reproducibility_stamps(race_pred_df)

    # --- 馬詳細 dataframe・SC#1 の6数値列 %.3f（HIGH-1 fukusho_*）---
    st.dataframe(race_pred_df, column_config=_build_column_config(), hide_index=True)

    # REVIEW LOW-4: 推奨ランク S 強調色は column_config と競合するため caption 代替（non-blocking polish）
    st.caption("推奨ランク S は上位候補です。色分けは将来の polish で対応予定。")

    # --- CSV download（D-04・REVIEW MEDIUM-6・scope=選択レースのみ・help で明示）---
    st.download_button(
        label="予測CSVをダウンロード",
        data=build_prediction_csv_bytes(race_pred_df),
        file_name=f"predictions_{selected_race_id}.csv",
        mime="text/csv",
        help="選択中のレースの予測行を出力します（現在のフィルタ全体でなく選択レース単位）。",
    )
