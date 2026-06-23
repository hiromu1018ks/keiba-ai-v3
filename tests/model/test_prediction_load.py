"""Phase 4 D-05 staging-swap idempotent 検証契約.

後続 PLAN 04 (prediction_load.py) が本 stub を GREEN 化する:
- D-05: _idempotent_load_prediction を2回実行で checksum 一致
  (advisory lock → CREATE staging INCLUDING ALL → TRUNCATE → executemany INSERT →
   SELECT count(*) verify → DELETE model_type+model_version scoped → INSERT (cols明示) →
   DROP staging)
- review HIGH#1 / Cross-Plan #3: model_version スコープ置換 (同一 model_type+model_version の行のみ
  DELETE → INSERT・他 model_type/version の行は保持) で全テーブル破壊を防止。
  lightgbm 実行後 catboost 実行が前者を削除する silent 履歴破壊を防止。

requires_db マーク付与: live DB 接続必須 (KEIBA_SKIP_DB_TESTS=1 で skip 可能).

参考: src/etl/fukusho_label.py::_idempotent_load_label パターン再利用・
      04-PATTERNS.md prediction_load.py セクション・
      04-04-PLAN.md Task 2 behavior/action.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from src.db.prediction_load import (
    PREDICTION_COLUMNS,
    _df_to_prediction_tuples,
    load_predictions,
)
from src.model.predict import PREDICTION_COLUMNS as PRED_COLUMNS_FROM_PREDICT  # noqa: F401

# ---------------------------------------------------------------------------
# helpers — 合成 prediction DataFrame
# ---------------------------------------------------------------------------

_TEST_MODEL_VERSION_LGB = "test-lgb-v1"
_TEST_MODEL_VERSION_CB = "test-cb-v1"


def _make_synthetic_prediction_df(
    n: int,
    *,
    model_type: str,
    model_version: str,
    as_of: datetime,
    umaban_offset: int = 0,
) -> pd.DataFrame:
    """合成 prediction DataFrame を PREDICTION_COLUMNS 列順で構築.

    10 行の予測を生成。PK (model_type+model_version+feature_snapshot_id+as_of_datetime +
    RACE_KEY 7) が一意になるよう umaban/kettonum を offset で分離。
    """
    rows = []
    for i in range(n):
        rows.append(
            {
                "model_type": model_type,
                "model_version": model_version,
                "feature_snapshot_id": "test-snapshot-v1",
                "as_of_datetime": as_of,
                "calib_method": "isotonic",
                "year": 2024,
                "jyocd": "05",
                "kaiji": 1,
                "nichiji": "01",
                "racenum": 1,
                "umaban": umaban_offset + i + 1,
                "kettonum": 1000 + umaban_offset + i,
                "p_fukusho_hit": 0.1 + 0.05 * i,  # [0.1, 0.55] 範囲
                "race_date": pd.Timestamp("2024-01-01").date(),
                "split": "test",
                # Phase 6 D-09 (Plan 06-04): is_primary 列追加に伴う Pitfall 4 回帰修正。
                # 予測生成時は False（set_primary_model で True に UPDATE・本テストは load 経路確認）。
                "is_primary": False,
            }
        )
    df = pd.DataFrame(rows)
    # PREDICTION_COLUMNS の順序に並び替え
    return df[list(PREDICTION_COLUMNS)]


# ---------------------------------------------------------------------------
# Test 1: idempotent checksum match (2 runs)
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_idempotent_checksum_match(write_cur):
    """D-05: load_predictions を2回実行で checksum 一致 (staging-swap idempotent).

    同一 model_type+model_version の行を scoped で置換 (review Cycle 2 NEW-3: 列明示 INSERT).
    2回目の実行で1回目の行が scoped DELETE で置換され・checksum が一致することを検証。

    検証項目:
      1. load_predictions 1回目・2回目の checksum が完全一致 (bit-identical)
      2. ``SELECT count(*) WHERE model_type+model_version`` == len(rows) (重複なし)
      3. staging テーブルが残らない
    """
    as_of = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    df = _make_synthetic_prediction_df(
        10,
        model_type="lightgbm",
        model_version=_TEST_MODEL_VERSION_LGB,
        as_of=as_of,
    )

    try:
        checksum1 = load_predictions(write_cur, df)
        # 2回目: scoped で DELETE → INSERT されるため row count は 10 のまま
        checksum2 = load_predictions(write_cur, df)

        assert checksum1 == checksum2, (
            f"idempotent violation: checksum1={checksum1!r} != checksum2={checksum2!r}"
        )

        # row count が len(rows) と一致 (重複挿入なし)
        write_cur.execute(
            "SELECT count(*) FROM prediction.fukusho_prediction "
            "WHERE model_type = %s AND model_version = %s",
            ("lightgbm", _TEST_MODEL_VERSION_LGB),
        )
        cnt = int(write_cur.fetchone()[0])
        assert cnt == 10, f"expected 10 rows after 2nd load, got {cnt}"

        # staging テーブルが残らない
        write_cur.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'prediction' "
            "AND table_name = 'fukusho_prediction_staging'"
        )
        staging_cnt = int(write_cur.fetchone()[0])
        assert staging_cnt == 0, "staging table was not cleaned up"
    finally:
        # teardown: テストデータ削除
        write_cur.execute(
            "DELETE FROM prediction.fukusho_prediction WHERE model_version IN (%s, %s)",
            (_TEST_MODEL_VERSION_LGB, _TEST_MODEL_VERSION_CB),
        )


# ---------------------------------------------------------------------------
# Test 2: review HIGH#1 model_version scoped swap preserves other models
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_model_version_scoped_swap_preserves_other_models(write_cur):
    """review HIGH#1 / Cross-Plan #3: model_version スコープ置換で他 model_type/version の行を保持.

    lightgbm v1 の予測を書込んだ後、catboost v1 の予測を別途書込んでも
    lightgbm v1 の行が破壊されず残ることを assert。全テーブル置換 (DROP+RENAME)
    で他 model を削除しないことを実証。

    検証項目:
      1. lightgbm 書込 → catboost 書込 → lightgbm が 10 行残る
      2. catboost も 10 行
      3. 各 model_type+model_version で row count が独立
    """
    as_of = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    df_lgb = _make_synthetic_prediction_df(
        10,
        model_type="lightgbm",
        model_version=_TEST_MODEL_VERSION_LGB,
        as_of=as_of,
    )
    df_cb = _make_synthetic_prediction_df(
        10,
        model_type="catboost",
        model_version=_TEST_MODEL_VERSION_CB,
        as_of=as_of,
        umaban_offset=100,  # PK 衝突回避
    )

    try:
        load_predictions(write_cur, df_lgb)
        load_predictions(write_cur, df_cb)

        # lightgbm が破壊されず 10 行残る
        write_cur.execute(
            "SELECT count(*) FROM prediction.fukusho_prediction "
            "WHERE model_type = 'lightgbm' AND model_version = %s",
            (_TEST_MODEL_VERSION_LGB,),
        )
        lgb_cnt = int(write_cur.fetchone()[0])
        assert lgb_cnt == 10, (
            f"lightgbm rows destroyed by catboost load: expected 10, got {lgb_cnt} "
            "(review HIGH#1 / Cross-Plan #3 violation)"
        )

        # catboost も 10 行
        write_cur.execute(
            "SELECT count(*) FROM prediction.fukusho_prediction "
            "WHERE model_type = 'catboost' AND model_version = %s",
            (_TEST_MODEL_VERSION_CB,),
        )
        cb_cnt = int(write_cur.fetchone()[0])
        assert cb_cnt == 10, f"catboost rows missing: expected 10, got {cb_cnt}"
    finally:
        write_cur.execute(
            "DELETE FROM prediction.fukusho_prediction WHERE model_version IN (%s, %s)",
            (_TEST_MODEL_VERSION_LGB, _TEST_MODEL_VERSION_CB),
        )


# ---------------------------------------------------------------------------
# Test 3: _df_to_prediction_tuples 単体検証 (unit・非 DB)
# ---------------------------------------------------------------------------


def test_df_to_prediction_tuples_column_order():
    """``_df_to_prediction_tuples`` が PREDICTION_COLUMNS 順の tuple を返す (unit).

    非 DB テスト。列順序と型変換 (str/int/float/timestamp) の契約を検証。
    """
    as_of = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    df = _make_synthetic_prediction_df(
        3,
        model_type="lightgbm",
        model_version="unit-v1",
        as_of=as_of,
    )
    tuples = _df_to_prediction_tuples(df)

    assert len(tuples) == 3
    # 各 tuple の長さ == len(PREDICTION_COLUMNS)
    assert all(len(t) == len(PREDICTION_COLUMNS) for t in tuples)

    # 列順序の検証: 先頭は model_type (str)・p_fukusho_hit は float
    first = tuples[0]
    assert first[0] == "lightgbm", f"first col should be model_type, got {first[0]!r}"
    # p_fukusho_hit は PREDICTION_COLUMNS の index を参照
    p_idx = list(PREDICTION_COLUMNS).index("p_fukusho_hit")
    assert isinstance(first[p_idx], float)
