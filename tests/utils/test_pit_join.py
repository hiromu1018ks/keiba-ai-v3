"""src/utils/pit_join.py の smoke テスト。

REVIEWS HIGH #1/#3 を直接検証する:
- HIGH #1: sortedness チェックは**呼出元入力（sort 前）**に対して行い、sort 後にチェックしない。
  これを検証するため、未ソート入力で `ValueError` が raise されること、
  かつ `pandas.merge_asof` が呼ばれないことを monkeypatch で確認する。
- HIGH #3: リーク防止ガードは `assert` ではなく `raise ValueError`。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from src.utils import pit_join
from src.utils.pit_join import pit_join_backward

# --- HIGH #1: 呼出元入力（sort 前）の sortedness pre-check raise ---


def test_sortedness_raises_on_unsorted_observations(monkeypatch):
    """未ソート observations で ValueError が raise され、merge_asof は呼ばれない（HIGH #1）。"""
    obs = pd.DataFrame(
        {
            "feature_cutoff_datetime": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
            "horse_id": ["h1", "h1", "h1"],
        }
    )
    hist = pd.DataFrame(
        {"as_of_datetime": pd.to_datetime(["2023-12-31"]), "horse_id": ["h1"], "value": [10]}
    )

    called = {"merge_asof": False}

    def _fake_merge_asof(*args, **kwargs):
        called["merge_asof"] = True
        return pd.DataFrame()

    monkeypatch.setattr(pit_join.pd, "merge_asof", _fake_merge_asof)

    with pytest.raises(ValueError, match="observations must be sorted"):
        pit_join_backward(obs, hist)

    assert not called["merge_asof"], (
        "merge_asof が呼ばれた = sortedness チェックが sort 後に行われた（HIGH #1 違反）"
    )


def test_sortedness_raises_on_unsorted_history(monkeypatch):
    """未ソート history で ValueError が raise され、merge_asof は呼ばれない（HIGH #1）。"""
    obs = pd.DataFrame(
        {
            "feature_cutoff_datetime": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "horse_id": ["h1", "h1"],
        }
    )
    hist = pd.DataFrame(
        {
            "as_of_datetime": pd.to_datetime(["2024-01-05", "2024-01-01"]),
            "horse_id": ["h1", "h1"],
            "value": [99, 10],
        }
    )

    called = {"merge_asof": False}

    def _fake_merge_asof(*args, **kwargs):
        called["merge_asof"] = True
        return pd.DataFrame()

    monkeypatch.setattr(pit_join.pd, "merge_asof", _fake_merge_asof)

    with pytest.raises(ValueError, match="history must be sorted"):
        pit_join_backward(obs, hist)

    assert not called["merge_asof"]


def test_no_silent_resort_implementation_guard():
    """リグレッションガード: is_monotonic_increasing チェックが sort_values より前（HIGH #1）。

    pit_join_backward のソースを取得し、最初の `is_monotonic_increasing` の出現オフセットが
    最初の `sort_values(` の出現オフセットより前であることを検証する。
    sort_values を先に呼んでからチェックする実装に戻った場合、このテストが FAIL する。
    """
    src = inspect.getsource(pit_join_backward)
    mono_idx = src.find("is_monotonic_increasing")
    sort_idx = src.find("sort_values(")

    assert mono_idx != -1, "is_monotonic_increasing チェックが存在しない"
    if sort_idx != -1:
        assert mono_idx < sort_idx, (
            "is_monotonic_increasing のチェックが sort_values より後に出現する（HIGH #1 違反）。"
            " sort 後にチェックすると未ソート入力が黙って通ってしまう。"
        )


# --- リーク防止本体: backward join で未来情報が cutoff を跨がない ---


def test_backward_join_no_future_leak():
    """observations=[t=10] に history=[{t=5,A},{t=15,B}] を backward join → v=A が付与される。"""
    obs = pd.DataFrame(
        {"feature_cutoff_datetime": pd.to_datetime(["2024-01-10"]), "horse_id": ["h1"]}
    )
    hist = pd.DataFrame(
        {
            "as_of_datetime": pd.to_datetime(["2024-01-05", "2024-01-15"]),
            "horse_id": ["h1", "h1"],
            "value": ["A", "B"],
        }
    )

    out = pit_join_backward(obs, hist)

    assert len(out) == 1
    assert out.iloc[0]["value"] == "A", (
        "未来の history 値（t=15, v=B）が cutoff(t=10) を越えて付与された = リーク"
    )


def test_by_group():
    """by=['horse_id'] で馬ごとに独立に過去値が join される。"""
    obs = pd.DataFrame(
        {
            "feature_cutoff_datetime": pd.to_datetime(["2024-01-10", "2024-01-10"]),
            "horse_id": ["h1", "h2"],
        }
    ).sort_values(["horse_id", "feature_cutoff_datetime"])
    hist = pd.DataFrame(
        {
            "as_of_datetime": pd.to_datetime(["2024-01-05", "2024-01-05"]),
            "horse_id": ["h1", "h2"],
            "value": ["A1", "A2"],
        }
    ).sort_values(["horse_id", "as_of_datetime"])

    out = pit_join_backward(obs, hist, by="horse_id")
    out = out.sort_values("horse_id").reset_index(drop=True)

    assert list(out["horse_id"]) == ["h1", "h2"]
    assert list(out["value"]) == ["A1", "A2"]


def test_tolerance_applied():
    """tolerance を超える履歴は付与されない（NaT/NaN 相当）。"""
    obs = pd.DataFrame(
        {"feature_cutoff_datetime": pd.to_datetime(["2024-01-10"]), "horse_id": ["h1"]}
    )
    hist = pd.DataFrame(
        {
            "as_of_datetime": pd.to_datetime(["2023-12-01"]),  # 40日前
            "horse_id": ["h1"],
            "value": ["OLD"],
        }
    )

    out = pit_join_backward(obs, hist, tolerance=pd.Timedelta(days=7))
    assert pd.isna(out.iloc[0]["value"]), "tolerance(7日)超の履歴は付与されないはず"


# --- HIGH #3 リグレッションガード: assert を使わない ---


def test_pit_join_no_assert_statement():
    """ソースに `assert ` 文が含まれない（HIGH #3）。"""
    src = inspect.getsource(pit_join_backward)
    # 行頭の assert 文を検出
    lines = [ln for ln in src.splitlines() if ln.lstrip().startswith("assert ")]
    assert lines == [], f"pit_join_backward に assert 文が含まれる（HIGH #3 違反）: {lines}"


# --- CR-07: global sortedness is load-bearing; per-group sorted ≠ global sorted ---


def test_globally_unsorted_but_per_group_sorted_raises():
    """CR-07 regression: per-group-sorted-but-globally-unsorted observations は拒否。

    従来は ``_validate_by_group_sorted`` が redundant に per-group sortedness を検査していたが、
    docstring が "merge_asof の by= はグループ内ソートを要求" と誤説明しており、未来の
    maintainer が global check を削除して silent leak を導入するリスクがあった。

    このテストは h1=[Jan2, Jan3] と h2=[Jan1] は各グループ内でソート済みだが、
    global には [Jan2, Jan1, Jan3] で non-monotonic な frame を構築し、global check
    （``is_monotonic_increasing``）が raise することを検証する。global check が削除
    されるとこのテストが FAIL する。
    """
    obs = pd.DataFrame(
        {
            # global: [Jan2, Jan1, Jan3] → non-monotonic
            # per-group(h1): [Jan2, Jan3] → monotonic
            # per-group(h2): [Jan1] → monotonic (singleton)
            "feature_cutoff_datetime": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-03"]),
            "horse_id": ["h1", "h2", "h1"],
        }
    )
    hist = pd.DataFrame(
        {
            "as_of_datetime": pd.to_datetime(["2024-01-01"]),
            "horse_id": ["h1"],
            "value": ["A"],
        }
    )

    with pytest.raises(ValueError, match="observations must be sorted"):
        pit_join_backward(obs, hist, by="horse_id")


def test_pit_join_no_redundant_per_group_check():
    """CR-07: ``_validate_by_group_sorted`` は削除され、global check のみが残る。

    リグレッションガード: 誤った docstring「merge_asof の by= はグループ内ソートを要求」
    を将来再導入しないよう、ソースに per-group 検査関数が存在しないことを検証。
    """
    src = inspect.getsource(pit_join)
    assert "_validate_by_group_sorted" not in src, (
        "CR-07: redundant な per-group check は削除されるべき（global check が負担契約）"
    )
    # global sortedness が負担契約である旨が docstring に明記されている
    assert "global" in src.lower(), (
        "CR-07: global sortedness が merge_asof の負担契約である旨を docstring に明記すべき"
    )
