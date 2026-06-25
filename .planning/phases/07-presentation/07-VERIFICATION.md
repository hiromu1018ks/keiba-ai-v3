---
phase: 07-presentation
verified: 2026-06-24T21:30:00Z
status: human_needed
score: 16/16 must-haves verified
behavior_unverified: 2 # ライブDB/ブラウザ描画振る舞い（grep/AST不可視）
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "KEIBA_SKIP_DB_TESTS=0 で実DB接続し streamlit run src/ui/app.py を起動・予測一覧タブでレース1行選択"
    expected: "下部に各馬の p_fukusho_hit/EV_lower/EV_upper/fukusho_odds_lower/upper/recommend_rank 6数値（%.3f）と再現性スタンプ5項目の inline 表示が展開される"
    why_human: "Unit test は KEIBA_SKIP_DB_TESTS=1 でDB未接続・selection_mode/on_select の実ブラウザ挙動と実データ描画は grep/AST で検証不可（07-03 checkpoint:human-verify RESOLVED 済だが回帰監視として残存）"
  - test: "Segment Calibration タブで6軸（year/month/jyocd/entry_count/ninki/odds_band）を切替"
    expected: "Plotly calibration curve が幅 stretch で重ね描きされ・scalar 表（ECE/MCE/max_dev_guarded/n_samples）が併記される"
    why_human: "Plotly Figure 構築は検証済だが・実 JSON 読込時の描画振る舞いと幅 stretch レンダリングはブラウザ目視が必要"
---

# Phase 7: Presentation 検証レポート

**Phase ゴール:** ユーザーが read-only Streamlit UI と再現可能な CSV 出力で・予測・EV・推奨・backtest 結果を確認できること。全再現性スタンプが inline 表示されること。
**検証日時:** 2026-06-24T21:30:00Z
**状態:** human_needed
**再検証:** No — 初回検証

## ゴール達成

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | PREDICTION_CSV_COLUMNS は20列・§16.2 原典と1:1 | ✓ VERIFIED | `src/ui/csv_columns.py` 実行検証: PREDICTION=20・BACKTEST=16。test_csv_export.py::test_prediction_csv_header_matches_columns で契約検証 |
| 2 | BACKTEST_CSV_COLUMNS は16列（「14列」は誤記） | ✓ VERIFIED | 実行検証 len(BACKTEST_CSV_COLUMNS)==16。test_backtest_csv_header_16_columns が二重保証 |
| 3 | 再現性スタンプ5項目が PREDICTION_CSV_COLUMNS（4項目+created_at）とUI行表示（5項目）に過不足なく含まれる | ✓ VERIFIED | PREDICTION含 odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/prediction_created_at・REPRODUCIBILITY_STAMPS(5)は backtest_strategy_version 含む |
| 4 | streamlit==1.58.0 が uv add 済み・import 成功 | ✓ VERIFIED | pyproject.toml L26 `"streamlit==1.58.0"`・packages=["src/config","src/db","src/ui"]・53 tests pass |
| 5 | hatch wheel packages に src/ui 追加・from src.ui.csv_columns import 成功 | ✓ VERIFIED | pyproject.toml L34・全テスト import 成功 |
| 6 | jyocd→競馬場名が code_tables.yaml から PyYAML 読込・UIハードコードなし | ✓ VERIFIED | src/ui/jyocd_map.py::load_jyocd_map が yaml.safe_load・src/ui 配下に dict ハードコード不存在 |
| 7 | .streamlit/config.toml が [theme] base='light' primaryColor='#FF4B4B' | ✓ VERIFIED | config.toml 直接確認・UI-SPEC Color Contract 準拠 |
| 8 | test_readonly_guarantee.py が src/ui 配下の書込み/DDL SQL キーワード不存在を検証 | ✓ VERIFIED | test_ui_has_no_write_ddl_sql / test_ui_uses_only_readonly_pool 存在・スキャンでも実コード違反なし（docstring言及のみ） |
| 9 | run_export_predictions_csv.py が UTF-8 BOM+CRLF CSV を生成・ヘッダ20列完全一致 | ✓ VERIFIED | build_prediction_csv_bytes が to_csv(encoding="utf-8-sig", lineterminator="\r\n")・test_prediction_csv_bom_crlf/header_matches_columns pass |
| 10 | run_export_backtest_csv.py が UTF-8 BOM+CRLF CSV を生成・ヘッダ16列完全一致 | ✓ VERIFIED | build_backtest_csv_bytes 同実装・test_backtest_csv_header_16_columns pass |
| 11 | OUT-01 odds/EV/rank は JODDS snapshot + compute_ev_and_rank 再計算経路（backtest JOIN 不可能） | ✓ VERIFIED | loaders.py L388 select_odds_snapshot(policy)・L419 compute_ev_and_rank(merged)・docstring L7-31 で正経路明記・backtest BACKTEST_COLUMNS に odds 値カラム不存在 |
| 12 | OUT-01 EV_lower/EV_upper/recommend_rank は compute_ev_and_rank 純粋関数で算出 | ✓ VERIFIED | src/ev/ev_rank.py::compute_ev_and_rank import・merged = compute_ev_and_rank(merged) |
| 13 | OUT-01 odds_snapshot_at は select_odds_snapshot 戻り値の happyo_datetime・policy は CLI/UI 固定引数 | ✓ VERIFIED | loaders L380-388・run_export_predictions_csv.py --odds-snapshot-policy flag（default 30min_before） |
| 14 | CLI と UI が同一の loaders と csv_columns を import・列揺れ構造的排除 | ✓ VERIFIED | run_export_*.py が from src.ui.csv_columns/loaders import・app.py/prediction_tab.py/backtest_tab.py も同一 |
| 15 | loaders/CLI が keiba_readonly ロールのみ・write_cursor/etl 経路なし・SQL は parameterized | ✓ VERIFIED | make_readonly_pool = make_pool(role="readonly")・cur.execute(sql, params)・test_loaders_readonly.py pass |
| 16 | CSV 生成前に列存在検証・欠落時 raise ValueError（python -O でも無効化されない） | ✓ VERIFIED | build_*_csv_bytes: missing=[...]→raise ValueError・test_prediction_csv_missing_column_asserts pass |
| 17 | prediction SELECT が WHERE is_primary = true を含む（主モデル=LightGBM 絞り） | ✓ VERIFIED | loaders.py L196 where_clauses=["is_primary = true"] |
| 18 | logger.info は settings.dsn_masked のみ（生DSN絶対禁止） | ✓ VERIFIED | run_export_*.py logger.info("readonly DSN: %s", settings.dsn_masked) |
| 19 | streamlit run src/ui/app.py が起動・ページタイトル「Keiba AI v3 — 複勝予測分析」 | ✓ VERIFIED | app.py st.title + sys.path guard（commit 0e46b7e 追加）・test_app_title_once_with_ja pass |
| 20 | 3タブ st.tabs(['予測一覧','Backtest','Segment Calibration']) | ✓ VERIFIED | app.py st.tabs 3ラベル・test_app_tabs_three_labels pass |
| 21 | 予測一覧 st.dataframe が selection_mode='single-row' + on_select='rerun'（正引数・Pitfall 1） | ✓ VERIFIED | prediction_tab.py L155-156・test_no_legacy_selection_arg pass |
| 22 | 各馬詳細 NumberColumn(format='%.3f') で6数値列表示 | ✓ VERIFIED | _build_column_config・test_prediction_tab_column_config_has_six_sc1_columns pass |
| 23 | 選択レース各馬行に6数値（p_fukusho_hit/EV_lower/EV_upper/fukusho_odds_lower/upper/recommend_rank）表示 | ✓ VERIFIED | prediction_tab.py render・SC#1 truth・fukusho_* 外部 canonical 名 |
| 24 | 再現性スタンプ5項目が選択レース予測行に inline 表示 | ✓ VERIFIED | prediction_tab.py st.columns(len(REPRODUCIBILITY_STAMPS))+st.caption loop・REPRODUCIBILITY_STAMPS(5) |
| 25 | st.sidebar に日付範囲・競馬場・推奨ランクフィルタ（D-02） | ✓ VERIFIED | app.py st.sidebar・test_app_sidebar_filters pass |
| 26 | Backtest タブ st.warning で honest 注記（JODDS 再検証 subject・暫定値） | ✓ VERIFIED | backtest_tab.py L74 st.warning・test で文字列検証 |
| 27 | Backtest タブ st.caption で「推奨ランクは参考情報（§19.3）」honest 注記 | ✓ VERIFIED | backtest_tab.py L78 st.caption |
| 28 | 予測/Backtest 各タブに download_button（D-04） | ✓ VERIFIED | prediction_tab L189・backtest_tab L104・test_prediction_tab_download_label pass |
| 29 | Segment Calibration タブ: 6軸 selectbox + st.plotly_chart(width="stretch")（D-05・commit db97a1f） | ✓ VERIFIED | calibration_tab.py L95 st.selectbox(SEGMENT_AXES 6軸)・L107 st.plotly_chart(fig, width="stretch") |
| 30 | Segment Calibration scalar 指標表（ECE/MCE/max_dev_guarded/n_samples・D-11） | ✓ VERIFIED | calibration_tab.py L109-117 scalar_rows 構築・st.dataframe |
| 31 | Segment JSON 未生成時 st.info empty state | ✓ VERIFIED | calibration_tab.py L99-102 st.info |
| 32 | レース一覧デフォルトソート race_date DESC・馬詳細 p_fukusho_hit DESC | ✓ VERIFIED | prediction_tab.py sort 処理（UI-SPEC Interaction Contract） |
| 33 | DB接続失敗時 st.error 定型メッセージ（生DSN絶対禁止） | ✓ VERIFIED | app.py except 節 st.error・dsn_masked も表示しない（UI-SPEC Copywriting） |
| 34 | src/ui 配下に書込み/DDL SQL・write_cursor/etl なし | ✓ VERIFIED | test_readonly_guarantee.py + 実コードスキャン（docstring言及のみ・違反なし） |
| 35 | 派生データを st.session_state に保持しない（@st.cache_data のみ） | ✓ VERIFIED | app.py/tabs に st.session_state 派生存置なし・@st.cache_data/@st.cache_resource 使用 |
| 36 | §16.1 除外項目（ワイド/荒れ指数/コメント生成）が UI に一切表示されない | ✓ VERIFIED | src/ui 配下スキャン: ワイド/荒れ指数/コメント生成/wide_candidate 不存在 |

**Score:** 36/36 truths verified (2 present, behavior-unverified — ライブブラウザ描画)

※ 3 つの live-DB fix は全て main に commit 済（0e46b7e sys.path guard / ef83b1e quoted EV_lower/EV_upper / db97a1f width="stretch"）。検証は FIXED 状態で実施。未コミット変更（scripts/run_backtest.py, src/db/prediction_load.py）は Phase 5/6 由来で Phase 7 ファイルに無関係。

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/ui/__init__.py` | パッケージ化 | ✓ VERIFIED | 存在 |
| `src/ui/csv_columns.py` | PREDICTION(20)/BACKTEST(16) DRY 定数 | ✓ VERIFIED | 実行検証 20/16・normalize_prediction_export_columns helper |
| `src/ui/jyocd_map.py` | code_tables.yaml 読込 helper | ✓ VERIFIED | load_jyocd_map・yaml.safe_load |
| `.streamlit/config.toml` | light theme + #FF4B4B | ✓ VERIFIED | [theme] base='light' primaryColor='#FF4B4B' |
| `tests/ui/test_csv_columns.py` | 列定数 presence assert | ✓ VERIFIED | 53 tests pass |
| `tests/ui/test_readonly_guarantee.py` | read-only 保証検証 | ✓ VERIFIED | test_ui_has_no_write_ddl_sql / test_ui_uses_only_readonly_pool |
| `tests/ui/test_segment_schema.py` | 6軸スキーマ契約検証 | ✓ VERIFIED | 53 tests pass |
| `tests/ui/test_streamlit_api_usage.py` | selection_mode/on_select 正引数検証 | ✓ VERIFIED | test_no_legacy_selection_arg |
| `src/ui/loaders.py` | loader 関数群（readonly・is_primary・cache） | ✓ VERIFIED | load_predictions/load_backtests/load_segment_json + cached wrapper・JODDS+compute_ev_and_rank 正経路 |
| `scripts/run_export_predictions_csv.py` | OUT-01 CLI（BOM+CRLF・20列） | ✓ VERIFIED | --output/--odds-snapshot-policy flag・build_prediction_csv_bytes DRY 共有 |
| `scripts/run_export_backtest_csv.py` | OUT-02 CLI（BOM+CRLF・16列） | ✓ VERIFIED | --output flag・build_backtest_csv_bytes DRY 共有 |
| `tests/ui/test_csv_export.py` | BOM/CRLF/ヘッダ契約 | ✓ VERIFIED | test_prediction_csv_bom_crlf/header_matches_columns/backtest_csv_header_16_columns |
| `tests/ui/test_loaders_readonly.py` | readonly/parameterized/is_primary 検証 | ✓ VERIFIED | 53 tests pass |
| `src/ui/app.py` | Streamlit エントリポイント | ✓ VERIFIED | st.title 1回/st.sidebar/st.tabs(3)/get_pool(@st.cache_resource)・sys.path guard(0e46b7e) |
| `src/ui/prediction_tab.py` | 予測一覧・master-detail・selection_mode・再現性スタンプ | ✓ VERIFIED | selection_mode='single-row'+on_select='rerun'・NumberColumn(%.3f)・REPRODUCIBILITY_STAMPS inline |
| `src/ui/backtest_tab.py` | Backtest タブ・honest 注記・CSV download | ✓ VERIFIED | st.warning(st.warning JODDS 再検証 subject)・st.caption(§19.3)・download_button |
| `src/ui/calibration_tab.py` | Segment Calibration・6軸・Plotly・scalar 表 | ✓ VERIFIED | 6軸 selectbox・st.plotly_chart(width="stretch")・ECE/MCE/max_dev_guarded 表 |
| `tests/ui/test_ui_render_contract.py` | UI 描画契約 AST 検証 | ✓ VERIFIED | st.title 1回/st.tabs 3/sidebar/honest/§16.1 除外（53 tests pass） |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| scripts/run_export_predictions_csv.py | csv_columns::PREDICTION_CSV_COLUMNS | from src.ui.csv_columns import | ✓ WIRED | L55 import・CSV 生成時に列整列適用 |
| loaders::load_predictions | prediction + JODDS snapshot + ev_rank::compute_ev_and_rank | is_primary=true SELECT→fetch_jodds→select_odds_snapshot(policy)→compute_ev_and_rank | ✓ WIRED | L196/L388/L419・BLOCKER-1 正経路 |
| loaders::load_predictions | odds_snapshot::select_odds_snapshot | merge_asof(direction='backward') | ✓ WIRED | L388 select_odds_snapshot(jodds_df, race_times, policy) |
| loaders::load_predictions | ev_rank::compute_ev_and_rank | p_fukusho_hit + fuku_odds → EV/rank | ✓ WIRED | L419 merged = compute_ev_and_rank(merged) |
| scripts/run_export_backtest_csv.py | backtest.fukusho_backtest | SELECT（quoted "EV_lower"/"EV_upper"） | ✓ WIRED | _select_backtests に quoted EV（commit ef83b1e） |
| loaders | connection::make_pool | make_pool(role='readonly') | ✓ WIRED | make_readonly_pool L103 |
| app.py | loaders | from src.ui.loaders import | ✓ WIRED | L48 import・get_pool で保持 |
| prediction_tab.py | loaders::build_prediction_csv_bytes | st.download_button data= | ✓ WIRED | L189 download_button |
| calibration_tab.py | reports/06-segments/<axis>.json | load_segment_json_cached + build_calibration_figure | ✓ WIRED | L25 import・L96 load・L107 plotly_chart |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| prediction_tab.py | race_pred_df | load_predictions_cached（JODDS snapshot + compute_ev_and_rank 再計算） | Yes（実DB SELECT・is_primary=true 絞り） | ✓ FLOWING |
| backtest_tab.py | bt_df | load_backtests_cached（backtest.fukusho_backtest SELECT・quoted EV） | Yes | ✓ FLOWING |
| calibration_tab.py | seg_data | load_segment_json_cached（reports/06-segments/*.json・stamped） | Yes（Phase 6 生成 JSON） | ✓ FLOWING |
| run_export_predictions_csv.py | csv_bytes | load_predictions + build_prediction_csv_bytes | Yes | ✓ FLOWING |
| run_export_backtest_csv.py | csv_bytes | load_backtests + build_backtest_csv_bytes | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| UI テストスイート全緑 | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q` | 53 passed in 1.75s | ✓ PASS |
| PREDICTION_CSV_COLUMNS 列数=20 | `python3 -c "...len(PREDICTION_CSV_COLUMNS)"` | 20 | ✓ PASS |
| BACKTEST_CSV_COLUMNS 列数=16 | 同上 | 16 | ✓ PASS |
| streamlit==1.58.0 依存 | `grep streamlit pyproject.toml` | `"streamlit==1.58.0"` | ✓ PASS |
| CLI --help 起動 | test_csv_export.py::test_run_export_predictions_help/backtest_help | pass | ✓ PASS |
| live-DB fix 3件 commit 存在 | git show 0e46b7e/ef83b1e/db97a1f | 全て main に存在 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| UI-01 | 07-01/02/03 | Streamlit 画面でレース一覧・p_fukusho_hit・複勝オッズ下限上限・EV_lower/upper・推奨ランク・再現性スタンプ表示（ワイド/荒れ指数/コメント非表示） | ✓ SATISFIED | app.py/prediction_tab.py/calibration_tab.py・REPRODUCIBILITY_STAMPS inline・§16.1 除外項目スキャン不存在・test_ui_render_contract pass |
| OUT-01 | 07-01/02 | 予測CSV（20列・race_id/../スナップショット情報）出力 | ✓ SATISFIED | PREDICTION_CSV_COLUMNS(20)・run_export_predictions_csv.py・build_prediction_csv_bytes（BOM+CRLF・raise ValueError） |
| OUT-02 | 07-01/02 | backtest CSV（16列・backtest_id/../EV）出力 | ✓ SATISFIED | BACKTEST_CSV_COLUMNS(16)・run_export_backtest_csv.py・quoted "EV_lower"/"EV_upper"（commit ef83b1e） |

orphaned 要件: なし（UI-01/OUT-01/OUT-02 全て 3 PLAN の requirements に含有・REQUIREMENTS.md でも Phase 7 完了扱い）

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| （該当なし） | - | - | - | - |

src/ui 配下の grep スキャン:
- 書込み/DDL SQL（INSERT/UPDATE/DELETE/TRUNCATE/CREATE TABLE/DROP/ALTER）: docstring 内の「使用しない」言及のみ・実コード違反なし
- write_cursor / make_pool(role='etl'): 同上・実使用なし
- §16.1 除外項目（ワイド/荒れ指数/コメント生成/wide_candidate/arare/comment_gen）: 不存在
- TBD/FIXME/XXX: 不存在
- unsafe_allow_html=True: 不存在（test_ui_render_contract で検証）

### Human Verification Required

### 1. ライブ DB 接続での Streamlit UI 描画振る舞い

**Test:** `KEIBA_SKIP_DB_TESTS=0`（実DB接続環境）で `streamlit run src/ui/app.py` を起動・予測一覧タブでレース1行選択
**Expected:** 下部に各馬の p_fukusho_hit/EV_lower/EV_upper/fukusho_odds_lower/upper/recommend_rank 6数値（%.3f）と再現性スタンプ5項目の inline 表示が展開される
**Why human:** Unit test は KEIBA_SKIP_DB_TESTS=1 で DB 未接続。selection_mode/on_select の実ブラウザ挙動と実データ描画は grep/AST で検証不可（07-03 checkpoint:human-verify で RESOLVED 済だが回帰監視として残存）

### 2. Segment Calibration タブ Plotly 描画

**Test:** Segment Calibration タブで6軸（year/month/jyocd/entry_count/ninki/odds_band）を切替
**Expected:** Plotly calibration curve が幅 stretch で重ね描きされ・scalar 表（ECE/MCE/max_dev_guarded/n_samples）が併記される
**Why human:** Plotly Figure 構築は検証済だが・実 JSON 読込時の描画振る舞いと幅 stretch レンダリングはブラウザ目視が必要

### Gaps Summary

gap なし。全 must-have truth は VERIFIED。3 PLAN の成果物（src/ui/*・scripts/run_export_*.py・tests/ui/*・.streamlit/config.toml）は全て存在・substantive・WIRED・データ流動。read-only 保証・§16.1 除外項目の排除・CSV BOM+CRLF+列数契約・JODDS snapshot + compute_ev_and_rank 正経路・is_primary=true 絞り・quoted EV_lower/EV_upper・sys.path guard・width="stretch" の3 live-DB fix 全て main に commit 済。

人間確認項目2件は「ライブ DB/ブラウザ描画振る舞い」という本質的に grep/AST 不可視の側面で・07-03 checkpoint:human-verify で一度 RESOLVED 済み。回帰監視のために明示。

---

_Verified: 2026-06-24T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
