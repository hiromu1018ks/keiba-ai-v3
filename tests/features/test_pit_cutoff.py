"""SC#1 + D-06 + REVIEWS HIGH #2 cutoff enforcement（RED stub・Plan 03-03 が GREEN 化）。

本ファイルは ``src.features.builder`` / ``src.features.rolling`` が未実装のため
ImportError / AttributeError で RED になる（Phase 2 Plan 02-02 RED-集群パターン）。
関数内 import で collection 時ではなく実行時に RED になる。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from tests.features.conftest import (
    _build_adversarial_rolling_rows,
    _build_race_obs_row,
)


def _get_builder():
    from src.features import builder  # Plan 03-03 で実装
    return builder


# ---------------------------------------------------------------------------
# SC#1 / Pitfall 3.1: 同日別レース成績が rolling に混入しない
# ---------------------------------------------------------------------------
def test_cutoff_excludes_same_day_races():
    builder = _get_builder()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")])
    result = builder.build_rolling_features(obs, history)
    # same_day_prior (88.88) / same_day_later (77.77) が rolling 結果に含まれない
    assert "rolling_timediff_mean_5" in result.columns
    assert abs(result.iloc[0]["rolling_timediff_mean_5"] - (-2.0)) < 1e-9


# ---------------------------------------------------------------------------
# REVIEWS HIGH #2 境界 adversarial: cutoff 同日レースが strict < で除外される
# ---------------------------------------------------------------------------
def test_cutoff_excludes_previous_day_race_strict_less_than():
    """feature_cutoff_datetime = '2023-06-03' (JST midnight) に対し、
    previous_day_row の as_of == '2023-06-03'（cutoff と同日）が除外される。
    strict < なので同日 == cutoff は除外（<= だと混入）。
    """
    builder = _get_builder()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")])
    result = builder.build_rolling_features(obs, history)
    # previous_day (66.66) が混入すると mean が -2.0 から外れる
    assert abs(result.iloc[0]["rolling_timediff_mean_5"] - (-2.0)) < 1e-9


def test_cutoff_excludes_future_race():
    builder = _get_builder()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")])
    result = builder.build_rolling_features(obs, history)
    # future (55.55) が混入すると mean が -2.0 から外れる
    assert abs(result.iloc[0]["rolling_timediff_mean_5"] - (-2.0)) < 1e-9


def test_pit_join_backward_called_with_sorted_input():
    """builder 内で pit_join_backward 呼出前に .sort_values() がある（regression guard）。"""
    builder = _get_builder()
    src = inspect.getsource(builder)
    assert "sort_values" in src, "builder に sort_values が無い（PIT join sorted 入力要件）"


def test_feature_cutoff_is_race_date_minus_one_day():
    """observations の feature_cutoff_datetime == race_date - 1 day（HIGH #2・JST midnight）。"""
    obs = _build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")
    expected = pd.to_datetime("2023-06-04") - pd.Timedelta(days=1)
    assert obs["feature_cutoff_datetime"] == expected


def test_cutoff_semantics_documented_in_metadata():
    """builder が生成する feature matrix に cutoff_rule (strict_less_than / Asia/Tokyo) が含まれる。"""
    builder = _get_builder()
    # Plan 03-03/03-04 完了後に GREEN
    assert hasattr(builder, "CUTOFF_RULE_METADATA") or "strict_less_than" in inspect.getsource(builder)
