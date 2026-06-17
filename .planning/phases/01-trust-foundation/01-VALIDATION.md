---
phase: 1
slug: trust-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> ソース: `01-RESEARCH.md` §Validation Architecture / §Security Domain（実データ照合済み）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（§17.1）|
| **Config file** | `pyproject.toml` の `[tool.pytest.ini_options]`（Wave 0 で作成）|
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 秒（unit 中心。PostgreSQL 接続を含む integration は接続先 `everydb2` DB に依存）|

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/ -x -q` を実行
- **After every plan wave:** `uv run pytest tests/ -v` を実行
- **Before `/gsd-verify-work`:** Full suite が green であること。加えて品質ゲート `scripts/run_quality_report.py`（DATA-01）が `verdict: pass` を出力すること
- **Max feedback latency:** 30 秒

---

## Per-Task Verification Map

> planner が PLAN.md を作成した後、各タスクの `<acceptance_criteria>` / `<automated>` verify コマンドをこの表の該当行に転記する。タスクID（`01-NN-MM`）は plan の wave/タスク構造が確定してから採番する。

参考: RESEARCH.md §Phase Requirements → Test Map（plan のタスク分割に先立つ要件→テストの対応）

| Requirement / Success Criterion | Behavior | Test Type | Automated Command | File Exists |
|---------------------------------|----------|-----------|-------------------|-------------|
| DATA-01 | §6.4 品質ゲート実行・verdict 出力 | unit | `uv run pytest tests/test_quality_gate.py -x` | ❌ Wave 0 |
| DATA-01 | 構造的欠陥（2015以降なし / PK重複）で BLOCK | unit | `uv run pytest tests/test_quality_gate.py::test_blocking_checks -x` | ❌ Wave 0 |
| DATA-02 | normalized ETL 実行・型/コード変換 | integration | `uv run pytest tests/test_normalized_etl.py -x` | ❌ Wave 0 |
| DATA-02 | raw 行ハッシュ不変（成功基準#2） | integration | `uv run pytest tests/test_raw_immutability.py -x` | ❌ Wave 0 |
| DATA-03 | クラス正規化: `jyokencd5`→`class_level_numeric`（§17.3） | unit | `uv run pytest tests/test_class_normalization.py -x` | ❌ Wave 0 |
| DATA-03 | code 005 が 2019年改革前後で同じ `class_level_numeric=1`（Pitfall 7） | unit | `uv run pytest tests/test_class_normalization.py::test_code_005_spans_reform -x` | ❌ Wave 0 |
| DATA-03 | `post_2019_class_system_flag` が `2019-06-08` 境界 | unit | `uv run pytest tests/test_class_normalization.py::test_reform_date -x` | ❌ Wave 0 |
| 成功基準#4 | `pit_join.py` sortedness raise | unit | `uv run pytest tests/utils/test_pit_join.py -x` | ❌ Wave 0 |
| 成功基準#4 | `group_split.py` race_id disjoint | unit | `uv run pytest tests/utils/test_group_split.py -x` | ❌ Wave 0 |
| 成功基準#4 | `category_map.py` `__UNSEEN__` fallback | unit | `uv run pytest tests/utils/test_category_map.py -x` | ❌ Wave 0 |
| 成功基準#4 | `calibrator.py` 時系列順序 assert（`max(train) < min(calib)`） | unit | `uv run pytest tests/utils/test_calibrator.py -x` | ❌ Wave 0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml`（`uv init --package`、`requires-python = ">=3.12,<3.13"`、`[tool.pytest.ini_options]`・ruff 設定）— 全テストの前提
- [ ] `uv add --dev pytest==9.1.0` — フレームワーク未導入
- [ ] `tests/conftest.py` — psycopg3 接続 fixture（`everydb2` DB への読取専用接続）
- [ ] `src/db/connection.py` — pydantic-settings による `.env` 接続管理（DSN 構築）
- [ ] `src/config/settings.py` — `.env` → 設定オブジェクト（機密値は `.env` のみ、planning 文書に書かない）
- [ ] `.env.example` — 接続設定の雛形（実値は含めない）
- [ ] `src/config/class_normalization.yaml` — DATA-03 の正（01-RESEARCH.md の対応表を直接転記）

*これらは Wave 1 の実装タスクが動く前に満たされなければならない（MISSING 参照解消）。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 読取専用ロールの付与（`REVOKE UPDATE,DELETE` on `raw_everydb2`） | DATA-02 / 成功基準#2 | DB ロール DDL は環境構築ステップ。ETL の行ハッシュ pytest がその効果を自動検証 | `psql` でロール権限を確認: `SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema='raw_everydb2';` に UPDATE/DELETE が無いこと |
| 品質レポート Markdown の人間による目視 | DATA-01 | verdict 以外の補助情報（NULL率分布等）は参考レポート。verdict 自体は自動 | `reports/quality_report.md` を開き、テーブル一覧・日付範囲・mojibake フラグが表示されること |

---

## Validation Sign-Off

- [ ] 全タスクが `<automated>` verify または Wave 0 依存を持つ
- [ ] Sampling continuity: 自動 verify を持たないタスクが3連続しない
- [ ] Wave 0 が全 MISSING 参照をカバーする
- [ ] watch-mode フラグなし
- [ ] Feedback latency < 30s
- [ ] frontmatter の `nyquist_compliant: true` を立てる

**Approval:** pending
