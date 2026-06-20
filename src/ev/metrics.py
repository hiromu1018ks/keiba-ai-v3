"""回収率 / P/L / max drawdown / 件数計算（§11.6）。

本モジュールは純粋関数で・backtest 結果 DataFrame から §11.6 の回収率指標を算出する。
返還馬は ``effective_stake=0`` で分母から控除・競走中止は ``effective_stake=100`` で
実運用の負けを消さない（§10.6）。max drawdown は ``race_date`` 昇順の累積 profit から計算。

設計（RESEARCH §8.1-§8.3・PATTERNS「metrics」節 + 共有パターン7）:
- ``compute_bl1`` (``baseline.py:110-128``) と同一の純粋 pandas 関数パターン
- ``effective_stake`` 合計 0 は ``recovery_rate=0.0``（ゼロ除算回避・§8.3）
- max drawdown: ``race_date`` 昇順で累積 profit の ``cummax - cumsum``（行整列・共有パターン7）

§11.6 指標定義::

    回収率 = sum(payout_amount) / sum(effective_stake)
    損益 (P/L) = sum(payout_amount) + sum(refund_amount) - sum(stake)
    selected_count = 返還を含む選択数
    effective_bet_count = 返還を除く実購入数
    refund_count = 返還数
    hit_count = fukusho_hit_validated=1 の件数
"""

from __future__ import annotations

import pandas as pd


def compute_backtest_metrics(df: pd.DataFrame) -> dict:
    """§11.6 回収率 / P/L / max drawdown / 件数を算出（純粋関数）。

    Parameters
    ----------
    df : pd.DataFrame
        backtest 結果の selected 行 DataFrame。必須列:
        - ``race_key``: レース識別子（行整列用）
        - ``umaban``: 馬番（行整列用）
        - ``race_date``: レース日（max drawdown の時系列順累積用）
        - ``stake``: 仮想購入額（0 or 100）
        - ``refund_flag``: 返還有無
        - ``refund_amount``: 返還金額
        - ``payout_amount``: 払戻金額（100円あたり実額・表示オッズでない）
        - ``profit``: 行 profit（= payout + refund - stake・refund_accounting 出力）
        - ``effective_stake``: 実効購入額（返還=0 / 通常・中止=100・§11.6）
        - ``fukusho_hit_validated``: 的中判定（0/1）

    Returns
    -------
    dict
        以下の key を持つ指標 dict:
        - ``recovery_rate``: 回収率（= sum(payout)/sum(effective_stake)・分母0なら0.0）
        - ``profit_loss``: 損益（= sum(payout) + sum(refund) - sum(stake)・集計式）
        - ``max_drawdown``: 最大下落幅（race_date 昇順の累積 profit cummax-cumsum）
        - ``selected_count``: 選択数（返還含む）
        - ``effective_bet_count``: 実購入数（返還除く・effective_stake>0）
        - ``refund_count``: 返還数
        - ``hit_count``: 的中数

    Notes
    -----
    - ``effective_stake`` 合計 0（全件返還の極端ケース）→ ``recovery_rate=0.0``
      （§8.3・ゼロ除算回避）。
    - max drawdown は ``race_date`` 昇順（同日内は ``race_key``→``umaban``）で累積 profit
      を計算し・ピーク（``cummax``）からの最大下落（``cummax - cumsum``）を返す。
      行整列は ``sort_values(kind='mergesort')`` で安定化（共有パターン7・T-05-05 mitigate）。
    - ``profit_loss`` は集計式（``sum(payout)+sum(refund)-sum(stake)``）を採用。
      行ごとの ``profit``（``refund_accounting`` 出力）との不変量
      ``sum(row.profit) == sum(payout)+sum(refund)-sum(stake)`` は
      ``test_metrics_profit_invariant`` で混在シナリオ検証済み（MEDIUM-02）。
    """
    total_payout = float(df["payout_amount"].sum())
    total_effective_stake = float(df["effective_stake"].sum())
    total_stake = float(df["stake"].sum())
    total_refund = float(df["refund_amount"].sum())

    # §11.6 回収率（ゼロ除算回避・§8.3）
    recovery_rate = (
        total_payout / total_effective_stake if total_effective_stake > 0 else 0.0
    )
    # §11.6 損益（集計式）
    profit_loss = int(total_payout + total_refund - total_stake)

    # max drawdown: race_date 昇順で累積 profit の cummax - cumsum（行整列・共有パターン7）
    df_sorted = df.sort_values(
        ["race_date", "race_key", "umaban"], kind="mergesort"
    )
    cumulative = df_sorted["profit"].astype(float).cumsum()
    running_max = cumulative.cummax()
    drawdown = running_max - cumulative
    max_drawdown = int(drawdown.max()) if len(drawdown) > 0 else 0

    return {
        "recovery_rate": recovery_rate,
        "profit_loss": profit_loss,
        "max_drawdown": max_drawdown,
        "selected_count": int(len(df)),
        "effective_bet_count": int((df["effective_stake"] > 0).sum()),
        "refund_count": int(df["refund_flag"].sum()) if "refund_flag" in df.columns else 0,
        "hit_count": int(df["fukusho_hit_validated"].sum()),
    }
