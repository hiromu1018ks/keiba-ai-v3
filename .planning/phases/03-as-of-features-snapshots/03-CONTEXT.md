# Phase 3: As-of Features & Snapshots - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

リーク防止の背骨を実装に落とすこと。Build-Order DAG の step 4（as-of 特徴量・スナップショット）。Phase 1 基盤（5層スキーマ・normalized ETL・リーク防止プリミティブ bootstrap）と Phase 2 ラベル（`fukusho_hit_validated`）の上に乗り、Phase 4 モデルが** stamped Parquet のみ**で学習できる PIT-correct な特徴量マトリクスと不変スナップショットを届ける。具体的には：

1. **feature_availability registry の本格運用（FEAT-01 / §13.3）** — Phase 1 は枠＋6項目スキーマのみ（`features: []` 空・D-15）。Phase 3 が §13.5 全候補（約25種）の実エントリを埋め、各 feature に `available_from_timing` / `leakage_risk_level` を付与。allowlist test が禁止 timing を0件検査（SC#2）
2. **PIT-correct feature builder（FEAT-01 / §13.2 / SC#1）** — 各 feature 行に `as_of_datetime` / `feature_cutoff_datetime` / `race_start_datetime` / `feature_snapshot_id` / `feature_availability_version` を付与。過去走ローリングは `pit_join_backward`（`merge_asof(direction='backward')`）で「そのレース cutoff 以前の走歴のみ」を結合
3. **Phase 1-A allowlist（FEAT-02 / §13.4 / SC#2）** — 当日馬場/天候/馬体重/当日オッズ/人気集中度/レース後通過順・上がり・走破タイム/当日レース結果由来集計 を fail-loud test で排除
4. **不変 versioned Parquet スナップショット（§12.4 / SC#3）** — 埋め込みメタデータ（`dataset_version` / `feature_snapshot_id` / `label_version` / `prediction_timing` / `feature_cutoff_datetime` / `train_period` / `validation_period` / `created_at` + sha256）で再現性証明。再読込で同一バイト（hash 検証）
5. **frozen category map の実データ fit（SC#4）** — 訓練窓のみ fit、val/test に `__UNSEEN__` / `__MISSING__` で適用（Phase 1 D-14 の本格消費）

**境界＝検証ゲート。** EV・バックテスト・評価は明示的に後続フェーズ。Phase 3 は特徴量とスナップショットのみ。

</domain>

<decisions>
## Implementation Decisions

### 特徴量スコープ（FEAT-02 / §13.5）
- **D-01: §13.5 全候補（約25種）を Phase 3 で網羅実装** — 静的属性（馬齢/性別/斤量/騎手/調教師/種牡馬/母父/競馬場/距離/芝ダート/右回り左回り/コース条件/クラス正規化/馬番/枠番）＋過去走ローリング9系統（着順/タイム差/上がり/通過順/距離/馬場状態/競馬場/間隔/推定脚質）すべて。Phase 3 が長期化するが、Phase 4 は特徴量完成済みで着手できる。代表サブセット（過去走を削る）ではなく、最初からフルセット
- **D-02: horse_id（出走馬ID）の扱いは Claude 裁量** — 実データで horse_id の出現頻度/分散を確認し、過去走ローリングで能力を捕捉できているか検証の上で feature 化の可否を判断。指針: 冷起動（新馬/2歳・履歴ゼロ）過学習リスクが高ければ **key 専用**（結合キー/行識別のみ）に倒す。騎手/調教師/種牡馬/母父は Phase 1 D-14 どおり frozen category_map 経由で feature 化（確定）

### 過去走ローリング設計（§13.5 / SC#1）
- **D-03: lookback = 直近5走** — JRA 直近成績表の標準。5走溜まり次第対象化（feature warm-up 2015-16 前半の馬も段階的に対象）。5走未満の馬は不足分を `__MISSING__` sentinel で明示（silent fill 禁止・Phase 1 D-13 整合）
- **D-04: 集約 = 平均＋最新値＋標準偏差の3軸** — 過去走数値（タイム差/上がり/着順等）を5走平均（基本能力）＋最新値（近況）＋標準偏差（一貫性）で表現。LightGBM/CatBoost は多重共線性に強く3軸とも有効。単一軸（平均のみ/加重平均）より情報量が高い
- **D-05: 推定脚質（逃げ/先行/差し/追込）は過去走の通過順から導出** — §13.5 注記のとおり、**当日レースの通過順は使用禁止**（post_race_only・リーク）。過去走の通過順パターンから事前推定脚質を算出し、「逃げ馬数」等のレース文脈特徴量はこの推定値からのみ構築。導出アルゴリズムの細部は Claude 裁量（計画者）

### cutoff と予測タイミング（FEAT-01 / §13.2 / §13.4 / SC#1）
- **D-06: feature_cutoff_datetime は日付粒度（`race_date - 1 day`）** — 当日すべての情報を一律排除し、**同日別レースの混入も構造的に防止**（午前レース結果が午後レースに漏れない）。§13.4 当日禁止リストと整合し実装シンプル。`race_start_datetime` は §13.2 必須項目として保持するが、PIT cutoff の基準には使わない。Phase 2 負債（`label.fukusho_label.race_date` 全行 NULL）も、この cutoff 用に race_date を設定する方向で Phase 3 で解消
- **D-07: Phase 1-A allowlist 境界は要件固定** — 許可 `available_from_timing ∈ {entry_confirmed, post_position_confirmed}`（出馬表・馬番・枠番確定後）。禁止 `{race_day_morning, body_weight_announced, odds_snapshot_available, post_race_only, same_day_aggregate}`。SC#2 の fail-loud test が禁止 timing の feature を0件であることを検査（構造的ブロック・Phase 1 D-01/D-13 踏襲）

### スナップショット戦略（§12.4 / SC#3）
- **D-08: 永続先 = Parquet のみ** — 埋め込みメタデータ（§12.4 の8項目 ＋ sha256）で再現性を証明。manifest は JSON/YAML で `snapshots/` 配下に保持。**DB に feature 層/テーブルは新設しない**（5層スキーマ `raw_everydb2`/`normalized`/`label`/`prediction`/`backtest` を維持・keep it simple・CLAUDE.md「DuckDB は永続層でない」整合）。SC#3 のバイト再現性は Parquet メタデータ＋hash で充足
- **D-09: feature matrix は全期間1枚・代表デモ境界は train 2016H2-2023 / val 2024** — PIT-correct な特徴量マトリクス Parquet は **2016H2〜2026現在の全期間を1枚**で生成（特徴量値は train/val 分割に依存しない）。Phase 3 が埋める代表デモ境界は train 2016H2-2023 / val 2024。**2025-2026 は Phase 4-5 の最終 test・BT 用に温存**。frozen category map は train 窓（2016H2-2023）で fit。本物の train/calib/test および BT-1..5 フル行列分割は Phase 4-5

### Claude's Discretion（研究者/計画者に委ねる）
- **horse_id の feature 化可否** — D-02。実データの出現頻度/分散で信号の有無を判定
- **推定脚質の導出アルゴリズム** — D-05。過去走通過順からの分類方式（閾値/ルールベース）。当日通過順不使用だけが制約
- **過去走タイム差の基準** — 勝馬タイム差か平均タイム差か等、§13.5 は未規定。実データの利用可能カラムで確定
- **`race_start_datetime` 欠損時の fallback** — D-06 で日付粒度を選んだため影響は限定的だが、欠損率を実データで確認
- **実データの最終 race_date 確定** — 2016H2〜2026 の実範囲を確定し train/val 境界と整合
- **`feature_availability.yaml` のエントリ粒度** — per-feature か feature-group か。25種を網羅する実エントリ設計
- **Parquet 物理構造** — partition（race_date 等）/ row-group サイズ。性能要件（Phase 4 学習の読込効率）と keep it simple のバランス。DuckDB で zero-copy 読込可能な構造

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §13.1-13.5 — as-of 管理の目的・必須項目（`as_of_datetime`/`feature_cutoff_datetime`/`race_start_datetime`/`feature_snapshot_id`/`feature_availability_version`）・feature_availability 定義（6項目＋`available_from_timing` 候補6種）・Phase 1-A 参照条件（当日禁止リスト）・利用可能特徴量候補（§13.5 約25種・推定脚質注記）。FEAT-01/02・SC#1/#2 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §12.4 — 学習用データセット保存（Parquet・8項目メタデータ）。D-08・SC#3 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §14.3-14.5 — LightGBM/CatBoost カテゴリ・欠損仕様（target encoding 禁止・負値コード回避・欠損理由区別・CatBoost has_time）。category_map util 設計と SC#4 の根拠（Phase 4 本格適用だが feature 設計に関与）
- `docs/keiba_ai_requirements_v1.3.md` §17.1-17.3 — スタック・`src/` レイアウト・テストコード一覧（feature_cutoff / PIT / split 係のテスト）

### EveryDB2 公式マニュアル（実データ依存の正・ユーザー提供）
- `docs/everydb2/04-UMA_RACE.md` — 出走馬（SE, 73フィールド）。過去走ローリングの主原料（着順 `KakuteiJyuni`/入線順位 `NyusenJyuni`/通過順/上がり3F/タイム差/馬体重 `BaTaijyu`/血統）。推定脚質の通過順カラム特定に使用
- `docs/everydb2/03-RACE.md` — レース（RA, 110フィールド）。race-level 文脈（競馬場/距離/芝ダ/右左/コース条件/クラス）。`race_date`/`race_start_datetime` の所在
- `docs/everydb2/INDEX.md` — 全59テーブル＋RecordSpec。過去走集計に必要な SE/RA 以外のソース特定
- `docs/everydb2/CODE.md` — ⚠ スクレイピング不完全（Phase 1 D-10）。コード表参照のみ、補完必須

### プロジェクト計画・状態
- `.planning/ROADMAP.md` — Phase 3 成功基準#1-#4・8フェーズ strict DAG。Phase 3 =「PIT-correct feature builder + immutable versioned Parquet snapshots」
- `.planning/REQUIREMENTS.md` — FEAT-01/02（Phase 3 割当）・全25要件トレーサビリティ
- `.planning/STATE.md` — **Blockers/Concerns に「Phase 3 research flag: `available_from_timing` mapping depends on exact JRA-VAN data-availability timings」を明示** → `/gsd-plan-phase --research-phase 3` を想定
- `.planning/PROJECT.md` — Core Value（リーク防止＝聖域）・Key Decisions・Out of Scope・Context（feature warm-up 2015-16前半・主対象 2016H2以降・BT は2019夏以降）

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/01-trust-foundation/01-CONTEXT.md` — **D-05（5層スキーマ・feature 層なし）/ D-13（silent fallback 禁止）/ D-14（リーク防止プリミティブ importable＋smoke）/ D-15（feature_availability.yaml 枠＋6項目スキーマ・Phase 3 で本格運用）/ D-16（utils/ 集約）/ D-17（leak assert smoke）** が Phase 3 の直接の前提
- `.planning/phases/02-fukusho-labels/02-CONTEXT.md` — **D-03（`is_model_eligible` フィルタで下流が絞り込み）**・ラベルテーブル保持項目。Phase 3 は `label.fukusho_label` から `fukusho_hit_validated` を目的変数として結合
- `.planning/phases/01-trust-foundation/01-VERIFICATION.md` — Phase 1 実装内容（`normalized.n_race`=39593行・5層スキーマ・REVOKE 実効性・76テスト green）・`n_odds_tanpuku`=単複共用確定事項

### コード契約（実装済み・Phase 3 が消費）
- `src/utils/pit_join.py` — `pit_join_backward(observations, history, on_cutoff, on_asof, by, tolerance)`。**呼出元が事前ソート必須**（未ソートは即 `raise ValueError`・REVIEWS HIGH #1/#3）。過去走ローリングの as-of 結合に使用
- `src/utils/category_map.py` — `fit_category_map`（訓練窓のみ）→ `apply_category_map`（val/test・`__UNSEEN__`/`__MISSING__`・非負 int32）。高基数 ID の frozen map
- `src/config/feature_availability.yaml` — `features: []` 空・`schema_version 0.1.0`・6項目スキーマ定義済み。Phase 3 が実エントリを追加
- `CLAUDE.md` — 技術スタック・リーク防止設定（§13.2 `feature_cutoff_datetime = race_date - 1 day`・`merge_asof(direction='backward')`・frozen category map per snapshot・Parquet §12.4 metadata）・Postgres↔Parquet↔DuckDB interop（プロジェクト指示として权威）

### プロジェクト研究
- `.planning/research/SUMMARY.md` — Build-Order DAG・Phase 3 位置づけ・PIT/snapshot アーキテクチャ
- `.planning/research/PITFALLS.md` — "Looks Done But Isn't" チェックリスト（特徴量/as-of 系の落とし穴）
- `.planning/research/ARCHITECTURE.md` — 層構造・PIT/snapshot アーキテクチャ・`src/` 構成（`features/` は Phase 3 で新設）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/utils/pit_join.py` (`pit_join_backward`)** — 過去走ローリングの as-of 結合にそのまま使用。observations（対象レース行・`feature_cutoff_datetime` 昇順ソート済み）に、history（過去出走成績・`as_of_datetime` 昇順ソート済み）を `by=horse_id` で cutoff 以前の最新値を付与。**呼出元の事前ソートが契約**（builder 側で `.sort_values()` 必須・ソート済み unit test 推奨・§17.3）
- **`src/utils/category_map.py` (`fit_category_map`/`apply_category_map`)** — 騎手/調教師/種牡馬/母父（＋ horse_id を feature 化する場合）の frozen category map。訓練窓（D-09 の train 2016H2-2023）でのみ fit、val/test に適用。`__UNSEEN__`/`__MISSING__` sentinel・非負 int32 保証（LightGBM 要件）
- **`src/utils/group_split.py` / `calibrator.py`** — Phase 1 bootstrap 済み。Phase 3 では feature matrix 作成後に代表デモ分割（smoke）で軽く使用、本格適用は Phase 4-5
- **`src/config/feature_availability.yaml`** — 枠＋6項目スキーマ（`feature_name`/`feature_group`/`available_from_timing`/`source_table`/`cutoff_rule`/`leakage_risk_level`）定義済み。Phase 3 が §13.5 約25種の実エントリを追加。`label_spec.yaml`/`class_normalization.yaml` の YAML→dataclass 読込パターン（Phase 1 D-07）を再利用
- **`src/etl/normalize.py`** — `staging-table-swap` idempotent load ＋ `_JRA_FILTER`（`jyocd BETWEEN '01' AND '10'`）＋ 全 varchar 明示キャスト。feature matrix の Parquet 書込も idempotent/hash-stable なパターンで
- **`src/db/connection.py`** — `make_pool(role='readonly')` で raw/normalized/label を SELECT。feature builder は **readonly ロール**（features は Parquet へ書出・DB には書かない・D-08）

### Established Patterns
- **5層スキーマ（Phase 1 D-05 / `src/db/schema.py`）:** `raw_everydb2`/`normalized`/`label`/`prediction`/`backtest`。**`feature` 層は非存在** → 特徴量は Parquet（D-08）。reader ロールは `normalized`/`label` に USAGE+SELECT 済み（Phase 1-2 GRANT）
- **hybrid gate（Phase 1 D-01 / Phase 2 D-02）:** 構造的欠陥=ブロック（pytest/CI fail）・量的異常=参考レポート。Phase 3 の allowlist test（SC#2）は**構造的ブロック**（禁止 timing feature が1件でも FAIL）
- **silent fallback 禁止（Phase 1 D-13）:** 5走未満の過去走欠損は `__MISSING__` sentinel で明示。見せかけの通過を許さない
- **raw read-only（Phase 1 D-06）:** feature builder は raw/normalized/label から SELECT のみ。Parquet へ書出
- **PIT leak-prevention（CLAUDE.md）:** `merge_asof(direction='backward')` ＋ `feature_cutoff_datetime = race_date - 1 day`（D-06）・禁止カラムは select しない（§13.4・`feature_availability` が監査可能 map・SC#2）

### Integration Points
- **READ（readonly ロール）:**
  - `normalized.n_race`（RA: race-level 文脈・`class_code_normalized`/`race_date`/`race_start_datetime`/競馬場/距離/芝ダ 等）
  - `normalized.n_uma_race`（SE: 出走/着順/通過順/上がり/タイム差/馬体重/血統・過去走ローリング原料）
  - `label.fukusho_label`（目的変数 `fukusho_hit_validated`・`is_model_eligible`/`label_validation_status` フィルタ・`sales_start_entry_count`）
- **WRITE（Parquet・`snapshots/` 配下）:**
  - feature matrix Parquet（§12.4 メタデータ埋め込み・全期間1枚）＋ manifest JSON/YAML
  - frozen category map artefact（`joblib`/`pickle`・train 窓 fit）— snapshot と並存
- **CONSUMED BY（下流フェーズ）:**
  - Phase 4（model）: stamped Parquet のみで学習・`p_fukusho_hit` 算出（SC#1）
  - Phase 5（backtest）: BT-1..5 窓で同 matrix から時系列分割（D-09・2025-2026 温存）
  - Phase 8（adversarial audit）: SC#2 allowlist test・`feature_cutoff_datetime` enforcement・PIT lookahead injection 検出（TEST-01）

</code_context>

<specifics>
## Specific Ideas

- **`src/features/` は Phase 3 で新設**（Phase 1 は `etl/`/`utils/`/`config/`/`db/` のみ・`features/` 未存在）。feature builder 本体・snapshot writer を `src/features/` 配下に配置（§17.2 レイアウト）
- **feature matrix は分割非依存** — 過去走ローリングも静的属性も「cutoff 以前の情報のみ」で算出されるため、train/val/test がどこで切られても特徴量値は同一。これが「全期間1枚」を可能にし、Phase 4-5 が任意の時系列分割を同 matrix から carve できる根拠
- **`horse_id` の §13.5 解釈** — 「出走馬ID」は結合キー/行識別として必須だが、feature 化（カテゴリ特徴量）は D-02 で Claude 裁量。冷起動過学習リスクと個馬信号のトレードオフを実データで判定
- **Phase 2 負債の解消** — `label.fukusho_label.race_date` 全行 NULL は Phase 3 の cutoff（D-06）で必要なため、race_date を設定（normalized.n_race からの結合バックフィル）して解消。ラベルテーブル（Phase 2 ドメイン）への小修正だが cutoff の前提
- **「逃げ馬数」等のレース文脈特徴量** — §13.5 注記のとおり当日通過順ではなく**推定脚質（D-05）からのみ**算出。post_race_only リークを避けるため feature_availability で明示タグ付け

</specifics>

<deferred>
## Deferred Ideas

- **Phase 4:** `fukusho_hit_validated` を目的変数に Phase 1-A モデル学習・`p_fukusho_hit` 算出・`CalibratedClassifierCV(cv='prefit')` 本格適用・LightGBM/CatBoost カテゴリ・欠損の実データ検証。Phase 3 は特徴量マトリクスとスナップショットの生成まで
- **Phase 5:** BT-1..BT-5 バックテスト窓のフル行列・固定 `odds_snapshot_policy` 仮想購入シミュレータ・返還/競走中止の `effective_stake` 計算。Phase 3 は代表デモ境界のみ（D-09）
- **Phase 7:** Streamlit での snapshot 一覧性・特徴量確認画面。Phase 3 は Parquet＋manifest のみ
- **Phase 8:** SC#2 allowlist test・`feature_cutoff_datetime` enforcement・synthetic-lookahead injection（T の特徴量が T+1 のデータを使う検出）に対する対抗的監査テスト（TEST-01）。Phase 3 で実装する allowlist/PIT 機構が監査対象
- **Phase 1-B（将来）:** 開催日朝モデル・発走直前モデル。D-06 の時刻粒度 cutoff（`race_start_datetime - δ`）は Phase 1-B 拡張時に意味を持つ。Phase 1-A は日付粒度で十分
- **Phase 2 ETL 拡張（Phase 3.1: Timediff/Babacd Rolling Restoration・挿入済み・Phase 3 gap-closure 03-05 完了後に /gsd-plan-phase 03.1 で計画）:** EveryDB2 normalized ETL を拡張して `timediff`（勝馬差 TimeDIFN）・`babacd`（過去走馬場状態）の source カラムを normalized.n_uma_race に持ち込む。その後 Phase 3 の rolling_timediff_* / rolling_babacd_* 計6 feature を registry・rolling.py・availability reserved の三者から再登録し、Phase 1-A rolling features を 18 → 24（8系統×3軸）に拡張。Phase 3 gap-closure (03-05・CR-01) で silent 全 NaN breach を解消するため一時削除した。

None — discussion stayed within phase scope

</deferred>

---

*Phase: 3-As-of Features & Snapshots*
*Context gathered: 2026-06-18*
