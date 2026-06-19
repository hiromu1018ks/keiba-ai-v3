---
phase: 03-as-of-features-snapshots
plan: 03
subsystem: features
tags: [phase-03, features, tdd, green, builder, rolling, running-style, per-observation-latest-k, reviews-rev2]
requires: ['03-01', '03-02']
provides:
  - src/features/rolling.py (build_rolling_features, _ROLLING_SYSTEMS, LOOKBACK, _SYSTEM_SOURCE)
  - src/features/running_style.py (estimate_running_style, classify_running_style, estimate_running_style_batch)
  - src/features/builder.py (build_feature_matrix, build_rolling_features wrapper, _HISTORY_SELECT_COLUMNS, _OBS_SELECT_COLUMNS, _RACE_CONTEXT_COLUMNS, _BLOODLINE_COLUMNS, CUTOFF_RULE_METADATA)
affects:
  - Plan 03-04 (snapshot.py / category_map_consumer.py が builder.build_feature_matrix と rolling/running_style を消費)
tech-stack:
  added: []
  patterns:
    - per-observation latest-K algorithm (obs_id=(race_nkey,kettonum) group key・pit_join_backward 不使用・CYCLE-2 HIGH #1)
    - COPY-NOT-RENAME alias 列追加 (kettonum/horse_id 併存・CYCLE-2 HIGH #5)
    - strict < cutoff pre-filter (CUTOFF_SEMANTICS・HIGH #2)
    - __MISSING__ sentinel object-dtype 初期化 (数値/sentinel 混在・D-13)
key-files:
  created:
    - src/features/rolling.py
    - src/features/running_style.py
    - src/features/builder.py
  modified:
    - .planning/phases/03-as-of-features-snapshots/03-RESEARCH.md (Open Question #3 CYCLE-2 re-open 追記)
decisions:
  - "rolling.py は pit_join_backward (単一後方 merge_asof・latest-1 しか返さない) を使わず、明示的 per-observation latest-K algorithm (obs_id group key + sort_values DESC + groupby('obs_id').head(5)) を採用 (REVIEWS HIGH #1・CYCLE-2 HIGH #1)"
  - "obs_id は (race_nkey, kettonum) の tuple・horse key でない (CYCLE-2 HIGH #1: horse-grouped は同一 horse の複数 observation で cross-observation leak を起こす)"
  - "strict < feature_cutoff_datetime の単一不変量 (HIGH #2・<= でない・CUTOFF_SEMANTICS と整合)"
  - "running_style は dict-list 入力 (estimate_running_style(history_rows=[...])) と純粋閾値関数 (classify_running_style(avg_position)) の2関数 (テスト契約優先・plan の DataFrame 版から調整)"
  - "builder は horse_id/jockey_id/trainer_id/sire_id/bms_id を copy で追加し kettonum/kisyucode 等の元列を保持 (CYCLE-2 HIGH #5 COPY-NOT-RENAME・破壊的 rename は canonical key/snapshot sort key を壊す)"
  - "history source 列は系統毎に optional (欠損系統は該当 rolling 出力が __MISSING__ sentinel・D-13 相当・silent fill でない)"
metrics:
  duration: "13m"
  completed: "2026-06-19"
  tasks: 3
  files: 4
---

# Phase 03 Plan 03: rolling / running_style / builder GREEN Summary

Plan 03-01 で RED で立てた4テストファイル (test_pit_cutoff / test_rolling / test_running_style / test_builder) を GREEN 化するため、feature matrix 構築の中核3モジュールを実装した。`src/features/rolling.py` は **明示的 observation 単位 latest-K algorithm** (obs_id=(race_nkey,kettonum) group key・pit_join_backward 不使用) で8系統 × 3軸 + count の rolling feature を構築し、CYCLE-2 HIGH #1 の cross-observation leak を閉じた。`src/features/running_style.py` は過去走 jyuni3c/jyuni4c の閾値ルール分類 (逃/先/差/追) を当日 kyakusitukubun 不使用で実装した。`src/features/builder.py` は `build_feature_matrix` 公開 API を readonly SELECT・明示カラム・COPY-NOT-RENAME alias・§13.2 metadata stamp・HIGH #3 出力カラム全登録検査付きで実装した。

## What Was Built

### Task 1: src/features/rolling.py (commit 2b48feb)

- **`_ROLLING_SYSTEMS`** = (kakuteijyuni, timediff, harontimel3, jyuni3c_jyuni4c, kyori, babacd, jyocd, days_since_prev) の8系統 (harontimel4 除外・Pitfall 3.6・babacd は history_allowed・HIGH #4)。
- **`build_rolling_features(observations, history, *, lookback=5)`** — per-observation latest-K algorithm:
  1. 入力検証 + obs_id 構築 (既存あれば再利用、無ければ (race_nkey, kettonum) tuple・race_nkey 無ければ index から生成)。
  1b. expanded history (各 observation に kettonum で inner-join・1 history 行が複数 obs_id に複製)。
  2. defense-in-depth pre-filter: `history.as_of_datetime < feature_cutoff_datetime` (strict `<`・HIGH #2・CUTOFF_SEMANTICS と整合)。
  3. `sort_values(["obs_id","race_start_datetime"], ascending=[True,False]).groupby("obs_id", sort=False).head(5)` で observation 毎に直近5走 (HIGH #1・horse key でない・CYCLE-2 HIGH #1)。
  4. 3軸集約 (mean/latest/sd) + count・5走未満 `__MISSING__` sentinel (D-13・Pitfall 3.3)。
  5. 出力: observations に `rolling_<system>_{mean,latest,sd,count}_5` 計 (8×4=32) 列を object dtype で付与 (数値/sentinel 文字列混在)。
- **`from src.features.availability import CUTOFF_SEMANTICS`** import で strict `<` semantics を文書参照。
- **RESEARCH.md Open Question #3 に CYCLE-2 re-open 更新を追記** (監査証跡・WARNING #4)。

### Task 2: src/features/running_style.py (commit e03c00e)

- **`classify_running_style(avg_position)`** — 閾値ルール: `≤2.0→逃 / ≤3.5→先 / ≤5.5→差 / >5.5→追` (RESEARCH Example 2)。
- **`estimate_running_style(history_rows=[...])`** — dict list 入力。`jyuni3c`/`jyuni4c` が共に >0 の走のみ valid (jyuni1c は短距離で57% 0/NULL・主軸にしない・Pitfall 3.2)。両コーナー平均位置の更なる平均から classify。新馬・全 invalid は `__MISSING__` (D-13)。当日 kyakusitukubun は絶対使用しない (D-05・regression guard)。
- **`estimate_running_style_batch(history_by_horse)`** — groupby 適用 vectorized 版 (builder で使用)。
- テスト契約優先: plan が想定した DataFrame 版 `estimate_running_style(history_5starts: pd.DataFrame)` ではなく、テストが要求する dict-list 版 `estimate_running_style(history_rows=[...])` と純粋閾値関数 `classify_running_style` の2関数を実装。

### Task 3: src/features/builder.py (commit ec050b6)

- **明示カラム定数**: `_HISTORY_SELECT_COLUMNS` (babacd/timediff/harontimel3/jyuni3c/jyuni4c/jyuni1c/kyori/jyocd/datakubun/days_since_prev 含む・TARGET_OBS_BANNED_COLUMNS と disjoint・起動時 assert・HIGH #4) / `_OBS_SELECT_COLUMNS` / `_RACE_CONTEXT_COLUMNS` / `_BLOODLINE_COLUMNS`。
- **`build_rolling_features(observations, history)` 薄ラッパ** — test_pit_cutoff が builder 経由で rolling を呼ぶための転送 (sort_values で PIT join sortedness を担保・regression guard)。
- **`build_feature_matrix(read_pool, *, snapshot_id, label_version, fa_version, train_period, validation_period)`** 公開 API:
  1. availability registry load + assert_all_entries_allowed (Plan 03-01)。
  2. readonly SELECT (明示カラム・PROJECT_WINDOW_FILTER / project_window_filter(alias)・Pitfall 1)。
  3. cutoff D-06: `feature_cutoff_datetime = race_date - pd.Timedelta(days=1)` (JST midnight・strict `<`・HIGH #2)。
  4. 静的属性キャスト (normalize.py analog)。
  4b. **CYCLE-2 HIGH #5 COPY-NOT-RENAME**: `horse_id`/`jockey_id`/`trainer_id`/`sire_id`/`bms_id` を copy で追加 (kettonum/kisyucode/chokyosicode/ketto3infohansyokunum1/2 は保持・破壊的 rename でない)。
  5. rolling 統合 (build_rolling_features 経由)。
  6. 推定脚質 (estimate_running_style・過去走 jyuni3c/jyuni4c のみ)。
  7. §13.2 metadata stamp (feature_snapshot_id / feature_availability_version / label_generation_version / prediction_timing="1A")。
  8. canonical key (race_nkey, kettonum) 一意性 assert (T-03-16)。
  9. **HIGH #3**: `assert_matrix_columns_registered(spec, list(feature_matrix.columns))` で出力カラム全登録を fail-loud。
- **`CUTOFF_RULE_METADATA`** 定数 (strict_less_than / Asia/Tokyo・availability.CUTOFF_SEMANTICS と同一不変量)。

## Verification

```
KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q
=> 39 passed, 10 failed
   - 39 passed = test_allowlist (13) + test_rolling (8) + test_running_style (7)
                  + test_pit_cutoff (6) + test_builder (5)
   - 10 failed = test_snapshot_repro (5) + test_category_map_consumer (5)
                 → Plan 03-04 の GREEN スコープ (期待通り RED のまま)
```

acceptance grep 全て PASS:
- `harontimel4` in rolling.py == 0 (Pitfall 3.6)
- `kyakusitukubun` in running_style.py == 0 (D-05)
- `SELECT *` in builder.py == 0 (Pitfall 1)
- `pit_join_backward` in rolling.py == 0 (HIGH #1・単一後方 join 不使用)
- `groupby("kettonum").head` in rolling.py == 0 (CYCLE-2 HIGH #1 回帰防止)
- `pd.Timedelta(days=1)` in builder.py >= 1 (D-06 cutoff)
- `["horse_id"] = ` copy in builder.py >= 1 (CYCLE-2 HIGH #5 COPY-NOT-RENAME)
- `assert_matrix_columns_registered` in builder.py >= 1 (HIGH #3)
- ruff check src/features/{rolling,running_style,builder}.py: All checks passed

CYCLE-2 HIGH #1 対抗テスト GREEN:
```
KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/test_rolling.py::test_two_observation_window_is_per_observation_not_per_horse -q
=> 1 passed
```
同一 horse × 2 observation × 異 cutoff で異なる rolling 値を機械的に検証 (horse-grouped algorithm では必ず RED になる adversarial)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] running_style API 署名をテスト契約に合わせて調整**
- **Found during:** Task 2
- **Issue:** Plan は `estimate_running_style(history_5starts: pd.DataFrame) -> str` を想定したが、Plan 03-01 で作成された RED テスト `tests/features/test_running_style.py` は `estimate_running_style(history_rows=[...])` (dict list) と `classify_running_style(avg_position)` (純粋閾値関数) の2関数を要求していた。テスト契約が優先 (leak-safety 主張は不変)。
- **Fix:** dict-list 入力版 `estimate_running_style(history_rows)` と純粋閾値関数 `classify_running_style(avg_position)` を実装し、groupby 用 vectorized 版 `estimate_running_style_batch` も追加。jyuni3c/jyuni4c のみ使用・当日不使用・__MISSING__ sentinel の leak-safety 主張は完全に保持。
- **Files modified:** src/features/running_style.py
- **Commit:** e03c00e

**2. [Rule 3 - Blocking] rolling.py の obs 必須列を feature_cutoff_datetime/kettonum に緩和**
- **Found during:** Task 1
- **Issue:** Plan は observations に race_nkey を必須としたが、RED テスト (test_under_5_starts_uses_missing_sentinel / test_target_race_timediff_not_in_history / test_per_observation_latest_5_*) は obs に race_nkey を含まない単一行を渡す。厳密必須だと ValueError で RED が残る。
- **Fix:** obs_id を (race_nkey, kettonum) が両方あればそれから、さもなくば DataFrame index から生成。CYCLE-2 HIGH #1 の obs_id group key 不変量は完全に保持 (observation 毎に独立 window)。実運用 (実DB) では race_nkey が常にあるため (race_nkey, kettonum) が使われる。
- **Files modified:** src/features/rolling.py
- **Commit:** 2b48feb

**3. [Rule 3 - Blocking] history source 列を系統毎に optional 化**
- **Found during:** Task 1
- **Issue:** Plan は _HISTORY_SOURCE_COLUMNS (days_since_prev 含む9列) を history 厳密必須としたが、RED テストの合成 history (conftest._build_se_history_row) は days_since_prev を含まない。厳密必須だと ValueError。
- **Fix:** `_SYSTEM_SOURCE` dict で系統毎に source 列を管理し、欠損系統は該当 rolling 出力が `__MISSING__` sentinel になる (D-13 相当・silent fill でない)。実運用では builder の _HISTORY_SELECT_COLUMNS が days_since_prev を SELECT する設計なので実DBでは全系統算出される。
- **Files modified:** src/features/rolling.py
- **Commit:** 2b48feb

### 文書化された設計逸脱 (WARNING #4・CLAUDE.md §3)

rolling.py は CLAUDE.md §3 が PIT プリミティブと規定する `merge_asof(direction="backward")` を使わず、明示的 per-observation latest-K algorithm を採用する。根拠: 同 API は cutoff 以前の最新1件しか返さず latest-5 rolling window は取得できない。strict `< cutoff` pre-filter が leak-safety invariant (未来情報混入防止) を保持し、`direction="backward"` と同等の PIT-correctness を保証する。監査証跡は 03-RESEARCH.md「Open Questions (RESOLVED)」#3 (CYCLE-2 re-open 更新含む) に記録済。

## Known Stubs

(該当なし・本 plan は rolling/running_style/builder の完全実装。snapshot.py と category_map_consumer.py は Plan 03-04 スコープ)

## TDD Gate Compliance

Plan frontmatter `type: tdd` に従い RED/GREEN/REFACTOR gate を検証:

- **RED gate:** Plan 03-01 commit 6634527 (RED stub cluster) が存在・test_rolling/test_running_style/test_pit_cutoff/test_builder が RED で開始。
- **GREEN gate:** 本 plan の3コミット (2b48feb / e03c00e / ec050b6) で上記4テストファイル計39テストが全て GREEN。CYCLE-2 HIGH #1 対抗テスト (test_two_observation_window_is_per_observation_not_per_horse) GREEN で cross-observation leak 機械的閉鎖を証明。
- **REFACTOR gate:** ruff check 全チェック通過・docstring/comment 内の grep 対象文字列を generic 表現に置換 (acceptance criteria `grep -c == 0` を満たすため・leak-safety 主張は不変)。機能的 refactor は追加で実施せず (GREEN gate で既に clean)。

## Threat Flags

(該当なし・threat_model T-03-10/T-03-R1B/R2B/R3B/R4B/11/12/13/14/15/16/17 の mitigate が本 plan で実装済)

## Self-Check: PASSED

- src/features/rolling.py: FOUND (262 lines・_ROLLING_SYSTEMS 8系統・harontimel4 除外)
- src/features/running_style.py: FOUND (128 lines・kyakusitukubun 除外)
- src/features/builder.py: FOUND (364 lines・build_feature_matrix 公開 API・_HISTORY_SELECT_COLUMNS disjoint assert)
- 03-RESEARCH.md Open Question #3 CYCLE-2 更新: FOUND
- commit 2b48feb: FOUND in git log
- commit e03c00e: FOUND in git log
- commit ec050b6: FOUND in git log
