# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)
"""Phase 4 orchestrator: train_and_predict (trainer + calibrate_model + predict_p_fukusho 統合).

成功基準 #4 (SC#4) / §19.1 再現性聖域 / D-03 (両モデル候補) / D-06 (固定 seed bit-identical) /
review HIGH#2 (行整列保証) / review HIGH#7 (固定 thread count + as_of_datetime で bit-identical) /
review HIGH#12 (calibrator.py でなく独立モジュール・循環依存回避) /
Cycle 2 NEW HIGH-1 (aligned pred_proba を predict_p_fukusho に注入し再予測防止) /
Cycle 2 residual #13 (データ API 境界明示: label-joined frame のみを受け取る) を実装する
orchestration 層。

**設計の核心 (review HIGH#12: 純粋 utility と orchestration の分離):**

本モジュールは **orchestration 層** であり・``src.model.data`` / ``src.model.trainer`` /
``src.model.calibrator`` / ``src.model.predict`` / ``src.model.artifact`` を**一方向に** import
する（逆方向の import なし）。これにより ``calibrator.py`` は純粋 utility のまま維持され・
data/trainer/predict/artifact 的関心を import する循環依存を回避する
（review HIGH#12: ``train_and_predict`` が ``calibrator.py`` にあると循環依存が生じる）。

**Cycle 2 residual #13: データ API 境界の明示的契約:**

``train_and_predict`` の ``feature_df`` 引数は **label-joined frame**
（``build_training_frame`` の出力・``fukusho_hit_validated`` 列を含む）を前提とする。
**orchestrator は label join を絶対に再実行しない**（DB cursor / ``label_df`` 引数を
持たない・``run_train_predict`` が事前に ``build_training_frame`` で join
済みの frame を渡す）。docstring に契約を明記し・入口で ``assert "fukusho_hit_validated" in
feature_df.columns`` で暗黙契約を fail-loud 化する（違反は ``ValueError``）。これにより
residual #13 の「label join が run script と orchestrator のどちらで起きるか不明確」を
契約レベルで解消する。

**review HIGH#2: 行整列保証:**

``train_and_predict`` は単一 index 付き modeling frame を split / feature 選択 / 予測 / 出力
の全段で運ぶ。全 ``X_train`` / ``X_calib`` / ``X_test`` と ``y_*`` と ``race_df`` の merge の
直前に ``X_*.index.equals(y_*.index)`` / ``X_test.index.equals(race_df.index)`` を assert する
（不一致は ``RuntimeError``）。CatBoost 予測パスは ``_prepare_catboost_pool`` が sort 済み Pool
を返すため・``align_predictions`` で元の行順序に復元する（silent wrong-horse prediction 防止）。

**Cycle 2 NEW HIGH-1: aligned pred_proba を predict_p_fukusho に注入:**

``predict_p_fukusho`` 呼出に ``pred_proba=pred_proba`` を明示的に渡す。CatBoost の場合
``align_predictions`` で復元した予測値を注入し・LightGBM の場合も ``calibrated.predict_proba``
で算出した値を一貫して注入する。``predict_p_fukusho`` は注入された ``pred_proba`` を
**再予測せず直接使用** し ``len(pred_proba)==len(X)`` と index 一致を assert するため・
silent wrong-horse prediction が構造的に不可能。

**review HIGH#7 / SC#4: bit-identical 再現性 (§19.1 構造的ブロック):**

固定 seed (``seed=42``)・固定 thread count (LightGBM ``num_threads=1``・CatBoost
``thread_count=1``)・固定 ``as_of_datetime`` (``FIXED_REPRODUCE_TS`` 定数) で2回
``train_and_predict`` を呼出し・戻り prediction DataFrame の ``p_fukusho_hit`` 列が
``np.array_equal`` で bit-identical になることを ``_assert_deterministic`` が検証する。
失敗時は ``RuntimeError``（Phase 完了不可・§19.1 構造的ブロック）。

参照: 04-05-PLAN.md Task 1 / 04-RESEARCH.md D-06 SC#4 Reproduce Smoke Test /
      04-PATTERNS.md Shared Pattern 4 (staging-swap) / 04-04-SUMMARY.md (predict API) /
      src/model/{data,trainer,calibrator,predict,artifact}.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from src.model.calibrator import CalibrationResult, calibrate_model
from src.model.data import make_X_y, split_3way
from src.model.predict import make_model_version, predict_p_fukusho
from src.model.trainer import (
    CB_INIT_PARAMS,
    LGB_INIT_PARAMS,
    _prepare_catboost_pool,
    _prepare_lightgbm_train_eval,
    _split_train_eval_tail,
    align_predictions,
    train_catboost,
    train_lightgbm,
)

# ---------------------------------------------------------------------------
# 定数 (review HIGH#7: bit-identical 保証のための固定値)
# ---------------------------------------------------------------------------

# SC#4 reproduce smoke で使用する固定 as_of_datetime。
# 揮発性 now() が hash に混入するのを防止する (T-04-25b / review HIGH#7)。
# run_train_predict --check-reproduce と本モジュールの _assert_deterministic が使用。
FIXED_REPRODUCE_TS: datetime = datetime(2026, 6, 20, 0, 0, 0, tzinfo=UTC)

# HIGH-A cycle-2: 生 ID 列 → _code 列 の mapping（trainer.HIGH_CARD_CODE_COLS と対称）。
# trainer.HIGH_CARD_CODE_COLS = ["jockey_id_code", "trainer_id_code", "sire_id_code",
#                                 "bms_id_code", "horse_id_code"]
# これらの _code 列は Phase 3 builder で生 ID 列から fit_category_map で構築済みだが・
# Phase 5 D-03 BT窓再学習では train_and_predict(category_map=bt_fit_map) で BT-train-only
# の frozen map を渡して _code 列を再構築する（test 窓未観測 ID → __UNSEEN__ sentinel）。
_RAW_ID_TO_CODE_COLS: dict[str, str] = {
    "jockey_id": "jockey_id_code",
    "trainer_id": "trainer_id_code",
    "sire_id": "sire_id_code",
    "bms_id": "bms_id_code",
    "horse_id": "horse_id_code",
}


def _apply_category_map(
    feature_df: pd.DataFrame,
    category_map: dict[str, Any] | None,
) -> pd.DataFrame:
    """HIGH-A cycle-2: BT-train-only frozen category_map を feature_df の ``_code`` 列に適用。

    ``category_map`` が ``None`` の場合は **no-op** で ``feature_df`` をそのまま返す
    (Phase 4 等価・A5 後方互換)。feature_df は Phase 3 builder が構築済みの ``_code`` 列
    (例: ``jockey_id_code``) を保持しており・本関数はそれを上書きしない。

    ``category_map`` が渡された場合 (``{raw_id_col: dict[str, int]}`` 形式) は・
    ``feature_df`` に対応する生 ID 列 (例: ``jockey_id``) が存在する時に限り・
    ``src.utils.category_map.apply_category_map`` で ``_code`` 列を再構築して上書きする。
    これにより BT-train-only で fit した frozen map が model 前処理パスで消費される
    (silent 無視厳禁・HIGH-A cycle-2)。test 窓の未観測 ID は ``__UNSEEN__`` sentinel に
    mapping される (§14.3 leak-safe categorical handling)。

    生 ID 列が ``feature_df`` に存在しない場合は当該 raw_id_col を silent skip する
    (feature_df が _code 列のみを持つ Phase 3 snapshot 由来の場合への後方互換)。
    ただし ``category_map`` 自体が ``None`` でない以上・呼出側が意図的に BT-train-only
    map を渡したことは ``category_map_source='bt_train_only'`` stamp で記録される。

    Parameters
    ----------
    feature_df : pd.DataFrame
        label-joined frame (``build_training_frame`` の出力)。``_code`` 列を含む。
        生 ID 列 (``jockey_id`` 等) を含む場合はそれらを使って ``_code`` 列を再構築。
    category_map : dict[str, Any] | None
        ``{raw_id_col: dict[str, int]}`` 形式の BT-train-only frozen map。
        ``None`` の場合は no-op (Phase 4 等価)。

    Returns
    -------
    pd.DataFrame
        ``_code`` 列が (category_map 指定時) BT-train-only map で再構築された frame。
        ``category_map=None`` の場合は入力そのまま (コピーも返さない・呼出側で copy 済み前提)。
    """
    if category_map is None:
        # Phase 4 等価 (A5)・feature snapshot 構築済み _code 列をそのまま使用
        return feature_df

    # CR-08 / WR-07: 呼出元 frame 保護のため copy する。
    # _assert_deterministic が同一 feature_df で2回 train_and_predict を呼ぶ際・
    # in-place で _code 列を書き換えると2回目が1回目の変換済み列 (int 化済み) に対して
    # 再変換を試み・apply_category_map の astype(str) で 0 → '0' → __UNSEEN__ code になり
    # bit-identical が崩れて RuntimeError (SC#4 / §19.1 構造的ブロック違反) になる。
    feature_df = feature_df.copy()

    from src.utils.category_map import apply_category_map

    for raw_id_col, frozen_map in category_map.items():
        code_col = _RAW_ID_TO_CODE_COLS.get(raw_id_col)
        if code_col is None:
            # trainer.HIGH_CARD_CODE_COLS に対応しない raw_id_col は skip
            # (将来拡張時に _RAW_ID_TO_CODE_COLS を更新すること)
            continue
        if raw_id_col not in feature_df.columns:
            # feature_df が生 ID 列を持たない (Phase 3 snapshot が _code のみ保持等) 場合は
            # 当該 raw_id_col を skip。feature_df が生 ID 列を含むテストシナリオでのみ消費。
            continue
        # 供給 frozen map で _code 列を再構築 (test 窓未観測 ID → __UNSEEN__ sentinel)
        feature_df[code_col] = apply_category_map(feature_df[raw_id_col], frozen_map).to_numpy()

    return feature_df


# ---------------------------------------------------------------------------
# _merge_params — default_params に override を merge し seed / thread count を固定
# ---------------------------------------------------------------------------
def _merge_params(
    default_params: dict[str, Any],
    override: dict[str, Any] | None,
    seed: int,
) -> dict[str, Any]:
    """``default_params`` に ``override`` を (shallow) merge し・seed / thread count を強制固定する
    (review HIGH#7: thread count も seed も上書き可能だがデフォルトは 1/42)。

    ``override`` の ``learning_rate`` / ``num_leaves`` / ``depth`` 等は反映するが・
    ``seed`` / ``random_seed`` / ``num_threads`` / ``thread_count`` / ``deterministic`` /
    ``force_col_wise`` / ``has_time`` / ``bagging_seed`` / ``feature_fraction_seed`` 等の
    決定論フラグは ``default_params`` の値 (LGB_INIT_PARAMS / CB_INIT_PARAMS) で上書きする。
    これにより呼出側が誤って非決定論的 thread count を渡しても bit-identical が崩れない。

    Parameters
    ----------
    default_params : dict
        ``LGB_INIT_PARAMS`` または ``CB_INIT_PARAMS``。決定論フラグが全て固定済み。
    override : dict | None
        呼出側が上書きしたい param (例: ``{"learning_rate": 0.1}``・``None`` の場合は無視)。
    seed : int
        固定 seed (デフォルト 42)。``default_params["seed"]`` / ``["random_seed"]`` の値と
        一致することを想定。本関数は ``override`` にこれらが含まれていても ``default_params``
        の値で上書きする (bit-identical 保証)。

    Returns
    -------
    dict
        merge 済み param dict・決定論フラグは ``default_params`` の値で固定。
    """
    merged = dict(default_params)
    if override:
        merged.update(override)
    # 決定論フラグを default_params の値で強制上書き (review HIGH#7)
    # LightGBM
    for k in (
        "seed",
        "deterministic",
        "force_col_wise",
        "num_threads",
        "bagging_seed",
        "feature_fraction_seed",
    ):
        if k in default_params:
            merged[k] = default_params[k]
    # CatBoost
    for k in (
        "random_seed",
        "thread_count",
        "has_time",
        "allow_writing_files",
    ):
        if k in default_params:
            merged[k] = default_params[k]
    return merged


# ---------------------------------------------------------------------------
# train_and_predict — trainer + calibrate_model + predict_p_fukusho 統合 orchestrator
# ---------------------------------------------------------------------------
def train_and_predict(
    feature_df: pd.DataFrame,
    *,
    model_type: str,
    feature_snapshot_id: str,
    version_n: int = 1,
    seed: int = 42,
    eval_fraction: float = 0.2,
    params_override: dict[str, Any] | None = None,
    as_of_datetime: datetime | None = None,
    split_periods: dict[str, tuple[str, str]] | None = None,
    category_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``trainer`` + ``calibrate_model`` + ``predict_p_fukusho`` を統合し・行整列保証付きで
    予測 DataFrame を返す orchestrator (review HIGH#2 / HIGH#7 / HIGH#12 / SC#4)。

    **Cycle 2 residual #13 (データ API 境界明示的契約):**

    ``feature_df`` は ``build_training_frame`` の出力 (**label-joined frame**・
    ``fukusho_hit_validated`` 列を含む) を前提とする。**train_and_predict does NOT rejoin
    labels** (orchestrator は label join を絶対に再実行しない・DB cursor / ``label_df``
    引数を持たない)。入口で ``fukusho_hit_validated`` 列存在を assert し・違反は
    ``ValueError`` (fail-loud)。呼出側 (``run_train_predict``) がラベル取得 +
    ``build_training_frame`` で label join を完結してから渡すこと。

    **review HIGH#2 (行整列保証):**

    単一 index 付き modeling frame を split / feature 選択 / 予測 / 出力の全段で運ぶ。
    全 ``X_*`` / ``y_*`` / ``race_df`` の merge の直前に index equality を assert する
    (不一致は ``RuntimeError``)。CatBoost 予測パスは ``align_predictions`` で元順序を復元。

    **Cycle 2 NEW HIGH-1 (aligned pred_proba 注入):**

    ``predict_p_fukusho`` 呼出に ``pred_proba=pred_proba`` を明示的に渡す。CatBoost の場合
    ``align_predictions`` で復元した予測値・LightGBM の場合 ``calibrated.predict_proba`` の
    算出値を一貫して注入し・再予測で整列が捨てられる回帰を閉塞する。

    **Phase 5 D-03 BT窓再学習 (``split_periods`` パラメータ・後方互換 A5):**

    ``split_periods`` に ``{"train": (start, end), "calib": (start, end), "test": (start, end)}``
    を渡すと ``split_3way`` に ``periods=split_periods`` として伝播し・BT窓区間で
    train/calib/test を分割する。``None`` (既定) の場合は Phase 4 ハードコード区間を使用
    (A5 後方互換・SC#4 bit-identical 回帰防止)。HIGH-4: train/calib 重複 periods は
    ``split_3way`` の完全時系列条件 guard が ``ValueError`` で拒否 (look-ahead leak 構造的ブロック)。

    **Phase 5 HIGH-A cycle-2 (``category_map`` パラメータ・BT-train-only frozen map plumbing):**

    ``category_map`` に ``{raw_id_col: dict[str, int]}`` 形式の BT-train-only frozen map を
    渡すと ``_apply_category_map(feature_df, category_map)`` が model 前処理パスで供給 map を
    **消費** して ``_code`` 列を再構築する (silent 無視厳禁・§14.3 leak-safe categorical)。
    ``None`` (既定) の場合は orchestrator 内部で従来どおり feature snapshot 構築済みの
    ``_code`` 列をそのまま使用 (Phase 4 等価・A5)。供給 map は train 窓のみで ``fit_category_map``
    された辞書で・test 窓の未観測 ID は ``__UNSEEN__`` sentinel に mapping される
    (§14.3 / CLAUDE.md leak-safe categorical handling)。model_version メタに
    ``category_map_source`` を stamp する (``'bt_train_only'`` / ``'orchestrator_internal'``)。

    Parameters
    ----------
    feature_df : pd.DataFrame
        ``build_training_frame`` の出力 (label-joined frame・``fukusho_hit_validated`` 列を含む)。
        index は任意 (内部で ``split_3way`` が reset_index する)。
    model_type : str
        ``"lightgbm"`` または ``"catboost"`` (D-03 両モデル候補)。
    feature_snapshot_id : str
        feature snapshot ID (例: ``"20260620-1a-postreview-v2"``)。
    version_n : int
        model_version 採番の version番号 (デフォルト 1・D-10)。
    seed : int
        固定 seed (デフォルト 42・review HIGH#7)。
    eval_fraction : float
        train slice から eval set (early stopping) を切る割合 (デフォルト 0.2・D-04)。
    params_override : dict | None
        trainer に渡す追加 param (``learning_rate`` 等)。決定論フラグは無視される。
    as_of_datetime : datetime | None
        予測 provenance の as_of_datetime。``None`` の場合は ``datetime.now(UTC)``。
        reproduce smoke では固定値 (``FIXED_REPRODUCE_TS``) を渡して bit-identical を保証
        (review HIGH#7 / T-04-25b)。
    split_periods : dict[str, tuple[str, str]] | None
        Phase 5 D-03 BT窓区間 (``"train"``/``"calib"``/``"test"`` キー)。``None`` の場合は
        Phase 4 ハードコード (後方互換 A5)。
    category_map : dict[str, Any] | None
        Phase 5 HIGH-A cycle-2 BT-train-only frozen category map
        (``{raw_id_col: dict[str, int]}``・例: ``{"jockey_id": {...}}``)。``None`` の場合は
        Phase 4 等価 (feature snapshot 構築済み ``_code`` 列をそのまま使用)。

    Returns
    -------
    dict
        - ``estimator``: 学習済み base estimator (LightGBM / CatBoost)
        - ``calibrated``: ``CalibratedClassifierCV`` (calibrate_model の出力)
        - ``calib_method``: ``"isotonic"`` / ``"sigmoid"`` (provenance)
        - ``pred_df``: ``predict_p_fukusho`` の出力・index は ``splits["test"].index`` と一致
        - ``model_version``: ``make_model_version`` の出力 (D-10 形式)
        - ``splits``: ``split_3way`` の戻り dict
        - ``_aligned_pred_proba``: orchestrator 内部で align / 算出した pred_proba Series
          (test で Cycle 2 NEW HIGH-1 の実証に使用・本番 pipeline は消費しない)
        - ``category_map_source``: HIGH-A cycle-2 provenance
          (``"bt_train_only"`` / ``"orchestrator_internal"``)

    Raises
    ------
    ValueError
        ``feature_df`` が label-joined でない (``fukusho_hit_validated`` 列がない) 時。
    RuntimeError
        X/y/race_df の index equality 違反・CatBoost 予測の align 失敗。
    """
    # --- Cycle 2 residual #13: label-joined frame 契約の fail-loud assert ---
    if "fukusho_hit_validated" not in feature_df.columns:
        raise ValueError(
            "train_and_predict: feature_df must be the output of build_training_frame "
            "(label-joined, contains 'fukusho_hit_validated' column). "
            "train_and_predict does NOT rejoin labels — call run_train_predict to "
            "load labels + build_training_frame first (Cycle 2 residual #13)."
        )

    # --- as_of_datetime の確定 (review HIGH#7: 制御可能) ---
    if as_of_datetime is None:
        as_of_dt = datetime.now(UTC)
    else:
        as_of_dt = as_of_datetime

    # --- HIGH-A cycle-2: BT-train-only frozen category_map を model 前処理で消費 ---
    # category_map が渡された場合・feature_df の生 ID 列 (jockey_id 等) から _code 列を再構築
    # して model 前処理 (LightGBM categorical_feature / CatBoost cat_features) に供給する。
    # silent 無視厳禁 (HIGH-A cycle-2)・test 窓未観測 ID は __UNSEEN__ sentinel に mapping。
    # category_map=None の場合は Phase 4 等価 (feature snapshot 構築済み _code 列をそのまま使用)。
    category_map_source = "orchestrator_internal"
    if category_map is not None:
        feature_df = _apply_category_map(feature_df, category_map)
        category_map_source = "bt_train_only"

    # --- split_3way で train/calib/test に分割 (正準 race_key 時系列条件保証済み) ---
    # Phase 5 D-03: split_periods を periods=split_periods として伝播 (後方互換 A5)
    splits = split_3way(feature_df, periods=split_periods)
    train_df = splits["train"]
    calib_df = splits["calib"]
    test_df = splits["test"]

    # --- make_X_y で厳密 feature 選択 (X.columns == FEATURE_COLUMNS 完全一致 assert) ---
    X_train_full, y_train_full = make_X_y(train_df)
    X_calib, y_calib = make_X_y(calib_df)
    X_test, y_test = make_X_y(test_df)

    # --- review HIGH#2: index equality assert (X/y は make_X_y が同一 frame から抽出) ---
    if not X_train_full.index.equals(y_train_full.index):
        raise RuntimeError(
            "train_and_predict: X_train_full.index != y_train_full.index (review HIGH#2)"
        )
    if not X_calib.index.equals(y_calib.index):
        raise RuntimeError("train_and_predict: X_calib.index != y_calib.index (review HIGH#2)")
    if not X_test.index.equals(y_test.index):
        raise RuntimeError("train_and_predict: X_test.index != y_test.index (review HIGH#2)")

    # --- race_df (PK + race_date) の index equality assert (review HIGH#2) ---
    # predict_p_fukusho が race_df の PK 列 + race_date を参照するため・X_test と一致が必要。
    # FEATURE_COLUMNS には PK 列が含まれないため・test_df (元 frame) から取得する。
    race_df_test = test_df.loc[X_test.index, :]
    if not race_df_test.index.equals(X_test.index):
        raise RuntimeError(
            "train_and_predict: race_df_test.index != X_test.index (review HIGH#2・"
            "silent wrong-horse prediction 防止)"
        )

    # --- model_version 採番 (D-10 / review HIGH#4) ---
    model_version = make_model_version(feature_snapshot_id, model_type, version_n)

    # --- _split_train_eval_tail で train_core / train_tail に分割 (D-04 / review Cross-Plan #8) ---
    # trainer の _split_train_eval_tail は race_start_datetime 列を必要とするため・
    # X_train に meta 列を付与した frame を渡す。FEATURE_COLUMNS は meta 列を含まないため・
    # 元 train_df から必要列を結合する。
    train_meta_cols = [
        c for c in ("race_start_datetime", "race_key", "race_date") if c in train_df.columns
    ]
    # _split_train_eval_tail に渡す frame: X_train_full + meta 列 (race_key 単位の時系列分割用)
    train_split_frame = X_train_full.copy()
    for c in train_meta_cols:
        train_split_frame[c] = train_df.loc[X_train_full.index, c].values
    train_core_df, train_tail_df = _split_train_eval_tail(
        train_split_frame, eval_fraction=eval_fraction
    )

    X_train_core = train_core_df.drop(columns=train_meta_cols, errors="ignore")
    X_train_tail = train_tail_df.drop(columns=train_meta_cols, errors="ignore")
    y_train_core = y_train_full.loc[X_train_core.index]
    y_train_tail = y_train_full.loc[X_train_tail.index]

    # --- eval set 分離 guard (review Cross-Plan #8) 用の race_key 集合 ---
    eval_race_keys = (
        set(train_tail_df["race_key"]) if "race_key" in train_tail_df.columns else set()
    )
    calib_race_keys = set(calib_df["race_key"]) if "race_key" in calib_df.columns else set()
    test_race_keys = set(test_df["race_key"]) if "race_key" in test_df.columns else set()

    train_core_max_date = train_df["race_date"].max()
    eval_max_date = (
        train_tail_df["race_date"].max() if "race_date" in train_tail_df.columns else None
    )

    # --- model_type で分岐: trainer 呼出 ---
    if model_type == "lightgbm":
        merged_params = _merge_params(LGB_INIT_PARAMS, params_override, seed)
        # train_core / train_tail を train_lightgbm に渡す。trainer 内部の
        # _prepare_lightgbm_train_eval が categorical を統一する。test 予測時は
        # 学習済み estimator の pandas_categorical を取得して test に適用する
        # （下記予測パスで _apply_lightgbm_pandas_categorical を使用）。
        estimator = train_lightgbm(
            X_train_core,
            y_train_core,
            X_eval=X_train_tail,
            y_eval=y_train_tail,
            eval_race_keys=eval_race_keys,
            calib_race_keys=calib_race_keys,
            test_race_keys=test_race_keys,
            train_core_max_date=train_core_max_date,
            eval_max_date=eval_max_date,
            params=merged_params,
        )
    elif model_type == "catboost":
        merged_params = _merge_params(CB_INIT_PARAMS, params_override, seed)
        # CatBoost は race_start_datetime sort のため meta 列が必要
        X_train_core_cb = X_train_core.copy()
        X_train_tail_cb = X_train_tail.copy()
        for c in ("race_start_datetime", "race_key"):
            if c in train_df.columns:
                X_train_core_cb[c] = train_df.loc[X_train_core.index, c].values
                X_train_tail_cb[c] = train_df.loc[X_train_tail.index, c].values
        estimator, _sorted_index = train_catboost(
            X_train_core_cb,
            y_train_core,
            X_eval=X_train_tail_cb,
            y_eval=y_train_tail,
            eval_race_keys=eval_race_keys,
            calib_race_keys=calib_race_keys,
            test_race_keys=test_race_keys,
            train_core_max_date=train_core_max_date,
            eval_max_date=eval_max_date,
            params=merged_params,
        )
    else:
        raise ValueError(
            f"train_and_predict: 未知の model_type {model_type!r} "
            "(expected 'lightgbm' or 'catboost')"
        )

    # --- calibrate_model (calibrator.py・prefit・isotonic/sigmoid 切替) ---
    # review HIGH#2 + Rule 3 auto-fix: LightGBM の場合・X_calib と X_test を train_core と
    # 同一の categorical dtype に前処理してから calibrator / predict に渡す。これにより
    # CalibratedClassifierCV 経由の predict で "train and valid dataset categorical_feature
    # do not match" エラーを回避する (LightGBM 4.6 が categorical dtype 完全一致を要求)。
    #
    # CatBoost + CalibratedClassifierCV 互換性 (Rule 3 auto-fix): CatBoost estimator を
    # FrozenEstimator でラップして CalibratedClassifierCV.fit(X_calib) すると・fit 内部で
    # CatBoost が DataFrame を受け取り cat_features 認識なしに Pool を作ろうとし・StringDtype
    # 列の pd.NA で "must be real number, not NAType" エラーになる。そのため CatBoost の場合は
    # calibrate_model を経由せず・base estimator で calib Pool の生予測を算出してから手動で
    # isotonic/sigmoid calibrator を fit する (_calibrate_catboost_manual helper)。
    if model_type == "lightgbm":
        _, X_calib_lgb = _prepare_lightgbm_train_eval(X_train_core, X_calib)
        calib_result = calibrate_model(
            estimator,
            X_calib_lgb,
            y_calib,
            race_dates_calib=calib_df.loc[X_calib.index, "race_date"],
            train_max_date=train_df["race_date"].max(),
        )
    else:  # catboost
        calib_result = _calibrate_catboost_manual(
            estimator,
            X_calib,
            y_calib,
            calib_df,
            train_df,
        )

    # --- 予測 (review HIGH#2 + HIGH#12 CatBoost 行順序復元 + Cycle 2 NEW HIGH-1) ---
    if model_type == "lightgbm":
        # LightGBM: calibrated.predict_proba(X_test) で直接予測。
        # train_core と test の categorical categories を _prepare_lightgbm_train_eval で統一する
        # (test_trainer.py test_no_target_encoding_leak と同一パターン・Rule 3 auto-fix:
        # LightGBM 4.6 が train/predict の categorical dtype 完全一致を要求する仕様への対応)。
        # train_lightgbm 内部の _prepare_lightgbm_train_eval(X_train_core, X_train_tail) が
        # train_core の categorical を確定するため・test も train_core を基準に統一する。
        _, X_test_lgb = _prepare_lightgbm_train_eval(X_train_core, X_test)
        raw_pred = calib_result.calibrated.predict_proba(X_test_lgb)[:, 1]
        pred_proba = pd.Series(raw_pred, index=X_test.index, name="p_fukusho_hit")
    else:  # catboost
        # CatBoost: sort 済み Pool で予測 → align_predictions で元順序復元
        X_test_cb = X_test.copy()
        for c in ("race_start_datetime", "race_key"):
            if c in test_df.columns:
                X_test_cb[c] = test_df.loc[X_test.index, c].values
        pool_test, sorted_test_idx = _prepare_catboost_pool(X_test_cb, sort=True)
        # CatBoost の CalibratedClassifierCV は predict_proba に DataFrame を渡すと
        # 内部で cat_features 認識なしに Pool を作ろうとして StringDtype の pd.NA で
        # "must be real number, not NAType" エラーになる (CatBoost + sklearn
        # CalibratedClassifierCV 互換性制約・Rule 3 auto-fix)。そのため base estimator
        # で Pool を直接予測し・calibrator (isotonic/sigmoid) を手動適用する。
        raw_pred_sorted = _catboost_calibrated_predict_proba(
            calib_result.calibrated, estimator, pool_test
        )
        pred_proba = align_predictions(
            pd.Series(raw_pred_sorted, index=sorted_test_idx, name="p_fukusho_hit"),
            sorted_test_idx,
            X_test.index,
        )

    # pred_proba の index が X_test.index と完全一致することを最終 assert (review HIGH#2)
    if not pred_proba.index.equals(X_test.index):
        raise RuntimeError(
            "train_and_predict: pred_proba.index != X_test.index after align "
            "(review HIGH#2・silent wrong-horse prediction)"
        )

    # --- predict_p_fukusho 呼出 (Cycle 2 NEW HIGH-1: pred_proba 注入で再予測防止) ---
    # pred_proba を明示的に渡すことで・CatBoost の aligned 予測値が predict_p_fukusho 内部で
    # 再予測されて捨てられる回帰 (Cycle 2 NEW HIGH-1) を閉塞。
    # predict_p_fukusho は注入時 len(pred_proba)==len(X) と index 一致を assert する。
    pred_df = predict_p_fukusho(
        calib_result.calibrated,
        X_test,
        model_type=model_type,
        model_version=model_version,
        feature_snapshot_id=feature_snapshot_id,
        calib_method=calib_result.calib_method,
        race_df=race_df_test,
        split_label="test",
        as_of_datetime=as_of_dt,
        pred_proba=pred_proba,
    )

    return {
        "estimator": estimator,
        "calibrated": calib_result.calibrated,
        "calib_method": calib_result.calib_method,
        "pred_df": pred_df,
        "model_version": model_version,
        "splits": splits,
        # _aligned_pred_proba: Cycle 2 NEW HIGH-1 実証用の内部参照 (test が消費)
        "_aligned_pred_proba": pred_proba,
        # HIGH-A cycle-2: category_map provenance stamp
        "category_map_source": category_map_source,
    }


def _calibrate_catboost_manual(
    base_estimator: Any,
    X_calib: pd.DataFrame,
    y_calib: pd.Series,
    calib_df: pd.DataFrame,
    train_df: pd.DataFrame,
) -> CalibrationResult:
    """CatBoost の場合の手動 calibration (Rule 3 auto-fix: CatBoost + CalibratedClassifierCV
    互換性問題回避)。

    CatBoost estimator を FrozenEstimator + CalibratedClassifierCV で fit すると・fit 内部で
    CatBoost が DataFrame を受け取り cat_features 認識なしに Pool を作ろうとし・StringDtype 列の
    pd.NA で失敗する。本関数は以下の手順で手動 calibration を実施する:

      1. X_calib を _prepare_catboost_pool で cat_features 指定済み Pool に変換
      2. base_estimator.predict_proba(pool) で生のクラス1確率を算出
      3. §15.2 推奨に従り calib sample 件数で isotonic/sigmoid を切替
      4. sklearn の _SigmoidCalibration / IsotonicRegression を生予測 → y_calib で fit
      5. CalibratedClassifierCV 互換のラッパー (ManualCalibratedEstimator) を構築して返す

    strict-later disjoint guard (train_max_date < calib_min_date) は calib_df / train_df の
    race_date から検証する (calibrate_model / fit_prefit_calibrator と同等の保証)。

    Returns
    -------
    CalibrationResult
        ``calibrated`` (ManualCalibratedEstimator・predict_proba 可能) + ``calib_method``。
    """
    from sklearn.isotonic import IsotonicRegression

    # strict-later disjoint guard (fit_prefit_calibrator と同等)
    calib_min_date = calib_df.loc[X_calib.index, "race_date"].min()
    train_max_date = train_df["race_date"].max()
    if not (train_max_date < calib_min_date):
        raise ValueError(
            "_calibrate_catboost_manual: strict-later disjoint 違反 "
            f"(train_max_date={train_max_date} >= calib_min_date={calib_min_date}・"
            "§15.2 / SC#4・look-ahead leak prevented)"
        )

    # 1. X_calib を Pool 化 (cat_features 指定・fillna 前処理)
    X_calib_cb = X_calib.copy()
    for c in ("race_start_datetime", "race_key"):
        if c in calib_df.columns:
            X_calib_cb[c] = calib_df.loc[X_calib.index, c].values
    calib_pool, _ = _prepare_catboost_pool(X_calib_cb, sort=False)

    # 2. base estimator で生予測
    raw_proba = base_estimator.predict_proba(calib_pool)[:, 1]

    # 3. §15.2: calib sample 件数で isotonic/sigmoid 切替
    calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"

    # 4. calibrator を fit
    if calib_method == "isotonic":
        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(raw_proba, y_calib.to_numpy())
    else:  # sigmoid
        from sklearn.calibration import _SigmoidCalibration

        calibrator = _SigmoidCalibration()
        calibrator.fit(raw_proba, y_calib.to_numpy())

    # 5. CalibratedClassifierCV 互換のラッパーを構築
    calibrated = _ManualCatBoostCalibrated(
        base_estimator=base_estimator,
        calibrator=calibrator,
    )

    return CalibrationResult(calibrated=calibrated, calib_method=calib_method)


class _ManualCatBoostCalibrated:
    """CatBoost + 手動 calibrator のラッパー (CalibratedClassifierCV 互換インターフェース)。

    ``predict_proba(pool)`` を呼ぶと (a) base estimator で Pool 予測 (b) calibrator で変換
    した calibrated なクラス確率を返す。Pool を直接受け取ることで CatBoost の cat_features
    認識問題を回避する (Rule 3 auto-fix)。

    predict_p_fukusho は本クラスの calibrated_estimator.predict_proba(X) を呼ぶが・
    orchestrator の CatBoost 予測パスでは本クラスを使わず _catboost_calibrated_predict_proba
    で Pool を直接渡す (DataFrame を渡すと cat_features 認識問題が再発するため)。
    """

    def __init__(self, base_estimator: Any, calibrator: Any) -> None:
        self.base_estimator = base_estimator
        self.calibrator = calibrator
        # CalibratedClassifierCV 互換属性 (artifact.save_native_artifact が参照)
        self.estimator = base_estimator
        self.calibrated_classifiers_ = [self]  # artifact.py が参照

    def predict_proba(self, X: Any) -> np.ndarray:
        """X (Pool or DataFrame) を受け取り calibrated なクラス確率 [n, 2] を返す。"""
        from catboost import Pool

        if isinstance(X, Pool):
            pool = X
        else:
            # DataFrame の場合は cat_features 認識問題を回避するため Pool 化は呼出側責任
            # (orchestrator は直接 Pool を渡す・本メソッドは fallback 用)
            pool, _ = _prepare_catboost_pool(X, sort=False)
        raw = self.base_estimator.predict_proba(pool)[:, 1]
        calibrated = self.calibrator.predict(raw)
        return np.column_stack([1.0 - calibrated, calibrated])


def _catboost_calibrated_predict_proba(
    calibrated_estimator: Any,
    base_estimator: Any,
    pool: Any,
) -> np.ndarray:
    """CatBoost の CalibratedClassifierCV 互換性問題を回避し・base estimator で Pool 予測してから
    calibrator (isotonic/sigmoid) を手動適用してクラス1確率を返す (Rule 3 auto-fix)。

    ``calibrated_estimator`` が ``_ManualCatBoostCalibrated`` の場合は内部 calibrator を使用。
    CalibratedClassifierCV の場合は ``calibrated_classifiers_[0].calibrators[0]`` から取得。

    Parameters
    ----------
    calibrated_estimator : CalibratedClassifierCV | _ManualCatBoostCalibrated
        ``calibrate_model`` または ``_calibrate_catboost_manual`` の戻り値。
    base_estimator : CatBoostClassifier
        ``train_catboost`` の戻り値。Pool を直接予測可能。
    pool : catboost.Pool
        ``_prepare_catboost_pool`` の戻り値。sort 済み・cat_features 指定済み。

    Returns
    -------
    np.ndarray
        calibrated なクラス1確率 (shape=[n_rows])。
    """
    # _ManualCatBoostCalibrated の場合は calibrator を直接使用
    if hasattr(calibrated_estimator, "calibrator") and hasattr(
        calibrated_estimator, "base_estimator"
    ):
        raw_proba = base_estimator.predict_proba(pool)[:, 1]
        return calibrated_estimator.calibrator.predict(raw_proba)

    # CalibratedClassifierCV の場合 (fallback)
    raw_proba = base_estimator.predict_proba(pool)[:, 1]
    calibrated_classifiers = getattr(calibrated_estimator, "calibrated_classifiers_", None)
    if not calibrated_classifiers:
        raise RuntimeError(
            "_catboost_calibrated_predict_proba: CalibratedClassifierCV に "
            "calibrated_classifiers_ が無い (sklearn API 変更の可能性)"
        )
    cc = calibrated_classifiers[0]
    calibrators = getattr(cc, "calibrators", None)
    if not calibrators:
        raise RuntimeError(
            "_catboost_calibrated_predict_proba: _CalibratedClassifier に "
            "calibrators が無い (sklearn API 変更の可能性)"
        )
    calibrator = calibrators[0]
    return calibrator.predict(raw_proba)


# ---------------------------------------------------------------------------
# _assert_deterministic — SC#4 reproduce smoke (review HIGH#7)
# ---------------------------------------------------------------------------
def _assert_deterministic(
    model_type: str,
    feature_df: pd.DataFrame,
    *,
    feature_snapshot_id: str = "20260620-1a-postreview-v2",
    version_n: int = 1,
    seed: int = 42,
    as_of_datetime: datetime = FIXED_REPRODUCE_TS,
    split_periods: dict[str, tuple[str, str]] | None = None,
    category_map: dict[str, Any] | None = None,
) -> None:
    """SC#4 reproduce smoke: 固定 seed + 固定 thread count + 固定 as_of_datetime で2回
    ``train_and_predict`` を呼出し・戻り prediction の ``p_fukusho_hit`` 列が
    ``np.array_equal`` (bit-identical) になることを検証する (review HIGH#7・§19.1 構造的ブロック)。

    Phase 5 D-03 / HIGH-A cycle-2: BT窓再学習 (``split_periods``) と BT-train-only
    category_map (``category_map``) を指定しても bit-identical が維持されることを検証。
    失敗時は ``RuntimeError``。

    Parameters
    ----------
    model_type : str
        ``"lightgbm"`` または ``"catboost"``。
    feature_df : pd.DataFrame
        label-joined frame (``train_and_predict`` と同一契約)。
    as_of_datetime : datetime
        固定 as_of_datetime (デフォルト ``FIXED_REPRODUCE_TS``・review HIGH#7)。
    split_periods : dict | None
        Phase 5 D-03 BT窓区間 (``None`` の場合は Phase 4 ハードコード)。
    category_map : dict | None
        Phase 5 HIGH-A cycle-2 BT-train-only frozen category map。
    """
    result1 = train_and_predict(
        feature_df,
        model_type=model_type,
        feature_snapshot_id=feature_snapshot_id,
        version_n=version_n,
        seed=seed,
        as_of_datetime=as_of_datetime,
        split_periods=split_periods,
        category_map=category_map,
    )
    result2 = train_and_predict(
        feature_df,
        model_type=model_type,
        feature_snapshot_id=feature_snapshot_id,
        version_n=version_n,
        seed=seed,
        as_of_datetime=as_of_datetime,
        split_periods=split_periods,
        category_map=category_map,
    )

    pred1 = result1["pred_df"]["p_fukusho_hit"].to_numpy()
    pred2 = result2["pred_df"]["p_fukusho_hit"].to_numpy()

    if not np.array_equal(pred1, pred2):
        raise RuntimeError(
            f"_assert_deterministic({model_type}): SC#4 reproduce smoke 違反 "
            "(review HIGH#7 / §19.1 構造的ブロック・Phase 完了不可): "
            f"seed={seed} + 固定 thread count + 固定 as_of_datetime={as_of_datetime} "
            "で2回 train_and_predict した p_fukusho_hit が bit-identical でない。"
        )


__all__ = [
    "FIXED_REPRODUCE_TS",
    "train_and_predict",
    "_merge_params",
    "_apply_category_map",
    "_assert_deterministic",
]
