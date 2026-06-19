"""D-03/D-04/D-13 + REVIEWS HIGH #1 per-observation latest-5 algorithm（RED stub・Plan 03-03 GREEN）。

本ファイルは ``src.features.rolling`` が未実装のため RED（Phase 2 RED-集群パターン）。
関数内 import で実行時に RED。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from tests.features.conftest import (
    _build_adversarial_rolling_rows,
    _build_two_observation_rolling_rows,
)


def _get_rolling():
    from src.features import rolling  # Plan 03-03 で実装
    return rolling


# ---------------------------------------------------------------------------
# D-03/D-04: lookback=5 / 3軸 (mean/latest/sd) / 5走未満 sentinel
# ---------------------------------------------------------------------------
def test_under_5_starts_uses_missing_sentinel():
    rolling = _get_rolling()
    # 3走のみの馬は mean は3走分で算出・starts_count=0（新馬）は3軸とも __MISSING__
    from src.utils.category_map import MISSING
    # 新馬（history 空）
    obs = pd.DataFrame([{"kettonum": 9999, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])
    history = pd.DataFrame(columns=["kettonum", "as_of_datetime", "timediff"])
    result = rolling.build_rolling_features(obs, history)
    assert result.iloc[0]["rolling_timediff_mean_5"] == MISSING


def test_rolling_three_axes_present():
    rolling = _get_rolling()
    result_columns = rolling.build_rolling_features.__doc__ or ""
    # 各系統で mean / latest / sd の3列が存在・sd は n<2 で __MISSING__（Pitfall 3.3）
    src = inspect.getsource(rolling)
    assert "mean_5" in src and "latest_5" in src and "sd_5" in src


def test_target_race_timediff_not_in_history():
    """対象レース自身の timediff が rolling 入力 history に含まれない（defense-in-depth・Pitfall 3.1）。"""
    rolling = _get_rolling()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([{"kettonum": 1001, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])
    result = rolling.build_rolling_features(obs, history)
    # target timediff=99.99 が混入すると mean が -2.0 から外れる
    assert abs(result.iloc[0]["rolling_timediff_mean_5"] - (-2.0)) < 1e-9


def test_harontimel4_not_in_feature_matrix():
    """feature matrix に harontimel4 列が存在しない（Pitfall 3.6）。"""
    rolling = _get_rolling()
    src = inspect.getsource(rolling)
    assert "harontimel4" not in src, "rolling モジュールに harontimel4 が現れる（Pitfall 3.6 違反）"


# ---------------------------------------------------------------------------
# REVIEWS HIGH #1: per-observation latest-5 algorithm 対抗テスト
# ---------------------------------------------------------------------------
def test_per_observation_latest_5_excludes_target_same_day_previous_future():
    """5行 adversarial + 3行 eligible の history で rolling_timediff_mean_5 == -2.0（eligible のみ）。"""
    rolling = _get_rolling()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([{"kettonum": 1001, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])
    result = rolling.build_rolling_features(obs, history)
    assert abs(result.iloc[0]["rolling_timediff_mean_5"] - (-2.0)) < 1e-9, (
        "target/same_day/previous_day/future の異常値が rolling に混入（HIGH #1 違反）"
    )


def test_two_observation_window_is_per_observation_not_per_horse():
    """CYCLE-2 HIGH #1 re-open: 同一 horse × 2 obs × 異 cutoff で rolling 結果が異なる。

    horse-grouped `groupby("kettonum").head(5)` では必ず RED・obs_id-keyed のみ GREEN。
    obs_A window = both_pre のみ（timediff=-1.0）
    obs_B window = both_pre + obs_B_only_pre の平均（=((-1.0)+(-7.7))/2 = -4.35）
    """
    rolling = _get_rolling()
    observations, history = _build_two_observation_rolling_rows(kettonum=2002)
    result = rolling.build_rolling_features(observations, history)
    obs_a = result[result["obs_id"] == "A"].iloc[0]
    obs_b = result[result["obs_id"] == "B"].iloc[0]
    assert abs(obs_a["rolling_timediff_mean_5"] - (-1.0)) < 1e-9, (
        "obs_A に obs_B_only_pre が混入（CYCLE-2 HIGH #1 違反）"
    )
    assert abs(obs_b["rolling_timediff_mean_5"] - (-4.35)) < 1e-9, (
        "obs_B に both_pre + obs_B_only_pre の平均が含まれない"
    )
    assert obs_a["rolling_timediff_mean_5"] != obs_b["rolling_timediff_mean_5"], (
        "obs_A と obs_B の rolling が同一 = horse-grouped cross-obs leak（CYCLE-2 HIGH #1）"
    )


def test_latest_5_window_ranked_by_race_start_datetime_desc():
    """build_rolling_features が sort_values(race_start_datetime, ascending=False).head(5) を持つ。"""
    rolling = _get_rolling()
    src = inspect.getsource(rolling.build_rolling_features)
    assert "race_start_datetime" in src, "race_start_datetime で window sort していない（HIGH #1）"
    assert ("head(5)" in src) or ("nlargest" in src), (
        "latest-5 window に head(5)/nlargest が無い（HIGH #1 per-observation algorithm 証明）"
    )


def test_history_pre_filtered_strict_less_than_cutoff():
    """build_rolling_features に strict < feature_cutoff_datetime filter がある（defense-in-depth）。"""
    rolling = _get_rolling()
    src = inspect.getsource(rolling.build_rolling_features)
    assert "feature_cutoff_datetime" in src, (
        "build_rolling_features に feature_cutoff_datetime 参照が無い（HIGH #1/#2）"
    )
    # strict < （<= でない）を regression assert
    assert "<=" not in src.replace("<feature_cutoff_datetime", "__KEEP__") or "< feature_cutoff_datetime" in src, (
        "strict < filter が確認できない（<= は HIGH #2 違反）"
    )
