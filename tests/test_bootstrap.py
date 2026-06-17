"""Bootstrap smoke tests（REVIEWS HIGH #6 / MEDIUM #1）。

- test_dsn_masks_password: Settings.dsn_masked / etl_dsn_masked が生パスワードを含まない
- test_etl_dsn_uses_etl_role: Settings.etl_dsn が KEIBA_ETL_DB_USER を user 部に含む
- test_readonly_cur_can_select_n_race: 実DBの n_race から JRA レース件数（>0）を取得
"""

from __future__ import annotations

import pytest


def test_dsn_masks_password(settings) -> None:  # noqa: ANN001
    """Settings.dsn_masked / etl_dsn_masked は生パスワードを含んでいてはならない。

    生パスワードを含む ``dsn`` / ``etl_dsn`` は絶対に logging.info 等に渡してはならない。
    ログ出力可能なのは masked 版のみ（REVIEWS MEDIUM #1 / T-01-01 / ASVS V8）。
    """
    raw_password = settings.db_password.get_secret_value()
    etl_raw_password = settings.etl_db_password.get_secret_value()

    # masked 版に生パスワードが現れてはならない
    assert raw_password not in settings.dsn_masked, (
        "raw db_password leaked into dsn_masked"
    )
    assert etl_raw_password not in settings.etl_dsn_masked, (
        "raw etl_db_password leaked into etl_dsn_masked"
    )
    # masked 版は *** プレースホルダを含む
    assert ":***@" in settings.dsn_masked
    assert ":***@" in settings.etl_dsn_masked

    # サンプル: dsn_masked を使った安全なログ出力
    safe_log_msg = f"connecting to {settings.dsn_masked}"
    assert raw_password not in safe_log_msg
    assert etl_raw_password not in safe_log_msg


def test_etl_dsn_uses_etl_role(settings) -> None:  # noqa: ANN001
    """Settings.etl_dsn は KEIBA_ETL_DB_USER を user 部に含む（REVIEWS HIGH #6）。"""
    # dsn は postgresql://{etl_db_user}:{pw}@host:port/db 形式
    assert settings.etl_db_user in settings.etl_dsn, (
        f"etl_dsn does not contain etl_db_user={settings.etl_db_user!r}"
    )
    # user 部に現れることを確認（:// の直後）
    scheme, rest = settings.etl_dsn.split("://", 1)
    creds = rest.split("@", 1)[0]
    user = creds.split(":", 1)[0]
    assert user == settings.etl_db_user


@pytest.mark.requires_db
def test_readonly_cur_can_select_n_race(readonly_cur) -> None:  # noqa: ANN001
    """readonly_cur で n_race を SELECT し JRA レース件数（>0）を確認。

    Pitfall 2 対策: ``jyocd BETWEEN '01' AND '10'`` で JRA 10場に限定。
    Task 3（CREATE ROLE）の実行後に keiba_readonly ロールが存在することを前提とする。
    """
    readonly_cur.execute(
        "SELECT count(*) FROM n_race WHERE jyocd BETWEEN '01' AND '10'"
    )
    (count,) = readonly_cur.fetchone()
    assert count > 0, f"expected JRA races in n_race but got count={count}"
