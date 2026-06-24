# ruff: noqa: E501  (UI 文言の日本語 docstring が長いため行長は緩和・src/ui/loaders.py と同一慣例)
"""Phase 7 Presentation Streamlit エントリポイント（UI-SPEC Layout Contract・D-01..D-05 LOCKED）。

単一ページ + ``st.tabs(3)`` 構成（multipage でない・UI-SPEC Layout L40-85）。サイドバーに
主要フィルタ（日付範囲・競馬場・推奨ランク・D-02 LOCKED）と手動キャッシュ更新ボタン
（REVIEW MEDIUM-2）を集約する。3つの render_* 関数（``render_prediction_tab``/
``render_backtest_tab``/``render_calibration_tab``）に pool と sidebar フィルタ引数を渡す。

**pool lifecycle（REVIEW HIGH-5 解決）:**

``@st.cache_resource`` 付き ``get_pool()`` で単一 readonly pool をプロセス内保持し・
rerun ごとに close しない。これにより ``@st.cache_data(hash_funcs={ConnectionPool: id})``
の id が安定して cache hit する（rerun ごとに pool id が変わり cache miss 連発する問題を解決）。
プロセス終了時の pool close は Streamlit runtime に委ねる（try-finally close は廃止）。

**read-only 保証（D-03・Phase 8 TEST-01 前提）:**

- ``make_readonly_pool``（``make_pool(role="readonly")`` の薄い wrapper）のみ使用・
  ``write_cursor`` / ``make_pool(role="etl")`` 経路を持たない。
- DB 接続失敗時は ``st.error`` で定型メッセージ（生 DSN 絶対禁止・dsn_masked も表示しない・
  UI-SPEC Copywriting・ASVS V8）。

参照: 07-03-PLAN.md <action> Task 1 / 07-UI-SPEC.md §Layout Contract / 07-PATTERNS.md §src/ui/app.py /
      src/ui/loaders.py::make_readonly_pool / src/config/settings.py::Settings
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit のスクリプト実行は app.py のある ``src/ui/`` を ``sys.path[0]`` に設定するため、
# プロジェクトルートを含めないと ``from src.*`` が解決できない。hatch wheel ``packages`` への
# ``src/ui`` 追加だけでは ``streamlit run`` は動かない（07-RESEARCH.md L639 の誤結論を訂正）。
# ``scripts/run_backtest.py`` / ``run_export_*.py`` と同一の ``sys.path.insert`` パターン
# （07-PATTERNS.md §Imports pattern・起動時 ModuleNotFoundError 回帰防止）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st  # noqa: E402
from psycopg_pool import ConnectionPool  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.ui.backtest_tab import render_backtest_tab  # noqa: E402
from src.ui.calibration_tab import render_calibration_tab  # noqa: E402
from src.ui.jyocd_map import load_jyocd_map  # noqa: E402
from src.ui.loaders import make_readonly_pool, normalize_date_range  # noqa: E402
from src.ui.prediction_tab import render_prediction_tab  # noqa: E402


@st.cache_resource
def get_pool() -> ConnectionPool:  # type: ignore[empty-body]
    """プロセス内で単一の readonly ConnectionPool を保持する（REVIEW HIGH-5 解決）。

    ``@st.cache_resource`` でプロセス内キャッシュされるため・rerun ごとに pool を再構築
    しない（pool id が安定し ``@st.cache_data(hash_funcs={ConnectionPool: id})`` が cache hit
    する）。``make_readonly_pool`` は ``make_pool(role="readonly")`` の薄い wrapper で・
    ``write_cursor`` / ``role="etl"`` 経路を持たない（D-03 read-only 保証）。
    """
    return make_readonly_pool(Settings())


def main() -> None:
    """Streamlit エントリポイント（UI-SPEC Layout・3タブ・sidebar フィルタ・pool lifecycle）。"""
    st.set_page_config(page_title="Keiba AI v3 — 複勝予測分析", layout="wide")
    st.title("Keiba AI v3 — 複勝予測分析")

    jyocd_map = load_jyocd_map()

    # --- sidebar（D-02 LOCKED・主要フィルタ）---
    with st.sidebar:
        raw_dates = st.date_input("日付範囲", [])
        date_from, date_to = normalize_date_range(raw_dates)  # NEW-L1・loaders の単一定義を import
        selected_jyocd = st.multiselect(
            "競馬場",
            options=list(jyocd_map.keys()),
            format_func=lambda c: jyocd_map.get(c, c),
            default=[],
        )
        selected_ranks = st.multiselect(
            "推奨ランク", ["S", "A", "B", "C", "D"], default=["S", "A", "B"]
        )
        # REVIEW MEDIUM-2: 手動キャッシュ更新ボタン（TTL 暗黙依存でなく陳腐化を明示的に解消）
        if st.button("キャッシュ更新", help="DB から最新データを再取得します"):
            st.cache_data.clear()
        st.caption("データソース: PostgreSQL keiba_readonly ロール（read-only・stamped）")

    # --- pool lifecycle（REVIEW HIGH-5・@st.cache_resource で単一 pool 保持）---
    try:
        pool = get_pool()
    except Exception:
        # DB 接続失敗・生 DSN は絶対に含めない（UI-SPEC Copywriting・ASVS V8）
        st.error(
            "PostgreSQL（keiba_readonly ロール）に接続できません。"
            "src/config/ の DSN と PostgreSQL 起動状態を確認してください。"
        )
        return

    # --- 3タブ（UI-SPEC Layout・multipage でなく単一ページ内タブ）---
    tab_pred, tab_bt, tab_cal = st.tabs(["予測一覧", "Backtest", "Segment Calibration"])
    with tab_pred:
        render_prediction_tab(pool, date_from, date_to, selected_jyocd, selected_ranks)
    with tab_bt:
        render_backtest_tab(pool)
    with tab_cal:
        render_calibration_tab()


if __name__ == "__main__":
    main()
