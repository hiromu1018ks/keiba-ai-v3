# ruff: noqa: E501
"""Phase 12 p_lower EV + Falsification 統合評価 script (SC#1-5 / EV-01 / EVAL-01 / EVAL-02 / SAFE-01).

本 script は Plan 12-01〜12-03 の成果 (compute_p_lower_conformal_shrinkage / orchestrator p_lower_q_shrink
注入 / src/eval/falsification.py / evaluator.check_phase12_warn_gate / segment_eval.compute_roi_by_bin /
refund_accounting.slippage) を統合し・Phase 12 の全 SC を live-DB で実証する最終評価 script である。

run_phase11_evaluation.py の idiom を踏襲し (§11.2 聖域の機械保証・theta/q_shrink 事前書き出し・
_sanitize_for_json / _atomic_write_text / _attach_label_to_pred / load_predictions public wrapper /
statement_timeout='30s' / byte-reproducible §19.1)・Phase 12 固有の以下を統合する:

  1. **q_shrink 計算 (calib slice のみ)**: ``_compute_q_shrink_on_calib`` が
     ``orchestrator.train_and_predict(score_split='calib')`` の calib slice のみで
     ``compute_p_lower_conformal_shrinkage`` を呼ぶ (§11.2 聖域・codex HIGH#1・score_split guard L449-455
     が test 窓に触れない機械保証)。pred_proba と y_calib を race_key+umaban fail-loud key-join で
     整列 (Phase 11 _attach_label_to_pred L452-458 と同一 idiom・C-12-04-1 HIGH)。
  2. **q_shrink.json 事前書き出し (C-12-04-1 HIGH)**: test 窓評価 (score_split='test') に先立ち・
     ``q_shrink.json`` を byte-reproducible (sort_keys=True, ensure_ascii=False, allow_nan=False) に
     atomic write する (theta-selection.json idiom・後知恵すり替え禁止)。
  3. **test 窓 p_lower 生成 (C-12-04-2 HIGH)**: ``orchestrator.train_and_predict(score_split='test',
     theta=1.0, p_lower_q_shrink=<calibで計算した値>)`` で calib 済み q_shrink を注入する
     (Plan 02 の p_lower_q_shrink keyword-only 引数が唯一の受取経路・test 窓 outcome を使った
     q_shrink 再計算を構造的に排除)。
  4. **falsification pipeline (C-12-03-1 HIGH・C-12-03-4 2-window 分離)**:
     ``run_falsification_pipeline`` が (a) ``fit_market_implied_calibrator`` を train/calib 窓のみで
     fit し (b) ``run_falsification_test`` を test 窓予測のみで評価する (§11.2 聖域)。
     ``falsification-spec.json`` を ``write_falsification_spec`` で test 窓評価前に byte-reproducible
     に事前書き出し (threshold dredging 監査)。
  5. **gate 評価 (D-06)**: ``_evaluate_gate`` が §15.2 gate (``check_acceptance_gate`` をそのまま消費・
     block_reasons/block_triggered・§15.2 不変) と Phase 12 専用 WARN gate
     (``check_phase12_warn_gate``・phase12_warn_triggered) を別キーで併載 (上書きでない・D-06/D-07)。
  6. **switch_recommendation (D-09)**: ``compute_switch_recommendation`` が SC#4 WARN gate +
     p_lower EV v1.0 binary 回収率比較 + falsification verdict を統合し 'switch'/'hold'/'reject' を
     report のみに出す (is_primary DB 変更はしない・人間承認の別アクション)。

聖域 (CONTEXT.md / 12-CONTEXT.md D-01..D-10 / 12-RESEARCH.md / 12-PATTERNS.md / 12-REVIEWS.md):
  - **§11.2 test 窓 sanctuary (critical)**: q_shrink 計算・market_implied calibrator fit・
    falsification 回帰仕様は train/calib 窓のみ。test 窓は予測のみで評価 (Shared Pattern 6)。
    score_split='calib' 経路が test 窓に触れない機械保証 (orchestrator L449-455 guard)。
    q_shrink.json / falsification-spec.json を test 窓評価前に byte-reproducible に事前書き出し。
  - **[C-12-04-3 / C2-12-04-2] 事前登録定数の import 集約**: Q_LEVEL_SHRINKAGE / Q_LEVEL_FALSIFICATION /
    HOLM_ALPHA / MARKET_CALIB_SAMPLE_THRESHOLD / ODDS_CLIP_MIN/MAX / LOGIT_CLIP_EPS /
    PHASE12_*_THRESHOLD は src/eval/falsification.py (Plan 03 constants block・C3-12-03-1 で Q_LEVEL_SHRINKAGE
    追加済み) から import し run script に重複定義しない (BT1_PERIODS のみ run script 固有)。
  - **D-10 (is_primary 立てない・人間承認の別アクション)**: 本 script は ``set_primary_model`` を呼ばない。
    AST check で Call node 0件 (Phase 11 D-07 踏襲)。
    switch_recommendation は判断材料を report に出すのみ (D-09)。is_primary DB 変更は人間承認の別アクション。
    (注: ``set_primary_model`` という識別子は・AST check で Call node 0件を保証するため・本 docstring
    以外の code に出現しない。docstring で言及するのは「呼ばない」ことを明示するため・AST check は Call node
    のみを判定するので false positive にならない。)
    **[C-12-04-4 MEDIUM] load_predictions は呼ぶ (SC#5 idempotent swap):**
    本 script は ``prediction_load.load_predictions`` (public wrapper・codex HIGH#4) を呼び・
    race-relative model の prediction 行を model_version scoped で idempotent swap する (SC#5)。
    Phase 11 docstring (run_phase11_evaluation.py L36-44) は load_predictions の呼出事実について
   不正確な記述を含んでいた (実際は L418-440 で呼ぶ)。本 script の docstring は load_predictions を呼ぶ事実を
    正確に反映し・D-10 対象を set_primary_model のみに限定する (Phase 11 docstring の不正確さを踏襲しない・C-12-04-4)。
  - **§15.2 gate 不変 (D-06)**: ``_evaluate_gate`` は ``evaluator.check_acceptance_gate`` をそのまま
    消費し・§15.2 gate の定義を run script 側で再定義しない。Phase 12 拡張指標は §15.2 指標と別キーで併載
    (後知恵すり替え禁止・memory: fix-must-verify-gate-result-livedb)。
  - **byte-reproducible §19.1**: FIXED_REPRODUCE_TS + 固定 seed/thread・json.dumps(sort_keys=True,
    ensure_ascii=False, allow_nan=False)・2回実行で reports/12-evaluation/*.json が bit-identical。
  - **SAFE-01**: 本 script は odds/market_implied を evaluation 専用層 (falsification / EV / refund_accounting)
    で消費するが・FEATURE_COLUMNS / build_training_frame / load_feature_matrix 等 feature 構築経路を通じて
    feature に混入させない (orchestrator.train_and_predict の FEATURE_COLUMNS allowlist が保証)。
  - **statement_timeout**: readonly_pool が ``SET statement_timeout = '30s'`` で configure される
    (memory: subagent-db-query-statement-timeout・重い DB クエリの孤立実行防止)。
  - **[C-12-04-5 HIGH・C-12-01-1 と同根] migration は呼ばない**: ``PREDICTION_ADD_P_LOWER_SQL`` (Plan 01 で
    src/db/schema.py に追加済み) の適用は ``run_apply_schema.py`` (owner/admin 権限・psql でなく
    ``uv run python scripts/run_apply_schema.py``) に一本化 (memory: migration-privilege-admin-required・
    etl ロールで ALTER TABLE を実行すると InsufficientPrivilege)。本 script からは migration 実行を削除
    (Phase 11 L286-290 idiom と同一)。

Usage (live-DB・KEIBA_SKIP_DB_TESTS unset・owner/admin で PREDICTION_ADD_P_LOWER_SQL 適用済みの前提)::

    uv run python scripts/run_phase12_evaluation.py \\
        --baseline-snapshot-id 20260626-1a-opponentstrength-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --selected-theta 1.0 \\
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
# (scripts/run_phase11_evaluation.py L80-84 と同一 idiom)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §15.2 事前登録指標不変: binning 定数を evaluator/segment_eval から import 再利用 (再定義禁止)
# [C-12-04-3 / C2-12-04-2 / C3-12-03-1] Phase 12 事前登録定数は falsification.py (Plan 03) の
# constants block から import し run script に重複定義しない (BT1_PERIODS のみ run script 固有)。
# [gap-closure] JODDS odds pipeline を run_backtest.py の PROVEN pattern で統合 (gap-closure):
# falsification / _compute_recovery (EV) / _compute_odds_band_calib_max_dev (SC#4 gate) /
# switch_recommendation が fuku_odds_lower/fuku_odds_upper を必要とするが・commit d0881f1 の初期実装は
# odds join を欠いており・live-DB で falsification が WARNING skip されていた (D-15 参考記録で握り潰し)。
# eval コピー (baseline_pred / rr_pred) にのみ odds を付与し・rr_test_result["pred_df"] は
# 20-col PREDICTION_COLUMNS のまま維持 (SC#5 idempotent swap の聖域・load_predictions が PREDICTION_COLUMNS
# のみ抽出するため odds 列が混入しても書込まれないが・eval コピーへの付与で契約を明示)。
from src.ev.odds_snapshot import (  # noqa: E402
    fetch_jodds,
    select_odds_snapshot,
)
from src.eval.falsification import (  # noqa: E402
    HOLM_ALPHA,
    LOGIT_CLIP_EPS,
    MARKET_CALIB_SAMPLE_THRESHOLD,
    ODDS_CLIP_MAX,
    ODDS_CLIP_MIN,
    PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD,
    PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD,
    Q_LEVEL_FALSIFICATION,
    Q_LEVEL_SHRINKAGE,
    fit_market_implied_calibrator,
    run_falsification_test,
    write_falsification_spec,
)
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    check_acceptance_gate,
    check_phase12_warn_gate,
    compute_metrics,
)
from src.model.predict import make_model_version  # noqa: E402
from src.model.race_relative import (  # noqa: E402
    compute_p_lower_conformal_shrinkage,
)
from src.model.segment_eval import (  # noqa: E402
    NINKI_BAND_EDGES,
    ODDS_BAND_EDGES,
    ODDS_BAND_LABELS,
    _odds_band,
    evaluate_all_segments,
)

logger = logging.getLogger("run_phase12_evaluation")

# ---------------------------------------------------------------------------
# BT-1 split periods (§15.5) — train 2019-06-01..2022-06-30 / calib 2022-07-01..2022-12-31 / test 2023
# run_phase11_evaluation.py L185-189 と同一 (§19.1 再現性・Phase 5 D-03 / HIGH-B cycle-2 idiom)。
# これのみ run script 固有 (Q_LEVEL_SHRINKAGE 等の事前登録値は falsification.py から import)。
# ---------------------------------------------------------------------------
BT1_PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2019-06-01", "2022-06-30"),
    "calib": ("2022-07-01", "2022-12-31"),
    "test": ("2023-01-01", "2023-12-31"),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する."""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 12 p_lower EV + Falsification 統合評価: q_shrink 計算 (calib slice のみ)・"
            "test 窓 p_lower 生成・falsification 回帰・SC#2/SC#4 gate・switch_recommendation (D-09)・"
            "§11.2 聖域の機械保証 (C-12-04-1/2 HIGH・C-12-03-1 HIGH・C-12-01-2 HIGH)"
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
        "--selected-theta",
        type=float,
        default=1.0,
        help=(
            "Phase 11 で選択された θ (default: 1.0・reports/11-evaluation/theta-selection.json の値)"
            "・Phase 12 では θ を再選択せず Phase 11 の選択を固定使用 (§11.2 聖域)"
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
# JSON sanitizer / atomic write (run_phase11_evaluation.py L189-224 と同一 idiom)
# ---------------------------------------------------------------------------
def _sanitize_for_json(obj: Any) -> Any:
    """dict/list/float/ndarray を再帰走査し NaN/Inf/ndarray を JSON 安全な表現に変換する.

    run_phase11_evaluation.py L191-216 と同一 idiom・single-class AUC 等で NaN が混入しても
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


def _configure_statement_timeout(conn) -> None:  # noqa: ANN001
    """readonly/etl pool の connection 初期化時に ``SET statement_timeout = '30s'`` を発行する.

    T-09-21: サブエージェント経由の重い DB クエリが孤立実行して CPU 張り付きになるのを防止
    (memory: subagent-db-query-statement-timeout・run_phase11_evaluation.py L271-280 と同一 idiom)。
    make_pool(role=..., configure=_configure_statement_timeout) 経由で pool の全 connection に適用される。
    """
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()


def _attach_label_to_pred(
    pred_df: pd.DataFrame,
    *,
    label_joined_frame: pd.DataFrame,
) -> pd.DataFrame:
    """orchestrator.train_and_predict の pred_df に label を JOIN する.

    run_phase11_evaluation.py L452-458 / run_phase10_evaluation.py L500-560 と同一 idiom:
      - umaban を Int64 に正規化
      - race_key + umaban の many_to_one merge (fail-loud)
      - label 付与失敗は RuntimeError (silent leak 回避・§19.1 聖域)
    """
    pred_df = pred_df.copy()
    label_df = label_joined_frame.copy()
    pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")
    label_df["umaban"] = pd.to_numeric(label_df["umaban"], errors="coerce").astype("Int64")

    label_keep = ["race_key", "umaban", "fukusho_hit_validated"]
    # [gap-closure] _compute_recovery_rate (purchase_simulator + refund_accounting) と select_bets が
    # is_fukusho_sale_available / is_model_eligible を消費するため・label/frame から eval コピーに伝播。
    # これらが無いと _compute_recovery_rate が NaN を返し・switch_recommendation の判断材料が欠ける。
    for extra in (
        "entry_count",
        "final_starter_count",
        "sales_start_entry_count",
        "is_fukusho_sale_available",
        "is_model_eligible",
        "fukusho_payout_places",
        "is_scratch_cancel",
        "is_race_excluded",
        "is_race_cancelled",
        "is_dead_loss",
    ):
        if extra in label_df.columns and extra not in label_keep:
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
# [gap-closure] _attach_odds_to_pred / _derive_test_years — JODDS odds pipeline 統合
# ---------------------------------------------------------------------------
# gap-closure bug #2 の根治: falsification / _compute_recovery / _compute_odds_band_calib_max_dev /
# switch_recommendation が eval コピー上の fuku_odds_lower/fuku_odds_upper + entry_count を必要とするが・
# 初期実装 (commit d0881f1) は odds join を欠き・live-DB で falsification が WARNING skip されていた。
# run_backtest.py L448-460 / L575-600 の PROVEN pattern (fetch_jodds → select_odds_snapshot →
# race_key+umaban merge + HIGH-2 len assert) を踏襲する。
# §11.2 / SAFE-01 聖域: odds は eval コピー (baseline_pred / rr_pred) のみに付与し・
# rr_test_result["pred_df"] (PREDICTION_COLUMNS 20-col) には触れない (load_predictions は
# PREDICTION_COLUMNS のみ抽出するため odds 列が混入しても書込まれないが・契約を明示)。
def _derive_test_years(split_periods: dict[str, tuple[str, str]]) -> list[str]:
    """split_periods の test 期間をカバーする年リストを導出する (性能最適化・全期間 JODDS 回避).

    run_backtest.py L1153-1157 と同一 idiom: test 期間 ("2023-01-01","2023-12-31") → ["2023"]。
    複数年またぎ (例: 2023-07..2024-06) → ["2023","2024"]。fetch_jodds の ``years`` 引数に渡す。
    """
    start_year = int(split_periods["test"][0][:4])
    end_year = int(split_periods["test"][1][:4])
    if end_year < start_year:
        raise ValueError(
            f"_derive_test_years: test 期間の end_year < start_year ({start_year} > {end_year})・"
            "split_periods['test'] の順序を確認"
        )
    return [str(y) for y in range(start_year, end_year + 1)]


def _attach_odds_to_pred(
    pred_df: pd.DataFrame,
    *,
    jodds_df: pd.DataFrame,
    odds_snapshot_policy: str,
    caller_label: str,
) -> pd.DataFrame:
    """eval コピー pred_df に JODDS 固定時点 odds (fuku_odds_lower/upper) を JOIN する (gap-closure).

    run_backtest.py L448-460 (_build_race_times_per_horse) + L575-600 (merge + HIGH-2 len assert) の
    PROVEN pattern を踏襲。``select_odds_snapshot`` は ``merge_asof(direction='backward')`` で
    cutoff (= race_start_datetime - N分) 以下の最大 snapshot を per-horse で選択 (D-02 未来リーク
    構造的不可・§13 PIT プリミティブと同一思想)。

    本関数は SAFE-01 聖域を守るため・odds を ``pred_df`` の copy に付与する (入力破壊禁止・純粋関数)。
    FEATURE_COLUMNS には触れない (orchestrator.train_and_predict の FEATURE_COLUMNS allowlist が保証)。

    Parameters
    ----------
    pred_df : pd.DataFrame
        eval コピー (_attach_label_to_pred 戻り値)。必須列: ``race_key, umaban, race_start_datetime``。
        ``race_start_datetime`` は orchestrator が pred_df の meta 列として付与済み (orchestrator.py
        L867-898・PREDICTION_COLUMNS に含まれない補助列)。
    jodds_df : pd.DataFrame
        ``fetch_jodds`` の戻り値 (test 期間の JODDS snapshot・中間オッズ datakubun='1' 固定)。
    odds_snapshot_policy : str
        ``'30min_before'`` / ``'10min_before'`` (D-01 事前登録・run_backtest と同一)。
    caller_label : str
        エラー文言用の呼出側ラベル ('baseline' / 'race_relative')。

    Returns
    -------
    pd.DataFrame
        ``pred_df`` と同行数。``fuku_odds_lower`` / ``fuku_odds_upper`` / ``odds_snapshot_at`` /
        ``odds_source_type`` / ``odds_missing_reason`` 列が付与される (cross-plan contract・snake_case)。
        既存列は維持 (suffixes=('', '_snap') で衝突時も左側優先)。

    Raises
    ------
    RuntimeError
        merge 後行数が ``pred_df`` と不一致 (HIGH-2 cartesian duplication・snapshot が馬単位でない)。
    """
    if "race_start_datetime" not in pred_df.columns:
        raise RuntimeError(
            f"_attach_odds_to_pred: pred_df に race_start_datetime 列がない ({caller_label})・"
            "orchestrator.train_and_predict が meta 列として付与するはず (orchestrator.py L867-898)"
        )
    out = pred_df.copy()
    # umaban 型正規化 (merge key・Int64・run_backtest L581 と同一 idiom)
    out["umaban"] = pd.to_numeric(out["umaban"], errors="coerce").astype("Int64")

    # 馬単位 race_times 構築 (run_backtest L448-460 と同一)
    race_times = out[["race_key", "umaban", "race_start_datetime"]].copy()

    # select_odds_snapshot: per-horse cutoff 以下最大 snapshot (D-02 未来リーク構造的不可)
    snapshot = select_odds_snapshot(jodds_df, race_times, odds_snapshot_policy)

    # HIGH-2: pred_df と snapshot を (race_key, umaban) で merge + 行数不変 assert (run_backtest L590-599)
    merged = out.merge(
        snapshot, on=["race_key", "umaban"], how="left", suffixes=("", "_snap")
    )
    if len(merged) != len(out):
        raise RuntimeError(
            f"_attach_odds_to_pred: HIGH-2 cartesian duplication 検出 ({caller_label})・"
            f"len(before)={len(out)} != len(after)={len(merged)} "
            "(snapshot が馬単位でない・race_key 単独 JOIN 等)"
        )
    return merged


def _ensure_entry_count(pred_df: pd.DataFrame, *, caller_label: str) -> pd.DataFrame:
    """eval コピー pred_df に ``entry_count`` 列を確保する (gap-closure・check_sum_p_distribution 用).

    gap-closure bug #1: ``check_sum_p_distribution`` (evaluator.py L602-669) が ``entry_count_col``
    引数で ``entry_count`` を要求するが・orchestrator は ``sales_start_entry_count`` を付与し
    ``entry_count`` 列は提供しない (orchestrator.py L731)・frame にも ``sales_start_entry_count``
    しか無い場合が多い。本関数は以下の優先順位で ``entry_count`` を確保する:

      1. 既に ``entry_count`` 列が存在する → 何もしない (unit test 合成 df 等との両立)。
      2. ``sales_start_entry_count`` 列が存在する → その値を ``entry_count`` に alias。
      3. ``final_starter_count`` 列が存在する → その値を ``entry_count`` に alias (確定出走頭数)。
      4. いずれも無い → ``race_key`` の group count で導出 (最後の fallback・run_backtest の
         主モデル pred_df は race_key を持つため安全)。導出できない場合は RuntimeError (silent skip 禁止)。

    SAFE-01 聖域: 本関数は eval コピーにのみ作用し・rr_test_result["pred_df"] には触れない。
    """
    if "entry_count" in pred_df.columns:
        return pred_df
    out = pred_df.copy()
    if "sales_start_entry_count" in out.columns:
        out["entry_count"] = out["sales_start_entry_count"]
        return out
    if "final_starter_count" in out.columns:
        out["entry_count"] = out["final_starter_count"]
        return out
    if "race_key" in out.columns:
        # race_key group の行数 = そのレースの馬数 (entry_count の定義)。
        # sales_start_entry_count は frame に無くとも race_key の group size で復元できる。
        counts = out.groupby("race_key")["race_key"].transform("size")
        out["entry_count"] = counts.astype("int64")
        return out
    raise RuntimeError(
        f"_ensure_entry_count: {caller_label} pred_df に entry_count / sales_start_entry_count / "
        "final_starter_count / race_key のいずれも無い・entry_count を導出できない "
        "(check_sum_p_distribution / falsification field_size 共変量が必須)"
    )


# ---------------------------------------------------------------------------
# [gap-closure] HARAI 払戻列伝播 (recovery_rate 正常化・determine_stake_payout が payout を返すため)
# ---------------------------------------------------------------------------
# gap-closure bug (recovery_rate=0.0) の根治: _compute_recovery_rate → determine_stake_payout →
# _lookup_payfukusyo_pay が payfukusyoumaban*/payfukusyopay* を探すが・eval コピー pred_df にこれらの
# HARAI 払戻列が無い (label_keep に含まれない) → 全 slot continue → payout=0 → recovery=0.0。
# Phase 5 run_backtest.py (HIGH-C cycle-2) / 09-05 stopgate の idiom を移植し・eval コピーのみに付与。
def _fetch_harai_race_level(
    readonly_cur: Any,
    *,
    years: list[str],
) -> pd.DataFrame:
    """``raw_everydb2.n_harai`` から race-level 払戻 slot を SELECT する (HIGH-C cycle-2).

    Phase 5 ``scripts/run_backtest.py`` L1333-1359 / 09-05 ``scripts/run_speed_figure_stopgate.py`` L787-823
    と同一ロジック・scripts 間 import 依存を避けるため inline 再実装。
    ``year IN (...)`` filter 付きで test 窓のみ取得する (``statement_timeout='30s'`` 安全・全期間回避)。

    HARAI は race-level slot レコード (``PayFukusyoUmaban1..5`` + ``PayFukusyoPay1..5``) で umaban 列を持たない。
    ``refund_accounting.determine_stake_payout`` が消費する ``fuseirituflag2`` / ``tokubaraiflag2`` /
    ``payfukusyoumaban1..5`` / ``payfukusyopay1..5`` を供給する。
    """
    from src.model.data import make_race_key

    placeholders = ",".join(["%s"] * len(years))
    query = f"""
        SELECT
            year, jyocd, kaiji, nichiji, racenum,
            fuseirituflag2, henkanflag2, tokubaraiflag2,
            payfukusyoumaban1, payfukusyoumaban2, payfukusyoumaban3,
            payfukusyoumaban4, payfukusyoumaban5,
            payfukusyopay1, payfukusyopay2, payfukusyopay3,
            payfukusyopay4, payfukusyopay5
        FROM raw_everydb2.n_harai
        WHERE year IN ({placeholders})
    """
    readonly_cur.execute(query, years)
    cols = [d.name for d in readonly_cur.description]
    rows = readonly_cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    # race_key 構築 (CR-01): make_race_key 正準形式 (fetch_jodds / label と同一 source of truth)
    df["race_key"] = make_race_key(df).to_numpy()
    return df


def _attach_harai_to_pred(
    pred_df: pd.DataFrame,
    *,
    harai_race_df: pd.DataFrame,
    caller_label: str,
) -> pd.DataFrame:
    """eval コピー pred_df に HARAI race-level 払戻 slot を JOIN する (gap-closure・recovery_rate 正常化).

    Phase 5 ``scripts/run_backtest.py`` L601-615 (HIGH-C cycle-2 HARAI race-level merge) /
    09-05 ``scripts/run_speed_figure_stopgate.py`` L908-923 と同一ロジック。
    ``refund_accounting.determine_stake_payout`` → ``_lookup_payfukusyo_pay`` が消費する
    ``fuseirituflag2`` / ``tokubaraiflag2`` / ``payfukusyoumaban1..5`` / ``payfukusyopay1..5`` を付与する。
    これらが無いと ``determine_stake_payout`` が常に payout=0 を返し recovery_rate が 0.0 になる
    (P1 ``payout_amount→payout`` 修正に加えて本 JOIN が必須・``_compute_recovery_rate`` の正常化)。

    SAFE-01 聖域: HARAI 払戻は eval コピー (baseline_pred / rr_pred) のみに付与し・
    ``rr_test_result["pred_df"]`` (PREDICTION_COLUMNS 20-col・load_predictions 用) には触れない。
    FEATURE_COLUMNS / feature 構築経路には一切触れない。

    Parameters
    ----------
    pred_df : pd.DataFrame
        eval コピー (_attach_label_to_pred + _attach_odds_to_pred + _ensure_entry_count 戻り値)。
        label 系フラグ (is_fukusho_sale_available / is_scratch_cancel / is_race_excluded /
        is_race_cancelled / is_dead_loss) は _attach_label_to_pred が既に伝播済み。
    harai_race_df : pd.DataFrame
        :func:`_fetch_harai_race_level` の戻り値 (race_key + HARAI 払戻 slot 列)。
    caller_label : str
        エラー文言用の呼出側ラベル ('baseline' / 'race_relative')。

    Raises
    ------
    RuntimeError
        merge 後行数が ``pred_df`` と不一致 (HIGH-C cycle-2 HARAI broadcast 膨張・race_key 重複)。
    """
    out = pred_df.copy()
    # HARAI race_df の PK 系 (year/jyocd/kaiji/nichiji/racenum) は pred_df の PREDICTION_COLUMNS と
    # 重複するため merge から除外する (race_key で JOIN するので同値)。衝突を放置すると
    # jyocd_x/jyocd_y に分裂し segment_eval (D-15) の jyocd 軸が WARN skip になる。
    # 払戻 slot 系 (fuseirituflag2/tokubaraiflag2/payfukusyoumaban*/payfukusyopay*/henkanflag2) のみ付与。
    _harai_pk_cols = {"year", "jyocd", "kaiji", "nichiji", "racenum"}
    harai_cols = [
        c for c in harai_race_df.columns
        if c != "race_key" and c not in _harai_pk_cols
    ]
    merged = out.merge(
        harai_race_df[["race_key"] + harai_cols],
        on=["race_key"],
        how="left",
        validate="many_to_one",
    )
    if len(merged) != len(out):
        raise RuntimeError(
            f"_attach_harai_to_pred: HIGH-C cycle-2 HARAI broadcast 膨張検出 ({caller_label})・"
            f"len(before)={len(out)} != len(after)={len(merged)} "
            "(HARAI race_key 単位の重複行が存在する・validate='many_to_one' 違反)"
        )
    return merged


def _build_falsification_windows(
    *,
    frame: pd.DataFrame,
    split_periods: dict[str, tuple[str, str]],
    readonly_pool,
    odds_snapshot_policy: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """falsification 用の odds-enriched train/calib df を構築する (gap-closure・§11.2 聖域).

    gap-closure bug #2 の根治の副次側面: ``fit_market_implied_calibrator`` は train/calib 窓の
    ``fuku_odds_lower`` + ``fukusho_hit_validated`` を必要とするが・frame (FEATURE_COLUMNS 由来)
    は odds-free (D-07/§13.4 odds-free allowlist)。本関数は frame から train/calib slice を
    切り出し・JODDS を fetch して odds を付与した eval 専用 df を返す。

    §11.2 聖域 (test 窓 sanctuary):
        本関数は train/calib 窓のみを扱う (``split_periods['train']`` / ``['calib']``)。
        test 窓の ``frame`` 行・test 窓 outcome 系は扱わない (Shared Pattern 6)。

    SAFE-01 聖域:
        本関数が返す df は ``run_falsification_pipeline`` (evaluation 専用層・falsification.py 内
        SAFE-01-ALLOW) のみが消費する。FEATURE_COLUMNS / build_training_frame / load_feature_matrix
        等 feature 構築経路には一切触れない。

    Parameters
    ----------
    frame : pd.DataFrame
        ``build_training_frame`` 戻り値 (label-joined・odds-free)。``race_date`` / ``race_key`` /
        ``umaban`` / ``race_start_datetime`` / ``fukusho_hit_validated`` 列を含むこと。
    split_periods : dict
        ``{"train": (start, end), "calib": (start, end), ...}``。``train``/``calib`` を使用。
    readonly_pool
        ``make_pool(role='readonly', ...)`` の pool。JODDS fetch 用。
    odds_snapshot_policy : str
        ``'30min_before'`` / ``'10min_before'``。各馬の固定時点 snapshot を選択 (D-01 事前登録)。

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        ``(train_df_with_odds, calib_df_with_odds)``。両者とも ``fuku_odds_lower`` /
        ``fuku_odds_upper`` / ``fukusho_hit_validated`` 列を持つ。
    """
    if "race_date" not in frame.columns:
        raise RuntimeError(
            "_build_falsification_windows: frame に race_date 列がない・train/calib 切出不能"
        )
    train_start, train_end = split_periods["train"]
    calib_start, calib_end = split_periods["calib"]
    frame_dt = pd.to_datetime(frame["race_date"], errors="coerce")
    train_mask = (frame_dt >= pd.Timestamp(train_start)) & (frame_dt <= pd.Timestamp(train_end))
    calib_mask = (frame_dt >= pd.Timestamp(calib_start)) & (frame_dt <= pd.Timestamp(calib_end))
    train_df = frame.loc[train_mask].copy()
    calib_df = frame.loc[calib_mask].copy()
    if len(train_df) == 0 or len(calib_df) == 0:
        raise RuntimeError(
            f"_build_falsification_windows: train ({len(train_df)} 行) / calib ({len(calib_df)} 行) "
            "が空・split_periods と frame の race_date を確認"
        )

    # umaban 型正規化 (JODDS merge key・Int64)
    for df in (train_df, calib_df):
        df["umaban"] = pd.to_numeric(df["umaban"], errors="coerce").astype("Int64")

    # JODDS fetch (train/calib 窓の年のみ・全期間取得回避)
    train_years = [str(y) for y in range(
        int(train_start[:4]), int(train_end[:4]) + 1
    )]
    calib_years = [str(y) for y in range(
        int(calib_start[:4]), int(calib_end[:4]) + 1
    )]
    fetch_years = sorted(set(train_years) | set(calib_years))
    logger.info(
        "[gap-closure] falsification 用 JODDS fetch: years=%s (train+calib 窓)",
        fetch_years,
    )
    from src.db.connection import readonly_cursor

    # JODDS fetch は test 窓 1 年で 41s / train+calib 4 年で ~3-4min 見込み (millions of rows)。
    # 標準 statement_timeout='30s' では train+calib 窓の fetch が QueryCanceled になる。
    # JODDS fetch は SELECT-only (readonly cursor) で副作用なし・意図的に重い集計クエリのため・
    # この fetch スコープのみ statement_timeout を '600s' (10min) に延長する (sanctuary:
    # pool の configure callback は 30s のまま・本 cursor の SET LOCAL 相当の上書き)。
    # memory: subagent-db-query-statement-timeout の趣旨 (孤立 CPU 張り付き防止) は・
    # 本 cursor が with ブロックを抜けたら readonly_cursor が閉じて pool に返却されるため
    # 他の cursor に伝播しない (connection 毎の SET・pool の configure callback は次 checkin
    # で再適用される) ことで守られる。
    with readonly_cursor(readonly_pool) as jodds_cur:
        jodds_cur.execute("SET statement_timeout = '600s'")
        jodds_df = fetch_jodds(jodds_cur, years=fetch_years)

    # 各窓に odds を付与 (run_backtest L575-600 と同一 pattern・select_odds_snapshot で固定時点)
    train_with_odds = _attach_odds_to_window(
        train_df, jodds_df=jodds_df, odds_snapshot_policy=odds_snapshot_policy,
        caller_label="falsification_train",
    )
    calib_with_odds = _attach_odds_to_window(
        calib_df, jodds_df=jodds_df, odds_snapshot_policy=odds_snapshot_policy,
        caller_label="falsification_calib",
    )

    # odds が JOIN できなかった行 (no_bet / snapshot 無) は falsification 回帰から除外
    # (NaN odds は fit_market_implied_calibrator で NaN 伝播して RuntimeError になるため)。
    train_usable = train_with_odds["fuku_odds_lower"].notna()
    calib_usable = calib_with_odds["fuku_odds_lower"].notna()
    n_train_drop = int((~train_usable).sum())
    n_calib_drop = int((~calib_usable).sum())
    if n_train_drop > 0 or n_calib_drop > 0:
        logger.info(
            "[gap-closure] falsification train/calib で odds 欠損行を除外: "
            "train drop=%d (usable=%d) calib drop=%d (usable=%d)",
            n_train_drop,
            int(train_usable.sum()),
            n_calib_drop,
            int(calib_usable.sum()),
        )
    train_with_odds = train_with_odds.loc[train_usable].copy()
    calib_with_odds = calib_with_odds.loc[calib_usable].copy()
    if len(train_with_odds) == 0 or len(calib_with_odds) == 0:
        raise RuntimeError(
            f"_build_falsification_windows: odds 付与後の train ({len(train_with_odds)}) / "
            f"calib ({len(calib_with_odds)}) が空・JODDS 取得状況を確認 (years={fetch_years})"
        )
    return train_with_odds, calib_with_odds


def _attach_odds_to_window(
    df: pd.DataFrame,
    *,
    jodds_df: pd.DataFrame,
    odds_snapshot_policy: str,
    caller_label: str,
) -> pd.DataFrame:
    """frame slice (train/calib) に JODDS 固定時点 odds を JOIN する (gap-closure・falsification 用).

    ``_attach_odds_to_pred`` と同一の merge pattern だが・frame slice は PREDICTION_COLUMNS でなく
    FEATURE_COLUMNS + label 系列 (race_date / race_key / umaban / race_start_datetime /
    fukusho_hit_validated 等) を持つ。``race_start_datetime`` は load_feature_matrix が snapshot に
    同梱する (orchestrator L867-898 が pred_df の meta 列として付与する元)。
    """
    if "race_start_datetime" not in df.columns:
        raise RuntimeError(
            f"_attach_odds_to_window: df に race_start_datetime 列がない ({caller_label})・"
            "load_feature_matrix の snapshot が race_start_datetime を含む必要がある"
        )
    out = df.copy()
    out["umaban"] = pd.to_numeric(out["umaban"], errors="coerce").astype("Int64")
    race_times = out[["race_key", "umaban", "race_start_datetime"]].copy()
    snapshot = select_odds_snapshot(jodds_df, race_times, odds_snapshot_policy)
    merged = out.merge(
        snapshot, on=["race_key", "umaban"], how="left", suffixes=("", "_snap")
    )
    if len(merged) != len(out):
        raise RuntimeError(
            f"_attach_odds_to_window: HIGH-2 cartesian duplication 検出 ({caller_label})・"
            f"len(before)={len(out)} != len(after)={len(merged)}"
        )
    return merged


# ---------------------------------------------------------------------------
# [C-12-04-1 HIGH] _compute_q_shrink_on_calib (calib slice のみ・race_key+umaban fail-loud key-join)
# ---------------------------------------------------------------------------
def _compute_q_shrink_on_calib(
    *,
    calib_pred_df: pd.DataFrame,
    y_calib_df: pd.DataFrame,
    q_level: float = Q_LEVEL_SHRINKAGE,
) -> float:
    """calib slice のみで q_shrink を計算する (§11.2 聖域・C-12-04-1 HIGH).

    ``orchestrator.train_and_predict(score_split='calib')`` の戻り値の calib slice (``calib_pred_df``)
    の ``p_fukusho_hit`` (race-relative 補正後 final p) と ``y_calib_df`` の binary outcome を
    race_key + umaban fail-loud key-join で整列し・``compute_p_lower_conformal_shrinkage`` で
    q_shrink を計算する (Phase 11 _attach_label_to_pred L452-458 と同一の機械的 join・index 前提でない)。

    §11.2 聖域 (test 窓 sanctuary):
        ``calib_pred_df`` は score_split='calib' 経路の calib slice のみ (呼出側が保証)。
        test 窓の outcome は引数に取らない (Shared Pattern 6・構造的聖域ブロック)。
        ``inspect.signature`` の parameters は {calib_pred_df, y_calib_df, q_level} のみ。

    Parameters
    ----------
    calib_pred_df : pd.DataFrame
        calib slice の prediction DataFrame (orchestrator.score_split='calib' の戻り値)。
        必須列: ``race_key``, ``umaban``, ``p_fukusho_hit``。
    y_calib_df : pd.DataFrame
        calib slice の binary outcome DataFrame。必須列: ``race_key``, ``umaban``,
        ``fukusho_hit_validated``。
    q_level : float
        shrinkage quantile level (既定 ``Q_LEVEL_SHRINKAGE=0.90``・D-02 事前登録値)。

    Returns
    -------
    float
        calib slice で計算した q_shrink (overprediction residual の q_level 分位)。
    """
    pred = calib_pred_df[["race_key", "umaban", "p_fukusho_hit"]].copy()
    ydf = y_calib_df[["race_key", "umaban", "fukusho_hit_validated"]].copy()

    # race_key + umaban の機械的 join (Phase 11 _attach_label_to_pred L452-458 と同一 idiom)
    pred["umaban"] = pd.to_numeric(pred["umaban"], errors="coerce").astype("Int64")
    ydf["umaban"] = pd.to_numeric(ydf["umaban"], errors="coerce").astype("Int64")

    merged = pred.merge(
        ydf,
        on=["race_key", "umaban"],
        how="inner",
        suffixes=("", "_y"),
        validate="one_to_one",
    )
    if len(merged) != len(pred):
        raise RuntimeError(
            f"_compute_q_shrink_on_calib: calib pred_proba と y_calib の race_key+umaban key-join が失敗・"
            f"len(pred)={len(pred)} != len(joined)={len(merged)}・"
            "C-12-04-1 HIGH fail-loud (silent label/pred_proba ズレ回避・Phase 11 _attach_label_to_pred idiom)"
        )
    if len(merged) == 0:
        raise RuntimeError(
            "_compute_q_shrink_on_calib: race_key+umaban key-join で 0 行・join key 不一致"
        )

    p_final_calib = merged["p_fukusho_hit"].to_numpy(dtype=float)
    y_calib = merged["fukusho_hit_validated"].to_numpy(dtype=float)

    # compute_p_lower_conformal_shrinkage は (p_lower, q_shrink) を返すが・
    # 本関数は calib slice 上の q_shrink 計算が目的なので p_lower は破棄 (test 窓 p_lower は
    # orchestrator 側で score_split='test' + p_lower_q_shrink 注入経路で別途生成)。
    _p_lower_calib, q_shrink = compute_p_lower_conformal_shrinkage(
        p_final=p_final_calib,  # calib slice の p_final == p_final_calib
        y_calib=y_calib,
        p_final_calib=p_final_calib,
        q_level=q_level,
    )
    return float(q_shrink)


# ---------------------------------------------------------------------------
# q_shrink.json 事前書き出し (C-12-04-1 HIGH・theta-selection.json idiom)
# ---------------------------------------------------------------------------
def _write_q_shrink_json(
    out_path: Path,
    *,
    calib_pred_df: pd.DataFrame,
    y_calib_df: pd.DataFrame,
    q_level: float = Q_LEVEL_SHRINKAGE,
) -> Path:
    """q_shrink 計算経路決定直後・test 窓評価に先立ち q_shrink.json を byte-reproducible に書き出す.

    codex HIGH#1 / C-12-04-1 HIGH: theta-selection.json idiom と同一形状・後知恵すり替え禁止。
    同一入力で byte-identical (sort_keys=True, ensure_ascii=False, allow_nan=False + atomic write)。
    """
    q_shrink = _compute_q_shrink_on_calib(
        calib_pred_df=calib_pred_df,
        y_calib_df=y_calib_df,
        q_level=q_level,
    )
    payload: dict[str, Any] = {
        "q_level": float(q_level),
        "q_shrink": float(q_shrink),
        # Pitfall 1 過度な保証主張回避 (D-01 修正文): 実測 coverage + selected-only calibration で報告
        "coverage_semantics": (
            "split conformal exchangeability を仮定し (1-alpha) marginal outcome coverage を保証するが・"
            "個体ごとの真の確率の下限保証でない。時系列パネルデータでは非 exchangeable で厳密な coverage "
            "保証は壊れる。よって「calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule」"
            "として扱い・report では実測 coverage + selected-only calibration を報告する (D-01・Pitfall 1)。"
        ),
        "sanctuary": "§11.2 test 窓 sanctuary: calib slice のみで計算・test 窓 outcome 不使用",
        "constants_source": "src/eval/falsification.py constants block (Q_LEVEL_SHRINKAGE=0.90)",
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
    _atomic_write_text(out_path, text)
    return out_path


# ---------------------------------------------------------------------------
# pred_df からの指標算出 helpers (run_phase11_evaluation.py L753-841 と同一契約)
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


def _compute_selected_only_calib_max_dev(
    pred_df: pd.DataFrame, *, p_col: str = "p_fukusho_hit"
) -> float:
    """selected/high-EV 層 (p_col 上位 30%) の calibration_max_dev を算出する (D-05-3 簡易版・Phase 11 idiom).

    run_phase11_evaluation.py L804-841 と同一契約・Phase 12 では p_col='p_fukusho_hit_lower' を指定して
    p_lower ベースの selected 層を測る (SC#4 WARN gate の入力)。
    """
    if p_col not in pred_df.columns or "fukusho_hit_validated" not in pred_df.columns:
        return float("nan")
    n = len(pred_df)
    if n == 0:
        return float("nan")
    cutoff_idx = max(1, int(n * 0.30))
    sorted_pred = pred_df.sort_values(p_col, ascending=False)
    selected = sorted_pred.head(cutoff_idx)
    if len(selected) == 0:
        return float("nan")
    mean_pred = float(selected[p_col].mean())
    frac_pos = float(selected["fukusho_hit_validated"].mean())
    return float(abs(mean_pred - frac_pos))


def _compute_odds_band_calib_max_dev(
    pred_df: pd.DataFrame, *, p_col: str = "p_fukusho_hit"
) -> dict[str, float]:
    """各 odds_band の conditional calib_max_dev を算出する (SC#4・segment_eval binning 再利用).

    各 odds_band で (mean(p_col) - frac_pos) の絶対値を計算し ODDS_BAND_LABELS の dict で返す。
    odds 列が無い場合は空 dict (run_phase11 _compute_overprediction_from_pred idiom と同一の NaN-safe)。
    """
    out: dict[str, float] = {}
    if "fuku_odds_lower" not in pred_df.columns or p_col not in pred_df.columns:
        return out
    odds = pd.to_numeric(pred_df["fuku_odds_lower"], errors="coerce")
    bands = _odds_band(odds)
    for label in ODDS_BAND_LABELS:
        mask = bands == label
        if int(np.sum(mask)) == 0:
            continue
        sub = pred_df.loc[mask]
        mean_pred = float(sub[p_col].mean())
        frac_pos = float(sub["fukusho_hit_validated"].mean())
        out[label] = float(abs(mean_pred - frac_pos))
    return out


# ---------------------------------------------------------------------------
# _evaluate_gate (§15.2 gate 不変 + Phase 12 WARN gate 併載・D-06)
# ---------------------------------------------------------------------------
def _evaluate_gate(
    *,
    baseline_pred_df: pd.DataFrame,
    rr_pred_df: pd.DataFrame,
) -> dict[str, Any]:
    """baseline (theta=None v1.0 binary) と race-relative (theta=selected・p_lower 注入済み) の pred_df から
    §15.2 gate (``check_acceptance_gate``) と Phase 12 専用 WARN gate (``check_phase12_warn_gate``) を
    併載評価する (D-06・上書きでなく別キーで併載)。

    §15.2 gate (block_reasons / block_triggered) は ``evaluator.check_acceptance_gate`` をそのまま
    消費し・run script 側で再定義しない (D-06 不変・memory: fix-must-verify-gate-result-livedb)。
    Phase 12 WARN gate (phase12_warn_triggered) は ``check_phase12_warn_gate`` で計算し・
    §15.2 gate と別キーで併載 (後知恵すり替え禁止)。
    """
    # §15.2 gate (不変・evaluator.check_acceptance_gate をそのまま消費)
    # check_acceptance_gate は (metrics_dict, sum_p_check) の2引数契約 (evaluator.py L888-891)。
    # metrics_dict は {model_name: compute_metrics 戻り値}・sum_p_check は check_sum_p_distribution 戻り値。
    baseline_metrics = _compute_pred_metrics(baseline_pred_df)
    rr_metrics = _compute_pred_metrics(rr_pred_df)

    # check_sum_p_distribution で §15.2 の sum(p) チェックを実施 (evaluator.check_sum_p_distribution)
    from src.model.evaluator import check_sum_p_distribution

    baseline_sum_p_check = check_sum_p_distribution(
        baseline_pred_df, p_col="p_fukusho_hit", entry_count_col="entry_count"
    )
    rr_sum_p_check = check_sum_p_distribution(
        rr_pred_df, p_col="p_fukusho_hit", entry_count_col="entry_count"
    )

    # check_acceptance_gate の signature に従い (metrics_dict, sum_p_check) で呼出 (evaluator.py の契約)。
    # 戻り値の block_triggered / block_reasons / warn_reasons をそのまま §15.2 gate 結果として併載。
    try:
        section_15_2_gate_baseline = check_acceptance_gate(
            {"lightgbm": baseline_metrics},
            baseline_sum_p_check,
        )
        section_15_2_gate_rr = check_acceptance_gate(
            {"lightgbm": rr_metrics},
            rr_sum_p_check,
        )
    except Exception as exc:
        # check_acceptance_gate が引数形式等で失敗する場合は §15.2 gate の本質ではない run script 側の問題・
        # §15.2 gate の定義を run script 側で再定義せず fail-loud (Shared Pattern 4)。
        raise RuntimeError(
            f"_evaluate_gate: evaluator.check_acceptance_gate 呼出失敗・silent fallback 禁止 "
            f"(Shared Pattern 4 / D-06 不変): {exc!r}"
        ) from exc

    # baseline / rr 両方の §15.2 gate 結果を併載 (run script 側で §15.2 gate を再定義しない)
    section_15_2_gate = {
        "baseline": section_15_2_gate_baseline,
        "race_relative": section_15_2_gate_rr,
    }

    # Phase 12 専用 WARN gate (SC#4・check_phase12_warn_gate・§15.2 gate とは完全分離)
    selected_only_calib_max_dev = _compute_selected_only_calib_max_dev(
        rr_pred_df,
        p_col="p_fukusho_hit_lower"
        if "p_fukusho_hit_lower" in rr_pred_df.columns
        else "p_fukusho_hit",
    )
    odds_band_calib_max_dev = _compute_odds_band_calib_max_dev(
        rr_pred_df,
        p_col="p_fukusho_hit_lower"
        if "p_fukusho_hit_lower" in rr_pred_df.columns
        else "p_fukusho_hit",
    )
    phase12_warn = check_phase12_warn_gate(
        selected_only_calib_max_dev=selected_only_calib_max_dev,
        odds_band_calib_max_dev=odds_band_calib_max_dev,
        # 事前登録閾値は falsification.py から import (C-12-04-3)・明示渡しで遅延 import 回避
        selected_only_threshold=PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD,
        odds_band_threshold=PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD,
    )

    # Phase 12 EVAL-01 拡張指標 (§15.2 とは別キーで併載・後知恵すり替え禁止)
    baseline_segments = _safe_evaluate_all_segments(baseline_pred_df)
    rr_segments = _safe_evaluate_all_segments(rr_pred_df)

    return {
        # §15.2 gate 結果 (不変・evaluator.check_acceptance_gate をそのまま消費)
        "section_15_2_gate": _sanitize_for_json(section_15_2_gate),
        "block_triggered": bool(
            section_15_2_gate_baseline.get("block_triggered", False)
            or section_15_2_gate_rr.get("block_triggered", False)
        ),
        "block_reasons": list(section_15_2_gate_baseline.get("block_reasons", []))
        + list(section_15_2_gate_rr.get("block_reasons", [])),
        "warn_reasons": list(section_15_2_gate_baseline.get("warn_reasons", []))
        + list(section_15_2_gate_rr.get("warn_reasons", [])),
        # Phase 12 専用 WARN gate (SC#4・§15.2 gate と別キーで併載・D-06)
        "phase12_warn": _sanitize_for_json(phase12_warn),
        "phase12_warn_triggered": bool(phase12_warn.get("phase12_warn_triggered", False)),
        "phase12_warn_reasons": list(phase12_warn.get("phase12_warn_reasons", [])),
        # Phase 12 EVAL-01 拡張指標 (§15.2 指標と別キーで併載・D-06/D-07)
        "baseline_metrics": _sanitize_for_json(baseline_metrics),
        "rr_metrics": _sanitize_for_json(rr_metrics),
        "baseline_segments_reference": _sanitize_for_json(baseline_segments),
        "rr_segments_reference": _sanitize_for_json(rr_segments),
        # binning 契約の由来 (import 再利用・codex review HIGH#2・bit-identical)
        "binning_source": {
            "CALIBRATION_CURVE_BINS": CALIBRATION_CURVE_BINS,
            "CALIBRATION_CURVE_MIN_BIN_COUNT": CALIBRATION_CURVE_MIN_BIN_COUNT,
            "ODDS_BAND_EDGES": [
                float(x) if math.isfinite(float(x)) else "inf" for x in ODDS_BAND_EDGES
            ],
            "ODDS_BAND_LABELS": list(ODDS_BAND_LABELS),
            "NINKI_BAND_EDGES": [
                float(x) if math.isfinite(float(x)) else "inf" for x in NINKI_BAND_EDGES
            ],
            "note": "§15.2 事前登録指標不変・evaluator/segment_eval から import 再利用 (再定義禁止)",
        },
        # Phase 12 事前登録定数の由来 (falsification.py constants block・C-12-04-3)
        "phase12_constants_source": {
            "Q_LEVEL_SHRINKAGE": Q_LEVEL_SHRINKAGE,
            "Q_LEVEL_FALSIFICATION": Q_LEVEL_FALSIFICATION,
            "HOLM_ALPHA": HOLM_ALPHA,
            "LOGIT_CLIP_EPS": LOGIT_CLIP_EPS,
            "ODDS_CLIP_MIN": ODDS_CLIP_MIN,
            "ODDS_CLIP_MAX": ODDS_CLIP_MAX,
            "MARKET_CALIB_SAMPLE_THRESHOLD": MARKET_CALIB_SAMPLE_THRESHOLD,
            "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD": PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD,
            "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD": PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD,
            "note": "Phase 12 事前登録定数は src/eval/falsification.py constants block から import (重複定義回避)",
        },
    }


# Phase 12 の pred_df (eval コピー) 列構成に合わせた segment 軸 (D-15 参考記録).
# segment_eval.SEGMENT_AXES 既定は Phase 6 feature matrix 向け (race_date/jyocd/entry_count/
# ninki/fukuoddslower) だが・Phase 12 の eval コピーは PREDICTION_COLUMNS + label/odds JOIN 構成で
# race_date (PREDICTION_COLUMNS 補助メタ) / jyocd (PK 系) / entry_count (_ensure_entry_count) /
# fuku_odds_lower (_attach_odds_to_pred) を持ち・ninki / fukuoddslower は持たない。
# よって pred_df の実列に合わせた axes を渡し・WARN skip (segment_eval.py の warnings.warn) を回避する。
# segment_eval.py の既定契約 (y_true_col='fukusho_hit' / SEGMENT_AXES) は Phase 6 保護のため触れない。
_PHASE12_SEGMENT_AXES: dict[str, str] = {
    "year": "race_date",
    "month": "race_date",
    "jyocd": "jyocd",
    "entry_count": "entry_count",
    "odds_band": "fuku_odds_lower",  # SEGMENT_AXES 既定は fukuoddslower・pred_df は fuku_odds_lower
    # ninki: pred_df に ninki 列が無いため除外 (WARN skip 回避・Pitfall 6)
}


def _safe_evaluate_all_segments(pred_df: pd.DataFrame) -> dict[str, Any]:
    """segment_eval.evaluate_all_segments を try/except で呼ぶ (参考記録・gate 継続).

    D-15 参考記録 (gate 判定には使わない)。Phase 12 の eval コピー pred_df の列構成に合わせて
    ``y_true_col='fukusho_hit_validated'`` と :data:`_PHASE12_SEGMENT_AXES` を明示渡す。
    segment_eval.py の既定契約 (``y_true_col='fukusho_hit'`` / :data:`SEGMENT_AXES`) は Phase 6
    保護のため触らない (他フェーズ回帰回避)。旧実装はデフォルト引数で呼び ``fukusho_hit`` 列が
    pred_df に無いため ValueError → WARNING 2行 (baseline/rr) となっていた (本修正の対象)。
    """
    try:
        return evaluate_all_segments(
            pred_df,
            y_true_col="fukusho_hit_validated",
            axes=_PHASE12_SEGMENT_AXES,
        )
    except Exception as e:  # pragma: no cover - 参考記録
        logger.warning("segment_eval 失敗 (参考記録・gate 継続): %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# [C-12-03-1 HIGH] run_falsification_pipeline (train/calib fit → test eval・§11.2 聖域)
# ---------------------------------------------------------------------------
def run_falsification_pipeline(
    *,
    train_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    test_df: pd.DataFrame,
    falsification_spec_path: Path,
) -> dict[str, Any]:
    """falsification pipeline: fit_market_implied_calibrator (train/calib) → run_falsification_test (test).

    §11.2 聖域 (test 窓 sanctuary):
      (1) [C-12-03-1 HIGH] ``falsification_spec_path`` に ``write_falsification_spec`` で
          回帰仕様を test 窓評価前に byte-reproducible に事前書き出し (threshold dredging 監査)。
      (2) [C-12-03-4] ``fit_market_implied_calibrator`` を train/calib 窓のみで fit し (2-window 分離)・
          test 窓 outcome 系引数を取らない (Shared Pattern 6・構造的聖域ブロック)。
      (3) ``run_falsification_test`` を test 窓予測のみで評価 (予測モデル p の再学習を行わない・
          事前登録評価回帰仕様を test 窓に fit する最終検定は許容)。

    Parameters
    ----------
    train_df : pd.DataFrame
        train 窓の DataFrame。必須列: ``fuku_odds_lower``, ``fukusho_hit_validated``。
    calib_df : pd.DataFrame
        calib 窓の DataFrame。必須列: ``fuku_odds_lower``, ``fukusho_hit_validated``。
    test_df : pd.DataFrame
        test 窓の予測 DataFrame。必須列: ``fuku_odds_lower``, ``p_fukusho_hit``, ``race_key``,
        ``fukusho_hit_validated``, ``entry_count`` (field_size 共変量)。
    falsification_spec_path : Path
        ``falsification-spec.json`` の出力 path (test 窓評価前に事前書き出し)。

    Returns
    -------
    dict
        ``run_falsification_test`` の戻り値 (model_p_coef / model_p_pvalue / verdict / Holm 補正後 pvalue)。
    """
    # (1) [C-12-03-1 HIGH] falsification-spec.json を test 窓評価前に事前書き出し (threshold dredging 監査)
    write_falsification_spec(falsification_spec_path)
    logger.info(
        "falsification-spec.json 事前書き出し完了 (test 窓評価前): %s", falsification_spec_path
    )

    # (2) [C-12-03-4] fit_market_implied_calibrator を train/calib 窓のみで fit (2-window 分離)
    odds_train = pd.to_numeric(train_df["fuku_odds_lower"], errors="coerce").to_numpy(dtype=float)
    y_train = train_df["fukusho_hit_validated"].to_numpy(dtype=float)
    odds_calib = pd.to_numeric(calib_df["fuku_odds_lower"], errors="coerce").to_numpy(dtype=float)
    y_calib = calib_df["fukusho_hit_validated"].to_numpy(dtype=float)
    calibrator = fit_market_implied_calibrator(
        odds_train=odds_train,
        y_train=y_train,
        odds_calib=odds_calib,
        y_calib=y_calib,
        calib_sample_size=len(calib_df),
    )

    # (3) test 窓予測のみで評価 (§11.2 聖域・予測モデル p の再学習を行わない)
    # gap-closure: no_bet sentinel (fuku_odds_lower NaN) の馬は市場情報が無く falsification 回帰の
    # 対象外 (market_implied が NaN になり logit で伝播して LogisticRegression/Logit が NaN で失敗)。
    # train/calib と同様に odds 欠損行を除外する (統計的妥当: 市場と比較可能な馬のみで検定)。
    odds_lower_series = pd.to_numeric(test_df["fuku_odds_lower"], errors="coerce")
    usable_mask = odds_lower_series.notna()
    n_test_total = len(test_df)
    n_test_usable = int(usable_mask.sum())
    if n_test_usable == 0:
        raise RuntimeError(
            "run_falsification_pipeline: test_df の全行の fuku_odds_lower が NaN・"
            "falsification 回帰の対象馬が0件 (no_bet sentinel ばかり・JODDS 取得状況を確認)"
        )
    if n_test_usable < n_test_total:
        logger.info(
            "falsification test 窓で odds 欠損行を除外: usable=%d/%d "
            "(no_bet sentinel の馬は市場比較不可・falsification 対象外)",
            n_test_usable,
            n_test_total,
        )
    test_df_usable = test_df.loc[usable_mask].copy()

    odds_test = odds_lower_series.loc[usable_mask].to_numpy(dtype=float)
    odds_test_clipped = np.clip(odds_test, ODDS_CLIP_MIN, ODDS_CLIP_MAX).reshape(-1, 1)
    market_implied_proba = calibrator.predict_proba(odds_test_clipped)[:, 1]
    model_p_test = test_df_usable["p_fukusho_hit"].to_numpy(dtype=float)
    y_outcome_test = test_df_usable["fukusho_hit_validated"].to_numpy(dtype=float)
    race_id_test = test_df_usable["race_key"].to_numpy()
    field_size_test = (
        test_df_usable["entry_count"].to_numpy(dtype=float)
        if "entry_count" in test_df_usable.columns
        else None
    )
    odds_band_test = odds_test  # run_falsification_test が _odds_band で binning

    falsification_result = run_falsification_test(
        y_outcome_test=y_outcome_test,
        market_implied_test=market_implied_proba,
        model_p_test=model_p_test,
        race_id_test=race_id_test,
        field_size_test=field_size_test,
        odds_band_test=odds_band_test,
    )
    return falsification_result


# ---------------------------------------------------------------------------
# D-09 switch_recommendation (SC#4 WARN gate + p_lower EV 比較 + falsification → switch/hold/reject)
# ---------------------------------------------------------------------------
def compute_switch_recommendation(
    *,
    phase12_warn_triggered: bool,
    baseline_recovery_rate: float,
    p_lower_recovery_rate: float,
    falsification_verdict: str,
) -> dict[str, Any]:
    """SC#4 WARN gate + p_lower EV v1.0 binary 回収率比較 + falsification verdict を統合し
    'switch' / 'hold' / 'reject' のいずれかを返す (D-09).

    is_primary DB 変更はしない (D-10)・本関数は判断材料を report に出すのみ。

    Parameters
    ----------
    phase12_warn_triggered : bool
        ``check_phase12_warn_gate`` の ``phase12_warn_triggered`` (True の場合 WARN gate FAIL)。
    baseline_recovery_rate : float
        v1.0 binary (theta=None) の回収率 (purchase_simulator p_min_base='p'・refund_accounting 会計)。
    p_lower_recovery_rate : float
        p_lower (theta=selected・p_min_base='p_lower') の回収率。
    falsification_verdict : str
        ``run_falsification_test`` の verdict ('feature_gap' or 'structural_limit')。

    Returns
    -------
    dict
        ``recommendation`` ('switch' / 'hold' / 'reject') と判断材料の明細。
    """
    # recovery_rate_delta > 0 で EV 改善
    recovery_rate_delta = float(p_lower_recovery_rate) - float(baseline_recovery_rate)
    ev_improved = recovery_rate_delta > 0.0

    # 判定ルール (D-09・CONTEXT.md):
    #   - SC#4 WARN gate FAIL → reject (core value 維持での黒字化困難・market が model を包摂)
    #   - SC#4 WARN gate PASS + EV 改善 + feature_gap → switch (市場 residual が残る・特徴量改善余地あり)
    #   - SC#4 WARN gate PASS + (EV 改善なし または structural_limit) → hold (現状維持・判断材料積み上げ)
    if phase12_warn_triggered:
        recommendation = "reject"
    elif ev_improved and falsification_verdict == "feature_gap":
        recommendation = "switch"
    else:
        recommendation = "hold"

    return {
        "recommendation": recommendation,
        "inputs": {
            "phase12_warn_triggered": bool(phase12_warn_triggered),
            "baseline_recovery_rate": float(baseline_recovery_rate),
            "p_lower_recovery_rate": float(p_lower_recovery_rate),
            "recovery_rate_delta": recovery_rate_delta,
            "ev_improved": bool(ev_improved),
            "falsification_verdict": str(falsification_verdict),
        },
        "rules": {
            "reject": "SC#4 WARN gate FAIL → core value 維持での黒字化困難 (market が model を包摂)",
            "switch": "SC#4 PASS + EV 改善 + feature_gap → 市場 residual が残る (特徴量改善余地あり)",
            "hold": "SC#4 PASS + (EV 改善なし または structural_limit) → 現状維持 (判断材料積み上げ)",
        },
        "d10_note": (
            "switch_recommendation は判断材料を report に出すのみ (D-09)・"
            "is_primary DB 変更は人間承認の別アクション (D-10・set_primary_model を呼ばない・AST check 0件)"
        ),
    }


# ---------------------------------------------------------------------------
# _compute_recovery_rate (purchase_simulator + refund_accounting・純粋関数)
# ---------------------------------------------------------------------------
def _compute_recovery_rate(
    pred_df: pd.DataFrame,
    *,
    p_col: str,
    p_min_base: str,
) -> float:
    """purchase_simulator.select_bets + refund_accounting で回収率を計算する (純粋関数).

    本関数は ev_rank.compute_ev_and_rank + purchase_simulator.select_bets + refund_accounting
    を chain し・§11.6 回収率を返す (ゼロ除算回避・§8.3)。odds 列が無い場合は NaN (D-15 参考記録)。

    Parameters
    ----------
    pred_df : pd.DataFrame
        baseline または rr の prediction DataFrame。
    p_col : str
        ``compute_ev_and_rank`` の EV 計算に使う確率列 ('p_fukusho_hit' or 'p_fukusho_hit_lower')。
    p_min_base : str
        ``select_bets`` の p_min 適用先 ('p' or 'p_lower')。
    """
    from src.ev.ev_rank import compute_ev_and_rank
    from src.ev.purchase_simulator import select_bets
    from src.ev.refund_accounting import determine_stake_payout

    required = {
        "race_key",
        "umaban",
        p_col,
        "fuku_odds_lower",
        "is_fukusho_sale_available",
        "is_model_eligible",
    }
    if not required.issubset(pred_df.columns):
        missing = required - set(pred_df.columns)
        logger.warning("_compute_recovery_rate: 必須列欠損 %s・NaN を返す (D-15 参考記録)", missing)
        return float("nan")

    ranked = compute_ev_and_rank(pred_df, p_col=p_col)
    selected = select_bets(ranked, p_col=p_col, p_min_base=p_min_base)
    if len(selected) == 0:
        return 0.0
    # refund_accounting.determine_stake_payout で effective_stake / payout を計算
    # (P1 fix) determine_stake_payout の戻り値キーは 'payout' (refund_accounting.py L103/171-178)。
    # 旧コードは 'payout_amount' を参照しキー不一致で常に 0.0 → recovery_rate が常に 0.0 になっていた。
    payout_total = 0.0
    stake_total = 0.0
    for _, row in selected.iterrows():
        result = determine_stake_payout(row)
        payout_total += float(result.get("payout", 0.0))
        stake_total += float(result.get("effective_stake", 0.0))
    if stake_total <= 0.0:
        return 0.0
    return payout_total / stake_total


# ---------------------------------------------------------------------------
# main — live-DB orchestration (KEIBA_SKIP_DB_TESTS unset で実行)
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """live-DB で Phase 12 統合評価を実行する (SC#1-5・EV-01・EVAL-01・EVAL-02・SAFE-01).

    手順 (§11.2 聖域の機械保証):
      (1) ``orchestrator.train_and_predict(score_split='calib', theta=selected_theta)`` で
          calib slice の予測を取得 (codex HIGH#1・score_split guard L449-455 が test 窓に触れない)。
      (2) [C-12-04-1 HIGH] calib slice の pred_proba と y_calib を race_key+umaban fail-loud key-join で
          整列し ``_compute_q_shrink_on_calib`` で q_shrink を計算 (§11.2 聖域)。
      (3) [C-12-04-1 HIGH] ``q_shrink.json`` を test 窓評価前に byte-reproducible に事前書き出し。
      (4) [C-12-04-2 HIGH] ``orchestrator.train_and_predict(score_split='test', theta=selected_theta,
          p_lower_q_shrink=<calibで計算した値>)`` で calib 済み q_shrink を注入し test 窓 p_lower を生成。
      (5) [C-12-03-1 HIGH] ``falsification-spec.json`` を ``run_falsification_pipeline`` の
          test 窓評価前に事前書き出し・fit_market_implied_calibrator (train/calib) →
          run_falsification_test (test) で falsification 実施。
      (6) ``_evaluate_gate`` で §15.2 gate (不変) と Phase 12 WARN gate (D-06) を併載評価。
      (7) ``compute_switch_recommendation`` で switch/hold/reject を report に出す (D-09)。
      (8) reports/12-evaluation/ の 8 ファイルを byte-reproducible に atomic write (SC#5・§19.1)。

    REVIEW H6: load_feature_matrix → load_labels → build_training_frame → load_frozen_maps →
    orchestrator.train_and_predict の正しい API chain を呼ぶ (run_phase11 idiom)。
    [C-12-04-4] load_predictions public wrapper を呼び SC#5 idempotent swap を実施
    (Phase 11 docstring の「load_predictions を呼ばない」誤りを踏襲せず・実際は呼ぶ)。
    [C-12-04-5] migration (PREDICTION_ADD_P_LOWER_SQL) は run_apply_schema.py (owner/admin 権限) に
    一本化し・本 script からは実行しない (Phase 11 L286-290 idiom と同一)。
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
    eval_dir = out_dir / "12-evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    # T-09-21: statement_timeout='30s' で重クエリの orphan CPU 張り付き防止
    # (MEMORY.md subagent-db-query-statement-timeout・run_phase11_evaluation.py L271-280 idiom)
    readonly_pool = make_pool(settings, role="readonly", configure=_configure_statement_timeout)
    # 永続化パス用 etl pool (load_predictions 呼出用・Phase 11 codex HIGH#3/#4 と同一)
    etl_pool = make_pool(settings, role="etl", configure=_configure_statement_timeout)
    try:
        # [C-12-04-5 HIGH] migration (PREDICTION_ADD_P_LOWER_SQL・Plan 01 で src/db/schema.py に追加済み)
        # は run_apply_schema.py (owner/admin 権限・`uv run python scripts/run_apply_schema.py`) で
        # 事前適用済みであることを前提 (Phase 6 / Phase 11 idiom と同一・memory: migration-privilege-admin-required)。
        # ALTER TABLE は owner 権限が必要で etl ロールでは InsufficientPrivilege となるため・本 script では
        # migration を実行せず run_apply_schema.py に一本化 (Phase 11 L286-290 idiom と同一)。

        with readonly_cursor(readonly_pool) as cur:
            # 二重防衛: configure callback と cursor 内 SET の両方で statement_timeout を設定
            cur.execute("SET statement_timeout = '30s'")

            # REVIEW H6: feature_df ロード
            logger.info("loading snapshot: %s", args.baseline_snapshot_id)
            feature_df = load_feature_matrix(snapshot_id=args.baseline_snapshot_id)
            label_df = load_labels(cur)
            frame = build_training_frame(feature_df, label_df)
            cat_map = load_frozen_maps(snapshot_id=args.baseline_snapshot_id)
            logger.info("category_map keys: %d", len(cat_map) if isinstance(cat_map, dict) else -1)

        # ---- (1) calib slice の予測 (score_split='calib'・§11.2 聖域の機械保証) ----
        selected_theta = float(args.selected_theta)
        rr_model_version = make_model_version(args.baseline_snapshot_id, "lightgbm_rr", 1)
        logger.info(
            "calib slice 予測 (score_split='calib'・theta=%s)・q_shrink 計算用",
            selected_theta,
        )
        rr_calib_result = train_and_predict(
            frame,
            model_type="lightgbm_rr",
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            version_n=1,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=selected_theta,
            score_split="calib",
            as_of_datetime=FIXED_REPRODUCE_TS,
            label_version="v1.0",
            odds_snapshot_policy=args.odds_snapshot_policy,
            backtest_strategy_version=args.bt_split,
        )
        rr_calib_pred = _attach_label_to_pred(rr_calib_result["pred_df"], label_joined_frame=frame)
        calib_y_df = rr_calib_pred[["race_key", "umaban", "fukusho_hit_validated"]].copy()

        # ---- (2)(3) [C-12-04-1 HIGH] q_shrink 計算 (calib slice のみ) と q_shrink.json 事前書き出し ----
        q_shrink_path = eval_dir / "q_shrink.json"
        _write_q_shrink_json(
            q_shrink_path,
            calib_pred_df=rr_calib_pred,
            y_calib_df=calib_y_df,
            q_level=Q_LEVEL_SHRINKAGE,
        )
        q_shrink_value = float(json.loads(q_shrink_path.read_text(encoding="utf-8"))["q_shrink"])
        logger.info(
            "q_shrink.json 事前書き出し完了 (test 窓評価前): q_shrink=%.6f / q_level=%.2f",
            q_shrink_value,
            Q_LEVEL_SHRINKAGE,
        )

        # ---- (4) [C-12-04-2 HIGH] test 窓 p_lower 生成 (calib 済み q_shrink を外部注入) ----
        logger.info(
            "test 窓予測 (score_split='test'・theta=%s・p_lower_q_shrink=%.6f・C-12-04-2 HIGH)",
            selected_theta,
            q_shrink_value,
        )
        rr_test_result = train_and_predict(
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
            p_lower_q_shrink=q_shrink_value,  # [C-12-04-2] 唯一の受取経路
        )

        # ---- baseline (theta=None v1.0 binary)・test 窓評価 ----
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

        # ---- SC#3 deterministic smoke (同一 rr model で bit-identical) ----
        _assert_deterministic(
            "lightgbm_rr",
            frame,
            feature_snapshot_id=args.baseline_snapshot_id,
            snapshot_id=args.baseline_snapshot_id,
            split_periods=BT1_PERIODS,
            category_map=cat_map,
            theta=selected_theta,
            p_lower_q_shrink=q_shrink_value,  # Phase 12 C-12-02-1: rr test-window smoke に実 q_shrink を注入 (聖域ガード充足)
            label_version="v1.0",
            odds_snapshot_policy=args.odds_snapshot_policy,
            backtest_strategy_version=args.bt_split,
        )
        logger.info("SC#3 deterministic smoke: PASS (bit-identical)")

        # ---- [C-12-04-4] SC#5 idempotent swap via load_predictions (public wrapper) ----
        # Phase 11 docstring の「load_predictions を呼ばない」誤りを踏襲せず・本 script は呼ぶ (C-12-04-4)。
        logger.info(
            "SC#5 idempotent swap: model_type=lightgbm_rr model_version=%s (load_predictions public wrapper)",
            rr_model_version,
        )
        with etl_pool.connection() as etl_conn:
            with etl_conn.cursor() as etl_cur:
                etl_cur.execute("SET statement_timeout = '30s'")
                checksum1 = load_predictions(
                    etl_cur, rr_test_result["pred_df"], reader_role=settings.db_reader_role
                )
                checksum2 = load_predictions(
                    etl_cur, rr_test_result["pred_df"], reader_role=settings.db_reader_role
                )
            etl_conn.commit()
        if checksum1 != checksum2:
            raise RuntimeError(
                f"SC#5 idempotent violation: 2回実行で checksum 不一致 "
                f"(as_of_datetime=FIXED_REPRODUCE_TS 固定) "
                f"checksum1={checksum1!r} checksum2={checksum2!r}"
            )
        logger.info("SC#5 idempotent swap: PASS (checksum bit-identical=%s)", checksum1)

        # ---- label JOIN ----
        baseline_pred = _attach_label_to_pred(baseline_result["pred_df"], label_joined_frame=frame)
        rr_pred = _attach_label_to_pred(rr_test_result["pred_df"], label_joined_frame=frame)

        # ---- [gap-closure] JODDS odds JOIN (eval コピーのみ・SAFE-01 聖域) ----
        # gap-closure bug #2 の根治: falsification / _compute_recovery (EV) /
        # _compute_odds_band_calib_max_dev (SC#4 gate) / switch_recommendation が odds を必要とする。
        # run_backtest.py L575-600 の PROVEN pattern で JODDS を test 窓期間のみ fetch し・
        # eval コピー (baseline_pred / rr_pred) に merge する。
        # rr_test_result["pred_df"] / baseline_result["pred_df"] は触れない (SC#5 idempotent swap 用・
        # PREDICTION_COLUMNS 20-col 維持・load_predictions が PREDICTION_COLUMNS のみ抽出)。
        test_years = _derive_test_years(BT1_PERIODS)
        logger.info(
            "[gap-closure] JODDS fetch 開始: test_years=%s policy=%s (falsification/EV/SC#4 gate 用)",
            test_years,
            args.odds_snapshot_policy,
        )
        with readonly_cursor(readonly_pool) as jodds_cur:
            # test 窓 1 年の JODDS fetch は数百万行・readonly cursor で SELECT-only。
            # pool の既定 statement_timeout='30s' だとサーバー側実行が長引いた場合に QueryCanceled
            # になるため・本 fetch スコープのみ '600s' に延長 (documented rationale は
            # _build_falsification_windows と同一・SELECT-only で副作用なし)。
            jodds_cur.execute("SET statement_timeout = '600s'")
            jodds_df = fetch_jodds(jodds_cur, years=test_years)
            # [gap-closure] HARAI 払戻 slot (recovery_rate 正常化用): n_harai test 1年は軽量
            # (数万行) なので・JODDS の 600s から 30s に戻して取得 (同一 cursor・SELECT-only)。
            jodds_cur.execute("SET statement_timeout = '30s'")
            harai_race_df = _fetch_harai_race_level(jodds_cur, years=test_years)
        logger.info(
            "[gap-closure] JODDS fetch 完了: rows=%d (test 期間のみ・全期間取得回避)",
            len(jodds_df),
        )
        baseline_pred = _attach_odds_to_pred(
            baseline_pred,
            jodds_df=jodds_df,
            odds_snapshot_policy=args.odds_snapshot_policy,
            caller_label="baseline",
        )
        rr_pred = _attach_odds_to_pred(
            rr_pred,
            jodds_df=jodds_df,
            odds_snapshot_policy=args.odds_snapshot_policy,
            caller_label="race_relative",
        )
        # gap-closure bug #1 の根治: check_sum_p_distribution / falsification field_size 共変量が
        # 必須とする entry_count を sales_start_entry_count 等から確保 (eval コピーのみ)。
        baseline_pred = _ensure_entry_count(baseline_pred, caller_label="baseline")
        rr_pred = _ensure_entry_count(rr_pred, caller_label="race_relative")
        n_odds_baseline = int(baseline_pred["fuku_odds_lower"].notna().sum())
        n_odds_rr = int(rr_pred["fuku_odds_lower"].notna().sum())
        logger.info(
            "[gap-closure] odds JOIN 完了: baseline usable_odds=%d/%d rr usable_odds=%d/%d "
            "(usable = fuku_odds_lower not NaN・no_bet sentinel は NaN 化済み)",
            n_odds_baseline,
            len(baseline_pred),
            n_odds_rr,
            len(rr_pred),
        )

        # [gap-closure] HARAI 払戻 slot JOIN (eval コピーのみ・recovery_rate 正常化)
        # determine_stake_payout → _lookup_payfukusyo_pay が payfukusyoumaban*/payfukusyopay*
        # /fuseirituflag2/tokubaraiflag2 を消費 (本 JOIN が無いと payout=0 → recovery=0.0)。
        baseline_pred = _attach_harai_to_pred(
            baseline_pred, harai_race_df=harai_race_df, caller_label="baseline"
        )
        rr_pred = _attach_harai_to_pred(
            rr_pred, harai_race_df=harai_race_df, caller_label="race_relative"
        )
        logger.info(
            "[gap-closure] HARAI 払戻 JOIN 完了: harai races=%d (recovery_rate 正常化用)",
            len(harai_race_df),
        )

        # ---- (5) [C-12-03-1 HIGH] falsification pipeline (falsification-spec.json 事前書き出し含む) ----
        # [gap-closure] falsification の fit_market_implied_calibrator は train/calib 窓の
        # fuku_odds_lower + fukusho_hit_validated を必要とするが・frame (FEATURE_COLUMNS 由来) は
        # odds-free (D-07/§13.4)。よって frame の train/calib slice を取り出し・JODDS odds を付与した
        # eval 専用 df を構築する (SAFE-01: feature 構築経路でなく evaluation 専用層の境界)。
        # train/calib 窓の年も fetch する (test 窓と合わせて JODDS を取得)。
        falsification_train_df, falsification_calib_df = _build_falsification_windows(
            frame=frame,
            split_periods=BT1_PERIODS,
            readonly_pool=readonly_pool,
            odds_snapshot_policy=args.odds_snapshot_policy,
        )
        falsification_spec_path = eval_dir / "falsification-spec.json"
        falsification_result = _safe_run_falsification_pipeline(
            train_df=falsification_train_df,
            calib_df=falsification_calib_df,
            test_pred_df=rr_pred,
            falsification_spec_path=falsification_spec_path,
        )

        # ---- (6) gate 評価 (§15.2 gate 不変 + Phase 12 WARN gate 併載) ----
        gate_result = _evaluate_gate(
            baseline_pred_df=baseline_pred,
            rr_pred_df=rr_pred,
        )

        # ---- 回収率 (purchase_simulator + refund_accounting) ----
        baseline_recovery = _compute_recovery_rate(
            baseline_pred, p_col="p_fukusho_hit", p_min_base="p"
        )
        p_lower_recovery = _compute_recovery_rate(
            rr_pred, p_col="p_fukusho_hit_lower", p_min_base="p_lower"
        )

        # ---- (7) switch_recommendation (D-09) ----
        switch_rec = compute_switch_recommendation(
            phase12_warn_triggered=gate_result["phase12_warn_triggered"],
            baseline_recovery_rate=baseline_recovery,
            p_lower_recovery_rate=p_lower_recovery,
            falsification_verdict=(
                falsification_result.get("verdict", "structural_limit")
                if falsification_result
                else "structural_limit"
            ),
        )

        # ---- (8) reports/12-evaluation/ の 8 ファイルを byte-reproducible に atomic write ----
        _write_reports(
            eval_dir,
            gate_result=gate_result,
            falsification_result=falsification_result,
            switch_recommendation=switch_rec,
            q_shrink_value=q_shrink_value,
            args=args,
            rr_model_version=rr_model_version,
            baseline_recovery=baseline_recovery,
            p_lower_recovery=p_lower_recovery,
        )
    finally:
        readonly_pool.close()
        etl_pool.close()

    logger.info("Phase 12 evaluation reports 書き出し完了: %s", eval_dir)
    return 0


def _safe_run_falsification_pipeline(
    *,
    train_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    test_pred_df: pd.DataFrame,
    falsification_spec_path: Path,
) -> dict[str, Any] | None:
    """``run_falsification_pipeline`` を try/except で呼ぶ (falsification 失敗時は None・report に明記).

    [gap-closure] 呼出側が odds-enriched な train_df / calib_df (JODDS fuku_odds_lower +
    fukusho_hit_validated 付き) と test_pred_df (odds-enriched eval コピー) を明示的に渡す形に変更。
    旧実装は frame から train/calib を切り出していたが・frame は FEATURE_COLUMNS 由来で odds 列を
    持たない (D-07/§13.4 odds-free allowlist) ため・falsification が必ず WARNING skip されていた
    (gap-closure bug #2 の副次症状)。SAFE-01: odds は evaluation 専用層の境界 (falsification.py 内
    SAFE-01-ALLOW 注記)・feature 構築経路から切り離されている。

    falsification-spec.json の事前書き出しは ``run_falsification_pipeline`` 内で実行されるため・
    仮に回帰 fit が失敗した場合でも spec は事前書き出しされた状態を保つ (C-12-03-1 HIGH 監査証跡)。
    falsification に必要な odds 列 (fuku_odds_lower) が test_pred_df に無い場合は None を返す
    (D-15 参考記録・gate 継続)。
    """
    if "fuku_odds_lower" not in test_pred_df.columns or "p_fukusho_hit" not in test_pred_df.columns:
        logger.warning(
            "falsification: test_pred_df に fuku_odds_lower / p_fukusho_hit が無い・skip (D-15 参考記録)"
        )
        # それでも falsification-spec.json だけは事前書き出しして監査証跡を残す (C-12-03-1)
        write_falsification_spec(falsification_spec_path)
        return None

    # 必須列の存在確認 (train/calib は呼出側が odds-enriched で渡した前提)
    for df, name in ((train_df, "train"), (calib_df, "calib")):
        if "fuku_odds_lower" not in df.columns or "fukusho_hit_validated" not in df.columns:
            logger.warning(
                "falsification: %s 窓に fuku_odds_lower / fukusho_hit_validated が無い・skip (D-15)",
                name,
            )
            write_falsification_spec(falsification_spec_path)
            return None

    try:
        return run_falsification_pipeline(
            train_df=train_df,
            calib_df=calib_df,
            test_df=test_pred_df,
            falsification_spec_path=falsification_spec_path,
        )
    except Exception as exc:  # pragma: no cover - live-DB 依存・unit test では経路未到達
        logger.warning("falsification pipeline 失敗 (D-15 参考記録・gate 継続): %s", exc)
        return None


# ---------------------------------------------------------------------------
# reports/12-evaluation/ 書き出し (8 ファイル・byte-reproducible)
# ---------------------------------------------------------------------------
def _write_reports(
    eval_dir: Path,
    *,
    gate_result: dict[str, Any],
    falsification_result: dict[str, Any] | None,
    switch_recommendation: dict[str, Any],
    q_shrink_value: float,
    args: argparse.Namespace,
    rr_model_version: str,
    baseline_recovery: float,
    p_lower_recovery: float,
) -> None:
    """reports/12-evaluation/ の 8 ファイルを byte-reproducible に atomic write する.

    8 ファイル:
      - 12-evaluation.md / 12-evaluation.json (§15.2 gate + Phase 12 拡張指標の併載・D-06/D-07)
      - falsification.md / falsification.json (model_p coef/pvalue/verdict・Holm 補正)
      - falsification-spec.json (回帰仕様事前書き出し・C-12-03-1・run_falsification_pipeline で既出)
      - switch-recommendation.md / switch-recommendation.json (switch/hold/reject・D-09)
      - q_shrink.json (q_level/q_shrink 実数値・D-02・_write_q_shrink_json で既出)

    ※ falsification-spec.json / q_shrink.json は main() の手順 (3)(5) で既に事前書き出しされている。
    本関数は残りの 6 ファイルを書き出す。
    """
    eval_dir.mkdir(parents=True, exist_ok=True)

    # 12-evaluation.json / .md
    eval_payload = {
        "phase": 12,
        "gate": gate_result,
        "switch_recommendation": switch_recommendation,
        "recovery_rates": {
            "baseline_v1_0_binary": float(baseline_recovery)
            if not math.isnan(baseline_recovery)
            else None,
            "p_lower": float(p_lower_recovery) if not math.isnan(p_lower_recovery) else None,
        },
        "q_shrink": float(q_shrink_value),
        "q_level": Q_LEVEL_SHRINKAGE,
        "args": {
            "baseline_snapshot_id": args.baseline_snapshot_id,
            "bt_split": args.bt_split,
            "odds_snapshot_policy": args.odds_snapshot_policy,
            "selected_theta": args.selected_theta,
        },
        "rr_model_version": rr_model_version,
    }
    _atomic_write_text(
        eval_dir / "12-evaluation.json",
        json.dumps(
            _sanitize_for_json(eval_payload),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
    )
    _atomic_write_text(
        eval_dir / "12-evaluation.md",
        _format_evaluation_markdown(eval_payload),
    )

    # falsification.json / .md (falsification_result が None の場合は skip 明記)
    falsification_payload = {
        "phase": 12,
        "falsification_result": _sanitize_for_json(falsification_result),
        "skipped_reason": (
            None
            if falsification_result is not None
            else "fuku_odds_lower / split 列不足 (D-15 参考記録)"
        ),
    }
    _atomic_write_text(
        eval_dir / "falsification.json",
        json.dumps(
            _sanitize_for_json(falsification_payload),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
    )
    _atomic_write_text(
        eval_dir / "falsification.md",
        _format_falsification_markdown(falsification_payload),
    )

    # switch-recommendation.json / .md
    _atomic_write_text(
        eval_dir / "switch-recommendation.json",
        json.dumps(
            _sanitize_for_json(switch_recommendation),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
    )
    _atomic_write_text(
        eval_dir / "switch-recommendation.md",
        _format_switch_recommendation_markdown(switch_recommendation),
    )


def _format_evaluation_markdown(payload: dict[str, Any]) -> str:
    """12-evaluation.md の Markdown を構築する."""
    lines: list[str] = []
    lines.append("# Phase 12 p_lower EV + Falsification 統合評価")
    lines.append("")
    lines.append("## Gate Verdict (§15.2 gate 不変 + Phase 12 WARN gate 併載)")
    lines.append("")
    gate = payload.get("gate", {})
    lines.append(f"- §15.2 gate (block_triggered): {gate.get('block_triggered')}")
    lines.append(
        f"- Phase 12 WARN gate (phase12_warn_triggered): {gate.get('phase12_warn_triggered')}"
    )
    if gate.get("phase12_warn_triggered"):
        for reason in gate.get("phase12_warn_reasons", []):
            lines.append(f"  - {reason}")
    lines.append("")
    lines.append("## 回収率 (purchase_simulator + refund_accounting)")
    lines.append("")
    rr = payload.get("recovery_rates", {})
    lines.append(f"- baseline (v1.0 binary): {rr.get('baseline_v1_0_binary')}")
    lines.append(f"- p_lower: {rr.get('p_lower')}")
    lines.append("")
    lines.append("## q_shrink (calib slice のみ・§11.2 聖域)")
    lines.append("")
    lines.append(f"- q_level: {payload.get('q_level')}")
    lines.append(f"- q_shrink: {payload.get('q_shrink')}")
    lines.append("")
    lines.append("## switch_recommendation (D-09・判断材料・実行でない)")
    lines.append("")
    sr = payload.get("switch_recommendation", {})
    lines.append(f"- recommendation: **{sr.get('recommendation')}**")
    lines.append("")
    return "\n".join(lines)


def _format_falsification_markdown(payload: dict[str, Any]) -> str:
    """falsification.md の Markdown を構築する."""
    lines: list[str] = []
    lines.append("# Phase 12 EVAL-02 Falsification Test (事前登録評価回帰・D-05)")
    lines.append("")
    result = payload.get("falsification_result")
    if result is None:
        lines.append(f"**SKIPPED**: {payload.get('skipped_reason')} (D-15 参考記録・gate 継続)")
        return "\n".join(lines)
    lines.append(f"- model_p_coef: {result.get('model_p_coef')}")
    lines.append(f"- model_p_pvalue: {result.get('model_p_pvalue')}")
    lines.append(f"- model_p_significant: {result.get('model_p_significant')}")
    lines.append(f"- verdict: **{result.get('verdict')}**")
    lines.append(f"- alpha: {result.get('alpha')}")
    lines.append(f"- holm_alpha: {result.get('holm_alpha')}")
    lines.append("")
    sub = result.get("sub_analyses_odds_band", {})
    if sub:
        lines.append("## odds_band サブ解析 (Holm 補正)")
        lines.append("")
        lines.append("| band | coef | raw_p | corrected_p | sig_after_holm |")
        lines.append("|------|------|-------|------------|----------------|")
        for band, stats in sub.items():
            lines.append(
                f"| {band} | {stats.get('coef')} | {stats.get('pvalue')} | "
                f"{stats.get('corrected_pvalue')} | {stats.get('significant_after_holm')} |"
            )
        lines.append("")
    return "\n".join(lines)


def _format_switch_recommendation_markdown(sr: dict[str, Any]) -> str:
    """switch-recommendation.md の Markdown を構築する."""
    lines: list[str] = []
    lines.append("# Phase 12 switch_recommendation (D-09)")
    lines.append("")
    lines.append(f"## Recommendation: **{sr.get('recommendation')}**")
    lines.append("")
    inputs = sr.get("inputs", {})
    lines.append("## 統合材料")
    lines.append("")
    lines.append(f"- phase12_warn_triggered: {inputs.get('phase12_warn_triggered')}")
    lines.append(f"- baseline_recovery_rate: {inputs.get('baseline_recovery_rate')}")
    lines.append(f"- p_lower_recovery_rate: {inputs.get('p_lower_recovery_rate')}")
    lines.append(f"- recovery_rate_delta: {inputs.get('recovery_rate_delta')}")
    lines.append(f"- ev_improved: {inputs.get('ev_improved')}")
    lines.append(f"- falsification_verdict: {inputs.get('falsification_verdict')}")
    lines.append("")
    rules = sr.get("rules", {})
    lines.append("## 判定ルール")
    lines.append("")
    for k, v in rules.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## D-10 (人間承認の別アクション)")
    lines.append("")
    lines.append(f"- {sr.get('d10_note', '')}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    raise SystemExit(main())
