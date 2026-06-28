---
spike: "001"
name: ablation-recovery
type: standard
validates: "Given Phase 9-12 snapshots/models, when measured with a single unified metric (12-system select_bets selector) on BT-1/2023, then which features/model/EV raise or lower fukusho recovery_rate, and what is the recovery-rate-maximizing feature subset"
verdict: VALIDATED
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
- 2026-06-28: U0 既存データ（05-backtest A0=0.6471 vs 09-stopgate A0=0.7018）で selector 差確定。A0 ゲート実行で eligibility 半減（22793/47672=48%）を発見 → newcomer '12' 誤除外バグ（syubetucd '12' は新馬でなく1勝/未勝利・code_tables.yaml 誤り）発覚 → 別セッション gsd-debug で修正（commit 2cdbac1・label v1.1.0・eligible 42214）。
- 2026-06-28: 新 universe で A0-A3 測定（A1=1.0459 黒字）。column-drop ハーネス実装（A3 クロスチェック PASS・命綱）。D1/D2 で9.1悪化の主因=分布形状5 を特定。C1 で Phase10 も悪化寄与を確認。A1 cross-window 5窓全て黒字（頑健）・leak 再監査 GREEN。A1 を黒字化の正解として確定。

## Results

**VALIDATED — A1（speed figure 基本6・binary）が黒字化の正解。**

- A1 BT-1: 回収率 **1.0459**（黒字）・A0(0.731)から +0.315。
- A1 cross-window 5窓（2023/2024/2025・expanding+rolling）**全て黒字**・平均 1.14・選抜 4000+。「2023固有フレイク」でない（頑健）。
- leak 再監査クリア（PIT-correct・odds-free・target leakage なし・adversarial test GREEN）。
- 9.1悪化は新 universe でも確認（A1 1.046→A2 0.700・−0.346）。主因=分布形状5（median/best2/trend・多重共線性+ノイズ）。
- Phase10（opponent/race_relative）も A1 に足すと悪化（C1=0.742 < A1=1.046）。**全部入り≠最善**。
- 最適部分集合: **A1（speed fig 基本6 単体）**。特徴量を引く方向が黒字化の鍵。
- B1（race_relative）は skip（A1 binary 黒字で限界価値低）。

詳細: `reports/12-evaluation/ablation-results.{md,json}`。
