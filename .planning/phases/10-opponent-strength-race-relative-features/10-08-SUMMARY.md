---
phase: 10-opponent-strength-race-relative-features
plan: 08
subsystem: features (field_strength / race_relative / builder / snapshot / connection / evaluation)
tags: [gap-closure, fail-loud, silent-fallback, live-db-regen, phase-11-input, safe-01-stronghold, w-3-stronghold]
requires:
  - 10-01 (CYCLE-2 HIGH-C2-1 source-as-of recompute・fail-loud 既存 idiom)
  - 10-05 (snapshot 20260626-1a-opponentstrength-v1・feature_count=106)
  - 10-07 (W-3 cProfile / SAFE-01 AST audit 聖域)
provides:
  - "src/features/field_strength.py: CR-01 silent fallback 封印 (fail-loud)・compute_field_strength_profile source race 数 fail-loud・空バッチ warning・WR-01 docstring 契約明文化"
  - "src/features/race_relative.py: CR-03 _gap_to_3rd_within_race 境界防御 (len < 3 早返し)"
  - "src/features/builder.py: CR-02 Step5c race_date 双方向 dtype 正規化 + field_strength_mean notna 率 < 0.5 で RuntimeError"
  - "src/features/snapshot.py: WR-03 _FEAT03_NUMERIC_COLUMNS を race_relative._AXIS_TO_RANK_SUFFIX から動的導出"
  - "src/db/connection.py: WR-02 make_pool が configure callback を ConnectionPool に forward"
  - "scripts/run_phase10_evaluation.py: CR-04 W-2 必須列 missing で RuntimeError・WR-02 pool 全体 statement_timeout"
  - "tests/features/test_field_strength.py: CR-01/WR-01 新テスト + WR-04 1000 race smoke + WR-05 rss 主指標化"
  - "tests/features/test_race_relative.py: CR-03 境界防御テスト (size=0/1/2 parametrize)"
  - "tests/features/test_builder_phase10_integration.py: CR-02 grep 検査テスト"
  - "tests/db/test_connection.py: WR-02 make_pool configure forward テスト"
  - "tests/features/test_run_phase10_evaluation.py: CR-04 W-2 RuntimeError + WR-02 main grep テスト"
  - "tests/audit/test_audit_field_strength.py: WR-06 else 経路 pytest.skip 化"
affects:
  - "Phase 11 MODEL-01 入力 snapshot (20260626-1a-opponentstrength-v1)・CR-02 修正で merge 値が変わる可能性を Task 3 live-DB で証明"
  - "Phase 10 SC#5 gate (run_phase10_evaluation.py)・CR-04 で W-2 証跡 RuntimeError 格上げ"
tech-stack:
  added: []
  patterns:
    - "silent fallback → RuntimeError fail-loud (core value「リーク防止」の鏡像「silent fallback 禁止」)"
    - "pd.to_datetime 双方向 dtype 正規化で silent NaN merge を構造的排除"
    - "動的導出 frozenset (race_relative._AXIS_TO_RANK_SUFFIX) でハードコード更新忘れ排除"
    - "psycopg_pool configure callback で SET statement_timeout を pool 全体適用 (cursor 単位でない)"
key-files:
  created:
    - tests/db/test_connection.py
    - tests/features/test_run_phase10_evaluation.py
  modified:
    - src/features/field_strength.py
    - src/features/race_relative.py
    - src/features/builder.py
    - src/features/snapshot.py
    - src/db/connection.py
    - scripts/run_phase10_evaluation.py
    - tests/features/test_field_strength.py
    - tests/features/test_race_relative.py
    - tests/features/test_builder_phase10_integration.py
    - tests/audit/test_audit_field_strength.py
decisions:
  - "CR-01/CR-02/CR-03/CR-04/WR-01〜06 の fail-loud 化・堅牢化を採用（core value「リーク防止」の鏡像「silent fallback 禁止」の機械保証）"
  - "WR-01 helper 大規模書き直し（_fs_history_row 77箇所 + 17テスト assertion）は backlog 化（context budget 圧迫と CYCLE-2 adversarial テスト破壊リスク・docstring 契約明文化 + adversarial テストで機械保証）"
  - "Task 3 live-DB snapshot 再生成は checkpoint:human-verify で停止（ユーザー承認待ち）"
  - "Info (IN-01〜05) と W-3 縮小版 5.0s 閾値と D-15 segment_eval は deferred（本 plan 対象外・10-VERIFICATION.md 参照）"
metrics:
  duration: 約70分（Task1/2 約35分 + Task3 live-DB regen ~24分を含む）
  completed: 2026-06-27
  tasks_total: 3
  tasks_done: 3
  tasks_checkpoint: 0
status: complete
---

# Phase 10 Plan 08: REVIEW Findings の fail-loud 化・堅牢化・live-DB 再生成検証 Summary

10-REVIEW.md の 4 Critical (CR-01〜04) + 6 Warning (WR-01〜06) のうち・ユーザー決定で採用された全対象を fail-loud 化・堅牢化し・live-DB で snapshot 再生成検証を実施する gap-closure plan。核心は core value「リーク防止」の鏡像である「silent fallback 禁止」の機械保証。Task 1/2 で実装とテストを完了し・Task 3 は live-DB snapshot 再生成検証で core value（再現性 §19.1）を完全証明した（SHA256 完全一致・silent NaN merge は本番未発生・Phase 11 入力 snapshot 不変）。

## Findings 実装サマリ

### Critical (4件)

| ID | 実装 | commit |
|----|------|--------|
| CR-01 | `_compute_source_asof_opponent_speed_figures` の silent empty DataFrame 返却を RuntimeError で封印（`source_available_at_by_race` 非空かつ batches 空）・`compute_field_strength_profile` に starters 存在 source race 数 vs cutoff 件数の fail-loud 検査追加・空バッチ logger.warning 追跡 + non_empty_batches のみ concat | f1864e9 |
| CR-02 | `builder.Step5c` merge 前に `pd.to_datetime` で `race_date` 双方向正規化・merge 後 `field_strength_mean` の notna 率 < 0.5 で RuntimeError（FEAT-02 21 feature 全行 sentinel 化の silent data loss 検知） | f1864e9 |
| CR-03 | `race_relative._gap_to_3rd_within_race` に `if len(mean5) < 3:` 早返し追加（pandas バージョン依存 transform 境界を明示防御・`index=mean5.index` の NaN Series を返す） | f1864e9 |
| CR-04 | `run_phase10_evaluation._compute_w2_diagnostics` の必須列 missing を WARNING skip でなく RuntimeError に格上げ（§11.2 聖域・W-2 証跡履行の構造的ブロック）・`race_date` 列欠損も RuntimeError | 875e100 |

### Warning (6件)

| ID | 実装 | commit |
|----|------|--------|
| WR-01 | `_opponent_ability_latest_mean5` docstring に obs_id parse 契約明文化（make_race_nkey の `_` 無し形式が契約・rsplit の安全性根拠・`_` 含み混入時リスク・adversarial テスト存在言及）。helper 大規模書き直し（77箇所・17テスト）は backlog 化（deferred セクション参照） | f1864e9 |
| WR-02 | `db/connection.make_pool` が `configure` callback 引数を取り `ConnectionPool(..., configure=configure)` に forward・`run_phase10_evaluation.main` が `_configure_statement_timeout` callback 定義・`make_pool(role='readonly', configure=_configure_statement_timeout)` で pool 構築（cursor 単位でなく connection checkout 毎に `SET statement_timeout='30s'`・memory subagent-db-query-statement-timeout） | 875e100 |
| WR-03 | `snapshot._FEAT03_NUMERIC_COLUMNS` を `race_relative._AXIS_TO_RANK_SUFFIX` から動的導出（frozenset ハードコードでなく・新 feature 追加時の snapshot.py 更新忘れ排除・実データ Parquet 直列化 bug 予防） | 875e100 |
| WR-04 | `test_production_scale_smoke_large` 新規追加（PROD_SMOKE_N_RACES_LARGE=1000・KEIBA_RUN_PERF_TESTS=1・W-3 聖域遵守・緩和でなく検出力向上・200 race では発覚しない OOM リスク検出） | 875e100 |
| WR-05 | `test_production_scale_smoke_no_h_squared_blowup` の `peak_gb` を `rss_gb` 主指標化（`max(peak_py_gb, rss_gb)` でなく）・docstring に tracemalloc 過小評価明記 | 875e100 |
| WR-06 | `test_audit_field_strength.test_feature_columns_contains_phase10_features_no_proxy` の else 経路を `pytest.raises(FileNotFoundError)` でなく `pytest.skip(...)` に変更（silent fallback mask 排除・実 snapshot 検証は test_data.py に一本化） | 875e100 |

## 新規テストリスト

### tests/features/test_field_strength.py（Task 1・CR-01 + WR-01）

- `test_cr01_compute_source_asof_fail_loud_on_all_starter_missing`（CR-01 fail-loud・RuntimeError 検証）
- `test_cr01_compute_source_asof_empty_when_cutoff_empty`（CR-01 正当な空入力時は空 DataFrame 返却）
- `test_cr01_compute_field_strength_profile_fail_loud_on_source_race_count_mismatch`（CR-01 compute_field_strength_profile 側 fail-loud 検査の静的証明）
- `test_cr01_empty_batch_warning_logged`（CR-01 空 バッチ warning + RuntimeError 検証・monkeypatch）
- `test_wr01_obs_id_parse_contract_documented`（WR-01 docstring 契約明文化の静的証明）
- `test_wr01_obs_id_parse_breaks_on_underscore_in_race_nkey`（WR-01 adversarial・`_` 含み race_nkey での parse 挙動証明）

### tests/features/test_field_strength.py（Task 2・WR-04 + WR-05）

- `test_production_scale_smoke_large`（WR-04・PROD_SMOKE_N_RACES_LARGE=1000・KEIBA_RUN_PERF_TESTS=1・default skip）
- `test_production_scale_smoke_no_h_squared_blowup`（WR-05・peak_gb=rss_gb 主指標化・docstring 拡張）

### tests/features/test_race_relative.py（Task 1・CR-03）

- `test_gap_to_3rd_within_race_size_lt_3_early_return_index_preserved`（CR-03・parametrize size=0/1/2・index 整合性検証）

### tests/features/test_builder_phase10_integration.py（Task 1・CR-02）

- `test_builder_step5c_has_race_date_dtype_normalization`（CR-02・pd.to_datetime 双方向正規化 grep 検査）
- `test_builder_step5c_has_join_ratio_fail_loud`（CR-02・joined_ratio < 0.5 で RuntimeError grep 検査）

### tests/db/test_connection.py（Task 2・WR-02・新規）

- `test_make_pool_accepts_configure_callback`（WR-02・signature 検証）
- `test_make_pool_forwards_configure_to_connection_pool`（WR-02・ConnectionPool configure= forward 検証・mock）
- `test_make_pool_default_configure_is_none`（WR-02・default None で既存呼出し非破壊）

### tests/features/test_run_phase10_evaluation.py（Task 2・CR-04 + WR-02・新規）

- `test_cr04_w2_diagnostics_raises_runtime_error_on_missing_required_columns`（CR-04・必須列 missing で RuntimeError）
- `test_cr04_w2_diagnostics_raises_runtime_error_on_race_date_missing`（CR-04・race_date 欠損で RuntimeError）
- `test_wr02_main_uses_make_pool_with_configure_callback`（WR-02・main の configure callback と二重防衛 grep 検査）

### tests/audit/test_audit_field_strength.py（Task 2・WR-06）

- `test_feature_columns_contains_phase10_features_no_proxy` の else 経路を `pytest.skip` 化（WR-06）

## 聖域回帰確認

| 聖域 | 確認結果 |
|------|---------|
| SC#1 PIT-correct（adversarial lookahead） | GREEN 維持（test_opponent_vs_source_pit_strict_less_adversarial / test_cycle2_high_c2_1_value_invariance / test_cycle2_high_c2_1_value_invariance_across_targets / test_obs_id_expanded_reuse_forbidden_and_available_at_derivation） |
| SC#4 SAFE-01（AST odds/ninki proxy 0 件・5段階鋳型） | GREEN 維持（tests/audit/test_audit_field_strength.py 7件） |
| §11.2 聖域（W-2 候補 score diagnostic・test 窓 rank すり替え禁止） | CR-04 で RuntimeError 格上げ・履行証跡欠損を構造的ブロック |
| §19.1 再現性（byte-reproducible snapshot・SHA256） | **PASS**（Task 3 live-DB 再生・SHA256 完全一致 `ea16f1e6...`/`c25ae556...`・write#1/#2 一致・silent NaN merge 本番未発生・Phase 11 入力不変） |
| W-3 性能聖域（per-race 予算 ≤0.30s/race・cProfile 上位3位 Python ループ無し・準二次スケーリングガード） | 緩和せず（WR-04 は検出力向上・既存テスト不変） |
| FEATURE_COLUMNS 106 回帰（test_data.py） | GREEN 維持（8件） |

## Task 3: live-DB snapshot 再生成検証（完了・PASS）

**状態**: 完了（ユーザー approved → orchestrator が live-DB で直接実行・subagent 経由でないため statement_timeout 問題を回避・`PGOPTIONS statement_timeout=600s` 安全弁設定）

**結果**: SHA256 完全一致・core value（再現性 §19.1）完全証明

| 項目 | 修正前 | 再生後 | 判定 |
|------|--------|--------|------|
| ファイル全体 SHA256 | `ea16f1e65b...daee70` | `ea16f1e65b...daee70` | ✅ 一致 |
| manifest SHA256 (metadata除外) | `c25ae5561e...750cd00` | `c25ae5561e...750cd00` | ✅ 一致 |
| write #1/#2 内部 assert | — | PASS | ✅ byte-repro |

**所見**:
- **CR-02 silent NaN merge は本番未発生**（dtype 正規化を加えても SHA256 不変 → history と profile の `race_date` dtype は元々一致していた・fail-loud は silent 経路封印の予防的堅牢化として有効）
- **WR-03 直列化結果も不変**（`_FEAT03_NUMERIC_COLUMNS` 動的導出に切り替えても同一 Parquet）
- 実行統計: Step5b speed_figure 21.7s / Step5c field_strength profile **725.7s**（重い・W-3 聖域想定内）/ Step5 rolling 261.0s / 全体 ~24分 / rows=554,267 features=106 raw_touched=False
- §12.4 metadata: feature_count=106・schema_version=0.6.0・feature_cutoff_rule='race_date - 1 day'・dataset_version v1.0.0（全て一致）
- 回帰テスト: `test_snapshot_repro`+`test_allowlist` **32 passed** / `test_audit_field_strength`(SAFE-01) **7 passed**（KEIBA_SKIP_DB_TESTS=1）
- **Phase 11 入力影響**: なし（snapshot byte-identical → Phase 11 入力 snapshot 不変・再学習不要）

**証跡**: `reports/10-gap-closure/regen-verification.json`（`sha256_unchanged: true`・`silent_nan_merge_absent: true`・`byte_reproducibility_sc3: PASS`・`phase11_impact: none`）

## Deviations from Plan

### Auto-fixed Issues

なし・plan は user decision 通りに実行（CR-01/02/03/04 + WR-01〜06 の全て）。

### Plan からの意図的な範囲縮小（docstring に明記済み）

1. **WR-01 helper 大規模書き直しの backlog 化**: `_fs_history_row` helper の77箇所呼出し + 17テスト assertion 全面書き直し（CYCLE-2 HIGH-C2-1 核心 adversarial テストの race_nkey 識別性依存）は・context budget 圧迫と CYCLE-2 adversarial テスト破壊リスクから backlog/issue 化した。本 plan では docstring 契約明文化 + adversarial テスト追加（`_` 含み race_nkey で parse が壊れるケースの証明）で機械保証する。本番 `make_race_nkey` が `_` 無し形式である限り実害は無い（field_strength.py L341 既存コメントで配慮済み）。

## Known Stubs

なし。

## Threat Flags

なし。本 plan の修正は既存コードの堅牢化（fail-loud 化）であり・新規のネットワークエンドポイント・認証経路・ファイルアクセスパターン・信頼境界のスキーマ変更は導入していない。脅威モデル T-10-08-01〜T-10-08-10 は全て mitigate disposition で実装済み。

## Deferred Issues

### Info (IN-01〜05)・本 plan 対象外

- IN-01: `field_strength.compute_field_strength_profile` の `observations` 引数 docstring（後方互換用・現在未使用）の整理
- IN-02: `race_relative.compute_candidate_score_diagnostics` の `score.std()` 冗長条件（`if score.notna().sum() >= 2` は不要だが明示的）
- IN-03: `builder.py` の関数内 import（`import time as _time` / `from src.features.speed_figure import ...` 等）の docstring 意図明記
- IN-04: `rolling.py::_ROLLING_SYSTEMS` と `availability._ROLLING_SYSTEMS_FOR_RESERVED` の二重定義（循環依存回避のため意図的・test で drift 検出済み）
- IN-05: `run_phase10_evaluation.py` の W-2 diagnostic が `BT1_PERIODS["test"]` を使わないことの暗黙（§11.2 聖域通りだが assert で明示的にするとより安全）

### WR-01 helper 大規模書き直し（backlog/issue 化）

`tests/features/test_field_strength.py` の `_fs_history_row` helper の77箇所の呼出し（17テスト関数）で `"R1_20230610"` 形式（`_` 含み）の race_nkey を使い続けている。本番 `make_race_nkey` が `_` 無し形式（YYYYJJJKKNN）である限り実害は無いが・helper 全面書き直し（77箇所 + 17テスト assertion・race_nkey 識別性を保ちつつ `_` 無し形式に移行）は別 issue として登録が必要。Phase 11 以降または保守 sprint で対応する。

### W-3 縮小版 5.0s 閾値（PLAN 01/07 で option-a 根拠再設定済み）

W-3 縮小版 5.0s 閾値（絶対）は PLAN 01/07 で option-a 根拠再設定済み（per-race 予算 ≤0.30s/race + 準二次スケーリングガード・緩和でなく根拠再設定・10-VERIFICATION.md deferred L14-17・NOT a gap）。本 plan では扱わない。

### D-15 segment_eval（Phase 12 EVAL-01 に先送り済み）

D-15 segment_eval column-name mismatch は Phase 12 EVAL-01 に先送り済み（10-VERIFICATION.md deferred L21-23・参照用 only・gate 判定に使わず）。本 plan では扱わない。

## Self-Check: PASSED

### 作成ファイルの存在確認

- tests/db/test_connection.py: FOUND
- tests/features/test_run_phase10_evaluation.py: FOUND

### コミットの存在確認

- f1864e9 (Task 1): FOUND
- 875e100 (Task 2): FOUND

### テスト結果

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ tests/audit/ tests/model/test_data.py -q` → 202 passed, 4 skipped（4 skip は KEIBA_RUN_PERF_TESTS 未設定の性能テスト・全て GREEN）

### 聖域回帰

- SC#1 PIT-correct: GREEN 維持
- SC#4 SAFE-01: GREEN 維持
- §11.2 W-2: CR-04 で強化（RuntimeError 格上げ）
- §19.1 byte-reproducibility: **PASS**（live-DB 再生 SHA256 完全一致・`reports/10-gap-closure/regen-verification.json`）
- W-3 性能: 緩和せず（WR-04 は検出力向上）
