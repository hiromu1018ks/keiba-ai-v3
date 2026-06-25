# Phase 9: Speed Figure Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 9-Speed Figure Foundation
**Areas discussed:** 指数の算出方式, スケール・クラス補正, 馬個人の集約, stop gate の評価範囲

---

## 指数の算出方式

| Option | Description | Selected |
|--------|-------------|----------|
| 長期par＋variant（推奨） | 距離×トラックの長期標準タイムを par とし、開催日の馬場差(variant)を別途算出して加減算。Beyer/Timeform 正統方式 | ✓ |
| 馬場状態で層別 | 距離×トラック×馬場状態(babacd)で par を算出。variant 不要だが層が細かくサンプル不足リスク | |
| 開催日単位のpar | ROADMAP 文面準拠・開催日の代表タイムを par に。PIT 上当日レース使えず推定が必要 | |

**User's choice:** 長期par＋variant（PIT 定義を明確化して採用）
**Notes:** par は full-period 固定値でなく **expanding/as-of robust par**（source race 時点までの利用可能な過去レースのみ）。粒度 `jyocd×trackcd×kyori×course_kubun`・階層 fallback（`jyocd×trackcd×kyori` → `trackcd×kyori`）。variant は target 当日不使用・`source_race_date×jyocd×surface` 単位で same-day residual の robust median/trimmed mean・**leave-one-race-out**（サンプル不足時 all-day robust fallback）。各 speed figure に `available_at` を持たせ `available_at < feature_cutoff_datetime` で集計。full-period par/variant・target day results 混入禁止。**クラスは par 層別に入れない**（能力差を消すため）→ 次領域でスケール調整/variant 補助として扱う。

---

## スケール・クラス補正

| Option | Description | Selected |
|--------|-------------|----------|
| Beyer型整数スケール（推奨） | variant 標準化秒差を速いほど大きい正の整数にスケール変換。SC#5 整合・interpretability 高 | ✓（float 化して採用）|
| variant標準化float | par からの秒差を variant 単位で割った連続値。情報劣化なし | |
| z-score標準化 | 同条件母集団で平均0・分散1。「絶対能力値」でなくなる | |

**User's choice:** Beyer 互換ポイントスケール（canonical は float）
**Notes:** **canonical feature は丸めない float**（variant 補正済みタイム差を距離別 `points_per_second` で変換・速いほど大きい `speed_figure`）。**モデル入力の正は float**。`speed_figure_int=round(speed_figure)` は監査/可視化用のみ。監査列として `speed_residual_sec`/`par_sec`/`variant_sec`/`points_per_second`/`sample_count`/`fallback_level` を保持。クラスは par 層別に深く入れず補助特徴量・SC#5 で単調性確認し必要なら後続 plan で `class_prior`/`class_par_adjustment` 追加。理由: Beyer 型解釈性欲しい・整数丸めで秒差情報を捨てない・z-score は絶対能力値でない・クラス過剰補正で能力差を消す危険。

---

## 馬個人の集約

| Option | Description | Selected |
|--------|-------------|----------|
| latest-K複数軸（推奨） | v1.0 rolling.py 踏襲・複数統計量×複数窓。表現力高・PIT-correct | ✓（最小十分に絞って採用）|
| 代表値1つ | 直近N走の中央値/decay加重平均の単一 feature。シンプル | |
| last＋中央値の2軸 | 直近1走 + 過去N走中央値の最小構成 | |

**User's choice:** latest-K 複数軸（Phase 9 は最小十分な6 feature に絞る）
**Notes:** v1.0 `rolling.py` の per-observation latest-K algorithm（`obs_id` group・`available_at < feature_cutoff_datetime`・strict `<`）踏襲。**6 feature**: `rolling_speed_figure_last_1`(直近状態)/`mean_3`/`mean_5`(安定)/`max_5`(ピーク)/`sd_5`(ブレ)/`count_5`(信頼度)。**median は追加しない**（pandas/再現性/欠損の複雑化回避・後続）。窓は **3 と 5 のみ**（v1.0 整合・膨張抑制）。**decay 加重も後続 refinement**（byte-reproducible・監査しやすい集約を優先）。欠損は既存 rolling の sentinel/nullable 方針・`feature_availability.yaml` と registry↔Parquet parity に登録。

---

## stop gate の評価範囲

| Option | Description | Selected |
|--------|-------------|----------|
| 指標比較のみ（推奨） | odds_band×p_bin 過大予測改善を evaluator/segment_eval で測る。falsification は Phase 12 委譲 | ✓（軽量 residual proxy も追加）|
| 暫定falsification含む | logit(outcome)~logit(market)+logit(model) を Phase 9 で暫定実装。SC#6 両肢を正面実行・重い | |
| 比較＋定性判断 | 定量は比較のみ・継続可否は定性レビュー | |

**User's choice:** 指標比較 ＋ 軽量 residual proxy
**Notes:** 正規 falsification（clustered SE・market 再校正・正式レポート）は **Phase 12 EVAL-02 に委譲**。Phase 9 終了時点で v1.0 baseline vs (v1.0+speed_figure) 単体モデルを**同一 BT split / 同一 odds snapshot policy / 同一選択ルール**で比較。**必須4指標**: (1) odds_band×p_bin selected/high-EV 層 calibration 改善 (2) selected-only 実現 EV/ROI 改善 (3) Brier/LogLoss/AUC 非劣化 or 許容幅内 (4) model-market disagreement bucket ROI/hit-rate 改善。**軽量 residual proxy**: `market_implied`/`model_p` を分位 bucket 化し同一 market bucket 内で model_p 高低による実的中率/ROI 差が残るか（p 値/回帰係数の正式結論は出さない・stop/continue 判断材料）。**両方（calibration 改善と residual proxy）が全く改善しない場合**「構造的限界寄り」で Phase 10-12 進行前に継続可否をユーザー確認。理由: 正式 logit 回帰は Phase 12 と重複・bucket proxy は既存 evaluator/segment_eval の延長で監査しやすい・「黒字化」でなく「進む価値があるか」の gate として十分。

---

## Claude's Discretion

- `points_per_second` 距離別テーブル具体値（Beyer 本式/Timeform 文献から researcher 採取）
- par/variant fallback のサンプル数下限・robust 統計量の trim 閾値（planner・live-DB 精査）
- leave-one-race-out variant の計算効率化（researcher/planner）
- stop gate「許容幅（非劣化マージン）」具体値（planner・Phase 11 SC#2 事前登録マージンと整合）
- 軽量 residual proxy の分位 bucket 数（planner）
- par/variant の normalized 層永続化 vs 中間成果物（planner・§19.1 と監査性のトレード）
- `feature_snapshot_id` 命名・v1.0 postreview-v2 系統の継承形態（planner）

## Deferred Ideas

- `rolling_speed_figure_median_*`（後続 plan・pandas/再現性/欠損の複雑化解決後）
- decay 加重 rolling speed figure（後続 refinement）
- `class_prior`/`class_par_adjustment`（SC#5 単調性確認後・必要なら後続 plan）
- 正規 falsification test `logit(outcome)~logit(market_implied)+logit(model_p)` with race_id clustered SE（Phase 12 EVAL-02）
- `p_lower` EV 判定（Phase 12 EV-01）
- 相手強度 `field_strength`（Phase 10 FEAT-02）・レース内相対 rank/gap_to_top/gap_to_3rd（Phase 10 FEAT-03）
