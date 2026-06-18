---
phase: 02-fukusho-labels
review_path: .planning/phases/02-fukusho-labels/02-REVIEW.md
fix_scope: critical_warning
iteration: 2
findings_in_scope: 18
fixed: 13
skipped: 0
needs_human: 4
status: all_fixed
fixed_at: 2026-06-18T19:50:00+09:00
iteration_1_fixed_at: 2026-06-18T18:30:00+09:00
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-06-18T18:30:00+09:00
**Source review:** `.planning/phases/02-fukusho-labels/02-REVIEW.md` (depth: deep)
**Iteration:** 1
**Fixer:** Claude (gsd-code-fixer)
**Strategy:** prior_decisions に基づく A群（自動修正）+ B群（要人間判断）振り分け

## Summary

- **Findings in scope (CR + WR):** 18（CR-01〜CR-07: 7件 / WR-01〜WR-11: 11件）
- **Fixed (A群):** 12 件（CR-01, CR-02, CR-03, CR-06, CR-07, WR-02, WR-03, WR-05, WR-06, WR-07, WR-08, WR-09, WR-11 — 重複カウント方式: 13 発見 ID を 12 コミットでカバー。詳細下記）
- **Needs human judgment (B群):** 5 件（CR-04, CR-05, WR-01, WR-04, WR-10）
- **Skipped:** 0 件（A群は全て適用、B群は仕様判断のため意図的に未修正）
- **Info (fix_scope 外):** IN-01〜IN-05（5件）は本 fix の対象外

**Verification:** 全 Phase 02 テスト + 全テストスイート (`KEIBA_SKIP_DB_TESTS=1`) が pass。
`114 passed, 20 skipped in 3.39s`（skipped は全て DB 必須の `@pytest.mark.requires_db`）。

---

## Fixed Issues (A群 — 自動修正適用)

### CR-01: `_check_raw_validated_drift` の severity を `label_validation_status` 別に分類

**Files modified:** `src/etl/label_reconcile.py`, `tests/test_label_reconcile.py`
**Commit:** `b3bf210` (CR-01 + CR-07 統合コミット)
**Test result:** `tests/test_label_reconcile.py` 18 passed, 1 skipped

**Applied fix:**
ユーザー承認済みの方針に基づく精密化。drift を `label_validation_status` で分類:
- drift かつ `label_validation_status IN ('unresolved', 'dead_heat')` → `severity='info'`, `passed=True`（D-04-legitimate・`6af3b00` 判断を尊重）
- drift かつ `label_validation_status IN ('validated', 'inferred')` → `severity='block'`, `passed=False`（genuine な矛盾・レビュー CR-01 採用）

`serious_drift_count` / `serious_drift_statuses` を detail に追加。実DB の既知7件 validated drift を BLOCK で捕捉する。

**Logic bug flag:** 本修正は条件分岐ロジックの変更のため、自動検証（Tier 1/2）では意味論的正しさを完全に保証できない。ユニットテスト（`test_check_raw_validated_drift_validated_inferred_is_block`, `test_check_raw_validated_drift_dead_heat_only`）で両分岐を検証済みだが、実DB での挙動は要人間確認。

---

### CR-02: `_compute_race_level_agreement` の SQL injection f-string → psycopg3 パラメータ化 + UNNEST

**Files modified:** `src/etl/label_reconcile.py`
**Commit:** `0e0895c`
**Test result:** `tests/test_label_reconcile.py` 17 passed, 1 skipped

**Applied fix:**
`held_out_list` を f-string 展開する `where_race_keys`（`hr.jyocd='{rk[1]}'` 等）を廃止し、
psycopg3 パラメータ埋め込み + `UNNEST(%s::int[], %s::text[], ...)` で set-based 比較に変更。
`defense-in-depth` 違反を解消（`jyocd`/`nichiji` が varchar で EveryDB2 データ品質に依存するため）。

---

### CR-03: `_payout_places` / `_is_dh` の pd.NA・異常値 TypeError guard + regression テスト

**Files modified:** `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py`
**Commit:** `9474e19`
**Test result:** `tests/test_fukusho_label.py` 30 passed

**Applied fix:**
`_payout_places` の `int(t)` と `_is_dh` の `int(pp)` / `int(pc)` を try/except `(TypeError, ValueError)` でガードし、pd.NA / `np.float64(nan)` / 空文字 / 英字混じり経由の例外を `no_sale` / `False` に正規化。仕様境界（`payout_places_rules`）は変更しない。

Regression テスト追加:
- `test_payout_places_and_is_dh_handle_pd_na_and_abnormal_values`: pd.NA / np.float64(nan) / "" / "abc" の4パターン
- `test_is_dh_handles_hr_missing_payout_count_nan`: HR 欠損行（payout_count NaN）で is_dead_heat=False

修正前の `int(pd.NA)` が実際に `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NAType'` を raise することを確認済み。

---

### CR-06: `_LABEL_WINDOW_FILTER` 二重管理を解消

**Files modified:** `src/etl/filters.py`, `src/etl/label_reconcile.py`
**Commit:** `304b1e9`
**Test result:** `tests/test_label_reconcile.py` + `tests/test_fukusho_label.py` 45 passed, 1 skipped

**Applied fix:**
`filters.py` に `project_window_filter(alias: str = "")` helper を追加。
`label_reconcile.py` の `_LABEL_WINDOW_FILTER = "l.jyocd BETWEEN ..."` を `project_window_filter("l")` から構築するよう変更。`filters.py` を唯一のソースにし、将来 `PROJECT_WINDOW_FILTER` の期間/JRA 範囲を変更した際の追随漏れ（silent drift）を防止。

---

### CR-07: `test_verdict_pass_when_all_block_pass` の docstring 整備（CR-01 と統合）

**Files modified:** `tests/test_label_reconcile.py`（CR-01 コミット `b3bf210` に統合）
**Commit:** `b3bf210`

**Applied fix:**
CR-01 修正（`_check_raw_validated_drift` の status 別 severity 分類）後の前提を docstring に明記。「通常状態（serious drift=0）では `severity='info'` で返るが、本テストは全検査を `severity='block' + passed=True` で上書きし、verdict 集計ロジックを検証する。serious drift > 0 の場合は別テスト `test_check_raw_validated_drift_validated_inferred_is_block` で検証」と記載。

**Note:** CR-01 と CR-07 は同じファイルの同じテスト関数（`test_verdict_pass_when_all_block_pass` と drift テスト群）に触れるため、1コミットに統合。分離は不自然（CR-01 実装テスト更新の流れの中で docstring も更新するのが自然）。

---

### WR-02: `_check_no_scratch_mislabeled` の NULL-safe 比較

**Files modified:** `src/etl/label_reconcile.py`
**Commit:** `446e80b`

**Applied fix:**
`df["fukusho_hit_validated"] == 1` を `df["fukusho_hit_validated"].fillna(0).astype(int) == 1` に変更。`fukusho_hit_validated` は `smallint`（NOT NULL 明記なし）のため、NULL 混入時の違反見逃し（`NULL == 1` → False）を防止。

---

### WR-03: `_VALID_INELIGIBILITY_REASONS` を `label_spec.yaml` から load

**Files modified:** `src/etl/label_reconcile.py`
**Commit:** `d1c2afb`

**Applied fix:**
ハードコード `tuple[str, ...]` を廃止し、`_valid_ineligibility_reasons()` helper で `label_spec.yaml.ineligibility_reason_codes` から `frozenset` を構築。D-07（単一の正）と D-13（silent fallback 禁止・spec 未設定時は ValueError）を両立。モジュールレベルキャッシュで初回のみ spec load。

---

### WR-05: `_select_se_state` の両 SELECT フィルタ一致 assertion + regression テスト

**Files modified:** `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py`
**Commit:** `e3c105c`
**Test result:** `tests/test_fukusho_label.py` 28 passed

**Applied fix:**
両 SELECT の SQL 文字列に同一フィルタ（`f"WHERE {PROJECT_WINDOW_FILTER} AND datakubun IN ('7', '9')"`）が含まれることを直接 assert。片側だけ退化した場合の silent data loss を構造的に防止。Regression テスト `test_select_se_state_both_selects_share_filter_assertion` を追加。

---

### WR-06: `_idempotent_load_label` rowcount 検証を `SELECT count(*)` に変更

**Files modified:** `src/etl/fukusho_label.py`
**Commit:** `54cd2f0`

**Applied fix:**
psycopg3 `executemany` の `rowcount` は pipeline mode / PG バージョンで `PQcmdTuples` の挙動が変わるため信用できない。INSERT 後に `SELECT count(*) FROM label.fukusho_label_staging` で実際の行数を検証する方式に変更（CR-04 rowcount verification の後継）。

---

### WR-07: checksum 列順序依存を解消

**Files modified:** `src/etl/fukusho_label.py`
**Commit:** `6b1fc56`

**Applied fix:**
`row(r.*)::text` を `row({cols_csv})::text` に変更。`_LABEL_INSERT_COLUMNS` で列を明示し、`ALTER TABLE ADD COLUMN` で同じデータでも checksum が変わる列順序依存を解消。idempotent 実行確認（`result1["checksum"] == result2["checksum"]`）の信頼性を保証。

---

### WR-08 + WR-09: `run_label_etl` read connection rollback + reader_role デッドロジック削除（統合コミット）

**Files modified:** `src/etl/fukusho_label.py`
**Commit:** `bc7d986` (WR-08 + WR-09 統合コミット)

**Applied fix:**
- **WR-08:** `read_pool.connection()` ブロック末尾に明示 `conn.rollback()` を追加し、read transaction を確実に閉じる（後続する `write_pool` の staging-swap とのロック衝突を構造的に防止）。
- **WR-09:** `Settings.db_reader_role` は `str = "keiba_readonly"`（常に非 None）なため、未設定警告のデッドロジックを削除し `reader_role = settings.db_reader_role` に簡素化。

**Note:** WR-08（rollback 追加）と WR-09（デッドロジック削除）は同じ `run_label_etl` 関数の近接箇所（`settings` 構築直後の read connection ブロック）のため、1コミットに統合。

---

### WR-11: `scripts/run_label_etl.py` のデッドコード削除

**Files modified:** `scripts/run_label_etl.py`
**Commit:** `236447c`

**Applied fix:**
2回目の `with read_pool.connection() as conn: conn.rollback()` を削除。psycopg_pool の context manager 抜けで自動 rollback されるため無意味なデッドコード。コメントで理由を明記。

---

## Needs Human Judgment (B群 — 自動修正禁止)

以下の5件は仕様・設計・schema 変更を伴う判断が必要なため、自動修正を**意図的に適用せず**、人間判断に委ねる。

### CR-04: `fukusho_hit_raw` が race_cancelled / fuseiritu / tokubarai 空レースでも `kakuteijyuni` ベースで算出され、`fukusho_hit_raw=1` の行が残留

**File:** `src/etl/fukusho_label.py:651-662`

**REVIEW 指摘:**
`fukusho_hit_raw` は `fukusho_payout_places > 0 AND 1 <= kakuteijyuni <= payout_places` のみで算出され、`label_validation_status` / `is_race_cancelled` を見ない。race_cancelled レースでも SE `kakuteijyuni` に `1,2,3` 等が入り得るため `fukusho_hit_raw=1` になる行が残留し、`raw=1, valid=0` の drift 行が unresolved status で発生。Phase 3 が誤って `fukusho_hit_raw` を目的変数に使った場合の silent leak 源になる。`is_fukusho_sale_available` も race_cancelled で True になる可能性。

**なぜ自動修正しないか:**
ラベル仕様判断。`fukusho_hit_raw` を 0 に正規化するか NULL にするか、`is_fukusho_sale_available` を False に正規化するかは、`label_spec.yaml` の D-04 仕様（`unresolved` の扱い）と `fukusho_hit_raw smallint NOT NULL` 制約（schema.py）の整合性に依存する。機械的に 0 にすると race_cancelled でも「複勝払戻対象外」ではなく「複勝外れ」という意味論になり、D-04 の「outcome 非確定で unresolved 隔離」設計と衝突する可能性。

**推奨対応:**
1. `label_spec.yaml` の D-04 仕様を再確認し、`fukusho_hit_raw` の race_cancelled 時の扱いを明文化
2. `fukusho_hit_raw smallint NOT NULL` を維持するなら 0 正規化が安全。NULL を許容する schema 変更も選択肢
3. `is_fukusho_sale_available` の race_cancelled 時の正規化は `label_spec.yaml.payout_places_rules` と整合させる
4. Phase 3 features が `fukusho_hit_raw` を使わないことを確認（ドキュメント整備）

---

### CR-05: `_check_payout_precision` / `_check_payout_recall` の JOIN が `monthday` を無視 — cross-join 誤照合リスク

**File:** `src/etl/label_reconcile.py:177-198`, `230-251`

**REVIEW 指摘:**
両検査の JOIN 条件は `(year, jyocd, kaiji, nichiji, racenum)` で `monthday` を含まない。`label.fukusho_label` 側は `monthday` 列を持たない構造的欠陥。同一 race-key で `monthday` が異なるレースが将来導入された場合に silent failure になる。

**なぜ自動修正しないか:**
schema 変更を伴う構造的判断。`label.fukusho_label` に `monthday` 列を追加するか、`normalized.n_race` を経由して `monthday` を取得するかは、`apply_schema.sql` / `fukusho_label.py._LABEL_TABLE_COLUMNS` / 既存 idempotent checksum（WR-07 対象）に影響する。現状の race-key PK 一意性（実測 39,580 = 39,580 distinct）は毎DB更新で要再検証。

**推奨対応:**
1. `apply_schema.sql` に `ALTER TABLE label.fukusho_label ADD COLUMN monthday varchar(4)` を追加
2. `fukusho_label.py._LABEL_TABLE_COLUMNS` / `_df_to_tuples_label` を更新
3. `label_reconcile.py` の precision/recall SQL の JOIN 条件に `monthday` を追加
4. WR-07 の `_LABEL_INSERT_COLUMNS` checksum が変わるため、idempotent テストの期待値を更新
5. `quality_gate.py.N_RACE_PK_COLS` の一意性検証も `monthday` 含めに変更するか別途検討

---

### WR-01: `_check_payout_recall` は dead_heat レースの非対象馬の不当 validated=1 を検知できない

**File:** `src/etl/label_reconcile.py:222-268`, `274-314`

**REVIEW 指摘:**
`is_dead_heat` フラグの誤設定で非対象馬が不当に payout set 扱いになっているケースは、`_check_payout_precision` / `_check_payout_recall` / `_check_dead_heat_integrity` のいずれでも見えない。`_check_dead_heat_integrity` は status↔flag の整合を検査するが、`is_dead_heat` と payout set の実内容（slot4/5 が本当に埋まっているか）の整合は検査しない。

**なぜ自動修正しないか:**
ゲート仕様判断。新規検査（例: `_check_dead_heat_payout_slot_integrity`）を追加するか、既存 `_check_dead_heat_integrity` を拡張するかは、`label_spec.yaml.dead_heat_rules` と D-02（BLOCK/INFO 分離）の整合性に依存。新規 BLOCK 検査を追加すると実DB で gate が fail する可能性がある。

**推奨対応:**
1. `label_spec.yaml.dead_heat_rules` の slot4/5 使用条件を再確認
2. `_check_dead_heat_integrity` に「`is_dead_heat=True` なのに slot4/5 が空」「`payout_count` と `fukusho_payout_places` の比較」の逆方向検査を追加するか、新規 `_check_dead_heat_payout_slot_integrity` を追加
3. 実DB で該当件数を確認し、BLOCK / INFO を判断

---

### WR-04: `is_fukusho_sale_available` / `_payout_places` の境界値が `min_torokutosu` で結合されている構造的脆さ + spec↔impl ずれ

**File:** `src/etl/fukusho_label.py:639-649`, `627-635`, `src/config/label_spec.yaml:33-46`

**REVIEW 指摘:**
`min_torokutosu`（=5）が「複勝発売の有無」と「払戻対象数の下限」の2つの異なる概念に使われており、将来の仕様変更で片方だけ変えた場合に同期が壊れる構造的脆さ。加えて `label_spec.yaml.payout_places_rules.note` は「境界は HR PayFukusyoUmaban/FuseirituFlag2 の観測事実で最終確定（D-01 厳格）」と明記するが、実装は `torokutosu` のみで判定しているため spec と実装がずれている。

**なぜ自動修正しないか:**
仕様判断。`label_spec.yaml` に `fukusho_sale_min_torokutosu`（発売有無の閾値）と `payout_places` 境界（5-7 / 8+）を分離して定義するか、spec の `note` を torokutosu ベースの実装に合わせて訂正するかは、D-01（厳格）と Pitfall 3（torokutosu のみで決定）のどちらを正とするかによる。実DB で 99.97% 一致（39,570/39,580）しているため現状は機能しているが、0.03% の不一致レースの扱いを含む。

**推奨対応:**
1. D-01 と Pitfall 3 の優先順位を確定（02-CONTEXT.md / 02-REVIEWS.md を参照）
2. `label_spec.yaml` を要件的に修正:
   - 分離案: `fukusho_sale_min_torokutosu` と `payout_places` 境界を別キーに
   - 訂正案: `note` を torokutosu ベースに合わせる
3. 実DB の不一致 10 レース（39,580 - 39,570）の原因を個別調査

---

### WR-10: `_select_se_state` の `how="left"` merge で timediff 側の余剰行が検知されない

**File:** `src/etl/fukusho_label.py:218-229`

**REVIEW 指摘:**
`merged = se_df.merge(timediff_df, on=merge_keys, how="left")` は左結合のため:
1. timediff_df 側に SE 側に無い行が存在した場合、右側の余剰行は捨てられ silent に進む
2. 逆方向（timediff 側が SE 側より行が少ない）も、`timediff` 列が NaN になり silent に進む

`merge.assert` は行数増殖のみ検知し、左右の不整合を検知しない。timediff が NaN になることで競走中止馬が正常馬に誤分類される silent leak 源になる可能性。

**なぜ自動修正しないか:**
リーク関連の設計判断。`how="left"` を `how="inner"` に変更し両側一致を強制するか、merge 後に `timediff` 列の NaN 数を assert するかは、`_select_se_state` の契約（timediff 欠損を許容するか否か）に依存。CR-03 で `_is_dh` が NaN を安全に扱うようになったため直ちに crash はしないが、silently 誤分類される経路は残る。WR-05 の両 SELECT フィルタ一致 assertion で「フィルタの退化」は防止できるが、PK レベルの欠損までは検知できない。

**推奨対応:**
1. `_select_se_state` の契約を再確認（timediff 欠損を許容するか否か）
2. `how="inner"` + merge 後の `timediff.isna().sum() == 0` assert を追加する案を検討
3. 実DB で merge 後の `timediff` NaN 件数を確認（現状 0 件なら実害無し）

---

## 要対応 (CR-01 精密化の影響)

**CR-01 精密化により実DB の LABEL-03 gate が7件 validated drift で fail する。**

実DB 確認（prior_decisions に基づく）で判明した genuine な矛盾 7件:
- 5件: 3頭払い（`payout_places=3`）レースで HR の3着馬番（`payfukusyoumaban3`）='00'（記録漏れ）。SE では3着（`kakuteijyuni='03'`）なのに HR 払戻に含まれない → 偽陰性
- 2件: 2020/05 R4。SE と HR で3着の馬番が入れ違っている

これらは LABEL-03 gate で `serious_drift_count > 0` となり `verdict='fail'` になる（**想定通り**）。

**運用対応（別タスク・本 fix 対象外）:**
- 既知7件を許容リスト（allowlist）として `label_reconcile.py` に組み込むか、HR 側のデータ修復を EveryDB2 側で行うかを判断する必要がある
- 許容リスト導入場合は、`label_spec.yaml` に許容対象 race_key を明示し、`_check_raw_validated_drift` で除外する仕組みを追加
- データ修復の場合は、EveryDB2 側の `payfukusyoumaban3` 入力ミスを修正（本プロジェクトの管轄外）

---

## Info (fix_scope 外・本 fix 対象外)

以下5件は `fix_scope=critical_warning` のため本 fix では対応しない（REVIEW.md IN-01〜IN-05）:

- **IN-01:** `compute_is_model_eligible` の `class_level_numeric` が pd.NA のときの regression 未カバー（テスト追加のみ・CR-03 と関連）
- **IN-02:** `test_label_reconcile.py` の mock cursor が SQL 部分文字列マッチで順序依存
- **IN-03:** `time_sentinels_absent` に zero-pad 表現（`"00"` / `"000"` / `"0.00"` 等）が無い
- **IN-04:** `KEIBA_SKIP_DB_TESTS=1` が reconcile gate を silently pass させる
- **IN-05:** `scripts/run_label_etl.py` が `KEIBA_SKIP_DB_TESTS` を見ない — reconcile との不整合

---

## Verification Summary

- **Tier 1 (re-read):** 全修正ファイルを再読み込み、修正が適用されていることを確認
- **Tier 2 (syntax check):** 全修正ファイルで `python -c "import ast; ast.parse(...)"` が pass
- **Test regression:** `KEIBA_SKIP_DB_TESTS=1 .venv/bin/pytest tests/ -q` → `114 passed, 20 skipped in 3.39s`
  - skipped は全て `@pytest.mark.requires_db`（実DB 必須・CI の DB 無し環境で skip）
- **Phase 02 個別:** `tests/test_label_reconcile.py` (18 passed, 1 skipped) + `tests/test_fukusho_label.py` (30 passed)

## Commits (11 commits for 12 finding IDs)

| Finding | Commit | Files |
|---------|--------|-------|
| CR-01 + CR-07 | `b3bf210` | `src/etl/label_reconcile.py`, `tests/test_label_reconcile.py` |
| CR-02 | `0e0895c` | `src/etl/label_reconcile.py` |
| CR-03 | `9474e19` | `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py` |
| CR-06 | `304b1e9` | `src/etl/filters.py`, `src/etl/label_reconcile.py` |
| WR-02 | `446e80b` | `src/etl/label_reconcile.py` |
| WR-03 | `d1c2afb` | `src/etl/label_reconcile.py` |
| WR-05 | `e3c105c` | `src/etl/fukusho_label.py`, `tests/test_fukusho_label.py` |
| WR-06 | `54cd2f0` | `src/etl/fukusho_label.py` |
| WR-07 | `6b1fc56` | `src/etl/fukusho_label.py` |
| WR-08 + WR-09 | `bc7d986` | `src/etl/fukusho_label.py` |
| WR-11 | `236447c` | `scripts/run_label_etl.py` |

**統合の理由:**
- **CR-01 + CR-07:** 同じテスト関数（`test_verdict_pass_when_all_block_pass` と drift テスト群）に触れるため、実装と docstring を1コミットに統合
- **WR-08 + WR-09:** 同じ `run_label_etl` 関数の近接箇所（`settings` 構築直後の read connection ブロック）のため統合

---

_Fixed (iteration 1): 2026-06-18T18:30:00+09:00_
_Fixer: Claude (gsd-code-fixer)_

---

# Iteration 2: WR-04 修正（CR-01 revert の根本原因解決）

**Fixed at:** 2026-06-18T19:50:00+09:00
**Iteration:** 2
**Fixer:** Claude (gsd-code-fixer)
**Trigger:** iteration 1 の CR-01 修正（`_check_raw_validated_drift` の severity を BLOCK に格上げ）が実DB の LABEL-03 gate で7件の validated drift を捕捉し gate fail になった。ユーザーが実DB を個別確認した結果、**7件のうち5件は `payout_places` が `torokutosu`（登録頭数）ベースで計算されていることが根本原因**と判明。CR-01 は誤検知（revert 済み `8bf0ae8`）で、真の原因は WR-04 だった。

## 実DB観測で判明した事実（iteration 1 の前提の誤り）

RESEARCH Pitfall 3 / CONTEXT D-01 / 旧 label_spec.yaml note は「払戻対象頭数は `torokutosu`（登録頭数＝出馬表発表時）ベースで決定。`syussotosu`（最終出走頭数）で決定してはならない」と主張していた。しかし実DB の7件 validated drift を `final_starter_count`（= `syussotosu_i`）で確認した結果:

| レース | 登録頭数 (torokutosu) | 実際出走 (syussotosu) | 旧 payout_places (torokutosu ベース) | 正しい payout_places (syussotosu ベース) | HR 3着馬番 |
|--------|----------------------|---------------------|------------------------------------|---------------------------------------|-----------|
| R10/R11/R8/R9/R1 (5件) | 8-13 | **7** | 3（3頭払い・誤り） | **2（2頭払い）** | '00'（正当・2頭払いの対象外） |
| R4 (2件) | 10 | 10 | 3（3頭払い） | 3（3頭払い） | 別馬番（genuine な馬番入れ違い） |

5件は「登録8頭超だが取消で実際7頭出走」のレース。`torokutosu` ベースの3頭払い計算だと3着馬（`kakuteijyuni='03'`）が `raw=1` になるが、HR は正しく2頭払いで記録（3着 slot='00'）なので `valid=0`。この raw=1 / valid=0 が drift として検出されていた。**正しくは syussotosu ベースの2頭払いで raw=0 となり drift は消失する。**

RESEARCH Pitfall 3 の主張は観測事実と逆だった（当時の観測「SyussoTosu != TorokuTosu が 1,899 レース」は取消/除外レースを指していたが、それらのレースでは **syussotosu ベースが JRA の実際の払戻ルール** と一致する）。

## Summary (iteration 2)

- **WR-04:** `needs_human` → **`fixed`** に昇格（CR-01 の根本原因として判明・コミット `81b7b07`）
- **CR-01:** iteration 1 で適用した severity 格上げ（`b3bf210`）は **誤検知** と判明し revert 済み（`8bf0ae8`）。WR-04 修正後に残る drift は R4 の2件のみ = genuine な馬番入れ違い（EveryDB2 側の入力ミス）。CR-01 の再適用は別タスクで R4 の2件のみを allowlist 対象とする形で検討
- **Fixed (累計):** 12 → **13 件**（WR-04 追加）
- **Needs human (累計):** 5 → **4 件**（WR-04 解消・残り: CR-04, CR-05, WR-01, WR-10）

## Fixed Issues (iteration 2)

### WR-04: `payout_places` を `syussotosu`（実際出走頭数）ベースに修正

**Files modified:** `src/etl/fukusho_label.py`, `src/config/label_spec.yaml`, `tests/test_fukusho_label.py`
**Commit:** `81b7b07`
**Test result:** `KEIBA_SKIP_DB_TESTS=1 pytest tests/` → `116 passed, 20 skipped`（iteration 1 の 114 から +2 net・新規3テスト追加 + 1テスト置換）

**Applied fix:**

1. **`src/etl/fukusho_label.py`** — `merged["fukusho_payout_places"]` の計算ベースを `torokutosu_i.map(_payout_places)` から `syussotosu_i.map(_payout_places)` に変更。取消・除外で `syussotosu < torokutosu` となるレースでは払戻対象頭数が減る（登録8頭でも実7頭出走→2頭払い・2着まで）。ファイル先頭の Pitfall 3 コメント（14行付近）と `_payout_places` のコメント（636行付近）も「syussotosu ベース」に訂正。

2. **`is_fukusho_sale_available` は `torokutosu` のまま（変更なし）** — 複勝発売の有無は出馬表発表時（登録時）に決まるので `torokutosu`（= `sales_start_entry_count` 代理値）ベースが正しい。境界ケース確認: `torokutosu=8`（発売あり）で `syussotosu=4` だと `payout_places=0`（不成立）になるが `is_fukusho_sale_available=True` のまま残る。これは「発売は宣言されたが当日取消で対象頭数に満たず不成立」の正当な状態で、`_check_no_fukusho_sale_not_in_training`（`is_model_eligible=True AND is_fukusho_sale_available=False` を検査）と**論理的に整合**する（逆方向の汚染は起きない）。ただし「発売あり宣言だが不成立」レースの `is_model_eligible` 扱いは将来の検討課題（本 fix の scope 外・自動修正禁止）。

3. **`src/config/label_spec.yaml`** — `payout_places_rules.note` と冒頭コメント（33-46行）を「払戻対象頭数は `syussotosu` ベース」に訂正。旧 Pitfall 3（torokutosu のみで決定）は撤回と明記。**spec↔impl の整合**（WR-04 の核心）を回復。

4. **`tests/test_fukusho_label.py`**:
   - `test_payout_places_uses_torokutosu_not_syussotosu` → `test_payout_places_uses_syussotosu_not_torokutosu` に**置換**（セマンティクス逆転・旧テストは新仕様で fail するため）。torokutosu=8, syussotosu=7 で payout_places=2 を assert。
   - **新規 `test_payout_places_scratch_race_3rd_place_excluded`**: 取消レース（torokutosu=8, syussotosu=7）で3着馬（`kakuteijyuni='03'`）の `raw=0` を assert。HR slot3='00' と整合し drift=0 になることを検証。実DB の5件ドリフトの再現防止回帰テスト。
   - **新規 `test_payout_places_normal_race_8_starters_3_places_regression`**: torokutosu=syussotosu=8 の通常レースは3頭払いのままであることを検証（取消の無いレースへの影響がないことの保証）。
   - **新規 `test_payout_places_syussotosu_missing_returns_no_sale`**: `syussotosu` が pd.NA / None / "" / "abc" のとき payout_places=0（no_sale）になることを検証（D-13 silent fallback 禁止・安全側）。
   - **CR-03 regression test 更新**: `test_payout_places_and_is_dh_handle_pd_na_and_abnormal_values` の駆動値を `torokutosu` から `syussotosu` に切替（計算ベース変更に追随・torokutosu='8' は固定）。

**Logic bug flag:** 本修正は `payout_places` 計算ベースの変更（意味論的）のため、Tier 1/2 自動検証では実DB での正しさを完全に保証できない。追加した3テスト（特に `test_payout_places_scratch_race_3rd_place_excluded` が実DB の5件ドリフトシナリオを再現）でカバーしているが、実DB での LABEL-03 gate 実行による最終確認が推奨される。

## Skipped Issues (iteration 2)

なし。WR-04 は iteration 1 では `needs_human` だったが、ユーザーによる実DB 個別確認で仕様判断が確定したため iteration 2 で fixed に昇格。

---

## 要対応 (iteration 2 時点・残課題)

### CR-01 の再適用検討（WR-04 修正後）

WR-04 修正により7件の validated drift のうち5件は解消される。残るは **R4 の2件**（2020/05 R4・torokutosu=10, syussotosu=10・3頭払い正しい・SE と HR で3着の馬番が入れ違っている genuine な矛盾）。

**推奨対応（別タスク）:**
1. WR-04 修正を適用した上で実DB の LABEL-03 gate を再実行し、drift が R4 の2件のみになることを確認
2. R4 の2件を allowlist（`label_spec.yaml` に race_key 明示）するか、EveryDB2 側で `payfukusyoumaban3` 入力ミスを修復するかを判断
3. allowlist 導入後に CR-01 の severity 格上げ（`_check_raw_validated_drift` の validated/inferred status での BLOCK 化）を再適用するか判断

### `is_fukusho_sale_available` 境界ケースの将来検討

`torokutosu=8`（発売あり宣言）で `syussotosu < 5`（当日取消で対象頭数未満）のレースは `payout_places=0`（不成立）だが `is_fukusho_sale_available=True` のまま残る。これは「発売は宣言されたが不成立」の正当な状態だが、`compute_is_model_eligible` のステップ (c)（`not is_fukusho_sale_available` → no_fukusho_sale）では捕捉されない。実DB で該当件数を確認し、必要なら `payout_places <= 0` の行を `no_fukusho_sale` で不適格にする追加検査を検討（本 fix の scope 外）。

---

_Fixed (iteration 2): 2026-06-18T19:50:00+09:00_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
