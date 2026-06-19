"""D-05 推定脚質（RED stub・Plan 03-03 が GREEN 化）。

本ファイルは ``src.features.running_style`` が未実装のため RED（Phase 2 RED-集群パターン）。
"""

from __future__ import annotations

import inspect

import pytest


def _get_running_style():
    from src.features import running_style  # Plan 03-03 で実装
    return running_style


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
