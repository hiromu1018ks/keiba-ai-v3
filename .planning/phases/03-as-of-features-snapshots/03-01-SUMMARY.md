---
phase: 03-as-of-features-snapshots
plan: 01
subsystem: features
tags: [phase-03, features, tdd, red-wave-0, allowlist, availability-loader, cutoff-semantics, source-role-taxonomy]
requires: []
provides:
  - src/features/__init__.py
  - src/features/availability.py
  - src/config/feature_availability.yaml (v0.2.0, 40 entries)
  - tests/features/conftest.py (synthetic + adversarial builders)
  - tests/features/test_allowlist.py (GREEN SC#2 + HIGH #3/#4)
  - 7 RED test stubs (Plan 03-03/03-04 GREEN targets)
affects:
  - Plan 03-03 (builder.py / rolling.py / running_style.py consume availability)
  - Plan 03-04 (snapshot.py / category_map_consumer.py consume availability)
tech-stack:
  added: []
  patterns:
    - YAML loader with required-key fail-fast (fukusho_label.load_label_spec analog)
    - function-level lazy import RED-cluster pattern (Phase 2 Plan 02-02 analog)
    - source_role taxonomy (target_obs_banned / history_allowed_post_race / both_allowed)
    - strict < cutoff PIT invariant documented as CUTOFF_SEMANTICS constant
key-files:
  created:
    - src/features/__init__.py
    - src/features/availability.py
    - tests/features/__init__.py
    - tests/features/conftest.py
    - tests/features/test_allowlist.py
    - tests/features/test_pit_cutoff.py
    - tests/features/test_rolling.py
    - tests/features/test_running_style.py
    - tests/features/test_snapshot_repro.py
    - tests/features/test_category_map_consumer.py
    - tests/features/test_builder.py
  modified:
    - src/config/feature_availability.yaml
decisions:
  - "rolling は 8系統 × 3軸 = 24 で計40 feature (静的15 + rolling24 + 推定脚質1)・RESEARCH Example 3 の days_since_prev 含む8系統を採用"
  - "source_role 3値 (target_obs_banned/history_allowed_post_race/both_allowed) を導入し babacd(history) と sibababacd/dirtbabacd(target_obs) を構造的に区別 (HIGH #4)"
  - "cutoff 比較は strict < feature_cutoff_datetime の単一不変量 (CYCLE-2 HIGH #2・全 surface で統一)"
metrics:
  duration: "7m"
  completed: "2026-06-19"
  tasks: 2
  files: 12
---

# Phase 03 Plan 01: features package + availability loader + RED test cluster Summary

Phase 3 Wave 1 基盤構築: `src/features/` package 新設・`feature_availability.yaml` を枠から §13.5 全40 feature エントリに拡充 (schema_version 0.1.0 → 0.2.0, source_role taxonomy 付き)・availability loader と allowlist helpers を実装・8つのテストファイル (conftest 含む) を RED-集群化 (Phase 2 Plan 02-02 パターン踏襲)。REVIEWS HIGH #2/#3/#4 を本 plan が主担当で解消し、HIGH #1/#5/#6 を RED stub として後続 Plan 03-03/03-04 の GREEN 契約に固定。

## What Was Built

### Task 1: features package + availability.yaml + loader (commit f0ba574)

- **`src/features/__init__.py`** — package marker。docstring に Phase 3 / snapshot を明記・`__all__` 空で明示的 import を強制。
- **`src/config/feature_availability.yaml`** — schema_version `0.2.0` に bump。40 feature エントリ:
  - 静的15 (barei/sexcd/futan/jockey_id/trainer_id/sire_id/bms_id/jyocd/kyori/trackcd/course_kubun/class_code_normalized/umaban/wakuban/horse_id) — `source_role: both_allowed`
  - rolling 8系統 × 3軸 = 24 (kakuteijyuni / timediff / harontimel3 / jyuni3c_jyuni4c / kyori / babacd / jyocd / days_since_prev) — `source_role: history_allowed_post_race`
  - estimated_running_style 1 — `source_role: history_allowed_post_race`
  - 全エントリ `available_from_timing ∈ {entry_confirmed, post_position_confirmed}` (D-07)・`cutoff_rule: "race_date - 1 day (strict < cutoff, JST midnight)"` 一律 (D-06)
  - トップレベル `cutoff_semantics:` ブロック追加 (HIGH #2): `comparison_operator: "strict_less_than"` / `timezone: "Asia/Tokyo"` / boundary_rule
- **`src/features/availability.py`** — loader + helpers:
  - `load_feature_availability()` — 必須キー (`cutoff_semantics` 含む) 欠損で `ValueError` (D-13 silent fallback 禁止・fukusho_label.load_label_spec パターン)
  - `BANNED_TIMINGS` / `ALLOWED_TIMINGS` frozenset (D-07)
  - `CUTOFF_SEMANTICS` 定数 dict (HIGH #2)
  - `TARGET_OBS_BANNED_COLUMNS` (kyakusitukubun/bataijyu/ninki/odds/sibababacd/dirtbabacd/tenkocd/harontimel4) / `HISTORY_ALLOWED_POST_RACE_COLUMNS` (kakuteijyuni/timediff/harontimel3/jyuni3c/jyuni4c/jyuni1c/babacd/datakubun) — disjoint (Pitfall 3.6 厳守・harontimel4 は banned 側)
  - `banned_features(spec)` / `assert_all_entries_allowed(spec)` (SC#2)
  - `registered_feature_columns(spec)` / `assert_matrix_columns_registered(spec, output_columns)` (HIGH #3・未登録カラムを ValueError で reject・reserved keys + `<col>_code` 形式は許可)
  - `_RESERVED_NON_FEATURE_COLUMNS` に `_ROLLING_SYSTEMS_FOR_RESERVED` 8要素から生成される `rolling_<system>_count_5` 計8列を具体名で展開 (BLOCKER #1 修正)

### Task 2: tests/features/ RED cluster (commit 6634527)

- **`tests/features/conftest.py`** — `_build_se_history_row` / `_build_race_obs_row` (JST midnight cutoff) / `_build_adversarial_rolling_rows` (5行 adversarial + 3行 eligible・HIGH #1) / `_build_two_observation_rolling_rows` (同一 horse × 2 obs × 異 cutoff・CYCLE-2 HIGH #1 re-open) / `synthetic_availability` / `mock_readonly_cur` fixtures。
- **`tests/features/test_allowlist.py`** — 13 GREEN tests。SC#2 (banned timing 0件・parametrize 5 timing)・HIGH #3 (matrix column registration・unregistered reject・banned-alias reject)・HIGH #4 (target_obs_banned features が registry に無い・history_allowed babacd rolling 存在・disjoint invariant)。
- **7 RED stubs** (test_pit_cutoff / test_rolling / test_running_style / test_snapshot_repro / test_category_map_consumer / test_builder) — 関数内 lazy import で実行時に ImportError/AttributeError (Phase 2 RED-集群パターン)。HIGH #1/#5/#6 の adversarial テストを含む。

## Verification

```
KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q
=> 14 passed, 35 failed
   - 14 passed = test_allowlist.py (13) + test_pit_cutoff.py::test_feature_cutoff_is_race_date_minus_one_day (1・conftest のみ依存)
   - 35 failed = 期待通りの RED stub (import error for未実装 src.features.{builder,rolling,running_style,snapshot,category_map_consumer})
```

grep acceptance criteria 全て PASS:
- `schema_version: "0.2.0"` == 1
- `comparison_operator: "strict_less_than"` == 1 (HIGH #2)
- `source_role` >= 1 (HIGH #4・実測 47)
- `feature_name:` >= 40 (実測 41 = 40 entries + 1 schema key)
- 禁止 timing 出現 == 0 (D-07)
- `rolling_babacd_mean_5` の source_role が `history_allowed_post_race` == 1
- `feature_name: (sibababacd|dirtbabacd)` == 0 (HIGH #4)

Python インポート健全性: features=40, banned=[], cutoff_op=strict_less_than, target/history disjoint=True, unregistered reject 動作確認済。

## Deviations from Plan

None — plan executed exactly as written.

### Auto-fixed Issues

(該当なし)

## Known Stubs

本 plan は意図的に「未実装モジュールに依存するテスト stub」を作成する RED wave である。各 RED stub は後続 plan が GREEN 化する契約:

| Stub file | 依存先 (未実装) | GREEN 化する Plan | 対応 HIGH |
|-----------|----------------|-------------------|-----------|
| test_pit_cutoff.py | src.features.builder | Plan 03-03 | HIGH #2 |
| test_rolling.py | src.features.rolling | Plan 03-03 | HIGH #1, CYCLE-2 HIGH #1 |
| test_running_style.py | src.features.running_style | Plan 03-03 | — |
| test_snapshot_repro.py | src.features.snapshot | Plan 03-04 | HIGH #6 |
| test_category_map_consumer.py | src.features.category_map_consumer | Plan 03-04 | HIGH #5 |
| test_builder.py | src.features.builder | Plan 03-03 | HIGH #3 |

これらは RED stub であり、本 plan の成果物 (loader / registry / GREEN test_allowlist) が後続 plan の検証基盤として機能する。

## TDD Gate Compliance

Plan frontmatter `type: tdd` に従い RED/GREEN/REFACTOR gate を検証:

- RED gate: `test(03-01): RED stub cluster ...` commit (6634527) 存在・期待通り RED (35 failed)
- GREEN gate: 本 plan は Wave 0 (RED 基盤) のみ・GREEN 化は Plan 03-03/03-04 が担当。但し test_allowlist.py は availability.py のみ依存のため本 plan で既に GREEN (13 tests passed)。
- REFACTOR gate: RED wave のため該当なし。

注: 本 plan は「後続 plan の GREEN 契約を固定する RED 基盤」が目的であり、GREEN gate の完全達成は後続 plan 03-03/03-04 に委譲される (Phase 2 Plan 02-02 と同一パターン)。

## Threat Flags

(該当なし・threat_model T-03-01/02/04/R1/R3/R4 の mitigate が本 plan で実装済)

## Self-Check: PASSED

- src/features/__init__.py: FOUND
- src/features/availability.py: FOUND
- src/config/feature_availability.yaml: FOUND (schema_version 0.2.0)
- tests/features/conftest.py: FOUND
- tests/features/test_allowlist.py: FOUND (13 GREEN)
- 7 RED stub files: FOUND
- commit f0ba574: FOUND in git log
- commit 6634527: FOUND in git log
