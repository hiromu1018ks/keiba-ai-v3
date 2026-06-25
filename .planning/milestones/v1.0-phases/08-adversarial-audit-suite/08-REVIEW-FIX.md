---
phase: 08-adversarial-audit-suite
fixed_at: 2026-06-25T00:00:00Z
review_path: .planning/phases/08-adversarial-audit-suite/08-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 08: Code Review Fix Report

**Fixed at:** 2026-06-25
**Source review:** `.planning/phases/08-adversarial-audit-suite/08-REVIEW.md`
**Iteration:** 1
**Fix scope:** `critical_warning` (Critical 3 + Warning 7 = 10 findings)

**Summary:**
- Findings in scope: 10
- Fixed: 10 (CR-01/CR-02 は前回中断 run で適用済み・今回 run は残り 8 件を全件 fixed)
- Skipped: 0
- Verification: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` → **9 passed** (各 fix 後に GREEN 確認)

## Fixed Issues

### CR-01: `test_audit_features.py` の「リーク注入」は guard を無効化せず・データ偽装のみ

**Files modified:** `src/features/rolling.py`, `tests/audit/test_audit_features.py`
**Commit:** `d1ed797` (前回中断 run で適用済み・今回 run では再修正せず)
**Applied fix:** strict `<` prefilter を module-private `_pit_cutoff_prefilter` helper に切り出し (byte-identical・振舞保存)。テストはその helper を `<=` 版に monkeypatch して guard を真正に無効化する try/finally 経路に書き換え・guard 無効化で previous_day (66) が混入することを検証。80 tests GREEN 確認済み。
**Status:** already_fixed (前回中断 run 適用分・今回 run は touch せず)

### CR-02: `test_audit_label.py` の「cursor end-to-end」は mock cursor の magic-proxy 挙動に偶然依存

**Files modified:** `tests/audit/test_audit_label.py`
**Commit:** `011c60e` (前回中断 run で適用済み・今回 run では再修正せず)
**Applied fix:** mock cursor の `fetchall.return_value = []` を明示設定 (magic-proxy 依存排除)。加えて `inspect.getsource(_check_payout_recall)` で注入キー `fukusho_hit_validated = 0` が本番 SQL に現れることを主張する回帰 guard を追加 (文字列 drift 検出)。GREEN 確認済み。
**Status:** already_fixed (前回中断 run 適用分・今回 run は touch せず)

### CR-03: `test_audit_ui_csv.py` の `_WRITE_DDL_KEYWORDS` が本番 guard と異なり「同一覆盖力」主張が誤实

**Files modified:** `tests/audit/test_audit_ui_csv.py`
**Commit:** `9ed1c82`
**Applied fix:** docstring の「同一覆盖力」虚偽主張を削除し・bare キーワードと本番 guard 複合キーワードの差異を明示開示。「audit GREEN ⇒ 本番 guard GREEN」が成立しない設計差（`DELETE` 単独等の境界ケース）を docstring に明記。キーワード検出動作は不変（SC#2 adversarial GREEN 維持・false positive リスク回避のため trivially safe な修正のみ）。
**Status:** fixed (docstring 開示のみ・動作不変・9 tests GREEN)

### WR-01: `src/audit/report.py` がテスト結果数値 (`passed=499`) を hardcode・実行時に検証しない

**Files modified:** `src/audit/report.py`
**Commit:** `8577a61`
**Applied fix:** `full_suite_result` JSON に `is_static_snapshot: True` / `verified_at_runtime: False` を開示フィールドとして追加。md 側にも「static snapshot・report 生成時に再検証せず・08-03-SUMMARY.md 突合前提」と明記。live pytest 実行の wire-up は意図的に行わず（別 phase の判断）・silent drift リスクの可視化に留める。
**Status:** fixed (開示のみ・live 実行の wire-up は scope 外・9 tests GREEN・generate_audit_report 機能確認済み)

### WR-02: `src/audit/report.py` の presence assert が header_line 抽出を `AUDIT_SURFACE_COLUMNS[0] in line` に依存 (fragile)

**Files modified:** `src/audit/report.py`
**Commit:** `8577a61` (WR-01 と同一 commit・同一ファイルの関連修正のため atomic に適用)
**Applied fix:** header 行抽出を部分文字列検索 (`AUDIT_SURFACE_COLUMNS[0] in line`) から `_format_surface_table_md` が生成するヘッダパターン (`"| surface |"`) の `startswith` に変更。将来 evidence 列に `"surface"` が現れた際の誤行抽出リスクを排除。
**Status:** fixed (presence assert の精度向上・generate_audit_report で header 抽出成功を確認済み)

### WR-03: `scripts/run_reproducibility_smoke.py` が subprocess 失敗時の stdout/stderr を破棄 (debug 性低下)

**Files modified:** `scripts/run_reproducibility_smoke.py`
**Commit:** `12bced2`
**Applied fix:** `subprocess.run(cmd, capture_output=True, text=True)` に変更し・失敗時のみ stdout/stderr の末尾 ~2000 文字を `logger.error` で dump。成功時は出力破棄 (GREEN のまま spam 回避)。強制失敗 path で dump 動作を確認済み。
**Status:** fixed (forced-fail テストで stdout/stderr dump 確認・GREEN path も維持)

### WR-04: `scripts/run_reproducibility_smoke.py` が SC#3 を「合成データ bit-identical」1 test のみで証明 (再現性 smoke として弱い)

**Files modified:** `scripts/run_reproducibility_smoke.py`
**Commit:** `12bced2` (WR-03 と同一 commit・同一ファイルの関連修正のため atomic に適用)
**Applied fix:** docstring のスコープ主張を縮退し・現状 calibrator bit-identical 1 関数のみ (+ SC#2 audit) を cover する「thin orchestrator」であることを冒頭に明記。ファイル名は不変（Plan 08-03 が呼出元・rename は別 phase で判断）。trainer bit-identical 群追加時の step 復帰指針も追記。
**Status:** fixed (docstring スコープ開示のみ・ファイル rename は scope 外・smoke GREEN 確認済み)

### WR-05: `tests/audit/conftest.py` の fixtures/builders (`_build_label_row`, `_build_payout_row`, `_build_history_row`, `audit_mock_cursor`) が未使用 (dead code)

**Files modified:** `tests/audit/conftest.py`
**Commit:** `773e7cb`
**Applied fix:** `grep -rn "_build_label_row\|_build_payout_row\|_build_history_row\|audit_mock_cursor" tests/ src/ scripts/` で全件 conftest 内定義/docstring 言及のみで test ファイルからの import/use が無いことを確認。4 シンボル (3 builder + 1 fixture) を削除し conftest を docstring のみに軽量化 (114 行削減)。docstring に削除履歴と将来拡張時の指針 (tests/features/conftest.py の builder 再利用推奨) を明記。
**Status:** fixed (全件 dead code 確認後に削除・9 tests GREEN 維持)

### WR-06: `test_audit_split.py::test_fold_race_id_shared_detected_and_raises` は既存 test の機械的複製 (D-04 重複)

**Files modified:** `tests/audit/test_audit_split.py`
**Commit:** `31514c0`
**Applied fix:** project_context の推奨に従い docstring note を追加。機械的複製であること (`test_get_bt_race_ids_raises_on_leak` と注入パターン等価・adversarial 新規検証力ゼロ) を誠実に開示しつつ・SC#2 三ケース形状要件 (Plan 08-01) のために残す判断理由と stale 化リスク (片方修正時の同期必須) を明記。テスト本体・検証動作は不変。
**Status:** fixed (docstring 開示のみ・削除は SC#2 形状要件のため見送り・2 tests GREEN)

### WR-07: `test_audit_ui_csv.py::test_reproducibility_stamp_missing_detected` が presence assert の tautology を内包

**Files modified:** `tests/audit/test_audit_ui_csv.py`
**Commit:** `85f7861`
**Applied fix:** step (2) の `for stamp in REPRODUCIBILITY_STAMPS: assert stamp in REPRODUCIBILITY_STAMPS` (定数 tuple なので常に GREEN・検証力ゼロ) を削除。実質検証力は step (4) の `_verify_degraded_tuple_fails_presence_assert` が担うため残置不要。step (2) は5項目であること (§19.1 聖域構成要件) の `len` assert のみ残す。本番 presence assert helper の import 化 (review option 2) は別 phase で判断。
**Status:** fixed (tautology 削除のみ・3 tests GREEN)

## Skipped Issues

なし (critical_warning スコープの全 10 件を fixed で完遂)。

---

_Fixed: 2026-06-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
_Verification: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` → 9 passed (every fix verified GREEN)_
