"""src/utils/group_split.py の smoke テスト。

REVIEWS HIGH #2/#3 を直接検証する:
- HIGH #2: 各 fold で max(train_time) < min(test_time) を strict `<` で強制し、
  等値タイムスタンプの跨ぎを許さない。
- HIGH #3: リーク防止ガードは `assert` ではなく `raise ValueError`。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from src.utils import group_split
from src.utils.group_split import race_id_time_series_split


def _make_races(n: int = 100, start: str = "2023-01-01") -> pd.DataFrame:
    """n 件のユニーク race_id を1日間隔で生成。"""
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame(
        {
            "race_id": [f"R{i:04d}" for i in range(n)],
            "race_start_datetime": dates,
        }
    )


# --- HIGH #2 通常系: race_id disjoint + 厳格時系列順序 ---


def test_race_id_disjoint_raises():
    """各 fold で train と test の race_id が空集合（正常系）。"""
    races = _make_races(100)
    folds = list(race_id_time_series_split(races, n_splits=5))
    assert len(folds) == 5
    for k, (train_rids, test_rids) in enumerate(folds, start=1):
        assert set(train_rids).isdisjoint(set(test_rids)), f"fold {k}: race_id が disjoint でない"
        assert len(train_rids) > 0 and len(test_rids) > 0, f"fold {k}: 空"


def test_strict_chronological_per_fold():
    """各 fold で max(train_time) < min(test_time)（**strict <**・等値不可）。"""
    races = _make_races(100)
    folds = list(race_id_time_series_split(races, n_splits=5))
    for k, (train_rids, test_rids) in enumerate(folds, start=1):
        train_max = races.loc[races.race_id.isin(train_rids), "race_start_datetime"].max()
        test_min = races.loc[races.race_id.isin(test_rids), "race_start_datetime"].min()
        assert train_max < test_min, (
            f"fold {k}: train_max={train_max} >= test_min={test_min}（strict < 違反）"
        )


# --- HIGH #2 直接検証: 等値タイムスタンプの跨ぎを許さない ---


def test_equal_timestamp_races_do_not_cross():
    """同一 race_start_datetime のレースが fold 境界を跨ぐ場合、ValueError を raise（HIGH #2）。

    4レース: R0=2023-01-01, R1=2023-01-02, R2=2023-01-02, R3=2023-01-03
    （R1/R2 は同時刻・競馬場違いを想定）。
    n_splits=2 のとき fold 境界が (R1,R2) の等値ペアに掛かると strict < が成立しなくなる。
    """
    races = pd.DataFrame(
        {
            "race_id": ["R0", "R1", "R2", "R3"],
            "race_start_datetime": pd.to_datetime(
                ["2023-01-01", "2023-01-02", "2023-01-02", "2023-01-03"]
            ),
        }
    )

    # R1 と R2 が同時刻なので、両者が別 fold に分かれる境界では train_max == test_min になる。
    # race_id_time_series_split は [race_start_datetime, race_id] で安定ソートするため
    # unique_races = [R0, R1, R2, R3]。n_splits=2 では:
    #   fold1: train=[R0], test=[R1] → train_max < test_min OK
    #   fold2: train=[R0,R1], test=[R2] → train_max == test_min → strict < 違反 → raise
    with pytest.raises(ValueError, match="chronological boundary violated"):
        list(race_id_time_series_split(races, n_splits=2))


# --- n_splits ---


def test_n_splits():
    """n_splits=3 で3 fold が yield される。"""
    races = _make_races(30)
    folds = list(race_id_time_series_split(races, n_splits=3))
    assert len(folds) == 3


def test_raises_on_n_splits_too_large():
    """n_splits >= n unique races のとき ValueError。"""
    races = _make_races(5)
    with pytest.raises(ValueError, match="n_splits"):
        list(race_id_time_series_split(races, n_splits=5))


def test_raises_on_missing_columns():
    """race_id または race_start_datetime 列が欠損で ValueError。"""
    bad1 = pd.DataFrame({"race_id": ["R0"], "other": [1]})
    bad2 = pd.DataFrame({"race_start_datetime": pd.to_datetime(["2023-01-01"]), "other": [1]})

    with pytest.raises(ValueError, match="race_id"):
        list(race_id_time_series_split(bad1, n_splits=1))
    with pytest.raises(ValueError, match="race_start_datetime"):
        list(race_id_time_series_split(bad2, n_splits=1))


# --- HIGH #3 リグレッションガード: assert を使わない ---


def test_assert_is_replaced_by_raise():
    """race_id_time_series_split のソースに `assert ` 文が含まれない（HIGH #3）。"""
    src = inspect.getsource(race_id_time_series_split)
    lines = [ln for ln in src.splitlines() if ln.lstrip().startswith("assert ")]
    assert lines == [], (
        f"group_split に assert 文が含まれる（HIGH #3 違反・python -O で削除される）: {lines}"
    )


# --- mlxtend fallback API の言及（副 API） ---


def test_mlxtend_group_time_series_split_exposed():
    """mlxtend.evaluate.GroupTimeSeriesSplit が副 API として import 可能（docstring 言及）。"""
    # 副 API がモジュールトップに露出しているか（re-export または docstring 言及）
    module_src = inspect.getsource(group_split)
    assert "GroupTimeSeriesSplit" in module_src, (
        "GroupTimeSeriesSplit が副 API として言及されていない（D-17・BT-1..BT-5 fallback）"
    )
