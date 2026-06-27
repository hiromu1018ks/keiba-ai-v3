---
phase: 12-p-lower-ev-falsification-evaluation
plan: 04
subsystem: script
tags: [script, evaluation, falsification, switch-recommendation, wave4, ev-01, eval-01, eval-02, safe-01, live-db]
requires:
  - "12-01 Wave 1 compute_p_lower_conformal_shrinkage 実装"
  - "12-02 Wave 2 orchestrator p_lower_q_shrink keyword-only 引数・ev/purchase_simulator p_col/p_min_base 拡張"
  - "12-03 Wave 3 falsification.py (run_falsification_test / fit_market_implied_calibrator / write_falsification_spec / constants block) + check_phase12_warn_gate + segment_eval.compute_roi_by_bin + refund_accounting.slippage"
  - "Phase 11 idiom (run_phase11_evaluation.py / _attach_label_to_pred / _sanitize_for_json / _atomic_write_text / load_predictions public wrapper / statement_timeout='30s' / set_primary_model Call 0 件)"
provides:
  - "scripts/run_phase12_evaluation.py: Phase 12 統合評価 script (q_shrink 計算・p_lower 生成・falsification・§15.2 + Phase 12 WARN gate・switch_recommendation・8ファイル byte-reproducible 出力)"
  - "_compute_q_shrink_on_calib: calib slice のみで q_shrink 計算・race_key+umaban fail-loud key-join (C-12-04-1 HIGH)"
  - "_write_q_shrink_json: q_shrink.json の byte-reproducible 事前書き出し (C-12-04-1 HIGH)"
  - "run_falsification_pipeline: falsification-spec.json 事前書き出し + fit_market_implied_calibrator (train/calib) → run_falsification_test (test) (C-12-03-1 HIGH)"
  - "compute_switch_recommendation: SC#4 WARN gate + p_lower EV + falsification → switch/hold/reject (D-09)"
  - "_evaluate_gate: §15.2 gate (check_acceptance_gate 不変) + Phase 12 WARN gate (check_phase12_warn_gate) を別キーで併載 (D-06)"
  - "tests/test_run_phase12_evaluation.py: 12 tests (AST / 値レベル adversarial / 聖域 / byte-reproducible / gate 併載)"
affects:
  - "Phase 12 Plan 05 (live-DB checkpoint): run_phase12_evaluation.py の live-DB 実行と reports/12-evaluation/* の REAL 出力・SC#2/SC#3/SC#4/SC#5 実証・switch_recommendation の人間確認"
tech-stack:
  added: []
  patterns:
    - "scripts/run_phase11_evaluation.py idiom 踏襲 (_sanitize_for_json / _atomic_write_text / _attach_label_to_pred race_key+umaban fail-loud join / load_predictions public wrapper / statement_timeout / set_primary_model Call 0件)"
    - "[C-12-04-1 HIGH] q_shrink 計算 calib slice のみ (score_split='calib' 機械保証) + q_shrink.json test 窓評価前事前書き出し (theta-selection.json idiom)"
    - "[C-12-04-2 HIGH] test 窓 p_lower は orchestrator.train_and_predict(score_split='test', p_lower_q_shrink=<calib値>) で外部注入 (keyword-only 唯一経路)"
    - "[C-12-03-1 HIGH] falsification-spec.json の test 窓評価前事前書き出し (threshold dredging 監査)"
    - "[C-12-01-2 HIGH] 値レベル adversarial test (test labels 改変で q_shrink.json sha256 不変・calib labels 改変で変化)"
    - "[C-12-04-3] 事前登録定数の falsification.py 集約 + import (run script 重複定義なし・BT1_PERIODS のみ run script 固有)"
key-files:
  created:
    - scripts/run_phase12_evaluation.py
    - tests/test_run_phase12_evaluation.py
  modified: []
decisions:
  - "C-12-04-1 HIGH: _compute_q_shrink_on_calib を race_key+umaban fail-loud key-join で実装 (Phase 11 _attach_label_to_pred idiom・index 前提でなく機械的 join)・join 失敗は RuntimeError"
  - "C-12-04-4 MEDIUM: docstring は Phase 11 の『load_predictions を呼ばない』誤りを踏襲せず・実際は load_predictions を呼ぶ事実を正確に反映・D-10 対象を set_primary_model のみに限定"
  - "D-09: compute_switch_recommendation は SC#4 WARN gate FAIL → reject / SC#4 PASS + EV 改善 + feature_gap → switch / それ以外 → hold の3値判定・is_primary DB 変更は人間承認の別アクション"
  - "D-06: §15.2 gate は evaluator.check_acceptance_gate(metrics_dict, sum_p_check) をそのまま消費し run script 側で再定義しない・Phase 12 WARN gate (check_phase12_warn_gate) と別キーで併載"
metrics:
  duration: 775s
  completed: 2026-06-27T14:10:15Z
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
  tests_added: 12
  commits: [d0881f1, 69cd065, 9da055c, fa783bc, 1a97bc6]
status: complete
---

# Phase 12 Plan 04: p_lower EV + Falsification 統合評価 script Summary

Phase 12 Plan 01〜03 の成果を統合し・§11.2 聖域 (calib slice のみ・test 窓 outcome 不使用) を機械保証しながら・q_shrink 計算・p_lower 生成・falsification 回帰・§15.2 gate + Phase 12 WARN gate 評価・switch_recommendation を1本の評価 script に統合した。

## One-liner

`run_phase12_evaluation.py` が `score_split='calib'` で q_shrink を計算し test 窓評価前に `q_shrink.json` を事前書き出し→ `score_split='test'` で calib 済み q_shrink を `p_lower_q_shrink` keyword-only 引数で注入して p_lower を生成→ `run_falsification_pipeline` が `falsification-spec.json` を事前書き出し後に train/calib fit → test eval→ `check_acceptance_gate` (§15.2 不変) + `check_phase12_warn_gate` を別キーで併載→ `compute_switch_recommendation` が switch/hold/reject を report のみに出す (D-10: set_primary_model Call 0件)。

## 成果

### Task 1 (commit d0881f1) — scripts/run_phase12_evaluation.py + tests/test_run_phase12_evaluation.py

新規ファイル:
- **`scripts/run_phase12_evaluation.py`** (1302行) — Phase 12 統合評価 script
- **`tests/test_run_phase12_evaluation.py`** (12 tests) — 契約検査

主な構成要素 (すべて計画書 `<action>` と整合):
- `_compute_q_shrink_on_calib` (C-12-04-1 HIGH): calib slice のみで `compute_p_lower_conformal_shrinkage` を呼び・pred_proba と y_calib を race_key+umaban fail-loud key-join で整列 (Phase 11 `_attach_label_to_pred` idiom)。join 失敗は RuntimeError (silent label/pred_proba ズレ回避)。
- `_write_q_shrink_json` (C-12-04-1 HIGH): q_shrink 計算経路決定直後・test 窓評価に先立ち `reports/12-evaluation/q_shrink.json` を byte-reproducible (sort_keys=True/ensure_ascii=False/allow_nan=False + atomic write) に書き出す。theta-selection.json idiom と同一形状・後知恵すり替え禁止。Pitfall 1 過度な保証主張回避の coverage_semantics フィールド併記。
- `main()` (C-12-04-2 HIGH): `orchestrator.train_and_predict(score_split='test', theta=selected_theta, p_lower_q_shrink=<calibで計算した値>)` で calib 済み q_shrink を注入し test 窓 p_lower を生成 (Plan 02 の `p_lower_q_shrink` keyword-only 引数が唯一の受取経路)。
- `run_falsification_pipeline` (C-12-03-1 HIGH・C-12-03-4 2-window 分離): (1) `write_falsification_spec` で `falsification-spec.json` を test 窓評価前に byte-reproducible に事前書き出し (threshold dredging 監査)→(2) `fit_market_implied_calibrator` を train/calib 窓のみで fit (base=LogisticRegression train・calibrator=CalibratedClassifierCV calib・FrozenEstimator で base 再 fit 回避)→(3) `run_falsification_test` を test 窓予測のみで評価 (予測モデル p の再学習を行わない・事前登録評価回帰仕様を test 窓に fit する最終検定は許容)。
- `_evaluate_gate` (D-06): `evaluator.check_acceptance_gate(metrics_dict, sum_p_check)` をそのまま消費し §15.2 gate (block_triggered/block_reasons/warn_reasons) を取得。Phase 12 専用 WARN gate (`check_phase12_warn_gate`・phase12_warn_triggered) を別キーで併載 (上書きでない)。binning 契約 (CALIBRATION_CURVE_BINS/ODDS_BAND_EDGES 等) は evaluator/segment_eval から import 再利用 (codex HIGH#2・bit-identical・再定義禁止)。
- `compute_switch_recommendation` (D-09): SC#4 WARN gate FAIL → reject / SC#4 PASS + EV 改善 + feature_gap → switch / それ以外 → hold の3値判定。`is_primary` DB 変更はしない (D-10)・判断材料を report に出すのみ。
- `_compute_recovery_rate`: `ev_rank.compute_ev_and_rank` + `purchase_simulator.select_bets` (p_col/p_min_base 切替) + `refund_accounting.determine_stake_payout` を chain し §11.6 回収率を算出。
- `_configure_statement_timeout` (memory: subagent-db-query-statement-timeout): module-level callback・readonly/etl pool の全 connection に `SET statement_timeout = '30s'` を適用 (run_phase11 L271-280 idiom)。
- 事前登録定数 (C-12-04-3): `Q_LEVEL_SHRINKAGE`/`Q_LEVEL_FALSIFICATION`/`HOLM_ALPHA`/`MARKET_CALIB_SAMPLE_THRESHOLD`/`ODDS_CLIP_MIN/MAX`/`LOGIT_CLIP_EPS`/`PHASE12_*_THRESHOLD` は `src/eval/falsification.py` (Plan 03 constants block・C3-12-03-1 で Q_LEVEL_SHRINKAGE 追加済み) から import。`BT1_PERIODS` (train/calib/test 期間) のみ run script 固有 (run_phase11 と同一)。
- docstring (C-12-04-4 MEDIUM): D-10 対象を `set_primary_model` のみに限定。Phase 11 docstring (run_phase11 L36-44) の load_predictions 呼出事実についての不正確な記述を踏襲せず・本 script は `prediction_load.load_predictions` (public wrapper) を呼ぶ事実を正確に反映 (SC#5 idempotent swap)。
- migration (C-12-04-5 HIGH): `PREDICTION_ADD_P_LOWER_SQL` (Plan 01 で src/db/schema.py に追加済み) は `run_apply_schema.py` (owner/admin 権限・`uv run python scripts/run_apply_schema.py`) に一本化し本 script からは実行しない (Phase 11 L286-290 idiom・memory: migration-privilege-admin-required)。
- 報告書の byte-reproducible 出力 (SC#5・§19.1): 8 ファイル (12-evaluation.md/.json・falsification.md/.json・falsification-spec.json・switch-recommendation.md/.json・q_shrink.json) を json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False) + _atomic_write_text で出力。falsification-spec.json と q_shrink.json は main() の手順 (3)(5) で test 窓評価前に事前書き出し (監査証跡)。

## 聖域遵守 (core value: リーク防止・再現性)

- **§11.2 test 窓 sanctuary (critical)**:
  - q_shrink 計算は `orchestrator.train_and_predict(score_split='calib')` の calib slice のみ (codex HIGH#1・score_split guard L449-455 が test 窓に触れない機械保証)。`_compute_q_shrink_on_calib` の signature は `{calib_pred_df, y_calib_df, q_level}` のみで・test 窓 outcome 系引数を取らない (Shared Pattern 6)。
  - `q_shrink.json` と `falsification-spec.json` を test 窓評価前に byte-reproducible に事前書き出し (theta-selection.json idiom・後知恵すり替え禁止・threshold dredging 監査)。
  - `fit_market_implied_calibrator` は train/calib 窓のみで fit (C-12-03-4 2-window 分離・test 窓 outcome 系引数を取らない)。`run_falsification_test` は test 窓予測のみで評価 (予測モデル p の再学習を行わない)。
- **[C-12-01-2 HIGH] 値レベル adversarial**: `test_14_q_shrink_value_level_adversarial` が合成データで (a) test labels 改変で q_shrink.json sha256 不変・(b) calib labels 改変で変化 を検証 (signature-only 監査でなく値レベルで §11.2 聖域の実リークを検出・codex HIGH#4)。
- **D-10 (is_primary 立てない)**: `set_primary_model` の ast.Call node 0件 (`test_03_set_primary_model_call_zero` で AST check)。switch_recommendation は report のみ (D-09)。
- **D-06 (§15.2 gate 不変)**: `_evaluate_gate` は `evaluator.check_acceptance_gate(metrics_dict, sum_p_check)` をそのまま消費し・§15.2 gate の定義を run script 側で再定義しない。Phase 12 拡張指標は §15.2 指標と別キーで併載 (`test_05_evaluate_gate_colists_phase12_warn_and_section_15_2` で検証)。
- **byte-reproducible §19.1**: FIXED_REPRODUCE_TS + 固定 seed/thread・json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False) + _atomic_write_text・`test_06_q_shrink_json_byte_reproducible` で同一入力の2回書き出しが byte-identical であることを検証。
- **SAFE-01**: 本 script は odds/market_implied を evaluation 専用層 (falsification / ev_rank / purchase_simulator / refund_accounting) で消費するが・FEATURE_COLUMNS / build_training_frame / load_feature_matrix 等 feature 構築経路を通じて feature に混入させない (orchestrator.train_and_predict の FEATURE_COLUMNS allowlist が保証)。
- **statement_timeout**: readonly/etl pool の configure callback で `SET statement_timeout = '30s'` を全 connection に適用 (`test_09_statement_timeout_30s_configured` で検証・memory: subagent-db-query-statement-timeout)。

## Deviations from Plan

None - 計画書の `<action>` / `<done>` / `<verify>` をすべて実行。`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_run_phase12_evaluation.py -x -q` で 12 tests 全 GREEN。全套 `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q` で 720 passed / 48 skipped / 0 failed (regression なし)。ruff check / format クリーン。

### Auto-fixed Issues

**1. [Rule 3 - Blocking] check_acceptance_gate の正しい signature への対応**
- **Found during:** Task 1 実装中・test_05 実行時
- **Issue:** 計画書の `<action>` は `check_acceptance_gate` の呼出形式を明記していなかった。実装の初回は `check_acceptance_gate({"baseline":..., "race_relative":...})` と単一 dict で呼んだが・実 signature は `check_acceptance_gate(metrics_dict, sum_p_check)` の2引数 (evaluator.py L888-891)。TypeError で停止。
- **Fix:** `check_sum_p_distribution` も呼び `(metrics_dict, sum_p_check)` の2引数で呼ぶよう修正。§15.2 gate の定義を run script 側で再定義しない (D-06) 点は維持。baseline / rr 両方の §15.2 gate 結果を併載。
- **Files modified:** scripts/run_phase12_evaluation.py (`_evaluate_gate`)
- **Commit:** d0881f1

**2. [Rule 3 - Blocking] _configure_statement_timeout の module-level 化**
- **Found during:** Task 1 実装中・test_09 実行時
- **Issue:** 計画書は run_phase11 L271-280 idiom を参照していたが・run_phase11 では `_configure_statement_timeout` は `main()` 内のローカル関数。`test_09` が `inspect.getsource(mod._configure_statement_timeout)` で module-level attr の存在を検証するため・ローカル関数だと `hasattr` が False になる。
- **Fix:** `_configure_statement_timeout` を module-level に引き上げ (run_phase11 の docstring idiom と同一の振る舞い・pool の configure callback として渡す点は不変)。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** d0881f1

**3. [Rule 1 - Bug] test_10 の重複定義検出を AST module-level Assign に精緻化**
- **Found during:** Task 1 テスト実装中
- **Issue:** test_10 の当初の検出ロジックは「行頭が `Q_LEVEL ` 等で始まる」文字列マッチで・docstring 中の `HOLM_ALPHA / MARKET_CALIB_SAMPLE_THRESHOLD / ...` 行を false positive に拾っていた。
- **Fix:** AST で module-level の `ast.Assign` / `ast.AnnAssign` ターゲット名だけを検出するよう精緻化。docstring / markdown / コメント中の言及は対象外 (C-12-04-3 の意図「重複定義の回避」を正確に反映)。
- **Files modified:** tests/test_run_phase12_evaluation.py
- **Commit:** d0881f1

## codex review HIGHs 対応 (Phase 12 Cycle 1-3)

| HIGH / MEDIUM | 本 plan での対応 | 検証 |
|---------------|-----------------|------|
| C-12-04-1 HIGH (q_shrink calib slice のみ) | `_compute_q_shrink_on_calib` が score_split='calib' の calib slice のみで計算・race_key+umaban fail-loud key-join | `test_01_q_shrink_uses_calib_slice_only` / `test_11_q_shrink_label_alignment_race_key_umaban_fail_loud` / `test_14_q_shrink_value_level_adversarial` |
| C-12-04-2 HIGH (q_shrink 外部注入) | `main()` が `orchestrator.train_and_predict(score_split='test', p_lower_q_shrink=<calib値>)` で calib 済み q_shrink を注入 (keyword-only 唯一経路) | `main()` 実装 (L619-644) + orchestrator L795-803 の RuntimeError guard が対応 |
| C-12-03-1 HIGH (falsification-spec.json 事前書き出し) | `run_falsification_pipeline` が `write_falsification_spec` で test 窓評価前に byte-reproducible に事前書き出し | `test_13_falsification_spec_pre_written_byte_reproducible` |
| C-12-01-2 HIGH (値レベル adversarial) | `test_14` が合成データで test labels 改変→sha256 不変・calib labels 改変→sha256 変化 を検証 | `test_14_q_shrink_value_level_adversarial` |
| C-12-04-3 MEDIUM (事前登録定数 import 集約) | Q_LEVEL_SHRINKAGE 等を falsification.py から import・run script に module-level 重複定義なし (BT1_PERIODS のみ run script 固有) | `test_10_constants_imported_no_duplicates` |
| C-12-04-4 MEDIUM (docstring 正確性) | docstring が load_predictions を呼ぶ事実を正確に反映・D-10 対象を set_primary_model のみに限定 | `test_15_docstring_accurate_calls_load_predictions` |
| C-12-04-5 HIGH (migration 呼ばない) | PREDICTION_ADD_P_LOWER_SQL は run_apply_schema.py (owner/admin) に一本化・本 script からは削除 | docstring + `main()` 内注記 (L566-572) |
| C2-12-04-2 (Q_LEVEL_SHRINKAGE も falsification.py 集約) | Q_LEVEL_SHRINKAGE を falsification.py から import・run script で再定義しない | `test_10_constants_imported_no_duplicates` (Q_LEVEL が forbidden_patterns に含まれ AST で検出) |
| C3-12-03-1 (Plan03 側 Q_LEVEL_SHRINKAGE 定義) | 本 plan は consumer 側・producer 側 (falsification.py) は Plan 03 で C3-12-03-1 fix 済み (commit 4fb64db) | `test_10` が `hasattr(falsification_mod, 'Q_LEVEL_SHRINKAGE')` で再確認 |

## Known Stubs

`run_phase12_evaluation.py` は live-DB 実行を前提とする script であり・unit test (KEIBA_SKIP_DB_TESTS=1) では合成データで生成ロジック・構造・byte-reproducible 性・聖域を検証する。実際の `reports/12-evaluation/*` の REAL 出力 (SC#2/SC#3/SC#4/SC#5 の live-DB 実証・switch_recommendation の人間確認) は Plan 05 checkpoint でオーケストレータが live-DB で実行する (user_setup 参照)。本 plan では `reports/12-evaluation/` に合成データのレポートを commit せず・live run のための生成機構のみを届ける (honest recording・synthetic data を real results として偽装しない)。

## Threat Flags

該当なし。本 plan で新規に導入された security-relevant surface (network endpoint / 認証経路 / file access pattern / trust boundary schema 変更) はなく・計画書 `<threat_model>` の T-12-18..T-12-25 の mitigate はすべて実装に反映済み。

## Phase 12 Plan 05 引き継ぎ材料

- `scripts/run_phase12_evaluation.py` の live-DB 実行 (`uv run python scripts/run_phase12_evaluation.py --baseline-snapshot-id ... --bt-split BT-1 --odds-snapshot-policy 30min_before --selected-theta 1.0 --out-dir reports`) が Plan 05 checkpoint の主要アクション。
- owner/admin 権限での `run_apply_schema.py` 実行 (PREDICTION_ADD_P_LOWER_SQL 適用) が前提 (user_setup・memory: migration-privilege-admin-required)。
- 生成される `reports/12-evaluation/` の8ファイルの REAL 出力を人間が確認し・switch_recommendation (switch/hold/reject) を判断材料として受け取る (D-09/D-10・人間承認の別アクション)。
- 本 plan の unit test (12 tests) は live-DB 実行後も regression なく GREEN を維持するはず (合成データと REAL データで生成ロジックは同一・byte-reproducible 性は入力依存)。

## Gap-Closure (2026-06-27〜28・live-DB END-TO-END 修正)

Plan 05 checkpoint (live-DB 実証) に先立ち・commit d0881f1 の初期実装が live-DB で完走しない2つの欠陥を gap-closure として修正した。本修正は 12-04 の success criteria (SC#1-5 / EV-01 / EVAL-01 / EVAL-02 / SAFE-01) を live-DB で実証可能にするもので・聖域 (§11.2 / SAFE-01 / §15.2 不変 / D-10 / byte-reproducible / statement_timeout) を全て維持した。

### 修正した欠陥

**gap-closure bug #1 [Rule 1 - Bug] entry_count KeyError**:
- **Found during:** live-DB 実行 (`uv run python scripts/run_phase12_evaluation.py --non-interactive`)
- **Issue:** `evaluator.check_sum_p_distribution(pred_df, entry_count_col="entry_count")` が `KeyError: 'Column not found: entry_count'` で停止。orchestrator は `sales_start_entry_count` (orchestrator.py L731) を提供するが・`entry_count` 列は提供しない。`run_falsification_pipeline` の `field_size_test` も `entry_count` を要求。
- **Fix:** `_ensure_entry_count` helper を追加し・`sales_start_entry_count` → `entry_count` の alias を eval コピー (baseline_pred / rr_pred) に付与 (fallback: final_starter_count / race_key group count)。SAFE-01: rr_test_result["pred_df"] (PREDICTION_COLUMNS 20-col) には触れない。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** 9da055c

**gap-closure bug #2 [Rule 1 - Bug] JODDS odds JOIN 欠落 (falsification WARNING skip)**:
- **Found during:** live-DB 実行
- **Issue:** `run_phase12_evaluation.py` が JODDS odds (fuku_odds_lower/fuku_odds_upper) を eval コピーに JOIN しておらず・`_safe_run_falsification_pipeline` が `test_pred_df に fuku_odds_lower / p_fukusho_hit が無い・skip (D-15 参考記録)` で WARNING skip されていた (falsification が実際には1度も実行されない)。`_compute_recovery_rate` (EV)・`_compute_odds_band_calib_max_dev` (SC#4 gate)・`switch_recommendation` ゞ odds 欠損で機能不全。
- **Fix:** `_attach_odds_to_pred` helper を追加し・run_backtest.py L448-460 / L575-600 の PROVEN pattern (fetch_jodds → select_odds_snapshot → race_key+umaban merge + HIGH-2 len assert) で eval コピーに odds を付与。frame (FEATURE_COLUMNS 由来・odds-free) から falsification 用 train/calib を切り出していた経路も・`_build_falsification_windows` で odds-enriched な train/calib を別途構築するよう変更 (frame は D-07/§13.4 odds-free allowlist)。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** 9da055c, 1a97bc6

**gap-closure bug #3 [Rule 3 - Blocking] falsification NaN odds で LogisticRegression 失敗**:
- **Found during:** gap-closure bug #2 修正後の live-DB 実行
- **Issue:** no_bet sentinel (fuku_odds_lower NaN) の馬が test_df に残り・calibrator.predict_proba が NaN を返し・logit で NaN が伝播して `fit_market_implied_calibrator` の LogisticRegression が `Input X contains NaN` で失敗。
- **Fix:** `run_falsification_pipeline` の test 窓評価で・train/calib と同様に odds 欠損行を除外 (統計的妥当: 市場と比較可能な馬のみで検定・no_bet 馬は falsification 対象外)。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** 1a97bc6

**gap-closure bug #4 [Rule 3 - Blocking] JODDS fetch が statement_timeout で QueryCanceled**:
- **Found during:** gap-closure bug #2 修正後の live-DB 実行
- **Issue:** train+calib 窓 (2019-2022・4年) の JODDS fetch が既定 `statement_timeout='30s'` で `QueryCanceled` (test 窓 1 年で 7,379,660 行 / 41s・train+calib 4 年で ~4min 見込み)。
- **Fix:** JODDS fetch スコープ (test 窓 + falsification 用 train/calib 窓) の cursor のみ `statement_timeout='600s'` に延長。pool の configure callback (30s) は維持・cursor の SET は connection 毎で他 cursor に伝播しない (memory: subagent-db-query-statement-timeout の趣旨維持)。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** fa783bc

**gap-closure bug #5 [Rule 1 - Bug] _compute_recovery_rate 必須列欠損**:
- **Found during:** gap-closure bug #2 修正後の live-DB 実行
- **Issue:** `_compute_recovery_rate` が `is_fukusho_sale_available / is_model_eligible` 欠損で NaN を返し・switch_recommendation の判断材料が欠けていた。`_attach_label_to_pred` が `fukusho_hit_validated` しか label/frame から伝播していなかった。
- **Fix:** `_attach_label_to_pred` が `is_fukusho_sale_available / is_model_eligible / fukusho_payout_places / is_scratch_cancel / is_race_excluded / is_race_cancelled / is_dead_loss` も label/frame から eval コピーに伝播 (purchase_simulator.select_bets / refund_accounting.determine_stake_payout が消費)。
- **Files modified:** scripts/run_phase12_evaluation.py
- **Commit:** 1a97bc6

### live-DB 実測値 (REAL・honest recording・memory: fix-must-verify-gate-result-livedb)

`uv run python scripts/run_phase12_evaluation.py --non-interactive` (BT-1 / 2023 test 窓 / snapshot=20260626-1a-opponentstrength-v1 / odds_snapshot_policy=30min_before / selected_theta=1.0) で得た実測値:

| 指標 | 実測値 | 備考 |
|------|--------|------|
| q_shrink | **0.332832** | calib slice のみ・q_level=0.90・§11.2 聖域 (score_split='calib') |
| q_shrink.json byte-reproducible | PASS | 2 回実行で sha256 完全一致 (sort_keys/ensure_ascii/allow_nan) |
| falsification verdict | **feature_gap** | model_p_coef=0.00627・model_p_pvalue=0.0395 < α=0.05・race_id clustered SE |
| odds_band サブ解析 (Holm 補正) | 1.0-2.9 のみ有意 | corrected_p=0.0010 (有意)・他 band は non-significant |
| §15.2 gate (baseline) | WARN | large_violation_rate=69.4% / small=78.6% (single condition・BLOCK でない) |
| §15.2 gate (race_relative) | WARN | sum_p_violation=False・warn_reasons=[] (race-relative 補正で sum(p) 収束) |
| Phase 12 WARN gate | **FAIL (phase12_warn_triggered=True)** | selected-only calib_max_dev=0.272 > 0.100・odds_band[1.0-2.9]=0.363 > 0.150・odds_band[3.0-4.9]=0.164 > 0.150 |
| switch_recommendation | **reject** | SC#4 WARN gate FAIL → reject ルール (D-09)・is_primary DB 変更は人間承認の別アクション (D-10) |
| baseline_recovery_rate | 0.0 | select_bets が投資対象を選ばず (後述) |
| p_lower_recovery_rate | 0.0 | q_shrink=0.332832 が大きく p_fukusho_hit_lower >= p_min=0.15 を満たす馬が皆無 (memory: fukusho-recovery-070-structural-ceiling) |
| usable odds coverage | 22792/22793 (99.996%) | no_bet sentinel は NaN 化・select_odds_snapshot の D-02 未来リーク構造的不可保証 |
| exit code | 0 | END-TO-END 完走・8 ファイル生成 |

**所見 (orchestrator 引き継ぎ)**:
- falsification は skip でなく実際に実行され・market 条件付きでも model_p に α=0.05 で有意な residual が観測された (feature_gap・統計的所見・「モデルが市場を打つ」保証でない)。1.0-2.9 odds band (人気馬) で Holm 補正後も有意な residual が残るのは・人気馬域で model が市場にない情報を捉えている可能性を示唆する。
- 一方・Phase 12 WARN gate は FAIL (selected-only・odds_band 共に過大予測)。q_shrink=0.332832 という大きい shrinkage は calib slice の過大予測の大きさを反映し・p_lower ベースでは p_min=0.15 を超える馬がほぼいない (recovery_rate=0.0)。これは memory: fukusho-recovery-070-structural-ceiling が予言した「複勝回収率〜0.65 天井・閾値では改善しない・Phase 1-B か評価リフレーム」の構造的限界と整合する正直な記録。
- よって switch_recommendation=reject は SC#4 WARN gate FAIL の機械的適用で・core value 維持での黒字化困難を示す。人間承認の別アクション (D-10) として is_primary を切り替えるかは Plan 05 checkpoint で判断する。

### 検証 (gap-closure)

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_run_phase12_evaluation.py tests/model/test_orchestrator_p_lower.py tests/evaluation/ tests/model/test_evaluator_phase12_warn_gate.py`: 75 passed (regression なし)
- `uv run ruff check scripts/run_phase12_evaluation.py`: All checks passed
- AST check: `set_primary_model` の ast.Call node 0件 (D-10 聖域・commit 9da055c 以降も維持)
- live-DB 実行: exit 0・8 ファイル生成 (12-evaluation/falsification/falsification-spec/switch-recommendation/q_shrink の md/json)
- byte-reproducible §19.1: 2 回実行で reports/12-evaluation/*.json 5 ファイルが sha256 完全一致
- falsification は WARNING skip でなく実際に実行 (verdict: feature_gap・model_p_coef/pvalue 実測)

## Self-Check: PASSED

- scripts/run_phase12_evaluation.py: FOUND
- tests/test_run_phase12_evaluation.py: FOUND (12 tests collected)
- reports/12-evaluation/: FOUND (8 files: 12-evaluation.{md,json} / falsification.{md,json} / falsification-spec.json / switch-recommendation.{md,json} / q_shrink.json)
- .planning/phases/12-p-lower-ev-falsification-evaluation/12-04-SUMMARY.md: FOUND
- commit d0881f1: FOUND (feat(12-04): run_phase12_evaluation.py で p_lower EV + falsification 統合評価)
- commit 69cd065: FOUND (fix(12-04): _assert_deterministic に p_lower_q_shrink 伝播)
- commit 9da055c: FOUND (fix(12-04): JODDS odds pipeline 統合 gap-closure bug #1/#2)
- commit fa783bc: FOUND (fix(12-04): JODDS fetch statement_timeout 600s 延長)
- commit 1a97bc6: FOUND (fix(12-04): falsification NaN odds 除外 + recovery_rate 用 label 列伝播)
- KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_run_phase12_evaluation.py: 12 passed
- KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_run_phase12_evaluation.py tests/model/test_orchestrator_p_lower.py tests/evaluation/ tests/model/test_evaluator_phase12_gate.py: 75 passed (regression なし)
- ruff check scripts/run_phase12_evaluation.py: All checks passed
- AST check: set_primary_model Call node 0件 (D-10 聖域)
- live-DB 実行: exit 0・8 ファイル生成・falsification verdict=feature_gap (skip でなく実行)
- byte-reproducible §19.1: 2 回実行で reports/12-evaluation/*.json 5 ファイル sha256 完全一致
