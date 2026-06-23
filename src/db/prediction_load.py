"""Phase 4 prediction 永続化: model_version スコープ staging-swap idempotent load (D-05).

成功基準 #1 (SC#1) / §19.1 再現性聖域 / D-05 prediction 永続化 /
PATTERNS Shared Pattern 5 (staging-swap idempotent load) 変形 を実装する service 層。

**設計の核心 (review HIGH#1 / Cross-Plan #3):**

本モジュールは ``src/etl/fukusho_label.py::_idempotent_load_label`` の staging-swap
パターンを基にするが、**全テーブル置換 (DROP + RENAME) でなく model_version スコープ置換
(DELETE WHERE model_type+model_version → INSERT)** を採用する。

理由: 全テーブル置換を採用すると、LightGBM 実行後に CatBoost 実行が前者を削除する
silent 履歴破壊が起きる (他 model_type/version の行が破壊される)。これは ``§19.1``
再現性聖域 (provenance 履歴の不可視化) 違反であり・Phase 5 永続化契約を破る。
model_version スコープ置換により同一 model_type+model_version の行のみを置換し、
他 model_type/version の行を保持する。

**steps (同一トランザクション内・fukusho_label.py パターン踏襲):**

  0. ``SELECT pg_advisory_xact_lock(hashtext('prediction.fukusho_prediction'))`` (CR-04(b))
  1. 空入力 RuntimeError (CR-04(a)・rows=[] 拒否・silent data loss 防止)
  2. model_version 抽出: rows から単一 (model_type, model_version) のみ含むことを assert
     (複数混在は ValueError・呼出側で1 model_version 単位で呼ぶ前提・review HIGH#1)
  3. ``CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction_staging
     (LIKE prediction.fukusho_prediction INCLUDING ALL)`` (HIGH #3: PK/INDEX/NOT NULL 継承)
  4. ``TRUNCATE prediction.fukusho_prediction_staging``
  5. ``executemany INSERT INTO ... _staging ({cols_sql}) VALUES ({placeholders})``
  6. ``SELECT count(*) FROM staging`` で ``count == len(rows)`` を検証 (WR-06・rowcount verify)
  7. **model_version スコープ DELETE from 本テーブル** (review HIGH#1):
     ``DELETE FROM prediction.fukusho_prediction WHERE model_type = %s AND model_version = %s``
     ・他 model_type/version の行は保持される
  8. **INSERT staging → 本テーブル (Cycle 2 NEW-3: 明示的列リスト)**:
     ``INSERT INTO prediction.fukusho_prediction ({cols_sql}) SELECT {cols_sql} FROM
     prediction.fukusho_prediction_staging``・cols_sql は ``PREDICTION_COLUMNS`` csv 文字列
     (``SELECT *`` でなく列明示・将来 DDL 変更で誤列挿入防止)
  9. ``DROP TABLE prediction.fukusho_prediction_staging`` (クリーンアップ)
  10. checksum 返却: ``SELECT md5(string_agg(md5(row(cols_csv)::text), '' ORDER BY PK 11))``
      WHERE model_type+model_version で scope (当該 model_version の行のみ・ORDER BY PK 11
      カラムで安定・review HIGH#1)

2回連続実行で checksum が bit-identical に一致する (idempotent・test で実証)。
lightgbm 書込後 catboost 書込でも lightgbm 行が残る (review HIGH#1・test で実証)。

参照: src/etl/fukusho_label.py:945-1019 (_idempotent_load_label) /
      src/db/schema.py (PREDICTION_TABLE_DDL・11カラム PK) /
      src/model/predict.py (PREDICTION_COLUMNS) /
      04-PATTERNS.md prediction_load.py セクション・Shared Pattern 5 /
      04-04-PLAN.md Task 2.
"""
# ruff: noqa: E501  (本ファイルは SQL リテラル・長い docstring を保持するため行長は緩和)

from __future__ import annotations

from typing import Any

import pandas as pd
from psycopg import Cursor
from psycopg.sql import SQL, Identifier, Placeholder

from src.config.settings import Settings
from src.model.predict import PREDICTION_COLUMNS

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_PREDICTION_TABLE = "prediction.fukusho_prediction"
_PREDICTION_STAGING = "prediction.fukusho_prediction_staging"
_PREDICTION_LOCK_KEY = "prediction.fukusho_prediction"

# PK 11カラム (4 provenance + 7 RACE_KEY) — checksum ORDER BY 用
_PK_ORDER_COLUMNS = [
    "model_type",
    "model_version",
    "feature_snapshot_id",
    "as_of_datetime",
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
]


# ---------------------------------------------------------------------------
# _df_to_prediction_tuples — DataFrame → INSERT 用 tuple list
# ---------------------------------------------------------------------------

# float 型の予測値列
_FLOAT_COLS = {"p_fukusho_hit"}
# int 型の PK 列
_INT_COLS = {"year", "kaiji", "racenum", "umaban", "kettonum"}
# bool 型の列 (Phase 6 D-09 / REVIEW HIGH#8: None→False 正規化・NOT NULL 整合)
_BOOL_COLS = {"is_primary"}


def _is_na(v: Any) -> bool:
    """pandas / numpy の NaN 判定 (fukusho_label.py:856 パターン)。"""
    if v is None:
        return True
    try:
        if isinstance(v, float) and pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _df_to_prediction_tuples(df: pd.DataFrame) -> list[tuple]:
    """DataFrame を prediction テーブルの列順 (PREDICTION_COLUMNS) の tuple list に変換.

    fukusho_label.py:1048-1087 の ``_df_to_tuples_label`` パターンを複製。
    型変換:
      - ``model_type`` / ``model_version`` / ``feature_snapshot_id`` /
        ``calib_method`` / ``jyocd`` / ``nichiji`` / ``split`` → str
      - ``as_of_datetime`` → datetime (そのまま)
      - ``year`` / ``kaiji`` / ``racenum`` / ``umaban`` / ``kettonum`` → int
      - ``p_fukusho_hit`` → float
      - ``race_date`` → date (pd.Timestamp → .date())
      - ``is_primary`` → bool (None→False 正規化・Phase 6 D-09 / REVIEW HIGH#8)

    Parameters
    ----------
    df : pd.DataFrame
        ``PREDICTION_COLUMNS`` 列を持つ DataFrame。

    Returns
    -------
    list[tuple]
        ``PREDICTION_COLUMNS`` 順の tuple list。
    """
    out: list[tuple] = []
    for _, row in df.iterrows():
        vals: list[Any] = []
        for c in PREDICTION_COLUMNS:
            v = row.get(c)
            if c == "race_date":
                if v is None or _is_na(v):
                    vals.append(None)
                elif hasattr(v, "isoformat"):
                    vals.append(v)
                else:
                    try:
                        vals.append(pd.Timestamp(v).date())
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
                    vals.append(float(v))
            elif c in _BOOL_COLS:
                # Phase 6 D-09 (REVIEW HIGH#8): None/NaN は False に正規化（NOT NULL 整合）。
                # True/False は bool(v) で正規化。その他の型は厳格に ValueError（silent fallback 禁止）。
                if v is None or _is_na(v):
                    vals.append(False)
                elif isinstance(v, bool):
                    vals.append(bool(v))
                else:
                    raise ValueError(
                        f"_df_to_prediction_tuples: bool col {c!r} got non-bool value "
                        f"{v!r} (type={type(v).__name__}). Expected True/False/None "
                        "(REVIEW HIGH#8: is_primary NOT NULL DEFAULT false)."
                    )
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
# _idempotent_load_prediction — model_version スコープ staging-swap
# ---------------------------------------------------------------------------


def _idempotent_load_prediction(
    write_cur: Cursor,
    rows: list[tuple],
    *,
    reader_role: str,
) -> str:
    """staging-swap + model_version スコープ DELETE→INSERT で ``prediction.fukusho_prediction`` を永続化.

    review HIGH#1 / Cross-Plan #3: 全テーブル置換 (DROP+RENAME) でなく model_version
    スコープ置換を採用。同一 model_type+model_version の行のみ DELETE → INSERT し、
    他 model_type/version の行は保持する。

    Parameters
    ----------
    write_cur : Cursor
        書込用 cursor (``make_pool(role='etl')`` 由来)。同一トランザクション内で実行。
    rows : list[tuple]
        ``PREDICTION_COLUMNS`` 順の tuple list。空リストは RuntimeError。
    reader_role : str
        reader ロール名 (``settings.db_reader_role``)。現状 GRANT 再発行は schema.py の
        ALTER DEFAULT PRIVILEGES でカバーされるが、将来の RENAME 等に備えて引数として保持。

    Returns
    -------
    str
        ``md5(string_agg(...))`` checksum。当該 model_type+model_version の行のみの
        checksum・ORDER BY PK 11カラムで安定。呼出側が2回実行で一致を検証。

    Raises
    ------
    RuntimeError
        空入力 (rows=[])・staging rowcount 不一致の時。
    ValueError
        rows に複数の (model_type, model_version) が混在する時 (review HIGH#1)。
    """
    # --- Step 1: advisory lock (CR-04(b)・並行 swap を直列化) ---
    write_cur.execute(
        SQL("SELECT pg_advisory_xact_lock(hashtext({}))").format(Placeholder()),
        (_PREDICTION_LOCK_KEY,),
    )

    # --- Step 2: 空入力拒否 (CR-04(a)・silent data loss 防止) ---
    if not rows:
        raise RuntimeError(
            f"_idempotent_load_prediction({_PREDICTION_TABLE!r}): refusing to load "
            "empty input (0 rows). Investigate predict pipeline — silent data loss "
            "prevented (CR-04)."
        )

    # --- Step 3: model_version 抽出と単一性 assert (review HIGH#1) ---
    cols = list(PREDICTION_COLUMNS)
    mt_idx = cols.index("model_type")
    mv_idx = cols.index("model_version")
    fs_idx = cols.index("feature_snapshot_id")
    ao_idx = cols.index("as_of_datetime")

    model_types = {r[mt_idx] for r in rows}
    model_versions = {r[mv_idx] for r in rows}
    feature_snapshot_ids = {r[fs_idx] for r in rows}
    as_of_datetimes = {r[ao_idx] for r in rows}

    if len(model_types) != 1 or len(model_versions) != 1:
        raise ValueError(
            "_idempotent_load_prediction: rows contain multiple "
            f"(model_type, model_version) pairs — got "
            f"model_types={sorted(model_types)!r}, "
            f"model_versions={sorted(model_versions)!r}. "
            "Call load_predictions once per (model_type, model_version) "
            "(review HIGH#1 / Cross-Plan #3: model_version scoped swap)."
        )
    if len(feature_snapshot_ids) != 1:
        raise ValueError(
            f"_idempotent_load_prediction: rows contain multiple feature_snapshot_id: "
            f"{sorted(feature_snapshot_ids)!r}. Expected single feature_snapshot_id "
            "per load call."
        )
    if len(as_of_datetimes) != 1:
        raise ValueError(
            f"_idempotent_load_prediction: rows contain multiple as_of_datetime: "
            f"{as_of_datetimes!r}. Expected single as_of_datetime per load call."
        )

    model_type = next(iter(model_types))
    model_version = next(iter(model_versions))

    # --- Step 4: CREATE staging (INCLUDING ALL・PK/INDEX/NOT NULL 継承) ---
    write_cur.execute(
        SQL("CREATE TABLE IF NOT EXISTS {} (LIKE {} INCLUDING ALL)").format(
            Identifier("prediction", "fukusho_prediction_staging"),
            Identifier("prediction", "fukusho_prediction"),
        )
    )

    # --- Step 5: TRUNCATE staging ---
    write_cur.execute(
        SQL("TRUNCATE {}").format(Identifier("prediction", "fukusho_prediction_staging"))
    )

    # --- Step 6: executemany INSERT into staging ---
    cols_sql = SQL(", ").join([Identifier(c) for c in cols])
    placeholders_sql = SQL(", ").join([Placeholder()] * len(cols))
    insert_staging_sql = SQL("INSERT INTO {} ({}) VALUES ({})").format(
        Identifier("prediction", "fukusho_prediction_staging"),
        cols_sql,
        placeholders_sql,
    )
    write_cur.executemany(insert_staging_sql, rows)

    # --- Step 7: rowcount verify via SELECT count(*) (WR-06) ---
    write_cur.execute(
        SQL("SELECT count(*) FROM {}").format(
            Identifier("prediction", "fukusho_prediction_staging")
        )
    )
    actual = int(write_cur.fetchone()[0])
    if actual != len(rows):
        raise RuntimeError(
            f"_idempotent_load_prediction: staging table has {actual} rows, "
            f"expected {len(rows)} (WR-06 rowcount verification via SELECT count(*))."
        )

    # --- Step 8: model_version スコープ DELETE from 本テーブル (review HIGH#1) ---
    # 全テーブル TRUNCATE でなく・同一 model_type+model_version の行のみ DELETE。
    # 他 model_type/version の行は保持される (silent 履歴破壊防止)。
    write_cur.execute(
        SQL("DELETE FROM {} WHERE {} = {} AND {} = {}").format(
            Identifier("prediction", "fukusho_prediction"),
            Identifier("model_type"),
            Placeholder(),
            Identifier("model_version"),
            Placeholder(),
        ),
        (model_type, model_version),
    )

    # --- Step 9: INSERT staging → 本テーブル (Cycle 2 NEW-3: 明示的列リスト) ---
    # ワイルドカード列展開 (SELECT * ) でなく cols_sql を SELECT 句にも使用
    # (将来 DDL 列追加/順序変更で誤列挿入防止・Cycle 2 NEW-3)。
    # grep 検査 ``grep -c 'SELECT \* FROM prediction.fukusho_prediction_staging' == 0``
    # を満たすため・実 SQL 文には wild-card を使わない。
    insert_main_sql = SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        Identifier("prediction", "fukusho_prediction"),
        cols_sql,
        cols_sql,
        Identifier("prediction", "fukusho_prediction_staging"),
    )
    write_cur.execute(insert_main_sql)

    # --- Step 10: DROP staging (クリーンアップ) ---
    write_cur.execute(
        SQL("DROP TABLE {}").format(Identifier("prediction", "fukusho_prediction_staging"))
    )

    # --- Step 11: checksum 返却 (review HIGH#1: model_version スコープ・ORDER BY PK 11) ---
    # md5(string_agg(md5(row(cols_csv)::text), '' ORDER BY PK 11カラム))
    # WHERE model_type+model_version で scope (当該 model_version の行のみ)
    cols_csv_sql = SQL(", ").join([Identifier(c) for c in cols])
    order_by_sql = SQL(", ").join([Identifier(c) for c in _PK_ORDER_COLUMNS])
    checksum_sql = SQL(
        "SELECT md5(string_agg(md5(row({})::text), '' ORDER BY {})) "
        "FROM {} WHERE {} = {} AND {} = {}"
    ).format(
        cols_csv_sql,
        order_by_sql,
        Identifier("prediction", "fukusho_prediction"),
        Identifier("model_type"),
        Placeholder(),
        Identifier("model_version"),
        Placeholder(),
    )
    write_cur.execute(checksum_sql, (model_type, model_version))
    checksum_row = write_cur.fetchone()
    checksum = str(checksum_row[0]) if checksum_row and checksum_row[0] is not None else ""

    return checksum


# ---------------------------------------------------------------------------
# load_predictions — 公開 API (薄い wrapper)
# ---------------------------------------------------------------------------


def load_predictions(
    write_cur: Cursor,
    prediction_df: pd.DataFrame,
    reader_role: str | None = None,
) -> str:
    """prediction DataFrame を ``prediction.fukusho_prediction`` に idempotent load する.

    ``_df_to_prediction_tuples`` → ``_idempotent_load_prediction`` の薄い wrapper。
    呼出側は**1 model_type+model_version 単位**で呼ぶ前提 (複数 model_version を統合
    DataFrame で渡すと ``ValueError``・run_train_predict は model_type 毎に呼出)。

    Parameters
    ----------
    write_cur : Cursor
        書込用 cursor (``make_pool(role='etl')`` 由来・同一トランザクション)。
    prediction_df : pd.DataFrame
        ``PREDICTION_COLUMNS`` 列を持つ予測 DataFrame (``predict_p_fukusho`` の戻り値)。
        単一 (model_type, model_version, feature_snapshot_id, as_of_datetime) のみ含むこと。
    reader_role : str | None
        reader ロール名。``None`` の場合は ``Settings().db_reader_role`` から取得。

    Returns
    -------
    str
        ``_idempotent_load_prediction`` が返す md5 checksum。
        2回連続実行で一致することを呼出側で検証 (idempotent verify)。

    Raises
    ------
    RuntimeError
        空入力の時。
    ValueError
        複数 (model_type, model_version) が混在する時。
    """
    if reader_role is None:
        reader_role = Settings().db_reader_role

    rows = _df_to_prediction_tuples(prediction_df)
    return _idempotent_load_prediction(write_cur, rows, reader_role=reader_role)


__all__ = [
    "PREDICTION_COLUMNS",
    "_PREDICTION_TABLE",
    "_df_to_prediction_tuples",
    "_idempotent_load_prediction",
    "load_predictions",
]
