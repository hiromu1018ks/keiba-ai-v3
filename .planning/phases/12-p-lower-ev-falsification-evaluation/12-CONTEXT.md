# Phase 12: p_lower EV & Falsification Evaluation - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 11 のレース内相対確率モデル `p_fukusho_hit`（race-relative model・θ=1.0・`is_primary=f` で永続化済み・`20260626-1a-opponentstrength-v1-lgbrr-v1`・22793行）を前提に、v1.1 マイルストーン最終フェーズとして以下を統合する:

1. **EV-01**: EV 判定を点推定 `p` から `p_lower × odds_lower`（下側信頼限界）へ移行
2. **EVAL-01**: 評価指標拡張（selected-only calibration / EV-decile 別実現 ROI / model-market disagreement 別 ROI / odds snapshot→final payout slippage）
3. **EVAL-02**: falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` で odds-free market residual を時系列 out-of-sample で統計検証（特徴量不足 vs 構造的限界の鑑別）
4. **SAFE-01**: オッズ帯別条件付き calibration を受入 gate（Phase 12 専用 WARN）化し、投票層の過大予測を構造的検出
5. **is_primary 切替判断材料の提示**（Phase 11 D-07 委譲・切替実行は人間承認の別アクション）

**層分離（domain-analysis §5・core value 再定式化の機構）:** `p` モデルは odds-free のまま（SAFE-01・特徴量に入れない）。**診断・EV・evaluation 層で odds を使って** `p` の過大予測を検出し EV 判定する。これが Phase 11 の D-05-1 overprediction penalty NaN FAIL（odds-free 1-A snapshot に odds/ninki がないため計算不能）を「診断層で odds を結合」することで解く正統な道。

**Phase 12 が届けないもの（別 Phase）:**
- 新たな特徴量追加（FEAT 系は Phase 9/10/9.1 完了・Phase 12 は EV/eval/falsification のみ）
- `is_primary=true` 切替の実行（switch_recommendation は出すが DB 自動変更はしない・人間承認の別アクション・Phase 11 D-07 踏襲）
- UI の本格改修（Phase 7・is_primary 切替後に UI 参照が変わるが UI 改修自体は別検討）
- listwise/Plackett-Luce による根本的 race-conditional 学習（Phase 11 D-01 と同じ・将来 refinement）
- 当日情報モデル（Phase 2 別マイルストーン）

**SAFE-01（odds/ninki/過去人気/過去オッズ proxy 排除）**・**リーク防止（PIT correct・race_id group split・merge_asof backward・adversarial audit・falsification は train/calib で設計し test 窓は評価のみ）**・**再現性（§19.1・byte-reproducible・FIXED_REPRODUCE_TS）**・**§15.2 事前登録指標不変（後知恵すり替え禁止）**・**§11.2 test 窓は最終評価のみ** を聖域として厳守。

</domain>

<decisions>
## Implementation Decisions

### p_lower 手法（SC#1・EV-01）

- **D-01:** **手法 = calibration-residual based lower bound（split conformal 風）**。later-disjoint calib slice で **overprediction residual `r = max(0, p_final - y)`** を計算し、その q_level 分位を保守的に差し引く。これは個体ごとの真の確率に対する厳密な信頼下限でなく、calib slice 上の過大予測を保守的に差し引く**分布自由な shrinkage rule**。race_relative.py の base logit `s_i` 由来の `p_final`（race-relative 補正後）に適用。
- **D-02:** **shrinkage quantile の表記（変数名と意味の分離・誤読防止）**:
  - shrinkage quantile は **`q_level=0.90`** と表記（`q_alpha` という変数名は**避ける**・「0.90 を直接 p から引く」意味でない）
  - `q_shrink` = calib slice の `r = max(0, p_final - y)` の q_level 分位（**実数値**）
  - **`p_lower = max(0, p_final - q_shrink)`**
  - report には **`q_level` と `q_shrink` 実数値を両方**出す（誤読防止・監査性）
  - `q_level=0.90` は shrinkage 強度の事前登録値・test 窓で変更不可（§11.2 聖域）
  - **coverage 表現は「p 信頼区間保証」でなく**、calib/test 上で**実測 coverage と selected-only calibration を報告**する（conformal は潜在確率の区間保証でなく outcome coverage / prediction set 的保証・過度な保証主張しない）
- **D-03:** 適用対象 = **race-relative 補正後の `p_final`**（orchestrator の race-relative 補正後に p_lower 生成を挿入）。`odds_lower` = 既存 **`fuku_odds_lower`**（JODDS snapshot・`odds_snapshot.py` 再利用）。`EV = p_lower × odds_lower`。purchase_simulator/ev_rank は `p × odds` → `p_lower × odds_lower` へ（構造変更不要・入力列差し替え）。

### falsification 統計仕様（SC#3・EVAL-02）

- **D-04:** **`market_implied` = 再校正**。train/calib 窓で `1/odds` を outcome に calibration（isotonic/Platt）し overround・FLB・複勝プール歪みを除去した「真の市場暗示確率」。model_p 係数が「市場にない純粋な residual」を測り、鑑別（特徴量不足 vs 構造的限界）に直接的。falsification は train/calib で設計し **test 窓の予測のみで評価**（§11.2 聖域）。market 情報は診断層のみ・`p` モデルには入れない（EVAL-02/SAFE-01）。
- **D-05:** **有意判定 = 標準 α=0.05**。model_p 単一係数の **race_id clustered 標準誤差**（race 内の outcome は独立でないため）で p値 < 0.05 で「市場 residual が残る」。bin/odds_band 別サブ解析でのみ Holm 補正（多重比較）。**統計仕様を事前登録**: (a) market_implied 定義=D-04 再校正、(b) race_id clustered SE=D-05、(c) field size 共変量・odds clipping（極端オッズの丸め）の統制は planner が calib sample size で事前登録。鑑別結果（model_p 有意=特徴量不足 / 非有意=構造的限界）を reports/ に honest 記録。

### 拡張指標の扱い（SC#2・EVAL-01）

- **D-06:** **§15.2 既存 BLOCK/WARN gate は不変**（calibration_max_dev/Brier/LogLoss/sum(p) 分布・後知恵すり替え禁止・聖域）。**selected-only calibration / odds-band conditional calibration = Phase 12 専用 WARN gate**（core value 再定式化「オッズ帯別条件付き calibration・過大でないこと」の直接的測定・報告のみでなく gate 化）。**BLOCK にはしない**（Phase 12 は切替判断材料を出すフェーズ・WARN が適切・v1.0 の「p=0.16→実0.04 の4倍過大」を catch する gate）。
- **D-07:** **EV-decile ROI / model-market disagreement ROI / snapshot→final payout slippage = `switch_recommendation`（D-09）入力 + 報告のみ**（gate 化しない・§15.2 gate とは別枠の診断指標）。現実回収率 0.78-0.92 を正直に測る。

### is_primary 切替（Phase 11 D-07 委譲）

- **D-08:** **is_primary 切替 = 結果次第・事後判断**（評価結果を見ずに自動切替しない）。Phase 12 は「本番切替フェーズ」でなく **p_lower EV と falsification で使う価値を鑑別するフェーズ**。事後判断を野放しにしないため D-09/D-10 の機構で構造化。
- **D-09:** **`switch_recommendation` 機構**。以下を統合し report に **`switch / hold / reject`** を出す:
  - SC#4 オッズ帯別条件付き calibration gate（投票層過大予測の v1.0 binary からの統計的改善）
  - p_lower EV の v1.0 binary 比較（回収率）
  - falsification の model_p residual（特徴量不足 vs 構造的限界の鑑別）
- **D-10:** **実際の `is_primary=true` 切替は人間承認の別アクション**。Phase 12 では DB の is_primary 変更を自動で行わない（`set_primary_model` Call 0件・AST check・Phase 11 D-07 踏襲）。switch_recommendation は「判断材料」で「実行」でない。

### Claude's Discretion

- **SC#4 gate の具体的閾値** — 投票層過大予測の許容幅・odds_band 区分（ODDS_BAND_EDGES [0,2.9,4.9,9.9,inf] を踏襲しつつ投票層の定義）は planner が事前登録パターン（Phase 10 D-12 / Phase 11 D-03）で Plan 内に固定・test 窓選び直し禁止。
- **再校正方法（isotonic / Platt）** — calib sample size で RESEARCH.md が比較検討。Platt（sigmoid）は parametric・安定、isotonic は柔軟だが過学習リスク。
- **odds clipping 範囲・field size 共変量** — planner が事前登録（極端オッズの 1/odds 飽和・inf 回避・field size strata または共変量）。
- **p_lower の bin/race 条件付き残差** — 全体 shrinkage（D-01）を主軸としつつ、race_id / odds_band 条件付き残差（D-01 修正文で言及）を RESEARCH.md で比較検討。条件付きは SC#4 との役割分担で判断。
- **snapshot→final slippage の具体的測定** — refund_accounting の HARAI PayFukusyoPay（final payout）と odds_snapshot の fuku_odds_lower の差分。planner が測定式を事前登録。
- **bootstrap / ensemble p_lower** — D-01 conformal 風 shrinkage を主軸。bootstrap・ensemble は RESEARCH.md で比較表作成・fallback（時系列 exchangeability に数値的阻害時）として事前登録。
- **statsmodels 依存追加** — clustered SE（`cov_type='cluster'`）・logit 回帰に必要・現状 pyproject.toml に無し。planner が追加（scipy は既存）。
- **prediction.fukusho_prediction への p_lower 列追加** — `PREDICTION_ADD_P_LOWER_SQL`（idempotent `ADD COLUMN IF NOT EXISTS`・schema.py L145-181 パターン）・PREDICTION_COLUMNS 拡張・3ファイル連鎖（schema/predict/prediction_load・Pitfall 4 列数一致 assert）。
- **falsification / switch_recommendation の report 構造** — reports/12-* の構成（falsification 回帰結果・鑑別結論・switch_recommendation・SC#4 WARN gate・§15.2 不変指標の併載・byte-reproducible）。
- **run_phase12_evaluation.py のひな形** — run_phase11_evaluation.py の構造（_select_theta_on_calib 相当の q_shrink 計算・_evaluate_gate・事前書き出し・load_predictions swap）を踏襲。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ロードマップ・要件（聖域）
- `.planning/ROADMAP.md` — Phase 12 section・SC#1-5（SC#1 p_lower train/calib 設計・test 窓閾値すり替え禁止 / SC#2 §15.2 不変 + 拡張指標併載・投票層 miscalibration 定量化 / SC#3 falsification 事前登録 market_implied・race_id clustered SE・field size/odds clipping 統制 / SC#4 オッズ帯別条件付き calibration 受入 gate / SC#5 対抗的監査 GREEN・byte-reproducible・現実回収率 0.78-0.92）・Depends on Phase 11
- `.planning/REQUIREMENTS.md` — EV-01（p_lower 移行）/ EVAL-01（指標拡張）/ EVAL-02（falsification）/ SAFE-01（オッズ帯別条件付き calibration 受入基準）・Out of Scope（過去人気/過去オッズ proxy 除外・市場回帰）
- `docs/keiba_ai_requirements_v1.3.md` — §11.2 test 窓聖域・§15.2 事前登録指標不変・§19.1 再現性・§14.3/§14.4 categorical leak-safe・§10 払戻対象数/同着/返還
- `.planning/PROJECT.md` — Key Decisions（core value 再定式化「`p` とオッズの独立性」→「オッズ帯別条件付き calibration・過大でないこと」・過去人気/オッズ proxy 除外）・v1.1 Current Milestone・Out of Scope

### ドメイン分析・学術
- `.planning/research/v1.1-domain-analysis.md` — §0 正直な結論（現実 0.78-0.92・悲観 0.65-0.80 天井）・§1 core value 再定式化（独立性は強すぎる・条件付き calibration が真の要件）・§5 ML 設計の層分離（`p` モデル odds-free / calibration odds-free / EV-selector 層=p・p_lower・odds / evaluation 層=odds 帯別診断）・§6 拡張評価指標 + falsification test（Codex 提唱・`logit(outcome)~logit(market)+logit(model)`・「次マイルストーンに必須」）・§7 シナリオ・§8 文献（Benter 1994 / Bolton & Chapman 1986 / Hausch,Ziemba,Rubinstein 1981 / Lessmann et al. 2010 等）

### 前 Phase の決定（事前登録パターン・honest 記録の踏襲）
- `.planning/phases/11-race-relative-probability-model/11-CONTEXT.md` — D-07 is_primary 委譲（Phase 12 で判断・切替は Phase 12）・D-03 θ 事前登録パターン（候補集合 + train/calib 窓内のみ + test 窓選び直し禁止 §11.2）・D-05 改善 gate 3 条件（overprediction penalty・selected-only・calib_max_dev）・D-06 base calib→補正順序・D-10 α_r 自己完結性 adversarial
- `reports/11-evaluation/11-evaluation.md` — SC#2 gate honest FAIL（D-04 非劣化 PASS: Brier -0.00323 / LogLoss -0.01355 / AUC +0.01896 全改善 / D-05 条件1 overprediction penalty NaN FAIL: odds-free 1-A で odds/ninki なく計算不能 / 条件2/3 PASS）・selected θ=1.0
- `reports/11-evaluation/theta-selection.md` — θ 選択経路（calib slice のみ・stage1 cutoff→stage2 NaN-safe→stage3 tiebreak θ=1 近傍・§11.2 聖域）
- `.planning/phases/11-race-relative-probability-model/11-05-SUMMARY.md` — SC#2 FAIL honest 記録の経緯・「D-15 overprediction penalty を活かすには odds 情報を予測時に結合する経路が必要」・race-relative 行 is_primary=f 永続化（22793行・baseline v1.0 binary is_primary=t 22213行）・SC#3 bit-identical / SC#5 idempotent swap PASS
- `.planning/phases/11-race-relative-probability-model/11-VERIFICATION.md` — SC#2 gate FAIL は goal 未達でなく honest 記録（race-relative model 実評価結果）・MODEL-01/SAFE-01 SATISFIED
- `.planning/phases/10-opponent-strength-race-relative-features/10-CONTEXT.md` — D-12 係数事前登録パターン（候補集合 {0.0,0.1,0.25,0.5} + train/calib 窓内のみ・θ D-03 の直接の先例）・D-15/D-16 SC#5 非劣化 gate + 参考記録（Phase 11 で selected-only/odds-band が必須 gate に昇格）

### 踏襲アセット（コード・必読）
- `src/ev/purchase_simulator.py` — `select_bets`（`p_fukusho_hit` + `fuku_odds_lower` → EV_lower 3閾値フィルタ・**p_lower 拡張ポイント**: EV_lower=p_lower×odds_lower へ・stake/effective_stake/payout/refund は refund_accounting で処理・構造変更不要）
- `src/ev/ev_rank.py` — `compute_ev_and_rank`（EV_lower=p×odds_lower / EV_upper=p×odds_upper・S/A/B/C/D ランク・**p_lower 切替ポイント**: p_lower 列追加時 EV_lower=p_lower×odds_lower）
- `src/ev/odds_snapshot.py` — `select_odds_snapshot`（`fuku_odds_lower`/`fuku_odds_upper`・JODDS mid-race snapshot・÷10 parse・**odds_lower としてそのまま再利用**）
- `src/ev/metrics.py` — `compute_backtest_metrics`（純粋関数 DB 不要・**EV-decile/disagreement ROI 追加土台**: group-by → compute_backtest_metrics per group）
- `src/ev/refund_accounting.py` — `determine_stake_payout`（HARAI PayFukusyoPay final payout slot lookup・**slippage 計算の土台**: payout/100 - fuku_odds_lower）
- `src/ev/report.py` — `generate_report`（REPORT_COLUMNS 11列・**EV-decile/disagreement/slippage/switch_recommendation 追加表示**・BACK-04 winner 強調禁止踏襲）
- `src/model/segment_eval.py` — `evaluate_all_segments` / `evaluate_segment_axis`（odds_band 4 band [0,2.9,4.9,9.9,inf]・`_compute_calibration_curve_bins`/`_compute_ece` import・**selected-only calib / EV-decile / disagreement binning 拡張ポイント**・独自 binning 禁止）
- `src/model/evaluator.py` — `check_acceptance_gate`（BLOCK/WARN hybrid・L888-1029・**Phase 12 専用 WARN gate 拡張ポイント**: selected-only/odds-band conditional calib を warn_reasons に追加・事前登録閾値）
- `src/model/race_relative.py` — `apply_race_relative_correction`（base logit `s_i`・**p_lower の r=max(0,p_final-y) 計算に再利用**）・`compute_overprediction_penalty`（`market_signal` 引数・SAFE-01 allowlist マーカー `SAFE-01-ALLOW: market_signal`）
- `src/model/orchestrator.py` — `train_and_predict`（race-relative 補正 L714-754・**L754 後に p_lower 生成挿入**・pred_df meta 列付与 L801-826 パターン再利用）
- `src/model/predict.py` — `predict_p_fukusho` / `PREDICTION_COLUMNS`（19列・**p_lower 列追加**: `p_fukusho_hit_lower`・DDL migration・`_assert_valid_prediction_df` 拡張）
- `src/model/artifact.py` — `save_native_artifact`（`race_relative_theta` metadata.json L213・**q_level / shrinkage method パラメータ保存ポイント**・既存 theta パターン踏襲）
- `src/db/schema.py` — `PREDICTION_TABLE_DDL`（CREATE TABLE L61-101・ALTER L145-181・`_ALL_MIGRATIONS` L386-392・**p_lower 列 idempotent ADD COLUMN IF NOT EXISTS**）
- `scripts/run_phase11_evaluation.py` — **run_phase12_evaluation.py のひな形**（`_select_theta_on_calib` 相当の q_shrink 計算 calib slice のみ・`_evaluate_gate`・theta-selection 事前書き出し・`load_predictions` public wrapper・`_sanitize_for_json`/`_atomic_write_text`/`_attach_label_to_pred` 再利用）
- `tests/audit/` — adversarial 5段階鋳型（`test_audit_race_relative.py` L11-27・**SAFE-01 p_lower proxy 排除 AST テスト・falsification leakage テスト追加先**・D-10 自己完結性テスト踏襲）

### 外部依存
- `pyproject.toml` — scipy>=1.17.1 既存（brentq・stats）。**statsmodels 未追加**（clustered SE `cov_type='cluster'`・logit 回帰に必要・planner が追加）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **race_relative.py の base logit `s_i`** — p_lower の overprediction residual `r = max(0, p_final - y)` 計算に再利用（apply_race_relative_correction の p_final を入力）。
- **`fuku_odds_lower` / `fuku_odds_upper`**（odds_snapshot.py）— odds_lower としてそのまま再利用。EV = p_lower × odds_lower。HARAI PayFukusyoPay が final payout（slippage 計算の対）。
- **segment_eval の `evaluate_segment_axis` + binning 契約** — EV-decile / disagreement ROI binning に再利用（`pd.qcut(EV_lower, 10)` / `|model_logit - market_logit|` を新 axis に）。独自 binning 禁止・bit-identical。
- **evaluator の `check_acceptance_gate`** — Phase 12 専用 WARN gate（selected-only/odds-band conditional calib）を warn_reasons に追加。hybrid gate パターン踏襲。
- **run_phase11_evaluation.py の構造** — θ選択経路 calib slice のみ・事前登録 gate・honest 記録・load_predictions swap。Phase 12 の q_shrink 計算・switch_recommendation・falsification に直接適用。

### Established Patterns
- **事前登録パターン**（Phase 10 D-12 / 11 D-03）— 候補集合を Plan に書き・train/calib 窓内のみで選び・test 窓で選び直さない（§11.2 聖域）。q_level=0.90・SC#4 閾値・再校正方法に適用。
- **§15.2 事前登録指標不変・拡張指標は併載** — calibration_max_dev/Brier/LogLoss/sum(p) は一切不変・拡張指標は上書きでなく併載（後知恵すり替え禁止）。
- **byte-reproducible** — FIXED_REPRODUCE_TS + 固定 thread/seed・`np.array_equal` / `DataFrame.equals`。q_shrink 計算・falsification 回帰も再現性保証。
- **fail-loud（silent fallback 禁止）** — Phase 10 gap-closure CR-01〜04 鏡像。p_lower 計算不能・falsification 回帰失敗は RuntimeError。
- **adversarial 5段階鋳型**（Phase 8 D-06 / tests/audit/）— p_lower の SAFE-01 proxy 排除 AST・falsification の test 窓 outcome 使用検出（leakage）・market_signal allowlist。
- **SAFE-01（odds/ninki proxy は `p` モデルに入れない・診断層のみ）** — p_lower/falsification/EV 層で odds を使うが FEATURE_COLUMNS には混入させない（market_signal allowlist マーカー）。
- **honest 記録**（Phase 11 SC#2 FAIL）— gate 緩和しない・§11.2 聖域・switch_recommendation は正直に switch/hold/reject。
- **層分離**（domain-analysis §5）— `p` モデル odds-free / 診断・EV・evaluation 層で odds 使用。core value 再定式化の機構。
- **model_version-scoped idempotent swap**（predict.py prediction_load）— p_lower 列追加後も v1.0 binary / race-relative 行保持。

### Integration Points
- `orchestrator.train_and_predict` の race-relative 補正後（L754）に p_lower 生成（`r=max(0,p_final-y)` の q_shrink 計算・calib slice）を挿入・pred_df に `p_fukusho_hit_lower` 付与。
- `ev_rank` / `purchase_simulator` の EV 計算を `p × odds` → `p_lower × odds_lower` へ（入力列差し替え・構造変更不要）。
- `evaluator.check_acceptance_gate` に Phase 12 専用 WARN gate（selected-only/odds-band conditional calib）追加・§15.2 gate は不変。
- `segment_eval.evaluate_all_segments` に EV-decile / disagreement ROI binning 追加（既存 binning 契約再利用）。
- `predict.py` / `schema.py` に `p_fukusho_hit_lower` 列 DDL migration（idempotent ADD COLUMN IF NOT EXISTS・PREDICTION_COLUMNS 拡張・3ファイル連鎖 Pitfall 4 列数一致 assert）。
- `reports/12-*` に switch_recommendation（switch/hold/reject）・falsification 鑑別結果（model_p residual）・SC#4 WARN gate・§15.2 不変指標併載・q_level/q_shrink 実数値。
- `run_phase12_evaluation.py` — q_shrink 計算（calib slice）・falsification 回帰（race_id clustered SE）・switch_recommendation 統合・SC#2/SC#4 gate・set_primary_model Call 0件（D-10）。

</code_context>

<specifics>
## Specific Ideas

- **D-01 修正文（ユーザー指摘・統計的厳密さ）**: split conformal は個体ごとの真の確率に対する下限保証を直接与えない（outcome coverage / prediction set 的保証）。p_lower は「calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule」。coverage 表現は「p 信頼区間保証」でなく calib/test 実測 coverage + selected-only calibration 報告。**この統計的厳密さの教訓は falsification 含む Phase 12 全体の統計的主張に適用**（過度な保証を主張しない）。
- **q_level / q_shrink 表記（ユーザー指摘・誤読防止）**: `q_alpha=0.90` は「0.90 を引く」と逆に解釈される危険。`q_level`（分位レベル）と `q_shrink`（実際の分位値・実数）を明確に分離。`p_lower = max(0, p_final - q_shrink)`。report に両方出す。
- **core value 再定式化（PROJECT.md）**: 「`p` とオッズの独立性」は数学的に強すぎる（優秀なモデルほど負相関）→ 真の要件は「オッズ帯別条件付き calibration（過大でないこと）」。**selected-only / odds-band conditional calibration が WARN gate の核心**（報告のみでなく gate 化・D-06）。
- **Phase 11 honest FAIL の解釈**: race-relative model（θ=1.0）は D-04 非劣化 PASS（Brier/LogLoss/AUC 全改善）だが D-05 条件1 overprediction penalty が NaN FAIL（odds-free 1-A snapshot に odds/ninki がない）。**Phase 12 は「診断層で odds を結合」してこの NaN を解く**（11-05-SUMMARY「overprediction penalty を活かすには odds 結合経路が必要」の実行）。
- **「Phase 12 は本番切替フェーズでなく鑑別フェーズ」**: is_primary 自動切替しない（D-08）。switch_recommendation は判断材料で実行でない（D-09/D-10）。人間承認の別アクション。
- **selected-only calibration は core value 再定式化そのもの**: 報告のみでなく WARN gate（D-06）。BLOCK でない（Phase 12 は切替判断材料フェーズ・WARN が適切）。
- **market_implied 再校正の理由**: falsification の目的は「市場を条件にしても model_p が残るか」。1/odds そのままだと控除率・FLB・複勝プール歪みが混ざり「model が市場 BIAS を補正しているだけ」か「本当に能力 residual があるか」の見分けが曖昧。再校正市場確率を主軸（D-04）。

</specifics>

<deferred>
## Deferred Ideas

- **`is_primary=true` 切替の実行** — switch_recommendation で switch が出ても DB 自動変更しない・人間承認の別アクション（D-10・Phase 12 では set_primary_model Call 0件）
- **bootstrap / ensemble p_lower** — D-01 calibration-residual shrinkage を主軸・bootstrap/ensemble は RESEARCH.md 比較表・fallback（時系列 exchangeability 数値的阻害時）として事前登録
- **listwise/Plackett-Luce による根本的 race-conditional 学習** — Phase 11 D-01 と同じ・将来 refinement（本 Phase は binary 不変 + 補正層 + p_lower の組み合わせ）
- **UI の p_lower 表示改修** — Phase 7 UI・is_primary 切替後に UI 参照が変わるが UI 改修自体は別検討
- **Phase 1-B（オッズ特徴量）** — 別マイルストーン・当日情報モデル（要件§13 PIT 再設計を要する）
- **Dr. Z 型 win-pool→複勝裁定** — 市場プール構造を使う価格裁定・診断用には有用だが本マイルストーン外（domain-analysis §2・Out of Scope）

*None folded from todos — discussion stayed within phase scope（todo.match-phase 0 件）*

</deferred>

---

*Phase: 12-p_lower EV & Falsification Evaluation*
*Context gathered: 2026-06-27*
</content>
</invoke>