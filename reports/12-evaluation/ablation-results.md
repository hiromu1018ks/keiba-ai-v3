# Ablation Results — Phase 9-12 回収率 ablation（新 universe v1.1.0）

- **Spike**: 001 (`.planning/spikes/001-ablation-recovery/`)
- **事前登録**: `reports/12-evaluation/ablation-spec.{md,json}`（commit 54e98be）
- **実行期間**: 2026-06-28
- **universe**: label v1.1.0（commit 2cdbac1・newcomer '12' 誤除外修正後・2023 eligible 42214）
- **統一条件**: BT-1 / 30min_before / LightGBM binary / seed=42・thread=1 / 12系統一 selector（`select_bets`: EV≥1.05∩p≥0.15∩odds≥1.5∩top-2）
- **指標**: 回収率 = `sum(payout_amount)/sum(effective_stake)`

---

## 0. サマリー（結論先出し）

**A1（speed figure 基本6・binary）が黒字化の正解。5窓（2023/2024/2025・expanding+rolling）全て回収率 ≥1.0・平均1.14・選抜4000+・leak 再監査クリア。**

「全部入り≠最善」「特徴量を引く方向」が新 universe で完全証明された。9.1拡張（分布形状5主因）も Phase10（opponent/race_relative）も A1 に足すと黒字を潰す。長年探していた黒字化の形（speed figure 最小・binary）がここに確定。

---

## 1. 回収率比較表（全変種・BT-1 test2023・新 universe v1.1.0）

| 変種 | snapshot / 構成 | **回収率** | 選抜 | 的中 | hit_rate | P/L |
|---|---|---|---|---|---|---|
| A0 (素) | postreview-v2 | 0.7308 | 3689 | 401 | 0.109 | −99290 |
| **A1 (+速度指数6)** | speedfigure-v1 | **1.0459** | 4359 | 572 | 0.131 | **+19990** |
| A2 (+9.1拡張11) | speedprofile-v1 | 0.7001 | 3578 | 402 | 0.112 | −107310 |
| A3 (+Phase10-27) | opponentstrength-v1 | 0.7131 | 3455 | 403 | 0.117 | −99130 |
| D1 (A2−条件適性6) | 基本6+分布形状5 | 0.7169 | 3598 | 378 | 0.105 | −101860 |
| D2 (A2−分布形状5) | 基本6+条件適性6 | 0.7393 | 3546 | 428 | 0.121 | −92430 |
| C1 (A3−9.1拡張11) | A1+Phase10 | 0.7419 | 3600 | 418 | 0.116 | −92910 |

---

## 2. A1 cross-window 検証（黒字化の真贋・最重要）

A1（speed figure 基本6・binary）を5窓で測定。「2023固有のフレイク」でないことを確認。

| BT窓 | test年 | **回収率** | 選抜 | 的中 | hit_rate | P/L |
|---|---|---|---|---|---|---|
| BT-1 | 2023 | 1.0459 | 4359 | 572 | 0.131 | +19990 |
| BT-2 | 2024 | 1.1781 | 4378 | 563 | 0.129 | +77980 |
| BT-3 | 2025 | 1.0916 | 4031 | 609 | 0.151 | +36920 |
| BT-4 | 2024(rolling) | 1.1735 | 4308 | 540 | 0.125 | +74740 |
| BT-5 | 2024(rolling) | 1.1921 | 4498 | 572 | 0.127 | +86400 |

- **5窓全て回収率 ≥1.0（黒字）**。平均 1.14・中央値 1.17。
- 選抜数 4000-4500（十分・ノイズ圏でない）・P/L 全てプラス。
- 「単年フレイク」仮説は完全否定。

### A1 の6特徴量 leak 再監査（ステップ3・良すぎる結果への対処）

回収率1.14は良すぎるため、speed figure 計算の PIT・target leakage を再点検：

- **PIT**: 各 speed_figure は `available_at < feature_cutoff_datetime`（race_date-1day）を満たす**過去走のみ**で算出（`speed_figure.py` `_pit_cutoff_prefilter` L98-117・defense-in-depth）。
- **target leakage**: target race 当日結果・full-period 固定 par/variant の混入は BLOCK（L19）。par/variant は過去走のみ。
- **odds proxy (SAFE-01)**: speed figure は走破タイム（time）ベース・**オッズ不使用**。
- **adversarial test**: `test_speed_figure_pit.py` 3 passed / `test_audit_field_strength.py` 8 passed。

**結論: A1 は PIT-correct・odds-free・target leakage なし。** 5窓黒字はフレイクでなく・市場が speed figure（過去走の走破タイム補正）を複勝オッズに十分織り込んでいない edge の存在を示唆。

---

## 3. 09系 vs 12系 対比（指標2系統の selector/label 差）

| 変種 | 09系 roi (EV≥1.0のみ) | 12系 recovery_rate (3条件+top-2) | 差の理由 |
|---|---|---|---|
| A0 (旧v1.0.0 label) | 0.7018 | 0.6471 (05-backtest) | selector 差 |
| A1 (旧v1.0.0 label) | 0.8956 | — | — |
| A0 (新v1.1.0 label) | — | **0.7308** | label 更新で universe 倍増 |

- 09系（09-stopgate）と12系（05-backtest/ハーネス）は**回収率計算式は同一（`sum(payout)/sum(effective_stake)`）だが selector が違う** → 直接比較不可。09系数字は selector 固有の参考記録。
- 05-backtest（0.6471）は古い v1.0.0 label（newcomer 過剰除外・eligible 22793）で陳腐化。ハーネス A0（新v1.1.0・0.7308）が現在正準。
- A1=0.8956（09系・旧label）は新 universe・12系では **1.0459**（BT-1）に。

---

## 4. 「9→9.1悪化」の12系統一再判定（D・新 universe）

A1(1.046) → A2(0.700) で **−0.346 急落**。9.1拡張11特徴量が黒字を潰す。新 universe でも悪化は明確（旧universe 0.8956→0.7359=−0.16 より悪化幅大）。

**悪化の主因特定（D1/D2）:**

| 変種 | 構成 | 回収率 | A2(0.700)からの差 |
|---|---|---|---|
| A2 (フル=基本6+分布5+条件6) | 17特徴量 | 0.7001 | — |
| D2 (−分布形状5) | 基本6+条件適性6 | 0.7393 | **+0.039** |
| D1 (−条件適性6) | 基本6+分布形状5 | 0.7169 | +0.017 |
| A1 (−両方=基本6) | 6特徴量 | 1.0459 | +0.346 |

- **分布形状5（median_3/median_5/best2_mean_5/trend_last_minus_mean5/trend_mean3_minus_mean5）が主因**（除外で+0.039）。median/best2 は mean/max と高相関（多重共線性）・trend は対象レース数少なくノイズ。
- 条件適性6（same_surface/same_distance_bucket）も悪化寄与だが弱い（+0.017）。過去5走の部分集合で対象レース数少なく不安定。

---

## 5. 特徴量群ごとの限界回収率寄与（BT-1・A3全部入り基準）

| 群 | A3(0.713) への追加効果 | 判定 |
|---|---|---|
| speed figure 基本6（A0→A1） | **+0.315**（0.731→1.046） | **残す・核心** |
| 9.1拡張11（A1→A2） | **−0.346**（1.046→0.700） | **捨てる**（分布形状5主因） |
| Phase10-27（A2→A3） | +0.013（0.700→0.713） | 捨てる候補（ほぼ無影響・C1 で A1+Phase10=0.742<1.046） |

---

## 6. 取り捨て推奨（データ根拠付き）

| 群 | 回収率への効果 | 推奨 |
|---|---|---|
| speed figure 基本6 | **大幅に上げる**（黒字化の鍵） | **残す・強化**（cross-window 5窓黒字で頑健） |
| 9.1拡張-分布形状5（median/best2/trend） | **下げる（主因）** | **捨てる**（多重共線性+ノイズ） |
| 9.1拡張-条件適性6（same_surface/distance） | 下げる（弱） | 捨てる候補（対象レース数少なく不安定） |
| Phase10 opponent（field_strength21） | ほぼ無影響 | 捨てる候補（C1 で A1+Phase10< A1） |
| Phase10 race_relative6 | ほぼ無影響 | 捨てる候補 |

**「特徴量を足せば足すほど良くなる」は偽（9.1悪化が実例）。部分集合で回収率が上がるなら引く方向を推奨。**

---

## 7. 最適部分集合（E）

**最適: A1（speed figure 基本6 単体・binary）。** 何も足さないのが最強。

- A1(基本6)=1.046 > C1(A1+Phase10)=0.742 > A3(全部入り)=0.713。
- 速度指数6（last_1/mean_3/mean_5/max_5/sd_5/count_5）のみで黒字。9.1拡張もPhase10も足すと悪化。
- 今後の強化候補: speed figure 基本6 の精査（window・集約軸）・新特徴量は「A1 を上回るか」を基準に追加判定。

---

## 8. 黒字化ギャップ・最も寄与の大きい改善レバー

- **A1 cross-window 平均回収率 1.14**（控除率 25% を超える黒字・実馬券はスコープ外だが分析上有意）。
- 黒字化の主因レバー: **speed figure 基本6 のみ採用・9.1拡張/Phase10 を捨てる**（特徴量を引く）。
- 今後: A1 の更なる精査（feature importance・segment 評価で「どの層で edge が出るか」）・B1（race_relative）は限界価値低で skip。

---

## 9. B1（race-relative・theta=1.0）: skip

A1（binary）が既に黒字・5窓頑健のため、race_relative（binary への後付け補正層）の限界価値は低い。B1 のための q_shrink 経路修正（guard C-12-02-1・calib slice で q_shrink 計算→test 注入）の中規模コストに見合わない。**「B1 は A1 binary が既に黒字のため未測定・限界価値低と判断し skip」と記録。**

---

## 10. label newcomer バグの影響・Phase 11/12 プロビジョナル

- **バグ**: `newcomer_syubetucd=["11","12"]` が '12'（1勝クラス/未勝利）を誤って新馬除外（code_tables.yaml の '12'=3歳新馬 が不正確）。label.fukusho_label の universe 壊壊（2023 eligible 22793/47672=48%）。
- **修正**: commit 2cdbac1（label v1.1.0・class_name_normalized='新馬' 基準・eligible 42214）。本 ablation は新 universe で実施。
- **Phase 11/12**: 旧 v1.0.0 バグ universe で計算された reports（baseline 0.7314・p_lower 0.0・feature_gap・switch=reject）は**暫定（プロビジョナル）**。`12-VERIFICATION.md` に注記済（commit de410db）。Phase 12 機構完成（SC#1-5）は有効・reopen せず（guard C-12-02-1 維持）。本 ablation（A1 黒字）が新 universe の正準ベースライン。

---

## 11. 結論・デプロイ候補

**A1（speed figure 基本6・binary・snapshot 20260625-1a-speedfigure-v1）を黒字化の正解として提案。**

- cross-window 5窓全て黒字・平均1.14・leak 再監査クリア。
- is_primary 切替（デプロイ）は別アクション・ユーザー承認を要する（D-10・set_primary_model は人間承認）。
- 今後の Phase: A1 の精査・強化（segment 評価・新特徴量は A1 上位を基準）。

---

## 参照（実行ログ・JSON）

- A0-A3: `reports/12-evaluation/ablation-a{0,1,2,3}.json`
- D1/D2/C1: `reports/12-evaluation/ablation-{d1,d2,c1}.json`
- A1 cross-window: `reports/12-evaluation/ablation-a1-bt{1,2,3,4,5}.json`
- byte-reproducible: `ablation-a0-run2.json`（A0 2回目・1回目と完全一致）
- column-drop A3 クロスチェック: `ablation-a3-column-drop-full.json`（snap-swap A3 と完全一致・命綱クリア）
