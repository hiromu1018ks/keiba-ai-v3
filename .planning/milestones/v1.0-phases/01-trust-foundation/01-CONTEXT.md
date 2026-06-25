# Phase 1: Trust & Foundation - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

下流すべて（ラベル/特徴量/モデル/バックテスト）が信頼できる基盤の上で動くようにすること。具体的には：

1. **Raw 品質ゲート（DATA-01）** — EveryDB2 由来 PostgreSQL データに対する品質チェック（テーブル存在/件数/日付範囲/2015以降/NULL/主キー・自然キー重複/文字化け/コード値異常）を pass/fail verdict 付きで実行できること（§6.4）
2. **Normalized ETL（DATA-02）** — 型変換・コード変換・クラス正規化を行い、raw を直接加工せず別テーブルとして正規化データを生成。raw 行ハッシュ不変で raw read-only を証明（成功基準#2）
3. **クラス正規化（DATA-03 / Pitfall 7）** — 文字列ではなく `race_condition_code` 基準。`class_code_normalized`/`class_name_normalized`/`class_level_numeric`/`post_2019_class_system_flag` を生成（§12.3）
4. **リーク防止プリミティブ bootstrap（成功基準#4）** — `merge_asof` PIT joiner / `GroupTimeSeriesSplit` / frozen-category-map fitter / `CalibratedClassifierCV(cv='prefit')` を importable な実体＋smoke test として、feature/label コードより先に用意（研究 SUMMARY「Build leakage-prevention infrastructure FIRST」）

Build-Order DAG の step 1-2 + リーク防止スタック bootstrap。**DAG 境界＝検証ゲート**（raw 品質が通らない限り下流は動かさない）。モデル/特徴量/ラベル実装は明示的に後続フェーズ。

</domain>

<decisions>
## Implementation Decisions

### 品質ゲート（DATA-01）
- **D-01:** ハイブリッドゲート。**構造的欠陥**（2015-01-01以降データなし／主キー・自然キー重複／主要テーブル欠損）はブロッキング（pytest/CI fail）。**量的異常**（NULL率等）は参考レポート。Core Value（信頼性）を守りつつ EveryDB2 既知のデータ揺れでの過剰 FAIL を避ける
- **D-02:** 対象範囲＝主要5系統（レース/出走/成績/払戻/オッズ）＋マスタ周辺（馬/騎手/調教師/馬場等）。テーブル特定は `docs/everydb2/INDEX.md` の RecordSpec（`RA`/`SE`/`HR`/`H1`/`UM`/`KS`/`CH` 等）で行う
- **D-03:** 閾値は実測2段階。初回は全項目を数値レポート（fail 判定は構造的欠陥のみ）、実測を見て主要項目に現実的閾値を設定。EveryDB2 特性が未知でも着手可能
- **D-04:** 出力＝`reports/` の Markdown（人間用）＋ JSON（機械判定用、pass/fail verdict 含む）。Streamlit 表示は Phase 7

### raw/normalized 分離と不変性（DATA-02）
- **D-05:** PostgreSQL 別スキーマ5層（`raw_everydb2` / `normalized` / `label` / `prediction` / `backtest`）。§12.2 論理層に1:1。権限管理と層境界の明瞭化のため
- **D-06:** raw read-only は二重保護。読み取り専用ロール（raw スキーマ SELECT-only）＋ ETL 前後の raw 行ハッシュ不変を pytest でアサーション（成功基準#2）
- **D-07:** コード変換辞書（クラス正規化対応表等）は `src/config/`（YAML/dataclass）で Git 管理。テスト容易・バージョン追跡可能
- **D-08:** normalized ETL は psycopg3 ＋ Python で明示的実装（型/コード/クラス変換ロジックを可読・テスト可能に）。DuckDB は大量集計時のみ補助（§12.1）

### クラス正規化（DATA-03 / Pitfall 7）
- **D-09:** `race_condition_code` → クラス対応表は「要件 §12.3 骨格（005→1, 010→2, 016→3）＋ `docs/everydb2/` 個別テーブル仕様（`03-RACE.md` 等）＋ 実データ照合」で構築。研究者が plan-phase で実データの全コード値と JRA 制度（2019改革）を突合して網羅
- **D-10:** ⚠ `docs/everydb2/CODE.md` はスクレイピング不完全（各コード表1エントリのみ、2007競走条件コードも全値欠落）。JRA-VAN 公式コード表または個別テーブル仕様書で補完が必須
- **D-11:** `post_2019_class_system_flag` は明確基準日で `race_date` 分岐。境界日は JRA-VAN 通知(2018-12-05)を踏まえ研究者が正確日付を確定し、コード定数として保持
- **D-12:** `is_open_class`/`is_listed`/`is_grade_race` は別コード（gradeコード/重賞フラグ等）から導出。名称パターンマッチに頼らない（Pitfall 7 精神）。研究者が該当カラムを特定
- **D-13:** 未知コード（新設/廃止/特殊）は厳格エラー。ETL で警告/エラーを出し該当レースを「class normalization unresolved」として記録・隔離。silent fallback 禁止（品質ゲート D-01 と整合）

### リーク防止 bootstrap（成功基準#4）
- **D-14:** importable ＋ smoke test 完全実装。`merge_asof` PIT joiner / `GroupTimeSeriesSplit` / frozen-category-map fitter（training-window-only fit, `__UNSEEN__` フォールバック）/ `CalibratedClassifierCV(cv='prefit')` を importable 実体で実装し各々 smoke test 通過。Phase 3/4 の実データパイプラインで立即利用可能
- **D-15:** `feature_availability` registry は `src/config/` の YAML。§13.3 項目（feature_name/feature_group/available_from_timing/source_table/cutoff_rule/leakage_risk_level）。Phase 1 では枠＋項目定義、本格運用と allowlist test は Phase 3
- **D-16:** モジュール配置は `src/utils/` に集約（`pit_join.py`/`group_split.py`/`category_map.py`/`calibrator.py` 等）。§17.2 構造に従い、Phase 3/4 各層から import しやすく層構造を汚さない
- **D-17:** smoke test は単体動作 ＋ リーク防止要所の assert。具体的には：`merge_asof` の sortedness raise／`GroupTimeSeriesSplit` の race_id disjoint assert／frozen-map の `__UNSEEN__` フォールバック／prefit calibrator の時系列順序 assert（`max(train.race_date) < min(calib.race_date)`）

### Claude's Discretion
- **接続設定管理:** `.env` ＋ pydantic-settings。機密値（DB名・パスワード等）は planning 文書に書かない（anti-pattern #20）。現在の EveryDB2 配置（public/専用スキーマ）と `raw_everydb2` スキーマへのマッピングは、研究者が plan-phase で実際の DB 接続を確認して決定
- **uv プロジェクト初期化:** `uv init --package`、`requires-python = ">=3.12,<3.13"`、§17.1 スタック（LightGBM/CatBoost/scikit-learn/psycopg3/DuckDB/PyArrow/mlxtend 等）の依存追加
- **pytest/ruff 構成:** §17.3 テスト一覧準拠の標準構成、`tests/` ディレクトリ
- **品質レポート実行:** §6.4「初回確認」を基本。ハイブリッドゲートのブロック要素は pytest に組み込み CI でも実行可能

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §6.4 — 品質チェック要件（9項目の確認内容）。DATA-01 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §12.1-12.4 — DB/ETL方針、論理層5層、クラス正規化（対応表の骨格）、Parquet メタデータ。DATA-02/03 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §13.3-13.5 — feature_availability 定義（項目・timing 候補6種）、Phase 1-A 参照条件、利用可能特徴量。registry 形式の根拠
- `docs/keiba_ai_requirements_v1.3.md` §17.1-17.3 — 開発環境スタック、プロジェクト構成（`src/` レイアウト）、テストコード一覧
- `docs/keiba_ai_requirements_v1.3.md` §14.3-14.5 — LightGBM/CatBoost カテゴリ仕様・欠損理由。utils/ カテゴリ/欠損プリミティブの根拠（Phase 4 本格適用だが utils 設計に関与）

### EveryDB2 公式マニュアル（実データ依存の正・ユーザー提供）
- `docs/everydb2/INDEX.md` — 全59テーブル ＋ RecordSpec（`RA`/`SE`/`HR`/`H1`/`UM`/`KS`/`CH`…）。品質対象テーブル特定と normalized ETL 設計の主情報源
- `docs/everydb2/03-RACE.md` — レース（RA, 110フィールド）。`race_condition_code` 保持の想定、クラス正規化の主テーブル
- `docs/everydb2/04-UMA_RACE.md` — 出走馬（SE, 73フィールド）。成績・着順。Phase 1 品質対象、Phase 2 ラベル原料
- `docs/everydb2/01-TOKU_RACE.md` — 特別レース定義（TK, 36フィールド）
- `docs/everydb2/05-HARAI.md` — 払戻（HR, 199フィールド）。Phase 1 品質対象、Phase 2 突合で本格使用
- `docs/everydb2/27-UMA.md` / `28-KISYU.md` / `30-CHOKYO.md` — 馬/騎手/調教師マスタ（マスタ周辺品質対象）
- `docs/everydb2/CODE.md` — ⚠ スクレイピング不完全（D-10）。コード表参照のみ、補完必須

### プロジェクト研究
- `.planning/research/SUMMARY.md` — 全体統合要約、Build-Order DAG、Phase 1 位置づけ、リーク防止 bootstrap の論拠
- `.planning/research/ARCHITECTURE.md` — 層構造・PIT/snapshot アーキテクチャ、`src/` フォルダ構成
- `.planning/research/STACK.md` — スタックとリーク防止設定、What NOT to Use
- `.planning/research/PITFALLS.md` — Pitfall 7（クラス正規化2019改革）等、"Looks Done But Isn't" 受入チェックリスト
- `.planning/research/FEATURES.md` — 機能優先度マトリクス

### プロジェクト計画
- `.planning/ROADMAP.md` — Phase 1 成功基準#1-#4、8フェーズ strict DAG
- `.planning/REQUIREMENTS.md` — DATA-01/02/03（Phase 1 割当）、全25要件トレーサビリティ
- `.planning/PROJECT.md` — Core Value、Key Decisions、Out of Scope
- `CLAUDE.md` — 技術スタック詳細・リーク防止設定・Postgres↔Parquet↔DuckDB interop（プロジェクト指示として权威）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- なし。コードベースは空（Phase 1 が最初のフェーズ）。本フェーズが基盤（uv プロジェクト／`src/` パッケージ／PostgreSQL スキーマ／utils/ プリミティブ）を構築する

### Established Patterns
- **`src/` パッケージ構造（§17.2）:** `config/` `db/` `etl/` `labels/` `features/` `models/` `prediction/` `backtest/` `evaluation/` `utils/`。Phase 1 は `etl/` `utils/` `config/` `db/` を中心に作成
- **論理層5層（§12.2）→ PostgreSQL 別スキーマ1:1（D-05）:** `raw_everydb2`→`normalized`→`label`→`prediction`→`backtest`。各層は自分自身か下位にのみ書く
- **リーク防止パターン（CLAUDE.md + 研究 STACK.md）:** `merge_asof(direction='backward')` / `GroupTimeSeriesSplit` / `CalibratedClassifierCV(cv='prefit')` / frozen category map（`__MISSING__`/`__UNSEEN__` sentinel）が `utils/` プリミティブ仕様の直接根拠

### Integration Points
- **`utils/` プリミティブ** ← Phase 3 features（PIT joiner, category map）、Phase 4 models（calibrator, category map）、Phase 5 backtest（GroupTimeSeriesSplit）が import
- **`normalized` スキーマ** ← Phase 2 labels、Phase 3 features が読む
- **品質レポート** ← §6.4 の9項目を `reports/` へ Markdown+JSON 出力。ブロック要素は pytest に組み込み

</code_context>

<specifics>
## Specific Ideas

- **ユーザー提供 `docs/everydb2/` が実データ依存の疑問を解決する主要情報源。** INDEX.md の RecordSpec で品質対象テーブルと ETL 設計が確定する。ただし CODE.md は不完全（D-10）
- **クラス正規化の連続性:** `race_condition_code=005` が 2019年前（500万下）と後（1勝クラス）をまたぐが、`class_level_numeric` は制度をまたいで連続（1/2/3）。これが Pitfall 7 の核心 — 名称で正規化すると制度改革で破綻するが、コード基準なら連続性が保たれる（§12.3 + 研究 PITFALLS.md Pitfall 7 + JRA-VAN data-change notice 2018-12-05）
- **ハイブリッドゲートの境界（D-01）:** 「構造的欠陥」= データが存在しない/重複で一意性が崩れる/主要テーブルが欠けている（下流が動かない）。「量的異常」= NULL率等（下流は動くが品質要注意）。この区別が pass/fail の基準

</specifics>

<deferred>
## Deferred Ideas

- **Phase 2:** 払戻テーブル突合ロジック（`docs/everydb2/05-HARAI.md` 199フィールド精読）、`sales_start_entry_count` 復元（§10.3）、`label_validation_status` 分類。Phase 1 では HR テーブルは品質チェック対象のみ
- **Phase 3:** `feature_availability` registry の本格運用（Phase 1-A allowlist test 含む）、PIT feature builder の実データ適用、Parquet スナップショット（§12.4 メタデータブロック）、frozen category map の実データ fit
- **Phase 4:** `CalibratedClassifierCV(cv='prefit')` の本格適用、LightGBM/CatBoost カテゴリ・欠損処理の実データ検証。Phase 1 は `utils/calibrator.py` を importable+smoke のみ
- **Phase 5:** `GroupTimeSeriesSplit` のバックテスト窓適用（BT-1..BT-5）。Phase 1 は utils の smoke のみ
- **Phase 7:** 品質レポートの Streamlit 表示。Phase 1 は Markdown+JSON のみ

None — discussion stayed within phase scope

</deferred>

---

*Phase: 1-Trust & Foundation*
*Context gathered: 2026-06-16*
