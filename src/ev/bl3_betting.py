"""BL-3 投資 ROI 比較（D-04 / MODL-02 / §14.2）。

本モジュールは純粋関数で・BL-3（確定複勝オッズが低い=人気順）による固定ルール仮想購入
候補を選択する。Phase 4 D-07 で「betting ROI 比較（固定 snapshot の投資戦略としての BL-3）
は Phase 5」と明記され・本モジュールがその実装を担う。

設計（RESEARCH §9.1-§9.4・PATTERNS「src/ev/bl3_betting.py」節）:
- ``compute_bl3`` (``baseline.py:184-201``) + ``fetch_market_data`` の確定オッズ参照を再利用
- ``BL3_COMPARISON_CAVEAT`` (``baseline.py:63-66``) を import して §14.2 caveat を付与
- ``fukuoddslow`` 昇順（低い=人気高い）で top-2（p=1/odds で EV 自己参照回避・D-04）

核心ルール（D-04）:
    BL-3 は ``p = 1/odds`` で ``EV = p × odds = 1.0`` になるため EV でなく人気順で選ぶ。
    EV 自己参照（常に1.0）では EV 閾値判定が無意味になるため・確定オッズ昇順の人気順で
    固定ルール（top-2・100円・複勝）を適用する。

§14.2 注記（T-05-04 mitigate）:
    BL-3 は確定オッズ（レース後確定）を使用するため・Phase 1-A モデル（出馬表確定時点の
    odds-free feature）と同一情報条件の比較ではない。市場暗示確率ベンチマークとしてのみ
    使用する（``BL3_COMPARISON_CAVEAT`` 再利用）。
"""

from __future__ import annotations

import pandas as pd

from src.model.baseline import BL3_COMPARISON_CAVEAT

# §14.2 caveat を backtest 用に再公開（Phase 4 baseline.BL3_COMPARISON_CAVEAT と同一内容）
BL3_BETTING_CAVEAT: str = BL3_COMPARISON_CAVEAT

# BL-3 固定 sentinel（D-04・20 backtest 行列とは別枠・5窓×1=5 backtest）
BL3_MODEL_TYPE: str = "bl3"
BL3_ODDS_SNAPSHOT_POLICY: str = "confirmed"  # JODDS 時点非依存


def select_bl3_bets(
    market_df: pd.DataFrame,
    *,
    max_bets_per_race: int = 2,
    stake_per_bet: int = 100,
) -> pd.DataFrame:
    """BL-3: 確定複勝オッズ昇順（=人気順）で top-2 選択（純粋関数・D-04）。

    Parameters
    ----------
    market_df : pd.DataFrame
        ``fetch_market_data`` 出力・確定オッズ + race_key を持つ DataFrame。必須列:
        - ``race_key``: レース識別子
        - ``umaban``: 馬番（タイブレーク用）
        - ``fukuoddslow``: 確定複勝最低オッズ（``n_odds_tanpuku`` 由来・レース後確定）
        - ``is_fukusho_sale_available``: 複勝発売有無
    max_bets_per_race : int
        レース内最大選択頭数（既定: 2・主モデル ``select_bets`` と対称）。
    stake_per_bet : int
        1候補あたりの仮想購入額（既定: 100円）。

    Returns
    -------
    pd.DataFrame
        選択された行に以下の列を付与した DataFrame:
        - ``selected_flag``: True
        - ``stake``: ``stake_per_bet``
        - ``model_type``: ``'bl3'`` sentinel
        - ``odds_snapshot_policy``: ``'confirmed'`` sentinel（JODDS 時点非依存・D-04）
        - ``bl3_comparison_caveat``: ``BL3_COMPARISON_CAVEAT``（§14.2 注記・T-05-04 mitigate）

    Notes
    -----
    - BL-3 は ``EV_lower`` 列を付与しない（``p=1/odds`` で ``EV=1.0`` 自己参照になり
      比較が無意味なため・D-04）。``test_bl3_no_ev`` で ``EV_lower`` 列不在を検証。
    - 確定オッズ昇順で top-2（タイブレークは ``umaban`` 昇順・主モデルと対称・決定論的）。
    - ``fukuoddslow`` が NaN / 0 / 負の行は事前 filter で除外（データ異常防御）。
    - BL-3 の ``odds_snapshot_policy='confirmed'`` は JODDS 時点（30min/10min）に非依存の
      sentinel・20 backtest 行列（主モデル2×policy2×窓5=20）とは別枠（窓5×1=5 backtest）。
    """
    # fukuoddslow は fetch_market_data で raw varchar（'0039' 等）のまま取得されるため・
    # 数値比較（> 0）と数値順 sort のために pd.to_numeric で正規化する（str > int の
    # TypeError を防ぐ・解析不能値は NaN で事前除外）。
    odds = pd.to_numeric(market_df["fukuoddslow"], errors="coerce")
    # 事前 filter: 複勝発売あり AND fukuoddslow 有効（notna AND > 0）
    eligible_mask = (
        market_df["is_fukusho_sale_available"].fillna(False).astype(bool)
        & odds.notna()
        & (odds > 0)
    )
    eligible = market_df.loc[eligible_mask].copy()
    eligible["fukuoddslow"] = odds.loc[eligible_mask].to_numpy()

    # 確定複勝オッズ昇順（低い=人気が高い）で top-2（決定論的タイブレーク・共有パターン7）
    eligible = eligible.sort_values(
        ["race_key", "fukuoddslow", "umaban"],
        ascending=[True, True, True],
        kind="mergesort",
    )
    selected = eligible.groupby("race_key", group_keys=False).head(max_bets_per_race)

    # BL-3 sentinel 付与（model_type / odds_snapshot_policy / caveat）
    selected = selected.copy()
    selected["selected_flag"] = True
    selected["stake"] = stake_per_bet
    selected["model_type"] = BL3_MODEL_TYPE
    selected["odds_snapshot_policy"] = BL3_ODDS_SNAPSHOT_POLICY
    selected["bl3_comparison_caveat"] = BL3_BETTING_CAVEAT
    return selected
