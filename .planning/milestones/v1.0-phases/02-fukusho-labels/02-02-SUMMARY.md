---
phase: 02-fukusho-labels
plan: 02
subsystem: labels
tags: [phase-02, labels, tdd, unit-test, red, mock-cursor, edge-cases]
requires:
  - 02-01-PLAN.md (label_spec.yaml・schema.py GRANT 拡張・完了済)
provides:
  - tests/test_fukusho_label.py (LABEL-01/02/04 RED test contract for Plan 02-03 GREEN)
affects:
  - src/etl/fukusho_label.py (Plan 02-03 が本テスト契約を満たす GREEN 実装を行う)
tech-stack:
  added: []
  patterns:
    - TDD RED/GREEN/REFACTOR
    - synthetic DataFrame builder (_build_hr_row/_build_se_row/_build_label_input_df)
    - 遅延 import による collection-safe RED state
    - inspect.getsource ベース regression test
key-files:
  created:
    - tests/test_fukusho_label.py
  modified: []
decisions:
  - "RED テストの collection を保証するため module-level import を避け、各テスト内で _get_fukusho_label_module() により遅延 import して ImportError で fail させる"
  - "実カラム名 (timediff / bataijyu / harontimel3 / datakubun / fuseirituflag2 / payfukusyounmaban1..5 / torokutosu / syussotosu) を厳格使用"
metrics:
  duration: ~6 min
  completed: 2026-06-18
  tasks: 2
  files: 1
  tests: 27
---

# Phase 2 Plan 02: Fukusho Label Unit Tests (TDD RED) Summary

LABEL-01/02/04 を網羅する27件の unit test を1ファイルにまとめて TDD RED フェーズで作成。
`src/etl/fukusho_label.py`（Plan 02-03）が未実装のため全テスト ImportError で RED。

## What was built

`tests/test_fukusho_label.py`（771 行・27 テスト）を作成。Plan 02-03 GREEN 実装の契約となる。

### テスト構成（27件）

**LABEL-01/02 (Task 1, 11件):**
- `test_fukusho_module_imports` — 公開 API import 可能性
- `test_raw_vs_validated_basic_8_horses` — 8頭レース raw/validated 整合
- `test_raw_vs_validated_basic_6_horses` — 6頭レース payout_places=2
- `test_drift_is_dead_heat_only` — drift は dead_heat status に分類
- `test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status` (**HIGH #1**)
- `test_unresolved_triggers_hr_missing` — HR 欠損で unresolved
- `test_no_fukusho_sale_under_5_horses` — 4頭以下は複勝発売なし
- `test_payout_places_uses_torokutosu_not_syussotosu` — Pitfall 3
- `test_canonicalize_markers_raw_string_form` (**HIGH #5**)
- `test_canonicalize_markers_numeric_cast_form` (**HIGH #5**)
- `test_canonicalize_markers_missing_time` (**NEW HIGH #3**)

**LABEL-04 + §7.2 (Task 2, 16件):**
- `test_dead_heat_all_payout_positive` / `test_scratch_cancel_excluded`
- `test_dead_loss_in_training` / `test_dead_loss_in_obstacle_race_excluded_for_obstacle_reason` (**HIGH #6**)
- `test_race_cancelled_all_unresolved` (**HIGH #4 強化**)
- `test_select_se_state_includes_datakubun_9` (**HIGH #4 regression**)
- `test_fuseiritu_flag2_unresolved` / `test_tokubaraiflag2_with_payout_validated` / `test_tokubaraiflag2_without_payout_unresolved` (W4 複勝特払)
- `test_is_model_eligible_obstacle_syubetucd` / `_newcomer_syubetucd` / `_maiden_syubetucd_included` (**MEDIUM 解決**) / `_class_below_minimum` / `_validated_normal`
- `test_dochachukubun_dead_heat_detection` (**MEDIUM #2** payout-table authoritative)
- `test_select_se_state_no_row_multiplication_on_timediff_merge` (**NEW HIGH #2**)

### Helper 関数

- `_build_hr_row(**overrides) -> dict` — n_harai 1レース分の合成行
- `_build_se_row(umaban, **overrides) -> dict` — n_uma_race 1馬行分
- `_build_label_input_df(n_horses, hr_overrides, se_overrides, syubetucd, class_level_numeric) -> (hr_df, se_df, race_df)`
- `_load_label_spec() -> dict` — src/config/label_spec.yaml（Plan 02-01 作成済み）を読込
- `_get_fukusho_label_module()` — 遅延 import helper（RED state を collection-safe に保つため）

## TDD RED state（成功条件）

```
$ uv run pytest tests/test_fukusho_label.py --collect-only
========================= 27 tests collected in 0.23s ==========================
```

```
$ uv run pytest tests/test_fukusho_label.py
...
_________________________ test_fukusho_module_imports __________________________
>       from src.etl import fukusho_label
E       ImportError: cannot import name 'fukusho_label' from 'src.etl'
============================== 27 failed in 0.58s ==============================
```

**全27テスト RED（ImportError）**。これは意図的であり、Plan 02-03 GREEN が `src/etl/fukusho_label.py` を実装することで全テスト通過に転じる。

### 設計判断: 遅延 import

Plan 02-02 の acceptance criteria は `uv run pytest --collect-only | grep "test_..."` でテスト名が出ることを要求する。module-level `from src.etl.fukusho_label import ...` は ImportError で collection 全体を落としてしまい、テスト名が列挙されない。そのため `_get_fukusho_label_module()` helper で各テスト内遅延 import し、collection は成功・実行時に ImportError で fail する構造にした（GREEN 実装では helper 透過的に動作・テスト本体は書き換え不要）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Collection-safe RED state のため module-level import を遅延 import 化**
- **Found during:** Task 1 verify 段階
- **Issue:** Plan 02-02 acceptance は `--collect-only` で27テスト名が列挙されることを要求するが、module-level `from src.etl.fukusho_label import ...` は ImportError で collection 全体を失敗させる
- **Fix:** `_get_fukusho_label_module()` helper を導入し各テスト内で遅延 import・collection は成功・実行時に ImportError で fail
- **Files modified:** tests/test_fukusho_label.py
- **Commit:** 7c780b0

それ以外: Plan 02-02 に忠実に実装。Task 1・Task 2 ともに同じファイルを対象とするため単一 RED commit で両タスク完了。

## Known Stubs

無し（テストファイルのみ・実装 stub は作成しない・RED state を保証）。

## Threat Flags

無し（テスト追加のみ・新規ネットワーク/auth/schema surface なし）。

## Verification Results

- [x] `test -f tests/test_fukusho_label.py` 成功（771 行）
- [x] `uv run pytest tests/test_fukusho_label.py --collect-only` が27テスト収集
- [x] `uv run pytest tests/test_fukusho_label.py` が RED（全27テスト ImportError / ModuleNotFoundError）
- [x] `from src.etl import fukusho_label` を含む（遅延 import helper 経由・`_canonicalize_markers` `_select_se_state` 含む）
- [x] LABEL-01/02/04 の全シナリオ + D-03 §7.2 適格性（未勝利 precision 含む）を網羅
- [x] 全テスト DB 不要（`@pytest.mark.requires_db` なし）
- [x] REVIEWS HIGH #1/#4/#5/#6 + MEDIUM + NEW HIGH #2/#3 全テスト存在

## Self-Check: PASSED

- FOUND: tests/test_fukusho_label.py (771 行)
- FOUND: 7c780b0 commit (test(02-02): add failing tests for LABEL-01/02/04 (TDD RED))
- FOUND: 27 tests collected by pytest
- FOUND: 27 tests failing with ImportError (RED state confirmed)
