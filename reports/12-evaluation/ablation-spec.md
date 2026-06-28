# Ablation Spec — Phase 9-12 回収率 ablation（特徴量/モデル/EV 取り捨てのデータ判定）

- **Spike**: 001 (`.planning/spikes/001-ablation-recovery/`)
- **事前登録日**: 2026-06-28
- **状態**: 事前登録（実行前・commit 済み）。実行結果は別途 ablation-results に記録。
- **目的**: Phase 9-12 の回収率効果を統制比較し、特徴量/モデル/EV 判定の取り捨てを**データで**決定する。黒字化（回収率 > 1.0・控除率 20-25% 考慮で回収率 ≥ 1.25 が真の黒字）が目的。分析ツール化しない。

---

## 0. 調査で判明した前提の訂正（重要・後知恵防止のために実行前に明記）

ユーザー開示時点の再構成表「A1=0.8956 → A2=0.7359（9→9.1 悪化）」は実物レポート（`reports/09-stopgate.md` 直下）に存在する数字だが、**その指標は 09 系独自 selector に依存し、Phase 12 の統一指標とは selected 集合が異なる**。実行前にこの差を固定する：

### 指標の 2 系統（計算式は同一・selector が異なる）

両系とも回収率 = `sum(payout_amount) / sum(effective_stake)`（`determine_stake_payout` 会計・`compute_backtest_metrics`）。差は **selected 集合の定義（selector）**:

| 系統 | 生成スクリプト | selector | 出典数字 |
|---|---|---|---|
| **09系** | `run_speed_figure_stopgate.py::_compute_selected_roi` | `EV_lower >= SELECTED_EV_THRESHOLD(=1.0)` **のみ** | A0=0.7018 / A1=0.8956 / A2=0.7359 |
| **12系** | `run_phase12_evaluation.py::_compute_recovery_rate` → `select_bets` | `EV_lower>=1.05 ∩ p>=0.15 ∩ fuku_odds_lower>=1.5 ∩ レース内top-2` | A3=0.7314(binary) / p_lower=0.0 |

- 09系 selector（EV≥1.0 のみ）は 12系 selector（3条件+top-2）より**緩く**、選抜数が多い（A1=6247件）。
- **09系数字と12系数字は selected 集合が違うため直接比較不可**。A1=0.8956 の「効きすぎ」は EV≥1.0 単独 selector（緩い）の産物の可能性が高い（metric artifact 候補）。
- **本 ablation の全変種は「12系統一 selector」で測り直す**。09系数字は selector 固有の参考記録として扱い、結論の根拠には**12系統一指標の数字**を使う。

---

## 1. 聖域（絶対・遵守）

- **§11.2 test 窓 sanctuary**: 全変種 BT-1 固定・test 窓 outcome は学習/閾値選択に使わない。test 窓での selector/θ/q_shrink の選び直し禁止。
- **SAFE-01**: 特徴量 odds-free（`FEATURE_COLUMNS` にオッズ/市場情報 proxy 混入なし）。
- **事前登録**: 本ファイル（ablation-spec.{md,json}）を commit してから実行。事前登録外の追加は理由を ablation-results に記録（後知恵防止）。
- **byte-reproducible**: `FIXED_REPRODUCE_TS`・固定 seed=42・num_threads=1・同一 hyperparam。同一条件で2回実行し一致を確認。
- **make_X_y 不改変**: column-drop は thin script 内で `X.drop(columns=...)` により実験隔離。生産 primitive（`make_X_y` の `X.columns==FEATURE_COLUMNS` 厳密 assert）は1行も変えない（core value 機械保証・adversarial audit 被覆維持）。

## 2. 統一条件

- **test 窓 BT-1**: train=`2019-06-01..2022-06-30` / calib=`2022-07-01..2022-12-31` / test=`2023-01-01..2023-12-31`（`group_split.BT_WINDOWS` BT-1 + `_carve_calib_from_train_tail`・両 pipeline 共通）。
- **odds policy**: `30min_before`（固定・§11.2）。
- **モデル**: **LightGBM のみ**（race_relative も LightGBM ベース・apples-to-apples）。CatBoost は主眼外。
- **hyperparam（Phase 12 同一・`trainer.LGB_INIT_PARAMS`）**: objective=binary, learning_rate=0.05, num_leaves=63, min_data_in_leaf=100, feature_fraction=0.9, seed=42, deterministic=True, force_col_wise=True, num_threads=1, bagging_seed=42, feature_fraction_seed=42, n_estimators=N_ESTIMATORS（固定）。
- **calibration**: `CalibratedClassifierCV(cv='prefit', method='isotonic')`（calib slice は train と disjoint・strict-later）。

## 3. 統一指標（全変種で同一）

- **selector**: 12系 `select_bets(FUKUSHO_EV_V1_THRESHOLDS)` = `EV_lower>=1.05 ∩ p>=0.15 ∩ fuku_odds_lower>=1.5 ∩ レース内top-2`（`p_col='p_fukusho_hit'`・binary 点推定経路）。
- **回収率**: `sum(payout_amount) / sum(effective_stake)`（`determine_stake_payout` 会計・`compute_backtest_metrics`）。
- **報告列（各変種）**: 回収率・選抜数(n_selected)・的中数(hit_count)・hit_rate・P/L・(選抜数<50 は信頼区間付きで断定しない)。

---

## 4. U0 — 指標統一検証ゲート（最初に実行・後知恵防止）

**U0 は「09系数字を捨てて12系統一指標へ移行する」ことの確認。**

1. **定義確認（済・本 spec §0）**: 09系 selector(EV≥1.0) と12系 selector(3条件+top-2) は異なる。計算式は同一でも selected 集合が違う。
2. **実行検証**: `run_phase12_evaluation.py --baseline-snapshot-id 20260626-1a-speedprofile-v1 --bt-split BT-1 --odds-snapshot-policy 30min_before --selected-theta 1.0` で A2(speedprofile) の12系 binary recovery_rate（統一 selector）を取得。
3. **比較**: 12系統一 recovery_rate vs 09系 roi=0.7359。**異なる selector なので一致しないのが予測**（一致しないこと自体が「09系数字は selector 固有」の確認）。
4. **ゲート判定**:
   - 09系数字(0.7018/0.8956/0.7359)は12系統一指標とは直接比較不可 → A0-A3 を12系統一 selector で再測定。
   - 再測定で「A1の突出(0.8956)」が崩れる（統一 selector で選抜大幅減・回収率変動）ことが予測 → 「9→9.1悪化」の真偽は**12系統一指標で再判定**。

---

## 5. 比較マトリクス

### A. 特徴量 snapshot ablation（binary 点推定・12系統一 selector）
| 変種 | snapshot_id | 追加特徴量 | 位置づけ |
|---|---|---|---|
| A0 | 20260620-1a-postreview-v2 | (baseline) | v1.0 素 |
| A1 | 20260625-1a-speedfigure-v1 | +speed figure 基本6 | Phase 9 効果 |
| A2 | 20260626-1a-speedprofile-v1 | +9.1拡張11(分布形状5+条件適性6) | Phase 9.1 効果 |
| A3 | 20260626-1a-opponentstrength-v1 | +Phase10-27(opponent21+race_relative6) | Phase 10 効果 |

### B. モデル/EV 比較（A3 で）
| 変種 | 内容 | 位置づけ |
|---|---|---|
| B0 | binary(theta=None) × 点推定（=A3） | baseline |
| B1 | race-relative(theta=1.0) × 点推定 | **Phase 11 真の効果（未知・核心）** |
| (B2: p_lower(q90) は既知 0.0・選抜極少・参考) | | |

### C. 特徴量群脱落（A3 で binary・column-drop）
| 変種 | 脱落群 | 位置づけ |
|---|---|---|
| C1 | speed profile 群（9.1拡張11） | 取り捨て判断 |
| C2 | opponent strength 群（field_strength21） | 取り捨て判断 |
| C3 | race_relative 群（race_relative6） | 取り捨て判断 |

### D. Phase 9.1 悪化の深掘り（A2=speedprofile ベース・column-drop で9.1拡張を分離）
9.1拡張11 = 分布形状5(`median_3,median_5,best2_mean_5,trend_last_minus_mean5,trend_mean3_minus_mean5`) + 条件適性6(`same_surface_{mean,max,count}_5, same_distance_bucket_{mean,max,count}_5`)
| 変種 | 構成 | 位置づけ |
|---|---|---|
| D1 | A1(基本6) + 分布形状5 のみ | 悪化原因特定 |
| D2 | A1(基本6) + 条件適性6 のみ | 悪化原因特定 |
| D3 | A2（基本6+両方=17）= 再確認 | 悪化原因特定 |
- D1,D2 vs A1 → どの部分群が（12系統一指標で）回収率を下げるか。12系指標で「9.1悪化」が再確認されれば D が活きる；崩れれば D の所見も変わる（後知恵防止のため U0→A 再測定の後に D を実行）。

### E. 最適部分集合探索（A-D 結果から）
FEATURE_COLUMNS の部分集合で回収率を最大化する組合せを数パターン試行しランキング。「全部入り≠最善」を確認。例: A1(基本6) + Phase10(opponent/race_relative) − 9.1拡張、等。

---

## 6. 実装方針

- **snapshot-swap（A0-A3/B1）**: 既存 `run_phase12_evaluation.py --baseline-snapshot-id` で即実行可能。B1 は `--selected-theta 1.0`（race_relative 適用）。
- **column-drop（C/D/E）**: 新規 `scripts/run_ablation.py`（thin script）。
  - `make_X_y(frame, snapshot_id)` を**そのまま呼び**完全 FEATURE_COLUMNS の X,y を取得（生産と一致・assert 通過・聖域維持）。
  - スクリプト内で `X_ablate = X.drop(columns=<除外群>)` し LightGBM 学習（渡された列のみで学習・category_map 整合は崩れない）。
  - split_3way / calib / category_map / race_relative 補正は既存 `orchestrator` ロジックを再利用（make_X_y が返す完全 X から drop するだけなので calib/category_map/race_relative への影響なし）。
  - 統一 selector/select_bets/determine_stake_payout/compute_backtest_metrics で回収率を算出（12系と同一経路）。
- **live-DB**: 各 backtest は readonly（odds/label/HARAI 取得）。`statement_timeout` 設定（`_configure_statement_timeout` idiom）。DB 書込はしない（dry run・`--no-write-db` 相当）。

## 7. 報告・判断基準

- 回収率単独で判断しない（選抜数・的中数・hit_rate を併載）。
- 選抜数 < 50 の変種は信頼区間付き・断定しない。
- **取り捨て推奨（データ根拠付き）**: 回収率を上げる→残す/強化 / 不変→捨て候補 / 下げる→捨てる。9.1拡張群（全部/一部）を捨てる提案を明示的に評価。
- 「特徴量を足せば足すほど良くなる」を仮定しない（部分集合で回収率が上がれば引く方向も推奨）。
- 既存レポート（09系数字）と矛盾する場合は理由（selector 差・test 窓）を明記。

## 8. 成果物（`reports/12-evaluation/ablation-results.{md,json}`）

1. 回収率比較表（全変種・12系統一指標・回収率/選抜数/的中数/hit_rate/P/L）
2. 09系数字 vs 12系統一数字の対比（selector 差の影響・A1=0.8956 の崩れ具合）
3. 「9→9.1悪化」の12系統一指標での再判定（真/偽）
4. 特徴量群ごとの限界回収率寄与
5. 取り捨て推奨（データ根拠付き）
6. 最適部分集合（E）の提案
7. 黒字化ギャップ（控除率 20-25% 考慮・真の黒字は回収率≥1.25）と最も寄与の大きい改善レバー

## 9. 実行順序

1. **事前登録 commit**（本ファイル）← 本ステップ
2. **U0**: 指標統一検証（A2 の12系実行・09系 roi との差確認）
3. **A0-A3**: 12系統一 selector で再測定（U0 の結果次第で「9.1悪化」の前提を再判定）
4. **column-drop ハーネス**（`run_ablation.py`）構築
5. **D1-D3**（A 再測定で9.1悪化が確認された場合）→ **C1-C3** → **E** → **B1**
6. byte-reproducible 確認（2回実行で一致）
7. 成果物（ablation-results）執筆
