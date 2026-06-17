# ruff: noqa: E501  (SQL リテラル・長い docstring を保持するため行長は緩和)
"""DATA-02: raw(``public.n_*``) → normalized への型/コード変換 ETL（psycopg3 + pandas 明示実装）。

仕様（01-CONTEXT.md D-06/D-08 / Pitfall 1/2/4 / HIGH #5/#6 / MEDIUM #1 / Warning #5）:

  - **D-08:** psycopg3 + Python で明示実装。DuckDB は補助のみで永続化には使わない（§12.1）。
  - **Pitfall 1:** raw の全 varchar を ``pd.to_numeric(errors='coerce')`` で明示キャスト。
      ``futan`` は0.1kg単位 → real。``kyori`` は integer。``race_date`` は date。
  - **Pitfall 2:** 全 SELECT で ``WHERE jyocd BETWEEN '01' AND '10'``（JRA 限定・NAR 除外）。
  - **Pitfall 4:** ``n_*``（確定）のみ扱い、``s_*``（速報）は対象外。
  - **HIGH #5:** ``_idempotent_load`` が staging-table-swap（CREATE _staging → TRUNCATE →
      INSERT → atomic DROP + RENAME TO）で再実行時の行重複を防ぐ（§19.1 再現性）。
  - **HIGH #6:** ``write_pool``（``make_pool(role='etl')``・``KEIBA_ETL_DB_USER``）経由で
      normalized に書込む。raw(``public.n_*``) には一切 UPDATE/DELETE/INSERT を発行しない。
  - **MEDIUM #1:** ``normalized.n_uma_race`` の主要カラム（``kakuteijyuni`` / ``kettonum`` /
      ``bamei`` / ``bataijyu`` 等）も型付き定義（Phase 2 labels 依存）。
  - **Warning #5:** ``hassotime`` が EveryDB2 初期値 ``'0'`` や長さ4数値でない不正値の場合は
      ``race_start_datetime=pd.NaT`` にフォールバック + WARNING（ETL 停止回避）。

実DB列名に関する実測補正（Rule 1 - plan 01-03 列定義との差異・2026-06-17 確認）:
  - ``n_race.hassotonen`` は存在しない → 除外
  - ``n_uma_race.bataiju`` は実測 ``bataijyu``（01-04 docs 表記揺れ）
  - ``n_uma_race.zogenfuka`` / ``tengokuangou`` / ``hansyoku`` / ``norei`` は raw に存在せず
    → これらを正とせず実在列のみ定義
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from psycopg import Cursor
from psycopg_pool import ConnectionPool

from src.etl.class_normalize import normalize_race_classes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JRA フィルタ（Pitfall 2）+ 2015年以降フィルタ（要件 §6.1: 学習・分析対象期間）
# EveryDB2 には2015年以前のレースも入っているが、本プロジェクトの対象外。ETL で
# 機械的に除外する（Rule 2: 要件 §6.1 は本プロジェクトの core 前提）。
# ---------------------------------------------------------------------------
_JRA_FILTER = "jyocd BETWEEN '01' AND '10' AND year::int >= 2015"


# ---------------------------------------------------------------------------
# normalized スキーマの型付き CREATE TABLE DDL
# MEDIUM #1: n_uma_race の主要カラムも型付き定義（Phase 2 labels 依存）
# 実DB列名（Rule 1 実測）: bataijyu / bataiju でない・zogenfuka/tengokuangou は存在しない
# ---------------------------------------------------------------------------
_RACE_COLUMNS = [
    # PK
    "year int",
    "jyocd varchar(2)",
    "kaiji int",
    "nichiji varchar(2)",
    "racenum int",
    # 型付き（Pitfall 1）
    "kyori integer",
    "futan real",  # 0.1kg 単位
    "race_date date",
    "race_start_datetime timestamp",
    # コード（varchar のまま保持）
    "jyokencd5 varchar(3)",
    "gradecd varchar(1)",
    "syubetucd varchar(2)",
    "hondai text",
    # クラス正規化結果（DATA-03）
    "class_code_normalized varchar(3)",
    "class_name_normalized text",
    "class_level_numeric smallint",
    "post_2019_class_system_flag boolean",
    "is_grade_race boolean",
    "is_listed boolean",
    "is_open_class boolean",
    "grade_numeric smallint",
    "class_normalization_status varchar(16)",
]

_UMA_RACE_COLUMNS = [
    # PK
    "year int",
    "jyocd varchar(2)",
    "kaiji int",
    "nichiji varchar(2)",
    "racenum int",
    "umaban int",
    "kettonum int",  # 実DB: kettonum varchar(10) → int に cast
    # 型付き（MEDIUM #1）
    "kakuteijyuni integer",  # 確定着順
    "nyusenjyuni integer",
    "wakuban smallint",
    "bamei text",
    "umakigocd varchar(2)",
    "sexcd varchar(1)",
    "keirocd varchar(2)",
    "hinsyucd varchar(1)",
    "barei integer",
    "tozaicd varchar(1)",
    "chokyosicode varchar(5)",
    "chokyosiryakusyo text",
    "banusicode varchar(6)",
    "banusiname text",
    "kisyucode varchar(5)",
    "kisyuryakusyo text",
    "kisyucodebefore varchar(5)",
    "minaraicd varchar(1)",
    "blinker varchar(1)",
    "futan real",  # 0.1kg 単位
    "bataijyu integer",  # 実測: bataijyu（bataiju でない）
    "zogenfugo varchar(1)",
    "zogensa integer",
    "ijyocd varchar(1)",
    "time real",  # 0.1秒単位
    "harontimel3 real",
    "harontimel4 real",
    "odds real",
    "ninki integer",
    "jyuni1c smallint",
    "jyuni2c smallint",
    "jyuni3c smallint",
    "jyuni4c smallint",
    "dochakukubun varchar(1)",
    "kyakusitukubun varchar(1)",
    "dmkubun varchar(1)",
]


def _create_table_ddl(table: str, columns: list[str]) -> str:
    """CREATE TABLE DDL を構築。PK 制約付き。"""
    pk_cols = {
        "n_race": "PRIMARY KEY (year, jyocd, kaiji, nichiji, racenum)",
        "n_uma_race": "PRIMARY KEY (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)",
    }
    cols_sql = ",\n  ".join(columns)
    pk = pk_cols.get(table, "")
    body = cols_sql + (",\n  " + pk if pk else "")
    return f"CREATE TABLE IF NOT EXISTS normalized.{table} (\n  {body}\n)"


def _create_normalized_tables(write_cur: Cursor) -> None:
    """``normalized.n_race`` / ``normalized.n_uma_race`` を IF NOT EXISTS で作成。

    既に存在する場合は ``_idempotent_load`` 側で staging-swap を使って置換するため、
    ここでは初回起動時の型付き定義のみを保証する。
    """
    write_cur.execute(_create_table_ddl("n_race", _RACE_COLUMNS))
    write_cur.execute(_create_table_ddl("n_uma_race", _UMA_RACE_COLUMNS))


# ---------------------------------------------------------------------------
# raw からの SELECT（readonly ロール・Pitfall 2 JRA フィルタ）
# ---------------------------------------------------------------------------
_RACE_SELECT_COLUMNS = [
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "monthday",
    "kyori",
    "hassotime",
    "jyokencd5",
    "gradecd",
    "syubetucd",
    "hondai",
]


def _select_raw_race(read_cur: Cursor) -> pd.DataFrame:
    """raw ``public.n_race`` から JRA 限定で SELECT（Pitfall 2/4）。"""
    cols = ", ".join(_RACE_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM public.n_race WHERE {_JRA_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_RACE_SELECT_COLUMNS)


_UMA_RACE_SELECT_COLUMNS = [
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "wakuban",
    "umaban",
    "kettonum",
    "bamei",
    "umakigocd",
    "sexcd",
    "hinsyucd",
    "keirocd",
    "barei",
    "tozaicd",
    "chokyosicode",
    "chokyosiryakusyo",
    "banusicode",
    "banusiname",
    "kisyucode",
    "kisyuryakusyo",
    "kisyucodebefore",
    "minaraicd",
    "blinker",
    "futan",
    "bataijyu",
    "zogenfugo",
    "zogensa",
    "ijyocd",
    "kakuteijyuni",
    "nyusenjyuni",
    "time",
    "harontimel3",
    "harontimel4",
    "odds",
    "ninki",
    "jyuni1c",
    "jyuni2c",
    "jyuni3c",
    "jyuni4c",
    "dochakukubun",
    "kyakusitukubun",
    "dmkubun",
]


def _select_raw_uma_race(read_cur: Cursor) -> pd.DataFrame:
    """raw ``public.n_uma_race`` から JRA 限定で SELECT（Pitfall 2/4・MEDIUM #1）。"""
    cols = ", ".join(_UMA_RACE_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM public.n_uma_race WHERE {_JRA_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_UMA_RACE_SELECT_COLUMNS)


# ---------------------------------------------------------------------------
# pandas による transform（Pitfall 1 明示キャスト・Warning #5 hassotime NaT fallback）
# ---------------------------------------------------------------------------
def _safe_parse_hassotime(series: pd.Series) -> pd.Series:
    """Warning #5: ``hassotime`` が '0' / 長さ≠4 / 非数値 / HH>23 / MM>59 は NaT に fallback。

    EveryDB2 の ``HassoTime varchar(4) 初期値 0`` により、未確定レースでは '0' が入る。
    ``datetime.strptime('0', '%H%M')`` は ValueError で ETL 全体が停止するのを防ぐため、
    事前に長さ4・数値妥当性をチェックし不正値を NaT にフォールバックする。
    """

    def _parse(v: Any) -> pd.Timestamp | pd._TSNA:  # noqa: SLF001
        if v is None:
            return pd.NaT
        s = str(v).strip()
        if len(s) != 4 or not s.isdigit():
            return pd.NaT
        hh, mm = int(s[:2]), int(s[2:])
        if hh > 23 or mm > 59:
            return pd.NaT
        return pd.Timestamp(f"{s[:2]}:{s[2:]}").time()

    return series.map(_parse)


def _transform_race_df(df: pd.DataFrame) -> pd.DataFrame:
    """raw の ``n_race`` DataFrame を typed に変換（Pitfall 1・Warning #5）。

    - ``kyori``: ``pd.to_numeric(errors='coerce')`` → Int64
    - ``race_date``: ``year + monthday`` → date
    - ``race_start_datetime``: ``race_date + hassotime``（不正値は NaT）
    - ``class_*``: ``normalize_race_classes`` で追加
    """
    out = df.copy()

    # kyori 明示キャスト
    out["kyori"] = pd.to_numeric(out["kyori"], errors="coerce").astype("Int64")

    # race_date 構築（Pitfall 1: 文字列ソートでなく date）
    ymd = out["year"].astype(str).str.cat(out["monthday"].astype(str).str.zfill(4))
    out["race_date"] = pd.to_datetime(ymd, format="%Y%m%d", errors="coerce").dt.date

    # race_start_datetime 構築（Warning #5: hassotime 不正値は NaT）
    time_parts = _safe_parse_hassotime(out["hassotime"])
    race_dt: list[Any] = []
    bad_count = 0
    for d, t in zip(out["race_date"], time_parts, strict=False):
        if d is None or pd.isna(d) or t is None or pd.isna(t):
            race_dt.append(pd.NaT)
            if not (d is None or pd.isna(d)):
                bad_count += 1
        else:
            import datetime as _dt

            race_dt.append(_dt.datetime.combine(d, t))
    if bad_count > 0:
        logger.warning(
            "Warning #5: hassotime 不正値により race_start_datetime を %d 件 NaT 化", bad_count
        )
    out["race_start_datetime"] = race_dt

    # class_* 追加（DATA-03・Pitfall 7: hondai 名称マッチ不使用）
    out = normalize_race_classes(out)

    return out


def _transform_uma_race_df(df: pd.DataFrame) -> pd.DataFrame:
    """raw の ``n_uma_race`` DataFrame を typed に変換（MEDIUM #1）。

    全数値項目を ``pd.to_numeric(errors='coerce')`` で明示キャストする。
    """
    out = df.copy()

    # int 系
    int_cols = [
        "year",
        "wakuban",
        "umaban",
        "kettonum",
        "kakuteijyuni",
        "nyusenjyuni",
        "barei",
        "bataijyu",
        "zogensa",
        "ninki",
        "jyuni1c",
        "jyuni2c",
        "jyuni3c",
        "jyuni4c",
    ]
    for c in int_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")

    # real 系
    real_cols = ["futan", "time", "harontimel3", "harontimel4", "odds"]
    for c in real_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)

    return out


# ---------------------------------------------------------------------------
# HIGH #5: idempotent staging-swap
# ---------------------------------------------------------------------------
def _idempotent_load(
    write_cur: Cursor,
    table: str,
    rows: list[tuple],
    columns: list[str],
) -> int:
    """staging-table-swap で atomic・idempotent な書込を行う（HIGH #5）。

    Steps（同一トランザクション内）:
      0. ``SELECT pg_advisory_xact_lock(hashtext('normalized.<table>'))``
         （CR-04: 同一テーブルに対する並行 ETL 実行を直列化）
      1. ``CREATE TABLE IF NOT EXISTS normalized.<table>_staging (LIKE normalized.<table> INCLUDING ALL)``
      2. ``TRUNCATE normalized.<table>_staging``
      3. ``INSERT INTO normalized.<table>_staging (...) VALUES (...)``
      4. ``DROP TABLE IF EXISTS normalized.<table>``
      5. ``ALTER TABLE normalized.<table>_staging RENAME TO <table>``

    atomic に commit されるため、外部からは常に ``<table>`` として見える。再実行で重複しない。

    CR-04 hardening:
      - 空入力（``rows == []``）の場合は ``RuntimeError`` で即座に fail する。
        読出プールのタイムアウト・transform bug・誤設定で 0 行になった場合、
        従来は空の staging を ``normalized.<table>`` に swap して silent data loss を
        起こしていた。trust-foundation ではこれを許容しない。
      - ``pg_advisory_xact_lock`` で同一テーブルの並行 swap を直列化する。並行実行で
        最後に commit した run のみが生き残び行が混ざるレースを防ぐ。
      - ``executemany`` 後 ``cursor.rowcount`` を検証し、期待行数と異なる場合は
        ``RuntimeError`` で fail する（trigger 抑制等で黙って行数が減るのを検知）。
    """
    staging = f"{table}_staging"

    # CR-04(b): 同一テーブルへの並行 ETL を直列化する transaction-scoped advisory lock。
    # hashtext('normalized.<table>') はテーブル名から安定した int32 キーを生成する。
    # xact_lock は現在の transaction の commit/rollback で自動解放される。
    write_cur.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        (f"normalized.{table}",),
    )

    # CR-04(a): 空入力の swap を拒否（silent data loss 防止）。
    # 読出プールのタイムアウトや transform bug で rows=0 になった場合、従来は空の
    # staging が normalized.<table> になり、run_normalized_etl が success で返っていた。
    if not rows:
        raise RuntimeError(
            f"_idempotent_load('{table}'): refusing to swap to empty (0 rows). "
            "Investigate read pool / transform — silent data loss prevented (CR-04)."
        )

    # IF NOT EXISTS で対象テーブルが存在しなければ作成（初回）
    write_cur.execute(
        f"CREATE TABLE IF NOT EXISTS normalized.{table} (LIKE normalized.{table} INCLUDING ALL)"
    )
    # staging を作成（既存定義を LIKE で継承・PK も含む）
    write_cur.execute(
        f"CREATE TABLE IF NOT EXISTS normalized.{staging} (LIKE normalized.{table} INCLUDING ALL)"
    )
    # TRUNCATE staging（同一トランザクション内で安全）
    write_cur.execute(f"TRUNCATE normalized.{staging}")

    # INSERT INTO staging
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    write_cur.executemany(
        f"INSERT INTO normalized.{staging} ({cols_sql}) VALUES ({placeholders})",
        rows,
    )
    # CR-04(c): executemany の実際 rowcount を検証。
    # psycopg3 は executemany 後 cursor.rowcount に作用した行数を返す。
    # trigger 等で行が抑制された場合、len(rows) と一致しない可能性がある。
    actual = write_cur.rowcount if write_cur.rowcount is not None else len(rows)
    if actual != len(rows):
        raise RuntimeError(
            f"_idempotent_load('{table}'): executemany inserted {actual}, "
            f"expected {len(rows)} (CR-04 rowcount verification)"
        )

    # atomic swap: DROP existing → RENAME staging → table
    write_cur.execute(f"DROP TABLE IF EXISTS normalized.{table}")
    write_cur.execute(f"ALTER TABLE normalized.{staging} RENAME TO {table}")
    # 新テーブル（ETL ロールが所有）に reader ロールの SELECT を付与。
    # staging-swap の都度新しい OID のテーブルが作られるため、ALTER DEFAULT
    # PRIVILEGES だけでは（ETL ロールが実行ユーザーでも timerace する）
    # reader が information_schema.columns / SELECT を使えなくなる問題を防ぐ。
    write_cur.execute(f"GRANT SELECT ON normalized.{table} TO PUBLIC")

    return len(rows)


# ---------------------------------------------------------------------------
# public API: run_normalized_etl
# ---------------------------------------------------------------------------
_NORMALIZED_COLUMNS = {
    "n_race": [
        "year",
        "jyocd",
        "kaiji",
        "nichiji",
        "racenum",
        "kyori",
        "futan",
        "race_date",
        "race_start_datetime",
        "jyokencd5",
        "gradecd",
        "syubetucd",
        "hondai",
        "class_code_normalized",
        "class_name_normalized",
        "class_level_numeric",
        "post_2019_class_system_flag",
        "is_grade_race",
        "is_listed",
        "is_open_class",
        "grade_numeric",
        "class_normalization_status",
    ],
    "n_uma_race": [
        "year",
        "jyocd",
        "kaiji",
        "nichiji",
        "racenum",
        "wakuban",
        "umaban",
        "kettonum",
        "bamei",
        "umakigocd",
        "sexcd",
        "hinsyucd",
        "keirocd",
        "barei",
        "tozaicd",
        "chokyosicode",
        "chokyosiryakusyo",
        "banusicode",
        "banusiname",
        "kisyucode",
        "kisyuryakusyo",
        "kisyucodebefore",
        "minaraicd",
        "blinker",
        "futan",
        "bataijyu",
        "zogenfugo",
        "zogensa",
        "ijyocd",
        "kakuteijyuni",
        "nyusenjyuni",
        "time",
        "harontimel3",
        "harontimel4",
        "odds",
        "ninki",
        "jyuni1c",
        "jyuni2c",
        "jyuni3c",
        "jyuni4c",
        "dochakukubun",
        "kyakusitukubun",
        "dmkubun",
    ],
}


def _df_to_tuples(df: pd.DataFrame, columns: list[str], *, table: str) -> list[tuple]:
    """DataFrame を INSERT 用 tuple list に変換（欠損は None・型は SQL 側で解決）。"""
    out: list[tuple] = []
    for _, row in df.iterrows():
        out.append(_row_to_tuple(row, columns, table=table))
    return out


def _row_to_tuple(row: pd.Series, columns: list[str], *, table: str) -> tuple:
    """1行を tuple に変換。race 系は ``race_date`` / ``race_start_datetime`` が含まれる。"""
    vals: list[Any] = []
    for c in columns:
        v = row.get(c)
        if c == "race_date":
            # CR-01: ``pd.isna(v)`` で ``pd.NaT`` も欠損として弾く（race_start_datetime
            # と対称）。従来は ``isinstance(v, float) and pd.isna(v)`` で float の NaN
            # しか弾けず、``pd.NaT`` は ``hasattr(v, "isoformat")`` 分岐に入って非 None
            # 値として date 列に混入し、INSERT 失敗/"NaT" 文字列化を引き起こしていた。
            if v is None or pd.isna(v):
                vals.append(None)
            elif hasattr(v, "isoformat"):
                vals.append(v)
            else:
                vals.append(None)
        elif c == "race_start_datetime":
            if v is None or pd.isna(v):
                vals.append(None)
            else:
                vals.append(v)
        elif isinstance(v, type(pd.NaT)):
            vals.append(None)
        elif v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            vals.append(None)
        elif table == "n_uma_race" and c in {
            "wakuban",
            "umaban",
            "kettonum",
            "kakuteijyuni",
            "nyusenjyuni",
            "barei",
            "bataijyu",
            "zogensa",
            "ninki",
            "jyuni1c",
            "jyuni2c",
            "jyuni3c",
            "jyuni4c",
        }:
            # Int64 → int or None
            vals.append(None if pd.isna(v) else int(v))
        elif table == "n_race" and c == "kyori":
            vals.append(None if pd.isna(v) else int(v))
        elif c in {"futan", "time", "harontimel3", "harontimel4", "odds"}:
            vals.append(None if pd.isna(v) else float(v))
        elif c in {"class_level_numeric", "grade_numeric"}:
            vals.append(None if pd.isna(v) else int(v))
        elif c in {"post_2019_class_system_flag", "is_grade_race", "is_listed", "is_open_class"}:
            if v is None or pd.isna(v):
                vals.append(None)
            else:
                vals.append(bool(v))
        elif isinstance(v, str):
            vals.append(v if v != "" else None if c in {"hondai", "bamei", "banusiname"} else v)
        else:
            vals.append(v if not (isinstance(v, float) and pd.isna(v)) else None)
    return tuple(vals)


def _load_race(read_pool: ConnectionPool, write_pool: ConnectionPool) -> tuple[int, int]:
    """``n_race`` を raw → typed/class-normalized → idempotent load。"""
    with read_pool.connection() as conn:
        with conn.cursor() as cur:
            raw = _select_raw_race(cur)
    transformed = _transform_race_df(raw)

    rows = _df_to_tuples(transformed, _NORMALIZED_COLUMNS["n_race"], table="n_race")
    unresolved = int((transformed["class_normalization_status"] == "unresolved").sum())

    with write_pool.connection() as conn:
        with conn.cursor() as wcur:
            _create_normalized_tables(wcur)
            inserted = _idempotent_load(wcur, "n_race", rows, _NORMALIZED_COLUMNS["n_race"])
        conn.commit()
    return inserted, unresolved


def _load_uma_race(read_pool: ConnectionPool, write_pool: ConnectionPool) -> int:
    """``n_uma_race`` を raw → typed → idempotent load（MEDIUM #1）。"""
    with read_pool.connection() as conn:
        with conn.cursor() as cur:
            raw = _select_raw_uma_race(cur)
    transformed = _transform_uma_race_df(raw)

    cols = _NORMALIZED_COLUMNS["n_uma_race"]
    rows = _df_to_tuples(transformed, cols, table="n_uma_race")

    with write_pool.connection() as conn:
        with conn.cursor() as wcur:
            _create_normalized_tables(wcur)
            inserted = _idempotent_load(wcur, "n_uma_race", rows, cols)
        conn.commit()
    return inserted


def run_normalized_etl(
    read_pool: ConnectionPool,
    write_pool: ConnectionPool,
    *,
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """raw → normalized ETL を実行する（HIGH #6: write_pool = ETL ロール）。

    Args:
        read_pool: readonly ロールの pool（``make_pool(role='readonly')``）。raw SELECT のみ。
        write_pool: ETL ロールの pool（``make_pool(role='etl')``・KEIBA_ETL_DB_USER）。
            normalized スキーマへの INSERT/UPDATE/TRUNCATE を持つ。
        tables: 処理対象（デフォルト ``['n_race', 'n_uma_race']``）。

    Returns:
        ``{"rows_inserted": {table: count}, "class_unresolved_count": int, "raw_touched": False}``
        ``raw_touched`` は常に False（raw には一切書込まない・成功基準#2）。
    """
    if tables is None:
        tables = ["n_race", "n_uma_race"]

    rows_inserted: dict[str, int] = {}
    unresolved_total = 0

    if "n_race" in tables:
        cnt, unresolved = _load_race(read_pool, write_pool)
        rows_inserted["n_race"] = cnt
        unresolved_total += unresolved
        logger.info("n_race: %d 行 inserted (%d unresolved)", cnt, unresolved)

    if "n_uma_race" in tables:
        cnt2 = _load_uma_race(read_pool, write_pool)
        rows_inserted["n_uma_race"] = cnt2
        logger.info("n_uma_race: %d 行 inserted", cnt2)

    return {
        "rows_inserted": rows_inserted,
        "class_unresolved_count": unresolved_total,
        "raw_touched": False,
    }


__all__ = [
    "run_normalized_etl",
    "_create_normalized_tables",
    "_idempotent_load",
    "_transform_race_df",
    "_transform_uma_race_df",
    "_select_raw_race",
    "_select_raw_uma_race",
]
