"""raw(``public.n_*``) の不変性証明用ヘルパー（成功基準#2 / D-06 二重保護 / MEDIUM #2）。

本モジュールは read-only helper であり、UPDATE/DELETE SQL を一切発行しない。

証明戦略（REVIEWS MEDIUM #2 に基づく2階層アプローチ）:

  - **主証明（primary）:** 各テーブル × 各年の aggregate checksum
    （``md5(string_agg(t::text, ',' ORDER BY t::text))`` per ``year`` per table）。
    これを ``<table>:<year>:<hash>`` のリストとして sorted concat し全体の md5 を計算する。
    これにより単一日の固定サンプルではなく**全 JRA 行**をカバーする。
  - **補助（supplementary）:** ``pg_stat_user_tables.n_tup_upd`` / ``n_tup_del`` /
    ``n_tup_ins`` の差分。``VACUUM`` でリセットされるため**補助シグナル**扱いであり、
    単独では不変証明とならない。主証明の row-hash + row-count と併用する。

注意（Pitfall 2）: 全クエリで ``jyocd BETWEEN '01' AND '10'``（JRA 限定）。
"""

from __future__ import annotations

import hashlib
from typing import Any

from psycopg import Cursor

_DEFAULT_TABLES = ("n_race", "n_uma_race", "n_harai", "n_hyosu", "n_odds_tanpuku")
_JRA_FILTER = "jyocd BETWEEN '01' AND '10'"


def compute_raw_fingerprint(
    read_cur: Cursor,
    *,
    tables: tuple[str, ...] = _DEFAULT_TABLES,
) -> dict[str, Any]:
    """raw(``public.<table>``) の指紋を計算する（read-only・成功基準#2 主証明 + 補助）。

    Args:
        read_cur: readonly ロールの cursor（UPDATE/DELETE 権限なし・安全）。
        tables: 対象テーブル（デフォルトは主要5系統）。

    Returns:
        ``{
          "row_hash": {table: str},         # 主証明: per-year aggregate md5
          "row_count": {table: {"total": N, "jra": M}},  # 主証明: 件数
          "n_tup_upd": {table: int},        # 補助: pg_stat_user_tables
          "n_tup_del": {table: int},        # 補助
          "n_tup_ins": {table: int},        # 補助
        }``
    """
    row_hash: dict[str, str] = {}
    row_count: dict[str, dict[str, int]] = {}
    n_tup_upd: dict[str, int] = {}
    n_tup_del: dict[str, int] = {}
    n_tup_ins: dict[str, int] = {}

    for table in tables:
        # 主証明: per-year aggregate checksum（全 JRA 行をカバー）
        # 旧 plan の単一日 sample_date="20240101" は範囲外変更を見逃す問題を解決するため、
        # 全 year × 全 JRA 行 の aggregate を計算する。
        read_cur.execute(
            f"SELECT year, md5(string_agg(t::text, ',' ORDER BY t::text)) "
            f"FROM public.{table} t WHERE {_JRA_FILTER} "
            f"GROUP BY year ORDER BY year"
        )
        per_year = [f"{table}:{y}:{h}" for y, h in read_cur.fetchall()]
        joined = "|".join(per_year)
        row_hash[table] = hashlib.md5(joined.encode("utf-8")).hexdigest()

        # 主証明: row count（全体 + JRA 限定）
        read_cur.execute(f"SELECT count(*) FROM public.{table}")
        total = int(read_cur.fetchone()[0])
        read_cur.execute(f"SELECT count(*) FROM public.{table} WHERE {_JRA_FILTER}")
        jra = int(read_cur.fetchone()[0])
        row_count[table] = {"total": total, "jra": jra}

        # 補助（supplementary）: pg_stat_user_tables（VACUUM でリセットされる点に注意）
        read_cur.execute(
            "SELECT relname, n_tup_upd, n_tup_del, n_tup_ins "
            "FROM pg_stat_user_tables "
            "WHERE schemaname='public' AND relname = %s",
            (table,),
        )
        stat = read_cur.fetchone()
        if stat is not None:
            n_tup_upd[table] = int(stat[1] or 0)
            n_tup_del[table] = int(stat[2] or 0)
            n_tup_ins[table] = int(stat[3] or 0)
        else:
            n_tup_upd[table] = -1  # テーブル未存在を示す番兵
            n_tup_del[table] = -1
            n_tup_ins[table] = -1

    return {
        "row_hash": row_hash,
        "row_count": row_count,
        "n_tup_upd": n_tup_upd,
        "n_tup_del": n_tup_del,
        "n_tup_ins": n_tup_ins,
    }


def assert_raw_unchanged(before: dict[str, Any], after: dict[str, Any]) -> None:
    """ETL 前後の ``compute_raw_fingerprint`` 結果を比較し、raw が不変であることを assert する。

    検証内容:
      - **主証明:** ``row_hash`` と ``row_count`` が完全一致（全テーブル・全 year）
      - **補助:** ``n_tup_upd`` / ``n_tup_del`` / ``n_tup_ins`` の差分が全テーブルで 0

    違反時は AssertionError に詳細メッセージを含む。
    """
    # 主証明: row_hash
    if before["row_hash"] != after["row_hash"]:
        diffs = []
        for table in before["row_hash"]:
            if before["row_hash"][table] != after["row_hash"].get(table):
                diffs.append(
                    f"{table}: before={before['row_hash'][table]} "
                    f"after={after['row_hash'].get(table)}"
                )
        raise AssertionError(
            "raw 不変性違反（主証明 row_hash）: " + "; ".join(diffs)
        )

    # 主証明: row_count
    if before["row_count"] != after["row_count"]:
        diffs = []
        for table in before["row_count"]:
            if before["row_count"][table] != after["row_count"].get(table):
                diffs.append(
                    f"{table}: before={before['row_count'][table]} "
                    f"after={after['row_count'].get(table)}"
                )
        raise AssertionError(
            "raw 不変性違反（主証明 row_count）: " + "; ".join(diffs)
        )

    # 補助: pg_stat 差分（VACUUM でリセットされるため参考値・主証明の代替ではない）
    aux_violations = []
    for table in before["n_tup_upd"]:
        upd_diff = after["n_tup_upd"].get(table, 0) - before["n_tup_upd"].get(table, 0)
        del_diff = after["n_tup_del"].get(table, 0) - before["n_tup_del"].get(table, 0)
        ins_diff = after["n_tup_ins"].get(table, 0) - before["n_tup_ins"].get(table, 0)
        if upd_diff != 0 or del_diff != 0 or ins_diff != 0:
            aux_violations.append(
                f"{table}: upd_diff={upd_diff}, del_diff={del_diff}, ins_diff={ins_diff}"
            )
    if aux_violations:
        raise AssertionError(
            "raw 不変性違反（補助 pg_stat）: " + "; ".join(aux_violations)
        )


__all__ = ["compute_raw_fingerprint", "assert_raw_unchanged"]
