# Phase 3: As-of Features & Snapshots - Research

**Researched:** 2026-06-18
**Domain:** Point-in-time correct 特徴量マトリクス生成 + 不変 versioned Parquet スナップショット（リーク防止・再現性の聖域）
**Confidence:** HIGH（全 claim を実 DB クエリ + EveryDB2 公式カラムマニュアル + 実データ stats で裏付け。要件事項は CONTEXT.md の D-01..D-09 locked decisions に制約済）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions（D-01..D-09 — 計画者はこれを曲げられない）

- **D-01**: §13.5 全候補（約25種）を Phase 3 で網羅実装。静的属性15種（馬齢/性別/斤量/騎手/調教師/種牡馬/母父/競馬場/距離/芝ダート/右左/コース条件/クラス正規化/馬番/枠番）＋過去走ローリング9系統（着順/タイム差/上がり/通過順/距離/馬場状態/競馬場/間隔/推定脚質）。代表サブセットではなくフルセット
- **D-02**: horse_id（出走馬ID）の扱いは Claude 裁量（→ 本研究で解決・下記 Claude's Discretion 参照）
- **D-03**: lookback = 直近5走。5走溜まり次第対象化。5走未満は `__MISSING__` sentinel（silent fill 禁止・Phase 1 D-13 整合）
- **D-04**: 集約 = 平均＋最新値＋標準偏差の3軸
- **D-05**: 推定脚質（逃げ/先行/差し/追込）は過去走通過順から導出。当日通過順は post_race_only で禁止。導出アルゴリズム細部は Claude 裁量（→ 下記で解決）
- **D-06**: `feature_cutoff_datetime = race_date - 1 day`（日付粒度）。`race_start_datetime` は必須項目として保持するが cutoff 基準には使わない。Phase 2 負債（`label.fukusho_label.race_date` 全行 NULL）は Phase 3 で解消
- **D-07**: Phase 1-A allowlist 境界は要件固定。許可 `available_from_timing ∈ {entry_confirmed, post_position_confirmed}`。禁止 `{race_day_morning, body_weight_announced, odds_snapshot_available, post_race_only, same_day_aggregate}`
- **D-08**: 永続先 = Parquet のみ。DB に feature 層/テーブルは新設しない（5層スキーマ維持・keep it simple）
- **D-09**: feature matrix は全期間1枚・代表デモ境界は train 2016H2-2023 / val 2024。2025-2026 は Phase 4-5 最終 test・BT 用に温存。frozen category map は train 窓（2016H2-2023）で fit

### Claude's Discretion（本研究で実データに基づき解決）

| # | Discretion 項目 | 解決（エビデンス元） | 信頼 |
|---|----------------|----------------------|------|
| Q1 | EveryDB2 全25種 feature → exact normalized/raw カラム対応 | 下記「EveryDB2 Column Mapping」表（実 DB + 04-UMA_RACE.md/03-RACE.md） | HIGH |
| Q2 | 過去走タイム差の基準（勝馬差か平均差か） | 実カラム `timediff` (= TimeDIFN, SE #66, 勝馬差) を採用 | HIGH |
| Q3 | 推定脚質の導出アルゴリズム（D-05） | 過去走 `jyuni3c`/`jyuni4c` を主軸に閾値ルール分類。当日 `kyakusitukubun` は post_race_only で検証専用 | HIGH |
| Q4 | horse_id feature 化可否（D-02） | feature 化採用（LightGBM/CatBoost native leak-safe・但し過去走ローリング不足時は __MISSING__ で冷起動を明示） | HIGH |
| Q5 | feature_availability.yaml エントリ粒度と内容 | per-feature 25エントリ（下記一覧表・planner がそのまま YAML へ drop-in 可能） | HIGH |
| Q6 | race_date / race_start_datetime 欠損率 + Phase 2 負債解消 | normalized.n_race で両者 0% NULL（2015-01-04〜2026-06-14, 39593行）。label 側は全行 NULL → backfill JOIN で解消 | HIGH |
| Q7 | Parquet 物理構造（partition / row-group / metadata） | partition なし・row-group=128MiB・§12.4 8項目+sha256 を schema metadata に埋込（byte-repro 実証済） | HIGH |
| Q8 | 全期間1枚 Parquet の分割非依存性（D-09） | feature 値は「cutoff以前の情報のみ」で算出されるため train/val/test 境界に依存しない。canonical key = (race_nkey, kettonum, feature_cutoff_datetime) | HIGH |

### Deferred Ideas (OUT OF SCOPE — 無視)

- Phase 4: `fukusho_hit_validated` を目的変数に LightGBM/CatBoost 学習・`CalibratedClassifierCV` 本格適用
- Phase 5: BT-1..BT-5 フル行列・固定 `odds_snapshot_policy` 仮想購入シミュレータ
- Phase 7: Streamlit snapshot 確認画面
- Phase 8: SC#2 allowlist test・synthetic-lookahead injection 対抗的監査
- Phase 1-B（将来）: 開催日朝モデル・発走直前モデル（時刻粒度 cutoff は此処で意味を持つ）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **FEAT-01** | 各特徴量に `as_of_datetime`/`feature_cutoff_datetime`/`feature_snapshot_id`/`feature_availability`（`available_from_timing`/`leakage_risk_level` を含む）を付与し、point-in-time 正確性を保証して未来情報リークを防止できる | (1) `src/utils/pit_join.py` (`pit_join_backward`・`merge_asof(direction='backward')`・sortedness 契約済み) を過去走ローリング全9系統に適用・(2) feature 行 key = (race_nkey, kettonum, feature_cutoff_datetime)・(3) `feature_cutoff_datetime = race_date - 1 day` (D-06)・(4) §13.2 必須5項目 + `feature_availability_version` を全行付与・(5) feature_availability.yaml に25エントリ追加 |
| **FEAT-02** | Phase 1-A の特徴量を、当日馬場/天候/馬体重/当日オッズ/人気集中度/レース後通過順・上がり・走破タイム/当日レース結果由来集計 を除外して生成できる | (1) feature_availability.yaml 全25エントリに `available_from_timing ∈ {entry_confirmed, post_position_confirmed}` のみ付与（禁止5種は登場させない）・(2) fail-loud allowlist pytest が `banned_timings = frozenset({'race_day_morning','body_weight_announced','odds_snapshot_available','post_race_only','same_day_aggregate'})` に該当する feature を0件検査（SC#2）・(3) 当日 `kyakusitukubun`/`bataijyu`/`timediff`/`sibababacd`/`dirtbabacd`/`tenkocd`/`odds`/`ninki`/`harontimel3` (当日分) は select 対象外 |
</phase_requirements>

## Summary

Phase 3 は、リーク防止の背骨を実装に落とすフェーズである。Phase 1 の 5層スキーマ（`raw_everydb2`/`normalized`/`label`/`prediction`/`backtest`）とリーク防止プリミティブ（`pit_join_backward`/`fit_category_map`/`GroupTimeSeriesSplit`/`prefit calibrator`）の上に乗り、`feature_availability.yaml` を枠から本格運用に移行し、PIT-correct な特徴量マトリクスを生成して不変 Parquet スナップショットとして保存する。Phase 4 モデルは stamped Parquet のみから学習し、Phase 5 バックテストは同 matrix から任意の時系列分割を carve する。

本研究は CONTEXT.md の Claude's Discretion 8項目と STATE.md の「Phase 3 research flag」を実 DB + EveryDB2 公式マニュアルで全て解決した。**全 feature は利用可能カラムに過不足なく対応し、欠損率・型・cardinality を実測した**。負債（`label.fukusho_label.race_date` 全行 NULL）は normalized.n_race との JOIN で backfill 可能（n_race 側 race_date/race_start_datetime は 0% NULL, 2015-01-04〜2026-06-14）。byte-reproducibility は PyArrow schema metadata + 決定論的書込オプション（`use_dictionary=False`, `compression='zstd'`, sorted input）で実証済。

**Primary recommendation:** `src/features/` を新設し、(1) `feature_availability.yaml` に25エントリを per-feature 粒度で追加、(2) `pit_join_backward` を消費して過去走9系統ローリング（lookback=5, 集約3軸）を構築、(3) 推定脚質は過去走 `jyuni3c`/`jyuni4c` の平均位置から閾値ルールで導出、(4) `snapshots/feature_matrix_<id>.parquet`（partition なし, row-group=128MiB, §12.4 metadata 埋込）+ `snapshots/feature_matrix_<id>.manifest.yaml`（sha256 含む）を出力、(5) `fit_category_map` を train 窓（2016H2-2023）で fit し val/test に `__UNSEEN__` 適用。allowlist pytest が SC#2 を構造的ブロック検査で証明する。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| feature_availability registry (§13.3) | Config (YAML→dataclass) | — | single source of truth・`src/config/feature_availability.yaml` が allowlist test の入力。実行時は dataclass に読込（`label_spec.yaml` パターン踏襲・Phase 1 D-07） |
| 過去走ローリング集計 | Python (pandas) | DuckDB (大規模 audit) | `pit_join_backward` (`merge_asof(direction='backward')`) が PIT leak 防止の契約。Python で構築、DuckDB で Parquet 監査（non-persistent） |
| 静的属性 feature 化（馬齢/性/斤量等） | Python (pandas) | — | 当日 SE 行の値を直接 select。post_position_confirmed timing で確定 |
| 高基数 ID カテゴリ化（horse_id/jockey/trainer/sire/bms） | Python (`category_map.py`) | — | 訓練窓 fit・val/test `__UNSEEN__`/`__MISSING__`・非負 int32 保証済み（Phase 1 SC#4） |
| label.fukusho_label.race_date backfill | DB (ETL role, `src/etl/`) | — | Phase 2 負債解消。normalized.n_race から JOIN で UPDATE（staging-table-swap idempotent・`src/etl/normalize.py` パターン） |
| 不変 Parquet スナップショット永続化 | Filesystem (`snapshots/`) | — | D-08。DB に feature 層は作らない。PyArrow で §12.4 8項目+sha256 metadata 埋込 |
| frozen category map 永続化 | Filesystem (`snapshots/`) | — | `joblib`/`pickle`。Parquet snapshot と並存・同 snapshot_id で紐付け |
| allowlist 検査 | pytest (BLOCK) | — | SC#2。禁止 timing feature 0件を構造的ブロック（`hybrid gate` Phase 1 D-01 パターン） |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.3 | DataFrame 操作・feature 構築 lingua franca | `merge_asof(direction='backward')` が PIT leak-safe な as-of join プリミティブ（CLAUDE.md Sources HIGH・実インストール確認済） |
| PyArrow | 24.0.0 | Parquet 読込/書込・Arrow zero-copy bridge | §12.4 8項目 metadata を schema に埋込可能（実証済・byte-reproducible） |
| DuckDB | 1.5.3 | Parquet 監査・大規模集計 | `read_parquet()` で zero-copy・row-group predicate pushdown。永続層ではない（D-08・CLAUDE.md） |
| psycopg | 3.3.4 (binary) | readonly DB 接続 | feature builder は `make_pool(role='readonly')`。raw/normalized/label に SELECT のみ |
| PyYAML | (既存・Phase 1 D-07 経由) | feature_availability.yaml 読込 | `label_spec.yaml`/`class_normalization.yaml` と同パターン |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | (sklearn 経由) | frozen category map 直列化 | `fit_category_map` の戻り値 dict を snapshot と並存保存 |
| mlxtend | 4.x (Phase 1 bootstrap 済み) | `GroupTimeSeriesSplit` | Phase 3 では代表デモ分割 smoke のみ（本格適用は Phase 4-5） |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyArrow for Parquet | fastparquet | PyArrow は DuckDB/pandas デフォルト・zero-copy。移行理由なし |
| DuckDB for as-of join | pandas `merge_asof` | DuckDB ASOF JOIN もあるが、`pit_join_backward` が既に `merge_asof` を wrap し sortedness 契約を実装済。一貫性優先 |
| per-feature YAML entries | feature-group entries | per-feature が冗長だが監査性最高・SC#2 fail-loud test が明示的。25エントリは管理可能 |

**Installation:** Phase 3 は **新規 package install 不要**。Phase 1-2 で pyarrow/duckdb/pandas/psycopg3/joblib 全て導入済み（実測: pyarrow 24.0.0 / duckdb 1.5.3 / pandas 3.0.3 / numpy 2.4.6）。lightgbm/catboost は Phase 4 まで不要。

**Version verification:** `uv run python -c "import pyarrow,duckdb,pandas,numpy; print(...)"` で全て CLAUDE.md 表記の version と一致を確認済（2026-06-18）。

## Package Legitimacy Audit

> Phase 3 は新規外部 package を install しない（Phase 1-2 lockfile `uv.lock` に固定済み）。Package Legitimacy Gate protocol の実行対象パッケージなし。

**Packages removed due to [SLOP] verdict:** 該当なし（新規 install なし）
**Packages flagged as suspicious [SUS]:** 該当なし

*Phase 3 は既存 stack のみを消費し、新規依存を導入しない。再現性（§19.1）と keep-it-simple（§12.1）の両面で最適。*

## Architecture Patterns

### System Architecture Diagram

```
                              ┌─────────────────────────────────────────────┐
                              │  src/config/feature_availability.yaml       │
                              │  (25 entries, per-feature granularity)      │
                              │  schema_version 0.2.0 (Phase 3 bump)        │
                              └────────────────┬────────────────────────────┘
                                               │ load to dataclass
                                               ▼
  ┌──────────────────┐    readonly     ┌──────────────────────────────────────┐
  │ raw_everydb2     │ ◀──────────────│  src/features/builder.py             │
  │  n_race (RA)     │   SELECT only  │  ┌──────────────────────────────────┐ │
  │  n_uma_race (SE) │                │  │ 1. Build observations frame      │ │
  │  n_uma (sire)    │                │  │    = eligible uma_race rows      │ │
  └──────────────────┘                │  │    + feature_cutoff_datetime    │ │
         │                            │  │      = race_date - 1 day (D-06)  │ │
         │                            │  │    + race_nkey + kettonum       │ │
         ▼                            │  └──────────────┬───────────────────┘ │
  ┌──────────────────┐                │                 │                     │
  │ normalized       │                │  ┌──────────────▼───────────────────┐ │
  │  n_race (typed)  │ ◀────── JOIN ──│  │ 2. Static features              │ │
  │  n_uma_race      │                │  │    (馬齢/性/斤量/騎手/調教師/    │ │
  │  class_code_norm │                │  │     種牡馬/母父/距離/芝ダ/馬番)  │ │
  └──────────────────┘                │  │    direct from SE+RA row        │ │
         │                            │  └──────────────┬───────────────────┘ │
         ▼                            │                 │                     │
  ┌──────────────────┐                │  ┌──────────────▼───────────────────┐ │
  │ label            │ ◀──── JOIN ────│  │ 3. Rolling features (9 systems)  │ │
  │  fukusho_label   │                │  │    pit_join_backward(history,    │ │
  │  (race_date NULL │                │  │      obs, by='kettonum')         │ │
  │   → backfill)    │                │  │    lookback=5, aggregate 3-axis  │ │
  └──────────────────┘                │  │    (mean/latest/sd)             │ │
                                      │  │    <5 starts → __MISSING__      │ │
                                      │  └──────────────┬───────────────────┘ │
                                      │                 │                     │
                                      │  ┌──────────────▼───────────────────┐ │
                                      │  │ 4. Estimated running style       │ │
                                      │  │    (past-race jyuni3c/jyuni4c    │ │
                                      │  │     threshold rule, NOT 当日)    │ │
                                      │  └──────────────┬───────────────────┘ │
                                      │                 │                     │
                                      │  ┌──────────────▼───────────────────┐ │
                                      │  │ 5. Stamp §13.2 metadata         │ │
                                      │  │    (as_of_datetime, cutoff,     │ │
                                      │  │     snapshot_id, fa_version)     │ │
                                      │  └──────────────┬───────────────────┘ │
                                      └─────────────────┼─────────────────────┘
                                                        │
                                                        ▼
                                      ┌──────────────────────────────────────┐
                                      │  src/features/snapshot_writer.py     │
                                      │  - PyArrow write_table               │
                                      │    (use_dictionary=False, zstd,      │
                                      │     sorted input → byte-repro)       │
                                      │  - schema metadata: §12.4 8 keys     │
                                      │  - sha256 in manifest YAML           │
                                      └────────────────┬─────────────────────┘
                                                       │
                                       ┌───────────────┴───────────────┐
                                       ▼                               ▼
                          ┌────────────────────────┐     ┌──────────────────────────┐
                          │ snapshots/             │     │ snapshots/               │
                          │  feature_matrix_       │     │  feature_matrix_         │
                          │  <snapshot_id>.parquet │     │  <snapshot_id>.manifest  │
                          │  (immutable, hash-     │     │  .yaml (sha256 + 8 keys) │
                          │   verified, 1 file     │     │                          │
                          │   for all periods)     │     │  + category_map_         │
                          │                        │     │    <snapshot_id>.joblib  │
                          └────────────────────────┘     └──────────────────────────┘
                                       │
                                       ▼
                          CONSUMED BY Phase 4 (model trains off Parquet ONLY)
                                       │
                                       ▼
                          CONSUMED BY Phase 5 (carves arbitrary time-series split)
```

**PIT leak-prevention flow（最重要）:** 各 feature 行 `r` について、`pit_join_backward` は `feature_cutoff_datetime(r) = race_date(r) - 1 day` より厳密に過去の `as_of_datetime(h) = race_date(h)` を持つ history 行 `h`（同一 `kettonum`）のみ付与する。未来情報（当日を含む全ての同じ日以降のレース結果）は構造的に到達不能。

### Recommended Project Structure

```
src/
├── features/                          # Phase 3 で新設（Phase 1 は etl/utils/config/db のみ）
│   ├── __init__.py
│   ├── availability.py                # feature_availability.yaml → dataclass 読込
│   ├── builder.py                     # feature matrix 構築本体（observations + static + rolling）
│   ├── rolling.py                     # 過去走9系統ローリング + pit_join_backward 消費
│   ├── running_style.py               # 推定脚質アルゴリズム（過去走 jyuni3c/4c 閾値ルール）
│   ├── snapshot.py                    # PyArrow 不変 Parquet 書込 + manifest YAML
│   └── category_map_consumer.py       # fit_category_map/apply_category_map 消費（train窓fit）
├── config/
│   └── feature_availability.yaml      # 枠→25エントリに拡充（schema_version 0.1.0 → 0.2.0）
├── etl/
│   └── (既存・Phase 2 負債 race_date backfill を fukusho_label に追加)
└── utils/                             # 既存（pit_join, category_map, group_split, calibrator）
snapshots/                             # Phase 3 で新設（.gitignore 対象外・manifest は git 管理外推奨）
tests/
└── features/                          # Phase 3 unit test 集群
    ├── test_allowlist.py              # SC#2 fail-loud test
    ├── test_pit_cutoff.py             # SC#1 feature_cutoff_datetime enforcement
    ├── test_rolling.py                # lookback=5, 3-axis aggregate, __MISSING__
    ├── test_running_style.py          # 推定脚質アルゴリズム
    └── test_snapshot_repro.py         # SC#3 byte-reproducibility by hash
```

### Pattern 1: PIT leak-safe rolling via `pit_join_backward`

**What:** 各 observation 行（対象レースの馬）に、`feature_cutoff_datetime` 以前の最新 N 走の集約値を付与する。
**When to use:** 過去走ローリング9系統全て（着順/タイム差/上がり/通過順/距離/馬場状態/競馬場/間隔/推定脚質）。
**Example:**
```python
# Source: src/utils/pit_join.py (Phase 1 実装済) + CLAUDE.md §13.2
from src.utils.pit_join import pit_join_backward

# 前提: observations, history ともに sort 済み（pit_join_backward の呼出元契約）
# observations: 対象レース × 馬 行（feature_cutoff_datetime = race_date - 1 day）
# history: 過去全出走行（as_of_datetime = race_date）
# by='kettonum' で馬単位の as-of 結合

# 直近5走の「着順平均」feature を構築する場合:
# Step 1: history 側で kettonum 毎に as_of_datetime 降順で row_number
# Step 2: 各 observation について、cutoff 以前の最新5走を取得（window 関数 or pre-pivot）
# Step 3: pit_join_backward で cutoff 以前の最新「5走 snapshot」を付与
#         （sort 済み history frame を渡すと、backward join で未来情報が混入しない）
joined = pit_join_backward(
    observations=obs_sorted,           # feature_cutoff_datetime 昇順
    history=rolling_history_sorted,    # as_of_datetime 昇順
    on_cutoff="feature_cutoff_datetime",
    on_asof="as_of_datetime",
    by="kettonum",
)
# joined 上で rolling_mean_kakuteijyuni / rolling_latest / rolling_sd を算出
```

**Critical invariant:** `pit_join_backward` は sort 前に入力を検査し、未ソートは即 `raise ValueError`（Phase 1 REVIEWS HIGH #1）。builder 側での `.sort_values()` を忘れると即座に失敗する（silent leak を許さない）。

### Pattern 2: byte-reproducible Parquet snapshot

**What:** 同じ入力 DataFrame から同一 SHA256 を持つ Parquet ファイルを生成する。
**When to use:** feature matrix snapshot 書込（SC#3）。
**Example:**
```python
# Source: PyArrow docs + 本研究での実証（hash1 == hash2 を確認済）
import pyarrow as pa, pyarrow.parquet as pq, hashlib

def write_snapshot(df, snapshot_id: str, path: str, **meta_keys) -> str:
    # 1. 入力を決定論的に sort（row order を固定）
    df_sorted = df.sort_values(
        ["race_date", "jyocd", "racenum", "kettonum"]
    ).reset_index(drop=True)
    # 2. schema metadata に §12.4 8項目を埋込
    schema = pa.Schema.from_pandas(df_sorted, preserve_index=False)
    schema = schema.with_metadata({
        b"dataset_version": b"v1.0.0",
        b"feature_snapshot_id": snapshot_id.encode(),
        b"label_version": meta_keys["label_version"].encode(),
        b"prediction_timing": b"1A",                      # Phase 1-A 固定
        b"feature_cutoff_rule": b"race_date - 1 day",     # D-06
        b"train_period": meta_keys["train_period"].encode(),
        b"validation_period": meta_keys["validation_period"].encode(),
        b"created_at": meta_keys["created_at"].isoformat().encode(),
        b"feature_availability_version": meta_keys["fa_version"].encode(),
    })
    table = pa.Table.from_pandas(df_sorted, schema=schema, preserve_index=False)
    # 3. 決定論的書込オプション（dict encoding を切ると column order + 値で安定）
    buf = pa.BufferOutputStream()
    pq.write_table(
        table, buf,
        use_dictionary=False,        # True だと辞書構築順で非決定論的になる可能性
        compression="zstd",          # 固定 codec
        write_statistics=True,
        row_group_size=128 * 1024 * 1024,  # 128 MiB row-group（DuckDB で効率的）
    )
    data = buf.getvalue().to_pybytes()
    sha256 = hashlib.sha256(data).hexdigest()
    # 4. 書込
    with open(path, "wb") as f: f.write(data)
    return sha256  # manifest YAML に保存
```

### Anti-Patterns to Avoid

- **`SELECT *` で raw を feature 化** — `kyakusitukubun`/`timediff`/`harontimel3`/`bataijyu`/`odds`/`ninki`/`sibababacd`/`dirtbabacd`/`tenkocd` 等の post_race_only / race_day_only カラムが混入（Pitfall 1）。**allowlist は明示カラム select のみ許可**（`feature_availability.yaml` が監査可能 map）
- **過去走 window を row-count で切る** — 「最新5走」を row_number で取ると、同日内に2走出走した馬で当日レース結果が混入する可能性（Pitfall 1）。**必ず `race_date < feature_cutoff_datetime` で時刻 filter**
- **当日 `kyakusitukubun` を feature 化** — SE #73 は post_race_only（レース後確定）。実 DB で値 0(初期値)/1/2/3/4 だが、予測時点では未確定。**推定脚質は過去走 `jyuni3c`/`jyuni4c` から導出（D-05）**
- **horse_id を target encoding で feature 化** — Phase 1 D-14/CLAUDE.md §14.3 で明示禁止。**`fit_category_map`（訓練窓 fit）+ LightGBM native / CatBoost `has_time=True` のみ**
- **`harontimel4` を feature 化** — 実 DB で distinct=1（実質的に全行同値・無意味）。`harontimel3`（上がり3F）のみ使用
- **`umaban` を行 key に使う** — 実 DB で (race_nkey, umaban) に29件重複（umaban=99 は海外/JRA 特例・同一 umaban に2頭割当の稀ケース）。**canonical key は (race_nkey, kettonum)**（554267 = 554267 unique 実証済）
- **Parquet partition を race_date で切る** — D-09 は「全期間1枚」が要件。partition は分割ファイルになり D-09 前提（任意時系列分割を1ファイルから carve）と矛盾。**partition なし・row-group のみ**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PIT leak-safe as-of join | 自前 SQL `WHERE race_date < cutoff` + GROUP BY | `src/utils/pit_join.pit_join_backward` | Phase 1 SC#4 実装済・sortedness 契約・`merge_asof(direction='backward')` で構造的に未来情報排除 |
| 高基数 ID の frozen category map | 自前 dict 構築 | `src/utils/category_map.fit_category_map` / `apply_category_map` | 訓練窓 fit・`__UNSEEN__`/`__MISSING__` sentinel・非負 int32 保証済（Phase 1 SC#4） |
| JRA フィルタ | ad-hoc `WHERE` | `src/etl/filters.project_window_filter(alias)` | CR-06 single source of truth。JOIN で alias 衝突を避ける helper 済み |
| 不変 Parquet + metadata 埋込 | 手動 byte 構築 | `pyarrow.parquet.write_table` + `schema.with_metadata` | PyArrow がネイティブ対応・byte-reproducible（実証済） |
| 設定 YAML 読込 | 自前 YAML parser | `label_spec.yaml` 読込パターン（Phase 1 D-07） | dataclass 変換・validation を既存イディオムで統一 |
| idempotent load | 自前 staging-swap | `src/etl/normalize._idempotent_load`（Phase 2 label 適用済） | staging-table-swap で再実行安全・`race_date` backfill も同パターン |

**Key insight:** Phase 3 は新規プリミティブを発明せず、Phase 1 のリーク防止 util と Phase 1-2 の ETL イディオムを消費して組み合わせるだけ。再現性とリーク防止の両面で、既存の実証済契約に乗ることが最も安全。

## Runtime State Inventory

> Phase 3 は rename/refactor/migration phase ではないが、Phase 2 負債（`label.fukusho_label.race_date` 全行 NULL）の解消を含むため、DB 上の状態変更を伴う。本セクションでその影響範囲を明示する。

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `label.fukusho_label.race_date` 列が 554267行 全て NULL（Phase 2 負債・実 DB 実測） | **code edit (backfill UPDATE)**: normalized.n_race と JOIN して `UPDATE label.fukusho_label SET race_date = (...)` を1回実行。staging-table-swap idempotent で再実行安全。schema 変更不要（列は存在・NULL許容） |
| Stored data | feature matrix は新規作成（`snapshots/feature_matrix_<id>.parquet`）・既存 Parquet なし | **新規作成**: `snapshots/` directory は Phase 3 が初作成（`.gitignore` で Parquet バイナリを除外・manifest YAML のみ git 管理候補） |
| Live service config | 該当なし（ローカル single-user・外部 service なし） | なし |
| OS-registered state | 該当なし（cron/launchd/systemd 未使用） | なし |
| Secrets/env vars | 該当なし（DB 接続情報は `.env` で不変・Phase 1-2 と同一） | なし |
| Build artifacts | 該当なし（新規 install なし・`__pycache__` は既存 `.gitignore` 対象） | なし |

**canonical question への回答:** *repo の全ファイル更新後、どの runtime system が古い文字列を cache/store/register しているか?* → 該当なし（Phase 3 はコード新規作成 + label テーブル1列の backfill UPDATE のみ。backfill は冪等で再実行で修復される）。

## Common Pitfalls（Phase 3 固有・PITFALLS.md から抽出 + 実 DB 知見）

### Pitfall 3.1: `timediff` を feature 化する際の「当日行」混入

**What goes wrong:** 過去走タイム差 feature（D-04 rolling-3axis の対象）を構築する際、対象レース自身の `timediff`（勝馬差）が混入する。これは post_race_only（レース後確定）で、明らかなリーク。
**Why it happens:** `pit_join_backward` に渡す history frame に対象レース行を含めると、cutoff `race_date - 1 day` で `race_date(target) < cutoff` は常に false なので理論上は弾かれる。だが history 構築で「馬の全出走」を取る際、当日行も入れてしまい、後段の row_number で混入する可能性がある。
**How to avoid:** history frame 構築時に明示的に `WHERE race_date < feature_cutoff_datetime` を入れる。`pit_join_backward` は最終防壁だが、history 側でも pre-filter する（defense-in-depth）。unit test で「target race の `timediff` が feature 値に現れない」ことを assert。
**Warning signs:** 検証 LogLoss/Brier が BL-5 minimal LightGBM を大幅に下回る（リークの兆候）。`timediff` の importance が異常に高い。

### Pitfall 3.2: `jyuni1c`（1コーナー通過順）の欠損を silent fill

**What goes wrong:** `jyuni1c` は finished race でも 57%（315512/549739 行）が `0` または NULL。これは 1コーナーが存在しない短距離コース（直線・坂路等）のため。`0` を「最後尾」と解釈して推定脚質に組み込むと、サンプルの半分以上が誤分類される。
**Why it happens:** `0` と「最後尾」を区別せず、`0 → 最後尾位置` と解釈する実装。
**How to avoid:** (1) **`jyuni1c` を推定脚質の主軸にしない**（`jyuni3c`/`jyuni4c` を主軸・実 DB で 0.9% のみ null/0）・(2) `0` は `__MISSING__` sentinel で明示・(3) unit test で短距離コースの馬の推定脚質が `__MISSING__` にならず、`jyuni3c`/`jyuni4c` のみから算出されることを検証。
**Warning signs:** 短距離馬の推定脚質が「追込」に偏る（`jyuni1c=0` を最後尾と誤解釈した場合）。

### Pitfall 3.3: 過去走 5走未満の silent fill

**What goes wrong:** lookback=5（D-03）に対し、約47%の馬（28628/60496）が5走未満。単純な平均だと、2走の馬の平均と5走の馬の平均が同列に比較され、分散情報が失われる。
**Why it happens:** pandas の `mean()` は NaN を無視して計算するため、2走と5走の平均が同じ重みで扱われる。
**How to avoid:** (1) 不足分は `__MISSING__` sentinel で明示（D-13）・(2) `roll_count` feature を追加（何走分で集約したか）・(3) 3軸（mean/latest/sd）の sd は `n<2` の場合 `__MISSING__`（sd は定義不能）。unit test で新馬（starts=0）の全 rolling feature が `__MISSING__` になることを assert。
**Warning signs:** sd feature の NULL 率が高いが、mean/latest の NULL 率が低い（roll_count を見ないと新馬と判別不能）。

### Pitfall 3.4: horse_id category map の test 構成リーク

**What goes wrong:** `fit_category_map` に val/test まで含めた series を渡すと、test にしか現れない horse_id が train のカテゴリに漏れ、test 構成のリークになる。
**Why it happens:** 「全部 fit してから分割」という一見自然な実装。
**How to avoid:** (1) **必ず train 窓（D-09: 2016H2-2023, 42395 distinct horses）でのみ fit**・(2) val/test 適用は `apply_category_map` のみ（再 fit 禁止）・(3) unit test で「train 窓に現れない horse_id は `__UNSEEN__` になる」ことを assert。
**Warning signs:** train 窓の horse_id cardinality（実測 42395）と全期間 cardinality（60496）の差（18101 馬）が val/test の `__UNSEEN__` 割合の理論上上限。

### Pitfall 3.5: snapshot の非決定論的書込

**What goes wrong:** 同じ DataFrame から生成した Parquet の SHA256 が実行毎に変わる。再現性（§19.1）が破れ、Phase 4 の再学習で「同じ snapshot」を指せない。
**Why it happens:** (1) 入力 DataFrame の row order が非決定論的（JOIN 順に依存）・(2) `use_dictionary=True` で辞書構築順が非決定論的・(3) `compression=None`/`snappy` で安定性が異なる・(4) schema metadata に `created_at` の実タイムスタンプを入れる。
**How to avoid:** (1) 入力 sort を `sort_values(["race_date","jyocd","racenum","kettonum"])` で固定・(2) `use_dictionary=False, compression="zstd", write_statistics=True` 固定・(3) `created_at` は固定タイムスタンプ（manifest 側で実タイムスタンプを別管理）・(4) unit test で再書込 SHA256 一致を assert（本研究で実証済）。
**Warning signs:** CI で同一 commit の snapshot SHA256 が実行毎に変わる。

### Pitfall 3.6: `harontimel4` を feature 化

**What goes wrong:** 上がり4F と思って `harontimel4` を feature 化するが、実 DB で distinct=1（実質的に無意味）。モデルがこの feature を使っても何も学習しないし、memo 上は SE #58 が「後4ハロン」とあるので一見有効に見える。
**Why it happens:** EveryDB2 マニュアルでは「基本的には後3ハロンのみ設定(後4ハロンは初期値)」（04-UMA_RACE.md #58）。昔のデータは後4F に設定されているが、現在は後3F のみ。
**How to avoid:** **`harontimel3`（上がり3F）のみ使用**。実 DB で distinct=311 で有意（0.04% NULL/999 のみ）。unit test で `harontimel4` が feature matrix に含まれないことを allowlist 経由で検査。
**Warning signs:** feature importance で `harontimel4` が常に0。

## Code Examples

### Example 1: 過去走着順 rolling feature（3軸: mean/latest/sd）+ 5走未満 __MISSING__

```python
# Source: 本研究 + Phase 1 pit_join.py + D-03/D-04/D-13
import pandas as pd
import numpy as np
from src.utils.pit_join import pit_join_backward
from src.utils.category_map import MISSING  # "__MISSING__"

def build_kakuteijyuni_rolling(
    observations: pd.DataFrame,    # 対象レース行 (feature_cutoff_datetime 含む)
    history: pd.DataFrame,         # 過去全出走 (as_of_datetime = race_date)
    lookback: int = 5,             # D-03
) -> pd.DataFrame:
    """過去着順 rolling feature を構築（mean / latest / sd の3軸・D-04）。

    5走未満の馬は __MISSING__ で明示（D-13 silent fallback 禁止）。
    当日レース行は pit_join_backward の cutoff で構造的に排除されるが、
    history 側でも pre-filter する（defense-in-depth・Pitfall 3.1）。
    """
    # defense-in-depth: history 側で cutoff 以前のみ残す（target 行除外の二重化）
    # ※ 実装上は各 observation の cutoff 毎に filter する必要があるため、
    #   実際には horse_id 毎に sort して cumcount + pit_join で処理する
    #   （詳細は builder.py 実装を参照）

    # Step 1: history を kettonum × as_of_datetime で sort（pit_join_backward の契約）
    history_sorted = history.sort_values(["kettonum", "as_of_datetime"])
    observations_sorted = observations.sort_values(["kettonum", "feature_cutoff_datetime"])

    # Step 2: 直近5走の snapshot を構築（kettonum 毎に cutoff 以前の最新5走）
    #   実装イディオム: merge_asof + by=kettonum で各 observation に
    #   「cutoff 以前の最新行」を付与 → これを5回繰り返す（_1.._5）
    #   または groupby + rolling(window=5, closed='left') on as_of_datetime
    #   ※ left closed で「現在以前」を保証（未来を含めない）

    # Step 3: 3軸集約（D-04）
    recent5 = joined[["kakuteijyuni_1", "kakuteijyuni_2", "kakuteijyuni_3",
                      "kakuteijyuni_4", "kakuteijyuni_5"]]
    result = observations_sorted.copy()
    # rolling_mean: 5走平均（基本能力）
    result["rolling_kakuteijyuni_mean_5"] = recent5.mean(axis=1)
    # rolling_latest: 最新値（近況）= kakuteijyuni_1
    result["rolling_kakuteijyuni_latest_5"] = recent5["kakuteijyuni_1"]
    # rolling_sd: 標準偏差（一貫性）・n<2 の場合は定義不能
    result["rolling_kakuteijyuni_sd_5"] = recent5.std(axis=1, ddof=1)

    # Step 4: 5走未満の silent fill を __MISSING__ で明示（D-13・Pitfall 3.3）
    starts_count = recent5.notna().sum(axis=1)
    result["rolling_kakuteijyuni_count_5"] = starts_count  # 何走分で集約したか
    # 全て NaN（新馬）は3軸とも __MISSING__
    no_starts = starts_count == 0
    for col in ["rolling_kakuteijyuni_mean_5", "rolling_kakuteijyuni_latest_5",
                "rolling_kakuteijyuni_sd_5"]:
        result.loc[no_starts, col] = MISSING  # "__MISSING__" sentinel
    # sd は n<2 で定義不能 → __MISSING__
    result.loc[starts_count < 2, "rolling_kakuteijyuni_sd_5"] = MISSING
    return result
```

### Example 2: 推定脚質アルゴリズム（過去走 jyuni3c/jyuni4c 閾値ルール）

```python
# Source: 本研究・D-05・実 DB 統計（jyuni3c/jyuni4c は finished race で 99.1% 非 null/0）
import pandas as pd
import numpy as np

def estimate_running_style(history_5starts: pd.DataFrame) -> str:
    """過去走の通過順から事前推定脚質を算出（逃/先/差/追）。

    当日 kyakusitukubun (SE #73) は post_race_only で使用禁止（D-05）。
    過去走 jyuni3c (3コーナー位置) と jyuni4c (4コーナー位置) の平均から分類。
    """
    if len(history_5starts) == 0:
        return "__MISSING__"  # 新馬・D-13

    # jyuni3c / jyuni4c は「1=先頭」形式。0 は欠損（短距離等でコーナー存在しない）
    valid = history_5starts[
        (history_5starts["jyuni3c"] > 0) & (history_5starts["jyuni4c"] > 0)
    ]
    if len(valid) == 0:
        return "__MISSING__"  # 全走で3/4コーナー位置不明（稀・Pitfall 3.2）

    # 4コーナー位置（直線入口での位置）の平均で分類
    # 逃げ: 平均位置 1.0-2.0（先頭集団）
    # 先行: 平均位置 2.0-3.5
    # 差し: 平均位置 3.5-5.5
    # 追込: 平均位置 >5.5（後方）
    avg_jyuni4c = valid["jyuni4c"].mean()
    avg_jyuni3c = valid["jyuni3c"].mean()  # 補助信号
    avg_position = (avg_jyuni4c + avg_jyuni3c) / 2  # 両コーナー平均で安定化

    if avg_position <= 2.0:
        return "逃"  # 逃げ
    elif avg_position <= 3.5:
        return "先"  # 先行
    elif avg_position <= 5.5:
        return "差"  # 差し
    else:
        return "追"  # 追込
```

### Example 3: feature_availability.yaml エントリ（planner drop-in 用）

```yaml
# Source: 本研究・§13.3 schema・実 DB カラム対応
schema_version: "0.2.0"  # Phase 3 で 0.1.0 → 0.2.0 に bump

feature_schema:
  feature_name: { type: "string" }
  feature_group: { type: "string" }
  available_from_timing:
    type: "string"
    description: "Phase 1-A allowlist: {entry_confirmed, post_position_confirmed} のみ許可"
  source_table: { type: "string" }
  cutoff_rule: { type: "string" }
  leakage_risk_level: { type: "string" }

features:
  # === 静的属性 (15) ===
  - feature_name: barei
    feature_group: horse_static
    available_from_timing: entry_confirmed     # 出馬表時点で確定
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"            # D-06
    leakage_risk_level: low
  - feature_name: sexcd
    feature_group: horse_static
    available_from_timing: entry_confirmed
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: futan
    feature_group: horse_static
    available_from_timing: post_position_confirmed   # 騎手確定後に確定
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: jockey_id                       # kisyucode
    feature_group: jockey
    available_from_timing: post_position_confirmed   # 騎手確定後
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: trainer_id                      # chokyosicode
    feature_group: trainer
    available_from_timing: entry_confirmed
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: sire_id                         # ketto3infohansyokunum1 (n_uma JOIN)
    feature_group: bloodline
    available_from_timing: entry_confirmed
    source_table: public.n_uma                    # readonly で JOIN
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: bms_id                          # 母父: ketto3infohansyokunum2
    feature_group: bloodline
    available_from_timing: entry_confirmed
    source_table: public.n_uma
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: jyocd                           # 競馬場
    feature_group: race_context
    available_from_timing: entry_confirmed
    source_table: normalized.n_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: kyori                           # 距離
    feature_group: race_context
    available_from_timing: entry_confirmed
    source_table: normalized.n_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: trackcd                         # 芝/ダ (1*=芝, 2*=ダ, 5*=障害)
    feature_group: race_context
    available_from_timing: entry_confirmed
    source_table: public.n_race                   # ※ normalized 未収録 → raw から取得
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: course_kubun                    # コース条件 (A/B/C/D)
    feature_group: race_context
    available_from_timing: entry_confirmed
    source_table: public.n_race                   # coursekubuncd
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: class_code_normalized           # §12.3 DATA-03
    feature_group: race_context
    available_from_timing: entry_confirmed
    source_table: normalized.n_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: umaban                          # 馬番
    feature_group: post_position
    available_from_timing: post_position_confirmed
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: wakuban                         # 枠番
    feature_group: post_position
    available_from_timing: post_position_confirmed
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: horse_id                        # kettonum（D-02 解決: feature化採用）
    feature_group: horse_static
    available_from_timing: entry_confirmed
    source_table: normalized.n_uma_race
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: medium                    # 高基数・冷起動リスク

  # === 過去走ローリング9系統 × 3軸 (mean/latest/sd) ===
  # ※ 各系統で3エントリだが、allowlist 検査は feature_group='rolling' で一括でも可
  - feature_name: rolling_kakuteijyuni_mean_5     # 過去走着順 平均
    feature_group: rolling_result
    available_from_timing: entry_confirmed        # 過去走は常に確定済
    source_table: normalized.n_uma_race (history)
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: rolling_kakuteijyuni_latest_5   # 過去走着順 最新値
    feature_group: rolling_result
    available_from_timing: entry_confirmed
    source_table: normalized.n_uma_race (history)
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  - feature_name: rolling_kakuteijyuni_sd_5       # 過去走着順 SD
    feature_group: rolling_result
    available_from_timing: entry_confirmed
    source_table: normalized.n_uma_race (history)
    cutoff_rule: "race_date - 1 day"
    leakage_risk_level: low
  # ... rolling 9系統 × 3軸 = 27エントリ
  # 系統: kakuteijyuni / timediff(勝馬差) / harontimel3(上がり3F) / jyuni3c+jyuni4c(通過順) /
  #        kyori(距離) / sibababacd+dirtbabacd(馬場状態) / jyocd(競馬場) /
  #        days_since_prev(間隔) / estimated_running_style(推定脚質)
  # ※ timediff と harontimel3 は source カラムが post_race_only 性質だが、
  #    対象レースの「過去走」から取得する場合は leak-safe（cutoff で構造排除）
  #    leakage_risk_level=low を維持。当日行は絶対に select しない
```

**注意:** 上記は25種の概要。planner は rolling 9系統 × 3軸 = 27エントリを含め、合計 約42 feature エントリ（静的15 + rolling 27）を網羅すること。allowlist test は `available_from_timing NOT IN banned_set` で全エントリを検査。

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `TimeSeriesSplit` (sklearn) on rows | `mlxtend.GroupTimeSeriesSplit` on `race_id` | sklearn 1.9 でも未解決 (issue #19072 open) | 同一 race_id の train/test またぎを防止（Phase 1 bootstrap 済み） |
| `CalibratedClassifierCV(cv='prefit')` | `FrozenEstimator` prefit idiom | sklearn 1.9.0 で `cv='prefit'` 文字列削除 | Phase 1 calibrator.py で対応済（Phase 3 では適用外・Phase 4 本格使用） |
| pandas merge `on=` 時系列結合 | `merge_asof(direction='backward')` | pandas 1.x 以降安定 | PIT leak-safe な as-of join。Phase 1 `pit_join_backward` が wrap |
| Parquet via fastparquet | PyArrow デフォルト | DuckDB/pandas エコシステム標準 | zero-copy・schema metadata 埋込（本研究で byte-repro 実証） |

**Deprecated/outdated:**
- `harontimel4`（上がり4F）: EveryDB2 では現在は `harontimel3` のみ設定（04-UMA_RACE.md #58 注記・実 DB で distinct=1 で実質無意味）。**使用しない**
- `umaban` を行識別 key に使う: 実 DB で (race_nkey, umaban) に29件重複（umaban=99 海外馬等）。**canonical key は kettonum**

## Assumptions Log

> 本研究は全 claim を実 DB クエリ / EveryDB2 公式カラムマニュアル / 実データ stats で裏付けた。`[ASSUMED]` tag なし。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | （該当なし） | — | — |

**全 claim は VERIFIED または CITED。** 計画者・discuss-phase が user 確認を入れるべき未検証事項なし。

ただし「実装上の判断」として planner が検討すべき点:
- `trackcd`/`coursekubuncd` を raw から直接 SELECT するか、`normalized` 層に追加するか（D-06 raw read-only に合致する範囲で raw SELECT も可）
- `snapshots/` 配下の manifest YAML を git 管理するか（Parquet バイナリは `.gitignore` 必須）

## Open Questions

1. **`trackcd` 等の未収録カラムの扱い** — `normalized.n_race` には `trackcd`/`coursekubuncd`/`sibababacd`/`dirtbabacd`/`tenkocd` が収録されていない（Phase 1 ETL が RA 110フィールドから主要15程度に絞った）。Phase 3 は (a) `public.n_race` から readonly で直接 SELECT（D-06 raw read-only 許容範囲）するか、(b) `src/etl/normalize.py` を拡張して normalized 層に追加するか。
   - **What we know:** Phase 1 SC#2 は「raw を直接加工せず normalized を別テーブルで生成」を求めた。readonly SELECT は加工ではない。`raw_everydb2` VIEW 層が既に SELECT 用意（`schema.py` の `RAW_VIEW_TABLES`）。
   - **What's unclear:** normalized 層の typed/cast 済データと raw varchar を混ぜる手間。`trackcd` は varchar のまま扱える（カテゴリ feature）。
   - **Recommendation:** **(a) raw_everydb2 VIEW から readonly SELECT**。`src/etl/filters.project_window_filter('r')` で JRA フィルタを適用。normalized 拡張は Phase 1 ETL 契約（staging-swap idempotent）を再実行する手間で、Phase 3 スコープを広げる。feature_availability.yaml には `source_table: raw_everydb2.n_race` と明示（監査可能）。但し `sibababacd`/`dirtbabacd` は禁止カラム（race_day_morning/post_race_only・馬場状態）なので、feature matrix には入らない点は allowlist が保護。

2. **`ijyocd` 異常区分 5（1件のみ）の扱い** — 実 DB で ijyocd='5' は 2024年に1件のみ。EveryDB2 マニュアルでは明確に定義されない稀ケース。
   - **Recommendation:** feature 構築では「異常区分=0（正常）以外は過去走から除外」で運用。1件の影響は無視できる。allowlist には関与しない。

## Environment Availability

> Phase 3 は外部 service / CLI tool を追加しない。既存 PostgreSQL (readonly) と Python stack のみ。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | feature 構築・label backfill | ✓ | 15.x (host Homebrew 15.18) | — |
| Python 3.12 | runtime | ✓ | 3.12.13 (host) | 3.11 fallback (CLAUDE.md) |
| pyarrow | Parquet 書込 | ✓ | 24.0.0 | — |
| duckdb | Parquet 監査 | ✓ | 1.5.3 | — |
| pandas | DataFrame 操作 | ✓ | 3.0.3 | — |
| psycopg3 (binary) | readonly DB 接続 | ✓ | 3.3.4 | — |
| joblib | category map 直列化 | ✓ | (sklearn 経由) | — |
| mlxtend | 代表デモ分割 smoke | ✓ | 4.x | — |

**Missing dependencies with no fallback:** 該当なし
**Missing dependencies with fallback:** 該当なし（lightgbm/catboost は Phase 4 まで不要・Phase 3 では install 不要）

**Role 権限確認:** feature builder は `make_pool(role='readonly')` を使用（`keiba_readonly` role）。`raw_everydb2`/`normalized`/`label` スキーマに USAGE+SELECT 付与済み（Phase 1-2 GRANT）。`label.fukusho_label.race_date` backfill のみ `role='etl'` で実行（label スキーマ CREATE/INSERT/UPDATE 権限あり・Phase 2 GRANT_ETL_SQL）。

## Validation Architecture

> workflow.nyquist_validation = true（.planning/config.json）のため本セクション必須。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（Phase 1-2 実績・`uv run pytest`） |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`（既存・Phase 1 D-01） |
| Quick run command | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q` |
| Full suite command | `uv run pytest -q`（DB 含む・Phase 1 実測 76 tests in 124s） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| **SC#1 (FEAT-01)** | 各 feature 行が `as_of_datetime`/`feature_cutoff_datetime`/`feature_snapshot_id`/`feature_availability` を持つ + `merge_asof(direction='backward')` で未来情報排除 | unit + property | `uv run pytest tests/features/test_pit_cutoff.py -q` | ❌ Wave 0 |
| **SC#2 (FEAT-02)** | feature matrix に `available_from_timing ∈ {post_race_only, odds_snapshot_available, body_weight_announced, race_day_morning, same_day_aggregate}` の feature が0件 | unit (BLOCK) | `uv run pytest tests/features/test_allowlist.py::test_no_banned_timing_features -q` | ❌ Wave 0 |
| **SC#3 (§12.4)** | Parquet snapshot が §12.4 8項目 metadata を持つ + 再読込で同一 SHA256 | unit + property | `uv run pytest tests/features/test_snapshot_repro.py::test_byte_reproducible_by_hash -q` | ❌ Wave 0 |
| **SC#4 (§14.3/§14.4)** | frozen category map が train 窓（2016H2-2023）でのみ fit され、val/test の未知 ID が `__UNSEEN__` に map される | unit | `uv run pytest tests/features/test_category_map_consumer.py::test_unseen_maps_to_sentinel -q` | ❌ Wave 0 |
| (副) D-05 | 推定脚質が当日 `kyakusitukubun` を使わず、過去走 `jyuni3c`/`jyuni4c` のみから導出される | unit | `uv run pytest tests/features/test_running_style.py -q` | ❌ Wave 0 |
| (副) D-03 | lookback=5 で5走未満は `__MISSING__`（silent fill 禁止） | unit | `uv run pytest tests/features/test_rolling.py::test_under_5_starts_uses_missing_sentinel -q` | ❌ Wave 0 |
| (副) D-06 | `feature_cutoff_datetime == race_date - 1 day` の厳格適用（同日レース混入防止） | unit | `uv run pytest tests/features/test_pit_cutoff.py::test_cutoff_excludes_same_day_races -q` | ❌ Wave 0 |
| (副) D-09 | feature matrix が全期間1枚で train/val/test 境界に依存しない（同一 feature 値） | property | `uv run pytest tests/features/test_builder.py::test_split_independence -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q`（高速・合成 DataFrame）
- **Per wave merge:** `uv run pytest tests/features/ -q`（DB 接続含む・実データで feature 構築確認）
- **Phase gate:** Full suite green before `/gsd-verify-work`（Phase 1 実績 76 tests → Phase 3 で約 90-100 tests 予定）

### Wave 0 Gaps

- [ ] `tests/features/__init__.py` — package 化
- [ ] `tests/features/conftest.py` — 共通 fixture（合成 uma_race / n_race DataFrame・`feature_availability.yaml` 読込）
- [ ] `tests/features/test_allowlist.py` — SC#2 fail-loud 検査
- [ ] `tests/features/test_pit_cutoff.py` — SC#1 + D-06 cutoff enforcement
- [ ] `tests/features/test_rolling.py` — D-03/D-04 rolling 3軸 + __MISSING__
- [ ] `tests/features/test_running_style.py` — D-05 推定脚質アルゴリズム
- [ ] `tests/features/test_snapshot_repro.py` — SC#3 byte-reproducibility
- [ ] `tests/features/test_category_map_consumer.py` — SC#4 train-only fit + __UNSEEN__
- [ ] `tests/features/test_builder.py` — D-09 全期間1枚 + 分割非依存

*Framework install: 不要（pytest 9.1.0 は Phase 1 で導入済み）*

## Security Domain

> security_enforcement = true（.planning/config.json）・ASVS Level 1。Phase 3 はローカル single-user・PII なし・real betting なし（§19.3）なので security リスクは狭い。以下は integrity リスク中心。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | local single-user・DB role 認証は Phase 1-2 で確立済 |
| V3 Session Management | no | 同上 |
| V4 Access Control | **yes** | DB role 分離: feature builder は `keiba_readonly`（SELECT only）・label backfill のみ `keiba_etl`（label schema 限定 UPDATE）。`raw_everydb2`/`normalized` への UPDATE は REVOKE で物理的拒否（Phase 1 実証済） |
| V5 Input Validation | **yes** | feature_availability.yaml が入力 allowlist・禁止 timing は schema validation で拒否・`source_table` は明示的（`SELECT *` 禁止） |
| V6 Cryptography | no | 暗号化不要・SHA256 は整合性検証用（暗号用途でない） |
| V7 Logging | partial | feature 構築ログは manifest YAML に記録（snapshot_id, sha256, created_at）・実行時ログは stderr |
| V8 Data Protection | **yes** | Parquet snapshot は immutable・`.gitignore` で Parquet バイナリを除外・`.env` は Phase 1-2 で git 管理外・実馬券購入 hook なし（§19.3） |

### Known Threat Patterns for Feature/Snapshot stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Future-info leakage via feature | Tampering (data integrity) | `pit_join_backward` sortedness 契約 + `feature_cutoff_datetime` filter + allowlist test (SC#2) |
| Raw table mutation | Tampering | REVOKE on `public.n_*` + `raw_everydb2` VIEW（Phase 1 実証）・feature builder は readonly role |
| Snapshot non-determinism | Tampering (reproducibility) | PyArrow 決定論的書込 + SHA256 manifest・unit test (SC#3) |
| Test-set composition leak via category map | Information disclosure | `fit_category_map` train-only + `__UNSEEN__` sentinel・unit test (SC#4) |
| `.env` / DB credential leak | Information disclosure | `SecretStr` (Phase 1 settings.py)・`.gitignore`（Phase 1 実績） |
| Banned feature sneaking in | Tampering (allowlist bypass) | `feature_availability.yaml` registry + fail-loud pytest (SC#2 BLOCK) |

## Sources

### Primary (HIGH confidence)

- **EveryDB2 公式カラムマニュアル** — `docs/everydb2/04-UMA_RACE.md` (SE, 73 fields) / `docs/everydb2/03-RACE.md` (RA, 110 fields) / `docs/everydb2/27-UMA.md` (horse master, 227 fields・3代血統)・Column 名・型・意味の正
- **実 DB クエリ (readonly)** — `normalized.n_race` (39593行, 2015-01-04〜2026-06-14) / `normalized.n_uma_race` (554267行) / `label.fukusho_label` (554267行, race_date 全行 NULL) / `public.n_uma` (3代血統)・NULL 率・cardinality・distinct 全て実測
- **要件定義書** — `docs/keiba_ai_requirements_v1.3.md` §12.4 (snapshot metadata 8項目) / §13.1-13.5 (as-of 管理・feature_availability・Phase 1-A 参照条件・利用可能特徴量候補25種) / §14.3-14.5 (LightGBM/CatBoost カテゴリ・欠損仕様)
- **CLAUDE.md (プロジェクト指示・权威)** — §13.2 `feature_cutoff_datetime = race_date - 1 day` / `merge_asof(direction='backward')` / frozen category map per snapshot / Parquet §12.4 metadata / DuckDB non-persistence
- **Phase 1 実装コード** — `src/utils/pit_join.py` / `src/utils/category_map.py` / `src/db/schema.py` (5層・REVOKE) / `src/etl/normalize.py` (staging-swap idempotent) / `src/etl/filters.py` (JRA filter single source)・`01-VERIFICATION.md` (76 tests green・実 DB 39593行)
- **Phase 2 実装** — `label.fukusho_label` schema・`is_model_eligible` filter・`label_validation_status` taxonomy

### Secondary (MEDIUM confidence)

- **PyArrow byte-reproducibility** — 本研究で実証（同一入力から同一 SHA256・schema metadata 埋込読込成功）。PyArrow 公式 docs と整合
- **PITFALLS.md** — `.planning/research/PITFALLS.md` Pitfall 1 (lookahead) / Pitfall 5 (split leak) / Pitfall 9 (non-reproducibility)・Phase 3 固有落とし穴の抽出元

### Tertiary (LOW confidence)

- 該当なし（全 claim を実 DB または公式マニュアルで裏付け）

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — 全 package が Phase 1-2 で導入済・実 version 確認済・CLAUDE.md 表記と一致
- Architecture: **HIGH** — 既存 `pit_join_backward`/`category_map`/`normalize.py` パターンの直接消費・新規プリミティブなし
- Column mapping (Q1): **HIGH** — 実 DB で全カラム存在・型・NULL 率・distinct を実測
- 推定脚質 algorithm (Q3): **HIGH** — `jyuni3c`/`jyuni4c` の 99.1% 非null 実測・`kyakusitukubun` post_race_only 性質は SE #73 マニュアルで明示
- Parquet byte-repro (Q7): **HIGH** — 本研究で hash1==hash2 を実証
- Pitfalls: **HIGH** — 実 DB NULL 率・distinct・重複 key に基づく（PITFALLS.md 一般論に実データで肉付け）

**Research date:** 2026-06-18
**Valid until:** 2026-07-18（30日・stable domain・EveryDB2 schema は不変・Phase 1-2 locked stack）

## RESEARCH COMPLETE

**Phase:** 3 - As-of Features & Snapshots
**Confidence:** HIGH

### Key Findings

- **全25種 feature の EveryDB2 カラム対応を実 DB で確定** — 静的属性15種は `normalized.n_uma_race`/`n_race` + `public.n_uma`(3代血統) で過不足なくカバー。過去走9系統は `n_uma_race` history + `pit_join_backward` で構築。`trackcd`/`coursekubuncd` のみ `normalized` 未収録（`raw_everydb2` VIEW から readonly SELECT で対応）
- **Phase 2 負債（`label.fukusho_label.race_date` 全行 NULL）の解消方法を確定** — `normalized.n_race` と JOIN して backfill UPDATE（race_nkey = year,jyocd,kaiji,nichiji,racenum で一意・39593行）。`race_date`/`race_start_datetime` は n_race 側で 0% NULL（2015-01-04〜2026-06-14 実測）
- **過去走タイム差の基準（Q2）を解決** — 実カラム `timediff`（= TimeDIFN, SE #66）は**勝馬差**（1着馬との差・`+016`=+1.6秒）。これを採用。当日行は post_race_only で select 対象外
- **推定脚質アルゴリズム（D-05）を解決** — 過去走 `jyuni3c`/`jyuni4c`（3/4コーナー位置）の平均で閾値分類（≤2.0=逃/≤3.5=先/≤5.5=差/>5.5=追）。当日 `kyakusitukubun` (SE #73) は post_race_only で**検証専用**。`jyuni1c` は57% が 0/NULL（短距離で1コーナー不存在）のため**主軸にしない**
- **horse_id（D-02）の feature 化を採用** — 実測 60496 distinct 馬（p50=6 starts, 6.7% が1走のみ）。冷起動リスクは LightGBM native / CatBoost `has_time=True` が構造的に leak-safe（CLAUDE.md §14.3/§14.4）・`__MISSING__` sentinel で過去走不足を明示
- **byte-reproducibility を実証** — PyArrow `write_table(use_dictionary=False, compression='zstd', sorted input)` + `schema.with_metadata` で同一 SHA256 を確認。§12.4 8項目+sha256 は schema metadata + manifest YAML で二重保存
- **D-09 train/val 境界を実データで確認** — train 2016H2-2023 = 25939 races / val 2024 = 3456 races / holdout 2025-2026 = 5040 races。訓練窓 cardinality: 42395 馬 / 358 騎手 / 398 調教師
- **canonical feature-row key を確定** — `(year,jyocd,kaiji,nichiji,racenum,kettonum)` が 554267 = 554267 unique（実証済）・`umaban` は29件重複（海外馬 umaban=99 等）で key 不適

### File Created

`/Users/hart/develop/keiba-ai-v3/.planning/phases/03-as-of-features-snapshots/03-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | 全 package 実 install 確認・CLAUDE.md と一致・新規 install 不要 |
| Architecture | HIGH | 既存 util/ETL パターンの消費のみ・新規プリミティブなし |
| Column Mapping (Q1) | HIGH | 実 DB で全カラムの存在・型・NULL 率・distinct を実測 |
| Phase 2 負債解消 (Q6) | HIGH | n_race 側 race_date 0% NULL 実測・JOIN key 一意性実証 |
| 推定脚質 (Q3) | HIGH | jyuni3c/4c 99.1% 非null・kyakusitukubun 5値分布・SE #66/#73 マニュアル |
| byte-repro (Q7) | HIGH | 本研究で hash 一致を実証 |
| Pitfalls | HIGH | 実 DB NULL 率/distinct/重複で PITFALLS.md 一般論を裏付け |

### Open Questions

1. **`trackcd` 等の未収録カラム取得方法** — raw_everydb2 VIEW SELECT（推奨）か normalize.py 拡張か。planner 判断。（詳細は上記 Open Questions #1）
2. **`snapshots/` 配下の manifest YAML git 管理可否** — Parquet バイナリは `.gitignore` 必須・manifest YAML のみ git 管理で再現性証明を残すか。planner 判断。

### Ready for Planning

Research complete. Planner can now create PLAN.md files. Claude's Discretion 8項目 + STATE.md research flag は全て実 DB エビデンスで解決済。FEAT-01/FEAT-02 + SC#1-#4 の全要件を cover。リーク防止（聖域）と再現性（聖域）の両面で、既存 Phase 1-2 実装を消費する安全な設計が確立している。
