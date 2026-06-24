# ruff: noqa: E501  (本ファイルは SQL リテラル・長い docstring を保持するため行長は緩和・src/db/prediction_load.py・src/db/backtest_load.py と同一慣例)
"""Phase 7 Presentation DB/JSON 読込 loader（D-04 DRY・readonly pool・§19.1 再現性聖域）.

UI (Streamlit) と CLI (``scripts/run_export_*.py``) が共有する**純粋 loader 関数**と
UI 専用の ``@st.cache_data`` 付き cached wrapper を提供する (D-04 LOCKED・REVIEW MEDIUM-4)。

**Open Question #1/#2 解決経路（BLOCKER-1 正経路・JODDS snapshot + compute_ev_and_rank 再計算）:**

``prediction.fukusho_prediction`` テーブルは ``p_fukusho_hit`` + provenance (model_type/
model_version/feature_snapshot_id/as_of_datetime + PK RACE_KEY 7 + race_date + is_primary)
のみ (src/db/schema.py L59-94)。odds/EV/rank/odds_snapshot_at 列は**全て不存在**。
一方 ``backtest.fukusho_backtest`` (BACKTEST_COLUMNS L77-116) には ``odds_snapshot_at``/
``odds_snapshot_policy``/``EV_lower``/``EV_upper``/``recommend_rank`` は存在するが・
**``fuku_odds_lower``/``fuku_odds_upper`` (odds 値そのもの) は存在しない**。よって
backtest JOIN で odds 値を取得する経路は構造的に不可能。

本モジュールは以下の正経路で odds/EV/rank を取得する:

1. **prediction SELECT (readonly pool・``WHERE is_primary = true`` 絞り・Pitfall 5)**:
   ``p_fukusho_hit`` + provenance + PK RACE_KEY 7 を取得 (主モデル=LightGBM のみ・22,213行)。
2. **JODDS snapshot 取得 (``src/ev/odds_snapshot.py``)**: ``fetch_jodds(cur, years=[...])`` で
   ``public.n_jodds_tanpuku`` + ``n_jodds_tanpukuwaku_head`` JOIN (datakubun='1' 中間固定・D-01)
   の snapshot を取得し・``select_odds_snapshot(jodds_df, race_times, policy)`` で
   ``merge_asof(direction='backward', by=['race_key','umaban'])`` により各馬単位の cutoff 以下
   最大 snapshot を選択。戻り値に ``fuku_odds_lower``/``fuku_odds_upper``/``odds_snapshot_at``
   (選択 snapshot の happyo_datetime・L213/L326)/``odds_source_type``/``odds_missing_reason``
   が含まれる。未来リーク構造的不可 (D-02・HIGH-1 per-horse odds 保証)。
3. **EV/rank 再計算 (``src/ev/ev_rank.py::compute_ev_and_rank`` 純粋関数・REVIEW HIGH-1 順序)**:
   prediction (p_fukusho_hit) + JODDS snapshot (``fuku_odds_lower``/``fuku_odds_upper`` = 内部名)
   を ``(race_key, umaban)`` で結合した DataFrame を ``compute_ev_and_rank`` に渡し
   ``EV_lower``/``EV_upper`` (§11.1 直線積)・``recommend_rank`` (§11.5 階層判定) を算出。
4. **odds 列名 normalize (``normalize_prediction_export_columns``・Step 3 の後)**:
   ``compute_ev_and_rank`` が内部名 ``fuku_odds_*`` を期待するため・**EV 計算の後に**
   ``fuku_odds_lower``/``fuku_odds_upper`` を外部 canonical 名 ``fukusho_odds_lower``/
   ``fukusho_odds_upper`` に rename (REVIEW HIGH-1)。

odds は EV 判定にのみ使用しモデル特徴量には混入しない (D-07 odds 非依存確率 p_fukusho_hit
+ EV 分離・Core Value 直結・§19.1 再現性)。

**read-only 保証 (D-03・Phase 8 TEST-01 前提):**

- ``make_pool(role="readonly")`` (既定) のみ使用・``write_cursor`` / ``make_pool(role="etl")``
  経路を持たない (test_loaders_uses_only_readonly_pool で AST 検証)。
- 全 SQL は psycopg parameterized query (``cur.execute(sql, (params,))``)・f-string/+ 結合禁止
  (test_loaders_uses_parameterized_queries で AST 検証・MEDIUM-3 静的 SELECT 例外あり)。
- ``WHERE is_primary = true`` で主モデル=LightGBM に絞る (test_loaders_predictions_filter_is_primary)。
- ``@st.cache_data`` の ``hash_funcs={ConnectionPool: id}`` で UnhashableParamError 回避 (Pitfall 2)。

参照: 07-02-PLAN.md <objective>/<artifacts_this_phase_produces> / 07-PATTERNS.md §src/ui/loaders.py /
      src/db/connection.py::make_pool (readonly pool analog) /
      src/db/prediction_load.py (psycopg.sql.SQL+Placeholder パターン analog) /
      src/ev/odds_snapshot.py::fetch_jodds + select_odds_snapshot (JODDS 正経路) /
      src/ev/ev_rank.py::compute_ev_and_rank (EV/rank 純粋関数・内部名 fuku_odds_* 期待)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from psycopg import Cursor
from psycopg_pool import ConnectionPool

from src.config.settings import Settings
from src.db.connection import make_pool, readonly_cursor
from src.ev.ev_rank import compute_ev_and_rank
from src.ev.odds_snapshot import fetch_jodds, select_odds_snapshot
from src.model.data import make_race_key
from src.ui.csv_columns import BACKTEST_CSV_COLUMNS, PREDICTION_CSV_COLUMNS
from src.ui.csv_columns import normalize_prediction_export_columns as _normalize_odds_columns
from src.ui.jyocd_map import load_jyocd_map

# ---------------------------------------------------------------------------
# 定数（REVIEW HIGH-3 / HIGH-4 解決）
# ---------------------------------------------------------------------------

# race_id canonical 区切り文字（REVIEW HIGH-3・表示専用 canonical ラベル）。
# DB 上の JOIN キー race_key (src/model/data.py::make_race_key・5部 year-jyocd-kaiji-nichiji-racenum)
# とは別物。build_race_id は人間可読な CSV/UI 表示のための派生列生成のみを担う。
_RACE_ID_DELIM = "-"

# EV 計算に用いた strategy バージョン（REVIEW HIGH-4・"latest backtest" 推論廃止）。
# 予測 CSV/UI の backtest_strategy_version 列に定数として付与する。これは「EV 計算に用いた
# strategy バージョン」を示し・予測行の再現性来歴そのものではない（docstring 明記）。
# backtest 戦略の来歴は OUT-02 backtest CSV 側の backtest_strategy_version 列で別途担保される。
EV_STRATEGY_VERSION = "fukusho_ev_v1"


# ---------------------------------------------------------------------------
# make_readonly_pool — UI/CLI 共有 readonly pool wrapper (PATTERNS shared pattern 2)
# ---------------------------------------------------------------------------


def make_readonly_pool(settings: Settings) -> ConnectionPool:
    """readonly ロールの ConnectionPool を構築する（UI/CLI 共有・PATTERNS shared pattern 2）。

    ``make_pool(settings, role="readonly")`` の薄い wrapper。``role="readonly"`` 固定で
    ``write_cursor`` / ``role="etl"`` 経路を持たない (D-03 read-only 保証・test で検証)。
    """
    return make_pool(settings, role="readonly")


# ---------------------------------------------------------------------------
# build_race_id — 表示専用 canonical race_id formatter（REVIEW HIGH-3・NEW-M3）
# ---------------------------------------------------------------------------


def build_race_id(year: Any, jyocd: Any, kaiji: Any, nichiji: Any, racenum: Any) -> str:
    """表示専用 canonical race_id 文字列を組立てる（REVIEW HIGH-3・NEW-M3 ピン留め）。

    ``f"{year}-{jyocd:02d}-{kaiji:02d}-{nichiji:02d}-{racenum:02d}"`` 形式
    (例: ``2024-01-05-06-09``)。year は4桁・jyocd/kaiji/nichiji/racenum は2桁ゼロ埋め。

    **NEW-M3 (race_id vs race_key 役割分離):**

    本関数が返す ``race_id`` (5部) は**表示専用の canonical ラベル**であり・CSV ヘッダ・
    UI 表示のために使う。JODDS snapshot 取得や ``compute_ev_and_rank`` 結合など DB 上の
    JOIN キーには既存の ``race_key`` (``src/model/data.py::make_race_key`` の正準形式・5部)
    を引き続き使用する。``build_race_id`` は DB JOIN キーを置換するものではない。
    """
    return _RACE_ID_DELIM.join(
        [
            str(int(year)) if not isinstance(year, str) else year,
            str(jyocd).zfill(2),
            str(kaiji).zfill(2),
            str(nichiji).zfill(2),
            str(racenum).zfill(2),
        ]
    )


# ---------------------------------------------------------------------------
# normalize_date_range — Streamlit st.date_input 正規化（REVIEW MEDIUM-5・NEW-L1 単一ホーム）
# ---------------------------------------------------------------------------


def normalize_date_range(raw: Any) -> tuple[str | None, str | None]:
    """Streamlit ``st.date_input`` の戻り値を ``(date_from, date_to)`` ISO 文字列に正規化する。

    REVIEW MEDIUM-5 / NEW-L1: ``src/ui/loaders.py`` のみに定義し・Plan 03 ``app.py`` は
    ``from src.ui.loaders import normalize_date_range`` で再利用する（重複定義禁止・単一ホーム）。

    - 空 list/tuple → ``(None, None)`` (bounds なし・全件)
    - 要素1件 → ``(same_day, same_day)`` (同日範囲)
    - 要素2件 → ``(from, to)`` (昇順保証)
    - それ以外 → ``(None, None)`` に fallback

    戻り値は ``date.isoformat()`` 形式の ISO 文字列 (``"YYYY-MM-DD"``)。
    """
    if raw is None:
        return (None, None)
    if isinstance(raw, (list, tuple)):
        if len(raw) == 0:
            return (None, None)
        if len(raw) == 1:
            d = pd.Timestamp(raw[0]).date()
            return (d.isoformat(), d.isoformat())
        if len(raw) >= 2:
            d_from = pd.Timestamp(raw[0]).date()
            d_to = pd.Timestamp(raw[1]).date()
            if d_from > d_to:
                d_from, d_to = d_to, d_from
            return (d_from.isoformat(), d_to.isoformat())
    # 単一 date/datetime/Timestamp の場合
    try:
        d = pd.Timestamp(raw).date()
        return (d.isoformat(), d.isoformat())
    except (TypeError, ValueError):
        return (None, None)


# ---------------------------------------------------------------------------
# _select_predictions — prediction SELECT (readonly・is_primary=true・Pitfall 5)
# ---------------------------------------------------------------------------


def _select_predictions(
    cur: Cursor,
    *,
    date_from: str | None,
    date_to: str | None,
    jyocd_list: list[str] | None,
) -> pd.DataFrame:
    """``prediction.fukusho_prediction`` から主モデル (``is_primary = true``) の予測を SELECT する。

    Pitfall 5 / Phase 6 D-09: ``WHERE is_primary = true`` で主モデル=LightGBM のみに絞る
    (44,426行でなく22,213行)。backtest テーブルへの JOIN は行わない (backtest テーブルに
    odds 値カラム ``fuku_odds_lower``/``fuku_odds_upper`` は不存在・構造的不可能)。

    全フィルタ (date_from/date_to/jyocd_list) は psycopg parameterized query の ``%s``
    placeholder で渡す (V5 Input Validation・T-07-05 mitigate)。
    """
    where_clauses: list[str] = ["is_primary = true"]
    params: list[Any] = []
    if date_from is not None:
        where_clauses.append("race_date >= %s")
        params.append(date_from)
    if date_to is not None:
        where_clauses.append("race_date <= %s")
        params.append(date_to)
    if jyocd_list:
        where_clauses.append("jyocd = ANY(%s)")
        params.append(list(jyocd_list))
    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            model_type, model_version, feature_snapshot_id, as_of_datetime,
            year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
            p_fukusho_hit, race_date, calib_method, is_primary
        FROM prediction.fukusho_prediction
        WHERE {where_sql}
    """
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def _select_race_times(cur: Cursor, pred_df: pd.DataFrame) -> pd.DataFrame:
    """``normalized.n_race`` から予測対象レースの ``race_start_datetime`` を取得する (REVIEW HIGH-2)。

    ``race_times`` DataFrame (``race_key``/``umaban``/``race_start_datetime``) を構築する。
    ``race_start_datetime`` が NULL の行 (出馬表未確定 等) は ``dropna(subset=["race_start_datetime"])``
    で**明示的に除外**する (NULL が select_odds_snapshot の cutoff 計算に混入すると snapshot
    選択が誤るため・fail-loud でなく除外ポリシー・REVIEW HIGH-2 付帯)。
    """
    if len(pred_df) == 0:
        return pd.DataFrame(columns=["race_key", "umaban", "race_start_datetime"])

    # 予測対象の race_key 一意集合を取得 (5部 RACE_KEY・make_race_key 正準形式)
    race_keys_df = pred_df[["year", "jyocd", "kaiji", "nichiji", "racenum"]].drop_duplicates()
    # n_race は race-level (umaban 無し) なので umaban を 1 に固定して race_key を構築し候補とする
    race_keys_df = race_keys_df.copy()
    race_keys_df["race_key"] = make_race_key(race_keys_df)

    years = sorted({int(y) for y in pred_df["year"].unique()})
    cur.execute(
        """
        SELECT year, jyocd, kaiji, nichiji, racenum, race_start_datetime
        FROM normalized.n_race
        WHERE year = ANY(%s)
          AND jyocd BETWEEN '01' AND '10'
        """,
        ([str(y) for y in years],),
    )
    cols = [d.name for d in cur.description]
    race_rows = cur.fetchall()
    race_df = pd.DataFrame(race_rows, columns=cols)
    if len(race_df) == 0:
        return pd.DataFrame(columns=["race_key", "umaban", "race_start_datetime"])

    race_df["race_key"] = make_race_key(race_df)

    # pred_df 側の (race_key, umaban) 組を作り・n_race の race_start_datetime を race_key で結合
    pred_keys = pred_df[["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban"]].copy()
    pred_keys["race_key"] = make_race_key(pred_keys)
    pred_keys["umaban"] = pd.to_numeric(pred_keys["umaban"], errors="coerce").astype("Int64")

    race_times = pred_keys.merge(
        race_df[["race_key", "race_start_datetime"]],
        on="race_key",
        how="left",
    )
    # REVIEW HIGH-2: race_start_datetime が NULL の行を明示的に除外
    race_times = race_times.dropna(subset=["race_start_datetime"])
    return race_times[["race_key", "umaban", "race_start_datetime"]].reset_index(drop=True)


def _select_uma_race_meta(cur: Cursor, pred_df: pd.DataFrame) -> pd.DataFrame:
    """``normalized.n_uma_race`` から馬名 (bamei)・枠番 (wakuban) を取得する (PATTERNS Data Provenance)。

    PK (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum) で結合する。
    """
    if len(pred_df) == 0:
        return pd.DataFrame(
            columns=[
                "year",
                "jyocd",
                "kaiji",
                "nichiji",
                "racenum",
                "umaban",
                "kettonum",
                "bamei",
                "wakuban",
            ]
        )

    years = sorted({int(y) for y in pred_df["year"].unique()})
    cur.execute(
        """
        SELECT year, jyocd, kaiji, nichiji, racenum, umaban, kettonum, bamei, wakuban
        FROM normalized.n_uma_race
        WHERE year = ANY(%s)
          AND jyocd BETWEEN '01' AND '10'
        """,
        ([str(y) for y in years],),
    )
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# 純粋 loader: load_predictions (CLI 直接 import・@st.cache_data なし・REVIEW MEDIUM-4)
# ---------------------------------------------------------------------------


def load_predictions(
    pool: ConnectionPool,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    jyocd_list: list[str] | None = None,
    odds_snapshot_policy: str = "30min_before",
) -> pd.DataFrame:
    """主モデル予測 + JODDS snapshot + EV/rank 再計算で予測 DataFrame を構築する (純粋関数・CLI 直接 import)。

    Open Question #1/#2 解決経路 (BLOCKER-1 正経路) を組込:

    1. prediction SELECT (readonly・``is_primary = true``・Pitfall 5)
    2. JODDS snapshot (``fetch_jodds`` + ``select_odds_snapshot(policy)``)
    3. ``compute_ev_and_rank`` 純粋関数で EV/rank 再計算 (内部名 ``fuku_odds_*`` 期待)
    4. ``normalize_prediction_export_columns`` で ``fuku_*`` → ``fukusho_*`` rename (REVIEW HIGH-1)
    5. n_uma_race から bamei/wakuban を JOIN・jyocd→競馬場名 map・派生列 (race_id/horse_id/競馬場/レース番号/枠番/馬番) 付与

    odds は EV 判定にのみ使用しモデル特徴量には混入しない (D-07 odds 非依存確率 p_fukusho_hit
    + EV 分離・Core Value 直結)。未来リーク構造的不可 (D-02・merge_asof direction='backward')。

    Parameters
    ----------
    pool : ConnectionPool
        ``make_pool(role="readonly")`` 由来の readonly pool。
    date_from, date_to : str | None
        ``race_date`` の期間フィルタ (ISO ``"YYYY-MM-DD"``)。``None`` で bounds なし。
    jyocd_list : list[str] | None
        競馬場コードフィルタ (``["01","05"]`` 等)。``None`` で全場。
    odds_snapshot_policy : str
        JODDS snapshot 取得 policy (default ``"30min_before"``・enum
        ``"30min_before"``/``"10min_before"``)。事前固定・事後選択禁止 (§11.2・BACK-04・NEW-H1)。

    Returns
    -------
    pd.DataFrame
        ``PREDICTION_CSV_COLUMNS`` の全列を含む DataFrame (CSV 生成時の列整列で適用)。
    """
    with readonly_cursor(pool) as cur:
        # --- Step 1: prediction SELECT (is_primary=true・Pitfall 5) ---
        pred_df = _select_predictions(
            cur,
            date_from=date_from,
            date_to=date_to,
            jyocd_list=jyocd_list,
        )

    if len(pred_df) == 0:
        return pd.DataFrame(columns=list(PREDICTION_CSV_COLUMNS))

    # race_key 構築 (make_race_key 正準形式・5部・DB JOIN 用)
    pred_df = pred_df.copy()
    pred_df["race_key"] = make_race_key(pred_df)
    pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")

    # --- Step 2: JODDS snapshot 取得 (src/ev/odds_snapshot.py・HIGH-2 race_start_datetime ピン留め) ---
    with readonly_cursor(pool) as cur:
        years = sorted({int(y) for y in pred_df["year"].unique()})
        jodds_df = fetch_jodds(cur, years=[str(y) for y in years])
        race_times = _select_race_times(cur, pred_df)

    if len(race_times) == 0:
        # snapshot 候補なし → odds/EV/rank 全て欠損 (silent fallback 禁止・§11.3)
        snapshot_df = pd.DataFrame(
            columns=[
                "race_key",
                "umaban",
                "fuku_odds_lower",
                "fuku_odds_upper",
                "odds_snapshot_at",
                "odds_source_type",
                "odds_missing_reason",
            ]
        )
    else:
        snapshot_df = select_odds_snapshot(jodds_df, race_times, policy=odds_snapshot_policy)
        # REVIEW HIGH-2 付帯: odds_snapshot_at NULL 行は odds_missing_reason="no_snapshot" マーク
        # (select_odds_snapshot は既に no_bet_empty 等を付けるが・race_times から除外された馬は
        # ここ到達しない・silent 0 埋め禁止・CSV では空欄)
        snapshot_df.loc[snapshot_df["odds_snapshot_at"].isna(), "odds_missing_reason"] = (
            snapshot_df.loc[snapshot_df["odds_snapshot_at"].isna(), "odds_missing_reason"].fillna(
                "no_snapshot"
            )
        )

    # prediction + snapshot 結合 (race_key, umaban)
    snapshot_df["umaban"] = pd.to_numeric(snapshot_df["umaban"], errors="coerce").astype("Int64")
    merged = pred_df.merge(
        snapshot_df[
            [
                "race_key",
                "umaban",
                "fuku_odds_lower",
                "fuku_odds_upper",
                "odds_snapshot_at",
                "odds_source_type",
                "odds_missing_reason",
            ]
        ],
        on=["race_key", "umaban"],
        how="left",
    )

    # --- Step 3: EV/rank 再計算 (compute_ev_and_rank・内部名 fuku_odds_* 期待・HIGH-1 順序) ---
    # compute_ev_and_rank は内部名 fuku_odds_lower/fuku_odds_upper を期待するため・
    # rename (Step 3.5) の前に実行する (rename 後だと KeyError)。
    merged = compute_ev_and_rank(merged)

    # --- Step 3.5: odds 列名 normalize (REVIEW HIGH-1・Step 3 の後) ---
    merged = _normalize_odds_columns(merged)

    # --- Step 4: n_uma_race から bamei/wakuban を JOIN ---
    with readonly_cursor(pool) as cur:
        uma_meta = _select_uma_race_meta(cur, pred_df)
    if len(uma_meta) > 0:
        merged = merged.merge(
            uma_meta[
                [
                    "year",
                    "jyocd",
                    "kaiji",
                    "nichiji",
                    "racenum",
                    "umaban",
                    "kettonum",
                    "bamei",
                    "wakuban",
                ]
            ],
            on=["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"],
            how="left",
        )
    else:
        merged["bamei"] = None
        merged["wakuban"] = None

    # --- Step 5: 派生列・jyocd→競馬場名・再現性スタンプ ---
    jyocd_map = load_jyocd_map()
    merged["競馬場"] = merged["jyocd"].map(jyocd_map)
    # 表示専用 canonical race_id (REVIEW HIGH-3・NEW-M3・DB JOIN キー race_key とは別物)
    merged["race_id"] = [
        build_race_id(y, j, k, n, r)
        for y, j, k, n, r in zip(
            merged["year"],
            merged["jyocd"],
            merged["kaiji"],
            merged["nichiji"],
            merged["racenum"],
            strict=True,
        )
    ]
    merged["レース番号"] = merged["racenum"]
    merged["horse_id"] = merged["kettonum"]  # horse_id 代用 (PATTERNS Data Provenance)
    merged["horse_name"] = merged["bamei"]
    merged["枠番"] = merged["wakuban"]
    merged["馬番"] = merged["umaban"]
    merged["prediction_created_at"] = merged[
        "as_of_datetime"
    ]  # as_of_datetime 代用 (csv_columns.py docstring)
    # 再現性スタンプ: odds_snapshot_policy は事前固定値の定数列 (事後選択禁止・§11.2・BACK-04)
    merged["odds_snapshot_policy"] = odds_snapshot_policy
    # backtest_strategy_version: EV_STRATEGY_VERSION 定数付与 (REVIEW HIGH-4・"latest backtest" 推論廃止)
    # これは「EV 計算に用いた strategy バージョン」を示し・予測行の再現性来歴そのものではない。
    merged["backtest_strategy_version"] = EV_STRATEGY_VERSION
    # race_start_datetime は race_times 経由で取得済みの snapshot_df には無い・n_race から再結合
    # (HIGH-2: race_times から除外された馬は race_start_datetime も NaN・CSV では空欄)
    race_start = _select_race_times_for_merged(pool, pred_df)
    if len(race_start) > 0:
        merged = merged.merge(
            race_start[["race_key", "umaban", "race_start_datetime"]],
            on=["race_key", "umaban"],
            how="left",
        )
    else:
        merged["race_start_datetime"] = pd.NaT

    return merged


def _select_race_times_for_merged(pool: ConnectionPool, pred_df: pd.DataFrame) -> pd.DataFrame:
    """load_predictions の後段で race_start_datetime 列を付与するための helper (HIGH-2)。

    ``_select_race_times`` は select_odds_snapshot 用に NULL 除外済みの race_times を返すが・
    最終 DataFrame の race_start_datetime 列は予測対象馬全件に付与する必要があるため・
    改めて NULL 含む全件を取得する (除外された馬は NaN・CSV では空欄)。
    """
    if len(pred_df) == 0:
        return pd.DataFrame(columns=["race_key", "umaban", "race_start_datetime"])
    with readonly_cursor(pool) as cur:
        years = sorted({int(y) for y in pred_df["year"].unique()})
        cur.execute(
            """
            SELECT year, jyocd, kaiji, nichiji, racenum, race_start_datetime
            FROM normalized.n_race
            WHERE year = ANY(%s)
              AND jyocd BETWEEN '01' AND '10'
            """,
            ([str(y) for y in years],),
        )
        cols = [d.name for d in cur.description]
        race_df = pd.DataFrame(cur.fetchall(), columns=cols)
    if len(race_df) == 0:
        return pd.DataFrame(columns=["race_key", "umaban", "race_start_datetime"])
    race_df["race_key"] = make_race_key(race_df)
    pred_keys = pred_df[["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban"]].copy()
    pred_keys["race_key"] = make_race_key(pred_keys)
    pred_keys["umaban"] = pd.to_numeric(pred_keys["umaban"], errors="coerce").astype("Int64")
    out = pred_keys.merge(
        race_df[["race_key", "race_start_datetime"]],
        on="race_key",
        how="left",
    )
    return out[["race_key", "umaban", "race_start_datetime"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 純粋 loader: load_backtests (CLI 直接 import・@st.cache_data なし・REVIEW MEDIUM-4)
# ---------------------------------------------------------------------------


def _select_backtests(
    cur: Cursor,
    *,
    backtest_id: str | None,
) -> pd.DataFrame:
    """``backtest.fukusho_backtest`` から全行 SELECT する (is_primary 絞り不要・backtest_id で識別)。"""
    if backtest_id is not None:
        cur.execute(
            """
            SELECT backtest_id, backtest_strategy_version, odds_snapshot_policy,
                   train_period_start, train_period_end, test_period_start, test_period_end,
                   model_type, model_version, feature_snapshot_id,
                   year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
                   selected_flag, stake, refund_flag, refund_amount, payout_amount, profit,
                   effective_stake, fukusho_hit_validated, recommend_rank, EV_lower, EV_upper,
                   odds_snapshot_at, odds_source_type, odds_missing_reason, race_date
            FROM backtest.fukusho_backtest
            WHERE backtest_id = %s
            """,
            (backtest_id,),
        )
    else:
        cur.execute(
            """
            SELECT backtest_id, backtest_strategy_version, odds_snapshot_policy,
                   train_period_start, train_period_end, test_period_start, test_period_end,
                   model_type, model_version, feature_snapshot_id,
                   year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
                   selected_flag, stake, refund_flag, refund_amount, payout_amount, profit,
                   effective_stake, fukusho_hit_validated, recommend_rank, EV_lower, EV_upper,
                   odds_snapshot_at, odds_source_type, odds_missing_reason, race_date
            FROM backtest.fukusho_backtest
            """
        )
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def load_backtests(
    pool: ConnectionPool,
    *,
    backtest_id: str | None = None,
) -> pd.DataFrame:
    """backtest 全行 SELECT から OUT-02 表示列を派生した DataFrame を返す (純粋関数・CLI 直接 import)。

    ``is_primary`` 絞り不要 (backtest_id で識別)。SELECT 列は BACKTEST_CSV_COLUMNS の来源となる
    DB 列。python 側で ``train_period`` (``f"{train_period_start}〜{train_period_end}"``) /
    ``validation_period`` (``f"{test_period_start}〜{test_period_end}"``) / ``race_id``
    (race_key 文字列) / ``horse_id`` (=``kettonum``) の各 OUT-02 表示列を派生する
    (PATTERNS Data Provenance・backtest 戦略/期間表)。

    Parameters
    ----------
    pool : ConnectionPool
        ``make_pool(role="readonly")`` 由来の readonly pool。
    backtest_id : str | None
        指定時は単一 backtest・未指定時は全件。

    Returns
    -------
    pd.DataFrame
        ``BACKTEST_CSV_COLUMNS`` の全列を含む DataFrame。
    """
    with readonly_cursor(pool) as cur:
        df = _select_backtests(cur, backtest_id=backtest_id)

    if len(df) == 0:
        return pd.DataFrame(columns=list(BACKTEST_CSV_COLUMNS))

    df = df.copy()
    # OUT-02 表示列派生 (PATTERNS Data Provenance)
    df["train_period"] = (
        df["train_period_start"].astype(str) + "〜" + df["train_period_end"].astype(str)
    )
    df["validation_period"] = (
        df["test_period_start"].astype(str) + "〜" + df["test_period_end"].astype(str)
    )
    # race_id: build_race_id で表示専用 canonical ラベル生成 (REVIEW HIGH-3・DB JOIN キー race_key とは別物)
    df["race_id"] = [
        build_race_id(y, j, k, n, r)
        for y, j, k, n, r in zip(
            df["year"],
            df["jyocd"],
            df["kaiji"],
            df["nichiji"],
            df["racenum"],
            strict=True,
        )
    ]
    df["horse_id"] = df["kettonum"]  # horse_id 代用 (PATTERNS Data Provenance)
    return df


# ---------------------------------------------------------------------------
# 純粋 loader: load_segment_json (CLI 直接 import・@st.cache_data なし・REVIEW MEDIUM-4)
# ---------------------------------------------------------------------------


def load_segment_json(axis: str) -> dict[str, Any]:
    """``reports/06-segments/<axis>.json`` を読込む (純粋関数・CLI 直接 import・PATTERNS L164-171)。

    存在しない場合は ``{}`` を返す (empty state・UI-SPEC Copywriting で案内)。
    """
    path = Path("reports/06-segments") / f"{axis}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# UI 用 cached wrapper (REVIEW MEDIUM-4 完全化・純粋関数の上に @st.cache_data を被せる)
# ---------------------------------------------------------------------------


@st.cache_data(hash_funcs={ConnectionPool: id})
def load_predictions_cached(
    pool: ConnectionPool,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    jyocd_list: list[str] | None = None,
    odds_snapshot_policy: str = "30min_before",
) -> pd.DataFrame:
    """``load_predictions`` の ``@st.cache_data`` 付き UI 用 wrapper (REVIEW MEDIUM-4・Pitfall 2)。

    Pitfall 2: ``ConnectionPool`` は unhashable なため ``hash_funcs={ConnectionPool: id}`` で
    ``UnhashableParamError`` を回避する。CLI は本関数でなく純粋関数 ``load_predictions`` を
    import すること (Streamlit runtime 非依存・REVIEW MEDIUM-4)。内部で純粋 ``load_predictions``
    を呼ぶ。
    """
    return load_predictions(
        pool,
        date_from=date_from,
        date_to=date_to,
        jyocd_list=jyocd_list,
        odds_snapshot_policy=odds_snapshot_policy,
    )


@st.cache_data(hash_funcs={ConnectionPool: id})
def load_backtests_cached(
    pool: ConnectionPool,
    *,
    backtest_id: str | None = None,
) -> pd.DataFrame:
    """``load_backtests`` の ``@st.cache_data`` 付き UI 用 wrapper (REVIEW MEDIUM-4・Pitfall 2)。"""
    return load_backtests(pool, backtest_id=backtest_id)


@st.cache_data
def load_segment_json_cached(axis: str) -> dict[str, Any]:
    """``load_segment_json`` の ``@st.cache_data`` 付き UI 用 wrapper (REVIEW MEDIUM-4)。

    ``axis`` (str) は hashable なため ``hash_funcs`` 不要。
    """
    return load_segment_json(axis)


# ---------------------------------------------------------------------------
# build_*_csv_bytes — UI/CLI 共有・UTF-8 BOM + CRLF・列検証 fail-loud (REVIEW LOW-3)
# ---------------------------------------------------------------------------


def build_prediction_csv_bytes(df: pd.DataFrame) -> bytes:
    """予測 DataFrame を OUT-01 CSV bytes (UTF-8 BOM + CRLF・§16.2 pin 20列) に変換する。

    UI と CLI が共有 (PATTERNS shared pattern 5)。``PREDICTION_CSV_COLUMNS`` の全列が
    DataFrame に存在することを検証し・欠落時は ``raise ValueError`` で fail-loud する
    (silent 欠落回避・REVIEW LOW-3・``assert`` でなく ``raise ValueError`` で ``python -O``
    でも無効化されない)。

    Parameters
    ----------
    df : pd.DataFrame
        ``PREDICTION_CSV_COLUMNS`` の全列を含む予測 DataFrame。

    Returns
    -------
    bytes
        UTF-8 BOM + CRLF 改行の CSV bytes (Excel 互換・UI-SPEC CSV Export Contract)。

    Raises
    ------
    ValueError
        ``PREDICTION_CSV_COLUMNS`` のいずれかの列が ``df`` に存在しない時。
    """
    missing = [c for c in PREDICTION_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"予測 DataFrame に必須列がない: {missing}")
    ordered = df[list(PREDICTION_CSV_COLUMNS)]
    return ordered.to_csv(index=False, encoding="utf-8-sig", lineterminator="\r\n").encode(
        "utf-8-sig"
    )


def build_backtest_csv_bytes(df: pd.DataFrame) -> bytes:
    """backtest DataFrame を OUT-02 CSV bytes (UTF-8 BOM + CRLF・§16.2 pin 16列) に変換する。

    ``BACKTEST_CSV_COLUMNS`` の全列が DataFrame に存在することを検証し・欠落時は
    ``raise ValueError`` で fail-loud する (silent 欠落回避・REVIEW LOW-3・Pitfall 3 16列保証)。

    Raises
    ------
    ValueError
        ``BACKTEST_CSV_COLUMNS`` のいずれかの列が ``df`` に存在しない時。
    """
    missing = [c for c in BACKTEST_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"backtest DataFrame に必須列がない: {missing}")
    ordered = df[list(BACKTEST_CSV_COLUMNS)]
    return ordered.to_csv(index=False, encoding="utf-8-sig", lineterminator="\r\n").encode(
        "utf-8-sig"
    )


__all__ = [
    "EV_STRATEGY_VERSION",
    "build_backtest_csv_bytes",
    "build_prediction_csv_bytes",
    "build_race_id",
    "load_backtests",
    "load_backtests_cached",
    "load_predictions",
    "load_predictions_cached",
    "load_segment_json",
    "load_segment_json_cached",
    "make_readonly_pool",
    "normalize_date_range",
]
