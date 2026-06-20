---
phase: 05-ev-backtest
plan: 01
subsystem: ev-backtest
tags: [backtest, bt-window, red-stubs, wave-0, leak-prevention]
status: complete
requires:
  - src/utils/group_split.py (race_id_time_series_split・既存)
  - mlxtend.evaluate.GroupTimeSeriesSplit (既存 re-export)
provides:
  - src/utils/group_split.py::BTWindow (dataclass frozen=True)
  - src/utils/group_split.py::BT_WINDOWS (§15.5 完全準拠リスト定数)
  - src/utils/group_split.py::get_bt_race_ids(races, bt) -> tuple[list[str], list[str]]
  - tests/ev/conftest.py::make_jodds_mock/make_harai_mock/make_label_mock/make_prediction_mock
  - tests/ev/test_*.py (6 RED stub・Wave 1/2 GREEN 化対象)
  - tests/model/test_orchestrator_bt.py (RED stub・Wave 1/2 GREEN 化対象)
  - tests/db/test_backtest_load.py (RED stub・Wave 2 GREEN 化対象)
affects:
  - scripts/run_backtest.py (Plan 05 で BT_WINDOWS を import)
  - src/model/data.py::split_3way (Wave 1/2 で periods パラメータ追加・test_orchestrator_bt が検証)
  - src/ev/*.py (Wave 1/2 で新設・test_*.py が検証)
  - src/db/backtest_load.py (Wave 2 で新設・test_backtest_load.py が検証)
tech-stack:
  added: []
  patterns:
    - raise ValueError guard (python -O 生存・HIGH #3・既存 group_split と同一)
    - lazy import in RED stubs (Phase 2 decision 02-22 と同一・collection 保証)
    - §15.5 要件正優先 (2019-06 開始・Phase 3 D-09 の 2016H2 でない)
key-files:
  created:
    - tests/ev/__init__.py
    - tests/ev/conftest.py
    - tests/ev/test_ev_rank.py
    - tests/ev/test_purchase_simulator.py
    - tests/ev/test_metrics.py
    - tests/ev/test_odds_snapshot.py
    - tests/ev/test_refund_accounting.py
    - tests/ev/test_bl3_betting.py
    - tests/db/__init__.py
    - tests/db/test_backtest_load.py
    - tests/model/test_orchestrator_bt.py
  modified:
    - src/utils/group_split.py (追記のみ・既存 race_id_time_series_split は後方互換)
    - tests/utils/test_group_split.py (新設7テスト追記・既存8テストは変更なし)
decisions:
  - "§15.5 優先: BT-1..3 train_start='2019-06-01'（Phase 3 D-09 の 2016H2〜 でなく要件正を適用）"
  - "BT-4/5 test 年は 2024 に揃える（D-03 + planner A2・BT-1..3 の test 年と比較可能にするため）"
  - "MEDIUM-01a: 固定 BT窓と mlxtend.GroupTimeSeriesSplit の等価性を docstring + test で立証（race_id disjoint + strict chronological を両者とも保証）"
  - "Wave 0 RED stub は lazy import（関数内 import）で collection 保証・Phase 2 decision 02-22 と同一パターン（module-level import だと collection error で --collect-only の acceptance criteria 達成不能）"
metrics:
  duration: 10m
  completed: 2026-06-20T23:14:38Z
  task_count: 2
  file_count: 13
---

# Phase 5 Plan 01: BT窓ヘルパ新設 + Wave 0 RED stub 集群 Summary

BACK-01 構造的ブロック確立: BT-1..5 固定窓 helper（§15.5 完全準拠・2019-06 開始）と Phase 5 全 unit test の Wave 0 RED stub 集群（9 テストファイル + 4 合成 fixtures）を構築。後続 Wave 1/2 plan が RED→GREEN で進める土台を提供。

## What Was Built

### Task 1: BT窓ヘルパ新設（group_split.py 追記）+ 新設分 unit test GREEN

**RED (7c2de9f):** `tests/utils/test_group_split.py` に behavior 7テストを追記（実装前なので ImportError で RED）。

**GREEN (4adf974):** `src/utils/group_split.py` に以下を追記（既存 `race_id_time_series_split` は関数本体未編集・後方互換）:

- `BTWindow` dataclass（`frozen=True`・`name`/`train_start`/`train_end`/`test_start`/`test_end`/`window_type`）
- `BT_WINDOWS` 定数リスト（§15.5 完全準拠）:
  - BT-1: train 2019-06-01..2022-12-31 / test 2023 / expanding
  - BT-2: train 2019-06-01..2023-12-31 / test 2024 / expanding
  - BT-3: train 2019-06-01..2024-12-31 / test 2025 / expanding
  - BT-4: train 2021-01-01..2023-12-31 / test 2024 / rolling（直近3年）
  - BT-5: train 2019-01-01..2023-12-31 / test 2024 / rolling（直近5年）
- `get_bt_race_ids(races, bt) -> tuple[list[str], list[str]]`: race_date 区間 filter + 既存3ガード（race_id disjoint / strict chronological / non-empty）を `raise ValueError` で保証（HIGH #3 python -O 生存・T-05-01 mitigate）

**等価性立証（MEDIUM-01a・T-05-01b mitigate）:** docstring と `test_bt_window_equivalent_to_group_ts_split` で、固定 BT窓（race_date 区間分割）と `mlxtend.evaluate.GroupTimeSeriesSplit`（group-aware 時系列分割）が共に race_id-level disjoint + strict chronological を保証することを立証。リーク防止の観点で両者は等価。

### Task 2: Wave 0 RED stub 集群 + 合成 fixtures

**コミット (63a22f4):** 9 テストファイル + 4 合成データ fixtures を新設。

**合成データ fixtures（`tests/ev/conftest.py`）:**

- `make_jodds_mock(race_key, snapshots, *, umabans)`: JODDS snapshot（`HappyoTime`/`FukuOddsLow`/`FukuOddsHigh`/`Umaban`/race_key PK 8カラム・RESEARCH §1.1 実証）。`umabans` 指定で複数馬の per-horse snapshot 生成可（HIGH-1 MEDIUM・`test_odds_snapshot_multi_horse` 用）。
- `make_harai_mock(scenario)`: HARAI 払戻系 flags（`FuseirituFlag2`/`HenkanFlag2`/`TokubaraiFlag2`/`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5`・9シナリオ）
- `make_label_mock(scenario)`: `label.fukusho_label` フラグ（`is_scratch_cancel`/`is_race_cancelled`/`is_race_excluded`/`is_dead_loss`/`is_fukusho_sale_available`/`fukusho_payout_places`/`fukusho_hit_validated`・9シナリオ）
- `make_prediction_mock(race_key, n_horses)`: `p_fukusho_hit` + race_key + PK 7カラム

**9 テストファイル（全て lazy import で collection 保証）:**

| File | 要件 | Test Count | 備考 |
|------|------|------------|------|
| `tests/ev/test_ev_rank.py` | EV-01/EV-02 | 4 | EV 計算・S-D ランク階層判定 |
| `tests/ev/test_purchase_simulator.py` | BACK-02 | 5 | filter / top2 / tiebreak / no_eligible / no_sale |
| `tests/ev/test_metrics.py` | §11.6 | 4 | recovery_rate / refund_excluded / max_drawdown / counts |
| `tests/ev/test_odds_snapshot.py` | BACK-03/BACK-04 | 6 | backward / no_bet / special_values / future_leak / day_boundary / **multi_horse** (HIGH-1 MEDIUM) |
| `tests/ev/test_refund_accounting.py` | BACK-03 | 17 | 9シナリオ parametrize + 8個別（normal/scratch/excluded/dead_loss/fuseiritu/race_cancelled/no_sale/deadheat） |
| `tests/ev/test_bl3_betting.py` | D-04 | 3 | select_top2_low_odds / no_ev / caveat |
| `tests/model/test_orchestrator_bt.py` | D-03 | 2 | split_3way periods injection / backward compat |
| `tests/db/test_backtest_load.py` | BACK-03 | 2 | idempotent / scoped_swap（`@pytest.mark.requires_db`） |

## TDD Gate Compliance

Task 1 は `type="auto" tdd="true"` で RED → GREEN の2コミット構成:

1. **RED gate (7c2de9f):** `test(05-01): add failing BT window helper tests (RED)` — 7テストが ImportError で RED
2. **GREEN gate (4adf974):** `feat(05-01): implement BT-1..5 window helper (GREEN)` — 実装後15テスト（既存8 + 新規7）が GREEN

Task 2 は RED stub 集群の作成のみ（`type="auto" tdd="true"` だが実装は後続 Wave 1/2 plan が担当）。本 plan の役割は「RED 状態のテスト群を配置して後続 plan が GREEN 化する土台を作る」こと。Wave 0 RED stub は実装前なので RED のままで完了（acceptance criteria「RED 実行: ImportError/AttributeError で RED」満たす）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking fix] RED stub の module-level import を lazy import 化**

- **Found during:** Task 2 collection 検証時
- **Issue:** plan acceptance criteria「9 テストファイルが `--collect-only` で列挙される」と「RED 実行: ImportError/AttributeError で RED」が、module-level import では両立不能（ImportError で collection error になり列挙されない）。
- **Fix:** Phase 2 decision 02-22「RED テスト collection 保証のため module-level import を遅延 import 化」と同一パターンを採用。全9テストファイルで実装モジュールの import を関数内（lazy）に移動。collection は成功（44 tests collected）し、実行時 ImportError/TypeError で RED になる。
- **Files modified:** `tests/ev/test_*.py`（6ファイル）、`tests/db/test_backtest_load.py`、`tests/model/test_orchestrator_bt.py`
- **Commit:** 63a22f4（Task 2 コミットに統合）

**2. [Rule 1 - Bug fix] `test_rank_B_no_odds_threshold` の入力値修正**

- **Found during:** Task 2 テスト作成時
- **Issue:** 元の入力（`p=0.16, odds=1.2`）では `EV_lower = 0.192` となり §11.5 B 条件 `EV≥1.05` を満たさず、実際は D ランクになるため B ランクを検証できなかった。
- **Fix:** `odds=7.0`（`EV=0.16*7.0=1.12`）に修正し、B ランク（`EV≥1.05 AND p≥0.15`・odds 閾値なし）を正しく検証。
- **Files modified:** `tests/ev/test_ev_rank.py`
- **Commit:** 63a22f4（Task 2 コミットに統合）

## Threat Mitigation Verification

| Threat ID | Category | Mitigation | Verification |
|-----------|----------|------------|--------------|
| T-05-01 | Information Disclosure | `get_bt_race_ids` の race_id disjoint / strict chronological を `raise ValueError` で保証 | `test_get_bt_race_ids_raises_on_leak` + `test_get_bt_race_ids_uses_raise_not_assert` (7c2de9f RED / 4adf974 GREEN) |
| T-05-02 | Tampering | BT-1..3 train_start='2019-06-01' を test で assert（§15.5 優先・D-09 でない） | `test_bt_window_2019_06_start` (GREEN) |
| T-05-01b | Information Disclosure | 固定 BT窓と `mlxtend.GroupTimeSeriesSplit` の等価性を docstring + test で立証 | `test_bt_window_equivalent_to_group_ts_split` (GREEN)・race_id disjoint + strict chronological を両者とも保証 |

## Verification

全 acceptance criteria 検証済み:

```
=== Task 1 GREEN (BT窓ヘルパ新設分 unit test) ===
$ uv run pytest tests/utils/test_group_split.py -x -q
15 passed in 1.07s  (既存8 + 新規7)

=== Wave 0 collect (9 テストファイル列挙) ===
$ uv run pytest tests/ev/ tests/db/test_backtest_load.py tests/model/test_orchestrator_bt.py --co -q
44 tests collected in 0.01s

=== RED 実行 (src.ev 未実装・実装前のため RED) ===
$ uv run pytest tests/ev/ tests/model/test_orchestrator_bt.py -q
42 failed in 0.21s  (ModuleNotFoundError: src.ev / TypeError: split_3way unexpected kw 'periods')

=== KEIBA_SKIP_DB_TESTS=1 ===
$ uv run pytest tests/db/test_backtest_load.py -v
2 skipped  (KEIBA_SKIP_DB_TESTS=1 set)

=== 既存テストスイート回帰確認 ===
$ uv run pytest --ignore=tests/ev --ignore=tests/db --ignore=tests/model/test_orchestrator_bt.py --ignore=tests/utils/test_group_split.py -q
230 passed, 24 skipped in 29.47s  (回帰なし)
```

Acceptance criteria:

- [x] `src/utils/group_split.py` に `class BTWindow` と `BT_WINDOWS` と `def get_bt_race_ids` が含まれる
- [x] BT-1.train_start == '2019-06-01'（grep で3箇所 BT-1/2/3 に現れる）
- [x] `get_bt_race_ids` の source に `raise ValueError` が含まれる（`test_get_bt_race_ids_uses_raise_not_assert` で検証）
- [x] `uv run pytest tests/utils/test_group_split.py` が全件 GREEN（既存 + 新規7件）
- [x] 既存 `race_id_time_series_split` のシグネチャ・docstring は変更なし（関数本体未編集・docstring ヘッダに Phase 5 説明追記 + dataclass import + 末尾追記のみ）
- [x] `tests/ev/__init__.py` と `tests/ev/conftest.py` と `tests/db/__init__.py` が存在
- [x] `def make_jodds_mock` / `make_harai_mock` / `make_label_mock` / `make_prediction_mock` が含まれる
- [x] `make_jodds_mock` の戻り値 DataFrame が `Umaban` 列を保持（HIGH-1 MEDIUM・JODDS PK 8カラム）
- [x] 9 テストファイルが `--collect-only` で列挙される（44 tests collected）
- [x] RED 実行: ImportError/AttributeError で RED（`src.ev` 未実装・`split_3way` に `periods` パラメータ未存在）
- [x] `test_backtest_load.py` は `--collect-only` で表示・`KEIBA_SKIP_DB_TESTS=1` で skip
- [x] `tests/conftest.py` の skip policy は変更なし

## Success Criteria

- [x] BACK-01 構造的ブロック確立: `BT_WINDOWS`（§15.5 完全準拠・2019-06 開始）+ `get_bt_race_ids`（race_id disjoint + strict chronological guard）が GREEN
- [x] 固定 BT窓と `mlxtend.GroupTimeSeriesSplit` の等価性を docstring + test で立証（MEDIUM-01a・T-05-01b）
- [x] Wave 0 RED stub 集群（9 テストファイル + 4 合成 fixtures・Umaban 列保持で per-horse odds テスト対応）が後続 Wave 1/2 plan で GREEN 化する準備完了
- [x] 既存 `race_id_time_series_split` は後方互換（変更なし）

## Commits

| Hash | Type | Message |
|------|------|---------|
| 7c2de9f | test(RED) | add failing BT window helper tests (RED) |
| 4adf974 | feat(GREEN) | implement BT-1..5 window helper (GREEN) |
| 63a22f4 | test | add Wave 0 RED stub cluster + synthetic fixtures |

## Self-Check: PASSED

### Created files exist

- FOUND: src/utils/group_split.py
- FOUND: tests/utils/test_group_split.py
- FOUND: tests/ev/__init__.py
- FOUND: tests/ev/conftest.py
- FOUND: tests/ev/test_ev_rank.py
- FOUND: tests/ev/test_purchase_simulator.py
- FOUND: tests/ev/test_metrics.py
- FOUND: tests/ev/test_odds_snapshot.py
- FOUND: tests/ev/test_refund_accounting.py
- FOUND: tests/ev/test_bl3_betting.py
- FOUND: tests/db/__init__.py
- FOUND: tests/db/test_backtest_load.py
- FOUND: tests/model/test_orchestrator_bt.py

### Commits exist

- FOUND: 7c2de9f (test(05-01): add failing BT window helper tests (RED))
- FOUND: 4adf974 (feat(05-01): implement BT-1..5 window helper (GREEN))
- FOUND: 63a22f4 (test(05-01): add Wave 0 RED stub cluster + synthetic fixtures)

### TDD gate commits exist

- FOUND: `test(...)` commit (RED gate・7c2de9f)
- FOUND: `feat(...)` commit after RED (GREEN gate・4adf974)
