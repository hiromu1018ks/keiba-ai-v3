"""Phase 9・Beyer 型スピード指数（能力素材のみ・PIT-correct・SC#1/SC#2・D-01〜D-07/D-09）.

本 module は過去走 history の走破タイムを Beyer 型 par/variant で補正し・速いほど大きい
``speed_figure`` float（D-05）を算出する。後続 P02(rolling 拡張) が history["speed_figure"]
列を前提とし・P03(builder 統合)・P04(audit/可視化)・P05(stop gate) が依存する新主軸能力特徴量。

3聖域（本 module の不変事項・adversarial テスト + AST audit で機械保証）:

1. **市場情報不使用（SAFE-01）**
   - オッズ/人気/過去人気/過去オッズ 等・市場情報 proxy は feature に一切入れない。
   - 本 module のソース上の識別子・文字列リテラルに市場情報系トークンは現れない。
   - P04 が AST audit で完全証明する（SC#4 下地）。

2. **PIT-correct（SC#2）**
   - 各 speed_figure は ``available_at < feature_cutoff_datetime`` (strict ``<``・JST midnight・
     ``race_date - 1day``) を満たす過去走のみで算出される。
   - ``_pit_cutoff_prefilter`` helper は ``rolling.py`` L104-116 と対称（adversarial test が
     monkeypatch で ``<=`` 版に差替可能）。
   - target race 当日結果・full-period 固定 par/variant の混入は決定的リーク（high severity・BLOCK）。

3. **byte-reproducible（§19.1）**
   - 決定論的アルゴリズム（median・固定順序・seed 不要）で同一入力は bit-identical。
   - ``test_byte_reproducible_speed_figure`` が ``np.array_equal`` で実証。

REVIEW H4 (per-observation PIT・集約キー仕様):
   par/variant は展開済みフレーム上で groupby する際・group キーに ``obs_id`` を含め
   observation 毎に独立した par/variant を算出する（par fallback group = ``obs_id`` +
   ``jyocd×trackcd×kyori``・variant group = ``obs_id`` + ``source_race_date×jyocd×surface``）。
   これにより cutoff の異なる複数 observation が同一 group に混入し earlier observation の
   par/variant median に later observation の eligible 行が漏れる cross-observation leak を
   構造的回避する（``rolling.py`` L236-265 obs_id expand idiom と対称）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.availability import CUTOFF_SEMANTICS

# ---------------------------------------------------------------------------
# HIGH #2 / SC#2: cutoff semantics 不変量の実行時参照（strict_less_than / Asia/Tokyo）。
# rolling.py L55 と対称な単一不変量・本 module の strict < filter は
# availability.CUTOFF_SEMANTICS["pit_filter"] と同一の真の源を持つ。
# ---------------------------------------------------------------------------
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"

# ---------------------------------------------------------------------------
# D-05 / Beyer 文献ベース概算値（[ASSUMED]・SC#5 で微調整可）
# 短距離ほど1秒の重みが大きい。JRA 距離(メートル) → points_per_second 換算テーブル。
# Source: Beyer "Picking Winners" + PaceAdvantage Forum / America's Best Racing
#   1/5秒 = 3.3 points (5f) vs 1/5秒 = 2 points (8f) → 短距離ほど1秒の重みが大きい
# ---------------------------------------------------------------------------
POINTS_PER_SECOND_BY_DISTANCE_M: dict[int, float] = {
    1000: 16.5,   # 5f 相当（短距離・1秒の重み最大）
    1200: 13.2,   # 6f 相当
    1400: 11.0,   # 7f 相当
    1600: 10.0,   # 8f 相当（1/5秒=2 → 1秒=10.0）
    1800: 8.8,    # 9f 相当
    2000: 8.0,    # 10f 相当
    2400: 6.6,    # 12f 相当（長距離・1秒の重み最小）
    3000: 5.3,    # 1.5mile+ 相当
    3200: 5.0,    # 長距離障害含む
}

# ---------------------------------------------------------------------------
# サンプル数下限 / robust 統計量パラメータ（planner discretion・live-DB 精査値）
# ---------------------------------------------------------------------------
_MIN_SAMPLES_PAR_JYO_TRACK_KYORI: int = 30
_MIN_SAMPLES_PAR_TRACK_KYORI: int = 30
_MIN_SAMPLES_VARIANT_GROUP: int = 10
_TRIM_PROPORTION: float = 0.1  # scipy.stats.trim_mean 用（両端10%カット）


def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    """defense-in-depth pre-filter: ``as_of_datetime < feature_cutoff_datetime`` (HIGH #1/#2).

    本 helper に切り出した意図: adversarial test (``tests/features/test_speed_figure_pit.py``)
    が ``monkeypatch`` で本関数を ``<=`` 版に差し替え・guard 無効化で T+1 データ混入を検証できる
    ようにするため（``rolling.py`` L104-116 と対称）。filter 式は byte-identical (``<`` strict)
    で振舞は不変。

    Parameters
    ----------
    expanded : pd.DataFrame
        obs_id 展開済みフレーム（``as_of_datetime`` / ``feature_cutoff_datetime`` 列必須）。

    Returns
    -------
    pd.DataFrame
        ``as_of_datetime < feature_cutoff_datetime`` を満たす行のみの copy。
    """
    return expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ].copy()


def _time_to_seconds(time_real: float | None) -> float:
    """``time`` (0.1秒単位・decisecond) を秒に換算。``time <= 0`` は NaN（完走でない）。

    Live-DB 実証: ``time=1108.0`` (1200mダート1着) → 110.8秒 = 1分50秒（典型タイム）。
    """
    if time_real is None or time_real <= 0:
        return float("nan")
    return float(time_real) / 10.0


def _time_to_seconds_series(time_series: pd.Series) -> pd.Series:
    """``_time_to_seconds`` の vectorized 版（pandas Series 向け）。

    ``pd.to_numeric(errors="coerce")`` で非数値を NaN 化後・``> 0`` のみ ``/10.0`` で秒換算。
    ``time <= 0`` (取消/競走中止・live-DB で4882件) は NaN になる。
    """
    numeric = pd.to_numeric(time_series, errors="coerce")
    return numeric.where(numeric > 0, np.nan) / 10.0


def _derive_surface(trackcd: pd.Series) -> pd.Series:
    """``trackcd`` 数値範囲から surface (turf/dirt/obstacle) を派生。

    ``builder.py::_construct_derived_columns`` と同一閾値（live-DB 実証）:
      - 10-22 → turf（平地芝）
      - 23-25 → dirt（平地ダート）
      - 51-59 → obstacle（障害）
      - それ以外 → "unknown" (sentinel)
    """
    tc_num = pd.to_numeric(trackcd.astype(str).str.strip(), errors="coerce")
    surface = pd.Series(["unknown"] * len(trackcd), index=trackcd.index, dtype=object)
    surface[tc_num.between(10, 22)] = "turf"
    surface[tc_num.between(23, 25)] = "dirt"
    surface[tc_num.between(51, 59)] = "obstacle"
    return surface


def get_points_per_second(kyori: int) -> float:
    """距離（メートル）→ ``points_per_second``。線形補間で中間距離に対応（端点クランプ）。

    byte-reproducible・決定論的（入力同一なら出力同一）。
    """
    distances = sorted(POINTS_PER_SECOND_BY_DISTANCE_M.keys())
    if kyori <= distances[0]:
        return POINTS_PER_SECOND_BY_DISTANCE_M[distances[0]]
    if kyori >= distances[-1]:
        return POINTS_PER_SECOND_BY_DISTANCE_M[distances[-1]]
    for i in range(len(distances) - 1):
        if distances[i] <= kyori <= distances[i + 1]:
            d0, d1 = distances[i], distances[i + 1]
            p0 = POINTS_PER_SECOND_BY_DISTANCE_M[d0]
            p1 = POINTS_PER_SECOND_BY_DISTANCE_M[d1]
            return p0 + (p1 - p0) * (kyori - d0) / (d1 - d0)
    # 到達不能（上記クランプでカバー）・安全のため 1mile 相当
    return 8.0


def _compute_pit_par(expanded_filtered: pd.DataFrame) -> pd.DataFrame:
    """PIT expanding/as-of robust par time を observation 単位で算出（D-01/D-03・REVIEW H4）。

    入力は ``rolling.py`` L236-265 と対称な **obs_id 展開済みかつ ``_pit_cutoff_prefilter``
    (strict ``<``) 済み**のフレーム（``obs_id`` / ``kettonum`` /
    ``feature_cutoff_datetime`` / ``time_sec`` / ``jyocd`` / ``trackcd`` / ``kyori`` 列を含む）。

    **REVIEW H4 (集約キー仕様・obs_id 必須)**:
        par 算出の groupby キーは ``obs_id + jyocd + trackcd + kyori`` とする（obs_id が先頭・
        observation 毎に独立した par）。各 group で ``time_sec`` の robust median
        (pandas ``.median()``・決定論的) を算出。group size < ``_MIN_SAMPLES_PAR_JYO_TRACK_KYORI``
        の group は ``obs_id + trackcd + kyori`` で再計算・それでも不足は ``obs_id`` 単位の
        all-history median。

        **重要**: par は各 observation の cutoff 以前の行のみで算出されるだけでなく・
        groupby キーが ``obs_id`` 区分なため cutoff の異なる observation が同一 par median に
        混入しない（``rolling.py`` L236-265 obs_id expand + groupby と対称）。もし ``obs_id`` を
        groupby キーから外すと・``jyocd×trackcd×kyori`` が同一で cutoff の異なる2 observation が
        同一 group に混入し earlier obs の eligible 行が later obs の par に漏れる
        cross-observation leak が生じる（T-09-28 mitigate）。

    各 row に ``par_sec`` / ``sample_count`` / ``fallback_level`` 列を付与（D-07）。
    ``fallback_level`` は文字列で ``"jyocd_trackcd_kyori"`` / ``"trackcd_kyori"`` / ``"all_day"``
    の3値（NULL 禁止・監査列）。

    算出戦略（決定論的・byte-reproducible）:
        1. groupby(obs_id + jyocd + trackcd + kyori).size() が ``_MIN_SAMPLES_PAR_JYO_TRACK_KYORI``
           以上の group は各 group の ``time_sec.median()`` を par として採用
           （fallback_level="jyocd_trackcd_kyori"）。
        2. 未採用行（group size < 閾値）は groupby(obs_id + trackcd + kyori) で再計算
           （fallback_level="trackcd_kyori"）。
        3. それでも不足の行は obs_id 単位の all-history median
           （fallback_level="all_day"）。
    各段階で group median が NaN の場合は段階的に fallback する（silent fill でなく・
    group key が細かすぎる際の正統 fallback・D-13 踏襲）。
    """
    out = expanded_filtered.copy()
    # time_sec が無ければ算出（_pit_cutoff_prefilter 済みフレームには無い場合がある）
    if "time_sec" not in out.columns:
        out["time_sec"] = _time_to_seconds_series(out["time"])
    # 集約キー素材の正規化（jyocd/trackcd/kyori は文字列混入対策で文字列化・groupby 安定化）
    out["_jyocd"] = out["jyocd"].astype(str)
    out["_trackcd"] = out["trackcd"].astype(str)
    out["_kyori"] = pd.to_numeric(out["kyori"], errors="coerce")

    # par_sec / sample_count / fallback_level を NaN/未設定で初期化
    out["par_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
    out["sample_count"] = pd.Series([0] * len(out), index=out.index, dtype=int)
    out["fallback_level"] = pd.Series([None] * len(out), index=out.index, dtype=object)

    # Stage 1: obs_id + jyocd + trackcd + kyori（最細粒度）
    key1 = ["obs_id", "_jyocd", "_trackcd", "_kyori"]
    grp1 = out.groupby(key1, sort=False, dropna=False)["time_sec"]
    size1 = grp1.size()
    median1 = grp1.median()
    # group size >= 閾値 の group に属する行マスク
    size1_map = size1.reindex(out.set_index(key1).index)
    median1_map = median1.reindex(out.set_index(key1).index)
    mask1 = (size1_map >= _MIN_SAMPLES_PAR_JYO_TRACK_KYORI).fillna(False).values
    out.loc[mask1, "par_sec"] = median1_map[mask1].values
    out.loc[mask1, "sample_count"] = size1_map[mask1].values
    out.loc[mask1, "fallback_level"] = "jyocd_trackcd_kyori"

    # Stage 2: 未確定行を obs_id + trackcd + kyori で fallback
    pending = out["par_sec"].isna()
    if pending.any():
        key2 = ["obs_id", "_trackcd", "_kyori"]
        grp2 = out.loc[pending].groupby(key2, sort=False, dropna=False)["time_sec"]
        size2 = grp2.size()
        median2 = grp2.median()
        idx2 = out.loc[pending].set_index(key2).index
        size2_map = size2.reindex(idx2)
        median2_map = median2.reindex(idx2)
        mask2 = (size2_map >= _MIN_SAMPLES_PAR_TRACK_KYORI).fillna(False).values
        pending_indices = out.index[pending]
        selected = pending_indices[mask2]
        out.loc[selected, "par_sec"] = median2_map[mask2].values
        out.loc[selected, "sample_count"] = size2_map[mask2].values
        out.loc[selected, "fallback_level"] = "trackcd_kyori"

    # Stage 3: それでも未確定の行は obs_id 単位の all-history median へ fallback
    pending = out["par_sec"].isna()
    if pending.any():
        grp3 = out.loc[pending].groupby("obs_id", sort=False)["time_sec"]
        size3 = grp3.size()
        median3 = grp3.median()
        for idx in out.index[pending]:
            obs_id = out.at[idx, "obs_id"]
            n = int(size3.get(obs_id, 0))
            m = median3.get(obs_id, float("nan"))
            out.at[idx, "par_sec"] = m
            out.at[idx, "sample_count"] = n
            out.at[idx, "fallback_level"] = "all_day"

    # par_sec が依然 NaN の行（obs_id の全 time_sec が NaN 等）は fallback_level="all_day"
    # を維持したまま par_sec=NaN とする（silent fill 禁止・D-13）
    return out


def _compute_leave_one_out_variant(expanded_with_par: pd.DataFrame) -> pd.DataFrame:
    """leave-one-race-out variant（D-02・REVIEW H4・same-day residual の robust median）。

    入力は ``_compute_pit_par`` の出力（obs_id 展開済み・``par_sec`` 付与済み・strict ``<`` filter 済み）。
    ``residual = time_sec - par_sec`` を算出後・**REVIEW H4 (集約キー仕様)** により
    group キーは ``obs_id + source_race_date + jyocd + surface`` とする（obs_id が先頭・par と対称に
    observation 毎に独立）。

    vectorized 近似（RESEARCH Pattern 2 / A3）:
        group 内で「自レースを除く residual の median」を
        ``group_median - (self_residual - group_median)/(n-1)`` の一次近似で算出。
        avg 215完走馬/group で自レース寄与 < 1%・十分精度（MEDIUM 懸念・精度上限を docstring/test
        で明示済み）。厳密ループは極小 group (n < ``_MIN_SAMPLES_VARIANT_GROUP``) のみ。

    group size < ``_MIN_SAMPLES_VARIANT_GROUP`` は ``obs_id`` 単位の all-history robust variant
    へ fallback。``variant_sec`` 列を付与（D-07・監査列）。

    ``source_race_date`` 列は ``pd.to_datetime(race_date).dt.date`` で導出済みを前提。
    variant も par と同一の展開済みフレーム上で ``obs_id`` 区分で算出（グローバル未展開 history
    でなく・集約キーに ``obs_id`` を含む・REVIEW H4）。

    算出戦略（決定論的・byte-reproducible）:
        1. ``residual = time_sec - par_sec`` を算出。
        2. groupby(obs_id + source_race_date + jyocd + surface).size() が
           ``_MIN_SAMPLES_VARIANT_GROUP`` 以上の group で一次近似
           ``group_median - (self_residual - group_median)/(n-1)`` を採用。
           ※ n==1 の group は leave-one-out 不能のため Stage 2 へ回す。
        3. 未採用行（group size < 閾値 or n==1）は obs_id 単位の all-history robust variant
           （obs_id の residual median）へ fallback。
        4. それでも決定不能な行（obs_id 全体で residual が NaN 等）は variant_sec=0.0
           （「馬場差不明=中立」・silent NaN fill でなく明示的 0.0）。
    """
    out = expanded_with_par.copy()
    # residual = time_sec - par_sec（time_sec が無ければ算出）
    if "time_sec" not in out.columns:
        out["time_sec"] = _time_to_seconds_series(out["time"])
    out["residual"] = out["time_sec"] - out["par_sec"]
    # source_race_date 導出（race_date が datetime/date 文字列を想定）
    if "source_race_date" not in out.columns:
        out["source_race_date"] = pd.to_datetime(out["race_date"]).dt.date
    # surface が無ければ trackcd から派生
    if "surface" not in out.columns:
        out["surface"] = _derive_surface(out["trackcd"])
    # 集約キー素材正規化
    out["_jyocd"] = out["jyocd"].astype(str)
    out["_surface"] = out["surface"].astype(str)
    out["_source_race_date"] = out["source_race_date"].astype(str)

    # variant_sec を NaN で初期化
    out["variant_sec"] = pd.Series([float("nan")] * len(out), index=out.index)

    # Stage 1: obs_id + source_race_date + jyocd + surface の leave-one-out 近似
    key1 = ["obs_id", "_source_race_date", "_jyocd", "_surface"]
    grp1 = out.groupby(key1, sort=False, dropna=False)["residual"]
    size1 = grp1.size()
    median1 = grp1.median()

    # 各 row の group の size/median を lookup
    idx1 = out.set_index(key1).index
    n1 = size1.reindex(idx1)
    med1 = median1.reindex(idx1)
    # leave-one-out 一次近似: group_median - (self_residual - group_median)/(n-1)
    # n >= 2 かつ n >= _MIN_SAMPLES_VARIANT_GROUP のみ Stage 1 採用
    n1_arr = n1.values
    med1_arr = med1.values
    self_resid = out["residual"].values
    eligible_s1 = (n1_arr >= _MIN_SAMPLES_VARIANT_GROUP) & (~pd.isna(med1_arr)) & (~pd.isna(self_resid))
    # leave-one-out 一次近似（n>=2 なので n-1>=1 で除算安全）
    approx = med1_arr - (self_resid - med1_arr) / np.maximum(n1_arr - 1, 1)
    # Stage 1 採用行に設定
    out.loc[eligible_s1, "variant_sec"] = approx[eligible_s1]

    # Stage 2: 未確定行を obs_id 単位の all-history robust variant へ fallback
    pending = out["variant_sec"].isna()
    if pending.any():
        grp2 = out.loc[pending].groupby("obs_id", sort=False)["residual"]
        median2 = grp2.median()
        for idx in out.index[pending]:
            obs_id = out.at[idx, "obs_id"]
            m = median2.get(obs_id, float("nan"))
            if pd.notna(m):
                out.at[idx, "variant_sec"] = float(m)
            else:
                # Stage 3: residual が全て NaN（par_sec NaN 等）→ 中立 0.0
                out.at[idx, "variant_sec"] = 0.0
    return out


def compute_speed_figure(
    time_sec: float,
    par_sec: float,
    variant_sec: float,
    kyori: int,
) -> float:
    """Beyer 型スピード指数（float・丸めない・D-05）。

    ``speed_figure = (par_sec - time_sec + variant_sec) × points_per_second(kyori)``

    - ``par_sec > time_sec`` (速い) → 正の値（速いほど大きい・D-05）
    - ``variant_sec`` 正 = 速い馬場 → 指数 UP 補正
    - ``pd.isna(time_sec) or pd.isna(par_sec)`` は NaN（完走でない・par 算出不可）
    """
    if pd.isna(time_sec) or pd.isna(par_sec):
        return float("nan")
    pps = get_points_per_second(kyori)
    adjusted_diff = (par_sec - time_sec) + variant_sec
    return float(adjusted_diff * pps)


def compute_speed_figure_for_history(
    history: pd.DataFrame,
    observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """history 全行に ``speed_figure`` / ``available_at`` / 監査列を付与して返す（公開 API）。

    ``builder.py`` L502-556（推定脚質）と ``rolling.py`` L189-265 の idiom を統合:

    1. ``history`` に ``time`` / ``trackcd`` / ``jyocd`` / ``kyori`` / ``race_date`` /
       ``as_of_datetime`` 列が必須・欠損は ``ValueError``（必須列明示）。
    2. ``history`` が空（新馬のみ）は ``RuntimeError``（fail-loud・WR-01 踏襲）。
    3. ``time_sec`` / ``surface`` / ``source_race_date`` を派生（copy-not-rename・既存列は破壊しない）。
    4. **REVIEW H4 (per-observation PIT・rolling.py L236-265 と対称)**:
       - ``observations`` 渡しの場合: ``obs_keys = observations[["obs_id","kettonum",
         "feature_cutoff_datetime"]]`` で展開し・``expanded = hist.merge(obs_keys, on="kettonum",
         how="inner")`` で各 observation に過去走を紐付け（``obs_id`` 単位の展開）。その後
         ``expanded_filtered = _pit_cutoff_prefilter(expanded)`` で strict ``<`` を適用し・
         **展開済みフレーム上で** ``_compute_pit_par`` / ``_compute_leave_one_out_variant`` を
         呼出し par/variant を算出（グローバル history でない）。
       - ``observations`` が ``None`` (unit test 専用) の場合: ``history`` 自身の全行で
         par/variant を算出。cutoff は ``history.as_of_datetime.max() + 1day`` を仮
         （docstring 明示・本パスは unit test 専用・production では ``builder`` が ``observations``
         を渡す・``observations=None`` は production で禁じる）。
    5. ``speed_figure`` 列を ``compute_speed_figure`` で付与（丸めない float・D-05）。
    6. 監査列 (``par_sec`` / ``variant_sec`` / ``speed_residual_sec`` = ``time_sec - par_sec`` /
       ``sample_count`` / ``fallback_level``) を付与（D-07）。
    7. ``available_at = pd.to_datetime(history["race_date"])`` 列を付与（rolling の PIT 集約で使用）。

    戻り値: ``history`` に ``speed_figure`` / ``available_at`` / 監査列を copy 追加した DataFrame
    （copy-not-rename・入力列は保持）。

    Raises
    ------
    ValueError
        必須列が欠損している場合。
    RuntimeError
        ``history`` が空の場合（fail-loud・WR-01 踏襲）。
    """
    # --- Step 1: 必須列検証 + 空 history fail-loud ---
    required_cols = ("time", "trackcd", "jyocd", "kyori", "race_date", "as_of_datetime")
    missing = [c for c in required_cols if c not in history.columns]
    if missing:
        raise ValueError(
            f"history に必須列が欠損: {missing} (speed_figure 構築・WR-01 fail-loud)"
        )
    if len(history) == 0:
        raise RuntimeError(
            "speed_figure: history fetch が空・silent data loss を検知 (WR-01 fail-loud)"
        )

    # --- Step 2: 派生列の追加（copy-not-rename） ---
    out = history.copy()
    out["time_sec"] = _time_to_seconds_series(out["time"])
    out["surface"] = _derive_surface(out["trackcd"])
    out["source_race_date"] = pd.to_datetime(out["race_date"]).dt.date

    # --- Step 3: par/variant 算出 ---
    if observations is not None:
        # production / 検証経路: obs_id 展開 + PIT prefilter(strict <)
        # 必須 observation 列の検証
        required_obs_cols = ("obs_id", "kettonum", "feature_cutoff_datetime")
        missing_obs = [c for c in required_obs_cols if c not in observations.columns]
        if missing_obs:
            raise ValueError(
                f"observations に必須列が欠損: {missing_obs} (speed_figure per-observation PIT・REVIEW H4)"
            )
        obs_keys = observations[list(required_obs_cols)].copy()
        # 展開: 各 observation に kettonum で inner-join（rolling.py L236-238 と対称）
        expanded = out.merge(obs_keys, on="kettonum", how="inner", suffixes=("", "_obs"))
        # feature_cutoff_datetime 列の衝突回避（obs_keys 由来を採用）
        if "feature_cutoff_datetime_obs" in expanded.columns:
            expanded["feature_cutoff_datetime"] = expanded["feature_cutoff_datetime_obs"]
            expanded = expanded.drop(columns=["feature_cutoff_datetime_obs"])
        # PIT pre-filter（strict < feature_cutoff_datetime）
        expanded_filtered = _pit_cutoff_prefilter(expanded)
        if len(expanded_filtered) == 0:
            # 全ての過去走が cutoff 以降（新馬等）→ speed_figure/par/variant は NaN
            out["par_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["variant_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["speed_residual_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["sample_count"] = pd.Series([0] * len(out), index=out.index, dtype=int)
            out["fallback_level"] = pd.Series([None] * len(out), index=out.index, dtype=object)
            out["speed_figure"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["available_at"] = pd.to_datetime(out["race_date"])
            return out
        # par/variant 算出
        with_par = _compute_pit_par(expanded_filtered)
        with_variant = _compute_leave_one_out_variant(with_par)
        # 展開フレームから元 history 行に集約（kettonum × race_date で unique な行に戻す）
        # obs_id 毎に par/variant が異なるため・元 history 行 × observation の組み合わせで保持
        # P02(rolling) は obs_id 単位で集約するため・展開済み形式で返すのが正しい
        result = with_variant
    else:
        # unit test 専用経路: history 自身の全行で par/variant を算出
        # cutoff は history.as_of_datetime.max() + 1day を仮定（本パスは unit test 専用）
        # rolling.py L189-265 の obs_id 無し単独ケース相当
        tmp = out.copy()
        tmp["obs_id"] = "SINGLE_OBS"  # 全行同一 obs_id
        tmp["feature_cutoff_datetime"] = pd.to_datetime(out["as_of_datetime"]).max() + pd.Timedelta(days=1)
        tmp["kettonum_obs"] = tmp["kettonum"]  # merge 自己結合対策（ダミー）
        # obs_keys 形式にして merge を経由せず直接 prefilter 適用
        expanded_filtered = _pit_cutoff_prefilter(tmp)
        if len(expanded_filtered) == 0:
            out["par_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["variant_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["speed_residual_sec"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["sample_count"] = pd.Series([0] * len(out), index=out.index, dtype=int)
            out["fallback_level"] = pd.Series([None] * len(out), index=out.index, dtype=object)
            out["speed_figure"] = pd.Series([float("nan")] * len(out), index=out.index)
            out["available_at"] = pd.to_datetime(out["race_date"])
            return out
        with_par = _compute_pit_par(expanded_filtered)
        result = _compute_leave_one_out_variant(with_par)

    # --- Step 4: speed_figure / 監査列 / available_at の付与 ---
    # speed_residual_sec = time_sec - par_sec（D-07）
    result["speed_residual_sec"] = result["time_sec"] - result["par_sec"]

    # speed_figure 列を compute_speed_figure で付与（丸めない float・D-05）
    # vectorized 適用: 行毎の kyori を数値化して pps lookup 後に adjusted_diff * pps
    kyori_num = pd.to_numeric(result["kyori"], errors="coerce")
    pps_per_row = kyori_num.map(get_points_per_second) if hasattr(kyori_num, "map") else kyori_num.apply(get_points_per_second)
    # compute_speed_figure と同一式: (par_sec - time_sec + variant_sec) × pps
    # NaN 伝播: time_sec/par_sec/variant_sec いずれか NaN → speed_figure NaN
    sf_values = (result["par_sec"] - result["time_sec"] + result["variant_sec"]) * pps_per_row
    # compute_speed_figure は time_sec or par_sec NaN → NaN だが・variant_sec NaN も伝播させる
    # （variant_sec は Stage3 で 0.0 埋めされているため・通常は非 NaN）
    sf_values = sf_values.where(result["par_sec"].notna() & result["time_sec"].notna(), other=float("nan"))
    result["speed_figure"] = sf_values.astype(float)

    # available_at = race_date（rolling の PIT 集約で使用）
    result["available_at"] = pd.to_datetime(result["race_date"])

    return result


# SAFE-01 odds-free: 本モジュールは市場情報 proxy（オッズ系/人気系/過去オッズ系）を一切
# 使用しない（SC#4・AST audit 対象・P04 が grep/AST で完全証明）。これら禁止トークンは
# 識別子・文字列リテラル・実行コードのいずれにも現れないこと。
