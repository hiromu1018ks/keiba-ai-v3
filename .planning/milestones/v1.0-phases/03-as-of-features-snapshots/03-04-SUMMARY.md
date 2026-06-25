---
phase: 03-as-of-features-snapshots
plan: 04
subsystem: features/snapshot
tags: [phase-03, features, tdd, green, snapshot, byte-reproducible, parquet, category-map, cli, live-db-integration]
requires: [03-03]
provides:
  - "byte-reproducible versioned Parquet snapshot writer (src/features/snapshot.py)"
  - "frozen category map consumer with train-window fit + __UNSEEN__ + raw ID drop (src/features/category_map_consumer.py)"
  - "end-to-end CLI entrypoint scripts/run_feature_build.py"
  - "snapshots/.gitignore (Parquet/joblib binary excluded per §19.1)"
affects:
  - "src/features/builder.py (BUG A/B/A' + days_since_prev scope + bloodline type-cast)"
  - "src/features/availability.py (BUG B: _RAW_ID_KEPT_COLUMNS allowlist)"
  - "src/features/snapshot.py (rolling object→Float64 Parquet coercion)"
  - "tests/features/test_builder.py (babacd/timediff assertion relaxed to real schema)"
tech-stack:
  added: []
  patterns:
    - "COPY-NOT-RENAME ID aliasing (HIGH #5): abstract alias copy + raw original retained"
    - "derived column construction in pandas (race_nkey from composite key, as_of_datetime, days_since_prev)"
    - "snapshot-boundary object→Float64 coercion for sentinel-mixed rolling columns"
key-files:
  created:
    - src/features/snapshot.py
    - src/features/category_map_consumer.py
    - scripts/run_feature_build.py
    - snapshots/.gitignore
  modified:
    - src/features/builder.py
    - src/features/availability.py
    - src/features/snapshot.py
    - tests/features/test_builder.py
decisions:
  - "race_nkey は DB カラムでなく予約済み canonical key。make_race_nkey(year,jyocd,kaiji,nichiji,racenum) で pandas 構築（obs/history 同一構成）"
  - "normalized 層に babacd/timediff/datakubun は存在しない。これら rolling 系統は D-13 sentinel (__MISSING__→NaN) で安全に fallback"
  - "COPY-NOT-RENAME の raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2) は意図的保持。_RAW_ID_KEPT_COLUMNS で明示許可（banned source は防御的 assert で排除）"
  - "rolling object 列は snapshot 境界でのみ Float64 化（rolling 内部 D-13 契約は不変）"
metrics:
  duration: ~25min (continuation agent)
  completed: 2026-06-19
  tasks: 3 implementation + 1 checkpoint-resolution
  files: 8 (4 created, 4 modified)
  unit_tests: 49 passed (KEIBA_SKIP_DB_TESTS=1)
  live_rows: 554267
  live_features: 63
  sha256: 19f11c3113319ae6b35cfde371ee2f69063e651bf37f920b599b65d6fa2673a0
---

# Phase 03 Plan 04: Byte-reproducible Parquet snapshot + frozen category map + CLI Summary

Phase 3 の最終成果物 — feature matrix を不変 versioned Parquet に書出し、frozen category map (joblib) と manifest YAML を同 snapshot_id で紐付け、Phase 4 モデルが stamped Parquet **のみ**から学習できる状態を届ける CLI エントリポイント。本 plan は autonomous:false で live-DB snapshot build の checkpoint で一時停止していたが、orchestrator がユーザ認可の上 live build を実行し、Phase 3 builder/registry (Plan 03-03) の 2 つの実統合バグ（+ 3 つの連鎖的 blocking issue）を発見。本 continuation agent が全て修正し live build exit 0 を達成。

## What Was Built

### 1. `src/features/snapshot.py` — byte-reproducible Parquet snapshot writer (Task 1)
- PyArrow 決定論的書込: `use_dictionary=False` / `compression="zstd"` / `write_statistics=True` / `row_group_size=100_000` (行数単位・REVIEWS MEDIUM #10) / canonical sort `_SNAPSHOT_SORT_KEYS = ("race_date","jyocd","racenum","kettonum")`
- §12.4 metadata 9 keys を schema metadata に埋込 (`dataset_version` / `feature_snapshot_id` / `label_version` / `prediction_timing` / `feature_cutoff_rule` / `train_period` / `validation_period` / `created_at` / `feature_availability_version`)
- REVIEWS HIGH #6: SHA256 scope = Parquet bytes のみ。`created_at` は schema metadata に直接埋め込まず deterministic sentinel `_DETERMINISTIC_CREATED_AT` で埋める（キー存在要件は満たす）。実値は manifest 側 `created_at_fixed` で別管理
- 空入力拒否 (CR-04(a)): `RuntimeError`
- `write_manifest()` で manifest YAML に sha256 / byte_size / row_count / feature_count / §12.4 metadata / `category_map_artifact` / `byte_reproducible_scope="parquet_bytes_only"` を記録

### 2. `src/features/category_map_consumer.py` — frozen category map consumer (Task 2)
- `FrozenCategoryMap` wrapper: dict-style (`m["__UNSEEN__"]`) + attribute-style (`m.codes[UNSEEN]`) 両対応。joblib 安全 (`__getstate__`/`__setstate__`)
- `build_frozen_category_maps(feature_matrix)`: train 窓 (D-09: 2016-07-01/2023-12-31) のみで fit。`train_mask = race_date.between(...)` で val/test 行を fit に絶対渡さない (Pitfall 3.4)
- `apply_frozen_category_maps`: 再 fit 禁止・`__UNSEEN__` / `__MISSING__` フォールバック・非負 int32 (§14.3)・CYCLE-2 HIGH #5 COPY-NOT-RENAME raw ID drop (`_CATEGORY_COLUMNS` の抽象 alias 5要素のみ drop、`kettonum` は保持)
- `persist_category_maps` / `load_category_maps` (joblib)

### 3. `scripts/run_feature_build.py` — end-to-end CLI (Task 3)
- masked DSN ログ (T-03-25・生 DSN は絶対出力しない)
- `build_feature_matrix` (readonly pool・D-06) → `build_frozen_category_maps` (train 窓 fit) → `apply_frozen_category_maps` (raw ID drop) → `write_snapshot` **2回呼出** で SHA256 完全一致を assert (SC#3) → `write_manifest` → `persist_category_maps`
- `raw_touched=False` assert・W-5 OOM escape hatch (`MemoryError` → exit 4)

### 4. `snapshots/.gitignore` — binary artifact 除外 (D-08 / §19.1)
- `*.parquet` / `*.joblib` は git 管理外。manifest YAML (`.manifest.yaml`) のみ git 管理候補（軽量テキスト・sha256 + §12.4 metadata 監査証跡）

## Live Snapshot Build Result (exit 0 — all 10 checks PASS)

```
snapshot_id: 20260619-1a-v1
rows: 554267  features: 63
category maps: jockey=361 trainers=402 sires=864 bms=15291 horses=42514
sha256 (write #1): 19f11c3113319ae6b35cfde371ee2f69063e651bf37f920b599b65d6fa2673a0
sha256 (write #2): 19f11c3113319ae6b35cfde371ee2f69063e651bf37f920b599b65d6fa2673a0
byte-reproducibility verify: PASS (SC#3・Pitfall 3.5)
raw_touched: False
artifacts: feature_matrix_20260619-1a-v1.parquet (34MB) + .manifest.yaml + category_map_20260619-1a-v1.joblib (946KB)
```

10 verification checks:
1. masked DSN ログ (生 DSN 非表示) — PASS
2. rows ≈ 554267 — PASS (554267)
3. category horses ≈ 42395 — PASS (42514)
4. write#1 sha256 == write#2 sha256 — PASS
5. `byte-reproducibility verify: PASS` + `raw_touched=False` — PASS
6. 3 files in snapshots/ (parquet + manifest.yaml + category_map.joblib) — PASS
7. manifest に §12.4 keys — PASS
8. DuckDB row-count + distinct (race_nkey,kettonum) 一意性 — PASS (554267 == 554267)
9. schema metadata に 9 §12.4 keys — PASS (missing=set())
10. test_allowlist re-run GREEN — PASS (13/13)

追加検証: 異なる `created_at` ("2020-01-01T00:00:00Z") で再 build しても SHA256 が同一 (`19f11c31...`) — HIGH #6 scope (Parquet bytes のみ) 確証。

## Deviations from Plan

### Auto-fixed Issues (Rule 1/2/3)

**1. [Rule 1 - Bug] BUG A: race_nkey は DB カラムでない**
- **Found during:** continuation — live build の `feature source fetch failed` / `history fetch failed`
- **Issue:** `src/features/builder.py` が observations と history の両 SELECT で `normalized.n_uma_race.race_nkey` を直接 SELECT していたが、`race_nkey` は `availability._RESERVED_NON_FEATURE_COLUMNS` の予約済み canonical key であり **DB の実在カラムではない** (information_schema で確認済・全スキーマ/ビュー/生成カラムに存在しない)。psycopg が `column "race_nkey" does not exist` で fetch を失敗させ empty frame にフォールバックしていた
- **Fix:** `make_race_nkey(year, jyocd, kaiji, nichiji, racenum)` helper と `_construct_derived_columns(df)` helper を追加。両 SELECT パスが同一の決定論的構成 (零埋連結 `YYYYJJJKK< nichiji>NN`) を使う (rolling は (race_nkey, kettonum) で group/join)。PIT 意味は不変 (純粋な key formatting)
- **Files modified:** src/features/builder.py
- **Commit:** 0b15b48

**2. [Rule 1 - Bug] BUG A': normalized 層カラム topology 不整合**
- **Found during:** continuation — BUG A 修正後の連鎖的発見
- **Issue:** plan (03-03) は `_HISTORY_SELECT_COLUMNS` / `_OBS_SELECT_COLUMNS` に `race_date` / `race_start_datetime` / `as_of_datetime` / `days_since_prev` / `timediff` / `babacd` / `datakubun` を含めていたが、これらは **normalized 層に存在しない** (information_schema 確認)。`race_date` / `race_start_datetime` は `normalized.n_race` に、`timediff` / `babacd` / `datakubun` は `public.*` / `raw_everydb2.*` のみに存在。psycopg は最初の欠損カラム (`race_nkey`) で止まっていたため、BUG A 修正後にこれらが順次顕在化
- **Fix:** 両 SELECT を `normalized.n_uma_race ur JOIN normalized.n_race nr` に rewrite。実在カラムのみ SELECT し、derived 列 (`race_nkey` / `as_of_datetime` / `days_since_prev`) は `_construct_derived_columns` で pandas 構築。`timediff` / `babacd` は normalized 層に欠損のため SELECT せず、当該 rolling 系統 (`rolling_timediff_*` / `rolling_babacd_*`) は rolling.py の D-13 sentinel 経路で `__MISSING__` (→ Parquet では NaN) 扱い。`babacd` は `sibababacd` / `dirtbabacd` (target-obs-banned・n_race の当日馬場) とは別物 — これらは引き続き排除
- **Files modified:** src/features/builder.py, tests/features/test_builder.py
- **Commit:** 0b15b48

**3. [Rule 3 - Blocking] BUG B: COPY-NOT-RENAME raw ID 原列が allowlist で reject**
- **Found during:** continuation — live build の `ValueError: unregistered feature-matrix column: kisyucode`
- **Issue:** builder は CYCLE-2 HIGH #5 (COPY-NOT-RENAME) に従い抽象 alias (`jockey_id` 等) を copy で追加し raw 原列 (`kisyucode` / `chokyosicode` / `ketto3infohansyokunum1` / `ketto3infohansyokunum2`) を保持する。`assert_matrix_columns_registered` はこれら raw 原列を registry / reserved / `<col>_code` のいずれにも該当しないと reject した
- **Fix:** `availability.py` に `_RAW_ID_KEPT_COLUMNS` frozenset を追加し `assert_matrix_columns_registered` の allowlist に統合。defense-in-depth assert で `TARGET_OBS_BANNED_COLUMNS` が allowlist に混入しないことを検証 (HIGH #3 fail-loud は真に未知のカラムに対して保持・`test_matrix_rejects_unregistered_column` / `test_matrix_rejects_banned_timing_column_under_allowed_name` GREEN)
- **Files modified:** src/features/availability.py
- **Commit:** 0b15b48

**4. [Rule 3 - Blocking] kettonum 型不一致 (bloodline merge)**
- **Found during:** continuation — BUG A/B 修正後の live build
- **Issue:** `normalized.n_uma_race.kettonum` は integer、`public.n_uma.kettonum` は varchar。obs + bloodline の merge が `trying to merge on int64 and str columns` で失敗
- **Fix:** bloodline SQL で `kettonum::int AS kettonum` に cast (非数値は `~ '^[0-9]+$'` で除外)
- **Files modified:** src/features/builder.py
- **Commit:** 9ad0b9d

**5. [Rule 3 - Blocking] days_since_prev が observations に漏洩**
- **Found during:** continuation — `ValueError: unregistered feature-matrix column: days_since_prev`
- **Issue:** `_construct_derived_columns` が history 専用 rolling source 列 `days_since_prev` を observations にも構築し、未登録カラムとして reject された
- **Fix:** `_construct_derived_columns(df, *, with_days_since_prev=False)` に変更し history path のみ `True` で呼出。observations は `days_since_prev` を持たない
- **Files modified:** src/features/builder.py
- **Commit:** 9ad0b9d

**6. [Rule 3 - Blocking] PyArrow ArrowTypeError (rolling object 列)**
- **Found during:** continuation — live build の `write_snapshot` で `Expected bytes, got a 'float' object`
- **Issue:** rolling.py の D-13 契約は未観測/5走未満を `__MISSING__` sentinel (文字列) で表現し、rolling 出力列は object dtype (数値と文字列が混在)。PyArrow は混在 object 列を直列化できない
- **Fix:** snapshot 境界に `_coerce_rolling_columns_for_parquet(df)` を追加。`rolling_*` object 列の `__MISSING__` を NaN に置換し nullable `Float64` に統一。rolling 内部 D-13 契約 (object + sentinel) は不変・純粋な直列化層変換・byte-reproducibility 維持 (決定論的 cast)
- **Files modified:** src/features/snapshot.py
- **Commit:** 9ad0b9d

**7. [Rule 1 - Bug] test_builder の babacd/timediff 過剰 assertion**
- **Found during:** continuation — BUG A' 修正で `_HISTORY_SELECT_COLUMNS` から babacd/timediff が除去され unit test が RED
- **Issue:** `test_banned_columns_not_selected` は `babacd` / `timediff` が `_HISTORY_SELECT_COLUMNS` に含まれることを assert していたが、これらは normalized 層に実在カラムがなく SELECT 対象外
- **Fix:** assertion を実在 history source (`harontimel3` / `jyuni3c` / `jyuni4c`) に緩和。babacd/timediff rolling 系統は sentinel fallback することが docstring で明記
- **Files modified:** tests/features/test_builder.py
- **Commit:** 0b15b48

### Auth Gates

None — readonly pool は password-less 接続 (keiba_readonly ロール)。

## Verification

### Unit Tests
```
KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q
→ 49 passed, 0 failed
```
mock-based test は実 DB カラム topology を仮定していたため BUG A/A' を検出できなかった。live build が唯一の検出経路。live build 後も 49 test は GREEN を維持 (conftest mock は derived 列を直接供給するため実構築 path と整合)。

### Live Snapshot Build (10 checks PASS)
```
uv run python scripts/run_feature_build.py \
    --snapshot-id 20260619-1a-v1 --label-version v1.0.0 --fa-version 0.2.0
→ exit 0
→ sha256=19f11c3113319ae6b35cfde371ee2f69063e651bf37f920b599b65d6fa2673a0
→ 554267 rows × 63 features
→ byte-reproducible (write#1 == write#2, stable across created_at)
```

### TDD Gate Compliance
Plan frontmatter `type: tdd`。本 plan は Plan 03-01 で作成済みの RED unit test 群 (test_snapshot_repro / test_category_map_consumer / test_allowlist) を GREEN 化する実装 (Task 1-3) + live checkpoint 解決 (continuation)。gate sequence は prior commits で履行済:
- `feat(03-04): byte-reproducible Parquet snapshot` (f813dcf) — GREEN
- `feat(03-04): frozen category map` (b17b7cf) — GREEN
- `feat(03-04): CLI run_feature_build` (ff02ce4) — GREEN

本 continuation の 2 commit は live-DB integration bug fix (Rule 1/3) であり TDD gate の追加ではなく、既存 GREEN test を維持した修正。

## Known Stubs

### rolling_timediff_* / rolling_babacd_* systems — sentinel (NaN) 全行
- **Files:** src/features/builder.py (`_HISTORY_DB_SELECT_COLUMNS`), src/features/rolling.py (`_SYSTEM_SOURCE`)
- **Reason:** normalized 層に `timediff` / `babacd` 実在カラムが存在しない (information_schema 確認・public.* / raw_everydb2.* のみ)。これら rolling 系統は D-13 sentinel 経路で全行 NaN となる。`babacd` は当日馬場 (`sibababacd` / `dirtbabacd`・target-obs-banned) とは別物であり、過去走馬場状態 rolling は normalized 層では利用不可。`timediff` は `public.n_uma_race.timediff` に存在するが normalized ETL (Phase 2) で持ち込まれなかった。
- **Impact:** これら 8 system 中 2 system (timediff / babacd) の rolling feature は情報量ゼロ (全 NaN)。Phase 4 モデル学習では LightGBM/CatBoost が NaN を missing として扱うため学習可能だが、当該系統からの寄与はない。
- **Future resolution:** Phase 2 ETL の normalized 層に `timediff` (走時計算の派生指標) と過去走 `babacd` 相当 (例: n_race の sibababacd/dirtbabacd を過去走 race に join) を追加する后再 build で解決可能。本 plan (03-04) の scope 外 (snapshot infra) であり、Phase 2 ETL 拡張または Phase 3 follow-up で対応すべき。rolling 残り 6 system (kakuteijyuni / harontimel3 / jyuni3c_jyuni4c / kyori / jyocd / days_since_prev) は実データで有意に populated (例: rolling_kakuteijyuni_mean_5 は 60650 行のみ NaN = 新馬/<5走)。

### estimated_running_style — `__MISSING__` sentinel 一部
- **Files:** src/features/builder.py (Step 6)
- **Reason:** rolling 同様、過去走 jyuni3c/jyuni4c が欠損の馬は `__MISSING__`。実データでは大多数の馬に過去走があるため populated だが、新馬は sentinel。
- **Impact:** 意図的 D-13 挙動。Phase 4 モデルは `__MISSING__` を専用カテゴリとして扱う。

## Threat Flags

None — 本 plan は新規ネットワーク endpoint / auth path / file access pattern / trust 境界 schema 変更を導入しない。readonly pool のみ使用 (`raw_touched=False`・D-06)。BUG B の `_RAW_ID_KEPT_COLUMNS` 追加は CYCLE-2 HIGH #5 の意図的設計 (Phase 4 が raw ID で refit する経路を開いたまま) であり、`TARGET_OBS_BANNED_COLUMNS` (sibababacd/dirtbabacd/odds 等) は defense-in-depth assert で構造的に排除済。

## Self-Check: PASSED

- FOUND: src/features/snapshot.py
- FOUND: src/features/category_map_consumer.py
- FOUND: scripts/run_feature_build.py
- FOUND: snapshots/.gitignore
- FOUND: snapshots/feature_matrix_20260619-1a-v1.parquet (34MB, gitignored)
- FOUND: snapshots/feature_matrix_20260619-1a-v1.manifest.yaml
- FOUND: snapshots/category_map_20260619-1a-v1.joblib (gitignored)
- FOUND: f813dcf (feat: byte-reproducible Parquet snapshot)
- FOUND: b17b7cf (feat: frozen category map)
- FOUND: ff02ce4 (feat: CLI run_feature_build)
- FOUND: 0b15b48 (fix: BUG A/B/A')
- FOUND: 9ad0b9d (fix: type-cast + days_since_prev + rolling coercion)
