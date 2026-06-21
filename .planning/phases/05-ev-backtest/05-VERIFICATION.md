---
phase: 05-ev-backtest
verified: 2026-06-21T11:30:00Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 3
overrides_applied: 0
re_verification:
  previous_status: verified
  previous_score: "(automated block GREEN と主張・E2E smoke 25 backtest 完走と主張)"
  gaps_closed:
    - "Critical 8 件（CR-01..08）は 05-REVIEW-FIX.md で全て修正コミット済み（commits 1fc0c71/28e3091/67dc536/f87b617/66ab31f/54c3451/eb495ae/3582964 等）"
    - "Warning 10 件（WR-01..09/11）も修正済み（WR-10/12 は v1 scope 外で明示的に skip）"
  gaps_remaining: []
    # 回帰バグは orchestrator が commit 8e557d9 で解消（run_backtest.py:656 変数誤参照修正・E2E 14件 green・reports/05-backtest 再生成・主要テスト 126 passed）
  regressions:
    - "前回 VERIFICATION.md は「合成データフル行列 smoke 25 backtest 完走・reports 生成」を主張したが・修正後のコード（10:28）では test_synthetic_full_matrix_smoke が KeyError: 'selected_flag' で停止し reports は再生成されない。reports/05-backtest.{md,json}（09:14）は修正前の stale 状態。"
gaps:
  - truth: "合成データ E2E: JODDS mock + label mock + HARAI mock で run_backtest --synthetic がフル行列を完走・reports/05-backtest 生成（実JODDS未完でも検証可能）"
    status: resolved
    resolution: "orchestrator commit 8e557d9 — CR-03 回帰修正（run_backtest.py:656 _attach_accounting(full_candidate) に修正）・E2E 14件 green・reports/05-backtest 再生成（25 backtest）・主要テスト 126 passed"
    reason: "CR-03 修正（commit f87b617・merge 順序を snapshot→HARAI→label→compute_ev_and_rank→select_bets に入れ替え）の回帰バグ。scripts/run_backtest.py:656 が _attach_accounting(full_candidate_with_label) を呼ぶが・selected_flag 列を付与したのは full_candidate（641-650行）のため・_zero_out_non_selected_accounting:532 が out[\"selected_flag\"] にアクセスして KeyError: 'selected_flag' で停止。test_synthetic_full_matrix_smoke を含む E2E test 6件 FAILED で実証済み（8 passed / 6 failed）。reports/05-backtest.{md,json} は修正前（09:14）の stale 状態で・現在のコード（10:28）では再生成されない。"
    artifacts:
      - path: "scripts/run_backtest.py"
        issue: "560-661 _run_main_model_backtest: 656行が _attach_accounting(full_candidate_with_label) だが・641-650行で selected_flag を付与したのは full_candidate。変数名の誤参照（copy-paste ミス）により selected_flag 列が _attach_accounting 入力に伝播しない。"
      - path: "reports/05-backtest.md"
        issue: "mtime 09:14:41 は CR-03 修正コミット f87b617（それ以降）より前。現在のコードでは reports は生成されないため stale。"
      - path: "reports/05-backtest.json"
        issue: "同上（mtime 09:14:41・stale）"
    missing:
      - "scripts/run_backtest.py:656 を _attach_accounting(full_candidate) に修正（変数名誤参照の解消）。これにより selected_flag 列が _attach_accounting → _zero_out_non_selected_accounting に伝播し E2E smoke が完走する。"
      - "修正後に `uv run pytest tests/ev/test_run_backtest_e2e.py -q` で 14件全て PASSED になることを確認。"
      - "修正後に `uv run python scripts/run_backtest.py --synthetic` で reports/05-backtest.{md,json} を再生成し mtime を更新。"
behavior_unverified_items:
  - truth: "BACK-04: reports/05-backtest.{md,json} が全25候補を一括報告（後知恵 winner 単独報告禁止・主モデル確定は Phase 6）"
    test: "test_synthetic_full_matrix_smoke 完走後・生成された reports/05-backtest.md に「推奨: BT-X」記述が無いことを `grep -c '推奨:' reports/05-backtest.md` == 0 で確認"
    expected: "winner 強調行が存在しないこと（BACK-04 odds policy 固定・no hindsight）"
    why_human: "現在の reports は stale（修正前）で再生成不能なため・回帰バグ修正後に再検証が必要。grep で自動判定可能だが前提として E2E smoke の完走が必要。"
  - truth: "WR-06 特払 (tokubarai) 処理の slot1 無条件参照を安全側フォールバックに修正（commit 3582964）"
    test: "JRA 特払公式ルールを確認し・payfukusyoumaban1..5 が全て '00' の場合のみ特払扱いとする仕様が正しいか・'05' 等 slot1 馬番が入った場合は通常中り扱いにフォールバックする仕様が JRA ルールと整合するか確認"
    expected: "JRA 公式ルールと一致すること"
    why_human: "JRA 特払公式ルールの最終確認は doc 参照が必要（REVIEW-FIX.md も「requires human verification」と明記）"
  - truth: "D-03 BT窓再学習: scripts/run_backtest.py が BT_WINDOWS × {30min,10min} × {lightgbm,catboost} ≈ 20 backtest + 5 BL-3 = 25 backtest フル行列を実行"
    test: "回帰バグ修正後に `uv run python scripts/run_backtest.py --synthetic` を実行し 25 backtest が完走することを確認"
    expected: "SUMMARY: 全 backtest 行=25 (主モデル 20 + BL-3 5)"
    why_human: "現在の回帰バグで停止するため・修正後に完走確認が必要（合成データ E2E truth の復旧と同時に検証）"
human_verification:
  - test: "実データ backtest 実行（BT期間 2019-2025）"
    expected: "JODDS 取得完了後・`uv run python scripts/run_backtest.py`（--synthetic 外す・--snapshot-id=20260620-1a-postreview-v2）で BT-1..5 フル行列が完走し実データ版 reports/05-backtest.{md,json} が生成される。`_assert_jodds_coverage_horse_level` gate が candidate-horse usable-odds coverage < 0.90 で RuntimeError で loud fail すること。"
    why_human: "JODDS 取得進行中のため現時点では実行不能（manual-only 分離・PLAN/VALIDATION と整合）。回帰バグ修正後に JODDS 取得完了を待って実行。"
  - test: "全25候補一括報告の目視（後知恵 winner 強調なし）"
    expected: "実データ版 reports/05-backtest.md に「推奨: BT-X」記述が無いこと（主モデル確定は Phase 6 D-03/D-04 事前登録選定基準）"
    why_human: "報告フォーマットの「推奨」記述欠如を目視。前提として回帰バグ修正 + reports 再生成が必要。"
overrides:
  - must_have: "実データ backtest（BT期間 2019-2025）は JODDS 取得完了後の manual-only 検証として明示分離（VALIDATION.md Manual-Only と整合）"
    reason: "Phase 5 自動化部分は構造的ブロック GREEN を合成データで実証。実データ backtest は外部依存（JODDS 取得）で Phase 5 スコープ外の時期分離。PLAN 05-06 と VALIDATION.md Manual-Only で明示的に設計された分離。本 truth は goal 達成の BLOCKER でなく Phase 5 完了後の運用タスク。"
    accepted_by: "hart"
    accepted_at: "2026-06-21T11:30:00Z"
---

# Phase 5: EV & Backtest Verification Report

**Phase Goal:** The honest verdict — EV/rank computation against a fixed `odds_snapshot_policy`, and a race_id-grouped time-series virtual-purchase backtest with refund/scratch/dead-loss accounting that cannot be inflated by hindsight odds selection（race_id 単位・時系列順の再現可能バックテストで過小評価馬の複勝払戻対象入り可能性を定量評価）
**Verified:** 2026-06-21T11:30:00Z
**Status:** gaps_found
**Re-verification:** Yes — 前回 VERIFICATION.md（2026-06-21・status: verified）の再検証。Critical 8 件修正後に新規発見された回帰バグにより gaps_found に格下げ。

---

## 重要な状況更新（前回 VERIFICATION.md からの差分）

前回 VERIFICATION.md（2026-06-21 09:33）は Phase 5 自動化部分を `verified` と判定した。しかし今回の再検証で以下の事実が判明した:

1. **05-REVIEW.md の Critical 8 件（CR-01..08）と Warning 10 件は 05-REVIEW-FIX.md で全て修正コミット済み**（commits 1fc0c71/28e3091/67dc536/f87b617/66ab31f/54c3451/eb495ae/3582964 等・2026-06-21）。`<phase_context>` の「Critical 5 件は別セッションで修正」という前提は既に満たされている。
2. **しかし CR-03 修正（commit f87b617・merge 順序入れ替え）で新規の回帰バグが導入された**。`scripts/run_backtest.py:656` が `_attach_accounting(full_candidate_with_label)` を呼ぶが・641-650行で `selected_flag` 列を付与したのは `full_candidate`（別変数）のため・`_zero_out_non_selected_accounting:532` が `out["selected_flag"]` にアクセスして `KeyError: 'selected_flag'` で停止する。
3. **E2E テスト 14件中 6件 FAILED** で実証（`test_synthetic_full_matrix_smoke` / `test_report_all_candidates_format` / `test_report_no_winner_override` / `test_report_strategy_version_stamp` / `test_report_bl3_caveat_present` / `test_report_columns_present`）。うち 5件は `test_synthetic_full_matrix_smoke` の失敗に依存する report 系テスト。
4. **reports/05-backtest.{md,json} は mtime 09:14:41（CR-03 修正前）で stale**。現在のコード（mtime 10:28:07）では再生成不能。前回 VERIFICATION.md の「合成データフル行列 smoke 25 backtest 完走・reports 生成」主張は現在のコードで再現しない。
5. **修正は 1行**（`_attach_accounting(full_candidate_with_label)` → `_attach_accounting(full_candidate)`）で完了する軽微な回帰バグだが・**現状のコードでは must_have truth「合成データ E2E smoke 完走」が FAILED** のため status は gaps_found とする。

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **EV-01**: EV_lower = p × odds_lower / EV_upper = p × odds_upper を pandas Series 演算で算出 | ✓ VERIFIED | `src/ev/ev_rank.py:109-110` で `out["EV_lower"] = out["p_fukusho_hit"] * out["fuku_odds_lower"]` / `EV_upper` 同様。純粋関数・NaN 伝播。test_ev_rank.py 23件 green。 |
| 2 | **EV-02**: 推奨ランク S/A/B/C/D を EV/確率/odds_lower のみで階層判定（未定義の予測信頼度不使用） | ✓ VERIFIED | `src/ev/ev_rank.py:15-31` で `RANK_RULES = {"S": {ev_lower_min:1.20, p_min:0.25, odds_lower_min:1.5}, "A":..., "B":..., "C":...}`。信頼度列は参照せず。 |
| 3 | **BACK-01**: BT-1..5 窓が race_date filter + 既存 guard（race_id disjoint + strict chronological）で (train_race_ids, test_race_ids) を返す | ✓ VERIFIED | `src/utils/group_split.py:165` BTWindow dataclass / :239 `get_bt_race_ids` / `race_id_time_series_split` と同一3ガード。test_group_split.py green。 |
| 4 | **BACK-02**: 仮想購入ルール fukusho_ev_v1（EV_lower≥1.05, p≥0.15, odds_lower≥1.5, top-2/race, 100円, 複勝のみ） | ✓ VERIFIED | `src/ev/purchase_simulator.py:30-40` FUKUSHO_EV_V1_STRATEGY="fukusho_ev_v1" / `select_bets` でフィルタ+groupby head(2)。test_purchase_simulator.py green。 |
| 5 | **BACK-03**: 返還会計決定表（6シナリオ）: 取消/除外/不成立/レース中止=effective_stake=0・競走中止=effective_stake=100 | ✓ VERIFIED | `src/ev/refund_accounting.py` determine_stake_payout 6シナリオ分岐。test_refund_accounting.py 30件 green。WR-03/06 修正済み（commit 16519be/3582964）。 |
| 6 | **BACK-04**: odds_snapshot_policy は 30min_before/10min_before 固定・merge_asof(direction='backward', by=['race_key','umaban']) | ✓ VERIFIED | `src/ev/odds_snapshot.py` select_odds_snapshot・CR-01 修正済み（make_race_key 正準形式・commit 28e3091）・WR-08/11 修正済み。test_odds_snapshot.py green。 |
| 7 | **§11.6**: 回収率/P/L/max DD/selected_count/effective_bet_count/refund_count を backtest_strategy_version 付きで計算 | ✓ VERIFIED | `src/ev/metrics.py:82-97` compute_backtest_metrics。run_backtest.py:687-689 で metrics を report 行に stamp。 |
| 8 | **D-04 BL-3**: 確定オッズ昇順 top-2 で固定ルール仮想購入 → 主モデル2つと回収率比較 | ✓ VERIFIED | `src/ev/bl3_betting.py` select_bl3_bets・ninki 昇順 top-2。scripts/run_backtest.py で BL-3 パス実装。test_bl3_betting.py green。 |
| 9 | **D-03 BT窓再学習**: scripts/run_backtest.py が BT_WINDOWS × {30min,10min} × {lightgbm,catboost} ≈ 20 + BL-3 5 = 25 backtest フル行列を実行 | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | コードは実装されている（scripts/run_backtest.py:1308行・BT_WINDOWS ループ）が・回帰バグ（#11 truth 参照）で現在停止するため完走未証明。修正後に再検証が必要。 |
| 10 | **A5 後方互換**: split_3way(periods=None) は Phase 4 と bit-identical | ✓ VERIFIED | `src/model/data.py:516-519` split_3way に periods パラメータ追加・periods=None で Phase 4 ハードコード区間。test_data.py / test_orchestrator.py 既存 green 維持（336 passed で確認）。 |
| 11 | **合成データ E2E**: JODDS mock + label mock + HARAI mock で run_backtest --synthetic がフル行列を完走・reports/05-backtest 生成 | ✗ FAILED | **回帰バグ**: scripts/run_backtest.py:656 が `_attach_accounting(full_candidate_with_label)` を呼ぶが・641-650行で `selected_flag` を付与したのは `full_candidate`。`_zero_out_non_selected_accounting:532` が `out["selected_flag"]` で `KeyError: 'selected_flag'`。E2E test 6件 FAILED（test_synthetic_full_matrix_smoke 含む）で実証。reports/05-backtest.{md,json} は stale（mtime 09:14・修正前）。 |
| 12 | **§19.1 stamp**: 各 backtest 行に backtest_strategy_version='fukusho_ev_v1' / odds_snapshot_policy / train_period / test_period / model_type / model_version | ✓ VERIFIED | BACKTEST_TABLE_DDL に `CHECK (backtest_strategy_version = 'fukusho_ev_v1')` 制約（src/db/schema.py:160）。run_backtest.py:670 _attach_provenance で全 stamp 付与。backtest_load.py で永続化。 |

**Score:** 11/12 truths verified（1 behavior_unverified・1 failed）

### Deferred Items

該当なし。実データ backtest は Phase 5 完了後の運用タスク（manual-only 分離・overrides で処理）。後続 Phase 6（Evaluation & Calibration Gates）は backtest 数値ではなく Calibration 指標が主対象で・本 gap の対象外。

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ev/ev_rank.py` | compute_ev_and_rank / _rank | ✓ VERIFIED | 113行・EV_lower/upper・rank S/A/B/C/D・RANK_RULES dict |
| `src/ev/purchase_simulator.py` | select_bets — fukusho_ev_v1 | ✓ VERIFIED | 114行・FUKUSHO_EV_V1_STRATEGY・フィルタ+groupby head(2) |
| `src/ev/metrics.py` | compute_backtest_metrics — §11.6 | ✓ VERIFIED | 107行・回収率/P/L/max DD/selected_count/effective_bet_count/refund_count |
| `src/ev/bl3_betting.py` | select_bl3_bets — 確定オッズ昇順 top-2 | ✓ VERIFIED | 100行・ninki 昇順・BL3_BETTING_CAVEAT |
| `src/ev/odds_snapshot.py` | select_odds_snapshot + JODDS/HARAI クエリ | ✓ VERIFIED | 338行・make_race_key 正準形式（CR-01 fix）・backward as-of・NaN 除外（WR-08）・raise RuntimeError（WR-11） |
| `src/ev/refund_accounting.py` | determine_stake_payout + _lookup_payfukusyo_pay | ✓ VERIFIED | 177行・6シナリオ分岐・特払 slot1 安全側フォールバック（WR-06 fix） |
| `src/ev/report.py` | generate_report — 全候補一括報告 | ✓ VERIFIED | 307行・REPORT_COLUMNS・BL3_BETTING_CAVEAT・winner 強調禁止 |
| `src/utils/group_split.py` | BTWindow / BT_WINDOWS / get_bt_race_ids | ✓ VERIFIED | 318行・BTWindow dataclass・:239 get_bt_race_ids・race_id_time_series_split と同一3ガード |
| `scripts/run_backtest.py` | BT窓再学習 + フル行列 25 backtest + reports 生成 CLI | ✗ STUB(回帰) | 1308行・構造は実装済みだが・:656 の変数誤参照で _run_main_model_backtest が KeyError 停止。フル行列完走不能（test_synthetic_full_matrix_smoke FAILED）。 |
| `src/db/backtest_load.py` | load_backtest — backtest_id scoped staging-swap | ✓ VERIFIED | 469行・pg_advisory_xact_lock・TRUNCATE staging・backtest_id scope DELETE・INSERT・checksum |
| `src/db/schema.py` | BACKTEST_TABLE_DDL + GRANT + APPLY_ORDER | ✓ VERIFIED | BACKTEST_TABLE_DDL:115・CHECK model_type IN ('lightgbm','catboost','bl3') + backtest_strategy_version='fukusho_ev_v1'・APPLY_ORDER に backtest_table エントリ |
| `src/model/orchestrator.py` | train_and_predict(split_periods, category_map) 拡張 | ✓ VERIFIED | split_periods パラメータ・_apply_category_map で category_map 適用・feature_df.copy() で CR-08/WR-07 fix |
| `src/model/data.py` | split_3way(periods) 拡張 | ✓ VERIFIED | :519 periods パラメータ追加・periods=None で Phase 4 ハードコード・A5 後方互換 |
| `reports/05-backtest.md` | Phase 5 フル行列 backtest 報告 | ⚠️ STALE | mtime 09:14:41（CR-03 修正前）。現在のコードでは再生成不能。回帰バグ修正後に再生成が必要。 |
| `reports/05-backtest.json` | 同 JSON 版 | ⚠️ STALE | 同上 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| tests/ev/test_group_split.py::test_bt_window_disjoint | src/utils/group_split.py::get_bt_race_ids | BT窓 race_id filter → 既存 guard 検証 | ✓ WIRED | get_bt_race_ids 呼出・test green |
| src/utils/group_split.py::BT_WINDOWS | scripts/run_backtest.py | `from src.utils.group_split import BT_WINDOWS` | ✓ WIRED | run_backtest.py で import・BT窓ループで消費 |
| src/ev/purchase_simulator.py::select_bets | src/ev/ev_rank.py::compute_ev_and_rank | select_bets は EV_lower/rank 付与済み df を受け取る | ✓ WIRED | run_backtest.py:636 compute_ev_and_rank → :640 select_bets |
| src/ev/bl3_betting.py | src/model/baseline.py::fetch_market_data / BL3_COMPARISON_CAVEAT | fetch_market_data で確定オッズ取得 | ✓ WIRED | BL3_BETTING_CAVEAT を report.py 経由で再利用 |
| src/ev/odds_snapshot.py::select_odds_snapshot | pandas.merge_asof(direction='backward', by=['race_key','umaban']) | race_key+umaban 単位 backward 最近接 | ✓ WIRED | select_odds_snapshot 内で merge_asof・CR-01 fix 後は正準 race_key で一致 |
| src/ev/refund_accounting.py::determine_stake_payout | label.fukusho_label + public.n_harai PayFukusyoPay | label フラグ一次・HARAI PayFukusyoPay で payout 確定 | ✓ WIRED | determine_stake_payout 内で is_dead_loss / is_scratch_cancel / PayFukusyoPay slot lookup |
| src/db/backtest_load.py::load_backtest | pg_advisory_xact_lock / TRUNCATE / scope DELETE | 11ステップ staging-swap | ✓ WIRED | load_backtest 内で advisory lock → staging TRUNCATE → INSERT → scope DELETE → checksum |
| src/model/orchestrator.py::train_and_predict | src/model/data.py::split_3way | split_periods パラメータ伝播 | ✓ WIRED | train_and_predict(split_periods=...) → split_3way(periods=split_periods) |
| src/model/orchestrator.py::train_and_predict | model 前処理（category dtype map） | category_map パラメータ伝播 | ✓ WIRED | _apply_category_map(category_map) で feature_df[code_col] を再構築（CR-08 fix で copy 済み） |
| scripts/run_backtest.py | src/model/orchestrator.py::train_and_predict(split_periods=...) | BT_WINDOWS ループで各窓 split_periods 注入 | ✓ WIRED | run_backtest.py で train_and_predict(split_periods=bt_periods) 呼出 |
| scripts/run_backtest.py | src/ev/{odds_snapshot,ev_rank,purchase_simulator,refund_accounting,metrics,bl3_betting,report}.py + src/db/backtest_load.py | EV→rank→purchase→refund→metrics→load→report フルパイプライン | ⚠️ PARTIAL | 全 import 存在するが・_run_main_model_backtest:656 の変数誤参照でパイプラインが _zero_out_non_selected_accounting で停止（KeyError） |
| scripts/run_apply_schema.py | src/db/schema.py::BACKTEST_TABLE_DDL | APPLY_ORDER 経由で CREATE TABLE | ✓ WIRED | run_apply_schema.py で BACKTEST_TABLE_DDL 適用・live-DB テーブル確認済み（前回 VERIFICATION 記載） |

### Data-Flow Trace (Level 4)

主要コンポーネントは純粋関数（ev_rank / purchase_simulator / metrics / refund_accounting）で・データフローは run_backtest.py のパイプライン経由。パイプラインが回帰バグで停止するため・現在のコードでは reports/05-backtest へのデータフローは DISCONNECTED。構造的には merge_asof(backward) / category_map BT-train-only / split_3way 完全時系列 / backtest_id scoped staging-swap / refund honest 会計は全て実装済み（code review でも「リーク防止聖域は正しく保持」と評価）。

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| フル pytest suite（E2E 以外） | `uv run pytest -q --ignore=tests/ev/test_run_backtest_e2e.py` | 336 passed, 3 warnings in 344s | ✓ PASS |
| E2E suite | `uv run pytest tests/ev/test_run_backtest_e2e.py -v` | 8 passed / 6 failed | ✗ FAIL |
| 合成データフル行列 smoke | `uv run python scripts/run_backtest.py --synthetic`（E2E test 経由で実証） | KeyError: 'selected_flag' で停止 | ✗ FAIL |
| snapshot parquet 存在 | `ls snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` | 38M・存在（REVIEW-FIX.md の FileNotFoundError 報告は不正確） | ✓ PASS |
| EV_lower 計算ロジック | grep `out["EV_lower"] = out["p_fukusho_hit"] * out["fuku_odds_lower"]` src/ev/ev_rank.py | :109 で実装 | ✓ PASS |
| BACKTEST_TABLE_DDL CHECK 制約 | grep `backtest_strategy_version = 'fukusho_ev_v1'` src/db/schema.py | :160 で実装 | ✓ PASS |

### Probe Execution

該当なし（本プロジェクトは scripts/*/tests/probe-*.sh 形式の probe を持たない・pytest が唯一の自動検証）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EV-01 | 05-02 | EV_lower/upper = p × odds 算出 | ✓ SATISFIED | src/ev/ev_rank.py:109-110・test_ev_rank.py green |
| EV-02 | 05-02 | 推奨ランク S/A/B/C/D を EV/確率/odds_lower のみで算出 | ✓ SATISFIED | src/ev/ev_rank.py:15-31 RANK_RULES・信頼度列不参照 |
| BACK-01 | 05-01/05/06 | race_id 単位 + race_date 昇順分割・train/test またぎ禁止 | ✓ SATISFIED | src/utils/group_split.py:165 BTWindow / :239 get_bt_race_ids・race_id disjoint guard |
| BACK-02 | 05-02/05/06 | 固定ルール（EV_lower≥1.05, p≥0.15, odds_lower≥1.5, top-2, 100円, 複勝）仮想購入 | ✓ SATISFIED | src/ev/purchase_simulator.py・FUKUSHO_EV_V1_STRATEGY・select_bets |
| BACK-03 | 05-03/04/05/06 | 返還 effective_stake=0・競走中止=100・回収率等を backtest_strategy_version 付きで計算 | ✓ SATISFIED | src/ev/refund_accounting.py・determine_stake_payout 6シナリオ・src/ev/metrics.py・backtest_strategy_version='fukusho_ev_v1' CHECK 制約 |
| BACK-04 | 05-03/05/06 | odds_snapshot_policy 固定（30/10min）・no_bet・全候補一括報告 | ✓ SATISFIED（構造） | src/ev/odds_snapshot.py・merge_asof backward・odds_missing_policy=no_bet・report.py 全候補一覧。ただし実データ backtest 数値検証は manual-only 分離（overrides 参照）。 |

全 6 要件とも構造的実装は SATISFIED。ただし BACK-04 の「全候補一括報告」目視検証は回帰バグ修正 + reports 再生成後に必要（behavior_unverified_items #1 参照）。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| scripts/run_backtest.py | 656 | 変数誤参照: _attach_accounting(full_candidate_with_label) だが selected_flag は full_candidate に付与 | ✓ Resolved (8e557d9) | 修正後 E2E 14件 green・reports 再生成 |
| （なし） | - | TODO/FIXME/XXX/TBD マーカー | - | 全成果物でゼロ（grep 検証済み） |
| （なし） | - | placeholder/stub 実装 | - | 全成果物でゼロ（grep 検証済み） |

### Critical/Warning Code Review 修正状況

**05-REVIEW.md の Critical 8 件 + Warning 12 件** は 05-REVIEW-FIX.md で以下の通り処理済み:

| ID | 重大度 | 状態 | 備考 |
|----|--------|------|------|
| CR-01 race_key 形式不整合 | Critical | ✓ fixed (28e3091) | make_race_key 正準形式に統一 |
| CR-02 load_labels race_key 欠落 | Critical | ✓ fixed (67dc536) | label_df に make_race_key で race_key 付与 |
| CR-03 select_bets 呼出順序 | Critical | ✓ fixed (f87b617) **ただし回帰バグ導入** | merge 順序入れ替え自体は正しいが・:656 の _attach_accounting 引数誤りで E2E 停止 |
| CR-04 BL-3 market_df race_date 欠落 | Critical | ✓ fixed (66ab31f) | market_df に race_key/race_date/sale_available 補完 |
| CR-05 %.2%% フォーマット | Critical | ✓ fixed (1fc0c71) | %.2f%% に修正 |
| CR-06 HARAI/label merge suffix 重複 | Critical | ✓ fixed (f87b617) | suffixes=('_left','_label') |
| CR-07 _filter_label_by_period 型混在 | Critical | ✓ fixed (54c3451) | pd.to_datetime 正規化 + silent fallback 廃止 |
| CR-08 _apply_category_map in-place | Critical | ✓ fixed (eb495ae) | feature_df.copy() 追加 |
| WR-01..09/11 | Warning | ✓ fixed | 各コミット参照 |
| WR-06 特払 slot1 | Warning | ⚠️ fixed・要 human verify | JRA 特払公式ルール最終確認推奨（behavior_unverified_items #2） |
| WR-10/12 性能（apply axis=1） | Warning | ⊘ skipped | v1 scope 外・Phase 6 で対応（REVIEW 自身が許容） |

### Human Verification Required

#### 1. 実データ backtest 実行（BT期間 2019-2025）

**Test:** JODDS 取得完了後・`uv run python scripts/run_backtest.py`（`--synthetic` 外す・`--snapshot-id=20260620-1a-postreview-v2`）を実行。
**Expected:** BT-1..5 フル行列が完走し実データ版 reports/05-backtest.{md,json} が生成される。`_assert_jodds_coverage_horse_level` gate が candidate-horse usable-odds coverage < 0.90 で RuntimeError を raise し・取得未完での誤実行を loud fail で防止する。
**Why human:** JODDS 取得進行中（2026-06-20 開始・2015年25レース日分のみ）のため現時点では実行不能。PLAN 05-06 と VALIDATION.md Manual-Only で明示的に分離された運用タスク。前提として回帰バグ（#11 truth）の修正が必要。

#### 2. 全25候補一括報告の目視（後知恵 winner 強調なし）

**Test:** 実データ版 reports/05-backtest.md に「推奨: BT-X」記述が無いことを確認（`grep -c '推奨:' reports/05-backtest.md` == 0）。
**Expected:** winner 強調行が存在しないこと（BACK-04・主モデル確定は Phase 6 D-03/D-04 事前登録選定基準・Calibration 重視）。
**Why human:** 報告フォーマットの「推奨」記述欠如を目視。合成データ版では既に grep == 0 を実証済みだが・実データ版の目視が必要。前提として回帰バグ修正 + reports 再生成が必要。

### Gaps Summary

Phase 5 自動化部分の構造的ブロック（EV-01/02/BACK-01..04 の純粋関数・リーク防止聖域・スキーマ・永続化）は**全て実装され wiring 済み**。Critical 8 件 + Warning 10 件のコードレビュー指摘も**全て修正コミット済み**。ただし **CR-03 修正（merge 順序入れ替え・commit f87b617）で 1行の変数誤参照による回帰バグが導入され**・`scripts/run_backtest.py:656` が `_attach_accounting(full_candidate_with_label)` を呼ぶことで `selected_flag` 列が伝播せず・`_zero_out_non_selected_accounting:532` で `KeyError: 'selected_flag'` で停止する。

これにより must_have truth「合成データ E2E: run_backtest --synthetic がフル行列を完走・reports/05-backtest 生成」が FAILED。E2E test 14件中 6件 FAILED（うち 5件は report 系で test_synthetic_full_matrix_smoke に依存）で実証。reports/05-backtest.{md,json} は修正前の stale 状態。

修正は 1行（`_attach_accounting(full_candidate_with_label)` → `_attach_accounting(full_candidate)`）で完了する軽微な回帰バグ。修正後に E2E 14件全て green・フル pytest suite 350 passed に戻り・reports が再生成されれば Phase 5 は passed に格上げ可能。本 gap は Phase 5 自身の完了条件であり・後続 Phase への deferred ではない。

実データ backtest は引き続き manual-only 分離（overrides 登録済み）で・JODDS 取得完了後の運用タスク。

### Re-verification: PASSED（2026-06-21・orchestrator）

CR-03 回帰バグは orchestrator が commit 8e557d9 で解消:
- `run_backtest.py:656` を `_attach_accounting(full_candidate)` に修正（selected_flag / odds_missing_reason 伝播）
- E2E test 14件 green（`test_synthetic_full_matrix_smoke` 含む）
- `reports/05-backtest.{md,json}` 再生成（25 backtest・BACK-04 `grep -c '推奨:'` == 0）
- 主要テスト 126 passed / 7 skipped（KEIBA_SKIP_DB_TESTS=1・回帰なし）

Phase 5 は 12/12 must-haves verified で **passed**。実データ backtest は引き続き manual-only（JODDS 取得完了後）。

---

_Verified: 2026-06-21T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes（前回 verified から gaps_found に格下げ・CR-03 修正の回帰バグ発見）_
