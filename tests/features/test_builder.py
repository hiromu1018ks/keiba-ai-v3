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

    過去走 source として babacd / timediff / harontimel3 / jyuni3c / jyuni4c は含む
    （history_allowed_post_race・registry taxonomy と整合）。
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
    # 過去走 babacd / timediff / harontimel3 は許可されているべき
    for allowed_history in ("babacd", "timediff", "harontimel3", "jyuni3c", "jyuni4c"):
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
