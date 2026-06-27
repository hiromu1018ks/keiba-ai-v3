---
phase: 12
slug: p-lower-ev-falsification-evaluation
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-27
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Wave 0 stubs と Per-Task Verification Map は planner が 12-RESEARCH.md Validation Architecture（L566-）と PLAN.md から埋めた。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（pyproject.toml `[tool.pytest.ini_options]`・Phase 1-11 で確立済み） |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（DB 不要 unit・高速・leak-safe 論理検証） |
| **Full suite command** | `uv run pytest -q`（`KEIBA_SKIP_DB_TESTS` unset = live-DB フルスイート・SC#5 が要求） |
| **Estimated runtime** | quick ~10-30s / full suite ~1-3 min（live-DB 含む・adversarial 5段階鋳型含む） |

> **注意（memory: phase7-ui-live-db-bugs・fix-must-verify-gate-result-livedb）:** gate 判定結果の検証は live-DB フルスイート（`KEIBA_SKIP_DB_TESTS` unset）で行うこと。unit test（`KEIBA_SKIP_DB_TESTS=1`）では gate PASS/FAIL の変化を検出できない。`--fix` 後や gate 変更後は `run_phase12_evaluation.py` を live-DB で回して gate 結果が変わらないか検証。

---

## Sampling Rate

- **After every task commit:** Run `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q`（live-DB フル）
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds（quick）/ 数分（wave ごと full）

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | EV-01 / SAFE-01 | T-12-01/02/03 | compute_p_lower_conformal_shrinkage が calib slice のみ・byte-reproducible・odds proxy 排除 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_p_lower.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-01-02 | 01 | 1 | EV-01 / SAFE-01 | T-12-04/05 | prediction p_fukusho_hit_lower 列 migration・3ファイル連鎖・CHECK 制約 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/db/test_schema_p_lower.py tests/model/test_prediction_load.py tests/db/test_is_primary_flag.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-02-01 | 02 | 2 | EV-01 | T-12-06/08/10 | orchestrator L754 後 p_lower 挿入・calib slice 聖域・artifact metadata・byte-reproducible | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_orchestrator_p_lower.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-02-02 | 02 | 2 | EV-01 | T-12-07/09 | EV 層 p_col='p_fukusho_hit_lower' / p_min_base='p_lower'・SAFE-01 EV 層 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ev/test_ev_p_lower.py tests/ev/ -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-03-01 | 03 | 3 | EVAL-02 / SAFE-01 | T-12-11/12/13/15/17 | falsification clustered SE・market_implied 再校正（calib のみ）・§11.2 聖域・Holm・logit clipping | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/evaluation/test_falsification.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-03-02 | 03 | 3 | EVAL-01 / SAFE-01 | T-12-13/14/16 | evaluator WARN gate（§15.2 不変）・segment_eval binning bit-identical・slippage | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_evaluator_phase12_gate.py tests/evaluation/test_extended_metrics.py tests/model/test_evaluator*.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-04-01 | 04 | 4 | EV-01/EVAL-01/EVAL-02/SAFE-01 | T-12-18/19/20/22/23/25 | run_phase12_evaluation.py・q_shrink calib slice・set_primary_model Call 0件・§15.2 不変・byte-reproducible・statement_timeout | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_run_phase12_evaluation.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-05-01 | 05 | 5 | SAFE-01 | T-12-26/27/28 | 対抗的監査 5段階鋳型・SAFE-01 proxy 排除 AST・falsification leakage・set_primary_model Call 0件 | adversarial audit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_p_lower_falsification.py tests/audit/test_audit_field_strength.py tests/audit/test_audit_race_relative.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 12-05-02 | 05 | 5 | SAFE-01/EVAL-01/EVAL-02 | T-12-29/30/31 | live-DB フルスイート SC#5 GREEN・run_phase12_evaluation.py byte-reproducible スモーク・§15.2 regression・switch_recommendation | integration (live-DB) + smoke | `uv run pytest tests/ -ra`（KEIBA_SKIP_DB_TESTS unset）+ `uv run python scripts/run_phase12_evaluation.py` x2 で bit-identical | ✅（Plan 04 で生成） | ⬜ checkpoint:human-verify |
| 12-05-03 | 05 | 5 | EV-01/EVAL-01/EVAL-02/SAFE-01 | — | 12-VERIFICATION.md・SC#1-5 結果・聖域遵守・honest 記録 | doc | `test -f 12-VERIFICATION.md && grep -cE 'SC#1\|SC#2\|SC#3\|SC#4\|SC#5\|EV-01\|EVAL-01\|EVAL-02\|SAFE-01\|§11.2\|§15.2\|§19.1\|D-10\|switch_recommendation'` | ❌ W0→✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

各 plan の最初の task が `<behavior>` block（tdd="true"）でテスト期待を明示し・実装前に test file を作成する（RED→GREEN→REFACTOR）。下記 test file が Wave 1-5 の各 task で作成される（planner は事前 stub でなく・各 task 内で tdd サイクル実施）。

- [x] `tests/model/test_p_lower.py` — Plan 01 Task 1 で作成・EV-01 (SC#1) p_lower 計算・calib slice 聖域・byte-reproducible
- [x] `tests/db/test_schema_p_lower.py` — Plan 01 Task 2 で作成・EV-01 p_lower 列 migration idempotent・3ファイル連鎖
- [x] `tests/model/test_orchestrator_p_lower.py` — Plan 02 Task 1 で作成・EV-01 orchestrator 挿入・calib slice 聖域
- [x] `tests/ev/test_ev_p_lower.py` — Plan 02 Task 2 で作成・EV-01 EV_lower=p_lower×odds_lower・p_min_base
- [x] `tests/evaluation/test_falsification.py` — Plan 03 Task 1 で作成・EVAL-02 (SC#3) falsification clustered SE
- [x] `tests/evaluation/test_extended_metrics.py` — Plan 03 Task 2 で作成・EVAL-01 (SC#2) EV-decile/disagreement/slippage
- [x] `tests/model/test_evaluator_phase12_gate.py` — Plan 03 Task 2 で作成・SC#4 WARN gate・§15.2 不変
- [x] `tests/test_run_phase12_evaluation.py` — Plan 04 Task 1 で作成・q_shrink・falsification・switch_recommendation・set_primary_model Call 0件
- [x] `tests/audit/test_audit_p_lower_falsification.py` — Plan 05 Task 1 で作成・SAFE-01 proxy 排除 AST + falsification leakage + set_primary_model Call 0件
- [x] statsmodels 0.14.6 — Plan 01 Task 1 で `uv add "statsmodels>=0.14.6"`・pyproject.toml + uv.lock へ反映
- [x] `scripts/run_phase12_evaluation.py` ひな形 — Plan 04 Task 1 で作成・run_phase11_evaluation.py 構造踏襲

*既存 adversarial 5段階鋳型（`tests/audit/test_audit_race_relative.py` L11-27）を踏襲して拡張（test_audit_p_lower_falsification.py）。既存 tests/audit/test_audit_field_strength.py は SAFE-01 proxy 排除で Phase 12 拡張後も regression 検証。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| reports/12-evaluation/switch-recommendation の人間確認・is_primary 切替判断（D-10） | SAFE-01 / EVAL-01 / EVAL-02 | switch_recommendation は判断材料で実行でない・Phase 12 では DB 自動変更しない・人間承認の別アクション | reports/12-evaluation/switch-recommendation.{md,json} を読み・switch/hold/reject と統合材料（SC#4 gate + p_lower EV 比較 + falsification verdict）を確認・is_primary 切替は別アクション |
| live-DB フルスイート SC#5 GREEN と byte-reproducible スモーク | SAFE-01 / §19.1 | unit test（KEIBA_SKIP_DB_TESTS=1）では gate PASS/FAIL 変化検出不可・live-DB 必須（memory: fix-must-verify-gate-result-livedb・phase7-ui-live-db-bugs） | `uv run pytest tests/ -ra`（KEIBA_SKIP_DB_TESTS unset）+ `uv run python scripts/run_phase12_evaluation.py` x2 で reports/12-evaluation/*.json bit-identical 確認 |
| owner/admin 権限で run_apply_schema.py 実行（PREDICTION_ADD_P_LOWER_SQL） | EV-01 | ALTER TABLE は owner/admin 権限必要・etl ロールで InsufficientPrivilege（memory: migration-privilege-admin-required） | `uv run python scripts/run_apply_schema.py` を owner/admin ロールで実行・psql で prediction.fukusho_prediction の p_fukusho_hit_lower 列と prediction_p_lower_range CHECK 制約を確認 |

*基本方針: Phase 12 の検証（p_lower byte-reproducible・falsification 回帰・SC#4 gate・対抗的監査 GREEN・再現性スモーク）は全て自動化可能。手動は人間承認の is_primary 切替（D-10・本 Phase では実行しない・switch_recommendation のみ）と・owner/admin 権限の migration 実行（run_apply_schema.py）と・live-DB での gate 結果確認。*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（各 plan task 内で tdd サイクルで test file 作成）
- [x] No watch-mode flags
- [x] Feedback latency < 30s（quick）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready（planner 記載・実行時に verify）
