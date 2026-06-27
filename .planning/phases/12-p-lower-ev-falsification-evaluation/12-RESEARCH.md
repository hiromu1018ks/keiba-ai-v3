# Phase 12: p_lower EV & Falsification Evaluation - Research

**Researched:** 2026-06-27
**Domain:** 統計的評価（conformal 風下側信頼限界 / ロジット回帰 falsification / オッズ帯別条件付き calibration gate / byte-reproducible migration）
**Confidence:** HIGH（統計 API と踏襲アセットの現状シグネチャは実証済み・JRA ドメイン閾値の一部は planner の事前登録対象）

## Summary

Phase 12 は v1.1 マイルストーンの最終フェーズで、Phase 11 の race-relative model `p_fukusho_hit`（θ=1.0・`is_primary=f` 永続化済み・snapshot `20260626-1a-opponentstrength-v1-lgbrr-v1`・22793行）を前提に、(1) EV 判定を点推定 `p` から `p_lower × odds_lower`（下側信頼限界）へ移行し、(2) 評価指標を拡張（selected-only / EV-decile / disagreement ROI / snapshot-final slippage）、(3) falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` で odds-free market residual を統計検証し、(4) オッズ帯別条件付き calibration を WARN gate 化して投票層の過大予測を構造的に検出する、統計的に厳密な評価フェーズ。`is_primary=true` 切替は人間承認の別アクション（D-10・Phase 12 は判断材料提示のみ）。

設計思想（層分離・falsification・core value 再定式化）は domain-analysis §0/§1/§5/§6 で確立済みで重複研究を避ける。本 Phase は**実装手法・API・統計的厳密さ・事前登録すべき具体値**に集中する。CONTEXT.md D-01 修正文「split conformal は個体の真の確率に対する厳密な下限保証でなく、calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule」は**理論的に正しい**（JMLR 2024 v25/23-1553 "Split Conformal Prediction and Non-Exchangeable Data" が exchangeability 必須を確認・時系列で壊れる）。この統計的厳密さの教訓を Phase 12 全体の統計的主張（coverage 表現・falsification 有意性主張・gate 判定）に適用する。

**Primary recommendation:** (a) `p_lower = max(0, p_final - q_shrink)` で `q_shrink = np.quantile(calib_residuals, 0.90)`・`r = max(0, p_final - y)`（calib slice のみ・test 窓聖域）、(b) falsification は statsmodels `Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id})` で race_id clustered SE、(c) market_implied 再校正は calib sample size ≥ 1000 で isotonic / <1000 で Platt（sigmoid）・D-04 事前登録、(d) SC#4 WARN gate は segment_eval `ODDS_BAND_EDGES=[0,2.9,4.9,9.9,inf]` を踏襲し「投票層」= selected_only=True の行、(e) prediction `p_fukusho_hit_lower` 列は idempotent `ADD COLUMN IF NOT EXISTS` で 3 ファイル連鎖（schema/predict/prediction_load・Pitfall 4 列数一致 assert）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**p_lower 手法（SC#1・EV-01）**
- **D-01:** 手法 = calibration-residual based lower bound（split conformal 風）。later-disjoint calib slice で overprediction residual `r = max(0, p_final - y)` を計算し q_level 分位を保守的に差し引く。race_relative.py の base logit `s_i` 由来の `p_final`（race-relative 補正後）に適用。個体ごとの真の確率の下限保証でなく、calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule（統計的厳密さ）。
- **D-02:** shrinkage quantile 表記。`q_level=0.90`（`q_alpha` 変数名は避ける）。`q_shrink` = calib slice の `r` の q_level 分位（実数値）。`p_lower = max(0, p_final - q_shrink)`。report に `q_level` と `q_shrink` 実数値を両方出す。`q_level=0.90` は shrinkage 強度の事前登録値・test 窓で変更不可（§11.2 聖域）。coverage 表現は「p 信頼区間保証」でなく calib/test 上の実測 coverage + selected-only calibration を報告（過度な保証主張しない）。
- **D-03:** 適用対象 = race-relative 補正後の `p_final`（orchestrator の race-relative 補正後に p_lower 生成を挿入）。`odds_lower` = 既存 `fuku_odds_lower`（JODDS snapshot・`odds_snapshot.py` 再利用）。`EV = p_lower × odds_lower`。purchase_simulator/ev_rank は `p × odds` → `p_lower × odds_lower` へ（構造変更不要・入力列差し替え）。

**falsification 統計仕様（SC#3・EVAL-02）**
- **D-04:** `market_implied` = 再校正。train/calib 窓で `1/odds` を outcome に calibration（isotonic/Platt）し overround・FLB・複勝プール歪みを除去。model_p 係数が「市場にない純粋な residual」を測る。falsification は train/calib で設計し test 窓の予測のみで評価（§11.2 聖域）。market 情報は診断層のみ・`p` モデルには入れない（EVAL-02/SAFE-01）。
- **D-05:** 有意判定 = 標準 α=0.05。model_p 単一係数の race_id clustered 標準誤差（race 内 outcome 非独立のため）で p 値 < 0.05 で「市場 residual が残る」。bin/odds_band 別サブ解析でのみ Holm 補正（多重比較）。統計仕様を事前登録: (a) market_implied 定義=D-04 再校正、(b) race_id clustered SE=D-05、(c) field size 共変量・odds clipping（極端オッズの丸め）の統制は planner が calib sample size で事前登録。鑑別結果（model_p 有意=特徴量不足 / 非有意=構造的限界）を reports/ に honest 記録。

**拡張指標の扱い（SC#2・EVAL-01）**
- **D-06:** §15.2 既存 BLOCK/WARN gate は不変（calibration_max_dev/Brier/LogLoss/sum(p) 分布・後知恵すり替え禁止・聖域）。selected-only calibration / odds-band conditional calibration = Phase 12 専用 WARN gate（core value 再定式化の直接的測定・報告のみでなく gate 化）。BLOCK にはしない（Phase 12 は切替判断材料フェーズ・WARN が適切・v1.0 の「p=0.16→実0.04 の4倍過大」を catch する gate）。
- **D-07:** EV-decile ROI / model-market disagreement ROI / snapshot→final payout slippage = `switch_recommendation`（D-09）入力 + 報告のみ（gate 化しない・§15.2 gate とは別枠の診断指標）。現実回収率 0.78-0.92 を正直に測る。

**is_primary 切替（Phase 11 D-07 委譲）**
- **D-08:** is_primary 切替 = 結果次第・事後判断（評価結果を見ずに自動切替しない）。Phase 12 は「本番切替フェーズ」でなく p_lower EV と falsification で使う価値を鑑別するフェーズ。
- **D-09:** `switch_recommendation` 機構。SC#4 オッズ帯別条件付き calibration gate・p_lower EV の v1.0 binary 比較（回収率）・falsification の model_p residual を統合し report に `switch / hold / reject` を出す。
- **D-10:** 実際の `is_primary=true` 切替は人間承認の別アクション。Phase 12 では DB の is_primary 変更を自動で行わない（`set_primary_model` Call 0件・AST check・Phase 11 D-07 踏襲）。

### Claude's Discretion（RESEARCH.md で比較検討・planner が事前登録パターンで固定）

- SC#4 gate の具体的閾値 — 投票層過大予測の許容幅・odds_band 区分（ODDS_BAND_EDGES [0,2.9,4.9,9.9,inf] 踏襲しつつ投票層の定義）
- 再校正方法（isotonic / Platt）— calib sample size で RESEARCH.md が比較検討
- odds clipping 範囲・field size 共変量 — planner が事前登録
- p_lower の bin/race 条件付き残差 — 全体 shrinkage（D-01）を主軸・race_id/odds_band 条件付き残差を RESEARCH.md で比較検討
- snapshot→final slippage の具体的測定 — refund_accounting の HARAI PayFukusyoPay（final payout）と odds_snapshot の fuku_odds_lower の差分
- bootstrap / ensemble p_lower — D-01 conformal 風 shrinkage を主軸・bootstrap/ensemble は RESEARCH.md で比較表作成・fallback として事前登録
- statsmodels 依存追加 — clustered SE・logit 回帰に必要・現状 pyproject.toml に無し
- prediction.fukusho_prediction への p_lower 列追加 — PREDICTION_ADD_P_LOWER_SQL・PREDICTION_COLUMNS 拡張・3ファイル連鎖
- falsification / switch_recommendation の report 構造 — reports/12-* の構成
- run_phase12_evaluation.py のひな形 — run_phase11_evaluation.py の構造を踏襲

### Deferred Ideas (OUT OF SCOPE)

- **`is_primary=true` 切替の実行** — switch_recommendation で switch が出ても DB 自動変更しない・人間承認の別アクション（D-10・Phase 12 では set_primary_model Call 0件）
- **bootstrap / ensemble p_lower** — D-01 calibration-residual shrinkage を主軸・bootstrap/ensemble は RESEARCH.md 比較表・fallback として事前登録（exchangeability 数値的阻害時）
- **listwise/Plackett-Luce による根本的 race-conditional 学習** — Phase 11 D-01 と同じ・将来 refinement
- **UI の p_lower 表示改修** — Phase 7 UI・is_primary 切替後に UI 参照が変わるが UI 改修自体は別検討
- **Phase 1-B（オッズ特徴量）** — 別マイルストーン・当日情報モデル
- **Dr. Z 型 win-pool→複勝裁定** — 市場プール構造を使う価格裁定・本マイルストーン外
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EV-01 | EV 判定を点推定 `p` から `p_lower`（下側信頼限界・bootstrap/ensemble/conformal）へ移行する — 点推定 `p` の過信を削り投票層の過大p を減らす（過学習聖域厳守・train/calib で設計） | p_lower 手法（D-01 conformal 風 shrinkage）・orchestrator 挿入ポイント・prediction 列 migration・purchase_simulator/ev_rank 入力列差し替え（Pattern 1/2/3・Pitfall 4 3ファイル連鎖） |
| EVAL-01 | 評価指標を拡張する — selected-only calibration / EV-decile 別実現 ROI / model-market disagreement 別 ROI / odds snapshot→final payout slippage を追加（全体 Brier が隠す投票層の失敗を可視化・§15.2 事前登録指標は不変） | segment_eval binning 契約再利用（Pattern 4）・refund_accounting HARAI PayFukusyoPay（slippage 計算の対）・D-06 selected-only/odds-band WARN gate・D-07 gate 化しない診断指標 |
| EVAL-02 | falsification test を導入する — `logit(outcome) ~ logit(market_implied) + logit(model_p)` を時系列 out-of-sample で測り、odds-free market residual が統計的に残るかを検証。回収率0.65が特徴量不足か構造的限界かを鑑別（market 情報は診断層のみ・`p` モデルには入れない） | statsmodels clustered SE API（Pattern 5）・market_implied 再校正（Pattern 6・isotonic vs Platt 1000 sample rule）・multipletests Holm・logit clipping・SAFE-01-ALLOW マーカー（falsification 層は evaluation 専用・FEATURE_COLUMNS から分離） |
| SAFE-01 | core value を維持する — オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない（市場回帰で edge 消滅）。オッズ帯別条件付き calibration を受入基準に追加し、投票層での過大予測を構造的に検出する | 層分離（domain-analysis §5・p モデル odds-free / 診断・EV・evaluation 層で odds 使用）・tests/audit/ adversarial 5段階鋳型拡張（SAFE-01 proxy 排除 AST + falsification leakage テスト）・SC#4 WARN gate |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md は本 Phase に直接的に適用される以下の聖域を定義する（CONTEXT.md 確定判断と同一・planner はこれらに違反する推奨をしてはならない）:

- **応答言語（日本語・最優先）**: RESEARCH.md の本文・見出し・比較表は日本語。技術用語・コード識別子は原文。
- **Tech stack 固定（§17.1）**: Python 3.12（uv 管理）/ LightGBM 4.6・CatBoost 1.2.10・scikit-learn 1.9 / PostgreSQL（主DB）/ DuckDB（補助）/ Parquet / Streamlit / Git。statsmodels は Supporting 追加（pyproject.toml に現状未追加・Phase 12 で追加）。
- **Leakage-prevention configuration（core value 聖域）**:
  - `merge_asof(direction='backward')` で PIT correct feature join（§13）。
  - `CalibratedClassifierCV(cv='prefit')` が時系列 mandatory（KFold shuffle しない・§15.2/§15.3）。
  - `mlxtend.evaluate.GroupTimeSeriesSplit` で race_id group integrity（§8.4・sklearn `TimeSeriesSplit` は group 非対応 issue #19072）。
  - LightGBM native categorical（Fisher optimal partition・target encoding 禁止 §14.3）+ `__MISSING__`/`__UNSEEN__` sentinel。
  - CatBoost `cat_features` + `has_time=True`（ordered TS・random permutation 禁止 §14.4）。
  - **target/mean encoding（OOF 含む）禁止 §14.3**・one-hot 高基数 ID 禁止・`pg_duckdb`/`pg_parquet` 禁止・Python 3.13 禁止・psycopg2 禁止・Feast/Hopsworks/MLflow/Optuna は Phase 1 外。
- **byte-reproducible（§19.1）**: FIXED_REPRODUCE_TS + 固定 thread/seed・`np.array_equal` / `DataFrame.equals`・q_shrink 計算・falsification 回帰も再現性保証。
- **§15.2 事前登録指標不変（後知恵すり替え禁止）**: calibration_max_dev/Brier/LogLoss/sum(p) は一切不変・拡張指標は併載（上書きでない）。
- **§11.2 test 窓は最終評価のみ**: q_shrink 計算（calib slice のみ）・falsification 回帰設計（train/calib のみ）・market_implied 再校正 fit（train/calib のみ）すべて test 窓を使用しない。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `p_lower` 計算（conformal 風 shrinkage） | API/Backend (`src/model/race_relative.py` 拡張 or 新純粋関数) | — | base logit `s_i` 由源の `p_final` を消費・calib slice のみで `r=max(0,p_final-y)` の q_level 分位を計算。orchestrator L754 後に挿入。純粋関数・DB 不要・race_relative.py の `apply_race_relative_correction` と同一 tier。 |
| `p_fukusho_hit_lower` 列永続化 | Database (`src/db/schema.py` ALTER + `predict.py` PREDICTION_COLUMNS + `prediction_load.py`) | — | prediction.fukusho_prediction テーブルのスキーマ拡張・owner/admin 権限の ALTER TABLE・idempotent migration（memory: migration-privilege-admin-required）。 |
| EV = `p_lower × odds_lower` 計算 | API/Backend (`src/ev/ev_rank.py`) | — | 純粋関数・入力列 `p_fukusho_hit` → `p_fukusho_hit_lower` に差し替え。構造変更不要。 |
| 仮想購入（p_lower ベース） | API/Backend (`src/ev/purchase_simulator.py`) | — | 純粋関数・`select_bets` の EV_lower フィルタが p_lower ベースに。閾値 `p_min=0.15` は p_lower ベースで再解釈要（planner 事前登録）。 |
| market_implied 再校正 fit | API/Backend (`run_phase12_evaluation.py` 内の純粋関数) | — | train/calib 窓で `1/odds` → outcome に `CalibratedClassifierCV(cv='prefit', method=isotonic/sigmoid)`・test 窓聖域。falsification 層（evaluation 専用・FEATURE_COLUMNS に混入させない・SAFE-01-ALLOW マーカー）。 |
| falsification ロジット回帰 | API/Backend (`run_phase12_evaluation.py` + `statsmodels.Logit`) | — | test 窓の予測のみで評価・race_id clustered SE・train/calib で設計。reports/12-* に honest 記録。 |
| SC#4 オッズ帯別条件付き calibration WARN gate | API/Backend (`src/model/evaluator.py::check_acceptance_gate` 拡張) | — | `warn_reasons` に Phase 12 専用 WARN gate を追加・§15.2 gate は不変（D-06）。segment_eval `ODDS_BAND_EDGES` を再利用。 |
| 拡張評価指標（EV-decile/disagreement/slippage ROI） | API/Backend (`src/model/segment_eval.py` binning 再利用 + `src/ev/metrics.py` group-by) | — | gate 化しない・switch_recommendation 入力 + 報告のみ（D-07）。既存 binning 契約の bit-identical 再利用。 |
| switch_recommendation 統合 | API/Backend (`run_phase12_evaluation.py`) | — | SC#4 gate・p_lower EV v1.0 binary 比較・falsification model_p residual を統合・`switch/hold/reject` を report に。is_primary DB 変更はしない（D-10）。 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.9.0 | market_implied 再校正（`CalibratedClassifierCV(cv='prefit', method='isotonic'/'sigmoid')`）・既存 calibration 層 | 既存依存・`cv='prefit'` が時系列 mandatory・`method` 選択は calib sample size 1000 で閾値 [VERIFIED: scikit-learn.org/stable/modules/calibration.html (1.9.0)] |
| statsmodels | 0.14.6 | falsification ロジット回帰 `Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id})`・`multipletests(method='holm')` | **新規追加**・clustered SE・多重比較補正の標準ライブラリ・NeurIPS/ICML で標準引用 [VERIFIED: pypi.org statsmodels 0.14.6 / requires numpy<3,>=1.22.3・scipy!=1.9.2,>=1.8・pandas>=1.4（本プロジェクトと互換）] |
| numpy | (transitive ≥2.0) | `np.quantile(r, 0.90)` で q_shrink 計算・`np.maximum(0, p_final - y)` で overprediction residual | 既存依存・`np.quantile` は default linear interpolation で seed 非依存・決定論的（実証検証済み） |
| pandas | 3.0.3 | `pd.qcut(EV_lower, 10)` で EV-decile binning・group-by ROI 計算 | 既存依存・segment_eval binning 契約と同一 tier |
| scipy | >=1.17.1 | 既存（brentq・stats）・falsification の補助 | 既存依存 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| statsmodels.stats.multitest.multipletests | 0.14.6 | Holm 補正（bin/odds_band サブ解析の多重比較） | falsification の bin/odds_band サブ解析のみ（model_p 単一係数の主検定は Holm 不要・D-05） |
| statsmodels.api.Logit / LogitResults | 0.14.6 | ロジット回帰・clustered SE・pvalue | falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| split conformal 風 shrinkage（D-01） | bootstrap p_lower（ensemble 予測の分散から下限） | bootstrap は exchangeability 非依存だが計算コスト高（model 再学習 N 回）・D-01 を主軸・fallback として事前登録（Claude's Discretion） |
| split conformal 風 shrinkage | Conformalized Quantile Regression (Romano 2019) | CQR は quantile regressor が必要・本プロジェクトは binary LightGBM/CatBoost で CQR 不適合・D-01 overprediction residual が同等の保守的 shrinkage を提供 |
| isotonic market_implied 再校正 | Platt (sigmoid) | calib sample size < 1000 で sigmoid（過学習回避）・≥ 1000 で isotonic [VERIFIED: sklearn docs]・planner が calib size で事前登録 |
| race_id clustered SE（D-05） | HC3 robust SE（非 cluster） | race 内 outcome は独立でない（同レースの馬は共通ショック）・clustered が正しい・HC3 は過小推定 |
| Holm 補正（bin/odds_band サブ解析） | Benjamini-Hochberg (FDR) | Holm は FWER 制御・D-05 事前登録・BH は FDR 制御で緩い・falsification の鑑別目的では FWER が適切 |

**Installation:**
```bash
# statsmodels を dependencies に追加（scipy/pandas/numpy は既存）
uv add "statsmodels>=0.14.6"
uv sync --frozen  # uv.lock に反映
```

**Version verification:**
```bash
# PyPI で statsmodels の現行版と依存制約を確認済み（2026-06-27）
pip index versions statsmodels  # 0.14.6 が最新・0.14.6/0.14.5/.../0.14.0
# requires: numpy<3,>=1.22.3 / scipy!=1.9.2,>=1.8 / pandas!=2.1.0,>=1.4
# 本プロジェクト numpy>=2.0 / scipy>=1.17.1 / pandas==3.0.3 と互換
```

## Package Legitimacy Audit

> Package Legitimacy Gate を実行済み。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| statsmodels | PyPI | 初版 2010（0.4.0）・0.14.6 は 2025-12-05 リリース | PyPI は download 数を公開しない（`unknown-downloads` で SUS 判定・**false-positive**） | https://www.statsmodels.org/ （GitHub: statsmodels/statsmodels・広く保守） | SUS（false-positive） | Approved — planner は `checkpoint:human-verify` を追加するが、statsmodels は統計分析の標準ライブラリ・NeurIPS/ICML で標準引用・実体は OK |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** statsmodels（`unknown-downloads` のみ・PyPI が download 数を公開しないため超著名パッケージでもこの判定になる・false-positive。repo URL・非 deprecated・成熟リリース歴で OK 判定を裏付け）

*scikit-learn / numpy / pandas / scipy は既存依存で legitimacy 確立済み・本 audit では再検証しない。*

## Architecture Patterns

### System Architecture Diagram

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │  Phase 11 既存: p_fukusho_hit (race-relative θ=1.0 補正後)   │
                  │  snapshot: 20260626-1a-opponentstrength-v1-lgbrr-v1 (22793行)│
                  └─────────────────────────────┬───────────────────────────────┘
                                                │
                  ┌─────────────────────────────▼───────────────────────────────┐
                  │  Phase 12 挿入: p_lower 生成 (orchestrator L754 後)          │
                  │  入力: p_final (race-relative 補正後) + y (calib slice のみ) │
                  │  計算: r = max(0, p_final - y) [overprediction residual]     │
                  │        q_shrink = np.quantile(r[calib], 0.90)  [§11.2 聖域]  │
                  │        p_lower = max(0, p_final - q_shrink)                  │
                  │  出力: p_fukusho_hit_lower 列 (prediction.fukusho_prediction)│
                  └─────────┬───────────────────────────────────┬───────────────┘
                            │                                   │
        ┌───────────────────▼──────────────┐    ┌──────────────▼──────────────────┐
        │  EV 層 (ev_rank.py・入力列差し替え) │    │  評価・診断層 (odds 結合・SAFE-01 │
        │  EV_lower = p_lower × odds_lower  │    │  聖域外・evaluation 専用)         │
        │  recommend_rank S/A/B/C/D         │    │                                   │
        └───────────────────┬──────────────┘    │  ┌─────────────────────────────┐ │
                            │                   │  │ selected-only calibration    │ │
        ┌───────────────────▼──────────────┐    │  │ (p_lower EV で選ばれた馬のみ) │ │
        │  仮想購入 (purchase_simulator.py) │    │  │ → SC#4 WARN gate (D-06)      │ │
        │  p_min=0.15 を p_lower ベースで   │    │  └─────────────────────────────┘ │
        │  select_bets → top-2/race        │    │  ┌─────────────────────────────┐ │
        └───────────────────┬──────────────┘    │  │ odds-band conditional calib │ │
                            │                   │  │ (ODDS_BAND_EDGES 踏襲・投票層)│ │
        ┌───────────────────▼──────────────┐    │  │ → SC#4 WARN gate (D-06)      │ │
        │  会計 (refund_accounting.py)       │    │  └─────────────────────────────┘ │
        │  HARAI PayFukusyoPay (final payout)│   │  ┌─────────────────────────────┐ │
        │  vs fuku_odds_lower (snapshot)    │    │  │ EV-decile / disagreement ROI │ │
        │  → snapshot→final slippage (D-07) │    │  │ snapshot→final slippage      │ │
        └───────────────────────────────────┘    │  │ → switch_recommendation 入力 │ │
                                                 │  └─────────────────────────────┘ │
                                                 │  ┌─────────────────────────────┐ │
                                                 │  │ falsification ロジット回帰   │ │
                                                 │  │ logit(outcome) ~             │ │
                                                 │  │   logit(market_implied) +    │ │
                                                 │  │   logit(model_p)             │ │
                                                 │  │ race_id clustered SE (D-05)  │ │
                                                 │  │ market_implied = 再校正(D-04)│ │
                                                 │  │ → model_p residual 鑑別       │ │
                                                 │  └──────────────┬──────────────┘ │
                                                 └─────────────────┼─────────────────┘
                                                                   │
                                          ┌────────────────────────▼────────────────────────┐
                                          │  switch_recommendation 統合 (run_phase12_eval)   │
                                          │  SC#4 gate + p_lower EV比較 + falsification      │
                                          │  → switch / hold / reject (report のみ・D-09)    │
                                          │  is_primary DB 変更しない (D-10・人間承認)        │
                                          └──────────────────────────────────────────────────┘
```

データフローの追跡: Phase 11 の `p_final` → (calib slice のみで q_shrink 計算) → `p_lower` → EV 層（入力列差し替え）→ 仮想購入 → 会計 → 評価・診断層（odds 結合・SAFE-01 聖域外）→ switch_recommendation。test 窓は q_shrink 計算・market_implied 再校正 fit・falsification 回帰設計のいずれにも使用しない（§11.2 聖域・破線で明示）。

### Recommended Project Structure
```
src/
├── model/
│   ├── race_relative.py        # 拡張: p_lower 計算関数を追加（apply_race_relative_correction 後）
│   ├── orchestrator.py         # 拡張: L754 後に p_lower 生成挿入・pred_df に p_fukusho_hit_lower 付与
│   ├── predict.py              # 拡張: PREDICTION_COLUMNS 19→20・_assert_valid_prediction_df に p_lower range check
│   ├── evaluator.py            # 拡張: check_acceptance_gate warn_reasons に Phase 12 専用 WARN gate 追加
│   └── segment_eval.py         # 再利用: ODDS_BAND_EDGES・binning 契約（EV-decile/disagreement axis 追加）
├── ev/
│   ├── ev_rank.py              # 拡張: EV_lower = p_lower × odds_lower（入力列差し替え）
│   ├── purchase_simulator.py   # 拡張: p_min=0.15 を p_lower ベースで再解釈（planner 事前登録）
│   ├── refund_accounting.py    # 再利用: HARAI PayFukusyoPay（slippage 計算の対）
│   └── report.py               # 拡張: REPORT_COLUMNS に switch_recommendation・falsification 追加表示
├── db/
│   ├── schema.py               # 拡張: PREDICTION_ADD_P_LOWER_SQL・APPLY_ORDER 追加・CHECK p_lower range
│   └── prediction_load.py      # 拡張: INSERT 列順に p_fukusho_hit_lower 追加（3ファイル連鎖 Pitfall 4）
scripts/
└── run_phase12_evaluation.py   # 新規: run_phase11_evaluation.py 構造踏襲・q_shrink・falsification・switch_rec
tests/
└── audit/
    └── test_audit_p_lower_falsification.py  # 新規: 5段階鋳型・SAFE-01 proxy 排除 AST + falsification leakage
reports/
└── 12-evaluation/              # 新規: 12-evaluation.md・falsification.md・switch-recommendation.md・q_shrink.json
```

### Pattern 1: p_lower 計算（conformal 風 shrinkage・calib slice のみ・§11.2 聖域）
**What:** race_relative 補正後の `p_final` に calib slice のみで計算した overprediction residual の q_level 分位を保守的に差し引く。
**When to use:** orchestrator L754（race-relative 補正後）に挿入。test 窓の outcome は絶対に使用しない。
**Example:**
```python
# Source: CONTEXT.md D-01/D-02 + np.quantile 挙動実証検証 + JMLR 2024 v25/23-1553
# (split conformal exchangeability・統計的厳密さ)
import numpy as np

def compute_p_lower_conformal_shrinkage(
    p_final: np.ndarray,
    y_calib: np.ndarray,
    p_final_calib: np.ndarray,
    *,
    q_level: float = 0.90,
) -> tuple[np.ndarray, float]:
    """calib slice のみで overprediction residual の q_level 分位を計算し p_lower を生成.

    統計的厳密さ (D-01 修正文・JMLR 2024):
      - split conformal は exchangeability を仮定し (1-alpha) marginal outcome coverage を保証するが・
        個体ごとの真の確率の下限保証でない。時系列パネルデータは非 exchangeable で厳密保証は壊れる。
      - よって本関数は「calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule」
        として扱い・report では実測 coverage + selected-only calibration を報告（過度な保証主張しない）。

    §11.2 聖域:
      - y_calib / p_final_calib は calib slice のみ（呼出側が保証）。
      - test 窓の outcome は引数に取らない（構造的聖域ブロック）。
      - q_level=0.90 は事前登録値・test 窓で変更不可。

    byte-reproducible:
      - np.quantile は default linear interpolation・seed 非依存・決定論的（実証検証済み）。
    """
    if not (0.0 < q_level < 1.0):
        raise ValueError(f"q_level must be in (0,1), got {q_level}")
    # overprediction residual: 予測が実現を上回る正方向誤差のみ（半波整流）
    r_calib = np.maximum(0.0, p_final_calib - y_calib)
    # q_level 分位（calib slice のみ・test 窓聖域）
    q_shrink = float(np.quantile(r_calib, q_level))
    # p_lower = max(0, p_final - q_shrink)（保守的 shrinkage）
    p_lower = np.maximum(0.0, p_final - q_shrink)
    return p_lower, q_shrink
```

### Pattern 2: prediction p_lower 列 migration（3ファイル連鎖・Pitfall 4・owner/admin 権限）
**What:** `p_fukusho_hit_lower` 列を prediction.fukusho_prediction に追加する idempotent migration。3ファイル（schema.py / predict.py / prediction_load.py）の列順序を完全一致させる。
**When to use:** Wave 0（schema 拡張）で実行・owner/admin 権限必要（memory: migration-privilege-admin-required）。
**Example:**
```python
# Source: schema.py PREDICTION_ADD_IS_PRIMARY_SQL / PREDICTION_ADD_PROVENANCE_SQL 既存 idiom
# (idempotent ADD COLUMN IF NOT EXISTS + DROP CONSTRAINT IF EXISTS + ADD)

# schema.py に追加 (PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL の直後・backtest_table の前):
PREDICTION_ADD_P_LOWER_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS p_fukusho_hit_lower double precision;
ALTER TABLE prediction.fukusho_prediction
    DROP CONSTRAINT IF EXISTS prediction_p_lower_range;
ALTER TABLE prediction.fukusho_prediction
    ADD CONSTRAINT prediction_p_lower_range
    CHECK (p_fukusho_hit_lower IS NULL OR
           (p_fukusho_hit_lower >= 0 AND p_fukusho_hit_lower <= 1));
COMMENT ON COLUMN prediction.fukusho_prediction.p_fukusho_hit_lower IS
    'Phase 12 SC#1: p_fukusho_hit の下側信頼限界 (conformal 風 shrinkage). '
    'v1.0 binary 行は NULL (後方互換). race-relative 行は p_lower を持つ. '
    'CHECK 制約 prediction_p_lower_range で [0,1] を保証 (NULL 許容で v1.0 行を保持).';
"""

# APPLY_ORDER に追加 (prediction_extend_model_type_domain の直後):
#   ("prediction_add_p_lower", PREDICTION_ADD_P_LOWER_SQL),

# predict.py PREDICTION_COLUMNS: p_fukusho_hit の直後に挿入 (20列化):
#   "p_fukusho_hit",
#   "p_fukusho_hit_lower",   # ← Phase 12 SC#1 追加
#   "race_date",

# _assert_valid_prediction_df に p_lower range check 追加:
#   p_lower = df["p_fukusho_hit_lower"]
#   if p_lower.notna().any():
#       pl_valid = p_lower.dropna()
#       if (pl_valid < 0).any() or (pl_valid > 1).any():
#           raise ValueError(...)

# prediction_load.py: INSERT 列順序に p_fukusho_hit_lower を追加 (3ファイル連鎖 Pitfall 4)
# v1.0 binary 行は p_lower=None で INSERT (後方互換・CHECK で NULL 許容)
```

### Pattern 3: EV 計算・仮想購入の入力列差し替え（構造変更不要）
**What:** ev_rank.py / purchase_simulator.py の `p_fukusho_hit` を `p_fukusho_hit_lower` に差し替え。構造変更不要・入力列差し替えのみ（D-03）。
**When to use:** ev_rank.compute_ev_and_rank / purchase_simulator.select_bets の呼出側で列を差し替え。
**Example:**
```python
# Source: ev_rank.py L107-113 / purchase_simulator.py L94-98 既存構造（変更不要）
# 呼出側 (run_phase12_evaluation.py) で列を差し替え:
#
# # 旧 (Phase 11): EV_lower = p_fukusho_hit × fuku_odds_lower
# # 新 (Phase 12): EV_lower = p_fukusho_hit_lower × fuku_odds_lower
#
# ev_rank.compute_ev_and_rank は "p_fukusho_hit" 列を期待するため・
# 呼出側で df["p_fukusho_hit"] = df["p_fukusho_hit_lower"] で alias を作るか・
# ev_rank に p_col 引数を追加して差し替え可能にする。
#
# purchase_simulator.select_bets の p_min=0.15 閾値は p_lower ベースで再解釈:
#   p_lower は p より小さいため・p_min=0.15 で選ばれる馬は p >= 0.15+q_shrink を満たす馬。
#   planner が事前登録: p_min を p_lower ベースで 0.15 にするか・p ベースで 0.15 を維持するか。
#   (Claude's Discretion「SC#4 gate の具体的閾値」と整合・事前登録パターン Phase 10 D-12 / 11 D-03)
```

### Pattern 4: segment_eval binning 契約再利用（EV-decile / disagreement ROI・bit-identical）
**What:** EV-decile ROI / model-market disagreement ROI の binning に segment_eval の binning 契約を再利用。独自 binning 禁止。
**When to use:** run_phase12_evaluation.py で EV-decile・disagreement ROI を計算する際。
**Example:**
```python
# Source: segment_eval.py _odds_band / evaluate_segment_axis binning 契約
# (bit-identical・契約一元化・codex review HIGH#2)

import pandas as pd
from src.model.segment_eval import _odds_band, ODDS_BAND_EDGES

# EV-decile: pd.qcut(EV_lower, 10) で bit-identical binning
# (segment_eval.evaluate_segment_axis の binning 契約と同一・pd.cut/pd.qcut は index 依存で
#  決定論的・np.digitize と組み合わせて決定論化)
df["ev_decile"] = pd.qcut(df["EV_lower"], 10, labels=False, duplicates="drop")

# model-market disagreement: |model_logit - market_logit| を binning
# market_logit = logit(market_implied)・model_logit = logit(p_fukusho_hit)
# (logit clipping 必須・eps=1e-6 で ±13.8 動的範囲)
eps = 1e-6
df["model_logit"] = np.log(np.clip(df["p_fukusho_hit"], eps, 1 - eps) /
                           (1 - np.clip(df["p_fukusho_hit"], eps, 1 - eps)))
df["market_logit"] = np.log(np.clip(df["market_implied"], eps, 1 - eps) /
                            (1 - np.clip(df["market_implied"], eps, 1 - eps)))
df["disagreement"] = (df["model_logit"] - df["market_logit"]).abs()
df["disagreement_band"] = pd.qcut(df["disagreement"], 5, labels=False, duplicates="drop")

# 各 bin で compute_backtest_metrics (src/ev/metrics.py) を group-by 適用
for bin_label, group in df.groupby("ev_decile"):
    metrics = compute_backtest_metrics(group)  # recovery_rate / profit_loss / hit_rate
    # → switch_recommendation 入力 + reports/12-evaluation に併載
```

### Pattern 5: falsification ロジット回帰（statsmodels clustered SE・test 窓聖域）
**What:** `logit(outcome) ~ logit(market_implied) + logit(model_p)` を statsmodels Logit で race_id clustered SE で fit し model_p 係数の有意性を検定。
**When to use:** run_phase12_evaluation.py で falsification test を実行。train/calib で market_implied 再校正を fit し・test 窓の予測のみで回帰を評価（§11.2 聖域）。
**Example:**
```python
# Source: statsmodels Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id})
# [VERIFIED: GitHub statsmodels/issues/6287 + WebSearch]
# groups= 直接渡しは error・cov_kwds={'groups': array} が正しい API
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

def run_falsification_test(
    y_outcome_test: np.ndarray,    # test 窓の outcome のみ（§11.2 聖域・train/calib で設計）
    market_implied_test: np.ndarray,  # train/calib で再校正した market calibrator を test 窓に適用
    model_p_test: np.ndarray,
    race_id_test: np.ndarray,
    field_size_test: np.ndarray | None = None,
) -> dict:
    """falsification: logit(outcome) ~ logit(market_implied) + logit(model_p).

    §11.2 聖域:
      - market_implied calibrator は train/calib 窓で fit 済み・本関数は test 窓に適用のみ。
      - 本関数は学習しない（test 窓 outcome を falsification モデルの学習に使わない）。
      - 回帰の「評価」は test 窓で行うが・「設計」(market calibrator fit) は train/calib のみ。
    D-05:
      - α=0.05 単一係数検定 (model_p)・race_id clustered SE。
      - bin/odds_band サブ解析のみ Holm 補正 (multipletests method='holm')。
    """
    eps = 1e-6  # logit clipping・inf 回避・planner 事前登録
    def logit_clip(p):
        p_c = np.clip(p, eps, 1 - eps)
        return np.log(p_c / (1 - p_c))

    y_logit = logit_clip(y_outcome_test)
    X = np.column_stack([
        logit_clip(market_implied_test),
        logit_clip(model_p_test),
    ])
    if field_size_test is not None:
        X = np.column_stack([X, field_size_test])  # 共変量統制 (D-05 (c)・planner 事前登録)
    X = sm.add_constant(X)

    # race_id clustered SE (D-05)・cov_kwds={'groups': race_id} が正しい API
    model = sm.Logit(y_outcome_test.astype(int), X)
    result = model.fit(cov_type="cluster", cov_kwds={"groups": race_id_test},
                       disp=0, maxiter=200)

    # model_p 係数は X[:, 2]（const/market/model_p 順・field_size あれば X[:, 3])
    model_p_idx = 2
    model_p_coef = float(result.params[model_p_idx])
    model_p_pvalue = float(result.pvalues[model_p_idx])

    # bin/odds_band サブ解析 (Holm 補正・D-05)
    # odds_band = _odds_band(pd.Series(market_implied_test を 1/odds に逆変換したもの))
    # 各 band で model_p pvalue を計算し multipletests(method='holm') で補正
    # (planner が事前登録: どの band をサブ解析に含めるか・Holm の alpha)

    return {
        "model_p_coef": model_p_coef,
        "model_p_pvalue": model_p_pvalue,
        "model_p_significant": model_p_pvalue < 0.05,
        "verdict": "feature_gap" if model_p_pvalue < 0.05 else "structural_limit",
        # feature_gap = model_p に有意残差（特徴量不足）
        # structural_limit = market 係数が model を包摂（core value 維持での黒字化棄却）
    }
```

### Pattern 6: market_implied 再校正（train/calib のみ・test 窓聖域）
**What:** `1/odds` を outcome に `CalibratedClassifierCV(cv='prefit', method=isotonic/sigmoid)` で calibration し overround・FLB・複勝プール歪みを除去。
**When to use:** run_phase12_evaluation.py で falsification の market_implied を構築。train/calib 窓で fit・test 窓に適用のみ。
**Example:**
```python
# Source: CLAUDE.md CalibratedClassifierCV cv='prefit' + sklearn docs isotonic vs sigmoid 1000 rule
# [VERIFIED: scikit-learn.org/stable/modules/calibration.html (1.9.0)]
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

def fit_market_implied_calibrator(
    odds_calib: np.ndarray,    # train/calib 窓の fuku_odds_lower（1/odds を base確率に）
    y_calib: np.ndarray,       # train/calib 窓の outcome（§11.2 聖域・test 窓使用しない）
    *,
    calib_sample_size: int,    # planner が事前登録（D-04/D-05 (c)）
) -> CalibratedClassifierCV:
    """train/calib 窓で 1/odds を outcome に calibration (D-04).

    method 選択 (sklearn docs):
      - calib_sample_size >= 1000 → method='isotonic' (non-parametric・柔軟・過学習リスク低)
      - calib_sample_size < 1000  → method='sigmoid' (Platt・parametric・安定)
    cv='prefit' は時系列 mandatory (KFold shuffle しない)。

    odds clipping (D-05 (c)・planner 事前登録):
      - 極端オッズの 1/odds が 1.0 に飽和（1.0 odds = 1.0 確率）・
        極低オッズの 1/odds が 0.0 に近い・inf 回避のため clip。
      - planner が事前登録: fuku_odds_lower ∈ [1.0, 100.0] 等・1/odds ∈ [0.01, 1.0]。
    """
    # odds clipping (planner 事前登録・例: [1.0, 100.0])
    odds_clipped = np.clip(odds_calib, 1.0, 100.0)
    market_base_p = 1.0 / odds_clipped  # overround 含む生の市場暗示確率

    method = "isotonic" if calib_sample_size >= 1000 else "sigmoid"
    # base estimator: market_base_p を予測する単純 estimator
    # (LogisticRegression で 1/odds → outcome を学習・これを prefit calibrator で校正)
    base = LogisticRegression(C=1e6)  # ほぼ正則化なし・1/odds をそのまま通す
    X_market = market_base_p.reshape(-1, 1)
    base.fit(X_market, y_calib.astype(int))

    calibrator = CalibratedClassifierCV(base, method=method, cv="prefit")
    calibrator.fit(X_market, y_calib.astype(int))
    return calibrator

# test 窓への適用（学習しない・§11.2 聖域）:
# market_implied_test = calibrator.predict_proba(
#     (1.0 / np.clip(odds_test, 1.0, 100.0)).reshape(-1, 1)
# )[:, 1]
```

### Anti-Patterns to Avoid
- **p 信頼区間保証の過度な主張:** split conformal は exchangeability 仮定で $(1-\alpha)$ marginal outcome coverage を保証するが・個体ごとの真の確率の下限保証でない（JMLR 2024）。時系列パネルデータは非 exchangeable で厳密保証は壊れる。report は「実測 coverage + selected-only calibration」を報告し「p は 90% 信頼下限」等の過度な保証主張をしない（D-01 修正文・CONTEXT.md specifics）。
- **target encoding / 過去オッズ proxy の `p` モデル混入:** SAFE-01 聖域違反。market_implied・odds は falsification/EV/evaluation 層のみ（SAFE-01-ALLOW マーカー）。FEATURE_COLUMNS に混入させない（tests/audit AST テストで機械保証）。
- **§15.2 事前登録指標の変更:** calibration_max_dev/Brier/LogLoss/sum(p) は一切不変（D-06）。拡張指標は上書きでなく併載（後知恵すり替え禁止）。
- **test 窓での q_shrink / market_implied calibrator fit / falsification 回帰設計:** §11.2 聖域違反。すべて train/calib 窓のみで設計し・test 窓は評価のみ。
- **`groups=` 直接渡し（statsmodels）:** error になる（GitHub #6287）。`cov_kwds={'groups': array}` が正しい API。
- **isotonic を小サンプル（<1000）に使う:** 過学習リスク（sklearn docs）。sigmoid（Platt）を使う。
- **race_id cluster を無視した通常 robust SE:** race 内 outcome は独立でない（共通ショック）・clustered SE でないと過小推定。
- **p_lower 列追加時の 3 ファイル不整合:** schema.py DDL / predict.py PREDICTION_COLUMNS / prediction_load.py INSERT の列順序が一致しないと Pitfall 4 silent 誤作動。`_assert_valid_prediction_df` の列順序チェックで機械保証。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| race_id clustered 標準誤差 | 手作り sandwich covariance | statsmodels `Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id})` | race 内相関の正確な SE・statsmodels が成熟実装・Holm 補正も `multipletests` で対応 |
| Holm 多重比較補正 | 手作り step-down p 値調整 | `statsmodels.stats.multitest.multipletests(method='holm')` | FWER 制御の標準実装・4-tuple で reject + corrected p 値を返す |
| market_implied 再校正 | 手作り isotonic 回帰 | `sklearn.calibration.CalibratedClassifierCV(cv='prefit', method='isotonic'/'sigmoid')` | sklearn が成熟・`cv='prefit'` が時系列 mandatory・既存 calibration 層と同一 API |
| overprediction residual の分位計算 | 手作り sort + index | `np.quantile(r_calib, q_level)` | default linear interpolation・seed 非依存・決定論的（実証検証済み） |
| EV-decile / odds-band binning | 手作り `np.linspace` bin edge | `segment_eval._odds_band` / `pd.qcut(..., duplicates='drop')` | bit-identical・契約一元化・codex review HIGH#2・独自 binning 禁止 |
| ロジット変換の inf 回避 | 手作り clip 閾値調整 | `np.clip(p, eps, 1-eps)` eps=1e-6（race_relative P_CAL_CLIP_EPSILON 踏襲） | race_relative.py と同一契約・logit 動的範囲 ±13.8・α_r 収束 < 1e-12 を保証 |
| snapshot→final payout slippage | 手作り payout lookup | `refund_accounting._lookup_payfukusyo_pay(row)` + `fuku_odds_lower` | HARAI PayFukusyoPay が final payout 一次・既存の slot 照合ロジックを再利用 |

**Key insight:** Phase 12 の統計的厳密さ（clustered SE・多重比較・conformal 風 shrinkage・logit 回帰）はすべて成熟ライブラリ（statsmodels/sklearn/numpy）が提供する。手作りすると統計的な正確性（sandwich covariance の自由度調整・isotonic の boundary 処理・quantile 補間）で落とし穴が出る。CLAUDE.md の「Feast/Hopsworks/MLflow は重型すぎ・keep it simple」と対照的に・statsmodels/sklearn は「標準的で軽量」なので D-01/D-04/D-05 に直接使う。

## Common Pitfalls

### Pitfall 1: split conformal の exchangeability 壊れと過度な保証主張
**What goes wrong:** 「p_lower は 90% 信頼下限」と report に書くと・時系列パネルデータでは数学的に保証されない（exchangeability 必須・JMLR 2024）。
**Why it happens:** split conformal の $(1-\alpha)$ marginal coverage 保証は calib/test の exchangeability を仮定するが・JRA の race_date 時系列パネルデータは非 exchangeable（時間的に drift・季節性・開催場シフト）。D-01 修正文「個体ごとの真の確率の下限保証でなく outcome coverage 的保証」を誤読すると過度な保証主張に至る。
**How to avoid:** report の coverage 表現は「p 信頼区間保証」でなく「calib/test 上の実測 coverage + selected-only calibration」（D-02）。q_level=0.90 は「shrinkage 強度の事前登録値」で「信頼水準」でない（変数名も `q_level` で `q_alpha` を避ける・D-02）。weighted/sequential conformal（Candes・Zaffran ACI）が時系列適応策だが本 Phase では実装せず・fallback として bootstrap/ensemble を RESEARCH.md 比較表で事前登録（Claude's Discretion）。
**Warning signs:** report に「90% confidence lower bound」「coverage guarantee」という言葉・q_level を α と同一視・calib と test の時間的 overlap。

### Pitfall 2: §11.2 test 窓聖域違反（q_shrink / market calibrator / falsification 回帰設計）
**What goes wrong:** q_shrink 計算・market_implied calibrator fit・falsification 回帰の設計に test 窓の outcome を使うと後知恵リーク。
**Why it happens:** np.quantile や CalibratedClassifierCV.fit に全データ（calib + test）を渡すと・test 窓の outcome が q_shrink や calibrator に混入。orchestrator の pred_df が train/calib/test 全 split を含むため・calib slice を正確に抽出しないと混入。
**How to avoid:** (a) q_shrink 計算関数は `y_calib` / `p_final_calib` 引数のみ（test 窓 outcome を引数に取らない・Pattern 1）。(b) market_implied calibrator は calib slice のみで fit（Pattern 6・`fit_market_implied_calibrator` は calib 引数のみ）。(c) falsification 回帰は test 窓の予測のみで評価（学習しない・Pattern 5）。(d) tests/audit/ に falsification leakage テストを追加（test 窓 outcome を fit に使うと detect）。
**Warning signs:** orchestrator pred_df をそのまま np.quantile に渡す・CalibratedClassifierCV.fit に全 split を渡す・falsification 回帰の X に test 窓 outcome を含める。

### Pitfall 3: p_lower 列追加の 3 ファイル連鎖不整合（Pitfall 4・silent 誤作動）
**What goes wrong:** schema.py の DDL / predict.py の PREDICTION_COLUMNS / prediction_load.py の INSERT 列順序が一致しないと・silent に誤った列に値が INSERT される。
**Why it happens:** PREDICTION_COLUMNS の順序と DB INSERT の順序が別々に定義されるため・1箇所変更して他を忘れると不整合。
**How to avoid:** (a) `_assert_valid_prediction_df` の列順序チェック（L361-365 既存）が常に走る。(b) p_fukusho_hit_lower を p_fukusho_hit の直後に挿入し・3ファイルすべてで同じ位置に。(c) v1.0 binary 行は p_lower=NULL で後方互換（CHECK 制約で NULL 許容）。(d) owner/admin 権限必要（memory: migration-privilege-admin-required・etl ロールで ALTER TABLE は InsufficientPrivilege）。
**Warning signs:** INSERT 後に p_fukusho_hit と p_fukusho_hit_lower の値が入れ替わる・v1.0 行の p_lower が NULL でない・ALTER TABLE が InsufficientPrivilege で失敗。

### Pitfall 4: statsmodels cov_type='cluster' の groups 渡し方
**What goes wrong:** `Logit.fit(cov_type='cluster', groups=race_id)` と groups を直接渡すと error（GitHub #6287）。
**Why it happens:** statsmodels は `groups` を `cov_kwds` dict で受け取る仕様・直接引数ではない。
**How to avoid:** `Logit.fit(cov_type='cluster', cov_kwds={'groups': race_id_array})` が正しい API（Pattern 5・[VERIFIED]）。groups array は model が NaN drop した後の行と整列している必要がある（predict.py の _assert_valid_prediction_df で NaN なしを保証済みなら OK）。
**Warning signs:** `TypeError: fit() got an unexpected keyword argument 'groups'`・clustered SE と通常 robust SE で同じ値（groups が無視された）。

### Pitfall 5: isotonic を小サンプル（<1000）に使う過学習
**What goes wrong:** calib sample size < 1000 で `method='isotonic'` を使うと・階段関数が過学習し market_implied が歪む。
**Why it happens:** isotonic regression は non-parametric で柔軟だが・データが少ないとノイズに適合する（sklearn docs: "tends to overfit"）。
**How to avoid:** calib sample size >= 1000 で isotonic・< 1000 で sigmoid（Platt）[VERIFIED: sklearn docs]。planner が calib size を事前登録（D-04/D-05 (c)）。本プロジェクトの calib slice は数千〜数万行と見込まれるため isotonic が主軸だが・odds_band サブ解析など小サンプルになるところでは sigmoid。
**Warning signs:** market_implied が階段状になる・calib slice の size を確認せず isotonic を使う。

### Pitfall 6: logit clipping 忘れ（inf 伝播）
**What goes wrong:** `logit(0) = -inf` / `logit(1) = +inf` で falsification 回帰が NaN 伝播し statsmodels が収束しない。
**Why it happens:** overround の強いレースでは 1/odds の和が 1.0 を超え・再校正前の market_base_p が 1.0 に近づく。model_p も race_relative 補正で端値になることがある。
**How to avoid:** `np.clip(p, eps, 1-eps)` eps=1e-6 で logit 動的範囲 ±13.8（race_relative.py P_CAL_CLIP_EPSILON と同一契約）。falsification の logit(outcome)/logit(market)/logit(model_p) すべてに適用（Pattern 5）。planner が eps と odds clipping 範囲を事前登録（D-05 (c)）。
**Warning signs:** statsmodels が `ConvergenceWarning`・pvalue が NaN・極端オッズの行で logit が発散。

### Pitfall 7: purchase_simulator p_min の p_lower ベース再解釈の漏れ
**What goes wrong:** p_min=0.15 閾値を p ではなく p_lower ベースで再解釈し忘れる・または逆に p ベースのままにして p_lower が小さすぎて選ばれない。
**Why it happens:** select_bets は `p_fukusho_hit >= 0.15` を見るが・Phase 12 で EV は p_lower ベースになる。p_min をどちらの確率ベースにするかが明示されないと・投票層の定義が曖昧になる。
**How to avoid:** planner が事前登録（Claude's Discretion「SC#4 gate の具体的閾値」と整合）: p_min を p_lower ベースで 0.15 にするか・p ベースで 0.15 を維持するか。投票層（SC#4 WARN gate の対象）の定義と整合させる。
**Warning signs:** selected_only calibration の対象馬数が v1.0 と大きく変わる・p_min の解釈が report に書かれていない。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存・§17.3 test list） |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`・testpaths=["tests"]・marker `requires_db` |
| Quick run command | `uv run pytest tests/ -x -q` （KEIBA_SKIP_DB_TESTS=1 で unit only） |
| Full suite command | `uv run pytest tests/ -ra` （KEIBA_SKIP_DB_TESTS unset で live-DB フルスイート・SC#5） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EV-01 (SC#1) | p_lower 計算が calib slice のみで q_shrink を計算し・test 窓 outcome を使用しない | unit | `uv run pytest tests/model/test_p_lower.py -x` （KEIBA_SKIP_DB_TESTS=1） | ❌ Wave 0 |
| EV-01 (SC#1) | p_lower が byte-reproducible（np.quantile 決定論的） | unit | `uv run pytest tests/model/test_p_lower.py::test_p_lower_byte_reproducible -x` | ❌ Wave 0 |
| EV-01 (SC#1) | prediction p_fukusho_hit_lower 列 migration が idempotent・3ファイル連鎖 | integration (live-DB) | `uv run pytest tests/db/test_schema_p_lower.py -x` （KEIBA_SKIP_DB_TESTS unset） | ❌ Wave 0 |
| EVAL-01 (SC#2) | §15.2 事前登録指標（calibration_max_dev/Brier/LogLoss/sum(p)）が不変 | regression (live-DB) | `uv run pytest tests/evaluation/test_phase12_metrics_invariants.py -x` （KEIBA_SKIP_DB_TESTS unset） | ❌ Wave 0 |
| EVAL-01 (SC#2) | EV-decile / disagreement ROI / snapshot→final slippage が測定される | unit | `uv run pytest tests/evaluation/test_extended_metrics.py -x` （KEIBA_SKIP_DB_TESTS=1） | ❌ Wave 0 |
| EVAL-02 (SC#3) | falsification ロジット回帰が race_id clustered SE で model_p pvalue を返す | unit | `uv run pytest tests/evaluation/test_falsification.py -x` （KEIBA_SKIP_DB_TESTS=1） | ❌ Wave 0 |
| EVAL-02 (SC#3) | falsification が test 窓 outcome を学習に使わない（leakage 検出） | adversarial audit | `uv run pytest tests/audit/test_audit_p_lower_falsification.py::test_falsification_no_test_outcome_leak -x` | ❌ Wave 0 |
| SAFE-01 (SC#4) | p_lower 計算・falsification・market_implied 層に odds/ninki proxy が混入しない（AST） | adversarial audit | `uv run pytest tests/audit/test_audit_p_lower_falsification.py -x` | ❌ Wave 0 |
| SAFE-01 (SC#4) | FEATURE_COLUMNS に odds/ninki が混入しない（SAFE-01 proxy 排除） | adversarial audit | `uv run pytest tests/audit/test_audit_field_strength.py -x` （既存・拡張） | ✅（拡張） |
| SC#4 | オッズ帯別条件付き calibration WARN gate が投票層の過大予測を catch する | unit | `uv run pytest tests/model/test_evaluator_phase12_gate.py -x` （KEIBA_SKIP_DB_TESTS=1） | ❌ Wave 0 |
| SC#5 | 対抗的監査フルスイート GREEN（KEIBA_SKIP_DB_TESTS unset・live-DB） | integration (live-DB) | `uv run pytest tests/audit/ -x` （KEIBA_SKIP_DB_TESTS unset） | ✅（拡張） |
| SC#5 | byte-reproducible snapshot + 再現性スモーク（実データ PASS） | smoke (live-DB) | `uv run python scripts/run_phase12_evaluation.py --reproduce-smoke` （memory: feature-snapshot-regen-required） | ❌ Wave 0 |
| D-10 | set_primary_model Call 0件（is_primary DB 変更しない） | adversarial audit | `uv run pytest tests/audit/test_audit_p_lower_falsification.py::test_no_set_primary_model_call -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/model/test_p_lower.py tests/evaluation/test_falsification.py -x -q` （KEIBA_SKIP_DB_TESTS=1・quick unit）
- **Per wave merge:** `uv run pytest tests/ -ra` （KEIBA_SKIP_DB_TESTS=1・full unit）
- **Phase gate:** `uv run pytest tests/ -ra` （KEIBA_SKIP_DB_TESTS unset・live-DB フルスイート GREEN・SC#5）+ `run_phase12_evaluation.py --reproduce-smoke`（実データ再現性）

### Wave 0 Gaps
- [ ] `tests/model/test_p_lower.py` — covers EV-01 (SC#1) p_lower 計算・calib slice 聖域・byte-reproducible
- [ ] `tests/evaluation/test_falsification.py` — covers EVAL-02 (SC#3) falsification ロジット回帰・clustered SE
- [ ] `tests/evaluation/test_extended_metrics.py` — covers EVAL-01 (SC#2) EV-decile/disagreement/slippage ROI
- [ ] `tests/evaluation/test_phase12_metrics_invariants.py` — covers §15.2 事前登録指標不変（regression・live-DB）
- [ ] `tests/model/test_evaluator_phase12_gate.py` — covers SC#4 オッズ帯別条件付き calibration WARN gate
- [ ] `tests/db/test_schema_p_lower.py` — covers EV-01 p_lower 列 migration idempotent・3ファイル連鎖（live-DB）
- [ ] `tests/audit/test_audit_p_lower_falsification.py` — covers SAFE-01 proxy 排除 AST + falsification leakage + set_primary_model Call 0件
- [ ] statsmodels install: `uv add "statsmodels>=0.14.6"` — pyproject.toml + uv.lock へ反映
- [ ] `scripts/run_phase12_evaluation.py` ひな形 — run_phase11_evaluation.py 構造踏襲

*(既存 tests/audit/test_audit_field_strength.py は SAFE-01 proxy 排除で拡張・新規でない)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Streamlit local-only・UI 層変更なし（Phase 7） |
| V3 Session Management | no | local single-user・変更なし |
| V4 Access Control | yes | owner/admin 権限で ALTER TABLE（memory: migration-privilege-admin-required）・etl ロールで prediction INSERT・set_primary_model Call 0件（D-10・AST check） |
| V5 Input Validation | yes | `_assert_valid_prediction_df` で p_fukusho_hit_lower ∈ [0,1] 検証・DB CHECK 制約 prediction_p_lower_range・logit clipping eps=1e-6 |
| V6 Cryptography | no | 該当なし |
| V7 Error Handling | yes | fail-loud（silent fallback 禁止・Phase 10 gap-closure CR-01〜04 鏡像）・q_shrink 計算不能・falsification 回帰失敗は RuntimeError |
| V9 Communications | no | local-only |
| V14 Configuration | yes | statsmodels 新規依存・pyproject.toml + uv.lock で再現性・FIXED_REPRODUCE_TS |

### Known Threat Patterns for 統計的評価 / migration phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| test 窓 outcome の q_shrink / market calibrator / falsification 回帰学習への混入（後知恵リーク） | Tampering / Information disclosure | q_shrink 関数は calib 引数のみ（test 窓 outcome を取らない・Pattern 1）・tests/audit leakage テスト・§11.2 聖域 |
| odds/ninki proxy の `p` モデル特徴量混入（SAFE-01 違反・市場回帰で edge 消滅） | Tampering | tests/audit AST テスト（forbidden Name/Attribute/string-constant 0件）・SAFE-01-ALLOW マーカー（race_relative.py compute_overprediction_penalty 既存 idiom）・FEATURE_COLUMNS と evaluation 層の分離 |
| prediction 列 migration の 3 ファイル不整合（silent 誤作動・誤列 INSERT） | Tampering | `_assert_valid_prediction_df` 列順序チェック・CHECK 制約・Pitfall 4 3ファイル連鎖 |
| ALTER TABLE の権限不足（InsufficientPrivilege） | Elevation | owner/admin 権限で run_apply_schema.py・etl ロールで不可（memory: migration-privilege-admin-required） |
| §15.2 事前登録指標の後知恵すり替え | Tampering | §15.2 gate は不変（D-06）・拡張指標は併載（上書きでない）・regression test で不変性検証 |
| is_primary 自動切替（D-10 違反） | Tampering / Repudiation | set_primary_model Call 0件 AST check・switch_recommendation は report のみ・人間承認の別アクション |
| split conformal の過度な保証主張（統計的厳密さ違反） | Information disclosure (誤報) | coverage 表現は「実測 coverage + selected-only calibration」・q_level を α と同一視しない（D-01/D-02） |

## Sources

### Primary (HIGH confidence)
- scikit-learn 1.9.0 — Probability Calibration（`method='isotonic'` when ≥1000 samples / `'sigmoid'` when ≪1000・`cv='prefit'` mandatory for time series）— https://scikit-learn.org/stable/modules/calibration.html [VERIFIED]
- statsmodels 0.14.6 — PyPI（requires numpy<3,>=1.22.3 / scipy!=1.9.2,>=1.8 / pandas>=1.4・本プロジェクトと互換・2026-06-27 確認）— https://pypi.org/pypi/statsmodels/json [VERIFIED]
- statsmodels GitHub Issue #6287 — `Logit.fit(cov_type='cluster', cov_kwds={'groups': array})` が正しい API・`groups=` 直接渡しは error — https://github.com/statsmodels/statsmodels/issues/6287 [VERIFIED]
- statsmodels — `multipletests(pvals, alpha=0.05, method='holm')` 4-tuple `(reject, pvals_corrected, alphacSidak, alphacBonf)` — https://www.statsmodels.org/dev/generated/statsmodels.stats.multitest.multipletests.html [VERIFIED]
- JMLR 2024 v25/23-1553 — "Split Conformal Prediction and Non-Exchangeable Data"（split conformal は exchangeability 必須・時系列で壊れる・weighted/sequential が適応策）— https://jmlr.org/papers/volume25/23-1553/23-1553.pdf [VERIFIED]
- Romano, Patterson & Candès (2019) — "Conformalized Quantile Regression" NeurIPS（CQR・基礎文献）— Conformal Prediction Beyond Exchangeability (Annals of Statistics 2023) で引用 [CITED]

### Secondary (MEDIUM confidence)
- Conformal Prediction Beyond Exchangeability (Annals of Statistics 2023) — exchangeability 弛める枠組み・Romano 2019 を引用 — https://projecteuclid.org/journals/annals-of-statistics/volume-51/issue-2/Conformal-prediction-beyond-exchangeability/10.1214/23-AOS2276.pdf [CITED]
- Adaptive Conformal Predictions for Time Series (Zaffran et al.) — ACI が時系列 distribution shift で有効 — https://www.semanticscholar.org/paper/Adaptive-Conformal-Predictions-for-Time-Series-Zaffran-Dieuleveut [CITED]
- domain-analysis §0/§1/§5/§6/§8 — core value 再定式化・層分離・falsification 設計思想・文献（Benter 1994 / Bolton & Chapman 1986 / Lessmann 2010 / Hausch 1981）— `.planning/research/v1.1-domain-analysis.md` [VERIFIED: codebase]

### Tertiary (LOW confidence — 実装で確認必要)
- np.quantile の default linear interpolation が seed 非依存・決定論的 — 実証検証済み（本 research session）だが statsmodels/sklearn の version upgrade で挙動変化可能性は監視
- JRA 複勝オッズの典型的範囲（fuku_odds_lower ∈ [1.0, 100.0] 程度）・1/odds の saturate 挙動 — planner が実データで確認し odds clipping 範囲を事前登録

## Project Skills

project skills ディレクトリ（`.claude/skills/` / `.agents/skills/` / `.cursor/skills/` / `.github/skills/` / `.codex/skills/`）に SKILL.md なし（CLAUDE.md で確認済み）。Phase 12 は project skill パターンに依存しない。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | prediction p_lower 列 migration・falsification 実データ評価 | ✓ | 15.18 (Homebrew・host) | — |
| Python 3.12 | runtime | ✓ | 3.12.13 (host) | — |
| uv | 依存管理 + lockfile | ✓ | 0.11.21 (host) | — |
| statsmodels | falsification clustered SE・logit 回帰・Holm 補正 | ✗ | — | **新規追加必須**（`uv add "statsmodels>=0.14.6"`・fallback なし） |
| LightGBM | 既存（race-relative model 再利用） | ✓ | 4.6.0 | — |
| CatBoost | 既存（race-relative model 再利用） | ✓ | 1.2.10 | — |
| scikit-learn | market_implied 再校正・既存 calibration | ✓ | 1.9.0 | — |
| numpy / pandas / scipy | q_shrink 計算・binning・logit clipping | ✓ | transitive | — |

**Missing dependencies with no fallback:**
- **statsmodels** — falsification の race_id clustered SE と Holm 補正に必須・代替なし（手作り sandwich covariance は統計的厳密さで劣る・Don't Hand-Roll）。Wave 0 で `uv add` 必須。

**Missing dependencies with fallback:**
- なし

## Code Examples

### 例1: p_lower 計算の完全な呼出経路（orchestrator L754 後に挿入）
```python
# Source: CONTEXT.md D-01/D-02/D-03 + Pattern 1 + race_relative.py apply_race_relative_correction
# orchestrator.train_and_predict の L754 (race_relative 補正後) に挿入

# calib slice のみで q_shrink を計算（test 窓聖域・§11.2）
# p_final は apply_race_relative_correction の戻り値（race-relative 補正後）
# orchestrator は calib slice の index を把握している（score_split_label == "calib"）

# pred_df に p_fukusho_hit_lower 列を付与（PREDICTION_COLUMNS の p_fukusho_hit の直後）
# v1.0 binary 行（theta=None）は p_fukusho_hit_lower = NULL（後方互換）
```

### 例2: switch_recommendation 統合（reports/12-* に記録）
```python
# Source: CONTEXT.md D-09 + run_phase11_evaluation.py _evaluate_gate 構造踏襲

def compute_switch_recommendation(
    sc4_warn_gate_result: dict,      # evaluator.check_acceptance_gate の Phase 12 WARN gate
    p_lower_ev_vs_v1_binary: dict,   # p_lower EV の回収率と v1.0 binary の回収率比較
    falsification_result: dict,      # model_p residual の有意性 (feature_gap / structural_limit)
) -> str:
    """switch / hold / reject を統合判定 (D-09).

    事後判断を野放しにしないため D-09/D-10 で構造化:
      - switch: SC#4 gate PASS・p_lower EV が v1.0 binary より回収率改善・falsification で
                model_p residual が有意（特徴量不足でなく改善余地）
      - hold:   一部条件のみ成立・人間判断が必要
      - reject: SC#4 gate FAIL（投票層過大予測が改善せず）・または falsification で
                structural_limit（core value 維持での黒字化棄却）

    is_primary DB 変更はしない（D-10・人間承認の別アクション）。
    """
    sc4_pass = not sc4_warn_gate_result.get("phase12_warn_triggered", False)
    ev_improved = p_lower_ev_vs_v1_binary.get("recovery_rate_delta", 0) > 0
    falsification_feature_gap = falsification_result.get("verdict") == "feature_gap"

    if sc4_pass and ev_improved:
        return "switch"  # 人間承認で is_primary=true へ
    elif sc4_pass and falsification_feature_gap:
        return "hold"    # 改善余地あり・次フェーズ検討
    else:
        return "reject"  # 構造的限界・core value 維持での黒字化困難
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 点推定 `p` での EV 判定（v1.0 binary・Phase 11 race-relative） | `p_lower × odds_lower`（下側信頼限界・conformal 風 shrinkage） | Phase 12 (2026) | 投票層の過大 `p` を削り・現実回収率 0.78-0.92 を正直に測る（domain-analysis §0） |
| §15.2 全体 Brier のみ | selected-only calibration + EV-decile ROI + disagreement ROI | Phase 12 (EVAL-01) | 全体 Brier が隠す投票層の失敗を可視化（domain-analysis §6） |
| 無鑑別の回収率 0.65 天井 | falsification `logit(outcome) ~ logit(market) + logit(model_p)` | Phase 12 (EVAL-02) | 特徴量不足（model_p 有意残差）と構造的限界（market 係数が model を包摂）の鑑別（domain-analysis §6・Codex 提唱） |
| `p` と odds の独立性要件（強すぎる） | オッズ帯別条件付き calibration（過大でないこと・WARN gate） | Phase 12 (SAFE-01) | core value 再定式化（PROJECT.md・優秀なモデルほど負相関は許容） |

**Deprecated/outdated:**
- 点推定 `p` での EV 判定: 過信リスク・投票層の過大 `p` を削れない（v1.0 の p=0.16→実0.04 の4倍過大）。p_lower で置き換え。
- 全体 Brier のみの評価: 投票層の失敗を隠す。selected-only calibration を併載。
- `p` と odds の独立性の数学的厳密要件: 優秀なモデルほど market と負相関するため強すぎる。オッズ帯別条件付き calibration が真の要件。

## Assumptions Log

> planner と discuss-phase が確認すべき [ASSUMED] クレーム。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | calib slice の sample size が ≥ 1000（market_implied で isotonic 使用可） | Pattern 6 / Pitfall 5 | < 1000 の場合 sigmoid（Platt）を使用・planner が calib size を確認し事前登録 |
| A2 | JRA 複勝オッズの典型範囲が fuku_odds_lower ∈ [1.0, 100.0] 程度（1/odds ∈ [0.01, 1.0]） | Pattern 6 / Pitfall 6 | 極端オッズの clipping 範囲が違うと market_implied が歪む・planner が実データで確認し事前登録 |
| A3 | race_id clustered SE で race 内の outcome 相関を十分キャッチ（field size 共変量は補助） | Pattern 5 / D-05 (c) | field size で層別が必要になる可能性・planner がサブ解析で確認 |
| A4 | q_level=0.90 が投票層の過大予測を適切に削る強度（v1.0 の4倍過大を catch） | Pattern 1 / D-02 | 強すぎると選ばれる馬が少なくなりすぎる・弱すぎると過大予測が残る・planner が事前登録し test 窓で変更しない |
| A5 | p_lower 列の NULL 許容（v1.0 binary 行の後方互換）が既存クエリに影響しない | Pattern 2 / Pitfall 3 | 既存の `WHERE p_fukusho_hit_lower IS NOT NULL` 等の追加が必要・planner が確認 |
| A6 | statsmodels 0.14.6 が本プロジェクトの numpy 2.x / pandas 3.0.3 と実行時互換（requires 制約は満たすが wheel の実検証必要） | Standard Stack / Package Legitimacy | import error や実行時 warning の可能性・Wave 0 で `uv add` 後に smoke test で確認 |

**If this table is empty:** 該当なし。上記 A1-A6 は planner が事前登録または Wave 0 で確認すべき項目。

## Open Questions

1. **purchase_simulator の p_min=0.15 を p と p_lower のどちらのベースにするか**
   - What we know: select_bets は `p_fukusho_hit >= 0.15` を見る。Phase 12 で EV は p_lower ベース。
   - What's unclear: p_min を p_lower ベースで 0.15 にすると（保守的）・p ベースで 0.15 を維持すると（p_lower が p より小さいので選ばれやすい）で投票層の定義が変わる。
   - Recommendation: planner が事前登録（Claude's Discretion「SC#4 gate の具体的閾値」と整合）。投票層（SC#4 WARN gate の対象）の定義と整合させる。Phase 10 D-12 / 11 D-03 の事前登録パターン踏襲。

2. **bin/odds_band サブ解析の Holm 補正の対象範囲**
   - What we know: D-05 で bin/odds_band サブ解析のみ Holm 補正・model_p 単一係数の主検定は Holm 不要。
   - What's unclear: どの band をサブ解析に含めるか（ODDS_BAND_EDGES 4 band 全部か・投票層のみか）・Holm の alpha（0.05 で統一か）。
   - Recommendation: planner が事前登録。投票層（高オッズ域・EV 上位）を主軸にしつつ・全 band をサブ解析して全体像を掴む。

3. **bootstrap / ensemble p_lower の fallback 発動条件**
   - What we know: D-01 conformal 風 shrinkage を主軸・bootstrap/ensemble は fallback（Claude's Discretion）。
   - What's unclear: exchangeability が数値的に阻害されたと判断する基準（calib/test の coverage が q_level から大きく外れた時？・時系列 drift の定量基準？）。
   - Recommendation: planner が事前登録。coverage 実測値が q_level=0.90 に対して大きく乖離（例: < 0.80）した場合に bootstrap fallback を発動・report に両方記載。

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — statsmodels 0.14.6 が PyPI で確認・requires 制約が本プロジェクトと互換・clustered SE/multipletests API が公式 docs + GitHub issue で確認
- Architecture (p_lower / falsification / migration 連鎖): HIGH — 踏襲アセットの現状シグネチャを実証検証（race_relative.py / orchestrator L754 / PREDICTION_COLUMNS 19列 / schema.py APPLY_ORDER / check_acceptance_gate warn_reasons）・CONTEXT.md D-01〜D-10 確定判断と整合
- Pitfalls: HIGH — split conformal exchangeability は JMLR 2024 で確認・statsmodels cov_kwds API は GitHub #6287 で確認・isotonic 1000 rule は sklearn docs で確認・3ファイル連鎖は Pitfall 4 既知
- Validation Architecture: HIGH — §17.3 test list・KEIBA_SKIP_DB_TESTS marker・tests/audit/ 5段階鋳型が既存

**Research date:** 2026-06-27
**Valid until:** 2026-07-27（30 days・statsmodels/sklearn は安定・JRA データ閾値は実データ確認で延長）
