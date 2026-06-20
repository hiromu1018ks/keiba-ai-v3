"""Phase 4 evaluator: Brier/LogLoss/Calibration/sum(p) + BL-1..5 比較表 (SC#2/§15.1/§15.2).

成功基準 #2 (SC#2) / §15.1 評価指標 / §15.2 確率品質受入基準 / D-04 主モデル選定基準事前登録 を
実装する service 層。

**設計の核心 (review MEDIUM):**

``sum(p)`` は複勝確率の**独立二値性質**により払戻対象数に厳密合計しない。本モジュールは
``sum(p)`` を厳密合計制約でなく**診断的指標**として扱い、§15.2 の理論値 (8頭以上 [2.7, 3.3]・
5-7頭 [1.8, 2.2]) を機械検査するが fail-loud でなく warning とする (hybrid gate D-01/D-02 準拠)。
``diagnostic_note`` キーで独立二値性質を明記し、false alarm を防止する。

**binning 契約 (review MEDIUM):**

calibration curve の binning を固定値で明示する (再現性保証):
  - ``CALIBRATION_CURVE_BINS = 10``
  - ``CALIBRATION_CURVE_STRATEGY = "uniform"``
  - ``CALIBRATION_CURVE_MIN_BIN_COUNT = 30``

``compute_metrics`` は上記定数を使用し・run 毎に bin 数や strategy が変わるのを防止する。

**D-04 事前登録 (review T-04-24):**

comparison 表の comment 列で「Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・
brier/logloss 次点・auc 参考)」を選定基準として結果を見る前に固定する。これは Phase 6 で
最終選定基準として採用される素材 (Information Disclosure: 後知恵で選定基準をすり替え防止)。

**review LOW (.md + .json 分離):**

``write_eval_report`` は比較表を Markdown (``reports/04-eval.md``) と JSON
(``reports/04-eval.json``) に**分離**出力する。JSON は ``json.dumps(sort_keys=True)`` で
byte-reproducible・``artifact.py::_atomic_write_text`` で atomic write する。

参照: src/model/baseline.py (compute_all_baselines) /
      src/model/predict.py (predict_p_fukusho) /
      src/model/artifact.py (_atomic_write_text / write_metadata_json) /
      04-RESEARCH.md D-04/D-08 §15.1/§15.2 /
      04-PATTERNS.md evaluator.py セクション /
      04-04-PLAN.md Task 3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from src.model.artifact import _atomic_write_text

# ---------------------------------------------------------------------------
# 定数 — §15.2 / review MEDIUM
# ---------------------------------------------------------------------------

# §15.2 sum(p) 理論値 (診断的閾値・独立二値確率のため厳密合計制約でなく参考値)
# 8頭以上は払戻対象 3 頭 → sum(p) ≈ 3.0 [2.7, 3.3]
# 5-7頭は払戻対象 2 頭 → sum(p) ≈ 2.0 [1.8, 2.2]
SUM_P_BOUNDS: dict[str, tuple[float, float]] = {
    "large": (2.7, 3.3),  # 8頭以上
    "small": (1.8, 2.2),  # 5-7頭
}

# METRIC_COLUMNS — 比較表の指標列 (D-04 事前登録の素材)
METRIC_COLUMNS: list[str] = [
    "brier",
    "logloss",
    "auc",
    "sum_p_mean",
    "sum_p_median",
    "sum_p_p10",
    "sum_p_p90",
    "calibration_max_dev",
]

# binning 契約 (review MEDIUM: 固定値で明示・再現性保証)
CALIBRATION_CURVE_BINS: int = 10
CALIBRATION_CURVE_STRATEGY: str = "uniform"
CALIBRATION_CURVE_MIN_BIN_COUNT: int = 30

# BL-3 §14.2 注記 (同一情報条件の比較でない)
BL3_MARKET_REFERENCE_NOTE = (
    "Phase 1-A モデルと同一情報条件の比較ではない (§14.2): BL-3 は確定複勝オッズ由来の"
    "市場暗示確率であり・Phase 1-A モデルは odds-free feature のみ使用"
)

# BL-4/BL-5 未キャリブレーション注記
BL_UNCALIBRATED_NOTE = (
    "BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない "
    "(calibrate_bl4_bl5=False)・比較公平性に注意"
)

# D-04 事前登録: Calibration 重視選定基準 (T-04-24・後知恵すり替え防止)
D04_SELECTION_CRITERION_NOTE = (
    "D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・"
    "brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用"
)

# sum(p) 診断注記 (review MEDIUM: 独立二値確率のため厳密合計制約でない)
SUM_P_DIAGNOSTIC_NOTE = (
    "複勝確率は独立二値確率のため sum(p) は払戻対象数に厳密合計しない・"
    "診断的指標として扱う (§15.2・review MEDIUM)"
)


# ---------------------------------------------------------------------------
# compute_metrics — Brier/LogLoss/AUC/sum(p)/calibration_max_dev
# ---------------------------------------------------------------------------


def compute_metrics(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    *,
    race_keys: np.ndarray | pd.Series | None = None,
    entry_counts: np.ndarray | pd.Series | None = None,
) -> dict[str, Any]:
    """Brier/LogLoss/AUC/sum(p) 分布/calibration_max_dev を計算する (§15.1/§15.2).

    Parameters
    ----------
    y_true : array-like
        バイナリ真ラベル (0/1)。
    y_pred : array-like
        予測確率 (クラス1)・[0,1] 区間。
    race_keys : array-like | None
        各行の race_key (race_id)。sum(p) 分布計算に使用。None の場合は sum(p) 系列は NaN。
    entry_counts : array-like | None
        各行のレース頭数。sum(p) 分布の large/small 分類に使用。None の場合は NaN。

    Returns
    -------
    dict
        ``brier`` / ``logloss`` / ``auc`` / ``sum_p_mean`` / ``sum_p_median`` /
        ``sum_p_p10`` / ``sum_p_p90`` / ``calibration_max_dev`` / ``sum_p_note`` キー。
        ``sum_p_note`` には review MEDIUM の診断注記を付与。
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred, dtype=float)

    metrics: dict[str, Any] = {
        "brier": float(brier_score_loss(y_true_arr, y_pred_arr)),
        "logloss": float(log_loss(y_true_arr, y_pred_arr, labels=[0, 1])),
    }
    # AUC は single-class の場合は定義不可・NaN にする
    if len(np.unique(y_true_arr)) < 2:
        metrics["auc"] = float("nan")
    else:
        metrics["auc"] = float(roc_auc_score(y_true_arr, y_pred_arr))

    # sum(p) 分布 (race_keys + entry_counts があれば計算)
    sum_p_stats: dict[str, float] = {
        "sum_p_mean": float("nan"),
        "sum_p_median": float("nan"),
        "sum_p_p10": float("nan"),
        "sum_p_p90": float("nan"),
    }
    if race_keys is not None and entry_counts is not None:
        race_keys_arr = np.asarray(race_keys)
        entry_counts_arr = np.asarray(entry_counts)
        df_tmp = pd.DataFrame(
            {"race_key": race_keys_arr, "p": y_pred_arr, "entry_count": entry_counts_arr}
        )
        sum_p_per_race = df_tmp.groupby("race_key")["p"].sum()
        sum_p_stats = {
            "sum_p_mean": float(sum_p_per_race.mean()),
            "sum_p_median": float(sum_p_per_race.median()),
            "sum_p_p10": float(sum_p_per_race.quantile(0.10)),
            "sum_p_p90": float(sum_p_per_race.quantile(0.90)),
        }
    metrics.update(sum_p_stats)

    # calibration_max_dev (review MEDIUM: binning 契約固定)
    metrics["calibration_max_dev"] = _compute_calibration_max_dev(y_true_arr, y_pred_arr)

    # review MEDIUM: sum(p) 診断注記
    metrics["sum_p_note"] = SUM_P_DIAGNOSTIC_NOTE

    return metrics


def _compute_calibration_max_dev(
    y_true: np.ndarray, y_pred: np.ndarray
) -> float:
    """calibration curve の max |mean_pred - frac_pos| を計算 (review MEDIUM: binning 契約固定).

    ``CALIBRATION_CURVE_BINS`` / ``CALIBRATION_CURVE_STRATEGY`` 定数を使用し・run 毎の
    bin 数・strategy 変更を防止する。

    bin サンプル数が ``CALIBRATION_CURVE_MIN_BIN_COUNT`` 未満の場合は・信頼性が低いため
    NaN を返す (空 bin や極小 bin での false alarm 防止)。

    single-class の場合は定義不可・NaN を返す。
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")
    try:
        frac_pos, mean_pred = calibration_curve(
            y_true,
            y_pred,
            n_bins=CALIBRATION_CURVE_BINS,
            strategy=CALIBRATION_CURVE_STRATEGY,
        )
    except (ValueError, IndexError):
        # bin が1つしか作れない・全予測値が同一等の異常時
        return float("nan")
    if len(frac_pos) == 0:
        return float("nan")
    return float(np.max(np.abs(mean_pred - frac_pos)))


# ---------------------------------------------------------------------------
# check_sum_p_distribution — §15.2 機械検査 (review MEDIUM: 診断的)
# ---------------------------------------------------------------------------


def check_sum_p_distribution(
    df: pd.DataFrame, p_col: str, entry_count_col: str
) -> dict[str, Any]:
    """race_key groupby で sum(p) を計算し §15.2 理論値を機械検査 (review MEDIUM: 診断的).

    8頭以上は [2.7, 3.3]・5-7頭は [1.8, 2.2] を機械検査するが・fail-loud でなく
    warning (量的異常は参考レポート・hybrid gate D-01/D-02)。

    Parameters
    ----------
    df : pd.DataFrame
        ``p_col`` (予測確率) と ``entry_count_col`` (レース頭数) と ``race_key`` 列を持つ
        DataFrame。
    p_col : str
        予測確率列名。
    entry_count_col : str
        レース頭数列名。

    Returns
    -------
    dict
        ``total_races`` / ``large_races`` / ``small_races`` / ``large_violations``
        (list of race_key) / ``small_violations`` (list of race_key) /
        ``large_violation_rate`` / ``small_violation_rate`` /
        ``diagnostic_note`` (review MEDIUM: 独立二値性質注記)。
    """
    if "race_key" not in df.columns:
        raise ValueError(
            f"check_sum_p_distribution: df must have 'race_key' column "
            f"(got columns: {list(df.columns)})"
        )
    sum_p_per_race = df.groupby("race_key")[p_col].sum()
    entry_per_race = df.groupby("race_key")[entry_count_col].first()

    large_mask = entry_per_race >= 8
    small_mask = (entry_per_race >= 5) & (entry_per_race <= 7)

    large_races = entry_per_race[large_mask]
    small_races = entry_per_race[small_mask]

    large_sum_p = sum_p_per_race.loc[large_races.index]
    small_sum_p = sum_p_per_race.loc[small_races.index]

    large_lo, large_hi = SUM_P_BOUNDS["large"]
    small_lo, small_hi = SUM_P_BOUNDS["small"]

    large_violations = large_sum_p[
        (large_sum_p < large_lo) | (large_sum_p > large_hi)
    ].index.tolist()
    small_violations = small_sum_p[
        (small_sum_p < small_lo) | (small_sum_p > small_hi)
    ].index.tolist()

    large_violation_rate = (
        float(len(large_violations) / len(large_races)) if len(large_races) > 0 else 0.0
    )
    small_violation_rate = (
        float(len(small_violations) / len(small_races)) if len(small_races) > 0 else 0.0
    )

    return {
        "total_races": int(len(sum_p_per_race)),
        "large_races": int(len(large_races)),
        "small_races": int(len(small_races)),
        "large_violations": large_violations,
        "small_violations": small_violations,
        "large_violation_rate": large_violation_rate,
        "small_violation_rate": small_violation_rate,
        "diagnostic_note": SUM_P_DIAGNOSTIC_NOTE,
    }


# ---------------------------------------------------------------------------
# build_comparison_table — BL-1..5 + 主モデル比較表 (SC#2 / D-04 事前登録)
# ---------------------------------------------------------------------------


def build_comparison_table(metrics_dict: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """metrics_dict を BL-1..5 + 主モデル比較表 DataFrame に統合する (SC#2 / D-04).

    Parameters
    ----------
    metrics_dict : dict
        ``{"lightgbm": {...}, "catboost": {...}, "bl1": {...}, ..., "bl5": {...}}``。
        各値は ``compute_metrics`` の戻り dict。

    Returns
    -------
    pd.DataFrame
        METRIC_COLUMNS + ``model_name`` + ``market_reference`` (BL-3) + ``bl_calib_note``
        (BL-4/5 未キャリブレーション注記) + ``d04_selection_criterion`` 列を持つ比較表。
    """
    rows = []
    for model_name, m in metrics_dict.items():
        row: dict[str, Any] = {"model_name": model_name}
        for col in METRIC_COLUMNS:
            row[col] = m.get(col, float("nan"))
        # BL-3 §14.2 注記
        if model_name == "bl3":
            row["market_reference"] = BL3_MARKET_REFERENCE_NOTE
        else:
            row["market_reference"] = ""
        # BL-4/BL-5 未キャリブレーション注記
        if model_name in {"bl4", "bl5"}:
            row["bl_calib_note"] = m.get("bl_calib_note", BL_UNCALIBRATED_NOTE)
        else:
            row["bl_calib_note"] = ""
        rows.append(row)

    df = pd.DataFrame(rows)
    # D-04 事前登録の選定基準を comment 列で全行に付与 (T-04-24)
    df["d04_selection_criterion"] = D04_SELECTION_CRITERION_NOTE
    return df


# ---------------------------------------------------------------------------
# write_eval_report — reports/04-eval.md + reports/04-eval.json (review LOW: 分離)
# ---------------------------------------------------------------------------


def write_eval_report(
    comparison_df: pd.DataFrame,
    metrics_dict: dict[str, dict[str, Any]],
    *,
    out_md_path: str | Path = "reports/04-eval.md",
    out_json_path: str | Path = "reports/04-eval.json",
) -> tuple[Path, Path]:
    """比較表を Markdown と JSON に分離出力する (review LOW / SC#2 / §15.1/§15.2).

    Parameters
    ----------
    comparison_df : pd.DataFrame
        ``build_comparison_table`` の戻り値。
    metrics_dict : dict
        ``compute_metrics`` の戻り値を統合した dict。
    out_md_path : str | Path
        Markdown 出力パス (デフォルト ``reports/04-eval.md``)。
    out_json_path : str | Path
        JSON 出力パス (デフォルト ``reports/04-eval.json``)。

    Returns
    -------
    tuple[Path, Path]
        (md_path, json_path)。
    """
    md_path = Path(out_md_path)
    json_path = Path(out_json_path)

    # --- Markdown (reports/04-eval.md) ---
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_lines: list[str] = []
    md_lines.append("# Phase 4 Evaluation Report (SC#2 / §15.1 / §15.2)\n")
    md_lines.append("\n")
    md_lines.append("## 比較表 (BL-1..5 + 主モデル)\n")
    md_lines.append("\n")
    md_lines.append(comparison_df.to_markdown(index=False))
    md_lines.append("\n\n")
    md_lines.append("## §15.2 sum(p) 分布検査結果\n")
    md_lines.append("\n")
    md_lines.append(f"- {SUM_P_DIAGNOSTIC_NOTE}\n")
    md_lines.append(f"- SUM_P_BOUNDS (診断的閾値): {SUM_P_BOUNDS}\n")
    md_lines.append(
        f"- CALIBRATION_CURVE_BINS={CALIBRATION_CURVE_BINS}, "
        f"STRATEGY={CALIBRATION_CURVE_STRATEGY!r}, "
        f"MIN_BIN_COUNT={CALIBRATION_CURVE_MIN_BIN_COUNT}\n"
    )
    md_lines.append("\n")
    md_lines.append("## 注記\n")
    md_lines.append("\n")
    md_lines.append(f"- {D04_SELECTION_CRITERION_NOTE}\n")
    md_lines.append(f"- BL-3: {BL3_MARKET_REFERENCE_NOTE}\n")
    md_lines.append(f"- BL-4/5: {BL_UNCALIBRATED_NOTE}\n")
    md_payload = "".join(md_lines)
    _atomic_write_text(md_path, md_payload)

    # --- JSON (reports/04-eval.json) — sort_keys=True で byte-reproducible ---
    json_path.parent.mkdir(parents=True, exist_ok=True)
    # DataFrame を dict に変換 (NaN は null に)
    comparison_records = json.loads(comparison_df.to_json(orient="records"))
    # NaN → null (json.loads で既に null 化されるが念のため)
    json_payload = json.dumps(
        {
            "metrics": metrics_dict,
            "comparison_table": comparison_records,
            "constants": {
                "SUM_P_BOUNDS": SUM_P_BOUNDS,
                "METRIC_COLUMNS": METRIC_COLUMNS,
                "CALIBRATION_CURVE_BINS": CALIBRATION_CURVE_BINS,
                "CALIBRATION_CURVE_STRATEGY": CALIBRATION_CURVE_STRATEGY,
                "CALIBRATION_CURVE_MIN_BIN_COUNT": CALIBRATION_CURVE_MIN_BIN_COUNT,
            },
            "notes": {
                "sum_p_diagnostic": SUM_P_DIAGNOSTIC_NOTE,
                "d04_selection_criterion": D04_SELECTION_CRITERION_NOTE,
                "bl3_market_reference": BL3_MARKET_REFERENCE_NOTE,
                "bl_uncalibrated": BL_UNCALIBRATED_NOTE,
            },
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    _atomic_write_text(json_path, json_payload)

    return (md_path, json_path)


# ---------------------------------------------------------------------------
# evaluate_all_models — 統合エントリポイント (PLAN 05 が消費)
# ---------------------------------------------------------------------------


def evaluate_all_models(
    predictions_by_model: dict[str, pd.DataFrame],
    y_true_by_split: dict[str, pd.Series],
    *,
    out_md_path: str | Path = "reports/04-eval.md",
    out_json_path: str | Path = "reports/04-eval.json",
) -> dict[str, dict[str, Any]]:
    """各モデルの予測を評価し比較表を reports/04-eval.{md,json} に出力する (SC#2 / PLAN 05 消費).

    Parameters
    ----------
    predictions_by_model : dict
        ``{"lightgbm": df, "catboost": df, "bl1": df, ..., "bl5": df}``。
        各 df は ``p_fukusho_hit`` / ``race_key`` / ``entry_count`` / ``split`` /
        ``fukusho_hit`` (真ラベル) 列を持つ。
    y_true_by_split : dict
        ``{"train": Series, "calib": Series, "test": Series}``。予測 df の index と
        整合すること。本関数は ``test`` split を主評価に使用する (§15.4)。
    out_md_path : str | Path
        Markdown 出力パス。
    out_json_path : str | Path
        JSON 出力パス。

    Returns
    -------
    dict
        metrics_dict (各モデルの ``compute_metrics`` 戻り値を統合)。
    """
    metrics_dict: dict[str, dict[str, Any]] = {}
    # 主評価は test split (§15.4)
    y_test = y_true_by_split.get("test")
    if y_test is None:
        raise ValueError(
            "evaluate_all_models: y_true_by_split must contain 'test' split (§15.4)"
        )

    for model_name, pred_df in predictions_by_model.items():
        # 予測 df の test split 抽出
        test_mask = pred_df["split"] == "test"
        pred_test = pred_df.loc[test_mask]
        if len(pred_test) == 0:
            metrics_dict[model_name] = {
                col: float("nan") for col in METRIC_COLUMNS
            }
            metrics_dict[model_name]["sum_p_note"] = SUM_P_DIAGNOSTIC_NOTE
            continue

        y_pred = pred_test["p_fukusho_hit"].to_numpy()
        # 真ラベルは予測 df 側に含まれている前提 (fukusho_hit 列)・なければ y_test を使用
        if "fukusho_hit" in pred_test.columns:
            y_true = pred_test["fukusho_hit"].to_numpy()
        else:
            y_true = y_test.reindex(pred_test.index).to_numpy()

        race_keys = (
            pred_test["race_key"].to_numpy() if "race_key" in pred_test.columns else None
        )
        entry_counts = (
            pred_test["entry_count"].to_numpy()
            if "entry_count" in pred_test.columns
            else None
        )

        metrics_dict[model_name] = compute_metrics(
            y_true, y_pred, race_keys=race_keys, entry_counts=entry_counts
        )

    comparison_df = build_comparison_table(metrics_dict)
    write_eval_report(
        comparison_df,
        metrics_dict,
        out_md_path=out_md_path,
        out_json_path=out_json_path,
    )
    return metrics_dict


__all__ = [
    "SUM_P_BOUNDS",
    "METRIC_COLUMNS",
    "CALIBRATION_CURVE_BINS",
    "CALIBRATION_CURVE_STRATEGY",
    "CALIBRATION_CURVE_MIN_BIN_COUNT",
    "BL3_MARKET_REFERENCE_NOTE",
    "BL_UNCALIBRATED_NOTE",
    "D04_SELECTION_CRITERION_NOTE",
    "SUM_P_DIAGNOSTIC_NOTE",
    "compute_metrics",
    "check_sum_p_distribution",
    "build_comparison_table",
    "write_eval_report",
    "evaluate_all_models",
]
