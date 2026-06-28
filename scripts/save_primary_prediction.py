# ruff: noqa: E501
"""ステップ2 手順1: A1 (speedfigure-v1) 予測を Phase 4 標準 chain で生成し保存する.

``run_train_predict.py`` は ``data.py`` の ``SNAPSHOT_PATH`` 固定 (postreview-v2) で A1 を扱えない
(``_assert_snapshot_id_matches_data_module`` L174-193 が ``sys.exit(1)``・かつ
``_prepare_feature_df`` が ``load_feature_matrix()`` 引数なしで postreview-v2 を読む)。
そのため ``run_ablation.py`` と同一 chain (``load_feature_matrix(snapshot_id)`` 明示 +
``train_and_predict`` + ``load_predictions``) で A1 を **Phase 4 標準 split** で保存する。
生産スクリプト (orchestrator / run_train_predict) は一切変更しない (core value 聖域)。

聖域 (core value):
  - **odds-free (SAFE-01)**: speed figure は走破タイム由来・オッズ不使用。
  - **PIT-correct**: feature_cutoff_datetime = race_date-1day・過去走のみ。
  - **byte-reproducible**: seed=42・thread=1・FIXED_REPRODUCE_TS=2026-06-20 00:00 UTC。
  - **H1-b (FEATURE_COLUMNS 選択)**: ``snapshot_id=A1`` を明示渡す (speed figure 6・v1.0
    デフォルト FEATURE_COLUMNS 誤使用を構造的に防止・P05 stop gate も検出不能な失敗を閉塞)。
  - **label v1.1.0** (commit 2cdbac1・newcomer '12' 誤除外修正後・eligible 42214)。

chain (run_ablation.run_snap_swap と同一・ただし split_periods/category_map を Phase 4 標準):
  1. ``load_feature_matrix("20260625-1a-speedfigure-v1")`` + ``load_labels`` + ``build_training_frame``
  2. ``train_and_predict(model_type="lightgbm", feature_snapshot_id=A1, snapshot_id=A1,
     version_n=1, seed=42, as_of_datetime=FIXED_REPRODUCE_TS,
     label_version="v1.1.0", odds_snapshot_policy="30min_before",
     backtest_strategy_version="fukusho_ev_v1")``
     - ``split_periods=None`` (Phase 4 標準: train 2016-07..2023-12 / calib 2024-01..06 /
       test 2024-07..12・postreview-v2 現 is_primary と同一 test 窓スコープ構造)
     - ``category_map=None`` (feature snapshot 構築済み _code 列使用・Phase 4 等価)
  3. ``load_predictions`` ×2 → checksum bit-identical 検証 (idempotent・D-05 staging-swap)

Usage::

    uv run python scripts/save_primary_prediction.py \\
        --snapshot-id 20260625-1a-speedfigure-v1
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor, write_cursor  # noqa: E402
from src.db.prediction_load import load_predictions  # noqa: E402
from src.model.data import (  # noqa: E402
    SNAPSHOT_PATH,
    build_training_frame,
    load_feature_matrix,
    load_labels,
)
from src.model.orchestrator import FIXED_REPRODUCE_TS, train_and_predict  # noqa: E402
from src.model.predict import make_model_version  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("save_primary_prediction")

# Phase 12 統一政策 (run_ablation.POLICY / run_phase12 と同一)
ODDS_POLICY = "30min_before"
LABEL_VERSION = "v1.1.0"
BACKTEST_STRATEGY_VERSION = "fukusho_ev_v1"


def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
    """etl/readonly pool 全 connection に SET statement_timeout='30s' (memory: subagent-db-query-statement-timeout).

    重いクエリの孤立実行 (CPU 張り付き) を防止する。run_ablation._configure_statement_timeout と同一 idiom。
    """
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A1 予測を Phase 4 標準 chain で生成し prediction.fukusho_prediction に保存 (ステップ2 手順1)",
    )
    parser.add_argument(
        "--snapshot-id",
        default="20260625-1a-speedfigure-v1",
        help="feature snapshot id (default: A1=20260625-1a-speedfigure-v1)",
    )
    parser.add_argument(
        "--model-type",
        default="lightgbm",
        choices=["lightgbm"],
        help="model type (本スクリプトは LightGBM binary のみ・A1 正解)",
    )
    parser.add_argument(
        "--version-n",
        type=int,
        default=1,
        help="model version number (D-10, default: 1)",
    )
    parser.add_argument(
        "--no-write-db",
        action="store_true",
        help="prediction 書込を skip (予測生成のみの dry run)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot_id = args.snapshot_id
    settings = Settings()

    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)
    logger.info(
        "config: snapshot_id=%s model_type=%s version_n=%d as_of=%s write_db=%s "
        "(data.py SNAPSHOT_PATH=%s ・本スクリプトは引数明示で A1 を読む)",
        snapshot_id,
        args.model_type,
        args.version_n,
        FIXED_REPRODUCE_TS.isoformat(),
        not args.no_write_db,
        SNAPSHOT_PATH,
    )

    expected_model_version = make_model_version(snapshot_id, args.model_type, args.version_n)
    logger.info("expected model_version (make_model_version): %s", expected_model_version)

    readonly_pool = make_pool(settings, role="readonly", configure=_configure_statement_timeout)
    etl_pool = None if args.no_write_db else make_pool(settings, role="etl", configure=_configure_statement_timeout)

    try:
        # --- Step 1: feature_df 構築 (label v1.1.0 join 済み・load_feature_matrix(snapshot_id) 明示) ---
        feature_df_raw = load_feature_matrix(snapshot_id)  # H1-b: 引数明示で A1 Parquet を読む
        with readonly_cursor(readonly_pool) as cur:
            label_df = load_labels(cur)  # 現在の label = v1.1.0 (commit 2cdbac1 後)
        feature_df = build_training_frame(feature_df_raw, label_df)
        if "fukusho_hit_validated" not in feature_df.columns:
            raise RuntimeError(
                "feature_df に fukusho_hit_validated 列がない (build_training_frame の label join 失敗)"
            )
        logger.info(
            "feature_df prepared: snapshot=%s rows=%d cols=%d (label v1.1.0 joined)",
            snapshot_id,
            len(feature_df),
            feature_df.shape[1],
        )

        # --- Step 2: train_and_predict (Phase 4 標準 chain・run_train_predict 等価・A1 向け) ---
        # split_periods=None → Phase 4 ハードコード区間 (test 2024-07..12・postreview-v2 と同一 test 窓)
        # category_map=None  → feature snapshot 構築済み _code 列使用 (Phase 4 等価・A5)
        # snapshot_id=A1     → FEATURE_COLUMNS 選択 (H1-b・speed figure 6・v1.0 誤使用防止・必須)
        result = train_and_predict(
            feature_df,
            model_type=args.model_type,
            feature_snapshot_id=snapshot_id,
            snapshot_id=snapshot_id,  # H1-b: FEATURE_COLUMNS 選択用 (feature_snapshot_id とは別)
            version_n=args.version_n,
            seed=42,
            as_of_datetime=FIXED_REPRODUCE_TS,
            label_version=LABEL_VERSION,
            odds_snapshot_policy=ODDS_POLICY,
            backtest_strategy_version=BACKTEST_STRATEGY_VERSION,
        )
        pred_df = result["pred_df"]
        model_version = result["model_version"]
        calib_method = result["calib_method"]

        # model_version 形式検証 (make_model_version と一致・provenance 整合)
        if model_version != expected_model_version:
            logger.error(
                "model_version 不一致: train_and_predict=%r expected(make_model_version)=%r",
                model_version,
                expected_model_version,
            )
            return 2
        logger.info(
            "train_and_predict 完了: model_type=%s model_version=%s calib_method=%s pred_rows=%d "
            "as_of=%s (Phase 4 標準 test 2024下期・label v1.1.0・byte-reproducible)",
            args.model_type,
            model_version,
            calib_method,
            len(pred_df),
            FIXED_REPRODUCE_TS.isoformat(),
        )

        # --- Step 3: prediction 書込 + idempotent 検証 (load_predictions ×2・D-05) ---
        if etl_pool is None:
            logger.info("--no-write-db 指定のため DB 書込を skip して終了 (pred_rows=%d)", len(pred_df))
            return 0

        checksum1: str
        with write_cursor(etl_pool) as write_cur:
            checksum1 = load_predictions(write_cur, pred_df, reader_role=settings.db_reader_role)
        logger.info(
            "prediction loaded #1: model_version=%s rows=%d checksum=%s",
            model_version,
            len(pred_df),
            checksum1,
        )

        # idempotent verify: 2回目実行で checksum bit-identical (staging-swap idempotent load・review HIGH#1)
        checksum2: str
        with write_cursor(etl_pool) as write_cur:
            checksum2 = load_predictions(write_cur, pred_df, reader_role=settings.db_reader_role)
        if checksum1 != checksum2:
            logger.error(
                "idempotent checksum 違反: model_version=%s c1=%s c2=%s "
                "(staging-swap idempotent load 違反・review HIGH#1)",
                model_version,
                checksum1,
                checksum2,
            )
            return 3
        logger.info(
            "prediction idempotent verify PASS: model_version=%s checksum=%s (2回実行で bit-identical)",
            model_version,
            checksum1,
        )
        logger.info(
            "SUMMARY: model_version=%s snapshot_id=%s as_of=%s pred_rows=%d checksum=%s "
            "label_version=%s odds_policy=%s (is_primary=False で保存・手順2 で True 化)",
            model_version,
            snapshot_id,
            FIXED_REPRODUCE_TS.isoformat(),
            len(pred_df),
            checksum1,
            LABEL_VERSION,
            ODDS_POLICY,
        )
        return 0
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 4
    finally:
        readonly_pool.close()
        if etl_pool is not None:
            etl_pool.close()


if __name__ == "__main__":
    sys.exit(main())
