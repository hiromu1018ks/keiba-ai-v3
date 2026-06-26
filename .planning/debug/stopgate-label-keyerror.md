---
slug: stopgate-label-keyerror
status: resolved
trigger: "09-05 SC#6 stop gate が pred_df['fukusho_hit_validated'] で KeyError (Phase 5 label/market/refund 統合不足)"
created: 2026-06-26
updated: 2026-06-26
related_phase: "09"
related_plan: "09-05"
resolves_todo: ".planning/todos/pending/260626-09-05-stopgate-completion.md"
tags: [stop-gate, sc6, phase5-integration, label, market, refund]
---

# Debug: 09-05 SC#6 stop gate label KeyError

## 症状 (Symptoms)

- **再現**: `KEIBA_SKIP_DB_TESTS= uv run python scripts/run_speed_figure_stopgate.py`
- **成功**: 学習 (baseline/speed_figure model_version 採番) ・ JODDS market JOIN (rows=22793)
- **失敗**: `_evaluate_and_decide` L721 で `baseline_pred["fukusho_hit_validated"]` が **KeyError**
- **結果**: `reports/09-stopgate.{md,json}` 未生成

## 根因 (Root Cause・既特定・原因究明不要)

`orchestrator.train_and_predict` の `pred_df` は `p_fukusho_hit` + test index + meta(`race_start_datetime`/`race_key`) のみで label (`fukusho_hit_validated`) を保持しない (orchestrator.py L566/L593-603)。09-05 スクリプトが pred_df に label がある前提で書かれていた。Phase 5 (`scripts/run_backtest.py`) の label/market/refund/payout 統合 idiom を不十分に実装。

## Current Focus

- **hypothesis**: Phase 5 idiom (label JOIN + HARAI race-level merge + `_attach_accounting`/`_zero_out_non_selected_accounting`) を stopgate スクリプトに移植すれば KeyError が解消し refund/payout が正しく算出される。
- **test**: `KEIBA_SKIP_DB_TESTS= uv run python scripts/run_speed_figure_stopgate.py` が完走し `reports/09-stopgate.{md,json}` が生成される。合成テスト 9 GREEN 維持。
- **next_action**: ヘルパー追加 (_fetch_harai_race_level / _prepare_label_for_join / _attach_label_and_harai / _attach_stopgate_accounting) + _compute_selected_roi 拡張 + main 統合。

## 修正計画 (残作業ステップ)

1. pred_df へ label JOIN (`fukusho_hit_validated` + refund フラグ群・`on=['race_key','umaban']`)
2. HARAI race-level merge (`payfukusyoumaban*`/`payfukusyopay*`/`fuseirituflag2`/`tokubaraiflag2`)
3. refund_accounting 統合 (`determine_stake_payout`・selector ev>=1.0・non-selected ゼロ化)
4. `_compute_selected_roi` 拡張 (accounted 優先・近似フォールバック・テスト互換)
5. 完全 stop gate 実行・D-16 判定・reports 生成

## 制約 (聖域)

- §15.2 事前登録指標不変: binning 定数 import 再利用・再定義禁止 (bit-identical)
- REVIEW H2/H7/H8: orchestrator.train_and_predict 経由・生 trainer 直接呼出禁止
- REVIEW H-new: snapshot_id= keyword (両 snapshot)
- REVIEW H6: fuku_odds_lower (誤略称 fukuodds でない)
- REVIEW M4: _sanitize_for_json (NaN/Inf 安全化・json.dumps allow_nan=False)
- SAFE-01 odds-free: market_implied 診断層のみ・FEATURE_COLUMNS/model_p 入力に混入させない
- 合成テスト 9 GREEN 維持: tests/model/test_speed_figure_stopgate.py
- statement_timeout='30s'・dsn_masked・readonly pool try/finally (live-DB safety)

## Evidence

- timestamp: 2026-06-26 09:27 — live-DB 実行 exit 0・reports/09-stopgate.{md,json} 生成完了
- HARAI race-level 取得 (2023): 3456 races
- label JOIN 前処理 (test 2023): 47672 rows
- baseline/speedfig JODDS JOIN: rows=22793 (each)
- pred_df 完全化 (label+HARAI+accounting): baseline selected=5621 / speedfig selected=6247
- 合成テスト 9 GREEN (format 適用後も維持)

## Resolution

- **root_cause**: `orchestrator.train_and_predict` の `pred_df` は `p_fukusho_hit` + meta(`race_start_datetime`/`race_key`) のみで label (`fukusho_hit_validated`) を保持しない (orchestrator.py L566/L593-603)。09-05 が pred_df に label がある前提で書かれていた。
- **fix**: Phase 5 idiom (`run_backtest.py` L601-650 / L487-547 / L1333-1359) を stopgate スクリプトに inline 移植:
  1. `_fetch_harai_race_level` (HARAI race-level・year filter 付き・statement_timeout 安全)
  2. `_prepare_label_for_join` (label に `make_race_key` 付与 + test 期間 filter・§19.1 聖域)
  3. `_attach_label_and_harai` (label JOIN on race_key+umaban + HARAI race-level merge validate='many_to_one'・CR-06 `_label` suffix 衝突解決)
  4. `_attach_stopgate_accounting` (selector EV>=1.0 + `determine_stake_payout` selected のみ apply + non-selected ゼロ化)
  5. `_compute_selected_roi` 拡張 (accounted 優先 `sum(payout)/sum(effective_stake)`・近似フォールバックで 9 tests GREEN 維持)
  6. `SELECTED_EV_THRESHOLD` 定数 (selector 閾値の single source of truth・silent ROI 歪み回避)
- **verification**:
  - live-DB 実行 exit 0・`reports/09-stopgate.{md,json}` 生成
  - D-16 verdict: **特徴量追加の有効性シグナルあり・Phase 10 進行候補**
  - 指標1 selected calibration: baseline 0.0973 → speed_figure 0.0906 (improved)
  - 指標2 selected ROI (accounted): baseline 0.7018 (n=5621) → speed_figure 0.8956 (n=6247)
  - 指標3 global metrics: Brier -0.0004 / LogLoss -0.0019 / AUC +0.0054 (non_degraded)
  - 指標4 + D-15 residual proxy: signal_present=True, n_valid_cells=94
  - 合成テスト 9 GREEN 維持・聖域 (§15.2 binning 不変/H2/H7/H8/H-new/H6/M4/SAFE-01) 全保持
- **files_changed**: `scripts/run_speed_figure_stopgate.py` (+288/-15・ruff format 適用で既存 if 文 117字>100 の拆れ含む・技術債是正)
- **todo 達成**: `.planning/todos/pending/260626-09-05-stopgate-completion.md` の完了条件 1-4 全達成
