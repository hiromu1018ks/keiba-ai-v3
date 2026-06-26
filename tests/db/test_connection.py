# ruff: noqa: E501
"""src/db/connection.py の unit test.

WR-02 (10-08 gap-closure): make_pool が configure callback 引数を取り ConnectionPool(..., configure=configure)
に forward することを検証する（psycopg_pool の configure は __init__ 引数であってインスタンスメソッドでない）。
live-DB に接続せず・make_pool の signature と ConnectionPool への引数 forward を mock で検証する。

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし・pure unit test）。
"""

from __future__ import annotations

from unittest.mock import patch


def test_make_pool_accepts_configure_callback() -> None:
    """WR-02 (10-08 gap-closure): ``make_pool`` が ``configure`` callback 引数を受け取ること."""
    import inspect

    from src.db.connection import make_pool

    sig = inspect.signature(make_pool)
    assert "configure" in sig.parameters, (
        "make_pool に configure 引数が無い・WR-02 pool 全体 statement_timeout 適用ができない"
    )
    # default は None（既存呼出し非破壊）
    assert sig.parameters["configure"].default is None, (
        "make_pool の configure 引数の default が None でない・既存呼出し非破壊が崩れる"
    )


def test_make_pool_forwards_configure_to_connection_pool() -> None:
    """WR-02: ``make_pool`` が ``configure`` callback を ConnectionPool(..., configure=configure) に forward すること.

    psycopg_pool の ConnectionPool.configure は __init__ 引数（インスタンスメソッドでない）。
    ``readonly_pool.configure(...)`` は AttributeError になるため・make_pool 経由で forward する必要がある。
    本テストは ConnectionPool を mock し・configure= が渡ることを検証する。
    """
    from src.db import connection as conn_mod
    from src.db.connection import make_pool

    # Settings の最小 mock
    class _FakeSettings:
        dsn = "postgresql://user:pass@localhost:5432/db"
        etl_dsn = "postgresql://user:pass@localhost:5432/db"
        db_schema_raw = "public"
        db_schema_label = "label"
        db_schema_prediction = "prediction"
        db_schema_backtest = "backtest"
        db_schema_normalized = "normalized"

    def _my_configure(conn) -> None:  # noqa: ANN001
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        conn.commit()

    with patch.object(conn_mod, "ConnectionPool") as mock_pool_cls:
        make_pool(_FakeSettings(), role="readonly", configure=_my_configure)

        # ConnectionPool が configure=_my_configure で呼ばれたか
        _, kwargs = mock_pool_cls.call_args
        assert "configure" in kwargs, (
            "make_pool が ConnectionPool(..., configure=...) に forward していない (WR-02)"
        )
        assert kwargs["configure"] is _my_configure, (
            "make_pool が ConnectionPool に渡す configure が呼出し元の callback でない (WR-02)"
        )


def test_make_pool_default_configure_is_none() -> None:
    """WR-02: configure 未指定時は ConnectionPool に configure=None が渡る（既存呼出し非破壊）."""
    from src.db import connection as conn_mod
    from src.db.connection import make_pool

    class _FakeSettings:
        dsn = "postgresql://user:pass@localhost:5432/db"
        etl_dsn = "postgresql://user:pass@localhost:5432/db"
        db_schema_raw = "public"
        db_schema_label = "label"
        db_schema_prediction = "prediction"
        db_schema_backtest = "backtest"
        db_schema_normalized = "normalized"

    with patch.object(conn_mod, "ConnectionPool") as mock_pool_cls:
        # configure 未指定
        make_pool(_FakeSettings(), role="readonly")
        _, kwargs = mock_pool_cls.call_args
        # configure=None が ConnectionPool に forward される（psycopg_pool は configure=None を許容）
        assert kwargs.get("configure") is None, (
            "make_pool が configure 未指定時に ConnectionPool に configure=None を forward していない・"
            "既存呼出し非破壊が崩れる (WR-02)"
        )
