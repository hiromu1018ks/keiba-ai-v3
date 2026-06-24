---
phase: 07-presentation
plan: 02
subsystem: ui-loaders-cli
tags: [ui, loaders, csv-export-cli, readonly-guarantee, jodds-snapshot, ev-recompute, dry-shared]
requires:
  - phase-06 (prediction.fukusho_prediction 主モデル行・backtest.fukusho_backtest)
  - 07-01 (PREDICTION_CSV_COLUMNS/BACKTEST_CSV_COLUMNS 定数・load_jyocd_map・normalize_prediction_export_columns)
  - src/ev/odds_snapshot.py (fetch_jodds + select_odds_snapshot・JODDS snapshot 正経路)
  - src/ev/ev_rank.py (compute_ev_and_rank 純粋関数・EV/rank 再計算)
  - src/db/connection.py (make_pool/readonly_cursor・2ロール DSN)
  - src/model/data.py (make_race_key・race_key 正準形式)
provides:
  - src/ui/loaders.py::load_predictions (純粋関数・CLI 直接 import・Open Question #1/#2 解決経路)
  - src/ui/loaders.py::load_backtests (純粋関数・CLI 直接 import)
  - src/ui/loaders.py::load_segment_json (純粋関数・CLI 直接 import)
  - src/ui/loaders.py::load_predictions_cached/load_backtests_cached/load_segment_json_cached (@st.cache_data 付き UI 用 wrapper・REVIEW MEDIUM-4)
  - src/ui/loaders.py::build_prediction_csv_bytes/build_backtest_csv_bytes (UI/CLI 共有・UTF-8 BOM + CRLF・raise ValueError fail-loud)
  - src/ui/loaders.py::build_race_id (表示専用 canonical race_id・NEW-M3)
  - src/ui/loaders.py::normalize_date_range (st.date_input 正規化・NEW-L1 単一ホーム)
  - src/ui/loaders.py::EV_STRATEGY_VERSION (REVIEW HIGH-4・"fukusho_ev_v1" 定数)
  - src/ui/loaders.py::make_readonly_pool (UI/CLI 共有 readonly pool wrapper)
  - scripts/run_export_predictions_csv.py (OUT-01 CLI・--odds-snapshot-policy flag・NEW-H1)
  - scripts/run_export_backtest_csv.py (OUT-02 CLI・--backtest-id flag)
  - tests/ui/test_loaders_readonly.py (readonly/parameterized query/is_primary/hash_funcs 契約検証・17 tests)
  - tests/ui/test_csv_export.py (BOM/CRLF/ヘッダ/fail-loud/--help/DRY import/dsn_masked 契約検証・9 tests)
affects:
  - 07-03-PLAN.md (Streamlit UI 本体が本 loaders の cached wrapper と列定数を消費・normalize_date_range を import)
  - Phase 8 TEST-01 (test_loaders_readonly.py/test_readonly_guarantee.py が書き込み経路不存在の出発点)
tech-stack:
  added: []
  patterns:
    - 純粋関数 loader と @st.cache_data cached wrapper の分離 (REVIEW MEDIUM-4・CLI は Streamlit runtime 非依存)
    - Open Question #1/#2 解決経路: prediction SELECT → JODDS snapshot → compute_ev_and_rank 再計算 → normalize rename (backtest JOIN でなく構造的不可能)
    - REVIEW HIGH-1 順序: compute_ev_and_rank (内部名 fuku_odds_* 期待) の後に normalize_prediction_export_columns で fukusho_* rename
    - AST で cur.execute Call を走査する parameterized query 検証 (MEDIUM-3 静的 SELECT 例外・JoinedStr WHERE/VALUES 検出)
    - build_race_id 表示専用 canonical race_id (NEW-M3・DB JOIN キー race_key とは別物)
    - EV_STRATEGY_VERSION 定数付与で "latest backtest" 推論廃止 (REVIEW HIGH-4)
key-files:
  created:
    - src/ui/loaders.py
    - scripts/run_export_predictions_csv.py
    - scripts/run_export_backtest_csv.py
    - tests/ui/test_loaders_readonly.py
    - tests/ui/test_csv_export.py
  modified: []
decisions:
  - Open Question #1/#2 RESOLVED: odds/EV/rank/odds_snapshot_at は backtest JOIN でなく「prediction SELECT (is_primary=true) → JODDS snapshot (fetch_jodds + select_odds_snapshot) → compute_ev_and_rank 再計算」経路で取得 (backtest テーブルに odds 値カラム fuku_odds_lower/upper 不存在のため構造的不可能・BLOCKER-1)
  - REVIEW HIGH-1 順序: compute_ev_and_rank が内部名 fuku_odds_* を期待するため EV 計算の後に normalize_prediction_export_columns で fukusho_* rename (rename 後だと KeyError)
  - REVIEW MEDIUM-4 完全化: load_predictions/load_backtests/load_segment_json は純粋関数 (@st.cache_data なし・CLI 直接 import)・load_*_cached が @st.cache_data(hash_funcs={ConnectionPool: id}) 付き UI 用 wrapper (CLI は Streamlit runtime 非依存)
  - REVIEW HIGH-3/NEW-M3: build_race_id は表示専用 canonical race_id (5部・year-jyocd-kaiji-nichiji-racenum)・DB JOIN キー race_key (make_race_key 正準形式) とは別物・docstring で役割分離明記
  - REVIEW HIGH-4: backtest_strategy_version は EV_STRATEGY_VERSION='fukusho_ev_v1' 定数付与のみ・"latest backtest" 推論廃止 (複数 strategy/policy 混在時の provenance 誤表示排除)
  - REVIEW MEDIUM-5/NEW-L1: normalize_date_range は src/ui/loaders.py のみに定義・Plan 03 app.py は import で再利用 (単一ホーム・重複定義禁止)
  - REVIEW LOW-3: build_*_csv_bytes の必須列欠落時は raise ValueError (assert/AssertionError でなく・python -O でも無効化されない・NEW-M2)
  - NEW-H1: --odds-snapshot-policy CLI flag で事前固定 policy を指定・事後 grep での最良 policy 再選択は §11.2 で禁止・再現性は odds_snapshot_policy 列で保証
  - REVIEW MEDIUM-3 例外: parameterized query 検証で %s/WHERE/VALUES を含まない静的 SELECT は第二引数省略を許容・文字列結合 BinOp と f-string WHERE/VALUES 構築は全ケース禁止
metrics:
  duration: 12min
  tasks_completed: 2
  files_created: 5
  files_modified: 0
  tests_passed: 26 passed / 1 skipped (Plan 01+02 統合 35 passed, 1 skipped・skip は Plan 03 実装後有効化)
  completed_date: 2026-06-24
status: complete
---

# Phase 7 Plan 02: Loaders + CSV 出力 CLI (OUT-01/OUT-02・DRY 共有・Open Question #1/#2 解決経路) Summary

Phase 7 (Presentation) の**データ読込と CLI バッチ出力経路**を実装 — `src/ui/loaders.py`（DB/JSON 読込 loader・`@st.cache_data` 付き cached wrapper と CLI 用純粋関数の分離・readonly pool・`is_primary=true` 絞り）と `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py`（OUT-01/OUT-02 CLI・UTF-8 BOM + CRLF・D-04 DRY）を作成。Plan 01 の DRY 列定数と Task 1 の純粋 loader を CLI と UI（Plan 03）が共有し列揺れを構造的に排除。**Open Question #1/#2 RESOLVED**: odds/EV/rank/odds_snapshot_at は backtest JOIN でなく「prediction SELECT → JODDS snapshot → compute_ev_and_rank 再計算」経路で取得（backtest テーブルに odds 値カラム不存在のため構造的不可能・BLOCKER-1）。

## What Was Built

### Task 1: src/ui/loaders.py（純粋 loader + cached wrapper・Open Question #1/#2 解決経路） (`8c87f3f`)
- **純粋関数 `load_predictions`** (CLI 直接 import・`@st.cache_data` なし・REVIEW MEDIUM-4):
  - **Step 1**: prediction SELECT (readonly pool・`WHERE is_primary = true`・Pitfall 5・主モデル=LightGBM 絞り) で `p_fukusho_hit` + provenance + PK RACE_KEY 7 を取得。backtest JOIN は行わない（構造的不可能）。
  - **Step 2**: JODDS snapshot 取得 (`fetch_jodds(cur, years=[...])` + `select_odds_snapshot(jodds_df, race_times, policy)`)・`race_times` は `normalized.n_race` から構築・`dropna(subset=["race_start_datetime"])` で NULL 除外 (REVIEW HIGH-2)・`merge_asof(direction='backward')` で未来リーク構造的不可 (D-02)。
  - **Step 3**: `compute_ev_and_rank` 純粋関数で EV/rank 再計算 (内部名 `fuku_odds_*` 期待・§11.1 直線積 + §11.5 階層判定)。
  - **Step 3.5**: `normalize_prediction_export_columns` で `fuku_*` → `fukusho_*` rename (REVIEW HIGH-1・EV 計算の**後**に実行・順序逆だと KeyError)。
  - **Step 4**: `normalized.n_uma_race` から bamei/wakuban を JOIN・jyocd→競馬場名 map・派生列 (race_id/horse_id/競馬場/レース番号/枠番/馬番) 付与。
  - 再現性スタンプ: `odds_snapshot_policy` (事前固定値定数列・§11.2) + `backtest_strategy_version` = `EV_STRATEGY_VERSION` (定数・REVIEW HIGH-4)。
- **純粋関数 `load_backtests`** (CLI 直接 import): backtest 全行 SELECT → train_period/validation_period/race_id/horse_id 派生。
- **純粋関数 `load_segment_json`** (CLI 直接 import): `reports/06-segments/<axis>.json` 読込・empty state で `{}`。
- **UI 用 cached wrapper** (REVIEW MEDIUM-4 完全化): `@st.cache_data(hash_funcs={ConnectionPool: id})` 付き `load_predictions_cached`/`load_backtests_cached`/`load_segment_json_cached`（純粋関数の上に Streamlit デコレータを被せる・Pitfall 2 UnhashableParamError 回避）。
- **helper 群**: `build_race_id` (表示専用 canonical race_id・NEW-M3・DB JOIN キー race_key とは別物)・`normalize_date_range` (st.date_input 正規化・NEW-L1 単一ホーム)・`build_prediction_csv_bytes`/`build_backtest_csv_bytes` (UI/CLI 共有・UTF-8 BOM + CRLF・`raise ValueError` fail-loud・REVIEW LOW-3)・`make_readonly_pool`・`EV_STRATEGY_VERSION = "fukusho_ev_v1"` (REVIEW HIGH-4)。
- **test_loaders_readonly.py** (17 tests): readonly pool AST 検証・書き込み/DDL SQL キーワード不存在・`is_primary` 絞り・parameterized query 検証 (MEDIUM-3 静的 SELECT 例外)・`hash_funcs`・rename map・build_race_id・fail-loud・EV_STRATEGY_VERSION・normalize_date_range・純粋/cached 分離の契約検証。

### Task 2: scripts/run_export_predictions_csv.py + run_export_backtest_csv.py（D-04 CLI・OUT-01/OUT-02） (`9729213`)
- **scripts/run_export_predictions_csv.py**: OUT-01 予測 CSV 20列 CLI・argparse で `--output`/`--date-from`/`--date-to`/`--jyocd`/`--odds-snapshot-policy` (NEW-H1・§11.2 hindsight-odds 禁止・enum 30min_before/10min_before) flag。純粋関数 `load_predictions` (cached wrapper でなく・REVIEW MEDIUM-4) を import・`odds_snapshot_policy=args.odds_snapshot_policy` を必ず渡す。`settings.dsn_masked` のみ logger 出力 (T-07-08 ASVS V8)・`make_pool(role="readonly")`・try/finally で pool close・戻り値 0/3。
- **scripts/run_export_backtest_csv.py**: OUT-02 backtest CSV 16列 (Pitfall 3) CLI・`--output`/`--backtest-id` flag。純粋関数 `load_backtests` を import・同構造。
- **test_csv_export.py** (9 tests): BOM/CRLF・ヘッダ完全一致 (PREDICTION 20列 / BACKTEST 16列・順序含む)・`raise ValueError` fail-loud (REVIEW LOW-3)・`--help` exit 0 で所定 flag 含む・DRY import (`from src.ui.csv_columns import` + `from src.ui.loaders import`)・`dsn_masked` 使用と生 DSN logger 出力不存在の契約検証。

## Verification Evidence

Plan 02 verification セクション6項目 (V7 は live-DB 手動検証で automated gate 範囲外) 全て GREEN:

1. **loaders read-only 保証** (V1): `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_loaders_readonly.py tests/ui/test_readonly_guarantee.py -q` → 17 passed (AST 検証で make_pool role='readonly'・書き込み/DDL SQL 不存在・is_primary 絞り・parameterized query・hash_funcs を確認・Plan 01 test_readonly_guarantee.py が loaders.py 追加後も green)
2. **CSV bytes 生成契約** (V2): `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/test_csv_export.py -q` → 9 passed (BOM/CRLF・ヘッダ完全一致・raise ValueError fail-loud・--help・DRY import・dsn_masked)
3. **CLI --help** (V3): 両 CLI の `--help` が exit 0 で所定 flag (`--output`/`--date-from`/`--date-to`/`--odds-snapshot-policy`・`--output`/`--backtest-id`) を含む usage を出力
4. **DRY 共有** (V4): 両 CLI が `from src.ui.csv_columns import` と `from src.ui.loaders import` を含む (grep 2/2)
5. **dsn_masked** (V5): 両 CLI が `dsn_masked` を含む (grep 2/2)
6. **統合ゲート** (V6): `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ui/ -q` → 35 passed, 1 skipped (Plan 01 + Plan 02 全 green・回帰なし・skip は Plan 03 実装後有効化の REVIEW LOW-1 緩和基準)

追加品質ゲート: `ruff check src/ui/loaders.py scripts/run_export_*.py tests/ui/test_*.py` → All checks passed・`ruff format --check` → 全 files already formatted。

## TDD Gate Compliance

2タスク全て `tdd="true"`。本 plan は loader/CLI 実装と契約テストが密接に連携し・各テストは presence assert と契約検証で実装を検証する構造 (RED→GREEN が1ステップで完結する性質・Plan 01 と同一)。Plan-level TDD gate (type: tdd) ではなく・各タスク frontmatter の `tdd="true"` 属性のため・commit prefix は実態 (新規機能) に合わせ `feat` で統一 (`test` RED commit を分離しなかった)。`workflow.tdd_mode=false` (config.json) のため MVP+TDD gate は不発火。振る舞い追加 (behavior-adding) は loaders.py の loader/CSV bytes 生成と CLI のバッチ出力経路確立。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ruff F541 (f-string が placeholder を持たない) と isort 順序の自動修正**
- **Found during:** Task 1・Task 2 検証フェーズ
- **Issue:** test_loaders_readonly.py の2箇所の assert メッセージが `f"..."` だが placeholder (`{...}`) を含まない (ruff F541)・loaders.py と CLI の import が ruff の isort (アルファベット順) で並び替えられる
- **Fix:** `ruff check --fix` で F541 を自動修正 (不要な f prefix を削除)・`ruff format` で isort 順序と行長を自動整形。機能的変更なし。
- **Files modified:** src/ui/loaders.py, tests/ui/test_loaders_readonly.py, tests/ui/test_csv_export.py
- **Commit:** 8c87f3f, 9729213 (各タスクのコミットに含む)

**2. [ Rule 3 - Blocking] acceptance criteria grep `from src.ui.loaders import load_predictions, build_prediction_csv_bytes` の順序不一致**
- **Found during:** Task 2 acceptance criteria 検証
- **Issue:** ruff の isort が import 文をアルファベット順に並び替え・`build_prediction_csv_bytes, load_predictions` の順になる (plan の grep 期待順序 `load_predictions, build_prediction_csv_bytes` と不一致で grep -c が 0)
- **Fix:** 実質的に両シンボルを import しており・`test_cli_imports_shared_constants` が green で D-04 DRY 共有を機械検証済み。grep 順序は ruff isort による自動整形で・機能的には完全に満たす。修正不要 (実装は正しい・plan の grep 期待が ruff の慣例と異なるだけ)。
- **Files modified:** なし (実装は正しい)

(その他 deviations なし・plan に忠実に実行)

## Open Questions Resolved (Plan に記載済・実装で確定)

1. **Open Question #1/#2 (BLOCKER-1) RESOLVED**: odds/EV/rank/odds_snapshot_at は backtest JOIN でなく「prediction SELECT (is_primary=true) → JODDS snapshot (`fetch_jodds` + `select_odds_snapshot(policy)`) → `compute_ev_and_rank` 再計算」経路で取得。backtest テーブルに odds 値カラム `fuku_odds_lower`/`fuku_odds_upper` は不存在 (BACKTEST_COLUMNS L77-116 実証済) のため backtest JOIN 経路は構造的不可能。loaders.py に正経路を組込。
2. **REVIEW HIGH-1 順序確定**: `compute_ev_and_rank` が内部名 `fuku_odds_*` を期待するため・Step 3 (EV 計算) を先に行い・Step 3.5 (`fuku_*`→`fukusho_*` rename) は EV 計算の**後**に実行する (順序逆だと KeyError)。loaders.py で実装。
3. **REVIEW MEDIUM-4 完全化**: CLI が Streamlit runtime に非依存となるよう・`load_predictions`/`load_backtests`/`load_segment_json` は `@st.cache_data` なしの純粋関数とし・CLI は純粋関数の方を import・`load_*_cached` が `@st.cache_data(hash_funcs={ConnectionPool: id})` 付き UI 用 wrapper。

## Threat Model Mitigations

| Threat ID | Category | Component | Disposition | 実装による mitigate 証明 |
|-----------|----------|-----------|-------------|--------------------------|
| T-07-05 | Tampering (SQL injection) | loaders.py load_predictions/load_backtests の SQL | mitigate | psycopg parameterized query (`cur.execute(sql, (params,))`) のみ・f-string/+ 結合禁止・test_loaders_uses_parameterized_queries が AST で cur.execute Call を走査し BinOp/JoinedStr WHERE 構築を検出 (MEDIUM-3 静的 SELECT 例外あり) |
| T-07-06 | Elevation of Privilege | loaders.py・make_pool role | mitigate | `make_pool(role="readonly")` のみ・test_loaders_uses_only_readonly_pool が AST 検証・write_cursor/make_pool(role='etl') 経路なし・test_loaders_has_no_write_ddl_sql が二重防御 |
| T-07-07 | Tampering (主モデル混入) | load_predictions SQL | mitigate | `WHERE is_primary = true` で主モデル=LightGBM 絞り・test_loaders_predictions_filter_is_primary が inspect.getsource で検証 (Pitfall 5) |
| T-07-08 | Information Disclosure | scripts/run_export_*.py logger | mitigate | `settings.dsn_masked` のみ logger.info 出力・test_cli_uses_dsn_masked が生 settings.dsn の logger 直接渡し不存在を検証 (Shared Pattern 8・ASVS V8) |
| T-07-09 | Tampering (silent 欠落) | build_*_csv_bytes | mitigate | DataFrame が PREDICTION/BACKTEST_CSV_COLUMNS 全列を含むことを検証し `raise ValueError` で fail-loud (NEW-M2: assert でなく raise ValueError・python -O でも無効化されない・test_prediction_csv_missing_column_asserts が pytest.raises(ValueError) で検証) |
| T-07-10 | Tampering (CSV 列順・§16.2 pin) | build_*_csv_bytes | mitigate | CSV ヘッダ1行目が PREDICTION/BACKTEST_CSV_COLUMNS を結合した文字列と完全一致を test で検証 (順序含む・test_prediction_csv_header_matches_columns/test_backtest_csv_header_16_columns)・BACKTEST 16列 (Pitfall 3) |
| T-07-11 | Tampering (hindsight odds・リーク) | load_predictions の JODDS snapshot + compute_ev_and_rank 再計算経路 | mitigate | `select_odds_snapshot(policy)` で `odds_snapshot_policy` を事前固定 (CLI --odds-snapshot-policy flag・NEW-H1)・`merge_asof(direction='backward')` で未来 snapshot 構造的不可 (D-02)・odds は EV 判定にのみ使用し特徴量に混入しない (D-07) |

## Known Stubs

なし。本 plan は loader・CLI・テストの実装完了で・placeholder/TODO/coming soon を含まない (stub scan 実施・grep の `Placeholder`/`placeholder で渡す` は psycopg.sql.Placeholder の技術用語で UI 表示の stub でない)。OUT-01/OUT-02 の CLI 出力経路は確立済み・UI (Plan 03) は本 loaders の cached wrapper を消費する仕様。

## Threat Flags

なし。`src/ui/loaders.py`・CLI は既存 DB 接続 (readonly pool)・既存ファイル出力 (reports/07-*.csv・T-07-09 範囲内) のみで・新規の network/auth/file access 経路は存在しない (threat surface scan 実施)。新規の脅威 surface なし。

## Self-Check: PASSED

- 作成ファイル 5件 (src/ui/loaders.py, scripts/run_export_predictions_csv.py, scripts/run_export_backtest_csv.py, tests/ui/test_loaders_readonly.py, tests/ui/test_csv_export.py): 全 FOUND
- コミット 2件 (8c87f3f / 9729213): 全 FOUND (git log --oneline で確認)
- Task 1 acceptance: is_primary=6, role="readonly"=5, hash_funcs=5, 関数定義=11, EV_STRATEGY_VERSION=4, rename map=1, loaders import OK
- Task 2 acceptance: 両 CLI --help exit 0・DRY import 2/2・dsn_masked 2/2・BOM OK
- 統合ゲート: tests/ui/ 35 passed, 1 skipped (Plan 01 + Plan 02 全 green・回帰なし)
- Phase 5/6 未コミット変更 (scripts/run_backtest.py・src/db/prediction_load.py): 手つかずで保持確認 (本 plan のコミットに混入なし)
