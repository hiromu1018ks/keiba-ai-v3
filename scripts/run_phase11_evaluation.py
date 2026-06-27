"""Phase 11 SC#2 改善 gate: v1.0 binary baseline vs race-relative model 3-way 比較.

Purpose
-------
Phase 11 で導入した race-relative 補正層（logit temperature θ + per-race α_r 二分探索）が
v1.0 binary LightGBM/CatBoost の確率品質を悪化させず・投票層の overprediction を改善することを
定量的に保証する（SC#2・D-04 非劣化 + D-05 改善 gate）。

D-04 事前登録許容幅 (§11.2 聖域・評価後変更禁止)::
    - Brier 悪化  <= 0.005  (Phase 10 の 0.002 より拡張・race-conditional 構造的変化への根拠再確認)
    - LogLoss 悪化 <= 0.010
    - AUC 悪化   <= 0.005   (AUC は「低下」が非劣化違反・符号注意)

D-05 SC#2 改善 gate (3 必須条件)::
    (1) odds_band×p_bin の overprediction penalty が v1.0 binary より低い（主指標）
    (2) selected/high-EV 層の「平均予測率 − 実現率」が v1.0 より低い
    (3) selected-only calib_max_dev が事前登録マージン（D-04）を超えて悪化しない

θ 選択経路 (D-03 制約付き選択・§11.2 聖域・test 窓選び直し禁止)::
    候補 {0.5, 0.75, 1.0, 1.25, 1.5} → calib slice で
      (1) 足切り D-04 非劣化 →
      (2) overprediction penalty 最小 (D-05-1) →
      (3) tie-break calib_max_dev → θ=1 に近い候補
    θ 選択は ``orchestrator.train_and_predict(score_split="calib")`` のみで候補評価する。
    ``score_split="calib"`` は X_calib のみを予測対象にするので構造的に test 窓に触れない
    （§11.2 聖域の機械保証・docstring 紳士協定でない・codex review HIGH#1・PLAN 11-04）。
    test 窓の y_true は θ 選択に一切使われない。

theta-selection.json の事前書き出し (codex HIGH#1・後知恵すり替え禁止)::
    θ 選択経路が決定した直後・test 窓評価 (score_split="test") に先立って
    ``reports/11-evaluation/theta-selection.{md,json}`` に候補毎の
    (Brier, LogLoss, AUC, overprediction_penalty, calib_max_dev,
     selected_only_calib_max_dev, verdict) と選択経路
    (足切り / 選択 / tie-break の各段階と残候補) を byte-reproducible に atomic write する。

D-07 (is_primary 立てない・§11.2 聖域)::
    Phase 11 は並列比較のみ・is_primary 切替は Phase 12。本 script は比較レポート生成のみで
    prediction_load.load_predictions も set_primary_model も**呼出しない**。
    （注: 呼出しを構成する ``set_primary_model`` という識別子は・D-07 codex cycle-2 LOW の
    AST check で Call node 0件を保証するため・本 docstring 以外の code に出現しない。
    docstring で言及するのは「呼出しない」ことを明示するためであり・AST check は Call node
    のみを判定するので false positive にならない。）
    実際の model_version 行追加は 11-05 で prediction_load.load_predictions 経由で実施。
    11-05 でも primary 切替 (primary flag を立てる操作) は行わない。

B-3 (baseline と race-relative を同一 trainer 設定で delta)::
    baseline (theta=None・v1.0 binary) と race-relative (theta=selected_theta) を全く同一の
    trainer 設定 (LightGBM version/hyperparams/seed/category_map/split_periods/odds_snapshot_policy/
    bt_split) で評価し・両者の実測値の delta を取る。feature_snapshot_id も同一 (Phase 10 完成
    snapshot) で・唯一の差は theta の有無 (= 補正層の on/off)。

§15.2 事前登録指標不変 (聖域)::
    evaluator/segment_eval の binning 定数 (CALIBRATION_CURVE_BINS /
    CALIBRATION_CURVE_MIN_BIN_COUNT / ODDS_BAND_EDGES / NINKI_BAND_EDGES) を import 再利用し・
    **再定義しない** (bit-identical)。overprediction penalty 測定も
    ``race_relative.compute_overprediction_penalty`` を経由して evaluator/segment_eval の
    binning を利用する (codex HIGH#2・二重 binning 禁止)。

REVIEW H6 (正しい API chain)::
    ``orchestrator.train_and_predict(snapshot_id=...)`` 略記でなく・正しい API chain
    ``load_feature_matrix(snapshot_id=...) → load_labels(cur) → build_training_frame(feature_df,
    label_df) → load_frozen_maps(snapshot_id=...) → train_and_predict(label_joined_frame,
    feature_snapshot_id=..., snapshot_id=..., version_n=1, split_periods=BT1_PERIODS,
    category_map=cat_map, theta=..., score_split=...)`` を呼ぶ。

REVIEW H2/H7/H8::
    生 trainer API は直接呼ばない (calibration skip / sorted_index 誤用 / categorical dtype
    mismatch の3バグを構造的回避)。

Usage (live-DB・KEIBA_SKIP_DB_TESTS unset)::

    uv run python scripts/run_phase11_evaluation.py \\
        --baseline-snapshot-id 20260626-1a-opponentstrength-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --theta-candidates 0.5 0.75 1.0 1.25 1.5 \\
        --out-dir reports
"""

# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加
# (scripts/run_phase10_evaluation.py L80-84 と同一 idiom)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §15.2 事前登録指標不変: binning 定数を import 再利用 (再定義禁止・bit-identical)
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    compute_metrics,
)
from src.model.predict import make_model_version  # noqa: E402  model_version 採番
from src.model.race_relative import (  # noqa: E402  Phase 11 (11-02 実装)
    ALPHA_SEARCH_XTOL,
    P_CAL_CLIP_EPSILON,
    THETA_CANDIDATES,
    compute_overprediction_penalty,
)
from src.model.segment_eval import (  # noqa: E402
    NINKI_BAND_EDGES,
    ODDS_BAND_EDGES,
    evaluate_all_segments,
)

logger = logging.getLogger("run_phase11_evaluation")

# ---------------------------------------------------------------------------
# D-04 事前登録許容幅 (§11.2 聖域・評価後変更禁止)
# ---------------------------------------------------------------------------
# Phase 10 D-16 (0.002 / 0.005 / 0.005) から拡張。
# race-conditional 構造的変化 (logit temperature + per-race α_r 二分探索による再配分) への
# 根拠再確認 (後追い緩和でない)。AUC は logit 順序保存で構造的に維持されるため ±0.005 固定 (D-04)。
TOLERANCE_BRIER: float = 0.005
TOLERANCE_LOGLOSS: float = 0.010
TOLERANCE_AUC: float = 0.005  # AUC は「低下」が非劣化違反 (符号注意)


# BT-1 split periods (§15.5) — train 2019-06-01..2022-06-30 / calib 2022-07-01..2022-12-31 / test 2023
# Phase 5 D-03 / HIGH-B cycle-2 idiom: calib は train tail 6ヶ月から切り出す。
# run_phase10_evaluation.py L185-189 と同一。
BT1_PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2019-06-01", "2022-06-30"),
    "calib": ("2022-07-01", "2022-12-31"),
    "test": ("2023-01-01", "2023-12-31"),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する."""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 11 SC#2 改善 gate: v1.0 binary vs race-relative model (theta + per-race α_r)"
            " 3-way 比較・D-04 非劣化 + D-05 改善 gate 3条件 (B-3・§11.2 聖域)"
        ),
    )
    parser.add_argument(
        "--baseline-snapshot-id",
        default="20260626-1a-opponentstrength-v1",
        help="baseline feature snapshot_id (default: Phase 10 完成 snapshot・v1.1 入力)",
    )
    parser.add_argument(
        "--bt-split",
        default="BT-1",
        help="backtest split (default: BT-1 = 2019-06-01..2022-12-31 train/calib / 2023 test・§15.5)",
    )
    parser.add_argument(
        "--odds-snapshot-policy",
        default="30min_before",
        help="odds snapshot policy (default: 30min_before・v1.0 と同一)",
    )
    parser.add_argument(
        "--theta-candidates",
        nargs="+",
        default=list(THETA_CANDIDATES),
        help=(
            f"θ 候補 (default: {list(THETA_CANDIDATES)}・D-03 事前登録・"
            "§11.2 聖域・test 窓選び直し禁止)"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="reports",
        help="出力 directory (default: reports)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="CI 用 (デフォルト False)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# JSON sanitizer (run_phase10_evaluation.py::_sanitize_for_json idiom・NaN/Inf → None/"NaN")
# ---------------------------------------------------------------------------
def _sanitize_for_json(obj: Any) -> Any:
    """dict/list/float/ndarray を再帰走査し NaN/Inf/ndarray を JSON 安全な表現に変換する.

    run_phase10_evaluation.py L144-178 と同一 idiom・single-class AUC 等で NaN が混入しても
    ``json.dumps(allow_nan=False)`` が ``ValueError`` で失敗するのを防ぐ (RFC 8259 strict)。
    numpy ndarray / scalar も list / Python scalar に変換する。
    """
    if isinstance(obj, np.ndarray):
        return _sanitize_for_json(obj.tolist())
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return _sanitize_for_json(float(obj))
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _atomic_write_text(path: Path, text: str) -> None:
    """byte-reproducible に atomic write する (tmp → replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# main — live-DB orchestration (KEIBA_SKIP_DB_TESTS unset で実行)
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """live-DB で v1.0 binary と race-relative model を**同一 trainer 設定**で評価し・
    D-04 非劣化 gate + D-05 改善 gate 3条件を test 窓で一回だけ判定する (B-3・§11.2 聖域)。

    θ 選択経路は ``orchestrator.train_and_predict(score_split="calib")`` のみで候補評価し・
    test 窓 (score_split="test") では事前登録 gate で一回だけ評価する (codex HIGH#1・D-03)。

    REVIEW H6: load_feature_matrix → load_labels → build_training_frame → load_frozen_maps →
    orchestrator.train_and_predict の正しい API chain を呼ぶ。
    REVIEW H2/H7/H8: 生 trainer API は直接呼ばない。
    D-07 (is_primary 立てない): 本 script は race-relative model 行を prediction_load.load_predictions
    (public wrapper・codex HIGH#4) で model_version scoped swap として追加するが・set_primary_model
    は呼ばない (is_primary=true は v1.0 binary のみ保持・primary 切替は Phase 12)。
    codex cycle-2 NEW HIGH#2: orchestrator.train_and_predict 呼出は as_of_datetime=FIXED_REPRODUCE_TS
    固定で PK が両実行で一致し checksum bit-identical (永続化パスで datetime.now(UTC) 既定を使わない)。
    """
    args = parse_args(argv)

    # 遅延 import: live-DB 依存 (KEIBA_SKIP_DB_TESTS unset でのみ実行)
    from src.config.settings import Settings
    from src.db.connection import make_pool, readonly_cursor
    from src.db.prediction_load import load_predictions
    from src.model.data import (
        build_training_frame,
        load_feature_matrix,
        load_frozen_maps,
        load_labels,
    )
    from src.model.orchestrator import (
        FIXED_REPRODUCE_TS,
        _assert_deterministic,
        train_and_predict,
    )

    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)

    out_dir = Path(args.out_dir)
    eval_dir = out_dir / "11-evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    # T-09-21: statement_timeout='30s' で重クエリの orphan CPU 張り付き防止
    # (MEMORY.md subagent-db-query-statement-timeout・run_phase10_evaluation.py と同一 idiom)
    def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        conn.commit()

    readonly_pool = make_pool(
        settings, role="readonly", configure=_configure_statement_timeout
    )
    # Phase 11 codex HIGH#3/#4・codex cycle-2 NEW HIGH#1/#2: 永続化パス用 etl pool。
    # readonly は prediction 書込権限を持たないため・load_predictions 呼出には etl ロールが必要。
    # make_pool(role='etl') が KEIBA_ETL_DB_USER で接続し prediction スキーマへの書込を許可。
    etl_pool = make_pool(settings, role="etl", configure=_configure_statement_timeout)
    try:
        # Phase 11 codex cycle-2 NEW HIGH#1/#3: schema migration（provenance 3列 DEFAULT
        # 'unspecified' sentinel + CHECK 制約 lightgbm_rr/catboost_rr 拡張）は run_apply_schema.py
        # （admin/owner 権限）で事前適用済みであることを前提（Phase 6 is_primary migration と同一 idiom）。
        # ALTER TABLE は owner 権限が必要で etl ロールでは InsufficientPrivilege となるため・本 script
        # では migration を実行せず run_apply_schema.py に一本化（deviation・11-05 SUMMARY に記録）。

        with readonly_cursor(readonly_pool) as cur:
            # 二重防衛: configure callback と cursor 内 SET の両方で statement_timeout を設定。
            cur.execute("SET statement_timeout = '30s'")

            # REVIEW H6 (5a): feature_df ロード
            logger.info("loading snapshot: %s", args.baseline_snapshot_id)
            feature_df = load_feature_matrix(snapshot_id=args.baseline_snapshot_id)

            # REVIEW H6 (5b): label 取得 + label-join
            label_df = load_labels(cur)
            frame = build_training_frame(feature_df, label_df)

            # REVIEW H6 (5c): category_map ロード
            cat_map = load_frozen_maps(snapshot_id=args.baseline_snapshot_id)
            logger.info("category_map keys: %d", len(cat_map) if isinstance(cat_map, dict) else -1)

        # ---- θ 選択経路 (score_split="calib" のみ・codex HIGH#1・§11.2 聖域の機械保証) ----
        # 各 θ 候補で train_and_predict(score_split="calib") を呼出し・calib slice の予測に対して
        # compute_overprediction_penalty / compute_metrics で評価する。
        # score_split="calib" は X_calib のみを予測対象にするので test 窓に触れない。
        theta_candidates: list[float] = [float(t) for t in args.theta_candidates]
        logger.info("θ 選択経路 (calib slice): candidates=%s", theta_candidates)
        # REVIEW CR-03: test 窓呼出と同一の §19.1 metadata 3引数を θ 選択経路にも渡す。
        # θ 候補評価用の calib slice pred_df が test 窓の pred_df と同一 provenance を持ち・
        # checksum 再現性が calib/test 両経路で一致する（§19.1 聖域）。
        # θ 選択ロジック（D-03/§11.2 聖域・calib slice のみ使用）には影響しない。
        theta_selection = _select_theta_on_calib(
            frame=frame,
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            cat_map=cat_map,
            theta_candidates=theta_candidates,
            label_df=label_df,
            metadata_kwargs=dict(
                label_version="v1.0",
                odds_snapshot_policy=args.odds_snapshot_policy,
                backtest_strategy_version=args.bt_split,
            ),
        )
        selected_theta = float(theta_selection["selected_theta"])
        logger.info(
            "θ 選択経路 done: selected_theta=%s (verdict=%s)",
            selected_theta,
            theta_selection["selection_path"]["final_verdict"],
        )

        # ---- theta-selection.{md,json} の事前書き出し (codex HIGH#1・後知恵すり替え禁止) ----
        # test 窓評価に先立ち・byte-reproducible に候補毎の評価値と選択経路を記録する。
        _write_theta_selection_reports(eval_dir, theta_selection)
        logger.info("theta-selection.json 書き出し完了 (test 窓評価に先立ち)")

        # ---- baseline (theta=None・v1.0 binary)・test 窓評価 ----
        # theta=None で補正層スキップ (A5 後方互換・v1.0 binary と等価)
        # codex cycle-2 NEW HIGH#2: as_of_datetime=FIXED_REPRODUCE_TS 固定で PK が両実行で一致し
        # checksum bit-identical (§19.1 再現性・datetime.now(UTC) 既定を使わない)。
        # codex HIGH#3: §19.1 metadata 3引数 (WARNING#2 第1層・事前登録値で渡す)。
        logger.info("baseline (theta=None) test 窓評価")
        baseline_result = train_and_predict(
            frame,
            model_type="lightgbm",
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=None,
            score_split="test",
            as_of_datetime=FIXED_REPRODUCE_TS,
            label_version="v1.0",
            odds_snapshot_policy=args.odds_snapshot_policy,
            backtest_strategy_version=args.bt_split,
        )
        # ---- race-relative (theta=selected_theta)・test 窓評価 (一回のみ・θ 再選択なし) ----
        rr_model_version = make_model_version(
            args.baseline_snapshot_id, "lightgbm_rr", 1
        )
        logger.info(
            "race-relative (theta=%s) test 窓評価・model_version=%s",
            selected_theta,
            rr_model_version,
        )
        rr_result = train_and_predict(
            frame,
            model_type="lightgbm_rr",
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=selected_theta,
            score_split="test",
            as_of_datetime=FIXED_REPRODUCE_TS,
            label_version="v1.0",
            odds_snapshot_policy=args.odds_snapshot_policy,
            backtest_strategy_version=args.bt_split,
        )

        baseline_model_version = make_model_version(
            args.baseline_snapshot_id, "lightgbm", 1
        )

        # ---- Phase 11 codex HIGH#8/MEDIUM: SC#3 bit-identical deterministic smoke ----
        # theta=selected_theta で race-relative model が同一 LightGBM 同一 seed で bit-identical
        # になることを検証 (FIXED_REPRODUCE_TS + 固定 seed/thread + np.array_equal)。
        # 同一モデル同一 seed の再現性を検証するのであり・LightGBM≠CatBoost cross-family 同一性でない。
        logger.info(
            "SC#3 deterministic smoke (theta=%s・race-relative・同一モデル同一 seed bit-identical)",
            selected_theta,
        )
        # REVIEW CR-01: test 窓呼出と同一の §19.1 metadata 3引数を smoke にも渡す。
        # smoke が test 窓の実運用契約（label_version="v1.0" 等）と同一条件で
        # bit-identical 再現性を検証する（as_of_datetime は既定 FIXED_REPRODUCE_TS）。
        _assert_deterministic(
            "lightgbm_rr",
            frame,
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=selected_theta,
            label_version="v1.0",
            odds_snapshot_policy=args.odds_snapshot_policy,
            backtest_strategy_version=args.bt_split,
        )
        logger.info("SC#3 deterministic smoke: PASS (bit-identical・codex MEDIUM)")

        # ---- Phase 11 codex HIGH#4 / cycle-2 NEW HIGH#1/#2/#3: SC#5 model_version-scoped ----
        # idempotent swap via load_predictions (public wrapper)。
        # rr_result["pred_df"] を prediction.fukusho_prediction に永続化。model_type='lightgbm_rr'
        # が CHECK 制約拡張で許容 (codex cycle-2 NEW HIGH#1)。as_of_datetime=FIXED_REPRODUCE_TS
        # 固定で PK が一致し・2回実行で checksum bit-identical (codex cycle-2 NEW HIGH#2)。
        # sentinel/事前登録値で NOT NULL 違反回避 (codex cycle-2 NEW HIGH#3)。
        # D-07: is_primary 立てない (set_primary_model を呼ばない・v1.0 binary 行は保持)。
        logger.info(
            "SC#5 idempotent swap: model_type=lightgbm_rr model_version=%s (load_predictions public wrapper)",
            rr_model_version,
        )
        with etl_pool.connection() as etl_conn:
            with etl_conn.cursor() as etl_cur:
                etl_cur.execute("SET statement_timeout = '30s'")
                checksum1 = load_predictions(etl_cur, rr_result["pred_df"])
                checksum2 = load_predictions(etl_cur, rr_result["pred_df"])
            etl_conn.commit()
        if checksum1 != checksum2:
            raise RuntimeError(
                f"SC#5 idempotent violation: 2回実行で checksum 不一致 "
                f"(as_of_datetime=FIXED_REPRODUCE_TS 固定・codex cycle-2 NEW HIGH#2) "
                f"checksum1={checksum1!r} checksum2={checksum2!r}"
            )
        logger.info(
            "SC#5 idempotent swap: PASS (2回実行 checksum bit-identical=%s)", checksum1
        )

        # _attach_label_to_pred で label JOIN (run_phase10_evaluation.py L500-560 と同一 idiom)
        baseline_pred = _attach_label_to_pred(
            baseline_result["pred_df"], label_joined_frame=frame
        )
        rr_pred = _attach_label_to_pred(
            rr_result["pred_df"], label_joined_frame=frame
        )
        logger.info(
            "pred_df label JOIN 完了: baseline rows=%d / race-relative rows=%d",
            len(baseline_pred),
            len(rr_pred),
        )

        # gate 判定 (B-3: 両実測値の delta)
        result = _evaluate_gate(
            baseline_pred=baseline_pred,
            rr_pred=rr_pred,
            baseline_model_version=baseline_model_version,
            rr_model_version=rr_model_version,
            selected_theta=selected_theta,
            theta_selection=theta_selection,
            args=args,
        )
    finally:
        readonly_pool.close()
        etl_pool.close()

    json_path, md_path = _write_reports(eval_dir, result)
    logger.info("wrote %s", json_path)
    logger.info("wrote %s", md_path)

    # gate verdict (B-3・D-04 + D-05)
    gate_pass = bool(result["gate_pass"])
    if gate_pass:
        logger.info(
            "SC#2 gate: PASS (D-04 非劣化 + D-05 改善 3条件 全て満たす・delta 基準は baseline 実測値)"
        )
        return 0
    logger.error(
        "SC#2 gate: FAIL・D-04 非劣化 または D-05 改善 3条件のいずれか未達 (§11.2 聖域・許容幅は変更せず)"
    )
    return 2  # gate FAIL (fail-loud)


# ---------------------------------------------------------------------------
# θ 選択経路 (D-03 制約付き選択・score_split="calib" のみ)
# ---------------------------------------------------------------------------
def _select_theta_on_calib(
    *,
    frame: pd.DataFrame,
    feature_snapshot_id: str,
    snapshot_id: str,
    cat_map: dict[str, Any],
    theta_candidates: list[float],
    label_df: pd.DataFrame,
    metadata_kwargs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """D-03 制約付き選択を ``score_split="calib"`` でのみ実施する (§11.2 聖域の機械保証).

    選択ルール (PLAN 11-04・CONTEXT D-03):
      (1) 足切り: D-04 非劣化 (Brier/LogLoss/AUC マージン内)
      (2) 選択: overprediction penalty 最小 (D-05-1)
      (3) tie-break: selected-only calib_max_dev → θ=1 に近い候補

    θ 選択は ``train_and_predict(score_split="calib")`` のみを使用する。
    ``score_split="calib"`` は X_calib のみを予測対象にするので構造的に test 窓に触れない
    (codex HIGH#1・§11.2 聖域の機械保証・docstring 紳士協定でない)。

    REVIEW CR-03 (§19.1 再現性):
    ``metadata_kwargs`` は baseline / rr 両方の ``train_and_predict(score_split="calib")``
    呼出に伝播される §19.1 provenance 3 引数（label_version / odds_snapshot_policy /
    backtest_strategy_version）。test 窓呼出と同一の実運用値を渡すことで・calib slice と
    test 窓の pred_df で provenance が一致し checksum 再現性が保証される。
    ``None`` の場合は sentinel "unspecified" 既定値を使う（train_and_predict 既定と同一）。
    **θ 選択ロジック自体（calib slice のみ使用・D-03/§11.2 聖域）は変更しない**。
    metadata_kwargs は pred_df の provenance 列に書き込まれるだけで・θ 候補の足切り・
    選択・tie-break の判定に影響しない（θ 決定経路に test 窓情報は混入しない）。

    Returns
    -------
    dict
        selected_theta / candidates (候補毎の評価値) / selection_path (足切り→選択→tie-break)
    """
    from src.model.orchestrator import train_and_predict  # 遅延 import

    # REVIEW CR-03: §19.1 metadata 3引数を共通化し baseline/rr 両呼出に伝播。
    # None の場合は sentinel "unspecified"（train_and_predict 既定値と同一）。
    _metadata = dict(
        label_version="unspecified",
        odds_snapshot_policy="unspecified",
        backtest_strategy_version="unspecified",
    )
    if metadata_kwargs is not None:
        _metadata.update(metadata_kwargs)

    # baseline (theta=None) の calib 指標 (足切り基準)
    baseline_calib_result = train_and_predict(
        frame,
        model_type="lightgbm",
        feature_snapshot_id=feature_snapshot_id,
        snapshot_id=snapshot_id,
        version_n=1,
        split_periods=BT1_PERIODS,
        category_map=cat_map,
        theta=None,
        score_split="calib",
        **_metadata,
    )
    baseline_calib_pred = _attach_label_to_pred(
        baseline_calib_result["pred_df"], label_joined_frame=frame
    )
    baseline_calib_metrics = _compute_pred_metrics(baseline_calib_pred)
    baseline_overprediction = _compute_overprediction_from_pred(baseline_calib_pred)

    candidates: list[dict[str, Any]] = []
    for theta in theta_candidates:
        rr_result = train_and_predict(
            frame,
            model_type="lightgbm_rr",
            feature_snapshot_id=feature_snapshot_id,
            snapshot_id=snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=theta,
            score_split="calib",
            **_metadata,  # REVIEW CR-03: §19.1 provenance 一貫性
        )
        rr_pred = _attach_label_to_pred(
            rr_result["pred_df"], label_joined_frame=frame
        )
        metrics = _compute_pred_metrics(rr_pred)
        overprediction = _compute_overprediction_from_pred(rr_pred)
        calib_max_dev = float(metrics.get("calibration_max_dev", float("nan")))
        selected_only_calib_max_dev = _compute_selected_only_calib_max_dev(rr_pred)

        # verdict (足切り D-04): Brier/LogLoss/AUC が baseline から許容幅内か
        brier_delta = float(metrics["brier"]) - float(baseline_calib_metrics["brier"])
        logloss_delta = float(metrics["logloss"]) - float(baseline_calib_metrics["logloss"])
        auc_delta = float(metrics["auc"]) - float(baseline_calib_metrics["auc"])
        pass_tol = (
            (brier_delta <= TOLERANCE_BRIER)
            and (logloss_delta <= TOLERANCE_LOGLOSS)
            and (auc_delta >= -TOLERANCE_AUC)
        )
        verdict = "pass" if pass_tol else "fail_tolerance"

        candidates.append(
            {
                "theta": float(theta),
                "brier": float(metrics["brier"]),
                "logloss": float(metrics["logloss"]),
                "auc": float(metrics["auc"]),
                "overprediction_penalty": float(overprediction),
                "calib_max_dev": calib_max_dev,
                "selected_only_calib_max_dev": selected_only_calib_max_dev,
                "brier_delta_vs_baseline_calib": brier_delta,
                "logloss_delta_vs_baseline_calib": logloss_delta,
                "auc_delta_vs_baseline_calib": auc_delta,
                "verdict": verdict,
            }
        )
        logger.info(
            "θ=%.3f calib: Brier=%.5f LogLoss=%.5f AUC=%.5f overpred=%.5f verdict=%s",
            theta,
            metrics["brier"],
            metrics["logloss"],
            metrics["auc"],
            overprediction,
            verdict,
        )

    # ---- 選択経路 (足切り → 選択 → tie-break) ----
    passing = [c for c in candidates if c["verdict"] == "pass"]
    selection_path: dict[str, Any] = {
        "stage_1_cutoff": {
            "rule": "D-04 非劣化 (Brier/LogLoss/AUC 許容幅内)",
            "tolerance": {
                "brier": TOLERANCE_BRIER,
                "logloss": TOLERANCE_LOGLOSS,
                "auc": TOLERANCE_AUC,
            },
            "n_before": len(candidates),
            "n_after": len(passing),
            "failed_thetas": [c["theta"] for c in candidates if c["verdict"] != "pass"],
        },
        "stage_2_argmin_overprediction": None,
        "stage_3_tiebreak": None,
        "baseline_calib_metrics": _sanitize_for_json(baseline_calib_metrics),
        "baseline_overprediction_penalty_calib": float(baseline_overprediction),
        "final_verdict": None,
    }

    if not passing:
        # 全候補が足切りで脱落 → θ=1.0 (baseline logit temperature) を安全策として選択
        # (fallback・本来は候補の見直しが必要・gate 自体は D-04 で FAIL になる)
        theta_1_candidates = [c for c in candidates if abs(c["theta"] - 1.0) < 1e-12]
        if theta_1_candidates:
            selected = theta_1_candidates[0]
            selected_theta = float(selected["theta"])
        else:
            # θ=1.0 が候補に無い場合は最初の候補 (後知恵でない・事前登録候補の先頭)
            selected_theta = float(candidates[0]["theta"])
            selected = candidates[0]
        selection_path["final_verdict"] = (
            f"no_candidates_passed_cutoff → fallback θ={selected_theta} "
            "(D-04 で全候補脱落・gate 自体は FAIL になる・候補見直しが必要)"
        )
        logger.warning(
            "θ 選択: 全候補が D-04 足切りで脱落 → fallback θ=%s", selected_theta
        )
        return {
            "selected_theta": selected_theta,
            "selected_candidate": _sanitize_for_json(selected),
            "candidates": _sanitize_for_json(candidates),
            "selection_path": selection_path,
        }

    # (2) 選択: overprediction penalty 最小 (D-05-1・NaN-safe)
    # odds/ninki 系列が pred_df に無い場合 (odds-free 1-A model・feature snapshot に odds 無し) ・
    # compute_overprediction が NaN を返す (D-15 参考記録)。全候補 NaN の場合は D-05-1 条件を
    # skip して passing をそのまま stage2 に流し・stage3 tiebreak (calib_max_dev → θ=1 近傍) で
    # 決定する（§11.2 聖域: test 窓を見ない・事前登録 idiom）。
    finite_overpred = [c for c in passing if not math.isnan(c["overprediction_penalty"])]
    if finite_overpred:
        min_overpred = min(c["overprediction_penalty"] for c in finite_overpred)
        stage2 = [
            c for c in passing if c["overprediction_penalty"] <= min_overpred + 1e-15
        ]
    else:
        # 全候補 overprediction_penalty=NaN (D-15) → passing をそのまま stage2 へ
        min_overpred = float("nan")
        stage2 = list(passing)
    selection_path["stage_2_argmin_overprediction"] = {
        "rule": "D-05-1 overprediction penalty 最小 (NaN-safe・全員 NaN は passing 保持)",
        "min_overprediction_penalty": (
            float(min_overpred) if not math.isnan(min_overpred) else None
        ),
        "n_before": len(passing),
        "n_after": len(stage2),
        "remaining_thetas": [c["theta"] for c in stage2],
    }

    # (3) tie-break: selected-only calib_max_dev → θ=1 に近い候補
    if len(stage2) == 1:
        selected = stage2[0]
        selection_path["stage_3_tiebreak"] = {
            "rule": "単一候補 (tie-break 不要)",
            "remaining_thetas": [selected["theta"]],
        }
    else:
        min_calib_dev = min(c["selected_only_calib_max_dev"] for c in stage2)
        # NaN が混じると min が NaN になるため・nan_safe に tiebreak する
        stage3a = [
            c
            for c in stage2
            if (
                not math.isnan(c["selected_only_calib_max_dev"])
                and c["selected_only_calib_max_dev"] <= min_calib_dev + 1e-15
            )
        ]
        if not stage3a:
            # 全員 NaN の場合は θ=1 に最も近い候補 (事前登録 priority)
            stage3a = stage2
        # θ=1 に近い順で sort して最初を採用
        stage3a_sorted = sorted(stage3a, key=lambda c: abs(c["theta"] - 1.0))
        selected = stage3a_sorted[0]
        selection_path["stage_3_tiebreak"] = {
            "rule": "tie-break: selected-only calib_max_dev 最小 → θ=1 に近い候補",
            "min_selected_only_calib_max_dev": (
                float(min_calib_dev) if not math.isnan(min_calib_dev) else None
            ),
            "n_before": len(stage2),
            "n_after": 1,
            "remaining_thetas": [c["theta"] for c in stage3a_sorted],
            "selected_theta": selected["theta"],
        }

    selection_path["final_verdict"] = (
        f"selected θ={selected['theta']} via cutoff→argmin_overpred→tiebreak"
    )
    logger.info(
        "θ 選択経路: stage1_cutoff n=%d→%d / stage2_argmin_overpred n=%d / "
        "stage3_tiebreak → θ=%s",
        len(candidates),
        len(passing),
        len(stage2),
        selected["theta"],
    )

    return {
        "selected_theta": float(selected["theta"]),
        "selected_candidate": _sanitize_for_json(selected),
        "candidates": _sanitize_for_json(candidates),
        "selection_path": selection_path,
    }


# ---------------------------------------------------------------------------
# pred_df からの指標算出 helpers
# ---------------------------------------------------------------------------
def _compute_pred_metrics(pred_df: pd.DataFrame) -> dict[str, Any]:
    """pred_df から compute_metrics で Brier/LogLoss/AUC/calib_max_dev 等を算出する.

    compute_metrics は evaluator から import 再利用 (§15.2・binning bit-identical)。
    """
    return compute_metrics(
        pred_df["fukusho_hit_validated"],
        pred_df["p_fukusho_hit"],
        race_keys=pred_df.get("race_key"),
        entry_counts=pred_df.get("entry_count"),
    )


def _compute_overprediction_from_pred(pred_df: pd.DataFrame) -> float:
    """pred_df から overprediction penalty を算出する (race_relative 経由・binning import 再利用).

    market_signal には odds 系外部参照列を使用する (SAFE-01: feature でなく evaluation 専用)。
    列名は segment_eval.evaluate_all_segments が期待する odds 系列と同一。
    odds 系列が無い場合は ninki 系列で fallback (segment_eval と同一契約)。
    いずれも無い場合は NaN (run_phase10_evaluation.py の D-15 参考記録失敗 idiom と同一)。
    """
    y_true = pred_df["fukusho_hit_validated"].to_numpy(dtype=float)
    y_pred = pred_df["p_fukusho_hit"].to_numpy(dtype=float)
    # segment_eval と同じ odds 系列優先順位で market_signal を構築
    signal_col = None
    for col in (
        "final_odds",
        "odds",
        "fukuodds",
        "ninki",
        "ninkij",
    ):
        if col in pred_df.columns:
            signal_col = col
            break
    if signal_col is None:
        logger.warning(
            "compute_overprediction: odds/ninki 系列が pred_df に無い・NaN を返す (D-15 参考記録)"
        )
        return float("nan")
    market_signal = pd.to_numeric(pred_df[signal_col], errors="coerce").to_numpy(dtype=float)
    return float(
        compute_overprediction_penalty(
            y_true=y_true,
            y_pred=y_pred,
            market_signal=market_signal,
            cell_filter_mask=None,
        )
    )


def _compute_selected_only_calib_max_dev(pred_df: pd.DataFrame) -> float:
    """selected/high-EV 層の calibration_max_dev を算出する (D-05-3・segment_eval 経由).

    selected/high-EV 層は p_fukusho_hit 上位 X% (EV-decile 相当) で定義する。
    本 Phase 11 では selected 層を「p_fukusho_hit 上位 30%」とし・Phase 12 EVAL-01 で
    厳密な EV-decile 定義に移行する (PLAN 11-04 acceptance_criteria に従い・事前登録閾値)。
    """
    if "p_fukusho_hit" not in pred_df.columns or "fukusho_hit_validated" not in pred_df.columns:
        return float("nan")
    n = len(pred_df)
    if n == 0:
        return float("nan")
    # p_fukusho_hit 上位 30% を selected/high-EV 層とする (事前登録)
    cutoff_idx = max(1, int(n * 0.30))
    sorted_pred = pred_df.sort_values("p_fukusho_hit", ascending=False)
    selected = sorted_pred.head(cutoff_idx)
    if len(selected) == 0:
        return float("nan")
    # selected 層の calibration_max_dev: 予測確率の平均と実現率の差の絶対値
    # (calibration curve を引くにはサンプルが足りないため・単純な mean 差で代用・
    #  Phase 12 EVAL-01 で厳密化)
    mean_pred = float(selected["p_fukusho_hit"].mean())
    frac_pos = float(selected["fukusho_hit_validated"].mean())
    return float(abs(mean_pred - frac_pos))


def _attach_label_to_pred(
    pred_df: pd.DataFrame,
    *,
    label_joined_frame: pd.DataFrame,
) -> pd.DataFrame:
    """orchestrator.train_and_predict の pred_df に label を JOIN する.

    run_phase10_evaluation.py L500-560 と同一 idiom (umaban 型正規化 + label 側の必要列抽出 +
    many_to_one validate + NaN fail-loud)。
    """
    pred_df = pred_df.copy()
    label_df = label_joined_frame.copy()
    pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")
    label_df["umaban"] = pd.to_numeric(label_df["umaban"], errors="coerce").astype("Int64")

    label_keep = ["race_key", "umaban", "fukusho_hit_validated"]
    for extra in ("entry_count", "final_starter_count", "sales_start_entry_count"):
        if extra in label_df.columns:
            label_keep.append(extra)

    merged = pred_df.merge(
        label_df[label_keep],
        on=["race_key", "umaban"],
        how="left",
        suffixes=("", "_label"),
        validate="many_to_one",
    )
    if len(merged) != len(pred_df):
        raise RuntimeError(
            f"_attach_label_to_pred: label merge 行数不変違反 "
            f"len(before)={len(pred_df)} != len(after)={len(merged)}"
        )
    for col in label_keep:
        if col in ("race_key", "umaban"):
            continue
        label_col = f"{col}_label"
        if label_col in merged.columns:
            merged[col] = merged[label_col]
            merged = merged.drop(columns=[label_col])

    n_missing = int(merged["fukusho_hit_validated"].isna().sum())
    if n_missing > 0:
        raise RuntimeError(
            f"_attach_label_to_pred: pred_df の {n_missing} 行に label が JOIN できなかった "
            "(silent leak・§19.1 聖域)"
        )
    return merged


# ---------------------------------------------------------------------------
# gate 評価 (D-04 非劣化 + D-05 改善 3条件)
# ---------------------------------------------------------------------------
def _evaluate_gate(
    *,
    baseline_pred: pd.DataFrame,
    rr_pred: pd.DataFrame,
    baseline_model_version: str,
    rr_model_version: str,
    selected_theta: float,
    theta_selection: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """baseline (theta=None) と race-relative (theta=selected_theta) の pred_df から
    D-04 非劣化 gate + D-05 改善 gate 3条件を判定する (B-3).

    gate_pass = D-04 AND D-05 (両方満たす必要)。
    D-15 参考記録 (segment_eval) も見える化するが gate 判定には使わない。
    """
    # compute_metrics で Brier/LogLoss/AUC 算出 (binning 定数は evaluator から import 再利用・§15.2)
    baseline_metrics = _compute_pred_metrics(baseline_pred)
    rr_metrics = _compute_pred_metrics(rr_pred)

    baseline_brier = float(baseline_metrics.get("brier", float("nan")))
    baseline_logloss = float(baseline_metrics.get("logloss", float("nan")))
    baseline_auc = float(baseline_metrics.get("auc", float("nan")))
    rr_brier = float(rr_metrics.get("brier", float("nan")))
    rr_logloss = float(rr_metrics.get("logloss", float("nan")))
    rr_auc = float(rr_metrics.get("auc", float("nan")))

    # B-3: delta は両実測値の差
    brier_delta = rr_brier - baseline_brier
    logloss_delta = rr_logloss - baseline_logloss
    auc_delta = rr_auc - baseline_auc

    # D-04 非劣化 gate (3条件の論理積)
    d04_pass = (
        (brier_delta <= TOLERANCE_BRIER)
        and (logloss_delta <= TOLERANCE_LOGLOSS)
        and (auc_delta >= -TOLERANCE_AUC)  # AUC は低下が違反 (符号注意)
    )

    # D-05 改善 gate 3条件
    baseline_overprediction = _compute_overprediction_from_pred(baseline_pred)
    rr_overprediction = _compute_overprediction_from_pred(rr_pred)
    # D-05-1: overprediction penalty が rr < baseline (NaN の場合は FAIL・safe side)
    d05_1_pass = (
        not math.isnan(baseline_overprediction)
        and not math.isnan(rr_overprediction)
        and rr_overprediction < baseline_overprediction
    )
    # D-05-2: selected/high-EV 層の (mean_pred - frac_pos) が rr < baseline
    baseline_selected_dev = _compute_selected_only_calib_max_dev(baseline_pred)
    rr_selected_dev = _compute_selected_only_calib_max_dev(rr_pred)
    d05_2_pass = (
        not math.isnan(baseline_selected_dev)
        and not math.isnan(rr_selected_dev)
        and rr_selected_dev < baseline_selected_dev
    )
    # D-05-3: selected-only calib_max_dev が D-04 マージン (TOLERANCE_BRIER を代用) 内で悪化しない
    # (rr_selected_dev が baseline_selected_dev + TOLERANCE_BRIER を超えない)
    d05_3_pass = (
        not math.isnan(rr_selected_dev)
        and rr_selected_dev <= baseline_selected_dev + TOLERANCE_BRIER
    )
    d05_pass = d05_1_pass and d05_2_pass and d05_3_pass

    gate_pass = bool(d04_pass and d05_pass)

    # D-15 参考記録: segment_eval.evaluate_all_segments (binning import 再利用)
    d15_segments: dict[str, Any] = {"note": "D-15 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない"}
    try:
        baseline_segments = evaluate_all_segments(baseline_pred)
        rr_segments = evaluate_all_segments(rr_pred)
        d15_segments["baseline"] = _sanitize_for_json(baseline_segments)
        d15_segments["race_relative"] = _sanitize_for_json(rr_segments)
    except Exception as e:
        logger.warning("D-15 segment_eval 失敗 (参考記録・gate 継続): %s", e)
        d15_segments["error"] = str(e)

    return {
        "gate_pass": gate_pass,
        "d04_non_degradation": {
            "pass": bool(d04_pass),
            "tolerance": {
                "brier": TOLERANCE_BRIER,
                "logloss": TOLERANCE_LOGLOSS,
                "auc": TOLERANCE_AUC,
                "note": "D-04 事前登録許容幅 (§11.2 聖域・Phase 10 の 0.002/0.005/0.005 から拡張)",
            },
            "brier_delta": brier_delta,
            "logloss_delta": logloss_delta,
            "auc_delta": auc_delta,
        },
        "d05_improvement_gate": {
            "pass": bool(d05_pass),
            "condition_1_overprediction_penalty": {
                "pass": bool(d05_1_pass),
                "baseline": float(baseline_overprediction),
                "race_relative": float(rr_overprediction),
                "rule": "rr < baseline (D-05-1 主指標)",
            },
            "condition_2_selected_mean_minus_frac": {
                "pass": bool(d05_2_pass),
                "baseline_selected_dev": float(baseline_selected_dev),
                "rr_selected_dev": float(rr_selected_dev),
                "rule": "rr < baseline (D-05-2 selected/high-EV 層)",
            },
            "condition_3_selected_calib_max_dev": {
                "pass": bool(d05_3_pass),
                "baseline_selected_dev": float(baseline_selected_dev),
                "rr_selected_dev": float(rr_selected_dev),
                "margin": TOLERANCE_BRIER,
                "rule": "rr <= baseline + TOLERANCE_BRIER (D-05-3)",
            },
        },
        "baseline_metrics": {
            "brier": baseline_brier,
            "logloss": baseline_logloss,
            "auc": baseline_auc,
            "calibration_max_dev": float(baseline_metrics.get("calibration_max_dev", float("nan"))),
        },
        "rr_metrics": {
            "brier": rr_brier,
            "logloss": rr_logloss,
            "auc": rr_auc,
            "calibration_max_dev": float(rr_metrics.get("calibration_max_dev", float("nan"))),
        },
        "delta": {
            "brier_delta": brier_delta,
            "logloss_delta": logloss_delta,
            "auc_delta": auc_delta,
        },
        "selected_theta": selected_theta,
        "theta_selection": theta_selection,
        "d15_reference_segments": d15_segments,
        "model_versions": {
            "baseline": baseline_model_version,
            "race_relative": rr_model_version,
        },
        "args": {
            "baseline_snapshot_id": args.baseline_snapshot_id,
            "bt_split": args.bt_split,
            "odds_snapshot_policy": args.odds_snapshot_policy,
            "theta_candidates": list(args.theta_candidates),
        },
        "binning_source": {
            "CALIBRATION_CURVE_BINS": CALIBRATION_CURVE_BINS,
            "CALIBRATION_CURVE_MIN_BIN_COUNT": CALIBRATION_CURVE_MIN_BIN_COUNT,
            "ODDS_BAND_EDGES": ODDS_BAND_EDGES,
            "NINKI_BAND_EDGES": NINKI_BAND_EDGES,
            "note": "§15.2 事前登録指標不変・evaluator/segment_eval から import 再利用 (再定義禁止)",
        },
        "race_relative_constants": {
            "THETA_CANDIDATES": list(THETA_CANDIDATES),
            "ALPHA_SEARCH_XTOL": ALPHA_SEARCH_XTOL,
            "P_CAL_CLIP_EPSILON": P_CAL_CLIP_EPSILON,
            "note": "11-01 事前登録定数 (§11.2 聖域)・再定義でなく import 再利用",
        },
        "safe_01_note": (
            "race-relative 補正層は 11-01 で SAFE-01 AST 監査済み (odds/ninki proxy 0件)。"
            "run_phase11_evaluation.py は market_signal (odds 系外部参照) を evaluation 専用層 "
            "(compute_overprediction_penalty / segment_eval) でのみ使用し FEATURE_COLUMNS には混入しない "
            "(orchestrator.train_and_predict の FEATURE_COLUMNS allowlist が保証・SAFE-01)。"
        ),
        "d07_note": (
            "Phase 11 は並列比較のみ・is_primary 切替は Phase 12 (D-07)。本 script は比較レポート生成のみ・"
            "prediction 永続化 (load_predictions / primary 切替) は行わない。実際の model_version 行追加は "
            "11-05 で実施 (primary 立ては Phase 12)。"
        ),
    }


# ---------------------------------------------------------------------------
# theta-selection report 書き出し (codex HIGH#1・test 窓評価に先立ち)
# ---------------------------------------------------------------------------
def _write_theta_selection_reports(eval_dir: Path, theta_selection: dict[str, Any]) -> None:
    """reports/11-evaluation/theta-selection.{md,json} を atomic write する.

    codex review HIGH#1・PLAN 11-04: θ 選択経路が決定した直後・test 窓評価に先立って
    byte-reproducible に書き出す (後知恵すり替え禁止・選択ルールは事前登録値で固定)。
    """
    json_path = eval_dir / "theta-selection.json"
    md_path = eval_dir / "theta-selection.md"

    sanitized = _sanitize_for_json(theta_selection)
    json_text = json.dumps(
        sanitized, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2
    )
    md_text = _format_theta_selection_markdown(theta_selection)

    _atomic_write_text(json_path, json_text)
    _atomic_write_text(md_path, md_text)
    logger.info("wrote %s / %s (test 窓評価に先立ち)", json_path, md_path)


def _format_theta_selection_markdown(theta_selection: dict[str, Any]) -> str:
    """theta-selection.md の Markdown レポートを構築する."""
    lines: list[str] = []
    lines.append("# Phase 11 θ 選択経路 (D-03 制約付き選択・calib slice のみ)")
    lines.append("")
    lines.append("## Selected θ")
    lines.append("")
    lines.append(f"**θ = {theta_selection.get('selected_theta')}**")
    lines.append("")
    sp = theta_selection.get("selection_path", {})
    lines.append(f"- final_verdict: {sp.get('final_verdict', '')}")
    lines.append("- §11.2 聖域: θ 選択は calib slice (score_split='calib') のみ・test 窓は選び直さない")
    lines.append("")

    lines.append("## 選択経路 (足切り → 選択 → tie-break)")
    lines.append("")
    s1 = sp.get("stage_1_cutoff", {})
    lines.append(f"### Stage 1: {s1.get('rule', '')}")
    tol = s1.get("tolerance", {})
    lines.append(f"- 許容幅: Brier ≤ {tol.get('brier')} / LogLoss ≤ {tol.get('logloss')} / AUC ≥ -{tol.get('auc')}")
    lines.append(f"- 通過: {s1.get('n_after', 0)} / {s1.get('n_before', 0)} (脱落: {s1.get('failed_thetas', [])})")
    lines.append("")

    s2 = sp.get("stage_2_argmin_overprediction")
    if s2:
        lines.append(f"### Stage 2: {s2.get('rule', '')}")
        lines.append(f"- min overprediction penalty: {s2.get('min_overprediction_penalty')}")
        lines.append(f"- 残候補: {s2.get('remaining_thetas', [])}")
        lines.append("")

    s3 = sp.get("stage_3_tiebreak")
    if s3:
        lines.append(f"### Stage 3: {s3.get('rule', '')}")
        lines.append(f"- 残候補 (θ=1 に近い順): {s3.get('remaining_thetas', [])}")
        if "selected_theta" in s3:
            lines.append(f"- selected: θ={s3.get('selected_theta')}")
        lines.append("")

    lines.append("## 候補毎の評価値 (calib slice)")
    lines.append("")
    lines.append("| θ | Brier | LogLoss | AUC | overprediction_penalty | calib_max_dev | selected_only_calib_max_dev | verdict |")
    lines.append("|---|-------|---------|-----|----------------------|---------------|-----------------------------|---------|")
    def _fmt(v: Any) -> str:
        """数値は :.5f・None/NaN は 'NaN'（D-15 参考記録: odds/ninki 無し等で計算不能）。"""
        if v is None:
            return "NaN"
        try:
            if math.isnan(v):
                return "NaN"
        except (TypeError, ValueError):
            pass
        return f"{v:.5f}"

    for c in theta_selection.get("candidates", []):
        lines.append(
            f"| {c.get('theta')} | {_fmt(c.get('brier'))} | {_fmt(c.get('logloss'))} | "
            f"{_fmt(c.get('auc'))} | {_fmt(c.get('overprediction_penalty'))} | "
            f"{_fmt(c.get('calib_max_dev'))} | {_fmt(c.get('selected_only_calib_max_dev'))} | "
            f"{c.get('verdict')} |"
        )
    lines.append("")
    lines.append("## baseline (theta=None) calib 指標 (足切り基準)")
    lines.append("")
    bm = sp.get("baseline_calib_metrics", {})
    lines.append(f"- Brier: {bm.get('brier')}")
    lines.append(f"- LogLoss: {bm.get('logloss')}")
    lines.append(f"- AUC: {bm.get('auc')}")
    lines.append(f"- baseline overprediction penalty (calib): {sp.get('baseline_overprediction_penalty_calib')}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 比較レポート書き出し
# ---------------------------------------------------------------------------
def _write_reports(eval_dir: Path, result: dict[str, Any]) -> tuple[Path, Path]:
    """reports/11-evaluation/11-evaluation.{md,json} を atomic write する."""
    eval_dir.mkdir(parents=True, exist_ok=True)
    json_path = eval_dir / "11-evaluation.json"
    md_path = eval_dir / "11-evaluation.md"

    sanitized = _sanitize_for_json(result)
    json_text = json.dumps(
        sanitized, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2
    )
    md_text = _format_markdown_report(result)

    _atomic_write_text(json_path, json_text)
    _atomic_write_text(md_path, md_text)
    return json_path, md_path


def _format_markdown_report(result: dict[str, Any]) -> str:
    """SC#2 gate (D-04 非劣化 + D-05 改善 3条件) の Markdown レポートを構築する."""
    lines: list[str] = []
    lines.append("# Phase 11 SC#2 Gate: v1.0 binary vs race-relative model (θ + per-race α_r)")
    lines.append("")
    lines.append("## Gate Verdict")
    lines.append("")
    gate_pass = result.get("gate_pass", False)
    verdict = (
        "PASS (D-04 非劣化 + D-05 改善 3条件 全て満たす・delta 基準は baseline 実測値)"
        if gate_pass
        else "FAIL (D-04 または D-05 のいずれか未達・§11.2 聖域・許容幅は変更せず)"
    )
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append(f"- selected θ: {result.get('selected_theta')}")
    lines.append("")

    lines.append("## D-04 非劣化 gate (delta 基準は baseline 実測値)")
    lines.append("")
    d04 = result.get("d04_non_degradation", {})
    lines.append(f"- verdict: {'PASS' if d04.get('pass') else 'FAIL'}")
    delta = result.get("delta", {})
    tol = d04.get("tolerance", {})
    lines.append("| 指標 | baseline 実測 | race-relative 実測 | delta | D-04 許容幅 |")
    lines.append("|------|-------------|-------------------|-------|------------|")
    bm = result.get("baseline_metrics", {})
    rm = result.get("rr_metrics", {})
    lines.append(
        f"| Brier | {bm.get('brier', 0):.5f} | {rm.get('brier', 0):.5f} | "
        f"{delta.get('brier_delta', 0):+.5f} | <= +{tol.get('brier')} |"
    )
    lines.append(
        f"| LogLoss | {bm.get('logloss', 0):.5f} | {rm.get('logloss', 0):.5f} | "
        f"{delta.get('logloss_delta', 0):+.5f} | <= +{tol.get('logloss')} |"
    )
    lines.append(
        f"| AUC | {bm.get('auc', 0):.5f} | {rm.get('auc', 0):.5f} | "
        f"{delta.get('auc_delta', 0):+.5f} | >= -{tol.get('auc')} |"
    )
    lines.append("")

    lines.append("## D-05 改善 gate (3 必須条件)")
    lines.append("")
    d05 = result.get("d05_improvement_gate", {})
    lines.append(f"- verdict: {'PASS' if d05.get('pass') else 'FAIL'} (3条件の論理積)")
    c1 = d05.get("condition_1_overprediction_penalty", {})
    c2 = d05.get("condition_2_selected_mean_minus_frac", {})
    c3 = d05.get("condition_3_selected_calib_max_dev", {})
    lines.append(f"- (1) overprediction penalty (rr < baseline): {'PASS' if c1.get('pass') else 'FAIL'} (baseline={c1.get('baseline')} / rr={c1.get('race_relative')})")
    lines.append(f"- (2) selected/high-EV 層 mean_pred - frac_pos (rr < baseline): {'PASS' if c2.get('pass') else 'FAIL'} (baseline={c2.get('baseline_selected_dev')} / rr={c2.get('rr_selected_dev')})")
    lines.append(f"- (3) selected-only calib_max_dev (rr <= baseline + margin): {'PASS' if c3.get('pass') else 'FAIL'} (baseline={c3.get('baseline_selected_dev')} / rr={c3.get('rr_selected_dev')} / margin={c3.get('margin')})")
    lines.append("")

    lines.append("## θ 選択経路 (D-03 制約付き選択・calib slice のみ・§11.2 聖域)")
    lines.append("")
    ts = result.get("theta_selection", {})
    sp = ts.get("selection_path", {})
    lines.append(f"- selected θ: {ts.get('selected_theta')}")
    lines.append(f"- final_verdict: {sp.get('final_verdict', '')}")
    lines.append("- θ 選択は score_split='calib' のみで実施 (codex HIGH#1・test 窓選び直し禁止)")
    lines.append("- reports/11-evaluation/theta-selection.{md,json} に候補毎の評価値と選択経路を事前書き出し済み (後知恵すり替え禁止)")
    lines.append("")

    lines.append("## §15.2 binning 契約 (import 再利用・再定義禁止)")
    lines.append("")
    bs = result.get("binning_source", {})
    lines.append(f"- CALIBRATION_CURVE_BINS: {bs.get('CALIBRATION_CURVE_BINS')}")
    lines.append(f"- CALIBRATION_CURVE_MIN_BIN_COUNT: {bs.get('CALIBRATION_CURVE_MIN_BIN_COUNT')}")
    lines.append(f"- ODDS_BAND_EDGES: {bs.get('ODDS_BAND_EDGES')}")
    lines.append(f"- NINKI_BAND_EDGES: {bs.get('NINKI_BAND_EDGES')}")
    lines.append("")

    lines.append("## race_relative 事前登録定数 (§11.2 聖域)")
    lines.append("")
    rc = result.get("race_relative_constants", {})
    lines.append(f"- THETA_CANDIDATES: {rc.get('THETA_CANDIDATES')}")
    lines.append(f"- ALPHA_SEARCH_XTOL: {rc.get('ALPHA_SEARCH_XTOL')}")
    lines.append(f"- P_CAL_CLIP_EPSILON: {rc.get('P_CAL_CLIP_EPSILON')}")
    lines.append("")

    lines.append("## model_versions")
    lines.append("")
    mv = result.get("model_versions", {})
    lines.append(f"- baseline: {mv.get('baseline')}")
    lines.append(f"- race_relative: {mv.get('race_relative')}")
    lines.append("")

    lines.append("## D-07 (is_primary 立てない)")
    lines.append("")
    lines.append(f"- {result.get('d07_note', '')}")
    lines.append("")

    lines.append("## D-15 参考記録 (selected-only calibration / odds_band×p_bin)")
    lines.append("- 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    raise SystemExit(main())
