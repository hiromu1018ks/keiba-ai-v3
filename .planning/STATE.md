---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-06-18T22:20:58.195Z"
last_activity: 2026-06-18 -- Phase 03 planning complete
progress:
  total_phases: 8
  completed_phases: 2
  total_plans: 8
  completed_plans: 8
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能なバックテストで定量評価できること。リーク防止と再現性だけは必ず守る。
**Current focus:** Phase 02 — fukusho-labels

## Current Position

Phase: 3
Plan: Not started
Status: Ready to execute
Last activity: 2026-06-18 -- Phase 03 planning complete

Progress: [░░░░░░░░░░] 0%

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2 research flag: `sales_start_entry_count` restoration logic and payout-table schema cannot be specified without inspecting actual EveryDB2/JRA-VAN columns — likely needs `/gsd-plan-phase --research-phase 2`
- Phase 3 research flag: `available_from_timing` mapping depends on exact JRA-VAN data-availability timings — likely needs `/gsd-plan-phase --research-phase 3`
- Phase 5 sub-spike: odds-snapshot timing granularity in EveryDB2 gates the candidate `odds_snapshot_policy` set

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-18T13:27:58.303Z
Stopped at: Phase 3 context gathered
Resume file: .planning/phases/03-as-of-features-snapshots/03-CONTEXT.md
