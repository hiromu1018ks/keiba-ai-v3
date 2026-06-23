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
from pathlib import Path

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
    render_segment_curves_html,
    write_segment_reports,
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


# ---------------------------------------------------------------------------
# 合成 segment_results ヘルパ（Task 2）
# ---------------------------------------------------------------------------


def _make_synthetic_segment_results(n_seg: int = 2, seed: int = 5) -> dict[str, dict]:
    """evaluate_segment_axis 相当の合成 segment_results を生成（Task 2 render/write テスト用）。"""
    rng = np.random.default_rng(seed)
    results: dict[str, dict] = {}
    for i in range(n_seg):
        m = 200
        logit = rng.normal(0, 1, m) + i * 0.3
        y_pred = np.clip(1.0 / (1.0 + np.exp(-logit)), 0.02, 0.98)
        y_true = (rng.random(m) < y_pred).astype(int)
        # evaluator binning で curve 構築
        bins = _compute_calibration_curve_bins(
            y_true, y_pred, strategy="uniform", n_bins=CALIBRATION_CURVE_BINS
        )
        results[f"seg{i}"] = {
            "curve": {
                "mean_pred": bins["mean_pred"].tolist(),
                "frac_pos": bins["frac_pos"].tolist(),
                "count": bins["counts"].astype(int).tolist(),
            },
            "scalar": {
                "ece_quantile": 0.05,
                "ece_uniform": 0.07,
                "mce_guarded": 0.12,
                "max_dev_guarded": 0.15,
                "n_samples": m,
            },
        }
    return results


# ---------------------------------------------------------------------------
# Task 2: render_segment_curves_html / write_segment_reports
# ---------------------------------------------------------------------------


def test_render_segment_curves_html_self_contained(tmp_path: Path) -> None:
    """REVIEW C13 cycle-2: HTML に Plotly.newPlot と <script src="plotly.min.js"> 共有参照が含まれる。"""
    seg_results = _make_synthetic_segment_results(n_seg=2, seed=5)
    out = tmp_path / "test_axis.html"
    result = render_segment_curves_html(seg_results, axis_name="test", out_path=out)
    assert result == out
    html = out.read_text(encoding="utf-8")
    # Plotly の描画呼出しが存在
    assert "Plotly.newPlot" in html
    # REVIEW C13 cycle-2: include_plotlyjs='directory' で plotly.min.js を共有参照
    assert 'src="plotly.min.js"' in html or "plotly.min.js" in html
    # 同じディレクトリに plotly.min.js が生成されている（directory モード）
    plotly_js = tmp_path / "plotly.min.js"
    assert plotly_js.exists(), f"plotly.min.js が {tmp_path} に生成されるべき（directory モード）"


def test_render_segment_curves_html_has_perfect_line(tmp_path: Path) -> None:
    """HTML に完全キャリブ対角線（perfect・dash・gray）の trace が含まれる。"""
    seg_results = _make_synthetic_segment_results(n_seg=1, seed=6)
    out = tmp_path / "perfect.html"
    render_segment_curves_html(seg_results, axis_name="axis", out_path=out)
    html = out.read_text(encoding="utf-8")
    assert "perfect" in html


def test_render_segment_curves_html_has_segment_traces(tmp_path: Path) -> None:
    """segment 値の数だけ trace が追加される（合成2 segment 値で3 trace = perfect + 2 segment）。"""
    seg_results = _make_synthetic_segment_results(n_seg=2, seed=7)
    out = tmp_path / "traces.html"
    render_segment_curves_html(seg_results, axis_name="axis", out_path=out)
    html = out.read_text(encoding="utf-8")
    # trace 数は直接カウント困難だが・各 segment 値の name が含まれることを検証
    assert "axis=seg0" in html
    assert "axis=seg1" in html
    assert "perfect" in html


def test_write_segment_reports_creates_files(tmp_path: Path) -> None:
    """write_segment_reports が6軸 × {json,html} + plotly.min.js の計13ファイルを生成。"""
    df = _make_synthetic_segment_df(n=2000, seed=42)
    all_results = evaluate_all_segments(df)
    paths = write_segment_reports(all_results, out_dir=tmp_path)

    # 6軸 + plotly_min_js
    expected_axes = set(SEGMENT_AXES.keys())
    actual_axes = {k for k in paths.keys() if k != "plotly_min_js"}
    assert actual_axes == expected_axes

    # 各軸の json と html ファイルが存在
    for axis_name in expected_axes:
        json_path = paths[axis_name]["json"]
        html_path = paths[axis_name]["html"]
        assert json_path.exists(), f"{axis_name}.json が存在しない"
        assert html_path.exists(), f"{axis_name}.html が存在しない"
        assert json_path.name == f"{axis_name}.json"
        assert html_path.name == f"{axis_name}.html"

    # 共有 plotly.min.js が1ファイル存在
    plotly_js = paths["plotly_min_js"]
    assert plotly_js.exists(), "plotly.min.js が存在しない（directory 共有参照）"


def test_write_segment_reports_json_schema(tmp_path: Path) -> None:
    """生成された JSON が {axis_name, segments: [{segment_value, curve, scalar}]} スキーマに準拠。"""
    seg_results = _make_synthetic_segment_results(n_seg=2, seed=8)
    all_results = {"jyocd": seg_results}
    paths = write_segment_reports(all_results, out_dir=tmp_path)

    json_path = paths["jyocd"]["json"]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["axis_name"] == "jyocd"
    assert isinstance(payload["segments"], list)
    assert len(payload["segments"]) == 2
    for seg in payload["segments"]:
        assert "segment_value" in seg
        assert "curve" in seg
        assert "scalar" in seg
        assert set(seg["curve"].keys()) == {"mean_pred", "frac_pos", "count"}
        assert "n_samples" in seg["scalar"]


def test_write_segment_reports_json_byte_reproducible(tmp_path: Path) -> None:
    """同じ入力で2回生成した JSON が byte-identical（sort_keys=True・_atomic_write_text）。"""
    seg_results = _make_synthetic_segment_results(n_seg=2, seed=9)
    all_results = {"year": seg_results}

    # 1回目
    write_segment_reports(all_results, out_dir=tmp_path / "run1")
    # 2回目（別ディレクトリ）
    write_segment_reports(all_results, out_dir=tmp_path / "run2")

    json1 = (tmp_path / "run1" / "year.json").read_text(encoding="utf-8")
    json2 = (tmp_path / "run2" / "year.json").read_text(encoding="utf-8")
    assert json1 == json2, "JSON が byte-reproducible でない（sort_keys=True 違反の可能性）"


def test_render_segment_curves_html_byte_reproducible(tmp_path: Path) -> None:
    """§19.1 再現性: 同じ入力で2回生成した HTML が byte-identical。

    Plotly 既定は `<div id="random-uuid">` を吐くため非決定的 → div_id を axis 固定値にして
    byte-reproducible 化（tracked 報告書の regeneration churn 防止）。
    """
    seg_results = _make_synthetic_segment_results(n_seg=2, seed=9)

    html1 = render_segment_curves_html(
        seg_results, axis_name="year", out_path=tmp_path / "run1.html"
    )
    html2 = render_segment_curves_html(
        seg_results, axis_name="year", out_path=tmp_path / "run2.html"
    )
    content1 = html1.read_text(encoding="utf-8")
    content2 = html2.read_text(encoding="utf-8")
    assert content1 == content2, (
        "HTML が byte-reproducible でない（Plotly div_id の random uuid が残っている可能性）"
    )
    # div_id が決定論的値（segment-{axis}）に固定されていることを確認
    assert 'id="segment-year"' in content1, "div_id が 'segment-year' に固定されていない"


def test_plotly_min_js_shared_single_file(tmp_path: Path) -> None:
    """REVIEW C13 cycle-2: 6軸 HTML が全て同じ plotly.min.js を共有参照・plotly.min.js は1ファイルのみ。"""
    df = _make_synthetic_segment_df(n=2000, seed=42)
    all_results = evaluate_all_segments(df)
    write_segment_reports(all_results, out_dir=tmp_path)

    # plotly.min.js は reports/06-segments/ 直下に1ファイルのみ
    plotly_js_files = list(tmp_path.glob("plotly.min.js"))
    assert len(plotly_js_files) == 1, (
        f"plotly.min.js は1ファイルのみ想定・{len(plotly_js_files)} ファイル存在"
    )

    # 6 HTML が全て plotly.min.js を参照している（include_plotlyjs='directory'）
    html_files = sorted(tmp_path.glob("*.html"))
    # 欠損軸で空 dict の場合 HTML は生成されるが trace は perfect のみ
    ref_count = 0
    for html_file in html_files:
        html = html_file.read_text(encoding="utf-8")
        if 'src="plotly.min.js"' in html:
            ref_count += 1
    assert ref_count == len(html_files), (
        f"全 HTML ({len(html_files)}) が plotly.min.js を参照すべき・実際 {ref_count}"
    )
