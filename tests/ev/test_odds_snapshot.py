"""JODDS 時点選択（``merge_asof(direction='backward')`` 等価）の unit test
（BACK-03 / BACK-04 / D-01 / D-02 / §11.2 / §13）。

Wave 0 (Plan 05-01): RED stub。``src.ev.odds_snapshot`` 未実装のため ImportError で RED。
Plan 05-03 Task 1 で GREEN 化（cycle-2 テスト追加含む）。

検証内容（RESEARCH §1.4 + Plan 05-03 cycle-2）:
- ``test_odds_snapshot_backward``: backward 最近接選択（発走N分前以下の最大 HappyoTime）
- ``test_odds_snapshot_no_bet_empty``: snapshot 0件 → no_bet sentinel
- ``test_odds_snapshot_special_values``: ``----`` / ``****`` / ``0000`` → no_bet
- ``test_odds_snapshot_0999_is_no_bet``: HIGH-3 canonical rule（CONTEXT D-02 正・RESEARCH 行89 廃棄）
- ``test_odds_snapshot_future_leak``: 発走時刻より未来の HappyoTime が選択されない
- ``test_odds_snapshot_day_boundary``: 深夜発走レースの日跨ぎで正しい snapshot
- ``test_odds_snapshot_datakubun_filter``: DataKubun='1'(中間) のみ使用・'3'/'4' は除外（D-01）
- ``test_odds_snapshot_returns_snake_case``: 戻り値列が snake_case fuku_odds_lower/upper
- ``test_odds_snapshot_multi_horse``: 同一 race_key で3頭・各異なる odds を保持（HIGH-1）
- ``test_odds_snapshot_fukusyoflag_normal_sale``: FukusuoFlag='7'(正常発売) で odds を返す
- ``test_odds_snapshot_multi_race``: 複数レース + 重複 happyo_datetime で merge_asof 正常動作
"""

from __future__ import annotations

import pandas as pd


def _make_race_times(race_start: str = "2024-01-03 10:00:00") -> pd.DataFrame:
    """race_start_datetime を持つ race_times 候補（1レース1頭）。

    HIGH-1: ``race_times`` は馬単位（race_key + umaban）で渡す前提。
    select_odds_snapshot の merge_asof ``by=['race_key','umaban']`` が動作するため。
    """
    return pd.DataFrame([{
        "race_key": "2024-0103-05-1-06-1",
        "umaban": 1,
        "race_start_datetime": pd.to_datetime(race_start),
    }])


def _make_jodds(
    happyo_times: list[str],
    *,
    fukuoddslow: str | list[str] = "0011",
    fukuoddshigh: str | list[str] = "0015",
    umaban: int = 1,
    race_key: str = "2024-0103-05-1-06-1",
    fukusyoflag: str | list[str] = "7",
    datakubun: str | list[str] = "1",
) -> pd.DataFrame:
    """HappyoTime リストから JODDS snapshot DataFrame を構築する。

    RESEARCH §1.1: JODDS PK は race_key 7カラム + Umaban + HappyoTime = 8カラム。
    """
    n = len(happyo_times)
    low_list = [fukuoddslow] * n if isinstance(fukuoddslow, str) else fukuoddslow
    high_list = [fukuoddshigh] * n if isinstance(fukuoddshigh, str) else fukuoddshigh
    fsf_list = [fukusyoflag] * n if isinstance(fukusyoflag, str) else fukusyoflag
    dk_list = [datakubun] * n if isinstance(datakubun, str) else datakubun
    rows = []
    for ht, low, high, fsf, dk in zip(
        happyo_times, low_list, high_list, fsf_list, dk_list, strict=True
    ):
        # happyo_datetime は mmddHHMM を完全日時に解釈（2024年固定・テスト用）
        happyo_dt = pd.to_datetime(f"2024-{ht[:2]}-{ht[2:4]} {ht[4:6]}:{ht[6:8]}")
        rows.append({
            "race_key": race_key,
            "umaban": umaban,
            "happyotime": ht,
            "happyo_datetime": happyo_dt,
            "fukuoddslow": low,
            "fukuoddshigh": high,
            "fukusyoflag": fsf,
            "datakubun": dk,
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
    jodds = pd.DataFrame(columns=[
        "race_key", "umaban", "happyotime", "happyo_datetime",
        "fukuoddslow", "fukuoddshigh", "fukusyoflag", "datakubun",
    ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # no_bet sentinel が付与される（odds_missing_reason='no_bet_empty'・fuku_odds_lower は NaN）
    assert "odds_missing_reason" in result.columns
    assert result["odds_missing_reason"].iloc[0] == "no_bet_empty"
    assert pd.isna(result["fuku_odds_lower"].iloc[0])


def test_odds_snapshot_special_values():
    """``----`` / ``****`` / ``0000`` → no_bet（silent fallback 禁止）。

    HIGH-3 canonical rule: これら特殊値は odds 欠損 sentinel 扱い。
    4 snapshot 全て cutoff 前に存在 → 直近（09:28 の '0000'）を選択するが
    odds_missing_reason='no_bet' で sentinel 化され・fuku_odds_lower は NaN。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds(
        ["01030925", "01030926", "01030927", "01030928"],
        fukuoddslow=["----", "****", "0000", "0999"],
        fukuoddshigh=["----", "****", "0000", "0999"],
    )
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # 09:28 (0999) が直近 → HIGH-3 で 0999 も no_bet となるため・
    # 全候補が no_bet sentinel 化される（fuku_odds_lower=NaN, odds_missing_reason='no_bet'）
    assert len(result) == 1
    assert pd.isna(result["fuku_odds_lower"].iloc[0])
    assert result["odds_missing_reason"].iloc[0] == "no_bet"


def test_odds_snapshot_0999_is_no_bet():
    """HIGH-3 canonical: ``0999`` は odds 欠損 sentinel（CONTEXT D-02 正・RESEARCH 行89 廃棄）。

    RESEARCH 行89 の「0999=99.9倍以上」記述は本モジュールで廃棄・0999=no_bet sentinel。
    fuku_odds_lower/fuku_odds_upper は NaN・odds_missing_reason='no_bet'。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds(["01030925"], fukuoddslow="0999", fukuoddshigh="0999")
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    assert len(result) == 1
    assert pd.isna(result["fuku_odds_lower"].iloc[0])
    assert pd.isna(result["fuku_odds_upper"].iloc[0])
    assert result["odds_missing_reason"].iloc[0] == "no_bet"


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
         "fukuoddslow": "0011", "fukuoddshigh": "0015",
         "fukusyoflag": "7", "datakubun": "1"},
        {"race_key": "2024-0104-05-1-06-1", "umaban": 1,
         "happyotime": "01040010",
         "happyo_datetime": pd.to_datetime("2024-01-04 00:10:00"),
         "fukuoddslow": "0012", "fukuoddshigh": "0018",
         "fukusyoflag": "7", "datakubun": "1"},
    ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    assert result["happyotime"].iloc[0] == "01032355"


def test_odds_snapshot_datakubun_filter():
    """DataKubun='1'(中間) のみ使用・'3'(最終)/'4'(確定) は除外（D-01）。

    同一 HappyoTime に datakubun='1' と '4' が混在しても '1' のみ使用される。
    中間 snapshot 09:25 (low=0011) と確定 snapshot 09:25 (low=9999) が同時刻にある場合、
    確定が混入せず中間値 0011 が選択されることを検証（D-01・Pitfall 2・T-05-07 mitigate）。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = pd.DataFrame([
        # 中間オッズ（採用されるべき）
        {"race_key": "2024-0103-05-1-06-1", "umaban": 1,
         "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0011", "fukuoddshigh": "0015",
         "fukusyoflag": "7", "datakubun": "1"},
        # 確定オッズ（D-01 で除外されるべき・同時刻だが datakubun='4'）
        {"race_key": "2024-0103-05-1-06-1", "umaban": 1,
         "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "9999", "fukuoddshigh": "9999",
         "fukusyoflag": "7", "datakubun": "4"},
    ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # datakubun='4' は除外され・'1' の 0011 が選択される（確定 9999 で上書きされない）
    assert result["fuku_odds_lower"].iloc[0] == 1.1


def test_odds_snapshot_returns_snake_case():
    """select_odds_snapshot 戻り値の odds 列は snake_case fuku_odds_lower/upper。

    cross-plan contract: Plan 02 ev_rank.py と Plan 05 run_backtest.py が
    JOIN するだけで column 再名不要。JODDS raw FukuOddsLow/High を rename 済み。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds = _make_jodds(["01030925"])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    assert "fuku_odds_lower" in result.columns
    assert "fuku_odds_upper" in result.columns
    # raw 列名（FukuOddsLow/FukuOddsHigh）は含まれない
    assert "FukuOddsLow" not in result.columns
    assert "FukuOddsHigh" not in result.columns


def test_odds_snapshot_multi_horse():
    """同一 race_key で3頭・各異なる odds を保持（HIGH-1・PK は race_key+Umaban 8カラム）。

    RESEARCH §1.1: JODDS PK は race_key 7カラム + Umaban の8カラム。
    merge_asof の by=['race_key','umaban'] で per-horse odds を保証。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = pd.DataFrame([
        {"race_key": "2024-0103-05-1-06-1", "umaban": u,
         "race_start_datetime": pd.to_datetime("2024-01-03 10:00:00")}
        for u in (1, 2, 3)
    ])
    rows = []
    for umaban, low, high in [(1, "0011", "0015"), (2, "0020", "0025"), (3, "0030", "0040")]:
        rows.append({
            "race_key": "2024-0103-05-1-06-1",
            "umaban": umaban,
            "happyotime": "01030925",
            "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
            "fukuoddslow": low,
            "fukuoddshigh": high,
            "fukusyoflag": "7",
            "datakubun": "1",
        })
    jodds = pd.DataFrame(rows)
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # 出力行数 == 3（各馬1行ずつ・HIGH-1）
    assert len(result) == 3
    # 各馬の odds が保持される（umaban で sort して比較）
    result_sorted = result.sort_values("umaban").reset_index(drop=True)
    assert result_sorted.loc[0, "fuku_odds_lower"] == 1.1
    assert result_sorted.loc[1, "fuku_odds_lower"] == 2.0
    assert result_sorted.loc[2, "fuku_odds_lower"] == 3.0


def test_odds_snapshot_fukusyoflag_normal_sale():
    """FukusuoFlag='7'(発売あり・EveryDB2 マニュアル正例) は odds を返す（MEDIUM positive test）。

    RESEARCH §1.1: FukusuoFlag は '0'(発売なし)/'1'(発売前取消)/'3'(発売後取消)/'7'(発売あり)。
    '7' は正常発売の正例・odds を返す。'0'/'1'/'3' は no_bet。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    # 正常発売 '7' → odds を返す
    race_times = _make_race_times("2024-01-03 10:00:00")
    jodds_normal = _make_jodds(["01030925"], fukusyoflag="7")
    result_normal = select_odds_snapshot(jodds_normal, race_times, policy="30min_before")
    assert result_normal["fuku_odds_lower"].iloc[0] == 1.1

    # 発売なし '0' → no_bet sentinel
    jodds_nosale = _make_jodds(["01030925"], fukusyoflag="0")
    result_nosale = select_odds_snapshot(jodds_nosale, race_times, policy="30min_before")
    assert pd.isna(result_nosale["fuku_odds_lower"].iloc[0])
    assert result_nosale["odds_missing_reason"].iloc[0] == "no_bet"


def test_odds_snapshot_multi_race():
    """複数レース + 重複 happyo_datetime で merge_asof が sort 違反なく per-horse snapshot を返す。

    MEDIUM-C cycle-2: race_key 優先 sort で happyo_datetime の大域ソートが崩れても
    merge_asof(by=['race_key','umaban']) が正常動作することを検証。
    R1: race_key=r1・umaban {1,2,3} / R2: race_key=r2・umaban {1,2}（計5頭）。
    各馬の happyo_datetime はレース間で重複（R1-umaban1 と R2-umaban1 の両者が 09:25 に snapshot）。
    """
    from src.ev.odds_snapshot import select_odds_snapshot

    race_times = pd.DataFrame([
        # R1 × 3頭
        {"race_key": "r1", "umaban": 1,
         "race_start_datetime": pd.to_datetime("2024-01-03 10:00:00")},
        {"race_key": "r1", "umaban": 2,
         "race_start_datetime": pd.to_datetime("2024-01-03 10:00:00")},
        {"race_key": "r1", "umaban": 3,
         "race_start_datetime": pd.to_datetime("2024-01-03 10:00:00")},
        # R2 × 2頭
        {"race_key": "r2", "umaban": 1,
         "race_start_datetime": pd.to_datetime("2024-01-03 11:00:00")},
        {"race_key": "r2", "umaban": 2,
         "race_start_datetime": pd.to_datetime("2024-01-03 11:00:00")},
    ])
    # 重複 happyo_datetime を意図的に作る（R1-umaban1 と R2-umaban1 が同 09:25・R2 は 10:25）
    jodds = pd.DataFrame([
        {"race_key": "r1", "umaban": 1, "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0011", "fukuoddshigh": "0015",
         "fukusyoflag": "7", "datakubun": "1"},
        {"race_key": "r1", "umaban": 2, "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0020", "fukuoddshigh": "0025",
         "fukusyoflag": "7", "datakubun": "1"},
        {"race_key": "r1", "umaban": 3, "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0030", "fukuoddshigh": "0040",
         "fukusyoflag": "7", "datakubun": "1"},
        # R2 は異なる odds・同じ 09:25 時刻（日跨ぎではないがレース間で重複）
        {"race_key": "r2", "umaban": 1, "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0050", "fukuoddshigh": "0060",
         "fukusyoflag": "7", "datakubun": "1"},
        {"race_key": "r2", "umaban": 2, "happyotime": "01030925",
         "happyo_datetime": pd.to_datetime("2024-01-03 09:25:00"),
         "fukuoddslow": "0070", "fukuoddshigh": "0080",
         "fukusyoflag": "7", "datakubun": "1"},
    ])
    result = select_odds_snapshot(jodds, race_times, policy="30min_before")
    # 行数 == 入力候補馬数 5（R1×3 + R2×2）・各馬の odds が正しく保持される
    assert len(result) == 5
    # r1-umaban1=1.1, r1-umaban2=2.0, r1-umaban3=3.0, r2-umaban1=5.0, r2-umaban2=7.0
    result_sorted = result.sort_values(["race_key", "umaban"]).reset_index(drop=True)
    assert result_sorted.loc[0, "fuku_odds_lower"] == 1.1   # r1-1
    assert result_sorted.loc[1, "fuku_odds_lower"] == 2.0   # r1-2
    assert result_sorted.loc[2, "fuku_odds_lower"] == 3.0   # r1-3
    assert result_sorted.loc[3, "fuku_odds_lower"] == 5.0   # r2-1
    assert result_sorted.loc[4, "fuku_odds_lower"] == 7.0   # r2-2
