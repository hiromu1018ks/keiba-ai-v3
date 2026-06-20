# Phase 4 Evaluation Report (SC#2 / §15.1 / §15.2)

## 比較表 (BL-1..5 + 主モデル)

| model_name | brier | logloss | auc | sum_p_mean | sum_p_median | sum_p_p10 | sum_p_p90 | calibration_max_dev | market_reference | bl_calib_note | d04_selection_criterion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm | 0.152216 | 0.474883 | 0.732295 | 3.041678 | 3.000430 | 1.931710 | 4.154802 | 0.230769 |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| catboost | 0.154529 | 0.482434 | 0.718001 | 3.067278 | 3.033874 | 1.972756 | 4.177213 | 0.257893 |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| bl1 | 0.169530 | 0.521015 | 0.573953 | 2.958365 | 3.000000 | 3.000000 | 3.000000 | 0.001426 |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| bl2 | nan | nan | nan | nan | nan | nan | nan | nan |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| bl3 | nan | nan | nan | nan | nan | nan | nan | nan | Phase 1-A モデルと同一情報条件の比較ではない (§14.2): BL-3 は確定複勝オッズ由来の市場暗示確率であり・Phase 1-A モデルは odds-free feature のみ使用 |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| bl4 | 0.168700 | 0.518246 | 0.601986 | 3.246690 | 3.303847 | 2.613266 | 3.793841 | 0.044928 |  | BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意 | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |
| bl5 | 0.167097 | 0.513048 | 0.619879 | 3.107942 | 3.145625 | 2.458588 | 3.707469 | 0.343709 |  | BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意 | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 |

## §15.2 sum(p) 分布検査結果

- 複勝確率は独立二値確率のため sum(p) は払戻対象数に厳密合計しない・診断的指標として扱う (§15.2・review MEDIUM)
- SUM_P_BOUNDS (診断的閾値): {'large': (2.7, 3.3), 'small': (1.8, 2.2)}
- CALIBRATION_CURVE_BINS=10, STRATEGY='uniform', MIN_BIN_COUNT=30

## 注記

- D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用
- BL-3: Phase 1-A モデルと同一情報条件の比較ではない (§14.2): BL-3 は確定複勝オッズ由来の市場暗示確率であり・Phase 1-A モデルは odds-free feature のみ使用
- BL-4/5: BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意
