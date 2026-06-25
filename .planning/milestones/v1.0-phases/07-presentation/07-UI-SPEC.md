---
phase: 7
slug: presentation
status: approved
shadcn_initialized: false
preset: none
created: 2026-06-24
reviewed_at: 2026-06-24
---

# Phase 7 — UI Design Contract

> Streamlit（Python 3.12）単一ローカルユーザー・read-only 分析ツール向けの視覚/相互作用契約。
> React/Next.js/Vite 系ではないため shadcn ゲートは対象外。Streamlit 1.58.0 ネイティブコンポーネント + Plotly で構成する。
> レイアウト/データ読込/CSV 出力の枠組みは `07-CONTEXT.md` の D-01..D-05 で LOCKED。本ファイルは残る視覚契約（スペーシング・タイポグラフィ・色・コピーライティング・安全性）を確定する。

---

## Design System

| Property | Value |
|----------|-------|
| Tool | Streamlit 1.58.0（ネイティブコンポーネント中心・CSS カスタマイズ最小） |
| Preset | not applicable（shadcn 非対象・Streamlit テーマ設定 `config.toml` のみ） |
| Component library | Streamlit 組み込み（`st.dataframe`/`st.selectbox`/`st.download_button`/`st.tabs`/`st.expander`/`st.metric`/`st.sidebar`） |
| Icon library | なし（Streamlit 組み込み emoji は使わない・推奨ランク色分けと数値で表現） |
| Chart library | Plotly 6.8.0（`reports/06-segments/*.json` を消費し動的 calibration curve 描画・D-05） |
| Font | Streamlit 既定（system sans-serif・日本語フォントは OS 既定・個人ローカル単一ユーザーのため指定不要） |
| Theme | Streamlit light theme 既定（`[theme] base="light"`・色弱配慮のため色+ラベルで情報を二重化） |

### 設計原則（本プロジェクト固有）
1. **再現性スタンプは聖域** — `odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version` を予測行・CSV ファイルの**各レコード** に inline 表示（§19.1・CONTEXT specifics）。
2. **read-only 保証** — 書き込み経路は存在しない（`keiba_readonly` ロール・schema 修飾 SELECT のみ）。破壊的アクション・編集 UI は一切配置しない。
3. **honest 注記** — backtest odds 正確性は JODDS 取得完了後の再検証 subject である旨を backtest 表示画面と CSV メタ欄に明示（Phase 5 manual-only 整合・回収率の過大表示回避）。
4. **§16.1 除外項目の排除** — ワイド候補・ワイド期待値・荒れ指数・コメント生成は UI/CSV に混入しない（Phase 2 以降）。
5. **確率品質（Calibration）吟味が主目的** — 個人分析ツール・実馬券購入しない。D-05 segment 動的描画を中核機能として扱う。

---

## Layout Contract（D-01..D-05 LOCKED → 具体化）

### 画面構成（マスター・ディテール・D-01）
```
┌─────────────────────────────────────────────────────────────────┐
│ st.sidebar（D-02 主要フィルタ）                                  │
│  ・日付範囲 (st.date_input, range)                                │
│  ・競馬場 jyocd (st.multiselect・コード→名称マッピング)            │
│  ・推奨ランク S/A/B/C/D (st.multiselect・default=S,A,B)           │
│  ・model_type 表示切替（主モデル=LightGBM 固定表示が default）      │
│  ─────────────────────────                                       │
│  ・データソース注記（readonly・stamped）                           │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ st.tabs（3タブ・multipage ではなく単一ページ内タブ）               │
│  [予測一覧]  [Backtest]  [Segment Calibration]                    │
│                                                                   │
│  ─ 予測一覧タブ（UI-01・D-01 マスター・ディテール）─               │
│   レース一覧 st.dataframe（行選択・selection="single-row"）        │
│     列: race_date / 競馬場 / R番 / 頭数 / 件数                     │
│     デフォルトソート: race_date DESC（最新日優先）                  │
│   ↓ 行選択で展開                                                   │
│   選択レースの各馬 st.dataframe                                    │
│     列: 馬番/枠番/馬名/p_fukusho_hit/odds下限/odds上限/            │
│         EV_lower/EV_upper/recommend_rank + 再現性スタンプ5列        │
│     recommend_rank 列は色分け（S=赤系/A=オレンジ/B=黄/            │
│         C=灰/D=薄灰・Streamlit column_config 式）                  │
│   st.download_button「予測CSV出力（OUT-01・20列）」                │
│                                                                   │
│  ─ Backtestタブ（OUT-02 表示元）─                                 │
│   backtest 一覧 st.dataframe（backtest_id/戦略バージョン/           │
│     学習検証期間/recovery_rate/selected_count・                    │
│     reports/05-backtest.json 相当）                                │
│   honest 注記 st.warning:                                          │
│     「odds 正確性は JODDS取得完了後の再検証 subject」               │
│   行選択で展開: 馬別 selected/profit/payout                        │
│   st.download_button「Backtest CSV 出力（OUT-02・14列）」          │
│                                                                   │
│  ─ Segment Calibrationタブ（D-05 動的 Plotly）─                   │
│   segment 軸 selectbox（year/month/jyocd/entry_count/             │
│     ninki/odds_band・06-CONTEXT D-12 の6軸）                       │
│   Plotly curve 重ね描き（06-segments/<axis>.json を消費）          │
│   scalar 指標表 st.dataframe（ECE/MCE/calibration_max_dev・        │
│     06-CONTEXT D-11・reports/06-evaluation.json 相当）             │
└─────────────────────────────────────────────────────────────────┘
```

### Focal Point（メイン画面の視覚的アンカー・Dimension 2）
- **予測一覧タブにおける primary focal point = 選択レース内の推奨ランク S 行**（accent 色 `#FF4B4B`・最も注目度が高い単一要素）。ユーザーの視線は首先この細胞に収束する。その他のランク色・スタンプ・ボタンは S 行に対して従属する。

### 実装手段（D-01 Claude's Discretion → 確定）
- **multipage ではなく単一ページ + `st.tabs(3)`** — 3機能（予測/Backtest/Calibration）は同じ readonly データソースを参照し、切り替えコストが低い。multipage は `streamlit_app/pages/*.py` のファイル分割が必要で D-01 の「行選択で展開」状態をページ間で持ち運ぶ `st.session_state` 経路が増える（CLAUDE.md が `session_state` での派生データ保持を抑制）。タブであれば状態は同一実行コンテキスト。
- **マスター・ディテールは `st.dataframe(selection="single-row")` + 選択インデックスで下部展開** — Streamlit 1.58.0 の行選択 API を直接使用。expander は馬数が多いレースでネストが深くなるため不採用。
- **フィルタは `st.sidebar` に集約** — D-02 LOCKED。サイドバー外にフィルタを置かない（22,213 行を行単位で扱うため絞り込みは必須・常に可視）。

### DRY 共有定数（D-04 LOCKED）
- `src/ui/csv_columns.py`（新規）に `PREDICTION_CSV_COLUMNS`（20列）・`BACKTEST_CSV_COLUMNS`（14列）を定義。
- `src/ev/report.py::REPORT_COLUMNS`（LOW-05 presence assert パターン）と同思想・`src/model/predict.py::PREDICTION_COLUMNS` と `src/db/backtest_load.py::BACKTEST_COLUMNS` をソースとして参照し、UI/CLI/test で同一列を保証（CONTEXT code_context Established Patterns）。
- `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py`（新規 CLI・D-04）も同じ定数を import。

---

## Spacing Scale

Streamlit は8ptグリッドを内部採用しており、本プロジェクトも8pt倍数に従う。カスタム CSS は最小限（Streamlit ネイティブの縦方向 gap が主）で、明示的なスペーシングが必要な箇所（`st.markdown` 区切り・Plotly レイアウト margin・サイドバーグループ）のみ適用。

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | タブ内要素間の小ギャップ・Plotly annotation offset |
| sm | 8px | `st.metric` 横並び gap・サイドバーウィジェット間 |
| md | 16px | Streamlit 既定の要素間縦 gap（`st.vertical_gap` 既定値）・データフレームとボタン間 |
| lg | 24px | タブ主要セクション間・`st.tabs` パネル上部 |
| xl | 32px | サイドバーセクション区切り（`st.divider` 前後） |
| 2xl | 48px | 主要タブ境界（使用最小・Streamlit 既定で十分な場合は適用しない） |
| 3xl | 64px | 使用しない（Streamlit ページ長に依存・明示しない） |

**Exceptions:**
- **推奨ランク バッジ・スタンプ inline 表示** — `st.column_config` の cell 表現で padding は Streamlit 既定（明示 4px 未満の微調整はしない・ハック回避）。
- **モバイル対応** — 個人ローカル単一ユーザー・デスクトップブラウザ前提。タッチターゲット 44px 例外は不要（Streamlit ウィジェット既定サイズで十分）。

---

## Typography

Streamlit 既定フォント（system sans-serif）を使用。日本語表示は OS 既定（個人の Mac 環境）。weight は **2 値のみ** に圧縮する（Streamlit はテーマ上書きなしでは medium (500) / semibold (600) を確実に再現できない・宣言しても executor に誤った期待を持たせるだけのため）。

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body / Label | 14px / 13px（Body=Streamlit 既定・Label=サイドバーウィジェットラベル・`st.caption`） | regular (400) | 1.5（Label は 1.4） |
| Heading / Display | 20px / 28px（Heading=`st.subheader`・タブタイトル・h2 相当／Display=`st.title`・単一・ページ先頭のみ） | bold (700) | 1.2（Heading・Display 共通） |

**weight の適用規則（2 値のみ）:**
- **`regular (400)`** — Body・Label 兼用。13px と 14px のサイズ差で階層を表現する（weight を分けない）。Streamlit 既定ウィジェットラベルも 400 で十分。
- **`bold (700)`** — Heading・Display 兼用。20px（`st.subheader`）と 28px（`st.title`）のサイズ差で階層を表現する。`st.subheader`/`st.title` は Streamlit 既定レンダリング（bold 相当）を採用し、テーマで weight を上書きしない。
- **medium (500) / semibold (600) は宣言しない** — Streamlit テーマ上書きなしでは識別不能なため（本契約から削除）。

**その他の適用規則:**
- `st.title` はページ先頭1回のみ（"Keiba AI v3 — 複勝予測分析"）。
- `st.header`（h1・24px 相当）は使用しない（`st.title` で代用）。
- `st.subheader` で各タブのセクション見出し。
- `st.code`/`st.markdown` で再現性スタンプを等幅表示する場合のみ monospace（Streamlit 既定）を採用し、本文は sans-serif。
- **数値表記** — `p_fukusho_hit`/EV/odds は小数点以下3桁固定（例: `0.452`・`EV_lower=1.083`）。`st.column_config.NumberColumn(format="%.3f")` で統一。

---

## Color

Streamlit light theme を基調。`config.toml` で `primaryColor` のみ上書きし、それ以外は既定。色だけでなく**推奨ランクラベル（S/A/B/C/D）のテキスト**を併記し色弱配慮（二重化）。

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#FFFFFF`（Streamlit light 既定 background） | メインキャンバス背景・データフレーム背景 |
| Secondary (30%) | `#F0F2F6`（Streamlit 既定 secondary background） | サイドバー・`st.warning`/`st.info` 注記ボックス背景・データフレーム hover |
| Accent (10%) | `#FF4B4B`（Streamlit 既定 primaryColor・そのまま採用） | **下記 reserved-for のみ** |
| Destructive | `#C0392B` | **使用しない**（read-only・破壊的アクション存在しないため） |

**Accent reserved for:**
- `st.download_button`（CSV 出力ボタン・主要 CTA）
- `st.button` のうち「データ再読込（キャッシュクリア）」ボタンのみ
- 選択中の `st.dataframe` 行ハイライト（Streamlit 既定）
- 推奨ランク **S のみ** の色付け（`st.column_config` で `#FF4B4B` 系・最も注目度が高い）

**推奨ランク色分け（S 以外は accent ではなく categorical 色・Streamlit 既定 palette を優先）:**
| Rank | 色 | 備考 |
|------|----|----|
| S | `#FF4B4B`（accent） | EV≥1.20・最注目 |
| A | `#FF8C00`（オレンジ） | EV≥1.10 |
| B | `#F1C40F`（黄） | EV≥1.05 |
| C | `#7F8C8D`（灰） | EV≥1.00 |
| D | `#BDC3C7`（薄灰） | その他・非強調 |

**注記色:**
- honest 注記（backtest odds 再検証 subject）= `st.warning`（Streamlit 既定・黄系）。`st.error` は使用しない（エラーではなく前提注記のため）。

---

## Copywriting Contract

すべて日本語（CLAUDE.md 応答言語指示に準拠・UI 文言も日本語）。技術識別子・カラム名・スタンプキーは原文（snake_case・英数字）。

| Element | Copy |
|---------|------|
| Primary CTA | 「予測CSVをダウンロード」（予測タブ）／「Backtest CSVをダウンロード」（Backtest タブ） |
| Secondary CTA | 「データを再読込」（キャッシュクリア・`st.button`） |
| Page title | 「Keiba AI v3 — 複勝予測分析」 |
| Empty state heading（フィルタ結果0件） | 「表示対象のレースがありません」 |
| Empty state body | 「フィルタ条件（日付範囲・競馬場・推奨ランク）を確認してください。直近の予測日をデフォルト表示しています。」 |
| Empty state（segment JSON 未生成） | 「segment データが未生成です。`scripts/run_evaluation.py` を実行して `reports/06-segments/` を生成してください。」 |
| Error state（DB 接続失敗） | 「PostgreSQL（keiba_readonly ロール）に接続できません。`src/config/` の DSN と PostgreSQL 起動状態を確認してください。」 |
| Error state（snapshot/JSON 不整合） | 「再現性スタンプが欠落しています。この行は Phase 8（Adversarial Audit）の検証対象です。」（honest・fail-loud） |
| Honest 注記（backtest odds） | 「注意: この backtest の odds 正確性は JODDS オッズ取得完了後に再検証する subject です。現状の回収率は暫定値であり、確定後に入れ替わる可能性があります。」（CONTEXT specifics・Phase 5 manual-only 整合） |
| Honest 注記（推奨ランク） | 「推奨ランクは参考情報であり、購入判断を強制するものではありません（§19.3・実馬券購入はスコープ外）。」 |
| Reproducibility スタンプ表示ラベル | `odds_snapshot_policy` / `odds_snapshot_at` / `model_version` / `feature_snapshot_id` / `backtest_strategy_version`（原文・各予測行に inline） |
| 破壊的確認 | **該当なし**（read-only・破壊的アクション・削除・編集なし） |

**コピーライティング規則:**
- 「推奨」「的中」「勝ち」など確定ニュアンスの語は使わない（確率予測であることを常に明示）。
- 回収率・EV には常に「暫定」「参考」の修飾を付与（実馬券購入しない個人分析ツール・honest 表示）。
- `recommend_rank` は「推奨ランク」と表示（「買い」「的中」とは言わない）。

---

## Registry Safety

shadcn 非対象（Streamlit/Python）。サードパーティの Streamlit コンポーネントレジストリ（`streamlit-components` 等）も**使用しない**。Streamlit 公式組み込みコンポーネント + Plotly 公式パッケージ（`plotly>=6.8.0`・pyproject 既依存）のみ。

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| Streamlit 公式（組み込み） | `st.dataframe`/`st.sidebar`/`st.tabs`/`st.selectbox`/`st.multiselect`/`st.date_input`/`st.download_button`/`st.metric`/`st.warning`/`st.info`/`st.caption`/`st.column_config` | not required（公式組み込み・pip install 済み） |
| Plotly 公式 | `plotly.graph_objects.Figure` / `plotly.express`（D-05 動的 calibration curve 描画） | not required（公式・既依存・reports/06-segments と同一パッケージ） |
| サードパーティ Streamlit コンポーネント | なし | 該当なし（使用禁止・CLAUDE.md「keep it simple」・ローカル単一ユーザーで要件過剰） |
| shadcn / radix / base-ui | 該当なし | 該当なし（React 系ではない） |

**安全性担保:**
- **read-only 保証** — DB 接続は `keiba_readonly` ロール（GRANT 済み・schema 修飾 SELECT のみ・Phase 1 D-01）を `src/config/` 経由で使用。書き込み/DDL を発行するコードパスは UI 配下に存在しない（Phase 8 が対抗的監査で検証）。
- **外部ネットワークアクセス** — UI から外部 API/fetch を呼ばない（ローカル PostgreSQL + ローカル reports/ JSON のみ）。
- **eval/動的コード実行** — なし（宣言的 UI）。
- **`process.env` / 秘密情報** — `src/config/` の pydantic-settings が DSN を管理（既存パターン再利用）。UI コードに秘密をハードコードしない。

---

## Component Inventory（planner/executor 向け具体リスト）

| UI 要素 | Streamlit API | 備考 |
|---------|---------------|------|
| ページタイトル | `st.title` | 1回のみ |
| 主要フィルタ群 | `st.sidebar` + `st.date_input`/`st.multiselect`/`st.selectbox` | D-02・常に可視 |
| タブ切り替え | `st.tabs(["予測一覧", "Backtest", "Segment Calibration"])` | 3タブ固定 |
| レース一覧 | `st.dataframe(selection="single-row")` | D-01 マスター |
| 馬別展開 | `st.dataframe`（選択レース）+ `st.column_config.NumberColumn(format="%.3f")` | D-01 ディテール |
| 推奨ランク色分け | `st.column_config`（条件付き書式・S のみ accent） | 色弱配慮でラベル併記 |
| 再現性スタンプ inline | `st.columns(5)` + `st.caption`（5スタンプ）または dataframe 列 | §19.1 聖域 |
| CSV ダウンロード | `st.download_button`（mime="text/csv"） | D-04・`PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` 適用 |
| honest 注記 | `st.warning` | backtest odds 再検証 subject（必須） |
| セグメント軸切替 | `st.selectbox`（6軸・D-12） | D-05 |
| Plotly 動的描画 | `st.plotly_chart(fig, use_container_width=True)` | D-05・`reports/06-segments/<axis>.json` 消費 |
| scalar 指標表 | `st.dataframe`（ECE/MCE/calibration_max_dev） | D-11 |
| データソース注記 | `st.caption`（サイドバー下部） | readonly・stamped 明示 |
| メトリクス表示 | `st.metric`（recovery_rate/selected_count 等・Backtest タブ） | 任意・honest 注記と併記 |

---

## CSV Export Contract（OUT-01 / OUT-02・D-04 LOCKED）

### 予測CSV（OUT-01・20列・§16.2 pin）
`PREDICTION_CSV_COLUMNS`（`src/ui/csv_columns.py` で単一定数化）:
`race_id` / `race_date` / `race_start_datetime` / `競馬場` / `レース番号` / `horse_id` / `horse_name` / `枠番` / `馬番` / `p_fukusho_hit` / `fukusho_odds_lower` / `fukusho_odds_upper` / `EV_lower` / `EV_upper` / `recommend_rank` / `odds_snapshot_policy` / `odds_snapshot_at` / `model_version` / `feature_snapshot_id` / `prediction_created_at`

### Backtest CSV（OUT-02・14列・§16.2 pin）
`BACKTEST_CSV_COLUMNS`（同定数化）:
`backtest_id` / `backtest_strategy_version` / `train_period` / `validation_period` / `odds_snapshot_policy` / `race_id` / `horse_id` / `selected_flag` / `stake` / `refund_flag` / `payout_amount` / `profit` / `fukusho_hit_validated` / `recommend_rank` / `EV_lower` / `EV_upper`

> ※ OUT-02 は §16.2 で14列と定義されるが上記実体は16項目。CONTEXT.md D-04 注記の「14列」と実体の齟齬は planner が要件定義書 §16.2 原文と照合して確定すること（本 SPEC は表示項目過不足なしを契約・数は原典優先）。

**検証契約:**
- `src/ev/report.py::REPORT_COLUMNS` の LOW-05 presence assert パターンを再利用し、`PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` と §16.2 の 1:1 対応を unit test で機械検証（CONTEXT Claude's Discretion・テスト構成）。
- UI と CLI（`scripts/run_export_*.py`）は同一定数を import し列揺れを構造的に排除（D-04 DRY）。
- CSV 1行目ヘッダ・UTF-8 with BOM（Excel 互換・日本語馬名のため）・改行 CRLF。

---

## Interaction Contract

| 操作 | 期待動作 |
|------|----------|
| 日付範囲変更 | レース一覧が即時再フィルタ（`@st.cache_data` キャッシュヒット時 <1s） |
| 競馬場/ランク フィルタ変更 | 同上 |
| レース一覧の行選択 | 下部に馬別展開が即時表示（ページ遷移なし・D-01） |
| CSV ダウンロードボタン | 現在のフィルタ結果を UTF-8 BOM CSV でダウンロード・ファイル名 `predictions_<YYYYMMDD>.csv` / `backtest_<backtest_id>.csv` |
| セグメント軸切替 | Plotly curve が即時再描画（`reports/06-segments/<axis>.json` 読込・`@st.cache_data`） |
| データ再読込ボタン | `st.cache_data.clear()` → 全データ再取得（手動リフレッシュ・ライブ DB 更新後） |
| 既定ソート | 予測=race_date DESC（最新日優先）・馬別=p_fukusho_hit DESC（確率高い順） |
| レスポンス目安 | フィルタ/選択 <1s・CSV 生成 <3s（22,213 行規模） |

---

## Performance & Caching Contract

- **`@st.cache_data` 必須** — 全 DB SELECT・`reports/*.json` 読込に適用（CLAUDE.md 指示）。派生データは `st.session_state` に持たない（同指示）。
- **TTL** — DB クエリは TTL なし（手動リフレッシュのみ・read-only でデータ不変前提）。JSON 読込も TTL なし（reports/ は stamped・Phase 6 で生成済み）。
- **ページネーション** — レース一覧は日付範囲フィルタで制限（既定=直近N日・planner が決定・目安30日）。22,213 行を一度に描画しない。
- **Plotly** — `use_container_width=True`・`fig.show()` ではなく `st.plotly_chart`（Streamlit 埋込）。静的 HTML リンクは併設しない（D-05「HTML リンクのみ」は却下済み）。

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved (2026-06-24, revision iteration 1)
