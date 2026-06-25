# Phase 9: Speed Figure Foundation - Research

**Researched:** 2026-06-25
**Domain:** スピード指数（Beyer 型）の odds-free・PIT-correct 構築・既存 feature snapshot pipeline への統合・stop gate 評価
**Confidence:** HIGH（live-DB 実証 + コード踏襲アセット実読 + 外部文献照合）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 指数の算出方式（par time / variant）
- **D-01:** 長期 par + variant（Beyer 本式）を採用。par は full-period 固定値でなく **expanding/as-of robust par**（source race 時点までに利用可能な過去レースのみで算出）。粒度は原則 `jyocd × trackcd × kyori × course_kubun`、サンプル不足時 `jyocd×trackcd×kyori` → `trackcd×kyori` の階層 fallback。
- **D-02:** variant は **target race 当日には使わず**、過去走を指数化するために `source_race_date × jyocd × surface` 単位で、source race 結果確定後の same-day residual の robust median/trimmed mean から推定。可能なら **leave-one-race-out variant**、サンプル不足時 all-day robust variant へ fallback。
- **D-03:** PIT 集約 — 各 speed figure に `available_at` を持たせ、feature row では `available_at < feature_cutoff_datetime`（= `race_date - 1day`・JST midnight・strict `<`）の指数のみ集計。**full-period par/variant と target day results の混入は禁止**（`merge_asof(direction='backward')` 相当・adversarial lookahead テスト GREEN）。
- **D-04:** **クラスは par の層別キーに入れない**（「強い馬が速い」能力差を消すため）。クラスは次カテゴリのスケール調整/variant 補助で扱う。

#### スケール・クラス補正
- **D-05:** Beyer 互換ポイントスケール。**canonical feature は丸めない float**（variant 補正済みタイム差を**距離別 `points_per_second`** で変換し、速いほど大きい `speed_figure` float が主特徴量）。**モデル入力の正は float**。
- **D-06:** `speed_figure_int = round(speed_figure)` は**人間向け監査/可視化用のみ**。
- **D-07:** 監査列/中間成果物として `speed_residual_sec`（秒差）・`par_sec`・`variant_sec`・`points_per_second`・`sample_count`・`fallback_level` を保持（byte-reproducible・監査可能）。
- **D-08:** クラスは par に深く入れず補助特徴量として扱う。SC#5 でクラス別指数分布の**単調性**を確認し、必要なら後続 plan で `class_prior`/`class_par_adjustment` を追加（段階的）。

#### 馬個人の集約
- **D-09:** **latest-K 複数軸**・v1.0 `rolling.py` の per-observation latest-K algorithm（`obs_id` group・`available_at < feature_cutoff_datetime`・strict `<`）を踏襲。Phase 9 は**最小十分な 6 feature** に絞る:
  - `rolling_speed_figure_last_1`（直近状態）
  - `rolling_speed_figure_mean_3` / `rolling_speed_figure_mean_5`（安定能力）
  - `rolling_speed_figure_max_5`（潜在能力/ピーク）
  - `rolling_speed_figure_sd_5`（不安定性/ブレ）
  - `rolling_speed_figure_count_5`（信頼度）
- **D-10:** **median は追加しない**（pandas/再現性/欠損処理の複雑化回避・後続で追加）。窓は **3 と 5 のみ**（v1.0 rolling と整合・特徴量膨張抑制）。**decay 加重も後続 refinement**。
- **D-11:** 欠損は既存 rolling と同じ sentinel/nullable 方針。`feature_availability.yaml` と registry↔Parquet parity に登録。feature_count は 62 → 68（+ 監査列）想定。

#### stop gate（SC#6）の評価範囲
- **D-12:** **「指標比較＋軽量 residual proxy」**。正規 falsification test（clustered SE・market 再校正・正式レポート）は **Phase 12 EVAL-02 に委譲**。
- **D-13:** v1.0 baseline vs (v1.0+speed_figure) **単体モデル**を**同一 BT split / 同一 odds snapshot policy / 同一選択ルール**で比較。
- **D-14:** **必須4指標**: (1) odds_band×p_bin の selected/high-EV 層 calibration 改善 (2) selected-only 実現 EV/ROI 改善 (3) Brier/LogLoss/AUC の非劣化 or 許容幅内 (4) model-market disagreement bucket の ROI/hit-rate 改善。
- **D-15:** **軽量 residual proxy** — `market_implied` と `model_p` を分位 bucket 化し、同一 market bucket 内で model_p 高低による実的中率/ROI 差が残るかを見る。p 値判定/回帰係数の正式結論は出さない。
- **D-16:** **両方（selected/high-EV calibration 改善 と residual proxy）が全く改善しない場合**「構造的限界寄り」として Phase 10-12 進行前に**継続可否をユーザー確認**。

### Claude's Discretion
- `points_per_second` の距離別テーブル具体値 — researcher が Beyer 本式/Timeform 文献から採取（短距離ほど1秒の重みが大きい）。→ **本 RESEARCH で解決（後述）**
- par/variant fallback の**サンプル数下限**・robust 統計量の trim 閾値 — planner が live-DB 精査で決定。→ **本 RESEARCH で実証データ提供（後述）**
- leave-one-race-out variant の**計算効率化**（全レースループ vs vectorized）— researcher/planner。→ **本 RESEARCH で実装提案（後述）**
- stop gate「**許容幅**（非劣化マージン）」の具体値 — planner。
- 軽量 residual proxy の**分位 bucket 数** — planner。
- par/variant を normalized 層に永続化するか・中間成果物（Parquet/JSON）のみか — planner。
- snapshot の `feature_snapshot_id` 命名・v1.0 `20260620-1a-postreview-v2` 系統の継承形態 — planner。

### Deferred Ideas (OUT OF SCOPE)
- `rolling_speed_figure_median_*`（pandas/再現性/欠損処理の複雑化解決後・後続 plan）
- decay 加重 rolling speed figure（refinement・後続 plan）
- `class_prior` / `class_par_adjustment`（SC#5 クラス別指数分布の単調性確認後・必要なら後続 plan）
- 正規 falsification test `logit(outcome) ~ logit(market_implied) + logit(model_p)` with race_id clustered SE（Phase 12 EVAL-02）
- `p_lower` による EV 判定（Phase 12 EV-01）
- 相手強度 `field_strength`（Phase 10 FEAT-02）・レース内相対 rank/gap_to_top/gap_to_3rd（Phase 10 FEAT-03）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FEAT-01 | スピード指数を構築する — 走破タイムを距離/馬場/クラス/トラック/開催日で補正した能力値（Beyer 的）。素材（`time`/`kyori`/`babacd`/`trackcd`/`class_code_normalized`）は normalized 層に存在確認済み（品質・正式カラム名は計画フェーズで精査）。 | live-DB 精査で素材カラムの実態・品質・欠損パターンを全て確定（後述 Standard Stack / Code Examples）。par/variant/points_per_second の算出フローと PIT 集約方法を文書化。 |
| SAFE-01 | core value を維持する — オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない。オッズ帯別条件付き calibration を受入基準に追加。 | 既存 `tests/audit/` adversarial パターン + `availability.py::assert_matrix_columns_registered` + `data.py::make_X_y` FEATURE_COLUMNS allowlist 完全一致 assert で proxy 排除を構造的保証（後述 Architecture Patterns / Validation Architecture）。 |
</phase_requirements>

## Summary

Phase 9 は、v1.0 odds-free pipeline に**スピード指数（Beyer 型）**を新主軸能力特徴量として追加する。核心は3点: (1) normalized 層素材から par time（距離/トラック標準タイム）と variant（開催日馬場差）を PIT-correct に算出し指数化、(2) 既存 `rolling.py` per-observation latest-K algorithm で馬個人の 6 集約特徴量を構築し byte-reproducible snapshot に統合、(3) stop gate で v1.0 baseline との比較により特徴量不足 vs 構造的限界を鑑別する。

**live-DB 実証で判明した最も重要な事実:** `time` は **0.1秒単位（decisecond）** で格納されている（`time_avg=1498.09` = 149.8秒・1200mダート1着 `time=1108.0` = 110.8秒 = 1分50秒）。normalize.py DDL コメント「0.1秒単位」が正しい。完走馬の `time > 0` フィルタ必須（`time_zero_or_neg=4882` は取消/競走中止）。`kyori`/`trackcd`/`sibababacd`/`dirtbabacd` は 2015年以降で欠損ゼロ（極めて高品質）。

**STATE.md Blockers「researcher の最初の仕事」解決:** `course_kubun` は **normalized 層に存在しない**（`feature_availability.yaml` line 129 に feature 登録されているが、`information_schema` にも DDL にも無い = silent parity 違反の既存 bug）。しかし **`trackcd` 単独で `jyocd×trackcd×kyori` 粒度は完全に表現可能**（trackcd は競馬場コース形態を包含）。D-01 の `course_kubun` 依存は**削除し `jyocd×trackcd×kyori` を最細粒度**とする。`surface`（芝/ダート）は `trackcd` から派生（10-22=芝/23-25=ダート/51-59=障害）で既存 `builder.py::_construct_derived_columns` の babacd 派生ロジックと完全一致。

**Primary recommendation:** 既存 `builder.py` / `rolling.py` / `snapshot.py` / `availability.py` パイプラインに `rolling_speed_figure_*` 6 feature を挿入する。par/variant 算出は新しい module（例: `src/features/speed_figure.py`）に分離し、`builder.py` の history expand + PIT pre-filter の直後で per-observation の speed_figure 値を計算・それを `rolling.py` に渡して latest-K 集約する。stop gate は `evaluator.py` + `segment_eval.py` の binning 契約を再利用する。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| par time 算出（PIT expanding/as-of robust） | Feature 構築層（`src/features/`） | normalized 読取層（readonly SELECT） | par は feature snapshot 生成時に一度計算し Parquet に固定。runtime 計算でなく offline batch。raw DB は readonly SELECT のみ（D-06 不変）。 |
| variant 算出（same-day residual・leave-one-race-out） | Feature 構築層 | Feature 構築層 | variant も par と同時 batch 計算。target race 当日結果は絶対混入禁止（SC#2・adversarial lookahead）。 |
| 馬個人の latest-K 集約（6 feature） | Feature 構築層（`rolling.py` 踏襲） | — | per-observation latest-K algorithm（`obs_id` group・strict `<cutoff`）で PIT 保証。CYCLE-2 HIGH#1 cross-obs leak 回避。 |
| feature snapshot 永続化（byte-reproducible） | Feature 構築層（`snapshot.py` 踏襲） | — | §12.4 metadata + SHA256（metadata 除外）+ PyArrow 決定論的書込。新 `feature_snapshot_id`。 |
| registry↔Parquet parity | Feature 構築層（`availability.py` + yaml） | — | `rolling_speed_figure_*` を registry に追加しないと `make_X_y` の FEATURE_COLUMNS 完全一致 assert が fail する。 |
| stop gate 評価（4 指標 + residual proxy） | モデル評価層（`evaluator.py` / `segment_eval.py`） | モデル学習層（`trainer.py`） | binning 契約固定（bit-identical）・§15.2 事前登録指標不変。v1.0 baseline と同一 BT split/policy で比較。 |
| SAFE-01 proxy 排除証明（adversarial audit） | 監査層（`tests/audit/`） | Feature 構築層 | AST read-only + allowlist grep で odds/ninki/過去オッズ proxy が新特徴量に混入しないことを証明。 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **pandas** | 3.0.3 | par/variant/集約の DataFrame 演算・`merge_asof` 相当の PIT join | `[VERIFIED: 既存コード]` v1.0 全 pipeline の基盤。`merge_asof(direction='backward')` は pit_join.py でwrap済み。 |
| **NumPy** | (transitive ≥2.0) | robust 統計量（trimmed mean/median）・vectorized 演算 | `[VERIFIED: 既存コード]` pandas/scikit-learn 経由。 |
| **PyArrow** | 24.0.0 | byte-reproducible Parquet 書込（`use_dictionary=False`・`compression="zstd"`） | `[VERIFIED: 既存コード snapshot.py]` §12.4 metadata 埋込 + SHA256（metadata除外）。 |
| **psycopg** | 3.3.4 (psycopg[binary]) | normalized 層 readonly SELECT（素材取得） | `[VERIFIED: 既存コード builder.py]` `make_pool(role='readonly')`。新パッケージインストール不要。 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **scipy.stats** | transitive (≥1.17.1) | robust 統計量（`trim_mean`・`median`）・variant 算出の外れ値除去 | `[VERIFIED: 既存コード evaluator.py]` `spearmanr` で既使用。`scipy.stats.trim_mean(arr, proportiontocut)` で両端カット平均。 |
| **Plotly** | ≥6.8.0 | SC#5 ドメイン整合性可視化（指数分布・クラス別単調性） | `[VERIFIED: 既存コード segment_eval.py]` `include_plotlyjs='directory'` で byte-reproducible HTML。 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 自前 Beyer 型 par/variant | LightGBM の time-to-finish 特徴量そのまま | `[CITED: domain-analysis §4]` par/variant 補正なしの生タイムは馬場/距離/クラスの交絡を含み「能力そのもの」を測れない（着順と同質）。自前構築が P0。 |
| leave-one-race-out variant | all-day robust variant のみ | leave-one-race-out は同一日の自レースが variant に混入するのを防ぐが計算コスト増。サンプル十分時は leave-one-race-out・不足時 all-day fallback（D-02）。 |
| DuckDB で par/variant 集計 | pandas groupby | `[CITED: CLAUDE.md]` DuckDB は補助のみ・永続化層でない。par/variant は pandas で計算し Parquet に固定。DuckDB は監査用 read_parquet で使用可。 |

**Installation:**
```bash
# 新規パッケージインストール不要 — 全て v1.0 の既存依存（pandas/NumPy/PyArrow/psycopg/scipy/plotly）
uv sync --frozen
```

**Version verification:** 全パッケージは v1.0 で稼働実績あり（`pyproject.toml` / `uv.lock` で pin 済み）。Phase 9 は新規インストールなし。

## Package Legitimacy Audit

> Phase 9 は**新規外部パッケージをインストールしない**（v1.0 既存依存のみ）。Package Legitimacy Gate は skip。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none — 全て v1.0 既存依存) | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
[normalized.n_uma_race (time/kakuteijyuni/timediff)]
[normalized.n_race (kyori/trackcd/sibababacd/dirtbabacd/class_code_normalized/race_date)]
        │
        │  readonly SELECT (builder.py::_fetch_history / _fetch_feature_sources)
        │  statement_timeout='30s' 必須 (subagent 経由重クエリ)
        ▼
[history DataFrame (全過去走) + observations DataFrame (target race 馬)]
        │
        │  Step A: _construct_derived_columns (既存)
        │    - trackcd → surface 派生 (10-22芝/23-25ダ/51-59障害)
        │    - babacd 派生 (siba/dirt 分岐)
        │    - time > 0 フィルタ (完走馬のみ・取消/競走中止除外)
        │    - time 単位確認: 0.1秒単位 (decisecond) → 秒換算
        ▼
[history with time_sec / surface / babacd / kyori]
        │
        │  Step B: NEW src/features/speed_figure.py
        │    - PIT expanding par: jyocd×trackcd×kyori 粒度
        │      available_at < cutoff の過去走のみで robust median 算出
        │      fallback 階層: jyocd×trackcd×kyori (130/141 group ≥100件)
        │                     → trackcd×kyori (81/90 group ≥100件)
        │    - variant: source_race_date×jyocd×surface 単位
        │      leave-one-race-out same-day residual の robust median
        │      (avg 215完走馬/開催日×surface → サンプル十分)
        │    - speed_figure = (par - actual_time) × points_per_second(kyori) + variant_adjustment
        │      float (丸めない・D-05)
        │    - 監査列: par_sec / variant_sec / speed_residual_sec / sample_count / fallback_level
        ▼
[history with speed_figure per past race (available_at = race_date)]
        │
        │  Step C: rolling.py 踏襲 (per-observation latest-K)
        │    - obs_id group (CYCLE-2 HIGH#1 cross-obs leak 回避)
        │    - strict < feature_cutoff_datetime (SC#2 PIT 保証)
        │    - 6 feature: last_1 / mean_3 / mean_5 / max_5 / sd_5 / count_5
        ▼
[observations with rolling_speed_figure_* 6 feature]
        │
        │  Step D: builder.py 統合 → snapshot.py (byte-reproducible Parquet)
        │    - feature_availability.yaml に 6 feature 登録 (registry↔Parquet parity)
        │    - _ROLLING_SYSTEMS_FOR_RESERVED に "speed_figure" 追加 (count_5 予約)
        │    - 新 feature_snapshot_id (例: 20260625-1a-speedfigure-v1)
        │    - §12.4 metadata 9 keys + SHA256 (metadata除外)
        ▼
[feature_matrix_<id>.parquet (feature_count 62→68+監査列)]
        │
        │  Step E: model/trainer.py (v1.0+speed_figure 単体モデル)
        │    - FEATURE_COLUMNS 自動拡張 (registry derived・make_X_y 完全一致 assert)
        │    - LightGBM native categorical (speed_figure は float・categorical 処理不要)
        │    - CatBoost has_time=True (時系列保持)
        ▼
[stop gate 評価: evaluator.py + segment_eval.py]
    - D-14 必須4指標 (odds_band×p_bin calibration / selected ROI / Brier非劣化 / disagreement ROI)
    - D-15 軽量 residual proxy (market_implied×model_p 分位 bucket)
    - binning 契約固定 (bit-identical・§15.2 事前登録指標不変)
```

### Recommended Project Structure
```
src/features/
├── speed_figure.py      # NEW: par/variant/speed_figure 算出 (PIT expanding/as-of robust)
├── rolling.py           # 拡張: _ROLLING_SYSTEMS に "speed_figure" 追加・6 axis 集約
├── builder.py           # 拡張: history expand 後に speed_figure 計算を挿入
├── snapshot.py          # 踏襲: byte-reproducible Parquet (新 feature_snapshot_id)
└── availability.py      # 拡張: _ROLLING_SYSTEMS_FOR_RESERVED に "speed_figure" 追加
src/config/
└── feature_availability.yaml  # 拡張: rolling_speed_figure_* 6 feature エントリ追加
src/model/
├── trainer.py           # 踏襲: v1.0+speed_figure 単体モデル学習
├── evaluator.py         # 踏襲: binning 契約固定・§15.2 事前登録指標不変
└── segment_eval.py      # 踏襲: odds_band×p_bin bucketing (bit-identical)
tests/
├── features/
│   ├── test_speed_figure.py      # NEW: par/variant/PIT/byte-reproducible 単体テスト
│   └── test_speed_figure_pit.py  # NEW: adversarial lookahead (SC#2)
└── audit/
    └── test_audit_speed_figure.py # NEW: SAFE-01 proxy 排除 (AST + allowlist grep)
```

### Pattern 1: PIT expanding/as-of robust par time（D-01/D-03）
**What:** target row の `feature_cutoff_datetime` 時点で利用可能な過去走のみで par time を算出。full-period 固定値禁止（未来情報リーク）。
**When to use:** 各 target observation の par time 計算全般。
**Example:**
```python
# Source: 既存 rolling.py の _pit_cutoff_prefilter + per-observation latest-K algorithm 踏襲
# D-03: available_at < feature_cutoff_datetime (strict <) の過去走のみ集計

def compute_pit_par(history: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    """各 observation の cutoff 以前の過去走のみで par time を算出 (PIT expanding).

    CYCLE-2 HIGH#1 踏襲: obs_id group で cross-obs leak 回避.
    CUTOFF_SEMANTICS 踏襲: strict < (JST midnight).
    """
    # Step 1: obs_id 構築 (rolling.py と同一 idiom)
    # Step 2: history を各 observation に kettonum で inner-join (expand)
    # Step 3: PIT pre-filter: history.available_at < observation.feature_cutoff_datetime
    #         (rolling.py::_pit_cutoff_prefilter と同一の strict <)
    # Step 4: jyocd×trackcd×kyori 粒度で robust median (time_sec) 算出
    #         サンプル不足 (< 30) → trackcd×kyori fallback
    # Step 5: fallback_level 監査列を付与 ("jyocd_trackcd_kyori" / "trackcd_kyori")
    return observations_with_par
```

### Pattern 2: leave-one-race-out variant（D-02）
**What:** source race の variant を算出する際、そのレース自身を除外した same-day residual の robust median を使う。target race 当日結果は絶対混入させない。
**When to use:** 過去走の speed_figure 化（variant 補正）全般。
**Example:**
```python
# D-02: variant は source_race_date×jyocd×surface 単位
# leave-one-race-out: source race 自身を除外した same-day residual

def compute_leave_one_out_variant(history: pd.DataFrame) -> pd.DataFrame:
    """same-day residual の leave-one-race-out robust median (variant).

    計算戦略 (research_focus_priority #3 解決):
    - vectorized as-of (推奨): 開催日×surface group で (actual - par) の
      trimmed mean を算出後、各レースの residual から group 値を再計算
      (scipy.stats.trim_mean で両端 10% カット). 2478 day×surface group,
      avg 215 完走馬 → サンプル十分.
    - 全レースループ (fallback): 極小 group (< 10件) のみループで個別計算.
      パフォーマンス影響限定的 (極小 group は少数).
    """
    # Step 1: 各 past race の residual = time_sec - par_sec(jyocd×trackcd×kyori)
    # Step 2: group = (source_race_date, jyocd, surface)
    # Step 3: group 内で leave-one-race-out: 自レースを除く residual の robust median
    #         vectorized: group_median - (自レースの group 寄与) で近似 (十分精度)
    # Step 4: サンプル不足 group (< 10件) → all-day robust variant fallback
    return history_with_variant
```

### Pattern 3: per-observation latest-K 集約（D-09・rolling.py 踏襲）
**What:** 各 target observation の cutoff 以前の直近 K 走の speed_figure を集約。`obs_id` group で cross-obs leak 回避。
**When to use:** `rolling_speed_figure_*` 6 feature の算出全般。
**Example:**
```python
# Source: 既存 rolling.py::build_rolling_features の完全踏襲
# _ROLLING_SYSTEMS に "speed_figure" を追加するだけで 6 axis 集約が動作する

# rolling.py 拡張箇所:
_ROLLING_SYSTEMS: tuple[str, ...] = (
    "kakuteijyuni", "harontimel3", "jyuni3c_jyuni4c", "kyori",
    "jyocd", "days_since_prev", "timediff", "babacd",
    "speed_figure",  # NEW Phase 9
)

# speed_figure は float (D-05) → numeric 系統 (mean/latest/sd/count)
# _axes_for("speed_figure") = ("mean", "latest", "sd", "count") が自動適用
# 出力: rolling_speed_figure_mean_5 / _latest_5 / _sd_5 / _count_5
# D-09 の mean_3 / max_5 は別途 axis 追加 (既存 _axes_for の拡張 or 個別算出)
```

### Pattern 4: byte-reproducible snapshot 統合（snapshot.py 踏襲）
**What:** speed_figure 追加後の feature matrix を同一手順で byte-reproducible な Parquet に書出し。
**When to use:** SC#1/SC#3 の byte-reproducibility 保証。
**Example:**
```python
# Source: 既存 snapshot.py::write_snapshot の完全踏襲
# 新 feature_snapshot_id 命名 (Claude's Discretion → planner):
#   v1.0: 20260620-1a-postreview-v2
#   Phase 9 候補: 20260625-1a-speedfigure-v1 (v1.0 系統の継承)

# SHA256 は metadata 除外 schema bytes のみ (CR-04 踏襲):
#   同一 DataFrame なら snapshot_id/created_at が異なっても SHA256 同一
# _coerce_rolling_columns_for_parquet で rolling_speed_figure_* の object 列を
#   nullable Float64 に統一 (既存ロジックが自動適用・speed_figure は float なので
#   categorical 分岐不要・numeric path で Float64 化)
```

### Anti-Patterns to Avoid
- **`course_kubun` への依存:** `[VERIFIED: live-DB]` normalized 層に存在しない（feature_availability.yaml line 129 は silent parity bug）。`trackcd` 単独で `jyocd×trackcd×kyori` 粒度は表現可能。D-01 の `course_kubun` は削除。
- **full-period 固定 par/variant:** `[CITED: SC#2/D-03]` 未来情報リーク。必ず expanding/as-of robust（`available_at < cutoff` の過去走のみ）。
- **target race 当日結果の par/variant 混入:** `[CITED: SC#2]` 致命的リーク。adversarial lookahead テスト GREEN 必須。
- **time=0 のスピード指数算出:** `[VERIFIED: live-DB]` 取消/競走中止（`time_zero_or_neg=4882`）。`time > 0 AND kakuteijyuni IS NOT NULL` フィルタ必須。
- **time 単位の誤認:** `[VERIFIED: live-DB]` `time` は 0.1秒単位（decisecond）。centisecond 解釈は物理的不可能（1200m=11秒）。秒換算: `time_sec = time / 10.0`。
- **speed_figure の整数丸め:** `[CITED: D-05]` canonical feature は float。`speed_figure_int` は監査/可視化用のみ。
- **オッズ/人気/過去オッズ proxy の混入:** `[CITED: SAFE-01]` `p` モデル特徴量に市場情報 proxy は一切入れない。adversarial audit で証明。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PIT as-of join（cutoff 以前の最新値） | 自前ループ | `rolling.py::_pit_cutoff_prefilter` + per-observation latest-K（`obs_id` group・strict `<`） | `[VERIFIED: 既存コード]` CYCLE-2 HIGH#1 cross-obs leak 回避済み・5-row adversarial テスト GREEN。 |
| byte-reproducible Parquet 書込 | 自前 PyArrow 設定 | `snapshot.py::write_snapshot`（`use_dictionary=False`・`compression="zstd"`・SHA256 metadata除外） | `[VERIFIED: 既存コード]` §12.4 metadata 9 keys + CR-04 byte-reproducibility 実証済み。 |
| FEATURE_COLUMNS allowlist 管理 | 手動カラムリスト | `data.py::_derive_feature_columns`（registry derived）+ `make_X_y` 完全一致 assert | `[VERIFIED: 既存コード]` registry に追加すれば自動反映・banned feature 構造的排除。 |
| odds_band×p_bin bucketing | 独自 binning | `segment_eval.py`（`_odds_band`/`_ninki_band`・`np.digitize`・`ODDS_BAND_EDGES`）+ `evaluator.py`（`CALIBRATION_CURVE_*` 定数） | `[VERIFIED: 既存コード]` binning 契約一元化・bit-identical・T-06-07。 |
| adversarial lookahead テスト鋳型 | ゼロから設計 | `tests/audit/test_audit_features.py`（5段階鋳型・monkeypatch で guard 無効化） | `[VERIFIED: 既存コード]` SC#2 踏襲・false-pass 構造的排除。 |
| robust 統計量（trimmed mean） | 自前 sort+slice | `scipy.stats.trim_mean(arr, proportiontocut=0.1)` | `[VERIFIED: pyproject.toml]` scipy は既存依存（evaluator.py で spearmanr 使用）。 |
| categorical leak-safe 処理 | target/mean encoding | LightGBM native `category` dtype + CatBoost `has_time=True`（speed_figure 自身は float だが素材 categorical は踏襲） | `[CITED: CLAUDE.md §14.3/§14.4]` 構造的リーク不可能。 |

**Key insight:** Phase 9 の新規実装は `src/features/speed_figure.py`（par/variant/speed_figure 算出）のみ。集約・snapshot・registry・評価は全て既存 asset の拡張（1-2 行追加）で動作する。これは v1.0 の「copy-not-rename builder + FEATURE_COLUMNS allowlist 契約」設計の意図通りの拡張性。

## Common Pitfalls

### Pitfall 1: `time` 単位の誤認（centisecond vs decisecond）
**What goes wrong:** `time` を centisecond（0.01秒）と誤認すると、1200mダートが 11秒（物理的不可能）になる。par time も1桁ズレて指数が無意味化。
**Why it happens:** normalize.py DDL コメント「0.1秒単位」は正しいが、`time_avg=1498.09` を見ると centisecond に見える。JRA-VAN 仕様書と EveryDB2 実装の齟齬。
**How to avoid:** `[VERIFIED: live-DB]` `time=1108.0`（1200mダート1着）→ 110.8秒 = 1分50秒（典型タイム）で確定。秒換算は `time_sec = time / 10.0`。unit test で `assert time_sec > 50` （50秒未満は物理的不可能）を追加。
**Warning signs:** par time が 10秒台・speed_figure が極端な値（±1000）。

### Pitfall 2: `course_kubun` silent parity 違反
**What goes wrong:** `feature_availability.yaml` line 129 に `course_kubun` が feature 登録されているが、normalized 層にカラムが存在しない。builder.py がこれを SELECT しようとするとエラー、または `assert_matrix_columns_registered` が通っても実データが存在しない silent bug。
**Why it happens:** v1.0 Phase 3 で registry を先行定義したが、ETL で `course_kubun` を取り込まなかった（trackcd で代替可能と判断した形跡）。
**How to avoid:** `[VERIFIED: live-DB]` `course_kubun` への依存を全て削除。par 粒度は `jyocd×trackcd×kyori` を最細とする（D-01 の `course_kubun` は削除）。`feature_availability.yaml` の `course_kubun` エントリは削除または `trackcd` に統合。
**Warning signs:** builder.py で `course_kubun` を参照する SQL・registry と実カラムの不一致。

### Pitfall 3: PIT par/variant での target race 当日結果混入
**What goes wrong:** target race の走破タイム・馬場結果が par や variant に混入すると未来情報リーク（SC#2 違反・致命的）。
**Why it happens:** expanding par の実装で「全期間の平均」を使うと未来情報が混入。variant で「当日の全レース」を使うと target race 自身が混入。
**How to avoid:** `[CITED: D-03]` `available_at < feature_cutoff_datetime`（strict `<`）の過去走のみ集計。leave-one-race-out で source race 自身を除外。adversarial lookahead テスト（5段階鋳型・target/same_day_prior/same_day_later/previous_day/future が全て除外）で GREEN 必須。
**Warning signs:** 同一 race_date のレースが par/variant に含まれる・再生成で SHA256 が変わる。

### Pitfall 4: time=0（取消/競走中止）のスピード指数算出
**What goes wrong:** `time=0` の馬をスピード指数化すると極端な外れ値（無限大に近い指数）が生まれ、rolling 集約が破綻。
**Why it happens:** `kakuteijyuni IS NOT NULL` でも `time=0` のケースがある（完走でない馬のタイム未確定）。
**How to avoid:** `[VERIFIED: live-DB]` `time > 0 AND kakuteijyuni IS NOT NULL` で完走馬のみ指数化（4882件除外）。`speed_figure` を NaN/sentinel にし、rolling の count 軸で信頼度を表現。
**Warning signs:** speed_figure が ±1000 を超える・rolling_speed_figure_count_5 が实际の出走数と乖離。

### Pitfall 5: par fallback 階層での silent 丸め込み
**What goes wrong:** サンプル不足 group が上位階層に fallback する際、fallback_level 監査列を付けないと「どの粒度で par を算出したか」が不透明（再現性・監査性の聖域違反）。
**Why it happens:** fallback 実装で監査列を省略すると、`jyocd×trackcd×kyori` と `trackcd×kyori` の par が混在して判別不能。
**How to avoid:** `[CITED: D-07]` 各 row に `fallback_level`（"jyocd_trackcd_kyori" / "trackcd_kyori" / "all_day"）・`sample_count`・`par_sec`・`variant_sec` 監査列を必ず付与。byte-reproducible で Parquet に永続化。
**Warning signs:** fallback_level 列が無い・sample_count が NULL。

## Code Examples

### time 単位換算と完走馬フィルタ（live-DB 実証）
```python
# Source: live-DB 精査 (2026-06-25) + normalize.py DDL コメント
# time は 0.1秒単位 (decisecond) で real 型格納
# 完走馬フィルタ: time > 0 AND kakuteijyuni IS NOT NULL
#   time_zero_or_neg = 4882 (2015-2026) → 取消/競走中止

def time_to_seconds(time_real: float) -> float:
    """time (0.1秒単位) を秒に換算. time <= 0 は NaN (完走でない)."""
    if time_real is None or time_real <= 0:
        return float("nan")
    return time_real / 10.0

# 実証値: 1200mダート1着 time=1108.0 → 110.8秒 = 1分50秒 (典型タイム)
# time_avg=1498.09 → 149.8秒 (全距離平均・妥当)
```

### trackcd → surface 派生（既存 builder.py 踏襲・live-DB 実証）
```python
# Source: 既存 builder.py::_construct_derived_columns (L275-311) + live-DB 精査
# trackcd 値分布 (live-DB 2015-2026):
#   10(芝・270件) 11(芝・5499) 12(芝・815) 17(芝・8598) 18(芝・3804)
#   20(芝・4) 21(芝・11)  → 芝計 19001件
#   23(ダ・6773) 24(ダ・12375) → ダート計 19148件
#   52/54/55/56/57(障害・1444件)

tc_num = pd.to_numeric(trackcd.astype(str).str.strip(), errors="coerce")
surface = pd.Series(["unknown"] * len(trackcd))
surface[tc_num.between(10, 22)] = "turf"     # 平地芝
surface[tc_num.between(23, 25)] = "dirt"     # 平地ダート
surface[tc_num.between(51, 59)] = "obstacle"  # 障害
# kyori/trackcd/sibababacd/dirtbabacd は 2015年以降で欠損ゼロ (高品質)
```

### points_per_second 距離別テーブル（Beyer 文献ベース・Claude's Discretion 解決）
```python
# Source: Beyer "Picking Winners" + WebSearch (PaceAdvantage Forum / America's Best Racing)
# [CITED: paceadvantage.com/forum/showthread.php?t=150742]
#   1/5秒 = 3.3 Beyer points (5furlong) vs 1/5秒 = 2 points (8furlong)
#   → 短距離ほど1秒の重みが大きい (D-05 設計通り)
# [CITED: americasbestracing.net] Beyer 94 等価タイム:
#   6f=1:12(72秒) / 7f=1:25(85秒) / 8f=1:38(98秒)
#   → これらは全て Beyer 94 → 距離別 par time の基準値

# JRA 距離（メートル）→ points_per_second 換算テーブル
# Beyer 原典は furlong (1f = 約200m)。JRA 距離を furlong 換算後、補間。
# 実装案 (Claude's Discretion → researcher 提案):
POINTS_PER_SECOND_BY_DISTANCE_M: dict[int, float] = {
    1000: 16.5,   # 5f 相当 (短距離・1秒の重み最大)
    1200: 13.2,   # 6f 相当 (1/5秒=3.3 → 1秒=16.5 → 1200m補間)
    1400: 11.0,   # 7f 相当
    1600: 10.0,   # 8f 相当 (1/5秒=2 → 1秒=10.0)
    1800:  8.8,   # 9f 相当
    2000:  8.0,   # 10f 相当
    2400:  6.6,   # 12f 相当 (長距離・1秒の重み最小)
    3000:  5.3,   # 1.5mile+ 相当
    3200:  5.0,   # 長距離障害含む
}

def get_points_per_second(kyori: int) -> float:
    """距離（メートル）→ points_per_second. 補間で中間距離に対応."""
    distances = sorted(POINTS_PER_SECOND_BY_DISTANCE_M.keys())
    if kyori <= distances[0]:
        return POINTS_PER_SECOND_BY_DISTANCE_M[distances[0]]
    if kyori >= distances[-1]:
        return POINTS_PER_SECOND_BY_DISTANCE_M[distances[-1]]
    # 線形補間 (byte-reproducible・決定論的)
    for i in range(len(distances) - 1):
        if distances[i] <= kyori <= distances[i + 1]:
            d0, d1 = distances[i], distances[i + 1]
            p0 = POINTS_PER_SECOND_BY_DISTANCE_M[d0]
            p1 = POINTS_PER_SECOND_BY_DISTANCE_M[d1]
            return p0 + (p1 - p0) * (kyori - d0) / (d1 - d0)
    return 8.0  # fallback (1mile相当)

# 注意: このテーブルは Beyer 原典の概算値ベース [ASSUMED].
#   厳密な Beyer テーブルは『Picking Winners』掲載の公式表.
#   JRA 距離体系への適合は planner が SC#5 ドメイン整合性で検証後に微調整可.
#   canonical feature は float (D-05) → 絶対スケールより相対的順序が重要.
```

### speed_figure 算出（Beyer 本式 + PIT 制約）
```python
# Source: Beyer "Picking Winners" + CONTEXT.md D-01/D-02/D-05
# speed_figure = (par_sec - actual_time_sec) × points_per_second(kyori) + base_offset
#   par_sec > actual (速い) → 正の値 (速いほど大きい・D-05)
#   variant 補正: source race の same-day variant を適用

def compute_speed_figure(
    time_sec: float,
    par_sec: float,
    variant_sec: float,  # same-day variant (leave-one-race-out)
    kyori: int,
    base_offset: float = 0.0,  # Beyer 互換スケール調整 (Claude's Discretion)
) -> float:
    """Beyer 型スピード指数 (float・丸めない・D-05).

    par は PIT expanding (available_at < cutoff の過去走のみ).
    variant は source_race_date×jyocd×surface の leave-one-race-out.
    """
    if pd.isna(time_sec) or pd.isna(par_sec):
        return float("nan")  # 完走でない・par 算出不可
    pps = get_points_per_second(kyori)
    time_diff = par_sec - time_sec  # 正 = par より速い
    # variant は「その日の馬場が標準より何秒速い/遅い」→ actual から引く
    adjusted_diff = time_diff + variant_sec  # variant_sec 正=速い馬場 → 指数UP補正
    return adjusted_diff * pps + base_offset
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 着順中心能力特徴量（kakuteijyuni rolling） | スピード指数中心（Beyer 型 par/variant 補正） | Phase 9 (v1.1) | `[CITED: domain-analysis §3]` 着順は相手構成に依存・能力そのものを測らない。スピード指数は馬場/距離/クラス補正後の絶対能力値。 |
| full-period 固定 par time | PIT expanding/as-of robust par | Phase 9 (v1.1) | `[CITED: SC#2]` full-period 固定は未来情報リーク。expanding は再現性 + PIT-correctness 両立。 |
| 生タイム特徴量 | par/variant 補正スピード指数 | Phase 9 (v1.1) | `[CITED: domain-analysis §4]` 生タイムは馬場/距離の交絡を含む。補正後指数が「能力そのもの」。 |
| 独立二値分類（v1.0） | （Phase 11 以降）レース内相対確率モデル | Phase 11 | 本 Phase 9 は特徴量層のみ・モデル層は v1.0 踏襲。 |

**Deprecated/outdated:**
- `feature_availability.yaml::course_kubun`（line 129）: `[VERIFIED: live-DB]` normalized 層にカラム不存在・silent parity bug。Phase 9 で削除または `trackcd` 統合。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `time` は 0.1秒単位（decisecond）。`time=1108.0`=110.8秒。 | Code Examples / Pitfall 1 | LOW — live-DB で 1200mダート1着の典型タイム（1分50秒）と整合で確定的。 |
| A2 | `points_per_second` 距離別テーブルの具体値（16.5〜5.0）。 | Code Examples | MEDIUM — Beyer 原典の概算値ベース。厳密な公式表は書籍参照必要。ただし canonical feature は float（D-05）で絶対スケールより相対的順序が重要なため、スケール調整で吸収可能。SC#5 でドメイン整合性検証後に微調整可。 |
| A3 | leave-one-race-out variant の vectorized 近似（group_median - 自レース寄与）は十分精度。 | Pattern 2 | LOW — avg 215完走馬/開催日×surface で自レースの寄与は < 1%。厳密ループは極小 group のみ。 |
| A4 | `course_kubun` は trackcd で完全代替可能。 | Standard Stack / Anti-Patterns | LOW — live-DB で trackcd が競馬場×コース形態を包含確認。par 粒度 `jyocd×trackcd×kyori` は141 group（130 group ≥100件）で十分。 |

## Open Questions (RESOLVED)

> 全3問とも Phase 9 plan（P01/P02/P05）で採用済み。以下に RESOLVED 文として最終解決方針を明記する（PLAN.md 変更不要・形式整合のみ）。

1. **RESOLVED: par/variant の永続化先（中間成果物のみ・normalized 層には入れない）**
   - 決定: **中間成果物（`snapshots/speed_figure_<snapshot_id>.parquet` および `reports/09-speed-figure-domain.{html,json}`）のみ**で永続化する。normalized 層（PostgreSQL system of record）には par/variant を書込まない。
   - 根拠: §12.1「DuckDB/derived を永続化層にしない」と整合。再現性は feature snapshot（byte-reproducible Parquet・§12.4 metadata + SHA256 metadata 除外）で保証済み・監査性も同一手順で再生成可能。ETL 拡張は不要。
   - 採用先: P01 は中間成果物（Parquet/JSON）のみを出力、P03 builder 統合で feature snapshot に取り込み、normalized 層への書込みは行わない。

2. **RESOLVED: stop gate「許容幅（非劣化マージン）」の具体値**
   - 決定: **Brier +0.005 以内・LogLoss +0.02 以内・AUC -0.005 以内**を「非劣化」とする。
   - 根拠: v1.0 LightGBM Brier=0.15222 を基準に、特徴量6個追加で起きうる微小な性能変動（過学習リスク由来）を許容する現実的なマージン。Phase 11 SC#2 で事前登録する非劣化マージンと**同一スケール**で設定（事前登録の聖域§15.2 を事後的に緩めない）。
   - 採用先: P05 stop gate（Task 1 指標3・`_compute_global_metric_delta`）でこの値を適用。**Phase 11 plan 作成時に SC#2 事前登録マージンと本 P05 許容幅が矛盾しないか再確認が必要**（整合確認事項: Phase 11 が P05 より厳しい値を事前登録した場合、P05 SUMMARY の判定は再解釈が必要になる可能性あり）。

3. **RESOLVED: 軽量 residual proxy の分位 bucket 数**
   - 決定: **10 分位**（market_implied 10分位 × model_p 10分位の 2 軸グリッド）。
   - 根拠: `src/model/evaluator.py` の `CALIBRATION_CURVE_BINS=10` と整合・`MIN_BIN_COUNT=30` で極小 bucket を skip（binning 契約固定・§15.2 事前登録指標不変・bit-identical）。
   - 採用先: P05 stop gate Task 1 (o) でこの bucket 数を採用。

## Environment Availability

> Phase 9 は live-DB 必須（feature snapshot 生成・SC#3 registry↔Parquet parity・SC#5 ドメイン整合性可視化）。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (everydb2) | normalized 層素材 SELECT・snapshot 生成 | ✓ | 15.18 (Homebrew) | — |
| Python 3.12 | runtime | ✓ | 3.12.13 | 3.11 fallback (§17.1) |
| uv | dependency + venv | ✓ | 0.11.21 | — |
| pandas / NumPy / PyArrow | feature 構築・snapshot | ✓ | 3.0.3 / ≥2.0 / 24.0.0 | — |
| psycopg3 (psycopg[binary]) | DB 接続 | ✓ | 3.3.4 | — |
| scipy | robust 統計量 (trim_mean) | ✓ | ≥1.17.1 | — |
| plotly | SC#5 可視化 | ✓ | ≥6.8.0 | — |
| LightGBM / CatBoost | stop gate 単体モデル学習 | ✓ | 4.6.0 / 1.2.10 | — |

**Missing dependencies with no fallback:** なし（全て v1.0 稼働実績あり）。

**Missing dependencies with fallback:** なし。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（v1.0 踏襲）+ tests/audit/ adversarial パッケージ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/features/test_speed_figure.py tests/features/test_speed_figure_pit.py -x` |
| Full suite command | `uv run pytest`（KEIBA_SKIP_DB_TESTS unset で live-DB テスト含む） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC#1 | byte-reproducible 再生成（同一 metadata で bit-identical） | unit + integration | `uv run pytest tests/features/test_speed_figure.py::test_byte_reproducible_regeneration -x` | ❌ Wave 0 |
| SC#2 | PIT-correct（`available_at < feature_cutoff_datetime`・strict `<`・adversarial lookahead） | adversarial | `uv run pytest tests/features/test_speed_figure_pit.py -x` | ❌ Wave 0 |
| SC#3 | §12.4 metadata + registry↔Parquet parity（live-DB） | integration | `uv run pytest tests/features/test_speed_figure.py::test_registry_parquet_parity -x`（KEIBA_SKIP_DB_TESTS unset） | ❌ Wave 0 |
| SC#4 | SAFE-01 proxy 排除（AST read-only + allowlist grep） | adversarial | `uv run pytest tests/audit/test_audit_speed_figure.py -x` | ❌ Wave 0 |
| SC#5 | ドメイン整合性（同一馬連続走安定・クラス昇降変動・外れ値なし） | integration（live-DB 可視化） | `uv run python scripts/verify_speed_figure_domain.py`（手動確認・Plotly HTML） | ❌ Wave 0 |
| SC#6 | stop gate 4 指標 + residual proxy（v1.0 baseline 比較） | integration（live-DB） | `uv run python scripts/run_speed_figure_stopgate.py`（evaluator/segment_eval 踏襲） | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/features/ -x`（speed_figure 単体・PIT・parity）
- **Per wave merge:** `uv run pytest`（KEIBA_SKIP_DB_TESTS unset・フル suite）
- **Phase gate:** フル suite GREEN + live-DB snapshot 再生成（SC#3）+ adversarial audit GREEN（SC#4）+ ドメイン整合性可視化確認（SC#5）+ stop gate 評価（SC#6）

### Wave 0 Gaps
- [ ] `tests/features/test_speed_figure.py` — covers SC#1/SC#3（par/variant/speed_figure 算出・byte-reproducible・registry parity）
- [ ] `tests/features/test_speed_figure_pit.py` — covers SC#2（adversarial lookahead・5段階鋳型・target/same_day_prior/same_day_later/previous_day/future 全除外）
- [ ] `tests/audit/test_audit_speed_figure.py` — covers SC#4（AST read-only・allowlist grep・odds/ninki/過去オッズ proxy 排除証明）
- [ ] `scripts/verify_speed_figure_domain.py` — covers SC#5（Plotly HTML・同一馬連続走・クラス昴降・外れ値）
- [ ] `scripts/run_speed_figure_stopgate.py` — covers SC#6（v1.0 baseline 比較・4 指標・residual proxy）
- [ ] Framework install: 不要（pytest 9.1.0 / plotly / scipy は v1.0 既存）

*(Framework は検出済み・新規インストール不要。テストファイル・スクリプトが Wave 0 gap)*

## Security Domain

> security_enforcement: true（config.json）・security_asvs_level: 1・security_block_on: high

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 該当なし（local single-user・Streamlit UI は Phase 7 実装済み・Phase 9 は特徴量層） |
| V3 Session Management | no | 該当なし（同上） |
| V4 Access Control | yes | readonly DB ロールのみ（`make_pool(role='readonly')`・D-06 不変）・raw read-only（REVOKE+fingerprint）・builder.py 既存パターン踏襲 |
| V5 Input Validation | yes | `time > 0`（完走馬フィルタ）・`kyori > 0`・`trackcd` 値域検証（10-25/51-59）・par/variant の NaN/sentinel 処理（silent fill 禁止・D-13 踏襲） |
| V6 Cryptography | no | 該当なし（SHA256 は snapshot.py 既存・新規暗号なし） |
| V7 Errors/Logging | yes | `ValueError`/`RuntimeError` fail-loud（空入力拒否・WR-01/WR-02 踏襲）・silent fallback 禁止（D-13） |
| V8 Data Protection | yes | DSN ログ出力厳禁（settings.py dsn_masked のみログ出力・anti-pattern #20）・.env gitignore（既存） |
| V9 Communications | no | 該当なし（local DB・外部APIなし） |
| V14 Configuration | yes | `feature_availability.yaml` の silent parity 違反（course_kubun）修正・registry↔実体一致（HIGH #3 踏襲） |

### Known Threat Patterns for Feature Engineering (Python/PostgreSQL)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PIT lookahead leak（未来情報の特徴量混入） | Tampering/Elevation | `available_at < feature_cutoff_datetime`（strict `<`）・adversarial lookahead テスト（SC#2・5段階鋳型）・merge_asof(direction='backward') 相当 |
| オッズ/人気 proxy 混入（市場回帰・core value 毀損） | Tampering | AST read-only audit + allowlist grep（SC#4・SAFE-01）・FEATURE_COLUMNS registry derived（make_X_y 完全一致 assert） |
| target race 当日結果の par/variant 混入 | Tampering | expanding/as-of robust（過去走のみ集計）・leave-one-race-out variant（自レース除外） |
| SQL injection（素材 SELECT） | Tampering | psycopg3 parameterized query（builder.py 既存・ワイルドカード SELECT 禁止・Pitfall 1） |
| byte-reproducibility 破壊（再現性聖域違反） | Repudiation | PyArrow 決定論的書込（use_dictionary=False・compression=zstd）+ SHA256（metadata除外）+ FIXED_REPRODUCE_TS |
| silent data loss（空結果・欠損の黙握り） | Denial | fail-loud（RuntimeError on empty・D-13 sentinel・WR-01/WR-02 踏襲） |

## Project Constraints (from CLAUDE.md)

> CLAUDE.md の指示は CONTEXT.md の locked decisions と同等の権威。Phase 9 は以下を遵守する。

| Constraint | Source | Phase 9 適用 |
|------------|--------|-------------|
| **odds-free 原則** | CLAUDE.md Core Value / §9.3 / §13.4 | スピード指数にはオッズ/人気/過去人気/過去オッズ proxy を一切入れない（SAFE-01）。素材は `time`/`kyori`/`trackcd`/`babacd`/`class_code_normalized` のみ。 |
| **リーク防止（PIT correct）** | CLAUDE.md §13 / SC#2 | `available_at < feature_cutoff_datetime`（strict `<`・JST midnight）・`merge_asof(direction='backward')` 相当・adversarial lookahead テスト GREEN。 |
| **byte-reproducible snapshot** | CLAUDE.md §19.1 / SC#1/SC#3 | snapshot.py 踏襲（PyArrow 決定論的書込・SHA256 metadata除外・§12.4 metadata 9 keys）。同一 metadata で再生成すると bit-identical。 |
| **categorical leak-safe** | CLAUDE.md §14.3/§14.4 | speed_figure 自身は float（categorical 処理不要）。素材 categorical（jyocd/trackcd）は LightGBM native + CatBoost has_time=True 踏襲。target/mean encoding 構造的禁止。 |
| **事前登録指標不変** | CLAUDE.md §15.2 / D-14 | stop gate で `evaluator.py`/`segment_eval.py` の binning 契約（CALIBRATION_CURVE_BINS=10 等）を固定再利用。§15.2 事前登録指標（calibration_max_dev/Brier/LogLoss）は一切変更しない。 |
| **再現性聖域 §19.1** | CLAUDE.md §19.1 | model_version・feature_snapshot_id・label_version・odds_snapshot_policy・backtest_strategy_version を保存。同じ条件で再学習・再現可能。 |
| **応答は全て日本語** | CLAUDE.md 最優先指示 | 本 RESEARCH.md 含む全ドキュメント・コメント・コミットメッセージは日本語。 |
| **live-DB クエリ時 statement_timeout 必須** | MEMORY.md subagent-db-query-statement-timeout | `SET statement_timeout = '30s'` を同一セッションで先行発行（本 RESEARCH で実証済み）。 |

## Sources

### Primary (HIGH confidence)
- **live-DB 精査 (2026-06-25・everydb2 PostgreSQL 15.18)** — `time`/`kyori`/`trackcd`/`sibababacd`/`dirtbabacd`/`class_code_normalized` の正式カラム名・data_type・nullable・値分布・欠損パターン・サンプル数。`time` 単位（0.1秒）の確定。`course_kubun` 不存在の確定。
- **既存コード実読** — `src/features/rolling.py`（per-observation latest-K algorithm・obs_id group・strict `<cutoff`・_ROLLING_SYSTEMS）・`src/features/builder.py`（_construct_derived_columns・trackcd→surface/babacd 派生・COPY-NOT-RENAME・HIGH #3 assert）・`src/features/snapshot.py`（byte-reproducible Parquet・SHA256 metadata除外・§12.4 metadata 9 keys）・`src/features/availability.py`（CUTOFF_SEMANTICS・TARGET_OBS_BANNED・_ROLLING_SYSTEMS_FOR_RESERVED・assert_matrix_columns_registered）・`src/model/data.py`（_derive_feature_columns・make_X_y 完全一致 assert）・`src/model/segment_eval.py`（_odds_band/_ninki_band・np.digitize・binning 契約一元化）・`src/model/evaluator.py`（CALIBRATION_CURVE_* 定数・METRIC_COLUMNS）・`src/etl/normalize.py`（_RACE_COLUMNS/_UMA_RACE_COLUMNS DDL・staging-swap・_TABLE_DDL_COLUMNS）
- **`.planning/research/v1.1-domain-analysis.md`** — 外部2AI リサーチ統合（スピード指数 P0 §4・層分離 §5・falsification §6・シナリオ §7・文献 §8）

### Secondary (MEDIUM confidence)
- **Beyer Speed Figure methodology** — [paceadvantage.com/forum/showthread.php?t=150742](http://paceadvantage.com/forum/showthread.php?t=150742)（1/5秒=3.3 points@5f / 2 points@8f）・[americasbestracing.net](https://americasbestracing.net/gambling/2020-horse-racing-speed-figures-explained)（Beyer 94 等価タイム 6f=1:12/7f=1:25/8f=1:38）・[en.wikipedia.org/wiki/Beyer_Speed_Figure](https://en.wikipedia.org/wiki/Beyer_Speed_Figure)（par time・track variant・points_per_second の方法論）・[grokipedia.com/page/Beyer_Speed_Figure](https://grokipedia.com/page/Beyer_Speed_Figure)（par times との比較・adjustments）
- **Beyer "Picking Winners"** — par time / variant / points_per_second の原典（外部書籍・本 RESEARCH では WebSearch 経由の二次情報）

### Tertiary (LOW confidence)
- **`points_per_second` 距離別テーブル具体値** — Beyer 原典の概算値ベース [ASSUMED]・厳密な公式表は書籍参照必要。canonical feature は float（D-05）でスケール調整で吸収可能。

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 全て v1.0 既存依存・新規インストールなし
- Architecture: HIGH — 既存コード実読で pipeline 構造完全把握・live-DB で素材実態確定
- Pitfalls: HIGH — live-DB 実証（time 単位・course_kubun 不存在・欠損パターン）+ 既存 adversarial テストパターン踏襲
- points_per_second テーブル: MEDIUM — Beyer 文献ベースの概算値 [ASSUMED]・SC#5 で検証後に微調整可

**Research date:** 2026-06-25
**Valid until:** 2026-07-25（30日・stable domain・v1.0 pipeline 踏襅で変動リスク低）
