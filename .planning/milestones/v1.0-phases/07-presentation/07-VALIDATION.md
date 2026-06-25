---
phase: 7
slug: presentation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-24
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> Phase 7 は UI/CLI 出力層（Streamlit + CSV export）のため・大量の unit/contract test と
> 1つの manual-only checkpoint（Plan 03 Task 3・実ブラウザ + live-DB 挙動確認）で構成される。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（既依存・§17.3） |
| **Config file** | `pyproject.toml`（`[tool.pytest.ini_options]`・`KEIBA_SKIP_DB_TESTS` 環境変数で live-DB テストを gate） |
| **Quick run command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -x -q` |
| **Full suite command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q`（Phase 7 スコープ・全テスト green で回帰なし） |
| **Estimated runtime** | ~15-25 秒（AST/文字列検証中心・DB 接続なし・`KEIBA_SKIP_DB_TESTS=1` で live PostgreSQL 不要） |

**Note:** Phase 7 の UI テストは AST/文字列/grep 検証が中心で・Streamlit 描画の実 E2E 起動は Plan 03 Task 3 checkpoint:human-verify で手動確認する。`KEIBA_SKIP_DB_TESTS=1` は loaders.py の live SELECT を伴うテスト（実行時のみ）を gate するが・本 Phase のテスト群は構造検証（import・AST・文字列）が主で DB 不要。

---

## Sampling Rate

- **After every task commit:** Run `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -x -q`（quick・当該 task の test ファイル中心だが・回帰検出のため tests/ui/ 全体を走査）
- **After every plan wave:** Run `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q`（Wave 1→2→3 の各完了時・全テスト green を確認）
- **Before `/gsd-verify-work`:** Full suite must be green（`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q` exit 0）+ Plan 03 Task 3 checkpoint:human-verify approved
- **Max feedback latency:** ~25 秒（quick run・AST/文字列検証のみ）

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | UI-01/OUT-01/OUT-02 | T-07-03/SC | streamlit==1.58.0 が §17.1 固定版・pyproject.toml packages に src/ui 追加 | unit | `uv run python -c "import streamlit; assert streamlit.__version__=='1.58.0'" && grep -q '"src/ui"' pyproject.toml` | ❌ W0→✅ | ⬜ pending |
| 07-01-02 | 01 | 1 | UI-01/OUT-01/OUT-02 | T-07-01/02 | CSV 列定数20/16・再現性スタンプ5項目 presence・read-only 保証・segment スキーマ契約・Streamlit API 正引数土俵 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_csv_columns.py tests/ui/test_readonly_guarantee.py tests/ui/test_segment_schema.py tests/ui/test_streamlit_api_usage.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 07-01-03 | 01 | 1 | UI-01 | T-07-04 | .streamlit/config.toml が UI-SPEC Color Contract（base=light, primaryColor=#FF4B4B） | unit | `test -f .streamlit/config.toml && grep -q 'base = "light"' .streamlit/config.toml && grep -q 'primaryColor = "#FF4B4B"' .streamlit/config.toml` | ❌ W0→✅ | ⬜ pending |
| 07-02-01 | 02 | 2 | OUT-01/OUT-02/UI-01 | T-07-05/06/07 | loaders.py が readonly pool・is_primary=true 絞り・parameterized query・@st.cache_data(hash_funcs)・Open Question #1/#2 解決経路（JODDS snapshot + compute_ev_and_rank） | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_loaders_readonly.py tests/ui/test_readonly_guarantee.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 07-02-02 | 02 | 2 | OUT-01/OUT-02 | T-07-08/09/10 | run_export_predictions_csv.py/run_export_backtest_csv.py が UTF-8 BOM + CRLF・20/16列・dsn_masked・DRY 共有 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_csv_export.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 07-03-01 | 03 | 3 | UI-01/OUT-01/OUT-02 | T-07-12..19 | app.py + 3タブ（prediction/backtest/calibration）が UI-SPEC Layout/Component Inventory・Pitfall 1 正引数（selection_mode/on_select）・honest 注記・再現性スタンプ inline・§16.1 除外項目排除 | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_ui_render_contract.py tests/ui/test_streamlit_api_usage.py tests/ui/test_readonly_guarantee.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 07-03-02 | 03 | 3 | UI-01 | T-07-12/15/18 | test_ui_render_contract.py 拡張・test_streamlit_api_usage.py 強化（AST 検証・st.title 1回・3タブラベル・sidebar フィルタ・NumberColumn %.3f・download_button ラベル・honest warning・plotly_chart・6軸・unsafe_allow_html なし・§16.1 除外項目なし） | unit | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_ui_render_contract.py tests/ui/test_streamlit_api_usage.py -x -q` | ❌ W0→✅ | ⬜ pending |
| 07-03-03 | 03 | 3 | UI-01/OUT-01/OUT-02 | T-07-12..19 | Streamlit UI 実ブラウザ + live-DB 挙動確認（manual-only・UI-01 予測一覧/スタンプ/ダウンロード・OUT-01/OUT-02 CSV・D-05 Plotly・honest 注記・§16.1 除外） | manual | `uv run streamlit run src/ui/app.py`（ブラウザ http://localhost:8501・Plan 03 Task 3 how-to-verify 10項目）+ `uv run python scripts/run_export_predictions_csv.py --output /tmp/pred.csv` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Phase 7 の Wave 0（テスト土俵）は Plan 01 Task 2 で計画・作成される（`wave_0_complete: true` は Plan 01 で Wave 0 相当のテストファイル群が作成されるため）。各テストファイルは Plan 01 Task 2 時点では検証対象コードが未実装のため green（土俵のみ）で・Plan 02/03 の実装とともに本格化する。

- [x] `tests/ui/__init__.py` — パッケージ化（Plan 01 Task 2）
- [x] `tests/ui/test_csv_columns.py` — PREDICTION_CSV_COLUMNS (20列) / BACKTEST_CSV_COLUMNS (16列) presence assert・再現性スタンプ5項目（REQ: OUT-01/OUT-02・T-07-01/02）
- [x] `tests/ui/test_readonly_guarantee.py` — src/ui/ 配下の書き込み/DDL SQL・write_cursor/role='etl' 不存在検証（REQ: UI-01・T-07-06・Phase 8 TEST-01 前提）
- [x] `tests/ui/test_segment_schema.py` — reports/06-segments/*.json 6軸スキーマ契約（REQ: UI-01・D-12・Phase 6 D-10/D-11 生成済 stamped データ検証）
- [x] `tests/ui/test_streamlit_api_usage.py` — selection_mode/on_select 正引数（Pitfall 1）・unsafe_allow_html なし（V13）の検証土俵（REQ: UI-01・T-07-12/18）

Wave 0 で作成されるテストは Phase 7 全 plan（01/02/03）で共有され・各 plan の実装とともに検証対象を拡張する。追加の conftest.py・fixture は不要（AST/文字列/grep 検証中心・DB fixture なし）。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Streamlit UI 実ブラウザ描画（UI-01 予測一覧・selection_mode single-row マスター・ディテール展開・再現性スタンプ inline・推奨ランク色分け・CSV ダウンロード） | UI-01 | Streamlit 描画はブラウザ DOM 描画とインタラクション状態を伴う・unit test の AST/文字列検証では描画結果の視覚的確認が不可能。@st.cache_data の実キャッシュ挙動・Plotly インタラクティブ描画・single-row 選択の実イベントも手動確認が必要。 | Plan 03 Task 3 checkpoint:human-verify の how-to-verify 10項目に従う（`uv run streamlit run src/ui/app.py` → http://localhost:8501 で UI-01/OUT-01/OUT-02/D-05/§16.1 除外を確認） |
| OUT-01/OUT-02 実 CSV 出力（live PostgreSQL から22,213行・主モデル=LightGBM・is_primary=true 絞り） | OUT-01/OUT-02 | live-DB SELECT を伴うため `KEIBA_SKIP_DB_TESTS=1` の unit test 範囲外。実データでしか検証できない列揃え・行数・日本語馬名の Excel 表示も手動確認。 | Plan 03 Task 3 how-to-verify Step 10: `uv run python scripts/run_export_predictions_csv.py --output /tmp/pred.csv --date-from 2024-01-01 --date-to 2024-12-31` で /tmp/pred.csv 生成・ヘッダ20列・UTF-8 BOM で Excel で化けないことを確認 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（07-03-03 checkpoint:human-verify は manual-only だが Plan 03 Task 1/2 の automated test が先に green であることを前提とする・Imports smoke `import src.ui.app` を checkpoint の automated に含めない（本計画では Streamlit 実起動が本体・import は unit test と `--help` で間接検証済））
- [x] Sampling continuity: no 3 consecutive tasks without automated verify（各 plan 内の task は全て automated verify を持つ・Plan 03 Task 3 manual-only は Task 1/2 の automated test green を前提とする連続最後の1つのみ）
- [x] Wave 0 covers all MISSING references（Plan 01 Task 2 で tests/ui/ 4ファイル作成・全 plan で共有・MISSING なし）
- [x] No watch-mode flags（`pytest -x -q` のみ・`--watch`/`pytest-watch` なし）
- [x] Feedback latency < 25s（AST/文字列検証中心・~15-25秒）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending（Phase 7 実行完了後に approved YYYY-MM-DD）
