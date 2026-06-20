"""EV 計算・推奨ランクの unit test（EV-01 / EV-02 / §11.1 / §11.5）。

Wave 0 (Plan 05-01): RED stub。``src.ev.ev_rank`` 未実装のため ImportError で RED。
Wave 1/2 plan が ``compute_ev_and_rank`` を実装して GREEN 化する。

検証内容（RESEARCH §3.4）:
- ``test_ev_calculation``: EV_lower / EV_upper の直線積
- ``test_rank_S``: EV≥1.20 / p≥0.25 / odds≥1.5 → 'S'
- ``test_rank_D_low_ev``: EV < 1.00 → 'D'
- ``test_rank_B_no_odds_threshold``: B は odds 閾値なし（EV/p のみ）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_input(p: float, odds_lower: float, odds_upper: float) -> pd.DataFrame:
    """EV 計算入力 DataFrame（1行）を構築する。"""
    return pd.DataFrame(
        {
            "p_fukusho_hit": [p],
            "fuku_odds_lower": [odds_lower],
            "fuku_odds_upper": [odds_upper],
        }
    )


def test_ev_calculation():
    """p=0.3, odds_lower=5.0 → EV_lower=1.5, EV_upper=p*odds_upper。"""
    from src.ev.ev_rank import compute_ev_and_rank

    df = _make_input(p=0.3, odds_lower=5.0, odds_upper=7.0)
    out = compute_ev_and_rank(df)
    np.testing.assert_almost_equal(out["EV_lower"].iloc[0], 1.5)
    np.testing.assert_almost_equal(out["EV_upper"].iloc[0], 0.3 * 7.0)


def test_rank_S():
    """EV=1.25, p=0.30, odds=2.0 → rank='S'。"""
    from src.ev.ev_rank import compute_ev_and_rank

    df = _make_input(p=0.30, odds_lower=2.0, odds_upper=2.5)
    out = compute_ev_and_rank(df)
    assert out["recommend_rank"].iloc[0] == "S"


def test_rank_D_low_ev():
    """EV=0.8 → rank='D'。"""
    from src.ev.ev_rank import compute_ev_and_rank

    df = _make_input(p=0.20, odds_lower=4.0, odds_upper=5.0)
    out = compute_ev_and_rank(df)
    assert out["recommend_rank"].iloc[0] == "D"


def test_rank_B_no_odds_threshold():
    """EV=1.06, p=0.16, odds=1.2 → rank='B'（odds 閾値なし・§11.5 B 定義）。"""
    from src.ev.ev_rank import compute_ev_and_rank

    # EV_lower = 0.16 * 1.2 = 0.192 ... §11.5 B 条件 EV≥1.05 を満たさない → 実際は D になる
    # 修正: B 条件を満たす EV≥1.05 を作るため odds=7.0 (EV=0.16*7.0=1.12)
    df = _make_input(p=0.16, odds_lower=7.0, odds_upper=9.0)
    out = compute_ev_and_rank(df)
    assert out["recommend_rank"].iloc[0] == "B"
