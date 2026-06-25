---
phase: 05-ev-backtest
plan: 02
subsystem: ev-backtest
tags: [ev, rank, purchase-simulator, metrics, bl3-betting, pure-functions, wave-1, leak-prevention]
status: complete
requires:
  - src/model/baseline.py::BL3_COMPARISON_CAVEAT (§14.2 caveat 再利用・変更なし)
  - tests/ev/conftest.py (Plan 01 合成 fixtures)
provides:
  - src/ev/__init__.py (Phase 5 EV/Backtest モジュール root)
  - src/ev/ev_rank.py::compute_ev_and_rank(df) / _rank(row) / RANK_THRESHOLDS
  - src/ev/purchase_simulator.py::select_bets(df, *, strategy, max_bets_per_race, stake_per_bet)
  - src/ev/purchase_simulator.py::FUKUSHO_EV_V1_STRATEGY / FUKUSHO_EV_V1_THRESHOLDS
  - src/ev/metrics.py::compute_backtest_metrics(df) -> dict
  - src/ev/bl3_betting.py::select_bl3_bets(market_df, *, max_bets_per_race, stake_per_bet)
  - src/ev/bl3_betting.py::BL3_BETTING_CAVEAT / BL3_MODEL_TYPE / BL3_ODDS_SNAPSHOT_POLICY
affects:
  - src/ev/odds_snapshot.py (Plan 05-03 で新設・本 plan の ev_rank purchase_simulator が EV_lower を消費)
  - src/ev/refund_accounting.py (Plan 05-03 で新設・本 plan の purchase_simulator.select_bets 出力を消費)
  - scripts/run_backtest.py (Plan 05-05 で新設・compute_ev_and_rank → select_bets → refund_accounting → compute_backtest_metrics の pipeline を構築)
tech-stack:
  added: []
  patterns:
    - 純粋関数 (df.copy()・入力破壊禁止・compute_bl1 analog)
    - 決定論的タイブレーク (sort_values kind='mergesort'・共有パターン7・seed 非依存)
    - §11.5 閾値定数化 (RANK_THRESHOLDS・T-05-03 mitigate)
    - §11.6 回収率ゼロ除算回避 (effective_stake=0 → recovery_rate=0.0・§8.3)
    - max drawdown race_date 昇順累積 (cummax-cumsum・T-05-05 mitigate)
    - 行 profit と集計 profit の不変量 (sum(row.profit)==sum(payout)+sum(refund)-sum(stake)・MEDIUM-02)
    - BL-3 EV 自己参照回避 (p=1/odds で EV=1.0・EV 計算せず人気順選択・D-04)
    - §14.2 caveat 再利用 (baseline.BL3_COMPARISON_CAVEAT import・T-05-04 mitigate)
key-files:
  created:
    - src/ev/__init__.py
    - src/ev/ev_rank.py
    - src/ev/purchase_simulator.py
    - src/ev/metrics.py
    - src/ev/bl3_betting.py
  modified:
    - tests/ev/test_ev_rank.py (test_rank_no_bet_is_D 追加 + test_rank_S 入力修正)
    - tests/ev/test_purchase_simulator.py (test_purchase_no_bet_excluded / test_purchase_stable_mergesort 追加)
    - tests/ev/test_metrics.py (test_metrics_zero_division / test_metrics_profit_invariant 追加)
    - tests/ev/test_bl3_betting.py (test_bl3_odds_policy_confirmed / test_bl3_model_type 追加)
decisions:
  - "05-02: EV/rank/purchase/metrics/bl3 は全て純粋関数 (DB 不要) で実装・合成データ検証可能・baseline.py compute_bl1 パターン踏襲"
  - "05-02: §11.5 ランク閾値を RANK_THRESHOLDS 定数で外部化 (T-05-03 mitigate・閾値すり替え防止・test で値を assert)"
  - "05-02: test_rank_S 入力 odds_lower 2.0→5.0 修正 (Rule 1・EV=0.30*2.0=0.60 では §11.5 S 条件 EV≥1.20 を満たさないため)"
  - "05-02: max drawdown は race_date→race_key→umaban 昇順の累積 profit cummax-cumsum (共有パターン7・T-05-05 mitigate)"
  - "05-02: profit_loss は集計式 sum(payout)+sum(refund)-sum(stake) を採用・行 profit (refund_accounting 出力) との不変量を test_metrics_profit_invariant で混在シナリオ検証 (MEDIUM-02/T-05-05b)"
  - "05-02: BL-3 は fukuoddslow 昇順 top-2 (EV でない) で選択・p=1/odds で EV=1.0 自己参照回避 (D-04)・EV_lower 列を付与しない"
  - "05-02: BL3_BETTING_CAVEAT は baseline.BL3_COMPARISON_CAVEAT を import して再公開 (Phase 4 と同一 §14.2 caveat・T-05-04 mitigate)"
  - "05-02: BL-3 sentinel model_type='bl3' / odds_snapshot_policy='confirmed' (JODDS 時点非依存・20 backtest 行列とは別枠)"
metrics:
  duration: 5m
  completed: 2026-06-20T23:26:09Z
  task_count: 3
  file_count: 9
---

# Phase 5 Plan 02: EV/rank/purchase/metrics/BL-3 純粋関数群 Summary

EV 計算・推奨ランク（§11.1/§11.5）・仮想購入ルール fukusho_ev_v1（§11.4/BACK-02）・回収率指標（§11.6）・BL-3 投資ROI比較（D-04/§14.2）の5つの純粋関数群を TDD RED→GREEN で実装し・Plan 01 Wave 0 RED stub のうち4ファイル（test_ev_rank/test_purchase_simulator/test_metrics/test_bl3_betting）を GREEN 化。全23テスト GREEN・リーク防止（no_bet→D・mergesort 決定論・§14.2 caveat・行/集計 profit 不変量）を検証。

## What Was Built

### Task 1: EV 計算 + 推奨ランク（ev_rank.py）— RED→GREEN

**RED (4b9ce1f):** `test_ev_rank.py` に `test_rank_no_bet_is_D` を追加（5テスト全て ModuleNotFoundError で RED）。

**GREEN (a2d630c):** `src/ev/__init__.py`（Phase 5 モジュール root）+ `src/ev/ev_rank.py` を新設:

- `compute_ev_and_rank(df) -> df`: `df.copy()` 純粋関数・§11.1 直線積 `EV_lower = p_fukusho_hit × fuku_odds_lower`・§11.5 階層判定（`df.apply(_rank, axis=1)`）
- `_rank(row)`: S→A→B→C→D 上から順に最初に満たした rank を返す・NaN（no_bet）は早期 'D'
- `RANK_THRESHOLDS` 定数: S(1.20/0.25/1.5)・A(1.10/0.20/1.5)・B(1.05/0.15)・C(1.00)（§11.5 完全準拠・T-05-03 mitigate）

**Rule 1 auto-fix:** `test_rank_S` 入力 `odds_lower=2.0` → `EV=0.30*2.0=0.60` で §11.5 S 条件 `EV≥1.20` 不満足のため `odds_lower=5.0`（`EV=1.50`）に修正。

### Task 2: 仮想購入ルール fukusho_ev_v1 + 回収率指標 — RED→GREEN

**RED (739a8c5):** `test_purchase_simulator.py` に `test_purchase_no_bet_excluded`・`test_purchase_stable_mergesort` を追加・`test_metrics.py` に `test_metrics_zero_division`・`test_metrics_profit_invariant` を追加（13テスト全て RED）。

**GREEN (73fc2b3):** `src/ev/purchase_simulator.py` + `src/ev/metrics.py` を新設:

- `select_bets(df, *, strategy='fukusho_ev_v1', max_bets_per_race=2, stake_per_bet=100)`:
  - 事前 filter: `is_fukusho_sale_available AND is_model_eligible AND fuku_odds_lower.notna()`（no_bet 除外・§11.3）
  - 購入条件 filter: `EV_lower≥1.05 AND p≥0.15 AND odds_lower≥1.5`（§11.4 完全準拠）
  - レース内 top-2: `sort_values(['race_key','EV_lower','umaban'], ascending=[True,False,True], kind='mergesort')` → `groupby('race_key').head(2)`（決定論的タイブレーク・共有パターン7）
  - `selected_flag`/`stake`/`backtest_strategy_version` 付与

- `compute_backtest_metrics(df) -> dict`:
  - `recovery_rate = sum(payout)/sum(effective_stake)`（分母0なら 0.0・§8.3 ゼロ除算回避）
  - `profit_loss = sum(payout) + sum(refund) - sum(stake)`（集計式）
  - `max_drawdown`: `sort_values(['race_date','race_key','umaban'], kind='mergesort')` → `profit.cumsum()` → `cummax - cumsum` の max（行整列・T-05-05 mitigate）
  - `selected_count`/`effective_bet_count`/`refund_count`/`hit_count`

**test_metrics_profit_invariant (MEDIUM-02/T-05-05b):** 合成 selected_with_accounting（通常的中/不的中/返還/競走中止 混在）で `sum(row.profit) == sum(payout)+sum(refund)-sum(stake)` を assert・refund 行や dead-loss 行で行ベース会計と集計会計が分岐しないことを担保。

### Task 3: BL-3 投資ROI比較（bl3_betting.py）— RED→GREEN

**RED (1daebc0):** `test_bl3_betting.py` に `test_bl3_odds_policy_confirmed`・`test_bl3_model_type` を追加（5テスト全て RED）。

**GREEN (d552302):** `src/ev/bl3_betting.py` を新設:

- `select_bl3_bets(market_df, *, max_bets_per_race=2, stake_per_bet=100)`:
  - 事前 filter: `is_fukusho_sale_available AND fukuoddslow.notna() AND fukuoddslow>0`
  - 確定複勝オッズ昇順（低い=人気高い）top-2: `sort_values(['race_key','fukuoddslow','umaban'], ascending=[True,True,True], kind='mergesort')` → `groupby('race_key').head(2)`
  - sentinel 付与: `model_type='bl3'`/`odds_snapshot_policy='confirmed'`（JODDS 時点非依存・D-04）
  - `BL3_BETTING_CAVEAT`（`baseline.BL3_COMPARISON_CAVEAT` import・§14.2 同一情報条件ではない注記・T-05-04 mitigate）
  - BL-3 は `EV_lower` 列を付与しない（`p=1/odds` で `EV=1.0` 自己参照回避・D-04）

## TDD Gate Compliance

各タスクは `type="auto" tdd="true"` で RED → GREEN の2コミット構成:

| Task | RED gate | GREEN gate |
|------|----------|------------|
| Task 1 (ev_rank) | `test(05-02): add test_rank_no_bet_is_D for no_bet→D rank (RED)` (4b9ce1f) | `feat(05-02): implement compute_ev_and_rank pure function (GREEN)` (a2d630c) |
| Task 2 (purchase/metrics) | `test(05-02): add no_bet/zero_division/profit_invariant RED tests (RED)` (739a8c5) | `feat(05-02): implement select_bets + compute_backtest_metrics (GREEN)` (73fc2b3) |
| Task 3 (bl3_betting) | `test(05-02): add bl3 odds_policy_confirmed + model_type RED tests (RED)` (1daebc0) | `feat(05-02): implement select_bl3_bets confirmed-odds baseline (GREEN)` (d552302) |

各タスクで `test(...)` commit (RED) の後に `feat(...)` commit (GREEN) が存在・gate sequence 満たす。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug fix] `test_rank_S` 入力値の数学的不整合修正**

- **Found during:** Task 1 GREEN 実行時
- **Issue:** Plan `<behavior>` の `test_rank_S` 仕様「EV_lower=1.25, p=0.30, odds_lower=2.0 → 'S'」は数学的に不整合（`EV_lower = 0.30 × 2.0 = 0.60` で §11.5 S 条件 `EV≥1.20` 不満足）。Plan 01 SUMMARY と同一の問題パターン。
- **Fix:** `odds_lower=5.0`（`EV_lower = 0.30 × 5.0 = 1.50`）に修正し・S 条件を正しく検証。docstring に Rule 1 auto-fix の旨を明記。
- **Files modified:** `tests/ev/test_ev_rank.py`
- **Commit:** a2d630c（Task 1 GREEN コミットに統合）

**2. [Rule 2 - Critical functionality] 決定論的タイブレーク検証テスト追加**

- **Found during:** Task 2 テスト拡張時
- **Issue:** Plan の acceptance criteria で `kind='mergesort'` 含有を要求するが・実行時検証テストが存在しなかった（source grep のみ）。
- **Fix:** `test_purchase_stable_mergesort` を追加し・`inspect.getsource(select_bets)` で `kind='mergesort'` 含有を検証（共有パターン7・§19.1 再現性・seed 非依存の決定論化を機械保証）。
- **Files modified:** `tests/ev/test_purchase_simulator.py`
- **Commit:** 739a8c5（Task 2 RED コミットに統合）

## Threat Mitigation Verification

| Threat ID | Category | Mitigation | Verification |
|-----------|----------|------------|--------------|
| T-05-03 | Tampering | `RANK_THRESHOLDS` 定数で §11.5 閾値を外部化（すり替え防止） | `test_rank_S` (1.20/0.25/1.5)・`test_rank_B_no_odds_threshold` (1.05/0.15・odds 閾値なし)・`test_rank_D_low_ev` (EV<1.00→D) (4b9ce1f RED / a2d630c GREEN) |
| T-05-04 | Information Disclosure | `BL3_BETTING_CAVEAT`（`baseline.BL3_COMPARISON_CAVEAT` import）で §14.2 caveat 付与 | `test_bl3_caveat`（§14.2 同一情報条件ではない）+ `test_bl3_odds_policy_confirmed`（confirmed sentinel）(1daebc0 RED / d552302 GREEN) |
| T-05-05 | Tampering | max drawdown は `race_date` 昇順ソート（kind='mergesort'）+ cummax-cumsum | `test_metrics_max_drawdown`（累積 [100,200,50,150] → max DD=150）(739a8c5 RED / 73fc2b3 GREEN) |
| T-05-05b | Tampering | 行 profit（refund_accounting）と集計 profit（metrics）の不変量 | `test_metrics_profit_invariant`（混在シナリオで sum(row.profit)==sum(payout)+sum(refund)-sum(stake) を assert）(739a8c5 RED / 73fc2b3 GREEN) |

## Verification

全 acceptance criteria 検証済み:

```
=== Task 1 GREEN (ev_rank) ===
$ uv run pytest tests/ev/test_ev_rank.py -x -q
5 passed in 0.01s  (test_ev_calculation/rank_S/rank_D_low_ev/rank_B_no_odds_threshold/rank_no_bet_is_D)

=== Task 2 GREEN (purchase_simulator + metrics) ===
$ uv run pytest tests/ev/test_purchase_simulator.py tests/ev/test_metrics.py -x -q
13 passed in 0.03s
  (purchase: filter_conditions/top2/tiebreak/no_eligible/no_sale/no_bet_excluded/stable_mergesort)
  (metrics: recovery_rate/refund_excluded/max_drawdown/counts/zero_division/profit_invariant)

=== Task 3 GREEN (bl3_betting) ===
$ uv run pytest tests/ev/test_bl3_betting.py -x -q
5 passed in 0.02s  (select_top2_low_odds/no_ev/caveat/odds_policy_confirmed/model_type)

=== Plan 02 全体 (GREEN 化対象4ファイル) ===
$ uv run pytest tests/ev/test_ev_rank.py tests/ev/test_purchase_simulator.py tests/ev/test_metrics.py tests/ev/test_bl3_betting.py -q
23 passed in 0.04s

=== Plan 03 スコープは RED のまま許容 (verification 仕様準拠) ===
$ uv run pytest tests/ev/ tests/model/test_orchestrator_bt.py -q
26 failed, 23 passed in 0.21s
  (test_odds_snapshot/test_refund_accounting/test_orchestrator_bt は Plan 03 で GREEN 化予定)

=== Plan 01 BT窓ヘルパ回帰確認 ===
$ uv run pytest tests/ev/test_ev_rank.py tests/ev/test_purchase_simulator.py tests/ev/test_metrics.py tests/ev/test_bl3_betting.py tests/utils/test_group_split.py -q
38 passed in 0.91s  (Plan 02 の23 + Plan 01 BT窓 helper 15・回帰なし)
```

Acceptance criteria:

- [x] `src/ev/ev_rank.py` に `def compute_ev_and_rank` と `def _rank` が含まれる
- [x] EV_lower/EV_upper の計算が `p_fukusho_hit * fuku_odds_lower/high`（§11.1 直線積）
- [x] `_rank` の閾値が §11.5 完全準拠（RANK_THRESHOLDS 定数: 1.20/0.25/1.5・1.10/0.20/1.5・1.05/0.15・1.00）
- [x] `src/ev/purchase_simulator.py` に `def select_bets` と `kind='mergesort'` が含まれる
- [x] `src/ev/purchase_simulator.py` の filter 条件が §11.4 完全準拠（1.05/0.15/1.5）
- [x] `src/ev/metrics.py` に `def compute_backtest_metrics` と `effective_stake` 分母控除ロジックが含まれる
- [x] max_drawdown の計算が race_date 昇順の累積 cummax - cumsum（kind='mergesort' 行整列）
- [x] `test_metrics_profit_invariant` で `sum(row.profit) == sum(payout)+sum(refund)-sum(stake)` が混在シナリオで成立（MEDIUM-02）
- [x] `src/ev/bl3_betting.py` に `def select_bl3_bets` と `BL3_COMPARISON_CAVEAT` import と `'confirmed'` sentinel が含まれる
- [x] BL-3 選択が `fukuoddslow` 昇順（EV でない）・p=1/odds 自己参照回避（`EV_lower` 列を付与しない）
- [x] `uv run pytest tests/ev/test_ev_rank.py tests/ev/test_purchase_simulator.py tests/ev/test_metrics.py tests/ev/test_bl3_betting.py` が全件 GREEN（23 passed）
- [x] Plan 03 スコープ（odds_snapshot/refund_accounting/orchestrator_bt）は RED のまま許容（26 failed・23 passed）

## Success Criteria

- [x] EV-01/EV-02/BACK-02 + §11.6 + D-04 BL-3 が純粋関数で実装・対応 RED stub 全 GREEN（23 tests）
- [x] §11.5 ランク閾値完全準拠（RANK_THRESHOLDS 定数）・no_bet は rank='D'
- [x] BL-3 は確定オッズ昇順（EV 自己参照回避・`EV_lower` 列なし）・§14.2 caveat 付与（`BL3_BETTING_CAVEAT`）
- [x] 決定論的タイブレーク（`kind='mergesort'`）を `inspect.getsource` で機械検証
- [x] 行 profit / 集計 profit 不変量を混在シナリオで検証（MEDIUM-02/T-05-05b）

## Commits

| Hash | Type | Message |
|------|------|---------|
| 4b9ce1c | test(RED) | add test_rank_no_bet_is_D for no_bet→D rank (RED) |
| a2d630c | feat(GREEN) | implement compute_ev_and_rank pure function (GREEN) |
| 739a8c5 | test(RED) | add no_bet/zero_division/profit_invariant RED tests (RED) |
| 73fc2b3 | feat(GREEN) | implement select_bets + compute_backtest_metrics (GREEN) |
| 1daebc0 | test(RED) | add bl3 odds_policy_confirmed + model_type RED tests (RED) |
| d552302 | feat(GREEN) | implement select_bl3_bets confirmed-odds baseline (GREEN) |

## Self-Check: PASSED

### Created files exist

- FOUND: src/ev/__init__.py
- FOUND: src/ev/ev_rank.py
- FOUND: src/ev/purchase_simulator.py
- FOUND: src/ev/metrics.py
- FOUND: src/ev/bl3_betting.py

### Commits exist

- FOUND: 4b9ce1c (test(05-02): add test_rank_no_bet_is_D for no_bet→D rank (RED))
- FOUND: a2d630c (feat(05-02): implement compute_ev_and_rank pure function (GREEN))
- FOUND: 739a8c5 (test(05-02): add no_bet/zero_division/profit_invariant RED tests (RED))
- FOUND: 73fc2b3 (feat(05-02): implement select_bets + compute_backtest_metrics (GREEN))
- FOUND: 1daebc0 (test(05-02): add bl3 odds_policy_confirmed + model_type RED tests (RED))
- FOUND: d552302 (feat(05-02): implement select_bl3_bets confirmed-odds baseline (GREEN))

### TDD gate commits exist (per task)

- Task 1: FOUND `test(...)` (4b9ce1f RED) → `feat(...)` (a2d630c GREEN)
- Task 2: FOUND `test(...)` (739a8c5 RED) → `feat(...)` (73fc2b3 GREEN)
- Task 3: FOUND `test(...)` (1daebc0 RED) → `feat(...)` (d552302 GREEN)
