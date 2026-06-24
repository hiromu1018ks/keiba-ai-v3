---
phase: 8
slug: adversarial-audit-suite
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-24
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

> Phase 8 はテストスイート統合フェーズ。「検証対象＝Phase 1-7 のリーク防止実装」「成果物＝監査テスト + 監査レポート + 再現性 smoke」。本フェーズのテスト自体の検証（注入テストが本当に fail すること・フルスイート GREEN の再現性・監査レポートの正確性）が核心。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（pyproject.toml pin） |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`（`testpaths=["tests"]`・`requires_db` marker 登録済み） |
| **Quick run command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -x -q`（DB skip・高速） |
| **Full suite command** | `uv run pytest tests/`（`KEIBA_SKIP_DB_TESTS` unset で全 `requires_db` 実行・D-04 フル GREEN 証明） |
| **Estimated runtime** | ~90-180 秒（491 テスト・live-DB 含むフル実行時） |

---

## Sampling Rate

- **After every task commit:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -x -q`（quick・DB skip）
- **After every plan wave:** `uv run pytest tests/`（full・KEIBA_SKIP_DB_TESTS unset）
- **Before `/gsd-verify-work`:** Full suite must be green（KEIBA_SKIP_DB_TESTS unset・D-04）
- **Max feedback latency:** 180 秒

---

## Per-Task Verification Map

> planner が PLAN.md を作成後、各 task（08-NN-MM）を本表に追記する。Phase 8 の task は主に `tests/audit/` 新設・`reports/08-audit` 生成・`scripts/run_reproducibility_smoke.py` 新設。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | TEST-01 | — | （planner 計画後に埋める） | unit | `uv run pytest tests/audit/ -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/audit/__init__.py` — 新規 adversarial 監査テストパッケージ
- [ ] `tests/audit/test_audit_lookahead.py` — SC#2 ケース1（lookahead 注入検出）RED stub
- [ ] `tests/audit/test_audit_payout_missing.py` — SC#2 ケース2（payout 正欠損検出）RED stub
- [ ] `tests/audit/test_audit_fold_race_id.py` — SC#2 ケース3（fold race_id 共有検出）RED stub
- [ ] `tests/audit/test_audit_ui_csv.py` — D-06（read-only 保証・スタンプ inline 検出）RED stub

*既存の `KEIBA_SKIP_DB_TESTS` skipif 機構・`requires_db` marker・conftest.py は Phase 1-7 で確立済み。新規フレームワークインストールなし。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| live-DB フル実行 GREEN 証明（KEIBA_SKIP_DB_TESTS unset） | TEST-01 / SC#1 | CI 環境なく個人開発ローカル PostgreSQL のみ・`checkpoint:human-verify` | `unset KEIBA_SKIP_DB_TESTS && uv run pytest tests/ -q` が全 GREEN（0 skipped・38+ requires_db 全実行）を人間が確認 |
| 再現性 smoke の live-DB 全量 | SC#3 | 合成データで代用可能・live-DB 全量は Phase 4 SC#4 既証明 | `uv run python scripts/run_reproducibility_smoke.py`（合成データ）が GREEN、live-DB 全量は Phase 4 実績で代用 |

*「注入テストが本当に fail すること」は自動検証可能（注入 fixture を ON にした pytest で fail を assert）—— manual ではない。*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
