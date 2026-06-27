# Phase 11: Race-Relative Probability Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 11-Race-Relative Probability Model
**Areas discussed:** 確率モデルの枠組み, 非劣化マージン事前登録, 制約とキャリブの順序, v1.0 binary との共存, k決定ルール, 欠損馬α_r母集団, α_r自己完結性保証

---

## 確率モデルの枠組み

### Q1.1 大筋の枠組み

| Option | Description | Selected |
|--------|-------------|----------|
| post-hoc 正規化 | binary 予測を race 内で softmax 的に再配分。trainer.py 再利用・低リスク。 | |
| listwise/PL 学習 | Plackett-Luce 等 listwise loss で根本から race-conditional 学習。理論的に綺麗だが再設計コスト高。 | |
| hybrid（binary+補正層） | binary 学習を保ち race-level 補正層で再正規化。中間。 | ✓ |

**User's choice:** hybrid（binary+補正層）
**Notes:** binary LightGBM/CatBoost 本体はそのまま、その上に race-conditional 補正層を乗せて sum(p)=払戻対象数 を実現。

### Q1.2 補正層の方式

| Option | Description | Selected |
|--------|-------------|----------|
| logit softmax + top-k | binary model の logit を race 内で softmax（温度 θ）で相対化。 | |
| rank-conditional isotonic | race 内予測順位ごとに isotonic を fit。同着/field size 境界が複雑。 | |
| 線形再スケール | binary p を sum(p)=k に線形スケール。logit 順序情報のみ。 | |
| (Other) logit temperature + per-race intercept normalization | sigmoid(s_i/θ + α_r)・二分探索で sum(p)=k・p∈(0,1) 厳密 | ✓ |

**User's choice:** logit temperature + per-race intercept normalization
**Notes:** binary model の base logit s_i・calib slice で温度 θ を事前登録候補から fit。各 race で p_i = sigmoid(s_i/θ + α_r) とし、sum_i p_i = k を満たす α_r を二分探索で解く。p∈(0,1) 厳密。k*softmax は p>1 リスクがあるため不採用。binary 本体不変・補正層のみ追加。「hybrid の中で一番堅い・既存 binary の順序情報を使い sum(p)=k を満たし確率境界も壊さない」。

### Q1.3 θ 選択指標

| Option | Description | Selected |
|--------|-------------|----------|
| odds-band miscalib | odds_band×p_bin miscalibration 最小。目的合致だが循環回避の文書化必要。 | |
| calibration_max_dev（安全） | §15.2 既存指標。後知恵すり替えリスク最小。 | |
| overall Brier/LogLoss | 確率品質標準。race 内再配分で θ 判別力が弱いリスク。 | |
| (Other) 制約付き選択 | Brier/LogLoss 足切り → overprediction penalty 最小 → tie-break calib_max_dev → θ=1 近傍 | ✓ |

**User's choice:** 制約付き選択（事前登録）
**Notes:** 候補集合は planner が事前登録・test 窓再選択禁止。足切り: overall Brier/LogLoss が binary baseline から事前登録マージン超え悪化する θ を除外。選択: 残候補から selected/high-EV 層・odds_band×p_bin の overprediction penalty（予測>実現の正方向誤差を重く）が最小の θ。tie-break: calibration_max_dev → 同値なら θ=1 近傍。「overall Brier/LogLoss だけだと投票層の病巣に鈍い。odds-band miscalib だけだと全体確率を壊す危険。だから 全体品質で足切り → 投票層過大予測で選択 が一番筋が通る」。

---

## 非劣化マージン事前登録

### Q2.1 全体非劣化マージン

| Option | Description | Selected |
|--------|-------------|----------|
| Phase11向け拡張 | Brier≤0.005/LogLoss≤0.010/AUC≤0.005。race-conditional 微小悪化許容・SC#2 本題優先。 | ✓ |
| Phase10同値（厳格） | Brier≤0.002/LogLoss≤0.005/AUC≤0.005。θ 大候補が足切りされ過大予測是正が弱まるリスク。 | |
| 相対率（+3%等） | binary baseline からの相対悪化率。スケール非依存だが判定が直感にくい。 | |

**User's choice:** Phase 11 向け拡張（Brier≤0.005/LogLoss≤0.010/AUC≤0.005）
**Notes:** AUC は logit 順序保存で維持。後追い緩和でなく・race-conditional 構造的変化への根拠再確認として事前登録（§11.2・θ足切り兼 SC#2 全体評価の統一閾値）。

### Q2.2 SC#2「改善」の定量化

| Option | Description | Selected |
|--------|-------------|----------|
| overprediction penalty 絶対改善 | odds_band×p_bin overprediction penalty が test 窓で v1.0 binary より絶対小。 | |
| selected-only calib_max_dev 改善 | 投票層 calib_max_dev が v1.0 より改善。§15.2 既存指標。 | |
| 統計的有意（bootstrap CI） | overprediction 減少が統計的に有意。Phase 12 と重複。 | |
| (Other) 3必須条件の複合 gate | overprediction penalty 改善 + selected/high-EV 過大予測改善 + selected-only calib_max_dev 非劣化 | ✓ |

**User's choice:** 主指標 overprediction penalty 絶対改善 + selected-only calib セーフガードの3必須条件 gate
**Notes:** (1) odds_band×p_bin overprediction penalty が v1.0 binary より低い、(2) selected/high-EV 層の平均予測率−実現率 が v1.0 より低い、(3) selected-only calib_max_dev が事前登録マージン超え悪化なし。bootstrap 統計有意は Phase 12 委譲・Phase 11 は方向性+非劣化 gate。θ は calib slice で選び test 窓で事前登録 gate で一回評価。「過大予測が減ったが selected 層が壊れた」を防ぐ。

---

## 制約とキャリブの順序

### Q3.1 統合順序

| Option | Description | Selected |
|--------|-------------|----------|
| base calib → 補正 | fit_prefit_calibrator で base logit 整定 → θ+α_r で sum(p)=k。calib→正規化で sum(p)=k 崩れない。 | ✓ |
| 補正 → 追加 calib | 補正後に calib すると sum(p)=k が崩れ α_r 再適用でループ。 | |
| 補正層のみ（calib 不使用） | θ+α_r が実質キャリブ。SC#1 fit_prefit_calibrator 要件と整合せず。 | |

**User's choice:** base calib → 補正
**Notes:** 実装パイプライン: raw binary model → fit_prefit_calibrator → p_cal → clip → logit(p_cal) → θ + per-race α_r → final p。補正後に追加 calib はしない。

---

## v1.0 binary との共存

### Q4.1 共存方針

| Option | Description | Selected |
|--------|-------------|----------|
| 新モデル is_primary・UI/EV も新 p | SC#2 通過で新モデル主に。UI/loader は新 p 表示。v1.0 binary は model_version 並列保持。 | |
| 並列比較のみ・is_primary は v1.0 維持 | 新モデルは model_version 並列・is_primary は v1.0 維持。比較レポート中心。 | ✓ |
| model_type 区別・is_primary 拡張 | model_type で binary/race_relative 区別・両方 is_primary 可能。概念拡張。 | |

**User's choice:** 並列比較のみ・is_primary は v1.0 維持
**Notes:** Phase 11 は確率構造の移行フェーズ・EV 本番切替は Phase 12（p_lower EV + 評価拡張）まで待つ方が安全。UI/EV をここで新 p に切り替えると、Phase 12 の評価前に実質的な運用基準が変わる。新 race-relative model は model_version で保存・Phase 11 では比較レポートで SC#2 を確認・is_primary 切替は Phase 12 の p_lower/selected-only/falsification まで見て判断。

---

## k決定ルール（追加 gray area・安全性核心）

### Q5.1 複勝払戻対象数 k の決定

| Option | Description | Selected |
|--------|-------------|----------|
| 予測時点固定頭数ルール | k = 発売開始時点頭数ベース固定（8頭以上=3・5-7頭=2・4頭以下=対象外）。同着は事後情報で k に反映しない。 | ✓ |
| 事後払戻実績 k | 実際の払戻対象数（同着含む）。予測時点では同着不明。 | |
| 予測固定+学習事後（非対称） | 予測時点固定 k・学習時事後 k。非対称で一貫性崩れる。 | |

**User's choice:** 予測時点固定頭数ルール
**Notes:** sum(p)=k の k は予測時点で確定・§10 ラベル基準（Phase 2 D-04 sales_start_entry_count）と整合。学習時 sum(label) は同着で k 超えうるが予測 p は固定 k（確率=予測時点・label=事後の不一致を許容・明文化）。

---

## 欠損馬α_r母集団（追加 gray area・安全性核心）

### Q6.1 欠損馬の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| neutral logit 仮置・全馬で sum(p)=k | 欠損馬に race central logit 仮置し母集団に含め p 算出。 | |
| 除外・非欠損馬で sum(p)=k | 欠損馬 p=NaN・α_r は非欠損馬で二分探索。Phase 10 D-09 踏襲だが過大リスク。 | |
| 残り枠均等配分 | 欠損馬の p = (k − 非欠損馬和)/欠損数。 | |
| (Other) logit 欠損を許容しない・fail-loud | binary logit 欠損は許容しない・前提条件 RuntimeError 検証 | ✓ |

**User's choice:** binary logit 欠損は許容しない（fail-loud）
**Notes:** α_r 母集団 = k 決定に使った予測対象の全馬・全馬に finite な base logit が存在することを前提条件として fail-loud に検証。特徴量欠損（過去走不足・speed profile 欠損等）は LightGBM/CatBoost が NaN として処理するため binary logit 欠損とは区別。p_cal は clip して logit 変換するが p_cal 自体が欠損する行があれば race-relative 補正に進まず RuntimeError。neutral logit 補完や非欠損馬だけへの k 配分は採用しない。「欠損 logit を中立補完するのは危険・バグを隠す。binary logit は全予測対象馬で必ず取得できるべき。『欠損馬をどう扱うか』ではなく予測対象馬に logit 欠損を出さないのが正しい設計」。

---

## α_r自己完結性保証（追加 gray area・安全性核心）

### Q7.1 α_r 自己完結性の保証強度

| Option | Description | Selected |
|--------|-------------|----------|
| adversarial unit test で証明 | tests/audit/ 追加・outcome 入れ替えで α_r/p 不変・他 race 情報混入検出・Phase 8 D-06 鋳型。 | ✓ |
| docstring + 軽量 assert | docstring 明文化・α_r 関数引数検証。 | |
| 構造的保証のみ | α_r 関数が logit+k のみ引数・コード構造で自明。 | |

**User's choice:** adversarial unit test で証明
**Notes:** α_r 二分探索は各 race の logit と k のみから決定（θ のみ calib slice fit・test 窓 outcome 不要）・これを adversarial test で機械証明。

---

## Claude's Discretion

- θ 候補集合の具体的値範囲（Phase 10 D-12 パターン踏襲・planner 事前登録）
- α_r 二分探索の収束基準・精度・p_cal clip 閾値（ε）
- overprediction penalty の厳密定義（重み付け・集約式・segment_eval.py binning 契約再利用）
- 補正層モジュール配置（新規 src/model/race_relative.py 等・既存 idiom 整合）
- model_version 命名（make_model_version パターン踏襲）
- CatBoost の logit 取得・適用（SC#3 両モデル bit-identical）
- BT窓・calib slice 期間（Phase 5/6/10 踏襲）
- 比較レポート reports/11-* の構成

## Deferred Ideas

- is_primary 切替・UI/EV の新 p 参照（Phase 12 p_lower/selected-only/falsification 評価後に判断）
- bootstrap 統計有意検定（Phase 12 EVAL-02 falsification と統合）
- p_lower（下側信頼限界）EV 判定（Phase 12 EV-01）
- 評価指標の本格拡張・正規 falsification test（Phase 12 EVAL-01/02）
- listwise/Plackett-Luce による根本的 race-conditional 学習（将来 refinement・本 Phase では hybrid 採用）
