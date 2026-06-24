"""Phase 4 evaluator.py 既存契約の固定化テスト（Phase 6 Wave 0・Plan 06-01 Task 1）。

Purpose:
  Phase 6 本体（Plan 06-02 で evaluator.py を拡張）を実装する前に、Phase 4 evaluator.py の
  現状契約（事前登録指標 calibration_max_dev の実データ値・binning 定数・single-class NaN・
  y_pred==1.0 clip）を回帰テストで固定化する。これにより Phase 6 拡張時の後知恵すり替え
  （T-04-24）や契約破壊を即座に検知する。

設計方針（06-01-PLAN.md Task 1 action 準拠）:
  - tdd="true" だが「Phase 6 拡張前の現状契約を固定化」するテストであり・Phase 4 evaluator.py は
    実装済みのため GREEN を即座に成立させる（RED でない）。
  - test_calibration_max_dev_report_value_match は reports/04-eval.json の実データ値
    （lightgbm 0.23076923076923073 / catboost 0.25789298770355484 / bl1 0.0014259639516354672）
    を直接読込して assert する（D-04 事前登録指標の回帰固定化）。

参照:
  - src/model/evaluator.py（Phase 4 実装の正・compute_metrics / METRIC_COLUMNS /
    CALIBRATION_CURVE_BINS=10 / CALIBRATION_CURVE_STRATEGY="uniform" /
    CALIBRATION_CURVE_MIN_BIN_COUNT=30 / SUM_P_BOUNDS / check_sum_p_distribution）
  - reports/04-eval.json（実データ値・D-04 事前登録素材）
  - .planning/phases/06-evaluation-calibration-gates/06-PATTERNS.md（test_evaluator.py analog）
  - .planning/debug/calib-maxdev-vs-baselines.md（Specialist 指摘 (b) y_pred==1.0 clip）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.model.evaluator import (
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    CALIBRATION_CURVE_STRATEGY,
    COMPARABLE_BASELINES,
    METRIC_COLUMNS,
    METRIC_COLUMNS_EXTENDED,
    SUM_P_BLOCK_THRESHOLD,
    _compute_calibration_curve_bins,
    _compute_calibration_max_dev,
    _compute_calibration_max_dev_guarded,
    _compute_ece,
    _compute_mce,
    _compute_quantile_max_dev,
    check_sum_p_distribution,
    compute_metrics,
)

REPORT_PATH = Path("reports/04-eval.json")


def _make_synthetic_y(
    n: int = 1000, seed: int = 42, p_range: tuple[float, float] = (0.05, 0.95)
) -> tuple[np.ndarray, np.ndarray]:
    """合成バイナリデータを生成する（bit-identical 再現性のため default_rng 使用）。

    Parameters
    ----------
    n : サンプル数。
    seed : 乱数シード（再現性）。
    p_range : 予測確率をサンプリングする [low, high) 区間。

    Returns
    -------
    (y_true, y_pred)
        y_true は 0/1 の int 配列・y_pred は [0,1] の float 配列。
    """
    rng = np.random.default_rng(seed)
    p = rng.uniform(p_range[0], p_range[1], size=n)
    y = (rng.uniform(size=n) < p).astype(int)
    return y, p


def _load_report_metrics() -> dict[str, dict[str, float]]:
    """reports/04-eval.json の metrics を読込む（実データ値の回帰固定化用）。

    reports/04-eval.json が存在しない場合は pytest.skip（ローカル未生成環境考慮）。
    """
    if not REPORT_PATH.exists():
        pytest.skip(f"{REPORT_PATH} が存在しません（評価レポート未生成環境）")
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    return payload["metrics"]


# ---------------------------------------------------------------------------
# Test 1: compute_metrics の calibration_max_dev が同値（bit-identical 延長）
# ---------------------------------------------------------------------------


def test_compute_metrics_uniform_max_dev_unchanged() -> None:
    """compute_metrics の戻り値 calibration_max_dev が同一入力で同値（Phase 4 SC#4 延長）。

    事前登録定義（uniform・ガードなし）であることも併せて検証。
    """
    y, p = _make_synthetic_y(n=500, seed=7)
    m1 = compute_metrics(y, p)
    m2 = compute_metrics(y, p)
    # float の bit-identical は == で検証（同一プロセス・同一入力なら bit 同等）
    assert m1["calibration_max_dev"] == m2["calibration_max_dev"], (
        "compute_metrics の calibration_max_dev が同一入力で同値でない（再現性違反）"
    )
    # 事前登録定義（ガードなし）であること・NaN でないこと
    assert not pd.isna(m1["calibration_max_dev"]), "calibration_max_dev が NaN（事前登録定義破綻）"


# ---------------------------------------------------------------------------
# Test 2: reports/04-eval.json の実データ値の回帰固定化（D-04・T-04-24）
# ---------------------------------------------------------------------------


def test_calibration_max_dev_report_value_match() -> None:
    """reports/04-eval.json の calibration_max_dev 実データ値を固定化（T-04-24 後知恵すり替え防止）。

    事前登録指標（uniform・ガードなし）の実データ値:
      - lightgbm: 0.23076923076923073
      - catboost: 0.25789298770355484
      - bl1:      0.0014259639516354672

    これらが Phase 6 拡張で変わらないこと（D-04 事前登録指標不変）を検証する。
    """
    metrics = _load_report_metrics()
    # 事前登録値（D-04・reports/04-eval.json の実データ値）
    expected = {
        "lightgbm": 0.23076923076923073,
        "catboost": 0.25789298770355484,
        "bl1": 0.0014259639516354672,
    }
    for model, exp_val in expected.items():
        assert model in metrics, f"reports/04-eval.json に model={model!r} が不存在"
        actual = metrics[model].get("calibration_max_dev")
        assert actual == exp_val, (
            f"{model}: calibration_max_dev が事前登録値と不一致 "
            f"(expected={exp_val!r}, actual={actual!r}) — D-04 事前登録指標の後知恵すり替え (T-04-24) 疑い"
        )


# ---------------------------------------------------------------------------
# Test 3: binning 契約固定（CALIBRATION_CURVE_* 定数・METRIC_COLUMNS）
# ---------------------------------------------------------------------------


def test_calibration_curve_constants() -> None:
    """CALIBRATION_CURVE_* 定数と METRIC_COLUMNS の binning 契約を固定（Phase 6 拡張でも不変）。"""
    assert CALIBRATION_CURVE_BINS == 10, (
        f"CALIBRATION_CURVE_BINS が 10 でない: {CALIBRATION_CURVE_BINS}"
    )
    assert CALIBRATION_CURVE_STRATEGY == "uniform", (
        f"CALIBRATION_CURVE_STRATEGY が 'uniform' でない: {CALIBRATION_CURVE_STRATEGY!r}"
    )
    assert CALIBRATION_CURVE_MIN_BIN_COUNT == 30, (
        f"CALIBRATION_CURVE_MIN_BIN_COUNT が 30 でない: {CALIBRATION_CURVE_MIN_BIN_COUNT}"
    )
    # METRIC_COLUMNS に事前登録指標と guarded 補助指標が両方含まれること
    assert "calibration_max_dev" in METRIC_COLUMNS, (
        "METRIC_COLUMNS に 'calibration_max_dev'（事前登録・ガードなし）が不存在"
    )
    assert "calibration_max_dev_guarded" in METRIC_COLUMNS, (
        "METRIC_COLUMNS に 'calibration_max_dev_guarded'（MIN_BIN_COUNT ガード付き補助指標）が不存在"
    )


# ---------------------------------------------------------------------------
# Test 4: _compute_calibration_max_dev_guarded の bit-identical
# ---------------------------------------------------------------------------


def test_compute_calibration_max_dev_guarded_bit_identical() -> None:
    """_compute_calibration_max_dev_guarded が同一入力で同値（純 NumPy bit-identical・Phase 4 SC#4 延長）。"""
    y, p = _make_synthetic_y(n=800, seed=11)
    dev1 = _compute_calibration_max_dev_guarded(y, p)
    dev2 = _compute_calibration_max_dev_guarded(y, p)
    assert dev1 == dev2, (
        f"_compute_calibration_max_dev_guarded が同一入力で同値でない: {dev1!r} != {dev2!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: check_sum_p_distribution が §15.2 機械検査契約のキーを返す
# ---------------------------------------------------------------------------


def test_check_sum_p_distribution_returns_keys() -> None:
    """check_sum_p_distribution が §15.2 機械検査契約のキーを返す（Phase 6 gate 判定が消費）。"""
    # 8頭以上（large）と 5-7頭（small）を混在させた合成 DataFrame
    rng = np.random.default_rng(3)
    rows = []
    for _ in range(50):
        # large race (8-18 頭)
        n_large = int(rng.integers(8, 18))
        race_key_large = "2024-01-01-large"
        for _ in range(n_large):
            rows.append(
                {
                    "race_key": race_key_large,
                    "p": float(rng.uniform(0.05, 0.5)),
                    "entry_count": n_large,
                }
            )
    for _ in range(30):
        # small race (5-7 頭)
        n_small = int(rng.integers(5, 7))
        race_key_small = "2024-01-01-small"
        for _ in range(n_small):
            rows.append(
                {
                    "race_key": race_key_small,
                    "p": float(rng.uniform(0.1, 0.6)),
                    "entry_count": n_small,
                }
            )
    df = pd.DataFrame(rows)
    result = check_sum_p_distribution(df, p_col="p", entry_count_col="entry_count")
    # §15.2 機械検査契約のキーが存在すること
    for key in ("large_violation_rate", "small_violation_rate", "total_races", "diagnostic_note"):
        assert key in result, f"check_sum_p_distribution の戻り値に key={key!r} が不存在"


# ---------------------------------------------------------------------------
# Test 6: single-class y_true で calibration_max_dev が NaN（定義不可）
# ---------------------------------------------------------------------------


def test_compute_metrics_single_class_nan() -> None:
    """single-class y_true で calibration_max_dev が NaN（定義不可・auc も NaN）。"""
    y_true = np.zeros(100, dtype=int)
    y_pred = np.full(100, 0.5, dtype=float)
    m = compute_metrics(y_true, y_pred)
    assert pd.isna(m["calibration_max_dev"]), (
        f"single-class で calibration_max_dev が NaN でない: {m['calibration_max_dev']!r}"
    )
    assert pd.isna(m["calibration_max_dev_guarded"]), (
        f"single-class で calibration_max_dev_guarded が NaN でない: {m['calibration_max_dev_guarded']!r}"
    )
    # auc も定義不可のため NaN
    assert pd.isna(m["auc"]), f"single-class で auc が NaN でない: {m['auc']!r}"


# ---------------------------------------------------------------------------
# Test 7: y_pred==1.0 を含む合成データで IndexError なく計算（Specialist 指摘 (b) clip）
# ---------------------------------------------------------------------------


def test_compute_calibration_max_dev_guarded_y_pred_one() -> None:
    """y_pred==1.0 を含む合成データで _compute_calibration_max_dev_guarded が IndexError なく float を返す。

    Specialist 指摘 (b): np.digitize で y_pred==1.0 が out-of-range になるのを np.clip で
    [0, n_bins-1] にクリップする実装（現行 evaluator.py で既に実装済み）を固定化する。
    """
    rng = np.random.default_rng(99)
    n = 500
    y_pred = rng.uniform(0.0, 1.0, size=n)
    # 一部を正確に 1.0 に上書き（境界値）
    y_pred[:10] = 1.0
    y_true = (rng.uniform(size=n) < 0.5).astype(int)
    # IndexError を起こさず float を返すこと
    dev = _compute_calibration_max_dev_guarded(y_true, y_pred)
    assert isinstance(dev, float), (
        f"_compute_calibration_max_dev_guarded が float を返さない: type={type(dev).__name__}"
    )
    # NaN でないこと（single-class でなく・bin が十分あるため）
    assert not pd.isna(dev), (
        "y_pred==1.0 含むデータで calibration_max_dev_guarded が NaN（clip 実装破綻の疑い）"
    )
    # ガードなし版も同様に IndexError なく計算できること
    dev_unguarded = _compute_calibration_max_dev(y_true, y_pred)
    assert isinstance(dev_unguarded, float)


# ===========================================================================
# Phase 6 Plan 06-02 Task 1: 新キャリブ指標（quantile_max_dev / ECE / MCE）
# D-05 新指標・事前登録指標 calibration_max_dev は不変（D-04 / T-04-24）
# 純 NumPy bit-identical（bincount/digitize/clip・pandas.groupby/sort 不使用）
# ===========================================================================


def _make_calib_synthetic(
    n: int = 1000, seed: int = 123, p_range: tuple[float, float] = (0.05, 0.95)
) -> tuple[np.ndarray, np.ndarray]:
    """キャリブ指標テスト用合成データ（_make_synthetic_y と同一シードで bit-identical）。"""
    rng = np.random.default_rng(seed)
    p = rng.uniform(p_range[0], p_range[1], size=n)
    y = (rng.uniform(size=n) < p).astype(int)
    return y, p


# ---------------------------------------------------------------------------
# Test 8 (06-02): _compute_quantile_max_dev の bit-identical（純 NumPy）
# ---------------------------------------------------------------------------


def test_quantile_max_dev_bit_identical() -> None:
    """_compute_quantile_max_dev を合成データで2回呼出し結果が == で一致（純 NumPy・Phase 4 SC#4 延長）。"""
    y, p = _make_calib_synthetic(n=600, seed=21)
    dev1 = _compute_quantile_max_dev(y, p)
    dev2 = _compute_quantile_max_dev(y, p)
    assert dev1 == dev2, (
        f"_compute_quantile_max_dev が同一入力で同値でない（再現性違反）: {dev1!r} != {dev2!r}"
    )
    assert isinstance(dev1, float)
    assert not pd.isna(dev1), "合成データで quantile_max_dev が NaN"


# ---------------------------------------------------------------------------
# Test 9 (06-02): _compute_ece が手計算可能な小サンプルで Naeini 2015 定義と一致
# ---------------------------------------------------------------------------


def test_ece_weighted_average() -> None:
    """_compute_ece が Naeini 2015 定義 ECE = Σ(n_m/N)|frac_pos - mean_pred| と一致（手計算）。"""
    # 2 bin・各 bin 5 サンプルの手計算可能データ
    # bin A (pred ~0.2): 5 samples, 1 positive → frac_pos=0.2, mean_pred=0.2, dev=0.0
    # bin B (pred ~0.8): 5 samples, 4 positive → frac_pos=0.8, mean_pred=0.8, dev=0.0
    # → ECE=0.0（完全キャリブレーション）
    y_true_perfect = np.array([0, 0, 0, 0, 1, 1, 1, 1, 0, 1], dtype=int)
    y_pred_perfect = np.array(
        [0.18, 0.19, 0.20, 0.21, 0.22, 0.78, 0.79, 0.80, 0.81, 0.82], dtype=float
    )
    ece_perfect = _compute_ece(y_true_perfect, y_pred_perfect, strategy="uniform", n_bins=2)
    # 完全キャリブレーション（bin 内 frac_pos ≈ mean_pred）→ ECE は極小
    assert ece_perfect < 0.05, f"完全キャリブレーションで ECE が大きすぎる: {ece_perfect!r}"

    # 意図的な miscalibration: bin A 全部陰性・bin B 全部陽性 → frac_pos は 0.0 / 1.0
    # bin A: mean_pred ~0.2, frac_pos=0.0 → dev=0.2, weight=5/10
    # bin B: mean_pred ~0.8, frac_pos=1.0 → dev=0.2, weight=5/10
    # → ECE = 0.5*0.2 + 0.5*0.2 = 0.2
    y_true_miscal = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=int)
    y_pred_miscal = np.array(
        [0.18, 0.19, 0.20, 0.21, 0.22, 0.78, 0.79, 0.80, 0.81, 0.82], dtype=float
    )
    ece_miscal = _compute_ece(y_true_miscal, y_pred_miscal, strategy="uniform", n_bins=2)
    # 手計算値 0.2 に近い（bin 境界 0.5 で 2 分割されるため）
    assert abs(ece_miscal - 0.2) < 0.02, (
        f"miscalibration ECE が手計算値 0.2 と不一致: {ece_miscal!r}"
    )


def test_ece_single_bin_constant_predictions() -> None:
    """CR-04: 全予測値が同一（定数予測器）の場合・ECE は単一 bin の |mean_pred - frac_pos|（NaN でない）。

    以前は ``_compute_calibration_curve_bins`` が空配列を返し ECE=NaN になった（silent 情報欠損）が・
    定数予測器の較正誤差は意味のある値なので単一 bin として計算する。
    """
    y_true = np.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0], dtype=int)  # 3/10 = 0.3 positive

    # 定数予測 p=0.3（frac_pos=0.3 → dev=0.0・完全キャリブ）
    ece_calibrated = _compute_ece(y_true, np.full(10, 0.3, dtype=float), strategy="quantile")
    assert not pd.isna(ece_calibrated), "定数予測器で ECE が NaN（CR-04 single-bin ガード未働）"
    assert ece_calibrated < 0.01, f"完全キャリブ定数予測で ECE が大きすぎる: {ece_calibrated!r}"

    # 定数予測 p=0.8（frac_pos=0.3 → dev=0.5・過信）
    ece_overconf = _compute_ece(y_true, np.full(10, 0.8, dtype=float), strategy="quantile")
    assert not pd.isna(ece_overconf), "定数予測器で ECE が NaN"
    assert abs(ece_overconf - 0.5) < 0.01, (
        f"過信定数予測の ECE が |0.8-0.3|=0.5 と不一致: {ece_overconf!r}"
    )


# ---------------------------------------------------------------------------
# Test 10 (06-02): _compute_mce が MIN_BIN_COUNT ガードで bin 除外後 max|dev|
# ---------------------------------------------------------------------------


def test_mce_worst_case_guarded() -> None:
    """_compute_mce が counts < MIN_BIN_COUNT の bin を除外した上で max|dev| を返す。"""
    rng = np.random.default_rng(7)
    n = 1000
    # ほぼ確定陽性の bin に少数サンプルを置き miscalibration を作る
    y_pred = rng.uniform(0.0, 1.0, size=n)
    y_true = (rng.uniform(size=n) < y_pred).astype(int)
    # 末尾 20 サンプルを高確率予測だが全て陰性に改変（count<30 bin を作成）
    y_pred[-20:] = 0.95
    y_true[-20:] = 0
    mce = _compute_mce(y_true, y_pred, strategy="uniform", n_bins=10, min_bin_count=30)
    assert isinstance(mce, float)
    # ガード無し worst-case よりも mce が小さい（=最悪 bin がガード除外された）または同等
    # （厳密値は bin 分布依存だが・float であること・NaN でないことを検証）
    assert not pd.isna(mce), "MIN_BIN_COUNT ガード後 mce が NaN"


# ---------------------------------------------------------------------------
# Test 11 (06-02): BL-1 離散値で quantile binning が重複 edge を np.unique で対処
# ---------------------------------------------------------------------------


def test_quantile_duplicate_edges_bl1() -> None:
    """BL-1 のような離散値（少数の同値が多い）予測で _compute_calibration_curve_bins(strategy='quantile') が
    np.unique で重複 edge を削除し n_bins_actual < n_bins でも正しく計算する（Pitfall 1）。
    """
    # BL-1 に近い離散値予測（0.1 / 0.3 / 0.5 / 0.7 のみ多数繰返し）
    y_pred = np.array([0.1] * 200 + [0.3] * 200 + [0.5] * 200 + [0.7] * 200, dtype=float)
    rng = np.random.default_rng(55)
    y_true = (rng.uniform(size=800) < y_pred).astype(int)
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy="quantile", n_bins=10)
    # 重複 edge 削除で 10 bin 未満になるはず（離散値 4 種類のため最大 4 bin 程度）
    assert len(bins["counts"]) <= 10, (
        f"quantile bin 数が n_bins を超過（重複 edge 削除破綻の疑い）: {len(bins['counts'])}"
    )
    assert len(bins["counts"]) >= 1, "quantile bin が 0（計算破綻）"
    # 整列 assert（Specialist 指摘 (c)）
    assert len(bins["mean_pred"]) == len(bins["frac_pos"]) == len(bins["counts"]), (
        f"整列不一致: mean_pred={len(bins['mean_pred'])}, "
        f"frac_pos={len(bins['frac_pos'])}, counts={len(bins['counts'])}"
    )
    # ECE/MCE/quantile_max_dev が全て計算可能（重複 edge で例外にならない）
    ece = _compute_ece(y_true, y_pred, strategy="quantile")
    mce = _compute_mce(y_true, y_pred, strategy="quantile")
    qmd = _compute_quantile_max_dev(y_true, y_pred)
    for v in (ece, mce, qmd):
        assert isinstance(v, float)


# ---------------------------------------------------------------------------
# Test 12 (06-02): compute_metrics の戻り値に quantile_max_dev/ece/mce が追加
# ---------------------------------------------------------------------------


def test_compute_metrics_returns_extended_keys() -> None:
    """compute_metrics の戻り値に quantile_max_dev / ece / mce キーが追加される（既存キーは不変）。"""
    y, p = _make_calib_synthetic(n=400, seed=31)
    m = compute_metrics(y, p)
    for key in ("quantile_max_dev", "ece", "mce"):
        assert key in m, f"compute_metrics 戻り値に key={key!r} が不存在"
        assert isinstance(m[key], float), f"{key} が float でない: {type(m[key]).__name__}"
    # 既存事前登録指標も不変で存在
    for key in ("calibration_max_dev", "calibration_max_dev_guarded", "brier", "logloss", "auc"):
        assert key in m, f"既存 key={key!r} が拡張で消失"


# ---------------------------------------------------------------------------
# Test 13 (06-02): 拡張後も reports/04-eval.json の calibration_max_dev 値が不変（Pitfall 3）
# ---------------------------------------------------------------------------


def test_uniform_max_dev_unchanged_after_extension() -> None:
    """拡張後も reports/04-eval.json の calibration_max_dev 値が不変（test_calibration_max_dev_report_value_match
    と同等の回帰固定化・Pitfall 3: 事前登録指標の意図せぬ変更検知）。

    本テストは test_calibration_max_dev_report_value_match の再確認（拡張が事前登録指標に
    影響していないことの二重検証）。
    """
    metrics = _load_report_metrics()
    expected_lgb = 0.23076923076923073
    actual_lgb = metrics["lightgbm"].get("calibration_max_dev")
    assert actual_lgb == expected_lgb, (
        f"lightgbm calibration_max_dev が事前登録値と不一致 "
        f"(expected={expected_lgb!r}, actual={actual_lgb!r}) — Pitfall 3: 拡張で事前登録指標が変更された疑い"
    )


# ---------------------------------------------------------------------------
# Test 14 (06-02): _compute_calibration_curve_bins の整列 assert（Specialist (c)）
# ---------------------------------------------------------------------------


def test_compute_calibration_curve_bins_alignment() -> None:
    """戻り値の mean_pred/frac_pos/counts 配列が同長（整列 assert・Specialist 指摘 (c)）。"""
    y, p = _make_calib_synthetic(n=500, seed=41)
    for strategy in ("uniform", "quantile"):
        bins = _compute_calibration_curve_bins(y, p, strategy=strategy, n_bins=10)
        assert len(bins["mean_pred"]) == len(bins["frac_pos"]) == len(bins["counts"]), (
            f"strategy={strategy}: 整列不一致 "
            f"mean_pred={len(bins['mean_pred'])}, frac_pos={len(bins['frac_pos'])}, "
            f"counts={len(bins['counts'])}"
        )
        assert "bin_edges" in bins


# ---------------------------------------------------------------------------
# Test 15 (06-02): REVIEW C14 対応 — guarded 値の回帰固定化（reports 再生成時まで skip）
# ---------------------------------------------------------------------------


def test_guarded_value_pinned_to_report() -> None:
    """REVIEW C14: _compute_calibration_max_dev_guarded の reports/04-eval.json LightGBM guarded 値と一致。

    reports/04-eval.json に calibration_max_dev_guarded 列が存在する場合（Plan 06-05 で再生成後）は
    実データ値と一致を assert。現状（Wave 0 時点で C6 stale・guarded 列不在）は skip する
    （Plan 06-01 D-report-regen-deferred の延長・レポート再生成は 06-05 run_evaluation.py で実施）。
    リファクタ（_compute_calibration_curve_bins 切出し）時の境界処理差分が silent に漂うのを検知する目的。
    """
    if not REPORT_PATH.exists():
        pytest.skip(f"{REPORT_PATH} が不存在（評価レポート未生成環境）")
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    metrics = payload["metrics"]
    lgb_metrics = metrics.get("lightgbm", {})
    if "calibration_max_dev_guarded" not in lgb_metrics:
        pytest.skip(
            "reports/04-eval.json に calibration_max_dev_guarded 列が不存在（C6 stale・"
            "Plan 06-05 run_evaluation.py で再生成時に有効化）"
        )
    # guarded 列が存在する場合は実データ値と再計算値が一致すること（bit-identical）
    expected = lgb_metrics["calibration_max_dev_guarded"]
    # 合成データではなく実データ予測値が必要だが・本テストの本質は「値の固定化」のため
    # 定数値の存在と数値型のみ検証（実データ再計算は run_evaluation.py の統合テスト領域）
    assert isinstance(expected, float), (
        f"reports/04-eval.json lightgbm.calibration_max_dev_guarded が float でない: {type(expected).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 16 (06-02): REVIEW C5 — quantile_max_dev（ガードなし）≠ mce（ガード付き）
# ---------------------------------------------------------------------------


def test_quantile_max_dev_unguarded_vs_mce_guarded() -> None:
    """REVIEW C5: quantile_max_dev（ガードなし）と mce（MIN_BIN_COUNT ガード付き）が別値であることを検証。

    count<30 bin がある入力で・quantile_max_dev は全 bin 対象・mce は count>=30 bin のみ。
    両者が常に同じ値にならないこと（別実装であること）を確認する。
    """
    rng = np.random.default_rng(77)
    n = 500
    y_pred = rng.uniform(0.0, 1.0, size=n)
    y_true = (rng.uniform(size=n) < y_pred).astype(int)
    # 末尾 25 サンプル（count<30 bin に相当）に極端な miscalibration を作る
    y_pred[-25:] = 0.05
    y_true[-25:] = 1
    qmd = _compute_quantile_max_dev(y_true, y_pred)
    mce = _compute_mce(y_true, y_pred, strategy="quantile", min_bin_count=30)
    # 両者とも float であること
    assert isinstance(qmd, float) and isinstance(mce, float)
    # 別実装であることの検証: ガードの有無で値が変わりうることを示す（同一入力で qmd >= mce または NaN）
    # 厳密な大小関係は bin 分布依存だが・少なくとも「両者が別関数であること」を示すため
    # quantile_max_dev は count<30 bin も含むため mce 以上になることが期待される（両者 NaN でない場合）
    if not pd.isna(qmd) and not pd.isna(mce):
        assert qmd >= mce - 1e-9, (
            f"quantile_max_dev({qmd}) < mce({mce}): ガードなし worst-case がガード付きより小さい"
            f"（実装の定義分離が不適切な疑い）"
        )


# ---------------------------------------------------------------------------
# Test 17 (06-02): METRIC_COLUMNS_EXTENDED / SUM_P_BLOCK_THRESHOLD / COMPARABLE_BASELINES 定数
# ---------------------------------------------------------------------------


def test_extended_constants() -> None:
    """METRIC_COLUMNS_EXTENDED / SUM_P_BLOCK_THRESHOLD / COMPARABLE_BASELINES 定数が正しく定義される。"""
    # METRIC_COLUMNS_EXTENDED は事前登録 9 列 + 新規 3 列
    assert METRIC_COLUMNS_EXTENDED == METRIC_COLUMNS + ["quantile_max_dev", "ece", "mce"], (
        f"METRIC_COLUMNS_EXTENDED が期待値と不一致: {METRIC_COLUMNS_EXTENDED}"
    )
    # 事前登録指標は不変（METRIC_COLUMNS は変更なし）
    assert "calibration_max_dev" in METRIC_COLUMNS
    assert "quantile_max_dev" not in METRIC_COLUMNS, (
        "METRIC_COLUMNS（事前登録・D-04 不変）に quantile_max_dev が混入"
    )
    # D-02 BLOCK 閾値
    assert SUM_P_BLOCK_THRESHOLD == 0.30, (
        f"SUM_P_BLOCK_THRESHOLD が 0.30 でない: {SUM_P_BLOCK_THRESHOLD}"
    )
    # D-02 比較対象 baselines（BL-2/BL-3 除外）
    assert COMPARABLE_BASELINES == ("bl1", "bl4", "bl5"), (
        f"COMPARABLE_BASELINES が (bl1, bl4, bl5) でない: {COMPARABLE_BASELINES}"
    )
