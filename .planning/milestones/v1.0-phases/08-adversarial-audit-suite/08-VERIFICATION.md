---
phase: 08-adversarial-audit-suite
verified: 2026-06-25T10:05:00Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 8: Adversarial Audit Suite Verification Report

**Phase Goal:** クロスカッティングなリーク防止テストスイート (TEST-01) — 全サイレント失敗モードサーフェスに対する対抗的監査テスト — が統合・GREEN で、「完成したように見えてそうでない (Looks Done But Isn't)」マイルストーン出荷ゲートとして機能する
**Verified:** 2026-06-25T10:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP 成功基準 + PLAN must_haves 統合)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC#1 | フルスイート GREEN（KEIBA_SKIP_DB_TESTS unset で全 requires_db 含む・リーク防止8サーフェス） | VERIFIED | 08-03 checkpoint 実績: 499 passed / 1 skipped / failed 0。1 skipped は `tests/model/test_evaluator.py:490` の data-driven `pytest.skip()`（reports/04-eval.json の calibration_max_dev_guarded 列欠損・Phase 6 C6 stale・Plan 06-05 委譲）で KEIBA_SKIP_DB_TESTS マーカー由来ではない。conftest.py L66-78 は KEIBA_SKIP_DB_TESTS=1 の時のみ requires_db を skip する fail-by-default policy（unset で全 requires_db 実行）。SC#1 intent「unset で requires_db が silent skip されない」は満たされる |
| SC#2 ケース1 | feature 値が T+1 データを使用すると検出されて fail する adversarial テストが GREEN | VERIFIED | `tests/audit/test_audit_features.py::test_lookahead_injection_detected_and_fails` が5段階鋳型（baseline→注入→guard 有効で正しい結果→guard 無効化で混入検出→検証力証明）を実装。KEIBA_SKIP_DB_TESTS=1 で GREEN 確証（9 passed）|
| SC#2 ケース2 | payout 払戻対象正の馬が label に欠落すると検出されて fail する adversarial テストが GREEN | VERIFIED | `tests/audit/test_audit_label.py::test_payout_positive_missing_from_labels_detected` が mock cursor で不一致件数1を注入→`_check_payout_recall.passed is False`→cursor ベース end-to-end で `reconcile_against_payout(cur)["verdict"]=="fail"` を検証。検証力証明（件数0で passed=True）も実装 |
| SC#2 ケース3 | fold の train/test が race_id を共有すると ValueError で検出される adversarial テストが GREEN | VERIFIED | `tests/audit/test_audit_split.py::test_fold_race_id_shared_detected_and_raises` が BTWindow で train_end==test_start の R2 共有を注入→`pytest.raises(ValueError, match="race_id")` を検証。正常 BTWindow で raise しない検証力証明も実装 |
| SC#2 D-06 (UI/CSV) | src/ui/ の read-only 保証違反・再現性スタンプ欠落を AST/presence assert が検出する adversarial が GREEN | VERIFIED | `tests/audit/test_audit_ui_csv.py::test_ui_write_sql_injection_detected`（tmp_path のダミー INSERT .py で検出 True・正規 src/ui/ で False）+ `test_reproducibility_stamp_missing_detected`（4スタンプ/5スタンプ presence assert + 縮退 tuple で fail 検証力証明・backtest_strategy_version を PREDICTION_CSV_COLUMNS に含めない保護）|
| SC#3 合成層 | scripts/run_reproducibility_smoke.py が合成 bit-identical pytest 群を束ねて固定 seed 再現を確認し GREEN | VERIFIED | 実行 exit=0・2 step 全 PASS（SC#4 calibrator bit-identical 1 passed + tests/audit/ 9 passed）。NC-02: subprocess.run で run_train_predict/run_backtest を呼ばない（grep count=0）。NC-03: trainer bit-identical 群は該当テスト0件のため step から除外（docstring 明記）|
| SC#3 live-DB CLI 層 | run_train_predict/run_backtest --check-reproduce が live-DB で GREEN | VERIFIED | 08-03 checkpoint 実績（approved）: run_train_predict --check-reproduce --no-write-db exit=0（両モデル bit-identical PASS）・run_backtest --bt-filter BT-1 --check-reproduce --no-write-db exit=0（race_date backfill 復元後・SC#4 bit-identical PASS・coverage horse=99.99% race=100%）。NC-01: reports/05-backtest は退避→復元で byte-identical 保持 |
| D-01 | reports/08-audit.{md,json} が生成され・サーフェス別カバレッジマップ + SC対応表 + Known Limitations を含む | VERIFIED | reports/08-audit.md に5セクション（タイトル/サーフェス別カバレッジマップ/SC対応表/Known Limitations/フルスイート GREEN 証明）。json は surface_map(11行)/constants/known_limitations(3)/sc_correspondence(3)/full_suite_result 階層 |
| D-05 | Known Limitations 3項目（回収率天井/Calibration劣位/odds JODDS再検証）が honest 開示 | VERIFIED | reports/08-audit.md「Known Limitations」セクション + json known_limitations に3項目（RECOVERY_CEILING_NOTE / CALIBRATION_BL_INFERIOR_NOTE / ODDS_JODDS_REVERIFICATION_NOTE）が定数で強制・md と json の両方に出力（隠蔽構造的に不可）|
| byte-reproducible | reports/08-audit.json が sort_keys=True・ensure_ascii=False で byte-reproducible | VERIFIED | 2回生成で同一 SHA（d6aeae0998674a00...）・json.dumps sort_keys=True ensure_ascii=False・_atomic_write_text で原子的書込 |
| KEIBA_SKIP_DB_TESTS=1 で tests/audit/ 全実行 | DB 不要・marker なし | VERIFIED | KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q で 9 passed・requires_db marker なし |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `tests/audit/__init__.py` | パッケージマーカー | VERIFIED | 1行 docstring（空マーカー）|
| `tests/audit/conftest.py` | 合成 DataFrame 注入ヘルパー（**overrides）| VERIFIED | 121行・_build_label_row / _build_payout_row / _build_history_row の3 builder 各 **overrides 機構 |
| `tests/audit/test_audit_features.py` | SC#2 ケース1 lookahead 注入 adversarial | VERIFIED | 155行・test_lookahead_injection_detected_and_fails + docstring cross-reference・5段階鋳型 |
| `tests/audit/test_audit_label.py` | SC#2 ケース2 payout 正欠損注入 adversarial | VERIFIED | 149行・test_payout_positive_missing_from_labels_detected・mock cursor + end-to-end |
| `tests/audit/test_audit_split.py` | SC#2 ケース3 fold race_id 共有注入 adversarial | VERIFIED | 113行・test_fold_race_id_shared_detected_and_raises・BTWindow 注入 |
| `tests/audit/test_audit_ui_csv.py` | D-06 read-only 保証 + 再現性スタンプ inline | VERIFIED | 275行・test_ui_write_sql_injection_detected + test_reproducibility_stamp_missing_detected・_extract_sql_literals/_contains_write_ddl/_CSV_STAMPS ヘルパ |
| `scripts/run_reproducibility_smoke.py` | SC#3 合成層 orchestrator | VERIFIED | 116行・main(argv)->int・sys.path ガード・2 step subprocess・live-DB CLI 呼出なし（NC-02）|
| `src/audit/__init__.py` | パッケージマーカー | VERIFIED | 1行 |
| `src/audit/report.py` | reports/08-audit 生成ロジック | VERIFIED | 344行・AUDIT_SURFACE_COLUMNS 定数・generate_audit_report・3 Known Limitations 定数・presence assert |
| `reports/08-audit.md` | 監査レポート人間確認版 | VERIFIED | 5セクション見出し・サーフェステーブル（11行）・Known Limitations 3項目 |
| `reports/08-audit.json` | 監査レポート機械消費版 | VERIFIED | byte-reproducible・sort_keys=True・surface_map/known_limitations/constants/sc_correspondence/full_suite_result |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| test_audit_features.py | src/features/rolling.py::build_rolling_features | import + 呼出 + guard 無効化注入 | WIRED | L24 import・L59/101 呼出・L76 _leaky_build_rolling_features で T+1 偽装注入 |
| test_audit_label.py | src/etl/label_reconcile.py::_check_payout_recall / reconcile_against_payout | import + mock cursor 注入 | WIRED | L23-27 import・L82 _check_payout_recall(cur)・L105 reconcile_against_payout(cur) end-to-end |
| test_audit_split.py | src/utils/group_split.py::get_bt_race_ids | import + BTWindow 注入 | WIRED | L23 import・L65 get_bt_race_ids(leak_races, bad_bt) で ValueError・L77 正常 BTWindow で検証力証明 |
| test_audit_ui_csv.py | src/ui/csv_columns.py::PREDICTION_CSV_COLUMNS + _extract_sql_literals | import + AST 抽出 + presence assert | WIRED | L26 import・L56 _extract_sql_literals・L78 _contains_write_ddl・L174 presence assert |
| run_reproducibility_smoke.py | test_reproduce_bit_identical / pytest tests/audit | subprocess.run | WIRED | L55 tests/model/test_calibrator.py::test_reproduce_bit_identical・L61 pytest tests/audit/ |
| run_reproducibility_smoke.py | run_train_predict / run_backtest --check-reproduce | （08-03 委譲・呼ばない）| WIRED (NC-02) | subprocess.run での run_train_predict/run_backtest 呼出 grep count=0・08-03 checkpoint が代行 |
| src/audit/report.py | src/model/artifact.py::_atomic_write_text | import + 原子的書込 | WIRED | L31 import・L282/L303 _atomic_write_text で md+json 書込 |
| src/audit/report.py | AUDIT_SURFACE_COLUMNS 定数 | presence assert で md/json 1:1 | WIRED | L36 定数・L314-323 presence assert（md ヘッダ + json row キー）|

### Data-Flow Trace (Level 4)

Phase 8 はテスト/レポート生成が主で・動的データレンダリングなし。tests/audit/ は合成データ（_build_*_row ヘルパ）と mock cursor を使い実データ不使用（DB 不要）。reports/08-audit は定数（SURFACE_ROWS / KNOWN_LIMITATIONS / SC_CORRESPONDENCE）から生成され外部入力なし。Level 4 該当サーフェスなし。

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| SC#2 tests/audit/ 全 GREEN（KEIBA_SKIP_DB_TESTS=1・DB 不要）| `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` | 9 passed in 1.00s | PASS |
| SC#3 合成層 smoke GREEN | `uv run python scripts/run_reproducibility_smoke.py` | exit=0・2 step ALL PASS | PASS |
| reports/08-audit.json byte-reproducible | 2回生成で SHA 比較 | d6aeae0998674a00 == d6aeae0998674a00 | PASS |
| ruff GREEN（tests/audit/ + scripts + src/audit/）| `uv run ruff check tests/audit/ scripts/run_reproducibility_smoke.py src/audit/` | All checks passed! | PASS |
| presence assert（md ヘッダ + json キーが AUDIT_SURFACE_COLUMNS と 1:1）| generate_audit_report 実行 | assert 全通過（loud fail なし）| PASS |

### Probe Execution

該当なし（Phase 8 は pytest/adversarial テストが主で scripts/*/tests/probe-*.sh はスコープ外）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| TEST-01 | 08-01 / 08-02 / 08-03 | 複勝ラベル・払戻突合・取消/除外/中止・オッズ時点固定・仮想購入・feature_cutoff_datetime・評価指標計算・race_id 分割・クラス正規化・カテゴリ/欠損処理 + リーク防止の対抗的監査テストを含む | SATISFIED | reports/08-audit.md サーフェス別カバレッジマップが11サーフェス（SC#1 #1-#8 + categorical_missing + ui_csv_readonly + evaluation_metrics）全て COVERED / COVERED+ADVERSARIAL で記載。SC#2 adversarial 3ケース（lookahead/payout/fold）+ D-06（UI/CSV）が tests/audit/ に GREEN で実装・docstring で既存機能テストへ cross-reference 明示 |

**TEST-01 全サーフェスカバレッジ:**
- 複勝ラベル → fukusho_label (COVERED・tests/test_fukusho_label.py)
- 払戻突合 → payout_reconcile (COVERED+ADVERSARIAL・tests/test_label_reconcile.py + tests/audit/test_audit_label.py)
- 取消/除外/中止 → refund_handling (COVERED・tests/test_refund_accounting.py)
- オッズ時点固定 → odds_snapshot (COVERED・tests/ev/test_odds_snapshot.py)
- 仮想購入 → virtual_purchase (COVERED・tests/ev/test_metrics.py)
- feature_cutoff_datetime → feature_cutoff (COVERED+ADVERSARIAL・tests/features/test_pit_cutoff.py + tests/audit/test_audit_features.py)
- race_id 分割 → race_id_split (COVERED+ADVERSARIAL・tests/utils/test_group_split.py + tests/audit/test_audit_split.py)
- クラス正規化 → class_normalization (COVERED・tests/test_class_normalization.py)
- カテゴリ/欠損処理 → categorical_missing (COVERED+ADVERSARIAL・tests/model/test_trainer.py + test_no_target_encoding_leak)
- 評価指標計算 → evaluation_metrics (COVERED・tests/ev/test_metrics.py + tests/model/test_evaluator*.py)

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| （該当なし）| - | - | - | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER/not yet implemented 全てゼロ（tests/audit/ + scripts/run_reproducibility_smoke.py + src/audit/ + reports/08-audit.md スキャン）|

Debt marker gate: GREEN（未参照の TBD/FIXME/XXX なし）。

### Human Verification Required

（なし）

SC#1 の live-DB フルスイート実行（KEIBA_SKIP_DB_TESTS unset）・SC#3 live-DB CLI 層（run_train_predict/run_backtest --check-reproduce）は 08-03 checkpoint:human-verify で実施済み・ユーザー承認（approved）済み。verifier は自動再実行可能な層（KEIBA_SKIP_DB_TESTS=1 での tests/audit/ GREEN・SC#3 合成層 smoke・byte-reproducible・ruff・presence assert・wiring）を独立検証し全て PASS。approved 済みの live-DB 実績は 08-03-SUMMARY.md の証憠（499 passed / 1 skipped Phase 6 C6 stale / failed 0・run_train_predict/run_backtest exit=0・reports/05-backtest byte-identical 保持）を引用する。

### Gaps Summary

**ギャップなし。** Phase 8 の3つの成功基準（SC#1/SC#2/SC#3）全てが実コードで達成されている：

1. **SC#1（フルスイート GREEN）**: 実績 499 passed / 1 skipped / failed 0。1 skipped は Phase 6 C6 stale（reports/04-eval.json の calibration_max_dev_guarded 列欠損・Plan 06-05 委譲・KEIBA_SKIP_DB_TESTS 由来でない）。conftest.py L66-78 は KEIBA_SKIP_DB_TESTS=1 の時のみ requires_db を skip する fail-by-default policy で・unset で全 requires_db テストが実行される。SC#1 の intent「KEIBA_SKIP_DB_TESTS unset で requires_db が silent skip されない」は満たされ・T-08-09/T-08-10（silent skip 誤認）の対象外。acceptance「skipped == 0」の字面との乖離はあるが・roadmap SC#1 の実質的条件（リーク防止8サーフェスが KEIBA_SKIP_DB_TESTS unset で GREEN）は満たされる。Phase 6 C6 stale 解消（reports/04-eval.json 再生成）は別セッション推奨（08-03-SUMMARY 記載）。

2. **SC#2（adversarial 3ケース）**: tests/audit/test_audit_features.py / test_audit_label.py / test_audit_split.py が「リーク注入で fail する」メタ検証として機能する。各テストは5段階鋳型（test_no_target_encoding_leak 構造）を採用し・docstring で SC#2 adversarial（注入型メタ検証）と近接する既存機能テストへの cross-reference を明示（重複回避・T-08-04 mitigate）。KEIBA_SKIP_DB_TESTS=1 で9テスト全 GREEN を独立再実行で確証。D-06（UI/CSV）も test_audit_ui_csv.py で read-only 保証注入検出 + 再現性スタンプ欠落検出が実装され GREEN。

3. **SC#3（reproducibility smoke）**: 合成層（scripts/run_reproducibility_smoke.py）は2 step（SC#4 calibrator bit-identical + tests/audit/）を subprocess で束ね exit=0・新規フルパイプライン runner なし（D-03）。live-DB CLI 層（run_train_predict/run_backtest --check-reproduce）は 08-03 checkpoint で GREEN（approved）・08-02 frontmatter は autonomous: true / user_setup: [] を維持するため 08-03 に委譲（NC-02: 08-02 は subprocess.run で run_train_predict/run_backtest を呼ばない）。

**TEST-01 全サーフェス（11項目）が COVERED / COVERED+ADVERSARIAL で網羅**され・reports/08-audit.{md,json} に集約可視化されている。D-05 Known Limitations 3項目（回収率天井/Calibration劣位/odds JODDS再検証）が定数で強制され md と json の両方に honest 開示される（隠蔽構造的に不可）。

**label race_date 再発（3度目）**: 08-03 検証中に label.fukusho_label.race_date 全行 NULL が再発したが・run_label_race_date_backfill.py で都度復元（554267/554267 non-NULL・raw 不変・idempotent verify PASS）してから run_backtest --check-reproduce を再実行し exit=0 を確認。Phase 8 完了をブロックしない（backfill で都度復元可能・根本調査は別 /gsd-debug 推奨・08-03-SUMMARY 記載）。

**成果物と配線の完全性:** tests/audit/（4ファイル + conftest + __init__）・scripts/run_reproducibility_smoke.py・src/audit/report.py + reports/08-audit.{md,json} の全成果物が存在し・substantive（最小行数満たす）で・wired（key_links 全 WIRED）で・anti-pattern ゼロ・ruff GREEN。SC#2 の3ケースは5段階鋳型で false-pass を構造的に排除し・docstring で既存機能テストと棲み分け明示。

Phase 8（v1 マイルストーン最終フェーズ）の出荷ゲート証憠が完成。

---

_Verified: 2026-06-25T10:05:00Z_
_Verifier: Claude (gsd-verifier)_
