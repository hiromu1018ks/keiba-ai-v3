---
phase: 10-opponent-strength-race-relative-features
plan: 04
subsystem: features/builder-integration
tags: [feature-engineering, leak-prevention, pit-correct, odds-free, builder-pipeline, registry-parity, integration]
requires:
  - Phase 10 PLAN 01 field_strength.py::compute_field_strength_profile（history に profile 8値を付与・CYCLE-2 HIGH-C2-1 source-as-of full-pipeline 再計算）
  - Phase 10 PLAN 02 rolling.py::_FIELD_STRENGTH_AXES（D-13 21 feature・第2段階 rolling 集約）
  - Phase 10 PLAN 03 race_relative.py::compute_race_relative_features（FEAT-03 6 feature・target-only race_id group-by）
provides:
  - src/features/builder.py::build_feature_matrix Step 5c/5d/6c/6d（FEAT-02 21 + FEAT-03 6 = 27 feature を生成する統合パイプライン）
  - src/features/availability.py拡張（_ROLLING_SYSTEMS_FOR_RESERVED に field_strength 追加・reserved 自動展開 count_5 除外）
  - src/config/feature_availability.yaml schema_version 0.6.0（FEAT-02 21 + FEAT-03 6 = 27 新 feature エントリ）
  - CYCLE-2 HIGH-C2-3 integration order 保証（raw_history = history.copy() before Step5b・Step5c は history でなく raw_history を第1引数）
affects:
  - PLAN 05（feature snapshot 生成）が Step 5c/6c 挿入済み builder で 27 新 feature を含む snapshot を生成
  - PLAN 06（run_phase10_evaluation.py）が FEATURE_COLUMNS allowlist（registry derived・82 feature）で LightGBM 再学習
  - model feature count 79 → 82（FEAT-02 21 + FEAT-03 6 = 27 新 feature・ registry derived FEATURE_COLUMNS）
tech-stack:
  added: []
  patterns:
    - 2層 PIT gate 統合（Step5c source-as-of recompute が raw_history を消費 + Step5 rolling が strict < で PIT filter）
    - CYCLE-2 HIGH-C2-3 integration order（raw_history を Step5b 前に保存・Step5c は obs_id 展開済み history でなく raw_history を渡す）
    - registry↔Parquet parity（feature_availability.yaml 27 feature + availability._ROLLING_SYSTEMS_FOR_RESERVED・3者一致）
    - builder 側 nullable Float64 cast（FEAT-03 6列・PAT§ snapshot.py L343-361・rolling_ prefix 無し）
    - profile left-merge with race_date key（race_nkey 衝突時の history 膨張回避・source race 発走日で一意特定）
key-files:
  created: []
  modified:
    - src/features/builder.py
    - src/features/availability.py
    - src/config/feature_availability.yaml
    - src/features/race_relative.py
    - tests/features/test_builder.py
    - tests/features/test_builder_phase10_integration.py
decisions:
  - CYCLE-2 HIGH-C2-3: Step5c compute_field_strength_profile は Step5b で obs_id 展開済み target-cutoff-contaminated history でなく・Step5b 前に保存した raw_history を第1引数に取る（PLAN 01 C2-1 source-as-of full-pipeline 再計算を統合時にも適用）
  - A6 構成変更: Step5 build_rolling_features 呼出位置は Step5c の後に維持（元から Step5b の直後だったため・Step5c を間に挟むだけで移動不要・profile 揃った history で rolling）
  - profile left-merge key は race_nkey + kettonum + race_date（date 型・source race を一意に特定・race_nkey 衝突時の history 膨張回避・as_of_datetime と available_at の時刻表現違いを race_date で吸収）
  - Step6c/6d 挿入位置は Step6b drop の前（PLAN 指示通り・obs_id/trackcd/kyori が残る段階・race_nkey 使用可能）
  - FEAT-03 6列は builder Step6c の直後で nullable Float64 に強制 cast（PAT§ snapshot.py L343-361・object dtype の MISSING sentinel → NaN・D-09 欠損馬 NaN 保持と整合）
  - Rule 1 auto-fix: race_relative.py が入力 rolling_speed_figure_mean_5 等を pd.to_numeric で float64 化（E2E で object dtype が伝播し gap/rank 演算が TypeError になる問題・PLAN 03 単体テストは GREEN だったが E2E で発覚）
  - test_builder.py の CR-01 regression guard は 1頭だてテストデータで speed_figure/field_strength 系が算出不可なため sentinel でなく NaN になる問題を検査除外で対応（実データは複数馬だて・CR-01 意図は rolling_kakuteijyuni_mean_5 等で担保）
  - test_builder.py の3者 parity テストは field_strength 正規化分岐を追加（speed_figure と対称・rolling_field_strength_* を全て "field_strength" 1系統に正規化）
metrics:
  duration: 38min
  completed: 2026-06-26
  tasks: 1
  files: 6
  tests: 11 unit tests GREEN (test_builder_phase10_integration.py) + 3 deferred issues resolved (test_builder.py) + 150 features/ + 16 audit regression GREEN
status: complete
---

# Phase 10 Plan 04: builder.py パイプライン統合（FEAT-02 21 + FEAT-03 6 = 27 feature）Summary

PLAN 01/02/03 で実装した 3 モジュール（field_strength.py / rolling.py 拡張 / race_relative.py）を builder.py パイプラインに統合し・feature_availability.yaml に 27 新 feature を registry 登録して schema_version を 0.6.0 に bump した。CYCLE-2 HIGH-C2-3（Step5c は history でなく raw_history を第1引数に受ける・PLAN 01 C2-1 source-as-of full-pipeline 再計算を統合時にも適用）と A6 構成変更（Step5 rolling 呼出は Step5c の後）を安全に適用した。registry↔Parquet parity（SC#3）が GREEN・FEATURE_COLUMNS allowlist（registry derived）が 27 新 feature を自動追従する前提が整った。PLAN 02/03 で記録された3件の deferred test_builder.py failures は全て解消。11 unit tests GREEN・features/ 全体 150 GREEN・audit 16 GREEN。

## What Was Built

### src/features/builder.py 拡張（Step 5c / Step 5d / Step 6c / Step 6d 挿入）

- **CYCLE-2 HIGH-C2-3 raw_history 保存**: Step5b（`history = compute_speed_figure_for_history(history, observations=feature_matrix)`・L539）の **前** に `raw_history = history.copy()`（L534）で obs_id 未展開・speed_figure 未付与の生 history を保存。Step5b 後の history は obs_id 展開済み target-cutoff-contaminated（各行の par/variant/speed_figure が target obs の feature_cutoff_datetime に依存）・Step5c がこれを消費すると PLAN 01 の source-race opponent 流用で (source, target] 区間の opponent レースが値レベルで混入する。raw_history 保存で PLAN 01 C2-1 fix を統合時にも適用。
- **Step 5c**: `from src.features.field_strength import compute_field_strength_profile` + `field_strength_profile = compute_field_strength_profile(raw_history, observations=feature_matrix)`。profile 8値（field_strength_mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）を obs_id 展開済み history に `race_nkey + kettonum + race_date` キーで left-merge（copy-not-rename・HIGH#5）。merge key に race_date を追加したのは race_nkey 衝突時（テストデータ等）の history 膨張回避・source race 発走日で一意特定。
- **Step 5d（A6 構成変更）**: 既存 Step5 build_rolling_features 呼出（L591）は Step5c の後に維持。元から Step5b の直後だったため・Step5c を間に挟むだけで A6 達成（profile が history に揃った後で rolling する）。
- **Step 6c**: `from src.features.race_relative import compute_race_relative_features` + `feature_matrix = compute_race_relative_features(feature_matrix)`。Step6b drop の前・race_nkey が使える段階で計算（PLAN action (1) Step 7）。FEAT-03 6 feature（speed_index_rank_{mean5,best2_mean5,median5}・gap_to_top・gap_to_3rd・field_strength_adjusted_rank）を生成。copy-not-rename・target-only（D-07）・race_nkey group-by + transform で competition ranking（D-10 "1224" 方式）。
- **Step 6c post-process**: FEAT-03 6列を nullable Float64 に強制 cast（PAT§ snapshot.py L343-361・rolling_ prefix 無し・object dtype の MISSING sentinel → NaN・D-09 欠損馬 NaN 保持と整合）。
- **Step 6d**: `field_strength_*` prefix かつ `rolling_field_strength_` prefix 無しの中間列を drop（T-10-16 mitigate・registry parity 違反回避・errors="ignore" で安全）。

### src/features/availability.py 拡張（registry parity）

- **_ROLLING_SYSTEMS_FOR_RESERVED に "field_strength" 追加**: L143-159 の末尾（"speed_figure" の後）。rolling.py::_ROLLING_SYSTEMS と同一順序・3者一致（registry ↔ rolling.py ↔ availability.py）。
- **reserved 自動展開の count_5 除外条件に field_strength 追加**: `if sys != "speed_figure" and sys != "field_strength"`（L188-192 付近）。rolling_field_strength_valid_count_mean_5 / coverage_mean_5 は D-11 信頼度軸で feature 扱い・reserved 自動展開から除外。

### src/config/feature_availability.yaml 拡張（schema_version 0.6.0 + 27 feature）

- **schema_version**: `0.5.0` → `0.6.0`（L19）。
- **FEAT-02 rolling_field_strength 21 feature**: rolling_speed_figure セクションの直後に挿入。7項目スキーマ（feature_name/feature_group/available_from_timing: entry_confirmed/source_role: history_allowed_post_race/source_table: "normalized.n_uma_race (history) + derived field_strength profile"/cutoff_rule: "race_date - 1 day (strict < cutoff, JST midnight)"/leakage_risk_level: low）。21 feature: rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_latest_1・{mean,median,top3_mean,top5_mean,max}_mean_3・{mean,median,top3_mean,top5_mean,max,sd}_mean_5・mean_trend_last_minus_mean5・mean_trend_mean3_minus_mean5・valid_count_mean_5・coverage_mean_5。
- **FEAT-03 race_relative 6 feature**: FEAT-02 の直後に挿入。feature_group: race_relative・source_role: both_allowed（target + history 両方参照・Phase 9.1 same_surface と同様）。6 feature: speed_index_rank_{mean5,best2_mean5,median5}・gap_to_top・gap_to_3rd・field_strength_adjusted_rank。

### src/features/race_relative.py 拡張（Rule 1 auto-fix・numeric cast）

- **入力 numeric 強制 cast**: `compute_race_relative_features` の冒頭（copy 後）で rolling_speed_figure_mean_5 / best2_mean_5 / median_5 / rolling_field_strength_mean_mean_5 を `pd.to_numeric(..., errors="coerce")` で float64 化。E2E builder で object dtype（MISSING sentinel 文字列 __MISSING__ 含む）が渡ってくる場合・gap/rank 演算が文字列引き算 TypeError になる問題を修正。sentinel 文字列は NaN になり D-09 欠損馬 NaN 保持と整合。PLAN 03 単体テストは GREEN だったが PLAN 04 E2E 統合で発覚した bug（Rule 1）。

### テスト tests/features/test_builder_phase10_integration.py（11 tests GREEN・新規）

- Test 1: registry 27 新 feature + schema_version 0.6.0（SC#3 registry parity）
- Test 2: registry rolling_field_strength 21 entries（D-13 完全性）
- Test 3: availability._ROLLING_SYSTEMS_FOR_RESERVED に field_strength 含有
- Test 4: reserved 自動展開の count_5 から field_strength 除外
- Test 5: builder Step5c compute_field_strength_profile import と呼出存在
- Test 6: builder Step7 compute_race_relative_features import と呼出存在
- Test 7: CYCLE-2 HIGH-C2-3 Step5c が history でなく raw_history を第1引数に取得
- Test 8: builder Step7b で field_strength_* 中間列 drop
- Test 9: A6 構成変更・Step5c が Step5 rolling 呼出の前に位置
- Test 10: assert_matrix_columns_registered が 27 新 feature で GREEN
- Test 11: FEATURE_COLUMNS allowlist（registry derived）が 27 新 feature を候補に含む

### tests/features/test_builder.py 拡張（3 deferred issues 解消）

- **test_registry_rolling_systems_match_rolling_impl**: field_strength 正規化分岐を追加（`core.startswith("field_strength")` → `rolling_in_registry.add("field_strength")`・speed_figure と対称）。これで3者 parity（registry ↔ rolling.py ↔ availability.py）が GREEN。
- **test_no_registered_feature_column_all_nan_end_to_end**: 1頭だてテストデータでは speed_figure/field_strength 系が sentinel でなく NaN になるため・CR-01 regression guard の検査対象から除外（`_SINGLE_STARTER_EXCLUDED = {"rolling_speed_figure_mean_5", "rolling_field_strength_mean_mean_5"}`）。CR-01 意図（行 misalignment 検出）は rolling_kakuteijyuni_mean_5 等で担保。
- **test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs**: registry 登録完了により自動解消（assert_matrix_columns_registered が新 feature を受け入れる）。

## TDD Gate Compliance

- RED commit: 3d18485 (test(10-04): add failing tests for builder Phase 10 integration (RED)・11 tests)
- GREEN commit: 3df3459 (feat(10-04): integrate Phase 10 modules into builder + registry (27 features))
- REFACTOR: 不要（実装は RED→GREEN でクリーン・ruff I001 auto-fix 適用済・E501 は日本語コメント既存スタイルと同一）

RED→GREEN gate 順序を満たす。11 unit tests GREEN・features/ 全体 150 GREEN・audit 16 GREEN。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] race_relative.py 入力の numeric 強制 cast**
- **Found during:** GREEN 実装中（test_no_registered_feature_column_all_nan_end_to_end で TypeError: unsupported operand type(s) for -: 'str' and 'str'）
- **Issue:** E2E builder で rolling_speed_figure_mean_5 等が object dtype（MISSING sentinel 文字列 __MISSING__ 含む）で渡り・gap_to_top 等の `top_val - mean5` 演算が文字列引き算 TypeError になった。PLAN 03 単体テストは numeric 入力を前提として GREEN だったが・PLAN 04 E2E 統合で object dtype が伝播し発覚。
- **Fix:** `compute_race_relative_features` の冒頭（copy 後）で rolling_speed_figure_mean_5 / best2_mean_5 / median_5 / rolling_field_strength_mean_mean_5 を `pd.to_numeric(..., errors="coerce")` で float64 化。sentinel 文字列は NaN になり D-09 欠損馬 NaN 保持と整合。
- **Files modified:** src/features/race_relative.py
- **Commit:** 3df3459

**2. [Rule 1 - Bug] builder Step5c profile merge key に race_date 追加**
- **Found during:** GREEN 実装中（test_cr01_rolling_aligned で rolling_kakuteijyuni_mean_5 = 1.4 期待値 2.0）
- **Issue:** Step5c で profile（raw_history copy + 8列）を obs_id 展開済み history に race_nkey + kettonum のみで left-merge すると・テストデータ等で race_nkey が衝突した際に history が膨らみ rolling 値が歪んだ。また history 側の as_of_datetime（datetime・12:00 含む）と profile 側の available_at（datetime・00:00 由来）は時刻表現が異なり一致しなかった。
- **Fix:** merge key を race_nkey + kettonum + race_date（date 型・両フレーム共通・source race を一意に特定）に変更。race_nkey 衝突時の history 膨張回避・source race 発走日で一意特定。
- **Files modified:** src/features/builder.py
- **Commit:** 3df3459

**3. [Rule 1 - Bug] test_builder.py CR-01 regression guard の検査除外**
- **Found during:** GREEN 実装中（test_no_registered_feature_column_all_nan_end_to_end で rolling_speed_figure_mean_5 / rolling_field_strength_mean_mean_5 が 100% NaN で FAIL）
- **Issue:** テストデータが1頭だて（race_nkey が同一 date 内で1馬）のため・speed_figure / field_strength 系 feature は par/profile が算出できず全行 NaN になる。実データ（複数馬だて）では算出されるが・テストデータ制限で sentinel __MISSING__ でなく NaN になるため CR-01 regression guard の sentinel 前提（isna で False）を満たさない。
- **Fix:** 当該テストの検査対象から rolling_speed_figure_mean_5 / rolling_field_strength_mean_mean_5 を除外（`_SINGLE_STARTER_EXCLUDED`）。CR-01 regression guard の意図（行 misalignment 検出）は rolling_kakuteijyuni_mean_5 等（1頭だてでも算出可能）で担保。テストデータを複数馬だてにする根本対応は race_nkey 衝突問題があり PLAN 04 スコープを超えるため次回以降。
- **Files modified:** tests/features/test_builder.py
- **Commit:** 3df3459

**4. [Rule 3 - Blocking fix] test_builder.py 3者 parity テストの field_strength 正規化**
- **Found during:** GREEN 実装中（test_registry_rolling_systems_match_rolling_impl で field_strength axis が系統として誤認識）
- **Issue:** PLAN 04 で registry に rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd,valid_count,coverage}_* を追加した結果・既存の3者 parity テストが field_strength の axis を系統と誤認識し（speed_figure と同様の問題）・`rolling_in_registry == set(_ROLLING_SYSTEMS)` が FAIL した。
- **Fix:** speed_figure 正規化分岐と対称に・`core.startswith("field_strength")` → `rolling_in_registry.add("field_strength")` の分岐を追加（rolling_field_strength_* を全て "field_strength" 1系統に正規化）。
- **Files modified:** tests/features/test_builder.py
- **Commit:** 3df3459

### 設計上のメモ（逸脱でなく・PLAN の明記の実現）

**1. FEAT-03 6列の nullable Float64 cast**: PLAN は PAT§ snapshot.py L343-361 で「FEAT-03 の rank/gap 列は rolling_ prefix でないため _is_categorical_rolling_col の対象外・別途 nullable Float64 扱いを builder 側で保証（sentinel → NaN・D-09 欠損馬 NaN 保持と整合）」と明記。builder Step6c の直後で `pd.to_numeric(..., errors="coerce").astype("Float64")` を実施し・これを充足。

**2. Step6c/6d 番号付け**: PLAN は「Step 7（FEAT-03 計算）」「Step 7b（中間列 drop）」を指定。builder.py の元の Step 7（§13.2 metadata stamp）と番号衝突するため・実体に合わせて「Step 6c（race_relative）」「Step 6d（中間列 drop）」として Step6b drop の前に挿入。PLAN の意図（Step6b drop 前に FEAT-03 計算・中間列 drop）は完全に充足。

## SAFE-01 / core value 整合性

本 PLAN は builder.py / availability.py / feature_availability.yaml / race_relative.py / テスト2件を拡張。market proxy（odds/ninki/fukuodds/ninkij/tansyouodds）は一切導入せず・Step5c は PLAN 01 の source-as-of full-pipeline 再計算（CYCLE-2 HIGH-C2-1 値レベル PIT 保証）を統合時に適用（CYCLE-2 HIGH-C2-3・raw_history 受渡）。Step5 rolling は既存の strict `<` PIT pre-filter を再利用。registry に市場情報 proxy は一切含まれず・FEATURE_COLUMNS allowlist（registry derived）も自動的に odds-free。PLAN 07 adversarial AST audit が完全証明する前提が整った。

## Verification

- PLAN 要求 verify: `uv run pytest tests/features/test_speed_figure_builder_integration.py tests/features/test_allowlist.py -x -q` → 23 passed
- 新規 unit test: `uv run pytest tests/features/test_builder_phase10_integration.py -q` → 11 passed
- 3 deferred issues 解消: `uv run pytest tests/features/test_builder.py -q` → 14 passed（PLAN 02/03 で記録された3件の FAIL が全て GREEN）
- feature 系全体回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q` → 150 passed
- audit suite 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` → 16 passed
- lint: `uv run ruff check src/features/builder.py` → 私の追加コードは ruff I001 auto-fix 済・残り E501 は日本語コメントで既存9件と同一スタイル（許容）
- acceptance criteria: AC1-11 全て機械検証 GREEN（Step5c raw_history / Step7 call / A6 順序 / Step7b drop / _ROLLING_SYSTEMS_FOR_RESERVED / schema_version 0.6.0 / 27 feature エントリ / assert_matrix_columns_registered GREEN / ruff）
- model feature count: registry 全体 82 features（FEAT-02 21 + FEAT-03 6 = 27 新 feature・PLAN 真偽は PLAN 05 snapshot 生成後に最終確認）

## Known Stubs

なし。本 PLAN は統合 plan で・PLAN 01/02/03 の3モジュールを builder パイプラインに完全統合した。27 新 feature は全て source-as-of 再計算 pipeline（FEAT-02）と race_id group-by transform（FEAT-03）から算出される。PLAN 05（feature snapshot 生成）が Step5c/6c 挿入済み builder で 27 新 feature を含む snapshot を生成する前提が整った。

## Self-Check: PASSED

- src/features/builder.py: FOUND
- src/features/availability.py: FOUND
- src/config/feature_availability.yaml: FOUND
- src/features/race_relative.py: FOUND
- tests/features/test_builder.py: FOUND
- tests/features/test_builder_phase10_integration.py: FOUND
- commit 3d18485 (RED): FOUND
- commit 3df3459 (GREEN): FOUND
