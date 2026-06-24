# ruff: noqa: E501
"""backtest_tab._build_backtest_summary の §11.6 回収率口径検証（CR-01 回帰防止）。

CR-01 (code review Critical): backtest_tab.py の recovery_rate が ``stake`` 分母で
Phase 5 ``src/ev/metrics.py::compute_backtest_metrics``（= sum(payout)/sum(effective_stake)）と
口径分裂していたのを ``effective_stake`` 分母に修正。返還馬 (effective_stake=0) が分母に
含まれ回収率が過小評価される回帰を防止する。

参照: 07-REVIEW.md CR-01 / src/ev/metrics.py L14/L84-85 / §11.6 払戻規則
"""

from __future__ import annotations

import pandas as pd

from src.ui.backtest_tab import _build_backtest_summary


def _row(
    backtest_id: str = "BT-1",
    stake: int = 100,
    effective_stake: int = 100,
    payout: float = 0.0,
    selected: bool = True,
) -> dict:
    return {
        "backtest_id": backtest_id,
        "backtest_strategy_version": "fukusho_ev_v1",
        "train_period": "2019-06〜2022",
        "odds_snapshot_policy": "30min_before",
        "stake": stake,
        "effective_stake": effective_stake,
        "payout_amount": payout,
        "selected_flag": selected,
    }


def test_recovery_rate_uses_effective_stake_denominator():
    """recovery_rate は effective_stake 分母（返還馬=effective_stake=0 は分母から控除・Phase 5 metrics.py 同口径）。

    返還馬 (effective_stake=0, payout=0) + 的中馬 (effective_stake=100, payout=150):
    - effective_stake 分母（正）: 150/100 = 1.5
    - stake 分母（CR-01 修正前・誤）: 150/200 = 0.75
    """
    bt = pd.DataFrame(
        [
            _row(effective_stake=0, payout=0.0),  # 返還馬（競走中止・effective_stake=0）
            _row(effective_stake=100, payout=150.0),  # 的中馬
        ]
    )
    summary = _build_backtest_summary(bt)
    assert len(summary) == 1
    rec = summary.iloc[0]["recovery_rate"]
    assert rec == 1.5, (
        f"recovery_rate は effective_stake 分母 (1.5) であるべき・stake 分母 (0.75) でない（CR-01・§11.6）: {rec}"
    )


def test_recovery_rate_zero_when_all_refunded():
    """全件返還（effective_stake 合計 0）は recovery_rate=NaN（ゼロ除算回避・§8.3・UI は N/A 表示）。"""
    bt = pd.DataFrame(
        [
            _row(effective_stake=0, payout=0.0),
            _row(effective_stake=0, payout=0.0),
        ]
    )
    summary = _build_backtest_summary(bt)
    rec = summary.iloc[0]["recovery_rate"]
    assert rec != rec, f"全件返還時は recovery_rate=NaN であるべき（§8.3・ゼロ除算回避）: {rec}"


def test_recovery_rate_empty_dataframe():
    """空 DataFrame は空 summary（recovery_rate 列存在）。"""
    summary = _build_backtest_summary(pd.DataFrame())
    assert len(summary) == 0
    assert "recovery_rate" in summary.columns
