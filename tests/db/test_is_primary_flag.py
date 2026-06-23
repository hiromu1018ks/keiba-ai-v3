"""prediction.fukusho_prediction.is_primary 列の migration・型処理テスト (Phase 6 Plan 06-04 Task 1)。

D-09 / REVIEW HIGH#8 (NOT NULL 明示) / REVIEW C10 (テスト挿入行スコープ):
- is_primary は ``boolean NOT NULL DEFAULT false`` (REVIEW HIGH#8 明示)
- 3ファイル連鎖 (schema.py DDL + predict.py PREDICTION_COLUMNS + prediction_load.py 型処理) を
  ``test_prediction_columns_matches_ddl_count`` で機械検証 (Pitfall 4)
- テスト挿入行スコープ (model_version='test_..._<uuid4>') + try/finally teardown で
  global DB 状態に依存しない (REVIEW C10)

``@pytest.mark.requires_db`` + ``write_cur`` fixture で ``KEIBA_SKIP_DB_TESTS`` skip policy を継承。
Task 2 で ``set_primary_model`` 関数とそれ向けの7テストを追加する。
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pandas as pd
import pytest
from psycopg.errors import IntegrityError, NotNullViolation

from src.db.schema import (
    APPLY_ORDER,
    PREDICTION_ADD_IS_PRIMARY_SQL,
    PREDICTION_TABLE_DDL,
)
from src.db.prediction_load import _df_to_prediction_tuples
from src.model.predict import PREDICTION_COLUMNS


# ---------------------------------------------------------------------------
# Helpers — 合成 prediction DataFrame / test 挿入行スコープ (REVIEW C10)
# ---------------------------------------------------------------------------


def _make_prediction_row(
    *,
    model_type: str,
    model_version: str,
    feature_snapshot_id: str,
    as_of_datetime: datetime,
    umaban: int = 1,
    kettonum: int = 100,
    is_primary=None,
) -> dict:
    """PREDICTION_COLUMNS 16 列を埋めた1行分の dict を返す。"""
    row = {
        "model_type": model_type,
        "model_version": model_version,
        "feature_snapshot_id": feature_snapshot_id,
        "as_of_datetime": as_of_datetime,
        "calib_method": "isotonic",
        "year": 2023,
        "jyocd": "05",
        "kaiji": 1,
        "nichiji": "06",
        "racenum": 1,
        "umaban": umaban,
        "kettonum": kettonum,
        "p_fukusho_hit": 0.42,
        "race_date": pd.Timestamp("2023-06-04"),
        "split": "test",
    }
    if is_primary is not None:
        row["is_primary"] = is_primary
    else:
        row["is_primary"] = False
    return row


def _unique_test_tag() -> str:
    """重複しないテスト用 model_version suffix を生成 (REVIEW C10 teardown scope)。"""
    return f"test_is_primary_{uuid.uuid4().hex[:12]}"


def _delete_test_scope(write_cur, model_version: str) -> None:
    """テスト挿入行を model_version スコープで削除 (try/finally teardown・REVIEW C10)。"""
    write_cur.execute(
        "DELETE FROM prediction.fukusho_prediction WHERE model_version = %s",
        (model_version,),
    )


# ---------------------------------------------------------------------------
# Task 1: 3ファイル連鎖 — unit (DB 不要)
# ---------------------------------------------------------------------------


def test_prediction_columns_includes_is_primary():
    """PREDICTION_COLUMNS に 'is_primary' が含まれ・長さが16・末尾に追加されている (Pitfall 4)。"""
    assert "is_primary" in PREDICTION_COLUMNS, (
        "PREDICTION_COLUMNS に is_primary が無い（Pitfall 4 3ファイル連鎖違反）"
    )
    assert len(PREDICTION_COLUMNS) == 16, (
        f"PREDICTION_COLUMNS 長さが16でない: {len(PREDICTION_COLUMNS)} (旧15+is_primary=16期待)"
    )
    assert PREDICTION_COLUMNS[-1] == "is_primary", (
        f"is_primary は末尾であるべき: 末尾={PREDICTION_COLUMNS[-1]!r}"
    )


def _parse_ddl_columns(ddl_text: str) -> list[str]:
    """CREATE TABLE ブロックから列名を順序付きでパース（CONSTRAINT/PRIMARY/COMMENT 除外）。"""
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS \w+\.\w+\s*\((.*?)\);", ddl_text, re.DOTALL
    )
    assert match is not None, "CREATE TABLE ブロックが見つからない"
    inner = match.group(1)
    cols: list[str] = []
    for raw_line in inner.splitlines():
        stripped = raw_line.strip().rstrip(",").strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith(("PRIMARY", "CONSTRAINT", "CHECK", "COMMENT")):
            continue
        first_token = stripped.split()[0]
        m_unquoted = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)$", first_token)
        if m_unquoted:
            cols.append(m_unquoted.group(1))
    return cols


def _extract_alter_add_columns(alter_sql: str) -> list[str]:
    """ALTER ... ADD COLUMN IF NOT EXISTS <name> ... の列名を抽出。"""
    return re.findall(
        r"ADD COLUMN IF NOT EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)", alter_sql, re.IGNORECASE
    )


def test_prediction_columns_matches_ddl_count():
    """PREDICTION_COLUMNS(16) と DDL(create table + ALTER is_primary) の合計列数が一致 (Pitfall 4)。"""
    base_cols = _parse_ddl_columns(PREDICTION_TABLE_DDL)
    alter_cols = [
        c for c in _extract_alter_add_columns(PREDICTION_ADD_IS_PRIMARY_SQL) if c not in base_cols
    ]
    ddl_cols = base_cols + alter_cols
    assert len(ddl_cols) == len(PREDICTION_COLUMNS), (
        f"DDL 列数({len(ddl_cols)}) と PREDICTION_COLUMNS({len(PREDICTION_COLUMNS)}) が不一致:\n"
        f"  DDL:      {ddl_cols}\n"
        f"  PREDICTION_COLUMNS: {list(PREDICTION_COLUMNS)}"
    )
    assert ddl_cols == list(PREDICTION_COLUMNS), (
        f"DDL 列順と PREDICTION_COLUMNS が不一致:\n  DDL: {ddl_cols}\n  COLS: {list(PREDICTION_COLUMNS)}"
    )
    # idempotent ALTER が NOT NULL DEFAULT false 明示 (REVIEW HIGH#8)
    assert "is_primary" in ddl_cols
    assert (
        re.search(
            r"ADD COLUMN IF NOT EXISTS is_primary\s+boolean\s+NOT NULL\s+DEFAULT\s+false",
            PREDICTION_ADD_IS_PRIMARY_SQL,
            re.IGNORECASE,
        )
        is not None
    ), "PREDICTION_ADD_IS_PRIMARY_SQL が 'boolean NOT NULL DEFAULT false' を明示していない (REVIEW HIGH#8)"


def test_apply_order_includes_prediction_add_is_primary():
    """APPLY_ORDER に prediction_add_is_primary が含まれる (run_apply_schema.py 適用経路)。"""
    names = [name for name, _ in APPLY_ORDER]
    assert "prediction_add_is_primary" in names, (
        f"APPLY_ORDER に prediction_add_is_primary が無い: {names}"
    )
    idx_table = names.index("prediction_table")
    idx_alter = names.index("prediction_add_is_primary")
    assert idx_alter == idx_table + 1, (
        f"prediction_add_is_primary は prediction_table の直後であるべき: "
        f"table_idx={idx_table}, alter_idx={idx_alter}"
    )


# ---------------------------------------------------------------------------
# Task 1: _df_to_prediction_tuples — unit (DB 不要)
# ---------------------------------------------------------------------------


def test_df_to_prediction_tuples_is_primary_none():
    """is_primary=None は False に正規化される (tuple 16番目要素・REVIEW HIGH#8)。"""
    row = _make_prediction_row(
        model_type="lightgbm",
        model_version="dummy",
        feature_snapshot_id="dummy",
        as_of_datetime=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
        is_primary=None,
    )
    df = pd.DataFrame([row])
    tuples = _df_to_prediction_tuples(df)
    assert len(tuples) == 1
    is_primary_idx = list(PREDICTION_COLUMNS).index("is_primary")
    assert tuples[0][is_primary_idx] is False, (
        f"is_primary=None が False 正規化されていない: {tuples[0][is_primary_idx]!r} (REVIEW HIGH#8)"
    )


def test_df_to_prediction_tuples_is_primary_bool():
    """is_primary=True/False が bool のまま tuple に変換される。"""
    base_kwargs = dict(
        model_type="lightgbm",
        model_version="dummy",
        feature_snapshot_id="dummy",
        as_of_datetime=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )
    df_true = pd.DataFrame([_make_prediction_row(is_primary=True, **base_kwargs)])
    df_false = pd.DataFrame([_make_prediction_row(is_primary=False, **base_kwargs)])
    is_primary_idx = list(PREDICTION_COLUMNS).index("is_primary")
    t_true = _df_to_prediction_tuples(df_true)[0][is_primary_idx]
    t_false = _df_to_prediction_tuples(df_false)[0][is_primary_idx]
    assert t_true is True, f"is_primary=True が bool でない: {t_true!r}"
    assert t_false is False, f"is_primary=False が bool でない: {t_false!r}"


# ---------------------------------------------------------------------------
# Task 1: DB 統合テスト (requires_db・KEIBA_SKIP_DB_TESTS skip policy 継承)
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_alter_adds_is_primary_column(write_cur):
    """ALTER TABLE 実行後・is_primary 列が boolean / NOT NULL / DEFAULT false (REVIEW HIGH#8)。

    テーブル・ALTER は run_apply_schema.py (admin) で適用済み前提。ETL ロールでは ALTER 権限が
    無いため・実 DB の列定義を検証する (Plan 05-06 と同一方針)。
    """
    write_cur.execute(
        "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema='prediction' AND table_name='fukusho_prediction' "
        "AND column_name='is_primary'"
    )
    row = write_cur.fetchone()
    assert row is not None, (
        "prediction.fukusho_prediction.is_primary 列が存在しない（migration 未適用）"
    )
    data_type, is_nullable, column_default = row
    assert data_type == "boolean", f"data_type が boolean でない: {data_type!r}"
    assert is_nullable == "NO", (
        f"is_nullable が NO でない: {is_nullable!r} (REVIEW HIGH#8 NOT NULL 違反)"
    )
    assert column_default is not None and "false" in str(column_default).lower(), (
        f"column_default が false でない: {column_default!r} (REVIEW HIGH#8 DEFAULT false 違反)"
    )


@pytest.mark.requires_db
def test_is_primary_default_false_on_synthetic_rows(write_cur):
    """合成 INSERT 行の is_primary が DEFAULT false (テスト挿入行スコープ・REVIEW C10)。"""
    tag = _unique_test_tag()
    ao_dt = datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)
    rows_raw = [
        _make_prediction_row(
            model_type="lightgbm",
            model_version=tag,
            feature_snapshot_id="test_snap",
            as_of_datetime=ao_dt,
            umaban=1,
            kettonum=101,
        ),
        _make_prediction_row(
            model_type="catboost",
            model_version=tag,
            feature_snapshot_id="test_snap",
            as_of_datetime=ao_dt,
            umaban=1,
            kettonum=101,
        ),
    ]
    # DEFAULT false 検証のため is_primary は INSERT 列に含めず DB DEFAULT に委ねる
    for r in rows_raw:
        r.pop("is_primary", None)
    cols_no_primary = [c for c in PREDICTION_COLUMNS if c != "is_primary"]
    tuples = [tuple(r[c] for c in cols_no_primary) for r in rows_raw]
    cols_sql = ", ".join(cols_no_primary)
    placeholders = ", ".join(["%s"] * len(cols_no_primary))
    try:
        write_cur.executemany(
            f"INSERT INTO prediction.fukusho_prediction ({cols_sql}) VALUES ({placeholders})",
            tuples,
        )
        write_cur.execute(
            "SELECT is_primary FROM prediction.fukusho_prediction WHERE model_version = %s",
            (tag,),
        )
        results = [r[0] for r in write_cur.fetchall()]
        assert len(results) == 2
        assert all(v is False for v in results), (
            f"is_primary が DEFAULT false でない: {results} (REVIEW HIGH#8)"
        )
    finally:
        _delete_test_scope(write_cur, tag)


@pytest.mark.requires_db
def test_is_primary_not_null_constraint(write_cur):
    """is_primary=NULL の INSERT が NOT NULL 制約で拒否される (REVIEW HIGH#8)。

    NotNullViolation はトランザクションを aborted 状態にするため・SAVEPOINT で囲み
    violation 後に ROLLBACK TO SAVEPOINT でトランザクションを回復させてから teardown する
    （write_cur は同一トランザクション内で動くため・abort したままでは以降の SQL が全て拒否される）。
    """
    tag = _unique_test_tag()
    ao_dt = datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)
    row = _make_prediction_row(
        model_type="lightgbm",
        model_version=tag,
        feature_snapshot_id="test_snap",
        as_of_datetime=ao_dt,
        is_primary=None,
    )
    df = pd.DataFrame([row])
    tuples = _df_to_prediction_tuples(df)
    # _df_to_prediction_tuples は None→False に正規化するため・直接 NULL を入れる tuple を作る
    is_primary_idx = list(PREDICTION_COLUMNS).index("is_primary")
    null_tuple = list(tuples[0])
    null_tuple[is_primary_idx] = None  # 強制 NULL
    null_tuple = tuple(null_tuple)
    cols_sql = ", ".join(PREDICTION_COLUMNS)
    placeholders = ", ".join(["%s"] * len(PREDICTION_COLUMNS))
    try:
        write_cur.execute("SAVEPOINT not_null_test")
        with pytest.raises((IntegrityError, NotNullViolation)):
            write_cur.execute(
                f"INSERT INTO prediction.fukusho_prediction ({cols_sql}) VALUES ({placeholders})",
                null_tuple,
            )
        # 到達不能（pytest.raises で例外を捕捉してもトランザクションは aborted）
        write_cur.execute("ROLLBACK TO SAVEPOINT not_null_test")
    except (IntegrityError, NotNullViolation):
        # pytest.raises が捕捉した後もトランザクションは aborted のため・SAVEPOINT まで戻す
        write_cur.execute("ROLLBACK TO SAVEPOINT not_null_test")
    finally:
        _delete_test_scope(write_cur, tag)


@pytest.mark.requires_db
def test_is_primary_check_constraint(write_cur):
    """CHECK 制約 prediction_is_primary_domain が存在する (REVIEW C16: NOT NULL 二重防御)。"""
    write_cur.execute(
        "SELECT con.conname FROM pg_constraint con "
        "JOIN pg_class cls ON con.conrelid = cls.oid "
        "JOIN pg_namespace nsp ON con.connamespace = nsp.oid "
        "WHERE nsp.nspname='prediction' AND cls.relname='fukusho_prediction' "
        "AND con.conname='prediction_is_primary_domain'"
    )
    row = write_cur.fetchone()
    assert row is not None, (
        "CHECK 制約 prediction_is_primary_domain が存在しない（REVIEW HIGH#8 二重防御）"
    )
    assert row[0] == "prediction_is_primary_domain"
