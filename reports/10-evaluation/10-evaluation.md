# Phase 10 SC#5 非劣化 Gate: v1.0 baseline vs Phase 10 snapshot (opponentstrength)

## Gate Verdict (D-16 事前登録許容幅)

**PASS (3条件全て D-16 許容幅内・delta 基準は baseline snapshot 実測値)**

## B-3 両 snapshot 実測値・delta (delta 基準は baseline snapshot 実測値)

| 指標 | baseline 実測 | Phase 10 実測 | delta | D-16 許容幅 | 判定 |
|------|-------------|--------------|-------|------------|------|
| Brier | 0.15546 | 0.15524 | -0.00022 | <= +0.002 | PASS |
| LogLoss | 0.47986 | 0.48473 | +0.00487 | <= +0.005 | PASS |
| AUC | 0.69708 | 0.69888 | +0.00180 | >= -0.005 | PASS |

## BASELINE_* 参考値との乖離 WARNING (B-3 鑑別資料)

- BASELINE_BRIER (Phase 6 当時): 0.15222 / baseline 実測: 0.15546 / drift: +0.00324
- BASELINE_LOGLOSS (Phase 6 当時): 0.47488 / baseline 実測: 0.47986 / drift: +0.00498
- BASELINE_AUC (Phase 6 当時): 0.7323 / baseline 実測: 0.69708 / drift: -0.03522
- baseline 実測値が BASELINE_* 参考値 (Phase 6 当時) と大きく乖離している場合・trainer 設定ドリフト (LightGBM version/hyperparams/seed/category_map/split_periods 揺らぎ) を疑う (feature ノイズ化と設定ドリフトの鑑別・§11.2 聖域)

## W-2 candidate score diagnostics (0.25 canonical 妥当性証拠)
- status: ok
- train: reports/10-evaluation/candidate_score_diagnostics_train.json
- calib: reports/10-evaluation/candidate_score_diagnostics_calib.json
- §11.2 聖域: 候補選定は train/calib 窓内のみ・test 窓 rank はすり替えない

## W-3 category_map bit-identity (B-3 同一 trainer 設定の前提)
- baseline_cat_map_hash: 96b7cc5807604e7c6b23570b22cdaed2...
- phase10_cat_map_hash: 96b7cc5807604e7c6b23570b22cdaed2...
- bit_identical: True

## §15.2 binning 契約 (import 再利用・再定義禁止)
- CALIBRATION_CURVE_BINS: 10
- CALIBRATION_CURVE_MIN_BIN_COUNT: 30
- ODDS_BAND_EDGES: [0.  2.9 4.9 9.9 inf]
- NINKI_BAND_EDGES: [ 0.  3.  6.  9. inf]

## D-15 参考記録 (selected-only calibration / odds_band×p_bin)
- 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない (Brier/LogLoss/AUC の3条件のみが gate)
