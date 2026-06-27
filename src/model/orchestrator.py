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
from src.model.predict import PREDICTION_COLUMNS, make_model_version, predict_p_fukusho
# Phase 12 SC#1 / EV-01: compute_p_lower_conformal_shrinkage (Plan 01 で追加済み・calib slice のみ・§11.2 聖域)
from src.model.race_relative import apply_race_relative_correction, compute_p_lower_conformal_shrinkage
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
# _normalize_model_type — Phase 11 codex review HIGH#2: race-relative short を
# binary base に正規化し・学習/calib/予測パスは base を使い・model_version 採番には
# 元の model_type（original）を渡して race-relative short を保持する。
# ---------------------------------------------------------------------------
def _normalize_model_type(model_type: str) -> tuple[str, str]:
    """``model_type`` を ``(base_type, original_type)`` に正規化する（codex HIGH#2）.

    race-relative 補正層は binary モデル（lightgbm/catboost）の上に被せる設計（D-01）.
    学習・calib・予測パスは binary base model を使う必要があるが・model_version 採番
    （``make_model_version``）には race-relative short 識別子（lgbrr/cbrr）を保持する
    ことで・binary v1.0（``-lgb-v1``）と race-relative（``-lgbrr-v1``）を区別可能にする
    （SC#5 model_version-scoped idempotent swap の前提・HIGH#1）.

    正規化規則:
      - ``"lightgbm_rr"`` → ``("lightgbm", "lightgbm_rr")``
      - ``"catboost_rr"`` → ``("catboost", "catboost_rr")``
      - ``"lightgbm"`` / ``"catboost"`` / ``"logreg"`` 等はそのまま
        ``(model_type, model_type)`` を返す（後方互換・A5）.

    Parameters
    ----------
    model_type : str
        呼出側が指定した model_type. race-relative short (``*_rr``) を含む.

    Returns
    -------
    tuple[str, str]
        ``(base_model_type, original_model_type)``. base は trainer/calib/予測パスが
        消費し・original は ``make_model_version`` が消費する.
    """
    if model_type == "lightgbm_rr":
        return ("lightgbm", "lightgbm_rr")
    if model_type == "catboost_rr":
        return ("catboost", "catboost_rr")
    return (model_type, model_type)

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
    snapshot_id: str | None = None,
    theta: float | None = None,
    score_split: str = "test",
    label_version: str = "unspecified",
    odds_snapshot_policy: str = "unspecified",
    backtest_strategy_version: str = "unspecified",
    # Phase 12 SC#1 / EV-01 [C-12-02-1 HIGH]: q_shrink 外部注入 API (keyword-only・§11.2 聖域)
    # - p_lower_q_shrink: None 既定・score_split='test' 経路で calib 済み q_shrink を外部注入する唯一の経路.
    #   呼出側 run_phase12_evaluation.py (Plan 04) が score_split='calib' で計算した値を渡す.
    #   theta is not None かつ score_split='test' かつ p_lower_q_shrink is None の場合は RuntimeError
    #   (test 窓 outcome を使った q_shrink 再計算経路への滑りを構造的に阻止・§11.2 聖域・Shared Pattern 1).
    # - p_lower_q_level: 0.90 既定 (D-02 事前登録値). test 窓で変更不可. score_split='calib' 経路の
    #   q_shrink 計算でも使用.
    p_lower_q_shrink: float | None = None,
    p_lower_q_level: float = 0.90,
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

    **REVIEW H1-b (Phase 9 P03・``snapshot_id`` パラメータ・FEATURE_COLUMNS 選択用):**

    ``snapshot_id`` は ``feature_snapshot_id`` とは**別引数**(FEATURE_COLUMNS 選択用・provenance
    でなく)・内部3箇所の ``make_X_y`` 呼出に ``snapshot_id=snapshot_id`` で明示伝播する
    (T-09-26 mitigate)。``snapshot_id=None`` (既定) は v1.0 デフォルト FEATURE_COLUMNS (A5 後方互換)。
    これにより speed_figure snapshot で学習しても v1.0 FEATURE_COLUMNS が静かに使われる失敗
    (P05 stop gate も検出不能) を閉塞する。予測経路に snapshot_id 無しの bare 呼出 が残らないことは
    acceptance_criteria の grep/AST verify で保証 (H1-b)。

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
    snapshot_id : str | None
        Phase 9 P03 REVIEW H1-b: FEATURE_COLUMNS 選択用 snapshot_id (``feature_snapshot_id``
        とは別・provenance でない)。``None`` (既定) は v1.0 デフォルト FEATURE_COLUMNS (A5)。
    theta : float | None
        Phase 11 race-relative logit temperature（D-03 事前登録・calib slice で選んだ値・
        test 窓選び直し禁止 §11.2 聖域）。``None`` の場合は補正層をスキップし v1.0 binary
        等価（A5 後方互換・SC#4 bit-identical 回帰防止）。候補は
        ``race_relative.THETA_CANDIDATES = (0.5, 0.75, 1.0, 1.25, 1.5)``。呼出側が
        ``theta=float`` を渡す場合は ``model_type`` は ``"lightgbm_rr"`` / ``"catboost_rr"``
        のいずれか（``_rr`` サフィックス）が必須（codex cycle-2 MEDIUM・双方向 guard・
        補正済み確率が binary model_version で刻印される silent provenance hole 回避）。
    score_split : str
        予測対象 split。既定 ``"test"``。Phase 11 で ``"calib"`` を指定すると ``X_test``
        でなく ``X_calib`` を予測対象とし・``predict_p_fukusho`` に ``split_label="calib"``
        を渡す（codex review HIGH#1・§11.2 聖域の機械保証・θ 選択経路が test 窓に触れない
        構造的ブロック）。許容値: ``{"test", "calib"}``。それ以外は ``ValueError``。
    label_version : str
        §19.1 再現性 metadata。既定値 ``"unspecified"`` sentinel (codex cycle-2 NEW HIGH#3)。
        orchestrator は値を推測せず呼出側から受け取った値をそのまま ``predict_p_fukusho``
        に伝播。run_phase11_evaluation.py が事前登録値を渡し・v1.0 binary 呼出
        (theta=None/3引数省略) は sentinel で安全 (NOT NULL 違反回避・loader 空文字→None 変換回避)。
    odds_snapshot_policy : str
        §19.1 再現性 metadata。既定値 ``"unspecified"`` sentinel (codex cycle-2 NEW HIGH#3)。
        orchestrator は値を推測せず呼出側から受け取った値をそのまま伝播。
    backtest_strategy_version : str
        §19.1 再現性 metadata。既定値 ``"unspecified"`` sentinel (codex cycle-2 NEW HIGH#3)。

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
        - ``race_relative_theta``: Phase 11 race-relative logit temperature provenance
          (``None`` = v1.0 等価・or float = calib slice で選んだ事前登録値・§19.1)
        - ``score_split``: Phase 11 予測対象 split provenance
          (``"test"`` / ``"calib"``・codex HIGH#1)
        - ``label_version`` / ``odds_snapshot_policy`` / ``backtest_strategy_version``:
          §19.1 再現性 metadata provenance (codex HIGH#3・呼出側から受け取った値をそのまま返却)

    Raises
    ------
    ValueError
        ``feature_df`` が label-joined でない (``fukusho_hit_validated`` 列がない) 時。
    RuntimeError
        X/y/race_df の index equality 違反・CatBoost 予測の align 失敗。
    ValueError
        ``theta`` と ``model_type`` の一貫性違反（codex cycle-2 MEDIUM 双方向 guard）。
    """
    # --- Phase 11 codex HIGH#2: _normalize_model_type で race-relative short を binary base に正規化 ---
    # 学習・calib・予測パスは base_model_type（lightgbm/catboost）を使い・model_version 採番には
    # original_model_type（lightgbm_rr/catboost_rr 含む）を渡す（race-relative short を保持）。
    base_model_type, original_model_type = _normalize_model_type(model_type)

    # --- Phase 11 codex cycle-2 MEDIUM: theta/model_type 一貫性の双方向 guard ---
    # theta=float + binary model_type だと・race-relative 補正済み確率が binary model_version
    # で刻印される silent provenance hole（T-11-13b）。model_type='_rr' + theta=None は不整合。
    # 両方向で ValueError にし・冒頭配置なので feature_df 無しでも guard が発火する。
    if theta is not None and not original_model_type.endswith("_rr"):
        raise ValueError(
            f"train_and_predict: theta=float の場合は model_type が '_rr' サフィックス必須"
            f"（lightgbm_rr/catboost_rr）・theta={theta} model_type={original_model_type}"
            f"（codex cycle-2 MEDIUM・silent provenance hole 回避）"
        )
    if original_model_type.endswith("_rr") and theta is None:
        raise ValueError(
            f"train_and_predict: model_type='_rr' の場合は theta 必須・"
            f"model_type={original_model_type} theta=None（11-03 仕様）"
        )

    # --- Phase 11 codex HIGH#1: score_split の入力検証（構造的聖域ブロック） ---
    # 許容値は {"test", "calib"} のみ。theta 選択経路は score_split="calib" で呼べば
    # 構造的に test 窓に触れない（§11.2 聖域の機械保証・docstring だけの紳士協定でない）。
    if score_split not in ("test", "calib"):
        raise ValueError(
            f"train_and_predict: score_split は 'test' または 'calib' のみ許容・"
            f"score_split={score_split!r}（codex HIGH#1・§11.2 聖域ブロック）"
        )

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
    # REVIEW H1-b (Phase 9 P03): snapshot_id を明示伝播 (bare call でない・T-09-26 mitigate)。
    # snapshot_id=None は v1.0 デフォルト FEATURE_COLUMNS (A5 後方互換)。
    X_train_full, y_train_full = make_X_y(train_df, snapshot_id=snapshot_id)
    X_calib, y_calib = make_X_y(calib_df, snapshot_id=snapshot_id)
    X_test, y_test = make_X_y(test_df, snapshot_id=snapshot_id)

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

    # --- Phase 11 codex HIGH#1: score_split による予測対象の切替（構造的聖域ブロック） ---
    # X_score / race_df_score を構築し・以降の予測パスは X_score を使う。
    # score_split="test" は既存の X_test / race_df_test をそのまま使用（A5 後方互換）。
    # score_split="calib" は X_calib を予測対象とし・θ 選択経路が test 窓に触れない
    # 構造的聖域ブロック（§11.2・docstring だけの紳士協定でなく・機械保証）。
    # calib_df は splits["calib"]（L472）から取り出された label-joined frame で・
    # test_df と同様に race_key/race_date/sales_start_entry_count/race_start_datetime を含む。
    if score_split == "test":
        X_score = X_test
        race_df_score = race_df_test
        score_split_label = "test"
    else:  # score_split == "calib"（入力検証済み・上記 guard で "test"/"calib" のみ許容）
        X_score = X_calib
        race_df_score = calib_df.loc[X_calib.index, :]
        score_split_label = "calib"
        if not race_df_score.index.equals(X_calib.index):
            raise RuntimeError(
                "train_and_predict: race_df_score.index != X_calib.index "
                "(Phase 11 codex HIGH#1・score_split='calib' 行整列保証)"
            )

    # --- model_version 採番 (D-10 / review HIGH#4 / Phase 11 codex HIGH#2) ---
    # original_model_type を渡すことで・race-relative short（lightgbm_rr/catboost_rr）が
    # model_version に保持される（base は学習パス・original は version 採番）。
    model_version = make_model_version(feature_snapshot_id, original_model_type, version_n)

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

    # --- base_model_type で分岐: trainer 呼出（Phase 11 codex HIGH#2） ---
    # base_model_type は _normalize_model_type で正規化済み（lightgbm_rr → lightgbm 等）。
    # 学習パスは binary base model のみを扱う（race-relative 補正は予測パス後段で適用）。
    if base_model_type == "lightgbm":
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
    elif base_model_type == "catboost":
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
            f"train_and_predict: 未知の model_type {original_model_type!r} "
            "(expected 'lightgbm', 'catboost', 'lightgbm_rr', or 'catboost_rr')"
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
    if base_model_type == "lightgbm":
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
    # Phase 11 codex HIGH#1: 予測対象は X_score（score_split で test/calib を切替）。
    # theta=None の場合は補正層をスキップし X_score で得た pred_proba をそのまま使用（A5）。
    if base_model_type == "lightgbm":
        # LightGBM: calibrated.predict_proba(X_score) で直接予測。
        # train_core と score 対象の categorical categories を _prepare_lightgbm_train_eval で統一する
        # (test_trainer.py test_no_target_encoding_leak と同一パターン・Rule 3 auto-fix:
        # LightGBM 4.6 が train/predict の categorical dtype 完全一致を要求する仕様への対応)。
        # train_lightgbm 内部の _prepare_lightgbm_train_eval(X_train_core, X_train_tail) が
        # train_core の categorical を確定するため・score 対象も train_core を基準に統一する。
        _, X_score_lgb = _prepare_lightgbm_train_eval(X_train_core, X_score)
        raw_pred = calib_result.calibrated.predict_proba(X_score_lgb)[:, 1]
        pred_proba = pd.Series(raw_pred, index=X_score.index, name="p_fukusho_hit")
    else:  # catboost
        # CatBoost: sort 済み Pool で予測 → align_predictions で元順序復元
        # Phase 11: 予測対象は X_score（test/calib で切替）。meta 列は race_df_score から取得。
        # REVIEW CR-02: LightGBM ブランチと同様・常に race_df_score を参照し・
        # test_df と race_df_score の暗黙の等価性（score_split="test" の時
        # race_df_score == race_df_test == test_df.loc[X_test.index, :]）に依存しない。
        # race_df_score.index == X_score.index を明示的に assert し・silent な
        # wrong-horse meta column alignment（.values が index 順に取るため・
        # index 集合が同一でも順序が異ると meta 列がずれる）を防止する。
        X_score_cb = X_score.copy()
        if not race_df_score.index.equals(X_score.index):
            raise RuntimeError(
                "train_and_predict: race_df_score.index != X_score.index "
                "(REVIEW CR-02・CatBoost 予測パス silent wrong-horse meta column alignment)"
            )
        for c in ("race_start_datetime", "race_key"):
            if c in race_df_score.columns:
                X_score_cb[c] = race_df_score.loc[X_score.index, c].values
        pool_score, sorted_score_idx = _prepare_catboost_pool(X_score_cb, sort=True)
        # CatBoost の CalibratedClassifierCV は predict_proba に DataFrame を渡すと
        # 内部で cat_features 認識なしに Pool を作ろうとして StringDtype の pd.NA で
        # "must be real number, not NAType" エラーになる (CatBoost + sklearn
        # CalibratedClassifierCV 互換性制約・Rule 3 auto-fix)。そのため base estimator
        # で Pool を直接予測し・calibrator (isotonic/sigmoid) を手動適用する。
        raw_pred_sorted = _catboost_calibrated_predict_proba(
            calib_result.calibrated, estimator, pool_score
        )
        pred_proba = align_predictions(
            pd.Series(raw_pred_sorted, index=sorted_score_idx, name="p_fukusho_hit"),
            sorted_score_idx,
            X_score.index,
        )

    # pred_proba の index が X_score.index と完全一致することを最終 assert (review HIGH#2)
    if not pred_proba.index.equals(X_score.index):
        raise RuntimeError(
            "train_and_predict: pred_proba.index != X_score.index after align "
            "(review HIGH#2・silent wrong-horse prediction)"
        )

    # --- Phase 11: race-relative 補正層（theta=None の場合はスキップ・A5 後方互換） ---
    # 両モデル（LightGBM/CatBoost）で同一の apply_race_relative_correction を呼ぶ
    # （SC#3 bit-identical・同一モデル同一 seed の再現性・D-01 binary 本体不変）。
    # theta は呼出側（run_phase11_evaluation.py）が calib slice で選んだ事前登録値を渡す・
    # orchestrator は theta を再選択しない（受け取った値をそのまま適用・§11.2 聖域）。
    # score_split="calib" の経路は θ 選択用・test 窓には触れない（構造的聖域ブロック）。
    # codex HIGH#6: sales_start_entry_count を race_df_score から必須取得（fallback なし）。
    # k=3 (8頭以上) / k=2 (5-7頭)・それ以外は RuntimeError（複勝発売なし・学習対象外・D-08）。
    if theta is not None:
        if "sales_start_entry_count" not in race_df_score.columns:
            raise RuntimeError(
                "train_and_predict: race_df_score に sales_start_entry_count 列がない"
                "（codex HIGH#6・data.py L135/371 で常に SELECT されるはず・"
                "fallback は導入しない・D-08/D-09 singleton 一意性）"
            )
        entry_counts = race_df_score.loc[X_score.index, "sales_start_entry_count"]
        # race_df_score は X_score と index が一致するが・sales_start_entry_count が
        # race 内で一意でない場合は RuntimeError（D-08/D-09・codex HIGH#6・fallback なし）。
        race_keys = race_df_score.loc[X_score.index, "race_key"].to_numpy()
        entry_counts_arr = entry_counts.to_numpy()
        k_per_race_arr = np.empty(len(entry_counts_arr), dtype=np.int64)
        # race 毎に k を確定（race 内で sales_start_entry_count が一意であることを検証）
        unique_race_keys, inverse = np.unique(race_keys, return_inverse=True)
        for ridx, rid in enumerate(unique_race_keys):
            mask = inverse == ridx
            ec_values = np.unique(entry_counts_arr[mask])
            if len(ec_values) != 1:
                raise RuntimeError(
                    f"train_and_predict: race {rid!r} 内で sales_start_entry_count が一意でない"
                    f"（codex HIGH#6・D-08/D-09）: ec_values={ec_values.tolist()}"
                )
            ec = int(ec_values[0])
            if ec >= 8:
                k_per_race_arr[mask] = 3
            elif 5 <= ec <= 7:
                k_per_race_arr[mask] = 2
            else:
                raise RuntimeError(
                    f"train_and_predict: race {rid!r} の sales_start_entry_count={ec} は"
                    "複勝発売なし（8頭以上=3・5-7頭=2・D-08・学習対象外）"
                )
        # 補正層呼出（race_relative.apply_race_relative_correction・D-06 step 6-8）
        p_final = apply_race_relative_correction(
            pred_proba.to_numpy(),
            theta=theta,
            k_per_race=k_per_race_arr,
            race_ids=race_keys,
        )
        pred_proba = pd.Series(p_final, index=X_score.index, name="p_fukusho_hit")

        # --- Phase 12 SC#1 / EV-01: p_lower 生成 (calib slice のみ・§11.2 聖域・C-12-02-1 HIGH) ---
        # RESEARCH.md Pattern 1 / 例1 完全呼出経路・calib slice のみで q_shrink を計算する経路と
        # 外部注入経路 (run_phase12_evaluation.py・Plan 04) の二経路のみ. test 窓 outcome を
        # q_shrink 計算に使う経路は構造的に触れない (score_split guard L449-455・codex HIGH#1).
        #
        # (a) score_split='calib' 経路 (θ選択経路と同一・codex HIGH#1):
        #     X_score == X_calib なので・p_final と y_calib は同一行集合. compute_p_lower_conformal_shrinkage
        #     に calib slice の p_final (= p_final_calib) と y_calib を渡して q_shrink を計算する.
        #     構造的聖域ブロック: 関数シグネチャが {p_final, y_calib, p_final_calib, q_level} のみで
        #     test 窓 outcome 系を取らない (Plan 01 で検証済み・tests/model/test_p_lower.py Test 2).
        # (b) score_split='test' 経路:
        #     theta is not None かつ p_lower_q_shrink is None の場合は RuntimeError (C-12-02-1 HIGH).
        #     test 窓で q_shrink を再計算する経路に滑るのを構造的に阻止.
        #     p_lower_q_shrink is not None の場合は外部注入値 (calib で計算済み) を使って
        #     max(0, p_final - q_shrink) で p_lower を算出 (§11.2 聖域・test 窓 outcome を使わない).
        # (c) theta=None/v1.0 binary の場合は p_lower=None (後方互換・p_lower_q_shrink は無視).
        if score_split == "calib":
            # calib slice のみで q_shrink 計算 (X_score == X_calib・p_final == p_final_calib).
            # y_calib は X_calib と index 整合 (review HIGH#2 で assert 済み・L498-505).
            p_lower_arr, q_shrink_value = compute_p_lower_conformal_shrinkage(
                p_final,
                y_calib.to_numpy(),
                p_final,  # score_split='calib' では score 対象 == calib slice のため p_final_calib == p_final
                q_level=p_lower_q_level,
            )
            pred_proba_lower_series = pd.Series(
                p_lower_arr, index=X_score.index, name="p_fukusho_hit_lower"
            )
        else:  # score_split == "test" (入力検証済み・L449-455 で "test"/"calib" のみ許容)
            if p_lower_q_shrink is None:
                # [C-12-02-1 HIGH] test 窓 outcome を使った q_shrink 再計算経路への滑りを構造的に阻止.
                raise RuntimeError(
                    "train_and_predict: score_split='test' with theta requires p_lower_q_shrink "
                    "(§11.2 聖域・外部注入のみ・test 窓 outcome を使った q_shrink 再計算は禁止). "
                    "呼出側 (run_phase12_evaluation.py・Plan 04) が score_split='calib' で計算した "
                    "q_shrink 値を p_lower_q_shrink 引数で渡すこと (C-12-02-1 HIGH)."
                )
            q_shrink_value = float(p_lower_q_shrink)
            # 外部注入 q_shrink を test 窓 p_final に適用 (§11.2 聖域・test 窓 outcome を使わない).
            p_lower_arr = np.maximum(0.0, p_final - q_shrink_value)
            pred_proba_lower_series = pd.Series(
                p_lower_arr, index=X_score.index, name="p_fukusho_hit_lower"
            )
        # Shared Pattern 4 fail-loud: pred_proba_lower と pred_proba の index/長さ不整合は RuntimeError.
        # (silent wrong-horse p_lower 防止・L700-704 と同一 idiom・Cycle 2 NEW HIGH-1 鏡像).
        if not pred_proba_lower_series.index.equals(pred_proba.index):
            raise RuntimeError(
                "train_and_predict: pred_proba_lower.index != pred_proba.index "
                "(Phase 12・Shared Pattern 4: silent wrong-horse p_lower prevented)"
            )
        if len(pred_proba_lower_series) != len(pred_proba):
            raise RuntimeError(
                f"train_and_predict: pred_proba_lower length {len(pred_proba_lower_series)} != "
                f"pred_proba length {len(pred_proba)} (Phase 12・Shared Pattern 4: length mismatch)"
            )
        p_lower_provenance = {
            "p_lower_q_level": float(p_lower_q_level),
            "p_lower_q_shrink": float(q_shrink_value),
            "p_lower_shrinkage_method": "calibration_residual_conformal",  # D-01
        }
    else:
        # theta=None / v1.0 binary: p_lower は NULL (後方互換・A5)・pred_proba_lower は None.
        pred_proba_lower_series = None
        p_lower_provenance = {
            "p_lower_q_level": None,
            "p_lower_q_shrink": None,
            "p_lower_shrinkage_method": None,
        }


    # --- predict_p_fukusho 呼出 (Cycle 2 NEW HIGH-1: pred_proba 注入で再予測防止) ---
    # pred_proba を明示的に渡すことで・CatBoost の aligned 予測値が predict_p_fukusho 内部で
    # 再予測されて捨てられる回帰 (Cycle 2 NEW HIGH-1) を閉塞。
    # predict_p_fukusho は注入時 len(pred_proba)==len(X) と index 一致を assert する。
    # Phase 11 codex HIGH#1: X_score / race_df_score / score_split_label で予測対象を切替。
    # Phase 11 codex HIGH#2: model_type には original_model_type を渡し race-relative short を保持。
    # theta 指定時は補正済み pred_proba が注入され・theta=None は v1.0 等価（A5）。
    pred_df = predict_p_fukusho(
        calib_result.calibrated,
        X_score,
        model_type=original_model_type,
        model_version=model_version,
        feature_snapshot_id=feature_snapshot_id,
        calib_method=calib_result.calib_method,
        race_df=race_df_score,
        split_label=score_split_label,
        as_of_datetime=as_of_dt,
        pred_proba=pred_proba,
        # Phase 12 SC#1 / EV-01 [C-12-02-2 MEDIUM]: pred_proba_lower 注入.
        # theta is not None の場合は compute_p_lower_conformal_shrinkage の戻り値を注入.
        # theta=None / v1.0 binary の場合は None で PREDICTION_COLUMNS の p_fukusho_hit_lower を
        # 全行 NULL にする (後方互換・A5・predict_p_fukusho が C-12-01-4 で機械保証).
        pred_proba_lower=pred_proba_lower_series,
        # Phase 11 codex HIGH#3: §19.1 metadata 3層ワイヤリング (WARNING#2 第2層)・
        # sentinel/事前登録値を predict_p_fukusho → PREDICTION_COLUMNS に伝播。
        # codex cycle-2 NEW HIGH#3: sentinel 既定値で v1.0 binary 呼出も安全。
        label_version=label_version,
        odds_snapshot_policy=odds_snapshot_policy,
        backtest_strategy_version=backtest_strategy_version,
    )

    # pred_df に backtest 用 meta 列（race_start_datetime / race_key）を付与
    # （backtest HIGH-1: _build_race_times_per_horse が [race_key, umaban, race_start_datetime] を
    # 使用し・select_odds_snapshot が race_start_datetime 基準で cutoff を計算するため）。
    # predict_p_fukusho の戻り値は PREDICTION_COLUMNS（prediction テーブル用・これら meta 列を
    # 含まない）だが・backtest の実データパスは pred_df から取得する。synthetic パス
    # （_build_synthetic_pred_df）は既に含むため・実データパスとの不整合を是正する。
    # race_start_datetime は race_df_score から直接・race_key は make_race_key で PK から構築
    # （snapshot に race_key 列は無く race_nkey のみ・make_race_key は race_nkey を使わない）。
    # race_df_score.index == pred_df.index (review HIGH#2) で values が安全に整列する。
    # prediction_load（DB 書込）は PREDICTION_COLUMNS のみ使用し・これら meta 列を無視
    # （列過多エラーなし）・_assert_valid_prediction_df は本付与前（PREDICTION_COLUMNS のみ）に
    # 実行済みで通過済み。
    # REVIEW WR-08: meta 列（race_start_datetime / race_key）は PREDICTION_COLUMNS に含まれない
    # 補助列であり・末尾に追加される。将来 PREDICTION_COLUMNS にこれらの列が追加された場合・
    # silent に PREDICTION_COLUMNS の列を上書きするのを防ぐため・meta 列が PREDICTION_COLUMNS
    # と重複しないことを付与前に assert する（fail-loud）。
    from src.model.data import make_race_key

    pred_df = pred_df.copy()
    _meta_cols_to_add = ("race_start_datetime", "race_key")
    _meta_in_prediction_cols = set(_meta_cols_to_add) & set(PREDICTION_COLUMNS)
    if _meta_in_prediction_cols:
        raise RuntimeError(
            "train_and_predict: meta 列 (race_start_datetime/race_key) が "
            f"PREDICTION_COLUMNS と重複 ({_meta_in_prediction_cols})・"
            "silent に PREDICTION_COLUMNS の列を上書きする可能性がある (REVIEW WR-08)。"
            "PREDICTION_COLUMNS 側にこれらの列を追加した場合は meta 付与経路を見直すこと。"
        )
    if "race_start_datetime" in race_df_score.columns:
        pred_df["race_start_datetime"] = race_df_score["race_start_datetime"].values
    if "race_key" not in pred_df.columns:
        pred_df["race_key"] = make_race_key(race_df_score).to_numpy()
    # REVIEW WR-08: meta 列付与後に・pred_df の先頭 len(PREDICTION_COLUMNS) 列が
    # PREDICTION_COLUMNS と完全一致すること（= PREDICTION_COLUMNS の列順序が meta 列で
    # 崩れていないこと）を assert する。downstream が pred_df[PREDICTION_COLUMNS] で
    # 抽出する際の安全性を機械保証する（load_predictions の _df_to_prediction_tuples は
    # PREDICTION_COLUMNS のみ抽出するが・他の downstream が columns == PREDICTION_COLUMNS
    # を前提とする場合の silent 誤作動を防止）。
    if list(pred_df.columns[: len(PREDICTION_COLUMNS)]) != list(PREDICTION_COLUMNS):
        raise RuntimeError(
            "train_and_predict: meta 列付与後に pred_df の先頭列が PREDICTION_COLUMNS "
            f"と一致しない (REVIEW WR-08)・got={list(pred_df.columns[: len(PREDICTION_COLUMNS)])}・"
            f"expected={list(PREDICTION_COLUMNS)}"
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
        # Phase 11 race-relative provenance（§19.1 再現性・codex HIGH#1）
        "race_relative_theta": theta,
        "score_split": score_split,
        # Phase 11 codex HIGH#3: §19.1 metadata provenance (呼出側から受け取った値をそのまま返却)
        "label_version": label_version,
        "odds_snapshot_policy": odds_snapshot_policy,
        "backtest_strategy_version": backtest_strategy_version,
        # Phase 12 SC#1 / EV-01: p_lower provenance (§19.1 再現性・C-12-02-1 HIGH).
        # theta=None/v1.0 binary の場合は全て None. race-relative の場合は事前登録値と calib 計算値.
        # score_split='test' の場合は p_lower_q_shrink 引数の値がそのまま記録される (外部注入・§11.2 聖域).
        "p_lower_q_level": p_lower_provenance["p_lower_q_level"],
        "p_lower_q_shrink": p_lower_provenance["p_lower_q_shrink"],
        "p_lower_shrinkage_method": p_lower_provenance["p_lower_shrinkage_method"],
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
    snapshot_id: str | None = None,
    theta: float | None = None,
    label_version: str = "unspecified",
    odds_snapshot_policy: str = "unspecified",
    backtest_strategy_version: str = "unspecified",
) -> None:
    """SC#4 reproduce smoke: 固定 seed + 固定 thread count + 固定 as_of_datetime で2回
    ``train_and_predict`` を呼出し・戻り prediction の ``p_fukusho_hit`` 列が
    ``np.array_equal`` (bit-identical) になることを検証する (review HIGH#7・§19.1 構造的ブロック)。

    Phase 5 D-03 / HIGH-A cycle-2: BT窓再学習 (``split_periods``) と BT-train-only
    category_map (``category_map``) を指定しても bit-identical が維持されることを検証。

    Phase 9 P03 REVIEW H1-b: ``snapshot_id`` も reproduce smoke に伝播し・両 snapshot で
    同一契約 (FEATURE_COLUMNS 選択含む) で bit-identical になることを検証。失敗時は ``RuntimeError``。

    Phase 11 codex HIGH#8 (``theta`` パラメータ・SC#3 bit-identical・同一モデル同一 seed の再現性):
    ``theta=None`` の場合は v1.0 binary の bit-identical (SC#4 回帰防止)。
    ``theta=float`` の場合は race-relative model の bit-identical (SC#3 実データ実証・
    codex MEDIUM・同一モデル同一 seed の再現性・LightGBM≠CatBoost cross-family 同一性でない)。
    ``theta=float`` の場合は ``model_type`` が ``"lightgbm_rr"`` / ``"catboost_rr"`` の
    いずれか (``_rr`` サフィックス) を渡すこと (11-03 双方向 guard・codex cycle-2 MEDIUM)。

    Phase 11 REVIEW CR-01 (§19.1 provenance 一貫性):
    ``label_version`` / ``odds_snapshot_policy`` / ``backtest_strategy_version`` も
    smoke に伝播し・両呼出で同一の §19.1 metadata 契約になることを保証する。
    これらは ``PREDICTION_COLUMNS`` に直接書き込まれ checksum の対象になるため・
    smoke が test 窓の実運用契約（``label_version="v1.0"`` 等）と同一条件で再現性を検証する。
    既定値 ``"unspecified"`` は ``train_and_predict`` の sentinel 既定値と同一。
    さらに ``pred_df`` 全体（provenance/as_of_datetime 列含む）が ``DataFrame.equals`` で
    bit-identical であることを検証し・provenance 列の混入も再現性検査の対象に含める。

    Parameters
    ----------
    model_type : str
        ``"lightgbm"`` または ``"catboost"`` (``theta=None`` 既定)・または
        ``"lightgbm_rr"`` / ``"catboost_rr"`` (``theta=float`` 指定時)。
    feature_df : pd.DataFrame
        label-joined frame (``train_and_predict`` と同一契約)。
    as_of_datetime : datetime
        固定 as_of_datetime (デフォルト ``FIXED_REPRODUCE_TS``・review HIGH#7)。
    split_periods : dict | None
        Phase 5 D-03 BT窓区間 (``None`` の場合は Phase 4 ハードコード)。
    category_map : dict | None
        Phase 5 HIGH-A cycle-2 BT-train-only frozen category map。
    snapshot_id : str | None
        Phase 9 P03 REVIEW H1-b: FEATURE_COLUMNS 選択用 snapshot_id。
    theta : float | None
        Phase 11 race-relative logit temperature。``None`` (既定) の場合は v1.0 binary 等価
        (A5・SC#4 回帰防止)。``float`` の場合は race-relative model の bit-identical を検証
        (SC#3・codex MEDIUM・同一モデル同一 seed の再現性)。
    label_version : str
        Phase 11 REVIEW CR-01: §19.1 provenance 列。既定 ``"unspecified"`` sentinel。
    odds_snapshot_policy : str
        Phase 11 REVIEW CR-01: §19.1 provenance 列。既定 ``"unspecified"`` sentinel。
    backtest_strategy_version : str
        Phase 11 REVIEW CR-01: §19.1 provenance 列。既定 ``"unspecified"`` sentinel。
    """
    common_kwargs = dict(
        feature_snapshot_id=feature_snapshot_id,
        version_n=version_n,
        seed=seed,
        as_of_datetime=as_of_datetime,
        split_periods=split_periods,
        category_map=category_map,
        snapshot_id=snapshot_id,
        theta=theta,
        label_version=label_version,
        odds_snapshot_policy=odds_snapshot_policy,
        backtest_strategy_version=backtest_strategy_version,
    )
    result1 = train_and_predict(feature_df, model_type=model_type, **common_kwargs)
    result2 = train_and_predict(feature_df, model_type=model_type, **common_kwargs)

    pred1 = result1["pred_df"]["p_fukusho_hit"].to_numpy()
    pred2 = result2["pred_df"]["p_fukusho_hit"].to_numpy()

    if not np.array_equal(pred1, pred2):
        raise RuntimeError(
            f"_assert_deterministic({model_type}, theta={theta}): SC#3/SC#4 reproduce smoke 違反 "
            "(review HIGH#7 / §19.1 構造的ブロック・Phase 完了不可): "
            f"seed={seed} + 固定 thread count + 固定 as_of_datetime={as_of_datetime} "
            "で2回 train_and_predict した p_fukusho_hit が bit-identical でない。"
        )

    # Phase 11 REVIEW CR-01: pred_df 全体（provenance/as_of_datetime 列含む）の bit-identical 検証。
    # as_of_datetime 固定化の意義（checksum bit-identical・永続化パスの再現性）を機械保証する。
    # 列単位の np.array_equal だけでは as_of_datetime 列混入の再現性破壊を検出できないため・
    # DataFrame.equals で全列の値・dtype・index を含む完全同一性を検証する。
    if not result1["pred_df"].equals(result2["pred_df"]):
        raise RuntimeError(
            f"_assert_deterministic({model_type}, theta={theta}): SC#3/SC#4 reproduce smoke 違反 "
            "(REVIEW CR-01 / §19.1・provenance 列含む pred_df 全体の bit-identical): "
            f"seed={seed} + 固定 as_of_datetime={as_of_datetime} + label_version={label_version} "
            f"+ odds_snapshot_policy={odds_snapshot_policy} "
            f"+ backtest_strategy_version={backtest_strategy_version} "
            "で2回 train_and_predict した pred_df 全体が bit-identical でない。"
        )


__all__ = [
    "FIXED_REPRODUCE_TS",
    "train_and_predict",
    "_merge_params",
    "_apply_category_map",
    "_normalize_model_type",
    "_assert_deterministic",
]
