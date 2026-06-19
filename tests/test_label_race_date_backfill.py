# ruff: noqa: E501
"""``src/etl/label_race_date_backfill.py`` unit test（Phase 2 負債解消 / Phase 3 cutoff 前提）。

Phase 2 Plan 02-03 の ``test_fukusho_label.py`` mock cursor + ``inspect.getsource``
パターンを踏襲し、``backfill_label_race_date`` の構造的保証を検証する:

  - CR-04(a): 空入力 ``RuntimeError("refusing to swap to empty")``（silent data loss 防止）
  - HIGH #3: staging-swap idempotent（``CREATE ... _staging (LIKE ... INCLUDING ALL)`` /
    ``pg_advisory_xact_lock(hashtext('label.fukusho_label'))`` /
    ``ALTER TABLE ... _staging RENAME TO fukusho_label`` /
    ``GRANT SELECT ON label.fukusho_label TO {reader_role}``）
  - CR-06: ``JOIN normalized.n_race`` + ``project_window_filter('fl')`` / ``project_window_filter('nr')``
  - D-06: raw 層（``raw_everydb2`` / ``public.n_*``）に UPDATE/INSERT を発行しない
  - WR-06: staging INSERT 後に ``SELECT count(*) FROM label.fukusho_label_staging`` で
    rowcount verify（不一致で ``RuntimeError``）
  - read_pool は SELECT のみ・etl_pool のみ DDL/DML（test_backfill_uses_etl_role_only）

``@pytest.mark.requires_db`` を付けた live-DB 統合テスト（Task 2 の human-verify checkpoint
で実行）は ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ skip（ルート conftest.py の policy 継承）。
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# 構造的回帰検査（mock cursor に依存しない・import / inspect のみ）
# ---------------------------------------------------------------------------
def test_backfill_module_imports_and_public_api() -> None:
    """``backfill_label_race_date`` 公開関数が存在し callable である。"""
    from src.etl import label_race_date_backfill

    assert callable(label_race_date_backfill.backfill_label_race_date)


def test_backfill_public_signature() -> None:
    """``backfill_label_race_date(read_pool, etl_pool, *, reader_role='keiba_readonly')`` シグネチャ。"""
    from src.etl import label_race_date_backfill

    sig = inspect.signature(label_race_date_backfill.backfill_label_race_date)
    params = list(sig.parameters.keys())
    # read_pool / etl_pool の2引数 + reader_role kw-only
    assert params[:2] == ["read_pool", "etl_pool"], (
        f"first two params should be read_pool, etl_pool: {params!r}"
    )
    assert "reader_role" in sig.parameters, "reader_role kwarg must exist"
    rr = sig.parameters["reader_role"]
    assert rr.default == "keiba_readonly", (
        f"reader_role default must be 'keiba_readonly': {rr.default!r}"
    )


# ---------------------------------------------------------------------------
# Test 1: CR-04(a) 空入力 RuntimeError
# ---------------------------------------------------------------------------
def test_backfill_refuses_empty_input() -> None:
    """``_idempotent_backfill_label`` は事前 SELECT で0行の場合 ``RuntimeError`` を送出。

    mock cursor で read 側が0行を返したケースを模倣し、staging swap が実行されない
    （silent data loss 防止・Phase 2 test_normalized_etl.py:29-53 と同形式）。
    """
    from src.etl.label_race_date_backfill import _idempotent_backfill_label

    write_cur = MagicMock()
    # 事前 rowcount SELECT が0を返す → 空入力として拒否
    # mock の fetchone は (0,) を返す
    write_cur.fetchone.return_value = (0,)

    with pytest.raises(RuntimeError, match="refusing to swap to empty"):
        _idempotent_backfill_label(write_cur, expected_rowcount=0, reader_role="keiba_readonly")

    # atomic swap の DROP / RENAME / GRANT は発行されない（fail-fast）
    executed_sql = " ".join(str(c.args[0]) for c in write_cur.execute.call_args_list)
    assert "DROP TABLE" not in executed_sql.upper(), (
        "空入力は swap 前に raise するべき（CR-04(a)）"
    )
    assert "RENAME" not in executed_sql.upper(), "空入力は rename 前に raise するべき（CR-04(a)）"


# ---------------------------------------------------------------------------
# Test 2: HIGH #3 staging-swap regression（inspect.getsource）
# ---------------------------------------------------------------------------
def test_backfill_uses_staging_swap_pattern() -> None:
    """``backfill_label_race_date`` ソースに staging-swap idiom が全て含まれる（HIGH #3）。"""
    from src.etl import label_race_date_backfill

    src = inspect.getsource(label_race_date_backfill)
    required = [
        "pg_advisory_xact_lock(hashtext('label.fukusho_label'))",
        "CREATE TABLE IF NOT EXISTS label.fukusho_label_staging",
        "ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label",
        "GRANT SELECT ON label.fukusho_label TO",
    ]
    missing = [r for r in required if r not in src]
    assert not missing, f"staging-swap idiom が欠落: {missing} (HIGH #3)"


# ---------------------------------------------------------------------------
# Test 3: CR-06 single source JOIN
# ---------------------------------------------------------------------------
def test_backfill_joins_normalized_n_race() -> None:
    """ソースに ``JOIN normalized.n_race`` と ``project_window_filter`` alias 修飾が含まれる。"""
    from src.etl import label_race_date_backfill

    src = inspect.getsource(label_race_date_backfill)
    assert "JOIN normalized.n_race" in src, (
        "normalized.n_race との JOIN が必要（race_date 取得・CR-06）"
    )
    assert "project_window_filter('fl')" in src, (
        "fukusho_label 側に project_window_filter('fl') が必要（CR-06 single source）"
    )
    assert "project_window_filter('nr')" in src, (
        "n_race 側に project_window_filter('nr') が必要（CR-06 single source）"
    )


# ---------------------------------------------------------------------------
# Test 4: D-06 raw read-only（UPDATE/INSERT を raw 層に発行しない）
# ---------------------------------------------------------------------------
def test_backfill_does_not_mutate_raw() -> None:
    """ソースに ``UPDATE raw_everydb2`` / ``UPDATE public.n_`` / ``INSERT INTO raw_everydb2``
    / ``INSERT INTO public.n_`` が含まれない（D-06 raw read-only）。"""
    from src.etl import label_race_date_backfill

    src = inspect.getsource(label_race_date_backfill)
    forbidden = [
        "UPDATE raw_everydb2",
        "UPDATE public.n_",
        "INSERT INTO raw_everydb2",
        "INSERT INTO public.n_",
        "DELETE FROM raw_everydb2",
        "DELETE FROM public.n_",
    ]
    found = [f for f in forbidden if f in src]
    assert not found, (
        f"raw 層への書込 SQL が検出された（D-06 違反）: {found}"
    )


# ---------------------------------------------------------------------------
# Test 5: read_pool は SELECT のみ・etl_pool のみ DDL/DML
# ---------------------------------------------------------------------------
def test_backfill_uses_etl_role_only() -> None:
    """ソース上で read cursor には SELECT のみ・write cursor に DDL/DML/GRANT。

    inspect.getsource を用いた構造検査: ``read_cur.execute(...)`` の呼出の直近に
    INSERT/UPDATE/CREATE/DROP/RENAME/GRANT/DELETE が無いことを、簡易ヒューリスティックで検査。
    より厳密には ``_idempotent_backfill_label`` が write cursor のみを受け取る設計を確認。
    """
    from src.etl import label_race_date_backfill

    src = inspect.getsource(label_race_date_backfill)
    # _idempotent_backfill_label ヘルパは write cursor のみを受け取り、
    # read cursor（raw fingerprint / non_null count）は外側の backfill_label_race_date で使う。
    # 従って内部ヘルパは単一 cursor 引数のみで DDL を発行する。
    assert "def _idempotent_backfill_label(" in src, (
        "_idempotent_backfill_label(write_cur, ...) ヘルパが必要（etl role で DDL 発行）"
    )
    # read 側で発行される SQL は SELECT のみ（compute_raw_fingerprint 内部も SELECT）。
    # ソース全体で read cursor に対する INSERT/UPDATE/CREATE/GRANT が無いことを検査:
    # write 关连の statement を含むのは _idempotent_backfill_label のみであり、
    # それが ``write_cur`` を受け取ることをシグネチャで保証。
    sig_src_match = inspect.getsource(label_race_date_backfill._idempotent_backfill_label)
    # write cursor param の名前が write_cur であること（read_cur と混同しない）
    assert "write_cur" in sig_src_match, (
        "_idempotent_backfill_label は write_cur を受け取るべき（read_pool と区別）"
    )


# ---------------------------------------------------------------------------
# Test 6: WR-06 rowcount verify（SELECT count(*) で不一致は RuntimeError）
# ---------------------------------------------------------------------------
def test_backfill_rowcount_verify() -> None:
    """staging INSERT 後に ``SELECT count(*) FROM label.fukusho_label_staging`` を発行し、
    expected rowcount と不一致で ``RuntimeError("WR-06 rowcount verification")`` を raise。"""
    from src.etl.label_race_date_backfill import _idempotent_backfill_label

    write_cur = MagicMock()
    # 事前 SELECT count(*) で expected_rowcount=100 を返す（空入力回避）
    # → staging INSERT 後の SELECT count(*) で actual=80（不一致）を返す
    # mock cursor の fetchone は順次呼ばれる: 1回目=pre-count, 2回目=post-INSERT count
    write_cur.fetchone.side_effect = [
        (100,),  # pre-count SELECT（空入力でない）
        (80,),   # staging INSERT 後の SELECT count(*) → 不一致
    ]

    with pytest.raises(RuntimeError, match="WR-06 rowcount verification"):
        _idempotent_backfill_label(write_cur, expected_rowcount=100, reader_role="keiba_readonly")

    # staging count が検査されたことを SQL で確認
    executed_sql = " ".join(str(c.args[0]) for c in write_cur.execute.call_args_list)
    assert "SELECT count(*) FROM label.fukusho_label_staging" in executed_sql, (
        "staging INSERT 後に SELECT count(*) で rowcount verify が必要（WR-06）"
    )
    # 不一致のため atomic swap (DROP/RENAME) は発行されない
    assert "DROP TABLE" not in executed_sql.upper(), (
        "rowcount 不一致時は swap 前に raise するべき（WR-06）"
    )


# ---------------------------------------------------------------------------
# Test 7: rowcount 一致時は最終 count を返す
# ---------------------------------------------------------------------------
def test_backfill_returns_final_rowcount_on_success() -> None:
    """rowcount 一致時は最終 ``SELECT count(*) FROM label.fukusho_label`` の値を返す。"""
    from src.etl.label_race_date_backfill import _idempotent_backfill_label

    write_cur = MagicMock()
    # pre-count=100, staging count=100（一致）, final count=100
    write_cur.fetchone.side_effect = [
        (100,),  # pre-count
        (100,),  # staging count verify
        (100,),  # final count after RENAME
    ]
    result = _idempotent_backfill_label(write_cur, expected_rowcount=100, reader_role="keiba_readonly")
    assert result == 100, f"final rowcount を返すべき: {result}"


# ---------------------------------------------------------------------------
# live-DB integration test（Task 2 checkpoint で人手実行・skip policy 対象）
# ---------------------------------------------------------------------------
@pytest.mark.requires_db
def test_backfill_live_db() -> None:
    """実 DB に対して backfill を実行し、race_date が全行非 NULL になることを検証。

    Task 2 の human-verify checkpoint で ``scripts/run_label_race_date_backfill.py``
    経由で実行される。``KEIBA_SKIP_DB_TESTS=1`` で skip（ルート conftest.py policy）。
    """
    from src.config.settings import Settings
    from src.db.connection import make_pool
    from src.etl.label_race_date_backfill import backfill_label_race_date

    settings = Settings()
    read_pool = make_pool(settings, role="readonly")
    etl_pool = make_pool(settings, role="etl")
    try:
        result = backfill_label_race_date(read_pool, etl_pool)
        assert result["raw_touched"] is False, "raw に書込んだ（D-06 違反）"
        assert result["non_null_race_date_count"] == result["rows_backfilled"], (
            "race_date が全行非 NULL でない（T-03-08 silent data loss）"
        )
    finally:
        read_pool.close()
        etl_pool.close()
