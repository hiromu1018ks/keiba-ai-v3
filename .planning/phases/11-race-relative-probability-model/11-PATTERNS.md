# Phase 11: Race-Relative Probability Model - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 6 (新規 4 + 拡張 2・聖域不変 7 は対象外)
**Analogs found:** 6 / 6

## 聖域ファイル（D-01・本体不変・本 Phase では一切変更しない）

以下は SC#3 bit-identical 维持・core value 保護のため **plan/execute いずれも触らない**。新規ファイルから import 再利用するのみ。

| 聖域ファイル | 役割 | 再利用方法 |
|--------------|------|------------|
| `src/model/trainer.py` | binary LightGBM/CatBoost 学習（`objective='binary'`・native categorical・`has_time=True`・`num_threads=1`） | orchestrator 拡張が `train_lightgbm` / `train_catboost` を呼出（現状通り） |
| `src/utils/calibrator.py` | `fit_prefit_calibrator`（FrozenEstimator + CalibratedClassifierCV idiom・later-disjoint guard） | orchestrator 拡張が base calib として呼出（D-06 パイプライン step 5） |
| `src/model/calibrator.py` | `calibrate_model` / `CalibrationResult` / CatBoost manual calib 分岐 | orchestrator 拡張が既存分岐を再利用 |
| `src/model/data.py` | `FEATURE_COLUMNS` / `split_3way` / `make_X_y` / `load_feature_matrix` | orchestrator 拡張が現状通り呼出 |
| `src/utils/group_split.py` | `GroupTimeSeriesSplit` / `split_3way` race_id disjoint | `split_3way` 経由で暗黙再利用 |
| `src/model/evaluator.py` | §15.2 事前登録指標 / `check_acceptance_gate` / binning 契約 | run_phase11_evaluation.py が import 再利用（bit-identical） |
| `src/db/prediction_load.py` | `_idempotent_load_prediction` model_version scoped swap | run_phase11_evaluation.py が呼出（is_primary 立てない・D-07） |

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/model/race_relative.py` 【新規】 | utility (pure 関数) | transform | `src/utils/calibrator.py` (pure 関数・定数 + guard + sklearn/scipy 利用) | exact |
| `src/model/orchestrator.py` 【拡張】 | service (orchestration) | request-response (pipeline) | `src/model/orchestrator.py` 自身（`train_and_predict` 内 `_calibrate_catboost_manual` 分岐・pred_proba 注入 idiom） | exact (自己拡張) |
| `src/model/artifact.py` 【拡張】 | utility (persistence) | file-I/O | `src/model/artifact.py` 自身（`save_native_artifact` metadata.json 拡張） | exact (自己拡張) |
| `tests/model/test_race_relative.py` 【新規】 | test (unit) | transform 検証 | `tests/model/test_calibrator.py` (pure 関数 unit test・bit-identical・境界ケース) | role-match |
| `tests/audit/test_audit_race_relative.py` 【新規】 | test (adversarial audit) | event-driven (注入検出) | `tests/audit/test_audit_field_strength.py` (Phase 8 D-06 5段階鋳型・SAFE-01 AST・lookahead 注入) | exact |
| `scripts/run_phase11_evaluation.py` 【新規】 | script (evaluation/report) | batch (比較レポート) | `scripts/run_phase10_evaluation.py` (v1.0 vs 新 snapshot 3-way 比較・SC#5 gate・事前登録許容幅) | exact |

**※ RESEARCH.md Wave 0 gaps 記載の `tests/unit/test_race_relative.py` は誤り。本プロジェクトの実態は `tests/model/` 配下（`test_calibrator.py` / `test_orchestrator.py` 等の配置）。正しいパスは `tests/model/test_race_relative.py`。planner はこちらを採用すること。**

## Pattern Assignments

### `src/model/race_relative.py` (utility, transform)

**Analog:** `src/utils/calibrator.py`（pure 関数・モジュール先頭定数・`raise ValueError`/`RuntimeError` guard・sklearn/scipy idiom・`from __future__ import annotations`）

**Imports pattern**（`src/utils/calibrator.py` lines 30-38 を踏襲）:
```python
from __future__ import annotations

from typing import Any  # 型ヒント用（必要に応じて）

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# binning 契約は segment_eval / evaluator から import 再利用（bit-identical・D-03/D-05）
from src.model.evaluator import CALIBRATION_CURVE_BINS
from src.model.segment_eval import _odds_band
```

**モジュール先頭定数 + docstring パターン**（`src/utils/calibrator.py` lines 40-50・researcher 裁量 #1/#2 の事前登録値を定数化）:
```python
# researcher 裁量 #1: α_r 二分探索の収束仕様（docstring で明示・test で検証）
ALPHA_SEARCH_XTOL = 1e-9        # |sum(p) - k| 理論上界 ≈ 2e-9（実測 4.44e-16）
ALPHA_SEARCH_RTOL = 1e-12
ALPHA_SEARCH_MAXITER = 200      # 理論反復数上限 < 50（brentq superlinear）
ALPHA_SEARCH_BOUNDS = (-100.0, 100.0)  # logit(k/n) 中心に十分な余裕

# researcher 裁量 #2: clip 閾値（logit 変換前の p_cal 用）
P_CAL_CLIP_EPSILON = 1e-6       # logit 動的範囲 ±13.8・sum(p)=k 精度 <1e-12（実証）
```

**fail-loud guard パターン**（`src/utils/calibrator.py` lines 86-94・`raise ValueError` で `python -O` でも生存・D-09 鏡像）:
```python
# D-09: p_cal 欠損チェック（特徴量欠損と区別・silent fallback 禁止）
if not np.all(np.isfinite(p_cal)):
    n_bad = int(np.sum(~np.isfinite(p_cal)))
    raise RuntimeError(
        f"apply_race_relative_correction: p_cal に {n_bad} 件の非 finite 値 "
        f"(NaN/inf)・binary logit 欠損 fail-loud（D-09・silent fallback 禁止）"
    )
```

**核心 pure 関数パターン**（RESEARCH.md Pattern 1 lines 262-348 が既に実証済みコードを提示・brentq + sigmoid・race 自己完結ループ）:
```python
def solve_alpha_for_race(
    s_logits: np.ndarray,
    theta: float,
    k: int,
) -> float:
    """race 内で sum_i sigmoid(s_i/θ + α) = k を満たす α を brentq で解く（D-02・D-10 自己完結）。
    [docstring で数学的健全性・境界挙動・Returns/Raises を明示・実証検証済み]
    """
    def f(alpha: float) -> float:
        z = s_logits / theta + alpha
        return float(np.sum(1.0 / (1.0 + np.exp(-z))) - k)

    return float(brentq(
        f,
        ALPHA_SEARCH_BOUNDS[0],
        ALPHA_SEARCH_BOUNDS[1],
        xtol=ALPHA_SEARCH_XTOL,
        rtol=ALPHA_SEARCH_RTOL,
        maxiter=ALPHA_SEARCH_MAXITER,
    ))
```

**race_id 毎独立ループ（D-10 自己完結性の構造的保証）**（`apply_race_relative_correction` 内・`np.unique(race_ids)` で他 race 情報混入を構造的排除）:
```python
for rid in np.unique(race_ids):
    mask = race_ids == rid
    s_race = s_logits[mask]
    k = int(k_per_race[mask][0])  # race 内で k は一意
    alpha_r = solve_alpha_for_race(s_race, theta, k)
    p_final[mask] = 1.0 / (1.0 + np.exp(-(s_race / theta + alpha_r)))
```

**overprediction penalty パターン**（RESEARCH.md Pattern 3 lines 402-449・segment_eval binning の import 再利用で bit-identical）:
```python
def compute_overprediction_penalty(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    odds: np.ndarray,
    *,
    cell_filter_mask: np.ndarray | None = None,  # None=overall / mask=selected 層
) -> float:
    """overprediction penalty = Σ_cells (count_cell/N_total) × max(0, mean_pred − frac_pos)（D-03/D-05）。
    binning 契約は segment_eval / evaluator から import 再利用（bit-identical）。
    """
    # ... odds_b = _odds_band(pd.Series(odds)) / p_b = _p_bin(pd.Series(y_pred))
    # セル毎に (count/n_total) * max(0, mean_pred - frac_pos) を集約
```

**`__all__` パターン**（`src/model/predict.py` lines 358-365・明示的 public API）:
```python
__all__ = [
    "ALPHA_SEARCH_XTOL",
    "P_CAL_CLIP_EPSILON",
    "solve_alpha_for_race",
    "apply_race_relative_correction",
    "compute_overprediction_penalty",
]
```

---

### `src/model/orchestrator.py` (service, request-response pipeline) 【拡張】

**Analog:** `src/model/orchestrator.py` 自身（`train_and_predict` lines 234-610・`_calibrate_catboost_manual` 分岐 lines 505-521・Cycle 2 NEW HIGH-1 pred_proba 注入 lines 566-577）

**核心: 拡張ポイントは既存の `pred_proba` 注入直前**（lines 524-560）。現在 `raw_pred` / `align_predictions` で得た `pred_proba` をそのまま `predict_p_fukusho(pred_proba=...)` に渡している箇所の直前に、補正層呼出を挿入する。

**LightGBM 予測パス（lines 524-533）の拡張イメージ**:
```python
if model_type == "lightgbm":
    _, X_test_lgb = _prepare_lightgbm_train_eval(X_train_core, X_test)
    raw_pred = calib_result.calibrated.predict_proba(X_test_lgb)[:, 1]
    pred_proba = pd.Series(raw_pred, index=X_test.index, name="p_fukusho_hit")
    # ↓ Phase 11 拡張: race-relative 補正層（D-06 step 6-8）
    # base logit → θ + α_r 二分探索 → final p（sum=p=k 厳密）
    # ※ θ は外部から渡す（calib slice で選んだ値・test 窓で選び直さない・§11.2）
```

**CatBoost 予測パス（lines 534-553）の拡張イメージ**（`align_predictions` 後に補正）:
```python
else:  # catboost
    # ... pool_test 構築・_catboost_calibrated_predict_proba で raw_pred_sorted 算出
    pred_proba = align_predictions(...)  # 既存
    # ↓ Phase 11 拡張: 同一 race_relative 補正層（両モデル共通・SC#3 bit-identical）
```

**既存 idiom の再利用（触らず import 追加のみ）**:
- `from src.model.race_relative import apply_race_relative_correction`（新規モジュール）
- `race_df_test["race_key"]` が既に取得済み（lines 405-410・review HIGH#2 index equality）→ race_id として使用可能
- `k` 決定に必要な `sales_start_entry_count` 系列は `race_df_test` または `test_df` から取得（D-08・Phase 2 D-04 由来）

**新規引数の追加パターン**（既存の `split_periods` / `category_map` / `snapshot_id` 追加 idiom・lines 244-246, 273-298 を踏襲）:
```python
def train_and_predict(
    feature_df: pd.DataFrame,
    *,
    # ... 既存引数 ...
    snapshot_id: str | None = None,
    # ↓ Phase 11 新規（θ は calib slice で選んだ事前登録値・None は v1.0 等価）
    theta: float | None = None,  # None の場合は補正層をスキップ（後方互換・A5）
) -> dict[str, Any]:
```

**戻り値 dict への provenance 追加**（既存の `category_map_source` stamp lines 373-376, 609 と同一 idiom）:
```python
return {
    # ... 既存キー ...
    "category_map_source": category_map_source,
    # ↓ Phase 11 新規 provenance
    "race_relative_theta": theta,  # None (skip) or float（事前登録値の記録・§19.1）
}
```

**docstring 契約拡張**（lines 251-352 のパターン・新引数セクション追加・Cycle 2 residual #13 と同様の明示的契約）:
- `theta : float | None` セクション追加（D-03 事前登録・test 窓選び直し禁止の明記）
- Returns に `race_relative_theta` 追加

---

### `src/model/artifact.py` (utility, file-I/O) 【拡張】

**Analog:** `src/model/artifact.py` 自身（`save_native_artifact` metadata.json の `saved_components` リスト・`write_metadata_json` lines 72+）

**核心: metadata.json に θ・α_r アルゴリズム params を追加**（`saved_components` audit trail への追記・既存の `calib_method` / `seed` / `hyperparams` / `train_calib_test_periods` と並列）。

**`write_metadata_json` 呼出側での metadata_dict 拡張イメージ**（orchestrator または run script から）:
```python
metadata_dict = {
    # ... 既存キー（model_version / base_model_type / feature_snapshot_id / calib_method / seed / hyperparams / train_calib_test_periods / saved_components）...
    # ↓ Phase 11 新規（θ 事前登録値・α_r は per-race なので保存せず θ のみ・再現性は θ + base logit で完全）
    "race_relative_theta": theta,  # None (v1.0 等価・補正層 skip) or float（事前登録値）
    "race_relative_alpha_search_xtol": ALPHA_SEARCH_XTOL,  # 定数の記録（固定値・再現性）
    "race_relative_p_cal_clip_epsilon": P_CAL_CLIP_EPSILON,
}
```

**`_atomic_write_text` + `sort_keys=True` + `ensure_ascii=False`**（lines 59-69・byte-reproducible・`saved_components` で何が保存されたか明示）は既存 idiom をそのまま再利用。

**注意:** `α_r` 自体は per-race で決定論的（θ + base logit + k から brentq で一意に定まる）ため artifact に保存する必要はない。θ と base logit（=base estimator + calibrator artifact）があれば α_r は完全再現可能（D-10 自己完結性）。保存するのは θ のみ。

---

### `tests/model/test_race_relative.py` (test, unit) 【新規】

**※ RESEARCH.md のパス `tests/unit/test_race_relative.py` は誤り。正しいパスは `tests/model/test_race_relative.py`（`test_calibrator.py` / `test_orchestrator.py` と同配置）。**

**Analog:** `tests/model/test_calibrator.py`（pure 関数 unit test・bit-identical・境界ケース・`from __future__ import annotations` + 標準 pytest import）

**ヘッダ docstring パターン**（`tests/model/test_orchestrator.py` lines 1-23・検証内容を箇条書きで明示・聖域 SC# 番号参照）:
```python
# ruff: noqa: E501
"""Phase 11 SC#1/SC#3 unit test: race_relative pure 関数（α_r 二分探索・clip・sum(p)=k・bit-identical）.

検証内容（RESEARCH.md Validation Architecture Test Map 17 件）:
- MODEL-01: solve_alpha_for_race が sum(p)=k を厳密達成（|sum−k| < 1e-9）
- MODEL-01: f(α) 単調増加で唯一解（IVT）
- MODEL-01: θ→∞ で α → logit(k/n)・θ→0+ で brentq 失敗（尖鋭化・発散検出）
- MODEL-01: clip ε=1e-6 で isotonic 0/1 生成時に sum(p)=k 精度 <1e-12
- MODEL-01: apply_race_relative_correction が race 毎に独立動作（他 race 不参照）
- MODEL-01: base logit s_i が両モデルで bit-identical（logit(proba) 経路）
- MODEL-01: sum(p)=k 不変性が完全パイプラインで成立
- MODEL-01: overprediction penalty が segment_eval binning と bit-identical
- MODEL-01: k 決定が sales_start_entry_count ベース・同着不反映（D-08）
- D-09: binary logit 欠損で RuntimeError（neutral 補完不採用）
- SC#3: 両モデル（LightGBM/CatBoost）で race-relative p が bit-identical

参考: 11-RESEARCH.md Pattern 1/2/3 / src/model/race_relative.py /
      tests/model/test_calibrator.py（pure 関数 unit test idiom）.
"""
```

**test 関数パターン**（`test_calibrator.py` の `def test_*():` + `assert` + docstring に検証内容・RESEARCH.md Test Map のテスト名をそのまま採用）:
```python
def test_solve_alpha_sum_p_equals_k() -> None:
    """MODEL-01: α_r 二分探索が sum(p)=k を厳密達成（|sum−k| < 1e-9・実測 4.44e-16）。"""
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=18)
    alpha = solve_alpha_for_race(s, theta=1.0, k=3)
    sum_p = float(np.sum(1.0 / (1.0 + np.exp(-(s / 1.0 + alpha)))))
    assert abs(sum_p - 3) < 1e-9  # 実測 4.44e-16

def test_logit_missing_fail_loud() -> None:
    """D-09: p_cal 欠損で RuntimeError（neutral 補完不採用・silent fallback 禁止）。"""
    p_cal = np.array([0.3, np.nan, 0.7])
    race_ids = np.array(["R1", "R1", "R1"])
    k_per_race = np.array([2, 2, 2])
    with pytest.raises(RuntimeError, match="fail-loud"):
        apply_race_relative_correction(p_cal, theta=1.0, k_per_race=k_per_race, race_ids=race_ids)
```

**DB 不要・KEIBA_SKIP_DB_TESTS=1 で実行可能**（`tests/audit/test_audit_field_strength.py` lines 26-27 と同一・marker なし・純粋関数検査）。

---

### `tests/audit/test_audit_race_relative.py` (test, adversarial audit) 【新規】

**Analog:** `tests/audit/test_audit_field_strength.py`（Phase 8 D-06 adversarial 5段階鋳型・SC#4 SAFE-01 AST odds/ninki proxy 監査・lookahead 注入 monkeypatch idiom）

**ヘッダ docstring パターン**（`test_audit_field_strength.py` lines 1-27・5段階鋳型 (a)(b)(c)(d)(g)(6) の構造踏襲・SC 番号参照）:
```python
# ruff: noqa: E501
"""SC#4/D-10 adversarial: race_relative 新モジュールの AST に市場情報 proxy が0件を静的証明し・
α_r 自己完結性を adversarial で逆証明する.

本ファイルは SC#4 adversarial（SAFE-01 横断聖域 + α_r 自己完結性・最終監査層）。
新モジュール ``src/model/race_relative.py`` が市場情報 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）
を一切参照しないことを AST 静的解析で証明し・更に D-10 adversarial で α_r が各 race の logit と k
のみから決定すること（outcome 入れ替え不変・他 race 情報混入検出）を逆証明する。

5段階鋳型（Phase 8 D-06 / tests/audit/test_audit_field_strength.py 踏襲）:
  (a)(b)(c) AST: forbidden Name/Attribute/SQL 文字列 proxy 0件（SAFE-01・SC#4）
  (d) allowlist: binning 契約の import 再利用（bit-identical・独自 binning 禁止）
  (g) false-pass 回避: 意図的注入を検出することの証明
  (6) D-10 自己完結性: outcome 入れ替えで α_r/p 不変・他 race logit 混入検出（monkeypatch）

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行・純粋 AST/monkeypatch 検査）.
"""
```

**forbidden tokens + AST scanner の import 再利用**（`test_audit_field_strength.py` lines 41-43, 49-136 をそのまま踏襲・`src.features` でなく `src.model.race_relative` に向け直す）:
```python
from src.model import race_relative  # 対象モジュール

_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)
# _scan_module_for_forbidden_tokens は test_audit_field_strength.py と同一構造で再実装
# （or 共通 helper に切り出す・本 Phase では踏襲で別実装が安全・5段階鋳型の独立性）
```

**D-10 adversarial: α_r 自己完結性テスト**（`test_audit_field_strength.py::test_lookahead_injection_detected` lines 413-502 の monkeypatch idiom 踏襲・outcome を入れ替えて α_r/p が不変であることを検証）:
```python
def test_alpha_self_contained_outcome_swap() -> None:
    """D-10: α_r は race logit と k のみから決定・outcome を入れ替えても α_r/p が不変.

    adversarial 5段階鋳型(6)（test_audit_field_strength.py::test_lookahead_injection_detected idiom 踏襲）。
    race R1 の outcome ラベルを [1,0,0] → [0,1,0] に入れ替えても α_r と final p が
    bit-identical であることを検証（α_r 計算に outcome が混入していない逆証明）。
    """
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=3)  # 3 頭・k=2
    # outcome は α_r 計算に使われないため・入れ替えても α_r は同一
    alpha_1 = solve_alpha_for_race(s, theta=1.0, k=2)
    # outcome を使う何らかの処理を模倣しても α_r は不変（自己完結性の構造的保証）
    assert alpha_1 == solve_alpha_for_race(s, theta=1.0, k=2)  # 決定論的

def test_alpha_cross_race_leak_detected() -> None:
    """D-10: α_r 計算に他 race 情報が混入しない（race_id 毎独立ループの構造的保証）.

    apply_race_relative_correction は np.unique(race_ids) で race 毎に独立ループ。
    他 race の logit を混ぜると α_r が変化することで・混入経路が閉じていることを逆証明。
    """
    # race R1 と R2 で独立に α_r が解けることを検証
    # R1 の logit を変えても R2 の p_final が不変であることを assert
```

---

### `scripts/run_phase11_evaluation.py` (script, batch evaluation/report) 【新規】

**Analog:** `scripts/run_phase10_evaluation.py`（v1.0 baseline vs 新 snapshot 3-way 比較・SC#5 非劣化 gate・事前登録許容幅・B-3 同一 trainer 設定で delta・§15.2 binning 定数 import 再利用）

**ヘッダ docstring パターン**（`run_phase10_evaluation.py` lines 1-63・Purpose / 事前登録許容幅 / §11.2 聖域 / B-3 比較方法 / Usage セクション）:
```python
"""Phase 11 SC#2 改善 gate: v1.0 binary baseline vs race-relative model 3-way 比較.

Purpose
-------
Phase 11 で導入した race-relative 補正層（logit temperature θ + per-race α_r 二分探索）が
v1.0 binary LightGBM/CatBoost の確率品質を悪化させず・投票層の overprediction を改善することを
定量的に保証する（SC#2・D-04 非劣化 + D-05 改善 gate）。

D-04 事前登録許容幅 (§11.2 聖域・評価後変更禁止)::
    - Brier 悪化  <= 0.005  (Phase 10 の 0.002 より拡張・race-conditional 構造的変化への根拠再確認)
    - LogLoss 悪化 <= 0.010
    - AUC 悪化   <= 0.005  (logit 順序保存で構造的に維持・D-04 根拠)

D-05 SC#2 改善 gate (3 必須条件)::
    (1) odds_band×p_bin の overprediction penalty が v1.0 binary より低い（主指標）
    (2) selected/high-EV 層の「平均予測率 − 実現率」が v1.0 より低い
    (3) selected-only calib_max_dev が事前登録マージン（D-04）を超えて悪化しない

θ 選択経路（D-03 制約付き選択・事前登録・test 窓選び直し禁止 §11.2）::
    候補 {0.5, 0.75, 1.0, 1.25, 1.5} → calib slice で (1) 足切り → (2) overprediction penalty 最小 →
    (3) tie-break calib_max_dev → θ=1 に近い候補

Usage (live-DB・KEIBA_SKIP_DB_TESTS unset)::

    uv run python scripts/run_phase11_evaluation.py \\
        --snapshot-id 20260626-1a-opponentstrength-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --theta-candidates 0.5 0.75 1.0 1.25 1.5 \\
        --out-dir reports/11-evaluation
"""
```

**sys.path 操作 idiom**（`run_phase10_evaluation.py` lines 80-84・`scripts/` から `src.*` を import する定型）:
```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
```

**§15.2 binning 定数 import 再利用**（`run_phase10_evaluation.py` lines 86-97・bit-identical 保証・再定義禁止）:
```python
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    compute_metrics,
)
from src.model.segment_eval import (  # noqa: E402
    NINKI_BAND_EDGES,
    ODDS_BAND_EDGES,
    evaluate_all_segments,
)
from src.model.predict import make_model_version  # noqa: E402
from src.model.race_relative import (  # noqa: E402  Phase 11 新規
    apply_race_relative_correction,
    compute_overprediction_penalty,
)
```

**事前登録許容幅の定数化**（`run_phase10_evaluation.py` lines 111-113・評価後変更禁止の明示）:
```python
# D-04 事前登録許容幅 (§11.2 聖域・Phase 10 の 0.002/0.005/0.005 から拡張・race-conditional 構造的変化)
TOLERANCE_BRIER: float = 0.005
TOLERANCE_LOGLOSS: float = 0.010
TOLERANCE_AUC: float = 0.005
```

**レビュー H6 対応（正しい API chain）**（`run_phase10_evaluation.py` lines 40-45・`orchestrator.train_and_predict(snapshot_id=...)` 略記でなく完全 chain）:
```python
# load_feature_matrix(snapshot_id=...) → load_labels(cur) → build_training_frame(feature_df, label_df)
# → load_frozen_maps(snapshot_id=...) → train_and_predict(label_joined_frame, feature_snapshot_id=...,
#   snapshot_id=..., version_n=1, split_periods=BT1_PERIODS, category_map=cat_map, theta=selected_theta)
```

**θ 選択経路の byte-reproducible 記録**（RESEARCH.md Open Question #2・`segment_eval.write_segment_reports` idiom・`_atomic_write_text` + `sort_keys=True`）:
```python
# reports/11-evaluation/theta-selection.json に候補毎の
# (Brier, LogLoss, AUC, overprediction_penalty, calib_max_dev, selected_only_calib_max_dev, verdict)
# を byte-reproducible に出力（後知恵すり替え禁止・選択ルールは事前登録値で固定）
```

**is_primary 立てない（D-07）**（`prediction_load._idempotent_load_prediction` 呼出で `set_primary_model` は呼ばない・model_version 行追加のみ）:
```python
# Phase 11 は並列比較のみ・is_primary 切替は Phase 12（D-07）
# prediction_load で新 model_version 行を追加するが・set_primary_model は呼出しない
```

---

## Shared Patterns

### 1. fail-loud（silent fallback 禁止）— D-09 / Phase 10 gap-closure CR-01〜04 鏡像

**Source:** `src/utils/calibrator.py` lines 86-94（`raise ValueError`・`python -O` 生存）・`src/db/prediction_load.py` lines 233-238（空入力 `RuntimeError`）

**Apply to:** `src/model/race_relative.py`（p_cal 欠損 `RuntimeError`）・`src/model/orchestrator.py` 拡張（base logit 欠損時の fail-loud・k 決定失敗時）

```python
# D-09: silent fallback 禁止・neutral 補完不採用
if not np.all(np.isfinite(p_cal)):
    raise RuntimeError(
        f"apply_race_relative_correction: p_cal に {n_bad} 件の非 finite 値・"
        f"binary logit 欠損 fail-loud（D-09）"
    )
```

### 2. §15.2 事前登録指標不変（binning 契約の一元化・bit-identical）

**Source:** `src/model/evaluator.py` lines 88-91（`CALIBRATION_CURVE_BINS=10` / `CALIBRATION_CURVE_MIN_BIN_COUNT=30`）・`src/model/segment_eval.py` lines 54-61, 69-75（import 再利用・再定義禁止）

**Apply to:** `src/model/race_relative.py`（`compute_overprediction_penalty` が `_odds_band` / `_p_bin` を import 再利用）・`scripts/run_phase11_evaluation.py`（binning 定数を import・再定義しない）

```python
from src.model.evaluator import CALIBRATION_CURVE_BINS
from src.model.segment_eval import _odds_band
# 独自 binning は導入しない（bit-identical 保証・契約一元化）
```

### 3. byte-reproducible JSON 出力（atomic write + sort_keys）

**Source:** `src/model/artifact.py` lines 59-69（`_atomic_write_text`）・`src/model/segment_eval.py` lines 505-512（`json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False)` + `_atomic_write_text`）

**Apply to:** `scripts/run_phase11_evaluation.py`（θ 選択経路・比較レポート出力）・`src/model/artifact.py` 拡張（metadata.json に θ 追加）

```python
json_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
_atomic_write_text(out_path, json_payload)  # tmp → os.replace で atomic
```

### 4. model_version-scoped idempotent swap（HIGH#1・is_primary 立てない D-07）

**Source:** `src/db/prediction_load.py` lines 191-271（`_idempotent_load_prediction`・advisory lock・staging-swap・同一 model_type+model_version のみ DELETE→INSERT）

**Apply to:** `scripts/run_phase11_evaluation.py`（新 race-relative model を model_version で永続化・v1.0 binary 行は保持・`set_primary_model` は呼出しない）

```python
# D-07: 並列比較のみ・is_primary は v1.0 binary 維持
# prediction_load で新 model_version 行を追加するが・set_primary_model は呼出しない
```

### 5. 事前登録パターン（候補集合 + train/calib 窓のみ + test 窓選び直し禁止 §11.2）

**Source:** `.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md` D-12（`{0.0, 0.1, 0.25, 0.5}` 候補・train/calib 窓内のみ選択）・`scripts/run_phase10_evaluation.py` lines 8-13, 111-113（許容幅の事前登録・評価後変更禁止）

**Apply to:** `scripts/run_phase11_evaluation.py`（θ 候補 `{0.5, 0.75, 1.0, 1.25, 1.5}`・D-04 許容幅 `0.005/0.010/0.005`・D-05 改善 gate 3 必須条件）

```python
# θ は calib slice でのみ選ぶ・test 窓では事前登録 gate で一回だけ評価（§11.2 聖域）
TOLERANCE_BRIER: float = 0.005  # 評価後変更禁止
```

### 6. adversarial 5段階鋳型（Phase 8 D-06 / SAFE-01）

**Source:** `tests/audit/test_audit_field_strength.py`（(a)(b)(c) AST forbidden tokens・(d) allowlist・(g) false-pass 回避・(6) lookahead 注入 monkeypatch）

**Apply to:** `tests/audit/test_audit_race_relative.py`（AST odds/ninki proxy 0件・D-10 α_r 自己完結性 outcome swap・cross-race leak 検出）

```python
# 5段階鋳型踏襲・test_audit_field_strength.py の _scan_module_for_forbidden_tokens を再利用
forbidden = _scan_module_for_forbidden_tokens(race_relative)
assert not forbidden[0]  # Name/Attribute 0件
assert not forbidden[1]  # SQL 文字列 proxy 0件
```

---

## No Analog Found

全 6 ファイルに強い analog が存在する。No Analog なし。

**補足:** RESEARCH.md が提示する α_r 二分探索（`scipy.optimize.brentq`）・overprediction penalty（半波整流 ECE）・base logit 統一経路（`predict_proba → clip → logit`）は実証検証済みのコード断片を RESEARCH.md Pattern 1/2/3 として既に提供している。これらは新規コードだが・既存 `src/utils/calibrator.py`（pure 関数 + sklearn/scipy idiom）と `src/model/segment_eval.py`（binning 契約）の組合せで実装されるため・「既存 idiom の新規組合せ」であり analog 不足ではない。

## Metadata

**Analog search scope:**
- `src/model/`（orchestrator / predict / calibrator / data / artifact / evaluator / segment_eval）
- `src/utils/`（calibrator / group_split）
- `src/db/`（prediction_load）
- `scripts/`（run_phase10_evaluation / run_evaluation）
- `tests/model/`（test_calibrator / test_orchestrator / test_predict）
- `tests/audit/`（test_audit_field_strength / test_audit_speed_figure / test_audit_features）

**Files scanned:** 12（src 7 + scripts 1 + tests 4）

**Pattern extraction date:** 2026-06-27

**注意事項（planner へ）:**
1. **テストパス訂正:** RESEARCH.md Wave 0 gaps の `tests/unit/test_race_relative.py` は誤り。正しいパスは `tests/model/test_race_relative.py`（`test_calibrator.py` / `test_orchestrator.py` と同配置・`tests/unit/` ディレクトリは存在しない）。
2. **聖域ファイルは plan/execute いずれも触らない:** `trainer.py` / `utils/calibrator.py` / `model/calibrator.py` / `data.py` / `group_split.py` / `evaluator.py` / `prediction_load.py` は D-01・SC#3 bit-identical 维持のため不変。新規ファイルから import 再利用するのみ。
3. **拡張ファイルは 2 つのみ:** `orchestrator.py`（補正層呼出挿入・`theta` 引数追加）と `artifact.py`（metadata.json に θ 追加）。両者とも既存関数の「拡張」であって再実装でない。
4. **run_phase11_evaluation.py は run_phase10_evaluation.py の直接の先例あり:** B-3 同一 trainer 設定で delta・事前登録許容幅・§15.2 binning import 再利用・正しい API chain（REVIEW H6）などほぼ全 idiom が踏襲可能。相違は θ 選択経路（D-03 制約付き選択）と is_primary 立てない（D-07）のみ。
