# ruff: noqa: E501  (SQL リテラル・長い docstring を保持するため行長は緩和)
"""LABEL-01/02/04: 複勝ラベル ETL 本体（psycopg3 + pandas 明示実装・REVIEWS HIGH #1-#6 対応）。

仕様（02-CONTEXT.md D-01..D-04 / D-06 / D-13 / 02-RESEARCH.md Pitfall 1-6 / REVIEWS HIGH #1/#3/#4/#5 / NEW HIGH #2/#3 / MEDIUM）:

  - **D-08 / Phase 1 踏襲:** psycopg3 + Python 明示 ETL。DuckDB は使用しない（§12.1）。
  - **D-06 raw read-only:** 全 raw SELECT は readonly pool で SELECT のみ。write_pool は
    ``label`` スキーマのみに書込む（``public.n_*`` には一切 UPDATE/DELETE/INSERT を発行しない）。
  - **D-04 観測事実ベース:** ``label_validation_status`` 4値（validated/inferred/dead_heat/
      unresolved）の判定は HR/SE の観測事実のみで行う（推測なし・silent fallback 禁止・D-13）。
  - **Pitfall 1:** 実カラム名は ``timediff``（EveryDB2 マニュアルの ``TimeDIFN`` ではない）。
      ``bataijyu``（``bataiju`` ではない）。本モジュールは両者を実カラム名で SELECT する。
  - **WR-04 修正（iteration 3・最終）:** ``fukusho_payout_places`` は **HR ``PayFukusyoUmaban``
      の実際の払戻馬番数（``payout_count`` = 非``'00'`` slot 数）** で決定する（D-01 厳格・
      spec note の本来の意図）。``torokutosu``（登録）/``syussotosu``（完走）は代理値であり、
      発走前取消・発走後中止レースで実際の払戻馬番数と一致しないため ``payout_places`` 計算に
      は不使用。``torokutosu`` は ``is_fukusho_sale_available``（複勝発売の有無・出馬表発表時
      決定）と ``sales_start_entry_count`` 代理値としてのみ使用。``places_5_to_7_horses``(2)/
      ``places_8_or_more_horses``(3) は JRA 規則の参考値（実計算は HR 払戻馬番数を使用・
      同着拡張で ``payout_count`` が 4-5 になる場合は HR 観測事実に従う）。実DB観測で
      ``torokutosu``→``syussotosu``→``payout_count`` と3回検証し、``payout_count`` が唯一の
      正解と判明した（iteration 1/2 の ``torokutosu``/``syussotosu`` ベースはいずれも不完全・
      旧 Pitfall 3 は撤回）。
  - **REVIEWS HIGH #1:** ``label.fukusho_label`` は ``sales_start_entry_count_confidence``
      （='inferred'）と ``sales_start_entry_count_source``（='torokutosu_proxy'）を
      ``label_validation_status`` から独立した varchar(16) NOT NULL カラムとして持つ。
  - **REVIEWS HIGH #3:** ``_idempotent_load_label`` は staging-swap（CREATE ... INCLUDING ALL
      → TRUNCATE → INSERT → atomic DROP+RENAME）で idempotent 書込。RENAME 後に明示的に
      ``GRANT SELECT ON label.fukusho_label TO {reader_role}`` を再発行し、``TO PUBLIC`` は
      一切使用しない。``INCLUDING ALL`` で PK/インデックス/NOT NULL/コメントが staging 表に
      継承され、RENAME 後も失われない。2回連続実行で row count + checksum が一致する。
  - **REVIEWS HIGH #4:** ``_select_se_state`` は ``datakubun IN ('7', '9')`` で SELECT する。
      ``datakubun='7'`` 単独では race_cancelled（DataKubun='9'）の 376 SE 行が SELECT から
      落とされ silent data loss になる。
  - **REVIEWS HIGH #5:** ``_canonicalize_markers`` は ``label_spec.yaml`` の
      ``se_marker_canonicalization`` sentinel 集合のみで判定する。単一文字列等価比較
      （例: ``harontimel3 == '999.0'``）は禁止・sentinel 集合への ``in`` 判定のみ許可。
      raw varchar と numeric cast と missing/null の3表現で同一結果を返す。
  - **REVIEWS NEW HIGH #2:** ``_select_se_state`` の ``timediff`` merge は両側
      ``datakubun IN ('7','9')`` でフィルタし、merge キーに ``datakubun`` を含めて strict
      1:1 merge を保証する。public 側に複数 DataKubun 行が存在しても PK+datakubun で厳密
      1:1 となり SE 行の増殖を構造的に防止。merge 前後で ``len(se_df) == len(merged_df)``
      を assert・不一致時は RuntimeError で fail-fast（D-13 silent fallback 禁止）。
  - **REVIEWS NEW HIGH #3:** ``_canonicalize_markers`` は必ず ``pd.isna(v)`` で missing/null
      を先に捕捉し sentinel ``"__MISSING__"`` にマップしてから ``str()`` に回す。
      ``NaN``→``str(NaN)='nan'`` / ``pd.NA``→``str(pd.NA)='<NA>'`` / ``None``→``str(None)='None'``
      が sentinel 集合外と誤判定され ``time_present=True`` → ``is_dead_loss=True`` になる
      silent corruption を構造的に回避する。missing time は ``time_present=False`` →
      ``is_race_excluded`` または ``unresolved`` に分類される。
  - **REVIEWS HIGH #6:** ``compute_is_model_eligible`` の適用順序で syubetucd 障害/新馬が
      先に評価される。``is_dead_loss`` は適用順序の判定対象に入らず、競走中止馬が他の理由
      で不適格になる場合（例: 障害レースで競走中止）、``ineligibility_reason`` には
      ``'obstacle'`` が格納され ``'dead_loss'`` 由来にはならない。Plan 04 がこの不変条件を検査する。

下流（Phase 3 features / Phase 4 model / Phase 5 backtest）は ``label_validation_status`` と
``is_model_eligible`` でフィルタする。本モジュールは予測目標の正 = リーク防止と同等の聖域。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from psycopg import Cursor
from psycopg.sql import SQL, Identifier
from psycopg_pool import ConnectionPool

from src.config.settings import Settings
from src.etl.filters import PROJECT_WINDOW_FILTER

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("src/config/label_spec.yaml")


# ---------------------------------------------------------------------------
# label_spec.yaml loader（class_normalize.load_class_config パターン踏襲）
# ---------------------------------------------------------------------------
_REQUIRED_SPEC_KEYS = (
    "label_generation_version",
    "status_values",
    "payout_places_rules",
    "se_marker_rules",
    "se_marker_canonicalization",
    "se_datakubun_inclusion",
    "sales_start_entry_count",
    "model_ineligibility_syubetucd",
    "newcomer_class_name",
    "class_eligibility",
    "unresolved_strategy",
)


def load_label_spec(path: str | Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """``label_spec.yaml`` を読み込み dict で返す（D-07 Git 管理・D-13 silent fallback 禁止）。

    必須キー（``_REQUIRED_SPEC_KEYS``）が1つでも欠損した場合は ``ValueError`` で fail-fast
    する（class_normalize.load_class_config と同形式）。未知コード戦略も同様。
    """
    with Path(path).open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(f"label_spec.yaml は dict でなければなりません: {type(spec)!r}")
    missing = [k for k in _REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(f"label_spec.yaml に必須キーが欠損: {missing} (D-13 silent fallback 禁止)")
    return spec


# ---------------------------------------------------------------------------
# raw からの SELECT（readonly pool・PROJECT_WINDOW_FILTER で JRA + 2015以降に限定）
# CR-06: JRA フィルタの単一の真の源は src.etl.filters（三重定義禁止）。
# ---------------------------------------------------------------------------
_HARAI_SELECT_COLUMNS = [
    "year",
    "monthday",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "datakubun",  # 月曜確定='2' / 速報='1' / レース全体中止='9'
    "torokutosu",  # 登録頭数（出馬表発表時・sales_start_entry_count 代理値）
    "syussotosu",  # 出走頭数（参考・final_starter_count）
    "fuseirituflag2",  # 複勝不成立フラグ
    "tokubaraiflag2",  # 複勝特払フラグ
    "henkanflag2",  # 複勝返還フラグ
    "payfukusyoumaban1",  # 複勝的中馬番 slot1..5（同着で拡張）
    "payfukusyoumaban2",
    "payfukusyoumaban3",
    "payfukusyoumaban4",
    "payfukusyoumaban5",
]


def _select_raw_harai(read_cur: Cursor) -> pd.DataFrame:
    """raw ``public.n_harai`` から JRA 限定で SELECT（D-06 raw read-only・Pitfall 2）。

    全 varchar をそのまま SELECT し、pandas 側で明示キャストする（Phase 1 D-08 踏襲）。
    """
    cols = ", ".join(_HARAI_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM public.n_harai WHERE {PROJECT_WINDOW_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_HARAI_SELECT_COLUMNS)


# ---------------------------------------------------------------------------
# SE state SELECT（REVIEWS HIGH #4 + NEW HIGH #2）
# ---------------------------------------------------------------------------
_SE_SELECT_COLUMNS = [
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
    "kakuteijyuni",  # 確定着順（fukusho_hit_raw 原料）
    "nyusenjyuni",
    "bataijyu",  # 馬体重（実カラム・bataiju でない・Pitfall 1）
    "harontimel3",  # ハロンタイム（marker）
    "harontimel4",  # ハロンタイム（marker・予備）
    "time",  # 走破タイム（競走中止識別・time_present）
    "datakubun",  # 月曜確定='7' / レース全体中止='9'
    # 注: dochakukubun / dochakutosu は normalized.n_uma_race に未格納のため
    # public.n_uma_race 側（_SE_TIMEDIFF_SELECT_COLUMNS）から取得し merge する
    # （参考値・payout-table が権威・MEDIUM #2・下記参照）。
]

# timediff / dochakukubun / dochakutosu は normalized.n_uma_race に未格納
# （Phase 1 normalize.py 未 SELECT）。public.n_uma_race から別 SELECT で取得し merge
# する（NEW HIGH #2: 両側 datakubun IN ('7','9') + merge キーに datakubun を含め
# 1:1 merge・row-multiplication 防止）。
_SE_TIMEDIFF_SELECT_COLUMNS = [
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
    "datakubun",
    "timediff",  # 実カラム名（Pitfall 1・EveryDB2 マニュアル TimeDIFN でない）
    "dochakukubun",  # 同着区分（参考値・payout-table が権威・MEDIUM #2）
    "dochakutosu",  # 同着頭数（参考値）
]


def _select_se_state(read_cur: Cursor) -> pd.DataFrame:
    """SE 状態を ``public.n_uma_race`` から取得（HIGH #4/#2）。

    **HIGH #4**: ``WHERE datakubun IN ('7', '9')`` で SELECT する。``datakubun='7'`` 単独では
    race_cancelled（DataKubun='9'）の 376 SE 行が SELECT から落とされ silent data loss になる。

    **NEW HIGH #2**: ``timediff`` / ``dochakutosu`` / ``dochakukubun`` は
    ``normalized.n_uma_race`` に未格納（Phase 1 normalize.py 未 SELECT）かつ
    ``normalized.n_uma_race`` には ``datakubun`` 列自体が存在しないため、SE state 全体を
    ``public.n_uma_race`` から取得する。両側の SELECT（基本状態 + timediff/参考列）とも
    ``datakubun IN ('7','9')`` でフィルタし、merge キーに ``datakubun`` を含める。
    public 側に複数 DataKubun 行が存在する場合でも PK+datakubun で厳密 1:1 となり SE 行の
    増殖を構造的に防止する。merge 前後で ``len(se_df) == len(merged_df)`` を assert し、
    不一致時は ``RuntimeError`` で fail-fast する（D-13 silent fallback 禁止）。

    **WR-10**: ``how="inner"`` で両側の行完全一致を強制する。``how="left"`` では
    timediff_df 側の余剰行・欠損行（PK 不一致・フィルタ退化）が silent に進み、
    ``timediff`` が NaN になることで競走中止馬が正常馬に誤分類される silent leak 源に
    なった。inner merge + merge 後 ``timediff`` の全行非 NaN assert で構造的に防止する。
    """
    cols = ", ".join(_SE_SELECT_COLUMNS)
    sql = (
        f"SELECT {cols} FROM public.n_uma_race "
        f"WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')"
    )
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    se_df = pd.DataFrame(rows, columns=_SE_SELECT_COLUMNS)

    # timediff + 参考列を public.n_uma_race から取得
    # （NEW HIGH #2: 両側 datakubun IN ('7','9') + 1:1 merge）
    tcols = ", ".join(_SE_TIMEDIFF_SELECT_COLUMNS)
    tsql = (
        f"SELECT {tcols} FROM public.n_uma_race "
        f"WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')"
    )
    # WR-05: 両 SELECT が同一フィルタ（PROJECT_WINDOW_FILTER + datakubun IN ('7','9')）
    # を持つことを直接 assert する。片側だけ退化（'9' が落ちる等）で merge 後に
    # timediff が NaN になる silent data loss を構造的に防止する。
    _required_filter = f"WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')"
    assert _required_filter in sql, (
        f"WR-05: _SE_SELECT 側 SQL が期待フィルタを欠く: {sql!r}"
    )
    assert _required_filter in tsql, (
        f"WR-05: _SE_TIMEDIFF_SELECT 側 SQL が期待フィルタを欠く: {tsql!r}"
    )
    read_cur.execute(tsql)
    trows = read_cur.fetchall()
    timediff_df = pd.DataFrame(trows, columns=_SE_TIMEDIFF_SELECT_COLUMNS)

    # 1:1 merge。merge キーに datakubun を含めて両側等価制約で厳密 1:1 を保証
    # （HIGH #2: public 側に複数 DataKubun 行が存在しても PK+datakubun で 1:1）。
    merge_keys = ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum", "datakubun"]
    pre_len = len(se_df)
    # WR-10: how="inner" で両側一致を強制する。how="left" では:
    #   (a) timediff_df 側に SE 側と一致しない余剰行があっても silent に捨てられ検知不能
    #   (b) timediff_df 側が欠損（行が少ない）と timediff 列が NaN になり silent に進む
    #       → 競走中止馬が正常馬に誤分類される silent leak 源（D-13）
    # inner merge で両側一致を強制し、行数不一致・timediff NaN を即時 RuntimeError で fail-fast。
    merged = se_df.merge(timediff_df, on=merge_keys, how="inner")
    # 行数増殖（duplicate rows）または欠損（余剰行 dropped）の検知・不一致は fail-fast。
    if len(merged) != pre_len:
        raise RuntimeError(
            f"_select_se_state: timediff merge で行数が不一致 "
            f"(se={pre_len}, merged={len(merged)})。timediff_df 側に SE 側と "
            f"一致しない行が存在する可能性（WR-10・D-13）"
        )
    # left merge では検知できなかった timediff NaN（timediff_df 側の欠損行）も検知。
    # inner merge 後であれば timediff は全行非 NaN であることを assert する。
    if merged["timediff"].isna().any():
        raise RuntimeError(
            f"_select_se_state: merge 後の timediff に NaN が "
            f"{int(merged['timediff'].isna().sum())} 件存在（WR-10）"
        )
    return merged


_RACE_META_SELECT_COLUMNS = [
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "syubetucd",  # 障害判定（§7.3・'18'/'19' は障害専用コード）
    "class_name_normalized",  # v1.1.0: newcomer/maiden 判定（§7.3/§7.2・jyokencd5 由来）
    "class_code_normalized",
    "class_level_numeric",  # §7.2 クラス適格性判定
    "class_normalization_status",
    "race_date",  # 時系列整序用
]


def _select_race_meta(read_cur: Cursor) -> pd.DataFrame:
    """``normalized.n_race`` から race-level 適格性情報を SELECT。"""
    cols = ", ".join(_RACE_META_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM normalized.n_race WHERE {PROJECT_WINDOW_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_RACE_META_SELECT_COLUMNS)


# ---------------------------------------------------------------------------
# _canonicalize_markers（REVIEWS HIGH #5 + NEW HIGH #3）
# ---------------------------------------------------------------------------
def _canonicalize_value(v: Any, *, missing_sentinel: str) -> str:
    """marker 値を正規化文字列に変換（HIGH #5 + NEW HIGH #3）。

    必ずまず ``pd.isna(v)`` で missing/null を捕捉し sentinel ``missing_sentinel``
    （通常 ``"__MISSING__"``）にマップしてから ``str()`` に回す。これにより
    ``NaN``→``'nan'`` / ``pd.NA``→``'<NA>'`` / ``None``→``'None'`` が sentinel 集合外
    と誤判定される silent corruption（HIGH #3）を構造的に回避する。
    numeric 型の値も ``str()`` でキャストし sentinel 比較に回す（raw varchar と numeric
    cast と missing/null の3表現で同一結果になるのが HIGH #5 の核心）。
    """
    # NEW HIGH #3: missing/null を先に捕捉（pd.isna は None/NaN/pd.NA/NaT 全て True）。
    try:
        if v is None or pd.isna(v):
            return missing_sentinel
    except (TypeError, ValueError):
        # pd.isna が配列的に振る舞う場合（should not happen for scalar marker）の安全弁
        if v is None:
            return missing_sentinel
    return str(v).strip()


def _canonicalize_markers(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """SE marker 列を sentinel 集合で正規化し boolean marker 列を追加して返す（HIGH #5/#3）。

    追加列:
      - ``is_scratch_cancel`` : ``bataijyu in bataijyu_sentinels_scratch``
      - ``is_race_cancelled`` : ``datakubun in datakubun_sentinels_race_cancelled``
      - ``marker_active``     : ``harontimel3 in harontimel3_sentinels AND
                                 timediff in timediff_sentinels``
      - ``time_present``      : ``time != missing_sentinel AND time not in
                                 time_sentinels_absent AND time != ''``
      - ``is_dead_loss``      : ``marker_active AND time_present``（発走後停止＝競走中止）
      - ``is_race_excluded``  : ``marker_active AND NOT time_present``（発走前除外・本DBでは0件）

    sentinel 集合は ``label_spec.yaml`` の ``se_marker_canonicalization`` から取得する。
    単一文字列等価比較（例: ``harontimel3 == '999.0'``）は禁止・sentinel 集合への ``in``
    判定のみ許可（HIGH #5）。
    """
    canon_cfg = spec["se_marker_canonicalization"]
    bataijyu_sentinels_scratch = set(canon_cfg["bataijyu_sentinels_scratch"])
    harontimel3_sentinels = set(canon_cfg["harontimel3_sentinels"])
    timediff_sentinels = set(canon_cfg["timediff_sentinels"])
    time_sentinels_absent = set(canon_cfg["time_sentinels_absent"])
    datakubun_sentinels_race_cancelled = set(canon_cfg["datakubun_sentinels_race_cancelled"])
    missing_sentinel = canon_cfg["missing_value_sentinel"]

    out = df.copy()

    # 各 marker 列を正規化文字列に変換（HIGH #5 + NEW HIGH #3）。
    # _canonicalize_value が pd.isna guard → sentinel マップ → str() の順で処理する。
    out["_c_bataijyu"] = out["bataijyu"].map(
        lambda v: _canonicalize_value(v, missing_sentinel=missing_sentinel)
    )
    out["_c_harontimel3"] = out["harontimel3"].map(
        lambda v: _canonicalize_value(v, missing_sentinel=missing_sentinel)
    )
    out["_c_timediff"] = out["timediff"].map(
        lambda v: _canonicalize_value(v, missing_sentinel=missing_sentinel)
    )
    out["_c_time"] = out["time"].map(
        lambda v: _canonicalize_value(v, missing_sentinel=missing_sentinel)
    )
    out["_c_datakubun"] = out["datakubun"].map(
        lambda v: _canonicalize_value(v, missing_sentinel=missing_sentinel)
    )

    # 出走取消: bataijyu in bataijyu_sentinels_scratch（実測 956 行）
    out["is_scratch_cancel"] = out["_c_bataijyu"].isin(bataijyu_sentinels_scratch)

    # レース全体中止: datakubun in datakubun_sentinels_race_cancelled（実測 376 SE 行）
    out["is_race_cancelled"] = out["_c_datakubun"].isin(datakubun_sentinels_race_cancelled)

    # marker_active: harontimel3 と timediff が両方とも sentinel（異常値）
    out["marker_active"] = out["_c_harontimel3"].isin(harontimel3_sentinels) & (
        out["_c_timediff"].isin(timediff_sentinels)
    )

    # NEW HIGH #3: time_present は最初に missing_value_sentinel を除外条件とする。
    # missing time（None/NaN/pd.NA）は _canonicalize_value で missing_sentinel に
    # マップ済みなので、ここで確実に time_present=False になる（is_dead_loss 汚染防止）。
    out["time_present"] = (
        (out["_c_time"] != missing_sentinel)
        & (~out["_c_time"].isin(time_sentinels_absent))
        & (out["_c_time"] != "")
    )

    # 競走中止（発走後停止）: marker_active AND time_present（実測 3,554 行・学習残 §10.6）
    out["is_dead_loss"] = out["marker_active"] & out["time_present"]

    # 発走前除外: marker_active AND NOT time_present（実測 0 件・本DBでは発生なし）
    out["is_race_excluded"] = out["marker_active"] & (~out["time_present"])

    # 作業列を破棄（external API には出さない）
    out = out.drop(
        columns=["_c_bataijyu", "_c_harontimel3", "_c_timediff", "_c_time", "_c_datakubun"]
    )

    return out


# ---------------------------------------------------------------------------
# classify_status（D-04 観測事実ベース・順序依存・早期 return）
# ---------------------------------------------------------------------------
def classify_status(row: pd.Series, *, spec: dict) -> str:
    """D-04 固定4値 status を返す（validated/inferred/dead_heat/unresolved）。

    順序依存あり（早期 return）。**D-13 silent fallback 禁止**・将来のDB更新
    （FuseirituFlag2/TokubaraiFlag2 の発生）に備え全分岐を明示する。

    順序:
      1. ``is_race_cancelled`` または HR ``datakubun == '9'`` → 'unresolved'
      2. HR ``fuseirituflag2 == '1'``（複勝不成立）→ 'unresolved'
      3. HR ``tokubaraiflag2 == '1'``（複勝特払・D-04）→ payout_umaban_set が非空なら
         'validated'（対象馬あり・正当な正例）/ 空なら 'unresolved'（対象馬なし・outcome 非確定）
      4. HR レコード欠損（``torokutosu_i`` が pd.NA）→ 'unresolved'
      5. ``is_dead_heat``（payout_count > fukusho_payout_places AND payout_places > 0）→ 'dead_heat'
      6. HR ``datakubun == '1'``（速報）→ 'inferred'
      7. それ以外 → 'validated'
    """
    harai_datakubun_sentinels = set(
        spec["se_marker_canonicalization"]["datakubun_sentinels_race_cancelled"]
    )

    # 1. レース全体中止（HR/SE DataKubun='9'）
    hr_dk = _safe_str(row.get("datakubun_harai"))
    if bool(row.get("is_race_cancelled", False)) or hr_dk in harai_datakubun_sentinels:
        return "unresolved"

    # 2. 複勝不成立（HR FuseirituFlag2='1'）
    if _safe_str(row.get("fuseitsuflag2")) == "1" or _safe_str(row.get("fuseirituflag2")) == "1":
        return "unresolved"

    # 3. 複勝特払（HR TokubaraiFlag2='1'・D-04・label_spec.yaml hr_status_rules）
    tokubarai_val = str(
        spec.get("hr_status_rules", {}).get("tokubarai_flag2_value", {}).get("value", "1")
    )
    if _safe_str(row.get("tokubaraiflag2")) == tokubarai_val:
        payout_count = int(row.get("payout_count", 0) or 0)
        if payout_count > 0:
            return "validated"  # 対象馬あり・正当な正例
        return "unresolved"  # 対象馬なし・outcome 非確定

    # 4. HR レコード欠損（torokutosu IS NA）
    torokutosu_i = row.get("torokutosu_i")
    if torokutosu_i is None or _is_na(torokutosu_i):
        return "unresolved"

    # 5. 同着（is_dead_heat flag・payout-table authoritative・MEDIUM #2: DochacoTosu は参考値）
    # WR-04 (iteration 3): ``fukusho_payout_places`` を ``payout_count`` と等価にしたため、
    # ``payout_count > fukusho_payout_places`` は常に False。``is_dead_heat`` flag は
    # ``_is_dh`` で ``payout_count > JRA 理論枠(syussotosu ベース)`` で算出されるため、
    # ここでは flag のみを参照する。
    is_dead_heat = bool(row.get("is_dead_heat", False))
    if is_dead_heat:
        return "dead_heat"

    # 6. 速報（HR DataKubun='1'）は inferred — 本DBでは発生しないが将来更新に備え保持（D-13）
    if hr_dk == "1":
        return "inferred"

    # 7. 通常（HR DataKubun='2' の月曜確定）
    return "validated"


# ---------------------------------------------------------------------------
# compute_is_model_eligible（D-03 §7.2 + REVIEWS HIGH #6 契約）
# ---------------------------------------------------------------------------
def compute_is_model_eligible(row: pd.Series, *, spec: dict) -> tuple[bool, str | None]:
    """§7.2 + status で ``(is_eligible, reason)`` を返す（HIGH #6: 順序依存）。

    適用順序（HIGH #6 契約: syubetucd 障害/class_name_normalized 新馬が先に評価され、
    is_dead_loss は単独では不適格理由にならない）:
      (a) ``syubetucd in model_ineligibility_syubetucd``（['18','19']）→ (False, 'obstacle')
          ※障害は syubetucd で確実識別可能（'18'/'19' は障害専用・平地との混在なし）
      (a') ``class_name_normalized in newcomer_class_name``（['新馬']）→ (False, 'newcomer')
          ※v1.1.0: syubetucd 基準から class_name_normalized 基準に変更。
          syubetucd='11'/'12' は馬齢カテゴリとクラスが直交する混在コード（実測: syubetucd='12'
          は未勝利9611/1勝1559/OP629/新馬599 races・新馬は最少）で newcomer 判定の代理キーとして
          不適格。class_name_normalized='新馬'（jyokencd5='701'）が正しい指標。
      (b) ``not is_fukusho_sale_available`` → (False, 'no_fukusho_sale')
      (c) ``label_validation_status == 'unresolved'`` → (False, 'unresolved')
      (d) ``is_race_cancelled or is_scratch_cancel or is_race_excluded``
          → (False, 'race_or_horse_cancelled')
      (e) ``class_level_numeric < minimum_class_level_numeric`` AND
          ``class_name_normalized NOT IN maiden_class_name`` → (False, 'class_below_minimum')
          （未勝利=class_level_numeric=0・class_name_normalized='未勝利' は §7.2 対象で適格）
      (f) ``label_validation_status in (validated, inferred, dead_heat)`` → (True, None)
      (g) それ以外 → (False, 'status_not_eligible')

    **HIGH #6 コメント:** ``is_dead_loss`` は適用順序の判定対象に入らない。競走中止馬が
    他の理由で不適格になる場合（例: 障害レースで競走中止）、``ineligibility_reason``
    には ``'obstacle'`` が格納され ``'dead_loss'`` 由来にはならない。

    **v1.1.0 改訂:** newcomer/maiden 判定基準を ``syubetucd`` から
    ``class_name_normalized`` に変更（class_name_normalized は race 静的属性・PIT 安全）。
    """
    syubetucd = _safe_str(row.get("syubetucd"))
    class_name = _safe_str(row.get("class_name_normalized"))
    obstacle_set = set(spec.get("model_ineligibility_syubetucd", []))
    newcomer_class_set = set(spec.get("newcomer_class_name", []))
    maiden_class_set = set(spec.get("class_eligibility", {}).get("maiden_class_name", []))
    min_class = spec.get("class_eligibility", {}).get("minimum_class_level_numeric", 1)

    # (a) 障害競走（§7.3・syubetucd で確実識別）
    if syubetucd in obstacle_set:
        return False, "obstacle"
    # (a') 新馬戦（§7.3・v1.1.0: class_name_normalized 基準）
    if class_name in newcomer_class_set:
        return False, "newcomer"
    # (b) 複勝発売なし
    if not bool(row.get("is_fukusho_sale_available", False)):
        return False, "no_fukusho_sale"
    # (c) ラベル生成/突合失敗（D-03）
    if row.get("label_validation_status") == "unresolved":
        return False, "unresolved"
    # (d) レース全体中止・取消・除外馬
    if (
        bool(row.get("is_race_cancelled", False))
        or bool(row.get("is_scratch_cancel", False))
        or bool(row.get("is_race_excluded", False))
    ):
        return False, "race_or_horse_cancelled"
    # (e) §7.2 クラス条件（未勝利=class_level_numeric=0・class_name_normalized='未勝利' は適格）
    class_level = row.get("class_level_numeric")
    if class_level is not None and not _is_na(class_level) and int(class_level) < int(min_class):
        if class_name not in maiden_class_set:
            return False, "class_below_minimum"
    # (f) status が validated/inferred/dead_heat のいずれか
    if row.get("label_validation_status") in ("validated", "inferred", "dead_heat"):
        return True, None
    # (g) それ以外（D-13 隔離）
    return False, "status_not_eligible"


# ---------------------------------------------------------------------------
# compute_fukusho_labels（合成 DataFrame / 実DB DataFrame 両方で deterministic）
# ---------------------------------------------------------------------------
_PAYOUT_COLS = [f"payfukusyoumaban{i}" for i in range(1, 6)]
_RACE_KEY = ["year", "jyocd", "kaiji", "nichiji", "racenum"]
# race_key 正規化: kaiji/racenum は実DB で型不整合を起こす（race_df=normalized.n_race 側は
# integer・SE/HR=public.n_* 側は 2桁ゼロ埋め varchar）。astype(str) のみだと int4 "1" vs
# varchar "01" で一致せず left join が全行 miss し race_date が全行 NULL になる（2026-06-23/24
# silent corruption の根本原因）。両者を str.zfill(2) で2桁ゼロ埋めに正規化して一致させる。
# year(4桁)/jyocd/nichiji は astype(str) のみで一致するため zfill 対象外。
_RACE_KEY_ZFILL_COLS = ["kaiji", "racenum"]


def compute_fukusho_labels(
    hr_df: pd.DataFrame,
    se_df: pd.DataFrame,
    race_df: pd.DataFrame,
    *,
    spec: dict | None = None,
) -> pd.DataFrame:
    """HR / SE / race DataFrame から複勝ラベルを計算し 1行/馬の DataFrame を返す。

    出力列（全て付与）:
      - PK: year, jyocd, kaiji, nichiji, racenum, umaban, kettonum
      - race-level: race_date, syubetucd, class_level_numeric
      - §10.2: sales_start_entry_count, sales_start_entry_count_source,
        sales_start_entry_count_confidence, final_starter_count,
        fukusho_payout_places, is_fukusho_sale_available
      - LABEL-01: fukusho_hit_raw, fukusho_hit_validated
      - D-04: label_validation_status, is_dead_heat
      - D-04 marker: is_scratch_cancel, is_race_excluded, is_dead_loss,
        is_race_cancelled
      - D-03: is_model_eligible, ineligibility_reason
      - §19.1: label_generation_version

    Args:
        hr_df: n_harai 1行/レース。``payfukusyoumaban1..5`` / ``torokutosu`` /
            ``syussotosu`` / ``fuseirituflag2`` / ``tokubaraiflag2`` /
            ``datakubun``（HR 側）を含む。
        se_df: n_uma_race 1行/馬。``kakuteijyuni`` / ``bataijyu`` /
            ``harontimel3`` / ``timediff`` / ``time`` / ``datakubun``（SE 側）を含む。
        race_df: normalized.n_race 1行/レース。``syubetucd`` /
            ``class_level_numeric`` / ``race_date`` を含む。
        spec: ``label_spec.yaml`` の dict。None の場合は ``load_label_spec()`` で読込。
    """
    spec = spec if spec is not None else load_label_spec()
    payout_rules = spec["payout_places_rules"]
    min_torokutosu = int(payout_rules["min_torokutosu_for_fukusho_sale"])
    # WR-04 (iteration 3): places_5_to_7_horses / places_8_or_more_horses は参考値のため
    # payout_places 計算には不使用（実計算は HR 払戻馬番数 payout_count を使用）。spec 上は
    # JRA 規則の参考値として保持する。
    no_sale = int(payout_rules["no_sale_marker_value"])
    source_confidence = spec["sales_start_entry_count"]["source_confidence"]
    label_version = spec["label_generation_version"]

    # --- HR 側の前処理: torokutosu / syussotosu / datakubun_harai / payout_umaban_set ---
    hr = hr_df.copy()
    # '00' と '' を pd.NA に変換（A3: silent mislabeling 防止・'00'=発売なし/特払/不成立）
    for c in _PAYOUT_COLS:
        if c in hr.columns:
            hr[c] = hr[c].replace({"00": pd.NA, "": pd.NA, None: pd.NA})

    # torokutosu / syussotosu を int 系にキャスト（Pitfall 1）
    hr["torokutosu_i"] = (
        pd.to_numeric(hr["torokutosu"], errors="coerce") if "torokutosu" in hr.columns else pd.NA
    )
    hr["syussotosu_i"] = (
        pd.to_numeric(hr["syussotosu"], errors="coerce") if "syussotosu" in hr.columns else pd.NA
    )
    # HR DataKubun を datakubun_harai として保持（SE DataKubun と区別）
    hr["datakubun_harai"] = hr["datakubun"] if "datakubun" in hr.columns else pd.NA

    # payout_umaban_set と payout_count を構築（HR 1行 → set）。
    # 行ベース apply（result_type="expand"）は空 DataFrame で列数不整合を起こすため、
    # list comprehension で安全に構築する（test_unresolved_triggers_hr_missing の空 HR 対応）。
    payout_sets: list[set[str]] = []
    payout_counts: list[int] = []
    for _, row in hr.iterrows():
        s: set[str] = set()
        for c in _PAYOUT_COLS:
            v = row.get(c)
            if v is None or _is_na(v):
                continue
            # umaban は zfill(2) 文字列で SE 側と比較する（A1: zero-padding 整合）
            try:
                s.add(str(int(float(v))).zfill(2))
            except (TypeError, ValueError):
                s.add(str(v).strip().zfill(2))
        payout_sets.append(s)
        payout_counts.append(len(s))
    hr["payout_umaban_set"] = payout_sets
    hr["payout_count"] = payout_counts

    # --- SE 側の前処理: kakuteijyuni / umaban / kettonum を int 系にキャスト ---
    se = se_df.copy()
    if "kakuteijyuni" in se.columns:
        se["kakuteijyuni_i"] = pd.to_numeric(se["kakuteijyuni"], errors="coerce")
    else:
        se["kakuteijyuni_i"] = pd.NA

    # --- merge: SE + HR（race key で left join・HR 1行 ↔ SE 複数行）---
    hr_merge = hr[
        _RACE_KEY
        + [
            "torokutosu_i",
            "syussotosu_i",
            "datakubun_harai",
            "fuseirituflag2",
            "tokubaraiflag2",
            "henkanflag2",
            "payout_umaban_set",
            "payout_count",
        ]
        + _PAYOUT_COLS
    ].copy()
    merged = se.merge(hr_merge, on=_RACE_KEY, how="left")

    # --- merge: + race_df（syubetucd / class_level_numeric / race_date）---
    # race_date は実DB（normalized.n_race）には存在するが、合成 DataFrame（unit test）には
    # 含まれない場合があるため、存在する列のみ merge する（deterministic・両対応）。
    # 実DB では race 側の _RACE_KEY は int4（normalized.n_race の kaiji/racenum）、SE/HR 側は
    # varchar（public.n_*）のため、merge 前に両者を str に揃える（Pitfall: str vs int64 merge error）。
    # さらに kaiji/racenum は実DB で int4(1) vs varchar('01') のゼロ埋めフォーマット差があり、
    # astype(str) のみだと "1" vs "01" で一致せず left join が全行 miss する（2026-06-23/24 の
    # race_date 全行 NULL silent corruption の根本原因）。両者を zfill(2) で2桁ゼロ埋めに
    # 正規化して一致させる。year(4桁)/jyocd/nichiji は astype(str) のみで一致する。
    race_extra_cols = [
        c
        for c in ("syubetucd", "class_name_normalized", "class_level_numeric", "race_date")
        if c in race_df.columns
    ]
    race_merge = race_df[_RACE_KEY + race_extra_cols].copy()
    for k in _RACE_KEY:
        if k in merged.columns:
            merged[k] = merged[k].astype(str)
        if k in race_merge.columns:
            race_merge[k] = race_merge[k].astype(str)
    # kaiji/racenum のゼロ埋め正規化（int4 "1" ↔ varchar "01" の不一致を吸収）
    for k in _RACE_KEY_ZFILL_COLS:
        if k in merged.columns:
            merged[k] = merged[k].str.zfill(2)
        if k in race_merge.columns:
            race_merge[k] = race_merge[k].str.zfill(2)
    merged = merged.merge(race_merge, on=_RACE_KEY, how="left")

    # --- race_date 伝播 fail-loud（silent corruption 再発防止・2026-06-23/06-24 事故対応）---
    # 従来 `if "race_date" not in merged.columns: merged["race_date"] = pd.NA` の fallback が
    # race_date 伝播失敗を黙って全行 NULL 化する構造的欠陥だった（label.fukusho_label.race_date
    # 全行 NULL が2回再発）。再発時に止まり、なぜ race_date が抜けたかがログから分かる仕組みに
    # 置換する。正常ケース（race_df に race_date があり merge 結果全行 non-NULL）は挙動不变。
    if "race_date" not in merged.columns or merged["race_date"].isna().any():
        # race_df 側の状態（行数・race_date 列有無・non-NULL 数）と merged 側の状態（行数・
        # race_date 列有無・NULL 数・non-NULL 数）を診断ログで出力（再発時の原因特定用）。
        race_df_has_race_date = "race_date" in race_df.columns
        race_df_race_date_nonnull = (
            int(race_df["race_date"].notna().sum()) if race_df_has_race_date else 0
        )
        merged_has_race_date = "race_date" in merged.columns
        merged_race_date_null = (
            int(merged["race_date"].isna().sum()) if merged_has_race_date else len(merged)
        )
        merged_race_date_nonnull = (
            int(merged["race_date"].notna().sum()) if merged_has_race_date else 0
        )
        logger.error(
            "race_date 伝播失敗: race_df(rows=%d, race_date列=%s, race_date_nonnull=%d) / "
            "merged(rows=%d, race_date列=%s, race_date_null=%d, race_date_nonnull=%d) / "
            "race_df空=%s / 原因候補=[race_df空 / race_date列なし / race_key型不整合]",
            len(race_df),
            race_df_has_race_date,
            race_df_race_date_nonnull,
            len(merged),
            merged_has_race_date,
            merged_race_date_null,
            merged_race_date_nonnull,
            len(race_df) == 0,
        )
        raise RuntimeError(
            "race_date 伝播失敗: label.fukusho_label.race_date が全行 NULL になる構造的欠陥を"
            "検知（silent corruption 再発防止の fail-loud）。診断ログで race_df / merged の"
            "状態を確認し、原因（race_df 空 / race_date 列なし / race_key 型不整合）を特定すること。"
        )

    # --- _canonicalize_markers で marker 列を正規化（HIGH #5 + NEW HIGH #3）---
    # marker 計算に必要な列が揃っていることを保証（test_canonicalize_markers_missing_time
    # が time=None/NaN/pd.NA を直接渡すため、欠損でも落ちないように _canonicalize_markers
    # 内で pd.isna guard する・HIGH #3）。
    for required in ("bataijyu", "harontimel3", "timediff", "time", "datakubun"):
        if required not in merged.columns:
            merged[required] = pd.NA
    merged = _canonicalize_markers(merged, spec=spec)

    # --- fukusho_payout_places（HR 払戻馬番数 payout_count ベース・WR-04 iteration 3 最終）---
    # WR-04（iteration 3・最終）: 払戻対象頭数は **HR ``PayFukusyoUmaban`` の実際の払戻馬番数
    # （``payout_count`` = 非``'00'`` slot 数）** で決定する（D-01 厳格・spec note の本来の意図）。
    # ``torokutosu``（登録・出馬表発表時）/``syussotosu``（完走）は代理値に過ぎず、
    # 発走前取消・発走後中止レースで実際の払戻馬番数と一致しないため ``payout_places`` 計算
    # には不使用。実DB観測で 5件の発走前取消レース（torokutosu=8 でも HR 払戻2頭）・
    # 2022/07 R8 の発走後中止レース（syussotosu=4 でも HR 払戻2頭）の双方で torokutosu /
    # syussotosu が誤るが payout_count は唯一正しいことが判明した。
    # ``places_5_to_7_horses``(2) / ``places_8_or_more_horses``(3) は JRA 規則の参考値で
    # 実計算には不使用（同着拡張で payout_count が 4-5 になる場合は HR 観測事実に従う）。
    # HR merge が left join で HR 欠損行（unresolved）では ``payout_count`` が NaN になる
    # ため ``fillna(0)`` で ``no_sale_marker_value`` に正規化する（D-13 silent fallback 禁止）。
    merged["fukusho_payout_places"] = merged["payout_count"].fillna(no_sale).astype(int)

    # --- is_fukusho_sale_available: torokutosu >= 5 AND fuseirituflag2 != '1' ---
    # WR-04（iteration 3）: 複勝発売の有無は「出馬表発表時（登録時）」に決まるため
    # torokutosu（= sales_start_entry_count 代理値）ベースのまま変更しない。
    # 発売あり（torokutosu >= 5）だが HR 払戻が無い（payout_places=0・不成立）場合でも
    # is_fukusho_sale_available=True は正当（「発売されたが不成立」の正当な状態）。
    fuseiritu = (
        merged["fuseirituflag2"].map(_safe_str)
        if "fuseirituflag2" in merged.columns
        else pd.Series([""] * len(merged))
    )
    merged["is_fukusho_sale_available"] = (
        merged["torokutosu_i"].map(
            lambda t: False if (t is None or _is_na(t)) else int(t) >= min_torokutosu
        )
    ) & (fuseiritu != "1")

    # --- fukusho_hit_raw: KakuteiJyuni-based ---
    def _raw_hit(r: pd.Series) -> int:
        pp = r["fukusho_payout_places"]
        kj = r["kakuteijyuni_i"]
        if pp is None or _is_na(pp) or int(pp) <= 0:
            return 0
        if kj is None or _is_na(kj):
            return 0
        kjv = int(kj)
        return 1 if (kjv >= 1 and kjv <= int(pp)) else 0

    merged["fukusho_hit_raw"] = merged.apply(_raw_hit, axis=1)

    # --- fukusho_hit_validated: PayFukusyoUmaban-based ---
    merged["umaban_str"] = merged["umaban"].map(
        lambda v: (
            "__NA__"
            if (v is None or _is_na(v))
            else (
                str(int(float(v))).zfill(2) if _is_numeric_str(v) else _safe_str(v).strip().zfill(2)
            )
        )
    )

    def _valid_hit(r: pd.Series) -> int:
        s = r.get("payout_umaban_set")
        if s is None or _is_na(s) or not isinstance(s, set) or len(s) == 0:
            return 0
        return 1 if r["umaban_str"] in s else 0

    merged["fukusho_hit_validated"] = merged.apply(_valid_hit, axis=1)

    # --- sales_start_entry_count 系（HIGH #1: label_validation_status から独立列）---
    merged["sales_start_entry_count"] = merged["torokutosu_i"].map(
        lambda t: None if (t is None or _is_na(t)) else int(t)
    )
    merged["sales_start_entry_count_source"] = "torokutosu_proxy"
    merged["sales_start_entry_count_confidence"] = source_confidence  # 'inferred'・HIGH #1 独立列
    merged["final_starter_count"] = merged["syussotosu_i"].map(
        lambda t: None if (t is None or _is_na(t)) else int(t)
    )

    # --- is_dead_heat（payout-table authoritative・MEDIUM #2: DochacoTosu は参考値）---
    # WR-04 (iteration 4): ``fukusho_payout_places`` を ``payout_count`` と等価にした結果、
    # ``payout_count > fukusho_payout_places`` は常に False になるため、同着検出は
    # ``payout_count`` と JRA 規則の標準払戻対象頭数（``syussotosu_i`` ベース・5-7頭→2・
    # 8+頭→3）の比較で行う。HR が標準枠を超えて slot4/5 を使用した場合
    # （``payout_count > standard``）に dead_heat と判定する。これは spec の本来の意図
    # 「HR PayFukusyoUmaban slot4/5 使用が唯一の権威ある同着検出」を維持。
    #
    # iteration 3 false positive 修正（実DB 検証）: ``syussotosu < 5``（完走4頭以下）の
    # レース（例: 2022/07 R8・発走後中止で完走4頭・2頭払い）は JRA 標準枠が0になるが、
    # ``payout_count=2 > 0`` で常に dead_heat 扱いになる false positive があった
    # （実DB で dead_heat が 1656→1661・+5馬・全て payout_count=2/syussotosu=4）。
    # ``syussotosu < 5`` は複勝発売なし/不成立の可能性が高く dead_heat 判定から除外し、
    # 標準払戻対象頭数の比較のみで判定する（保護）。真の dead_heat
    # （payout_count=3/syussotosu=6-7・payout_count>=4/syussotosu>=8）は維持される。
    def _is_dh(r: pd.Series) -> bool:
        pc = r.get("payout_count", 0)
        syus = r.get("syussotosu_i")
        # CR-03: pd.NA / 異常値経由の TypeError/ValueError をガード。
        # pc は HR merge が left join で HR 欠損行では NaN になる経路があるため _is_na で保護し、
        # 更に try/except で予期せぬ型変換例外を回収する。
        if pc is None or _is_na(pc):
            return False
        try:
            pc_i = int(pc)
        except (TypeError, ValueError):
            return False
        if syus is None or _is_na(syus):
            return False
        try:
            syus_i = int(float(syus))
        except (TypeError, ValueError):
            return False
        # JRA 複勝の標準払戻対象頭数（発走時頭数を syussotosu で近似）。
        # payout_count がこれを超えていれば同着拡張（slot4/5 使用）= dead_heat。
        if syus_i >= 8:
            standard = int(spec["payout_places_rules"]["places_8_or_more_horses"])
        elif min_torokutosu <= syus_i <= 7:
            standard = int(spec["payout_places_rules"]["places_5_to_7_horses"])
        else:
            # syussotosu < 5（完走4頭以下）は複勝発売なし/不成立扱い。
            # dead_heat 判定から除外（R8 相当の false positive 防止）。
            return False
        return pc_i > standard

    merged["is_dead_heat"] = merged.apply(_is_dh, axis=1)

    # --- label_validation_status / is_model_eligible（行毎に適用）---
    # classify_status / compute_is_model_eligible が row.get で参照する全キーを含む row dict
    # を渡す。merge 結果の Series をそのまま渡せる。
    status_cols = [
        "is_race_cancelled",
        "datakubun_harai",
        "fuseirituflag2",
        "tokubaraiflag2",
        "torokutosu_i",
        "payout_count",
        "fukusho_payout_places",
        "is_dead_heat",
    ]
    for c in status_cols:
        if c not in merged.columns:
            merged[c] = pd.NA

    merged["label_validation_status"] = merged.apply(
        lambda r: classify_status(r, spec=spec), axis=1
    )
    elig = merged.apply(
        lambda r: compute_is_model_eligible(r, spec=spec), axis=1, result_type="expand"
    )
    elig.columns = ["is_model_eligible", "ineligibility_reason"]
    merged["is_model_eligible"] = elig["is_model_eligible"]
    merged["ineligibility_reason"] = elig["ineligibility_reason"]

    # --- CR-04: race_cancelled レースは複勝発売不成立・is_fukusho_sale_available=False に正規化 ---
    # REVIEW.md CR-04 残る論点（iteration 3 以降の payout_count ベースで fukusho_payout_places=0,
    # fukusho_hit_raw=0 は既に達成）に対する最終是正。
    # 現状: is_fukusho_sale_available は torokutosu ベース（登録>=5 → True）のため、
    # race_cancelled レース（出馬表発表時は発売予定だったが当日中止）でも True になる。
    # 「複勝発売が実際には無かった（中止）レースで is_fukusho_sale_available=True」を是正する。
    #
    # fukusho_payout_places（payout_count ベース・race_cancelled=0）と
    # fukusho_hit_raw（payout_count=0 → raw=0）は iteration 3 (WR-04) で既に達成済み。
    #
    # _check_no_fukusho_sale_not_in_training gate への影響:
    # race_cancelled 馬は status='unresolved' → compute_is_model_eligible step (d) で
    # is_model_eligible=False となる。従って本正規化により race_cancelled 馬が
    # is_fukusho_sale_available=False になっても gate には引っかからない（is_model_eligible=False
    # で既に学習除外されているため）。
    mask_race_cancelled = merged["is_race_cancelled"] == True  # noqa: E712
    merged.loc[mask_race_cancelled, "is_fukusho_sale_available"] = False

    # --- label_generation_version ---
    merged["label_generation_version"] = label_version

    # 不要な作業列を削除
    drop_cols = [
        c
        for c in ["kakuteijyuni_i", "umaban_str", "payout_umaban_set", "payout_count"]
        if c in merged.columns
    ]
    if drop_cols:
        merged = merged.drop(columns=drop_cols)

    return merged.reset_index(drop=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _safe_str(v: Any) -> str:
    """None/NaN/NA を空文字列に、それ以外を ``str(v).strip()`` に変換。

    sentinel 集合比較（HIGH #5）ではなく status 分類のフラグ比較（'1'/'9' 等）用の helper。
    marker 値の正規化は ``_canonicalize_value`` を使用すること（HIGH #3 pd.isna guard）。
    """
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def _is_na(v: Any) -> bool:
    """scalar の欠損判定（pd.isna の安全 wrapper・配列入力時の ValueError を回避）。"""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _is_numeric_str(v: Any) -> bool:
    """値が numeric に変換可能か（umaban zfill のために数値化できるか判定）。"""
    if v is None or _is_na(v):
        return False
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# label.fukusho_label CREATE TABLE（HIGH #1: sales_start_entry_count_confidence 独立列）
# ---------------------------------------------------------------------------
_LABEL_TABLE_COLUMNS = [
    # PK
    "year int",
    "jyocd varchar(2)",
    "kaiji int",
    "nichiji varchar(2)",
    "racenum int",
    "umaban int",
    "kettonum int",
    # §10.2 保持項目
    "race_date date",
    "sales_start_entry_count int",
    "sales_start_entry_count_source varchar(32)",
    # REVIEWS HIGH #1: label_validation_status から独立した varchar NOT NULL
    "sales_start_entry_count_confidence varchar(16) NOT NULL",
    "final_starter_count int",
    "fukusho_payout_places smallint",
    "is_fukusho_sale_available boolean",
    "fukusho_hit_raw smallint",
    "fukusho_hit_validated smallint",
    "label_validation_status varchar(16)",
    # D-03
    "is_model_eligible boolean",
    "ineligibility_reason varchar(64)",
    # D-04 状態マーカー
    "is_scratch_cancel boolean",
    "is_race_excluded boolean",
    "is_dead_loss boolean",
    "is_race_cancelled boolean",
    "is_dead_heat boolean",
    # §19.1 再現性
    "label_generation_version varchar(16) NOT NULL",
]

# WR-11 (03-REVIEW): private prefix を外して public API に昇格。
# ``src.etl.label_race_date_backfill`` が INSERT 列順序を参照するため、cross-module で
# private import する設計負債を解消。末尾の ``_LABEL_INSERT_COLUMNS`` alias は既存 import の
# 後方互換用（非推奨・将来削除候補）。
LABEL_INSERT_COLUMNS = [c.split()[0] for c in _LABEL_TABLE_COLUMNS]
_LABEL_INSERT_COLUMNS = LABEL_INSERT_COLUMNS  # 後方互換 alias（非推奨・WR-11）


def _create_label_table(write_cur: Cursor, *, reader_role: str) -> None:
    """``label.fukusho_label`` を IF NOT EXISTS で作成（HIGH #1 + HIGH #3）。

    初回作成直後に ``GRANT SELECT ON label.fukusho_label TO {reader_role}`` を発行
    （HIGH #3: PUBLIC 不使用・明示的 reader ロール・psycopg.sql.Identifier で安全に置換）。
    """
    cols_sql = ",\n  ".join(_LABEL_TABLE_COLUMNS)
    pk = "PRIMARY KEY (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)"
    ddl = f"CREATE TABLE IF NOT EXISTS label.fukusho_label (\n  {cols_sql},\n  {pk}\n)"
    write_cur.execute(ddl)
    write_cur.execute(
        "COMMENT ON TABLE label.fukusho_label IS "
        "'Fukusho label table (Phase 2). label_generation_version-managed. (REVIEWS HIGH #3)'"
    )
    # HIGH #3: 明示的 reader ロール GRANT（PUBLIC 不使用）
    write_cur.execute(
        SQL("GRANT SELECT ON label.fukusho_label TO {}").format(Identifier(reader_role))
    )


# ---------------------------------------------------------------------------
# _idempotent_load_label（HIGH #3: staging-swap・INCLUDING ALL・reader role 明示 GRANT）
# ---------------------------------------------------------------------------
def _idempotent_load_label(
    write_cur: Cursor,
    rows: list[tuple],
    columns: list[str],
    *,
    reader_role: str,
) -> int:
    """staging-swap で ``label.fukusho_label`` を atomic 替換する（HIGH #3）。

    Steps（同一トランザクション内）:
      0. ``SELECT pg_advisory_xact_lock(hashtext('label.fukusho_label'))``（CR-04(b)）
      1. 空入力 RuntimeError（CR-04(a)・rows=[] 拒否・silent data loss 防止）
      2. ``_create_label_table(write_cur, reader_role=reader_role)``（IF NOT EXISTS・既存は no-op）
      3. ``CREATE TABLE IF NOT EXISTS label.fukusho_label_staging
         (LIKE label.fukusho_label INCLUDING ALL)``（HIGH #3: INCLUDING ALL で
         PK / インデックス / NOT NULL / コメントが staging 表に継承）
      4. ``TRUNCATE label.fukusho_label_staging``
      5. ``executemany INSERT INTO ... _staging ...``（rowcount 検証 CR-04(c)）
      6. ``DROP TABLE IF EXISTS label.fukusho_label``
      7. ``ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label``
      8. **``GRANT SELECT ON label.fukusho_label TO {reader_role}``**（HIGH #3: RENAME 後に
         明示的 reader role GRANT を再発行・PUBLIC 不使用・psycopg.sql.Identifier で安全に置換）
      9. ``SELECT count(*) FROM label.fukusho_label`` で rowcount を返り値として返す
         （idempotent 実行の checksum 基準）
    """
    # CR-04(b): transaction-scoped advisory lock で並行 swap を直列化
    write_cur.execute("SELECT pg_advisory_xact_lock(hashtext('label.fukusho_label'))")

    # CR-04(a): 空入力の swap を拒否（silent data loss 防止）
    if not rows:
        raise RuntimeError(
            "_idempotent_load_label('label.fukusho_label'): refusing to swap to empty "
            "(0 rows). Investigate read pool / transform — silent data loss prevented (CR-04)."
        )

    # IF NOT EXISTS で対象テーブル作成（初回）+ comment + 初回 GRANT
    _create_label_table(write_cur, reader_role=reader_role)

    # staging を INCLUDING ALL で作成（PK / インデックス / NOT NULL / コメント継承）
    write_cur.execute(
        "CREATE TABLE IF NOT EXISTS label.fukusho_label_staging "
        "(LIKE label.fukusho_label INCLUDING ALL)"
    )
    write_cur.execute("TRUNCATE label.fukusho_label_staging")

    # INSERT INTO staging
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    write_cur.executemany(
        f"INSERT INTO label.fukusho_label_staging ({cols_sql}) VALUES ({placeholders})",
        rows,
    )
    # WR-06: psycopg3 executemany の rowcount は pipeline mode / PG バージョンで
    # PQcmdTuples の挙動が変わるため信用できない。INSERT 後に SELECT count(*) で
    # staging テーブルの実際の行数を検証する（CR-04 rowcount verification の後継）。
    write_cur.execute("SELECT count(*) FROM label.fukusho_label_staging")
    actual = int(write_cur.fetchone()[0])
    if actual != len(rows):
        raise RuntimeError(
            f"_idempotent_load_label: staging table has {actual} rows, "
            f"expected {len(rows)} (WR-06 rowcount verification via SELECT count(*))"
        )

    # atomic swap: DROP existing → RENAME staging → table
    write_cur.execute("DROP TABLE IF EXISTS label.fukusho_label")
    write_cur.execute("ALTER TABLE label.fukusho_label_staging RENAME TO fukusho_label")
    # HIGH #3: RENAME 後に明示的 reader role GRANT を再発行（TO PUBLIC は使用しない）
    write_cur.execute(
        SQL("GRANT SELECT ON label.fukusho_label TO {}").format(Identifier(reader_role))
    )

    # rowcount を返す（idempotent 実行確認用・checksum 基準）
    write_cur.execute("SELECT count(*) FROM label.fukusho_label")
    cnt = int(write_cur.fetchone()[0])
    return cnt


# ---------------------------------------------------------------------------
# _df_to_tuples_label
# ---------------------------------------------------------------------------
_BOOL_COLS = {
    "is_model_eligible",
    "is_fukusho_sale_available",
    "is_scratch_cancel",
    "is_race_excluded",
    "is_dead_loss",
    "is_race_cancelled",
    "is_dead_heat",
}
_INT_COLS = {
    "year",
    "kaiji",
    "racenum",
    "umaban",
    "kettonum",
    "sales_start_entry_count",
    "final_starter_count",
    "fukusho_payout_places",
    "fukusho_hit_raw",
    "fukusho_hit_validated",
}


def _df_to_tuples_label(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """DataFrame を INSERT 用 tuple list に変換（normalize._df_to_tuples と同形式）。"""
    out: list[tuple] = []
    for _, row in df.iterrows():
        vals: list[Any] = []
        for c in columns:
            v = row.get(c)
            if c == "race_date":
                if v is None or _is_na(v):
                    vals.append(None)
                elif hasattr(v, "isoformat"):
                    vals.append(v)
                else:
                    # normalized.n_race から来る date / datetime / str のいずれか
                    try:
                        vals.append(pd.Timestamp(v).date())
                    except (TypeError, ValueError):
                        vals.append(None)
            elif c in _BOOL_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    vals.append(bool(v))
            elif c in _INT_COLS:
                if v is None or _is_na(v):
                    vals.append(None)
                else:
                    try:
                        vals.append(int(v))
                    except (TypeError, ValueError):
                        vals.append(None)
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
# run_label_etl（public API）
# ---------------------------------------------------------------------------
def run_label_etl(
    read_pool: ConnectionPool,
    write_pool: ConnectionPool,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """複勝ラベル ETL のエントリポイント（HIGH #6: write_pool = ETL ロール）。

    Args:
        read_pool: readonly ロールの pool（``make_pool(role='readonly')``）。raw SELECT のみ。
        write_pool: ETL ロールの pool（``make_pool(role='etl')``）。``label`` スキーマへの
            INSERT/DROP/RENAME/GRANT を持つ。
        settings: Settings。``db_reader_role`` から GRANT 先ロール名を取得
            （HIGH #3・デフォルト ``'keiba_readonly'``）。

    Returns:
        ``{"rows_inserted": int, "label_unresolved_count": int, "raw_touched": False, "checksum": str}``
        ``raw_touched`` は常に False（成功基準#2・raw には一切書込まない）。
        ``checksum`` は ``label.fukusho_label`` 全行の md5 aggregate・idempotent 実行確認用。
    """
    if settings is None:
        settings = Settings()
    # WR-09: Settings.db_reader_role は ``str = \"keiba_readonly\"``（settings.py:46）で
    # getattr は常に非 None を返すため、未設定警告を発火できないデッドロジックを削除。
    # 明示的に settings.db_reader_role を使用する（HIGH #3 reader ロール明示 GRANT 用）。
    reader_role = settings.db_reader_role

    # --- READ（readonly pool）---
    with read_pool.connection() as conn:
        with conn.cursor() as cur:
            hr_df = _select_raw_harai(cur)
            se_df = _select_se_state(cur)
            race_df = _select_race_meta(cur)
        # WR-08: SELECT only だが明示的に rollback し read transaction を確実に閉じる
        # （psycopg_pool は context manager 抜けで自動 rollback するが、明示することで
        # 後続する write_pool の staging-swap とのロック衝突を構造的に防ぐ）。
        conn.rollback()

    # --- TRANSFORM ---
    label_df = compute_fukusho_labels(hr_df, se_df, race_df)
    unresolved_count = int((label_df["label_validation_status"] == "unresolved").sum())
    logger.info(
        "compute_fukusho_labels: rows=%d, unresolved=%d, dead_heat=%d, validated=%d",
        len(label_df),
        unresolved_count,
        int((label_df["label_validation_status"] == "dead_heat").sum()),
        int((label_df["label_validation_status"] == "validated").sum()),
    )

    rows = _df_to_tuples_label(label_df, _LABEL_INSERT_COLUMNS)

    # --- WRITE（etl pool・staging-swap idempotent）---
    with write_pool.connection() as conn:
        with conn.cursor() as wcur:
            rows_inserted = _idempotent_load_label(
                wcur, rows, _LABEL_INSERT_COLUMNS, reader_role=reader_role
            )
            # --- post-condition: staging-swap 後の race_date NULL 二重防波堤 ---
            # compute_fukusho_labels の fail-loud を抜けた場合（race_df 状態は正常だが
            # INSERT/staging-swap のどこかで race_date が欠損した等の異常）の最終検知。
            # staging-swap（DROP+RENAME）完了後の実表 label.fukusho_label に対して
            # SELECT count(*) WHERE race_date IS NULL を実行し、>0 なら fail-loud する。
            # null_count == 0 の場合は挙動不变（以降の checksum 計算・conn.commit() へ進む）。
            # トランザクションは RuntimeError で context を抜けることで rollback される
            # （conn.commit() に到達しない）。
            wcur.execute(
                "SELECT count(*) FROM label.fukusho_label WHERE race_date IS NULL"
            )
            null_count_row = wcur.fetchone()
            null_count = int(null_count_row[0]) if null_count_row else 0
            if null_count > 0:
                logger.error(
                    "label.fukusho_label post-condition violation: race_date NULL %d / %d rows"
                    "（compute_fukusho_labels を抜けたが最終表で NULL 残存・二重防波堤）",
                    null_count,
                    rows_inserted,
                )
                raise RuntimeError(
                    "label.fukusho_label post-condition violation: race_date に NULL が "
                    f"{null_count} / {rows_inserted} 行残存（staging-swap 後の最終検知・"
                    "二重防波堤）。compute_fukusho_labels の fail-loud を抜けたが INSERT/"
                    "staging-swap のどこかで race_date が欠損した。診断ログを確認すること。"
                )
            # checksum（idempotent 実行確認用・HIGH #3）
            # WR-07: row(r.*)::text は列順序依存で ALTER TABLE で checksum が変わる
            # ため、_LABEL_INSERT_COLUMNS で列を明示して順序非依存にする。
            cols_csv = ", ".join(_LABEL_INSERT_COLUMNS)
            wcur.execute(
                f"SELECT md5(string_agg(md5(row({cols_csv})::text), '' "
                f"ORDER BY year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)) "
                f"FROM label.fukusho_label"
            )
            checksum_row = wcur.fetchone()
            checksum = str(checksum_row[0]) if checksum_row and checksum_row[0] is not None else ""
        conn.commit()

    return {
        "rows_inserted": rows_inserted,
        "label_unresolved_count": unresolved_count,
        "raw_touched": False,
        "checksum": checksum,
    }


__all__ = [
    "run_label_etl",
    "compute_fukusho_labels",
    "classify_status",
    "compute_is_model_eligible",
    "_canonicalize_markers",
    "_select_raw_harai",
    "_select_se_state",
    "_select_race_meta",
    "_idempotent_load_label",
    "_create_label_table",
    "load_label_spec",
]
