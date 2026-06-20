"""Phase 4 SC#4 検証契約 (Wave 0 RED stub).

後続 PLAN 02 (calibrator.py wrapper) が本 stub を GREEN 化する:
- SC#4: strict-later disjoint (max(train) < min(calib)) 違反で fit_prefit_calibrator が ValueError
- SC#4 smoke: seed=42 で2回 train_and_predict → np.array_equal(pred1, pred2) (bit-identical)
- §15.2: calib sample >=1000 で isotonic・<1000 で sigmoid

参考: src/utils/calibrator.py::fit_prefit_calibrator (既存・薄い wrapper)・
      04-RESEARCH.md D-06 確定事項 (固定 seed 全箇所リスト)・CLAUDE.md §15.2.
"""

from __future__ import annotations

import pytest


def test_strict_later_disjoint():
    """SC#4: max(train.race_date) < min(calib.race_date) 違反で fit_prefit_calibrator が ValueError.

    src/utils/calibrator.py が ValueError guard 内蔵済み・本テストは Phase 4 wrapper 経由で検証.
    look-ahead leak を構造防止 (§15.2).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")


def test_reproduce_bit_identical():
    """SC#4 reproduce smoke: seed=42 で2回 train_and_predict → np.array_equal(pred1, pred2).

    固定 seed 全箇所 (LightGBM: seed/deterministic/force_col_wise/bagging_seed/feature_fraction_seed/num_threads=1,
    CatBoost: random_seed/has_time/thread_count=1) + 固定 as_of_datetime (FIXED_REPRODUCE_TS).
    review HIGH#16 + Cycle 3 NEW HIGH-1.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02/05")


def test_isotonic_vs_sigmoid_threshold():
    """§15.2: calib sample >=1000 で isotonic・<1000 で sigmoid.

    CLAUDE.md §15.2 公式推奨 (isotonic は <1000 で過学習).
    Phase 4 推奨案 (D-02b) では calib sample = 24,884 > 1000 → isotonic 使用可.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")
