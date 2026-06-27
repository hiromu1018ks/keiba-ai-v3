---
phase: 12
slug: p-lower-ev-falsification-evaluation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-27
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 詳細な test map・Wave 0 stubs は planner が `12-RESEARCH.md` の「## Validation Architecture」（L566-）を元に埋める。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（pyproject.toml `[tool.pytest.ini_options]`・Phase 1-11 で確立済み） |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（DB 不要 unit・高速・leeak-safe 論理検証） |
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

> planner が PLAN.md の task ID に合わせて埋める。各 task は `<verify>` で quick command を持つこと（sampling continuity・3 task 連続で自動 verify なしを避ける）。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | EV-01 | — | {planner 埋め} | unit | `{planner 埋め}` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `{tests/...}` — p_lower / falsification / SAFE-01 proxy 排除 / §11.2 test 窓聖域 の stub（planner が `12-RESEARCH.md` Validation Architecture test map から具体化）
- [ ] statsmodels 0.14.6 — `uv add statsmodels==0.14.6`（clustered SE・logit 回帰・multipletests・新規依存）

*既存 adversarial 5段階鋳型（`tests/audit/test_audit_race_relative.py` L11-27）を踏襲して拡張。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| {planner 判断} | {REQ} | {reason} | {steps} |

*基本方針: Phase 12 の検証（p_lower byte-reproducible・falsification 回帰・SC#4 gate・対抗的監査 GREEN・再現性スモーク）は全て自動化可能。手動は人間承認の is_primary 切替（D-10・本 Phase では実行しない・switch_recommendation のみ）。*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s（quick）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
