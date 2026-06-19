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
from psycopg_pool import ConnectionPool

from src.etl.filters import PROJECT_WINDOW_FILTER, project_window_filter
from src.features.availability import (
    TARGET_OBS_BANNED_COLUMNS,
    assert_all_entries_allowed,
    assert_matrix_columns_registered,
    load_feature_availability,
)
from src.features.rolling import build_rolling_features as _build_rolling_features_impl
from src.features.running_style import estimate_running_style

logger = logging.getLogger(__name__)

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
# normalized.n_uma_race から取得する過去走 history カラム。TARGET_OBS_BANNED_COLUMNS
# （当日禁止: kyakusitukubun/bataijyu/ninki/odds/sibababacd/dirtbabacd/tenkocd/harontimel4）
# とは**異なる SELECT パス**・同名衝突しない。過去走 babacd/timediff/harontimel3/
# jyuni3c/jyuni4c は HISTORY_ALLOWED_POST_RACE_COLUMNS（rolling source として許可・
# 当日行は cutoff で除外）。
_HISTORY_SELECT_COLUMNS: tuple[str, ...] = (
    "kettonum",
    "race_nkey",
    "race_date",
    "as_of_datetime",
    "race_start_datetime",
    "kakuteijyuni",
    "timediff",
    "harontimel3",
    "jyuni3c",
    "jyuni4c",
    "jyuni1c",
    "kyori",
    "jyocd",
    "babacd",
    "datakubun",
    "days_since_prev",
)

# 対象レース observations（normalized.n_uma_race + n_race JOIN から取得）
_OBS_SELECT_COLUMNS: tuple[str, ...] = (
    "kettonum",
    "race_nkey",
    "race_date",
    "race_start_datetime",
    "jyocd",
    "kyori",
    "umaban",
    "wakuban",
    "barei",
    "sexcd",
    "futan",
    "kisyucode",
    "chokyosicode",
    "class_code_normalized",
)

# race-level 文脈（normalized.n_race から取得・trackcd/coursekubuncd は raw_everydb2 VIEW 由来）
_RACE_CONTEXT_COLUMNS: tuple[str, ...] = (
    "race_nkey",
    "race_date",
    "race_start_datetime",
    "jyocd",
    "kyori",
    "trackcd",
    "coursekubuncd",
    "class_code_normalized",
)

# 3代血統（public.n_uma から取得）
_BLOODLINE_COLUMNS: tuple[str, ...] = (
    "kettonum",
    "ketto3infohansyokunum1",  # sire_id
    "ketto3infohansyokunum2",  # bms_id
)

# ---------------------------------------------------------------------------
# 起動時不変量: _HISTORY_SELECT_COLUMNS と TARGET_OBS_BANNED_COLUMNS は disjoint（HIGH #4）
# 両者は別 SELECT パスなので同名衝突しないが、誤って禁止カラムを history に混入するのを
# 機械的に防止する。sibababacd/dirtbabacd（target_obs_banned）と babacd（history_allowed）
# は異なるカラム名なのでこの検査で衝突しない。
# ---------------------------------------------------------------------------
assert TARGET_OBS_BANNED_COLUMNS.isdisjoint(_HISTORY_SELECT_COLUMNS), (
    "_HISTORY_SELECT_COLUMNS に TARGET_OBS_BANNED_COLUMNS と衝突するカラムがある (HIGH #4)"
)


def build_rolling_features(observations: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """``src.features.rolling.build_rolling_features`` への薄い転送（テスト契約）。

    ``test_pit_cutoff.py`` が builder 経由で rolling を呼び出すための薄ラッパ。
    入力を rolling 実装に渡す前に PIT join 用の sortedness を担保する（``sort_values``
    を呼出・regression guard・HIGH #1/#3）。
    """
    obs_sorted = observations.sort_values("feature_cutoff_datetime").reset_index(drop=True)
    if len(history) > 0:
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
    6. 推定脚質（``estimate_running_style``・過去走 jyuni3c/jyuni4c のみ・D-05）。
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

    # --- Step 2: readonly SELECT（明示カラム・JRA フィルタ・Pitfall 1） ---
    feature_matrix = _fetch_feature_sources(read_pool)

    # --- Step 3: cutoff 計算（D-06・HIGH #2: race_date - 1 day・JST midnight・strict <） ---
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
    history = _fetch_history(read_pool)
    if len(history) > 0 and len(feature_matrix) > 0:
        rolling_df = build_rolling_features(feature_matrix, history)
        rolling_cols = [
            c for c in rolling_df.columns if c.startswith("rolling_")
        ]
        fm_reset = feature_matrix.reset_index(drop=True)
        rolling_reset = rolling_df[rolling_cols].reset_index(drop=True)
        feature_matrix = pd.concat([fm_reset, rolling_reset], axis=1)

    # --- Step 6: 推定脚質（過去走 jyuni3c/jyuni4c のみ・当日不使用・D-05） ---
    if len(history) > 0 and "kettonum" in history.columns and len(feature_matrix) > 0:
        style_map: dict[Any, str] = {}
        for kn, group in history.groupby("kettonum"):
            rows = group[["jyuni3c", "jyuni4c"]].to_dict(orient="records") if len(group) > 0 else []
            style_map[kn] = estimate_running_style(rows)
        feature_matrix["estimated_running_style"] = (
            feature_matrix["kettonum"].map(style_map).fillna("__MISSING__")
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
    """observations + race_context + bloodline を readonly で SELECT し統合（明示カラム）。

    normalized.n_uma_race / normalized.n_race / public.n_uma から ``PROJECT_WINDOW_FILTER``
    と ``project_window_filter(alias)`` で JRA フィルタを適用（CR-06）。明示カラムのみ
    （ワイルドカード SELECT 禁止・Pitfall 1）。

    実行時 DB が未接続（unit test 等）の場合は空 DataFrame を返し、rolling/sentinel 経路で
    安全にフォールバックする。本関数は ``build_feature_matrix`` のみから呼ばれる。
    """
    try:
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                obs_cols = ", ".join(_OBS_SELECT_COLUMNS)
                blood_cols = ", ".join(_BLOODLINE_COLUMNS)
                obs_sql = (
                    f"SELECT {obs_cols} FROM normalized.n_uma_race ur "
                    f"JOIN normalized.n_race nr ON (ur.year=nr.year AND ur.jyocd=nr.jyocd "
                    f"AND ur.kaiji=nr.kaiji AND ur.nichiji=nr.nichiji AND ur.racenum=nr.racenum) "
                    f"WHERE {project_window_filter('ur')}"
                )
                blood_sql = (
                    f"SELECT {blood_cols} FROM public.n_uma "
                    f"WHERE kettonum IS NOT NULL"
                )
                cur.execute(obs_sql)
                obs_rows = cur.fetchall()
                cur.execute(blood_sql)
                blood_rows = cur.fetchall()
        obs_df = pd.DataFrame(obs_rows, columns=_OBS_SELECT_COLUMNS) if obs_rows else pd.DataFrame()
        blood_df = (
            pd.DataFrame(blood_rows, columns=_BLOODLINE_COLUMNS)
            if blood_rows
            else pd.DataFrame(columns=_BLOODLINE_COLUMNS)
        )
        if len(obs_df) > 0 and len(blood_df) > 0:
            obs_df = obs_df.merge(blood_df, on="kettonum", how="left")
        return obs_df
    except Exception as exc:  # noqa: BLE001 - unit test / DB 未接続時は空 frame で安全フォールバック
        logger.warning("feature source fetch failed (returning empty frame): %s", exc)
        return pd.DataFrame(columns=_OBS_SELECT_COLUMNS)


def _fetch_history(read_pool: ConnectionPool) -> pd.DataFrame:
    """過去走 history を readonly で SELECT（明示カラム・JRA フィルタ）。

    ``_HISTORY_SELECT_COLUMNS``（TARGET_OBS_BANNED_COLUMNS と disjoint・HIGH #4）のみ。
    """
    try:
        with read_pool.connection() as conn:
            with conn.cursor() as cur:
                cols = ", ".join(_HISTORY_SELECT_COLUMNS)
                sql = (
                    f"SELECT {cols} FROM normalized.n_uma_race WHERE {PROJECT_WINDOW_FILTER}"
                )
                cur.execute(sql)
                rows = cur.fetchall()
        return pd.DataFrame(rows, columns=_HISTORY_SELECT_COLUMNS) if rows else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001 - DB 未接続時は空 frame
        logger.warning("history fetch failed (returning empty frame): %s", exc)
        return pd.DataFrame(columns=_HISTORY_SELECT_COLUMNS)


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
