# Phase 11: Race-Relative Probability Model - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 10 の feature snapshot（`20260626-1a-opponentstrength-v1`・model FEATURE_COLUMNS=79・FEAT-01/02/03 完成）を入力に、**v1.0 の独立二値分類（馬独立 LightGBM `objective='binary'`）から、`race_id` 単位で `sum(p)=払戻対象数` 制約を持つレース内相対確率モデルへ移行する（MODEL-01）**。過大EVを構造的に抑え、`p_fukusho_hit` の確率品質を維持または改善する。

**移行の形（核心）:** binary LightGBM/CatBoost 本体は変更せず、その上に **race-level 補正層（logit temperature + per-race intercept normalization）** を乗せ、各 race で `sum_i p_i = k`（払戻対象数）を厳密に満たす。新モデルは `model_version` で並列保存し、**v1.0 binary は `is_primary` 維持**（EV 本番切替は Phase 12 まで待つ）。

**SAFE-01（odds/ninki/過去人気/過去オッズ proxy 排除）**・**リーク防止（PIT correct・race_id group split・merge_asof backward・adversarial audit・α_r は test 窓 outcome 不使用の自己完結変換）**・**再現性（§19.1・bit-reproducible・FIXED_REPRODUCE_TS）**・**§15.2 事前登録指標不変（後知恵すり替え禁止）**・**§11.2 test窓は最終評価のみ** を聖域として厳守。

**Phase 11 が届けないもの（別 Phase）:**
- `p_lower`（下側信頼限界）EV 判定 — Phase 12 EV-01
- 評価指標の本格拡張（EV-decile ROI / model-market disagreement ROI / snapshot-final slippage）・正規 falsification test（`logit(outcome) ~ logit(market) + logit(model)`・race_id clustered SE）・bootstrap 統計有意 — Phase 12 EVAL-01/02
- is_primary 切替・UI/EV の新 p 参照切替 — Phase 12（p_lower/selected-only/falsification 評価後に判断）

</domain>

<decisions>
## Implementation Decisions

### 確率モデルの枠組み（MODEL-01・SC#1 核心）

- **D-01:** **hybrid（binary 学習 + race-level 補正層）** を採用。`src/model/trainer.py` の binary LightGBM/CatBoost（`objective='binary'`）は**そのまま再利用・本体不変**（SC#3 bit-identical 维持・Phase 4/6 資産活用）。その上に race-conditional 補正層を新規追加し `sum(p)=払戻対象数` を実現する。post-hoc 正規化（binary を softmax 再配分のみ）でも listwise/Plackett-Luce 学習（根本から race-conditional 学習に切替）でもない中間。
- **D-02:** 補正層は **logit temperature + per-race intercept normalization**。binary model の base logit を `s_i` とし、各 race で `p_i = sigmoid(s_i / θ + α_r)` とする。race 内で `sum_i p_i = k`（払戻対象数）を満たす `α_r` を**二分探索**で解く。これにより (a) race 内 `sum(p)=k` を厳密に満たし、(b) 各 `p_i` は常に `(0,1)` に収まる（`k * softmax` は p>1 リスクがあるため不採用）。binary 本体は不変・補正層のみ追加。
- **D-03:** 温度 **θ は制約付き選択（事前登録）** で決める。候補集合は planner が Plan 内で事前登録し、**test 窓での再選択は禁止（§11.2 聖域）**。選択ルール: (1) **足切り** — overall Brier/LogLoss が binary baseline から事前登録マージン（D-04）を超えて悪化する θ を除外。(2) **選択** — 残候補から selected/high-EV 層・`odds_band×p_bin` の **overprediction penalty**（予測率 > 実現率 の正方向誤差だけを重く見る）が最小の θ。(3) **tie-break** — `calibration_max_dev`、さらに同値なら **θ=1 に近い候補**。θ は train/calib の later-disjoint calib slice のみで選ぶ。設計意図: 「全体品質で足切り → 投票層過大予測で選択」（odds-band だけだと全体確率を壊す危険・Brier/LogLoss だけだと投票層の病巣に鈍い）。

### 非劣化マージン・SC#2 評価 gate（事前登録・評価後変更禁止 §11.2）

- **D-04:** 全体非劣化マージンは **Phase 11 向け拡張: Brier ≤ 0.005 / LogLoss ≤ 0.010 / AUC ≤ 0.005**（v1.0 LightGBM Phase 6 D-07 水準 Brier=0.15222/LogLoss=0.47488/AUC=0.73230 に対する悪化許容幅）。race-conditional 再配分・平坦化による全体 Brier/LogLoss の微小悪化を許容し、SC#2 本題（selected-only/odds-band 改善）を優先。**AUC は logit temperature + per-race intercept が race 内 logit 順序を保存する（sigmoid 単調・α_r は race 内一様加算）ため binary baseline とほぼ維持**される構造的理由から ±0.005 に固定。これは θ 足切り（D-03）と SC#2 全体評価の**統一閾値**。後追い緩和でなく・race-conditional 構造的変化への根拠再確認として事前登録（memory `perf-threshold-sanctuary-rationale-rebase` 整合）。
- **D-05:** SC#2「v1.0 より改善」の判定は **overprediction penalty 絶対改善（主指標）+ selected-only calibration セーフガード** の **3 必須条件 gate**: (1) `odds_band×p_bin` の overprediction penalty が v1.0 binary より低い、(2) selected/high-EV 層の「平均予測率 − 実現率」が v1.0 より低い、(3) selected-only `calib_max_dev` が事前登録マージン（D-04）を超えて悪化しない。**bootstrap 統計的有意検定は Phase 12 EVAL-02 に委譲**・Phase 11 では方向性と非劣化 gate のみ。θ は calib slice で選び、test 窓ではこの事前登録 gate で**一回だけ**評価する。設計意図: 「過大予測は減ったが selected 層が壊れた」を防ぐ多層防御。

### 制約とキャリブレーションの統合順序（SC#1 later-disjoint との両立）

- **D-06:** **base calib → 補正** の順序。完全パイプライン: `raw binary model → fit_prefit_calibrator → p_cal → clip → logit(p_cal) → θ + per-race α_r → final p`。`fit_prefit_calibrator`（`src/utils/calibrator.py`・sklearn 1.9.0 `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` idiom・later-disjoint strict `<`・SC#1 準拠）で base logit を事前整定し、整定済み logit に θ+α_r を適用して `sum(p)=k` を厳密達成。**補正後に追加 calib はしない**（sum(p)=k が崩れ α_r 再適用でループになるため）。calib → 正規化の順なので sum(p)=k は崩れない。`p_cal` の clip 閾値（0/1 での inf 回避）等の境界数値は researcher 裁量。

### v1.0 binary との共存（SC#5・Phase 7 UI・Phase 12 EV 影響）

- **D-07:** **並列比較のみ・is_primary は v1.0 binary 維持**。Phase 11 は確率構造の移行フェーズ・**EV 本番切替（UI/EV の新 p 参照・is_primary 切替）は Phase 12（p_lower EV + selected-only/falsification 評価）まで待つ**。新 race-relative model は `model_version` で `prediction.fukusho_prediction` に保存（model_version-scoped idempotent swap・HIGH#1 踏襲）・Phase 11 では比較レポートで SC#2 を確認。**is_primary 切替は Phase 12 で判断**。Phase 7 UI/loader（`is_primary=true` SELECT）・EV 計算は v1.0 binary のまま（実質的運用基準を Phase 12 評価前に変えない・§11.2 聖域整合・memory `review-gate-plan-to-execute-core-value-phase` 整合）。

### 安全性（k 決定・欠損馬・α_r 自己完結性・core value 核心）

- **D-08:** 複勝払戻対象数 **k の決定 = 予測時点固定頭数ルール**。`k = feature_cutoff_datetime`（発売開始時点・Phase 2 D-04 `sales_start_entry_count`）の頭数ベース固定（8頭以上=3・5-7頭=2・4頭以下=複勝発売なしなのでモデル対象外）。**同着は事後情報なので k に反映しない**（予測時点では同着不明・未来リーク防止）。`sum(p)=k` の k は予測時点で確定・§10 ラベル基準と整合。学習時 `sum(label)` は同着で k を超えうるが、予測 `p` は固定 k（確率=予測時点・label=事後の不一致を許容・明文化）。
- **D-09:** **binary logit 欠損は許容しない（fail-loud）**。α_r 二分探索の母集団は **k 決定に使った予測対象の全馬**とし、全馬に finite な base probability/logit が存在することを**前提条件として `RuntimeError` で検証**する。特徴量欠損（過去走不足・speed profile 欠損等）は LightGBM/CatBoost が NaN として native 処理して logit を出すため、**binary logit 欠損とは区別**する。`p_cal` は clip して logit 変換するが、`p_cal` 自体が欠損する行があれば race-relative 補正に進まず `RuntimeError`。**neutral logit 補完・非欠損馬だけへの k 配分は不採用**（バグを隠す silent fallback・Phase 10 gap-closure CR-01〜04「silent fallback 禁止」の鏡像）。設計意図: 「欠損馬をどう扱うか」でなく「予測対象馬に logit 欠損を出さない」のが正しい設計。
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ロードマップ・要件（聖域）
- `.planning/ROADMAP.md` — Phase 11 section・SC#1-5（SC#1 sum(p)=払戻対象数/GroupTimeSeriesSplit/fit_prefit_calibrator・SC#2 事前登録非劣化+selected-only/odds-band 改善・SC#3 LightGBM+CatBoost bit-identical・SC#4 SAFE-01 proxy 排除/`.cat.codes.min()>=0`・SC#5 §19.1 metadata model_version-scoped swap）・Depends on Phase 10
- `.planning/REQUIREMENTS.md` — MODEL-01（レース内相対確率モデル）・SAFE-01（odds-free/proxy 排除）・Out of Scope（過去人気/過去オッズ proxy は市場回帰で除外）
- `docs/keiba_ai_requirements_v1.3.md` — 要件正（§8.4 race_id group・§10 払戻対象数/同着/返還・§11.2 test窓聖域・§14.3/§14.4 categorical leak-safe・§15.2 事前登録指標不変・§19.1 再現性）
- `.planning/PROJECT.md` — Key Decisions（core value 再定式化・過去人気/オッズ proxy 除外）・v1.1 Current Milestone・Out of Scope

### 前 Phase の決定（事前登録パターン・評価方針の踏襲）
- `.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md` — D-12 係数事前登録パターン（候補集合 + train/calib 窓内のみ + test 窓選び直し禁止 §11.2・θ 事前登録 D-03 の直接の先例）・D-15/D-16 SC#5 非劣化 gate + 参考記録（Phase 11 で selected-only/odds-band が必須 gate に昇格）・D-09 欠損 NaN 保持・母集団除外（logit 欠損 fail-loud D-09 との対比）
- `.planning/phases/09-speed-figure-foundation/09-CONTEXT.md` — D-11 sentinel/nullable（magic number 不採用）・PIT strict `<`・latest-K rolling

### 踏襲アセット（コード・必読）
- `src/model/trainer.py` — `train_lightgbm` / `train_catboost`（`objective='binary'`・native categorical・`has_time=True`・`num_threads=1`・D-04-03）・**binary 本体不変の対象**（D-01）
- `src/utils/calibrator.py` — `fit_prefit_calibrator`（`FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` idiom・`method`・strict-later disjoint guard）・D-06 パイプラインの base calib
- `src/model/calibrator.py` — strict-later disjoint 保証・Phase 4/6 の calib 適用 idiom
- `src/utils/group_split.py` — `GroupTimeSeriesSplit` re-export + strict chronological（`max(train)<min(test)`・race_id group・§8.4）
- `src/model/orchestrator.py` — `train_and_predict`（strict-later disjoint guard・CatBoost manual calib・aligned pred_proba 注入）・**補正層統合先**（D-01/D-06）
- `src/model/data.py` — `FEATURE_COLUMNS` allowlist・`make_X_y`（完全一致 assert）・`split_3way`・`load_feature_matrix(snapshot_id)`・`_carve_calib_from_train_tail`
- `src/model/segment_eval.py` — `odds_band×p_bin`・selected-only calibration・binning 契約（`_compute_calibration_curve_bins`/`_compute_ece`/`_compute_ece`）・**overprediction penalty 測定の土台**（D-03/D-05）
- `src/model/evaluator.py` — §15.2 事前登録指標（calibration_max_dev/Brier/LogLoss 不変）・`check_acceptance_gate`・D-07 LightGBM 水準（SC#2 非劣化の比較対象）
- `src/model/predict.py` — `prediction_load`（model_version-scoped swap・HIGH#1 idempotent）・**新 race-relative model 永続化先**（D-07/SC#5）
- `src/model/artifact.py` — `save_native_artifact` / `load_native_artifact`（CalibratedClassifierCV 分離保存・bit-identical 再構築）
- `tests/audit/` — adversarial 5段階鋳型・SC#1/#2/#3・**α_r 自己完結性テスト（D-10）・logit 欠損 fail-loud テスト（D-09）の追加先**

### 外部2AI リサーチ・文献
- `.planning/research/v1.1-domain-analysis.md` — レース内相対確率モデルの P0 位置づけ・層分離（§5: p モデル odds-free）・falsification（§6: Phase 12 EVAL-02 委譲）・文献（§8）
- Benter (1994)・Bolton & Chapman (1986)・Hausch/Ziemba/Rubinstein (1981) — fundamental model・relative performance・Harville/Plackett-Luce 的 rank probability の文献（domain-analysis §8）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `train_lightgbm` / `train_catboost`（`trainer.py`）: binary 本体はそのまま再利用（D-01）。base logit `s_i` は `model.predict_proba(... )[:,1]` または `decision_function` 相当から取得（CatBoost は aligned pred_proba 注入 idiom・orchestrator HIGH-1 踏襲）。
- `fit_prefit_calibrator`（`utils/calibrator.py`）: base logit の事前整定（D-06 パイプライン）。later-disjoint strict `<` は既存 guard が保証。
- `GroupTimeSeriesSplit`（`utils/group_split.py`）: train→calib→test の race_id group 時系列分割（SC#1）。`split_3way` で固定 BT窓。
- `segment_eval.py`（`odds_band×p_bin` / selected-only calibration / binning 契約）: overprediction penalty（D-03/D-05）の測定土台。bit-identical 保証のため独自 binning は導入せず import 再利用。
- `evaluator.py`（`check_acceptance_gate` / §15.2 事前登録指標）: SC#2 非劣化 gate と改善 gate（D-04/D-05）の評価。D-07 LightGBM 水準が比較対象。
- `predict.py`（`prediction_load` model_version-scoped swap）: 新 race-relative model の DB 永続化（D-07/SC#5）。
- `artifact.py`（`save_native_artifact` 分離保存）: θ・α_r アルゴリズム参数 + metadata の再現性ある保存。

### Established Patterns
- **binary 不変 + 補正層追加** — trainer.py を触らず・新層で race-conditional 性を入れる（SC#3 bit-identical 维持・fake-green 防止）。
- **later-disjoint strict `<` calib** — `fit_prefit_calibrator` + `_carve_calib_from_train_tail`（θ 選択も calib slice のみ・§11.2 聖域）。
- **race_id group 時系列分割** — GroupTimeSeriesSplit・§8.4（同一 race_id の train/test またぎ禁止）。
- **事前登録パターン**（Phase 10 D-12）— 候補集合を Plan に書き・train/calib 窓内のみで選び・test 窓で選び直さない（θ D-03・非劣化マージン D-04）。
- **fail-loud（silent fallback 禁止）** — logit 欠損 RuntimeError（D-09）・`.cat.codes.min()>=0`（SC#4）・Phase 10 gap-closure CR-01〜04 鏡像。
- **adversarial 5段階鋳型**（Phase 8 D-06 / tests/audit/）— α_r 自己完結性（D-10）・lookahead・proxy 排除。
- **byte-reproducible**（`FIXED_REPRODUCE_TS` + 固定 thread/seed・`np.array_equal`）— SC#3 両モデル bit-identical。
- **AUC 順序保存の構造的理由** — sigmoid 単調 + α_r race 内一様加算で logit 順序保存 → AUC は binary baseline とほぼ維持（D-04 根拠）。

### Integration Points
- `orchestrator.train_and_predict` 拡張 — binary 学習 → `fit_prefit_calibrator` → base logit 取得 → 補正層（θ + per-race α_r 二分探索）→ final `p_fukusho_hit`（D-06 パイプライン）。
- `predict.py` — 新 race-relative model を model_version で永続化（is_primary は立てない・D-07）。§19.1 metadata（model_version・feature_snapshot_id・label_version・`odds_snapshot_policy`・`backtest_strategy_version`）。
- `evaluator.py` / `segment_eval.py` — SC#2 評価（非劣化 gate D-04 + 改善 gate D-05）・v1.0 binary との比較レポート（reports/11-*）。
- `tests/audit/` — α_r 自己完結性（D-10）・logit 欠損 fail-loud（D-09）・SAFE-01 proxy 排除（SC#4）の adversarial テスト追加。

</code_context>

<specifics>
## Specific Ideas

- **「全体品質で足切り → 投票層過大予測で選択」**（θ 選択 D-03）がユーザーの方針。odds-band miscalib 単独だと全体確率を壊す危険・Brier/LogLoss 単独だと投票層の病巣に鈍い → 両方統合した制約付き選択。
- **「過大予測は減ったが selected 層が壊れた」を防ぐ**（SC#2 gate D-05）が3必須条件の設計動機。
- **`k * softmax` は p>1 リスク** があるため sigmoid + per-race intercept 二分探索を採用（p∈(0,1) 厳密）。ユーザーの明示的指摘。
- **「欠損馬をどう扱うか」でなく「予測対象馬に logit 欠損を出さない」のが正しい設計**（D-09）。neutral 補完はバグを隠す silent fallback として不採用。
- **`sum(p)=k` の k は予測時点固定・同着は事後情報**（D-08）。学習 label は同着で k 超えうるが、確率モデルの制約は予測時点 k（確率=予測時点・label=事後の不一致を許容）。
- **EV 本番切替は Phase 12 まで待つ**（D-07）。Phase 11 は確率構造の移行フェーズ・UI/EV をここで新 p に切替えると Phase 12 評価前に実質的運用基準が変わる（聖域整合）。
- **AUC は logit 順序保存で維持**（D-04）— 変動するのは確率値依存の Brier/LogLoss のみ。Phase 10 同値（Brier≤0.002）より Phase 11 拡張（Brier≤0.005）にする根拠は race-conditional 構造的変化（緩和でなく根拠再確認）。

</specifics>

<deferred>
## Deferred Ideas

- **is_primary 切替・UI/EV の新 p 参照** — Phase 12（p_lower EV + selected-only/falsification 評価後に判断・D-07）
- **bootstrap 統計有意検定**（overprediction 減少の race_id clustered SE）— Phase 12 EVAL-02 falsification と統合（D-05）
- **`p_lower`（下側信頼限界）EV 判定** — Phase 12 EV-01
- **評価指標の本格拡張**（EV-decile ROI / model-market disagreement ROI / snapshot-final slippage）・正規 falsification test（`logit(outcome) ~ logit(market) + logit(model)`）— Phase 12 EVAL-01/02
- **listwise/Plackett-Luce による根本的 race-conditional 学習**（D-01 hybrid と比較した将来 refinement・本 Phase では binary 不変の hybrid を採用）

*None folded from todos — discussion stayed within phase scope（todo.match-phase 0 件）*

</deferred>

---

*Phase: 11-Race-Relative Probability Model*
*Context gathered: 2026-06-27*
