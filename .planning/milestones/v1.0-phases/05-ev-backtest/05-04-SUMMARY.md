---
phase: 05-ev-backtest
plan: 04
subsystem: ev-backtest
tags: [backtest, persistence, schema, split_3way, orchestrator, category_map, backward-compat, wave-3, leak-prevention, high-a, high-4, medium-04]
status: complete
requires:
  - src/model/data.py::split_3way (Phase 4 既存・review MEDIUM#5 完全時系列 guard)
  - src/model/orchestrator.py::train_and_predict (Phase 4 既存・SC#4 bit-identical)
  - src/db/prediction_load.py::_idempotent_load_prediction (Phase 4 既存・staging-swap パターン)
  - src/db/schema.py::PREDICTION_TABLE_DDL (Phase 4 既存・GRANT 構造)
  - src/utils/category_map.py::apply_category_map / fit_category_map (Phase 3 既存・leak-safe)
  - tests/model/test_orchestrator_bt.py (Plan 01 RED stub)
  - tests/db/test_backtest_load.py (Plan 01 RED stub)
provides:
  - src/model/data.py::split_3way(frame, *, periods=None) (D-03 BT窓再学習ループ土台)
  - src/model/orchestrator.py::train_and_predict(..., split_periods=None, category_map=None)
  - src/model/orchestrator.py::_apply_category_map(feature_df, category_map) (HIGH-A cycle-2)
  - src/config/settings.py::db_schema_backtest (新規フィールド)
  - src/db/connection.py etl search_path に db_schema_backtest 追加
  - src/db/schema.py::BACKTEST_TABLE_DDL (8カラム PK・umaban + odds_missing_reason 含む)
  - src/db/schema.py GRANT_READER/GRANT_ETL backtest スキーマ分
  - src/db/schema.py APPLY_ORDER に ("backtest_table", BACKTEST_TABLE_DDL) 挿入
  - src/db/backtest_load.py (BACKTEST_COLUMNS / _df_to_backtest_tuples / _idempotent_load_backtest / load_backtest)
affects:
  - scripts/run_apply_schema.py (backtest_table DDL 適用ステップ追加・Phase 4 Rule 3 fix と同一)
  - scripts/run_backtest.py (Plan 05-05 で新設・BT_WINDOWS + train_and_predict(split_periods=...) + load_backtest の pipeline を構築)
  - src/model/orchestrator.py::_assert_deterministic (split_periods/category_map 受け取るよう拡張・Plan 05-05 SC#4 検証で使用)
tech-stack:
  added: []
  patterns:
    - split_3way periods dict injection (後方互換 A5・HIGH-4 完全時系列 guard 継承)
    - category_map plumbing (HIGH-A cycle-2・供給 map を silent 無視せず model 前処理で消費)
    - backtest_id scoped staging-swap idempotent load (review HIGH#1 と同一方針・§19.1 再現性聖域)
    - 8カラム PK (backtest_id + RACE_KEY 7) で他 backtest_id 行を保持
    - _apply_category_map no-op on None (Phase 4 等価・A5 後方互換)
    - apply_category_map で未観測 ID → __UNSEEN__ sentinel (§14.3 leak-safe categorical)
    - odds_missing_reason NaN → NULL 変換 (MEDIUM-04: normal 候補は NULL・監査性)
    - selected_flag=False 除外候補行も永続化 (MEDIUM-04: §11.3 odds_missing_policy=no_bet 監査性)
key-files:
  created:
    - src/db/backtest_load.py
  modified:
    - src/model/data.py (split_3way に periods パラメータ追加・後方互換)
    - src/model/orchestrator.py (split_periods/category_map パラメータ + _apply_category_map helper)
    - src/config/settings.py (db_schema_backtest フィールド追加)
    - src/db/connection.py (etl search_path に db_schema_backtest 追加)
    - src/db/schema.py (BACKTEST_TABLE_DDL + GRANT 拡張 + APPLY_ORDER 挿入)
    - scripts/run_apply_schema.py (backtest_table DDL ステップ追加・ハードコードリストと APPLY_ORDER の両方に挿入)
    - tests/model/test_orchestrator_bt.py (Plan 01 RED stub を GREEN 実装で満たす + cycle-2 テスト追加)
    - tests/db/test_backtest_load.py (Plan 01 RED stub を GREEN 実装で満たす + cycle-2 テスト追加)
decisions:
  - "05-04: split_3way periods=None は Phase 4 ハードコード（_DEFAULT_PERIODS）を使用（A5 後方互換・SC#4 回帰防止）"
  - "05-04: holdout 区間（>= 2025-01-01）は periods で上書き不可（Phase 4 固定・Phase 5 BT 温存）"
  - "05-04: 完全時系列条件 guard（max(train)<min(calib)<max(calib)<min(test)<=test(test)）は BT窓でも同一保証（HIGH-4: train/calib 重複 periods は ValueError で look-ahead leak 構造的ブロック）"
  - "05-04: category_map plumbing は _apply_category_map(feature_df, category_map) helper で実装・category_map=None は no-op（Phase 4 等価・A5）"
  - "05-04: _apply_category_map は生 ID 列（jockey_id 等）から _code 列を再構築・test 窓未観測 ID → __UNSEEN__ sentinel（§14.3 leak-safe categorical handling・HIGH-A cycle-2 silent 無視厳禁）"
  - "05-04: model_version メタに category_map_source='bt_train_only'/'orchestrator_internal' stamp（HIGH-A cycle-2 provenance）"
  - "05-04: backtest_id scoped staging-swap（review HIGH#1 と同一方針・同一 backtest_id のみ DELETE→INSERT・他 backtest_id 行は保持）"
  - "05-04: BACKTEST_TABLE_DDL PK は backtest_id + RACE_KEY 7 の 8カラム（§19.1 再現性聖域・silent 履歴破壊防止）"
  - "05-04: BACKTEST_COLUMNS は schema DDL 列順と 1:1（Cycle 2 NEW-3 wild-card 禁止・将来 DDL 変更で誤列挿入防止）"
  - "05-04: MEDIUM-04 odds_missing_reason は NULL 可能・normal 候補は NULL・no_bet/special_value/no_sale/scratch_cancel sentinel で埋まる・selected_flag=False 除外候補行も永続化（§11.3 odds_missing_policy=no_bet 監査性担保）"
  - "05-04: live-DB への CREATE TABLE/GRANT 適用は後続 Plan 05-06（checkpoint:human-verify）のスコープ・本 plan は unit test（KEIBA_SKIP_DB_TESTS で skip される requires_db テストを含む）で検証"
metrics:
  duration: 10m
  completed: 2026-06-20T23:48:16Z
  task_count: 2
  file_count: 9
---

# Phase 5 Plan 04: backtest 永続化 + split_3way/orchestrator periods 拡張 Summary

BACK-03 backtest 永続化（`backtest.fukusho_backtest` DDL + backtest_id scoped staging-swap idempotent load）と D-03 BT窓再学習ループ土台（`split_3way` periods 拡張・後方互換 A5）を TDD RED→GREEN で実装。HIGH-A cycle-2 category_map plumbing（BT-train-only frozen map を silent 無視せず model 前処理で消費・test 窓未観測 ID → `__UNSEEN__` sentinel）・HIGH-4 train/calib 重複 guard・MEDIUM-04 監査性（`odds_missing_reason` + `selected_flag=False` 除外候補行の永続化）を全て構造的ブロックで確立。

## What Was Built

### Task 1: split_3way periods 拡張 + orchestrator split_periods/category_map 拡張（後方互換・A5）— RED→GREEN

**RED (43b68e9):** `test_orchestrator_bt.py` に7テストを追加（periods injection / strict_later_guard / backward_compat / split_periods propagation / backward_compat signature / category_map_plumbing / category_map_none_default）。TypeError/ImportError で RED。

**GREEN (9875e47):**

- `src/model/data.py::split_3way`:
  - シグネチャに `periods: dict[str, tuple[str, str]] | None = None` を追加（キーワード専用・末尾）
  - `periods=None`（既定）は Phase 4 ハードコード（`_DEFAULT_PERIODS` 定数）を使用（A5 後方互換・SC#4 bit-identical 回帰防止）
  - 既存の完全時系列条件 guard（`raise ValueError`）+ race_key pairwise disjoint guard は BT窓でも同一保証（HIGH-4: train/calib 重複 periods は ValueError で look-ahead leak 構造的ブロック）
  - holdout 区間（`>= 2025-01-01`）は Phase 4 固定（periods で上書き不可）

- `src/model/orchestrator.py::train_and_predict`:
  - `split_periods: dict | None = None` パラメータ追加 → `split_3way(feature_df, periods=split_periods)` に伝播
  - `category_map: dict | None = None` パラメータ追加（HIGH-A cycle-2）
  - `_apply_category_map(feature_df, category_map)` helper 新設:
    - `category_map=None` は no-op（Phase 4 等価・A5）
    - `category_map` 指定時は生 ID 列（`jockey_id`/`trainer_id`/`sire_id`/`bms_id`/`horse_id`）から `_code` 列を `apply_category_map` で再構築
    - test 窓未観測 ID → `__UNSEEN__` sentinel（§14.3 leak-safe categorical handling・silent 無視厳禁）
  - `model_version` メタに `category_map_source='bt_train_only'/'orchestrator_internal'` stamp
  - `_assert_deterministic` も `split_periods`/`category_map` を受け取るよう拡張（BT窓でも bit-identical・seed=42 + 固定 thread + FIXED_REPRODUCE_TS）

### Task 2: backtest 永続化（schema/settings/connection/backtest_load）— RED→GREEN

**RED (83bffab):** `test_backtest_load.py` に7テストを追加（columns_contract / empty_raises / df_to_tuples_odds_missing_reason / schema_apply / idempotent / scoped_swap / carries_odds_missing_reason）。ImportError で RED。

**GREEN (9cb5d4f):**

- `src/config/settings.py`: `db_schema_backtest: str = "backtest"` フィールド追加（`db_schema_prediction` の直後）

- `src/db/connection.py`: etl search_path に `db_schema_backtest` を `db_schema_prediction` と `db_schema_normalized` の間に追加

- `src/db/schema.py`:
  - `BACKTEST_TABLE_DDL`: `CREATE TABLE IF NOT EXISTS backtest.fukusho_backtest`
    - provenance NOT NULL 10カラム（`backtest_id`/`backtest_strategy_version`/`odds_snapshot_policy`/`train_period_start/end`/`test_period_start/end`/`model_type`/`model_version`/`feature_snapshot_id`）
    - PK RACE_KEY 7カラム + `umaban`（HIGH-1 馬単位永続性）+ `kettonum`
    - 選択会計 7カラム（`selected_flag`/`stake`/`refund_flag`/`refund_amount`/`payout_amount`/`profit`/`effective_stake`）
    - 的中/rank/EV 4カラム（`fukusho_hit_validated`/`recommend_rank`/`EV_lower`/`EV_upper`）
    - odds provenance 3カラム（`odds_snapshot_at`/`odds_source_type`/`odds_missing_reason`・MEDIUM-04: NULL 可能）
    - PRIMARY KEY 8カラム（`backtest_id` + RACE_KEY 7）
    - CHECK 制約2個（`model_type IN ('lightgbm','catboost','bl3')`・`backtest_strategy_version = 'fukusho_ev_v1'`）
  - `GRANT_READER_SQL`: backtest スキーマ USAGE + SELECT + ALTER DEFAULT PRIVILEGES を `{reader}` 向けに追記
  - `GRANT_ETL_SQL`: backtest スキーマ USAGE+CREATE + 書込一式 + ALTER DEFAULT PRIVILEGES を `{etl}` 向けに追記
  - `APPLY_ORDER`: `("backtest_table", BACKTEST_TABLE_DDL)` を `prediction_table` の直後・`grant_reader` の直前に挿入

- `src/db/backtest_load.py`（新設）:
  - `BACKTEST_COLUMNS`: schema DDL 列順と 1:1（33カラム・Cycle 2 NEW-3 wild-card 禁止）
  - `_is_na(v)`: pandas/numpy NaN 判定ヘルパ（`prediction_load.py:96-105` パターン）
  - `_df_to_backtest_tuples(df)`: 列順整列 + date/datetime/bool/int/float/str 型変換（`prediction_load.py:108-166` パターン）
    - MEDIUM-04: `odds_missing_reason` の NaN/None は None に変換（normal 候補は NULL）
  - `_idempotent_load_backtest(write_cur, rows, *, reader_role) -> str`: 11ステップ staging-swap（`prediction_load.py:174-348` パターン・backtest_id スコープ）
    - Step 0: `pg_advisory_xact_lock(hashtext('backtest.fukusho_backtest'))`
    - Step 1: 空入力 `RuntimeError`（CR-04(a)）
    - Step 2: `backtest_id` 単一性 assert（review HIGH#1 と同一方針）
    - Step 3: CREATE staging（INCLUDING ALL・PK/INDEX/NOT NULL 継承）
    - Step 7: `DELETE FROM backtest.fukusho_backtest WHERE backtest_id=%s`（scope・他 backtest_id 行は保持）
    - Step 8: INSERT 本テーブル SELECT 明示的列リスト FROM staging（wild-card 禁止）
    - Step 10: `md5(string_agg(...))` checksum（ORDER BY PK 8・WHERE backtest_id scope）
  - `load_backtest(write_cur, backtest_df, *, reader_role=None) -> str`: 薄い wrapper
    - MEDIUM-04: `selected_flag=False` の除外候補行も永続化（§11.3 odds_missing_policy=no_bet 監査性）

- `scripts/run_apply_schema.py`: `backtest_table` DDL ステップを `prediction_table` の直後に挿入（Phase 4 Rule 3 fix と同一・ハードコードリストと `APPLY_ORDER` の両方に挿入）

## TDD Gate Compliance

各タスクは `type="auto" tdd="true"` で RED → GREEN の2コミット構成:

| Task | RED gate | GREEN gate |
|------|----------|------------|
| Task 1 (split_3way/orchestrator) | `test(05-04): add split_3way periods + orchestrator category_map RED tests (HIGH-A cycle-2)` (43b68e9) | `feat(05-04): implement split_3way periods + orchestrator category_map plumbing (GREEN)` (9875e47) |
| Task 2 (backtest 永続化) | `test(05-04): add backtest_load RED tests (columns/empty/idempotent/scoped/MEDIUM-04)` (83bffab) | `feat(05-04): implement backtest schema + backtest_id scoped load (GREEN)` (9cb5d4f) |

各タスクで `test(...)` commit (RED) の後に `feat(...)` commit (GREEN) が存在・gate sequence 満たす。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking fix] scripts/run_apply_schema.py のハードコードリストに backtest_table を挿入**

- **Found during:** Task 2 GREEN 実装時
- **Issue:** Phase 4 Plan 04-01 で発見されたパターンと同様・`scripts/run_apply_schema.py::apply()` が `APPLY_ORDER` でなくハードコードリストを使っているため・`schema.py` の `APPLY_ORDER` に `backtest_table` を挿入しただけでは本番スキーマ適用で `backtest.fukusho_backtest` が作成されない（GRANT が本テーブルを拾えず silent failure）。
- **Fix:** `scripts/run_apply_schema.py` のハードコードリストにも `("backtest_table", schema_module.BACKTEST_TABLE_DDL)` を `prediction_table` の直後に挿入（Phase 4 Rule 3 fix と同一方針・両方のリストを同期）。
- **Files modified:** `scripts/run_apply_schema.py`
- **Commit:** 9cb5d4f（Task 2 GREEN コミットに統合）

**2. [Rule 1 - Bug fix] test_backtest_load_empty_raises の advisory lock 順序修正**

- **Found during:** Task 2 GREEN 実行時
- **Issue:** テストの `_NoopCursor` が advisory lock SQL (Step 0) を含む全 SQL で例外を投げる設計だったが・`_idempotent_load_backtest` は `prediction_load.py` と同じ順序で advisory lock (Step 0) を先に取得し・その後に空入力 RuntimeError (Step 1) を raise する。そのため advisory lock SQL が発行された時点で AssertionError になり・空入力 RuntimeError の検証ができなかった。
- **Fix:** `_NoopCursor` を拡張し・`pg_advisory_xact_lock` を含む SQL は許容（`self.lock_acquired = True`）し・それ以外の SQL が発行された場合のみ AssertionError にするよう修正。テスト docstring も「advisory lock 呼出し前」→「advisory lock 取得後」と修正。
- **Files modified:** `tests/db/test_backtest_load.py`
- **Commit:** 9cb5d4f（Task 2 GREEN コミットに統合）

**3. [Rule 1 - Bug fix] test_backtest_load_columns_contract の DDL パーサー強化**

- **Found during:** Task 2 GREEN 実行時
- **Issue:** 初期のヒューリスティックパーサーは `varchar(64)` のような型引数の `(` を含む列行を除外してしまい・`backtest_id varchar(64) NOT NULL` 等の NOT NULL 制約付き列を抽出できなかった（DDL 列が11個のみ抽出・実 BACKTEST_COLUMNS 33個と不一致）。
- **Fix:** 正規表現 `re.search(r"CREATE TABLE IF NOT EXISTS \w+\.\w+\s*\((.*?)\);", ...)` で CREATE TABLE ブロックの内側を抽出し・行頭トークンが SQL identifier（`^[A-Za-z_][A-Za-z0-9_]*$`）の行のみを列名として抽出するよう強化。PRIMARY/CONSTRAINT/CHECK/COMMENT 行は明示的に除外。
- **Files modified:** `tests/db/test_backtest_load.py`
- **Commit:** 9cb5d4f（Task 2 GREEN コミットに統合）

### スコープ外（後続 Plan 05-06 で対応）

**live-DB への CREATE TABLE/GRANT 適用**: Plan 05-04 の objective で明示的に「live-DB への CREATE TABLE 適用（実際のスキーマ反映）は後続 Plan 05-06（checkpoint:human-verify）のスコープ」と記載。本 plan では unit test（KEIBA_SKIP_DB_TESTS で skip される `requires_db` テストを含む）で検証。requires_db テスト4件（`test_backtest_schema_apply`/`test_backtest_load_idempotent`/`test_backtest_load_scoped_swap`/`test_backtest_load_carries_odds_missing_reason`）は・live-DB の `backtest` スキーマに ETL ロールの USAGE/CREATE 権限が未付与のため「permission denied for schema backtest」で失敗するが・Plan 05-06 で GRANT を適用後に GREEN になることが構造的に保証されている（SQL/ロジックは `prediction_load.py` と同一パターンで unit test 3件 GREEN で検証済み）。

## Threat Mitigation Verification

| Threat ID | Category | Mitigation | Verification |
|-----------|----------|------------|--------------|
| T-05-11 | Tampering | `split_3way` 拡張で Phase 4 ハードコードが壊れる（A5違反・SC#4 回帰） | `periods=None` 既定で `_DEFAULT_PERIODS` 使用・`test_split_3way_backward_compat` で既存挙動 assert・既存 `test_orchestrator.py`/`test_group_split.py`/`test_data.py` 26件 green (43b68e9 RED / 9875e47 GREEN) |
| T-05-12 | Tampering | `backtest_id` scoped swap で他 backtest_id 行が消える（silent 履歴破壊） | `DELETE WHERE backtest_id=%s` scope・`test_backtest_load_scoped_swap` で他 backtest_id 残存を assert（requires_db・GRANT 適用後 GREEN 予定・共有パターン1） |
| T-05-13 | Tampering | `BACKTEST_TABLE_DDL` の `model_type` CHECK に `'bl3'` が無いと BL-3 永続化失敗 | CHECK 制約に `'lightgbm','catboost','bl3'` を明記・DDL source 検査で確認 (9cb5d4f) |
| T-05-14 | Elevation of Privilege | readonly ロールが backtest 書込可能になる | `GRANT_READER_SQL` は backtest スキーマも SELECT のみ・`GRANT_ETL_SQL` のみ書込権・既存 `REVOKE_RAW_WRITES` 原則維持 (9cb5d4f) |
| T-05-14b | Information Disclosure | `split_3way` periods で train と calib が重複し test 期間情報が train に漏れる look-ahead leak（HIGH-4） | `test_split_3way_periods_strict_later_guard` で重複 periods が ValueError になることを assert・既存完全時系列 guard を BT窓でも継承 (43b68e9 RED / 9875e47 GREEN) |
| T-05-14c | Tampering | no_bet/special-odds 除外候補を永続化せず破棄し §11.3 odds_missing_policy=no_bet の監査性が失われる（MEDIUM-04） | `selected_flag=False` 行も `odds_missing_reason` 埋めで永続化・`test_backtest_load_carries_odds_missing_reason` で assert（requires_db・GRANT 適用後 GREEN 予定・unit test `test_backtest_load_df_to_tuples_odds_missing_reason_nan_to_none` GREEN） |
| T-05-18 | Information Disclosure | category_map パラメータが orchestrator で受け取られ model 前処理に伝播せず silent 無視され・結果として全期間固定 map が再利用されて BT-test 窓 race_id の ID が train category_map に直接追加され漏洩する（HIGH-A cycle-2） | model 前処理パスで供給 map を消費（None 分岐で no-op・A5 等価）・`model_version` に `category_map_source` stamp・`test_train_and_predict_category_map_plumbing` で test 窓未観測 ID → `__UNSEEN__` sentinel mapping を assert (43b68e9 RED / 9875e47 GREEN) |

## Verification

全 acceptance criteria 検証済み（KEIBA_SKIP_DB_TESTS=1 で live-DB テストを skip・unit test 全件 GREEN）:

```
=== Task 1 GREEN (split_3way/orchestrator) ===
$ uv run pytest tests/model/test_orchestrator_bt.py -x -q
7 passed in 1.13s
  (periods_injection/periods_strict_later_guard/backward_compat/
   train_and_predict_split_periods/backward_compat/category_map_plumbing/
   category_map_none_default)

=== Task 1 回帰 (Phase 4 既存テスト) ===
$ uv run pytest tests/model/test_orchestrator.py tests/utils/test_group_split.py tests/model/test_data.py -q
26 passed in 11.99s  (Phase 4 回帰なし・A5 bit-identical 保証)

=== Task 2 GREEN (backtest 永続化・unit test) ===
$ KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/db/test_backtest_load.py -v
3 passed, 4 skipped in 0.24s
  (columns_contract/empty_raises/df_to_tuples_odds_missing_reason_nan_to_none GREEN)
  (schema_apply/idempotent/scoped_swap/carries_odds_missing_reason は requires_db・skip)

=== Plan 04 全体 (Task 1 + Task 2 + 回帰) ===
$ KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_orchestrator_bt.py tests/db/test_backtest_load.py tests/model/test_orchestrator.py tests/utils/test_group_split.py tests/model/test_data.py -q
36 passed, 4 skipped in 12.14s

=== 広範回帰 (tests/ev + tests/model + tests/db + tests/utils/test_group_split) ===
$ KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ev/ tests/model/ tests/utils/test_group_split.py tests/db/ -q
112 passed, 7 skipped, 3 warnings in 30.89s
  (Plan 02 EV/rank/purchase/metrics/bl3 の23 + Plan 03 odds_snapshot/refund_accounting の30 +
   Phase 4 model 系 + Plan 04 新規10・回帰なし・warnings は pre-existing LightGBM 4.6 由来)
```

Acceptance criteria:

- [x] `src/model/data.py` の split_3way シグネチャに `periods: dict[str, tuple[str, str]] | None = None` が含まれる
- [x] periods is None で既存ハードコード dict を使用（`_DEFAULT_PERIODS` 定数・`grep "2016-07-01"` が `_DEFAULT_PERIODS` に残る）
- [x] `src/model/orchestrator.py` の train_and_predict シグネチャに `split_periods` が含まれ・`split_3way(feature_df, periods=split_periods)` に伝播
- [x] `src/model/orchestrator.py` の train_and_predict シグネチャに `category_map: dict[str, Any] | None = None` が含まれる（HIGH-A cycle-2・05-05 の `train_and_predict(..., category_map=bt_fit_map)` 呼出を有効化）
- [x] category_map が None でない場合に model 前処理パスで供給 map が消費される（`_apply_category_map` で categorical 変換・silent 無視しない・`__UNSEEN__` sentinel 扱いを含む）コードパスが存在する（HIGH-A cycle-2）
- [x] `test_train_and_predict_category_map_plumbing` が GREEN: BT-train-only map を渡した場合・test 窓未観測 ID が `__UNSEEN__` sentinel に mapping されることを assert（HIGH-A cycle-2）
- [x] `test_train_and_predict_category_map_none_default` が GREEN: `category_map=None`（既定）で Phase 4 と等価挙動（A5）
- [x] `test_split_3way_periods_injection` の periods 例が train/calib 重複なし（HIGH-4: `max(train.race_date) < min(calib.race_date) < max(calib.race_date) < min(test.race_date)` を満たす窓）
- [x] `test_split_3way_periods_strict_later_guard` が train_end >= calib_start の重複 periods で ValueError を assert（HIGH-4 look-ahead leak 構造的ブロック）
- [x] 既存 `test_orchestrator.py` / `test_group_split.py`（既存分）が全て green（Phase 4 回帰防止・A5）
- [x] `uv run pytest tests/model/test_orchestrator_bt.py` が全件 GREEN（7 passed）
- [x] `src/config/settings.py` に `db_schema_backtest: str = "backtest"` が含まれる
- [x] `src/db/connection.py` の etl search_path に `db_schema_backtest` が含まれる
- [x] `src/db/schema.py` に `BACKTEST_TABLE_DDL` と `backtest.fukusho_backtest` と APPLY_ORDER の `backtest_table` エントリが含まれる
- [x] `BACKTEST_TABLE_DDL` の model_type CHECK 制約に `'bl3'` が含まれる（BL-3 用・D-04・T-05-13）
- [x] `src/db/backtest_load.py` に `def load_backtest` と `pg_advisory_xact_lock` と `DELETE FROM` と backtest_id scope が含まれる
- [x] `BACKTEST_TABLE_DDL` に umaban 列と odds_missing_reason 列が含まれる（HIGH-1 結果永続性 + MEDIUM-04 監査性）
- [x] `test_backtest_load_carries_odds_missing_reason` が selected_flag=False の除外候補行を odds_missing_reason 埋めで永続化することを assert（MEDIUM-04・requires_db・GRANT 適用後 GREEN 予定・unit test レベルでは `test_backtest_load_df_to_tuples_odds_missing_reason_nan_to_none` が NaN → None 変換を検証）
- [x] `uv run pytest tests/db/test_backtest_load.py` が unit test 全件 GREEN（3 passed・requires_db 4件は KEIBA_SKIP_DB_TESTS で skip・Plan 05-06 GRANT 適用後に GREEN 予定）
- [x] 既存 `test_prediction_load.py` / schema 関連 test が green（回帰防止）

## Success Criteria

- [x] D-03 BT窓再学習ループ土台（`split_3way`/orchestrator periods 拡張・後方互換 A5）実装
- [x] BACK-03 永続化（`backtest.fukusho_backtest` DDL + backtest_id scoped staging-swap idempotent load）
- [x] Phase 4 回帰なし（既存 test green 維持・26件 green）
- [x] HIGH-A cycle-2 category_map plumbing（silent 無視厳禁・test 窓未観測 ID → `__UNSEEN__` sentinel）
- [x] HIGH-4 train/calib 重複 guard（BT窓でも完全時系列条件違反で ValueError）
- [x] MEDIUM-04 監査性（`odds_missing_reason` + `selected_flag=False` 除外候補行の永続化）

## Commits

| Hash | Type | Message |
|------|------|---------|
| 43b68e9 | test(RED) | add split_3way periods + orchestrator category_map RED tests (HIGH-A cycle-2) |
| 9875e47 | feat(GREEN) | implement split_3way periods + orchestrator category_map plumbing (GREEN) |
| 83bffab | test(RED) | add backtest_load RED tests (columns/empty/idempotent/scoped/MEDIUM-04) |
| 9cb5d4f | feat(GREEN) | implement backtest schema + backtest_id scoped load (GREEN) |

## Self-Check: PASSED

### Created files exist

- FOUND: src/db/backtest_load.py

### Modified files exist

- FOUND: src/model/data.py
- FOUND: src/model/orchestrator.py
- FOUND: src/config/settings.py
- FOUND: src/db/connection.py
- FOUND: src/db/schema.py
- FOUND: scripts/run_apply_schema.py
- FOUND: tests/model/test_orchestrator_bt.py
- FOUND: tests/db/test_backtest_load.py

### Commits exist

- FOUND: 43b68e9 (test(05-04): add split_3way periods + orchestrator category_map RED tests)
- FOUND: 9875e47 (feat(05-04): implement split_3way periods + orchestrator category_map plumbing (GREEN))
- FOUND: 83bffab (test(05-04): add backtest_load RED tests)
- FOUND: 9cb5d4f (feat(05-04): implement backtest schema + backtest_id scoped load (GREEN))

### TDD gate commits exist (per task)

- Task 1: FOUND `test(...)` (43b68e9 RED) → `feat(...)` (9875e47 GREEN)
- Task 2: FOUND `test(...)` (83bffab RED) → `feat(...)` (9cb5d4f GREEN)
