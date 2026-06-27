# Phase 12: p_lower EV & Falsification Evaluation - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 17 (新規 3 + 拡張 13 + config 1)
**Analogs found:** 16 / 17 (新規 `src/eval/falsification.py` は部分 analog・run_phase11_evaluation.py 構造踏襲)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/model/race_relative.py` (拡張) | utility (純粋関数) | transform | `src/model/race_relative.py::apply_race_relative_correction` (同一ファイル) | exact |
| `src/model/orchestrator.py` (拡張 L754 後) | service | request-response | `src/model/orchestrator.py::train_and_predict` (同一ファイル・race-relative 補正ブロック) | exact |
| `src/model/predict.py` (拡張 PREDICTION_COLUMNS / `_assert_valid_prediction_df`) | service | transform | `src/model/predict.py` (同一ファイル・is_primary 追加 Phase 6 / provenance 3列追加 Phase 11 と同一 idiom) | exact |
| `src/db/schema.py` (拡張 `PREDICTION_ADD_P_LOWER_SQL` / `APPLY_ORDER`) | config (DDL) | file-I/O | `src/db/schema.py::PREDICTION_ADD_PROVENANCE_SQL` / `PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL` (同一ファイル) | exact |
| `src/db/prediction_load.py` (拡張 `_FLOAT_COLS` / INSERT 列順序) | service | file-I/O | `src/db/prediction_load.py::_df_to_prediction_tuples` (同一ファイル・Pitfall 4 3ファイル連鎖) | exact |
| `src/ev/ev_rank.py` (拡張 `EV_lower = p_lower × odds_lower`) | utility (純粋関数) | transform | `src/ev/ev_rank.py::compute_ev_and_rank` (同一ファイル・入力列差し替え) | exact |
| `src/ev/purchase_simulator.py` (拡張 `p_min` を p_lower ベースで再解釈) | utility (純粋関数) | transform | `src/ev/purchase_simulator.py::select_bets` (同一ファイル・入力列差し替え) | exact |
| `src/ev/odds_snapshot.py` (再利用・`fuku_odds_lower` 再利用のみ) | utility | request-response | `src/ev/odds_snapshot.py::select_odds_snapshot` (変更不要・再利用のみ) | exact (no-change) |
| `src/ev/refund_accounting.py` (再利用・`_lookup_payfukusyo_pay` slippage 計算の対) | utility | request-response | `src/ev/refund_accounting.py::_lookup_payfukusyo_pay` (変更不要・再利用のみ) | exact (no-change) |
| `src/ev/metrics.py` (拡張 group-by 適用・EV-decile/disagreement ROI) | utility (純粋関数) | transform | `src/ev/metrics.py::compute_backtest_metrics` (同一ファイル・group-by 適用) | exact |
| `src/ev/report.py` (拡張 REPORT_COLUMNS・switch_recommendation 表示) | service | file-I/O | `src/ev/report.py::REPORT_COLUMNS` / `generate_report` (同一ファイル) | exact |
| `src/model/segment_eval.py` (再利用 `ODDS_BAND_EDGES` / `evaluate_segment_axis` binning 契約) | utility | transform | `src/model/segment_eval.py::_odds_band` / `evaluate_segment_axis` (変更不要・import 再利用) | exact (reuse) |
| `src/model/evaluator.py` (拡張 `check_acceptance_gate` `warn_reasons`) | service | request-response | `src/model/evaluator.py::check_acceptance_gate` (同一ファイル・L888-1029・WARN 分離 idiom) | exact |
| `src/model/artifact.py` (拡張 metadata.json に `q_level`/`shrinkage_method`) | service | file-I/O | `src/model/artifact.py::save_native_artifact` (同一ファイル・`race_relative_theta` metadata 追加 Phase 11 と同一 idiom) | exact |
| `src/eval/falsification.py` (新規) | service (純粋関数) | transform | `scripts/run_phase11_evaluation.py::_select_theta_on_calib` (calib slice のみ・statsmodels 新規) | role-match (partial) |
| `scripts/run_phase12_evaluation.py` (新規) | script | request-response (batch) | `scripts/run_phase11_evaluation.py` (全体構造・API chain・gate・report) | exact |
| `tests/audit/test_audit_p_lower_falsification.py` (新規) | test (adversarial) | event-driven | `tests/audit/test_audit_race_relative.py` (5段階鋳型・AST + false-pass + leakage) | exact |
| `pyproject.toml` (拡張 dependencies に `statsmodels`) | config | file-I/O | `pyproject.toml::dependencies` (同一ファイル・scipy 既存) | exact |

## Pattern Assignments

### `src/model/race_relative.py` (utility, transform) — p_lower 計算関数を追加

**Analog:** 同一ファイル `apply_race_relative_correction` / `compute_overprediction_penalty`

**Imports pattern** (lines 33-46・import 再利用 idiom):
```python
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# binning 契約の import 再利用（D-03/D-05・codex review HIGH#2 対応）。
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    _compute_calibration_curve_bins,
)
from src.model.segment_eval import _odds_band  # noqa: E402
```

**Core pattern: 純粋関数 + calib slice 引数のみ + fail-loud guard** (lines 227-259 `apply_race_relative_correction` より):
```python
# D-09 fail-loud: p_cal の NaN/inf 検査（neutral 補完・silent fallback 禁止）。
if not np.all(np.isfinite(p_cal)):
    n_bad = int(np.sum(~np.isfinite(p_cal)))
    raise RuntimeError(
        f"apply_race_relative_correction: p_cal に {n_bad} 件の非 finite 値 "
        f"(NaN/inf)・binary logit 欠損 fail-loud（D-09・silent fallback 禁止）"
    )
# ...race 毎に α_r を解き final p を算出（race 自己完結・D-10）。
# np.unique(race_ids) で他 race の logit が混入しないことを構造的に保証（Pitfall 5）。
for rid in np.unique(race_ids):
    mask = race_ids == rid
    # ...
    p_final[mask] = 1.0 / (1.0 + np.exp(-(s_race / theta + alpha_r)))
return p_final
```

**Phase 12 p_lower 関数の契約** (D-01/D-02・CONTEXT.md より):
```python
def compute_p_lower_conformal_shrinkage(
    p_final: np.ndarray,
    y_calib: np.ndarray,
    p_final_calib: np.ndarray,
    *,
    q_level: float = 0.90,
) -> tuple[np.ndarray, float]:
    """§11.2 聖域: y_calib / p_final_calib は calib slice のみ（test 窓 outcome 取らない）。
    q_level=0.90 は事前登録値・test 窓で変更不可。
    byte-reproducible: np.quantile は default linear interpolation・seed 非依存。"""
    if not (0.0 < q_level < 1.0):
        raise ValueError(...)
    r_calib = np.maximum(0.0, p_final_calib - y_calib)  # overprediction residual
    q_shrink = float(np.quantile(r_calib, q_level))
    p_lower = np.maximum(0.0, p_final - q_shrink)
    return p_lower, q_shrink
```

**Error handling**: `RuntimeError`/`ValueError` で fail-loud（silent fallback 禁止・Phase 10 gap-closure CR-01〜04 鏡像・L227-232 と同一 idiom）。

**SAFE-01 聖域**: 本モジュールは feature 構築経路（`FEATURE_COLUMNS`/`build_training_frame`/`load_feature_matrix`）を import しない（L40-46 が binning のみ）。p_lower 関数も `p_final`/`y_calib` のみを取り・odds/ninki 系は引数に取らない（tests/audit/test_audit_race_relative.py の AST 検査がそのまま適用可能）。

---

### `src/model/orchestrator.py` (service, request-response) — L754 後に p_lower 挿入

**Analog:** 同一ファイル `train_and_predict` L706-754（race-relative 補正ブロック・theta is not None 分岐）

**Imports pattern** (lines 67-80・orchestration 層は一方向 import):
```python
from src.model.calibrator import CalibrationResult, calibrate_model
from src.model.data import make_X_y, split_3way
from src.model.predict import PREDICTION_COLUMNS, make_model_version, predict_p_fukusho
from src.model.race_relative import apply_race_relative_correction
# ↑ Phase 12 は compute_p_lower_conformal_shrinkage もここに追加
from src.model.trainer import (...)
```

**Core pattern: race-relative 補正ブロック（theta is not None 分岐）** (lines 714-754):
```python
if theta is not None:
    # ... (中略: sales_start_entry_count → k_per_race 変換)
    # 補正層呼出（race_relative.apply_race_relative_correction・D-06 step 6-8）
    p_final = apply_race_relative_correction(
        pred_proba.to_numpy(),
        theta=theta,
        k_per_race=k_per_race_arr,
        race_ids=race_keys,
    )
    pred_proba = pd.Series(p_final, index=X_score.index, name="p_fukusho_hit")
# ↑ Phase 12 挿入ポイント: この直後（L754 後）に q_shrink 計算と pred_df への
# p_fukusho_hit_lower 付与を挿入。theta is not None 分岐の中で・score_split="calib"
# 経路で calib slice のみ q_shrink 計算（§11.2 聖域の機械保証・L711 注記参照）。
```

**meta 列付与パターン（L801-826）の再利用**:
```python
# pred_df に backtest 用 meta 列（race_start_datetime / race_key）を付与
pred_df = pred_df.copy()
# ...（REVIEW WR-08: PREDICTION_COLUMNS と重複しないことを付与前に assert）
# Phase 12 は p_fukusho_hit_lower を PREDICTION_COLUMNS 内に追加するため・
# この meta 付与経路でなく predict_p_fukusho 側（PREDICTION_COLUMNS 構築）で付与する。
```

**Provenance 追加パターン** (L828-846):
```python
return {
    "estimator": estimator,
    # ...
    "race_relative_theta": theta,          # ← Phase 11 codex HIGH#1
    "score_split": score_split,
    # Phase 12 追加: q_level / q_shrink / shrinkage_method provenance（§19.1 再現性）
}
```

---

### `src/model/predict.py` (service, transform) — PREDICTION_COLUMNS 19→20・`_assert_valid_prediction_df` 拡張

**Analog:** 同一ファイル（is_primary 追加 Phase 6 / provenance 3列追加 Phase 11 と同一 idiom）

**PREDICTION_COLUMNS 列順序契約** (lines 68-98・現在19列・3ファイル連鎖 Pitfall 4):
```python
# provenance (5) + PK RACE_KEY (7) + 予測値 (1) + 補助メタ (2) +
# §19.1 metadata (3) + is_primary (1) = 19 列
# schema.py PREDICTION_TABLE_DDL + PREDICTION_ADD_IS_PRIMARY_SQL +
# PREDICTION_ADD_PROVENANCE_SQL の定義順と完全一致すること
PREDICTION_COLUMNS: list[str] = [
    "model_type", "model_version", "feature_snapshot_id", "as_of_datetime", "calib_method",
    "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum",
    "p_fukusho_hit",
    # ↑ Phase 12: この直後に "p_fukusho_hit_lower" を挿入（20列化）
    "race_date", "split",
    "label_version", "odds_snapshot_policy", "backtest_strategy_version",
    "is_primary",
]
```

**`_assert_valid_prediction_df` 拡張ポイント** (lines 360-398):
```python
# 3. p_fukusho_hit ∈ [0, 1]
p = df["p_fukusho_hit"]
if (p < 0).any() or (p > 1).any():
    raise ValueError(...)
# Phase 12 追加: p_fukusho_hit_lower ∈ [0, 1]（NULL 許容・v1.0 binary 行は NULL）
#   p_lower = df["p_fukusho_hit_lower"]
#   if p_lower.notna().any():
#       pl_valid = p_lower.dropna()
#       if (pl_valid < 0).any() or (pl_valid > 1).any():
#           raise ValueError(...)
```

**predict_p_fukusho 構築パターン** (lines 306-327): `df["p_fukusho_hit"] = pred_series.values` の直後に `df["p_fukusho_hit_lower"] = ...` を挿入（v1.0 binary 呼出 `theta=None` の場合は NULL/None）。

---

### `src/db/schema.py` (config/DDL, file-I/O) — `PREDICTION_ADD_P_LOWER_SQL`・idempotent ALTER

**Analog:** 同一ファイル `PREDICTION_ADD_PROVENANCE_SQL` L145-159 / `PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL` L176-181（DROP CONSTRAINT IF EXISTS + ADD idiom）

**Imports/定数**: N/A（DDL 文字列定数）

**Core pattern: idempotent ADD COLUMN IF NOT EXISTS + CHECK 制約** (lines 145-159):
```python
PREDICTION_ADD_PROVENANCE_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS label_version varchar(32) NOT NULL DEFAULT 'unspecified';
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS odds_snapshot_policy varchar(32) NOT NULL DEFAULT 'unspecified';
...
COMMENT ON COLUMN prediction.fukusho_prediction.label_version IS
    'Phase 11 SC#5 §19.1 metadata: label_version. DEFAULT ''unspecified'' sentinel ...';
"""
```

**Phase 12 `PREDICTION_ADD_P_LOWER_SQL` 雛形** (NULL 許容・v1.0 binary 行の後方互換):
```python
PREDICTION_ADD_P_LOWER_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS p_fukusho_hit_lower double precision;
ALTER TABLE prediction.fukusho_prediction
    DROP CONSTRAINT IF EXISTS prediction_p_lower_range;
ALTER TABLE prediction.fukusho_prediction
    ADD CONSTRAINT prediction_p_lower_range
    CHECK (p_fukusho_hit_lower IS NULL OR
           (p_fukusho_hit_lower >= 0 AND p_fukusho_hit_lower <= 1));
COMMENT ON COLUMN prediction.fukusho_prediction.p_fukusho_hit_lower IS
    'Phase 12 SC#1: p_fukusho_hit の下側信頼限界. v1.0 binary 行は NULL.';
"""
```

**APPLY_ORDER 追加ポイント** (lines 380-403・`prediction_extend_model_type_domain` の直後):
```python
APPLY_ORDER = [
    # ...
    ("prediction_extend_model_type_domain", PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL),
    # Phase 12 追加: この直後
    ("prediction_add_p_lower", PREDICTION_ADD_P_LOWER_SQL),
    # ...
]
```

**権限**: ALTER TABLE は owner/admin 権限必要（memory: migration-privilege-admin-required・`run_apply_schema.py` idiom・etl ロールで `InsufficientPrivilege`）。run_phase11_evaluation.py L286-290 注記と同一（"ALTER TABLE は owner 権限が必要で etl ロールでは InsufficientPrivilege となるため・本 script では migration を実行せず run_apply_schema.py に一本化"）。

**`__all__` への追加** (lines 406-424): `PREDICTION_ADD_P_LOWER_SQL` を追加。

---

### `src/db/prediction_load.py` (service, file-I/O) — `_FLOAT_COLS` 拡張・3ファイル連鎖

**Analog:** 同一ファイル `_df_to_prediction_tuples` L111-183（Pitfall 4 3ファイル連鎖）

**型変換定数** (lines 91-96):
```python
_FLOAT_COLS = {"p_fukusho_hit"}
# ↑ Phase 12: {"p_fukusho_hit", "p_fukusho_hit_lower"} に拡張
_INT_COLS = {"year", "kaiji", "racenum", "umaban", "kettonum"}
_BOOL_COLS = {"is_primary"}
```

**Core pattern: PREDICTION_COLUMNS 列順で tuple 構築** (lines 134-183):
```python
for _, row in df.iterrows():
    vals: list[Any] = []
    for c in PREDICTION_COLUMNS:
        v = row.get(c)
        # ...
        elif c in _FLOAT_COLS:
            if v is None or _is_na(v):
                vals.append(None)      # ← v1.0 binary 行は p_lower=None で NULL INSERT
            else:
                vals.append(float(v))
    out.append(tuple(vals))
```

`_FLOAT_COLS` に `p_fukusho_hit_lower` を追加するだけで・列順は `PREDICTION_COLUMNS` を import して従うため・INSERT SQL 構築（L241/L292/L331 の `cols = list(PREDICTION_COLUMNS)`）は自動的に追従する（3ファイル連鎖の auto-propagation・Pitfall 4 対策は `_assert_valid_prediction_df` が列順序を検証）。

---

### `src/ev/ev_rank.py` (utility, transform) — EV_lower 入力列差し替え

**Analog:** 同一ファイル `compute_ev_and_rank` L107-113（構造変更不要・入力列差し替えのみ D-03）

**Core pattern** (lines 107-113):
```python
out = df.copy()
# §11.1 直線積（pandas Series 演算）・NaN は伝播して EV_lower/upper も NaN
out["EV_lower"] = out["p_fukusho_hit"] * out["fuku_odds_lower"]
out["EV_upper"] = out["p_fukusho_hit"] * out["fuku_odds_upper"]
# ↑ Phase 12: 呼出側で入力列を差し替え（D-03）。
#   パターンA: 呼出側で df["p_fukusho_hit"] = df["p_fukusho_hit_lower"] で alias 作成
#   パターンB: ev_rank に p_col 引数を追加して差し替え可能に
# 構造変更不要・入力列差し替えのみ。
```

**閾値定数** (lines 28-34・`p_min` は Phase 12 で事前登録・Claude's Discretion):
```python
RANK_THRESHOLDS: dict[str, dict[str, float]] = {
    "S": {"ev_lower_min": 1.20, "p_min": 0.25, "odds_lower_min": 1.5},
    # ↑ p_min は p_lower ベースで再解釈（planner 事前登録・Pitfall 7）
}
```

---

### `src/ev/purchase_simulator.py` (utility, transform) — `select_bets` `p_min` 再解釈

**Analog:** 同一ファイル `select_bets` L86-114（入力列差し替え・閾値事前登録）

**Core pattern: 3条件 filter + レース内 top-2 mergesort** (lines 94-107):
```python
cond_mask = (
    (eligible["EV_lower"] >= FUKUSHO_EV_V1_THRESHOLDS["ev_lower_min"])
    & (eligible["p_fukusho_hit"] >= FUKUSHO_EV_V1_THRESHOLDS["p_min"])
    & (eligible["fuku_odds_lower"] >= FUKUSHO_EV_V1_THRESHOLDS["odds_lower_min"])
)
# ↑ Phase 12: p_fukusho_hit を p_fukusho_hit_lower に差し替え（入力列差し替え・D-03）。
# planner 事前登録（Claude's Discretion「SC#4 gate の具体的閾値」と整合）:
#   p_min を p_lower ベースで 0.15 にするか・p ベースで 0.15 を維持するか（Pitfall 7）。
eligible = eligible.loc[cond_mask]
eligible = eligible.sort_values(
    ["race_key", "EV_lower", "umaban"],
    ascending=[True, False, True],
    kind="mergesort",   # 共有パターン7・seed 非依存の決定論化
)
selected = eligible.groupby("race_key", group_keys=False).head(max_bets_per_race)
```

---

### `src/ev/refund_accounting.py` (utility, request-response) — `_lookup_payfukusyo_pay` slippage 計算の対（再利用のみ）

**Analog:** 同一ファイル `_lookup_payfukusyo_pay` L38-75 / `determine_stake_payout` L78-177（変更不要・再利用のみ）

**Core pattern: slot 照合** (lines 52-75):
```python
def _lookup_payfukusyo_pay(row: pd.Series) -> int:
    """row.umaban を PayFukusyoUmaban1..5 slot と照合し・該当 slot の
    PayFukusyoPay1..5 を返す（同着で slot 2-5 使用可・該当なしは 0）。"""
    try:
        umaban = int(row.get("umaban"))
    except (TypeError, ValueError):
        return 0
    for slot in range(1, 6):
        umaban_col = f"payfukusyoumaban{slot}"
        pay_col = f"payfukusyopay{slot}"
        # ...
# ↑ Phase 12 slippage 計算（D-07）:
#   payout/100 - fuku_odds_lower で snapshot→final payout slippage
#   （planner が測定式を事前登録・CONTEXT.md Claude's Discretion）
# 本関数は変更不要・再利用のみ。
```

---

### `src/ev/metrics.py` (utility, transform) — `compute_backtest_metrics` group-by 適用

**Analog:** 同一ファイル `compute_backtest_metrics` L30-107（純粋関数・DB 不要・group-by の土台）

**Core pattern: 純粋 pandas 関数・ゼロ除算回避** (lines 78-97):
```python
total_payout = float(df["payout_amount"].sum())
total_effective_stake = float(df["effective_stake"].sum())
# §11.6 回収率（ゼロ除算回避・§8.3）
recovery_rate = (
    total_payout / total_effective_stake if total_effective_stake > 0 else 0.0
)
# ↑ Phase 12 EV-decile/disagreement ROI: group-by で各 bin に本関数を適用
#   for bin_label, group in df.groupby("ev_decile"):
#       metrics = compute_backtest_metrics(group)
# 拡張しない（再利用のみ・group-by は run_phase12_evaluation.py 側）。
```

---

### `src/ev/report.py` (service, file-I/O) — REPORT_COLUMNS 拡張・switch_recommendation 表示

**Analog:** 同一ファイル `REPORT_COLUMNS` L41-53 / `generate_report` L176-274

**Core pattern: 列契約の外部化** (lines 41-53):
```python
REPORT_COLUMNS: tuple[str, ...] = (
    "backtest_id", "bt_name", "odds_policy", "model_type",
    "recovery_rate", "P/L", "max_DD", "selected", "effective_bet", "refund", "hit_rate",
)
# ↑ Phase 12: switch_recommendation・falsification 結果の表示列を追加
#   （拡張指標は上書きでなく併載・§15.2 不変・D-06/D-07）
```

**byte-reproducible JSON 書き出し** (lines 250-272):
```python
json_payload = json.dumps(
    {...},
    sort_keys=True,
    ensure_ascii=False,
)
_atomic_write_text(json_path, json_payload)
# ↑ Phase 12: switch_recommendation / falsification_result / q_level / q_shrink を
#   JSON に併載（sort_keys=True・byte-reproducible・Shared Pattern atomic write）。
```

---

### `src/model/segment_eval.py` (utility, transform) — binning 契約再利用（変更不要）

**Analog:** 同一ファイル `_odds_band` L151-158 / `evaluate_segment_axis` L166-285 / `ODDS_BAND_EDGES` L74

**Core pattern: np.digitize で決定論的 binning** (lines 120-139):
```python
def _band_labels_from_edges(s, edges, labels):
    arr = s.to_numpy(dtype=float)
    nan_mask = ~np.isfinite(arr)
    arr_filled = np.where(nan_mask, 0.0, arr)
    bin_idx = np.digitize(arr_filled, bins=edges[1:-1], right=True)
    bin_idx = np.clip(bin_idx, 0, len(labels) - 1)
    # ...
```

**ODDS_BAND_EDGES 定数** (lines 74-75・Phase 12 SC#4 WARN gate が踏襲):
```python
ODDS_BAND_EDGES: np.ndarray = np.array([0.0, 2.9, 4.9, 9.9, np.inf])
ODDS_BAND_LABELS: tuple[str, ...] = ("1.0-2.9", "3.0-4.9", "5.0-9.9", "10+")
# ↑ Phase 12: import 再利用・独自 binning 禁止（codex review HIGH#2・bit-identical）
#   EV-decile / disagreement binning も pd.qcut(..., duplicates='drop') で
#   決定論化（index 依存を避ける・np.digitize と組み合わせ）
```

**Phase 12 は本ファイルを変更しない**（import 再利用のみ・run_phase12_evaluation.py が `from src.model.segment_eval import ODDS_BAND_EDGES, _odds_band, evaluate_segment_axis`）。

---

### `src/model/evaluator.py` (service, request-response) — `check_acceptance_gate` `warn_reasons` に Phase 12 WARN gate 追加

**Analog:** 同一ファイル `check_acceptance_gate` L888-1029（BLOCK/WARN hybrid・D-02 AND 条件・D-03 WARN 分離）

**Core pattern: BLOCK/WARN 分離** (lines 938-1016):
```python
block_reasons: list[str] = []
warn_reasons: list[str] = []
# --- BLOCK 条件1: baselines 全敗 ---
# --- BLOCK 条件2: sum(p) 著乖離 ---
block_triggered = baselines_all_lose and sum_p_violation   # D-02 AND 条件
# ...
else:
    # WARN 分離（REVIEW HIGH#2）: 片方だけ成立の場合は warn_reasons に記録（出荷停止しない）
    if baselines_all_lose:
        for mm in main_models_losing:
            warn_reasons.append(...)
    if sum_p_violation:
        # ...
# ↑ Phase 12: §15.2 gate は不変（D-06）・warn_reasons に Phase 12 専用 WARN gate を追加
#   （selected-only/odds-band conditional calib・BLOCK でなく WARN・CONTEXT.md D-06）
```

**Return dict 構造** (lines 1018-1029):
```python
return {
    "block_triggered": block_triggered,
    "block_reasons": block_reasons,
    "warn_reasons": warn_reasons,
    "gate_verdict": "BLOCK" if block_triggered else "WARN",
    # ...
    # Phase 12 追加: "phase12_warn_triggered" / "phase12_warn_reasons" など
    # （SC#4 オッズ帯別条件付き calib WARN gate の結果・D-06）
}
```

---

### `src/model/artifact.py` (service, file-I/O) — metadata.json に `q_level`/`shrinkage_method` 保存

**Analog:** 同一ファイル `save_native_artifact` L98-218（`race_relative_theta` metadata 追加 Phase 11 と同一 idiom）

**Core pattern: metadata dict + sort_keys=True atomic write** (lines 202-217):
```python
metadata = {
    "model_version": model_version,
    "base_model_type": base_model_type,
    # ...
    # Phase 11 race-relative provenance（§19.1・codex MEDIUM）
    "race_relative_theta": race_relative_theta,
    "race_relative_alpha_search_xtol": 1e-9,
    "race_relative_p_cal_clip_epsilon": 1e-6,
    # ↑ Phase 12 追加（§19.1 再現性・q_level / shrinkage method metadata）:
    #   "p_lower_q_level": q_level,         # 事前登録値（0.90）
    #   "p_lower_q_shrink": q_shrink,       # calib slice で計算した実数値
    #   "p_lower_shrinkage_method": "calibration_residual_conformal",  # D-01
}
write_metadata_json(out, metadata)
```

**`save_native_artifact` シグネチャ拡張** (lines 98-110):
```python
def save_native_artifact(
    calibrated_estimator, base_model_type, model_version, *,
    feature_snapshot_id, hyperparams, seed, train_calib_test_periods, calib_method,
    race_relative_theta=None,
    # Phase 12 追加: q_level / q_shrink / shrinkage_method を keyword-only 引数で
    out_dir=None,
) -> Path:
```

---

### `scripts/run_phase12_evaluation.py` (script, request-response/batch) — run_phase11_evaluation.py 構造踏襲

**Analog:** `scripts/run_phase11_evaluation.py`（全体構造・API chain・gate・report）

**Imports/ヘッダ idiom** (L82-118):
```python
from __future__ import annotations
import argparse, json, logging, math, sys
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §15.2 事前登録指標不変: binning 定数を import 再利用（再定義禁止・bit-identical）
from src.model.evaluator import (CALIBRATION_CURVE_BINS, CALIBRATION_CURVE_MIN_BIN_COUNT, compute_metrics)
from src.model.predict import make_model_version
from src.model.race_relative import (compute_p_lower_conformal_shrinkage,)  # Phase 12 新関数
from src.model.segment_eval import (NINKI_BAND_EDGES, ODDS_BAND_EDGES, evaluate_all_segments)
# Phase 12 新規依存:
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
```

**事前登録値 idiom** (L128-140):
```python
# D-04/D-05 事前登録（§11.2 聖域・評価後変更禁止）
Q_LEVEL: float = 0.90  # shrinkage quantile（D-02・q_alpha 変数名は避ける）
TOLERANCE_BRIER: float = 0.005
# Phase 12 新規: odds clipping / logit eps / Holm alpha / market method 閾値
ODDS_CLIP_MIN: float = 1.0
ODDS_CLIP_MAX: float = 100.0
LOGIT_CLIP_EPS: float = 1e-6   # = race_relative.P_CAL_CLIP_EPSILON と同一契約
HOLM_ALPHA: float = 0.05
MARKET_CALIB_SAMPLE_THRESHOLD: int = 1000  # ≥1000 → isotonic / <1000 → sigmoid
BT1_PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2019-06-01", "2022-06-30"),
    "calib": ("2022-07-01", "2022-12-31"),
    "test":  ("2023-01-01", "2023-12-31"),
}
```

**API chain idiom** (L296-305・REVIEW H6):
```python
feature_df = load_feature_matrix(snapshot_id=args.baseline_snapshot_id)
label_df = load_labels(cur)
frame = build_training_frame(feature_df, label_df)
cat_map = load_frozen_maps(snapshot_id=args.baseline_snapshot_id)
# ... → train_and_predict(...) を baseline(theta=None) / race-relative(theta=selected)
#      の2通りで test 窓評価（run_phase11 と同一・B-3 delta）
```

**θ 選択経路 idiom から派生する q_shrink 計算経路** (L499-546 `_select_theta_on_calib`):
```python
# Phase 12 は θ 選択経路（run_phase11 で確定済み θ=1.0・reports/11-evaluation に事前書き出し済み）
# を再利用しつつ・calib slice のみで q_shrink を計算する経路を新設する。
# score_split="calib" が構造的に test 窓に触れない（codex HIGH#1・§11.2 聖域の機械保証）。
# q_shrink 計算は calib slice の pred_proba と y_calib のみ（test 窓 outcome 取らない）。
```

**`_atomic_write_text` / `_sanitize_for_json` idiom** (L219-224 / L191-216):
```python
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
# ↑ Shared Pattern 7（artifact.py / segment_eval.py と同一）。
#   Phase 12 reports/12-* の JSON/MD 書き出しに再利用。
```

**`_evaluate_gate` idiom** (L896-1078):
```python
def _evaluate_gate(*, baseline_pred, rr_pred, ...) -> dict[str, Any]:
    # ... compute_metrics で Brier/LogLoss/AUC 算出（binning 定数は evaluator から import 再利用）
    # D-04 非劣化 / D-05 改善 gate 判定
    # Phase 12 拡張: SC#4 WARN gate / switch_recommendation / falsification 結果を統合
    #   gate_pass は §15.2 gate（不変）・Phase 12 WARN gate は別途 report（D-06/D-07）
```

**D-10 AST check 対応** (L36-44 docstring の idiom・set_primary_model は Call node 0件):
```python
# D-10: Phase 12 では DB の is_primary 変更を自動で行わない。
# set_primary_model という識別子は docstring 以外の code に出現しない
# （AST check が Call node 0件を保証・tests/audit/test_audit_p_lower_falsification.py で検証）。
```

**statement_timeout idiom** (L271-280・memory: subagent-db-query-statement-timeout):
```python
def _configure_statement_timeout(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()
readonly_pool = make_pool(settings, role="readonly", configure=_configure_statement_timeout)
```

---

### `src/eval/falsification.py` (新規, service, transform) — statsmodels ロジット回帰（clustered SE）

**Analog:** `scripts/run_phase11_evaluation.py::_select_theta_on_calib`（calib slice のみ設計・test 窓聖域の機械保証 idiom）

**注意**: `src/eval/` ディレクトリは現状存在しない。`src/ev/`（EV 計算層）とは別。Phase 12 で新設するか `scripts/run_phase12_evaluation.py` 内に純粋関数として実装するかは planner 裁量（RESEARCH.md 推奨は run_phase12_evaluation.py 内の純粋関数）。

**Core pattern（RESEARCH.md Pattern 5 より・statsmodels cov_kwds API）**:
```python
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

def run_falsification_test(
    y_outcome_test, market_implied_test, model_p_test, race_id_test,
    field_size_test=None,
) -> dict:
    """§11.2 聖域: market_implied calibrator は train/calib 窓で fit 済み・本関数は test 窓に適用のみ。
    D-05: α=0.05 単一係数検定 (model_p)・race_id clustered SE。
          bin/odds_band サブ解析のみ Holm 補正 (multipletests method='holm')。"""
    eps = 1e-6  # logit clipping・race_relative.P_CAL_CLIP_EPSILON と同一契約
    def logit_clip(p):
        p_c = np.clip(p, eps, 1 - eps)
        return np.log(p_c / (1 - p_c))
    # ... X 構築・sm.add_constant
    # ★ Pitfall 4: cov_kwds={'groups': race_id} が正しい API・groups= 直接渡しは error (GitHub #6287)
    result = model.fit(cov_type="cluster", cov_kwds={"groups": race_id_test},
                       disp=0, maxiter=200)
    return {
        "model_p_coef": ..., "model_p_pvalue": ...,
        "model_p_significant": model_p_pvalue < 0.05,
        "verdict": "feature_gap" if model_p_pvalue < 0.05 else "structural_limit",
    }
```

**market_implied 再校正（RESEARCH.md Pattern 6・train/calib のみ・test 窓聖域）**:
```python
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

def fit_market_implied_calibrator(odds_calib, y_calib, *, calib_sample_size) -> CalibratedClassifierCV:
    """D-04: 1/odds を outcome に calibration（isotonic/Platt）。
    method 選択: calib_sample_size >= 1000 → isotonic / < 1000 → sigmoid（sklearn docs）。
    cv='prefit' 相当（sklearn 1.9.0 では FrozenEstimator・utils/calibrator.py idiom）。"""
    odds_clipped = np.clip(odds_calib, ODDS_CLIP_MIN, ODDS_CLIP_MAX)
    market_base_p = 1.0 / odds_clipped
    method = "isotonic" if calib_sample_size >= MARKET_CALIB_SAMPLE_THRESHOLD else "sigmoid"
    # ... FrozenEstimator + CalibratedClassifierCV（utils/calibrator.py L100-102 idiom）
```

**shared `utils/calibrator.py` idiom** (L100-102・sklearn 1.9.0 prefit):
```python
frozen = FrozenEstimator(base_estimator)
cal = CalibratedClassifierCV(estimator=frozen, method=method)
cal.fit(X_calib, y_calib)
return cal
```

---

### `tests/audit/test_audit_p_lower_falsification.py` (新規, test/adversarial, event-driven) — 5段階鋳型

**Analog:** `tests/audit/test_audit_race_relative.py`（完全同一構造・5段階鋳型 (a)(b)(c)(d)(g)(6)）

**Imports/forbidden tokens idiom** (L31-50):
```python
from __future__ import annotations
import ast, inspect, re, textwrap
import numpy as np
from src.model import race_relative
# Phase 12: from src.eval import falsification または run_phase12_evaluation 内関数

_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)
```

**5段階鋳型 (a)(b)(c): AST forbidden Name/Attribute/Constant 0件** (L89-160):
```python
def _scan_module_for_forbidden_tokens(module_obj) -> tuple[list[str], list[str]]:
    source = inspect.getsource(module_obj)
    tree = ast.parse(textwrap.dedent(source))
    # ast.Name / ast.Attribute / ast.Constant を走査
# ↑ Phase 12: p_lower 計算関数 / falsification 関数が FEATURE_COLUMNS 構築経路に
#   odds/ninki proxy を混入させないことを保証（SAFE-01 聖域）。
#   falsification は test 窓 odds を evaluation 専用層で使うが・FEATURE_COLUMNS には混入させない。
```

**SAFE-01-ALLOW マーカー idiom** (L189-244):
```python
_MARKET_SIGNAL_ARG_ALLOWLIST_MARKER = "SAFE-01-ALLOW: market_signal"
def test_market_signal_arg_has_allowlist() -> None:
    funcs_with_market_signal = _find_functions_with_market_signal_arg(race_relative)
    for func_name, func_node in funcs_with_market_signal:
        docstring = ast.get_docstring(func_node) or ""
        assert _MARKET_SIGNAL_ARG_ALLOWLIST_MARKER in docstring
# ↑ Phase 12: market_implied / odds / model_p 引数を持つ falsification 関数にも
#   SAFE-01-ALLOW マーカーを docstring に明示させる（feature 構築経路からの切り離し機械保証）。
```

**自己完結性 test idiom (6)** (L250-378):
```python
def test_alpha_self_contained_outcome_swap() -> None:
    sig = inspect.signature(race_relative.solve_alpha_for_race)
    forbidden_params = {"y_true", "outcome", "label", "y", "labels", "target"}
    actual_params = set(sig.parameters.keys())
    leak_params = actual_params & forbidden_params
    assert not leak_params
# ↑ Phase 12: compute_p_lower_conformal_shrinkage のシグネチャ検証。
#   ★ q_shrink 計算が calib slice のみで・test 窓 outcome を取らないことを構造的保証。
#   forbidden_params に "y_test" / "outcome_test" を追加して p_lower 計算関数を検証。
#   通過引数は {p_final, y_calib, p_final_calib, q_level} のみ（test 窓 outcome 系不可）。
```

**false-pass 回避 (g)** (L383-471):
```python
def test_false_pass_detection_power() -> None:
    # 意図的に禁止トークンを含むダミーソースを構築し AST parse して検出力証明
# ↑ Phase 12: そのまま再利用（p_lower/falsification モジュールへの拡張も同一 idiom）。
```

**Phase 12 新規 test: falsification leakage 検出** (run_phase12_evaluation.py 連携):
```python
def test_falsification_no_test_outcome_leak() -> None:
    """§11.2 聖域: falsification 回帰設計が test 窓 outcome を学習に使わない。
    fit_market_implied_calibrator のシグネチャが calib 引数のみ（test 窓 outcome 取らない）を検証。"""
    sig = inspect.signature(fit_market_implied_calibrator)
    forbidden = {"y_test", "outcome_test", "y_outcome_test"}
    actual = set(sig.parameters.keys())
    assert not (actual & forbidden)
```

**Phase 12 新規 test: set_primary_model Call 0件（D-10）**:
```python
def test_no_set_primary_model_call() -> None:
    """D-10: run_phase12_evaluation.py の AST で set_primary_model Call node が0件。"""
    import scripts.run_phase12_evaluation as mod
    source = inspect.getsource(mod)
    tree = ast.parse(textwrap.dedent(source))
    call_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "set_primary_model":
                call_count += 1
            elif isinstance(func, ast.Attribute) and func.attr == "set_primary_model":
                call_count += 1
    assert call_count == 0
```

---

### `pyproject.toml` (config, file-I/O) — `statsmodels>=0.14.6` 追加

**Analog:** 同一ファイル `dependencies` L10-27（scipy 既存）

**Core pattern: dependencies リストへの追記** (lines 10-27):
```toml
dependencies = [
    "psycopg[binary]==3.3.4",
    # ...
    "scipy>=1.17.1",
    # ↑ Phase 12: この直後に statsmodels を追加
    "statsmodels>=0.14.6",   # falsification clustered SE / Holm 補正（RESEARCH.md Standard Stack）
    "streamlit==1.58.0",
]
```

**インストール検証 idiom** (RESEARCH.md より):
```bash
uv add "statsmodels>=0.14.6"
uv sync --frozen  # uv.lock に反映・byte-reproducible（§19.1）
# requires: numpy<3,>=1.22.3 / scipy!=1.9.2,>=1.8 / pandas>=1.4（本プロジェクトと互換）
```

---

## Shared Patterns

### Shared Pattern 1: 事前登録パターン（Phase 10 D-12 / Phase 11 D-03 踏襲）

**Source:** `scripts/run_phase11_evaluation.py` L128-140 (`TOLERANCE_*` / `BT1_PERIODS`) / `src/model/race_relative.py` L73-82 (`THETA_CANDIDATES`)

**Apply to:** `scripts/run_phase12_evaluation.py` の `Q_LEVEL` / `ODDS_CLIP_*` / `LOGIT_CLIP_EPS` / `HOLM_ALPHA` / `MARKET_CALIB_SAMPLE_THRESHOLD`

```python
# §11.2 聖域・test 窓で選び直し禁止・候補集合を Plan に書き・train/calib 窓内のみで選ぶ
Q_LEVEL: float = 0.90
TOLERANCE_BRIER: float = 0.005
# ...（L128-140 と同一 idiom・docstring に「§11.2 聖域・評価後変更禁止」と明記）
```

### Shared Pattern 2: §15.2 binning 契約の import 再利用（bit-identical・独自 binning 禁止）

**Source:** `src/model/segment_eval.py` L54-61 / `scripts/run_phase11_evaluation.py` L101-118

**Apply to:** `scripts/run_phase12_evaluation.py` の EV-decile / disagreement binning・SC#4 オッズ帯別条件付き calib gate

```python
from src.model.evaluator import (CALIBRATION_CURVE_BINS, CALIBRATION_CURVE_MIN_BIN_COUNT, compute_metrics)
from src.model.segment_eval import (NINKI_BAND_EDGES, ODDS_BAND_EDGES, evaluate_all_segments, _odds_band)
# 再定義禁止・codex review HIGH#2・np.digitize で決定論化（pd.cut は index 依存で不使用）
```

### Shared Pattern 3: byte-reproducible atomic write（Shared Pattern 7）

**Source:** `src/model/artifact.py` L59-69 (`_atomic_write_text`) / `src/ev/report.py` L33 / `scripts/run_phase11_evaluation.py` L219-224

**Apply to:** `scripts/run_phase12_evaluation.py` の reports/12-* 書き出し・`_sanitize_for_json` idiom

```python
def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)
# json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False) と組み合わせ（RFC 8259 strict）
```

### Shared Pattern 4: fail-loud（silent fallback 禁止・Phase 10 gap-closure CR-01〜04 鏡像）

**Source:** `src/model/race_relative.py` L227-232 / L136-149 / `src/model/predict.py` L360-398

**Apply to:** `compute_p_lower_conformal_shrinkage` / `run_falsification_test` / `fit_market_implied_calibrator` / `_assert_valid_prediction_df` 拡張

```python
if not np.all(np.isfinite(p_cal)):
    n_bad = int(np.sum(~np.isfinite(p_cal)))
    raise RuntimeError(
        f"... {n_bad} 件の非 finite 値 ... fail-loud（D-09・silent fallback 禁止）"
    )
# q_shrink 計算不能・falsification 回帰失敗（ConvergenceWarning）・p_lower range 外 は RuntimeError
```

### Shared Pattern 5: SAFE-01-ALLOW マーカー（feature 構築経路からの odds/ninki 切り離し）

**Source:** `src/model/race_relative.py` L301-314 (`compute_overprediction_penalty` docstring) / `tests/audit/test_audit_race_relative.py` L173-244

**Apply to:** `src/eval/falsification.py` の `market_implied`/`odds`/`model_p` 引数・`compute_p_lower_conformal_shrinkage` が `p_final` のみ消費（odds 系引数に取らない）

```python
"""SAFE-01-ALLOW: market_signal
本関数は market_signal 引数（odds 系外部参照）を受け取る。evaluation 専用層の境界。
FEATURE_COLUMNS / build_training_frame / load_feature_matrix 等の feature 構築経路から切り離されている。"""
# ↑ このマーカーが docstring に無い場合は tests/audit/test_audit_p_lower_falsification.py が fail-loud
```

### Shared Pattern 6: §11.2 聖域ブロック（calib slice のみ・test 窓 outcome 取らない）

**Source:** `scripts/run_phase11_evaluation.py` L449-455 (`score_split` guard) / L499-546 (`_select_theta_on_calib`) / `src/model/orchestrator.py` L449-455

**Apply to:** `compute_p_lower_conformal_shrinkage` / `fit_market_implied_calibrator` / `run_falsification_test` のシグネチャ設計

```python
# 関数シグネチャで test 窓 outcome を取らない（構造的聖域ブロック・docstring 紳士協定でない）
def compute_p_lower_conformal_shrinkage(
    p_final, y_calib, p_final_calib, *, q_level=0.90
) -> tuple[np.ndarray, float]:
    # y_test / outcome_test / y_outcome_test は引数に取らない
    # tests/audit が inspect.signature で検証（test_alpha_self_contained_outcome_swap idiom）
```

### Shared Pattern 7: owner/admin 権限での ALTER TABLE（memory: migration-privilege-admin-required）

**Source:** `scripts/run_phase11_evaluation.py` L286-290（migration は run_apply_schema.py に一本化） / `src/db/schema.py` L117-181（idempotent ALTER idiom）

**Apply to:** `PREDICTION_ADD_P_LOWER_SQL` の適用経路

```python
# ALTER TABLE は owner 権限が必要で etl ロールでは InsufficientPrivilege となるため・
# run_phase12_evaluation.py では migration を実行せず run_apply_schema.py に一本化。
# (run_apply_schema.py が PREDICTION_ADD_P_LOWER_SQL を APPLY_ORDER 経由で適用)
```

## No Analog Found

該当なし。全ファイルに既存 analog が存在する。

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | `src/eval/falsification.py` は statsmodels 新規依存だが・ロジット回帰/clustering SE の API は RESEARCH.md Pattern 5/6 で実証検証済み。run_phase11_evaluation.py の calib-slice-only idiom が構造 analog。 |

## Metadata

**Analog search scope:**
- `src/model/` (race_relative.py, orchestrator.py, predict.py, evaluator.py, segment_eval.py, artifact.py, calibrator.py, utils/calibrator.py)
- `src/ev/` (purchase_simulator.py, ev_rank.py, refund_accounting.py, metrics.py, report.py, odds_snapshot.py)
- `src/db/` (schema.py, prediction_load.py)
- `scripts/` (run_phase11_evaluation.py)
- `tests/audit/` (test_audit_race_relative.py, test_audit_field_strength.py)
- `pyproject.toml`

**Files scanned:** 16+ (踏襲アсет全て)
**Pattern extraction date:** 2026-06-27
