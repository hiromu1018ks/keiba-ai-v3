# Phase 7: Presentation - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

モデルの判定結果（予測 `p_fukusho_hit`・EV・推奨ランク・backtest 結果・確率品質）を **read-only の Streamlit UI** と **再現可能な CSV export** で開発者自身が閲覧できるようにする。すべての再現性スタンプ（`odds_snapshot_policy` / `odds_snapshot_at` / `model_version` / `feature_snapshot_id` / `backtest_strategy_version`）を inline 表示する。Build-Order DAG step 8（presentation）。

具体的には:

1. **Streamlit 最小画面（UI-01 / §16.1）** — レース一覧・各馬 `p_fukusho_hit`・複勝オッズ下限/上限・`EV_lower`/`EV_upper`・推奨ランク・`odds_snapshot_policy`/`odds_snapshot_at`・`model_version`・`feature_snapshot_id`・`backtest_strategy_version` を表示。**ワイド候補・ワイド期待値・荒れ指数・コメント生成は Phase 1 では表示しない**（§16.1 明示）
2. **予測 CSV 出力（OUT-01 / §16.2）** — pin 済み20列（race_id/race_date/race_start_datetime/racecourse/race_number/horse_id/horse_name/post_position/horse_number/p_fukusho_hit/fukusho_odds_lower/fukusho_odds_upper/EV_lower/EV_upper/recommend_rank/odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/prediction_created_at）
3. **バックテスト CSV 出力（OUT-02 / §16.2）** — pin 済み14列（backtest_id/backtest_strategy_version/train_period/validation_period/odds_snapshot_policy/race_id/horse_id/selected_flag/stake/refund_flag/payout_amount/profit/fukusho_hit_validated/recommend_rank/EV_lower/EV_upper）
4. **segment calibration 動的可視化（Phase 6 D-10/D-11 の消費）** — `reports/06-segments/*.json` を消費し segment 切替の動的 calibration curve を Plotly 描画（§16.1 列挙外だが Core Value たる確率品質の吟味が主目的のため採用）

**境界＝検証ゲート。** Phase 7 は**表示と出力のみ**（read-only）。新規予測生成・モデル再学習・backtest 再実行は行わない（Phase 4/5/6 の stamped 成果物をそのまま消費・Phase 4 SC#4 bit-identical / Phase 5 §19.1 再現性を維持）。UI/CSV のリーク防止・read-only 保証の対抗的監査は Phase 8（Adversarial Audit）が後続。

### ⚠ 表示対象データの前提（Phase 4/5/6 成果・実在・§19.1 聖域）
- `prediction.fukusho_prediction`（lightgbm 22,213行 + catboost 22,213行・`is_primary=true` が主モデル=LightGBM・Phase 6 D-09）— schema 修飾 SELECT GRANT 済み（Phase 7 Streamlit 用・T-04-02）
- `backtest.fukusho_backtest`（実データ backtest 25件完走・5窓フル行列・ただし **odds 正確性は JODDS取得完了後の再検証 subject**・UI では honest 注記が必要）
- `reports/06-segments/`（segment calibration JSON + Plotly HTML・Phase 6 D-10/D-11 生成済み・UI 動的描画が消費）
- `reports/06-evaluation.{md,json}` / `reports/04-eval.{md,json}` / `reports/05-backtest.{md,json}`（統合評価・モデル比較・backtest 集計）

</domain>

<decisions>
## Implementation Decisions

### 画面構成・レイアウト（UI-01 / §16.1）
- **D-01: マスター・ディテール構成** — レース一覧を行選択すると、そのレースの各馬（`p_fukusho_hit`/EV/推奨ランク/スタンプ）を展開または別ページ遷移で表示。競馬は「日 → レース → 馬」の階層が自然でこれに適合。Streamlit の `st.dataframe` + expanders / query params / multipage のいずれかで実装（具体手段は Claude's Discretion）。ユーザー選択: マスター・ディテール。（単一テーブル / multipage は却下）
- **D-02: 主要フィルタ付きサイドバー** — サイドバーに 日付範囲・競馬場（`jyocd`）・推奨ランク（S/A/B/C/D）の主要フィルタを配置。デフォルトは最新日 or EV 高順。22,213行の予測を行単位で扱うため絞り込みは実質必須。ユーザー選択: 主要フィルタ付き。（フィルタ最小限 / Claude判断 は却下）

### データ読込元（read-only・§19.1）
- **D-03: ハイブリッド読込** — prediction/backtest の**行データ**（UI-01/OUT-01/02 の主）は live PostgreSQL から schema 修飾 SELECT（`is_primary=true` で主モデル絞り・GRANT 済み・`keiba_readonly` ロール）。evaluation/segment の**集計**（calibration curve 等）は `reports/06-*.json` を消費。各データソースの性質（行データ=DB・集計=stamped JSON）に適合。`@st.cache_data` でキャッシュ。ユーザー選択: ハイブリッド。（live DB 一本 / reports 一本 は却下）

### CSV 出力の起点（OUT-01/OUT-02 / §16.2）
- **D-04: UI download + CLI の両方** — Streamlit の `st.download_button`（フィルタ結果をその場で export）と `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py` CLI（再現性あるバッチ export）の両方を実装。列定義は**単一定数**（`PREDICTION_CSV_COLUMNS` / `BACKTEST_CSV_COLUMNS`・§16.2 pin 済み20/14列）で DRY 共有し UI と CLI で同一列を保証。既存 `scripts/run_*.py` 慣例（`run_backtest`/`run_evaluation` 等）に整合。ユーザー選択: 両方。（Streamlit のみ / CLI のみ は却下）

### segment calibration 可視化（Phase 6 D-10/D-11 の消費）
- **D-05: 動的 Plotly 描画** — `reports/06-segments/*.json` を消費し、UI 上で segment（year/month/競馬場/頭数/人気帯/オッズ帯）切替の動的 calibration curve を Plotly で描画（curve 重ね描き + scalar 表併記・06-CONTEXT D-11 踏襲）。§16.1/UI-01 列挙には含まれないが、本プロジェクトは**確率品質（Calibration）の吟味が主目的の個人分析ツール**（実馬券購入しない）であり、Phase 6 が JSON を「Phase 7 が消費して動的描画」前提で生成した（D-10）ため採用。ユーザー選択: 動的 Plotly 描画。（最小画面のみ / HTML リンクのみ / Claude判断 は却下）

### Claude's Discretion（研究者/計画者に委ねる）
- **`streamlit` 依存追加** — `pyproject.toml` に未追加（現在 `src/ui/` も未作成）。CLAUDE.md 推奨は Streamlit 1.58.0。`uv add streamlit` で追加。
- **ディレクトリ構成** — §17.2 は `streamlit_app/` を提案するが、実コードは `src/` レイアウト（`src/db`/`src/ev` 等）。`src/ui/`（実コード慣例に整合）vs `streamlit_app/`（§17.2 提案）を planner が判断。どちらも `src/` 配下の既存モジュールを import できることが前提。
- **read-only 保証** — UI は `keiba_readonly` ロール（GRANT 済み・schema 修飾 SELECT）のみ使用。書き込みなし。実馬券購入スコープ外（19.3）。接続設定は `src/config/` の既存 2ロール DSN を再利用。
- **キャッシュ戦略** — `@st.cache_data`（Parquet/DB read 用・CLAUDE.md 指示・`st.session_state` で派生データを持たない）。TTL・無効化戦略は planner が決定。
- **マスター・ディテールの Streamlit 実装手段** — D-01 の具体的実装（expanders / query params / multipage）・フィルタ widget の UI 詳細・デフォルトソート。
- **テスト構成（§17.3）** — UI は unit/contract テスト中心（CSV 列定数の presence assert・`PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` と§16.2 の 1:1 検証・`src/ev/report.py` REPORT_COLUMNS 検証パターン[LOW-05] 再利用）。Streamlit 描画の E2E は最小。read-only 保証の assert。
- **segment 動的描画の Plotly レイアウト** — curve 重ね描きの軸/凡例/色分け・scalar 表（ECE/MCE/calibration_max_dev）の併記形式・06-CONTEXT D-11/D-12 の6軸を踏襲。
- **backtest 表示の honest 注記** — D-03 の backtest 行データ表示時、odds 正確性が JODDS取得完了後の再検証 subject である旨を UI/CSV メタ欄に注記（Phase 5 manual-only 整合・honest 表示）。
- **レース一覧の補助情報** — 競馬場名・レース番号・馬名等の表示用ラベルの取得経路（`label.fukusho_label` / `normalized` 層 JOIN・06-CONTEXT segment 軸データ経路を参考）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §16.1 — Phase 1 画面表示項目（レース一覧/p_fukusho_hit/複勝オッズ下限上限/EV_lower/upper/推奨ランク/odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/backtest_strategy_version・**ワイド/荒れ指数/コメント生成は Phase 1 では表示しない**）。UI-01/D-01/D-02 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §16.2 — Phase 1 CSV 出力列（予測20列・backtest14列・pin 済み）。OUT-01/OUT-02/D-04 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §17.2 — プロジェクト構成（`streamlit_app/` ディレクトリ提案・`src/` 配下構成）。ディレクトリ判断の根拠
- `docs/keiba_ai_requirements_v1.3.md` §11.5 — 推奨ランク初期仕様（S/EV≥1.20, A/1.10, B/1.05, C/1.00, D/otherwise）。D-02 フィルタ軸の定義
- `docs/keiba_ai_requirements_v1.3.md` §11.6 — 回収率計算（backtest 表示値の意味）
- `docs/keiba_ai_requirements_v1.3.md` §19.1 — 再現性（スタンプ inline 表示必須・versioned artefact）。D-03/D-04 の根拠

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/06-evaluation-calibration-gates/06-CONTEXT.md` — **D-09（主モデルは `is_primary=true`・LightGBM）/ D-10（segment JSON + Plotly HTML を reports/06-segments/ に生成・Phase 7 が JSON を消費して動的描画）/ D-11（curve 並列 + scalar 表）/ D-12（6軸全生成）**。D-03/D-05 の直接の前提
- `.planning/phases/05-ev-backtest/05-CONTEXT.md` — **backtest.fukusho_backtest テーブル・reports/05-backtest.{md,json}・実データ backtest 25件完走（odds 正確性は JODDS取得後再検証 subject・manual-only）**。OUT-02/backtest 表示の入力
- `.planning/phases/04-model-prediction/04-CONTEXT.md` — **prediction テーブル（model_type/model_version/feature_snapshot_id/as_of_datetime）・SC#4 bit-identical（num_threads=1/seed=42/FIXED_REPRODUCE_TS）**。OUT-01/予測表示の入力。Phase 7 は stamped 成果物を消費し再生成しない

### コード契約（実装済み・Phase 7 が消費・scout 確認済み）
- `src/db/schema.py` — **`prediction.fukusho_prediction` DDL（L60・PK 11カラム + is_primary ALTER L110-116）・`backtest.fukusho_backtest` DDL（L145）・schema 修飾 SELECT GRANT（L250/255・Phase 7 Streamlit 用・T-04-02）**。テーブル構造・read-only アクセスの根拠
- `src/model/predict.py` — **`PREDICTION_COLUMNS`（L63）・`MODEL_TYPE_TO_SHORT`（L89・lightgbm→lgb/catboost→cb）**。prediction 行の列順・主モデル絞りの参考
- `src/db/prediction_load.py` — `load_predictions`（model_version-scoped staging-swap・`is_primary` bool 列）。prediction SELECT の参考
- `src/db/backtest_load.py` — **`BACKTEST_COLUMNS`（L77）**。backtest 行の列順・OUT-02 CSV の参考
- `src/ev/report.py` — **`REPORT_COLUMNS`（L41）・md+json 分離・手動 Markdown 表生成**。CSV 出力の DRY 列定数パターン・presence assert 検証（LOW-05）の再利用元
- `scripts/run_backtest.py` / `scripts/run_evaluation.py` / `scripts/run_train_predict.py` — 既存 CLI 慣例（argparse・reports/ 出力）。D-04 の `run_export_*.py` の参考
- `reports/06-segments/`（JSON + Plotly HTML）・`reports/06-evaluation.{md,json}` — D-05 動的描画の入力データ・segment 6軸
- `reports/04-eval.{md,json}` / `reports/05-backtest.{md,json}` — 統合評価・モデル比較の参考データ

### プロジェクト計画・状態
- `.planning/ROADMAP.md` — Phase 7 成功基準 #1-3（UI-01/OUT-01/OUT-02・§16 inline スタンプ表示）・8フェーズ strict DAG・Phase 8 が後続
- `.planning/REQUIREMENTS.md` — UI-01/OUT-01/OUT-02（Phase 7 割当・Pending）・全25要件トレーサビリティ
- `.planning/STATE.md` — Phase 7 移行状態・Phase 5 実データ backtest 完走（JODDS再検証 subject）・Decisions 履歴
- `CLAUDE.md` — **Streamlit 1.58.0 推奨・`st.cache_data`（Parquet/DB read 用・`session_state` で派生データを持たない）・Plotly 推奨・read-only・プロジェクト指示として权威・§16/§17.2 参照**

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/ev/report.py`（REPORT_COLUMNS・md/json 分離・presence assert[LOW-05]）** — CSV 出力の DRY 列定数 + 検証パターンの直接の再利用元。D-04 の `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` も同思想
- **`src/model/predict.py`（PREDICTION_COLUMNS）・`src/db/backtest_load.py`（BACKTEST_COLUMNS）** — DB 行の列順。UI 表示・CSV の元データ構造
- **`src/db/schema.py`（GRANT 済み schema 修飾 SELECT）** — Streamlit が `prediction.fukusho_prediction` / `backtest.fukusho_backtest` を `keiba_readonly` ロールで直接 SELECT 可能（T-04-02）
- **`reports/06-segments/*.json`（Phase 6 生成済み）** — segment calibration の機械可読データ（curve の bin/mean_pred/frac_pos/count・scalar 指標）。D-05 動的描画がそのまま消費
- **`src/config/`（2ロール DSN・pydantic-settings）** — readonly ロール接続設定の再利用

### Established Patterns
- **`scripts/run_*.py` CLI 慣例** — argparse・reports/ 出力・`KEIBA_SKIP_DB_TESTS` ゲート。D-04 の `run_export_*.py` が踏襲
- **md + json 分離出力（review LOW）** — Markdown（人間確認）と JSON（byte-reproducible・機械消費）の分離。reports/ 慣例
- **5層スキーマ分離（Phase 3 D-08 + Phase 4 D-05）** — feature=不変 Parquet・prediction/backtest=queryable Postgres（結果層）。Phase 7 は prediction/backtest を queryable に SELECT
- **CSV 列 pin（§16.2）** — 表示/出力列は要件で固定。列定数を単一ソース（定数）にして UI/CLI/test で DRY 共有
- **readonly ロール GRANT（Phase 1 D-01）** — `keiba_readonly` は明示的 reader のみ（TO PUBLIC 不使用）。UI は read-only 保証

### Integration Points
- **READ（readonly ロール・schema 修飾 SELECT）:**
  - `prediction.fukusho_prediction`（`is_primary=true` で主モデル=LightGBM 絞り・`model_type`/`model_version`/`p_fukusho_hit`/`feature_snapshot_id`/`as_of_datetime`/`odds_snapshot_*`/`race_key`/`entry_count`）
  - `backtest.fukusho_backtest`（実データ backtest 25件・`backtest_id`/`backtest_strategy_version`/`selected_flag`/`stake`/`payout_amount`/`profit`/`fukusho_hit_validated`）
  - `label.fukusho_label` / `normalized` 層（競馬場名・レース番号・馬名・枠番/馬番等の表示ラベル）
  - `reports/06-segments/*.json`・`reports/06-evaluation.json`（calibration 動的描画・統合評価）
- **OUT（新規・read-only・書き込み DB なし）:**
  - Streamlit UI（`src/ui/` または `streamlit_app/`・新規）
  - `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py`（新規 CLI・§16.2 pin 列）
  - CSV ファイル（download / バッチ出力先）
- **CONSUMED BY（下流フェーズ）:**
  - Phase 8（Adversarial Audit）: UI/CSV のリーク防止テスト・再現性スタンプ inline 検証・read-only 保証の対抗的監査（TEST-01）・固定 seed 再現性

</code_context>

<specifics>
## Specific Ideas

- **競馬データの「日→レース→馬」階層** — レース一覧を起点に馬別へ展開するマスター・ディテール（D-01）が競馬データに自然。22,213行の予測を行単位で扱うには階層化が有効
- **個人分析ツールとしての主目的** — 実馬券購入を行わず、確率品質（Calibration）の吟味・過小評価馬の検出が主目的。これが D-05（segment calibration 動的描画）を §16.1 列挙外でも採用する根拠。Phase 6 D-10 が JSON を Phase 7 消費前提で生成した経緯とも整合
- **§16.1 明示的除外項目** — ワイド候補・ワイド期待値・荒れ指数・コメント生成は Phase 1 では表示しない（Phase 2 以降・REQUIREMENTS PHASE2-05 Streamlit 表示拡張）。UI にこれらを混入しない
- **backtest の honest 注記** — 実データ backtest は25件完走しているが、odds 正確性は JODDS取得完了後の再検証 subject（Phase 5 manual-only 分離）。UI/CSV で現状の stamped 結果を表示しつつ、再検証余地を honest に注記（回収率の過大表示回避・Core Value 整合）
- **再現性スタンプは聖域** — `odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version` は UI の各行・CSV の各ファイルに inline 表示（§19.1）。stamped 成果物を消費し再生成しない（Phase 4 SC#4 bit-identical 維持）

</specifics>

<deferred>
## Deferred Ideas

- **Phase 8（Adversarial Audit）:** UI/CSV のリーク防止テスト・再現性スタンプの inline 検証（スタンプ欠落検出）・read-only 保証（書き込み経路不存在）の対抗的監査・固定 seed での UI/CSV 再現性（TEST-01）
- **PHASE2-05（将来・Streamlit 表示拡張）:** ワイド候補・ワイド期待値・荒れ指数・コメント生成の UI 追加・高度化（§16.1 除外項目・REQUIREMENTS v2）
- **ワイド/三連複モデル対応 UI（PHASE2/PHASE3）:** UI の multipage 化・モデル自動更新表示（REQUIREMENTS PHASE3-04）
- **MLflow/Optuna 連携 UI（OPS-01/02）:** モデル管理・ハイパラ最適化の可視化（Phase 1 安定後・§21 defer）

### Reviewed Todos (not folded)
- **`.planning/todos/phase3-advisory-hardening.md`** — 「Phase 03 advisory 4件 hardening — Phase 3.1 に統合」。Phase 3.1 で既に解決済み・Phase 7（Presentation）とは無関係（match score 0.6 は keyword "phase" のみの偶発一致）。Phase 7 スコープには畳み込まず。

</deferred>

---

*Phase: 7-Presentation*
*Context gathered: 2026-06-24*
