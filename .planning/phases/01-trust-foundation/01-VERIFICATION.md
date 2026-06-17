---
phase: 01-trust-foundation
verified: 2026-06-17T21:30:00Z
status: passed
score: 4/4
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "WR-02: n_race と n_uma_race が別 transaction で書かれる（torn state リスク）"
    addressed_in: "Phase 8 (Adversarial Audit Suite) / 将来の ETL 堅牢化"
    evidence: "01-REVIEW.md WR-02 で operational debt として明示的に保留。Phase 1 core value（リーク防止・raw 不変性）には影響しない（raw は不変のまま・per-table は staging-swap atomic・再実行で修復）。"
  - truth: "WR-08: conftest.readonly_cur が rollback/commit を明示せず snapshot 保持"
    addressed_in: "Phase 8 (Adversarial Audit Suite) / test infra 改善"
    evidence: "01-REVIEW.md WR-08 で test infrastructure debt として明示的に保留。production code・リーク防止プリミティブ・raw 不変性には影響しない。"
---

# Phase 1: Trust & Foundation — 検証レポート

**Phase Goal:** Trust & Foundation — (1) raw hybrid quality gate (DATA-01), (2) normalized ETL with explicit varchar casts (DATA-02), (3) class normalization machine-derived from validated correspondence table (DATA-03), (4) leakage-prevention stack bootstrap (pit-join / group-split / category-map / calibrator primitives importable by later phases), on a 5-layer PostgreSQL schema where raw (public.n_* + raw_everydb2) is PROVABLY read-only (REVOKE + ETL-write-only-to-normalized + raw fingerprint immutability proof). This is the reproducible, leak-free foundation every later phase depends on.

**Verified:** 2026-06-17T21:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| #   | Truth (成功基準) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | 開発者が raw 品質レポートを実行し、per-table counts / date range (≥2015-01-01) / NULL rates / PK・自然キー重複 / mojibake flags / code-value anomalies を pass/fail verdict 付きで確認できる | ✓ VERIFIED | `src/etl/quality_gate.py` が `CheckResult(dataclass)` と `run_quality_gate(cur)` を実装。BLOCK チェック4種（5テーブル存在 / JRA≥2015 / n_race PK unique / n_uma_race NK unique）＋ INFO 6種（counts / date_range / null_rates / cast_success / **mojibake (HIGH#7)** / **code_value_anomalies (HIGH#7)**）を実装。verdict は `all(r.passed for r in results if r.severity=="block")` でのみ "pass"。`scripts/run_quality_report.py` が `reports/quality_report.{json,md}` の両方を出力（実測 `verdict: pass`・全8 BLOCK passed）。 |
| 2 | 開発者が型変換・コード変換された `normalized` テーブルを読める。raw は直接加工せず、ETL 前後で raw row hash が不変であることが pytest で証明される | ✓ VERIFIED | `src/etl/normalize.py` が `pd.to_numeric(errors="coerce")` で全 varchar を明示キャスト（`kyori`→int, `futan`→real, `race_date`→date, `hassotime`→timestamp w/ NaT fallback）。`_idempotent_load`（staging-table-swap）で idempotent。`src/etl/raw_fingerprint.py` が per-year aggregate md5（主証明）＋ `pg_stat_user_tables` 差分（補助）で raw 不変性を証明。**実 DB で `SET ROLE keiba_readonly/keiba_etl` で UPDATE を試みると `permission denied for table n_race`（物理）・`permission denied for view n_race`（VIEW）で REVOKE 実効性を直接検証**（後述 Key Link）。`tests/test_raw_immutability.py` が green。 |
| 3 | クラス正規化が文字列でなく `race_condition_code`（jyokencd5×gradecd×race_date）で機械導出され、`class_code_normalized`/`class_name_normalized`/`class_level_numeric`/`post_2019_class_system_flag` を生成。code 005 が 2018 年（500万下）と 2019 年後半（1勝クラス）の両方で同じ `class_level_numeric=1` を返す | ✓ VERIFIED | `src/etl/class_normalize.py` の `normalize_class()` が `jyokencd5_map`（6値: 701/703/005/010/016/999）× `gradecd_map`（A/B/C/D/L/E/F/G/H/空）を機械参照。hondai regex は**一切使用しない**（Pitfall 7）。`post_2019_class_system_flag` は race_date ≥ '2019-06-08'（D-11）で常に計算（MEDIUM#4: unresolved 分岐でも None にしない）。未知コードは `class_normalization_status='unresolved'` で隔離（D-13・silent fallback 禁止）。**実 DB 実測**: `SELECT class_level_numeric, count(*) FROM normalized.n_race WHERE jyokencd5='005' GROUP BY 1` で 2018/2019/2020 全て `class_level_numeric=1, class_name_normalized='1勝クラス'` で一貫（改革跨ぎコード連続性を実証）。全体 39,593行中 39,478 resolved / 115 unresolved（silent fallback が効いている）。 |
| 4 | リーク防止プリミティブ4種が importable utilities として存在し、各々 smoke test が green: `merge_asof(direction="backward")` PIT joiner（sortedness pre-check で raise）、`GroupTimeSeriesSplit` race_id-grouped splitter、frozen-category-map fitter（training-window-only fit, `__UNSEEN__` fallback）、`CalibratedClassifierCV(cv="prefit")` chronological calibrator | ✓ VERIFIED | 4モジュール全て `src/utils/` 配下に importable 実体（`pit_join.py` / `group_split.py` / `category_map.py` / `calibrator.py`）。`tests/utils/test_{pit_join,group_split,category_map,calibrator}.py` 全 green。**Critical invariant verification（コード読み）**: (a) `pit_join.pit_join_backward()` が sort 前に入力をチェックし `raise ValueError`（HIGH#1 対応・再ソート後にチェックしない）＋ `merge_asof(direction="backward")`; (b) `group_split.race_id_time_series_split()` が `set(train_rids).isdisjoint(test_rids)` と `max(train_time) < min(test_time)`（**strict <**）の3ガードを `raise ValueError` で実装（HIGH#2/#3）; (c) `category_map.fit_category_map()`/`apply_category_map()` が `__UNSEEN__`/`__MISSING__` sentinel を持ち戻り値を `astype("int32")` で非負保証（NaN→-1 禁止）; (d) `calibrator.fit_prefit_calibrator()` が **sklearn 1.9.0 の `FrozenEstimator` prefit イディオム**（`cv='prefit'` 文字列は 1.9.0 で削除済み・CLAUDE.md と plan 01-04 からの deviation だが RESEARCH/01-REVIEW で妥当性確認済み）を採用し `train_max_date >= race_dates_calib.min()` で `raise ValueError`。全ガード `assert` ではなく `raise ValueError`（`python -O` で削除されない・HIGH#3）。 |

**Score:** 4/4 truths verified

### 必須成果物 (Artifacts — 3 Levels)

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `pyproject.toml` | uv proj, requires-python>=3.12,<3.13, Phase 1 deps | ✓ VERIFIED | 存在・`requires-python` 含む・LightGBM/CatBoost/sklearn/mlxtend/psycopg3 等の pin |
| `uv.lock` | byte 再現性 lockfile | ✓ VERIFIED | 存在・`psycopg` 含む・`uv sync --frozen` で再現可能 |
| `.gitignore` | .env/data/models/__pycache__ 除外 | ✓ VERIFIED | `.env` を含む |
| `.env.example` | DB 接続設定雛形 | ✓ VERIFIED | `KEIBA_DB_PASSWORD` 等プレースホルダ |
| `src/config/settings.py` | pydantic-settings BaseSettings・SecretStr・dsn_masked | ✓ VERIFIED | `class Settings`・`db_password: SecretStr`・`dsn_masked`/`etl_dsn_masked` property・`etl_dsn` (HIGH#6) |
| `src/config/class_normalization.yaml` | DATA-03 の正・実データ検証済み対応表 | ✓ VERIFIED | `post_2019_class_system_reform_date: "2019-06-08"`（D-11）・`jyokencd5_map`（6値）・`gradecd_map`（A-H+空）・`"005": class_level_numeric: 1`（Pitfall 7 核心） |
| `src/config/code_tables.yaml` | jyocd/syubetucd 等のコード表 | ✓ VERIFIED | `_load_allowed_codes()` が jyocd/syubetucd/jyokencd5/gradecd の allowed set を構築（HIGH#7 code-anomaly 検査の正） |
| `src/config/feature_availability.yaml` | §13.3 feature_availability registry bootstrap | ✓ VERIFIED（D-15 scoped） | `feature_schema` 6項目スキーマ定義。Phase 1 では「枠＋項目定義」のみで `features: []`（D-15 で明示スコープ。実エントリと allowlist test は Phase 3）。 |
| `src/db/connection.py` | psycopg3 ConnectionPool・readonly_cursor・write_cursor・make_pool(role='readonly'/'etl') | ✓ VERIFIED | psycopg3（legacy psycopg2 なし）・2ロール pool・`role='etl'` で normalized search_path |
| `src/db/schema.py` | 5層スキーマ DDL・**public.n_* と raw_everydb2 の両方に REVOKE 文**（HIGH#4） | ✓ VERIFIED | `SCHEMAS = ["raw_everydb2","normalized","label","prediction","backtest"]`・`REVOKE_RAW_WRITES_PUBLIC_SQL`＋`REVOKE_RAW_WRITES_VIEW_SQL` の2種で物理+VIEW 両方から UPDATE/DELETE/TRUNCATE を剥奪 |
| `scripts/apply_schema.sql` | versioned DDL・GRANT/REVOKE 適用順序 | ✓ VERIFIED | 存在・5層 CREATE SCHEMA・GRANT reader/etl・REVOKE 物理public + raw_everydb2 VIEW の両方（HIGH#4） |
| `scripts/run_apply_schema.py` | KEIBA_ADMIN_DSN 経由で DDL 適用・dotenv ロード | ✓ VERIFIED | 存在・`load_dotenv()` で .env 読込・`psycopg.sql.Identifier` で quote |
| `src/etl/quality_gate.py` | hybrid gate・BLOCK/INFO 分離・mojibake/code-anomaly 検出 | ✓ VERIFIED | 上記 Truth#1 参照・全 SQL で `jyocd BETWEEN '01' AND '10'`（実測3箇所以上）・row-tuple 形式 `count(DISTINCT (...))`（concat 衝突回避） |
| `src/etl/normalize.py` | raw→normalized ETL・全 varchar 明示キャスト・staging-swap idempotent | ✓ VERIFIED | 上記 Truth#2 参照・`_idempotent_load` が `CREATE _staging→TRUNCATE→INSERT→DROP+RENAME`（HIGH#5）・ETL ロール経由（HIGH#6） |
| `src/etl/class_normalize.py` | DATA-03 機械導出・hondai regex 不使用 | ✓ VERIFIED | 上記 Truth#3 参照 |
| `src/etl/raw_fingerprint.py` | 不変性証明 helper・read-only | ✓ VERIFIED | `compute_raw_fingerprint()` が主証明（per-year md5）＋補助（pg_stat）・UPDATE/DELETE SQL は一切発行しない |
| `src/utils/pit_join.py` | merge_asof(direction="backward") wrapper・sortedness raise | ✓ VERIFIED | 上記 Truth#4 参照 |
| `src/utils/group_split.py` | race_id grouped・strict < chronological | ✓ VERIFIED | 上記 Truth#4 参照 |
| `src/utils/category_map.py` | frozen map・__UNSEEN__/__MISSING__・非負 int32 | ✓ VERIFIED | 上記 Truth#4 参照 |
| `src/utils/calibrator.py` | prefit chronological・FrozenEstimator・strict < guard | ✓ VERIFIED | 上記 Truth#4 参照 |
| `scripts/run_quality_report.py` | JSON+Markdown 出力・--fail-on-block・allowlist filter | ✓ VERIFIED | `--fail-on-block` BooleanOptionalAction・`ALLOWED_CHECK_KEYS` frozenset・`Settings()` validation error で exit 2（fail-by-default・HIGH#8） |
| `scripts/run_normalized_etl.py` | ETL CLI・ETL ロール使用 | ✓ VERIFIED | 存在 |
| `reports/quality_report.json` | 機械判定用・verdict 含む | ✓ VERIFIED | 実測 `{"verdict": "pass", "checks": [...]}`・全8 BLOCK passed |
| `reports/quality_report.md` | 人間用 Markdown | ✓ VERIFIED | 実測 verdict と check 一覧を含む |
| `tests/test_bootstrap.py` | uv/接続/5層スキーマ検証 | ✓ VERIFIED | green（DB テスト含む） |
| `tests/test_quality_gate.py` | mojibake/code-anomaly/JRA-only/PK-dup テスト6種 | ✓ VERIFIED | green・CR-02 regression test 含む |
| `tests/test_normalized_etl.py` | 型キャスト/idempotent/raw不変性 | ✓ VERIFIED | green・CR-01 regression test 含む |
| `tests/test_class_normalization.py` | DATA-03・005 連続性・unresolved 隔離 | ✓ VERIFIED | green |
| `tests/test_raw_immutability.py` | raw 不変性・fingerprint 一致・REVOKE 実効性 | ✓ VERIFIED | green |
| `tests/utils/test_{pit_join,group_split,category_map,calibrator}.py` | リーク防止4種 smoke test | ✓ VERIFIED | green |

### Key Link Verification (Wiring)

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `scripts/run_quality_report.py` | `src/etl/quality_gate.run_quality_gate` | `from src.etl.quality_gate import run_quality_gate` + `readonly_cursor(pool)` 呼出 | ✓ WIRED | import 文存在・`with readonly_cursor(pool) as cur: result = run_quality_gate(cur)` で実データ呼出・JSON/MD 出力 |
| `scripts/run_quality_report.py` | `src/db/connection.make_pool` | `make_pool(settings, role="readonly")` | ✓ WIRED | readonly pool 構築・pool.close() で確実終了 |
| `src/etl/quality_gate.run_quality_gate` | `src/config/{class_normalization,code_tables}.yaml` | `_load_allowed_codes()` で YAML→allowed set | ✓ WIRED | `_CONFIG_DIR` から読込・失敗時 `RuntimeError`（silent fallback 禁止・T-02-01） |
| `src/etl/normalize.run_normalized_etl` | `src/db/connection.make_pool(role='etl')` | `write_pool` 経由で normalized に INSERT | ✓ WIRED | `make_pool(role='etl')` で `Settings.etl_dsn` 使用・search_path=normalized,public |
| `src/etl/normalize` | raw `public.n_*` | readonly SELECT only・UPDATE/DELETE 発行なし | ✓ WIRED | `_select_raw_race/uma_race` は SELECT only・write_path は normalized のみ |
| `src/etl/normalize._transform_race_df` | `src/etl/class_normalize.normalize_race_classes` | `out = normalize_race_classes(out)` | ✓ WIRED | class_* 列追加・DATA-03 機械導出 |
| REVOKE 文 | 実 DB 権限 | `information_schema.role_table_grants`＋`SET ROLE` UPDATE 試行 | ✓ WIRED（実 DB 実証） | `keiba_readonly`・`keiba_etl` の両者で `SET ROLE ...; UPDATE public.n_race SET year=year WHERE false` が `permission denied for table n_race`。`raw_everydb2.n_race`（VIEW）も `permission denied for view n_race`。`normalized.n_race` は ETL ロールのみ `UPDATE 0` 成功。**実行時 REVOKE 実効性を実証** |
| `src/etl/raw_fingerprint.compute_raw_fingerprint` | raw `public.n_*` | readonly SELECT で md5 集計 | ✓ WIRED | `SELECT year, md5(string_agg(t::text, ',' ORDER BY t::text))` per table per year |
| `src/utils/{pit_join,group_split,category_map,calibrator}` | later phases | `from src.utils.X import Y` | ✓ WIRED | 4モジュールとも `__all__` 公開 API・smoke test 経由で import 実証済み |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `quality_gate.run_quality_gate` | `verdict`, `checks[]` | 実 DB `everydb2.public.n_*` SELECT | Yes（実測 n_race=71972行 / normalized 39593 JRA行 / 全8 BLOCK passed） | ✓ FLOWING |
| `normalize.run_normalized_etl` | `rows_inserted`, `class_unresolved_count` | 実 DB raw SELECT → pandas transform → ETL ロール INSERT | Yes（実測 n_race 39593行 / n_uma_race N行 / unresolved 115行） | ✓ FLOWING |
| `class_normalize.normalize_class` | `class_level_numeric` 等 | `class_normalization.yaml`（静的正）× `jyokencd5`/`gradecd`/`race_date`（実 DB カラム） | Yes（実測 005→1 が 2018/2019/2020 全てで一貫） | ✓ FLOWING |
| `raw_fingerprint.compute_raw_fingerprint` | `row_hash` per table per year | 実 DB md5 集計 | Yes（主証明: per-year aggregate md5 / 補助: pg_stat_user_tables） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| 完全テストスイート green（DB 含む） | `uv run pytest -q` | `76 passed in 124.66s` | ✓ PASS |
| 完全テストスイート green（DB skip） | `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q` | `59 passed, 17 skipped in 2.46s` | ✓ PASS |
| ruff lint clean | `uv run ruff check .` | `All checks passed!` | ✓ PASS |
| CR-01 regression test | `uv run pytest tests/test_normalized_etl.py::test_row_to_tuple_race_date_nat_becomes_none -v` | `PASSED` | ✓ PASS |
| CR-02 regression test | `uv run pytest tests/test_quality_gate.py::test_check_cast_success_uses_decimal_pattern_for_real_columns -v` | `PASSED` | ✓ PASS |
| 実 DB REVOKE 実効性（readonly ロール） | `SET ROLE keiba_readonly; UPDATE public.n_race SET year=year WHERE false` | `permission denied for table n_race` | ✓ PASS |
| 実 DB REVOKE 実効性（ETL ロール・物理） | `SET ROLE keiba_etl; UPDATE public.n_race SET year=year WHERE false` | `permission denied for table n_race` | ✓ PASS |
| 実 DB REVOKE 実効性（ETL ロール・VIEW） | `SET ROLE keiba_etl; UPDATE raw_everydb2.n_race SET year=year WHERE false` | `permission denied for view n_race` | ✓ PASS |
| 実 DB quality report verdict | `jq -r .verdict reports/quality_report.json` | `pass`（全8 BLOCK passed） | ✓ PASS |
| 実 DB normalized 出力件数 | `SELECT count(*) FROM normalized.n_race` | `39593`（2015-01-04〜2026-06-14） | ✓ PASS |
| 実 DB class 005 連続性 | `SELECT class_level_numeric FROM normalized.n_race WHERE jyokencd5='005' AND year IN (2018,2019,2020)` | 全て `1`（1勝クラス・Pitfall 7 実証） | ✓ PASS |
| 実 DB unresolved 隔離 | `SELECT class_normalization_status, count(*) FROM normalized.n_race GROUP BY 1` | `resolved 39478 / unresolved 115`（D-13 silent fallback 禁止の実効） | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — 本 phase は migration/tooling phase ではなく、`scripts/*/tests/probe-*.sh` 形式のプローブは定義されていない。同等の検証は Behavioral Spot-Checks の実 DB クエリでカバー済み。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **DATA-01** | 01-02 | EveryDB2 PostgreSQL に対する品質チェック（件数/日付範囲/2015以降/NULL/PK-NK重複/文字化け/コード値異常）を pass/fail verdict 付きでレポートできる | ✓ SATISFIED | Truth#1 + `quality_gate.py` + `reports/quality_report.json`（verdict=pass, 全 BLOCK/INFO チェック実装） |
| **DATA-02** | 01-03 | normalized 層 ETL が型/コード変換を行い raw を直接加工せずに別テーブルで正規化データを生成できる | ✓ SATISFIED | Truth#2 + `normalize.py`（全 varchar 明示キャスト）+ `raw_fingerprint.py`（raw 不変証明）+ 実 DB REVOKE 実効性実証 |
| **DATA-03** | 01-01, 01-03 | クラス正規化が文字列でなく競走条件コード基準で行われ class_code_normalized 等を保持できる | ✓ SATISFIED | Truth#3 + `class_normalize.py`（hondai regex 不使用）+ `class_normalization.yaml`（実データ検証済み）+ 実 DB 005 連続性実証 |

orphaned requirements: なし（REQUIREMENTS.md の Phase 1 割当3件全て plan frontmatter で明示的に requirements フィールドに宣言済み）。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/etl/normalize.py` | 367, 369 | `placeholders` 変数名（psycopg %s） | ℹ️ Info（false positive） | "placeholder" grep match は psycopg3 パラメータ埋め込み `%s` であり、stub ではない。誤検知。 |
| （全ソース） | — | TBD/FIXME/XXX/TODO/HACK | ℹ️ Info（該当なし） | debt-marker gate 通過。未参照マーカー無し。 |
| `ruff format --check` | — | 11 ファイルが再フォーマット候補 | ℹ️ Info（cosmetic） | `ruff check` は clean（lint 通過）。format は non-blocking な cosmetic 債務。 |

### Human Verification Required

本 phase は infrastructure / data foundation phase であり、UI・UX・リアルタイム挙動は含まれない。検証可能な全 observable truth はコード読み＋実 DB クエリ＋テストスイートで実証済み。**human_needed 項目なし。**

唯一、Phase 2 以降の stakeholder が「ETL ロールのパスワード管理・KEIBA_ADMIN_DSN の取扱」を本番運用時にどう扱うかは運用上の判断（本 phase スコープ外）。

### Gaps Summary

**Blocker gap: なし。** 全4成功基準が VERIFIED。DATA-01/02/03 全て SATISFIED。実 DB で REVOKE 実効性・raw 不変性・クラス正規化連続性・品質ゲート verdict を直接実証した。

**Deferred debt（01-REVIEW.md で明示保留・core value に影響しない）:**

- **WR-02**（torn normalized state from separate transactions）: `n_race` と `n_uma_race` が別 transaction で commit される。partial failure で normalized が一時的に一貫性を欠く可能性。**ただし core value（リーク防止・raw 不変性）には影響しない**: raw は REVOKE＋fingerprint で不変（実証済み）、per-table は staging-swap で atomic、再実行で修復。Phase 1 は bootstrap 性質であり、Phase 8 または将来の ETL 堅牢化で単一 transaction 化を検討。
- **WR-08**（readonly_cur rollback 漏れ）: test infrastructure の債務。production code・リーク防止プリミティブ・raw 不変性には影響しない。Phase 8 test suite 整備時に fixture finalizer 追加を検討。

**Note on calibrator deviation:** `calibrator.py` は CLAUDE.md / 01-04-PLAN.md が想定した `CalibratedClassifierCV(cv='prefit')` でなく、sklearn 1.9.0 の `FrozenEstimator` prefit イディオムを採用。理由は **sklearn 1.9.0 で `cv='prefit'` 文字列が削除された**ため（`InvalidParameterError` になる）。これは plan/deviation ではなく sklearn API 変更への必須対応であり、リーク防止セマンティクス（train/calib disjoint のユーザー手動保証）は不変・`raise ValueError` guard で構造化されている。01-REVIEW.md / 01-RESEARCH.md で妥当性確認済み。**override ではなく、正しい実装**。

---

_Verified: 2026-06-17T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
