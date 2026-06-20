"""``backtest_load.load_backtest`` の統合テスト
（BACK-03 / §19.1 / RESEARCH §7.5）。

Wave 0 (Plan 05-01): RED stub。``src.db.backtest_load`` 未実装のため ImportError で RED。
Wave 2 plan が実装して GREEN 化する。

``@pytest.mark.requires_db`` + ``write_cur`` fixture で ``KEIBA_SKIP_DB_TESTS`` skip policy
を継承する（``tests/conftest.py`` 参照）。
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_backtest_df(backtest_id: str = "BT-1-30min_before-lightgbm") -> pd.DataFrame:
    """backtest 結果 DataFrame（1行）を構築する。"""
    return pd.DataFrame([{
        "backtest_id": backtest_id,
        "backtest_strategy_version": "fukusho_ev_v1",
        "odds_snapshot_policy": "30min_before",
        "train_period_start": pd.to_datetime("2019-06-01"),
        "train_period_end": pd.to_datetime("2022-12-31"),
        "test_period_start": pd.to_datetime("2023-01-01"),
        "test_period_end": pd.to_datetime("2023-12-31"),
        "model_type": "lightgbm",
        "model_version": "20260620-1a-postreview-v2-lg-v1",
        "feature_snapshot_id": "20260620-1a-postreview-v2",
        "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": "06",
        "racenum": 1, "umaban": 3, "kettonum": 123,
        "selected_flag": True,
        "stake": 100, "refund_flag": False, "refund_amount": 0,
        "payout_amount": 150, "profit": 50, "effective_stake": 100,
        "fukusho_hit_validated": 1,
        "recommend_rank": "S",
        "EV_lower": 1.25, "EV_upper": 1.60,
        "odds_snapshot_at": pd.to_datetime("2023-01-03 09:30:00"),
        "odds_source_type": "jodds_tanpuku",
        "odds_missing_reason": None,
        "race_date": pd.to_datetime("2023-01-03"),
    }])


@pytest.mark.requires_db
def test_backtest_load_idempotent(write_cur):
    """2回連続実行で checksum が bit-identical（staging-swap idempotent・§19.1）。"""
    from src.db.backtest_load import load_backtest

    df = _make_backtest_df()
    load_backtest(write_cur, df)
    load_backtest(write_cur, df)
    # 2回実行でも同一 backtest_id の行数が1行であることを検証（idempotent）
    write_cur.execute(
        "SELECT count(*) FROM backtest.fukusho_backtest WHERE backtest_id = %s",
        ("BT-1-30min_before-lightgbm",),
    )
    count = write_cur.fetchone()[0]
    assert count == 1, f"idempotent 違反: {count} 行（1行期待）"


@pytest.mark.requires_db
def test_backtest_load_scoped_swap(write_cur):
    """backtest_id A 書込後 B 書込で A が残る（backtest_id scoped swap・他 scope 行は保持）。"""
    from src.db.backtest_load import load_backtest

    df_a = _make_backtest_df("BT-1-30min_before-lightgbm")
    df_b = _make_backtest_df("BT-1-30min_before-catboost")
    load_backtest(write_cur, df_a)
    load_backtest(write_cur, df_b)
    # 両方の backtest_id が1行ずつ残っていることを検証
    write_cur.execute(
        "SELECT backtest_id, count(*) FROM backtest.fukusho_backtest "
        "WHERE backtest_id IN (%s, %s) GROUP BY backtest_id",
        ("BT-1-30min_before-lightgbm", "BT-1-30min_before-catboost"),
    )
    rows = dict(write_cur.fetchall())
    assert rows.get("BT-1-30min_before-lightgbm") == 1
    assert rows.get("BT-1-30min_before-catboost") == 1
