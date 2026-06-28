# Phase 12 p_lower EV + Falsification 統合評価

## Gate Verdict (§15.2 gate 不変 + Phase 12 WARN gate 併載)

- §15.2 gate (block_triggered): False
- Phase 12 WARN gate (phase12_warn_triggered): True
  - phase12_selected_only_calib_max_dev: selected-only calib_max_dev=0.272 > threshold=0.100 (投票層の過大予測・SC#4・D-06 WARN)
  - phase12_odds_band_calib_max_dev[1.0-2.9]: calib_max_dev=0.363 > threshold=0.150 (オッズ帯別条件付き calibration 過大・SC#4・D-06 WARN)
  - phase12_odds_band_calib_max_dev[3.0-4.9]: calib_max_dev=0.164 > threshold=0.150 (オッズ帯別条件付き calibration 過大・SC#4・D-06 WARN)

## 回収率 (purchase_simulator + refund_accounting)

- baseline (v1.0 binary): 0.7313844714686623
- p_lower: 0.0

## q_shrink (calib slice のみ・§11.2 聖域)

- q_level: 0.9
- q_shrink: 0.3328315161410432

## switch_recommendation (D-09・判断材料・実行でない)

- recommendation: **reject**
