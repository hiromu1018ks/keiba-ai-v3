"""Frozen category map の fit/apply（成功基準#4 / §14.3 / §14.5）。

訓練窓（train window）でのみ ``fit_category_map`` を呼び出して安定なカテゴリ→コード
マップを構築し、val/test には ``apply_category_map`` で**再 fit せず**適用する。

CLAUDE.md §14.3 LightGBM native categorical handling の要点:
- 高基数 ID（jockey_id/horse_id/sire_id）は ``feature_snapshot_id`` 毎に**安定・frozen** な
  カテゴリ map を訓練窓で fit し、同一 map を val/test に適用する。
- 予測時未知の ID は専用の ``__UNSEEN__`` カテゴリへ（NaN ではない）。
- 欠損は ``__MISSING__`` カテゴリで明示的に区別する（§14.5 欠損理由区別）。
- pandas の ``category`` dtype は NaN をコード -1 にするハザードがあるため、
  ``apply_category_map`` は ``.astype("int32")`` で**非負**を保証する。
"""

from __future__ import annotations

import pandas as pd

# sentinel カテゴリ（§14.3 / §14.5）
UNSEEN = "__UNSEEN__"
MISSING = "__MISSING__"


def fit_category_map(series: pd.Series) -> dict[str, int]:
    """訓練窓 series から frozen category map を構築する。

    **必ず訓練窓（train window）でのみ呼び出すこと**（§14.3・test 構成リーク防止）。
    val/test の series を渡してはならない。未知/欠損は ``apply_category_map`` 側で
    機械的に sentinel へフォールバックする。

    Parameters
    ----------
    series : pd.Series
        訓練窓の categorical series（str 推奨）。NaN は訓練窓のカテゴリとはならず
        ``__MISSING__`` sentinel のみで扱う。

    Returns
    -------
    dict[str, int]
        カテゴリ値（str 化済）→ 非負 int の map。末尾に ``__UNSEEN__`` と
        ``__MISSING__`` の sentinel エントリを含む。両 sentinel は異なるコードを持つ
        （§14.5 欠損理由区別）。
    """
    cats = sorted(series.dropna().astype(str).unique().tolist())
    code: dict[str, int] = {c: i for i, c in enumerate(cats)}
    # 未知 ID 用 sentinel（train 構成に現れなかった ID はここへ）
    code[UNSEEN] = len(code)
    # 欠損理由区別用 sentinel（§14.5・__UNSEEN__ とは別コード）
    code[MISSING] = len(code)
    return code


def apply_category_map(series: pd.Series, code: dict[str, int]) -> pd.Series:
    """frozen category map を val/test に適用する。

    **再 fit しないこと**（``code`` は ``fit_category_map`` の戻り値をそのまま渡す）。
    未知値は ``__UNSEEN__``・欠損は ``__MISSING__`` へ機械的にフォールバックする。
    戻り値は**非負 int32** の pd.Series（pandas の category code -1 ハザード回避・§14.3）。

    Parameters
    ----------
    series : pd.Series
        適用対象の categorical series（val/test）。未知値・NaN を含んでよい。
    code : dict[str, int]
        ``fit_category_map`` で構築した frozen map。

    Returns
    -------
    pd.Series
        非負 int32 のコード系列。NaN → ``code[MISSING]``、未知 → ``code[UNSEEN]``。
        ``-1`` は絶対に返さない（LightGBM の非負要件・§14.3）。
    """
    # NaN を __MISSING__ sentinel 文字列に置換してから str 化
    s = series.astype(str).where(series.notna(), MISSING)
    # map 適用。code に無い値（未知）は NaN になるので __UNSEEN__ で fillna
    return s.map(code).fillna(code[UNSEEN]).astype("int32")
