"""Phase 4 MODL-02/SC#2 BL-1..5 検証契約 (Wave 0 RED stub).

後続 PLAN 03 (baseline.py) が本 stub を GREEN 化する:
- BL-1: 頭数別一定 (8頭以上 3/count・5-7頭 2/count)
- BL-2: 確定人気 (1/ninki レース内正規化・sum=払戻対象数)
- BL-3: 確定複勝オッズ逆数 (1/fukuoddslow レース内正規化・D-07)
- BL-4: LogisticRegression (少数特徴量)
- BL-5: LightGBM 最小特徴量 (rolling 除外)
- D-08: 市場データ源 (n_odds_tanpuku.fukuoddslow / n_uma_race.ninki)

参考: 04-RESEARCH.md D-07/D-08 確定事項 / §14.2 BL-1..5 定義.
"""

from __future__ import annotations

import pytest


def test_bl1_field_size_constant():
    """BL-1 頭数別一定確率: 8頭以上 3/sales_start_entry_count・5-7頭 2/count.

    label.fukusho_label.sales_start_entry_count と fukusho_payout_places から算出.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_bl2_ninki_normalized():
    """BL-2 確定人気由来: 1/ninki をレース内正規化して sum=払戻対象数 (D-07/D-08).

    n_uma_race.ninki (確定人気) を市場暗示確率として変換.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_bl3_fukuodds_inverse_normalized():
    """BL-3 確定複勝オッズ逆数: 1/fukuoddslow をレース内正規化 (D-07・§14.2 市場参照ベンチマーク).

    n_odds_tanpuku.fukuoddslow/high から算出. モデル特徴量には絶対混入しない (MODL-01 odds-free).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_bl4_logreg():
    """BL-4 LogisticRegression: sklearn LogisticRegression で少数基本特徴量 (barei/futan/umaban/wakuban/class_code_normalized) を学習.

    predict_proba で p_fukusho_hit を算出.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_bl5_min_lightgbm():
    """BL-5 LightGBM 最小特徴量: rolling 系統を除外した LightGBM 学習 (レース条件+馬情報中心).

    trainer.py の train_lightgbm を feature subset で呼出 → predict_proba → キャリブレーション.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")


def test_market_data_source():
    """D-08: n_odds_tanpuku.fukuoddslow (確定複勝オッズ) / n_uma_race.ninki (確定人気) が存在.

    市場コンセンサス最終値を確率品質ベンチマークの標準として使用. 歴史レース (val 2024 / test 2025-26) に存在.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 03")
