# Phase 10: Opponent Strength & Race-Relative Features - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 10-Opponent Strength & Race-Relative Features
**Areas discussed:** 相手強度 field_strength の定義, レース内相対 rank, field_strength 集約, SC#5 評価方針

---

## 相手強度 field_strength の定義（FEAT-02・SC#1）

### Q1. as-of タイミング

| Option | Description | Selected |
|--------|-------------|----------|
| 厳格版(as-of) | 各過去走の source race 時点 available_at で存在する相手の能力のみ。PIT の最も厳しい解釈・adversarial audit で説明しやすい・core value と整合 | ✓ |
| 再評価版(cutoff) | 予測時点 cutoff で既知の相手の能力（最新 rolling profile）。信号強度高だが「当時の強さ」でなく「現在わかる強さ」 | |
| 両方を比較 | 両方実装して stop gate で比較採用。feature 数増・計算コスト約2倍・Phase 9「最小十分」方針と反する | |

**User's choice:** 厳格版(as-of)
**Notes:** core value「リーク防止・再現性だけは必ず守る」と整合・PIT の最も厳しい解釈・adversarial audit で最も説明しやすい。SC#1 が計画段階決定を要求していた核心。

### Q2. 相手の能力の測度（厳格版として）

| Option | Description | Selected |
|--------|-------------|----------|
| source race の指数 | その source race で各相手が走った speed_figure を集約。history に既付与・計算効率良 | |
| 当時の rolling 能力 | source race 時点 available_at までの相手の rolling 安定能力。安定信号だが計算コスト大 | ✓ |
| 両方 | speed_figure + 当時 rolling。信号豊かだが feature 膨張・計算コスト最大 | |

**User's choice:** 当時の rolling 能力
**Notes:** 安定信号を優先。計算コスト高（各過去走×各相手×rolling）は researcher が vectorized 設計。

### Q3. source race 内の相手集約

| Option | Description | Selected |
|--------|-------------|----------|
| 全相手の mean | 自馬以外の全出走馬の平均。標準的 field_strength | |
| 全相手の median | 中央値・外れ値に強い・Phase 9.1 踏襲 | |
| 完走馬のみ mean | 競走中止/除外馬を除く完走馬の平均 | |
| (Other) field_strength profile 化 | mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage の8値 profile。発走馬のみ相手（未発走除外・競走中止馬は含む）。top-k=min(k,valid_opponents)。canonical=mean・profile 全体を特徴量候補 | ✓ |

**User's choice:** (Other) field_strength profile 化（8値）
**Notes:** 「mean 単独では Phase 10 の情報を削りすぎ」・Phase 9.1 で profile 拡張した意図の踏襲。発走馬の特定は researcher が live-DB で datakubun/取消除外ステータス/is_model_eligible/refund と照合。原則「実際に発走した馬を相手に含める・未発走馬は除外・競走中止馬は発走済みなので含める」。2段階集約構造（①source race 内 profile → ②target 馬の過去走 profile を latest-K rolling・strict `<`）。

---

## レース内相対特徴量（FEAT-03・SC#2）

### Q1. 順位素材 speed_index の定義

| Option | Description | Selected |
|--------|-------------|----------|
| mean_5(安定) | rolling_speed_figure_mean_5。Phase 9 D-09 主軸 | |
| best2_mean_5 | ピーク寄り・Phase 9.1 追加 | |
| median_5 | 外れ値に強い・Phase 9.1 踏襲 | |
| 複数軸で rank | mean_5/best2/median の各々で rank/gap を作る | ✓ |

**User's choice:** 複数軸で rank（gap は主軸中心）
**Notes:** 「Phase 9.1 を入れた理由は単一代表値に潰さないため。レース内相対も mean_5 だけでは弱い。ただし全部に同じだけ rank/gap を作ると膨らみすぎるので、複数軸で rank、gap は主軸中心」。→ rank は3軸（mean_5/best2_mean_5/median_5）・gap（gap_to_top/gap_to_3rd）は mean_5 主軸に確定。

### Q2. gap の単位

| Option | Description | Selected |
|--------|-------------|----------|
| 指数 point 差 | speed_figure float の差（top/3位 − self）。解釈容易・adversarial audit 透明・Phase 9 D-05 float をそのまま | ✓ |
| 秒差(逆変換) | points_per_second で秒に戻す。物理的直感だが距離別係数依存 | |
| race 内 z-score | race の mean_5 の sd で正規化。field size 非依存・スケールフリー | |

**User's choice:** 指数 point 差

### Q3. 欠損馬の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| NaN保持・母集団除外 | 欠損馬を rank/gap の母集団から除外・自身 NaN。LightGBM native NaN 処理・Phase 9 D-11 踏襲 | ✓ |
| 最下位固定 | rank=有効馬+1（最下位）・gap=sentinel。保守的 | |
| sentinel 数値 | __MISSING__ 数値 sentinel（-999 等）。magic number で監査要注意 | |

**User's choice:** NaN保持・母集団除外
**Notes:** 同着は competition ranking（min rank）で明文化（Claude 裁量・SC#2 要件）。

### Q4. field_strength_adjusted_rank の定義

| Option | Description | Selected |
|--------|-------------|----------|
| index−field_strength で rank | 自馬能力から相手強度を引いた净值で rank | |
| index/field_strength 比で rank | 相手強度に対する能力比 | |
| Claude 裁量に委ねる | 実装方式は researcher/planner・CONTEXT に方針のみ | |
| (Other) additive score | 相手強度を正の補正として加える。canonical=mean_5 + 0.25*field_strength_mean_mean_5・race 内降順 rank・raw は別保持 | ✓ |

**User's choice:** (Other) additive score（正の補正）
**Notes:** ユーザー指摘「差も比も強い相手と走ってきた馬をむしろ下げやすい」→ 正の補正（additive bonus）が正しい。主能力=mean_5 優先・field_strength は補助ボーナス。欠損は NaN/母集団除外。raw の speed_index_rank/field_strength profile/rank は別特徴量で保持（composite が効かない場合の安全策）。係数 0.25 を事前登録 canonical 初期値・候補 {0.0,0.1,0.25,0.5}（0.0=baseline・raw mean_5 rank と同値）・train/calib 内のみ感度分析・test 窓選び直し禁止（§11.2）・Plan 時点で候補集合と選定指標を明記。

---

## field_strength 集約（target feature 化）

### Q1. profile のどの軸を latest-K rolling feature 化するか

| Option | Description | Selected |
|--------|-------------|----------|
| 代表軸中心 | mean/median/best2/trend + count/coverage・窓3/5。same_surface/distance_bucket は省略 | |
| Phase 9.1 完全踏襲 | 代表軸 + same_surface/same_distance_bucket。17 feature と完全対称・膨張大 | |
| mean/median のみ | rolling_field_strength_mean/median_{3,5}。最小 | |
| (Other) rich but bounded | 21 feature（latest_1×6/mean_3×5/mean_5×6/trend×2/valid_count_mean_5/coverage_mean_5）。same_surface/distance_bucket は省略（speed 側で既存・重複回避）。欠損 NaN・count/coverage で信頼度明示 | ✓ |

**User's choice:** (Other) rich but bounded（21 feature）
**Notes:** 相手強度は過去レースの field quality・target 条件適性は speed profile 側で既に表現 → field_strength 側に条件適性を重複させない。

---

## SC#5 評価方針

### Q1. 評価フロー

| Option | Description | Selected |
|--------|-------------|----------|
| 中間:非劣化+投票層参考 | SC#5(Brier/LogLoss/AUC 非劣化)を必須 gate・selected-only/odds_band×p_bin を参考記録・residual proxy は Phase 12 EVAL-02 へ委譲 | ✓ |
| SC#5 軽量のみ | Brier/LogLoss/AUC 非劣化のみ・他は記録しない | |
| Phase 9 stop gate 完全踏襲 | 4指標+residual proxy・改善 gate。Phase 10 は MODEL-01 前・改善期待には早い | |

**User's choice:** 中間:非劣化+投票層参考

### Q2. 非劣化の許容幅

| Option | Description | Selected |
|--------|-------------|----------|
| Claude 裁量(planner) | Brier/LogLoss/AUC の許容悪化幅を planner が事前登録（Phase 11 SC#2 と整合・§15.2 事前登録指標整合・test 窓変更禁止）。候補例 Brier 悪化 ≤0.002/AUC 悪化 ≤0.005 程度 | ✓ |
| ユーザーが数値指定 | ここで具体マージンを決める | |
| 厳格:一切の悪化不可 | v1.0 と同等か改善のみ（浮動小誤差除く） | |

**User's choice:** Claude 裁量(planner)
**Notes:** 「planner が Phase 10 の実装内容・サンプル数・BT窓・Phase 11 の非劣化基準との整合を見て Plan 作成時に数値を事前登録する方が正確」。条件: Plan 内で Brier/LogLoss/AUC の許容幅を明記・pass/fail ルールも明記・評価結果を見た後に変更しない（§11.2）。

---

## Claude's Discretion

- 発走馬特定の実装（datakubun/ステータス精査・live-DB・D-04 原則の機械的実現）
- 相手の当時 rolling の vectorized 実装（全レースループ vs expanding as-of vs per-source-race batch）
- モジュール構成・compute_field_strength 配置（新モジュール vs 既存拡張）
- builder.py 拡張（新 Step 挿入位置・obs_id idiom 踏襲・Step 6b 中間列 drop）
- snapshot feature_snapshot_id 命名・schema_version（0.5.0 → 次）・v1.0 系統継承
- feature_count 最終値・registry↔Parquet parity（3者）・_ROLLING_SYSTEMS 拡張
- trend/coverage/top-k 集約の境界数値・sentinel 閾値
- 非劣化マージン数値（D-16・Phase 11 SC#2 と整合）
- stop gate 相当の3-way 比較表示（reports/10-evaluation・選定基準の後知恵すり替えは禁止）

## Deferred Ideas

- 正規 falsification test・residual proxy — Phase 12 EVAL-02（D-15）
- p_lower による EV 判定 — Phase 12 EV-01
- レース内相対確率モデル（sum(p)=払戻対象数 制約・race-level top-k calibration）— Phase 11 MODEL-01
- same_surface/distance_bucket の相手強度版・decay 加重 field_strength・class 別 field_strength — speed 側で既存・将来 refinement
- field_strength profile の additional 軸（percentile/IQR）・FEAT-03 の過去走適用 — 将来検討
