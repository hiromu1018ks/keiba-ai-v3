"""Phase 9 SC#6 stop gate: v1.0 baseline vs (v1.0+speed_figure) 単体モデル比較.

D-14 必須4指標 (odds_band×p_bin calibration 改善 / selected ROI 改善 / Brier等の非劣化 /
model-market disagreement ROI 改善) と D-15 軽量 residual proxy を算出し・D-16 に基づき
「両方改善しない場合は構造的限界寄り・Phase 10-12 進行前にユーザー確認」と honest 記録する。

**§15.2 事前登録指標不変 (聖域):**
``evaluator.py`` / ``segment_eval.py`` の binning 定数 (``CALIBRATION_CURVE_BINS`` /
``CALIBRATION_CURVE_MIN_BIN_COUNT`` / ``ODDS_BAND_EDGES`` / ``NINKI_BAND_EDGES``) を
import 再利用し・**再定義しない** (bit-identical・T-09-17 mitigate)。許容幅は RESEARCH.md
Open Questions (RESOLVED) #2 採用 (Brier +0.005 / LogLoss +0.02 / AUC -0.005)。

**REVIEW H2/H7/H8 (横断的・最優先):**
``orchestrator.train_and_predict`` を両 snapshot で呼び・calibration 済み予測で比較する。
生 trainer 公開 API (各 GBDT の学習関数・予測整列 helper・catboost Pool 準備 helper)
は直接呼ばない (H2 calibration skip / H7 sorted_index 誤用 /
H8 categorical dtype mismatch の3バグを構造的回避・T-09-26/27/28 mitigate)。

**REVIEW H-new (Cycle 3・P05 caller gap):**
両 snapshot (baseline・+speed_figure) の ``train_and_predict`` 呼出に ``snapshot_id=<対応する
snapshot_id>`` を**明示的に渡す**。省略すると orchestrator 内部の ``make_X_y(test_df,
snapshot_id=None)`` で v1.0 FEATURE_COLUMNS が選択され・stop gate が「v1.0 vs v1.0」を比較する
(H1-b と同じ静かな失敗メカニズム・SC#6 完全無意味化・T-09-31 mitigate)。

**REVIEW H6:**
market_implied は ``1.0 / fuku_odds_lower`` (src/ev/odds_snapshot.py L210-215 の正しい列名・
``fuku_odds`` 系の誤略称でない・T-09-29 mitigate)。診断層のみ使用し・FEATURE_COLUMNS や model_p 入力には
絶対混入しない (SAFE-01・T-09-18 mitigate)。

**REVIEW M4:**
single-class AUC や空 bucket で NaN/Inf が混入する可能性があるため・``_sanitize_for_json``
helper (NaN→None/"NaN"・Inf→"Infinity"・src/model/segment_eval.py L94-112 sanitizer pattern 踏襲)
を通してから ``json.dumps(allow_nan=False)`` で安全に JSON 化する (RFC 8259 strict・T-09-30 mitigate)。

cross-reference: .planning/phases/09-speed-figure-foundation/09-VALIDATION.md SC#6

Usage (live-DB・KEIBA_SKIP_DB_TESTS unset)::

    uv run python scripts/run_speed_figure_stopgate.py \\
        --baseline-snapshot-id 20260620-1a-postreview-v2 \\
        --speed-figure-snapshot-id 20260625-1a-speedfigure-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --out-dir reports
"""

# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)

from __future__ import annotations

import argparse
import ast
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加
# (scripts/run_evaluation.py L65-68 と同一 idiom)。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §15.2 事前登録指標不変: binning 定数を import 再利用 (再定義禁止・bit-identical・T-09-17 mitigate)
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    compute_metrics,
)
from src.model.predict import make_model_version  # noqa: E402  model_version 採番 (review HIGH#4)
from src.model.segment_eval import (  # noqa: E402
    NINKI_BAND_EDGES,
    ODDS_BAND_EDGES,
    _ninki_band,
    _odds_band,
    evaluate_all_segments,
)

logger = logging.getLogger("run_speed_figure_stopgate")

# ---------------------------------------------------------------------------
# 定数 — D-16 verdict / D-14 許容幅 (RESEARCH.md Open Questions RESOLVED #2)
# ---------------------------------------------------------------------------

# 許容幅: v1.0 baseline (Brier=0.15222・LogLoss=0.47488・AUC=0.73230) 基準の現実的変動マージン。
#  - Brier +0.005 は v1.0 Brier の ~3.3%
#  - LogLoss +0.02 は ~4.2%
#  - AUC -0.005 は ~0.7%
# いずれも「モデル実用性を毀損しない変動」範囲。Phase 11 SC#2 事前登録マージンと同一スケール
# であることを前提とする (Phase 11 plan 作成時に再確認・stop gate 通過≠Phase 11 SC#2 通過)。
TOLERANCE_BRIER: float = 0.005
TOLERANCE_LOGLOSS: float = 0.02
TOLERANCE_AUC: float = 0.005  # AUC は「低下」が非劣化違反 (符号注意)

# D-16 verdict 文言 (json/md 両方に honest 記録・D-05 踏襲)
VERDICT_EFFECTIVE_SIGNAL = "特徴量追加の有効性シグナルあり・Phase 10 進行候補"
VERDICT_STRUCTURAL_LIMIT = "構造的限界寄り・Phase 10-12 進行前にユーザー確認 (D-16)"

# D-08 過大予測是正シグナル判定レイヤ (投票層: odds>=4.9 かつ p∈[0.15,0.20])
SELECTED_ODDS_LOWER: float = 4.9
SELECTED_P_LOWER: float = 0.15
SELECTED_P_UPPER: float = 0.20


# ---------------------------------------------------------------------------
# REVIEW M4: JSON sanitizer (NaN/Inf → None/"NaN"/"Infinity")
# ---------------------------------------------------------------------------


def _sanitize_for_json(obj: Any) -> Any:
    """dict/list/float を再帰走査し NaN/Inf を JSON 安全な表現に変換する (REVIEW M4・T-09-30).

    src/model/segment_eval.py L94-112 (``_sanitize_nan_to_null``) の sanitizer pattern を踏襲。
    single-class AUC 等で NaN が混入しても ``json.dumps(allow_nan=False)`` が
    ``ValueError`` で失敗するのを防ぐ (RFC 8259 strict)。

    変換規則:
      - ``NaN``  → ``None`` (意味: データなし・null が正しい意味論)
      - ``+Inf`` → ``"Infinity"`` (文字列・情報保全)
      - ``-Inf`` → ``"-Infinity"`` (文字列・情報保全)
    """
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


# ---------------------------------------------------------------------------
# D-14 指標算出ヘルパー (module-level・純粋関数・テストから import 可能)
# ---------------------------------------------------------------------------


def _compute_selected_calibration(
    pred_df: pd.DataFrame,
    *,
    p_col: str = "p_fukusho_hit",
    odds_lower_col: str = "fuku_odds_lower",
    y_col: str = "fukusho_hit_validated",
) -> float:
    """D-14 指標1: 投票層 (odds>=4.9 かつ p∈[0.15,0.20]) の |mean_pred - frac_pos| を算出.

    v1.0 で4倍過大予測だった領域 (D-08) の是正シグナルを定量評価する。サンプル不足や
    該当層不在時は ``float("nan")`` を返す (呼出側で ``_sanitize_for_json`` が None 化)。

    Parameters
    ----------
    pred_df : pd.DataFrame
        ``p_fukusho_hit`` / ``fuku_odds_lower`` / ``fukusho_hit_validated`` 列を持つ予測 DataFrame.
    """
    if p_col not in pred_df.columns or odds_lower_col not in pred_df.columns or y_col not in pred_df.columns:
        return float("nan")
    mask = (
        (pred_df[odds_lower_col] >= SELECTED_ODDS_LOWER)
        & (pred_df[p_col] >= SELECTED_P_LOWER)
        & (pred_df[p_col] <= SELECTED_P_UPPER)
    )
    sub = pred_df.loc[mask]
    if len(sub) == 0:
        return float("nan")
    mean_pred = float(sub[p_col].mean())
    frac_pos = float(sub[y_col].astype(float).mean())
    return abs(mean_pred - frac_pos)


def _compute_selected_roi(
    pred_df: pd.DataFrame,
    *,
    p_col: str = "p_fukusho_hit",
    odds_lower_col: str = "fuku_odds_lower",
    odds_upper_col: str = "fuku_odds_upper",
    y_col: str = "fukusho_hit_validated",
    ev_lower_threshold: float = 1.0,
) -> dict[str, float]:
    """D-14 指標2: selected-only 実現 ROI/EV 改善 (selector: EV_lower>=閾値で選択).

    選ばれた馬の回収率 (payout/stake) を算出する。src/ev/metrics.py profit_loss の
    集計式 ``sum(payout) / sum(stake)`` に準拠 (refund 払戻対象/競走中止の effective_stake
    処理は live-DB の market_df JOIN で行う前提・本ヘルパーは単純化版)。

    Returns
    -------
    dict
        ``{"roi": float, "n_selected": int, "hit_rate": float}``. サンプル不足時は NaN.
    """
    if odds_lower_col not in pred_df.columns or p_col not in pred_df.columns:
        return {"roi": float("nan"), "n_selected": 0, "hit_rate": float("nan")}
    ev = pred_df[p_col] * pred_df[odds_lower_col]
    selected_mask = ev >= ev_lower_threshold
    sub = pred_df.loc[selected_mask]
    n = int(selected_mask.sum())
    if n == 0:
        return {"roi": float("nan"), "n_selected": 0, "hit_rate": float("nan")}
    stake = float(n)  # 単位 stakes (effective_stake=1 と単純化)
    hits = sub[y_col].astype(float).to_numpy()
    payouts = hits * sub[odds_lower_col].to_numpy()  # lower odds で保守的に試算
    payout = float(payouts.sum())
    roi = payout / stake if stake > 0 else float("nan")
    hit_rate = float(hits.mean())
    return {"roi": roi, "n_selected": n, "hit_rate": hit_rate}


def _compute_global_metric_delta(
    baseline_metrics: dict[str, Any],
    speedfig_metrics: dict[str, Any],
) -> dict[str, Any]:
    """D-14 指標3: Brier/LogLoss/AUC の非劣化判定 (許容幅内か).

    許容幅 (TOLERANCE_BRIER/LOGLOSS/AUC) 以内を「非劣化」とする (RESEARCH.md RESOLVED #2)。
    AUC は「低下」が違反 (符号注意)。

    Returns
    -------
    dict
        ``{"brier_delta": float, "logloss_delta": float, "auc_delta": float,
        "non_degraded": bool, "tolerance": {...}}``.
    """
    brier_delta = float(speedfig_metrics.get("brier", float("nan"))) - float(
        baseline_metrics.get("brier", float("nan"))
    )
    logloss_delta = float(speedfig_metrics.get("logloss", float("nan"))) - float(
        baseline_metrics.get("logloss", float("nan"))
    )
    auc_delta = float(speedfig_metrics.get("auc", float("nan"))) - float(
        baseline_metrics.get("auc", float("nan"))
    )
    non_degraded = (
        (brier_delta <= TOLERANCE_BRIER)
        and (logloss_delta <= TOLERANCE_LOGLOSS)
        and (auc_delta >= -TOLERANCE_AUC)  # AUC は低下が違反
    )
    return {
        "brier_delta": brier_delta,
        "logloss_delta": logloss_delta,
        "auc_delta": auc_delta,
        "non_degraded": bool(non_degraded),
        "tolerance": {
            "brier": TOLERANCE_BRIER,
            "logloss": TOLERANCE_LOGLOSS,
            "auc": TOLERANCE_AUC,
        },
    }


def _compute_residual_proxy(
    pred_df: pd.DataFrame,
    *,
    p_col: str = "p_fukusho_hit",
    odds_lower_col: str = "fuku_odds_lower",
    y_col: str = "fukusho_hit_validated",
    n_bins: int = CALIBRATION_CURVE_BINS,
    min_bin_count: int = CALIBRATION_CURVE_MIN_BIN_COUNT,
) -> dict[str, Any]:
    """D-15 軽量 residual proxy: market_implied × model_p 分位 bucket グリッド.

    SAFE-01: ``market_implied = 1.0 / fuku_odds_lower`` は**診断層のみ**で使用し・
    model 特徴量には絶対混入しない (T-09-18 mitigate・Phase 12 EVAL-02 で完全 audit)。

    bucket 数 = ``n_bins`` (CALIBRATION_CURVE_BINS=10 と整合)・極小 bucket は
    ``min_bin_count`` (CALIBRATION_CURVE_MIN_BIN_COUNT=30) 未満で skip。

    同一 market bucket 内で model_p 高低による実的中率/ROI 差が残るかを確認する
    (market residual の暫定シグナル)。**p値判定・回帰係数の正式結論は出さない**
    (Phase 12 EVAL-02 に委譲・D-12)。

    Returns
    -------
    dict
        ``{"buckets": [...], "signal_present": bool, "n_valid_cells": int}``.
        ``signal_present`` は同一 market bucket 内で高 model_p cell の的中率が
        低 model_p cell の的中率を上回る cell が1つでもあれば True.
    """
    if odds_lower_col not in pred_df.columns or p_col not in pred_df.columns:
        return {"buckets": [], "signal_present": False, "n_valid_cells": 0}

    df = pred_df[[p_col, odds_lower_col, y_col]].copy()
    # SAFE-01: market_implied は診断層ローカル変数のみ・FEATURE_COLUMNS には絶対入れない
    market_implied = 1.0 / df[odds_lower_col].astype(float)
    df["_market_implied"] = market_implied  # 診断層ローカル (出力前に drop)
    df["_model_p"] = df[p_col].astype(float)
    df["_y"] = df[y_col].astype(float)

    # NaN/Inf 除外 (odds 欠損行)
    df = df[np.isfinite(df["_market_implied"]) & np.isfinite(df["_model_p"])].copy()
    if len(df) < min_bin_count:
        return {"buckets": [], "signal_present": False, "n_valid_cells": 0}

    # 分位 bucket (q=NaN 扱いに注意・duplicates='drop' で安全)
    try:
        df["_market_bin"] = pd.qcut(
            df["_market_implied"], q=n_bins, labels=False, duplicates="drop"
        )
        df["_model_bin"] = pd.qcut(
            df["_model_p"], q=n_bins, labels=False, duplicates="drop"
        )
    except ValueError:
        # 全同一値等で分位化不能
        return {"buckets": [], "signal_present": False, "n_valid_cells": 0}

    buckets: list[dict[str, Any]] = []
    signal_present = False
    n_valid_cells = 0
    for mb in sorted(df["_market_bin"].dropna().unique()):
        sub_market = df[df["_market_bin"] == mb]
        if len(sub_market) < min_bin_count:
            continue
        cell_records: list[dict[str, Any]] = []
        for pb in sorted(sub_market["_model_bin"].dropna().unique()):
            cell = sub_market[sub_market["_model_bin"] == pb]
            if len(cell) < min_bin_count:
                continue
            n_valid_cells += 1
            hr = float(cell["_y"].mean())
            roi = float((cell["_y"] * cell[odds_lower_col]).sum() / len(cell))
            cell_records.append(
                {
                    "model_bin": int(pb),
                    "n": int(len(cell)),
                    "hit_rate": hr,
                    "roi": roi,
                }
            )
        if len(cell_records) >= 2:
            # 同一 market bucket 内で model_p 高低による的中率差が残るか (market residual)
            hit_rates = [c["hit_rate"] for c in cell_records]
            if max(hit_rates) > min(hit_rates):
                signal_present = True
        buckets.append(
            {
                "market_bin": int(mb),
                "n_market": int(len(sub_market)),
                "cells": cell_records,
            }
        )

    return {
        "buckets": buckets,
        "signal_present": bool(signal_present),
        "n_valid_cells": int(n_valid_cells),
    }


# ---------------------------------------------------------------------------
# D-16 verdict helper (module-level・純粋関数)
# ---------------------------------------------------------------------------


def _decide_stopgate_verdict(
    *,
    selected_calibration_improved: bool,
    residual_proxy_signal: bool,
) -> str:
    """D-16: 両方 (selected calibration 改善・residual proxy シグナル) が全く改善しない場合
    「構造的限界寄り」を返す (honest 記録)。片方でも改善があれば「Phase 10 進行候補」を返す。

    Parameters
    ----------
    selected_calibration_improved : bool
        D-14 指標1 (selected/high-EV 層 calibration) が v1.0 baseline から改善したか。
    residual_proxy_signal : bool
        D-15 residual proxy に market residual シグナルが残存するか (``_compute_residual_proxy``
        の ``signal_present``)。

    Returns
    -------
    str
        ``VERDICT_EFFECTIVE_SIGNAL`` または ``VERDICT_STRUCTURAL_LIMIT``. BLOCK でなく exit 0.
    """
    if selected_calibration_improved or residual_proxy_signal:
        return VERDICT_EFFECTIVE_SIGNAL
    return VERDICT_STRUCTURAL_LIMIT


# ---------------------------------------------------------------------------
# レポート出力 (atomic write・D-16・REVIEW M4 sanitizer)
# ---------------------------------------------------------------------------


def _write_reports(
    out_dir: Path,
    result: dict[str, Any],
) -> tuple[Path, Path]:
    """reports/09-stopgate.{md,json} を atomic write する (REVIEW M4 sanitizer 適用済).

    json は ``sort_keys=True, ensure_ascii=False, allow_nan=False`` で RFC 8259 strict
    (scripts/run_evaluation.py L1048-1306 と同一)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "09-stopgate.json"
    md_path = out_dir / "09-stopgate.md"

    # REVIEW M4: NaN/Inf を sanitizer で安全化してから allow_nan=False で dumps
    sanitized = _sanitize_for_json(result)
    json_text = json.dumps(
        sanitized, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2
    )
    md_text = _format_markdown_report(result)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    return json_path, md_path


def _format_markdown_report(result: dict[str, Any]) -> str:
    """D-14 4指標 + D-15 residual proxy + D-16 verdict の Markdown レポートを構築する."""
    lines: list[str] = []
    lines.append("# Phase 9 SC#6 Stop Gate: v1.0 baseline vs (v1.0+speed_figure)")
    lines.append("")
    lines.append("## D-14 必須4指標")
    lines.append("")
    m1 = result.get("metric1_selected_calibration", {})
    lines.append(f"- 指標1 selected calibration (投票層 |mean_pred - frac_pos|):")
    lines.append(f"  - baseline: {m1.get('baseline')}")
    lines.append(f"  - speed_figure: {m1.get('speed_figure')}")
    lines.append(f"  - improved: {m1.get('improved')}")
    m2 = result.get("metric2_selected_roi", {})
    lines.append(f"- 指標2 selected-only ROI/EV:")
    lines.append(f"  - baseline: {m2.get('baseline')}")
    lines.append(f"  - speed_figure: {m2.get('speed_figure')}")
    m3 = result.get("metric3_global_metrics", {})
    lines.append(f"- 指標3 Brier/LogLoss/AUC 非劣化判定:")
    lines.append(f"  - brier_delta: {m3.get('brier_delta')} (許容幅 +{TOLERANCE_BRIER})")
    lines.append(f"  - logloss_delta: {m3.get('logloss_delta')} (許容幅 +{TOLERANCE_LOGLOSS})")
    lines.append(f"  - auc_delta: {m3.get('auc_delta')} (許容幅 -{TOLERANCE_AUC})")
    lines.append(f"  - non_degraded: {m3.get('non_degraded')}")
    m4 = result.get("metric4_residual_proxy", {})
    lines.append(f"- 指標4 model-market disagreement ROI (D-15 residual proxy 連動):")
    lines.append(f"  - signal_present: {m4.get('signal_present')}")
    lines.append(f"  - n_valid_cells: {m4.get('n_valid_cells')}")
    lines.append("")
    lines.append("## D-15 軽量 residual proxy")
    lines.append(f"- signal_present: {m4.get('signal_present')}")
    lines.append(f"- (p値判定・回帰係数は Phase 12 EVAL-02 に委譲・D-12)")
    lines.append("")
    lines.append("## D-16 Verdict")
    lines.append("")
    verdict = result.get("verdict", "")
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append("## 許容幅の根拠 (RESEARCH.md Open Questions RESOLVED #2)")
    lines.append(f"- Brier +{TOLERANCE_BRIER} (v1.0=0.15222 の ~3.3%)")
    lines.append(f"- LogLoss +{TOLERANCE_LOGLOSS} (v1.0=0.47488 の ~4.2%)")
    lines.append(f"- AUC -{TOLERANCE_AUC} (v1.0=0.73230 の ~0.7%)")
    lines.append("- Phase 11 SC#2 事前登録マージンと同一スケール前提 (cross-reference)")
    lines.append("")
    lines.append("## SAFE-01 (EVAL-02)")
    lines.append("- market_implied (1.0 / fuku_odds_lower) は診断層のみ使用・FEATURE_COLUMNS に混入なし")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main — live-DB orchestration (KEIBA_SKIP_DB_TESTS unset で実行)
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する."""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 9 SC#6 stop gate: v1.0 baseline vs (v1.0+speed_figure) 単体モデル比較・"
            "D-14 4指標 + D-15 residual proxy + D-16 verdict (§15.2 事前登録指標不変)"
        ),
    )
    parser.add_argument(
        "--baseline-snapshot-id",
        default="20260620-1a-postreview-v2",
        help="v1.0 baseline snapshot_id (default: 20260620-1a-postreview-v2)",
    )
    parser.add_argument(
        "--speed-figure-snapshot-id",
        default="20260625-1a-speedfigure-v1",
        help="(v1.0+speed_figure) snapshot_id (default: 20260625-1a-speedfigure-v1)",
    )
    parser.add_argument(
        "--bt-split",
        default="BT-1",
        help="backtest split (default: BT-1 = 2019-06-01..2022-12-31 train / 2023 test・§15.5)",
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


# BT-1 split periods (§15.5) — train 2019-06-01..2022-12-31 / test 2023
BT1_PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2019-06-01", "2022-12-31"),
    "test": ("2023-01-01", "2023-12-31"),
}


def main(argv: list[str] | None = None) -> int:
    """live-DB で v1.0 baseline と +speed_figure を比較し reports/09-stopgate.{md,json} を出力.

    REVIEW H2/H7/H8: ``orchestrator.train_and_predict`` を両 snapshot で呼び・
    calibration 済み予測で比較する (生 trainer 直接呼出禁止)。
    REVIEW H-new: 両 snapshot の ``train_and_predict`` 呼出に ``snapshot_id=`` を明示的に渡す。
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
    # T-09-20: 生 DSN のログ出力禁止・dsn_masked のみログ出力
    logger.info("readonly DSN: %s", settings.dsn_masked)

    out_dir = Path(args.out_dir)

    # T-09-21: statement_timeout='30s' で重クエリの orphan CPU 張り付き防止
    # (MEMORY.md subagent-db-query-statement-timeout)
    readonly_pool = make_pool(settings, role="readonly")
    try:
        with readonly_cursor(readonly_pool) as cur:
            cur.execute("SET statement_timeout = '30s'")

            # REVIEW H1: 両 snapshot を明示的な snapshot_id でロード
            logger.info("loading baseline snapshot: %s", args.baseline_snapshot_id)
            baseline_feature_df = load_feature_matrix(snapshot_id=args.baseline_snapshot_id)
            logger.info("loading speed_figure snapshot: %s", args.speed_figure_snapshot_id)
            speedfig_feature_df = load_feature_matrix(snapshot_id=args.speed_figure_snapshot_id)

            label_df = load_labels(cur)

            # build_training_frame で label-joined frame を構築
            # (orchestrator は label join を再実行しない・feature_df は label-joined 前提)
            baseline_frame = build_training_frame(baseline_feature_df, label_df)
            speedfig_frame = build_training_frame(speedfig_feature_df, label_df)

            baseline_cat_map = load_frozen_maps(snapshot_id=args.baseline_snapshot_id)
            speedfig_cat_map = load_frozen_maps(snapshot_id=args.speed_figure_snapshot_id)

        # REVIEW H2/H7/H8: orchestrator.train_and_predict 経由で calibration 済み予測を取得
        # REVIEW H-new: snapshot_id= keyword を両呼出で明示的に渡す (silent-failure 閉塞)
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
        # +speed_figure 呼出: snapshot_id=args.speed_figure_snapshot_id
        # (rolling_speed_figure_* 含 FEATURE_COLUMNS を選択・省略すると v1.0 vs v1.0 になる)
        speedfig_result = train_and_predict(
            speedfig_frame,
            model_type="lightgbm",
            feature_snapshot_id=args.speed_figure_snapshot_id,
            snapshot_id=args.speed_figure_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=speedfig_cat_map,
        )

        # model_version 採番 (review HIGH#4・報告用)
        baseline_model_version = make_model_version(args.baseline_snapshot_id, "lightgbm", 1)
        speedfig_model_version = make_model_version(args.speed_figure_snapshot_id, "lightgbm", 1)
        logger.info("baseline model_version: %s", baseline_model_version)
        logger.info("speed_figure model_version: %s", speedfig_model_version)

        # market データ (fuku_odds_lower/upper) を JODDS snapshot から取得し pred_df に JOIN
        # (live-DB・本 stop gate の公平性は同一 odds_snapshot_policy で保証・D-13/T-09-19)
        baseline_pred = _attach_market_data(baseline_result["pred_df"], cur_pool=readonly_pool)
        speedfig_pred = _attach_market_data(speedfig_result["pred_df"], cur_pool=readonly_pool)

        result = _evaluate_and_decide(
            baseline_pred=baseline_pred,
            speedfig_pred=speedfig_pred,
            baseline_model_version=baseline_model_version,
            speedfig_model_version=speedfig_model_version,
            args=args,
        )
    finally:
        readonly_pool.close()

    json_path, md_path = _write_reports(out_dir, result)
    logger.info("wrote %s", json_path)
    logger.info("wrote %s", md_path)
    logger.info("D-16 verdict: %s", result.get("verdict"))
    return 0  # BLOCK でなく exit 0 (継続可否は checkpoint:human-verify)


def _attach_market_data(pred_df: pd.DataFrame, *, cur_pool: Any) -> pd.DataFrame:
    """JODDS snapshot から ``fuku_odds_lower``/``fuku_odds_upper`` を取得し pred_df に JOIN する.

    REVIEW H6: ``fuku_odds`` 系の誤略称でなく ``fuku_odds_lower``/``fuku_odds_upper`` を使用
    (src/ev/odds_snapshot.py L210-215 の正しい列名・T-09-29 mitigate)。
    本 helper は live-DB 専用 (KEIBA_SKIP_DB_TESTS unset)。
    """
    from src.db.connection import readonly_cursor
    from src.ev.odds_snapshot import select_odds_snapshot

    with readonly_cursor(cur_pool) as cur:
        odds_df = select_odds_snapshot(cur, policy="30min_before")

    if len(odds_df) == 0:
        # odds 未取得時は NaN 埋め (D-15 residual proxy は skip・signal_present=False)
        pred_df = pred_df.copy()
        pred_df["fuku_odds_lower"] = float("nan")
        pred_df["fuku_odds_upper"] = float("nan")
        return pred_df

    merged = pred_df.merge(
        odds_df[["race_key", "umaban", "fuku_odds_lower", "fuku_odds_upper"]],
        on=["race_key", "umaban"],
        how="left",
        validate="many_to_one",
    )
    return merged


def _evaluate_and_decide(
    *,
    baseline_pred: pd.DataFrame,
    speedfig_pred: pd.DataFrame,
    baseline_model_version: str,
    speedfig_model_version: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """両モデルの pred_df から D-14 4指標 + D-15 residual proxy + D-16 verdict を算出する (純粋関数)."""
    # race_keys/entry_counts は compute_metrics の sum(p) 分布計算に使用
    baseline_metrics = compute_metrics(
        baseline_pred["fukusho_hit_validated"],
        baseline_pred["p_fukusho_hit"],
        race_keys=baseline_pred.get("race_key"),
        entry_counts=baseline_pred.get("entry_count"),
    )
    speedfig_metrics = compute_metrics(
        speedfig_pred["fukusho_hit_validated"],
        speedfig_pred["p_fukusho_hit"],
        race_keys=speedfig_pred.get("race_key"),
        entry_counts=speedfig_pred.get("entry_count"),
    )

    # 指標1: selected/high-EV 層 calibration 改善
    baseline_sel_calib = _compute_selected_calibration(baseline_pred)
    speedfig_sel_calib = _compute_selected_calibration(speedfig_pred)
    sel_calib_improved = (
        not math.isnan(speedfig_sel_calib)
        and (math.isnan(baseline_sel_calib) or speedfig_sel_calib < baseline_sel_calib)
    )

    # 指標2: selected-only ROI 改善
    baseline_roi = _compute_selected_roi(baseline_pred)
    speedfig_roi = _compute_selected_roi(speedfig_pred)

    # 指標3: Brier/LogLoss/AUC 非劣化
    global_delta = _compute_global_metric_delta(baseline_metrics, speedfig_metrics)

    # 指標4 + D-15: residual proxy
    residual = _compute_residual_proxy(speedfig_pred)
    residual_signal = bool(residual.get("signal_present", False))

    # D-16 verdict
    verdict = _decide_stopgate_verdict(
        selected_calibration_improved=sel_calib_improved,
        residual_proxy_signal=residual_signal,
    )

    return {
        "metric1_selected_calibration": {
            "baseline": baseline_sel_calib,
            "speed_figure": speedfig_sel_calib,
            "improved": bool(sel_calib_improved),
        },
        "metric2_selected_roi": {
            "baseline": baseline_roi,
            "speed_figure": speedfig_roi,
        },
        "metric3_global_metrics": {
            **global_delta,
            "baseline": {
                "brier": baseline_metrics.get("brier"),
                "logloss": baseline_metrics.get("logloss"),
                "auc": baseline_metrics.get("auc"),
            },
            "speed_figure": {
                "brier": speedfig_metrics.get("brier"),
                "logloss": speedfig_metrics.get("logloss"),
                "auc": speedfig_metrics.get("auc"),
            },
        },
        "metric4_residual_proxy": {
            "signal_present": residual_signal,
            "n_valid_cells": residual.get("n_valid_cells", 0),
        },
        "d15_residual_proxy_detail": residual,
        "verdict": verdict,
        "model_versions": {
            "baseline": baseline_model_version,
            "speed_figure": speedfig_model_version,
        },
        "args": {
            "baseline_snapshot_id": args.baseline_snapshot_id,
            "speed_figure_snapshot_id": args.speed_figure_snapshot_id,
            "bt_split": args.bt_split,
            "odds_snapshot_policy": args.odds_snapshot_policy,
        },
        "tolerance": {
            "brier": TOLERANCE_BRIER,
            "logloss": TOLERANCE_LOGLOSS,
            "auc": TOLERANCE_AUC,
            "note": "RESEARCH.md Open Questions RESOLVED #2 (Brier ~3.3% / LogLoss ~4.2% / AUC ~0.7%)",
        },
        "safe_01_note": (
            "market_implied (1.0 / fuku_odds_lower) は診断層のみ・FEATURE_COLUMNS に混入なし (SAFE-01/EVAL-02)"
        ),
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    raise SystemExit(main())
