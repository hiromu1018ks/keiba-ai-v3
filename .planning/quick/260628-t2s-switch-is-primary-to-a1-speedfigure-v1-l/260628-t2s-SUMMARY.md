---
quick_id: 260628-t2s
slug: switch-is-primary-to-a1-speedfigure-v1-l
status: complete
date: 2026-06-28
---

# ステップ2: is_primary 切替 → A1（speedfigure-v1・binary・v1.1.0）+ 切替後 BT + segment dump

## 概要

Spike 001 で黒字化の正解と確定した A1（snapshot 20260625-1a-speedfigure-v1・LightGBM binary・label v1.1.0）を新 universe v1.1.0 の主モデル（is_primary）に切り替え・切替後バックテストで検証。Phase 4 標準窓で postreview-v2 との直接比較も実施（交代正当性確認）。

## 実行結果

### 手順1: A1 予測生成 + 保存 + idempotent 検証
- `scripts/save_primary_prediction.py` 新設（run_train_predict.py は SNAPSHOT_PATH 固定で A1 扱えず・run_ablation chain 流用）。
- model_version=`20260625-1a-speedfigure-v1-lgb-v1`・pred_rows=18737（Phase 4 標準 test 2024下期・label v1.1.0）・calib=isotonic・as_of=FIXED_REPRODUCE_TS。
- **idempotent verify PASS**: checksum `926aa1ddd82325c5b01d40abdfe62b58`（2回実行で bit-identical）。

### 手順2: is_primary 切替（D-10 人間承認）
- `scripts/switch_primary_model.py`（--dry-run → AskUserQuestion 承認 → --confirm）。
- Step1 `set_primary_model(A1)` → A1=True（post-condition REVIEW HIGH#7 pass）・Step2 UPDATE postreview-v2-lgb → False。
- **受入基準1 PASS**: A1 のみ is_primary=True（他 model_version 全て False）。

### 手順3: 切替後 BT-1..5（Spike 001 一致・byte-reproducible）
- BT-1=1.0459 / BT-2=1.1781 / BT-3=1.0916 / BT-4=1.1735 / BT-5=1.1921（5窓全て Spike 001 と完全一致・n_selected/hit/P/L も一致）。
- **受入基準3 PASS**: is_primary 切替の副作用無し。

### 手順3b: Phase 4 標準窓（test 2024下期）A1 vs postreview-v2 比較（ユーザー指示）
- A1=1.176195（+33900）vs postreview-v2=0.766284（-40690）→ **差 +0.41 → A1 交代正当**。
- 同じ universe（pred_rows=18737 同一・両 snapshot は speed fig 列の有無のみ差）で FEATURE 差の純粋比較。

### 手順4: segment dump（ステップ3 精査用）
- `.planning/debug/a1-primary/full_candidate_BT-{1..5}-*.parquet`（5窓・30列・race_key で n_race join 可能）。
- **受入基準4 PASS**。

## 受入基準（全 PASS）

1. ✅ A1 が is_primary=True（他は False）
2. ✅ load_predictions idempotent（checksum 一致）
3. ✅ 切替後 BT-1..5 が Spike 001 と完全一致
4. ✅ full_candidate dump 5窓分・segment 精査可能

## 聖域遵守（core value）

- D-10: is_primary 切替は人間承認の別アクション（AskUserQuestion で承認取得）。
- odds-free(SAFE-01) / PIT-correct / byte-reproducible(seed=42・thread=1・FIXED_REPRODUCE_TS)。
- H1-b: snapshot_id=A1 で FEATURE_COLUMNS 選択（speed fig 誤使用防止）。
- Phase 11/12 凍結維持（reopen せず）。

## 成果物

- `scripts/save_primary_prediction.py` / `scripts/switch_primary_model.py` / `scripts/compare_phase4_window.py`
- `reports/12-evaluation/step2-is-primary-a1-switch.md`（実行記録・詳細）
- `reports/12-evaluation/ablation-a1-bt{1..5}-postswitch.json` / `phase4-window-a1-vs-postreview-v2.json`
- `.planning/debug/a1-primary/full_candidate_BT-{1..5}-*.parquet`（ステップ3 segment 精査用）

## 次ステップ

ステップ3（A1 の segment 精査）: `.planning/debug/a1-primary/` の dump（race_key → n_race join で jyocd/距離/class/重賞/人気 を付与）で、odds band・競馬場・クラス・重賞・月/季節別の回収率・的中率・選抜数・P/L を分析。
