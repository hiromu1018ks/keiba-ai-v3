---
phase: 12
plan: 02
subsystem: orchestrator p_lower integration + EV layer p_lower switch (C-12-02-1..5)
tags: [model, orchestrator, ev, p-lower, wave2, ev-01, safe-01, artifact, byte-reproducible]
requires:
  - "Phase 12 Plan 01 (compute_p_lower_conformal_shrinkage + PREDICTION_COLUMNS 20列 + statsmodels==0.14.6)"
  - "Phase 11 race-relative model (apply_race_relative_correction・theta=1.0・score_split guard)"
provides:
  - "orchestrator.train_and_predict L754 後 p_lower 生成ブロック (theta is not None 分岐内・calib slice のみ)"
  - "train_and_predict signature に p_lower_q_shrink/p_lower_q_level keyword-only 引数 (C-12-02-1 HIGH)"
  - "orchestrator return dict に p_lower_q_level/q_shrink/shrinkage_method provenance (§19.1)"
  - "artifact.save_native_artifact に p_lower 3キー keyword-only 引数 + metadata.json 記録"
  - "artifact.write_metadata_json の allow_nan=False 厳密化 (C-12-02-5・NaN → ValueError)"
  - "ev_rank.compute_ev_and_rank に p_col keyword-only 引数 (D-03 入力列差し替え)"
  - "ev_rank._rank に p_col 伝播 (C-12-02-3・EV 計算と rank 条件の確率基準一致)"
  - "purchase_simulator.select_bets に p_col/p_min_base keyword-only 引数 (Pitfall 7 事前登録)"
  - "report.REPORT_COLUMNS_PHASE12 + generate_report report_columns 切替 (C-12-02-4・既存 regression なし)"
affects:
  - "Plan 03: src/eval/falsification.py が statsmodels + q_shrink 経路を消費"
  - "Plan 04: scripts/run_phase12_evaluation.py が p_lower_q_shrink 外部注入・EV 計算 p_col 切替を統合"
  - "Plan 05: 対抗的監査 test_audit_p_lower_falsification.py が SAFE-01 AST を拡張"
tech_stack:
  added: []
  patterns:
    - "orchestrator L754 後の p_lower 生成 (calib slice のみ score_split='calib'・外部注入 score_split='test')"
    - "[C-12-02-1 HIGH] keyword-only signature で q_shrink 外部注入 API を構造化 (§11.2 聖域の機械保証)"
    - "[C-12-02-1 HIGH] score_split='test' + theta + p_lower_q_shrink=None → RuntimeError (fail-loud)"
    - "return dict + artifact metadata の3キー provenance (race_relative_theta idiom と同一・§19.1)"
    - "[C-12-02-5] artifact.write_metadata_json allow_nan=False (RFC 8259 strict・NaN → ValueError)"
    - "[C-12-02-3] _rank p_col 伝播 (EV 計算と rank 条件の確率基準一致・投票層定義分裂回避)"
    - "[C-12-02-4] Phase 12 専用 reports 分離 (REPORT_COLUMNS_PHASE12 + generate_report report_columns 切替)"
    - "silent fallback 禁止 (pred_proba_lower index/長さ不整合 → RuntimeError・Shared Pattern 4)"
    - "byte-reproducible (mergesort sort・np.array_equal 2回呼出・seed 非依存)"
key_files:
  created:
    - "tests/model/test_orchestrator_p_lower.py (EV-01 unit・Test 1-12・12 テスト)"
    - "tests/ev/test_ev_p_lower.py (EV-01 unit・Test 1-8・10 テスト)"
  modified:
    - "src/model/orchestrator.py (signature 拡張 + L754 後 p_lower 生成ブロック + return dict + import)"
    - "src/model/artifact.py (write_metadata_json allow_nan=False + save_native_artifact signature/metadata)"
    - "src/ev/ev_rank.py (_rank p_col・compute_ev_and_rank p_col)"
    - "src/ev/purchase_simulator.py (select_bets p_col/p_min_base)"
    - "src/ev/report.py (REPORT_COLUMNS_PHASE12 + generate_report report_columns・_format_comparison_table_md)"
decisions:
  - "[C-12-02-1 HIGH] p_lower_q_shrink/p_lower_q_level を keyword-only で signature に追加・test 窓外部注入 API を構造化"
  - "[C-12-02-1 HIGH] score_split='test' + theta is not None + p_lower_q_shrink is None → RuntimeError で fail-loud (§11.2 聖域)"
  - "[C-12-02-5] artifact.write_metadata_json を allow_nan=False で厳密化 (NaN の JSON 化を ValueError で検出)"
  - "[C-12-02-3] _rank に p_col を伝播し EV 計算と rank 条件の確率基準を一致 (投票層定義分裂回避)"
  - "[C-12-02-4] Phase 12 専用 reports を REPORT_COLUMNS_PHASE12 + report_columns 引数で分離 (既存 REPORT_COLUMNS 不変・Phase 5 regression 回避)"
  - "purchase_simulator p_min_base='p_lower' を Phase 12 評価のデフォルト経路に事前登録 (Pitfall 7)"
  - "silent fallback 禁止: pred_proba_lower index/長さ不整合は RuntimeError (Shared Pattern 4)"
metrics:
  duration: 40min
  completed: "2026-06-27"
  tasks: 2
  files: 7
  tests_added: 22
status: complete
---

# Phase 12 Plan 02: orchestrator p_lower 統合 + EV 層 p_lower 切替 Summary

Phase 12 Wave 2: Plan 01 の `compute_p_lower_conformal_shrinkage` 純粋関数と `PREDICTION_COLUMNS` 拡張を消費し・orchestrator L754（race-relative 補正後）で calib slice のみ q_shrink を計算して `p_fukusho_hit_lower` を生成する経路を確立した。EV 層（ev_rank / purchase_simulator / report）の入力列を `p` から `p_fukusho_hit_lower` に差し替え可能にし・`p_min` を `p_lower` ベースで解釈する事前登録経路を整えた。聖域（§11.2・SAFE-01・byte-reproducible）を保ちつつ・theta=None/v1.0 binary 呼出は NULL・p_col 省略で従来 `p_fukusho_hit` ベース（A5 後方互換）。

## What Was Built

### Task 1: orchestrator L754 後 p_lower 生成 + q_shrink 外部注入 API（C-12-02-1 HIGH）+ artifact metadata allow_nan=False（C-12-02-5）

- **[C-12-02-1 HIGH] `train_and_predict` signature 拡張**: `p_lower_q_shrink: float | None = None` と `p_lower_q_level: float = 0.90` の2つの keyword-only 引数を追加（`*` 以降・L273-291 signature）。`p_lower_q_level=0.90` は D-02 事前登録値（test 窓で変更不可）。`p_lower_q_shrink` は `score_split='test'` 経路で呼出側（`run_phase12_evaluation.py`・Plan 04）から calib 済み q_shrink を外部注入する唯一の受取経路。
- **L754 後 p_lower 生成ブロック**（theta is not None 分岐内・RESEARCH.md Pattern 1・例1 完全呼出経路）:
  - **(a) score_split='calib' 経路**: X_score == X_calib なので・`compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final, q_level=p_lower_q_level)` で q_shrink を計算。構造的聖域ブロック（関数シグネチャが calib slice のみ・test 窓 outcome 系を取らない・Plan 01 で検証済み）。
  - **(b) score_split='test' 経路**: `theta is not None かつ p_lower_q_shrink is None` の場合に `RuntimeError` で fail-loud（test 窓 outcome を使った q_shrink 再計算経路への滑りを構造的に阻止）。`p_lower_q_shrink is not None` の場合は外部注入値を使い `max(0, p_final - q_shrink)` で p_lower を算出（§11.2 聖域・test 窓 outcome を使わない）。
  - **(c) theta=None/v1.0 binary**: p_lower=None（NULL・後方互換・`p_lower_q_shrink` は無視）。`pred_proba_lower_series = None` で `predict_p_fukusho` に渡り全行 NULL。
- **Shared Pattern 4 fail-loud**: `pred_proba_lower_series` と `pred_proba` の index/長さ不整合は `RuntimeError`（L700-704 と同一 idiom・silent wrong-horse p_lower 防止・Cycle 2 NEW HIGH-1 鏡像）。
- **[C-12-02-2 MEDIUM] pred_proba_lower 注入**: orchestrator L764-781 の `predict_p_fukusho` 呼出で `pred_proba_lower=pred_proba_lower_series` を注入（Plan 01 で predict.py 側に `pred_proba_lower` 引数は追加済み・本 Plan で呼出側を接続）。race-relative 経路（theta != None）は常に非 NULL・v1.0 binary 経路（theta=None・pred_proba_lower=None）は常に NULL を機械保証（C-12-01-4 鏡像）。
- **return dict provenance**: `p_lower_q_level: float | None`・`p_lower_q_shrink: float | None`・`p_lower_shrinkage_method: str | None` を追加（L828-846 の `race_relative_theta` の直後）。theta=None の場合は全て None・race-relative の場合は事前登録値と calib 計算値・score_split='test' の場合は `p_lower_q_shrink` 引数の値（§19.1 再現性）。
- **[C-12-02-5 MEDIUM] artifact.write_metadata_json を `allow_nan=False` で厳密化**: NaN を含む dict を渡した場合に `ValueError`（json モジュール仕様）で fail-loud（§19.1・RFC 8259 strict）。q_shrink が計算不能で NaN のまま metadata に入る silent な再現性破壊を防止。
- **save_native_artifact signature 拡張**: `p_lower_q_level`/`p_lower_q_shrink`/`p_lower_shrinkage_method` の3つの keyword-only 引数を追加（既定 None・`race_relative_theta=L108` と同一 idiom）。metadata dict（L213 の `race_relative_theta` の直後）に3キーを追加・theta=None の場合は None を記録。
- **byte-reproducible (§19.1・SC#3)**: `compute_p_lower_conformal_shrinkage` の `np.quantile` は default linear interpolation・seed 非依存・決定論的。2回実行で `np.array_equal(p_lower_1, p_lower_2)` が True・`q_shrink_1 == q_shrink_2`（Test 4 で検証）。

### Task 2: EV 層 p_lower 切替（ev_rank p_col + purchase_simulator p_min_base='p_lower' + report REPORT_COLUMNS_PHASE12）

- **ev_rank.compute_ev_and_rank に `p_col` keyword-only 引数**（既定 `'p_fukusho_hit'`・後方互換）。L107-113 の `out["EV_lower"] = out["p_fukusho_hit"] * out["fuku_odds_lower"]` を `out["EV_lower"] = out[p_col] * out["fuku_odds_lower"]` に変更（D-03・入力列差し替え）。
- **[C-12-02-3 MEDIUM] _rank に p_col 伝播**: `_rank(row, *, p_col='p_fukusho_hit')` に拡張し・`compute_ev_and_rank` が `out.apply(lambda row: _rank(row, p_col=p_col), axis=1)` で伝播。`_rank` 内の `row.get("p_fukusho_hit")` を `row.get(p_col)` に変更し・S/A/B rank の p_min 判定が p_col に従う（EV 計算と rank 条件の確率基準一致・投票層定義の分裂回避）。
- **purchase_simulator.select_bets に `p_col` と `p_min_base` の2つの keyword-only 引数**を追加（既定 `p_col='p_fukusho_hit'`, `p_min_base='p'`・後方互換）。事前登録値: `p_min_base='p_lower'` が Phase 12 のデフォルト経路（Claude's Discretion「SC#4 gate の具体的閾値」と整合・Shared Pattern 1）。L95-97 の `eligible["p_fukusho_hit"] >= FUKUSHO_EV_V1_THRESHOLDS["p_min"]` を・`p_min_base='p_lower'` の場合は `eligible[p_filter_col] >= FUKUSHO_EV_V1_THRESHOLDS["p_min"]`（`p_filter_col = 'p_fukusho_hit_lower'`）に解釈。docstring に Pitfall 7（投票層の定義明示）と事前登録値を記載。
- **[C-12-02-4 MEDIUM] report.py REPORT_COLUMNS_PHASE12 新設**: `REPORT_COLUMNS`（Phase 5 既存・11列）は不変のまま・`REPORT_COLUMNS_PHASE12 = REPORT_COLUMNS + ("p_fukusho_hit_lower", "p_lower_q_level", "p_lower_q_shrink")` を新設。`generate_report` に `report_columns`（既定 `REPORT_COLUMNS`・Phase 5 互換）と `report_basename`（既定 `'05-backtest'`・Phase 12 は `'12-evaluation'` 等に切替）の keyword-only 引数を追加。`_format_comparison_table_md` は既に `row.get(col)` で欠損キーを許容するため・`report_columns=REPORT_COLUMNS_PHASE12` を指定した場合でも p_lower 系キーが欠損した Phase 5 既存 backtest dict で KeyError にならない（regression 回避）。
- **SAFE-01 聖域**: ev_rank / purchase_simulator / report は FEATURE_COLUMNS / build_training_frame / load_feature_matrix 構築経路を import しない（Test 7 で AST 検証・0 violations）。EV 計算層は odds を消費するが feature 構築経路から切り離されている（層分離・domain-analysis §5）。
- **byte-reproducible**: ev_rank / purchase_simulator の sort は `mergesort` を維持（seed 非依存・決定論的タイブレーク・Test 5 で bit-identical 検証）。

## Tests Added

### tests/model/test_orchestrator_p_lower.py（12 tests・KEIBA_SKIP_DB_TESTS=1 GREEN）

- `test_train_and_predict_p_lower_signature_keyword_only`（[C-12-02-1 HIGH] signature 検証・KEYWORD_ONLY）
- `test_predict_p_fukusho_pred_proba_lower_signature`（[C-12-02-2] predict_p_fukusho pred_proba_lower 引数）
- `test_artifact_metadata_json_allow_nan_false_strict`（[C-12-02-5] allow_nan=False + NaN → ValueError）
- `test_q_shrink_test_window_fail_loud_without_injection`（[C-12-02-1 HIGH] score_split='test' + theta + p_lower_q_shrink=None → RuntimeError）
- `test_calib_slice_only_q_shrink_computation`（§11.2 聖域・calib slice のみ q_shrink 計算）
- `test_theta_none_yields_null_p_lower`（theta=None で p_lower 全行 NULL・A5 後方互換）
- `test_theta_specified_yields_non_null_p_lower_le_than_p`（theta=1.0 で p_lower 非NULL かつ p_lower <= p_fukusho_hit・D-01）
- `test_p_lower_byte_reproducible`（2回呼出で p_lower が np.array_equal・§19.1・SC#3）
- `test_return_dict_p_lower_provenance`（return dict に3キー・§19.1）
- `test_save_native_artifact_p_lower_metadata`（artifact metadata.json に3キー記録）
- `test_predict_p_fukusho_pred_proba_lower_index_mismatch_fail_loud`（Shared Pattern 4・silent fallback 禁止）
- `test_q_shrink_external_injection_yields_p_lower_on_test`（[C-12-02-1 HIGH] 外部注入で p_lower 生成・score_split='test'）

### tests/ev/test_ev_p_lower.py（10 tests・KEIBA_SKIP_DB_TESTS=1 GREEN）

- `test_compute_ev_and_rank_p_lower_column_substitution`（EV_lower=p_lower×odds_lower・D-03）
- `test_compute_ev_and_rank_default_p_col_backward_compat`（p_col 省略は従来通り・A5）
- `test_rank_p_col_propagation_changes_threshold_base`（[C-12-02-3] _rank p_col 伝播・境界例 p=0.30 vs p_lower=0.10）
- `test_compute_ev_and_rank_p_col_propagates_to_rank`（compute_ev_and_rank が _rank に p_col を伝播）
- `test_select_bets_p_min_base_p_lower`（p_min_base='p_lower' で p_lower >= 0.15・Pitfall 7）
- `test_select_bets_p_min_base_p_backward_compat`（p_min_base='p' は従来・A5）
- `test_select_bets_byte_reproducible_mergesort`（2回呼出で bit-identical・mergesort）
- `test_report_p_lower_display_no_regression_on_legacy_dicts`（[C-12-02-4] 既存 dict で KeyError なし）
- `test_report_phase12_p_lower_columns_display`（[C-12-02-4] REPORT_COLUMNS_PHASE12 で p_lower 系表示）
- `test_ev_layer_no_feature_columns_import_safe01`（[SAFE-01] AST 検証・0 violations）

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - 本 plan は orchestrator 統合・EV 層切替が目的で・実装は完了（stub なし）。Plan 03/04 が q_shrink 外部注入の呼出側（`run_phase12_evaluation.py`）と falsification を実装する。

## Threat Flags

None - 本 plan のファイルは `<threat_model>` の T-12-06..T-12-10 を全て mitigate 済み。新規に脅威面を導入していない。

## Sanctuaries Honored

- **§11.2 test 窓聖域**: orchestrator の q_shrink 計算は calib slice（`score_split='calib'`）または外部注入（`p_lower_q_shrink` 引数）のみ。`score_split='test'` + theta + `p_lower_q_shrink=None` は RuntimeError で fail-loud（T-12-06 mitigate・codex HIGH#1 score_split guard・Test 1/9/10 で検証）。
- **SAFE-01 odds proxy 排除**: ev_rank / purchase_simulator / report は FEATURE_COLUMNS 構築経路を import しない（T-12-07 mitigate・Test 7 AST 検証・0 violations）。EV 計算層は odds を消費するが feature 構築経路から切り離されている。
- **byte-reproducible §19.1**: `compute_p_lower_conformal_shrinkage` の `np.quantile` は seed 非依存・決定論的。2回実行で `np.array_equal` True（Test 4）。ev_rank/purchase_simulator は mergesort sort（Test 5 bit-identical）。artifact metadata は `sort_keys=True` + `allow_nan=False`（C-12-02-5）。
- **§15.2 事前登録指標不変**: 本 plan は計算経路の確立のみで・§15.2 gate（calibration_max_dev/Brier/LogLoss/sum(p)）には触れない。
- **後方互換 A5**: theta=None/v1.0 binary 呼出で p_lower=NULL（Test 2）・p_col 省略で従来 `p_fukusho_hit` ベース（Test 2・Phase 5 既存 backtest dict も regression なし・Test 6）。
- **silent fallback 禁止（Shared Pattern 4）**: pred_proba_lower の index/長さ不整合は RuntimeError（T-12-08 mitigate・Test 7）。
- **T-12-09 mitigate**: purchase_simulator.select_bets の `p_min_base` は keyword-only 引数・docstring に事前登録値（`'p_lower'` が Phase 12 デフォルト）と §11.2 聖域を明記。test 窓評価は `run_phase12_evaluation.py`（Plan 04）が事前登録値で固定呼出。
- **T-12-10 mitigate**: save_native_artifact の metadata dict に3キーを必ず追加・theta=None の場合は None を記録。race_relative_theta idiom と同一・metadata.json sort_keys=True で byte-reproducible（Test 6 で検証）。

## Self-Check: PASSED

### 作成ファイルの存在確認

- FOUND: tests/model/test_orchestrator_p_lower.py
- FOUND: tests/ev/test_ev_p_lower.py

### コミットの存在確認

- FOUND: a2c069f (test(12-02): add failing test for orchestrator p_lower integration RED)
- FOUND: 932425b (feat(12-02): orchestrator p_lower 生成 + artifact metadata allow_nan=False GREEN)
- FOUND: b6d1f1d (test(12-02): add failing test for EV layer p_lower switch RED)
- FOUND: ce4b2a5 (feat(12-02): EV 層 p_lower 切替 + report p_lower 表示 GREEN)

### done criteria grep 検証

- `grep -c "compute_p_lower_conformal_shrinkage" src/model/orchestrator.py` == 5 (>= 1) ✓
- `grep -c "allow_nan=False" src/model/artifact.py` == 4 (>= 1) ✓
- `inspect.signature(train_and_predict).parameters['p_lower_q_shrink'].kind == KEYWORD_ONLY` ✓
- `inspect.signature(train_and_predict).parameters['p_lower_q_level'].kind == KEYWORD_ONLY` ✓
- `inspect.signature(predict_p_fukusho).parameters['pred_proba_lower']` exists ✓
- `score_split='test', theta=1.0, p_lower_q_shrink=None` → RuntimeError ✓
- `compute_ev_and_rank` に p_col keyword-only 引数（既定 'p_fukusho_hit'）・p_col='p_fukusho_hit_lower' で EV_lower=p_lower×odds_lower ✓
- `_rank` にも p_col が伝播（C-12-02-3）✓
- `select_bets` に p_col / p_min_base keyword-only 引数 ✓
- `REPORT_COLUMNS_PHASE12` 新設・既存 REPORT_COLUMNS 不変 ✓
- ev_rank / purchase_simulator が FEATURE_COLUMNS を import しない（SAFE-01 AST 検証・0 violations）✓
- KEIBA_SKIP_DB_TESTS=1 full suite: 601 passed, 48 skipped（regression なし）✓
