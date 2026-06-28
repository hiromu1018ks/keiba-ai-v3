---
spike: "001"
name: ablation-recovery
type: standard
validates: "Given Phase 9-12 snapshots/models, when measured with a single unified metric (12-system select_bets selector) on BT-1/2023, then which features/model/EV raise or lower fukusho recovery_rate, and what is the recovery-rate-maximizing feature subset"
verdict: PENDING
related: []
tags: [ablation, recovery-rate, leak-prevention, lightgbm, backtest, core-value]
---

# Spike 001: Phase 9-12 回収率 ablation（特徴量/モデル/EV 取り捨てのデータ判定）

## What This Validates

Phase 9-12 で追加された特徴量群（speed figure 基本6 / 9.1拡張11 / Phase10-27）とモデル/EV（binary vs race-relative）が、**統一指標（12系 select_bets selector）で**複勝回収率を上げるか下げるかを統制比較し、取り捨てをデータで決定する。黒字化（回収率≥1.25・控除率考慮）が目的。

## 調査で判明した前提の訂正（重要）

ユーザー開示時点の「9→9.1悪化（0.8956→0.7359）」は実物レポートに存在するが、**09系独自 selector（EV≥1.0のみ）**の数字で、Phase 12 統一 selector（EV≥1.05∩p≥0.15∩odds≥1.5∩top-2）とは selected 集合が異なる。A1=0.8956 の「効きすぎ」は metric artifact 候補。**全変種を12系統一指標で再測定**して真の傾向を判定する。

詳細は事前登録 `reports/12-evaluation/ablation-spec.{md,json}`（commit 済み・実行前）。

## How to Run

未実装（事前登録段階）。実行順序は ablation-spec §9：
1. U0: `run_phase12_evaluation.py --baseline-snapshot-id 20260626-1a-speedprofile-v1 --bt-split BT-1 --odds-snapshot-policy 30min_before --selected-theta 1.0`
2. A0-A3: 同上で `--baseline-snapshot-id` を各 snapshot に切替
3. C/D/E: 新規 `scripts/run_ablation.py`（column-drop thin script）

## What to Expect

- U0 で12系統一 recovery_rate が09系 roi(0.7359) と**一致しない**こと（selector 差の確認）。
- A0-A3 を12系統一 selector で再測定し、「9.1悪化」の真偽を再判定（A1=0.8956 は崩れる予測）。
- D で9.1拡張のどの部分群（分布形状5 vs 条件適性6）が回収率を下げるか特定。
- C/E で取り捨て推奨と最適部分集合を提案。

## Investigation Trail

- 2026-06-28: 事前登録。調査で指標2系統の selector 差を特定（09系 EV≥1.0 vs 12系 3条件+top-2）。ユーザー判断: column-drop は thin script（make_X_y 不改変・聖域維持）/ LightGBMのみ / U0先決。Explore agent の集約を検証中に一時「幻覚」と誤断定したが実物（reports/09-stopgate.md 直下）で A1=0.8956 が実在することを確認・訂正。

## Results

（実行後に記録）
