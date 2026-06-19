---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Plan 03-05 complete (gap-closure: CR-01/02/03/04 + WR-01・全 features テスト GREEN・live-DB snapshot rebuild で parity 実証)
last_updated: "2026-06-19T04:45:00.000Z"
last_activity: 2026-06-19 -- Phase 03 gap-closure 03-05 complete
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 13
  completed_plans: 13
  percent: 24
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能なバックテストで定量評価できること。リーク防止と再現性だけは必ず守る。
**Current focus:** Phase 03 — as-of-features-snapshots (gap-closure 完了・Phase 3 verification 再判定待ち)

## Current Position

Phase: 03 (as-of-features-snapshots) — gap-closure 03-05 COMPLETE (Phase 3 verification 再判定待ち)
Plan: 5 of 5 (Phase 3 全 plan 完了)
Status: Phase 03 gap-closure 完了・verification で must-have #1 PARTIAL→VERIFIED 判定待ち
Last activity: 2026-06-19 -- 03-05 gap-closure (CR-01/02/03/04 + WR-01) 完了

Progress: [████░░░░░░░] 24%

## Performance Metrics

**Velocity:**

- Total plans completed: 8
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 4 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: — (no execution yet)

*Updated after each plan completion*
| Phase 01 P01 | 64 | 4 tasks | 19 files |
| Phase 01 P02 | 28 | 2 tasks | 5 files |
| Phase 01 P04 | 18m | 2 tasks | 10 files |
| Phase 01 P03 | 136 | 3 tasks | 9 files |
| Phase 02 P01 | 10 | 3 tasks | 5 files |
| Phase 02 P02 | 6 | 2 tasks | 1 files |
| Phase 02 P03 | 12m | 2 tasks | 4 files |
| Phase 02 P04 | 36 | 3 tasks | 3 files |
| Phase 03 P01 | 7m | 2 tasks | 12 files |
| Phase 03 P02 | 12m | 2 tasks | 3 files |
| Phase 03 P03 | 13m | 3 tasks | 4 files |
| Phase 03 P04 | 25m | 4 tasks | 8 files |
| Phase 03 P05 | 45m | 3 tasks | 14 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Strict DAG-driven phase order — no model work (Phase 4) before labels (Phase 2) and as-of features (Phase 3) are locked and gated
- Roadmap: Phase 2 (Labels) is the long pole with a hard >99.9% payout-table reconciliation gate; Phase 8 is a dedicated adversarial-audit acceptance gate consolidating TEST-01
- Roadmap: Snapshots/reproducibility-stamping folded into Phase 3 (as-of builder writes immutable Parquet) rather than a standalone phase
- [Phase ?]: plan 01-01: hatchling ビルドバックエンド採用（uv_build は src/config,src/db を扱えないため）
- [Phase ?]: plan 01-02: Hybrid Quality Gate 実装（BLOCK/INFO 分離・HIGH#7 mojibake + code-anomaly・HIGH#8 fail-by-default）
- [Phase ?]: sklearn 1.9.0 で cv='prefit' 文字列削除のため FrozenEstimator 公式 prefit イディオムに適合（01-04・リーク防止セマンティクス不変）
- [Phase ?]: group_split は strict max(train)<min(test) で等値タイムスタンプ跨ぎ禁止（01-04 HIGH #2）
- [Phase 01]: plan 01-03: normalized ETL を staging-table-swap で idempotent 化（HIGH #5・§19.1 再現性）
- [Phase 01]: plan 01-03: ETL ロールに normalized CREATE 権限を付与（HIGH #5/#6 のため・01-01 GRANT_ETL_SQL を USAGE+CREATE に拡張）
- [Phase 01]: plan 01-03: reader ロールにも normalized SELECT を付与（テストの readonly_cur 検証用・01-01 GRANT_READER_SQL を拡張）
- [Phase 01]: plan 01-03: 要件 §6.1（2015年以降）を ETL 側で機械適用（_JRA_FILTER に year::int >= 2015 を追加・Rule 2）
- [Phase 02]: [Phase 02] plan 02-01: label_spec.yaml でラベル定義を Git 管理化（D-07・label_generation_version='v1.0.0'・marker canonicalization sentinel・source_confidence 分離）
- [Phase 02]: [Phase 02] plan 02-01: GRANT_READER_SQL は明示的 reader ロール（keiba_readonly）のみ付与・TO PUBLIC 一切不使用（HIGH #3）
- [Phase ?]: RED テスト collection 保証のため module-level import を遅延 import 化（Plan 02-02）
- [Phase ?]: Phase 2 Plan 03 GREEN: fukusho_label ETL 実装完了・27 unit tests GREEN・REVIEWS HIGH #1/#3/#4/#5/#6 + NEW HIGH #2/#3 解決・Task 3 実DB実行は checkpoint:human-verify で停止
- [Phase ?]: 02-04: LABEL-03 gate PASSES live (100% agreement, 6 BLOCK checks green). Drift BLOCK->INFO per Rule 1 (drift is D-04-legitimate, label correctness via precision/recall BLOCK)
- [Phase ?]: 03-01: rolling 8 systems x 3 axes (24) + static 15 + running_style 1 = 40 features; source_role taxonomy [HIGH #4]; strict < cutoff unified [HIGH #2]
- [Phase 03]: plan 03-02: label.fukusho_label.race_date 全 554267 行 backfill 済 (Phase 2 負債解消)・INSERT/SELECT positional mismatch を Rule 1 で auto-fix・staging-swap idempotent (2回実行同一 checksum) + raw 不変性 PASS
- [Phase 03]: plan 03-03: rolling.py は per-observation latest-K algorithm (obs_id=(race_nkey,kettonum) group・pit_join_backward 不使用) で CYCLE-2 HIGH #1 cross-obs leak を閉鎖・running_style は dict-list + 純粋閾値関数 (テスト契約優先)・builder は COPY-NOT-RENAME (HIGH #5) + HIGH #3 出力カラム全登録検査・39/39 GREEN (10 RED は 03-04 スコープ)
- [Phase 03]: race_nkey は DB カラムでなく予約済み canonical key — make_race_nkey(year,jyocd,kaiji,nichiji,racenum) で pandas 構築 (BUG A fix)
- [Phase 03]: normalized 層に babacd/timediff/datakubun は存在しない — 当該 rolling 系統は D-13 sentinel で fallback
- [Phase 03]: COPY-NOT-RENAME raw ID 原列は _RAW_ID_KEPT_COLUMNS で明示許可 (HIGH #5・banned source は防御的 assert で排除)
- [Phase 03]: plan 03-05 (gap-closure): CR-01 は REVIEW option (c) 採用 — rolling timediff/babacd 6エントリ削除 + Deferred note で Phase 3.1 で再登録（source カラムが normalized 層に揃った段階）
- [Phase 03]: plan 03-05: estimated_running_style は rolling と同一 PIT pre-filter (strict < cutoff) を groupby 前に適用 (WR-01・registry 宣言と一致・obs_id 構築不要・kettonum 単位 per-horse style)
- [Phase 03]: plan 03-05: category_map artifact は JSON (sort_keys=True・byte-reproducible・human-auditable) で永続化 (CR-04・pickle ACE vector 完全解消・joblib 廃止)
- [Phase 03]: plan 03-05: CR-04 regression guard は AST 解析で Import/ImportFrom/Attribute を検査 (docstring の「joblib 廃止」説明は許容・実コード依存のみを検出)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2 research flag: `sales_start_entry_count` restoration logic and payout-table schema cannot be specified without inspecting actual EveryDB2/JRA-VAN columns — likely needs `/gsd-plan-phase --research-phase 2`
- Phase 3 research flag: `available_from_timing` mapping depends on exact JRA-VAN data-availability timings — likely needs `/gsd-plan-phase --research-phase 3`
- Phase 5 sub-spike: odds-snapshot timing granularity in EveryDB2 gates the candidate `odds_snapshot_policy` set

### Roadmap Evolution

- Phase 3.1 (Timediff/Babacd Rolling Restoration) inserted after Phase 3 (URGENT): Phase 2 ETL source extension (timediff/babacd → normalized.n_uma_race) + Phase 3 rolling re-registration of the 6 features deleted in gap-closure 03-05 (CR-01). Planned via /gsd-plan-phase 03.1 after Phase 3 gap-closure (03-05) completes.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-19T04:45:00.000Z
Stopped at: Plan 03-05 complete (gap-closure: CR-01/02/03/04 + WR-01・全 features テスト GREEN・live-DB snapshot rebuild で parity 実証)
Resume file: Phase 3 verification 再判定 (must-have #1 PARTIAL→VERIFIED) → Phase 4 (model) 計画 or Phase 3.1 (Timediff/Babacd Restoration) 計画
