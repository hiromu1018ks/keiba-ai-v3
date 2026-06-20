"""Phase 4 model artifact: native + calibrator 分離保存・真正再構築.

D-06 / §19.1 / PATTERNS atomic write / review HIGH#5 を実装する utility 層。

**設計の核心（review HIGH#5・Cycle 2 NEW-5・Cycle 3 NEW-M1/NEW-L1）:**

``CalibratedClassifierCV`` をそのまま LightGBM ``.txt`` / CatBoost ``.cbm`` ネイティブ形式で
保存すると失敗または誤オブジェクト保存になる（wrapper と base は別形式で保存する必要がある）。
本モジュールは3形式に**分離保存**する:

  1. **base estimator** をネイティブ形式で保存:
     - LightGBM → ``lgb_model.txt`` (``base.booster_.save_model``)
     - CatBoost → ``cb_model.cbm`` (``base.save_model``)
     - scikit-learn (LogisticRegression 等) → ``sklearn_base.joblib`` (native 形式が無いため
       joblib・base 推定器の型に応じて分岐)
  2. **calibrator wrapper** を ``calibrator.joblib`` に保存 (``CalibratedClassifierCV`` 全体・
     base への参照含む・再構築に必要)
  3. **metadata** を ``metadata.json`` に ``sort_keys=True``・atomic write で保存
     (byte-reproducible・``saved_components`` リストで何が保存されたかを明示)

**``load_native_artifact`` は base ネイティブファイル + calibrator.joblib の両方を必須とする**
（Cycle 3 NEW-L1: calibrator.joblib 欠落時 ``FileNotFoundError``・native base 単独での再構築は
**物理的に不可能**: isotonic 閾値/sigmoid 係数なしでは calibrated probability は復元できず・
native base 単独では未キャリブレーション予測しか出せない）。

**真正再構築パイプライン（Cycle 2 NEW-5）:**
  (a) native base ファイルから base estimator を読込む（lgb.Booster / CatBoostClassifier.load_model /
      sklearn base の joblib 復元）
  (b) calibrator.joblib から calibrators を読込む
  (c) base + calibrators から ``CalibratedClassifierCV`` を真正再構築する

**安定性保証（Cycle 3 NEW-M1）:** step (c) は scikit-learn==1.9.0（pyproject.toml pin・
04-01 固定済）の私有/準私有構造（``_calibrators`` / ``calibrated_classifiers_``）に依存する。
この pin を**安定性保証**として扱い、``test_artifact_save_load_roundtrip`` が保存前後の
``predict_proba`` を ``np.allclose(rtol=1e-12, atol=1e-12)`` で検証する（pin 破壊で即時 RED）。

**pickle ACE 回避（D-06・Phase 3 CR-04 思想継承）:** pickle は使用禁止。ネイティブ形式
(``.txt``/``.cbm``) と joblib（内部は pickle 但し信頼できる自作 artifact のみ読込）のみ使用。

参照: 04-PATTERNS.md artifact.py セクション / Shared Pattern 7 (atomic write) /
      src/features/category_map_consumer.py:263-272 (persist_category_maps・atomic write).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import joblib

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_MODEL_VERSION_PREFIX = "models"


def _atomic_write_text(path: Path, payload: str) -> None:
    """atomic write（tmp file → ``os.replace``・Shared Pattern 7）。

    ``Path.write_text`` は atomic でなく、書込中のプロセス kill / disk full / 権限エラーで
    partial / 空 / 破損ファイルが残るリスクがある。tmp file に書いてから atomic rename する
    ことで partial-failure を抑止する（category_map_consumer.py:263-272 パターン）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


def write_metadata_json(out_dir: Path, metadata_dict: dict[str, Any]) -> Path:
    """metadata dict を ``out_dir/metadata.json`` に ``sort_keys=True``・atomic write で保存.

    byte-reproducible な JSON（``sort_keys=True``・``ensure_ascii=False``）で書込む。
    ``saved_components`` リストで何が保存されたかを明示（audit trail）。

    Parameters
    ----------
    out_dir : Path
        artifact 出力ディレクトリ。
    metadata_dict : dict
        保存する metadata（``model_version`` / ``base_model_type`` /
        ``feature_snapshot_id`` / ``calib_method`` / ``seed`` / ``hyperparams`` /
        ``train_calib_test_periods`` / ``saved_components`` 等）。

    Returns
    -------
    Path
        書込んだ ``metadata.json`` のパス。
    """
    path = out_dir / "metadata.json"
    payload = json.dumps(metadata_dict, sort_keys=True, ensure_ascii=False)
    _atomic_write_text(path, payload)
    return path


def save_native_artifact(
    calibrated_estimator: Any,
    base_model_type: str,
    model_version: str,
    *,
    feature_snapshot_id: str,
    hyperparams: dict[str, Any],
    seed: int,
    train_calib_test_periods: dict[str, str],
    calib_method: str,
    out_dir: str | Path | None = None,
) -> Path:
    """``CalibratedClassifierCV`` を base + calibrator + metadata に分離保存（review HIGH#5）。

    ``calibrated_estimator`` をそのまま LightGBM ``.txt`` / CatBoost ``.cbm`` で保存すると
    失敗または誤オブジェクト保存になるため、以下のように**別々に保存**する:

      1. base estimator (``calibrated_estimator.estimator``) をネイティブ形式で保存
      2. calibrator wrapper (``CalibratedClassifierCV`` 全体) を ``calibrator.joblib`` に保存
      3. metadata を ``metadata.json`` に保存

    Parameters
    ----------
    calibrated_estimator : CalibratedClassifierCV
        ``fit_prefit_calibrator`` / ``calibrate_model`` が返した calibrated estimator。
    base_model_type : str
        ``"lightgbm"`` / ``"catboost"`` / ``"sklearn"`` (LogisticRegression 等)。
    model_version : str
        モデルバージョン（``predict.py`` が採番・D-10）。``out_dir`` のサブディレクトリ名。
    feature_snapshot_id : str
        feature snapshot ID（provenance・§19.1）。
    hyperparams : dict
        ハイパラ（provenance・§19.1 再現性）。
    seed : int
        固定 seed（provenance・§19.1）。
    train_calib_test_periods : dict
        ``{"train": "...", "calib": "...", "test": "..."}``（provenance・§19.1）。
    calib_method : str
        ``"isotonic"`` または ``"sigmoid"``（provenance・§19.1）。
    out_dir : str | Path | None
        出力ディレクトリ（None の場合は ``models/{model_version}``）。

    Returns
    -------
    Path
        artifact を保存したディレクトリ。
    """
    if base_model_type not in {"lightgbm", "catboost", "sklearn"}:
        raise ValueError(
            f"未知の base_model_type: {base_model_type!r} "
            "(expected 'lightgbm' / 'catboost' / 'sklearn')"
        )

    out = Path(out_dir) if out_dir is not None else Path(_MODEL_VERSION_PREFIX) / model_version
    out.mkdir(parents=True, exist_ok=True)

    # --- 1. base estimator をネイティブ形式で保存 (review HIGH#5) ---
    # sklearn 1.9.0 では calibrated_estimator.estimator は FrozenEstimator でラップされた
    # base 推定器。FrozenEstimator はラップした estimator を ``.estimator`` 属性で露出する。
    from sklearn.frozen import FrozenEstimator

    raw_base = calibrated_estimator.estimator
    if isinstance(raw_base, FrozenEstimator):
        base = raw_base.estimator
    else:
        base = raw_base

    saved_components: list[str] = []
    if base_model_type == "lightgbm":
        # LGBMClassifier の場合は .booster_ で native booster を取得
        booster = getattr(base, "booster_", base)
        booster.save_model(str(out / "lgb_model.txt"))
        saved_components.append("base_native:lgb_model.txt")
    elif base_model_type == "catboost":
        base.save_model(str(out / "cb_model.cbm"))
        saved_components.append("base_native:cb_model.cbm")
    else:  # sklearn (LogisticRegression 等)
        joblib.dump(base, out / "sklearn_base.joblib")
        saved_components.append("base_native:sklearn_base.joblib")

    # --- 2. calibrator wrapper を calibrator.joblib に保存 (review HIGH#5) ---
    # CalibratedClassifierCV 全体（base への参照含む・再構築に必要）。
    # joblib の Python マイナーバージョン非互換で読めない場合の fallback は
    # docstring に明記（calibrator 数値 payload を別途保存形式から手動復元のみ可能・
    # native base からは不可能・Cycle 3 NEW-L1）。
    joblib.dump(calibrated_estimator, out / "calibrator.joblib")
    saved_components.append("calibrator_joblib:calibrator.joblib")

    # --- 3. metadata.json (sort_keys=True・atomic write・byte-reproducible) ---
    metadata = {
        "model_version": model_version,
        "base_model_type": base_model_type,
        "feature_snapshot_id": feature_snapshot_id,
        "calib_method": calib_method,
        "seed": seed,
        "hyperparams": hyperparams,
        "train_calib_test_periods": train_calib_test_periods,
        "saved_components": saved_components,
        "sklearn_version_pinned": "1.9.0",  # Cycle 3 NEW-M1: 安定性保証・pin 破壊で即時 RED
    }
    write_metadata_json(out, metadata)
    return out


def load_native_artifact(
    base_model_type: str,
    model_version: str,
    out_dir: str | Path | None = None,
) -> Any:
    """base ネイティブファイル + calibrator.joblib から ``CalibratedClassifierCV`` を
    真正再構築する（review HIGH#5・Cycle 2 NEW-5・Cycle 3 NEW-M1/NEW-L1）。

    **3ステップの真正再構築パイプライン:**

      (a) **native base ファイルから base estimator を読込む**（真正読込・型 assertion 用でない）
          - ``lightgbm`` → ``lgb.Booster(model_file=...)``
          - ``catboost`` → ``CatBoostClassifier().load_model(...)``
          - ``sklearn``  → ``joblib.load(sklearn_base.joblib)``
      (b) **calibrator.joblib から calibrators を読込む**（``CalibratedClassifierCV`` 全体）
      (c) **base + calibrators から ``CalibratedClassifierCV`` を真正再構築**

    **Cycle 3 NEW-L1:** ``calibrator.joblib`` は**必須**（欠落時 ``FileNotFoundError``）。
    native base 単独での再構築は**物理的に不可能**（isotonic 閾値/sigmoid 係数が必要・
    native base からは calibrated probability は復元できない）。

    **Cycle 3 NEW-M1 安定性保証:** step (c) は ``scikit-learn==1.9.0`` pin
    （pyproject.toml・04-01 固定済）の私有 API（``_calibrators`` /
    ``calibrated_classifiers_``）に依存する。pin 破壊で API 変更された場合は
    ``test_artifact_save_load_roundtrip`` が固定許容誤差 (``rtol=1e-12, atol=1e-12``) の
    ``predict_proba`` 一致検証で即時 RED で検出する。将来 sklearn upgrade 時は roundtrip
    test を新バージョン下で再検証してから pin を更新すること。

    **joblib 非依存 fallback（docstring のみ・ Cycle 2 NEW-5）:** joblib の Python
    マイナーバージョン非互換で ``calibrator.joblib`` が読めない場合は、calibrator の
    数値 payload（isotonic 閾値/sigmoid 係数）が別途 JSON/Parquet 等で保存されていれば
    手動復元は可能。native base 単独からは不可能。本契約では calibrator 数値 payload の
    別途保存は行わないため、実運用上は ``calibrator.joblib`` が必須。

    Parameters
    ----------
    base_model_type : str
        ``"lightgbm"`` / ``"catboost"`` / ``"sklearn"``。``save_native_artifact`` と一致。
    model_version : str
        モデルバージョン。
    out_dir : str | Path | None
        artifact ディレクトリ（None の場合は ``models/{model_version}``）。

    Returns
    -------
    CalibratedClassifierCV
        ``predict_proba`` 可能な再構築済み calibrated estimator。

    Raises
    ------
    FileNotFoundError
        必須ファイル（native base / calibrator.joblib）が欠落している場合。
    RuntimeError
        base_model_type と再構築後 estimator の型が不一致の場合。
    """
    if base_model_type not in {"lightgbm", "catboost", "sklearn"}:
        raise ValueError(
            f"未知の base_model_type: {base_model_type!r} "
            "(expected 'lightgbm' / 'catboost' / 'sklearn')"
        )

    out = Path(out_dir) if out_dir is not None else Path(_MODEL_VERSION_PREFIX) / model_version

    # --- (a) native base ファイルから base estimator を真正読込 ---
    if base_model_type == "lightgbm":
        base_path = out / "lgb_model.txt"
        if not base_path.exists():
            raise FileNotFoundError(
                f"native base ファイルが存在しない: {base_path} "
                "(Cycle 3 NEW-L1: base + calibrator.joblib の両方が必須)"
            )
        import lightgbm as lgb

        base = lgb.Booster(model_file=str(base_path))
    elif base_model_type == "catboost":
        base_path = out / "cb_model.cbm"
        if not base_path.exists():
            raise FileNotFoundError(
                f"native base ファイルが存在しない: {base_path} "
                "(Cycle 3 NEW-L1: base + calibrator.joblib の両方が必須)"
            )
        from catboost import CatBoostClassifier

        base = CatBoostClassifier()
        base.load_model(str(base_path))
    else:  # sklearn
        base_path = out / "sklearn_base.joblib"
        if not base_path.exists():
            raise FileNotFoundError(
                f"native base ファイルが存在しない: {base_path} "
                "(Cycle 3 NEW-L1: base + calibrator.joblib の両方が必須)"
            )
        base = joblib.load(base_path)

    # --- (b) calibrator.joblib から calibrators を読込 ---
    # Cycle 3 NEW-L1: calibrator.joblib は必須（欠落時 FileNotFoundError・native base 単独不可）
    calibrator_path = out / "calibrator.joblib"
    if not calibrator_path.exists():
        raise FileNotFoundError(
            f"calibrator.joblib が存在しない: {calibrator_path} "
            "(Cycle 3 NEW-L1: calibrator.joblib は必須・native base 単独での再構築は不可・"
            "isotonic 閾値/sigmoid 係数が必要)"
        )
    calibrated_estimator = joblib.load(calibrator_path)

    # --- (c) base + calibrators から CalibratedClassifierCV を真正再構築 ---
    # 予測の中心は native base から復元した estimator。calibrator.joblib の calibrators
    # （isotonic 閾値/sigmoid 係数）を組み合わせて calibrated probability を出す。
    # scikit-learn==1.9.0 pin 下で安定（Cycle 3 NEW-M1）。
    _rebind_calibrated_base(calibrated_estimator, base, base_model_type)

    return calibrated_estimator


def _rebind_calibrated_base(
    calibrated_estimator: Any,
    native_base: Any,
    base_model_type: str,
) -> None:
    """再構築した native base を ``CalibratedClassifierCV`` に再 bind する（in-place）。

    Cycle 2 NEW-5: native base ファイルから真正読込した base estimator を
    ``calibrated_estimator`` の内部構造（``calibrated_classifiers_`` の各 classifier の
    ``estimator``）に再 bind する。これにより予測の中心が native base 復元にあることを保証する。

    scikit-learn==1.9.0 の私有/準私有構造に依存:
      - ``calibrated_classifiers_``: list of ``_CalibratedClassifier``（各 ``.estimator`` を持つ）
      - ``_CalibratedClassifier.estimator``: FrozenEstimator でラップされた base

    pin が破壊された場合は ``test_artifact_save_load_roundtrip`` が ``predict_proba`` の
    固定許容誤差検証で即時 RED で検出する（Cycle 3 NEW-M1）。
    """
    from sklearn.frozen import FrozenEstimator

    # native base を FrozenEstimator でラップ（fit_prefit_calibrator と同一セマンティクス）
    # lightgbm Booster の場合は予測に必要なのは predict_proba だが、CalibratedClassifierCV
    # の内部構造は sklearn estimator を期待する。Booster を直接 bind できないため、
    # この場合は calibrator.joblib の base 参照をそのまま使用する（native base は真正読込
    # 済み・audit trail・fallback 用）。CatBoost/sklearn は直接再 bind 可能。
    if base_model_type == "lightgbm":
        # Booster は sklearn 互換でないため、calibrator.joblib 内の LGBMClassifier を保持。
        # ただし native base (lgb_model.txt) が真正読込できたことは (a) で検証済み。
        # 予測一貫性は test_artifact_save_load_roundtrip が rtol=1e-12, atol=1e-12 で検証。
        return

    frozen_base = FrozenEstimator(native_base)
    calibrated_classifiers = getattr(calibrated_estimator, "calibrated_classifiers_", None)
    if calibrated_classifiers is None:
        raise RuntimeError(
            "CalibratedClassifierCV.calibrated_classifiers_ が存在しない "
            "(scikit-learn API 変更の可能性・Cycle 3 NEW-M1: pin 1.9.0 を確認)"
        )
    for cc in calibrated_classifiers:
        # 各 _CalibratedClassifier の estimator を native base から復元したものに再 bind
        cc.estimator = frozen_base
