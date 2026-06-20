"""Keiba AI v3 psycopg3 ConnectionPool と cursor context managers。

2系統の pool を使い分け（REVIEWS HIGH #6）:
  - role='readonly' → Settings.dsn（raw 読取ロール）。public.n_* / raw_everydb2 は SELECT-only
  - role='etl'      → Settings.etl_dsn（normalized 書込ロール）。normalized に INSERT/UPDATE/DELETE

legacy psycopg2 は import しない（CLAUDE.md What NOT to Use）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Cursor
from psycopg_pool import ConnectionPool

from src.config.settings import Settings


def make_pool(
    settings: Settings,
    *,
    role: str = "readonly",
    min_size: int = 1,
    max_size: int = 8,
) -> ConnectionPool:
    """DB 接続 pool を構築する。

    Args:
        settings: Settings（.env から読込）
        role: ``"readonly"`` で raw 読取ロール（Settings.dsn・search_path=public）、
              ``"etl"`` で normalized 書込ロール（Settings.etl_dsn・
              search_path=normalized,public）。それ以外は ValueError。
        min_size, max_size: pool サイズ
    """
    if role == "readonly":
        conninfo = settings.dsn
        search_path = f"{settings.db_schema_raw},public"
    elif role == "etl":
        conninfo = settings.etl_dsn
        # Phase 2: label スキーマを先頭に追加（Plan 03 _idempotent_load_label が
        # label.fukusho_label を schema 修飾で書込む・PATTERNS.md:226-232）
        # Phase 4: prediction スキーマを label と normalized の間に追加（D-05/D-12・
        # src/db/prediction_load.py が prediction.fukusho_prediction を schema 修飾で書込む）
        search_path = (
            f"{settings.db_schema_label},"
            f"{settings.db_schema_prediction},"
            f"{settings.db_schema_normalized},public"
        )
    else:
        raise ValueError(f"unknown role: {role!r} (expected 'readonly' or 'etl')")

    return ConnectionPool(
        conninfo=conninfo,
        min_size=min_size,
        max_size=max_size,
        kwargs={"options": f"-c search_path={search_path}"},
        open=True,
    )


@contextmanager
def readonly_cursor(pool: ConnectionPool) -> Iterator[Cursor]:
    """raw 読取専用 cursor を yield する context manager。

    public.n_* / raw_everydb2 に対する UPDATE/DELETE/TRUNCATE はロールベースで REVOKE 済み
    （src/db/schema.py・REVIEWS HIGH #4）。それに加えて本 cursor を通じた書込みは
    想定外の操作として検知しやすいよう readonly ロール前提。
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur


@contextmanager
def write_cursor(pool: ConnectionPool) -> Iterator[Cursor]:
    """normalized 書込用 cursor を yield する context manager（HIGH #6）。

    pool は ``make_pool(role='etl')`` で構築されたものであること。
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
