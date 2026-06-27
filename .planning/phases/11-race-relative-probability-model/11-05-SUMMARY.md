---
phase: 11-race-relative-probability-model
plan: 05
subsystem: model
tags: [model, race-relative, wave4, live-db, sc2, sc3, sc5, checkpoint, model-01, safe-01]
requires:
  - "11-01 Wave 0 stub + test 契約"
  - "11-02 Wave 1 race_relative 3関数実装"
  - "11-03 Wave 2 orchestrator theta 統合 + artifact/predict 拡張"
  - "11-04 Wave 3 D-10 adversarial + run_phase11_evaluation.py"
  - "PostgreSQL everydb2 (live-DB)・feature snapshot 20260626-1a-opponentstrength-v1"
provides:
  - "SC#5 §19.1 metadata schema migration (label_version/odds_snapshot_policy/backtest_strategy_version・sentinel 'unspecified'・CHECK 制約 lightgbm_rr/catboost_rr 拡張)"
  - "PREDICTION_TABLE_DDL (CREATE TABLE) への provenance 3列追加 (新規 CREATE TABLE で19列化・再現性§19.1)"
  - "orchestrator.train_and_predict 新3引数 (3層ワイヤリング・sentinel 既定値) + 固定 as_of_datetime=FIXED_REPRODUCE_TS"
  - "run_phase11_evaluation.py: load_predictions public wrapper・NaN-safe θ 選択・honest SC#2 gate 記録"
  - "reports/11-evaluation/{11-evaluation.md,11-evaluation.json,theta-selection.md,theta-selection.json}"
  - "prediction.fukusho_prediction: lightgbm_rr / ...-lgbrr-v1 行 (is_primary=f・v1.0 binary 行保持・D-07)"
affects:
  - "Phase 12 (p_lower EV + falsification): SC#2 gate FAIL の honest 記録が is_primary 切替判断材料 (race-relative model は v1.0 binary を D-04 非劣化・確率精度で改善するも D-05 改善 gate 未達)"
---

# 11-05 SUMMARY — race-relative live-DB checkpoint・SC#2/SC#3/SC#5 実証

## Self-Check: PASSED

3 Task 構成（Task 1/2 auto・Task 3 checkpoint:human-verify）全完了。live-DB（KEIBA_SKIP_DB_TESTS unset）で SC#2 gate・SC#3 bit-identical・SC#5 idempotent swap を実証し・全套 pytest 651 passed / 0 failed を確認。

## 成果

### Task 1（commit 5e6a275）— schema + predict migration
- `src/db/schema.py`: `PREDICTION_ADD_PROVENANCE_SQL`（3列 DEFAULT 'unspecified' sentinel・codex cycle-2 NEW HIGH#3）+ `PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL`（CHECK 制約 lightgbm_rr/catboost_rr 拡張・codex cycle-2 NEW HIGH#1・DROP IF EXISTS + ADD idempotent）
- `src/model/predict.py`: PREDICTION_COLUMNS 3列追記（is_primary の前・Pitfall 4 3ファイル連鎖）・predict_p_fukusho 新3引数（sentinel 既定値）・DataFrame 構築で3列付与
- `tests/model/test_prediction_load.py`: 合成 row helper に3列追加（Rule 3 auto-fix・PREDICTION_COLUMNS 拡張に直接起因）

### Task 2（commit 52af872）— orchestrator + script ワイヤリング
- `src/model/orchestrator.py`: train_and_predict 新3引数（sentinel 既定値・WARNING#2 第1層）・predict_p_fukusho 呼出に3引数伝播（第2層）・return dict に3 provenance・`_assert_deterministic` theta 引数（codex HIGH#8・SC#3）
- `scripts/run_phase11_evaluation.py`: load_predictions public wrapper（codex HIGH#4）・orchestrator 呼出で3引数 + as_of_datetime=FIXED_REPRODUCE_TS（codex cycle-2 NEW HIGH#2）・_assert_deterministic(theta) smoke・set_primary_model Call 0件（D-07・AST check）

### Task 3（commit da0a985）— live-DB human-verify checkpoint・実装不備修正
**live-DB 実証結果（reports/11-evaluation/）:**
- **SC#3 bit-identical: PASS** — θ=1.0 race-relative model で FIXED_REPRODUCE_TS + 固定 seed/thread + np.array_equal で2回 train_and_predict が bit-identical（同一 LightGBM 同一 seed の再現性・cross-family 同一性でない・codex MEDIUM）
- **SC#5 idempotent swap: PASS** — load_predictions public wrapper で2回実行 checksum bit-identical=2af031240e77312f5be62518a98b1929・race-relative 行（lightgbm_rr / ...-lgbrr-v1 / 22793行）追加・v1.0 binary 行（lightgbm / ...-lgb-v1 / is_primary=t / 22213行）保持（D-07）・3 metadata 列が sentinel でなく事前登録値（label_version=v1.0 / odds_snapshot_policy=30min_before / backtest_strategy_version=BT-1・codex HIGH#3）・as_of_datetime=2026-06-20 00:00:00 UTC 固定で PK 一致（codex cycle-2 NEW HIGH#2）
- **SC#2 gate: FAIL（honest 記録・§11.2 聖域・許容幅は変更せず）**
  - D-04 非劣化 gate: **PASS** — Brier -0.00323 / LogLoss -0.01355 / AUC +0.01896（全指標で v1.0 binary 改善）
  - D-05 改善 gate: **FAIL（3条件の論理積）** — (1) overprediction penalty: FAIL（baseline=nan/rr=nan・odds-free 1-A で odds/ninki 無く計算不能・D-15 参考記録）/ (2) selected/high-EV 層: PASS / (3) selected-only calib_max_dev: PASS
  - θ 選択経路: selected θ=1.0（stage1 cutoff n=5→5 / stage2 NaN-safe / stage3 tiebreak θ=1 近傍・§11.2 聖域・test 窓選び直し禁止・theta-selection.json を test 窓評価前に事前書き出し codex HIGH#1）
- **全套 pytest: 651 passed / 5 skipped / 0 failed**（KEIBA_SKIP_DB_TESTS unset・live-DB フルスイート）

## 聖域遵守（core value: リーク防止・再現性）

- **D-01 聖域**: binary 本体（trainer/calibrator/data/evaluator/segment_eval/race_relative/artifact）は全 Phase 11 を通じて不変
- **§11.2 聖域**: θ 選択は score_split='calib' のみ・test 窓は選び直さない（codex HIGH#1）・theta-selection.json を test 窓評価前に byte-reproducible に事前書き出し
- **D-07**: set_primary_model を呼ばない（AST check で Call 0件）・is_primary=true は v1.0 binary（lightgbm）のみ
- **§19.1 再現性**: PREDICTION_TABLE_DDL（CREATE TABLE）に provenance 3列を含め新規 CREATE TABLE で19列化・as_of_datetime=FIXED_REPRODUCE_TS 固定で PK 一致・2回実行で checksum bit-identical
- **codex cycle-2 NEW HIGH#1/#2/#3**: CHECK 制約 lightgbm_rr/catboost_rr 拡張・固定 as_of_datetime・sentinel 既定値（空文字 '' でなく loader 空文字→None 変換回避）すべて live-DB で実証

## codex review HIGHs 対応

| HIGH | 対応 | 実証 |
|------|------|------|
| HIGH#1（θ test 窓聖域） | ✅ | score_split='calib' のみ・theta-selection 事前書き出し |
| HIGH#2（binning import 再利用） | ✅ | evaluator/segment_eval binning 再利用・再定義0件 |
| HIGH#3（§19.1 metadata 3層ワイヤリング） | ✅ | script→orchestrator→predict_p_fukusho→PREDICTION_COLUMNS・live-DB psql で事前登録値確認 |
| HIGH#4（load_predictions public wrapper） | ✅ | private _idempotent_load_prediction 不使用・SC#5 swap PASS |
| HIGH#5（task 順序） | ✅ | Task1→2→3 順で実装が checkpoint に先行 |
| HIGH#8（_assert_deterministic theta） | ✅ | theta=float で bit-identical PASS |
| cycle-2 NEW HIGH#1（CHECK 制約拡張） | ✅ | lightgbm_rr INSERT 可能・psql で確認 |
| cycle-2 NEW HIGH#2（固定 as_of_datetime） | ✅ | FIXED_REPRODUCE_TS で2回実行 checksum bit-identical |
| cycle-2 NEW HIGH#3（sentinel 既定値） | ✅ | DEFAULT 'unspecified'・NOT NULL 違反回避 |

## Deviations（Task 3 live-DB 実行で発見・修正・全て構造的制約による必然的逸脱）

1. **migration 適用経路の変更（PLAN Task 2 action【7】から逸脱）**: PLAN は run_phase11_evaluation.py の etl cursor で migration 実行を指示したが・ALTER TABLE は owner 権限が必要で etl ロールでは `InsufficientPrivilege` となる。Phase 6 idiom（run_apply_schema.py が admin/owner で migration を適用）に従い・run_apply_schema.py の APPLY step リストに prediction_add_provenance / prediction_extend_model_type_domain を追加して一本化・run_phase11_evaluation.py からは migration 実行を削除。
2. **PREDICTION_TABLE_DDL（CREATE TABLE）への provenance 3列追加（Task 1 action【1】漏れの回復）**: Task 1 は ALTER（migration）のみ実装し CREATE TABLE 定義への列追加を漏れていた。test_prediction_columns_matches_ddl_count が正しく検出。CREATE TABLE に provenance 3列を追加し新規 CREATE TABLE で19列化（再現性§19.1）。
3. **stage2 NaN-safe（odds-free 1-A 構造的制約）**: compute_overprediction が odds/ninki 無しで NaN を返す（feature snapshot は odds-free 1-A・D-15 参考記録）。全候補 NaN の場合 D-05-1 条件を skip して passing をそのまま stage2 に流し stage3 tiebreak（calib_max_dev → θ=1 近傍）で決定（§11.2 聖域・test 窓を見ない）。
4. **markdown None-safe**: θ 候補表の overprediction_penalty が NaN→None になるため _fmt helper で "NaN" 表示。
5. **test_is_primary_flag.py regression 修正**: Phase 11 schema 変更（PREDICTION_COLUMNS 19列・provenance・CHECK制約）で9テストが失敗。helper に provenance 追加 + assert 16→19 で全17テスト GREEN。

## Phase 12 引き継ぎ材料

- SC#2 gate FAIL（honest）: race-relative model（θ=1.0）は v1.0 binary を D-04 非劣化（確率精度で改善）するも・D-05 改善 gate の条件1（overprediction penalty）が odds-free 1-A 構造的制約で NaN になり FAIL。Phase 12 で is_primary 切替を見送るか続行するかの判断材料。
- race-relative model 行は prediction.fukusho_prediction に永続化済み（is_primary=f・Phase 12 で切替可能）。
- D-15 overprediction penalty を活かすには odds 情報を予測時に結合する経路（Phase 1-B 以降）が必要。

## 主要ファイルパス

- `/Users/hart/develop/keiba-ai-v3/src/db/schema.py`（PREDICTION_TABLE_DDL provenance 追加・migration 定数）
- `/Users/hart/develop/keiba-ai-v3/src/model/orchestrator.py`（train_and_predict 新3引数・_assert_deterministic theta）
- `/Users/hart/develop/keiba-ai-v3/src/model/predict.py`（PREDICTION_COLUMNS 19列・predict_p_fukusho 新3引数）
- `/Users/hart/develop/keiba-ai-v3/scripts/run_apply_schema.py`（Phase 11 migration step 追加）
- `/Users/hart/develop/keiba-ai-v3/scripts/run_phase11_evaluation.py`（load_predictions・NaN-safe・honest gate 記録）
- `/Users/hart/develop/keiba-ai-v3/tests/db/test_is_primary_flag.py`（provenance 対応・19列）
- `/Users/hart/develop/keiba-ai-v3/reports/11-evaluation/`（SC#2 gate・θ 選択経路・honest 記録）
