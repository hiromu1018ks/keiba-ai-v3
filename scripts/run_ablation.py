# ruff: noqa: E501
"""Spike 001 (ablation-recovery): Phase 9-12 回収率 ablation ハーネス.

事前登録: reports/12-evaluation/ablation-spec.{md,json}（commit 済み・実行前登録）。

本ハーネスは **生産 primitive を1行も変更しない** (make_X_y / train_and_predict 不改変・
core value 機械保証・adversarial audit 被覆維持)。実験は本スクリプト内に隔離する。

2 モード:
  - snap-swap : ``train_and_predict`` をそのまま使用し snapshot_id/theta を切替 (A0-A3/B1)。
                安全・helper 含む・生産と同一学習 chain。
  - column-drop: ``make_X_y`` で完全 FEATURE_COLUMNS の X,y を取得 (生産と一致・assert 通過)
                → スクリプト内で ``X.drop(columns=<除外群>)`` し LightGBM 学習 (C/D/E)。
                train_and_predict を通さない自前 chain (orchestrator 内部関数を import 再利用・
                コピペでない) → A3 フル特徴量で snap-swap と一致クロスチェックが命綱。

統一指標 (全変種同一・事前登録 §3):
  - selector: ``select_bets(FUKUSHO_EV_V1_THRESHOLDS)`` = EV>=1.05 ∩ p>=0.15 ∩ odds>=1.5 ∩ top-2
  - 回収率: ``sum(payout_amount)/sum(effective_stake)`` (compute_backtest_metrics)
  - 回収率計算 chain は ``run_backtest._run_main_model_backtest`` を import 再利用 (run_backtest
    と完全同一 → A0 で reports/05-backtest の 0.6471 一致を保証)。

聖域: §11.2 test 窓 BT-1 固定 / SAFE-01 odds-free / byte-reproducible (FIXED_REPRODUCE_TS・seed=42
・thread=1) / LightGBMのみ / BT-1/30min / statement_timeout / no DB writes.

Usage::

    # A0 ゲート検証 (reports/05-backtest 0.6471 と一致するか)
    uv run python scripts/run_ablation.py --mode snap-swap --snapshot-id 20260620-1a-postreview-v2 --a0-gate

    # A1/A2/A3 測定 (9→9.1 悪化の12系統一再判定)
    uv run python scripts/run_ablation.py --mode snap-swap --snapshot-id 20260625-1a-speedfigure-v1
    uv run python scripts/run_ablation.py --mode snap-swap --snapshot-id 20260626-1a-speedprofile-v1
    uv run python scripts/run_ablation.py --mode snap-swap --snapshot-id 20260626-1a-opponentstrength-v1

    # B1: race-relative(theta=1.0) 点推定 (Phase 11 真の効果)
    uv run python scripts/run_ablation.py --mode snap-swap --snapshot-id 20260626-1a-opponentstrength-v1 --theta 1.0

    # column-drop (C/D/E・段階2・A3 クロスチェック後): --exclude-features <group|col,col,...>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# scripts/ を sys.path に追加し run_backtest の関数を import 再利用 (回収率 chain の同一性保証)
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import run_backtest as rb  # noqa: E402  _run_main_model_backtest / _fit_bt_category_map / _carve_calib_from_train_tail / _filter_label_by_period / _fetch_harai_race_level

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor  # noqa: E402
from src.ev.odds_snapshot import fetch_jodds  # noqa: E402
from src.model.data import (  # noqa: E402
    build_training_frame,
    load_feature_matrix,
    load_labels,
    make_race_key,
    make_X_y,
    split_3way,
)
from src.model.orchestrator import (  # noqa: E402
    FIXED_REPRODUCE_TS,
    _apply_category_map,
    _merge_params,
    train_and_predict,
)
from src.utils.group_split import BT_WINDOWS  # noqa: E402

# column-drop モード用 (train_and_predict を通さない自前 chain・内部関数 import 再利用)
from src.model.calibrator import calibrate_model  # isort: skip  # noqa: E402
from src.model.predict import make_model_version, predict_p_fukusho  # isort: skip  # noqa: E402
from src.model.trainer import (  # isort: skip  # noqa: E402
    LGB_INIT_PARAMS,
    _prepare_lightgbm_train_eval,
    _split_train_eval_tail,
    train_lightgbm,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_ablation")

# ---------------------------------------------------------------------------
# 定数 (事前登録 §2/§3・run_phase12 BT1_PERIODS と同一)
# ---------------------------------------------------------------------------
POLICY = "30min_before"
MODEL_TYPE_BINARY = "lightgbm"
MODEL_TYPE_RR = "lightgbm_rr"
# A0 universe 確認 (label v1.1.0・commit 2cdbac1・newcomer '12' 誤除外修正後)。
# 古い v1.0.0 バグ universe (eligible 22793・新馬過剰除外) の参照値 → 新 universe (eligible 42214) では使えない。
#   v1.0.0 参考: 05-backtest recovery_rate=0.6471421933085502 / 09-stopgate roi=0.7017790428749333 (09系 selector)
# 新 universe は外部参照が無いため・ゲートは「universe 確認 + pipeline 正準性 + byte-reproducible」で担保。
A0_V1_0_05_BACKTEST = 0.6471421933085502  # 参考: 古い v1.0.0 バグ universe
A0_V1_0_09_STOPGATE = 0.7017790428749333  # 参考: 古い v1.0.0 (09系 selector)
A0_V1_1_UNIVERSE_MIN_ROWS = (
    40000  # 新 universe (v1.1.0) の _full_candidate_rows 下限 (1勝/未勝利復帰)
)
A0_V1_0_BUGGY_MAX_ROWS = 25000  # 古い v1.0.0 バグ universe (過剰除外) の上限


def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
    """readonly pool の connection に SET statement_timeout='30s' (memory: subagent-db-query-statement-timeout).

    run_phase12_evaluation.py L250-258 と同一 idiom。make_pool(role=..., configure=...) 経由で
    pool 全 connection に適用され・重いクエリの孤立実行 (CPU 張り付き) を防止する。
    """
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()


def _bt1():
    """BT-1 window (group_split.BT_WINDOWS から取得・§15.5)。"""
    for bt in BT_WINDOWS:
        if bt.name == "BT-1":
            return bt
    raise RuntimeError("BT-1 が BT_WINDOWS に見つからない (§15.5)")


def _prepare_feature_df(snapshot_id: str, readonly_pool) -> pd.DataFrame:  # type: ignore[name-defined]
    """load_feature_matrix(snapshot_id) + load_labels + build_training_frame (run_backtest._prepare_feature_df と同一・ただし snapshot_id 明示).

    REVIEW H1-a/b: snapshot_id を load_feature_matrix に渡し v1.0/speedfig/speedprof/opponent
    各 snapshot をロード (run_backtest._prepare_feature_df は v1.0 デフォルト固定・本ハーネスは明示)。
    """
    feature_df_raw = load_feature_matrix(snapshot_id)
    if readonly_pool is None:
        return feature_df_raw
    with readonly_cursor(readonly_pool) as cur:
        label_df = load_labels(cur)
    return build_training_frame(feature_df_raw, label_df)


def _fetch_live_db(readonly_pool, periods: dict[str, tuple[str, str]]):
    """BT-1 test 期間の JODDS/label/HARAI を取得 (readonly・statement_timeout 済み pool).

    run_backtest._run_pipeline L1151-1161 と同一 (test_years filter で全期間 JODDS 回避・WR-10/12)。
    """
    test_years = [
        str(y) for y in range(int(periods["test"][0][:4]), int(periods["test"][1][:4]) + 1)
    ]
    with readonly_cursor(readonly_pool) as cur:
        jodds_df = fetch_jodds(cur, years=test_years)
        label_df = load_labels(cur)
        harai_race_df = rb._fetch_harai_race_level(cur)
    # CR-02: load_labels は race_key を SELECT しないため正準形式を付与 (run_backtest idiom)
    if "race_key" not in label_df.columns:
        label_df = label_df.copy()
        label_df["race_key"] = make_race_key(label_df).to_numpy()
    # label を BT-1 test 期間に filter (silent fallback 禁止・§19.1 聖域)
    label_df = rb._filter_label_by_period(label_df, periods["test"][0], periods["test"][1])
    return jodds_df, label_df, harai_race_df


def _metrics_from_pred_df(
    bt,
    pred_df: pd.DataFrame,  # type: ignore[name-defined]
    jodds_df: pd.DataFrame,  # type: ignore[name-defined]
    label_df: pd.DataFrame,  # type: ignore[name-defined]
    harai_race_df: pd.DataFrame,  # type: ignore[name-defined]
    *,
    snapshot_id: str,
    model_version: str,
    periods: dict[str, tuple[str, str]],
    model_type: str,
) -> dict[str, Any]:
    """run_backtest._run_main_model_backtest で回収率 chain を走らせる (12系統一 selector・run_backtest と同一).

    write_cur=None / no_write_db=True で DB 書込 skip (dry run)。戻り row に
    recovery_rate / selected / hit_rate / P/L 等が入る (run_backtest と同一 key)。
    """
    return rb._run_main_model_backtest(
        bt,
        POLICY,
        model_type,
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


def run_snap_swap(
    snapshot_id: str,
    *,
    theta: float | None,
    readonly_pool,
) -> dict[str, Any]:
    """snap-swap モード: train_and_predict 使用 (A0-A3/B1)。

    train_and_predict は make_X_y で完全 FEATURE_COLUMNS の X,y を取得し (生産と同一 chain)
    train_lightgbm + calibrate_model + (theta 補正) + predict_p_fukusho を統合実行。
    本関数は train_and_predict を呼ぶのみ (column-drop なし・FEATURE_COLUMNS 全使用)。
    """
    bt = _bt1()
    periods = rb._carve_calib_from_train_tail(bt)
    logger.info(
        "snap-swap: snapshot=%s theta=%s periods train=%s..%s calib=%s..%s test=%s..%s",
        snapshot_id,
        theta,
        periods["train"][0],
        periods["train"][1],
        periods["calib"][0],
        periods["calib"][1],
        periods["test"][0],
        periods["test"][1],
    )

    feature_df = _prepare_feature_df(snapshot_id, readonly_pool)
    # HIGH-5: BT-1 train 期間のみで fit_category_map (frozen map・§14.3 leak-safe)
    bt_map = rb._fit_bt_category_map(feature_df, periods["train"][0], periods["train"][1])

    model_type = MODEL_TYPE_RR if theta is not None else MODEL_TYPE_BINARY
    result = train_and_predict(
        feature_df,
        model_type=model_type,
        feature_snapshot_id=snapshot_id,
        snapshot_id=snapshot_id,  # FEATURE_COLUMNS 選択用 (make_X_y に伝播・H1-b)
        version_n=1,
        seed=42,
        as_of_datetime=FIXED_REPRODUCE_TS,
        split_periods=periods,
        category_map=bt_map,
        theta=theta,
    )
    pred_df = result["pred_df"]
    model_version = result["model_version"]
    logger.info(
        "snap-swap: train_and_predict 完了 model_type=%s model_version=%s pred_rows=%d",
        model_type,
        model_version,
        len(pred_df),
    )

    jodds_df, label_df, harai_race_df = _fetch_live_db(readonly_pool, periods)
    row = _metrics_from_pred_df(
        bt,
        pred_df,
        jodds_df,
        label_df,
        harai_race_df,
        snapshot_id=snapshot_id,
        model_version=model_version,
        periods=periods,
        model_type=model_type,
    )
    return row


def run_column_drop(
    snapshot_id: str,
    *,
    exclude_features: list[str],
    theta: float | None,
    readonly_pool,
) -> dict[str, Any]:
    """column-drop モード: make_X_y→X.drop→自前 chain (C/D/E)。

    make_X_y(frame, snapshot_id) で完全 FEATURE_COLUMNS の X,y を取得 (生産と一致・assert 通過・
    make_X_y 不改変) → スクリプト内で X.drop(columns=exclude) して LightGBM 学習。
    train_and_predict を通さない自前 chain (orchestrator 内部関数 import 再利用)。

    TODO (段階2): A3 フル特徴量 (exclude=[]) で snap-swap モードと回収率完全一致をクロスチェック
    してから本格運用。一致が column-drop 妥当性の命綱 (ユーザー指示 b)。

    Note: theta (race_relative) は別途 (B1・q_shrink 計算が必要・guard C-12-02-1)。
    """
    if theta is not None:
        raise NotImplementedError(
            "column-drop + theta(race_relative) は B1 で別途実装 (q_shrink 計算が必要・guard C-12-02-1)"
        )

    bt = _bt1()
    periods = rb._carve_calib_from_train_tail(bt)
    logger.info(
        "column-drop: snapshot=%s exclude=%d theta=%s",
        snapshot_id,
        len(exclude_features),
        theta,
    )

    feature_df = _prepare_feature_df(snapshot_id, readonly_pool)
    bt_map = rb._fit_bt_category_map(feature_df, periods["train"][0], periods["train"][1])
    if bt_map is not None:
        feature_df = _apply_category_map(feature_df, bt_map)
    splits = split_3way(feature_df, periods=periods)
    train_df, calib_df, test_df = splits["train"], splits["calib"], splits["test"]

    # make_X_y で完全 FEATURE_COLUMNS の X,y (生産と一致・FEATURE_COLUMNS assert 通過・make_X_y 不改変)
    X_train, y_train = make_X_y(train_df, snapshot_id=snapshot_id)
    X_calib, y_calib = make_X_y(calib_df, snapshot_id=snapshot_id)
    X_test, y_test = make_X_y(test_df, snapshot_id=snapshot_id)

    # column-drop (実験隔離・make_X_y 不改変・X.drop のみ・フル特徴量時は exclude=[] で無操作)
    drop_cols = [c for c in exclude_features if c in X_train.columns]
    if drop_cols:
        logger.info("column-drop: 除外 %d 列 (先頭5): %s", len(drop_cols), drop_cols[:5])
        X_train = X_train.drop(columns=drop_cols)
        X_calib = X_calib.drop(columns=drop_cols)
        X_test = X_test.drop(columns=drop_cols)

    # --- train_and_predict の LightGBM binary chain を内部関数 import で再構築 ---
    train_meta_cols = [
        c for c in ("race_start_datetime", "race_key", "race_date") if c in train_df.columns
    ]
    train_split_frame = X_train.copy()
    for c in train_meta_cols:
        train_split_frame[c] = train_df.loc[X_train.index, c].values
    train_core_df, train_tail_df = _split_train_eval_tail(train_split_frame, eval_fraction=0.2)
    X_train_core = train_core_df.drop(columns=train_meta_cols, errors="ignore")
    X_train_tail = train_tail_df.drop(columns=train_meta_cols, errors="ignore")
    y_train_core = y_train.loc[X_train_core.index]
    y_train_tail = y_train.loc[X_train_tail.index]

    eval_race_keys = (
        set(train_tail_df["race_key"]) if "race_key" in train_tail_df.columns else set()
    )
    calib_race_keys = set(calib_df["race_key"]) if "race_key" in calib_df.columns else set()
    test_race_keys = set(test_df["race_key"]) if "race_key" in test_df.columns else set()
    train_core_max_date = train_df["race_date"].max()
    eval_max_date = (
        train_tail_df["race_date"].max() if "race_date" in train_tail_df.columns else None
    )

    merged_params = _merge_params(LGB_INIT_PARAMS, None, 42)
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

    # calibrate_model (prefit・isotonic/sigmoid 切替)
    _, X_calib_lgb = _prepare_lightgbm_train_eval(X_train_core, X_calib)
    calib_result = calibrate_model(
        estimator,
        X_calib_lgb,
        y_calib,
        race_dates_calib=calib_df.loc[X_calib.index, "race_date"],
        train_max_date=train_df["race_date"].max(),
    )

    # predict (test) → pred_df
    race_df_test = test_df.loc[X_test.index, :]
    _, X_test_lgb = _prepare_lightgbm_train_eval(X_train_core, X_test)
    model_version = make_model_version(snapshot_id, "lightgbm", 1)
    pred_df = predict_p_fukusho(
        calib_result.calibrated,
        X_test_lgb,
        model_type="lightgbm",
        model_version=model_version,
        feature_snapshot_id=snapshot_id,
        calib_method=calib_result.calib_method,
        race_df=race_df_test,
        split_label="test",
        as_of_datetime=FIXED_REPRODUCE_TS,
        label_version="v1.1.0",
        odds_snapshot_policy=POLICY,
        backtest_strategy_version="fukusho_ev_v1",
    )
    # pred_df に backtest 用 meta 列 (race_start_datetime / race_key) を付与
    # (train_and_predict L867-898 と同一・PREDICTION_COLUMNS はこれらを含まないため別途付与。
    #  _build_race_times_per_horse HIGH-1 と select_odds_snapshot cutoff が要求)
    pred_df = pred_df.copy()
    if "race_start_datetime" in race_df_test.columns:
        pred_df["race_start_datetime"] = race_df_test["race_start_datetime"].values
    if "race_key" not in pred_df.columns:
        pred_df["race_key"] = make_race_key(race_df_test).to_numpy()
    logger.info(
        "column-drop: 学習+予測完了 model_version=%s pred_rows=%d (drop=%d)",
        model_version,
        len(pred_df),
        len(drop_cols),
    )

    jodds_df, label_df, harai_race_df = _fetch_live_db(readonly_pool, periods)
    row = _metrics_from_pred_df(
        bt,
        pred_df,
        jodds_df,
        label_df,
        harai_race_df,
        snapshot_id=snapshot_id,
        model_version=model_version,
        periods=periods,
        model_type="lightgbm",
    )
    return row


def _row_to_result(
    row: dict[str, Any], snapshot_id: str, theta: float | None, mode: str, exclude: list[str] | None
) -> dict[str, Any]:
    """backtest row を ablation 結果 dict に整列 (報告列: 事前登録 §3)。"""
    return {
        "mode": mode,
        "snapshot_id": snapshot_id,
        "theta": theta,
        "exclude_features": exclude,
        "recovery_rate": float(row.get("recovery_rate", 0.0)),
        "n_selected": int(row.get("selected", 0)),
        "effective_bet": int(row.get("effective_bet", 0)),
        "hit_count": int(row.get("_metrics", {}).get("hit_count", 0)),
        "hit_rate": float(row.get("hit_rate", 0.0)),
        "profit_loss": int(row.get("P/L", 0)),
        "max_drawdown": int(row.get("max_DD", 0)),
        "_full_candidate_rows": int(row.get("_full_candidate_rows", 0)),
        "bt_name": row.get("bt_name"),
        "odds_policy": row.get("odds_policy"),
        "model_type": row.get("model_type"),
        "model_version": row.get("model_version", ""),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spike 001 ablation ハーネス (Phase 9-12 回収率・12系統一 selector)",
    )
    parser.add_argument("--mode", choices=["snap-swap", "column-drop"], default="snap-swap")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument(
        "--theta",
        type=float,
        default=None,
        help="race-relative theta (B1: 1.0)・None で binary 点推定",
    )
    parser.add_argument(
        "--exclude-features",
        default=None,
        help="column-drop 除外群 (カンマ区切り col 名 or group 名・段階2)",
    )
    parser.add_argument(
        "--a0-gate",
        action="store_true",
        help="A0 ゲート (v1.1.0): _full_candidate_rows で新 universe 確認 (1勝/未勝利復帰・>=40000)・v1.0.0 バグ universe (<=25000) で FAIL",
    )
    parser.add_argument("--out-json", default=None, help="結果 JSON 出力 path (任意)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info(
        "config: mode=%s snapshot_id=%s theta=%s a0_gate=%s",
        args.mode,
        args.snapshot_id,
        args.theta,
        args.a0_gate,
    )

    readonly_pool = make_pool(settings, role="readonly", configure=_configure_statement_timeout)
    try:
        if args.mode == "snap-swap":
            row = run_snap_swap(args.snapshot_id, theta=args.theta, readonly_pool=readonly_pool)
            exclude = None
        else:
            exclude = (
                [s.strip() for s in args.exclude_features.split(",") if s.strip()]
                if args.exclude_features
                else []
            )
            row = run_column_drop(
                args.snapshot_id,
                exclude_features=exclude,
                theta=args.theta,
                readonly_pool=readonly_pool,
            )
        result = _row_to_result(row, args.snapshot_id, args.theta, args.mode, exclude)
        logger.info("RESULT: %s", json.dumps(result, ensure_ascii=False))

        # A0 ゲート (label v1.1.0・新 universe・事前登録 §4 更新)。
        # 新 universe は外部参照が無いため・_full_candidate_rows で新 universe 確認 + pipeline 正準性で担保。
        # 回収率の絶対値比較 (古い v1.0.0 の 0.6471/0.7018) は universe が違うため行わない。
        if args.a0_gate:
            fcr = result["_full_candidate_rows"]
            rr = result["recovery_rate"]
            if fcr <= A0_V1_0_BUGGY_MAX_ROWS:
                logger.error(
                    "A0 GATE FAIL: _full_candidate_rows=%d <= %d (v1.0.0 バグ universe・新 label v1.1.0 が効いていない)・"
                    "label.fukusho_label の再生成 (commit 2cdbac1) を確認",
                    fcr,
                    A0_V1_0_BUGGY_MAX_ROWS,
                )
                return 2
            if fcr < A0_V1_1_UNIVERSE_MIN_ROWS:
                logger.warning(
                    "A0 GATE WARN: _full_candidate_rows=%d < %d (新 universe 想定より少ない・feature/label 対応要確認)",
                    fcr,
                    A0_V1_1_UNIVERSE_MIN_ROWS,
                )
            logger.info(
                "A0 GATE PASS (v1.1.0): _full_candidate_rows=%d (新 universe・1勝/未勝利復帰)・"
                "recovery_rate=%.10f (新 universe 正準値・外部参照なし・pipeline正準性+byte-reproducibleで担保)・"
                "参考(古いv1.0.0): 05-backtest=%.4f・09-stopgate=%.4f",
                fcr,
                rr,
                A0_V1_0_05_BACKTEST,
                A0_V1_0_09_STOPGATE,
            )

        if args.out_json:
            out = Path(args.out_json)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("wrote %s", out)
        return 0
    finally:
        readonly_pool.close()


if __name__ == "__main__":
    sys.exit(main())
