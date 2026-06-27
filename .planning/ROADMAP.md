# Roadmap: Keiba AI v3

## Overview

**v1.0 shipped 2026-06-25** — leakage-critical・reproducibility-critical な odds-free 複勝 `p_fukusho_hit` pipeline。各出走馬の複勝払戻対象確率を推定し、固定オッズ時点のEVで評価、race_id単位・時系列順の再現可能バックテストで定量評価、read-only Streamlit UI + CSV で提示。コアバリュー（リーク防止・再現性）は完全保持。

回収率0.65-0.70天井は odds-free 1-A モデルの構造的限界（3層構造: 市場情報不足→中高オッズ域過大予測→EV演算増幅→複勝控除率天井）。要件未達でなく正直な結論。

**v1.1 現マイルストーン** は core value（odds-free）を維持したまま、この構造的限界（層1: 市場情報不足→中高オッズ域過大予測）へ正統に対応する。能力特徴量を「着順中心」から「速度（スピード指数）・相手強度・レース内相対」へ拡張し、レース内相対確率モデル（`sum(p)=払戻対象数` 制約）と `p_lower` EV 判定で投票層の過大予測を是正する。同時に falsification test で「odds-free で market residual が残るか」を検証し、回収率0.65が特徴量不足か構造的限界かを鑑別する。成功基準は黒字化でなく「市場残差能力の定量測定」＋「投票層の過大予測是正」（現実回収率 0.78-0.92 見込・正直な結論）。

詳細は `.planning/milestones/v1.0-ROADMAP.md`（v1.0 フル Phase Details）・`v1.0-MILESTONE-AUDIT.md`（v1.0 監査）。

## Milestones

- ✅ **v1.0 Leak-Free Fukusho Pipeline** — Phases 1-8 + 3.1 (shipped 2026-06-25)
- 🚧 **v1.1 Ability Feature v2 & Conditional Calibration** — Phases 9-12 (started 2026-06-25)

## Phases

<details>
<summary>✅ v1.0 Leak-Free Fukusho Pipeline (Phases 1-8 + 3.1) — SHIPPED 2026-06-25</summary>

- [x] Phase 1: Trust & Foundation (4/4 plans) — completed 2026-06-17
- [x] Phase 2: Fukusho Labels (4/4 plans) — completed 2026-06-18
- [x] Phase 3: As-of Features & Snapshots (5/5 plans) — completed 2026-06-19
- [x] Phase 3.1: Timediff/Babacd Rolling Restoration (4/4 plans, INSERTED) — completed 2026-06-19
- [x] Phase 4: Model & Prediction (6/6 plans) — completed 2026-06-20
- [x] Phase 5: EV & Backtest (6/6 plans) — completed 2026-06-21
- [x] Phase 6: Evaluation & Calibration Gates (5/5 plans) — completed 2026-06-23
- [x] Phase 7: Presentation (3/3 plans) — completed 2026-06-24
- [x] Phase 8: Adversarial Audit Suite (3/3 plans) — completed 2026-06-25

</details>

### v1.1 Ability Feature v2 & Conditional Calibration

- [x] **Phase 9: Speed Figure Foundation** - 走破タイムを馬場/距離/トラック/クラス補正したスピード指数（Beyer 的）を自前構築し、能力特徴量の新たな主軸を据える (completed 2026-06-25)
- [x] **Phase 9.1: Speed Ability Profile Expansion** (INSERTED) - Phase 9 の speed_figure 6→17 feature 拡張（median/best2/trend + same_surface/same_distance_bucket）・Phase 10 入力強化 (completed 2026-06-26)
- [x] **Phase 10: Opponent Strength & Race-Relative Features** - 相手強度（as-of）とレース内相対特徴量（rank/gap_to_top/gap_to_3rd）を追加し、複勝の相対競争を特徴量層で表現する (completed 2026-06-27)
- [ ] **Phase 11: Race-Relative Probability Model** - 独立二値分類から `sum(p)=払戻対象数(2/3)` 制約・race-level top-k calibration のレース内相対確率モデルへ移行する
- [ ] **Phase 12: p_lower EV & Falsification Evaluation** - `p_lower` 下側信頼限界によるEV判定へ移行し、評価指標拡張（selected-only calibration / EV-decile ROI / disagreement ROI / snapshot slippage）と falsification test で market residual を統計検証する

## Phase Details

### Phase 9: Speed Figure Foundation

**Goal**: 走破タイムを馬場/距離/トラック/クラス/開催日で補正したスピード指数（Beyer 的）を odds-free かつ PIT-correct に構築し、能力特徴量の主軸として v1.0 snapshot に追加可能な形で確立する。着順でなく能力を直接測る。
**Depends on**: Phase 8 (v1.0 shipped・既存 normalized 層 + feature snapshot pipeline を踏襲)
**Requirements**: FEAT-01, SAFE-01 (特徴量追加時のリーク/市場回帰ガード)
**Success Criteria** (what must be TRUE):

  1. スピード指数が par time（距離/トラック/開催日ごとの標準タイム）と馬場差（baba 差分）の算出を通じて、normalized 層の素材（`time`/`kyori`/`babacd`/`trackcd`/`class_code_normalized`）から byte-reproducible に生成できる（同じ snapshot metadata で再生成すると bit-identical）
  2. スピード指数が PIT-correct である。各過去走の指数には `available_at`（その走の `race_date`）を持たせ、target row では **`available_at < feature_cutoff_datetime`（= `race_date - 1day`・JST midnight・strict <）の指数だけを** par time（距離/トラック/開催日ごとの標準タイム）・馬場差（track variant）の算出に集計する。**対象レース当日の走破タイム・馬場結果は絶対に par/variant に入れない**（未来情報リーク）。`merge_asof(direction='backward')` 相当の as-of 計算・adversarial lookahead テスト GREEN。
  3. スピード指数を追加した新 feature snapshot（feature_count 増・新 `feature_snapshot_id`）が `§12.4` metadata を満たし、`KEIBA_SKIP_DB_TESTS` unset の live-DB で生成でき・registry↔Parquet parity が保たれる
  4. オッズ/人気/過去人気/過去オッズ proxy が新特徴量に混入していないことを adversarial audit（AST 静的保証・allowlist grep）で証明できる（SAFE-01・過去オッズ proxy 排除）
  5. スピード指数の分布がドメイン整合性を持つ（同一馬の連続走で指数が大きく安定し・クラス昇降で有意に変動する・極端な外れ値がないことを live-DB で可視化確認）
  6. 【**stop gate**・Phase 9 終了時】スピード指数を追加した単体モデル（v1.0 特徴量＋スピード指数）で、odds_band × p_bin の過大予測（v1.0 の中高オッズ域4倍過大）が改善するか、または falsification の暫定 market residual が残るかを確認する。**両方とも改善/residual が見られなければ「特徴量不足でなく構造的限界寄り」と判断**し、Phase 10-12 に進む前にマイルストーン継続の可否を評価する（マイルストーン目的＝市場残差能力の定量測定・鑑別に合致・早期撤退判断）。

**Plans**: 5/5 plans complete
**Wave 1**

- [x] 09-01-PLAN.md — speed_figure.py 新規(par/variant/PIT/float) + SC#1/SC#2 単体/adversarial テスト(FEAT-01/SAFE-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — rolling.py/availability.py/feature_availability.yaml 拡張(speed_figure 6 feature + course_kubun bug 修正)(FEAT-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 09-03-PLAN.md — builder.py Step 5b 統合 + SC#1 byte-reproducible/SC#3 registry↔Parquet parity + REVIEW H1-a/H1-b/H1-c data.py/orchestrator snapshot parameterization(FEAT-01)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 09-04-PLAN.md — SC#4 SAFE-01 proxy 排除 AST audit + SC#5 ドメイン整合性可視化(SAFE-01/FEAT-01)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 09-05-PLAN.md — SC#6 stop gate(v1.0 baseline 比較・D-14 4指標+D-15 residual proxy・D-16 checkpoint)(FEAT-01)

### Phase 09.1: Speed Ability Profile Expansion (INSERTED・完了 2026-06-26)

**Goal:** Phase 9 の `speed_figure` 6 feature を 17 feature に拡張（median/best2/trend + same_surface/same_distance_bucket）。Phase 10（相手強度・レース内相対）の入力として十分な speed ability profile を確立。par/variant・float scale・PIT・stopgate の Phase 9 成果は壊さず、馬個人の speed profile 集約だけを拡張。
**Depends on:** Phase 9
**Requirements**: FEAT-01 (speed ability profile expansion), SAFE-01
**Success Criteria** (what must be TRUE):

  1. 新 11 特徴量（median_3/median_5/best2_mean_5/trend_last_minus_mean5/trend_mean3_minus_mean5 + same_surface/same_distance_bucket × mean/max/count）が live snapshot に存在し・欠損/count/coverage の挙動が説明できる（D-09.1-01/02/03）
  2. registry↔Parquet parity GREEN（schema_version 0.5.0・`assert_matrix_columns_registered`）
  3. unit tests GREEN（79 tests・Phase 9 回帰なし）
  4. adversarial lookahead test GREEN（same_surface/distance_bucket が二重 PIT filter に依存・guard 無効化で混入検出）+ odds proxy audit GREEN（SAFE-01）
  5. PIT-correct 維持（`available_at < feature_cutoff_datetime` strict `<`）
  6. byte reproducibility 維持（snapshot `20260626-1a-speedprofile-v1`・features=79・2回 build で SHA256 一致）
  7. stopgate 3-way 比較（v1.0 baseline / Phase 9 6-feature / Phase 9.1 expanded）が reports/09-stopgate + reports/09.1-stopgate に読める形で残る（D-16 verdict: Phase 10 進行候補）

**Plans:** 1/1 complete
Plans:

- [x] 09.1-01-PLAN.md — rolling.py 拡張(median/best2/trend + same_surface/same_distance_bucket) + availability/feature_availability.yaml(schema 0.5.0) + builder(target trackcd/kyori) + snapshot/tests/stopgate (FEAT-01/SAFE-01)

### Phase 10: Opponent Strength & Race-Relative Features

**Goal**: 過去走の相手の as-of 能力平均（`field_strength`）と、レース内相対特徴量（`speed_index_rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`）を、Phase 9 のスピード指数を前提として odds-free・PIT-safe に追加する。複勝の「相対競争・各馬独立事象でない」性質を特徴量層で表現する。
**Depends on**: Phase 9.1 (Phase 9.1 完了後の新 snapshot `20260626-1a-speedprofile-v1`・17 feature 拡張 speed profile を入力。Phase 9 スピード指数 + Phase 9.1 分布形状/趨勢/条件適性 profile が相手強度・レース内相対の基盤・Phase 10 後の speed profile 差し込み禁止)
**Requirements**: FEAT-02, FEAT-03, SAFE-01 (特徴量追加時のリーク/市場回帰ガード)
**Success Criteria** (what must be TRUE):

  1. 相手強度特徴量が PIT-correct に計算できる。as-of 定義は**計画段階で以下のいずれかを決定し明文化**する: (厳格版) 各過去走の時点 `available_at` で存在する相手の能力のみ使用、または (current-cutoff 再評価版) 予測時点 `feature_cutoff_datetime` で既知の相手の能力（そのレース後に相手が強かったという事後情報も予測時点では合法な能力情報）を使用。**いずれも対象レース当日の結果は使わない**・未来の能力値を遡及注入しない・adversarial lookahead テスト GREEN。
  2. レース内相対特徴量（`speed_index_rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`）が race_id 単位で計算され・出走馬内の順序付けが future-information なしで確定する（出馬表確定時点 `feature_cutoff_datetime` 基準・同着・欠損の境界処理が明文化される）
  3. 追加特徴量を含む feature snapshot が byte-reproducible・registry↔Parquet parity を満たし・`§12.4` metadata に新 `feature_cutoff_datetime` と `feature_availability` エントリが反映される
  4. オッズ/人気/過去人気/過去オッズ proxy の混入がないことを adversarial audit で証明できる（SAFE-01）
  5. live-DB で生成した snapshot が・v1.0 の主モデル（LightGBM）で再学習時に Brier/LogLoss/AUC の現行水準（Phase 6 D-07 数値）を悪化させない（特徴量ノイズ化の回帰検知）

**Plans**: 7/7 plans executed (Phase 10 complete) + 2 gap-closure plans (10-08/10-09・post-ship REVIEW findings 対応・10-REVIEW.md 4 Critical + 6 Warning + doc 不整合)

Plans:
**Wave 1**

- [x] 10-01-PLAN.md — FEAT-02 相手強度 field_strength 第1段階（source race 内 opponent profile 8値・D-01 厳格版 as-of・D-04 発走馬特定・compute_field_strength_profile 新規・CYCLE-2 HIGH-C2-1: raw history に obs_id='SOURCE_ASOF_<race_nkey>' で full par+variant+speed_figure pipeline を source-as-of 再計算・値の不変性 adversarial test）

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-02-PLAN.md — FEAT-02 相手強度 第2段階（rolling.py 拡張・_FIELD_STRENGTH_AXES・D-13 21 feature・obs_id group・sentinel ルール）
- [x] 10-03-PLAN.md — FEAT-03 レース内相対特徴量（race_relative.py 新規・speed_index_rank 3軸・gap_to_top/3rd・field_strength_adjusted_rank・competition ranking・D-12 係数事前登録）

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 10-04-PLAN.md — builder.py 統合（Step 5c/5d/7/7b・A6 構成変更・CYCLE-2 HIGH-C2-3: Step 5c は history でなく raw_history を渡す）+ feature_availability.yaml schema_version 0.6.0 + 27 feature registry 登録（registry↔Parquet parity）

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 10-05-PLAN.md — snapshot.py 拡張 + live-DB で snapshot 20260626-1a-opponentstrength-v1（feature_count=106）生成 + byte-reproducibility 検証（SC#3・§19.1・Pitfall 5）

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 10-06-PLAN.md — data.py/trainer/evaluator + scripts/run_phase10_evaluation.py（SC#5 非劣化 gate・D-16 事前登録許容幅 Brier≤0.002/LogLoss≤0.005/AUC≤0.005・§11.2 聖域）
- [x] 10-07-PLAN.md — SAFE-01 adversarial audit（AST odds/ninki proxy 排除【REVIEW H3 odds-in-SQL 拡張】・lookahead 注入【行包含 + 値の不変性・CYCLE-2 MEDIUM-C2-4】・5段階鋳型）+ cProfile 性能検証（W-3 核心 GREEN・W-3 縮小版 5.0s は PLAN 01 設計と構造的矛盾で default skip・PLAN 更新待ち）

**Gap-Closure (post-ship・10-REVIEW.md findings 対応)**

- [x] 10-08-PLAN.md — gap-closure 本体（10-REVIEW.md 4 Critical + 6 Warning の fail-loud 化・堅牢化・live-DB snapshot 再生成検証・CR-01〜04/WR-01〜06・Phase 11 入力 snapshot 整合・core value「リーク防止」の鏡像「silent fallback 禁止」機械保証）
- [x] 10-09-PLAN.md — 10-06-PLAN doc truth 数値訂正（baseline feature count 79 → 35・substantive 達成済み・doc 正確性・コード変更なし）

### Phase 11: Race-Relative Probability Model

**Goal**: 独立二値分類（v1.0 LightGBM）から、`sum(p)=払戻対象数(2/3)` 制約と race-level top-k calibration（Plackett-Luce/Harville 的）を取り入れたレース内相対確率モデルへ移行し、過大EVを構造的に抑える。`p_fukusho_hit` の確率品質（Brier/Calibration）を維持または改善する。
**Depends on**: Phase 10 (FEAT-01/02/03 の完成した feature snapshot が入力)
**Requirements**: MODEL-01, SAFE-01 (モデル変更時のリーク/市場回帰ガード)
**Success Criteria** (what must be TRUE):

  1. モデルが race_id 単位で `sum(p)` を払戻対象数（8頭以上3頭・5-7頭2頭・それ以外は仕様通り）に近づける構造（制約付き正規化・race-level top-k calibration・listwise loss のいずれか）を持ち・train→calib→test が `GroupTimeSeriesSplit`（groups=`race_id`）で時系列厳守・キャリブレーションは既存 `src/utils/calibrator.py` の `fit_prefit_calibrator`（**sklearn 1.9.0 で削除された `cv='prefit'` でなく `FrozenEstimator` + `CalibratedClassifierCV(estimator=...)` idiom・v1.0 Phase 1 確定**）で厳格に later-disjoint に実施（`max(train.race_date) < min(calib.race_date)` unit-test GREEN・§8.4/§15.4）
  2. 新モデルの予測 `p_fukusho_hit` が、v1.0 §15.2 事前登録指標（calibration_max_dev 等は不変・後知恵すり替え禁止）で評価され、全体 Brier/LogLoss は v1.0 主モデル LightGBM（Phase 6 D-07: Brier=0.15222/LogLoss=0.47488/AUC=0.73230/calib=0.231）に対し**事前登録した非劣化マージン（許容幅）内**に収まる（`sum(p)` 制約・`p_lower` 過信抑制が狙いなので全体指標の微小悪化で有用な改善を落とさない）・`sum(p)` 分布チェック（≥8頭 2.7-3.3・5-7頭 1.8-2.2）で過大/過小なし、かつ **selected-only calibration / odds-band calibration が v1.0 より改善**する（投票層の過大予測是正の定量証拠）
  3. 新モデルが LightGBM 構成（native categorical・`__MISSING__`/`__UNSEEN__` sentinel・target/mean encoding 構造的禁止 §14.3）と CatBoost 構成（`cat_features` + `has_time=True`・`race_start_datetime`-sorted Pool §14.4）の両方で構築でき・bit-identical（FIXED_REPRODUCE_TS + 固定 thread/seed・`np.array_equal` 実データ実証）
  4. 特徴量にオッズ/人気/過去人気/過去オッズ proxy が入っていないこと・LightGBM categorical code が非負 int32 であること（`.cat.codes.min()>=0` fail-loud）を adversarial leak diagnostic で証明できる（SAFE-01・SC#3 踏襲）
  5. 新 `p_fukusho_hit` の prediction テーブルが `§19.1` 再現性メタデータ（model_version・feature_snapshot_id・label_version・`odds_snapshot_policy`・`backtest_strategy_version`）付きで DB に model_version-scoped idempotent swap で永続化される（HIGH#1 踏襲）

**Plans**: 2/5 plans executed

Plans:

**Wave 0** (TDD RED・test stub + race_relative.py API stub)

- [x] 11-01-PLAN.md — race_relative.py 公開 API stub + 事前登録定数（θ 候補 {0.5,0.75,1.0,1.25,1.5}・ε=1e-6・xtol=1e-9）+ test_race_relative.py/test_audit_race_relative.py stub RED（MODEL-01/SAFE-01・D-02/D-03/D-09/D-10・SC#1/#3/#4）

**Wave 1** *(blocked on Wave 0)*

- [x] 11-02-PLAN.md — race_relative.py 補正層本体実装（Pattern 1/2/3・brentq α_r 二分探索・sum(p)=k 厳密・D-09 fail-loud・D-10 自己完結・overprediction penalty bit-identical binning）→ test_race_relative.py 12テスト GREEN（MODEL-01/SAFE-01）

**Wave 2** *(blocked on Wave 1)*

- [ ] 11-03-PLAN.md — orchestrator.train_and_predict theta 引数 + 補正層呼出（D-01/D-06・A5 後方互換・SC#3 bit-identical）+ artifact.py metadata.json theta provenance（α_r 不保存・D-10）+ predict.py MODEL_TYPE_TO_SHORT 拡張（lgbrr/cbrr）（MODEL-01/SAFE-01）

**Wave 3** *(blocked on Wave 2)*

- [ ] 11-04-PLAN.md — test_audit_race_relative.py D-10 adversarial 実装（α_r 自己完結 outcome swap + cross-race leak 検出・4テスト GREEN）+ scripts/run_phase11_evaluation.py 新規（v1.0 vs race-relative 3-way 比較・SC#2 gate D-04 非劣化+D-05 改善3条件・θ 選択経路 calib slice のみ §11.2 聖域・is_primary 立てない D-07）（MODEL-01/SAFE-01）

**Wave 4** *(blocked on Wave 3・live-DB・checkpoint)*

- [ ] 11-05-PLAN.md — live-DB SC#2 gate honest 記録 + SC#5 model_version-scoped idempotent swap（2回実行 checksum bit-identical・v1.0 binary 行保持）+ SC#3 bit-identical 実データ実証（FIXED_REPRODUCE_TS + np.array_equal・theta=selected_theta）・checkpoint:human-verify（MODEL-01/SAFE-01）

### Phase 12: p_lower EV & Falsification Evaluation

**Goal**: EV 判定を点推定 `p` から `p_lower`（下側信頼限界・bootstrap/ensemble/conformal・train/calib 設計で test 窓は最終評価のみ）へ移行し、評価指標を拡張（selected-only calibration / EV-decile ROI / model-market disagreement ROI / snapshot-final slippage）して falsification test `logit(outcome) ~ logit(market) + logit(model)` で odds-free market residual を統計検証する。オッズ帯別条件付き calibration を受入基準に追加し、投票層の過大予測を構造的に検出する。
**Depends on**: Phase 11 (レース内相対確率モデルの `p_fukusho_hit` 完成が前提)
**Requirements**: EV-01, EVAL-01, EVAL-02, SAFE-01 (オッズ帯別条件付き calibration 受入基準)
**Success Criteria** (what must be TRUE):

  1. `p_lower`（下側信頼限界）が train/calib データのみで設計され（bootstrap/ensemble/conformal・test 窓での閾値すり替え禁止 §11.2 聖域厳守）・EV 判定が点推定 `p` でなく `p_lower × odds_lower` に移行できる。purchase_simulator が `p_lower` を用いる設定で byte-reproducible に再現可能
  2. 評価指標拡張（selected-only calibration / EV-decile 別実現 ROI / model-market disagreement 別 ROI / odds snapshot→final payout slippage）が実装され・§15.2 事前登録指標（calibration_max_dev/Brier/LogLoss/sum(p) 分布）は一切不変（後知恵すり替え防止）で報告に併載される。投票層（`p_lower` EV で選ばれた馬）の miscalibration が v1.0（p=0.15-0.20 bin で4倍過大予測・実現EV -0.34〜-0.35）から統計的に改善したかどうかが定量化される
  3. falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` が時系列 out-of-sample（train/calib で設計し**test 窓の予測のみで評価**・§11.2 聖域厳守）で実行される。**統計仕様を事前登録**: (a) `market_implied` の定義（複勝 `1/odds` をそのまま使うか train/calib で再校正するか）、(b) race 内の outcome は独立でないため **race_id clustered 標準誤差**を採用、(c) field size・odds clipping（極端オッズの丸め）を統制。`model_p` 係数が統計的に有意（market residual が残る）か否かが明確に結論づけられ、回収率0.65天井が「特徴量不足（model_p に有意な残差）」か「構造的限界（market 係数が model を包摂）」かの鑑別結果が reports/ に honest 記録される（market 情報は診断層のみ・`p` モデルには入れない・EVAL-02/SAFE-01）
  4. オッズ帯別条件付き calibration が受入基準に追加され・投票層（高オッズ域・EV 上位）で `p` が統計的に過大でないことが構造的に検証される（v1.0 の投票馬 p=0.16→実0.04 の4倍過大を catch する gate・SAFE-01）。§15.2 の既存 BLOCK/WARN gate と整合（D-01/D-02/D-03）
  5. v1.0 対抗的監査パターン（tests/audit/・`KEIBA_SKIP_DB_TESTS` unset の live-DB フルスイート GREEN・SC#1/#2/#3 踏襲）が本マイルストーンの全変更（特徴量追加・モデル変更・EV/eval 拡張）に対して GREEN を維持する。byte-reproducible snapshot + 再現性スモークが実データで PASS。現実回収率シナリオ（0.78-0.92 見込・正直な結論）が backtest で定量測定される

**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Trust & Foundation | v1.0 | 4/4 | Complete | 2026-06-17 |
| 2. Fukusho Labels | v1.0 | 4/4 | Complete | 2026-06-18 |
| 3. As-of Features & Snapshots | v1.0 | 5/5 | Complete | 2026-06-19 |
| 3.1 Timediff/Babacd (INSERTED) | v1.0 | 4/4 | Complete | 2026-06-19 |
| 4. Model & Prediction | v1.0 | 6/6 | Complete | 2026-06-20 |
| 5. EV & Backtest | v1.0 | 6/6 | Complete | 2026-06-21 |
| 6. Evaluation & Calibration Gates | v1.0 | 5/5 | Complete | 2026-06-23 |
| 7. Presentation | v1.0 | 3/3 | Complete | 2026-06-24 |
| 8. Adversarial Audit Suite | v1.0 | 3/3 | Complete | 2026-06-25 |
| 9. Speed Figure Foundation | v1.1 | 5/5 | Complete   | 2026-06-25 |
| 9.1. Speed Ability Profile Expansion (INSERTED) | v1.1 | 1/1 | Complete | 2026-06-26 |
| 10. Opponent Strength & Race-Relative Features | v1.1 | 9/9 | Complete    | 2026-06-26 |
| 11. Race-Relative Probability Model | v1.1 | 2/5 | In Progress|  |
| 12. p_lower EV & Falsification Evaluation | v1.1 | 0/? | Not started | - |
