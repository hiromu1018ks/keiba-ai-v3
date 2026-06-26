---
phase: 10-opponent-strength-race-relative-features
plan: 02
subsystem: features/rolling
tags: [feature-engineering, leak-prevention, pit-correct, odds-free, opponent-strength, rolling, field-strength]
requires:
  - Phase 10 PLAN 01 field_strength.py::compute_field_strength_profile（history に profile 8値を付与・第1段階中間値）
  - Phase 9 rolling.py::_SPEED_FIGURE_AXES 17 feature 拡張（直接の analog・D-09/D-09.1-01 idiom）
provides:
  - src/features/rolling.py::_FIELD_STRENGTH_AXES（D-13 21 feature・_SPEED_FIGURE_AXES と対称）
  - src/features/rolling.py::_field_strength_col_name（D-13 命名規則 helper・trend/count-coverage 特別扱い）
  - rolling_field_strength_* 21 feature（target 馬の過去走 field_strength profile を latest-K rolling で集約）
affects:
  - PLAN 03（race_relative.py）の field_strength_adjusted_rank が rolling_field_strength_mean_mean_5 を消費
  - PLAN 04（builder.py）が Step 5c で compute_field_strength_profile(raw_history) を呼出後・Step 5 の build_rolling_features で 21 feature を自動取得（Step 5 の移動が必要・A6）
  - PLAN 03/04 で src/features/availability.py::_ROLLING_SYSTEMS_FOR_RESERVED + src/config/feature_availability.yaml に field_strength 系統を登録（registry parity・3者一致検査の前提）
tech-stack:
  added: []
  patterns:
    - per-observation latest-K rolling（obs_id group・strict < cutoff・LOOKBACK=5・CYCLE-2 HIGH#1 対称）
    - D-13 意味サフィックス命名（window 番号でなく latest_1/mean_3/mean_5・trend 系は axis 名に window 埋込）
    - profile → rolling の2段階構造（PLAN 01 profile 8値を source に 21 feature を生成）
    - sentinel threshold の axis 別分類（stats/trend は count>=window・count/coverage は常に実際数値・D-11 信頼度軸）
    - CYCLE-2 HIGH-C2-2 downstream gate（profile 汚染→rolling 出力汚染伝播の両方向検証・PLAN 01 C2-1 fix の前提表示）
key-files:
  created: []
  modified:
    - src/features/rolling.py
    - tests/features/test_rolling.py
decisions:
  - D-13 命名は _SPEED_FIGURE_AXES の window 番号 suffix でなく「意味サフィックス」（latest_1/mean_3/mean_5）を採用・PLAN frontmatter の明記通り
  - trend 系（trend_last_minus_mean5 / trend_mean3_minus_mean5）は axis 名に mean5 埋込・列名は rolling_field_strength_mean_{axis}（_speed_figure_col_name idiom と対称）
  - count/coverage 系（valid_count_mean / coverage_mean）は axis 名に _mean 埋込・window=5 固定・sentinel 化しない（D-11 信頼度軸・Phase 9.1 idiom 踏襲）
  - CYCLE-2 HIGH-C2-2 は PLAN 02 単体で解決せず・PLAN 01 の source-as-of full-pipeline 再計算（C2-1 fix）が前提・Test 9 で「汚染伝播」と「クリーン profile → クリーン rolling」の両方向を機械表示
metrics:
  duration: 11min
  completed: 2026-06-26
  tasks: 1
  files: 2
  tests: 9 unit tests GREEN (21 feature 対象) / 18 total GREEN (regression safe)
status: complete
---

# Phase 10 Plan 02: 相手強度 rolling_field_strength 21 feature（D-06 第2段階）Summary

D-06 第2段階として src/features/rolling.py を拡張し・PLAN 01 が history に付与した field_strength profile 8値を入力に target 馬の過去走にわたり latest-K rolling（obs_id group・strict `<cutoff`・LOOKBACK=5）で集約し D-13 の 21 feature を生成する。既存 speed_figure 17 feature と完全に対称な idiom で実装し・CYCLE-2 HIGH#1（cross-obs leak 回避）・CYCLE-2 HIGH-C2-2（PLAN 01 C2-1 fix の下流伝播）を機械保証する。9 unit tests が GREEN。

## What Was Built

### 拡張モジュール src/features/rolling.py

- **_ROLLING_SYSTEMS**（L74-91）: `"field_strength"` 系統を追加（speed_figure の直後）。source 列 = field_strength.py が history に付与した profile 8値（PLAN 01 出力・D-06 第1段階中間値）。
- **_SYSTEM_SOURCE["field_strength"]**（L93-110）: 8 source 列（field_strength_mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）を定義。
- **_FIELD_STRENGTH_AXES**（L200-256）: D-13 の 21 feature を (axis, window) ペアで定義。_SPEED_FIGURE_AXES と対称だが・D-13 命名は window 番号でなく意味サフィックス（1→latest_1, 3→mean_3, 5→mean_5）を採用。
  - latest_1 系6: (mean/median/top3_mean/top5_mean/max/sd, 1) → rolling_field_strength_{axis}_latest_1
  - mean_3 系5: (mean/median/top3_mean/top5_mean/max, 3) → rolling_field_strength_{axis}_mean_3（sd は window=3 で定義しない・_SPEED_FIGURE_AXES best2_mean 踏襲）
  - mean_5 系6: (mean/median/top3_mean/top5_mean/max/sd, 5) → rolling_field_strength_{axis}_mean_5
  - trend 系2: (trend_last_minus_mean5, 5) / (trend_mean3_minus_mean5, 5) → rolling_field_strength_mean_trend_*
  - count/coverage 系2: (valid_count_mean, 5) / (coverage_mean, 5) → rolling_field_strength_{axis}_5（信頼度軸・sentinel 化しない）
  - 合計 6+5+6+2+2 = 21 feature（assert len(_FIELD_STRENGTH_AXES) == 21 で機械保証）
- **_field_strength_col_name(axis, window)** helper（L258-291）: 3分類（stats/trend/count-coverage）の命名規則を吸収。_speed_figure_col_name と対称だが・D-13 命名は window 番号でなく意味サフィックス。
- **build_rolling_features に `if system == "field_strength":` 分岐**（L722-834）: speed_figure 集約ブロック（L403-720）と対称な idiom。_FIELD_STRENGTH_AXES の各 (axis, window) で windowed = groupby("obs_id").head(window) で窓を切り・axis 種別（stats/trend/count-coverage）で分岐して集約。
  - stats axis: source 列（_fs_field_strength_{axis}）の mean/median/max/std を算出（top3_mean/top5_mean は profile → rolling の2段階で mean 化）
  - trend axis: _fs_field_strength_mean で first - mean / mean3 - mean5 を算出
  - count/coverage axis: source 列の mean を算出（sentinel 化しない）
  - sentinel threshold: stats/trend は count>=window（trend は count>=5・mean5 必要）・count/coverage は常に実際数値（D-11 信頼度軸・speed_figure count_5 idiom と対称）

### テスト tests/features/test_rolling.py（9 tests GREEN・既存9 + 新規9 = 18 total GREEN）

- Test 1 (D-13 21 feature 完全性): 21 feature の列名完全性・_FIELD_STRENGTH_AXES 要素数 21・_ROLLING_SYSTEMS に field_strength 含有・_SYSTEM_SOURCE["field_strength"] が 8 source 列
- Test 2 (PIT strict <・obs_id group): 5走 eligible + 3行 adversarial（当日/未来/cutoff同日）で mean_5 = 13.0 のみ（adversarial 999.0 混入検出）
- Test 3 (sentinel ルール): 3走のみで mean_mean_5/sd_mean_5/max_mean_5/trend_last_minus_mean5 は sentinel・mean_mean_3/mean_latest_1 は算出
- Test 4 (count/coverage 軸): 3走のみでも valid_count_mean_5/coverage_mean_5 は sentinel 化せず実際数値（D-11）
- Test 5 (trend 系): trend_last_minus_mean5 = latest_1 - mean_5・trend_mean3_minus_mean5 = mean_3 - mean_5（base_mean=40 で +2/+1）
- Test 6 (top-k source 2段階): top3_mean/top5_mean source 列を rolling で更に mean 化（profile → rolling 2段階構造）
- Test 7 (byte-reproducible): 同一 history で2回呼出すと21 feature 全て bit-identical（§19.1）
- Test 8 (copy-not-rename・HIGH#5): 入力 history の既存列は破壊されず・21 列が observations 側に copy 追加
- Test 9 (CYCLE-2 HIGH-C2-2 downstream gate): クリーン profile（5走・mean_5=13.0）と汚染 profile（5走・mean_5=209.8・999.0 混入）で rolling 出力が変わることを両方向検証・PLAN 01 C2-1 fix が PLAN 02 の前提であることを機械表示

## TDD Gate Compliance

- RED commit: 3f340dc (test(10-02): add failing tests for rolling_field_strength 21 features (RED))
- GREEN commit: 394bb70 (feat(10-02): implement rolling_field_strength 21 features (GREEN))
- REFACTOR: 不要（実装は RED→GREEN で既にクリーン・ruff E501/F401/F821/F841/I001 は全て既存由来・私の追加コードは ruff clean）

RED→GREEN gate 順序を満たす。9 tests GREEN・18 total GREEN（既存回帰 safe）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] テストデータの fs_mean 割当順序が「最新=最大」でない問題**
- **Found during:** GREEN 実装中（Test 3 latest_1 = 21 で期待値 23 と不一致）
- **Issue:** _build_fs_5start_history と Test 3 の3走ケースで・ループ変数 i を race_date offset と fs_mean の両方に使っていたため・最新1件目（race_date 降順で先頭）の fs_mean が最小値になっていた。テストの意図（latest_1 = 最新の最大値）と合致しなかった。
- **Fix:** race_date offset を i でなく (6 - i + 1) で算出するよう修正し・fs_mean = base + i が「i=1(最古) → base+1 / i=5(最新) → base+5」になるようデータ設計を調整。実装の契約（PLAN の truths/acceptance）は不変・テストデータの設計調整のみ。
- **Files modified:** tests/features/test_rolling.py
- **Commit:** 394bb70

**2. [Rule 1 - Bug] Test 9 (C2-2 downstream) の dirty 行が LOOKBACK=5 窓に入らない問題**
- **Found during:** GREEN 実装中（dirty 側の mean_5 が clean と同値 13.0 で伝播検出不能）
- **Issue:** Test 9 の dirty 行（fs_mean=999.0）を obs_rd - 10d に置いたところ・最新5件窓（obs_rd - 2d 〜 -6d）に入らず・rolling 出力が clean 側と同じになった。C2-2 伝播検出力が不足していた。
- **Fix:** clean 側を4走（fs_mean=11..14）+ 5走目（正当値=15 または汚染値=999）の構成に変更し・dirty 行を obs_rd - 6d（窓内・5走目）に配置。dirty 側は5走（count=5・window=5 窓内）で mean_5 = (11+12+13+14+999)/5 = 209.8 に変化し・伝播が機械検出されるようになった。
- **Files modified:** tests/features/test_rolling.py
- **Commit:** 394bb70

**3. [Rule 1 - Bug] Test 4 で MISSING import 不足・Test 内 _build_se_history_row 未参照**
- **Found during:** GREEN 実装中（NameError: MISSING / NameError: _build_se_history_row）
- **Issue:** Test 4 の関数本体で from src.utils.category_map import MISSING を関数内 import していなかった・また conftest の _build_se_history_row を import していなかった。
- **Fix:** conftest から _build_se_history_row を import に追加・Test 4 に関数内 import を追加。他の Phase 3 テスト（test_field_strength.py 等）と同一慣例。
- **Files modified:** tests/features/test_rolling.py
- **Commit:** 394bb70

**4. [Rule 1 - Bug] ruff B007 未使用ループ変数 label**
- **Found during:** GREEN 完了後の ruff lint（B007 Loop control variable `label` not used）
- **Issue:** Test 2 の adversarial 行生成ループで for off, label in ... の label が未使用。
- **Fix:** for off, _label in ... に変更（ruff 推奨）。
- **Files modified:** tests/features/test_rolling.py
- **Commit:** 394bb70

### SAFE-01 / core value 整合性

本 PLAN は src/features/rolling.py と tests/features/test_rolling.py のみ拡張。rolling.py は市場情報 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）を使用せず・既存の strict `<` PIT pre-filter（`_pit_cutoff_prefilter`・L114-126）を再利用するため・core value「リーク防止」は機械保証される。field_strength profile 8値（PLAN 01 出力）は history の中間値で・CYCLE-2 HIGH-C2-2 で示した通り PLAN 01 の source-as-of full-pipeline 再計算が前提（本 PLAN 単体では解決せず）。

## Verification

- 単体テスト: `uv run pytest tests/features/test_rolling.py -x -q` → 18 passed（新規9 + 既存9回帰）
- 関連回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/test_field_strength.py tests/features/test_speed_figure.py tests/features/test_speed_figure_pit.py tests/audit/ -q` → 50 passed（PLAN 01 field_strength と Phase 9 speed_figure と audit 全て回帰 safe）
- lint: `uv run ruff check src/features/rolling.py tests/features/test_rolling.py` → 私の追加コードは clean（残り5件 F401/F821/F841/I001 は全て既存由来・stash 比較で確認）
- acceptance criteria: AC1-5 全て機械検証 GREEN（_ROLLING_SYSTEMS / _SYSTEM_SOURCE / _FIELD_STRENGTH_AXES 21 / if 分岐 / 主要5列名テスト存在）

## Known Stubs

なし。rolling_field_strength_* 21 feature は完全実装・全値が PLAN 01 の source-as-of 再計算 pipeline を経由した field_strength profile（8値中間値）から算出される。PLAN 03（race_relative.py）が本 21 feature 中の rolling_field_strength_mean_mean_5 を消費して field_strength_adjusted_rank を算出する前提が整った。

## Threat Flags

なし。本 PLAN は既存の `_pit_cutoff_prefilter`（strict `<`）・obs_id group・LOOKBACK=5 窓の再利用で・新規の network endpoint / auth path / file access / schema 変更 を導入しない。CYCLE-2 HIGH#1（cross-obs leak）・CYCLE-2 HIGH-C2-2（profile 汚染伝播）は既存 idiom と Test 9 で機械保証される。

## Deferred Issues

### tests/features/test_builder.py の3件失敗（PLAN 03/04 で解消される設計上の前提）

`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/` で3件が失敗する:

- `test_no_registered_feature_column_all_nan_end_to_end`（E2E・build_rolling_features が未登録列 rolling_field_strength_mean_latest_1 を生成）
- `test_registry_rolling_systems_match_rolling_impl`（3者 parity 検査・registry と availability._ROLLING_SYSTEMS_FOR_RESERVED に field_strength が未登録）
- `test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs`（E2E・同上）

これらは PLAN 02 の acceptance criteria（test_rolling.py 全体 GREEN・ruff）の対象外で・PLAN 03（availability.yaml + availability.py 拡張）と PLAN 04（builder.py Step 5c 挿入・Step 5 移動・FEATURE_COLUMNS 更新）で解消される設計上の前提。PLAN 02 の `must_haves.artifacts` にも「availability.yaml の登録は PLAN 04（builder.py 統合）の前提」と明記済み。PLAN 02 単体の不完全さではなく・Phase 10 DAG 内の PLAN 間依存の正常な振舞。

## Self-Check: PASSED

- src/features/rolling.py: FOUND
- tests/features/test_rolling.py: FOUND
- commit 3f340dc (RED): FOUND
- commit 394bb70 (GREEN): FOUND
