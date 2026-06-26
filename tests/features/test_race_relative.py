# ruff: noqa: E501  (docstring / 日本語コメント行長は緩和・test_speed_figure.py / test_rolling.py と同一慣例)
"""Phase 10 PLAN 03・FEAT-03 レース内相対特徴量 unit tests.

D-07 target-only / D-09 欠損馬除外 / D-10 competition ranking / D-08 gap (top/3rd) /
D-11/D-12 additive score (0.25 canonical 事前登録・候補 {0.0, 0.1, 0.25, 0.5}) /
W-5 候補別一時列の非残存 / W-2 diagnostic helper を検証する。

RED 前提: src/features/race_relative.py が未実装のため module import が失敗する。
GREEN で compute_race_relative_features / compute_candidate_score_diagnostics /
_competition_rank_desc_within_race / 定数（_SPEED_INDEX_AXES_FOR_RANK /
ADJUSTED_RANK_COEF_CANDIDATES / ADJUSTED_RANK_COEF_CANONICAL）が全て実装される。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# --- ヘルパ: 合成 feature_matrix 構築 ----------------------------------------

def _build_race(
    race_nkey: str,
    rows: list[dict[str, float]],
    extra_cols: bool = True,
) -> pd.DataFrame:
    """1 race 分の target observation feature_matrix を構築。

    Parameters
    ----------
    race_nkey : str
        レース複合キー。
    rows : list[dict]
        各馬の mean5/best2/median5/fs_mean5 値の dict。
    extra_cols : bool
        False の場合 rolling_field_strength_mean_mean_5 列を省く（fail-loud 用）。
    """
    base = pd.DataFrame(rows)
    base["race_nkey"] = race_nkey
    base["kettonum"] = [str(i + 1) for i in range(len(base))]
    if "rolling_field_strength_mean_mean_5" not in base.columns and extra_cols:
        base["rolling_field_strength_mean_mean_5"] = 10.0
    return base


def _two_race_matrix() -> pd.DataFrame:
    """race_id group-by の検証用・2 race の feature_matrix."""
    race_a = _build_race(
        "2024A001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 105.0,
             "rolling_speed_figure_median_5": 99.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 98.0,
             "rolling_speed_figure_median_5": 94.0,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 97.0,
             "rolling_speed_figure_median_5": 93.0,
             "rolling_field_strength_mean_mean_5": 8.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 92.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 7.0},
        ],
    )
    race_b = _build_race(
        "2024A002",
        [
            {"rolling_speed_figure_mean_5": 80.0,
             "rolling_speed_figure_best2_mean_5": 82.0,
             "rolling_speed_figure_median_5": 80.0,
             "rolling_field_strength_mean_mean_5": 5.0},
            {"rolling_speed_figure_mean_5": 75.0,
             "rolling_speed_figure_best2_mean_5": 77.0,
             "rolling_speed_figure_median_5": 75.0,
             "rolling_field_strength_mean_mean_5": 4.0},
        ],
    )
    return pd.concat([race_a, race_b], ignore_index=True)


# === Test 1 (D-10 competition ranking・同着) =================================

def test_competition_ranking_ties_desc():
    """D-10: values [100, 95, 95, 90] desc → ranks [1, 2, 2, 4] (min rank・"1224" 方式).

    dense でなく min rank・同着は同じ rank・次は同着数だけ飛ぶ。
    """
    from src.features.race_relative import _competition_rank_desc_within_race

    s = pd.Series([100.0, 95.0, 95.0, 90.0])
    ranks = _competition_rank_desc_within_race(s).tolist()
    assert ranks == [1.0, 2.0, 2.0, 4.0], f"competition ranking が不正: {ranks}"


def test_competition_ranking_na_option_keep():
    """D-09: 欠損馬は NaN 保持・母集団から除外される (na_option='keep'・最下位固定しない)."""
    from src.features.race_relative import _competition_rank_desc_within_race

    s = pd.Series([100.0, np.nan, 90.0, 80.0])
    ranks = _competition_rank_desc_within_race(s).tolist()
    assert ranks[0] == 1.0
    assert np.isnan(ranks[1]), "欠損は NaN のままであるべき (na_option='keep')"
    assert ranks[2] == 2.0
    assert ranks[3] == 3.0


# === Test 2 (D-07 rank 3軸) ==================================================

def test_speed_index_rank_3axes():
    """D-07: speed_index_rank が mean5 / best2_mean5 / median5 の3軸それぞれで race_id 内 rank.

    列名は speed_index_rank_mean5 / speed_index_rank_best2_mean5 / speed_index_rank_median5。
    """
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix()
    out = compute_race_relative_features(fm)
    for col in (
        "speed_index_rank_mean5",
        "speed_index_rank_best2_mean5",
        "speed_index_rank_median5",
    ):
        assert col in out.columns, f"出力列が存在しない: {col}"
    # race_a の mean5: [100, 95, 95, 90] → rank [1, 2, 2, 4]
    race_a_mask = out["race_nkey"] == "2024A001"
    a_ranks = out.loc[race_a_mask, "speed_index_rank_mean5"].tolist()
    assert a_ranks == [1.0, 2.0, 2.0, 4.0], f"race_a mean5 rank が不正: {a_ranks}"


# === Test 3 (D-09 欠損馬) ====================================================

def test_missing_speed_index_horse_is_nan():
    """D-09: speed_index 欠損馬は rank も NaN・母集団から除外される (na_option='keep')."""
    from src.features.race_relative import compute_race_relative_features

    fm = _build_race(
        "2024B001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": np.nan,
             "rolling_speed_figure_best2_mean_5": np.nan,
             "rolling_speed_figure_median_5": np.nan,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 8.0},
        ],
    )
    out = compute_race_relative_features(fm)
    ranks = out["speed_index_rank_mean5"].tolist()
    assert ranks[0] == 1.0
    assert np.isnan(ranks[1]), "欠損馬は NaN 保持・最下位固定でない"
    assert ranks[2] == 2.0


# === Test 4 (D-08 gap_to_top・Open Question #2) =============================

def test_gap_to_top_mean5():
    """D-08: gap_to_top = top(1位).mean5 - self.mean5・mean_5 主軸."""
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix()
    out = compute_race_relative_features(fm)
    # race_a: mean5 [100, 95, 95, 90] → top=100
    a = out[out["race_nkey"] == "2024A001"].sort_values("kettonum")
    expected_gaps = [0.0, 5.0, 5.0, 10.0]
    actual = a["gap_to_top"].tolist()
    assert actual == pytest.approx(expected_gaps), f"gap_to_top が不正: {actual}"


# === Test 5 (D-08 gap_to_3rd・Open Question #2) =============================

def test_gap_to_3rd_mean5_basic():
    """D-08: gap_to_3rd = 3位.mean5 - self.mean5・同着無し race で算出される.

    race_b: mean5 [80, 75] は size<3 で gap_to_3rd は NaN。
    3位が存在する race_a でも [100, 95, 95, 90] は同着2位で rank==3 が空位 → 全馬 NaN (Test 5b)。
    ここでは同着無し・size>=3 で算出されるケースを検証する。
    """
    from src.features.race_relative import compute_race_relative_features

    fm = _build_race(
        "2024C001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 95.0,
             "rolling_speed_figure_median_5": 95.0,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 8.0},
            {"rolling_speed_figure_mean_5": 85.0,
             "rolling_speed_figure_best2_mean_5": 85.0,
             "rolling_speed_figure_median_5": 85.0,
             "rolling_field_strength_mean_mean_5": 7.0},
        ],
    )
    out = compute_race_relative_features(fm)
    # rank==3 の馬は3番目に速い = mean5=90 (kettonum='3')
    # gap_to_3rd = 90 - self.mean5
    expected = [90 - 100, 90 - 95, 90 - 90, 90 - 85]  # [-10, -5, 0, 5]
    actual = out.sort_values("kettonum")["gap_to_3rd"].tolist()
    assert actual == pytest.approx(expected), f"gap_to_3rd が不正: {actual}"


def test_gap_to_3rd_size_lt_3_is_nan():
    """D-08: 出走馬 < 3 の場合・gap_to_3rd は NaN."""
    from src.features.race_relative import compute_race_relative_features

    fm = _build_race(
        "2024D001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 8.0},
        ],
    )
    out = compute_race_relative_features(fm)
    assert out["gap_to_3rd"].isna().all(), "size<3 では gap_to_3rd は全馬 NaN"


# === Test 5b (REVIEW MEDIUM-7 gap_to_3rd tie 仕様) ==========================

def test_gap_to_3rd_tie_at_2nd_is_nan():
    """REVIEW MEDIUM-7: values=[100, 95, 95, 90] の場合・competition rank [1,2,2,4] で
    rank==3 は空位 → gap_to_3rd は race 内の全馬で NaN.
    tie が無い [100, 95, 90, 85] → rank [1,2,3,4] は rank==3 が存在し算出される。
    """
    from src.features.race_relative import compute_race_relative_features

    # tie ケース
    fm_tie = _build_race(
        "2024E001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 95.0,
             "rolling_speed_figure_median_5": 95.0,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 95.0,
             "rolling_speed_figure_median_5": 95.0,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 7.0},
        ],
    )
    out_tie = compute_race_relative_features(fm_tie)
    assert out_tie["gap_to_3rd"].isna().all(), (
        "同着2位で rank==3 が空位の場合・gap_to_3rd は race 内全馬で NaN であるべき"
    )

    # tie 無し ケース
    fm_no_tie = _build_race(
        "2024E002",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            {"rolling_speed_figure_mean_5": 95.0,
             "rolling_speed_figure_best2_mean_5": 95.0,
             "rolling_speed_figure_median_5": 95.0,
             "rolling_field_strength_mean_mean_5": 9.0},
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 8.0},
            {"rolling_speed_figure_mean_5": 85.0,
             "rolling_speed_figure_best2_mean_5": 85.0,
             "rolling_speed_figure_median_5": 85.0,
             "rolling_field_strength_mean_mean_5": 7.0},
        ],
    )
    out_no_tie = compute_race_relative_features(fm_no_tie)
    assert not out_no_tie["gap_to_3rd"].isna().all(), (
        "tie 無し・size>=3 では rank==3 が存在し gap_to_3rd が算出されるべき"
    )


# === Test 6 (D-11 additive score・D-12 coef) ================================

def test_field_strength_adjusted_rank_canonical():
    """D-11/D-12: field_strength_adjusted_rank は (mean5 + 0.25*fs_mean5) の race_id 内 rank.

    coef=0.25 canonical.
    """
    from src.features.race_relative import (
        ADJUSTED_RANK_COEF_CANONICAL,
        compute_race_relative_features,
    )

    assert ADJUSTED_RANK_COEF_CANONICAL == 0.25

    fm = _build_race(
        "2024F001",
        [
            # mean5=100, fs_mean5=20 → score=100+0.25*20=105 (rank 1)
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 20.0},
            # mean5=98, fs_mean5=0 → score=98 (rank 3)
            {"rolling_speed_figure_mean_5": 98.0,
             "rolling_speed_figure_best2_mean_5": 98.0,
             "rolling_speed_figure_median_5": 98.0,
             "rolling_field_strength_mean_mean_5": 0.0},
            # mean5=98, fs_mean5=10 → score=100.5 (rank 2)
            {"rolling_speed_figure_mean_5": 98.0,
             "rolling_speed_figure_best2_mean_5": 98.0,
             "rolling_speed_figure_median_5": 98.0,
             "rolling_field_strength_mean_mean_5": 10.0},
            # mean5=80, fs_mean5=100 → score=105 (rank 1 tie・同着)
            {"rolling_speed_figure_mean_5": 80.0,
             "rolling_speed_figure_best2_mean_5": 80.0,
             "rolling_speed_figure_median_5": 80.0,
             "rolling_field_strength_mean_mean_5": 100.0},
        ],
    )
    out = compute_race_relative_features(fm)
    ranks = out.sort_values("kettonum")["field_strength_adjusted_rank"].tolist()
    # scores: [105, 98, 100.5, 105] → competition rank desc [1, 4, 3, 1]
    assert ranks == pytest.approx([1.0, 4.0, 3.0, 1.0]), (
        f"field_strength_adjusted_rank (coef=0.25) が不正: {ranks}"
    )


# === Test 6b (CYCLE-3 MEDIUM #2 scale 兼容性・非リーク) =====================

def test_additive_score_same_scale_compatibility():
    """CYCLE-3 MEDIUM #2: mean5 と fs_mean5 が同 horse-level par normalization 上にある前提で
    加算が成立することを検証。両者が同 scale (speed_figure 単位) の場合・adjusted_score が
    race_id 内で意味のある順序付けを与える."""
    from src.features.race_relative import compute_race_relative_features

    fm = _build_race(
        "2024G001",
        [
            {"rolling_speed_figure_mean_5": 100.0,
             "rolling_speed_figure_best2_mean_5": 100.0,
             "rolling_speed_figure_median_5": 100.0,
             "rolling_field_strength_mean_mean_5": 100.0},  # 同 scale
            {"rolling_speed_figure_mean_5": 90.0,
             "rolling_speed_figure_best2_mean_5": 90.0,
             "rolling_speed_figure_median_5": 90.0,
             "rolling_field_strength_mean_mean_5": 90.0},  # 同 scale
        ],
    )
    out = compute_race_relative_features(fm)
    # score = 100+0.25*100=125 / 90+0.25*90=112.5 → rank [1, 2]
    ranks = out.sort_values("kettonum")["field_strength_adjusted_rank"].tolist()
    assert ranks == pytest.approx([1.0, 2.0])


# === Test 7 (D-12 候補集合・§11.2 聖域) =====================================

def test_adjusted_rank_coef_candidates_constant():
    """D-12: ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5)・0.0 は baseline."""
    from src.features.race_relative import (
        ADJUSTED_RANK_COEF_CANDIDATES,
        ADJUSTED_RANK_COEF_CANONICAL,
    )

    assert ADJUSTED_RANK_COEF_CANDIDATES == (0.0, 0.1, 0.25, 0.5)
    assert ADJUSTED_RANK_COEF_CANONICAL in ADJUSTED_RANK_COEF_CANDIDATES
    # 0.0 は baseline (raw mean5 rank と同値)
    assert 0.0 in ADJUSTED_RANK_COEF_CANDIDATES


def test_speed_index_axes_for_rank_constant():
    """D-07: _SPEED_INDEX_AXES_FOR_RANK は3軸 (mean5/best2_mean5/median5)."""
    from src.features.race_relative import _SPEED_INDEX_AXES_FOR_RANK

    assert _SPEED_INDEX_AXES_FOR_RANK == (
        "rolling_speed_figure_mean_5",
        "rolling_speed_figure_best2_mean_5",
        "rolling_speed_figure_median_5",
    )


# === Test 8 (D-07 target-only・過去走誤適用防止) ============================

def test_target_only_no_history_rows():
    """D-07: feature_matrix の行数が target observations 数と一致・過去走 history 行には
    rank/gap が付与されない (Pitfall 4 回避)."""
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix()
    out = compute_race_relative_features(fm)
    assert len(out) == len(fm), "出力行数は入力行数 (target obs のみ) と一致すべき"


# === Test 9 (copy-not-rename・HIGH#5) =======================================

def test_copy_not_rename_input_preserved():
    """HIGH#5: 入力 feature_matrix の既存列は破壊されず・6 列が copy 追加される."""
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix().copy()
    original_cols = list(fm.columns)
    original_vals = fm["rolling_speed_figure_mean_5"].tolist()
    out = compute_race_relative_features(fm)
    # 入力は破壊されない
    assert list(fm.columns) == original_cols
    assert fm["rolling_speed_figure_mean_5"].tolist() == original_vals
    # 6 列追加
    new_cols = [c for c in out.columns if c not in original_cols]
    assert len(new_cols) == 6, f"追加列は6列のはず: {new_cols}"
    expected_new = {
        "speed_index_rank_mean5",
        "speed_index_rank_best2_mean5",
        "speed_index_rank_median5",
        "gap_to_top",
        "gap_to_3rd",
        "field_strength_adjusted_rank",
    }
    assert set(new_cols) == expected_new, f"期待6列でない: {set(new_cols)}"


# === Test 10 (fail-loud) ====================================================

def test_fail_loud_on_missing_required_columns():
    """必須列欠落時に raise ValueError."""
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix()
    # rolling_field_strength_mean_mean_5 を削る
    fm_no_fs = fm.drop(columns=["rolling_field_strength_mean_mean_5"])
    with pytest.raises(ValueError, match=r"race_relative|required|必須"):
        compute_race_relative_features(fm_no_fs)

    # race_nkey を削る
    fm_no_key = fm.drop(columns=["race_nkey"])
    with pytest.raises(ValueError, match=r"race_relative|required|必須"):
        compute_race_relative_features(fm_no_key)


# === Test 11 (W-5 候補別一時列の非残存・§11.2 聖域保護) =====================

def test_no_candidate_score_temp_columns_in_output():
    """W-5: compute_race_relative_features 戻り値の columns に候補別 score の一時列が含まれない.

    うっかり残ると候補別 rank が feature として漏出し §11.2 聖域 (test 窓すり替え) を破る。
    """
    from src.features.race_relative import compute_race_relative_features

    fm = _two_race_matrix()
    out = compute_race_relative_features(fm)
    forbidden_patterns = (
        "coef_0.0", "coef_0.1", "coef_0.5", "coef_0.25",
        "adjusted_score_internal", "_score_internal", "score_internal",
        "adjusted_score_0", "adjusted_score_1", "adjusted_score_2",
    )
    leaked = [c for c in out.columns
              if any(p in c for p in forbidden_patterns)]
    assert not leaked, (
        f"候補別 score の一時列が戻り値に残存: {leaked} (§11.2 聖域違反・W-5)"
    )
    # 出力は6列のみ (Test 9 と重複するが念のため)
    expected_out_features = {
        "speed_index_rank_mean5",
        "speed_index_rank_best2_mean5",
        "speed_index_rank_median5",
        "gap_to_top",
        "gap_to_3rd",
        "field_strength_adjusted_rank",
    }
    added = set(out.columns) - set(fm.columns)
    assert added == expected_out_features, (
        f"追加列は6 feature 候補のみであるべき: {added}"
    )


# === Test 12 (W-2 係数妥当性証跡・diagnostic helper) ========================

def test_compute_candidate_score_diagnostics_returns_dict():
    """W-2: compute_candidate_score_diagnostics が候補 {0.0,0.1,0.25,0.5} の分布統計を返す.

    0.0 の adjusted_rank_mean は raw mean5 rank の分布統計と一致 (baseline・係数0は raw rank と同値)。
    feature_matrix の列は破壊されない (copy 使用)。
    split_mask=None は全行対象。
    """
    from src.features.race_relative import (
        ADJUSTED_RANK_COEF_CANDIDATES,
        compute_candidate_score_diagnostics,
    )

    fm = _two_race_matrix().copy()
    original_cols = list(fm.columns)
    original_vals = fm["rolling_speed_figure_mean_5"].tolist()

    diag = compute_candidate_score_diagnostics(fm, split_mask=None)

    assert isinstance(diag, dict)
    assert set(diag.keys()) == set(ADJUSTED_RANK_COEF_CANDIDATES), (
        f"diag キーは候補集合と一致すべき: {set(diag.keys())}"
    )
    for coef in ADJUSTED_RANK_COEF_CANDIDATES:
        stats = diag[coef]
        for key in ("mean", "std", "min", "max",
                    "p10", "p50", "p90",
                    "adjusted_rank_mean", "adjusted_rank_std"):
            assert key in stats, f"coef={coef} に必須キー {key} が無い: {stats.keys()}"

    # feature_matrix は破壊されない
    assert list(fm.columns) == original_cols
    assert fm["rolling_speed_figure_mean_5"].tolist() == original_vals

    # 0.0 の adjusted_rank_mean は raw mean5 rank の分布統計と一致 (baseline)
    # raw mean5 rank を直接計算して比較
    expected_raw = fm.groupby("race_nkey")["rolling_speed_figure_mean_5"].transform(
        lambda s: s.rank(method="min", ascending=False, na_option="keep")
    )
    expected_raw_mean = float(expected_raw.mean())
    assert diag[0.0]["adjusted_rank_mean"] == pytest.approx(expected_raw_mean, nan_ok=True), (
        f"coef=0.0 の adjusted_rank_mean は raw mean5 rank の平均と一致すべき: "
        f"{diag[0.0]['adjusted_rank_mean']} vs {expected_raw_mean}"
    )


def test_compute_candidate_score_diagnostics_with_split_mask():
    """W-2: split_mask で行抽出した分布を返す・全行と一部で値が変わる."""
    from src.features.race_relative import compute_candidate_score_diagnostics

    fm = _two_race_matrix()
    mask_all = pd.Series([True] * len(fm))
    mask_half = fm["race_nkey"] == "2024A001"

    diag_all = compute_candidate_score_diagnostics(fm, split_mask=mask_all)
    diag_half = compute_candidate_score_diagnostics(fm, split_mask=mask_half)

    # mask_all は None と同値
    diag_none = compute_candidate_score_diagnostics(fm, split_mask=None)
    assert diag_all[0.25]["mean"] == pytest.approx(diag_none[0.25]["mean"])
    # mask で抽出すると値が変わる
    assert diag_half[0.25]["mean"] != pytest.approx(diag_all[0.25]["mean"])
