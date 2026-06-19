---
phase: 03-as-of-features-snapshots
fixed_at: 2026-06-20T00:00:00Z
review_path: .planning/phases/03-as-of-features-snapshots/03-REVIEW.md
iteration: 1
findings_in_scope: 15
fixed: 14
skipped: 0
wontfix: 1
status: partial
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-06-20T00:00:00Z
**Source review:** `.planning/phases/03-as-of-features-snapshots/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (critical_warning): 15（Critical 4 + Warning 11）
- Fixed: 14
- Skipped: 0
- Wontfix (ユーザー判断): 1（CR-03）
- Info 6件（IN-01〜IN-06）は fix_scope=critical_warning のため対象外。IN-01（3重定義）は
  CR-02 修正時に registry↔rolling.py↔availability.py の parity を `test_registry_rolling_systems_match_rolling_impl`
  で機械保証する形で整合済み。IN-03（created_at 引数の役割明確化）は CR-04 修正時に
  `created_at` → `created_at_fixed` rename で対応済み。

**テスト結果:**
- `uv run pytest tests/features/ tests/test_label_race_date_backfill.py -q`: **78 passed / 1 failed**
- 1件の失敗 (`test_backfill_live_db`) は live-DB 必須の pre-existing 失敗（環境変数未設定・
  pydantic ValidationError）。本修正の対象外・修正前から存在する失敗。

## Fixed Issues

### CR-01: rolling 統合での行順不整合による silent row-misalignment（データ破損）

**Files modified:** `src/features/builder.py`, `tests/features/test_builder.py`
**Commit:** `cc5e3a0`
**Applied fix:** rolling 統合ブロック（Step 5）を位置ベース `axis=1` concat から
canonical key（`race_nkey`, `kettonum`・または `obs_id`）での明示的 `merge` に変更。
`build_rolling_features` 内部で `sort_values("feature_cutoff_datetime")` されるため、
返却 DataFrame の行順が feature_matrix と一致する保証が無く、旧実装は rolling 値を別の
observation に割当てる silent バグがあった。merge_keys が無い場合は RuntimeError で
fail-loud する防御層を追加。回帰テスト `test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs`
を追加（異なる cutoff を持つ複数 observation で rolling 値が正しい馬に対応付けられることを検証）。
**Status:** fixed: requires human verification（論理バグ修正のため手動確認を推奨）

### CR-02: rolling_jyocd がカテゴリカル競馬場コードを数値集計する意味論的バグ

**Files modified:** `src/features/rolling.py`, `src/config/feature_availability.yaml`,
`tests/features/test_builder.py`, `tests/features/test_rolling.py`
**Commit:** `43bd81f`
**Applied fix:** `jyocd`（JRA 競馬場コード varchar(2)）を categorical 系統として扱い、
`rolling_jyocd_mean_5` / `rolling_jyocd_sd_5` を廃止して `rolling_jyocd_mode_5`（過去5走の
最頻値）に変更。`rolling_jyocd_latest_5`（直近の競馬場）は意味論的に妥当なので保持。
rolling.py に `_CATEGORICAL_SYSTEMS` / `_axes_for(system)` を導入し categorical 系統は
`mode/latest/count` 軸、numeric 系統は従来通り `mean/latest/sd/count` 軸を出力。
registry↔rolling.py↔availability.py の 3者 parity テストを categorical 系統（mode_5）も
取り込んだ形に更新。jyocd mode 集計の値検証テスト `test_jyocd_categorical_mode_aggregation` を追加。
IN-01（3重定義）の整合は parity テスト強化で対応。当日 jyocd（静的属性）は別エントリのため変更せず。

### CR-04: Parquet schema metadata の feature_snapshot_id が sentinel で埋められ §12.4 監査証跡が消失

**Files modified:** `src/features/snapshot.py`, `scripts/run_feature_build.py`,
`tests/features/test_snapshot_repro.py`
**Commit:** `bfaa20d`
**Applied fix:** REVIEW.md Fix 案の選択肢1（推奨）を採用。SHA256 計算を metadata 無し schema bytes
で行い、その後 schema metadata（実際の `snapshot_id` と `created_at_fixed` 引数を含む）を付与して
Parquet bytes を書込む。これにより (a) SHA256 は「データ内容のみ」に依存して byte-reproducible が
維持、(b) Parquet ファイル単体から snapshot_id/created_at を復元可能になり §12.4 監査証跡が復元。
`_DETERMINISTIC_CREATED_AT` sentinel 定数を廃止。IN-03（created_at 引数の役割明確化）として
`created_at` 引数を `created_at_fixed` に rename し docstring を整備。呼出側
（`scripts/run_feature_build.py`, `test_snapshot_repro.py`）の引数名を更新。
回帰テスト `test_cr04_parquet_metadata_embeds_real_snapshot_id_and_created_at` と
`test_cr04_sha256_independent_of_snapshot_id` を追加。

### WR-01: _fetch_feature_sources / _fetch_history が except Exception で全例外を握り潰し

**Files modified:** `src/features/builder.py`
**Commit:** `137395d`
**Applied fix:** 両関数の `except Exception` を `psycopg.errors.OperationalError` /
`InterfaceError` / `ConnectionError` のみに限定。DB 接続関連例外は空 frame フォールバック
（unit test / 本番 DB 一時障害）。想定外例外（MemoryError / RuntimeError / ProgrammingError 等）は
re-raise して WR-02 fail-loud に伝播。`import psycopg.errors` を追加。

### WR-02: days_since_prev が全 history で計算されるが rolling の PIT フィルタ後に再計算されない

**Files modified:** `src/features/builder.py`
**Commit:** `137395d`
**Applied fix:** docstring / コードコメントで「days_since_prev は全 history 上の前走（window 外含む）
からの日数であり rolling window 内で再計算されるものではない」ことを明記。リークではなく定義上の
挙動（PIT filter 適用後も各 history 行の「前走日数」として意味は保つ）。

### WR-03: estimated_running_style の groupby が kettonum 単位で cross-observation leak の再発リスク

**Files modified:** `src/features/builder.py`, `src/features/availability.py`
**Commit:** `e7c0e1b`
**Applied fix:** Step 6 推定脚質の groupby を `kettonum` 単位から `obs_id` 単位に変更
（rolling と対称・CR-01 merge_keys 整合）。同一 horse が複数 observation に現れる場合の
cross-obs leak 再発を防止。`obs_id` 列が無ければ rolling と同一 idiom で生成。
`_RESERVED_NON_FEATURE_COLUMNS` に `obs_id` を追加（feature でない中間 key・HIGH #3 検査対象外）。
**Status:** fixed: requires human verification（cross-obs leak は実データで稀なため手動確認を推奨）

### WR-04: feature_availability.yaml の available_from_timing 値が entry/post_position を混在させるが個別検査が無い

**Files modified:** `src/features/builder.py`, `src/features/availability.py`,
`tests/features/test_allowlist.py`
**Commit:** `5f77fdf`
**Applied fix:** `PREDICTION_TIMING_ALLOWED` mapping と `assert_features_allowed_for_prediction_timing`
検査関数を追加。builder Step 1 で `assert_features_allowed_for_prediction_timing(spec, "1A")` を呼出し、
registry 全 feature が 1A 許可集合内にあることを fail-loud 検査。CR-03 wontfix 制約下で
1-A = 「出馬表・馬番・枠番確定後」（要件 §8.1/§13.4/§13.5）のため 1A は entry_confirmed +
post_position_confirmed 両方を許可（futan/jockey_id/umaban/wakuban は 1-A 利用可能・新規
1A_BANNED_TIMINGS で弾く変更は行わない）。回帰テスト3件（1A 許可・未知 timing reject・
不許可 timing reject）を追加。

### WR-05: as_of_datetime が naive datetime で timezone 考慮がない

**Files modified:** `src/features/builder.py`
**Commit:** `c6e461d`
**Applied fix:** naive 運用を明記（JRA データは全て JST であり same-day 同一 JST midnight 境界で
実害軽微・将来マルチタイムゾーン混入時は tz_localize 適用が必要）。コードコメントで
CUTOFF_SEMANTICS["timezone"]="Asia/Tokyo" 宣言と naive 実装の関係を文書化。

### WR-06: test_wr01_prime_raises_on_missing_as_of_datetime が KeyError 受け入れで検証を弱体化

**Files modified:** `src/features/builder.py`, `tests/features/test_builder.py`
**Commit:** `c6e461d`
**Applied fix:** `build_rolling_features` 薄ラッパで `history.sort_values("as_of_datetime")` が
`KeyError` を raise するのを事前チェックで `ValueError` に wrap（PIT filter 適用不可を明示化）。
テストの `pytest.raises((ValueError, KeyError))` を `pytest.raises(ValueError, match="as_of_datetime")`
に絞り regression 検出感度を向上。

### WR-07: backfill idempotent verify がスクリプト全体での raw 不変性を検証しない

**Files modified:** `scripts/run_label_race_date_backfill.py`
**Commit:** `d727422`
**Applied fix:** main の try ブロック冒頭で raw fingerprint（`compute_raw_fingerprint`）を取得し、
backfill 2回実行後に再度取得して両者が一致することを assert。各 backfill run 内部の before/after
比較に加え、1回目と2回目の間に別プロセスが raw を変更した場合を検出するスクリプト全体の二重保護を追加。

### WR-08: estimate_running_style_batch が前方参照型アノテーションを持ち dead code

**Files modified:** `src/features/running_style.py`
**Commit:** `d727422`
**Applied fix:** `estimate_running_style_batch` を削除（YAGNI）。builder.py は
`estimate_running_style` のみを使用しており呼出されていなかった。module top-level に
`import pandas as pd` が無い状態で戻り値型 `pd.Series` を前方参照していた問題（`# noqa: F821` で
黙らせていた・type checker は黙らない）も解消。削除理由をコメントで明記。

### WR-09: _construct_derived_columns の days_since_prev 再代入が index の再整列に依存し壊れやすい

**Files modified:** `src/features/builder.py`
**Commit:** `137395d`
**Applied fix:** `reset_index(drop=True)` してから計算し、元の index に戻す堅牢化。
壊れやすい `rd.loc[ordered.index]` lookup を廃止し、`_rd_dt` 補助列 + `sort_index()` で
元の順序に復元。重複 index 混入時の alignment エラーを防止。

### WR-10: persist_category_maps が atomic write でなく partial JSON を残す可能性

**Files modified:** `src/features/category_map_consumer.py`
**Commit:** `05b35e8`
**Applied fix:** `tmp file + os.replace` の atomic write に変更。`Path.write_text` は atomic でなく、
書込中のプロセス kill / disk full / 権限エラーで partial / 空 / 破損 JSON が残るリスクがあった。
tmp file（同一 filesystem 上・`.tmp` suffix）に書いてから atomic rename することで partial-failure
を抑止（CR-01新・Pitfall 5 の意図と整合）。

### WR-11: _LABEL_INSERT_COLUMNS の private API 跨 module 参照 + staging 再利用時の schema drift リスク

**Files modified:** `src/etl/label_race_date_backfill.py`, `src/etl/fukusho_label.py`,
`tests/test_label_race_date_backfill.py`
**Commit:** `05b35e8`
**Applied fix:** (a) `_LABEL_INSERT_COLUMNS` を public の `LABEL_INSERT_COLUMNS` に昇格
（private prefix を外す・後方互換 alias として `_LABEL_INSERT_COLUMNS = LABEL_INSERT_COLUMNS` を残す）。
`label_race_date_backfill.py` の import と参照を public 名に更新。(b) staging 作成を
`CREATE TABLE IF NOT EXISTS` から `DROP TABLE IF EXISTS` → `CREATE TABLE` に変更し常に新規作成
（fukusho_label 側で列追加された際の schema drift を防止・TRUNCATE は不要）。
`test_backfill_rowcount_verify` の「DROP TABLE が含まれてはいけない」検査を「本体 swap 用の
DROP TABLE（staging でない）が含まれてはいけない」に修正（staging 準備用の DROP は許可）。

## Skipped Issues

None — すべての in-scope finding が fixed または wontfix 扱い。

## Wontfix Issues（ユーザー判断・要件に基づく）

### CR-03: post_position_confirmed timing feature が 1-A 出力に無条件混入するリーク経路

**File:** `src/config/feature_availability.yaml`, `src/features/builder.py`, `src/features/availability.py`
**Reason:** ユーザー判断により wontfix（絶対修正しない）。実装は要件通り正しく、リークではない。

理由の詳細:
- 要件 §8.1/§8.2 で Phase 1-A =「出馬表・馬番・枠番確定後」と定義されている。
  出馬表確定後 と 馬番・枠番確定後 は JRA 運用上は木曜枠番確定で前日には確定済み（同一タイミング）。
- §13.4 禁止リストに馬番・枠番は含まれない。
- §13.5 で斤量・騎手・馬番・枠番・競馬場が Phase 1-A 利用可能と明記されている。
- `futan` / `jockey_id` / `umaban` / `wakuban` を 1-A から除外すると要件違反 + 重要予測因子の喪失になる。
- WR-04 修正で prediction_timing×timing 整合性検査を強化したが、1A は entry+post_position 両方を
  許可する設計（CR-03 wontfix 制約）としたため、本事項に起因するコード変更は一切行っていない。

**Original issue:** feature_availability.yaml が Phase 1-A 許可タイミングとして
{entry_confirmed, post_position_confirmed} を許可し、futan/jockey_id/umaban/wakuban が
post_position_confirmed 登録だが、feature_cutoff_datetime = race_date - 1 day の PIT 不変条件が
各 feature の available_from_timing と個別に照合されない可能性が指摘された。要件解釈の結果、
本事項はリークでないと判断された。

---

_Fixed: 2026-06-20T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
