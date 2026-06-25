---
phase: 06-evaluation-calibration-gates
plan: 04
subsystem: database
tags: [postgres, idempotent-migration, is_primary-flag, staging-swap-idiom, leak-prevention, fail-loud-postcondition]

# Dependency graph
requires:
  - phase: 04-model-prediction
    provides: prediction.fukusho_prediction DDL (11 PK + 3 CHECK 制約) + PREDICTION_COLUMNS (15列) + model_version scoped staging-swap idiom
  - phase: 06-evaluation-calibration-gates/02
    provides: evaluator.py 拡張（quantile_max_dev/ECE/MCE・check_acceptance_gate）
  - phase: 06-evaluation-calibration-gates/03
    provides: segment_eval.py (6軸 segment calibration curve)
provides:
  - prediction.fukusho_prediction.is_primary 列（boolean NOT NULL DEFAULT false・CHECK prediction_is_primary_domain）
  - PREDICTION_COLUMNS 16列（is_primary 末尾追加・Pitfall 4 3ファイル連鎖）
  - set_primary_model 関数（model_version scoped・idempotent・0 行 UPDATE で RuntimeError post-condition・as_of_datetime canonical parse）
  - _canonicalize_as_of_datetime helper（str/datetime/pd.Timestamp 正規化・REVIEW C11）
  - _BOOL_COLS 定数 + _df_to_prediction_tuples の is_primary 型処理（None→False 正規化）
  - tests/db/test_is_primary_flag.py（17 テスト・requires_db・ライブ DB GREEN）
affects: [06-evaluation-calibration-gates/05 (run_evaluation.py が set_primary_model を呼ぶ), 07-streamlit-ui (is_primary=true の主モデルを表示)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3ファイル連鎖 DB migration（schema DDL + predict.py PREDICTION_COLUMNS + prediction_load.py 型処理）・Pitfall 4 回帰防止は列数一致 assert で機械検証"
    - "idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS + DROP CONSTRAINT IF EXISTS → ADD CONSTRAINT（既存 staging-swap idiom の拡張）"
    - "set_primary_model post-condition assert（0 行 UPDATE で RuntimeError + SELECT で true が1 model_type のみ検証）・silent no-op を fail-loud に転換"
    - "datetime canonical parse（pd.Timestamp(as_of_datetime).to_pydatetime()）で timezone/microsecond ズレによる 0 行 UPDATE を防止"
    - "テスト挿入行スコープ（model_version='test_..._<uuid4>'）+ try/finally teardown で global DB 状態に依存しない・Plan 06-05 完了後も RED にならない"

key-files:
  created:
    - tests/db/test_is_primary_flag.py
  modified:
    - src/db/schema.py
    - src/model/predict.py
    - src/db/prediction_load.py
    - scripts/run_apply_schema.py
    - tests/model/test_prediction_load.py

key-decisions:
  - "is_primary 列は boolean NOT NULL DEFAULT false で追加（REVIEW HIGH#8・CHECK prediction_is_primary_domain は NOT NULL の二重防御）"
  - "set_primary_model は model_type+model_version+feature_snapshot_id+as_of_datetime スコープで UPDATE（全行 UPDATE でない・silent 履歴破壊防止・staging-swap idiom と同方針）"
  - "0 行 UPDATE は RuntimeError で fail-loud（REVIEW HIGH#7 post-condition・silent no-op 防止）"
  - "as_of_datetime は _canonicalize_as_of_datetime で str/datetime/pd.Timestamp を正規化（REVIEW C11・timezone/microsecond ズレ対策）"
  - "predict_p_fukusho は is_primary=False で初期化（NOT NULL 制約と整合・set_primary_model で True に UPDATE）"
  - "主モデルの選定自体（D-07）は Plan 06-05 Task 2 checkpoint:human-verify で実施（REVIEW C17 重複解消・本 plan は機構と検証のみ提供）"
  - "tests/db/__init__.py は既存 package marker 規約に従い保持（REVIEW Codex LOW cycle-2 明示判断・新規作成不要）"

patterns-established:
  - "post-condition assert idiom: UPDATE rowcount==0 → RuntimeError + SELECT で不変量検証（silent no-op を fail-loud に）"
  - "datetime canonical parse idiom: pd.Timestamp(x).to_pydatetime() で多態入力を正規化（DB バインド前・ズレによる 0 行 UPDATE 防止）"
  - "テスト挿入行スコープ idiom: uuid4 接尾辞付き model_version + try/finally teardown（global DB 状態非依存・後続 plan 完了後も RED にならない）"

requirements-completed: [EVAL-01, EVAL-02]

# Metrics
duration: 約30分（継続 agent：実装2 task は先に完了済み、本サマリは checkpoint 承認後の完了処理）
completed: 2026-06-23
status: complete
---

# Phase 6 Plan 04: is_primary Migration Mechanism Summary

**prediction.fukusho_prediction に is_primary フラグ（NOT NULL DEFAULT false）を追加する 3ファイル連鎖 DB migration + set_primary_model 関数（model_version scoped・idempotent・0 行 UPDATE で RuntimeError post-condition）を実装し、REVIEW HIGH#7/HIGH#8/C10/C11/C17 を解消**

## Performance

- **Duration:** 約30分（実装 task 1+2 完了 + checkpoint:human-verify 承認）
- **Tasks:** 3（task 1: 3ファイル連鎖 migration / task 2: set_primary_model / task 3: checkpoint:human-verify 承認）
- **Files modified:** 6（src 4 + tests 2）

## Accomplishments

- prediction.fukusho_prediction に `is_primary boolean NOT NULL DEFAULT false` 列を idempotent ALTER で追加（REVIEW HIGH#8・CHECK prediction_is_primary_domain は NOT NULL 二重防御）
- PREDICTION_COLUMNS を 15→16 列に拡張（is_primary 末尾）し、3ファイル連鎖（schema.py DDL + predict.py + prediction_load.py 型処理）を Pitfall 4 列数一致 assert で機械検証
- set_primary_model 新規関数（model_type+model_version+feature_snapshot_id+as_of_datetime スコープ・idempotent・両モデル行保持・psycopg.sql.SQL で SQL injection 防御）
- REVIEW HIGH#7 post-condition: 0 行 UPDATE は RuntimeError・SELECT で is_primary=true が1 model_type のみ・>=1 行を検証（silent no-op を fail-loud に）
- REVIEW C11: _canonicalize_as_of_datetime で str/datetime/pd.Timestamp を正規化（timezone/microsecond ズレによる 0 行 UPDATE を防止）
- 17 テスト（requires_db・KEIBA_SKIP_DB_TESTS unset）がライブ DB で全て GREEN・3 回帰テスト（test_prediction_load.py Pitfall 4 修正）も GREEN

## Task Commits

各 task は原子的にコミット：

1. **Task 1: 3ファイル連鎖 is_primary 列追加（schema.py DDL + predict.py PREDICTION_COLUMNS + prediction_load.py 型処理・Pitfall 4）** - `b7b80a3` (feat)
2. **Task 2: set_primary_model 新規関数（model_version scoped・idempotent・D-09・REVIEW HIGH#7 post-condition assert）** - `c685ab2` (feat)
3. **Task 3: is_primary migration 機構承認（checkpoint:human-verify・REVIEW C17 縮小・主モデル選定自体は 06-05 で実施）** - （ファイル変更なし・人間 "approved" で resume）

**Plan metadata:** （本コミットに続く・docs(06-04): complete ...）

## Files Created/Modified

- `src/db/schema.py` - PREDICTION_ADD_IS_PRIMARY_SQL 新規（boolean NOT NULL DEFAULT false + CHECK prediction_is_primary_domain + COMMENT ON COLUMN）+ APPLY_ORDER 拡張
- `src/model/predict.py` - PREDICTION_COLUMNS 16列（is_primary 末尾）+ predict_p_fukusho で is_primary=False 初期化
- `src/db/prediction_load.py` - _BOOL_COLS 定数 + _df_to_prediction_tuples の is_primary 型処理（None→False 正規化）+ set_primary_model 新規関数 + _canonicalize_as_of_datetime helper
- `scripts/run_apply_schema.py` - Rule 3 fix・インライン適用リストに prediction_add_is_primary を追加（Phase 4 04-01 と同一パターン・APPLY_ORDER と同期）
- `tests/db/test_is_primary_flag.py`（新規）- 17 テスト（requires_db・ライブ DB GREEN）: Task 1 9テスト + Task 2 8テスト
- `tests/model/test_prediction_load.py` - Pitfall 4 回帰修正（合成 DataFrame に is_primary=False 追加）

## Decisions Made

- **CHECK 制約の位置付け（REVIEW HIGH#8）:** `boolean NOT NULL DEFAULT false` を明示し、CHECK `prediction_is_primary_domain` (is_primary IN (true,false)) は NOT NULL の二重防御として配置。boolean 型に対し整数挿入は psycopg の型変換で CHECK 以前に拒否されるため、CHECK 自体の検証は制約存在確認（information_schema.check_constraints）にとどめ、NULL INSERT 拒否を主検証とした。
- **テスト挿入行スコープ（REVIEW C10）:** 本番 22,213×2 行（両モデル）の is_primary を assert すると Plan 06-05 完了後（本番で主モデル確定済）に true 行が存在して RED になる。そのため `model_version='test_..._<uuid4>'` の合成行を INSERT → assert → try/finally で DELETE し、global DB 状態に依存しない設計を採用。
- **set_primary_model の post-condition（REVIEW HIGH#7）:** Step 2 の UPDATE rowcount==0 は RuntimeError（fail-loud）。加えて SELECT `count(*) FILTER (WHERE is_primary) GROUP BY model_type` で is_primary=true が1 model_type のみ・>=1 行であることを検証。これにより model_version/as_of_datetime ズレによる silent no-op（主モデルなし状態）を構造的にブロック。
- **as_of_datetime canonical parse（REVIEW C11）:** 引数は ISO8601 文字列・datetime.datetime・pd.Timestamp のいずれかを受付、内部で `pd.Timestamp(as_of_datetime).to_pydatetime()` で canonical 化してから WHERE バインド。timezone/microsecond ズレで 0 行 UPDATE になる経路を閉鎖。
- **主モデル選定の委譲（REVIEW C17）:** 本 plan の checkpoint:human-verify は「is_primary migration 機構」の承認のみに縮小。主モデルの「選定」自体（D-04 基準で lightgbm/catboost いずれにするか）は Plan 06-05 Task 2 checkpoint:human-verify で実施し、06-04 と 06-05 の重複を解消。
- **scripts/run_apply_schema.py 同期（Rule 3）:** APPLY_ORDER に prediction_add_is_primary を追加しただけでは run_apply_schema.py がハードコードリストを使うため適用されない（Phase 4 04-01 と同一の blocking issue）。インライン適用リストにも同エントリを追加し、APPLY_ORDER と同期。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] scripts/run_apply_schema.py のインライン適用リストに prediction_add_is_primary を追加**
- **Found during:** Task 1（3ファイル連鎖 migration）
- **Issue:** APPLY_ORDER に新エントリを追加しただけでは、run_apply_schema.py がハードコードされたインライン適用リストを使うため ALTER が実行されない（Phase 4 plan 04-01 と同一の blocking pattern）
- **Fix:** scripts/run_apply_schema.py のインライン適用リストに `("prediction_add_is_primary", PREDICTION_ADD_IS_PRIMARY_SQL)` を追加し、APPLY_ORDER と同期
- **Files modified:** scripts/run_apply_schema.py
- **Verification:** ライブ DB で ALTER 実行後・information_schema.columns に is_primary（data_type='boolean' AND is_nullable='NO' AND column_default='false'）が存在することを test_alter_adds_is_primary_column で検証
- **Committed in:** b7b80a3（Task 1 commit に含む）

**2. [Rule 1 - Bug] tests/model/test_prediction_load.py の合成 DataFrame に is_primary=False を追加（Pitfall 4 回帰）**
- **Found during:** Task 1（3ファイル連鎖 migration）
- **Issue:** PREDICTION_COLUMNS を 15→16 列に拡張したことで、既存 test_prediction_load.py の合成 DataFrame（15列）が _df_to_prediction_tuples で列数不一致に（Pitfall 4・3ファイル連鎖の典型）
- **Fix:** 合成 DataFrame に is_primary=False 列を追加し16列化
- **Files modified:** tests/model/test_prediction_load.py
- **Verification:** tests/model/test_prediction_load.py の3テスト（test_idempotent_checksum_match 含む）が GREEN
- **Committed in:** b7b80a3（Task 1 commit に含む）

---

**Total deviations:** 2 auto-fixed（1 blocking・1 bug regression）
**Impact on plan:** 両 auto-fix は正確性と機能完了に必須・スコープクリープなし。いずれも Pitfall 4 / Phase 4 04-01 と同一の既知パターン。

## Issues Encountered

- テスト数が plan 期待（15）を上回り17になった：Task 1 で9テスト（plan の8 + test_df_to_prediction_tuples_is_primary_bool）、Task 2 で8テスト（plan の7 + test_canonicalize_as_of_datetime_accepts_str_datetime_timestamp・REVIEW C11 専用）。いずれも plan の behavior 仕様を網羅するものでスコープ内。

## REVIEW Dispositions（本 plan で解消した REVIEW 指摘）

| REVIEW ID | 重要度 | 指摘 | 解消策 | 検証 |
|-----------|--------|------|--------|------|
| HIGH#7 | HIGH | set_primary_model の silent no-op（0 行 UPDATE）で主モデルなし状態 | Step 2 rowcount==0 → RuntimeError + SELECT post-condition（true が1 model_type のみ・>=1 行）| test_set_primary_model_raises_on_zero_rows / test_set_primary_model_post_condition_one_true_per_model_type |
| HIGH#8 | HIGH | is_primary の NULL 許容で CHECK 制約が vacuous | `boolean NOT NULL DEFAULT false` 明示 + predict_p_fukusho False 初期化 + load 時 None→False 正規化 | test_is_primary_not_null_constraint / test_alter_adds_is_primary_column |
| C10 | MEDIUM | 既存行の is_primary assert が Plan 06-05 完了後に RED になる | テスト挿入行スコープ（uuid4 model_version）+ try/finally teardown | test_is_primary_default_false_on_synthetic_rows |
| C11 | MEDIUM | as_of_datetime の timezone/microsecond ズレで 0 行 UPDATE | _canonicalize_as_of_datetime で str/datetime/pd.Timestamp を正規化 | test_canonicalize_as_of_datetime_accepts_str_datetime_timestamp |
| C17 | LOW | 06-04 と 06-05 の checkpoint 重複 | 本 plan checkpoint は「機構承認」のみに縮小・主モデル選定自体は Plan 06-05 Task 2 で実施 | Task 3 checkpoint:human-verify で "approved" |
| Codex LOW (cycle-2) | LOW | tests/db/__init__.py の取扱 | 既存（find で確認済）のため新規作成せず保持・本プロジェクトの package marker 規約に従う | 明示判断として文書化 |

## Verification Results

- **17 テスト GREEN（requires_db・KEIBA_SKIP_DB_TESTS unset・ライブ DB）:** tests/db/test_is_primary_flag.py 全件
- **3 回帰テスト GREEN:** tests/model/test_prediction_load.py（Pitfall 4 修正後・test_idempotent_checksum_match 含む）
- **PREDICTION_COLUMNS = 16（is_primary 末尾）:** 機械検証（test_prediction_columns_matches_ddl_count）
- **ライブ DB 列確認:** `SELECT data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='fukusho_prediction' AND column_name='is_primary'` → `boolean / NO / false`（NOT NULL DEFAULT false・REVIEW HIGH#8）
- **orchestrator 独立検証:** 17 DB tests GREEN・3 regression GREEN・PREDICTION_COLUMNS=16/is_primary last・live DB column exists (boolean NOT NULL)

## Next Phase Readiness

- **Plan 06-05（run_evaluation.py 統合 CLI）への引き継ぎ:** run_evaluation.py は本 plan の set_primary_model を呼び、主モデル確定（D-07）を機械的に反映する。主モデルの「選定」自体は Plan 06-05 Task 2 checkpoint:human-verify で人間が D-04 事前登録基準（Calibration 重視）に従い決定する。
- **Phase 7 Streamlit UI:** is_primary=true の主モデルを表示する経路が提供済み（reader ロール SELECT 権限も既存 GRANT_READER_SQL で付与済み・追加権限不要）。
- **§19.1 再現性:** 両モデル（lightgbm+catboost）の行は is_primary フラグ更新後も保持され（silent 履歴破壊防止）、比較可能性が維持される。set_primary_model は idempotent（2回実行で同一状態）。

## Self-Check: PASSED

- FOUND: .planning/phases/06-evaluation-calibration-gates/06-04-SUMMARY.md
- FOUND: b7b80a3 (Task 1 commit)
- FOUND: c685ab2 (Task 2 commit)

---
*Phase: 06-evaluation-calibration-gates*
*Plan: 04*
*Completed: 2026-06-23*
