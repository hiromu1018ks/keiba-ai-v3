---
phase: 9
slug: speed-figure-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-25
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 成功基準 SC#1-6（ROADMAP.md）と RESEARCH.md `## Validation Architecture` を統合。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（v1.0 踏襲）+ `tests/audit/` adversarial パッケージ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/features/test_speed_figure.py tests/features/test_speed_figure_pit.py -x` |
| **Full suite command** | `uv run pytest`（`KEIBA_SKIP_DB_TESTS` unset で live-DB テスト含む） |
| **Estimated runtime** | ~120 秒（quick）/ ~600 秒（full + live-DB snapshot 再生成） |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/features/ -x`（speed_figure 単体・PIT・parity）
- **After every plan wave:** Run `uv run pytest`（`KEIBA_SKIP_DB_TESTS` unset・フル suite）
- **Before `/gsd-verify-work`:** Full suite must be green + live-DB snapshot 再生成（SC#3）+ adversarial audit GREEN（SC#4）+ ドメイン整合性可視化確認（SC#5）+ stop gate 評価（SC#6）
- **Max feedback latency:** 120 秒（quick）/ 600 秒（wave gate）

---

## Per-Requirement Verification Map

| Req / SC | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|----------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| SC#1 / FEAT-01 | byte-reproducible 再生成（同一 metadata で bit-identical） | T-9-03（PAR/variant 計算の full-period 値混入） | par/variant は expanding/as-of で算出（full-period 固定値禁止） | unit + integration | `uv run pytest tests/features/test_speed_figure.py::test_byte_reproducible_regeneration -x` | ❌ W0 | ⬜ pending |
| SC#2 / SAFE-01 | PIT-correct（`available_at < feature_cutoff_datetime`・strict `<`・adversarial lookahead） | T-9-01 / T-9-02（target 当日結果リーク・same-day future 注入） | target race 当日の走破タイム/馬場結果は par/variant に絶対混入させない | adversarial | `uv run pytest tests/features/test_speed_figure_pit.py -x` | ❌ W0 | ⬜ pending |
| SC#3 / FEAT-01 | §12.4 metadata + registry↔Parquet parity（live-DB） | — | `feature_snapshot_id`・`feature_cutoff_datetime`・`feature_availability` エントリが §12.4 準拠 | integration | `uv run pytest tests/features/test_speed_figure.py::test_registry_parquet_parity -x`（KEIBA_SKIP_DB_TESTS unset） | ❌ W0 | ⬜ pending |
| SC#4 / SAFE-01 | proxy 排除（オッズ/人気/過去人気/過去オッズが新特徴量に混入しない） | T-9-04（市場回帰 proxy 混入） | FEATURE_COLUMNS allowlist のみ・AST read-only・allowlist grep で静的証明 | adversarial | `uv run pytest tests/audit/test_audit_speed_figure.py -x` | ❌ W0 | ⬜ pending |
| SC#5 / FEAT-01 | ドメイン整合性（同一馬連続走安定・クラス昇降変動・外れ値なし） | — | 指数は float（丸めない）・クラス昇降で有意変動・極端外れ値なし | integration（live-DB 可視化） | `uv run python scripts/verify_speed_figure_domain.py`（Plotly HTML・手動確認） | ❌ W0 | ⬜ pending |
| SC#6 / FEAT-01 | stop gate 4 指標 + residual proxy（v1.0 baseline 比較） | — | 同一 BT split / 同一 odds snapshot policy / 同一選択ルール・§15.2 事前登録指標不変 | integration（live-DB） | `uv run python scripts/run_speed_figure_stopgate.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Per-Task Verification Map（task ID 単位）は planner が PLAN.md を作成後、各 task の `<verify>` と突き合わせて本表を拡張する。本表は requirement/SC 単位の上位契約。

---

## Wave 0 Requirements

- [ ] `tests/features/test_speed_figure.py` — covers SC#1/SC#3（par/variant/speed_figure 算出・byte-reproducible・registry parity・`_ROLLING_SYSTEMS` 拡張）
- [ ] `tests/features/test_speed_figure_pit.py` — covers SC#2（adversarial lookahead・5 段階鋳型: target / same_day_prior / same_day_later / previous_day / future 全除外）
- [ ] `tests/audit/test_audit_speed_figure.py` — covers SC#4（AST read-only・allowlist grep・odds/ninki/過去オッズ proxy 排除証明・`tests/audit/` パッケージ踏襲）
- [ ] `scripts/verify_speed_figure_domain.py` — covers SC#5（Plotly HTML・同一馬連続走・クラス昇降・外れ値）
- [ ] `scripts/run_speed_figure_stopgate.py` — covers SC#6（v1.0 baseline 比較・4 指標・residual proxy・`evaluator.py`/`segment_eval.py` 踏襲）
- [ ] Framework install: 不要（pytest 9.1.0 / plotly / scipy は v1.0 既存・新規インストールなし）

*Framework は検出済み・新規インストール不要。テストファイル・スクリプトが Wave 0 gap。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ドメイン整合性の視覚確認 | SC#5 | 指数分布の単調性・外れ値は目視判断が必要 | `scripts/verify_speed_figure_domain.py` 生成の Plotly HTML を開き、同一馬の連続走で指数が大きく安定・クラス昇降で有意変動・極端外れ値がないことを確認 |
| stop gate の継続可否判断 | SC#6 | 「両方改善/residual 無し → 構造的限界寄り」のユーザー確認（D-16）は人間の意思決定 | `scripts/run_speed_figure_stopgate.py` の 4 指標 + residual proxy 結果を見て、Phase 10-12 進行前にマイルストーン継続可否を評価 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references（上記 5 ファイル/スクリプト）
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s（quick）/ 600s（wave）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
