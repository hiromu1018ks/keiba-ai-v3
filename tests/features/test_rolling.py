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
    history = pd.DataFrame(columns=["kettonum", "as_of_datetime", "kakuteijyuni"])
    result = rolling.build_rolling_features(obs, history)
    assert result.iloc[0]["rolling_kakuteijyuni_mean_5"] == MISSING


def test_rolling_three_axes_present():
    rolling = _get_rolling()
    result_columns = rolling.build_rolling_features.__doc__ or ""
    # 各系統で mean / latest / sd の3列が存在・sd は n<2 で __MISSING__（Pitfall 3.3）
    src = inspect.getsource(rolling)
    assert "mean_5" in src and "latest_5" in src and "sd_5" in src


def test_target_race_timediff_not_in_history():
    """対象レース自身の kakuteijyuni が rolling 入力 history に含まれない（defense-in-depth・Pitfall 3.1）。

    ※ CR-01 (03-05): timediff 系統は rolling から削除されたため、残存系統 kakuteijyuni で
    同等の PIT defense-in-depth を検証する（target/同日/前日/future の除外・eligible 3行のみ包含）。
    eligible 3行の kakuteijyuni=(1.0,2.0,3.0) → mean=2.0。
    """
    rolling = _get_rolling()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([{"kettonum": 1001, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])
    result = rolling.build_rolling_features(obs, history)
    # target kakuteijyuni=99 等が混入すると mean が 2.0 から外れる
    assert abs(result.iloc[0]["rolling_kakuteijyuni_mean_5"] - (2.0)) < 1e-9


def test_harontimel4_not_in_feature_matrix():
    """feature matrix に harontimel4 列が存在しない（Pitfall 3.6）。"""
    rolling = _get_rolling()
    src = inspect.getsource(rolling)
    assert "harontimel4" not in src, "rolling モジュールに harontimel4 が現れる（Pitfall 3.6 違反）"


# ---------------------------------------------------------------------------
# REVIEWS HIGH #1: per-observation latest-5 algorithm 対抗テスト
# ---------------------------------------------------------------------------
def test_per_observation_latest_5_excludes_target_same_day_previous_future():
    """5行 adversarial + 3行 eligible の history で rolling_kakuteijyuni_mean_5 == 2.0（eligible のみ）。

    ※ CR-01 (03-05): timediff 系統は rolling から削除されたため残存系統 kakuteijyuni で検証。
    eligible 3行 (1.0,2.0,3.0) のみを含む → mean=2.0。
    """
    rolling = _get_rolling()
    history = _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([{"kettonum": 1001, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])
    result = rolling.build_rolling_features(obs, history)
    assert abs(result.iloc[0]["rolling_kakuteijyuni_mean_5"] - (2.0)) < 1e-9, (
        "target/same_day/previous_day/future の異常値が rolling に混入（HIGH #1 違反）"
    )


def test_two_observation_window_is_per_observation_not_per_horse():
    """CYCLE-2 HIGH #1 re-open: 同一 horse × 2 obs × 異 cutoff で rolling 結果が異なる。

    horse-grouped `groupby("kettonum").head(5)` では必ず RED・obs_id-keyed のみ GREEN。
    ※ CR-01 (03-05): timediff 系統は rolling から削除されたため残存系統 kakuteijyuni で検証。
    obs_A window = both_pre のみ（kakuteijyuni=1）
    obs_B window = both_pre + obs_B_only_pre の平均（=((1)+(7))/2 = 4.0）
    """
    rolling = _get_rolling()
    observations, history = _build_two_observation_rolling_rows(kettonum=2002)
    result = rolling.build_rolling_features(observations, history)
    obs_a = result[result["obs_id"] == "A"].iloc[0]
    obs_b = result[result["obs_id"] == "B"].iloc[0]
    assert abs(obs_a["rolling_kakuteijyuni_mean_5"] - (1.0)) < 1e-9, (
        "obs_A に obs_B_only_pre が混入（CYCLE-2 HIGH #1 違反）"
    )
    assert abs(obs_b["rolling_kakuteijyuni_mean_5"] - (4.0)) < 1e-9, (
        "obs_B に both_pre + obs_B_only_pre の平均が含まれない"
    )
    assert obs_a["rolling_kakuteijyuni_mean_5"] != obs_b["rolling_kakuteijyuni_mean_5"], (
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


# ---------------------------------------------------------------------------
# CR-02 (03-REVIEW): jyocd は categorical（varchar 競馬場コード）として最頻値集計
# ---------------------------------------------------------------------------
def test_jyocd_categorical_mode_aggregation():
    """CR-02 (03-REVIEW): rolling_jyocd は数値 mean/sd でなく最頻値(mode)と直近値(latest)
    を算出する。varchar(2) 競馬場コードの数値平均は意味をなさないため categorical 扱い。

    検証: 過去5走の競馬場コード ["05","05","05","01","01"] の mode="05"・latest="01"
    （race_start_datetime 降順で最初）・count=5。mean/sd 列は生成されない。
    """
    rolling = _get_rolling()
    from src.features.rolling import _CATEGORICAL_SYSTEMS

    assert "jyocd" in _CATEGORICAL_SYSTEMS, "jyocd が categorical 系統に含まれない（CR-02）"

    # history: 馬 3003 の過去5走・race_date 降順で [01, 01, 05, 05, 05]
    #（最新が 01、3走前〜5走前が 05・mode は同票の場合値昇順で最小→"01" になるが
    # ここでは 05 を3回出して mode="05" になるよう構成）
    base = pd.Timestamp("2023-06-04")
    history_rows = []
    # 最新から順: 01(2回) → 05(3回)・latest=01・mode=05
    seq = [("01", -1), ("01", -2), ("05", -3), ("05", -4), ("05", -5)]
    for jyocd_val, day_off in seq:
        rd = base + pd.Timedelta(days=day_off)
        history_rows.append({
            "kettonum": 3003, "year": 2023, "jyocd": jyocd_val, "kaiji": 1,
            "nichiji": 1, "racenum": 1, "race_date": rd,
            "race_start_datetime": rd + pd.Timedelta(hours=12),
            "as_of_datetime": rd + pd.Timedelta(hours=12),
            "kakuteijyuni": 1, "harontimel3": 36.0, "jyuni3c": 1, "jyuni4c": 1,
            "jyuni1c": 0, "kyori": 1600,
        })
    history = pd.DataFrame(history_rows)
    obs = pd.DataFrame([{
        "kettonum": 3003, "feature_cutoff_datetime": base - pd.Timedelta(days=1),
    }])
    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]

    # categorical 系統: mode / latest / count のみ（mean/sd は無い）
    assert "rolling_jyocd_mode_5" in result.columns, "jyocd の mode_5 列が無い（CR-02）"
    assert "rolling_jyocd_latest_5" in result.columns, "jyocd の latest_5 列が無い（CR-02）"
    assert "rolling_jyocd_count_5" in result.columns, "jyocd の count_5 列が無い"
    assert "rolling_jyocd_mean_5" not in result.columns, (
        "jyocd に mean_5 が存在する（CR-02 違反・categorical は数値平均しない）"
    )
    assert "rolling_jyocd_sd_5" not in result.columns, (
        "jyocd に sd_5 が存在する（CR-02 違反）"
    )
    assert row["rolling_jyocd_mode_5"] == "05", (
        f"jyocd mode が不正: {row['rolling_jyocd_mode_5']}（期待値 '05'・3回出現で最頻）"
    )
    # latest: cutoff = base-1day（6/3・strict <）なので最新の 6/3(day_off=-1) は除外され、
    # 次の 6/2(day_off=-2) の "01" が latest になる
    assert row["rolling_jyocd_latest_5"] == "01", (
        f"jyocd latest が不正: {row['rolling_jyocd_latest_5']}（期待値 '01'・直近値）"
    )
    # cutoff strict < で day_off=-1 (6/3) は除外されるため count=4
    assert int(row["rolling_jyocd_count_5"]) == 4, (
        f"jyocd count が不正: {row['rolling_jyocd_count_5']}（期待値 4・cutoff strict < で最新1件除外）"
    )
