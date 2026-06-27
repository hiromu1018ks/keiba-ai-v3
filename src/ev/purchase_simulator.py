"""仮想購入ルール ``fukusho_ev_v1``（BACK-02 / §11.4）。

本モジュールは純粋関数で・固定ルール ``fukusho_ev_v1`` による仮想購入候補を選択する。
``compute_ev_and_rank`` で ``EV_lower`` / ``recommend_rank`` が付与された
予測 DataFrame を受け取り・§11.4 の3条件 filter + レース内 top-2 選択を適用する。

設計（RESEARCH §4.1-§4.5・PATTERNS「purchase_simulator」節）:
- ``_race_normalize_inverse`` (``baseline.py:134-161``) と同一の race_key groupby パターン
- ``sort_values(kind='mergesort')`` で決定論的タイブレーク（共有パターン7・RESEARCH §4.3）
- ``selected_flag`` / ``stake`` / ``backtest_strategy_version`` を付与

§11.4 fukusho_ev_v1 ルール::

    購入単位: 1候補100円
    対象馬券: 複勝のみ
    購入条件:
      EV_lower >= 1.05
      p_fukusho_hit >= 0.15
      fuku_odds_lower >= 1.5
    同一レース制約: EV_lower上位2頭まで
    同一馬への追加購入: なし
    返還: 出走取消・競走除外は返還・競走中止は不的中
"""

from __future__ import annotations

import pandas as pd

# §11.4 fukusho_ev_v1 戦略 version（§19.1 再現性 stamp）
FUKUSHO_EV_V1_STRATEGY = "fukusho_ev_v1"

# §11.4 購入条件閾値（定数）
FUKUSHO_EV_V1_THRESHOLDS: dict[str, float] = {
    "ev_lower_min": 1.05,
    "p_min": 0.15,
    "odds_lower_min": 1.5,
}


def select_bets(
    df: pd.DataFrame,
    *,
    strategy: str = FUKUSHO_EV_V1_STRATEGY,
    max_bets_per_race: int = 2,
    stake_per_bet: int = 100,
    # Phase 12 SC#1 / EV-01 [D-03・Pitfall 7・Claude's Discretion 事前登録]:
    # p_col: ``compute_ev_and_rank`` の EV 計算で使う確率列と同一のものを指定する (D-03・入力列差し替え).
    #   既定 'p_fukusho_hit' は従来互換. Phase 12 のデフォルト経路は 'p_fukusho_hit_lower'.
    # p_min_base: ``FUKUSHO_EV_V1_THRESHOLDS['p_min']`` (0.15) をどの確率列に適用するか.
    #   - 'p' (既定): 従来通り ``p_fukusho_hit >= 0.15`` で判定 (v1.0 binary 呼出互換・A5)
    #   - 'p_lower': ``p_fukusho_hit_lower >= 0.15`` で判定 (Phase 12 デフォルト経路・Pitfall 7 投票層明示)
    # 事前登録値: ``p_min_base='p_lower'`` が Phase 12 評価のデフォルト (CONTEXT Claude's Discretion).
    # test 窓で変更不可 (§11.2 聖域・Shared Pattern 1). run_phase12_evaluation.py (Plan 04) が固定呼出.
    p_col: str = "p_fukusho_hit",
    p_min_base: str = "p",
) -> pd.DataFrame:
    """§11.4 fukusho_ev_v1: フィルタ → レース内 top-2 選択（純粋関数）。

    Parameters
    ----------
    df : pd.DataFrame
        ``compute_ev_and_rank`` 出力（``EV_lower`` / ``recommend_rank`` 付与済み）。
        必須列:
        - ``race_key``: レース識別子
        - ``umaban``: 馬番（タイブレーク用）
        - ``EV_lower``: ``df[p_col] × fuku_odds_lower`` (compute_ev_and_rank の p_col と整合)
        - ``p_fukusho_hit``: キャリブレーション済み確率
        - ``p_fukusho_hit_lower``: Phase 12 下側信頼限界 (``p_col='p_fukusho_hit_lower'`` 時に必須)
        - ``fuku_odds_lower``: 固定 snapshot の複勝最低オッズ（NaN=no_bet）
        - ``is_fukusho_sale_available``: 複勝発売有無（事前 filter）
        - ``is_model_eligible``: モデル適格性（事前 filter）
    strategy : str
        仮想購入戦略名。現在は ``'fukusho_ev_v1'`` のみ対応（§19.1 stamp）。
    max_bets_per_race : int
        レース内最大選択頭数（§11.4 既定: 2）。
    stake_per_bet : int
        1候補あたりの仮想購入額（§11.4 既定: 100円）。
    p_col : str
        Phase 12 D-03: ``compute_ev_and_rank`` の EV 計算と整合する確率列名 (既定 ``'p_fukusho_hit'``).
        Phase 12 評価では ``'p_fukusho_hit_lower'`` を指定して下側信頼限界ベースに切替.
    p_min_base : str
        Phase 12 Pitfall 7 投票層定義の明示:
        - ``'p'`` (既定): ``p_fukusho_hit >= 0.15`` で filter (従来・v1.0 binary 呼出互換・A5)
        - ``'p_lower'``: ``p_fukusho_hit_lower >= 0.15`` で filter (Phase 12 デフォルト経路・事前登録)
        事前登録値 ``'p_lower'`` は Phase 12 評価で固定 (§11.2 聖域・test 窓で変更不可).

    Returns
    -------
    pd.DataFrame
        選択された行（0行〜 ``len(df)`` 行）に以下の列を付与した DataFrame:
        - ``selected_flag``: True（選択された馬）
        - ``stake``: ``stake_per_bet``
        - ``backtest_strategy_version``: ``strategy`` 引数の値

    Notes
    -----
    - ``fuku_odds_lower=NaN`` (``no_bet`` sentinel) は事前 filter で除外（§11.3・D-13）。
    - タイブレーク: ``sort_values(['race_key','EV_lower','umaban'],
      ascending=[True,False,True], kind='mergesort')`` で安定ソート（共有パターン7）。
      ``mergesort`` で seed 非依存の決定論化（pandas default は quicksort・非安定）。
    - 選択後の返還/中止会計は ``refund_accounting`` モジュール（Plan 05-03）が担当。
      本関数は選択のみ（effective_stake/payout は別途計算）。
    - SAFE-01 聖域: 本関数は FEATURE_COLUMNS / build_training_frame / load_feature_matrix 構築経路を
      import しない (EV 計算層で odds を消費するが feature 構築経路からは切り離されている).
    """
    # 事前 filter: 複勝発売あり AND モデル適格 AND no_bet 除外
    eligible_mask = (
        df["is_fukusho_sale_available"].fillna(False).astype(bool)
        & df["is_model_eligible"].fillna(False).astype(bool)
        & df["fuku_odds_lower"].notna()
    )
    eligible = df.loc[eligible_mask].copy()

    # §11.4 購入条件 filter: EV/p/odds の3閾値
    # Phase 12 Pitfall 7: p_min 適用先を p_min_base で明示 (投票層の定義明示・事前登録).
    if p_min_base == "p_lower":
        p_filter_col = "p_fukusho_hit_lower"
    else:  # p_min_base == 'p' (従来・後方互換)
        p_filter_col = "p_fukusho_hit"
    cond_mask = (
        (eligible["EV_lower"] >= FUKUSHO_EV_V1_THRESHOLDS["ev_lower_min"])
        & (eligible[p_filter_col] >= FUKUSHO_EV_V1_THRESHOLDS["p_min"])
        & (eligible["fuku_odds_lower"] >= FUKUSHO_EV_V1_THRESHOLDS["odds_lower_min"])
    )
    eligible = eligible.loc[cond_mask]

    # レース内 top-2: 決定論的タイブレーク（共有パターン7・kind='mergesort'）
    eligible = eligible.sort_values(
        ["race_key", "EV_lower", "umaban"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    selected = eligible.groupby("race_key", group_keys=False).head(max_bets_per_race)

    # 選択 flag / stake / strategy stamp を付与
    selected = selected.copy()
    selected["selected_flag"] = True
    selected["stake"] = stake_per_bet
    selected["backtest_strategy_version"] = strategy
    return selected
