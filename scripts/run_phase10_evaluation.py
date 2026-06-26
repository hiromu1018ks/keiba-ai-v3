"""Phase 10 SC#5 非劣化 gate: v1.0 baseline vs Phase 10 snapshot 3-way 比較 (両 snapshot 同一 trainer 設定で delta).

Purpose
-------
Phase 10 で追加した 27 新 feature (FEAT-02 相手強度 rolling profile 21 + FEAT-03 レース内相対 6)
が v1.0 LightGBM の性能を悪化させないことを定量的に保証する (SC#5・特徴量ノイズ化の回帰検知)。

D-16 事前登録許容幅 (§11.2 聖域・Open Question #4 解決)::
    - Brier 悪化  <= 0.002
    - LogLoss 悪化 <= 0.005
    - AUC 悪化   <= 0.005  (AUC は「低下」が非劣化違反・符号注意)

許容幅は評価結果を見た後に変更しない (§11.2 聖域・D-16)。

B-3 (両 snapshot 同一 trainer 設定で delta・§11.2 聖域の核心)
    baseline snapshot ``20260620-1a-postreview-v2`` と Phase 10 snapshot
    ``20260626-1a-opponentstrength-v1`` を**全く同一の trainer 設定** (LightGBM
    version/hyperparams/seed/category_map/split_periods/odds_snapshot_policy/bt_split)
    で再評価し・両者の**実測値**の delta を取る。BASELINE_* 定数 (Phase 6 当時参考値) は
    gate 判定の delta 基準には**使わない** (feature ノイズ化とベースライン設定ドリフト
    LightGBM version/hyperparams/seed/category_map/split_periods 揺らぎを鑑別するため)。

W-2 (係数妥当性証拠・REVIEWS.md L86 actionable MEDIUM/LOW・PLAN 03 compute_candidate_score_diagnostics の consumer)
    train/calib 窓それぞれで候補 {0.0, 0.1, 0.25, 0.5} の adjusted_score 分布統計を
    ``reports/10-evaluation/candidate_score_diagnostics_{train,calib}.json`` に出力する。
    §11.2 聖域保護: 候補選定は train/calib 窓内のみ・test 窓 rank はすり替えない。
    0.25 canonical の妥当性証拠を残す (diagnostic であり gate 条件にはしない)。

W-3 (category-map bit-identity・REVIEWS.md L140/L205 MEDIUM・B-3 前提)
    baseline_cat_map と phase10_cat_map の hash bit-identity を実行時に assert する。
    Phase 10 は新 feature 追加のみで category mapping を変更しない設計の実行時証明。
    category_map が異なると delta は feature ノイズ化ではなく category mapping ドリフト
    を測る (B-3・両 snapshot 同一 trainer 設定の核心)。

§15.2 事前登録指標不変 (聖域)
    evaluator/segment_eval の binning 定数 (CALIBRATION_CURVE_BINS /
    CALIBRATION_CURVE_MIN_BIN_COUNT / ODDS_BAND_EDGES / NINKI_BAND_EDGES) を import 再利用し・
    **再定義しない** (bit-identical)。

REVIEW H6 (10-REVIEWS.md L139-145, L200, L228)
    ``orchestrator.train_and_predict(snapshot_id=...)`` 略記でなく・正しい API chain
    ``load_feature_matrix(snapshot_id=...) → load_labels(cur) → build_training_frame(feature_df,
    label_df) → load_frozen_maps(snapshot_id=...) → train_and_predict(label_joined_frame,
    feature_snapshot_id=..., snapshot_id=..., version_n=1, split_periods=BT1_PERIODS,
    category_map=cat_map)`` を呼ぶ (run_speed_figure_stopgate.py L583-622 の直接踏襲)。

REVIEW H2/H7/H8
    生 trainer API は直接呼ばない (calibration skip / sorted_index 誤用 / categorical dtype
    mismatch の3バグを構造的回避)。

D-15 参考記録
    selected-only calibration / odds_band×p_bin は参考記録として見える化され (Phase 12
    EVAL-01 先行指標)・ただし gate 判定には使わない (Brier/LogLoss/AUC の3条件のみが gate)。

Usage (live-DB・KEIBA_SKIP_DB_TESTS unset)::

    uv run python scripts/run_phase10_evaluation.py \\
        --baseline-snapshot-id 20260620-1a-postreview-v2 \\
        --phase10-snapshot-id 20260626-1a-opponentstrength-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --out-dir reports
"""

# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加
# (scripts/run_speed_figure_stopgate.py L65-68 と同一 idiom)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §15.2 事前登録指標不変: binning 定数を import 再利用 (再定義禁止・bit-identical)
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    compute_metrics,
)
from src.model.predict import make_model_version  # noqa: E402  model_version 採番 (review HIGH#4)
from src.model.segment_eval import (  # noqa: E402
    NINKI_BAND_EDGES,
    ODDS_BAND_EDGES,
    evaluate_all_segments,
)

logger = logging.getLogger("run_phase10_evaluation")

# ---------------------------------------------------------------------------
# D-16 事前登録許容幅 (§11.2 聖域・Open Question #4 解決)
# ---------------------------------------------------------------------------
# 許容幅は評価結果を見た後に変更しない (§11.2 聖域・D-16)。
# Phase 6 D-07 水準 (Brier=0.15222 / LogLoss=0.47488 / AUC=0.73230) 基準の現実的変動マージン。
#  - Brier +0.002 は v1.0 Brier の ~1.3%
#  - LogLoss +0.005 は ~1.1%
#  - AUC -0.005 は ~0.7%
# run_speed_figure_stopgate (0.005/0.02/0.005) より厳格・Phase 11 SC#2 事前登録マージンと
# 同一スケールであることを前提とする (Phase 11 plan 作成時に再確認)。
TOLERANCE_BRIER: float = 0.002
TOLERANCE_LOGLOSS: float = 0.005
TOLERANCE_AUC: float = 0.005  # AUC は「低下」が非劣化違反 (符号注意)

# ---------------------------------------------------------------------------
# BASELINE_* 定数 (Phase 6 D-07 水準・参考値・**gate 判定の delta 基準でない**)
# ---------------------------------------------------------------------------
# B-3 (§11.2 聖域の核心): これらは Phase 6 当時の参考値。SC#5 gate 判定は baseline snapshot
# (20260620-1a-postreview-v2) を同一 trainer 設定で再評価した**実測値**を delta 基準に使う。
# 固定ハードコード値を gate 判定に使うと「feature ノイズ化かベースライン設定ドリフト
# (LightGBM version/hyperparams/seed/category_map/split_periods 揺らぎ) か」の鑑別ができない。
# ログ表示と BASELINE_* との乖離 WARNING (設定ドリフト鑑別資料) にのみ使用する。
BASELINE_BRIER: float = 0.15222
BASELINE_LOGLOSS: float = 0.47488
BASELINE_AUC: float = 0.73230


# ---------------------------------------------------------------------------
# hash_canonical helper (W-3 bit-identity・mapping 順序に依存しない)
# ---------------------------------------------------------------------------
def hash_canonical(obj: Any) -> str:
    """dict/list を stable に正規化して SHA256 hash を返す (W-3 bit-identity 検証用)。

    json.dumps(sort_keys=True) で正規化してから hash するため・mapping 順序に依存しない。
    baseline_cat_map と phase10_cat_map の bit-identity 検証に使用する (B-3 同一 trainer 設定の前提)。
    """
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JSON sanitizer (run_speed_figure_stopgate.py L121-143 idiom・NaN/Inf → None/"NaN"/"Infinity")
# ---------------------------------------------------------------------------
def _sanitize_for_json(obj: Any) -> Any:
    """dict/list/float/ndarray を再帰走査し NaN/Inf/ndarray を JSON 安全な表現に変換する (REVIEW M4 idiom).

    src/model/segment_eval.py L94-112 (``_sanitize_nan_to_null``) の sanitizer pattern を踏襲。
    single-class AUC 等で NaN が混入しても ``json.dumps(allow_nan=False)`` が
    ``ValueError`` で失敗するのを防ぐ (RFC 8259 strict)。

    拡張: numpy.ndarray / numpy scalar も list / Python scalar に変換する
    (compute_metrics / evaluate_all_segments の戻り値に ndarray が含まれるため)。
    """
    # numpy ndarray / scalar の再帰的 list 化 (先に処理・float 判定より前)
    try:
        import numpy as _np
    except ImportError:  # numpy 無し環境 (本プロジェクトでは起こり得ないが安全側)
        _np = None
    if _np is not None:
        if isinstance(obj, _np.ndarray):
            return _sanitize_for_json(obj.tolist())
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.floating):
            return _sanitize_for_json(float(obj))
        if isinstance(obj, _np.bool_):
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


# BT-1 split periods (§15.5) — train 2019-06-01..2022-06-30 / calib 2022-07-01..2022-12-31 / test 2023
# Phase 5 D-03 / HIGH-B cycle-2 idiom: calib は train tail 6ヶ月から切り出す
# (_carve_calib_from_train_tail と同一方針・max(train)<min(calib)<max(calib)<min(test) を満たす)
# run_speed_figure_stopgate.py L543-547 と同一定数。
BT1_PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2019-06-01", "2022-06-30"),
    "calib": ("2022-07-01", "2022-12-31"),
    "test": ("2023-01-01", "2023-12-31"),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する."""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 10 SC#5 非劣化 gate: v1.0 baseline vs Phase 10 snapshot (opponentstrength)"
            " 3-way 比較・両 snapshot 同一 trainer 設定で delta (B-3・D-16 事前登録許容幅)"
        ),
    )
    parser.add_argument(
        "--baseline-snapshot-id",
        default="20260620-1a-postreview-v2",
        help="v1.0 baseline snapshot_id (default: 20260620-1a-postreview-v2)",
    )
    parser.add_argument(
        "--phase10-snapshot-id",
        default="20260626-1a-opponentstrength-v1",
        help="Phase 10 snapshot_id (default: 20260626-1a-opponentstrength-v1・Open Question #3 事前登録)",
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
# W-2 diagnostic: train/calib 窓の候補 {0.0,0.1,0.25,0.5} adjusted_score 分布統計
# ---------------------------------------------------------------------------
def _compute_w2_diagnostics(
    phase10_frame: pd.DataFrame,
    *,
    out_dir: Path,
) -> dict[str, Any]:
    """W-2 (REVIEWS.md L86 actionable MEDIUM/LOW): PLAN 03 compute_candidate_score_diagnostics を消費し・
    train/calib 窓それぞれの候補 {0.0,0.1,0.25,0.5} adjusted_score 分布統計を JSON + ログ出力する。

    §11.2 聖域保護:
        - 候補選定は train/calib 窓内のみ (test 窓 rank はすり替えない)。
        - diagnostic は証跡であって gate 条件にはしない (0.25 canonical rank の gate 判定は不変)。

    万が一 PLAN 03 の compute_candidate_score_diagnostics が未実装の場合は WARN ログを出して
    スキップ (gate は継続)・ただし acceptance_criteria の W-2 が未達となるので SUMMARY に記録。
    """
    try:
        from src.features.race_relative import compute_candidate_score_diagnostics
    except ImportError as e:
        logger.warning(
            "W-2 skip: compute_candidate_score_diagnostics の import に失敗 (%s)・"
            "gate は継続するが acceptance_criteria W-2 は未達 (SUMMARY 記録対象)",
            e,
        )
        return {"status": "skipped", "reason": f"import failed: {e}"}

    # CR-04 (10-08 gap-closure): phase10_frame が rolling 系 feature を含むことを assert する。
    # W-2 diagnostic は §11.2 聖域（test 窓 rank すり替え禁止・W-2 候補集合 diagnostic）の履行証跡であり・
    # rolling 系 feature が未伝播の frame を受け取った場合は WARNING skip でなく RuntimeError で
    # 履行証跡欠損を構造的ブロックする（FEAT-02/03 未伝播・Phase 10 acceptance_criteria W-2 履行不能）。
    required = ("race_nkey", "rolling_speed_figure_mean_5", "rolling_field_strength_mean_mean_5")
    missing = [c for c in required if c not in phase10_frame.columns]
    if missing:
        raise RuntimeError(
            f"W-2 必須列が phase10_frame に無い: {missing}・FEAT-02/03 未伝播・"
            "Phase 10 acceptance_criteria W-2 が履行不能（§11.2 聖域・CR-04 fail-loud）"
        )

    # train/calib 窓の mask を構築 (split_periods=BT1_PERIODS から race_date で)
    # CR-04 (10-08 gap-closure): race_date 列欠損も RuntimeError に格上げ（mask 構築不能 = W-2 履行不能）。
    if "race_date" not in phase10_frame.columns:
        raise RuntimeError(
            "W-2 mask 構築不能: phase10_frame に race_date 列がない・"
            "Phase 10 acceptance_criteria W-2 が履行不能（§11.2 聖域・CR-04 fail-loud）"
        )
    rd = pd.to_datetime(phase10_frame["race_date"], errors="coerce")
    train_mask = rd.between(pd.to_datetime(BT1_PERIODS["train"][0]), pd.to_datetime(BT1_PERIODS["train"][1]))
    calib_mask = rd.between(pd.to_datetime(BT1_PERIODS["calib"][0]), pd.to_datetime(BT1_PERIODS["calib"][1]))

    diag_train = compute_candidate_score_diagnostics(phase10_frame, split_mask=train_mask)
    diag_calib = compute_candidate_score_diagnostics(phase10_frame, split_mask=calib_mask)

    eval_dir = out_dir / "10-evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    train_path = eval_dir / "candidate_score_diagnostics_train.json"
    calib_path = eval_dir / "candidate_score_diagnostics_calib.json"
    # coef は float key なので文字列化してから dump (JSON 仕様)
    train_json = {str(k): v for k, v in diag_train.items()}
    calib_json = {str(k): v for k, v in diag_calib.items()}
    train_path.write_text(
        json.dumps(_sanitize_for_json(train_json), sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    calib_path.write_text(
        json.dumps(_sanitize_for_json(calib_json), sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    logger.info("W-2 diagnostic 出力: %s / %s", train_path, calib_path)

    # 0.0 vs 0.25 rank 相関の要約ログ (0.25 canonical 妥当性の目視材料)
    def _summary(diag: dict[str, Any], name: str) -> str:
        try:
            r0 = diag.get(0.0, {}).get("adjusted_rank_mean", float("nan"))
            r25 = diag.get(0.25, {}).get("adjusted_rank_mean", float("nan"))
            m0 = diag.get(0.0, {}).get("mean", float("nan"))
            m25 = diag.get(0.25, {}).get("mean", float("nan"))
            return (
                f"{name}: rank_mean(0.0)={r0:.3f} rank_mean(0.25)={r25:.3f} "
                f"score_mean(0.0)={m0:.3f} score_mean(0.25)={m25:.3f}"
            )
        except Exception:
            return f"{name}: summary extract failed"

    logger.info("W-2 %s", _summary(diag_train, "train"))
    logger.info("W-2 %s", _summary(diag_calib, "calib"))

    return {
        "status": "ok",
        "train_path": str(train_path),
        "calib_path": str(calib_path),
        "diag_train": diag_train,
        "diag_calib": diag_calib,
    }


# ---------------------------------------------------------------------------
# main — live-DB orchestration (KEIBA_SKIP_DB_TESTS unset で実行)
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """live-DB で v1.0 baseline と Phase 10 snapshot を**同一 trainer 設定**で再評価し・
    両**実測値**の delta を D-16 許容幅で判定する (B-3・§11.2 聖域の核心)。

    REVIEW H6: load_feature_matrix → load_labels → build_training_frame → load_frozen_maps →
    orchestrator.train_and_predict の正しい API chain を呼ぶ (run_speed_figure_stopgate.py
    L583-622 の直接踏襲・略記 snapshot_id=... でない)。
    REVIEW H2/H7/H8: 生 trainer API は直接呼ばない。
    REVIEW H1-b: orchestrator.train_and_predict に snapshot_id を明示伝播。
    W-3: hash_canonical(baseline_cat_map) == hash_canonical(phase10_cat_map) を assert。
    """
    args = parse_args(argv)

    # 遅延 import: live-DB 依存 (KEIBA_SKIP_DB_TESTS unset でのみ実行)
    from src.config.settings import Settings
    from src.db.connection import make_pool, readonly_cursor
    from src.model.data import (
        build_training_frame,
        load_feature_matrix,
        load_frozen_maps,
        load_labels,
    )
    from src.model.orchestrator import train_and_predict

    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)

    out_dir = Path(args.out_dir)
    eval_dir = out_dir / "10-evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    # T-09-21: statement_timeout='30s' で重クエリの orphan CPU 張り付き防止
    # (MEMORY.md subagent-db-query-statement-timeout)
    #
    # WR-02 (10-08 gap-closure): psycopg_pool ConnectionPool の configure callback で
    # SET statement_timeout='30s' を pool 全体に適用する。cursor 単位の SET は connection を
    # pool に返した後に別 session になると引き継がれないが・configure callback は新規 connection
    # checkout 毎に呼ばれるため・train_and_predict 内の別 session にも確実に適用される。
    def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        conn.commit()

    readonly_pool = make_pool(
        settings, role="readonly", configure=_configure_statement_timeout
    )
    try:
        with readonly_cursor(readonly_pool) as cur:
            # 二重防衛: configure callback と cursor 内 SET の両方で statement_timeout を設定。
            # 主は configure callback（pool 全体適用）・本 cursor SET は defense-in-depth。
            cur.execute("SET statement_timeout = '30s'")

            # REVIEW H6 (5a): feature_df ロード (両 snapshot 明示的 snapshot_id で)
            logger.info("loading baseline snapshot: %s", args.baseline_snapshot_id)
            baseline_feature_df = load_feature_matrix(snapshot_id=args.baseline_snapshot_id)
            logger.info("loading Phase 10 snapshot: %s", args.phase10_snapshot_id)
            phase10_feature_df = load_feature_matrix(snapshot_id=args.phase10_snapshot_id)

            # REVIEW H6 (5b): label 取得 + label-join (build_training_frame で fukusho_hit_validated 付与)
            label_df = load_labels(cur)
            baseline_frame = build_training_frame(baseline_feature_df, label_df)
            phase10_frame = build_training_frame(phase10_feature_df, label_df)

            # REVIEW H6 (5c): category_map ロード + W-3 bit-identity assert
            baseline_cat_map = load_frozen_maps(snapshot_id=args.baseline_snapshot_id)
            phase10_cat_map = load_frozen_maps(snapshot_id=args.phase10_snapshot_id)
            baseline_cat_hash = hash_canonical(baseline_cat_map)
            phase10_cat_hash = hash_canonical(phase10_cat_map)
            logger.info("W-3 baseline_cat_map hash: %s...", baseline_cat_hash[:16])
            logger.info("W-3 phase10_cat_map hash: %s...", phase10_cat_hash[:16])
            if baseline_cat_hash != phase10_cat_hash:
                # W-3 bit-identity 違反・category mapping ドリフト (delta は feature ノイズ化と
                # 鑑別不能)・FAIL として exit 非0 + WARNING ログ出力。
                logger.error(
                    "W-3 bit-identity 違反・baseline_cat_map と phase10_cat_map の hash が異なる "
                    "(category mapping ドリフト・B-3 同一 trainer 設定の前提崩れ)・"
                    "baseline=%s... phase10=%s...",
                    baseline_cat_hash[:16],
                    phase10_cat_hash[:16],
                )
                _write_gate_failure_report(
                    eval_dir,
                    reason="W-3 category_map bit-identity violation",
                    baseline_cat_hash=baseline_cat_hash,
                    phase10_cat_hash=phase10_cat_hash,
                    args=args,
                )
                return 2  # gate FAIL (W-3 前提違反)

        # W-2: train/calib 窓の候補 {0.0,0.1,0.25,0.5} adjusted_score 分布 (§11.2 聖域・test 窓は含めない)
        # orchestrator.train_and_predict 呼出の前に出力 (diagnostic は証跡であって gate 条件にはしない)
        w2_result = _compute_w2_diagnostics(phase10_frame, out_dir=out_dir)

        # REVIEW H6 (5d): orchestrator.train_and_predict 呼出 (両 snapshot・同一 trainer 設定)
        # baseline 呼出: snapshot_id=args.baseline_snapshot_id (v1.0 FEATURE_COLUMNS を明示選択)
        baseline_result = train_and_predict(
            baseline_frame,
            model_type="lightgbm",
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=baseline_cat_map,
        )
        # Phase 10 呼出: snapshot_id=args.phase10_snapshot_id (27 新 feature 含 FEATURE_COLUMNS を選択)
        phase10_result = train_and_predict(
            phase10_frame,
            model_type="lightgbm",
            feature_snapshot_id=args.phase10_snapshot_id,
            snapshot_id=args.phase10_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=phase10_cat_map,
        )

        # model_version 採番 (review HIGH#4・報告用)
        baseline_model_version = make_model_version(args.baseline_snapshot_id, "lightgbm", 1)
        phase10_model_version = make_model_version(args.phase10_snapshot_id, "lightgbm", 1)
        logger.info("baseline model_version: %s", baseline_model_version)
        logger.info("Phase 10 model_version: %s", phase10_model_version)

        # orchestrator.train_and_predict の pred_df は label (fukusho_hit_validated) を保持しないため・
        # build_training_frame 済みの frame (label-joined) から label を JOIN する (Phase 5 idiom・
        # run_speed_figure_stopgate.py L638-667 と同一)。本 JOIN が無いと _evaluate_gate で
        # fukusho_hit_validated KeyError (todo 260626 step 1)。
        baseline_pred = _attach_label_to_pred(
            baseline_result["pred_df"], label_joined_frame=baseline_frame
        )
        phase10_pred = _attach_label_to_pred(
            phase10_result["pred_df"], label_joined_frame=phase10_frame
        )
        logger.info(
            "pred_df label JOIN 完了: baseline rows=%d / phase10 rows=%d",
            len(baseline_pred),
            len(phase10_pred),
        )

        # gate 判定 (B-3: 両実測値の delta)
        result = _evaluate_gate(
            baseline_pred=baseline_pred,
            phase10_pred=phase10_pred,
            baseline_model_version=baseline_model_version,
            phase10_model_version=phase10_model_version,
            args=args,
            w2_result=w2_result,
            baseline_cat_hash=baseline_cat_hash,
            phase10_cat_hash=phase10_cat_hash,
        )
    finally:
        readonly_pool.close()

    json_path, md_path = _write_reports(eval_dir, result)
    logger.info("wrote %s", json_path)
    logger.info("wrote %s", md_path)

    # gate verdict (B-3・D-16)
    gate_pass = bool(result["gate_pass"])
    if gate_pass:
        logger.info("SC#5 非劣化 gate: PASS (3条件全て D-16 許容幅内・delta 基準は baseline snapshot 実測値)")
        return 0
    logger.error(
        "SC#5 非劣化 gate: FAIL・どれかの指標が D-16 許容幅を超過 (§11.2 聖域・許容幅は変更せず feature 見直し)"
    )
    return 2  # gate FAIL (fail-loud)


def _attach_label_to_pred(
    pred_df: pd.DataFrame,
    *,
    label_joined_frame: pd.DataFrame,
) -> pd.DataFrame:
    """orchestrator.train_and_predict の pred_df に label (fukusho_hit_validated 等) を JOIN する。

    run_speed_figure_stopgate.py::_attach_label_and_harai の label 馬単位 merge 部分を抽出した
    最小版 (HARAI race-level 払戻 slot は SC#5 非劣化 gate の Brier/LogLoss/AUC 算出には不要・
    D-14 selected ROI 計算でのみ必要なため本 gate では省略)。

    orchestrator.train_and_predict の pred_df は label (fukusho_hit_validated) を保持しないため・
    本 JOIN が必須 (run_speed_figure_stopgate.py L638-667 と同一 idiom・todo 260626 step 1)。

    label_joined_frame は build_training_frame の出力 (label-joined・fukusho_hit_validated 含む)。
    pred_df と race_key + umaban で merge する (Phase 5 idiom・HIGH-1 馬単位保証)。
    """
    pred_df = pred_df.copy()
    label_df = label_joined_frame.copy()
    # umaban 型統一 (Phase 5 idiom・run_backtest.py L576-582): pred_df (object 揺れ) /
    # label_df で merge key 型不一致 ("str and Int64") → pd.to_numeric で Int64 正規化
    pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")
    label_df["umaban"] = pd.to_numeric(label_df["umaban"], errors="coerce").astype("Int64")

    # label 側の必要列だけ抽出 (fukusho_hit_validated + race_key/umaban)
    label_keep = ["race_key", "umaban", "fukusho_hit_validated"]
    # entry_count (compute_metrics の sum(p) 分布チェック用) も存在すれば付与
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
            f"len(before)={len(pred_df)} != len(after)={len(merged)} "
            "(label が馬単位でない・race_key+umaban 重複)"
        )
    # suffix 衝突解決 (CR-06: _label を正とする)
    for col in label_keep:
        if col in ("race_key", "umaban"):
            continue
        label_col = f"{col}_label"
        if label_col in merged.columns:
            merged[col] = merged[label_col]
            merged = merged.drop(columns=[label_col])

    # fukusho_hit_validated が JOIN 後も NaN の行があれば fail-loud (silent leak 防止・§19.1 聖域)
    n_missing = int(merged["fukusho_hit_validated"].isna().sum())
    if n_missing > 0:
        raise RuntimeError(
            f"_attach_label_to_pred: pred_df の {n_missing} 行に label が JOIN できなかった "
            "(race_key+umaban で label 側に対応行がない・silent leak・§19.1 聖域)"
        )
    return merged


def _evaluate_gate(
    *,
    baseline_pred: pd.DataFrame,
    phase10_pred: pd.DataFrame,
    baseline_model_version: str,
    phase10_model_version: str,
    args: argparse.Namespace,
    w2_result: dict[str, Any],
    baseline_cat_hash: str,
    phase10_cat_hash: str,
) -> dict[str, Any]:
    """両モデルの pred_df から Brier/LogLoss/AUC を算出し・D-16 許容幅で SC#5 非劣化 gate を判定する (B-3).

    delta 基準は baseline snapshot の**実測値** (BASELINE_* 定数=参考値ではない・B-3)。
    D-15 参考記録 (selected-only calibration / odds_band×p_bin) も見える化するが gate 判定には使わない。
    """
    # compute_metrics で Brier/LogLoss/AUC 算出 (binning 定数は evaluator から import 再利用・§15.2)
    baseline_metrics = compute_metrics(
        baseline_pred["fukusho_hit_validated"],
        baseline_pred["p_fukusho_hit"],
        race_keys=baseline_pred.get("race_key"),
        entry_counts=baseline_pred.get("entry_count"),
    )
    phase10_metrics = compute_metrics(
        phase10_pred["fukusho_hit_validated"],
        phase10_pred["p_fukusho_hit"],
        race_keys=phase10_pred.get("race_key"),
        entry_counts=phase10_pred.get("entry_count"),
    )

    baseline_brier = float(baseline_metrics.get("brier", float("nan")))
    baseline_logloss = float(baseline_metrics.get("logloss", float("nan")))
    baseline_auc = float(baseline_metrics.get("auc", float("nan")))
    phase10_brier = float(phase10_metrics.get("brier", float("nan")))
    phase10_logloss = float(phase10_metrics.get("logloss", float("nan")))
    phase10_auc = float(phase10_metrics.get("auc", float("nan")))

    # B-3: delta は両実測値の差 (BASELINE_* 定数でない)
    brier_delta = phase10_brier - baseline_brier
    logloss_delta = phase10_logloss - baseline_logloss
    auc_delta = phase10_auc - baseline_auc

    # D-16 gate 判定 (3条件の論理積)
    gate_pass = (
        (brier_delta <= TOLERANCE_BRIER)
        and (logloss_delta <= TOLERANCE_LOGLOSS)
        and (auc_delta >= -TOLERANCE_AUC)  # AUC は低下が違反 (符号注意)
    )

    # BASELINE_* 参考値との乖離 WARNING (B-3 鑑別資料・feature ノイズ化 vs trainer 設定ドリフト)
    baseline_drift = {
        "brier_drift": baseline_brier - BASELINE_BRIER,
        "logloss_drift": baseline_logloss - BASELINE_LOGLOSS,
        "auc_drift": baseline_auc - BASELINE_AUC,
        "warning": (
            "baseline 実測値が BASELINE_* 参考値 (Phase 6 当時) と大きく乖離している場合・"
            "trainer 設定ドリフト (LightGBM version/hyperparams/seed/category_map/split_periods 揺らぎ) "
            "を疑う (feature ノイズ化と設定ドリフトの鑑別・§11.2 聖域)"
        ),
    }

    # D-15 参考記録: selected-only calibration / odds_band×p_bin (gate 判定には使わない)
    # segment_eval.evaluate_all_segments は bit-identical な binning 定数を消費 (§15.2)
    d15_segments = {"note": "D-15 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない"}
    try:
        baseline_segments = evaluate_all_segments(baseline_pred)
        phase10_segments = evaluate_all_segments(phase10_pred)
        d15_segments["baseline"] = _sanitize_for_json(baseline_segments)
        d15_segments["phase10"] = _sanitize_for_json(phase10_segments)
    except Exception as e:
        # 参考記録なので失敗しても gate は継続・WARNING のみ
        logger.warning("D-15 segment_eval 失敗 (参考記録・gate 継続): %s", e)
        d15_segments["error"] = str(e)

    return {
        "gate_pass": bool(gate_pass),
        "baseline_metrics": {
            "brier": baseline_brier,
            "logloss": baseline_logloss,
            "auc": baseline_auc,
        },
        "phase10_metrics": {
            "brier": phase10_brier,
            "logloss": phase10_logloss,
            "auc": phase10_auc,
        },
        "delta": {
            "brier_delta": brier_delta,
            "logloss_delta": logloss_delta,
            "auc_delta": auc_delta,
        },
        "tolerance": {
            "brier": TOLERANCE_BRIER,
            "logloss": TOLERANCE_LOGLOSS,
            "auc": TOLERANCE_AUC,
            "note": "D-16 事前登録許容幅 (§11.2 聖域・Open Question #4 解決)・評価後変更しない",
        },
        "baseline_constants_reference": {
            "BASELINE_BRIER": BASELINE_BRIER,
            "BASELINE_LOGLOSS": BASELINE_LOGLOSS,
            "BASELINE_AUC": BASELINE_AUC,
            "note": (
                "Phase 6 D-07 当時参考値・gate 判定の delta 基準でない (B-3・baseline snapshot 実測値が delta 基準)"
            ),
        },
        "baseline_drift_warning": baseline_drift,
        "d15_reference_segments": d15_segments,
        "w2_candidate_score_diagnostics": w2_result,
        "w3_category_map_bit_identity": {
            "baseline_cat_map_hash": baseline_cat_hash,
            "phase10_cat_map_hash": phase10_cat_hash,
            "bit_identical": baseline_cat_hash == phase10_cat_hash,
        },
        "model_versions": {
            "baseline": baseline_model_version,
            "phase10": phase10_model_version,
        },
        "args": {
            "baseline_snapshot_id": args.baseline_snapshot_id,
            "phase10_snapshot_id": args.phase10_snapshot_id,
            "bt_split": args.bt_split,
            "odds_snapshot_policy": args.odds_snapshot_policy,
        },
        "binning_source": {
            "CALIBRATION_CURVE_BINS": CALIBRATION_CURVE_BINS,
            "CALIBRATION_CURVE_MIN_BIN_COUNT": CALIBRATION_CURVE_MIN_BIN_COUNT,
            "ODDS_BAND_EDGES": ODDS_BAND_EDGES,
            "NINKI_BAND_EDGES": NINKI_BAND_EDGES,
            "note": "§15.2 事前登録指標不変・evaluator/segment_eval から import 再利用 (再定義禁止)",
        },
        "safe_01_note": (
            "Phase 10 snapshot は PLAN 05 で odds-free を実証済み (registry derived FEATURE_COLUMNS・"
            "SAFE-01・SC#4 AST audit 対象)。run_phase10_evaluation.py は market データを diagnostic "
            "層 (D-15 segment_eval) でのみ使用し FEATURE_COLUMNS には混入しない。"
        ),
    }


def _write_gate_failure_report(
    eval_dir: Path,
    *,
    reason: str,
    baseline_cat_hash: str,
    phase10_cat_hash: str,
    args: argparse.Namespace,
) -> None:
    """W-3 bit-identity 違反等で gate が早期 FAIL した際の最小レポートを書出す。"""
    result = {
        "gate_pass": False,
        "fail_reason": reason,
        "w3_category_map_bit_identity": {
            "baseline_cat_map_hash": baseline_cat_hash,
            "phase10_cat_map_hash": phase10_cat_hash,
            "bit_identical": baseline_cat_hash == phase10_cat_hash,
        },
        "args": {
            "baseline_snapshot_id": args.baseline_snapshot_id,
            "phase10_snapshot_id": args.phase10_snapshot_id,
            "bt_split": args.bt_split,
            "odds_snapshot_policy": args.odds_snapshot_policy,
        },
    }
    json_path, md_path = _write_reports(eval_dir, result)
    logger.info("wrote gate-fail report %s / %s", json_path, md_path)


def _write_reports(eval_dir: Path, result: dict[str, Any]) -> tuple[Path, Path]:
    """reports/10-evaluation/10-evaluation.{md,json} を atomic write する (REVIEW M4 sanitizer 適用済)."""
    eval_dir.mkdir(parents=True, exist_ok=True)
    json_path = eval_dir / "10-evaluation.json"
    md_path = eval_dir / "10-evaluation.md"

    sanitized = _sanitize_for_json(result)
    json_text = json.dumps(sanitized, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
    md_text = _format_markdown_report(result)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    return json_path, md_path


def _format_markdown_report(result: dict[str, Any]) -> str:
    """SC#5 非劣化 gate の Markdown レポートを構築する (B-3・D-16)."""
    lines: list[str] = []
    lines.append("# Phase 10 SC#5 非劣化 Gate: v1.0 baseline vs Phase 10 snapshot (opponentstrength)")
    lines.append("")
    lines.append("## Gate Verdict (D-16 事前登録許容幅)")
    lines.append("")
    gate_pass = result.get("gate_pass", False)
    verdict = "PASS (3条件全て D-16 許容幅内・delta 基準は baseline snapshot 実測値)" if gate_pass else "FAIL (D-16 許容幅超過・§11.2 聖域・feature 見直し)"
    lines.append(f"**{verdict}**")
    if "fail_reason" in result:
        lines.append(f"**早期 FAIL 理由:** {result['fail_reason']}")
    lines.append("")

    # 早期 FAIL (W-3 違反等) の場合はここで終了
    if "baseline_metrics" not in result:
        lines.append("## W-3 category_map bit-identity")
        w3 = result.get("w3_category_map_bit_identity", {})
        lines.append(f"- baseline_cat_map_hash: {w3.get('baseline_cat_map_hash', '')[:32]}...")
        lines.append(f"- phase10_cat_map_hash: {w3.get('phase10_cat_map_hash', '')[:32]}...")
        lines.append(f"- bit_identical: {w3.get('bit_identical', False)}")
        return "\n".join(lines)

    baseline = result.get("baseline_metrics", {})
    phase10 = result.get("phase10_metrics", {})
    delta = result.get("delta", {})
    tol = result.get("tolerance", {})

    lines.append("## B-3 両 snapshot 実測値・delta (delta 基準は baseline snapshot 実測値)")
    lines.append("")
    lines.append("| 指標 | baseline 実測 | Phase 10 実測 | delta | D-16 許容幅 | 判定 |")
    lines.append("|------|-------------|--------------|-------|------------|------|")
    brier_ok = delta.get("brier_delta", float("inf")) <= tol.get("brier", 0)
    logloss_ok = delta.get("logloss_delta", float("inf")) <= tol.get("logloss", 0)
    auc_ok = delta.get("auc_delta", float("-inf")) >= -tol.get("auc", 0)
    lines.append(
        f"| Brier | {baseline.get('brier'):.5f} | {phase10.get('brier'):.5f} | "
        f"{delta.get('brier_delta'):+.5f} | <= +{tol.get('brier')} | {'PASS' if brier_ok else 'FAIL'} |"
    )
    lines.append(
        f"| LogLoss | {baseline.get('logloss'):.5f} | {phase10.get('logloss'):.5f} | "
        f"{delta.get('logloss_delta'):+.5f} | <= +{tol.get('logloss')} | {'PASS' if logloss_ok else 'FAIL'} |"
    )
    lines.append(
        f"| AUC | {baseline.get('auc'):.5f} | {phase10.get('auc'):.5f} | "
        f"{delta.get('auc_delta'):+.5f} | >= -{tol.get('auc')} | {'PASS' if auc_ok else 'FAIL'} |"
    )
    lines.append("")

    lines.append("## BASELINE_* 参考値との乖離 WARNING (B-3 鑑別資料)")
    lines.append("")
    ref = result.get("baseline_constants_reference", {})
    drift = result.get("baseline_drift_warning", {})
    lines.append(f"- BASELINE_BRIER (Phase 6 当時): {ref.get('BASELINE_BRIER')} / baseline 実測: {baseline.get('brier'):.5f} / drift: {drift.get('brier_drift', 0):+.5f}")
    lines.append(f"- BASELINE_LOGLOSS (Phase 6 当時): {ref.get('BASELINE_LOGLOSS')} / baseline 実測: {baseline.get('logloss'):.5f} / drift: {drift.get('logloss_drift', 0):+.5f}")
    lines.append(f"- BASELINE_AUC (Phase 6 当時): {ref.get('BASELINE_AUC')} / baseline 実測: {baseline.get('auc'):.5f} / drift: {drift.get('auc_drift', 0):+.5f}")
    lines.append(f"- {drift.get('warning', '')}")
    lines.append("")

    lines.append("## W-2 candidate score diagnostics (0.25 canonical 妥当性証拠)")
    w2 = result.get("w2_candidate_score_diagnostics", {})
    lines.append(f"- status: {w2.get('status', 'unknown')}")
    if w2.get("status") == "ok":
        lines.append(f"- train: {w2.get('train_path')}")
        lines.append(f"- calib: {w2.get('calib_path')}")
    lines.append("- §11.2 聖域: 候補選定は train/calib 窓内のみ・test 窓 rank はすり替えない")
    lines.append("")

    lines.append("## W-3 category_map bit-identity (B-3 同一 trainer 設定の前提)")
    w3 = result.get("w3_category_map_bit_identity", {})
    lines.append(f"- baseline_cat_map_hash: {w3.get('baseline_cat_map_hash', '')[:32]}...")
    lines.append(f"- phase10_cat_map_hash: {w3.get('phase10_cat_map_hash', '')[:32]}...")
    lines.append(f"- bit_identical: {w3.get('bit_identical', False)}")
    lines.append("")

    lines.append("## §15.2 binning 契約 (import 再利用・再定義禁止)")
    bs = result.get("binning_source", {})
    lines.append(f"- CALIBRATION_CURVE_BINS: {bs.get('CALIBRATION_CURVE_BINS')}")
    lines.append(f"- CALIBRATION_CURVE_MIN_BIN_COUNT: {bs.get('CALIBRATION_CURVE_MIN_BIN_COUNT')}")
    lines.append(f"- ODDS_BAND_EDGES: {bs.get('ODDS_BAND_EDGES')}")
    lines.append(f"- NINKI_BAND_EDGES: {bs.get('NINKI_BAND_EDGES')}")
    lines.append("")

    lines.append("## D-15 参考記録 (selected-only calibration / odds_band×p_bin)")
    lines.append("- 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない (Brier/LogLoss/AUC の3条件のみが gate)")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    raise SystemExit(main())
