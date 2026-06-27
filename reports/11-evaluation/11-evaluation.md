# Phase 11 SC#2 Gate: v1.0 binary vs race-relative model (θ + per-race α_r)

## Gate Verdict

**FAIL (D-04 または D-05 のいずれか未達・§11.2 聖域・許容幅は変更せず)**

- selected θ: 1.0

## D-04 非劣化 gate (delta 基準は baseline 実測値)

- verdict: PASS
| 指標 | baseline 実測 | race-relative 実測 | delta | D-04 許容幅 |
|------|-------------|-------------------|-------|------------|
| Brier | 0.15524 | 0.15202 | -0.00323 | <= +0.005 |
| LogLoss | 0.48473 | 0.47118 | -0.01355 | <= +0.01 |
| AUC | 0.69888 | 0.71784 | +0.01896 | >= -0.005 |

## D-05 改善 gate (3 必須条件)

- verdict: FAIL (3条件の論理積)
- (1) overprediction penalty (rr < baseline): FAIL (baseline=nan / rr=nan)
- (2) selected/high-EV 層 mean_pred - frac_pos (rr < baseline): PASS (baseline=0.011456606328211216 / rr=0.010573222942066529)
- (3) selected-only calib_max_dev (rr <= baseline + margin): PASS (baseline=0.011456606328211216 / rr=0.010573222942066529 / margin=0.005)

## θ 選択経路 (D-03 制約付き選択・calib slice のみ・§11.2 聖域)

- selected θ: 1.0
- final_verdict: selected θ=1.0 via cutoff→argmin_overpred→tiebreak
- θ 選択は score_split='calib' のみで実施 (codex HIGH#1・test 窓選び直し禁止)
- reports/11-evaluation/theta-selection.{md,json} に候補毎の評価値と選択経路を事前書き出し済み (後知恵すり替え禁止)

## §15.2 binning 契約 (import 再利用・再定義禁止)

- CALIBRATION_CURVE_BINS: 10
- CALIBRATION_CURVE_MIN_BIN_COUNT: 30
- ODDS_BAND_EDGES: [0.  2.9 4.9 9.9 inf]
- NINKI_BAND_EDGES: [ 0.  3.  6.  9. inf]

## race_relative 事前登録定数 (§11.2 聖域)

- THETA_CANDIDATES: [0.5, 0.75, 1.0, 1.25, 1.5]
- ALPHA_SEARCH_XTOL: 1e-09
- P_CAL_CLIP_EPSILON: 1e-06

## model_versions

- baseline: 20260626-1a-opponentstrength-v1-lgb-v1
- race_relative: 20260626-1a-opponentstrength-v1-lgbrr-v1

## D-07 (is_primary 立てない)

- Phase 11 は並列比較のみ・is_primary 切替は Phase 12 (D-07)。本 script は比較レポート生成のみ・prediction 永続化 (load_predictions / primary 切替) は行わない。実際の model_version 行追加は 11-05 で実施 (primary 立ては Phase 12)。

## D-15 参考記録 (selected-only calibration / odds_band×p_bin)
- 参考記録 (Phase 12 EVAL-01 先行指標)・gate 判定には使わない
