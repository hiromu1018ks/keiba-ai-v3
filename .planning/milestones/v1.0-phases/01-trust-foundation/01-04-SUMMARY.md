---
phase: 01-trust-foundation
plan: 04
subsystem: trust-foundation (リーク防止プリミティブ bootstrap)
tags: [phase-01, leak-prevention, pit-join, group-split, category-map, calibrator, mlxtend, sklearn]
requires: [01-01]
provides:
  - "src.utils.pit_join.pit_join_backward: merge_asof(direction='backward') wrapper・呼出元入力(sort前)の sortedness を raise ValueError で検証"
  - "src.utils.group_split.race_id_time_series_split: race_id 単位時系列CV・disjoint + strict chronological(max(train)<min(test)) を raise ValueError で強制"
  - "src.utils.group_split.GroupTimeSeriesSplit: mlxtend 副 API re-export（BT-1..BT-5 等 fallback）"
  - "src.utils.category_map.fit_category_map / apply_category_map: 訓練窓 fit の frozen map・__UNSEEN__/__MISSING__ フォールバック・非負 int32"
  - "src.utils.calibrator.fit_prefit_calibrator: sklearn 1.9.0 FrozenEstimator による prefit 校正・時系列順序違反で raise ValueError"
  - "src.utils.category_map.UNSEEN / MISSING: sentinel 文字列定数"
  - "tests/utils/test_{pit_join,group_split,category_map,calibrator}.py: D-17 smoke + REVIEWS HIGH 回帰検出器"
affects:
  - "Phase 3 (features): pit_join_backward / category_map fit-apply を即 import して利用"
  - "Phase 4 (models): calibrator / category_map を即 import して利用"
  - "Phase 5 (backtest): race_id_time_series_split を BT-1..BT-5 窓に適用"
tech-stack:
  added: []
  patterns:
    - "merge_asof(direction='backward') を wrap し sortedness pre-check を sort 前に raise ValueError で実行（HIGH #1）"
    - "race_id disjoint + strict max(train_time)<min(test_time) を両方 raise ValueError で強制（HIGH #2）"
    - "リーク防止ガードは assert ではなく raise ValueError のみ（HIGH #3・python -O でも生存）"
    - "sklearn 1.9.0 prefit: FrozenEstimator で訓練済み推定器をラップして CalibratedClassifierCV へ（cv='prefit' 文字列は 1.9.0 で削除）"
    - "frozen category map: 訓練窓で fit → pickle/joblib → val/test に apply（再 fit 禁止）"
    - "未知 ID は __UNSEEN__・欠損は __MISSING__・apply は非負 int32（pandas category code -1 ハザード回避）"
key-files:
  created:
    - src/utils/__init__.py
    - src/utils/pit_join.py
    - src/utils/group_split.py
    - src/utils/category_map.py
    - src/utils/calibrator.py
    - tests/utils/__init__.py
    - tests/utils/test_pit_join.py
    - tests/utils/test_group_split.py
    - tests/utils/test_category_map.py
    - tests/utils/test_calibrator.py
decisions:
  - "sklearn 1.9.0 で cv='prefit' 文字列が削除されたため、FrozenEstimator で訓練済み推定器をラップして CalibratedClassifierCV へ渡す公式 prefit イディオムに適合（リーク防止セマンティクスは不変・Rule 3 blocking issue）"
  - "group_split の strict chronological ガードは train_max < test_min で strict '<'（等値不可）とし、同一 race_start_datetime のレース群が train/test を跨ぐことを明示的に禁止（HIGH #2）"
  - "pit_join_backward は呼出元が事前ソート済みの DataFrame を渡す契約とし、関数内で sort_values しない（sort 後チェックは未ソート入力を黙って通すため HIGH #1）"
  - "mlxtend.evaluate.GroupTimeSeriesSplit を副 API として re-export し、BT-1..BT-5 等の異なる policy が必要な場合の fallback に備える"
metrics:
  duration: "約18分"
  completed: "2026-06-17"
  tasks_total: 2
  files_created: 10
  commits: 5
---

# Phase 01 Plan 04: リーク防止プリミティブ bootstrap Summary

成功基準#4 の4プリミティブ（`pit_join` / `group_split` / `category_map` / `calibrator`）を `src/utils/` に importable 実体 + D-17 smoke test + REVIEWS HIGH #1/#2/#3 回帰検出器として実装した。01-RESEARCH.md §Code Examples 2-5 をベースにしつつ、3つの HIGH 修正（sort 前チェック / strict `<` / assert→raise）を適用。Phase 3（feature PIT join / category map fit）/ Phase 4（calibrator / category map）/ Phase 5（GroupTimeSeriesSplit）が即 import して利用可能。本物の LightGBM/CatBoost 不要・dummy estimator（DummyClassifier / GradientBoostingClassifier）で検証。

## Tasks Completed

| Task | Name | Commit | Key files |
|------|------|--------|-----------|
| 1 | pit_join.pit_join_backward + group_split.race_id_time_series_split（REVIEWS HIGH #1/#2/#3） | d796a11 / 116fb7e | src/utils/{pit_join,group_split}.py, tests/utils/test_{pit_join,group_split}.py |
| 2 | category_map.fit/apply + calibrator.fit_prefit_calibrator（REVIEWS HIGH #3） | c650480 / 60cfdcd | src/utils/{category_map,calibrator}.py, tests/utils/test_{category_map,calibrator}.py |
| (lint) | ruff lint/format 適用 | 5a03c84 | src/utils/*, tests/utils/* |

両タスクとも TDD（RED: 失敗テスト commit → GREEN: 実装 commit）で実行した。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] sklearn 1.9.0 で `CalibratedClassifierCV(cv='prefit')` が削除**

- **Found during:** Task 2 GREEN フェーズ
- **Issue:** plan / 01-RESEARCH Example 5 / CLAUDE.md §15.2 は `CalibratedClassifierCV(estimator=base, method=method, cv="prefit")` を前提としていた。しかしインストール済みの **scikit-learn 1.9.0**（pyproject.toml pin 通り）で `cv='prefit'` 文字列を渡すと `InvalidParameterError: The 'cv' parameter of CalibratedClassifierCV must be an int in the range [2, inf), ... Got 'prefit' instead.` で fail する。1.9.0 の param validation が cv='prefit' を明示的に拒否する。
- **Fix:** sklearn 1.9.0 の**正式な prefit イディオム**である `sklearn.frozen.FrozenEstimator` で訓練済み推定器をラップしてから `CalibratedClassifierCV(estimator=frozen, method=method)` へ渡す方式に適合（1.9.0 docstring 明記: "Already fitted classifiers can be calibrated by wrapping the model in a FrozenEstimator. In this case all provided data is used for calibration. The user has to take care manually that data for model fitting and calibration are disjoint."）。
- **リーク防止セマンティクスは不変:** "calibration slice が train より厳格に未来" を `raise ValueError` guard で強制し、train/calib の disjoint 保証を構造化している（ユーザー手動保証を関数契約で機械強制）。`cv='prefit'` 廃止前後で look-ahead leak 防止の実効性は同等。
- **テスト側も追従:** `.cv == 'prefit'` 検証を廃止し、代わりに `cal.estimator` が `FrozenEstimator` インスタンスであることを検証（1.9.0 で再 fit されていない prefit セマンティクスの直接証明）。
- **Files modified:** src/utils/calibrator.py, tests/utils/test_calibrator.py
- **Commit:** 60cfdcd

### Plan-as-Written に対する他の調整

- **`test_calibrator_uses_estimator_arg_not_base_estimator` の検査対象絞り込み:** モジュール全体ソースを検査すると docstring 中の "base_estimator=" 言及が誤検知されるため、`inspect.getsource(fit_prefit_calibrator)` で関数本体内の `CalibratedClassifierCV(base_estimator=` 呼出のみを検査するよう調整（HIGH #3 の検証意図は維持）。
- **`test_no_silent_resort_implementation_guard` のため docstring 表記調整:** リグレッションガードが `inspect.getsource(pit_join_backward)` 内の `sort_values(` トークン出現順を検査するため、実装内の `sort_values` 言及を（関数内で sort しないという注意書き含め）別表現に置換。機能的影響なし。

## Threat Flags

該当なし。plan の `<threat_model>` T-04-01..T-04-06 は全て mitigated 状態で実装済み:
- T-04-01 (sortedness): `pit_join_backward` が sort 前に `raise ValueError`（HIGH #1 対応）
- T-04-02 (race_id disjoint + 等値タイムスタンプ): `race_id_time_series_split` が strict `<` で `raise ValueError`（HIGH #2 対応）
- T-04-03 (category map 再 fit): fit/apply 分離 API 設計
- T-04-04 (NaN→-1 ハザード): `__MISSING__` sentinel + 非負 int32
- T-04-05 (KFold shuffle leak): FrozenEstimator + 時系列順序 `raise ValueError`
- T-04-06 (`python -O` で assert 無効化): 全 guard が `raise ValueError` のみ・3つの回帰検出器が `inspect.getsource()` で `assert` トークン不在を検証

新規に plan 外の security-relevant な表面は導入していない。

## Known Stubs

該当なし。4プリミティブは全て dummy estimator（DummyClassifier / GradientBoostingClassifier）で検証済みの完全実体。本物 LightGBM/CatBoost は Phase 4 で導入予定（plan scope 外）。

## Verification Results

- `uv run pytest tests/utils/ -v`: **27 passed**（4 smoke ファイル全て green）
  - test_pit_join.py: 7件（sortedness raise×2, no-silent-resort guard, no-future-leak, by-group, tolerance, no-assert）
  - test_group_split.py: 8件（disjoint, strict chronological, equal-timestamp-cross raise, n_splits, n_splits-too-large, missing-columns, no-assert, mlxtend re-export）
  - test_category_map.py: 6件（unseen/missing sentinel, NaN handling, unseen fallback, missing fallback, non-negative int32, order preservation）
  - test_calibrator.py: 6件（after-train pass, prefit semantics via FrozenEstimator, before-train raise ValueError, `python -O` サブプロセス検証, no-assert, estimator= 引数）
- `uv run python -O -m pytest tests/utils/ -q`: **27 passed**（`-O` 最適化でも同一結果・HIGH #3 のランタイム検証）
- `uv run ruff check src/utils/ tests/utils/`: **All checks passed**
- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q`: **39 passed, 3 skipped**（01-01/01-02 の既存テストも含め回帰なし）
- 各 utils モジュールが `from src.utils.X import Y` で import 可能（4プリミティブ + sentinel 定数 + GroupTimeSeriesSplit re-export）

### Acceptance Criteria grep 検証結果

- `src/utils/pit_join.py`: `raise ValueError` 9件 / `assert ` 0件 / `is_monotonic_increasing` が77行目に出現し `sort_values(` トークン不在（HIGH #1・sort 後チェックでない）
- `src/utils/group_split.py`: `raise ValueError` 9件 / `assert ` 0件 / `train_time_max < test_time_min` で strict `<`（HIGH #2・`<=` は0件）
- `src/utils/category_map.py`: `UNSEEN = "__UNSEEN__"` / `MISSING = "__MISSING__"` / `def fit_category_map` / `def apply_category_map` / `.astype("int32")`
- `src/utils/calibrator.py`: `raise ValueError` / `assert ` 0件 / `CalibratedClassifierCV(estimator=` / `FrozenEstimator`（sklearn 1.9.0 prefit イディオム）

## Self-Check: PASSED

### Created files exist

- src/utils/__init__.py: FOUND
- src/utils/pit_join.py: FOUND
- src/utils/group_split.py: FOUND
- src/utils/category_map.py: FOUND
- src/utils/calibrator.py: FOUND
- tests/utils/__init__.py: FOUND
- tests/utils/test_pit_join.py: FOUND
- tests/utils/test_group_split.py: FOUND
- tests/utils/test_category_map.py: FOUND
- tests/utils/test_calibrator.py: FOUND

### Commits exist

- d796a11: FOUND (RED: pit_join + group_split tests)
- 116fb7e: FOUND (GREEN: pit_join + group_split impl)
- c650480: FOUND (RED: category_map + calibrator tests)
- 60cfdcd: FOUND (GREEN: category_map + calibrator impl)
- 5a03c84: FOUND (chore: ruff lint)
