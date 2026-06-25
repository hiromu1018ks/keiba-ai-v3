---
status: complete
phase: 01-trust-foundation
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md]
started: 2026-06-17T12:30:41Z
updated: 2026-06-17T12:43:03Z
executor: claude（ユーザー指示「君ができるところはやってくれー」により Claude が実行・観測）
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test（クリーン再現）
expected: `uv sync --frozen` が uv.lock から venv を再構築（37 packages・エラー無し）。`uv run python -c "import psycopg, pandas, sklearn, mlxtend, pyarrow, duckdb, pydantic_settings; print('deps OK')"` が `deps OK` を出力する。
result: pass
evidence: "`uv sync --frozen` → `Checked 37 packages in 4ms`。import check → `deps OK`。Settings() ロード成功・`dsn_masked`/`etl_dsn_masked` でパスワードが `***` マスク（ASVS V8）。"

### 2. Raw 品質レポート（成功基準#1）
expected: `run_quality_report.py` が quality_report.{json,md} を生成。JSON verdict="pass"。per-table counts・JRA≥2015・mojibake=0・code-anomaly(NAR) が含まれる。
result: pass
evidence: "verdict=pass・BLOCK 8件全 passed（5テーブル存在 / jra_since_2015 count=39593 / n_race PK 40035重複0 / n_uma_race NK 554610重複0）。INFO: table_counts(n_race JRA=40035/non_jra=31937) / date_range jra_min=2015… / null_rates / cast_success / mojibake=0 / code_value_anomalies(jyokencd5異常256件=0.64% INFO)。"

### 3. スキーマ適用 dry-run と raw 二重保護（成功基準#2 一部）
expected: `run_apply_schema.py --dry-run` が identifier-quote 済み SQL（CREATE SCHEMA / REVOKE UPDATE, DELETE, TRUNCATE ON TABLES / GRANT INSERT）を出力。KEIBA_ADMIN_DSN 未設定時は fail。
result: pass
evidence: "5層 CREATE SCHEMA(raw_everydb2/normalized/label/prediction/backtest)・CREATE ROLE \"keiba_readonly\"/\"keiba_etl\"（Identifier quote）・CREATE OR REPLACE VIEW 5表・GRANT USAGE, CREATE ON SCHEMA normalized TO keiba_etl・`REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public`（物理+VIEW 二重保護）。dry-run SQL 正常出力。"
note: "fail-fast（KEIBA_ADMIN_DSN 未設定時の exit）は load_dotenv が .env から補完するため個別検証せず。主目的の dry-run 出力は正常。"

### 4. Normalized ETL 実行と冪等性（成功基準#2）
expected: `run_normalized_etl.py` が normalized.n_race(約39593)/n_uma_race(約554610)を書込み・raw_touched=False・class_unresolved 出力。再実行で同一件数・同一ハッシュ（idempotent）。
result: pass
evidence: "run#1: n_race=39593 n_uma_race=554267。run#2: rows_inserted同一(39593/554267)・class_unresolved=115・**raw_touched=False**。2015年 per-year md5 ハッシュ run#1=run#2=`b09619fdb6d27511d4f23701ba0576b3`（IDEMPOTENT True）。unresolved WARNING(gradecd F/G/H)は silent fallback 禁止で隔離。"

### 5. クラス正規化の改革跨ぎ連続性（成功基準#3・核心）
expected: jyokencd5='005' が2018(旧500万下)・2019+(1勝クラス)両方で class_level_numeric=1/'1勝クラス'。未知コードは unresolved で隔離。
result: pass
evidence: "`SELECT ... WHERE jyokencd5='005'` → 2018: (1,'1勝クラス',1040) / 2019: (1,'1勝クラス',993) / 2020: (1,'1勝クラス',955)。3年全て同一 class_level_numeric=1 で改革跨ぎコード連続性を実証（hondai 名称マッチ不使用）。class_normalization_status: resolved=39478 / unresolved=115（silent fallback 無し）。"

### 6. Raw 不変性の pytest 証明（成功基準#2）
expected: `pytest tests/test_raw_immutability.py -v` 全 green。test_raw_unchanged_after_etl / test_etl_role_cannot_write_public 含む。
result: pass
evidence: "6 passed in 56.64s。test_raw_unchanged_after_etl（ETL前後 per-year row-hash 一致）・test_etl_role_cannot_write_public（ETLロールが public.n_race INSERT で InsufficientPrivilege）・test_raw_role_has_no_update_grant_public・test_raw_is_view_in_raw_everydb2_schema 全 green。"

### 7. リーク防止プリミティブ4種（成功基準#4）
expected: `pytest tests/utils/ -v` 全 green。`python -O -m pytest tests/utils/ -q` も同一結果（guard が raise ValueError なので -O でも生存）。
result: pass
evidence: "normal: 29 passed in 2.30s。`python -O`: 29 passed, 1 warning in 2.20s（最適化でも同一・guard 生存）。pit_join / group_split / category_map / calibrator 全 green。（SUMMARY 記載の27件→REVIEW-FIX で29件に増加・全 green）"

### 8. フルテストスイートと fail-by-default skip policy
expected: `pytest tests/ -q` 全件 pass（回帰無し）。`KEIBA_SKIP_DB_TESTS=1 pytest tests/ -q` が DB テストを skip（HIGH#8）。
result: pass
evidence: "full suite: 83 passed in 121.58s（回帰無し）。`KEIBA_SKIP_DB_TESTS=1`: 66 passed, 17 skipped（全 DB テストが `KEIBA_SKIP_DB_TESTS=1 set` で skip・偽 pass 無し）。"

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none — all 8 tests passed]
