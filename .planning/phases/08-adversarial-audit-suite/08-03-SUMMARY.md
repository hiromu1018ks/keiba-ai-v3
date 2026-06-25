---
phase: 08-adversarial-audit-suite
plan: 03
subsystem: testing
tags: [checkpoint, human-verify, live-db, full-suite, sc1, sc3, reproducibility, label-backfill]

# Dependency graph
requires:
  - phase: 08-adversarial-audit-suite
    provides: 08-01 (tests/audit/ パッケージ・9テスト GREEN) + 08-02 (scripts/run_reproducibility_smoke.py + src/audit/report.py + reports/08-audit.{md,json})
  - phase: 04-model-prediction
    provides: scripts/run_train_predict.py --check-reproduce (SC#4 bit-identical・live-DB 必須)
  - phase: 05-ev-backtest
    provides: scripts/run_backtest.py --bt-filter --check-reproduce (SC#4 bit-identical・live-DB 必須)
provides:
  - KEIBA_SKIP_DB_TESTS unset live-DB フルスイート GREEN 証明 (SC#1・D-04・checkpoint approved)
  - SC#3 live-DB 必須 CLI 層 GREEN 証明 (run_train_predict / run_backtest --check-reproduce・F-02/F-03)
  - reports/08-audit.md「フルスイート GREEN 証明」セクションの実績反映 (499 passed / 1 skipped Phase 6 C6 stale 明記)
affects: [v1-milestone-audit (出荷ゲート証憠・完了)・将来 PHASE2/PHASE3 (label race_date 再発の根本調査が別途推奨)]

# Tech tracking
tech-stack:
  added: []  # 新規依存なし (検証のみ)
  patterns:
    - "checkpoint:human-verify の代行実行 (memory run-authorized-ops-directly / phase7-ui-live-db-bugs 準拠): Claude 側が live-DB 検証を実施し結果を提示・ユーザー承認を得る"
    - "label race_date backfill 復元 (run_label_race_date_backfill.py・idempotent・raw 不変・WR-07): race_date 全行 NULL 再発時に都度復元可能・聖域安全"

key-files:
  created: []  # 検証のみ・新規ファイルなし
  modified:
    - src/audit/report.py (フルスイート証明セクションの「0 skipped」断言を実績に修正・Rule 1)
    - reports/08-audit.md (実績反映: 499 passed / 1 skipped Phase 6 C6 stale / failed 0 / approved)
    - reports/08-audit.json (full_suite_result に passed/skipped/failed/skip_reason を追加)

key-decisions:
  - "1 skipped (test_evaluator.py:490・reports/04-eval.json calibration_max_dev_guarded 列欠損) は Phase 6 C6 stale 既知 (Plan 06-05 委譲・STATE.md decision 記録済み)・KEIBA_SKIP_DB_TESTS 由来でない・conftest.py fail-by-default policy は守備 (requires_db 全実行)。acceptance「skipped == 0」の intent (KEIBA_SKIP_DB_TESTS unset で requires_db が silent skip されない) は満たされ・T-08-09/T-08-10 (silent skip 誤認) 対象外として人間承認"
  - "label.fukusho_label.race_date 全行 NULL (3度目の再発・STATE.md / fukusho-recovery-070 debug ノート既記録) を run_label_race_date_backfill.py で復元 (554267/554267 non-NULL・raw 不変 PASS・idempotent verify PASS) してから run_backtest --check-reproduce を再実行し exit=0 を確認。本 plan は files_modified 空 (検証のみ) だが・race_date 復元は検証前提の環境整備 (idempotent・raw 不変・聖域安全) として実施"
  - "reports/08-audit.md の「0 skipped」断言 (08-02 生成時の期待値) を実績 (499 passed / 1 skipped Phase 6 C6 stale 明記・approved) に修正 (D-05 honest 開示・Rule 1 事実誤差)。src/audit/report.py の full_suite 文言 + json full_suite_result を更新し reports/08-audit を再生成 (byte-reproducible)"
  - "reports/05-backtest は run_backtest --check-reproduce 実行で BT-1 単窓結果に上書きされる副作用 (NC-01) を trap による退避→復元で byte-identical 保持・本 plan files_modified 空契約を遵守"

patterns-established:
  - "live-DB 出荷ゲート checkpoint: Claude 代行実行 + ユーザー承認 (KEIBA_SKIP_DB_TESTS unset フルスイート + SC#3 CLI 層)"
  - "race_date 再発時の backfill 復元 (idempotent・raw 不変) を検証前提として扱う運用 (根本調査は別途)"

requirements-completed: [TEST-01]

# Metrics
duration: 35min
completed: 2026-06-25
status: complete
---

# Phase 8 Plan 03: live-DB Full-Suite GREEN + Shipment Gate (checkpoint approved) Summary

**KEIBA_SKIP_DB_TESTS unset で live-DB フルスイート GREEN (499 passed / 1 skipped Phase 6 既知・failed 0) + SC#3 live-DB 必須 CLI 層 (run_train_predict / run_backtest --check-reproduce) bit-identical PASS を人間承認 (approved)・label race_date backfill 復元 (3度目の再発・raw 不変) で SC#3 backtest GREEN を確立**

## Performance

- **Duration:** ~35 min (live-DB 検証セッション全体)
- **Started:** 2026-06-25T08:48Z (SC#3 smoke 合成層)
- **Completed:** 2026-06-25T09:35Z (reports/08-audit 実績反映)
- **Tasks:** 1 (checkpoint:human-verify)
- **Files modified:** 3 (src/audit/report.py・reports/08-audit.md・reports/08-audit.json・全て実績反映)

## Accomplishments

- **SC#1 GREEN (D-04・live-DB フルスイート):** KEIBA_SKIP_DB_TESTS unset で `uv run pytest tests/ -q` が完走・**499 passed / 1 skipped / failed 0** (332秒)。1 skipped は test_evaluator.py:490 (reports/04-eval.json の calibration_max_dev_guarded 列欠損・Phase 6 C6 stale・Plan 06-05 委譲) で KEIBA_SKIP_DB_TESTS 由来でなく・conftest.py fail-by-default policy は守備 (requires_db 全実行)。memory phase7-ui-live-db-bugs (unit test SKIP では検出不可な live-DB bug) の対処を兼ねる
- **SC#3 合成層 GREEN:** `uv run python scripts/run_reproducibility_smoke.py` exit=0 (calibrator bit-identical 1 passed + tests/audit/ 9 passed・DB 不要)
- **SC#3 live-DB CLI 層 GREEN (08-02 から委譲・F-02/F-03):**
  - `run_train_predict.py --check-reproduce --no-write-db` exit=0・SC#4 bit-identical PASS (lightgbm + catboost・固定 seed=42 + thread=1 + FIXED_REPRODUCE_TS)
  - `run_backtest.py --bt-filter BT-1 --check-reproduce --no-write-db` exit=0・SC#4 bit-identical PASS (BT-1 両モデル)・coverage horse=99.99% race=100%・backtest 完走 (LightGBM 0.6471/0.6623・CatBoost 0.6176/0.5995・BL-3 0.8240)
- **NC-01 契約保持:** reports/05-backtest.{md,json} を trap 退避→復元で byte-identical 保持 (MD/JSON とも SHA 復元検証済)・本 plan files_modified 空契約遵守
- **reports/08-audit 実績反映 (D-05 honest):** フルスイート GREEN 証明セクションを「0 skipped」断言から実績 (499 passed / 1 skipped Phase 6 C6 stale / failed 0 / approved) に修正・byte-reproducible 再生成

## Task Commits

本 plan は checkpoint:human-verify・検証のみ (files_modified 空) のため task commit なし。実績反映 (report.py / reports/08-audit) と metadata を最終 commit に集約:

1. **Task 1: KEIBA_SKIP_DB_TESTS unset live-DB フルスイート GREEN + SC#3 全層 GREEN (D-04 / SC#1 / SC#3)** - checkpoint approved (検証のみ・コード commit なし)

**Plan metadata:** (本 SUMMARY + report.py 実績反映 + reports/08-audit 再生成 + STATE.md + ROADMAP.md・最終 commit)

## Files Created/Modified

- `src/audit/report.py` - フルスイート証明 md 文言 + json full_suite_result を実績に修正 (Rule 1 事実誤差・「0 skipped」断言→実績明記)
- `reports/08-audit.md` - 実績反映 (フルスイート GREEN 証明セクション: 499 passed / 1 skipped Phase 6 C6 stale / failed 0 / approved)
- `reports/08-audit.json` - full_suite_result に passed/skipped/failed/skip_reason/detail_ref を追加 (byte-reproducible)

## Decisions Made

- 1 skipped は Phase 6 C6 stale 既知・acceptance「skipped == 0」の intent (KEIBA_SKIP_DB_TESTS unset で requires_db が silent skip されない) は満たされるため・T-08-09/T-08-10 (silent skip 誤認) 対象外として人間承認
- label race_date 全行 NULL (3度目の再発) を backfill で復元してから run_backtest を再実行 (ユーザー選択「backfill復元→再実行」)・race_date 復元は idempotent・raw 不変 (WR-07 PASS) で聖域安全
- reports/08-audit の「0 skipped」断言を実績に修正し D-05 honest 開示を担保 (Rule 1)
- reports/05-backtest を trap 退避→復元で byte-identical 保持 (NC-01・files_modified 空契約)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] label.fukusho_label.race_date 全行 NULL (3度目の再発) で run_backtest --check-reproduce が test 期間 label 0件で ValueError**
- **Found during:** Task 1 (SC#3 live-DB CLI 層・run_backtest --bt-filter BT-1 --check-reproduce 実行)
- **Issue:** label.fukusho_label.race_date が 554267 行すべて NULL (dtype object・全 nan)。_filter_label_by_period が test 期間 2023 の label 行を0件と判定し ValueError (silent フォールバック禁止・§19.1 聖域)。STATE.md (Phase 03 / 2026-06-23) と fukusho-recovery-070 debug ノート (cycle-2 / 2026-06-24) で backfill 復元済み記録があったが現環境の everydb2 で再消滅。SC#4 bit-identical 検証 (本来目的) 自体は両コマンド PASS していた
- **Fix:** ユーザー選択「backfill復元→再実行」に従い scripts/run_label_race_date_backfill.py を実行。rows_backfilled=554267 (expected=554267)・non_null_race_date_count=554267・raw 不変性 PASS (row-hash + row-count + pg_stat 全て不変)・idempotent 検証 PASS (2回実行で checksum 同一 554267|554267)。復元後 run_backtest --check-reproduce を再実行し exit=0 (ValueError 解消・backtest 完走)
- **Files modified:** なし (DB の label.fukusho_label.race_date UPDATE のみ・コード変更なし・raw 不変)
- **Verification:** backfill 後 load_labels で race_date non-NULL count=554267 を確認・run_backtest が reports/05-backtest と一致する backtest 結果で完走 (recovery LightGBM 0.6471/0.6623・BL-3 0.8240)・reports/05-backtest byte-identical 保持
- **Committed in:** (DB 変更のみ・git commit 対象外)

**2. [Rule 1 - Bug] reports/08-audit.md「フルスイート GREEN 証明」セクションの「0 skipped」断言が実績と不整合**
- **Found during:** Task 1 (フルスイート実績 499 passed / 1 skipped と reports/08-audit (08-02 生成) の「0 skipped」記述の突合)
- **Issue:** src/audit/report.py (08-02 成果物) が md「KEIBA_SKIP_DB_TESTS unset 全実行・全 requires_db 含む・0 skipped」と固定出力していたが・実績は 1 skipped (Phase 6 C6 stale)。acceptance「reports/08-audit.md のフルスイート GREEN 証明セクションが live-DB 実行結果と整合」に抵触・D-05 honest 開示に反する
- **Fix:** src/audit/report.py の md 文言を「KEIBA_SKIP_DB_TESTS unset で全 requires_db テストを実行 (conftest.py fail-by-default policy 確証)・checkpoint 08-03 実績: 499 passed / 1 skipped (test_evaluator.py:490・reports/04-eval.json の calibration_max_dev_guarded 列欠損・Phase 6 C6 stale 既知・Plan 06-05 委譲・非 KEIBA_SKIP_DB_TESTS 由来) / failed 0・人間承認済み (approved)」に修正。json full_suite_result に passed/skipped/failed/skip_reason/detail_ref を追加。reports/08-audit.{md,json} を再生成 (byte-reproducible・2回生成で同一 SHA)
- **Files modified:** src/audit/report.py・reports/08-audit.md・reports/08-audit.json
- **Verification:** reports/08-audit.md のフルスイートセクションが実績 (499/1/0) と整合・json byte-reproducible (IDENTICAL)・ruff check src/audit/ GREEN
- **Committed in:** (最終 docs commit に集約)

---

**Total deviations:** 2 auto-fixed (Rule 1 - Bug ×2・いずれも acceptance 整合/honest 開示のための前提復元・スコープクリープなし)
**Impact on plan:** deviation 1 (label race_date backfill) は検証前提の環境復元 (idempotent・raw 不変・聖域安全)・deviation 2 (reports/08-audit 実績反映) は acceptance「整合」と D-05 honest 開示のための事実修正。いずれも plan intent 不変・files_modified 空 (検証のみ) の契約は本質的に遵守 (レポート実績反映を除き新規コード変更なし)。

## Issues Encountered

- label.fukusho_label.race_date の3度目の再発 (Phase 03 / debug 070 に続く)。本 plan では backfill で都度復元したが・なぜ何度も race_date が NULL に戻るか (ETL 再実行 / スナップショット復元 / マイグレーション層) の根本原因調査は別セッション (/gsd-debug 推奨) に委ねる。Phase 8 完了をブロックしない (backfill で都度復元可能・idempotent)

## User Setup Required

PostgreSQL (everydb2) の KEIBA_DATABASE_URL (Phase 1 設定済み)。本検証で使用・追加設定なし。

## Next Phase Readiness

- Phase 8 (Adversarial Audit Suite) の全3 plan 完了・TEST-01 (SC#1/#2/#3) の出荷ゲート証憠が完成
- v1 マイルストーン最終フェーズ完了・/gsd-verify-work (手動確認) または verifier による Phase 8 ゴール検証 → /gsd-complete-milestone へ
- 推奨 (別セッション): label race_date 再消失の根本原因調査 (/gsd-debug)・Phase 6 C6 stale 解消 (reports/04-eval.json 再生成で skipped=0)

## Self-Check: PASSED

**検証実績:**
- フルスイート: 499 passed / 1 skipped (Phase 6 C6 stale) / failed 0 (KEIBA_SKIP_DB_TESTS unset)
- SC#3 smoke 合成層: exit=0
- run_train_predict --check-reproduce: exit=0 (両モデル bit-identical)
- run_backtest BT-1 --check-reproduce: exit=0 (race_date backfill 後・bit-identical PASS・backtest 完走)
- reports/05-backtest: MD/JSON byte-identical (NC-01 保持)
- label race_date backfill: 554267/554267 non-NULL・raw 不変・idempotent verify PASS
- reports/08-audit: 実績反映・byte-reproducible・ruff GREEN

**人間承認:** approved (checkpoint:human-verify gate・blocking 解放)

---
*Phase: 08-adversarial-audit-suite*
*Completed: 2026-06-25*
