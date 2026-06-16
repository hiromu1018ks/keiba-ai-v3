# Phase 1: Trust & Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 1-Trust & Foundation
**Areas discussed:** 品質ゲートの扱い, raw/normalized 分離と不変性, クラス正規化の参照ソース, リーク防止 bootstrap 範囲

---

## 品質ゲートの扱い（DATA-01）

| Option | Description | Selected |
|--------|-------------|----------|
| ハイブリッド | 構造的欠陥はブロッキング、量的異常は参考レポート | ✓ |
| 完全ブロッキング | 全異常を pytest/CI で fail | |
| 参考レポートのみ | verdict 付きで人間判断、自動ブロックなし | |

| Option | Description | Selected |
|--------|-------------|----------|
| モデル主要テーブル | レース/出走/成績/払戻/オッズ の5系統中心 | |
| 主要＋マスタ周辺 | 5系統＋馬/騎手/調教師/馬場等マスタ | ✓ |
| EveryDB2全テーブル | 取得全テーブル網羅 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 実測2段階 | 初回レポート→実測で主要項目に閾値設定 | ✓ |
| 厳格事前定義 | NULL0%・重複0%等を事前固定 | |
| 閾値なし | 数値・分布の記録のみ | |

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown+JSON | reports/ に人間用MD＋機械判定用JSON | ✓ |
| DuckDB対話ベース | 生クエリ可能な形 | |
| CLI標準出力 | 端末表示 | |

**User's choice:** ハイブリッド／主要＋マスタ周辺／実測2段階／Markdown+JSON（すべて推奨）
**Notes:** Core Value（信頼性）と EveryDB2 既知のデータ揺れのバランスを重視。対象テーブルは docs/everydb2/INDEX.md の RecordSpec で特定可能と判明。

---

## raw/normalized 分離と不変性（DATA-02）

| Option | Description | Selected |
|--------|-------------|----------|
| PG別スキーマ | raw_everydb2/normalized/label/prediction/backtest の5スキーマ | ✓ |
| テーブルプレフィックス | raw_/norm_ 等で1スキーマ内 | |
| 別データベース | raw用DBと派生層用DB分離 | |

| Option | Description | Selected |
|--------|-------------|----------|
| ロール+ハッシュ | 読取専用ロール＋ETL前後ハッシュアサーション | ✓ |
| ハッシュ検証のみ | 検証で担保、DB権限触らず | |
| DB権限のみ | ロール物理保護、ハッシュ省略 | |

| Option | Description | Selected |
|--------|-------------|----------|
| src/config(YAML/dataclass) | Git管理・テスト容易 | ✓ |
| Postgresマスタテーブル | DB内管理 | |
| ハイブリッド | クラス正規化はconfig、汎用マスタはPostgres | |

| Option | Description | Selected |
|--------|-------------|----------|
| psycopg3+Python | 型/コード/クラス変換を明示的実装 | ✓ |
| DuckDB COPY中心 | postgres_scanner経由 | |
| SQL(CTAS)中心 | CREATE TABLE AS SELECT | |

**User's choice:** PG別スキーマ／ロール+ハッシュ／src/config／psycopg3+Python（すべて推奨）
**Notes:** §12.2 論理層を PostgreSQL スキーマに1:1マップ。Pitfall 7 等の変換ロジックの可読性・テスト容易性を優先。

---

## クラス正規化の参照ソース（DATA-03 / Pitfall 7）

| Option | Description | Selected |
|--------|-------------|----------|
| 要件§12.3＋実データ照合 | §12.3骨格＋EveryDB2個別テーブル仕様＋実データ照合 | ✓ |
| JRA公式のみ正 | JRA公式コード一覧を唯一の正 | |
| EveryDB2マスタ優先 | EveryDB2内コードマスタを正 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 明確基準日 | race_date分岐、境界日は研究者が確定・定数化 | ✓ |
| 名称から推定 | 1勝クラス等の名称出現で事後判定 | |
| 境界日を要件に委ねる | 都度確認、定数化しない | |

| Option | Description | Selected |
|--------|-------------|----------|
| 別コードから | gradeコード/重賞フラグ等から導出 | ✓ |
| 名称マッチ | G1/オープン等の名称パターン | |
| 別項目+名称補完 | 別コード優先・欠損時名称 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 厳格エラー | unresolved として記録・隔離 | ✓ |
| name_raw推定 | 最寄りクラス推定 | |
| NULLで通過 | 後段で除外 | |

**User's choice:** 「対応表出所」の質問意図を確認後、§12.3＋EveryDB2個別仕様＋実データ照合 を採用。他3つは推奨通り。
**Notes:** ユーザー提供 docs/everydb2/ で実データ依存の疑問が解決。CODE.md はスクレイピング不完全（コード表1エントリのみ、2007競走条件コード全値欠落）のため補完必須と判明。code 005 が 500万下(前)/1勝クラス(後)をまたぐが class_level_numeric は連続 — Pitfall 7 の核心。

---

## リーク防止 bootstrap 範囲（成功基準#4）

| Option | Description | Selected |
|--------|-------------|----------|
| importable+smoke | 4プリミティブを実体実装＋各smoke test通過 | ✓ |
| 最小スタブ | シグネチャ+docstring程度 | |
| 完全+実データ検証 | 境界ケース検証まで | |

| Option | Description | Selected |
|--------|-------------|----------|
| src/config(YAML) | §13.3項目をYAML管理 | ✓ |
| Postgresテーブル | DB管理 | |
| コード内(dataclass) | Python定義 | |

| Option | Description | Selected |
|--------|-------------|----------|
| utils/集約 | pit_join/group_split/category_map/calibrator を utils/に | ✓ |
| 専用モジュール | src/leak_prevention/ 新設 | |
| 層に分散 | 各層に配置 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 単体+要所assert | 基本動作＋sortedness/disjoint/__UNSEEN__/時系列順序 | ✓ |
| 単体動作のみ | エラーなく動くことのみ | |
| 包括的(境界含む) | 空入力/重複/未来時刻等 | |

**User's choice:** importable+smoke／src/config(YAML)／utils/集約／単体+要所assert（すべて推奨）
**Notes:** ROADMAP 成功基準#4 が importable+smoke を明記済み。Phase 3/4 の実データパイプラインで立即利用可能な状態にする。

---

## Claude's Discretion

- 接続設定管理（.env + pydantic-settings、機密値は文書化しない）
- 現在の EveryDB2 配置と raw_everydb2 スキーマへのマッピング（研究者が plan-phase で実DB確認）
- uv プロジェクト初期化・pytest/ruff 構成（§17.1-17.3 準拠）
- 品質レポート実行タイミング（§6.4 初回確認＋ブロック要素は pytest 組込）

## Deferred Ideas

- Phase 2: 払戻テーブル突合ロジック、sales_start_entry_count 復元
- Phase 3: feature_availability registry 本格運用・allowlist test・Parquet スナップショット
- Phase 4: CalibratedClassifierCV 本格適用・LightGBM/CatBoost カテゴリ実データ検証
- Phase 5: GroupTimeSeriesSplit のバックテスト窓適用
- Phase 7: 品質レポートの Streamlit 表示
