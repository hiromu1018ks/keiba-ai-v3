---
phase: 07-presentation
plan: 01
subsystem: ui-foundation
tags: [ui, csv-contract, streamlit, readonly-guarantee, reproducibility-stamps]
requires:
  - phase-06 (segment JSON 6軸生成済・reports/06-segments/*.json)
  - src/config/code_tables.yaml (jyocd マッピング入力)
  - src/db/schema.py (prediction/backtest DDL・列参照元)
  - src/ev/report.py (REPORT_COLUMNS analog・LOW-05 presence assert)
provides:
  - src/ui/csv_columns.py::PREDICTION_CSV_COLUMNS (20列・§16.2 pin・UI/CLI/test DRY)
  - src/ui/csv_columns.py::BACKTEST_CSV_COLUMNS (16列・§16.2 pin・Pitfall 3 16確定)
  - src/ui/csv_columns.py::REPRODUCIBILITY_STAMPS (UI 行表示用5項目・§19.1 聖域)
  - src/ui/csv_columns.py::normalize_prediction_export_columns (JODDS→canonical rename)
  - src/ui/jyocd_map.py::load_jyocd_map (code_tables.yaml→jyocd dict)
  - tests/ui/ Wave 0 テスト集群 (csv_columns / readonly_guarantee / segment_schema / streamlit_api_usage)
  - .streamlit/config.toml (UI-SPEC Color Contract・light theme + primaryColor=#FF4B4B)
  - pyproject.toml src/ui wheel packages 登録
affects:
  - 07-02-PLAN.md (loaders + CLI が本定数/helper を消費)
  - 07-03-PLAN.md (Streamlit UI 本体が本定数/helper/config を消費)
  - Phase 8 TEST-01 (test_readonly_guarantee.py が書き込み経路不存在の出発点)
tech-stack:
  added:
    - streamlit==1.58.0 (CLAUDE.md §17.1・T-07-SC: 公式パッケージ・blocking human checkpoint 不要)
  patterns:
    - LOW-05 presence assert 再利用 (src/ev/report.py REPORT_COLUMNS → PREDICTION_CSV_COLUMNS)
    - tuple[str, ...] 固定順序の DRY 列定数 (src/db/backtest_load.py BACKTEST_COLUMNS analog)
    - AST で SQL リテラルのみ検査する read-only 保証テスト (REVIEW LOW-2 解決)
    - code_tables.yaml を単一ソースとする DRY YAML 読込 helper
key-files:
  created:
    - src/ui/__init__.py
    - src/ui/csv_columns.py
    - src/ui/jyocd_map.py
    - tests/ui/__init__.py
    - tests/ui/test_csv_columns.py
    - tests/ui/test_readonly_guarantee.py
    - tests/ui/test_segment_schema.py
    - tests/ui/test_streamlit_api_usage.py
    - .streamlit/config.toml
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - odds 列名 canonical は fukusho_odds_lower/fukusho_odds_upper (外部公開)・loaders 内部 fuku_odds_* は normalize_prediction_export_columns で rename (REVIEW HIGH-1)
  - odds_snapshot_at の予測 CSV 取得元は JODDS snapshot の happyo_datetime (backtest JOIN でなく・backtest テーブルに odds 値カラム不存在のため構造的不可能・07-02 revision 確定・REVIEW MEDIUM-2)
  - BACKTEST_CSV_COLUMNS = 16列 (§16.2 原典優先・CONTEXT D-04 「14列」は errata・RESEARCH Pitfall 3・CLAUDE.md 要件優先)
  - read-only 保証テストは AST で execute() Call 第一引数の str 定数のみ検査 (comment/docstring の false positive 回避・planner-discipline-allow マーカーで例外許容・REVIEW LOW-2)
  - selection_mode 検証は緩和基準 (st.dataframe 呼出存在時のみ・Plan 03 実装後有効化・REVIEW LOW-1)
metrics:
  duration: 7min
  tasks_completed: 3
  files_created: 9
  files_modified: 2
  tests_passed: 11 passed / 1 skipped (skip は Plan 03 実装後有効化の緩和基準)
  completed_date: 2026-06-24
status: complete
---

# Phase 7 Plan 01: Presentation 基盤 (CSV 列定数 DRY・jyocd マッピング・Streamlit 依存・Wave 0 テスト) Summary

Phase 7 (Presentation) の基盤を構築 — 後続 Plan 02 (loaders + CLI)・Plan 03 (Streamlit UI 本体) が消費する DRY 単一定数 (`PREDICTION_CSV_COLUMNS` 20列 / `BACKTEST_CSV_COLUMNS` 16列)・jyocd→競馬場名マッピング helper・Streamlit==1.58.0 依存追加・wheel packages 登録・`.streamlit/config.toml` (UI-SPEC Color Contract)・Wave 0 テスト集群 (列定数 presence assert・read-only 保証 AST 検証・segment JSON スキーマ契約・Streamlit API 正引数) を作成。D-04 LOCKED と UI-SPEC 承認済み契約をコード上の契約として固定化。

## What Was Built

### Task 1: 依存追加・パッケージ登録・ディレクトリ骨架 (`ac0ae67`)
- `uv add streamlit==1.58.0` で dependencies と uv.lock を更新 (CLAUDE.md §17.1 推奨バージョン固定・T-07-SC: 公式パッケージ)
- `pyproject.toml` `[tool.hatch.build.targets.wheel] packages` に `"src/ui"` を追加 (RESEARCH Open Question #3 解決・src/config・src/db と同階層)
- `src/ui/__init__.py` をパッケージ化ファイルで作成 (src.* 直接 import 可能化)

### Task 2: CSV 列定数 DRY・jyocd マッピング helper・Wave 0 テスト集群 (`6cd125c`)
- `src/ui/csv_columns.py`:
  - `PREDICTION_CSV_COLUMNS: tuple[str, ...]` (20列・§16.2 原典 行1092-1112 と 1:1)
  - `BACKTEST_CSV_COLUMNS: tuple[str, ...]` (16列・§16.2 原典 行1118-1133・RESEARCH Pitfall 3・CONTEXT D-04 「14列」は errata)
  - `REPRODUCIBILITY_STAMPS: tuple[str, ...]` (UI 行表示用5項目・§19.1 聖域・backtest_strategy_version 含む)
  - `normalize_prediction_export_columns(df)` helper (JODDS 内部 `fuku_odds_*` → 外部 canonical `fukusho_odds_*` rename・REVIEW HIGH-1)
  - docstring で odds_snapshot_at 取得元 (JODDS snapshot happyo_datetime・backtest JOIN でない) と prediction_created_at (as_of_datetime 代用) を明記 (REVIEW MEDIUM-2)
- `src/ui/jyocd_map.py`: `load_jyocd_map() -> dict[str, str]` が `src/config/code_tables.yaml` から PyYAML safe_load で jyocd→競馬場名を読込 (DRY・UI 側に dict ハードコードなし)
- `tests/ui/` 4テストファイル (11 passed, 1 skipped):
  - `test_csv_columns.py`: OUT-01/OUT-02 列定数 presence assert・§16.2 原典20/16項目との順序含む完全一致・重複列なし検証 (LOW-05 再利用)
  - `test_readonly_guarantee.py`: `src/ui/` 配下の SQL 文字列リテラル (AST で execute() Call 第一引数 str 定数のみ) に書き込み/DDL キーワードがないことを検証・make_pool role='readonly' 検証 (REVIEW LOW-2 解決・planner-discipline-allow マーカーで例外許容・Phase 8 TEST-01 前提)
  - `test_segment_schema.py`: `reports/06-segments/{year,month,jyocd,entry_count,ninki,odds_band}.json` 6軸の存在と axis_name + segments[] (curve/scalar/segment_value) スキーマ契約を検証
  - `test_streamlit_api_usage.py`: `st.dataframe` の古い `selection=` 引数不存在と `selection_mode=` 存在の緩和基準検証土俵 (RESEARCH Pitfall 1・Plan 03 実装後有効化)

### Task 3: Streamlit テーマ設定・統合ゲート (`b6e01c1`)
- `.streamlit/config.toml`: `[theme] base = "light"` + `primaryColor = "#FF4B4B"` (UI-SPEC Color Contract・accent reserved-for 明記・その他は Streamlit 既定)
- 統合ゲート: `KEIBA_SKIP_DB_TESTS=1 pytest tests/ui/` → 11 passed, 1 skipped・streamlit + csv_columns + jyocd_map 統合 import OK

## Verification Evidence

全ての Plan 01 verification セクション8項目 GREEN:

1. **依存とパッケージ**: `uv pip show streamlit` → Version: 1.58.0・`grep '"src/ui"' pyproject.toml` → packages 行に一致・`grep 'streamlit==1.58.0'` → dependencies に一致
2. **CSV 列定数 DRY**: `pytest tests/ui/test_csv_columns.py` green・PREDICTION 20列・BACKTEST 16列・再現性スタンプ4項目 presence
3. **read-only 保証土俵**: `pytest tests/ui/test_readonly_guarantee.py` green (src/ui 配下が csv_columns/jyocd_map のみ・SQL 含まない)
4. **segment スキーマ契約**: `pytest tests/ui/test_segment_schema.py` green (6軸 JSON 存在・curve/scalar/segment_value 構造検証)
5. **Streamlit API 正引数土俵**: `pytest tests/ui/test_streamlit_api_usage.py` green (src/ui に st.dataframe 呼出なし・skip)
6. **jyocd マッピング**: `load_jyocd_map()['01']=='札幌' and ['10']=='小倉'` 成功
7. **テーマ設定**: `.streamlit/config.toml` が `base = "light"` + `primaryColor = "#FF4B4B"` を持つ
8. **統合ゲート**: `KEIBA_SKIP_DB_TESTS=1 pytest tests/ui/` exit 0 (11 passed, 1 skipped)

追加品質ゲート: `ruff check src/ui/ tests/ui/` → All checks passed・`ruff format --check` → 8 files already formatted。

## TDD Gate Compliance

3タスク全て `tdd="true"`。本planは定数・helper・設定ファイル・テストの作成が本質で・各テストは presence assert で実装を検証する構造 (RED→GREEN が1ステップで完結する性質)。Plan-level TDD gate (type: tdd) ではなく・各タスク frontmatter の `tdd="true"` 属性のため・commit prefix は実態 (新規機能) に合わせ `feat` で統一 (`test` RED commit を分離しなかった)。`workflow.tdd_mode=false` (config.json) のため MVP+TDD gate は不発火。振る舞い追加 (behavior-adding) なし・定数契約の固定化のみ。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_readonly_guarantee.py のインデント崩れ修正**
- **Found during:** Task 2 検証フェーズ
- **Issue:** `_extract_sql_literals` 関数の docstring が 3スペースインデント (Python 仕様違反・IndentationError で pytest collection 失敗)
- **Fix:** 4スペースに修正
- **Files modified:** tests/ui/test_readonly_guarantee.py
- **Commit:** 6cd125c

**2. [Rule 3 - Blocking] ruff E501 の日本語 docstring 行長緩和**
- **Found during:** Task 2 検証フェーズ
- **Issue:** テストファイルの docstring / assert メッセージが日本語で行長 100 を超える (12箇所)・`ruff check` が FAIL し CI gate を通らない
- **Fix:** `src/ev/report.py`・`src/db/schema.py`・`src/db/backtest_load.py` と同一慣例 (`# ruff: noqa: E501`) で docstring 行長を緩和するディレクティブを4ファイルの先頭に追加
- **Files modified:** tests/ui/test_csv_columns.py, tests/ui/test_readonly_guarantee.py, tests/ui/test_segment_schema.py, tests/ui/test_streamlit_api_usage.py
- **Commit:** 6cd125c

( иных deviations なし・plan に忠実に実行)

## Open Questions Resolved (Plan に記載済・実装で確定)

1. **odds_snapshot_at 取得元** (07-02-PLAN revision で確定済): JODDS snapshot の `happyo_datetime` から取得 (backtest テーブル JOIN でなく・backtest テーブル BACKTEST_COLUMNS に odds 値カラム fuku_odds_lower/fuku_odds_upper 不存在のため構造的不可能)。csv_columns.py docstring に明記。
2. **EV/odds/rank 算出経路** (07-02-PLAN revision で確定済): `compute_ev_and_rank` (src/ev/ev_rank.py L80・純粋関数) を UI/CLI 側で都度適用。odds は EV 判定にのみ使用し特徴量に混入しない (Core Value 直結)。
3. **ディレクトリ判断**: `src/ui/` を採用・pyproject.toml `[tool.hatch.build.targets.wheel] packages` に `"src/ui"` 追加。

## W4 errata 対応 (CONTEXT D-04 「14列」→「16列」)

CONTEXT.md L15/L39 の「pin 済み14列」/「§16.2 pin 済み20/14列」は errata。`BACKTEST_CSV_COLUMNS` は §16.2 原典 (16列) を正として実装し・`test_backtest_csv_columns_count` で `assert len(BACKTEST_CSV_COLUMNS) == 16` を機械検証 (T-07-02 mitigate)。Phase 7 全 plan で一貫して errata 扱い・実装には影響しない。

## Threat Model Mitigations

| Threat ID | Disposition | 実装による mitigate 証明 |
|-----------|-------------|--------------------------|
| T-07-01 (Tampering・CSV 列揺れ) | mitigate | test_csv_columns.py::test_prediction_csv_columns_match_spec が §16.2 原典20項目との順序含む完全一致を assert・列揺れ構造的ブロック |
| T-07-02 (Tampering・BACKTEST 列数誤記) | mitigate | test_csv_columns.py::test_backtest_csv_columns_count が `len == 16` を固定・「14列」誤記を機械的に排除 |
| T-07-03 (Info Disclosure・pyproject/uv.lock) | accept | streamlit==1.58.0 は公開情報・DSN/パスワード含まず (pydantic-settings 別管理) |
| T-07-04 (Tampering・サードパーティコンポーネント) | mitigate | dependencies に streamlit==1.58.0 のみ追加・サードパーティ Streamlit コンポーネント依存なし |
| T-07-SC (Tampering・streamlit install) | mitigate | streamlit は CLAUDE.md §17.1 + docs.streamlit.io (公式) で権威付け・blocking human checkpoint 不要 |

## Known Stubs

なし。本 plan は定数・helper・設定・テストのみで・UI 描画ロジック・データ取得ロジック・placeholder/TODO は含まない (Plan 02/03 で実装)。

## Threat Flags

なし。`src/ui/` 配下に DB 接続・ネットワーク・認証・ファイルアクセス経路は一切存在しない (定数・helper のみ)。新規の脅 threat surface なし。

## Self-Check: PASSED

- 作成ファイル 10件 (src/ui/* 3・tests/ui/* 5・.streamlit/config.toml・SUMMARY.md): 全 FOUND
- コミット 3件 (ac0ae67 / 6cd125c / b6e01c1): 全 FOUND
- pyproject.toml: src/ui packages 登録 FOUND・streamlit==1.58.0 deps FOUND
- Phase 5/6 未コミット変更 (scripts/run_backtest.py・src/db/prediction_load.py): 手つかずで保持確認
