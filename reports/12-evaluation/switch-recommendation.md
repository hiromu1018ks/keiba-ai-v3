# Phase 12 switch_recommendation (D-09)

## Recommendation: **reject**

## 統合材料

- phase12_warn_triggered: True
- baseline_recovery_rate: 0.0
- p_lower_recovery_rate: 0.0
- recovery_rate_delta: 0.0
- ev_improved: False
- falsification_verdict: feature_gap

## 判定ルール

- **reject**: SC#4 WARN gate FAIL → core value 維持での黒字化困難 (market が model を包摂)
- **switch**: SC#4 PASS + EV 改善 + feature_gap → 市場 residual が残る (特徴量改善余地あり)
- **hold**: SC#4 PASS + (EV 改善なし または structural_limit) → 現状維持 (判断材料積み上げ)

## D-10 (人間承認の別アクション)

- switch_recommendation は判断材料を report に出すのみ (D-09)・is_primary DB 変更は人間承認の別アクション (D-10・set_primary_model を呼ばない・AST check 0件)