"""Phase 4 predict: calibrated estimator → provenance 付き予測 DataFrame (MODL-01/D-05/D-10).

成功基準 #1 (SC#1) / §19.1 再現性聖域 / D-05 prediction provenance / D-10 model_version 採番 を
実装する service 層。

**設計の核心:**

本モジュールは ``calibrated_estimator.predict_proba(X)[:, 1]`` から ``p_fukusho_hit`` を
算出し、``prediction.fukusho_prediction`` テーブルの列順 (``PREDICTION_COLUMNS``) に整列した
provenance 付き DataFrame を構築する。provenance 5 列
(``model_type`` / ``model_version`` / ``feature_snapshot_id`` / ``as_of_datetime`` /
``calib_method``) は ``§19.1`` 再現性聖域であり、``_assert_valid_prediction_df`` で NOT NULL
と [0,1] 範囲を ValueError guard する。

**review HIGH#4 / Cross-Plan #1 / Cycle 3 NEW-4 (model_version 採番):**

``make_model_version`` は D-10 例と**完全一致**する形式
``{feature_snapshot_id}-{short}-v{N}`` を返す (例: ``20260620-1a-postreview-v2-lgb-v1``)。
``feature_snapshot_id`` 全体をそのまま prefix として使い、**再度 suffix を追加しない**
(snapshot_id が ``-v2`` 等で終わっても二重 postfix にならない)。後続 PLAN 05/06 と
artifact パス・prediction provenance・テストが全てこの形式に依存する。

**Cycle 2 NEW HIGH-1 (pred_proba 注入・CatBoost 行整列伝播):**

``predict_p_fukusho`` は ``pred_proba`` 引数 (None デフォルト) を受け取る。
``None`` の場合は ``calibrated_estimator.predict_proba(X)[:, 1]`` を算出 (LightGBM 標準パス・
X.index と予測順序は一致)。呼出側が ``np.ndarray`` または ``pd.Series`` で渡した場合は
それを直接使用し**再予測しない**。orchestrator が ``align_predictions`` で元行順序に復元済みの
CatBoost 予測値を注入することで、最終 DataFrame に行整列が伝播する。
``len(pred_proba) == len(X)`` と ``pred_proba.index.equals(X.index)`` (Series の場合) を
assert し、違反は ``RuntimeError`` (silent wrong-horse prediction 防止)。

**review MEDIUM (as_of_datetime 制御可能):**

``as_of_datetime`` 引数が ``None`` の場合は ``datetime.now(timezone.utc)`` を使用。
``reproduce smoke`` 等で bit-identical な hash を保証するためには固定値を渡すこと
(``T-04-25b``: 揮発性 ``now()`` が hash に混入するのを防止)。本モジュールは hash を
計算しないが、``prediction_load.py`` の checksum が ``as_of_datetime`` を含む全列で
計算されるため、呼出側で固定値を渡すことが §19.1 の前提。

参照: src/model/calibrator.py (CalibrationResult) /
      src/db/schema.py (PREDICTION_TABLE_DDL・11カラム PK) /
      04-RESEARCH.md D-05/D-10 / 04-PATTERNS.md predict.py セクション /
      04-04-PLAN.md Task 1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 定数 — schema.py PREDICTION_TABLE_DDL の列順と 1:1 (review HIGH#1: 11カラム PK)
# ---------------------------------------------------------------------------
# provenance (5) + PK RACE_KEY (7) + 予測値 (1) + 補助メタ (2) = 15 列
# schema.py の PREDICTION_TABLE_DDL の定義順と完全一致すること (prediction_load.py が
# この順序で INSERT する)。
PREDICTION_COLUMNS: list[str] = [
    # provenance (§19.1 再現性・NOT NULL)
    "model_type",
    "model_version",
    "feature_snapshot_id",
    "as_of_datetime",
    "calib_method",
    # PK RACE_KEY (label.fukusho_label と同一7カラム)
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "umaban",
    "kettonum",
    # 予測値
    "p_fukusho_hit",
    # 補助メタ (Phase 5/6/7 が参照)
    "race_date",
    "split",
]

# D-10 model_type → short mapping (review HIGH#4 / Cycle 3 NEW-4)
MODEL_TYPE_TO_SHORT: dict[str, str] = {
    "lightgbm": "lgb",
    "catboost": "cb",
    "logreg": "logreg",
}

# label.fukusho_label と同一の7カラム RACE_KEY PK
# (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)
PK_COLUMNS: list[str] = ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"]


# ---------------------------------------------------------------------------
# make_model_version — D-10 / review HIGH#4 / Cross-Plan #1 / Cycle 3 NEW-4
# ---------------------------------------------------------------------------


def make_model_version(
    feature_snapshot_id: str, model_type: str, version_n: int = 1
) -> str:
    """D-10 model_version 採番: ``{feature_snapshot_id}-{short}-v{N}`` 形式 (review HIGH#4).

    例:
      - ``make_model_version("20260620-1a-postreview-v2", "lightgbm", 1)``
        → ``"20260620-1a-postreview-v2-lgb-v1"``
      - ``make_model_version("20260620-1a-postreview-v2", "catboost", 1)``
        → ``"20260620-1a-postreview-v2-cb-v1"``

    **review HIGH#4 / Cycle 3 NEW-4 残渣解消:**
    ``feature_snapshot_id`` 全体をそのまま prefix として使う。snapshot_id が ``-v2`` 等の
    version suffix で終わっていても**再度 suffix を追加しない** (二重 postfix 防止)。
    旧版の ``"20260620-1a-postreview-v2-postreview-v2-lgb-v1"`` のような形式は絶対に
    出力しない。

    Parameters
    ----------
    feature_snapshot_id : str
        feature snapshot ID (例: ``"20260620-1a-postreview-v2"``)。全体を prefix に使う。
    model_type : str
        ``"lightgbm"`` / ``"catboost"`` / ``"logreg"``。``MODEL_TYPE_TO_SHORT`` で短縮形に変換。
    version_n : int
        モデルバージョン番号 (デフォルト 1)。バージョン bump は呼出側で管理 (手動・semver 的)。

    Returns
    -------
    str
        ``{feature_snapshot_id}-{short}-v{version_n}`` 形式の model_version 文字列。

    Raises
    ------
    ValueError
        ``model_type`` が ``MODEL_TYPE_TO_SHORT`` に未登録の時。
    """
    if model_type not in MODEL_TYPE_TO_SHORT:
        raise ValueError(
            f"未知の model_type: {model_type!r} "
            f"(expected one of {sorted(MODEL_TYPE_TO_SHORT.keys())})"
        )
    short = MODEL_TYPE_TO_SHORT[model_type]
    # review HIGH#4: feature_snapshot_id 全体をそのまま prefix・再 suffix 追加禁止
    return f"{feature_snapshot_id}-{short}-v{version_n}"


# ---------------------------------------------------------------------------
# predict_p_fukusho — calibrated estimator → provenance 付き予測 DataFrame
# ---------------------------------------------------------------------------


def predict_p_fukusho(
    calibrated_estimator: Any,
    X: pd.DataFrame,
    *,
    model_type: str,
    model_version: str,
    feature_snapshot_id: str,
    calib_method: str,
    race_df: pd.DataFrame,
    split_label: str,
    as_of_datetime: datetime | None = None,
    pred_proba: np.ndarray | pd.Series | None = None,
) -> pd.DataFrame:
    """calibrated estimator から provenance 付き予測 DataFrame を構築する (MODL-01/D-05/D-10).

    ``calibrated_estimator.predict_proba(X)[:, 1]`` から ``p_fukusho_hit`` を算出し、
    ``race_df`` (PK 7カラム + race_date + race_start_datetime) と結合して
    ``PREDICTION_COLUMNS`` 列順の DataFrame を返す。

    **Cycle 2 NEW HIGH-1 (pred_proba 注入):**
    ``pred_proba`` 引数が ``None`` の場合は ``calibrated_estimator.predict_proba(X)[:, 1]``
    を算出 (LightGBM 標準パス)。``np.ndarray`` / ``pd.Series`` で渡された場合はそれを
    直接使用し**再予測しない**。CatBoost のように呼出側で ``align_predictions`` により
    元行順序に復元済みの予測値を注入する用途 (orchestrator が整列を最終 DataFrame に伝播)。

    Parameters
    ----------
    calibrated_estimator : estimator
        ``.predict_proba(X)`` を持つ calibrated estimator (``CalibratedClassifierCV``・
        又は ``predict_proba`` を持つ任意の sklearn estimator)。``pred_proba=None`` の時に
        使用される。
    X : pd.DataFrame
        特徴量行列。index は ``race_df`` と一致すること。
    model_type : str
        ``"lightgbm"`` / ``"catboost"`` / ``"logreg"``。provenance 列。
    model_version : str
        ``make_model_version`` で採番した model_version 文字列。provenance 列。
    feature_snapshot_id : str
        feature snapshot ID。provenance 列。
    calib_method : str
        ``"isotonic"`` / ``"sigmoid"``。provenance 列。
    race_df : pd.DataFrame
        PK 7カラム (year/jyocd/kaiji/nichiji/racenum/umaban/kettonum) + ``race_date`` を
        持つ DataFrame。index は ``X`` と一致すること。
    split_label : str
        ``"train"`` / ``"calib"`` / ``"test"`` / ``"holdout_2025_plus"``。補助メタ列。
    as_of_datetime : datetime | None
        予測時刻。``None`` の場合は ``datetime.now(timezone.utc)``。
        reproduce smoke では固定値を渡して bit-identical を保証 (review MEDIUM / T-04-25b)。
    pred_proba : np.ndarray | pd.Series | None
        呼出側で事前算出・整列済みの予測確率 (クラス1)。``None`` の場合は
        ``calibrated_estimator.predict_proba(X)[:, 1]`` を算出。
        ``np.ndarray`` の場合は ``len == len(X)`` を assert し ``pd.Series(index=X.index)``
        に正規化。``pd.Series`` の場合は ``index.equals(X.index)`` を assert。
        違反は ``RuntimeError`` (silent wrong-horse prediction 防止・Cycle 2 NEW HIGH-1)。

    Returns
    -------
    pd.DataFrame
        ``PREDICTION_COLUMNS`` 列順の予測 DataFrame。index は ``X.index`` と一致。

    Raises
    ------
    ValueError
        provenance 列に NaN がある・``p_fukusho_hit`` が [0,1] 区間外・PK 11カラムで重複する時。
    RuntimeError
        ``pred_proba`` の長さ・index が ``X`` と一致しない時 (NEW HIGH-1)。
    """
    # --- pred_proba の取得 (NEW HIGH-1) ---
    if pred_proba is None:
        # LightGBM 標準パス: predict_proba[:, 1] を算出
        raw_pred = calibrated_estimator.predict_proba(X)[:, 1]
        pred_series = pd.Series(raw_pred, index=X.index, name="p_fukusho_hit")
    else:
        # 注入パス: 再予測せず注入値を使用 (CatBoost 行整列伝播)
        if isinstance(pred_proba, pd.Series):
            if not pred_proba.index.equals(X.index):
                raise RuntimeError(
                    "predict_p_fukusho: pred_proba.index does not match X.index "
                    "(Cycle 2 NEW HIGH-1: silent wrong-horse prediction prevented). "
                    f"pred_proba.index={list(pred_proba.index)[:5]}... "
                    f"X.index={list(X.index)[:5]}..."
                )
            pred_series = pred_proba.rename("p_fukusho_hit")
        elif isinstance(pred_proba, np.ndarray):
            if len(pred_proba) != len(X):
                raise RuntimeError(
                    f"predict_p_fukusho: pred_proba length {len(pred_proba)} != "
                    f"len(X) {len(X)} (Cycle 2 NEW HIGH-1: length mismatch prevented)."
                )
            pred_series = pd.Series(pred_proba, index=X.index, name="p_fukusho_hit")
        else:
            raise TypeError(
                f"predict_p_fukusho: pred_proba must be np.ndarray or pd.Series, "
                f"got {type(pred_proba).__name__}"
            )

    # --- as_of_datetime の確定 (review MEDIUM: 制御可能) ---
    if as_of_datetime is None:
        as_of_dt = datetime.now(timezone.utc)
    else:
        as_of_dt = as_of_datetime

    # --- race_df と予測の結合 ---
    # PK 7カラム + race_date を race_df から取得 (X.index と一致前提)
    needed_cols = PK_COLUMNS + ["race_date"]
    missing = [c for c in needed_cols if c not in race_df.columns]
    if missing:
        raise ValueError(
            f"predict_p_fukusho: race_df missing required columns: {missing}"
        )
    if not race_df.index.equals(X.index):
        raise ValueError(
            "predict_p_fukusho: race_df.index does not match X.index"
        )

    # --- 予測 DataFrame 構築 (PREDICTION_COLUMNS 列順) ---
    df = pd.DataFrame(index=X.index)
    df["model_type"] = model_type
    df["model_version"] = model_version
    df["feature_snapshot_id"] = feature_snapshot_id
    df["as_of_datetime"] = as_of_dt
    df["calib_method"] = calib_method
    for col in PK_COLUMNS:
        df[col] = race_df[col].values
    df["p_fukusho_hit"] = pred_series.values
    df["race_date"] = race_df["race_date"].values
    df["split"] = split_label

    # PREDICTION_COLUMNS 列順に整列
    df = df[list(PREDICTION_COLUMNS)]

    # 不変条件検証
    _assert_valid_prediction_df(df)

    return df


# ---------------------------------------------------------------------------
# _assert_valid_prediction_df — 予測 DataFrame の不変条件 (T-04-20)
# ---------------------------------------------------------------------------


def _assert_valid_prediction_df(df: pd.DataFrame) -> None:
    """予測 DataFrame の不変条件を検証する (T-04-20 / §19.1 / review HIGH#1).

    検証項目:
      1. 列順序が ``PREDICTION_COLUMNS`` と完全一致
      2. 5 provenance 列 (model_type/model_version/feature_snapshot_id/as_of_datetime/
         calib_method) が NOT NULL (NaN なし)
      3. ``p_fukusho_hit`` ∈ [0, 1]
      4. PK 11カラム (4 provenance + 7 RACE_KEY) で一意 (duplicated なし)

    Parameters
    ----------
    df : pd.DataFrame
        ``predict_p_fukusho`` の戻り DataFrame。

    Raises
    ------
    ValueError
        上記いずれかの不変条件に違反した時 (fail-loud・silent fallback 禁止)。
    """
    # 1. 列順序
    if list(df.columns) != list(PREDICTION_COLUMNS):
        raise ValueError(
            "_assert_valid_prediction_df: columns mismatch. "
            f"got={list(df.columns)}, expected={list(PREDICTION_COLUMNS)}"
        )

    # 2. provenance 列 NOT NULL
    provenance_cols = [
        "model_type",
        "model_version",
        "feature_snapshot_id",
        "as_of_datetime",
        "calib_method",
    ]
    for col in provenance_cols:
        nan_count = int(df[col].isna().sum())
        if nan_count > 0:
            raise ValueError(
                f"_assert_valid_prediction_df: provenance col {col!r} has "
                f"{nan_count} NaN (§19.1 再現性聖域違反 / T-04-20)"
            )

    # 3. p_fukusho_hit ∈ [0, 1]
    p = df["p_fukusho_hit"]
    if (p < 0).any() or (p > 1).any():
        raise ValueError(
            f"_assert_valid_prediction_df: p_fukusho_hit out of [0,1] range. "
            f"min={float(p.min())}, max={float(p.max())}"
        )

    # 4. PK 11カラムで一意
    pk_11 = (
        ["model_type", "model_version", "feature_snapshot_id", "as_of_datetime"]
        + PK_COLUMNS
    )
    dup_count = int(df.duplicated(subset=pk_11).sum())
    if dup_count > 0:
        raise ValueError(
            f"_assert_valid_prediction_df: PK 11 columns have {dup_count} duplicates "
            "(review HIGH#1: 11カラム PK 一意性違反)"
        )


__all__ = [
    "PREDICTION_COLUMNS",
    "MODEL_TYPE_TO_SHORT",
    "PK_COLUMNS",
    "make_model_version",
    "predict_p_fukusho",
    "_assert_valid_prediction_df",
]
