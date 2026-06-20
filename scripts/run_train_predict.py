# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)
"""Phase 4 エントリポイント: 両モデル学習 → キャリブレーション → 予測 → 書込 → 評価.

D-01 (snapshot 確定) / D-03 (両モデル候補) / D-05 (prediction DB 永続化) /
D-06 (artifact ネイティブ形式) / SC#2 (BL 比較表) / SC#4 (bit-identical 再現性) /
review HIGH#1 (model_version スコープ swap) / review HIGH#2 (行整列保証) /
review HIGH#4 (model_version D-10 形式) / review HIGH#5 (base+calibrator 分離保存) /
review HIGH#7 (固定 thread/as_of_datetime で bit-identical) /
review HIGH#12 (orchestrator は orchestrator.py) /
Cycle 2 residual #13 (label join は run script 側でのみ発生・orchestrator は label-joined
frame のみを受け取る) を実装する Phase 4 のエントリポイント。

起動フロー (run_label_etl.py / run_feature_build.py と同一構造・masked DSN・try/finally):

  1. ``Settings`` から ``dsn_masked`` / ``etl_dsn_masked`` をログ出力 (生 DSN 絶対禁止)
  2. ``--snapshot-id`` を実パス (Parquet / manifest / category_map) に解決し存在確認
     (review MEDIUM: 単なる provenance 文字列でなく実パス選択)
  3. ``args.snapshot_id`` と ``data.py.SNAPSHOT_PATH`` の snapshot_id 部分が一致することを assert
     (ドリフト検出)
  4. readonly pool + etl pool 構築
  5. ``load_feature_matrix()`` (Parquet のみ) + ``load_labels(readonly_cur)`` +
     ``build_training_frame`` で label join を完結 (Cycle 2 residual #13: orchestrator に渡す前に
     label join を完了)
  6. 両モデル (model_type in {lightgbm, catboost}) で ``train_and_predict`` を呼出し
     (review HIGH#2: orchestrator が行整列保証・review HIGH#12: orchestrator.py 配置)
  7. ``save_native_artifact`` で base+calibrator 分離保存 (review HIGH#5)
  8. ``compute_all_baselines`` で BL-1..5 計算 (SC#2)
  9. ``load_predictions`` を各 model_type+model_version 単位で呼び prediction.fukusho_prediction に
     永続化 (review HIGH#1: 統合 DataFrame でなく各モデル別・model_version スコープ swap)
 10. ``evaluate_all_models`` で reports/04-eval.md + reports/04-eval.json に出力 (SC#2)
 11. ``--check-reproduce`` の場合・orchestrator._assert_deterministic で SC#4 bit-identical 検証
 12. try/except PsycopgError / finally pool.close (run_label_etl.py パターン)
 13. idempotent verify: 各 model_type の load_predictions をもう1回実行し checksum 報告

Usage::

    uv run python scripts/run_train_predict.py \\
        --snapshot-id 20260620-1a-postreview-v2 \\
        --model-type both \\
        --version-n 1

    # SC#4 reproduce smoke (bit-identical 検証のみ・DB 書込 skip)
    uv run python scripts/run_train_predict.py --check-reproduce --no-write-db
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor, write_cursor  # noqa: E402
from src.db.prediction_load import load_predictions  # noqa: E402
from src.model.artifact import save_native_artifact  # noqa: E402
from src.model.baseline import compute_all_baselines, fetch_market_data  # noqa: E402
from src.model.data import (  # noqa: E402
    SNAPSHOT_PATH,
    build_training_frame,
    load_feature_matrix,
    load_labels,
    make_X_y,
)
from src.model.evaluator import evaluate_all_models  # noqa: E402
from src.model.orchestrator import (  # noqa: E402
    FIXED_REPRODUCE_TS,
    _assert_deterministic,
    train_and_predict,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_train_predict")


# ---------------------------------------------------------------------------
# parse_args — review MEDIUM: --snapshot-id は実パス解決
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する。

    review MEDIUM: ``--snapshot-id`` は実パス (Parquet / manifest / category_map) に解決される
    (単なる provenance 文字列でなく実パス選択)。``args.snapshot_id`` と ``data.py.SNAPSHOT_PATH``
    の snapshot_id 部分が一致することを ``main`` で assert する (ドリフト検出)。
    """
    parser = argparse.ArgumentParser(
        description=(
            "Phase 4 entry point: train both models -> calibrate -> predict -> "
            "load -> evaluate (D-01/D-03/D-05/D-06/SC#2/SC#4)"
        ),
    )
    parser.add_argument(
        "--snapshot-id",
        default="20260620-1a-postreview-v2",
        help="feature snapshot identifier (D-01, default: 20260620-1a-postreview-v2)",
    )
    parser.add_argument(
        "--model-type",
        choices=["lightgbm", "catboost", "both"],
        default="both",
        help="model type to train (D-03: both models, default: both)",
    )
    parser.add_argument(
        "--version-n",
        type=int,
        default=1,
        help="model version number (D-10, default: 1)",
    )
    parser.add_argument(
        "--check-reproduce",
        action="store_true",
        help="run SC#4 reproduce smoke (seed=42, two runs, np.array_equal bit-identical)",
    )
    parser.add_argument(
        "--no-write-db",
        action="store_true",
        help="skip prediction.fukusho_prediction write (dry run)",
    )
    parser.add_argument(
        "--as-of-datetime",
        default=None,
        help=(
            "fixed as_of_datetime for prediction provenance (ISO8601). 指定無し場合は "
            "now(UTC)・reproduce smoke では固定必須 (review HIGH#7 / T-04-25b)"
        ),
    )
    return parser.parse_args(argv)


def _resolve_snapshot_paths(snapshot_id: str) -> dict[str, Path]:
    """``--snapshot-id`` を実パス (Parquet / manifest / category_map) に解決し存在確認する
    (review MEDIUM: 単なる provenance 文字列でなく実パス選択)。

    Returns
    -------
    dict
        ``{"parquet": Path, "manifest": Path, "category_map": Path}``。

    Raises
    ------
    FileNotFoundError
        いずれかのパスが存在しない時 (T-04-26: CLI 引数 injection で不正パス読込防止)。
    """
    paths = {
        "parquet": _REPO_ROOT / f"snapshots/feature_matrix_{snapshot_id}.parquet",
        "manifest": _REPO_ROOT / f"snapshots/feature_matrix_{snapshot_id}.manifest.yaml",
        "category_map": _REPO_ROOT / f"snapshots/category_map_{snapshot_id}.json",
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"--snapshot-id {snapshot_id!r} に対応するファイルが存在しない "
            "(review MEDIUM: 実パス解決・T-04-26 CLI injection 防止): "
            f"missing={missing}"
        )
    return paths


def _assert_snapshot_id_matches_data_module(snapshot_id: str) -> None:
    """``args.snapshot_id`` と ``data.py.SNAPSHOT_PATH`` の snapshot_id 部分が一致することを
    assert する (ドリフト検出・T-04-26)。

    ``data.py.SNAPSHOT_PATH`` は ``snapshots/feature_matrix_{id}.parquet`` 形式の固定定数。
    ``args.snapshot_id`` がこれと一致しない場合は ``data.load_feature_matrix()`` が別 snapshot を
    読むことになり・provenance 不整合を生むため ``sys.exit(1)`` する。
    """
    # SNAPSHOT_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.parquet"
    # から snapshot_id 部分を抽出
    sp = Path(SNAPSHOT_PATH).stem  # "feature_matrix_20260620-1a-postreview-v2"
    data_snapshot_id = sp.replace("feature_matrix_", "", 1)
    if data_snapshot_id != snapshot_id:
        logger.error(
            "snapshot_id ドリフト検出: args.snapshot_id=%r data.py.SNAPSHOT_PATH 由来=%r "
            "(data.load_feature_matrix() が別 snapshot を読む・provenance 不整合・T-04-26)",
            snapshot_id,
            data_snapshot_id,
        )
        sys.exit(1)


def _parse_as_of_datetime(s: str | None) -> datetime:
    """``--as-of-datetime`` 文字列を datetime に parse する。``None`` の場合は now(UTC)。"""
    if s is None:
        return datetime.now(UTC)
    # ISO8601 を parse (末尾 Z は UTC)
    cleaned = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _model_types_to_run(model_type: str) -> list[str]:
    """``--model-type`` を実際に学習する model_type の list に変換する。"""
    if model_type == "both":
        return ["lightgbm", "catboost"]
    return [model_type]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """両モデル pipeline を実行し prediction / artifact / 評価レポートを生成する。

    SC#4 ``--check-reproduce`` の場合は bit-identical 検証のみ実施し (DB 書込は
    ``--no-write-db`` で skip 可能)・失敗時 ``sys.exit(1)`` (§19.1 構造的ブロック)。
    """
    args = parse_args(argv)
    settings = Settings()

    # T-04-27 / Shared Pattern 8: 生 DSN は絶対に出力しない (masked のみ)
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)

    # review MEDIUM: --snapshot-id 実パス解決 + ドリフト検出
    snapshot_paths = _resolve_snapshot_paths(args.snapshot_id)
    _assert_snapshot_id_matches_data_module(args.snapshot_id)
    logger.info(
        "snapshot resolved: id=%s parquet=%s manifest=%s category_map=%s",
        args.snapshot_id,
        snapshot_paths["parquet"],
        snapshot_paths["manifest"],
        snapshot_paths["category_map"],
    )

    as_of_dt = _parse_as_of_datetime(args.as_of_datetime)
    model_types = _model_types_to_run(args.model_type)
    logger.info(
        "config: model_types=%s version_n=%d as_of_datetime=%s check_reproduce=%s write_db=%s",
        model_types,
        args.version_n,
        as_of_dt.isoformat(),
        args.check_reproduce,
        not args.no_write_db,
    )

    readonly_pool = make_pool(settings, role="readonly")
    etl_pool = None if args.no_write_db else make_pool(settings, role="etl")

    try:
        # --- SC#4 --check-reproduce: bit-identical 検証のみ (DB 書込 skip 可能) ---
        if args.check_reproduce:
            logger.info("SC#4 reproduce smoke: 開始 (両モデル bit-identical 検証)")
            # reproduce 用の feature_df を構築 (label join 済み)
            feature_df_repro = _prepare_feature_df(readonly_pool)
            for mt in model_types:
                _assert_deterministic(
                    mt,
                    feature_df_repro,
                    feature_snapshot_id=args.snapshot_id,
                    version_n=args.version_n,
                    seed=42,
                    as_of_datetime=FIXED_REPRODUCE_TS,
                )
                logger.info(
                    "SC#4 reproduce smoke PASS (%s): seed=42 + 固定 thread + 固定 as_of_datetime "
                    "で bit-identical (review HIGH#7 / §19.1)",
                    mt,
                )
            logger.info("SC#4 reproduce smoke: 全モデル PASS")
            if args.no_write_db:
                logger.info("--no-write-db 指定のため DB 書込を skip して終了")
                return 0
            # --no-write-db で無い場合は通常 pipeline も継続実行

        # --- Step 1: feature_df 構築 (label join は run script 側で完結・Cycle 2 residual #13) ---
        feature_df = _prepare_feature_df(readonly_pool)
        # feature_df を train_and_predict に渡す前に fukusho_target 列が存在することを assert
        # (run script 側の境界 guard・orchestrator 側の assert と二重防御)
        if "fukusho_hit_validated" not in feature_df.columns:
            raise RuntimeError(
                "run_train_predict: feature_df に fukusho_hit_validated 列がない "
                "(build_training_frame が label join に失敗・Cycle 2 residual #13)"
            )
        logger.info(
            "feature_df prepared: rows=%d cols=%d (label-joined)",
            len(feature_df),
            feature_df.shape[1],
        )

        # --- Step 2: 両モデル学習 (review HIGH#2: orchestrator が行整列保証) ---
        results_by_model: dict[str, dict] = {}
        for mt in model_types:
            logger.info("train_and_predict 開始: model_type=%s", mt)
            result = train_and_predict(
                feature_df,
                model_type=mt,
                feature_snapshot_id=args.snapshot_id,
                version_n=args.version_n,
                seed=42,
                as_of_datetime=as_of_dt,
            )
            results_by_model[mt] = result
            logger.info(
                "train_and_predict 完了: model_type=%s model_version=%s calib_method=%s "
                "pred_rows=%d",
                mt,
                result["model_version"],
                result["calib_method"],
                len(result["pred_df"]),
            )

        # --- Step 3: artifact 保存 (review HIGH#5: base+calibrator 分離) ---
        for mt, result in results_by_model.items():
            # base_model_type は save_native_artifact の期待値 (lightgbm/catboost)
            out_dir = save_native_artifact(
                result["calibrated"],
                base_model_type=mt,
                model_version=result["model_version"],
                feature_snapshot_id=args.snapshot_id,
                hyperparams={},  # trainer の LGB/CB_INIT_PARAMS が固定済み・provenance は metadata.json
                seed=42,
                train_calib_test_periods={
                    "train": "2016-07-01/2023-12-31",
                    "calib": "2024-01-01/2024-06-30",
                    "test": "2024-07-01/2024-12-31",
                },
                calib_method=result["calib_method"],
            )
            logger.info(
                "artifact saved: model_type=%s out_dir=%s (base+calibrator 分離・review HIGH#5)",
                mt,
                out_dir,
            )

        # --- Step 4: BL 計算 (SC#2・市場データは readonly SELECT) ---
        baseline_df = _compute_baselines(readonly_pool, feature_df, results_by_model)
        logger.info(
            "baselines computed: rows=%d cols=%d",
            len(baseline_df),
            baseline_df.shape[1],
        )

        # --- Step 5: prediction 書込 (review HIGH#1: 各 model_type+model_version 単位で呼ぶ) ---
        checksums: dict[str, str] = {}
        if etl_pool is not None:
            for mt, result in results_by_model.items():
                pred_df = result["pred_df"]
                with write_cursor(etl_pool) as write_cur:
                    checksum1 = load_predictions(
                        write_cur,
                        pred_df,
                        reader_role=settings.db_reader_role,
                    )
                logger.info(
                    "prediction loaded #1: model_type=%s rows=%d checksum=%s",
                    mt,
                    len(pred_df),
                    checksum1,
                )
                # idempotent verify: 2回目実行で checksum bit-identical (run_label_etl.py パターン)
                with write_cursor(etl_pool) as write_cur:
                    checksum2 = load_predictions(
                        write_cur,
                        pred_df,
                        reader_role=settings.db_reader_role,
                    )
                if checksum1 != checksum2:
                    logger.error(
                        "idempotent checksum 違反: model_type=%s c1=%s c2=%s "
                        "(staging-swap idempotent load 違反・review HIGH#1)",
                        mt,
                        checksum1,
                        checksum2,
                    )
                    return 3
                checksums[mt] = checksum1
                logger.info(
                    "prediction idempotent verify PASS: model_type=%s checksum=%s",
                    mt,
                    checksum1,
                )

        # --- Step 6: 評価レポート (SC#2・reports/04-eval.md + .json) ---
        _write_eval_report(results_by_model, baseline_df, feature_df)
        logger.info("eval report written: reports/04-eval.md + reports/04-eval.json (SC#2)")

        # --- 終了サマリ ---
        for mt, result in results_by_model.items():
            logger.info(
                "SUMMARY model_type=%s: model_version=%s calib_method=%s pred_rows=%d checksum=%s",
                mt,
                result["model_version"],
                result["calib_method"],
                len(result["pred_df"]),
                checksums.get(mt, "(skip --no-write-db)"),
            )
        return 0
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        readonly_pool.close()
        if etl_pool is not None:
            etl_pool.close()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _prepare_feature_df(readonly_pool) -> pd.DataFrame:  # type: ignore[name-defined]
    """``load_feature_matrix`` + ``load_labels`` + ``build_training_frame`` で label-joined
    feature_df を構築する (Cycle 2 residual #13: label join は run script 側でのみ発生)。

    orchestrator (``train_and_predict``) は label-joined frame のみを受け取り・label join を
    再実行しない (docstring + assert で契約明示)。
    """
    import pandas as pd  # noqa: F401  (type hint 用)

    feature_df_raw = load_feature_matrix()  # Parquet のみ・SC#1 聖域
    with readonly_cursor(readonly_pool) as cur:
        label_df = load_labels(cur)
    feature_df = build_training_frame(feature_df_raw, label_df)
    return feature_df


def _compute_baselines(
    readonly_pool,
    feature_df: pd.DataFrame,  # type: ignore[name-defined]
    results_by_model: dict[str, dict],
) -> pd.DataFrame:  # type: ignore[name-defined]
    """BL-1..5 を計算する (SC#2・市場データは readonly SELECT・feature matrix には混入しない)。

    ``compute_all_baselines`` に test split の feature/label を渡す。BL-2/BL-3 の市場データ
    (ninki / fukuoddslow) は ``fetch_market_data`` で別途取得し test split の df に結合する
    (D-07: 市場データは BL 計算専用・主モデル feature には混入しない)。
    """
    import pandas as pd  # noqa: F401

    # test split を再取得 (orchestrator と同一の split_3way で分離)
    from src.model.data import split_3way

    splits = split_3way(feature_df)
    test_df = splits["test"]
    train_df = splits["train"]
    calib_df = splits["calib"]

    X_train, y_train = make_X_y(train_df)
    X_test, y_test = make_X_y(test_df)
    X_calib, y_calib = make_X_y(calib_df)

    # BL-2/BL-3 用の市場データを test split に結合 (ninki / fukuoddslow)
    # PK で left join・市場データが無い行は NaN (compute_bl2/bl3 が除外)
    with readonly_cursor(readonly_pool) as cur:
        market_df = fetch_market_data(cur, year=2024)
    # PK 7カラムで型整列してから merge
    merge_keys = ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"]
    for k in merge_keys:
        if k in test_df.columns:
            test_df[k] = test_df[k].astype(str)
        if k in market_df.columns:
            market_df[k] = market_df[k].astype(str)
    test_df_with_market = test_df.merge(
        market_df[["ninki", "fukuoddslow"] + merge_keys],
        on=merge_keys,
        how="left",
    )

    baseline_df = compute_all_baselines(
        test_df_with_market,
        X_train_bl4_bl5=X_train,
        y_train=y_train,
        X_test_bl4_bl5=X_test,
        X_calib=X_calib,
        y_calib=y_calib,
        # calibrate_bl4_bl5=False: BL-4/BL-5 の calibrator 経由予測で LightGBM categorical
        # 前処理が走らない問題 (PLAN 03 baseline.py 制約) のため・本 PLAN では未キャリブレーション
        # で評価レポートを生成する (BL_UNCALIBRATED_NOTE で注記・SC#2 比較公平性は Phase 6 で再評価)。
        calibrate_bl4_bl5=False,
    )
    return baseline_df


def _write_eval_report(
    results_by_model: dict[str, dict],
    baseline_df: pd.DataFrame,  # type: ignore[name-defined]
    feature_df: pd.DataFrame,  # type: ignore[name-defined]
) -> dict:
    """evaluate_all_models を呼出し reports/04-eval.{md,json} に出力する (SC#2)。

    主モデル (lightgbm/catboost) の pred_df と BL-1..5 の baseline_df を統合し・
    test split で評価する。
    """
    import pandas as pd

    from src.model.data import split_3way

    splits = split_3way(feature_df)
    test_df = splits["test"]
    y_test = test_df["fukusho_hit_validated"].astype(int)
    # evaluator が期待する形式: 予測 DataFrame は p_fukusho_hit / race_key / entry_count /
    # split / fukusho_hit 列を持つ。主モデルの pred_df を evaluator 形式に変換。
    predictions_by_model: dict[str, pd.DataFrame] = {}

    for mt, result in results_by_model.items():
        pred_df = result["pred_df"].copy()
        # evaluator 用の補助列を付与
        # pred_df は PK 7カラム + p_fukusho_hit + race_date + split を持つ
        # race_key / entry_count / fukusho_hit を test_df から結合
        merge_keys = ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"]
        for k in merge_keys:
            if k in pred_df.columns:
                pred_df[k] = pred_df[k].astype(str)
        test_eval = test_df.copy()
        for k in merge_keys:
            if k in test_eval.columns:
                test_eval[k] = test_eval[k].astype(str)
        # race_key と fukusho_hit (真ラベル) と entry_count を結合
        aux_cols = ["race_key", "fukusho_hit_validated", "sales_start_entry_count"]
        aux_cols = [c for c in aux_cols if c in test_eval.columns]
        pred_df = pred_df.merge(
            test_eval[merge_keys + aux_cols],
            on=merge_keys,
            how="left",
        )
        # evaluator 期待列名に rename
        if "fukusho_hit_validated" in pred_df.columns:
            pred_df = pred_df.rename(columns={"fukusho_hit_validated": "fukusho_hit"})
        if "sales_start_entry_count" in pred_df.columns:
            pred_df = pred_df.rename(columns={"sales_start_entry_count": "entry_count"})
        predictions_by_model[mt] = pred_df

    # BL-1..5 を baseline_df から evaluator 形式に変換
    for bl_name, p_col in [
        ("bl1", "p_bl1"),
        ("bl2", "p_bl2"),
        ("bl3", "p_bl3"),
        ("bl4", "p_bl4"),
        ("bl5", "p_bl5"),
    ]:
        if p_col not in baseline_df.columns:
            continue
        bl_df = pd.DataFrame(index=baseline_df.index)
        bl_df["p_fukusho_hit"] = baseline_df[p_col].values
        bl_df["split"] = "test"
        # race_key / entry_count / fukusho_hit を test_df から結合
        bl_df["race_key"] = test_df["race_key"].values if "race_key" in test_df.columns else None
        bl_df["entry_count"] = (
            test_df["sales_start_entry_count"].values
            if "sales_start_entry_count" in test_df.columns
            else None
        )
        bl_df["fukusho_hit"] = test_df["fukusho_hit_validated"].astype(int).values
        # pred 確率が NaN の行 (市場データ無し等) は除外
        bl_df = bl_df.dropna(subset=["p_fukusho_hit"])
        predictions_by_model[bl_name] = bl_df

    metrics = evaluate_all_models(
        predictions_by_model,
        y_true_by_split={"test": y_test},
        out_md_path="reports/04-eval.md",
        out_json_path="reports/04-eval.json",
    )
    return metrics


if __name__ == "__main__":
    sys.exit(main())
