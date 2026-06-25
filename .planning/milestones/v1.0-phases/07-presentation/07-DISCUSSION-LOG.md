# Phase 7: Presentation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 7-Presentation
**Areas discussed:** 画面構成・レイアウト, データ読込元, CSV出力の起点, segment calibration 可視化

---

## 画面構成・レイアウト

### Q1: Streamlit の画面構成方式

| Option | Description | Selected |
|--------|-------------|----------|
| マスター・ディテール（推奨） | レース一覧を行選択すると各馬（p/EV/推奨ランク）を展開/別ページ遷移。「日→レース→馬」階層が自然 | ✓ |
| 単一テーブル（全馬一覧） | 全レース全馬を1テーブルで一覧・フィルタ/ソートで絞り込み。実装最も単純・§16.1 最小画面に最忠実 | |
| multipage（ページ分離） | Streamlit multipage app でページ分離。将来拡張余地大だが実装量多め・Phase 1 最小画面としては過剰 | |
| Claude判断に委ねる | researcher/planner が§16.1 + Streamlit 慣例で決定 | |

**User's choice:** マスター・ディテール（推奨）
**Notes:** 競馬データの「日→レース→馬」階層に適合。22,213行を行単位で扱うため階層化が有効。

### Q2: フィルタ・デフォルト並び

| Option | Description | Selected |
|--------|-------------|----------|
| 主要フィルタ付き（推奨） | サイドバーに 日付範囲・競馬場(jyocd)・推奨ランク(S/A/B/C/D)。デフォルト最新日 or EV高順 | ✓ |
| フィルタ最小限（検索のみ） | 日付 or race_id 検索のみ。§16.1 最小画面重視 | |
| Claude判断に委ねる | フィルタ軸を実データ分布と Streamlit 標準 widget で決定 | |

**User's choice:** 主要フィルタ付き（推奨）
**Notes:** 22,213行の予測を行単位で扱うなら絞り込みは実質必須。

---

## データ読込元

| Option | Description | Selected |
|--------|-------------|----------|
| ハイブリッド（推奨） | 行データ(UI/CSV の主)は live PostgreSQL SELECT[is_primary絞り]・集計(calibration 等)は reports/06-*.json 消費 | ✓ |
| live PostgreSQL 一本 | 行データも集計も全て live DB。常に最新・単一ソースだが calibration 集計は DB 未保存で再計算/保存が必要 | |
| reports/ 成果物が主 | reports/ の JSON/Parquet/stamped 成果物を主に読む。再現性スタンプ固定だが行データも別途 export 必要 | |

**User's choice:** ハイブリッド（推奨）
**Notes:** 行データ（DB）と集計（stamped JSON）の性質の違いに適合。`@st.cache_data` でキャッシュ。prediction は is_primary=true（LightGBM）で主モデル絞り・schema 修飾 SELECT GRANT 済み。

---

## CSV 出力の起点

| Option | Description | Selected |
|--------|-------------|----------|
| 両方（UI + CLI）（推奨） | UI の st.download_button + scripts/run_export_*.py CLI の両方。列定義は単一定数で DRY 共有 | ✓ |
| Streamlit download のみ | UI のダウンロードボタンのみ。最小実装だが CI/バッチ stamped export が別途必要 | |
| CLI のみ | scripts/run_export_*.py のみ。バッチ再現性重視だが UI ユーザが都度 export 不可 | |
| Claude判断に委ねる | UI/CLI 配分・列定数共有方法を実装慣例で決定 | |

**User's choice:** 両方（UI + CLI）（推奨）
**Notes:** OUT-01(予測20列)/OUT-02(backtest14列) は§16.2 pin 済み。列定義を `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` 単一定数で UI/CLI/test 共有（DRY）。既存 scripts/run_*.py 慣例に整合。

---

## segment calibration 可視化

| Option | Description | Selected |
|--------|-------------|----------|
| 動的 Plotly 描画（推奨） | reports/06-segments/*.json を消費し segment(year/競馬場/頭数/人気帯/オッズ帯)切替の動的 calibration curve を Plotly 描画 | ✓ |
| 最小画面のみ（載せない） | §16.1/UI-01 列挙項目に徹し calibration curve は reports/06-segments/*.html の静的 HTML で別途確認 | |
| 既存HTMLのリンク/埋め込みのみ | UI 上に reports/06-segments/ HTML へのリンク or 埋め込み（動的描画なし） | |
| Claude判断に委ねる | §16.1 厳格解釈 vs Phase 6 D-10 期待の天秤を委ねる | |

**User's choice:** 動的 Plotly 描画（推奨）
**Notes:** §16.1/UI-01 列挙には含まれないが、本プロジェクトは確率品質（Calibration）の吟味が主目的の個人分析ツール（実馬券購入しない）であり、Phase 6 が JSON を「Phase 7 消費・動的描画」前提で生成した（D-10）ため採用。curve 重ね描き + scalar 表併記（06-CONTEXT D-11/D-12 踏襲）。

---

## Claude's Discretion

- `streamlit` 依存追加（pyproject.toml に未追加・CLAUDE.md 推奨 1.58.0）
- ディレクトリ構成（`src/ui/` vs `streamlit_app/`[§17.2 提案]・実コード src/ レイアウト整合）
- read-only 保証（`keiba_readonly` ロール・GRANT 済み・schema 修飾 SELECT・書き込みなし）
- キャッシュ戦略（`@st.cache_data`・TTL/無効化）
- マスター・ディテールの Streamlit 実装手段（expanders / query params / multipage）・フィルタ widget 詳細・デフォルトソート
- テスト構成（§17.3・CSV 列定数 presence assert[LOW-05 再利用]・read-only assert・Streamlit E2E は最小）
- segment 動的描画の Plotly レイアウト（curve 重ね描き/凡例/色・scalar 表併記形式）
- backtest 表示の honest 注記（odds 正確性は JODDS取得後再検証 subject）
- レース一覧の補助情報（競馬場名・レース番号・馬名等の取得経路）

## Deferred Ideas

- Phase 8（Adversarial Audit）: UI/CSV のリーク防止テスト・再現性スタンプ inline 検証・read-only 保証の対抗的監査（TEST-01）
- PHASE2-05（将来・Streamlit 表示拡張）: ワイド候補・ワイド期待値・荒れ指数・コメント生成の UI 追加
- ワイド/三連複モデル対応 UI（PHASE2/PHASE3）
- MLflow/Optuna 連携 UI（OPS-01/02・§21 defer）
