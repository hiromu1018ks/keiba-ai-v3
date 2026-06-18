# Phase 3: As-of Features & Snapshots - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-18
**Phase:** 3-As-of Features & Snapshots
**Areas discussed:** 特徴量スコープ(厚み), 過去走ローリング設計, cutoffと予測タイミング, スナップショット戦略

---

## 特徴量スコープ(厚み)

### Q1: Phase 3 の Phase 1-A 特徴量マトリクスの網羅度

| Option | Description | Selected |
|--------|-------------|----------|
| 代表サブセット(推奨) | 静的属性+過去走ローリング(着順/タイム差/上がり/通過順 の直近N走)。機械を実際の履歴で動作させ Phase 4 に意味ある特徴量を渡す。馬場状態/競馬場/距離/推定脚質は Phase 4 拡張。 | |
| §13.5 全候補(約25種) | 過去走馬場状態/競馬場/距離/間隔/推定脚質 含む全候補を Phase 3 で網羅。Phase 3 長期化するが Phase 4 は特徴量完成済みで着手。 | ✓ |
| 最小証明セット | 静的属性のみ(過去走ローリングなし)。PIT joiner を実履歴で動かさないためリーク防止検証が形骸化し、Phase 4 の予測力も実質的に機能しない。非推奨。 | |

**User's choice:** §13.5 全候補(約25種)
**Notes:** 推奨(代表サブセット)を提示したが、ユーザーはフルセットを選択。Phase 3 を長めにしても Phase 4 に完成済み特徴量を渡すことを優先。過去走9系統すべてが PIT joiner で実検証されるため、リーク防止のカバレッジも最大になる。

### Q2: 出走馬ID(horse_id)をモデル特徴量として扱うか（§13.5「出走馬ID」の解釈）

| Option | Description | Selected |
|--------|-------------|----------|
| key 専用(推奨) | horse_id は結合キー/行識別のみ。高基数かつ新馬/2歳で履歴ゼロ→過学習リスク。能力は過去走ローリングで捕捉。騎手/調教師/種牡馬/母父のみ category feature。 | |
| horse_id も feature 化 | horse_id も frozen category_map で特徴量化。個馬バイアスを直接取り込めるが、履歴浅い馬は __UNSEEN__ に集中し冷起動に弱い。 | |
| Claude に委ねる | 実データで horse_id の出現頻度/分散を確認し、意味のある信号か計画者が判断。 | ✓ |

**User's choice:** Claude に委ねる
**Notes:** 実データで horse_id の信号の有無を検証して決定。指針は key 専用（過学習回避）。

---

## 過去走ローリング設計

### Q1: 過去走ローリング特徴量の lookback(参照窓)

| Option | Description | Selected |
|--------|-------------|----------|
| 直近5走(推奨) | JRA 直近成績表の標準。信号の厚みと冷起動耐性のバランス。warm-up 期の馬も5走溜まり次第対象化。不足時 __MISSING__。 | ✓ |
| 直近3走 | 最近の調子重視。信号薄・欠損増。 | |
| 直近10走 | 長期安定度。古い走歴のノイズ。 | |
| 1年内全走 | 頭数可変(期間で切る)。集計複雑・長期離脱馬で0走。 | |

**User's choice:** 直近5走
**Notes:** JRA 標準に準拠。5走未満は __MISSING__ sentinel で明示（silent fill 禁止）。

### Q2: 5走分の過去走数値の集約

| Option | Description | Selected |
|--------|-------------|----------|
| 平均+最新+安定度(推奨) | 5走平均(基本能力)+最新値(近況)+標準偏差(一貫性)の3軸。GBDT は多重共線性に強く有効。推定脚質は通過順から別途導出。 | ✓ |
| 平均のみ | 5走の単純平均。シンプル。近況/一貫性の信号は失う。 | |
| 加重平均(recency) | 新しい走ほど重い加重平均。近況重視だが1軸に集約。 | |

**User's choice:** 平均+最新+安定度
**Notes:** 3軸で能力/近況/一貫性を表現。推定脚質は過去走通過順から別途導出（当日通過順禁止＝§13.5 注記のリーク制約）。

---

## cutoffと予測タイミング

### Q1: feature_cutoff_datetime の粒度と PIT 結合の基準

| Option | Description | Selected |
|--------|-------------|----------|
| 日付粒度(推奨) | race_date - 1 day。当日情報を一律排除し同日別レース混入も構造的に防止。§13.4 当日禁止と整合・実装シンプル。race_start_datetime は保持するが cutoff には不使用。Phase 2 負債(label.race_date NULL)解消と整合。 | ✓ |
| 時刻粒度 race_start-δ | race_start_datetime - δ。同日午前の情報を理論上取り込めるが Phase 1-A は当日禁止なので実質同じ。複雑化。Phase 1-B 拡張時に意味を持つ。 | |
| Claude に委ねる | 実データで race_start_datetime の欠損率を確認し選択。 | |

**User's choice:** 日付粒度(race_date - 1 day)
**Notes:** 同日別レースの混入を構造的に防止（午前レース→午後レースのリーク）。allowlist 境界は要件固定（許可 entry_confirmed/post_position_confirmed・禁止 race_day_morning/body_weight_announced/odds_snapshot_available/post_race_only/same_day_aggregate・SC#2 が0件検査）。

---

## スナップショット戦略

### Q1: 特徴量スナップショットの永続先

| Option | Description | Selected |
|--------|-------------|----------|
| Parquetのみ(推奨) | 埋め込みメタデータ(§12.4 8項目+sha256)で再現性証明。manifest は JSON/YAML で snapshots/ 配下。DB 層を増やさず keep it simple。SC#3 のバイト再現は充足。 | ✓ |
| +PG manifestテーブル | PostgreSQL に薄い feature_snapshot レジストリ。SQL で一覧・照合できるが feature 層新設と権限管理が増える。 | |
| Claude に委ねる | Phase 7 Streamlit での snapshot 一覧性要件を見て判断。 | |

**User's choice:** Parquetのみ
**Notes:** 5層スキーマ（feature 層なし）を維持。DB feature テーブルは新設しない。CLAUDE.md「DuckDB は永続層でない」・keep it simple に整合。

### Q2: Phase 3 代表デモの train/val 境界線

| Option | Description | Selected |
|--------|-------------|----------|
| train-2023/val 2024(推奨) | matrix は全期間(2016H2-2026)を1枚生成。代表デモ境界 train 2016H2-2023/val 2024。2025-2026 は Phase 4-5 test・BT 用に温存。 | ✓ |
| train-2024/val 2025 | 代表境界を後ろにずらす。2026 のみ test 温存。 | |
| Claude に委ねる | 実データの最終 race_date と Phase 5 BT-1..5 窓を整合させて計画者が決定。 | |

**User's choice:** train-2023/val 2024
**Notes:** ユーザーから「2026年までデータはあるんじゃないの？」との質問あり。誤解を解消：feature matrix（Parquet 本体）は train/val 分割に依存せず 2016H2-2026 全期間を1枚で生成。2023 は matrix の終端ではなく**代表デモの境界線**。本物の train/calib/test/BT 分割は Phase 4-5。2025-2026 は最終 test・BT 用に温存。

---

## Claude's Discretion

- **horse_id の feature 化可否** — 実データの出現頻度/分散で信号の有無を判定（基本は key 専用）
- **推定脚質の導出アルゴリズム** — 過去走通過順からの分類方式。当日通過順不使用だけが制約
- **過去走タイム差の基準** — 勝馬タイム差か平均タイム差か。実データの利用可能カラムで確定
- **`race_start_datetime` 欠損時の fallback** — 日付粒度選択で影響は限定的、欠損率を実データで確認
- **実データの最終 race_date 確定** — 2016H2-2026 の実範囲を確定し train/val 境界と整合
- **`feature_availability.yaml` のエントリ粒度** — per-feature か feature-group か
- **Parquet 物理構造** — partition/row-group サイズ。DuckDB zero-copy 読込可能な構造

## Deferred Ideas

- Phase 1-B（将来）の時刻粒度 cutoff（race_start_datetime - δ）— Phase 1-A は日付粒度で十分
- その他 Phase 4-8 の後続作業は CONTEXT.md `<deferred>` 参照

None outside phase scope — discussion stayed within Phase 3 boundary
