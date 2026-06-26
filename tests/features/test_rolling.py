# ruff: noqa: E501  (docstring / assert メッセージ / 日本語コメント行長は緩和・tests/features/test_field_strength.py 等と同一慣例)
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
    _build_se_history_row,
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


# ===========================================================================
# Phase 10 PLAN 02: rolling_field_strength_* 21 feature（D-06 第2段階・D-13）
#
# PLAN 01 が history に付与した field_strength profile 8値（中間値）を入力に・
# target 馬の過去走にわたり latest-K rolling（obs_id group・strict < cutoff・LOOKBACK=5）で
# 集約し 21 feature を生成する。既存 speed_figure 17 feature と完全に対称な idiom で拡張する。
#
# D-13 命名規則（_SPEED_FIGURE_AXES と異なり window 番号でなく意味サフィックス）:
#   - latest_1 系6: rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_latest_1
#   - mean_3 系5:   rolling_field_strength_{mean,median,top3_mean,top5_mean,max}_mean_3
#   - mean_5 系6:   rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_mean_5
#   - trend 系2:    rolling_field_strength_mean_trend_last_minus_mean5 / _trend_mean3_minus_mean5
#   - count/coverage 系2: rolling_field_strength_valid_count_mean_5 / coverage_mean_5
#   合計 6+5+6+2+2 = 21 feature
# ===========================================================================


# ---------------------------------------------------------------------------
# 合成 field_strength history builder（PLAN 01 出力形式の profile 8値を手動設定）
# ---------------------------------------------------------------------------
_FS_PROFILE_COLS = (
    "field_strength_mean",
    "field_strength_median",
    "field_strength_top3_mean",
    "field_strength_top5_mean",
    "field_strength_max",
    "field_strength_sd",
    "field_strength_valid_count",
    "field_strength_coverage",
)


def _build_fs_history_row(
    kettonum: int,
    race_date: str,
    *,
    fs_mean: float,
    fs_median: float,
    fs_top3: float,
    fs_top5: float,
    fs_max: float,
    fs_sd: float,
    fs_valid_count: int,
    fs_coverage: float,
) -> dict:
    """合成 history 行（field_strength profile 8値を手動設定・PLAN 01 出力形式）。

    PLAN 01 の compute_field_strength_profile を呼ばず・直接 profile 列を設定する（unit test として独立）。
    """
    row = _build_se_history_row(
        kettonum=kettonum,
        race_date=race_date,
    )
    # field_strength profile 8値（PLAN 01 出力形式・rolling source 列）
    row["field_strength_mean"] = fs_mean
    row["field_strength_median"] = fs_median
    row["field_strength_top3_mean"] = fs_top3
    row["field_strength_top5_mean"] = fs_top5
    row["field_strength_max"] = fs_max
    row["field_strength_sd"] = fs_sd
    row["field_strength_valid_count"] = fs_valid_count
    row["field_strength_coverage"] = fs_coverage
    return row


def _build_fs_5start_history(
    kettonum: int = 7007,
    obs_race_date: str = "2023-06-04",
    base_mean: float = 50.0,
) -> pd.DataFrame:
    """5走の過去走（cutoff 以前・全て eligible）を持つ field_strength history builder.

    各 row の field_strength_mean を区別値に設定し・最新1件目が最大値（base+5）になるよう構成。
    rolling_field_strength_mean_mean_5 = (base+1 + base+2 + base+3 + base+4 + base+5)/5 = base+3
    ・latest_1 = base+5（最新）・mean_3 = (base+5 + base+4 + base+3)/3 = base+4 で window 完全性を機械検出。
    """
    obs_rd = pd.to_datetime(obs_race_date)
    rows = []
    # 5走・全て cutoff 以前（2〜6日前）。i=1 が最古・i=5 が最新（race_date 降順で先頭）
    for i in range(1, 6):
        rd = obs_rd - pd.Timedelta(days=6 - i + 1)  # i=1 → -6d（最古）・i=5 → -2d（最新）
        rows.append(
            _build_fs_history_row(
                kettonum=kettonum,
                race_date=(rd).strftime("%Y-%m-%d"),
                fs_mean=base_mean + i,  # i=1(最古) → base+1 / i=5(最新) → base+5
                fs_median=base_mean + i + 0.5,
                fs_top3=base_mean + i + 1.0,
                fs_top5=base_mean + i + 1.5,
                fs_max=base_mean + i + 2.0,
                fs_sd=float(i),
                fs_valid_count=10 + i,
                fs_coverage=0.8 + i * 0.01,
            )
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1 (D-13 21 feature 完全性)
# ---------------------------------------------------------------------------
def test_field_strength_21_features_completeness():
    """D-13: rolling_field_strength_* 21 feature が全て生成される（列名完全性）.

    命名規則:
      - latest_1 系6: rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_latest_1
      - mean_3 系5:   rolling_field_strength_{mean,median,top3_mean,top5_mean,max}_mean_3
      - mean_5 系6:   rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_mean_5
      - trend 系2:    rolling_field_strength_mean_trend_{last_minus_mean5,mean3_minus_mean5}
      - count/coverage 系2: rolling_field_strength_{valid_count_mean_5,coverage_mean_5}
    """
    rolling = _get_rolling()

    # 21 feature の列名リスト（D-13 命名）
    expected_cols = [
        # latest_1 系6
        "rolling_field_strength_mean_latest_1",
        "rolling_field_strength_median_latest_1",
        "rolling_field_strength_top3_mean_latest_1",
        "rolling_field_strength_top5_mean_latest_1",
        "rolling_field_strength_max_latest_1",
        "rolling_field_strength_sd_latest_1",
        # mean_3 系5
        "rolling_field_strength_mean_mean_3",
        "rolling_field_strength_median_mean_3",
        "rolling_field_strength_top3_mean_mean_3",
        "rolling_field_strength_top5_mean_mean_3",
        "rolling_field_strength_max_mean_3",
        # mean_5 系6
        "rolling_field_strength_mean_mean_5",
        "rolling_field_strength_median_mean_5",
        "rolling_field_strength_top3_mean_mean_5",
        "rolling_field_strength_top5_mean_mean_5",
        "rolling_field_strength_max_mean_5",
        "rolling_field_strength_sd_mean_5",
        # trend 系2
        "rolling_field_strength_mean_trend_last_minus_mean5",
        "rolling_field_strength_mean_trend_mean3_minus_mean5",
        # count/coverage 系2
        "rolling_field_strength_valid_count_mean_5",
        "rolling_field_strength_coverage_mean_5",
    ]
    assert len(expected_cols) == 21, f"expected_cols の要素数が21でない: {len(expected_cols)}"

    # _FIELD_STRENGTH_AXES の要素数が21
    assert len(rolling._FIELD_STRENGTH_AXES) == 21, (
        f"_FIELD_STRENGTH_AXES の要素数が21でない: {len(rolling._FIELD_STRENGTH_AXES)}"
    )

    # _ROLLING_SYSTEMS に "field_strength" が含まれる
    assert "field_strength" in rolling._ROLLING_SYSTEMS, (
        "_ROLLING_SYSTEMS に field_strength が含まれない"
    )

    # _SYSTEM_SOURCE["field_strength"] が 8 source 列
    expected_sources = {
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    }
    assert set(rolling._SYSTEM_SOURCE["field_strength"]) == expected_sources, (
        f"_SYSTEM_SOURCE['field_strength'] が8 source 列でない: "
        f"{rolling._SYSTEM_SOURCE['field_strength']}"
    )

    # 実行して全列が生成されることを確認
    history = _build_fs_5start_history()
    obs = pd.DataFrame([{
        "kettonum": 7007,
        "feature_cutoff_datetime": pd.Timestamp("2023-06-03"),
    }])
    result = rolling.build_rolling_features(obs, history)
    for col in expected_cols:
        assert col in result.columns, f"生成結果に列が存在しない: {col}"


# ---------------------------------------------------------------------------
# Test 2 (PIT strict <・obs_id group)
# ---------------------------------------------------------------------------
def test_field_strength_pit_strict_less_obs_id_group():
    """PIT strict <・obs_id group・LOOKBACK=5 窓で cutoff 以前の最新5件のみで集約・未来行は混入しない.

    CYCLE-2 HIGH#1: 同一 horse が複数 observation に現れた場合・obs 毎に独立 window。
    """
    rolling = _get_rolling()

    # 5走 eligible + 2行 adversarial（当日・未来）で構成
    obs_rd = pd.to_datetime("2023-06-04")
    rows = []
    # eligible 5走（cutoff=6/3 以前・2〜6日前）
    for i in range(1, 6):
        rd = obs_rd - pd.Timedelta(days=i + 1)
        rows.append(_build_fs_history_row(
            kettonum=8008,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=10.0 + i,  # 11..15 → mean_5 = 13.0
            fs_median=0.0, fs_top3=0.0, fs_top5=0.0, fs_max=0.0, fs_sd=0.0,
            fs_valid_count=5, fs_coverage=0.5,
        ))
    # adversarial: 当日（target・除外）・未来（除外）・cutoff同日（除外）
    for off, _label in [(0, "target"), (2, "future"), (-1, "cutoff_day")]:
        rd = obs_rd + pd.Timedelta(days=off)
        rows.append(_build_fs_history_row(
            kettonum=8008,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=999.0,  # 混入検出用の識別値
            fs_median=999.0, fs_top3=999.0, fs_top5=999.0, fs_max=999.0, fs_sd=999.0,
            fs_valid_count=999, fs_coverage=0.99,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([{"kettonum": 8008, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]
    # mean_5 = (11+12+13+14+15)/5 = 13.0（adversarial 999.0 が混入しない）
    assert abs(float(row["rolling_field_strength_mean_mean_5"]) - 13.0) < 1e-9, (
        f"PIT strict < 違反: mean_mean_5 = {row['rolling_field_strength_mean_mean_5']}"
        f"（期待値 13.0・adversarial 999.0 が混入）"
    )


# ---------------------------------------------------------------------------
# Test 3 (sentinel ルール)
# ---------------------------------------------------------------------------
def test_field_strength_sentinel_rule_count_below_window():
    """count>=window で算出・未満は sentinel（NaN→MISSING）・best2_mean 系は使わない.

    3走のみの馬: mean_mean_5 / sd_mean_5 / max_mean_5 は sentinel（count<5）・
    mean_mean_3 / max_mean_3 は算出（count>=3）・mean_latest_1 は算出（count>=1）。
    """
    from src.utils.category_map import MISSING

    rolling = _get_rolling()

    obs_rd = pd.to_datetime("2023-06-04")
    rows = []
    # 3走のみ（cutoff 以前）・i=1 が最古・i=3 が最新（fs_mean=21..23・最新が23）
    for i in range(1, 4):
        rd = obs_rd - pd.Timedelta(days=4 - i + 1)  # i=1 → -4d（最古）・i=3 → -2d（最新）
        rows.append(_build_fs_history_row(
            kettonum=9009,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=20.0 + i,  # i=1(最古)=21 / i=3(最新)=23
            fs_median=20.0 + i, fs_top3=20.0 + i, fs_top5=20.0 + i,
            fs_max=20.0 + i, fs_sd=1.0,
            fs_valid_count=8, fs_coverage=0.8,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([{"kettonum": 9009, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]

    # window=5 系は sentinel（count=3 < 5）
    assert row["rolling_field_strength_mean_mean_5"] == MISSING, (
        f"count<5 なのに mean_mean_5 が sentinel でない: {row['rolling_field_strength_mean_mean_5']}"
    )
    assert row["rolling_field_strength_sd_mean_5"] == MISSING
    assert row["rolling_field_strength_max_mean_5"] == MISSING
    # trend 系も count>=5 で算出（window=5）なので sentinel
    assert row["rolling_field_strength_mean_trend_last_minus_mean5"] == MISSING

    # window=3 系は算出（count=3 >= 3）
    # mean_mean_3 = (21+22+23)/3 = 22.0
    assert abs(float(row["rolling_field_strength_mean_mean_3"]) - 22.0) < 1e-9
    # window=1 系は算出（count>=1）・最新1件目（race_start_datetime 降順で最初）= 23
    assert abs(float(row["rolling_field_strength_mean_latest_1"]) - 23.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 4 (count/coverage 軸は常に実際数値・sentinel 化しない)
# ---------------------------------------------------------------------------
def test_field_strength_count_coverage_always_real():
    """rolling_field_strength_valid_count_mean_5 / coverage_mean_5 は常に実際数値（0〜window）を出力.

    sentinel 化しない（D-11 信頼度軸・Phase 9.1 idiom 踏襲）。
    """
    from src.utils.category_map import MISSING

    rolling = _get_rolling()

    # 3走のみの場合でも count/coverage は実際数値
    obs_rd = pd.to_datetime("2023-06-04")
    rows = []
    for i in range(1, 4):
        rd = obs_rd - pd.Timedelta(days=i + 1)
        rows.append(_build_fs_history_row(
            kettonum=1010,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=30.0,
            fs_median=30.0, fs_top3=30.0, fs_top5=30.0,
            fs_max=30.0, fs_sd=1.0,
            fs_valid_count=12,  # 各 source race の opponent 有効数
            fs_coverage=0.75,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([{"kettonum": 1010, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]

    # valid_count_mean_5 = (12+12+12)/3 = 12.0（3走のみ・count>=5 でないが sentinel でない）
    vc = row["rolling_field_strength_valid_count_mean_5"]
    assert vc != MISSING, f"valid_count_mean_5 が sentinel 化した（D-11 違反）: {vc}"
    assert abs(float(vc) - 12.0) < 1e-9, f"valid_count_mean_5 が不正: {vc}"

    # coverage_mean_5 = 0.75（同様）
    cov = row["rolling_field_strength_coverage_mean_5"]
    assert cov != MISSING, f"coverage_mean_5 が sentinel 化した（D-11 違反）: {cov}"
    assert abs(float(cov) - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# Test 5 (trend 系)
# ---------------------------------------------------------------------------
def test_field_strength_trend_axes():
    """trend 系: trend_last_minus_mean5 = latest_1 の mean - mean_5 の mean・
    trend_mean3_minus_mean5 = mean_3 の mean - mean_5 の mean.
    """
    rolling = _get_rolling()

    # 5走で構成・field_strength_mean = [41, 42, 43, 44, 45]（直近1件目=45・3件=[45,44,43]・5件=全て）
    history = _build_fs_5start_history(kettonum=1111, base_mean=40.0)
    obs = pd.DataFrame([{"kettonum": 1111, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]

    # field_strength_mean の5走 = 41..45（直近1件=45・mean3=(45+44+43)/3=44・mean5=(41+42+43+44+45)/5=43）
    # trend_last_minus_mean5 = latest_1.mean - mean_5.mean = 45 - 43 = 2.0
    trend_last = row["rolling_field_strength_mean_trend_last_minus_mean5"]
    assert abs(float(trend_last) - 2.0) < 1e-9, (
        f"trend_last_minus_mean5 が不正: {trend_last}（期待値 2.0）"
    )
    # trend_mean3_minus_mean5 = mean_3 - mean_5 = 44 - 43 = 1.0
    trend_m3 = row["rolling_field_strength_mean_trend_mean3_minus_mean5"]
    assert abs(float(trend_m3) - 1.0) < 1e-9, (
        f"trend_mean3_minus_mean5 が不正: {trend_m3}（期待値 1.0）"
    )


# ---------------------------------------------------------------------------
# Test 6 (top-k source: top3_mean/top5_mean は profile → rolling の2段階で正常動作)
# ---------------------------------------------------------------------------
def test_field_strength_topk_source_two_stage():
    """source 列の top3_mean/top5_mean（PLAN 01 出力）を rolling で更に mean 化する場合も正常動作.

    profile → rolling の2段階構造（top3/top5 は各 source race 内の opponent top-k 平均・
    rolling はその target 馬の過去走にわたる mean）。
    """
    rolling = _get_rolling()

    # 5走の top3_mean = [51, 52, 53, 54, 55]・top5_mean = [61, 62, 63, 64, 65]
    obs_rd = pd.to_datetime("2023-06-04")
    rows = []
    for i in range(1, 6):
        rd = obs_rd - pd.Timedelta(days=i + 1)
        rows.append(_build_fs_history_row(
            kettonum=1212,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=0.0,
            fs_median=0.0,
            fs_top3=50.0 + i,  # 51..55
            fs_top5=60.0 + i,  # 61..65
            fs_max=0.0, fs_sd=0.0,
            fs_valid_count=10, fs_coverage=0.5,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([{"kettonum": 1212, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)
    row = result.iloc[0]

    # top3_mean_mean_5 = (51+52+53+54+55)/5 = 53.0
    assert abs(float(row["rolling_field_strength_top3_mean_mean_5"]) - 53.0) < 1e-9
    # top5_mean_mean_5 = (61+62+63+64+65)/5 = 63.0
    assert abs(float(row["rolling_field_strength_top5_mean_mean_5"]) - 63.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 7 (byte-reproducible)
# ---------------------------------------------------------------------------
def test_field_strength_byte_reproducible():
    """byte-reproducible（§19.1）: 同一 history で2回呼出すと21 feature 全て bit-identical."""
    import numpy as np

    rolling = _get_rolling()

    history = _build_fs_5start_history(kettonum=1313, base_mean=70.0)
    obs = pd.DataFrame([{"kettonum": 1313, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result1 = rolling.build_rolling_features(obs, history)
    result2 = rolling.build_rolling_features(obs, history)

    fs_cols = [c for c in result1.columns if c.startswith("rolling_field_strength_")]
    assert len(fs_cols) == 21
    for col in fs_cols:
        v1 = result1.iloc[0][col]
        v2 = result2.iloc[0][col]
        # 数値の場合は np.array_equal・MISSING sentinel の場合は同値
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            assert np.array_equal([v1], [v2]), f"{col} が bit-identical でない: {v1} vs {v2}"
        else:
            assert v1 == v2, f"{col} が bit-identical でない: {v1} vs {v2}"


# ---------------------------------------------------------------------------
# Test 8 (copy-not-rename・HIGH#5)
# ---------------------------------------------------------------------------
def test_field_strength_copy_not_rename():
    """HIGH#5: 入力 history の既存列は破壊されず・21 列が copy 追加される."""
    rolling = _get_rolling()

    history = _build_fs_5start_history(kettonum=1414, base_mean=80.0)
    history_cols_before = set(history.columns)
    history_rows_before = len(history)
    obs = pd.DataFrame([{"kettonum": 1414, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result = rolling.build_rolling_features(obs, history)

    # history は破壊されない（copy-not-rename）
    assert set(history.columns) == history_cols_before, "入力 history の列が破壊された（HIGH#5 違反）"
    assert len(history) == history_rows_before, "入力 history の行数が破壊された（HIGH#5 違反）"

    # result に 21 列が追加されている（observations 側に付与）
    fs_cols = [c for c in result.columns if c.startswith("rolling_field_strength_")]
    assert len(fs_cols) == 21


# ---------------------------------------------------------------------------
# Test 9 (CYCLE-2 HIGH-C2-2 downstream gate・10-REVIEWS.md L94-99, L211-217, L296)
# ---------------------------------------------------------------------------
def test_field_strength_high_c22_downstream_propagation():
    """CYCLE-2 HIGH-C2-2 downstream gate・両方向検証.

    PLAN 02 の入力 profile が PLAN 01 の source-as-of full-pipeline 再計算（C2-1 fix）に依存することを
    機械表示:
      (a) 汚染 profile（target-cutoff-contaminated opponent 混入想定の汚染値）→ rolling 出力も汚染される（伝播）
      (b) クリーン profile（source-as-of full-pipeline 再計算）→ rolling も正しい値

    これにより PLAN 01 の C2-1 fix が PLAN 02 の前提であることが機械的に表示される
    （PLAN 02 単体では C2-1 を解決せず・PLAN 01 の source-as-of full-pipeline 再計算 profile が前提）。
    """
    rolling = _get_rolling()

    obs_rd = pd.to_datetime("2023-06-04")
    # クリーン profile: 4走・mean = [11, 12, 13, 14]（最新=14・降順で [14,13,12,11]）
    # → mean_5 = sentinel（count=4 < 5）だが count>=4 で mean_5 を算出可能にするため 4 走 + dirty 1件 = 5 走で検証
    clean_rows = []
    for i in range(1, 5):
        rd = obs_rd - pd.Timedelta(days=5 - i + 1)  # i=1 → -5d（最古）・i=4 → -2d（最新）
        clean_rows.append(_build_fs_history_row(
            kettonum=1515,
            race_date=rd.strftime("%Y-%m-%d"),
            fs_mean=10.0 + i,  # i=1(最古)=11 / i=4(最新)=14
            fs_median=0.0, fs_top3=0.0, fs_top5=0.0,
            fs_max=0.0, fs_sd=0.0,
            fs_valid_count=9, fs_coverage=0.9,
        ))
    clean_history = pd.DataFrame(clean_rows)

    # 汚染 profile: クリーン profile 4走 に (source, target] 区間の汚染 opponent 混入を想定した
    # 汚染値（fs_mean=999.0）を「最新」として1件追加（target-cutoff-contaminated speed_figure 流用を想定）。
    # これにより dirty 側は5走（count=5・window=5 窓内）になり・mean_5 が (11+12+13+14+999)/5 = 209.8 に変化。
    # クリーン4走のみでは count<5 で mean_5 は sentinel になり比較不能なため・クリーン側も5走目（正当値=15）を用意。
    clean_history_with_5th = pd.concat([
        clean_history,
        pd.DataFrame([_build_fs_history_row(
            kettonum=1515,
            race_date=(obs_rd - pd.Timedelta(days=6)).strftime("%Y-%m-%d"),  # 6日前・最古
            fs_mean=15.0,  # 5走目（正当値）
            fs_median=0.0, fs_top3=0.0, fs_top5=0.0,
            fs_max=0.0, fs_sd=0.0,
            fs_valid_count=9, fs_coverage=0.9,
        )]),
    ], ignore_index=True)
    # clean_history_with_5th: 5走・mean = [11,12,13,14,15]・最新5件 = 全て → mean_5 = 13.0
    # ※ race_date: -5d(11), -4d(12), -3d(13), -2d(14), -6d(15)・降順で [14,13,12,11,15]・最新5件 = 全て

    dirty_history = pd.concat([
        clean_history,  # 4走
        pd.DataFrame([_build_fs_history_row(
            kettonum=1515,
            race_date=(obs_rd - pd.Timedelta(days=6)).strftime("%Y-%m-%d"),  # 6日前（5走目・窓内）
            fs_mean=999.0,  # 汚染値（target-cutoff-contaminated 由来を想定）
            fs_median=0.0, fs_top3=0.0, fs_top5=0.0,
            fs_max=0.0, fs_sd=0.0,
            fs_valid_count=9, fs_coverage=0.9,
        )]),
    ], ignore_index=True)
    # dirty_history: 5走・降順で [14,13,12,11,999] → mean_5 = (14+13+12+11+999)/5 = 209.8

    obs = pd.DataFrame([{"kettonum": 1515, "feature_cutoff_datetime": pd.Timestamp("2023-06-03")}])

    result_clean = rolling.build_rolling_features(obs, clean_history_with_5th)
    result_dirty = rolling.build_rolling_features(obs, dirty_history)

    # (a) 汚染伝播: dirty 側は rolling_field_strength_mean_mean_5 が 999.0 の影響で変化
    clean_mean5 = float(result_clean.iloc[0]["rolling_field_strength_mean_mean_5"])
    dirty_mean5 = float(result_dirty.iloc[0]["rolling_field_strength_mean_mean_5"])
    assert abs(clean_mean5 - 13.0) < 1e-9, f"クリーン profile の mean_5 が不正: {clean_mean5}"
    assert abs(dirty_mean5 - 13.0) > 1e-9, (
        f"汚染 profile なのに rolling 出力が変わらない（伝播なし・C2-2 検出力不足）: "
        f"clean={clean_mean5}, dirty={dirty_mean5}"
    )

    # (b) クリーン profile なら rolling 出力も正しい値（mean_5 = 13.0）
    # 上記 clean_mean5 assert で立証済み
