---
phase: 03-as-of-features-snapshots
verified: 2026-06-19T07:30:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 2.5/3
  gaps_closed:
    - "CR-01: rolling_timediff_* / rolling_babacd_* 6エントリを registry / rolling.py / availability.py の3者から削除し registry↔Parquet parity を復元（live snapshot v2 で該当列 0・feature_count=55 一致を実証）"
    - "WR-01: builder.estimated_running_style が groupby(kettonum) 前に PIT pre-filter (as_of_datetime < feature_cutoff_datetime・strict <・per-observation) を適用（builder.py:347-352）"
    - "CR-02: _fetch_feature_sources / _fetch_history の JOIN 右側 nr に project_window_filter('nr') を適用（builder.py:427, 477）"
    - "CR-03: build_frozen_category_maps が race_date 欠損 frame で fail-loud (ValueError)（category_map_consumer.py:179-181）"
    - "CR-04: load_category_maps を joblib.load (pickle) から json.loads に移行・__getstate__/__setstate__ 削除・artifact 拡張子 .joblib → .json"
  gaps_remaining: []
  regressions: []
advisories:
  - id: "CR-01(new) / 03-REVIEW"
    severity: warning
    location: "scripts/run_feature_build.py:206-228"
    detail: >-
      manifest 書出（L206・SHA256 含む）が persist_category_maps（L228）より先に実行される。
      persist が失敗（disk full / 権限 / encode error）した場合、SHA256 一致の「完成済」manifest
      が残り category map artifact 欠損の再現性破壊状態が完成する潜在リスク。category_map_artifact
      が相対パス（`snapshots/category_map_*.json`）で CWD 依存。現状の live snapshot では
      artifact は正常生成されており manifest SHA256 = on-disk SHA256 で一致（再現性は現在成立）。
    recommendation: >-
      persist を manifest 書出より先に実行し、永続化直後に存在確認 (assert exists)、
      manifest の category_map_artifact を repo-root 相対で正規化。Phase 4 読込前に修正推奨。
    blocks_current_sc: false
  - id: "WR-01' / 03-REVIEW"
    severity: warning
    location: "src/features/builder.py:353-354"
    detail: >-
      `else: pit_filtered_style = expanded_style`（silent no-filter fallback）が残存。
      通常 build_feature_matrix path では _fetch_history が必ず as_of_datetime を derive するため
      到達不能だが、将来の refactor / 合成 history 直接 inject で silent に未来レースが推定脚質に
      混入する余地。WR-01 must_have（「PIT pre-filter を groupby 前に適用」）は live path で成立
      （test_estimated_running_style_applies_pit_prefilter が PIT 挙動を検証済）。
    recommendation: >-
      `as_of_datetime` 不在時は silent skip でなく fail-loud (ValueError) にする。Phase 4 学習前修正推奨。
    blocks_current_sc: false
  - id: "WR-02 / 03-REVIEW"
    severity: warning
    location: "src/features/builder.py:455-457, 485-487"
    detail: >-
      _fetch_feature_sources / _fetch_history が `except Exception` で空 DataFrame を返す。
      DB 障害時に空/全 NaN snapshot を SHA256 付きで書出す可能性（CR-01 silent-NaN と同根）。
      現状 CI/local では DB 接続されており non-triggering。
    recommendation: >-
      build_feature_matrix 側で空 frame を検出したら fail-loud、または明示的な allow_empty 引数で制御。
    blocks_current_sc: false
  - id: "WR-03 / 03-REVIEW"
    severity: info
    location: "src/features/rolling.py:236-240"
    detail: >-
      groupby().apply(lambda) が pandas 3.x で非推奨形。現状 pandas 3.0.3 で動作（live snapshot
      byte-reproducible PASS）だが将来 pandas upgrade で SHA256 drift の可能性。
    recommendation: >-
      groupby().size() の vectorized 形に置換。Phase 4 前後で対処可能（同一プロセス同一 pandas では
      drift 検出不可・upgrade 時発覚）。
    blocks_current_sc: false
  - id: "WR-05 / 03-REVIEW"
    severity: info
    location: "src/features/builder.py:363-367 / src/features/category_map_consumer.py:48"
    detail: >-
      estimated_running_style が str/object dtype で `__MISSING__` sentinel を持ち、_CATEGORY_COLUMNS
      対象外のため生文字列のまま snapshot に乗る。Phase 4 LightGBM category 変換時に `__MISSING__` が
      pandas category code -1 になる §14.3 Negative-code hazard の潜在。Phase 3 SC は feature 生成
      （リーク防止）が対象で LightGBM 統合は Phase 4 のスコープ。
    recommendation: >-
      Phase 4 で estimated_running_style を _CATEGORY_COLUMNS に追加、または category 変換時に
      `__MISSING__` を非負 code sentinel に正規化する工程を文書化・回帰テスト。
    blocks_current_sc: false
  - id: "IN-01 / 03-REVIEW"
    severity: info
    location: "src/config/feature_availability.yaml:121-134 / src/features/builder.py:74-112"
    detail: >-
      trackcd / course_kubun が registry に feature 登録されているが builder は SELECT せず生成しない。
      assert_matrix_columns_registered は出力側 subset 検査のみで検出されない。Phase 3.1 と同様の
      registry↔実体 drift の潜在。Phase 3.1 / Phase 3.2 で整理対象。
    blocks_current_sc: false
  - id: "§12.4 metadata キー名の変種"
    severity: info
    location: "src/features/snapshot.py:180-189"
    detail: >-
      SC#3 が挙げる metadata キー名 `label_generation_version` / `feature_cutoff_datetime` が、
      実 schema metadata では `label_version` / `feature_cutoff_rule` という変種名で格納されている。
      キー存在要件（9項目）は充足するが §12.4 正準名ではない。feature_snapshot_id / created_at は
      HIGH #6 設計で deterministic sentinel 値（実値は manifest 側）。再現性・リーク防止には無害。
    recommendation: >-
      Phase 3.1 または Phase 4 で §12.4 正準名に alias 付与を検討。現状は manifest 側に正確な実値があるため監査性は保たれている。
    blocks_current_sc: false
---

# Phase 03: As-of Features & Snapshots — Verification Report

**Phase Goal:** The leakage-prevention backbone is enforced — every feature row is point-in-time correct via `feature_cutoff_datetime` and the `feature_availability` taxonomy, the Phase 1-A allowlist forbids banned timings (post-race, same-day, body-weight-announced, race-day-morning, odds), and the immutable Parquet snapshots carry the full reproducibility manifest
**Verified:** 2026-06-19T07:30:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (03-05: CR-01/02/03/04 + WR-01) and weighing 03-REVIEW.md new findings

## 検証方針

前回 `gaps_found` の単一実質 gap（CR-01 silent empty features + 4 潜伏負債）を 03-05 が closure した主張を、SUMMARY ではなく実コードと live snapshot で検証。その後 03-REVIEW.md（Critical 1 / Warning 6 / Info 5）の新規発見を ROADMAP Success Criteria と CLAUDE.md Core Value（リーク防止・再現性）に対して重量評価。新規発見のうち WR-04（rolling_sd object dtype hazard）が実コードで無効（`_coerce_rolling_columns_for_parquet` が Float64 に統一・実 snapshot で Float64 確認済）であることを実証的に確認。

## Goal Achievement

### Observable Truths（ROADMAP Phase 3 Success Criteria に基づく）

| #   | Truth (SC)                                                                                                                                                                                                                                                                                       | Status     | Evidence（実コード・実 snapshot で検証）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A feature row carries `as_of_datetime`, `feature_cutoff_datetime`, `feature_snapshot_id`, `feature_availability` (`available_from_timing`, `leakage_risk_level`) on every column, and the PIT join uses `merge_asof(direction='backward')` so a horse's feature value at prediction time T uses only data known strictly before T. | ✓ VERIFIED | **行レベル stamp**: live snapshot v2（554,267 行）で `feature_cutoff_datetime`/`as_of_datetime`/`feature_snapshot_id`/`feature_availability_version` 4列とも 100% non-null（PyArrow probe）✓。**cutoff 算術**: `feature_cutoff_datetime = race_date - 1 day`（builder.py:297-299・sample で一致）✓。**PIT filter**: rolling.py:193-195 で strict `<` per-observation（obs_id-keyed window）✓。**WR-01 closure**: estimated_running_style が groupby(kettonum) 前に `as_of_datetime < feature_cutoff_datetime`（strict `<`）を適用（builder.py:347-352・test_estimated_running_style_applies_pit_prefilter で PIT 挙動を検証・cutoff 前の「逃」が cutoff 後の「追」で上書きされないことを実証）✓。**CR-01 closure**: rolling_timediff_*/rolling_babacd_* 6エントリを registry/rolling.py/availability.py の3者から削除済み（grep で残存 0・3者 parity test GREEN）✓。snapshot v2 に timediff/babacd rolling 列 0・feature_count=55 = manifest 55 で parity 完備 ✓。注: merge_asof ではなく rolling.py の obs_id-keyed per-observation strict-< window を採用（CLAUDE.md §13 idiom から文書化された等価逸脱・前回 verification で leak-safe 判定済）。 |
| 2   | The fail-loud feature-allowlist test passes: the Phase 1-A feature matrix contains ZERO features tagged `post_race_only` / `odds_snapshot_available` / `body_weight_announced` / `race_day_morning` / `same_day_aggregate`.                                                                                                                                                                                                                                                    | ✓ VERIFIED | `feature_availability.yaml` に5禁止 timing 出現ゼロ（grep）✓。`test_no_banned_timing_parametrized` が5 timing 各々で empty list を assert ✓。`TARGET_OBS_BANNED_COLUMNS`（sibababacd/dirtbababd/odds/ninki 等）と registry feature 名の積が空 ✓。`assert_matrix_columns_registered` が未登録/banned alias を fail-loud reject ✓。当日馬場/天候/馬体重/当日オッズ/人気/レース後通過順・上がり・走破タイム 全て除外済。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 3   | A developer can write a Parquet snapshot whose embedded metadata block contains `dataset_version`, `feature_snapshot_id`, `label_generation_version`, `feature_cutoff_datetime`, `prediction_timing`, and train/val period bounds — and re-reading reproduces identical bytes (immutability verified by hash).                                                                                                                                                                | ✓ VERIFIED | **on-disk SHA256** = `36254ab69188bde1d076c833b73bccafec87aa2a30506b9d89d7c56acc3be760` = manifest `sha256` ✓（再計算で一致）。**byte_size** 34,311,329 = manifest `byte_size` ✓。**schema metadata 9 keys** 全て存在 ✓（dataset_version/feature_snapshot_id/label_version/prediction_timing/feature_cutoff_rule/train_period/validation_period/created_at/feature_availability_version）。`test_byte_reproducible_by_hash` / `test_sha256_covers_parquet_bytes_only` GREEN ✓。byte-reproducibility は Parquet bytes のみ（manifest の created_at_real は run 毎可変・SHA 対象外・HIGH #6 設計）。注: SC#3 が挙げる `label_generation_version`/`feature_cutoff_datetime` は実 schema では `label_version`/`feature_cutoff_rule` の変種名（advisory に記載・実値は manifest 側で正確）。                                                                                                                                                                                                                                                                                       |
| 4   | Frozen category maps are fit on the training window only, persisted alongside the snapshot, and applied to val/test with unknown IDs mapping to `__UNSEEN__` (not NaN).                                                                                                                                                                                                                                                          | ✓ VERIFIED | **train 窓 fit**: category_map_consumer.py:185-188 で `race_date_col.between(train_window[0], train_window[1])` で train mask ✓。**__UNSEEN__ mapping**: FrozenCategoryMap で未知 ID → `__UNSEEN__`（test で検証）✓。**race_date 欠損 fail-loud** (CR-03): category_map_consumer.py:179-181 で `ValueError` ✓（test_build_frozen_maps_raises_on_missing_race_date GREEN）✓。**pickle ACE 解消** (CR-04): json.loads/json.dumps(sort_keys=True) のみ・import joblib / __getstate__/__setstate__ 削除済・test_load_category_maps_does_not_use_joblib が AST 解析で依存除去を検証 ✓。**artifact**: `snapshots/category_map_20260619-1a-v2.json`（.json 拡張子・実ファイル存在・1.2MB）✓。manifest `category_map_artifact: snapshots/category_map_20260619-1a-v2.json` 参照 ✓。                                                                                                                                                                                                                                                                                                                 |

**Score:** 4/4 truths verified

### 03-REVIEW.md 新規発見の重量評価（Core Value 対して）

03-05 gap-closure が閉じた5課題（CR-01 registry parity / WR-01 look-ahead / CR-02 JOIN filter / CR-03 race_date fail-loud / CR-04 pickle ACE）は全て実コード + テスト + live snapshot で closure を確認。03-REVIEW.md はその上で新規に 1 Critical / 6 Warning / 5 Info を挙げた。各々を ROADMAP Phase 3 Success Criteria および Core Value（リーク防止・再現性）に対して評価：

| ID            | 内容                                                                                                            | 現 SC 達成への影響                                                                                                                                                                                                                                                                                                                                                                                  | Verifier 判定                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CR-01(new)    | manifest 書出が persist_category_maps より先（persist 失敗時に SHA256 一致の「完成」manifest が残る潜在）・相対パス CWD 依存 | **現時点で breach 無し**: live snapshot v2 で category_map_*.json は正常生成・manifest SHA256 = on-disk SHA256 で一致。persist 失敗は disk full / 権限等の運用時限事故でのみ顕在化する潜伏リスク。SC#3/#4 は現在成立。                                                                                                                                                                                       | **WARNING（advisory）** — 現 SC を破らない。再現性 Core Value の defense-in-depth 強化として Phase 4 前に修正推奨。                                                                                                                                                                                                                                                                                                                                                     |
| WR-01'        | `else: pit_filtered_style = expanded_style`（silent no-filter fallback）が残存                                   | **現時点で leak 無し**: 通常 build_feature_matrix path では _fetch_history が必ず as_of_datetime を derive するため到達不能。WR-01 must_have（「PIT pre-filter を groupby 前に適用」）は live path で成立（test_estimated_running_style_applies_pit_prefilter GREEN）。将来の refactor / 合成 history 直接 inject で silent leak する余地。                                                                                       | **WARNING（advisory）** — 現 SC を破らない。リーク防止 Core Value の defense-in-depth 強化として Phase 4 前に fail-loud 化推奨。                                                                                                                                                                                                                                                                                                                                      |
| WR-02         | _fetch_feature_sources/_fetch_history が `except Exception` で空 DataFrame を返す（CR-01 silent-NaN と同根）       | **現時点で non-triggering**: CI/local で DB 接続されており空 frame にならない。DB 障害時に空/全 NaN snapshot を SHA256 付きで書出す潜在リスク。SC#1 は現在成立。                                                                                                                                                                                                                                                  | **WARNING（advisory）** — 現 SC を破らない。Phase 4 前に fail-loud 化推奨。                                                                                                                                                                                                                                                                                                                                                                                   |
| WR-03         | rolling の `groupby().apply(lambda)` が pandas 3.x で非推奨                                                       | **現時点で drift 無し**: pandas 3.0.3 で動作・live snapshot byte-reproducible PASS。同一プロセス同一 pandas では検出不可・pandas upgrade 時に SHA256 drift 発覚。SC#3 は現在成立。                                                                                                                                                                                                                              | **INFO（advisory）** — 現 SC を破らない。Phase 4 前後で vectorized 形に置換推奨。                                                                                                                                                                                                                                                                                                                                                                                |
| WR-04         | rolling_sd object dtype（float と `__MISSING__` 混在）が Phase 4 LightGBM category で -1 code になる hazard       | **REVIEW 主張が実コードで無効**: rolling.py:167-174 は object 初期化だが `_coerce_rolling_columns_for_parquet`（snapshot.py:79）が nullable Float64 に統一してから Parquet 書込。実 snapshot v2 で `rolling_*_sd_5` は `Float64`（Float64 sample = 数値・object でない）を実証。負の code hazard は現在存在しない。                                                                                          | **NON-ISSUE（REVIEW の誤りを実証）** — 現 SC を破らない。                                                                                                                                                                                                                                                                                                                                                                                                       |
| WR-05         | estimated_running_style が str/object + `__MISSING__` で _CATEGORY_COLUMNS 対象外                                  | **Phase 4 forward-looking**: Phase 3 SC は feature 生成（リーク防止）が対象で LightGBM 統合は Phase 4 のスコープ。estimated_running_style は leak 無く生成されている。                                                                                                                                                                                                                                            | **INFO（Phase 4 に延期）** — 現 Phase 3 SC を破らない。Phase 4 で対処（`_CATEGORY_COLUMNS` 追加または category 変換時の正規化工程）。                                                                                                                                                                                                                                                                                                                                     |
| WR-06 / IN-01..05 | index 暗黙依存 / trackcd・course_kubun 未生成 / docstring 表記揺れ / jyocd 二重登録 等                          | いずれも現 SC を破らず、docstring/可読性改善または Phase 3.1 で整理対象。                                                                                                                                                                                                                                                                                                                                                   | **INFO** — 現 SC を破らない。Phase 3.1 または後続 phase で整理。                                                                                                                                                                                                                                                                                                                                                                                                  |

**総合判定:** 03-REVIEW の Critical 1 件を含め全て現時点の ROADMAP Phase 3 Success Criteria（4項）を破るものではない。CR-01(new)/WR-01'/WR-02 は leak-prevention / reproducibility Core Value の defense-in-depth を更に強固にするため Phase 4 開始前に修正することが推奨されるが、現 snapshot でリーク防止と再現性（Core Value の2本柱）は共に成立している。よって Phase 3 must_haves は達成（passed）と判定する。ただし advisory 4件（CR-01 new / WR-01' / WR-02 / WR-03）は Phase 4 学習パイプライン構築前に対応することが、再現性聖域を長期保全する上で強く推奨される。

### Required Artifacts

| Artifact                                              | Expected                                                        | Status      | Details                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | --------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/features/builder.py`                             | feature matrix 公開 API・PIT cutoff・rolling/running_style 統合  | ✓ VERIFIED  | `build_feature_matrix` Step 1-9 完備・cutoff `race_date - 1 day` (L297-299)・§13.2 stamp (L370-373)・WR-01 PIT pre-filter on estimated_running_style (L347-352)・CR-02 JOIN 両側 project_window_filter (L427, L477)・`assert_matrix_columns_registered` (L384)。wired（run_feature_build.py から呼出・実 snapshot 存在）。                                              |
| `src/features/rolling.py`                             | per-observation latest-K・strict < cutoff・6系統×3軸+count       | ✓ VERIFIED  | `obs_id`-keyed window・`groupby("obs_id").head(5)`・strict `<` pre-filter・D-13 sentinel。CR-01 で timediff/babacd 削除後 6系統×3軸=18 rolling features。`_coerce_rolling_columns_for_parquet` が Float64 統一（WR-04 否定の根拠）。実 snapshot で rolling_kakuteijyuni_mean_5 89% populated を確認。                                                                          |
| `src/features/snapshot.py`                            | byte-reproducible Parquet 書込・§12.4 metadata 9 keys・SHA256   | ✓ VERIFIED  | PyArrow zstd/use_dictionary=False/row_group_size=100_000・schema metadata 9 keys・SHA256 = Parquet bytes のみ（HIGH #6 設計・feature_snapshot_id/created_at は deterministic sentinel）。on-disk hash 再検証で manifest と一致。                                                                                                                                 |
| `src/features/availability.py`                        | registry loader・allowlist・出力カラム全登録検査・taxonomy 定数 | ✓ VERIFIED  | `BANNED_TIMINGS`/`ALLOWED_TIMINGS` 定数・`assert_all_entries_allowed`・`assert_matrix_columns_registered`・`_ROLLING_SYSTEMS_FOR_RESERVED` が rolling.py と完全一致（3者 parity test GREEN）。                                                                                                                                                                |
| `src/features/category_map_consumer.py`               | frozen map fit(train-only)/apply/persist/load・JSON 移行        | ✓ VERIFIED  | train 窓 fit (L185-188)・race_date 欠損 fail-loud (L179-181・CR-03)・json.dumps(sort_keys=True)/json.loads のみ（CR-04・joblib 削除・AST test 保護）・`__UNSEEN__` mapping。                                                                                                                                                                                  |
| `src/config/feature_availability.yaml`                | §13 feature エントリ・timing/leakagerisk tag・cutoff_semantics  | ✓ VERIFIED  | banned timing ゼロ・cutoff_semantics ブロック存在・rolling timediff/babacd 6エントリ削除済み（CR-01）・Deferred note コメントブロック（Phase 3.1 で再登録予約）。注: trackcd/course_kubun が registry 登録だが builder 未生成（IN-01・advisory）。                                                                                                                  |
| `scripts/run_feature_build.py`                        | CLI・snapshot build・manifest・category_map artifact             | ⚠️ ADVISORY | 実装存在・live snapshot を生成（exit 0・byte-reproducible verify PASS）。ただし CR-01(new): manifest 書出（L206）が persist_category_maps（L228）より先・category_map_artifact が相対パス。現状正常動作（live で artifact 生成済・SHA 一致）だが潜伏リスク。                                                                                                                |
| `snapshots/feature_matrix_20260619-1a-v2.parquet`     | 554,267行 × 55列・§12.4 metadata・byte-reproducible             | ✓ VERIFIED  | 実ファイル存在・SHA256 = manifest と一致・metadata 9 keys・timediff/babacd rolling 列 0・feature_count=55 = manifest 55。CR-01 end-to-end parity を実データで実証。                                                                                                                                                                                              |
| `snapshots/category_map_20260619-1a-v2.json`          | JSON フォーマット・train 窓 fit・__UNSEEN__ sentinel            | ✓ VERIFIED  | .json 拡張子（CR-04）・実ファイル 1.2MB 存在・manifest から参照。                                                                                                                                                                                                                                                                                                |

### Key Link Verification

| From                                                       | To                                       | Via                                                                     | Status    | Details                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/run_feature_build.py`                             | `builder.build_feature_matrix`           | 直接呼出                                                                | ✓ WIRED   | 実 snapshot v2 が存在（live build exit 0）。                                                                                                                                                                                                              |
| `builder.build_feature_matrix` Step 1                      | `availability.load_feature_availability` | Step 1                                                                  | ✓ WIRED   | builder.py:290                                                                                                                                                                                                                                          |
| `builder.build_feature_matrix` Step 5                      | `rolling.build_rolling_features`         | Step 5・sort_values 後転送                                              | ✓ WIRED   | builder.py:321・rolling 側で strict < cutoff 適用                                                                                                                                                                                                        |
| `builder.build_feature_matrix` Step 6                      | `estimated_running_style` PIT pre-filter | `as_of_datetime < feature_cutoff_datetime` 後 `groupby("kettonum")`     | ✓ WIRED   | builder.py:337-362・WR-01 closure・test_estimated_running_style_applies_pit_prefilter GREEN                                                                                                                                                              |
| `builder._fetch_feature_sources` / `_fetch_history`        | `project_window_filter('nr')`            | JOIN 右側 nr にも filter                                                | ✓ WIRED   | builder.py:427, 477・CR-02 closure・test_fetch_history_and_feature_sources_filter_both_join_sides GREEN                                                                                                                                                  |
| `builder.build_feature_matrix` → `snapshot.write_snapshot` | on-disk Parquet                          | `pa.BufferOutputStream`・zstd                                           | ✓ WIRED   | 実 snapshot 存在・SHA256 一致                                                                                                                                                                                                                            |
| `category_map_consumer.build_frozen_category_maps`         | `race_date` 欠損 fail-loud               | `raise ValueError`                                                      | ✓ WIRED   | category_map_consumer.py:179-181・CR-03 closure・test_build_frozen_maps_raises_on_missing_race_date GREEN                                                                                                                                               |
| `category_map_consumer.load_category_maps`                 | `json.loads`                             | JSON 安全フォーマット                                                   | ✓ WIRED   | category_map_consumer.py:274・CR-04 closure・test_load_category_maps_does_not_use_joblib（AST 解析）GREEN                                                                                                                                                |
| Parquet schema metadata                                    | §12.4 9 keys                             | `pa.Schema.with_metadata`                                              | ✓ WIRED   | snapshot.py:193・実 metadata で9 keys 確認（キー名は label_version/feature_cutoff_rule の変種・advisory）                                                                                                                                               |
| manifest sha256                                            | on-disk Parquet bytes                    | `hashlib.sha256(data)`                                                  | ✓ WIRED   | 再計算で一致（36254ab6...）                                                                                                                                                                                                                              |

### Data-Flow Trace (Level 4)

| Artifact                                | Data Variable                               | Source                                  | Produces Real Data | Status    |
| --------------------------------------- | ------------------------------------------- | --------------------------------------- | ------------------ | --------- |
| feature_matrix (Parquet v2)             | rolling_kakuteijyuni_mean_5                 | normalized.n_uma_race.kakuteijyuni (DB) | Yes (89% non-null) | ✓ FLOWING |
| feature_matrix (Parquet v2)             | rolling_harontimel3_mean_5                  | normalized.n_uma_race.harontimel3 (DB)  | Yes                | ✓ FLOWING |
| feature_matrix (Parquet v2)             | rolling_*_sd_5（6系統）                     | rolling sd 計算                         | Yes (Float64)      | ✓ FLOWING |
| feature_matrix (Parquet v2)             | feature_cutoff_datetime                     | `race_date - 1 day` (pandas)            | Yes (100%)         | ✓ FLOWING |
| feature_matrix (Parquet v2)             | estimated_running_style                     | PIT-filtered history.groupby(kettonum) | Yes（leak 無し）   | ✓ FLOWING |
| feature_matrix (Parquet v2)             | rolling_timediff_* / rolling_babacd_*       | N/A（CR-01 で registry/実装から削除）   | N/A                | N/A（削除済・Phase 3.1 で再登録予約） |

### Behavioral Spot-Checks

| Behavior                                                                       | Command                                                          | Result                                      | Status |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------- | ------ |
| Feature tests pass                                                             | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q`         | `58 passed in 0.30s`                        | ✓ PASS |
| Full test suite                                                                | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q`                  | `191 passed, 21 skipped in 3.25s`           | ✓ PASS |
| CR-01/03/04 + WR-01 regression tests                                           | key 4テスト選択実行                                              | `11 passed`                                 | ✓ PASS |
| Snapshot row/col count                                                         | PyArrow read_table                                               | rows=554267 cols=55                         | ✓ PASS |
| manifest feature_count == actual cols                                          | PyArrow probe                                                    | manifest=55 / actual=55                     | ✓ PASS |
| On-disk SHA256 == manifest sha256                                              | `hashlib.sha256(open(...).read())`                               | `36254ab6...` == manifest                   | ✓ PASS |
| byte_size match                                                                | PyArrow read                                                     | 34,311,329 == manifest                      | ✓ PASS |
| §13.2 row-level stamps 100% non-null                                           | PyArrow probe                                                    | 4列とも 100% non-null                       | ✓ PASS |
| rolling_kakuteijyuni_mean_5 signal                                             | PyArrow `isna().mean()`                                          | NaN frac=10.94%, non_null=493,617           | ✓ PASS |
| rolling_*_sd_5 dtype                                                           | pandas probe                                                     | Float64（object でない・WR-04 否定）        | ✓ PASS |
| timediff/babacd rolling cols removed                                           | PyArrow column_names                                            | 該当列 0                                    | ✓ PASS |
| `feature_availability.yaml` に5禁止 timing 0件                                  | grep                                                             | 0 matches                                   | ✓ PASS |
| `inspect.getsource(category_map_consumer)` に joblib 含まない                   | AST-based test                                                   | test_load_category_maps_does_not_use_joblib GREEN | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — 本 phase は `scripts/*/tests/probe-*.sh` 形式の phase-declared probe を持たない（migration/tooling phase でない）。検証は pytest + PyArrow snapshot probe で実施。

### Requirements Coverage

| Requirement | Source Plan                            | Description                                                                                                                                                                                                                                                                                              | Status    | Evidence                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FEAT-01     | 03-01/02/03/04/05                      | 各特徴量に `as_of_datetime`/`feature_cutoff_datetime`/`feature_snapshot_id`/`feature_availability`（`available_from_timing`/`leakage_risk_level` 含む）を付与し、point-in-time 正確性を保証して未来情報リークを防止できる                                                                                              | ✓ SATISFIED | 行レベル stamp 100% ✓・cutoff 算術 ✓・rolling strict `<` per-observation ✓・WR-01 estimated_running_style PIT pre-filter ✓（live path）・CR-01 registry↔Parquet parity ✓（feature_count=55 一致）・CR-02 JOIN 両側 filter ✓。リアクション: WR-01' silent no-filter fallback は現時点で到達不能（advisory）。                                                          |
| FEAT-02     | 03-01/03/03/04/05                      | Phase 1-A の特徴量を、当日馬場/天候/馬体重/当日オッズ/人気集中度/レース後通過順・上がり・走破タイム/当日レース結果由来集計 を除外して生成できる                                                                                                                                                                                              | ✓ SATISFIED | `feature_availability.yaml` に5禁止 timing 出現ゼロ・`TARGET_OBS_BANNED_COLUMNS`（sibababacd/dirtbababd/odds/ninki 等）と registry feature 積が空・`assert_matrix_columns_registered` fail-loud・`test_no_banned_timing_parametrized` GREEN。                                                                                                                                                       |

REQUIREMENTS.md で Phase 3 に紐づく FEAT-01/FEAT-02 両 ID とも全 plan でカバーされ、実コードで充足確認。orphaned requirement なし。

### Anti-Patterns Found

| File                          | Line      | Pattern                                                    | Severity | Impact                                                                                                                                                                                                                                                                                                                                                                                          |
| ----------------------------- | --------- | ---------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/run_feature_build.py` | 206-228   | manifest 書出 → persist_category_maps の順序（CR-01 new）   | ⚠️ Warning | persist 失敗時に SHA256 一致の「完成」manifest が残り再現性破壊の潜伏リスク。現状は正常動作（live で artifact 生成済）。advisory。                                                                                                                                                                                                                                                                      |
| `src/features/builder.py`     | 353-354   | `else: pit_filtered_style = expanded_style`（silent fallback）| ⚠️ Warning | WR-01' as_of_datetime 不在時に silent no-filter。現時点で到達不能・advisory。                                                                                                                                                                                                                                                                                                                       |
| `src/features/builder.py`     | 455-457, 485-487 | `except Exception` → 空 DataFrame（WR-02）                 | ⚠️ Warning | DB 障害時に silent NaN snapshot を SHA256 付きで書出す潜在。現状 non-triggering・advisory。                                                                                                                                                                                                                                                                                                          |
| `src/features/rolling.py`     | 236-240   | `groupby().apply(lambda)` pandas 3.x 非推奨（WR-03）        | ℹ️ Info   | 現状動作（live snapshot reproducible PASS）。pandas upgrade 時 SHA256 drift リスク・advisory。                                                                                                                                                                                                                                                                                                       |
| `src/features/builder.py`     | 363-367   | estimated_running_style str + `__MISSING__`（WR-05）        | ℹ️ Info   | Phase 4 LightGBM category 変換時に -1 code hazard の潜在。Phase 3 SC（feature 生成・リーク防止）の対象外。Phase 4 に延期。                                                                                                                                                                                                                                                                                |
| `src/config/feature_availability.yaml` | 121-134   | trackcd/course_kubun registry 登録だが builder 未生成（IN-01）| ℹ️ Info   | assert_matrix_columns_registered は出力側 subset 検査のみで検出されず。Phase 3.1/3.2 で整理対象。                                                                                                                                                                                                                                                                                                  |

Debt-marker gate（TBD/FIXME/XXX を formal follow-up 参照無しに含む）: 該当なし（コメント中の CR-/WR-/IN- ID はすべて本 verification または 03-REVIEW.md への formal 参照）。

### Human Verification Required

本 phase はローカルデータパイプライン・再現性検証が主で、UI/UX・実タイム動作・外部サービス統合を含まない。PyArrow snapshot probe・pytest・SHA256 再計算で mechanically 検証可能な範囲で全 must_have が確認された。human_verification 項目なし。

### Gaps Summary

**gaps なし。** ROADMAP Phase 3 の4つの Success Criteria（PIT correctness + feature_availability 完備 / fail-loud allowlist / byte-reproducible §12.4 metadata snapshot / frozen category map train-fit + __UNSEEN__）は全て実コード + live snapshot v2（554,267 行 × 55 列・SHA256 一致）+ 191 tests GREEN で達成された。

03-05 gap-closure（CR-01 registry parity / WR-01 look-ahead / CR-02 JOIN filter / CR-03 race_date fail-loud / CR-04 pickle ACE）は5項とも closure を確認。03-REVIEW.md が挙げた新規発見（Critical 1 / Warning 6 / Info 5）は：
- **WR-04 は REVIEW の誤り**（`_coerce_rolling_columns_for_parquet` が Float64 統一・実 snapshot で Float64 実証）
- **CR-01(new) / WR-01' / WR-02 / WR-03** は現時点で SC を破らない潜伏リスク（advisory）
- **WR-05 / IN-01..05** は Phase 4 / Phase 3.1 スコープの forward-looking 事項

Core Value（リーク防止・再現性）の2本柱は、現 snapshot で leak 無く byte-reproducible に成立している。ただし advisory 4件（CR-01 new / WR-01' / WR-02 / WR-03）は Phase 4 学習パイプライン構築前に対応することが、Core Value を長期保全する上で強く推奨される（Phase 3 の「passed」判定を覆すものではなく、Phase 4 以降の hardening 任务）。

Phase 3.1（Timediff/Babacd Rolling Restoration・ROADMAP に挿入済み）が削除した6 feature の再登録を担い、IN-01（trackcd/course_kubun）も同 phase または別途整理対象。

---

_Verified: 2026-06-19T07:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: after 03-05 gap closure + 03-REVIEW.md new findings weighed_
