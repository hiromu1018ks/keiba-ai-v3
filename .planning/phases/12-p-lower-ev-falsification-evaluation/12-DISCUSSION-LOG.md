# Phase 12: p_lower EV & Falsification Evaluation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 12-p_lower EV & Falsification Evaluation
**Areas discussed:** p_lower 手法選択, falsification 統計仕様, 条件付き calib gate と is_primary 切替, 拡張指標の扱い

---

## 順位1: p_lower 手法選択（SC#1・EV-01）

| Option | Description | Selected |
|--------|-------------|----------|
| conformal（推奨） | 分布自由な coverage 保証。calib slice で nonconformity score 計算。過信削減に最整合。時系列 exchangeability は rolling/weighted で対処。 | |
| bootstrap | base model N 回再学習（または jackknife+/residual）。base logit 再利用・FIXED seed で再現。計算コスト高。 | |
| ensemble (LGB+CB) | 既存2モデルの予測ばらつきから下限。計算コスト最低。ただし2点のばらつきは粗い。 | |
| お任せ（Claude 裁量・事前登録） | Claude が総合し Plan 内で事前登録。 | ✓（初回） |

**User's choice:** お任せ（初回）→ **統計的厳密さの訂正を指示** → D-01/D-02 修正確定

**Notes（ユーザー訂正・重要）:**
- 「真の p ≥ p_lower が 90% で成立」という表現は危険。split conformal は個体ごとの真の確率に対する下限保証を直接与えない（outcome coverage / prediction set 的保証）。
- **修正文採用**: 手法 = calibration-residual based lower bound（split conformal 風）。later-disjoint calib slice で過大誤差 `p_final - y` の残差を推定し `p_lower = max(0, p_final - q_shrink)`。個体の真の確率への厳密な信頼下限でなく、calib 上の過大予測を保守的に差し引く分布自由 shrinkage rule。coverage は「p 信頼区間保証」でなく calib/test 実測 coverage + selected-only calibration 報告。
- この統計的厳密さの教訓は falsification 含む Phase 12 全体に適用（過度な保証を主張しない）。

---

## 順位2: falsification 統計仕様（SC#3・EVAL-02）

### Q1: market_implied の定義

| Option | Description | Selected |
|--------|-------------|----------|
| 再校正（推奨） | train/calib で 1/odds を outcome に calibration し overround・FLB 除去。model_p 係数が純粋 residual を測り鑑別に直接的。 | ✓ |
| 1/odds そのまま | 生の市場暗示確率（控除・FLB 含む）。market 側 BIAS が model_p 解釈に混入。 | |
| 両方併記（honest） | 1/odds と再校正の両方で model_p を算出し比較。多重比較補正必要。 | |
| お任せ | Claude が鑑別目的・core value・統計妥当性を総合し事前登録。 | |

**User's choice:** 再校正

**Notes:** falsification の目的は「市場を条件にしても model_p が残るか」。1/odds そのままだと控除率・FLB・複勝プール歪みが混ざり、model が市場 BIAS を補正しているだけなのか本当に能力 residual があるのか分かりにくい。再校正市場確率を主にするのが正しい。

### Q2: 有意判定の厳格さ

| Option | Description | Selected |
|--------|-------------|----------|
| 保守的・Holm 補正（推奨） | 基本単一係数 α=0.05 + bin/odds_band 別サブ解析で Holm 補正。偽陽性回避。 | |
| 標準 α=0.05 | model_p 単一係数の race_id clustered SE で p値<0.05。bin 別サブ解析のみ Holm。 | ✓ |
| お任せ | Claude が保守的を主軸に事前登録。 | |

**User's choice:** 標準 α=0.05

**Notes:** シンプル・解釈やすい。bin 別サブ解析でのみ Holm 補正。

---

## 順位3: 条件付き calib gate と is_primary 切替（SC#4 + Phase 11 D-07 委譲）

| Option | Description | Selected |
|--------|-------------|----------|
| 条件 gate PASS で切替（推奨） | SC#4 gate + p_lower EV 回収率が v1.0 binary 上回る・を条件に PASS なら切替。 | |
| v1.0 binary 維持・評価のみ | Phase 12 は評価・診断が主目的。本番切替は別判断。 | |
| 結果次第・事後判断 | 事前登録 gate は定義するが切替可否は人間が判断。構造的限界なら見送り。 | ✓ |
| お任せ | Claude が core value・成功基準を総合し事前登録。 | |

**User's choice:** 結果次第・事後判断

**Notes（ユーザー指示・構造化要求）:**
- is_primary は評価結果を見ずに自動切替にしない。Phase 12 は「本番切替フェーズ」でなく p_lower EV と falsification で使う価値を鑑別するフェーズ。
- 事後判断を野放しにしないため Plan に明記: SC#4 条件付き calibration gate / p_lower EV の v1.0 比較 / falsification の model_p residual / これらを統合した **switch_recommendation: switch/hold/reject を report に出す** / 実際の is_primary 切替は**人間承認の別アクション**。
- Phase 12 は切替判断材料を出すまで。DB の is_primary=true 変更は自動でやらない、が安全。

---

## 順位4: 拡張指標の扱い（EVAL-01）

| Option | Description | Selected |
|--------|-------------|----------|
| switch_rec 入力・報告のみ（推奨） | 拡張指標は switch_recommendation 入力として report 併載。§15.2 gate 不変。 | |
| selected-only を WARN gate 化 | selected-only calib を §15.2 とは別の WARN gate に追加。残りは報告のみ。 | ✓ |
| 全て WARN gate 化 | 拡張指標の異常を全て WARN gate に。厳格だが複雑化。 | |
| お任せ | Claude が switch_recommendation 機構と整合する形で事前登録。 | |

**User's choice:** selected-only を WARN gate 化

**Notes（ユーザー指示）:**
- selected-only calibration は今回の core value 再定式化そのものなので、単なる報告だけでは弱い。
- §15.2 の既存 BLOCK/WARN gate は不変にするべきなので、別枠の Phase 12 WARN gate にする。
- 扱い: 既存 §15.2 gate は変更しない / selected-only calibration / odds-band conditional calibration は Phase 12 専用 WARN gate / EV-decile ROI / disagreement ROI / slippage は switch_recommendation 入力 + 報告のみ / BLOCK にはしない（Phase 12 は切替判断材料を出すフェーズなので WARN が正しい）。

---

## 追加: q_level / q_shrink 表記の明文化

**ユーザー指摘（D-02 最終化）:** p_lower の q_alpha=0.90 の意味が逆に解釈される危険。`p_lower = max(0, p_final - q_alpha)` の q_alpha は「過大誤差の90%分位」のような値だが、表で q_alpha=0.90 と書くと「数値 0.90 を引く」とも読める。
- **決定**: shrinkage quantile は `q_level=0.90` と表記し `q_alpha` という変数名は避ける。実際に差し引く値は calib slice の overprediction residual `r = max(0, p_final - y)` の q_level 分位 `q_shrink`。`p_lower = max(0, p_final - q_shrink)`。q_level=0.90 は分位レベルであって 0.90 を直接引く意味ではない。report には q_level と q_shrink 実数値を両方出す。

---

## Claude's Discretion

- SC#4 gate の具体的閾値（投票層過大予測の許容幅・odds_band 区分）— planner 事前登録パターン
- 再校正方法（isotonic / Platt）— RESEARCH.md で calib sample size 比較
- odds clipping 範囲・field size 共変量 — planner 事前登録
- p_lower の bin/race 条件付き残差（全体 shrinkage vs 条件付き）— RESEARCH.md 比較
- snapshot→final slippage の具体的測定方法 — planner
- bootstrap / ensemble p_lower — RESEARCH.md 比較表・fallback として事前登録
- statsmodels 依存追加（clustered SE・logit 回帰）— planner
- prediction.fukusho_prediction への p_lower 列追加 DDL migration — planner
- falsification / switch_recommendation の report 構造 — planner
- run_phase12_evaluation.py のひな形（run_phase11_evaluation.py 踏襲）— planner

## Deferred Ideas

- is_primary=true 切替の実行 — switch_recommendation で switch でも DB 自動変更しない・人間承認の別アクション
- bootstrap / ensemble p_lower — D-01 主軸でない・fallback/cross-check
- listwise/Plackett-Luce による根本的 race-conditional 学習 — 将来 refinement
- UI の p_lower 表示改修 — Phase 7・別検討
- Phase 1-B（オッズ特徴量）— 別マイルストーン
- Dr. Z 型 win-pool→複勝裁定 — 診断用だが本マイルストーン外
