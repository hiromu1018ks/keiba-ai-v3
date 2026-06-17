"""src/utils/category_map.py の smoke テスト（成功基準#4 / §14.3 / §14.5）。

frozen category map の fit/apply が以下を満たすことを検証する:
- 訓練窓 series のみで fit し、未知値は __UNSEEN__・欠損は __MISSING__ にフォールバック
- 戻り値は非負 int32（pandas の category code -1 ハザード回避・§14.3）
"""

from __future__ import annotations

import pandas as pd

from src.utils.category_map import MISSING, UNSEEN, apply_category_map, fit_category_map


def test_fit_returns_unseen_missing():
    """fit_category_map が __UNSEEN__ と __MISSING__ の両方をキーに持つ。"""
    code = fit_category_map(pd.Series(["a", "b", "a"]))
    assert UNSEEN in code, f"{UNSEEN} が code に存在しない: {code}"
    assert MISSING in code, f"{MISSING} が code に存在しない: {code}"
    # a, b の2値が 0, 1 に割当
    assert code["a"] == 0
    assert code["b"] == 1
    # __UNSEEN__ と __MISSING__ は別のコード
    assert code[UNSEEN] != code[MISSING], (
        f"{UNSEEN} と {MISSING} が同じコード（§14.5 欠損理由区別違反）"
    )


def test_fit_handles_nan():
    """fit 時の NaN は訓練窓のカテゴリとはならず __MISSING__ のみに集約される。"""
    code = fit_category_map(pd.Series(["a", None, "b"]))
    assert "a" in code and "b" in code
    assert "nan" not in code, "NaN が str(nan)='nan' としてカテゴリ化されてしまった"


def test_apply_unseen_fallback():
    """apply で未知値 'c' を渡すと code[__UNSEEN__] が返る（§14.3）。"""
    code = fit_category_map(pd.Series(["a", "b"]))
    out = apply_category_map(pd.Series(["a", "b", "c"]), code)
    assert out.iloc[2] == code[UNSEEN], (
        f"未知値 'c' が {UNSEEN}={code[UNSEEN]} にフォールバックされていない: {out.tolist()}"
    )


def test_apply_missing_fallback():
    """apply で NaN を渡すと code[__MISSING__] が返る（NaN→-1 禁止・§14.3/§14.5）。"""
    code = fit_category_map(pd.Series(["a", "b"]))
    out = apply_category_map(pd.Series(["a", None]), code)
    assert out.iloc[1] == code[MISSING], (
        f"NaN が {MISSING}={code[MISSING]} にフォールバックされていない: {out.tolist()}"
    )
    assert out.iloc[1] != -1, "NaN が code -1 になった（LightGBM ハザード・§14.3 違反）"


def test_non_negative_int32():
    """apply の戻り値 dtype が int32 で min >= 0。"""
    code = fit_category_map(pd.Series(["a", "b", "c"]))
    out = apply_category_map(pd.Series(["a", "b", "c", "unknown", None]), code)
    assert str(out.dtype) == "int32", f"dtype が int32 ではない: {out.dtype}"
    assert out.min() >= 0, f"非負でない値がある: {out.tolist()}"
    assert (out < 0).sum() == 0


def test_apply_preserves_order():
    """apply は series の行順を保ち、既知値は code 通りの int を返す。"""
    code = fit_category_map(pd.Series(["x", "y", "z"]))
    out = apply_category_map(pd.Series(["z", "x", "y"]), code)
    assert out.tolist() == [code["z"], code["x"], code["y"]]
