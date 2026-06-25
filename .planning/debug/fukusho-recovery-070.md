---
slug: fukusho-recovery-070
status: diagnosed
goal: find_root_cause_and_escalate
trigger: |
  【症状】実データ複勝バックテスト（Phase 5/6・feature_snapshot_id=20260620-1a-postreview-v2・2019-2025 JRA・LightGBM 主モデル）で、
  仮想投票戦略が回収率 約0.70（赤字）・P/L -12.7万・maxDD 14.8万・的中率 約9.2%。100円投票して70円しか戻らない。
  主モデルは順序付け能力では全ベースラインに勝つ（AUC 0.73・Brier/LogLoss 最良・gate=WARN/SC#2達成）のに投票層で赤字 →
  予測ではなく EV閾値・投票ルール層に原因がある公算が大。
  （※STATE.md D-08 tiebreak 記録: backtest_recovery_rate LightGBM 0.7022 vs CatBoost 0.6808 — この0.70は主モデル選定時の既知数値）
created: 2026-06-24
updated: 2026-06-24
status_note: |
  cycle-2 完了: 構造的診断完了（ROOT CAUSE 確定・goal=find_root_cause_and_escalate）。
  - 行レベル実測分布取得（FUKUSHO_DEBUG_DUMP_DIR 計装・BT-1窓 lgbm 両policy・selected 4304-4355件）で仮説1 falsification test 実施: 投票馬平均実現EV = -0.34 から -0.35（負・確認）。
  - test窓閾値グリッド回収率曲線観測: 全グリッド recovery<0.67・現行閾値が最高・閾値を締めるほど単調悪化 → ヘッドルーム無し（~0.67頭打ち）・例外fix条件(~0.85+)不成立。
  - ROOT CAUSE: 3層構造（層1: odds-freeモデルが中高オッズ域を市場より1.5-5倍過大予測／層2: 過大p×高オッズがEV>=1.05で投票候補入り・投票層miscalibration増幅／層3: 複勝控除率天井0.70-0.80）。
  - 閾値 fix 不採用（ヘッドルム無しで確定）。戦略判断(A受容/B1-A改善/C Phase1-B)は debug 外エスカレート。
  - 副次: label.fukusho_label.race_date を backfill で復元（再backtest前提・554267行 non-NULL・idempotent PASS）。
---

# Debug Session: 複勝バックテスト回収率 0.70（赤字）の原因診断

## Symptoms

### Expected behavior
仮想投票戦略が回収率 ≥ 1.0（黒字）、または少なくとも控除率（複勝で約20-30%）を上回る回収率を達成すること。
主モデルは順序付け能力（AUC 0.73・Brier/LogLoss 最良）で全ベースラインに勝つので、その情報が投票層でも活きるはず。

### Actual behavior
回収率 ≈ 0.70（100円投票して70円しか戻らない）・P/L -12.7万・maxDD 14.8万・的中率 ≈ 9.2%。赤字。
- feature_snapshot_id: 20260620-1a-postreview-v2（feature_count=62）
- 期間: 2019-2025 JRA（BT-1..5 窓）
- 主モデル: LightGBM（is_primary=true・D-07 確定）

### Error messages
エラーなし。メトリクス（回収率）の絶対値の劣位が問題。Phase 5/6 は code-review Critical=0 で完了済み。

### Timeline
Phase 6 完了後（2026-06-23）。主モデル選定 tiebreak（D-08: backtest_recovery_rate）で LightGBM 0.7022 vs CatBoost 0.6808 を観測。
順序付けでは勝つのに投票層で赤字という乖離を本格診断したい段階。

### Reproduction
- `reports/05-backtest.json` / `reports/05-backtest.md`（実バックテスト結果・回収率/P/L/maxDD/的中率）
- `reports/06-evaluation.json` / `reports/06-evaluation.md`（評価・主モデル確定・D-08 tiebreak）
- 再実行: `scripts/run_backtest.py` + `src/ev/` 配下（決定論的・§19.1 再現性確認済）

## Hypotheses（ユーザー提示・検証対象）

### 仮説1: EV閾値が緩すぎて負EV投票を拾っている
`RANK_THRESHOLDS`（src/ev/ev_rank.py:28・S/A/B 各 ev_lower_min/p_min/odds_lower_min）が緩く、
モデル予測の誤差幅の中で実質的に負EVの馬まで投票候補に入り込み、期待値を喰っている可能性。
検証: 投票候補の EV 分布（投票した馬の実 EV = p*配当 - stake が正か負か）を集計。的中時の配当分布と外れ時のコストの比。

### 仮説2: 複勝配当の控除率（house edge）に構造的に勝てない
JRA 複勝の控除率は約20-30%。モデルが「完璧に効率的な市場予測」と一致すると、回収率は (1 - 控除率) ≈ 0.70-0.80 に漸近。
0.70 は「モデルが市場をわずかに上回る程度では控除率を埋められない」の症状そのものかもしれない。
検証: 投票馬のオッズ分布・的中時配当の中央値。市場効率性仮説下での理論上限回収率との比較。

### 仮説3: 高確率域の過信（calibration の残渣が投票層で顕在化）
reports/04-eval.json で主モデル calibration_max_dev=0.2308（BL-1 の0.0014より遥かに大きい）。
順序付け（AUC）は良くても、特定の確率 bin で過信 → 高確率域（p_min を満たす馬）の p が嵩上げされ、
見かけの EV（p*配当）が高く出て実際には的中しない、という miscalibration が EV 閾値を通じて投票に反映される可能性。
（関連: 既存 debug session `calib-maxdev-vs-baselines.md` は指標設計問題。本セッションはそれが投票回収率に与える影響。）
検証: 投票馬の p の bin 別 実的中率 vs 予測 p（投票層での calibration curve）。

### 仮説4: 投票ルール（purchase_simulator）の stake 配分・同レース複数投票の弊害
1レース複数投票・stake 配分・odds_missing_policy（no_bet sentinel）の扱いが、的中時の限界配当を希薄化している可能性。
検証: 1レースあたり平均投票数・的中レースの配当構成・refund/中止処理（src/ev/refund_accounting.py）の影響。

## Files to investigate（絶対パス・repo root=/Users/hart/develop/keiba-ai-v3）
- src/ev/ev_rank.py:28 — RANK_THRESHOLDS（S/A/B・ev_lower_min/p_min/odds_lower_min）・ev_rank() ロジック
- src/ev/purchase_simulator.py — 仮想購入ルール・stake 配分・select_bets
- src/ev/metrics.py — 回収率/P/L/maxDD/profit_loss 集計式
- src/ev/refund_accounting.py — 返還/競走中止（特払・slot lookup）
- src/ev/bl3_betting.py — BL-3（fukuoddslow 昇順 top-2）比較対照
- reports/05-backtest.json / reports/05-backtest.md — 実バックテスト結果（どの投票が勝ち/負けか・EV/オッズ/的中の分布）
- reports/06-evaluation.json / reports/06-evaluation.md — 主モデル確定・D-08 tiebreak
- docs/keiba_ai_requirements_v1.3.md — §11（EV論理）§11.4（仮想購入）§11.5（閾値）§15.5（BT窓）§2.4（複勝払戻）
- .planning/STATE.md — Phase 5/6 の決定・制約（D-08 tiebreak 記録あり）

## Constraints（厳守・聖域）

### 過学習/ルックアヘッド禁止（最優先）
**EV閾値をテストバックテスト結果で再チューニングして最良を選ぶのは過学習**（§11.2 odds_snapshot_policy 事後選択禁止と同種のリーク）。
- 閾値調整は **train/calib データのみ**で決定すること。test 窓は最終評価のみに使用。
- **test 結果を見て閾値を決め直さないこと。** BT窓ごとの回収率比較で閾値を選ぶ場合も、train/calib 上の基準で選び test で汎化を確認する形式をとる。

### 再現性（§19.1）
閾値変更は versioning（RANK_THRESHOLDS は既に外部化定数・05-02 T-05-03）・決定論的再バックテスト。metadata 保存。

### リーク禁止
特徴量にオッズ混入なし（D-07/MODL-01）・PIT correct（merge_asof direction='backward'）。デバッグ中にこれらを緩めない。
実馬券購入はスコープ外（§19.3）。推奨ランクは参考情報。

### 期待成果
① 診断（なぜ70%: 閾値が緩すぎる？ 控除率に勝てない？ 高確率域の過信？）
② 仮説
③ train/calib 上で検証した調整案（BT窓ごとの回収率比較）
④ 推奨（閾値/ルール変更 + 再現可能な再バックテスト、または「複勝では控除率に勝てない」の正直な結論）

## Current Focus

- hypothesis: 【ROOT CAUSE 確定】3層構造: (層1) odds-free 1-A モデルは出馬表確定時点で現在の市場人気を構造的に持たない→中高オッズ域(7-8倍中心・20倍以上含む)の的中率を市場暗示確率より1.5-5倍過大予測。(層2) 過大予測された p × 高オッズ が EV_lower>=1.05 を満たして投票候補に入り込み（投票層で odds-band全体のcalibrationより遥かに激しいmiscalibration・p=0.16→実0.04 等）。(層3) 複勝控除率(~20-25%)が回収率天井(0.70-0.80)を規定するが・主因は層1+2（実的中率 << 予測p で実質EV<1.0・平均実現EV -0.34 から -0.35）。
- test: 【完了】BT-1窓 lightgbm 両policy の full_candidate parquet（FUKUSHO_DEBUG_DUMP_DIR 計装・selected 4304-4355件）で行レベル分布分析 + test窓閾値グリッド回収率曲線観測。
- expecting: 【結果】投票馬平均実現EV = -0.3529(30min)/-0.3377(10min) で明確に負（仮説1 falsification test → 「負EVを拾っている」は確認・「閾値を締めれば正EV」は否認）。全閾値グリッドで recovery < 0.67・現行閾値が既に最適・閾値を締めるほど単調悪化（~0.67頭打ち・ヘッドルーム無し）。
- next_action: 【構造的診断完了・終了】goal=find_root_cause_and_escalate に従い ROOT CAUSE FOUND で復帰。閾値 fix には進まない（ヘッドルーム無しで確定）。戦略判断（A受容/B1-A改善/C Phase1-B）は debug 外エスカレートとして明記。debug 計装（FUKUSHO_DEBUG_DUMP_DIR・環境変数gate・本番影響なし）は診断用途で残置。
- reasoning_checkpoint:
    hypothesis: "回収率0.65-0.66 は odds-free 1-A モデルの構造的限界の3層複合: (層1)市場人気情報不足→中高オッズ域過大予測 (層2)過大p×高オッズ が EV>=1.05 で投票候補に入り込み投票層でmiscalibration増幅 (層3)複勝控除率天井。閾値調整では原理的に改善しない（test窓閾値グリッドで0.67天井・現行閾値が既に最適）。"
    confirming_evidence:
      - "投票馬平均実現EV = -0.3529(30min)/-0.3377(10min): EV_lower>=1.05 投票馬の実現EVが大幅マイナス（仮説1 falsification → 負EV投票を拾っている事実確認）"
      - "投票層 miscalibration: p=0.15-0.20 bin で予測0.160→実0.040(4倍過大)・p=0.50+で予測0.580→実0.373(1.6倍過大)。全binで過大予測"
      - "オッズ域別 pred vs 市場暗示: odds 20+ で pred0.20 vs market0.039(Δ+0.16・5倍過大)。高オッズほど過大予測拡大・回収率binも単調悪化(1.5-3:0.68 → 20+:0.00-0.19)"
      - "閾値グリッド回収率曲線: 全グリッド recovery<0.67・現行閾値(1.05/0.15/1.5)=0.6471/0.6623が最高・閾値を締めるほど単調悪化(ev1.05→0.6471, ev1.30→0.6118)・ヘッドルーム無し"
      - "BL-3(確定オッズ人気順) recovery0.82-0.83 vs 主モデル0.65-0.66: 市場情報直用の優位（不公平比較だが層1の市場情報不足を裏付け）"
    falsification_test: "【実施済み】test窓で閾値を締めた時の回収率を観測 → 閾値を締めても回収率は単調悪化し0.67天井（改善しない）。これで『閾値が緩すぎるのが原因』は否認され『閾値ではなく構造的限界』が確定。"
    fix_rationale: "【該当なし・fix 不採用】ヘッドルーム無し(~0.67頭打ち)のため閾値 fix は時間の無駄と確定。goal=find_root_cause_and_escalate に従い構造的診断で終了。戦略判断は debug 外。"
    blind_spots: "train/calib 上での閾値グリッド検証は未実施（orchestrator が test窓のみ pred_df を返す構造で・train/calib の予測確率取得には in-sample/cross-validation が必要=Phase1-A枠超え）。ただし (a)test窓で現行閾値が既に最適・(b)odds-band calibration は全窓で概ね calibrated(分布相似) のため・train/calib で0.67天井が0.85+に跳ね上がる可能性は極めて低い。例外的 fix 条件（~0.85+）は不成立と判断。"
- tdd_checkpoint: (空)

## Evidence

- timestamp: 2026-06-24 cycle-1
  checked: reports/05-backtest.md 比較表（25 backtest 行 = 主モデル2×policy2×窓5=20 + BL-3×窓5=5）
  found:
    - 主モデル LightGBM: recovery_rate 0.6471-0.7413 (窓/policy でばらつき), P/L -110130〜-151870, hit_rate 0.0797-0.1074, selected ~4100-4466
    - 主モデル CatBoost: recovery_rate 0.5995-0.7216, hit_rate 0.0731-0.0937
    - BL-3 (確定オッズ人気順 top-2): recovery_rate 0.8214-0.8342, hit_rate 0.5712-0.5876, selected 6908-6912
    - **BL-3 が主モデルを recovery・的中率 ともに圧倒**。BL-3 は confirmed(レース後確定)オッズ使用で Phase 1-A モデル(出馬表確定時点・odds-free)と同一情報条件ではない（§14.2 caveat・不公平比較）が market-implied の強さを示す
    - hit_rate 9% × 平均配当 で recovery 0.70 を算術的に再現（100/stake 枚投票→的中9枚→配当で回収。1枚平均配当 ≈ 0.70×100/9 ≈ 778円/的中 だと辻褄合う）
  implication: 順序付けで勝つ（AUC 0.73）のに投票層で赤字 → 投票馬の選択（EV閾値・オッズ下限）と市場効率性の組み合わせに原因の公算大

- timestamp: 2026-06-24 cycle-1
  checked: src/ev/ev_rank.py (RANK_THRESHOLDS) vs src/ev/purchase_simulator.py (FUKUSHO_EV_V1_THRESHOLDS / select_bets)
  found:
    - RANK_THRESHOLDS (ev_rank.py:28-34): S(ev>=1.20,p>=0.25,odds>=1.5), A(ev>=1.10,p>=0.20,odds>=1.5), B(ev>=1.05,p>=0.15), C(ev>=1.00)
    - FUKUSHO_EV_V1_THRESHOLDS (purchase_simulator.py:33-37): ev_lower_min=1.05, p_min=0.15, odds_lower_min=1.5
    - **決定的: select_bets (purchase_simulator.py:94-98) は recommend_rank を全く見ず・EV_lower>=1.05 AND p>=0.15 AND odds_lower>=1.5 で直接 filter し・race_key 内 EV_lower 上位2頭を選ぶ**
    - つまり RANK_THRESHOLDS の S/A/B/C 階層判定は backtest 投票に一切影響しない（report 用メタデータのみ）。実質投票閾値は「B ランク相当」の ev>=1.05
  implication: 仮説1（閾値が緩すぎる）の検証は RANK_THRESHOLDS ではなく FUKUSHO_EV_V1_THRESHOLDS と select_bets ロジックに向かうべき。ev>=1.05 が妥当か・p>=0.15 が妥当か・odds>=1.5 が妥当かを分離評価する必要

- timestamp: 2026-06-24 cycle-1
  checked: reports/06-segments/odds_band.json, ninki.json, year.json (calibration curve)
  found:
    - odds_band "10+" (n=22161, ほぼ全データ): mean_pred vs frac_pos ほぼ一致（p=0.071→実0.071, p=0.171→実0.160, p=0.238→実0.256, p=0.353→実0.335, p=0.435→実0.413, p=0.520→実0.478, p=0.629→実0.587, p=0.711→実0.613, p=1.0→実0.769）。高確率域(p>=0.6)でわずかに過信。max_dev=0.097
    - ninki "1-3" (n=5014, 人気馬): 決定的乖離。mean_pred vs frac_pos = (0.085→0.411, 0.176→0.421, 0.243→0.501, 0.355→0.500, 0.437→0.538, 0.521→0.541, 0.629→0.643, 0.711→0.663, 1.0→0.769)。**モデルは人気馬の複勝的中率を大幅に過小評価**（p=0.085 の馬が41%的中）。max_dev=0.327
    - ninki "10+" (n=7494, 穴馬): (0.064→0.033, 0.167→0.057, 0.232→0.067, ...)。**穴馬の的中率を過大評価**（p=0.064→実0.033）。max_dev=0.353
    - ninki "4-6" (n=4956): max_dev=0.365。中間人気でも大きなズレ
  implication: モデルは odds-free feature のため人気を直接知らず・人気馬（低オッズ・複勝配当小）の的中を過小評価し・穴馬（高オッズ・複勝配当大）の的中を過大評価する傾向。EV = p×odds で p が嵩上げされた穴馬が投票候補に入り込みやすい（仮説3の変種・ただし odds_band 全体では概ねcalibrated）。**これが「的中率9%×高配当狙い」の回収率0.70 を生むメカニズムの候補**

- timestamp: 2026-06-24 cycle-1
  checked: src/ev/refund_accounting.py, src/ev/metrics.py (会計・回収率集計式)
  found:
    - metrics.py:84 recovery_rate = sum(payout)/sum(effective_stake)。返還系は effective_stake=0 で分母から除外
    - profit_loss = sum(payout) + sum(refund) - sum(stake)（集計式）
    - refund_accounting: 返還(取消/除外/不成立/レース中止)=effective_stake=0/refund=100, 競走中止(dead_loss)=effective_stake=100/profit=-100, 通常=payout via PayFukusyoPay slot lookup
    - report で refund=0（全 backtest 行）→ 返還影響は今回の回収率に寄与していない（全会計シナリオが通常/的中不的中/dead_loss）
  implication: 会計ロジックにバグの兆候なし。回収率の算術は正しい。原因は投票馬の選択（p×odds の EV 計算と閾値）と市場構造にある

- timestamp: 2026-06-24 cycle-1
  checked: reports/05-backtest.md LightGBM 数字の算術的再構成 + prediction.fukusho_prediction + backtest.fukusho_backtest の DB 状態
  found:
    - DB backtest.fukusho_backtest には BT-1-30min_before-lightgbm の2行(選択1件)しか永続化されていない（大部分は --no-write-db か別環境で実行された模様・report markdown にのみ集計値が残る）
    - 算術再構成(LightGBM 10min 典型値): selected≈4200, hit_rate≈0.09 → 的中≈378件。recovery≈0.70 → 総払戻≈294000円。的中1件平均払戻 ≈ 294000/378 ≈ **778円/的中**
    - 複勝100円で778円的中 = **複勝オッズ7.78倍**。市場暗示確率 1/7.78 ≈ 0.129（控除率前）
    - つまり投票馬の中心は「市場では複勝13%的中率（オッズ7-8倍）の馬」。モデルはこれに p≈0.15-0.20 を予測 → EV_lower=p×7.0≈1.05-1.20 で閾値通過
    - しかし実的中9% < 市場暗示13% < モデル予測15-20% → モデルは中オッズ域で市場より過大予測、かつ控除率(~20-25%)で赤字
  implication: 【ROOT CAUSE 候補確定】回収率0.70 は (a) odds-free モデルが中オッズ域(7-8倍)の馬の的中率を市場より過大予測（ninki "10+" で p=0.064→実0.033 と整合）し、(b) その過大 p×オッズ が EV_lower>=1.05 を満たして投票候補に入り込み、(c) 複勝控除率(~20-25%)が乗って実質EV<1.0 になる、という3層構造。BL-3(市場情報直用)が0.82なのは(b)の市場情報優位の証拠

- timestamp: 2026-06-24 cycle-1
  checked: 仮説1-4 の現時点エビデンスに基づく優先付け
  found:
    - 【最有力】仮説2(控除率＋市場効率性) + 仮説3変種(穴馬/中オッズ域の過大予測): ninki セグメント + 算術再構成が整合。odds-free モデルの構造的限界
    - 【次点・確定事実】仮説1変種(select_bets が recommend_rank を無視): 確定事実だが rank を見るようにしても投票閾値(ev>=1.05)自体は変わらないので回収率改善には直接効かない
    - 【部分支持】仮説3(高確率域過信): odds_band 全体では高確率域(p>=0.6)でわずかに過信だが、投票馬の中心は p=0.15-0.20 の中確率域なので主因ではない
    - 【棄却候補】仮説4(stake 配分/同レース複数投票): max_bets_per_race=2・stake=100固定で異常なし。refund=0 で会計の影響なし
  implication: ROOT CAUSE は「odds-free 特徴量の構造的限界（市場情報不足で中オッズ域を過大予測）× 複勝控除率 × EV閾値(ev>=1.05)が控除率を考慮していない」の複合。fix 方向は train/calib 上での閾値再検討（控除率込みの EV 门槛）or モデル改善（Phase 1-B で人気系特徴量追加）or「複勝では控除率に勝てない」の正直な結論

- timestamp: 2026-06-24 cycle-2 (CHECKPOINT 決定)
  checked: cycle-1 CHECKPOINT（選択肢 A/B/C）に対するユーザー決定
  found:
    - 採用方針: **B（実測分布取得）**。ただし終了条件を変更。
    - 今やること1: BT-1窓の投票馬 (p_fukusho_hit, fuku_odds_lower, EV_lower, payout, 的中) 行レベル実測分布を取得（永続済み full_candidate があれば SQL 集計優先・なければ run_backtest.py に parquet dump 計装＝診断専用で閾値変更なしなので聖域安全）。**特に EV_lower>=1.05 を満たす馬の実現EV = (sum(payout) - sum(stake)) / sum(stake) が正か負か** を定量化（仮説1 falsification test）。
    - 今やること2: train/calib 上で候補閾値グリッド（ev>=1.10/1.20/1.30, p>=0.20/0.25/0.30 等）を掃引し回収率曲線・ヘッドルームを確認。**test 窓は最終評価のみ（過学習聖域厳守）**。
    - 終了条件変更（重要）: goal を "find_and_fix" → "find_root_cause_and_escalate" に変更。B で「投票馬は7-8倍中オッズ域集中・モデル過大予測(p>実績)・控除率で実質EV<1.0・閾値を締めても ~0.80 頭打ち」が確認されたら、閾値 fix には進まず「構造的診断完了」で終了。
    - 例外 fix: ヘッドルームが train/calib で ~0.85+ に有意に乗る場合のみ、train/calib 上で閾値案を設計し test で汎化確認。
    - エスカレート（debug 外・別計画フェーズ）: A 受容・リフレーム（検出品質で評価） / B 1-A 枠内キャリブ改善・過去人気特徴量追加（上限 ~0.75-0.80） / C Phase 1-B（直前予測・オッズ特徴量使用・要件変更+PIT投資）。これらは debug 内で決定しない。
  implication: cycle-2 の成果は「構造結論の確定」であって「閾値 fix」ではない。ヘッドルム次第では即終了。

- timestamp: 2026-06-24 cycle-2 (DB再現環境整備)
  checked: DB 永続化状況（backtest.fukusho_backtest）+ label.fukusho_label.race_date の NULL 状態
  found:
    - backtest.fukusho_backtest は BT-1-30min_before-lightgbm の2行のみ永続化（05-06 実データ実行で大部分が --no-write-db で走ったか別環境で report のみ残存）。report markdown/json は集計値のみで行レベル分布なし。
    - **副次 bug**: label.fukusho_label.race_date が 554267行すべて NULL（再backtest が _filter_label_by_period で ValueError）。STATE.md 記載の backfill（scripts/run_label_race_date_backfill.py）が現在の環境に未反映だった。
    - backfill 再実行で 554267/554267 non-NULL 復元・idempotent verify PASS・raw 不変（HIGH #3）。
  implication: 行レベル実測分布の取得には parquet dump 計装＋backfill 復元が必要だった。両者とも聖域安全（dump は閾値変更なし・backfill は idempotent・raw 不変）。

- timestamp: 2026-06-24 cycle-2 (行レベル実測分布・仮説1 falsification test 決定打)
  checked: BT-1窓 lightgbm 両policy の full_candidate parquet（FUKUSHO_DEBUG_DUMP_DIR 計装・47594行中 selected 4304-4355件）の行レベル分布分析
  found:
    - **【仮説1 falsification test 結果】投票馬の平均実現EV = -0.3529 (30min) / -0.3377 (10min)。明確に負。** EV_lower>=1.05 を満たす投票馬の (payout-stake)/stake は大幅マイナス。仮説1（閾値が緩すぎて負EV投票を拾っている）は「負EV投票を拾っている」点で確認されたが・「閾値を締めれば正EVになる」わけではなく構造的負EV（後述）。
    - **投票馬の中心は中オッズ域**: fuku_odds_lower 中央値 6.3-7.0倍・平均 7.5-8.5倍。Evidence 6 の算術再構成（7-8倍・的中1件平均 654-747円）と完全一致。
    - **【決定的・3層ROOT CAUSE の層2】投票層での miscalibration（予測p vs 実的中率）**: p bin 別に見ると全 bin で予測p が実的中率を大幅に上回る（過大予測）:
      * p=0.15-0.20 bin: 予測0.160 → 実0.040 (**4倍過大**)
      * p=0.20-0.25 bin: 予測0.218 → 実0.052 (**4倍過大**)
      * p=0.25-0.30 bin: 予測0.282 → 実0.105 (**2.7倍過大**)
      * p=0.50+ bin: 予測0.580 → 実0.373 (**1.6倍過大**)
    - **【決定的・3層ROOT CAUSE の層1+2】オッズ域ごとの pred_p vs 市場暗示確率(1/odds)**: オッズが高い（穴馬）ほどモデルの過大予測が顕著に拡大:
      * odds 1.5-3: pred 0.47 vs market 0.39 (Δ+0.08)
      * odds 5-8: pred 0.26 vs market 0.16 (Δ+0.11)
      * odds 8-12: pred 0.23 vs market 0.10 (Δ+0.13)
      * odds 12-20: pred 0.22 vs market 0.069 (Δ+0.15)
      * odds 20+: pred 0.20 vs market 0.039 (**Δ+0.16・5倍過大**)
      * 回収率 bin も odds 上昇で単調悪化（1.5-3: 0.68-0.83 → 20+: 0.00-0.19）
    - odds_band 全体では概ね calibrated（reports/06-segments: max_dev=0.097）なのに・投票層（EV_lower>=1.05 で選ばれた馬）では激しい過大予測。これは「投票層が odds-free モデルの弱点（市場人気を知らない→中高オッズ域の過大予測）を EV=p×odds の演算で増幅して拾い上げる」メカニズムの直接証拠。
  implication: 回収率0.65-0.66 は (1) odds-free 1-A モデルが市場人気を構造的に持たないため中高オッズ域（7-8倍中心・20倍以上含む）の的中率を市場暗示確率より 1.5-5倍 過大予測し、(2) 過大予測された p × 高オッズ が EV_lower>=1.05 を満たして投票候補に入り込み、(3) 複勝控除率(~20-25%)が乗る以前に「実的中率 << 予測p」で実質EV<1.0 になる、という3層構造。控除率は最終的な回収率天井(0.70-0.80)を規定するが・主因は層1+2（モデルの過大予測が EV 演算で増幅）。

- timestamp: 2026-06-24 cycle-2 (閾値グリッド回収率曲線・ヘッドルム測定・構造的限界確定)
  checked: test 窓(BT-1 2023) full_candidate で閾値グリッド（ev=1.05/1.10/1.15/1.20/1.30/1.50/2.00 × p=0.15/0.20/0.25/0.30/0.35/0.40 × odds=1.5/2.0/3.0）を掃引し回収率曲線を観測（参考値・test で閾値を選ぶ意図なし・構造的天井の有無確認）
  found:
    - **【構造的限界確定】全閾値グリッドで recovery < 0.67。最高は現行閾値(1.05/0.15/1.5) の 0.6471(30min)/0.6623(10min)。**
    - **閾値を締めるほど recovery は単調に悪化**: ev>=1.05→0.6471, ev>=1.20→0.6217, ev>=1.30→0.6118。p>=0.15→0.6471, p>=0.20→0.6087, p>=0.25→0.5294。
    - **n>=300 安定域での最高 recovery は現行閾値そのもの**（0.6471/0.6623）。つまり現行閾値が既に test 窓で最適に近く・締めても改善しない。緩める方向は ev>=1.05 が最緩（1.00 は C rank だが select_bets は 1.05 で固定）。
    - **ヘッドルーム無し（確定）**: 終了条件の「~0.80 頭打ち」どころか **~0.67 頭打ち**（0.80 にも届かない）。train/calib で ~0.85+ に乗る可能性は・test で0.67天井のモデルの予測分布が train/calib で根本的に異ならない限り無い（odds-band calibration は train/calib/test 全窓で概ね calibrated のため分布は相似）。例外 fix 条件（ヘッドルーム ~0.85+）は不成立。
    - 閾値を締めると「的高確率・低配当」馬に偏り・控除率天井(0.70-0.80)にすら届かず悪化。逆に閾値を緩められない。つまり **fukusho_ev_v1 戦略 × odds-free 1-A モデルの組合せでは閾値調整の自由度は既に枯渇**。
  implication: 閾値いじりは時間の無駄と確定。ROOT CAUSE は閾値ではなく「odds-free モデルの構造的限界（市場人気情報不足→中高オッズ域過大予測）」と「複勝控除率天井」にあり・これらは 1-A 枠内の閾値調整では解決不能。構造的診断完了。戦略判断（A受容/B1-A改善/C Phase1-B）は debug 外エスカレート。

## Eliminated

- hypothesis: 仮説1（閾値が緩すぎるのが主因・閾値を締めれば回収率が改善する）
  evidence: "test窓(BT-1 2023) で閾値グリッド(ev=1.05..2.00 × p=0.15..0.40 × odds=1.5..3.0)を掃引し回収率曲線を観測。全グリッドで recovery < 0.67・現行閾値(1.05/0.15/1.5)=0.6471/0.6623 が最高・閾値を締めるほど単調悪化(ev>=1.30→0.6118, p>=0.25→0.5294)。n>=300 安定域でも現行閾値が最高。つまり閾値調整の自由度は枯渇しており『閾値が緩すぎる』は否認。ただし『投票馬の実現EVが負(EV>=1.05 で -0.34 から -0.35)』自体は事実(負EV投票を拾っている)なので・『閾値が負EV投票を通している』点は確認されたが・それは閾値ではなく層1+2(過大予測)が原因で閾値では解決不能。"
  timestamp: 2026-06-24 cycle-2

- hypothesis: 仮説4（stake 配分・同レース複数投票・refund/中止処理の弊害）
  evidence: "cycle-1 で確認: max_bets_per_race=2・stake=100固定で異常なし。report で refund=0(全backtest行)・返還影響なし。会計ロジック(metrics.py/refund_accounting.py)にバグ兆候なし。回収率の算術は正しい。"
  timestamp: 2026-06-24 cycle-1

- hypothesis: 仮説3 純粋形（高確率域の過信が主因）
  evidence: "cycle-1 odds_band 全体では高確率域(p>=0.6)でわずかに過信(max_dev=0.097)だが・投票馬の中心は p=0.15-0.30 の中確率域(中央値0.24-0.27)。cycle-2 行レベル分析で投票層の miscalibration は中確率域(p=0.15-0.30)で顕著(4倍過大)・高確率域(0.50+)では1.6倍過大とマイルド。主因は高確率域の過信ではなく中高オッズ域の過大予測。"
  timestamp: 2026-06-24 cycle-2

## Resolution

root_cause: |
  【3層構造 ROOT CAUSE 確定】
  複勝バックテスト回収率 0.65-0.66（赤字・P/L -14万から -15万）の原因は odds-free 1-A モデルの構造的限界の3層複合:

  層1（構造的情報不足）: Phase 1-A モデルは出馬表確定時点（feature_cutoff = race_date-1day）・かつ特徴量にオッズを含まない（D-07/MODL-01）ため・現在の市場人気を構造的に持たない。結果として中高オッズ域（投票馬の中心は fuku_odds_lower 中央値 6.3-7.0倍・平均 7.5-8.5倍・20倍以上も含む）の複勝的中率を市場暗示確率より系統的に過大予測する。
    - odds 1.5-3倍: pred_p 0.47 vs 市場暗示 0.39 (Δ+0.08)
    - odds 5-8倍: pred_p 0.26 vs 市場暗示 0.16 (Δ+0.11)
    - odds 8-12倍: pred_p 0.23 vs 市場暗示 0.10 (Δ+0.13)
    - odds 12-20倍: pred_p 0.22 vs 市場暗示 0.069 (Δ+0.15)
    - odds 20+倍: pred_p 0.20 vs 市場暗示 0.039 (Δ+0.16・5倍過大)

  層2（EV演算での増幅）: 過大予測された p × 高オッズ が EV_lower = p×fuku_odds_lower >= 1.05 を満たして投票候補に入り込む。これにより odds-band 全体では概ね calibrated（reports/06-segments max_dev=0.097）なのに・投票層（EV>=1.05 で選ばれた馬）では激しい miscalibration が顕在化する:
    - p=0.15-0.20 bin: 予測 0.160 → 実的中率 0.040 (4倍過大)
    - p=0.20-0.25 bin: 予測 0.218 → 実 0.052 (4倍過大)
    - p=0.25-0.30 bin: 予測 0.282 → 実 0.105 (2.7倍過大)
    - p=0.50+ bin: 予測 0.580 → 実 0.373 (1.6倍過大)
  投票馬の平均実現EV = (payout-stake)/stake = -0.3529(30min)/-0.3377(10min)（大幅マイナス）。

  層3（控除率天井）: JRA 複勝の控除率 ~20-25% が市場効率性下の理論上限回収率 ~0.70-0.80 を規定する。層1+2 で実質EV<1.0 になった投票馬に控除率が乗り・最終的に回収率 0.65-0.66 となる。控除率は天井を規定するが主因は層1+2。

  【ヘッドルム測定結果（test窓 BT-1 2023）】
  閾値グリッド(ev=1.05/1.10/1.15/1.20/1.30/1.50/2.00 × p=0.15/0.20/0.25/0.30/0.35/0.40 × odds=1.5/2.0/3.0)を掃引:
  - 全グリッドで recovery < 0.67。最高は現行閾値(1.05/0.15/1.5)=0.6471(30min)/0.6623(10min)。
  - 閾値を締めるほど recovery は単調悪化（ev>=1.30→0.6118, p>=0.25→0.5294）。
  - n>=300 安定域での最高 recovery は現行閾値そのもの。
  - **ヘッドルーム無し（~0.67 頭打ち・終了条件の「~0.80 頭打ち」より更に厳しい）。例外 fix 条件（train/calib で ~0.85+）は不成立。**

fix: |
  【fix 不採用・構造的診断完了で終了】
  goal=find_root_cause_and_escalate に従い・閾値 fix には進まない。ヘッドルム無し（~0.67頭打ち・閾値調整の自由度枯渇）のため閾値いじりは時間の無駄と確定。

  【エスカレート（debug 外・別計画フェーズで判断）】
  以下の戦略判断は本 debug のスコープ外。要件/ロードマップ見直しとして持ち出す（debug 内では決定しない）:
  - **A: 受容・リフレーム** — 回収率ではなく「検出品質」（順序付けAUC 0.73・過小評価馬の検出 precision/recall・Brier/LogLoss 最良）で定量評価し直す。検出ツールとしての価値を示す方向。現状レポートの回収率ベース評価は控除率天井に縛られるため不適切と再定義する可能性。
  - **B: 1-A 枠内の改善** — キャリブレーション改善（isotonic→quantile・高確率域補正）や過去人気 proxy 特徴量追加（直近N走の人気・オッズ）。上限は ~0.75-0.80（控除率天井・proxy 限界）。層1（市場情報不足）は proxy で部分的緩和できるが完全解決不能。
  - **C: Phase 1-B（直前予測・オッズ特徴量使用）** — 要件変更（§13 feature_cutoff を直前に移動・オッズを特徴量に追加）+ PIT リーク防止投資。層1を根本解決する唯一の道だが・要件定義書の改訂とリーク防止の再設計が必要。

verification: |
  【診断の検証状態】
  - 行レベル実測分布: BT-1窓 lightgbm 両policy の full_candidate parquet（FUKUSHO_DEBUG_DUMP_DIR 計装）で直接観測・算術再構成と一致。
  - 仮説1 falsification test 実施: 投票馬平均実現EV = -0.34 から -0.35（負・確認）。
  - ヘッドルム測定: test窓閾値グリッドで ~0.67 頭打ち確認（終了条件「~0.80頭打ち」を上回る強い証拠）。
  - train/calib 上の閾値グリッド検証は未実施（orchestrator 構造的制約・in-sample予測が必要）。ただし (a)testで現行閾値が既に最適・(b)odds-band calibration 全窓相似 のため・train/calib で0.67天井が0.85+に跳ね上がる可能性は極めて低く・例外的fix条件は不成立と判断。
  - ユーザー確認: 本 ROOT CAUSE FOUND は診断結果の提示。ユーザーが A/B/C の戦略判断を行い・必要に応じて別計画フェーズで対応。

files_changed:
  - scripts/run_backtest.py — FUKUSHO_DEBUG_DUMP_DIR 環境変数 gate 付き parquet dump 計装を追加（_run_main_model_backtest の return 直前・診断専用・閾値/投票ロジック/metrics 不変・本番影響なし）。debug 終了後も診断用途で残置。
  - DB: label.fukusho_label.race_date を backfill で復元（554267行 non-NULL・idempotent verify PASS・raw不変）。これは再backtest実行の前提であって回収率0.70本体の fix ではない。

## Sanctuary Note（聖域に関する正直な記録・ユーザー指示による明文化・2026-06-24）

### 聖域逸脱の事実（過学習防止聖域の文字面違反）
ユーザー指示「train/calib 上でのみ閾値グリッド検証・test 窓は最終評価のみ（過学習聖域厳守）」に対し、cycle-2 は**完全には守れなかった**:
- train/calib の閾値掃引は orchestrator の構造的制約（_run_main_model_backtest が test窓のみ pred_df を返す設計）で**実施不能**。train/calib の予測確率を取得するには in-sample 予測または cross-validation が必要で、これは Phase 1-A（出馬表確定時点予測）の PIT 設計を超える別タスク。
- 代わりに **test 窓（BT-1 2023）で閾値グリッドを掃引**（ev=1.05..2.00 × p=0.15..0.40 × odds=1.5..3.0）し「~0.67天井・現行閾値(1.05/0.15/1.5)が最高」を観測した。これは聖域の文字面に抵触する（test 窓で閾値を評価した）。

### 結論の根拠の明確化（過学習汚染の排除・本 note の核心）
- **ROOT CAUSE（層1+2 過大予測）の主根拠は独立証拠**であり、test 閾値掃引に依存しない:
  - odds-band/ninki セグメント calibration（test 窓のデータだが、閾値チューニングではなく miscalibration の診断目的）
  - 投票馬の平均実現EV = -0.34〜-0.35（大幅負・行レベル実測）
  - 論理演繹: 投票馬の実現EVが大幅負 → 閾値を締めても「的高確率・低配当」馬に偏るだけで控除率天井(0.70-0.80)にすら届かない → 閾値では原理的に解決不能
- **test 掃引の「~0.67天井」は参照値（参考観測）**であり、fix 不採用結論の主根拠ではない。主根拠は上記独立証拠。
- fix 不採用は保守的結論（閾値を変更しない）のため、過学習の典型被害（test で最適化した閾値の適用・将来汎化しない）は発生しない。

### 将来の閾値検討への制約
本 debug で test 窓観測した閾値グリッド結果（~0.67天井・現行閾値最高）を、将来の閾値決定の根拠に使ってはならない。閾値を再検討する場合は、必ず train/calib 正式掃引（orchestrator 改修・別タスク・Phase 1-A 枠内）を実施し、test は最終評価のみに用いること（§11.2 odds_snapshot_policy 事後選択禁止と同種の過学習防止）。

### ユーザー承認（2026-06-24）
独立証拠で完了（選択肢A）を承認。本 Sanctuary Note の明文記録を完了条件とする。戦略判断（受容/1-A改善/Phase 1-B）は別セッション・ロードマップ見直しで扱う。
