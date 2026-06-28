# Spike Manifest

## Idea
Phase 9-12 の回収率効果を統制比較し、特徴量/モデル/EV 判定の取り捨てをデータで決定する。黒字化（回収率≥1.25・控除率考慮）が目的。分析ツール化しない。

## Requirements
- 全変種は12系統一 selector（`select_bets`/`FUKUSHO_EV_V1_THRESHOLDS`: EV≥1.05∩p≥0.15∩odds≥1.5∩top-2）で測る。09系数字（EV≥1.0のみ selector）は selector 固有の参考記録。
- column-drop は thin script（`scripts/run_ablation.py`）で `make_X_y` 不改変・`X.drop` で実験隔離（core value 機械保証・adversarial audit 被覆維持）。
- LightGBM のみ（race_relative も LightGBM ベース・apples-to-apples）。CatBoost は主眼外。
- U0（指標統一検証）が最初のゲート。A0-A3 を12系統一指標で再測定してから D/C/E/B1 に進む。
- §11.2 test 窓 BT-1 固定・SAFE-01 odds-free・byte-reproducible（FIXED_REPRODUCE_TS・seed=42・thread=1）。

## Spikes
| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | ablation-recovery | standard | unified-metric feature/model/EV ablation on BT-1/2023 | VALIDATED | ablation,recovery-rate,leak-prevention,core-value |
