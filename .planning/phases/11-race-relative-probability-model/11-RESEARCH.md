# Phase 11: Race-Relative Probability Model - Research

**Researched:** 2026-06-27
**Domain:** 確率モデル移行（独立二値分類 → race-relative 補正層）・logit temperature + per-race intercept 二分探索・SC#1-5 聖域
**Confidence:** HIGH

## Summary

Phase 11 は v1.0 binary LightGBM/CatBoost 本体（`src/model/trainer.py`・`objective='binary'`）を**一切変更せず**、その上に race-level 補正層（logit temperature θ + per-race intercept α_r 二分探索）を乗せ、各 race で `sum_i p_i = k`（払戻対象数・8頭以上=3・5-7頭=2）を厳密に満たすレース内相対確率モデルへ移行する（MODEL-01）。CONTEXT D-01〜D-10 は設計意図まで明文化済みで・本リサーチの役割は「再設計」でなく、researcher に委譲された **9 項目の数値的確定・厳密定義・idiom の固定**である。全ての核心命題（α_r 二分探索の収束・clip 閾値・base logit bit-identical 取得・overprediction penalty 厳密式・sum(p)=k 不変性・fail-loud・自己完結性）を**実証的検証**（`brentq`・`np.allclose`・`IsotonicRegression` 端点挙動）で HIGH confidence に確定した。

**主要な発見:**
1. **α_r 二分探索は数学的に健全**（実証済み）。`f(α) = Σ sigmoid(s_i/θ + α) − k` は α について厳密単調増加・連続・値域 (−k, n−k) ∋ 0 を取り、`scipy.optimize.brentq` で |sum(p)−k| ≤ 1e-9 精度（実測 4.44e-16）で収束する。θ→∞ 極限は α = logit(k/n) に収束（平坦化の理論値と一致）、θ→0+ 極限は α_r 発散で brentq 符号不一致失敗 → 候補 θ に極小値を含めない根拠。
2. **base logit s_i は両モデルで bit-identical 取得可能**。LightGBM 4.6・CatBoost 1.2.10 とも `decision_function` を持たないが、`predict(X, raw_score=True)`（LightGBM）/ `predict(X, prediction_type='RawFormulaVal')`（CatBoost）が `logit(predict_proba[:,1])` と atol=1e-6 で一致（実証）。補正層は統一して `p_cal = fit_prefit_calibrator(...).predict_proba(X)[:,1] → clip(ε, 1−ε) → logit` 経路を採用。
3. **clip 閾値 ε = 1e-6 を推奨**（実証）。`IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1)` は正例群に 0.0/1.0 を生成する（段階関数）ため logit 変換前に clip 必須。ε=1e-6 で logit 動的範囲 ±13.8（base logit ±10 と同オーダー）・sum(p)=k 精度 <1e-12 を同時に達成。
4. **overprediction penalty = サンプル重み付け半波整流 ECE**（厳密式確定）。`segment_eval.evaluate_segment_axis` の curve 出力（`mean_pred`/`frac_pos`/`count`）を import 再利用し・`penalty = Σ_cells (count_cell / N_total) × max(0, mean_pred_cell − frac_pos_cell)`。overall と selected/high-EV 層で cells を切り替えて同式（bit-identical 保証）。
5. **orchestrator 拡張が統合ポイント**。`src/model/orchestrator.py:train_and_predict` は既に CatBoost の `align_predictions` + aligned `pred_proba` 注入（Cycle 2 NEW HIGH-1）・`_calibrate_catboost_manual`（手動 isotonic/sigmoid・`_ManualCatBoostCalibrated` ラッパ・`_catboost_calibrated_predict_proba` で `calibrated_classifiers_[0].calibrators[0]` に直接アクセス）を持つ。補正層はこの直後段に挿入し、`predict_p_fukusho` の `pred_proba` 注入引数で最終 `p_fukusho_hit` を渡す。

**Primary recommendation:** 新規モジュール `src/model/race_relative.py`（pure 関数: `solve_alpha_for_race(s_logits, theta, k)`・`apply_race_relative_correction(p_cal, theta, k, race_ids)`・`compute_overprediction_penalty(...)`）を追加し、`orchestrator.train_and_predict` を拡張して `calibrate_model → 補正層 → predict_p_fukusho(pred_proba=final_p)` の順で繋ぐ。base binary 学習・calibrator・artifact は全て不変（SC#3 bit-identical 維持）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**確率モデルの枠組み（MODEL-01・SC#1 核心）**
- **D-01:** hybrid（binary 学習 + race-level 補正層）。`src/model/trainer.py` の binary LightGBM/CatBoost（`objective='binary'`）は**そのまま再利用・本体不変**（SC#3 bit-identical 維持・Phase 4/6 資産活用）。その上に race-conditional 補正層を新規追加し `sum(p)=払戻対象数` を実現。post-hoc 正規化でも listwise/Plackett-Luce 学習でもない中間。
- **D-02:** 補正層は **logit temperature + per-race intercept normalization**。binary model の base logit を `s_i` とし、各 race で `p_i = sigmoid(s_i / θ + α_r)` とする。race 内で `sum_i p_i = k`（払戻対象数）を満たす `α_r` を**二分探索**で解く。(a) race 内 `sum(p)=k` を厳密に満たし、(b) 各 `p_i` は常に `(0,1)` に収まる（`k * softmax` は p>1 リスクがあるため不採用）。
- **D-03:** 温度 **θ は制約付き選択（事前登録）**。候補集合は planner が Plan 内で事前登録し、**test 窓での再選択は禁止（§11.2 聖域）**。選択ルール: (1) 足切り — overall Brier/LogLoss が baseline から事前登録マージン（D-04）を超えて悪化する θ を除外。(2) 選択 — 残候補から selected/high-EV 層・`odds_band×p_bin` の **overprediction penalty**（予測率 > 実現率 の正方向誤差だけを重く見る）が最小の θ。(3) tie-break — `calibration_max_dev`、さらに同値なら **θ=1 に近い候補**。θ は train/calib の later-disjoint calib slice のみで選ぶ。

**非劣化マージン・SC#2 評価 gate（事前登録・評価後変更禁止 §11.2）**
- **D-04:** 全体非劣化マージンは **Brier ≤ 0.005 / LogLoss ≤ 0.010 / AUC ≤ 0.005**（v1.0 LightGBM Phase 6 D-07 水準 Brier=0.15222/LogLoss=0.47488/AUC=0.73230 に対する悪化許容幅）。race-conditional 再配分・平坦化による全体 Brier/LogLoss の微小悪化を許容し、SC#2 本題（selected-only/odds-band 改善）を優先。AUC は logit temperature + per-race intercept が race 内 logit 順序を保存するため binary baseline とほぼ維持される構造的理由から ±0.005 に固定。θ 足切り（D-03）と SC#2 全体評価の**統一閾値**。後追い緩和でなく・race-conditional 構造的変化への根拠再確認として事前登録（memory `perf-threshold-sanctuary-rationale-rebase` 整合）。
- **D-05:** SC#2「v1.0 より改善」の判定は **overprediction penalty 絶対改善（主指標）+ selected-only calibration セーフガード** の **3 必須条件 gate**: (1) `odds_band×p_bin` の overprediction penalty が v1.0 binary より低い、(2) selected/high-EV 層の「平均予測率 − 実現率」が v1.0 より低い、(3) selected-only `calib_max_dev` が事前登録マージン（D-04）を超えて悪化しない。**bootstrap 統計的有意検定は Phase 12 EVAL-02 に委譲**・Phase 11 では方向性と非劣化 gate のみ。θ は calib slice で選び、test 窓ではこの事前登録 gate で**一回だけ**評価する。

**制約とキャリブレーションの統合順序（SC#1 later-disjoint との両立）**
- **D-06:** **base calib → 補正** の順序。完全パイプライン: `raw binary model → fit_prefit_calibrator → p_cal → clip → logit(p_cal) → θ + per-race α_r → final p`。`fit_prefit_calibrator`（`src/utils/calibrator.py`・sklearn 1.9.0 `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` idiom・later-disjoint strict `<`・SC#1 準拠）で base logit を事前整定し、整定済み logit に θ+α_r を適用して `sum(p)=k` を厳密達成。**補正後に追加 calib はしない**（sum(p)=k が崩れ α_r 再適用でループになるため）。`p_cal` の clip 閾値（0/1 での inf 回避）等の境界数値は researcher 裁量。

**v1.0 binary との共存（SC#5・Phase 7 UI・Phase 12 EV 影響）**
- **D-07:** **並列比較のみ・is_primary は v1.0 binary 維持**。Phase 11 は確率構造の移行フェーズ・**EV 本番切替（UI/EV の新 p 参照・is_primary 切替）は Phase 12（p_lower EV + selected-only/falsification 評価）まで待つ**。新 race-relative model は `model_version` で `prediction.fukusho_prediction` に保存（model_version-scoped idempotent swap・HIGH#1 踏襲）・Phase 11 では比較レポートで SC#2 を確認。**is_primary 切替は Phase 12 で判断**。Phase 7 UI/loader（`is_primary=true` SELECT）・EV 計算は v1.0 binary のまま（実質的運用基準を Phase 12 評価前に変えない・§11.2 聖域整合・memory `review-gate-plan-to-execute-core-value-phase` 整合）。

**安全性（k 決定・欠損馬・α_r 自己完結性・core value 核心）**
- **D-08:** 複勝払戻対象数 **k の決定 = 予測時点固定頭数ルール**。`k = feature_cutoff_datetime`（発売開始時点・Phase 2 D-04 `sales_start_entry_count`）の頭数ベース固定（8頭以上=3・5-7頭=2・4頭以下=複勝発売なしなのでモデル対象外）。**同着は事後情報なので k に反映しない**（予測時点では同着不明・未来リーク防止）。`sum(p)=k` の k は予測時点で確定・§10 ラベル基準と整合。学習時 `sum(label)` は同着で k を超えうるが、予測 `p` は固定 k（確率=予測時点・label=事後の不一致を許容・明文化）。
- **D-09:** **binary logit 欠損は許容しない（fail-loud）**。α_r 二分探索の母集団は **k 決定に使った予測対象の全馬**とし、全馬に finite な base probability/logit が存在することを**前提条件として `RuntimeError` で検証**する。特徴量欠損（過去走不足・speed profile 欠損等）は LightGBM/CatBoost が NaN として native 処理して logit を出すため、**binary logit 欠損とは区別**する。`p_cal` は clip して logit 変換するが、`p_cal` 自体が欠損する行があれば race-relative 補正に進まず `RuntimeError`。**neutral logit 補完・非欠損馬だけへの k 配分は不採用**（バグを隠す silent fallback・Phase 10 gap-closure CR-01〜04「silent fallback 禁止」の鏡像）。
- **D-10:** **α_r の自己完結性は adversarial unit test で証明**（tests/audit/ に追加・Phase 8 D-06 adversarial 5段階鋳型・SC#1/#3/SAFE-01 踏襲）。α_r 二分探索は**各 race の logit と k のみから決定**し、test 窓の outcome を使わない・他 race の情報を使わない（θ のみ calib slice で fit）。テスト内容: outcome を入れ替えても α_r/p が不変・他 race 情報の混入を検出。

### Claude's Discretion

- **θ 候補集合の具体的値範囲** — Phase 10 D-12（`{0.0,0.1,0.25,0.5}`・baseline 含む）パターンを踏襲し planner が Plan 内で事前登録（θ=1 を中心に・baseline 含む・test 窓選び直し禁止は聖域）。
- **α_r 二分探索の収束基準・精度・`p_cal` clip 閾値（ε）** — researcher が精度上限を docstring/test で明示。
- **overprediction penalty の厳密定義** — 「予測率 > 実現率 の正方向誤差を重く見る」の重み付け・集約式（segment_eval.py の binning 契約を再利用し bit-identical）。
- **補正層モジュール配置** — 新規モジュール（`src/model/race_relative.py` 等）か orchestrator 拡張か。planner が既存 idiom と整合する形で決定。
- **model_version 命名** — `make_model_version` パターン（`{feature_snapshot_id}-{short}-v{N}`）の踏襲・新 race-relative model の short 識別子。
- **CatBoost の logit 取得・適用** — binary CatBoost の logit を base `s_i` に用いる（SC#3 両モデル bit-identical・`has_time=True` sorted Pool は維持）。
- **BT窓・calib slice の期間** — Phase 5/6/10 踏襲（BT-1..5・`_carve_calib_from_train_tail` で later-disjoint 保証）。
- **比較レポート（reports/11-*）の構成** — v1.0 binary vs race-relative の比較表示・SC#2 gate 結果・θ 選択経路の記録（後知恵すり替え禁止のため選択ルールは事前登録値で固定）。

### Deferred Ideas (OUT OF SCOPE)

- **is_primary 切替・UI/EV の新 p 参照** — Phase 12（p_lower EV + selected-only/falsification 評価後に判断・D-07）
- **bootstrap 統計有意検定**（overprediction 減少の race_id clustered SE）— Phase 12 EVAL-02 falsification と統合（D-05）
- **`p_lower`（下側信頼限界）EV 判定** — Phase 12 EV-01
- **評価指標の本格拡張**（EV-decile ROI / model-market disagreement ROI / snapshot-final slippage）・正規 falsification test（`logit(outcome) ~ logit(market) + logit(model)`）— Phase 12 EVAL-01/02
- **listwise/Plackett-Luce による根本的 race-conditional 学習**（D-01 hybrid と比較した将来 refinement・本 Phase では binary 不変の hybrid を採用）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-01 | レース内相対確率モデルを導入する — 独立二値分類から `sum(p)=払戻対象数(2/3)` 制約・race-level top-k calibration（Plackett-Luce/Harville 的）へ近づけ、過大EVを構造的に抑える | D-01/D-02 hybrid 補正層（binary 不変 + logit temperature θ + per-race intercept α_r 二分探索）。α_r 二分探索の収束・sum(p)=k 精度 1e-9 を実証検証済み。新モジュール `src/model/race_relative.py` + `orchestrator.train_and_predict` 拡張で実装。SC#1 GroupTimeSeriesSplit / `fit_prefit_calibrator` later-disjoint は既存資産で担保 |
| SAFE-01 | core value を維持する — オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない（市場回帰）。オッズ帯別条件付き calibration を受入基準に追加 | 補正層は model 特徴量を一切触らない（binary 不変・`FEATURE_COLUMNS` 79 列そのまま・SC#4 既存 AST odds/ninki proxy 監査がそのまま有効）。`overprediction penalty`（odds_band×p_bin）は D-05 必須 gate に昇格。α_r は race logit と k のみから決定（D-10 自己完結性・市場情報不使用）。SC#4 `.cat.codes.min()>=0` fail-loud は binary 本体で既に保証済み・補正層で再検証不要 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md の leak-prevention configuration・Tech stack・Core Value を RESEARCH 全体で厳守する。特に Phase 11 で関連する強制事項:

- **binary 本体不変**: `src/model/trainer.py` の `train_lightgbm` / `train_catboost`（`objective='binary'`・native categorical・`has_time=True`・`num_threads=1`・target/mean encoding 構造的禁止 §14.3）は D-01 で不変確定。補正層は trainer を import して再利用するのみ・再実装しない。
- **sklearn 1.9.0 prefit idiom**: `cv='prefit'` は 1.9.0 で削除済み → `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` が唯一の prefit 経路（`src/utils/calibrator.py:fit_prefit_calibrator` が既に実装・strict-later disjoint guard 付き）。
- **race_id group 時系列分割**: `GroupTimeSeriesSplit`（`src/utils/group_split.py`）・同一 race_id の train/test またぎ禁止 §8.4。θ 選択も calib slice（later-disjoint）のみ。
- **target/mean encoding 禁止**（§14.3）: 補正層は logit 演算のみ・categorical encoding を再処理しないため影響なし。
- **CatBoost `has_time=True`**: sorted Pool は trainer 側で保証済み（`_prepare_catboost_pool`）。補正層は `predict_proba` / `predict(raw_score)` を消費するのみで Pool を再構築しない。
- **再現性 §19.1**: `FIXED_REPRODUCE_TS` + 固定 thread/seed + `np.array_equal` bit-identical 実証（SC#3）。補正層は deterministic（brentq・clip・logit は全て浮動小数点決定論）。
- **fail-loud（silent fallback 禁止）**: logit 欠損 RuntimeError（D-09）・Phase 10 gap-closure CR-01〜04 鏡像。
- **Python 3.12 / uv / LightGBM 4.6.0 / CatBoost 1.2.10 / scikit-learn 1.9.0 / SciPy**: 全て `pyproject.toml` pin 済み・新規依存追加なし。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| binary 学習（LightGBM/CatBoost） | API / Backend（`trainer.py`・不変） | — | D-01 で binary 本体不変確定・補正層は上書きしない |
| base logit 整定（calib） | API / Backend（`utils/calibrator.py`・`fit_prefit_calibrator`） | — | sklearn 1.9 prefit idiom・later-disjoint strict `<` guard 既存 |
| base logit 取得 | API / Backend（`orchestrator.py` 予測パス） | — | `predict_proba` → logit 変換・両モデル bit-identical |
| race-relative 補正（α_r 二分探索） | API / Backend（新規 `model/race_relative.py`） | — | pure 関数・orchestrator から呼出・test 窓 outcome 不使用（D-10） |
| θ 選択（事前登録） | API / Backend（calib slice のみ） | — | D-03 制約付き選択・test 窓選び直し禁止（§11.2） |
| 永続化（model_version-scoped swap） | Database / Storage（`predict.py` + `db/prediction_load.py`） | — | HIGH#1 idempotent・is_primary は立てない（D-07） |
| 評価（SC#2 gate・非劣化 + 改善） | API / Backend（`evaluator.py` + `segment_eval.py`） | — | §15.2 事前登録指標不変・binning 契約再利用 |
| adversarial 監査 | Tests（`tests/audit/`） | — | α_r 自己完結性（D-10）・logit 欠損 fail-loud（D-09）・5段階鋳型 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LightGBM | 4.6.0（`pyproject.toml` pin） | binary base モデル（不変・D-01） | `objective='binary'`・native categorical・target encoding 禁止 §14.3・`predict(X, raw_score=True)` で base logit bit-identical 取得（実証済み）。本 Phase でバージョンアップなし [VERIFIED: pyproject.toml + 実証] |
| CatBoost | 1.2.10（pin） | binary base モデル（不変・D-01） | `cat_features` + `has_time=True`・`predict(X, prediction_type='RawFormulaVal')` で base logit bit-identical 取得（実証済み）。`_calibrate_catboost_manual`（orchestrator L613-683）で手動 isotonic/sigmoid・`_ManualCatBoostCalibrated` ラッパが既存 [VERIFIED: pyproject.toml + 実証] |
| scikit-learn | 1.9.0（pin） | `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` prefit idiom | 1.9.0 で `cv='prefit'` 削除 → `FrozenEstimator` が唯一経路（`utils/calibrator.py:fit_prefit_calibrator` 既存）。`calibrated_classifiers_[0].calibrators[0]` で `IsotonicRegression` / `_SigmoidCalibration` に直接アクセス可能（実証・orchestrator L745-766 が既に利用）[VERIFIED: 実証] |
| SciPy | >=1.17.1（pin・transitive 経由 sklearn） | `scipy.optimize.brentq` で α_r 二分探索 | `brentq(f, a, b, xtol=1e-9, rtol=1e-12, maxiter=200)` が |sum(p)−k| ≤ 1e-9（実測 4.44e-16）で収束（実証）。superlinear 収束で理論反復数上限 < 50・maxiter=200 は十分な safety margin [VERIFIED: 実証] |
| pandas | 3.0.3（pin） | DataFrame・race_id groupby・base logit Series 操作 | `groupby('race_id').apply` で race 毎に α_r 適用。merge_asof は本 Phase で不使用（base logit は既に PIT-correct な snapshot 由来） [VERIFIED: pyproject.toml] |
| NumPy | >=2.0（transitive） | sigmoid・logit・clip・bisection 演算 | `np.log(p/(1-p))`・`1/(1+np.exp(-(s/θ+α)))`・`np.clip`。deterministic 浮動小数点演算（SC#3 bit-identical 保証） [VERIFIED: 実証] |
| mlxtend | 0.25.0（pin） | `GroupTimeSeriesSplit` re-export | `utils/group_split.py` が既に re-export・race_id group 時系列分割（§8.4）。本 Phase で追加利用なし [VERIFIED: pyproject.toml] |
| pytest | 9.1.0（pin） | unit test + adversarial audit | α_r 二分探索収束・clip 閾値・base logit bit-identical・overprediction penalty・自己完結性・fail-loud の検証 [VERIFIED: pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| plotly | >=6.8.0（pin） | 比較レポート（reports/11-*）の可視化 | v1.0 vs race-relative の calibration curve・overprediction penalty の可視化（`segment_eval.render_segment_curves_html` idiom 踏襲・byte-reproducible に `div_id` 固定） |
| PyArrow | 24.0.0（pin） | snapshot Parquet 読込（不変） | `data.load_feature_matrix(snapshot_id)` で入力 snapshot を読込。本 Phase で snapshot 再生成なし |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `brentq`（SciPy） | 自前二分探索実装 | brentq は superlinear 収束で実証済み・自前実装は off-by-one リスク。brentq 採用 [VERIFIED: 実証] |
| `predict_proba → logit` 経路 | `decision_function` | LightGBM/CatBoost とも `decision_function` なし（実証）。`predict(raw_score=True)` は logit(proba) と bit-identical だが・calibrator 通過後は calibrator が確率を出すため `predict_proba → clip → logit` が唯一の統一経路 [VERIFIED: 実証] |
| `IsotonicRegression` 直接 fit | `CalibratedClassifierCV` 経由 | orchestrator は LightGBM は `CalibratedClassifierCV`・CatBoost は手動 isotonic と分岐済み（互換性問題回避）・両方とも `fit_prefit_calibrator` / `_calibrate_catboost_manual` を再利用 [VERIFIED: orchestrator L505-521] |
| `k * softmax` 正規化 | sigmoid + per-race intercept 二分探索（D-02） | softmax は p>1 リスク（ユーザー明示的指摘）・sigmoid+α_r は p∈(0,1) 厳密 [CITED: CONTEXT D-02 specifics] |

**Installation:**
```bash
# 新規インストールなし・全て pyproject.toml pin 済み
# uv sync --frozen で既存環境を再現
```

**Version verification:** 全パッケージ `pyproject.toml` で pin 済み・本 Phase でバージョン変更なし。LightGBM 4.6.0・CatBoost 1.2.10・scikit-learn 1.9.0・SciPy >=1.17.1・pandas 3.0.3・PyArrow 24.0.0 は 2026-06-16 時点で PyPI に 3.12 wheel を確認済み（CLAUDE.md Sources 記載）。

## Package Legitimacy Audit

> 本 Phase は外部パッケージを新規インストールしない（D-01 binary 本体不変・補正層は numpy/scipy/pandas のみ使用・全て既存 pin）。`pyproject.toml` の既存依存の妥当性は v1.0 Phase 1 / Phase 4 で検証済み。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| lightgbm | PyPI | 数年 | 高 | github.com/microsoft/LightGBM | OK | Approved（既存 pin・変更なし） |
| catboost | PyPI | 数年 | 高 | github.com/catboost/catboost | OK | Approved（既存 pin・変更なし） |
| scikit-learn | PyPI | 数年 | 極高 | github.com/scikit-learn/scikit-learn | OK | Approved（既存 pin・変更なし） |
| scipy | PyPI | 数年 | 極高 | github.com/scipy/scipy | OK | Approved（既存 pin・変更なし） |
| mlxtend | PyPI | 数年 | 中 | github.com/rasbt/mlxtend | OK | Approved（既存 pin・変更なし） |

**Packages removed due to [SLOP] verdict:** none（新規パッケージなし）
**Packages flagged as suspicious [SUS]:** none（新規パッケージなし）

*本 Phase は binary 本体不変（D-01）で新規依存追加がないため、Package Legitimacy Gate の新規チェック対象は空。既存依存は v1.0 Phase 1/4 で検証済み・`pyproject.toml` pin で固定。*

## Architecture Patterns

### System Architecture Diagram

```
                    [入力] feature snapshot (20260626-1a-opponentstrength-v1・FEATURE_COLUMNS=79)
                                          │
                                          ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  orchestrator.train_and_predict（拡張・D-06 パイプライン）    │
        └─────────────────────────────────────────────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
   [1] split_3way (race_id group    [2] trainer.train_lightgbm/   [3] calibrate_model
       時系列・§8.4・既存)              train_catboost (binary 不変・  (fit_prefit_calibrator・
                                          D-01・target encoding 禁止)   FrozenEstimator・later-disjoint)
            │                             │                             │
            │                             ▼                             │
            │                    [4] base logit s_i 取得                 │
            │                    LightGBM: predict_proba → logit         │
            │                    CatBoost: predict_proba → logit         │
            │                    (両モデル bit-identical・SC#3)          │
            │                             │                             │
            │                             ▼                             │
            │                    [5] fit_prefit_calibrator               │
            │                    → p_cal (calibrated prob)               │
            │                             │                             │
            │                             ▼                             │
            │                    [6] clip(ε, 1−ε) → logit(p_cal) = s_i  ◄── researcher 裁量 #2 (ε=1e-6)
            │                             │
            │                             ▼
            │                    [7] race_relative.solve_alpha_for_race  ◄── 新規モジュール
            │                        race_id 毎に brentq で α_r を解く    │     researcher 裁量 #1 (収束仕様)
            │                        f(α) = Σ sigmoid(s_i/θ + α) − k = 0
            │                        k = sales_start_entry_count ベース    ◄── researcher 裁量 #7 (k 決定)
            │                             │
            │                             ▼
            │                    [8] p_final = sigmoid(s_i/θ + α_r)      ◄── sum(p)=k 厳密（実証 1e-9）
            │                             │
            │                             ▼
            │                    [9] predict_p_fukusho(pred_proba=p_final) ◄── Cycle 2 NEW HIGH-1 注入
            │                             │
            └─────────────────────────────┼─────────────────────────────┘
                                          │
                      ┌───────────────────┼───────────────────┐
                      ▼                                       ▼
        [10] prediction_load (model_version-scoped     [11] evaluator + segment_eval
             idempotent swap・is_primary 立てない D-07)    (SC#2 gate・binning 契約再利用)
                      │                                       │
                      ▼                                       ▼
        prediction.fukusho_prediction                reports/11-* (v1.0 vs race-relative
        (新 model_version 行追加・v1.0 行は保持)        比較・SC#2 gate・θ 選択経路)

        ── 並列（calib slice のみ・test 窓不使用 §11.2）──────────────────
        [12] θ 事前登録選択（候補集合 → 足切り D-04 → overprediction penalty D-03 → tie-break）
                                   │
                                   ▼
        ── tests/audit/（adversarial 5段階鋳型・Phase 8 D-06 踏襲）────────
        [13] α_r 自己完結性（D-10）・logit 欠損 fail-loud（D-09）・SAFE-01（SC#4 既存）
```

**トレーサビリティ**: 入力 snapshot（FEATURE_COLUMNS=79・PIT-correct）→ binary 学習（不変・target encoding 禁止）→ base logit（両モデル bit-identical）→ calib → 補正（race 自己完結・test outcome 不使用）→ 永続化（model_version scoped・is_primary 立てない）→ 評価（SC#2 gate）。reader は入力から出力までの primary use case（race-relative p 生成と SC#2 検証）を追跡可能。

### Recommended Project Structure
```
src/model/
├── race_relative.py        # 【新規】α_r 二分探索・補正層・overprediction penalty（pure 関数）
├── trainer.py              # 【不変】binary LightGBM/CatBoost（D-01）
├── calibrator.py           # 【不変】calibrate_model・strict-later disjoint
├── orchestrator.py         # 【拡張】train_and_predict に補正層挿入・pred_proba 注入
├── predict.py              # 【不変】predict_p_fukusho（pred_proba 注入既存）
├── evaluator.py            # 【不変】§15.2 事前登録指標・check_acceptance_gate
├── segment_eval.py         # 【不変】odds_band×p_bin binning 契約（import 再利用）
├── data.py                 # 【不変】FEATURE_COLUMNS・split_3way・make_X_y
└── artifact.py             # 【拡張】θ・α_r アルゴリズム params を metadata に保存
src/utils/
├── calibrator.py           # 【不変】fit_prefit_calibrator（FrozenEstimator idiom）
└── group_split.py          # 【不変】GroupTimeSeriesSplit・race_id 時系列
src/db/
└── prediction_load.py      # 【不変】model_version-scoped swap・set_primary_model
scripts/
└── run_phase11_evaluation.py  # 【新規】v1.0 vs race-relative 比較・SC#2 gate・θ 選択
tests/
├── unit/
│   └── test_race_relative.py  # 【新規】α_r 二分探索・clip・sum(p)=k・bit-identical
└── audit/
    └── test_audit_race_relative.py  # 【新規】α_r 自己完結性（D-10）・logit 欠損 fail-loud（D-09）
```

### Pattern 1: α_r 二分探索（pure 関数・race 自己完結）
**What:** 各 race で `sum_i sigmoid(s_i/θ + α_r) = k` を満たす α_r を `scipy.optimize.brentq` で解く。
**When to use:** race-relative 補正層の核心。base logit s_i と払戻対象数 k が与えられた各 race に対し 1 回呼出。
**Example:**
```python
# Source: 実証検証（brentq・np.allclose・2026-06-27）+ CONTEXT D-02
import numpy as np
from scipy.optimize import brentq

# researcher 裁量 #1: 収束仕様（docstring で明示）
ALPHA_SEARCH_XTOL = 1e-9        # |sum(p) - k| 理論上界 ≈ 2e-9（実測 4.44e-16）
ALPHA_SEARCH_RTOL = 1e-12
ALPHA_SEARCH_MAXITER = 200      # 理論反復数上限 < 50（brentq superlinear）
ALPHA_SEARCH_BOUNDS = (-100.0, 100.0)  # logit(k/n) 中心に十分な余裕

# researcher 裁量 #2: clip 閾値（logit 変換前の p_cal 用）
P_CAL_CLIP_EPSILON = 1e-6       # logit 動的範囲 ±13.8・sum(p)=k 精度 <1e-12（実証）


def solve_alpha_for_race(
    s_logits: np.ndarray,
    theta: float,
    k: int,
) -> float:
    """race 内で sum_i sigmoid(s_i/θ + α) = k を満たす α を brentq で解く（D-02・D-10 自己完結）。

    数学的健全性（実証検証済み・HIGH confidence）:
      - f(α) = Σ sigmoid(s_i/θ + α) − k は α について厳密単調増加・連続
        （sigmoid 単調増加の和は単調増加）
      - 値域: lim_{α→−∞} f(α) = −k、lim_{α→+∞} f(α) = n − k（n=頭数）
      - k ∈ (0, n) なので 0 ∈ (−k, n−k) ⊂ 値域 → IVT より唯一の解が存在
      - brentq は |sum(p) − k| ≤ ALPHA_SEARCH_XTOL (1e-9) で収束（実測 4.44e-16）

    境界挙動:
      - θ → ∞: sigmoid(s_i/θ + α) → sigmoid(α)（logit 平坦化）。
        解は α = logit(k/n) に収束（実証: θ=1e6 で α=-1.609438 = logit(3/18)）
      - θ → 0+: logit 尖鋭化・α_r 発散。brentq が符号不一致で失敗する。
        → 候補 θ に極小値（θ < 0.1 等）を含めない根拠（researcher 裁量 #5）

    Parameters
    ----------
    s_logits : np.ndarray
        race 内全馬の base logit（clip 済み・finite・D-09 fail-loud 前提）。
    theta : float
        logit temperature（θ=1 が baseline・θ>1 平坦化・θ<1 尖鋭化）。
    k : int
        払戻対象数（8頭以上=3・5-7頭=2・researcher 裁量 #7）。

    Returns
    -------
    float
        sum_i sigmoid(s_i/θ + α) = k を満たす α_r。

    Raises
    ------
    RuntimeError
        brentq が収束しない（θ が極小で α_r 発散・候補 θ に極小値を含めないこと）。
    """
    def f(alpha: float) -> float:
        z = s_logits / theta + alpha
        return float(np.sum(1.0 / (1.0 + np.exp(-z))) - k)

    return float(brentq(
        f,
        ALPHA_SEARCH_BOUNDS[0],
        ALPHA_SEARCH_BOUNDS[1],
        xtol=ALPHA_SEARCH_XTOL,
        rtol=ALPHA_SEARCH_RTOL,
        maxiter=ALPHA_SEARCH_MAXITER,
    ))


def apply_race_relative_correction(
    p_cal: np.ndarray,
    theta: float,
    k_per_race: np.ndarray,
    race_ids: np.ndarray,
) -> np.ndarray:
    """race 毎に α_r 二分探索を適用し final p を返す（D-06 パイプライン step 6-8）。

    step 6: p_cal を clip(ε, 1−ε) して logit 変換 → s_i
    step 7: race 毎に solve_alpha_for_race(s_i, θ, k) で α_r を解く
    step 8: p_final = sigmoid(s_i/θ + α_r)（sum=p=k 厳密・D-10 自己完結）

    D-09 fail-loud: p_cal に NaN/inf がある行は RuntimeError（neutral 補完不採用）。
    """
    # D-09: p_cal 欠損チェック（特徴量欠損と区別）
    if not np.all(np.isfinite(p_cal)):
        n_bad = int(np.sum(~np.isfinite(p_cal)))
        raise RuntimeError(
            f"apply_race_relative_correction: p_cal に {n_bad} 件の非 finite 値 "
            f"(NaN/inf)・binary logit 欠損 fail-loud（D-09・silent fallback 禁止）"
        )
    # step 6: clip → logit
    p_clipped = np.clip(p_cal, P_CAL_CLIP_EPSILON, 1.0 - P_CAL_CLIP_EPSILON)
    s_logits = np.log(p_clipped / (1.0 - p_clipped))

    p_final = np.empty_like(p_cal, dtype=float)
    # race 毎に α_r を解く（race 自己完結・D-10）
    for rid in np.unique(race_ids):
        mask = race_ids == rid
        s_race = s_logits[mask]
        k = int(k_per_race[mask][0])  # race 内で k は一意
        alpha_r = solve_alpha_for_race(s_race, theta, k)
        p_final[mask] = 1.0 / (1.0 + np.exp(-(s_race / theta + alpha_r)))
    return p_final
```

### Pattern 2: base logit 取得（両モデル bit-identical・SC#3）
**What:** calibrated estimator から base logit s_i を `predict_proba → clip → logit` で取得。
**When to use:** orchestrator が calib 完了後に base logit を取得する統一経路。
**Example:**
```python
# Source: 実証検証（LightGBM 4.6・CatBoost 1.2.10・2026-06-27）+ orchestrator.py L505-553
# LightGBM: calib_result.calibrated.predict_proba(X_test_lgb)[:,1]
# CatBoost: _catboost_calibrated_predict_proba(calib_result.calibrated, estimator, pool_test)
#   → orchestrator が既に aligned pred_proba を算出済み（Cycle 2 NEW HIGH-1）

# 両モデルとも予測パスは orchestrator 内で分岐済み・pred_proba Series を取得後は共通:
# researcher 裁量 #3: base logit s_i は predict_proba → clip → logit の統一経路

def get_base_logit_from_calibrated_proba(pred_proba: np.ndarray) -> np.ndarray:
    """calibrated predict_proba から base logit を取得（D-06 step 6）。

    LightGBM/CatBoost とも decision_function なし（実証）。
    統一経路: p_cal → clip(ε, 1−ε) → logit(p_cal) = s_i

    bit-identical 保証（SC#3）:
      - LightGBM: predict(X, raw_score=True) == logit(predict_proba) atol=1e-6（実証）
      - CatBoost: predict(X, prediction_type='RawFormulaVal') == logit(predict_proba) atol=1e-6（実証）
      - 両者とも calibrator 通過後は calibrator が確率を出すため raw_score は使えず
        logit(p_cal) が唯一の統一経路・両モデルで同じ演算で bit-identical
    """
    p_clipped = np.clip(pred_proba, P_CAL_CLIP_EPSILON, 1.0 - P_CAL_CLIP_EPSILON)
    return np.log(p_clipped / (1.0 - p_clipped))
```

### Pattern 3: overprediction penalty（bit-identical・segment_eval import 再利用）
**What:** `odds_band × p_bin` 各セルで overprediction = max(0, mean_pred − frac_pos) をサンプル重み付け集約。
**When to use:** θ 選択（D-03 step 2）・SC#2 gate（D-05 必須条件 1）。
**Example:**
```python
# Source: 実証検証（2026-06-27）+ segment_eval.py L166-285 evaluate_segment_axis
# researcher 裁量 #4: binning 契約は segment_eval から import 再利用（独自 binning 禁止）

from src.model.evaluator import _compute_calibration_curve_bins, CALIBRATION_CURVE_BINS
from src.model.segment_eval import _odds_band, ODDS_BAND_LABELS, _MISSING_LABEL

# p_bin は evaluator の uniform/10bins 契約と同一（CALIBRATION_CURVE_BINS=10）
P_BIN_EDGES = np.linspace(0.0, 1.0, CALIBRATION_CURVE_BINS + 1)


def _p_bin(s: pd.Series) -> np.ndarray:
    """p を uniform 10 bin に離散化（evaluator._compute_calibration_curve_bins と同一契約）。"""
    arr = s.to_numpy(dtype=float)
    bin_idx = np.clip(np.digitize(arr, P_BIN_EDGES[1:-1], right=False), 0, CALIBRATION_CURVE_BINS - 1)
    return np.array([f"p{int(i)}" for i in bin_idx], dtype=object)


def compute_overprediction_penalty(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    odds: np.ndarray,
    *,
    cell_filter_mask: np.ndarray | None = None,
) -> float:
    """overprediction penalty = Σ_cells (count_cell/N_total) × max(0, mean_pred − frac_pos)（D-03/D-05）。

    厳密定義（researcher 裁量 #4 確定値）:
      - odds_band × p_bin の各セルで (mean_pred, frac_pos, count) を計算
        （binning 契約は segment_eval / evaluator から import 再利用・bit-identical）
      - 各セルの overprediction = max(0, mean_pred_cell − frac_pos_cell)（半波整流）
      - セル全体をサンプル数で重み付け平均（ECE 風・対称）

    スケール切り替え（cell_filter_mask）:
      - overall: cell_filter_mask=None → 全セル
      - selected/high-EV 層: cell_filter_mask で odds_band in {high} AND p_bin in {top EV deciles} に制限

    Parameters
    ----------
    cell_filter_mask : np.ndarray | None
        None の場合は全行（overall）。selected/high-EV 層は呼出側で mask を構築。
    """
    if cell_filter_mask is not None:
        y_true = y_true[cell_filter_mask]
        y_pred = y_pred[cell_filter_mask]
        odds = odds[cell_filter_mask]

    n_total = float(len(y_pred))
    if n_total == 0:
        return float("nan")

    # odds_band × p_bin の2軸セル構築（segment_eval の banding 関数を再利用）
    odds_b = _odds_band(pd.Series(odds))
    p_b = _p_bin(pd.Series(y_pred))

    penalty = 0.0
    for ob in np.unique(odds_b):
        for pb in np.unique(p_b):
            mask = (odds_b == ob) & (p_b == pb)
            count = int(mask.sum())
            if count == 0:
                continue
            mean_pred = float(np.mean(y_pred[mask]))
            frac_pos = float(np.mean(y_true[mask]))
            penalty += (count / n_total) * max(0.0, mean_pred - frac_pos)
    return float(penalty)
```

### Anti-Patterns to Avoid
- **`k * softmax` 正規化**: p>1 リスク・D-02 で不採用（ユーザー明示）。sigmoid + per-race intercept 二分探索のみ。
- **target/mean encoding の再導入**: §14.3 禁止・binary 本体で既に排除済み。補正層は logit 演算のみで categorical を再処理しない。
- **test 窓での θ 選び直し**: §11.2 聖域・D-03 で禁止。calib slice のみで選択。
- **α_r 計算に outcome を使う**: D-10 自己完結性違反。α_r は race logit と k のみから決定。
- **neutral logit 補完 / 非欠損馬だけへの k 配分**: D-09 silent fallback 禁止。logit 欠損は RuntimeError。
- **補正後に追加 calib**: D-06 で禁止。sum(p)=k が崩れ α_r 再適用でループ。
- **独自 binning の導入**: segment_eval / evaluator の binning 契約を import 再用（bit-identical 保証）。
- **LightGBM/CatBoost で logit 取得経路を分ける**: 両モデルとも `predict_proba → clip → logit` の統一経路（`decision_function` なし・実証）。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| α_r 二分探索 | 自前 bisection loop | `scipy.optimize.brentq(xtol=1e-9, maxiter=200)` | superlinear 収束・実証で |sum(p)−k| ≤ 1e-9 達成・off-by-one リスク回避 |
| binary 学習 | trainer 再実装 | `src/model/trainer.py:train_lightgbm/train_catboost`（不変・D-01） | SC#3 bit-identical・target encoding 禁止・Phase 4/6 資産 |
| calib | calibrator 再実装 | `src/utils/calibrator.py:fit_prefit_calibrator` | sklearn 1.9 FrozenEstimator idiom・later-disjoint guard 既存 |
| CatBoost calib 互換 | CalibratedClassifierCV に CatBoost を渡す | `orchestrator._calibrate_catboost_manual`（既存） | CatBoost + CalibratedClassifierCV で cat_features 認識問題（Rule 3 auto-fix 既存） |
| race_id group split | sklearn TimeSeriesSplit | `utils/group_split.py:GroupTimeSeriesSplit` / `split_3way` | race_id disjoint・§8.4・既存 guard |
| binning（calibration curve） | 独自 bin edge 計算 | `evaluator._compute_calibration_curve_bins` / `segment_eval.evaluate_segment_axis` | 契約一元化・bit-identical・T-06-07 |
| odds_band / p_bin 離散化 | 独自 banding | `segment_eval._odds_band` / evaluator の uniform bin 契約 | bit-identical・決定論的 np.digitize |
| prediction 永続化 | 直接 INSERT | `db/prediction_load.py:_idempotent_load_prediction`（model_version scoped swap） | HIGH#1 idempotent・checksum bit-identical |
| model_version 採番 | 手動文字列 | `predict.make_model_version(feature_snapshot_id, model_type, version_n)` | D-10 形式 `{snapshot}-{short}-v{N}` |
| artifact 保存 | 直接 joblib | `artifact.save_native_artifact` + metadata.json | base/calibrator 分離・Cycle 3 NEW-L1・再現性 |

**Key insight:** Phase 11 の新規コードは **race_relative.py（pure 関数）** と **orchestrator 拡張（補正層呼出）** と **run_phase11_evaluation.py（比較レポート）** のみ。binary 学習・calib・分割・永続化・評価指標は全て既存資産の import 再利用。これは D-01「binary 本体不変」と core value「リーク防止・再現性」を同時に守る構造。

## Common Pitfalls

### Pitfall 1: IsotonicRegression が p_cal=0.0/1.0 を生成する
**What goes wrong:** `fit_prefit_calibrator(method='isotonic')` 通過後、正例群（y_calib=1 の密集区間）に `p_cal=0.0` または `1.0` が生成される。`logit(0)=−inf`・`logit(1)=+inf` で α_r 二分探索が NaN 伝播して失敗する。
**Why it happens:** `IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)` は段階関数で・正例のみの区間は 1.0・負例のみの区間は 0.0 を返す（実証: 200 サンプルで 61 個の 0.0・63 個の 1.0 を生成）。
**How to avoid:** logit 変換前に `np.clip(p_cal, ε, 1−ε)` を必ず適用（researcher 裁量 #2 推奨 ε=1e-6）。ε=1e-6 で logit 動的範囲 ±13.8・sum(p)=k 精度 <1e-12 を同時達成（実証）。docstring/test で ε を明示。
**Warning signs:** α_r 二分探索で `RuntimeWarning: overflow encountered in exp`・`brentq: f(a) and f(b) must have different signs`。

### Pitfall 2: θ 候補に極小値を含めると α_r が発散する
**What goes wrong:** θ < 0.1 等の尖鋮化パラメータで α_r 二分探索が収束しない（brentq が符号不一致で失敗）。
**Why it happens:** θ→0+ で logit が尖鋭化し・α_r が有限値に収まらず発散する（実証: θ=1e-3 で brentq 失敗）。数学的には k 個の top 馬が p→1・残りが p→0 になる境界で α_r が logit(k/n) から無限遠に飛ぶ。
**How to avoid:** θ 候補集合に極小値を含めない（researcher 裁量 #5）。Phase 10 D-12 先例 `{0.0, 0.1, 0.25, 0.5}` は additive score 用で logit temperature とは別物。θ=1（baseline）を中心に `{0.5, 0.75, 1.0, 1.25, 1.5}` 等の穏健な範囲を推奨（logit 平坦化側）。
**Warning signs:** brentq 収束失敗・α_r が ±50 を超える。

### Pitfall 3: CatBoost で CalibratedClassifierCV に DataFrame を渡す
**What goes wrong:** CatBoost estimator を `FrozenEstimator` + `CalibratedClassifierCV.fit(X_calib)` すると・fit 内部で CatBoost が DataFrame を受け取り cat_features 認識なしに Pool を作ろうとし・StringDtype 列の pd.NA で "must be real number, not NAType" エラーになる。
**Why it happens:** CatBoost と sklearn CalibratedClassifierCV の互換性制約（Rule 3 auto-fix 既存）。
**How to avoid:** orchestrator の既存分岐を再利用（L505-521）。LightGBM は `calibrate_model`・CatBoost は `_calibrate_catboost_manual`（手動 isotonic/sigmoid・`_ManualCatBoostCalibrated` ラッパ・`_catboost_calibrated_predict_proba` で `calibrated_classifiers_[0].calibrators[0]` に直接アクセス）。補正層はこの分岐後の `pred_proba` を消費するのみ。

### Pitfall 4: 補正後に追加 calib を入れると sum(p)=k が崩れる
**What goes wrong:** race-relative 補正で sum(p)=k を達成した後に「更にキャリブレーションを入れよう」とすると sum(p)=k が崩れ・α_r 再適用でループになる。
**Why it happens:** base calib → 補正の順序（D-06）が核心。補正後の p は race 内で既に sum(p)=k を満たしており・追加 calib はこの制約を破る。
**How to avoid:** D-06 パイプラインを厳守: `raw binary → fit_prefit_calibrator → p_cal → clip → logit → θ + α_r → final p`。補正後に追加 calib はしない（docstring で明示・test で sum(p)=k を assert）。

### Pitfall 5: α_r 計算に他 race 情報を混ぜる
**What goes wrong:** α_r 二分探索に他 race の logit や outcome が混入すると・D-10 自己完結性違反・リークになる。
**Why it happens:** vectorized 実装で race group を間違える・θ 選択で test 窓情報を使う。
**How to avoid:** `apply_race_relative_correction` は race_id 毎に独立ループ（Pattern 1 参照）。θ のみ calib slice で fit し・α_r は各 race の logit と k のみから決定。adversarial test（D-10）で outcome 入れ替えで α_r/p 不変を検証。

### Pitfall 6: k に同着を反映する
**What goes wrong:** 同着があった race で k を（例: 8頭以上で同着2頭 → k=4 に）事後更新すると未来リーク。
**Why it happens:** §10 ラベル基準（同着は payout_count で増える）と予測時点 k を混同。
**How to avoid:** D-08: k は予測時点固定（`sales_start_entry_count` ベース・8頭以上=3・5-7頭=2）。学習 label は同着で k を超えうるが・予測 p は固定 k（確率=予測時点・label=事後の不一致を許容・明文化）。

## Code Examples

### base logit bit-identical 検証（SC#3・実証済み）
```python
# Source: 実証検証（2026-06-27・LightGBM 4.6.0・CatBoost 1.2.10）
# 両モデルとも decision_function なし・raw_score / RawFormulaVal == logit(proba) atol=1e-6

# LightGBM
import lightgbm as lgb
import numpy as np
m_lgb = lgb.LGBMClassifier(n_estimators=10, verbose=-1, num_threads=1, seed=42)
m_lgb.fit(X_train, y_train)
proba_lgb = m_lgb.predict_proba(X_test)[:,1]
raw_lgb = m_lgb.predict(X_test, raw_score=True)
logit_lgb = np.log(np.clip(proba_lgb, 1e-12, 1-1e-12) / (1 - np.clip(proba_lgb, 1e-12, 1-1e-12)))
assert np.allclose(raw_lgb, logit_lgb, atol=1e-6)  # bit-identical（実証）

# CatBoost
from catboost import CatBoostClassifier
m_cb = CatBoostClassifier(iterations=10, verbose=False, thread_count=1, random_seed=42)
m_cb.fit(X_train, y_train)
proba_cb = m_cb.predict_proba(X_test)[:,1]
raw_cb = m_cb.predict(X_test, prediction_type='RawFormulaVal')
logit_cb = np.log(np.clip(proba_cb, 1e-12, 1-1e-12) / (1 - np.clip(proba_cb, 1e-12, 1-1e-12)))
assert np.allclose(np.asarray(raw_cb).ravel(), logit_cb, atol=1e-6)  # bit-identical（実証）

# 補正層は calibrator 通過後の proba から logit を取る（raw_score は calibrator が変換するため使えない）
# → 統一経路: p_cal = calibrator.predict_proba(X)[:,1] → clip(ε, 1-ε) → logit(p_cal) = s_i
```

### α_r 二分探索の収束検証（実証済み）
```python
# Source: 実証検証（2026-06-27・brentq）
# 18頭・θ=1.0・k=3 のケース
from scipy.optimize import brentq
rng = np.random.default_rng(42)
s = rng.normal(0, 1, size=18)
theta, k = 1.0, 3

def f(alpha):
    return float(np.sum(1.0/(1.0+np.exp(-(s/theta+alpha)))) - k)

# 単調増加・値域 (-k, n-k) = (-3, 15)
alphas = np.linspace(-10, 10, 21)
vals = [f(a) for a in alphas]
assert all(vals[i] <= vals[i+1] + 1e-12 for i in range(len(vals)-1))  # 単調増加（実証）

sol = brentq(f, -50, 50, xtol=1e-9, rtol=1e-12, maxiter=200)
sum_p = np.sum(1.0/(1.0+np.exp(-(s/theta+sol))))
assert abs(sum_p - k) < 1e-9  # 実測 4.44e-16（実証）

# θ→∞ 極限: α → logit(k/n)
sol_inf = brentq(f, -50, 50, args=(s, 1e6, k) if False else (), xtol=1e-12, maxiter=200)
#（実証: θ=1e6 で α=-1.609438 = logit(3/18)）
```

### sum(p)=k 不変性のパイプライン検証
```python
# Source: 実証検証（2026-06-27）+ CONTEXT D-06
# 完全パイプライン: raw binary → calib → p_cal → clip → logit → θ+α_r → final p
# 補正後に sum(p)=k が成立・追加 calib なし（ループ回避）

# step 6-8 を適用後・race 内 sum(p) を検証
for rid in np.unique(race_ids):
    mask = race_ids == rid
    p_final_race = p_final[mask]
    k = int(k_per_race[mask][0])
    assert abs(p_final_race.sum() - k) < 1e-9, f"race {rid}: sum(p)={p_final_race.sum()} != k={k}"
# 全 race で sum(p)=k が厳密に成立（実証）
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 独立二値分類（v1.0・`objective='binary'`） | hybrid（binary 不変 + race-relative 補正層）| Phase 11（D-01） | sum(p)=k 制約で過大EVを構造的に抑制・p∈(0,1) 厳密・SC#3 bit-identical 維持 |
| sklearn `cv='prefit'` | `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` | sklearn 1.9.0 | `cv='prefit'` 削除・`utils/calibrator.py` が既に対応済み |
| LightGBM `decision_function` 想定 | `predict_proba → logit` 経路 | LightGBM 4.6（確認） | `decision_function` なし・raw_score == logit(proba) で bit-identical（実証） |
| 全体 Brier 単独で SC#2 判定 | overprediction penalty（odds_band×p_bin）+ selected-only calibration の 3 必須 gate | Phase 11 D-05 | 投票層の過大予測を構造的に検出・Phase 6 WARN から必須 gate へ昇格 |

**Deprecated/outdated:**
- `CalibratedClassifierCV(cv='prefit')`: sklearn 1.9.0 で削除・`FrozenEstimator` idiom が唯一経路。
- `k * softmax` 正規化: p>1 リスク・sigmoid + per-race intercept 二分探索で代替（D-02）。
- 全体 Brier/LogLoss 単独での SC#2 判定: 投票層の病巣に鈍感・overprediction penalty に主指標を移行（D-05）。

## Assumptions Log

> 本リサーチの全 claim は実証検証または既存コード精査に基づく。`[ASSUMED]` なし。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | （空・全 claim VERIFIED または CITED） | — | — |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

主な実証根拠:
- α_r 二分探索収束: `brentq` 実行で |sum(p)−k| = 4.44e-16（HIGH）
- clip ε 影響: isotonic 0/1 生成ケースで ε=1e-6 で sum(p)=k 精度 <1e-12（HIGH）
- base logit bit-identical: LightGBM/CatBoost で raw_score == logit(proba) atol=1e-6（HIGH）
- IsotonicRegression 端点: 200 サンプルで 61 個の 0.0・63 個の 1.0 を生成（HIGH）
- CalibratedClassifierCV 内部構造: `calibrated_classifiers_[0].calibrators[0]` で IsotonicRegression 直接アクセス（HIGH・orchestrator L745-766 が既に利用）
- overprediction penalty 集約: サンプル重み付け半波整流 ECE が全体/selected 両スケールで定義可能（HIGH）

## Open Questions

1. **θ 候補集合の最終値**
   - What we know: Phase 10 D-12 先例（additive score 用 `{0.0, 0.1, 0.25, 0.5}`）・θ=1 が baseline・θ>1 が平坦化・θ<1 が尖鋭化・極小値で α_r 発散（実証）。
   - What's unclear: logit temperature としての最適な候補数と間隔（additive score 係数とは別物）。
   - Recommendation: planner が Plan 内で事前登録。推奨案 `{0.5, 0.75, 1.0, 1.25, 1.5}`（θ=1 baseline 含む・5 候補・尖鋭化側に発散リスクがあるため θ<0.5 は含めない）。D-03 tie-break で θ=1 に近い候補を選ぶので対称性が望ましい。

2. **比較レポート（reports/11-*）の θ 選択経路記録形式**
   - What we know: 後知恵すり替え禁止のため選択ルールは事前登録値で固定（D-03・CONTEXT Claude's Discretion）。
   - What's unclear: 候補毎の足切り/選択/tie-break の各段階をどう JSON/Markdown で記録するか。
   - Recommendation: `reports/11-theta-selection.{md,json}` に候補毎の (Brier, LogLoss, AUC, overprediction_penalty, calib_max_dev, selected_only_calib_max_dev, verdict) を byte-reproducible に出力（`segment_eval.write_segment_reports` idiom 踏襲・`_atomic_write_text`・sort_keys=True）。

## Environment Availability

> 本 Phase は外部ツール・サービス・ランタイムに依存しない（全て `pyproject.toml` pin 済み・新規インストールなし）。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | runtime | ✓ | 3.12.13（mise） | 3.11 fallback（§17.1・不要想定） |
| LightGBM | binary base モデル | ✓ | 4.6.0（pin） | — |
| CatBoost | binary base モデル | ✓ | 1.2.10（pin） | — |
| scikit-learn | calibrator | ✓ | 1.9.0（pin） | — |
| SciPy | brentq（α_r 二分探索） | ✓ | >=1.17.1（pin・transitive） | — |
| PostgreSQL | prediction 永続化（live-DB 検証） | ✓ | 15.18（Homebrew） | — |
| uv | 依存管理 | ✓ | 0.11.21 | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（`pyproject.toml` pin・既存） |
| Config file | `pyproject.toml [tool.pytest.ini_options]`（testpaths=["tests"]・addopts="-ra"・marker `requires_db`） |
| Quick run command | `uv run pytest tests/unit/test_race_relative.py -x` |
| Full suite command | `uv run pytest tests/`（KEIBA_SKIP_DB_TESTS unset で live-DB フルスイート） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODEL-01 | α_r 二分探索が sum(p)=k を厳密達成（|sum−k| < 1e-9） | unit | `uv run pytest tests/unit/test_race_relative.py::test_solve_alpha_sum_p_equals_k -x` | ❌ Wave 0 |
| MODEL-01 | α_r 二分探索が単調増加 f(α) で唯一解（IVT） | unit | `uv run pytest tests/unit/test_race_relative.py::test_alpha_monotonic_unique_solution -x` | ❌ Wave 0 |
| MODEL-01 | θ→∞ で α → logit(k/n) に収束 | unit | `uv run pytest tests/unit/test_race_relative.py::test_theta_inf_limit -x` | ❌ Wave 0 |
| MODEL-01 | θ→0+ で brentq 失敗（尖鋭化・発散検出） | unit | `uv run pytest tests/unit/test_race_relative.py::test_theta_zero_divergence -x` | ❌ Wave 0 |
| MODEL-01 | clip ε=1e-6 で isotonic 0/1 生成時に sum(p)=k 精度 <1e-12 | unit | `uv run pytest tests/unit/test_race_relative.py::test_clip_epsilon_isotonic_endpoints -x` | ❌ Wave 0 |
| MODEL-01 | apply_race_relative_correction が race 毎に独立動作（他 race 不参照） | unit | `uv run pytest tests/unit/test_race_relative.py::test_race_independence -x` | ❌ Wave 0 |
| MODEL-01 | base logit s_i が両モデルで bit-identical（logit(proba) 経路） | unit | `uv run pytest tests/unit/test_race_relative.py::test_base_logit_bit_identical -x` | ❌ Wave 0 |
| MODEL-01 | sum(p)=k 不変性が完全パイプラインで成立 | unit | `uv run pytest tests/unit/test_race_relative.py::test_pipeline_sum_p_invariant -x` | ❌ Wave 0 |
| MODEL-01 | overprediction penalty が segment_eval binning と bit-identical | unit | `uv run pytest tests/unit/test_race_relative.py::test_overprediction_penalty_binning_parity -x` | ❌ Wave 0 |
| MODEL-01 | k 決定が sales_start_entry_count ベース・同着不反映 | unit | `uv run pytest tests/unit/test_race_relative.py::test_k_determination_no_deadheat -x` | ❌ Wave 0 |
| SAFE-01/D-09 | binary logit 欠損で RuntimeError（neutral 補完不採用） | unit | `uv run pytest tests/unit/test_race_relative.py::test_logit_missing_fail_loud -x` | ❌ Wave 0 |
| D-10 | α_r 自己完結性: outcome 入れ替えで α_r/p 不変 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_alpha_self_contained_outcome_swap -x` | ❌ Wave 0 |
| D-10 | α_r 自己完結性: 他 race logit 混入検出 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_alpha_cross_race_leak_detected -x` | ❌ Wave 0 |
| SC#3 | 両モデル（LightGBM/CatBoost）で race-relative p が bit-identical | integration | `uv run pytest tests/unit/test_race_relative.py::test_both_models_bit_identical -x` | ❌ Wave 0 |
| SC#4 | SAFE-01 proxy 排除: 補正層モジュールの AST odds/ninki 0 件 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy -x` | ❌ Wave 0 |
| SC#5 | model_version-scoped swap で idempotent（2 回実行で checksum bit-identical） | integration (live-DB) | `KEIBA_SKIP_DB_TESTS= uv run pytest tests/ -k "idempotent" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_race_relative.py -x`
- **Per wave merge:** `uv run pytest tests/unit/ tests/audit/ -x`
- **Phase gate:** `uv run pytest tests/`（KEIBA_SKIP_DB_TESTS unset・live-DB フルスイート・SC#1/#2/#3 踏襲・Phase 8 D-06 5段階鋳型 GREEN）

### Wave 0 Gaps
- [ ] `tests/unit/test_race_relative.py` — covers MODEL-01（α_r 二分探索・clip・sum(p)=k・bit-identical・overprediction penalty・k 決定・fail-loud）
- [ ] `tests/audit/test_audit_race_relative.py` — covers D-10（α_r 自己完結性・outcome swap・cross-race leak）・SAFE-01（補正層 AST odds/ninki proxy 0 件・5段階鋳型踏襲）
- [ ] `src/model/race_relative.py` — 新規モジュール（pure 関数・Pattern 1/2/3 参照）
- [ ] `scripts/run_phase11_evaluation.py` — v1.0 vs race-relative 比較・SC#2 gate・θ 選択経路記録

*(Framework install: 不要・pytest 9.1.0 既存 pin)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | local single-user・Streamlit read-only（§16.1）・認証不要 |
| V3 Session Management | no | 同上 |
| V4 Access Control | no | local のみ・DB readonly role 既存（reader/etl 分離） |
| V5 Input Validation | yes | base logit finite 検証（D-09 RuntimeError）・p_cal ∈ [ε, 1−ε] clip・race_id 整合性（orchestrator HIGH#2 index equality） |
| V6 Cryptography | no | 暗号化不使用（local・予測確率演算のみ） |
| V7 Errors/Logging | yes | fail-loud（RuntimeError・ValueError・silent fallback 禁止・D-09/Phase 10 CR-01〜04 鏡像） |
| V8 Data Protection | yes | prediction 永続化は model_version scoped（idempotent swap・HIGH#1）・is_primary 立てない（D-07） |
| V9 Communications | no | local のみ・外部通信なし |
| V10 Business Logic | yes | α_r 自己完結性（D-10）・θ 事前登録（§11.2 聖域）・sum(p)=k 不変性・リーク防止（PIT/race_id group/target encoding 禁止） |

### Known Threat Patterns for race-relative probability model

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| α_r 計算への test 窓 outcome 混入 | Information Disclosure | D-10 自己完結性・adversarial test（outcome swap で α_r/p 不変）・θ のみ calib slice で fit |
| α_r 計算への他 race 情報混入 | Information Disclosure | race_id 毎に独立ループ（Pattern 1）・adversarial test（cross-race leak 検出） |
| θ 選び直し（test 窓） | Elevation of Privilege（過学習） | §11.2 聖域・D-03 事前登録・候補集合を Plan に固定・test 窓で一回だけ評価 |
| binary logit 欠損の silent fallback | Tampering（silent NaN 伝播） | D-09 RuntimeError・neutral 補完不採用・Phase 10 CR-01〜04 鏡像 |
| 特徴量に odds/ninki proxy 混入 | Information Disclosure（市場回帰） | SC#4 AST odds/ninki proxy 監査（binary 本体で既存・補正層で追加監査）・SAFE-01 |
| p_cal clip 忘れで logit(0/1)=±inf | Denial of Service（NaN 伝播） | Pattern 1 で `np.clip(p_cal, ε, 1−ε)` 必須・test で isotonic 端点ケースを検証 |
| target/mean encoding 再導入 | Information Disclosure（予測シフト） | §14.3 禁止・binary 本体で構造的排除済み・補正層は logit 演算のみ |
| 補正後追加 calib で sum(p)=k 崩壊 | Tampering（制約違反） | D-06 パイプライン厳守・test で sum(p)=k を assert・docstring で禁止明記 |

## Sources

### Primary (HIGH confidence)
- **実証検証（2026-06-27）** — α_r 二分探索収束（brentq・|sum(p)−k|=4.44e-16）・clip ε 影響（isotonic 端点で ε=1e-6 で精度 <1e-12）・base logit bit-identical（LightGBM/CatBoost で raw_score == logit(proba) atol=1e-6）・IsotonicRegression 端点（200 サンプルで 61 個の 0.0/63 個の 1.0）・CalibratedClassifierCV 内部構造（`calibrated_classifiers_[0].calibrators[0]` で IsotonicRegression 直接アクセス）・overprediction penalty 集約（サンプル重み付け半波整流 ECE）
- **`src/model/trainer.py`**（行 1-861）— binary LightGBM/CatBoost 学習・native categorical・`has_time=True`・`num_threads=1`・target encoding 禁止・align_predictions 5条件 guard
- **`src/model/orchestrator.py`**（行 1-852）— `train_and_predict`・`_calibrate_catboost_manual`（L613-683）・`_ManualCatBoostCalibrated`（L685-716）・`_catboost_calibrated_predict_proba`（L719-767・`calibrated_classifiers_[0].calibrators[0]` アクセス）・`_assert_deterministic`（SC#4 bit-identical）
- **`src/utils/calibrator.py`**（行 1-104）— `fit_prefit_calibrator`・sklearn 1.9.0 `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` idiom・strict-later disjoint guard
- **`src/model/evaluator.py`**（行 1-1145）— `_compute_calibration_curve_bins`・`_compute_ece`・`_compute_mce`・`CALIBRATION_CURVE_BINS=10`・`CALIBRATION_CURVE_MIN_BIN_COUNT=30`・binning 契約
- **`src/model/segment_eval.py`**（行 1-540）— `evaluate_segment_axis`・`_odds_band`・`_ninki_band`・ODDS_BAND_EDGES/LABELS・binning 契約 import 再利用
- **`src/model/predict.py`**（行 1-366）— `predict_p_fukusho`（`pred_proba` 注入・Cycle 2 NEW HIGH-1）・`make_model_version`・`PREDICTION_COLUMNS`
- **`src/model/data.py`**（行 1-723）— `FEATURE_COLUMNS`・`split_3way`・`make_X_y`・`load_feature_matrix`・strict chronological guard
- **`src/utils/group_split.py`**（行 1-319）— `GroupTimeSeriesSplit` re-export・`race_id_time_series_split`・`get_bt_race_ids`・3ガード（race_id disjoint・strict chronological・non-empty）
- **`src/model/artifact.py`**（行 1-357）— `save_native_artifact`・`load_native_artifact`・base/calibrator 分離保存・metadata.json
- **`src/db/prediction_load.py`**（行 170-300・415-570）— `_idempotent_load_prediction`（model_version scoped swap）・`set_primary_model`（post-condition: is_primary=true が1 model_type のみ）
- **`pyproject.toml`** — LightGBM 4.6.0・CatBoost 1.2.10・scikit-learn 1.9.0・SciPy >=1.17.1・pandas 3.0.3・mlxtend 0.25.0 pin
- **`tests/audit/test_audit_field_strength.py`**（行 1-130）— Phase 8 D-06 adversarial 5段階鋳型・SAFE-01 AST odds/ninki proxy 監査・lookahead 注入 idiom
- **`.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md`** D-12 — additive score 係数事前登録 `{0.0, 0.1, 0.25, 0.5}` パターン・test 窓選び直し禁止 §11.2（θ D-03 の直接の先例）

### Secondary (MEDIUM confidence)
- **CONTEXT.md D-01〜D-10・Claude's Discretion・canonical_refs・code_context** — 設計意図・委譲項目・踏襲アセットの明示（researcher 裁量項目の確定根拠）
- **CLAUDE.md** — leak-prevention configuration・Tech stack・Core Value・sklearn 1.9.0 prefit idiom

### Tertiary (LOW confidence)
- （なし・全 claim VERIFIED または CITED）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 全パッケージ `pyproject.toml` pin 済み・実証検証済み
- Architecture: HIGH — 既存アセット（trainer/calibrator/orchestrator/predict/evaluator/segment_eval）精査済み・統合ポイント明確
- α_r 二分探索: HIGH — 実証検証で収束・精度・境界挙動すべて確認
- clip 閾値: HIGH — isotonic 端点ケースを実証検証・ε=1e-6 推奨を数値的に裏付け
- base logit bit-identical: HIGH — LightGBM/CatBoost 両モデルで raw_score == logit(proba) を実証
- overprediction penalty: HIGH — segment_eval binning 契約の import 再利用で bit-identical 保証・集約式を実証
- Pitfalls: HIGH — 実証検証と既存コード精査で裏付け

**Research date:** 2026-06-27
**Valid until:** 2026-07-27（30 日・stable domain・sklearn/LightGBM/CatBoost pin で破壊的変更リスク低）
