---
phase: quick
plan: 260625-h1g
subsystem: etl/label
tags: [label, race_date, fail-loud, silent-corruption, leak-prevention]
requires:
  - "Phase 2 label ETL（compute_fukusho_labels / run_label_etl / _idempotent_load_label）"
  - "src/etl/fukusho_label.py の既存 race_df merge ロジック（行631-647）"
provides:
  - "compute_fukusho_labels の race_date 伝播失敗 fail-loud + 診断ログ"
  - "run_label_etl の staging-swap 後 race_date NULL post-condition（二重防波堤）"
  - "race_date 伝播失敗ケースの回帰テスト（空 race_df / race_date 列欠損 / 正常ケース / post-condition 構造検査）"
affects:
  - "src/etl/fukusho_label.py::compute_fukusho_labels（race_df merge 後の fail-loud ブロック）"
  - "src/etl/fukusho_label.py::run_label_etl（_idempotent_load_label 後の post-condition）"
  - "tests/test_fukusho_label.py（_build_label_input_df デフォルト race_date 付与・3+1 新規回帰テスト）"
tech-stack:
  added: []
  patterns:
    - "fail-loud: silent corruption を RuntimeError で即停止（pd.NA fallback 削除）"
    - "二重防波堤: compute_fukusho_labels（第一）+ run_label_etl post-condition（第二）"
    - "診断ログ: 再発時の原因特定を可能にする race_df/merged 状態の詳細ログ出力"
key-files:
  created: []
  modified:
    - "src/etl/fukusho_label.py"
    - "tests/test_fukusho_label.py"
decisions:
  - "pd.NA fallback を fail-loud に置換（silent corruption 構造的防止）"
  - "_build_label_input_df デフォルトに race_date を付与（既存テスト群の正常ケース GREEN 維持）"
  - "post-condition を _idempotent_load_label 直後・checksum 計算前に配置（staging-swap 完了後の実表を検査）"
  - "根本原因（race_key 型不整合）の修正は本 plan のスコープ外・別 quick task で対応"
metrics:
  duration: "約45分"
  completed: "2026-06-25"
  tasks_total: 3
  tasks_completed: 3
status: complete
---

# Quick 260625-h1g: label.fukusho_label.race_date 全行 NULL fail-loud + 診断ログ化 Summary

label.fukusho_labels.race_date 全行 NULL の silent corruption 再発（2026-06-23/06-24 の2回）を構造的に防止する fail-loud + 診断ログ + 二重防波堤を実装し、live-DB 検証で根本原因（race_key 型不整合）を特定した。

## What Was Built

### Task 1: compute_fukusho_labels の race_date fail-loud + 診断ログ化

- `src/etl/fukusho_label.py:645-679`: 行646-647 の `if "race_date" not in merged.columns: merged["race_date"] = pd.NA` fallback を fail-loud ブロックに置換。
- merge 後 `race_date` 列が無い、または NULL が1行でもある場合、`logger.error` で診断情報（race_df 側: 行数・race_date 列有無・non-NULL 数／merged 側: 行数・race_date 列有無・NULL 数・non-NULL 数／race_df空フラグ／原因候補）を出力し `RuntimeError` を raise。
- 正常ケース（race_date 全行 non-NULL）は挙動不变・logger.error 未発火・checksum 同一。

### Task 2: run_label_etl の post-condition 二重防波堤

- `src/etl/fukusho_label.py:1186-1213`: `_idempotent_load_label` の staging-swap（DROP+RENAME）完了後・checksum 計算前に `SELECT count(*) FROM label.fukusho_label WHERE race_date IS NULL` を実行。
- `null_count > 0` の場合、`logger.error` で「post-condition violation: race_date NULL {null_count} / {rows_inserted} rows」を出力し `RuntimeError` を raise（トランザクションは commit されず rollback）。
- `null_count == 0` は挙動不变（rows_inserted/checksum/raw_touched は一切変更なし）。
- compute_fukusho_labels の fail-loud を抜けた場合（INSERT/staging-swap で race_date が欠損した等の異常）の最終検知。

### Task 3: live-DB 検証で根本原因（race_key 型不整合）を特定

- `uv run python scripts/run_label_etl.py` で fail-loud が発火（PLAN の目的「再発時に原因を記録して特定する仕組み」の成功）。
- 診断ログから race_df 側は正常（rows=39593, race_date列=True, nonnull=39593）、merged 側は全行 NULL（rows=554267, null=554267）と判明 → race_key 型不整合が原因と特定。

## Verification Results

1. **KEIBA_SKIP_DB_TESTS=1 で unit test**: 45 passed（DB 不要テスト全体 GREEN）。
2. **DB 必須テスト含む全体**: 45 passed（DB 接続確認済み）。
3. **ruff check src/etl/fukusho_label.py**: All checks passed（src は完全クリーン）。
4. **ruff check tests/test_fukusho_label.py**: 18 errors（全て pre-existing な E501・コメント行・私の編集範囲外・スコープ外）。
5. **live-DB ETL 2回連続実行**: fail-loud 発火（Task 3 の目的通り・原因特定成功）。idempotent verify は fail-loud で到達せず（Task 1 が先に発火するため・設計通り）。

### 新規回帰テスト（4件）

- `test_compute_fukusho_labels_raises_on_empty_race_df`: race_df 空（0行）で RuntimeError。
- `test_compute_fukusho_labels_raises_on_missing_race_date_column`: race_df に race_date 列欠損で RuntimeError。
- `test_compute_fukusho_labels_normal_case_no_diagnostic_log`: 正常ケース（race_date 全行 non-NULL）は RuntimeError 未発生・挙動不变。
- `test_run_label_etl_has_race_date_post_condition`: `inspect.getsource` で post-condition SQL 文（`race_date IS NULL`）と `RuntimeError` の存在を構造検査（WR-10 guard と同パターン）。

### 既存テスト GREEN 維持

- `test_compute_fukusho_labels_propagates_race_date`: GREEN（名指しされた回帰テスト）。
- `test_race_meta_select_columns_includes_race_date`: GREEN（名指しされた回帰テスト）。
- その他41テスト: GREEN（`_build_label_input_df` デフォルトに race_date を付与したことで正常ケースとして維持）。

## 根本原因（Task 3 の診断ログで特定）

**race_key 型不整合**: `compute_fukusho_labels` の race_df merge で `_RACE_KEY = ["year", "jyocd", "kaiji", "nichiji", "racenum"]` を `astype(str)` で揃えているが、実データの型が不一致:

| 列 | normalized.n_race（race_df 側） | public.n_harai/n_uma_race（SE/HR 側） | str 化後の不一致 |
|----|-------------------------------|---------------------------------------|----------------|
| `year` | `2015` (int4) | `'2015'` (varchar) | 一致 |
| `jyocd` | `'06'` (varchar) | `'06'` (varchar) | 一致 |
| `kaiji` | `1` (int4) | `'01'` (varchar・2桁ゼロ埋め) | **`"1"` vs `"01"` で不一致** |
| `nichiji` | `'01'` (varchar) | `'01'` (varchar) | 一致 |
| `racenum` | `1` (int4) | `'01'` (varchar・2桁ゼロ埋め) | **`"1"` vs `"01"` で不一致** |

`kaiji` と `racenum` が `int4`（ゼロ埋めなし）vs `varchar`（2桁ゼロ埋め）のため、`astype(str)` しても `"1"` vs `"01"` で一致せず、left join が全行 miss → race_date が全行 NULL になる。

コメント行634「実DB では race 側の _RACE_KEY は int4（normalized.n_race）、SE/HR 側は varchar」は既知の pitfall として記載されていたが、`astype(str)` だけではゼロ埋めフォーマット差を吸収できていなかった。

### 影響

- 2026-06-23/06-24 の label.fukusho_label.race_date 全行 NULL はこの race_key 型不整合が原因（backfill で一時復元済み）。
- 本 plan の fail-loud + 診断ログにより、再発時即停止 + 原因特定が可能になった（Task 3 で実証）。
- **根本原因の修正（race_key ゼロ埋め正規化）は本 plan のスコープ外**（PLAN の `<objective>`: 「根本原因は再発時の診断ログで特定する仕組みを作る」・別 quick task で対応推奨）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] _build_label_input_df のデフォルト race_df に race_date を付与**

- **Found during:** Task 1 GREEN フェーズ
- **Issue:** PLAN の `action` は `_build_label_input_df` のデフォルト race_df が race_date 列を含まないことを前提としていたが、実際には既存41テストがそのデフォルトを使い正常ケースとして期待していた。新しい fail-loud を入れると31テストが wide regression した（PLAN の done 基準「test_fukusho_label.py 全体が GREEN」と矛盾）。
- **Fix:** `_build_label_input_df` のデフォルト race_df に `race_date` 列（`dt.date(2023, 1, 1)`）を付与。これにより既存テスト群は自動的に正常ケースとして GREEN を維持。`test_compute_fukusho_labels_raises_on_missing_race_date_column` は明示的に `race_df.drop(columns=["race_date"])` で列を削除して検証するよう修正。また `test_is_dh_handles_hr_missing_payout_count_nan` の独自 race_df にも race_date を付与（本来の検証目的は is_dead_heat NaN 処理・race_date 伝播ではない）。
- **Files modified:** tests/test_fukusho_label.py
- **Commit:** 5bd65ca

**2. [Rule 1 - Bug] test docstring の E501 行長超過を修正**

- **Found during:** Task 1 GREEN フェーズ・ruff check
- **Issue:** `test_compute_fukusho_labels_raises_on_missing_race_date_column` の docstring 1行目が100文字超過。
- **Fix:** docstring を「race_df に race_date 列が無い場合・RuntimeError を raise する。」に短縮。
- **Files modified:** tests/test_fukusho_label.py
- **Commit:** 5bd65ca（同一コミットに含む）

## Scope Boundary遵守

- **raw 不変（D-06）**: raw テーブルに一切書込まず（live-DB 検証で fail-loud 発火により write_pool 到達せず・raw_touched は検証される前に RuntimeError）。
- **再現性（§19.1）**: staging-swap / idempotent ロジック（`_idempotent_load_label`）の構造は一切変更せず。post-condition は staging-swap 完了後に検査・null_count==0 は挙動不变。
- **通常ケース挙動不变**: fail-loud・診断ログは異常時のみ発火。正常ケースの出力列・行数・checksum は変更なし（unit test で normal_case_no_diagnostic_log が GREEN）。ただし live-DB では根本原因（race_key 型不整合）により異常ケースが常態化しているため、別 quick task での根本修正が必要。
- **変更ファイル**: `src/etl/fukusho_label.py` と `tests/test_fukusho_label.py` のみ。既存の未コミット変更（`scripts/run_backtest.py`, `src/db/prediction_load.py`）は一切 staging していない（git add で2ファイルのみ明示指定）。

## Deferred Issues / 別タスク推奨

### race_key 型不整合の根本修正（別 quick task 推奨）

- **問題**: `compute_fukusho_labels` の race_df merge で `kaiji` と `racenum` が `int4`（normalized.n_race）vs `varchar` 2桁ゼロ埋め（public.n_*）で一致せず、race_date が全行 NULL になる。
- **影響**: label.fukusho_label.race_date 全行 NULL が常態化（backfill で一時復元済みだが ETL 再実行で再発）。
- **推奨修正**: race_merge 構築時に `kaiji`/`racenum` を2桁ゼロ埋め（`race_merge[k] = race_merge[k].astype(str).str.zfill(2)`）に正規化、または SELECT 時に `LPAD(kaiji::text, 2, '0')` で正規化。ただし既存の正常ケース（unit test の合成データ）と整合するよう注意が必要（unit test の kaiji/racenum は既に2桁ゼロ埋め varchar）。
- **スコープ**: 本 quick plan（fail-loud + 診断ログ）は完了。根本修正は別 quick task（例: `260625-h1g2-race-key-zero-pad-fix`）で対応。

## Self-Check: PASSED

- src/etl/fukusho_label.py: FOUND（変更済み・3コミット全てに含む）
- tests/test_fukusho_label.py: FOUND（変更済み・3コミット全てに含む）
- commit 29d2789 (RED): FOUND
- commit 5bd65ca (GREEN/fail-loud): FOUND
- commit c32ad30 (Task 2 post-condition): FOUND
- KEIBA_SKIP_DB_TESTS=1 unit test 45 passed: VERIFIED
- DB 必須テスト含む 45 passed: VERIFIED
- ruff check src/etl/fukusho_label.py: VERIFIED (All checks passed)
- fail-loud live-DB 発火 + 根本原因特定: VERIFIED（PLAN の目的達成）
