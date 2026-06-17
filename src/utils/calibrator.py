"""Prefit chronological calibrator（成功基準#4 / §15.2 / §15.3）。

時系列データでは確率校正で KFold shuffle による look-ahead leak を防ぐため、
訓練済み推定器を **再 fit せず** calibration slice のみで校正する（"prefit"・§15.2）。

**sklearn 1.9.0 API 変更への適合（plan 01-04 / 01-RESEARCH Example 5 からの deviation）:**
CLAUDE.md / 01-RESEARCH.md / 01-04-PLAN.md は ``CalibratedClassifierCV(cv='prefit')``
を前提としていたが、**sklearn 1.9.0 で ``cv='prefit'`` 文字列は削除された**
（``InvalidParameterError`` になる）。1.9.0 では代わりに
``sklearn.frozen.FrozenEstimator`` で訓練済み推定器をラップしてから
``CalibratedClassifierCV`` に渡すことが公式の prefit イディオムである
（1.9.0 docstring: "Already fitted classifiers can be calibrated by wrapping the
model in a FrozenEstimator. In this case all provided data is used for calibration.
The user has to take care manually that data for model fitting and calibration are
disjoint."）。

リーク防止セマンティクス（train/calib の disjoint をユーザーが手動保証）は不変。
本関数は ``raise ValueError`` guard で「calibration slice が train より厳格に未来」を
強制することで、その disjoint 保証を構造化する。

REVIEWS HIGH #3:
- リーク防止ガードは ``assert`` ではなく ``raise ValueError`` 形式。
  ``python -O`` 最適化実行で ``assert`` が削除されるのを防ぐ。
- ``train_max_date >= race_dates_calib.min()`` のとき ``raise ValueError`` する。

sklearn 1.9.0 では ``CalibratedClassifierCV`` は ``estimator=`` 引数を使用する
（legacy の ``base_estimator=`` は非推奨）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator


def fit_prefit_calibrator(
    base_estimator: Any,
    X_calib: np.ndarray,
    y_calib: np.ndarray,
    race_dates_calib: pd.Series,
    train_max_date: date | pd.Timestamp,
    method: str = "isotonic",
) -> CalibratedClassifierCV:
    """訓練済み推定器を calibration slice のみで時系列安全に確率校正する。

    calibration slice は訓練 slice より**厳格に未来**でなければならない
    （``max(train) < min(calib)``・strict ``<``）。等値は不可。違反時 ``raise ValueError``。

    Parameters
    ----------
    base_estimator : estimator
        既に TRAIN slice 上で ``.fit()`` 済みの推定器。本関数内で ``FrozenEstimator`` に
        ラップして ``CalibratedClassifierCV`` へ渡すため、calibration 時には再 fit されない
        （"prefit" セマンティクス）。
    X_calib : np.ndarray
        calibration slice の特徴量。
    y_calib : np.ndarray
        calibration slice のラベル。
    race_dates_calib : pd.Series
        calibration slice の各行に対応する ``race_date``（時系列順序検証用）。
    train_max_date : date | pd.Timestamp
        TRAIN slice の ``race_date`` 最大値。``race_dates_calib.min()`` より
        厳格に過去でなければならない。
    method : str
        ``"isotonic"`` または ``"sigmoid"``（sklearn 1.8+ は ``"temperature"`` も可）。
        CLAUDE.md §15.2 では calib サンプル >= 1000 で isotonic、< 1000 で sigmoid を推奨。
        デフォルト ``"isotonic"``。

    Returns
    -------
    CalibratedClassifierCV
        ``.fit(X_calib, y_calib)`` 済みの calibrator。内部の base estimator は
        ``FrozenEstimator`` でラップされており、calibration slice で再訓練されていない。

    Raises
    ------
    ValueError
        ``train_max_date >= race_dates_calib.min()`` のとき（calibration slice が
        train より厳格に未来でない = look-ahead leak・§15.2/D-17）。
    """
    # --- 時系列順序 guard（HIGH #3: assert ではなく raise ValueError） ---
    calib_min = pd.Timestamp(race_dates_calib.min())
    train_max_ts = pd.Timestamp(train_max_date)
    if not (train_max_ts < calib_min):
        raise ValueError(
            "calibration slice must be strictly later than training "
            f"(train_max={train_max_date}, calib_min={race_dates_calib.min()}); "
            "look-ahead leak prevented (§15.2/D-17, HIGH #3)"
        )

    # sklearn 1.9.0 prefit イディオム: FrozenEstimator でラップしてから CalibratedClassifierCV へ。
    # cv=None では KFold shuffle が走るが、FrozenEstimator は「既に fit 済み・再 fit しない」
    # セマンティクスを提供するため、calibration slice のみで校正が行われる。
    # （1.8 以前の cv='prefit' と等価。1.9.0 で cv='prefit' 文字列は削除された）
    frozen = FrozenEstimator(base_estimator)
    cal = CalibratedClassifierCV(estimator=frozen, method=method)
    cal.fit(X_calib, y_calib)
    return cal
