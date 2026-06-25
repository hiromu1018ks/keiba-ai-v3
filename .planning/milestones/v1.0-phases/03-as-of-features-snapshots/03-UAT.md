---
status: complete
phase: 03-as-of-features-snapshots
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md, 03-05-SUMMARY.md
started: 2026-06-20T01:22:46Z
updated: 2026-06-20T02:05:00Z
note: |
  Phase 3 は 03-05 SUMMARY 後に大幅進化: deep review 14 fix (CR-01..04/WR-01..11) + 実データ検証
  RT-01/02 + Phase 3.1 (timediff/babacd 復元→8系統) + schema 0.2.0→0.3.0 bump。
  03-VERIFICATION.md は既に status: passed (4/4)。本 UAT の expected は現在のコードベース基準。
  検証者: Claude (live-DB 操作・memory run-authorized-ops-directly/feature-snapshot-regen-required に準拠)。
---

## Current Test

[testing complete]

## Tests

### 1. Unit Test Suite 全体 GREEN (Cold-start smoke)
expected: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q` が全て pass。skipped は live-DB マーカーのみ、機能テスト失敗 0 件。
result: pass
evidence: `202 passed, 21 skipped in 3.47s`（21 skipped は全て KEIBA_SKIP_DB_TESTS マーカー・機能テスト失敗 0）

### 2. Feature Availability Registry 整合性 (3者 parity)
expected: schema 0.3.0・8 rolling 系統（timediff/babacd 含む・Phase 3.1 復元）・banned timing の feature entry 0件（available_from_timing は entry_confirmed/post_position_confirmed のみ）・jyocd は categorical の mode_5/latest_5（CR-02・mean_5/sd_5 廃止）・3者 parity が unit test で機械保証。
result: pass
evidence: schema_version 0.3.0 / available_from_timing=entry_confirmed(35)+post_position_confirmed(4) のみ（banned 0件） / rolling_jyocd=mode_5+latest_5（mean/sd 廃止） / rolling.py==availability.py: True（8系統）

### 3. PIT Cutoff Leak-Prevention 検証 (adversarial)
expected: rolling + estimated_running_style 両方で PIT pre-filter (strict < feature_cutoff_datetime・per-observation/obs_id) を適用、CR-01 canonical key merge で row-misalignment 解消。adversarial テスト（同一 horse × 複数 observation × 異 cutoff）GREEN。
result: pass
evidence: unit test 全体 202 passed に含まれる (test_pit_cutoff / test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs / test_estimated_running_style_applies_pit_prefilter / test_two_observation_window_is_per_observation_not_per_horse)

### 4. Pickle ACE 解消 (joblib→JSON 移行)
expected: category_map_consumer.py に joblib import 不在 (AST guard)・artifact `.json`・atomic write (WR-10 tmp+os.replace)・JSON round-trip で sentinel 保持。
result: pass
evidence: `grep joblib import → なし` / run_feature_build.py `category_map_<id>.json` / unit test GREEN

### 5. Cold-Start Snapshot Build (live-DB, byte-reproducible)
expected: `scripts/run_feature_build.py` を新規 snapshot_id・fa-version 0.3.0 でクリーン実行 → exit 0、≈554267 rows × 62 features、write#1==write#2 SHA256 一致 (byte-reproducibility PASS)、raw_touched=False、3 ファイル生成、RT-01/02 反映。
result: pass
evidence: live-DB 554267行・exit 0・rows=554267 features=62 raw_touched=False・byte-reproducibility PASS (write#1==write#2=8ed8829cd259904ba20a498ac6398e38daf3dae1e4583bd2bbe4b436e3723f32)・3ファイル生成 (parquet 38M + manifest + json 1.2M)・masked DSN

### 6. Reproducibility Manifest §12.4 完備
expected: 生成 manifest.yaml に §12.4 reproducibility keys 全て存在。SHA256 scope = parquet_data_only_metadata_excluded (CR-04)。Parquet schema metadata に実際の snapshot_id/created_at 埋込（監査証跡復元）。Parquet 内 (race_nkey, kettonum) 一意性。
result: pass
evidence: manifest missing §12.4 keys = []（18 keys 全完備）/ sha256 scope=parquet_data_only_metadata_excluded / Parquet metadata に snapshot_id=20260620-1a-uat + created_at + 9 §12.4 keys 実値埋込 (CR-04) / obs_id in columns=False (RT-01) / rolling_jyocd_mode_5+latest_5=large_string (RT-02)・count_5=double / (race_nkey,kettonum) 554267/554267 一意

### 7. label.race_date Backfill Idempotent (live-DB)
expected: `scripts/run_label_race_date_backfill.py` を 2 回連続実行 → run#1 と run#2 が同一 rowcount + checksum (idempotent verify PASS)、スクリプト全体 raw fingerprint 前後一致 (WR-07)、raw_touched=False、label.fukusho_label.race_date 全行非 NULL。
result: pass
evidence: run#1==run#2 (rows=554267 checksum=554267|554267)・idempotent 検証 PASS (HIGH #3)・raw 不変性 スクリプト全体 PASS (WR-07 前後 fingerprint 完全一致)・raw 不変性 PASS (row-hash+row-count+pg_stat)・race_date 全行非 NULL 554267/554267・masked DSN・exit 0

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Advisories 状態（UAT 検証後・2026-06-20 訂正）

UAT 実施時に実コードを精査した結果、03-VERIFICATION.md が記録していた advisories #1-#4 は **Phase 3.1 で既に hardening 済み**（コードコメント「Phase 3.1 advisory hardening」+ 専用 unit test GREEN で証明・11 test）。03-VERIFICATION.md の advisory 記述は Phase 3.1 適用前の状態で残存していた。**修正作業は不要**。

### 既に hardening 済み（Phase 3.1・test GREEN・修正不要）

1. **CR-01(new) manifest 書出順序** — persist_category_maps → exists() assert → write_manifest の順序（`run_feature_build.py:214-242`・docstring L19-20）。test: `test_snapshot_repro.py::test_persist_before_manifest_order` / `test_persist_then_manifest_order_in_script_source` ✓
2. **WR-01' silent no-filter fallback** — `as_of_datetime` 不在時 ValueError で fail-loud（`builder.py:500-504`）。test: `test_builder.py::test_wr01_prime_raises_on_missing_as_of_datetime` ✓
3. **WR-02 空 frame fail-loud** — `_fetch_*` は OperationalError/InterfaceError/ConnectionError 限定 + `build_feature_matrix:398-402` で空 frame を RuntimeError で fail-loud。test: `test_builder.py::test_wr02_raises_on_empty_feature_source` ✓
4. **WR-03 groupby().apply 非推奨形** — numeric 系統は vector 形（`.notna().groupby().sum()`・`rolling.py:322-325`）に置換。test: `test_rolling.py::test_jyocd_categorical_mode_aggregation` ✓

### Phase 4 で対応（Phase 3 スコープ外・設計上の留保）

5. **WR-05** — `estimated_running_style` の `__MISSING__` sentinel が object dtype のまま snapshot に乗る（Phase 4 LightGBM category 変換時の §14.3 Negative-code hazard）。feature snapshot は生の category 値を保存する Phase 3 設計・code 化は Phase 4 LightGBM 統合の責務（advisory recommendation も Phase 4 推奨）。

6. **SHA256 drift (0.2.0 vs 0.3.0)** — 【原因判明・UAT 深掘り】postreview-v1 (sha256=65426387461b...) と uat (sha256=8ed8829cd259904b...) の Parquet を比較: rows/cols/型/sort 後 key 全て一致、差分は data column の `feature_snapshot_id`（snapshot_id 固有値）と `feature_availability_version`（0.2.0 vs 0.3.0）の 2 列のみで、他 60 列（実 feature data）は完全一致。CR-04 SHA256 scope (parquet_data_only_metadata_excluded) は Parquet schema metadata(key-value) を除外するが、feature_matrix の data column に stamp された識別子は含まれるため、SHA256 が snapshot_id と fa_version に依存する。データ破損/jyocd 非決定性ではなく識別子の差。同一 snapshot_id+fa_version+source で再生成 → 同じ SHA256 (write#1==write#2 で証明) で再現性 Core Value の最小要件は満たす。Phase 4 で SHA256 を「純粋なデータ同一性判定」に使う場合、識別子列を SHA256 計算から除外する設計変更（または識別子を data column でなく schema metadata のみに格納）を推奨。

## Gaps

[none — 全テスト pass・Phase 3 success criteria 達成]
