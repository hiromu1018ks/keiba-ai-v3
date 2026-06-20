---
status: complete
phase: 03-as-of-features-snapshots
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md, 03-05-SUMMARY.md
started: 2026-06-20T01:22:46Z
updated: 2026-06-20T01:43:00Z
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

## Acknowledged Advisories (Phase 4 前修正推奨・blocks_current_sc: false)

Phase 03-VERIFICATION.md (status: passed, 4/4 must-haves) が記録する 5 advisory + UAT で発見した 1 確認事項。現状機能は動作・Phase 3 success criteria は非ブロック。Phase 4 学習前に対処推奨（特に #1, #2, #6）。

1. **CR-01(new) warning** — `scripts/run_feature_build.py:206-228` manifest 書出が persist_category_maps(L228) より先。persist 失敗（disk full/権限/encode error）時に SHA256 一致の「完成済」manifest が残り category_map artifact 欠損の再現性破壊状態が完成する潜在リスク。現状 live snapshot では artifact 正常生成済。
2. **WR-01' warning** — `src/features/builder.py:353-354` estimated_running_style の silent no-filter fallback（`else: pit_filtered_style = expanded_style`）。live path では到達不能だが将来 refactor/合成 history inject で未来レース混入の余地。
3. **WR-02 warning** — `_fetch_feature_sources/_fetch_history` の `except Exception` 空 frame フォールバック（deep review 時点指摘・WR-01 fix 137395d で OperationalError 限定に変更済だが advisory は旧記述を参照）。
4. **WR-03 info** — `rolling.py:236-240` groupby().apply(lambda) が pandas 3.x 非推奨形。将来 pandas upgrade で SHA256 drift の可能性。
5. **WR-05 info** — `estimated_running_style` の `__MISSING__` sentinel が object dtype のまま snapshot に乗る（Phase 4 LightGBM category 変換時の §14.3 Negative-code hazard）。Phase 4 スコープ。

### UAT で発見した確認事項（Phase 4 前推奨）

6. **SHA256 drift (0.2.0 vs 0.3.0)** — postreview-v1 (fa 0.2.0, sha256=65426387461b05fb...) と uat (fa 0.3.0, sha256=8ed8829cd259904b...) で SHA256 が異なる。ef635b6 の snapshot.py diff は fa_version デフォルト引数変更のみで data 書き方に無関係・feature 定義も実質同じ（feature_count 62・jyocd categorical + obs_id 除外は両 snapshot で適用済み）。同一 0.3.0 プロセス内の再現性は write#1==write#2 で証明済み (byte-repro PASS)。異なる時点間の drift 原因は要追跡（source データ変化 or jyocd mode 集計の tie-break 非決定性の可能性）。Core Value「再現性」に関わるため、Phase 4 学習前に固定 source での 0.3.0 再生成 SHA256 安定性を要確認。

## Gaps

[none — 全テスト pass・Phase 3 success criteria 達成]
