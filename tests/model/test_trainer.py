"""Phase 4 SC#3/MODL-03 検証契約 (Wave 0 RED stub).

後続 PLAN 03 (trainer.py) が本 stub を GREEN 化する:
- SC#3: LightGBM native categorical (非負 code・NaN→-1 禁止・target encoding 禁止)
- SC#3: CatBoost has_time=True (random permutation 無効化) + Pool は race_start_datetime sort
- SC#3 leak diagnostic: 合成希少カテゴリ RARE_X で target encoding 非混入を実証
- D-04: early stopping eval set が calib/test と完全に disjoint

参考: 04-RESEARCH.md D-03/D-04/D-05/D-09 確定事項 / CLAUDE.md §14.3/§14.4.
"""

from __future__ import annotations

import pytest


def test_lightgbm_nonneg_codes():
    """SC#3: LightGBM category dtype の code が非負 (NaN→-1 ハザード回避・§14.3).

    pandas category が NaN を code -1 にする問題を __MISSING__ sentinel で回避.
    低基数 string 列 (sexcd/class_code_normalized/estimated_running_style/rolling_jyocd_*) の
    .cat.codes.min() >= 0 を assert.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_catboost_has_time():
    """SC#3: CatBoostClassifier が has_time=True・Pool は race_start_datetime で sort (§14.4).

    has_time=True で random permutation を無効化し ordered TS が過去行のみ使用.
    高基数 ID _code 列 (jockey/trainer/sire/bms/horse) は astype(str) で文字列化し cat_features に含める
    (review HIGH#5・CatBoost の int cat 扱い問題を回避).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_no_target_encoding_leak():
    """SC#3 leak diagnostic: 合成希少カテゴリ RARE_X で予測が mean に縮む (target encoding 非混入).

    target encoding 混入なら予測が自身の label に過剰適合 (1.0 近く)・native categorical なら
    global mean (0.21 程度) に縮む. _build_intentional_leak_control で DEMONSTRABLY fail を実証
    (review HIGH#6・対抗的構造診断・live-data 証明と称さない).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_eval_set_disjoint_from_calib_test():
    """D-04: early stopping eval set が calib/test と完全に disjoint (Pitfall 5).

    eval set は train slice の時系列末尾から切り出し・set(eval_races).isdisjoint(calib_races)
    と .isdisjoint(test_races) を assert. eval_max(race_date) <= train_max < calib_min (Cross-Plan #8).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")
