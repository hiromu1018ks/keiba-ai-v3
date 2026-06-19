"""SC#2 fail-loud + REVIEWS HIGH #3 出力カラム検査 + HIGH #4 taxonomy（GREEN 想定）。

本テストは ``src/features/availability.py``（Plan 03-01 Task 1 作成済）のみに依存し、
他の features.* モジュール（builder/rolling/snapshot 等・Plan 03-03/03-04）には依存しない。
したがって GREEN になるはず（Phase 2 Plan 02-02 RED-集群パターンの例外）。
"""

from __future__ import annotations

import pytest

from src.features.availability import (
    ALLOWED_TIMINGS,
    BANNED_TIMINGS,
    assert_all_entries_allowed,
    assert_matrix_columns_registered,
    banned_features,
    load_feature_availability,
    registered_feature_columns,
)


def _spec() -> dict:
    return load_feature_availability()


# ---------------------------------------------------------------------------
# SC#2 fail-loud: 禁止 timing の feature は0件
# ---------------------------------------------------------------------------
def test_no_banned_timing_features():
    spec = _spec()
    offenders = banned_features(spec)
    assert offenders == [], f"禁止 timing の feature が存在: {offenders} (D-07)"


@pytest.mark.parametrize("timing", sorted(BANNED_TIMINGS))
def test_no_banned_timing_parametrized(timing: str):
    """5禁止 timing 各々について spec 内に0件であることを parametrize で検査。"""
    spec = _spec()
    matches = [f["feature_name"] for f in spec["features"] if f.get("available_from_timing") == timing]
    assert matches == [], f"available_from_timing={timing} の feature が存在: {matches}"


def test_all_entries_in_allowed_set():
    """全 feature の timing が ALLOWED_TIMINGS に属する（未知 timing 含まない）。"""
    assert_all_entries_allowed(_spec())  # raise しなければ合格


# ---------------------------------------------------------------------------
# REVIEWS HIGH #3: 出力カラム全登録検査
# ---------------------------------------------------------------------------
def test_matrix_columns_all_registered():
    """registry 全 feature + reserved keys を渡すと raise しない。"""
    spec = _spec()
    output_columns = sorted(registered_feature_columns(spec))
    assert_matrix_columns_registered(spec, output_columns)  # raise しなければ合格


def test_matrix_rejects_unregistered_column():
    """未登録カラムは ValueError で reject される。"""
    spec = _spec()
    with pytest.raises(ValueError, match="unregistered feature-matrix column: unregistered_evil_column"):
        assert_matrix_columns_registered(spec, output_columns=["unregistered_evil_column"])


def test_matrix_rejects_banned_timing_column_under_allowed_name():
    """banned source が allowed feature 名の alias で潜入しても reject される。"""
    spec = _spec()
    with pytest.raises(ValueError, match="unregistered feature-matrix column: same_day_track_condition"):
        assert_matrix_columns_registered(spec, output_columns=["same_day_track_condition"])


# ---------------------------------------------------------------------------
# REVIEWS HIGH #4: target_obs_banned vs history_allowed taxonomy
# ---------------------------------------------------------------------------
def test_target_obs_banned_columns_not_in_registry_features():
    """target_obs_banned カラムは registry の feature_name に含まれない。"""
    spec = _spec()
    names = registered_feature_columns(spec)
    from src.features.availability import TARGET_OBS_BANNED_COLUMNS

    leaked = TARGET_OBS_BANNED_COLUMNS & names
    assert leaked == set(), (
        f"target_obs_banned カラムが feature_name として登録されている: {leaked} (HIGH #4)"
    )


def test_history_allowed_babacd_rolling_present():
    """過去走 babacd に由来する rolling feature は registry に含まれる（HIGH #4 で許可）。"""
    spec = _spec()
    names = registered_feature_columns(spec)
    for required in ("rolling_babacd_mean_5", "rolling_babacd_latest_5", "rolling_babacd_sd_5"):
        assert required in names, (
            f"{required} が registry に存在しない（過去走 babacd rolling は history_allowed・HIGH #4）"
        )


def test_target_and_history_column_sets_disjoint():
    """TARGET_OBS_BANNED_COLUMNS と HISTORY_ALLOWED_POST_RACE_COLUMNS は disjoint。

    Pitfall 3.6 厳守: harontimel4 は TARGET_OBS_BANNED 側に分類され history SELECT にも許可されない。
    """
    from src.features.availability import (
        HISTORY_ALLOWED_POST_RACE_COLUMNS,
        TARGET_OBS_BANNED_COLUMNS,
    )

    assert TARGET_OBS_BANNED_COLUMNS.isdisjoint(HISTORY_ALLOWED_POST_RACE_COLUMNS), (
        "TARGET_OBS_BANNED_COLUMNS と HISTORY_ALLOWED_POST_RACE_COLUMNS が交差している "
        "(Pitfall 3.6 違反・harontimel4 が history 側に漏れている可能性)"
    )
    assert "harontimel4" in TARGET_OBS_BANNED_COLUMNS
    assert "harontimel4" not in HISTORY_ALLOWED_POST_RACE_COLUMNS
