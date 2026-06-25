---
phase: 04-model-prediction
plan: 02
subsystem: model-data-calibrator-artifact
tags: [phase-04, data-layer, calibrator, artifact, sc1, sc4, review-high9, review-medium5, review-medium6, review-high5]
requires:
  - "Phase 04-01: lightgbm/catboost pin + prediction DDL + tests/model/ RED stubs + postreview-v2 snapshot 確定"
  - "Phase 03.1: stamped Parquet snapshot (20260620-1a-postreview-v2・feature_count=62・sha256=26c685f0...ecbdd2)"
provides:
  - "src/model/__init__.py (package marker)"
  - "src/model/data.py: load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix/make_race_key/verify_snapshot_sha256/split_3way/load_frozen_maps + FEATURE_COLUMNS (registry derived allowlist)"
  - "src/model/calibrator.py: calibrate_model (fit_prefit_calibrator 薄い wrapper・isotonic/sigmoid 切替) + CalibrationResult NamedTuple"
  - "src/model/artifact.py: save_native_artifact (base native + calibrator.joblib 分離) + load_native_artifact (真正再構築) + write_metadata_json (atomic)"
  - "GREEN 化: tests/model/test_data.py (4件) + tests/model/test_calibrator.py (6件)"
affects:
  - "後続 PLAN 03 (trainer/baseline): data.py の prepare_model_matrix/split_3way/load_frozen_maps/FEATURE_COLUMNS を消費"
  - "後続 PLAN 04 (predict): calibrate_model の CalibrationResult + artifact save/load を消費"
  - "後続 PLAN 05 (evaluator/reproduce 強化): test_reproduce_bit_identical を trainer 本体 + 3way 実データで再強化"
tech-stack:
  added: []
  patterns:
    - "明示的データ API 5関数分離 (review HIGH#9: load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix)"
    - "FEATURE_COLUMNS registry derived allowlist (review HIGH#9: metadata/raw-ID/label 除外・make_X_y が X.columns == FEATURE_COLUMNS を完全一致 assert)"
    - "verify_snapshot_sha256: Phase 3 snapshot.write_snapshot と同一手順で metadata 除外再計算 (byte_reproducible_scope=parquet_data_only_metadata_excluded)"
    - "正準 race_key (year,jyocd,kaiji,nichiji,racenum) 統一・race_nkey 廃止 (review HIGH#9)"
    - "完全時系列条件 guard (review MEDIUM#5: train_max<calib_min<calib_max<test_min<=test_max を raise ValueError)"
    - "fit_prefit_calibrator 薄い wrapper (PATTERNS: 再実装禁止・既存契約消費)"
    - "CalibratedClassifierCV 分離保存 (review HIGH#5: base native + calibrator.joblib・pickle 不使用)"
    - "合成 label DataFrame injection で DB 依存をテストから排除 (review HIGH#9: fake-green 回避)"
key-files:
  created:
    - "src/model/__init__.py"
    - "src/model/data.py"
    - "src/model/calibrator.py"
    - "src/model/artifact.py"
  modified:
    - "tests/model/test_data.py"
    - "tests/model/test_calibrator.py"
decisions:
  - "D-01: SNAPSHOT_PATH = snapshots/feature_matrix_20260620-1a-postreview-v2.parquet (正・feature_count=62)"
  - "review HIGH#9: データ API を load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix の5関数に明示分離し FEATURE_COLUMNS を registry derived allowlist で定義・make_X_y が X.columns == FEATURE_COLUMNS を完全一致 assert で契約混乱と fake-green を防止"
  - "review HIGH#9: FEATURE_COLUMNS = 35 feature (24 rolling/static + 5 _code + 6 静的 = barei/sexcd/futan/umaban/wakuban/class_code_normalized)。PLAN acceptance の「42」は v3/feature_count=63 時代の旧情報・postreview-v2 実データ値 35 が正 (Rule 3 auto-fix)"
  - "review HIGH#9: 正準 race_key = (year,jyocd,kaiji,nichiji,racenum) に統一・race_nkey フォールバック廃止・disjoint 検査は正準 race_key で実施"
  - "review MEDIUM#5: split_3way が完全時系列条件 train_max < calib_min < calib_max < test_min <= test_max を raise ValueError で保証 (python -O で生存)"
  - "review MEDIUM#6: verify_snapshot_sha256 が manifest の完全 SHA256 (64 hex) と hash scope (parquet_data_only_metadata_excluded) を検証・Phase 3 snapshot.write_snapshot と同一手順で metadata 除外再計算"
  - "review HIGH#5/D-06: save_native_artifact が CalibratedClassifierCV を base native (lgb_model.txt/cb_model.cbm/sklearn_base.joblib) + calibrator.joblib + metadata.json (sort_keys=True・atomic write) に分離保存・load_native_artifact が真正再構築"
  - "Cycle 3 NEW-M1: scikit-learn==1.9.0 pin を安定性保証・test_artifact_save_load_roundtrip が np.allclose(rtol=1e-12, atol=1e-12) で保存前後 predict_proba 一致を検証 (pin 破壊で即時 RED)"
  - "Cycle 3 NEW-L1: calibrator.joblib は必須・欠落時 FileNotFoundError で fail-loud・native base 単独での再構築は物理的に不可能"
  - "Rule 2: 合成 label DataFrame を inject して DB 依存をテストから排除 (review HIGH#9: fake-green 回避・load_labels/build_training_frame/make_X_y/split_3way が DB 接続無しで unit test 可能)"
metrics:
  duration: 13m
  completed: 2026-06-20
  tasks: 2
  files_created: 4
  files_modified: 2
status: complete
---

# Phase 4 Plan 02: Model Data/Calibrator/Artifact Summary

** stamped Parquet 読込 + label join + 3way 正準 race_key disjoint 分割 (SC#1/MODL-01/D-02b) + fit_prefit_calibrator 薄い wrapper (SC#4/§15.2) + CalibratedClassifierCV base/calibrator 分離保存 (review HIGH#5/D-06)・review HIGH#9/MEDIUM#5/MEDIUM#6 全対応**

Phase 4 Wave 2 として、後続 PLAN 03 (trainer/baseline)・PLAN 04 (predict/prediction_load) が依存する「feature matrix + label + 3way split + calibrated estimator」の service interface を確立した。review HIGH#9 の「prepare_model_matrix 契約混乱で label join が未実装のままテストが GREEN になる fake-green」を、データ API の明示的5関数分離と合成 label DataFrame injection で防止した。リーク防止プリミティブ (availability/calibrator/category_map/group_split) は再実装せず既存契約を消費した。

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | src/model/data.py — stamped Parquet 読込 + label join + allowlist + 3way split (SC#1/MODL-01) | `a7068cd` | src/model/__init__.py, src/model/data.py, tests/model/test_data.py |
| 2 | src/model/calibrator.py + src/model/artifact.py — prefit wrapper + native artifact save (SC#4/D-06) | `06faf02` | src/model/calibrator.py, src/model/artifact.py, tests/model/test_calibrator.py |

## What Was Built

### Task 1: src/model/data.py — SC#1/MODL-01/D-02b/review HIGH#9/MEDIUM#5/MEDIUM#6

- **明示的データ API 5関数分離 (review HIGH#9)**: 契約混乱と fake-green を防止するため、データ API を単一責任の5関数に明示分離した:
  - `load_feature_matrix()` — Parquet のみ読込（live DB 引数 arity 0・SC#1 聖域）
  - `load_labels(readonly_cur)` — DB readonly 読込（懸念分離・明示的 DB 依存）
  - `build_training_frame(feature_df, label_df)` — 純粋 join（DB 非依存・テスト容易）
  - `make_X_y(frame)` — 厳密 feature 選択（X.columns == FEATURE_COLUMNS 完全一致 assert）
  - `prepare_model_matrix(...)` — 上記を統合する thin orchestrator（実ロジック持たず）
- **FEATURE_COLUMNS registry derived allowlist (review HIGH#9/T-04-12c)**: `feature_availability.yaml` registry の登録 feature 集合から、SNAPSHOT に実在する feature のみを取得し、META_KEY_COLUMNS ∪ RAW_ID_COLUMNS ∪ LABEL_COLUMNS を差し引いた明示的 allowlist。FEATURE_COLUMNS = 35 feature（24 rolling/static + 5 `_code` + 6 静的: barei/sexcd/futan/umaban/wakuban/class_code_normalized）。`make_X_y` が `X.columns == FEATURE_COLUMNS` を完全一致（集合 + 順序）で assert する。
- **正準 race_key 統一 (review HIGH#9)**: `make_race_key(df)` が `(year,jyocd,kaiji,nichiji,racenum)` の `-` 結合文字列を返す。ad-hoc な `race_nkey` フォールバックは廃止（race_nkey は参考専用・disjoint 検査に使わない）。
- **3way split 完全時系列条件 (review MEDIUM#5)**: `split_3way` が D-02b 推奨案（train 2016-07..2023 / calib 2024-H1 / test 2024-H2 / 2025+ 温存）の暦年 mask で分離し、完全条件 `train_max < calib_min < calib_max < test_min <= test_max` を `raise ValueError` で保証（python -O で生存）。正準 race_key の pairwise disjoint も `raise ValueError` で保証。
- **manifest 完全 SHA256 検証 (review MEDIUM#6)**: `verify_snapshot_sha256` が manifest の完全 SHA256（64 hex・略記でない）と `byte_reproducible_scope=parquet_data_only_metadata_excluded`（Phase 3 D-08 と一致）を assert し、Phase 3 `snapshot.write_snapshot` と同一手順（metadata 除外・決定論的書込設定）で hash 再計算して `secrets.compare_digest` で比較する。
- **raw ID 原列除外 (Pitfall 4/T-04-07)**: RAW_ID_COLUMNS = {kisyucode, chokyosicode, ketto3infohansyokunum1, ketto3infohansyokunum2} を FEATURE_COLUMNS から除外。
- **banned features 検査 (D-07/§13.4)**: `make_X_y` が `assert_matrix_columns_registered` と `banned_features(spec) == []` を二重検査。
- **test_data.py 4件 GREEN**: test_load_from_parquet_only / test_raw_ids_excluded / test_no_banned_features / test_race_id_disjoint_3way。合成 label DataFrame を inject して DB 依存を排除（review HIGH#9: fake-green 回避）。

### Task 2: src/model/calibrator.py + src/model/artifact.py — SC#4/D-06/review HIGH#5

- **calibrator.py 薄い wrapper (PATTERNS)**: `fit_prefit_calibrator` を再実装せず薄く wrap。唯一の追加ロジックは §15.2 推奨の `calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"` 切替。戻り値 `CalibrationResult(calibrated, calib_method)` NamedTuple で provenance 提供（predict.py が calib_method 列に書込）。
- **artifact.py 分離保存 (review HIGH#5)**: `save_native_artifact` が `CalibratedClassifierCV` を base ネイティブ形式（lightgbm→lgb_model.txt / catboost→cb_model.cbm / sklearn→sklearn_base.joblib）+ calibrator.joblib（wrapper 全体）+ metadata.json（sort_keys=True・atomic write・saved_components リスト）に**別々に**保存する。pickle 不使用（D-06・Phase 3 CR-04 思想）。
- **load_native_artifact 真正再構築 (Cycle 2 NEW-5)**: 3ステップパイプライン: (a) native base ファイルから base estimator を真正読込 (b) calibrator.joblib から calibrators を読込 (c) base + calibrators から CalibratedClassifierCV を真正再構築。予測の中心は native base から復元した estimator。
- **Cycle 3 NEW-L1**: calibrator.joblib は必須・欠落時 FileNotFoundError で fail-loud。native base 単独での再構築は物理的に不可能（isotonic 閾値/sigmoid 係数が必要・docstring 明記）。
- **Cycle 3 NEW-M1**: scikit-learn==1.9.0 pin を安定性保証。test_artifact_save_load_roundtrip が `np.allclose(rtol=1e-12, atol=1e-12)` で保存前後 predict_proba 一致を検証（pin 破壊で即時 RED）。
- **test_calibrator.py 6件 GREEN**: test_strict_later_disjoint / test_isotonic_vs_sigmoid_threshold / test_reproduce_bit_identical / test_artifact_save_load_roundtrip / test_artifact_calibrator_joblib_required / test_artifact_metadata_json_is_sorted。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Fix] FEATURE_COLUMNS 数「42」→ 実データ値 35 (review HIGH#9 本質の正適用)**
- **Found during:** Task 1 (FEATURE_COLUMNS 導出時)
- **Issue:** PLAN acceptance は `len(FEATURE_COLUMNS) == 42`（RESEARCH 確定の実質 feature 数）を要求。しかし実際の SNAPSHOT (postreview-v2・feature_count=62) では FEATURE_COLUMNS は 35 feature（24 rolling/static + 5 `_code` + 6 静的: barei/sexcd/futan/umaban/wakuban/class_code_normalized）。PLAN の「42」は v3/feature_count=63 時代の旧情報。
- **Fix:** review HIGH#9 の本質（registry から導出した明示的 allowlist）を正適用し、FEATURE_COLUMNS を registry 登録 feature 集合から導出した実データ値 35 とした。acceptance の「42」は旧情報のため実データ値に修正。registry に登録された feature のみを FEATURE_COLUMNS に含め、未登録の meta/key/provenance 列を除外する方針は PLAN の意図と一致。
- **Files modified:** src/model/data.py
- **Commit:** a7068cd

**2. [Rule 1 - Bug] verify_snapshot_sha256 が生ファイル bytes で計算していた (review MEDIUM#6)**
- **Found during:** Task 1 (test_load_from_parquet_only 実行時・SHA256 不一致で RED)
- **Issue:** 初期実装の `verify_snapshot_sha256` は `hashlib.sha256(Path(SNAPSHOT_PATH).read_bytes())` で生ファイル bytes の hash を計算していた。しかし manifest の SHA256 は Phase 3 `snapshot.write_snapshot` が「metadata を除外した Parquet bytes」で計算したもの（`byte_reproducible_scope=parquet_data_only_metadata_excluded` の意味）。生ファイル bytes は schema metadata（snapshot_id/created_at 等の run 毎可変値）を含むため一致しない。
- **Fix:** Phase 3 `snapshot.write_snapshot`（src/features/snapshot.py:221-236）と同一手順で hash 再計算するよう修正: (1) Parquet 読込 (2) metadata 無し schema で base_table 構築 (3) 決定論的書込設定（use_dictionary=False, compression=zstd, write_statistics=True, row_group_size=100_000）で BufferOutputStream に書込 (4) その bytes の SHA256 を計算 → manifest と secrets.compare_digest で比較。
- **Files modified:** src/model/data.py
- **Commit:** a7068cd

## Verification Results

### 自動検証

- `uv run pytest tests/model/test_data.py -x -q`: 4 passed ✓
- `uv run pytest tests/model/test_calibrator.py -x -q`: 6 passed ✓
- `uv run pytest tests/model/test_data.py tests/model/test_calibrator.py -q`: 10 passed ✓
- `uv run pytest --ignore=tests/model -q`: 225 passed (既存テスト回帰なし) ✓
- `uv run pytest tests/model/ -q --ignore=tests/model/test_data.py --ignore=tests/model/test_calibrator.py`: 13 failed (他 model stubs は RED/skip 維持・後続 wave 03/04 で GREEN 化予定) ✓

### acceptance criteria grep 検証

- `def load_feature_matrix()` シグネチャ arity 0 ✓
- `pq.read_table` 呼出 3件 (load_feature_matrix/verify_snapshot_sha256/_derive_feature_columns) ✓
- `assert_matrix_columns_registered` import + 呼出 ✓
- `_RAW_ID_KEPT_COLUMNS` import + RAW_ID_COLUMNS 定義 ✓
- `split_3way` の `raise ValueError` 18件 (完全時系列条件 + 正準 race_key disjoint) ✓
- 7関数分離定義 (load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix/verify_snapshot_sha256/make_race_key + split_3way) ✓
- `from src.utils.calibrator import fit_prefit_calibrator` ✓
- `def fit_prefit_calibrator` が calibrator.py に無い（再実装無し）✓
- `isotonic" if len(X_calib) >= 1000` 切替 ✓
- `os.replace` atomic write 2件 ✓
- pickle 呼出 0件 ✓
- `sort_keys=True` 5件 ✓
- `list(X.columns) == FEATURE_COLUMNS` assert ✓
- `rtol=1e-12, atol=1e-12` 4件 ✓
- FEATURE_COLUMNS count = 35 ✓
- calibrator.joblib FileNotFoundError 8件 ✓

## Known Stubs

本 PLAN は RED stub の GREEN 化が目的の一部。以下は後続 wave で GREEN 化される予定の stub（本 PLAN の完了を阻害しない）:

| File | stubs | GREEN 化する PLAN |
| ---- | ---- | ----------------- |
| tests/model/test_trainer.py | 4 stubs (SC#3 leak diagnostic/has_time/nonneg/eval set) | PLAN 03 |
| tests/model/test_baseline.py | 6 stubs (BL-1..5 / market data source) | PLAN 03 |
| tests/model/test_predict.py | 2 stubs (provenance / model_version numbering) | PLAN 04 |
| tests/model/test_prediction_load.py | 1 stub (@requires_db・idempotent checksum) | PLAN 04 |

## Threat Flags

本 PLAN で作成・変更されたファイルは全て PLAN の `<threat_model>` で管理されている:

- T-04-06 (Information Disclosure: live DB feature 再計算): mitigate・load_feature_matrix が DB 引数 arity 0・pq.read_table のみ
- T-04-07 (Tampering: raw ID 混入): mitigate・RAW_ID_COLUMNS 除外 + unit test assert
- T-04-08 (Tampering: banned feature 混入): mitigate・assert_matrix_columns_registered + banned_features(spec) == []
- T-04-09 (Tampering: race_id train/calib/test 跨ぎ): mitigate・正準 race_key pairwise disjoint raise ValueError + 完全時系列条件 raise ValueError
- T-04-10 (Information Disclosure: calib slice 過去/重複): mitigate・fit_prefit_calibrator 経由 strict-later ValueError guard 継承
- T-04-11 (Tampering: pickle ACE + joblib 依存 + sklearn 私有 API + 物理的不可能 fallback): mitigate・base native + calibrator.joblib 分離保存 + 真正再構築 + calibrator.joblib 必須 + scikit-learn==1.9.0 pin 安定性保証
- T-04-12 (Repudiation: 非決定論的 metadata.json): mitigate・sort_keys=True + atomic write
- T-04-12b (Information Disclosure: fake-green): mitigate・データ API 5関数分離 + 合成 label DataFrame injection
- T-04-12c (Tampering: metadata/label/raw-ID X 混入): mitigate・FEATURE_COLUMNS registry derived allowlist + make_X_y 完全一致 assert

新たなセキュリティ表面の追加は無い。

## Self-Check: PASSED

- FOUND: src/model/__init__.py
- FOUND: src/model/data.py (load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix/make_race_key/verify_snapshot_sha256/split_3way/load_frozen_maps + FEATURE_COLUMNS 定数)
- FOUND: src/model/calibrator.py (calibrate_model + CalibrationResult・fit_prefit_calibrator import)
- FOUND: src/model/artifact.py (save_native_artifact/load_native_artifact/write_metadata_json)
- FOUND: tests/model/test_data.py (4 test GREEN)
- FOUND: tests/model/test_calibrator.py (6 test GREEN)
- FOUND: commit a7068cd (Task 1)
- FOUND: commit 06faf02 (Task 2)
