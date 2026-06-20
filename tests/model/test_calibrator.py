"""Phase 4 SC#4 / D-06 検証契約 (PLAN 02 GREEN 化).

検証内容:
- SC#4: strict-later disjoint (max(train) < min(calib)) 違反で calibrate_model が ValueError
- §15.2: calib sample >=1000 で isotonic・<1000 で sigmoid
- SC#4 reproduce smoke: seed=42 で2回 calibrate → predict_proba が np.array_equal (bit-identical)
- review HIGH#5 / D-06: artifact.py が CalibratedClassifierCV を base native + calibrator.joblib
  に分離保存し・load_native_artifact が真正再構築する
- Cycle 3 NEW-M1: test_artifact_save_load_roundtrip が np.allclose(rtol=1e-12, atol=1e-12) で
  保存前後 predict_proba 一致を検証（scikit-learn==1.9.0 pin を安定性保証）
- Cycle 3 NEW-L1: calibrator.joblib 欠落時 load_native_artifact が FileNotFoundError で fail-loud

trainer 未実装のため、base estimator は sklearn LogisticRegression / lightgbm 小モデルで代用
（docstring 明記・PLAN 05 で trainer 本体 + 3way 実データで再強化）。

参考: src/utils/calibrator.py::fit_prefit_calibrator (薄い wrapper が消費) /
      04-RESEARCH.md D-06 確定事項 / CLAUDE.md §15.2.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

from src.model.artifact import (
    load_native_artifact,
    save_native_artifact,
    write_metadata_json,
)
from src.model.calibrator import CalibrationResult, calibrate_model


def _make_base_and_data(n_train: int = 200, n_calib: int = 150, seed: int = 42):
    """合成データと fit 済み LogisticRegression base を生成する（trainer 未実装のため代用）.

    docstring: trainer.py が未実装のため sklearn LogisticRegression で代用。
    PLAN 05 で trainer 本体 + 3way 実データで再強化する。
    """
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n_train + n_calib, 4))
    y = (X[:, 0] + 0.5 * rng.normal(size=n_train + n_calib) > 0).astype(int)
    base = LogisticRegression(max_iter=1000, random_state=seed)
    base.fit(X[:n_train], y[:n_train])
    return base, X[n_train:], y[n_train:]


def _calib_dates(n: int, start: str = "2024-04-01") -> pd.Series:
    return pd.Series(pd.date_range(start, periods=n))


def test_strict_later_disjoint():
    """SC#4: max(train.race_date) >= min(calib.race_date) 違反で calibrate_model が ValueError.

    src/utils/calibrator.py が ValueError guard 内蔵済み・本テストは Phase 4 wrapper 経由で検証.
    正常入力 (train_max < calib_min) では CalibrationResult(calibrated, calib_method) を返す.
    """
    base, X_calib, y_calib = _make_base_and_data(n_train=200, n_calib=50)
    calib_dates = _calib_dates(50, "2024-04-01")

    # --- 違反ケース: train_max >= calib_min (等値) → ValueError ---
    with pytest.raises(ValueError, match="strictly later"):
        calibrate_model(
            base_estimator=base,
            X_calib=X_calib,
            y_calib=y_calib,
            race_dates_calib=calib_dates,
            train_max_date=date(2024, 4, 1),  # == calib.min() → 違反
        )

    # --- 違反ケース: train_max > calib_min → ValueError ---
    with pytest.raises(ValueError, match="strictly later"):
        calibrate_model(
            base_estimator=base,
            X_calib=X_calib,
            y_calib=y_calib,
            race_dates_calib=calib_dates,
            train_max_date=date(2024, 5, 1),  # > calib.min() → 違反
        )

    # --- 正常ケース: train_max < calib_min → CalibrationResult を返す ---
    result = calibrate_model(
        base_estimator=base,
        X_calib=X_calib,
        y_calib=y_calib,
        race_dates_calib=calib_dates,
        train_max_date=date(2024, 3, 31),  # < calib.min() → 正常
    )
    assert isinstance(result, CalibrationResult), (
        f"戻り値が CalibrationResult でない: {type(result)}"
    )
    assert isinstance(result.calibrated, CalibratedClassifierCV), (
        f"calibrated が CalibratedClassifierCV でない: {type(result.calibrated)}"
    )
    assert result.calib_method in {"isotonic", "sigmoid"}, (
        f"calib_method が isotonic/sigmoid 以外: {result.calib_method!r}"
    )


def test_isotonic_vs_sigmoid_threshold():
    """§15.2: calib sample >=1000 で isotonic・<1000 で sigmoid が選択される.

    合成 DataFrame で境界 999/1000 を検証。
    """
    base_999, X_999, y_999 = _make_base_and_data(n_train=50, n_calib=999)
    base_1000, X_1000, y_1000 = _make_base_and_data(n_train=50, n_calib=1000)

    # 999 行 → sigmoid
    result_999 = calibrate_model(
        base_estimator=base_999,
        X_calib=X_999,
        y_calib=y_999,
        race_dates_calib=_calib_dates(999, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )
    assert result_999.calib_method == "sigmoid", (
        f"999 行で sigmoid が選択されない: {result_999.calib_method!r}"
    )

    # 1000 行 → isotonic
    result_1000 = calibrate_model(
        base_estimator=base_1000,
        X_calib=X_1000,
        y_calib=y_1000,
        race_dates_calib=_calib_dates(1000, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )
    assert result_1000.calib_method == "isotonic", (
        f"1000 行で isotonic が選択されない: {result_1000.calib_method!r}"
    )


def test_reproduce_bit_identical():
    """SC#4 reproduce smoke: seed=42 で2回 calibrate → predict_proba が bit-identical.

    docstring: trainer.py が未実装のため sklearn LogisticRegression で代用。
    PLAN 05 で trainer 本体 (LightGBM/CatBoost) + 3way 実データで再強化する。

    固定 seed 全箇所 (LightGBM: seed/deterministic/force_col_wise/bagging_seed/
    feature_fraction_seed/num_threads=1, CatBoost: random_seed/has_time/thread_count=1) +
    固定 as_of_datetime (FIXED_REPRODUCE_TS) は trainer 実装時に検証する（本 test は
    calibrate_model の決定論性のみ）。
    """
    base1, X_calib1, y_calib1 = _make_base_and_data(n_train=200, n_calib=150, seed=42)
    base2, X_calib2, y_calib2 = _make_base_and_data(n_train=200, n_calib=150, seed=42)

    result1 = calibrate_model(
        base_estimator=base1,
        X_calib=X_calib1,
        y_calib=y_calib1,
        race_dates_calib=_calib_dates(150, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )
    result2 = calibrate_model(
        base_estimator=base2,
        X_calib=X_calib2,
        y_calib=y_calib2,
        race_dates_calib=_calib_dates(150, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )

    # 同一 X で predict_proba が bit-identical
    rng = np.random.default_rng(99)
    X_eval = rng.normal(size=(20, 4))
    proba1 = result1.calibrated.predict_proba(X_eval)[:, 1]
    proba2 = result2.calibrated.predict_proba(X_eval)[:, 1]
    assert np.array_equal(proba1, proba2), (
        "seed=42 で2回 calibrate した predict_proba が bit-identical でない (SC#4 reproduce 違反)"
    )


def test_artifact_save_load_roundtrip(tmp_path):
    """review HIGH#5 / D-06: CalibratedClassifierCV を base + calibrator.joblib に分離保存し
    load_native_artifact で真正再構築する。

    Cycle 3 NEW-M1: np.allclose(rtol=1e-12, atol=1e-12) で保存前後 predict_proba 一致を検証
    （scikit-learn==1.9.0 pin を安定性保証・pin 破壊で即時 RED）。
    Cycle 2 NEW-5: native base ファイルから base estimator を真正読込し再構築。
    Cycle 3 NEW-L1: calibrator.joblib 欠落時 FileNotFoundError で fail-loud。
    """
    # --- 合成 CalibratedClassifierCV (sklearn LogisticRegression base・isotonic) ---
    base, X_calib, y_calib = _make_base_and_data(n_train=200, n_calib=1500, seed=42)
    result = calibrate_model(
        base_estimator=base,
        X_calib=X_calib,
        y_calib=y_calib,
        race_dates_calib=_calib_dates(1500, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )
    assert result.calib_method == "isotonic", "1500 行 → isotonic 期待"

    out_dir = tmp_path / "test-model-v1"
    save_native_artifact(
        calibrated_estimator=result.calibrated,
        base_model_type="sklearn",
        model_version="test-model-v1",
        feature_snapshot_id="20260620-1a-postreview-v2",
        hyperparams={"C": 1.0, "max_iter": 1000},
        seed=42,
        train_calib_test_periods={
            "train": "2016-07-01/2023-12-31",
            "calib": "2024-01-01/2024-06-30",
            "test": "2024-07-01/2024-12-31",
        },
        calib_method=result.calib_method,
        out_dir=out_dir,
    )

    # --- base native + calibrator.joblib + metadata.json の3形式が作成されたことを検証 ---
    assert (out_dir / "sklearn_base.joblib").exists(), "sklearn_base.joblib が作成されていない"
    assert (out_dir / "calibrator.joblib").exists(), "calibrator.joblib が作成されていない"
    assert (out_dir / "metadata.json").exists(), "metadata.json が作成されていない"

    # --- metadata.json の中身検証 ---
    import json

    with (out_dir / "metadata.json").open() as f:
        meta = json.load(f)
    assert meta["base_model_type"] == "sklearn"
    assert meta["calib_method"] == "isotonic"
    assert meta["feature_snapshot_id"] == "20260620-1a-postreview-v2"
    assert meta["seed"] == 42
    assert "sklearn_base.joblib" in " ".join(meta["saved_components"]), (
        f"saved_components に sklearn_base が無い: {meta['saved_components']}"
    )
    assert "calibrator.joblib" in " ".join(meta["saved_components"]), (
        f"saved_components に calibrator.joblib が無い: {meta['saved_components']}"
    )

    # --- load_native_artifact で真正再構築 ---
    loaded = load_native_artifact(
        base_model_type="sklearn",
        model_version="test-model-v1",
        out_dir=out_dir,
    )

    # --- Cycle 3 NEW-M1: 固定許容誤差で保存前後 predict_proba 一致を検証 ---
    rng = np.random.default_rng(7)
    X_eval = rng.normal(size=(30, 4))
    saved_proba = result.calibrated.predict_proba(X_eval)[:, 1]
    loaded_proba = loaded.predict_proba(X_eval)[:, 1]
    assert np.allclose(saved_proba, loaded_proba, rtol=1e-12, atol=1e-12), (
        "保存前後の predict_proba が固定許容誤差 (rtol=1e-12, atol=1e-12) 内で一致しない "
        "(Cycle 3 NEW-M1: scikit-learn==1.9.0 pin 破壊または API 変更の可能性)"
    )


def test_artifact_calibrator_joblib_required(tmp_path):
    """Cycle 3 NEW-L1: calibrator.joblib 欠落時 load_native_artifact が FileNotFoundError で fail-loud.

    native base 単独での再構築は不可（isotonic 閾値/sigmoid 係数が必要・物理的に不可能）。
    """
    base, X_calib, y_calib = _make_base_and_data(n_train=200, n_calib=1500, seed=42)
    result = calibrate_model(
        base_estimator=base,
        X_calib=X_calib,
        y_calib=y_calib,
        race_dates_calib=_calib_dates(1500, "2024-04-01"),
        train_max_date=date(2024, 3, 31),
    )
    out_dir = tmp_path / "missing-calib-v1"
    save_native_artifact(
        calibrated_estimator=result.calibrated,
        base_model_type="sklearn",
        model_version="missing-calib-v1",
        feature_snapshot_id="20260620-1a-postreview-v2",
        hyperparams={},
        seed=42,
        train_calib_test_periods={},
        calib_method=result.calib_method,
        out_dir=out_dir,
    )

    # calibrator.joblib を削除 → load_native_artifact が FileNotFoundError
    (out_dir / "calibrator.joblib").unlink()
    with pytest.raises(FileNotFoundError, match="calibrator.joblib"):
        load_native_artifact(
            base_model_type="sklearn",
            model_version="missing-calib-v1",
            out_dir=out_dir,
        )


def test_artifact_metadata_json_is_sorted(tmp_path):
    """T-04-12: metadata.json が sort_keys=True で書かれる（byte-reproducible）。"""
    import json

    out_dir = tmp_path / "sort-test"
    out_dir.mkdir(parents=True)
    meta = {
        "zebra": "last",
        "apple": "first",
        "mango": "middle",
        "saved_components": ["calibrator.joblib", "sklearn_base.joblib"],
    }
    path = write_metadata_json(out_dir, meta)
    raw = path.read_text(encoding="utf-8")
    # sort_keys=True で書かれているか raw テキストのキー順で確認
    keys_in_file = [
        line.split('"')[1]
        for line in raw.splitlines()
        if line.strip().startswith('"') and '":' in line
    ]
    assert keys_in_file == sorted(keys_in_file), (
        f"metadata.json が sort_keys=True で書かれていない: {keys_in_file}"
    )
    # 読込んで内容一致
    with path.open() as f:
        loaded = json.load(f)
    assert loaded == meta, f"metadata.json の内容が不正: {loaded}"
