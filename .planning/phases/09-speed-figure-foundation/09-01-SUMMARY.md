---
phase: 09-speed-figure-foundation
plan: 01
subsystem: feature-engineering (speed figure)
tags: [speed-figure, beyer, par-time, variant, pit-correct, odds-free, byte-reproducible]
requires:
  - src/features/availability.py (CUTOFF_SEMANTICS)
  - src/features/rolling.py (per-observation latest-K idiom / obs_id expand)
provides:
  - src/features/speed_figure.py::compute_speed_figure_for_history (公開 API)
  - history["speed_figure"] 列（P02 rolling 拡張が前提とする契約）
  - history["available_at"] 列（rolling の PIT 集約で使用）
affects:
  - P02 rolling.py 拡張（_ROLLING_SYSTEMS に "speed_figure" 追加で numeric path 自動適用）
  - P03 builder.py 統合（Step 5b で compute_speed_figure_for_history を呼出）
  - P04 availability/yaml 拡張 + AST audit（SC#4 SAFE-01 完全証明）
  - P05 stop gate（v1.0 baseline vs +speed_figure 比較）
tech-stack:
  added: []
  patterns:
    - per-observation PIT cutoff (rolling.py L104-116 と対称な _pit_cutoff_prefilter)
    - obs_id groupby (CYCLE-2 HIGH #1 cross-obs leak 回避 idiom 対称適用)
    - leave-one-race-out 一次近似 (group_median - (self_residual - group_median)/(n-1))
    - copy-not-rename (入力 history 列を破壊せず監査/派生列を追加)
    - fail-loud (空 history は RuntimeError・WR-01 踏襲)
key-files:
  created:
    - src/features/speed_figure.py
    - tests/features/test_speed_figure.py
    - tests/features/test_speed_figure_pit.py
  modified:
    - tests/features/conftest.py
decisions:
  - POINTS_PER_SECOND_BY_DISTANCE_M は Beyer 文献[ASSUMED]概算値(1000:16.5..3200:5.0)を採用・SC#5 ドメイン整合性で微調整可
  - leave-one-race-out variant は一次近似(A3)を採用・厳密ループでなく docstring/test で精度上限を明示
  - _MIN_SAMPLES_PAR_JYO_TRACK_KYORI=30・_MIN_SAMPLES_PAR_TRACK_KYORI=30・_MIN_SAMPLES_VARIANT_GROUP=10 (planner discretion)
  - REVIEW H4: par group = obs_id + jyocd×trackcd×kyori・variant group = obs_id + source_race_date×jyocd×surface (obs_id 必須・cross-obs leak 構造的不能)
  - 禁止トークン(odds/ninki/fukuodds/ninkij/tansyouodds)は docstring 含め実行コード非コメントから排除・P04 AST audit で完全証明予定
metrics:
  duration: 約35分
  completed: 2026-06-25
  tasks: 2
  files_created: 3
  files_modified: 1
  tests_added: 13
status: complete
---

# Phase 09 Plan 01: Speed Figure Foundation（speed_figure.py 新規実装）Summary

Beyer 型スピード指数（par/variant/speed_figure）を odds-free・PIT-correct・byte-reproducible に算出する新 module `src/features/speed_figure.py` と・SC#1 単体 + SC#2 adversarial 計13テストを実装。後続 P02-P05 が依存する能力特徴量の新主軸を確立。

## What Was Built

### `src/features/speed_figure.py`（新規・公開 API + 内部 helper）

**公開 API:**

```python
def compute_speed_figure_for_history(
    history: pd.DataFrame,
    observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """history 全行に speed_figure / available_at / 監査列を付与して返す(copy-not-rename)。"""
```

戻り値の追加列:
- `speed_figure` (float・丸めない・D-05): `(par_sec - time_sec + variant_sec) × points_per_second(kyori)`
- `available_at` (datetime): `pd.to_datetime(race_date)`・rolling の PIT 集約で使用
- 監査列（D-07）: `par_sec` / `variant_sec` / `speed_residual_sec` = `time_sec - par_sec` / `sample_count` / `fallback_level`

**モジュール top-level 不変量:**

```python
from src.features.availability import CUTOFF_SEMANTICS
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"
```

`rolling.py` L55 と対称な単一不変量・strict `<` filter を `availability.CUTOFF_SEMANTICS["pit_filter"]` と同一の真の源に固定。

**helper / 算出関数:**

| 関数 | 役割 | 対称 analog |
|------|------|-------------|
| `_pit_cutoff_prefilter(expanded)` | strict `<` filter helper・adversarial test が monkeypatch で `<=` 版に差替可能 | `rolling.py::L104-116` |
| `_time_to_seconds` / `_time_to_seconds_series` | 0.1秒単位(decisecond) → 秒換算・`time<=0` は NaN（完走馬フィルタ・live-DB 4882件除外） | RESEARCH Code Examples |
| `_derive_surface(trackcd)` | trackcd 10-22=turf/23-25=dirt/51-59=obstacle・他=unknown | `builder.py::_construct_derived_columns` と同一閾値 |
| `get_points_per_second(kyori)` | 線形補間・端点クランプ・決定論的 | RESEARCH Code Examples |
| `_compute_pit_par(expanded_filtered)` | REVIEW H4: par group = `obs_id + jyocd×trackcd×kyori`・fallback 階層(jyocd_trackcd_kyori→trackcd_kyori→all_day)・D-07 監査列付与 | `rolling.py::L236-265` obs_id expand + groupby idiom 対称 |
| `_compute_leave_one_out_variant(expanded_with_par)` | variant group = `obs_id + source_race_date×jyocd×surface`・一次近似 `group_median - (self_residual - group_median)/(n-1)` (A3)・`< _MIN_SAMPLES_VARIANT_GROUP` は obs_id all-history fallback | RESEARCH Pattern 2 |
| `compute_speed_figure(time_sec, par_sec, variant_sec, kyori)` | float・丸めない・D-05 | RESEARCH Code Examples |

### `POINTS_PER_SECOND_BY_DISTANCE_M`（採用値・Beyer 文献[ASSUMED]）

| 距離(m) | pps | 由来 |
|---------|-----|------|
| 1000 | 16.5 | 5f 相当（短距離・1秒の重み最大） |
| 1200 | 13.2 | 6f 相当 |
| 1400 | 11.0 | 7f 相当 |
| 1600 | 10.0 | 8f 相当（1/5秒=2 → 1秒=10.0） |
| 1800 | 8.8 | 9f 相当 |
| 2000 | 8.0 | 10f 相当 |
| 2400 | 6.6 | 12f 相当（長距離・1秒の重み最小） |
| 3000 | 5.3 | 1.5mile+ 相当 |
| 3200 | 5.0 | 長距離障害含む |

[ASSUMED] Beyer 文献（PaceAdvantage Forum / America's Best Racing）の概算値。canonical feature は float（D-05）のため絶対スケールより相対的順序が重要・SC#5 ドメイン整合性検証後に微調整可。

### Fallback 階層サンプル数下限（planner discretion・live-DB 精査前の初期値）

- `_MIN_SAMPLES_PAR_JYO_TRACK_KYORI = 30`（最細粒度 jyocd×trackcd×kyori のサンプル下限）
- `_MIN_SAMPLES_PAR_TRACK_KYORI = 30`（第2階層 trackcd×kyori）
- `_MIN_SAMPLES_VARIANT_GROUP = 10`（variant group source_race_date×jyocd×surface）
- `_TRIM_PROPORTION = 0.1`（scipy.stats.trim_mean 両端カット・現在未使用・将来 robust 化で利用予定）

※ 実データでの group size 分布確認は P02/P03 builder 統合時（live-DB）に実施予定。現時点では planner discretion の初期値。

## SC#1/SC#2 GREEN 証拠

### SC#1 byte-reproducible（13 テスト GREEN）

```
tests/features/test_speed_figure.py ..........  [76%]
tests/features/test_speed_figure_pit.py ...     [100%]
============================== 13 passed in 0.18s ==============================
```

- `test_byte_reproducible_speed_figure`: 同一 history+observations で2回呼出し・`np.array_equal` で speed_figure/par_sec/variant_sec 列が bit-identical を実証（決定論的 median・seed 不要）。

### SC#2 PIT-correct（adversarial GREEN・false-pass 回避実証）

- `test_lookahead_injection_detected_and_fails`（5段階鋳型）:
  - (2) guard 有効: eligible 3行(110,111,112) の median par_sec = **111.0**
  - (5) guard monkeypatch無効化(`<=`): previous_day(time=9960ds → 996.0秒)混入で par_sec が **111.0 から変化**（false-pass 回避の機械証明）
- `test_cross_observation_pit_no_leak`（REVIEW H4）:
  - 保護あり: O_early の `sample_count = 1`（base 行のみ・obs_id 独立 group）
  - obs_id groupby外し hack: O_early の `sample_count = 3`（O_late の base+intervention が同一 group に混入）
  - H4 per-obs invariant が guard でなく**集約キー仕様(obs_id 必須)**由来であることを機械証明（T-09-28 mitigate）

### `test_docstring_cross_reference`（T-08-04）

モジュール docstring とテスト docstring に `"SC#2 adversarial"` + `"cross-reference: tests/features/test_speed_figure.py"` が含まれることを assert（機能テストと adversarial の棲み分け明示）。

## 後続 PLAN が依存する公開 API（契約）

**P02 (rolling.py 拡張)** が前提とする契約:

```python
from src.features.speed_figure import compute_speed_figure_for_history
history = compute_speed_figure_for_history(history, observations=observations)
# history["speed_figure"] 列が各過去走行に付与される・available_at=race_date
# rolling.py は _ROLLING_SYSTEMS に "speed_figure" を1行追加するだけで numeric path 自動適用:
#   rolling_speed_figure_mean_5 / _latest_5 / _sd_5 / _count_5
```

**P03 (builder.py 統合)**: Step 5 rolling の直後（Step 5b）に `compute_speed_figure_for_history` を呼出し・history に `speed_figure` 列を copy-not-rename で追加。`observations` を渡すのが production 経路（`observations=None` は unit test 専用・docstring 明記）。

**P04 (AST audit)**: `src/features/speed_figure.py` を AST audit 対象とし・識別子・文字列リテラル・実行コードに市場情報 proxy トークンが現れないことを完全証明（SC#4 SAFE-01）。本 P01 段階では `grep -v '^#' | grep -cE ...` で **0件** を確認済み。

**P05 (stop gate)**: `evaluator.py` + `segment_eval.py` の binning 契約を固定再利用し・v1.0 baseline と +speed_figure 単体モデルを同一 BT split/policy で比較（D-13/D-14/D-15/D-16）。

## PLAN verification grep 全パス

| 項目 | 期待 | 実測 |
|------|------|------|
| `grep -c 'def compute_speed_figure_for_history'` | 1 | 1 ✓ |
| `grep -c 'def _pit_cutoff_prefilter'` | 1 | 1 ✓ |
| `grep -c 'strict_less_than'` | >=1 | 2 ✓ |
| `grep -v '^#' \| grep -cE 'odds\|ninki\|fukuodds\|ninkij\|tansyouodds'` | 0 | 0 ✓ |
| `uv run pytest tests/features/test_speed_figure*.py -x` | GREEN | 13 passed ✓ |

## 自己チェック: PASSED

### 作成ファイルの存在確認

- FOUND: src/features/speed_figure.py (Task 1)
- FOUND: tests/features/test_speed_figure.py (Task 2)
- FOUND: tests/features/test_speed_figure_pit.py (Task 2)
- 拡張: tests/features/conftest.py (Task 2・_build_speed_figure_history_rows 追加)

### コミットの存在確認

- FOUND: e2fca6a (Task 1・feat)
- FOUND: dabba18 (Task 2・test)

### 削除ファイル確認

- 両コミットとも `git diff --diff-filter=D --name-only` で空（意図しない削除なし）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] par/variant 算出における median の性質上・H4 cross-obs leak の検出方法を par_sec 変化 → sample_count 変化 に調整**
- **Found during:** Task 2 `test_cross_observation_pit_no_leak` 実装
- **Issue:** PLAN は「obs_id groupby 外し hack で earlier obs の par が変化することで false-pass 回避を機械証明」を期待していたが・3件(eligible 1+1+intervention 1)の median は中央値になるため・O_early の par_sec が 110.0 のまま変化しないケースがあった。
- **Fix:** sample_count の変化（保護あり=1・hack あり=3）で cross-observation leak を機械検出するよう test を調整。H4 invariant が集約キー仕様(obs_id 必須)由来であることの実証力は維持（sample_count が observation 毎でなく全体サイズになることが漏洩の直接証拠）。
- **Files modified:** tests/features/test_speed_figure_pit.py
- **Commit:** dabba18

**2. [Rule 1 - Bug] test_par_pit_expanding で target 行の存在 assert を削除**
- **Found during:** Task 2 実装
- **Issue:** PIT prefilter(strict <) で target 当日行は結果フレームから除外される（par 算出への混入が構造的不能）が・初期テストは `result["row_label"]=="target"` の存在を assert していた。
- **Fix:** 「結果フレームは eligible 行のみ含む」ことを確認するよう修正。これは PIT 保護の正常動作（adversarial 5行が除外される）を示すもので・SC#2 の機能テスト契約と整合。
- **Files modified:** tests/features/test_speed_figure.py
- **Commit:** dabba18

**3. [Rule 1 - Bug] docstring odds-free 文書化と禁止トークン grep == 0 の両立**
- **Found during:** Task 1 verification
- **Issue:** PLAN verification `grep -v '^#' | grep -cE ... == 0` は docstring 行（`"""` 内）も捕捉する。docstring で「odds/ninki を使わない」と直接トークン名を書くと grep が 0 にならない。
- **Fix:** docstring の文言を「市場情報 proxy（オッズ/人気/過去オッズ系）」のように一般化し・直接の禁止トークン名（`odds`/`ninki`/`fukuodds`/`ninkij`/`tansyouodds`）を docstring 含む非コメント行から排除。これで `grep -v '^#' | grep -cE ... == 0` を達成。P04 が AST audit で完全証明予定（識別子・属性参照・文字列リテラルの区別無く全域スキャン）。
- **Files modified:** src/features/speed_figure.py
- **Commit:** e2fca6a

## 既知制限・次フェーズへの引継ぎ事項

- **leave-one-race-out variant は一次近似（A3）**: 厳密ループでなく・`group_median - (self_residual - group_median)/(n-1)` の一次近似を採用。docstring で「avg 215完走馬/group で自レース寄与 < 1%」と精度上限を明示。極小 group (n < 10) は obs_id all-history fallback。
- **`_TRIM_PROPORTION = 0.1` は現時点で未使用**: robust 統計量(trim_mean)の将来利用に備えた予約定数。現状は pandas 組込 `.median()` のみ使用（決定論的・byte-reproducible）。
- **`observations=None` 経路は unit test 専用**: production では builder が observations を渡す。docstring に明記済み・P03 で builder 統合時に production 経路を確立。
- **fallback サンプル数下限(30/30/10)は planner discretion 初期値**: P02/P03 で live-DB の group size 分布を確認後に微調整可能性。現時点では unit test で機能している。
- **POINTS_PER_SECOND_BY_DISTANCE_M は [ASSUMED] Beyer 概算値**: SC#5 ドメイン整合性検証（同一馬連続走安定・クラス別単調性）後に微調整可。canonical feature は float のため絶対スケールでなく相対的順序が重要。

## Self-Check: PASSED

作成ファイル存在・コミット存在・削除0・PLAN grep 全パス・13テストGREEN を確認。
