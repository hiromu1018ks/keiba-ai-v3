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

import pandas as pd
import psycopg.errors
from psycopg_pool import ConnectionPool

import numpy as np

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

    # Phase 3.1 (Plan 03 Task 1): babacd trackcd 第1桁分岐派生（D-13・Pitfall 2・T-03.1-08）
    # trackcd 先頭桁で芝/ダートを判定し、対応する馬場状態コード（sibababacd/dirtbabacd）を
    # babacd 列に格納。判定不能/欠損は __MISSING__ sentinel（silent NaN fill 禁止）。
    #   - trackcd 第1桁 "1"/"2" → 芝 → babacd = hist_sibababacd（芝馬場状態）
    #   - trackcd 第1桁 "5"     → ダート → babacd = hist_dirtbabacd（ダート馬場状態）
    #     （dirtbabacd='0'/欠損/NaN の場合は信号欠損 → __MISSING__・T-03.1-08 accept）
    #   - その他（'0'/'3'/'4'/欠損/曖昧）→ __MISSING__
    if (
        "trackcd" in result.columns
        and "hist_sibababacd" in result.columns
        and "hist_dirtbabacd" in result.columns
        and "babacd" not in result.columns
    ):
        tc = result["trackcd"].astype(str).str.strip()
        lead = tc.str[0]
        turf_mask = lead.isin(["1", "2"])
        dirt_mask = lead == "5"
        babacd = pd.Series([MISSING] * len(result), dtype=object, index=result.index)
        # 芝: sibababacd が '0'/空/NaN なら __MISSING__（信号欠損）
        turf_val = result["hist_sibababacd"].astype(str).str.strip()
        turf_valid = turf_mask & turf_val.notna() & (turf_val != "") & (turf_val != "nan") & (turf_val != "0")
        babacd = babacd.where(~turf_valid, turf_val)
        # ダート: dirtbabacd が '0'/空/NaN なら __MISSING__（信号欠損・T-03.1-08）
        dirt_val = result["hist_dirtbabacd"].astype(str).str.strip()
        dirt_valid = dirt_mask & dirt_val.notna() & (dirt_val != "") & (dirt_val != "nan") & (dirt_val != "0")
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
    if len(history) > 0 and len(feature_matrix) > 0:
        rolling_df = build_rolling_features(feature_matrix, history)
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
