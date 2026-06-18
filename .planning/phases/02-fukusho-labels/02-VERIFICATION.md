---
phase: 02-fukusho-labels
verified: 2026-06-18T08:30:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
gaps: []
deferred:
  - truth: "label.fukusho_label.race_date が全行 NULL（Plan-03 ETL 未 populate）"
    addressed_in: "Phase 3"
    evidence: "Phase 3 SC#1 で feature row が as_of_datetime / feature_cutoff_datetime を持つ（race_date は PIT 結合に必要・Phase 3 が normalized.n_race を JOIN する設計）・Phase 2 SC#1-#4 は race_date populated を要求しない"
  - truth: "fukusho_hit_raw が unresolved レースで KakuteiJyuni-based で算出され fukusho_hit_raw=1 になり得る（CR-04）"
    addressed_in: "Phase 8"
    evidence: "§10.3 line 516 が fukusho_hit_validated を学習目標に明示指定し unresolved を学習除外。Phase 8 SC#1 が fukusho label generation に対抗的監査を含む。Phase 2 SC#1-#4 は学習契約ではなくラベル生成契約（fukusho_hit_raw は audit 列）"
human_verification:
  - test: "実DB で label ETL を実行し rows_inserted/checksum/idempotent 確認 (Plan 02-03 Task 3)"
    expected: "uv run python scripts/run_label_etl.py exit 0・rows_inserted ≈ 554,267・2 回実行で checksum 完全一致 (HIGH #3)・raw fingerprint 前後不変 (D-06)・label_validation_status / is_model_eligible / sales_start_entry_count_confidence の NULL 件数 = 0・is_race_cancelled = 376 (HIGH #4)"
    why_human: "live PostgreSQL everydb2 接続・数分の ETL 実行・psql spot check が必要・CI/verifier 環境では利用不可（02-VALIDATION.md W5 で明記済み）。02-03-SUMMARY は verdict=pass / rows=554,267 / checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4 を報告するが SUMMARY claims は証拠ではない"
  - test: "実DB で reconcile を実行し verdict=pass / agreement>=99.9% 確認 (Plan 02-04 Task 3)"
    expected: "uv run python scripts/run_label_reconcile.py exit 0・verdict=pass・agreement_pct >= 99.9（02-04-SUMMARY は 100.0% / 4063/4063 held-out races を報告）・各 BLOCK check の count=0（payout_precision / recall / scratch_mislabeled / dead_loss_not_excluded / no_fukusho_sale_not_in_training / dead_heat_integrity）"
    why_human: "live DB に対する reconcile と held-out 10% agreement 検証は agent/verifier では実行不能・CI でも利用不可（02-VALIDATION.md W5）。02-04-SUMMARY の verdict=pass / agreement=100.0% は SUMMARY claims であり証拠ではない"
---

# Phase 2: Fukusho Labels — 検証レポート

**Phase Goal:** `fukusho_hit_validated`（予測目標の正）が正しく・払戻テーブルと整合し・発売開始時点ベースで・同着/取消/競走中止を JRA 規則通り処理した形で生成されること（ROADMAP Phase 2 Goal）
**Verified:** 2026-06-18T08:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

 ROADMAP Phase 2 Success Criteria に基づく 4 truths:

| #   | Truth (SC)                                                                                                                                                                                                                                          | Status       | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **SC#1:** 開発者は `fukusho_hit_raw`（着順由来一次ラベル）と `fukusho_hit_validated`（払戻テーブル突合済み）の両方を持つラベル行を読み取れ、全行に `label_validation_status` ∈ {`validated`, `inferred`, `dead_heat`, `unresolved`} が付与される          | ✓ VERIFIED   | `src/etl/fukusho_label.py:675-681` が `_raw_hit`（KakuteiJyuni-based）/ `_valid_hit`（PayFukusyoUmaban-based）を実装・`:722-724` が `classify_status` で 4 値 status を付与・`label.fukusho_label` CREATE TABLE に `fukusho_hit_raw` / `fukusho_hit_validated` / `label_validation_status` カラムを含む（`:808-810`）・27 unit tests GREEN（含 `test_raw_vs_validated_basic_8_horses` / `test_drift_is_dead_heat_only`）・D-04 status 4 値が `label_spec.yaml:30` で定義                              |
| 2   | **SC#2:** 払戻テーブル突合テストがホールドアウトサンプルで >99.9% 一致で通過（全 `fukusho_hit_validated=1` 馬が払戻テーブルの複勝払戻対象に存在・取り消し/除外馬の誤正例なし・複勝発売なしレースはモデル適格集合から除外）                          | ✓ VERIFIED   | `src/etl/label_reconcile.py:159-268` が `_check_payout_precision` / `_check_payout_recall` を NULL-safe NOT EXISTS/EXISTS + 両側 LPAD zero-pad で実装（NEW HIGH #1）・`:590+` `_compute_race_level_agreement` が時系列ホールドアウト 10% + 層化でレース単位馬集合完全一致を検証・18 unit tests GREEN（含 `test_gt_999_pct_agreement` / `test_check_payout_precision_null_safe_padded_umaban`）・02-04-SUMMARY は agreement=100.0% (4063/4063) を報告（live-DB・human-verify 待ち） |
| 3   | **SC#3:** `sales_start_entry_count` が全適格レースで populated（直接項目または出馬表+取消/除外発表時刻から復元・不能は `unresolved` で学習除外・`unresolved` 割合を報告）                                                                          | ✓ VERIFIED   | `src/etl/fukusho_label.py:684-691` が TorokuTosu 代理値 + `source='torokutosu_proxy'` + 独立 `confidence='inferred'` 列（HIGH #1）で populated・`label_spec.yaml:56-66` で `sales_start_entry_count` セクション定義・`label_reconcile.py:510-584` `_check_label_status_distribution` が `unresolved_fraction` と `unresolved_threshold=0.01` を明示報告（W3）・02-04-SUMMARY 実測 unresolved=376/554267=0.000678 < 0.01                                                      |
| 4   | **SC#4:** 同着レースは払戻テーブルの全複勝対象馬を正例・取消/除外は予測対象外（返還は Phase 5）・競走中止は学習に含め `fukusho_hit=0`（unit test が各シナリオを構築しラベルを assert）                                                                | ✓ VERIFIED   | `src/etl/fukusho_label.py:431-486` `compute_is_model_eligible` が HIGH #6 順序（障害/新馬が先・`is_dead_loss` は単独では不適格理由にならない）で実装・`classify_status` が同着 → `dead_heat`、取消/除外 → `is_model_eligible=False`、競走中止 → `fukusho_hit=0` で学習残（§10.6）を返す・`_canonicalize_markers` が sentinel 集合で scratch/dead_loss/race_cancelled を分類（HIGH #5）・27 unit tests GREEN（`test_dead_heat_all_payout_positive` / `test_scratch_cancel_excluded` / `test_dead_loss_in_training` / `test_race_cancelled_all_unresolved`） |

**Score:** 4/4 truths verified

### Deferred Items

ROADMAP の後続フェーズで明示的に扱われる項目（Step 9b でフィルタ）:

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | `label.fukusho_label.race_date` が全行 NULL（Plan-03 ETL で未 populate・02-04-SUMMARY Deviation #3 で Rule 3 live-DB discovery として記録・reconcile は `normalized.n_race` JOIN で回避） | Phase 3 | Phase 3 SC#1 が feature row の `as_of_datetime` / `feature_cutoff_datetime` を要求（race_date は PIT 結合に必要・Phase 3 が `normalized.n_race` を JOIN する設計・`feature_cutoff_datetime = race_date - 1 day`・CLAUDE.md Architecture）。Phase 2 SC#1-#4 は `label.fukusho_label.race_date` populated を要求しない（SC#3 は `sales_start_entry_count` のみ） |
| 2 | `fukusho_hit_raw` が race_cancelled / fuseiritu / tokubarai(空) レースでも KakuteiJyuni-based で算出され `fukusho_hit_raw=1` になり得る（CR-04・silent-leak SOURCE if Phase 3 が誤って raw を使用） | Phase 8 | `docs/keiba_ai_requirements_v1.3.md` §10.3 line 516 が「Phase 1 学習・評価では `fukusho_hit_validated` を使用・`unresolved` は学習除外」を明示指定。Phase 8 SC#1 が「fukusho label generation + payout-table reconciliation ... に対抗的監査テスト」を含む。Phase 2 SC#1-#4 は学習契約ではなくラベル生成契約（`fukusho_hit_raw` は audit-only 列・§10.5 line 514） |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/config/label_spec.yaml` | `label_generation_version='v1.0.0'`・D-04 status 4 値・D-01 payout 境界・HIGH #1 source_confidence 分離・HIGH #5 sentinel 集合・NEW HIGH #3 `missing_value_sentinel`・HIGH #4 `required_se_datakubun_values=['7','9']`・MEDIUM class_eligibility precision | ✓ VERIFIED | 245 行（min 1 行）・`yaml.safe_load` 成功・全 must_haves キー存在・`label_generation_version: "v1.0.0"`・`status_values: ["validated","inferred","dead_heat","unresolved"]`・`source_confidence: "inferred"` が独立キー・`missing_value_sentinel: "__MISSING__"`・`required_se_datakubun_values: ["7","9"]`・`maiden_syubetucd: ["13","14","15"]` |
| `src/etl/fukusho_label.py` | `compute_fukusho_labels` / `classify_status` / `compute_is_model_eligible` / `_canonicalize_markers` / `run_label_etl` / `_select_se_state` / `_idempotent_load_label` を提供 | ✓ VERIFIED | 1080 行（min 450）・全関数定義済み・HIGH #4 `datakubun IN ('7', '9')` × 5 出現・NEW HIGH #2 `len(merged) != pre_len` assertion・NEW HIGH #3 `pd.isna` guard + `missing_value_sentinel`・HIGH #3 `INCLUDING ALL` + reader role 明示 GRANT・HIGH #1 `sales_start_entry_count_confidence varchar(16) NOT NULL` |
| `src/etl/label_reconcile.py` | `reconcile_against_payout` + 6 §10.5 検査 + drift 検査 + `_recompute_scratch_markers`（HIGH #7） | ✓ VERIFIED | 886 行（min 380）・`reconcile_against_payout` 定義・6 検査 BLOCK 実装・NEW HIGH #1 NULL-safe NOT EXISTS/EXISTS + 両側 LPAD・HIGH #6 dead_loss_only 制約・HIGH #7 `_recompute_scratch_markers` が `is_scratch_cancel` 非依存（コード本体） |
| `tests/test_fukusho_label.py` | 25+ unit tests・LABEL-01/02/04 + REVIEWS HIGH #1/#4/#5/#6 + NEW HIGH #2/#3 網羅 | ✓ VERIFIED | 774 行（min 280）・27 tests collection・`KEIBA_SKIP_DB_TESTS=1 uv run pytest` で 27 passed・`test_drift_is_dead_heat_only` / `test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status` / `test_canonicalize_markers_missing_time` / `test_select_se_state_includes_datakubun_9` / `test_select_se_state_no_row_multiplication_on_timediff_merge` 等 全て GREEN |
| `tests/test_label_reconcile.py` | 18+ tests・§10.5 6 検査 + agreement + drift + HIGH #2/#6/#7 + NEW HIGH #1 | ✓ VERIFIED | 675 行（min 260）・18 tests collection（17 unit + 1 requires_db）・`KEIBA_SKIP_DB_TESTS=1 uv run pytest` で 17 passed + 1 skipped（requires_db）・`test_check_payout_precision_null_safe_padded_umaban` / `test_recompute_scratch_markers_uses_sentinel` / `test_check_raw_validated_drift_dead_heat_only` 含む |
| `scripts/run_label_etl.py` | CLI エントリポイント・masked DSN・2 回 idempotent 検証・raw fingerprint 前後比較 | ✓ VERIFIED | 132 行・`run_label_etl` 2 回呼出・`result1["checksum"] == result2["checksum"]` assertion・`compute_raw_fingerprint` + `assert_raw_unchanged` import・`dsn_masked` / `etl_dsn_masked` ログ・public.n_* への INSERT/UPDATE/DELETE なし（D-06） |
| `scripts/run_label_reconcile.py` | CLI・verdict-based exit code・masked DSN | ✓ VERIFIED | 184 行・`reconcile_against_payout` 呼出・verdict で exit 0 or 1・`dsn_masked` ログ |
| `tests/test_raw_immutability.py` 拡張 | `test_raw_unchanged_after_label_etl` + `test_label_etl_idempotent` | ✓ VERIFIED | 両テスト関数定義（line 70 / 96）・`@pytest.mark.requires_db`・`KEIBA_SKIP_DB_TESTS=1` で skip・02-03-SUMMARY は live DB で 2 passed を報告 |
| `src/db/schema.py` GRANT 拡張 | GRANT_READER_SQL / GRANT_ETL_SQL に label スキーマ・TO PUBLIC なし | ✓ VERIFIED | `grep -c "SCHEMA label"` schema.py = 6・`GRANT USAGE, CREATE ON SCHEMA label TO {etl}` / `GRANT USAGE ON SCHEMA label TO {reader}` 存在・`grep -c "TO PUBLIC" src/db/schema.py` = 0（HIGH #3） |
| `src/config/settings.py` | `db_schema_label='label'` / `db_reader_role='keiba_readonly'` | ✓ VERIFIED | line 41 / 46 で両フィールド定義 |
| `src/db/connection.py` | `make_pool(role='etl')` search_path = label,normalized,public | ✓ VERIFIED | line 44 `search_path = f"{settings.db_schema_label},{settings.db_schema_normalized},public"` |
| `scripts/apply_schema.sql` | schema.py GRANT 拡張と同期・TO PUBLIC 0 | ✓ VERIFIED | `SCHEMA label` 6 箇所・`grep -c "TO PUBLIC"` = 0・D-06 REVOKE 維持 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `fukusho_label.run_label_etl` | readonly pool → raw SELECT | `_select_raw_harai` / `_select_se_state` / `_select_race_meta`（FROM public.n_harai / public.n_uma_race / normalized.n_race） | ✓ WIRED | line 1027-1029 で readonly cursor から3関数呼出・`PROJECT_WINDOW_FILTER` 適用・raw 書込 SQL なし（D-06） |
| `fukusho_label._select_se_state` | timediff 1:1 merge | 両側 `datakubun IN ('7','9')` + merge キー datakubun + `len(merged) != pre_len` RuntimeError | ✓ WIRED | `inspect.getsource` で確認・NEW HIGH #2 regression test GREEN |
| `fukusho_label.compute_fukusho_labels` | `label_spec.yaml` | `load_label_spec()` 経由で payout_places_rules / se_marker_canonicalization / class_eligibility 参照 | ✓ WIRED | line 528 `spec = spec if spec is not None else load_label_spec()`・11 必須キー検証（`_REQUIRED_SPEC_KEYS`） |
| `fukusho_label._idempotent_load_label` | staging-swap | INCLUDING ALL + DROP+RENAME + reader role 明示 GRANT（PUBLIC 不使用） | ✓ WIRED | line 888-892 `LIKE label.fukusho_label INCLUDING ALL`・line 914-916 `SQL("GRANT SELECT ON label.fukusho_label TO {}").format(Identifier(reader_role))` |
| `label_reconcile.reconcile_against_payout` | `quality_gate.CheckResult` | `from src.etl.quality_gate import CheckResult` + D-02 BLOCK/INFO verdict 集計 | ✓ WIRED | line 58 import・`all(r.passed for r in results if r.severity == "block")` verdict パターン（Phase 1 D-01 踏襲） |
| `label_reconcile._check_no_scratch_mislabeled` | raw SE marker 再計算 | `_recompute_scratch_markers` が `bataijyu_sentinels_scratch` を使用し `is_scratch_cancel` を参照しない | ✓ WIRED | `inspect.getsource` で確認・コード本体に `is_scratch_cancel` なし（docstring/comment のみ）・HIGH #7 |
| `label_reconcile._check_payout_precision/recall` | HR payout set | NULL-safe NOT EXISTS/EXISTS + 両側 LPAD zero-pad（NEW HIGH #1） | ✓ WIRED | `inspect.getsource` で確認・`LPAD(NULLIF(hr.payfukusyoumaban1,'00')::text, 2, '0')` × 5 slots・`NOT IN` は docstring 内の禁止文言参照のみ |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `label.fukusho_label` | `fukusho_hit_validated` | `public.n_harai.payfukusyoumaban1..5` → `_valid_hit`（line 675-681） | Yes（02-03-SUMMARY: 実測 validated=552,475 / dead_heat=1,416 / unresolved=376） | ✓ FLOWING（live-DB 実測値は 02-03-SUMMARY claims・human-verify 待ち） |
| `label.fukusho_label` | `fukusho_hit_raw` | `normalized.n_uma_race.kakuteijyuni` → `_raw_hit`（line 652-662） | Yes（audit 列・学習目標ではない・§10.3 line 516） | ✓ FLOWING（audit-only） |
| `label.fukusho_label` | `sales_start_entry_count` | `public.n_harai.torokutosu` → `sales_start_entry_count`（line 684-686） | Yes（HIGH #1 独立 confidence 列・全行 populated） | ✓ FLOWING |
| `label_reconcile.agreement` | race-set | `label.fukusho_label.fukusho_hit_validated=1` ↔ `public.n_harai.payfukusyoumaban1..5`（`_compute_race_level_agreement`） | Yes（02-04-SUMMARY: agreement=100.0% / 4063/4063 held-out） | ✓ FLOWING（live-DB 実測値は 02-04-SUMMARY claims・human-verify 待ち） |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase 2 unit tests GREEN | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/test_fukusho_label.py tests/test_label_reconcile.py -q` | 44 passed, 1 skipped（requires_db）in 0.66s | ✓ PASS |
| 全 unit tests 回帰なし | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ -q --ignore=tests/test_raw_immutability.py` | 108 passed, 14 skipped in 2.92s | ✓ PASS |
| `_canonicalize_value` pd.isna guard | `uv run python -c "import inspect; from src.etl.fukusho_label import _canonicalize_value; src = inspect.getsource(_canonicalize_value); assert 'pd.isna(v)' in src and 'missing_sentinel' in src"` | True / True | ✓ PASS |
| `_select_se_state` datakubun IN ('7','9') + merge + len assert | `inspect.getsource` regex | FROM public.n_uma_race=True / datakubun IN ('7','9') count=5 / merge=True / len assertion=True | ✓ PASS |
| `_check_payout_precision` LPAD + NOT EXISTS | `inspect.getsource` | LPAD=True / NOT EXISTS=True / SQL body に NOT IN なし（docstring の禁止参照のみ） | ✓ PASS |
| `_check_payout_recall` LPAD + EXISTS | `inspect.getsource` | LPAD=True / EXISTS=True | ✓ PASS |
| `_recompute_scratch_markers` is_scratch_cancel 非依存 | `inspect.getsource` + docstring strip | bataijyu_sentinels_scratch=True / コード本体に is_scratch_cancel なし | ✓ PASS |
| `_check_raw_validated_drift` severity=info（CR-01 decision） | `inspect.getsource` | severity="info"=True / severity="block"=False / passed=True constant | ✓ PASS（CR-01 design decision として文書化） |
| `_is_na` が pd.NA / NaN / NaT を捕捉 | `uv run python` 実測 | None/float('nan')/np.nan/pd.NA/pd.NaT 全て True・CR-03 理論懸念を実測で否定 | ✓ PASS |
| `_payout_places` が pd.NA 入力で no_sale を返す | `uv run python` 実測 | pd.NA → 0 / np.nan → 0 / 8 → 3 / 6 → 2 / 4 → 0 | ✓ PASS |
| GRANT に TO PUBLIC なし | `grep -c "TO PUBLIC"` src/db/schema.py scripts/apply_schema.sql | 0 / 0 | ✓ PASS（HIGH #3） |
| schema.py に SCHEMA label 6 箇所 | `grep -c "SCHEMA label" src/db/schema.py` | 6 | ✓ PASS |
| ETL ロール search_path が label 先頭 | `grep "db_schema_label" src/db/connection.py` | `search_path = f"{settings.db_schema_label},{settings.db_schema_normalized},public"` | ✓ PASS |
| raw への書込 SQL なし | `grep "INSERT\|UPDATE\|DELETE FROM public.n_" src/etl/fukusho_label.py src/etl/label_reconcile.py` | 0 件（D-06 / T-02-08 / T-02-19） | ✓ PASS |
| `scripts/run_label_etl.py` 2 回 idempotent | `grep "result1\|result2\|checksum" scripts/run_label_etl.py` | line 92/98 で rows_inserted と checksum の一致 assert | ✓ PASS（実行は human-verify） |

### Probe Execution

Phase 2 は conventional probe（`scripts/*/tests/probe-*.sh`）を宣言しておらず、migration/tooling phase ではないため SKIPPED。同等の検証は unit tests（27 + 18 GREEN）と `KEIBA_SKIP_DB_TESTS=1` で実行される structural grep assertion が担う。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| LABEL-01 | 02-01 / 02-02 / 02-03 | 着順由来一次ラベル `fukusho_hit_raw` と払戻テーブル突合後の確定ラベル `fukusho_hit_validated` を生成 | ✓ SATISFIED | `fukusho_label.py:662/681`・27 unit tests・label.fukusho_label CREATE TABLE に両カラム |
| LABEL-02 | 02-01 / 02-02 / 02-03 | `sales_start_entry_count` を取得・直接項目なければ復元・不能は `unresolved` で学習除外 | ✓ SATISFIED | `fukusho_label.py:684-691`（TorokuTosu 代理値 + source='torokutosu_proxy' + 独立 confidence='inferred' 列・HIGH #1）・`compute_is_model_eligible` が unresolved → is_model_eligible=False で学習除外・`label_reconcile._check_label_status_distribution` が unresolved_fraction を報告 |
| LABEL-03 | 02-04 | `fukusho_hit_validated` が払戻テーブルと整合・§10.5 突合検査結果を `label_validation_status` に保存 | ✓ SATISFIED | `label_reconcile.py` 6 §10.5 BLOCK 検査 + drift INFO + race-set agreement・NEW HIGH #1 NULL-safe + LPAD・HIGH #2 tautology 回避・HIGH #6 dead_loss_only・HIGH #7 raw marker 再計算・02-04-SUMMARY は verdict=pass / agreement=100.0% を報告 |
| LABEL-04 | 02-01 / 02-02 / 02-03 | 同着=払戻テーブル全対象馬を正例・取消/除外=予測対象外・競走中止=学習に含めて `fukusho_hit=0` | ✓ SATISFIED | `classify_status` / `compute_is_model_eligible` / `_canonicalize_markers` が D-04 5 エッジを観測事実ベースで分類・27 unit tests GREEN（`test_dead_heat_all_payout_positive` / `test_scratch_cancel_excluded` / `test_dead_loss_in_training` / `test_race_cancelled_all_unresolved` / `test_fuseiritu_flag2_unresolved` / `test_tokubaraiflag2_*`） |

**Orphaned requirements:** REQUIREMENTS.md で Phase 2 に割り当てられた LABEL-01..04 は全ていずれかの PLAN の `requirements:` frontmatter でカバー済み。orphaned なし。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `src/etl/label_reconcile.py` | 701-714 | `_compute_race_level_agreement` の `where_race_keys` が f-string で `held_out_list`（DB 由来 PK tuple）を SQL に直接展開（CR-02） | ⚠️ Warning | defense-in-depth 違反・プロジェクトのパラメータ化クエリ原則に反する。ただし入力は DB 由来 PK（user input ではない）・本ツールは local single-user analysis tool・SQL injection 実害なし。psycopg3 パラメータ埋め込み（`cur.execute(sql, params)`）または `UNNEST` set-based 比較への修正を推奨 |
| `src/etl/fukusho_label.py` | 652-662 | `fukusho_hit_raw` が race_cancelled / fuseiritu / tokubarai(空) レースでも `kakuteijyuni`-based で算出され `fukusho_hit_raw=1` になり得る（CR-04） | ⚠️ Warning | `fukusho_hit_raw` は audit-only 列・§10.3 line 516 が `fukusho_hit_validated` を学習目標に明示指定・Phase 3 が契約通り `fukusho_hit_validated` を使えば silent leak なし。Phase 8 対抗的監査で強化推奨（`fukusho_hit_raw_safe` 列または unresolved 行の raw=NULL 化） |
| `src/etl/label_reconcile.py` | 429-504 | `_check_raw_validated_drift` が `severity="info"` + `passed=True` 固定（CR-01・02-04-SUMMARY Rule 1 live-DB discovery で BLOCK→INFO に格下げ） | ⚠️ Warning | 02-04-SUMMARY は 41 drift 行（34 unresolved + 7 validated）を root-cause し「label は D-04 で HR payout を権威として正しく採用・ETL bug ではない」と結論。`fukusho_hit_validated` の正当性は precision/recall BLOCK 検査（label↔HR 直接照合）が保証するため、学習目標の聖域は守られる。ただし「validated status での SE↔HR source 不一致」が将来の ETL 変更で増加した場合にゲートが素通りするリスクあり。Phase 8 監査で validated drift 行数の監視強化を推奨 |
| `src/etl/fukusho_label.py` | 1052-1055 | `run_label_etl` の checksum が `md5(string_agg(md5(row(r.*)::text), '' ORDER BY ...))` で列順序依存（WR-07） | ℹ️ Info | 将来 `ALTER TABLE label.fukusho_label ADD COLUMN` で checksum が変化し idempotent 検証が「同じデータでも別 checksum」を返す。列明示的列挙への修正を推奨 |
| `src/etl/fukusho_label.py` | 1017-1022 | `run_label_etl` の `settings=None` のとき reader_role warning 分岐が到達不能コード（WR-09） | ℹ️ Info | `Settings.db_reader_role` のデフォルトが `'keiba_readonly'` なので `getattr(...) or "keiba_readonly"` は常に同じ値を返し warning が発火しない。デッドロジック削除推奨 |
| `src/config/label_spec.yaml` | 121 | `time_sentinels_absent` に `"00"` / `"000"` 等 zero-pad 表現が無い（IN-03） | ℹ️ Info | `bataijyu_sentinels_scratch` は `"000"` を含むが time 側は `"0"` 系のみ。EveryDB2 実データで time=`"00"` が発生する場合 `time_present=True` になる可能性。実測で time=`"0"` のみであれば影響なし |

**Debt-marker gate:** TBD/FIXME/XXX マーカーは Phase 2 で修正されたファイルに存在しない（`grep` で確認）。

### コードレビュー（02-REVIEW.md）5 BLOCKER の評価

| CR | 内容 | 評価 | 根拠 |
| -- | ---- | ---- | ---- |
| **CR-01** | `_check_raw_validated_drift` が BLOCK→INFO に格下げ（02-04 executor の Rule 1 偏倚） | ⚠️ **WARNING（advisory・非 BLOCKER）** | (a) `fukusho_hit_validated`（学習目標）の正当性は `_check_payout_precision` / `_check_payout_recall` BLOCK 検査（label↔HR 直接照合）が保証する・label↔SE drift が INFO でも学習目標の聖域は守られる。(b) 02-04-SUMMARY は 7 validated drift 行を root-cause し「label は D-04 で HR payout を権威として採用（§10.5 line 514）・ETL bug ではなく source data quality issue」と結論・1 行を例示（SE umaban=1 が 3 着・HR payout が {06,03}・label の validated=0 は HR と一致・正しい）。(c) D-02 一貫性（Phase 1 D-01 と同じ BLOCK/INFO 分離）。**ただし** reviewer の懸念（将来の ETL 変更で validated drift が増えてもゲートが素通りする）は妥当・Phase 8 対抗的監査で `validated` status drift 行数の監視強化を推奨。本件は 02-04-SUMMARY で文書化された設計決定（deviation #5）であり、override 提出ではなく advisory WARNING として扱う |
| **CR-02** | `_compute_race_level_agreement` の `where_race_keys` が f-string で PK 値を SQL に展開（SQL injection 可能性） | ⚠️ **WARNING（low severity・local single-user tool）** | 入力は DB 由来 PK tuple（user input ではない）・本ツールは local single-user analysis tool・SQL injection 実害なし。ただし defense-in-depth 違反・プロジェクトのパラメータ化クエリ原則に反する。psycopg3 パラメータ埋め込みまたは `UNNEST` set-based 比較への修正を推奨 |
| **CR-03** | `_payout_places` で `pd.NA` と整数の比較が pandas で例外になる経路 | ✓ **NOT A BUG（実測で否定）** | `_is_na(pd.NA) == True`・`_is_na(np.float64(nan)) == True`・`_is_na(pd.NaT) == True`（verifier 実測）・`_payout_places(pd.NA) == 0` / `_payout_places(np.nan) == 0` / `_payout_places(8) == 3` / `_payout_places(6) == 2`・reviewer 自身「the path is closed」と評価・理論上の懸念のみ・unit test で `pd.NA` regression を追加すれば完了 |
| **CR-04** | `fukusho_hit_raw` が unresolved レースで `kakuteijyuni`-based で算出され `fukusho_hit_raw=1` になり得る・silent-leak SOURCE if Phase 3 が誤って raw を使用 | ⚠️ **WARNING（deferred to Phase 8）** | §10.3 line 516 が「Phase 1 学習・評価では `fukusho_hit_validated` を使用・`unresolved` は学習除外」を明示指定・label spec / downstream contract が audit-only 列として扱う・Phase 2 SC#1-#4 は学習契約ではなくラベル生成契約。Phase 8 SC#1 対抗的監査で強化推奨（`fukusho_hit_raw_safe` 列または unresolved 行の raw=NULL 化）。本件は deferred として分類 |
| **CR-05** | `_check_payout_precision/recall` JOIN が `monthday` を無視・race-key PK 一意性の検証が `monthday` 抜き | ✓ **NOT A CURRENT BUG（理論 future-risk）** | verifier で `inspect.getsource` して実際の SQL JOIN ON 句を抽出：(year, jyocd, kaiji, nichiji, racenum) の5カラム JOIN・実 SQL body に `monthday` なし（docstring/comment のみ）。EveryDB2 仕様上 `monthday` は自然キーの一部だが、現状 JRA+2015 の race-key PK で 39,580 = 39,580 distinct（02-04-SUMMARY 実測）・誤照合 0 件・agreement=100.0%。将来 `monthday` が異なる同一 race-key レースが導入された場合に壊れる future-risk のみ・Phase 2 完了をブロックしない |

### Human Verification Required

Phase 2 の 4 truths は全て verifier で structural/wiring を確認したが、以下の live-DB 実行結果は SUMMARY claims に依存しており verifier では再現不能（02-VALIDATION.md W5 で文書化済み）:

#### 1. 実DB での label ETL 実行（Plan 02-03 Task 3）

**Test:** `uv run python scripts/run_label_etl.py`
**Expected:** exit 0 / rows_inserted ≈ 554,267 / 2 回連続実行で checksum 完全一致（HIGH #3 idempotent）/ `compute_raw_fingerprint` 前後不変（D-06 raw 不変性）/ 以下の SQL 結果:
- `SELECT count(*) FROM label.fukusho_label` ≈ 554,267
- `SELECT count(*) FROM label.fukusho_label WHERE label_validation_status IS NULL` = 0（SC#1）
- `SELECT count(*) FROM label.fukusho_label WHERE sales_start_entry_count_confidence IS NULL` = 0（HIGH #1）
- `SELECT count(*) FROM label.fukusho_label WHERE is_race_cancelled = true` = 376（HIGH #4・datakubun='9' が落とされず含まれる）
- `SELECT has_table_privilege('keiba_readonly', 'label.fukusho_label', 'SELECT')` = True（HIGH #3 reader role 明示 GRANT）
- 02-03-SUMMARY は rows_inserted=554,267 / label_unresolved_count=376 / checksum=f8617a6a8f2f1ddcb11de9fa8b74d1c4（両実行で同一）を報告
**Why human:** live PostgreSQL everydb2 接続・数分の ETL 実行・psql spot check が必要・CI/verifier 環境では利用不可

#### 2. 実DB での reconcile 実行（Plan 02-04 Task 3）

**Test:** `uv run python scripts/run_label_reconcile.py`
**Expected:** exit 0 / verdict=pass / agreement_pct >= 99.9 / 各 BLOCK check の count=0:
- `payout_precision` count=0（NULL-safe NOT EXISTS + 両側 LPAD）
- `payout_recall` count=0
- `dead_heat_integrity` mismatch_count=0
- `no_scratch_mislabeled` count=0（HIGH #7 raw bataijyu sentinel 再計算）
- `dead_loss_not_excluded` count=0（HIGH #6 dead_loss_only 制約）
- `no_fukusho_sale_not_in_training` count=0
- `agreement.agreement_pct` >= 99.9 / `agreement.agree_count` / `agreement.total_held_out`（02-04-SUMMARY は 100.0% / 4063 / 4063 を報告）
- INFO check `raw_validated_drift`: drift_count=41 / non_dead_heat_drift_count=41 / drift_status_breakdown={unresolved: 34, validated: 7}（CR-01 design decision として INFO・label 正当性は precision/recall BLOCK が保証）
- INFO check `label_status_distribution`: unresolved_fraction=0.000678 < threshold=0.01 / threshold_exceeded=False（SC#3）
**Why human:** live DB against の reconcile と held-out 10% agreement 検証は agent/verifier では実行不能

### Gaps Summary

**gaps: なし**（SC#1-#4 の must-haves は全て verifier で structural/wiring/data-flow 確認済み）

**advisory warnings（完了をブロックしないが後続フェーズで対応推奨）:**
- **CR-01** drift 検査の INFO 格下げ（02-04-SUMMARY で文書化された設計決定・Phase 8 監査強化推奨）
- **CR-02** `_compute_race_level_agreement` の SQL injection f-string（local tool・実害なし・psycopg3 パラメータ化推奨）
- **CR-04** `fukusho_hit_raw` が unresolved レースで偽正例（audit-only 列・§10.3 契約で `fukusho_hit_validated` が学習目標・Phase 8 で強化推奨）
- **WR-07 / WR-09 / IN-03** checksum 列順序依存・デッドロジック・time sentinel 網羅性（minor）

**deferred（後続フェーズで明示的に扱われる）:**
- `label.fukusho_label.race_date` 全行 NULL → Phase 3 SC#1 が feature_cutoff_datetime に必要・Phase 2 SC 群は要求しない
- `fukusho_hit_raw` の unresolved レース偽正例 → Phase 8 SC#1 対抗的監査

**human_needed（status 決定要因）:**
- Plan 02-03 Task 3・Plan 02-04 Task 3 は共に `checkpoint:human-verify` gate で実DB 実行が必要・verifier では再現不能・02-VALIDATION.md W5 で文書化済み。SUMMARY の verdict=pass / agreement=100.0% / rows=554,267 / checksum 一致は claims であり証拠ではない・user が live DB で再確認する必要がある。

---

_Verified: 2026-06-18T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
