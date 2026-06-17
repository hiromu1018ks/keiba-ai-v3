---
phase: 1
slug: trust-foundation
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-17
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> Phase 1 は CLAUDE.md の Core Value「リークなく検出」の根幹を確立する。リーク防止プリミティブ（merge_asof backward join・race_id-grouped 時系列分割・leak-safe calibration・frozen category map）に加え、DB ロール分離と品質ゲートを含む。本 Phase の脅威モデリングは plan-time に全4 PLAN への `<threat_model>` ブロックとして著述済み（`register_authored_at_plan_time: true`）。

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `.env` → プロセス環境変数 | DB 認証情報（パスワード）がプロセスに渡る境界。`.env` は gitignore、コード内ハードコード禁止（ASVS V8） | DB password（秘匿） |
| readonly ロール → `everydb2.public.n_*`（物理）および `raw_everydb2.*`（VIEW） | raw データへの読取専用アクセス境界。**両スキーマで** UPDATE/DELETE/TRUNCATE が REVOKE される（ASVS V4）。raw_everydb2 は VIEW として構造的非更新 | raw JRA レースデータ（非改変） |
| ETL ロール → `normalized.*` | normalized スキーマへの書込境界。raw には SELECT-only（ASVS V4） | 正規化済 JRA データ |
| プロセス → PostgreSQL | psycopg3 接続。DSN に生パスワードを含むため `dsn_masked` のみログ出力可能（ASVS V8 Information Disclosure） | DSN / SQL クエリ |
| readonly_cur → `everydb2.public.n_*`（品質ゲート SELECT） | 品質ゲート SELECT の境界。読取専用ロールで UPDATE/DELETE 不可 | raw 集計値 |
| `reports/` → CI / 人間 | 出力レポートの境界。JSON に機密情報（DB パスワード等）を含めない（allowlist filter） | check verdict（非秘匿） |
| 訓練窓 → val/test データ | category map が訓練窓で fit され val/test に適用される境界。test 構成の leakage を防ぐ（§14.3） | category code dict |
| train slice → calibration slice | `CalibratedClassifierCV(cv='prefit')` が両者を分離する境界。時系列順序逆転で calibration リーク（§15.2） | calibrator 状態 |
| feature history → observation cutoff | `merge_asof(direction='backward')` が cutoff 以前の履歴のみ付与する境界。未来情報の cutoff 跨ぎで feature リーク（§13） | 過去集計特徴量 |
| train race_id → test race_id | `race_id_time_series_split` が race_id を分割する境界。同一 race_id の train/test またぎ・等値タイムスタンプ跨ぎは §8.4 違反 | race_id group |

---

## Threat Register

> Status: **closed** ×25（全 disposition 済み）。Evidence 列は `gsd-security-auditor` が verify-mitigations-exist モードで実装から抽出した file:line 証拠。

| Threat ID | Category | Component | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|-------------|-----------------------|--------|
| T-01-01 | Information Disclosure | DSN/ログのパスワード露出 | mitigate | `SecretStr` for db_password/etl_db_password (`settings.py:35,43`); `dsn_masked`/`etl_dsn_masked` (`:73-87`); `test_dsn_masks_password` (`test_bootstrap.py:13-36`) | closed |
| T-01-02 | Tampering | raw(`public.n_*`) 誤更新 | mitigate | REVOKE UPDATE,DELETE,TRUNCATE on `public` AND `raw_everydb2` FROM both roles + ALTER DEFAULT PRIVILEGES (`apply_schema.sql:77-85`, `schema.py:105-117`); raw_everydb2 as VIEW (`apply_schema.sql:39-43`) | closed |
| T-01-03 | Tampering | silent fallback で未知コード隠蔽 | mitigate | `unresolved_strategy: "error_and_isolate"` (`class_normalization.yaml:130`); F/G/H unresolved (`:96-116`) | closed |
| T-01-04 | Information Disclosure | DB 認証情報の notebook/コード埋め込み | accept | local-only 単一ユーザ（§19.3）+ SecretStr + `.env` gitignore (`.gitignore:2`) + `dsn_masked`。CI secret injection は Phase 8 で評価。→ Accepted Risks Log 参照 | closed |
| T-01-05 | Tampering | ETL ロール未定義で raw 読取ロール権限で normalized 書込 | mitigate | `etl_dsn` + `make_pool(role="etl")` 分離 (`connection.py:21-52`); GRANT INSERT は normalized のみ (`apply_schema.sql:65,68`); raw SELECT-only (`:66-67`); `test_etl_dsn_uses_etl_role` (`test_bootstrap.py:39-49`) | closed |
| T-01-06 | Tampering | ロール名 string-substitute で SQL injection | mitigate | `psycopg.sql.Identifier` で安全 quote、実行時置換 (`run_apply_schema.py:34-37,47-64`); `_require_env` で env 強制 (`:81-88`) | closed |
| T-01-SC | Tampering | uv 依存の供給チェーン | mitigate | `uv.lock` が全 package version pin（psycopg 3.3.4, pandas 3.0.3, sklearn 1.9.0 等）; 01-RESEARCH §Package Legitimacy Audit 検証済 | closed |
| T-02-01 | Tampering | silent fallback で品質チェック結果隠蔽 | mitigate | `verdict = "pass" if all(r.passed ... severity=="block")` 機械判定 (`quality_gate.py:583`); `CheckResult` dataclass (`:91-106`); `_load_allowed_codes` 失敗で fail (`:131-133,149-150`) | closed |
| T-02-02 | Information Disclosure | `reports/quality_report.json` へ認証情報混入 | mitigate | allowlist `{name,passed,severity,detail}` (`run_quality_report.py:45`); `_filter_check` を dump 前適用 (`:48-53,64`); `CheckResult` フィールド固定 (`quality_gate.py:91-106`) | closed |
| T-02-03 | Repudiation | 品質ゲート未実行で偽 verdict=pass | mitigate | `--fail-on-block` default True, exit 1 (`run_quality_report.py:148-153,216-217`); Settings error → exit 2 (`:159-184`); DB-test skip は `KEIBA_SKIP_DB_TESTS=1` のみ (`conftest.py:66-78`) | closed |
| T-02-04 | Tampering | mojibake / code-value anomaly 未検出 | mitigate | `_check_mojibake` U+FFFD 検出 (`quality_gate.py:410-452`); `_check_code_value_anomalies` 安全 param binding (`:455-525`); 両者 INFO で常時実行 (`:580-581`); 回帰テスト (`test_quality_gate.py:176-226`) | closed |
| T-03-01 | Tampering | ETL バグで raw(`public.n_*`) 誤更新/削除 | mitigate | REVOKE 両スキーマ×両ロール; `normalize.py` は raw に SELECT のみ（grep gate）; `raw_fingerprint.py:36-150` row-hash+count+pg_stat; `assert_raw_unchanged` (`:108-150`); 権限テスト両スキーマ (`test_raw_immutability.py:69-81,84-109`) | closed |
| T-03-02 | Tampering | hondai regex で 2019 改革に分類破綻 | mitigate | `jyokencd5×gradecd×year` のみ機械導出、`hondai` 非参照 (`class_normalize.py:97-154`); `test_normalize_class_signature_and_no_hondai_match` (`test_class_normalization.py:41`); `test_code_005_spans_reform` (`:60`) | closed |
| T-03-03 | Tampering | 未知 jyokencd5/gradecd の silent fallback 誤分類 | mitigate | 未知 → `class_normalization_status="unresolved"` + WARNING (`class_normalize.py:120-134`); `post_2019_class_system_flag` は unresolved 時も race_date から計算 (`:54-60,92,112`); テスト (`test_class_normalization.py:107,120,129`) | closed |
| T-03-04 | Tampering | 暗黙 varchar キャストで文字列ソート事故 | mitigate | `pd.to_numeric(errors="coerce")` 明示キャスト (`normalize.py:285,288-289`); `futan` real (`:68`); `test_type_cast_kyori_int` (`test_normalized_etl.py:163`) | closed |
| T-03-05 | Tampering | NAR(jyocd>=30) が normalized に混入 | mitigate | `jyocd BETWEEN '01' AND '10' AND year::int >= 2015` 単一ソース (`filters.py:36`); `normalize.py:51,181,237` で使用; `test_jra_only_filter` (`test_normalized_etl.py:198`); `test_jra_filter_single_source_of_truth` (`test_quality_gate.py:404`) | closed |
| T-03-06 | Tampering | DuckDB で永続化し §12.1 違反 | mitigate | `normalize.py` に `import duckdb` なし（grep gate = 0）; PostgreSQL のみ永続化 | closed |
| T-03-07 | Tampering | ETL 再実行で normalized 行重複・再現性破綻 | mitigate | `_idempotent_load` staging-table-swap: advisory lock → CREATE _staging → TRUNCATE → INSERT → rowcount verify → atomic DROP+RENAME (`normalize.py:356-441`); CR-04 hardenings (`:390-393,398-402,425-430`); `test_etl_idempotent_rerun` (`test_normalized_etl.py:246`) | closed |
| T-03-08 | Tampering | ETL ロール未定義で raw 読取権限で normalized 書込 | mitigate | `run_normalized_etl(write_pool=...)` (`normalize.py:624-625`); `make_pool(role="etl")` 経由; ETL は normalized に INSERT のみ (`apply_schema.sql:65,68`); `test_etl_role_cannot_write_public` が `InsufficientPrivilege` を assert (`test_raw_immutability.py:84-109`) | closed |
| T-04-01 | Tampering | `merge_asof` への未ソート入力で黙って誤結合 | mitigate | `pit_join_backward` が**呼出元入力（sort 前）**の `is_monotonic_increasing` を事前チェックし `raise ValueError` (`pit_join.py:85-94`); sort 後チェックは到達不能のため禁止（`:75-77` コメント）; `test_no_silent_resort_implementation_guard` (`test_pit_join.py:81`) | closed |
| T-04-02 | Tampering | 同一 race_id の train/test またぎ・等値タイムスタンプ跨ぎ | mitigate | `race_id_time_series_split`: (a) race_id disjoint (b) `max(train_time) < min(test_time)` **strict `<`** (c) non-empty、全て `raise ValueError` (`group_split.py:104-127`); テスト (`test_group_split.py:34,44,59`) | closed |
| T-04-03 | Tampering | category map が test 構成で再 fit し cardinality leakage | mitigate | `fit_category_map` は訓練窓 series のみ受取 (`category_map.py:24-50`); `apply_category_map` は既存 dict を使い再 fit しない (`:53-76`); `__UNSEEN__`/`__MISSING__` 機械フォールバック | closed |
| T-04-04 | Tampering | NaN→code -1 で missing と unknown を混同 | mitigate | NaN→`__MISSING__` 置換→別コード→`.astype("int32")` 非負保証 (`category_map.py:73-76`); `test_non_negative_int32` (`test_category_map.py:55`) | closed |
| T-04-05 | Tampering | `CalibratedClassifierCV(cv=5)` KFold shuffle で look-ahead leak | mitigate | `if not (train_max_ts < calib_min): raise ValueError` strict `<`、assert 非使用 (`calibrator.py:86-94`); `FrozenEstimator` + `CalibratedClassifierCV(estimator=frozen)` で sklearn 1.9 prefit 等価 (`:100-102`); `test_calib_before_train_raises_valueerror` が `-O` で検証 (`test_calibrator.py:89`) | closed |
| T-04-06 | Tampering | `python -O` で assert ベースのリーク防止ガードが無効化 | mitigate | 4 primitive 全て `if ...: raise ValueError(...)` 形式のみ・**assert 0件**（grep 確認）; 回帰検出 `inspect.getsource()` で assert トークン不在を検査（`test_no_silent_resort_implementation_guard`, `test_assert_is_replaced_by_raise`, `test_calib_raises_is_valueerror_not_assertion`） | closed |

*Disposition: mitigate（実装必須）· accept（文書化済リスク受諾）· transfer（第三者委譲）*
*Status: closed（mitigation 実装確認済 または accepted risks 文書化済）· open*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-04 | T-01-04 | DB 認証情報の notebook/コード埋め込み。本プロジェクトは local-only 単一ユーザ環境（§19.3: Streamlit localhost・認証不要）。`SecretStr` + `.env`（gitignore 済 `:2`）+ `dsn_masked`/`etl_dsn_masked` の4重保護で local 脅威モデルに対し十分。CI/本番への secret injection・rotation は Phase 8（運用ハードニング）で評価予定（low risk）。再評価トリガ: CI/デプロイ環境導入時・複数ユーザアクセス導入時 | hart（project owner） + gsd-security-auditor（根拠有効性再確認） | 2026-06-17 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-17 | 25 | 25 | 0 | gsd-security-auditor（verify-mitigations-exist mode, ASVS L1, block_on: high） |

### Audit 2026-06-17 — Detail

| Metric | Count |
|--------|-------|
| Threats found | 25 |
| Closed | 25 |
| Open | 0 |

- **Audit mode:** `register_authored_at_plan_time: true` → verify-mitigations-exist（新規脅威スキャンなし、register は plan-time の4 `<threat_model>` ブロックが権威）。
- **Verdict:** `## SECURED` — 全25脅威の mitigation が実装に PRESENT（file:line 証拠付き）。PARTIAL/ABSENT なし。
- **Accepted risk:** T-01-04（AR-01-04）の accept 根拠が現状でも有効（local-only + 4重保護すべて実装確認）。
- **Unregistered flags:** なし。4 SUMMARY 全て「該当なし」。`GRANT CREATE ON SCHEMA normalized TO keiba_etl`（staging-swap 用）は T-03-07/T-03-08 にマップ済みで `normalized` 内に限定、`public`/`raw_everydb2` の CREATE は依然なし・REVOKE 維持。
- **Implementation files:** READ-ONLY（監査中に変更なし）。
- **Note:** 01-REVIEW.md の CR-03〜CR-07 / WR-01..09 / IN-01..06 は品質・保守性の指摘であり、`<threat_register>` の未充足 mitigation ではない（例: CAST-based quality gate・NAR tampering 検出・BT-1..5 backtest helper は本 audit scope 外の新規脅威扱い）。

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-17
