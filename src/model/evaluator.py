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
from scipy.stats import spearmanr
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
# - calibration_max_dev:        事前登録定義 (ガードなし)。docstring 通りに実装された
#   「sklearn.calibration_curve(strategy='uniform', n_bins=10) の max|mean_pred - frac_pos|」。
#   極小サンプル bin の統計ノイズが無防備に現れるが・D-04 事前登録の指標定義として固定 (後知恵
#   すり替え防止 T-04-24)。
# - calibration_max_dev_guarded: 事前登録 docstring が意図した MIN_BIN_COUNT=30 per-bin ガード
#   を実装した補助指標 (debug: calib-maxdev-vs-baselines)。両指標を併記し・ガードの有無による
#   差を観察可能にする。比較表では両者を隣接列で提示。
METRIC_COLUMNS: list[str] = [
    "brier",
    "logloss",
    "auc",
    "sum_p_mean",
    "sum_p_median",
    "sum_p_p10",
    "sum_p_p90",
    "calibration_max_dev",
    "calibration_max_dev_guarded",
]

# binning 契約 (review MEDIUM: 固定値で明示・再現性保証)
CALIBRATION_CURVE_BINS: int = 10
CALIBRATION_CURVE_STRATEGY: str = "uniform"
CALIBRATION_CURVE_MIN_BIN_COUNT: int = 30

# ---------------------------------------------------------------------------
# Phase 6 (Plan 06-02) 新規定数 — D-05 新指標 / D-02 構造的 BLOCK 閾値
# 既存 METRIC_COLUMNS / CALIBRATION_CURVE_* は一切変更しない（D-04 事前登録指標不変・T-04-24 回避）
# ---------------------------------------------------------------------------

# METRIC_COLUMNS_EXTENDED — 事前登録 9 列に Phase 6 の新指標 3 列を追加（D-05）
# METRIC_COLUMNS（事前登録・ガードなし max_dev 含む）は不変・拡張リストは別名で定義
METRIC_COLUMNS_EXTENDED: list[str] = METRIC_COLUMNS + [
    "quantile_max_dev",  # D-05: quantile bin の max|dev|（BL-1 bin 退化バイアス解除）
    "ece",  # D-05: Expected Calibration Error（Naeini 2015・重み付け平均）
    "mce",  # D-05: Maximum Calibration Error（worst-case・MIN_BIN_COUNT ガード付き）
]

# SUM_P_BLOCK_THRESHOLD — D-02 構造的 BLOCK 条件2（sum(p) 著乖離）の閾値
# §15.2 [2.7,3.3]/[1.8,2.2] から 30% 超違反で BLOCK（large/small いずれかの bucket）
# REVIEW HIGH#5: 0.30 は仮置き・Plan 06-05 Wave 3 Step 3a で実データ violation_rate を
# 計測し偽陽性 BLOCK を出さないか検証する。現データ LightGBM sum_p_mean=3.04 でほぼ 0% 想定。
SUM_P_BLOCK_THRESHOLD: float = 0.30

# COMPARABLE_BASELINES — D-02 構造的 BLOCK 条件1（baselines 全敗）の比較対象
# BL-2 (NaN・single-class 未定義) / BL-3 (§14.2 caveat・同一情報条件でない市場暗示確率) は除外
COMPARABLE_BASELINES: tuple[str, ...] = ("bl1", "bl4", "bl5")

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


def _df_to_markdown_table(df: pd.DataFrame) -> str:
    """DataFrame を Markdown 表形式文字列に変換する (tabulate 非依存・Rule 3 auto-fix)。

    ``df.to_markdown()`` は optional dependency の ``tabulate`` を要求するが・本プロジェクトの
    pyproject.toml は ``tabulate`` を含まない。依存関係追加を避けるため・手動で Markdown 表を
    構築する (PLAN 05 E2E 実行の blocking issue 解消)。
    """
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
        ``sum_p_p10`` / ``sum_p_p90`` / ``calibration_max_dev`` /
        ``calibration_max_dev_guarded`` / ``sum_p_note`` キー。
        ``calibration_max_dev`` は事前登録定義 (ガードなし)・
        ``calibration_max_dev_guarded`` は MIN_BIN_COUNT=30 per-bin ガード付き補助指標
        (debug: calib-maxdev-vs-baselines)。両者を併記しガード有無の差を観察する。
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
    # 事前登録定義 (ガードなし) と docstring が意図した MIN_BIN_COUNT=30 ガード付き補助指標を併記
    # (debug: calib-maxdev-vs-baselines)。後知恵すり替え防止のため事前登録指標は不変。
    metrics["calibration_max_dev"] = _compute_calibration_max_dev(y_true_arr, y_pred_arr)
    metrics["calibration_max_dev_guarded"] = _compute_calibration_max_dev_guarded(
        y_true_arr, y_pred_arr
    )

    # Phase 6 (Plan 06-02) D-05 新指標: quantile_max_dev / ECE / MCE
    # 事前登録 calibration_max_dev / _guarded は上記の通り不変（D-04・T-04-24）
    metrics["quantile_max_dev"] = _compute_quantile_max_dev(y_true_arr, y_pred_arr)
    metrics["ece"] = _compute_ece(
        y_true_arr, y_pred_arr, strategy="quantile", n_bins=CALIBRATION_CURVE_BINS
    )
    metrics["mce"] = _compute_mce(
        y_true_arr,
        y_pred_arr,
        strategy="quantile",
        n_bins=CALIBRATION_CURVE_BINS,
        min_bin_count=CALIBRATION_CURVE_MIN_BIN_COUNT,
    )

    # review MEDIUM: sum(p) 診断注記
    metrics["sum_p_note"] = SUM_P_DIAGNOSTIC_NOTE

    return metrics


def _compute_calibration_max_dev(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """calibration curve の max |mean_pred - frac_pos| を計算 (review MEDIUM: binning 契約固定).

    ``CALIBRATION_CURVE_BINS`` / ``CALIBRATION_CURVE_STRATEGY`` 定数を使用し・run 毎の
    bin 数・strategy 変更を防止する。

    **注意 (事前登録定義・ガードなし):** 本関数は D-04 事前登録の指標定義として固定されており・
    bin サンプル数によるガードを行わない。従って ``CALIBRATION_CURVE_MIN_BIN_COUNT`` 定数を
    参照しない。極小サンプル bin (例: count=13) の統計ノイズが max_dev に無防備に反映されるが・
    これは事前登録時点の仕様 (後知恵すり替え防止 T-04-24)。
    ガード付き補助指標は :func:`_compute_calibration_max_dev_guarded` を参照のこと。

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


def _compute_calibration_max_dev_guarded(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """calibration curve の max |mean_pred - frac_pos| を計算 (MIN_BIN_COUNT per-bin ガード付き).

    :func:`_compute_calibration_max_dev` と同じ binning 契約
    (``CALIBRATION_CURVE_BINS`` / ``CALIBRATION_CURVE_STRATEGY``) を使用するが・各 bin の
    サンプル数が ``CALIBRATION_CURVE_MIN_BIN_COUNT`` (30) 未満の bin を max 計算から除外する。
    全ての bin が基準未満 (残り 0 bin) の場合は NaN を返す。

    **実装 (Specialist SUGGEST_CHANGE 準拠・bit-identical 再現性):**
      sklearn 1.9 の ``calibration_curve`` は count を返さず・空 bin を除外して整列を返すため・
      bin と count の対応付けが自明でない。本関数は ``calibration_curve`` を呼ばず・
      ``np.linspace(0, 1, n_bins+1)`` + ``np.digitize`` + ``np.bincount`` で bin ごとに
      (mean_pred, frac_pos, count) を自前計算する。これにより戻り値と count 配列は構造的に
      整列する (pandas.groupby/sort は等値要素の index 依存で再現性リスク → 不使用)。
      境界値 ``y_pred == 1.0`` は ``np.digitize`` で out-of-range になるため ``np.clip`` で
      ``[0, n_bins-1]`` にクリップ (LightGBM worst bin の mean_pred=1.0 の count を正確に捕捉)。

    **非対称性に関する注記 (debug: calib-maxdev-vs-baselines):**
      本ガードは LightGBM の worst bin (count=13 < 30) を除外し max_dev を
      0.2308 → 0.1005 に改善する。一方 CatBoost の worst bin (count=59 > 30) はガード対象外
      のため 0.2579 のまま変化しない。これは CatBoost の高確率域 (pred > 0.7) に残存する
      **本質的 miscalibration** (副因 C・Phase 6 領域) を示唆するものであり・ガードの不備ではない。

    single-class の場合は定義不可・NaN を返す。
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")

    n_bins = CALIBRATION_CURVE_BINS
    strategy = CALIBRATION_CURVE_STRATEGY
    if strategy != "uniform":
        # 本関数は strategy='uniform' を前提とする (bin_edges を linspace で構築)。
        # 'quantile' は別途 data-driven な bin_edges が必要になるため未サポート。
        return float("nan")

    min_bin_count = CALIBRATION_CURVE_MIN_BIN_COUNT

    # bin ごとに (mean_pred, frac_pos, count) を自前計算
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    # 境界値 1.0 が out-of-range になるのを防ぐため digitize 後に clip
    bin_idx_full = np.digitize(y_pred, bins=bin_edges[1:-1], right=False)
    bin_idx_clipped = np.clip(bin_idx_full, 0, n_bins - 1)

    y_true_f = y_true.astype(float)
    # 各 bin のサンプル数・正例数・予測確率和
    counts_full = np.bincount(bin_idx_clipped, minlength=n_bins).astype(float)
    pos_sum_full = np.bincount(bin_idx_clipped, weights=y_true_f, minlength=n_bins)
    pred_sum_full = np.bincount(bin_idx_clipped, weights=y_pred, minlength=n_bins)

    # 空でない bin のみ抽出 (count > 0)
    nonempty_mask = counts_full > 0
    counts = counts_full[nonempty_mask]
    pos_sums = pos_sum_full[nonempty_mask]
    pred_sums = pred_sum_full[nonempty_mask]

    if len(counts) == 0:
        return float("nan")

    frac_pos = pos_sums / counts
    mean_pred = pred_sums / counts

    # 戻り値と count 配列の整列を assert (off-by-one 防止・Specialist 指摘 (b))
    # 自前計算のため構造的に整列するが・念のため長さを検証
    assert len(counts) == len(frac_pos) == len(mean_pred), (
        f"_compute_calibration_max_dev_guarded: alignment mismatch "
        f"len(counts)={len(counts)}, len(frac_pos)={len(frac_pos)}, "
        f"len(mean_pred)={len(mean_pred)}"
    )

    # MIN_BIN_COUNT 未満の bin を除外
    keep_mask = counts >= min_bin_count
    if not np.any(keep_mask):
        # 全 bin が基準未満 → 信頼できる bin が無い
        return float("nan")

    devs = np.abs(mean_pred[keep_mask] - frac_pos[keep_mask])
    return float(np.max(devs))


# ---------------------------------------------------------------------------
# Phase 6 (Plan 06-02): 新規キャリブ指標ヘルパー（D-05・純 NumPy bit-identical）
# 既存 _compute_calibration_max_dev / _compute_calibration_max_dev_guarded は一切変更しない
# （D-04 事前登録指標不変・T-04-24 回避）。strategy='quantile' の bin_edges 構築は
# np.unique(np.quantile(...)) で重複 edge を削除（BL-1 離散値対策・Pitfall 1）。
# y_pred==1.0 は np.clip で最終 bin に（Pitfall 2・Specialist 指摘 (b) と同一パターン）。
# 整列 assert で off-by-one 防止（Specialist 指摘 (c)）。
# ---------------------------------------------------------------------------


def _compute_calibration_curve_bins(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    strategy: str,
    n_bins: int = CALIBRATION_CURVE_BINS,
    min_bin_count: int = CALIBRATION_CURVE_MIN_BIN_COUNT,
) -> dict[str, np.ndarray]:
    """bin ごとに (mean_pred, frac_pos, counts, bin_edges) を純 NumPy で計算（bit-identical）。

    Phase 6 (Plan 06-02) 新規ヘルパー。既存 ``_compute_calibration_max_dev_guarded``
    の binning パターン（np.linspace + digitize + bincount + clip）を切り出し・
    ``strategy`` 引数で ``'uniform'`` と ``'quantile'`` を切替可能にする。

    Parameters
    ----------
    y_true : np.ndarray
        バイナリ真ラベル (0/1)。
    y_pred : np.ndarray
        予測確率・[0,1] 区間。
    strategy : str
        ``'uniform'``: ``np.linspace(0,1,n+1)`` で等幅 bin
        （既存 ``_compute_calibration_max_dev_guarded`` と同一）。
        ``'quantile'``: ``np.unique(np.quantile(y_pred, np.linspace(0,1,n+1)))`` で等頻度 bin。
        重複 edge は ``np.unique`` で削除（BL-1 離散値対策・Pitfall 1）。
    n_bins : int
        bin 数（``CALIBRATION_CURVE_BINS=10`` がデフォルト）。
    min_bin_count : int
        ガード閾値（``CALIBRATION_CURVE_MIN_BIN_COUNT=30``・本ヘルパー自身はガードしないが・
        呼出側 ``_compute_mce`` が counts 配列を使ってガードするため戻り値に含める）。

    Returns
    -------
    dict[str, np.ndarray]
        ``mean_pred`` / ``frac_pos`` / ``counts`` / ``bin_edges`` キー。
        空でない bin のみ抽出（count > 0）。整列は assert で保証。
        ``single-class`` の場合は空配列を返さず・呼出側で
        ``len(np.unique(y_true))<2`` で NaN 判定する。
        ``bin_edges`` は reference 用（実際に使用した境界値・重複削除後）。

    Notes
    -----
    - 戻り値の ``counts`` 配列は ``min_bin_count`` によるガードを**行わない**。
      ガードは呼出側（``_compute_mce`` 等）の責務。
    - ``y_pred==1.0`` の out-of-range は ``np.clip`` で ``[0, n_bins_actual-1]`` に捕捉
      （Specialist 指摘 (b)・既存 ``_compute_calibration_max_dev_guarded`` と同一パターン）。
    """
    if strategy == "uniform":
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    elif strategy == "quantile":
        # 重複 edge を np.unique で削除（BL-1 離散値で多数の同値が発生する・Pitfall 1）
        bin_edges = np.unique(np.quantile(y_pred, np.linspace(0.0, 1.0, n_bins + 1)))
    else:
        raise ValueError(f"_compute_calibration_curve_bins: unsupported strategy={strategy!r}")

    n_bins_actual = len(bin_edges) - 1
    if n_bins_actual < 1:
        # bin が構築不能（全予測値が同一等）・空配列を返す
        return {
            "mean_pred": np.array([], dtype=float),
            "frac_pos": np.array([], dtype=float),
            "counts": np.array([], dtype=float),
            "bin_edges": bin_edges,
        }

    # 境界値 1.0 が out-of-range になるのを防ぐため digitize 後に clip（Specialist 指摘 (b)）
    bin_idx_full = np.digitize(y_pred, bins=bin_edges[1:-1], right=False)
    bin_idx_clipped = np.clip(bin_idx_full, 0, n_bins_actual - 1)

    y_true_f = y_true.astype(float)
    counts_full = np.bincount(bin_idx_clipped, minlength=n_bins_actual).astype(float)
    pos_sum_full = np.bincount(bin_idx_clipped, weights=y_true_f, minlength=n_bins_actual)
    pred_sum_full = np.bincount(bin_idx_clipped, weights=y_pred, minlength=n_bins_actual)

    # 空でない bin のみ抽出（count > 0）
    nonempty_mask = counts_full > 0
    counts = counts_full[nonempty_mask]
    pos_sums = pos_sum_full[nonempty_mask]
    pred_sums = pred_sum_full[nonempty_mask]

    if len(counts) == 0:
        return {
            "mean_pred": np.array([], dtype=float),
            "frac_pos": np.array([], dtype=float),
            "counts": np.array([], dtype=float),
            "bin_edges": bin_edges,
        }

    frac_pos = pos_sums / counts
    mean_pred = pred_sums / counts

    # 整列 assert（off-by-one 防止・Specialist 指摘 (c)）
    assert len(counts) == len(frac_pos) == len(mean_pred), (
        f"_compute_calibration_curve_bins: alignment mismatch "
        f"len(counts)={len(counts)}, len(frac_pos)={len(frac_pos)}, "
        f"len(mean_pred)={len(mean_pred)}"
    )

    return {
        "mean_pred": mean_pred,
        "frac_pos": frac_pos,
        "counts": counts,
        "bin_edges": bin_edges,
    }


def _compute_quantile_max_dev(
    y_true: np.ndarray, y_pred: np.ndarray, *, n_bins: int = CALIBRATION_CURVE_BINS
) -> float:
    """quantile bin での worst-case max|frac_pos - mean_pred|（D-05・REVIEW C5: ガードなし）。

    ``strategy='quantile'`` の bin で ``max|dev|`` を計算するが・**MIN_BIN_COUNT ガードなし**
    （全 bin 対象）。事前登録 ``calibration_max_dev``（uniform・ガードなし）との対比を明確にする
    ため・``_compute_mce``（MIN_BIN_COUNT ガード付き）とは別実装とする（METRIC_COLUMNS_EXTENDED
    でも別列）。

    single-class の場合は定義不可・NaN を返す。
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy="quantile", n_bins=n_bins)
    if len(bins["counts"]) == 0:
        return float("nan")
    return float(np.max(np.abs(bins["frac_pos"] - bins["mean_pred"])))


def _compute_ece(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    strategy: str = "quantile",
    n_bins: int = CALIBRATION_CURVE_BINS,
) -> float:
    """ECE = Σ(n_m/N) × |frac_pos - mean_pred|（D-05・Naeini 2015・重み付け平均）。

    ``_compute_calibration_curve_bins`` を消費し・各 bin の ``|dev|`` をサンプル数で重み付け
    した平均を返す（robust 指標・worst-case bin に支配されない）。

    Parameters
    ----------
    strategy : str
        ``'quantile'``（デフォルト・BL-1 bin 退化バイアス解除）または ``'uniform'``。
    n_bins : int
        bin 数（``CALIBRATION_CURVE_BINS=10`` がデフォルト）。

    single-class の場合は定義不可・NaN を返す。空 bin の場合は NaN。
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy=strategy, n_bins=n_bins)
    if len(bins["counts"]) == 0:
        return float("nan")
    n_total = float(len(y_pred))
    devs = np.abs(bins["frac_pos"] - bins["mean_pred"])
    return float(np.sum(bins["counts"] / n_total * devs))


def _compute_mce(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    strategy: str = "quantile",
    n_bins: int = CALIBRATION_CURVE_BINS,
    min_bin_count: int = CALIBRATION_CURVE_MIN_BIN_COUNT,
) -> float:
    """MCE = max|dev|（D-05・worst-case・MIN_BIN_COUNT ガード付き）。

    ``_compute_calibration_curve_bins`` を消費し・``counts >= min_bin_count`` の bin のみ
    ``max|dev|`` を計算する。全 bin が基準未満（残り 0 bin）の場合は NaN。

    REVIEW C5: ``_compute_quantile_max_dev``（ガードなし）と定義を分離。本関数は
    MIN_BIN_COUNT ガード付きの worst-case・極小サンプル bin の統計ノイズを除外する。

    Parameters
    ----------
    strategy : str
        ``'quantile'``（デフォルト）または ``'uniform'``。
    n_bins : int
        bin 数。
    min_bin_count : int
        ガード閾値（``CALIBRATION_CURVE_MIN_BIN_COUNT=30`` がデフォルト）。

    single-class の場合は定義不可・NaN を返す。
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(
        y_true, y_pred, strategy=strategy, n_bins=n_bins, min_bin_count=min_bin_count
    )
    if len(bins["counts"]) == 0:
        return float("nan")
    keep_mask = bins["counts"] >= min_bin_count
    if not np.any(keep_mask):
        return float("nan")
    return float(np.max(np.abs(bins["frac_pos"][keep_mask] - bins["mean_pred"][keep_mask])))


# ---------------------------------------------------------------------------
# check_sum_p_distribution — §15.2 機械検査 (review MEDIUM: 診断的)
# ---------------------------------------------------------------------------


def check_sum_p_distribution(df: pd.DataFrame, p_col: str, entry_count_col: str) -> dict[str, Any]:
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
    md_lines.append(_df_to_markdown_table(comparison_df))
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
        raise ValueError("evaluate_all_models: y_true_by_split must contain 'test' split (§15.4)")

    for model_name, pred_df in predictions_by_model.items():
        # 予測 df の test split 抽出
        test_mask = pred_df["split"] == "test"
        pred_test = pred_df.loc[test_mask]
        if len(pred_test) == 0:
            metrics_dict[model_name] = {col: float("nan") for col in METRIC_COLUMNS}
            metrics_dict[model_name]["sum_p_note"] = SUM_P_DIAGNOSTIC_NOTE
            continue

        y_pred = pred_test["p_fukusho_hit"].to_numpy()
        # 真ラベルは予測 df 側に含まれている前提 (fukusho_hit 列)・なければ y_test を使用
        if "fukusho_hit" in pred_test.columns:
            y_true = pred_test["fukusho_hit"].to_numpy()
        else:
            y_true = y_test.reindex(pred_test.index).to_numpy()

        race_keys = pred_test["race_key"].to_numpy() if "race_key" in pred_test.columns else None
        entry_counts = (
            pred_test["entry_count"].to_numpy() if "entry_count" in pred_test.columns else None
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
    "METRIC_COLUMNS_EXTENDED",
    "CALIBRATION_CURVE_BINS",
    "CALIBRATION_CURVE_STRATEGY",
    "CALIBRATION_CURVE_MIN_BIN_COUNT",
    "SUM_P_BLOCK_THRESHOLD",
    "COMPARABLE_BASELINES",
    "BL3_MARKET_REFERENCE_NOTE",
    "BL_UNCALIBRATED_NOTE",
    "D04_SELECTION_CRITERION_NOTE",
    "SUM_P_DIAGNOSTIC_NOTE",
    "compute_metrics",
    "check_sum_p_distribution",
    "build_comparison_table",
    "write_eval_report",
    "evaluate_all_models",
    # Phase 6 (Plan 06-02) 新規
    "_compute_calibration_curve_bins",
    "_compute_quantile_max_dev",
    "_compute_ece",
    "_compute_mce",
]
