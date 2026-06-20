---
phase: 05-ev-backtest
plan: 03
subsystem: ev-backtest
tags: [ev, odds-snapshot, refund-accounting, jodds, merge-asof, backward, leak-prevention, wave-2, high-1, high-3, cycle-2]
status: complete
requires:
  - src/model/baseline.py::fetch_market_data (readonly_cur + parameterized query analog・変更なし)
  - src/etl/fukusho_label.py (label フラグ READ のみ・変更なし)
  - tests/ev/conftest.py (Plan 01 合成 fixtures・make_harai_mock/make_label_mock)
provides:
  - src/ev/odds_snapshot.py::fetch_jodds(readonly_cur, *, year=None)
  - src/ev/odds_snapshot.py::select_odds_snapshot(jodds_df, race_times, policy)
  - src/ev/odds_snapshot.py::ODDS_SNAPSHOT_POLICIES / ODDS_SOURCE_TYPE_JODDS
  - src/ev/refund_accounting.py::determine_stake_payout(row, *, stake_per_bet=100)
  - src/ev/refund_accounting.py::_lookup_payfukusyo_pay(row)
affects:
  - src/ev/ev_rank.py (本 plan の select_odds_snapshot 戻り値 fuku_odds_lower/upper を消費・snake_case contract・Plan 02 既存)
  - src/ev/purchase_simulator.py (同上・fuku_odds_lower 列を filter 条件に使用・Plan 02 既存)
  - scripts/run_backtest.py (Plan 05-05 で新設・compute_ev_and_rank → select_odds_snapshot → refund_accounting pipeline)
tech-stack:
  added: []
  patterns:
    - merge_asof(direction='backward', by=['race_key','umaban']) 馬単位 PIT-join (HIGH-1・D-02・T-05-06/06b mitigate)
    - parameterized query (%s placeholder・readonly_cur・baseline.py fetch_market_data analog・T-05-SC mitigate)
    - n_jodds_tanpuku JOIN n_jodds_tanpukuwaku_head ON 7カラム PK + datakubun='1' filter (D-01 Pitfall 2・T-05-07 mitigate)
    - HIGH-3 canonical: 0999/----/****/0000/sp 全て no_bet sentinel (CONTEXT D-02 正・RESEARCH 行89 廃棄・T-05-07b mitigate)
    - cross-plan snake_case contract (fuku_odds_lower/upper・T-05-SC2 mitigate)
    - race_start_datetime + pd.Timedelta cutoff (Pitfall 1 日跨ぎ回避)
    - label フラグ一次・HARAI cross-check (Pitfall A6・HenkanUma 直接解析しない)
    - 特払 HARAI slot semantics (TokubaraiFlag2='1' + PayFukusyoUmaban='00' + PayFukusyoPay=特払金額・的中フラグ非依存・T-05-23 mitigate)
key-files:
  created:
    - src/ev/odds_snapshot.py
    - src/ev/refund_accounting.py
  modified:
    - tests/ev/test_odds_snapshot.py (cycle-2 テスト追加 + stub テストの HIGH-3 canonical/snake_case/fukusyoflag 整合修正)
    - tests/ev/test_refund_accounting.py (test_refund_tokubarai_harai_fixture 追加)
decisions:
  - "05-03: HIGH-3 canonical rule — CONTEXT D-02 を正とし 0999=no_bet sentinel（RESEARCH 行89 の「99.9倍以上」記述は本モジュールで廃棄・T-05-07b mitigate）"
  - "05-03: cross-plan contract — select_odds_snapshot 戻り値は snake_case fuku_odds_lower/fuku_odds_upper（JODDS raw FukuOddsLow/FukuOddsHigh を rename）・Plan 02 ev_rank.py と Plan 05 run_backtest.py が JOIN するだけで column 再名不要（T-05-SC2 mitigate）"
  - "05-03: merge_asof by=['race_key','umaban'] — HIGH-1 馬単位 odds 保証（race_key 単独では同一レース別馬 odds で上書きされる silent leak を構造的排除・T-05-06b mitigate）"
  - "05-03: cutoff 計算は race_start_datetime + pd.Timedelta(minutes=N)（HHMM 整数比較は日跨ぎで破綻・Pitfall 1 回避）"
  - "05-03: 特払（TokubaraiFlag2='1'）は PayFukusyoUmaban='00'(的中馬番なし) でも PayFukusyoPay>0 を payout に計上（§2.4・的中フラグ非依存・HARAI PayFukusyoPay 一次・T-05-23 mitigate）"
  - "05-03: test_odds_snapshot_special_values の期待値を HIGH-3 canonical（0999=no_bet）に合わせて修正 — cycle-2 test_odds_snapshot_0999_is_no_bet と整合（Rule 1 auto-fix）"
metrics:
  duration: 7m
  completed: 2026-06-20T23:33:27Z
  task_count: 2
  file_count: 4
---

# Phase 5 Plan 03: JODDS 時点選択 + 返還/中止 honest 会計 Summary

JODDS 固定時点オッズ選択（D-01/D-02・BACK-04）と返還/中止 honest 会計決定表（D-05・BACK-03）を TDD RED→GREEN で実装し・Plan 01 Wave 0 RED stub のうち2ファイル（test_odds_snapshot/test_refund_accounting）を GREEN 化。HIGH-1 馬単位 odds 保証（`merge_asof by=['race_key','umaban']`）・HIGH-3 canonical rule（0999=no_bet sentinel）・cycle-2 テスト（multi-race sort・特払 HARAI fixture）全 GREEN・リーク防止と honest 会計の構造的ブロックを確立。

## What Was Built

### Task 1: JODDS 固定時点オッズ選択（odds_snapshot.py）— RED→GREEN

**RED (0b01438):** `test_odds_snapshot.py` に cycle-2 テスト5件を追加（multi_race/0999/datakubun/snake_case/fukusyoflag）+ stub テストの HIGH-3 canonical 整合修正。11テスト全て ModuleNotFoundError で RED。

**GREEN (aa09807):** `src/ev/odds_snapshot.py` を新設:

- `fetch_jodds(readonly_cur, *, year=None) -> pd.DataFrame`: `public.n_jodds_tanpuku` JOIN `n_jodds_tanpukuwaku_head` ON 7カラム PK（Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum, HappyoTime）・`datakubun='1'`(中間) で filter（D-01・Pitfall 2・T-05-07）。parameterized query（`%s` placeholder・baseline.py::fetch_market_data analog・T-05-SC）。戻り値は race_key + happyo_datetime 構築済み（JODDS PK は race_key 7 + Umaban + HappyoTime = 9カラム・RESEARCH §1.1 実証）。
- `select_odds_snapshot(jodds_df, race_times, policy) -> df`: `merge_asof(direction='backward', by=['race_key','umaban'])` で馬単位の cutoff 以下最大 snapshot を選択（HIGH-1・D-02 未来リーク構造的不可・T-05-06/06b）。cutoff は `race_start_datetime - pd.Timedelta(minutes=N)`（Pitfall 1 日跨ぎ回避）。
- HIGH-3 canonical rule: `0999`/`----`/`****`/`0000`/` `(sp) は全て no_bet sentinel（CONTEXT D-02 正・RESEARCH 行89 廃棄・T-05-07b）。`FukusuoFlag` が `0`/`1`/`3` も no_bet（`7`=発売ありのみ正常・MEDIUM positive test）。
- cross-plan contract: 戻り値 odds 列は snake_case `fuku_odds_lower`/`fuku_odds_upper`（JODDS raw `FukuOddsLow`/`FukuOddsHigh` を rename）・`odds_missing_reason`（`no_bet_empty`/`no_bet`/NaN）・`odds_snapshot_at`・`odds_source_type='jodds_tanpuku'` 保持。

### Task 2: 返還/中止 honest 会計決定表（refund_accounting.py）— RED→GREEN

**RED (4659e18):** `test_refund_accounting.py` に `test_refund_tokubarai_harai_fixture` を追加（HARAI 実スキーマ形状の特払 fixture・MEDIUM-D cycle-2）。ModuleNotFoundError で RED。

**GREEN (b12d053):** `src/ev/refund_accounting.py` を新設:

- `determine_stake_payout(row, *, stake_per_bet=100) -> dict`: RESEARCH §2.2/§2.3 決定表を実装。label フラグ一次・HARAI cross-check（Pitfall A6・HenkanUma 直接解析しない）。
  - 複勝発売なし → `stake=0`（選択対象外・事前 filter）
  - 取消/除外/不成立/レース中止 → `effective_stake=0` / `refund=100`（§11.6・T-05-09）
  - 競走中止（`is_dead_loss`）→ `effective_stake=100` / `profit=-100`（§10.6 除外禁止・Pitfall 4・T-05-08・実運用の負けを消さない）
  - 特払（`TokubaraiFlag2='1'`）→ `payout=PayFukusyoPay slot1`（§2.4・T-05-23・的中フラグ非依存・HARAI 一次）
  - 通常 → `payout=_lookup_payfukusyo_pay(row)`
- `_lookup_payfukusyo_pay(row) -> int`: `row.umaban` を `PayFukusyoUmaban1..5` slot と照合・該当 slot の `PayFukusyoPay1..5` を返す（同着 slot 2-5 使用可・`range(1,6)`・該当なしは 0）。

## TDD Gate Compliance

各タスクは `type="auto" tdd="true"` で RED → GREEN の2コミット構成:

| Task | RED gate | GREEN gate |
|------|----------|------------|
| Task 1 (odds_snapshot) | `test(05-03): add cycle-2 odds_snapshot RED tests (multi-race/0999/snake_case/datakubun/fukusyoflag)` (0b01438) | `feat(05-03): implement JODDS odds_snapshot selection (GREEN)` (aa09807) |
| Task 2 (refund_accounting) | `test(05-03): add tokubarai HARAI fixture RED test (cycle-2 MEDIUM-D)` (4659e18) | `feat(05-03): implement refund/dead-loss honest accounting (GREEN)` (b12d053) |

各タスクで `test(...)` commit (RED) の後に `feat(...)` commit (GREEN) が存在・gate sequence 満たす。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug fix] `test_odds_snapshot_special_values` 期待値の HIGH-3 canonical 整合修正**

- **Found during:** Task 1 RED テスト拡張時
- **Issue:** Plan 01 の RED stub `test_odds_snapshot_special_values` の docstring に「`0999` は odds として使用可能」とあったが・Plan 05-03 の must_haves で HIGH-3 canonical rule（CONTEXT D-02 正・0999=no_bet sentinel）が正として決定されたため矛盾。
- **Fix:** stub テストの期待値を HIGH-3 canonical（0999=no_bet）に合わせて修正。4 snapshot(`----`/`****`/`0000`/`0999`) 全てが cutoff 前に存在する場合・直近(09:28)の `0999` が選択されるが no_bet sentinel 化され `fuku_odds_lower=NaN`/`odds_missing_reason='no_bet'` となるよう assert を更新。cycle-2 の `test_odds_snapshot_0999_is_no_bet` と整合。
- **Files modified:** `tests/ev/test_odds_snapshot.py`
- **Commit:** 0b01438（Task 1 RED コミットに統合）

**2. [Rule 1 - Bug fix] `test_odds_snapshot_day_boundary` の race_key 不整合修正**

- **Found during:** Task 1 GREEN 実行時
- **Issue:** `_make_race_times("2024-01-04 00:30:00")` は `_make_race_times` の既定 race_key(`2024-0103-05-1-06-1`)を使うが・テスト本体の jodds は `2024-0104-05-1-06-1` を使っており race_key 不一致で merge_asof がマッチせず `happyotime=None` になる silent failure。
- **Fix:** テスト側で race_key=`2024-0104-05-1-06-1` の race_times を直接構築（`_make_race_times` helper を使わず）し・jodds と race_key を一致させた。
- **Files modified:** `tests/ev/test_odds_snapshot.py`
- **Commit:** aa09807（Task 1 GREEN コミットに統合）

## Threat Mitigation Verification

| Threat ID | Category | Mitigation | Verification |
|-----------|----------|------------|--------------|
| T-05-06 | Information Disclosure | `merge_asof(direction='backward')` で未来 snapshot 構造的不可（D-02） | `test_odds_snapshot_future_leak`（09:25/10:30 → 09:25 選択・10:30 は未来で除外）(0b01438 RED / aa09807 GREEN) |
| T-05-06b | Information Disclosure | `by=['race_key','umaban']` で per-horse as-of join（HIGH-1） | `test_odds_snapshot_multi_horse`（3頭の行数と odds 保存）+ `test_odds_snapshot_multi_race`（複数レース + 重複 happyo_datetime で 5行・各馬 odds 保持）(0b01438 RED / aa09807 GREEN) |
| T-05-07 | Tampering | head テーブル JOIN + `datakubun='1'` filter（D-01・確定 '4' 混入防止） | `test_odds_snapshot_datakubun_filter`（同時刻の中間 '1'(low=0011) と確定 '4'(low=9999) → 0011 選択）(0b01438 RED / aa09807 GREEN) |
| T-05-07b | Tampering | 0999=no_bet sentinel canonical（CONTEXT D-02 正・RESEARCH 行89 廃棄） | `test_odds_snapshot_0999_is_no_bet`（0999 → fuku_odds_lower=NaN/odds_missing_reason='no_bet'）+ `test_odds_snapshot_special_values`（4特殊値全て no_bet）(0b01438 RED / aa09807 GREEN) |
| T-05-08 | Tampering | `is_dead_loss` 馬を `effective_stake=100`/`profit=-100` で計上（§10.6 除外禁止） | `test_refund_dead_loss`（effective_stake=100, profit=-100, refund=0）(4659e18 RED / b12d053 GREEN) |
| T-05-09 | Tampering | 返還馬（取消/除外/不成立/レース中止）は `effective_stake=0` | `test_refund_scratch_cancel`/`race_excluded`/`fuseiritu`/`race_cancelled`（全て effective_stake=0, refund=100）(Plan 01 stub / b12d053 GREEN) |
| T-05-10 | Information Disclosure | snapshot 0件・特殊値は no_bet sentinel（silent fallback 禁止） | `test_odds_snapshot_no_bet_empty`（0件 → no_bet_empty sentinel）+ `test_odds_snapshot_special_values`（4特殊値 → no_bet）(0b01438 RED / aa09807 GREEN) |
| T-05-10b | Tampering | `FukusuoFlag='7'`(正常発売) を odds 返却正例とする（MEDIUM positive） | `test_odds_snapshot_fukusyoflag_normal_sale`（'7' → odds 返却・'0' → no_bet）(0b01438 RED / aa09807 GREEN) |
| T-05-22 | Information Disclosure | 複数レース + 重複 happyo_datetime で `merge_asof(by=['race_key','umaban'])` 正常動作（MEDIUM-C cycle-2） | `test_odds_snapshot_multi_race`（R1×3 + R2×2 = 5行・各馬 odds 保持・sort 違反なし）(0b01438 RED / aa09807 GREEN) |
| T-05-23 | Tampering | 特払（TokubaraiFlag2='1'）HARAI slot semantics（的中馬番なし PayFukusyoPay 計上・MEDIUM-D cycle-2） | `test_refund_tokubarai_harai_fixture`（PayFukusyoUmaban='00' + PayFukusyoPay=70 → payout=70, profit=-30, effective_stake=100）(4659e18 RED / b12d053 GREEN) |
| T-05-SC | Tampering | parameterized query（`%s` placeholder）で SQL injection 対策 | `fetch_jodds` の query 構成（`where_clauses`/`params`・baseline.py::fetch_market_data analog）(aa09807) |
| T-05-SC2 | Tampering | cross-plan odds カラム名 snake_case 統一（fuku_odds_lower/upper） | `test_odds_snapshot_returns_snake_case`（snake_case 含む・raw FukuOddsLow/High 含まない）(0b01438 RED / aa09807 GREEN) |

## Verification

全 acceptance criteria 検証済み:

```
=== Task 1 GREEN (odds_snapshot) ===
$ uv run pytest tests/ev/test_odds_snapshot.py -x -q
11 passed in 0.06s
  (backward/no_bet_empty/special_values/0999_is_no_bet/future_leak/day_boundary/
   datakubun_filter/returns_snake_case/multi_horse/fukusyoflag_normal_sale/multi_race)

=== Task 2 GREEN (refund_accounting) ===
$ uv run pytest tests/ev/test_refund_accounting.py -x -q
19 passed in 0.04s
  (9シナリオ parametrize + normal_hit/normal_miss/scratch_cancel/race_excluded/
   dead_loss/fuseiritu/race_cancelled/no_sale/deadheat/tokubarai_harai_fixture)

=== Plan 05-03 全体 ===
$ uv run pytest tests/ev/test_odds_snapshot.py tests/ev/test_refund_accounting.py -q
30 passed in 0.09s

=== tests/ev/ 全体（Plan 02 + Plan 03 統合）===
$ uv run pytest tests/ev/ -q
53 passed in 0.12s  (Plan 02 の23 + Plan 03 の30)

=== 回帰 (Plan 01 BT窓 helper + tests/ev + orchestrator_bt) ===
$ uv run pytest tests/utils/test_group_split.py tests/ev/ tests/model/test_orchestrator_bt.py -q
2 failed, 68 passed in 1.19s
  (orchestrator_bt の2件は Plan 05 後続 plan (05-04/05) スコープで RED のまま許容・
   Plan 02 SUMMARY と同一方針・split_3way periods 拡張未実装のため)
```

Acceptance criteria:

- [x] `src/ev/odds_snapshot.py` に `def select_odds_snapshot` と `direction="backward"` と `def fetch_jodds` が含まれる
- [x] `select_odds_snapshot` の merge_asof 呼出しで `by=` に umaban が含まれる（HIGH-1: `by=["race_key", "umaban"]`）
- [x] `fetch_jodds` の戻り値に Umaban 列が含まれる（SELECT 列リストに `j.umaban`）
- [x] `select_odds_snapshot` 戻り値の odds 列が snake_case `fuku_odds_lower`/`fuku_odds_upper`（raw `FukuOddsLow`/`FukuOddsHigh` を rename）
- [x] `fetch_jodds` が `n_jodds_tanpukuwaku_head` と JOIN して `datakubun='1'` で filter（Pitfall 2）
- [x] `select_odds_snapshot` が `race_start_datetime + pd.Timedelta` で cutoff 計算（HHMM 整数比較なし・Pitfall 1）
- [x] 特殊値 `----`/`****`/`0000`/`0999` が全て no_bet（HIGH-3 canonical）
- [x] `test_odds_snapshot_multi_horse` が3頭の異なる odds を入力し3行で返す（HIGH-1: 行数==入力馬数・各 umaban の odds 保存）
- [x] `test_odds_snapshot_fukusyoflag_normal_sale` が FukusuoFlag='7' で odds を返す（MEDIUM 正常発売 positive test）
- [x] 未来 snapshot が選択されない（`test_odds_snapshot_future_leak`・merge_asof backward）
- [x] `test_odds_snapshot_multi_race` が GREEN（MEDIUM-C cycle-2: 複数レース + 重複 happyo_datetime で sort 違反なく各馬に正しい per-horse snapshot・行数==入力候補馬数）
- [x] `uv run pytest tests/ev/test_odds_snapshot.py` が全件 GREEN（11 passed）
- [x] `src/ev/refund_accounting.py` に `def determine_stake_payout` と `def _lookup_payfukusyo_pay` が含まれる
- [x] `is_dead_loss` のケースが `effective_stake=100, profit=-100`（§10.6 除外禁止）
- [x] 取消/除外/不成立/レース中止のケースが `effective_stake=0, refund=100`
- [x] `_lookup_payfukusyo_pay` が `PayFukusyoUmaban1..5` slot → `PayFukusyoPay1..5` の lookup（同着 slot 2-5 含む・`range(1,6)`）
- [x] `test_refund_tokubarai_harai_fixture` が GREEN（MEDIUM-D cycle-2: HARAI 実スキーマ形状の特払 fixture で `PayFukusyoPay=70` を payout に計上・`fukusho_hit_validated=0` でも `PayFukusyoPay>0` で payout>0 の契約）
- [x] `uv run pytest tests/ev/test_refund_accounting.py` が全件 GREEN（19 passed）

## Success Criteria

- [x] BACK-04 odds 時点固定・未来リーク構造的不可（`merge_asof direction='backward'`）・特殊値/0件 no_bet sentinel
- [x] HIGH-1 馬単位オッズ保証: `merge_asof by=['race_key','umaban']` で各馬に固有 odds を割当（`test_odds_snapshot_multi_horse` 3頭行数・odds 保存 GREEN・`test_odds_snapshot_multi_race` 5行 GREEN）
- [x] HIGH-3 0999 canonical rule: `0999=no_bet` sentinel（CONTEXT D-02 正・RESEARCH 行89 廃棄・`test_odds_snapshot_0999_is_no_bet` GREEN）
- [x] BACK-03 返還会計決定表（6シナリオ + 特払）対抗的テスト全 GREEN・label 一次/HARAI cross-check
- [x] §10.6（競走中止除外禁止）+ §11.6（effective_stake 分母控除）履行
- [x] MEDIUM: FukusyoFlag='7' 正常発売 positive test GREEN（`test_odds_snapshot_fukusyoflag_normal_sale`）
- [x] MEDIUM-C cycle-2: 複数レース + 重複 happyo_datetime で merge_asof 正常動作（`test_odds_snapshot_multi_race` GREEN）
- [x] MEDIUM-D cycle-2: 特払 HARAI fixture で PayFukusyoPay=70 を payout 計上（`test_refund_tokubarai_harai_fixture` GREEN）

## Commits

| Hash | Type | Message |
|------|------|---------|
| 0b01438 | test(RED) | add cycle-2 odds_snapshot RED tests (multi-race/0999/snake_case/datakubun/fukusyoflag) |
| aa09807 | feat(GREEN) | implement JODDS odds_snapshot selection (GREEN) |
| 4659e18 | test(RED) | add tokubarai HARAI fixture RED test (cycle-2 MEDIUM-D) |
| b12d053 | feat(GREEN) | implement refund/dead-loss honest accounting (GREEN) |

## Self-Check: PASSED

### Created files exist

- FOUND: src/ev/odds_snapshot.py
- FOUND: src/ev/refund_accounting.py

### Modified files exist

- FOUND: tests/ev/test_odds_snapshot.py
- FOUND: tests/ev/test_refund_accounting.py

### Commits exist

- FOUND: 0b01438 (test(05-03): add cycle-2 odds_snapshot RED tests)
- FOUND: aa09807 (feat(05-03): implement JODDS odds_snapshot selection (GREEN))
- FOUND: 4659e18 (test(05-03): add tokubarai HARAI fixture RED test)
- FOUND: b12d053 (feat(05-03): implement refund/dead-loss honest accounting (GREEN))

### TDD gate commits exist (per task)

- Task 1: FOUND `test(...)` (0b01438 RED) → `feat(...)` (aa09807 GREEN)
- Task 2: FOUND `test(...)` (4659e18 RED) → `feat(...)` (b12d053 GREEN)
