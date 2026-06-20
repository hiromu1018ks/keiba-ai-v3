"""回収率 / P/L / max drawdown / 件数計算の unit test（§11.6）。

Wave 0 (Plan 05-01): RED stub。``src.ev.metrics`` 未実装のため ImportError で RED。

検証内容（RESEARCH §8.4）:
- ``test_metrics_recovery_rate``: payout=150 / effective_stake=100 → 1.5
- ``test_metrics_refund_excluded``: 返還马 effective_stake=0 → 分母から控除
- ``test_metrics_max_drawdown``: 累積 [100, 200, 50, 150] → max DD=150
- ``test_metrics_counts``: selected / effective_bet / refund 件数
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_bet_row(
    *,
    race_key: str = "2024-05-1-06-1",
    umaban: int = 1,
    race_date: str = "2024-06-01",
    stake: int = 100,
    refund_flag: bool = False,
    refund_amount: int = 0,
    payout_amount: int = 0,
    profit: int = -100,
    effective_stake: int = 100,
    fukusho_hit_validated: int = 0,
) -> dict[str, object]:
    return {
        "race_key": race_key,
        "umaban": umaban,
        "race_date": pd.to_datetime(race_date),
        "stake": stake,
        "refund_flag": refund_flag,
        "refund_amount": refund_amount,
        "payout_amount": payout_amount,
        "profit": profit,
        "effective_stake": effective_stake,
        "fukusho_hit_validated": fukusho_hit_validated,
    }


def test_metrics_recovery_rate():
    """payout=150 / effective_stake=100 → recovery_rate=1.5。"""
    from src.ev.metrics import compute_backtest_metrics

    df = pd.DataFrame([
        _make_bet_row(payout_amount=150, profit=50, fukusho_hit_validated=1),
    ])
    metrics = compute_backtest_metrics(df)
    np.testing.assert_almost_equal(metrics["recovery_rate"], 1.5)


def test_metrics_refund_excluded():
    """返還马 effective_stake=0 → 分母から控除される。"""
    from src.ev.metrics import compute_backtest_metrics

    df = pd.DataFrame([
        _make_bet_row(umaban=1, payout_amount=200, profit=100, effective_stake=100,
                       fukusho_hit_validated=1),
        _make_bet_row(umaban=2, refund_flag=True, refund_amount=100,
                       payout_amount=0, profit=0, effective_stake=0,
                       fukusho_hit_validated=0),
    ])
    metrics = compute_backtest_metrics(df)
    # effective_stake 合計 = 100 (返還分は除く) / payout 合計 = 200 → recovery=2.0
    np.testing.assert_almost_equal(metrics["recovery_rate"], 2.0)


def test_metrics_max_drawdown():
    """累積 profit [100, 200, 50, 150] → max DD=150（200→50）。"""
    from src.ev.metrics import compute_backtest_metrics

    df = pd.DataFrame([
        _make_bet_row(umaban=1, race_date="2024-06-01", profit=100),
        _make_bet_row(umaban=2, race_date="2024-06-02", profit=100),
        _make_bet_row(umaban=3, race_date="2024-06-03", profit=-150),
        _make_bet_row(umaban=4, race_date="2024-06-04", profit=100),
    ])
    metrics = compute_backtest_metrics(df)
    # 累積: [100, 200, 50, 150] / running_max: [100, 200, 200, 200]
    # drawdown: [0, 0, 150, 50] → max DD = 150
    assert metrics["max_drawdown"] == 150


def test_metrics_counts():
    """selected / effective_bet / refund 件数が正しく計算される。"""
    from src.ev.metrics import compute_backtest_metrics

    df = pd.DataFrame([
        _make_bet_row(umaban=1, effective_stake=100, fukusho_hit_validated=1),
        _make_bet_row(umaban=2, effective_stake=100, fukusho_hit_validated=0),
        _make_bet_row(umaban=3, refund_flag=True, refund_amount=100,
                       effective_stake=0, fukusho_hit_validated=0),
    ])
    metrics = compute_backtest_metrics(df)
    assert metrics["selected_count"] == 3
    assert metrics["effective_bet_count"] == 2
    assert metrics["refund_count"] == 1
    assert metrics["hit_count"] == 1


def test_metrics_zero_division():
    """全件 ``effective_stake=0`` (全件返還) → ``recovery_rate=0.0`` (ゼロ除算回避・§8.3)。"""
    from src.ev.metrics import compute_backtest_metrics

    df = pd.DataFrame([
        _make_bet_row(umaban=1, refund_flag=True, refund_amount=100,
                       payout_amount=0, profit=0, effective_stake=0,
                       fukusho_hit_validated=0),
        _make_bet_row(umaban=2, refund_flag=True, refund_amount=100,
                       payout_amount=0, profit=0, effective_stake=0,
                       fukusho_hit_validated=0),
    ])
    metrics = compute_backtest_metrics(df)
    assert metrics["recovery_rate"] == 0.0
    assert metrics["effective_bet_count"] == 0


def test_metrics_profit_invariant():
    """行 profit と集計 profit が混在シナリオで恒等的に等しい（MEDIUM-02・T-05-05b mitigate）。

    合成 selected_with_accounting で通常的中 / 不的中 / 返還 / 競走中止 を混在させ・
    ``sum(row.profit) == sum(payout_amount) + sum(refund_amount) - sum(stake)``
    が成立することを assert。refund 行や dead-loss 行で行ベース会計と集計会計が
    分岐しないことを担保する。
    """
    from src.ev.metrics import compute_backtest_metrics

    # 混在シナリオ:
    # - umaban=1: 通常的中 (stake=100, payout=200, refund=0, profit=100, effective_stake=100)
    # - umaban=2: 通常不的中 (stake=100, payout=0, refund=0, profit=-100, effective_stake=100)
    # - umaban=3: 返還 (stake=100, payout=0, refund=100, profit=0, effective_stake=0)
    # - umaban=4: 競走中止 (stake=100, payout=0, refund=0, profit=-100, effective_stake=100)
    df = pd.DataFrame([
        _make_bet_row(umaban=1, stake=100, payout_amount=200, refund_amount=0,
                       profit=100, effective_stake=100, fukusho_hit_validated=1),
        _make_bet_row(umaban=2, stake=100, payout_amount=0, refund_amount=0,
                       profit=-100, effective_stake=100, fukusho_hit_validated=0),
        _make_bet_row(umaban=3, stake=100, payout_amount=0, refund_amount=100,
                       refund_flag=True, profit=0, effective_stake=0,
                       fukusho_hit_validated=0),
        _make_bet_row(umaban=4, stake=100, payout_amount=0, refund_amount=0,
                       profit=-100, effective_stake=100, fukusho_hit_validated=0),
    ])
    metrics = compute_backtest_metrics(df)

    # 不変量: sum(row.profit) == sum(payout) + sum(refund) - sum(stake)
    sum_row_profit = int(df["profit"].sum())
    sum_payout = int(df["payout_amount"].sum())
    sum_refund = int(df["refund_amount"].sum())
    sum_stake = int(df["stake"].sum())
    expected_profit_loss = sum_payout + sum_refund - sum_stake
    assert sum_row_profit == expected_profit_loss, (
        f"行 profit 合計 {sum_row_profit} != 集計 profit {expected_profit_loss} "
        f"(MEDIUM-02: refund/dead-loss 行で会計分岐)"
    )
    # metrics の profit_loss も同一値（集計式）であることを cross-check
    assert metrics["profit_loss"] == expected_profit_loss, (
        f"metrics.profit_loss {metrics['profit_loss']} != 期待値 {expected_profit_loss}"
    )

