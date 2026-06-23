# Phase 6: Evaluation & Calibration Gates - Pattern Map

**Mapped:** 2026-06-23
**Files analyzed:** 11（新規 8・修正 3）
**Analogs found:** 11 / 11（全て strong match・既存コード契約の直接拡張）

本 Phase は既存コード（特に `src/model/evaluator.py` / `src/ev/report.py` / `src/db/prediction_load.py`）の**確立したパターンの直接拡張**が中心。新規アーキテクチャ概念はほぼなく、実装リスクの大部分は `_compute_calibration_max_dev_guarded`（commit 9fce782）の純 NumPy binning パターンが解決済み。

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/model/evaluator.py`（拡張） | service | transform | `src/model/evaluator.py` 自身（`_compute_calibration_max_dev_guarded` / `check_sum_p_distribution` / `build_comparison_table` / `write_eval_report`） | exact（同一ファイル拡張） |
| `src/model/segment_eval.py`（新規） | service | transform | `src/model/evaluator.py`（binning 契約）+ `src/ev/metrics.py`（純粋関数パターン） | role-match（binning 再利用） |
| `src/db/schema.py`（修正） | config | CRUD | `src/db/schema.py` 自身（`PREDICTION_TABLE_DDL` / `APPLY_ORDER`） | exact（同一ファイル拡張） |
| `src/model/predict.py`（修正） | model | transform | `src/model/predict.py` 自身（`PREDICTION_COLUMNS`） | exact（同一ファイル拡張） |
| `src/db/prediction_load.py`（修正 + 新関数） | service | CRUD | `src/db/prediction_load.py`（`_idempotent_load_prediction` staging-swap idiom）+ `_df_to_prediction_tuples` 型処理 | exact（同一ファイル拡張） |
| `scripts/run_evaluation.py`（新規） | CLI | request-response | `scripts/run_train_predict.py`（argparse + pool/cur + try/except PsycopgError + finally pool.close）+ `scripts/run_backtest.py`（report 出力フロー） | role-match（CLI 慣例） |
| `src/model/gate.py`（仮・新規） または evaluator.py 内関数 | service | transform | `src/model/evaluator.py::check_sum_p_distribution`（hybrid gate 慣例・diagnostic note） | role-match |
| `reports/06-evaluation.md`（新規） | artifact | file-I/O | `reports/04-eval.md` + `reports/05-backtest.md`（md 構造） | exact（レポート慣例） |
| `reports/06-evaluation.json`（新規） | artifact | file-I/O | `reports/04-eval.json` + `reports/05-backtest.json`（`json.dumps(sort_keys=True, ensure_ascii=False)`） | exact |
| `reports/06-segments/{axis}.{json,html}`（新規） | artifact | file-I/O | `reports/04-eval.json`（JSON 構造）+ Plotly `fig.write_html(include_plotlyjs=True)`（新規 API・アナログなし） | role-match（JSON 部）/ no-analog（HTML 部） |
| `tests/model/test_evaluator.py`（新規） | test | unit | `tests/model/test_prediction_load.py::test_df_to_prediction_tuples_column_order`（純粋関数 unit テスト・合成データ）+ `tests/model/test_orchestrator.py::test_reproduce_bit_identical`（bit-identical 回帰） | role-match |
| `tests/model/test_evaluator_gate.py`（新規） | test | unit | `tests/model/test_prediction_load.py`（合成データ → assert）+ `tests/test_quality_gate.py`（gate 慣例） | role-match |
| `tests/model/test_segment_eval.py`（新規） | test | unit | `tests/model/test_prediction_load.py`（unit テスト構造） | role-match |
| `tests/db/test_is_primary_flag.py`（新規） | test | integration (requires_db) | `tests/model/test_prediction_load.py::test_idempotent_checksum_match`（requires_db・write_cur fixture・try/finally teardown） | exact（DB テスト慣例） |
| `pyproject.toml`（修正） | config | — | `pyproject.toml` 自身 | exact（`uv add plotly`） |

---

## Pattern Assignments

### `src/model/evaluator.py`（拡張: quantile_max_dev / ECE / MCE + check_acceptance_gate）

**Analog:** 自身（同一ファイルの直接拡張）

**Imports pattern**（既存 lines 42-53・新規 `scipy.stats.spearmanr` のみ追加）:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from src.model.artifact import _atomic_write_text
# Phase 6 追加（D-03 bin 単調性 WARN・scipy は sklearn 推移依存で既に利用可能）
from scipy.stats import spearmanr
```

**定数拡張**（既存 lines 62-90 の直後に新規定数を追加・既存 `METRIC_COLUMNS` / `CALIBRATION_CURVE_*` は不変）:
```python
# Phase 6 新規: METRIC_COLUMNS を拡張（既存 9 列は不変・D-04 事前登録維持）
METRIC_COLUMNS_EXTENDED: list[str] = METRIC_COLUMNS + [
    "quantile_max_dev",  # D-05: quantile bin の max|dev|（BL-1 bin 退化バイアス解除）
    "ece",               # D-05: Expected Calibration Error（Naeini 2015・重み付け平均）
    "mce",               # D-05: Maximum Calibration Error（worst-case・MIN_BIN_COUNT ガード付き）
]

# D-02 構造的 BLOCK 閾値（Claude's Discretion・RESEARCH「受入ゲート判定ロジック」節）
SUM_P_BLOCK_THRESHOLD: float = 0.30       # violation_rate 30% 超で BLOCK
COMPARABLE_BASELINES: tuple[str, ...] = ("bl1", "bl4", "bl5")  # BL-2 (NaN) / BL-3 (§14.2 caveat) 除外
```

**Core binning pattern（純 NumPy bit-identical）** — 既存 `_compute_calibration_max_dev_guarded`（lines 259-335）の bin_edges 構築を strategy 引数で切替え。**重要: 既存関数は一切変更しない（D-04 事前登録指標不変・T-04-24 回避）**。新規ヘルパーを追加し・既存関数から呼ぶ形で再利用:

```python
# 既存 _compute_calibration_max_dev_guarded (lines 296-306) の binning ロジックを切り出して
# strategy='quantile' を追加可能にした新規ヘルパー。既存関数は本ヘルパーを呼ぶように
# リファクタしてもよいが・戻り値の bit-identical は test_compute_metrics_uniform_max_dev で保証。

def _compute_calibration_curve_bins(
    y_true: np.ndarray, y_pred: np.ndarray, *,
    strategy: str,  # 'uniform' | 'quantile'
    n_bins: int = CALIBRATION_CURVE_BINS,
    min_bin_count: int = CALIBRATION_CURVE_MIN_BIN_COUNT,
) -> dict[str, np.ndarray]:
    """bin ごとに (mean_pred, frac_pos, count) を純 NumPy で計算（bit-identical）。

    strategy='uniform': np.linspace(0,1,n+1)  [既存 _compute_calibration_max_dev_guarded と同一]
    strategy='quantile': np.unique(np.quantile(y_pred, np.linspace(0,1,n+1)))
                        重複 edge は np.unique で対処（BL-1 離散値対策・Pitfall 1）
    """
    # ↓ 既存 lines 297-306 のパターンをそのまま適用
    if strategy == "uniform":
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    elif strategy == "quantile":
        bin_edges = np.unique(np.quantile(y_pred, np.linspace(0.0, 1.0, n_bins + 1)))
    else:
        raise ValueError(f"unsupported strategy: {strategy!r}")
    n_bins_actual = len(bin_edges) - 1
    if n_bins_actual < 1:
        return {"mean_pred": np.array([]), "frac_pos": np.array([]),
                "counts": np.array([]), "bin_edges": bin_edges}

    # ↓ 既存 lines 299-306 と同一（y_pred==1.0 の out-of-range を clip で捕捉・Specialist (b)）
    bin_idx = np.digitize(y_pred, bins=bin_edges[1:-1], right=False)
    bin_idx = np.clip(bin_idx, 0, n_bins_actual - 1)

    counts = np.bincount(bin_idx, minlength=n_bins_actual).astype(float)
    pos_sum = np.bincount(bin_idx, weights=y_true.astype(float), minlength=n_bins_actual)
    pred_sum = np.bincount(bin_idx, weights=y_pred, minlength=n_bins_actual)

    nonempty = counts > 0
    # ↓ 既存 lines 320-326 の整列 assert（Specialist (c)）
    assert len(counts[nonempty]) == len(pos_sum[nonempty]) == len(pred_sum[nonempty])
    return {
        "mean_pred": pred_sum[nonempty] / counts[nonempty],
        "frac_pos":  pos_sum[nonempty] / counts[nonempty],
        "counts":    counts[nonempty],
        "bin_edges": bin_edges,
    }
```

**ECE/MCE 計算** — `_compute_calibration_curve_bins` を消費（RESEARCH Code Examples lines 720-773 を実装化・Naeini 2015 定義）:
```python
def _compute_ece(y_true, y_pred, *, strategy="quantile", n_bins=CALIBRATION_CURVE_BINS) -> float:
    """ECE = Σ(n_m/N) × |frac_pos - mean_pred|（Naeini 2015）。single-class は NaN。"""
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy=strategy, n_bins=n_bins)
    if len(bins["counts"]) == 0:
        return float("nan")
    N = float(len(y_pred))
    devs = np.abs(bins["frac_pos"] - bins["mean_pred"])
    return float(np.sum(bins["counts"] / N * devs))

def _compute_mce(y_true, y_pred, *, strategy="quantile",
                 n_bins=CALIBRATION_CURVE_BINS, min_bin_count=CALIBRATION_CURVE_MIN_BIN_COUNT) -> float:
    """MCE = max|dev|（worst-case・MIN_BIN_COUNT ガード付き）。single-class は NaN。"""
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(
        y_true, y_pred, strategy=strategy, n_bins=n_bins, min_bin_count=min_bin_count)
    if len(bins["counts"]) == 0:
        return float("nan")
    keep = bins["counts"] >= min_bin_count
    if not np.any(keep):
        return float("nan")
    return float(np.max(np.abs(bins["frac_pos"][keep] - bins["mean_pred"][keep])))
```

**check_acceptance_gate**（新規・D-01/D-02/D-03・hybrid gate）— `check_sum_p_distribution`（lines 343-410）の戻り値を消費:

```python
def check_acceptance_gate(
    metrics_dict: dict[str, dict[str, Any]],
    sum_p_check: dict[str, Any],
) -> dict[str, Any]:
    """§15.2 受入ゲート判定（D-01/D-02/D-03・hybrid gate）。

    BLOCK（D-02）: baselines 全敗 + sum(p) 著乖離 → block_triggered=True（pytest/CI fail）
    WARN  (D-03) : 年次反転数・bin 単調違反・Spearman → 参考レポート（人間判定）
    """
    block_reasons: list[str] = []
    # BLOCK 条件1: baselines 全敗（順序付け能力ゼロ）
    for main_model in ("lightgbm", "catboost"):
        m = metrics_dict.get(main_model, {})
        if not m or pd.isna(m.get("logloss")):
            continue
        bl_ll = [metrics_dict[b]["logloss"] for b in COMPARABLE_BASELINES
                 if b in metrics_dict and not pd.isna(metrics_dict[b].get("logloss"))]
        bl_br = [metrics_dict[b]["brier"] for b in COMPARABLE_BASELINES
                 if b in metrics_dict and not pd.isna(metrics_dict[b].get("brier"))]
        if not bl_ll or not bl_br:
            continue
        if m["logloss"] > max(bl_ll) and m["brier"] > max(bl_br):
            block_reasons.append(
                f"{main_model}: LogLoss+Brier both worse than all comparable baselines "
                f"({', '.join(COMPARABLE_BASELINES)})")
    # BLOCK 条件2: sum(p) 著乖離（§15.2 理論値から 30% 超違反）
    if sum_p_check["large_violation_rate"] > SUM_P_BLOCK_THRESHOLD:
        block_reasons.append(f"sum(p) large-bucket violation_rate>={SUM_P_BLOCK_THRESHOLD:.0%}")
    if sum_p_check["small_violation_rate"] > SUM_P_BLOCK_THRESHOLD:
        block_reasons.append(f"sum(p) small-bucket violation_rate>={SUM_P_BLOCK_THRESHOLD:.0%}")

    return {
        "block_triggered": len(block_reasons) > 0,
        "block_reasons": block_reasons,
        "gate_verdict": "BLOCK" if block_reasons else "WARN",
        "comparable_baselines": list(COMPARABLE_BASELINES),
        "sum_p_block_threshold": SUM_P_BLOCK_THRESHOLD,
    }
```

**WARN 指標（D-03・人間判定参考）** — Spearman は RESEARCH Code Examples lines 776-797 を実装化:
```python
def compute_monotonicity_warn(bins: dict) -> dict[str, float]:
    """bin 単調性 WARN（D-03・人間判定参考）。Spearman 順位相関 + bin 逆転数。"""
    frac_pos = bins["frac_pos"]; mean_pred = bins["mean_pred"]
    if len(frac_pos) < 2:
        return {"spearman_corr": float("nan"), "bin_inversions": 0}
    corr, _ = spearmanr(frac_pos, mean_pred, nan_policy="omit")
    return {"spearman_corr": float(corr),
            "bin_inversions": int(np.sum(np.diff(frac_pos) < 0))}
```

**Error handling / Validation pattern** — 既存 `_compute_calibration_max_dev`（lines 242-256）と同一: single-class は `float("nan")`・try/except (ValueError, IndexError) で bin 異常時は NaN。

---

### `src/model/segment_eval.py`（新規: 6軸 segment 別 calibration curve）

**Analog:** `src/model/evaluator.py`（binning 契約再利用）+ `src/ev/metrics.py`（純粋関数パターン）

**Imports pattern**（`evaluator.py` から binning 関数を import・Plotly は新規）:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go   # 新規依存（uv add plotly・D-10）

from src.model.artifact import _atomic_write_text
from src.model.evaluator import (
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    _compute_calibration_curve_bins,   # Phase 6 新規ヘルパー（上記）
    _compute_calibration_max_dev_guarded,
    _compute_ece,
    _compute_mce,
)
```

**Core pattern（segment 軸 groupby + evaluator binning）** — RESEARCH Pattern 2（lines 298-342）を実装化。groupby 自体は行順序非依存（segment 値で分割のみ）・bit-identical 保証は binning 関数内:
```python
SEGMENT_AXES: dict[str, str] = {
    "year":         "race_date_year",    # df["race_date"].dt.year から事前生成
    "month":        "race_date_month",
    "jyocd":        "jyocd",
    "entry_count":  "entry_count",
    "ninki":        "ninki",             # 人気帯（label.fukusho_label から JOIN）
    "odds_band":    "fukuoddslower",     # 複勝オッズ下限（label.fukusho_label から JOIN）
}

def evaluate_segment_axis(
    y_true: np.ndarray, y_pred: np.ndarray, segment_values: np.ndarray, *,
    axis_name: str, n_bins: int = CALIBRATION_CURVE_BINS,
) -> dict[str, Any]:
    """1つの segment 軸で全 segment 値の calibration curve + scalar を生成。"""
    results: dict[str, Any] = {}
    unique_segs = np.unique(segment_values[pd.notna(segment_values)])
    for seg_val in unique_segs:
        mask = segment_values == seg_val
        if int(mask.sum()) < CALIBRATION_CURVE_MIN_BIN_COUNT:
            continue  # 極小 segment はスキップ（D-12 取得可能軸前提）
        bins = _compute_calibration_curve_bins(
            y_true[mask], y_pred[mask], strategy="uniform", n_bins=n_bins)
        results[str(seg_val)] = {
            "curve": {"mean_pred": bins["mean_pred"].tolist(),
                      "frac_pos":  bins["frac_pos"].tolist(),
                      "count":     bins["counts"].astype(int).tolist()},
            "scalar": {
                "ece_quantile":      _compute_ece(y_true[mask], y_pred[mask], strategy="quantile"),
                "ece_uniform":       _compute_ece(y_true[mask], y_pred[mask], strategy="uniform"),
                "mce_guarded":       _compute_mce(y_true[mask], y_pred[mask], strategy="uniform"),
                "max_dev_guarded":   _compute_calibration_max_dev_guarded(y_true[mask], y_pred[mask]),
                "n_samples":         int(mask.sum()),
            },
        }
    return results
```

**Plotly HTML 出力** — RESEARCH Pattern 3（lines 344-377）を実装化・`include_plotlyjs=True` で自己完結:
```python
def render_segment_curves_html(
    segment_results: dict, *, axis_name: str, out_path: Path,
) -> Path:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                            name="perfect", line=dict(dash="dash", color="gray")))
    for seg_val, data in sorted(segment_results.items()):
        c = data["curve"]
        fig.add_trace(go.Scatter(
            x=c["mean_pred"], y=c["frac_pos"], mode="lines+markers",
            name=f"{axis_name}={seg_val} (n={data['scalar']['n_samples']})",
            customdata=c["count"],
            hovertemplate="pred=%{x:.3f}<br>obs=%{y:.3f}<br>n=%{customdata}<extra></extra>"))
    fig.update_layout(title=f"Calibration Curve by {axis_name}",
                      xaxis_title="mean predicted probability",
                      yaxis_title="observed fraction", width=900, height=600)
    fig.write_html(str(out_path), include_plotlyjs=True)  # ~3MB plotly.js 埋込・offline
    return out_path
```

**JSON 出力** — `evaluator.write_eval_report`（lines 516-542）と同一パターン・`json.dumps(sort_keys=True, ensure_ascii=False)` + `_atomic_write_text`。

**Pitfall 対処**: Pitfall 6（segment 軸データ欠損）は Wave 0 で `information_schema.columns` 確認・欠損軸は WARN skip。

---

### `src/db/schema.py`（修正: is_primary 列 DDL + APPLY_ORDER 追加）

**Analog:** 自身（`PREDICTION_TABLE_DDL` lines 59-94 + `APPLY_ORDER` lines 293-307）

**新規定数（idempotent ALTER・RESEARCH Code Examples lines 799-810）**:
```python
# Phase 6 D-09: prediction.fukusho_prediction へ is_primary 列追加（idempotent）
PREDICTION_ADD_IS_PRIMARY_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS is_primary boolean DEFAULT false;
ALTER TABLE prediction.fukusho_prediction
    DROP COLUMN IF EXISTS is_primary_old;  -- 任意: 過去誤 migration の cleanup（不要なら削除）
-- CHECK 制約（model_type domain と同パターン・lines 82-84）
ALTER TABLE prediction.fukusho_prediction
    DROP CONSTRAINT IF EXISTS prediction_is_primary_domain;
ALTER TABLE prediction.fukusho_prediction
    ADD CONSTRAINT prediction_is_primary_domain CHECK (is_primary IN (true, false));
COMMENT ON COLUMN prediction.fukusho_prediction.is_primary IS
    'Phase 6 D-09: 主モデル確定フラグ. 選定モデル=true/未選定=false. '
    'etl ロールで model_type+model_version+feature_snapshot_id+as_of_datetime スコープ UPDATE. '
    'GRANT: reader SELECT / etl SELECT+INSERT+UPDATE+DELETE は GRANT_ETL_SQL で既に付与済 (lines 248-253).';
"""
```

**APPLY_ORDER 拡張**（lines 293-307 の `prediction_table` の直後に挿入）:
```python
APPLY_ORDER = [
    ("create_schemas", CREATE_SCHEMAS_SQL),
    ("create_roles", CREATE_ROLES_SQL),
    ("create_raw_views", CREATE_RAW_VIEWS_SQL),
    ("prediction_table", PREDICTION_TABLE_DDL),
    ("prediction_add_is_primary", PREDICTION_ADD_IS_PRIMARY_SQL),  # ← Phase 6 追加
    ("backtest_table", BACKTEST_TABLE_DDL),
    ("grant_reader", GRANT_READER_SQL),
    ("grant_etl", GRANT_ETL_SQL),
    ("revoke_raw_writes_public", REVOKE_RAW_WRITES_PUBLIC_SQL),
    ("revoke_raw_writes_view", REVOKE_RAW_WRITES_VIEW_SQL),
]
```

**GRANT 権限**: 既存 `GRANT_ETL_SQL`（lines 248-253）が prediction スキーマに SELECT/INSERT/UPDATE/DELETE/TRUNCATE を etl ロールに付与済み・is_primary UPDATE に**追加権限不要**。reader ロールも SELECT 済み（lines 222-224）。

**CHECK 制約慣例**: 既存 `prediction_fukusho_hit_range` / `prediction_model_type_domain` / `prediction_calib_method_domain`（lines 82-84）と同形式。

---

### `src/model/predict.py`（修正: PREDICTION_COLUMNS 15→16 列）

**Analog:** 自身（`PREDICTION_COLUMNS` lines 62-82）

**修正箇所**（lines 62-82・末尾に `is_primary` を追加）:
```python
PREDICTION_COLUMNS: list[str] = [
    # provenance (§19.1 再現性・NOT NULL)
    "model_type",
    "model_version",
    "feature_snapshot_id",
    "as_of_datetime",
    "calib_method",
    # PK RACE_KEY (label.fukusho_label と同一7カラム)
    "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum",
    # 予測値
    "p_fukusho_hit",
    # 補助メタ (Phase 5/6/7 が参照)
    "race_date",
    "split",
    "is_primary",   # ← Phase 6 D-09 追加（bool・DEFAULT false・予測生成時は None）
]
```

**Pitfall 4 対処（3ファイル連鎖）**: schema.py / predict.py / prediction_load.py を同時更新。`test_prediction_columns_matches_ddl`（新規 unit test）で PREDICTION_COLUMNS と DDL 列数が一致を assert。

---

### `src/db/prediction_load.py`（修正: _df_to_prediction_tuples 型処理 + 新規 set_primary_model）

**Analog:** 自身（`_df_to_prediction_tuples` lines 108-166 + `_idempotent_load_prediction` staging-swap lines 174-348）

**修正1: `_df_to_prediction_tuples` の is_primary 型処理**（lines 91-93 の定数集合に bool 追加）:
```python
_FLOAT_COLS = {"p_fukusho_hit"}
_INT_COLS = {"year", "kaiji", "racenum", "umaban", "kettonum"}
_BOOL_COLS = {"is_primary"}   # ← Phase 6 追加
```
`_df_to_prediction_tuples`（lines 131-166）のループ内で is_primary の分岐を追加: None→None・True/False→bool は既存 `else` 分岐（lines 158-164）で処理可能だが・明示分岐推奨。

**新規関数: set_primary_model（RESEARCH lines 550-570）** — staging-swap idiom と同方針・`psycopg.sql.SQL` + `Placeholder` で SQL injection 防御:
```python
from psycopg.sql import SQL, Identifier, Placeholder

def set_primary_model(
    write_cur: Cursor, *,
    primary_model_type: str, primary_model_version: str,
    feature_snapshot_id: str, as_of_datetime,
) -> None:
    """主モデルの is_primary フラグを設定（D-09）。

    当該 feature_snapshot_id+as_of_datetime スコープで:
      1. 全行 is_primary=false にリセット
      2. 選定 model_type+model_version の行を is_primary=true に UPDATE
    両モデル行は保持（silent 履歴破壊防止・prediction_load の model_version scoped swap と同方針）。
    """
    scope_where = SQL(" WHERE feature_snapshot_id = {} AND as_of_datetime = {}").format(
        Placeholder(), Placeholder())
    write_cur.execute(
        SQL("UPDATE prediction.fukusho_prediction SET is_primary = false") + scope_where,
        (feature_snapshot_id, as_of_datetime))
    write_cur.execute(
        SQL("UPDATE prediction.fukusho_prediction SET is_primary = true")
        + SQL(" WHERE model_type = {} AND model_version = {}")
        + scope_where,
        (primary_model_type, primary_model_version,
         feature_snapshot_id, as_of_datetime))
```

**idempotency**: 2回実行で同一状態（`test_set_primary_model_idempotent` で検証）。

---

### `scripts/run_evaluation.py`（新規: 統合評価 CLI）

**Analog:** `scripts/run_train_predict.py`（argparse + pool/cur + try/except PsycopgError + finally）

**起動フロー慣例**（run_train_predict.py lines 13-32 と同一構造）:
1. `Settings` から `dsn_masked` / `etl_dsn_masked` をログ出力（生 DSN 絶対禁止）
2. readonly pool + etl pool 構築
3. 成果物読込（readonly ロール・READ only）
4. 評価 → ゲート判定 → segment 評価 → 主モデル確定 → レポート出力
5. try/except `PsycopgError` / finally `pool.close()`

**Imports pattern**（`sys.path.insert` で `src.*` を import・run_train_predict.py lines 58-82 と同一）:
```python
from __future__ import annotations
import argparse, logging, sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError
from src.config.settings import Settings
from src.db.connection import make_pool, readonly_cursor, write_cursor
from src.db.prediction_load import set_primary_model
from src.model.evaluator import (
    evaluate_all_models, check_sum_p_distribution, check_acceptance_gate,
    compute_monotonicity_warn, COMPARABLE_BASELINES, SUM_P_BLOCK_THRESHOLD,
)
from src.model.segment_eval import evaluate_all_segments, render_segment_curves_html
```

**parse_args**（run_train_predict.py lines 94-142 と同一形式）:
```python
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Phase 6 evaluation CLI (EVAL-01/02/03 / D-01..D-12)")
    p.add_argument("--feature-snapshot-id", required=True,
                   help="feature snapshot id（postreview-v2 等・READ scope）")
    p.add_argument("--primary-model", choices=["lightgbm", "catboost"], default=None,
                   help="主モデル（人間判断結果・省略時は D-08 タイブレーク規則適用）")
    p.add_argument("--as-of-datetime", required=True,
                   help="prediction の as_of_datetime（UPDATE scope・ISO8601）")
    p.add_argument("--skip-segments", action="store_true",
                   help="開発時・segment 評価スキップ")
    return p.parse_args(argv)
```

**Error handling** — BLOCK 発火時は `RuntimeError` で fail-loud（run_train_predict.py が `sys.exit(1)` で critical error を扱う慣例・CLAUDE.md hybrid gate）:
```python
gate = check_acceptance_gate(metrics_dict, sum_p_check)
if gate["block_triggered"]:
    logger.error("ACCEPTANCE GATE BLOCK: %s", gate["block_reasons"])
    raise RuntimeError(f"Phase 6 acceptance gate BLOCK: {gate['block_reasons']}")
```

---

### `src/model/gate.py`（仮・新規） または evaluator.py 内関数

**推奨:** evaluator.py 内関数として実装（`check_acceptance_gate` / `compute_monotonicity_warn`）。別モジュール化はゲートロジックが肥大化した場合のみ。`check_sum_p_distribution` と同ファイルに gate 群を集約する方が cohesion 高い。

---

### `reports/06-evaluation.{md,json}`（新規）

**Analog:** `reports/04-eval.{md,json}`（evaluator.write_eval_report lines 486-542）+ `reports/05-backtest.{md,json}`（ev/report.generate_report lines 209-272）

**md 構造**（RESEARCH lines 629 を実装化）:
```
# Phase 6 Evaluation Report (EVAL-01/02/03 / §15.1/§15.2/§15.3)
## 受入ゲート判定（BLOCK/WARN）
  - gate_verdict / block_reasons / WARN 指標（Spearman・反転数）
## 主モデル比較表（全指標）
  - METRIC_COLUMNS_EXTENDED + backtest 指標（reports/05-backtest.json から統合）
## 主モデル確定（理由記録・D-07）
  - primary_model / selection_reason / tiebreak_applied
## segment 安定性サマリ（6軸 scalar 表への参照）
## 注記
  - D-04 事前登録基準・BL-1 caveat・BL-3 §14.2 caveat
```

**json 構造** — evaluator.py lines 521-541 の `json.dumps(sort_keys=True, ensure_ascii=False)` パターンを踏襲:
```python
json_payload = json.dumps({
    "gate_result": gate,
    "comparison_table": comparison_records,
    "primary_model": {
        "model_type": ..., "model_version": ...,
        "feature_snapshot_id": ..., "as_of_datetime": ...,
        "selection_reason": ...,     # D-07 人間判断理由
        "tiebreak_applied": ...,     # D-08 タイブレーク発火段階 or None
    },
    "segment_summary": ...,
    "constants": {"METRIC_COLUMNS_EXTENDED": ..., "SUM_P_BLOCK_THRESHOLD": ...,
                  "COMPARABLE_BASELINES": ...},
    "notes": {...},
}, sort_keys=True, ensure_ascii=False)
_atomic_write_text(json_path, json_payload)
```

**Markdown 表生成** — `_df_to_markdown_table`（evaluator.py lines 117-140）を再利用。tabulate 非依存・NaN は "nan" 表示。

**REPORT_COLUMNS 契約（LOW-05）** — `ev/report.py::REPORT_COLUMNS`（lines 41-53）パターン・md ヘッダと json comparison_table キーが 1:1 になることを unit test で assert。

---

### `tests/model/test_evaluator.py`（新規）

**Analog:** `tests/model/test_prediction_load.py`（unit テスト構造・合成データ・純粋 assert）+ `tests/model/test_orchestrator.py::test_reproduce_bit_identical`（bit-identical 回帰）

**Fixture / 合成データパターン**（test_prediction_load.py lines 41-77 の `_make_synthetic_prediction_df` に倣う）:
```python
import numpy as np
import pandas as pd
import pytest

def _make_synthetic_y(n=1000, seed=42, p_range=(0.05, 0.95)):
    """合成 y_true / y_pred（固定 seed・bit-identical 検証用）。"""
    rng = np.random.default_rng(seed)
    p = rng.uniform(*p_range, size=n)
    y = (rng.uniform(size=n) < p).astype(int)
    return y, p

def test_quantile_max_dev_bit_identical():
    """固定入力で2回呼出し np.array_equal（Phase 4 SC#4 延長・純 NumPy 保証）。"""
    y, p = _make_synthetic_y()
    from src.model.evaluator import _compute_mce
    a = _compute_mce(y, p, strategy="quantile")
    b = _compute_mce(y, p, strategy="quantile")
    assert a == b   # float の bit-identical は == で検証

def test_compute_metrics_uniform_max_dev_unchanged():
    """D-04 事前登録指標（uniform・ガードなし）が温存される（reports/04-eval.json の値と一致）。
    Pitfall 3 対処・T-04-24 後知恵すり替え防止。"""
    # reports/04-eval.json の LightGBM calibration_max_dev=0.23077・CatBoost 0.25789 を assert
```

**requires_db 非使用** — evaluator は純粋関数・`@pytest.mark.requires_db` 不要（conftest.py lines 22-63 参照）。

---

### `tests/model/test_evaluator_gate.py`（新規）

**Analog:** `tests/model/test_prediction_load.py`（合成データ → assert）+ `tests/test_quality_gate.py`（gate 慬例）

**ゲート正発火テスト** — 合成 metrics_dict で BLOCK 条件を構築:
```python
def test_block_baselines_all_lose():
    """D-02 BLOCK 条件1: 主モデルが LogLoss+Brier 両方で全 baselines に劣る → block_triggered=True."""
    metrics = {
        "lightgbm": {"logloss": 0.6, "brier": 0.2},   # 全 BL より悪い
        "bl1": {"logloss": 0.5, "brier": 0.18},
        "bl4": {"logloss": 0.52, "brier": 0.19},
        "bl5": {"logloss": 0.51, "brier": 0.185},
    }
    sum_p = {"large_violation_rate": 0.0, "small_violation_rate": 0.0}
    from src.model.evaluator import check_acceptance_gate
    g = check_acceptance_gate(metrics, sum_p)
    assert g["block_triggered"] is True
    assert any("LogLoss+Brier" in r for r in g["block_reasons"])

def test_bl2_bl3_excluded_from_comparable():
    """BL-2 (NaN) / BL-3 (§14.2 caveat) が比較対象から除外される（COMPARABLE_BASELINES）。"""
    # metrics に bl2/bl3 を入れても block 判定に影響しないことを assert
```

---

### `tests/model/test_segment_eval.py`（新規）

**Analog:** `tests/model/test_prediction_load.py`（unit 構造）

**Contract テスト** — evaluator binning 契約の再利用・Plotly HTML 自己完結・PIT 軸一致:
```python
def test_segment_curve_binning_contract():
    """evaluator.py binning 契約（uniform/10bins/MIN_BIN_COUNT=30）が再利用されること。"""
    # segment_eval.evaluate_segment_axis が _compute_calibration_curve_bins を呼ぶことを検証

def test_segment_plotly_html_self_contained(tmp_path):
    """HTML に plotly.js が埋込まれていること（include_plotlyjs=True）。"""
    out = tmp_path / "test.html"
    # ... render_segment_curves_html 呼出 ...
    content = out.read_text()
    assert "plotly" in content.lower()
    assert len(content) > 1_000_000   # ~3MB plotly.js 埋込確認
```

---

### `tests/db/test_is_primary_flag.py`（新規・requires_db）

**Analog:** `tests/model/test_prediction_load.py`（`@pytest.mark.requires_db` + `write_cur` fixture + try/finally teardown・lines 85-200）

**惯例** — conftest.py の `write_cur` fixture（lines 58-63）を使用・`@pytest.mark.requires_db` マーク・try/finally で teardown:
```python
@pytest.mark.requires_db
def test_set_primary_model_idempotent(write_cur):
    """set_primary_model を2回実行で同一状態（staging-swap と同・idempotent）。"""
    try:
        set_primary_model(write_cur,
                          primary_model_type="lightgbm",
                          primary_model_version="test-phase6-v1",
                          feature_snapshot_id="test-snapshot",
                          as_of_datetime=datetime(2026, 6, 23, tzinfo=UTC))
        # 2回目
        set_primary_model(write_cur, primary_model_type="lightgbm",
                          primary_model_version="test-phase6-v1",
                          feature_snapshot_id="test-snapshot",
                          as_of_datetime=datetime(2026, 6, 23, tzinfo=UTC))
        write_cur.execute(
            "SELECT count(*) FROM prediction.fukusho_prediction "
            "WHERE is_primary = true AND feature_snapshot_id = %s",
            ("test-snapshot",))
        assert int(write_cur.fetchone()[0]) > 0
    finally:
        write_cur.execute(
            "UPDATE prediction.fukusho_prediction SET is_primary = false "
            "WHERE feature_snapshot_id = 'test-snapshot'")

@pytest.mark.requires_db
def test_alter_adds_is_primary_column(write_cur):
    """ALTER TABLE IF NOT EXISTS で is_primary 列が追加される（idempotent）。"""
    write_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='prediction' AND table_name='fukusho_prediction' "
        "AND column_name='is_primary'")
    assert write_cur.fetchone() is not None
```

---

## Shared Patterns

### 1. 純 NumPy bit-identical binning（最重要・Phase 4 SC#4 延長）
**Source:** `src/model/evaluator.py::_compute_calibration_max_dev_guarded` lines 259-335
**Apply to:** evaluator.py 拡張（ECE/MCE/quantile_max_dev）・segment_eval.py 全関数
```python
# bin_edges 構築 → digitize + clip → bincount（weights で pos_sum/pred_sum 同時計算）
bin_edges = np.linspace(0.0, 1.0, n_bins + 1)   # uniform
# または np.unique(np.quantile(y_pred, np.linspace(0,1,n+1)))  # quantile
bin_idx = np.clip(np.digitize(y_pred, bins=bin_edges[1:-1], right=False), 0, n_bins - 1)
counts   = np.bincount(bin_idx, minlength=n_bins).astype(float)
pos_sum  = np.bincount(bin_idx, weights=y_true.astype(float), minlength=n_bins)
pred_sum = np.bincount(bin_idx, weights=y_pred, minlength=n_bins)
# pandas.groupby/sort は等値要素 index 依存で bit-identical リスク → 不使用（debug Specialist (f)）
```

### 2. md + json 分離出力（review LOW）
**Source:** `src/model/evaluator.py::write_eval_report` lines 486-542 + `src/ev/report.py::generate_report` lines 209-272
**Apply to:** reports/06-evaluation.{md,json}・reports/06-segments/*.json
```python
# md: _atomic_write_text(md_path, "".join(md_lines))
# json: json.dumps({...}, sort_keys=True, ensure_ascii=False) → _atomic_write_text
# REPORT_COLUMNS 定数で md ヘッダと json comparison_table キーが 1:1（LOW-05）
```

### 3. hybrid gate（Phase 1 D-01 / Phase 2 D-02 延長）
**Source:** `src/model/evaluator.py::check_sum_p_distribution` lines 343-410（diagnostic note・fail-loud でなく warning）
**Apply to:** evaluator.py::check_acceptance_gate・compute_monotonicity_warn
- 構造的欠陥（D-02 BLOCK）= pytest/CI fail（RuntimeError）
- 量的異常・曖昧基準（D-03 WARN）= 参考レポート（人間判定）

### 4. staging-swap idempotent・model_version scoped（review HIGH#1）
**Source:** `src/db/prediction_load.py::_idempotent_load_prediction` lines 174-348
**Apply to:** `src/db/prediction_load.py::set_primary_model`（新規）
- `psycopg.sql.SQL` + `Identifier` + `Placeholder` で SQL injection 防御
- model_type+model_version+feature_snapshot_id+as_of_datetime スコープ UPDATE（全行 UPDATE でなく・silent 履歴破壊防止）
- 2回実行で同一状態（idempotent・test で検証）

### 5. 5層スキーマ分離 + GRANT ロール分離
**Source:** `src/db/schema.py` lines 26-326
**Apply to:** schema.py 拡張（is_primary 列）・run_evaluation.py（readonly READ + etl UPDATE）
- readonly ロール: SELECT のみ（prediction スキーマ lines 222-224）
- etl ロール: SELECT/INSERT/UPDATE/DELETE/TRUNCATE（lines 248-253・is_primary UPDATE に追加権限不要）
- raw_everydb2 / public は REVOKE UPDATE/DELETE/TRUNCATE（二重保護 lines 267-279）

### 6. CLI 起動フロー（argparse + masked DSN + try/except + finally）
**Source:** `scripts/run_train_predict.py` lines 46-88・218-322
**Apply to:** `scripts/run_evaluation.py`（新規）
- `sys.path.insert(0, str(_REPO_ROOT))` で `src.*` import
- `Settings` から `dsn_masked` / `etl_dsn_masked` をログ出力（生 DSN 絶対禁止）
- try/except `PsycopgError` / finally `pool.close()`

### 7. atomic write（Shared Pattern 7）
**Source:** `src/model/artifact.py::_atomic_write_text` lines 59-69
**Apply to:** 全 reports/06-* 出力・segment JSON/HTML
```python
def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)
```

### 8. 事前登録指標の不変（T-04-24 回避）
**Source:** evaluator.py docstring lines 22-26 + `_compute_calibration_max_dev` lines 228-256
**Apply to:** evaluator.py 拡張
- `calibration_max_dev`（uniform・ガードなし・事前登録）は**一切触れない**
- 新指標（quantile/ECE/MCE）を**併記**するのみ（D-04）
- `test_compute_metrics_uniform_max_dev` で reports/04-eval.json の値（LightGBM 0.23077・CatBoost 0.25789）と一致を assert

### 9. requires_db fixture と teardown 慣例
**Source:** `tests/conftest.py` lines 22-78 + `tests/model/test_prediction_load.py` lines 85-200
**Apply to:** `tests/db/test_is_primary_flag.py`（新規）
- `@pytest.mark.requires_db` + `write_cur` fixture
- `KEIBA_SKIP_DB_TESTS=1` で skip（CI では skip しない・fail-by-default）
- try/finally で teardown（テストデータ削除）

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `reports/06-segments/*.html`（Plotly 部分） | artifact | file-I/O | **Plotly は新規依存**・既存コードに Plotly 使用箇所なし（`uv add plotly` で追加・API は RESEARCH Pattern 3 と plotly.com 公式 docs で検証済み） |

それ以外は全て既存コード契約の直接拡張でカバーされる。Phase 6 の実装リスクの大部分は `_compute_calibration_max_dev_guarded`（commit 9fce782）の binning パターンが解決済みのため・新規アーキテクチャ概念は実質的に Plotly HTML 出力のみ。

---

## Metadata

**Analog search scope:**
- `/Users/hart/develop/keiba-ai-v3/src/model/`（evaluator.py / predict.py / artifact.py / orchestrator.py / calibrator.py / baseline.py）
- `/Users/hart/develop/keiba-ai-v3/src/ev/`（metrics.py / report.py / bl3_betting.py）
- `/Users/hart/develop/keiba-ai-v3/src/db/`（schema.py / prediction_load.py / connection.py）
- `/Users/hart/develop/keiba-ai-v3/scripts/`（run_train_predict.py / run_backtest.py / run_apply_schema.py）
- `/Users/hart/develop/keiba-ai-v3/tests/`（conftest.py / test_prediction_load.py / test_quality_gate.py / test_orchestrator.py）
- `/Users/hart/develop/keiba-ai-v3/reports/`（04-eval.{md,json} / 05-backtest.{md,json}）

**Files scanned:** 14 ファイル（evaluator.py / predict.py / artifact.py / metrics.py / report.py / schema.py / prediction_load.py / run_train_predict.py / conftest.py / test_prediction_load.py / CLAUDE.md / 06-CONTEXT.md / 06-RESEARCH.md / plotly docs via RESEARCH）

**Key insight:** Phase 6 の binning 契約・md/json 分離・staging-swap idiom・hybrid gate・ロール分離・atomic write・CLI 起動フロー・requires_db fixture の**全てが既存コードに確立済み**。Phase 6 はこれらを直接拡張するのみ。新規に設計すべきは Plotly HTML 出力（RESEARCH Pattern 3 と公式 docs で検証済み）と check_acceptance_gate の閾値（Claude's Discretion・RESEARCH で閾値案提示済み）。

**Pattern extraction date:** 2026-06-23
