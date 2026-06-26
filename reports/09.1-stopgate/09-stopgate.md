# Phase 9 SC#6 Stop Gate: v1.0 baseline vs (v1.0+speed_figure)

## D-14 必須4指標

- 指標1 selected calibration (投票層 |mean_pred - frac_pos|):
  - baseline: 0.09729669284232105
  - speed_figure: 0.091456579094177
  - improved: True
- 指標2 selected-only ROI/EV:
  - baseline: {'roi': 0.7017790428749333, 'n_selected': 5621, 'hit_rate': 0.09606831524639743}
  - speed_figure: {'roi': 0.7358603220553646, 'n_selected': 5527, 'hit_rate': 0.0998733490139316}
- 指標3 Brier/LogLoss/AUC 非劣化判定:
  - brier_delta: -0.0006383988128838003 (許容幅 +0.005)
  - logloss_delta: -0.00038685424035628246 (許容幅 +0.02)
  - auc_delta: 0.004594664312118635 (許容幅 -0.005)
  - non_degraded: True
- 指標4 model-market disagreement ROI (D-15 residual proxy 連動):
  - signal_present: True
  - n_valid_cells: 88

## D-15 軽量 residual proxy
- signal_present: True
- (p値判定・回帰係数は Phase 12 EVAL-02 に委譲・D-12)

## D-16 Verdict

**特徴量追加の有効性シグナルあり・Phase 10 進行候補**

## 許容幅の根拠 (RESEARCH.md Open Questions RESOLVED #2)
- Brier +0.005 (v1.0=0.15222 の ~3.3%)
- LogLoss +0.02 (v1.0=0.47488 の ~4.2%)
- AUC -0.005 (v1.0=0.73230 の ~0.7%)
- Phase 11 SC#2 事前登録マージンと同一スケール前提 (cross-reference)

## SAFE-01 (EVAL-02)
- market_implied (1.0 / fuku_odds_lower) は診断層のみ使用・FEATURE_COLUMNS に混入なし
