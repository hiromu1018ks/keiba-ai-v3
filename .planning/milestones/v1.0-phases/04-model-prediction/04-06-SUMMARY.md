---
phase: 04-model-prediction
plan: 06
subsystem: final-verification-phase-completion
tags: [phase-04, verification, sc3-leak-green, sc4-reproduce-green, sc2-honest, green-by-skip-prevented, roadmap-update, hybrid-gate, both-models-e2e, review-high3, review-high7, review-high8, review-high10]
requires:
  - "Phase 04-01: lightgbm/catboost pin + prediction DDL + RED stubs + v3 ドリフト修正"
  - "Phase 04-02: data.py / calibrator.py / artifact.py (FEATURE_COLUMNS / split_3way / calibrate_model / save_native_artifact)"
  - "Phase 04-03: trainer.py / baseline.py (train_lightgbm / train_catboost / align_predictions / compute_all_baselines + SC#3 leak diagnostic)"
  - "Phase 04-04: predict.py / evaluator.py / prediction_load.py (predict_p_fukusho / evaluate_all_models / load_predictions)"
  - "Phase 04-05: orchestrator.py + run_train_predict.py (train_and_predict 統合 + SC#4 bit-identical + both-models pipeline)"
provides:
  - "Phase 4 完了宣言: SC#3/SC#4 構造的ブロック GREEN（両モデル実データ）・全テスト KEIBA_SKIP_DB_TESTS unset で GREEN（262 passed / 0 skipped）"
  - "prediction.fukusho_prediction 両モデル永続化（lightgbm + catboost 各 22,213 行・model_version スコープ swap）"
  - "reports/04-eval.md + reports/04-eval.json（LightGBM + CatBoost + BL-1..5 比較表 + §15.2 sum(p) 診断）"
  - "models/{version}/ artifact（.gitignore 対象・§19.1 再現は code + uv.lock + snapshot metadata）"
  - "ROADMAP Phase 4 完了 + SC#1-#4 Achievement 証拠（SC#2 2要素分離・SC#3 対抗的構造診断と正確に呼ぶ・SC#4 固定 thread/as_of_datetime）"
  - "STATE.md: Phase 4 complete → Phase 5 (EV & Backtest) 移行"
affects:
  - "Phase 5 (EV & Backtest): prediction.fukusho_prediction 両モデルを SQL 照会し EV/rank + virtual-purchase backtest を実施"
  - "Phase 6 (Evaluation & Calibration Gates): reports/04-eval.{md,json} と D-04 事前登録選定基準（Calibration 重視）で §15.2/§15.3 ゲート最終判定・SC#2 AI 付加価値の最終判定"
  - "Phase 8 (Adversarial Audit): SC#3 leak diagnostic が live-data での target encoding 非混入を別途検証（本 PLAN は対抗的構造診断と明示）"
tech-stack:
  added: []
  patterns:
    - "最終ゲート green-by-skip 防止（review HIGH#10）: KEIBA_SKIP_DB_TESTS unset で全テスト実行し critical テスト（requires_db 38 件）の skipped count == 0 を記録"
    - "SC#2 正直注記パターン（review HIGH#8）: 比較表生成（要素 a）と主モデル vs baselines 具体指標比較（要素 b）を分離・Brier/LogLoss/AUC で AI が勝るが D-04 主要基準 Calibration で BL に劣る場合は『部分証明/未証明』と正直に注記・過大請求防止"
    - "SC#3 対抗的構造診断と正確に呼ぶ（review HIGH#3）: 合成データでの構造実証を live-data 証明と称さず・Phase 8 adversarial audit が live-data 検証を担う旨を明示"
    - "ROADMAP 系統的更新（review HIGH#8/#3/#7）: SC#1-#4 各々に Achieved: PLAN 番号 + test 名 + 生成物の証拠を付記・D-01..D-08 + reviews HIGH 反応を集約"
key-files:
  created:
    - "reports/04-eval.md（成果物・Git 追跡・LightGBM + CatBoost + BL-1..5 比較表 + §15.2 sum(p) 診断 + D-04 事前登録選定基準素材）"
    - "reports/04-eval.json（成果物・Git 追跡・機械処理用 JSON）"
  modified:
    - ".planning/phases/04-model-prediction/04-VALIDATION.md（nyquist_compliant=true / wave_0_complete=true / status=approved / final_gate_run_with_skip_unset=true・全 test 実行証拠格納）"
    - ".planning/ROADMAP.md（Phase 4 [x] 完了・6 plans・SC#1-#4 Achievement 証拠・D-01..D-08 + reviews HIGH 反応集約）"
    - ".planning/STATE.md（status phase-4-complete・current_phase 05・completed_plans 23/23）"
  generated_not_tracked:
    - "models/20260620-1a-postreview-v2-lgb-v1/{lgb_model.txt, calibrator.joblib, metadata.json}（.gitignore・SHA256 記録）"
    - "models/20260620-1a-postreview-v2-cb-v1/{cb_model.cbm, calibrator.joblib, metadata.json}（.gitignore・SHA256 記録）"
    - "prediction.fukusho_prediction テーブル（lightgbm 22,213 行 + catboost 22,213 行）"
decisions:
  - "SC#2 正直注記（review HIGH#8）: 主モデルは Brier/LogLoss/AUC（順序付け性能）で BL-1/BL-4/BL-5 を上回るが・D-04 事前登録の主要基準 Calibration（calibration_max_dev）では BL-1=0.001426・BL-4=0.044928 に劣る（LightGBM=0.230769・CatBoost=0.257893）。事前登録基準（Calibration 重視）の観点では『AI 付加価値 部分証明』・Phase 6 ゲートで最終判定。Phase 4 完了を過大請求しない。"
  - "BL-2/BL-3 市場データ test split で NaN（review HIGH#8 透明性）: test split（2024-H2）で fetch_market_data の ninki/fukuoddslow が取得できておらず・BL-2/BL-3 が NaN。市場データ可用性 gap は genuine data-availability 問題（bug でなく）・Phase 6 で市場データ SELECT 範囲調整を再評価する旨を Phase-6 item として正直に文書化（fake 値での上回り主張はしない）。"
  - "BL-4/BL-5 キャリブレーション（calibrate_bl4_bl5=False）: 04-05 から持ち越し。BL-4/BL-5 の calibrator 経由予測で LightGBM categorical 前処理が走らない問題のため・本 PLAN では未キャリブレーションで評価レポート生成（BL_UNCALIBRATED_NOTE で注記）。Phase 6 で SC#2 比較公平性を再評価。"
  - "green-by-skip 防止（review HIGH#10）: KEIBA_SKIP_DB_TESTS unset で全テスト実行し critical テスト（requires_db マーク 38 件）の skipped count == 0 を 04-VALIDATION.md と reports で記録。final_gate_run_with_skip_unset: true を新規 frontmatter フィールドで明示。"
  - "SC#3 を対抗的構造診断と正確に呼ぶ（review HIGH#3）: test_no_target_encoding_leak は合成データでの構造実証（低基数 RARE_X + 高基数 _code train-only/test-unseen + 意図的リーク制御 DEMONSTRABLY fail）・live-data 証明と称さず・Phase 8 adversarial audit が live-data での別途検証を担う。"
  - "SC#4 固定 thread/as_of_datetime（review HIGH#7）: seed=42 + num_threads=1/thread_count=1 + FIXED_REPRODUCE_TS で両モデル bit-identical を実データで実証（--check-reproduce で exit 0）。"
metrics:
  duration: 35m
  completed: 2026-06-20
  tasks: 2
  files_created: 3
  files_modified: 3
status: complete
---

# Phase 4 Plan 06: Final Verification & Phase 4 Completion Summary

**Phase 4 最終検証と完了宣言: 両モデル実データ E2E（DB 書込 + reports commit）・SC#3/SC#4 構造的ブロック GREEN・全テスト KEIBA_SKIP_DB_TESTS unset で 262 passed / 0 skipped（green-by-skip 防止）・SC#2 正直注記（AI 付加価値 部分証明: Brier/LogLoss/AUC で BL 上回るが D-04 主要基準 Calibration で BL に劣る）・ROADMAP/STATE 更新で Phase 5 引き渡し**

Phase 4 Wave 5 / Plan 06 の完結編として、(a) `scripts/run_train_predict.py --model-type both --check-reproduce` を実データで実行し両モデル（LightGBM + CatBoost）の学習→キャリブレーション→予測→artifact 保存→prediction.fukusho_prediction 書込（model_version スコープ swap）→reports/04-eval.{md,json} 生成を完結・reports をコミット、(b) review HIGH#3 / HIGH#7 対応で SC#3 leak diagnostic と SC#4 reproduce smoke が両モデル実データで GREEN になることを構造的ブロックで確認、(c) review HIGH#10 対応で KEIBA_SKIP_DB_TESTS を unset で最終検証を実行し critical テスト（requires_db 38 件）の skipped count == 0 を確認（green-by-skip 防止）、(d) review HIGH#8 対応で SC#2 を『比較表生成』と『主モデル vs baselines 具体指標比較』の2要素に分離・Brier/LogLoss/AUC で AI が勝るが D-04 主要基準 Calibration で BL に劣る旨を正直に『AI 付加価値 部分証明』と注記、(e) review MEDIUM 対応で 04-VALIDATION.md に各テストのコマンド・終了コード・予測 checksum・artifact SHA256・行数の実行証拠を格納、(f) ROADMAP/STATE を Phase 4 完了で更新し Phase 5（EV & Backtest）への引き渡しを確立した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | 実データ run_train_predict --model-type both --check-reproduce + SC#3/SC#4 構造的ブロック GREEN + 全テスト KEIBA_SKIP_DB_TESTS unset + VALIDATION 実行証拠更新 | `0907729` | reports/04-eval.md, reports/04-eval.json, .planning/phases/04-model-prediction/04-VALIDATION.md |
| 2 | ROADMAP Phase 4 完了更新 + STATE Phase 5 移行 | `d35a244` | .planning/ROADMAP.md, .planning/STATE.md |

## What Was Built / Verified

### Task 1: 両モデル実データ E2E + SC#3/SC#4 GREEN + green-by-skip 防止

**両モデル完全 E2E pipeline（実データ・DB 書込あり）— review HIGH#1/#2/#5/#7**:

- コマンド: `uv run python scripts/run_train_predict.py --model-type both --check-reproduce` → **exit 0**
- feature_df: 552,935 行（label-joined・81 列）
- LightGBM: model_version=`20260620-1a-postreview-v2-lgb-v1` / calib_method=isotonic / pred_rows=22,213 / checksum=`72713b7a54872bba30f354f8e04adf3f`
- CatBoost: model_version=`20260620-1a-postreview-v2-cb-v1` / calib_method=isotonic / pred_rows=22,213 / checksum=`268687d5a8fbc5b36b9cf990574f4e59`
- prediction idempotent verify: 両モデル PASS（2 回目実行で checksum 一致・review HIGH#1 model_version スコープ swap で他 model 破壊せず）
- artifact: base+calibrator 分離保存（review HIGH#5）・models/{version}/{base, calibrator.joblib, metadata.json}
- prediction.fukusho_prediction: lightgbm 22,213 行 + catboost 22,213 行を psql で確認

**SC#3 leak diagnostic GREEN（対抗的構造診断・review HIGH#3）**:

- `uv run pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x -v` → exit 0 / 1 passed in 12.40s
- 構造: 低基数希少カテゴリ RARE_X（両モデル予測が mean ≈0.21 に縮み `< 0.5`）+ 高基数 `_code` 列 train-only/test-unseen ID（global mean に縮む）+ 意図的 target encoding 制御注入（予測 > 0.9 で false-pass でないことを証明）
- GREEN = target encoding 非混入の**対抗的構造実証**（合成データ・live-data 証明と称さない・review HIGH#3）・Phase 8 adversarial audit が live-data で別途検証

**SC#4 reproduce smoke GREEN（固定 thread/as_of_datetime・review HIGH#7）**:

- 単体: `uv run pytest tests/model/test_orchestrator.py::test_reproduce_bit_identical -x -v` → exit 0 / 1 passed in 2.38s
- 実データ: `--check-reproduce` で `SC#4 reproduce smoke PASS (lightgbm)` / `PASS (catboost)` / `全モデル PASS` を出力
- 固定条件: seed=42 + num_threads=1 (lightgbm) / thread_count=1 (catboost) + FIXED_REPRODUCE_TS

**最終ゲート（KEIBA_SKIP_DB_TESTS unset・review HIGH#10: green-by-skip 防止）**:

- コマンド: `unset KEIBA_SKIP_DB_TESTS && uv run pytest`
- 結果: **262 passed, 3 warnings in 315.53s**（2 回目 321.45s）・**0 failed / 0 skipped**
- `uv run pytest -rs` で `^SKIPPED` 行 0 件を確認
- `requires_db` マーク付きテスト（38 件）が全て実行された（KEIBA_SKIP_DB_TESTS unset で skip なし）

**reports/04-eval.{md,json} 生成（Git 追跡・成果物）**:

- LightGBM + CatBoost + BL-1..5 の比較表（Brier / LogLoss / AUC / sum_p_mean / sum_p_median / sum_p_p10 / sum_p_p90 / calibration_max_dev）
- §15.2 sum(p) 診断（診断的閾値 SUM_P_BOUNDS large=[2.7,3.3] small=[1.8,2.2]）
- BL-3 §14.2 注記・BL-4/BL-5 キャリブレーション注記・D-04 事前登録選定基準素材

**04-VALIDATION.md 更新（review MEDIUM: 実行証拠格納）**:

- frontmatter: `status: approved` / `nyquist_compliant: true` / `wave_0_complete: true` / 新規 `final_gate_run_with_skip_unset: true`
- Per-Task Verification Map: 全 13 test ✅ GREEN・Task ID（PLAN 番号）埋込済み・各 test に実行証拠（コマンド / 終了コード / checksum / SHA256 / 行数）を格納
- "Final Gate Execution Evidence" セクション新設: SC#3 / SC#4 / 両モデル E2E / prediction テーブル / artifact SHA256 / reports SHA256 / 最終ゲート / SC#2 比較表の各証拠を集約
- Validation Sign-Off: 6 項目 + final_gate_run_with_skip_unset の全てにチェック

### Task 2: ROADMAP Phase 4 完了 + STATE Phase 5 移行

**ROADMAP.md Phase 4 エントリ**:

- トップレベル: `[x] **Phase 4: Model & Prediction** ... (completed 2026-06-20)`
- `**Plans**: 6 plans`（5/6 → 6 plans）・全 6 PLAN が checked
- **SC#1-#4 Achievement Evidence**（review HIGH#8/#3/#7）:
  - SC#1: PLAN 01-02・test_load_from_parquet_only / test_raw_ids_excluded / test_no_banned_features GREEN・models/{version}/ artifact 生成
  - **SC#2 2要素分離（review HIGH#8）**: (a) 比較表生成済み (b) AI 付加価値 部分証明 — Brier/LogLoss/AUC で BL 上回るが D-04 主要基準 Calibration で BL-1/BL-4 に劣る・Phase 6 ゲートで最終判定
  - SC#3: PLAN 03・**対抗的構造診断**（review HIGH#3: live-data 証明と称さず）・test_no_target_encoding_leak GREEN
  - SC#4: PLAN 02/05・test_reproduce_bit_identical GREEN（固定 thread count + 固定 as_of_datetime・review HIGH#7）・run_train_predict --check-reproduce 両モデル bit-identical
- Locked decisions D-01..D-08 全て実装 + reviews HIGH#1..#12 + actionable MEDIUM/LOW 対応の集約
- 実行生成物（Phase 5 引き渡し）の明記

**STATE.md**:

- frontmatter: `current_phase: 05` / `current_phase_name: ev-backtest` / `status: phase-4-complete` / `completed_plans: 23/23` / `percent: 56`
- Current Position: Phase 4 COMPLETE・Phase 5 (EV & Backtest) ready to plan
- Performance Metrics: `Phase 04 P06 | 18m | 2 tasks | 5 files` 追記
- Session Continuity: Phase 4 complete の停止位置

## SC#2 Honest Comparison（review HIGH#8 — AI 付加価値の正直評価）

reports/04-eval.md の比較表（実測値）:

| model_name | brier | logloss | auc | sum_p_mean | calibration_max_dev |
| --- | --- | --- | --- | --- | --- |
| lightgbm | **0.152216** | **0.474883** | **0.732295** | 3.041678 | 0.230769 |
| catboost | 0.154529 | 0.482434 | 0.718001 | 3.067278 | 0.257893 |
| bl1 | 0.169530 | 0.521015 | 0.573953 | 2.958365 | **0.001426** |
| bl2 | NaN | NaN | NaN | NaN | NaN |
| bl3 | NaN | NaN | NaN | NaN | NaN |
| bl4 | 0.168700 | 0.518246 | 0.601986 | 3.246690 | 0.044928 |
| bl5 | 0.167097 | 0.513048 | 0.619879 | 3.107942 | 0.343709 |

- **Brier / LogLoss / AUC（順序付け性能）**: 主モデル（LightGBM/CatBoost）が BL-1/BL-4/BL-5 を上回る（LightGBM が最良）。
- **Calibration（D-04 事前登録の主要選定基準）**: 主モデル calibration_max_dev 0.230769 / 0.257893 に対し・BL-1=0.001426（constant 予測）・BL-4=0.044928（未キャリブレーション）が低位。**主モデルは calibration_max_dev で BL-1/BL-4 より劣る**。
- **結論**: Brier/LogLoss/AUC では AI モデルが baselines を上回るが・D-04 事前登録の主要基準である Calibration では BL-1/BL-4 に劣る。事前登録基準（Calibration 重視）の観点からは **「AI 付加価値 部分証明」** と正直に注記する（Phase 6 ゲートで最終選定基準を適用して最終判定）。Phase 4 完了を過大請求しない。

## Deviations from Plan

### Auto-fixed Issues

None — PLAN は計画通りに実行された。全ての前提（Wave 1-4 完了・tests/model/ 37 passed・LGB artifact 04-05 で生成済・CatBoost E2E 未完・DB 未書込）が整っており・Task 1 の E2E 実行・Task 2 の ROADMAP/STATE 更新ともに追加 auto-fix なしで完結した。

### Carried-forward from 04-05（計画通り close）

| 04-05 Deferred Item | 04-06 での対応 | 結果 |
| ---- | ---- | ---- |
| 両モデル完全 E2E + DB 書込 + reports コミット | Task 1 で `--model-type both --check-reproduce` 実行・reports をコミット（commit `0907729`） | **CLOSED** — lightgbm + catboost 各 22,213 行永続化・reports コミット済 |
| BL-2/BL-3 市場データ merge が空（test split で NaN） | 調査: 市場データ SELECT 範囲と test split（2024-H2）の整合性を確認・genuine data-availability gap（bug でない）と判定 | **Phase-6 item として正直文書化**（fake 値での上回り主張はしない） |
| BL-4/BL-5 キャリブレーション（calibrate_bl4_bl5=False） | 04-06 でも有効化せず・BL_UNCALIBRATED_NOTE で注記継続 | **Phase-6 item として正直文書化**（比較公平性は Phase 6 で再評価） |

## Verification Results

### 最終ゲート（KEIBA_SKIP_DB_TESTS unset・review HIGH#10）

```
$ unset KEIBA_SKIP_DB_TESTS && uv run pytest
================= 262 passed, 3 warnings in 315.53s (0:05:15) =================
```

- `uv run pytest -rs`: `^SKIPPED` 行 0 件（critical テスト skipped count == 0）
- `requires_db` マーク付きテスト: 38 件・全て実行（skip なし）

### SC#3 / SC#4 構造的ブロック（review HIGH#3 / HIGH#7）

- SC#3: `test_no_target_encoding_leak` → 1 passed in 12.40s（対抗的構造診断・合成データ）
- SC#4: `test_reproduce_bit_identical` → 1 passed in 2.38s（両モデル bit-identical）
- 実データ: `--check-reproduce` で両モデル PASS・exit 0

### tests/model/ quick subset

```
$ uv run pytest tests/model/ -q
37 passed, 3 warnings in 26.27s
```

### prediction.fukusho_prediction テーブル（両モデル永続化）

```
 model_type |          model_version           | count
------------+----------------------------------+-------
 catboost   | 20260620-1a-postreview-v2-cb-v1  | 22213
 lightgbm   | 20260620-1a-postreview-v2-lgb-v1 | 22213
```

### artifact SHA256（.gitignore 対象・§19.1 再現は code + uv.lock + snapshot metadata）

```
ce769f0c...  models/20260620-1a-postreview-v2-lgb-v1/lgb_model.txt
c28ef8dc...  models/20260620-1a-postreview-v2-lgb-v1/calibrator.joblib
076374a3...  models/20260620-1a-postreview-v2-lgb-v1/metadata.json
0897735a...  models/20260620-1a-postreview-v2-cb-v1/cb_model.cbm
f7cde828...  models/20260620-1a-postreview-v2-cb-v1/calibrator.joblib
4140ad5e...  models/20260620-1a-postreview-v2-cb-v1/metadata.json
```

### reports/04-eval.{md,json} SHA256（Git 追跡）

```
98d6b17d...  reports/04-eval.md
8b668dfa...  reports/04-eval.json
```

### ROADMAP/STATE grep 検証

- `grep -c '04-0[1-6]-PLAN.md' .planning/ROADMAP.md` == 6 ✓
- `grep -q 'Achieved: PLAN' .planning/ROADMAP.md` ✓
- `grep -q 'status: phase-4-complete' .planning/STATE.md` ✓
- `grep -c '対抗的構造診断' .planning/ROADMAP.md` == 3（SC#3 記載が対抗的構造診断と正確に呼ぶ）✓
- `grep -c 'FIXED_REPRODUCE_TS\|固定 thread' .planning/ROADMAP.md` == 3（SC#4 固定 thread/as_of_datetime 記載）✓

## TDD Gate Compliance

本 PLAN は type="execute"・tdd なし。Task 1 は検証タスク（実行証拠収集）・Task 2 は文書更新。両タスクとも `<automated>` verify と acceptance criteria grep で完了確認。

## Known Stubs

本 PLAN で新規に作成した stub なし。Phase 4 全 PLAN を通じて残存する stub なし。

## Deferred Issues（Phase 5 / Phase 6 引き渡し）

| Issue | Description | 対応 Phase |
| ---- | ---- | ---- |
| BL-2/BL-3 市場データ test split で NaN | test split（2024-H2）で fetch_market_data の ninki/fukuoddslow が取得できておらず・BL-2/BL-3 が NaN。genuine data-availability gap（bug でない）。市場データ SELECT の year/dataset 範囲調整が必要。 | Phase 6（SC#2 比較公平性再評価） |
| BL-4/BL-5 キャリブレーション（calibrate_bl4_bl5=False） | BL-4/BL-5 の calibrator 経由予測で LightGBM categorical 前処理が走らない問題（baseline.py 制約）。本 PLAN では未キャリブレーションで評価レポート生成（BL_UNCALIBRATED_NOTE 注記）。 | Phase 6（比較公平性再評価） |
| SC#2 AI 付加価値 最終判定 | D-04 事前登録の主要基準（Calibration 重視）で主モデルが BL-1/BL-4 に劣るため『部分証明』。Phase 6 ゲートで §15.2/§15.3 受入基準と D-04 選定基準を適用して最終判定。 | Phase 6（Evaluation & Calibration Gates） |
| SC#3 live-data target encoding 検証 | 本 PLAN の test_no_target_encoding_leak は合成データでの対抗的構造診断。live-data での target encoding 非混入の別途検証。 | Phase 8（Adversarial Audit Suite） |
| data.py build_training_frame の既存 ruff 違反（E741 `l` / F841 `n_before`） | PLAN 02 の既存コード・Phase 4 スコープ外。 | 別途 follow-up |

## Threat Flags

本 PLAN で新規作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている:

- T-04-32 (Repudiation: SC#3/SC#4 silent skip で GREEN 扱い): mitigate・KEIBA_SKIP_DB_TESTS unset で critical テスト skipped count == 0 を記録（review HIGH#10）・--check-reproduce 失敗で sys.exit(1)・SC#3 は対抗的構造診断と正確に呼ぶ（review HIGH#3）
- T-04-32b (Repudiation: SC#3 を live-data 証明と過大請求): mitigate・SC#3 記載を『対抗的構造診断（合成データ）』に統一・Phase 8 が live-data 検証を担う旨を明示
- T-04-32c (Repudiation: SC#2 比較表だけで AI 付加価値宣言): mitigate・SC#2 を 2 要素（比較表生成 + 具体指標比較）に分離・Calibration で BL に劣る場合は『部分証明』と正直注記（review HIGH#8）
- T-04-33 (Tampering: 実データ pipeline 部分失敗で破損予測が Phase 5 に渡る): mitigate・load_predictions staging-swap atomic・model_version スコープで他 model 破壊しない（review HIGH#1）・2 回実行 checksum 一致
- T-04-34 (Repudiation: ROADMAP/STATE ドリフト再発): mitigate・Edit scoped replacement のみ・SC 達成根拠（PLAN 番号 + test 名 + 生成物）を明記
- T-04-35 (Information Disclosure: 実行ログへの生 DSN 出力): mitigate・run_train_predict の masked DSN ログ・本 PLAN でも生 DSN 出力なし
- T-04-36 (Tampering: D-04 事前登録選定基準を結果見てすり替え): mitigate・reports/04-eval.md の comment 列で「Calibration 重視」を結果前に固定・Phase 6 ゲートですり替え検知

新たなセキュリティ表面の追加は無い。

## Self-Check: PASSED

- FOUND: reports/04-eval.md（Git 追跡・SHA256 98d6b17d...）
- FOUND: reports/04-eval.json（Git 追跡・SHA256 8b668dfa...）
- FOUND: .planning/phases/04-model-prediction/04-VALIDATION.md（nyquist_compliant: true / wave_0_complete: true / status: approved / final_gate_run_with_skip_unset: true）
- FOUND: .planning/ROADMAP.md（Phase 4 [x] checked・6 plans・SC#1-#4 Achievement 証拠）
- FOUND: .planning/STATE.md（status: phase-4-complete・current_phase: 05・completed_plans: 23/23）
- FOUND: commit 0907729（Task 1: reports + VALIDATION）
- FOUND: commit d35a244（Task 2: ROADMAP + STATE）
- FOUND: prediction.fukusho_prediction（lightgbm 22,213 行 + catboost 22,213 行・psql で確認）
- FOUND: models/20260620-1a-postreview-v2-lgb-v1/{lgb_model.txt, calibrator.joblib, metadata.json}（.gitignore 対象・SHA256 記録）
- FOUND: models/20260620-1a-postreview-v2-cb-v1/{cb_model.cbm, calibrator.joblib, metadata.json}（.gitignore 対象・SHA256 記録）
