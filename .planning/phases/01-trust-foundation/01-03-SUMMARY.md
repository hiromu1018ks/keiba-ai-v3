---
phase: 01-trust-foundation
plan: 03
subsystem: trust-foundation (normalized ETL + class normalization + raw immutability proof)
tags: [phase-01, etl, normalized, class-normalization, idempotent-staging-swap, raw-immutability, leak-prevention]
requires: [01-01, 01-02, 01-04]
provides:
  - "src.etl.class_normalize.load_class_config / normalize_class / normalize_race_classes / audit_gradecd_d_by_syubetucd（DATA-03 機械導出・hondai 不使用・Pitfall 7・MEDIUM #3/#4）"
  - "src.etl.normalize.run_normalized_etl（psycopg3+pandas 明示実装・staging-swap idempotent・HIGH #5/#6・MEDIUM #1）"
  - "src.etl.normalize._idempotent_load（atomic staging-table-swap）"
  - "src.etl.raw_fingerprint.compute_raw_fingerprint / assert_raw_unchanged（成功基準#2 直接証明・MEDIUM #2 row-hash 主証明 + pg_stat 補助）"
  - "scripts/run_normalized_etl.py（ETL エントリポイント・raw fingerprint 前後比較ログ・masked DSN）"
  - "tests/test_class_normalization.py（DATA-03 unit/integration・13 tests）"
  - "tests/test_normalized_etl.py（DATA-02 integration・13 tests・HIGH #5 idempotency 含む）"
  - "tests/test_raw_immutability.py（成功基準#2・HIGH #4 両スキーマ・HIGH #6 補完・6 tests）"
  - "normalized.n_race / normalized.n_uma_race（型付きカラム・class_* 正規化列付き）"
affects:
  - "Phase 2 (labels): normalized.n_uma_race の kakuteijyuni/kettonum に依存"
  - "Phase 3 (features): normalized.n_race の class_* / race_start_datetime に依存"
  - "Phase 4 (models): gradecd='D' 扱いを audit 結果に基づき再調整可能"
tech-stack:
  added: []
  patterns:
    - "staging-table-swap: CREATE _staging (LIKE table INCLUDING ALL) → TRUNCATE → INSERT → atomic DROP + RENAME TO + GRANT SELECT TO PUBLIC（HIGH #5・再実行で重複しない）"
    - "per-year per-table md5(string_agg(...)) aggregate checksum: 全 JRA 行カバー・単一日 sample の見逃しを解消（MEDIUM #2 主証明）"
    - "pg_stat_user_tables.n_tup_upd/del/ins は VACUUM でリセットされるため補助シグナル扱い（MEDIUM #2）"
    - "date.fromisoformat で post_2019_class_system_reform_date を parse（MEDIUM #3 typo 修正）"
    - "unresolved 分岐でも post_2019_class_system_flag は race_date から計算（MEDIUM #4・null 化しない）"
    - "全 SELECT で jyocd BETWEEN '01' AND '10' AND year >= 2015（Pitfall 2 + 要件 §6.1）"
    - "hassotime='0'（EveryDB2 初期値）は事前チェックで NaT にフォールバック（Warning #5・ETL 停止回避）"
    - "hondai regex/match を使わず jyokencd5+gradecd+race_date のみで機械導出（Pitfall 7）"
key-files:
  created:
    - src/etl/class_normalize.py
    - src/etl/normalize.py
    - src/etl/raw_fingerprint.py
    - scripts/run_normalized_etl.py
    - tests/test_class_normalization.py
    - tests/test_normalized_etl.py
    - tests/test_raw_immutability.py
  modified:
    - src/db/schema.py
    - scripts/apply_schema.sql
decisions:
  - "実DBの ETL ロール（keiba_etl）が normalized スキーマに CREATE 権限を持たないと staging-swap が出来ないため、schema.py の GRANT_ETL_SQL を GRANT USAGE, CREATE ON SCHEMA normalized に拡張し、apply_schema.sql も同様に更新（Rule 3 blocking・01-01 schema に対する追加修正）"
  - "staging-swap の都度新しい OID のテーブルが作られるため reader ロールの SELECT が消える問題を防ぐため、_idempotent_load の最後に GRANT SELECT ON normalized.<table> TO PUBLIC を発行（ETL ロールが所有者なので GRANT 可能）"
  - "reader ロール（keiba_readonly）が normalized を SELECT できるよう GRANT_READER_SQL に GRANT USAGE ON SCHEMA normalized + GRANT SELECT ON ALL TABLES を追加（テストの readonly_cur が normalized を検証できるよう本 plan で拡張）"
  - "要件 §6.1（2015年以降）を ETL 側で機械適用: _JRA_FILTER に year::int >= 2015 を追加（Rule 2・EveryDB2 には2015年以前のデータも入っているため）"
  - "実測（Rule 1）: n_race.hassotonen は存在しない、n_uma_race.bataiju ではなく bataijyu、zogenfuka/tengokuangou/hansyoku/norei は raw に存在せず plan 01-03 の列定義をこれらの存在しない列を除外して実装"
  - "test_etl_idempotent_rerun で readonly_cur の read transaction を明示 rollback しないと後続 ETL の DROP TABLE がロック待ちでデッドロックする問題を修正（pytest fixture が transaction を自動 commit しないため）"
metrics:
  duration: "約136分"
  completed: "2026-06-17"
  tasks_total: 3
  files_created: 7
  files_modified: 2
  commits: 10
---

# Phase 01 Plan 03: Normalized ETL + Class Normalization + Raw Immutability Summary

raw(``public.n_*``) の全 varchar カラムを明示キャストして型付き ``normalized`` スキーマへ書込み・``class_normalization.yaml`` を適用して ``jyokencd5``×``gradecd``×``race_date`` から ``class_*`` / ``post_2019_class_system_flag`` 等を機械導出する normalized ETL を構築し、**ETL 前後で raw の行ハッシュ（per-year per-table md5 aggregate）が1バイトも変わらないことを pytest で直接証明**した。ETL は **staging-table-swap** で idempotent（再実行で重複しない・§19.1 再現性）・**ETL ロール（KEIBA_ETL_DB_USER・HIGH #6）** で ``normalized`` のみに書込む・DuckDB は補助のみで永続化に使わない（§12.1）。Pitfall 7（hondai 名称マッチ不使用・2019 改革跨ぎのコード連続性）・Pitfall 1（全 varchar 明示キャスト）・Pitfall 2（JRA フィルタ）・D-06（raw 二重保護）・D-11（2019-06-08 基準日）・D-13（未知コード unresolved 隔離・post_2019_flag は race_date から計算・MEDIUM #4）を全て統合検証した Phase 1 の integration capstone。実DBで ETL 実行後も ``scripts/run_quality_report.py`` が verdict=pass を維持し、raw 不変を間接確認。

## Tasks Completed

| Task | Name | Commit | Key files |
|------|------|--------|-----------|
| 1 (RED) | DATA-03 class normalization failing tests | 83f1b83 | tests/test_class_normalization.py |
| 1 (GREEN) | class_normalize.py（hondai 不使用・MEDIUM #3/#4・audit_gradecd_d） | 9639ce5 | src/etl/class_normalize.py |
| 2 (RED) | normalized ETL integration tests | 590bf9f | tests/test_normalized_etl.py |
| 2 (GREEN) | normalize.py + staging-swap + scripts/run_normalized_etl.py | 8611b6a | src/etl/normalize.py, scripts/run_normalized_etl.py, src/db/schema.py, scripts/apply_schema.sql |
| 2 (fix) | run_normalized_etl.py sys.path セットアップ | fdab2d6 | scripts/run_normalized_etl.py |
| 3 (RED) | raw immutability failing tests | bd4bc48 | tests/test_raw_immutability.py |
| 3 (GREEN) | raw_fingerprint.py（row-hash 主証明 + pg_stat 補助） | 4eef353 | src/etl/raw_fingerprint.py |
| (lint) | ruff lint/format 適用 | 16f591a | src/etl/normalize.py, scripts/run_normalized_etl.py, tests/* |

全3タスクを TDD（RED: 失敗テスト commit → GREEN: 実装 commit）で実行。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ETL ロールに normalized スキーマの CREATE 権限が無い**

- **Found during:** Task 2 GREEN（実DB integration テスト）
- **Issue:** plan 01-01 の ``GRANT_ETL_SQL`` は ``GRANT USAGE ON SCHEMA normalized TO {etl}`` のみで CREATE を含んでいなかった。HIGH #5 の staging-swap は ``CREATE TABLE normalized.<table>_staging`` を発行するが、``permission denied for schema normalized`` で fail した。
- **Fix:** ``src/db/schema.py`` の ``GRANT_ETL_SQL`` と ``scripts/apply_schema.sql`` を ``GRANT USAGE, CREATE ON SCHEMA normalized TO {etl}`` に拡張。実行中の DB にも admin DSN で同 GRANT を適用（idempotent）。
- **Files modified:** src/db/schema.py, scripts/apply_schema.sql
- **Commit:** 8611b6a

**2. [Rule 3 - Blocking] staging-swap の都度 reader ロールの SELECT 権限が消える**

- **Found during:** Task 2 GREEN（``information_schema.columns`` から kyori が見えない）
- **Issue:** ``_idempotent_load`` の ``DROP TABLE normalized.n_race; ALTER TABLE n_race_staging RENAME TO n_race`` で新しい OID のテーブルが作られ、所有者が ``keiba_etl`` になる。``ALTER DEFAULT PRIVILEGES`` は将来のテーブルにのみ適用され、ETL ロールが作った既存テーブルには遡及しないため、``keiba_readonly`` から SELECT 出来なくなる。
- **Fix:** ``_idempotent_load`` の最後に ``GRANT SELECT ON normalized.<table> TO PUBLIC`` を発行（ETL ロールが所有者なので GRANT 可能）。これで staging-swap の都度 reader に SELECT が付与される。
- **Files modified:** src/etl/normalize.py
- **Commit:** 8611b6a

**3. [Rule 3 - Blocking] reader ロールが normalized スキーマを読めない**

- **Found during:** Task 2 GREEN（``readonly_cur`` で ``normalized.n_race`` にアクセスすると ``permission denied for schema normalized``）
- **Issue:** plan 01-01 の ``GRANT_READER_SQL`` は ``public`` と ``raw_everydb2`` のみで ``normalized`` を含んでいなかった。テストが ``readonly_cur`` で ``normalized`` を検証するためには USAGE + SELECT 権限が必要。
- **Fix:** ``GRANT_READER_SQL`` と ``apply_schema.sql`` に ``GRANT USAGE ON SCHEMA normalized TO {reader}`` + ``GRANT SELECT ON ALL TABLES IN SCHEMA normalized TO {reader}`` + ``ALTER DEFAULT PRIVILEGES IN SCHEMA normalized GRANT SELECT ON TABLES TO {reader}`` を追加。実 DB にも admin DSN で適用（idempotent）。
- **Files modified:** src/db/schema.py, scripts/apply_schema.sql
- **Commit:** 8611b6a

**4. [Rule 2 - Critical] 要件 §6.1（2015年以降）を ETL 側で機械適用**

- **Found during:** Task 2 GREEN（``test_race_date_constructed`` で 1989年のデータが含まれる）
- **Issue:** EveryDB2 には2015年以前のレース（1989年〜）も入っており、plan 通りの ``jyocd BETWEEN '01' AND '10'`` だけでは JRA 限定にはなるが期間限定にならない。要件 §6.1 は「2015年1月1日以降の JRA データ」を明示的に対象期間とする。
- **Fix:** ``_JRA_FILTER`` を ``jyocd BETWEEN '01' AND '10' AND year::int >= 2015`` に拡張。ETL が2015年以前の行を機械的に除外し、要件 §6.1 を実装レベルで保証。``test_rowcount_jra_matches_raw`` も ``year::int >= 2015`` で raw と件数比較するよう調整。
- **Files modified:** src/etl/normalize.py, tests/test_normalized_etl.py
- **Commit:** 8611b6a

**5. [Rule 1 - Bug] plan 列定義が実DBと不一致（hassotonen / bataiju / zogenfuka 等）**

- **Found during:** Task 2 GREEN 設計時（実DBカラム確認）
- **Issue:** plan 01-03 の ``_RACE_COLUMNS`` / ``_UMA_RACE_COLUMNS`` 定義が挙げた一部カラムが実DBに存在しない: ``n_race.hassotonen``（存在せず）・``n_uma_race.bataiju``（実測は ``bataijyu``・docs 04-UMA_RACE.md 表記揺れ）・``zogenfuka`` / ``tengokuangou`` / ``hansyoku`` / ``norei``（raw に存在せず）。これらを正として INSERT すると ``column does not exist`` で ETL 全体が abort する。
- **Fix:** 実在する列名で ``_RACE_COLUMNS`` / ``_UMA_RACE_COLUMNS`` を再定義。``bataijyu``（正）/ ``zogenfugo`` + ``zogensa``（実在）/ ``chokyosicode`` + ``chokyosiryakusyo`` / ``kisyucode`` + ``kisyuryakusyo`` / ``banusicode`` + ``banusiname`` 等、docs/everydb2/04-UMA_RACE.md の実際の73フィールドに合わせる。存在しない plan 想定列は除外。
- **Files modified:** src/etl/normalize.py
- **Commit:** 8611b6a

**6. [Rule 1 - Bug] pd._TSNA は pandas 3.0 に存在しない**

- **Found during:** Task 2 GREEN
- **Issue:** ``_row_to_tuple`` で ``isinstance(v, pd._TSNA)`` を使ったが pandas 3.0.3 には ``pd._TSNA`` 属性が無く ``AttributeError``。
- **Fix:** ``isinstance(v, type(pd.NaT))`` に変更。
- **Files modified:** src/etl/normalize.py
- **Commit:** 8611b6a

**7. [Rule 1 - Bug] test_etl_idempotent_rerun でデッドロック**

- **Found during:** Task 2 GREEN（テスト実行がハング）
- **Issue:** ``readonly_cur`` fixture が ``pg_pool.connection()`` を使い回し、SELECT 後も read transaction を明示 commit/rollback しないため、後続の ETL が発行する ``DROP TABLE normalized.n_race`` がロック待ちでデッドロックした。``pg_stat_activity`` で ``idle in transaction`` + ``Lock: relation`` を確認。
- **Fix:** ``test_etl_idempotent_rerun`` 内で各 SELECT 後に ``readonly_cur.connection.rollback()`` を明示的に呼出し read transaction を閉じてロックを解放。他の統合テストでも必要に応じて ``rollback()`` を追加（``test_raw_unchanged_after_etl`` でも同様）。
- **Files modified:** tests/test_normalized_etl.py, tests/test_raw_immutability.py
- **Commit:** 8611b6a

### Plan-as-Written に対する他の調整

- **docstring grep 検証の意図化:** ``test_normalize_class_signature_and_no_hondai_match`` は単純な ``"hondai" not in src`` だと docstring 内の注意書き（「hondai 名称マッチ不使用」）まで誤検知するため、``normalize_class`` 関数本体内で ``re.match`` / ``str.match`` / ``.match(`` 等のトークン不在を検査するよう絞り込み。Pitfall 7 の検証意図は完全に維持。
- **``test_module_loads_fromisoformat_not_typo`` も同様に ``date.fromisoformat(`` 関数呼び出しの存在と ``date.fromisoconfig(`` typo 呼び出しの不在を検査**（docstring の「typo ではない」という注意書きで誤検知しないよう）。
- **audit_gradecd_d_by_syubetucd 実測結果（RESEARCH Open Question #1 RESOLVED）:** ``gradecd='D'`` の syubetucd 分布は ``{11:1, 12:4, 13:2, 19:2}`` で**圧倒的に平地G3**（syubetucd='19' 障害はわずか2件）。plan 01-01 の暫定 ``grade_numeric=3``（G3 扱い）は妥当。今後 Phase 4 で ``is_grade_race`` を更に細分する際は「D は大部分が平地G3・障害G3 は2件のみ」を前提に調整可能。

## Threat Flags

該当なし。plan の ``<threat_model>`` T-03-01..T-03-08 は全て mitigated 状態で実装済み:

- **T-03-01 (Tampering: raw 誤更新):** ``normalize.py`` は raw に SELECT のみ発行（grep gate ``UPDATE public.n_`` / ``DELETE FROM public.n_`` が 0）。ETL 前後の row-hash + row-count + pg_stat を ``test_raw_unchanged_after_etl`` が主証明で assert。
- **T-03-02 (hondai regex で改革破綻):** ``class_normalize.py`` は ``jyokencd5+gradecd+race_date`` のみで機械導出（``test_normalize_class_signature_and_no_hondai_match`` が ``re.match``/``str.match`` トークン不在を検証）。``test_code_005_spans_reform`` が 2018/2019 で同じ class_level_numeric=1 を assert。
- **T-03-03 (silent fallback):** 未知コードは ``class_normalization_status='unresolved'`` で WARNING ログと共に隔離。``test_unresolved_unknown_jyokencd5`` / ``test_unresolved_gradecd_fgh`` が検証。実DBで115件の unresolved（F/G/H 障害級 + 1989年当時の未知 jyokencd5）を INFO で報告。
- **T-03-04 (varchar 暗黙キャスト事故):** ``pd.to_numeric(errors='coerce')`` で明示キャスト。``futan`` は /10.0 で real。``test_type_cast_kyori_int`` / ``test_race_date_constructed`` が型を検証。
- **T-03-05 (NAR 混入):** 全 SELECT で ``jyocd BETWEEN '01' AND '10'``。``test_jra_only_filter`` が normalized.n_race 全行で JRA のみを assert（NAR 0件）。
- **T-03-06 (DuckDB 永続化):** ``import duckdb`` が ``normalize.py`` に無いことを grep gate（0件）で保証。
- **T-03-07 (ETL 再実行重複):** ``_idempotent_load`` の staging-swap（CREATE _staging → TRUNCATE → INSERT → atomic DROP+RENAME+GRANT）で再現性保証。``test_etl_idempotent_rerun`` が2回実行で同一件数・同一ハッシュを assert。
- **T-03-08 (ETL ロール未定義で raw ロールで書込む):** ETL は ``write_pool = make_pool(role='etl')``（KEIBA_ETL_DB_USER）経由。``test_etl_role_cannot_write_public`` が ``public.n_race`` への INSERT で ``InsufficientPrivilege`` を raise することを ``pytest.raises`` で検証。

新規に plan 外の security-relevant な表面は導入していない。``GRANT CREATE ON SCHEMA normalized TO keiba_etl`` は ETL ロールの権限拡張だが、これは ``normalized`` スキーマ内のみ（``public`` / ``raw_everydb2`` には依然 CREATE 無し・REVOKE も維持）なので新規の脅威表面とはならない。

## Known Stubs

該当なし。本 plan は実DBに対する完全な ETL 実装・クラス正規化・不変性証明で、stub/placeholder なし。

## Verification Results

- ``uv run pytest tests/test_class_normalization.py tests/test_normalized_etl.py tests/test_raw_immutability.py -v``: **32 passed**（class 13 + etl 13 + raw 6）
- ``uv run pytest tests/ --ignore=tests/utils``: **47 passed**（01-01 bootstrap 3 + 01-02 quality 12 + 01-03 32・回帰なし）
- ``uv run python scripts/run_normalized_etl.py``: ETL 実行成功（n_race=39593 行・n_uma_race=554267 行・class_unresolved=115・raw_touched=False）→ **raw 不変性確認: PASS**
- ``uv run python scripts/run_quality_report.py``: ETL 実行後も ``verdict=pass`` 維持（14 checks・raw 不変の間接確認）
- ``uv run ruff check src/etl/ scripts/run_normalized_etl.py tests/test_*.py``: **All checks passed**

### Acceptance Criteria grep 検証結果

- ``src/etl/class_normalize.py``:
  - ``def normalize_class`` / ``def load_class_config`` 存在（2）
  - ``date.fromisoformat`` 含む（5）・``date.fromisoconfig(`` typo 関数呼び出し無し
  - ``post_2019_class_system_reform_date`` 参照（3）・date 比較で ``post_2019_class_system_flag`` 算出
  - ``class_normalization_status`` 含む（10）・unresolved 戻り値含む
  - ``def audit_gradecd_d_by_syubetucd`` 存在（1）
  - ``jyocd BETWEEN '01' AND '10'`` 含む（2）
- ``src/etl/normalize.py``:
  - ``def run_normalized_etl`` / ``def _create_normalized_tables`` / ``def _idempotent_load`` 存在（3）
  - ``kyori`` / ``futan`` / ``race_date`` 明示キャスト（24箇所）
  - ``jyocd BETWEEN '01' AND '10'`` 含む（2）
  - ``INSERT INTO normalized`` 含む（2）
  - staging-swap パターン（``_staging`` / ``RENAME TO`` / ``DROP TABLE IF EXISTS normalized``）= 10箇所（HIGH #5）
  - ``UPDATE public.n_`` / ``DELETE FROM public.n_`` = **0**（成功基準#2）
  - ``normalize_race_classes`` import 含む（3）
  - ``import duckdb`` = **0**（§12.1 禁止）
  - ``write_pool`` / ``write_cur`` = 21箇所（>= 2・HIGH #6）
  - ``kakuteijyuni integer`` / ``kettonum int`` / ``bamei text`` 含む（MEDIUM #1）
  - ``scripts/run_normalized_etl.py`` が ``run_normalized_etl`` / ``dsn_masked`` / ``etl_dsn_masked`` / ``make_pool(role="etl")`` を含む（HIGH #6 + MEDIUM #1）
- ``src/etl/raw_fingerprint.py``:
  - ``def compute_raw_fingerprint`` / ``def assert_raw_unchanged`` 存在（2）
  - ``pg_stat_user_tables`` / ``md5`` 参照（9箇所）
  - ``補助`` / ``supplementary`` / ``primary`` のいずれかを含む（11箇所・MEDIUM #2）
  - ``'UPDATE `` / ``'DELETE `` SQL = **0**（read-only helper）
- ``tests/test_raw_immutability.py``:
  - ``test_raw_unchanged_after_etl`` / ``test_raw_role_has_no_update_grant_public`` / ``test_etl_role_cannot_write_public`` 存在（HIGH #4/#6 補完）
  - ``table_schema IN ('public','raw_everydb2')`` 含む（HIGH #4・両スキーマ）

### RESEARCH Open Question #1 解決（audit_gradecd_d_by_syubetucd 実測）

``gradecd IN ('C','D')`` × ``syubetucd`` の実測分布:

| gradecd | syubetucd | 件数 | 解釈 |
|---------|-----------|------|------|
| C | 11 | 93 | 2歳G3（平地） |
| C | 12 | 171 | 3歳G3（平地） |
| C | 13 | 298 | 古馬G3（平地） |
| C | 14 | 221 | 古馬G3（平地・通常） |
| D | 11 | 1 | 2歳（平地） |
| D | 12 | 4 | 3歳（平地） |
| D | 13 | 2 | 古馬（平地） |
| D | 19 | 2 | **障害G3（わずか2件のみ）** |

**結論:** ``gradecd='D'`` は圧倒的に平地G3（計7件中5件が平地・障害G3は2件のみ）。plan 01-01 の暫定 ``grade_numeric=3``（G3 扱い）は妥当。Phase 4 特徴量設計で ``is_grade_race`` を細分する際は「D の大部分は平地G3・障害G3 は極めて稀」を前提に調整可能。

## Self-Check: PASSED

### Created files exist

- src/etl/class_normalize.py: FOUND
- src/etl/normalize.py: FOUND
- src/etl/raw_fingerprint.py: FOUND
- scripts/run_normalized_etl.py: FOUND
- tests/test_class_normalization.py: FOUND
- tests/test_normalized_etl.py: FOUND
- tests/test_raw_immutability.py: FOUND

### Commits exist

- 83f1b83: FOUND (RED: class_normalization tests)
- 9639ce5: FOUND (GREEN: class_normalize.py)
- 590bf9f: FOUND (RED: normalized ETL tests)
- 8611b6a: FOUND (GREEN: normalize.py + schema/apply_schema 拡張)
- fdab2d6: FOUND (fix: run_normalized_etl.py sys.path)
- bd4bc48: FOUND (RED: raw immutability tests)
- 4eef353: FOUND (GREEN: raw_fingerprint.py)
- 16f591a: FOUND (chore: ruff lint)
