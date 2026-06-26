# ruff: noqa: E501  (docstring / 日本語コメント行長は緩和・speed_figure.py / field_strength.py / rolling.py と同一慣例)
"""Phase 10 PLAN 03・FEAT-03 レース内相対特徴量（target-only・D-07〜D-12）.

本 module は target observation の feature_matrix 上でのみ動作し・race_id (race_nkey) 単位の
group-by でレース内相対特徴量 (rank 3軸 / gap_to_top / gap_to_3rd / field_strength_adjusted_rank)
を算出する。過去走 history には適用しない (D-07 target-only・Pitfall 4 回避)。

3聖域（本 module の不変事項・adversarial テスト + AST audit で機械保証）:

1. **市場情報不使用（SAFE-01）**
   - オッズ/人気/過去人気/過去オッズ 等・市場情報 proxy は feature に一切入れない。
   - 本 module のソース上の識別子・文字列リテラルに市場情報系トークンは現れない。
   - PLAN 07 が AST audit で完全証明する (SC#4 下地)。

2. **target-only（D-07）**
   - FEAT-03 は target observation のみで計算される・過去走には適用しない。
   - rank 母集団は feature_cutoff_datetime 時点で確定した rolling_speed_figure_mean_5 等
     (Phase 9.1 / PLAN 02 で strict ``<cutoff`` 済み) のみ・当日結果は不使用。
   - 出馬表確定時点 (entry_confirmed) での順序付けを future-information なしで確定する。

3. **byte-reproducible（§19.1）**
   - 決定論的アルゴリズム (pandas Series.rank・method="min"・ascending=False・na_option="keep"
     competition ranking) で同一入力は bit-identical。

§11.2 聖域（test 窓選び直し禁止）:
   field_strength_adjusted_rank の係数は 0.25 canonical を事前登録公開定数とする。
   候補 {0.0, 0.1, 0.25, 0.5} は train/calib 窓内のみ感度分析 (W-2 diagnostic) で使用し・
   feature_matrix に出力するのは coef=0.25 canonical の rank のみ。候補別 score の一時列は
   関数末尾で確実に drop され・戻り値 columns に残存しない (W-5 機械保証)。

CYCLE-3 MEDIUM #2 (10-REVIEWS.md L222・par-scale 兼容性・非リーク):
   rolling_speed_figure_mean_5 (target 経路・horse-level par 由来) と
   rolling_field_strength_mean_mean_5 (PLAN 01 source-asof 経路) は同一 horse-level par
   normalization 上にある (PLAN 01 が obs_id を SOURCE_ASOF_<race_nkey>_<kettonum> として
   target 経路と揃えたため) ・よって additive score の加算項は scale 整合し・係数 0.25 の
   事前登録 canonical が意味的に妥当。仮に PLAN 01 が race 単位 obs_id (field-level par) を
   採用していた場合は scale 不一致で加算が不正確化するため・PLAN 01 の CYCLE-3 MEDIUM #2
   設計選択 (horse-level par) が本特徴量の前提・test で両項の scale が一致することを検証。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.availability import CUTOFF_SEMANTICS

# ---------------------------------------------------------------------------
# HIGH #2 / SC#2: cutoff semantics 不変量の実行時参照 (strict_less_than / Asia/Tokyo)。
# FEAT-03 は target-only で PIT は更に厳格 (feature_cutoff_datetime 時点で確定した
# rolling_speed_figure_mean_5 等のみを母集団とする・当日結果不使用)。
# ---------------------------------------------------------------------------
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"

# ---------------------------------------------------------------------------
# D-07: rank 算出に用いる speed_index 3軸。
# 各 axis が1つの rank 列を生成 (canonical は mean_5・D-08 gap 主軸・D-11 additive score 主軸)。
# ---------------------------------------------------------------------------
_SPEED_INDEX_AXES_FOR_RANK: tuple[str, ...] = (
    "rolling_speed_figure_mean_5",        # canonical・D-08 gap 主軸・D-11 additive score 主軸
    "rolling_speed_figure_best2_mean_5",  # 潜在能力の尖り
    "rolling_speed_figure_median_5",      # 外れ値頑健
)

# axis 列名から rank 列名の suffix を機械導出する mapping。
# rolling_speed_figure_mean_5     → mean5
# rolling_speed_figure_best2_mean_5 → best2_mean5
# rolling_speed_figure_median_5     → median5
_AXIS_TO_RANK_SUFFIX: dict[str, str] = {
    "rolling_speed_figure_mean_5": "mean5",
    "rolling_speed_figure_best2_mean_5": "best2_mean5",
    "rolling_speed_figure_median_5": "median5",
}

# ---------------------------------------------------------------------------
# D-12: additive score 係数（§11.2 聖域・事前登録公開定数）。
# 0.0 は baseline (raw mean_5 rank と同値)・候補は train/calib 窓内のみ感度分析 (W-2)。
# feature_matrix に出力するのは coef=0.25 canonical の rank のみ。
# ---------------------------------------------------------------------------
ADJUSTED_RANK_COEF_CANDIDATES: tuple[float, ...] = (0.0, 0.1, 0.25, 0.5)
ADJUSTED_RANK_COEF_CANONICAL: float = 0.25


def _competition_rank_desc_within_race(s: pd.Series) -> pd.Series:
    """competition ranking（min rank・同着同順位・"1224" 方式・D-10）.

    降順（速いほど上位）・rank 1 から開始・同着は同じ rank・次は同着数だけ飛ぶ。

    例: values [100, 95, 95, 90] desc → ranks [1, 2, 2, 4]
        （dense でなく min rank・"1224" 方式・competition ranking 標準挙動）

    D-09: 欠損馬は NaN のまま (na_option="keep"・母集団から除外・最下位固定しない・
    sentinel 数値は使わない)。

    Parameters
    ----------
    s : pd.Series
        rank 化対象の数値 Series（race_id 内の各馬の speed_index 等）。

    Returns
    -------
    pd.Series
        降順 competition ranking の Series（欠損は NaN のまま）。
    """
    return s.rank(method="min", ascending=False, na_option="keep")


def _adjusted_score(
    mean5: pd.Series, fs_mean5: pd.Series, coef: float
) -> pd.Series:
    """D-11: additive score = mean5 + coef * field_strength_mean_mean_5（正の補正）.

    差/比は不採用（強い相手と走ってきた馬を不当に下げるため）。

    CYCLE-3 MEDIUM #2 (10-REVIEWS.md L222・par-scale 兼容性):
        加算の前提として mean5 (rolling_speed_figure_mean_5) と fs_mean5
        (rolling_field_strength_mean_mean_5) が同一 horse-level par normalization 上にある
        こと。PLAN 01 が obs_id を SOURCE_ASOF_<race_nkey>_<kettonum> として target 経路と
        揃えたため・両者は同 scale (speed_figure 単位) で加算が意味的に妥当。仮に PLAN 01 が
        race 単位 obs_id (field-level par) を採用していた場合は scale 不一致で加算が不正確化。

    Parameters
    ----------
    mean5 : pd.Series
        rolling_speed_figure_mean_5 (target 経路・horse-level par 由来)。
    fs_mean5 : pd.Series
        rolling_field_strength_mean_mean_5 (PLAN 01 source-asof 経路・同一 horse-level par)。
    coef : float
        additive score 係数（0.0 は baseline・0.25 は canonical・候補 {0.0,0.1,0.25,0.5}）。

    Returns
    -------
    pd.Series
        mean5 + coef * fs_mean5。
    """
    return mean5 + coef * fs_mean5


def _gap_to_top_within_race(mean5: pd.Series) -> pd.Series:
    """D-08 gap_to_top: race_id 内の1位 (top・max) の mean_5 − self.mean_5.

    competition ranking で順位確定後の1位馬の mean_5 を使う（同着1位の場合は同値なので
    単純に max で良い）。

    Parameters
    ----------
    mean5 : pd.Series
        race_id group 内の rolling_speed_figure_mean_5。

    Returns
    -------
    pd.Series
        top(1位).mean5 − self.mean5（race_id group 内）。
    """
    top_val = mean5.max()
    return top_val - mean5


def _gap_to_3rd_within_race(mean5: pd.Series) -> pd.Series:
    """D-08 gap_to_3rd: competition ranking で rank==3 の馬の mean_5 − self.mean_5.

    REVIEW MEDIUM-7 tie 仕様（10-REVIEWS.md L201, L226）:
        gap_to_3rd は「competition ranking で rank==3 である馬の mean_5 − self.mean_5」と定義する
        （rank 値が 3 の馬・3番目のソート済み non-null 値でない）。
        [100, 95, 95, 90] の場合 competition rank は [1, 2, 2, 4] となり rank==3 の馬は存在しないため・
        gap_to_3rd は race 内の全馬で NaN となる（同着2位がいる場合 rank 3 は空位・
        これが competition ranking の min rank 方式の挙動）。
        tie が無い [100, 95, 90, 85] → rank [1, 2, 3, 4] の場合は rank==3 の馬 (95) が存在し
        gap_to_3rd が算出される。

    出走馬 < 3 の場合も NaN（rank==3 が存在しないため上記と同値）。
    欠損馬（D-09）は母集団除外・自身の gap も NaN。

    Parameters
    ----------
    mean5 : pd.Series
        race_id group 内の rolling_speed_figure_mean_5。

    Returns
    -------
    pd.Series
        rank==3 の馬の mean_5 − self.mean_5（rank==3 が存在しない場合は race 内全馬 NaN）。
    """
    # competition ranking を算出（rank==3 の馬を特定するため）
    ranks = mean5.rank(method="min", ascending=False, na_option="keep")
    # rank==3 の馬が存在するか確認・存在すればその馬の mean_5 を使う
    third_mask = ranks == 3
    if not third_mask.any():
        # rank==3 が空位（同着等で飛んでいる）場合は race 内全馬 NaN
        return pd.Series([np.nan] * len(mean5), index=mean5.index)
    third_val = mean5[third_mask].iloc[0]
    return third_val - mean5


def compute_race_relative_features(feature_matrix: pd.DataFrame) -> pd.DataFrame:
    """FEAT-03: target observation のみ・race_id (race_nkey) group-by で rank/gap/adjusted_rank を算出.

    D-07: target observation のみ（過去走には適用しない・feature_matrix 上で計算・Pitfall 4 回避）。
    D-09: speed_index 欠損馬は NaN 保持・母集団から除外（na_option="keep"・最下位固定しない）。
    D-10: 同着は competition ranking（min rank・"1224" 方式）で同順位・次は同着数だけ飛ぶ。
    D-08: gap_to_top = top(1位).mean5 − self.mean5・gap_to_3rd = 3位.mean5 − self.mean5
          （REVIEW MEDIUM-7 tie 仕様：rank==3 が空位の場合は race 内全馬 NaN）。
    D-11/D-12: field_strength_adjusted_rank は (mean5 + 0.25 * fs_mean5) の race_id 内 rank・
               係数 0.25 は事前登録 canonical・候補 {0.0,0.1,0.25,0.5} は train/calib 窓内のみ
               感度分析で使用（W-2 diagnostic・§11.2 聖域・test 窓選び直し禁止）。

    copy-not-rename（HIGH #5）: 入力 feature_matrix を破壊せず・copy に 6 列を追加。

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        target observation の feature_matrix。必須列:
        - race_nkey
        - rolling_speed_figure_mean_5
        - rolling_speed_figure_best2_mean_5
        - rolling_speed_figure_median_5
        - rolling_field_strength_mean_mean_5

    Returns
    -------
    pd.DataFrame
        入力 copy に 6 列を追加:
        - speed_index_rank_mean5 / speed_index_rank_best2_mean5 / speed_index_rank_median5
        - gap_to_top
        - gap_to_3rd
        - field_strength_adjusted_rank

    Raises
    ------
    ValueError
        必須列が欠損した場合。
    """
    # --- 入力検証（fail-loud）---
    required_cols = (
        "race_nkey",
        *_SPEED_INDEX_AXES_FOR_RANK,
        "rolling_field_strength_mean_mean_5",
    )
    missing = [c for c in required_cols if c not in feature_matrix.columns]
    if missing:
        raise ValueError(
            f"compute_race_relative_features: 必須列が欠損: {missing} "
            f"(FEAT-03 race_relative・D-07/D-08/D-11)"
        )

    # --- copy-not-rename (HIGH #5) ---
    result = feature_matrix.copy()

    # --- numeric 強制 cast (Rule 1 auto-fix・PLAN 04 統合時発覚) ---
    # rolling_speed_figure_mean_5 / best2_mean_5 / median_5 / rolling_field_strength_mean_mean_5 は
    # E2E builder で object dtype（MISSING sentinel 文字列 __MISSING__ 含む）で渡ってくる場合がある。
    # 数値演算 (gap = top_val - mean5 等) が object で文字列引き算 TypeError になるため・
    # 入力を pd.to_numeric(errors="coerce") で通常の float64 に変換する（sentinel 文字列は np.nan・
    # D-09 欠損馬 NaN 保持と整合・PLAN 03 既存テスト契約の np.isnan 互換性を維持）。
    # 最終的な Parquet 出力時の nullable Float64 化は builder Step 6c 側で実施（PAT§ snapshot.py
    # L343-361・rank/gap 列の nullable 扱いは builder の責務）。
    for axis_col in (*_SPEED_INDEX_AXES_FOR_RANK, "rolling_field_strength_mean_mean_5"):
        if axis_col in result.columns:
            result[axis_col] = pd.to_numeric(result[axis_col], errors="coerce")

    # --- D-07 rank 3軸: race_id group-by + transform ---
    for axis_col in _SPEED_INDEX_AXES_FOR_RANK:
        rank_suffix = _AXIS_TO_RANK_SUFFIX[axis_col]
        rank_col = f"speed_index_rank_{rank_suffix}"
        result[rank_col] = result.groupby("race_nkey", sort=False)[axis_col].transform(
            _competition_rank_desc_within_race
        )

    # --- D-08 gap_to_top / gap_to_3rd: race_id group-by + transform ---
    # mean_5 主軸 (Open Question #2 解決)
    grouped_mean5 = result.groupby("race_nkey", sort=False)["rolling_speed_figure_mean_5"]
    result["gap_to_top"] = grouped_mean5.transform(_gap_to_top_within_race)
    result["gap_to_3rd"] = grouped_mean5.transform(_gap_to_3rd_within_race)

    # --- D-11/D-12 field_strength_adjusted_rank: coef=0.25 canonical ---
    # 候補別 score は内部計算用の一時列（coef=0.0/0.1/0.5）・feature_matrix に出力しない
    # （test 窓すり替え防止・D-12・§11.2 聖域）。W-5 で戻り値 columns に残存しないことを機械保証。
    adjusted_score_canonical = _adjusted_score(
        result["rolling_speed_figure_mean_5"],
        result["rolling_field_strength_mean_mean_5"],
        ADJUSTED_RANK_COEF_CANONICAL,
    )
    # 一時列に score を格納し rank を算出後・必ず drop する（W-5・§11.2 聖域保護）
    _TEMP_SCORE_COL = "_rr_adjusted_score_canonical"
    result[_TEMP_SCORE_COL] = adjusted_score_canonical
    try:
        result["field_strength_adjusted_rank"] = result.groupby(
            "race_nkey", sort=False
        )[_TEMP_SCORE_COL].transform(_competition_rank_desc_within_race)
    finally:
        # W-5: 一時列の確実な drop（うっかり残ると候補別 rank が feature として漏出し
        # §11.2 聖域 test 窓すり替え を破るため・try/finally で確実に削除）
        if _TEMP_SCORE_COL in result.columns:
            result.drop(columns=[_TEMP_SCORE_COL], inplace=True)

    return result


def compute_candidate_score_diagnostics(
    feature_matrix: pd.DataFrame,
    split_mask: pd.Series | np.ndarray | None = None,
) -> dict:
    """W-2: additive score 係数候補 {0.0,0.1,0.25,0.5} の分布統計を返す（係数妥当性証跡）.

    目的: additive score 係数 (0.25 canonical) の妥当性を train/calib 窓内で事前登録候補集合
    {0.0, 0.1, 0.25, 0.5} に対して感度証跡を残すこと。

    §11.2 聖域保護:
        test 窓の rank すり替え目的ではない・候補選定は train/calib 窓内のみ。
        本関数は呼出側が split_mask で制御した行集合の統計のみを返す。
        feature_matrix に列を追加しない（copy のみ・戻り値は純粋な dict）。
        PLAN 06 run_phase10_evaluation.py が本関数を消費し train/calib 窓の分布を log 出力する。

    0.0 は baseline（raw mean5 rank と同値）。

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        target observation の feature_matrix。必須列:
        - race_nkey
        - rolling_speed_figure_mean_5
        - rolling_field_strength_mean_mean_5
    split_mask : pd.Series | np.ndarray | None
        行抽出 mask (train 窓=True / calib 窓=True 等の boolean Series・race_id 単位)。
        None の場合は全行を対象。

    Returns
    -------
    dict
        ``{coef: {mean, std, min, max, p10, p50, p90, adjusted_rank_mean, adjusted_rank_std}}``
        各 coef 0.0/0.1/0.25/0.5 について・race_id group の rank 分布統計を含む。
        0.0 の adjusted_rank_mean は raw mean5 rank の分布統計と一致 (baseline)。

    Raises
    ------
    ValueError
        必須列が欠損した場合。
    """
    # --- 入力検証（fail-loud）---
    required_cols = (
        "race_nkey",
        "rolling_speed_figure_mean_5",
        "rolling_field_strength_mean_mean_5",
    )
    missing = [c for c in required_cols if c not in feature_matrix.columns]
    if missing:
        raise ValueError(
            f"compute_candidate_score_diagnostics: 必須列が欠損: {missing} "
            f"(W-2 diagnostic・FEAT-03 race_relative)"
        )

    # --- 行抽出（copy 使用・feature_matrix を破壊しない）---
    if split_mask is None:
        subset = feature_matrix.copy()
    else:
        subset = feature_matrix[split_mask].copy()

    # rank 計算用の score を候補毎に算出（feature_matrix には追加しない・subset のみ）
    n = len(subset)
    empty_stats = {
        "mean": float("nan"),
        "std": float("nan"),
        "min": float("nan"),
        "max": float("nan"),
        "p10": float("nan"),
        "p50": float("nan"),
        "p90": float("nan"),
        "adjusted_rank_mean": float("nan"),
        "adjusted_rank_std": float("nan"),
    }
    if n == 0:
        return {coef: dict(empty_stats) for coef in ADJUSTED_RANK_COEF_CANDIDATES}

    diagnostics: dict[float, dict[str, float]] = {}
    for coef in ADJUSTED_RANK_COEF_CANDIDATES:
        score = _adjusted_score(
            subset["rolling_speed_figure_mean_5"],
            subset["rolling_field_strength_mean_mean_5"],
            coef,
        )
        # race_id group で competition ranking
        rank = subset.groupby("race_nkey", sort=False)["rolling_speed_figure_mean_5"].transform(
            _competition_rank_desc_within_race
        ) if coef == 0.0 else score.groupby(subset["race_nkey"], sort=False).transform(
            _competition_rank_desc_within_race
        )
        diagnostics[coef] = {
            "mean": float(score.mean()) if score.notna().any() else float("nan"),
            "std": float(score.std()) if score.notna().sum() >= 2 else float("nan"),
            "min": float(score.min()) if score.notna().any() else float("nan"),
            "max": float(score.max()) if score.notna().any() else float("nan"),
            "p10": float(score.quantile(0.10)) if score.notna().any() else float("nan"),
            "p50": float(score.quantile(0.50)) if score.notna().any() else float("nan"),
            "p90": float(score.quantile(0.90)) if score.notna().any() else float("nan"),
            "adjusted_rank_mean": float(rank.mean()) if rank.notna().any() else float("nan"),
            "adjusted_rank_std": float(rank.std()) if rank.notna().sum() >= 2 else float("nan"),
        }
    return diagnostics


__all__ = [
    "compute_race_relative_features",
    "compute_candidate_score_diagnostics",
]
