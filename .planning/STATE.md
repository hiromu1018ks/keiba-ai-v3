---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Ability Feature v2 & Conditional Calibration
current_phase: 1
status: Awaiting next milestone
stopped_at: Completed 12-01-PLAN.md (statsmodels + p_lower + migration)
last_updated: "2026-06-28T13:31:41.652Z"
last_activity: 2026-06-28
last_activity_desc: Milestone v1.1 completed and archived
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 25
  completed_plans: 25
  percent: 100
current_phase_name: p_lower EV & Falsification Evaluation
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能バックテストで定量評価できること。リーク防止と再現性だけは必ず守る。
**Current focus:** Phase 12 — p_lower EV & Falsification Evaluation

## Current Position

Phase: Milestone v1.1 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-28 — Milestone v1.1 completed and archived

## v1.1 Milestone Context

**Goal:** core value（odds-free）維持のもと、回収率0.65天井（debug `fukusho-recovery-070` 3層 ROOT CAUSE）へ正統に対応する。能力特徴量を「着順中心」から「速度・相手強度・レース内相対」へ拡張し、レース内相対確率モデル + `p_lower` EV で投票層の過大予測を是正。falsification test で odds-free market residual を統計検証（特徴量不足 vs 構造的限界の鑑別）。

**成功基準（正直・黒字化でない）:** 市場残差能力の定量測定 + 投票層の過大予測是正。現実回収率 0.78-0.92 見込（外部2AI 一致）。

**Phase 構成（依存関係 DAG）:**

- Phase 9: FEAT-01 スピード指数基盤（FEAT-02/03 の前提）
- Phase 10: FEAT-02 相手強度 + FEAT-03 レース内相対（FEAT-01 に依存）
- Phase 11: MODEL-01 レース内相対確率モデル（FEAT-01/02/03 完成後）
- Phase 12: EV-01 p_lower EV + EVAL-01 指標拡張 + EVAL-02 falsification + SAFE-01 オッズ帯別条件付き calibration 受入基準

**聖域（全フェーズで遵守）:** odds-free（オッズ/人気/過去人気/過去オッズ proxy は `p` モデルに入れない）・リーク防止（PIT correct・race_id group split・merge_asof backward・adversarial audit）・再現性（§19.1・byte-reproducible snapshot・FIXED_REPRODUCE_TS）・§15.2 事前登録指標不変（後知恵すり替え禁止）・test 窓は最終評価のみ（過学習聖域 §11.2）

## Performance Metrics

**Velocity:**

- Total plans completed: 59 (v1.0) + 0 (v1.1)
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
| 05 | 6 | - | - |
| 06 | 5 | - | - |
| 07 | 3 | - | - |
| 08 | 3 | - | - |
| 09 | 0/5 | - | - |
| 10 | 9 | - | - |
| 11 | 5 | - | - |
| 12 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: — (v1.1 未実行)

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
| Phase 05 P03 | 7m | 2 tasks | 4 files |
| Phase 05 P04 | 10m | 2 tasks | 9 files |
| Phase 05 P05 | 32m | 2 tasks | 3 files |
| Phase 05 P06 | 35m | 2 tasks | 5 files |
| Phase 06 P01 | 15m | 2 tasks | 4 files |
| Phase 06 P02 | 約25分 | 2 tasks | 3 files |
| Phase 06 P03 | 約30分 | 2 tasks | 2 files |
| Phase 06 P04 | 約30分 | 3 tasks | 6 files |
| Phase 06 P05 | 41min | 2 tasks | 4 files |
| Phase 07 P01 | 7min | 3 tasks tasks | 11 files files |
| Phase 07 P02 | 12min | 2 tasks | 5 files |
| Phase 07 P03 | 8 | 2 tasks | 6 files |
| Phase 08 P01 | 5min | 3 tasks | 6 files |
| Phase 08 P02 | 3min | 2 tasks | 5 files |
| Phase 08 P03 | 35min | 1 tasks | 3 files |
| Phase 09 P01 | 約35分 | 2 tasks | 4 files |
| Phase 09 P02 | 約30分 | 3 tasks | 4 files |
| Phase 09 P03 | 約12分 | 3 tasks | 7 files |
| Phase 09 P04 | 約18分 | 2 tasks | 2 files |
| Phase 10 P01 | 23min | 1 task tasks | 2 files files |
| Phase 10 P02 | 11min | 1 task | 2 files |
| Phase 10 P03 | 4min | 1 tasks | 2 files |
| Phase 10 P04 | 38min | 1 tasks | 6 files |
| Phase 10 P05 | 90min | 2 tasks | 5 files |
| Phase 10 P06 | 60min | 3 tasks | 6 files |
| Phase 10 P07 | 55min | 2 tasks | 3 files |
| Phase 11 P01 | 7 | 3 tasks | 3 files |
| Phase 11 P02 | 5 min | 2 tasks | 1 files |
| Phase 11 P03 | 8 min | 2 tasks | 4 files |
| Phase 11 P04 | 9 min | 2 tasks | 2 files |
| Phase 12 P01 | 15min | - tasks | - files |
| Phase 12 P01 | 15min | 2 tasks | 9 files |
| Phase 12 P02 | 40min | 2 tasks | 7 files |
| Phase 12 P03 | 45min | 2 tasks | 9 files |
| Phase 12 P04 | 775s | 1 tasks | 2 files |
| Phase 12 P04 | 1200s | 1 tasks | 10 files |

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap v1.1: Strict DAG-driven phase order（Phase 9→10→11→12）— スピード指数（FEAT-01）は相手強度・レース内相対（FEAT-02/03）の前提・それらが揃ってから MODEL-01 レース内相対確率モデル・その後に EV-01 p_lower + EVAL-01/02 + falsification を統合
- Roadmap v1.1: core value（odds-free）維持での正統な改善道（能力特徴量精密化 + レース内相対確率モデル）・過去人気/過去オッズ proxy は市場回帰で除外（2AI 一致・debug + リサーチ準拠・SAFE-01 横断）
- Roadmap v1.1: 成功基準は黒字化でなく「市場残差能力の定量測定」+「投票層の過大予測是正」（現実回収率 0.78-0.92 見込・正直な結論・EVAL-02 falsification で特徴量不足 vs 構造的限界を鑑別）
- Roadmap v1.1: §15.2 事前登録指標（calibration_max_dev/Brier/LogLoss/sum(p) 分布）は不変・追加指標は上書きでなく併載（後知恵すり替え禁止）
- Roadmap v1.1: v1.0 対抗的監査パターン（tests/audit/・KEIBA_SKIP_DB_TESTS unset live-DB GREEN・SC#1/#2/#3 踏襲）を全フェーズで遵守
- Roadmap v1.0 (履歴): Strict DAG-driven phase order — no model work (Phase 4) before labels (Phase 2) and as-of features (Phase 3) are locked and gated
- Roadmap v1.0 (履歴): Phase 2 (Labels) is the long pole with a hard >99.9% payout-table reconciliation gate; Phase 8 is a dedicated adversarial-audit acceptance gate consolidating TEST-01
- Roadmap v1.0 (履歴): Snapshots/reproducibility-stamping folded into Phase 3 (as-of builder writes immutable Parquet) rather than a standalone phase
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
- [Phase ?]: RED テスト collection 保証のため module-level import を遅延 import 化（Plan 02-22）
- [Phase ?]: Phase 2 Plan 03 GREEN: fukusho_label ETL 実装完了・27 unit tests GREEN・REVIEWS HIGH #1/#3/#4/#5/#6 + NEW HIGH #2/#3 解決・Task 3 実DB実行は checkpoint:human-verify で停止
- [Phase ?]: 02-04: LABEL-03 gate PASSES live (100% agreement, 6 BLOCK checks green). Drift BLOCK->INFO per Rule 1 (drift is D-04-legitimate, label correctness via precision/recall BLOCK)
- [Phase ?]: 03-01: rolling 8 systems x 3 axes (24) + static 15 + running_style 1 = 40 features; source_role taxonomy [HIGH #4]; strict < cutoff unified [HIGH #2]
- [Phase 03]: plan 03-02: label.fukusho_label.race_date 全 554267 行 backfill 済 (Phase 2 負債解消)・INSERT/SELECT positional mismatch を Rule 1 で auto-fix・staging-swap idempotent (2回実行同一 checksum) + raw 不変性 PASS
- [Phase 03 / 2026-06-23 追記]: 上記 backfill 成果が某経路で消失し race_date 全行 NULL に戻っていたのを検出（Phase 5 実データ backtest の _filter_label_by_period で発覚）→ scripts/run_label_race_date_backfill.py 再実行で 554267/554267 non-NULL に復元（raw fingerprint 前後完全一致・idempotent verify PASS）。label ETL 本体 (_RACE_META_SELECT_COLUMNS に race_date) + backfill の二重防衛 + 回帰テスト追加 (test_race_meta_select_columns_includes_race_date / test_compute_fukusho_labels_propagates_race_date) で再発防止
- [Phase 05 / 2026-06-23]: 実データ backtest（--snapshot-id 20260620-1a-postreview-v2・全5窓）が完走（25 backtest = 主モデル20 + BL-3 5・exit 0・coverage gate 全 pass 99.99-100%・reports/05-backtest.{md,json} 生成）。race_date 復元に加え実データパス固有の連鎖 bug（pred_df の race_start_datetime/race_key 付与・merge_asof 大域 sort・make_race_key zfill 正規化・umaban 型統一・BL-3 fukuoddslow 数値化・market_df test窓絞り・_is_na NaT 捕捉）を修正 + 回帰テスト追加。TRUNCATE→再実行で checksum 同一（決定論的・§19.1）
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
- [Phase ?]: 05-03: HIGH-3 canonical rule — CONTEXT D-02 を正とし 0999=no_bet sentinel（RESEARCH 行89 廃棄・T-05-07b mitigate）
- [Phase ?]: 05-03: cross-plan contract — select_odds_snapshot 戻り値は snake_case fuku_odds_lower/fuku_odds_upper（JODDS raw を rename・T-05-SC2 mitigate）
- [Phase ?]: 05-03: merge_asof by=['race_key','umaban'] — HIGH-1 馬単位 odds 保証（T-05-06b mitigate）
- [Phase ?]: 05-03: 特払（TokubaraiFlag2='1'）は的中フラグ非依存・HARAI PayFukusyoPay 一次契約（§2.4・T-05-23 mitigate）
- [Phase ?]: 05-04: split_3way periods=None は Phase 4 ハードコード（_DEFAULT_PERIODS）を使用（A5 後方互換・SC#4 回帰防止）・holdout 区間（>=2025-01-01）は固定
- [Phase ?]: 05-04: 完全時系列条件 guard（max(train)<min(calib)<max(calib)<min(test)<=test(test)）は BT窓でも同一保証（HIGH-4: train/calib 重複 periods は ValueError で look-ahead leak 構造的ブロック）
- [Phase ?]: 05-04: category_map plumbing は _apply_category_map(feature_df, category_map) helper で実装・None は no-op（Phase 4 等価・A5）・test 窓未観測 ID → __UNSEEN__ sentinel（§14.3 leak-safe categorical・HIGH-A cycle-2 silent 無視厳禁）
- [Phase ?]: 05-04: backtest_id scoped staging-swap（review HIGH#1 と同一方針・同一 backtest_id のみ DELETE→INSERT・他 backtest_id 行は保持）・PK は backtest_id + RACE_KEY 7 の 8カラム（§19.1 再現性聖域・silent 履歴破壊防止）
- [Phase ?]: 05-04: MEDIUM-04 odds_missing_reason は NULL 可能・normal 候補は NULL・no_bet/special_value/no_sale/scratch_cancel sentinel で埋まる・selected_flag=False 除外候補行も永続化（§11.3 odds_missing_policy=no_bet 監査性担保）
- [Phase ?]: 05-04: live-DB への CREATE TABLE/GRANT 適用は後続 Plan 05-06（checkpoint:human-verify）のスコープ・本 plan は unit test（KEIBA_SKIP_DB_TESTS で skip される requires_db テストを含む）で検証
- [Phase ?]: 05-05: scripts/run_backtest.py + src/ev/report.py で Plan 01-04 全成果物を統合・フル行列 25 backtest (5窓 × 2policy × 2model + 5 BL-3) を生成・実データ backtest は JODDS 取得進行中のため Plan 05-06 で分離（本 plan は合成データ E2E smoke）
- [Phase ?]: 05-05 HIGH-B cycle-2: _carve_calib_from_train_tail(bt) は train_start 固定・train_end = calib_start - 1day に短縮 (calib を BT窓 train 尾の6ヶ月から切る)・max(train)<min(calib)<max(calib)<min(test) 順序を BT-1..5 全窓で deterministic に保証
- [Phase ?]: 05-05 HIGH-1+2: pred_df/snapshot/label の merge は on=['race_key','umaban'] + len(merged)==len(pred_df) assert で cartesian duplication を構造的ブロック (HARAI は race-level slot のため on=['race_key']+validate='many_to_one' で例外・HIGH-C)
- [Phase ?]: 05-05 HIGH-5: 各 BT窓 train 期間のみで fit_category_map・test 窓未観測 ID を __UNSEEN__ sentinel に mapping (全期間固定 category_map 再利用回避・05-04 HIGH-A category_map plumbing 経由で伝播)
- [Phase ?]: 05-05 HIGH-C cycle-2: HARAI は race-level slot レコードのため race-level merge(on=['race_key'], validate='many_to_one') でブロードキャスト・払戻は 05-03 _lookup_payfukusyo_pay の行ベース slot lookup で確定
- [Phase ?]: 05-05 MEDIUM-A cycle-2: select_bets 後に selected + non-selected の全候補 (full_candidate_with_accounting・odds_missing_reason 埋め) を load_backtest に渡し §11.3 監査性を担保
- [Phase ?]: 05-05 MEDIUM-B cycle-2: --synthetic 外す実行で candidate-horse usable-odds coverage < 0.90 で RuntimeError (race-level coverage < 0.95 も secondary check・取得未完の不正 backtest を loud fail)
- [Phase ?]: 05-05 MEDIUM cycle-3: determine_stake_payout が selected_flag 分岐を持たないため non-selected 行の stake/effective_stake/payout/refund/profit を永続化前に 0 にゼロ化 (架空会計防止・ROI 計算は selected_flag=True filter 済みで非影響)
- [Phase ?]: 05-05 LOW-05: REPORT_COLUMNS を外部定数で定義し md 列ヘッダ + json comparison_table キーと 1:1 になることを presence assert で機械検証 (grep 否定でない)
- [Phase ?]: 05-05 BACK-04: 全候補を backtest_id 辞書順で一括提示・highest-recovery を推奨/採用候補として突出させる記述は一切生成しない (主モデル確定は Phase 6 D-03/D-04 事前登録選定基準)
- [Phase 05] 05-06: live-DB backtest.fukusho_backtest テーブル + GRANT 適用 (CREATE TABLE IF NOT EXISTS・PK 8カラム + CHECK 制約2個・reader=SELECT/etl=全権・run_apply_schema.py APPLY_ORDER 経由)
- [Phase 05] 05-06 Rule 1 fix: PostgreSQL 引用符なし識別子小文字化で BACKTEST_COLUMNS (EV_lower/upper 大文字混在) と不整合 → DDL 側で引用符付き保持 + tests DDL パーサー強化 + DROP TABLE→TRUNCATE (admin 所有テーブル・ETL ロール DROP 不可)
- [Phase 05] 05-06: 実データ backtest (BT期間 2019-2025) は JODDS 取得進行中のため manual-only 検証として分離 (2段階実行計画・MEDIUM-05 _assert_jodds_coverage_horse_level gate で coverage<0.90 は loud fail)
- [Phase 05] 05-06: Phase 5 自動化部分 完了宣言 (フル suite 350 passed + 合成データフル行列 25 backtest GREEN + BACK-01..04 構造的ブロック全 GREEN)・主モデル確定は Phase 6 D-03/D-04 事前登録選定基準 (Calibration 重視) に引き継ぎ
- [Phase ?]: [Phase 06] plan 06-01: plotly>=6.8.0 + scipy>=1.17.1 明示依存追加（D-10・spearmanr 直接 import 用）
- [Phase ?]: [Phase 06] plan 06-01: Open Question #1 RESOLVED — segment 6軸カラム経路が実 DB で確定（label 直接 + market JOIN フォールバック・prediction test 44426 行 = label JOIN 後 44426 行・cartesian duplication なし）
- [Phase ?]: [Phase 06] plan 06-01: reports/04-eval.json の guarded 列欠損（C6 stale）解消は Plan 06-02/06-05 に委譲（Wave 0 本質は契約固定化 + segment 軸確認・unguarded 実データ値で GREEN 達成済み）
- [Phase 06]: plan 06-03: np.digitize の right=True で banding 区間を上界閉区間 (edges[i-1], edges[i]] に（PLAN 期待通り ninki=3 → "1-3"・odds=2.9 → "1.0-2.9"・Rule 1 auto-fix）
- [Phase 06]: plan 06-03: segment_eval.py は evaluator.py の binning 契約（_compute_calibration_curve_bins / _compute_ece / _compute_mce / CALIBRATION_CURVE_*）を import 再利用・bit-identical 保証・独自 binning 導入禁止（T-06-07）
- [Phase 06]: plan 06-03: include_plotlyjs='directory' で plotly.min.js を共有1ファイル参照（REVIEW C13 cycle-2・N1 解消・reports/ tracked ポリシー維持・.gitignore 変更なし・~21MB 重複を ~3.5MB に集約）
- [Phase 06]: plan 06-04: is_primary 列追加は boolean NOT NULL DEFAULT false で（REVIEW HIGH#8）・CHECK prediction_is_primary_domain は NOT NULL 二重防御・3ファイル連鎖（schema/predict/prediction_load）は Pitfall 4 列数一致 assert で機械検証
- [Phase 06]: plan 06-04: set_primary_model は model_type+model_version+feature_snapshot_id+as_of_datetime スコープで UPDATE（staging-swap idiom と同方針・全行 UPDATE でない・silent 履歴破壊防止）・idempotent・両モデル行保持
- [Phase 06]: plan 06-04: REVIEW HIGH#7 対応 — set_primary_model は 0 行 UPDATE で RuntimeError（post-condition assert）+ SELECT で is_primary=true が1 model_type のみ・>=1 行を検証（silent no-op を fail-loud に）・_canonicalize_as_of_datetime（pd.Timestamp 正規化）で timezone/microsecond ズレ対策（REVIEW C11）
- [Phase 06]: plan 06-04: REVIEW C17 重複解消 — 本 plan checkpoint は「機構承認」のみに縮小・主モデル選定自体（D-07）は Plan 06-05 Task 2 checkpoint:human-verify で実施
- [Phase ?]: D-07 主モデル確定: lightgbm（D-04 事前登録基準・全指標で CatBoost を上回る・is_primary=true 設定済み）
- [Phase ?]: D-08 tiebreak: backtest_recovery_rate（06-05・LightGBM 0.7022 vs CatBoost 0.6808）
- [Phase ?]: 06-05 sum(p) threshold 0.30 維持（threshold_appropriate=False・SC#2 達成で WARN のまま・後続再検討）
- [Phase ?]: 06-05 model_version 推測は make_model_version に一本化（[:3] 手動推測は lig/cat 偏差 bug・Rule 1）
- [Phase ?]: 07-01: PREDICTION_CSV_COLUMNS (20) / BACKTEST_CSV_COLUMNS (16) を DRY 単一定数化 (§16.2 pin・D-04 LOCKED・LOW-05 presence assert 再利用)
- [Phase ?]: 07-01: odds 列名 canonical は fukusho_odds_* (外部公開)・loaders 内部 fuku_odds_* は normalize_prediction_export_columns で rename (REVIEW HIGH-1)
- [Phase ?]: 07-01: odds_snapshot_at は JODDS snapshot happyo_datetime から取得 (backtest JOIN でなく・backtest テーブルに odds 値カラム不存在のため構造的不可能・REVIEW MEDIUM-2)
- [Phase ?]: 07-01: BACKTEST_CSV_COLUMNS は16列 (§16.2 原典優先・CONTEXT D-04「14列」は errata・RESEARCH Pitfall 3)
- [Phase ?]: 07-01: read-only 保証テストは AST で execute() Call 第一引数 str 定数のみ検査 (comment/docstring false positive 回避・planner-discipline-allow マーカーで例外許容・REVIEW LOW-2)
- [Phase 07]: 07-02: Open Question #1/#2 RESOLVED — odds/EV/rank/odds_snapshot_at は backtest JOIN でなく prediction SELECT(is_primary=true)→JODDS snapshot→compute_ev_and_rank 再計算経路で取得 (backtest テーブルに odds 値カラム不存在のため構造的不可能・BLOCKER-1)
- [Phase 07]: 07-02: REVIEW HIGH-1 順序 — compute_ev_and_rank (内部名 fuku_odds_* 期待) の後に normalize_prediction_export_columns で fukusho_* rename (順序逆だと KeyError)
- [Phase 07]: 07-02: REVIEW MEDIUM-4 完全化 — load_* は純粋関数 (@st.cache_data なし・CLI 直接 import)・load_*_cached が @st.cache_data(hash_funcs={ConnectionPool: id}) 付き UI 用 wrapper (CLI は Streamlit runtime 非依存)
- [Phase ?]: 07-03: pool lifecycle は @st.cache_resource で単一 readonly pool を保持・try-finally close 廃止（REVIEW HIGH-5）
- [Phase ?]: 07-03: download_button scope=選択レースのみ（MEDIUM-6）・フィルタ全体は OUT-01 CLI で使い分け
- [Phase ?]: 07-03: 推奨ランク S 強調色は column_config と競合するため caption 代替（LOW-4 non-blocking polish）
- [Phase ?]: 07-03: SEGMENT_AXES モジュール定数を selectbox に変数渡し・テストは str Constant fallback で検証
- [Phase 08]: 08-01: tests/audit/ パッケージ新設（SC#2 3ケース lookahead/payout正欠損/fold race_id共有 + D-06 UI/CSV 計9テスト・KEIBA_SKIP_DB_TESTS=1 GREEN・DB 不要・adversarial 5段階鋳型で false-pass 構造的排除・docstring cross-reference で機能テストと棲み分け）
- [Phase 08]: 08-01: payout recall は cursor ベース end-to-end で検証（DataFrame 受け API 非存在・src/etl/label_reconcile.py L933 署名 cur: Cursor）・backtest_strategy_version は予測テーブル非存在のため PREDICTION_CSV_COLUMNS presence assert 対象から除外（UI 用 REPRODUCIBILITY_STAMPS 側にのみ含む）
- [Phase ?]: SC#3 合成層 (08-02) は DB 不要 pytest (calibrator bit-identical + tests/audit/) のみで orchestrate・live-DB 必須 CLI は 08-03 に委譲 (D-03/F-02/F-03)
- [Phase ?]: reports/08-audit の KNOWN_LIMITATIONS 3項目 (回収率天井・Calibration劣位・odds JODDS再検証) を定数で強制し md と json の両方に honest 開示 (D-05)
- [Phase 09]: plan 09-01: POINTS_PER_SECOND_BY_DISTANCE_M は Beyer 文献[ASSUMED]概算値(1000:16.5..3200:5.0)を採用・SC#5 ドメイン整合性検証後に微調整可（canonical feature は float・D-05）
- [Phase 09]: plan 09-01: leave-one-race-out variant は一次近似(A3) group_median - (self_residual - group_median)/(n-1) を採用・厳密ループでなく docstring/test で精度上限明示
- [Phase 09]: plan 09-01: REVIEW H4 対応 — par group = obs_id + jyocd×trackcd×kyori・variant group = obs_id + source_race_date×jyocd×surface (obs_id 必須・cross-obs leak 構造的不能・sample_count 変化で false-pass 回避を機械証明)
- [Phase 09]: plan 09-01: odds-free 文書化と禁止トークン grep==0 の両立のため docstring の直接トークン名(odds/ninki/..)を一般化表現に置換・P04 AST audit で完全証明予定
- [Phase 09]: plan 09-03: builder Step 5b 挿入位置 = WR-01 fail-loud history 空チェック後・CR-01 merge 前（Step 5 rolling の直前）。history["speed_figure"] を copy-not-rename で付与
- [Phase 09]: plan 09-03: REVIEW H1-c 解決 — Step 5b 直前に feature_matrix["obs_id"] を早期構築（既存 Step 6 L505-517 と完全同一 idiom・Step 6 で再利用・Step 6b で drop・P01 API 契約充足）
- [Phase 09]: plan 09-03: REVIEW H1-a 解決 — load_feature_matrix(snapshot_id) を必須パラメータ化（acceptance から arity-0 escape `or list(sig.parameters)==[]` を削除・古い arity-0 関数を構造的に拒否）
- [Phase 09]: plan 09-03: REVIEW H1-b 解決 — orchestrator.train_and_predict に snapshot_id 引数追加（feature_snapshot_id とは別・FEATURE_COLUMNS 選択用）・内部3箇所の make_X_y を snapshot_id=snapshot_id で明示伝播・grep/AST verify で予測経路の bare call 残存なしを保証
- [Phase 09]: plan 09-03: 新 feature_snapshot_id 候補 = 20260625-1a-speedfigure-v1（v1.0 20260620-1a-postreview-v2 系統継承・make_model_version prefix 整合・P04/P05 が消費）
- [Phase ?]: SC#4 SAFE-01 proxy 排除: AST Name/Attribute + H5 SQL 文字列 word-boundary で市場情報 proxy 0件を静的証明（Phase 9 横断聖域）
- [Phase ?]: SC#5 script: build_feature_matrix dict 戻り値から result[feature_matrix] 抽出・include_plotlyjs=directory + div_id 固定で byte-reproducible・dsn_masked+statement_timeout で安全
- [Phase ?]: Phase 10 Plan 01: CYCLE-2 HIGH-C2-1 source-as-of full-pipeline recompute（obs_id=SOURCE_ASOF_<race_nkey>_<kettonum>・source_race.available_at cutoff で compute_speed_figure_for_history を raw history に再実行・値レベル source-vs-target-cutoff 保証）
- [Phase ?]: Phase 10 Plan 01: CYCLE-3 MEDIUM #1/#2/#3（available_at 関数内導出・horse-level par via race×horse obs_id・per-source-race batch で H² 積回避）
- [Phase ?]: Phase 10 Plan 01: D-02 Open Question #1 解決（OPPONENT_ROLLING_AXIS=rolling_speed_figure_mean_5 の1軸のみ・17倍計算量抑制）
- [Phase ?]: Phase 10 Plan 02: rolling_field_strength 21 feature（D-06 第2段階）実装・D-13 意味サフィックス命名・CYCLE-2 HIGH-C2-2 downstream gate
- [Phase 10]: Phase 10 Plan 03: FEAT-03 race_relative.py (target-only race_id group-by + competition ranking + W-5 §11.2 protection + W-2 diagnostic helper) — D-10 competition ranking via pandas Series.rank method=min ascending=False na_option=keep. D-12 coef 0.25 canonical pre-registered (candidates {0.0,0.1,0.25,0.5} for train/calib window only). REVIEW MEDIUM-7 gap_to_3rd tie spec: rank==3 empty -> all NaN. CYCLE-3 MEDIUM #2 horse-level par scale compatibility.
- [Phase ?]: Phase 10 Plan 04: builder.py Step5c/6c/6d 統合 (FEAT-02 21 + FEAT-03 6 = 27 feature)・feature_availability.yaml schema_version 0.6.0・CYCLE-2 HIGH-C2-3 raw_history 受渡・A6 構成変更・registry parity GREEN
- [Phase ?]: Phase 10 Plan 05: snapshot 20260626-1a-opponentstrength-v1 生成 (feature_count=106 Parquet, model FEATURE_COLUMNS=79, delta=+27, SHA256 byte-reproducible §19.1) + FEAT-03 snapshot 境界防御的 Float64 変換 + Rule 1 fix (Step6d adjusted_rank 誤 drop)
- [Phase 10]: Phase 10 Plan 07: SC#4 SAFE-01 proxy 排除証明完了 (AST + lookahead 注入 + 値の不変性)。W-3 cProfile 上位3位に Python ループ無し GREEN (vectorized 実装証明)・CYCLE-3 MEDIUM #3 production-scale smoke GREEN (H² 積回避)。W-3 縮小版 5.0 秒閾値は PLAN 01 設計 (CYCLE-2 HIGH-C2-1 per-source-race full-pipeline 再計算・core value 必須) と構造的に両立しない (実測 194 秒) ことが正直発覚・W-3 聖域 (後追い緩和禁止) に従い閾値温存・default skip で PLAN 更新 (閾値根拠再確認) 待ち (Rule 4 アーキテクチャ変更相当・緩和でなく構造的矛盾の正直属証)。
- [Phase ?]: Phase 11 Plan 01: THETA_CANDIDATES=(0.5,0.75,1.0,1.25,1.5)・ALPHA_SEARCH_XTOL=1e-9・P_CAL_CLIP_EPSILON=1e-6 事前登録（§11.2 聖域・src/model/race_relative.py stub）
- [Phase ?]: Phase 11 Plan 01: SC#3 = 同一 LightGBM 同一 seed の再現性（codex review MEDIUM・cross-family 同一性でなく・test_both_models_bit_identical で契約固定）
- [Phase ?]: Phase 11 Plan 01: compute_overprediction_penalty 第3引数 = market_signal（SAFE-01・SC#4 で禁止トークン回避・機能は RESEARCH Pattern 3 準拠）
- [Phase ?]: 11-02: brentq 前 fail-loud guard（finite/theta>0/0<k<n）を必須挿入
- [Phase ?]: 11-02: binning は evaluator/segment_eval の import 再利用・独自 np.linspace bin edge 再定義なし
- [Phase ?]: 11-03: orchestrator.train_and_predict に theta + score_split + _normalize_model_type（codex HIGH#1/#2）・theta/model_type 双方向 guard（codex cycle-2 MEDIUM・silent provenance hole 回避）・sales_start_entry_count 必須（codex HIGH#6）・race_relative 補正層を両予測パスに挿入（SC#3 bit-identical）・theta=None で v1.0 等価（A5・既存テスト10件全 GREEN）
- [Phase ?]: 11-03: artifact metadata.json に race_relative_theta / xtol=1e-9 / epsilon=1e-6 を追加・α_r は不保存（D-10 自己完結性）・定数は数値リテラル（循環 import 回避・bit-identical）・predict に lightgbm_rr→lgbrr / catboost_rr→cbrr 追加（SC#5 model_version-scoped swap 前提）
- [Phase 11]: 11-04: D-10 adversarial を inspect.signature API seam 検証と cross-race leak 検出力証明で強化（docstring 紳士協定でない）
- [Phase 11]: 11-04: theta 選択経路は score_split=calib のみで候補評価・test 窓は theta 再選択なしで一回だけ評価（§11.2 聖域の機械保証）
- [Phase 11]: 11-04: theta-selection.{md,json} を test 窓評価に先立って byte-reproducible に事前書き出し（後知恵すり替え禁止・codex HIGH#1）
- [Phase 11]: 11-04: D-07 set_primary_model 呼出 AST Call 0件・comparison のみ・primary 切替は Phase 12
- [Phase ?]: [Phase 12] plan 12-01: [C2-12-01-1] statsmodels==0.14.6 厳密固定採用（>= でなく ==・byte-reproducible §19.1・将来の false fail 回避）
- [Phase ?]: [Phase 12] plan 12-01: compute_p_lower_conformal_shrinkage は D-01 修正文採用（p 信頼区間保証でなく calib slice 上の過大予測を保守的に差し引く分布自由な shrinkage rule・JMLR 2024 exchangeability 必須）
- [Phase ?]: [Phase 12] plan 12-01: [C-12-01-1 HIGH] scripts/run_apply_schema.py 手動 step list（APPLY_ORDER 不参照）にも prediction_add_p_lower を挿入（schema.py APPLY_ORDER だけでは run_apply_schema.py は適用しない）
- [Phase ?]: [Phase 12] plan 12-01: [C-12-01-4 MEDIUM] predict_p_fukusho に pred_proba_lower 引数追加（race-relative 経路は非 NULL・v1.0 binary 経路は None を機械保証）
- [Phase ?]: [Phase 12] plan 12-01: docstring 直接トークン名 (odds/ninki/fukuodds) を一般化表現に置換（Phase 09 decision 踏襲・test_audit_race_relative.py SQL 文字列 scan との両立）
- [Phase 12]: [C-12-02-1 HIGH] p_lower_q_shrink/p_lower_q_level を train_and_predict の keyword-only 引数で追加・test 窓外部注入 API を構造化 (§11.2 聖域・score_split='test'+theta+None → RuntimeError)
- [Phase 12]: [C-12-02-5] artifact.write_metadata_json を allow_nan=False で厳密化・NaN の JSON 化を ValueError で検出 (§19.1・RFC 8259 strict)
- [Phase 12]: [C-12-02-3] ev_rank._rank に p_col を伝播し EV 計算と rank 条件の確率基準を一致 (投票層定義分裂回避)
- [Phase 12]: [C-12-02-4] Phase 12 専用 reports を REPORT_COLUMNS_PHASE12 + report_columns 切替で分離・Phase 5 既存 REPORT_COLUMNS は不変 (regression 回避)
- [Phase 12]: purchase_simulator p_min_base='p_lower' を Phase 12 評価のデフォルト経路に事前登録 (Pitfall 7 投票層明示)
- [Phase 12] plan 12-03: [C-12-03-1 HIGH] run_falsification_test docstring「pre-registered evaluation regression fitted on the test window」正確表現・曖昧否定表現「学習しない」は 0 件・write_falsification_spec ヘルパー byte-reproducible (sort_keys/ensure_ascii=False/allow_nan=False)
- [Phase 12] plan 12-03: [C-12-03-2 HIGH 選択 A・推奨] §15.2 gate (check_acceptance_gate signature/return 完全不変) と Phase 12 WARN gate (check_phase12_warn_gate 分離関数) を完全分離・D-06 違反リスク最小・BLOCK でなく WARN
- [Phase 12] plan 12-03: [C-12-03-3 MEDIUM] compute_roi_by_bin 別関数 (pd.qcut duplicates='drop') ・evaluate_segment_axis (calibration curve 用 API) は完全不変 (bit-identical binning 契約保護)
- [Phase 12] plan 12-03: [C-12-03-4 MEDIUM] fit_market_implied_calibrator は base=train・calibrator=calib 2-window 分離 (FrozenEstimator + CalibratedClassifierCV・同一 calib slice で二重 fit しない)
- [Phase 12] plan 12-03: [C-12-03-5 MEDIUM] refund_accounting.compute_snapshot_final_slippage は row ベース版 (_lookup_payfukusyo_pay 呼ぶ) + payout_amount 受け取り版の 2 種 (二重 slot lookup 回避)
- [Phase 12] plan 12-03: [C-12-04-3 / C3-12-03-1] Phase 12 定数を src/eval/falsification.py constants block に集約 (Q_LEVEL_SHRINKAGE=0.90 含む・Plan 04 が import・重複定義回避・閾値 drift 防止)
- [Phase 12] plan 12-03: verdict feature_gap (model_p pvalue<α) / structural_limit (>=α) は過度な保証主張でない (α=0.05 事前登録・market 条件付き residual 検出・D-05/D-01 修正文)
- [Phase 12] plan 12-03: 循環参照回避 (src.eval.falsification → src.model.segment_eval → src.model.evaluator chain) のため・evaluator.py から falsification constants への import は関数内 (遅延 import) で実装
- [Phase ?]: C-12-04-1 HIGH: _compute_q_shrink_on_calib を race_key+umaban fail-loud key-join (Phase 11 _attach_label_to_pred idiom) で実装・calib slice のみ・join 失敗は RuntimeError
- [Phase ?]: D-09: compute_switch_recommendation は SC#4 WARN gate + p_lower EV + falsification で switch/hold/reject を report のみ (D-10: set_primary_model Call 0件・人間承認の別アクション)
- [Phase ?]: C-12-04-4 MEDIUM: docstring は load_predictions を呼ぶ事実を正確に反映・Phase 11 docstring の誤りを踏襲せず・D-10 対象を set_primary_model のみに限定
- [Phase ?]: C-12-04-5 HIGH: migration (PREDICTION_ADD_P_LOWER_SQL) は run_apply_schema.py (owner/admin) に一本化・本 script からは実行しない (Phase 11 L286-290 idiom)
- [Phase ?]: [Phase 12] 12-04 gap-closure: JODDS odds pipeline 統合・live-DB END-TO-END 完走 (commit 9da055c/fa783bc/1a97bc6)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 9 research flag: スピード指数構築（FEAT-01）に必要な normalized 層素材（`time`/`kyori`/`babacd`/`trackcd`/`class_code_normalized`）の正式カラム名・品質・欠損パターン・par time 算出に必要な開催日/馬場メタの実態を live-DB で精査する必要 — `/gsd-plan-phase 9 --research-phase 9` または計画時の精査がlikely
- Phase 11 research flag: レース内相対確率モデル（MODEL-01）の `sum(p)=払戻対象数` 制約・race-level top-k calibration の実装方針（Plackett-Luce/Harville/listwise loss/制約付き正規化のどれを採用するか）は、v1.0 独立二値分類の拡張として計画フェーズで比較検討が必要
- **Phase 10 Plan 07 W-3 縮小版閾値（PLAN 更新が必要・Rule 4 相当）**: W-3 縮小版 5.0 秒閾値は PLAN 01 設計（CYCLE-2 HIGH-C2-1 per-source-race full-pipeline 再計算・core value 必須）と構造的に両立しない（実測 194 秒）。W-3 聖域（後追い緩和禁止）に従い閾値は温存・default skip（KEIBA_RUN_PERF_TESTS=1 で RED 再現）で PLAN 更新（閾値根拠再確認）待ち。選択肢 (a) 閾値再設定・(b) PLAN 01 設計見直し（CYCLE-2 HIGH-C2-1 値の不変性を損なわない前提・Rule 4）・(c) W-3 縮小版削除。詳細は 10-07-SUMMARY.md『W-3 閾値と PLAN 01 設計の構造的矛盾』セクション参照。
- **Phase 11 再実行不能（Phase 12 C-12-02-1 guard 回帰・凍結維持・再実行禁止）**: `run_phase11_evaluation.py` は Phase 12 の orchestrator guard（C-12-02-1 HIGH・`score_split='test' with theta requires p_lower_q_shrink`）により main L378-391 で RuntimeError。Phase 11 は 6/27 完了の凍結フェーズ（reports/11-evaluation 確定済み）・p_lower は Phase 12 の仕事。**Phase 11 を再実行してはならない**: Phase 11/12 は同一 model_version の rr 予測行に `load_predictions` で書き込み・`p_lower_q_shrink=0.0` 等で無理やり動かすと `p_lower=p_final`（引き算なし）で上書きされ Phase 12 が正しく計算した p_lower（0.3328 引き）が静かに消える（silent data corruption）。「落ちる」状態は安全装置（人が気づく）・壊れたままが正解。将来本当に再実行する場合は q_shrink 計算の移植（Phase 12 と同等）を含む復旧タスクとして計画的に実施すること。Phase 11 の segment_eval WARNING（Phase 12 と同根の y_true_col 不整合）は凍結のため未修正（影響なし・Phase 12 側は commit 98e150f で修正済み）。

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260625-h1g | label race_date NULL 再発の原因特定可能化 fail-loud guard | 2026-06-25 | 0695787 | [260625-h1g-label-race-date-null-fail-loud-diagnosti](./quick/260625-h1g-label-race-date-null-fail-loud-diagnosti/) |
| 260628-t2s | is_primary 切替 → A1（speedfigure-v1・binary・v1.1.0）+ 切替後 BT-1..5 + segment dump | 2026-06-28 | fe111b4 | [260628-t2s-switch-is-primary-to-a1-speedfigure-v1-l](./quick/260628-t2s-switch-is-primary-to-a1-speedfigure-v1-l/) |

### Roadmap Evolution

- Phase 3.1 (Timediff/Babacd Rolling Restoration) inserted after Phase 3 (URGENT): Phase 2 ETL source extension (timediff/babacd → normalized.n_uma_race) + Phase 3 rolling re-registration of the 6 features deleted in gap-closure 03-05 (CR-01). Planned via /gsd-plan-phase 03.1 after Phase 3 gap-closure (03-05) completes.

## Deferred Items

Items acknowledged and deferred at v1.0 milestone close on 2026-06-25:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| debug | fukusho-recovery-070 | diagnosed — 回収率0.65-0.70天井の構造的限界（ROOT CAUSE 確定・3層構造: 市場情報不足→中高オッズ域過大予測→EV演算増幅→複勝控除率天井）。戦略判断（A受容/B 1-A改善/C Phase 1-B）は別計画フェーズ・ユーザー承認済(2026-06-24)・要件未達でなく正直な結論 → **v1.1 は戦略 B（1-A改善: 能力特徴量精密化 + レース内相対確率モデル）として実行中** | 2026-06-25 |
| verification | phase-07-human-needed | human_needed — 36/36 truths verified・残り2件はライブブラウザ描画振る舞い（grep/AST 不可視）・07-03 checkpoint:human-verify で RESOLVED 済・回帰監視として残存 | 2026-06-25 |

Items acknowledged and deferred at v1.1 milestone close on 2026-06-28 (override closeout — 監査 gaps_found・BLOCKER 0・機構完成・Core Value 保持):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| debug | fukusho-recovery-070 | **RESOLVED in v1.1** — 戦略 B（能力特徴量精密化 + レース内相対確率モデル）を実行した結果、Spike 001 ablation で「黒字化したのは Phase 9 基本6（speed figure・binary）のみ・cross-window 5窓平均回収率1.14」と判明。A1 を is_primary にデプロイ（ユーザー承認・backtest 反映済み）。 | 2026-06-28 |
| verification | phase-09-09.1-verification-gap | FEAT-01 VERIFICATION.md 欠落（Phase 9 は 09-VALIDATION.md draft のみ・Phase 9.1 は SUMMARY/REVIEW のみ）・機構・テスト・snapshot は実在し cross-phase 9/9 WIRED・Spike 001 で基本6黒字を過剰実証済み・形式証跡の補完が残課題 | 2026-06-28 |
| verification | phase-11-12-provisional-results | Phase 11/12 数値結果（baseline 0.7314/p_lower 0.0/falsification feature_gap/switch reject）は buggy label v1.0.0 universe で暫定・label v1.1.0 修正済み（commit 2cdbac1）だが reopen 不可（guard C-12-02-1・silent p_lower corruption 防止）・Spike 001 が v1.1.0 正準ベースライン（A1 黒字） | 2026-06-28 |
| tech-debt | phase-09-05-stopgate-incomplete | Phase 9 SC#6 stop gate 指標算出パイプライン未完成（09-05 partial・pred_df label JOIN bug・Phase 5 idiom 移植未実施）・Spike 001 が新 universe で代替検証完了 | 2026-06-28 |
| tech-debt | prediction-columns-doc-mismatch | PREDICTION_COLUMNS doc コメント 19列/20列 不整合（実体は20列で一貫・doc 陳腐化） | 2026-06-28 |

## Session Continuity

**Last session:** 2026-06-27T15:15:50.921Z

**Resume file:** 

None
Stopped at: Completed 12-01-PLAN.md (statsmodels + p_lower + migration)
Resume: `/gsd-execute-phase 9`（P04: SC#4 SAFE-01 AST audit + SC#5 ドメイン整合性可視化・rolling_speed_figure_* 6 feature を含む完成 feature_matrix が必要・本 P03 で生成可能に）

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone

## Accumulated Context

### Roadmap Evolution

- Phase 9.1 inserted after Phase 9: Speed Ability Profile Expansion (rolling speed figure 6-> expanded profile: median/best2/trend + same_surface/same_distance_bucket) (URGENT)
- Phase 9.1 completed after Phase 9: Speed Ability Profile Expansion 完了 (speed_figure 6→17 feature・snapshot 20260626-1a-speedprofile-v1・D-16 Phase 10 進行候補・3-way stopgate 比較)
