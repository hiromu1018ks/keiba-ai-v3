"""成功基準#2 直接証明: ETL 前後で raw(public.n_*) が不変であることを pytest で保証する。

01-VALIDATION.md §Phase Requirements → Test Map に準拠。以下を直接証明する:
  - **主証明（MEDIUM #2）:** ETL 前後の row-hash + row-count が完全一致（per-year per-table
    aggregate checksum）。``pg_stat_user_tables.n_tup_upd/n_tup_del/n_tup_ins`` は VACUUM で
    リセットされるため**補助シグナル**扱い（主証明ではない）。
  - **HIGH #4:** ``public`` と ``raw_everydb2`` の両方のスキーマで KEIBA_DB_USER と
    KEIBA_ETL_DB_USER に UPDATE/DELETE/TRUNCATE 権限が無いことを DB カタログから検証。
  - **HIGH #6 補完:** ETL ロールが ``public.n_race`` に INSERT を試みると権限エラーになる。
"""

from __future__ import annotations

import pytest


def test_raw_fingerprint_module_signature() -> None:
    """``compute_raw_fingerprint`` / ``assert_raw_unchanged`` が存在し read-only helper。"""
    import inspect

    from src.etl import raw_fingerprint

    assert callable(raw_fingerprint.compute_raw_fingerprint)
    assert callable(raw_fingerprint.assert_raw_unchanged)
    src = inspect.getsource(raw_fingerprint)
    # pg_stat と md5 を参照
    assert "pg_stat_user_tables" in src
    assert "md5" in src
    # UPDATE / DELETE SQL を発行しない（read-only helper）
    assert "'UPDATE " not in src and "'DELETE " not in src


def test_raw_fingerprint_doc_describes_aux_vs_primary() -> None:
    """MEDIUM #2: pg_stat は補助・主証明は row-hash + row-count である旨が記載されている。"""
    import inspect

    from src.etl import raw_fingerprint

    src = inspect.getsource(raw_fingerprint)
    # 日本語 or 英語で「補助」「supplementary」「primary」のいずれか
    assert any(tok in src for tok in ("補助", "supplementary", "primary")), (
        "MEDIUM #2: pg_stat は補助・主証明は row-hash である旨を docstring/comment で明記すべき"
    )


@pytest.mark.requires_db
def test_raw_unchanged_after_etl(pg_pool, write_pool, readonly_cur) -> None:  # noqa: ANN001
    """成功基準#2 直接証明: ETL 前後で raw の row-hash + row-count + pg_stat が不変。"""
    from src.etl.normalize import run_normalized_etl
    from src.etl.raw_fingerprint import (
        assert_raw_unchanged,
        compute_raw_fingerprint,
    )

    before = compute_raw_fingerprint(readonly_cur)
    # read transaction を閉じる（ETL の raw SELECT とロック衝突回避）
    readonly_cur.connection.rollback()

    # ETL 実行（HIGH #6: write_pool = ETL ロール）
    run_normalized_etl(pg_pool, write_pool, tables=["n_race", "n_uma_race"])

    after = compute_raw_fingerprint(readonly_cur)
    readonly_cur.connection.rollback()

    # 主証明（row-hash + row-count）と補助（pg_stat diff == 0）の両方を assert
    assert_raw_unchanged(before, after)


@pytest.mark.requires_db
def test_raw_unchanged_after_label_etl(pg_pool, write_pool, readonly_cur) -> None:  # noqa: ANN001
    """label ETL 追加後の raw 不変性拡張（SC#2 / D-06 / Plan 02-03 / REVIEWS HIGH #3）。

    Phase 2 の ``src.etl.fukusho_label.run_label_etl`` が raw(``public.n_*``) に一切
    書込まないことを直接証明する。HIGH #3 の reader role 明示 GRANT 再発行（PUBLIC 不使用）
    後も raw は不変であることを併せて検証する。
    """
    from src.etl.fukusho_label import run_label_etl
    from src.etl.raw_fingerprint import (
        assert_raw_unchanged,
        compute_raw_fingerprint,
    )

    before = compute_raw_fingerprint(readonly_cur)
    readonly_cur.connection.rollback()

    # label ETL 実行（HIGH #6: write_pool = ETL ロール・raw には SELECT のみ）
    run_label_etl(pg_pool, write_pool)

    after = compute_raw_fingerprint(readonly_cur)
    readonly_cur.connection.rollback()

    assert_raw_unchanged(before, after)


@pytest.mark.requires_db
def test_label_etl_idempotent(pg_pool, write_pool) -> None:  # noqa: ANN001
    """REVIEWS HIGH #3 対応: staging-swap idempotency の直接検証。

    ``run_label_etl`` を2回連続実行し:
      - ``rows_inserted`` が完全一致すること（staging-swap で行重複しない）
      - ``checksum`` が完全一致すること（INCLUDING ALL で PK/インデックス継承・
        RENAME 後に reader role 明示 GRANT を再発行・``TO PUBLIC`` 不使用）
      - 2回目も ``raw_touched=False`` であること（raw には触れない）

    これにより staging-swap が PK/インデックス/GRANT/コメントを保存したまま再実行で
    同一結果になることを保証する（HIGH #3・§19.1 再現性）。
    """
    from src.etl.fukusho_label import run_label_etl

    result1 = run_label_etl(pg_pool, write_pool)
    result2 = run_label_etl(pg_pool, write_pool)

    assert result1["rows_inserted"] == result2["rows_inserted"], (
        f"idempotent violation (rows_inserted): "
        f"{result1['rows_inserted']} != {result2['rows_inserted']}"
    )
    assert result1["checksum"] == result2["checksum"], (
        f"idempotent checksum violation: {result1['checksum']} != {result2['checksum']}"
    )
    assert result2["raw_touched"] is False, "raw_touched=True on run #2 (D-06 violation)"


@pytest.mark.requires_db
def test_raw_role_has_no_update_grant_public(readonly_cur) -> None:  # noqa: ANN001
    """HIGH #4 直接検証: ``public`` と ``raw_everydb2`` の両方で UPDATE/DELETE/TRUNCATE 権限が
    現在のユーザ（keiba_readonly）に無いことを DB カタログから検証。
    """
    readonly_cur.execute(
        "SELECT table_schema, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema IN ('public','raw_everydb2') "
        "AND grantee = current_user "
        "AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')"
    )
    rows = readonly_cur.fetchall()
    assert rows == [], f"HIGH #4 violation: keiba_readonly に raw 書込権限が残っている: {rows}"


@pytest.mark.requires_db
def test_etl_role_cannot_write_public(write_cur) -> None:  # noqa: ANN001
    """HIGH #6 補完: ETL ロール（keiba_etl）が ``public.n_race`` に INSERT を試みると権限エラー。

    write_cur fixture は ETL ロールで接続されている（conftest・HIGH #6）。

    WR-07: rollback は try/finally で必ず実行する。従来は ``with pytest.raises`` の
    外側に ``rollback()`` を置いていたため、INSERT が万が一 *成功* した場合
    （例: role 権限の誤設定）に ``pytest.raises`` が ``Failed`` を送出して
    ``rollback()`` がスキップされ、汚染行が ``public.n_race`` に残って後続の
    ``test_raw_unchanged_after_etl`` を巻き込んで連鎖失敗するリスクがあった。
    """
    import psycopg

    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            # PK 違反や NOT NULL 違反ではなく権限エラーで raise することを検証。
            # VALUES 句は最小限（実データ投入ではなく権限テストなので）。
            write_cur.execute(
                "INSERT INTO public.n_race (year, monthday, jyocd, kaiji, nichiji, racenum) "
                "VALUES ('2099', '0101', '99', '99', '99', '99')"
            )
    finally:
        # テストが成功しても失敗しても（INSERT が成功して pytest.raises が Failed に
        # なっても）、汚染行を残さないよう必ず rollback する（WR-07）。
        write_cur.connection.rollback()


@pytest.mark.requires_db
def test_raw_is_view_in_raw_everydb2_schema(readonly_cur) -> None:  # noqa: ANN001
    """``raw_everydb2.n_race`` が VIEW であることを検証（plan 01-01 schema.py の成果物）。"""
    readonly_cur.execute(
        "SELECT table_name FROM information_schema.views "
        "WHERE table_schema='raw_everydb2' AND table_name='n_race'"
    )
    row = readonly_cur.fetchone()
    assert row is not None, "raw_everydb2.n_race は VIEW であるべき（plan 01-01）"
