---
phase: 11-race-relative-probability-model
plan: 04
subsystem: model
tags: [model, evaluation, adversarial, audit, race-relative, wave3, model-01, safe-01, d-03, d-04, d-05, d-07, d-10, sc2, sc4]

# Dependency graph
requires:
  - "11-01 Wave 0 race_relative.py stub + test 契約（事前登録定数）"
  - "11-02 Wave 1 race_relative.py 3 公開関数実装（solve_alpha_for_race / apply_race_relative_correction / compute_overprediction_penalty）"
  - "11-03 Wave 2 orchestrator.train_and_predict の theta + score_split 拡張（score_split='calib' の構造的聖域ブロック）"
  - "scripts/run_phase10_evaluation.py（事前登録許容幅・B-3 delta・binning import 再利用・API chain・statement_timeout idiom）"
provides:
  - "tests/audit/test_audit_race_relative.py 4テスト GREEN（D-10 adversarial 強化: inspect.signature 検証 + cross-race leak 検出力証明）"
  - "scripts/run_phase11_evaluation.py（v1.0 binary vs race-relative 3-way 比較・SC#2 gate・θ 選択経路 calib slice のみ・theta-selection.json 事前書き出し）"
  - "D-04 事前登録許容幅（Brier≤0.005 / LogLoss≤0.010 / AUC≤0.005）の定数化・§11.2 聖域"
  - "D-05 改善 gate 3条件（overprediction penalty / selected-high-EV 層 / selected-only calib_max_dev）の実装"
  - "θ 選択経路（D-03 制約付き選択）の score_split='calib' のみでの実行・test 窓 score_split='test' は θ 再選択なしで一回だけ評価"
affects:
  - "11-05（live-DB SC#2/SC#3/SC#5 検証・run_phase11_evaluation.py の KEIBA_SKIP_DB_TESTS unset 実行・model_version で binary と race-relative を並列保存）"
  - "Phase 12（p_lower EV + selected-only/falsification 評価後に is_primary 切替判断）"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-10 adversarial 強化: inspect.signature でシグネチャが outcome 系引数を取らないことを API seam で検証（docstring 紳士協定でない）"
    - "D-10 cross-race leak 検出力証明: 不変であることの主張が empty でないことを保証（R1 logit 変更で R1 p_final が変化することの assert）"
    - "θ 選択経路の score_split='calib' のみでの実行（§11.2 聖域の機械保証・codex HIGH#1）"
    - "theta-selection.json の test 窓評価に先立つ byte-reproducible 事前書き出し（後知恵すり替え禁止・codex HIGH#1）"
    - "D-04 事前登録許容幅の定数化（§11.2 聖域・評価後変更禁止）"
    - "D-07 AST guard: set_primary_model Call node 0件（docstring で言及しても AST check は Call node のみ判定し false positive にならない）"

key-files:
  created:
    - "scripts/run_phase11_evaluation.py"
  modified:
    - "tests/audit/test_audit_race_relative.py（D-10 adversarial 強化・未使用 pytest import 削除）"

key-decisions:
  - "test_alpha_self_contained_outcome_swap に inspect.signature 検証を追加（PLAN 11-04 action 通り・T-11-13 API seam 保証）"
  - "test_alpha_cross_race_leak_detected に R1 変更検出力証明を追加（PLAN 11-04 acceptance_criteria 通り・silent 変更でない保証）"
  - "run_phase11_evaluation.py の θ 選択経路は score_split='calib' で候補評価し test 窓は一回だけ評価（codex HIGH#1・§11.2 聖域）"
  - "theta-selection.{md,json} の事前書き出しを test 窓評価に先立って実施（後知恵すり替え禁止・byte-reproducible）"
  - "D-05 の selected 層は「p_fukusho_hit 上位 30%」と定義（Phase 12 EVAL-01 で厳密な EV-decile に移行）"
  - "compute_overprediction_penalty の market_signal は segment_eval と同一契約で odds 系外部参照（feature でない・SAFE-01）"
  - "fallback θ=1.0 は全候補が D-04 足切りで脱落した場合の安全策（gate 自体は D-04 で FAIL になる）"

patterns-established:
  - "θ 選択経路記録を test 窓評価に先立ってアーティファクト化するパターン（後知恵すり替え禁止）"
  - "AST check で primary 切替を Call node 0件で保証するパターン（D-07 codex cycle-2 LOW）"
  - "adversarial で「不変であること」の主張が empty でないことを検出力証明で保証するパターン"

requirements-completed:
  - MODEL-01
  - SAFE-01

# Coverage metadata (#1602)
coverage:
  - id: D10a
    description: "D-10 α_r 自己完結性 (outcome swap): solve_alpha_for_race が outcome 系引数を取らないことを inspect.signature で検証 + 決定論的呼出で α_r が不変"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_race_relative.py::test_alpha_self_contained_outcome_swap (GREEN・11-04 で inspect.signature adversarial 強化)"
        status: pass
    human_judgment: false
  - id: D10b
    description: "D-10 cross-race leak 検出: R1 logit 変更で R2 p_final 不変 + R1 p_final 変更の検出力証明"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_race_relative.py::test_alpha_cross_race_leak_detected (GREEN・11-04 で検出力証明 adversarial 強化)"
        status: pass
    human_judgment: false
  - id: SC2a
    description: "D-04 非劣化 gate (Brier/LogLoss/AUC 事前登録許容幅内) + D-05 改善 gate 3条件 (overprediction / selected-high-EV / selected-only calib_max_dev)"
    requirement: "MODEL-01"
    verification:
      - kind: static
        ref: "scripts/run_phase11_evaluation.py::_evaluate_gate (TOLERANCE_BRIER=0.005 / TOLERANCE_LOGLOSS=0.010 / TOLERANCE_AUC=0.005・d04_pass AND d05_pass = gate_pass)"
        status: pass
      - kind: manual
        ref: "live-DB 実行は 11-05 で実施（KEIBA_SKIP_DB_TESTS unset）"
        status: pending
    human_judgment: false
  - id: D03a
    description: "θ 選択経路 (D-03 制約付き選択) は score_split='calib' のみで候補評価・test 窓 (score_split='test') は θ 再選択なしで一回だけ評価 (codex HIGH#1・§11.2 聖域の機械保証)"
    requirement: "SAFE-01"
    verification:
      - kind: static
        ref: "scripts/run_phase11_evaluation.py::_select_theta_on_calib (train_and_predict(theta=θ_i, score_split='calib')) / main (theta=selected_theta, score_split='test')"
        status: pass
    human_judgment: false
  - id: D03b
    description: "theta-selection.{md,json} の test 窓評価に先立つ byte-reproducible 事前書き出し (後知恵すり替え禁止・codex HIGH#1)"
    requirement: "SAFE-01"
    verification:
      - kind: static
        ref: "scripts/run_phase11_evaluation.py::_write_theta_selection_reports (eval_dir/theta-selection.{md,json}・sort_keys=True・allow_nan=False・atomic write)"
        status: pass
    human_judgment: false
  - id: D07a
    description: "D-07: set_primary_model は呼ばない (AST Call 0件・comparison のみ・Phase 12 で切替判断)"
    requirement: "MODEL-01"
    verification:
      - kind: static
        ref: "uv run python -c ast check で set_primary_model Call 0件 (docstring 言及は AST Call node 判定外・false positive なし)"
        status: pass
    human_judgment: false

# Metrics
duration: 9 min
completed: 2026-06-27
status: complete
---

# Phase 11 Plan 04: D-10 adversarial 強化 + run_phase11_evaluation.py 新規（SC#2 gate・θ 選択経路 calib slice・D-07 primary 立てない）Summary

Phase 11 Wave 3 の 2 task を実行した。(1) `tests/audit/test_audit_race_relative.py` の D-10 adversarial テスト（α_r 自己完結性・cross-race leak 検出）に・PLAN 11-04 が要求する inspect.signature による API seam 検証と・cross-race leak の検出力証明を追加して強化した（4テスト全て GREEN）。(2) `scripts/run_phase11_evaluation.py` を新規作成し・v1.0 binary (theta=None) vs race-relative model (theta=selected_theta) の 3-way 比較・D-04 非劣化 gate + D-05 改善 gate 3条件・θ 選択経路（D-03 制約付き選択・score_split="calib" のみ）・theta-selection.json の事前書き出し（後知恵すり替え禁止）・D-07 is_primary 立てない（AST Call 0件）を実装した。live-DB 実行は 11-05 で実施（本 plan はスクリプト作成 + 構文/AST/unit test 検証のみ）。

## Performance

- **Duration:** 9 min
- **Tasks:** 2
- **Files created:** 1（scripts/run_phase11_evaluation.py）
- **Files modified:** 1（tests/audit/test_audit_race_relative.py）

## Accomplishments

### Task 1: D-10 adversarial テスト強化（test_audit_race_relative.py）

- **test_alpha_self_contained_outcome_swap:** inspect.signature(race_relative.solve_alpha_for_race) で `s_logits / theta / k` の3引数のみであること・`y_true / outcome / label / y / labels / target` が含まれないことを検証（T-11-13 API seam 保証・docstring 紳士協定でない）。加えて・決定論的呼出（alpha_1 == alpha_2）と p の bit-identical 性を検証。
- **test_alpha_cross_race_leak_detected:** R1 logit 変更で R2 p_final が bit-identical であること（cross-race leak 検出）に加え・R1 logit 変更で R1 p_final が変化することを assert（検出力証明・silent 変更でない保証・PLAN 11-04 acceptance_criteria の「検出力証明」）。これにより「不変であること」の主張が empty にならないことを保証。
- test_no_odds_ninki_proxy / test_false_pass_detection_power は 11-01 から継続 GREEN（11-02 実装で odds/ninki proxy 混入なし・SC#4 bit-identical 維持）。
- **4テスト全て GREEN**（`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py -x` exit 0）。

### Task 2: run_phase11_evaluation.py 新規（SC#2 gate・θ 選択経路・D-07）

- **3-way 比較 (B-3):** baseline (theta=None・v1.0 binary) と race-relative (theta=selected_theta) を全く同一の trainer 設定 (feature_snapshot_id / hyperparams / seed / category_map / split_periods / odds_snapshot_policy / bt_split) で評価し delta を取る。
- **D-04 事前登録許容幅 (§11.2 聖域):** `TOLERANCE_BRIER=0.005 / TOLERANCE_LOGLOSS=0.010 / TOLERANCE_AUC=0.005`（Phase 10 の 0.002/0.005/0.005 から拡張・race-conditional 構造的変化への根拠再確認・後追い緩和でない）。
- **D-05 改善 gate 3条件:** (1) `compute_overprediction_penalty(rr) < baseline` (2) selected/high-EV 層（p_fukusho_hit 上位 30%）の (mean_pred − frac_pos) が rr < baseline (3) selected-only calib_max_dev が D-04 マージン内で悪化しない。
- **θ 選択経路 (D-03 制約付き選択・§11.2 聖域):** 候補 {0.5,0.75,1.0,1.25,1.5} → `train_and_predict(theta=θ_i, score_split="calib")` で候補評価 → (1) 足切り D-04 非劣化 → (2) overprediction penalty 最小 (D-05-1) → (3) tie-break selected-only calib_max_dev → θ=1 に近い候補。**score_split="calib" が X_calib のみを予測対象にするので構造的に test 窓に触れない（codex HIGH#1・§11.2 聖域の機械保証・docstring 紳士協定でない）**。
- **theta-selection.{md,json} の事前書き出し (codex HIGH#1・後知恵すり替え禁止):** θ 選択経路決定直後・test 窓評価（score_split="test"）に先立ち・候補毎の (Brier/LogLoss/AUC/overprediction_penalty/calib_max_dev/selected_only_calib_max_dev/verdict) と選択経路（足切り/選択/tie-break の各段階と残候補）を byte-reproducible に atomic write（`_sanitize_for_json` + `allow_nan=False` + `sort_keys=True`）。
- **race-relative test 評価呼出:** `train_and_predict(theta=selected_theta, score_split="test")`（11-03 拡張・model_type="lightgbm_rr"・test 窓で一回だけ評価・θ の再選択なし）。
- **§15.2 binning import 再利用 (bit-identical):** `CALIBRATION_CURVE_BINS / CALIBRATION_CURVE_MIN_BIN_COUNT / ODDS_BAND_EDGES / NINKI_BAND_EDGES` を evaluator/segment_eval から import。`compute_overprediction_penalty` は race_relative 経由で evaluator/segment_eval の binning を利用（codex HIGH#2・二重 binning 禁止）。grep で binning 再定義 0件。
- **D-07 (is_primary 立てない):** `set_primary_model` の AST Call node 0件（AST check で検証済）。本 script は comparison のみで prediction 永続化（`load_predictions` も呼ばない・AST Call 0件）。実際の model_version 行追加は 11-05 で実施。docstring で「呼出しない」ことを明記（AST check は Call node のみ判定するため docstring 言及は false positive にならない）。
- **REVIEW H6 (正しい API chain):** `load_feature_matrix(snapshot_id=...) → load_labels(cur) → build_training_frame → load_frozen_maps → train_and_predict(feature_snapshot_id=..., snapshot_id=..., version_n=1, split_periods=BT1_PERIODS, category_map=..., theta=..., score_split=...)`。
- **REVIEW H2/H7/H8:** 生 trainer API は直接呼ばない（orchestrator.train_and_predict 経由）。
- **statement_timeout='30s'** で重クエリの orphan CPU 張り付き防止（MEMORY.md subagent-db-query-statement-timeout・configure callback + cursor 内 SET の二重防衛）。
- **D-15 参考記録:** `segment_eval.evaluate_all_segments` の出力を result dict に格納（gate 判定には使わない・Phase 12 EVAL-01 先行指標）。

## Task Commits

各 task は原子的に commit された:

1. **Task 1: D-10 adversarial 強化・inspect.signature 検証 + cross-race leak 検出力証明** - `44e92f1` (test)
2. **Task 2: run_phase11_evaluation.py 新規・SC#2 gate + θ 選択経路 (calib slice) + D-07 primary 立てない** - `0981277` (feat)

## TDD Gate Compliance

Plan 11-04 frontmatter は `type: execute`（`type: tdd` でない）。Task 1 は `type="tdd" tdd="true"` だが・11-02 で既に RED→GREEN が完了している test に対する 11-04 での adversarial 強化（acceptance_criteria の要求に従う拡張）である。本 plan は単独で新規 RED→GREEN サイクルを作らないが・test 弱体化でなく test 強化（inspect.signature 検証・検出力証明の追加）であり・fake-green 禁止の精神を遵守。

## Deviations from Plan

None - plan executed exactly as written. PLAN 11-04 の `<action>` 指示をそのまま実装した。

Auto-fixed Issues（Rule 1-3 適用）:

**1. [Rule 1 - Bug/ruff] 未使用 import 削除（apply_race_relative_correction / pytest）**
- **Found during:** Task 2 verify（ruff check）
- **Issue:** scripts/run_phase11_evaluation.py で `apply_race_relative_correction` を import していたが実際には呼び出していない（orchestrator.train_and_predict 内で呼ばれる）・tests/audit/test_audit_race_relative.py の `pytest` も未使用（11-01 から存在）。
- **Fix:** 両方の未使用 import を削除。ruff をクリーンに維持（CLAUDE.md の ruff 方針）。
- **Files modified:** scripts/run_phase11_evaluation.py（import から apply_race_relative_correction 削除）/ tests/audit/test_audit_race_relative.py（import pytest 削除）
- **Commit:** 0981277

binary 本体（trainer/calibrator/data/evaluator/segment_eval/race_relative.py/orchestrator/artifact/predict）は一切変更していない（D-01 聖域遵守）。

## Verification

### Task 1 (D-10 adversarial 強化)

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py -x` → **4 passed**（exit 0）
- inspect.signature(race_relative.solve_alpha_for_race).parameters == {"s_logits", "theta", "k"} を test 内で検証（forbidden_params 混入なし・T-11-13 API seam）
- cross-race leak 検出力証明: R1 logit 変更で R1 p_final が変化することを assert（empty test でない保証）

### Task 2 (run_phase11_evaluation.py)

- `uv run python -c "import ast; ast.parse(open('scripts/run_phase11_evaluation.py').read()); print('syntax OK')"` → syntax OK ✓
- `KEIBA_SKIP_DB_TESTS=1 uv run python scripts/run_phase11_evaluation.py --help` → CLI 引数（--baseline-snapshot-id / --bt-split / --odds-snapshot-policy / --theta-candidates / --out-dir / --non-interactive）表示 ✓
- `grep -c "CALIBRATION_CURVE_BINS\s*=\s*10\|ODDS_BAND_EDGES\s*=\s*np.array" scripts/run_phase11_evaluation.py` → **0**（binning 再定義なし・import 再利用・codex HIGH#2）✓
- AST check `set_primary_model` Call 0件（D-07 codex cycle-2 LOW・docstring 言及は false positive にならない）✓
- AST check `load_predictions` Call 0件（comparison のみ・11-05 で実施）✓
- TOLERANCE_BRIER==0.005 / TOLERANCE_LOGLOSS==0.010 / TOLERANCE_AUC==0.005（D-04 事前登録・§11.2 聖域）✓
- default THETA_CANDIDATES == [0.5, 0.75, 1.0, 1.25, 1.5]（D-03 事前登録）✓
- `uv run ruff check scripts/run_phase11_evaluation.py tests/audit/test_audit_race_relative.py` → All checks passed ✓

## Known Stubs

該当なし。本 plan は evaluation script と adversarial test 強化が役割で・stub なし。run_phase11_evaluation.py の live-DB 実行は 11-05 で実施（本 plan はスクリプト作成 + 構文/AST/unit test 検証のみ・PLAN 11-04 の設計通り）。

## Threat Flags

該当なし。threat_model の T-11-13〜T-11-17 は全て acceptance_criteria で保証済み:

| Threat | Severity | Disposition | 実装箇所 |
|--------|----------|-------------|----------|
| T-11-13（α_r への test 窓 outcome 混入・critical） | critical | mitigate | inspect.signature(race_relative.solve_alpha_for_race).parameters が {s_logits, theta, k} のみであることを adversarial で検証（API seam・T-11-13） |
| T-11-14（他 race 情報混入・high） | high | mitigate | apply_race_relative_correction の race 毎独立ループ（np.unique(race_ids)）+ R1 logit 変更で R2 p_final 不変 + R1 p_final 変更の検出力証明 |
| T-11-15（θ 選び直し・test 窓への θ 漏れ・critical） | critical | mitigate | θ は score_split="calib" でのみ候補評価・test 窓 (score_split="test") は θ 再選択なしで一回だけ評価 + theta-selection.json の事前書き出し（後知恵すり替え禁止） |
| T-11-16（市場回帰・run script が odds を feature に混入・high） | high | mitigate | market_signal (odds 系外部参照) は compute_overprediction_penalty / segment_eval の evaluation 専用層でのみ使用・FEATURE_COLUMNS には混入しない（orchestrator.train_and_predict の FEATURE_COLUMNS allowlist が保証・SAFE-01） |
| T-11-17（is_primary 誤設定・Phase 12 前に EV 本番切替・high） | high | mitigate | set_primary_model を呼ばない（AST Call 0件）・comparison のみ・load_predictions も呼ばない（11-05 で実施・primary 立ては Phase 12） |

## Next Phase Readiness

- 11-05（Wave 4）は本 plan の run_phase11_evaluation.py を KEIBA_SKIP_DB_TESTS unset で live-DB 実行し・SC#2 gate (D-04 + D-05) の検証を実施。theta-selection.{md,json} の事前書き出しで後知恵すり替え禁止が機械保証される。
- 11-05 で model_version で binary（-lgb-v1）と race-relative（-lgbrr-v1）を並列保存可能（SC#5 model_version-scoped idempotent swap）。primary 立ては Phase 12。
- binary 本体・race_relative.py・orchestrator/artifact/predict は一切変更していない（D-01 聖域遵守・11-01/02/03 の資産維持）。

---
*Phase: 11-race-relative-probability-model*
*Completed: 2026-06-27*

## Self-Check: PASSED

### 作成/変更ファイルの存在確認

- FOUND: scripts/run_phase11_evaluation.py（Task 2・新規）
- FOUND: tests/audit/test_audit_race_relative.py（Task 1・D-10 adversarial 強化）

### commit の存在確認

- FOUND: 44e92f1（Task 1・D-10 adversarial 強化・inspect.signature + cross-race leak 検出力証明）
- FOUND: 0981277（Task 2・run_phase11_evaluation.py 新規・SC#2 gate + θ 選択経路 + D-07）

### verification コマンドの実行結果

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_race_relative.py -x` → 4 passed（exit 0）✓
- `uv run python -c "import ast; ast.parse(open('scripts/run_phase11_evaluation.py').read())"` → syntax OK ✓
- `KEIBA_SKIP_DB_TESTS=1 uv run python scripts/run_phase11_evaluation.py --help` → CLI 引数表示 ✓
- `grep -c "CALIBRATION_CURVE_BINS\s*=\s*10\|ODDS_BAND_EDGES\s*=\s*np.array" scripts/run_phase11_evaluation.py` == 0（binning 再定義なし）✓
- AST check `set_primary_model` Call 0件（D-07）✓
- AST check `load_predictions` Call 0件（comparison のみ）✓
- TOLERANCE 定数（0.005 / 0.010 / 0.005）の事前登録値確認 ✓
- THETA_CANDIDATES default [0.5, 0.75, 1.0, 1.25, 1.5] 確認 ✓
- `uv run ruff check scripts/run_phase11_evaluation.py tests/audit/test_audit_race_relative.py` → All checks passed ✓
- binary 本体（trainer/calibrator/data/evaluator/segment_eval/race_relative.py/orchestrator/artifact/predict）は files_modified に含まれない（D-01 聖域遵守）✓
