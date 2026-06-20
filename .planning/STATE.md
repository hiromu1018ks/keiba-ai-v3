---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 05
current_phase_name: ev-backtest
status: executing
stopped_at: Completed 05-02-PLAN.md
last_updated: "2026-06-20T23:28:04.073Z"
last_activity: 2026-06-20
last_activity_desc: Completed 05-01-PLAN.md
progress:
  total_phases: 9
  completed_phases: 5
  total_plans: 29
  completed_plans: 25
  percent: 56
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能なバックテストで定量評価できること。リーク防止と再現性だけは必ず守る。
**Current focus:** Phase 05 — ev-backtest

## Current Position

Phase: 05 (ev-backtest) — EXECUTING
Plan: 3 of 6
Status: Plan 05-01 complete (BT窓ヘルパ + Wave 0 RED stub)
Last activity: 2026-06-20 — Completed 05-01-PLAN.md

Progress: [████████░░] 83%

## Performance Metrics

**Velocity:**

- Total plans completed: 23
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 4 | - | - |
| 03 | 5 | - | - |
| 03.1 | 4 | - | - |
| 04 | 6 | - | - |

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
| Phase 03.1 P01 | 15m | 2 tasks | 1 files |
| Phase 03.1 P02 | 8m | 2 tasks | 2 files |
| Phase 03.1 P03 | 約30分 | 4 tasks | 7 files |
| Phase 03.1 P04 | 約20分 | 1 task | 3 files (snapshots) |
| Phase 04 P01 | 12m | 3 tasks | 15 files |
| Phase 04 P02 | 13m | 2 tasks | 6 files |
| Phase 04 P03 | 34m | 2 tasks | 4 files |
| Phase 04 P04 | 38m | 3 tasks | 5 files |
| Phase 04 P05 | 49m | 2 tasks | 7 files |
| Phase 04 P06 | 18m | 2 tasks | 5 files |
| Phase 05 P01 | 10m | 2 tasks | 13 files |
| Phase 05 P02 | 5m | - tasks | - files |
| Phase 05 P02 | 5m | 3 tasks | 9 files |

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
- [Phase 03.1]: plan 03.1-01: timediff/baba3 を normalized ETL へ raw varchar pass-through で取り込み（D-01/D-03）・parse/派生は後続 Plan 03 builder 側
- [Phase 03.1]: plan 03.1-01: staging-swap を LIKE から DDL 駆動に変更（_TABLE_DDL_COLUMNS）・新カラム追加が即時本番スキーマへ反映（Rule 3 blocking fix）
- [Phase 03]: COPY-NOT-RENAME raw ID 原列は _RAW_ID_KEPT_COLUMNS で明示許可 (HIGH #5・banned source は防御的 assert で排除)
- [Phase 03]: plan 03-05 (gap-closure): CR-01 は REVIEW option (c) 採用 — rolling timediff/babacd 6エントリ削除 + Deferred note で Phase 3.1 で再登録（source カラムが normalized 層に揃った段階）
- [Phase 03]: plan 03-05: estimated_running_style は rolling と同一 PIT pre-filter (strict < cutoff) を groupby 前に適用 (WR-01・registry 宣言と一致・obs_id 構築不要・kettonum 単位 per-horse style)
- [Phase 03]: plan 03-05: category_map artifact は JSON (sort_keys=True・byte-reproducible・human-auditable) で永続化 (CR-04・pickle ACE vector 完全解消・joblib 廃止)
- [Phase 03]: plan 03-05: CR-04 regression guard は AST 解析で Import/ImportFrom/Attribute を検査 (docstring の「joblib 廃止」説明は許容・実コード依存のみを検出)
- [Phase 03.1]: [Phase 03.1] plan 03.1-02: persist-exists-manifest 順序化（CR-01新・partial-failure 抑止）・AST テストで行順序機械保証
- [Phase ?]: Phase 03.1-03: timediff/babacd rolling 復元完了（rolling 18→24 features・3者 parity・WR-01'/WR-02/WR-03 advisory hardening 3件）
- [Phase 03.1]: plan 03.1-04: live-DB で normalized ETL 再実行 + snapshot rebuild を実証（当初 snapshot-id=中間版・feature_count=63・SHA256=42865b9a…321516 byte-repro・registry parity PASS・raw 不変）・Phase 4 入力は D-01 で `20260620-1a-postreview-v2`（feature_count=62・fa_version 0.3.0・SHA256=26c685f0…ecbdd2）に確定（feature 63→62 は CR-02 rolling_jyocd mean→mode rename + sd remove・§13.4 odds-free allowlist 違反なし・D-02 研究者確定）
- [Phase 03.1]: plan 03.1-04: PLAN acceptance criteria feature_count 24→62 を実装実態（rolling 32 + 静的/PK/label/meta 30 = 全 Parquet 列数）に一致（commit 5535bc5・実装不変・文書のみ・postreview-v2 で 63→62 に更新: rolling_jyocd_mean→mode rename + sd remove）
- [Phase ?]: [Phase 04]: plan 04-01: lightgbm==4.6.0/catboost==1.2.10 pin (D-11) + prediction.fukusho_prediction DDL (11カラム PK + 3 CHECK 制約・review HIGH#1/Cross-Plan #3) + tests/model/ 20 RED stub (review MEDIUM#3) + v3→postreview-v2 ドリフト修正 (D-01)
- [Phase ?]: [Phase 04]: plan 04-01 Rule 3 fix — scripts/run_apply_schema.py::apply() が APPLY_ORDER ではなくハードコードリストを使うため prediction_table DDL を両方に挿入
- [Phase 04]: plan 04-02: review HIGH#9 対応 — データ API を load_feature_matrix/load_labels/build_training_frame/make_X_y/prepare_model_matrix の5関数に明示分離 + FEATURE_COLUMNS を registry derived allowlist (35 feature) で定義 + make_X_y が X.columns == FEATURE_COLUMNS を完全一致 assert（契約混乱・fake-green 防止）
- [Phase 04]: plan 04-02: review MEDIUM#5/MEDIUM#6 対応 — split_3way が完全時系列条件 train_max<calib_min<calib_max<test_min<=test_max を raise ValueError で保証 + verify_snapshot_sha256 が manifest の完全 SHA256 と hash scope を検証（Phase 3 snapshot.write_snapshot と同一手順で metadata 除外再計算）
- [Phase 04]: plan 04-02: review HIGH#5/D-06 対応 — save_native_artifact が CalibratedClassifierCV を base native + calibrator.joblib + metadata.json に分離保存 + load_native_artifact が真正再構築（Cycle 2 NEW-5/NEW-M1/NEW-L1・scikit-learn==1.9.0 pin 安定性保証）
- [Phase 04]: plan 04-02 Rule 3 fix — FEATURE_COLUMNS 数「42」は v3/feature_count=63 時代の旧情報・postreview-v2 実データ値 35 が正（registry derived allowlist の正適用）
- [Phase 04]: plan 04-02 Rule 1 fix — verify_snapshot_sha256 が生ファイル bytes で計算していたのを Phase 3 snapshot.write_snapshot と同一手順（metadata 除外・決定論的書込設定）で再計算するよう修正
- [Phase ?]: D-04-03: LightGBM native cat + CatBoost has_time + HIGH_CARD_CODE_COLS を cat_features に含め (review HIGH#6/MODL-03)・align_predictions 5条件厳密置換 guard (Cycle 2 NEW-2)・eval_max_date <= train_max_date (review Cross-Plan #8)
- [Phase ?]: D-04-03 baseline: BL-1..5 全計算・市場データ (fukuoddslow/ninki) は feature 非混入 (D-07/MODL-01)・BL-4/5 calibrate 引数 + bl_calib_note 列でキャリブレーション状態明示 (review MEDIUM)
- [Phase 04]: review HIGH#4/Cross-Plan #1/Cycle 3 NEW-4: make_model_version が D-10 例と完全一致 {feature_snapshot_id}-{short}-v{N} を返す・feature_snapshot_id 全体を prefix・二重 postfix 回帰防止
- [Phase 04]: review HIGH#1/Cross-Plan #3: prediction_load.py が model_version スコープ置換 (DELETE WHERE model_type+model_version → INSERT) を採用・全テーブル破壊でなく他 model/version の行を保持
- [Phase 04]: Cycle 2 NEW HIGH-1: predict_p_fukusho が pred_proba 引数で CatBoost aligned 予測値を注入・再予測で整列が捨てられる silent wrong-horse prediction 回帰を閉塞
- [Phase 04]: review MEDIUM/LOW: evaluator.py が sum(p) を独立二値確率の診断的指標として扱い binning 契約固定・reports/04-eval.{md,json} に分離出力
- [Phase ?]: test decision 04-05
- [Phase ?]: 04-05: train_and_predict orchestrator を src/model/orchestrator.py に配置 (review HIGH#12: 循環依存回避)・行整列保証 + bit-identical + aligned pred_proba 注入
- [Phase ?]: 04-05: SC#4 bit-identical を実データ両モデルで実証 (固定 seed=42 + thread count=1 + FIXED_REPRODUCE_TS・np.array_equal)
- [Phase ?]: 04-05: CatBoost + CalibratedClassifierCV 互換性: base estimator Pool 予測から手動 calibrator fit (StringDtype pd.NA 回避・Rule 3 auto-fix)
- [Phase 05]: §15.5 優先 — BT-1..3 train_start='2019-06-01'（Phase 3 D-09 の 2016H2〜 でなく要件正を適用・T-05-02 mitigate）
- [Phase 05]: BT-4/5 test 年は 2024 に揃える（D-03 + planner A2・BT-1..3 の test 年と比較可能にするため）
- [Phase 05]: MEDIUM-01a — 固定 BT窓と mlxtend.GroupTimeSeriesSplit の等価性を docstring + test で立証（T-05-01b mitigate）
- [Phase 05]: Wave 0 RED stub は lazy import で collection 保証（Phase 2 decision 02-22 と同一パターン）
- [Phase ?]: 05-02: EV/rank/purchase/metrics/bl3 は全て純粋関数 (DB 不要) で実装・baseline.py compute_bl1 パターン踏襲・§11.5 閾値を RANK_THRESHOLDS 定数で外部化 (T-05-03 mitigate)
- [Phase ?]: 05-02: BL-3 は fukuoddslow 昇順 top-2 (EV でない) で選択・p=1/odds で EV=1.0 自己参照回避 (D-04)・BL3_BETTING_CAVEAT は baseline.BL3_COMPARISON_CAVEAT を import して再公開 (§14.2 caveat・T-05-04 mitigate)・model_type='bl3'/odds_snapshot_policy='confirmed' sentinel (JODDS 時点非依存)
- [Phase ?]: 05-02: profit_loss は集計式 sum(payout)+sum(refund)-sum(stake)・行 profit (refund_accounting 出力) との不変量を test_metrics_profit_invariant で混在シナリオ検証 (MEDIUM-02/T-05-05b)・max drawdown は race_date 昇順 cummax-cumsum (共有パターン7)

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

Last session: 2026-06-20T23:28:04.068Z
Stopped at: Completed 05-02-PLAN.md
Resume file: None
