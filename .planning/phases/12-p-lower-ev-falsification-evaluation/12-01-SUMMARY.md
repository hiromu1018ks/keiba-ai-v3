---
phase: 12
plan: 01
subsystem: p_lower foundation (statsmodels + compute_p_lower_conformal_shrinkage + prediction migration)
tags: [model, p-lower, schema-migration, wave1, ev-01, safe-01, foundation, byte-reproducible]
requires:
  - "Phase 11 race-relative model (p_fukusho_hit・race_relative.py・θ=1.0 永続化済)"
provides:
  - "compute_p_lower_conformal_shrinkage 純粋関数 (race_relative.py・calib slice のみ・§11.2 聖域)"
  - "prediction.fukusho_prediction.p_fukusho_hit_lower 列 (idempotent ALTER・3ファイル連鎖)"
  - "statsmodels==0.14.6 厳密固定依存 (byte-reproducible §19.1・Plan 03/04 が消費)"
  - "run_apply_schema.py 手動 step list に prediction_add_p_lower 挿入 (C-12-01-1 HIGH)"
affects:
  - "Plan 02: orchestrator L754 後 p_lower 生成挿入・artifact metadata(q_level/q_shrink)"
  - "Plan 03: src/eval/falsification.py が statsmodels + race_relative の q_shrink 計算を消費"
  - "Plan 04: scripts/run_phase12_evaluation.py が p_lower 列・statsmodels・q_level を統合"
  - "Plan 05: 対抗的監査 test_audit_p_lower_falsification.py が SAFE-01 AST 拡張"
tech_stack:
  added:
    - "statsmodels==0.14.6（厳密固定・byte-reproducible §19.1・[C2-12-01-1]）"
  patterns:
    - "calibration-residual based lower bound（split conformal 風・D-01 修正文・分布自由な shrinkage rule）"
    - "idempotent ALTER: ADD COLUMN IF NOT EXISTS + DROP CONSTRAINT IF EXISTS + ADD（schema.py 既存 idiom 踏襲）"
    - "3ファイル列連鎖: schema.py DDL ↔ predict.py PREDICTION_COLUMNS ↔ prediction_load.py _FLOAT_COLS"
    - "§11.2 聖域の構造的機械保証: 関数シグネチャで test 窓 outcome 系引数を取らない"
    - "SAFE-01 関数限定 AST scan: モジュール全体でなく本関数のみ（false-red 回避・C2-12-01-2）"
    - "docstring 直接トークン名の一般化（Phase 09 decision 踏襲・SQL 文字列 scan との両立）"
key_files:
  created:
    - "tests/model/test_p_lower.py (EV-01 unit・Test 1-6・7 テスト)"
    - "tests/db/test_schema_p_lower.py (EV-01 unit・Test 1-9・17 テスト)"
  modified:
    - "pyproject.toml (statsmodels==0.14.6 追加)"
    - "uv.lock (statsmodels==0.14.6 + patsy==1.0.2 反映)"
    - "src/model/race_relative.py (compute_p_lower_conformal_shrinkage 新関数)"
    - "src/db/schema.py (PREDICTION_ADD_P_LOWER_SQL + CREATE TABLE 20列 + APPLY_ORDER + __all__)"
    - "src/model/predict.py (PREDICTION_COLUMNS 20列 + _assert_valid_prediction_df 拡張 + pred_proba_lower 引数)"
    - "src/db/prediction_load.py (_FLOAT_COLS 拡張)"
    - "scripts/run_apply_schema.py (手動 step list に prediction_add_p_lower 挿入・C-12-01-1 HIGH)"
    - "tests/model/test_prediction_load.py (helper _make_synthetic_prediction_df 20列追従)"
    - "tests/db/test_is_primary_flag.py (helper _make_prediction_row 20列追従・len==20 assert 更新)"
decisions:
  - "D-01 修正文採用: p_lower は『p 信頼区間保証』でなく『calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule』（JMLR 2024 exchangeability 必須・時系列で厳密保証は壊れる）"
  - "D-02 採用: q_level=0.90（α と同一視しない・変数名 q_level で q_alpha 回避）・q_shrink 実数値を report に併載"
  - "[C2-12-01-1] statsmodels==0.14.6 厳密固定（>= でなく ==）・将来の 0.14.7 等の解決による false fail 回避"
  - "[C2-12-01-2] SAFE-01 AST scan を inspect.getsource(本関数のみ) に限定・モジュール全体で false-red 回避"
  - "[C-12-01-1 HIGH] scripts/run_apply_schema.py のハードコード手動 step list (APPLY_ORDER 不参照) にも prediction_add_p_lower を挿入"
  - "[C-12-01-4 MEDIUM] predict_p_fukusho に pred_proba_lower 引数追加・race-relative 経路は非 NULL・v1.0 binary 経路は None を機械保証"
  - "docstring の直接トークン名 (odds/ninki/fukuodds) を一般化表現に置換（Phase 09 decision 踏襲・test_audit_race_relative.py SQL 文字列 scan との両立）"
metrics:
  duration: 35min
  completed: "2026-06-27"
  tasks: 2
  files: 9
  tests_added: 24
status: complete
---

# Phase 12 Plan 01: p_lower 基盤（statsmodels + compute_p_lower_conformal_shrinkage + prediction migration）Summary

Phase 12 Wave 1 基盤: statsmodels==0.14.6 厳密固定依存を追加し・calib slice のみで q_shrink を計算する `compute_p_lower_conformal_shrinkage` 純粋関数（§11.2 聖域の構造的機械保証・byte-reproducible・SAFE-01 odds proxy 排除）と prediction.fukusho_prediction への `p_fukusho_hit_lower` 列追加（3ファイル連鎖・Pitfall 4・idempotent ALTER・C-12-01-1 HIGH で run_apply_schema.py step list にも挿入・C-12-01-4 MEDIUM で race-relative 行の非 NULL 保証）を確立した。

## What Was Built

### Task 1: statsmodels 依存 + compute_p_lower_conformal_shrinkage 純粋関数

- **[C2-12-01-1] statsmodels==0.14.6 厳密固定**（pyproject.toml + uv.lock）。`uv add "statsmodels==0.14.6"` 実行で patsy==1.0.2 を含む依存ツリーが反映。import smoke 通過（`statsmodels.__version__ == "0.14.6"`・`multipletests`/`api` 互換）。byte-reproducible §19.1 で `>=` でなく `==` 固定（将来の 0.14.7 等の解決による false fail 回避）。
- **`compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, *, q_level=0.90) -> tuple[np.ndarray, float]`** を `src/model/race_relative.py` に追加。D-01/D-02 の契約通り `r_calib = np.maximum(0, p_final_calib - y_calib)` → `q_shrink = float(np.quantile(r_calib, q_level))` → `p_lower = np.maximum(0, p_final - q_shrink)` を実装。
- **§11.2 聖域の構造的機械保証**: 関数シグネチャが `{p_final, y_calib, p_final_calib, q_level}` のみ（test 窓 outcome 系 `y_test`/`outcome_test`/`y_outcome_test` を取らない）。`inspect.signature` で機械検証（Test 2）。
- **統計的厳密さ (D-01 修正文・JMLR 2024・Pitfall 1)**: docstring に「calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule（個体ごとの真の確率の下限保証でない・時系列で厳密保証は壊れる）」と明記。coverage 表現は「p 信頼区間保証」でなく「実測 coverage + selected-only calibration」。q_level を α と同一視しない（D-02）。
- **byte-reproducible (§19.1)**: `np.quantile` は default linear interpolation・seed 非依存・決定論的。2回実行で `np.array_equal(p_lower_1, p_lower_2)` が True・`q_shrink_1 == q_shrink_2`（Test 1）。
- **Shared Pattern 4 fail-loud**: y_calib/p_final_calib の NaN/inf で RuntimeError（apply_race_relative_correction L227-232 と同一 idiom・silent fallback 禁止・Test 5）。
- **D-02 q_level 境界 guard**: `0 < q_level < 1` 外は ValueError（事前登録値の健全性・Test 4）。
- **SAFE-01 odds proxy 排除**: 本関数のみ（モジュール全体でなく）の AST scan で odds/ninki/fukuodds の Name/Attribute 出現 0件（Test 6・[C2-12-01-2] 関数限定スコープで false-red 回避）。加えて race_relative モジュール全体が FEATURE_COLUMNS/build_training_frame/load_feature_matrix 構築経路を import しない併用検証。
- **docstring 直接トークン名の一般化**（Phase 09 decision 踏襲）: docstring 内の「odds/ninki/fukuodds」直接言及を「市場情報 proxy 系」に置換。`test_audit_race_relative.py` の SQL 文字列リテラル scan（word-boundary・odds 含む拡張）との両立。

### Task 2: prediction p_fukusho_hit_lower 列 migration（3ファイル連鎖 + run_apply_schema.py）

- **`PREDICTION_ADD_P_LOWER_SQL`** を schema.py に追加。idempotent ALTER（`ADD COLUMN IF NOT EXISTS p_fukusho_hit_lower double precision` + `DROP CONSTRAINT IF EXISTS prediction_p_lower_range` + `ADD CONSTRAINT prediction_p_lower_range CHECK (p_fukusho_hit_lower IS NULL OR (p_fukusho_hit_lower >= 0 AND p_fukusho_hit_lower <= 1))`）。COMMENT ON COLUMN で Phase 12 SC#1 由来を明記。
- **PREDICTION_TABLE_DDL の CREATE TABLE にも p_fukusho_hit_lower を追加**（20列化）。ALTER だけだと CREATE TABLE と不整合になる教訓（11-05 Deviation#2 と同一）に従い・新規 CREATE TABLE と ALTER の両方で定義。
- **APPLY_ORDER と __all__** にそれぞれ `("prediction_add_p_lower", PREDICTION_ADD_P_LOWER_SQL)` / `PREDICTION_ADD_P_LOWER_SQL` を追加（外部参照経路）。
- **[C-12-01-1 HIGH] scripts/run_apply_schema.py 手動 step list 挿入**: schema.py APPLY_ORDER への追加だけでは run_apply_schema.py は適用しない（ハードコード list が APPLY_ORDER を参照しない・レビュー C-12-01-1・codex HIGH）。`prediction_extend_model_type_domain` の直後（`backtest_table` の前）に `("prediction_add_p_lower", schema_module.PREDICTION_ADD_P_LOWER_SQL)` を挿入。`grep -c 'prediction_add_p_lower' scripts/run_apply_schema.py == 1`・AST 検証で tuple が1件含まれることを機械保証（Test 8）。
- **predict.py PREDICTION_COLUMNS 19→20**: `p_fukusho_hit` の直後に `p_fukusho_hit_lower` を挿入（3ファイル全てで同位置・Pitfall 4）。コメント「= 19 列」→「= 20 列」更新。
- **`_assert_valid_prediction_df` 拡張**: `p_fukusho_hit_lower ∈ [0,1]`（NULL 許容）を検証。`dropna()` してから範囲チェック（v1.0 binary 行の全行 None は valid・race-relative 行の非 None 値は [0,1] 必須）。
- **`predict_p_fukusho` に `pred_proba_lower` 引数追加**（[C-12-01-4 MEDIUM]）: `None` の場合は `df["p_fukusho_hit_lower"] = None`（v1.0 binary 行・後方互換）。非 None の場合は `pred_proba` と同一の整列・長さ検証を行い（silent wrong-horse p_lower 防止・Cycle 2 NEW HIGH-1 鏡像）・`df["p_fukusho_hit_lower"] = pred_lower_series.values`。race-relative 経路（theta != None・pred_proba_lower 受け取る）は常に非 NULL・v1.0 binary 経路（theta=None・pred_proba_lower=None）は常に None を機械保証（Test 9）。
- **prediction_load.py `_FLOAT_COLS` 拡張**: `{"p_fukusho_hit", "p_fukusho_hit_lower"}`。INSERT 列順序は PREDICTION_COLUMNS を import して従うため自動追従（3ファイル連鎖の auto-propagation・Pitfall 4 対策は `_assert_valid_prediction_df` が列順序を検証）。
- **helper 更新（Regression）**: `test_prediction_load._make_synthetic_prediction_df` と `test_is_primary_flag._make_prediction_row` が20列に追従。PREDICTION_COLUMNS 拡張で `df[list(PREDICTION_COLUMNS)]` が KeyError になるのを防止。`test_is_primary_flag.test_prediction_columns_includes_is_primary` の `len == 19` assert を `len == 20` に更新。
- **本 plan では migration 実行しない**（owner/admin 権限必要・memory: migration-privilege-admin-required・run_apply_schema.py への step 挿入のみ・live-DB 適用は Plan 04/05 checkpoint で人間が実行・11-05 Deviation#1 と同じ）。

## Tests Added

### tests/model/test_p_lower.py（7 tests・KEIBA_SKIP_DB_TESTS=1 GREEN）

- `test_p_lower_byte_reproducible`: 2回呼出しで (p_lower, q_shrink) が np.array_equal で完全一致（§19.1・seed 非依存）
- `test_p_lower_signature_no_test_outcome`: inspect.signature が test 窓 outcome 系引数を取らない（§11.2 聖域・構造的機械保証）
- `test_p_lower_overprediction_residual_semantics`: D-01 r_calib = max(0, p_final_calib - y_calib)・p_lower <= p_final
- `test_p_lower_q_level_bounds`: q_level=0.90 で呼出可能・境界外で ValueError（D-02 事前登録値）
- `test_p_lower_fail_loud_on_non_finite`: y_calib/p_final_calib の NaN/inf で RuntimeError（Shared Pattern 4）
- `test_p_lower_no_odds_proxy_in_function_source`: 本関数のみ AST scan で odds/ninki/fukuodds 出現 0件（SAFE-01・[C2-12-01-2]）
- `test_p_lower_no_feature_pipeline_import`: race_relative モジュール全体が FEATURE_COLUMNS 構築経路を import しない（併用検証）

### tests/db/test_schema_p_lower.py（17 tests・KEIBA_SKIP_DB_TESTS=1 GREEN）

- Test 1: PREDICTION_COLUMNS len == 20 / DDL 全列数と一致（Pitfall 4 3ファイル連鎖）
- Test 2: p_fukusho_hit_lower が p_fukusho_hit の直後 index
- Test 3: _assert_valid_prediction_df NULL 許容 [0,1]（全行 None valid・[0,1] 外で ValueError）
- Test 4: _FLOAT_COLS に p_fukusho_hit_lower が含まれる
- Test 5: PREDICTION_ADD_P_LOWER_SQL が idempotent ALTER（ADD COLUMN IF NOT EXISTS + DROP + ADD）
- Test 6: CHECK 制約 prediction_p_lower_range（NULL 許容 OR [0,1]）
- Test 7: 合成 row helper が20列に追従（test_prediction_load / test_is_primary_flag）
- **Test 8 [C-12-01-1 HIGH]**: run_apply_schema.py 手動 step list に prediction_add_p_lower が1件（grep -c == 1 + AST tuple 検証）
- Test 8 追加: schema.py APPLY_ORDER に prediction_add_p_lower が1件・__all__ に PREDICTION_ADD_P_LOWER_SQL
- **Test 9 [C-12-01-4 MEDIUM]**: race-relative 経路（pred_proba_lower 渡）で p_fukusho_hit_lower が全行非 None・v1.0 binary 経路（pred_proba_lower=None）で全行 None

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] docstring 直接トークン名が audit AST scan で false-positive 検出**
- **Found during:** Task 1 実装後・`tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy` 実行時
- **Issue:** compute_p_lower_conformal_shrinkage の docstring で SAFE-01 聖域を説明するため `odds`/`ninki`/`fukuodds` の直接トークン名を使ったが・test_audit_race_relative.py の SQL 文字列リテラル scan（word-boundary・odds 含む拡張）がこれを検出し fail した。
- **Fix:** Phase 09 decision（STATE.md L265「odds-free 文書化と禁止トークン grep==0 の両立のため docstring の直接トークン名(odds/ninki/..)を一般化表現に置換」）と同一パターンで docstring を「市場情報 proxy 系」に一般化。関数実装・機能は不変。
- **Files modified:** src/model/race_relative.py（docstring 2箇所）
- **Commit:** a80f8c4（Task 1 commit に取り込み）

**2. [Rule 1 - Bug] test helper のパーサーが SQL コメント行を列として誤認**
- **Found during:** Task 2 テスト実装時・`test_prediction_columns_match_ddl_count` 実行時
- **Issue:** 自前実装した DDL パーサーが `stripped.split()[0]` で `--` コメント行の先頭トークンを列名として誤認（DDL 列数 31 と誤算出）。
- **Fix:** `tests/db/test_is_primary_flag.py::_parse_ddl_columns` と同一の正規表現 `^([A-Za-z_][A-Za-z0-9_]*)$` で純粋な識別子のみ抽出するよう修正。
- **Files modified:** tests/db/test_schema_p_lower.py
- **Commit:** Task 2 commit 5231242 に取り込み（RED→GREEN サイクル内）

None - plan executed exactly as written（機能面）・上記はテスト・docstring 表記上の auto-fix（Rule 1）。

## Known Stubs

None - 本 plan は基盤確立が目的で・実装は完了（stub なし）。

- `pred_proba_lower` は Plan 02 で orchestrator L754 後に `compute_p_lower_conformal_shrinkage` の戻り値を渡すことで伝播される（本 plan では pred_proba_lower 引数追加まで・呼出側実装は Plan 02）。

## Threat Flags

None - 本 plan のファイルは `<threat_model>` の T-12-01〜T-12-SC を全て mitigate 済み。新規に脅威面を導入していない。

## Sanctuaries Honored

- **§11.2 test 窓聖域**: `compute_p_lower_conformal_shrinkage` の引数は calib slice のみ（test 窓 outcome 系不可）・`q_level=0.90` は事前登録値で test 窓で変更不可（docstring + 機械保証）。
- **SAFE-01 odds proxy 排除**: race_relative.py p_lower 経路に odds/ninki proxy 混入なし（関数限定 AST scan 0件・feature 構築経路 import なし）。
- **byte-reproducible §19.1**: statsmodels==0.14.6 厳密固定・`np.quantile` default linear で seed 非依存・2回実行で np.array_equal True。
- **§15.2 事前登録指標不変**: 本 plan は計算関数・DDL のみで・§15.2 gate（calibration_max_dev/Brier/LogLoss/sum(p)）には触れない。
- **memory: migration-privilege-admin-required**: 本 plan では ALTER TABLE を実行せず・run_apply_schema.py の手動 step list への挿入のみ（live-DB 適用は Plan 04/05 checkpoint で人間が実行）。
- **Pitfall 4 3ファイル連鎖**: PREDICTION_COLUMNS 拡張を schema.py DDL / predict.py / prediction_load.py の3ファイル全てで同位置に挿入・`_assert_valid_prediction_df` とテスト（Test 1/2）で機械保証。
- **C-12-01-1 HIGH**: schema.py APPLY_ORDER だけでなく scripts/run_apply_schema.py 手動 step list にも prediction_add_p_lower を挿入（grep -c == 1・AST 検証済）。
- **C-12-01-4 MEDIUM**: predict_p_fukusho に pred_proba_lower 引数追加・race-relative 経路（非 None）で全行非 NULL・v1.0 binary 経路（None）で全行 None を機械保証（Test 9）。

## Self-Check: PASSED

### 作成ファイルの存在確認

- FOUND: tests/model/test_p_lower.py
- FOUND: tests/db/test_schema_p_lower.py

### コミットの存在確認

- FOUND: a80f8c4 (feat(12-01): statsmodels 依存と compute_p_lower_conformal_shrinkage 純粋関数)
- FOUND: 5231242 (feat(12-01): prediction p_fukusho_hit_lower 列 migration)

### done criteria grep 検証

- `grep -c "def compute_p_lower_conformal_shrinkage" src/model/race_relative.py` == 1 ✓
- `inspect.signature` params == {p_final, y_calib, p_final_calib, q_level}（test 窓 outcome 系なし）✓
- AST scan odds/ninki/fukuodds violations == 0 ✓
- `len(PREDICTION_COLUMNS)` == 20 ✓
- `PREDICTION_COLUMNS.index('p_fukusho_hit_lower') == PREDICTION_COLUMNS.index('p_fukusho_hit') + 1` == 13 == 12+1 ✓
- `grep -c 'prediction_add_p_lower' src/db/schema.py` == 1 ✓
- `grep -c 'prediction_add_p_lower' scripts/run_apply_schema.py` == 1 (C-12-01-1 HIGH) ✓
- `grep -c 'p_fukusho_hit_lower' src/db/schema.py` == 9 (>= 3) ✓
- `'p_fukusho_hit_lower' in _FLOAT_COLS` == True ✓
- KEIBA_SKIP_DB_TESTS=1 full suite: 635 passed, 48 skipped ✓
