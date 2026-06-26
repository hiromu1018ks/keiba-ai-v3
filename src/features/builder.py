"""Feature matrix 公開 API（Phase 3 Plan 03-03 Task 3 / SC#1 / SC#2 / §13.2）.

``build_feature_matrix(read_pool, *, snapshot_id, label_version, fa_version,
train_period, validation_period)`` が readonly pool から PIT-correct feature matrix
を構築する。PIT correctness（SC#1）と禁止 feature 構造的排除（SC#2）は実装で保証し、
Plan 03-01 の RED unit test が GREEN 化をもって契約履行を証明する。

設計要点:
  - **readonly ロールのみ**（D-06）・``make_pool(role='readonly')`` が search_path
    ``public,normalized,label`` を持つ（``src/db/connection.py``）。
  - **明示カラム SELECT のみ**（ワイルドカード SELECT 禁止・Pitfall 1）。
    ``_HISTORY_SELECT_COLUMNS`` は ``TARGET_OBS_BANNED_COLUMNS``（当日禁止）と disjoint で
    起動時に assert（HIGH #4）。
  - **cutoff D-06**: ``feature_cutoff_datetime = race_date - 1 day``（JST midnight・strict ``<``）。
    rolling は ``src.features.rolling.build_rolling_features`` に委譲（per-observation latest-K）。
  - **§13.2 metadata stamp**: 全行に ``as_of_datetime`` / ``feature_cutoff_datetime`` /
    ``feature_snapshot_id`` / ``feature_availability_version`` / ``label_generation_version`` /
    ``prediction_timing`` を付与。
  - **CYCLE-2 HIGH #5 (COPY-NOT-RENAME)**: ``kettonum``/``kisyucode``/``chokyosicode``/
    ``ketto3infohansyokunum1``/``ketto3infohansyokunum2`` は残したまま、抽象名 ``horse_id``/
    ``jockey_id``/``trainer_id``/``sire_id``/``bms_id`` を copy で追加（破壊的 rename は
    canonical key・snapshot sort key を壊す）。
  - **HIGH #3**: 構築完了後に ``availability.assert_matrix_columns_registered`` で出力カラム
    全登録を検査し、banned source が alias 名で潜入するのを fail-loud。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import psycopg.errors
from psycopg_pool import ConnectionPool

from src.etl.filters import project_window_filter
from src.features.availability import (
    TARGET_OBS_BANNED_COLUMNS,
    assert_all_entries_allowed,
    assert_features_allowed_for_prediction_timing,
    assert_matrix_columns_registered,
    load_feature_availability,
)
from src.features.rolling import build_rolling_features as _build_rolling_features_impl
from src.features.running_style import estimate_running_style
from src.utils.category_map import MISSING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 3.1 (Plan 03 Task 1): timediff sentinel 集合（builder/rolling 層用）
# label_spec.yaml::se_marker_canonicalization.timediff_sentinels とは別関心事
# （label 層は se_marker 識別用・本定数は rolling source の real parse 用・両者で
#  "0000"/"9999" を含む点は整合）。実データ検証で 0000 は kakuteijyuni='00' と完全一致
# （376件・発走前取消/競走中止のタイム差未確定）・9999 は異常値。両者を NaN 化する
# （T-03.1-07: sentinel が 0.0/999.9 秒として rolling に混入するのを防止）。
# ---------------------------------------------------------------------------
_TIMEDIFF_SENTINELS: frozenset[str] = frozenset({"0000", "9999"})

# ---------------------------------------------------------------------------
# cutoff semantics metadata（§13.2 / HIGH #2・availability.CUTOFF_SEMANTICS と同一不変量）
# ---------------------------------------------------------------------------
CUTOFF_RULE_METADATA: dict[str, str] = {
    "comparison_operator": "strict_less_than",
    "timezone": "Asia/Tokyo",
    "cutoff_definition": "feature_cutoff_datetime = race_date - 1 day (JST midnight)",
    "pit_filter": "history.as_of_datetime < observation.feature_cutoff_datetime",
}

# ---------------------------------------------------------------------------
# 明示カラム定数（SC#2・HIGH #4 taxonomy）
# ---------------------------------------------------------------------------
# 注意（live-DB schema 整合・BUG A fix）: ``race_nkey`` / ``race_date`` /
# ``race_start_datetime`` / ``as_of_datetime`` / ``days_since_prev`` / ``timediff`` /
# ``babacd`` / ``datakubun`` は **DB の実在カラムではない**（``race_nkey`` は予約済み
# canonical key・他は derived）。実在する raw DB カラムのみを SELECT し、derived 列は
# pandas 側で ``_construct_derived_columns`` で構築する（リーク不変量は不変・PIT 意味は
# 変更なし）。``timediff`` / ``babacd`` は Phase 3 gap-closure (03-05・CR-01) で rolling
# 系統から削除済み・Phase 2 ETL 拡張（Phase 3.1: Timediff/Babacd Rolling Restoration）
# で normalized 層に source カラムが追加された後に再登録予定。
#
# history SELECT（normalized.n_uma_race ur JOIN normalized.n_race nr）。
# TARGET_OBS_BANNED_COLUMNS（当日禁止: kyakusitukubun/bataijyu/ninki/odds/sibababacd/
# dirtbabacd/tenkocd/harontimel4）とは**異なる SELECT パス**・同名衝突しない。過去走
# harontimel3/jyuni3c/jyuni4c は HISTORY_ALLOWED_POST_RACE_COLUMNS（rolling source）。
#
# Phase 3.1 (Plan 03 Task 1): timediff と baba3 を raw varchar pass-through で SELECT。
#   - `ur.timediff AS timediff_raw`: raw カラム名 `timediff` は派生名と衝突するため alias
#     `timediff_raw` を付与（Pitfall 3・`_DERIVED_HISTORY_COLUMN_NAMES` により `timediff` は
#     SELECT 対象から除外）。
#   - `nr.sibababacd AS hist_sibababacd` / `nr.dirtbabacd AS hist_dirtbabacd` /
#     `nr.trackcd AS trackcd`: baba3。sibababacd/dirtbabacd は TARGET_OBS_BANNED_COLUMNS と
#     **同名衝突**するため alias (`hist_*`) を付与して L213-215 の disjoint assert を回避
#     （HIGH #4 の intent は「target race 当日行の馬場=禁止」・history の過去走 n_race 馬場は
#     許可。alias で同名衝突を回避しつつ intent を保持・`_HISTORY_SELECT_COLUMNS` には
#     `hist_sibababacd`/`hist_dirtbabacd` が入るため target_obs_banned と disjoint）。
#   - babacd 自体は `_DERIVED_HISTORY_COLUMN_NAMES` にあるため SELECT せず、
#     `_construct_derived_columns` で trackcd 第1桁分岐 + sibababacd/dirtbabacd 値から派生。
_HISTORY_DB_SELECT_COLUMNS: tuple[str, ...] = (
    "ur.kettonum AS kettonum",
    "ur.year AS year",
    "ur.jyocd AS jyocd",
    "ur.kaiji AS kaiji",
    "ur.nichiji AS nichiji",
    "ur.racenum AS racenum",
    "nr.race_date AS race_date",
    "nr.race_start_datetime AS race_start_datetime",
    "ur.kakuteijyuni AS kakuteijyuni",
    "ur.harontimel3 AS harontimel3",
    "ur.jyuni3c AS jyuni3c",
    "ur.jyuni4c AS jyuni4c",
    "ur.jyuni1c AS jyuni1c",
    "nr.kyori AS kyori",
    # Phase 3.1: raw varchar pass-through（alias で派生名衝突/TARGET_OBS_BANNED 同名衝突を回避）
    "ur.timediff AS timediff_raw",
    "nr.sibababacd AS hist_sibababacd",
    "nr.dirtbabacd AS hist_dirtbabacd",
    "nr.trackcd AS trackcd",
    # Phase 9: speed_figure.py が history の走破タイム（0.1秒単位・real）を消費。
    # ur.time は derived でなく raw DB カラム・TARGET_OBS_BANNED_COLUMNS とは
    # disjoint（L320-322 assert で機械保証・T-09-12 mitigate）。
    "ur.time AS time",
)
_HISTORY_SELECT_COLUMN_NAMES: tuple[str, ...] = tuple(
    c.split(" AS ")[1] for c in _HISTORY_DB_SELECT_COLUMNS
)

# observations SELECT（normalized.n_uma_race ur JOIN normalized.n_race nr JOIN public.n_uma）。
_OBS_DB_SELECT_COLUMNS: tuple[str, ...] = (
    "ur.kettonum AS kettonum",
    "ur.year AS year",
    "ur.jyocd AS jyocd",
    "ur.kaiji AS kaiji",
    "ur.nichiji AS nichiji",
    "ur.racenum AS racenum",
    "nr.race_date AS race_date",
    "nr.race_start_datetime AS race_start_datetime",
    "ur.umaban AS umaban",
    "ur.wakuban AS wakuban",
    "ur.barei AS barei",
    "ur.sexcd AS sexcd",
    "ur.futan AS futan",
    "ur.kisyucode AS kisyucode",
    "ur.chokyosicode AS chokyosicode",
    "nr.class_code_normalized AS class_code_normalized",
    # Phase 9.1 (D-09.1-05): target race の trackcd/kyori（same_surface/same_distance_bucket
    # 計算用の中間値・rolling.build_rolling_features が observations から参照）。
    # feature_matrix には出力しない（Step 6b で drop・snapshot 構成変更を speed profile
    # 特徴量のみに抑制）。registry には race_context (both_allowed) として既登録だが
    # v1.0/v1.1 でも feature として出力されていない（本 Phase も中間値のみ）。
    "nr.trackcd AS trackcd",
    "nr.kyori AS kyori",
)
_OBS_SELECT_COLUMN_NAMES: tuple[str, ...] = tuple(
    c.split(" AS ")[1] for c in _OBS_DB_SELECT_COLUMNS
)

# 後方互換: 既存テスト（test_banned_columns_not_selected 等）が参照する公開定数名。
# ``_HISTORY_SELECT_COLUMNS`` は HIGH #4 taxonomy 検査の対象（target_obs_banned と disjoint）。
# 実 DB カラム名の set として expose する（derived 列 race_nkey/as_of_datetime 等は含まない）。
_DERIVED_HISTORY_COLUMN_NAMES = frozenset({
    "race_nkey", "as_of_datetime", "days_since_prev", "timediff", "babacd", "datakubun",
})
_HISTORY_SELECT_COLUMNS: frozenset[str] = frozenset(
    c for c in _HISTORY_SELECT_COLUMN_NAMES if c not in _DERIVED_HISTORY_COLUMN_NAMES
)
_OBS_SELECT_COLUMNS: tuple[str, ...] = _OBS_SELECT_COLUMN_NAMES

# 3代血統（public.n_uma から取得）
_BLOODLINE_COLUMNS: tuple[str, ...] = (
    "kettonum",
    "ketto3infohansyokunum1",  # sire_id
    "ketto3infohansyokunum2",  # bms_id
)


def make_race_nkey(
    year: pd.Series,
    jyocd: pd.Series,
    kaiji: pd.Series,
    nichiji: pd.Series,
    racenum: pd.Series,
) -> pd.Series:
    """複合レースキー ``race_nkey`` を pandas で決定論的に構築する（BUG A fix）。

    ``race_nkey`` は予約済み canonical key（availability._RESERVED_NON_FEATURE_COLUMNS）
    だが **DB の実在カラムではない**（information_schema で確認済）。複合キー
    (year, jyocd, kaiji, nichiji, racenum) を零埋連結した固定幅文字列
    ``YYYYJJJKK< nichiji>NN`` で構築する。同一レースの全馬で同一値・観測と
    過去走で同一構成（両者は race_nkey で group/join される・rolling.py 参照）。

    リーク不変量: 本関数は純粋な key formatting のみ行い、PIT 意味（cutoff / as_of）
    には一切影響しない。
    """
    return (
        year.astype(str).str.zfill(4)
        + jyocd.astype(str).str.zfill(2)
        + kaiji.astype(str).str.zfill(2)
        + nichiji.astype(str).str.zfill(2)
        + racenum.astype(str).str.zfill(2)
    )


def _construct_derived_columns(
    df: pd.DataFrame, *, with_days_since_prev: bool = False
) -> pd.DataFrame:
    """DB に存在しない derived 列を pandas で構築する（observations / history 共通）。

    - ``race_nkey``: ``make_race_nkey(year, jyocd, kaiji, nichiji, racenum)``。
    - ``as_of_datetime``: ``race_start_datetime``（=レース発走時刻・PIT 基準時刻）。
    - ``days_since_prev``: 同一 kettonum 内の前走 race_date からの日数差（rolling source）。
      **history のみ**意味を持つ（observations では構築しない・matrix に出力しない）。
      ``with_days_since_prev=True`` のときのみ構築。

    リーク不変量: 全て過去情報のみから導出。cutoff / PIT filter は別途 rolling 側で
    strict ``<`` で適用される。
    """
    result = df.copy()
    composite_present = all(
        c in result.columns for c in ("year", "jyocd", "kaiji", "nichiji", "racenum")
    )
    if composite_present and "race_nkey" not in result.columns:
        result["race_nkey"] = make_race_nkey(
            result["year"],
            result["jyocd"],
            result["kaiji"],
            result["nichiji"],
            result["racenum"],
        )
    if "race_start_datetime" in result.columns and "as_of_datetime" not in result.columns:
        result["as_of_datetime"] = pd.to_datetime(result["race_start_datetime"])
    # days_since_prev: kettonum 毎に race_date 昇順で diff(days)。history rolling source 専用。
    # WR-02 (03-REVIEW) docstring 明記: 本値は「全 history 上の前走（window 外含む）」からの
    # 日数であり、rolling window 内で再計算されるものではない。rolling 側で latest 軸は
    # window 内の最新1件を取るが、その最新走の days_since_prev 値は window 外の前走を基準に
    # している場合がある（リークではなく定義上の挙動・PIT filter 適用後も各 history 行の
    # 「前走日数」として意味は保つ）。
    # WR-09 (03-REVIEW): index の重複リスクを排除するため reset_index(drop=True) してから
    # 計算し、元の index に整列し直す（壊れやすい .loc[ordered.index] lookup を廃止）。
    if (
        with_days_since_prev
        and "kettonum" in result.columns
        and "race_date" in result.columns
        and "days_since_prev" not in result.columns
    ):
        original_index = result.index
        result = result.reset_index(drop=True)
        result["_rd_dt"] = pd.to_datetime(result["race_date"])
        ordered = result.sort_values(["kettonum", "race_date"])
        ordered["days_since_prev"] = (
            ordered.groupby("kettonum")["_rd_dt"].diff().dt.total_seconds() / 86400.0
        )
        # sort_index で元の result 順序に戻す（reset_index 済みなので 0..N-1）
        result["days_since_prev"] = ordered.sort_index()["days_since_prev"].values
        result = result.drop(columns=["_rd_dt"])
        result.index = original_index

    # Phase 3.1 (Plan 03 Task 1): timediff parse (varchar4 → real秒・sentinel 0000/9999 → NaN)
    # raw format: "sNNN"（s="+"/"-"、NNN=3桁・NNN/10 秒）・例 "+001"→0.1秒・"-020"→-2.0秒。
    # sentinel 0000/9999 は NaN 化（T-03.1-07・D-03・Pitfall 1）。vector 化 idiom。
    if "timediff_raw" in result.columns and "timediff" not in result.columns:
        raw_td = result["timediff_raw"].astype(str)
        is_sentinel = raw_td.isin(_TIMEDIFF_SENTINELS)
        sign = raw_td.str[0]
        digits = pd.to_numeric(raw_td.str.slice(1, 4), errors="coerce")
        signed = digits.where(sign != "-", -digits)
        result["timediff"] = (signed / 10.0).where(~is_sentinel, np.nan)

    # Phase 3.1 (Plan 03 Task 1): babacd 派生 — trackcd 数値範囲で芝/ダート/障害を判定し、
    # 対応する馬場状態コードを babacd 列に格納。判定不能/欠損は __MISSING__ sentinel
    # （silent NaN fill 禁止）。JRA-VAN JV-Data 仕様に準拠（実DB検証 + 公式資料で確定）:
    #   - trackcd 10-22 → 平地芝     → babacd = hist_sibababacd（芝馬場状態）
    #   - trackcd 23-25 → 平地ダート → babacd = hist_dirtbabacd（ダート馬場状態）
    #   - trackcd 51-59 → 障害（芝） → babacd = hist_sibababacd（障害コースは芝馬場）
    #   - それ以外/欠損 → __MISSING__
    # 馬場状態コード '0' は JRA-VAN JV-Data で「未設定/初期値」（有効値は '1'=良, '2'=稍重,
    # '3'=重, '4'=不良・developer.jra-van.jp/t/topic/58・JV-Data コード表）。実DBでも整合:
    # ダート(trackcd23-25)レースの sibababacd は '0'(未設定)が99%・芝レースの sibababacd は
    # '1'(良)が最多。よって '0' は除外（空/NaN/None と同様・__MISSING__）。
    # trackcd の芝/ダート判定は旧実装（先頭桁 1/2=芝, 5=ダート）が実態と逆転（'2x' の大半=
    # 23/24 はダート, '5x' は障害芝）していたのが真の data loss 真因。旧実装が '2x'（ダート）
    # を芝扱いして sibababacd '0'(未設定) → __MISSING__ 化していたのを、数値範囲判定で
    # dirtbabacd を見るように精密化して解消（'0' 除外 intent 自体は正しかった）。
    if (
        "trackcd" in result.columns
        and "hist_sibababacd" in result.columns
        and "hist_dirtbabacd" in result.columns
        and "babacd" not in result.columns
    ):
        tc_num = pd.to_numeric(
            result["trackcd"].astype(str).str.strip(), errors="coerce"
        )
        turf_mask = tc_num.between(10, 22)  # 平地芝（左回り10-19 + 右回り20-22）
        dirt_mask = tc_num.between(23, 25)  # 平地ダート
        obstacle_mask = tc_num.between(51, 59)  # 障害（芝馬場）
        babacd = pd.Series([MISSING] * len(result), dtype=object, index=result.index)
        # 芝 + 障害 → sibababacd（'0'/空/NaN/None は未設定なので __MISSING__）
        siba_pick = turf_mask | obstacle_mask
        siba_val = result["hist_sibababacd"].astype(str).str.strip()
        siba_valid = (
            siba_pick
            & siba_val.notna()
            & (siba_val != "")
            & (siba_val != "nan")
            & (siba_val != "None")
            & (siba_val != "0")
        )
        babacd = babacd.where(~siba_valid, siba_val)
        # ダート → dirtbabacd（'0'/空/NaN/None は未設定なので __MISSING__）
        dirt_val = result["hist_dirtbabacd"].astype(str).str.strip()
        dirt_valid = (
            dirt_mask
            & dirt_val.notna()
            & (dirt_val != "")
            & (dirt_val != "nan")
            & (dirt_val != "None")
            & (dirt_val != "0")
        )
        babacd = babacd.where(~dirt_valid, dirt_val)
        result["babacd"] = babacd
    return result

# ---------------------------------------------------------------------------
# 起動時不変量: _HISTORY_SELECT_COLUMNS と TARGET_OBS_BANNED_COLUMNS は disjoint（HIGH #4）
# 両者は別 SELECT パスなので同名衝突しないが、誤って禁止カラムを history に混入するのを
# 機械的に防止する。sibababacd/dirtbabacd（target_obs_banned・n_race の当日馬場）は
# normalized 層 history SELECT には現れない（本検査で機械的に保証）。
# ---------------------------------------------------------------------------
assert TARGET_OBS_BANNED_COLUMNS.isdisjoint(_HISTORY_SELECT_COLUMNS), (
    "_HISTORY_SELECT_COLUMNS に TARGET_OBS_BANNED_COLUMNS と衝突するカラムがある (HIGH #4)"
)


def build_rolling_features(observations: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """``src.features.rolling.build_rolling_features`` への薄い転送（テスト契約）。

    ``test_pit_cutoff.py`` が builder 経由で rolling を呼び出すための薄ラッパ。
    入力を rolling 実装に渡す前に PIT join 用の sortedness を担保する（``sort_values``
    を呼出・regression guard・HIGH #1/#3）。

    WR-06 (03-REVIEW): history に ``as_of_datetime`` 列が無い場合、``sort_values`` が
    ``KeyError`` を raise するのを ``ValueError`` で wrap する（PIT filter 適用不可を
    明示化・将来 refactor での silent leak 防止・呼出側で例外型を揃える）。
    """
    obs_sorted = observations.sort_values("feature_cutoff_datetime").reset_index(drop=True)
    if len(history) > 0:
        if "as_of_datetime" not in history.columns:
            raise ValueError(
                "history に as_of_datetime 列が無い・sort_values できない "
                "(WR-06・PIT filter 適用不可・将来 refactor での silent leak 防止)"
            )
        hist_sorted = history.sort_values("as_of_datetime").reset_index(drop=True)
    else:
        hist_sorted = history
    return _build_rolling_features_impl(obs_sorted, hist_sorted)


def build_feature_matrix(
    read_pool: ConnectionPool,
    *,
    snapshot_id: str,
    label_version: str,
    fa_version: str,
    train_period: tuple[str, str] = ("2016-07-01", "2023-12-31"),
    validation_period: tuple[str, str] = ("2024-01-01", "2024-12-31"),
) -> dict[str, Any]:
    """readonly pool から PIT-correct feature matrix を構築する（公開 API）。

    Pipeline
    --------
    1. availability registry load + assert_all_entries_allowed（Plan 03-01 loader）。
    2. readonly SELECT で observations / history / race_context / bloodline を取得
       （明示カラム・``PROJECT_WINDOW_FILTER`` / ``project_window_filter(alias)``
       で JRA フィルタ）。
    3. **cutoff 計算（D-06・HIGH #2）**: ``feature_cutoff_datetime = race_date - 1 day``
       （``pd.Timedelta(days=1)``・JST midnight・strict ``<``）。
       ``as_of_datetime = race_start_datetime``。
    4. 静的属性 transform（``normalize.py:_transform_uma_race_df`` のキャストイディオム）。
    4b. **CYCLE-2 HIGH #5 (COPY-NOT-RENAME)**: 抽象名 ``horse_id``/``jockey_id``/``trainer_id``/
        ``sire_id``/``bms_id`` を copy で追加（``kettonum``/``kisyucode`` 等の元列は保持）。
    5. rolling features 統合（``build_rolling_features`` 経由・per-observation latest-K・HIGH #1）。
    5b. **Step 5b: speed_figure 計算**（Phase 9・``compute_speed_figure_for_history``・history に
        ``speed_figure`` 列を copy-not-rename で追加）。PIT 保証は ``speed_figure.py`` 側の
        ``_pit_cutoff_prefilter`` (strict ``<``) で適用（rolling と対称）。Step 5 rolling が
        ``history["speed_figure"]`` を numeric 系統として自動集約し ``rolling_speed_figure_*``
        6 feature を出力（P02 拡張済み）。**REVIEW H1-c**: Step 5b の直前に ``feature_matrix["obs_id"]``
        を早期構築（Step 6 で再利用・Step 6b で drop・P01 API 契約充足）。
    6. 推定脚質（``estimate_running_style``・過去走 jyuni3c/jyuni4c のみ・**cutoff 以前の過去走のみ**
       （rolling と同一 PIT pre-filter・``as_of_datetime < feature_cutoff_datetime``・strict ``<``）・
       当日不使用・D-05・WR-01 fix）。
    7. **§13.2 metadata stamp**: 全行に ``feature_snapshot_id`` / ``feature_availability_version``
       / ``label_generation_version`` / ``prediction_timing`` の定数列を付与。
    8. canonical key 検証: ``(race_nkey, kettonum)`` 一意性。
    9. **HIGH #3**: ``assert_matrix_columns_registered`` で出力カラム全登録を fail-loud 検査。

    Parameters
    ----------
    read_pool : ConnectionPool
        ``make_pool(role="readonly")`` の pool（search_path: public,normalized,label）。
    snapshot_id : str
        feature snapshot identifier（§12.4 metadata）。
    label_version : str
        label generation version（§12.4 metadata）。
    fa_version : str
        feature_availability.yaml schema_version（§12.4 metadata）。
    train_period : tuple[str, str]
        学習窓（``train_period`` は feature 構築自体には使わない・全期間1枚 D-09・呼出側で
        snapshot を train/val/test に分割する際の参照用に保持）。
    validation_period : tuple[str, str]
        検証窓（同上・D-09 全期間1枚前提）。

    Returns
    -------
    dict[str, Any]
        ``{"feature_matrix": pd.DataFrame, "snapshot_id": snapshot_id,
        "raw_touched": False, "feature_count": int, "row_count": int}``。

    Raises
    ------
    ValueError
        availability registry 違反・出力カラム未登録・canonical key 一意性違反。
    """
    # --- Step 1: availability registry load + allowlist 強制（Plan 03-01） ---
    spec = load_feature_availability()
    assert_all_entries_allowed(spec)
    # WR-04 (03-REVIEW): prediction_timing="1A" で許可される available_from_timing 集合に
    # 全 feature が属することを検査（timing×cutoff 整合性の fail-loud・CR-03 wontfix 制約下で
    # 1-A = 出馬表・馬番・枠番確定後 なので futan/jockey_id/umaban/wakuban は許可）。
    assert_features_allowed_for_prediction_timing(spec, "1A")

    # --- Step 2: readonly SELECT（明示カラム・JRA フィルタ・Pitfall 1） ---
    feature_matrix = _fetch_feature_sources(read_pool)

    # WR-02 (Phase 3.1 advisory hardening): feature source fetch が空結果を返した場合
    # （DB 例外/0行結果/silent empty）をチョークポイントで fail-loud 検知（D-04 採択・
    # advisory hardening todo WR-02）。`_fetch_feature_sources` 内の except→空 DF は維持
    # しつつ、本呼出点で空を検知して RuntimeError（silent data loss 回避）。
    if len(feature_matrix) == 0:
        raise RuntimeError(
            "feature source fetch が空結果を返した・DB例外/0行結果の silent empty を検知 "
            "(WR-02 fail-loud・advisory hardening)"
        )

    # --- Step 3: cutoff 計算（D-06・HIGH #2: race_date - 1 day・JST midnight・strict <） ---
    # WR-05 (03-REVIEW) 明記: feature_cutoff_datetime / as_of_datetime は naive datetime
    # （tz_localize 未適用）。CUTOFF_SEMANTICS["timezone"]="Asia/Tokyo" は JRA データが全て
    # JST であり same-day 同一 JST midnight 境界で運用される前提の宣言。実データは全て JST
    # 発走時刻であり tz 情報を持たないため、naive 同士の比較で日付境界が明確（race_date は
    # date 型・発走時刻も JST 固定）。将来マルチタイムゾーンデータが混入する場合は
    # .dt.tz_localize("Asia/Tokyo") の適用が必要（advisory・現状は実害軽微のため naive 運用）。
    feature_matrix["feature_cutoff_datetime"] = (
        pd.to_datetime(feature_matrix["race_date"]) - pd.Timedelta(days=1)
    )
    feature_matrix["as_of_datetime"] = pd.to_datetime(feature_matrix["race_start_datetime"])

    # --- Step 4: 静的属性 transform（キャストイディオム・normalize.py analog） ---
    feature_matrix = _cast_static_columns(feature_matrix)

    # --- Step 4b: CYCLE-2 HIGH #5 COPY-NOT-RENAME（抽象名 alias 追加・元列は保持） ---
    # 破壊的 rename は canonical key (race_nkey, kettonum)・snapshot sort key を壊すため
    # copy で併存させる。horse_id は Plan 03-04 _CATEGORY_COLUMNS の drop 対象・kettonum は保持。
    feature_matrix["horse_id"] = feature_matrix["kettonum"]
    if "kisyucode" in feature_matrix.columns:
        feature_matrix["jockey_id"] = feature_matrix["kisyucode"]
    if "chokyosicode" in feature_matrix.columns:
        feature_matrix["trainer_id"] = feature_matrix["chokyosicode"]
    if "ketto3infohansyokunum1" in feature_matrix.columns:
        feature_matrix["sire_id"] = feature_matrix["ketto3infohansyokunum1"]
    if "ketto3infohansyokunum2" in feature_matrix.columns:
        feature_matrix["bms_id"] = feature_matrix["ketto3infohansyokunum2"]

    # --- Step 5: rolling features 統合（per-observation latest-K・HIGH #1・rolling 側で完結） ---
    # CR-01 (03-REVIEW): rolling 統合は位置ベース(axis=1) concat でなく canonical key で
    # merge する。build_rolling_features は内部で sort_values("feature_cutoff_datetime")
    # した上で rolling を計算するため、返却 DataFrame の行順が feature_matrix と一致する保証は
    # 無い。位置 concat は silent に別の observation に rolling 値を割当ててしまう row-
    # misalignment バグの原因。race_nkey/kettonum（存在時）または obs_id で明示 merge する。
    history = _fetch_history(read_pool)
    # WR-01 (Phase 3.1 code review): history fetch が空結果（DB例外/0行・_fetch_history の
    # 接続例外フォールバック）をチョークポイントで fail-loud 検知。obs 側は Step2 WR-02 で
    # 検知するが、history 側が空だと後続 Step5/6 が ``if len(history) > 0`` でスキップされ、
    # 全馬が「新馬扱い」（rolling_* が全 __MISSING__）の silent data loss が manifest 書出
    # まで進む。全期間 SELECT が 0 行になるのは DB 一時障害/0行結果のみ（JRA データで過去走
    # 0件は非現実）のため、空は即 fail とする（obs 側 WR-02 と対称な二重防御）。
    if len(history) == 0:
        raise RuntimeError(
            "history fetch が空結果を返した・DB例外/0行結果の silent empty を検知 "
            "(WR-01 fail-loud・advisory hardening・全馬新馬扱いの silent data loss 回避)"
        )

    # --- REVIEW H1-c: obs_id 早期構築（Phase 9・Step 5b 前に feature_matrix に obs_id が必要） ---
    # 旧来 obs_id は Step 6 推定脚質（L505-517）で初出していたが・Step 5b speed_figure 計算が
    # P01 compute_speed_figure_for_history(history, observations=feature_matrix) API 契約で
    # observations が obs_id を持つことを期待する（P01 PLAN L114・rolling.py L207-215 と対称）。
    # よって Step 5b の直前で既存 idiom（Step 6 L505-517 と完全同一ロジック）により
    # feature_matrix["obs_id"] を早期構築する。Step 6 は "obs_id" in columns で skip して再利用
    # （再生成でない・回帰なし）・Step 6b（L560-564）で引き続き drop される（PyArrow 直列化不能・
    # 契約不変）。本早期構築がないと P01 が observations から obs_id を取れず cross-observation
    # leak を起こす（T-09-27 mitigate）。
    if "obs_id" not in feature_matrix.columns and len(feature_matrix) > 0:
        if "race_nkey" in feature_matrix.columns:
            feature_matrix["obs_id"] = list(zip(
                feature_matrix["race_nkey"].tolist(),
                feature_matrix["kettonum"].tolist(),
                strict=False,
            ))
        else:
            feature_matrix["obs_id"] = list(zip(
                feature_matrix.index.tolist(),
                feature_matrix["kettonum"].tolist(),
                strict=False,
            ))

    # --- Step 5b: speed_figure 計算（Phase 9・Beyer 型・history に speed_figure 列を付与） ---
    # history に time/trackcd/jyocd/kyori/race_date/as_of_datetime が揃った段階で
    # src.features.speed_figure を呼出。PIT 保証は speed_figure.py 内の _pit_cutoff_prefilter
    # （strict < feature_cutoff_datetime・availability.CUTOFF_SEMANTICS と同一不変量）で適用
    # （rolling と対称）。copy-not-rename: history に "speed_figure" 列を追加（既存列は破壊しない・
    # HIGH #5 踏襲・T-09-10 mitigate）。available_at = race_date を付与（rolling の PIT 集約で使用）。
    # REVIEW H1-c: feature_matrix を observations として渡す（obs_id は上記で早期構築済み）。
    # 位置は CR-01 merge（Step 5 rolling）の前・build_rolling_features が history["speed_figure"]
    # を numeric 系統として自動集約し rolling_speed_figure_* 6 feature を出力（P02 拡張済み）。
    #
    # **CYCLE-2 HIGH-C2-3 (10-REVIEWS.md L108-114, L219-226, L297)**: Step 5b の呼出で
    # ``history = compute_speed_figure_for_history(history, observations=feature_matrix)`` が
    # history を obs_id 展開済み target-cutoff-contaminated フレームに変換する（各行の par/variant/
    # speed_figure が target obs の feature_cutoff_datetime に依存・speed_figure.py L655-657）。
    # Step 5c compute_field_strength_profile がこれを消費すると PLAN 01 の source-race opponent
    # 流用で (source, target] 区間の opponent レースが値レベルで混入する。よって Step 5b の **前** に
    # raw_history = history.copy() で obs_id 未展開・speed_figure 未付与の生 history を保存し・
    # Step 5c は history でなく raw_history を第1引数に渡す（PLAN 01 C2-1 full-pipeline source-as-of
    # 再計算を適用するための入力）。
    raw_history = history.copy()  # CYCLE-2 HIGH-C2-3: Step 5b 前・obs_id 未展開
    import time as _time

    from src.features.speed_figure import compute_speed_figure_for_history
    _t_5b = _time.time()
    history = compute_speed_figure_for_history(history, observations=feature_matrix)
    logger.info(
        "build_feature_matrix: Step5b speed_figure %.1fs (history rows=%d)",
        _time.time() - _t_5b, len(history),
    )

    # --- Step 5c: 相手強度 field_strength profile 計算（D-06 第1段階・Phase 10 PLAN 01・新） ---
    # raw_history（obs_id 未展開・speed_figure 未付与の生 history・CYCLE-2 HIGH-C2-3）を
    # compute_field_strength_profile に渡す。同関数は raw_history に合成 observation
    # (SOURCE_ASOF_<race_nkey>_<kettonum>・feature_cutoff_datetime=source_race.available_at) で
    # compute_speed_figure_for_history を再実行し full par+variant+speed_figure pipeline を
    # source-as-of で再計算する（PLAN 01 CYCLE-2 HIGH-C2-1 値レベル PIT 保証）。得られた
    # field_strength profile 8値を obs_id 展開済み history に race_nkey + kettonum + race_date で
    # left-merge（copy-not-rename・HIGH#5・profile は source-as-of 再計算由来で target cutoff 非依存）。
    # Step 5（build_rolling_features）は profile が history に揃った後で rolling する（A6 構成変更）。
    from src.features.field_strength import compute_field_strength_profile
    _t_5c = _time.time()
    field_strength_profile = compute_field_strength_profile(raw_history, observations=feature_matrix)
    # profile 8値（field_strength_mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）を
    # raw_history に付与した戻り値から取り出し・obs_id 展開済み history に left-merge。
    # merge key は race_nkey + kettonum + race_date（date 型・source race を一意に特定）。
    # race_nkey + kettonum だけだとテストデータ等で race_nkey が衝突した際に history が膨らむため・
    # source race の race_date（両フレーム共通・date 型で一致）で一意に特定。
    # history 側の as_of_datetime（datetime・12:00 含む）と profile 側の available_at
    # （datetime・00:00 由来）は時刻表現が異なるため race_date（date）で一致させる。
    _fs_profile_cols = [
        c for c in field_strength_profile.columns
        if c.startswith("field_strength_")
    ]
    if len(_fs_profile_cols) > 0 and len(history) > 0 and "race_date" in history.columns:
        _profile_merge = field_strength_profile[
            ["race_nkey", "kettonum", "race_date"] + _fs_profile_cols
        ]
        # CR-02 (10-08 gap-closure): merge 前に race_date を pd.to_datetime で双方向正規化する。
        # history 側は Step5b compute_speed_figure_for_history を経由した obs_id 展開済みフレームで
        # race_date の dtype が実装依存（datetime.date object / datetime64 等）・profile 側は
        # raw_history.assign(available_at=pd.to_datetime(race_date)) の copy で race_date 自体は入力の型を
        # 保持する。両者が同じ raw_history 由来でも dtype 不一致で silent NaN merge になるリスクを
        # 構造的に排除する（FEAT-02 21 feature 全行 sentinel 化の silent data loss 封印・core value 違反）。
        history["race_date"] = pd.to_datetime(history["race_date"])
        _profile_merge = _profile_merge.copy()
        _profile_merge["race_date"] = pd.to_datetime(_profile_merge["race_date"])
        history = history.merge(
            _profile_merge,
            on=["race_nkey", "kettonum", "race_date"],
            how="left",
            suffixes=("", "_fs_profile"),
        )
        # suffix 衝突で _fs_profile 付いた列があれば元列名に統一（copy-not-rename・profile が勝る）
        for col in list(_fs_profile_cols):
            if f"{col}_fs_profile" in history.columns and col not in history.columns:
                history[col] = history[f"{col}_fs_profile"]
                history = history.drop(columns=[f"{col}_fs_profile"])
        # CR-02 (10-08 gap-closure): merge 後に field_strength_mean の notna 率を fail-loud 検査する。
        # starter_mask（kakuteijyuni > 0）上で field_strength_mean が 0.5 未満しか JOIN できていない場合は
        # silent NaN merge（dtype mismatch / profile 欠損等）とみなし RuntimeError を raise する
        # （FEAT-02 21 feature 全行 sentinel 化の silent data loss を検知・core value「リーク防止」の鏡像）。
        if "field_strength_mean" in history.columns and len(history) > 0:
            starter_mask = history["kakuteijyuni"].fillna(0) > 0
            if starter_mask.any():
                joined_ratio = float(
                    history.loc[starter_mask, "field_strength_mean"].notna().mean()
                )
                if joined_ratio < 0.5:
                    raise RuntimeError(
                        f"Step5c profile merge で field_strength_mean が {joined_ratio:.1%} しか "
                        f"JOIN できず (silent data loss・dtype mismatch / profile 欠損の疑い・"
                        "core value「リーク防止」の鏡像「silent fallback 禁止」違反・CR-02 fail-loud)"
                    )
    logger.info(
        "build_feature_matrix: Step5c field_strength profile %.1fs (profile rows=%d)",
        _time.time() - _t_5c,
        len(field_strength_profile),
    )

    if len(history) > 0 and len(feature_matrix) > 0:
        _t_5 = _time.time()
        rolling_df = build_rolling_features(feature_matrix, history)
        logger.info("build_feature_matrix: Step5 rolling %.1fs", _time.time() - _t_5)
        rolling_cols = [
            c for c in rolling_df.columns if c.startswith("rolling_")
        ]
        if "race_nkey" in rolling_df.columns and "kettonum" in rolling_df.columns:
            merge_keys = ["race_nkey", "kettonum"]
        elif "obs_id" in rolling_df.columns:
            merge_keys = ["obs_id"]
        else:
            # フォールバック: rolling_df が key 列を全く持たない（rolling 実装契約違反）。
            # 位置 concat は row-misalignment を起こすため認めない・fail-loud。
            raise RuntimeError(
                "rolling_df に merge key (race_nkey/kettonum または obs_id) が無い・"
                "row-misalignment を防ぐ merge が実行できない (CR-01・rolling 実装契約違反)"
            )
        feature_matrix = feature_matrix.merge(
            rolling_df[merge_keys + rolling_cols], on=merge_keys, how="left"
        )

    # --- Step 6: 推定脚質（過去走 jyuni3c/jyuni4c のみ・当日不使用・D-05） ---
    # WR-01 (03-05 gap-closure): rolling と同一の PIT pre-filter
    # （history.as_of_datetime < obs.feature_cutoff_datetime・per-observation・strict <）
    # を groupby 前に適用し、cutoff 後の過去走が推定脚質に混入しないようにする。
    # WR-03 (03-REVIEW): groupby を kettonum 単位でなく obs_id 単位に変更
    # （rolling と対称・同一 horse が複数 observation に現れる場合の cross-obs leak 再発防止）。
    # registry は strict `< cutoff` を宣言（feature_availability.yaml L355-361）し、本実装が一致。
    if len(history) > 0 and "kettonum" in history.columns and len(feature_matrix) > 0:
        # obs_id 構築（rolling と同一 idiom・CR-01 merge_keys 整合）。
        # 既に rolling merge で obs_id 列が追加されていれば再利用・無ければ生成。
        if "obs_id" not in feature_matrix.columns:
            if "race_nkey" in feature_matrix.columns:
                feature_matrix["obs_id"] = list(zip(
                    feature_matrix["race_nkey"].tolist(),
                    feature_matrix["kettonum"].tolist(),
                    strict=False,
                ))
            else:
                feature_matrix["obs_id"] = list(zip(
                    feature_matrix.index.tolist(),
                    feature_matrix["kettonum"].tolist(),
                    strict=False,
                ))
        obs_keys_style = feature_matrix[
            ["obs_id", "kettonum", "feature_cutoff_datetime"]
        ].copy()
        expanded_style = history.merge(
            obs_keys_style, on="kettonum", how="inner", suffixes=("", "_obs")
        )
        if "feature_cutoff_datetime_obs" in expanded_style.columns:
            expanded_style["feature_cutoff_datetime"] = expanded_style[
                "feature_cutoff_datetime_obs"
            ]
            expanded_style = expanded_style.drop(columns=["feature_cutoff_datetime_obs"])
        if "obs_id_obs" in expanded_style.columns:
            expanded_style["obs_id"] = expanded_style["obs_id_obs"]
            expanded_style = expanded_style.drop(columns=["obs_id_obs"])
        # PIT pre-filter: cutoff 以前の過去走のみ（rolling.py L193-195 と同一の strict < idiom）
        # WR-01' (Phase 3.1 advisory hardening): as_of_datetime 列が無い場合は silent に
        # no-filter でフォールバックせず ValueError で fail-loud（将来 refactor での
        # silent leak 防止・advisory hardening todo WR-01'）。
        if "as_of_datetime" not in expanded_style.columns:
            raise ValueError(
                "history に as_of_datetime 列が無い・PIT filter を適用できない "
                "(WR-01' fail-loud・将来 refactor での silent leak 防止)"
            )
        pit_filtered_style = expanded_style[
            expanded_style["as_of_datetime"]
            < expanded_style["feature_cutoff_datetime"]
        ].copy()
        style_map: dict[Any, str] = {}
        # WR-03: obs_id 単位で groupby（kettonum でない・cross-obs leak 回避）
        for obs_id_key, group in pit_filtered_style.groupby("obs_id"):
            rows = (
                group[["jyuni3c", "jyuni4c"]].to_dict(orient="records")
                if len(group) > 0
                else []
            )
            style_map[obs_id_key] = estimate_running_style(rows)
        feature_matrix["estimated_running_style"] = (
            feature_matrix["obs_id"].map(style_map).fillna("__MISSING__")
        )
    else:
        feature_matrix["estimated_running_style"] = "__MISSING__"

    # --- Step 6c: レース内相対特徴量（FEAT-03・target-only・Phase 10 PLAN 03・D-07・新） ---
    # Step 6b の obs_id drop の前・race_nkey が使える段階で計算（PLAN 04 PLAN action (1) Step 7）。
    # compute_race_relative_features は feature_matrix に copy-not-rename で6列を追加:
    #   speed_index_rank_{mean5,best2_mean5,median5}・gap_to_top・gap_to_3rd・
    #   field_strength_adjusted_rank
    # 入力: rolling_speed_figure_mean_5/best2_mean_5/median_5（Phase 9.1・target 経路）と
    #   rolling_field_strength_mean_mean_5（PLAN 02・source-asof 経由・同一 horse-level par）。
    # target-only（D-07）・race_nkey group-by + transform で competition ranking を算出
    # （feature_cutoff_datetime 時点で確定した値のみ・当日結果不使用・SAFE-01）。
    from src.features.race_relative import compute_race_relative_features
    if len(feature_matrix) > 0:
        feature_matrix = compute_race_relative_features(feature_matrix)
        # FEAT-03 6列（rolling_ prefix 無し・PAT§ snapshot.py L343-361）を float64 に強制 cast。
        # rolling_speed_figure_mean_5 等が object dtype（MISSING sentinel 文字列）の場合・
        # rank/gap が object dtype で伝播し Parquet 書出し/数値演算で TypeError になる。
        # sentinel 文字列は pd.to_numeric(errors="coerce") で NaN になり D-09 欠損馬 NaN 保持と整合。
        # rank 列は整数値だが間欠欠損 (NaN) を許容するため Float64 (nullable float) で保持。
        _FEAT03_COLS = [
            "speed_index_rank_mean5",
            "speed_index_rank_best2_mean5",
            "speed_index_rank_median5",
            "gap_to_top",
            "gap_to_3rd",
            "field_strength_adjusted_rank",
        ]
        for _feat3_col in _FEAT03_COLS:
            if _feat3_col in feature_matrix.columns:
                feature_matrix[_feat3_col] = pd.to_numeric(
                    feature_matrix[_feat3_col], errors="coerce"
                ).astype("Float64")

    # --- Step 6d: 中間値 drop（Phase 10 PLAN 04 Step 7b・T-10-16 mitigate） ---
    # field_strength profile 生値（field_strength_mean 等・rolling_ prefix 無し）は
    # rolling_field_strength_* の計算用中間値・feature_matrix に出力しない（registry parity 違反回避）。
    # D-11 raw rank/profile と別保持: rolling_field_strength_* / FEAT-03 6 feature は残す。
    # Rule 1 auto-fix (PLAN 05 live-DB 検証で発覚): field_strength_adjusted_rank は FEAT-03 feature
    # （D-11/D-12・target-only race_id group-by で算出・race_relative.py L287-289）・中間値でない。
    # 元の ``c.startswith("field_strength_")`` 条件がこれも巻き込んで drop していたため・
    # FEAT-03 feature 名を明示的に除外する（registry parity のため・6 feature 全て残す）。
    _FEAT03_KEEP_COLS = frozenset({
        "speed_index_rank_mean5",
        "speed_index_rank_best2_mean5",
        "speed_index_rank_median5",
        "gap_to_top",
        "gap_to_3rd",
        "field_strength_adjusted_rank",
    })
    feature_matrix = feature_matrix.drop(
        columns=[
            c for c in feature_matrix.columns
            if c.startswith("field_strength_")
            and not c.startswith("rolling_field_strength_")
            and c not in _FEAT03_KEEP_COLS
        ],
        errors="ignore",
    )

    # --- Step 6b: obs_id 中間処理用列の除去（CR-01 / WR-03 実データ検証で発見） ---
    # obs_id は rolling merge (CR-01) と推定脚質 groupby (WR-03) の中間キーで (race_nkey, kettonum)
    # の tuple。PyArrow が tuple を直列化できず write_snapshot で ArrowTypeError になる。
    # race_nkey + kettonum で復元可能なため最終 feature_matrix からは除外する。
    # Phase 9.1 (D-09.1-05): trackcd/kyori も same_surface/same_distance_bucket 計算用の中間値
    # として feature snapshot に出力しない（speed profile 特徴量のみ追加・rolling_df から
    # rolling_* のみ merge なので自動的に入らないが・feature_matrix 本体に残るため明示 drop）。
    feature_matrix = feature_matrix.drop(
        columns=["obs_id", "trackcd", "kyori"], errors="ignore"
    )

    # --- Step 7: §13.2 metadata stamp（全行に定数列） ---
    feature_matrix["feature_snapshot_id"] = snapshot_id
    feature_matrix["feature_availability_version"] = fa_version
    feature_matrix["label_generation_version"] = label_version
    feature_matrix["prediction_timing"] = "1A"

    # --- Step 8: canonical key 一意性検証（umaban 重複29件回避・Pitfall・T-03-16） ---
    if "race_nkey" in feature_matrix.columns:
        n_groups = feature_matrix.groupby(["race_nkey", "kettonum"]).ngroups
        assert n_groups == len(feature_matrix), (
            f"feature matrix の (race_nkey, kettonum) が一意でない: "
            f"groups={n_groups} != rows={len(feature_matrix)} (canonical key 違反・T-03-16)"
        )

    # --- Step 9: HIGH #3 出力カラム全登録検査（banned alias sneak-in を fail-loud） ---
    assert_matrix_columns_registered(spec, list(feature_matrix.columns))

    logger.info(
        "build_feature_matrix: snapshot_id=%s rows=%d features=%d raw_touched=False",
        snapshot_id,
        len(feature_matrix),
        feature_matrix.shape[1],
    )

    return {
        "feature_matrix": feature_matrix,
        "snapshot_id": snapshot_id,
        "raw_touched": False,
        "feature_count": int(feature_matrix.shape[1]),
        "row_count": int(len(feature_matrix)),
    }


# ---------------------------------------------------------------------------
# internal: readonly SELECT helpers（明示カラム・JRA フィルタ・Pitfall 1）
# ---------------------------------------------------------------------------
def _fetch_feature_sources(read_pool: ConnectionPool) -> pd.DataFrame:
    """observations + bloodline を readonly で SELECT し統合（明示カラム）。

    normalized.n_uma_race / normalized.n_race / public.n_uma から ``project_window_filter``
    で JRA フィルタを適用（CR-06: JOIN 両側に ``project_window_filter`` を付与・03-05 CR-02 fix
    で label_race_date_backfill.py と対称）。明示カラムのみ（ワイルドカード SELECT 禁止・Pitfall 1）。
    DB に存在しない derived 列（race_nkey / as_of_datetime）は ``_construct_derived_columns``
    で pandas 側で構築する（BUG A fix・PIT 意味不変）。

    実行時 DB が未接続（unit test 等）の場合は空 DataFrame を返し、rolling/sentinel 経路で
    安全にフォールバックする。本関数は ``build_feature_matrix`` のみから呼ばれる。
    """
    try:
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                obs_cols = ", ".join(_OBS_DB_SELECT_COLUMNS)
                obs_sql = (
                    f"SELECT {obs_cols} FROM normalized.n_uma_race ur "
                    f"JOIN normalized.n_race nr ON (ur.year=nr.year AND ur.jyocd=nr.jyocd "
                    f"AND ur.kaiji=nr.kaiji AND ur.nichiji=nr.nichiji AND ur.racenum=nr.racenum) "
                    # CR-06 / CR-02 (03-05): JOIN 両側に project_window_filter を適用
                    # （label_race_date_backfill.py と対称・JRA 10場 + year>=2015 単一ソース）。
                    f"WHERE {project_window_filter('ur')} AND {project_window_filter('nr')}"
                )
                # n_uma.kettonum は varchar・n_uma_race.kettonum は integer なので
                # join key 型を揃えるため cast（live-DB 整合・Rule 3 blocking fix）。
                blood_sql = (
                    "SELECT kettonum::int AS kettonum, ketto3infohansyokunum1, "
                    "ketto3infohansyokunum2 FROM public.n_uma "
                    "WHERE kettonum IS NOT NULL AND kettonum ~ '^[0-9]+$'"
                )
                cur.execute(obs_sql)
                obs_rows = cur.fetchall()
                cur.execute(blood_sql)
                blood_rows = cur.fetchall()
        obs_df = (
            pd.DataFrame(obs_rows, columns=_OBS_SELECT_COLUMN_NAMES)
            if obs_rows
            else pd.DataFrame(columns=_OBS_SELECT_COLUMN_NAMES)
        )
        blood_df = (
            pd.DataFrame(blood_rows, columns=_BLOODLINE_COLUMNS)
            if blood_rows
            else pd.DataFrame(columns=_BLOODLINE_COLUMNS)
        )
        if len(obs_df) > 0:
            obs_df = _construct_derived_columns(obs_df)
        if len(obs_df) > 0 and len(blood_df) > 0:
            obs_df = obs_df.merge(blood_df, on="kettonum", how="left")
        return obs_df
    except (
        psycopg.errors.OperationalError,
        psycopg.errors.InterfaceError,
        ConnectionError,
    ) as exc:
        # WR-01 (03-REVIEW): DB 接続関連例外のみ空 frame で安全フォールバック
        # （unit test の DB 未接続・本番 DB 一時障害）。想定外例外（MemoryError /
        # ProgrammingError / RuntimeError 等）は re-raise して WR-02 fail-loud に伝播させる。
        logger.warning("feature source fetch failed (DB unavailable, returning empty frame): %s", exc)
        return pd.DataFrame(columns=_OBS_SELECT_COLUMN_NAMES)


def _fetch_history(read_pool: ConnectionPool) -> pd.DataFrame:
    """過去走 history を readonly で SELECT（明示カラム・JRA フィルタ）。

    ``_HISTORY_DB_SELECT_COLUMNS``（TARGET_OBS_BANNED_COLUMNS と disjoint・HIGH #4）のみを
    DB から取得し、derived 列（race_nkey / as_of_datetime / days_since_prev）は
    ``_construct_derived_columns`` で pandas 側で構築する（BUG A fix・PIT 意味不変）。
    """
    try:
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                cols = ", ".join(_HISTORY_DB_SELECT_COLUMNS)
                sql = (
                    f"SELECT {cols} FROM normalized.n_uma_race ur "
                    f"JOIN normalized.n_race nr ON (ur.year=nr.year AND ur.jyocd=nr.jyocd "
                    f"AND ur.kaiji=nr.kaiji AND ur.nichiji=nr.nichiji AND ur.racenum=nr.racenum) "
                    # CR-06 / CR-02 (03-05): JOIN 両側に project_window_filter を適用
                    # （label_race_date_backfill.py と対称）。
                    f"WHERE {project_window_filter('ur')} AND {project_window_filter('nr')}"
                )
                cur.execute(sql)
                rows = cur.fetchall()
        if not rows:
            return pd.DataFrame(columns=_HISTORY_SELECT_COLUMN_NAMES)
        hist_df = pd.DataFrame(rows, columns=_HISTORY_SELECT_COLUMN_NAMES)
        return _construct_derived_columns(hist_df, with_days_since_prev=True)
    except (
        psycopg.errors.OperationalError,
        psycopg.errors.InterfaceError,
        ConnectionError,
    ) as exc:
        # WR-01 (03-REVIEW): DB 接続関連例外のみ空 frame で安全フォールバック
        # （unit test の DB 未接続・本番 DB 一時障害）。想定外例外は re-raise して
        # 呼出側の WR-02 fail-loud / 上位ログ層に伝播させる。
        logger.warning("history fetch failed (DB unavailable, returning empty frame): %s", exc)
        return pd.DataFrame(columns=_HISTORY_SELECT_COLUMN_NAMES)


def _cast_static_columns(df: pd.DataFrame) -> pd.DataFrame:
    """静的属性のキャスト（``normalize.py:_transform_uma_race_df`` analog）。

    int 系は ``pd.to_numeric(errors="coerce").astype("Int64")``・real 系は ``astype(float)``。
    """
    int_cols = ("barei", "umaban", "wakuban", "kakuteijyuni")
    real_cols = ("futan",)
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in real_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df
