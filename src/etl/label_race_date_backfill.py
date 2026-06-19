# ruff: noqa: E501  (長い docstring / SQL 文字列を保持するため行長は緩和)
"""Phase 2 負債解消: ``label.fukusho_label.race_date`` 全行 backfill（Phase 3 cutoff 前提）。

背景
----
Phase 2 で ``label.fukusho_label`` テーブルを構築した際、race_date 列（``date NULL``・
Phase 2 `_LABEL_TABLE_COLUMNS` の1項目）は全 554267 行 NULL のまま残された
（02-VERIFICATION.md Deferred #1）。Phase 3 の cutoff（D-06: ``feature_cutoff_datetime =
race_date - 1 day``）がこの列に依存するため、feature builder が動く前に backfill が必要。

アプローチ
----------
Phase 1 ``src/etl/normalize.py:_idempotent_load`` と Phase 2
``src/etl/fukusho_label.py:_idempotent_load_label`` で確立した **staging-table-swap
idempotent** パターンを再利用（HIGH #3・REVIEWS MEDIUM #7 accept）。
``label.fukusho_label`` を ``normalized.n_race`` と JOIN して ``race_date`` を取得した
staging 表で atomic に置換する（narrow ``UPDATE`` 直書きでなく staging-swap）。
再実行で rowcount 一致を assert する。

セキュリティ / リーク防止
-------------------------
  - D-06: raw 層（``raw_everydb2`` / ``public.n_*``）には一切書込まない。
    backfill は ``label.fukusho_label``（label スキーマ）の atomic swap のみ。
    ``compute_raw_fingerprint(before)`` / ``assert_raw_unchanged(after)`` で二重保護。
  - HIGH #3: atomic swap 後に ``GRANT SELECT ON label.fukusho_label TO {reader_role}``
    を明示再発行（``psycopg.sql.Identifier``・TO PUBLIC 不使用）。RENAME で GRANT が
    欠落する事故を防止（T-03-07）。
  - CR-04(b): ``pg_advisory_xact_lock(hashtext('label.fukusho_label'))`` で並行 swap を
    transaction-scoped に直列化（T-03-06 DoS 防止）。
  - CR-04(a): 事前 SELECT で 0 行の場合 ``RuntimeError("refusing to swap to empty")``
    で fail-fast（silent data loss 防止・T-03-08）。
  - CR-06: JOIN の両側に ``project_window_filter`` を付与（JRA 10場 + year>=2015 単一ソース）。
  - WR-06: staging INSERT 後に ``SELECT count(*) FROM label.fukusho_label_staging`` で
    actual rowcount を検証（psycopg3 executemany rowcount は PG version で非決定論的）。

戻り値
------
``{"rows_backfilled": int, "checksum": str, "raw_touched": False,
   "non_null_race_date_count": int}``
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg import Cursor
from psycopg.sql import SQL, Identifier
from psycopg_pool import ConnectionPool

from src.etl.filters import project_window_filter
from src.etl.fukusho_label import LABEL_INSERT_COLUMNS  # WR-11: public API
from src.etl.raw_fingerprint import assert_raw_unchanged, compute_raw_fingerprint

logger = logging.getLogger(__name__)

# label.fukusho_label の PK race-level prefix（normalized.n_race と同一 KEY・
# umaban/kettonum は SE level なので race-level JOIN では使わない）。
# normalized.n_race の PK は race-level: (year, jyocd, kaiji, nichiji, racenum)。
# JOIN 後、fukusho_label 側は SE 行（umaban 毎）になるが、race_date は race-level で
# 同一値が付与されるため 1:N JOIN で行増殖は起きない（race_date は race-level 定数）。
_RACE_LEVEL_JOIN_KEYS = ("year", "jyocd", "kaiji", "nichiji", "racenum")


def _idempotent_backfill_label(
    write_cur: Cursor,
    *,
    expected_rowcount: int,
    reader_role: str,
) -> int:
    """staging-swap で ``label.fukusho_label`` を atomic 替換し race_date を backfill する。

    Steps（同一トランザクション内・Phase 2 ``_idempotent_load_label`` lines 940-1014 と同一構造）:

      0. ``SELECT pg_advisory_xact_lock(hashtext('label.fukusho_label'))``（CR-04(b)・T-03-06）
      1. 空入力拒否: ``expected_rowcount == 0`` で ``RuntimeError("refusing to swap to empty")``
         （CR-04(a)・T-03-08 silent data loss 防止）
      2. ``CREATE TABLE IF NOT EXISTS label.fukusho_label_staging
         (LIKE label.fukusho_label INCLUDING ALL)``（HIGH #3: PK/index/NOT NULL/comment 継承）
      3. ``TRUNCATE label.fukusho_label_staging``
      4. **INSERT SELECT with JOIN**:
         ``INSERT INTO label.fukusho_label_staging (<全列>)``
         SELECT 句は <全列> と同一順序で、race_date 位置だけ nr.race_date に差し替え
         （INSERT col[i] ← SELECT expr[i] の位置完全整列・末尾 append しない）。
         ``FROM label.fukusho_label fl
         JOIN normalized.n_race nr ON (fl.year=nr.year AND fl.jyocd=nr.jyocd AND
               fl.kaiji=nr.kaiji AND fl.nichiji=nr.nichiji AND fl.racenum=nr.racenum)
         WHERE project_window_filter('fl') AND project_window_filter('nr')``
         （CR-06 single source・race_date を n_race から取得）
      5. ``SELECT count(*) FROM label.fukusho_label_staging`` で actual rowcount 検証
         （WR-06・不一致で ``RuntimeError``）
      6. ``DROP TABLE IF EXISTS label.fukusho_label`` →
         ``ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label``（atomic swap）
      7. ``GRANT SELECT ON label.fukusho_label TO {reader_role}``
         （HIGH #3・T-03-07・TO PUBLIC 不使用・Identifier で安全に置換）
      8. ``SELECT count(*) FROM label.fukusho_label`` で最終 rowcount を返す（checksum 基準）

    Args:
        write_cur: etl ロールの cursor（label schema DDL/DML 権限・raw は REVOKE）。
        expected_rowcount: backfill 前の ``label.fukusho_label`` 行数（事前 SELECT 済）。
            staging INSERT 後の rowcount と一致することを検証する基準値。
        reader_role: GRANT 再発行対象の明示的 reader ロール名（HIGH #3）。

    Returns:
        swap 後の ``label.fukusho_label`` 最終行数。

    Raises:
        RuntimeError: 空入力（expected_rowcount==0）・rowcount 不一致（WR-06）。
    """
    # CR-04(b): transaction-scoped advisory lock で並行 swap を直列化
    write_cur.execute("SELECT pg_advisory_xact_lock(hashtext('label.fukusho_label'))")

    # CR-04(a): 空入力の swap を拒否（silent data loss 防止）
    if expected_rowcount == 0:
        raise RuntimeError(
            "_idempotent_backfill_label('label.fukusho_label'): refusing to swap to empty "
            "(0 rows). Investigate read pool / pre-count — silent data loss prevented (CR-04(a))."
        )

    # staging を INCLUDING ALL で作成（PK / インデックス / NOT NULL / コメント継承）
    # WR-11 (03-REVIEW): CREATE TABLE IF NOT EXISTS は既存 staging がある場合に schema を
    # 更新しないため、fukusho_label 側で列追加されると古い schema が残る schema drift が
    # 生じる。DROP TABLE IF EXISTS → CREATE TABLE の順で常に新規作成し、常に最新 schema を
    # 継承する（TRUNCATE は不要・DROP 済みなので）。
    write_cur.execute("DROP TABLE IF EXISTS label.fukusho_label_staging")
    write_cur.execute(
        "CREATE TABLE label.fukusho_label_staging "
        "(LIKE label.fukusho_label INCLUDING ALL)"
    )

    # INSERT SELECT with JOIN: race_date を normalized.n_race から取得
    # 列リストは既存 label.fukusho_label の全列（LABEL_INSERT_COLUMNS・race_date 含む）。
    # SELECT 側は cols_list と完全に同一順序で、race_date 位置だけ nr.race_date で差し替え。
    # ※ INSERT col[i] ← SELECT expr[i] の位置完全整列・positional mismatch 回避。
    #    race_date は LABEL_INSERT_COLUMNS の index 7 に含まれるが、SELECT 側では
    #    nr.race_date で差し替えるため fl.race_date は選択しない（末尾 append しない）。
    # WR-11 (03-REVIEW): public API へ移行（旧 _LABEL_INSERT_COLUMNS は後方互換 alias）。
    cols_list = list(LABEL_INSERT_COLUMNS)
    insert_cols_sql = ", ".join(cols_list)
    select_cols_sql = ", ".join(
        "nr.race_date" if c == "race_date" else f"fl.{c}" for c in cols_list
    )

    join_on = " AND ".join(f"fl.{k} = nr.{k}" for k in _RACE_LEVEL_JOIN_KEYS)
    fl_filter = project_window_filter("fl")
    nr_filter = project_window_filter("nr")

    insert_sql = (
        f"INSERT INTO label.fukusho_label_staging ({insert_cols_sql}) "
        f"SELECT {select_cols_sql} "
        f"FROM label.fukusho_label fl "
        f"JOIN normalized.n_race nr ON ({join_on}) "
        f"WHERE {fl_filter} AND {nr_filter}"
    )
    write_cur.execute(insert_sql)

    # WR-06: staging テーブルの実際の行数を SELECT count(*) で検証
    # （psycopg3 executemany/execute の rowcount は PG version で非決定論的のため信用しない）
    write_cur.execute("SELECT count(*) FROM label.fukusho_label_staging")
    actual = int(write_cur.fetchone()[0])
    if actual != expected_rowcount:
        raise RuntimeError(
            f"_idempotent_backfill_label: staging table has {actual} rows, "
            f"expected {expected_rowcount} (WR-06 rowcount verification via SELECT count(*)). "
            f"JOIN 結合の漏れ・NULL race_date 残存・NAR 混入の可能性を確認してください。"
        )

    # atomic swap: DROP existing → RENAME staging → table
    write_cur.execute("DROP TABLE IF EXISTS label.fukusho_label")
    write_cur.execute("ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label")
    # HIGH #3: RENAME 後に明示的 reader role GRANT を再発行（TO PUBLIC は使用しない）
    write_cur.execute(
        SQL("GRANT SELECT ON label.fukusho_label TO {}").format(Identifier(reader_role))
    )

    # 最終 rowcount を返す（idempotent 実行の checksum 基準）
    write_cur.execute("SELECT count(*) FROM label.fukusho_label")
    cnt = int(write_cur.fetchone()[0])
    return cnt


def backfill_label_race_date(
    read_pool: ConnectionPool,
    etl_pool: ConnectionPool,
    *,
    reader_role: str = "keiba_readonly",
) -> dict[str, Any]:
    """Phase 2 負債（``label.fukusho_label.race_date`` 全行 NULL）を backfill する。

    ``label.fukusho_label`` を ``normalized.n_race`` と JOIN した staging 表で
    atomic に置換し、race_date 列に実日付を設定する。再実行で rowcount 一致を
    assert する（HIGH #3 idempotent）。

    本関数は:

      - **read_pool** (``role='readonly'``): ``compute_raw_fingerprint`` （raw 不変性
        before/after）・事前 rowcount SELECT ・non_null_race_date_count SELECT のみ。
        raw/normalized/label への書込は権限上 REVOKE 済。
      - **etl_pool** (``role='etl'``): label schema のみ DDL/DML。raw 層は REVOKE 済
        （Phase 1 実証）。advisory lock → staging CREATE → INSERT JOIN → DROP+RENAME → GRANT。

    Args:
        read_pool: readonly ロールの ConnectionPool（SELECT のみ）。
        etl_pool: etl ロールの ConnectionPool（label schema DDL/DML）。
        reader_role: GRANT 再発行対象の明示的 reader ロール名（HIGH #3）。

    Returns:
        ``{
          "rows_backfilled": int,          # backfill 後の label.fukusho_label 行数
          "checksum": str,                  # "{rows_backfilled}|{non_null_race_date_count}"
          "raw_touched": False,             # 常に False（D-06・raw への書込なし）
          "non_null_race_date_count": int,  # race_date IS NOT NULL の行数（== rows_backfilled 期待）
        }``

    Raises:
        RuntimeError: 空入力・rowcount 不一致・raw 不変性違反。
    """
    # --- raw fingerprint before（D-06 二重保護・read pool）---
    with read_pool.connection() as conn:
        with conn.cursor() as read_cur:
            before = compute_raw_fingerprint(read_cur)
    logger.info(
        "raw fingerprint before backfill: row_counts=%s",
        {k: v for k, v in before["row_count"].items()},
    )

    # --- 事前 rowcount（空入力判定基準・read pool）---
    with read_pool.connection() as conn:
        with conn.cursor() as read_cur:
            read_cur.execute("SELECT count(*) FROM label.fukusho_label")
            expected_rowcount = int(read_cur.fetchone()[0])
    logger.info("label.fukusho_label pre-count: %d rows", expected_rowcount)

    # --- backfill 実行（etl pool・単一トランザクションで staging-swap）---
    with etl_pool.connection() as conn:
        with conn.cursor() as write_cur:
            final_count = _idempotent_backfill_label(
                write_cur,
                expected_rowcount=expected_rowcount,
                reader_role=reader_role,
            )
        # staging-swap が成功したらコミット（with 抜けで自動 commit）
        # ※ psycopg_pool の transaction context は明示 commit が無ければ rollback するため、
        #    成功時のみ commit する（例外時は自動 rollback で元テーブルが残る）。
        conn.commit()
    logger.info(
        "backfill complete: rows_backfilled=%d (expected=%d)",
        final_count,
        expected_rowcount,
    )

    # --- non_null race_date count（read pool・T-03-08 silent data loss 検証）---
    with read_pool.connection() as conn:
        with conn.cursor() as read_cur:
            read_cur.execute("SELECT count(*) FROM label.fukusho_label WHERE race_date IS NOT NULL")
            non_null_race_date_count = int(read_cur.fetchone()[0])

    # --- raw fingerprint after（D-06 二重保護）---
    with read_pool.connection() as conn:
        with conn.cursor() as read_cur:
            after = compute_raw_fingerprint(read_cur)
    assert_raw_unchanged(before, after)  # raise AssertionError if raw mutated
    logger.info("raw 不変性確認: PASS（row-hash + row-count + pg_stat 全て不変）")

    checksum = f"{final_count}|{non_null_race_date_count}"
    return {
        "rows_backfilled": final_count,
        "checksum": checksum,
        "raw_touched": False,
        "non_null_race_date_count": non_null_race_date_count,
    }


__all__ = ["backfill_label_race_date", "_idempotent_backfill_label"]
