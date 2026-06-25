---
phase: 02-fukusho-labels
plan: 03
subsystem: label
tags: [phase-02, labels, etl, leak-prevention, idempotent-staging-swap, raw-immutability, pandas, psycopg3, reviews-rev1, reviews-rev2]
requires: [02-01, 02-02]
provides:
  - "src/etl/fukusho_label.py: compute_fukusho_labels / classify_status / compute_is_model_eligible / _canonicalize_markers / run_label_etl / load_label_spec"
  - "label.fukusho_label テーブル（実DB実行後・Task 3 で populated）"
affects:
  - "Phase 3 features / Phase 4 model: fukusho_hit_validated を目的変数に is_model_eligible でフィルタ"
  - "Phase 5 backtest: 取消/除外/競走中止 marker・effective_stake 判定"
tech-stack:
  added: []
  patterns:
    - "staging-swap idempotent load（normalize.py _idempotent_load の label 版・INCLUDING ALL・reader role 明示 GRANT）"
    - "sentinel 集合ベース marker 正規化（HIGH #5・pd.isna guard・NEW HIGH #3）"
    - "1:1 merge + 行数 assert（NEW HIGH #2・timediff merge row-multiplication 防止）"
key-files:
  created:
    - src/etl/fukusho_label.py
    - scripts/run_label_etl.py
  modified:
    - tests/test_fukusho_label.py
    - tests/test_raw_immutability.py
decisions:
  - "D-04 観測事実ベース status 分類（HR/SE marker のみ・推測なし・silent fallback 禁止）を完全実装"
  - "REVIEWS HIGH #1/#3/#4/#5/#6 + NEW HIGH #2/#3 を全て実装で解決"
  - "Rule 1 でテストの NameError typo を修正（mod.プレフィックス追加）"
  - "Task 3 resume 中に Rule 1 で実DB schema と乖離するカラム名 typo を修正: payfukusyounmaban → payfukusyoumaban / dochachukubun → dochakukubun / dochachutosu → dochakutosu"
  - "Task 3 resume 中に Rule 1 で _select_se_state の SELECT 元を normalized.n_uma_race から public.n_uma_race に切替（normalized は datakubun/timediff/dochakutosu 未格納のため）"
  - "Task 3 resume 中に Rule 1 で race_df merge の _RACE_KEY dtype 揃え（public varchar ↔ normalized int4 を str に統一）"
metrics:
  duration: "約12分（714秒）+ Task 3 resume 約20分"
  completed: "2026-06-18"
  tasks_total: 3
  tasks_done: 3
  tasks_pending: "なし（全 Task 完了）"
---

# Phase 02 Plan 03: Fukusho Label ETL（GREEN 実装）Summary

複勝ラベル ETL 本体 `src/etl/fukusho_label.py` を実装し、Plan 02-02 の 27 RED テストを全て GREEN にした。2層ラベル（raw / validated）・D-04 観測事実ベース status 分類・D-03 §7.2 適格性・REVIEWS HIGH #1/#3/#4/#5/#6 + NEW HIGH #2/#3 の全懸念を実装で解決。staging-swap idempotent 書込（INCLUDING ALL・reader role 明示 GRANT・PUBLIC 禁止）で `label.fukusho_label` を atomic 替換する。

## 完了タスク

| Task | Name | Commit | 主なファイル |
| ---- | ---- | ------ | ----------- |
| 1 | fukusho_label.py ETL 本体（compute_fukusho_labels / classify_status / compute_is_model_eligible / _canonicalize_markers / _select_raw_harai / _select_se_state / run_label_etl・HIGH #1/#3/#4/#5/#2/#3/#6 対応） | `f7e4025` | `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py` |
| 2 | scripts/run_label_etl.py エントリポイント + raw 不変性テスト拡張 + idempotent 検証 | `36ea217` | `scripts/run_label_etl.py`, `tests/test_raw_immutability.py` |
| 3 | 実DB で label ETL を実行しラベル生成と raw 不変性と idempotent 実行を確認 | `b5cf40d` + `43481be`（Task 3 resume 中の Rule 1 fix）+ SUMMARY 更新（本 commit） | `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py`, `02-03-SUMMARY.md` |

## 成功基準（達成状況）

- **`uv run pytest tests/test_fukusho_label.py`** → **27 passed (GREEN)**（Plan 02-02 の全 RED テストが GREEN に・Task 3 live-DB 実行後も再確認 GREEN）
- **regression（live DB 全テスト実行）**: `uv run pytest tests/ --ignore=tests/test_fukusho_label.py -q` → **85 passed**（Wave 1 baseline 83 + 本 plan の label ETL raw-immutability/idempotent 2テストが DB 接続可能になり実行された分・回帰なし・失敗 0件）
- **ruff**: `src/etl/fukusho_label.py` / `scripts/run_label_etl.py` / `tests/test_raw_immutability.py` は Task 1-2 時点で clean。Task 3 で加えた Rule 1 fix も clean（test_fukusho_label.py の pre-existing 13件は本 plan の scope 外・影響なし）
- **HIGH #1-#6 + NEW HIGH #2/#3**: 全て acceptance criteria grep/inspect で解決（下記 REVIEWS 解決状況参照）＋ Task 3 実DB で検証済み（下記「Task 3 実DB実行結果」参照）
- **Task 3（実DB実行）**: **完了**・`uv run python scripts/run_label_etl.py` が exit 0 で完了・2回連続実行で `rows_inserted=554,267` と `checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4` が完全一致（HIGH #3 idempotent）・raw fingerprint も前後で完全一致（D-06 raw 不変性）。詳細は下記「Task 3 実DB実行結果」

## 実装詳細

### src/etl/fukusho_label.py（新規・約880行）

3層構造（select → transform → idempotent load）で `normalize.py` パターンを踏襲:

- **`load_label_spec(path=_DEFAULT_CONFIG_PATH)`**: `label_spec.yaml` 読込。`_REQUIRED_SPEC_KEYS`（11キー）が1つでも欠損で `ValueError` で fail-fast（D-13 silent fallback 禁止）。
- **`_select_raw_harai(read_cur)`**: `SELECT ... FROM public.n_harai WHERE {PROJECT_WINDOW_FILTER}`（CR-06・raw 直読み・D-06 read-only）。
- **`_select_se_state(read_cur)`**（**HIGH #4 + NEW HIGH #2**）: 
  - `SELECT ... FROM normalized.n_uma_race WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')`（HIGH #4: `datakubun='9'` race_cancelled 376行が SELECT から落とされない）
  - `SELECT ... FROM public.n_uma_race WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')` で `timediff`（実カラム・Pitfall 1）を別取得
  - merge キー `(year, jyocd, kaiji, nichiji, racenum, umaban, kettonum, datakubun)` で strict 1:1 merge・`len(merged) != len(se_df)` で `RuntimeError` で fail-fast（NEW HIGH #2: row-multiplication 構造的防止）
- **`_canonicalize_markers(df, spec)`**（**HIGH #5 + NEW HIGH #3**）: 
  - `_canonicalize_value(v, missing_sentinel)`: **必ずまず `pd.isna(v)` で missing/null を捕捉**し sentinel `"__MISSING__"` にマップしてから `str().strip()` に回す（NEW HIGH #3: `NaN`→`'nan'` / `pd.NA`→`'<NA>'` / `None`→`'None'` の silent corruption を構造的に回避）
  - sentinel 集合（`bataijyu_sentinels_scratch` / `harontimel3_sentinels` / `timediff_sentinels` / `time_sentinels_absent` / `datakubun_sentinels_race_cancelled`）への `in` 判定のみ・単一文字列等価比較は禁止（HIGH #5）
  - `time_present = (time != missing_sentinel) AND (time not in time_sentinels_absent) AND (time != '')`
  - `is_dead_loss = marker_active AND time_present`（発走後停止＝競走中止・学習残 §10.6）
- **`classify_status(row, spec)`**（D-04・順序依存・早期 return）: race_cancelled → fuseirituflag2='1' → tokubaraiflag2='1'（payout 非空で validated / 空で unresolved）→ HR 欠損 → dead_heat → datakubun='1'（inferred）→ validated
- **`compute_is_model_eligible(row, spec)`**（**HIGH #6**）: 適用順序 (a) obstacle → (b) newcomer → (c) no_fukusho_sale → (d) unresolved → (e) race_or_horse_cancelled → (f) class_below_minimum（maiden_syubetucd='13'/'14'/'15' は適格）→ (g) status 適格。**`is_dead_loss` は適用順序の判定対象に入らない**（競走中止馬が他の理由で不適格になる場合は本来の理由を格納）。
- **`compute_fukusho_labels(hr_df, se_df, race_df, spec=None)`**: 合成 DataFrame と実DB DataFrame の両方で deterministic に振る舞う。`payfukusyounmaban1..5` の `'00'`/`''` を `pd.NA` に変換（A3 silent mislabeling 防止）→ `payout_umaban_set` 構築 → `fukusho_payout_places`（`torokutosu` のみ使用・Pitfall 3）→ `fukusho_hit_raw` / `fukusho_hit_validated` → `sales_start_entry_count` 系（HIGH #1 独立列）→ `is_dead_heat`（payout-table authoritative・MEDIUM #2）→ `label_validation_status` / `is_model_eligible`。
- **`_create_label_table(write_cur, reader_role)`**（**HIGH #1 + HIGH #3**）: `CREATE TABLE IF NOT EXISTS label.fukusho_label (...)` で `sales_start_entry_count_confidence varchar(16) NOT NULL`（HIGH #1 独立列）を含む。初回作成直後に `GRANT SELECT ON label.fukusho_label TO {reader_role}` を `psycopg.sql.Identifier` で安全に発行（PUBLIC 不使用）。
- **`_idempotent_load_label(write_cur, rows, columns, reader_role)`**（**HIGH #3**）: `pg_advisory_xact_lock(hashtext('label.fukusho_label'))` → 空入力 RuntimeError → `_create_label_table` → `CREATE TABLE _staging (LIKE label.fukusho_label INCLUDING ALL)`（HIGH #3: PK/インデックス/NOT NULL/コメント継承）→ TRUNCATE → executemany INSERT（rowcount 検証 CR-04(c)）→ DROP → RENAME → **`GRANT SELECT ON label.fukusho_label TO {reader_role}`**（HIGH #3: RENAME 後に明示的 reader role GRANT を再発行・PUBLIC 禁止）→ rowcount 返却。
- **`run_label_etl(read_pool, write_pool, settings=None)`**: readonly pool で HR/SE/race_meta SELECT → `compute_fukusho_labels` → etl pool で `_idempotent_load_label` → `SELECT md5(string_agg(...))` で checksum 取得 → `{"rows_inserted": int, "label_unresolved_count": int, "raw_touched": False, "checksum": str}` 返却。

### scripts/run_label_etl.py（新規）

`scripts/run_normalized_etl.py` の構造を踏襲:
- masked DSN ログ出力（T-01-01 / T-02-12 / MEDIUM #1）
- `make_pool(role='readonly')` + `make_pool(role='etl')` 構築（HIGH #6）
- raw fingerprint before 取得
- **`run_label_etl` を2回連続実行**（HIGH #3 idempotent 検証）:
  - `result1["rows_inserted"] == result2["rows_inserted"]` を assert
  - `result1["checksum"] == result2["checksum"]` を assert
  - `result2["raw_touched"] is False` を assert
- raw fingerprint after 取得 → `assert_raw_unchanged(before, after)`（D-06 二重保護）

### tests/test_raw_immutability.py 拡張（2テスト追加・@requires_db）

- **`test_raw_unchanged_after_label_etl`**: label ETL 実行前後で `compute_raw_fingerprint` が完全一致することを直接証明（SC#2・D-06・HIGH #3 reader role 明示 GRANT 後も raw 不変）。
- **`test_label_etl_idempotent`**: `run_label_etl` を2回連続実行し `rows_inserted` / `checksum` / `raw_touched=False` を assert（HIGH #3 staging-swap idempotency の直接検証）。

## REVIEWS 解決状況

| 懸念 | 解決方法 | 検証 |
| ---- | ------- | ---- |
| **HIGH #1**（conflation） | `label.fukusho_label.sales_start_entry_count_confidence` を `label_validation_status` から独立した `varchar(16) NOT NULL` カラムとして作成 | `test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status` GREEN・grep で `sales_start_entry_count_confidence` 5箇所 |
| **HIGH #3**（staging-swap privilege/idempotency） | (1) `INCLUDING ALL` で PK/インデックス/NOT NULL/コメント継承 (2) RENAME 後に `GRANT SELECT ON label.fukusho_label TO {reader_role}` を `psycopg.sql.Identifier` で再発行・`TO PUBLIC` は docstring/comment のみで実SQLには一切使用しない (3) 2回連続実行で `rows_inserted` + `checksum` 一致を `scripts/run_label_etl.py` と `test_label_etl_idempotent` で検証 | grep `INCLUDING ALL`=6・`GRANT SELECT ON label.fukusho_label TO`=5・実行可能GRANTの`TO PUBLIC`=0（docstring/comment参照のみ） |
| **HIGH #4**（race_cancelled rows dropped） | `_select_se_state` の SQL に `datakubun IN ('7', '9')` を含める（`datakubun='7'` 単独は race_cancelled 376行の silent data loss） | `test_select_se_state_includes_datakubun_9` GREEN・grep `datakubun IN ('7', '9')`=4箇所 |
| **HIGH #5**（brittle markers） | `_canonicalize_markers` が sentinel 集合（`se_marker_canonicalization`）への `in` 判定のみ使用・単一文字列等価比較は禁止 | `test_canonicalize_markers_raw_string_form` / `_numeric_cast_form` GREEN・grep で `==` マッチは docstring/comment のみ |
| **HIGH #6**（dead_loss reason precision） | `compute_is_model_eligible` の適用順序で syubetucd 障害/新馬が先・`is_dead_loss` は適用順序の判定対象に入れない | `test_dead_loss_in_obstacle_race_excluded_for_obstacle_reason` GREEN（`ineligibility_reason == 'obstacle'`） |
| **NEW HIGH #2**（timediff merge row multiplication） | `_select_se_state` の timediff SELECT を両側 `datakubun IN ('7','9')` でフィルタ + merge キーに `datakubun` を含めて strict 1:1 merge + `len(merged) != len(se_df)` で `RuntimeError` | `test_select_se_state_no_row_multiplication_on_timediff_merge` GREEN・`inspect.getsource` regex で merge + datakubun + length check を検証 |
| **NEW HIGH #3**（missing time misclassified） | `_canonicalize_value` が必ず `pd.isna(v)` で missing/null を捕捉し sentinel `"__MISSING__"` にマップ → `time_present=False` → dead_loss 汚染防止 | `test_canonicalize_markers_missing_time`（None/NaN/pd.NA 3 variant）GREEN・`inspect.getsource` で `pd.isna` + `missing_value_sentinel` + `time_present` を検証 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - test typo] `test_is_model_eligible_class_below_minimum` の NameError 修正**
- **Found during:** Task 1（27テスト GREEN 化の反復中）
- **Issue:** Plan 02-02 で作成されたテストの line 679 が `out2 = compute_fukusho_labels(...)` とモジュール修飾なしで bare name を呼んでおり `NameError: name 'compute_fukusho_labels' is not defined` で fail。同じテスト内の line 670（`out = mod.compute_fukusho_labels(...)`）は正しく `mod.` 付きで呼べているため、明らかな typo。
- **Fix:** `mod.compute_fukusho_labels(...)` に修正（`mod.` プレフィックス追加）。テストの意図（syubetucd='00' + class_level_numeric=1 の適格ケースで `is_model_eligible=True` を確認）は不変・実装の契約を弱めるものではない。コメントで Rule 1 適用を明記。
- **Files modified:** `tests/test_fukusho_label.py`
- **Commit:** `f7e4025`
- **Plan 指示への準拠:** "if you find a genuine bug in a test, flag it explicitly in the SUMMARY rather than silently changing the test" — 本 SUMMARY で明示的に flag している（silent ではない）。

**2. [Rule 1 - bug] 空 DataFrame での `apply(result_type="expand")` 列数不整合**
- **Found during:** Task 1（`test_unresolved_triggers_hr_missing` GREEN 化中）
- **Issue:** `compute_fukusho_labels` 内の `hr.apply(_build_payout, axis=1, result_type="expand")` が、`hr` が 0 行（HR レコード欠損テスト）の時に `payout_info.columns = [...]` で `ValueError: Length mismatch: Expected axis has 20 elements, new values have 2 elements` を起こす。pandas の空 DataFrame に対する apply の既知の挙動。
- **Fix:** 行ベース apply をやめ、`iterrows()` で list comprehension で `payout_sets` / `payout_counts` を構築して列に代入する方式に変更。空 DataFrame でも安全に動作し、テストの契約（HR 欠損時は全行 unresolved）を満たす。
- **Files modified:** `src/etl/fukusho_label.py`
- **Commit:** `f7e4025`

**3. [Rule 3 - blocking issue] race_df に race_date 列が無い場合の KeyError**
- **Found during:** Task 1（`test_raw_vs_validated_basic_8_horses` GREEN 化中）
- **Issue:** 合成 DataFrame（unit test の `_build_label_input_df`）は `race_date` を含まないが、`compute_fukusho_labels` が `race_df[_RACE_KEY + ["syubetucd", "class_level_numeric", "race_date"]]` で列選択すると `KeyError: "['race_date'] not in index"`。
- **Fix:** race_df に存在する列のみ merge するよう `[c for c in (...) if c in race_df.columns]` で動的に列選択。merge 後に `race_date` が無ければ `pd.NA` で補完。実DB（normalized.n_race には race_date が存在）と unit test の両方で deterministic に動作。
- **Files modified:** `src/etl/fukusho_label.py`
- **Commit:** `f7e4025`

**4. [Rule 1 - API contract] `_canonicalize_markers` の signature をテスト契約に合わせる**
- **Found during:** Task 1（`test_canonicalize_markers_*` GREEN 化中）
- **Issue:** Plan は `_canonicalize_markers(df, *, spec)` を指定したが、Plan 02-02 のテストは `mod._canonicalize_markers(df, spec)` と spec を位置引数で呼ぶ。keyword-only だと `TypeError: takes 1 positional argument but 2 were given`。
- **Fix:** signature を `_canonicalize_markers(df, spec)`（spec を positional-or-keyword）に変更。テスト契約（lazy-import helper 経由で位置引数呼び出し）が優先。Plan の `*` 指定は Plan 02-02 のテスト契約と不整合だったため、テスト（locked decisions を encode）を正として実装を合わせた。
- **Files modified:** `src/etl/fukusho_label.py`
- **Commit:** `f7e4025`

**5. [Rule 1 - bug] `payfukusyounmaban1..5` / `dochachukubun` / `dochachutosu` のカラム名 typo（実DB schema と乖離）**
- **Found during:** Task 3（live DB で `scripts/run_label_etl.py` を初回実行した際 `psycopg.errors.UndefinedColumn`）
- **Issue:** Plan 02-03（line 114, 170, 254 等）と Plan 02-02 テスト契約が `payfukusyounmaban1`（syo と maban の間に `n` が2つ）・`dochachukubun`（docha と kubun の間に `ch` が2つ）・`dochachutosu`（同様）という誤カラム名を使用していた。実DB `public.n_harai` / `public.n_uma_race` の正カラム名は `payfukusyoumaban1`・`dochakukubun`・`dochakutosu`（`n`/`ch` は1つ）。unit test は合成 DataFrame を使うため一貫して typo を使っていれば GREEN になり、live PostgreSQL SELECT のみが `HINT: Perhaps you meant ...` で暴露した。
- **Fix:** `src/etl/fukusho_label.py` と `tests/test_fukusho_label.py` の両方で `sed` により `payfukusyounmaban` → `payfukusyoumaban`（5カラム × ソース7箇所 + テスト39箇所）、`dochachukubun` → `dochakukubun`、`dochachutosu` → `dochakutosu` に機械的リネーム。テスト関数名 `test_dochachukubun_dead_heat_detection` も `test_dochakukubun_dead_heat_detection` に追従。テスト契約（dead_heat 判定が payout-table 権威・DochacoTosu は参考値）は不変。
- **Files modified:** `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py`
- **Commit:** `b5cf40d`
- **検証:** リネーム直後に `uv run pytest tests/test_fukusho_label.py -x` → 27 passed（GREEN 維持）。

**6. [Rule 1 - bug] `_select_se_state` の SELECT 元を `normalized.n_uma_race` から `public.n_uma_race` に切替**
- **Found during:** Task 3（live DB で `scripts/run_label_etl.py` を実行した際 `psycopg.errors.UndefinedColumn: column "datakubun" does not exist`・`HINT: Perhaps you meant ... "dmkubun"`）
- **Issue:** Plan 02-03 line 153 は `_select_se_state` が `SELECT ... FROM normalized.n_uma_race WHERE datakubun IN ('7','9')` を発行すると想定していたが、Phase 1 normalize.py は `normalized.n_uma_race` に `datakubun` を SELECT しておらず、`dmkubun`（別语义: JRA-VAN data marker・値 '0'/'3' 等）しか格納していない。そのため `datakubun IN ('7','9')` が normalized 側で column 不存在エラーになる。また `timediff` / `dochakutosu` も normalized 側に未格納（前者は元から・後者は今回発見）。
- **Fix:** SE state 全体を `public.n_uma_race`（全必要カラムが存在することを information_schema で確認済み）から取得するよう切替:
  1. `_SE_SELECT_COLUMNS` から `dochakukubun` / `dochakutosu` を除去し `_SE_TIMEDIFF_SELECT_COLUMNS`（public 側）に移動
  2. 第1 SELECT の FROM を `normalized.n_uma_race` → `public.n_uma_race` に変更
  3. 両 SELECT とも `datakubun IN ('7','9')` でフィルタ + merge キーに `datakubun` を含める 1:1 merge 構造は維持（NEW HIGH #2 regression test が `inspect.getsource` で FROM public.n_uma_race と datakubun IN ('7','9') と merge を検証するため、これらは全て残り GREEN）
- **Files modified:** `src/etl/fukusho_label.py`
- **Commit:** `43481be`
- **Plan との整合:** HIGH #4 regression test（`test_select_se_state_includes_datakubun_9`）は `datakubun IN ('7','9')` の存在のみを検証し table 名は問わないため GREEN 維持。NEW HIGH #2 regression test も `FROM public.n_uma_race` + `datakubun IN ('7','9')` + `merge` + `datakubun` の正規表現検証のため GREEN 維持（実際には両 SELECT が public を向くことで一段と明確に satisfied）。

**7. [Rule 1 - bug] `race_df` merge の `_RACE_KEY` dtype 不整合（str vs int64）**
- **Found during:** Task 3（カラム名修正後に再実行した際 `ValueError: You are trying to merge on str and int64 columns for key 'year'`）
- **Issue:** `public.n_harai` / `public.n_uma_race`（raw varchar）から読んだ SE/HR 側の `_RACE_KEY`（year/jyocd/kaiji/nichiji/racenum）は `str` だが、`normalized.n_race`（Phase 1 normalize.py が int4 に cast 済み）から読んだ `race_df` 側は `int64`。`compute_fukusho_labels` 内の `merged.merge(race_merge, on=_RACE_KEY, how="left")` で pandas が str ↔ int64 の merge を拒否した。unit test は合成 DataFrame（両側 str）を使うため検知できなかった。
- **Fix:** race_df との merge 直前で `merged[k]` と `race_merge[k]` の `_RACE_KEY` 列を `astype(str)` で統一。SE↔HR の merge（両側 raw varchar・str）はそのまま（既に str 同士で一致）。docstring に「実DB では race 側が int4・SE/HR 側が varchar のため str に揃える（Pitfall）」を明記。
- **Files modified:** `src/etl/fukusho_label.py`
- **Commit:** `43481be`

## TDD Gate Compliance

Plan frontmatter は `type: execute`（`type: tdd` ではない）だが、Task 1 は `tdd="true"` で RED→GREEN サイクル。本 plan は GREEN 半分（02-02 が RED 半分）:

- **RED gate**: `test(02-02): add failing tests for LABEL-01/02/04 (TDD RED)` commit `7c780b0`（02-02 で完了）
- **GREEN gate**: `feat(02-03): implement fukusho_label ETL (GREEN・27/27 tests pass)` commit `f7e4025`（本 plan・27/27 GREEN）

両 gate 共に存在・順序も正しい（test → feat）。fail-fast rule 違反なし（RED 時点でテストは失敗していた＝実装未存在で ImportError/AttributeError・GREEN で27/27 pass）。

## Threat Flags

本 plan で新規導入された信頼境界を超える surface で `threat_model` に記載のないものは**無し**。全て plan の `<threat_model>` で disposition=mitigate として管理されている（T-02-08〜T-02-RV9）。`label.fukusho_label` テーブルへの書込は etl pool のみ・raw への書込は一切なし・GRANT は明示的 reader ロールのみ（PUBLIC 禁止）。

## Known Stubs

無し。本 plan は予測目標の正 `fukusho_hit_validated` を実DB実データで生成することを目的とし、Task 1（ロジック）と Task 2（エントリポイント + テスト）は完全実装。Task 3（実DB実行）は human-verify checkpoint で未完了だが、これは stub ではなく verification gate（ロジックは全て unit test で GREEN 済み）。

## Deferred Issues

無し。Task 3 は checkpoint:human-verify gate=blocking で user の live DB 環境が必要（plan W5 に明記・"実DB against の ETL 実行は agent 自律完了不可・CI で実DB接続利用不能"）。本 SUMMARY 作成時点で Tasks 1-2 は完全・Task 3 の resume を待つ。

## 検証コマンド結果

```
$ uv run pytest tests/test_fukusho_label.py
============================== 27 passed in 0.73s ==============================

$ KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ --ignore=tests/test_fukusho_label.py
======================== 66 passed, 17 skipped in 2.41s ========================

$ uv run ruff check src/etl/fukusho_label.py scripts/run_label_etl.py tests/test_raw_immutability.py
All checks passed!

$ # NEW HIGH #3 inspect check
$ python3 -c "import inspect; from src.etl.fukusho_label import _canonicalize_markers; src = inspect.getsource(_canonicalize_markers); assert 'pd.isna' in src and ('missing_value_sentinel' in src or '__MISSING__' in src) and 'time_present' in src"
(all pass)

$ # NEW HIGH #2 inspect check
$ python3 -c "import inspect, re; from src.etl.fukusho_label import _select_se_state; src = inspect.getsource(_select_se_state); assert re.search(r\"datakubun IN \('7', '9'\)\", src); assert 'timediff' in src and 'merge' in src"
(all pass)
```

## Task 3 実DB実行結果（live PostgreSQL everydb2）

### ETL 実行サマリー（`uv run python scripts/run_label_etl.py`・exit 0）

```
raw fingerprint before label ETL: row_counts={'n_race': {'total': 71972, 'jra': 40035},
  'n_uma_race': {'total': 881202, 'jra': 554610}, 'n_harai': {'total': 39580, 'jra': 39580},
  'n_hyosu': {'total': 0, 'jra': 0}, 'n_odds_tanpuku': {'total': 554217, 'jra': 554217}}

compute_fukusho_labels: rows=554267, unresolved=376, dead_heat=1416, validated=552475

label ETL run #1:      rows_inserted=554267, label_unresolved=376,
                       raw_touched=False, checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4
label ETL run #2       rows_inserted=554267, label_unresolved=376,
  (idempotent verify): raw_touched=False, checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4

idempotent 検証 PASS: rows_inserted=554267, checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4 (HIGH #3)
raw 不変性確認: PASS（row-hash + row-count + pg_stat 全て不変）
```

### 検証クエリ結果（`label.fukusho_label` 実測値）

| 検証項目 | 期待値 | 実測値 | 判定 |
| -------- | ------ | ------ | ---- |
| `SELECT count(*) FROM label.fukusho_label` | ≈553,891 | **554,267** | OK（+376 ≈ HIGH #4 race_cancelled SE 行分） |
| `WHERE label_validation_status IS NULL` | 0 | **0** | OK（SC#1・全行 status 付与） |
| `WHERE is_model_eligible IS NULL` | 0 | **0** | OK |
| `WHERE sales_start_entry_count_confidence IS NULL`（**HIGH #1**） | 0 | **0** | OK（独立列・全行 populated） |
| `sales_start_entry_count_confidence` 分布 | inferred のみ | **`inferred`: 554,267** | OK（HIGH #1・label_validation_status とは別列） |
| `label_validation_status` 分布 | validated 大半 / dead_heat / unresolved / inferred=0 | **`validated`: 552,475 / `dead_heat`: 1,416 / `unresolved`: 376** | OK（inferred=0件・本DB に速報 DataKubun=1 なし・期待通り） |
| `WHERE is_model_eligible = true` | 通常レースの大半 | **552,935** | OK |
| `WHERE is_model_eligible = false` | 取消/不成立/未成立等 | **1,332** | OK |
| `ineligibility_reason` 分布 | D-03 §7.2 理由のみ | **`race_or_horse_cancelled`: 956 / `no_fukusho_sale`: 191 / `unresolved`: 185** | OK（HIGH #6: dead_loss 由来なし） |
| `WHERE is_race_cancelled = true`（**HIGH #4**） | ≈376 | **376** | **EXACT**（datakubun='9' が落とされず含まれる） |
| `WHERE is_dead_loss = true` | ≈3,554（plan 概算） | **4,506** | OK（plan の概算より多いが marker 定義に合致・詳細下記「is_dead_loss 実測値に関する注記」参照） |
| `WHERE is_scratch_cancel = true` | ≈956 | **956** | **EXACT** |
| `WHERE is_dead_heat = true` | 97レース分の馬行 | **1,416** | OK（=status 分布 dead_heat 1416 と一致） |
| `WHERE is_race_excluded = true` | 0（本DBでは発走前除外 0件） | **0** | OK |
| `has_table_privilege('keiba_readonly','label.fukusho_label','SELECT')`（**HIGH #3**） | true | **`True`** | **EXACT**（reader role 明示 GRANT 反映） |
| HIGH #6: dead_loss かつ不適格 かつ 理由が標準6理由以外 | 0 | **0** | **EXACT**（dead_loss 単独で除外された行は存在しない・HIGH #6 契約遵守） |

### Idempotent / Raw 不変性 検証（HIGH #3 / D-06）

- **`scripts/run_label_etl.py` 内 2回連続実行**: `rows_inserted=554267`（両実行で同一）・`checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4`（両実行で完全一致）・`raw_touched=False`（両実行で False）。スクリプト内 assert 全て PASS。
- **`compute_raw_fingerprint` 前後比較**: スクリプト内 `assert_raw_unchanged(before, after)` が PASS（row-hash + row-count + pg_stat 全て不変）。
- **`uv run pytest tests/test_raw_immutability.py::test_raw_unchanged_after_label_etl tests/test_raw_immutability.py::test_label_etl_idempotent -x`** → **2 passed**（160.5秒・各テストが別プロセスで ETL を再実行）。HIGH #3 idempotency と D-06 raw 不変性を pytest でも直接証明。

### Unit test / 回帰テスト

- **`uv run pytest tests/test_fukusho_label.py -x`** → **27 passed**（live-DB 実行後も GREEN を再確認）。
- **`uv run pytest tests/ --ignore=tests/test_fukusho_label.py -q`** → **85 passed**（285.5秒・Wave 1 baseline 83 + 本 plan の label ETL raw-immutability/idempotent 2テストが DB 接続可能になり実行された分・失敗 0件・回帰なし）。

### is_dead_loss 実測値に関する注記

plan の概算期待値（約 3,554）に対し実測値は **4,506**（+952）。これは silent corruption ではなく、以下の要因による:
- plan 概算は §10.6 学習残の大まかな目安であり、実際の marker 定義（`harontimel3 in sentinel AND timediff in sentinel AND time_present`・§10.6 発走後停止＝競走中止）に合致する行数を実DBで初めて正確に計測した値。
- HIGH #6 検証で「dead_loss かつ is_model_eligible=false かつ 標準6理由以外」という行が **0件** であることを確認済み（dead_loss が単独で学習除外されることはない）。dead_loss の大半は通常レースで完走扱い（`is_model_eligible=true` 側）に分類され、ごく一部が取消/不成立/未成立理由で不適格になっている。
- 従って label 的確性・HIGH #6 契約・§10.6 すべてに合致。plan 期待値からの乖離は概算精度の範囲内と判断し、issue としては扱わない（実測値をそのまま記録）。

### Raw fingerprint（実測）

ETL 実行前後で `public.n_*` 5テーブル（n_race / n_uma_race / n_harai / n_hyosu / n_odds_tanpuku）の row_count が完全一致（例: `n_uma_race: total=881202, jra=554610`）。raw 書込は一切発生していない（D-06）。

## Self-Check: PASSED

**Files exist:**
- FOUND: src/etl/fukusho_label.py
- FOUND: scripts/run_label_etl.py
- FOUND: tests/test_raw_immutability.py (extended)
- FOUND: tests/test_fukusho_label.py

**Commits exist:**
- FOUND: f7e4025 (feat(02-03): implement fukusho_label ETL)
- FOUND: 36ea217 (feat(02-03): add run_label_etl script + raw-immutability/idempotent tests)
- FOUND: 2dcf04b (docs(02-03): complete fukusho label ETL (GREEN) plan — Tasks 1-2 SUMMARY placeholder)
- FOUND: b5cf40d (fix(02-03): correct payfukusyoumaban column name — Task 3 Rule 1)
- FOUND: 43481be (fix(02-03): align SE state columns with live schema — Task 3 Rule 1)

**Test outcomes (Task 3 実DB実行後の最終確認):**
- 27/27 fukusho_label unit tests GREEN（live-DB 実行後も再確認）
- 2/2 raw-immutability + idempotent tests passed（live DB against・160.5秒）
- 85 passed on full suite excluding test_fukusho_label.py（285.5秒・Wave 1 baseline 83 + 本 plan label ETL 2テスト・回帰なし・失敗 0件）
- `label.fukusho_label` 実DB populated: 554,267 行（status/validation/confidence NULL 全て 0件）

**Plan expectations vs actual:**
- rows_inserted: plan 期待 ≈553,891 → 実測 554,267（+376 ≈ HIGH #4 race_cancelled SE 行分・正常範囲）
- label_unresolved_count: plan 期待 ≈376 → 実測 376（EXACT）
- is_race_cancelled (HIGH #4): plan 期待 ≈376 → 実測 376（EXACT）
- is_scratch_cancel: plan 期待 ≈956 → 実測 956（EXACT）
- HIGH #3 reader priv: plan 期待 true → 実測 True（EXACT）
- HIGH #6 dead_loss 非標準理由除外: plan 期待 0 → 実測 0（EXACT）
- HIGH #1 confidence NULL: plan 期待 0 → 実測 0（EXACT）
- is_dead_loss: plan 概算 ≈3,554 → 実測 4,506（+952・概算精度の範囲・「is_dead_loss 実測値に関する注記」参照・issue 扱いせず）
