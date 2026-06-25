# Phase 7: Presentation - Research

**Researched:** 2026-06-24
**Domain:** Streamlit 1.58.0 ローカル read-only UI + 再現可能 CSV export + Plotly 動的 calibration 可視化
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: マスター・ディテール構成** — レース一覧を行選択すると、そのレースの各馬を展開表示。単一テーブル / multipage は却下。
- **D-02: 主要フィルタ付きサイドバー** — 日付範囲・競馬場(`jyocd`)・推奨ランク(S/A/B/C/D)の主要フィルタを配置。フィルタ最小限 / Claude判断 は却下。
- **D-03: ハイブリッド読込** — prediction/backtest 行データは live PostgreSQL から schema 修飾 SELECT(`is_primary=true` で主モデル絞り・`keiba_readonly` ロール・GRANT 済み)。evaluation/segment 集計は `reports/06-*.json` を消費。`@st.cache_data` でキャッシュ。live DB 一本 / reports 一本 は却下。
- **D-04: UI download + CLI の両方** — Streamlit `st.download_button` + `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py` CLI の両方。列定義は単一定数(`PREDICTION_CSV_COLUMNS` / `BACKTEST_CSV_COLUMNS`)で DRY 共有。Streamlit のみ / CLI のみ は却下。
- **D-05: 動的 Plotly 描画** — `reports/06-segments/*.json` を消費し segment 切替の動的 calibration curve を Plotly で描画(curve 重ね描き + scalar 表併記)。最小画面のみ / HTML リンクのみ / Claude判断 は却下。

### Claude's Discretion

- `streamlit` 依存追加(`pyproject.toml` に未追加・CLAUDE.md 推奨 1.58.0・`uv add streamlit`)
- ディレクトリ構成: `src/ui/`(実コード慣例) vs `streamlit_app/`(§17.2 提案) — planner 判断
- read-only 保証: `keiba_readonly` ロール(GRANT 済み・schema 修飾 SELECT)のみ使用・書き込み経路不存在
- キャッシュ戦略: `@st.cache_data`(Parquet/DB read 用・CLAUDE.md 指示・`st.session_state` で派生データを持たない)。TTL・無効化戦略
- マスター・ディテールの Streamlit 実装手段(expanders / query params / multipage・UI-SPEC は `st.tabs(3)` + `selection_mode="single-row"` に確定済み)
- テスト構成(§17.3): CSV 列定数 presence assert(`src/ev/report.py::REPORT_COLUMNS` LOW-05 パターン再利用)・read-only assert・スタンプ inline presence・Plotly 描画契約の contract test
- segment 動的描画の Plotly レイアウト(curve 重ね描きの軸/凡例/色分け・scalar 表併記形式)
- backtest 表示の honest 注記(odds 正確性は JODDS取得完了後の再検証 subject)
- レース一覧の補助情報(競馬場名・レース番号・馬名等の表示用ラベル取得経路)

### Deferred Ideas (OUT OF SCOPE)

- **Phase 8（Adversarial Audit）:** UI/CSV のリーク防止テスト・再現性スタンプ inline 検証・read-only 保証(書き込み経路不存在)の対抗的監査・固定 seed での UI/CSV 再現性(TEST-01)
- **PHASE2-05（将来・Streamlit 表示拡張）:** ワイド候補・ワイド期待値・荒れ指数・コメント生成の UI 追加(§16.1 除外項目)
- **ワイド/三連複モデル対応 UI（PHASE2/PHASE3）:** UI の multipage 化・モデル自動更新表示
- **MLflow/Optuna 連携 UI（OPS-01/02）:** Phase 1 安定後・§21 defer
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | Streamlit 画面でレース一覧・各馬 `p_fukusho_hit`・複勝オッズ下限/上限・`EV_lower`/`EV_upper`・推奨ランク・`odds_snapshot_policy`/`odds_snapshot_at`・`model_version`・`feature_snapshot_id`・`backtest_strategy_version` を表示(ワイド/荒れ指数/コメント生成は表示しない) | §Standard Stack(Streamlit 1.58.0)・§Architecture Patterns(D-01..D-05 具体化・`st.tabs(3)` + `selection_mode="single-row"` + `st.sidebar`)・§Code Examples(`st.dataframe` 行選択・`st.column_config.NumberColumn`)・§Data Provenance(`prediction.fukusho_prediction` SELECT + `normalized.n_uma_race` JOIN で表示ラベル) |
| OUT-01 | 予測CSV(race_id/race_date/race_start_datetime/競馬場/レース番号/horse_id/horse_name/枠番/馬番/p_fukusho_hit/オッズ下限上限/EV/推奨ランク/スナップショット情報)を出力 | §CSV Export Contract(`PREDICTION_CSV_COLUMNS` 20列・要件§16.2 原典と照合済)・§Don't Hand-Roll(`src/ev/report.py::REPORT_COLUMNS` LOW-05 presence assert パターン再利用)・§Code Examples(UTF-8 BOM + CRLF 実装) |
| OUT-02 | バックテストCSV(backtest_id/戦略バージョン/学習検証期間/odds_snapshot_policy/race_id/horse_id/selected_flag/stake/refund_flag/payout_amount/profit/fukusho_hit_validated/推奨ランク/EV)を出力 | §CSV Export Contract(`BACKTEST_CSV_COLUMNS` 16列・要件§16.2 原典「14列」表記と実体16項目の齟齬解消済)・§Data Provenance(`backtest.fukusho_backtest` SELECT) |
</phase_requirements>

## Summary

Phase 7 は Phase 4/5/6 の stamped 成果物を **read-only** で消費し、開発者自身が予測/EV/backtest/calibration を吟味できる Streamlit UI と再現可能 CSV export を構築するフェーズ。設計契約(D-01..D-05)と視覚契約(07-UI-SPEC.md・Sign-Off 6/6)は既に承認済みのため、研究は「契約の実装曖昧さを実データ/API/コードで解消する」ことに集中した。

主要な発見は 5 点。(1) Streamlit 1.58.0 の行選択 API は `selection=` でなく `selection_mode="single-row"` + `on_select="ignore"|"rerun"` であり、戻り値は `selection["rows"][0]`(行インデックス・リスト) — UI-SPEC の `selection="single-row"` 記述は古い API 形状で planner/executor は正しい引数名に修正する必要がある。(2) `@st.cache_data` に psycopg `ConnectionPool` を渡すと `UnhashableParamError` になるため `hash_funcs={ConnectionPool: id}` が必須 — DSN 文字列を渡す方がより安全。(3) OUT-02 backtest CSV の列数は要件§16.2 原典(行1118-1134)を数えると **16項目** であり「14列」表記は誤り — planner は 16 列で `BACKTEST_CSV_COLUMNS` を定義すること。(4) `reports/06-segments/*.json` のスキーマは全6軸で統一構造(`axis_name` + `segments[]`・各 segment は `curve`(count/frac_pos/mean_pred) + `scalar`(ece_quantile/ece_uniform/max_dev_guarded/mce_guarded/n_samples) + `segment_value`)。(5) jyocd→競馬場名マッピングは `src/config/code_tables.yaml` に既存・馬名/枠番/馬番は `normalized.n_uma_race`(bamei/wakuban/umaban/kettonum)から取得可能。

read-only 保証は既存 `keiba_readonly` ロール(GRANT 済み・`schema.py` GRANT_READER_SQL・Phase 7 Streamlit 用 T-04-02)と `src/db/connection.py::make_pool(role='readonly')` の再利用で構造的に担保される。書き込み/DDL を発行するコードパスを UI 配下に存在させないことが Phase 8 対抗的監査(TEST-01)の前提。

**Primary recommendation:** `src/ui/` ディレクトリに Streamlit アプリ本体 + `csv_columns.py`(DRY 列定数)を配置し、`scripts/run_export_*.py` は既存 `scripts/run_*.py` 慣例(argparse・`reports/` 出力・`KEIBA_SKIP_DB_TESTS` ゲート)に踏襲。`@st.cache_data(hash_funcs={ConnectionPool: id})` で DB 読込をキャッシュし、派生データは `st.session_state` に持たない(CLAUDE.md 指示)。

## Project Constraints (from CLAUDE.md)

- **応答言語は日本語必須（最優先指示）** — UI 文言・コメント・コミットメッセージ全て日本語。技術識別子・カラム名・スタンプキー(snake_case)・Streamlit/Plotly API 名は原文。
- **Tech stack 固定(§17.1)** — Python 3.12(uv 管理) / Streamlit 1.58.0(CLAUDE.md 推奨) / Plotly 6.8.0(pyproject 既依存・`>=6.8.0`) / PostgreSQL(`keiba_readonly` ロール・read-only 保証)。
- **`@st.cache_data` 指示** — Parquet/DB read 用に使用。`st.session_state` で派生データを持たない。
- **Core value 聖域** — 再現性スタンプ(`odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version`)は inline 表示必須(§19.1)。リーク防止・read-only 保証。
- **§16.1 明示的除外** — ワイド候補・ワイド期待値・荒れ指数・コメント生成は UI/CSV に混入しない(Phase 2 以降)。
- **実馬券購入スコープ外(§19.3)** — 推奨ランクは参考情報・購入判断を強制しない。回収率/EV には「暫定」「参考」修飾。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 予測/backtest 行データ読込 | API / Backend（PostgreSQL readonly SELECT） | — | `prediction.fukusho_prediction` / `backtest.fukusho_backtest` は queryable Postgres（Phase 3 D-08）。UI は `keiba_readonly` ロールで schema 修飾 SELECT のみ（D-03）。書き込み経路なし。 |
| 表示ラベル取得（競馬場名/馬名/枠番/馬番） | API / Backend（PostgreSQL readonly SELECT） | CDN/Static（code_tables.yaml の jyocd→競馬場名） | 馬名等は `normalized.n_uma_race` から SELECT。jyocd→競馬場名は `src/config/code_tables.yaml` の固定マッピング（ファイル読込・DB 不要）。UI 側でマッピングを持たない（DRY）。 |
| calibration 集計データ読込 | CDN/Static（`reports/06-segments/*.json` ファイル読込） | — | Phase 6 D-10 が stamped JSON を生成済み。UI は `@st.cache_data` でファイル読込。再集計しない（stamped 成果物消費・§19.1）。 |
| 行選択インタラクション（マスター→ディテール） | Browser/Client（Streamlit ウィジェット状態） | Frontend Server（Streamlit rerun） | `selection_mode="single-row"` + `on_select="rerun"` で行インデックスを取得し下部描画を切り替え。状態は Streamlit rerun メカニズム（`st.session_state` で派生データを持たない・選択インデックスのみ）。 |
| CSV ファイル生成 | API / Backend（pandas DataFrame → CSV bytes） | — | UI(`st.download_button` の `data=`)と CLI(`Path.write_text`)の両方が `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` 適用済み DataFrame から CSV bytes を生成。UTF-8 BOM + CRLF。 |
| Plotly Figure 構築 | Browser/Client（Plotly.js レンダリング） | Frontend Server（`st.plotly_chart` 埋込） | `reports/06-segments/<axis>.json` → pandas/Plotly で `go.Figure` 構築 → `st.plotly_chart(use_container_width=True)`。静的 HTML リンクは併設しない（D-05「HTML リンクのみ」却下済）。 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Streamlit** | 1.58.0 | ローカル read-only UI（§16.1・CLAUDE.md 推奨） | `[CITED: docs.streamlit.io/develop/api-reference/data/st.dataframe]` §17.1 技術スタック固定。`selection_mode`/`on_select`/`st.column_config`/`st.cache_data(hash_funcs=)`/`st.download_button` は 1.35+ で安定。Python ≥3.10（3.12 完全対応）。`pyproject.toml` に **未追加**（`uv add streamlit==1.58.0` で追加・D-04 CLI 慣例整合）。 |
| **Plotly** | 6.8.0（`>=6.8.0`・pyproject 既依存） | 動的 calibration curve 描画（D-05・`reports/06-segments/*.json` 消費） | `[CITED: plotly.com/python/]` Phase 6 D-10 が `reports/06-segments/*.html`（`include_plotlyjs='directory'`・`plotly.min.js` 共有）を生成済み。UI 動的描画は同一パッケージの `plotly.graph_objects.Figure` を `st.plotly_chart` で埋込。依存追加不要。 |
| **pandas** | 3.0.3（既依存） | DataFrame 操作・CSV 生成・`reports/*.json` 読込 | `[CITED: pandas.pydata.org/docs/reference/api/pandas.merge_asof.html]` プロジェクト lingua franca。`df.to_csv(index=False)` で CSV bytes 生成（BOM/CRLF は `encoding='utf-8-sig'`/`lineterminator='\r\n'`）。 |
| **psycopg** (`psycopg[binary]`) | 3.3.4（既依存） | PostgreSQL readonly 接続（`keiba_readonly` ロール） | `[CITED: psycopg.org/psycopg3/docs/]` `src/db/connection.py::make_pool(role='readonly')` を再利用。`psycopg_pool.ConnectionPool` は Streamlit でプール再利用。 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **PyYAML** | `pyyaml`（既依存） | `src/config/code_tables.yaml` から jyocd→競馬場名マッピング読込 | 競馬場名表示（`st.multiselect` の `format_func` 用）。DB JOIN 不要・固定マッピング。 |
| **pydantic-settings** | 2.14.1（既依存） | `src/config/settings.py::Settings` から readonly DSN 取得 | `Settings().dsn`（`keiba_readonly` ロール）を `make_pool` に渡す。既存パターン再利用・DSN ハードコード禁止。 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `src/ui/`（実コード慣例） | `streamlit_app/`（§17.2 提案） | `src/ui/` は `src/db`/`src/ev`/`src/config` と同一パッケージ階層で import が単純（`from src.db.connection import make_pool`）。`streamlit_app/` は §17.2 提案だが `sys.path` 操作かパッケージ化が必要。**推奨: `src/ui/`**（実コード慣例優先・hatch wheel packages に `src/ui` 追加で解決）。 |
| `st.dataframe(selection_mode=)` 行選択 | `st.data_editor` + checkbox 列 / `st.button` 行クリック | `selection_mode` が Streamlit 1.35+ ネイティブ機能で最も簡潔。`st.data_editor` は編集可能 UI になり read-only 契約（D-03）と衝突。**`selection_mode="single-row"` 採用**。 |
| `@st.cache_data(hash_funcs={ConnectionPool: id})` | DSN 文字列を渡して関数内で pool 構築 | DSN 文字列は hashable で `hash_funcs` 不要だが pool が毎回再構築される可能性。`hash_funcs={ConnectionPool: id}` は pool 同一性でキャッシュ判定。**両方有効・planner が選択**（DSN 渡しの方が Streamlit キャッシュ意味論的に素直）。 |

**Installation:**
```bash
# streamlit のみ新規追加（plotly/pandas/psycopg/pyyaml/pydantic-settings は既依存）
uv add streamlit==1.58.0
```

**Version verification:**
```bash
uv pip show streamlit | head -2   # Name: streamlit / Version: 1.58.0
uv pip show plotly | head -2      # Name: plotly / Version: 6.8.0（既依存・確認のみ）
```

## Package Legitimacy Audit

> Phase 7 は `streamlit` 1件のみ新規追加。plotly/pandas/psycopg/pyyaml/pydantic-settings は既依存（再インストール不要）。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| streamlit | PyPI | ~6 yrs（v1.0 は 2021-11） | 数百万/wk（Streamlit 公式） | github.com/streamlit/streamlit | OK | Approved |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious [SUS]:** none

*streamlit は WebSearch/训练数据 経由で発見したが、CLAUDE.md（プロジェクト指示・§17.1 で「Streamlit」と明記）および docs.streamlit.io 公式ドキュメント で権威付けされているため `[CITED]` 扱い。PyPI での正当性は download ボリューム・streamlit/streamlit 公式 repo で十分確立。*

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ユーザー（開発者自身・ローカル単一）                                       │
│  ブラウザ → http://localhost:8501                                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTP（Streamlit 既定）
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Streamlit Server（streamlit run src/ui/app.py・単一プロセス）             │
│                                                                          │
│  ┌─ st.sidebar（D-02 主要フィルタ）────────────────────────────────────┐ │
│  │  st.date_input(range) → date_range                                  │ │
│  │  st.multiselect(jyocd・format_func=競馬場名) → selected_jyocd       │ │
│  │  st.multiselect(S/A/B/C/D・default=S,A,B) → selected_ranks          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─ st.tabs(["予測一覧", "Backtest", "Segment Calibration"])────────────┐ │
│  │                                                                      │ │
│  │  [予測一覧タブ]                                                       │ │
│  │   event = st.dataframe(race_list_df,                                 │ │
│  │                        selection_mode="single-row",                  │ │
│  │                        on_select="rerun")                            │ │
│  │      ↓ selection["rows"][0] = row_index                              │ │
│  │   selected_race = race_list_df.iloc[row_index]                       │ │
│  │   st.dataframe(horse_detail_df + st.column_config.NumberColumn)      │ │
│  │   st.columns(5) + st.caption（5スタンプ inline・§19.1）                │ │
│  │   st.download_button("予測CSVをダウンロード", data=csv_bytes)         │ │
│  │                                                                      │ │
│  │  [Backtestタブ]                                                       │ │
│  │   st.dataframe(backtest_list_df)                                     │ │
│  │   st.warning（honest 注記: odds 再検証 subject）                       │ │
│  │   st.download_button("Backtest CSVをダウンロード", data=csv_bytes)    │ │
│  │                                                                      │ │
│  │  [Segment Calibrationタブ]                                           │ │
│  │   axis = st.selectbox（6軸: year/month/jyocd/entry_count/ninki/odds_band） │ │
│  │   seg_data = load_segment_json(axis)  ← reports/06-segments/<axis>.json │ │
│  │   fig = build_calibration_figure(seg_data)  ← Plotly go.Figure       │ │
│  │   st.plotly_chart(fig, use_container_width=True)                     │ │
│  │   st.dataframe(scalar_metrics_df)  ← ECE/MCE/max_dev                 │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──┬───────────────────────────────┬───────────────────────────────────────┘
   │ @st.cache_data                 │ @st.cache_data
   │ (hash_funcs={ConnectionPool:id})│ (ファイル読込)
   ▼                                ▼
┌──────────────────────────────┐  ┌──────────────────────────────────────┐
│  PostgreSQL（keiba_readonly）  │  │  reports/06-segments/*.json           │
│  ・prediction.fukusho_prediction│  │  （Phase 6 D-10 生成済・stamped）      │
│  　WHERE is_primary=true       │  │  axis_name + segments[]               │
│  ・backtest.fukusho_backtest   │  │  ・curve(count/frac_pos/mean_pred)    │
│  ・normalized.n_uma_race       │  │   ・scalar(ece/mce/max_dev/n_samples) │
│  　（bamei/wakuban/umaban JOIN）│  │   ・segment_value                     │
│  ※ schema 修飾 SELECT GRANT 済  │  └──────────────────────────────────────┘
└──────────────────────────────┘
        ▲
        │ 別経路（CLI・D-04）
┌───────┴────────────────────────────────────────────────────────────────┐
│  scripts/run_export_predictions_csv.py / run_export_backtest_csv.py     │
│  　argparse + Settings().dsn（readonly）+ PREDICTION_CSV_COLUMNS 適用    │
│  　→ reports/07-*.csv or stdout（既存 run_*.py 慣例踏襲）                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/
├── ui/                          # 新規・Phase 7 Streamlit アプリ（推奨配置）
│   ├── __init__.py
│   ├── app.py                   # エントリポイント（streamlit run src/ui/app.py）
│   ├── csv_columns.py           # PREDICTION_CSV_COLUMNS / BACKTEST_CSV_COLUMNS（DRY 単一定数・D-04）
│   ├── loaders.py               # @st.cache_data 付き DB/JSON 読込関数
│   ├── prediction_tab.py        # 予測一覧タブ（マスター・ディテール・D-01）
│   ├── backtest_tab.py          # Backtest タブ（honest 注記・OUT-02 表示元）
│   ├── calibration_tab.py       # Segment Calibration タブ（D-05 動的 Plotly）
│   └── jyocd_map.py             # code_tables.yaml から jyocd→競馬場名読込（簡易 helper）
├── db/
│   ├── connection.py            # 既存・make_pool(role='readonly') 再利用
│   └── schema.py                # 既存・GRANT_READER_SQL（prediction/backtest SELECT 済）
├── ev/
│   └── report.py                # 既存・REPORT_COLUMNS LOW-05 パターン（CSV 列定数の参考）
└── config/
    ├── settings.py              # 既存・Settings().dsn（keiba_readonly）
    └── code_tables.yaml         # 既存・jyocd→競馬場名マッピング

scripts/
├── run_export_predictions_csv.py   # 新規・D-04 CLI（argparse・PREDICTION_CSV_COLUMNS 適用）
└── run_export_backtest_csv.py      # 新規・D-04 CLI（argparse・BACKTEST_CSV_COLUMNS 適用）

tests/
└── ui/                          # 新規・Phase 7 unit/contract test
    ├── __init__.py
    ├── test_csv_columns.py      # PREDICTION_CSV_COLUMNS/BACKTEST_CSV_COLUMNS presence assert（§16.2 1:1・LOW-05 再利用）
    ├── test_readonly_guarantee.py # read-only 保証の構造的検証（書き込み/DDL 経路不存在）
    └── test_segment_schema.py   # reports/06-segments/*.json スキーマ契約（property test）
```

### Pattern 1: 行選択マスター・ディテール（D-01 具体化・selection_mode 正引数）

**What:** `st.dataframe(selection_mode="single-row", on_select="rerun")` の戻り値から選択行インデックスを取得し、下部にディテール展開。
**When to use:** マスター・ディテール構成全般（D-01）。
**Example:**
```python
# Source: [CITED: docs.streamlit.io/develop/api-reference/data/st.dataframe] + [CITED: docs.streamlit.io/develop/tutorials/elements/dataframe-row-selections]
# ⚠ UI-SPEC.md の `selection="single-row"` は古い API 形状。正しくは selection_mode + on_select。
import streamlit as st
import pandas as pd

race_list_df: pd.DataFrame = ...  # @st.cache_data で読込済

event = st.dataframe(
    race_list_df,
    selection_mode="single-row",   # "single-row" | "single-row-required" | "multi-row" | list
    on_select="rerun",             # "ignore"（既定・rerun しない） | "rerun"（選択で再実行）
    hide_index=False,
)

selection = event.selection        # SelectionState オブジェクト（dict 的）
rows = selection.get("rows", [])   # list[int]・行インデックス（0-based・DataFrame の row position）

if rows:
    selected_idx = rows[0]         # single-row でも list で返る・[0] で取り出し
    selected_race = race_list_df.iloc[selected_idx]
    # ディテール展開: 選択レースの各馬を SELECT して st.dataframe
    horse_df = load_horses_for_race(selected_race["race_key"])
    st.dataframe(horse_df, column_config=...)
else:
    st.info("レースを 1 行選択すると各馬の詳細が表示されます。")
```

### Pattern 2: @st.cache_data で psycopg ConnectionPool を扱う

**What:** `hash_funcs={ConnectionPool: id}` で pool の同一性（`id()`）をキャッシュキーにする。
**When to use:** DB pool をキャッシュ関数に渡す全場面（D-03・CLAUDE.md 指示）。
**Example:**
```python
# Source: [CITED: discuss.streamlit.io/t/unhashabletype-cannot-hash-object-of-type-thread-local/1917] + [CITED: docs.streamlit.io/develop/concepts/architecture/caching]
# UnhashableParamError を避けるため hash_funcs で ConnectionPool のハッシュ方法を明示。
from psycopg_pool import ConnectionPool
import streamlit as st

@st.cache_data(hash_funcs={ConnectionPool: id})
def load_predictions(pool: ConnectionPool, *, date_from, date_to, jyocd_list, rank_list):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT model_version, feature_snapshot_id, odds_snapshot_policy,
                   year, jyocd, racenum, umaban, kettonum, p_fukusho_hit, race_date
              FROM prediction.fukusho_prediction
             WHERE is_primary = true
               AND race_date BETWEEN %s AND %s
            """,
            (date_from, date_to),
        )
        rows = cur.fetchall()
    return rows  # hashable な戻り値（tuple list）でキャッシュ

# 代替案（より Streamlit 慣用的）: DSN 文字列を渡す（hashable・hash_funcs 不要）
@st.cache_data
def load_predictions_v2(dsn: str, *, date_from, date_to):
    # dsn は str なのでそのままキャッシュキーに。pool は関数内で構築。
    ...
```

### Pattern 3: CSV 列定数 DRY + presence assert（LOW-05 再利用）

**What:** 列定義を単一定数(`PREDICTION_CSV_COLUMNS`)に集約し、UI/CLI/test が同一参照。
**When to use:** CSV 出力全般（D-04・OUT-01/OUT-02）。
**Example:**
```python
# src/ui/csv_columns.py
PREDICTION_CSV_COLUMNS: tuple[str, ...] = (
    "race_id", "race_date", "race_start_datetime", "競馬場", "レース番号",
    "horse_id", "horse_name", "枠番", "馬番", "p_fukusho_hit",
    "fukusho_odds_lower", "fukusho_odds_upper", "EV_lower", "EV_upper",
    "recommend_rank",
    "odds_snapshot_policy", "odds_snapshot_at",
    "model_version", "feature_snapshot_id", "prediction_created_at",
)  # 20 列（要件§16.2 原典 行1092-1112 と照合済）

BACKTEST_CSV_COLUMNS: tuple[str, ...] = (
    "backtest_id", "backtest_strategy_version",
    "train_period", "validation_period", "odds_snapshot_policy",
    "race_id", "horse_id",
    "selected_flag", "stake", "refund_flag", "payout_amount", "profit",
    "fukusho_hit_validated", "recommend_rank", "EV_lower", "EV_upper",
)  # 16 列（要件§16.2 原典 行1118-1133 と照合済・「14列」表記は誤り）

# tests/ui/test_csv_columns.py — LOW-05 presence assert 再利用
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS, BACKTEST_CSV_COLUMNS

def test_prediction_csv_columns_count():
    """OUT-01: PREDICTION_CSV_COLUMNS は §16.2 pin の20列である（presence assert）。"""
    assert len(PREDICTION_CSV_COLUMNS) == 20
    # 必須スタンプ列が含まれる（§19.1 聖域）
    for stamp in ("odds_snapshot_policy", "odds_snapshot_at", "model_version", "feature_snapshot_id"):
        assert stamp in PREDICTION_CSV_COLUMNS, f"再現性スタンプ {stamp} が予測 CSV 列にない"

def test_backtest_csv_columns_count():
    """OUT-02: BACKTEST_CSV_COLUMNS は §16.2 原典の16列である（「14列」表記は誤り）。"""
    assert len(BACKTEST_CSV_COLUMNS) == 16
    assert "backtest_strategy_version" in BACKTEST_CSV_COLUMNS
```

### Anti-Patterns to Avoid

- **`selection="single-row"`（古い API 形状・UI-SPEC.md 記載）を使用する** — Streamlit 1.35+ の正引数は `selection_mode="single-row"` + `on_select=`。`selection=` は `StreamlitAPIException` になる。UI-SPEC.md の記述はプレースホルダ的で planner/executor が正引数に修正すること（本 RESEARCH で確定）。
- **`@st.cache_data` に `ConnectionPool` を `hash_funcs` なしで渡す** — `UnhashableParamError: Cannot hash object of type _thread._local`。`hash_funcs={ConnectionPool: id}` 必須、または DSN 文字列を渡す。
- **`st.session_state` で派生データ（フィルタ結果・選択レースの馬 DataFrame 等）を保持する** — CLAUDE.md が明示禁止。派生データは `@st.cache_data` で再計算させる。`st.session_state` は widget 状態（選択インデックス等）のみ。
- **UI 配下に書き込み/DDL 経路（`write_cursor`/`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`CREATE`）を置く** — read-only 保証（D-03）違反・Phase 8 対抗的監査(TEST-01)の前提崩壊。UI は `make_pool(role='readonly')` のみ使用。
- **予測/backtest を UI 内で再生成・再集計する** — stamped 成果物（Phase 4/5/6）を消費し再生成しない（§19.1 聖域・SC#4 bit-identical 維持）。UI は SELECT のみ。
- **§16.1 除外項目（ワイド/荒れ指数/コメント生成）を UI/CSV に混入する** — Phase 2 以降。混入すると Phase 8 監査で検出される。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 行選択 UI | checkbox 列 / `st.button` 行クリック / `st.data_editor` | `st.dataframe(selection_mode="single-row", on_select="rerun")` | Streamlit 1.35+ ネイティブ機能。`st.data_editor` は編集可能になり read-only 契約（D-03）と衝突。 |
| jyocd→競馬場名マッピング | UI 側に dict ハードコード | `src/config/code_tables.yaml` の `jyocd:` マッピング（PyYAML 読込） | 既存・DRY。マッピング追加時の二重管理を防止。 |
| CSV 列定義 | UI と CLI で別々の列リスト | `src/ui/csv_columns.py::PREDICTION_CSV_COLUMNS` / `BACKTEST_CSV_COLUMNS`（単一定数） | UI/CLI/test が同一参照で列揺れ構造的排除（D-04 DRY・LOW-05 パターン）。 |
| DB 接続・pool 管理 | 独自 pool / 生 `psycopg.connect` | `src/db/connection.py::make_pool(role='readonly')` + `readonly_cursor` | 既存・2ロール DSN（`keiba_readonly`）再利用。`Settings().dsn` で DSN 解決。 |
| UTF-8 BOM + CRLF CSV 出力 | 手動バイト操作 | `df.to_csv(index=False, encoding='utf-8-sig', lineterminator='\r\n')` | pandas 標準。Excel 互換・日本語馬名のため BOM 必須（UI-SPEC 指示）。 |
| calibration curve 描画 | matplotlib 静的 PNG / 手描画 SVG | `plotly.graph_objects.Figure` + `st.plotly_chart(use_container_width=True)` | D-05 LOCKED。Phase 6 が `reports/06-segments/*.html`（Plotly）を生成済でパッケージ一致。 |
| segment JSON スキーマ検証 | ad-hoc dict key check | property-based test（`hypothesis` 不要・全6軸ファイルを走査し `axis_name`/`segments[]`/`curve`/`scalar`/`segment_value` の存在 assert） | reports/06-segments は Phase 6 D-10/D-11/D-12 で生成済・スキーマ固定。契約 test で検出。 |

**Key insight:** Phase 7 は「表示と出力のみ」の read-only フェーズ。再生成・再集計・書き込みを一切行わず、Phase 4/5/6 の stamped 成果物を消費する。既存の DB helper・config・code_tables・REPORT_COLUMNS パターンを再利用し、新規发明を最小化する（CLAUDE.md「keep it simple」・§12.1）。

## Runtime State Inventory

> Phase 7 は新規 UI/CLI 追加フェーズ（rename/refactor/migration ではない）。本セクションは参考記載。

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — UI は既存 `prediction.fukusho_prediction` / `backtest.fukusho_backtest` を読むだけ（書き込みなし）。 | なし |
| Live service config | Streamlit 既定 port 8501（`streamlit run`・設定不要）。`.streamlit/config.toml` で `[theme] base="light"`・`primaryColor="#FF4B4B"`（UI-SPEC 指示）。 | 新規作成（1ファイル・UI-SPEC Color 契約） |
| OS-registered state | None — ローカル手動起動・デーモン登録しない。 | なし |
| Secrets/env vars | `KEIBA_DB_USER` / `KEIBA_DB_PASSWORD` 等（`.env`・既存・`Settings()` が読込）。UI は `keiba_readonly` ロール DSN を再利用。 | なし（既存 `.env` 流用） |
| Build artifacts | `uv add streamlit==1.58.0` で `uv.lock` 更新。hatch wheel `packages` に `src/ui` を追加（`pyproject.toml`・`src/config`/`src/db` と同列）。 | `pyproject.toml` 編集（2箇所・依存 + packages） |

## Common Pitfalls

### Pitfall 1: Streamlit 行選択 API の引数名誤り
**What goes wrong:** UI-SPEC.md に `st.dataframe(selection="single-row")` と記載されているが、Streamlit 1.35+ の正引数は `selection_mode="single-row"` + `on_select=` である。`selection=` を渡すと `StreamlitAPIException` / `TypeError`。
**Why it happens:** UI-SPEC は視覚契約（何を表示するか）を中心に記述され、API 引数名の正確さまで保証していない。Streamlit の selection 機能は 1.35.0（2024-05）で追加され API が安定しているが、引数名の認識が曖昧になりやすい。
**How to avoid:** `selection_mode="single-row"` + `on_select="rerun"`（選択で再実行）または `"ignore"`（既定・rerun なし）を使用。戻り値は `event.selection["rows"][0]`（行インデックス・`single-row` でも list）。
**Warning signs:** `StreamlitAPIException: selection is not a valid keyword argument` / `TypeError: dataframe() got an unexpected keyword argument 'selection'`。

### Pitfall 2: @st.cache_data で ConnectionPool がハッシュ化できず UnhashableParamError
**What goes wrong:** `@st.cache_data` 付き関数に `psycopg_pool.ConnectionPool` を渡すと `UnhashableParamError: Cannot hash object of type _thread._local`。pool 内部の `_thread.local` が再帰的にハッシュ化されない。
**Why it happens:** Streamlit はキャッシュキー計算のため引数を再帰的にハッシュ化するが、`ConnectionPool`（とその内部 `_thread.local`）は hashable でない。
**How to avoid:** `hash_funcs={ConnectionPool: id}` で pool の `id()`（メモリアドレス・同一性）をハッシュ値に使う。または DSN 文字列（`str`・hashable）を渡して関数内で pool を構築する（より Streamlit 慣用的）。
**Warning signs:** `UnhashableParamError` / `Cannot hash object of type _thread._local`。

### Pitfall 3: OUT-02 backtest CSV の列数「14列」と「16列」の齟齬
**What goes wrong:** CONTEXT.md D-04 / UI-SPEC で「backtest CSV 14列」と記載されるが、要件§16.2 原典（行1118-1134）と UI-SPEC の列挙を実数すると **16項目** ある。
**Why it happens:** 「14列」は要件定義書の初期ドラフト由来の誤記。原典の code block を行数えると 16 行（backtest_id〜EV_upper）。
**How to avoid:** `BACKTEST_CSV_COLUMNS` を **16列** で定義する（原典優先・CLAUDE.md「要件定義書優先」）。テストで `len(BACKTEST_CSV_COLUMNS) == 16` を assert。planner が OUT-02 実装の前提として確定すること。
**Warning signs:** テスト `assert len(...) == 14` が通らない / CSV ヘッダが 16 列になる。

### Pitfall 4: 派生データを st.session_state に保持する（CLAUDE.md 違反）
**What goes wrong:** フィルタ結果・選択レースの馬 DataFrame 等「派生データ」を `st.session_state` にキャッシュすると、データ更新時に陳腐化し rerun 整合性が崩れる。
**Why it happens:** `st.session_state` が「状態保持の場」と直感的に使ってしまう。
**How to avoid:** CLAUDE.md 指示通り派生データは `@st.cache_data` で再計算させる。`st.session_state` は widget 状態（`st.multiselect` の選択値等・Streamlit が自動管理）のみ。手動で `st.session_state["foo"] = derived_df` としない。
**Warning signs:** フィルタ変更後に古いデータが表示される / rerun で state と widget の不整合 warning。

### Pitfall 5: prediction テーブルの is_primary 絞り忘れ（主モデル以外が混入）
**What goes wrong:** `prediction.fukusho_prediction` は LightGBM(22,213行) + CatBoost(22,213行) の両モデル行を保持（Phase 6 D-09）。`is_primary=true` で絞らないと主モデル(LightGBM)以外が UI/CSV に混入する。
**Why it happens:** テーブルが複数 model_type/version を保持する設計（Phase 4 SC#4 staging-swap・silent 履歴破壊防止）のため、UI 側で主モデル絞りが必須。
**How to avoid:** 全 SELECT で `WHERE is_primary = true`（Phase 6 D-09・主モデル=LightGBM）。UI-SPEC の「model_type 表示切替（主モデル=LightGBM 固定表示が default）」は将来拡張用・Phase 1 は `is_primary=true` で固定。
**Warning signs:** UI 行数が 44,426（22,213×2）になる / 同一レース同一馬が2行出る。

### Pitfall 6: backtest odds の過大表示（honest 注記漏れ）
**What goes wrong:** backtest 回収率を「確定値」として表示すると、odds 正確性が JODDS取得完了後の再検証 subject（Phase 5 manual-only）であることを隠蔽し Core Value（honest 表示）に違反する。
**Why it happens:** backtest テーブルには数値が入っており「確定」に見える。
**How to avoid:** backtest タブと CSV メタ欄に `st.warning` で「odds 正確性は JODDS取得完了後に再検証する subject・現状の回収率は暫定値」と注記（UI-SPEC Copywriting Contract・honest 注記）。
**Warning signs:** backtest 回収率に「暫定」「参考」修飾がない。

## Code Examples

### CSV 出力（UTF-8 BOM + CRLF・Excel 互換）

```python
# Source: pandas 標準 + UI-SPEC CSV Export Contract
import pandas as pd
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS

def build_prediction_csv_bytes(df: pd.DataFrame) -> bytes:
    """予測 DataFrame から §16.2 pin 20列の CSV bytes を生成（UTF-8 BOM + CRLF）。

    UI(st.download_button) と CLI(run_export_predictions_csv.py) の両方が使用。
    """
    # 列順を PREDICTION_CSV_COLUMNS に整列（過不足は事前 assert で検出）
    missing = [c for c in PREDICTION_CSV_COLUMNS if c not in df.columns]
    assert not missing, f"予測 DataFrame に必須列がない: {missing}"
    ordered = df[list(PREDICTION_CSV_COLUMNS)]
    return ordered.to_csv(index=False, encoding="utf-8-sig", lineterminator="\r\n").encode("utf-8-sig")

# UI 側
st.download_button(
    label="予測CSVをダウンロード",
    data=build_prediction_csv_bytes(pred_df),
    file_name=f"predictions_{date_from}_{date_to}.csv",
    mime="text/csv",
)
```

### Plotly 動的 calibration curve（reports/06-segments/*.json 消費）

```python
# Source: reports/06-segments/*.json 実スキーマ検証（year.json/odds_band.json 等を読込確認）
import json
from pathlib import Path
import plotly.graph_objects as go
import streamlit as st

SEGMENTS_DIR = Path("reports/06-segments")
SEGMENT_AXES = ("year", "month", "jyocd", "entry_count", "ninki", "odds_band")  # D-12 の6軸

@st.cache_data
def load_segment_json(axis: str) -> dict:
    """reports/06-segments/<axis>.json を読込（stamped・Phase 6 D-10 生成済）。"""
    path = SEGMENTS_DIR / f"{axis}.json"
    if not path.exists():
        return {}  # empty state・UI-SPEC Copywriting で案内
    return json.loads(path.read_text(encoding="utf-8"))

def build_calibration_figure(seg_data: dict) -> go.Figure:
    """segment JSON から curve 重ね描き Figure を構築（D-05・D-11）。

    期待スキーマ（実ファイル確認済）:
      {"axis_name": str, "segments": [
          {"segment_value": str, "curve": {"count":[...], "frac_pos":[...], "mean_pred":[...]},
           "scalar": {"ece_quantile":float, "ece_uniform":float, "max_dev_guarded":float,
                      "mce_guarded":float, "n_samples":int}}
      ]}
    """
    fig = go.Figure()
    for seg in seg_data.get("segments", []):
        curve = seg["curve"]
        sv = seg["segment_value"]
        n = seg["scalar"].get("n_samples", 0)
        label = f"{sv} (n={n:,})"
        # 完全予測（identity）線は最初の segment にのみ描画してもよい（UI-SPEC Claude's Discretion）
        fig.add_trace(go.Scatter(
            x=curve["mean_pred"], y=curve["frac_pos"], mode="lines+markers",
            name=label, hovertemplate="予測: %{x:.3f}<br>実測: %{y:.3f}<br>" + label,
        ))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                             line=dict(dash="dash", color="gray"), name="完全予測", showlegend=False))
    fig.update_layout(
        xaxis_title="予測確率 (mean_pred)", yaxis_title="実測頻度 (frac_pos)",
        xaxis_range=[0, 1], yaxis_range=[0, 1], legend_title=seg_data.get("axis_name", ""),
    )
    return fig

axis = st.selectbox("segment 軸", SEGMENT_AXES)
seg_data = load_segment_json(axis)
if not seg_data:
    st.info("segment データが未生成です。`scripts/run_evaluation.py` を実行して `reports/06-segments/` を生成してください。")
else:
    st.plotly_chart(build_calibration_figure(seg_data), use_container_width=True)
    # scalar 表併記（D-11）
    scalar_rows = [{"segment_value": s["segment_value"], **s["scalar"]} for s in seg_data["segments"]]
    st.dataframe(scalar_rows)
```

### read-only 保証の構造的検証テスト（Phase 8 TEST-01 前提）

```python
# tests/ui/test_readonly_guarantee.py
"""read-only 保証の構造的検証（D-03・Phase 8 TEST-01 前提）。

UI 配下の src/ui/ モジュールが書き込み/DDL 経路（INSERT/UPDATE/DELETE/TRUNCATE/CREATE/DROP/ALTER）
を含まないことを AST/grep で検証。write_cursor / role='etl' の使用も禁止。
"""
import ast
from pathlib import Path

UI_DIR = Path("src/ui")
FORBIDDEN_CALLS = {"write_cursor", "make_pool"}  # make_pool は role='readonly' のみ許可・検査で引数確認
FORBIDDEN_KEYWORDS = ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "CREATE ", "DROP ", "ALTER ")
# ※ make_pool は readonly 引数確認が必要なため別途検査

def _walk_py_files(d: Path):
    yield from d.rglob("*.py")

def test_ui_has_no_write_ddl_sql():
    """src/ui/ 配下に書き込み/DDL SQL キーワードが含まれない（大文字小文字区別なし・文字列内も検査）。"""
    for py in _walk_py_files(UI_DIR):
        text = py.read_text(encoding="utf-8")
        lower = text.lower()
        for kw in ("insert into", "update ", "delete from", "truncate ", "create table",
                   "drop table", "alter table"):
            assert kw not in lower, f"{py}: 書き込み/DDL SQL '{kw}' が含まれる（read-only 違反・D-03）"

def test_ui_uses_only_readonly_pool():
    """src/ui/ の make_pool 呼出は全て role='readonly'（既定）または引数なし。"""
    for py in _walk_py_files(UI_DIR):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "make_pool":
                role_arg = next((kw.value for kw in node.keywords if kw.arg == "role"), None)
                # role 未指定（既定='readonly'）または role='readonly' のみ許可
                if role_arg is not None:
                    assert (isinstance(role_arg, ast.Constant) and role_arg.value == "readonly"), \
                        f"{py}: make_pool(role=...) が 'readonly' でない（read-only 違反・D-03）"
```

## CSV Export Contract（OUT-01 / OUT-02・D-04 LOCKED）

### 予測CSV（OUT-01・20列・§16.2 原典 行1092-1112 と照合済）

`PREDICTION_CSV_COLUMNS`（`src/ui/csv_columns.py` で単一定数化）:

```text
race_id / race_date / race_start_datetime / 競馬場 / レース番号 /
horse_id / horse_name / 枠番 / 馬番 / p_fukusho_hit /
fukusho_odds_lower / fukusho_odds_upper / EV_lower / EV_upper / recommend_rank /
odds_snapshot_policy / odds_snapshot_at /
model_version / feature_snapshot_id / prediction_created_at
```

### Backtest CSV（OUT-02・16列・§16.2 原典 行1118-1133 と照合済）

`BACKTEST_CSV_COLUMNS`（同定数化）:

```text
backtest_id / backtest_strategy_version /
train_period / validation_period / odds_snapshot_policy /
race_id / horse_id /
selected_flag / stake / refund_flag / payout_amount / profit /
fukusho_hit_validated / recommend_rank / EV_lower / EV_upper
```

> **列数齟齬の解消（planner 必読）:** 要件§16.2 原典（行1118-1134）を行数えると **16項目**。CONTEXT.md D-04 および UI-SPEC に「14列」と記載されるが、これは**初期ドラフト由来の誤記**。CLAUDE.md「要件定義書優先」に従い **16列** を正とする。`BACKTEST_CSV_COLUMNS` を 16 列で定義し、テスト `assert len(BACKTEST_CSV_COLUMNS) == 16` で確定する。

**検証契約:**
- `src/ev/report.py::REPORT_COLUMNS` の LOW-05 presence assert パターン（`tests/ev/test_run_backtest_e2e.py:296-320` 参照）を再利用し、`PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` と §16.2 原典の 1:1 対応を unit test で機械検証。
- UI と CLI（`scripts/run_export_*.py`）は同一定数を import し列揺れを構造的に排除（D-04 DRY）。
- CSV 1行目ヘッダ・UTF-8 with BOM（`encoding='utf-8-sig'`・Excel 互換・日本語馬名のため）・改行 CRLF（`lineterminator='\r\n'`）。

## Data Provenance（表示ラベル取得経路・実テーブル/カラム確認済）

| 表示項目 | 取得元 | カラム/経路 | 備考 |
|----------|--------|-------------|------|
| 予測行の中核 | `prediction.fukusho_prediction` | `model_version`/`feature_snapshot_id`/`odds_snapshot_policy`/`p_fukusho_hit`/`race_date`/`is_primary` | `WHERE is_primary=true`（Phase 6 D-09・主モデル=LightGBM）。`odds_snapshot_at` は prediction テーブルに**ない** — backtest 側または 別途保持要確認（要項参照）。 |
| 競馬場名 | `src/config/code_tables.yaml` | `jyocd:` マッピング（`"01":札幌`..`"10":小倉`） | PyYAML 読込・DB JOIN 不要。`st.multiselect(format_func=)` で表示名に変換。 |
| レース番号 | `prediction.fukusho_prediction` | `racenum`（PK RACE_KEY 構成要素） | 直接 SELECT 可。 |
| 馬名 | `normalized.n_uma_race` | `bamei`（normalize.py L106・`_UMA_RACE_SELECT_COLUMNS`） | `(year,jyocd,kaiji,nichiji,racenum,umaban,kettonum)` で JOIN。 |
| 枠番 / 馬番 | `normalized.n_uma_race` / prediction PK | `wakuban`（L105）/ `umaban`（PK） | `umaban` は prediction PK にも含まれる。`wakuban` は normalized JOIN。 |
| horse_id | `normalized.n_uma_race` | `kettonum`（血統登録番号・L101・horse_id 代用） | prediction PK の `kettonum` と一致。 |
| EV_lower/EV_upper・推奨ランク・fukusho_odds_lower/upper | `backtest.fukusho_backtest`（backtest CSV 用） | `EV_lower`/`EV_upper`/`recommend_rank`（DDL L179-180 引用符付き大文字保持） | 予測 CSV 用の EV/odds は prediction テーブルには直接ない — **ev_rank 計算結果を別途保持または UI/CLI 側で再計算**（`src/ev/ev_rank.py::compute_ev_and_rank` 純粋関数・DB 不要）。 |
| backtest 戦略/期間 | `backtest.fukusho_backtest` | `backtest_id`/`backtest_strategy_version`/`train_period_start`/`train_period_end`/`test_period_start`/`test_period_end`/`odds_snapshot_policy` | OUT-02 CSV の `train_period`/`validation_period` は start-end 文字列結合で生成。 |
| calibration curve/scalar | `reports/06-segments/*.json` | `axis_name`/`segments[].curve`/`segments[].scalar`/`segments[].segment_value` | Phase 6 D-10/D-11/D-12 生成済・`@st.cache_data` でファイル読込。 |

**⚠ 要項（planner 確認事項）:**
- **`odds_snapshot_at` の取得元:** prediction テーブル DDL（schema.py L59-94）には `odds_snapshot_at` 列がない。OUT-01 CSV に含める必要があるが、予測生成時に odds snapshot を取得した時点タイムスタンプをどこかに保持しているか、または固定値（`as_of_datetime` 代用）とするかを planner が確認すること。backtest テーブルには `odds_snapshot_at`（L182）がある。
- **EV/odds の予測 CSV 出力:** prediction テーブルは `p_fukusho_hit` のみ保持。EV_lower/EV_upper/fukusho_odds_lower/upper/recommend_rank は prediction 行だけからは得られない。`src/ev/ev_rank.py::compute_ev_and_rank`（純粋関数・p + odds → EV/rank）を UI/CLI 側で適用するか、ev 計算結果をどこかに永続化しているかを planner が確認すること。backtest テーブルには EV/rank がある。

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `st.dataframe` 行選択に checkbox 列/`st.button` を手動実装 | `selection_mode` + `on_select` ネイティブ API | Streamlit 1.35.0（2024-05） | マスター・ディテールが標準 API で簡潔に。`st.data_editor`（編集可能）は read-only 契約と衝突するため不採用。 |
| `@st.cache`（旧・単一デコレータ） | `@st.cache_data`（直列化可能データ）/ `@st.cache_resource`（非直列化リソース）の分離 | Streamlit 1.18.0（2023-03） | DataFrame/DB 結果は `@st.cache_data`。ConnectionPool は `hash_funcs` で対応。 |
| `st.table`（静的・スクロール不可） | `st.dataframe`（インタラクティブ・選択/ソート/列設定） | Streamlit 1.0+ | UI-01 レース一覧・馬別展開は `st.dataframe`。`st.table` は小表（scalar 指標）のみ。 |
| matplotlib 静的 PNG（Streamlit 埋込） | Plotly インタラクティブ（`st.plotly_chart`） | Streamlit 1.0+（Plotly サポート） | D-05 動的描画・Phase 6 が Plotly HTML 生成済でパッケージ一致。matplotlib は併用しない。 |

**Deprecated/outdated:**
- `st.cache`（旧デコレータ）: `@st.cache_data`/`@st.cache_resource` に置換（1.18.0+）。新規コードでは使用禁止。
- `st.experimental_data_editor`: `st.data_editor` に GA 昇格（本プロジェクトでは read-only のため不採用）。
- `st.pyplot` 単独使用: D-05 は Plotly のため不使用（CLAUDE.md「Plotly は Streamlit と統合が良い」）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `selection_mode="single-row"` + `on_select="rerun"` が Streamlit 1.58.0 で正引数（`selection=` でない） | Pattern 1 / Pitfall 1 | `[CITED: docs.streamlit.io]` で確認済・HIGH。UI-SPEC の `selection=` は誤記。 |
| A2 | `@st.cache_data(hash_funcs={ConnectionPool: id})` で UnhashableParamError 解消 | Pattern 2 / Pitfall 2 | `[CITED: discuss.streamlit.io]` コミュニティ + 公式 caching docs で確認・MEDIUM（実環境未検証・planner が DSN 渡し代替も検討）。 |
| A3 | OUT-02 backtest CSV は 16 列（「14列」は誤記） | CSV Export Contract / Pitfall 3 | 要件§16.2 原典（行1118-1134）を行数えて確定・HIGH。CLAUDE.md「要件優先」。 |
| A4 | `prediction` テーブルに `odds_snapshot_at` 列がない（schema.py DDL 確認） | Data Provenance | `[VERIFIED: src/db/schema.py:59-94]` コード確認済・HIGH。planner が取得元（別保持 or `as_of_datetime` 代用）を確定する必要。 |
| A5 | prediction テーブルは `p_fukusho_hit` のみで EV/odds/rank 列がない | Data Provenance | `[VERIFIED: src/db/schema.py:59-94]`・HIGH。UI/CLI 側で `compute_ev_and_rank` 再適用 or 別永続化の確認が必要。 |
| A6 | `code_tables.yaml` の `jyocd:` マッピングが JRA 10場を網羅 | Standard Stack / Data Provenance | `[VERIFIED: src/config/code_tables.yaml]`（01-10 確認済）・HIGH。 |
| A7 | `reports/06-segments/*.json` が6軸すべて生成済み | Data Provenance / Code Examples | `[VERIFIED: ls reports/06-segments/]`（year/month/jyocd/entry_count/ninki/odds_band の6ファイル確認）・HIGH。 |
| A8 | Streamlit 1.58.0 が Python 3.12 で動作 | Standard Stack | `[CITED: docs.streamlit.io]`（Python ≥3.10 サポート・3.12 完全対応）・HIGH。 |

## Open Questions (RESOLVED)

> **解決済（Phase 7 revision・planner が src/ev/odds_snapshot.py・src/ev/ev_rank.py・src/db/schema.py・src/db/backtest_load.py を読んで確定）:**
> 3 Question とも 07-02-PLAN.md / 07-03-PLAN.md に反映済。正経路は **JODDS snapshot（`src/ev/odds_snapshot.py::fetch_jodds` + `select_odds_snapshot(policy)`）+ `compute_ev_and_rank` 純粋関数再計算**（backtest JOIN 経路は `backtest.fukusho_backtest` に odds 値カラム `fuku_odds_lower`/`fuku_odds_upper` が不存在のため構造的に不可能・`BACKTEST_COLUMNS` L77-116 実証済）。

1. **`odds_snapshot_at` の予測 CSV への取得元**
   - What we know: prediction テーブル DDL（schema.py L59-94）に `odds_snapshot_at` 列はない。backtest テーブル（L182）にはある。OUT-01 CSV は `odds_snapshot_at` を含む。
   - What's unclear: 予測生成時に odds snapshot 取得時点をどこかに保持しているか（別テーブル/メタ/`as_of_datetime` 代用）、または UI/CLI 側で固定値/推定値を入れるか。
   - Recommendation: planner が Phase 4/5 の予測・EV パイプライン（`src/model/predict.py`/`src/ev/odds_snapshot.py`）を確認し、`odds_snapshot_at` の取得元を確定する。`as_of_datetime` 代用が妥当ならその旨を定数化。
   - **✅ RESOLVED:** `src/ev/odds_snapshot.py::select_odds_snapshot` 戻り値の `odds_snapshot_at` 列（選択 snapshot の `happyo_datetime` Timestamp・L213/L326）から取得する。`fetch_jodds(readonly_cur, years=...)` で JODDS 中間オッズ（`datakubun='1'`・D-01）を取得し・`select_odds_snapshot(jodds_df, race_times_df, policy)` で `merge_asof(direction='backward', by=['race_key','umaban'])` により各馬単位の cutoff 以下最大 snapshot を選択・その戻り値の `odds_snapshot_at` を予測 CSV に結合する（07-02-PLAN.md Task 1 Step 2）。`as_of_datetime`（予測生成時点）は `prediction_created_at` 代用として別列に使用（Open Question #1 とは別物）。未来リーク構造的不可（D-02・HIGH-1 per-horse odds 保証）。

2. **予測 CSV の EV/odds/rank の算出経路**
   - What we know: prediction テーブルは `p_fukusho_hit` のみ。EV_lower/EV_upper/fukusho_odds_lower/upper/recommend_rank は prediction 行単体からは得られない。
   - What's unclear: UI/CLI 側で `src/ev/ev_rank.py::compute_ev_and_rank`（純粋関数・p + odds → EV/rank）を都度適用するか、ev 計算結果を永続化したテーブル/JSON があるか。
   - Recommendation: planner が `src/ev/` 配下と Phase 5 ev 計算結果の永続化有無を確認。純粋関数再適用が最もリーク安全（odds は EV 判定のみ・特徴量非混入）。
   - **✅ RESOLVED:** `src/ev/ev_rank.py::compute_ev_and_rank`（L80・純粋関数）を UI/CLI 側で都度適用する（Recommendation どおり・最もリーク安全）。経路: prediction SELECT（`is_primary=true`）→ JODDS snapshot 取得（`fetch_jodds` + `select_odds_snapshot(policy)`・`fuku_odds_lower`/`fuku_odds_upper` 取得）→ `(race_key, umaban)` で結合 → `compute_ev_and_rank` で `EV_lower`/`EV_upper`（§11.1 直線積 p*odds）・`recommend_rank`（§11.5 階層判定 S/A/B/C/D）を算出（07-02-PLAN.md Task 1 Step 3）。odds は EV 判定にのみ使用し特徴量に混入しない（D-07 odds 非依存確率 p_fukusho_hit + EV 分離・Core Value 直結・§19.1 再現性）。backtest JOIN 経路は backtest テーブルに `fuku_odds_lower`/`fuku_odds_upper` が不存在（`BACKTEST_COLUMNS` L77-116）のため構造的に不可能。

3. **`src/ui/` vs `streamlit_app/` 最終判断**
   - What we know: §17.2 は `streamlit_app/` を提案。実コードは `src/` レイアウト。`src/ui/` は import 単純・`streamlit_app/` は `sys.path` 操作要。
   - What's unclear: hatch wheel `packages`（現 `src/config`/`src/db`）に `src/ui` を追加するだけで `streamlit run src/ui/app.py` が動くか。
   - Recommendation: `src/ui/` を推奨（実コード慣例・import 単純）。`pyproject.toml` の `[tool.hatch.build.targets.wheel] packages` に `"src/ui"` を追加。planner が判断。
   - **✅ RESOLVED:** `src/ui/` を採用（Recommendation どおり）。`pyproject.toml` の `[tool.hatch.build.targets.wheel] packages` に `"src/ui"` を追加し・`streamlit run src/ui/app.py` で起動可能（07-01-PLAN.md Task 1/2・Open Question #3 解決）。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | 全体 | ✓ | 3.12.13（host） | 3.11（§17.1 切替可） |
| uv | 依存管理 | ✓ | ≥0.11（host: 0.11.21） | — |
| PostgreSQL | 予測/backtest 行データ読込 | ✓ | 15.18（Homebrew・host） | — |
| Streamlit | UI（UI-01・D-01..D-05） | ✗（未インストール） | — | `uv add streamlit==1.58.0` で追加 |
| Plotly | 動的 calibration 描画（D-05） | ✓ | 6.8.0（pyproject 既依存 `>=6.8.0`） | — |
| pandas | DataFrame/CSV | ✓ | 3.0.3（既依存） | — |
| psycopg[binary] | PostgreSQL 接続 | ✓ | 3.3.4（既依存） | — |
| psycopg-pool | ConnectionPool | ✓ | 3.3.1（既依存） | — |
| PyYAML | code_tables.yaml 読込 | ✓ | `pyyaml`（既依存） | — |
| pydantic-settings | Settings().dsn | ✓ | 2.14.1（既依存） | — |
| pytest | テスト（§17.3・Validation） | ✓ | 9.1.0（dev 既依存） | — |
| ruff | lint/format | ✓ | 0.15.17（dev 既依存） | — |

**Missing dependencies with no fallback:**
- なし（Streamlit 1件のみ `uv add` で解決・他は全て既依存）。

**Missing dependencies with fallback:**
- なし。

## Validation Architecture

> `workflow.nyquist_validation` は `config.json` で `true`（明示的）。本セクション必須。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存・`pyproject.toml [dependency-groups] dev`） |
| Config file | `pyproject.toml [tool.pytest.ini_options]`（`testpaths=["tests"]`・`addopts="-ra"`・`markers=["requires_db: ..."]`） |
| Quick run command | `uv run pytest tests/ui/ -x -q`（UI 配下のみ・DB 不要・<10s） |
| Full suite command | `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（DB 不要全套・推奨）または `uv run pytest -q`（DB 含む全套） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | CSV 列定数 `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` が §16.2 pin と 1:1 | unit | `uv run pytest tests/ui/test_csv_columns.py -x` | ❌ Wave 0 |
| UI-01 | 再現性スタンプ5列が PREDICTION_CSV_COLUMNS に含まれる（§19.1 聖域） | unit | `uv run pytest tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps -x` | ❌ Wave 0 |
| UI-01 | read-only 保証: src/ui/ 配下に書き込み/DDL SQL・`role='etl'` 経路が不存在 | unit/contract | `uv run pytest tests/ui/test_readonly_guarantee.py -x` | ❌ Wave 0 |
| UI-01 | Streamlit 描画契約: `selection_mode`/`on_select`/`st.column_config` の正引数使用 | contract | `uv run pytest tests/ui/test_streamlit_api_usage.py -x`（AST で引数名検証） | ❌ Wave 0 |
| OUT-01 | 予測 CSV が UTF-8 BOM + CRLF・20列ヘッダを生成 | unit | `uv run pytest tests/ui/test_csv_export.py::test_prediction_csv_bom_crlf -x` | ❌ Wave 0 |
| OUT-02 | backtest CSV が 16列（「14列」でない）・honest 注記メタ含む | unit | `uv run pytest tests/ui/test_csv_export.py::test_backtest_csv_16_columns -x` | ❌ Wave 0 |
| D-05 | reports/06-segments/*.json スキーマ契約（6軸・curve/scalar/segment_value 存在） | contract/property | `uv run pytest tests/ui/test_segment_schema.py -x` | ❌ Wave 0 |
| D-04 | UI と CLI が同一 `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` を import | unit | `uv run pytest tests/ui/test_csv_columns.py::test_ui_cli_share_columns -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -x -q`（UI 配下・DB 不要・<10s・速報）
- **Per wave merge:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（DB 不要全套・回帰確認）
- **Phase gate:** `uv run pytest -q`（DB 含む全套・`requires_db` マーク付きは live PostgreSQL 必要）green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/ui/__init__.py` — パッケージ化
- [ ] `tests/ui/test_csv_columns.py` — OUT-01/OUT-02 列定数 presence assert（LOW-05 再利用・§16.2 1:1）
- [ ] `tests/ui/test_readonly_guarantee.py` — read-only 保証の構造的検証（AST/grep・書き込み/DDL 経路不存在）
- [ ] `tests/ui/test_csv_export.py` — UTF-8 BOM + CRLF・列順・ヘッダ検証
- [ ] `tests/ui/test_segment_schema.py` — reports/06-segments/*.json スキーマ契約（6軍・property test）
- [ ] `tests/ui/test_streamlit_api_usage.py` — `selection_mode`/`on_select` 正引数使用の AST 検証（Pitfall 1 予防）
- [ ] Framework install: 不要（pytest 9.1.0 既存）

*(ruff/format は既存設定を踏襲・新規框架追加なし)*

## Security Domain

> `security_enforcement` は `config.json` で `true`（`security_asvs_level: 1`）。本セクション必須。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 該当なし（ローカル単一ユーザー・Streamlit 認証不要・§16.1） |
| V3 Session Management | no | 該当なし（ローカル・認証セッションなし） |
| V4 Access Control | **yes** | DB ロールベース: `keiba_readonly`（GRANT 済み・`schema.py GRANT_READER_SQL`）・schema 修飾 SELECT のみ・書き込み/DDL REVOKE 済（`REVOKE_RAW_WRITES_*`）。UI 配下に `role='etl'`/`write_cursor` 経路なし（`test_readonly_guarantee.py` で構造的検証）。 |
| V5 Input Validation | **yes** | Streamlit widget 値（date_input/multiselect/selectbox）は型安全・SQL へは psycopg parameterized query（`%s` placeholder）で注入。文字列組み立て禁止（既存 `prediction_load.py`/`backtest_load.py` の `psycopg.sql.SQL`+`Placeholder` パターン踏襲）。 |
| V6 Cryptography | no | 該当なし（パスワードは `Settings().db_password: SecretStr`・DSN は `Settings.dsn` property・ログ出力厳禁は既存・UI 側で新規扱いなし） |
| V7 Errors & Logging | **yes** | DB 接続失敗時の `st.error`/`st.warning` で DSN/パスワードを表示しない（`Settings().dsn_masked` のみ表示・既存パターン）。UI-SPEC Error state コピー参照。 |
| V8 Data Protection | **yes** | `Settings().dsn`/`etl_dsn` は生パスワード含むため**ログ出力厳禁**（既存 MEDIUM #1・ASVS V8）。`@st.cache_data` のキャッシュに DSN が入らないよう DSN は `hash_funcs` のみ（DSN 渡しの場合はキャッシュキーに使われるが Streamlit はキャッシュをメモリ内保持・ディスク永続化なし）。 |
| V9 Communications | no | 該当なし（ローカル HTTP・localhost:8501・外部 API/fetch なし・UI-SPEC Registry Safety） |
| V13 API & Web Service | **yes（最小）** | Streamlit は ローカル単一ユーザー・CSRF/XSS は Streamlit フレームワーク既定。UI は `st.markdown` で `unsafe_allow_html=True` を使用しない（デフォルト・UI-SPEC CSS カスタマイズ最小）。 |

### Known Threat Patterns for Streamlit + PostgreSQL readonly

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection（フィルタ値の文字列組み立て） | Tampering | psycopg parameterized query（`cur.execute(sql, params)`）・`psycopg.sql.SQL`+`Placeholder`。`f"SELECT ... WHERE jyocd = '{val}'"` 禁止。 |
| 権限昇格（readonly ロールでの書き込み） | Elevation | `keiba_readonly` ロールは `prediction`/`backtest`/`label`/`normalized`/`public` の SELECT のみ（GRANT_READER_SQL）・UPDATE/DELETE/TRUNCATE は REVOKE 済（REVOKE_RAW_WRITES_*）。UI 配下に `make_pool(role='etl')` 経路なし（テストで検証）。 |
| Information Disclosure（DSN/パスワード漏洩） | Information Disclosure | `Settings().dsn` はログ出力厳禁・`dsn_masked` のみ表示（既存 MEDIUM #1）。`st.error` に生 DSN を含めない。 |
| 再現性スタンプ欠落（silent 聖域違反） | Tampering（データ完全性） | 全予測行/CSV に5スタンプ inline 表示（§19.1）・presence assert で検証・Phase 8 が対抗的監査（TEST-01）。 |
| §16.1 除外項目混入（ワイド/荒れ指数/コメント） | Tampering（スコープ逸脱） | UI/CSV 列定数で機械的に排除・テストで検証。 |

## Sources

### Primary (HIGH confidence)

- **要件定義書 v1.3 §16.1/§16.2/§11.5/§17.1/§17.2/§17.3**（`docs/keiba_ai_requirements_v1.3.md` 行1069-1195, 655-681）— UI 表示項目・CSV 列 pin（原典）・推奨ランク閾値・技術スタック・プロジェクト構成・テストコード。CLAUDE.md「要件定義書優先」。
- **`src/db/schema.py`**（L59-94 PREDICTION_TABLE_DDL・L109-123 PREDICTION_ADD_IS_PRIMARY_SQL・L144-202 BACKTEST_TABLE_DDL・L234-259 GRANT_READER_SQL・L296-308 REVOKE_RAW_WRITES_*）— テーブル構造・read-only GRANT の正。
- **`src/db/connection.py`**（L21-63 make_pool・L66-87 readonly_cursor/write_cursor）— 2ロール DSN・readonly pool 構築の正。
- **`src/config/settings.py`**（L1-150 Settings・dsn/dsn_masked/SecretStr）— DSN 管理・ログ出力厳禁の正。
- **`src/config/code_tables.yaml`**（jyocd マッピング 01-10）— 競馬場名マッピングの正。
- **`src/model/predict.py`**（L55-86 PREDICTION_COLUMNS/MODEL_TYPE_TO_SHORT/PK_COLUMNS）— prediction 行の列順・主モデル絞り参考。
- **`src/db/prediction_load.py`**（L62-84・L373-411 load_predictions/set_primary_model）— staging-swap idiom・`is_primary` 絞り参考。
- **`src/db/backtest_load.py`**（L77-103 BACKTEST_COLUMNS）— backtest 行の列順・OUT-02 CSV 参考。
- **`src/ev/report.py`**（L41-50 REPORT_COLUMNS・LOW-05 presence assert パターン）— CSV 列定数 DRY パターンの再利用元。
- **`tests/ev/test_run_backtest_e2e.py`**（L296-320 LOW-05 presence assert 実装）— テストパターン実例。
- **`reports/06-segments/*.json`**（year/month/jyocd/entry_count/ninki/odds_band の6ファイル・実スキーマ確認済）— D-05 動的描画の入力データ。
- **`pyproject.toml`**（dependencies・`[tool.pytest.ini_options]`・`[tool.hatch.build.targets.wheel] packages`）— 既存依存・テスト設定・wheel packages。
- **`07-CONTEXT.md`**（D-01..D-05 LOCKED・canonical_refs・code_context）— 設計契約の正。
- **`07-UI-SPEC.md`**（Sign-Off 6/6・Layout/Color/Typography/Copywriting/Registry/CSV Contract）— 視覚/相互作用契約の正。

### Secondary (MEDIUM confidence)

- **Streamlit 公式 docs — st.dataframe**（`docs.streamlit.io/develop/api-reference/data/st.dataframe`）— `selection_mode`/`on_select`/戻り値 `selection["rows"]` の API 仕様。`[CITED]`。
- **Streamlit 公式 tutorial — dataframe-row-selections**（`docs.streamlit.io/develop/tutorials/elements/dataframe-row-selections`）— 行選択パターン。`[CITED]`。
- **Streamlit 公式 docs — Caching**（`docs.streamlit.io/develop/concepts/architecture/caching`）— `@st.cache_data`/`hash_funcs` 仕様。`[CITED]`。
- **Streamlit Forum — UnhashableType: _thread._local**（`discuss.streamlit.io/t/unhashabletype-cannot-hash-object-of-type-thread-local/1917`）— `hash_funcs={ConnectionPool: id}` 解法。`[CITED]`（コミュニティ・公式 docs と整合）。
- **Plotly 公式 — plotly.com/python/**（`plotly.com/python/`）— `go.Figure`/`go.Scatter` API。`[CITED]`。
- **CLAUDE.md**（Recommended Stack Streamlit 1.58.0・`@st.cache_data` 指示・Plotly 推奨・§16/§17.2 参照・応答言語日本語）— プロジェクト指示（権威）。

### Tertiary (LOW confidence)

- *(なし — 全 claim が VERIFIED/CITED で裏付け済み)*

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — Streamlit 1.58.0/Plotly 6.8.0/pandas/psycopg は既存依存または公式推奨・CLAUDE.md/§17.1 で固定。
- Architecture: **HIGH** — D-01..D-05 LOCKED・UI-SPEC 承認済・既存コード契約（schema/connection/predict/backtest_load/report）で裏付け。
- Pitfalls: **HIGH** — Streamlit API 引数名/`hash_funcs`/CSV 列数齟齬は実ドキュメント+実コード+要件原典で検証済。
- Data Provenance: **HIGH** — 実テーブル/カラム/JSON ファイルを読込確認。ただし `odds_snapshot_at` 取得元(A4)と EV/odds 算出経路(A5)は planner 確認事項。

**Research date:** 2026-06-24
**Valid until:** 2026-07-24（30日・安定ドメイン・Streamlit/Plotly API は四半期単位で安定）
