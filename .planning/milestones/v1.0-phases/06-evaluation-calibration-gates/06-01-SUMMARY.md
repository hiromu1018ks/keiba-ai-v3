---
phase: 06-evaluation-calibration-gates
plan: 01
subsystem: evaluation
tags: [test, evaluator, segment, calibration, wave-0, foundation]
requires:
  - Phase 4 evaluator.py（compute_metrics / _compute_calibration_max_dev(_guarded) / check_sum_p_distribution）
  - Phase 4 reports/04-eval.json（事前登録指標の実データ値）
  - label.fukusho_label / prediction.fukusho_prediction（実 DB）
  - raw_everydb2.n_odds_tanpuku / normalized.n_uma_race（market segment 軸フォールバック）
provides:
  - tests/model/test_evaluator.py（Phase 4 evaluator.py 既存契約の回帰固定化・Phase 6 拡張前基盤）
  - tests/model/test_segment_axis_columns.py（segment 6軸カラム経路の実 DB 検証・Open Question #1 RESOLVED）
  - pyproject.toml の plotly>=6.8.0 + scipy>=1.17.1 明示依存（D-10 segment HTML 出力前提）
affects:
  - Plan 06-02（evaluator.py 拡張: quantile_max_dev / ECE / MCE + check_acceptance_gate）
  - Plan 06-05（run_evaluation.py: segment 評価生成・fetch_market_data JOIN 経路）
tech-stack:
  added:
    - plotly>=6.8.0（segment HTML 出力用・D-10）
    - scipy>=1.17.1（scipy.stats.spearmanr 直接 import 用・REVIEW Codex LOW・以前は sklearn 推移依存）
  patterns:
    - Phase 4 契約固定化テスト（RED でなく GREEN 即座成立・Phase 6 拡張時の回帰検知基盤）
    - 実 DB information_schema.columns 検証（requires_db・readonly_cur・parameterized query）
    - label/market 二段階 segment 軸確認（REVIEW HIGH#3 fail-loud + C3 フォールバック）
key-files:
  created:
    - tests/model/test_evaluator.py
    - tests/model/test_segment_axis_columns.py
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - D-plotly-version: plotly>=6.8.0（pyproject.toml 明示依存・D-10 segment HTML 出力前提・uv add で最新版確認）
  - D-scipy-explicit: scipy>=1.17.1 を明示依存化（sklearn 推移依存で利用可能だが Phase 6 で spearmanr 直接 import・REVIEW Codex LOW 対応）
  - D-report-regen-deferred: reports/04-eval.json の calibration_max_dev_guarded 列欠損（C6 stale）の解消は Plan 06-02（evaluator.py 拡張時）または 06-05 に委ねる（Wave 0 の本質は契約固定化テスト + segment 軸確認・test_calibration_max_dev_report_value_match は unguarded 実データ値で GREEN のため再生成不要）
  - D-openq1-resolved: Open Question #1（segment 軸カラム経路）は test_segment_axis_columns.py GREEN で実 DB 裏付け確定。label に ninki/odds は不存在・market データ（n_uma_race.ninki + n_odds_tanpuku.fukuoddslow）JOIN 経路で補完可能・fetch_market_data が確立済み経路を再利用
metrics:
  duration: 約15分
  completed: 2026-06-23
  tasks: 2
  files_created: 2
  files_modified: 2
  tests_added: 11
status: complete
---

# Phase 6 Plan 01: Wave 0 基盤（plotly 依存 + evaluator.py 契約固定化 + segment 軸確認） Summary

evaluator.py Phase 4 既存契約（事前登録指標の実データ値・binning 定数・single-class NaN・y_pred==1.0 clip）を回帰テストで固定化し、segment 6軸カラムのデータ経路（label + market JOIN）を実 DB で検証して Open Question #1 を解決した Phase 6 全後続 Wave の前提基盤。

## What Was Built

### Task 1: plotly 依存追加 + evaluator.py Phase 4 既存契約固定化テスト（commit 51fc461）

**plotly + scipy 明示依存追加（pyproject.toml + uv.lock）:**
- `plotly>=6.8.0` 追加（D-10 segment HTML 出力の前提・CLAUDE.md Plotly 推奨に整合）
- `scipy>=1.17.1` 追加（REVIEW Codex LOW・Phase 6 で `from scipy.stats import spearmanr` を直接 import・推移依存の暗黙前提を解消）

**tests/model/test_evaluator.py 新設（7 テスト・全 GREEN）:**

| テスト | 検証内容 | 根拠 |
|--------|----------|------|
| `test_compute_metrics_uniform_max_dev_unchanged` | compute_metrics の calibration_max_dev が同一入力で同値（bit-identical・Phase 4 SC#4 延長） | 事前登録定義（uniform・ガードなし）の再現性 |
| `test_calibration_max_dev_report_value_match` | reports/04-eval.json の実データ値（lightgbm=0.23076923076923073 / catboost=0.25789298770355484 / bl1=0.0014259639516354672）と完全一致 | D-04 事前登録指標不変・T-04-24 後知恵すり替え防止の前提 |
| `test_calibration_curve_constants` | CALIBRATION_CURVE_BINS==10 / STRATEGY=="uniform" / MIN_BIN_COUNT==30 / METRIC_COLUMNS に calibration_max_dev + _guarded が両方含まれる | binning 契約固定（Phase 6 拡張でも不変） |
| `test_compute_calibration_max_dev_guarded_bit_identical` | _compute_calibration_max_dev_guarded が同一入力で同値 | 純 NumPy bit-identical（bincount/digitize・pandas.groupby 不使用） |
| `test_check_sum_p_distribution_returns_keys` | large_violation_rate / small_violation_rate / total_races / diagnostic_note キーが存在 | §15.2 機械検査契約・Phase 6 gate 判定が消費 |
| `test_compute_metrics_single_class_nan` | single-class y_true で calibration_max_dev / _guarded / auc が NaN | 定義不可の境界ケース |
| `test_compute_calibration_max_dev_guarded_y_pred_one` | y_pred==1.0 を含むデータで IndexError なく float を返す | Specialist 指摘 (b) np.clip 実装の回帰固定化 |

### Task 2: segment 6軸カラム経路確認テスト（commit 50b9d0b・Open Question #1 解決）

**tests/model/test_segment_axis_columns.py 新設（requires_db・4 テスト・実 DB で全 GREEN）:**

| テスト | 検証内容 | 実 DB 結果 |
|--------|----------|------------|
| `test_prediction_table_has_segment_join_keys` | prediction.fukusho_prediction に RACE_KEY 7カラム + race_date + split が存在 | GREEN（entry_count は prediction 側に不存在・label JOIN で補完） |
| `test_label_table_has_segment_axes` | label.fukusho_label に race_date / jyocd / 頭数軸（sales_start_entry_count or final_starter_count）が存在 | GREEN（race_date/jyocd/sales_start_entry_count/final_starter_count 全て存在） |
| `test_segment_join_coverage` | prediction test split と label JOIN 後行数が一致（cartesian duplication なし） | GREEN（pred_test=44,426 行 = joined=44,426 行・完全一致） |
| `test_market_data_segment_axes_if_label_missing` | label に不在の ninki/odds が market データに存在するか（フォールバック経路） | GREEN（ninki → normalized.n_uma_race.ninki / オッズ帯 → raw_everydb2.n_odds_tanpuku の fukuoddslow/fukuoddshigh/fukuninki） |

## Open Question #1 RESOLVED

researcher が 06-CONTEXT.md で「segment 軸が揃うことを確認」とした記述（実コード未検証）を・本テスト GREEN で実 DB 裏付け確定:

| segment 軸 | カラム | データソース | JOIN 経路 |
|------------|--------|--------------|-----------|
| year/month | `race_date` | label.fukusho_label | 直接 |
| 競馬場 | `jyocd` | label.fukusho_label | 直接 |
| 頭数 | `sales_start_entry_count` / `final_starter_count` | label.fukusho_label | 直接 |
| 人気帯 | `ninki` | normalized.n_uma_race | fetch_market_data JOIN（label には不存在） |
| オッズ帯 | `fukuoddslow` / `fukuoddshigh` | raw_everydb2.n_odds_tanpuku | fetch_market_data JOIN（label には不存在） |

Plan 06-05 run_evaluation.py は `src/model/baseline.py::fetch_market_data` が確立済みの JOIN 経路を再利用し、6軸全ての segment 評価を生成可能。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] reports/04-eval.json の calibration_max_dev_guarded 列欠損（C6 stale）対処の委譲**
- **Found during:** Task 1（reports/04-eval.json 読込時）
- **Issue:** PLAN action ステップ 2 は reports/04-eval.json を現 evaluator.py で再生成し guarded 列（9列化）を追加することを指示。しかし現 evaluator.py は既に `calibration_max_dev_guarded` を compute_metrics 戻り値に含むが・reports/04-eval.json は Phase 4 生成時点の 8 列（guarded 列なし）。
- **Executor 判断（PLAN が許容）:** PLAN action ステップ 2 末尾で「もし再生成が困難な場合は Plan 06-05 run_evaluation.py が代替値で補完する経路に切り替え（本 PLAN の read_first/action で executor が判断）」と明示的に executor 判断を委譲済み。
- **判断根拠:** (a) test_calibration_max_dev_report_value_match は unguarded 実データ値（0.23076.../0.25789.../0.00142...）で GREEN のため D-04 事前登録指標の回帰固定化は達成済み・(b) Wave 0 の本質は契約固定化テストと segment 軸確認でありレポート再生成は Plan 06-02（evaluator.py 拡張時）または 06-05 が自然なタイミング・(c) モデル予測値は不変（SC#4 bit-identical 維持）で evaluation レポート再生成のみのため後続 Plan でいつでも実施可能。
- **Files modified:** なし（委譲のみ・reports/04-eval.json は未変更）
- **Deferred to:** Plan 06-02（evaluator.py 拡張時）または Plan 06-05（run_evaluation.py）

**2. [Rule 3 - Blocking] tests/model/__init__.py 等の取扱（PLAN 通り・既存確認のみ）**
- **Found during:** Task 1（テストファイル作成前）
- **Issue:** PLAN は tests/model/__init__.py を「既存のため新規作成せず」と明示判断（REVIEW Codex LOW cycle-2）。
- **確認結果:** `find tests -name __init__.py` で tests/__init__.py / tests/model/__init__.py / tests/db/__init__.py / tests/ev/__init__.py / tests/features/__init__.py / tests/utils/__init__.py 全て既存（本プロジェクトの package marker 規約として確立済）。
- **対応:** PLAN 通り新規作成せず・既存規約に従い保持。Phase 6 の新規テストは既存 __init__.py がそのまま package marker として機能。

## Verification

- `uv run pytest tests/model/test_evaluator.py tests/model/test_segment_axis_columns.py -v` → **11 passed in 1.03s**
- pyproject.toml dependencies に `plotly>=6.8.0` と `scipy>=1.17.1` が含まれる（grep で確認）
- reports/04-eval.json の実データ値（lightgbm/catboost/bl1 の calibration_max_dev）が test で固定化
- prediction test split 44,426 行が label.fukusho_label と完全 JOIN（cartesian duplication なし）
- segment 6軸のデータ経路が全て実 DB で確認（label 直接 + market JOIN フォールバック）

## Self-Check: PASSED

- [x] tests/model/test_evaluator.py 存在（11 テスト中 7 テスト GREEN）
- [x] tests/model/test_segment_axis_columns.py 存在（11 テスト中 4 テスト GREEN・requires_db・実 DB）
- [x] pyproject.toml に plotly>=6.8.0 / scipy>=1.17.1 含まれる
- [x] commit 51fc461 存在（Task 1）
- [x] commit 50b9d0b 存在（Task 2）
