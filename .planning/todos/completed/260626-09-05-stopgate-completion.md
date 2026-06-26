---
title: "Phase 9 09-05 SC#6 stop gate 完全化（label/market/refund/payout 統合）"
priority: high
created: 2026-06-26
related_phase: "09"
related_plan: "09-05"
resolves_phase: "9.1"
tags: [stop-gate, sc6, phase5-integration, label, market, refund]
---

# Phase 9 09-05 SC#6 stop gate 完全化

## 背景

Phase 9 09-05 は部分完了（学習通過確認済み）。stop gate スクリプト（`scripts/run_speed_figure_stopgate.py`）が Phase 5（`run_backtest.py`）の label/market/refund/payout 統合 idiom を不十分に実装しており、実行時に bug が連鎖した。

## 完了済み（再利用可）

- スクリプト本体 + 合成テスト 9 tests GREEN（H2/H7/H8/H6/H-new/M4 全対応）
- baseline / speed_figure snapshot 両方生成済み（baseline `20260620-1a-postreview-v2` + speed_figure `20260625-1a-speedfigure-v1` MMSS.t 修正版）
- 両 snapshot で `train_and_predict` 学習通過確認（model_version 採番成功・calibration pipeline 完走）
- JODDS 2023 test 窓 market データ JOIN 成功（rows=22793）

## 修正済み bug（参考）

| bug | commit |
|-----|--------|
| BT1_PERIODS に calib 欠落 | 1c0c405 |
| `select_odds_snapshot` 署名誤認（fetch_jodds/race_times なし） | 173d727 |
| `umaban` 型不一致（str vs Int64） | ccb51f2 |

## 残作業（本 todo のスコープ）

1. **pred_df へ label JOIN**: `train_and_predict` の pred_df は `p_fukusho_hit + test index` のみで label（`fukusho_hit_validated`）を保持しない。`feature_df`（build_training_frame 戻り・label 含む）から pred_df に label 列を JOIN（index or race_key+umaban）。
2. **refund_accounting 統合**: `determine_stake_payout`（src/ev/refund_accounting）で payout/effective_stake を算出。non-selected 会計ゼロ化（Phase 5 MEDIUM cycle-3）。
3. **D-14 指標 2（selected ROI）/ 4（market disagreement）+ D-15 residual proxy 算出**: market_implied（`1.0 / fuku_odds_lower`）・model_p の分位 bucket・D-16 verdict。
4. **完全 stop gate 実行**: `reports/09-stopgate.{md,json}` 生成・D-16 判定（構造的限界寄り or Phase 10 進行候補）・checkpoint:human-verify。

## 参照

- Phase 5 idiom: `scripts/run_backtest.py`（label/market/refund/payout 統合の正典・L448 `_build_race_times_per_horse` / L788-794 umaban 型統一 / `determine_stake_payout` / `compute_backtest_metrics`）
- 09-05 PLAN: `.planning/phases/09-speed-figure-foundation/09-05-PLAN.md`
- 許容幅: Brier +0.005 / LogLoss +0.02 / AUC -0.005（RESEARCH.md Open Questions RESOLVED #2・Phase 11 SC#2 と同一スケール前提）
