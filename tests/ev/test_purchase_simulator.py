"""仮想購入ルール ``fukusho_ev_v1`` の unit test（BACK-02 / §11.4）。

Wave 0 (Plan 05-01): RED stub。``src.ev.purchase_simulator`` 未実装のため ImportError で RED。

検証内容（RESEARCH §4.6）:
- ``test_purchase_filter_conditions``: EV/p/odds 閾値で正しく filter
- ``test_purchase_top2``: レース内3候補 → 上位2頭選択
- ``test_purchase_tiebreak``: 同 EV で umaban 昇順
- ``test_purchase_no_eligible``: 条件満たさず → 0選択
- ``test_purchase_no_sale``: ``is_fukusho_sale_available=False`` → 除外
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_race_row(
    *,
    race_key: str = "2024-05-1-06-1",
    umaban: int = 1,
    ev_lower: float = 1.10,
    p: float = 0.20,
    odds_lower: float = 5.5,
    is_sale: bool = True,
    is_model_eligible: bool = True,
) -> dict[str, object]:
    return {
        "race_key": race_key,
        "umaban": umaban,
        "EV_lower": ev_lower,
        "p_fukusho_hit": p,
        "fuku_odds_lower": odds_lower,
        "is_fukusho_sale_available": is_sale,
        "is_model_eligible": is_model_eligible,
    }


def test_purchase_filter_conditions():
    """EV≥1.05 / p≥0.15 / odds≥1.5 の3条件を全て満たす馬のみ選択される。"""
    from src.ev.purchase_simulator import select_bets

    df = pd.DataFrame([
        # 選択される (EV=1.20, p=0.20, odds=6.0)
        _make_race_row(umaban=1, ev_lower=1.20, p=0.20, odds_lower=6.0),
        # EV 不合格 (1.04 < 1.05)
        _make_race_row(umaban=2, ev_lower=1.04, p=0.20, odds_lower=5.2),
        # p 不合格 (0.14 < 0.15)
        _make_race_row(umaban=3, ev_lower=1.20, p=0.14, odds_lower=8.0),
        # odds 不合格 (1.4 < 1.5)
        _make_race_row(umaban=4, ev_lower=1.20, p=0.20, odds_lower=1.4),
    ])
    selected = select_bets(df)
    selected_umabans = sorted(selected["umaban"].tolist())
    assert selected_umabans == [1], f"条件 filter 失敗: {selected_umabans}"


def test_purchase_top2():
    """レース内3候補 → 上位2頭選択（EV_lower 降順）。"""
    from src.ev.purchase_simulator import select_bets

    df = pd.DataFrame([
        _make_race_row(umaban=1, ev_lower=1.30, p=0.25, odds_lower=5.2),
        _make_race_row(umaban=2, ev_lower=1.20, p=0.20, odds_lower=6.0),
        _make_race_row(umaban=3, ev_lower=1.10, p=0.20, odds_lower=5.5),
    ])
    selected = select_bets(df, max_bets_per_race=2)
    assert len(selected) == 2
    # EV 降順で umaban 1, 2 が選択
    assert sorted(selected["umaban"].tolist()) == [1, 2]


def test_purchase_tiebreak():
    """同 EV で umaban 昇順（若い馬番優先・決定論）。"""
    from src.ev.purchase_simulator import select_bets

    df = pd.DataFrame([
        _make_race_row(umaban=5, ev_lower=1.20, p=0.20, odds_lower=6.0),
        _make_race_row(umaban=2, ev_lower=1.20, p=0.20, odds_lower=6.0),
        _make_race_row(umaban=8, ev_lower=1.20, p=0.20, odds_lower=6.0),
    ])
    selected = select_bets(df, max_bets_per_race=2)
    assert sorted(selected["umaban"].tolist()) == [2, 5]


def test_purchase_no_eligible():
    """条件を満たす馬がいない → 0選択。"""
    from src.ev.purchase_simulator import select_bets

    df = pd.DataFrame([
        _make_race_row(umaban=1, ev_lower=1.04, p=0.20, odds_lower=5.2),
        _make_race_row(umaban=2, ev_lower=1.20, p=0.14, odds_lower=8.0),
    ])
    selected = select_bets(df)
    assert len(selected) == 0


def test_purchase_no_sale():
    """``is_fukusho_sale_available=False`` → 除外（選択対象外）。"""
    from src.ev.purchase_simulator import select_bets

    df = pd.DataFrame([
        _make_race_row(umaban=1, ev_lower=1.20, p=0.20, odds_lower=6.0, is_sale=False),
    ])
    selected = select_bets(df)
    assert len(selected) == 0
