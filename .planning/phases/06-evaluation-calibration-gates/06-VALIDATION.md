---
phase: 06
slug: evaluation-calibration-gates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-23
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 検証戦略の技術根拠は `06-RESEARCH.md` の `## Validation Architecture` セクションを参照（ゲート判定の正確性・指標計算の bit-identical・segment PIT 正当性・is_primary idempotency）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x（uv 管理・既存 `tests/` ディレクトリ） |
| **Config file** | `pyproject.toml`（[tool.pytest]・既存） |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~30–60 秒（純 NumPy 指標計算・DB fixture なしの unit 中心想定） |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 秒

---

## Per-Task Verification Map

> planner が PLAN.md を作成後、各 task の `<verify>` / `<acceptance_criteria>` に対応する行を埋める。Phase 6 の検証重点: (1) ゲート判定ロジックの正確性（構造的 BLOCK 正発火・曖昧基準 WARN）・(2) 指標計算の bit-identical 再現性（固定 seed・純 NumPy）・(3) segment 評価の PIT 正当性・(4) is_primary フラグ idempotency。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | TBD | 0 | EVAL-XX | — | TBD | unit | `uv run pytest tests/test_*.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_evaluator.py` — evaluator.py は Phase 4 実装だが単体テスト未存在（RESEARCH 指摘）。Phase 6 拡張（quantile/ECE/MCE・ゲート判定）のテスト基盤として Wave 0 で新設
- [ ] segment 軸データ経路のカラム存在確認テスト（`prediction.fukusho_prediction` + `label.fukusho_label` の JOIN で ninki/odds_band が揃うか・Open Question #1）
- [ ] `uv add plotly`（D-10 JSON + Plotly HTML の依存・pyproject.toml に未追加）

*既存 pytest 基盤はあるが、Phase 6 専用の evaluator テストと segment カラム確認が Wave 0 必須。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 主モデル選定（D-07 人間判断・理由記録） | EVAL-01/02 | D-04 事前登録基準（Calibration 重視）の柔軟適用・過機械化回避。planner が両モデル全指標を並列提示し人間が決定 | `reports/06-evaluation.{md,json}` の指標表を確認し、D-04 基準で LightGBM/CatBoost を選定・理由を記録 |
| 曖昧基準の WARN 判定（D-03） | EVAL-02 | 年次キャリブ反転・bin 単調性は数値併記するが PASS/FAIL は人間判定 | 年次反転数・Spearman 順位相関・bin 単調違反数を確認し人間が評価 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
