---
phase: 1
slug: trust-foundation
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-17
approved: 2026-06-17
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
| DATA-02 | raw 行ハッシュ不変（成功基準#2） | integration | `uv run pytest tests/test_raw_immutability.py::test_raw_unchanged_after_etl -x` | ❌ Wave 0 |
| DATA-02 / D-06 | raw_everydb2 スキーマ上の KEIBA_DB_USER に UPDATE/DELETE/TRUNCATE/INSERT 権限が無い（権限側、plan 01-01 REVOKE と対象一致） | integration | `uv run pytest tests/test_raw_immutability.py::test_raw_role_has_no_update_grant -x` | ❌ Wave 0 |
| DATA-03 / A1 | gradecd='C'/'D' の syubetucd 交差確認（RESEARCH Open Question #1 RESOLVED） | integration | `uv run pytest tests/test_class_normalization.py::test_audit_gradecd_d_by_syubetucd -x` | ❌ Wave 0 |
| DATA-02 | hassotime='0'（初期値）が NaT にフォールバックし ETL 停止しない（Warning #5） | unit | `uv run pytest tests/test_normalized_etl.py::test_hassotime_zero_falls_back_to_nat -x` | ❌ Wave 0 |
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

- [x] `pyproject.toml`（`uv init --package`、`requires-python = ">=3.12,<3.13"`、`[tool.pytest.ini_options]`（`markers = ["requires_db: ..."]` 含む・Warning #8）・ruff 設定）— 全テストの前提（plan 01-01 Task 1/2 で作成）
- [x] `uv add --dev pytest==9.1.0` — フレームワーク未導入（plan 01-01 Task 1）
- [x] `tests/conftest.py` — psycopg3 接続 fixture（`everydb2` DB への読取専用接続）+ `@pytest.mark.requires_db` skip ポリシー（plan 01-01 Task 2・Warning #8）
- [x] `src/db/connection.py` — pydantic-settings による `.env` 接続管理（DSN 構築）（plan 01-01 Task 2）
- [x] `src/config/settings.py` — `.env` → 設定オブジェクト（機密値は `.env` のみ、planning 文書に書かない）（plan 01-01 Task 2）
- [x] `.env.example` — 接続設定の雛形（実値は含めない・`KEIBA_ADMIN_DSN` を含む）（plan 01-01 Task 1/3）
- [x] `src/config/class_normalization.yaml` — DATA-03 の正（01-RESEARCH.md の対応表を直接転記）（plan 01-01 Task 4）
- [x] `KEIBA_ADMIN_DSN` — plan 01-01 Task 3 が REVOKE を実行する管理者接続（ユーザー手動提供・Manual-Only Verifications 参照）

*これらは Wave 1 の実装タスクが動く前に満たされなければならない（MISSING 参照解消）。plan 01-01 で全て作成・`KEIBA_ADMIN_DSN` のみユーザー提供。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KEIBA_ADMIN_DSN で示す管理者ロール／パスワードの用意 | DATA-02 / 成功基準#2 / D-06 | DB 管理者権限の credential 調達は Claude が実施不可（ユーザーの環境に依存）。plan 01-01 Task 3 が `scripts/run_apply_schema.py` でこの DSN を使い `REVOKE UPDATE,DELETE,TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM <KEIBA_DB_USER>` を実行・plan 01-03 Task 3 の `test_raw_role_has_no_update_grant` が DB カタログから自動検証 | `.env` に `KEIBA_ADMIN_DSN=postgresql://<admin>:<pw>@localhost/everydb2` を設定（superuser または everydb2 objects の所有者）。未設定の場合 plan 01-01 Task 3 が `RuntimeError` で fail する |
| 品質レポート Markdown の人間による目視 | DATA-01 | verdict 以外の補助情報（NULL率分布等）は参考レポート。verdict 自体は自動 | `reports/quality_report.md` を開き、テーブル一覧・日付範囲・mojibake フラグが表示されること |

---

## Validation Sign-Off

- [x] 全タスクが `<automated>` verify または Wave 0 依存を持つ
- [x] Sampling continuity: 自動 verify を持たないタスクが3連続しない
- [x] Wave 0 が全 MISSING 参照をカバーする
- [x] watch-mode フラグなし
- [x] Feedback latency < 30s
- [x] frontmatter の `nyquist_compliant: true` を立てた

**Approval:** approved 2026-06-17（revision pass: Blocker #1/#2/#3 + Warning #4/#5/#6/#8/#9/#10 解消。Warning #7 plan 01-03 分割は見送り – Blocker/WARNING 修正で density リスクは許容範囲と判断）
