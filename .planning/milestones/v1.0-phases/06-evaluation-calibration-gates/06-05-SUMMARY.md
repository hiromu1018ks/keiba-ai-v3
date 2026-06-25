---
phase: "06"
plan: "05"
subsystem: evaluation-calibration-gates
tags: [evaluation, calibration, model-selection, reproducibility, cli]
requires:
  - 06-02 (segment 6軸評価基盤)
  - 06-03 (race_id disjoint 再検証)
  - 06-04 (is_primary migration 機構・set_primary_model)
provides:
  - scripts/run_evaluation.py (統合評価 CLI・EVAL-01/02/03 + D-07 主モデル確定)
  - reports/06-evaluation.{md,json} (受入ゲート判定 + 主モデル比較表 + D-07 選定記録)
  - reports/06-segments/{axis}.{json,html}×6軸 (segment 安定性)
  - prediction.fukusho_prediction.is_primary = true (model_type=lightgbm, snapshot=20260620-1a-postreview-v2)
affects:
  - ROADMAP Phase 6 (SC#1/2/3 達成確定)
  - Phase 7 (Presentation) への primary model 引き渡し
tech-stack:
  added: []
  patterns:
    - "make_model_version 正規採番の全経路統一（手動 [:3] 推測は DB 実値と不整合 → Rule 1 bug）"
    - "byte-reproducible reports 生成（sort_keys + ensure_ascii=False + atomic write）"
    - "set_primary_model post-condition assert (REVIEW HIGH#7: 0-row UPDATE → RuntimeError fail-loud)"
key-files:
  created:
    - reports/06-evaluation.md
    - reports/06-evaluation.json
    - reports/06-segments/{entry_count,jyocd,month,ninki,odds_band,year}.{json,html}
  modified:
    - scripts/run_evaluation.py
    - tests/model/test_run_evaluation.py
decisions:
  - "D-07 主モデル選定: lightgbm（D-04 Calibration 重視の事前登録基準・全指標で CatBoost を上回る・D-08 tiebreak backtest_recovery_rate 0.7022 vs 0.6808）"
  - "D-08 tiebreak 発火段階: backtest_recovery_rate（brier/logloss/auc/calibration_max_dev/monotonicity は LightGBM 勝ち・最終段 backtest 回収率で決定）"
  - "sum(p) threshold 0.30 は維持（threshold_appropriate=False・71% violation で厳格すぎるが SC#2 通過のため WARN のまま・後続 Phase で再検討）"
  - "model_version 推測は make_model_version に一本化（[:3] 手動推測禁止・Rule 1）"
metrics:
  duration: "41 min (全 checkpoint/resume 含む) / 26 min (本継続部分)"
  completed: "2026-06-23"
  tasks: 2
  files: 4 (scripts/run_evaluation.py + tests + reports MD/JSON + segments 12)
  tests: "128 passed, 1 skipped (C6 stale: 04-eval.json calibration_max_dev_guarded 列不存在・期待 skip)"
status: complete
---

# Phase 06 Plan 05: run_evaluation.py 統合評価 CLI + D-07 主モデル確定 Summary

D-04 事前登録選定基準（Calibration 重視）に基づき LightGBM を主モデルに確定し、`prediction.fukusho_prediction.is_primary` を model_version scoped で設定。受入ゲート判定（WARN / SC#2 達成）・主モデル比較表・segment 6軸安定性を `reports/06-evaluation.{md,json}` + `reports/06-segments/` に byte-reproducible で生成する統合評価 CLI。

## 目的

Phase 6 の最終成果物として、Phase 4（model metrics）+ Phase 5（backtest）の結果を統合し：

1. **EVAL-01/02/03**: 受入ゲート（Brier/LogLoss/calibration/sum(p)/stability）判定
2. **SC#1/2/3**: 主モデルが全 baseline（BL-1/BL-4/BL-5）で Brier+LogLoss に勝つ（SC#2）等の達成確認
3. **D-07 主モデル確定**: 人間判断で `--primary-model lightgbm` を指定し、理由（selection_reason）+ tiebreak_applied を記録
4. **is_primary フラグ UPDATE**: `set_primary_model`（06-04 で実装）経由で live DB を更新

## タスク

### Task 1: scripts/run_evaluation.py 新規 + E2E テスト（commit 21dd136）

`run_evaluation.py`（Step 1-7 パイプライン）と `tests/model/test_run_evaluation.py`（10 E2E テスト）を新規作成。Step 構成：

- Step 1: 成果物読込（prediction/label/market/split_integrity・pure functions）
- Step 2-4: EVAL-01/02/03 + SC#1/2/3 判定 → gate_verdict（BLOCK/WARN）
- Step 5: reports atomic write（REVIEW HIGH#6: BLOCK 時は reports 書込 *後* に RuntimeError）
- Step 6: recommended_primary_model 表（REVIEW C7: --primary-model 省略時は提示のみ）
- Step 7: `--primary-model` 指定時 `set_primary_model` で is_primary UPDATE

### Task 1-fix: schema 不整合 + sum(p) 二重計上 bug 修正（commit 0e32634・Rule 1/3）

実データ実行で発覚：
- **Rule 3（blocking）**: prediction schema の `jyocd` 列名差異・market JOIN 経路の型不整合
- **Rule 1（bug）**: sum(p) large/small 測定で同一 race_id の行が二重計上される集計 bug

### Task 2 前半: 実データ reports-only 生成（commit 337be7c）

`--primary-model` 省略で reports のみ生成（byte-reproducible 検証済み・checkpoint:human-verify 前半）。gate_verdict=WARN / block_triggered=false。

### Task 2 後半（本継続）: D-07 primary=lightgbm 確定 + is_primary UPDATE

checkpoint 解決後、`--primary-model lightgbm` を指定して実行。本継続で 2 件の Rule 1 bug を発見・修正。

## 主な決定事項

### D-07: 主モデル = lightgbm

D-04 事前登録選定基準（Calibration 重視）で LightGBM を選定。全指標で CatBoost を上回る：

| 指標 | LightGBM | CatBoost | 勝者 |
|------|----------|----------|------|
| brier | 0.15222 | 0.15453 | LightGBM |
| logloss | 0.47488 | 0.48243 | LightGBM |
| auc | 0.73230 | 0.71800 | LightGBM |
| calibration_max_dev | 0.231 | 0.258 | LightGBM |
| monotonicity (spearman) | 1.0 | 0.9833 | LightGBM |
| backtest_recovery_rate | 0.7022 | 0.6808 | LightGBM |

**selection_reason（D-07）:** "D-04 Calibration 重視の事前登録基準で LightGBM を選定（brier/logloss/auc + calibration_max_dev + monotonicity spearman + backtest 回収率 の全指標で CatBoost を上回る・D-08 tiebreak: backtest_recovery_rate 0.7022 vs 0.6808）"

### D-08: tiebreak 発火段階 = backtest_recovery_rate

優先順位表の全段で LightGBM が勝利したため、最終段の backtest 回収率が tiebreak として記録された（実質的には全段一致だが、最後の決定段として記録）。

### sum(p) threshold 0.30 は維持（threshold_appropriate=False）

`sum_p_measurement.threshold_appropriate = False`（71% violation・0.30 は厳格すぎる）。しかし SC#2（LightGBM beats all baselines on Brier+LogLoss）は達成済みで gate_verdict=WARN / block_triggered=false のため、本 Phase では threshold 変更せず WARN のままとする。後続 Phase（または再検討）で 0.30 の経験的根拠を見直す候補として記録。

## 受入ゲート判定

- **gate_verdict:** WARN
- **block_triggered:** false
- **SC#2 達成:** LightGBM が BL-1/BL-4/BL-5 全てで Brier + LogLoss に勝利
- **SC#1/SC#3:** PLAN 01/03 で別途達成済み

## byte-reproducibility 検証

同一引数での 2 回連続実行で MD/JSON の MD5 が完全一致（Core Value §19.1 準拠）：

- `reports/06-evaluation.md` MD5 = `77561d4541d6f795a77e13a9c782932b`
- `reports/06-evaluation.json` MD5 = `bb265ea228e22a4c6215557bd3a44081`

（`selection_reason` テキストが異なると MD5 は変わる = 期待動作。同一引数での再現性が Core Value の要求。）

## is_primary フラグ検証（live DB）

```
model_type | rows  | any_primary
catboost   | 22213 | False
lightgbm   | 22213 | True
primary model_types: ['lightgbm']
```

- lightgbm 22213 行: is_primary=true（D-07 選定反映）
- catboost 22213 行: is_primary=false（リセット・行は保持・silent 履歴破壊なし）
- primary model_type は lightgbm のみ（set_primary_model post-condition 適合）

## Plan からの逸脱

### Auto-fixed Issues

**1. [Rule 1 - Bug] model_version 推断偏差を修正（commit 86afe9f）**

- **発見場所:** Task 2 後半（`--primary-model lightgbm` 実行時）
- **問題:** `run_evaluation.py` は `primary_model[:3]` で model_version を手動推測していたが、"lightgbm"→"lig" となり DB 実値（`-lgb-v1`・`make_model_version` の `MODEL_TYPE_TO_SHORT` による）と不整合。結果として `set_primary_model` の WHERE が 0 行となり RuntimeError（REVIEW HIGH#7 post-condition が正しく検知）。
- **修正:** `scripts/run_evaluation.py` の両箇所（L1014 primary_model_record 生成・L1306 set_primary_model 呼出）を `make_model_version(feature_snapshot_id, model_type, version_n=1)` に置換。
- **副次修正:** `tests/model/test_run_evaluation.py` の fixture も同一の `[:3]` 偏差を内包していたため、`MODEL_TYPE_TO_SHORT` と同一の `_short_model()` ヘルパーで生成するよう修正（テストが本 bug を検知できるように）。既存 E2E テスト 10 個は set_primary_model を mock していたため検知できていなかった。
- **ファイル:** scripts/run_evaluation.py, tests/model/test_run_evaluation.py
- **コミット:** 86afe9f

**2. [Rule 3 - Blocking] as_of_datetime 引数と DB 実値の不一致**

- **発見場所:** Task 2 後半
- **問題:** resume_instructions が指定した `--as-of-datetime 2026-06-20T00:00:00Z` は DB 実値（prediction 実行時刻 `2026-06-20T20:13:33.368966`）と不一致 → set_primary_model WHERE が 0 行。
- **修正:** DB 実値 `2026-06-20T20:13:33.368966` を指定して再実行。これは run_evaluation.py の bug ではなく引数指定の問題（prediction_load が実行時刻を as_of_datetime として記録する挙動）。本 Phase では引数を実値に合わせることで対応。
- **コミット:** dcf66f6（reports 更新に含む）

### 手動チェックポイント

- **checkpoint:human-verify（D-07 主モデル選定）:** 解決済み。人間が lightgbm を選択（selection_reason + D-08 tiebreak 指示）。本継続で反映完了。

## Known Stubs

なし。全ての report が実データ（prediction 44426 行 / label 554267 行 / market 554232 行）から生成され、mock/placeholder なし。

## 脅威フラグ

なし。本 Phase は評価・フラグ更新のみで新規ネットワークエンドポイント・認証経路・ファイルアクセスパターンの追加なし。

## 自己チェック: PASSED

- FOUND: scripts/run_evaluation.py（model_version 修正済み）
- FOUND: tests/model/test_run_evaluation.py（fixture 修正済み）
- FOUND: reports/06-evaluation.md / reports/06-evaluation.json（D-07 選定反映済み）
- FOUND: reports/06-segments/×6軸
- FOUND: commit 21dd136 / 0e32634 / 337be7c / 86afe9f / dcf66f6（全て git log に存在）
- live DB is_primary 検証済み（lightgbm=true / catboost=false・両モデル行保持）
