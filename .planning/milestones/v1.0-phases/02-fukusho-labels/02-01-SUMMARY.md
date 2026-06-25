---
phase: 02-fukusho-labels
plan: 01
subsystem: database
tags: [phase-02, labels, schema, grant, config, foundation, postgres, psycopg3, settings]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "5層 PostgreSQL スキーマ・2ロール(reader/etl)・run_apply_schema.py・GRANT/REVOKE idempotent 適用基盤"
provides:
  - "label_spec.yaml — ラベル定義の静的正（label_generation_version='v1.0.0' / D-04 status 4値 / D-01 payout 境界 / §7.2-7.3 適格性 / marker canonicalization sentinel 集合 / sales_start_entry_count source_confidence 分離）"
  - "GRANT_ETL_SQL / GRANT_READER_SQL の label スキーマ拡張（明示的 reader ロール・PUBLIC 不使用）"
  - "Settings.db_schema_label='label' / Settings.db_reader_role='keiba_readonly'"
  - "make_pool(role='etl') search_path = label,normalized,public"
  - "scripts/apply_schema.sql の schema.py 同期（TO PUBLIC 含まず）"
  - "実DB label スキーマ GRANT 反映（keiba_etl USAGE+CREATE+書込 / keiba_readonly USAGE+SELECT）"
affects: [02-02 (label_generator), 02-03 (label table + idempotent load), 02-04 (label tests), phase-03 (as-of features), phase-05 (EV), phase-08 (audit)]

# Tech tracking
tech-stack:
  added: []  # 外部パッケージ新規追加なし（Phase 1 依存で完結・RESEARCH Package Legitimacy Audit 検証済み）
  patterns:
    - "label_spec.yaml によるラベル定義の Git 管理化（D-07・class_normalization.yaml ヘッダ慣行踏襲）"
    - "marker canonicalization sentinel 集合（raw 文字列/数値キャスト後の両表現を同一視・HIGH #5）"
    - "明示的 reader ロール付与（TO PUBLIC 一切不使用・HIGH #3）"
    - "source_confidence / label_validation_status の直交分離（HIGH #1）"
    - "run_apply_schema.py による GRANT 拡張の実DB idempotent 反映（Phase 1 01-01/01-03 と同じパターン）"

key-files:
  created:
    - "src/config/label_spec.yaml — ラベル定義の静的正（label_generation_version/status_values/payout_places_rules/sales_start_entry_count/model・newcomer_syubetucd/class_eligibility/se_marker_canonicalization/se_marker_rules/se_datakubun_inclusion/hr_status_rules/dead_heat_rules/ineligibility_reason_codes/unresolved_strategy）"
  modified:
    - "src/db/schema.py — GRANT_READER_SQL / GRANT_ETL_SQL に label スキーマ権限を追加"
    - "src/config/settings.py — db_schema_label='label' / db_reader_role='keiba_readonly' 追加"
    - "src/db/connection.py — make_pool(role='etl') search_path を label,normalized,public に拡張"
    - "scripts/apply_schema.sql — schema.py の GRANT 拡張と同期（reader 3行 + etl 3行・TO PUBLIC 0件）"

key-decisions:
  - "label_generation_version='v1.0.0' 採用（Open Question #1 推奨・セマンティック採番・Phase 3 snapshot metadata 埋込）"
  - "GRANT_READER_SQL は明示的 reader ロール（{reader} placeholder=keiba_readonly）のみ付与・TO PUBLIC 一切不使用（HIGH #3・Plan 03 も同様）"
  - "marker canonicalization を sentinel 集合で定義し '999.0'==999 のような brittle 等価を禁止（HIGH #5）"
  - "sales_start_entry_count.source_confidence='inferred' を label_validation_status から独立キーとして定義（HIGH #1・conflation 回避）"
  - "missing_value_sentinel='__MISSING__' を定義し pd.isna guard で silent corruption を防止（NEW HIGH #3 支援）"
  - "se_datakubun_inclusion.required_se_datakubun_values=['7','9'] で race_cancelled 行の silent data loss を予防（HIGH #4）"
  - "Task 3 はファイル差分を伴わない（apply_schema.sql は Task 2 commit に含まれ・Task 3 は live DB 反映のみ）"

patterns-established:
  - "label_spec.yaml がラベルロジックの唯一の正（Plan 02/03/04 はこれを参照・ハードコード禁止）"
  - "settings.db_schema_* 系列に label を追加（raw/normalized/label の対称性）"
  - "GRANT 拡張は schema.py が source of truth・apply_schema.sql は同期された参照成果物"

requirements-completed: [LABEL-01, LABEL-02, LABEL-03, LABEL-04]

# Metrics
duration: 約 10 min（socket 中断からの継続含む）
completed: 2026-06-18
---

# Phase 02 Plan 01: 複勝ラベル定義の静的正 + label スキーマ GRANT 基盤 Summary

**label_spec.yaml でラベル定義を Git 管理化し（label_generation_version='v1.0.0'）、PostgreSQL label スキーマに対する明示的 reader/etl ロール GRANT と search_path 拡張を実DB まで反映（PUBLIC 不使用・HIGH #3）。**

## Performance

- **Duration:** 約 10 min（前回 socket 中断を含む継続実行）
- **Started:** 継続実行（Task 1 は前回完了済）
- **Completed:** 2026-06-18T04:02Z
- **Tasks:** 3 (Task 1 = 前回 commit 済、Task 2/3 = 今回完了)
- **Files modified:** 5（label_spec.yaml 新規 + schema.py/settings.py/connection.py/apply_schema.sql 修正）

## Accomplishments

- **label_spec.yaml 作成（Task 1・前回完了）:** `label_generation_version='v1.0.0'` でラベル定義の静的正を Git 管理下に配置（D-07）。D-04 status 4 値 / D-01 payout 境界 / §7.2-7.3 適格性ルール（未勝利 precision 含む）/ marker canonicalization sentinel 集合 / sales_start_entry_count source_confidence 分離を網羅。REVIEWS HIGH #1（conflation 回避）/ #4（SE DataKubun='9' 包含）/ #5（marker sentinel）/ NEW HIGH #3 支援（missing_value_sentinel='__MISSING__'）+ MEDIUM（class_eligibility 未勝利 precision）を全て組み込み。
- **GRANT 拡張（Task 2）:** GRANT_READER_SQL に label スキーマ USAGE+SELECT+DEFAULT PRIVILEGES を、GRANT_ETL_SQL に USAGE+CREATE+書込権を追加。**明示的 reader ロール（keiba_readonly）のみ付与し TO PUBLIC は一切使用しない（HIGH #3/MEDIUM #3）。** D-06 二重保護（public/raw_everydb2 の REVOKE）は維持。
- **設定・接続の統合（Task 2）:** Settings.db_schema_label='label' / Settings.db_reader_role='keiba_readonly' を追加、make_pool(role='etl') の search_path を `label,normalized,public` に拡張。
- **実DB 反映（Task 3・Pitfall 6 回避）:** `uv run python scripts/run_apply_schema.py` が exit 0 で完了。実DB で `has_schema_privilege('keiba_etl','label','USAGE, CREATE')=True` / `has_schema_privilege('keiba_readonly','label','USAGE')=True` を検証済。default ACL も `keiba_readonly=r/hart`, `keiba_etl=arwdD/hart` で明示的ロール付与を確認。

## Task Commits

各 task を原子的に commit（Task 1 は前回実行、Task 2 は今回完了、Task 3 はファイル差分なしで live DB 適用のみ）:

1. **Task 1: label_spec.yaml 作成（D-07 Git 管理）** — `27a2991` (feat) — *前回 socket 中断前に完了*
2. **Task 2: schema.py GRANT 拡張 + settings/connection/apply_schema.sql 同期** — `4e3810b` (feat)
3. **Task 3: run_apply_schema.py 実DB 適用（Pitfall 6）** — ファイル差分なし（live DB のみ・Task 2 commit に apply_schema.sql 変更を含むため空 commit は作成せず）

## Files Created/Modified

- `src/config/label_spec.yaml`（新規・Task 1）— ラベル定義の静的正。label_generation_version / status_values / payout_places_rules / sales_start_entry_count（source_confidence 分離）/ model_ineligibility_syubetucd / newcomer_syubetucd / class_eligibility（未勝利 precision）/ se_marker_canonicalization（sentinel 集合 + missing_value_sentinel）/ se_marker_rules / se_datakubun_inclusion / hr_status_rules / dead_heat_rules / ineligibility_reason_codes / unresolved_strategy
- `src/db/schema.py`（修正・Task 2）— GRANT_READER_SQL / GRANT_ETL_SQL に label スキーマ権限を追加（各3行）。コメント中の「TO PUBLIC は一切使用しない」表現は verify assertion (`'TO PUBLIC' not in GRANT_READER_SQL`) を通すため「汎用ロールへの付与は一切しない」に言い換え（意図は同一）
- `src/config/settings.py`（修正・Task 2）— db_schema_label='label' / db_reader_role='keiba_readonly' 追加
- `src/db/connection.py`（修正・Task 2）— make_pool(role='etl') search_path を label,normalized,public に拡張
- `scripts/apply_schema.sql`（修正・Task 2）— schema.py の GRANT 拡張と同期（reader 3行 + etl 3行・TO PUBLIC 0件）

## Verification Results

Task 1（前回完了・acceptance criteria 全件 PASS）:
- `test -f src/config/label_spec.yaml` 成功
- `python3 -c "import yaml; yaml.safe_load(open('src/config/label_spec.yaml'))"` 成功
- `label_generation_version: "v1.0.0"` 含む
- `status_values == ["validated","inferred","dead_heat","unresolved"]`（D-04）
- HIGH #1: `sales_start_entry_count.source_confidence='inferred'` が独立キー・`proxy_status` 同義キー不存在
- HIGH #5: `se_marker_canonicalization` が `harontimel3_sentinels` に `"999"`/`"999.0"` 両方含む
- NEW HIGH #3 支援: `missing_value_sentinel='__MISSING__'`
- HIGH #4 予防: `se_datakubun_inclusion.required_se_datakubun_values=['7','9']`
- MEDIUM: `class_eligibility.maiden_syubetucd=['13','14','15']` + `minimum_class_level_numeric: 1`

Task 2（今回完了・acceptance criteria 全件 PASS）:
- `grep -c 'GRANT USAGE, CREATE ON SCHEMA label TO {etl};' src/db/schema.py` = 1
- `grep -c 'GRANT USAGE ON SCHEMA label TO {reader};' src/db/schema.py` = 1
- `grep -c 'ALTER DEFAULT PRIVILEGES IN SCHEMA label' src/db/schema.py` = 2
- `grep -c 'REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public' src/db/schema.py` = 2（D-06 維持）
- `python3 -c "from src.db.schema import GRANT_READER_SQL; assert 'TO PUBLIC' not in GRANT_READER_SQL"` 成功
- `Settings.model_fields['db_reader_role'].default == 'keiba_readonly'` 成功
- `Settings.model_fields['db_schema_label'].default == 'label'` 成功
- `make_pool` ソースに `db_schema_label` と `db_schema_normalized` が両方含まれる（label が先頭）
- `GRANT_ETL_SQL.count('SCHEMA label') >= 3` / `GRANT_READER_SQL.count('SCHEMA label') >= 2` 成功

Task 3（今回完了・acceptance criteria 全件 PASS）:
- `uv run python scripts/run_apply_schema.py` exit 0・`schema applied successfully` ログ出力
- `scripts/apply_schema.sql` の `SCHEMA label` 出現回数 = 6（≥5）
- `grep -c 'TO PUBLIC' scripts/apply_schema.sql` = 0
- `grep -c 'REVOKE UPDATE, DELETE, TRUNCATE' scripts/apply_schema.sql` = 8（≥4・D-06 維持）
- dry-run 出力に `"keiba_etl"` / `"keiba_readonly"` の Identifier quote 含む（MEDIUM #3）
- **実DB 検証:** `has_schema_privilege('keiba_etl','label','USAGE, CREATE')=True` / `has_schema_privilege('keiba_readonly','label','USAGE')=True` / label スキーマ default ACL = `keiba_readonly=r/hart`, `keiba_etl=arwdD/hart`（明示的ロール・PUBLIC なし）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GRANT_READER_SQL のコメント文言を verify assertion 合致用に調整**
- **Found during:** Task 2 自動検証
- **Issue:** 計画の verify assertion `'TO PUBLIC' not in GRANT_READER_SQL` が、HIGH #3 の意図を説明するコメント中のリテラル `TO PUBLIC` 文字列に一致して失敗（実 GRANT 文は PUBLIC を使っていないが、コメント内の説明文に "TO PUBLIC は一切使用しない" と書いてあった）
- **Fix:** コメント表現を「汎用ロールへの付与は一切しない」に言い換え（src/db/schema.py:86 と scripts/apply_schema.sql:57）。意図（HIGH #3・PUBLIC 不使用）は完全不変。
- **Files modified:** src/db/schema.py, scripts/apply_schema.sql
- **Commit:** 4e3810b

**2. [計画通り・特記事項] Task 3 の atomic commit を見送り**
- **Found during:** Task 3 完了時
- **Issue:** Task 3 の `<files>` は `scripts/apply_schema.sql` のみだが、このファイルは Task 2 commit (4e3810b) に既に含まれている。Task 3 本体は live DB 適用（run_apply_schema.py 実行 + 実DB GRANT 検証）のみでファイル差分を生じない。
- **Fix:** 空 commit（`--allow-empty`）は作成せず、Task 3 の成果は SUMMARY の Verification Results で記録。これは GSD の「コミットは差分がある場合のみ」慣行に合致。
- **Files modified:** なし（live DB のみ）
- **Commit:** 該当なし（Task 2 commit 4e3810b に apply_schema.sql 差分を含む）

## Known Stubs

なし。本 plan は設定・権限基盤の確立のみで、スタブとなる UI/データ経路は持たない。

## Threat Flags

なし。脅威モデル T-02-01〜T-02-04 / T-02-RV1 / T-02-RV5 / T-02-RV9-cfg / T-02-SC の全 mitigation が実装され、新規の脅威表面は導入されていない（実DB GRANT 拡張は計画通り・REVOKE は維持）。

## Self-Check: PASSED

- [x] `src/config/label_spec.yaml` FOUND
- [x] `src/db/schema.py` GRANT 拡張 FOUND（`grep -c 'SCHEMA label'` = 6）
- [x] `src/config/settings.py` db_schema_label/db_reader_role FOUND
- [x] `src/db/connection.py` search_path 拡張 FOUND
- [x] `scripts/apply_schema.sql` 同期 FOUND（`SCHEMA label` = 6 / `TO PUBLIC` = 0）
- [x] commit `27a2991` FOUND（Task 1）
- [x] commit `4e3810b` FOUND（Task 2）
- [x] 実DB GRANT 反映検証済（keiba_etl USAGE+CREATE / keiba_readonly USAGE / default ACL 明示ロール）
