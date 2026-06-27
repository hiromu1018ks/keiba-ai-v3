---
phase: 12-p-lower-ev-falsification-evaluation
plan: 05
subsystem: testing
tags: [adversarial-audit, p-lower, falsification, safe-01, d10, ast, signature-audit, value-level-adversarial, checkpoint, live-db]

# Dependency graph
requires:
  - phase: 12-p-lower-ev-falsification-evaluation (Plan 01-04)
    provides: compute_p_lower_conformal_shrinkage / src/eval/falsification.py (fit_market_implied_calibrator / run_falsification_test) / scripts/run_phase12_evaluation.py / orchestrator p_lower integration
provides:
  - tests/audit/test_audit_p_lower_falsification.py (Phase 12 専用 adversarial audit・5段階鋳型・SAFE-01/§11.2/D-10 機械保証)
  - tests/audit/test_audit_field_strength.py 拡張 (Phase 12 regression・FEATURE_COLUMNS SAFE-01 層分離)
  - tests/audit/test_audit_race_relative.py 拡張 (Phase 12 regression・compute_p_lower_conformal_shrinkage 追加後 SAFE-01 維持)
affects: [12-VERIFICATION.md (Task 3), v1.1 milestone archive, Phase 13+ (model selection/is_primary 切替)]

# Tech tracking
tech-stack:
  added: []  # 純テスト拡張・新規依存なし
  patterns:
    - "5段階鋳型 adversarial audit (AST forbidden Name/Attribute + SAFE-01-ALLOW marker + signature + false-pass detection + D-10 AST)"
    - "値レベル §11.2 leak 検出 (signature-only 監査を補完・呼出側 test outcome 混入を実リーク検出)"
    - "SAFE-01 dual check (allow-list marker 許容 + feature 経路 import 検出・false red / false green 同時回避)"
    - "関数レベル AST scan (モジュール全体 scan の false-red 回避・C2-12-01-2)"

key-files:
  created:
    - tests/audit/test_audit_p_lower_falsification.py
  modified:
    - tests/audit/test_audit_field_strength.py
    - tests/audit/test_audit_race_relative.py

key-decisions:
  - "falsification.py のモジュール全体 AST scan は docstring prose 中の 'market_implied'/'1/odds' 等の言及で false-red になるため・Name/Attribute のみ strict 検査とし・docstring の SAFE-01-ALLOW marker で別途機械保証 (C-12-01-3/C-12-05-3 併用)"
  - "値レベル adversarial (C-12-05-1) は compute_p_lower_conformal_shrinkage を純粋関数として合成データで直接呼ぶ audit 独自経路とし・run_phase12_evaluation.py 側の live-DB test とは別経路で二重保証"
  - "set_primary_model AST check は import でなくファイルパスから source を直接 read する (scripts/__init__.py が無く import が fragile になるため)"
  - "test_audit_race_relative.py の関数レベル scan 拡張で C2-12-01-2 (race_relative 全体 AST scan の _odds_band false-red) を回避しつつ二重保証"

patterns-established:
  - "5段階鋳型 (test_audit_race_relative.py / test_audit_field_strength.py 踏襲) の Phase 12 拡張: AST scan + signature + 値レベル adversarial + feature 経路 import 検出の統合"
  - "D-10 set_primary_model Call 0件 AST check の scripts/__init__.py 無し環境向け idiom (ファイルパス直接読込)"

requirements-completed: [SAFE-01]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "test_audit_p_lower_falsification.py の SAFE-01 AST scan (p_lower/falsification 層 forbidden Name/Attribute 0件)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_no_odds_ninki_proxy_in_p_lower_falsification"
        status: pass
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_no_feature_construction_route_in_p_lower_falsification"
        status: pass
    human_judgment: false
  - id: D2
    description: "SAFE-01-ALLOW marker 機械保証 (fit_market_implied_calibrator/run_falsification_test docstring)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_market_implied_arg_has_allowlist"
        status: pass
    human_judgment: false
  - id: D3
    description: "§11.2 聖域 signature 検証 (compute_p_lower_conformal_shrinkage / fit_market_implied_calibrator)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_p_lower_self_contained_outcome_swap"
        status: pass
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_falsification_no_test_outcome_leak"
        status: pass
    human_judgment: false
  - id: D4
    description: "[C-12-05-1 HIGH・codex HIGH#4] 値レベル adversarial・q_shrink sha256 不変性検証 (test labels 改変で不変・calib labels 改変で変化)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_q_shrink_value_level_adversarial_invariance"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-10 set_primary_model Call 0件 AST check (scripts/run_phase12_evaluation.py)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_no_set_primary_model_call"
        status: pass
    human_judgment: false
  - id: D6
    description: "false-pass detection power (意図的注入を検出することの証明・silent test 回避)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_false_pass_detection_power"
        status: pass
    human_judgment: false
  - id: D7
    description: "[C-12-01-3/C-12-05-3] SAFE-01 dual check 統合証明 (allow-list 許容 + feature 経路検出)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_p_lower_falsification.py::test_safe01_audit_allowlist_and_feature_route_dual_check"
        status: pass
    human_judgment: false
  - id: D8
    description: "Phase 12 regression: FEATURE_COLUMNS SAFE-01 proxy 排除維持 (test_audit_field_strength.py / test_audit_race_relative.py 拡張)"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "tests/audit/test_audit_field_strength.py::test_phase12_p_lower_falsification_no_feature_columns_route"
        status: pass
      - kind: unit
        ref: "tests/audit/test_audit_race_relative.py::test_p_lower_addition_preserves_race_relative_safe01"
        status: pass
    human_judgment: false
  - id: D9
    description: "[Task 2・orchestrator checkpoint] live-DB フルスイート (KEIBA_SKIP_DB_TESTS unset) で SC#5 GREEN・run_phase12_evaluation.py 2回実行で reports/12-evaluation/*.json が bit-identical (SC#3/SC#5・FIXED_REPRODUCE_TS)"
    requirement: "SAFE-01"
    verification: []
    human_judgment: true
    rationale: "live-DB 依存の全套 pytest と byte-reproducible smoke は人間が PostgreSQL (everydb2) 接続と owner/admin 権限で実行する必要がある (memory: phase7-ui-live-db-bugs・fix-must-verify-gate-result-livedb・migration-privilege-admin-required)。KEIBA_SKIP_DB_TESTS=1 unit test では gate PASS/FAIL の変化を検出不可のため automation 不可能。"
  - id: D10
    description: "[Task 3] 12-VERIFICATION.md 作成 (SC#1-5 各結果・要件マッピング・聖域遵守・switch_recommendation 次アクション・honest 記録)"
    requirement: "SAFE-01"
    verification: []
    human_judgment: true
    rationale: "Task 2 checkpoint の実データ結果 (reports/12-evaluation/*) の転記を待って記載する必要があるため・Task 2 完了前に作成不可。"

# Metrics
duration: ~25min
completed: 2026-06-27
status: in_progress  # Task 1 done・Task 2 (live-DB checkpoint)・Task 3 (VERIFICATION.md) は orchestrator 管轄
---

# Phase 12 Plan 05: 対抗的監査 (p_lower + falsification + run_phase12_evaluation) Summary

**Phase 12 全実装に対する 5段階鋳型 adversarial audit + 値レベル §11.2 leak 検出 (C-12-05-1 HIGH) で・SAFE-01 odds proxy 排除・§11.2 test 窓聖域・D-10 is_primary 自動変更禁止を機械保証 (Task 1 完了・Task 2/3 は orchestrator checkpoint 管轄)**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-27T15:00Z
- **Completed:** 2026-06-27T15:28Z (Task 1)
- **Tasks:** 1/3 (Task 2 = checkpoint:human-verify・Task 3 = 12-VERIFICATION.md は orchestrator 管轄)
- **Files modified:** 3 (tests/audit/)

## Accomplishments
- tests/audit/test_audit_p_lower_falsification.py 新規 (9 tests): 5段階鋳型 + 値レベル adversarial + SAFE-01 dual check + D-10 set_primary_model AST check
- test_audit_field_strength.py / test_audit_race_relative.py 拡張: Phase 12 regression (p_lower/falsification 追加後も SAFE-01 聖域維持)
- [C-12-05-1 HIGH・codex HIGH#4] signature-only 監査で検出不能な呼出側 test outcome 混入を値レベルで検出 (test labels 改変で q_shrink sha256 不変・calib labels 改変で変化)
- [C-12-01-3/C-12-05-3] SAFE-01 dual check で false red (正しい evaluation 層が怒られる) と false green (feature 混入見逃し) を同時回避
- KEIBA_SKIP_DB_TESTS=1 で 3 ファイル 23 tests GREEN・broader sweep (tests/audit tests/model tests/evaluation tests/ev) 314 passed / 8 skipped・regression なし

## Task Commits

1. **Task 1: tests/audit/test_audit_p_lower_falsification.py 新規 + 拡張** - `076d914` (test)

(Task 2 は checkpoint:human-verify・Task 3 は 12-VERIFICATION.md 作成・いずれも orchestrator 管轄で未実施)

## Files Created/Modified
- `tests/audit/test_audit_p_lower_falsification.py` (新規・868行) - Phase 12 専用 adversarial audit・5段階鋳型 (AST + SAFE-01-ALLOW marker + signature + false-pass detection + D-10 AST) + 値レベル §11.2 leak 検出 + SAFE-01 dual check 統合証明
- `tests/audit/test_audit_field_strength.py` (拡張) - `test_phase12_p_lower_falsification_no_feature_columns_route` 追加・Phase 12 regression で FEATURE_COLUMNS SAFE-01 層分離維持を検証
- `tests/audit/test_audit_race_relative.py` (拡張) - `test_p_lower_addition_preserves_race_relative_safe01` 追加・compute_p_lower_conformal_shrinkage 追加後の race_relative.py SAFE-01 維持 (モジュール全体 + 関数レベル AST scan の二重保証・C2-12-01-2)

## Decisions Made
- **falsification.py モジュール全体 AST scan の取扱い**: docstring prose 中の 'market_implied' / '1/odds' 等の言及が Constant-str scan で false-red になるため・Name/Attribute のみ strict 検査とし・docstring の SAFE-01-ALLOW marker で別途機械保証 (C-12-01-3/C-12-05-3 併用)。これは test_audit_race_relative.py L189-244 の market_signal allow-list idiom の Phase 12 拡張。
- **値レベル adversarial (C-12-05-1) の経路**: run_phase12_evaluation.py 側の live-DB test とは別に・audit 独自の合成データで compute_p_lower_conformal_shrinkage を純粋関数として直接呼ぶ経路で二重保証 (live-DB 不可環境でも KEIBA_SKIP_DB_TESTS=1 で検証可能)。
- **set_primary_model AST check の import 方式**: PATTERNS L733 は `import scripts.run_phase12_evaluation as mod` だが・scripts/ は package でない (__init__.py 無し) ため import が fragile。代わりにファイルパスから source を直接 read し ast.parse する安定方式を採用。
- **run_falsification_test docstring precise language 検証**: C-12-03-1 で確定した '事前登録評価回帰' / 'pre-registered evaluation regression' の precise language が docstring に存在することを検証 (模糊表現「学習を行わない」単独使用でないことの契約保証)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] scripts/__init__.py 不在のため import-based AST check が不可**
- **Found during:** Task 1 (test_no_set_primary_model_call 実装)
- **Issue:** 12-PATTERNS.md L733 は `import scripts.run_phase12_evaluation as mod` を想定するが・scripts/ は package でなく (__init__.py 無し)・`sys.path` 操作なしでは import が fragile。
- **Fix:** ファイルパスから `Path.read_text()` で source を直接読み `ast.parse(textwrap.dedent(source))` する安定方式に変更。意味論は同一 (ast.walk で Call node を走査)。
- **Files modified:** tests/audit/test_audit_p_lower_falsification.py
- **Verification:** KEIBA_SKIP_DB_TESTS=1 で test_no_set_primary_model_call が GREEN・call_count == 0 を検証。
- **Committed in:** 076d914 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** 実装方式の安定化のみ・意味論的等価。スコープ creep なし。

## Issues Encountered
- なし・plan の 5段階鋳型指示に忠実に従い実装。

## User Setup Required

**Task 2 checkpoint:human-verify (orchestrator 管轄) で live-DB 実行が必要。** 詳細は 12-05-PLAN.md Task 2 の how-to-verify セクション参照:
- PostgreSQL (everydb2) 接続 (owner/admin 権限)
- `uv run python scripts/run_apply_schema.py` で PREDICTION_ADD_P_LOWER_SQL 適用 (Plan 01・memory: migration-privilege-admin-required)
- `KEIBA_SKIP_DB_TESTS` を unset して `uv run pytest tests/ -ra` (SC#5 GREEN・adversarial 5段階鋳型含む)
- `uv run python scripts/run_phase12_evaluation.py` を2回実行し reports/12-evaluation/*.json の bit-identical を確認 (SC#3/SC#5・FIXED_REPRODUCE_TS)
- reports/12-evaluation/switch-recommendation.{md,json} を人間が確認 (D-10・is_primary 切替は別アクション)

## Next Phase Readiness
- Task 1 (対抗的監査) 完了: Phase 12 全実装の SAFE-01 / §11.2 / D-10 聖域が KEIBA_SKIP_DB_TESTS=1 環境で機械保証された。
- Task 2 (checkpoint:human-verify) は orchestrator が live-DB で実行し SC#5 GREEN と byte-reproducible を実証する必要がある。
- Task 3 (12-VERIFICATION.md) は Task 2 の実データ結果を待って作成 (SC#1-5 各結果・要件マッピング・聖域遵守・switch_recommendation 次アクション・honest 記録)。

### Known Stubs
なし・Task 1 は純粋にテスト追加のみで stub なし。

### Threat Flags
なし・Task 1 は新しいネットワークエンドポイント・auth パス・ファイルアクセスパターン・trust boundary 境界の schema 変更を導入しない (純 AST/signature/値経路検査のみ)。

---

*Phase: 12-p-lower-ev-falsification-evaluation*
*Plan: 05*
*Task 1 Completed: 2026-06-27*
*Task 2/3: orchestrator checkpoint (live-DB) 管轄・pending*

## Self-Check: PASSED

- 全成果物ファイル存在確認: tests/audit/test_audit_p_lower_falsification.py / tests/audit/test_audit_field_strength.py / tests/audit/test_audit_race_relative.py / 12-05-SUMMARY.md 全て FOUND
- Task 1 commit (076d914) 存在確認: FOUND
- KEIBA_SKIP_DB_TESTS=1 で 3 ファイル 23 tests GREEN・broader sweep (tests/audit tests/model tests/evaluation tests/ev) 314 passed / 8 skipped (regression なし)
