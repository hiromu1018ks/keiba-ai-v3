"""``split_3way`` の ``periods`` パラメータ拡張（BT窓再学習用）の unit test
（D-03 / RESEARCH §6.5）。

Wave 0 (Plan 05-01): RED stub。``src.model.data.split_3way`` に ``periods`` パラメータが
未存在のため TypeError で RED。Wave 1/2 plan が ``periods`` を追加して GREEN 化する。

検証内容:
- ``test_split_3way_periods_injection``: ``periods`` 指定で BT窓分割・既存 guard 継承
- ``test_split_3way_backward_compat``: ``periods=None`` で既存ハードコード（Phase 4 回帰防止）
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_feature_frame(n_per_year: int = 100) -> pd.DataFrame:
    """BT窓テスト用の合成 feature DataFrame（race_date 列を持つ）。"""
    dates = pd.date_range("2019-01-01", "2025-12-31", freq="W")
    n = min(n_per_year * 7, len(dates))
    return pd.DataFrame({
        "race_key": [f"RK{i:05d}" for i in range(n)],
        "race_date": dates[:n],
        "year": dates[:n].year,
        "jyocd": "05",
        "kaiji": 1,
        "nichiji": "06",
        "racenum": 1,
        "umaban": [1] * n,
        "kettonum": [100 + i for i in range(n)],
    })


def test_split_3way_periods_injection():
    """``periods`` 指定で BT窓分割・strict chronological + race_key disjoint guard を継承。"""
    from src.model.data import split_3way

    frame = _make_feature_frame()
    periods = {
        "train": ("2019-06-01", "2022-12-31"),
        "calib": ("2022-07-01", "2022-12-31"),
        "test": ("2023-01-01", "2023-12-31"),
    }
    splits = split_3way(frame, periods=periods)
    assert set(splits.keys()) >= {"train", "calib", "test"}
    # BT窓区間で filter されていることを検証
    assert splits["train"]["race_date"].min() >= pd.to_datetime("2019-06-01")
    assert splits["train"]["race_date"].max() <= pd.to_datetime("2022-12-31")
    assert splits["test"]["race_date"].min() >= pd.to_datetime("2023-01-01")
    assert splits["test"]["race_date"].max() <= pd.to_datetime("2023-12-31")
    # race_key disjoint（train と test で共有なし）
    assert set(splits["train"]["race_key"]).isdisjoint(set(splits["test"]["race_key"]))


def test_split_3way_backward_compat():
    """``periods=None`` で既存ハードコード挙動（Phase 4 回帰防止）。

    既存の ``train 2016-07〜2023 / calib 2024-01〜06 / test 2024-07〜12`` 区間が
    適用されることを検証する。``periods`` を渡さない呼び出しと ``periods=None``
    呼び出しは同一結果を返すべき（後方互換）。
    """
    from src.model.data import split_3way

    frame = _make_feature_frame()
    # 既存呼び出し（periods 引数なし）
    splits_legacy = split_3way(frame)
    # periods=None 呼び出し
    splits_none = split_3way(frame, periods=None)
    # train 行数が一致することで後方互換を検証
    assert len(splits_legacy["train"]) == len(splits_none["train"])
    assert len(splits_legacy["calib"]) == len(splits_none["calib"])
    assert len(splits_legacy["test"]) == len(splits_none["test"])
