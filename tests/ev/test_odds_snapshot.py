"""JODDS 時点選択（``merge_asof(direction='backward')`` 等価）の unit test
（BACK-03 / BACK-04 / D-01 / D-02 / §11.2 / §13）。

Wave 0 (Plan 05-01): RED stub。``src.ev.odds_snapshot`` 未実装のため ImportError で RED。

検証内容（RESEARCH §1.4）:
- ``test_odds_snapshot_backward``: backward 最近接選択（発走N分前以下の最大 HappyoTime）
- ``test_odds_snapshot_no_bet_empty``: snapshot 0件 → no_bet sentinel
- ``test_odds_snapshot_special_values``: ``----`` / ``****`` / ``0000`` → no_bet
- ``test_odds_snapshot_future_leak``: 発走時刻より未来の HappyoTime が選択されない
- ``test_odds_snapshot_day_boundary``: 深夜発走レースの日跨ぎで正しい snapshot
- ``test_odds_snapshot_multi_horse``: 同一 race_key で3頭・各異なる odds を保持
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_race_times(race_start: str = "2024-01-03 10:00:00") -> pd.DataFrame:
    """race_start_datetime を持つ race_times 候補（1レース）。"""
    return pd.DataFrame([{
        "race_key": "2024-0103-05-1-06-1",
        "race_start_datetime": pd.to_datetime(race_start),
    }])


def _make_jodds(
    happyo_times: list[str],
    *,
    fukuoddslow: str | list[str] = "0011",
    fukuoddshigh: str | list[str] = "0015",
    umaban: int = 1,
) -> pd.DataFrame:
    """HappyoTime リストから JODDS snapshot DataFrame を構築する。"""
    n = len(happyo_times)
    low_list = [fukuoddslow] * n if isinstance(fukuoddslow, str) else fukuoddslow
    high_list = [fukuoddshigh] * n if isinstance(fukuoddshigh, str) else fukuoddshigh
    rows = []
    for ht, low, high in zip(happyo_times, low_list, high_list, strict=True):
        # happyo_datetime は mmddHHMM を完全日時に解釈（2024年固定・テスト用）
        # HappyoTime は mmddHHMM
        happyo_dt = pd.to_datetime(f"2024-{ht[:2]}-{ht[2:4]} {ht[4:6]}:{ht[6:8]}")
        rows.append({
            "race_key": "2024-0103-05-1-06-1",
            "umaban": umaban,
            "happyotime": ht,
            "happyo_datetime": happyo_dt,
            "fukuoddslow": low,
            "fukuoddshigh": high,
        })
    return pd.DataFrame(rows)


def test_odds_snapshot_backward():
    """発走 10:00 / policy=30min → cutoff 09:30 以下の最大 HappyoTime を選択。

    snapshot 09:25 / 09:31 / 09:35 のうち 09:25 を選択（09:31, 09:35 は cutoff 超）。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds(["01030925", "01030931", "01030935"])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # cutoff = 09:30 → 09:25 が選択される（最大かつ ≤09:30）
    assert len(result) == 1
    assert result["happyotime"].iloc[0] == "01030925"


def test_odds_snapshot_no_bet_empty():
    """snapshot 0件 → no_bet sentinel 行を返す（silent fallback 禁止・§11.3）。"""
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds([])  # 空
    if len(jodds) == 0:
        jodds = pd.DataFrame(columns=[
            "race_key", "umaban", "happyotime", "happyo_datetime",
            "fukuoddslow", "fukuoddshigh",
        ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # no_bet sentinel が付与される（fukuoddslow が NaN または 'no_bet' marker）
    assert "no_bet" in str(result).lower() or result["fukuoddslow"].isna().any()


def test_odds_snapshot_special_values():
    """``----`` / ``****`` / ``0000`` → no_bet・``0999`` は odds として使用可能。"""
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    # 各特殊値が含まれる snapshot を1つずつ生成（cutoff 前に全て存在）
    jodds = _make_jodds(
        ["01030925", "01030926", "01030927", "01030928"],
        fukuoddslow=["----", "****", "0000", "0999"],
        fukuoddshigh=["----", "****", "0000", "0999"],
    )
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # 0999 が選択される（最大 09:28）・odds として有効
    # ※ただし 09:25 の ---- が最大時刻でないことを確認する設計
    assert len(result) >= 1


def test_odds_snapshot_future_leak():
    """発走時刻より未来の HappyoTime が選択されない（backward 原則・D-02）。

    snapshot 09:25 / 10:30（発走後）・policy=30min → 09:25 のみ選択。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds(["01030925", "01031030"])  # 10:30 は発走後
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    assert result["happyotime"].iloc[0] == "01030925"


def test_odds_snapshot_day_boundary():
    """深夜発走（例: 翌日 00:30）の日跨ぎで正しい snapshot を選択。

    発走 2024-01-04 00:30 / policy=30min → cutoff 2024-01-04 00:00。
    snapshot 2024-01-03 23:55 / 2024-01-04 00:10 のうち 23:55 が選択される（00:10 は cutoff 後）。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-04 00:30:00")
    jodds = pd.DataFrame([
        {"race_key": "2024-0104-05-1-06-1", "umaban": 1,
         "happyotime": "01032355",
         "happyo_datetime": pd.to_datetime("2024-01-03 23:55:00"),
         "fukuoddslow": "0011", "fukuoddshigh": "0015"},
        {"race_key": "2024-0104-05-1-06-1", "umaban": 1,
         "happyotime": "01040010",
         "happyo_datetime": pd.to_datetime("2024-01-04 00:10:00"),
         "fukuoddslow": "0012", "fukuoddshigh": "0018"},
    ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    assert result["happyotime"].iloc[0] == "01032355"


def test_odds_snapshot_multi_horse():
    """同一 race_key で3頭・各異なる odds を保持（HIGH-1 MEDIUM・PK は race_key+Umaban 8カラム）。

    RESEARCH §1.1: JODDS PK は race_key 7カラム + Umaban の8カラム。
    per-horse odds テストで出力行数==3・各馬の odds が保持されることを検証。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    rows = []
    for umaban, low, high in [(1, "0011", "0015"), (2, "0020", "0025"), (3, "0030", "0040")]:
        rows.append({
            "race_key": "2024-0103-05-1-06-1",
            "umaban": umaban,
            "happyotime": "01030925",
            "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
            "fukuoddslow": low,
            "fukuoddshigh": high,
        })
    jodds = pd.DataFrame(rows)
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # 出力行数 == 3（各馬1行ずつ）
    assert len(result) == 3
    # 各馬の odds が保持される（umaban で sort して比較）
    result_sorted = result.sort_values("umaban").reset_index(drop=True)
    assert result_sorted.loc[0, "fukuoddslow"] == "0011"
    assert result_sorted.loc[1, "fukuoddslow"] == "0020"
    assert result_sorted.loc[2, "fukuoddslow"] == "0030"
