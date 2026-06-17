"""Keiba AI v3 pytest fixtures と DB-test skip policy（REVIEWS HIGH #8）。

DB-test skip policy:
  - ``KEIBA_SKIP_DB_TESTS=1`` の時のみ ``@pytest.mark.requires_db`` マーク付きテストを skip
    （開発時の一時回避用）
  - それ以外（デフォルト・CI 含む）は ``.env`` 未設定でも skip ではなく Settings() の
    validation error で fail させる（テスト環境の設定ミスを明示）

これにより「実 DB 無しで verdict=pass が未検証のまま green になる」品質劣化リスクを排除する。
"""

from __future__ import annotations

import os

import pytest

from src.config.settings import Settings
from src.db.connection import make_pool


@pytest.fixture(scope="session")
def settings() -> Settings:
    """``.env`` から Settings を読込。未設定時は Settings() の validation error で fail。"""
    return Settings()


@pytest.fixture(scope="session")
def pg_pool(settings: Settings):
    """raw 読取ロール（role='readonly'）の pool（session scope）。

    teardown で ``pool.close()`` を呼ぶ。
    """
    pool = make_pool(settings, role="readonly")
    yield pool
    pool.close()


@pytest.fixture
def readonly_cur(pg_pool):
    """raw 読取 cursor（function scope）。``@pytest.mark.requires_db`` 推奨。"""
    with pg_pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur


@pytest.fixture(scope="session")
def write_pool(settings: Settings):
    """normalized 書込ロール（role='etl'）の pool（session scope・REVIEWS HIGH #6）。

    plan 01-03 の ETL integration テストが使用。teardown で ``pool.close()`` を呼ぶ。
    """
    pool = make_pool(settings, role="etl")
    yield pool
    pool.close()


@pytest.fixture
def write_cur(write_pool):
    """normalized 書込 cursor（function scope・HIGH #6）。``@pytest.mark.requires_db`` 推奨。"""
    with write_pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    """KEIBA_SKIP_DB_TESTS=1 の時のみ requires_db マークを skip する（HIGH #8）。

    デフォルト（unset / CI）では skip しない。実 DB 未接続環境では Settings() の
    validation error で fail する（policy: fail-by-default unless KEIBA_SKIP_DB_TESTS=1）。
    """
    skip_db = os.environ.get("KEIBA_SKIP_DB_TESTS") == "1"
    if not skip_db:
        return
    skip_marker = pytest.mark.skip(reason="KEIBA_SKIP_DB_TESTS=1 set")
    for item in items:
        if "requires_db" in item.keywords:
            item.add_marker(skip_marker)
