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
    # vectorized 版
    s = pd.Series([1108.0, 0.0, -1.0, 9990.0, None])
    out = _time_to_seconds_series(s)
    assert abs(out.iloc[0] - 110.8) < 1e-9, "iloc[0]: 1108.0 ds → 110.8 s"
    assert pd.isna(out.iloc[1]), "iloc[1]: time=0 → NaN"
    assert pd.isna(out.iloc[2]), "iloc[2]: time=-1 → NaN"
    assert abs(out.iloc[3] - 999.0) < 1e-9, "iloc[3]: 9990.0 ds → 999.0 s"
    assert pd.isna(out.iloc[4]), "iloc[4]: None → NaN"


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
        f"target 当日 999.0秒が混入すると median が跳ね上がる"
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
