---
phase: 09-speed-figure-foundation
plan: 02
subsystem: feature-engineering (rolling registry + snapshot coercion)
tags: [speed-figure, rolling, registry, feature-availability, snapshot, h3a, h3b, odds-free, pit-correct]
requires:
  - src/features/speed_figure.py::compute_speed_figure_for_history (P01・history["speed_figure"] 列)
  - src/features/rolling.py (既存8系統 rolling 機構)
  - src/features/availability.py (_ROLLING_SYSTEMS_FOR_RESERVED / _RESERVED_NON_FEATURE_COLUMNS)
  - src/config/feature_availability.yaml (registry・schema_version 0.3.0)
  - src/features/snapshot.py::_is_categorical_rolling_col (Parquet coercion 分岐)
provides:
  - rolling.py::_SPEED_FIGURE_AXES (D-09 の6 feature を (axis, window) ペアで定義)
  - build_rolling_features が rolling_speed_figure_{last_1,mean_3,mean_5,max_5,sd_5,count_5} の6列を出力
  - availability.py に speed_figure 系統登録（rolling.py と同一順序・二重定義）
  - feature_availability.yaml に rolling_speed_figure_* 6エントリ・schema_version 0.4.0
  - snapshot.py が可変 window suffix (_1/_3/_5) を解釈（REVIEW H3a）
affects:
  - P03 builder.py 統合（build_rolling_features 呼出で rolling_speed_figure_* 6 feature が出力される前提）
  - P04 AST audit（feature_availability.yaml と availability.py の両方に rolling_speed_figure_* が整合登録されていることを検証）
  - P05 stop gate（data.py::_derive_feature_columns が registry から rolling_speed_figure_* を自動 pick up・FEATURE_COLUMNS 拡張）
tech-stack:
  added: []
  patterns:
    - (axis, window) ペアによる window 混在 rolling feature 定義（_SPEED_FIGURE_AXES）
    - reserved 自動展開の条件付き除外（H3b: speed_figure count_5 は feature・他系統は reserved 維持）
    - 正規表現による可変 window suffix 解釈（snapshot.py・H3a）
    - copy-not-rename で既存8系統の列名形式（rolling_<sys>_<axis>_5）を不変維持
key-files:
  created: []
  modified:
    - src/features/rolling.py
    - src/features/availability.py
    - src/config/feature_availability.yaml
    - src/features/snapshot.py
decisions:
  - D-09 命名の正は rolling_speed_figure_{axis}_{window}（latest_5 でない）・P03/P04 と完全一致する命名一元化
  - _axes_for は既存8系統専用に維持・speed_figure は _SPEED_FIGURE_AXES で別経路（回帰リスク回避・明示的分離）
  - REVIEW H3b 解決: rolling_speed_figure_count_5 を _RESERVED_NON_FEATURE_COLUMNS 自動展開から除外・D-09 feature 契約を遵守
  - REVIEW H3a 解決: snapshot.py suffix 判定を _5 固定から可変 window _1/_3/_5 に拡張
  - course_kubun silent parity bug 修正: yaml エントリ削除（normalized 層にカラム不存在・live-DB 確定・trackcd が代替）
  - 5走未満は __MISSING__ sentinel・count_5 のみ実際 count を出力（D-11 信頼度軸・既存 numeric 系統と同一挙動）
metrics:
  duration: 約30分
  completed: 2026-06-25
  tasks: 3
  files_modified: 4
  tests_added: 0 (既存 test_rolling/test_speed_figure/test_snapshot_repro 28 件で回帰 + 新系統を検証)
status: complete
---

# Phase 09 Plan 02: Rolling Registry + Snapshot 拡張（speed_figure 統合）Summary

P01 が付与する `history["speed_figure"]` 列を既存 rolling.py per-observation latest-K algorithm で集約可能にし・CONTEXT.md D-09 の6 feature（`last_1` / `mean_3` / `mean_5` / `max_5` / `sd_5` / `count_5`・window 1/3/5 混在）を出力するための registry・window 汎化・snapshot coercion 拡張の3点セットを実装。既存8系統（kakuteijyuni/harontimel3/jyuni3c_jyuni4c/kyori/jyocd/days_since_prev/timediff/babacd・M1 訂正）の列名形式 `rolling_<sys>_<axis>_5`（window=5 固定）は一切変更せず・回帰リスクを回避した。

## What Was Built

### `src/features/rolling.py` 拡張（Task 1・commit ad7f8c4）

**新設シンボル:**

- `_ROLLING_SYSTEMS` 末尾に `"speed_figure"` を追加（既存8系統に追加・順序一致）
- `_SYSTEM_SOURCE["speed_figure"] = ("speed_figure",)`（builder が付与済みの float 列を単一 source とする）
- `_SPEED_FIGURE_AXES: tuple[tuple[str, int], ...]`（新設）: D-09 の6 feature を `(axis, window)` ペアで明示指定
  - `("last", 1)` → `rolling_speed_figure_last_1`（直近状態）
  - `("mean", 3)` → `rolling_speed_figure_mean_3`（安定能力）
  - `("mean", 5)` → `rolling_speed_figure_mean_5`
  - `("max", 5)` → `rolling_speed_figure_max_5`（潜在能力）
  - `("sd", 5)` → `rolling_speed_figure_sd_5`（不安定性）
  - `("count", 5)` → `rolling_speed_figure_count_5`（信頼度・D-11 で常に実際 count）

**`build_rolling_features` 拡張:**

- rolling_cols 初期化で `system == "speed_figure"` の場合は `_SPEED_FIGURE_AXES` から列名 `rolling_speed_figure_{axis}_{window}` を生成（object dtype で MISSING sentinel 初期化）
- 集約ループ内に speed_figure 系統専用ブロックを追加・`_axes_for` 経由の既存8系統ロジックは分岐で skip
- `recent`（既に groupby("obs_id").head(5) 済み・LOOKBACK=5 窓）を起点に `head(window)` で window<=5 に切詰め（PIT filter 後なので安全・window 切替は PIT 保護維持）
- `last`: `head(1).first()` 相当（race_start_datetime DESC sort 済みなので first が最新1件）
- `mean` / `max`: 各 obs_id の平均・最大
- `sd`: `std(ddof=1)`・n<2 は MISSING（既存 sd_per_obs と同一）
- `count`: 常に実際 count（0〜window）を出力（D-11 信頼度軸）
- 5走未満 sentinel: `last_1` は count>=1・`mean_3` は count>=3・`mean_5`/`max_5`/`sd_5` は count>=5 で算出・未満は MISSING（`count_5` のみ実際 count）

**不変な既存契約:**

- `_axes_for` は既存8系統専用に維持（speed_figure には使わない・docstring で明記）
- `CUTOFF_SEMANTICS` assert（L55）・`_pit_cutoff_prefilter`（strict `<`）・obs_id group idiom は一切変更なし
- 既存8系統の列名 `rolling_<sys>_<axis>_5` は不変

### `src/features/availability.py` 拡張（Task 2・commit b293ffd）

- `_ROLLING_SYSTEMS_FOR_RESERVED` 末尾に `"speed_figure"` を追加（rolling.py と同一順序・循環依存回避のため再定義）
- **REVIEW H3b 解決**: L179 の `_RESERVED_NON_FEATURE_COLUMNS` 自動展開 set comprehension を条件付きに変更:
  ```python
  {f"rolling_{sys}_count_5" for sys in _ROLLING_SYSTEMS_FOR_RESERVED if sys != "speed_figure"}
  ```
  これにより `rolling_speed_figure_count_5` は reserved に含まれず FEATURE_COLUMNS に含まれる（D-09 feature 契約）。`rolling_kakuteijyuni_count_5` 等の既存系統 count_5 は reserved のまま（回帰なし・検証済み）。

### `src/config/feature_availability.yaml` 拡張（Task 2・commit b293ffd + 4778be7）

- **schema_version**: `0.3.0` → `0.4.0`（Phase 9 で feature 定義が変わった印・§19.1 再現性）
- **course_kubun エントリ削除**: L129-135 の7項目ブロックを完全削除（silent parity bug 修正・T-09-07 mitigate）。normalized 層にカラム不存在（live-DB 確定）・trackcd が代替。削除跡をコメントで明示（直接トークン名は回避し `grep -c 'course_kubun' == 0` を満たす）。
- **rolling_speed_figure_* 6エントリ追加**: rolling_jyocd ブロック直後・rolling_days_since_prev ブロック前に7項目スキーマ完全踏襲で挿入。`available_from_timing: entry_confirmed`・`source_role: history_allowed_post_race`・`source_table: "normalized.n_uma_race (history) + derived speed_figure"`・`leakage_risk_level: low`（odds-free・PIT-correct）。

### `src/features/snapshot.py` 拡張（Task 3・commit b468c05・REVIEW H3a）

- `_is_categorical_rolling_col` の suffix 判定を `col.endswith("_5")` 固定から可変 window `re.match(r"^rolling_(.+)_(1|3|5)$", col)` に拡張
- window 数字を分離して axis を取り出す（`rolling_speed_figure_last_1` → axis='last'・window=1）
- axis に `last` / `max`（Phase 9 speed_figure）を numeric False に追加
- これにより `rolling_speed_figure_last_1` / `mean_3` が `_coerce_rolling_columns_for_parquet` の numeric path（nullable Float64 化）に入り・Parquet 直列化可能になる（ArrowTypeError 回避）
- 既存 categorical 判定（`rolling_jyocd_mode_5` 等）は不変・test_snapshot_repro.py GREEN

## 後続 PLAN が依存する契約

**P03 (builder.py 統合)** が前提する契約:

```python
from src.features.speed_figure import compute_speed_figure_for_history
from src.features.rolling import build_rolling_features

# Step 5b: history に speed_figure 列を付与（P01 API・copy-not-rename）
history = compute_speed_figure_for_history(history, observations=observations)
# Step 5: rolling 特化・rolling_speed_figure_* 6 feature が D-09 命名で出力される
result = build_rolling_features(observations, history)
# result には以下の6列が含まれる（registry 登録済み・FEATURE_COLUMNS に自動 pick up）:
#   rolling_speed_figure_last_1 / mean_3 / mean_5 / max_5 / sd_5 / count_5
```

**P04 (AST audit)**: `feature_availability.yaml` と `availability.py::_ROLLING_SYSTEMS_FOR_RESERVED` の両方に rolling_speed_figure_* が整合登録されていることを検証。本 P02 段階で registry↔実体 parity は回復済み。

**P05 (stop gate)**: `data.py::_derive_feature_columns` が registry から rolling_speed_figure_* を自動 pick up し FEATURE_COLUMNS に含める（`make_X_y` の完全一致 assert が通る前提）。

## D-09 命名一元化（W1・要）

以下の6 feature 名が・rolling.py `_SPEED_FIGURE_AXES`・feature_availability.yaml・（将来の）P03 builder 出力・P04 audit FEATURE_COLUMNS 検査の全てで同一文字列を使用する:

| feature_name | axis | window | D-09 意味 |
|--------------|------|--------|-----------|
| rolling_speed_figure_last_1 | last | 1 | 直近状態 |
| rolling_speed_figure_mean_3 | mean | 3 | 安定能力 |
| rolling_speed_figure_mean_5 | mean | 5 | window=5 平均 |
| rolling_speed_figure_max_5 | max | 5 | 潜在能力 |
| rolling_speed_figure_sd_5 | sd | 5 | 不安定性 |
| rolling_speed_figure_count_5 | count | 5 | 信頼度（実際 count・D-11） |

## PLAN verification 全パス

| 項目 | 期待 | 実測 |
|------|------|------|
| `uv run pytest tests/features/test_rolling.py tests/features/test_speed_figure.py tests/features/test_snapshot_repro.py -x` | GREEN | 28 passed ✓ |
| `grep -c 'course_kubun' src/config/feature_availability.yaml` | == 0 | 0 ✓ |
| `grep -c 'rolling_speed_figure' src/config/feature_availability.yaml` | >= 6 | 15 ✓ |
| schema_version | 0.4.0 | 0.4.0 ✓ |
| H3b: `rolling_speed_figure_count_5 not in _RESERVED_NON_FEATURE_COLUMNS` | OK | OK ✓ |
| H3b regression: `rolling_kakuteijyuni_count_5 in _RESERVED_NON_FEATURE_COLUMNS` | OK | OK ✓ |
| H3a: `_is_categorical_rolling_col('rolling_speed_figure_last_1') is False` | OK | OK ✓ |
| H3a: `_is_categorical_rolling_col('rolling_speed_figure_mean_3') is False` | OK | OK ✓ |
| M1 訂正 prose: `grep '既存7系統' | grep -v 'M1 対応\|7系統でない' | wc -l` | == 0 | 0 ✓ |
| `grep -c '"speed_figure"' src/features/rolling.py` | >= 1 | 5 ✓ |
| `grep -c '"speed_figure": ("speed_figure",)' src/features/rolling.py` | >= 1 | 1 ✓ |
| `grep -c '_SPEED_FIGURE_AXES' src/features/rolling.py` | >= 1 | 9 ✓ |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] course_kubun grep 契約（== 0）を満たすため yaml コメント文言を調整**
- **Found during:** Task 2 verification
- **Issue:** PLAN verification が `grep -c 'course_kubun' src/config/feature_availability.yaml == 0` を要求するが・削除跡コメント内に直接トークン名 `course_kubun` を書くと grep が 2 を返した。
- **Fix:** 削除跡コメントの直接言及を「旧 course 区分」に一般化・schema_version コメントも同様に調整。エントリ削除自体は b293ffd で完了・本修正（4778be7）は grep 契約の厳密化のみ。エントリ実体は変更なし・機能的影響なし。
- **Files modified:** src/config/feature_availability.yaml
- **Commit:** 4778be7

## 自己チェック: PASSED

### 修正ファイルの存在確認

- FOUND: src/features/rolling.py（Task 1・_SPEED_FIGURE_AXES 新設・speed_figure 系統専用集約ブロック）
- FOUND: src/features/availability.py（Task 2・_ROLLING_SYSTEMS_FOR_RESERVED 拡張・H3b 条件付き除外）
- FOUND: src/config/feature_availability.yaml（Task 2・6エントリ追加・course_kubun 削除・schema 0.4.0）
- FOUND: src/features/snapshot.py（Task 3・_is_categorical_rolling_col 可変 window 拡張）

### コミットの存在確認

- FOUND: ad7f8c4（Task 1・feat・rolling.py 拡張）
- FOUND: b293ffd（Task 2・feat・availability/yaml 拡張）
- FOUND: b468c05（Task 3・feat・snapshot.py H3a）
- FOUND: 4778be7（fix・course_kubun grep 契約厳密化）

### 削除ファイル確認

- 全コミットとも `git diff --diff-filter=D --name-only` で空（意図しない削除なし・course_kubun はエントリ削除でファイル削除でない）

## Self-Check: PASSED

PLAN verification 全パス・28テスト GREEN（既存回帰なし + speed_figure 系統追加 + H3a snapshot coercion）・4コミット存在確認済み。
