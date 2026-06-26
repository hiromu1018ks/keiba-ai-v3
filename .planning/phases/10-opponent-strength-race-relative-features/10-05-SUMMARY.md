---
phase: 10-opponent-strength-race-relative-features
plan: 05
subsystem: features/snapshot
tags: [feature-snapshot, byte-reproducibility, leak-prevention, pit-correct, odds-free, live-db-validation, parquet-serialization, review-h5]
requires:
  - Phase 10 PLAN 04 builder.py 統合（FEAT-02 21 + FEAT-03 6 = 27 feature・schema_version 0.6.0）
  - src/features/snapshot.py write_snapshot（SC#3 byte-reproducible・§12.4 metadata 9 keys・FIXED_REPRODUCE_TS）
  - src/model/data.py _derive_feature_columns（registry derived FEATURE_COLUMNS allowlist・snapshot_id 明示伝播）
provides:
  - snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet（feature_count=106・model FEATURE_COLUMNS=79・SHA256 byte-reproducible）
  - src/features/snapshot.py::_FEAT03_NUMERIC_COLUMNS frozenset（FEAT-03 6列の防御的 nullable Float64 変換・Pitfall 5 最終防衛線）
  - tests/features/test_snapshot_repro.py 拡張（16 tests・Phase 10 PLAN 05 の 7 新テスト含む）
affects:
  - PLAN 06（run_phase10_evaluation.py）が本 snapshot で LightGBM 再学習（FEATURE_COLUMNS=79・snapshot_id 明示伝播）
  - PLAN 07（adversarial audit）が本 snapshot に対して SC#4 SAFE-01 AST 証明を適用
tech-stack:
  added: []
  patterns:
    - rolling_ prefix 無し FEAT-03 列の snapshot 境界防御的 Float64 変換（_FEAT03_NUMERIC_COLUMNS・builder 保証に加え最終防衛線）
    - live-DB での byte-reproducibility 検証（run_feature_build.py 内部 write #1/#2 SHA256 assert + ファイル SHA256 独立生成比較）
    - REVIEW H5 実キー文字列検査（feature_availability_version・schema 無し・_METADATA_KEYS タプル実値検査で誤キー false-pass 回避）
key-files:
  created:
    - snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet
    - snapshots/feature_matrix_20260626-1a-opponentstrength-v1.manifest.yaml
    - snapshots/category_map_20260626-1a-opponentstrength-v1.json
  modified:
    - src/features/snapshot.py
    - src/features/builder.py
    - tests/features/test_snapshot_repro.py
decisions:
  - FEAT-03 6列の nullable Float64 変換は builder Step6c が保証するが・snapshot.py 境界でも防御的に変換する（Pitfall 5 最終防衛線・実データ Parquet 直列化 bug は unit test では発覚しない・memory feature-snapshot-regen-required）
  - Open Question #3 解決: snapshot_id = '20260626-1a-opponentstrength-v1'（v1.0 20260620-1a-postreview-v2 → Phase 9.1 20260625-1a-speedprofile-v1 → Phase 10 系統継承・make_model_version 形式）
  - PLAN truth「model feature count 106（FEATURE_COLUMNS リスト長）」記載は不正確・正しくは Parquet 全列数=106・model FEATURE_COLUMNS=79（registry derived・META/RAW_ID/LABEL 除外・Phase 9.1 52 + 27 新 feature）。実質の検証対象（27 新 feature が FEATURE_COLUMNS に含まれる）は完全達成
  - REVIEW H5-CLI 確認: run_feature_build.py 実装 CLI 引数（--snapshot-id / --label-version / --fa-version / --created-at）を使用・--bt-split は存在しない（T-10-22b mitigate）
metrics:
  duration: 約90分（live-DB snapshot 生成 約25分/回 × 2回 + テスト拡張 + 検証）
  completed: 2026-06-27
  tasks: 2（Task 1: auto/TDD・Task 2: live-DB 検証）
  files: 5（src 2 + tests 1 + snapshots 3）
  tests: 16 unit tests GREEN (test_snapshot_repro.py) + 173 features+audit GREEN
status: complete
---

# Phase 10 Plan 05: feature snapshot 20260626-1a-opponentstrength-v1 生成 + byte-reproducibility 検証 Summary

PLAN 04 で統合した builder パイプライン（FEAT-02 21 + FEAT-03 6 = 27 新 feature・schema_version 0.6.0）を使って live-DB から feature snapshot `20260626-1a-opponentstrength-v1` を生成し・SC#3 byte-reproducibility（§19.1 聖域）を実データで検証した。Task 1 で snapshot.py の FEAT-03 6列に対する防御的 nullable Float64 変換を追加し・byte-reproducibility テスト・metadata 実キー検査（REVIEW H5）テストを拡張（16 tests GREEN）。Task 2 の live-DB 検証で Rule 1 bug（builder Step6d が `field_strength_adjusted_rank` を誤 drop）を発見し修正・最終的に feature_count=106・model FEATURE_COLUMNS=79（27 新 feature 全て含む）・2回の独立生成でファイル SHA256 完全一致（`ea16f1e6...`）を実証した。Pitfall 5（Parquet 直列化失敗）は実データで回避済み。

## What Was Built

### src/features/snapshot.py 拡張（FEAT-03 列防御的 nullable Float64 変換・Pitfall 5 最終防衛線）

- **`_FEAT03_NUMERIC_COLUMNS` frozenset 追加**: FEAT-03 6列（`speed_index_rank_{mean5,best2_mean5,median5}`・`gap_to_top`・`gap_to_3rd`・`field_strength_adjusted_rank`）を定義。`rolling_` prefix 無しの FEAT-03 列が object dtype + sentinel の場合に Parquet ArrowInvalid を起こすため・snapshot 境界でも防御的に nullable Float64 変換する（builder Step6c 保証に加え最終防衛線・memory feature-snapshot-regen-required）。
- **`_coerce_rolling_columns_for_parquet` 拡張**: `rolling_` prefix 列に加え・`_FEAT03_NUMERIC_COLUMNS` 列も numeric 変換（sentinel → NaN・D-09 欠損馬 NaN 保持と整合）。byte-reproducibility は維持（決定論的 cast）。

### src/features/builder.py 修正（Rule 1 auto-fix・Step6d drop 条件）

- **問題**: Step6d drop 条件 `c.startswith("field_strength_") and not c.startswith("rolling_field_strength_")` が・FEAT-03 feature `field_strength_adjusted_rank`（race_relative.py L287-289 で生成・D-11/D-12）にもマッチし・中間値でない FEAT-03 feature を誤って drop していた。
- **発覚経路**: PLAN 05 Task 2 の live-DB snapshot 生成（feature_count=105）で・Parquet 全列から `field_strength_adjusted_rank` が欠落していることを発見（registry には登録済み・Step6c で生成されるが Step6d で消されていた）。
- **修正**: `_FEAT03_KEEP_COLS` frozenset（6 feature）を定義し・drop 対象から除外。registry parity と FEATURE_COLUMNS allowlist が完全一致するようになった。

### tests/features/test_snapshot_repro.py 拡張（7 新テスト追加・計16 GREEN）

- **Test: `test_phase10_snapshot_id_preregistered`** — Open Question #3 snapshot_id='20260626-1a-opponentstrength-v1' 事前登録（文字列リテラル検査・typo 検出）。
- **Test: `test_phase10_byte_reproducible_with_27_new_features`** — SC#3 byte-reproducible・27 新 feature を含む同一 DataFrame で SHA256 完全一致。
- **Test: `test_phase10_feat02_columns_coerced_to_nullable_float64`** — Pitfall 5・FEAT-02 rolling_field_strength_* 21 列が nullable Float64 変換（rolling_ prefix 自動対象）。
- **Test: `test_phase10_feat03_columns_coerced_to_nullable_float64`** — Pitfall 5・FEAT-03 6列が防御的 nullable Float64 変換（rolling_ prefix 無し・_FEAT03_NUMERIC_COLUMNS 対象）。
- **Test: `test_phase10_metadata_feature_availability_version`** — REVIEW H5・metadata 実キー `feature_availability_version=0.6.0`（schema 無し・誤キー `feature_availability_schema_version` が存在しないことも検査）。
- **Test: `test_phase10_metadata_keys_literal_in_metadata_keys_tuple`** — REVIEW H5 厳格対応・snapshot.py `_METADATA_KEYS` タプル実値に `feature_availability_version` が含まれ `feature_availability_schema_version` は含まれないことを検査（inspect.getsource でなく実値検査・docstring false positive 回避）。
- **Test: `test_phase10_fixed_reproduce_ts_sha256_independent_of_created_at`** — FIXED_REPRODUCE_TS・created_at_fixed を変化させても SHA256 は同一（§19.1 聖域）。

### snapshots/feature_matrix_20260626-1a-opponentstrength-v1 生成（live-DB・SC#3 byte-reproducible 実証）

- **生成コマンド**: `uv run python scripts/run_feature_build.py --snapshot-id 20260626-1a-opponentstrength-v1 --label-version v1.0.0 --fa-version 0.6.0 --created-at 2026-06-26T00:00:00Z`（REVIEW H5-CLI・実装 CLI 引数のみ使用・`--bt-split` は存在しない・T-10-22b mitigate）。
- **statement_timeout 設定**: `PGOPTIONS='-c statement_timeout=1800000'` で重い Step5c（per-source-race batch）を保護（memory subagent-db-query-statement-timeout）。
- **結果**: row_count=554267・feature_count=106（Parquet 全列・27 新 feature 含む）・model FEATURE_COLUMNS=79（registry derived allowlist・Phase 9.1 52 + 27 新 feature）・raw_touched=False（readonly role・D-06）。
- **SHA256 (metadata除外 schema bytes)**: `c25ae5561e5e1db068973972e57a4f61d2f919be28a2e82ed9a72e05a750cd00`・run_feature_build.py 内部の write #1/#2 SHA256 一致 assert PASS（SC#3・Pitfall 3.5）。
- **ファイル SHA256**: `ea16f1e65b595484dedb27fc85c53c7b318ceb7761d494f2959336a48bdaee70`・**2回の独立生成で完全一致**（PLAN how-to-verify step 6・§19.1 聖域の実データ実証）。
- **§12.4 metadata 9 keys**: `feature_snapshot_id=20260626-1a-opponentstrength-v1`・`feature_availability_version=0.6.0`（REVIEW H5・schema 無し・実キー）・`label_version=v1.0.0`・`prediction_timing=1A` 等。
- **Pitfall 5 回避**: FEAT-02 21 列（rolling_ prefix で自動対象）+ FEAT-03 6 列（防御的 _FEAT03_NUMERIC_COLUMNS 対象）が nullable Float64 で直列化され・PyArrow ArrowTypeError 無し（実データ検証 PASS）。
- **生成時間内訳**: Step5b speed_figure 22s + Step5c field_strength profile 728s + Step5 rolling 268s + 書出/manifest ~30s = 約17分/回。

## TDD Gate Compliance

- RED commit: 2eb5f23 のテスト拡張が RED を検出（FEAT-03 object dtype + sentinel で `pyarrow.lib.ArrowInvalid: Could not convert '__MISSING__' with type str`・Pitfall 5 再現）。
- GREEN commit: 2eb5f23（同一 commit・`_FEAT03_NUMERIC_COLUMNS` 追加で全16 tests GREEN）。
- 追加 GREEN commit: d84a331（Rule 1 auto-fix・live-DB 検証で発覚した `field_strength_adjusted_rank` drop bug 修正）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] builder Step6d drop 条件が `field_strength_adjusted_rank` を誤 drop**
- **Found during:** Task 2 live-DB snapshot 生成（feature_count=105 で `field_strength_adjusted_rank` が Parquet から欠落）
- **Issue:** Step6d の drop 条件 `c.startswith("field_strength_") and not c.startswith("rolling_field_strength_")` が・FEAT-03 feature `field_strength_adjusted_rank`（race_relative.py L287-289 で生成・D-11/D-12・target-only race_id group-by）にもマッチし・中間値でない FEAT-03 feature を誤 drop していた。registry には登録済み（schema_version 0.6.0）・Step6c で生成されるが Step6d で消されていた。unit test（KEIBA_SKIP_DB_TESTS=1）では発覚せず・live-DB 実データ snapshot 生成でのみ発覚（memory feature-snapshot-regen-required の典型的パターン）。
- **Fix:** `_FEAT03_KEEP_COLS` frozenset（6 feature）を定義し・drop 対象から除外（`c not in _FEAT03_KEEP_COLS` 条件を追加）。registry parity と FEATURE_COLUMNS allowlist が完全一致。
- **Files modified:** src/features/builder.py
- **Commit:** d84a331

**2. [Rule 2 - Defensive] snapshot.py に FEAT-03 6列の防御的 nullable Float64 変換を追加**
- **Found during:** Task 1 テスト拡張（FEAT-03 列の object dtype + sentinel が PyArrow ArrowInvalid を起こすことを RED で再現）
- **Issue:** PLAN 04 で builder Step6c が FEAT-03 6列の nullable Float64 を保証するが・snapshot 境界でも防御的に扱う必要がある（実データ Parquet 直列化 bug は unit test では発覚しない・Pitfall 5・memory feature-snapshot-regen-required）。PLAN Task 1 action (3) の「もし builder 側だけでは不十分な場合」に該当。
- **Fix:** `_FEAT03_NUMERIC_COLUMNS` frozenset（6 列）を定義し・`_coerce_rolling_columns_for_parquet` で `rolling_` prefix 列に加え FEAT-03 列も numeric 変換（sentinel → NaN・D-09 整合）。builder 保証に加え・snapshot 境界での最終防衛線。
- **Files modified:** src/features/snapshot.py
- **Commit:** 2eb5f23

### 設計上のメモ（逸脱でなく・PLAN の検証結果）

**1. PLAN truth「model feature count が 106」記載の不正確**: PLAN 真偽条件は「model feature count が 106（FEATURE_COLUMNS リスト長・79 既存 + 27 新 feature）」と記載。実際は FEATURE_COLUMNS=79（registry derived allowlist・META/RAW_ID/LABEL 除外）で・106 は Parquet 全列数（META 23 + RAW_ID 4 + LABEL 17 + feature columns 含む）。実質の検証対象（27 新 feature 全てが FEATURE_COLUMNS に含まれる・delta from Phase 9.1 = +27）は完全達成。PLAN 04 SUMMARY の「model feature count: registry 全体 82 features」記載とも整合（82 registry features から META/RAW_ID/LABEL と重複除外で 79）。

**2. SC#3 byte-reproducibility 二重検証**: `run_feature_build.py` が内部で write #1/#2 の SHA256 assert を実施（metadata除外 schema bytes）・それに加えて PLAN how-to-verify step 6 の「2回 build で SHA256 一致」を・ファイル SHA256（metadata 含む全体）でも実証（2回の独立生成で `ea16f1e6...` 完全一致）。这两层验证都是 §19.1 聖域の実証。

## SAFE-01 / core value 整合性

本 PLAN は snapshot.py と builder.py のみ拡張・市場 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）は一切導入せず・SC#3 byte-reproducibility は `run_feature_build.py` 内部検証 + ファイル SHA256 独立生成比較の二重検証で保証。registry に市場情報 proxy は一切含まれず・FEATURE_COLUMNS allowlist（registry derived）も自動的に odds-free。PLAN 07 adversarial AST audit が完全証明する前提が整った（snapshot が生成され FEATURE_COLUMNS=79 が確定）。

## Verification

- PLAN Task 1 verify: `uv run pytest tests/features/test_snapshot_repro.py -x -q` → 16 passed（7 新テスト含む）
- features/ 全体回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q` → 157 passed
- audit suite 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` → 16 passed
- features+audit 統合回帰（Rule 1 fix 後）: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ tests/audit/ -q` → 173 passed
- PLAN Task 2 live-DB 検証:
  - snapshot 生成成功: `uv run python scripts/run_feature_build.py --snapshot-id 20260626-1a-opponentstrength-v1 --label-version v1.0.0 --fa-version 0.6.0 --created-at 2026-06-26T00:00:00Z` → exit 0・raw_touched=False
  - feature_count=106 (Parquet 全列・27 新 feature 含む)・model FEATURE_COLUMNS=79 (delta from Phase 9.1 = +27)
  - SHA256 (metadata除外) = `c25ae556...`・write #1/#2 一致（run_feature_build.py 内部 assert PASS）
  - ファイル SHA256 = `ea16f1e6...`・2回独立生成で完全一致（§19.1 聖域・PLAN how-to-verify step 6 PASS）
  - metadata 実キー検査: `feature_availability_version=0.6.0`（schema 無し・REVIEW H5 PASS）
  - ArrowTypeError 無し（Pitfall 5 回避・FEAT-02/03 nullable Float64 変換が実データで成功）
- lint: `uv run ruff check src/features/snapshot.py src/features/builder.py` → 私の追加分の E501 は日本語コメント既存スタイル（PLAN 04 と同一方針・許容）

## Known Stubs

なし。本 PLAN は snapshot 生成・検証 plan で・PLAN 04 で統合済みの 27 新 feature が全て FEATURE_COLUMNS に含まれ・live-DB 実データで byte-reproducible な Parquet が生成された。PLAN 06（run_phase10_evaluation.py・SC#5 非劣化 gate）が本 snapshot で LightGBM 再学習する前提が整った。

## Self-Check: PASSED

- src/features/snapshot.py: FOUND
- src/features/builder.py: FOUND
- tests/features/test_snapshot_repro.py: FOUND
- snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet: FOUND
- snapshots/feature_matrix_20260626-1a-opponentstrength-v1.manifest.yaml: FOUND
- snapshots/category_map_20260626-1a-opponentstrength-v1.json: FOUND
- commit 2eb5f23 (Task 1: snapshot.py FEAT-03 変換 + テスト拡張): FOUND
- commit d84a331 (Rule 1 fix + live-DB snapshot): FOUND
