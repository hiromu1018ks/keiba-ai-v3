# Phase 10: Opponent Strength & Race-Relative Features - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 9 のスピード指数（`speed_figure` float・`available_at` 付き・par/variant 補正済み）と Phase 9.1 の 17-feature speed ability profile を前提に、**odds-free・PIT-safe** に以下を feature snapshot へ追加する（FEAT-02 + FEAT-03）:

1. **相手強度 `field_strength`（FEAT-02）** — target 馬の各過去走について、同じ source race に発走した相手の「当時の rolling 安定能力」から source race 単位の能力分布（profile 8値）を計算し、target 馬の過去走にわたり latest-K rolling で集約した特徴量。低着順でも強い相手なら価値があることを反映。
2. **レース内相対特徴量（FEAT-03）** — `speed_index_rank`（3軸）/ `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`。race_id 単位・出馬表確定時点 `feature_cutoff_datetime` 基準で、出走馬内の順序付けを future-information なしで確定する。複勝の「相対競争・各馬独立事象でない」性質を特徴量層で表現。

**SAFE-01（オッズ/人気/過去人気/過去オッズ proxy 排除）** を厳守。入力 snapshot は `20260626-1a-speedprofile-v1`（features=79・Phase 9.1 完成）・Phase 10 後の speed profile 差し込み禁止（ROADMAP・聖域）。

**Phase 10 が届けないもの（別 Phase）:** レース内相対確率モデル（MODEL-01・Phase 11）・`p_lower` EV・正規 falsification test（Phase 12 EVAL-02）・same_surface/same_distance_bucket の相手強度版（speed 側で既存のため本 Phase では重複させない）。

</domain>

<decisions>
## Implementation Decisions

### 相手強度 field_strength の定義（FEAT-02・SC#1 必須決定）

- **D-01:** **as-of 厳格版**を採用。各過去走の source race 時点 `available_at` で存在する相手の能力のみ使用する（当時の相手の強さを正確に反映・PIT の最も厳しい解釈・adversarial lookahead テスト GREEN・core value「リーク防止最優先」と整合）。**再評価版（cutoff 時点の相手能力）・両方比較は採用しない**。
- **D-02:** 相手の能力の測度は**相手の当時の rolling 安定能力**（source race 時点 `available_at` までの latest-K `speed_figure` profile）。source race での単発 `speed_figure` でなく安定能力で測る（信号強度優先・計算コスト高は researcher が vectorized 設計）。
- **D-03:** source race 内の相手集約は **mean 単独でなく field_strength profile（8値）**: `mean` / `median` / `top3_mean` / `top5_mean` / `max` / `sd` / `valid_count` / `coverage`。canonical は `mean`・profile 全体を特徴量候補にする（Phase 9.1「単一代表値に潰さない」方針の踏襲・情報を削らない）。
- **D-04:** 相手の範囲は**実際に発走した馬のみ**。除外・取消・発走除外等の未発走馬は相手から除外する。**競走中止馬は発走済みなので相手に含む**（rolling 能力が取得できる限り）。原則「実際に発走した馬を相手に含める・未発走馬は除外・競走中止馬は含める」。発走馬の特定は researcher が live-DB で `datakubun` / 取消・除外・発走除外・競走中止ステータス / `is_model_eligible`（§7.2）/ refund accounting と照合して決定する。
- **D-05:** top-k 集約（`top3_mean`/`top5_mean`）は `k = min(k, valid_opponents)` でクランプする。`valid_count` / `coverage` を**必ず保持**し相手数不足時の信頼度を担保する（Phase 9.1 count/sentinel 方針の拡張）。
- **D-06:** **2段階集約構造**。第1段階: source race 内で self を除いた相手の当時 rolling 能力から field_strength profile（8値中間値）を作る。第2段階: target 馬の過去走に紐づく profile を v1.0 rolling algorithm（`available_at < feature_cutoff_datetime`・strict `<`）で latest-K 集約して target row の最終特徴量にする。

### レース内相対特徴量（FEAT-03・SC#2 必須決定）

- **D-07:** `speed_index_rank` は **3軸**（`rolling_speed_figure_mean_5` / `best2_mean_5` / `median_5`）それぞれで race_id 内 rank を作成する（Phase 9.1 拡張意図の踏襲・単一代表値に潰さない）。各 rank は1セット。FEAT-03 は **target observation のみ**（出馬表確定時点 `feature_cutoff_datetime` 基準・各 target row で1回計算・過去走には適用しない）。
- **D-08:** `gap_to_top` / `gap_to_3rd` は **`mean_5` 主軸**（canonical）・**指数 point 差**（`top/3位の mean_5 − self`・速い馬との能力差・Phase 9 D-05 float 指数をそのまま・adversarial audit で透明）。gap の計算は mean_5 の1セットのみ（feature 膨張抑制）。秒差（`points_per_second` 逆変換）・race 内 z-score は採用しない。
- **D-09:** speed_index 欠損馬（デビュー戦・`speed_figure` 計算不可等）は **NaN 保持・母集団除外**。欠損馬を rank/gap 計算の母集団から除外し・自身の rank/gap は NaN とする（Phase 9 D-11 sentinel/nullable 踏襲・LightGBM native NaN 処理）。最下位固定・sentinel 数値（magic number）は採用しない。
- **D-10:** 同着は **competition ranking（min rank・同着は同順位・"1224" 方式）** で明文化する（Claude 裁量・SC#2「同着の境界処理が明文化される」要件を満たす）。
- **D-11:** `field_strength_adjusted_rank` は**差/比でなく additive score（相手強度を正の補正として加える）**で定義する。canonical: `field_strength_adjusted_score = rolling_speed_figure_mean_5 + 0.25 * rolling_field_strength_mean_mean_5` を race_id 内で score 降順 rank にする。主能力は `speed_index`(mean_5) を優先し・field_strength は補助ボーナスに留める。**差（index − field_strength）・比（index / field_strength）は不採用**（いずれも強い相手と走ってきた馬を不当に下げるため）。欠損馬は score/rank を NaN・母集団除外。raw の `speed_index_rank` と field_strength profile/rank は**別特徴量として保持**し・composite が効かない場合はモデルが無視できるようにする（冗長性による安全策）。
- **D-12:** additive score の係数は **0.25 を事前登録 canonical 初期値**とし・候補集合 `{0.0, 0.1, 0.25, 0.5}` で **train/calib 窓内のみ**感度分析する（`0.0` は raw `mean_5` rank と同値なので baseline として必須）。**test 窓で係数を選び直すのは禁止**（§11.2 聖域）。Plan 時点で候補集合と選定指標を明記する。

### field_strength 集約（target feature 化・D-06 第2段階の具体形）

- **D-13:** target 馬の過去走の field_strength profile を latest-K rolling で集約した feature は **21 feature**（rich but bounded）:
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_latest_1`（6）
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max}_mean_3`（5）
  - `rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_mean_5`（6）
  - `rolling_field_strength_mean_trend_last_minus_mean5` / `_trend_mean3_minus_mean5`（2）
  - `rolling_field_strength_valid_count_mean_5` / `coverage_mean_5`（2）
- **D-14:** **same_surface / same_distance_bucket は Phase 10 では入れない**。相手強度は過去レースの field quality であり・target の条件適性は speed profile 側（Phase 9.1）で既に表現しているため・field_strength 側に条件適性を重複させない（feature 膨張抑制）。欠損は NaN・`count`/`coverage` で信頼度を明示する。

### SC#5 評価方針（feature ノイズ化の回帰検知）

- **D-15:** **中間**（SC#5 非劣化必須 gate + 投票層参考記録）。Brier/LogLoss/AUC が Phase 6 D-07 水準（Brier=0.15222/LogLoss=0.47488/AUC=0.73230）を悪化させないことを**必須 gate**とする。`selected-only calibration` / `odds_band×p_bin` を**参考記録**（Phase 12 EVAL-01 の先行指標として見える化）。**residual proxy・正規 falsification test は Phase 12 EVAL-02 に委譲**（Phase 9 D-12 と同方針・重複回避）。Phase 9 stop gate（4指標 + residual proxy による go/no-go）は不採用（Phase 10 は feature 追加段階・MODEL-01 前で・改善期待には早い）。
- **D-16:** 非劣化の**許容幅（Brier/LogLoss/AUC 各）と pass/fail ルールは planner が Plan 内で事前登録**する（Phase 10 の実装内容・サンプル数・BT窓・Phase 11 SC#2 の非劣化マージンとの整合を見て決定・候補例: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005 程度）。**評価結果を見た後に変更しない**（§11.2 聖域）。

### Claude's Discretion

- **発走馬特定の実装** — `datakubun` / 取消・除外・発走除外・競走中止ステータスの正規化層素材を researcher が live-DB で精査（D-04 原則の機械的実現・`is_model_eligible`/refund と整合）。
- **相手の当時 rolling の vectorized 実装** — 各過去走の各相手について source race 時点での rolling を計算する計算量の多い処理（全レースループ vs expanding as-of vs per-source-race batch）。researcher/planner が効率化方針を決定。
- **モジュール構成・`compute_field_strength` 配置** — 新モジュール（`src/features/field_strength.py` 等）か `speed_figure.py`/`rolling.py` 拡張か。planner が既存 idiom と整合する形で決定。
- **`builder.py` 拡張** — 新 Step（Step 5c 相手強度・Step 7 レース内相対等）の挿入位置・obs_id idiom 踏襲・Step 6b での中間列 drop。planner が Phase 9 Step 5b idiom と整合させ決定。
- **snapshot `feature_snapshot_id` 命名・`schema_version`** — v1.0 `20260620-1a-postreview-v2` → Phase 9 `20260625-1a-speedfigure-v1` → Phase 9.1 `20260626-1a-speedprofile-v1` 系統の継承（`make_model_version` 形式整合）・`feature_availability.yaml` schema_version 0.5.0 → 次。planner が v1.0 踏襲で決定。
- **`feature_count` 最終値・registry↔Parquet parity** — 21 field_strength feature + FEAT-03 feature（rank 3 + gap 2 + adjusted_rank 1 = 6）+ 監査列の合計。`_ROLLING_SYSTEMS` / `feature_availability.yaml` / registry 3者 parity（`assert_matrix_columns_registered`）。
- **trend / coverage / top-k 集約の境界数値** — `count`/`coverage` の sentinel 閾値・trend 軸の window 埋込命名（Phase 9.1 idiom 踏襲）。
- **非劣化マージン数値（D-16）** — planner が Phase 11 SC#2 事前登録マージンと整合して決定。
- **stop gate 相当の比較表示** — D-15 で gate は非劣化のみだが・v1.0 baseline vs Phase 10 snapshot の3-way 比較表示（reports/10-evaluation）は researcher/planner 裁量で残してよい（Phase 9/9.1 stopgate 表示との連続性・選定基準の後知恵すり替えは D-16 で禁止）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ロードマップ・要件（聖域）
- `.planning/ROADMAP.md` — Phase 10 section・SC#1-5（SC#1 as-of 定義必須決定・SC#2 race_id 単位/同着欠損明文化・SC#3 §12.4 metadata/byte-reproducible/parity・SC#4 SAFE-01 proxy 排除・SC#5 v1.0 LightGBM 非劣化）・Depends on Phase 9.1
- `.planning/REQUIREMENTS.md` — FEAT-02（相手強度 `field_strength`）・FEAT-03（レース内相対 rank/gap_to_top/gap_to_3rd/field_strength_adjusted_rank）・SAFE-01（odds-free/proxy 排除）・Out of Scope（過去人気/過去オッズ proxy は市場回帰で除外）
- `docs/keiba_ai_requirements_v1.3.md` — 要件正（§7.2 `is_model_eligible`・§10.5 払戻/返還・§12.4 metadata・§13 PIT/feature_availability/§13.4 forbidden columns・§14.3 categorical leak-safe・§15.2 事前登録指標不変・§19.1 再現性）
- `.planning/PROJECT.md` — Key Decisions（core value 再定式化・過去人気/オッズ proxy 除外）・Out of Scope・v1.1 Current Milestone

### 前 Phase の決定（PIT 定義・API の踏襲）
- `.planning/phases/09-speed-figure-foundation/09-CONTEXT.md` — D-03 PIT（`available_at < feature_cutoff_datetime` strict `<`）・D-09 latest-K rolling（obs_id group・窓3/5・sentinel）・D-05 float 指数（丸めない）・踏襲アセット・Claude's Discretion の範囲
- `.planning/phases/09.1-speed-ability-profile-expansion/09.1-01-PLAN.md` — speed profile 17 feature 拡張（median/best2/trend + same_surface/distance_bucket）・命名 idiom（`rolling_speed_figure_{axis}_{window}`・trend 系の window 埋込）・schema_version 0.5.0

### 外部2AI リサーチ・文献
- `.planning/research/v1.1-domain-analysis.md` — 相手強度・レース内相対の P0 位置づけ・層分離（§5: p モデル odds-free）・falsification（§6: Phase 12 EVAL-02 委譲）・文献（§8）
- Benter (1994)・Bolton & Chapman (1986)・Hausch/Ziemba/Rubinstein (1981) — fundamental model・relative performance・opponent quality の文献（domain-analysis §8）

### 踏襲アセット（コード・必読）
- `src/features/speed_figure.py` — `compute_speed_figure_for_history(history, observations)`（history 全行に `speed_figure` float + `available_at` + 監査列を付与・obs_id 展開・`_pit_cutoff_prefilter` strict `<`）・`_derive_surface` / `get_points_per_second` / `_compute_leave_one_out_variant`
- `src/features/rolling.py` — `build_rolling_features(observations, history, lookback=5)`（per-observation latest-K・`obs_id` group・strict `<cutoff`・`_ROLLING_SYSTEMS`・`_speed_figure_col_name`/`_best2_mean_of_group`）・Phase 9.1 拡張（median/best2/trend + same_surface/distance_bucket）
- `src/features/builder.py` — `build_feature_matrix`（Step 1-6b・Step 5 rolling・Step 5b speed_figure・Step 6 推定脚質・Step 6b obs_id drop・`make_race_nkey`・COPY-NOT-RENAME・FEATURE_COLUMNS allowlist 契約）
- `src/features/snapshot.py` — §12.4 metadata・byte-reproducible Parquet 書込（新 `feature_snapshot_id`・SHA256・metadata 除外再計算）
- `src/features/availability.py` + `src/config/feature_availability.yaml` — `_ROLLING_SYSTEMS_FOR_RESERVED`・registry↔Parquet parity・`assert_matrix_columns_registered`・schema_version
- `src/utils/pit_join.py` — `merge_asof(direction='backward')` primitive（PIT 集約保証）
- `src/etl/normalize.py` — 素材層（`race_nkey`/`kettonum`/`datakubun`/取消除外ステータス・staging-swap DDL 駆動 `_TABLE_DDL_COLUMNS`）
- `src/config/class_normalization.yaml` — `class_code_normalized` 機械導出（参考）

### 評価・監査（SC#5・SAFE-01）
- `src/model/evaluator.py` — `check_acceptance_gate`・§15.2 事前登録指標不変（calibration_max_dev/Brier/LogLoss）・D-07 水準
- `src/model/segment_eval.py` — odds_band×p_bin・selected-only calibration・6軸 segment・binning 契約（`_compute_calibration_curve_bins`/`_compute_ece`/`_compute_mce`）・Plotly HTML+JSON
- `src/model/data.py` — `FEATURE_COLUMNS` allowlist・`make_X_y`（FEATURE_COLUMNS 完全一致 assert）・`load_feature_matrix(snapshot_id)`
- `src/model/trainer.py` — LightGBM/CatBoost 学習（単体モデル再利用・SC#5 v1.0 LightGBM 再学習）
- `src/audit/report.py`・`tests/audit/` — adversarial audit（AST read-only・allowlist grep・lookahead・SC#1/#2/#3 踏襲・SAFE-01 proxy 排除証明）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_speed_figure_for_history(history, observations)`: history 全行に `speed_figure`/`available_at` が既に付与済み。相手強度計算はこの列（各過去走の各馬の `speed_figure` + `available_at`）を入力にする。source race の識別は `race_nkey`（`make_race_nkey(year,jyocd,kaiji,nichiji,racenum)`）・馬単位は `kettonum`。
- `build_rolling_features(observations, history, lookback=5)`: per-observation latest-K algorithm（`obs_id=(race_nkey,kettonum)` group・strict `<cutoff`）。field_strength profile（D-13）の第2段階 latest-K 集約は、`rolling_speed_figure_*` 17 feature と**対称**の idiom で拡張可能（系統に `field_strength` を追加・軸 = profile 8値）。
- `_pit_cutoff_prefilter` / `merge_asof(direction='backward')`: 相手の当時 rolling 能力（D-02）の PIT 保証（source race 時点 `available_at` で相手能力を再計算する際の strict `<`）。
- `snapshot.py` + `availability.py` + `feature_availability.yaml`: 新 feature の §12.4 metadata・byte-reproducible Parquet・registry↔Parquet parity（schema_version 0.5.0 → 次）。
- `evaluator.py` + `segment_eval.py`: SC#5 非劣化 gate（Brier/LogLoss/AUC）・selected-only calibration/odds_band×p_bin 参考記録（binning 契約固定・bit-identical）。
- `trainer.py` + `data.py`: v1.0 LightGBM 再学習（FEATURE_COLUMNS allowlist 拡張・`make_X_y` 完全一致 assert）。

### Established Patterns
- **per-observation latest-K rolling**（`obs_id` group・strict `<cutoff`）— CYCLE-2 HIGH#1 cross-obs leak 回避（rolling_speed_figure と対称）。
- **PIT 厳格 `<`**（`available_at < feature_cutoff_datetime`・race_date - 1day・JST midnight・strict）— 相手強度（D-01 厳格版）・レース内相対（target のみ）の両方で不変量。
- **copy-not-rename builder** + FEATURE_COLUMNS allowlist（§14.3）— 新 feature 追加時の契約（fake-green 防止）。
- **byte-reproducible snapshot**（`FIXED_REPRODUCE_TS`・SHA256・metadata 除外）— §19.1 聖域。
- **profile 化集約**（mean/median/top-k/max/sd/count/coverage）— Phase 9.1 の 17 feature 拡張 idiom（単一代表値に潰さない・count/coverage で信頼度）。
- **adversarial audit**（AST read-only・allowlist grep・lookahead・SC#1/#2/#3）— SAFE-01 proxy 排除証明（相手強度・レース内相対でも odds/ninki proxy が混入しないことの静的保証）。

### Integration Points
- `builder.py` に相手強度（Step 5c 等）・レース内相対（Step 7 等）を挿入 → `snapshot.py` で Parquet 永続化 → `data.py`/`trainer` で v1.0 LightGBM 再学習 → `evaluator`/`segment_eval` で SC#5 評価。
- `rolling.py` の `_ROLLING_SYSTEMS` に `field_strength` 系統を追加（source 列 = 第1段階 profile）・`feature_availability.yaml` と registry に3者 parity 登録。
- レース内相対特徴量（FEAT-03）は target observation のみ・race_id（`race_nkey`）単位の group-by で計算（過去走には適用しない）。
- prediction/backtest テーブルは `model_version`-scoped swap（HIGH#1・`make_model_version` 形式 `{feature_snapshot_id}-{short}-v{N}`）— Phase 10 snapshot は別 `feature_snapshot_id`。

</code_context>

<specifics>
## Specific Ideas

- **厳格版 as-of はユーザーの明示的判断**（core value「リーク防止最優先」と整合・再評価版の強信号よりも PIT の最も厳しい解釈と監査の説明しやすさを優先）。SC#1 が「計画段階で決定・明文化」を要求していた核心。
- **profile 化は Phase 9.1 の意図の踏襲**（「単一代表値に潰さない」・mean 単独では情報を削りすぎ・top-k クランプと count/coverage で信頼度を明示）。
- **`field_strength_adjusted_rank` は正の補正（additive bonus）**。ユーザー指摘: 差（index − field_strength）も比（index / field_strength）も「強い相手と走ってきた馬をむしろ下げやすい」ので不採用。強い相手と戦った実績はボーナス（`+ 0.25 * field_strength`）で表現する。raw rank/profile と別保持で composite が効かない場合の安全策。
- **same_surface/distance_bucket の重複排除**はユーザーの明示的判断（相手強度は過去 field quality・条件適性は speed 側で既存・field_strength 側に重複させない）。
- **係数候補 `{0.0, 0.1, 0.25, 0.5}` に `0.0` を含める**のは baseline（raw mean_5 rank と同値）として必須・test 窓選び直し禁止（§11.2）は聖域。
- **rich but bounded**（21 feature）は情報量と feature 膨張のバランス・Phase 9.1 17 feature と同世代の規模感。

</specifics>

<deferred>
## Deferred Ideas

- 正規 falsification test（`logit(outcome) ~ logit(market_implied) + logit(model_p)`・race_id clustered SE・market 再校正・正式レポート）— Phase 12 EVAL-02（residual proxy も同委譲・D-15）
- `p_lower`（下側信頼限界）による EV 判定 — Phase 12 EV-01
- レース内相対確率モデル（`sum(p)=払戻対象数` 制約・race-level top-k calibration）— Phase 11 MODEL-01（FEAT-02/03 完成後の入力）
- same_surface / same_distance_bucket の相手強度版・decay 加重 field_strength・class 別 field_strength — speed 側で条件適性を既存扱い・本 Phase では重複回避（将来 refinement）
- field_strength profile の additional 軸（percentile・IQR 等）・FEAT-03 の過去走適用（target のみで十分と判断・将来検討）

*None folded from todos — discussion stayed within phase scope（todo.match-phase 0 件）*

</deferred>

---

*Phase: 10-Opponent Strength & Race-Relative Features*
*Context gathered: 2026-06-26*
