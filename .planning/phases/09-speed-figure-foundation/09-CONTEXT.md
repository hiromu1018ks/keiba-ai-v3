# Phase 9: Speed Figure Foundation - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

走破タイムを馬場/距離/トラック/クラス/開催日で補正した**スピード指数（Beyer 的）**を、**odds-free・PIT-correct** に自前構築し、v1.0 feature snapshot に追加可能な形で確立する。着順でなく**能力を直接測る**能力特徴量の新主軸（FEAT-01）。**SAFE-01（オッズ/人気/過去人気/過去オッズ proxy 排除）** を厳守。

素材（`time`/`kyori`/`babacd`/`trackcd`/`class_code_normalized`）は normalized 層に存在するが、**正式カラム名・品質・欠損パターン・開催日/馬場メタの実態は live-DB 精査が必須**（STATE.md Blockers 指摘済 → researcher の最初の仕事）。

**Phase 9 が届けないもの（別 Phase）:** 相手強度（FEAT-02・Phase 10）・レース内相対特徴量（FEAT-03・Phase 10）・レース内相対確率モデル（MODEL-01・Phase 11）・`p_lower` EV・正規 falsification（Phase 12）。

</domain>

<decisions>
## Implementation Decisions

### 指数の算出方式（par time / variant）
- **D-01:** 長期 par + variant（Beyer 本式）を採用。par は full-period 固定値でなく **expanding/as-of robust par**（source race 時点までに利用可能な過去レースのみで算出）。粒度は原則 `jyocd × trackcd × kyori × course_kubun`、サンプル不足時 `jyocd×trackcd×kyori` → `trackcd×kyori` の階層 fallback。
- **D-02:** variant は **target race 当日には使わず**、過去走を指数化するために `source_race_date × jyocd × surface` 単位で、source race 結果確定後の same-day residual の robust median/trimmed mean から推定。可能なら **leave-one-race-out variant**、サンプル不足時 all-day robust variant へ fallback。
- **D-03:** PIT 集約 — 各 speed figure に `available_at` を持たせ、feature row では `available_at < feature_cutoff_datetime`（= `race_date - 1day`・JST midnight・strict `<`）の指数のみ集計。**full-period par/variant と target day results の混入は禁止**（`merge_asof(direction='backward')` 相当・adversarial lookahead テスト GREEN）。
- **D-04:** **クラスは par の層別キーに入れない**（「強い馬が速い」能力差を消すため）。クラスは次カテゴリのスケール調整/variant 補助で扱う。

### スケール・クラス補正
- **D-05:** Beyer 互換ポイントスケール。**canonical feature は丸めない float**（variant 補正済みタイム差を**距離別 `points_per_second`** で変換し、速いほど大きい `speed_figure` float が主特徴量）。**モデル入力の正は float**。
- **D-06:** `speed_figure_int = round(speed_figure)` は**人間向け監査/可視化用のみ**。
- **D-07:** 監査列/中間成果物として `speed_residual_sec`（秒差）・`par_sec`・`variant_sec`・`points_per_second`・`sample_count`・`fallback_level` を保持（byte-reproducible・監査可能）。
- **D-08:** クラスは par に深く入れず補助特徴量として扱う。SC#5 でクラス別指数分布の**単調性**を確認し、必要なら後続 plan で `class_prior`/`class_par_adjustment` を追加（段階的）。理由: Beyer 型解釈性欲しい・整数丸めで秒差情報を捨てない・z-score は絶対能力値でなくなる・クラス過剰補正で能力差を消す危険。

### 馬個人の集約
- **D-09:** **latest-K 複数軸**・v1.0 `rolling.py` の per-observation latest-K algorithm（`obs_id` group・`available_at < feature_cutoff_datetime`・strict `<`）を踏襲。Phase 9 は**最小十分な 6 feature** に絞る:
  - `rolling_speed_figure_last_1`（直近状態）
  - `rolling_speed_figure_mean_3` / `rolling_speed_figure_mean_5`（安定能力）
  - `rolling_speed_figure_max_5`（潜在能力/ピーク）
  - `rolling_speed_figure_sd_5`（不安定性/ブレ）
  - `rolling_speed_figure_count_5`（信頼度）
- **D-10:** **median は追加しない**（pandas/再現性/欠損処理の複雑化回避・後続で追加）。窓は **3 と 5 のみ**（v1.0 rolling と整合・特徴量膨張抑制）。**decay 加重も後続 refinement**（まず byte-reproducible で監査しやすい集約を優先）。
- **D-11:** 欠損は既存 rolling と同じ sentinel/nullable 方針。`feature_availability.yaml` と registry↔Parquet parity に登録。feature_count は 62 → 68（+ 監査列）想定。

### stop gate（SC#6）の評価範囲
- **D-12:** **「指標比較＋軽量 residual proxy」**。正規 falsification test（clustered SE・market 再校正・正式レポート）は **Phase 12 EVAL-02 に委譲**（重複回避）。
- **D-13:** v1.0 baseline vs (v1.0+speed_figure) **単体モデル**を**同一 BT split / 同一 odds snapshot policy / 同一選択ルール**で比較（比較の公平性）。
- **D-14:** **必須4指標**: (1) odds_band×p_bin の selected/high-EV 層 calibration 改善 (2) selected-only 実現 EV/ROI 改善 (3) Brier/LogLoss/AUC の非劣化 or 許容幅内 (4) model-market disagreement bucket の ROI/hit-rate 改善。
- **D-15:** **軽量 residual proxy** — `market_implied` と `model_p` を分位 bucket 化し、同一 market bucket 内で model_p 高低による実的中率/ROI 差が残るかを見る。p 値判定/回帰係数の正式結論は出さない（Phase 10-12 へ進む stop/continue 判断材料に限定）。既存 `evaluator.py`/`segment_eval.py` の延長で実装・監査しやすい。
- **D-16:** **両方（selected/high-EV calibration 改善 と residual proxy）が全く改善しない場合**「構造的限界寄り」として Phase 10-12 進行前に**継続可否をユーザー確認**（マイルストーン目的＝市場残差能力の定量測定・鑑別に合致・早期撤退判断）。

### Claude's Discretion
- `points_per_second` の距離別テーブル具体値 — researcher が Beyer 本式/Timeform 文献から採取（短距離ほど1秒の重みが大きい）。
- par/variant fallback の**サンプル数下限**・robust 統計量の trim 閾値 — planner が live-DB 精査で決定。
- leave-one-race-out variant の**計算効率化**（全レースループ vs vectorized）— researcher/planner。
- stop gate「**許容幅**（非劣化マージン）」の具体値 — planner。Phase 11 SC#2 で事前登録される非劣化マージンとの整合に注意。
- 軽量 residual proxy の**分位 bucket 数** — planner。
- par/variant を normalized 層に永続化するか・中間成果物（Parquet/JSON）のみか — planner（§19.1 再現性聖域と監査性のトレード）。
- snapshot の `feature_snapshot_id` 命名・v1.0 `20260620-1a-postreview-v2` 系統の継承形態 — planner（v1.0 踏襲）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ロードマップ・要件（聖域）
- `.planning/ROADMAP.md` — Phase 9 section・SC#1-6（SC#2 PIT・SC#3 §12.4 metadata・SC#4 SAFE-01 proxy 排除証明・SC#5 ドメイン整合性・SC#6 stop gate）・Depends on Phase 8
- `.planning/REQUIREMENTS.md` — FEAT-01（スピード指数）・SAFE-01（odds-free/proxy 排除）・Out of Scope（過去人気/過去オッズ proxy は市場回帰で除外・2AI 一致）
- `docs/keiba_ai_requirements_v1.3.md` — 要件正（§12.4 metadata・§13 PIT/feature_availability・§14.3 categorical leak-safe・§15.2 事前登録指標不変・§19.1 再現性）
- `.planning/PROJECT.md` — Key Decisions（core value 再定式化・過去人気/オッズ proxy 除外）・Out of Scope

### 外部2AI リサーチ・文献
- `.planning/research/v1.1-domain-analysis.md` — スピード指数 P0（§4）・層分離（§5: p モデル odds-free）・falsification（§6: logit(outcome)~logit(market)+logit(model)・Codex 必須）・シナリオ（§7: 現実 0.78-0.92）・文献（§8）
- Beyer『Picking Winners』/ Beyer Speed Figure（par time・variant・points_per_second の原典）※外部書籍
- Timeform rating（斤量/着差/レース水準の能力値変換）※外部
- Rosenbloom (2003) Omega 31(5)（Beyer speed numbers を使った確率モデルと win pool の比較枠組み）※外部
- Hausch/Ziemba/Rubinstein (1981)・Bolton & Chapman (1986)・Benter (1994) — fundamental model 文献（domain-analysis §8）

### 踏襲アセット（コード・必読）
- `src/features/rolling.py` — per-observation latest-K algorithm・`obs_id` group・`strict < cutoff`・`_ROLLING_SYSTEMS`（speed_figure 6 feature の集約に直接適用）
- `src/features/builder.py` — feature builder 本体・copy-not-rename（HIGH#5）・FEATURE_COLUMNS allowlist 契約
- `src/features/snapshot.py` — §12.4 metadata・byte-reproducible Parquet 書込（新 `feature_snapshot_id`）
- `src/features/availability.py` — `_ROLLING_SYSTEMS_FOR_RESERVED`・registry↔Parquet parity
- `src/utils/pit_join.py` — `merge_asof(direction='backward')` primitive（par/variant の PIT 集約保証）
- `src/etl/normalize.py` — 素材層（`sibababacd`/`dirtbabacd`/`trackcd`/`timediff` varchar pass-through・staging-swap DDL 駆動 `_TABLE_DDL_COLUMNS`）・`time`/`kyori`/`babacd`/`class_code_normalized` の素材源
- `src/config/feature_availability.yaml` — feature availability 定義・parity 登録先
- `src/config/class_normalization.yaml` — `class_code_normalized` 機械導出（jyokencd5×gradecd×race_date）
- `src/config/label_spec.yaml` — label sentinel（参考）

### stop gate 評価（コード）
- `src/model/evaluator.py` — D-05 指標・`check_acceptance_gate`・§15.2 事前登録指標不変（calibration_max_dev 等）
- `src/model/segment_eval.py` — odds_band×p_bin・6軸 segment・binning 契約（`_compute_calibration_curve_bins`/`_compute_ece`/`_compute_mce`）・Plotly HTML+JSON
- `src/model/trainer.py` — LightGBM/CatBoost 学習（単体モデル再利用）
- `src/model/data.py` — `FEATURE_COLUMNS` allowlist・`make_X_y`（FEATURE_COLUMNS 完全一致 assert）
- `src/audit/report.py`・`tests/audit/` — adversarial audit（AST read-only・allowlist grep・SC#1/#2/#3 踏襲）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/features/rolling.py`: per-observation latest-K algorithm を `rolling_speed_figure_*` 6 feature にそのまま適用（`obs_id` group・strict `<cutoff` で PIT 保証）。
- `src/utils/pit_join.py`: `merge_asof(direction='backward')` で `available_at < cutoff` を保証（par/variant の expanding/as-of 集約）。
- `src/features/snapshot.py`: §12.4 metadata + byte-reproducible Parquet 書込（新 `feature_snapshot_id`・SHA256・metadata 除外再計算）。
- `src/features/availability.py` + `feature_availability.yaml`: `rolling_speed_figure_*` の registry↔Parquet parity 登録（`_ROLLING_SYSTEMS_FOR_RESERVED` 拡張）。
- `src/etl/normalize.py`: staging-swap DDL 駆動で素材カラム取り込み済み。`course_kubun`/`surface` 派生が未確認 → researcher が精査（par 粒度 `jyocd×trackcd×kyori×course_kubun` に必要）。
- `src/model/evaluator.py` + `segment_eval.py`: stop gate の4指標・odds_band×p_bin bucketing を再利用（binning 契約固定・bit-identical）。
- `src/model/trainer.py` + `data.py`: v1.0+speed_figure 単体モデル学習（FEATURE_COLUMNS allowlist 拡張）。

### Established Patterns
- **per-observation latest-K rolling**（`obs_id` group・strict `<cutoff`）— speed_figure 集約の PIT 保証（CYCLE-2 HIGH#1 cross-obs leak 回避）。
- **copy-not-rename builder** + FEATURE_COLUMNS allowlist（§14.3）— 新 feature 追加時の契約（fake-green 防止）。
- **staging-swap idempotent ETL** + raw read-only（D-06 不変・REVOKE+fingerprint）— 素材取り込み。
- **byte-reproducible snapshot**（`FIXED_REPRODUCE_TS`・SHA256・metadata 除外）— §19.1 聖域。
- **category_map JSON**（`sort_keys=True`・`__UNSEEN__`/`__MISSING__` sentinel）— categorical（speed figure 自身は float だが、素材 categorical は踏襲）。
- **adversarial audit**（AST read-only・allowlist grep・SC#1/#2/#3）— SAFE-01 proxy 排除証明。
- `CalibratedClassifierCV(estimator=...)` + `FrozenEstimator`（sklearn 1.9.0）— later-disjoint calibration（stop gate 比較時）。

### Integration Points
- `builder.py`（feature 生成）→ `snapshot.py`（Parquet 永続化）→ `trainer`/`evaluator`（モデル入力）の既存パイプラインに `rolling_speed_figure_*` を挿入。
- 新 `rolling_speed_figure_*` 6 feature を `_ROLLING_SYSTEMS` / `feature_availability.yaml` / registry に追加（3者 parity）。
- stop gate は `evaluator`/`segment_eval` の既存 segment 軸（odds_band×p_bin）を v1.0 vs +speed_figure 比較に適用。
- prediction/backtest テーブルは `model_version`-scoped swap（HIGH#1）— Phase 9 単体モデルは別 `model_version`（`make_model_version` 形式 `{feature_snapshot_id}-{short}-v{N}`）。

### Creative options
- par/variant を **normalized 層に永続化**するか・**中間成果物**（Parquet/JSON）のみか — planner 判断（再現性聖域と監査性のトレード）。
- **leave-one-race-out variant** の計算戦略（全レースループ vs vectorized as-of）— researcher。
- `course_kubun`/`surface` が normalized 層に無ければ ETL 拡張（Phase 3.1 の `timediff`/`babacd` pass-through パターン踏襲）か・`trackcd` から派生か — researcher が live-DB で判定。

</code_context>

<specifics>
## Specific Ideas

- **Beyer 本式の par/variant 分離を正統実装**（par は距離×トラック長期標準・variant は開催日馬場差）するが、**PIT 制約から par/variant とも expanding/as-of で算出**（full-period 固定値禁止）。これが v1.0 odds-free パイプラインとの整合の核心。
- **クラスを par 層別に入れない**（D-04/D-08）はユーザーの明示的判断。domain-analysis の「クラス補正」と一見矛盾するが「par 層別でなく指数スケール/variant 補助で」という精密化（強い馬が速い能力差を消さない）。
- **Phase 9 は最小十分**（median/decay/正式 falsification を後続に回す）の一貫方針。まず byte-reproducible で監査しやすい集約を優先（ユーザー反復指示）。
- stop gate は「黒字化」でなく「**Phase 10-12 に進む価値があるか**」を判定する gate（domain-analysis §7 現実シナリオ 0.78-0.92・正直な結論）。

</specifics>

<deferred>
## Deferred Ideas

- `rolling_speed_figure_median_*`（pandas/再現性/欠損処理の複雑化解決後・後続 plan）
- decay 加重 rolling speed figure（refinement・後続 plan）
- `class_prior` / `class_par_adjustment`（SC#5 クラス別指数分布の単調性確認後・必要なら後続 plan）
- 正規 falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` with race_id clustered SE・market 再校正・正式レポート（Phase 12 EVAL-02）
- `p_lower` による EV 判定（Phase 12 EV-01）
- 相手強度 `field_strength`（Phase 10 FEAT-02）・レース内相対 rank/gap_to_top/gap_to_3rd（Phase 10 FEAT-03）

*None folded from todos — discussion stayed within phase scope（todo.match-phase 0 件）*

</deferred>

---

*Phase: 9-Speed Figure Foundation*
*Context gathered: 2026-06-25*
