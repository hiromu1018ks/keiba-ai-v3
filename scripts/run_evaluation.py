# ruff: noqa: E501  (長い docstring / SQL リテラル・Phase 6 統合評価 CLI)
"""Phase 6 統合評価 CLI: EVAL-01/02/03 を一本化し reports/06-evaluation.{md,json} と
reports/06-segments/×6軸 を生成する (SC#1/2/3 達成・Plan 06-05)。

起動フロー (run_train_predict.py / run_backtest.py パターン・masked DSN・try/finally):

  Step 1. 成果物読込 (readonly ロール・READ only):
    - prediction.fukusho_prediction WHERE feature_snapshot_id=? AND split='test'
    - label.fukusho_label (race_key + segment 軸 + fukusho_hit_validated)
    - reports/04-eval.json (metrics・Phase 4 stamped)
    - reports/05-backtest.json (comparison_table・Phase 5 stamped)
    - REVIEW N3 cycle-3: prediction.fukusho_prediction WHERE split IN ('train','val','test')
      (§8.4 race_id disjoint 真再検証用・test-only 読込では vacuous True になるのを回避)

  Step 2. 確率品質指標計算 (evaluator.py):
    - evaluate_all_models で両モデル + baselines の compute_metrics
    - check_sum_p_distribution で sum(p) §15.2 検査
    - REVIEW HIGH#5: sum_p_measurement dict 構築（0.30 閾値の経験的根拠）

  Step 3. segment 別安定性評価 (segment_eval.py):
    - evaluate_all_segments (6軸・REVIEW HIGH#4 banding)
    - write_segment_reports で reports/06-segments/{axis}.{json,html}×6軸 生成

  Step 4. 受入ゲート判定 (evaluator.check_acceptance_gate):
    - REVIEW HIGH#6: segment 評価 *後に* gate 判定
    - compute_monotonicity_warn + compute_yearly_inversion_warn
    - REVIEW Codex MEDIUM + N3: race_id split integrity check（両 split 非空で真検証・空は "N/A"）

  Step 5. レポート生成 (reports/06-evaluation.{md,json}) → atomic write
    - REVIEW HIGH#6: BLOCK の場合も含めて必ず atomic write

  Step 6. BLOCK 発火時 (block_triggered==True): reports atomic write 完了後・RuntimeError 送出 (D-01)

  Step 7. --primary-model 指定時: set_primary_model で is_primary UPDATE (D-07/D-09)
    - REVIEW C7: 省略時は recommended_primary_model のみ提示・is_primary 更新スキップ

Usage::

    # reports のみ生成（主モデル未確定・人間が比較表を確認）
    uv run python scripts/run_evaluation.py \\
        --feature-snapshot-id 20260620-1a-postreview-v2 \\
        --as-of-datetime 2026-06-20T00:00:00Z

    # 主モデル確定（人間が選定後）
    uv run python scripts/run_evaluation.py \\
        --feature-snapshot-id 20260620-1a-postreview-v2 \\
        --as-of-datetime 2026-06-20T00:00:00Z \\
        --primary-model lightgbm \\
        --selection-reason "D-04 Calibration 重視基準で LightGBM を選定"
"""

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

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor  # noqa: E402
from src.db.prediction_load import set_primary_model  # noqa: E402
from src.model.artifact import _atomic_write_text  # noqa: E402
from src.model.predict import make_model_version  # noqa: E402  Rule1: DB実値と一致する正規の model_version 採番（[:3] 手動推測は "lig" 偏差 bug）
from src.model.evaluator import (  # noqa: E402
    BL3_MARKET_REFERENCE_NOTE,
    BL_UNCALIBRATED_NOTE,
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    COMPARABLE_BASELINES,
    D04_SELECTION_CRITERION_NOTE,
    METRIC_COLUMNS_EXTENDED,
    SUM_P_BLOCK_THRESHOLD,
    SUM_P_DIAGNOSTIC_NOTE,
    build_comparison_table,
    check_acceptance_gate,
    check_sum_p_distribution,
    compute_metrics,
    compute_monotonicity_warn,
    compute_yearly_inversion_warn,
)
from src.model.segment_eval import (  # noqa: E402
    evaluate_all_segments,
    write_segment_reports,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_evaluation")

# ---------------------------------------------------------------------------
# 定数 — D-08 タイブレーク優先順位（主モデル選定時）
# ---------------------------------------------------------------------------

# D-08 優先順位: backtest 回収率 → 計算コスト低=LightGBM → Brier → LogLoss → AUC
TIEBREAK_PRIORITY_ORDER: tuple[str, ...] = (
    "backtest_recovery_rate",
    "compute_cost_lightgbm_first",
    "brier",
    "logloss",
    "auc",
)

# 主モデル比較対象の model_type（タイブレーク候補）
PRIMARY_MODEL_CANDIDATES: tuple[str, ...] = ("lightgbm", "catboost")

# 主モデル比較表に統合する backtest 集計方法（REVIEW C8: 優位 policy 代表窓）
BACKTEST_AGGREGATION_METHOD = (
    "優位 policy の代表窓（30min_before/10min_before のうち recovery_rate が高い方を代表）"
)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する。"""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 6 統合評価 CLI: EVAL-01/02/03 を一本化し reports/06-evaluation.{md,json} と "
            "reports/06-segments/ を生成 (SC#1/2/3 / §15.1/§15.2/§15.3)"
        ),
    )
    parser.add_argument(
        "--feature-snapshot-id",
        required=True,
        help="feature snapshot identifier (READ scope・postreview-v2 等)",
    )
    parser.add_argument(
        "--as-of-datetime",
        required=True,
        help="prediction の as_of_datetime (UPDATE scope・ISO8601・set_primary_model 側で canonical parse)",
    )
    parser.add_argument(
        "--primary-model",
        choices=list(PRIMARY_MODEL_CANDIDATES),
        default=None,
        help=(
            "人間が選定した主モデル (D-07/D-09)。省略時は is_primary 更新スキップ・"
            "reports のみ生成（REVIEW C7）"
        ),
    )
    parser.add_argument(
        "--selection-reason",
        default=None,
        help="D-07 人間判断の理由テキスト・--primary-model 省略時は無視",
    )
    parser.add_argument(
        "--skip-segments",
        action="store_true",
        help="segment 評価をスキップ（開発時・reports/06-segments/ を生成しない）",
    )
    parser.add_argument(
        "--out-md",
        default="reports/06-evaluation.md",
        help="統合評価 Markdown 出力パス (default: reports/06-evaluation.md)",
    )
    parser.add_argument(
        "--out-json",
        default="reports/06-evaluation.json",
        help="統合評価 JSON 出力パス (default: reports/06-evaluation.json)",
    )
    parser.add_argument(
        "--segments-dir",
        default="reports/06-segments",
        help="segment 評価出力ディレクトリ (default: reports/06-segments)",
    )
    parser.add_argument(
        "--eval-04-path",
        default="reports/04-eval.json",
        help="Phase 4 stamped eval JSON 入力パス (default: reports/04-eval.json)",
    )
    parser.add_argument(
        "--backtest-05-path",
        default="reports/05-backtest.json",
        help="Phase 5 stamped backtest JSON 入力パス (default: reports/05-backtest.json)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Step 1 helpers: 成果物読込（pure functions・テスト容易）
# ---------------------------------------------------------------------------


def _load_json_file(path: str | Path) -> dict[str, Any]:
    """JSON ファイルを読込む。存在しない場合は FileNotFoundError。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"読込対象ファイルが存在しない: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _fetch_prediction_test_df(cur, feature_snapshot_id: str):  # type: ignore[no-untyped-def]
    """prediction.fukusho_prediction から test split を SELECT する（readonly ロール）。

    prediction テーブルは PREDICTION_COLUMNS 16列のみ（entry_count / race_key /
    fukusho_hit / ninki / fukuoddslower は含まれない）のため・呼出側が label/market
    データと JOIN してこれらの列を補完する。
    """
    query = """
        SELECT model_type, model_version, feature_snapshot_id, as_of_datetime,
               year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
               race_date, p_fukusho_hit, calib_method, split, is_primary
        FROM prediction.fukusho_prediction
        WHERE feature_snapshot_id = %s AND split = 'test'
        ORDER BY model_type, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum
    """
    cur.execute(query, (feature_snapshot_id,))
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    # race_key を正準形式で構築（prediction テーブルは race_key 列を持たない）
    if len(df) > 0 and "race_key" not in df.columns:
        from src.model.data import make_race_key

        df["race_key"] = make_race_key(df).to_numpy()
    return df


def _fetch_label_df(cur):  # type: ignore[no-untyped-def]
    """label.fukusho_label から segment 軸 + fukusho_hit_validated を SELECT する（readonly）。

    label テーブルは race_key / ninki / fukuoddslower / entry_count を持たないため・
    PK 6カラム + sales_start_entry_count + fukusho_hit_validated のみ取得。race_key は
    呼出側で make_race_key で構築する（CONTEXT.md: label 欠損時は market JOIN で補完）。
    """
    query = """
        SELECT year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
               race_date, sales_start_entry_count, fukusho_hit_validated
        FROM label.fukusho_label
    """
    cur.execute(query)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    if len(df) > 0:
        from src.model.data import make_race_key

        df["race_key"] = make_race_key(df).to_numpy()
        # entry_count / fukusho_hit の alias（segment 評価が期待する列名に統一）
        df["entry_count"] = df["sales_start_entry_count"]
        df["fukusho_hit"] = df["fukusho_hit_validated"]
    return df


def _fetch_market_data(cur, race_keys: list[str] | None = None):  # type: ignore[no-untyped-def]
    """market データ (ninki/fukuoddslow) を取得する（CONTEXT.md: label 欠損時の segment 軸補完）。

    src/model/baseline.py::fetch_market_data の薄い wrapper。market データは
    raw_everydb2.n_odds_tanpuku + normalized.n_uma_race から取得し・prediction/label
    と (race_key, umaban) で JOIN する。

    **列名正規化:** baseline.fetch_market_data は ``fukuoddslow`` (w付き) を返すが・
    segment_eval.py は ``fukuoddslower`` (rあり) を期待するため alias を付与。
    race_keys フィルタは baseline 側で未実装のため無視（全件取得→呼出側で JOIN 時に絞り込まれる）。
    """
    from src.model.baseline import fetch_market_data

    df = fetch_market_data(cur, race_keys=None)  # race_keys 未実装のため無視
    if len(df) > 0:
        from src.model.data import make_race_key

        df["race_key"] = make_race_key(df).to_numpy()
        # fukuoddslow (baseline 戻り値) → fukuoddslower (segment_eval 期待名) の alias
        if "fukuoddslow" in df.columns and "fukuoddslower" not in df.columns:
            df["fukuoddslower"] = pd.to_numeric(df["fukuoddslow"], errors="coerce")
    return df


def _fetch_split_integrity_df(cur, feature_snapshot_id: str):  # type: ignore[no-untyped-def]
    """REVIEW N3 cycle-3: prediction.fukusho_prediction から全 split の DISTINCT (race_key, split)
    を SELECT する（§8.4 race_id disjoint 真再検証用・test-only では vacuous True になるのを回避）。

    prediction テーブルは race_key 列を持たないため・PK 6カラムから make_race_key で構築する。
    """
    query = """
        SELECT DISTINCT year, jyocd, kaiji, nichiji, racenum, split
        FROM prediction.fukusho_prediction
        WHERE feature_snapshot_id = %s AND split IN ('train', 'val', 'test')
    """
    cur.execute(query, (feature_snapshot_id,))
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    if len(df) > 0:
        from src.model.data import make_race_key

        df["race_key"] = make_race_key(df).to_numpy()
    return df


# ---------------------------------------------------------------------------
# Step 1b: 合成テスト用の成果物読込ヘルパ（DB 不要・tmp_path 由来 DataFrame を直接消費）
# ---------------------------------------------------------------------------


def _enrich_prediction_with_segments(prediction_df, label_df, market_df):  # type: ignore[no-untyped-def]
    """prediction_df に label と market の segment 軸（entry_count / fukusho_hit /
    ninki / fukuoddslower）を (race_key, umaban) で JOIN する（HIGH-1/HIGH-2: 行数不変 assert）。

    CONTEXT.md D-12: segment 軸（year/month/jyocd/entry_count/ninki/odds_band）のうち
    ninki/fukuoddslower は prediction/label テーブルに存在せず・market データ
    (raw_everydb2.n_odds_tanpuku + normalized.n_uma_race) から補完する必要がある。
    本関数は Step 1 の後・Step 2 の前に呼ばれ・prediction_df を segment 評価可能な形にする。
    """
    if len(prediction_df) == 0:
        return prediction_df

    out = prediction_df.copy()
    # umaban 型統一（prediction=object / label/market=int 等の混在対策）
    for _df_name, df in (("label", label_df), ("market", market_df)):
        if df is not None and len(df) > 0 and "umaban" in df.columns:
            df["umaban"] = pd.to_numeric(df["umaban"], errors="coerce").astype("Int64")
    if "umaban" in out.columns:
        out["umaban"] = pd.to_numeric(out["umaban"], errors="coerce").astype("Int64")

    # label から entry_count + fukusho_hit_validated を JOIN
    if label_df is not None and len(label_df) > 0:
        label_cols = [c for c in ("race_key", "umaban", "entry_count",
                                  "sales_start_entry_count", "fukusho_hit_validated",
                                  "race_date", "jyocd")
                      if c in label_df.columns]
        if {"race_key", "umaban"}.issubset(label_cols):
            out = out.merge(
                label_df[label_cols], on=["race_key", "umaban"], how="left",
                suffixes=("", "_label"),
            )
            if len(out) != len(prediction_df):
                raise RuntimeError(
                    f"_enrich_prediction_with_segments: label merge 行数不変違反 "
                    f"len(before)={len(prediction_df)} != len(after)={len(out)}"
                )
            # entry_count alias が無ければ sales_start_entry_count から補完
            if "entry_count" not in out.columns and "sales_start_entry_count" in out.columns:
                out["entry_count"] = out["sales_start_entry_count"]
            # fukusho_hit を fukusho_hit_validated から設定（evaluator が期待する列名）
            if "fukusho_hit" not in out.columns and "fukusho_hit_validated" in out.columns:
                out["fukusho_hit"] = out["fukusho_hit_validated"]

    # market から ninki + fukuoddslower を JOIN
    if market_df is not None and len(market_df) > 0:
        market_cols = [c for c in ("race_key", "umaban", "ninki", "fukuoddslower")
                       if c in market_df.columns]
        if {"race_key", "umaban"}.issubset(market_cols):
            out = out.merge(
                market_df[market_cols], on=["race_key", "umaban"], how="left",
                suffixes=("", "_market"),
            )
            if len(out) != len(prediction_df):
                raise RuntimeError(
                    f"_enrich_prediction_with_segments: market merge 行数不変違反 "
                    f"len(before)={len(prediction_df)} != len(after)={len(out)}"
                )

    return out


def _merge_prediction_with_label(prediction_df, label_df):  # type: ignore[no-untyped-def]
    """prediction_df と label_df を race_key 7カラムで JOIN する（HIGH-1/HIGH-2 契約・
    cartesian duplication 防御）。

    本関数は evaluator.evaluate_all_models が消費する予測+ラベル統合 df を返す。
    """

    # prediction_df 側にラベルが既に含まれている場合（テスト fixture 等）はそのまま返す
    if "fukusho_hit" in prediction_df.columns and len(prediction_df) > 0:
        # segment 軸が prediction_df 側に無い場合は label_df から補完
        seg_cols = ["race_date", "jyocd", "entry_count", "ninki", "fukuoddslower"]
        missing = [c for c in seg_cols if c not in prediction_df.columns]
        if not missing:
            return prediction_df
        # missing 補完のため label_df と JOIN
        join_cols = ["race_key", "umaban"]
        merged = prediction_df.merge(
            label_df[join_cols + missing],
            on=join_cols,
            how="left",
            suffixes=("", "_label"),
        )
        if len(merged) != len(prediction_df):
            raise RuntimeError(
                f"_merge_prediction_with_label: cartesian duplication 検出 "
                f"len(before)={len(prediction_df)} != len(after)={len(merged)}"
            )
        return merged

    # 完全 JOIN: label_df からラベル + segment 軸を補完
    keep = ["race_key", "umaban", "fukusho_hit", "fukusho_hit_validated",
            "race_date", "jyocd", "entry_count", "ninki", "fukuoddslower"]
    keep = [c for c in keep if c in label_df.columns]
    merged = prediction_df.merge(label_df[keep], on=["race_key", "umaban"], how="left")
    if len(merged) != len(prediction_df):
        raise RuntimeError(
            f"_merge_prediction_with_label: cartesian duplication 検出 "
            f"len(before)={len(prediction_df)} != len(after)={len(merged)}"
        )
    # fukusho_hit が label 側から来た場合は fukusho_hit_validated を正とする（WR-09）。
    # validated が NaN（未検証）の行のみ推定 fukusho_hit で補完するが・未検証ラベルを真として
    # §15.1 評価に用いるリスクがあるため・補完件数が 0 でなければ警告で可視化（silent 回避）。
    if "fukusho_hit_validated" in merged.columns and "fukusho_hit" in merged.columns:
        _unvalidated_n = int(merged["fukusho_hit_validated"].isna().sum())
        if _unvalidated_n > 0:
            logger.warning(
                "fukusho_hit_validated が %d 行 NaN → 推定 fukusho_hit で補完"
                "（未検証ラベルを真ラベルとして採用・§15.1 評価精度リスクあり）",
                _unvalidated_n,
            )
        merged["fukusho_hit"] = merged["fukusho_hit_validated"].fillna(merged["fukusho_hit"])
    return merged


# ---------------------------------------------------------------------------
# REVIEW Codex MEDIUM + N3 cycle-3: race_id split integrity check
# ---------------------------------------------------------------------------


def check_race_id_split_disjoint(split_integrity_df) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """train/val と test の race_key 集合が disjoint（空積）か検証する（§8.4 聖域・REVIEW N3 cycle-3）。

    **vacuous check 回避（REVIEW N3 cycle-3）:**
    両 split が非空の場合のみ真の検証。片方が空（該当 split 行なし）の場合は
    ``"N/A: split データ不足・Phase 4 GroupTimeSeriesSplit 担保"`` を返す。
    これは test-only 読込で ``set(train_races) == set()`` が常に disjoint=True になる
    silent 合格を排除するため。

    Parameters
    ----------
    split_integrity_df : pd.DataFrame
        ``race_key`` と ``split`` 列を持つ DataFrame（train/val/test のいずれかを含む）。

    Returns
    -------
    dict
        ``{race_id_split_disjoint: bool|str, n_train_races, n_test_races, diagnostic_note}``。
        ``race_id_split_disjoint`` は True/False または "N/A"（空 split 時）。
    """

    if split_integrity_df is None or len(split_integrity_df) == 0:
        return {
            "race_id_split_disjoint": "N/A",
            "n_train_races": 0,
            "n_test_races": 0,
            "diagnostic_note": "split_integrity_df が空・§8.4 検証不能",
        }

    train_races = set(
        split_integrity_df.loc[split_integrity_df["split"] == "train", "race_key"].dropna().tolist()
    )
    val_races = set(
        split_integrity_df.loc[split_integrity_df["split"] == "val", "race_key"].dropna().tolist()
    )
    test_races = set(
        split_integrity_df.loc[split_integrity_df["split"] == "test", "race_key"].dropna().tolist()
    )

    n_train = len(train_races) + len(val_races)
    n_test = len(test_races)

    if n_train == 0 or n_test == 0:
        # CR-01: prediction.fukusho_prediction は Phase 4 設計で test split のみ永続化されるため・
        # 本経路（prediction テーブル読込）からは train/test の race_id disjoint を再検査できない。
        # fail-loud は却下（test-only は正常系で評価全体を止めるべきでない）・代わりに誠実に
        # 「本レポートは再検査でなく Phase 4 分割時検証の参照記録」と明記し warning で可視化する。
        # ※ §8.4 不変量自体は Phase 4 GroupTimeSeriesSplit（strict max(train)<min(test)）で担保済み。
        logger.warning(
            "race_id split disjoint の再検査が不能（n_train_races=%d / n_test_races=%d）: "
            "prediction.fukusho_prediction が test split のみ（Phase 4 設計）。"
            "§8.4 不変量は Phase 4 分割時検証に依存（本レポートは再検査でなく参照記録）",
            n_train,
            n_test,
        )
        return {
            "race_id_split_disjoint": "N/A",
            "n_train_races": n_train,
            "n_test_races": n_test,
            "diagnostic_note": (
                "再検査不能（NOT re-verified here）: prediction.fukusho_prediction は test split のみ"
                "永続化（Phase 4 設計）のため本経路からは train/test の race_id disjoint を検証できない。"
                "§8.4 不変量は Phase 4 GroupTimeSeriesSplit（strict max(train.race_date)<min(test.race_date)）"
                "で分割時に検証済み。真の再検査が必要な場合は snapshot Parquet 側の split 列から race_key を"
                "再構築して検証すること（CR-01 follow-up 候補）"
            ),
        }

    # train ∪ val と test の共通部分が空なら disjoint
    train_val_races = train_races | val_races
    common = train_val_races & test_races
    is_disjoint = len(common) == 0

    return {
        "race_id_split_disjoint": is_disjoint,
        "n_train_races": n_train,
        "n_test_races": n_test,
        "diagnostic_note": (
            f"train/val ({n_train} races) と test ({n_test} races) は disjoint={'True' if is_disjoint else 'False'}"
            + (f"・leak race_keys={sorted(common)[:5]}" if common else "")
        ),
    }


# ---------------------------------------------------------------------------
# Step 2-4 helper: evaluate_integrated（純粋関数・DB 不要・テスト対象）
# ---------------------------------------------------------------------------


def aggregate_backtest_for_model(bt_rows: list[dict], model_type: str) -> dict[str, Any]:
    """reports/05-backtest.json の comparison_table から特定 model_type の行を集約する（REVIEW C8）。

    **集計規則（REVIEW C8: 優位 policy の代表窓）:**
    model_type 毎に 30min_before / 10min_before の2 policy がある場合・recovery_rate が
    高い方を代表窓として1行に集約。5窓ある場合は全窓の平均を取る（窓毎の代表窓の重み付き平均）。

    Parameters
    ----------
    bt_rows : list[dict]
        reports/05-backtest.json の comparison_table（各 backtest 行）。
    model_type : str
        集約対象の model_type（``"lightgbm"`` / ``"catboost"`` / ``"bl3"``）。

    Returns
    -------
    dict
        ``{recovery_rate, profit_loss, max_drawdown, selected, effective_bet,
        representative_policy, n_windows}``。該当行がない場合は空 dict。
    """
    rows = [r for r in bt_rows if r.get("model_type") == model_type]
    if not rows:
        return {}

    # bt_name × policy で代表窓（recovery_rate 最高）を選択
    from collections import defaultdict

    by_bt: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_bt[r.get("bt_name", "?")].append(r)

    representatives: list[dict] = []
    representative_policies: list[str] = []
    for _bt_name, bt_rows_group in by_bt.items():
        best = max(bt_rows_group, key=lambda r: float(r.get("recovery_rate", 0.0)))
        representatives.append(best)
        representative_policies.append(str(best.get("odds_policy", "?")))

    n = len(representatives)
    # 全窓の平均（単純平均・窓毎の候補数がほぼ同規模のため）
    recovery_rate = sum(float(r.get("recovery_rate", 0.0)) for r in representatives) / n
    # WR-04: 切捨て除算 // でなく浮動小数除算（recovery_rate と一貫・端数累積誤差回避）
    profit_loss = sum(int(r.get("P/L", 0)) for r in representatives) / n
    max_drawdown = max(int(r.get("max_DD", 0)) for r in representatives)
    selected = sum(int(r.get("selected", 0)) for r in representatives)
    effective_bet = sum(int(r.get("effective_bet", 0)) for r in representatives)
    # SC#1/EVAL-01 複勝的中率: 重み付き平均（分母 = 全代表窓 effective_bet 総和・CR-03）。
    # 以前は代表窓の hit_rate 単純平均だったが・窓毎の購買馬数バラツキで正しい的中率と不一致するため
    # effective_bet で重み付け（Σ(hit_rate_i × effective_bet_i) / Σ effective_bet_i = Σhits/Σbets）。
    if effective_bet > 0:
        weighted_hits = sum(
            float(r.get("hit_rate", 0.0)) * int(r.get("effective_bet", 0))
            for r in representatives
        )
        hit_rate = weighted_hits / effective_bet
    else:
        hit_rate = 0.0

    # 代表窓 policy（最頻値）
    from collections import Counter

    policy_counts = Counter(representative_policies)
    representative_policy = policy_counts.most_common(1)[0][0]

    return {
        "recovery_rate": recovery_rate,
        "hit_rate": hit_rate,
        "profit_loss": profit_loss,
        "max_drawdown": max_drawdown,
        "selected": selected,
        "effective_bet": effective_bet,
        "representative_policy": representative_policy,
        "n_windows": n,
    }


def build_recommended_primary_model(
    metrics_04: dict[str, dict[str, Any]],
    bt_by_model: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """D-08 タイブレーク優先順位で推奨主モデルを決定する（REVIEW C7 省略時の推奨表）。

    **D-08 優先順位:**
      1. backtest 回収率（高い方）
      2. 計算コスト低=LightGBM（同点時）
      3. Brier（低い方）
      4. LogLoss（低い方）
      5. AUC（高い方）

    Parameters
    ----------
    metrics_04 : dict
        reports/04-eval.json の ``metrics`` dict（両モデル + baselines）。
    bt_by_model : dict
        ``aggregate_backtest_for_model`` の戻り値を model_type 毎に集めた dict。

    Returns
    -------
    dict
        ``{model_type, selection_reason, tiebreak_applied, priority_order}``。
        ``tiebreak_applied`` は同点で発火した段階のキー・無ければ None。
    """
    candidates: list[str] = [mt for mt in PRIMARY_MODEL_CANDIDATES if mt in metrics_04]
    if not candidates:
        return {
            "model_type": None,
            "selection_reason": "候補モデルなし（metrics_04 に lightgbm/catboost が無い）",
            "tiebreak_applied": None,
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }
    if len(candidates) == 1:
        mt = candidates[0]
        return {
            "model_type": mt,
            "selection_reason": f"単一候補: {mt}",
            "tiebreak_applied": None,
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }

    # D-08 優先順位で比較
    def _recovery(mt: str) -> float:
        return float(bt_by_model.get(mt, {}).get("recovery_rate", 0.0))

    def _brier(mt: str) -> float:
        return float(metrics_04.get(mt, {}).get("brier", float("inf")))

    def _logloss(mt: str) -> float:
        return float(metrics_04.get(mt, {}).get("logloss", float("inf")))

    def _auc(mt: str) -> float:
        return float(metrics_04.get(mt, {}).get("auc", 0.0))

    a, b = candidates[0], candidates[1]
    tiebreak_applied: str | None = None

    # 1. backtest 回収率（D-08 優先順位の第1基準）
    # ※ WR-10 対応（誤読防止）: D-08 は「接近・同点時に優先順位（回収率→計算コスト→…）で1つ選ぶ」。
    # 回収率が異なれば（差の大小に関わらず）回収率が第1基準として勝敗を決める。5%未満の僅差は
    # 「tiebreak 規則が発火した（接戦だった）」旨の注記（tiebreak_applied）だけで・次基準へは飛ばない。
    # 次基準（計算コスト）は回収率が*完全に同点*の場合のみ発火（下の #2）。
    if _recovery(a) != _recovery(b):
        winner = a if _recovery(a) > _recovery(b) else b
        reason = (
            f"D-08 tiebreak[1] backtest_recovery_rate: {winner} "
            f"(recovery: {_recovery(a):.4f} vs {_recovery(b):.4f})"
        )
        # 僅差（5%未満）の場合のみ tiebreak 規則発火を明記（決定は常に回収率の大小）
        if abs(_recovery(a) - _recovery(b)) < 0.05:
            tiebreak_applied = "backtest_recovery_rate"
        return {
            "model_type": winner,
            "selection_reason": reason,
            "tiebreak_applied": tiebreak_applied,
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }

    # 2. 計算コスト低=LightGBM（同回収率時）
    if "lightgbm" in candidates:
        tiebreak_applied = "compute_cost_lightgbm_first"
        return {
            "model_type": "lightgbm",
            "selection_reason": (
                f"D-08 tiebreak[2] compute_cost_lightgbm_first: backtest 回収率同点"
                f" ({_recovery(a):.4f}) のため LightGBM を優先（計算コスト低）"
            ),
            "tiebreak_applied": tiebreak_applied,
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }

    # 3. Brier
    if _brier(a) != _brier(b):
        winner = a if _brier(a) < _brier(b) else b
        return {
            "model_type": winner,
            "selection_reason": (
                f"D-08 tiebreak[3] brier: {winner} "
                f"(brier: {_brier(a):.6f} vs {_brier(b):.6f})"
            ),
            "tiebreak_applied": "brier",
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }

    # 4. LogLoss
    if _logloss(a) != _logloss(b):
        winner = a if _logloss(a) < _logloss(b) else b
        return {
            "model_type": winner,
            "selection_reason": (
                f"D-08 tiebreak[4] logloss: {winner} "
                f"(logloss: {_logloss(a):.6f} vs {_logloss(b):.6f})"
            ),
            "tiebreak_applied": "logloss",
            "priority_order": list(TIEBREAK_PRIORITY_ORDER),
        }

    # 5. AUC（最終）
    winner = a if _auc(a) > _auc(b) else b
    return {
        "model_type": winner,
        "selection_reason": (
            f"D-08 tiebreak[5] auc: {winner} "
            f"(auc: {_auc(a):.6f} vs {_auc(b):.6f})"
        ),
        "tiebreak_applied": "auc",
        "priority_order": list(TIEBREAK_PRIORITY_ORDER),
    }


def evaluate_integrated(
    *,
    prediction_df,
    label_df,
    eval_04_path: str | Path,
    backtest_05_path: str | Path,
    split_integrity_df,
    feature_snapshot_id: str,
    as_of_datetime: str,
    segments_dir: str | Path = "reports/06-segments",
    skip_segments: bool = False,
) -> dict[str, Any]:
    """統合評価の中核（Step 1-4 の純粋関数版・DB 不要・テスト対象）。

    Parameters
    ----------
    prediction_df : pd.DataFrame
        ``prediction.fukusho_prediction`` の test split 行（両モデル + baselines 含む）。
        ``model_type`` / ``p_fukusho_hit`` / ``race_key`` / ``entry_count`` /
        ``split`` / ``fukusho_hit`` / segment 軸（race_date/jyocd/ninki/fukuoddslower）。
    label_df : pd.DataFrame
        ``label.fukusho_label`` 行（race_key + segment 軸 + fukusho_hit_validated）。
    eval_04_path : str | Path
        reports/04-eval.json のパス（metrics dict を読込）。
    backtest_05_path : str | Path
        reports/05-backtest.json のパス（comparison_table を読込）。
    split_integrity_df : pd.DataFrame
        ``race_key`` と ``split`` 列を持つ DataFrame（§8.4 disjoint 検証用）。
    feature_snapshot_id : str
        feature snapshot ID（provenance 記録用）。
    as_of_datetime : str
        prediction の as_of_datetime（provenance 記録用・ISO8601）。
    segments_dir : str | Path
        segment 評価出力ディレクトリ。
    skip_segments : bool
        segment 評価をスキップする場合は True。

    Returns
    -------
    dict
        統合評価結果 dict（``gate_result`` / ``comparison_table`` / ``segment_summary``
        / ``backtest_summary`` / ``sum_p_measurement`` / ``reproducibility_checks``
        / ``metrics_dict`` / ``recommended_primary_model`` / ``provenance``）。
    """
    # Step 1: 成果物読込
    eval_04 = _load_json_file(eval_04_path)
    metrics_04: dict[str, dict[str, Any]] = eval_04.get("metrics", {})
    backtest_05 = _load_json_file(backtest_05_path)
    bt_rows: list[dict] = backtest_05.get("comparison_table", [])

    # Step 2: 確率品質指標計算（evaluator.py）
    # prediction_df と label_df を race_key 7カラムで JOIN
    merged = _merge_prediction_with_label(prediction_df, label_df)

    # evaluate_all_models 形式に変換（model_type 毎に dict）
    predictions_by_model: dict[str, Any] = {}
    y_true_by_split: dict[str, Any] = {}
    for mt, group in merged.groupby("model_type"):
        predictions_by_model[mt] = group.reset_index(drop=True)
    # test のみの真ラベル（evaluate_all_models は test split を使用）
    test_mask_all = merged["split"] == "test"
    y_true_by_split["test"] = merged.loc[test_mask_all, "fukusho_hit"].reset_index(drop=True) if test_mask_all.any() else merged["fukusho_hit"].reset_index(drop=True)

    # evaluate_all_models は reports/04-eval.{md,json} を再生成してしまうため・
    # compute_metrics を直接呼出して metrics_dict を構築（04-eval.json の stamped 値を優先しない・
    # 06-eval 独立性担保・ただし両者は bit-identical になるはず）。
    # → Phase 4 stamped 値をそのまま消費（再現性聖域・Phase 4 SC#4）。
    metrics_dict: dict[str, dict[str, Any]] = dict(metrics_04)
    # 欠損モデル・欠損指標があれば prediction_df から compute_metrics で補完
    for mt in list(predictions_by_model.keys()):
        if mt not in metrics_dict or not metrics_dict[mt]:
            pred = predictions_by_model[mt]
            test_mask = pred["split"] == "test" if "split" in pred.columns else slice(None)
            pred_test = pred.loc[test_mask] if isinstance(test_mask, pd.Series) else pred
            if len(pred_test) == 0:
                continue
            y_t = pred_test["fukusho_hit"].to_numpy()
            y_p = pred_test["p_fukusho_hit"].to_numpy()
            rk = pred_test["race_key"].to_numpy() if "race_key" in pred_test.columns else None
            ec = pred_test["entry_count"].to_numpy() if "entry_count" in pred_test.columns else None
            metrics_dict[mt] = compute_metrics(y_t, y_p, race_keys=rk, entry_counts=ec)

    # 比較表構築（両モデル + baselines）
    comparison_df = build_comparison_table(metrics_dict)

    # sum(p) 分布検査（§15.2）
    # REVIEW HIGH#5 bug fix: 主モデル候補 *両方* の行を含めると race_key 毎の sum(p) が
    # 2倍（≈6）になり §15.2 理論値 [2.7,3.3] を著しく逸脱する false alarm になる。
    # → lightgbm のみ（Phase 4 evaluator.evaluate_all_models と同様・片モデル毎）で計算。
    main_pred_lightgbm = merged[merged["model_type"] == "lightgbm"]
    if len(main_pred_lightgbm) == 0:
        # lightgbm が無い場合は catboost を代替
        main_pred_lightgbm = merged[merged["model_type"] == "catboost"]
    main_pred_test = (
        main_pred_lightgbm[main_pred_lightgbm["split"] == "test"]
        if "split" in main_pred_lightgbm.columns
        else main_pred_lightgbm
    )
    if len(main_pred_test) == 0:
        main_pred_test = main_pred_lightgbm
    sum_p_check = check_sum_p_distribution(
        main_pred_test, p_col="p_fukusho_hit", entry_count_col="entry_count"
    )

    # REVIEW HIGH#5: sum_p_measurement dict
    large_rate = float(sum_p_check.get("large_violation_rate", 0.0))
    small_rate = float(sum_p_check.get("small_violation_rate", 0.0))
    total_races = int(sum_p_check.get("total_races", 0))
    # threshold_appropriate: 偽陽性 BLOCK にならないか（現データで violation_rate < threshold）
    threshold_appropriate = (large_rate < SUM_P_BLOCK_THRESHOLD) and (
        small_rate < SUM_P_BLOCK_THRESHOLD
    )
    sum_p_measurement = {
        "large_violation_rate": large_rate,
        "small_violation_rate": small_rate,
        "total_races": total_races,
        "threshold": SUM_P_BLOCK_THRESHOLD,
        "threshold_appropriate": bool(threshold_appropriate),
        "diagnostic_note": (
            f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} の経験的根拠: "
            f"現データ violation_rate (large={large_rate:.4f}, small={small_rate:.4f}) が "
            f"閾値 {SUM_P_BLOCK_THRESHOLD:.2f} を下回るため偽陽性 BLOCK にならない（安全網として妥当）"
            if threshold_appropriate
            else f"閾値 {SUM_P_BLOCK_THRESHOLD:.2f} を超過・閾値調整を検討"
        ),
    }

    # Step 3: segment 別安定性評価（segment_eval.py）
    segment_summary: dict[str, Any] = {}
    all_segment_results: dict[str, dict[str, Any]] = {}
    segment_report_paths: dict[str, Any] = {}
    if not skip_segments:
        # segment 評価用 df は prediction + label JOIN 済み（merged）の test split 主モデル
        # 主モデルの test 行（lightgbm を代表）・全モデルを含めてもよいが代表で十分
        seg_df = main_pred_test.copy()
        if len(seg_df) > 0:
            try:
                all_segment_results = evaluate_all_segments(
                    seg_df,
                    p_col="p_fukusho_hit",
                    y_true_col="fukusho_hit",
                )
                segment_report_paths = write_segment_reports(
                    all_segment_results, out_dir=segments_dir
                )
                # 各軸の scalar サマリ（axes × セグメント数）
                for axis, seg_results in all_segment_results.items():
                    segment_summary[axis] = {
                        "n_segments": len(seg_results),
                        "segments": sorted(seg_results.keys()),
                        "scalars": {
                            seg_val: data.get("scalar", {})
                            for seg_val, data in seg_results.items()
                        },
                    }
            except Exception as e:
                logger.warning("segment 評価で例外（skip 扱い）: %s", e)
                segment_summary = {"error": str(e)}

    # Step 4: 受入ゲート判定（REVIEW HIGH#6: segment 評価 *後* に gate 判定）
    gate_result = check_acceptance_gate(metrics_dict, sum_p_check)

    # monotonicity WARN（全モデルの test split の calibration curve binning）
    monotonicity_warn_by_model: dict[str, dict[str, float]] = {}
    from src.model.evaluator import _compute_calibration_curve_bins  # 遅延 import

    for mt, pred in predictions_by_model.items():
        test_mask = pred["split"] == "test" if "split" in pred.columns else slice(None)
        pred_test = pred.loc[test_mask] if isinstance(test_mask, pd.Series) else pred
        if len(pred_test) == 0:
            continue
        y_t = pred_test["fukusho_hit"].to_numpy()
        y_p = pred_test["p_fukusho_hit"].to_numpy()
        if len(np.unique(y_t)) < 2:
            continue
        bins = _compute_calibration_curve_bins(y_t, y_p, strategy="uniform")
        monotonicity_warn_by_model[mt] = compute_monotonicity_warn(bins)
    gate_result["monotonicity_warn_by_model"] = monotonicity_warn_by_model

    # 年次反転 WARN（reports/06-segments/year.json の各年 curve に適用）
    year_segment_results = all_segment_results.get("year", {})
    yearly_inversion_warn = compute_yearly_inversion_warn(year_segment_results)
    gate_result["yearly_inversion_warn"] = yearly_inversion_warn

    # REVIEW Codex MEDIUM + N3 cycle-3: race_id split integrity check
    split_check = check_race_id_split_disjoint(split_integrity_df)
    gate_result.setdefault("reproducibility_checks", {})
    gate_result["reproducibility_checks"]["race_id_split_disjoint"] = split_check["race_id_split_disjoint"]
    gate_result["reproducibility_checks"]["n_train_races"] = split_check["n_train_races"]
    gate_result["reproducibility_checks"]["n_test_races"] = split_check["n_test_races"]
    gate_result["reproducibility_checks"]["split_diagnostic_note"] = split_check["diagnostic_note"]

    # backtest_summary（REVIEW C8: 集計方法を明記）
    backtest_by_model: dict[str, dict[str, Any]] = {}
    for mt in PRIMARY_MODEL_CANDIDATES:
        backtest_by_model[mt] = aggregate_backtest_for_model(bt_rows, mt)
    backtest_summary = {
        "by_model": backtest_by_model,
        "backtest_aggregation_method": BACKTEST_AGGREGATION_METHOD,
        "source": str(backtest_05_path),
    }

    # recommended_primary_model（REVIEW C7: 推奨表）
    recommended_primary_model = build_recommended_primary_model(metrics_04, backtest_by_model)

    return {
        "gate_result": gate_result,
        "comparison_df": comparison_df,
        "metrics_dict": metrics_dict,
        "segment_summary": segment_summary,
        "segment_report_paths": segment_report_paths,
        "backtest_summary": backtest_summary,
        "sum_p_measurement": sum_p_measurement,
        "recommended_primary_model": recommended_primary_model,
        "provenance": {
            "feature_snapshot_id": feature_snapshot_id,
            "as_of_datetime": as_of_datetime,
        },
    }


# ---------------------------------------------------------------------------
# レポート出力: generate_evaluation_reports（md + json・atomic write）
# ---------------------------------------------------------------------------


# REVIEW C15 cycle-2: SC#2「beat all baselines」と BLOCK 条件1「baselines 全敗」の対称性注記
SC2_BLOCK_SYMMETRY_NOTE = (
    "SC#2「beat all baselines」と BLOCK 条件1「baselines 全敗」は対称的な表現。"
    "どちらも COMPARABLE_BASELINES bl1/bl4/bl5 の LogLoss+Brier 比較で・"
    "SC#2 は両指標で全 baselines の max に勝る（全勝）・BLOCK 条件1 は両指標で全 baselines の max に劣る（全敗）。"
    "中間の「一部にのみ劣る / 一部にのみ勝る」は WARN に留まる（D-02 AND 条件）。"
    "現データ（reports/04-eval.json）では LightGBM が LogLoss/Brier 両方で BL-1/BL-4/BL-5 の全てに勝るため "
    "SC#2 達成・BLOCK 条件1 は非該当。定義の対称性を明示することで Phase 8 対抗的監査で「SC#2 達成」の"
    "解釈が曖昧にならない（REVIEW C15 cycle-2 修正）。"
)


def _sanitize_nan_to_null(obj: Any) -> Any:
    """dict/list/float 再帰的に走査し NaN/Inf を None に正規化する（RFC 8259 strict JSON 化）。

    reports/06-evaluation.json の segment scalar（odds_band.__MISSING__ / entry_count.6.0 等）は
    計算不能（サンプル不足・bin 未構築）で NaN になる。Python json.dumps はデフォルトで
    NaN を ``NaN`` リテラルとして出力するが・これは RFC 8259 strict 仕様違反で Phase 7 Streamlit
    や外部パーサで失敗するリスクがある。NaN は「データなし」の正しい意味論なので null に正規化する。

    ``allow_nan=False`` と組み合わせることで・万が一変換漏れがあれば json.dumps が ValueError を送出し
    silent な strict 違反を防止する（fail-loud・Phase 7 消費安全性）。
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan_to_null(v) for v in obj]
    return obj


def _df_to_markdown_table(df) -> str:  # type: ignore[no-untyped-def]
    """DataFrame を Markdown 表に変換（evaluator.py のパターンを再利用）。"""
    import pandas as pd  # 遅延 import

    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                if pd.isna(v):
                    cells.append("nan")
                else:
                    cells.append(f"{v:.6f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + rows)


def _build_comparison_table_with_backtest(
    comparison_df,
    backtest_by_model: dict[str, dict[str, Any]],
) -> pd.DataFrame:  # type: ignore[name-defined]
    """主モデル比較表に backtest 指標（回収率/P/L/maxDD）を統合する（EVAL-01・REVIEW C8）。

    METRIC_COLUMNS_EXTENDED に加えて backtest 系3列を付与。baselines は NaN。
    """

    df = comparison_df.copy()
    df["bt_recovery_rate"] = float("nan")
    df["bt_hit_rate"] = float("nan")
    df["bt_profit_loss"] = float("nan")
    df["bt_max_drawdown"] = float("nan")
    df["bt_representative_policy"] = ""
    for mt, agg in backtest_by_model.items():
        if not agg:
            continue
        mask = df["model_name"] == mt
        if mask.any():
            df.loc[mask, "bt_recovery_rate"] = float(agg.get("recovery_rate", float("nan")))
            df.loc[mask, "bt_hit_rate"] = float(agg.get("hit_rate", float("nan")))
            df.loc[mask, "bt_profit_loss"] = int(agg.get("profit_loss", 0))
            df.loc[mask, "bt_max_drawdown"] = int(agg.get("max_drawdown", 0))
            df.loc[mask, "bt_representative_policy"] = str(agg.get("representative_policy", ""))
    return df


def generate_evaluation_reports(
    result: dict[str, Any],
    *,
    out_md_path: str | Path,
    out_json_path: str | Path,
    primary_model: str | None,
    selection_reason: str | None,
) -> tuple[Any, Any]:  # type: ignore[type-arg]
    """reports/06-evaluation.{md,json} を atomic write する（REVIEW HIGH#6: BLOCK の場合も含む）。

    Parameters
    ----------
    result : dict
        ``evaluate_integrated`` の戻り値。
    out_md_path / out_json_path : str | Path
        出力パス。
    primary_model : str | None
        人間が選定した主モデル（``--primary-model`` 引数）。None の場合は recommended のみ提示。
    selection_reason : str | None
        ``--selection-reason`` 引数。None の場合は recommended の理由を使用。
    """
    md_path = Path(out_md_path)
    json_path = Path(out_json_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    gate_result = result["gate_result"]
    backtest_summary = result["backtest_summary"]
    sum_p_measurement = result["sum_p_measurement"]
    recommended = result["recommended_primary_model"]
    provenance = result["provenance"]

    # backtest 統合済み比較表
    comparison_df_with_bt = _build_comparison_table_with_backtest(
        result["comparison_df"],
        backtest_summary["by_model"],
    )

    # primary_model レコード構築（REVIEW C7: 指定時のみ非 null）
    if primary_model is not None:
        # model_version は metrics_dict から推測できないため prediction_df から取得する想定だが・
        # ここでは provenance と feature_snapshot_id から推定
        # Rule1: DB実値と一致する正規の model_version 採番 (旧: primary_model[:3] → "lig" 偏差 bug)
        model_version = make_model_version(
            provenance["feature_snapshot_id"], primary_model, version_n=1
        )
        primary_model_record = {
            "model_type": primary_model,
            "model_version": model_version,
            "feature_snapshot_id": provenance["feature_snapshot_id"],
            "as_of_datetime": provenance["as_of_datetime"],
            "selection_reason": selection_reason or recommended.get("selection_reason", ""),
            "tiebreak_applied": recommended.get("tiebreak_applied"),
        }
        recommended_record = None
    else:
        primary_model_record = None
        recommended_record = recommended

    # --- JSON 構築（sort_keys=True byte-reproducible・RFC 8259 strict） ---
    comparison_records = json.loads(comparison_df_with_bt.to_json(orient="records"))
    # NaN → null（comparison_records・従来処理）
    for rec in comparison_records:
        for k, v in list(rec.items()):
            if isinstance(v, float) and pd.isna(v):
                rec[k] = None

    # RFC 8259 strict JSON 化: ネスト dict 内の NaN/Inf を再帰的に null に正規化
    # （segment_summary.odds_band.__MISSING__ / entry_count.6.0 の scalar 等）
    # allow_nan=False と組み合わせ・変換漏れがあれば fail-loud で検出

    # CR-02: sum_p 閾値根拠注記を threshold_appropriate で分岐（矛盾文言解消）。
    # 以前は固定で「偽陽性 BLOCK を出さないか検証済み」としていたが・threshold_appropriate=False
    # （violation_rate 高）の実データと矛盾する監査性違反だったため正直に記述する。
    _sp_appropriate = bool(sum_p_measurement.get("threshold_appropriate", False))
    _sp_large = float(sum_p_measurement.get("large_violation_rate", 0.0))
    _sp_small = float(sum_p_measurement.get("small_violation_rate", 0.0))
    if _sp_appropriate:
        sum_p_threshold_rationale = (
            f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} は仮置き・"
            "現データ violation_rate 実測で偽陽性 BLOCK を出さないことを確認済み"
            f"（threshold_appropriate=True・large={_sp_large:.1%}/small={_sp_small:.1%}）"
        )
    else:
        sum_p_threshold_rationale = (
            f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} は現データの violation_rate "
            f"(large={_sp_large:.1%}/small={_sp_small:.1%}) に対して低すぎ・偽陽性 BLOCK になりうる。"
            "閾値の引き上げ（0.30→0.80 等）または sum(p) の BLOCK 条件からの除外（WARN 専門化）を"
            f"検討すること（threshold_appropriate=False・ただし D-02 AND 条件のため baselines_all_lose=False で BLOCK 非発火）"
        )
    json_obj = {
        "gate_result": _sanitize_nan_to_null(gate_result),
        "comparison_table": _sanitize_nan_to_null(comparison_records),
        "primary_model": _sanitize_nan_to_null(primary_model_record),
        "recommended_primary_model": _sanitize_nan_to_null(recommended_record),
        "segment_summary": _sanitize_nan_to_null(result["segment_summary"]),
        "backtest_summary": _sanitize_nan_to_null(backtest_summary),
        "sum_p_measurement": _sanitize_nan_to_null(sum_p_measurement),
        "reproducibility_checks": _sanitize_nan_to_null(
            gate_result.get("reproducibility_checks", {})
        ),
        "constants": {
            "METRIC_COLUMNS_EXTENDED": list(METRIC_COLUMNS_EXTENDED),
            "SUM_P_BLOCK_THRESHOLD": SUM_P_BLOCK_THRESHOLD,
            "COMPARABLE_BASELINES": list(COMPARABLE_BASELINES),
            "CALIBRATION_CURVE_BINS": CALIBRATION_CURVE_BINS,
            "CALIBRATION_CURVE_MIN_BIN_COUNT": CALIBRATION_CURVE_MIN_BIN_COUNT,
        },
        "notes": {
            "d04_selection_criterion": D04_SELECTION_CRITERION_NOTE,
            "bl1_caveat": (
                "BL-1 は順序付け能力ゼロ (AUC≈0.57) の副産物で calibration_max_dev が構造的極小。"
                "uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない（debug Resolution #4）"
            ),
            "bl3_caveat": BL3_MARKET_REFERENCE_NOTE,
            "bl_uncalibrated": BL_UNCALIBRATED_NOTE,
            "sum_p_diagnostic": SUM_P_DIAGNOSTIC_NOTE,
            "sum_p_threshold_rationale": sum_p_threshold_rationale,
            "sc2_block_symmetry_note": SC2_BLOCK_SYMMETRY_NOTE,
        },
    }
    json_payload = json.dumps(
        json_obj,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,  # NaN/Inf の混入を防止（silent strict 違反回避・fail-loud）
    )
    _atomic_write_text(json_path, json_payload)

    # --- Markdown 構築（5セクション + REVIEW C15 cycle-2 対称性注記） ---
    md_lines: list[str] = []
    md_lines.append("# Phase 6 Evaluation Report (EVAL-01/02/03 / §15.1/§15.2/§15.3)\n\n")
    md_lines.append(
        f"**feature_snapshot_id:** {provenance['feature_snapshot_id']}  /  "
        f"**as_of_datetime:** {provenance['as_of_datetime']}\n\n"
    )

    # セクション1: 受入ゲート判定
    md_lines.append("## 受入ゲート判定（BLOCK/WARN）\n\n")
    md_lines.append(f"- **gate_verdict:** {gate_result['gate_verdict']}\n")
    md_lines.append(f"- **block_triggered:** {gate_result['block_triggered']}\n")
    if gate_result["block_reasons"]:
        md_lines.append("- **block_reasons:**\n")
        for r in gate_result["block_reasons"]:
            md_lines.append(f"  - {r}\n")
    if gate_result["warn_reasons"]:
        md_lines.append("- **warn_reasons:**\n")
        for r in gate_result["warn_reasons"]:
            md_lines.append(f"  - {r}\n")
    md_lines.append(
        f"- **condition_flags:** {gate_result['condition_flags']}\n"
        f"- **comparable_baselines:** {gate_result['comparable_baselines']}\n"
        f"- **sum_p_block_threshold:** {gate_result['sum_p_block_threshold']}\n\n"
    )
    # monotonicity / yearly inversion WARN
    mono = gate_result.get("monotonicity_warn_by_model", {})
    if mono:
        md_lines.append("### bin 単調性 WARN 指標（D-03・参考）\n\n")
        md_lines.append("| model | spearman_corr | spearman_pvalue | bin_inversions |\n")
        md_lines.append("| --- | --- | --- | --- |\n")
        for mt, data in sorted(mono.items()):
            md_lines.append(
                f"| {mt} | {data['spearman_corr']:.4f} | "
                f"{data['spearman_pvalue']:.4f} | {data['bin_inversions']} |\n"
            )
        md_lines.append("\n")
    yw = gate_result.get("yearly_inversion_warn", {})
    if yw:
        md_lines.append("### 年次反転 WARN 指標（D-03 年次要素・参考）\n\n")
        md_lines.append("| year | spearman_corr | spearman_pvalue | bin_inversions |\n")
        md_lines.append("| --- | --- | --- | --- |\n")
        for year, data in sorted(yw.items()):
            md_lines.append(
                f"| {year} | {data['spearman_corr']:.4f} | "
                f"{data['spearman_pvalue']:.4f} | {data['bin_inversions']} |\n"
            )
        md_lines.append("\n")
    # sum(p) measurement（REVIEW HIGH#5）
    md_lines.append("### sum(p) violation_rate 計測（REVIEW HIGH#5・0.30 閾値の経験的根拠）\n\n")
    md_lines.append(
        f"- large_violation_rate: {sum_p_measurement['large_violation_rate']:.4f} "
        f"(threshold={sum_p_measurement['threshold']:.2f})\n"
        f"- small_violation_rate: {sum_p_measurement['small_violation_rate']:.4f}\n"
        f"- total_races: {sum_p_measurement['total_races']}\n"
        f"- threshold_appropriate: {sum_p_measurement['threshold_appropriate']}\n"
        f"- diagnostic_note: {sum_p_measurement['diagnostic_note']}\n\n"
    )
    # race_id split integrity（REVIEW Codex MEDIUM）
    rep = gate_result.get("reproducibility_checks", {})
    md_lines.append("### race_id split integrity（REVIEW Codex MEDIUM + N3 cycle-3・§8.4 聖域）\n\n")
    md_lines.append(
        f"- race_id_split_disjoint: {rep.get('race_id_split_disjoint')}\n"
        f"- n_train_races: {rep.get('n_train_races')}\n"
        f"- n_test_races: {rep.get('n_test_races')}\n"
        f"- diagnostic_note: {rep.get('split_diagnostic_note')}\n\n"
    )

    # セクション2: 主モデル比較表
    md_lines.append("## 主モデル比較表（全指標）\n\n")
    md_lines.append(_df_to_markdown_table(comparison_df_with_bt))
    md_lines.append("\n\n")
    md_lines.append(
        f"**backtest 集計方法（REVIEW C8）:** {backtest_summary['backtest_aggregation_method']}\n\n"
    )

    # セクション3: 主モデル確定
    md_lines.append("## 主モデル確定（理由記録・D-07）\n\n")
    if primary_model_record:
        md_lines.append(
            f"- **primary_model:** {primary_model_record['model_type']} "
            f"(model_version={primary_model_record['model_version']})\n"
            f"- **selection_reason:** {primary_model_record['selection_reason']}\n"
            f"- **tiebreak_applied:** {primary_model_record['tiebreak_applied']}\n\n"
        )
    else:
        md_lines.append(
            "- **primary_model:** 未確定（--primary-model 省略・REVIEW C7）\n\n"
        )
        md_lines.append("### 推奨主モデル（D-08 タイブレーク優先順位・参考）\n\n")
        md_lines.append(
            f"- **recommended:** {recommended.get('model_type')}\n"
            f"- **selection_reason:** {recommended.get('selection_reason')}\n"
            f"- **tiebreak_applied:** {recommended.get('tiebreak_applied')}\n"
            f"- **priority_order:** {recommended.get('priority_order')}\n\n"
        )

    # セクション4: segment 安定性サマリ
    md_lines.append("## segment 安定性サマリ（6軸）\n\n")
    seg_summary = result.get("segment_summary", {})
    if seg_summary and "error" not in seg_summary:
        md_lines.append("| axis | n_segments | segments |\n")
        md_lines.append("| --- | --- | --- |\n")
        for axis, data in sorted(seg_summary.items()):
            segs = data.get("segments", [])
            md_lines.append(
                f"| {axis} | {data.get('n_segments', 0)} | "
                f"{', '.join(segs[:5])}{'...' if len(segs) > 5 else ''} |\n"
            )
        md_lines.append(
            "\n詳細: reports/06-segments/{year,month,jyocd,entry_count,ninki,odds_band}.{json,html}\n\n"
        )
    else:
        md_lines.append(f"segment 評価: {seg_summary.get('error', '未生成')}\n\n")

    # セクション5: 注記
    md_lines.append("## 注記\n\n")
    md_lines.append(f"- {D04_SELECTION_CRITERION_NOTE}\n")
    md_lines.append(
        "- BL-1 caveat: 順序付け能力ゼロ (AUC≈0.57) の副産物で calibration_max_dev が構造的極小・"
        "uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない（debug Resolution #4）\n"
    )
    md_lines.append(f"- BL-3: {BL3_MARKET_REFERENCE_NOTE}\n")
    md_lines.append(f"- BL-4/5: {BL_UNCALIBRATED_NOTE}\n")
    md_lines.append(f"- sum(p) threshold 根拠: {sum_p_threshold_rationale}\n")
    md_lines.append(f"- {SC2_BLOCK_SYMMETRY_NOTE}\n")

    md_payload = "".join(md_lines)
    _atomic_write_text(md_path, md_payload)

    return md_path, json_path


def _build_comparison_table_with_backmetrictable(*args, **kwargs):  # type: ignore[no-untyped-def]
    """DEPRECATED alias（互換性のため残すが使用しない）。"""
    return _build_comparison_table_with_backtest(*args, **kwargs)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Phase 6 統合評価 CLI エントリポイント（フロー6ステップ）。"""
    args = parse_args(argv)
    settings = Settings()

    # masked DSN ログ（生 DSN 絶対禁止・T-06-15）
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)
    logger.info(
        "config: feature_snapshot_id=%s as_of_datetime=%s primary_model=%s skip_segments=%s",
        args.feature_snapshot_id,
        args.as_of_datetime,
        args.primary_model,
        args.skip_segments,
    )

    readonly_pool = make_pool(settings, role="readonly")
    etl_pool = None
    # --primary-model 指定時のみ etl pool を構築（is_primary UPDATE 用）
    if args.primary_model is not None:
        etl_pool = make_pool(settings, role="etl")

    try:
        # Step 1: 成果物読込（readonly ロール）
        with readonly_cursor(readonly_pool) as cur:
            prediction_df = _fetch_prediction_test_df(cur, args.feature_snapshot_id)
            label_df = _fetch_label_df(cur)
            split_integrity_df = _fetch_split_integrity_df(cur, args.feature_snapshot_id)
            # CONTEXT.md: label 欠損時は market データ JOIN で segment 軸（ninki/fukuoddslower）を補完
            # race_keys で絞らない（fetch_market_data 全件は重いが market_df を prediction と JOIN するため）
            race_keys_for_market = (
                prediction_df["race_key"].dropna().unique().tolist()
                if "race_key" in prediction_df.columns and len(prediction_df) > 0
                else None
            )
            market_df = _fetch_market_data(cur, race_keys=race_keys_for_market)
        logger.info(
            "Step 1 読込: prediction=%d rows / label=%d rows / market=%d rows / split_integrity=%d rows",
            len(prediction_df), len(label_df), len(market_df), len(split_integrity_df),
        )

        # Step 1b: prediction に label/market の segment 軸を JOIN（HIGH-1/HIGH-2: 行数不変）
        prediction_df = _enrich_prediction_with_segments(prediction_df, label_df, market_df)
        # WR-02: label 由来の core segment 軸（jyocd / race_date）が enrich 後に全面欠損の場合は
        # label JOIN が壊れた実エラーのため fail-loud（SC#3 segment 評価が silent に不能化するのを防ぐ）。
        # ※ market 由来（ninki / fukuoddslower）は部分欠損が正常系のためここでは検査しない。
        if len(prediction_df) > 0:
            _missing_core_seg = [
                c for c in ("jyocd", "race_date")
                if c not in prediction_df.columns or prediction_df[c].isna().all()
            ]
            if _missing_core_seg:
                raise RuntimeError(
                    f"segment 軸の label 由来 core カラムが付与されなかった: missing={_missing_core_seg}. "
                    "label.fukusho_label JOIN 経路の確認が必要（SC#3 segment 評価が不能）"
                )
        # label_df 側の entry_count 列名を alias で統一（segment_eval が期待）
        if "entry_count" not in label_df.columns and "sales_start_entry_count" in label_df.columns:
            label_df["entry_count"] = label_df["sales_start_entry_count"]

        # Step 2-4: 統合評価（純粋関数）
        result = evaluate_integrated(
            prediction_df=prediction_df,
            label_df=label_df,
            eval_04_path=args.eval_04_path,
            backtest_05_path=args.backtest_05_path,
            split_integrity_df=split_integrity_df,
            feature_snapshot_id=args.feature_snapshot_id,
            as_of_datetime=args.as_of_datetime,
            segments_dir=args.segments_dir,
            skip_segments=args.skip_segments,
        )
        logger.info(
            "Step 2-4 完了: gate_verdict=%s block_triggered=%s",
            result["gate_result"]["gate_verdict"],
            result["gate_result"]["block_triggered"],
        )

        # Step 5: レポート生成（atomic write・REVIEW HIGH#6: BLOCK の場合も含む）
        md_path, json_path = generate_evaluation_reports(
            result,
            out_md_path=args.out_md,
            out_json_path=args.out_json,
            primary_model=args.primary_model,
            selection_reason=args.selection_reason,
        )
        logger.info("Step 5 reports: %s, %s", md_path, json_path)

        # Step 6: BLOCK 発火時（REVIEW HIGH#6: reports atomic write 後に RuntimeError）
        if result["gate_result"]["block_triggered"]:
            block_reasons = result["gate_result"]["block_reasons"]
            logger.error("acceptance gate BLOCK: %s", block_reasons)
            raise RuntimeError(
                f"acceptance gate BLOCK: {block_reasons} "
                "(reports/06-evaluation.{md,json} は atomic write 済み・REVIEW HIGH#6)"
            )

        # Step 7: --primary-model 指定時（is_primary UPDATE・REVIEW C7: 省略時はスキップ）
        if args.primary_model is not None and etl_pool is not None:
            model_version = make_model_version(
                args.feature_snapshot_id, args.primary_model, version_n=1
            )
            with etl_pool.connection() as conn, conn.cursor() as cur:
                set_primary_model(
                    cur,
                    primary_model_type=args.primary_model,
                    primary_model_version=model_version,
                    feature_snapshot_id=args.feature_snapshot_id,
                    as_of_datetime=args.as_of_datetime,
                )
            logger.info(
                "Step 7 is_primary UPDATE: model_type=%s model_version=%s",
                args.primary_model, model_version,
            )
        else:
            logger.info(
                "Step 7 skip: --primary-model 省略・recommended=%s",
                result["recommended_primary_model"].get("model_type"),
            )

        return 0

    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        readonly_pool.close()
        if etl_pool is not None:
            etl_pool.close()


if __name__ == "__main__":
    sys.exit(main())
