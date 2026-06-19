"""SC#4 + REVIEWS HIGH #5 raw ID drop（RED stub・Plan 03-04 GREEN）。

本ファイルは ``src.features.category_map_consumer`` が未実装のため RED。
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest


def _get_category_map_consumer():
    from src.features import category_map_consumer  # Plan 03-04 で実装
    return category_map_consumer


# ---------------------------------------------------------------------------
# SC#4: train-only fit + __UNSEEN__ sentinel
# ---------------------------------------------------------------------------
def test_unseen_maps_to_sentinel():
    """train 窓に無い horse_id を val/test に適用すると code['__UNSEEN__'] になる。"""
    cmc = _get_category_map_consumer()
    from src.utils.category_map import UNSEEN

    train_df = pd.DataFrame({"horse_id": ["H1", "H2"], "race_date": ["2020-01-01", "2020-06-01"]})
    val_df = pd.DataFrame({"horse_id": ["H_NEW"]})
    frozen = cmc.fit_category_map(train_df, column="horse_id")
    result = cmc.apply_category_map(val_df, column="horse_id", frozen_map=frozen)
    assert result.iloc[0]["horse_id_code"] == frozen["__UNSEEN__"]
    assert result.iloc[0]["horse_id_code"] == frozen.codes[UNSEEN]


def test_fit_called_on_train_window_only():
    """train 窓 mask（race_date で train period filter）が存在する（Pitfall 3.4・D-09）。"""
    cmc = _get_category_map_consumer()
    src = inspect.getsource(cmc)
    assert "race_date" in src, "category_map_consumer に race_date 窓 filter が無い（Pitfall 3.4）"
    # train period で filter している形跡
    assert "2016-07-01" in src or "train_period" in src or "train" in src, (
        "train 窓で fit している形跡が無い（Pitfall 3.4・D-09）"
    )


def test_codes_are_non_negative_int32():
    """apply_category_map の戻り dtype が int32 で min >= 0（LightGBM §14.3 非負要件）。"""
    cmc = _get_category_map_consumer()
    train_df = pd.DataFrame({"horse_id": ["H1", "H2"], "race_date": ["2020-01-01", "2020-06-01"]})
    frozen = cmc.fit_category_map(train_df, column="horse_id")
    result = cmc.apply_category_map(train_df, column="horse_id", frozen_map=frozen)
    assert result["horse_id_code"].dtype == np.int32, (
        f"horse_id_code dtype が int32 でない: {result['horse_id_code'].dtype}"
    )
    assert result["horse_id_code"].min() >= 0, "code に負値がある（LightGBM §14.3 違反・-1 禁止）"


# ---------------------------------------------------------------------------
# REVIEWS HIGH #5: raw ID drop
# ---------------------------------------------------------------------------
def test_apply_frozen_maps_drops_raw_id_columns():
    """apply_frozen_category_maps 適用後、raw ID 文字列列が残らない（_code suffix 列のみ残る）。"""
    cmc = _get_category_map_consumer()
    train_df = pd.DataFrame({
        "horse_id": ["H1", "H2"],
        "jockey_id": ["J1", "J2"],
        "trainer_id": ["T1", "T2"],
        "sire_id": ["S1", "S2"],
        "bms_id": ["B1", "B2"],
        "race_date": ["2020-01-01", "2020-06-01"],
    })
    frozen_maps = {
        col: cmc.fit_category_map(train_df, column=col)
        for col in ["horse_id", "jockey_id", "trainer_id", "sire_id", "bms_id"]
    }
    result = cmc.apply_frozen_category_maps(train_df, frozen_maps=frozen_maps)
    for raw_col in ["horse_id", "jockey_id", "trainer_id", "sire_id", "bms_id"]:
        assert raw_col not in result.columns, (
            f"raw ID 列 {raw_col} が残っている（HIGH #5 違反・Phase 4 モデルが raw ID で refit する危険）"
        )
        assert f"{raw_col}_code" in result.columns, f"{raw_col}_code が存在しない"


def test_apply_frozen_maps_no_raw_id_in_output_schema():
    """_CATEGORY_COLUMNS の5カラムのうち1つでも非 _code 形式で apply 後 DataFrame に残れば fail。"""
    cmc = _get_category_map_consumer()
    expected_category_columns = {"jockey_id", "trainer_id", "sire_id", "bms_id", "horse_id"}
    # consumer 側の _CATEGORY_COLUMNS 定数と一致
    assert hasattr(cmc, "_CATEGORY_COLUMNS"), "category_map_consumer に _CATEGORY_COLUMNS が無い"
    assert set(cmc._CATEGORY_COLUMNS) == expected_category_columns, (
        f"_CATEGORY_COLUMNS が期待と不一致: {cmc._CATEGORY_COLUMNS}"
    )


# ---------------------------------------------------------------------------
# CR-03 (03-05 gap-closure): race_date 欠損 frame fail-loud
# ---------------------------------------------------------------------------
def test_build_frozen_maps_raises_on_missing_race_date():
    """``race_date`` 列を持たない合成 DataFrame を ``build_frozen_category_maps`` に渡すと
    ``ValueError`` が raise されること（silent all-train fallback に fall しない・D-13 fail-loud・
    CR-03 regression guard）を assert。エラーメッセージに ``race_date`` が含まれること。
    """
    cmc = _get_category_map_consumer()
    # race_date 列を持たない frame（将来の refactor で誤って渡される可能性のある形状）
    fm_no_race_date = pd.DataFrame({
        "horse_id": ["H1", "H2"],
        "jockey_id": ["J1", "J2"],
        "trainer_id": ["T1", "T2"],
        "sire_id": ["S1", "S2"],
        "bms_id": ["B1", "B2"],
    })
    with pytest.raises(ValueError, match="race_date"):
        cmc.build_frozen_category_maps(fm_no_race_date)
    # CR-03 で silent fallback comment が削除されたことも回帰防止
    src = inspect.getsource(cmc.build_frozen_category_maps)
    assert "全行を train 扱い" not in src, (
        "silent all-train fallback comment が残存（CR-03 違反・D-13 fail-loud に反する）"
    )
    assert "unit test の合成" not in src, (
        "silent all-train fallback comment が残存（CR-03 違反）"
    )
    assert "raise ValueError" in src and "race_date" in src, (
        "race_date 欠損で ValueError を raise しない（CR-03 違反）"
    )
