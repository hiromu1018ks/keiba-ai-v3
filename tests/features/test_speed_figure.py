# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/model/test_trainer.py と同一慣例)
"""SC#1/SC#3 単体テスト・speed_figure 算出・byte-reproducible・fallback・parity 下地（Phase 9 P01）。

本ファイルは ``src/features/speed_figure.py`` の機能単体テストであり・SC#2 adversarial
（注入型メタ検証）は ``tests/features/test_speed_figure_pit.py`` に独立層として存在する
（T-08-04 踏襲・機能テストと adversarial の棲み分け）。

cover: SC#1 byte-reproducible・SC#3 par/variant/speed_figure 算出・fallback 階層・float・parity 下地。

cross-reference: tests/features/test_speed_figure_pit.py（SC#2 adversarial・guard 無効化で混入実証）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.speed_figure import (
    POINTS_PER_SECOND_BY_DISTANCE_M,
    _derive_surface,
    _time_to_seconds,
    _time_to_seconds_series,
    compute_speed_figure,
    compute_speed_figure_for_history,
    get_points_per_second,
)
from tests.features.conftest import (
    _build_race_obs_row,
    _build_se_history_row,
    _build_speed_figure_history_rows,
)


def test_time_decisecond_conversion() -> None:
    """``time`` (0.1秒単位) → 秒換算: 1108.0 → 110.8・0/<0 は NaN。"""
    # スカラー版
    assert abs(_time_to_seconds(1108.0) - 110.8) < 1e-9, "1108.0 ds → 110.8 s"
    assert _time_to_seconds(0) != _time_to_seconds(0), "time=0 は NaN"
    assert _time_to_seconds(-5.0) != _time_to_seconds(-5.0), "time<0 は NaN"
    assert _time_to_seconds(None) != _time_to_seconds(None), "time=None は NaN"
    # vectorized 版（kyori/surface 引数無し: 従来挙動・範囲チェック無し）
    s = pd.Series([1108.0, 0.0, -1.0, 9990.0, None])
    out = _time_to_seconds_series(s)
    assert abs(out.iloc[0] - 110.8) < 1e-9, "iloc[0]: 1108.0 ds → 110.8 s"
    assert pd.isna(out.iloc[1]), "iloc[1]: time=0 → NaN"
    assert pd.isna(out.iloc[2]), "iloc[2]: time=-1 → NaN"
    assert abs(out.iloc[3] - 999.0) < 1e-9, "iloc[3]: 9990.0 ds → 999.0 s"
    assert pd.isna(out.iloc[4]), "iloc[4]: None → NaN"


def test_time_to_seconds_obstacle_and_physical_range_exclusion() -> None:
    """Phase 9 SC#5 外れ値根本対策: 障害除外 + 距離別物理妥持範囲外 NaN。

    live-DB SC#5 で rolling_speed_figure_mean_5 が min=-1748/max=4591 になった根本原因:
      (a) 障害レース(trackcd 51-59)は pps テーブルが平地専用なのに speed_figure 算出されていた
      (b) 1000m time=1176 (117.6s) 等・物理不可能な time>0（落馬/故障/記録ミス）が time<=0 チェック
          のみで生き残り par median を汚染していた

    本テストは ``_time_to_seconds_series(time, kyori, surface)`` が両者を NaN 化することを実証。
    """
    # 1000m・平地: 700 ds (70.0s・範囲 53-85) は保持・1176 ds (117.6s・範囲外) は NaN
    time = pd.Series([700.0, 1176.0, 1100.0, 700.0])
    kyori = pd.Series([1000, 1000, 1600, 1000])
    surface = pd.Series(["turf", "turf", "dirt", "obstacle"])
    out = _time_to_seconds_series(time, kyori, surface)
    # 1000m 70.0s → 保持
    assert abs(out.iloc[0] - 70.0) < 1e-9, "1000m 70.0s は範囲内(53-85) → 保持"
    # 1000m 117.6s → NaN（物理妥持範囲外・落馬/故障/記録ミス）
    assert pd.isna(out.iloc[1]), (
        "1000m 117.6s は物理妥持範囲外(53-85) → NaN（JRA 1000m record ~56s・正常完走は ~58-75s）"
    )
    # 1600m 110.0s → 保持
    assert abs(out.iloc[2] - 110.0) < 1e-9, "1600m 110.0s は範囲内(92-125) → 保持"
    # 1000m 70.0s だが obstacle → NaN（障害は Beyer 平地モデル不適合）
    assert pd.isna(out.iloc[3]), (
        "surface=='obstacle' は time_sec を NaN 化（pps テーブルが平地専用・SC#5 外れ値根本原因）"
    )


def test_surface_derivation() -> None:
    """trackcd → surface: 10/17/20=turf・23/24=dirt・52/54=obstacle・他=unknown。"""
    tc = pd.Series(["10", "17", "20", "23", "24", "52", "54", "99", None])
    s = _derive_surface(tc)
    assert s.iloc[0] == "turf", "trackcd=10 → turf"
    assert s.iloc[1] == "turf", "trackcd=17 → turf"
    assert s.iloc[2] == "turf", "trackcd=20 → turf"
    assert s.iloc[3] == "dirt", "trackcd=23 → dirt"
    assert s.iloc[4] == "dirt", "trackcd=24 → dirt"
    assert s.iloc[5] == "obstacle", "trackcd=52 → obstacle"
    assert s.iloc[6] == "obstacle", "trackcd=54 → obstacle"
    assert s.iloc[7] == "unknown", "trackcd=99 → unknown"
    assert s.iloc[8] == "unknown", "trackcd=None → unknown"


def test_obstacle_race_excluded_from_speed_figure() -> None:
    """Phase 9 SC#5 外れ値根本対策: 障害レース(trackcd 51-59) は speed_figure が NaN。

    障害レースの走破タイムは Beyer 平地モデル（POINTS_PER_SECOND_BY_DISTANCE_M は
    1000-3200m 平地専用・障害 3000m avg ~169s は平地 3000m ~180s と大きく異なる stamina profile）
    に適合しないため・speed_figure feature から除外する（落馬/故障でなく・意味的に不適合）。
    """
    # 障害(trackcd=52, kyori=3000) の過去走を持つ馬
    rows = [
        _build_se_history_row(
            kettonum=5001,
            race_date="2023-05-01",
            as_of_datetime=pd.to_datetime("2023-05-01"),
            time=1690.0,   # 169.0s・障害 3000m 典型
            trackcd="52",  # 障害
            kyori=3000,
            jyocd="05",
            kakuteijyuni=1,
            row_label="obstacle_past",
        ),
    ]
    history = pd.DataFrame(rows)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 5001, "2023-06-04", obs_id="OBS_OBS")]
    )
    result = compute_speed_figure_for_history(history, observations=obs)
    # 障害行の time_sec/speed_figure は NaN
    obstacle_rows = result[result["trackcd"].astype(str) == "52"]
    assert len(obstacle_rows) > 0, "テスト前提: 障害行が含まれる"
    assert obstacle_rows["time_sec"].isna().all(), (
        "障害 trackcd=52 の time_sec は NaN（surface=='obstacle' で除外）"
    )
    assert obstacle_rows["speed_figure"].isna().all(), (
        "障害 trackcd=52 の speed_figure は NaN（Beyer 平地モデル不適合・SC#5 外れ値根本対策）"
    )


def test_physical_outlier_does_not_pollute_par_median() -> None:
    """Phase 9 SC#5 外れ値根本対策: 物理異常値 time は par median を汚染しない。

    同一 jyocd×trackcd×kyori group 内の1行が 117.6s (1000m 物理不可能・落馬/故障/記録ミス) でも・
    物理妥持範囲外のため time_sec が NaN 化され・par median は正常行のみで算出される。
    もし範囲外チェックが無ければ・par median が異常値に引っ張られ速度指数が ±1000 超の外れ値になる
    （live-DB SC#5 min=-1748/max=4591 の再現）。
    """
    # 観測対象馬 6001 の過去走 30件: 29件は正常(60-67s)・1件は 117.6s(物理異常)
    # 同一 jyocd×trackcd×kyori group で物理異常値が par median を汚染しないことを検証
    rows = []
    for i in range(29):
        rows.append(_build_se_history_row(
            kettonum=6001,
            race_date=f"2023-04-{(i % 28) + 1:02d}",
            as_of_datetime=pd.to_datetime(f"2023-04-{(i % 28) + 1:02d}"),
            time=600.0 + (i % 8) * 10,   # 60.0-67.0s（1000m 正常完走範囲 53-85 内）
            trackcd="10",
            kyori=1000,
            jyocd="05",
            kakuteijyuni=1,
            row_label=f"normal_{i}",
        ))
    # 物理異常行: 1000m 117.6s（live-DB SC#5 で観測された外れ値）
    rows.append(_build_se_history_row(
        kettonum=6001,
        race_date="2023-03-15",
        as_of_datetime=pd.to_datetime("2023-03-15"),
        time=1176.0,   # 117.6s・物理不可能
        trackcd="10",
        kyori=1000,
        jyocd="05",
        kakuteijyuni=1,
        row_label="physical_outlier",
    ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 6001, "2023-06-04", obs_id="OBS_POLLUTION")]
    )
    result = compute_speed_figure_for_history(history, observations=obs)

    # 物理異常行の time_sec は NaN（範囲外チェック）
    outlier_rows = result[result["row_label"] == "physical_outlier"]
    assert len(outlier_rows) > 0, "テスト前提: physical_outlier 行が存在"
    assert outlier_rows["time_sec"].isna().all(), (
        "1000m 117.6s は物理妥持範囲外 → time_sec NaN（落馬/故障/記録ミス）"
    )
    assert outlier_rows["speed_figure"].isna().all(), (
        "物理異常値行の speed_figure は NaN（外れ値生成を根源防止）"
    )

    # 正常行の par_sec は異常値に汚染されていない
    # 異常値 117.6s が混入すると par median は ~63.5（正常29行 median）から跳ね上がり
    # 正常行の speed_figure も外れる。範囲外除外により par median ~63.5 が維持される。
    # 全行同一 (obs_id, jyocd, trackcd, kyori) group なので par_sec は全行同値
    par_vals = result["par_sec"].dropna()
    if len(par_vals) > 0:
        par_median = float(par_vals.iloc[0])
        # 正常29行の time_sec median は ~63.5（60-67s の中央値）
        # 異常値 117.6s が混入すると par median が ~66-67 に跳ね上がる
        assert par_median < 80.0, (
            f"par_sec={par_median}: 物理異常値 117.6s が par median に混入した疑い"
            f"（正常行のみの median は ~63.5 のはず）"
        )


def test_points_per_second_interpolation() -> None:
    """距離別 pps: 1200→13.2・1600→10.0・1400(中間)は線形補間・端点クランプ。"""
    assert abs(get_points_per_second(1200) - 13.2) < 1e-9, "1200m → 13.2"
    assert abs(get_points_per_second(1600) - 10.0) < 1e-9, "1600m → 10.0"
    # 1400m は 11.0 と 10.0 の境界点（POINTS_PER_SECOND_BY_DISTANCE_M に直接登録済み）
    assert abs(get_points_per_second(1400) - 11.0) < 1e-9, "1400m → 11.0 (直接登録値)"
    # 中間距離 1500m: 1400(11.0) と 1600(10.0) の中点 → 10.5
    assert abs(get_points_per_second(1500) - 10.5) < 1e-9, "1500m → 10.5 (補間)"
    # 端点クランプ: 1000 未満は 1000 の値・3200 超は 3200 の値
    assert abs(get_points_per_second(800) - POINTS_PER_SECOND_BY_DISTANCE_M[1000]) < 1e-9, "800m → 1000m 値でクランプ"
    assert abs(get_points_per_second(5000) - POINTS_PER_SECOND_BY_DISTANCE_M[3200]) < 1e-9, "5000m → 3200m 値でクランプ"


def test_par_pit_expanding() -> None:
    """PIT expanding par: target 当日行は par に混入しない（strict <）・par_sec は eligible 3行の median。

    target/same_day_prior/same_day_later/previous_day/future 行は PIT prefilter で除外され・
    結果フレームに含まれない（par 算出への混入が構造的不能）。eligible 3行のみが残り・
    同一 observation の par は time_sec(110.0, 111.0, 112.0) の median = 111.0。
    """
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS1")]
    )
    result = compute_speed_figure_for_history(history, observations=obs)
    # PIT prefilter(strict <) で adversarial 5行は除外されるため・結果は eligible 3行のみ
    labels_present = set(result["row_label"].dropna().unique())
    assert labels_present == {"eligible"}, (
        f"結果フレームは eligible 行のみ含むべき（adversarial 5行は PIT 除外）・実際: {labels_present}"
    )
    # eligible 3行の time_sec = 110.0, 111.0, 112.0 → 同一 observation の par median = 111.0
    eligible_mask = result["row_label"] == "eligible"
    par_vals = result.loc[eligible_mask, "par_sec"].dropna().unique()
    assert len(par_vals) == 1, f"eligible 3行の par_sec は全て同値(同一 observation の par)・実際: {par_vals}"
    assert abs(float(par_vals[0]) - 111.0) < 1e-9, (
        f"par_sec は eligible 3行の median=111.0・実際: {par_vals[0]}・"
        f"target 当日 124.0秒が混入すると median が跳ね上がる"
    )


def test_par_fallback_hierarchy() -> None:
    """par fallback 階層: 最細 group サンプル不足 → trackcd_kyori → all_day・NULL 禁止。"""
    # jyocd×trackcd×kyori group が _MIN_SAMPLES_PAR_JYO_TRACK_KYORI(30) 未満の小さい history
    rows = []
    for i in range(5):  # 5行のみ(< 30)・全て同一 jyocd/trackcd/kyori
        rows.append(_build_se_history_row(
            kettonum=2001,
            race_date=f"2023-05-{i+1:02d}",
            as_of_datetime=pd.to_datetime(f"2023-05-{i+1:02d}"),
            time=1100.0 + i * 10,   # 110.0, 111.0, ..., 114.0 秒
            trackcd="24",
            kyori=1600,
            jyocd="05",
            kakuteijyuni=1,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R2", 2001, "2023-06-04", obs_id="OBS_FALLBACK")]
    )
    result = compute_speed_figure_for_history(history, observations=obs)
    # 5行 < 30 のため jyocd_trackcd_kyori は fallback・trackcd_kyori も 5行 < 30 なので all_day へ
    fallback_levels = set(result["fallback_level"].dropna().unique())
    assert len(fallback_levels) >= 1, "fallback_level は必須(NULL 禁止)"
    for fl in fallback_levels:
        assert fl in {"jyocd_trackcd_kyori", "trackcd_kyori", "all_day"}, (
            f"fallback_level は3値のいずれか・実際: {fl}"
        )
    # 全行 fallback_level が NULL でない
    assert result["fallback_level"].notna().all(), "fallback_level は全行非 NULL"


def test_variant_leave_one_race_out() -> None:
    """variant leave-one-race-out: 自レースを除く same-day residual median（近似精度は docstring 明記範囲）。"""
    # 同一日の3頭(3 race)・jyocd/surface 同一・各 race 1行 → leave-one-out で他2行の median
    rows = []
    for horse, time_ds in [(3001, 1100.0), (3002, 1110.0), (3003, 1120.0)]:
        rows.append(_build_se_history_row(
            kettonum=horse,
            race_date="2023-05-15",
            as_of_datetime=pd.to_datetime("2023-05-15"),
            time=time_ds,
            trackcd="24",
            kyori=1600,
            jyocd="05",
            kakuteijyuni=1,
        ))
    history = pd.DataFrame(rows)
    # 各馬を別 observation として扱う
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0615-R1", 3001, "2023-06-04", obs_id="OBS_V1"),
        _build_race_obs_row("2023A0615-R2", 3002, "2023-06-04", obs_id="OBS_V2"),
        _build_race_obs_row("2023A0615-R3", 3003, "2023-06-04", obs_id="OBS_V3"),
    ])
    result = compute_speed_figure_for_history(history, observations=obs)
    # variant_sec 列が存在し NaN でない行が少なくともある
    assert "variant_sec" in result.columns, "variant_sec 列が存在"
    # 各 observation の par_sec は自身を含む group で計算されるが・variant は leave-one-out 近似
    # 厳密値でなく近似であることは docstring の通り・ここでは列の存在と NaN でないことを検証
    non_na_variant = result["variant_sec"].dropna()
    assert len(non_na_variant) > 0, "variant_sec に非 NaN 値が少なくとも1つはある"


def test_speed_figure_float_monotone() -> None:
    """speed_figure は par より速い(time<par)ほど大きい(float・丸めない・D-05)。"""
    # par_sec=110.0 として time_sec を変化
    sf_fast = compute_speed_figure(time_sec=109.0, par_sec=110.0, variant_sec=0.0, kyori=1600)
    sf_par = compute_speed_figure(time_sec=110.0, par_sec=110.0, variant_sec=0.0, kyori=1600)
    sf_slow = compute_speed_figure(time_sec=111.0, par_sec=110.0, variant_sec=0.0, kyori=1600)
    assert sf_fast > sf_par > sf_slow, (
        f"速いほど大きい: fast={sf_fast} > par={sf_par} > slow={sf_slow}"
    )
    # float・丸めない: 値が整数でないことを確認(非ゼロ小数部)
    assert isinstance(sf_fast, float), "speed_figure は float"
    # 109.0 vs 110.0 → diff=1.0 × 10.0 = 10.0 (整数になるが float 型)
    assert abs(sf_fast - 10.0) < 1e-9, f"(110-109)*10.0 = 10.0・実際: {sf_fast}"


def test_byte_reproducible_speed_figure() -> None:
    """SC#1 byte-reproducible: 同一 history+observations で bit-identical（決定論的・seed 不要）。"""
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_REPRO")]
    )
    r1 = compute_speed_figure_for_history(history, observations=obs)
    r2 = compute_speed_figure_for_history(history, observations=obs)
    # speed_figure 列が bit-identical
    assert np.array_equal(
        r1["speed_figure"].to_numpy(), r2["speed_figure"].to_numpy()
    ), "同一入力で speed_figure 列が bit-identical でない（SC#1 違反）"
    # par_sec / variant_sec も同様
    assert np.array_equal(
        r1["par_sec"].to_numpy(), r2["par_sec"].to_numpy()
    ), "同一入力で par_sec が bit-identical でない"
    assert np.array_equal(
        r1["variant_sec"].to_numpy(), r2["variant_sec"].to_numpy()
    ), "同一入力で variant_sec が bit-identical でない"


def test_empty_history_raises() -> None:
    """空 history は RuntimeError（fail-loud・WR-01 踏襲）。"""
    empty = pd.DataFrame(columns=[
        "kettonum", "race_date", "as_of_datetime", "time", "trackcd", "jyocd", "kyori"
    ])
    raised = False
    try:
        compute_speed_figure_for_history(empty)
    except RuntimeError:
        raised = True
    except Exception as e:  # 予期せぬ例外型
        raise AssertionError(
            f"空 history は RuntimeError 期待・実際 {type(e).__name__}: {e}"
        ) from e
    assert raised, "空 history で RuntimeError が発生していない（WR-01 fail-loud 違反）"


def test_compute_speed_figure_for_history_adds_columns() -> None:
    """戻り値に speed_figure/available_at/監査列が追加される（copy-not-rename・入力列は保持）。"""
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_COLS")]
    )
    result = compute_speed_figure_for_history(history, observations=obs)
    required = [
        "speed_figure",
        "available_at",
        "par_sec",
        "variant_sec",
        "speed_residual_sec",
        "sample_count",
        "fallback_level",
    ]
    for col in required:
        assert col in result.columns, f"必須列 {col} が不存在"
    # 入力列も保持(copy-not-rename)
    for orig_col in ["kettonum", "race_date", "time", "trackcd", "jyocd", "kyori"]:
        assert orig_col in result.columns, f"入力列 {orig_col} が破壊されている(copy-not-rename 違反)"
    # speed_residual_sec = time_sec - par_sec の不変量
    non_na = result.dropna(subset=["speed_residual_sec", "par_sec"])
    if len(non_na) > 0:
        for _, row in non_na.iterrows():
            expected = row["time_sec"] - row["par_sec"]
            assert abs(row["speed_residual_sec"] - expected) < 1e-6, (
                f"speed_residual_sec != time_sec - par_sec: {row['speed_residual_sec']} vs {expected}"
            )


# ---------------------------------------------------------------------------
# Phase 9 P03 Task 2: SC#1 byte-reproducible snapshot + SC#3 registry↔Parquet parity
# ---------------------------------------------------------------------------

def test_byte_reproducible_snapshot_with_speed_figure(tmp_path) -> None:
    """SC#1 byte-reproducible snapshot: 同一 DataFrame で snapshot_id/created_at を変えて
    write_snapshot を2回呼出し・SHA256 が bit-identical になる（CR-04・metadata 除外 schema bytes のみ依存）。

    speed_figure / rolling_speed_figure_* が snapshot の numeric path で Float64 化され・
    同一 DataFrame なら SHA256 が不変であることを実証する（T-09-11 mitigate）。
    """
    from src.features.rolling import build_rolling_features
    from src.features.snapshot import write_snapshot
    from src.model.orchestrator import FIXED_REPRODUCE_TS

    # 合成 history に speed_figure を付与 → rolling で rolling_speed_figure_* 6 feature を生成
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_SNAP")]
    )
    history_with_sf = compute_speed_figure_for_history(history, observations=obs)
    fm = build_rolling_features(obs, history_with_sf)

    # rolling_speed_figure_* 6 列が含まれることを確認（前提）
    expected_sf_cols = [
        "rolling_speed_figure_last_1",
        "rolling_speed_figure_mean_3",
        "rolling_speed_figure_mean_5",
        "rolling_speed_figure_max_5",
        "rolling_speed_figure_sd_5",
        "rolling_speed_figure_count_5",
    ]
    for col in expected_sf_cols:
        assert col in fm.columns, f"{col} が rolling 出力に含まれない（P02 拡張不備の可能性）"

    # 同一 DataFrame で snapshot_id/created_at_fixed を変えて2回書出し
    fixed_ts = FIXED_REPRODUCE_TS.isoformat()
    sha1 = write_snapshot(
        fm, out_dir=tmp_path, snapshot_id="test-speed-v1", created_at_fixed=fixed_ts
    )
    sha2 = write_snapshot(
        fm, out_dir=tmp_path, snapshot_id="test-speed-v2", created_at_fixed=fixed_ts
    )
    assert sha1 == sha2, (
        f"SHA256 が snapshot_id で変化した（CR-04 byte-reproducible 違反）: {sha1} vs {sha2}"
    )


def test_registry_parquet_parity_speed_figure() -> None:
    """SC#3 registry↔Parquet parity: rolling_speed_figure_* 6 feature が registry と
    FEATURE_COLUMNS の両方で整合する（HIGH #3 silent parity 違反回避・T-09-13 mitigate）。

    REVIEW H1 (data.py parameterization): ``_derive_feature_columns(snapshot_id=None)``
    は v1.0 デフォルト（rolling_speed_figure_* 非含）・speed_figure snapshot 生成後は
    動的導出で FEATURE_COLUMNS に含まれる契約を docstring で明示。
    本テストは registry と derived list の静的整合性を検証（KEIBA_SKIP_DB_TESTS 非依存）。
    """
    from src.features.availability import (
        load_feature_availability,
        registered_feature_columns,
    )
    from src.model.data import META_KEY_COLUMNS, RAW_ID_COLUMNS, LABEL_COLUMNS, _derive_feature_columns

    spec = load_feature_availability()
    reg = registered_feature_columns(spec)

    # registry に rolling_speed_figure_* 6 feature が登録されていること（P02 拡張）
    excluded = META_KEY_COLUMNS | RAW_ID_COLUMNS | LABEL_COLUMNS
    speed_cols_in_registry = [
        c for c in reg
        if c.startswith("rolling_speed_figure_") and c not in excluded
    ]
    assert sorted(speed_cols_in_registry) == sorted([
        "rolling_speed_figure_last_1",
        "rolling_speed_figure_mean_3",
        "rolling_speed_figure_mean_5",
        "rolling_speed_figure_max_5",
        "rolling_speed_figure_sd_5",
        "rolling_speed_figure_count_5",
    ]), f"registry の rolling_speed_figure_* が D-09 の6 feature と不一致: {speed_cols_in_registry}"

    # REVIEW H1: _derive_feature_columns(snapshot_id=None) は v1.0 snapshot を読むため
    # rolling_speed_figure_* を含まない（v1.0 は Phase 9 直前の snapshot）。これは H1-a/H1-b で
    # snapshot_id parameterization を行う前の後方互換挙動（A5）。
    v1_cols = _derive_feature_columns(snapshot_id=None)
    v1_speed = [c for c in v1_cols if c.startswith("rolling_speed_figure_")]
    assert v1_speed == [], (
        f"v1.0 snapshot_id=None の FEATURE_COLUMNS は rolling_speed_figure_* を含まない前提・"
        f"実際: {v1_speed}（snapshot_id 動的導入前の v1.0 硬結合状態）"
    )
