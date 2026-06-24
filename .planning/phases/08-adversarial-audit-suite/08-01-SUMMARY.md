---
phase: 08-adversarial-audit-suite
plan: 01
subsystem: testing
tags: [pytest, adversarial, leak-prevention, pit-cutoff, payout-reconciliation, race-id-split, ast, csv-stamps]

# Dependency graph
requires:
  - phase: 03-as-of-features-snapshots
    provides: src.features.rolling.build_rolling_features（strict < feature_cutoff_datetime guard）+ tests/features/conftest.py 合成データ builder
  - phase: 02-fukusho-labels
    provides: src.etl.label_reconcile._check_payout_recall / reconcile_against_payout + tests/test_label_reconcile.py _mock_cursor パターン
  - phase: 05-ev-backtest
    provides: src.utils.group_split.BTWindow / BT_WINDOWS / get_bt_race_ids（race_id disjoint guard）+ tests/utils/test_group_split.py
  - phase: 07-presentation
    provides: src.ui.csv_columns.PREDICTION_CSV_COLUMNS / REPRODUCIBILITY_STAMPS + tests/ui/test_readonly_guarantee.py（AST _extract_sql_literals）+ tests/ui/test_csv_columns.py（presence assert）
provides:
  - tests/audit/ パッケージ（SC#2 adversarial 3ケース + D-06 2テスト・計9テスト・KEIBA_SKIP_DB_TESTS=1 で GREEN・DB 不要）
  - SC#2 ケース1 lookahead 注入 adversarial（test_lookahead_injection_detected_and_fails・5段階鋳型）
  - SC#2 ケース2 payout 正欠損注入 adversarial（test_payout_positive_missing_from_labels_detected・cursor ベース end-to-end verdict='fail' 実証）
  - SC#2 ケース3 fold race_id 共有注入 adversarial（test_fold_race_id_shared_detected_and_raises・ValueError(match='race_id')）
  - D-06 UI 書き込み/DDL SQL 注入検出 adversarial（test_ui_write_sql_injection_detected・tmp_path ダミー .py で AST 検出実証）
  - D-06 再現性スタンプ欠落検出 adversarial（test_reproducibility_stamp_missing_detected・PREDICTION_CSV_COLUMNS 4スタンプ + REPRODUCIBILITY_STAMPS 5スタンプ presence assert・縮退 tuple fail 実証）
affects: [08-02-PLAN（フルスイート GREEN 証明）, 08-03-PLAN（再現性 smoke）, v1-milestone-audit（出荷ゲート証憠）]

# Tech tracking
tech-stack:
  added: []  # 新規依存なし（既存 pytest/pandas/ruff のみ）
  patterns:
    - "adversarial（注入型メタ検証）5段階鋳型（test_no_target_encoding_leak L277-486 構造）— 合成データ→ベースライン→リーク注入→guard 有効で正しい結果→guard 無効で混入実証（false-pass 回避）"
    - "mock cursor による payout recall 注入（_mock_cursor・SQL 部分文字列マッチで fetchone 戻り値を制御）"
    - "AST SQL リテラル検査 + presence assert の組み合わせ（D-06 UI/CSV 対抗的監査）"
    - "docstring cross-reference による重複回避（T-08-04 mitigate・機能テストとの棲み分け明示）"

key-files:
  created:
    - tests/audit/__init__.py（パッケージマーカー）
    - tests/audit/conftest.py（_build_label_row/_build_payout_row/_build_history_row・**overrides 注入ヘルパー）
    - tests/audit/test_audit_features.py（SC#2 ケース1・lookahead 注入 adversarial）
    - tests/audit/test_audit_label.py（SC#2 ケース2・payout 正欠損注入 adversarial）
    - tests/audit/test_audit_split.py（SC#2 ケース3・fold race_id 共有注入 adversarial）
    - tests/audit/test_audit_ui_csv.py（D-06・read-only 保証 + スタンプ欠落 adversarial）
  modified: []

key-decisions:
  - "SC#2 3ケースは既存機能テストと重複しないよう docstring cross-reference で棲み分け明示（adversarial=注入型メタ検証・機能テスト=正しく処理される・独立層・T-08-04 mitigate）"
  - "lookahead 注入は strict < を <= に緩める runtime patch でなく・previous_day 行の as_of を cutoff 直前に偽装する経路で再現（機能テスト test_pit_cutoff と同一 guard を素通りさせる注入）"
  - "payout recall は DataFrame 受けの API が存在しないため cursor ベース end-to-end で検証（src/etl/label_reconcile.py L933 署名 cur: Cursor・reconcile_against_payout）"
  - "backtest_strategy_version は予測テーブルに非存在のため PREDICTION_CSV_COLUMNS presence assert 対象から除外（src/ui/csv_columns.py L68-74 docstring・UI 行表示用 REPRODUCIBILITY_STAMPS 側にのみ含む）"
  - "_contains_write_ddl は bare キーワード（insert/update/delete/truncate/create/drop/alter）で広く捉え・前後が英数字でないことを確認する簡易単語境界判定で false positive 回避"

patterns-established:
  - "adversarial テストの docstring 契約: 冒頭に 'SC#2 adversarial' または 'D-06' を明示 + cross-reference で近接機能テストを明記（重複回避・T-08-04）"
  - "adversarial 5段階鋳型: (1) 合成データ構築 (2) 通常経路ベースライン (3) 意図的リーク注入 (4) guard 有効で正しい結果 (5) guard 無効で混入実証（検証力証明・false-pass 回避）"
  - "DB 不要の adversarial テスト設計: mock cursor / 合成 DataFrame / AST 検査で KEIBA_SKIP_DB_TESTS=1 でも実行（requires_db marker なし）"

requirements-completed: [TEST-01]

# Metrics
duration: 5min
completed: 2026-06-24
status: complete
---

# Phase 8 Plan 01: Adversarial Audit Suite Summary

**SC#2 の3リーク注入ケース（lookahead / payout 正欠損 / fold race_id 共有）と D-06（UI 書き込み/DDL SQL 混入 + 再現性スタンプ欠落）を・リークを注入すると fail する独立 adversarial テスト9件として tests/audit/ に新設（KEIBA_SKIP_DB_TESTS=1 で全 GREEN・DB 不要・ruff GREEN）**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-24T23:31:49Z
- **Completed:** 2026-06-24T23:37:09Z
- **Tasks:** 3
- **Files modified:** 6（全て新規作成）

## Accomplishments
- SC#2 ケース1 lookahead 注入 adversarial: previous_day 行の as_of を cutoff 直前に偽装して strict < を素通りさせる注入で・guard 有効なら mean=2.0 不変・guard 無効（T+1 偽装）なら mean=18.0 に変化することを機械検出（false-pass 回避）
- SC#2 ケース2 payout 正欠損注入 adversarial: mock cursor で _check_payout_recall SQL が不一致件数=1 を返すよう注入 → passed=False + cursor ベース end-to-end で reconcile_against_payout verdict='fail' を実証（DataFrame 受け API 非存在のため cursor ベース）
- SC#2 ケース3 fold race_id 共有注入 adversarial: BTWindow で train_end==test_start の R2 共有を注入 → ValueError(match='race_id') を検証 + 正常 BTWindow で raise しない検証力証明
- D-06 UI 書き込み/DDL 注入検出: tmp_path のダミー INSERT .py で _contains_write_ddl が True・正規 src/ui/ 全 .py で False を AST 検査で実証
- D-06 再現性スタンプ欠落検出: PREDICTION_CSV_COLUMNS 4スタンプ（backtest_strategy_version は予測テーブル非存在のため除外）+ REPRODUCIBILITY_STAMPS 5スタンプ（UI 用・backtest_strategy_version 含む）presence assert・縮退 tuple で fail することを実証し検証力証明（§19.1 聖域）
- 各テスト docstring で SC#2 adversarial / D-06 + 近接機能テストへの cross-reference 明示（重複回避・T-08-04 mitigate）

## Task Commits

Each task was committed atomically（TDD: 宣言ファイルのみ staging・dirty-tree containment で scripts/run_backtest.py・src/db/prediction_load.py は未ステージ維持）:

1. **Task 1: tests/audit/ パッケージ基盤 + SC#2 ケース1 lookahead 注入 adversarial** - `86c1f00` (test)
2. **Task 2: SC#2 ケース2 payout 正欠損 + ケース3 fold race_id 共有 adversarial** - `ecb94c5` (test)
3. **Task 3: D-06 UI/CSV 対抗的監査（read-only 保証 + 再現性スタンプ）** - `79912af` (test)

**Plan metadata:**（本 SUMMARY + STATE.md + ROADMAP.md・最終 commit で別途実施）

## Files Created/Modified
- `tests/audit/__init__.py` - パッケージマーカー（docstring コメント1行）
- `tests/audit/conftest.py` - 合成 DataFrame 注入ヘルパー（_build_label_row / _build_payout_row / _build_history_row・**overrides 機構・PII なし・ID のみ）
- `tests/audit/test_audit_features.py` - SC#2 ケース1 lookahead 注入 adversarial（test_lookahead_injection_detected_and_fails・5段階鋳型）
- `tests/audit/test_audit_label.py` - SC#2 ケース2 payout 正欠損注入 adversarial（_mock_cursor 複製・cursor ベース end-to-end verdict='fail'）
- `tests/audit/test_audit_split.py` - SC#2 ケース3 fold race_id 共有注入 adversarial（BTWindow R2 共有 → ValueError(match='race_id')）
- `tests/audit/test_audit_ui_csv.py` - D-06 adversarial（_extract_sql_literals / _contains_write_ddl / _CSV_STAMPS・2テスト + docstring 検証）

## Decisions Made
- SC#2 3ケースは既存機能テスト（test_pit_cutoff / test_label_reconcile / test_group_split）と docstring cross-reference で棲み分け明示（adversarial=注入型メタ検証・機能テスト=正しく処理される・独立層・T-08-04 mitigate）
- lookahead 注入は guard の runtime patch（< を <= に緩める）でなく・previous_day 行の as_of を cutoff 直前に偽装する経路で再現（機能テストと同一 guard を素通りさせる注入・検証力証明は mean が 2.0→18.0 に変化することで機械的確認）
- payout recall は DataFrame 受けの API が存在しないため cursor ベース end-to-end で検証（src/etl/label_reconcile.py L933 署名 cur: Cursor・plan acceptance criteria「DataFrame 受けの API は使わない」に準拠）
- backtest_strategy_version は予測テーブルに非存在のため PREDICTION_CSV_COLUMNS presence assert 対象から除外（_CSV_STAMPS は4項目・UI 行表示用 REPRODUCIBILITY_STAMPS 側にのみ5項目目として含む・acceptance_criteria の grep 検証で presence assert 箇所は0を確認）
- _contains_write_ddl は analog test_readonly_guarantee.py の末尾スペース付きキーワードでなく・bare キーワード（insert/update/delete/truncate/create/drop/alter）で広く捉え・前後が英数字でないことを確認する簡易単語境界判定で "deleted_at" 等の変数名 false positive を回避

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] conftest.py audit_mock_cursor fixture 未使用・docstring 検証テストのモジュール doc 参照バグ**
- **Found during:** Task 1（test_audit_features.py の初回実行）
- **Issue:** `test_lookahead_injection_docstring_cross_reference` が `test_audit_features.__doc__` でモジュール名参照（`test_audit_features` は未定義 Name）・未使用 `pytest` import で ruff FAIL
- **Fix:** `sys.modules[__name__].__doc__` に修正（モジュール doc 取得の正規イディオム）・未使用 `pytest` import 削除。audit_mock_cursor fixture は後続 Task 用に残置（conftest.py の共通基盤）
- **Files modified:** tests/audit/test_audit_features.py
- **Verification:** KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_features.py -v が 2 passed・ruff check GREEN
- **Committed in:** 86c1f00（Task 1 commit）

**2. [Rule 1 - Bug] test_audit_split.py の存在しない BT_WINDOW_TEST_ONLY import**
- **Found during:** Task 2（test_audit_split.py 作成直後の実行前確認）
- **Issue:** `src.utils.group_split` に `BT_WINDOW_TEST_ONLY` が存在しない（勝手に推測した公開 API）・未使用 `BT_WINDOWS` も noqa 付き import していた
- **Fix:** 正規公開 API（`BTWindow` / `get_bt_race_ids` のみ）に修正・src/utils/group_split.py L164-189 を直接精査して BTWindow フィールド（name/train_start/train_end/test_start/test_end/window_type）を確認
- **Files modified:** tests/audit/test_audit_split.py
- **Verification:** KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/test_audit_split.py -v が 2 passed
- **Committed in:** ecb94c5（Task 2 commit）

**3. [Rule 1 - Bug] test_audit_split.py docstring の cross-reference 文字列が改行で分断**
- **Found during:** Task 2（test_audit_split.py の初回実行）
- **Issue:** `test_fold_race_id_shared_detected_and_raises` の docstring で `cross-reference:\n    tests/utils/test_group_split.py` と改行が入り・`"cross-reference: tests/utils/test_group_split.py"` の完全文字列マッチが失敗
- **Fix:** docstring を1行にまとめて `cross-reference: tests/utils/test_group_split.py` を連続文字列に修正
- **Files modified:** tests/audit/test_audit_split.py
- **Verification:** 再実行で GREEN
- **Committed in:** ecb94c5（Task 2 commit）

---

**Total deviations:** 3 auto-fixed（全て Rule 1 - Bug・実装バグ/auto-fix）
**Impact on plan:** 全て実装上の軽微バグ（モジュール doc 参照・未存在 import・docstring 改行）で・plan の intent・acceptance criteria は不変・スコープクリープなし。

## Issues Encountered
- `src.features.builder.build_rolling_features` と `src.features.rolling.build_rolling_features` の2エントリポイントが存在（前者は後者への薄い転送・src/features/builder.py L325-346）。plan は `src.features.rolling.build_rolling_features` を指定しているためそちらに従い・機能テスト test_pit_cutoff.py が使う builder 経由でなく直接 rolling を検査（adversarial は guard 本体を検査する方が intent に合致）

## User Setup Required
None - no external service configuration required.（全テスト DB 不要・KEIBA_SKIP_DB_TESTS=1 で実行）

## Next Phase Readiness
- tests/audit/ パッケージが完成・Phase 8 Plan 02（フルスイート GREEN 証明・KEIBA_SKIP_DB_TESTS unset）の対象に tests/audit/ 9テストが含まれる
- Phase 8 Plan 03（再現性 smoke・scripts/run_reproducibility_smoke.py）から subprocess で tests/audit/ を呼出可能（KEIBA_SKIP_DB_TESTS=1 で GREEN・DB 不要）
- TEST-01「リーク防止の対抗的監査テストを含む」の SC#2 3ケース + D-06 2テストが機械検証可能な形で成立・v1 マイルストーン出荷ゲート証憠（reports/08-audit）の素材が揃った

---
*Phase: 08-adversarial-audit-suite*
*Completed: 2026-06-24*
