"""Phase 5 backtest 結果永続化: backtest_id scoped staging-swap idempotent load (BACK-03).

成功基準 #1 (SC#1) / §19.1 再現性聖域 / BACK-03 backtest 永続化 /
PATTERNS Shared Pattern 5 (staging-swap idempotent load) 変形 を実装する service 層。

**設計の核心 (review HIGH#1 / Cross-Plan #3 と同一方針・RESEARCH §7.2-§7.4):**

本モジュールは ``src/db/prediction_load.py::_idempotent_load_prediction`` の staging-swap
パターンを基にするが・**model_version スコープ置換でなく ``backtest_id`` スコープ置換**
(DELETE WHERE backtest_id → INSERT) を採用する。

理由: backtest は ``backtest_id`` (複合キー ``{bt_name}-{policy}-{model_type}``・例:
``BT-1-30min_before-lightgbm``) 単位で永続化される。同一 backtest_id の行のみを
DELETE→INSERT で置換し・他 backtest_id の行は保持する。これにより 20 backtest
(2policy × 2model × 5窓) の provenance 履歴が互いに上書きされる silent 履歴破壊
(§19.1 再現性聖域違反) を防止する。

**MEDIUM-04 監査性 (odds_missing_policy=no_bet):**

``load_backtest`` は ``selected_flag=True`` の的中/購入行だけでなく・``selected_flag=False``
の除外候補行 (no_bet / special-odds / no-sale / scratch-cancel) も ``backtest_id`` スコープで
永続化する。これにより後続監査で「BT窓 test 中の no_bet 除外件数・内訳」を SQL 集計可能に
なり・§11.3 odds_missing_policy=no_bet の監査性が担保される。除外候補行は
``odds_missing_reason`` 列に sentinel 値 ('no_bet'/'special_value'/'no_sale'/'scratch_cancel')
が埋まり・normal 候補行は NULL になる。

**steps (同一トランザクション内・prediction_load.py パターン踏襲):**

  0. ``SELECT pg_advisory_xact_lock(hashtext('backtest.fukusho_backtest'))`` (CR-04(b))
  1. 空入力 RuntimeError (CR-04(a)・rows=[] 拒否・silent data loss 防止)
  2. backtest_id 抽出: rows から単一 backtest_id のみ含むことを assert
     (複数混在は ValueError・呼出側で1 backtest_id 単位で呼ぶ前提・review HIGH#1 と同一方針)
  3. ``CREATE TABLE IF NOT EXISTS backtest.fukusho_backtest_staging
     (LIKE backtest.fukusho_backtest INCLUDING ALL)`` (HIGH #3: PK/INDEX/NOT NULL 継承)
  4. ``TRUNCATE backtest.fukusho_backtest_staging``
  5. ``executemany INSERT INTO ... _staging ({cols_sql}) VALUES ({placeholders})``
  6. ``SELECT count(*) FROM staging`` で ``count == len(rows)`` を検証 (WR-06・rowcount verify)
  7. **backtest_id スコープ DELETE from 本テーブル** (review HIGH#1 と同一方針):
     ``DELETE FROM backtest.fukusho_backtest WHERE backtest_id = %s``
     ・他 backtest_id の行は保持される
  8. **INSERT staging → 本テーブル (Cycle 2 NEW-3 と同一: 明示的列リスト)**:
     ``INSERT INTO backtest.fukusho_backtest ({cols_sql}) SELECT {cols_sql} FROM
     backtest.fukusho_backtest_staging``・cols_sql は ``BACKTEST_COLUMNS`` csv 文字列
  9. ``DROP TABLE backtest.fukusho_backtest_staging`` (クリーンアップ)
  10. checksum 返却: ``SELECT md5(string_agg(md5(row(cols_csv)::text), '' ORDER BY PK 8))``
      WHERE backtest_id で scope (当該 backtest_id の行のみ・ORDER BY PK 8カラムで安定)

2回連続実行で checksum が bit-identical に一致する (idempotent・test で実証)。
backtest_id A 書込後 B 書込でも A が残る (review HIGH#1 と同一・test で実証)。

参照: src/db/prediction_load.py:174-348 (_idempotent_load_prediction) /
      src/db/schema.py (BACKTEST_TABLE_DDL・8カラム PK) /
      05-PATTERNS.md backtest_load.py セクション・Shared Pattern 5 /
      05-04-PLAN.md Task 2.
"""
# ruff: noqa: E501  (本ファイルは SQL リテラル・長い docstring を保持するため行長は緩和)

from __future__ import annotations

from typing import Any

import pandas as pd
from psycopg import Cursor
from psycopg.sql import SQL, Identifier, Placeholder

from src.config.settings import Settings

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_BACKTEST_TABLE = "backtest.fukusho_backtest"
_BACKTEST_STAGING = "backtest.fukusho_backtest_staging"
_BACKTEST_LOCK_KEY = "backtest.fukusho_backtest"

# BACKTEST_COLUMNS: schema.py の BACKTEST_TABLE_DDL 列順と 1:1
# (predict.py::PREDICTION_COLUMNS と同一規約・Cycle 2 NEW-3 wild-card 禁止)
BACKTEST_COLUMNS: tuple[str, ...] = (
    # provenance（§19.1 再現性・NOT NULL）
    "backtest_id",
    "backtest_strategy_version",
    "odds_snapshot_policy",
    "train_period_start",
    "train_period_end",
    "test_period_start",
    "test_period_end",
    "model_type",
    "model_version",
    "feature_snapshot_id",
    # PK RACE_KEY (7カラム・HIGH-1: umaban 含む馬単位)
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
    # 選択・会計（MEDIUM-04: selected_flag=False の除外候補行も永続化）
    "selected_flag",
    "stake",
    "refund_flag",
    "refund_amount",
    "payout_amount",
    "profit",
    "effective_stake",
    # 的中・rank・EV
    "fukusho_hit_validated",
    "recommend_rank",
    "EV_lower",
    "EV_upper",
    # odds provenance（§11.2・MEDIUM-04: NULL 可能）
    "odds_snapshot_at",
    "odds_source_type",
    "odds_missing_reason",
    # 補助
    "race_date",
)

# PK 8カラム (backtest_id + RACE_KEY 7) — checksum ORDER BY 用
_PK_ORDER_COLUMNS = [
    "backtest_id",
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
]

# ---------------------------------------------------------------------------
# _df_to_backtest_tuples — DataFrame → INSERT 用 tuple list
# ---------------------------------------------------------------------------

# int 型の PK / 会計列
_INT_COLS = {
    "year",
    "kaiji",
    "racenum",
    "umaban",
    "kettonum",
    "stake",
    "refund_amount",
    "payout_amount",
    "profit",
    "effective_stake",
    "fukusho_hit_validated",
}
# float 型の EV 列
_FLOAT_COLS = {"EV_lower", "EV_upper"}
# bool 型の flag 列
_BOOL_COLS = {"selected_flag", "refund_flag"}
# date 型の period/race_date 列（pd.Timestamp → date 変換）
_DATE_COLS = {
    "train_period_start",
    "train_period_end",
    "test_period_start",
    "test_period_end",
    "race_date",
}
# datetime 型の snapshot_at 列（そのまま）
_DATETIME_COLS = {"odds_snapshot_at"}


def _is_na(v: Any) -> bool:
    """pandas / numpy の NaN / NaT 判定 (fukusho_label.py:856 / prediction_load.py:96 パターン)。

    pd.isna は NaN / NaT / None を全て True にする。配列入力で配列を返すため try/except
    で保護する。旧実装の ``isinstance(v, float) and pd.isna(v)`` は pd.NaT (NaT 型・float
    でない) を捕捉できず・BL-3 の ``odds_snapshot_at = pd.NaT`` が None でなく tuple に残り・
    INSERT で psycopg が NaT を異常値 (datetime64 int64-min → 48113 年オーバーフロー) に
    変換して year/race_date も巻き込み NOT NULL 違反になった silent corruption を是正。
    """
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _df_to_backtest_tuples(df: pd.DataFrame) -> list[tuple]:
    """DataFrame を backtest テーブルの列順 (BACKTEST_COLUMNS) の tuple list に変換.

    prediction_load.py:108-166 の ``_df_to_prediction_tuples`` パターンを踏襲。
    型変換:
      - ``backtest_id`` / ``backtest_strategy_version`` / ``odds_snapshot_policy`` /
        ``model_type`` / ``model_version`` / ``feature_snapshot_id`` / ``jyocd`` /
        ``nichiji`` / ``recommend_rank`` / ``odds_source_type`` /
        ``odds_missing_reason`` → str (空文字 "" は None)
      - ``train_period_*`` / ``test_period_*`` / ``race_date`` → date
        (pd.Timestamp → ``.date()``・MEDIUM-04: normal 候補は odds_missing_reason=NULL)
      - ``odds_snapshot_at`` → datetime (そのまま)
      - ``year`` / ``kaiji`` / ``racenum`` / ``umaban`` / ``kettonum`` /
        ``stake`` / ``refund_amount`` / ``payout_amount`` / ``profit`` /
        ``effective_stake`` / ``fukusho_hit_validated`` → int
      - ``EV_lower`` / ``EV_upper`` → float (除外候補行は None)
      - ``selected_flag`` / ``refund_flag`` → bool
      - ``odds_missing_reason`` → str or None (MEDIUM-04: NaN/None は None に変換)

    Parameters
    ----------
    df : pd.DataFrame
        ``BACKTEST_COLUMNS`` 列を持つ DataFrame。

    Returns
    -------
    list[tuple]
        ``BACKTEST_COLUMNS`` 順の tuple list。
    """
    out: list[tuple] = []
    for _, row in df.iterrows():
        vals: list[Any] = []
        for c in BACKTEST_COLUMNS:
            v = row.get(c)
            if c in _DATE_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                elif hasattr(v, "date"):
                    vals.append(v.date())
                else:
                    try:
                        vals.append(pd.Timestamp(v).date())
                    except (TypeError, ValueError):
                        vals.append(None)
            elif c in _DATETIME_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                elif hasattr(v, "to_pydatetime"):
                    vals.append(v.to_pydatetime())
                else:
                    try:
                        vals.append(pd.Timestamp(v).to_pydatetime())
                    except (TypeError, ValueError):
                        vals.append(None)
            elif c in _INT_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    try:
                        vals.append(int(v))
                    except (TypeError, ValueError):
                        vals.append(None)
            elif c in _FLOAT_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        vals.append(None)
            elif c in _BOOL_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    vals.append(bool(v))
            elif isinstance(v, str):
                vals.append(v if v != "" else None)
            else:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    vals.append(v)
        out.append(tuple(vals))
    return out


# ---------------------------------------------------------------------------
# _idempotent_load_backtest — backtest_id スコープ staging-swap
# ---------------------------------------------------------------------------


def _idempotent_load_backtest(
    write_cur: Cursor,
    rows: list[tuple],
    *,
    reader_role: str,
) -> str:
    """staging-swap + backtest_id スコープ DELETE→INSERT で ``backtest.fukusho_backtest`` を永続化.

    review HIGH#1 / Cross-Plan #3 と同一方針: 全テーブル置換 (DROP+RENAME) でなく
    backtest_id スコープ置換を採用。同一 backtest_id の行のみ DELETE → INSERT し・
    他 backtest_id の行は保持する。

    Parameters
    ----------
    write_cur : Cursor
        書込用 cursor (``make_pool(role='etl')`` 由来)。同一トランザクション内で実行。
    rows : list[tuple]
        ``BACKTEST_COLUMNS`` 順の tuple list。空リストは RuntimeError。
    reader_role : str
        reader ロール名 (``settings.db_reader_role``)。GRANT 再発行は schema.py の
        ALTER DEFAULT PRIVILEGES でカバーされるが・将来の RENAME 等に備えて引数として保持。

    Returns
    -------
    str
        ``md5(string_agg(...))`` checksum。当該 backtest_id の行のみの checksum・
        ORDER BY PK 8カラムで安定。呼出側が2回実行で一致を検証。

    Raises
    ------
    RuntimeError
        空入力 (rows=[])・staging rowcount 不一致の時。
    ValueError
        rows に複数の backtest_id が混在する時 (review HIGH#1 と同一方針)。
    """
    # --- Step 0: advisory lock (CR-04(b)・並行 swap を直列化) ---
    write_cur.execute(
        SQL("SELECT pg_advisory_xact_lock(hashtext({}))").format(Placeholder()),
        (_BACKTEST_LOCK_KEY,),
    )

    # --- Step 1: 空入力拒否 (CR-04(a)・silent data loss 防止) ---
    if not rows:
        raise RuntimeError(
            f"_idempotent_load_backtest({_BACKTEST_TABLE!r}): refusing to load "
            "empty input (0 rows). Investigate backtest pipeline — silent data loss "
            "prevented (CR-04)."
        )

    # --- Step 2: backtest_id 抽出と単一性 assert (review HIGH#1 と同一方針) ---
    cols = list(BACKTEST_COLUMNS)
    bt_id_idx = cols.index("backtest_id")

    backtest_ids = {r[bt_id_idx] for r in rows}

    if len(backtest_ids) != 1:
        raise ValueError(
            "_idempotent_load_backtest: rows contain multiple "
            f"backtest_id — got backtest_ids={sorted(backtest_ids)!r}. "
            "Call load_backtest once per backtest_id "
            "(review HIGH#1 / Cross-Plan #3 と同一方針: backtest_id scoped swap)."
        )

    backtest_id = next(iter(backtest_ids))

    # --- Step 3: CREATE staging (INCLUDING ALL・PK/INDEX/NOT NULL 継承) ---
    write_cur.execute(
        SQL("CREATE TABLE IF NOT EXISTS {} (LIKE {} INCLUDING ALL)").format(
            Identifier("backtest", "fukusho_backtest_staging"),
            Identifier("backtest", "fukusho_backtest"),
        )
    )

    # --- Step 4: TRUNCATE staging ---
    write_cur.execute(SQL("TRUNCATE {}").format(Identifier("backtest", "fukusho_backtest_staging")))

    # --- Step 5: executemany INSERT into staging ---
    cols_sql = SQL(", ").join([Identifier(c) for c in cols])
    placeholders_sql = SQL(", ").join([Placeholder()] * len(cols))
    insert_staging_sql = SQL("INSERT INTO {} ({}) VALUES ({})").format(
        Identifier("backtest", "fukusho_backtest_staging"),
        cols_sql,
        placeholders_sql,
    )
    write_cur.executemany(insert_staging_sql, rows)

    # --- Step 6: rowcount verify via SELECT count(*) (WR-06) ---
    write_cur.execute(
        SQL("SELECT count(*) FROM {}").format(Identifier("backtest", "fukusho_backtest_staging"))
    )
    actual = int(write_cur.fetchone()[0])
    if actual != len(rows):
        raise RuntimeError(
            f"_idempotent_load_backtest: staging table has {actual} rows, "
            f"expected {len(rows)} (WR-06 rowcount verification via SELECT count(*))."
        )

    # --- Step 7: backtest_id スコープ DELETE from 本テーブル (review HIGH#1 と同一方針) ---
    # 全テーブル TRUNCATE でなく・同一 backtest_id の行のみ DELETE。
    # 他 backtest_id の行は保持される (silent 履歴破壊防止・§19.1 再現性聖域)。
    write_cur.execute(
        SQL("DELETE FROM {} WHERE {} = {}").format(
            Identifier("backtest", "fukusho_backtest"),
            Identifier("backtest_id"),
            Placeholder(),
        ),
        (backtest_id,),
    )

    # --- Step 8: INSERT staging → 本テーブル (Cycle 2 NEW-3 と同一: 明示的列リスト) ---
    # ワイルドカード列展開 (SELECT *) でなく cols_sql を SELECT 句にも使用
    # (将来 DDL 列追加/順序変更で誤列挿入防止・Cycle 2 NEW-3)。
    insert_main_sql = SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        Identifier("backtest", "fukusho_backtest"),
        cols_sql,
        cols_sql,
        Identifier("backtest", "fukusho_backtest_staging"),
    )
    write_cur.execute(insert_main_sql)

    # --- Step 9: DROP staging (クリーンアップ) ---
    write_cur.execute(
        SQL("DROP TABLE {}").format(Identifier("backtest", "fukusho_backtest_staging"))
    )

    # --- Step 10: checksum 返却 (review HIGH#1 と同一方針: backtest_id スコープ・ORDER BY PK 8) ---
    # md5(string_agg(md5(row(cols_csv)::text), '' ORDER BY PK 8カラム))
    # WHERE backtest_id で scope (当該 backtest_id の行のみ)
    cols_csv_sql = SQL(", ").join([Identifier(c) for c in cols])
    order_by_sql = SQL(", ").join([Identifier(c) for c in _PK_ORDER_COLUMNS])
    checksum_sql = SQL(
        "SELECT md5(string_agg(md5(row({})::text), '' ORDER BY {})) FROM {} WHERE {} = {}"
    ).format(
        cols_csv_sql,
        order_by_sql,
        Identifier("backtest", "fukusho_backtest"),
        Identifier("backtest_id"),
        Placeholder(),
    )
    write_cur.execute(checksum_sql, (backtest_id,))
    checksum_row = write_cur.fetchone()
    checksum = str(checksum_row[0]) if checksum_row and checksum_row[0] is not None else ""

    return checksum


# ---------------------------------------------------------------------------
# load_backtest — 公開 API (薄い wrapper)
# ---------------------------------------------------------------------------


def load_backtest(
    write_cur: Cursor,
    backtest_df: pd.DataFrame,
    *,
    reader_role: str | None = None,
) -> str:
    """backtest DataFrame を ``backtest.fukusho_backtest`` に idempotent load する.

    ``_df_to_backtest_tuples`` → ``_idempotent_load_backtest`` の薄い wrapper。
    呼出側は**1 backtest_id 単位**で呼ぶ前提 (複数 backtest_id を統合 DataFrame で渡すと
    ``ValueError``・run_backtest は backtest_id 毎に呼出)。

    MEDIUM-04: ``selected_flag=True`` の的中/購入行だけでなく・``selected_flag=False`` の
    除外候補行 (odds_missing_reason 埋め) も永続化する (§11.3 odds_missing_policy=no_bet 監査性)。

    Parameters
    ----------
    write_cur : Cursor
        書込用 cursor (``make_pool(role='etl')`` 由来・同一トランザクション)。
    backtest_df : pd.DataFrame
        ``BACKTEST_COLUMNS`` 列を持つ backtest DataFrame (run_backtest の戻り値)。
        単一 backtest_id のみ含むこと。selected_flag=True/False 混在可 (MEDIUM-04)。
    reader_role : str | None
        reader ロール名。``None`` の場合は ``Settings().db_reader_role`` から取得。

    Returns
    -------
    str
        ``_idempotent_load_backtest`` が返す md5 checksum。
        2回連続実行で一致することを呼出側で検証 (idempotent verify)。

    Raises
    ------
    RuntimeError
        空入力の時。
    ValueError
        複数 backtest_id が混在する時。
    """
    if reader_role is None:
        reader_role = Settings().db_reader_role

    rows = _df_to_backtest_tuples(backtest_df)
    return _idempotent_load_backtest(write_cur, rows, reader_role=reader_role)


__all__ = [
    "BACKTEST_COLUMNS",
    "_BACKTEST_TABLE",
    "_df_to_backtest_tuples",
    "_idempotent_load_backtest",
    "load_backtest",
]
