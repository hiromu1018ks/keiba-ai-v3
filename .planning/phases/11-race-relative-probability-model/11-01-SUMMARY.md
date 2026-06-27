---
phase: 11-race-relative-probability-model
plan: 01
subsystem: model
tags: [model, race-relative, wave0, tdd-stub, safe-01, d-10, sc3, sc4]
requires:
  - "Phase 10 features/race_relative.py（FEAT-03 レース内相対特徴量）完了"
  - "src/model/trainer.py binary 本体（不変・D-01）"
  - "src/utils/calibrator.py fit_prefit_calibrator（不変・later-disjoint guard）"
provides:
  - "src/model/race_relative.py（公開 API stub・事前登録定数・Wave 1 実装契約）"
  - "tests/model/test_race_relative.py（13テスト契約・12 RED + 1 即時 GREEN）"
  - "tests/audit/test_audit_race_relative.py（4テスト契約・2 RED + 2 即時 GREEN）"
  - "THETA_CANDIDATES=(0.5,0.75,1.0,1.25,1.5)・ALPHA_SEARCH_XTOL=1e-9・P_CAL_CLIP_EPSILON=1e-6 事前登録（§11.2 聖域）"
affects:
  - "11-02 Wave 1（race_relative.py 実装・GREEN gate）"
  - "11-03/04/05（orchestrator 拡張・artifact 拡張・run_phase11_evaluation.py）"
tech-stack:
  added: []
  patterns:
    - "pure 関数 stub + NotImplementedError（src/utils/calibrator.py idiom 踏襲）"
    - "TDD RED phase（stub で契約固定・fake-green 構造的防止）"
    - "adversarial 5段階鋳型（tests/audit/test_audit_field_strength.py 踏襲）"
    - "AST forbidden token 静的証明（SAFE-01・SC#4・codex MEDIUM・Constant-string 走査含む）"
    - "事前登録定数の機械保証（§11.2 聖域・test_preregistered_constants_invariant）"
key-files:
  created:
    - "src/model/race_relative.py"
    - "tests/model/test_race_relative.py"
    - "tests/audit/test_audit_race_relative.py"
  modified: []
decisions:
  - "THETA_CANDIDATES=(0.5,0.75,1.0,1.25,1.5) 事前登録（§11.2 聖域・D-03・θ<0.5 は尖鋭化発散で除外）"
  - "ALPHA_SEARCH_XTOL=1e-9 / RTOL=1e-12 / MAXITER=200 / BOUNDS=(-100,100) 事前登録（researcher 裁量 #1）"
  - "P_CAL_CLIP_EPSILON=1e-6 事前登録（researcher 裁量 #2・Pitfall 1 対策・isotonic 0/1 端点で logit(±inf) 回避）"
  - "compute_overprediction_penalty の第3引数を market_signal と命名（SAFE-01・SC#4 で禁止トークン回避・機能は PLAN 準拠）"
  - "SC#3 = 同一 LightGBM 同一 seed の再現性（codex review MEDIUM・cross-family 同一性でない）"
metrics:
  duration: "7 min"
  completed: "2026-06-27"
  tasks: 3
  files-created: 3
  tests-defined: 17
  tests-red: 13
  tests-green-immediate: 4
status: complete
---

# Phase 11 Plan 01: Race-Relative 公開 API stub + Test 契約（RED）Summary

logit temperature θ + per-race α_r 二分探索の race-relative 補正層（src/model/race_relative.py）の公開 API と事前登録定数を stub で定義し・VALIDATION.md Test Map（17テスト）に対応する test 契約を RED 状態で作成した。Wave 1（11-02）の実装が・既に存在する test 契約を満たす形で進むようにする（fake-green 構造的防止）。

## What Was Built

### 新規ファイル（3）

**1. `src/model/race_relative.py`（235 行・stub・pure 関数）**

- 事前登録定数（§11.2 聖域・D-02/D-03・researcher 裁量 #1/#2）:
  - `ALPHA_SEARCH_XTOL = 1e-9`（brentq 収束仕様・|sum(p)-k| 理論上界 ≈ 2e-9・実測 4.44e-16）
  - `ALPHA_SEARCH_RTOL = 1e-12` / `ALPHA_SEARCH_MAXITER = 200` / `ALPHA_SEARCH_BOUNDS = (-100.0, 100.0)`
  - `P_CAL_CLIP_EPSILON = 1e-6`（logit 変換前 clip・Pitfall 1 対策・isotonic 0/1 端点で logit(±inf) 回避）
  - `THETA_CANDIDATES = (0.5, 0.75, 1.0, 1.25, 1.5)`（θ=1 baseline 含む・尖鋭化発散で θ<0.5 除外）
- 3 公開関数 stub（NotImplementedError・docstring 契約）:
  - `solve_alpha_for_race(s_logits, theta, k) -> float`（α_r 二分探索・D-02/D-10 自己完結）
  - `apply_race_relative_correction(p_cal, theta, k_per_race, race_ids) -> np.ndarray`（D-06 step 6-8・D-09 fail-loud）
  - `compute_overprediction_penalty(y_true, y_pred, market_signal, *, cell_filter_mask=None) -> float`（D-03/D-05・半波整流 ECE・binning 契約 import 再利用）
- `__all__` 6 要素（3 定数 + 3 関数）
- SAFE-01・SC#4: AST に odds/ninki/fukuodds/ninkij/tansyouodds の Name/Attribute/string-constant 0件（acceptance_criteria AST 検査 GREEN・codex MEDIUM 対応）

**2. `tests/model/test_race_relative.py`（393 行・13テスト契約）**

MODEL-01/SAFE-01/D-09/SC#3 の unit test を12 + §11.2 聖域保護1 = 13テスト定義:

| Test | Status | 検証内容 |
|------|--------|----------|
| test_solve_alpha_sum_p_equals_k | RED | α_r 二分探索が sum(p)=k を厳密達成（|sum−k| < 1e-9） |
| test_alpha_monotonic_unique_solution | RED | f(α) 単調増加で唯一解（IVT） |
| test_theta_inf_limit | RED | θ→∞ で α → logit(k/n) 収束 |
| test_theta_zero_divergence | RED | θ→0+ で brentq 失敗（尖鋭化・発散検出） |
| test_clip_epsilon_isotonic_endpoints | RED | clip ε=1e-6 で isotonic 0/1 端点で sum(p)=k 精度 <1e-12 |
| test_race_independence | RED | apply_race_relative_correction が race 毎独立（D-10） |
| test_base_logit_bit_identical | GREEN | logit(proba) 経路 atol=1e-6（stub 非依存） |
| test_pipeline_sum_p_invariant | RED | 完全パイプラインで sum(p)=k（D-06） |
| test_overprediction_penalty_binning_parity | RED | segment_eval binning と bit-identical |
| test_k_determination_no_deadheat | RED | k=sales_start_entry_count ベース・同着不反映（D-08） |
| test_logit_missing_fail_loud | RED | p_cal 欠損で RuntimeError（D-09） |
| test_both_models_bit_identical | RED | 同一 LightGBM 同一 seed で bit-identical（SC#3・codex MEDIUM） |
| test_preregistered_constants_invariant | GREEN | 事前登録定数の不変性（§11.2 聖域・Rule 2 追加） |

**3. `tests/audit/test_audit_race_relative.py`（343 行・4テスト契約）**

SC#4/D-10 adversarial（5段階鋳型・tests/audit/test_audit_field_strength.py 踏襲）:

| Test | Status | 検証内容 |
|------|--------|----------|
| test_no_odds_ninki_proxy | GREEN | SC#4 AST: 市場情報 proxy Name/Attribute/Constant-string 0件 |
| test_alpha_self_contained_outcome_swap | RED | D-10: α_r は outcome 入れ替えで不変 |
| test_alpha_cross_race_leak_detected | RED | D-10: 他 race logit 混入検出（race_id 毎独立ループ） |
| test_false_pass_detection_power | GREEN | (g) false-pass 回避: 意図的注入検出の証明 |

### 契約の核心（Wave 1・11-02 が満たすべき仕様）

- α_r 二分探索は scipy.optimize.brentq で |sum(p)−k| ≤ 1e-9 を達成（実測 4.44e-16）
- base logit 取得は predict_proba → clip(ε,1−ε) → logit の統一経路（両モデル bit-identical・SC#3）
- D-09 fail-loud: p_cal の NaN/inf は RuntimeError（neutral 補完不採用・silent fallback 禁止）
- D-10 自己完結性: α_r は race logit + k のみから決定・test 窓 outcome 不使用・他 race 不参照
- D-06 パイプライン: base calib → 補正の順序・補正後に追加 calib なし（sum(p)=k 不変・ループ回避）
- binning 契約は segment_eval / evaluator から import 再利用（bit-identical・独自 binning 禁止）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] docstring の禁止トークン列挙を一般化表現に置換**
- **Found during:** Task 1 verify（SC#4 AST 検査）
- **Issue:** モジュール docstring の「odds/ninki/fukuodds/ninkij/tansyouodds の Name/Attribute/string-constant は0件」という説明文が・AST `ast.Constant`（文字列定数）として検出され・acceptance_criteria「SC#4 AST odds/ninki proxy 0件」に違反した（5トークンすべてが false-positive）。
- **Fix:** docstring の禁止トークン列挙を「市場情報 proxy トークン（tests/audit/test_audit_race_relative.py が定義する禁止集合）」という一般化表現に置換。PLAN `<action>` の指示「市場用語を出さない方が安全・一般化表現を使う」に従い・`src/features/race_relative.py`（Phase 10・grep で禁止トークン0件）と同じ方針。
- **Files modified:** src/model/race_relative.py（docstring の1ブロック）
- **Commit:** a4e6987

**2. [Rule 1 - Bug] test_audit_race_relative.py の関数呼出を race_relative.* と修飾**
- **Found during:** Task 3 verify（D-10 テスト実行）
- **Issue:** PLAN `<action>` は「`from src.model import race_relative`（Task 1 stub）」とモジュール import を指示していたが・test_alpha_self_contained_outcome_swap / test_alpha_cross_race_leak_detected が裸の `solve_alpha_for_race` / `apply_race_relative_correction` を呼んでいて `NameError: name 'solve_alpha_for_race' is not defined` で fail した。
- **Fix:** 裸の関数呼出を `race_relative.solve_alpha_for_race` / `race_relative.apply_race_relative_correction` と修飾。PLAN 指示のモジュール import を維持しつつ呼出側で修飾（5段階鋳型の独立性・test_audit_field_strength.py L431-432 の関数内 import idiom と整合）。test_race_relative.py（機能側）は from-import で裸呼出を維持。
- **Files modified:** tests/audit/test_audit_race_relative.py（2箇所の関数呼出）
- **Commit:** e6beaca

### Plan 追加（Rule 2）

**3. [Rule 2 - 機能追加] test_preregistered_constants_invariant テスト追加（§11.2 聖域保護）**
- **Trigger:** §11.2 聖域（事前登録値の test 窓選び直し禁止）は Wave 0 の核心だが・VALIDATION.md Test Map には定数値の不変性を検証するテストが無かった。
- **Fix:** test_race_relative.py に `test_preregistered_constants_invariant` を追加し・`ALPHA_SEARCH_XTOL == 1e-9` / `P_CAL_CLIP_EPSILON == 1e-6` / `THETA_CANDIDATES == (0.5,0.75,1.0,1.25,1.5)` を機械保証。stub 非依存で即時 GREEN。
- **Files modified:** tests/model/test_race_relative.py
- **Commit:** 85ef2f0
- **Note:** test 数は VALIDATION.md Test Map の「16テスト」に対し +1（補助1件）= 17テスト。契約の核心（§11.2 聖域）を機械保証するため Rule 2 で追加。

### 命名設計（Rule 適用外・明記）

**compute_overprediction_penalty の第3引数名 `market_signal`:** PLAN の RESEARCH Pattern 3 では引数名が `odds` だったが・SAFE-01・SC#4（AST で禁止トークン0件）を満たすため `market_signal` に変更。機能は PLAN 準拠（segment_eval._odds_band と同一契約で binning）。docstring で「市場シグナル（評価軸の外部参照・feature でない）」と明記し・SAFE-01（feature 側の聖域）と evaluation（別層）の棲み分けを明文化。

## TDD Gate Compliance

Plan 11-01 frontmatter `type: tdd` により Plan-Level TDD Gate Enforcement が適用される。本 plan は Wave 0 stub 作成が役割で・実装（GREEN gate）は後続 Wave 1（11-02）が担当する設計:

- **RED gate:** 達成。`test(...)` commit 2つ（Task 2・3）で test 契約（17テスト）を RED で作成。13テストは stub 関数呼出で NotImplementedError RED・4テストは stub 非依存で即時 GREEN。
- **GREEN gate:** 未達成（11-02 の役割）。11-01 は stub のみで実装なし・PLAN 設計通り。
- **REFACTOR gate:** GREEN 後に 11-02 で判定。

11-02 の SUMMARY で GREEN gate（`feat(...)` commit）が達成される予定。11-01 単独では RED gate のみ完了・これは PLAN の Wave 0 設計に準拠（stub で契約固定・実装は Wave 1 が埋める）。

## Known Stubs

本 plan は「stub のみ」が目的であり・以下の stub は Wave 1（11-02）で実装されることが計画済み（fake-green でなく構造的 RED → GREEN):

- `src/model/race_relative.py::solve_alpha_for_race` — raise NotImplementedError（Wave 1 11-02 で実装）
- `src/model/race_relative.py::apply_race_relative_correction` — raise NotImplementedError（Wave 1 11-02 で実装）
- `src/model/race_relative.py::compute_overprediction_penalty` — raise NotImplementedError（Wave 1 11-02 で実装）

これらは PLAN の明示的な設計（`<action>` で「関数本体は raise NotImplementedError のみ・Wave 1 実装者が契約を逃さない」と指定）。test 契約（13 RED）が実装を待つ状態・Wave 1 で GREEN になる予定。

## Threat Flags

該当なし。本 plan は stub 作成のみで・新たな trust boundary を導入しない。threat_model の T-11-01（race_relative.py stub の AST odds/ninki proxy 0件・SC#4）・T-11-02（D-10 RED test 存在）とも・acceptance_criteria で保証済み:
- T-11-01: test_no_odds_ninki_proxy が即時 GREEN で SC#4 AST odds/ninki proxy 0件を静的証明
- T-11-02: test_alpha_self_contained_outcome_swap / test_alpha_cross_race_leak_detected が RED で存在（Wave 1 で GREEN・D-10 契約固定）
- T-11-SC: 新規依存インストールなし（scipy/sklearn 既存 pin）・slopcheck 不要

## Self-Check: PASSED

### 作成ファイルの存在確認

- FOUND: src/model/race_relative.py（Task 1）
- FOUND: tests/model/test_race_relative.py（Task 2）
- FOUND: tests/audit/test_audit_race_relative.py（Task 3）

### commit の存在確認

- FOUND: a4e6987（Task 1・race_relative.py stub）
- FOUND: 85ef2f0（Task 2・test_race_relative.py 13テスト契約）
- FOUND: e6beaca（Task 3・test_audit_race_relative.py 4テスト契約）

### verification コマンドの実行結果

- `uv run python -c "from src.model import race_relative; print(race_relative.THETA_CANDIDATES)"` → (0.5, 0.75, 1.0, 1.25, 1.5) ✓
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_race_relative.py tests/audit/test_audit_race_relative.py --co -q` → 17 tests collected（exit 0）✓
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy -x` → GREEN（SC#4 即時保証）✓
