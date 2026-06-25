---
phase: 5
slug: ev-backtest
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-20
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 内容は `05-RESEARCH.md` §Validation Architecture（実DBスキーマ・件数実証済み）を正として転記。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（既存・外部インストール不要） |
| **Config file** | `pyproject.toml`（`[tool.pytest.ini_options]` testpaths=["tests"]・addopts="-ra"・markers 定義済み） |
| **Quick run command** | `uv run pytest tests/ev/ tests/utils/test_group_split.py -x -q` |
| **Full suite command** | `uv run pytest -q`（Phase 4 完了時 26 ファイル・262 tests green） |
| **Estimated runtime** | quick ~30秒 / full ~数分（モデル再学習含む BT 系統は別途） |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/ev/ tests/utils/test_group_split.py -x -q`（新規モジュールの unit test・<30秒）
- **After every plan wave:** `uv run pytest -q`（フル suite）
- **Before `/gsd-verify-work`:** フル suite green + BACK-03 対抗的テスト（6シナリオ stake/payout assert）全 green
- **Max feedback latency:** ~30秒（quick）/ 数分（full）

---

## Per-Task Verification Map

> Task ID は PLAN.md 確定後に具体化。ここでは 要件→テスト→コマンド の対応を正として固定（RESEARCH.md §Validation Architecture 転記）。

| Task Area | Plan | Wave | Requirement | Threat Ref | Secure behavior | Test Type | Automated Command | File Exists | Status |
|-----------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| EV_lower/EV_upper 計算 | TBD | 1 | EV-01 | — | 純粋関数・EV/probability/odds_lower のみ | unit | `uv run pytest tests/ev/test_ev_rank.py::test_ev_calculation -x` | ❌ W0 | ⬜ pending |
| 推奨ランク S/A/B/C/D | TBD | 1 | EV-02 | — | 閾値 S≥1.20/A≥1.10/B≥1.05/C≥1.00/D | unit | `uv run pytest tests/ev/test_ev_rank.py::test_rank_S -x` | ❌ W0 | ⬜ pending |
| race_id-grouped split + BT窓 | TBD | 1 | BACK-01 | T-後知恵リーク | race_id disjoint + strict chronological guard | unit | `uv run pytest tests/utils/test_group_split.py::test_bt_window_disjoint -x` | ❌ W0 | ⬜ pending |
| 仮想購入ルール fukusho_ev_v1 | TBD | 1 | BACK-02 | — | EV_lower≥1.05,p≥0.15,odds_lower≥1.5,top-2,100円,複勝 | unit | `uv run pytest tests/ev/test_purchase_simulator.py::test_purchase_top2 -x` | ❌ W0 | ⬜ pending |
| 返還会計 6シナリオ | TBD | 1 | BACK-03 | — | 取消/除外=返還(0)・中止=loss(100)・§11.6 | unit | `uv run pytest tests/ev/test_refund_accounting.py::test_refund_dead_loss -x` | ❌ W0 | ⬜ pending |
| odds 時点選択 backward | TBD | 1 | BACK-03 | T-未来リーク | `merge_asof(direction='backward')`・未来 snapshot 不使用 | unit | `uv run pytest tests/ev/test_odds_snapshot.py::test_odds_snapshot_future_leak -x` | ❌ W0 | ⬜ pending |
| odds policy 固定・no_bet | TBD | 1 | BACK-04 | T-後知恵オッズ | 30/10分前固定・特殊値/0件=no_bet sentinel | unit | `uv run pytest tests/ev/test_odds_snapshot.py::test_odds_snapshot_no_bet_empty -x` | ❌ W0 | ⬜ pending |
| staging-swap idempotent | TBD | 2 | BACK-03 | — | backtest_id scoped swap・advisory lock | integration | `uv run pytest tests/db/test_backtest_load.py::test_backtest_load_idempotent -x` | ❌ W0 | ⬜ pending |
| 回収率/max drawdown | TBD | 2 | §11.6 | — | 実 PayFukusyoPay 使用・effective_stake 分母控除 | unit | `uv run pytest tests/ev/test_metrics.py::test_metrics_recovery_rate -x` | ❌ W0 | ⬜ pending |
| BT窓再学習ループ | TBD | 2 | D-03 | T-リーク | split_3way periods 注入・後方互換 | integration | `uv run pytest tests/model/test_orchestrator_bt.py::test_split_3way_periods_injection -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/ev/__init__.py`・`tests/ev/conftest.py` — 合成データ fixtures（label flags + HARAI + JODDS mock）
- [ ] `tests/ev/test_odds_snapshot.py` — covers EV-01/BACK-04（backward / no_bet / special_values `----`/`****`/`0000`/`0999` / day_boundary / future_leak）
- [ ] `tests/ev/test_refund_accounting.py` — covers BACK-03（normal / scratch / excluded / dead_loss / fuseiritu / race_cancelled / no_sale / deadheat）
- [ ] `tests/ev/test_ev_rank.py` — covers EV-01/EV-02
- [ ] `tests/ev/test_purchase_simulator.py` — covers BACK-02（filter / top2 / tiebreak / no_eligible / no_sale）
- [ ] `tests/ev/test_metrics.py` — covers §11.6（recovery_rate / max_drawdown / counts）
- [ ] `tests/utils/test_group_split.py` — covers BACK-01（BT窓ヘルパ新設分・既存 test_group_split.py に追記）
- [ ] `tests/db/test_backtest_load.py` — covers 永続化（staging-swap idempotent・scoped swap）
- [ ] `tests/model/test_orchestrator_bt.py` — covers D-03（split_3way periods injection・後方互換）

**合成データ設計指針**（実JODDS未完でも検証可能）:
- JODDS mock: `HappyoTime`(mmddHHMM) 複数 snapshot・`FukuOddsLow` 正常値/特殊値混在
- HARAI mock: `FuseirituFlag2`/`HenkanFlag2`/`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5` 各シナリオ
- label mock: `is_scratch_cancel`/`is_dead_loss`/`is_race_cancelled`/`is_fukusho_sale_available` 各シナリオ
- prediction mock: p_fukusho_hit + race_key + PK 7カラム

*Framework install 不要・既存 pytest 9.1.0 + KEIBA_SKIP_DB_TESTS パターンで DB テスト制御*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 実データ backtest 実行（BT期間 2019-2025） | BACK-01/04 | JODDS 取得進行中（2026-06-20 開始・2015年25レース日分のみ）・実データが未完 | JODDS 取得完了後・`scripts/run_backtest.py` でフル行列実行・回収率/P/L を `reports/05-backtest.{md,json}` で確認 |
| 全25候補一括報告の目視（後知恵 winner 強調なし） | BACK-04 | 報告フォーマットの「推奨」記述欠如を目視 | `reports/05-backtest.md` に「推奨: BT-X」の記述が無いことを確認（主モデル確定は Phase 6） |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s（quick）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
