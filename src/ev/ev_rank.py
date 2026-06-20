"""EV 計算・推奨ランク（EV-01 / EV-02 / §11.1 / §11.5）。

本モジュールは純粋関数（DB 不要・pandas Series 演算）で EV と推奨ランクを算出する。
Phase 4 のキャリブレーション済み予測 ``p_fukusho_hit`` と固定 snapshot の
``fuku_odds_lower`` / ``fuku_odds_upper`` を消費し・§11.1 の直線積で EV を計算した上で・
§11.5 の階層判定（S→A→B→C→D）で推奨ランクを付与する。

設計（RESEARCH §3.1-§3.3・PATTERNS「src/ev/ev_rank.py」節）:
- ``compute_bl1`` (``src/model/baseline.py:110-128``) と同一の純粋関数構造
- ``df.copy()`` で入力破壊禁止・pandas Series 演算でベクトル化
- ``odds_lower`` が NaN (``no_bet`` sentinel) の行は rank='D'（選択対象外）

§11.5 推奨ランク閾値（初期仕様・未定義の予測信頼度不使用）::

    S: EV_lower >= 1.20 AND p_fukusho_hit >= 0.25 AND fuku_odds_lower >= 1.5
    A: EV_lower >= 1.10 AND p_fukusho_hit >= 0.20 AND fuku_odds_lower >= 1.5
    B: EV_lower >= 1.05 AND p_fukusho_hit >= 0.15
    C: EV_lower >= 1.00
    D: 上記以外
"""

from __future__ import annotations

import pandas as pd

# §11.5 推奨ランク閾値（定数・T-05-03 mitigate: 閾値のすり替え防止）
# 上から順に階層判定（最初に満たした rank を返す）。
RANK_THRESHOLDS: dict[str, dict[str, float]] = {
    "S": {"ev_lower_min": 1.20, "p_min": 0.25, "odds_lower_min": 1.5},
    "A": {"ev_lower_min": 1.10, "p_min": 0.20, "odds_lower_min": 1.5},
    "B": {"ev_lower_min": 1.05, "p_min": 0.15},
    # C は ev_lower_min=1.00 のみ（odds/p 閾値なし）
    "C": {"ev_lower_min": 1.00},
}


def _rank(row: pd.Series) -> str:
    """§11.5 階層判定（上から順に最初に満たした rank を返す）。

    ``EV_lower`` が NaN の場合は早期 'D' 返却（no_bet・選択対象外・§3.3）。
    """
    ev_lower = row.get("EV_lower")
    p = row.get("p_fukusho_hit")
    odds_lower = row.get("fuku_odds_lower")

    # EV_lower / p / odds_lower が NaN の場合は早期 'D'（no_bet 対策・RESEARCH §3.3）
    if pd.isna(ev_lower) or pd.isna(p) or pd.isna(odds_lower):
        return "D"

    # S: 3 条件 AND
    if (
        ev_lower >= RANK_THRESHOLDS["S"]["ev_lower_min"]
        and p >= RANK_THRESHOLDS["S"]["p_min"]
        and odds_lower >= RANK_THRESHOLDS["S"]["odds_lower_min"]
    ):
        return "S"

    # A: 3 条件 AND
    if (
        ev_lower >= RANK_THRESHOLDS["A"]["ev_lower_min"]
        and p >= RANK_THRESHOLDS["A"]["p_min"]
        and odds_lower >= RANK_THRESHOLDS["A"]["odds_lower_min"]
    ):
        return "A"

    # B: EV + p の 2 条件 AND（odds 閾値なし・§11.5 B 定義）
    if (
        ev_lower >= RANK_THRESHOLDS["B"]["ev_lower_min"]
        and p >= RANK_THRESHOLDS["B"]["p_min"]
    ):
        return "B"

    # C: EV のみ
    if ev_lower >= RANK_THRESHOLDS["C"]["ev_lower_min"]:
        return "C"

    return "D"


def compute_ev_and_rank(df: pd.DataFrame) -> pd.DataFrame:
    """§11.1 EV 計算 + §11.5 推奨ランク付与（純粋関数・DB 不要）。

    Parameters
    ----------
    df : pd.DataFrame
        以下の列を持つ予測+オッズ結合済み DataFrame:
        - ``p_fukusho_hit`` (float): キャリブレーション済み複勝払戻対象確率
        - ``fuku_odds_lower`` (float): 固定 snapshot の複勝最低オッズ
          （``no_bet`` の場合は NaN・§11.3）
        - ``fuku_odds_upper`` (float): 固定 snapshot の複勝最高オッズ
          （``no_bet`` の場合は NaN・§11.3）

    Returns
    -------
    pd.DataFrame
        入力の copy に以下の列を付与した DataFrame:
        - ``EV_lower``: ``p_fukusho_hit * fuku_odds_lower``（§11.1 直線積）
        - ``EV_upper``: ``p_fukusho_hit * fuku_odds_upper``（§11.1 直線積）
        - ``recommend_rank``: 'S' / 'A' / 'B' / 'C' / 'D'（§11.5 階層判定）

    Notes
    -----
    - 入力 DataFrame は破壊しない（``df.copy()`` で純粋関数保証・compute_bl1 と同一パターン）。
    - ``fuku_odds_lower`` が NaN (``no_bet``) の行の ``EV_lower`` / ``EV_upper`` は NaN となり・
      ``recommend_rank`` は 'D' になる（選択対象外・§3.3）。
    """
    out = df.copy()
    # §11.1 直線積（pandas Series 演算）・NaN は伝播して EV_lower/upper も NaN
    out["EV_lower"] = out["p_fukusho_hit"] * out["fuku_odds_lower"]
    out["EV_upper"] = out["p_fukusho_hit"] * out["fuku_odds_upper"]
    # §11.5 階層判定
    out["recommend_rank"] = out.apply(_rank, axis=1)
    return out
