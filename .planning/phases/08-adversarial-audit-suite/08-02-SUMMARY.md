---
phase: 08-adversarial-audit-suite
plan: 02
subsystem: testing
tags: [reproducibility, sc3, smoke-orchestrator, audit-report, known-limitations, byte-reproducible]

# Dependency graph
requires:
  - phase: 08-adversarial-audit-suite
    provides: 08-01 (tests/audit/ パッケージ・9テスト KEIBA_SKIP_DB_TESTS=1 で GREEN・DB 不要)
  - phase: 04-model-prediction
    provides: tests/model/test_calibrator.py::test_reproduce_bit_identical (SC#4 calibrator bit-identical・live-DB 不要) + src/model/orchestrator.py::FIXED_REPRODUCE_TS (SC#3 基盤)
  - phase: 05-ev-backtest
    provides: src/ev/report.py (md+json 分離・REPORT_COLUMNS・_atomic_write_text・sort_keys=True DRY パターン) + reports/06-evaluation.json (回収率/calibration_max_dev 数値根拠)
provides:
  - scripts/run_reproducibility_smoke.py (SC#3 合成層 orchestrator・2 step subprocess・DB 不要 pytest のみ・main()->int)
  - src/audit/__init__.py + src/audit/report.py (AUDIT_SURFACE_COLUMNS・SURFACE_ROWS・KNOWN_LIMITATIONS・SC_CORRESPONDENCE・generate_audit_report)
  - reports/08-audit.md (人間確認版・5セクション見出し・サーフェス別カバレッジマップ・SC対応表・Known Limitations)
  - reports/08-audit.json (byte-reproducible・sort_keys=True・surface_map/known_limitations/constants/sc_correspondence/full_suite_result 階層)
affects: [08-03-PLAN (live-DB 必須再現 CLI checkpoint)・v1-milestone-audit (出荷ゲート証憠)]

# Tech tracking
tech-stack:
  added: []  # 新規依存なし (既存 subprocess/argparse/json/Path + src.model.artifact._atomic_write_text のみ)
  patterns:
    - "subprocess orchestrate の薄い orchestrator (D-03): 既存 pytest を束ねる・新規フルパイプライン runner 作らない・main(argv)->int 構造・いずれかの step 非零 exit で即座 return 1"
    - "md+json 分離 reports DRY パターン再利用 (src/ev/report.py): 定数外部化 (AUDIT_SURFACE_COLUMNS)・_atomic_write_text・sort_keys=True byte-reproducible・presence assert (LOW-05 analog)"
    - "presence assert による列契約機械検証 (LOW-05 analog): md ヘッダ行と json row キーが AUDIT_SURFACE_COLUMNS と 1:1 であることを loud fail で検証"

key-files:
  created:
    - scripts/run_reproducibility_smoke.py (SC#3 合成層 orchestrator・116行)
    - src/audit/__init__.py (パッケージマーカー)
    - src/audit/report.py (md+json 生成ロジック・315行)
    - reports/08-audit.md (人間確認版・監査レポート)
    - reports/08-audit.json (byte-reproducible・機械消費版)
  modified: []

key-decisions:
  - "SC#3 合成層は run_train_predict/run_backtest --check-reproduce を呼ばず DB 不要 pytest のみ (calibrator bit-identical + tests/audit/) で orchestrate (D-03・F-02/F-03)。live-DB 必須 CLI は 08-03 checkpoint に委譲。subprocess.run 呼出に run_train_predict/run_backtest を含まないことを grep (match count == 0) で検証"
  - "NC-03: trainer bit-identical 群 (tests/model/test_trainer.py -k 'reproduce or bit_identical or deterministic') は現状0件のため step から除外 (collect-only で確認)・将来追加時に戻すこと"
  - "SURFACE_ROWS に evaluation_metrics 行を必ず含める (F-05・REQUIREMENTS.md L65 TEST-01 評価指標計算・existing_tests=test_metrics/test_evaluator/test_evaluator_gate)"
  - "KNOWN_LIMITATIONS 3項目を定数 (RECOVERY_CEILING_NOTE / CALIBRATION_BL_INFERIOR_NOTE / ODDS_JODDS_REVERIFICATION_NOTE) で強制し md と json の両方に出力 (D-05・隠蔽構造的に不可)。数値根拠は reports/06-evaluation.json から直接確認 (LGB recovery_rate=0.7022・CatBoost 0.6808・LGB calibration_max_dev=0.2308 vs BL-1 0.0014)"
  - "presence assert の md ヘッダ行抽出は先頭行 (レポートタイトル) でなく・表ヘッダ行を明示的に抽出して column 名を検証する (Rule 1 auto-fix)"

patterns-established:
  - "SC#3 合成層 orchestrator: 既存 pytest を subprocess で束ねる薄いスクリプト・DB 不要層と live-DB 必須層 (08-03) の分離"
  - "監査レポートの列契約 presence assert: AUDIT_SURFACE_COLUMNS 定数で md ヘッダと json キーを 1:1 保持・loud fail で検証"

requirements-completed: [TEST-01]

# Metrics
duration: 3min
completed: 2026-06-25
status: complete
---

# Phase 8 Plan 02: Reproducibility Smoke + Audit Report Summary

**SC#3 合成層 orchestrator (scripts/run_reproducibility_smoke.py・DB 不要 pytest 2 step subprocess・live-DB 必須 CLI は 08-03 委譲) と reports/08-audit.{md,json} 生成ロジック (src/audit/report.py・AUDIT_SURFACE_COLUMNS presence assert・KNOWN_LIMITATIONS 3項目 honest 開示・byte-reproducible) を新設**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-24T23:42:06Z
- **Completed:** 2026-06-24T23:45:20Z
- **Tasks:** 2
- **Files modified:** 5 (全て新規作成)

## Accomplishments
- scripts/run_reproducibility_smoke.py 新設 (D-03): SC#3 合成層の薄い orchestrator。2 step (calibrator bit-identical pytest + tests/audit/) を subprocess.run で順次実行・いずれかが非零 exit で return 1・全 PASS で return 0。NC-03 対応で trainer bit-identical 群は collect-only で該当0件を確認し step から除外。run_train_predict/run_backtest --check-reproduce は呼ばない (F-02/F-03・live-DB 必須・08-03 委譲)。grep で subprocess.run 呼出に run_train_predict/run_backtest を含まないことを検証 (match count == 0)
- src/audit/report.py 新設 (D-01/D-05): AUDIT_SURFACE_COLUMNS 定数 (6要素 tuple) で md 列ヘッダと json キーを 1:1 保持・generate_audit_report 末尾の presence assert (LOW-05 analog) で loud 検証。SURFACE_ROWS は SC#1 #1-#8 (8サーフェス) + categorical_missing + ui_csv_readonly + evaluation_metrics (F-05・REQUIREMENTS.md L65 TEST-01 評価指標計算) の11行
- KNOWN_LIMITATIONS 3項目を定数で強制 (D-05・隠蔽構造的に不可): RECOVERY_CEILING_NOTE (回収率天井 ~0.65-0.70・LGB 0.7022/CatBoost 0.6808・memory fukusho-recovery-070-structural-ceiling 整合) / CALIBRATION_BL_INFERIOR_NOTE (LGB calibration_max_dev=0.2308 vs BL-1 0.0014・Phase 4 SC#2 確定) / ODDS_JODDS_REVERIFICATION_NOTE (Phase 5 odds・JODDS取得後に再検証・manual-only 分離)
- reports/08-audit.{md,json} 生成: md は人間確認用 (5セクション見出し: タイトル/サーフェス別カバレッジマップ/SC#1/#2/#3 対応表/Known Limitations/フルスイート GREEN 証明)・json は byte-reproducible (sort_keys=True・ensure_ascii=False・2回生成 diff なしで検証)。_atomic_write_text で原子的書込 (partial-failure 抑止)
- SC_CORRESPONDENCE: SC#1 (機能テスト) / SC#2 (adversarial 3ケース・Plan 08-01) / SC#3 (run_reproducibility_smoke・08-03 委譲) の対応表データ

## Task Commits

各 task を原子的に commit (dirty-tree containment で scripts/run_backtest.py・src/db/prediction_load.py は未ステージ維持):

1. **Task 1: scripts/run_reproducibility_smoke.py 新設 — SC#3 既存 CLI orchestrate (D-03)** - `688002c` (feat)
2. **Task 2: src/audit/report.py + reports/08-audit.{md,json} 生成 (D-01, D-05)** - `d47d03a` (feat)

**Plan metadata:** (本 SUMMARY + STATE.md + ROADMAP.md・最終 commit で別途実施)

## Files Created/Modified
- `scripts/run_reproducibility_smoke.py` - SC#3 合成層 orchestrator (main(argv)->int・sys.path ガード・2 step subprocess・--step デバッグオプション)
- `src/audit/__init__.py` - パッケージマーカー (docstring コメント1行)
- `src/audit/report.py` - 監査レポート生成 (AUDIT_SURFACE_COLUMNS・SURFACE_ROWS 11行・SC_CORRESPONDENCE・KNOWN_LIMITATIONS 3項目・generate_audit_report・presence assert)
- `reports/08-audit.md` - 人間確認版 (5セクション見出し・サーフェス別カバレッジマップ・SC対応表・Known Limitations 3項目)
- `reports/08-audit.json` - byte-reproducible (surface_map/known_limitations/constants/sc_correspondence/full_suite_result 階層)

## Decisions Made
- SC#3 合成層は DB 不要 pytest (calibrator bit-identical + tests/audit/) のみで orchestrate (D-03)。run_train_predict/run_backtest --check-reproduce は live-DB 必須 (run_train_predict は --synthetic flag 非存在・run_backtest --synthetic --check-reproduce は readonly_pool=None でラベル未結合→ValueError で非零 exit 確定) のため 08-03 checkpoint に委譲 (F-02/F-03)
- NC-03: trainer bit-identical 群 (tests/model/test_trainer.py -k 'reproduce or bit_identical or deterministic') は現状 (commit eff76c6 時点) 該当0件・collect-only で確認済のため step から除外。将来 trainer に bit-identical テストが追加された場合は steps に戻すこと (docstring に明記)
- SURFACE_ROWS に evaluation_metrics 行を必ず含め (F-05・REQUIREMENTS.md L65 TEST-01 評価指標計算)・existing_tests に tests/ev/test_metrics.py + tests/model/test_evaluator.py + tests/model/test_evaluator_gate.py を明記
- KNOWN_LIMITATIONS の数値は reports/06-evaluation.json から直接確認 (LGB recovery_rate=0.7021532541 / CatBoost 0.6807827217 / LGB calibration_max_dev=0.2307692308 / bl1 0.001425964)・記載と実データの整合性を保証
- SC_CORRESPONDENCE で SC#3 の「合成層 (08-02)・live-DB 必須層 (08-03)」の分離を明示し・SC#3 達成が 08-02 単独で完結しないことを honest に記載

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] presence assert の md ヘッダ行抽出が先頭行 (レポートタイトル) を見ていた**
- **Found during:** Task 2 (generate_audit_report 初回実行)
- **Issue:** presence assert が `md_payload.splitlines()[0]` (="# Phase 8 Adversarial Audit Report...") を ヘッダ行として検査していたため・AUDIT_SURFACE_COLUMNS[0] ("surface") が見つからず AssertionError で loud fail
- **Fix:** md 先頭行はレポートタイトルのため・表ヘッダ行 ("| surface | sc_id | ..." 形式) を明示的に抽出するよう修正。`for line in md_payload.splitlines(): if line.startswith("| ") and AUDIT_SURFACE_COLUMNS[0] in line:` で表ヘッダを特定
- **Files modified:** src/audit/report.py
- **Verification:** generate_audit_report が GREEN で完了・presence assert が通る・md ヘッダと json キーが AUDIT_SURFACE_COLUMNS と 1:1 であることを検証
- **Committed in:** d47d03a (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug・実装バグ/auto-fix)
**Impact on plan:** presence assert の検証ロジックの初期バグ (md ヘッダ行の特定誤り)・plan の intent・acceptance criteria は不変・スコープクリープなし。

## Issues Encountered
- なし (NC-03 の trainer bit-identical 群0件は plan で予見済み・collect-only で確認し step から除外)

## User Setup Required
None - no external service configuration required. (run_reproducibility_smoke.py は DB 不要 pytest のみ・reports 生成も外部入力なし)

## Next Phase Readiness
- SC#3 合成層 (08-02) と live-DB 必須層 (08-03) の分離が確立・08-03 checkpoint が run_train_predict/run_backtest --check-reproduce を人間承認付きで実行する基盤が整った
- reports/08-audit.{md,json} が v1 マイルストーン出荷ゲート証憠の素材として生成済・Known Limitations 3項目が honest 開示されている
- TEST-01「リーク防止の対抗的監査テストを含む」の SC#3 (合成層) が機械検証可能な形で成立・SC_CORRESPONDENCE で SC#1/#2/#3 の達成状況が一枚のレポートに集約された

## Self-Check: PASSED

**作成ファイルの存在確認:**
- FOUND: scripts/run_reproducibility_smoke.py
- FOUND: src/audit/__init__.py
- FOUND: src/audit/report.py
- FOUND: reports/08-audit.md
- FOUND: reports/08-audit.json

**commit の存在確認:**
- FOUND: 688002c (Task 1)
- FOUND: d47d03a (Task 2)

---
*Phase: 08-adversarial-audit-suite*
*Completed: 2026-06-25*
