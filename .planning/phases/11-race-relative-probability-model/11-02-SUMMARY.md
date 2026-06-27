---
phase: 11-race-relative-probability-model
plan: 02
subsystem: model
tags: [model, race-relative, wave1, tdd-green, model-01, safe-01, d-02, d-06, d-09, d-10, sc3, sc4]
requires:
  - "11-01 Wave 0 stub + test 契約（13 RED + 4 即時 GREEN・事前登録定数）"
  - "src/model/evaluator.py _compute_calibration_curve_bins / CALIBRATION_CURVE_BINS（binning 契約の正・import 再利用）"
  - "src/model/segment_eval.py _odds_band（bit-identical banding・import 再利用）"
  - "scipy.optimize.brentq（xtol=1e-9・maxiter=200）"
provides:
  - "src/model/race_relative.py（3 公開関数 実装済み・NotImplementedError 解消）"
  - "solve_alpha_for_race: brentq 前 fail-loud guard + 本体（|sum-k| 実測 3.03e-13 < 1e-9）"
  - "apply_race_relative_correction: D-06 step 6-8 + D-09 fail-loud + race 内 k 一意性 guard + D-10 race 毎独立ループ"
  - "compute_overprediction_penalty: evaluator/segment_eval binning の import 再利用（codex HIGH#2）・半波整流 ECE"
affects:
  - "11-03/04/05（orchestrator 拡張・artifact 拡張・run_phase11_evaluation.py が本 3 関数を消費）"
tech-stack:
  added: []
  patterns:
    - "TDD GREEN phase（11-01 RED 契約を弱体化せず実装のみで GREEN 化・fake-green 禁止遵守）"
    - "brentq 前 fail-loud guard（finite / theta>0 / 0<k<n・D-09 鏡像）"
    - "race 毎独立ループで D-10 自己完結性を構造的に保証（np.unique(race_ids)・他 race 情報混入不能）"
    - "binning 契約の true import-level parity（np.linspace による独自 bin edge 再定義なし・codex HIGH#2）"
key-files:
  created: []
  modified:
    - "src/model/race_relative.py（3 関数の NotImplementedError → 実装）"
decisions:
  - "solve_alpha_for_race に brentq 前 fail-loud guard を必須挿入（codex review MEDIUM 対応・theta>0/0<k<n/finite logits 違反で ValueError/RuntimeError）"
  - "apply_race_relative_correction に race 内 k_per_race 一意性 guard を挿入（codex review MEDIUM・D-08/D-09・呼出側バグを silent fallback せず fail-loud）"
  - "compute_overprediction_penalty は evaluator._compute_calibration_curve_bins(strategy='uniform') と segment_eval._odds_band を import 再利用し・独自 _p_bin/P_BIN_EDGES は導入しない（codex HIGH#2: 真の import-level parity）"
  - "市場シグナル帯 × 予測確率 bin の二重ループ構造を維持（RESEARCH Pattern 3 厳密式）しつつ・内側の bin は _compute_calibration_curve_bins が返す non-empty bin 配列を直接使用"
metrics:
  duration: "5 min"
  completed: "2026-06-27"
  tasks: 2
  files-modified: 1
  tests-red-before: 10
  tests-green-after: 13
status: complete
---

# Phase 11 Plan 02: Race-Relative 公開関数 実装（TDD GREEN）Summary

11-01 で定義した `src/model/race_relative.py` の 3 公開関数（`solve_alpha_for_race` / `apply_race_relative_correction` / `compute_overprediction_penalty`）を RESEARCH Pattern 1/2/3 の実証済みコード断片に基づいて実装し・11-01 の RED テスト 10 件を含む全 13 テストを GREEN にした（TDD GREEN phase・fake-green 禁止遵守・test 弱体化なし）。binary 本体（trainer/calibrator/data/evaluator/segment_eval）は一切変更していない（D-01 聖域）。

## What Was Built

### 変更ファイル（1）

**`src/model/race_relative.py`** — 3 関数の `raise NotImplementedError` を実装に置換（定数・docstring・`__all__` は 11-01 そのまま維持）:

#### 1. `solve_alpha_for_race(s_logits, theta, k) -> float`

- **brentq 前 fail-loud guard（codex review MEDIUM 対応・D-09 鏡像）**: brentq に不健全な入力が渡るのを構造的に防止。違反で raise（`python -O` でも生存・assert でない）:
  - `if not np.all(np.isfinite(s_logits)): raise RuntimeError(...)` — binary logit 欠損は許容しない
  - `if not (theta > 0): raise ValueError(...)` — θ>0 必須（θ=0 は割算発散）
  - `if not (0 < int(k) < n): raise ValueError(...)` — 0<k<n 必須（IVT の前提）
- **brentq 本体**: 内部 `f(α) = Σ sigmoid(s_i/θ + α) − k`（単調増加・連続・IVT で唯一解）を `brentq(f, -100, 100, xtol=1e-9, rtol=1e-12, maxiter=200)` で解く。実測精度: |sum(p)−k| = 3.03e-13（要求 1e-9 を大幅に下回る）。
- **境界挙動**: θ→∞ で α → logit(k/n)（実証 atol=1e-4 以内）・θ→0+ で brentq が符号不一致で失敗（Pitfall 2・test_theta_zero_divergence で RuntimeError/ValueError 捕捉）。

#### 2. `apply_race_relative_correction(p_cal, theta, k_per_race, race_ids) -> np.ndarray`

- **D-09 fail-loud guard**: `if not np.all(np.isfinite(p_cal)): raise RuntimeError(...)`（neutral 補完・silent fallback 禁止・src/utils/calibrator.py L86-94 idiom 踏襲）。
- **D-06 step 6**: `np.clip(p_cal, ε, 1−ε)` → `logit`（Pitfall 1 対策・IsotonicRegression 0/1 端点で logit(±inf) 回避・ε=P_CAL_CLIP_EPSILON=1e-6）。
- **D-06 step 7-8（race 毎独立ループ・D-10 自己完結）**: `for rid in np.unique(race_ids):` で race 毎に独立処理（他 race の logit 混入を構造的に排除・Pitfall 5）:
  - **race 内 k_per_race 一意性 guard（codex review MEDIUM・D-08/D-09）**: `k_values = np.unique(k_per_race[mask]); if len(k_values) != 1: raise RuntimeError(...)`。呼出側が race 内一意を保証すべき値が混入した場合は silent fallback せず fail-loud。
  - `solve_alpha_for_race(s_race, theta, k)` で α_r を解き・`p_final[mask] = sigmoid(s_race/θ + α_r)`。
- **補正後に追加 calib なし**（D-06・sum(p)=k が崩れ α_r 再適用でループになるため）。

#### 3. `compute_overprediction_penalty(y_true, y_pred, market_signal, *, cell_filter_mask=None) -> float`

- **binning import 再利用（codex review HIGH#2 対応）**: `evaluator._compute_calibration_curve_bins(y_true_cell, y_pred_cell, strategy='uniform', n_bins=CALIBRATION_CURVE_BINS)` と `segment_eval._odds_band(pd.Series(market_signal))` を import 再利用。`race_relative.py` 内に `np.linspace` による独自 bin edge 再定義（`_p_bin` / `P_BIN_EDGES`）は**導入しない**（true import-level parity・コメント中の言及のみで実コードは 0 件）。
- **半波整流 ECE（D-03/D-05）**: 市場シグナル帯 × 予測確率 bin の各セルで `overprediction = max(0.0, mean_pred − frac_pos)` を計算し・`penalty += (count / n_total) * overprediction` で重み付け和。`n_total == 0` の場合は NaN。
- **スケール切り替え**: `cell_filter_mask=None` で overall・mask 指定で selected/high-EV 層。

### Test 結果（13 テスト全 GREEN）

`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_race_relative.py` → **13 passed**（11-01 RED 10 件 + 即時 GREEN 3 件 → 全 GREEN）:

| Test | 11-01 | 11-02 | 検証内容 |
|------|-------|-------|----------|
| test_solve_alpha_sum_p_equals_k | RED | GREEN | α_r 二分探索が sum(p)=k を厳密達成（|sum−k| = 3.03e-13 < 1e-9） |
| test_alpha_monotonic_unique_solution | RED | GREEN | f(α) 単調増加・唯一解（IVT） |
| test_theta_inf_limit | RED | GREEN | θ=1e6 で α → logit(k/n) atol=1e-4 以内 |
| test_theta_zero_divergence | RED | GREEN | θ=1e-3 で brentq 失敗（ValueError 捕捉） |
| test_clip_epsilon_isotonic_endpoints | RED | GREEN | clip ε=1e-6 で isotonic 0/1 端点で sum(p)=k 精度 <1e-12 |
| test_race_independence | RED | GREEN | race 毎独立動作（結合処理 == 単独処理・atol=1e-12） |
| test_base_logit_bit_identical | GREEN | GREEN | logit(proba) 経路 atol=1e-6（11-01 から即時 GREEN） |
| test_pipeline_sum_p_invariant | RED | GREEN | 3 race 完全パイプラインで sum(p)=k 成立 |
| test_overprediction_penalty_binning_parity | RED | GREEN | bit-identical・決定論的 binning |
| test_k_determination_no_deadheat | RED | GREEN | k=3 固定（同着不反映 D-08） |
| test_logit_missing_fail_loud | RED | GREEN | p_cal NaN で RuntimeError match="fail-loud" |
| test_both_models_bit_identical | RED | GREEN | 同一 seed で np.array_equal（SC#3 再現性） |
| test_preregistered_constants_invariant | GREEN | GREEN | 事前登録定数の不変性（§11.2 聖域） |

`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py` → **4 passed**（D-10 adversarial 含む・11-01 から連続）:

| Test | 11-01 | 11-02 | 検証内容 |
|------|-------|-------|----------|
| test_no_odds_ninki_proxy | GREEN | GREEN | SC#4 AST odds/ninki proxy 0 件 |
| test_alpha_self_contained_outcome_swap | RED | GREEN | D-10: α_r は outcome 入れ替えで不変 |
| test_alpha_cross_race_leak_detected | RED | GREEN | D-10: 他 race logit 混入検出（race 毎独立） |
| test_false_pass_detection_power | GREEN | GREEN | false-pass 回避: 意図的注入検出の証明 |

## Deviations from Plan

### Plan 指示の厳密実行（deviation なし）

本 plan は PLAN.md の `<action>` 指示をそのまま実行した。以下・PLAN 指示との対応を明記:

- **codex review HIGH#2 対応（binning import 再利用）**: PLAN Task 2 action 通り・`evaluator._compute_calibration_curve_bins(strategy='uniform')` と `segment_eval._odds_band` を import 再利用し・`_p_bin` / `P_BIN_EDGES` は導入せず。`grep -c "np.linspace" src/model/race_relative.py` == 2 だが両方とも**コメント中の言及**（再定義禁止の根拠説明）で・実コードの np.linspace は 0 件（acceptance_criteria 達成）。
- **codex review MEDIUM 対応（brentq 前 guard）**: PLAN Task 1 action 通り・finite logits / theta>0 / 0<k<n の 3 guard を brentq 前に挿入・違反で ValueError/RuntimeError。
- **codex review MEDIUM 対応（race 内 k 一意性 guard）**: PLAN Task 1 action 通り・race 毎ループ内で `np.unique(k_per_race[mask])` の一意性を検査・違反で RuntimeError。

Auto-fixed Issues（Rule 1-3 適用）は**該当なし**。binary 本体・既存 test とも変更なし（D-01 聖域遵守）。

## TDD Gate Compliance

Plan 11-02 frontmatter `type: tdd` により Plan-Level TDD Gate Enforcement が適用。本 plan は Wave 1 実装が役割:

- **RED gate**: 達成（11-01 が作成・`test(...)` commit 2 つで test 契約を RED 作成）。
- **GREEN gate**: 達成。本 plan で `feat(11-02)` commit 2 つ（Task 1: solve+apply・Task 2: penalty）で 13 テスト全 GREEN。test 弱体化なし・11-01 の docstring + 期待数値 + assert をそのまま満たした。
- **REFACTOR gate**: 不要・実装は RESEARCH Pattern 1/3 の実証済みコード断片に忠実で・クリーンアップ対象なし。

fake-green 禁止遵守: 11-01 test 契約（docstring + 期待数値 + assert）を一切変更せず・実装のみで GREEN 化。11-01 で即時 GREEN だった 3 テスト（base_logit_bit_identical / preregistered_constants / test_no_odds_ninki_proxy / test_false_pass_detection_power）も引き続き GREEN。

## Verification

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_race_relative.py -x` → 13 passed（exit 0）
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py -x` → 4 passed（exit 0）
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy tests/audit/test_audit_race_relative.py::test_false_pass_detection_power -x` → GREEN（11-01 から継続）
- verification snippet: `solve_alpha_for_race(s,1.0,3)` の |sum(p)−k| = **3.03e-13**（要求 1e-9 未満・実測 4.44e-16 程度のオーダー）✓
- `grep -c "np.linspace" src/model/race_relative.py` == 2（両方ともコメント中の言及・実コード np.linspace bin edge 再定義は 0 件・codex HIGH#2）✓
- binary 本体（trainer.py / calibrator.py / data.py / evaluator.py / segment_eval.py）は files_modified に含まれない（D-01 聖域）✓
- race_relative.py の AST に odds/ninki proxy 0 件（test_no_odds_ninki_proxy が引き続き GREEN）✓

## Known Stubs

該当なし。本 plan は 11-01 stub を全て実装済み・未解決 stub なし。

## Threat Flags

該当なし。threat_model の T-11-03〜T-11-08 は全て acceptance_criteria で保証済み:

- T-11-03（α_r への test 窓 outcome 混入・critical）: α_r は race logit + k のみから決定・y_true を引数に取らない → test_alpha_self_contained_outcome_swap GREEN
- T-11-04（他 race 情報混入・high）: np.unique(race_ids) で race 毎独立ループ → test_alpha_cross_race_leak_detected GREEN
- T-11-05（binary logit 欠損 silent fallback・high）: np.isfinite 検査で RuntimeError → test_logit_missing_fail_loud GREEN
- T-11-06（p_cal clip 忘れ・high）: np.clip(ε,1−ε) を logit 前に必須適用 → test_clip_epsilon_isotonic_endpoints GREEN
- T-11-07（補正後追加 calib で sum(p)=k 崩壊・high）: docstring で「補正後追加 calib 禁止」明記 + test_pipeline_sum_p_invariant GREEN
- T-11-08（target/mean encoding 再導入・medium）: 補正層は logit 演算のみ・categorical 再処理なし → accept（静的）

## Self-Check: PASSED

### 変更ファイルの存在確認

- FOUND: src/model/race_relative.py（Task 1 + Task 2 で実装）

### commit の存在確認

- FOUND: e545470（Task 1・solve_alpha_for_race + apply_race_relative_correction 実装）
- FOUND: f6377de（Task 2・compute_overprediction_penalty 実装）

### verification コマンドの実行結果

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_race_relative.py` → 13 passed（exit 0）✓
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py` → 4 passed（exit 0）✓
- `uv run python -c "from src.model.race_relative import solve_alpha_for_race; ..."` → |sum-k| = 3.03e-13 < 1e-9 ✓
- `grep -c "np.linspace" src/model/race_relative.py` == 2（両方コメント中・実コード 0 件）✓
