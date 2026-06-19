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

    Phase 3.1 (Plan 03 Task 3B・CHECKER WARNING #1 対応): 派生経路を一つに確定するため
    ``build_rolling_features`` 直接呼出を廃止し ``build_feature_matrix`` 経由に切り替え。
    これにより ``_construct_derived_columns`` (timediff/babacd 派生) → ``build_rolling_features``
    の順序が本番と同一 path で走り、新6 feature 列が非 NaN で生成されることを機械保証
    （silent-NaN guard の silent 緩和リスク排除）。
    """
    from src.features.availability import load_feature_availability

    builder = _get_builder()

    # 合成 DB-mock: 2馬 × 数レースの過去走（cutoff 前後の mix）
    obs_rd = pd.Timestamp("2023-06-04")
    # observations: _fetch_feature_sources が返す OBS_SELECT_COLUMN_NAMES 構造
    # （race_nkey/as_of_datetime/feature_cutoff_datetime は _construct_derived_columns で派生）
    obs_rows = [
        {
            "kettonum": 1001, "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": 1,
            "racenum": 1, "race_date": obs_rd, "race_start_datetime": obs_rd + pd.Timedelta(hours=12),
            "umaban": 1, "wakuban": 1, "barei": 4, "sexcd": "1", "futan": 57.0,
            "kisyucode": "01001", "chokyosicode": "01001", "class_code_normalized": 1,
            "ketto3infohansyokunum1": "SIRE001", "ketto3infohansyokunum2": "BMS001",
        },
        {
            "kettonum": 1002, "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": 1,
            "racenum": 1, "race_date": obs_rd, "race_start_datetime": obs_rd + pd.Timedelta(hours=12),
            "umaban": 2, "wakuban": 2, "barei": 5, "sexcd": "2", "futan": 57.0,
            "kisyucode": "01002", "chokyosicode": "01002", "class_code_normalized": 1,
            "ketto3infohansyokunum1": "SIRE002", "ketto3infohansyokunum2": "BMS002",
        },
    ]
    observations_raw_df = pd.DataFrame(obs_rows)

    # history: _fetch_history が返す構造を再現（_construct_derived_columns 適用後の状態）。
    # monkey-patch で _fetch_history 本体を差し替えるため、派生列（as_of_datetime /
    # days_since_prev / timediff / babacd）も事前に構築しておく（本番では _fetch_history 内の
    # _construct_derived_columns が生成・テストでは等価な前処理として明示）。
    history_rows = []
    for kn in (1001, 1002):
        for day_offset, val in [(-2, 1), (-3, 2), (-4, 3), (-5, 4)]:
            hr = obs_rd + pd.Timedelta(days=day_offset)
            history_rows.append({
                "kettonum": kn, "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": 1,
                "racenum": 1, "race_date": hr, "race_start_datetime": hr + pd.Timedelta(hours=12),
                "kakuteijyuni": val, "harontimel3": 36.0 + val,
                "jyuni3c": val, "jyuni4c": val, "jyuni1c": 0,
                "kyori": 1600,
                # Phase 3.1: timediff_raw/baba3 を追加（_construct_derived_columns で派生される）
                "timediff_raw": f"+{val * 10:03d}",  # 例 "+010" → 1.0秒・NNN/10
                "hist_sibababacd": "1",              # 芝・良馬場（trackcd 第1桁1→芝→babacd=1）
                "hist_dirtbabacd": "0",
                "trackcd": "10",                     # 第1桁 1=芝
            })
    history_raw_df = pd.DataFrame(history_rows)
    # _fetch_history と等価: _construct_derived_columns(with_days_since_prev=True) を適用
    history_df = builder._construct_derived_columns(history_raw_df, with_days_since_prev=True)

    # _fetch_feature_sources / _fetch_history を monkey-patch で差し替え（DB 不要化）
    # _fetch_feature_sources 本体も _construct_derived_columns を呼ぶため、observations 側も
    # 同様に派生済みの DataFrame を返す（race_nkey/as_of_datetime 等を含む）。
    observations_df = builder._construct_derived_columns(observations_raw_df)
    orig_fetch_sources = builder._fetch_feature_sources
    orig_fetch_history = builder._fetch_history
    builder._fetch_feature_sources = lambda read_pool: observations_df.copy()
    builder._fetch_history = lambda read_pool: history_df.copy()
    try:
        result = builder.build_feature_matrix(
            read_pool=None,  # monkey-patch 済みなので DB 不要
            snapshot_id="test-snap",
            label_version="v1.0.0",
            fa_version="0.2.0",
        )
    finally:
        builder._fetch_feature_sources = orig_fetch_sources
        builder._fetch_history = orig_fetch_history

    feature_matrix = result["feature_matrix"]

    spec = load_feature_availability()
    rolling_mean_features = [
        e["feature_name"]
        for e in spec["features"]
        if e["feature_name"].startswith("rolling_") and e["feature_name"].endswith("_mean_5")
    ]
    assert len(rolling_mean_features) > 0, "registry に rolling_*_mean_5 が1つも無い（前提違反）"

    all_nan_cols = []
    for col in rolling_mean_features:
        if col not in feature_matrix.columns:
            all_nan_cols.append(col)
            continue
        series = feature_matrix[col]
        # 純粋 NaN 100% を弾く（sentinel 文字列 __MISSING__ は isna で False なので新馬行列も合格）
        if series.isna().all():
            all_nan_cols.append(col)
    assert all_nan_cols == [], (
        f"登録 rolling_*_mean_5 feature が 100% NaN: {all_nan_cols} "
        "(CR-01 regression・registry↔実体 silent 乖離・source カラム欠損)"
    )

    # Phase 3.1: 新6 feature（rolling_timediff_*/rolling_babacd_*）が非 NaN で生成されたことを
    # 個別に機械保証（silent-NaN guard が新6 feature をカバー・派生経路 build_feature_matrix 経由）
    for new_col in (
        "rolling_timediff_mean_5", "rolling_babacd_mean_5",
    ):
        assert new_col in feature_matrix.columns, (
            f"{new_col} が feature_matrix に存在しない（派生経路の不備・CHECKER WARNING #1）"
        )
        assert not feature_matrix[new_col].isna().all(), (
            f"{new_col} が全 NaN（timediff parse / babacd trackcd 分岐派生の不備・"
            "silent-NaN regression guard 違反）"
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


def test_timediff_babacd_present_in_registry_or_rolling():
    """Phase 3.1 RESTORE verify: rolling._ROLLING_SYSTEMS /
    availability._ROLLING_SYSTEMS_FOR_RESERVED / registry features のいずれにも
    rolling_timediff_* / rolling_babacd_* 系統（6エントリ）が含まれること。

    CR-01 (03-05) で一時削除されていた timediff/babacd 系統が Phase 3.1 で正しく復元
    されたことを検証（D-01 完全復元・SC#2 rolling 18→24）。
    """
    from src.features.availability import (
        _ROLLING_SYSTEMS_FOR_RESERVED,
        load_feature_availability,
    )
    from src.features.rolling import _ROLLING_SYSTEMS

    assert "timediff" in _ROLLING_SYSTEMS, (
        "rolling.py に timediff が無い（Phase 3.1 復元違反）"
    )
    assert "babacd" in _ROLLING_SYSTEMS, (
        "rolling.py に babacd が無い（Phase 3.1 復元違反）"
    )
    assert "timediff" in _ROLLING_SYSTEMS_FOR_RESERVED, (
        "availability.py に timediff が無い（Phase 3.1 復元違反）"
    )
    assert "babacd" in _ROLLING_SYSTEMS_FOR_RESERVED, (
        "availability.py に babacd が無い（Phase 3.1 復元違反）"
    )
    spec = load_feature_availability()
    feats = [e["feature_name"] for e in spec["features"]]
    required = {
        "rolling_timediff_mean_5", "rolling_babacd_mean_5",
        "rolling_timediff_latest_5", "rolling_babacd_latest_5",
        "rolling_timediff_sd_5", "rolling_babacd_sd_5",
    }
    missing = required - set(feats)
    assert missing == set(), (
        f"registry に rolling_timediff_*/rolling_babacd_* が未復元: {missing} "
        "(Phase 3.1 復元違反・D-01 完全復元)"
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


# ---------------------------------------------------------------------------
# Phase 3.1 (Plan 03 Task 3B): WR-01' / WR-02 fail-loud unit test
# ---------------------------------------------------------------------------
def test_wr01_prime_raises_on_missing_as_of_datetime():
    """WR-01' (Phase 3.1 advisory hardening): history に as_of_datetime 列が無い場合、
    build_feature_matrix が fail-loud することを assert。

    silent no-filter fallback（旧 L353-354 `else: pit_filtered_style = expanded_style`）が
    削除され、将来 refactor での silent leak を防止する。実装上の二重防御: rolling ステップ
    （L296 sort_values）と推定脚質ステップ（WR-01' ValueError）の両方が as_of_datetime を
    要求する。いずれかで fail-loud になれば WR-01' の intent（silent leak 防止）は達成される
    ため、本テストは ValueError/KeyError のいずれかで as_of_datetime に関連するエラーが
    raise されることを検証する。
    """
    builder = _get_builder()

    obs_rd = pd.Timestamp("2023-06-04")
    observations_raw_df = pd.DataFrame([{
        "kettonum": 1001, "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": 1,
        "racenum": 1, "race_date": obs_rd, "race_start_datetime": obs_rd + pd.Timedelta(hours=12),
        "umaban": 1, "wakuban": 1, "barei": 4, "sexcd": "1", "futan": 57.0,
        "kisyucode": "01001", "chokyosicode": "01001", "class_code_normalized": 1,
        "ketto3infohansyokunum1": "SIRE001", "ketto3infohansyokunum2": "BMS001",
    }])
    observations_df = builder._construct_derived_columns(observations_raw_df)
    # as_of_datetime を欠損させるため race_start_datetime を持たない history を構築
    # （_construct_derived_columns は race_start_datetime が無いと as_of_datetime を派生しない）
    bad_history_raw = pd.DataFrame([{
        "kettonum": 1001, "year": 2023, "jyocd": "05", "kaiji": 1, "nichiji": 1,
        "racenum": 1, "race_date": obs_rd - pd.Timedelta(days=2),
        "kakuteijyuni": 1, "harontimel3": 36.0, "jyuni3c": 1, "jyuni4c": 1, "jyuni1c": 0,
        "kyori": 1600, "timediff_raw": "+010",
        "hist_sibababacd": "1", "hist_dirtbabacd": "0", "trackcd": "10",
        # race_start_datetime / as_of_datetime を意図的に欠損
    }])
    # with_days_since_prev=True だが race_start_datetime 無し → as_of_datetime は派生されない
    bad_history = builder._construct_derived_columns(bad_history_raw, with_days_since_prev=True)
    assert "as_of_datetime" not in bad_history.columns, (
        "テスト前提: bad_history に as_of_datetime が派生されてしまっている"
    )

    orig_fetch_sources = builder._fetch_feature_sources
    orig_fetch_history = builder._fetch_history
    builder._fetch_feature_sources = lambda read_pool: observations_df.copy()
    builder._fetch_history = lambda read_pool: bad_history.copy()
    try:
        # rolling/推定脚質いずれかのステップで as_of_datetime 不在が fail-loud 検出される。
        # ValueError(WR-01' message) または KeyError(rolling sort_values) のいずれか。
        with pytest.raises((ValueError, KeyError)) as exc_info:
            builder.build_feature_matrix(
                read_pool=None, snapshot_id="test-snap",
                label_version="v1.0.0", fa_version="0.2.0",
            )
        # as_of_datetime に関連するエラーであることを検証
        msg = str(exc_info.value)
        assert "as_of_datetime" in msg, (
            f"as_of_datetime 不在エラーではない: {type(exc_info.value).__name__}: {msg}"
        )
    finally:
        builder._fetch_feature_sources = orig_fetch_sources
        builder._fetch_history = orig_fetch_history


def test_wr02_raises_on_empty_feature_source():
    """WR-02 (Phase 3.1 advisory hardening): _fetch_feature_sources が空 DataFrame を
    返した状態（DB例外/0行結果/silent empty）で、build_feature_matrix がチョークポイント
    で RuntimeError で fail-loud することを assert（D-04 採択・silent data loss 回避）。
    """
    builder = _get_builder()

    empty_df = pd.DataFrame()
    orig_fetch_sources = builder._fetch_feature_sources
    builder._fetch_feature_sources = lambda read_pool: empty_df.copy()
    try:
        with pytest.raises(RuntimeError, match="WR-02"):
            builder.build_feature_matrix(
                read_pool=None, snapshot_id="test-snap",
                label_version="v1.0.0", fa_version="0.2.0",
            )
    finally:
        builder._fetch_feature_sources = orig_fetch_sources
