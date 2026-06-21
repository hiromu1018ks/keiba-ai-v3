# ruff: noqa: E501
"""JODDS 時系列オッズの固定時点選択（D-01 / D-02 / BACK-04 / §11.2 / §13）.

Phase 5 EV/backtest で「発走N分前」の JODDS snapshot を選択する service 層。
リーク防止の構造的ブロック（T-05-06/06b/07/07b/10/10b/22 mitigate・Core Value 直結）を提供する。

**設計の核心（RESEARCH §1.1-§1.4 / Plan 05-03）:**

1. **HIGH-1 馬単位オッズ保証**: ``merge_asof`` の ``by=['race_key','umaban']`` で各馬に
   固有の odds を割り当てる。JODDS PK は race_key 7カラム + Umaban の 8カラム
   （RESEARCH §1.1 実証）。race_key 単独の by= では同一レース内で別馬の odds で
   上書きされる silent leak を構造的に排除（T-05-06b mitigate）。
2. **未来リーク構造的不可（D-02・T-05-06 mitigate）**: ``merge_asof(direction='backward')``
   で cutoff_datetime 以降の未来 snapshot が選択されない。CLAUDE.md §13 PIT プリミティブ
   と同一思想。
3. **DataKubun='1'(中間) 固定（D-01・T-05-07 mitigate）**: ``n_jodds_tanpuku`` 本体テーブルは
   ``DataKubun`` 列を持たない（RESEARCH Pitfall 2）。``n_jodds_tanpukuwaku_head`` と JOIN して
   ``datakubun='1'`` で filter（確定 '4' / 最終 '3' 混入防止）。
4. **HIGH-3 canonical rule**: 特殊値 ``----``/``****``/``0000``/``0999``/`` ``(sp) は全て
   ``no_bet`` sentinel。CONTEXT D-02 を正とし・RESEARCH 行89 の「0999=99.9倍以上」記述は
   本モジュールで廃棄（T-05-07b mitigate）。
5. **silent fallback 禁止（§11.3・T-05-10 mitigate）**: snapshot 0件・FukusyoFlag が
   '0'/'1'/'3' も ``no_bet`` sentinel。都合の良い別時点への差し替えを行わない。
6. **cross-plan contract**: 戻り値の odds 列は snake_case ``fuku_odds_lower``/``fuku_odds_upper``
   （JODDS raw ``FukuOddsLow``/``FukuOddsHigh`` を rename）。Plan 02 ``ev_rank.py`` と
   Plan 05 ``run_backtest.py`` が JOIN するだけで column 再名不要（T-05-SC2 mitigate）。

**Pitfall 1 日跨ぎ**: ``HassoTime`` が深夜（例: ``0030``）で ``HassoTime - N分`` が前日になる場合、
HHMM 整数比較は破綻する。``race_start_datetime``（race_date + HassoTime 構築済み）基準で
``pd.Timedelta(minutes=N)`` で cutoff を計算すれば自動解決。

参照: 05-RESEARCH.md §1.1-§1.4 / 05-PATTERNS.md odds_snapshot.py 節 /
      src/model/baseline.py::fetch_market_data (readonly_cur + parameterized query analog) /
      CLAUDE.md §13 (merge_asof direction='backward').
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# odds_snapshot_policy が取り得る固定値（§11.2・事前登録・レース後変更不可）
ODDS_SNAPSHOT_POLICIES: dict[str, int] = {
    "30min_before": 30,
    "10min_before": 10,
}

# odds 欠損 sentinel とみなす FukuOddsLow/FukuOddsHigh の特殊値（HIGH-3 canonical・CONTEXT D-02 正）
# RESEARCH §1.1 + Plan 05-03 must_haves: 0999 も odds 欠損 sentinel（RESEARCH 行89 廃棄）。
# ' '(sp)=登録なし も sentinel。
_NO_BET_SPECIAL_VALUES: frozenset[str] = frozenset({
    "----",   # 発売前取消
    "****",   # 発売後取消
    "0000",   # 無投票
    "0999",   # odds 欠損 sentinel（HIGH-3 canonical・CONTEXT D-02 正）
    "",       # 空文字
    " ",      # sp = 登録なし（EveryDB2 マニュアル）
})

# FukusuoFlag の no_bet 扱い値（RESEARCH §1.1・EveryDB2 マニュアル）
# '7'(発売あり) のみ正常発売・それ以外は no_bet
_NO_BET_FUKUSYOFLAGS: frozenset[str] = frozenset({"0", "1", "3"})

# odds_source_type sentinel（§11.2 保持項目・odds provenance）
ODDS_SOURCE_TYPE_JODDS = "jodds_tanpuku"


def fetch_jodds(
    readonly_cur: Any,
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """``public.n_jodds_tanpuku`` (時系列オッズ単複) + ``n_jodds_tanpukuwaku_head`` JOIN で
    中間オッズ (``datakubun='1'``) の snapshot を取得する（D-01・readonly_cur で SELECT-only）。

    JODDS PK は race_key 7カラム (Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum) + HappyoTime +
    Umaban = 9カラム（RESEARCH §1.1 実証）。head テーブルは Umaban を持たないため 7カラム PK で
    JOIN して ``DataKubun``/``FukusyoFlag`` を取得（Pitfall 2: 本体テーブルに DataKubun 列無し）。

    Parameters
    ----------
    readonly_cur : readonly ロールの cursor（``public`` schema へ SELECT 権限）。
    year : 指定された場合その年のレースに絞る（パフォーマンス推奨）。

    Returns
    -------
    pd.DataFrame
        以下の列を持つ DataFrame（全て JODDS raw 列名・select_odds_snapshot が snake_case へ rename）:
        ``year, monthday, jyocd, kaiji, nichiji, racenum, umaban, happyotime,
        fukuoddslow, fukuoddshigh, fukusyoflag, datakubun``。
        ``race_key`` (``f"{year}-{monthday}-{jyocd}-{kaiji}-{nichiji}-{racenum}"``) も付与。
        ``happyo_datetime`` (Timestamp・mmddHHMM を year 基準で解釈) も付与。
    """
    where_clauses: list[str] = ["h.datakubun = '1'"]  # 中間オッズ固定（D-01）
    params: list[Any] = []
    if year is not None:
        where_clauses.append("j.year = %s")
        params.append(str(year))
    where_sql = "WHERE " + " AND ".join(where_clauses)

    # baseline.py::fetch_market_data パターン（readonly_cur + parameterized query + CAST(int) JOIN）
    # head テーブルは Umaban 列を持たないため 7カラム PK (HappyoTime 含む) で JOIN。
    query = f"""
        SELECT
            j.year, j.monthday, j.jyocd, j.kaiji, j.nichiji, j.racenum,
            j.umaban,
            j.happyotime,
            j.fukuoddslow,
            j.fukuoddshigh,
            h.fukusyoflag,
            h.datakubun
        FROM public.n_jodds_tanpuku j
        JOIN public.n_jodds_tanpukuwaku_head h
            ON j.year = h.year
            AND j.monthday = h.monthday
            AND j.jyocd = h.jyocd
            AND j.kaiji::int = h.kaiji::int
            AND j.nichiji = h.nichiji
            AND j.racenum::int = h.racenum::int
            AND j.happyotime = h.happyotime
        {where_sql}
    """
    readonly_cur.execute(query, params)
    cols = [d.name for d in readonly_cur.description]
    rows = readonly_cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)

    if len(df) == 0:
        # 空結果でも後続の select_odds_snapshot が扱えるよう必要列を整える
        return pd.DataFrame(columns=cols + ["race_key", "happyo_datetime"])

    # race_key 構築 (CR-01): make_race_key と同一の正準形式
    # (year-jyocd-kaiji-nichiji-racenum・5要素・monthday 無し) に統一。
    # 旧実装は 6要素 (monthday 挿入) で・make_race_key / fetch_harai_race_level /
    # _fetch_market_data の暗黙 race_key と絶対に一致せず・実データでオッズ全件 NaN 化。
    # monthday は happyo_datetime 計算用に別途保持 (SELECT 列に残す)。
    from src.model.data import make_race_key

    df["race_key"] = make_race_key(df).to_numpy()
    # happyo_datetime: mmddHHMM (例 '01031833') を year 基準で完全日時に解釈
    # HappyoTime は mmddHHMM varchar(8)
    df["happyo_datetime"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["happyotime"].astype(str).str[:2]
        + "-" + df["happyotime"].astype(str).str[2:4] + " "
        + df["happyotime"].astype(str).str[4:6] + ":"
        + df["happyotime"].astype(str).str[6:8],
        errors="coerce",
    )
    # Umaban を int に正規化（merge_asof by= のため）
    df["umaban"] = pd.to_numeric(df["umaban"], errors="coerce").astype("Int64")
    return df


def _is_no_bet_value(val: object) -> bool:
    """FukuOddsLow/High の値が no_bet sentinel か判定する（HIGH-3 canonical）。

    ``----``/``****``/``0000``/``0999``/`` ``(sp)/NaN のいずれかなら no_bet。
    """
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    sval = str(val).strip()
    return sval in _NO_BET_SPECIAL_VALUES


def _parse_odds(val: object) -> float:
    """``FukuOddsLow``/``FukuOddsHigh`` (varchar(4)・例 '0011' → 1.1) を float に変換。

    no_bet sentinel は NaN。正常値は ``int(val) / 10.0``（EveryDB2: 1.1倍='0011'）。
    """
    if _is_no_bet_value(val):
        return float("nan")
    try:
        # '0011' → 11 → 1.1 / '0999' は _is_no_bet_value で NaN 済み
        return int(str(val).strip()) / 10.0
    except (ValueError, TypeError):
        return float("nan")


def select_odds_snapshot(
    jodds_df: pd.DataFrame,
    race_times: pd.DataFrame,
    policy: str,
) -> pd.DataFrame:
    """``odds_snapshot_policy`` で固定時点の JODDS snapshot を選択する（D-01/D-02・BACK-04）。

    ``merge_asof(direction='backward', by=['race_key','umaban'])`` で各馬単位の cutoff 以下
    最大 snapshot を選択（HIGH-1 per-horse odds 保証・D-02 未来リーク構造的不可）。

    Parameters
    ----------
    jodds_df : JODDS snapshot DataFrame。必須列:
        ``race_key, umaban, happyotime, happyo_datetime, fukuoddslow, fukuoddshigh,
        fukusyoflag, datakubun``（``fetch_jodds`` 戻り値・合成 mock でも可）。
        ``datakubun`` が存在する場合は ``'1'``(中間) のみ使用（D-01・Pitfall 2・T-05-07 mitigate）。
    race_times : 予測対象馬単位の cutoff 候補。必須列:
        ``race_key, umaban, race_start_datetime``（馬単位であることが前提・HIGH-1）。
    policy : ``'30min_before'`` / ``'10min_before'``。cutoff = race_start_datetime - N分。

    Returns
    -------
    pd.DataFrame
        ``race_times`` と同行数。以下の列を付与:
        - ``fuku_odds_lower`` / ``fuku_odds_upper`` (float・snake_case・cross-plan contract)
        - ``happyotime`` (選択した snapshot の HappyoTime)
        - ``odds_snapshot_at`` (選択 snapshot の happyo_datetime・Timestamp)
        - ``odds_source_type`` (``'jodds_tanpuku'`` sentinel)
        - ``odds_missing_reason`` (``'no_bet_empty'`` / ``'no_bet'`` / NaN)
        - ``fukusyoflag`` / ``datakubun`` (選択 snapshot の値)
    """
    if policy not in ODDS_SNAPSHOT_POLICIES:
        raise ValueError(
            f"policy は {list(ODDS_SNAPSHOT_POLICIES)} のいずれか (got {policy!r})"
        )
    minutes = ODDS_SNAPSHOT_POLICIES[policy]

    # 入力の防衛的 copy（純粋関数・入力破壊禁止）
    jodds = jodds_df.copy()
    cutoff_base = race_times.copy()

    # DataKubun filter（D-01・Pitfall 2・T-05-07 mitigate）
    # datakubun 列が存在する場合のみ '1'(中間) で filter（合成 mock でも省略可能）
    if "datakubun" in jodds.columns:
        jodds = jodds[jodds["datakubun"].astype(str) == "1"].copy()

    # cutoff_datetime 計算（Pitfall 1 日跨ぎ回避・race_start_datetime + Timedelta）
    cutoff_base["cutoff_datetime"] = (
        cutoff_base["race_start_datetime"] - pd.Timedelta(minutes=minutes)
    )

    # 列の型正規化（merge_asof by= のため）
    jodds["umaban"] = pd.to_numeric(jodds["umaban"], errors="coerce").astype("Int64")
    cutoff_base["umaban"] = pd.to_numeric(cutoff_base["umaban"], errors="coerce").astype("Int64")

    # 結果格納用ベース（race_times の各行に対し1行ずつ）
    n_expected = len(cutoff_base)
    result_rows: list[dict[str, object]] = []

    if len(jodds) == 0:
        # snapshot 0件 → 全候補 no_bet_empty sentinel（silent fallback 禁止・§11.3）
        for _, rt in cutoff_base.iterrows():
            result_rows.append({
                "race_key": rt["race_key"],
                "umaban": rt["umaban"],
                "fuku_odds_lower": float("nan"),
                "fuku_odds_upper": float("nan"),
                "happyotime": None,
                "odds_snapshot_at": pd.NaT,
                "odds_source_type": ODDS_SOURCE_TYPE_JODDS,
                "odds_missing_reason": "no_bet_empty",
                "fukusyoflag": None,
                "datakubun": None,
            })
        return pd.DataFrame(result_rows)

    # merge_asof 前提: 両フレーム sort_values（by=['race_key','umaban'] + 結合キーで sort）
    # MEDIUM-C cycle-2: race_key 優先 sort で happyo_datetime の大域ソートが崩れても
    # merge_asof は by= グループ内で sort 済みであれば正常動作（pandas by= セマンティクス）
    jodds_sorted = jodds.sort_values(
        ["race_key", "umaban", "happyo_datetime"]
    ).reset_index(drop=True)
    cutoff_sorted = cutoff_base.sort_values(
        ["race_key", "umaban", "cutoff_datetime"]
    ).reset_index(drop=True)

    # HIGH-1: by=['race_key','umaban'] で per-horse as-of join（未来リーク構造的不可）
    merged = pd.merge_asof(
        cutoff_sorted,
        jodds_sorted,
        left_on="cutoff_datetime",
        right_on="happyo_datetime",
        by=["race_key", "umaban"],
        direction="backward",  # ← 未来 snapshot 構造的不可（D-02・T-05-06 mitigate）
    )

    # 結果組み立て（cross-plan contract: snake_case へ rename + no_bet sentinel 付与）
    for _, row in merged.iterrows():
        raw_low = row.get("fukuoddslow")
        raw_high = row.get("fukuoddshigh")
        fsf = row.get("fukusyoflag")
        happyo_dt = row.get("happyo_datetime")
        happyo_time = row.get("happyotime")

        # snapshot が選択されなかった場合（merge_asof 該当無し・happyo_datetime=NaT）
        no_bet_empty = pd.isna(happyo_dt) if happyo_dt is not None else True

        # odds 変換（HIGH-3 canonical: 0999/----/****/0000/sp → NaN）
        foku_lower = _parse_odds(raw_low)
        foku_upper = _parse_odds(raw_high)

        # odds_missing_reason 判定
        if no_bet_empty:
            missing_reason = "no_bet_empty"
        elif (
            _is_no_bet_value(raw_low)
            or _is_no_bet_value(raw_high)
            or (str(fsf).strip() in _NO_BET_FUKUSYOFLAGS if fsf is not None else False)
        ):
            missing_reason = "no_bet"
        else:
            missing_reason = None  # 正常 odds

        # no_bet の場合は odds を NaN 化（silent fallback 禁止）
        if missing_reason is not None:
            foku_lower = float("nan")
            foku_upper = float("nan")

        result_rows.append({
            "race_key": row["race_key"],
            "umaban": row["umaban"],
            "fuku_odds_lower": foku_lower,
            "fuku_odds_upper": foku_upper,
            "happyotime": happyo_time if not no_bet_empty else None,
            "odds_snapshot_at": happyo_dt if not no_bet_empty else pd.NaT,
            "odds_source_type": ODDS_SOURCE_TYPE_JODDS,
            "odds_missing_reason": missing_reason,
            "fukusyoflag": fsf if not no_bet_empty else None,
            "datakubun": row.get("datakubun") if not no_bet_empty else None,
        })

    result_df = pd.DataFrame(result_rows)
    # 行数不変（HIGH-1・race_times と同行数）
    assert len(result_df) == n_expected, (
        f"select_odds_snapshot 行数不変条件違反: expected {n_expected}, got {len(result_df)}"
    )
    return result_df
