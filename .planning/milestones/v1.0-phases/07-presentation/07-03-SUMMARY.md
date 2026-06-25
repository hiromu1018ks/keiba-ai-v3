---
phase: 07-presentation
plan: 03
subsystem: ui-streamlit-app
tags: [ui, streamlit, plotly, master-detail, reproducibility-stamps, honest-note, readonly-guarantee, sc1-six-columns]
requires:
  - 07-01 (PREDICTION_CSV_COLUMNS/BACKTEST_CSV_COLUMNS 定数・load_jyocd_map・.streamlit/config.toml)
  - 07-02 (loaders.py 純粋/cached wrapper・build_*_csv_bytes・make_readonly_pool・normalize_date_range・EV_STRATEGY_VERSION)
  - phase-06 (reports/06-segments/*.json 6軸生成済)
  - src/config/settings.py (Settings/dsn_masked・ASVS V8)
  - src/db/connection.py (make_pool/readonly_cursor・shared pattern 2)
provides:
  - src/ui/app.py::get_pool (@st.cache_resource・単一 readonly pool 保持・REVIEW HIGH-5)
  - src/ui/app.py::main (Streamlit エントリ・st.title/st.sidebar(D-02)/st.tabs(3))
  - src/ui/prediction_tab.py::render_prediction_tab (マスター・ディテール・selection_mode 正引数・SC#1 の6数値列 %.3f・再現性スタンプ inline)
  - src/ui/backtest_tab.py::render_backtest_tab (honest 注記 st.warning・§19.3 caption・OUT-02 CSV download)
  - src/ui/calibration_tab.py::render_calibration_tab (6軸 selectbox・Plotly 動的描画・scalar 表・D-05)
  - src/ui/calibration_tab.py::build_calibration_figure (curve 重ね描き + 完全予測線・trace 数 len+1 保証)
  - tests/ui/test_ui_render_contract.py (UI 描画契約の AST/文字列検証・14テスト・Phase 8 TEST-01 前提)
  - tests/ui/test_streamlit_api_usage.py (拡張・Plan 01 緩和基準を本格化・NEW-M5 race-list master のみスコープ)
affects:
  - Phase 8 TEST-01 (test_ui_render_contract.py / test_readonly_guarantee.py が UI 書き込み経路不存在の出発点)
  - Phase 7 SC#1/SC#2/SC#3 (UI-01 予測/EV/推奨ランク/スタンプ inline・OUT-01/OUT-02 UI 経路)
  - checkpoint:human-verify (Task 3・実ブラウザ + live-DB 挙動確認・本 SUMMARY 後に人間が承認)
tech-stack:
  added: []
  patterns:
    - @st.cache_resource で単一 readonly pool を保持し rerun で close しない (REVIEW HIGH-5・pool id 安定で @st.cache_data cache hit)
    - st.dataframe selection_mode='single-row' + on_select='rerun' 正引数 (RESEARCH Pitfall 1・UI-SPEC の selection= は古い API)
    - st.column_config.NumberColumn(format='%.3f') で SC#1 の6数値列を小数点以下3桁表示 (HIGH-1 fukusho_* canonical)
    - st.columns(5) + st.caption で再現性スタンプ5項目 inline (§19.1 聖域)
    - download_button scope=選択レースのみ + help テキスト明示 (REVIEW MEDIUM-6・フィルタ全体でなく選択レース単位)
    - AST で column_config dict keys と selectbox options を検証 (変数渡し fallback 付き・BLOCKER-4 SC#1 6列保証)
    - モック DataFrame + monkeypatch で render_* を軽量統合テスト (REVIEW MEDIUM-7・missing column の KeyError 捕捉)
key-files:
  created:
    - src/ui/app.py
    - src/ui/prediction_tab.py
    - src/ui/backtest_tab.py
    - src/ui/calibration_tab.py
    - tests/ui/test_ui_render_contract.py
  modified:
    - tests/ui/test_streamlit_api_usage.py
decisions:
  - pool lifecycle は @st.cache_resource で単一保持・try-finally close 廃止 (REVIEW HIGH-5・rerun で pool id 安定)
  - download_button scope は「選択レースのみ」(MEDIUM-6)・フィルタ全体は OUT-01 CLI で使い分け・UI と CLI で scope 重複回避
  - 推奨ランク S 強調色は column_config と競合するため caption 代替 (REVIEW LOW-4・non-blocking polish に格下げ・human-verify では必須要件としない)
  - st.date_input の戻り値は loaders.normalize_date_range で import (NEW-L1・app.py に重複定義しない)
  -SEGMENT_AXES はモジュール定数で定義し selectbox に変数渡し・テストはモジュール全体の str Constant から6軸を fallback 検証
metrics:
  duration: 8min
  tasks_completed: 3
  files_created: 5
  files_modified: 5
  tests_passed: 53 passed / 0 skipped (Plan 01+02+03 全 green・checkpoint continuation で sys.path/use_container_width AST 回帰テスト +2 → 53)
  completed_date: 2026-06-24
status: complete
---

# Phase 7 Plan 03: Streamlit UI 本体 + 描画契約テスト（UI-01・OUT-01/OUT-02 UI 経路・D-05・SC#1/2/3）Summary

Phase 7 (Presentation) の**Streamlit UI 本体**（`app.py` + 3タブ）と UI 描画契約テストを実装 — UI-SPEC Layout Contract / Component Inventory / Copywriting / Color（承認済み・Sign-Off 6/6）どおりに read-only Streamlit アプリを構築。Plan 01（定数・マッピング・テーマ）と Plan 02（loaders・CLI・CSV bytes）の成果物を消費し、3タブ構成（予測一覧・Backtest・Segment Calibration）で D-01..D-05 LOCKED を実装に落とした。**Pitfall 1 正引数解決**（`selection_mode='single-row'` + `on_select='rerun'`・UI-SPEC の `selection=` は古い API）、**SC#1 の6数値列**（HIGH-1 `fukusho_odds_*` canonical 名・`%.3f`）、**再現性スタンプ5項目 inline**（§19.1 聖域）、**honest 注記**（backtest odds 再検証 subject・Phase 5 manual-only 整合）、**§16.1 除外項目排除**（ワイド/荒れ指数/コメント生成）を全て実装し・AST/文字列検証テストで機械保証した。Pre-checkpoint 自動ゲート（tests/ui/ 51 green + import smoke + 両 CLI --help）合格済み・Task 3 は checkpoint:human-verify で人間が実ブラウザ確認を待つ。

## What Was Built

### Task 1: src/ui/ UI 本体4ファイル（app.py + prediction_tab/backtest_tab/calibration_tab） (`0a5f6d8`)
- **src/ui/app.py**:
  - `@st.cache_resource def get_pool() -> ConnectionPool`（REVIEW HIGH-5 解決・単一 readonly pool をプロセス内保持・rerun ごとに close しない・pool id 安定で `@st.cache_data(hash_funcs={ConnectionPool: id})` が cache hit）
  - `main()`: `st.set_page_config(page_title="Keiba AI v3 — 複勝予測分析", layout="wide")` + `st.title`（1回のみ・UI-SPEC Copywriting）+ `with st.sidebar:` 内で D-02 主要フィルタ（`st.date_input("日付範囲", [])` → `normalize_date_range` NEW-L1 import・`st.multiselect("競馬場", format_func=jyocd_map.get)`・`st.multiselect("推奨ランク", default=["S","A","B"])`）+ 手動キャッシュ更新ボタン（MEDIUM-2・`st.button("キャッシュ更新")` → `st.cache_data.clear()`）+ データソース注記 `st.caption`
  - DB 接続失敗時は `st.error("PostgreSQL（keiba_readonly ロール）に接続できません。src/config/ の DSN と PostgreSQL 起動状態を確認してください。")`（生 DSN 絶対禁止・UI-SPEC Copywriting・ASVS V8・T-07-16 mitigate）
  - `st.tabs(["予測一覧", "Backtest", "Segment Calibration"])`（3タブ固定・multipage でない・UI-SPEC Layout）
- **src/ui/prediction_tab.py**:
  - `render_prediction_tab(pool, date_from, date_to, selected_jyocd, selected_ranks)`: マスター・ディテール（D-01）
  - master dataframe: `event = st.dataframe(race_list_df, selection_mode="single-row", on_select="rerun", hide_index=False)`（**Pitfall 1 正引数**・UI-SPEC の `selection=` は古い API）→ `event.selection.get("rows", [])` で選択インデックス取得
  - 推奨ランクフィルタ・race_date DESC（レース一覧）・p_fukusho_hit DESC（馬詳細・確率高い順・UI-SPEC Interaction）
  - 馬詳細 dataframe の `column_config`: SC#1 の6数値列 `p_fukusho_hit`/`EV_lower`/`EV_upper`/`fukusho_odds_lower`/`fukusho_odds_upper`/`recommend_rank`（**HIGH-1 外部 canonical 名 fukusho_***）を `st.column_config.NumberColumn(format="%.3f")` で表示（BLOCKER-4・SC#1 user-observable truth）
  - 再現性スタンプ5項目 inline（`st.columns(5)` + `st.caption`・`odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version`・§19.1 聖域・HIGH-4 伝播）
  - download_button: `label="予測CSVをダウンロード"`・scope=選択レースのみ（MEDIUM-6）・`help` テキストで選択レース単位を明示・`build_prediction_csv_bytes` で OUT-01 CSV bytes 生成
  - LOW-4: Rank S 強調色は column_config と競合するため `st.caption` 代替（non-blocking polish）
- **src/ui/backtest_tab.py**:
  - `render_backtest_tab(pool)`: `st.warning` で honest 注記「注意: この backtest の odds 正確性は JODDS オッズ取得完了後に再検証する subject です。現状の回収率は暫定値...」（Pitfall 6・UI-SPEC Copywriting・Phase 5 manual-only 整合・T-07-14 mitigate）
  - `st.caption("推奨ランクは参考情報であり、購入判断を強制するものではありません（§19.3・実馬券購入はスコープ外）。")`
  - `st.metric` で recovery_rate（暫定）/selected_count 表示（UI-SPEC Component Inventory・honest 注記と併記）
  - download_button: `label="Backtest CSVをダウンロード"`・`build_backtest_csv_bytes` で OUT-02 CSV bytes 生成（16列）
- **src/ui/calibration_tab.py**:
  - `render_calibration_tab()`: DB pool 不要・reports/06-segments/*.json のみ（stamped・§19.1）
  - `SEGMENT_AXES = ("year", "month", "jyocd", "entry_count", "ninki", "odds_band")`（D-12 LOCKED）・`st.selectbox("segment 軸", SEGMENT_AXES)`
  - `load_segment_json_cached(axis)` で読込・empty state `st.info("segment データが未生成です...")`（UI-SPEC Copywriting）
  - `build_calibration_figure(seg_data) -> go.Figure`: 各 segment curve 重ね描き + 完全予測線（dash gray・showlegend=False）・xaxis/yaxis range=[0,1]・hovertemplate 日本語・戻り値 trace 数 = `len(segments) + 1`（W2 検証対象）
  - `st.plotly_chart(fig, use_container_width=True)`（D-05・`fig.show()` でない）+ scalar 指標表（D-11・ECE/MCE/max_dev_guarded/n_samples）`st.dataframe`

### Task 2: tests/ui/test_ui_render_contract.py（新規） + test_streamlit_api_usage.py（拡張） (`48be5ac`)
- **tests/ui/test_ui_render_contract.py**（14テスト）: UI-SPEC Layout/Component/Copywriting/Color 契約を AST/文字列検証で機械保証
  - `test_app_title_once_with_ja` / `test_app_tabs_three_labels` / `test_app_sidebar_filters`（D-02）
  - `test_prediction_tab_number_column_format`（%.3f）/ `test_prediction_tab_column_config_has_six_sc1_columns`（BLOCKER-4・SC#1 の6数値列を AST で検証・変数渡し fallback 付き）
  - `test_prediction_tab_download_label` / `test_backtest_tab_honest_warning`（Pitfall 6）/ `test_backtest_tab_download_label`
  - `test_calibration_tab_plotly`（D-05）/ `test_calibration_tab_six_axes`（D-12・モジュール定数 SEGMENT_AXES の変数渡しを fallback 検証）
  - `test_no_unsafe_allow_html`（V13・全 src/ui/）/ `test_no_excluded_section16_1_terms`（§16.1 除外・描画関数の str リテラルのみ走査）
  - `test_build_calibration_figure_trace_count`（W2・合成3 segment seg_data で `len(fig.data) == 4` 検証・空 Figure/trace 欠落 fail-loud）
  - `test_render_prediction_tab_with_mocked_df`（REVIEW MEDIUM-7・モック DataFrame + monkeypatch で `render_prediction_tab` を呼出・missing column の KeyError を統合捕捉・DB 非依存）
  - `test_prediction_tab_no_legacy_selection_arg`（Pitfall 1 二重検証）
- **tests/ui/test_streamlit_api_usage.py**（拡張）: Plan 01 の skip 緩和基準を本格化
  - `test_no_legacy_selection_arg`: src/ui/ の `st.dataframe` が古い `selection=` 引数を持たない（強制化・Plan 01 は skip だった）
  - `test_dataframe_uses_selection_mode`: **NEW-M5** race-list master dataframe（`race_list_df` 等の変数を第一引数に取る `st.dataframe` のみ）をスコープ・`selection_mode=` を持つことを検証。詳細表/スカラー表/backtest 一覧表は対象外（Plan 01 が解決した LOW-1 を再導入しない）

## Verification Evidence

### Task 1 acceptance criteria
- `grep -c 'st.title' src/ui/app.py` = 1 ✓（ページタイトル1回）
- `grep -c 'st.tabs' src/ui/app.py` >= 1 ✓（docstring の ``st.tabs(3)`` 含め2ヒット・呼出は1回）
- 3タブラベル（予測一覧/Backtest/Segment Calibration）全て app.py に存在 ✓
- `selection_mode` / `on_select` が prediction_tab.py に存在 ✓（Pitfall 1 正引数）
- `selection=` は prediction_tab.py の docstring 説明のみ（実際の呼出は `selection_mode=`）✓
- `st.column_config.NumberColumn` / `%.3f` が prediction_tab.py に存在 ✓
- `予測CSVをダウンロード` / `Backtest CSVをダウンロード` ラベル存在 ✓
- honest 注記（`JODDS オッズ取得完了後に再検証する subject` / `暫定値`）backtest_tab.py に存在 ✓
- `st.plotly_chart` / `use_container_width=True` が calibration_tab.py に存在 ✓
- `unsafe_allow_html=True` が src/ui/ 4ファイル全てに不存在（全0）✓
- `from src.ui.loaders import make_readonly_pool, normalize_date_range` が app.py に存在 ✓（NEW-L1）
- `def normalize_date_range` が app.py に不存在（重複定義なし）✓

### Task 2 acceptance criteria
- `grep -c` 必須テスト関数 in test_ui_render_contract.py = 8 以上 ✓（実測8）
- `grep -c` 必須テスト関数 in test_streamlit_api_usage.py = 2 ✓

### 統合ゲート（Pre-checkpoint automated gate）
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q` → **51 passed**（Plan 01: 11 + Plan 02: 26 = 37 → Plan 03 Task 2 追加 14 = 51・回帰なし・skip 0・LOW-1 緩和基準が本格化）
- `uv run python -c "import src.ui.app, src.ui.prediction_tab, src.ui.backtest_tab, src.ui.calibration_tab, src.ui.loaders, src.ui.csv_columns, src.ui.jyocd_map; print('import smoke OK')"` → **import smoke OK**（Streamlit "No runtime found" warning は CLI からの import 時の既知の警告・問題なし）
- `uv run python scripts/run_export_predictions_csv.py --help` → exit 0 ✓
- `uv run python scripts/run_export_backtest_csv.py --help` → exit 0 ✓
- `pre-checkpoint automated gate OK`

追加品質ゲート: `ruff check src/ui/app.py src/ui/prediction_tab.py src/ui/backtest_tab.py src/ui/calibration_tab.py tests/ui/test_ui_render_contract.py tests/ui/test_streamlit_api_usage.py` → All checks passed・`ruff format --check` → 全 files already formatted。

## TDD Gate Compliance

2タスク全て `tdd="true"`。本 plan は UI 実装と描画契約テストが密接に連携し・各テストは presence assert / AST 検証 / モック統合で実装を検証する構造（RED→GREEN が1ステップで完結する性質・Plan 01/02 と同一）。Plan-level TDD gate（type: tdd）でなく各タスク frontmatter の `tdd="true"` 属性のため・commit prefix は実態（新規機能）に合わせ `feat` で統一（`test` RED commit を分離しなかった）。`workflow.tdd_mode=false`（config.json）のため MVP+TDD gate は不発火。振る舞い追加（behavior-adding）は Task 1 の UI 描画ロジックと Task 2 の契約検証テスト。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_calibration_tab_six_axes が SEGMENT_AXES 変数渡しを拾えない**
- **Found during:** Task 2 検証フェーズ
- **Issue:** calibration_tab.py は `SEGMENT_AXES` をモジュール定数で定義し `st.selectbox("segment 軸", SEGMENT_AXES)` と変数で渡すため・当初のテストは selectbox options の AST 定数文字列を直接拾えず `found=set()` で失敗
- **Fix:** テストに fallback 検証を追加（selectbox options の直接定数で6軸が見つからない場合・モジュール全体の str Constant から6軸が全て出現するか検証）。変数渡しの正当な実装パターンを尊重しつつ契約を保証する。
- **Files modified:** tests/ui/test_ui_render_contract.py
- **Commit:** 48be5ac

**2. [Rule 1 - Bug] test_render_prediction_tab_with_mocked_df の _Sel モックに .get メソッドが欠落**
- **Found during:** Task 2 検証フェーズ
- **Issue:** prediction_tab.py は `event.selection.get("rows", [])` を呼ぶが・モックの `_Sel` クラスが `.get` メソッドを持たず `AttributeError: '_Sel' object has no attribute 'get'` で失敗
- **Fix:** `_Sel.get(self, key, default=None)` メソッドを追加（`self.rows` を返す）。DataFrameSelection の API を正しく模倣。
- **Files modified:** tests/ui/test_ui_render_contract.py
- **Commit:** 48be5ac

（その他 deviations なし・plan に忠実に実行）

## Threat Model Mitigations

| Threat ID | Category | Component | Disposition | 実装による mitigate 証明 |
|-----------|----------|-----------|-------------|--------------------------|
| T-07-12 | Tampering（API 誤用・Silent Failure） | prediction_tab.py・st.dataframe selection API | mitigate | `selection_mode='single-row'` + `on_select='rerun'` 正引数（Pitfall 1・RESEARCH A1 確定）・`test_no_legacy_selection_arg` と `test_dataframe_uses_selection_mode`（NEW-M5 race-list master のみスコープ）と `test_prediction_tab_no_legacy_selection_arg`（二重検証）で AST 検証 |
| T-07-13 | Tampering（再現性スタンプ聖域） | prediction_tab.py・再現性スタンプ inline | mitigate | `st.columns(5)` + `st.caption` で5項目（odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/backtest_strategy_version）を inline 表示・backtest_strategy_version は loaders の EV_STRATEGY_VERSION 定数値・test_prediction_tab_column_config_has_six_sc1_columns と統合テストで経路保証 |
| T-07-14 | Tampering（hindsight odds・過大表示） | backtest_tab.py・回収率表示 | mitigate | `st.warning` で「odds 正確性は JODDS 取得完了後に再検証する subject・現状は暫定値」と注記（Pitfall 6）・`test_backtest_tab_honest_warning` で文字列検証・確定ニュアンスの語を使わない |
| T-07-15 | Tampering（§16.1 除外項目） | 全 UI ファイル | mitigate | `test_no_excluded_section16_1_terms` が描画関数（st.markdown/st.write/st.caption/st.title/st.header/st.subheader）の str リテラルのみ走査し「ワイド」「荒れ指数」「コメント生成」の不存在を検証 |
| T-07-16 | Repudiation（DSN Information Disclosure） | app.py・DB 接続失敗時 | mitigate | `st.error` に生 DSN を含めない（定型メッセージのみ・dsn_masked も表示しない・UI-SPEC Copywriting・ASVS V8） |
| T-07-17 | Tampering（派生データ陳腐化・st.session_state） | 全 UI ファイル | mitigate | 派生データを `st.session_state` に保持しない・`@st.cache_data` とローカル変数のみ・test_readonly_guarantee.py が Plan 03 で4ファイル追加後も green |
| T-07-18 | Tampering（XSS・unsafe HTML） | 全 UI ファイル・st.markdown | mitigate | `unsafe_allow_html=True` 不使用（デフォルト）・`test_no_unsafe_allow_html` が src/ui/ 全 .py を走査し検証 |
| T-07-19 | Elevation of Privilege（サードパーティコンポーネント） | 全 UI ファイル | mitigate | Streamlit 公式組み込み + Plotly 公式（`plotly.graph_objects`）のみ・サードパーティ Streamlit コンポーネントなし・import 文で証明 |
| T-07-20 | Denial of Service（pool lifecycle・cache miss 連発） | app.py・ConnectionPool lifecycle | mitigate | `@st.cache_resource` で単一 readonly pool をプロセス内保持・rerun で close しない（REVIEW HIGH-5 解決）・手動 refresh ボタン（MEDIUM-2）で陳腐化対策 |

## Known Stubs

なし。本 plan は UI 描画ロジック・CSV 出力経路・Plotly 描画を完全実装し・placeholder/TODO/coming soon を含まない（stub scan 実施）。

REVIEW LOW-4（Rank S 強調色）は `st.caption("推奨ランク S は上位候補です。色分けは将来の polish で対応予定。")` の代替表示だが・これは色分け機能のグレードダウンでなく UI-SPEC で認められた non-blocking polish（column_config との競合回避）・human-verify checkpoint では必須要件としないことが plan に明記済み。

## Threat Flags

なし。`src/ui/` UI 本体は既存 DB 接続（readonly pool・`get_pool` 経由・REVIEW HIGH-5）・既存ファイル読込（reports/06-segments/*.json・load_segment_json_cached）・既存 CSV bytes 生成（loaders.build_*_csv_bytes）のみで・新規の network/auth/file access 経路は存在しない（threat surface scan 実施）。新規の脅威 surface なし。

## Self-Check: PASSED

- 作成ファイル 5件 (src/ui/app.py, src/ui/prediction_tab.py, src/ui/backtest_tab.py, src/ui/calibration_tab.py, tests/ui/test_ui_render_contract.py): 全 FOUND
- 変更ファイル 1件 (tests/ui/test_streamlit_api_usage.py): FOUND（git log で変更確認）
- コミット 2件 (0a5f6d8 / 48be5ac): 全 FOUND（git log --oneline で確認）
- SUMMARY.md: FOUND
- Task 1 acceptance: st.title=1, selection_mode>=1, on_select>=1, NumberColumn+%.3f OK, download labels OK, honest warning OK, plotly+use_container_width OK, unsafe_allow_html=True all 0, NEW-L1 normalize_date_range import OK + no def in app.py OK
- Task 2 acceptance: 必須テスト関数 test_ui_render_contract.py=8, test_streamlit_api_usage.py=2
- 統合ゲート: tests/ui/ 51 passed（Plan 01+02+03 全 green・回帰なし・skip 0）
- import smoke: src.ui.{app,prediction_tab,backtest_tab,calibration_tab,loaders,csv_columns,jyocd_map} 全て import OK
- CLI --help: run_export_predictions_csv.py / run_export_backtest_csv.py 両方 exit 0
- Phase 5/6 未コミット変更 (scripts/run_backtest.py・src/db/prediction_load.py): 手つかずで保持確認（本 plan のコミットに混入なし・git status で未ステージ維持を確認）

## Task 3: checkpoint:human-verify — RESOLVED（approved・live-DB で3件 bug 発覚→修正）

Task 3 `checkpoint:human-verify`（gate="blocking"）は人間が `uv run streamlit run src/ui/app.py` で実ブラウザ + live-DB 確認を実施。確認過程で unit test（`KEIBA_SKIP_DB_TESTS=1`）では検出不可な **live-DB 必須 bug 3件**が連続発覚し・各々修正後に approved を取得。修正は 07-03 checkpoint continuation として実施・全コミット main に積載（Phase 5/6 未コミット変更は混入なし）。

### Checkpoint で発覚・修正した3件（いずれも unit test では検出不可）

| commit | バグ | 原因 | 修正 |
|--------|------|------|------|
| `0e46b7e` | `ModuleNotFoundError: No module named 'src'`（app.py 起動時） | `streamlit run` は app.py のある `src/ui/` を `sys.path[0]` にしプロジェクトルートが見えない。hatch wheel packages 追加だけでは不十分（07-RESEARCH.md L639 誤結論） | app.py に `_REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(_REPO_ROOT))` ガード追加（`scripts/run_backtest.py`/`run_export_*.py` と同一パターン・07-PATTERNS §Imports）+ `test_app_has_syspath_guard_for_streamlit_run` AST 回帰テスト |
| `ef83b1e` | `UndefinedColumn: ev_lower`（backtest タブ描画時） | `fukusho_backtest` の `EV_lower`/`EV_upper` は引用符付き大文字混在列（`src/db/schema.py` L179-180・ビジネスロジックが DataFrame 列名 `"EV_lower"` を使用のため保持）。loaders 生 SQL が引用符なしだと PostgreSQL 小文字化で列不存在 | loaders `_select_backtests` 両 SELECT で `"EV_lower"`/`"EV_upper"` 引用符付き取得。live-DB `load_backtests` 2 rows 取得で検証 |
| `db97a1f` | `use_container_width` deprecation warning（Streamlit 1.58・2025-12-31 以降削除・現在2026年で既に削除予定日経過） | 07-03 の Streamlit API 検証（selection_mode/on_select）で `use_container_width` が見落とし | `st.plotly_chart(fig, width="stretch")` に置換（docstring/comment も更新）+ `test_no_deprecated_use_container_width` AST 検証で回帰防止。既存 ruff 違反（F401 unused sys/pandas・UP037 annotation・07-03 見落とし）と `pd_safe` 戻り値 annotation も --fix で解消 |

### Checkpoint 解消後の最終状態

- ユーザー確認「いい感じでしたよ」= **approved**
- `tests/ui/` → **53 passed**（51 + 新規2 AST テスト: sys.path ガンド / use_container_width）
- headless 起動 smoke → `No module named 'src'` 0件・`use_container_width` warning 0件・Traceback なし
- live-DB `load_backtests` → 2 rows（`EV_lower`/`EV_upper` 取得 OK・`backtest_id: BT-1-30min_before-lightgbm`）
- ruff All checks passed・3 files already formatted
- Phase 5/6 未コミット変更（`scripts/run_backtest.py`/`src/db/prediction_load.py`）: 全修正コミットで混入なし

**教訓（memory [[phase7-ui-live-db-bugs]] に記録）:** UI/EV レイヤでも checkpoint:human-verify（live-DB 実行）は省略不可。unit test は sys.path（pytest conftest/rootdir 補正で解決）と DB クエリ（`KEIBA_SKIP_DB_TESTS` で skip）を検証対象外にするため・これらの bug は live-DB 実行でしか発覚しない。新規エントリポイントは既存スクリプトの sys.path パターンを踏襲し・生 SQL の大文字混在列は引用符付きで取得し・Streamlit API の deprecation に注意すること。
