---
phase: 09-speed-figure-foundation
plan: 03
subsystem: feature-engineering (builder 統合) + model-layer (data/orchestrator snapshot parameterization)
tags: [speed-figure, builder-step5b, snapshot-id-parameterization, h1-a, h1-b, h1-c, odds-free, pit-correct, byte-reproducible, backward-compat]
requires:
  - src/features/speed_figure.py (P01・compute_speed_figure_for_history API)
  - src/features/rolling.py (P02・_SPEED_FIGURE_AXES で rolling_speed_figure_* 6 feature 生成)
  - src/features/availability.py (P02・_ROLLING_SYSTEMS_FOR_RESERVED 拡張・registry 登録済み)
  - src/config/feature_availability.yaml (P02・schema_version 0.4.0・rolling_speed_figure_* 6エントリ)
  - src/features/snapshot.py (P02 H3a・可変 window suffix coercion 拡張済み)
provides:
  - src/features/builder.py::build_feature_matrix が Step 5b で compute_speed_figure_for_history を呼出
  - history["speed_figure"] 列が builder で付与され rolling が rolling_speed_figure_* 6 feature を出力
  - src/model/data.py が snapshot_id parameterization で v1.0/speed_figure 両 snapshot をロード可能
  - src/model/orchestrator.py::train_and_predict が snapshot_id を受け取り 内部 make_X_y に伝播
  - 新 feature_snapshot_id 候補: 20260625-1a-speedfigure-v1 (v1.0 系統継承・make_model_version prefix 整合)
affects:
  - P04 (audit/可視化): builder Step 5b と registry↔Parquet parity を AST audit で完全証明
  - P05 (stop gate): snapshot_id parameterization で v1.0 baseline と speed_figure snapshot を比較可能
tech-stack:
  added: []
  patterns:
    - REVIEW H1-a: snapshot_id 必須 parameterization (arity-0 escape 構造的拒否・escape hatch 削除)
    - REVIEW H1-b: 予測経路 make_X_y bare call の grep/AST 検査 (snapshot_id= 明示伝播)
    - REVIEW H1-c: 中間処理列 obs_id の早期構築 → Step 6 再利用 → Step 6b drop (P01 API 契約充足)
    - 後方互換 A5 (Phase 5 D-03 と同一 idiom): 全新規引数はデフォルト値を持ち既存呼出元は変更不要
    - copy-not-rename (HIGH #5): _HISTORY_DB_SELECT_COLUMNS への ur.time AS time 追加で既存列破壊なし
key-files:
  created:
    - tests/features/test_speed_figure_builder_integration.py
  modified:
    - src/features/builder.py
    - src/model/data.py
    - src/model/orchestrator.py
    - tests/features/test_speed_figure.py
    - tests/features/test_builder.py
    - tests/model/test_data.py
decisions:
  - feature_snapshot_id 候補 = 20260625-1a-speedfigure-v1 (v1.0 20260620-1a-postreview-v2 系統継承・make_model_version prefix 整合・P04/P05 が消費)
  - DEFAULT_SNAPSHOT_PATH/SNAPSHOT_PATH の二重定義は後方互換 A5 (既存 import `from src.model.data import SNAPSHOT_PATH` 保護・新コードは _snapshot_paths を使用)
  - REVIEW H1-c: Step 5b 挿入の直前に feature_matrix['obs_id'] を早期構築 (既存 Step 6 L505-517 と完全同一 idiom・Step 6 は 'obs_id' in columns で skip 再利用・Step 6b で drop は不変)
  - H1-b docstring 中の 'make_X_y(' 文字列表現を回避表現に修正 (grep/AST verify が docstring の prose を拾わないよう精密化)
  - 合成 history に ur.time 列を追加 (Phase 9 必須素材・Rule 3 blocking fix・test_builder.py 3テスト対象)
metrics:
  duration: 約12分
  completed: 2026-06-25
  tasks: 3
  files_created: 1
  files_modified: 6
  tests_added: 6 (SC#1 + SC#3 + builder integration 3 + H1-b snapshot feature columns 1)
status: complete
---

# Phase 09 Plan 03: Builder 統合 + data.py/orchestrator snapshot parameterization（REVIEW H1 横断的）Summary

P01 の `compute_speed_figure_for_history` と P02 の rolling/registry 拡張を builder.py pipeline に統合（Step 5b 挿入）し・SC#1 byte-reproducible と SC#3 registry↔Parquet parity の統合テストで契約を証明した。更に REVIEW H1-a/H1-b/H1-c（横断的・最優先）として src/model/data.py と src/model/orchestrator.py の v1.0 硬結合を解除し・新 snapshot での学習を可能にする基盤を完成させた。本 PLAN 完了後・実際の feature snapshot 生成スクリプトが rolling_speed_figure_* を含む byte-reproducible な Parquet を生成でき・P04/P05 がそれを消費可能になった。

## What Was Built

### Task 1: builder.py Step 5b 挿入（commit 2a5a66c）

**`_HISTORY_DB_SELECT_COLUMNS` 拡張:**
```python
"ur.time AS time",  # Phase 9: speed_figure.py が走破タイム（0.1秒単位）を消費
```
- `time` は derived でなく raw DB カラム・`_DERIVED_HISTORY_COLUMN_NAMES` には追加しない
- `TARGET_OBS_BANNED_COLUMNS`（ninki/odds/sibababacd/dirtbabacd/tenkocd/harontimel4 等）とは disjoint（L320-322 assert で機械保証・T-09-12 mitigate）

**REVIEW H1-c: obs_id 早期構築（Step 5b の直前・新規）:**
```python
if "obs_id" not in feature_matrix.columns and len(feature_matrix) > 0:
    if "race_nkey" in feature_matrix.columns:
        feature_matrix["obs_id"] = list(zip(feature_matrix["race_nkey"], feature_matrix["kettonum"], ...))
    else:
        feature_matrix["obs_id"] = list(zip(feature_matrix.index, feature_matrix["kettonum"], ...))
```
- 旧来 obs_id は Step 6 推定脚質（L505-517）で初出していたが・Step 5b speed_figure 計算が P01 API 契約で observations が obs_id を持つことを期待するため・Step 5b の直前に早期構築
- 既存 Step 6 L505-517 と完全同一ロジック（"obs_id" in columns で skip・再利用・回帰なし）
- Step 6b（L560-564）で引き続き drop（PyArrow 直列化不能・契約不変）

**Step 5b 挿入（CR-01 merge の前）:**
```python
# --- Step 5b: speed_figure 計算（Phase 9・Beyer 型・history に speed_figure 列を付与） ---
from src.features.speed_figure import compute_speed_figure_for_history
history = compute_speed_figure_for_history(history, observations=feature_matrix)
```
- 位置: WR-01 fail-loud history 空チェックの後・Step 5 rolling 統合（CR-01 merge）の前
- copy-not-rename: history に `speed_figure` 列を追加（既存列は破壊しない・HIGH #5・T-09-10 mitigate）
- PIT 保証は speed_figure.py 側の `_pit_cutoff_prefilter`（strict `<`・availability.CUTOFF_SEMANTICS と同一不変量）で適用（builder 側で再実装しない・rolling と対称）
- available_at = race_date を付与（rolling の PIT 集約で使用）
- Step 5 rolling は history["speed_figure"] を numeric 系統として自動集約（P02 拡張済み・builder 側の rolling 変更不要）

**既存テスト修正（Rule 3 blocking fix・test_builder.py）:**
- `test_no_registered_feature_column_all_nan_end_to_end`: 合成 history に `time` 列追加（着順に反比例させる）
- `test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs`: 同上
- `test_wr06_raises_when_no_as_of_datetime`: as_of_datetime エラーより前に time チェックで止まらないよう `time` 追加
- 3テストとも実DB には time カラムが存在する（Phase 9 必須素材・Rule 3）

### Task 2: SC#1/SC#3 + builder integration テスト（commit 23b4d7b）

**`tests/features/test_speed_figure.py` 拡張:**

(a) `test_byte_reproducible_snapshot_with_speed_figure` (SC#1):
- 合成 history+observations で compute_speed_figure_for_history → build_rolling_features で feature_matrix 相当を構築
- snapshot.write_snapshot を2回（snapshot_id="test-speed-v1"/"test-speed-v2"・created_at_fixed=FIXED_REPRODUCE_TS で同一）呼出し・戻り SHA256 が完全一致することを assert
- metadata 除外 schema bytes のみ依存することを実証（CR-04・T-09-11 mitigate）

(b) `test_registry_parquet_parity_speed_figure` (SC#3):
- registry に rolling_speed_figure_* 6 feature が D-09 命名で登録されていることを検証
- `_derive_feature_columns(snapshot_id=None)` は v1.0 デフォルト（rolling_speed_figure_* 非含）を返す契約を docstring + assert で明示（T-09-13 mitigate）

**`tests/features/test_speed_figure_builder_integration.py` 新規（3テスト）:**

(c) `test_builder_step5b_adds_speed_figure_to_history`:
- compute_speed_figure_for_history → build_rolling_features の統合 GREEN
- rolling_speed_figure_last_1/mean_3/mean_5/max_5/sd_5/count_5 の6列が出力されることを assert
- rolling_speed_figure_count_5 は eligible 3行で 3（adversarial 5行が PIT 除外・D-11 実際 count）

(d) `test_builder_step5b_copy_not_rename`:
- history の既存列（time/trackcd/jyocd/kyori/kakuteijyuni/harontimel3 等）が compute_speed_figure_for_history 呼出後も保持されることを assert（HIGH #5 copy-not-rename・破壊的 rename でない）

(e) `test_builder_step5b_pit_correct` (SC#2 機能側):
- 5段階 adversarial history（target/same_day_prior/same_day_later/previous_day/future + eligible 3行）で compute_speed_figure_for_history を呼出し・結果フレームが eligible 行のみ（adversarial 5行は PIT 除外）・par_sec が eligible 3行の median=111.0 になることを assert
- speed_figure が adversarial 混入で極端な値にならないことも検証（|sf| < 1000.0）

### Task 3: data.py/orchestrator snapshot parameterization（commit d49b234・REVIEW H1-a/H1-b/H1-c）

**`src/model/data.py` 拡張（H1-a・横断的）:**

```python
# DEFAULT_* 定数を新設（v1.0 デフォルト値保持）
DEFAULT_SNAPSHOT_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.parquet"
DEFAULT_SNAPSHOT_MANIFEST_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.manifest.yaml"
DEFAULT_CATEGORY_MAP_PATH = "snapshots/category_map_20260620-1a-postreview-v2.json"
SNAPSHOT_PATH = DEFAULT_SNAPSHOT_PATH  # 後方互換 alias（既存 import 保護）

def _snapshot_paths(snapshot_id: str | None = None) -> tuple[str, str, str]:
    """snapshot_id=None は v1.0 デフォルト（A5）・指定時は snapshots/feature_matrix_{snapshot_id}.* を返す"""
    if snapshot_id is None:
        return DEFAULT_SNAPSHOT_PATH, DEFAULT_SNAPSHOT_MANIFEST_PATH, DEFAULT_CATEGORY_MAP_PATH
    return (
        f"snapshots/feature_matrix_{snapshot_id}.parquet",
        f"snapshots/feature_matrix_{snapshot_id}.manifest.yaml",
        f"snapshots/category_map_{snapshot_id}.json",
    )
```

- `_derive_feature_columns(snapshot_id=None)`: 選択 snapshot から FEATURE_COLUMNS を動的導出（モジュールレベル `FEATURE_COLUMNS: list[str] = _derive_feature_columns()` は v1.0 デフォルトのまま残存・既存 import 保護）
- `load_feature_matrix(snapshot_id=None)`: **H1-a・acceptance から arity-0 escape `or list(sig.parameters)==[]` を削除**・snapshot_id を必須パラメータ化（古い arity-0 関数を構造的に拒否・T-09-25 mitigate）
- `verify_snapshot_sha256/make_X_y/prepare_model_matrix/load_frozen_maps` も snapshot_id 引数を受け取る（後方互換デフォルト付き）

**`src/model/orchestrator.py` 拡張（H1-b・新規）:**

- `train_and_predict(...)` に `snapshot_id: str | None = None` 引数を追加（既存 `feature_snapshot_id` とは別・FEATURE_COLUMNS 選択用・provenance/model_version には無関係）
- 内部3箇所の `make_X_y(train_df/calib_df/test_df)` を `make_X_y(..., snapshot_id=snapshot_id)` に書換
- `_assert_deterministic` も snapshot_id を受け取り reproduce smoke で両 snapshot 同一契約を保証

**`tests/model/test_data.py` 拡張:**

- `test_load_from_parquet_only` を H1-a intent に修正: arity-0 escape を削除し・live DB 系引数（readonly_cur/cur/pool 等）の不在を検査（snapshot_id 受取は許可・ローカル Parquet path 選択のみのため SC#1 聖域は不変）
- `test_make_X_y_uses_snapshot_feature_columns` 新規（H1-b）: 合成 speed_figure snapshot を tmp_path に生成し・`make_X_y(frame, snapshot_id="test-speed-figure")` が返す X.columns が rolling_speed_figure_* を含み・`snapshot_id=None`（v1.0）は含まないことを assert（H1-b 静かな失敗の閉塞証明）

## REVIEW H1-a/H1-b/H1-c 解決証拠

### H1-a: load_feature_matrix が snapshot_id を必須パラメータ化（escape hatch 削除）

```
$ uv run python -c "import inspect, src.model.data as d; sig = inspect.signature(d.load_feature_matrix); params = list(sig.parameters.keys()); assert 'snapshot_id' in params, ...; print('OK')"
H1-a OK: params= ['snapshot_id']
```

acceptance_criteria の `or list(sig.parameters)==[]` 逃げ道を削除し・古い arity-0 関数が GREEN に通るのを構造的に拒否（T-09-25 mitigate）。

### H1-b: 予測経路に bare make_X_y 残存なし（grep/AST verify GREEN）

```
$ grep -nE 'make_X_y\(' src/model/orchestrator.py | grep -v 'snapshot_id=' | grep -v '^\s*#' | wc -l
0
$ uv run python -c "import inspect, src.model.orchestrator as o; sig = inspect.signature(o.train_and_predict); assert 'snapshot_id' in sig.parameters, ...; print('OK')"
H1-b OK
```

train_and_predict が snapshot_id を受け取り・内部3箇所の make_X_y が全て `snapshot_id=snapshot_id` で明示伝播（T-09-26 mitigate）。`test_make_X_y_uses_snapshot_feature_columns` で snapshot_id が異なると FEATURE_COLUMNS が実際に切替わることを実証した（静かな失敗の閉塞証明）。

### H1-c: Step 5b 直前の obs_id 早期構築

```
$ grep -n 'obs_id\|Step 5b\|Step 6\|Step 6b' src/features/builder.py | head -10
486: # --- REVIEW H1-c: obs_id 早期構築（Phase 9・Step 5b 前に feature_matrix に obs_id が必要） ---
495: if "obs_id" not in feature_matrix.columns and len(feature_matrix) > 0:  # 早期構築
509: # --- Step 5b: speed_figure 計算（Phase 9・Beyer 型・history に speed_figure 列を付与） ---
542: # --- Step 6: 推定脚質（obs_id 構築は "obs_id" in columns で skip 再利用） ---
607: # --- Step 6b: obs_id 中間処理用列の除去（CR-01 / WR-03・PyArrow 直列化不能） ---
```

Step 5b（L509）の直前に obs_id 早期構築（L486-507）・Step 6（L542）で再利用・Step 6b（L607）で drop。P01 API 契約（observations は obs_id を持つ）を充足（T-09-27 mitigate）。

## 新 feature_snapshot_id 候補（P04/P05 が依存）

```
feature_snapshot_id 候補: 20260625-1a-speedfigure-v1
  - v1.0 系統（20260620-1a-postreview-v2）を継承（同一 prefix 整合）
  - make_model_version("20260625-1a-speedfigure-v1", "lightgbm", 1)
    → "20260625-1a-speedfigure-v1-lgb-v1"（review HIGH#4 prefix 全体使用・二重 postfix 回帰防止）
  - make_model_version(..., "catboost", 1) → "20260625-1a-speedfigure-v1-cb-v1"
```

P04 は本 snapshot_id を AST audit・SC#5 ドメイン整合性検証で使用予定。P05 stop gate は `train_and_predict(snapshot_id="20260625-1a-speedfigure-v1")` を明示的に呼び・v1.0 baseline と speed_figure snapshot を同一 BT split/policy で比較する（D-13/D-14/D-15/D-16・H1-b 伝播により FEATURE_COLUMNS も切替わる）。

## SC#1/SC#3 GREEN 証拠

```
$ uv run pytest tests/features/test_speed_figure.py tests/features/test_speed_figure_builder_integration.py tests/features/test_builder.py tests/model/test_data.py -x
..................................                                       [100%]
============================= 34 passed in 10.21s ==============================
```

- SC#1 byte-reproducible: 同一 DataFrame で snapshot_id/created_at を変えても SHA256 が bit-identical（CR-04・metadata 除外 schema bytes のみ依存）
- SC#3 registry↔Parquet parity: rolling_speed_figure_* 6 feature が registry と FEATURE_COLUMNS で整合（HIGH #3・silent parity 違反回避）
- builder Step 5b が history に speed_figure を付与し・rolling が rolling_speed_figure_* 6 feature を出力（統合 GREEN）
- copy-not-rename: history/feature_matrix の既存列は保持されたまま speed_figure/rolling_speed_figure_* が追加

## 後続 PLAN が依存する契約

**P04 (audit/可視化):**
- builder.py が Step 5b で compute_speed_figure_for_history を呼ぶことを AST audit で確認
- registry と Parquet 実カラムの parity が GREEN（本 P03 で実証済み）
- SC#5 ドメイン整合性検証（同一馬連続走安定・クラス別単調性）は完成した feature_matrix が必要（本 P03 で生成可能に）

**P05 (stop gate):**
- feature_snapshot_id = 20260625-1a-speedfigure-v1（本 P03 で候補決定）
- orchestrator.train_and_predict(snapshot_id="20260625-1a-speedfigure-v1") が内部 make_X_y に伝播し FEATURE_COLUMNS が切替わる（H1-b・本 P03 で機能証明済み）
- v1.0 baseline と speed_figure snapshot を同一 BT split/policy で比較可能

## PLAN verification 全パス

| 項目 | 期待 | 実測 |
|------|------|------|
| `uv run pytest tests/features/test_speed_figure.py tests/features/test_speed_figure_builder_integration.py tests/features/test_builder.py tests/model/test_data.py -x` | GREEN | 34 passed ✓ |
| `grep -c 'compute_speed_figure_for_history' src/features/builder.py` | >= 1 | 4 ✓ |
| `grep -c 'ur.time AS time' src/features/builder.py` | >= 1 | 1 ✓ |
| H1-a: `load_feature_matrix` が `snapshot_id` を必須パラメータ化 | OK | OK ✓ |
| H1-b grep: 予測経路に bare `make_X_y(` 残存なし | == 0 | 0 ✓ |
| H1-b 機能証明: `train_and_predict` が `snapshot_id` 受け取り | OK | OK ✓ |
| H1-c: Step 5b 直前に obs_id 早期構築 → Step 6 再利用 → Step 6b drop | OK | OK ✓ |
| `time` in `TARGET_OBS_BANNED_COLUMNS` | False | False ✓（disjoint 維持） |
| SHA256 bit-identical (SC#1) | OK | OK ✓ |
| rolling_speed_figure_* 6 feature が FEATURE_COLUMNS 候補（excluded set 通過） | 6 | 6 ✓ |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 合成 history に ur.time 列を追加（test_builder.py 3テスト）**
- **Found during:** Task 1 verify
- **Issue:** 既存の合成 history は `time` 列を持たず・Step 5b 挿入後に speed_figure.py の必須列検証（`required_cols = ("time", "trackcd", "jyocd", "kyori", "race_date", "as_of_datetime")`）で `ValueError` が raise された。実 DB には time カラムが存在するが・DB を通さない unit test の合成 history には含まれていなかった。
- **Fix:** test_builder.py の3テスト（test_no_registered_feature_column_all_nan_end_to_end / test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs / test_wr06_raises_when_no_as_of_datetime）の合成 history に `time` 列を追加。値は着順に反比例（速いほど time が小さい）。実 DB の time（0.1秒単位・real）と同等の素材。test_wr06 は as_of_datetime エラーより前に time チェックで止まらないよう time 追加が必須。
- **Files modified:** tests/features/test_builder.py
- **Commit:** 2a5a66c

**2. [Rule 1 - Bug] test_load_from_parquet_only を H1-a intent に修正（arity-0 escape 削除）**
- **Found during:** Task 3 verify
- **Issue:** 既存テストは `len(sig.parameters) == 0`（live DB 引数を持たない = arity 0）を検査していたが・PLAN H1-a は明示的にこの escape hatch を削除し snapshot_id を必須パラメータ化することを求めている。H1-a parameterization 後は `len(sig.parameters) == 1`（snapshot_id）になりテストが FAIL する。
- **Fix:** テストの intent を「live DB 系引数（readonly_cur/cur/pool/conn 等）を持たない（SC#1 聖域）」に精密化。snapshot_id 受取は許可（ローカル Parquet path 選択のみで live DB 非依存のため）。forbidden_db_params & actual_db_params の積が空であることを検査。H1-a の intent（arity-0 構造的拒否）を維持しつつ SC#1 聖域（live DB 非依存）も不変。
- **Files modified:** tests/model/test_data.py
- **Commit:** d49b234

**3. [Rule 3 - Blocking] H1-b docstring 中の 'make_X_y(' 文字列表現を修正**
- **Found during:** Task 3 verify
- **Issue:** PLAN acceptance criteria の grep `grep -nE 'make_X_y\(' src/model/orchestrator.py | grep -v 'snapshot_id=' | grep -v '^\s*#' | wc -l == 0` は docstring の prose 中の ``make_X_y(`` という文字列表現も捕捉し・1 を返した。実コード呼出は全て snapshot_id= 付きだが docstring の説明文が false positive を起こしていた。
- **Fix:** docstring の表現を ``make_X_y(`` の bare call から「snapshot_id 無しの bare 呼出」に修正。実コードの挙動は不変（既に3箇所とも snapshot_id= 付き）。grep verify が 0 になることを確認。
- **Files modified:** src/model/orchestrator.py
- **Commit:** d49b234

## 自己チェック: PASSED

### 作成/修正ファイルの存在確認

- FOUND: src/features/builder.py（Task 1・Step 5b 挿入・_HISTORY_DB_SELECT_COLUMNS に ur.time AS time 追加・H1-c obs_id 早期構築）
- FOUND: src/model/data.py（Task 3・snapshot_id parameterization・DEFAULT_* 定数・_snapshot_paths helper・H1-a）
- FOUND: src/model/orchestrator.py（Task 3・train_and_predict に snapshot_id 追加・内部 make_X_y 伝播・H1-b）
- FOUND: tests/features/test_speed_figure.py（Task 2・SC#1/SC#3 テスト2件追記）
- FOUND: tests/features/test_speed_figure_builder_integration.py（Task 2・新規・3テスト）
- FOUND: tests/features/test_builder.py（Task 1・合成 history に time 列追加・3テスト）
- FOUND: tests/model/test_data.py（Task 3・H1-a 修正・H1-b テスト新規追加）

### コミットの存在確認

- FOUND: 2a5a66c（Task 1・feat・builder Step 5b + H1-c obs_id 早期構築）
- FOUND: 23b4d7b（Task 2・test・SC#1/SC#3 + builder integration テスト）
- FOUND: d49b234（Task 3・feat・data.py/orchestrator snapshot parameterization・H1-a/H1-b）

### 削除ファイル確認

- 全コミットとも `git diff --diff-filter=D --name-only HEAD~1 HEAD` で空（意図しない削除なし）

## Self-Check: PASSED

PLAN verification 全パス・34 テスト GREEN（SC#1 byte-reproducible + SC#3 parity + builder integration + H1-a/b/c）・3 コミット存在確認済み・後続 P04/P05 が依存する契約（feature_snapshot_id 候補・snapshot_id parameterization・rolling_speed_figure_* 6 feature）全て確立。
