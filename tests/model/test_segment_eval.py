"""segment_eval.py 契約テスト（Phase 6 Plan 06-03・EVAL-03 / D-10 / D-11 / D-12）。

Task 1: evaluate_segment_axis / evaluate_all_segments / banding 関数の9テスト。
Task 2: render_segment_curves_html / write_segment_reports の6テスト（後続追加）。

設計の核心:
  - evaluator.py の binning 契約（_compute_calibration_curve_bins / CALIBRATION_CURVE_BINS=10 /
    CALIBRATION_CURVE_MIN_BIN_COUNT=30）を再利用し・bit-identical を保証（T-06-07）。
  - REVIEW HIGH#4: ninki/odds_band は _ninki_band/_odds_band で離散帯に変換（生値でない）。
  - REVIEW C12: race_date dtype が date object / object dtype / datetime64[ns] のいずれでも
    pd.to_datetime(errors="coerce") で正規化してから .dt.year/.dt.month を抽出。
"""

from __future__ import annotations

import datetime
import json

import numpy as np
import pandas as pd

from src.model.evaluator import (
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    _compute_calibration_curve_bins,
)
from src.model.segment_eval import (
    NINKI_BAND_LABELS,
    ODDS_BAND_LABELS,
    SEGMENT_AXES,
    _ninki_band,
    _odds_band,
    evaluate_all_segments,
    evaluate_segment_axis,
)

# ---------------------------------------------------------------------------
# 合成データヘルパ
# ---------------------------------------------------------------------------


def _make_synthetic_segment_df(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """6軸の segment 列を持つ合成 DataFrame を生成。

    race_date は datetime.date object（C12 テストで object dtype 経路を踏む）。
    jyocd は 5-10（JRA 中央競馬場コード相当）・entry_count は 8-18。
    ninki は 1-18・fukuoddslower は 1.0-50.0 の連続 float。
    """
    rng = np.random.default_rng(seed)
    # race_date: 2021-2024 のランダム日付（date object）
    base = datetime.date(2021, 1, 1)
    days = rng.integers(0, 365 * 4, size=n)
    race_dates = [base + datetime.timedelta(int(d)) for d in days]

    df = pd.DataFrame(
        {
            "race_date": race_dates,
            "jyocd": rng.integers(5, 11, size=n),  # 5-10
            "entry_count": rng.integers(8, 19, size=n),  # 8-18
            "ninki": rng.integers(1, 19, size=n),  # 1-18
            "fukuoddslower": rng.uniform(1.0, 50.0, size=n),  # 1.0-50.0
        }
    )
    # 予測確率: logit 正規分布で [0.05, 0.95] に clip・真ラベルと相関を持たせる
    logit = rng.normal(0.0, 1.0, size=n)
    p = 1.0 / (1.0 + np.exp(-logit))
    # ninki が小さい（1番人気）ほど p が高くなるようバイアス
    p = np.clip(p - (df["ninki"].to_numpy() - 9) * 0.02, 0.02, 0.98)
    df["p_fukusho_hit"] = p
    # 真ラベル: Bernoulli(p)
    df["fukusho_hit"] = (rng.random(n) < p).astype(int)
    return df


# ---------------------------------------------------------------------------
# Task 1: banding 関数 / SEGMENT_AXES / evaluate_segment_axis / evaluate_all_segments
# ---------------------------------------------------------------------------


def test_segment_axes_all_six_defined() -> None:
    """SEGMENT_AXES が6軸（year/month/jyocd/entry_count/ninki/odds_band）のキーを持つ（D-12）。"""
    assert set(SEGMENT_AXES.keys()) == {
        "year",
        "month",
        "jyocd",
        "entry_count",
        "ninki",
        "odds_band",
    }
    # year/month は同じ race_date 列を共有（Info #6 一元化）
    assert SEGMENT_AXES["year"] == "race_date"
    assert SEGMENT_AXES["month"] == "race_date"
    # ninki/odds_band は banding 対象列
    assert SEGMENT_AXES["ninki"] == "ninki"
    assert SEGMENT_AXES["odds_band"] == "fukuoddslower"


def test_ninki_band_discretizer() -> None:
    """_ninki_band が ninki 値を4帯ラベルに変換（REVIEW HIGH#4・np.digitize・決定論的）。"""
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 18])
    result = _ninki_band(s)
    expected = np.array(
        ["1-3", "1-3", "1-3", "4-6", "4-6", "4-6", "7-9", "7-9", "7-9", "10+", "10+", "10+"],
        dtype=object,
    )
    assert list(result) == list(expected)
    # 区分確認
    assert NINKI_BAND_LABELS == ("1-3", "4-6", "7-9", "10+")


def test_ninki_band_handles_nan() -> None:
    """_ninki_band が NaN/None を __MISSING__ に変換（evaluator missing reason 慣例）。"""
    s = pd.Series([1, np.nan, None, 18])
    result = _ninki_band(s)
    assert result[0] == "1-3"
    assert result[1] == "__MISSING__"
    assert result[2] == "__MISSING__"
    assert result[3] == "10+"


def test_odds_band_discretizer() -> None:
    """_odds_band が fukuoddslower を4帯ラベルに変換（REVIEW HIGH#4・np.digitize・決定論的）。"""
    s = pd.Series([1.5, 2.9, 3.0, 4.9, 5.0, 9.9, 10.0, 25.0])
    result = _odds_band(s)
    expected = np.array(
        [
            "1.0-2.9",
            "1.0-2.9",
            "3.0-4.9",
            "3.0-4.9",
            "5.0-9.9",
            "5.0-9.9",
            "10+",
            "10+",
        ],
        dtype=object,
    )
    assert list(result) == list(expected)
    assert ODDS_BAND_LABELS == ("1.0-2.9", "3.0-4.9", "5.0-9.9", "10+")


def test_evaluate_segment_axis_returns_curve_and_scalar() -> None:
    """evaluate_segment_axis が {segment_value: {curve, scalar}} スキーマを返す。"""
    rng = np.random.default_rng(0)
    n = 500
    # jyocd 2値・各 250 サンプル（MIN_BIN_COUNT=30 を満たす）
    seg = np.array([5] * 250 + [10] * 250)
    logit = rng.normal(0, 1, n)
    y_pred = 1.0 / (1.0 + np.exp(-logit))
    y_true = (rng.random(n) < y_pred).astype(int)

    result = evaluate_segment_axis(y_true, y_pred, seg, axis_name="jyocd")

    assert set(result.keys()) == {"5", "10"}
    for _seg_val, data in result.items():
        assert "curve" in data
        assert "scalar" in data
        curve = data["curve"]
        assert set(curve.keys()) == {"mean_pred", "frac_pos", "count"}
        assert len(curve["mean_pred"]) == len(curve["frac_pos"]) == len(curve["count"])
        scalar = data["scalar"]
        assert set(scalar.keys()) == {
            "ece_quantile",
            "ece_uniform",
            "mce_guarded",
            "max_dev_guarded",
            "n_samples",
        }
        assert scalar["n_samples"] == 250


def test_segment_curve_binning_contract() -> None:
    """evaluate_segment_axis が evaluator._compute_calibration_curve_bins と同一結果（bit-identical）。"""
    rng = np.random.default_rng(1)
    n = 500
    seg = np.array(["A"] * n)
    logit = rng.normal(0, 1, n)
    y_pred = 1.0 / (1.0 + np.exp(-logit))
    y_true = (rng.random(n) < y_pred).astype(int)

    result = evaluate_segment_axis(y_true, y_pred, seg, axis_name="test")
    seg_data = result["A"]
    curve = seg_data["curve"]

    # 同一入力で evaluator の binning ヘルパを直接呼出し・一致を検証（T-06-07）
    expected = _compute_calibration_curve_bins(
        y_true, y_pred, strategy="uniform", n_bins=CALIBRATION_CURVE_BINS
    )
    np.testing.assert_array_almost_equal(np.array(curve["mean_pred"]), expected["mean_pred"])
    np.testing.assert_array_almost_equal(np.array(curve["frac_pos"]), expected["frac_pos"])
    np.testing.assert_array_equal(np.array(curve["count"]), expected["counts"].astype(int))


def test_segment_small_skip() -> None:
    """MIN_BIN_COUNT=30 未満の segment 値はスキップされる（Pitfall 6）。"""
    rng = np.random.default_rng(2)
    n = 500
    # seg=A: 450 サンプル（閾値以上）・seg=B: 20 サンプル（閾値未満・skip 対象）
    seg = np.array(["A"] * 450 + ["B"] * 20 + ["A"] * 30)
    logit = rng.normal(0, 1, n)
    y_pred = 1.0 / (1.0 + np.exp(-logit))
    y_true = (rng.random(n) < y_pred).astype(int)

    result = evaluate_segment_axis(y_true, y_pred, seg, axis_name="test")

    assert "A" in result
    assert "B" not in result  # 20 < 30 → skip
    assert CALIBRATION_CURVE_MIN_BIN_COUNT == 30


def test_evaluate_all_segments_six_axes() -> None:
    """evaluate_all_segments が6軸のキーを全て返す（D-12・欠損軸は空 dict）。"""
    df = _make_synthetic_segment_df(n=2000, seed=42)
    result = evaluate_all_segments(df)

    assert set(result.keys()) == set(SEGMENT_AXES.keys())
    # 各軸は dict（空でない可能性が高い・合成データなので）
    for axis_name in SEGMENT_AXES:
        assert isinstance(result[axis_name], dict)


def test_segment_json_schema() -> None:
    """evaluate_segment_axis 戻り値が json.dumps でシリアライズ可能。"""
    rng = np.random.default_rng(3)
    n = 500
    seg = np.array(["X"] * n)
    logit = rng.normal(0, 1, n)
    y_pred = 1.0 / (1.0 + np.exp(-logit))
    y_true = (rng.random(n) < y_pred).astype(int)

    result = evaluate_segment_axis(y_true, y_pred, seg, axis_name="test")
    # np.ndarray は .tolist() 済みなので JSON シリアライズ可能なはず
    payload = json.dumps(result)
    restored = json.loads(payload)
    assert "X" in restored
    assert "curve" in restored["X"]
    assert "scalar" in restored["X"]


def test_race_date_dtype_normalization() -> None:
    """REVIEW C12: race_date が date object / object dtype / datetime64[ns] のいずれでも AttributeError 起こさない。"""
    n = 500
    rng = np.random.default_rng(4)
    logit = rng.normal(0, 1, n)
    p = 1.0 / (1.0 + np.exp(-logit))
    y_true = (rng.random(n) < p).astype(int)

    base = datetime.date(2021, 1, 1)
    days = rng.integers(0, 365 * 3, size=n)
    date_objects = [base + datetime.timedelta(int(d)) for d in days]
    jyocd = rng.integers(5, 11, size=n)

    # 3パターンの dtype で year/month 軸が例外なく動くことを検証
    for race_date_values in [
        date_objects,  # Python date object list
        pd.Series(date_objects, dtype="object"),  # object dtype
        pd.to_datetime(pd.Series(date_objects)),  # datetime64[ns]
    ]:
        df = pd.DataFrame(
            {
                "race_date": race_date_values,
                "jyocd": jyocd,
                "p_fukusho_hit": p,
                "fukusho_hit": y_true,
            }
        )
        # year/month 軸だけ評価（race_date 正規化が効く）
        result = evaluate_all_segments(df, axes={"year": "race_date", "month": "race_date"})
        assert "year" in result
        assert "month" in result
        # 正規化された year/month が int でキー化されているはず
        for k in result["year"]:
            assert isinstance(k, str)
