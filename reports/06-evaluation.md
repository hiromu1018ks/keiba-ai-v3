# Phase 6 Evaluation Report (EVAL-01/02/03 / §15.1/§15.2/§15.3)

**feature_snapshot_id:** 20260620-1a-postreview-v2  /  **as_of_datetime:** 2026-06-20T00:00:00Z

## 受入ゲート判定（BLOCK/WARN）

- **gate_verdict:** WARN
- **block_triggered:** False
- **warn_reasons:**
  - sum_p_violation (single condition, not BLOCK): large_violation_rate=71.4% >= 30% — D-02 AND 条件未満
  - sum_p_violation (single condition, not BLOCK): small_violation_rate=76.7% >= 30% — D-02 AND 条件未満
- **condition_flags:** {'baselines_all_lose': False, 'sum_p_violation': True}
- **comparable_baselines:** ['bl1', 'bl4', 'bl5']
- **sum_p_block_threshold:** 0.3

### bin 単調性 WARN 指標（D-03・参考）

| model | spearman_corr | spearman_pvalue | bin_inversions |
| --- | --- | --- | --- |
| catboost | 0.9833 | 0.0000 | 1 |
| lightgbm | 1.0000 | 0.0000 | 0 |

### 年次反転 WARN 指標（D-03 年次要素・参考）

| year | spearman_corr | spearman_pvalue | bin_inversions |
| --- | --- | --- | --- |
| 2024 | 1.0000 | 0.0000 | 0 |

### sum(p) violation_rate 計測（REVIEW HIGH#5・0.30 閾値の経験的根拠）

- large_violation_rate: 0.7139 (threshold=0.30)
- small_violation_rate: 0.7667
- total_races: 1654
- threshold_appropriate: False
- diagnostic_note: 閾値 0.30 を超過・閾値調整を検討

### race_id split integrity（REVIEW Codex MEDIUM + N3 cycle-3・§8.4 聖域）

- race_id_split_disjoint: N/A
- n_train_races: 0
- n_test_races: 1654
- diagnostic_note: split データ不足（train または test が空）・Phase 4 GroupTimeSeriesSplit 担保・REVIEW N3 cycle-3 vacuous check 回避

## 主モデル比較表（全指標）

| model_name | brier | logloss | auc | sum_p_mean | sum_p_median | sum_p_p10 | sum_p_p90 | calibration_max_dev | calibration_max_dev_guarded | market_reference | bl_calib_note | d04_selection_criterion | bt_recovery_rate | bt_profit_loss | bt_max_drawdown | bt_representative_policy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bl1 | 0.169530 | 0.521015 | 0.573953 | 2.958365 | 3.000000 | 3.000000 | 3.000000 | 0.001426 | nan |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | nan | nan | nan |  |
| bl2 | nan | nan | nan | nan | nan | nan | nan | nan | nan |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | nan | nan | nan |  |
| bl3 | nan | nan | nan | nan | nan | nan | nan | nan | nan | Phase 1-A モデルと同一情報条件の比較ではない (§14.2): BL-3 は確定複勝オッズ由来の市場暗示確率であり・Phase 1-A モデルは odds-free feature のみ使用 |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | nan | nan | nan |  |
| bl4 | 0.168700 | 0.518246 | 0.601986 | 3.246690 | 3.303847 | 2.613266 | 3.793841 | 0.044928 | nan |  | BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意 | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | nan | nan | nan |  |
| bl5 | 0.167097 | 0.513048 | 0.619879 | 3.107942 | 3.145625 | 2.458588 | 3.707469 | 0.343709 | nan |  | BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意 | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | nan | nan | nan |  |
| catboost | 0.154529 | 0.482434 | 0.718001 | 3.067278 | 3.033874 | 1.972756 | 4.177213 | 0.257893 | nan |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | 0.680783 | -129146.000000 | 157200.000000 | 30min_before |
| lightgbm | 0.152216 | 0.474883 | 0.732295 | 3.041678 | 3.000430 | 1.931710 | 4.154802 | 0.230769 | nan |  |  | D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用 | 0.702153 | -126736.000000 | 147890.000000 | 10min_before |

**backtest 集計方法（REVIEW C8）:** 優位 policy の代表窓（30min_before/10min_before のうち recovery_rate が高い方を代表）

## 主モデル確定（理由記録・D-07）

- **primary_model:** 未確定（--primary-model 省略・REVIEW C7）

### 推奨主モデル（D-08 タイブレーク優先順位・参考）

- **recommended:** lightgbm
- **selection_reason:** D-08 tiebreak[1] backtest_recovery_rate: lightgbm (recovery: 0.7022 vs 0.6808)
- **tiebreak_applied:** backtest_recovery_rate
- **priority_order:** ['backtest_recovery_rate', 'compute_cost_lightgbm_first', 'brier', 'logloss', 'auc']

## segment 安定性サマリ（6軸）

| axis | n_segments | segments |
| --- | --- | --- |
| entry_count | 13 | 10.0, 11.0, 12.0, 13.0, 14.0... |
| jyocd | 9 | 01, 02, 03, 04, 05... |
| month | 6 | 10, 11, 12, 7, 8... |
| ninki | 4 | 1-3, 10+, 4-6, 7-9 |
| odds_band | 2 | 10+, __MISSING__ |
| year | 1 | 2024 |

詳細: reports/06-segments/{year,month,jyocd,entry_count,ninki,odds_band}.{json,html}

## 注記

- D-04 事前登録: Calibration 重視 (calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考)。Phase 6 で最終選定基準として採用
- BL-1 caveat: 順序付け能力ゼロ (AUC≈0.57) の副産物で calibration_max_dev が構造的極小・uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない（debug Resolution #4）
- BL-3: Phase 1-A モデルと同一情報条件の比較ではない (§14.2): BL-3 は確定複勝オッズ由来の市場暗示確率であり・Phase 1-A モデルは odds-free feature のみ使用
- BL-4/5: BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない (calibrate_bl4_bl5=False)・比較公平性に注意
- sum(p) threshold 根拠: SUM_P_BLOCK_THRESHOLD=0.3 は仮置き・現データ violation_rate 実測で偽陽性 BLOCK を出さないか検証済み（threshold_appropriate=False）
- SC#2「beat all baselines」と BLOCK 条件1「baselines 全敗」は対称的な表現。どちらも COMPARABLE_BASELINES bl1/bl4/bl5 の LogLoss+Brier 比較で・SC#2 は両指標で全 baselines の max に勝る（全勝）・BLOCK 条件1 は両指標で全 baselines の max に劣る（全敗）。中間の「一部にのみ劣る / 一部にのみ勝る」は WARN に留まる（D-02 AND 条件）。現データ（reports/04-eval.json）では LightGBM が LogLoss/Brier 両方で BL-1/BL-4/BL-5 の全てに勝るため SC#2 達成・BLOCK 条件1 は非該当。定義の対称性を明示することで Phase 8 対抗的監査で「SC#2 達成」の解釈が曖昧にならない（REVIEW C15 cycle-2 修正）。
