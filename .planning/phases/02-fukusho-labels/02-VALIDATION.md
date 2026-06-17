---
phase: 2
slug: fukusho-labels
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-17
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> Source of truth: `02-RESEARCH.md` §Validation Architecture + 各 PLAN の `<verify><automated>` ブロック。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（`[VERIFIED: pyproject.toml]`・Phase 1 導入済み・新規インストール不要） |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`（testpaths=`["tests"]`・Phase 1 実績） |
| **Quick run command** | `uv run pytest tests/test_fukusho_label.py tests/test_label_reconcile.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | unit 約 5 秒 / full（DB integration 含む）約 60 秒 |

**実行環境ノート:**
- Python 3.12（uv 管理）・psycopg3 / pandas / pyyaml は Phase 1 の `pyproject.toml` に固定済み
- `KEIBA_SKIP_DB_TESTS` 環境変数で `@pytest.mark.requires_db` を一括 skip 可（CI・実DB未接続環境）
- `tests/conftest.py`（Phase 1 実績）が `settings` / `pg_pool` / `readonly_cur` / `write_cur` fixture を提供

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_fukusho_label.py tests/test_label_reconcile.py -x`
- **After every plan wave:** Run `uv run pytest`（full suite・raw_immutability 拡張含む）
- **Before `/gsd-verify-work`:** Full suite must be green（`uv run pytest` exit 0）
- **Max feedback latency:** ~60 秒（full suite・実DB接続時）

---

## Per-Task Verification Map

> 11 タスク（02-01-T1..T3 / 02-02-T1..T2 / 02-03-T1..T3 / 02-04-T1..T3）。各 `<automated>` コマンドは対応 PLAN の `<verify><automated>` ブロックから直接流用。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-T1 | 01 | 1 | LABEL-01/02/03/04 | T-02-02 / T-02-04 | label_spec.yaml が D-07 Git 管理下に配置・label_generation_version='v1.0.0' でバージョン管理・silent fallback 禁止（unresolved_strategy='error_and_isolate'） | shell + import smoke（pytest 未使用・W1） | `test -f src/config/label_spec.yaml && grep -c "label_generation_version" src/config/label_spec.yaml \| grep -q "^1$" && python3 -c "import yaml; cfg = yaml.safe_load(open('src/config/label_spec.yaml')); assert cfg['label_generation_version'] == 'v1.0.0'; ..."` | ❌ W1（pytest 対象外・config/SQL） | ⬜ pending |
| 02-01-T2 | 01 | 1 | LABEL-01/02/03/04 | T-02-01 / T-02-03 / T-02-04 | GRANT_ETL_SQL/GRANT_READER_SQL の label スキーマ拡張・public/raw_everydb2 の REVOKE 維持（D-06）・db_schema_label 追加 | shell + import smoke（pytest 未使用・W1） | `grep -q "GRANT USAGE, CREATE ON SCHEMA label TO {etl};" src/db/schema.py && grep -q "db_schema_label: str = \"label\"" src/config/settings.py && python3 -c "from src.db.schema import GRANT_ETL_SQL, GRANT_READER_SQL; assert 'SCHEMA label' in GRANT_ETL_SQL..."` | ❌ W1（pytest 対象外・config/SQL） | ⬜ pending |
| 02-01-T3 | 01 | 1 | LABEL-01/02/03/04 | T-02-01 / T-02-04 | `run_apply_schema.py` 再実行で GRANT 拡張を実DBに反映（Pitfall 6・permission denied 回避）・D-06 二重保護維持 | shell smoke（pytest 未使用・W1） | `uv run python scripts/run_apply_schema.py 2>&1 \| tail -5 \| grep -q "schema applied successfully"` | ❌ W1（pytest 対象外・schema apply） | ⬜ pending |
| 02-02-T1 | 02 | 1 | LABEL-01/02/04 | T-02-05 / T-02-06 | LABEL-01/02 unit test シナリオ（raw vs validated drift・sales_start_entry_count・payout 境界）・mock cursor と合成 DataFrame で DB 不要・Pitfall 3 反証 | unit（pytest collection・RED） | `test -f tests/test_fukusho_label.py && uv run pytest tests/test_fukusho_label.py --collect-only 2>&1 \| head -30 \| grep -q "test_raw_vs_validated_basic_8_horses"` | ❌ Wave 0（本タスクが作成） | ⬜ pending |
| 02-02-T2 | 02 | 1 | LABEL-04 + D-03 + W4 | T-02-05 / T-02-06 / T-02-07 | LABEL-04 エッジケース（5状態）+ W4 tokubaraiflag2 2シナリオ + D-03 §7.2 適格性 6理由の unit test・実カラム名 bataijyu/harontimel3/timediff 使用 | unit（pytest collection・RED） | `uv run pytest tests/test_fukusho_label.py --collect-only 2>&1 \| grep -c "test_" \| awk '{if ($1 >= 19) print "OK"; else print "NG"}' \| grep -q "^OK$"` | ✅（T1 で作成・T2 で拡張） | ⬜ pending |
| 02-03-T1 | 03 | 2 | LABEL-01/02/04 | T-02-08 / T-02-09 / T-02-10 / T-02-11 / T-02-13 / T-02-14 | fukusho_label.py ETL 本体（compute_fukusho_labels/classify_status/compute_is_model_eligible/run_label_etl）・Plan 02 RED を GREEN に・tokubaraiflag2 分岐（W4）・Pitfall 1/3 対策 | unit（pytest GREEN） | `uv run pytest tests/test_fukusho_label.py -x 2>&1 \| tail -5 \| grep -E "passed\|failed" \| grep -qE "(18 passed\|1[89] passed\|2[0-9] passed)"` | ✅（Plan 02 作成済み） | ⬜ pending |
| 02-03-T2 | 03 | 2 | LABEL-01/02/04 | T-02-08 / T-02-12 | scripts/run_label_etl.py（readonly/etl 2ロール pool・masked DSN・raw fingerprint 前後比較）+ test_raw_immutability.py 拡張 | unit（pytest collection） | `test -f scripts/run_label_etl.py && grep -q "from src.etl.fukusho_label import run_label_etl" scripts/run_label_etl.py && grep -q "test_raw_unchanged_after_label_etl" tests/test_raw_immutability.py && uv run pytest tests/test_raw_immutability.py --collect-only 2>&1 \| grep -q "test_raw_unchanged_after_label_etl"` | ✅（Phase 1 既存・拡張） | ⬜ pending |
| 02-03-T3 | 03 | 2 | LABEL-01/02/03/04 | T-02-08 | 実DB で label ETL を実行し rows_inserted 553,891 ± 数件・label_unresolved_count 376 ± 数件・raw 不変性確認（`human_verify_mode=end-of-phase` 逸脱・W5） | checkpoint:human-verify（実DB spot check） | `uv run python scripts/run_label_etl.py` exit 0・`SELECT count(*) FROM label.fukusho_label` ≈ 553,891・`SELECT count(*) FROM label.fukusho_label WHERE label_validation_status IS NULL` = 0 | N/A（実DB検証） | ⬜ pending |
| 02-04-T1 | 04 | 3 | LABEL-03 + D-02 | T-02-15 / T-02-16 / T-02-17 / T-02-18 | test_label_reconcile.py（§10.5 6検査 BLOCK/INFO + agreement + W3 unresolved_fraction + degraded_checks_count + T-02-02 認証情報非含有）・mock cursor と合成データ | unit（pytest collection・RED） | `test -f tests/test_label_reconcile.py && uv run pytest tests/test_label_reconcile.py --collect-only 2>&1 \| grep -c "test_" \| awk '{if ($1 >= 14) print "OK"; else print "NG"}' \| grep -q "^OK$"` | ❌ Wave 0（本タスクが作成） | ⬜ pending |
| 02-04-T2 | 04 | 3 | LABEL-03 | T-02-15 / T-02-16 / T-02-17 / T-02-18 / T-02-19 | label_reconcile.py 実装 + run_label_reconcile.py CLI・Plan 04 Task 1 RED を GREEN に・reconcile_against_payout が 6 BLOCK + 1 INFO（unresolved_fraction 含む・W3）+ agreement + verdict + degraded_checks_count を返す | unit（pytest GREEN） | `uv run pytest tests/test_label_reconcile.py -x 2>&1 \| tail -5 \| grep -E "passed\|failed" \| grep -qE "(14 passed\|1[45] passed\|1[4-9] passed)"` | ✅（T1 で作成） | ⬜ pending |
| 02-04-T3 | 04 | 3 | LABEL-03 + D-02 + SC#2 | T-02-15 / T-02-17 | 実DB で reconcile を実行し verdict='pass'・agreement_pct >= 99.9（実測 99.9987%）・各 check の count を確認（`human_verify_mode=end-of-phase` 逸脱・W5） | checkpoint:human-verify（実DB検証） | `uv run python scripts/run_label_reconcile.py` exit 0・verdict='pass'・agreement_pct >= 99.9 | N/A（実DB検証） | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Phase 2 の Wave 0 = **Plan 02-02**（test_fukusho_label.py を RED で先行作成）+ **Plan 02-04 Task 1**（test_label_reconcile.py を RED で先行作成）。両者とも `type: tdd`・`tdd_phase: red` で実装より先にテストを書く。

- [x] `tests/test_fukusho_label.py` — LABEL-01/02/04 + W4 複勝特払（tokubaraiflag2）2シナリオ + D-03 §7.2 適格性の unit test（計20テスト目標・Plan 02-02 Task 1+2 で作成・W4 対応で2件追加）
- [x] `tests/test_label_reconcile.py` — LABEL-03 §10.5 6検査 BLOCK/INFO + `>99.9%` agreement + W3 unresolved_fraction + WR-05 degraded_checks_count + T-02-02 認証情報非含有（計14テスト目標・Plan 02-04 Task 1 で作成・W3 対応で1件追加）
- [x] `tests/test_raw_immutability.py` — Phase 1 既存・Plan 02-03 Task 2 で `test_raw_unchanged_after_label_etl` を拡張
- [x] `tests/conftest.py` — Phase 1 既存（readonly_cur/write_cur fixture）を再利用・label 固有 fixture 追加不要
- [x] Framework install: 不要（Phase 1 で pytest 9.1.0 導入済み・`[VERIFIED: pyproject.toml]`）

### W1 対応: Plan 02-01 の pytest 非使用タスクの扱い

Plan 02-01 の3タスク（label_spec.yaml 作成 / schema.py GRANT 拡張 / run_apply_schema.py 実行）は **shell grep + `python3 -c` import smoke で検証し、pytest は使用しない**。理由:
- 設定ファイル（YAML）・DDL（SQL）・権限反映（CLI 実行）は pytest の unit test より shell smoke の方が直接性が高い
- pytest カバレッジは **Plan 02-02 の RED 作成（Wave 1 同時）から開始**・02-03 GREEN で本格化
- `test -f` / `grep -c` / `python3 -c "import yaml; yaml.safe_load(...)"` で YAML 構文・必須キー・実カラム名を検証
- `run_apply_schema.py` の実DB GRANT 反映は exit code 0 + ログ `schema applied successfully` で検証（CI ではなく実DBへの one-shot apply）

このため Per-Task Verification Map で 02-01-T1..T3 の `File Exists` 列は ❌ W1（pytest 対象外）だが、`<automated>` 検証コマンド自体は存在し実行可能。Nyquist 連続性は Plan 02-02（Wave 1 同時並行）で回復する。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 実DB で label ETL が553,891 行を正常処理し raw 不変 | LABEL-01/02/04 + D-06 | 合成 DataFrame では実DBのキャスト境界・NULL 分布を完全再現できない。55万行の実行は数分要し CI では実行不可 | Plan 02-03 Task 3: `uv run python scripts/run_label_etl.py` exit 0・rows_inserted ≈ 553,891・label_unresolved_count ≈ 376・`SELECT label_validation_status, count(*) FROM label.fukusho_label GROUP BY 1` で validated/dead_heat/unresolved 分布確認・`uv run pytest tests/test_raw_immutability.py::test_raw_unchanged_after_label_etl -x` passed |
| 実DB で reconcile が verdict='pass'・agreement >= 99.9% | LABEL-03 + SC#2 | held-out 10% + 層化サンプリングは実DBの全レース（39,580）が必要。mock cursor では完全一致検査の現実的分布を再現不能 | Plan 02-04 Task 3: `uv run python scripts/run_label_reconcile.py` exit 0・verdict='pass'・agreement_pct >= 99.9（実測 99.9987%）・`agreement.agree_count / total_held_out` 報告・`uv run pytest tests/test_label_reconcile.py -x` 14 passed |

**`human_verify_mode=end-of-phase` との関係（W5）:** Plan 02-03 Task 3 と Plan 02-04 Task 3 は `checkpoint:human-verify` を使用するが、これは `human_verify_mode=end-of-phase` の default から逸脱する。理由: 実DB against の ETL/reconcile 実行は agent が自律完了できず・実DB接続・psql spot check・数分の実行待ちが必要。**SUMMARY にこの逸脱と理由を明記する**。代替（auto タスク化）は実DB接続が CI で利用不能のため現実的でない。

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（02-01 は shell smoke・02-02/03/04 は pytest）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify（Wave 1 の 02-01-T3 → 02-02-T1 で pytest 連続性回復）
- [x] Wave 0 covers all MISSING references（02-02-T1/T2 と 02-04-T1 が test ファイル作成・Wave 1 と Wave 3 で完了）
- [x] No watch-mode flags（`uv run pytest -x` のみ・`--pdb` 等のインタラクティブモードなし）
- [x] Feedback latency < 60s（full suite・実DB接続時）
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter（Wave 0 = Plan 02-02 + 02-04 Task 1・両者とも RED 作成を完了前提）

**Approval:** approved 2026-06-17（revision mode・checker issues B2/W1 対応で充填）
