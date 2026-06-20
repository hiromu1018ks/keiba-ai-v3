"""Phase 4 model calibrator: prefit wrapper + isotonic/sigmoid 切替.

成功基準#4 (SC#4) / §15.2 / D-06 を実装する service 層。

**設計の核心（review HIGH#5 ではないが SC#4 再現性聖域）:**

本モジュールは ``src/utils/calibrator.py::fit_prefit_calibrator`` を**薄く wrap するのみ**
（PATTERNS.md calibrator.py セクション）。リーク防止プリミティブ（strict-later ValueError
guard + ``FrozenEstimator`` + ``CalibratedClassifierCV``）は既存関数が内蔵済みであり、
本モジュールは**再実装しない**。

本モジュールが追加する唯一のロジック: ``§15.2`` 推奨に従い calib sample 件数で
``method`` を切替える:

  - calib sample >= 1000 → ``method="isotonic"``（isotonic regression は大样本で安定）
  - calib sample <  1000 → ``method="sigmoid"``（isotonic は <1000 で過学習）

戻り値は ``CalibrationResult`` NamedTuple（``calibrated`` + ``calib_method``）で、
``calib_method`` は ``predict.py`` が ``prediction.fukusho_prediction.calib_method`` 列に
書込む provenance として使用する（§19.1 再現性）。

参照: src/utils/calibrator.py / 04-RESEARCH.md Pattern 4 FrozenEstimator prefit /
      04-PATTERNS.md calibrator.py セクション.
"""

from __future__ import annotations

from datetime import date
from typing import Any, NamedTuple

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from src.utils.calibrator import fit_prefit_calibrator


class CalibrationResult(NamedTuple):
    """``calibrate_model`` の戻り値。

    Attributes
    ----------
    calibrated : CalibratedClassifierCV
        ``.fit(X_calib, y_calib)`` 済みの calibrator。内部の base estimator は
        ``FrozenEstimator`` でラップされており、calibration slice で再訓練されていない
        （"prefit" セマンティクス・§15.2）。
    calib_method : str
        使用した calibration method (``"isotonic"`` または ``"sigmoid"``)。
        ``predict.py`` が ``prediction.fukusho_prediction.calib_method`` 列に書込む
        provenance（§19.1 再現性）。
    """

    calibrated: CalibratedClassifierCV
    calib_method: str


def calibrate_model(
    base_estimator: Any,
    X_calib: np.ndarray,
    y_calib: np.ndarray,
    race_dates_calib: pd.Series,
    train_max_date: date | pd.Timestamp,
) -> CalibrationResult:
    """訓練済み推定器を calibration slice のみで時系列安全に確率校正する（SC#4・§15.2）。

    ``src.utils.calibrator.fit_prefit_calibrator`` を**再実装せず薄く wrap する**
    （PATTERNS.md calibrator.py セクション・リーク防止プリミティブは既存契約を消費）。

    ``§15.2`` 推奨に従い calib sample 件数で ``method`` を切替える:

      - ``len(X_calib) >= 1000`` → ``method="isotonic"``
      - ``len(X_calib) <  1000`` → ``method="sigmoid"``（isotonic は <1000 で過学習）

    strict-later disjoint guard（``train_max_date < race_dates_calib.min()``・strict ``<``）
    は ``fit_prefit_calibrator`` が内蔵済み（``raise ValueError``・``python -O`` で生存）。
    違反時は本関数経由で ``ValueError`` が伝播する。

    Parameters
    ----------
    base_estimator : estimator
        既に TRAIN slice 上で ``.fit()`` 済みの推定器。``fit_prefit_calibrator`` 内で
        ``FrozenEstimator`` にラップして ``CalibratedClassifierCV`` へ渡すため、
        calibration 時には再 fit されない（"prefit" セマンティクス）。
    X_calib : np.ndarray
        calibration slice の特徴量。
    y_calib : np.ndarray
        calibration slice のラベル。
    race_dates_calib : pd.Series
        calibration slice の各行に対応する ``race_date``（時系列順序検証用）。
    train_max_date : date | pd.Timestamp
        TRAIN slice の ``race_date`` 最大値。``race_dates_calib.min()`` より
        厳格に過去でなければならない（strict ``<``・等値不可）。

    Returns
    -------
    CalibrationResult
        ``calibrated`` (``CalibratedClassifierCV``) + ``calib_method`` (``str``)。

    Raises
    ------
    ValueError
        ``train_max_date >= race_dates_calib.min()`` のとき（``fit_prefit_calibrator``
        経由・look-ahead leak prevented・§15.2/D-17）。
    """
    # §15.2: calib sample 件数で isotonic/sigmoid を切替える（再実装禁止の唯一追加ロジック）
    calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"
    calibrated = fit_prefit_calibrator(
        base_estimator=base_estimator,
        X_calib=X_calib,
        y_calib=y_calib,
        race_dates_calib=race_dates_calib,
        train_max_date=train_max_date,
        method=calib_method,
    )
    return CalibrationResult(calibrated=calibrated, calib_method=calib_method)
