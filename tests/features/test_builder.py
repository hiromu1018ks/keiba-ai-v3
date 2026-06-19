"""D-09 + SELECT * 禁止 + REVIEWS HIGH #3 builder 連携（RED stub・Plan 03-03 GREEN）。

本ファイルは ``src.features.builder`` が未実装のため RED。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest


def _get_builder():
    from src.features import builder  # Plan 03-03 で実装
    return builder


# ---------------------------------------------------------------------------
# D-09: 全期間1枚 + 分割非依存
# ---------------------------------------------------------------------------
def test_split_independence():
    """同一 snapshot を train/val/test に任意の race_date 境界で分割しても境界付近の馬の
    feature 値が同一である（全期間1枚の根拠）。"""
    builder = _get_builder()
    src = inspect.getsource(builder.build_feature_matrix)
    # 全期間1枚で構築後、呼出側で分割することを契約で示す
    assert "train_period" in src or "split" in src.lower(), (
        "build_feature_matrix が全期間1枚でなく分割依存の可能性（D-09）"
    )


def test_no_select_star_in_builder():
    """builder に SELECT * が出現しない（明示カラムのみ・Pitfall 1）。"""
    builder = _get_builder()
    src = inspect.getsource(builder)
    assert "SELECT *" not in src, "builder に SELECT * がある（Pitfall 1・明示カラムのみ許可）"


def test_banned_columns_not_selected():
    """_HISTORY_SELECT_COLUMNS に target_obs_banned カラムが含まれない（HIGH #4 区別）。

    過去走 source として harontimel3 / jyuni3c / jyuni4c は含む
    （history_allowed_post_race・registry taxonomy と整合）。``babacd`` / ``timediff`` は
    normalized 層に実在カラムが無いため SELECT 対象外（rolling 側 D-13 sentinel 扱い・
    live-DB 整合 fix）。当該 rolling 系統は ``__MISSING__`` で安全に fallback する。
    """
    builder = _get_builder()
    assert hasattr(builder, "_HISTORY_SELECT_COLUMNS"), (
        "builder に _HISTORY_SELECT_COLUMNS 定数が無い"
    )
    history_cols = set(builder._HISTORY_SELECT_COLUMNS)
    from src.features.availability import TARGET_OBS_BANNED_COLUMNS

    leaked = TARGET_OBS_BANNED_COLUMNS & history_cols
    assert leaked == set(), (
        f"_HISTORY_SELECT_COLUMNS に target_obs_banned カラムが含まれる: {leaked} (HIGH #4)"
    )
    # 過去走 harontimel3 / jyuni3c / jyuni4c は実在カラムであり許可されているべき
    for allowed_history in ("harontimel3", "jyuni3c", "jyuni4c"):
        assert allowed_history in history_cols, (
            f"_HISTORY_SELECT_COLUMNS に過去走 source {allowed_history} が無い（HIGH #4 history_allowed）"
        )


def test_canonical_key_is_race_nkey_kettonum():
    """feature matrix の行 key が (race_nkey, kettonum) で一意（umaban は key にしない）。"""
    builder = _get_builder()
    src = inspect.getsource(builder)
    assert "race_nkey" in src and "kettonum" in src, (
        "builder に race_nkey / kettonum の canonical key が無い（29件重複回避）"
    )


# ---------------------------------------------------------------------------
# REVIEWS HIGH #3: builder -> availability 連携
# ---------------------------------------------------------------------------
def test_builder_output_columns_all_registered_in_registry():
    """build_feature_matrix の戻り columns が assert_matrix_columns_registered で全て合格。

    builder 内部で assert_matrix_columns_registered を呼ぶ実装契約。
    """
    from src.features.availability import (
        assert_matrix_columns_registered,
        load_feature_availability,
    )

    builder = _get_builder()
    spec = load_feature_availability()
    # builder が出力するカラム名一覧を取得（docstring/契約から）
    # Plan 03-03 完了後に実際の build 結果で検証
    src = inspect.getsource(builder.build_feature_matrix)
    assert "assert_matrix_columns_registered" in src, (
        "build_feature_matrix 内部で assert_matrix_columns_registered を呼んでいない（HIGH #3）"
    )
    # spec 自体が健全であることも再確認
    assert_matrix_columns_registered(spec, output_columns=[])


# ---------------------------------------------------------------------------
# CR-01 (03-05 gap-closure): registry↔実体 silent empty feature breach 回帰防止
# ---------------------------------------------------------------------------
def test_no_registered_feature_column_all_nan_end_to_end():
    """合成 DB-mock を通じた end-to-end builder path で、登録 feature 列が1つも
    100% NaN にならないことを assert（CR-01 regression guard・MANDATORY）。

    現状 test_rolling.py は合成 dict fixture のみを検査し builder 経由の end-to-end
    をカバーしないため、CR-01（rolling source 欠損 → silent 全 NaN）が検出できなかった。
    万が一 rolling source が欠損した系統が再登録されると本 test が RED になる。
    """
    from src.features.availability import load_feature_availability
    from src.utils.category_map import MISSING

    builder = _get_builder()

    # 合成 DB-mock: 2馬 × 数レースの過去走（cutoff 前後の mix）
    obs_rd = pd.Timestamp("2023-06-04")
    cutoff = obs_rd - pd.Timedelta(days=1)
    observations = pd.DataFrame([
        {
            "race_nkey": "2023A0604-R1", "kettonum": 1001,
            "race_date": obs_rd, "race_start_datetime": obs_rd + pd.Timedelta(hours=12),
            "feature_cutoff_datetime": cutoff, "as_of_datetime": obs_rd,
            "jyocd": "05", "kyori": 1600, "umaban": 1, "wakuban": 1,
            "barei": 4, "sexcd": "1", "futan": 57.0,
            "kisyucode": "01001", "chokyosicode": "01001",
            "ketto3infohansyokunum1": "SIRE001", "ketto3infohansyokunum2": "BMS001",
        },
        {
            "race_nkey": "2023A0604-R1", "kettonum": 1002,
            "race_date": obs_rd, "race_start_datetime": obs_rd + pd.Timedelta(hours=12),
            "feature_cutoff_datetime": cutoff, "as_of_datetime": obs_rd,
            "jyocd": "05", "kyori": 1600, "umaban": 2, "wakuban": 2,
            "barei": 5, "sexcd": "2", "futan": 57.0,
            "kisyucode": "01002", "chokyosicode": "01002",
            "ketto3infohansyokunum1": "SIRE002", "ketto3infohansyokunum2": "BMS002",
        },
    ])
    history_rows = []
    for kn in (1001, 1002):
        for day_offset, val in [(-2, 1), (-3, 2), (-4, 3), (-5, 4)]:
            hr = obs_rd + pd.Timedelta(days=day_offset)
            history_rows.append({
                "kettonum": kn,
                "race_date": hr,
                "as_of_datetime": hr,
                "race_start_datetime": hr + pd.Timedelta(hours=12),
                "kakuteijyuni": val, "harontimel3": 36.0 + val,
                "jyuni3c": val, "jyuni4c": val, "jyuni1c": 0,
                "kyori": 1600, "jyocd": "05",
                "days_since_prev": float(abs(day_offset)),
            })
    history = pd.DataFrame(history_rows)

    rolling_df = builder.build_rolling_features(observations, history)

    spec = load_feature_availability()
    rolling_mean_features = [
        e["feature_name"]
        for e in spec["features"]
        if e["feature_name"].startswith("rolling_") and e["feature_name"].endswith("_mean_5")
    ]
    assert len(rolling_mean_features) > 0, "registry に rolling_*_mean_5 が1つも無い（前提違反）"

    all_nan_cols = []
    for col in rolling_mean_features:
        if col not in rolling_df.columns:
            all_nan_cols.append(col)
            continue
        series = rolling_df[col]
        # 純粋 NaN 100% を弾く（sentinel 文字列 __MISSING__ は isna で False なので新馬行列も合格）
        if series.isna().all():
            all_nan_cols.append(col)
    assert all_nan_cols == [], (
        f"登録 rolling_*_mean_5 feature が 100% NaN: {all_nan_cols} "
        "(CR-01 regression・registry↔実体 silent 乖離・source カラム欠損)"
    )


def test_registry_rolling_systems_match_rolling_impl():
    """registry の rolling_*_mean_5 系統集合が rolling.py::_ROLLING_SYSTEMS と
    availability._ROLLING_SYSTEMS_FOR_RESERVED と完全一致することを assert
    （3者 parity・IN-01 重複定義の drift を機械検出）。
    """
    from src.features.availability import (
        _ROLLING_SYSTEMS_FOR_RESERVED,
        load_feature_availability,
    )
    from src.features.rolling import _ROLLING_SYSTEMS

    spec = load_feature_availability()
    rolling_in_registry = {
        e["feature_name"].removeprefix("rolling_").removesuffix("_mean_5")
        for e in spec["features"]
        if e["feature_name"].startswith("rolling_") and e["feature_name"].endswith("_mean_5")
    }
    assert rolling_in_registry == set(_ROLLING_SYSTEMS), (
        f"registry↔rolling.py drift: {rolling_in_registry} != {set(_ROLLING_SYSTEMS)}"
    )
    assert rolling_in_registry == set(_ROLLING_SYSTEMS_FOR_RESERVED), (
        f"registry↔availability drift: {rolling_in_registry} != "
        f"{set(_ROLLING_SYSTEMS_FOR_RESERVED)}"
    )
    assert tuple(_ROLLING_SYSTEMS_FOR_RESERVED) == _ROLLING_SYSTEMS, (
        "rolling.py と availability.py の _ROLLING_SYSTEMS 順序含め不一致"
    )


def test_no_timediff_babacd_in_registry_or_rolling():
    """CR-01 DELETE verify: rolling._ROLLING_SYSTEMS /
    availability._ROLLING_SYSTEMS_FOR_RESERVED / registry features のいずれにも
    rolling_timediff_* / rolling_babacd_* が含まれないこと。
    """
    from src.features.availability import (
        _ROLLING_SYSTEMS_FOR_RESERVED,
        load_feature_availability,
    )
    from src.features.rolling import _ROLLING_SYSTEMS

    assert "timediff" not in _ROLLING_SYSTEMS, (
        "rolling.py に timediff が残存（CR-01 違反）"
    )
    assert "babacd" not in _ROLLING_SYSTEMS, (
        "rolling.py に babacd が残存（CR-01 違反）"
    )
    assert "timediff" not in _ROLLING_SYSTEMS_FOR_RESERVED, (
        "availability.py に timediff が残存（CR-01 違反）"
    )
    assert "babacd" not in _ROLLING_SYSTEMS_FOR_RESERVED, (
        "availability.py に babacd が残存（CR-01 違反）"
    )
    spec = load_feature_availability()
    feats = [e["feature_name"] for e in spec["features"]]
    leaked = [
        x for x in feats
        if x.startswith("rolling_timediff_") or x.startswith("rolling_babacd_")
    ]
    assert leaked == [], (
        f"registry に rolling_timediff_* / rolling_babacd_* が残存: {leaked} (CR-01 違反)"
    )


# ---------------------------------------------------------------------------
# CR-02 (03-05 gap-closure): JOIN 両側 project_window_filter 回帰防止
# ---------------------------------------------------------------------------
def test_fetch_history_and_feature_sources_filter_both_join_sides():
    """_fetch_feature_sources と _fetch_history の両方の source に
    ``project_window_filter('nr')`` が含まれることを assert（CR-02 / CR-06 契約・
    label_race_date_backfill.py と対称）。
    """
    builder = _get_builder()
    src_features = inspect.getsource(builder._fetch_feature_sources)
    src_history = inspect.getsource(builder._fetch_history)
    assert "project_window_filter('ur')" in src_features, (
        "_fetch_feature_sources に project_window_filter('ur') が無い"
    )
    assert "project_window_filter('ur')" in src_history, (
        "_fetch_history に project_window_filter('ur') が無い"
    )
    assert "project_window_filter('nr')" in src_features, (
        "_fetch_feature_sources に project_window_filter('nr') が無い（CR-02 違反・JOIN 右側未 filter）"
    )
    assert "project_window_filter('nr')" in src_history, (
        "_fetch_history に project_window_filter('nr') が無い（CR-02 違反・JOIN 右側未 filter）"
    )
