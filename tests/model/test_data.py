"""Phase 4 SC#1/MODL-01 検証契約 (Wave 0 RED stub).

後続 PLAN 02-03 (data.py) が本 stub を GREEN 化する:
- SC#1: stamped Parquet のみ学習 (live DB 非使用・feature 再計算禁止)
- raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2) のモデル入力除外
- feature allowlist 検査 (banned_features が空・odds-free 保証)
- BACK-01 前置: race_id 単位の train/calib/test 3way disjoint 分割

参考: 04-RESEARCH.md D-02b/D-03/D-05 確定事項 / 04-PATTERNS.md data.py セクション.
"""

from __future__ import annotations

import pytest


def test_load_from_parquet_only():
    """SC#1: load_feature_matrix は snapshots/feature_matrix_20260620-1a-postreview-v2.parquet のみ読込.

    live DB から feature を再計算しない (SC#1 不変・§19.1 再現性聖域).
    snapshot-id は D-01 で確定した postreview-v2 (feature_count=62, fa_version 0.3.0).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")


def test_raw_ids_excluded():
    """raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2) はモデル入力から除外.

    HIGH #5 COPY-NOT-RENAME で Parquet に保持されるが、モデル入力には混入しない (Pitfall 4).
    prepare_model_matrix がこれらの列を drop することを assert.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")


def test_no_banned_features():
    """feature allowlist 検査: assert_matrix_columns_registered で banned_features が空.

    D-07/§13.4 odds-free allowlist 保証. odds 系/当日情報系 feature がモデル入力に
    混入しないことを防御的 assert で検証 (SC#1 間接).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")


def test_race_id_disjoint_3way():
    """BACK-01 前置: 3way 分割で同一 race_id が train/calib/test を跨がない.

    D-02b 推奨案: train 2016-07..2023 / calib 2024-H1 / test 2024-H2 / 2025+ は Phase 5 BT 温存.
    race_id_time_series_split (race_id 単位・strict chronological) で分離することを assert.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 02")
