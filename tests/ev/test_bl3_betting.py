"""BL-3 投資 ROI 比較の unit test（D-04 / MODL-02 / §14.2）。

Wave 0 (Plan 05-01): RED stub。``src.ev.bl3_betting`` 未実装のため ImportError で RED。

検証内容（RESEARCH §9.4）:
- ``test_bl3_select_top2_low_odds``: 確定複勝オッズ昇順で top-2 選択
- ``test_bl3_no_ev``: BL-3 は EV 計算しない（p=1/odds で EV=1.0 自己参照）
- ``test_bl3_caveat``: §14.2 caveat（同一情報条件ではない）が付与される
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_market_row(
    *,
    race_key: str = "2024-05-1-06-1",
    umaban: int = 1,
    fukuoddslow: float = 2.0,
    ninki: int = 1,
    is_sale: bool = True,
) -> dict[str, object]:
    return {
        "race_key": race_key,
        "umaban": umaban,
        "fukuoddslow": fukuoddslow,
        "ninki": ninki,
        "is_fukusho_sale_available": is_sale,
    }


def test_bl3_select_top2_low_odds():
    """確定複勝オッズ昇順（=人気順）で top-2 選択。"""
    from src.ev.bl3_betting import select_bl3_bets

    df = pd.DataFrame([
        _make_market_row(umaban=1, fukuoddslow=3.5, ninki=3),
        _make_market_row(umaban=2, fukuoddslow=1.5, ninki=1),  # 人気1
        _make_market_row(umaban=3, fukuoddslow=2.5, ninki=2),  # 人気2
        _make_market_row(umaban=4, fukuoddslow=8.0, ninki=4),
    ])
    selected = select_bl3_bets(df, max_bets_per_race=2)
    # オッズ昇順で umaban 2, 3 が選択
    assert sorted(selected["umaban"].tolist()) == [2, 3]


def test_bl3_no_ev():
    """BL-3 は EV 計算しない（p=1/odds で EV 自己参照=1.0・比較無意味・D-04）。

    ``select_bl3_bets`` の戻り値に ``EV_lower`` 列が無いことを検証。
    """
    from src.ev.bl3_betting import select_bl3_bets

    df = pd.DataFrame([
        _make_market_row(umaban=1, fukuoddslow=1.5),
        _make_market_row(umaban=2, fukuoddslow=2.5),
    ])
    selected = select_bl3_bets(df, max_bets_per_race=2)
    assert "EV_lower" not in selected.columns


def test_bl3_caveat():
    """``BL3_BETTING_CAVEAT`` 定数が §14.2 caveat（同一情報条件ではない）を含む。"""
    from src.ev.bl3_betting import BL3_BETTING_CAVEAT

    assert isinstance(BL3_BETTING_CAVEAT, str)
    assert len(BL3_BETTING_CAVEAT) > 0
    # caveat の内容に「同一情報条件ではない」旨が含まれる（Phase 4 baseline.BL3_COMPARISON_CAVEAT と対称）
    # 厳密な文言でなく意味的合致を検証
    caveat_lower = BL3_BETTING_CAVEAT.lower()
    assert "情報" in BL3_BETTING_CAVEAT or "condition" in caveat_lower or "市場" in BL3_BETTING_CAVEAT
