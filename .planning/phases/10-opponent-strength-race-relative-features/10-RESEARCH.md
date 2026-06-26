# Phase 10: Opponent Strength & Race-Relative Features - Research

**Researched:** 2026-06-26
**Domain:** 相手強度特徴量 (FEAT-02) + レース内相対特徴量 (FEAT-03)・odds-free・PIT-safe・byte-reproducible
**Confidence:** HIGH（踏襲 idiom 完全特定・live-DB 実証済・CONTEXT.md で決定事項 D-01〜D-16 ロック済）

## Summary

Phase 10 は Phase 9.1 完了後の新 snapshot `20260626-1a-speedprofile-v1`（features=79・17-feature 拡張 speed profile）を前提に、**相手強度 `field_strength`（FEAT-02）とレース内相対特徴量（FEAT-03: speed_index_rank 3軸 / gap_to_top / gap_to_3rd / field_strength_adjusted_rank）を odds-free・PIT-safe に追加**する。複勝の「相対競争・各馬独立事象でない」性質を特徴量層で表現する、core value「リーク防止最優先」を最も厳格に問う Phase である。

研究の核心は 3 点：(1) **D-01 厳格版 as-of**（各過去走の source race 時点 `available_at` で相手の rolling 能力を再計算・未来情報の遡及注入なし）の機械的実現方法、(2) **D-04 発走馬特定**の live-DB 実証（`tozaicd` は EveryDB2 独自拡張で発走馬判定に使えない・`kakuteijyuni > 0` が確実シグナル）、(3) **D-06 2段階集約構造**（第1段階 = source race 内 opponent profile 8値・第2段階 = target 馬の過去走 profile を latest-K rolling）の計算量見積もりと vectorized 実装方針である。

全アセット（`compute_speed_figure_for_history`・`build_rolling_features`・`_ROLLING_SYSTEMS`・`_pit_cutoff_prefilter`・`merge_asof(direction='backward')`・`assert_matrix_columns_registered`・`_atomic_write_text`・adversarial audit AST 検査）は既存 idiom をそのまま拡張可能で、新モジュールは `src/features/field_strength.py`（D-02/D-06 第1段階）と `src/features/race_relative.py`（FEAT-03 target のみ）の2つ、加えて `rolling.py::_ROLLING_SYSTEMS` への `field_strength` 系統追加（D-06 第2段階）で構成する。計算量は history 48万行 × 平均14相手 = 約6.7M ペアの第1段階集約で、純粋ループは致命的低速（数十分単位）のため **per-source-race batch + vectorized pandas groupby** が必須。

**Primary recommendation:** `field_strength.py`（第1段階: source race 内 opponent profile 計算）+ `race_relative.py`（FEAT-03 target-only race_id group-by）+ `rolling.py::_ROLLING_SYSTEMS` 拡張（第2段階: field_strength profile の latest-K rolling）の3層構成で実装する。PIT 保証は既存 `_pit_cutoff_prefilter` (strict `<`) と `merge_asof(direction='backward')` を対称に適用。発走馬特定は `kakuteijyuni > 0` の単一条件（time=0 と完全一致・live-DB 実証済）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions（CONTEXT.md ## decisions より・変更不可）

**相手強度 field_strength 定義（FEAT-02・SC#1）:**
- **D-01:** **as-of 厳格版**採用。各過去走 source race 時点 `available_at` で存在する相手の能力のみ使用。再評価版・両方比較は不採用。
- **D-02:** 相手能力の測度 = **相手の当時の rolling 安定能力**（source race 時点 `available_at` までの latest-K `speed_figure` profile）。単発 `speed_figure` でなく安定能力。
- **D-03:** source race 内の相手集約 = **mean 単独でなく field_strength profile（8値）**: `mean` / `median` / `top3_mean` / `top5_mean` / `max` / `sd` / `valid_count` / `coverage`。canonical は `mean`。
- **D-04:** 相手範囲 = **実際に発走した馬のみ**。未発走馬（除外・取消・発走除外）は相手から除外。**競走中止馬は発走済みなので相手に含む**（rolling 能力が取得できる限り）。
- **D-05:** top-k 集約（`top3_mean`/`top5_mean`）は `k = min(k, valid_opponents)` でクランプ。`valid_count` / `coverage` を必ず保持。
- **D-06:** **2段階集約構造**。第1段階 = source race 内 opponent profile（8値中間値）。第2段階 = target 馬の過去走 profile を v1.0 rolling algorithm（`available_at < feature_cutoff_datetime`・strict `<`）で latest-K 集約。

**レース内相対特徴量（FEAT-03・SC#2）:**
- **D-07:** `speed_index_rank` は **3軸**（`rolling_speed_figure_mean_5` / `best2_mean_5` / `median_5`）それぞれで race_id 内 rank。FEAT-03 は **target observation のみ**（過去走には適用しない）。
- **D-08:** `gap_to_top` / `gap_to_3rd` は **`mean_5` 主軸**（canonical）・**指数 point 差**（`top/3位の mean_5 − self`）。秒差・race 内 z-score は不採用。
- **D-09:** speed_index 欠損馬は **NaN 保持・母集団除外**。最下位固定・sentinel 数値（magic number）は不採用。
- **D-10:** 同着 = **competition ranking（min rank・"1224" 方式）**。
- **D-11:** `field_strength_adjusted_rank` は **additive score**（`rolling_speed_figure_mean_5 + 0.25 * rolling_field_strength_mean_mean_5`）を race_id 内 rank 化。差・比は不採用（強い相手と走ってきた馬を不当に下げるため）。raw rank/profile と別保持（composite が効かない場合の安全策）。
- **D-12:** additive score 係数 = **0.25 を事前登録 canonical 初期値**・候補集合 `{0.0, 0.1, 0.25, 0.5}` で **train/calib 窓内のみ**感度分析。`0.0` = baseline（raw `mean_5` rank と同値）必須。**test 窓選び直し禁止**（§11.2 聖域）。

**field_strength 集約（target feature 化・D-06 第2段階の具体形）:**
- **D-13:** target 馬の過去走 field_strength profile を latest-K rolling で集約 = **21 feature**（rich but bounded）:
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_latest_1`（6）
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max}_mean_3`（5）
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_mean_5`（6）
  - `rolling_field_strength_mean_trend_last_minus_mean5` / `_trend_mean3_minus_mean5`（2）
  - `rolling_field_strength_valid_count_mean_5` / `coverage_mean_5`（2）
- **D-14:** **same_surface / same_distance_bucket は Phase 10 では入れない**（条件適性は speed profile 側で既存・重複回避・feature 膨張抑制）。

**SC#5 評価方針（feature ノイズ化の回帰検知）:**
- **D-15:** **中間**（非劣化必須 gate + 参考記録）。Brier/LogLoss/AUC が Phase 6 D-07 水準（Brier=0.15222/LogLoss=0.47488/AUC=0.73230）を悪化させないことを**必須 gate**。`selected-only calibration` / `odds_band×p_bin` は**参考記録**（Phase 12 EVAL-01 先行指標）。residual proxy・正規 falsification test は Phase 12 EVAL-02 委譲。Phase 9 stop gate（4指標 + residual proxy による go/no-go）は不採用（feature 追加段階・MODEL-01 前で改善期待には早い）。
- **D-16:** 非劣化の**許容幅（Brier/LogLoss/AUC 各）と pass/fail ルールは planner が Plan 内で事前登録**（候補例: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005 程度・Phase 11 SC#2 事前登録マージンとの整合）。**評価結果を見た後に変更しない**（§11.2 聖域）。

### Claude's Discretion（研究対象・推奨あり）

- **発走馬特定の実装** — `datakubun` / 取消・除外ステータスの正規化層素材を live-DB で精査（→ **研究結果: `kakuteijyuni > 0` の単一条件で機械的確定**・詳細後述）。
- **相手の当時 rolling の vectorized 実装** — 計算量の多い処理（→ **研究結果: per-source-race batch + vectorized groupby** 必須・純粋ループは致命的低速）。
- **モジュール構成・`compute_field_strength` 配置** — 新モジュール `field_strength.py` + `race_relative.py` 推奨（詳細後述）。
- **`builder.py` 拡張** — Step 5c 相手強度・Step 7 レース内相対の挿入位置（→ 09-01-PLAN.md Step 5b idiom と対称）。
- **snapshot `feature_snapshot_id` 命名・`schema_version`** — `20260626-1a-opponentstrength-v1`（`make_model_version` 形式・09/9.1 系統継承）・schema_version 0.5.0 → 0.6.0。
- **`feature_count` 最終値・registry↔Parquet parity** — 21 field_strength + FEAT-03 6 feature（rank 3 + gap 2 + adjusted_rank 1）= **27 新 feature**。feature_availability.yaml・registry・`_ROLLING_SYSTEMS` 3者 parity。
- **非劣化マージン数値（D-16）** — planner が Phase 11 SC#2 と整合して決定（候補: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005）。

### Deferred Ideas（OUT OF SCOPE・別 Phase）

- 正規 falsification test（`logit(outcome) ~ logit(market_implied) + logit(model_p)`・race_id clustered SE・market 再校正・正式レポート）— Phase 12 EVAL-02（residual proxy も同委譲・D-15）
- `p_lower`（下側信頼限界）による EV 判定 — Phase 12 EV-01
- レース内相対確率モデル（`sum(p)=払戻対象数` 制約・race-level top-k calibration）— Phase 11 MODEL-01（FEAT-02/03 完成後の入力）
- same_surface / same_distance_bucket の相手強度版・decay 加重 field_strength・class 別 field_strength — speed 側で条件適性を既存扱い・本 Phase では重複回避（将来 refinement）
- field_strength profile の additional 軸（percentile・IQR 等）・FEAT-03 の過去走適用（target のみで十分と判断・将来検討）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **FEAT-02** | 相手強度補正特徴量を追加する — 過去走の相手の as-of 能力平均・`field_strength` で、低着順でも強い相手なら価値があることを反映（odds-free・PIT-safe） | D-01 厳格版 as-of + D-02 当時 rolling 能力 + D-06 2段階集約 + D-13 21 feature が FEAT-02 を完全に具象化。`field_strength.py`（第1段階）+ `rolling.py::_ROLLING_SYSTEMS` 拡張（第2段階）で実装。`compute_speed_figure_for_history` の戻り値（各過去走の speed_figure + available_at + race_nkey + kettonum）が入力素材。 |
| **FEAT-03** | レース内相対特徴量を追加する — スピード指数等の出走馬内 `rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`（複勝は相対競争・各馬独立事象でない） | D-07 rank 3軸 + D-08 gap mean_5 主軸 + D-09 NaN/母集団除外 + D-10 competition ranking + D-11 additive score + D-12 係数候補 {0.0,0.1,0.25,0.5} が FEAT-03 を完全に具象化。`race_relative.py`（target-only・race_id group-by）で実装。FEAT-02 完成後の rolling_field_strength_mean_mean_5 が adjusted_rank の入力。 |
| **SAFE-01** | core value を維持する — オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない（市場回帰で edge 消滅） | 既存 adversarial audit idiom（`_FORBIDDEN_TOKENS` AST Name/Attribute/Constant 検査・`tests/audit/test_audit_speed_figure.py` 鋳型）を `field_strength.py` / `race_relative.py` に拡張。新 feature に odds/ninki proxy が混入しないことの静的証明。 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md の leakage-prevention 設計（最優先・本 Phase の core value）:

1. **odds-free 原則（SAFE-01）**: 相手強度・レース内相対のいかなる入力にもオッズ/人気/過去人気/過去オッズ proxy を入れない。speed_figure（Phase 9 D-05 float 指数）・過去走 rolling speed_figure profile のみで測る。target/過去走とも §13.4 禁止列（当日馬場/天候/馬体重/当日オッズ/当日ここまでの騎手成績/過去人気/過去オッズ proxy）は構造排除。
2. **LightGBM native categorical**: target/mean encoding は構造的禁止（§14.3）。新 feature は全て float/数値（rank・gap・field_strength profile）で categorical 性なし。
3. **CatBoost has_time=True**: ordered TS + 時系列順（§14.4）。新 feature は float なので直接関連しないが・snapshot 出力後の trainer で has_time=True は不変。
4. **merge_asof(direction='backward') / strict `<`**: PIT プリミティブ。相手強度（D-01 厳格版）は `available_at < feature_cutoff_datetime` の strict `<` を適用。レース内相対（target のみ）は feature_cutoff_datetime 時点での確定情報のみ（出馬表確定後・当日結果不使用）。
5. **CalibratedClassifierCV cv='prefit'**: later-disjoint calibration。SC#5 評価時に厳守（Phase 6 D-07 水準との比較）。
6. **GroupTimeSeriesSplit**: race_id group。SC#5 v1.0 LightGBM 再学習時に厳守（mlxtend・sklearn TimeSeriesSplit は group-aware でないため不使用）。
7. **byte-reproducible snapshot**: §19.1 聖域。FIXED_REPRODUCE_TS・SHA256・metadata 除外再計算。新 snapshot は `write_snapshot` 既存 idiom 踏襲。

**Python 3.12 / uv 管理 / ruff lint・pytest test 必須**（§17.1/§17.3）。**live-DB 必須検証**（memory `feature-snapshot-regen-required`・unit test 後に live-DB で snapshot 再生成検証・実データでしか発覚しない Parquet 直列化 bug あり）。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 相手強度 field_strength profile 計算（D-06 第1段階） | Feature 構築層（`src/features/field_strength.py`） | — | source race 内の opponent rolling 能力から profile 8値を算出。PIT 保証は `_pit_cutoff_prefilter` (strict `<`) で適用。target tier は時系列厳格 as-of を要件とするため feature 層で完結。 |
| 相手強度 latest-K rolling（D-06 第2段階・21 feature） | Feature 構築層（`src/features/rolling.py::_ROLLING_SYSTEMS` 拡張） | — | target 馬の過去走 field_strength profile を latest-K で集約。`obs_id` group・strict `<cutoff`・`_ROLLING_SYSTEMS` idiom 踏襲（speed_figure 17 feature と対称）。 |
| レース内相対特徴量（FEAT-03・target-only） | Feature 構築層（`src/features/race_relative.py`） | — | target observation のみ・race_id（`race_nkey`）group-by で rank/gap/adjusted_rank を計算。過去走には適用しない（D-07）。出馬表確定時点 `feature_cutoff_datetime` 基準。 |
| 発走馬特定（D-04） | Feature 構築層（`field_strength.py` 内ヘルパ） | normalized 層素材 | `kakuteijyuni > 0` の単一条件（live-DB 実証・time=0 と完全一致）で機械的確定。normalized 層に `datakubun` は存在しない（精査済）。 |
| PIT 保証 | Feature 構築層（既存 `_pit_cutoff_prefilter`・`merge_asof(direction='backward')`・strict `<`） | availability.py（CUTOFF_SEMANTICS 定数） | 既存 idiom を対称に適用。adversarial test が monkeypatch で guard を無効化し lookahead 混入を検証（`tests/audit/test_audit_features.py` 鋳型）。 |
| byte-reproducible snapshot | Feature 構築層（`snapshot.py::write_snapshot`） | — | §12.4 metadata 9 keys・SHA256（metadata 除外）・FIXED_REPRODUCE_TS・決定論的 PyArrow 書込。既存 idiom 踏襲・新 feature も数値/nullable 扱いで `_coerce_rolling_columns_for_parquet` 対象。 |
| registry↔Parquet parity | Feature 構築層（`availability.py`・`feature_availability.yaml`） | — | schema_version 0.5.0 → 0.6.0・`assert_matrix_columns_registered`・`_ROLLING_SYSTEMS_FOR_RESERVED` 拡張。 |
| adversarial audit（SAFE-01） | Audit 層（`src/audit/report.py`・`tests/audit/`） | — | AST Name/Attribute/Constant 検査（`_FORBIDDEN_TOKENS`）・lookahead 注入テスト。新 feature モジュールを検査対象に追加。 |
| SC#5 非劣化 gate | Evaluation 層（`evaluator.py`・`segment_eval.py`・`trainer.py`・`data.py`） | — | v1.0 LightGBM 再学習（FEATURE_COLUMNS allowlist 拡張・`make_X_y` 完全一致 assert）→ Brier/LogLoss/AUC 評価（D-07 水準比較）→ selected-only calibration / odds_band×p_bin 参考記録。 |

## Standard Stack

### Core（要件定義書 §17.1 固定・変更不可）

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 (<3.13) | Runtime | 要件固定・host 実証済 `[VERIFIED: host python3.12.13]` |
| pandas | 3.0.3 | DataFrame・`merge_asof(direction='backward')` PIT プリミティブ | 要件固定・`obs_id` group + `groupby.head(K)` + `nlargest` で vectorized rolling・byte-reproducible 決定論的順序 `kind="mergesort"` `[VERIFIED: pyproject.toml]` |
| NumPy | ≥2.0（transitive） | 配列演算・`np.where`/`np.digitize`/`np.bincount` | vectorized rank/gap 計算・competition ranking 実装 `CITED: numpy.org` |
| PyArrow | 24.0.0 | Parquet 読み書き・metadata 除外 SHA256 | byte-reproducible snapshot・`pa.Schema.from_pandas`・`pq.write_table(use_dictionary=False, compression="zstd")` `[VERIFIED: snapshot.py]` |
| LightGBM | 4.6.0 | SC#5 v1.0 主モデル再学習 | 要件固定・新 feature は全て float/数値で categorical 性なし・native NaN 処理（D-09 欠損馬 NaN 保持 と整合） `[VERIFIED: pyproject.toml]` |
| scikit-learn | 1.9.0 | Brier/LogLoss/AUC・CalibratedClassifierCV | 要件固定・`cv='prefit'` later-disjoint・METRIC_COLUMNS 固定 binning 契約 `[VERIFIED: evaluator.py]` |
| mlxtend | 0.25.0 | GroupTimeSeriesSplit | 要件固定・race_id group integrity・sklearn TimeSeriesSplit は非 group-aware `[VERIFIED: CLAUDE.md]` |
| psycopg[binary] | 3.3.4 | live-DB readonly SELECT | 要件固定・発走馬特定の live-DB 精査 `[VERIFIED: pyproject.toml]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DuckDB | 1.5.3 | 大量集計補助（任意） | per-source-race batch の高速化検討・pandas groupby で十分なら不要 `[VERIFIED: pyproject.toml]` |
| SciPy | transitive | `scipy.stats`（任意） | 本 Phase では直接使用しない・evaluator が既存利用 `[VERIFIED: evaluator.py import]` |
| PyYAML | standard | feature_availability.yaml 読込 | availability registry `[VERIFIED: availability.py]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas groupby + vectorized（推奨） | DuckDB `read_parquet` + SQL window | pandas で十分（6.7M ペアは秒単位）・DuckDB は Parquet 読込に限定し集計は pandas が既存 idiom・混在避ける |
| 新モジュール `field_strength.py` + `race_relative.py` | `speed_figure.py` / `rolling.py` 直接拡張 | 新モジュールが関心の分離明確・既存モジュール肥大化回避・adversarial audit の検査対象明示化 |
| `kakuteijyuni > 0` 単一条件（推奨） | `tozaicd`/`time`/`datakubun` 組合せ | live-DB 実証で `kakuteijyuni > 0` が time=0 と完全一致（1516件）・最も簡潔で確実・`tozaicd` は EveryDB2 独自拡張で意味不明 |

**Installation:** 新規依存関係なし。既存 `pyproject.toml` の依存関係で完結（pandas 3.0.3・NumPy・PyArrow・LightGBM・psycopg 3.3.4）。

## Package Legitimacy Audit

本 Phase は**新規外部パッケージをインストールしない**（既存 `pyproject.toml` の依存関係のみで完結）。Package Legitimacy Gate は skip。

| Package | Registry | Verdict | Disposition |
|---------|----------|---------|-------------|
| (新規インストールなし) | — | — | 本 Phase は N/A |

*Package Legitimacy Gate: SKIPPED（新規パッケージインストールなし・全依存関係は v1.0/Phase 9/9.1 で既に検証済）。*

## Architecture Patterns

### System Architecture Diagram

```
                           [Phase 9.1 snapshot 20260626-1a-speedprofile-v1 (79 features)]
                                              |
                                              v
   [target observations (feature_matrix)]   [history (全過去走・speed_figure 付与済)]
        |                                          |
        |   Step 5b: compute_speed_figure_for_history  (既存・Phase 9)
        |                          |
        |                          v
        |              [history with speed_figure/available_at/race_nkey/kettonum/surface]
        |                          |
        |              Step 5c: 相手強度 field_strength（D-06 第1段階）
        |              ┌────────────────────────────────────────────────────┐
        |              │ for each source race (race_nkey):                  │
        |              │   opponents = history[kakuteijyuni>0] - self       │  <- D-04 発走馬特定
        |              │   for each opponent:                               │
        |              │     rolling ability @ available_at (strict <)      │  <- D-01 厳格版 as-of
        |              │       = latest-K speed_figure profile              │  <- D-02 相手の当時能力
        |              │   profile_8vals = {mean,median,top3_mean,top5_mean,│  <- D-03 profile 化
        |              │     max,sd,valid_count,coverage} of opponents      │
        |              │   → source race 単位の field_strength profile      │
        |              └────────────────────────────────────────────────────┘
        |                          |
        |              v  [history with field_strength_profile (8値中間値)]
        |                          |
        |              Step 5d: 相手強度 latest-K rolling（D-06 第2段階）
        |              ┌────────────────────────────────────────────────────┐
        |              │ rolling.py::_ROLLING_SYSTEMS に field_strength 追加│
        |              │ obs_id group・strict <cutoff・latest-K algorithm   │
        |              │   → 21 feature (D-13):                             │
        |              │     rolling_field_strength_{axis}_{window}        │
        |              │     + trend + valid_count/coverage_mean_5          │
        |              └────────────────────────────────────────────────────┘
        |                          |
        v                          v
   [feature_matrix + rolling_field_strength_* 21 features (FEAT-02 完了)]
        |
        |   Step 7: レース内相対特徴量（FEAT-03・target-only）
        |   ┌────────────────────────────────────────────────────────────┐
        |   │ for each target race_nkey:                                 │
        |   │   population = obs[speed_index notna] (D-09 欠損馬除外)    │
        |   │   speed_index_rank_{mean5,best2_mean5,median5} =           │  <- D-07 rank 3軸
        |   │     competition_rank(population, desc)                      │  <- D-10 "1224" 方式
        |   │   gap_to_top = top.mean5 - self.mean5                       │  <- D-08 gap (mean_5 主軸)
        |   │   gap_to_3rd = 3rd.mean5 - self.mean5                       │
        |   │   for coef in {0.0, 0.1, 0.25, 0.5}:                        │  <- D-12 train/calib のみ
        |   │     score = mean5 + coef * field_strength_mean_mean_5       │  <- D-11 additive score
        |   │   field_strength_adjusted_rank = rank(score, coef=0.25)     │
        |   └────────────────────────────────────────────────────────────┘
        |
        v
   [feature_matrix + FEAT-02 21 + FEAT-03 6 = 27 新 features]
        |
        |   Step 7b: 中間列 drop (obs_id・中間 opponent profile 等)
        |   Step 8: §13.2 metadata stamp
        |   Step 9: assert_matrix_columns_registered (registry parity)
        |
        v
   [snapshot.py::write_snapshot] → snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet
        |
        v
   [data.py::make_X_y (FEATURE_COLUMNS allowlist拡張)] → [trainer.py v1.0 LightGBM 再学習]
        |
        v
   [evaluator.py + segment_eval.py] → SC#5 非劣化 gate (Brier/LogLoss/AUC vs D-07 水準)
                                    + selected-only calibration / odds_band×p_bin (参考記録)
        |
        v
   [tests/audit/] → adversarial audit (AST odds/ninki proxy 排除・lookahead 注入)
```

### Recommended Project Structure

```
src/features/
├── field_strength.py      # NEW Phase 10: 相手強度 profile 計算（D-06 第1段階）
│                          #   compute_field_strength_profile(history, observations)
│                          #   - source race 内 opponent profile 8値
│                          #   - PIT: _pit_cutoff_prefilter (strict <)
│                          #   - 発走馬特定: kakuteijyuni > 0
├── race_relative.py       # NEW Phase 10: レース内相対特徴量（FEAT-03・target-only）
│                          #   compute_race_relative_features(feature_matrix)
│                          #   - speed_index_rank 3軸・gap_to_top/3rd・adjusted_rank
│                          #   - race_id group-by・competition ranking
├── rolling.py             # 拡張: _ROLLING_SYSTEMS に field_strength 系統追加（第2段階）
├── speed_figure.py        # 既存（Phase 9・不変・import 元）
├── builder.py             # 拡張: Step 5c/5d/7 挿入・Step 7b drop
├── snapshot.py            # 既存（不変・新 feature は nullable Float64 で自動対応）
└── availability.py        # 拡張: _ROLLING_SYSTEMS_FOR_RESERVED に field_strength 追加

src/config/
└── feature_availability.yaml  # 拡張: 27 新 feature + schema_version 0.5.0 → 0.6.0

src/model/
├── data.py                # 既存（不変・FEATURE_COLUMNS は registry から動的導出・REVIEW H1）
├── trainer.py             # 既存（不変・v1.0 LightGBM 再学習）
├── evaluator.py           # 既存（不変・SC#5 評価）
└── segment_eval.py        # 既存（不変・参考記録）

src/audit/
└── report.py              # 既存（不変・SURFACE_ROWS に Phase 10 feature 追加は任意）

tests/features/
├── test_field_strength.py          # NEW: 第1段階 profile・PIT・発走馬特定 unit test
├── test_race_relative.py           # NEW: rank 3軸・gap・adjusted_rank・competition ranking unit test
└── test_rolling.py                 # 拡張: field_strength 系統 21 feature unit test

tests/audit/
└── test_audit_field_strength.py    # NEW: AST odds/ninki proxy 排除・lookahead 注入 adversarial

tests/features/test_speed_figure_builder_integration.py  # 拡張: hardcode feature list 更新
```

### Pattern 1: per-source-race batch + vectorized groupby（D-06 第1段階・必須）

**What:** 各 source race（`race_nkey`）内で相手の当時 rolling 能力を計算し profile 8値を算出する重処理。6.7M ペアを純粋ループで回すと数十分の低速化。

**When to use:** field_strength 第1段階計算（全 source race × 全 opponent × latest-K rolling）。

**Example:**
```python
# Source: 既存 rolling.py L378-383 idiom (groupby + head) + speed_figure.py の集約 idiom の合成
# 重いループは避ける・race_nkey group で vectorized 処理

def compute_field_strength_profile(history: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    """D-06 第1段階: 各 source race 内の opponent profile（8値）を vectorized で算出。

    PIT 保証（D-01 厳格版）: opponent の rolling 能力計算時に
    opponent.available_at < self.available_at (source race の available_at) を適用。
    ※ source race 自体の結果は相手能力に使わない（未来情報）・過去走のみ。
    """
    # 1. 発走馬特定（D-04・live-DB 実証済）: kakuteijyuni > 0
    starters = history[history["kakuteijyuni"].fillna(0) > 0].copy()

    # 2. 各 source race で self 以外の starter を展開（per-source-race batch）
    #    starter A から見た「同じ source race の他の starter」を join
    starters["_source_race_key"] = starters["race_nkey"]
    expanded = starters.merge(
        starters[["race_nkey", "kettonum", "speed_figure", "available_at"]].rename(
            columns={"kettonum": "_opp_kettonum",
                     "speed_figure": "_opp_speed_figure",
                     "available_at": "_opp_available_at"}
        ),
        left_on="_source_race_key", right_on="race_nkey",
        suffixes=("", "_opp"),
    )
    # self を除く
    expanded = expanded[expanded["kettonum"] != expanded["_opp_kettonum"]]

    # 3. D-01 厳格版 as-of: opponent の available_at < self の available_at (source race 時点)
    #    ※ strict <・_pit_cutoff_prefilter と同一不変量
    expanded = expanded[
        expanded["_opp_available_at"] < expanded["available_at"]
    ].copy()

    # 4. opponent の latest-K rolling speed_figure（既存 rolling.py idiom 再利用）
    #    各 (self_row, opponent) pair で opponent の self.available_at 以前 latest-K を集約
    #    ※ ここが最も計算量大・per-opponent latest-K を sort + groupby.head(K) で vectorized
    # ... (vectorized rolling 実装・詳細は PLAN で詰める)

    # 5. source race 内 opponent profile 8値（D-03）
    profile = expanded.groupby(["race_nkey", "kettonum"]).agg(
        field_strength_mean=("_opp_rolling_ability", "mean"),
        field_strength_median=("_opp_rolling_ability", "median"),
        field_strength_top3_mean=("_opp_rolling_ability", lambda s: s.nlargest(min(3, len(s))).mean()),
        field_strength_top5_mean=("_opp_rolling_ability", lambda s: s.nlargest(min(5, len(s))).mean()),
        field_strength_max=("_opp_rolling_ability", "max"),
        field_strength_sd=("_opp_rolling_ability", "std"),
        field_strength_valid_count=("_opp_rolling_ability", "count"),
    ).reset_index()
    # coverage = valid_count / starters_count_in_source_race
    return profile
```

### Pattern 2: latest-K rolling extension（D-06 第2段階・rolling.py 拡張）

**What:** `field_strength` 系統を `_ROLLING_SYSTEMS` に追加し・既存 `build_rolling_features` の `obs_id` group + strict `<cutoff` + latest-K algorithm を再利用して 21 feature（D-13）を生成。

**When to use:** target 馬の過去走 field_strength profile（第1段階中間値）を latest-K rolling で集約。

**Example:**
```python
# Source: rolling.py L74-87 _ROLLING_SYSTEMS idiom + L136-152 _SPEED_FIGURE_AXES idiom の合成
# rolling.py に追加:

_ROLLING_SYSTEMS: tuple[str, ...] = (
    # ... 既存8系統 + speed_figure ...
    "speed_figure",
    # NEW Phase 10: 相手強度 profile（D-06 第2段階）
    # source 列 = 第1段階で付与した field_strength profile 8値（mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）
    "field_strength",
)

# field_strength 系統の axis 定義（D-13・21 feature）
# mean_5 系: {mean,median,top3_mean,top5_mean,max,sd}_mean_5 (6)
# mean_3 系: {mean,median,top3_mean,top5_mean,max}_mean_3 (5)
# latest_1 系: {mean,median,top3_mean,top5_mean,max,sd}_latest_1 (6)
# trend 系: mean_{trend_last_minus_mean5, trend_mean3_minus_mean5} (2)
# count/coverage: {valid_count_mean_5, coverage_mean_5} (2)
# 計 21 feature

# 既存 speed_figure 集約ブロック（rolling.py L403-609）と対称なブロックを追加
# system == "field_strength": で分岐・第1段階 profile 列を source に集約
```

### Pattern 3: competition ranking（FEAT-03・D-10 同着）

**What:** race_id 内 rank を competition ranking（"1224" 方式・同着は同順位・min rank）で算出。

**When to use:** FEAT-03 speed_index_rank 3軸・gap_to_top/3rd・field_strength_adjusted_rank。

**Example:**
```python
# Source: 標準 competition ranking algorithm（"1224" = dense でない・min rank）
# pandas で vectorized 実装

def competition_rank(series_desc: pd.Series) -> pd.Series:
    """competition ranking（min rank・同着同順位・"1224" 方式・D-10）。

    降順（速いほど上位）で rank 1 から開始・同着は同じ rank・次は同着数だけ飛ぶ。
    例: values [100, 95, 95, 90] desc → ranks [1, 2, 2, 4]
    """
    # method='min' + ascending=False で competition ranking
    # 欠損（D-09）は NaN のまま（母集団除外・最下位固定しない）
    return series_desc.rank(method="min", ascending=False, na_option="keep")
```

### Pattern 4: 中間列 drop と FEATURE_COLUMNS allowlist（D-11/D-13 raw 別保持）

**What:** 第1段階の中間値（`field_strength_mean/median/...`・race_id group 内 raw 値）は feature_matrix に出力せず・`rolling_field_strength_*` のみ残す。FEAT-03 rank/gap も計算後は speed_index の raw 値（`rolling_speed_figure_mean_5` 等）は別 feature として保持し続け（D-11 raw rank/profile と別保持）・`field_strength_adjusted_rank` のみ追加。Step 7b（09-01-PLAN.md L625-627 idiom と対称）で `obs_id`・中間 opponent profile 列等を明示 drop する。

**When to use:** builder.py Step 7 終了後・§12.2 metadata stamp 前。

**Pitfall:** `assert_matrix_columns_registered` は「出力した feature が全て registry にある」方向の検査なので・drop すれば parity 維持（D-09.1-05 と同 idiom・出力しない feature があっても違反でない）。

### Anti-Patterns to Avoid

- **純粋ループ（`for source_race in races: for opp in opponents:`）**: 6.7M ペアで数十分の低速化・必ず pandas groupby + vectorized で実装。
- **target/mean encoding 的な opponent 集約**: leak する（§14.3 禁止）。speed_figure float のみで測る。
- **未来情報の遡及注入**: source race の相手の「その後の」能力値を使う（再評価版）は D-01 で不採用・厳格版 `available_at < self.available_at` (strict `<`) を必ず適用。
- **race_id 内 rank に future information 混入**: target observation のみで計算・過去走には適用しない（D-07）。出馬表確定時点 `feature_cutoff_datetime` 基準・当日結果不使用。
- **categorical 扱いの新 feature**: rank/gap/field_strength は全て float/数値・LightGBM native categorical は既存（jockey_id 等）のみ。新 feature を categorical 化しない（D-09 NaN 保持は LightGBM native NaN で対応）。
- **tozaicd での発走馬判定**: live-DB 実証で EveryDB2 独自拡張（1/2 が大多数の完走馬・3/4 が中止/失格）・JRA-VAN 公式仕様（0/1/2）と異なる・意味不明。`kakuteijyuni > 0` を使う。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PIT as-of join | 自前 `<` filter 実装 | `_pit_cutoff_prefilter` / `merge_asof(direction='backward')` (既存・rolling.py/speed_figure.py と対称) | adversarial test が monkeypatch で guard 無効化し lookahead 検出・既存不変量 CUTOFF_SEMANTICS と単一真の源 |
| latest-K rolling | 自前 window 集約 | `build_rolling_features` + `_ROLLING_SYSTEMS` 拡張 | obs_id group・strict `<cutoff`・byte-reproducible・CYCLE-2 HIGH#1 cross-obs leak 回避・17 feature と対称 |
| byte-reproducible Parquet | 自前書込 | `snapshot.py::write_snapshot` (FIXED_REPRODUCE_TS・SHA256・metadata 除外) | §19.1 聖域・2回 build で SHA256 一致・test_byte_reproducible で機械保証 |
| registry parity 検査 | 自前列チェック | `assert_matrix_columns_registered` + `feature_availability.yaml` | HIGH#3 fake-green 防止・banned alias sneak-in 構造排除 |
| adversarial AST audit | 自前 grep | `_FORBIDDEN_TOKENS` AST Name/Attribute/Constant 検査 (test_audit_speed_figure.py 鋳型) | docstring/comment の "odds-free" false positive 回避・SAFE-01 静的証明 |
| SC#5 評価 metrics | 自前 Brier/LogLoss 算出 | `evaluator.py::compute_metrics` + `check_acceptance_gate` | §15.2 事前登録指標不変・D-04 binning 契約固定・bit-identical |
| competition ranking | 自前 rank ループ | `pandas.Series.rank(method="min", ascending=False, na_option="keep")` | D-10 "1224" 方式・vectorized・D-09 NaN 保持 |

**Key insight:** 全ての基盤プリミティブは Phase 9/9.1 で確立済み。本 Phase は「既存 idiom をどう組み合わせて拡張するか」に集約され・新規アルゴリズムは極小（competition ranking のみ pandas 標準 API で対応）。core value「リーク防止」は既存の strict `<` / `merge_asof(direction='backward')` / adversarial audit の再利用で機械保証される。

## Common Pitfalls

### Pitfall 1: tozaicd による発走馬判定の誤り（D-04 核心・live-DB 実証済）

**What goes wrong:** CONTEXT.md の D-04 で「`datakubun` / 取消・除外・発走除外・競走中止ステータス」とあるが・normalized.n_uma_race に `datakubun` カラムは存在しない（information_schema・staging-swap DDL `_UMA_RACE_COLUMNS` 精査済）。`tozaicd` は存在するが・実データの分布が JRA-VAN 公式仕様（0/1/2）と異なり EveryDB2 独自拡張（1/2 が大多数の完走馬・3=競走中止190件・4=失格16件・2023+ 実証）で意味不明。

**Why it happens:** EveryDB2 が JV-Data の別フィールドを `tozaicd` にマージしている可能性。CONTEXT.md の記述は要件定義書の汎用記述に基づき・実装の実態を精査する前の仮置き。

**How to avoid:** 発走馬特定は `kakuteijyuni > 0` の単一条件で機械的確定（live-DB 実証：time=0 かつ kakuteijyuni>0 は0件・time=0 と kakuteijyuni=0 が1516件完全一致＝未発走）。競走中止/失格馬（tozaicd=3/4）は kakuteijyuni=11-16 等の大型番号を持つので「発走済み」と判定され D-04 原則「競走中止馬は含む」と整合。`tozaicd`・`datakubun` は使わない。

**Warning signs:** `tozaicd='1'` で発走馬を除外すると8万件の完走馬を落とす（致命的 data loss）。分布を必ず live-DB で確認してから実装。

### Pitfall 2: 相手強度計算の計算量爆発

**What goes wrong:** D-02「相手の当時 rolling 能力」を各 (target, source_race, opponent) トリプルで計算すると・history 48万行 × 平均14相手 × latest-K rolling で数千萬ペアになり・純粋 Python ループで数十分〜時間単位の低速化。

**Why it happens:** pandas の `iterrows` や `for race in races:` のネストループは C 実装の groupby に比べ100倍以上遅い。

**How to avoid:** per-source-race batch + vectorized groupby で実装。相手 rolling 能力の latest-K は `sort_values + groupby.head(K)` で vectorized（既存 rolling.py L378-383 idiom）。source race 内 profile 集約は `groupby(["race_nkey", "kettonum"]).agg(...)` で一括（top-k は `nlargest` で vectorized）。

**Warning signs:** builder の Step 5c が build 全体の 80% 以上の時間を占める・cProfile で Python ループが hot spot。

### Pitfall 3: D-01 厳格版 as-of の PIT 違反

**What goes wrong:** 相手の rolling 能力計算で source race 以降の相手の走（未来情報）を混入させる・または source race 当日の他馬の結果（同着等）を相手能力に使う。

**Why it happens:** 「source race 時点の相手の強さ」を測る際・source race の確定着順や speed_figure（当日結果）を使うと未来情報リーク。厳格版 D-01 は「opponent.available_at < self.available_at (source race の available_at)」の strict `<` を要求。

**How to avoid:** 相手 rolling 能力計算時に `opponent.available_at < source_race.available_at` (strict `<`) を明示適用（`_pit_cutoff_prefilter` と同一不変量）。adversarial test（`tests/audit/test_audit_field_strength.py`）が monkeypatch で guard を `<=` に差し替え・T+1 opponent データ混入を検出するテストを必ず追加（test_audit_features.py L鋳型）。

**Warning signs:** unit test で source race と同日の相手 speed_figure が rolling に混入・ adversarial lookahead test が RED。

### Pitfall 4: FEAT-03 の過去走への誤適用

**What goes wrong:** レース内相対特徴量（rank/gap）を過去走にも適用してしまう・または target race の当日結果（確定着順・確定 speed_figure）を rank 母集団に混入。

**Why it happens:** rolling feature の idiom（過去走に適用）と混同しやすい。

**How to avoid:** FEAT-03 は **target observation のみ**（D-07 明示）・race_id group-by は target feature_matrix 上でのみ実行。target race の rank 母集団は「出馬表確定時点 `feature_cutoff_datetime` で知っている各馬の rolling_speed_figure_mean_5 等」のみ（当日結果不使用）。speed_index 欠損馬（D-09）は NaN のまま母集団除外。

**Warning signs:** feature_matrix の行数が target observations 数（~4.7万件/年）でなく history 行数（~48万件）になる・または target race の確定着順が rank 計算に混入。

### Pitfall 5: Parquet 直列化失敗（object dtype + sentinel）

**What goes wrong:** 新 feature を object dtype + `__MISSING__` sentinel で出力し PyArrow が ArrowTypeError で直列化失敗。

**How to avoid:** 既存 `snapshot.py::_coerce_rolling_columns_for_parquet` が `rolling_*` prefix 列を nullable Float64 に変換する仕組みを踏襲（rolling_field_strength_* は自動対象）。FEAT-03 の rank/gap 列は `rolling_` prefix でないため・`_is_categorical_rolling_col` の対象外・別途 nullable Float64 扱いを builder 側で保証（sentinel → NaN）。memory `feature-snapshot-regen-required`: unit test 後に必ず live-DB で snapshot 再生成検証（実データでしか発覚しない Parquet 直列化 bug あり）。

**Warning signs:** unit test は GREEN だが `run_feature_build.py` で ArrowTypeError・`feature-snapshot-regen-required` memory の指摘事項。

### Pitfall 6: additive score 係数の test 窓すり替え（D-12/§11.2 聖域）

**What goes wrong:** `field_strength_adjusted_rank` の係数候補 `{0.0, 0.1, 0.25, 0.5}` を test 窓の結果を見て選び直す・過学習聖域違反。

**How to avoid:** 係数候補集合と選定指標を Plan 時点で事前登録（D-12）・感度分析は train/calib 窓内のみ。0.25 を canonical 初期値として事前登録し・test 窓では canonical のみで評価（候補別評価は参考記録として残すが test 窓選び直し禁止）。

## Code Examples

### compute_field_strength_profile（D-06 第1段階・新モジュール）

```python
# Source: 既存 rolling.py L209-382 build_rolling_features + speed_figure.py L566 compute_speed_figure_for_history
#         の idiom 合成・PIT 保証は既存 _pit_cutoff_prefilter と同一不変量

from src.features.availability import CUTOFF_SEMANTICS
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"

# D-05: top-k クランプ
def _topk_mean_clamped(values: pd.Series, k: int) -> float:
    """top-k mean・k = min(k, valid_opponents) でクランプ（D-05）。"""
    valid = values.dropna()
    if len(valid) == 0:
        return float("nan")
    actual_k = min(k, len(valid))
    return float(valid.nlargest(actual_k).mean())

def compute_field_strength_profile(
    history: pd.DataFrame,
    observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """D-06 第1段階: history 全行に source race 内 opponent profile（8値）を付与。

    PIT 保証（D-01 厳格版）: 各 opponent の rolling 能力は
    opponent.available_at < source_race.available_at (strict <) を満たす
    opponent 過去走のみで算出。source race 当日結果は混入しない。

    入力: compute_speed_figure_for_history の戻り値
        - 各 history 行に speed_figure / available_at / race_nkey / kettonum 付与済
    出力: history に 8 列（field_strength_{mean,median,top3_mean,top5_mean,max,sd,valid_count,coverage}）を copy 追加
    """
    # 1. 発走馬特定（D-04・live-DB 実証済: kakuteijyuni > 0）
    starters_mask = history["kakuteijyuni"].fillna(0) > 0
    starters = history[starters_mask].copy()
    # source race size（coverage 計算用）
    race_size = starters.groupby("race_nkey").size().to_dict()

    # 2. per-source-race batch: starter × starter join（self 除く）
    #    opponent の当時 rolling ability を vectorized で算出
    #    ※ 詳細な vectorized 実装は PLAN で詰める（計算量 core・Pitfall 2 参照）

    # 3. opponent profile 8値（D-03）を groupby(["race_nkey", "kettonum"]) で集約
    #    coverage = valid_count / race_size[race_nkey]

    # ... (実装詳細は PLAN)
    pass
```

### competition ranking（FEAT-03・D-10・pandas 標準 API）

```python
# Source: pandas.Series.rank 公式 API・method='min' で competition ranking
# CITED: https://pandas.pydata.org/docs/reference/api/pandas.Series.rank.html

def speed_index_rank_within_race(
    feature_matrix: pd.DataFrame,
    speed_index_col: str,  # "rolling_speed_figure_mean_5" / "best2_mean_5" / "median_5"
    rank_col: str,         # "speed_index_rank_mean5" 等
) -> pd.Series:
    """race_id 内の competition ranking（min rank・"1224" 方式・D-10）。

    D-09: speed_index 欠損馬は NaN 保持・母集団除外（na_option="keep"）。
    D-07: target observation のみ・race_id（race_nkey）group-by。
    """
    return feature_matrix.groupby("race_nkey")[speed_index_col].transform(
        lambda s: s.rank(method="min", ascending=False, na_option="keep")
    )
```

### field_strength_adjusted_rank（D-11 additive score）

```python
# Source: D-11 決定・additive score（正の補正）
# 係数候補 {0.0, 0.1, 0.25, 0.5} は train/calib 窓内のみ感度分析（D-12）

ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5)
ADJUSTED_RANK_COEF_CANONICAL = 0.25  # D-12 事前登録 canonical 初期値

def field_strength_adjusted_score(
    feature_matrix: pd.DataFrame,
    *,
    mean5_col: str = "rolling_speed_figure_mean_5",
    fs_mean5_col: str = "rolling_field_strength_mean_mean_5",
    coef: float = ADJUSTED_RANK_COEF_CANONICAL,
) -> pd.Series:
    """D-11: additive score = mean5 + coef * field_strength_mean_mean_5。

    係数は正（強い相手と走ってきた馬をボーナス評価）・差/比は不採用。
    欠損馬（D-09）はスコア NaN・母集団除外。
    """
    return feature_matrix[mean5_col] + coef * feature_matrix[fs_mean5_col]

# 候補別の score 計算（train/calib 窓内のみ・test 窓選び直し禁止 D-12）
#   for coef in ADJUSTED_RANK_COEF_CANDIDATES:
#       score = field_strength_adjusted_score(..., coef=coef)
#       rank = score.groupby("race_nkey").transform(...)
#   → train/calib 窓で感度分析・最終 feature_matrix には coef=0.25 canonical の rank のみ出力
```

### builder.py Step 5c/5d/7 挿入（09-01-PLAN.md Step 5b idiom と対称）

```python
# Source: builder.py L516-627 Step 5b speed_figure + Step 6 推定脚質 idiom の対称拡張

# --- Step 5c: 相手強度 field_strength profile 計算（D-06 第1段階・新） ---
# Step 5b で history に speed_figure/available_at が揃った段階で呼出。
# copy-not-rename: history に field_strength_* profile 列を追加（既存列は破壊しない・HIGH#5 踏襲）。
from src.features.field_strength import compute_field_strength_profile
history = compute_field_strength_profile(history, observations=feature_matrix)

# --- Step 5d: 相手強度 latest-K rolling（D-06 第2段階・rolling.py 拡張で既存 build_rolling_features 内で処理） ---
# rolling.py の _ROLLING_SYSTEMS に "field_strength" を追加済みであれば・
# 既存 Step 5 build_rolling_features 呼出で rolling_field_strength_* 21 feature が自動生成される。
# ※ Step 5b→5c の順で history に profile 列が揃った後に Step 5 を呼ぶ必要がある点に注意・
#   既存 Step 5 の位置（L531-551）を Step 5c の後に移動する必要がある（builder 構成変更）。

# --- Step 7: レース内相対特徴量（FEAT-03・target-only・新） ---
# Step 6b で obs_id を drop する前・または race_nkey を使える段階で計算。
from src.features.race_relative import compute_race_relative_features
feature_matrix = compute_race_relative_features(feature_matrix)

# --- Step 7b: 中間列 drop（09-01-PLAN.md L625-627 と対称） ---
# field_strength profile 生値（field_strength_mean 等・rolling_ prefix 無し）は
# rolling_field_strength_* の計算用中間値・feature_matrix に出力しない。
feature_matrix = feature_matrix.drop(
    columns=[
        "obs_id",
        # field_strength profile 中間値（第1段階）・feature_matrix 本体に残るため明示 drop
        *[c for c in feature_matrix.columns
          if c.startswith("field_strength_") and not c.startswith("rolling_field_strength_")],
    ],
    errors="ignore",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 着順中心 rolling（`rolling_kakuteijyuni_*`） | 速度能力中心（`rolling_speed_figure_*` 17 feature）+ 相手強度（`rolling_field_strength_*` 21 feature）+ レース内相対（`speed_index_rank_*` 等 6 feature） | Phase 9 / 9.1 / 10 (2026-06) | 回収率0.65天井の「市場情報不足」層へ odds-free で正統対応（CLAUDE.md core value 再定式化・debug ROOT CAUSE 準拠） |
| target encoding 的な opponent 集約 | speed_figure float のみで測る opponent rolling 能力・LightGBM native categorical / CatBoost ordered TS 構造的適用 | Phase 9 / 10 (§14.3/§14.4) | target encoding leak 構造的回避・adversarial audit で静的証明 |
| 独立二値分類（v1.0 LightGBM） | レース内相対特徴量追加（Phase 10）→ レース内相対確率モデル（Phase 11 MODEL-01） | Phase 10 / 11 | 複勝の「相対競争」性質を特徴量層（P10）→ モデル層（P11）で段階表現 |

**Deprecated/outdated:**
- 過去人気/過去オッズ proxy の `p` モデル特徴量化: 市場回帰で edge 消滅・2AI リサーチ一致・要件定義書 Out of Scope（本 Phase でも厳禁・SAFE-01）
- `time/10.0` decisecond 誤認（Phase 9 09-01 bug）: `_decode_jra_time` MMSS.t エンコードで是正済（speed_figure 入力は正しい・本 Phase で再利用時も問題なし）
- tozaicd による発走馬判定: EveryDB2 独自拡張で意味不明・`kakuteijyuni > 0` を使う（本 Phase RESEARCH で実証）

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 発走馬特定は `kakuteijyuni > 0` の単一条件で機械的確定できる（live-DB 2023+ 実証：time=0 と kakuteijyuni=0 が1516件完全一致） | Pitfall 1 / 発走馬特定 | 低：live-DB で直接実証済・しかし全期間（2015-）で同様かは未検証・builder 実装時に全期間 assert を入れるべき |
| A2 | tozaicd は JRA-VAN 公式仕様（0/1/2）と異なり EveryDB2 独自拡張（1/2 が大多数の完走馬・3=競走中止・4=失格） | Pitfall 1 | 低：Web 検索で JRA-VAN 公式コード表確認 + live-DB 分布実証・意味の詳細は EveryDB2 側に問合せ必要だが発走馬判定には使わないので影響なし |
| A3 | 相手強度計算の計算量は history 48万行 × 平均14相手 = 約6.7M ペア・pandas vectorized で秒単位処理可能 | Pattern 1 / Pitfall 2 | 中：実際の latest-K rolling を含めると更に膨らむ可能性・cProfile で計測し必要なら DuckDB 補助か chunk 化を検討 |
| A4 | 新 feature 27 個（FEAT-02 21 + FEAT-03 6）は全て float/数値で categorical 性なし・LightGBM native NaN で D-09 欠損対応可能 | Anti-Patterns / FEAT-03 | 低：rank/gap/score は全て数値・sentinel 数値（magic number）を使わない方針（D-09）と整合 |
| A5 | field_strength_adjusted_rank の係数 0.25 は train/calib 窓内の感度分析で 0.0（baseline）との差が有意かは未検証・事前登録値として採用 | FEAT-03 / D-12 | 低：候補集合 {0.0, 0.1, 0.25, 0.5} を事前登録済・test 窓ですり替えない限り聖域違反なし・0.0 が baseline として効かない場合はモデルが無視できる（D-11 安全策） |
| A6 | builder.py の既存 Step 5 rolling 呼出位置を Step 5c の後に移動する構成変更が必要（field_strength profile が history に揃った後で rolling する必要があるため） | Pattern 4 / builder 拡張 | 中：構成変更は既存テスト（test_speed_figure_builder_integration.py 等）に影響・copy-not-rename と hardcode feature list 更新で対応 |

## Open Questions

1. **D-02 相手の「当時 rolling 能力」の具象化**
   - What we know: source race 時点 `available_at` 以前の相手の latest-K `speed_figure` profile（17 feature のいずれか）を使う・D-03 の profile 8値は「source race 内の opponent 集約」であって「相手個人の rolling」は別軸。
   - What's unclear: 相手個人の rolling は17 feature 全てか、canonical（mean_5・best2_mean_5 等）の一部か。計算量 viewpoint からは少なくしたいが情報量 viewpoint からは多い方がよい。D-02 は「rolling 安定能力 profile」と曖昧。
   - Recommendation: planner が PLAN 内で「相手個人の rolling は canonical の mean_5（Phase 9.1 D-09.1-01 踏襲）1軸のみ」と事前登録することを推奨（計算量抑制・feature 膨張抑制・rolling_speed_figure_mean_5 が Phase 9 D-09 の安定能力の代表値）。これにより field_strength_mean は「source race 内の opponent の mean_5 の平均」という明確な意味を持つ。もし17 feature 全てを使う場合は計算量が17倍膨らむ（6.7M × 17 = 1億ペア）ため非現実的。

2. **FEAT-03 gap_to_top/gap_to_3rd の "top/3位" の定義**
   - What we know: D-08 は「top/3位の mean_5 − self」・mean_5 主軸。
   - What's unclear: top は1位（max）・3rd は3位（median 的）か・competition ranking（D-10 同着）と整合するか・欠損馬が3位以下にどう影響するか。
   - Recommendation: planner が PLAN 内で「top = mean_5 降順1位（max）・3rd = 降順3位・同着は competition ranking で順位確定後・欠損馬は母集団除外（D-09）・出走馬 < 3 の場合は gap_to_3rd は NaN」と明文化すること。3位未満の出走馬（5-7頭）でも gap_to_3rd は意味を持つ（複勝払戻対象2頭でも相手強度評価として）。

3. **snapshot feature_snapshot_id 命名**
   - What we know: v1.0 `20260620-1a-postreview-v2` → Phase 9 `20260625-1a-speedfigure-v1` → Phase 9.1 `20260626-1a-speedprofile-v1` 系統。
   - What's unclear: Phase 10 の snapshot_id 文字列（`make_model_version` 形式）。
   - Recommendation: `20260626-1a-opponentstrength-v1`（Phase 9.1 完成日 same day・opponent strength の機能名・v1）を推奨。planner が決定。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (EveryDB2 normalized) | 発走馬特定の live-DB 精査・snapshot build | ✓ | 15.x (host Homebrew) | — |
| Python 3.12 / uv | runtime | ✓ | 3.12.13 / uv 0.11.21 | — |
| pandas / NumPy / PyArrow | feature 構築・snapshot | ✓ | 3.0.3 / ≥2.0 / 24.0.0 | — |
| LightGBM / CatBoost | SC#5 v1.0 LightGBM 再学習 | ✓ | 4.6.0 / 1.2.10 | — |
| pytest / ruff | test / lint | ✓ | 9.1.0 / 0.15.17 | — |

**Missing dependencies with no fallback:** なし（全て既存 v1.0/Phase 9/9.1 環境で完結）。

**Missing dependencies with fallback:** なし。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（`requires_db` marker・`KEIBA_SKIP_DB_TESTS` 環境変数で live-DB 必須テストを切替） |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`・testpaths=["tests"]・addopts="-ra") |
| Quick run command | `uv run pytest tests/features/test_field_strength.py tests/features/test_race_relative.py tests/features/test_rolling.py tests/audit/test_audit_field_strength.py -x -q` |
| Full suite command | `uv run pytest` （`KEIBA_SKIP_DB_TESTS` unset で live-DB 必須テスト含む全テスト）|

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FEAT-02 / D-01 厳格版 as-of | 相手 rolling 能力が source race 時点 `available_at` 以前のみで算出される・未来情報混入なし | unit + adversarial | `uv run pytest tests/features/test_field_strength.py::test_opponent_ability_pit_strict_less -x` + `tests/audit/test_audit_field_strength.py::test_lookahead_injection_detected` | ❌ Wave 0 |
| FEAT-02 / D-04 発走馬特定 | `kakuteijyuni > 0` のみを opponent に含める・未発走馬（kakuteijyuni=0）は除外・競走中止馬（kakuteijyuni=11-16）は含む | unit | `uv run pytest tests/features/test_field_strength.py::test_starter_identification -x` | ❌ Wave 0 |
| FEAT-02 / D-03 profile 8値 | source race 内 opponent profile 8値（mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）が正しく算出される・top-k クランプ（D-05）動作 | unit | `uv run pytest tests/features/test_field_strength.py::test_profile_8vals -x` | ❌ Wave 0 |
| FEAT-02 / D-06 第2段階 21 feature | target 馬の過去走 profile が latest-K rolling で集約され 21 feature が生成・sentinel/count ルール（D-09.1-01/03 と対称） | unit | `uv run pytest tests/features/test_rolling.py::test_field_strength_rolling_21_features -x` | ❌ Wave 0 |
| FEAT-03 / D-07 rank 3軸 | race_id 内 competition ranking（D-10）が mean_5 / best2_mean_5 / median_5 の3軸で算出・target のみ | unit | `uv run pytest tests/features/test_race_relative.py::test_speed_index_rank_3axes -x` | ❌ Wave 0 |
| FEAT-03 / D-08 gap_to_top/3rd | mean_5 主軸・top/3位との差・欠損馬は母集団除外（D-09） | unit | `uv run pytest tests/features/test_race_relative.py::test_gap_to_top_3rd -x` | ❌ Wave 0 |
| FEAT-03 / D-10 competition ranking | 同着が "1224" 方式（min rank）で同順位・次は飛ぶ | unit | `uv run pytest tests/features/test_race_relative.py::test_competition_ranking_ties -x` | ❌ Wave 0 |
| FEAT-03 / D-11/D-12 adjusted_rank | additive score（mean5 + 0.25*fs_mean5）の race_id 内 rank・候補 {0.0,0.1,0.25,0.5} は train/calib 窓のみ | unit | `uv run pytest tests/features/test_race_relative.py::test_adjusted_rank_additive_score -x` | ❌ Wave 0 |
| SAFE-01 / odds-free proxy 排除 | field_strength.py / race_relative.py ソースの AST に odds/ninki/fukuodds/ninkij/tansyouodds の Name/Attribute/Constant が0件 | adversarial | `uv run pytest tests/audit/test_audit_field_strength.py::test_odds_proxy_ast_clean -x` | ❌ Wave 0 |
| SC#3 / byte-reproducible | 同一 DataFrame で SHA256 一致・FIXED_REPRODUCE_TS 不変 | unit + live-DB | `uv run pytest tests/features/test_snapshot_repro.py -x` (既存・拡張) | ✅ (既存・27 feature 追加で再実行) |
| SC#3 / registry↔Parquet parity | `assert_matrix_columns_registered` GREEN・schema_version 0.6.0 | unit | `uv run pytest tests/features/test_allowlist.py -x` (既存・拡張) | ✅ (既存・27 feature 追加で再実行) |
| SC#5 非劣化 gate | Brier/LogLoss/AUC が Phase 6 D-07 水準（0.15222/0.47488/0.73230）の許容幅内（D-16・事前登録） | live-DB + evaluation | `uv run python scripts/run_phase10_evaluation.py` (新規・scripts/run_speed_figure_stopgate.py 鋳型) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/features/test_field_strength.py tests/features/test_race_relative.py tests/features/test_rolling.py tests/audit/test_audit_field_strength.py -x -q`（quick・合成データ・DB 不要）
- **Per wave merge:** `uv run pytest`（`KEIBA_SKIP_DB_TESTS=1` で live-DB 必須テストを skip した全テスト）
- **Phase gate:** `KEIBA_SKIP_DB_TESTS` unset で live-DB フルスイート GREEN + `run_feature_build.py` で snapshot 再生成 + SHA256 一致 + SC#5 非劣化 gate PASS

### Wave 0 Gaps
- [ ] `tests/features/test_field_strength.py` — FEAT-02 第1段階 profile・PIT strict <・発走馬特定・profile 8値・top-k クランプ unit test
- [ ] `tests/features/test_race_relative.py` — FEAT-03 rank 3軸・gap・competition ranking・adjusted rank・欠損馬除外 unit test
- [ ] `tests/audit/test_audit_field_strength.py` — AST odds/ninki proxy 排除・lookahead 注入（`_pit_cutoff_prefilter` monkeypatch）adversarial
- [ ] `tests/features/test_rolling.py` 拡張 — `rolling_field_strength_*` 21 feature unit test（median/best2/trend/sentinel ルール）
- [ ] `tests/features/test_speed_figure_builder_integration.py` hardcode feature list 更新 — 27 新 feature 追加（feature_count 79 → 106 想定）
- [ ] `tests/audit/test_audit_speed_figure.py` hardcode feature list 更新 — Phase 10 feature 追加（SAFE-01 検査対象拡張）
- [ ] `scripts/run_phase10_evaluation.py` 新規 — SC#5 非劣化 gate（v1.0 baseline vs Phase 10 snapshot 3-way 比較・run_speed_figure_stopgate.py 鋳型）

## Security Domain

`security_enforcement: true`（config.json）・`security_asvs_level: 1`。本 Phase は feature 構築層（PII 不保持・外部入力なし）だが・core value「リーク防止」が security と同等の重要性を持つ。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A（local Streamlit・Phase 7 で完結・本 Phase は feature 構築） |
| V3 Session Management | no | N/A |
| V4 Access Control | yes（readonly DB role） | `make_pool(role='readonly')`（search_path=public・raw 読取専用・REVIEWS HIGH#4 REVOKE）・builder は readonly pool のみ使用 |
| V5 Input Validation | yes | `kakuteijyuni > 0` による発走馬特定（live-DB 実証済・境界値明示）・`pd.to_numeric(errors='coerce')` で不正値 NaN 化・`assert` で必須列検証 |
| V6 Cryptography | no | N/A（暗号化不要・SHA256 は byte-reproducibility 用で機密性でない） |
| V7 Error Handling | yes | fail-loud 原則（`raise ValueError` / `RuntimeError`）・silent NaN fill 禁止・`__MISSING__` sentinel で未観測明示 |
| V9 Data Protection | yes（core value） | **odds-free 原則（SAFE-01）**: オッズ/人気/過去人気/過去オッズ proxy は feature に一切入れない・adversarial AST audit で静的証明 |
| V14 Configuration | yes | `feature_availability.yaml` registry が single source of truth・`assert_matrix_columns_registered` で fail-loud・banned source 構造排除 |

### Known Threat Patterns for feature construction / leak prevention

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Lookahead leak（未来情報の特徴量混入） | Tampering / Elevation of privilege | `_pit_cutoff_prefilter` (strict `<`) + `merge_asof(direction='backward')`・adversarial test が monkeypatch で guard 無効化し T+1 データ混入を検出 |
| Target encoding leak（categorical の target 平均入り encoding） | Tampering | LightGBM native categorical（Fisher optimal partition・split-finder は target 不可）・target/mean encoding 構造的禁止（§14.3）・新 feature は全て float/数値 |
| Cross-observation leak（同一 horse の複数 observation で window 共有） | Tampering | `obs_id` (= race_nkey, kettonum) group・CYCLE-2 HIGH#1・per-observation independent window |
| Market regression（odds proxy で edge 消滅） | Information disclosure | odds-free 原則（SAFE-01）・`_FORBIDDEN_TOKENS` AST 検査・test_audit_field_strength.py で odds/ninki proxy 0件を静的証明 |
| Row-misalignment（rolling 結果の誤 observation 割当） | Tampering | canonical key merge（`race_nkey` + `kettonum` または `obs_id`）・位置 concat 禁止（CR-01） |
| Silent data loss（空 history / 0行結果が silent に sentinel 化） | Denial of service | fail-loud（`RuntimeError` for empty history/obs・WR-01/WR-02）・`assert` で必須列検証 |
| Reproducibility drift（run 毎に SHA256 変動） | Tampering | `write_snapshot` FIXED_REPRODUCE_TS + 決定論的 PyArrow 書込（use_dictionary=False・row_group_size=100_000）・SHA256 は metadata 除外 schema bytes のみ |
| Post-evaluation selection（test 窓結果を見た閾値すり替え） | Elevation of privilege | D-12/D-16 事前登録・§11.2 聖域・`adjusted_rank` 係数候補は train/calib 窓のみ・test 窓は canonical(0.25) のみ評価 |

## Sources

### Primary (HIGH confidence・live-DB 実証 + 既存コード idiom)
- `src/features/speed_figure.py` `compute_speed_figure_for_history` — 相手強度計算の入力素材（history に speed_figure/available_at/race_nkey/kettonum/surface/time_sec を付与済）・PIT 保証は `_pit_cutoff_prefilter` (strict `<`)
- `src/features/rolling.py` `build_rolling_features` + `_ROLLING_SYSTEMS` + `_SPEED_FIGURE_AXES` — per-observation latest-K algorithm・obs_id group・strict `<cutoff`・第2段階 latest-K rolling の直接の拡張先
- `src/features/builder.py` `build_feature_matrix` Step 1-9 — copy-not-rename・FEATURE_COLUMNS allowlist・obs_id idiom・Step 6b drop
- `src/features/snapshot.py` `write_snapshot` — §12.4 metadata 9 keys・SHA256（metadata 除外）・FIXED_REPRODUCE_TS・`_coerce_rolling_columns_for_parquet`
- `src/features/availability.py` `assert_matrix_columns_registered` + `CUTOFF_SEMANTICS` + `_ROLLING_SYSTEMS_FOR_RESERVED` — registry parity・strict `<` 単一不変量
- `src/model/evaluator.py` `compute_metrics` + `check_acceptance_gate` — §15.2 事前登録指標（Brier/LogLoss/AUC）・D-04 binning 契約固定
- `src/model/data.py` `_derive_feature_columns` — registry から動的 FEATURE_COLUMNS 導出（snapshot_id 指定・REVIEW H1）・`make_X_y` 完全一致 assert
- `src/audit/report.py` + `tests/audit/test_audit_speed_figure.py` — AST Name/Attribute/Constant 検査・`_FORBIDDEN_TOKENS`・lookahead 注入 adversarial
- live-DB 実証（2026-06-26・normalized.n_uma_race year>=2023）: `tozaicd` 分布（1=79766・2=85317・3=190・4=16）・`kakuteijyuni=0` と `time=0` が1516件完全一致・発走馬特定は `kakuteijyuni > 0` で確定
- live-DB 実証: history 規模（483,862行・34,553レース・平均14馬）・target 2024年観測規模（46,752行・3,454レース）

### Secondary (MEDIUM confidence・Web 検索 + 公式ドキュメント参照)
- JRA-VAN JV-Data コード表（`JV-Data490.xlsx`） — 取消区分 TozaiCd 公式仕様は 0/1/2 の3値（0=レコード削除・1=出走取消・2=競走除外）・競走中止/失格は別レコード区分・EveryDB2 実装は独自拡張（分布異なる） `[CITED: https://jra-van.jp/dlb/sdv/sdk/JV-Data490.xlsx]`
- pandas `Series.rank` 公式 API — `method='min'` で competition ranking（同着同順位・"1224" 方式）・`na_option='keep'` で欠損 NaN 保持 `[CITED: https://pandas.pydata.org/docs/reference/api/pandas.Series.rank.html]`
- pandas `merge_asof(direction='backward')` — PIT as-of join プリミティブ・CLAUDE.md §3 で仕様化 `[CITED: https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html]`
- CONTEXT.md / ROADMAP.md / REQUIREMENTS.md / PROJECT.md — Phase 10 境界・FEAT-02/FEAT-03/SAFE-01・D-01〜D-16 ロック決定

### Tertiary (LOW confidence・training knowledge・要検証)
- 相手強度計算の vectorized 実装の詳細アルゴリズム — per-source-race batch + groupby の組み合わせで6.7M ペアを秒単位処理可能という見積もりは training knowledge に基づく・PLAN で実装時に cProfile 検証が必要 `[ASSUMED]`
- additive score 係数 0.25 が適切な初期値か — Phase 9.1 D-09.1-01 の weight 係数等との整合は未検証・train/calib 窓で感度分析後に確定 `[ASSUMED]`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 要件固定（§17.1）・pyproject.toml で実証済・新規依存関係なし
- Architecture: HIGH — 踏襲 idiom 完全特定（speed_figure.py・rolling.py・builder.py・snapshot.py・availability.py）・09-01-PLAN.md / 09.1-01-PLAN.md で直接の先例あり
- 発走馬特定: HIGH — live-DB 実証済（`kakuteijyuni > 0` で機械的確定）・JRA-VAN 公式仕様と EveryDB2 実装の差も Web 検索で確認
- 計算量見積もり: MEDIUM — 数値オーダーは live-DB で実証・vectorized 実装の実速度は未検証（PLAN で cProfile 必要）
- 相手能力の rolling 定義（D-02 の具象）: MEDIUM — CONTEXT.md で「rolling 安定能力 profile」と曖昧・planner が PLAN 内で mean_5 1軸に事前登録することを推奨

**Research date:** 2026-06-26
**Valid until:** 2026-07-26（30日・stable domain・既存コード idiom と要件固定なので長期間有効・ただし planner は Open Questions #1/#2 の事前登録を必須とする）
