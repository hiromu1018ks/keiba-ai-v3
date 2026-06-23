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
    METRIC_COLUMNS,
    _compute_calibration_max_dev,
    _compute_calibration_max_dev_guarded,
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
    assert CALIBRATION_CURVE_BINS == 10, f"CALIBRATION_CURVE_BINS が 10 でない: {CALIBRATION_CURVE_BINS}"
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
            rows.append({"race_key": race_key_large, "p": float(rng.uniform(0.05, 0.5)), "entry_count": n_large})
    for _ in range(30):
        # small race (5-7 頭)
        n_small = int(rng.integers(5, 7))
        race_key_small = "2024-01-01-small"
        for _ in range(n_small):
            rows.append({"race_key": race_key_small, "p": float(rng.uniform(0.1, 0.6)), "entry_count": n_small})
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
