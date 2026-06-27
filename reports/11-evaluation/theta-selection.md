# Phase 11 θ 選択経路 (D-03 制約付き選択・calib slice のみ)

## Selected θ

**θ = 1.0**

- final_verdict: selected θ=1.0 via cutoff→argmin_overpred→tiebreak
- §11.2 聖域: θ 選択は calib slice (score_split='calib') のみ・test 窓は選び直さない

## 選択経路 (足切り → 選択 → tie-break)

### Stage 1: D-04 非劣化 (Brier/LogLoss/AUC 許容幅内)
- 許容幅: Brier ≤ 0.005 / LogLoss ≤ 0.01 / AUC ≥ -0.005
- 通過: 5 / 5 (脱落: [])

### Stage 2: D-05-1 overprediction penalty 最小 (NaN-safe・全員 NaN は passing 保持)
- min overprediction penalty: None
- 残候補: [0.5, 0.75, 1.0, 1.25, 1.5]

### Stage 3: tie-break: selected-only calib_max_dev 最小 → θ=1 に近い候補
- 残候補 (θ=1 に近い順): [1.0]
- selected: θ=1.0

## 候補毎の評価値 (calib slice)

| θ | Brier | LogLoss | AUC | overprediction_penalty | calib_max_dev | selected_only_calib_max_dev | verdict |
|---|-------|---------|-----|----------------------|---------------|-----------------------------|---------|
| 0.5 | 0.15557 | 0.48366 | 0.72491 | NaN | 0.24697 | 0.08952 | pass |
| 0.75 | 0.15113 | 0.46632 | 0.72603 | NaN | 0.15107 | 0.02374 | pass |
| 1.0 | 0.15099 | 0.46607 | 0.72617 | NaN | 0.26512 | 0.01388 | pass |
| 1.25 | 0.15197 | 0.46933 | 0.72522 | NaN | 0.28589 | 0.03911 | pass |
| 1.5 | 0.15317 | 0.47310 | 0.72349 | NaN | 0.37518 | 0.05281 | pass |

## baseline (theta=None) calib 指標 (足切り基準)

- Brier: 0.1543136722624418
- LogLoss: 0.47566579926145663
- AUC: 0.7049495103144049
- baseline overprediction penalty (calib): nan
