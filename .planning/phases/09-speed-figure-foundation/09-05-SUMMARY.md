---
phase: 09-speed-figure-foundation
plan: 05
status: partial — 学習通過確認済み・SC#6 指標算出（D-14/15/16）は別タスクで完全化
requirements: [FEAT-01]
---

# 09-05 SUMMARY — SC#6 stop gate（部分完了・完全化は別タスク）

## 達成

### スクリプト + 合成テスト（DB 不要・9 tests GREEN）
`scripts/run_speed_figure_stopgate.py`（750+行）+ `tests/model/test_speed_figure_stopgate.py`（9 tests GREEN）:
- **REVIEW H2/H7/H8**: `orchestrator.train_and_predict` 経由・生 trainer 直接呼出禁止（AST guard）
- **REVIEW H-new**: 両 snapshot の `train_and_predict` 呼出に `snapshot_id=` keyword を明示渡し（AST guard・silent "v1.0 vs v1.0" 比較を閉塞）
- **REVIEW H6**: `market_implied = 1.0 / fuku_odds_lower`（誤略称 `fukuodds` でない）
- **REVIEW M4**: `_sanitize_for_json` で NaN/Inf 安全化・`json.dumps(allow_nan=False)` RFC 8259 strict
- **§15.2 事前登録指標不変**: `CALIBRATION_CURVE_BINS` / `ODDS_BAND_EDGES` 等を import 再利用（再定義禁止・AST 証明）

### 学習通過確認（live-DB）
- baseline `20260620-1a-postreview-v2-lgb-v1` / speed_figure `20260625-1a-speedfigure-v1-lgb-v1` の model_version 採番成功
- 両 snapshot で `train_and_predict` が calibration pipeline 完走（H2/H7/H8 回避確認）
- JODDS 2023 test 窓 market データ JOIN 成功（rows=22793・snapshot=22793）

## 未完了（別タスクで完全化）— SC#6 指標算出 D-14/15/16

09-05 スクリプトは Phase 5（run_backtest.py）の label/market/refund/payout 統合 idiom を不十分に実装しており、実行時に bug が連鎖した:

| bug | 状態 | commit |
|-----|------|--------|
| BT1_PERIODS に calib 欠落（split_3way KeyError） | ✅ 修正 | 1c0c405 |
| `select_odds_snapshot` 署名誤認（fetch_jodds/race_times なし） | ✅ 修正 | 173d727 |
| `umaban` 型不一致（str vs Int64・merge ValueError） | ✅ 修正 | ccb51f2 |
| **pred_df に label（`fukusho_hit_validated`）不在** | ❌ 未修正 | — |

残る label JOIN 修正後も refund/payout/effective_stake 統合で別 bug が出る可能性が高い。09-05 を Phase 5 idiom（label/market/refund/payout 全統合）で大幅見直しする必要がある（別タスク・~1時間+）。

## 後続への引き継ぎ（別タスク）

- **09-05 完全化タスク**: pred_df へ label JOIN → refund_accounting（determine_stake_payout）→ effective_stake → D-14 指標2/4 + D-15 residual proxy + D-16 verdict の算出。run_backtest.py の label/market/refund idiom を完全移植。
- snapshot は両方生成済み（baseline postreview-v2 + speed_figure MMSS.t 修正版）・学習も通過済み。残るは指標算出パイプラインの統合のみ。
- **許容幅**（Brier +0.005 / LogLoss +0.02 / AUC -0.005）は RESEARCH.md Open Questions RESOLVED #2 採用・Phase 11 SC#2 事前登録マージンと同一スケール前提。

## Phase 9 全体を通じた最大の成果

09-05 実行の過程で SC#5 が speed_figure 外れ値を検出 → **09-01 の `time/10.0`（decisecond 仮定）が MMSS.t 可変長エンコードの誤認と判明**（commit 4a20f13・真の根本原因）。これは Phase 9 全体の価値（実データ検証で潜在 bug を摘出）の核心。→ [jra-van-time-mmss-t-encoding](memory) 参照。
