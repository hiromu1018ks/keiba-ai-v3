---
phase: 03-as-of-features-snapshots
plan: 02
subsystem: etl
tags: [phase-03, etl, label-backfill, phase-2-debt, staging-swap, human-verify, reviews-rev2, cutoff-prereq]
requires:
  - Plan 02-03 (label.fukusho_label ETL — 負債の発生元)
  - Plan 03-01 (feature_availability.yaml が race_date 列を前提とする cutoff_semantics)
provides:
  - src/etl/label_race_date_backfill.py (backfill_label_race_date + _idempotent_backfill_label)
  - scripts/run_label_race_date_backfill.py (CLI・2回実行 idempotent verify)
  - tests/test_label_race_date_backfill.py (9 GREEN unit tests / 1 live-DB skip)
  - label.fukusho_label.race_date 全 554267 行 非 NULL（実 DB に反映済）
affects:
  - Plan 03-03 (builder が feature_cutoff_datetime = race_date - 1 day を stamp 可能に)
  - Plan 03-04 (snapshot が race_date 列を含む Parquet を作成可能に)
  - Phase 4 モデル（PID-correct feature snapshot の前提）
tech-stack:
  added: []
  patterns:
    - staging-table-swap idempotent backfill (Phase 1 _idempotent_load / Phase 2 _idempotent_load_label の第3適用・advisory lock + INCLUDING ALL + GRANT 再発行)
    - INSERT/SELECT positional alignment via per-column comprehension (race_date 位置だけ nr.race_date に差替・末尾 append 禁止)
    - double-execution idempotent verify (run_label_etl.py パターン踏襲・checksum + rowcount 一致 assert)
key-files:
  created:
    - src/etl/label_race_date_backfill.py
    - scripts/run_label_race_date_backfill.py
    - tests/test_label_race_date_backfill.py
  modified: []
decisions:
  - "narrow UPDATE 直書きでなく staging-swap を採用 (Phase 1/2 の確立パターン・INCLUDING ALL で PK/index/comment 継承・REVIEWS MEDIUM #7 accept)"
  - "INSERT と SELECT の列順を完全整列 (race_date 位置だけ nr.race_date に差替)・末尾 append は positional mismatch で date/integer 型エラーになるため禁止"
  - "Task 2 checkpoint で実行した結果 SQL 型不一致 bug を発見 (Rule 1 auto-fix)・raw へは書込前だったため DB 被害なし"
metrics:
  duration: "12m"
  completed: "2026-06-19"
  tasks: 2
  files: 3
---

# Phase 03 Plan 02: label.fukusho_label.race_date backfill (Phase 2 負債解消 / cutoff 前提) Summary

Phase 2 で残された `label.fukusho_label.race_date` 全 554267 行 NULL 負債を、Phase 1/2 で確立した staging-table-swap idempotent パターン（advisory lock → CREATE INCLUDING ALL → INSERT with JOIN → rowcount verify → atomic DROP+RENAME → 明示 reader GRANT）で解消。実 DB 実行で発覚した INSERT/SELECT positional mismatch bug を Rule 1 で auto-fix し、2回連続実行 idempotent verify + raw fingerprint before/after 二重保護 + race_date 全行非 NULL (554267/554267) を実証。Phase 3 cutoff（D-06: `feature_cutoff_datetime = race_date - 1 day`）の前提が解消され、後続 Plan 03-03/03-04 が稼働可能になった。

## What Was Built

### Task 1: backfill モジュール + unit test + CLI (commits b0dfaf3 → a878f6a → f3ac6ea)

- **`src/etl/label_race_date_backfill.py`** — Phase 2 `_idempotent_load_label`（fukusho_label.py:940-1014）の staging-swap idiom を再利用した backfill 専用モジュール:
  - public API `backfill_label_race_date(read_pool, etl_pool, *, reader_role='keiba_readonly') -> dict` — 戻り値 `{rows_backfilled, checksum, raw_touched=False, non_null_race_date_count}`
  - 内部ヘルパー `_idempotent_backfill_label(write_cur, *, expected_rowcount, reader_role) -> int` — `pg_advisory_xact_lock(hashtext('label.fukusho_label'))` (CR-04(b)) → 空入力 RuntimeError (CR-04(a)) → `CREATE ... _staging (LIKE ... INCLUDING ALL)` (HIGH #3) → `TRUNCATE` → INSERT SELECT with JOIN → `SELECT count(*)` rowcount verify (WR-06) → atomic DROP+RENAME → `GRANT SELECT ON label.fukusho_label TO {reader_role}` (HIGH #3・TO PUBLIC 不使用・Identifier で安全に置換)
  - JOIN: `label.fukusho_label fl JOIN normalized.n_race nr ON (year, jyocd, kaiji, nichiji, racenum)` + 両側 `project_window_filter` (CR-06 single source)
  - read_pool（readonly）は SELECT のみ（raw fingerprint before/after + pre-count + non_null count）・etl_pool（etl）のみ DDL/DML（HIGH #6 role 分離）
  - `assert_raw_unchanged(before, after)` で D-06 二重保護
- **`scripts/run_label_race_date_backfill.py`** — `run_label_etl.py` と同一構造の CLI:
  - masked DSN ログ（MEDIUM #1・HIGH #6・パスワード `***`）
  - `backfill_label_race_date` を **2回連続実行** し `result1 == result2`（rows_backfilled + checksum）を assert（HIGH #3 idempotent verify）
  - 2回実行でも `raw_touched=False` を assert（D-06）
  - `non_null_race_date_count == rows_backfilled` を assert（T-03-08 silent data loss 防止）
- **`tests/test_label_race_date_backfill.py`** — Phase 2 test_fukusho_label.py の mock cursor + `inspect.getsource` パターンで 9 つの構造的回帰検査:
  - `test_backfill_refuses_empty_input`（CR-04(a) 空入力 RuntimeError・swap 前に raise）
  - `test_backfill_uses_staging_swap_pattern`（HIGH #3: advisory lock / CREATE staging / RENAME / GRANT の4要素 regression）
  - `test_backfill_joins_normalized_n_race`（CR-06 single source JOIN + project_window_filter('fl')/('nr')）
  - `test_backfill_does_not_mutate_raw`（D-06: UPDATE/INSERT/DELETE INTO raw_everydb2/public.n_ が無い）
  - `test_backfill_uses_etl_role_only`（read cursor は SELECT のみ・write_cur のみ DDL）
  - `test_backfill_rowcount_verify`（WR-06: staging SELECT count(*) 不一致で RuntimeError・swap 前に raise）
  - `test_backfill_returns_final_rowcount_on_success`
  - `test_backfill_live_db`（`@pytest.mark.requires_db`・KEIBA_SKIP_DB_TESTS=1 で skip・Task 2 checkpoint で人手実行）

### Task 2: 実 DB backfill 実行 + bug fix + 6 検証 PASS (commit 006728d)

Task 2 の human-verify checkpoint で orchestrator が CLI を実行した結果、**INSERT 実行時点で SQL 型エラー**が発生:

```
ERROR: column "race_date" is of type date but expression is of type integer
HINT: You will need to rewrite or cast the expression.
```

raw fingerprint 取得後・staging INSERT の段階で失敗したため DB は無傷（atomic swap 未到達・`DROP+RENAME` 未実行）。

**Root cause (Rule 1 bug):** `_idempotent_backfill_label` の SELECT 列構築で positional mismatch があった:
- INSERT 列リストは `_LABEL_INSERT_COLUMNS`（race_date は index 7）
- SELECT 側は `fl.<race_date 以外の全列> + nr.race_date`（末尾 append）
- これにより INSERT col[7]=race_date（date 型）に SELECT expr[7]=racenum（integer）が割り当てられ date/integer 型不一致

**Fix:** SELECT 側を `cols_list` と完全同一順序に整列し、race_date 位置だけ `nr.race_date` で差し替え（末尾 append 廃止）:

```python
cols_list = list(_LABEL_INSERT_COLUMNS)
insert_cols_sql = ", ".join(cols_list)
select_cols_sql = ", ".join(
    "nr.race_date" if c == "race_date" else f"fl.{c}" for c in cols_list
)
```

docstring の SELECT 句説明も「位置完全整列・末尾 append しない」に更新。9 unit tests は全て GREEN のまま（`inspect.getsource` regression は古い phrasing に依存しなかった）。

## Verification

### Unit tests (KEIBA_SKIP_DB_TESTS=1)

```
uv run pytest tests/test_label_race_date_backfill.py -q
=> 9 passed, 1 skipped (live-DB)
```

### Live-DB script (uv run python scripts/run_label_race_date_backfill.py)

6 検証全て PASS・exit 0:

| # | Check | Result |
|---|-------|--------|
| (a) | masked raw fingerprint 表示 | PASS（パスワード `***`） |
| (b) | rows_backfilled == non_null_race_date_count == 554267 | PASS（554267 / 554267） |
| (c) | run#1 と run#2 が同一 rowcount + checksum | PASS（554267 / `554267\|554267` で一致） |
| (d) | `idempotent 検証: PASS` ログ | PASS |
| (e) | `raw 不変性確認: PASS` ログ | PASS |
| (f) | `race_date 全行非 NULL: PASS (554267/554267)` + exit 0 | PASS |

raw fingerprint（baseline と一致・D-06 二重保護）:

```
row_counts={'n_race': {'total': 71972, 'jra': 40035},
            'n_uma_race': {'total': 881202, 'jra': 554610},
            'n_harai': {'total': 39580, 'jra': 39580},
            'n_hyosu': {'total': 0, 'jra': 0},
            'n_odds_tanpuku': {'total': 554217, 'jra': 554217}}
```

baseline と完全一致（failure 時点・fix 後 2回実行 とも同一 row_counts）・raw 層は一切不変。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] INSERT/SELECT positional mismatch (date/integer 型エラー)**

- **Found during:** Task 2 (live-DB backfill 実行)
- **Issue:** `_idempotent_backfill_label` が INSERT 列リスト（race_date=index 7）と SELECT 式リスト（`fl.<race_date 以外> + nr.race_date` 末尾 append）で positional mismatch を起こし、INSERT col[7]=race_date（date 型）に整数列が割り当てられて `column "race_date" is of type date but expression is of type integer` で INSERT が失敗した。Task 1 unit test（mock cursor）では発覚しなかった（mock は SQL 構文を検証しないため）。
- **Fix:** SELECT 式リストを `cols_list` と完全同一順序に構築し、`race_date` 位置だけ `nr.race_date` で差し替える per-column comprehension に変更（末尾 append 廃止）。INSERT col[i] ← SELECT expr[i] の位置完全対応を構造的に保証。
- **Files modified:** src/etl/label_race_date_backfill.py
- **Commit:** 006728d

### その他

Task 1 の 9 unit tests は fix 後も全て GREEN・`inspect.getsource` regression assertion は古い phrasing に依存していなかったため test 側の更新は不要だった。

## Authentication Gates

(該当なし・Task 2 checkpoint は orchestrator が user authorization を得て実行済み・DB 認証情報は Settings から masked DSN 経由で取得)

## Known Stubs

(該当なし・本 plan の成果物は全て実 DB で稼働検証済・race_date 列は全行非 NULL で backfill 済)

## TDD Gate Compliance

Task 1 は `type="tdd" tdd_phase="red-green"` に従い RED/GREEN gate を検証:

- **RED gate:** `test(03-02): RED failing tests for label_race_date_backfill` (commit b0dfaf3) — 9 failing tests 作成
- **GREEN gate:** `feat(03-02): implement label_race_date_backfill with staging-swap` (commit a878f6a) — 9 tests GREEN（1 skipped live-DB）
- **REFACTOR gate:** 該当なし（実装は既に Phase 2 idiom の直接踏襲・簡潔）
- **Live-DB verify gate:** Task 2 checkpoint で orchestrator 実行→bug 発覚→Rule 1 fix (006728d)→再実行で 6 検証 PASS

TDD gate sequence 完全準拠。

## Threat Flags

(該当なし・threat_model T-03-05/06/07/08/09/R-M7 の mitigate が全て実装済:
T-03-05 raw REVOKE + assert_raw_unchanged / T-03-06 pg_advisory_xact_lock /
T-03-07 明示的 reader role GRANT 再発行 (Identifier) / T-03-08 non_null_race_date_count==554267 検証 /
T-03-09 2回実行 checksum 一致 / T-03-R-M7 INCLUDING ALL + GRANT 再発行)

## Self-Check: PASSED

- src/etl/label_race_date_backfill.py: FOUND
- scripts/run_label_race_date_backfill.py: FOUND
- tests/test_label_race_date_backfill.py: FOUND (9 passed / 1 skipped)
- commit b0dfaf3 (RED): FOUND in git log
- commit a878f6a (GREEN impl): FOUND in git log
- commit f3ac6ea (GREEN CLI): FOUND in git log
- commit 006728d (Rule 1 fix): FOUND in git log
- label.fukusho_label.race_date 全行非 NULL (554267/554267): VERIFIED via live script
- raw fingerprint unchanged vs baseline: VERIFIED (n_race/n_uma_race/n_harai/n_odds_tanpuku 全て同一)
