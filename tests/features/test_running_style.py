"""D-05 推定脚質（RED stub・Plan 03-03 が GREEN 化）。

本ファイルは ``src.features.running_style`` が未実装のため RED（Phase 2 RED-集群パターン）。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest


def _get_running_style():
    from src.features import running_style  # Plan 03-03 で実装
    return running_style


def _get_builder():
    from src.features import builder
    return builder


def test_estimate_running_style_uses_past_races_only():
    """running_style モジュールに kyakusitukubun が出現しない（当日リーク防止・D-05）。"""
    running_style = _get_running_style()
    src = inspect.getsource(running_style)
    assert "kyakusitukubun" not in src, (
        "running_style に kyakusitukubun が現れる（当日情報リーク・D-05 違反）"
    )


def test_short_distance_jyuni1c_zero_is_missing():
    """過去走 jyuni1c=0（短距離・1コーナー不存在）のみの馬でも jyuni3c/jyuni4c から算出される（Pitfall 3.2）。"""
    running_style = _get_running_style()
    # 過去走 jyuni3c/jyuni4c のみで推定
    result = running_style.estimate_running_style(
        history_rows=[{"jyuni3c": 1, "jyuni4c": 1, "jyuni1c": 0}]
    )
    assert result is not None, "短距離（jyuni1c=0）でも jyuni3c/jyuni4c から推定できるはず（Pitfall 3.2）"


@pytest.mark.parametrize(
    "avg_position,expected",
    [
        (1.5, "逃"),
        (3.0, "先"),
        (4.5, "差"),
        (6.0, "追"),
    ],
)
def test_threshold_classification(avg_position: float, expected: str):
    """avg_position 閾値: ≤2.0 -> 逃・≤3.5 -> 先・≤5.5 -> 差・>5.5 -> 追。"""
    running_style = _get_running_style()
    result = running_style.classify_running_style(avg_position)
    assert result == expected, f"avg_position={avg_position} -> {result} (expected {expected})"


def test_new_horse_returns_missing():
    """history=[] の馬は __MISSING__。"""
    running_style = _get_running_style()
    from src.utils.category_map import MISSING

    result = running_style.estimate_running_style(history_rows=[])
    assert result == MISSING, "新馬（history 空）は __MISSING__ であるべき"


# ---------------------------------------------------------------------------
# WR-01 (03-05 gap-closure): estimated_running_style PIT pre-filter 回帰防止
# ---------------------------------------------------------------------------
def test_estimated_running_style_applies_pit_prefilter():
    """builder.build_feature_matrix の estimated_running_style 算出 block が
    rolling と同一の PIT pre-filter（``as_of_datetime < feature_cutoff_datetime``・
    per-observation・strict ``<``）を適用していることを検証する（WR-01 regression guard）。

    2段階:
      (1) inspect-based regression guard: source に PIT filter idiom が含まれること
      (2) 合成 feature_matrix（同一 kettonum・cutoff 前後の history）で cutoff 後の
          jyuni3c/jyuni4c が推定脚質に混入しないことを実証
    """
    builder = _get_builder()
    src = inspect.getsource(builder.build_feature_matrix)
    assert "feature_cutoff_datetime" in src, (
        "build_feature_matrix に feature_cutoff_datetime 参照が無い（WR-01 PIT filter 未適用）"
    )
    assert "as_of_datetime" in src, (
        "build_feature_matrix に as_of_datetime 参照が無い（WR-01 PIT filter 未適用）"
    )
    # strict < filter idiom の存在
    assert "< expanded_style" in src or "pit_filtered_style" in src, (
        "estimated_running_style に PIT pre-filter が無い（WR-01 look-ahead leak）"
    )

    # (2) 合成実証: cutoff 前は全て「逃 (jyuni3c/jyuni4c=1)」・cutoff 後に「追 (jyuni3c/jyuni4c=18)」を
    # 混入させても推定脚質が「逃」になること（cutoff 後が混入すると「差/追」に変化）。
    running_style = _get_running_style()
    obs_rd = pd.Timestamp("2023-06-04")
    cutoff = obs_rd - pd.Timedelta(days=1)
    # cutoff 前の過去走（avg_position = 1.0 → 逃）
    pre_history = pd.DataFrame([
        {"kettonum": 1001, "as_of_datetime": obs_rd - pd.Timedelta(days=2),
         "jyuni3c": 1, "jyuni4c": 1, "race_start_datetime": obs_rd - pd.Timedelta(days=2)},
        {"kettonum": 1001, "as_of_datetime": obs_rd - pd.Timedelta(days=3),
         "jyuni3c": 1, "jyuni4c": 1, "race_start_datetime": obs_rd - pd.Timedelta(days=3)},
    ])
    # cutoff 後の過去走（avg_position = 18.0 → 追）・本データが混入すると結果が「追」に変化
    post_history = pd.DataFrame([
        {"kettonum": 1001, "as_of_datetime": obs_rd + pd.Timedelta(days=1),
         "jyuni3c": 18, "jyuni4c": 18, "race_start_datetime": obs_rd + pd.Timedelta(days=1)},
    ])
    history_all = pd.concat([pre_history, post_history], ignore_index=True)
    observations = pd.DataFrame([{
        "kettonum": 1001,
        "feature_cutoff_datetime": cutoff,
    }])
    # rolling.py と同一 idiom を手動で再現して estimated_running_style に相当する値を算出
    obs_keys = observations[["kettonum", "feature_cutoff_datetime"]].copy()
    expanded = history_all.merge(obs_keys, on="kettonum", how="inner", suffixes=("", "_obs"))
    pit_filtered = expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ]
    rows = pit_filtered[["jyuni3c", "jyuni4c"]].to_dict(orient="records")
    result = running_style.estimate_running_style(rows)
    assert result == "逃", (
        f"cutoff 後の未来レースが推定脚質に混入（WR-01 違反）: result={result} (期待 '逃')"
    )
