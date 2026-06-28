# ruff: noqa: E501
"""ステップ2 手順3b: Phase 4 標準窓 (test 2024下期) で A1 と postreview-v2 の回収率を直接比較.

ユーザー指示 (PLAN 手順3b): 切替後の実運用数値として・Phase 4 標準 test 窓 (2024-07..12) で
A1 (speedfig FEATURE) と postreview-v2 (v1.0 FEATURE) を **同じ label v1.1.0 universe** で評価し・
A1 が postreview-v2 を上回るか (交代の正当性) を確認する。

BT-1..5 (Spike 001 一致検証) とは別系統。本番デプロイ運用 (UI が WHERE is_primary=true で SELECT)
と同じ test 窓スコープ (Phase 4 標準・postreview-v2 現行と同一構造)。

chain (run_ablation.run_snap_swap と同一・ただし Phase 4 標準 BTWindow):
  - BTWindow(name="phase4-2024H2", train 2016-07..2024-06→carve で train+calib, test 2024-07..12)
  - _carve_calib_from_train_tail → Phase 4 標準 periods (= split_3way デフォルトと一致)
  - train_and_predict(model_type="lightgbm", snapshot_id=<各snap>, split_periods=phase4_periods,
    category_map=None, label_version="v1.1.0") → label v1.1.0 統一
  - _run_main_model_backtest(phase4_bt, ...) → 回収率

聖域: odds-free(SAFE-01) / PIT-correct / byte-reproducible / no_write_db (DB 変更無し).
※ A1 は手順1で DB 保存済み・本スクリプトは評価のみ (no_write_db). postreview-v2 は label v1.1.0 で
再評価 (FEATURE_COLUMNS は snapshot_id で選択・postreview-v2 は v1.0 デフォルト想定・A0 相当).

Usage::

    uv run python scripts/compare_phase4_window.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import run_ablation as ra  # noqa: E402  _prepare_feature_df / _fetch_live_db / _metrics_from_pred_df / _configure_statement_timeout
import run_backtest as rb  # noqa: E402  _carve_calib_from_train_tail / _run_main_model_backtest

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool  # noqa: E402
from src.model.orchestrator import FIXED_REPRODUCE_TS, train_and_predict  # noqa: E402
from src.utils.group_split import BTWindow  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("compare_phase4_window")

POLICY = "30min_before"
LABEL_VERSION = "v1.1.0"

# Phase 4 標準窓 (= split_3way デフォルトと一致・postreview-v2 現行デプロイと同一 test 窓構造)
# train_end=2024-06-30 → _carve_calib_from_train_tail が calib=2024-01..06, train=2016-07..2023-12 を生成
PHASE4_BT = BTWindow(
    name="phase4-2024H2",
    train_start="2016-07-01",
    train_end="2024-06-30",
    test_start="2024-07-01",
    test_end="2024-12-31",
    window_type="expanding",
)

# (snapshot_id, 表示label, FEATURE 構成)
COMPARISONS = [
    ("20260625-1a-speedfigure-v1", "A1 (speedfig 6)", "speed figure 基本6"),
    ("20260620-1a-postreview-v2", "postreview-v2 (v1.0)", "v1.0 デフォルト (speed fig 無し)"),
]


def main() -> int:
    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("Phase 4 標準窓: %s (train+calib carved / test 2024-07..12)", PHASE4_BT.name)

    readonly_pool = make_pool(settings, role="readonly", configure=ra._configure_statement_timeout)
    try:
        periods = rb._carve_calib_from_train_tail(PHASE4_BT)
        logger.info(
            "periods: train=%s..%s calib=%s..%s test=%s..%s (= split_3way デフォルト)",
            periods["train"][0], periods["train"][1], periods["calib"][0], periods["calib"][1],
            periods["test"][0], periods["test"][1],
        )
        jodds_df, label_df, harai_race_df = ra._fetch_live_db(readonly_pool, periods)

        results = {}
        for snapshot_id, label, feature_desc in COMPARISONS:
            logger.info("=== %s (snapshot=%s FEATURE=%s) ===", label, snapshot_id, feature_desc)
            feature_df = ra._prepare_feature_df(snapshot_id, readonly_pool)
            result = train_and_predict(
                feature_df,
                model_type="lightgbm",
                feature_snapshot_id=snapshot_id,
                snapshot_id=snapshot_id,  # H1-b: FEATURE_COLUMNS 選択
                version_n=1,
                seed=42,
                as_of_datetime=FIXED_REPRODUCE_TS,
                split_periods=periods,  # Phase 4 標準
                category_map=None,  # Phase 4 標準 (feature snapshot _code 列使用)
                label_version=LABEL_VERSION,
                odds_snapshot_policy=POLICY,
                backtest_strategy_version="fukusho_ev_v1",
            )
            pred_df = result["pred_df"]
            model_version = result["model_version"]
            row = rb._run_main_model_backtest(
                PHASE4_BT,
                POLICY,
                "lightgbm",
                pred_df=pred_df,
                jodds_df=jodds_df,
                label_df=label_df,
                harai_race_df=harai_race_df,
                feature_snapshot_id=snapshot_id,
                model_version=model_version,
                periods=periods,
                write_cur=None,
                no_write_db=True,
            )
            entry = {
                "label": label,
                "snapshot_id": snapshot_id,
                "feature": feature_desc,
                "model_version": model_version,
                "recovery_rate": float(row.get("recovery_rate", 0.0)),
                "n_selected": int(row.get("selected", 0)),
                "hit_rate": float(row.get("hit_rate", 0.0)),
                "profit_loss": int(row.get("P/L", 0)),
                "_full_candidate_rows": int(row.get("_full_candidate_rows", 0)),
                "pred_rows": len(pred_df),
            }
            results[label] = entry
            logger.info(
                "%s: recovery_rate=%.6f selected=%d hit_rate=%.4f P/L=%d pred_rows=%d",
                label, entry["recovery_rate"], entry["n_selected"], entry["hit_rate"],
                entry["profit_loss"], entry["pred_rows"],
            )

        # 比較出力
        a1 = results["A1 (speedfig 6)"]
        pr = results["postreview-v2 (v1.0)"]
        logger.info("=" * 70)
        logger.info("=== Phase 4 標準窓 (test 2024下期) A1 vs postreview-v2 比較 ===")
        logger.info("  A1            recovery_rate=%.6f (selected=%d P/L=%d)", a1["recovery_rate"], a1["n_selected"], a1["profit_loss"])
        logger.info("  postreview-v2 recovery_rate=%.6f (selected=%d P/L=%d)", pr["recovery_rate"], pr["n_selected"], pr["profit_loss"])
        diff = a1["recovery_rate"] - pr["recovery_rate"]
        verdict = "A1 が上回る (交代正当)" if diff > 0 else "postreview-v2 が上回る (要精査)"
        logger.info("  差 (A1 - postreview-v2) = %+.6f → %s", diff, verdict)
        logger.info("  ※ label v1.1.0 統一・FEATURE 差 (speed fig 有無) の効果")
        logger.info("=" * 70)

        out_path = _REPO_ROOT / "reports/12-evaluation/phase4-window-a1-vs-postreview-v2.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"window": "phase4-2024H2", "periods": periods, "label_version": LABEL_VERSION,
                        "comparisons": results, "diff_a1_minus_postreview": diff}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("wrote %s", out_path)
        return 0
    finally:
        readonly_pool.close()


if __name__ == "__main__":
    sys.exit(main())
