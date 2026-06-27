---
phase: 10-opponent-strength-race-relative-features
verified: 2026-06-27T09:30:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  previous_verified: 2026-06-27T08:30:00Z
  gaps_closed:
    - "10-REVIEW.md 4 Critical (CR-01〜04) + 6 Warning (WR-01〜06) の fail-loud 化・堅牢化（commits f1864e9 / 875e100・10-08 gap-closure plan）"
    - "PLAN truth doc 不整合（10-06-PLAN baseline 79→35 訂正・commit ff34252・10-09 doc fix plan）"
    - "live-DB snapshot 再生 SHA256 完全一致・silent NaN merge 本番未発生証明・Phase 11 入力 snapshot 不変（reports/10-gap-closure/regen-verification.json・commit a662c9c）"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "W-3 性能ゲート（絶対 5.0s 閾値）"
    status: addressed_not_gap
    addressed_in: "Phase 10 内・PLAN 01/07 で 2026-06-27 option-a により根拠再設定で解決済み（NOT a gap）"
    evidence: "10-01-PLAN L217 / 10-07-PLAN L28-30, L181-193: 絶対閾値を per-source-race 線形予算(≤0.30s/race) + 準二次スケーリングガードに根拠再設定（緩和でなく根拠再設定・聖域遵守）。test_no_python_loop_hot_spot GREEN（cProfile 上位3位に Python ループ無し）で原理証明済み。"
  - truth: "10-REVIEW.md 4 Critical / 6 Warning / 5 Info"
    status: closed
    addressed_in: "Phase 10 gap-closure（10-08 plan・commits f1864e9 / 875e100）"
    evidence: "CR-01〜04 + WR-01〜06 を fail-loud 化・堅牢化（core value「リーク防止」の鏡像「silent fallback 禁止」の機械保証）。Info (IN-01〜05) は backlog 化（10-08-SUMMARY deferred に明記）。WR-01 helper 大規模書き直し（_fs_history_row 77箇所）も backlog 化（docstring 契約明文化 + adversarial テスト test_wr01_obs_id_parse_breaks_on_underscore_in_race_nkey で機械保証）。live-DB snapshot 再生で SHA256 完全一致（ea16f1e6.../c25ae556...）・silent NaN merge 本番未発生証明（regen-verification.json）。"
  - truth: "D-15 segment_eval（10-06）column-name mismatch"
    status: deferred
    addressed_in: "Phase 12 EVAL-01"
    evidence: "参照用 only・gate 判定に使わず（Brier/LogLoss/AUC の3条件のみ gate）・Phase 12 EVAL-01 で正式対応。"
  - truth: "PLAN truth doc 不整合（10-06 baseline 79→35）"
    status: closed
    addressed_in: "Phase 10 gap-closure（10-09 plan・commit ff34252）"
    evidence: "10-06-PLAN.md の model FEATURE_COLUMNS 文脈の baseline snapshot (postreview-v2) の FEATURE_COLUMNS 値を 79 → 35 に訂正（実測値根拠: PROJECT decisions『postreview-v2 実データ値 35 が正』・src/model/data.py _derive_feature_columns の registry 動的導出・tests/model/test_data.py の BASELINE_V10_FEATURE_COUNT=35 定数）。W-4 文脈判定基準（model FEATURE_COLUMNS vs Parquet 全列数）のキーフレーズリストで機械置換。コード変更なし・substantive 検証は 10-06 で達成済み（SC#5 gate_pass=True）。"
  - truth: "Info (IN-01〜05)・10-REVIEW.md軽微事項"
    status: deferred
    addressed_in: "backlog/issue 化"
    evidence: "10-08-SUMMARY.md Deferred Issues セクションに全件明記（IN-01 observations 引数 docstring / IN-02 score.std 冗長条件 / IN-03 関数内 import / IN-04 _ROLLING_SYSTEMS 二重定義 / IN-05 W-2 test 窓暗黙）。実害無・別 issue で対応。"
  - truth: "WR-01 helper 大規模書き直し（_fs_history_row 77箇所）"
    status: deferred
    addressed_in: "backlog/issue 化（Phase 11 以降または保守 sprint）"
    evidence: "本番 make_race_nkey が _ 無し形式（YYYYJJJKKNN）である限り実害無・docstring 契約明文化（src/features/field_strength.py _opponent_ability_latest_mean5 docstring）+ adversarial テスト test_wr01_obs_id_parse_breaks_on_underscore_in_race_nkey で機械保証。helper 全面書き直し（77箇所 + 17テスト assertion・CYCLE-2 核心 adversarial テスト破壊リスク）は別 issue。"
---

# Phase 10: Opponent Strength & Race-Relative Features Verification Report

**Phase Goal:** 過去走の相手の as-of 能力平均（`field_strength`）と、レース内相対特徴量（`speed_index_rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`）を、Phase 9 のスピード指数を前提として odds-free・PIT-safe に追加する。複勝の「相対競争・各馬独立事象でない」性質を特徴量層で表現する。
**Verified:** 2026-06-27T09:30:00Z
**Status:** passed
**Re-verification:** Yes — gap-closure後再検証（10-08/10-09 追加実行後・前回 status: passed 5/5 を維持・core value 強化）

## Re-verification サマリ（gap-closure で強化された core value）

本 re-verification は前回（2026-06-27T08:30:00Z）の status: passed (5/5) を受け・gap-closure plan 10-08/10-09 で追加実行された修正が core value（リーク防止 + 再現性 §19.1）を強化したことを確認するものである。gap-closure は SC#1-5 を覆さず・むしろ silent fallback 経路の封印・W-2 証跡の RuntimeError 格上げ・live-DB での SHA256 完全一致証明で core value を更に機械保証した。

**gap-closure の層別サマリ:**

| 層 | 強化内容 | 証拠 |
|----|---------|------|
| silent fallback → fail-loud（core value の鏡像） | CR-01（field_strength 空 batch RuntimeError）・CR-02（builder Step5c race_date 双方向 dtype 正規化 + JOIN率 <0.5 で RuntimeError） | src/features/field_strength.py L267-271・src/features/builder.py L578-602 |
| §11.2 聖域強化 | CR-04 W-2 証跡 WARNING skip → RuntimeError 格上げ（履行証跡欠損の構造的ブロック） | scripts/run_phase10_evaluation.py L265-270 |
| 再現性 §19.1 完全証明 | live-DB snapshot 再生で SHA256 完全一致・silent NaN merge 本番未発生証明 | reports/10-gap-closure/regen-verification.json（sha256_unchanged=true・silent_nan_merge_absent=true・byte_reproducibility_sc3=PASS） |
| 境界防御 | CR-03（race_relative _gap_to_3rd_within_race len<3 早返し） | src/features/race_relative.py L193 |
| 動的導出（更新忘れ排除） | WR-03（snapshot._FEAT03_NUMERIC_COLUMNS を race_relative._AXIS_TO_RANK_SUFFIX から動的導出） | src/features/snapshot.py L49/L86-91 |
| pool statement_timeout（副次強化） | WR-02（make_pool configure callback forward・connection checkout 毎に SET） | src/db/connection.py L27/L72・scripts/run_phase10_evaluation.py |
| 検出力向上（W-3 聖域遵守・緩和でなく） | WR-04（PROD_SMOKE_N_RACES_LARGE=1000）・WR-05（rss_gb 主指標化）・WR-06（pytest.skip 化） | tests/features/test_field_strength.py L816/L1079/L1116・tests/audit/test_audit_field_strength.py L273 |
| doc truth 整合 | 10-09（10-06-PLAN baseline 79→35 訂正・W-4 文脈判定基準で機械置換・コード変更なし） | .planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md（commit ff34252） |

## Goal Achievement

### Observable Truths (SC#1–SC#5)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC#1 | 相手強度特徴量が PIT-correct（as-of 定義明文化・当日結果不使用・未来能力の遡及注入なし・adversarial lookahead テスト GREEN） | ✓ VERIFIED | `src/features/field_strength.py` 621行・実質的実装。厳格版 D-01（strict `<`）採用・`_pit_cutoff_prefilter` L121 で行レベル PIT gate・`_compute_source_asof_opponent_speed_figures` で source-as-of full pipeline 再計算（CYCLE-2 HIGH-C2-1 値レベル保証・obs_id 展開済み speed_figure 再利用禁止・raw_history に合成 observation で再計算）。`tests/features/test_field_strength.py` 18 テスト（adversarial lookahead・value-invariance・same-day opponent 混入検出含む）全 GREEN。特に `test_opponent_vs_source_pit_strict_less_adversarial` / `test_cycle2_high_c2_1_value_invariance` / `test_cycle2_high_c2_1_value_invariance_across_targets` が load-bearing invariant を機械証明。 **【gap-closure 強化】** CR-01 で `_compute_source_asof_opponent_speed_figures` の silent empty DataFrame 返却経路（source_available_at_by_race 非空かつ全 source race が starter 不在）を RuntimeError で封印（L267-271・CYCLE-2 HIGH-C2-1 値レベル PIT 保証の silent fallback 経路を構造的ブロック）・空バッチ logger.warning 追跡 + non_empty_batches のみ concat・compute_field_strength_profile 側に starters 存在 source race 数 vs source_available_at_by_race 件数の fail-loud 検査を追加。test_cr01_compute_source_asof_fail_loud_on_all_starter_missing・test_cr01_empty_batch_warning_logged 等の新規 fail-loud テストが GREEN。 |
| SC#2 | レース内相対特徴量が race_id 単位で future-information なし・同着/欠損境界処理明文化 | ✓ VERIFIED | `src/features/race_relative.py` 404行・実質的実装。race_nkey group-by + transform で race_id 単位計算・target observation のみ（history 行混入禁止・test_target_only_no_history_rows）。同着 = competition ranking（"1224" 方式・D-10）・欠損 = `na_option="keep"` で母集団除外・最下位固定しない（D-09）・gap_to_3rd tie 仕様明文化（REVIEW MEDIUM-7・同着2位で rank==3 空位時は全馬 NaN）。`tests/features/test_race_relative.py` 18 テスト全 GREEN・tie/missing/tie-at-2nd/scale-compatibility を網羅。 **【gap-closure 強化】** CR-03 で `_gap_to_3rd_within_race` に `if len(mean5) < 3:` 早返し（NaN series・index=mean5.index）を追加（L193）・pandas バージョン依存の transform 境界を明示防御。test_gap_to_3rd_within_race_size_lt_3_early_return_index_preserved（parametrize size=0/1/2）が GREEN。 |
| SC#3 | 追加特徴量を含む feature snapshot が byte-reproducible・registry↔Parquet parity・§12.4 metadata 反映 | ✓ VERIFIED | snapshot `feature_matrix_20260626-1a-opponentstrength-v1.parquet`（108MB・106 columns・554,267 rows）+ manifest（sha256=c25ae556...・feature_count=106・schema_version=0.6.0・feature_cutoff_rule='race_date - 1 day'・dataset_version v1.0.0）。registry `src/config/feature_availability.yaml` 711行・schema_version 0.6.0・Phase 10 の 27 feature（rolling_field_strength 21 + race_relative 6）を明示登録・cutoff_semantics（strict_less_than / Asia/Tokyo）仕様化。`tests/features/test_snapshot_repro.py` 16 テスト GREEN。Parquet schema が 106 列と manifest feature_count=106 と一致（registry↔Parquet parity）。 **【gap-closure 完全証明】** live-DB で CR-02 dtype 正規化 + WR-03 動的導出 修正後の builder/snapshot を使って snapshot を再生成し・SHA256 が修正前と完全一致（ファイル全体: ea16f1e65b...daee70・metadata除外 manifest: c25ae5561e...750cd00）・silent NaN merge は本番では発生していなかったこと（dtype 一致）を証明（reports/10-gap-closure/regen-verification.json: sha256_unchanged=true・silent_nan_merge_absent=true・byte_reproducibility_sc3=PASS・phase11_impact=none）。WR-03 で _FEAT03_NUMERIC_COLUMNS を race_relative._AXIS_TO_RANK_SUFFIX から動的導出（snapshot.py L49/L86-91）・新 feature 追加時の更新忘れ排除。回帰テスト test_snapshot_repro+test_allowlist 32 passed・test_audit_field_strength(SAFE-01) 7 passed。 |
| SC#4 | オッズ/人気 proxy 混入がないことを adversarial audit で証明（SAFE-01） | ✓ VERIFIED | `tests/audit/test_audit_field_strength.py` 7 テスト GREEN・5段階鋳型（AST Name/Attribute + SQL 文字列リテラル REVIEW H3 odds-in-SQL 拡張 + FEATURE_COLUMNS allowlist + false-pass 回避 + lookahead 注入・値の不変性）。Test 1/2 で `field_strength.py`/`race_relative.py` の AST から odds/ninki/fukuodds/ninkij/tansyouodds proxy 0件を静的証明。Test 4 false-pass detection power で意図的注入を guard が検出することを証明。Test 5/6 で 2層 PIT gate 完全突破 adversarial で guard 有効性を逆証明。src/audit/report.py 359行で SAFE-01 聖域を report 化。 **【gap-closure 強化】** §11.2 聖域（test 窓 rank すり替え禁止・W-2 候補 score diagnostic）の履行証跡欠損を CR-04 で構造的ブロック（scripts/run_phase10_evaluation.py L265-270・必須列 missing を WARNING skip でなく RuntimeError に格上げ・W-2 acceptance criteria 未達を明示）。WR-06 で test_audit_field_strength の snapshot 未生成時 else 経路を pytest.raises(FileNotFoundError) から pytest.skip に変更（silent fallback mask 排除・実 snapshot 検証は test_data.py に一本化・L273）。test_cr04_w2_diagnostics_raises_runtime_error_on_missing_required_columns と test_cr04_w2_diagnostics_raises_runtime_error_on_race_date_missing が GREEN。 |
| SC#5 | live-DB snapshot が v1.0 LightGBM 再学習で Brier/LogLoss/AUC 現行水準を悪化させない（D-16 許容幅内・SC#5 gate） | ✓ VERIFIED | `reports/10-evaluation/10-evaluation.json` + `10-evaluation.md`: gate_pass=True（3/3 D-16 許容幅内）。Brier delta=-0.00022 (tol ≤+0.002) PASS・LogLoss delta=+0.00487 (tol ≤+0.005) PASS・AUC delta=+0.00180 (tol ≥-0.005) PASS。W-3 category_map bit_identical=True（baseline/phase10 cat_map hash 同一）。W-2 candidate score diagnostics status=ok（0.25 canonical 妥当性証拠・train/calib 窓内のみ・§11.2 聖域）。§15.2 binning import 再利用確認。 **【gap-closure 強化】** gap-closure で snapshot は byte-identical（SHA256 完全一致）のため・SC#5 gate_pass=True 判定の前提（入力 snapshot）は不変・Phase 11 入力 snapshot も不変。CR-04 で W-2 証跡が RuntimeError 格上げされたことで・将来 rolling 系 feature 伝播が壊れた場合に process が即座に停止し・silent に W-2 証跡欠損で ship されるリスクを構造的排除（§11.2 聖域強化）。WR-02 で pool configure callback により SET statement_timeout='30s' が connection checkout 毎に適用され・memory subagent-db-query-statement-timeout の系統の orphan CPU 張り付きリスクも軽減。 |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Deferred Items

| # | Item | Status | Addressed In | Evidence |
|---|------|--------|-------------|----------|
| 1 | 10-REVIEW.md 4 Critical / 6 Warning / 5 Info | closed | Phase 10 gap-closure (10-08) | CR-01〜04 + WR-01〜06 を fail-loud 化（commits f1864e9/875e100）・Info (IN-01〜05) は backlog 化・WR-01 helper も backlog 化。live-DB snapshot 再生 SHA256 完全一致で core value 強化証明。 |
| 2 | PLAN truth doc 不整合（10-06 baseline 79→35） | closed | Phase 10 gap-closure (10-09) | commit ff34252・W-4 文脈判定基準で機械置換・コード変更なし・substantive 検証は 10-06 で達成済み。 |
| 3 | W-3 性能ゲート（絶対 5.0s 閾値） | addressed_not_gap | Phase 10 内（PLAN 01/07 option-a） | per-race 予算 ≤0.30s/race + 準二次スケーリングガードで根拠再設定（緩和でなく根拠再設定）。 |
| 4 | D-15 segment_eval column-name mismatch | deferred | Phase 12 EVAL-01 | 参照用 only・gate 判定に使わず（Brier/LogLoss/AUC の3条件のみ gate）。 |
| 5 | Info (IN-01〜05)・10-REVIEW.md軽微事項 | deferred | backlog/issue 化 | 10-08-SUMMARY.md Deferred Issues セクションに全件明記・実害無・別 issue で対応。 |
| 6 | WR-01 helper 大規模書き直し（_fs_history_row 77箇所） | deferred | backlog/issue 化（Phase 11 以降） | 本番 make_race_nkey が _ 無し形式である限り実害無・docstring 契約明文化 + adversarial テスト test_wr01_obs_id_parse_breaks_on_underscore_in_race_nkey で機械保証。 |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/features/field_strength.py` | SC#1 source-as-of field_strength profile 8値 | ✓ VERIFIED | 621 lines・compute_field_strength_profile + 5 helper。**【gap-closure】** CR-01 silent empty DataFrame 返却封印（L267-271）・compute_field_strength_profile 側 fail-loud 検査・空バッチ warning + non_empty_batches のみ concat・_opponent_ability_latest_mean5 docstring 契約明文化（WR-01）。 |
| `src/features/race_relative.py` | SC#2 race_id group-by rank/gap/adjusted_rank | ✓ VERIFIED | 404 lines・competition ranking helper（D-10・D-09・D-08・D-11/D-12 全決定反映）。**【gap-closure】** CR-03 `_gap_to_3rd_within_race` に len < 3 早返し追加（L193）。 |
| `src/features/rolling.py` | D-13 21 feature rolling 集約 | ✓ VERIFIED | 949 lines・_FIELD_STRENGTH_AXES・D-13 (axis, window) 21 feature・strict < cutoff PIT gate。 |
| `src/features/builder.py` | Step 5c/5d/7/7b 統合 | ✓ VERIFIED | 892 lines・Step 5c raw_history → compute_field_strength_profile・Step 7 feature_matrix → compute_race_relative_features・registry derived FEATURE_COLUMNS。**【gap-closure】** CR-02 Step5c race_date 双方向 dtype 正規化（L578-580）+ JOIN率 <0.5 で RuntimeError（L596-602）。 |
| `src/config/feature_availability.yaml` | registry↔Parquet parity・schema_version 0.6.0 | ✓ VERIFIED | 711 lines・schema_version "0.6.0"・Phase 10 27 feature 明示登録・cutoff_semantics strict_less_than。 |
| `src/features/snapshot.py` | byte-reproducible snapshot | ✓ VERIFIED | 447 lines・sha256 (Parquet bytes only)・feature_count・§12.4 metadata。**【gap-closure】** WR-03 _FEAT03_NUMERIC_COLUMNS を race_relative._AXIS_TO_RANK_SUFFIX から動的導出（L49/L86-91・frozenset ハードコードでなく）。 |
| `src/db/connection.py` | psycopg3 pool/cursor | ✓ VERIFIED | make_pool・readonly_cursor・write_cursor。**【gap-closure】** WR-02 make_pool が configure callback 引数を取り ConnectionPool(..., configure=configure) に forward（L27/L72・statement_timeout 等 session 設定の pool 全体適用）。 |
| `snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet` | live-DB snapshot・106 features | ✓ VERIFIED | 108MB・106 columns・554,267 rows・sha256 ea16f1e65b...daee70。**【gap-closure 完全証明】** CR-02/WR-03 修正後の builder/snapshot で live-DB 再生し SHA256 完全一致（silent NaN merge 本番未発生）。 |
| `snapshots/feature_matrix_20260626-1a-opponentstrength-v1.manifest.yaml` | §12.4 metadata 完備 | ✓ VERIFIED | feature_count=106・schema_version=0.6.0・feature_cutoff_rule='race_date - 1 day'・dataset_version v1.0.0・sha256 c25ae556...。 |
| `scripts/run_phase10_evaluation.py` | SC#5 非劣化 gate 実行 | ✓ VERIFIED | 820 lines・D-16 許容幅判定・W-3 cat_map bit-identity・W-2 candidate score diagnostics・§15.2 binning import。**【gap-closure】** CR-04 W-2 必須列 missing で WARNING skip → RuntimeError 格上げ（L265-270・§11.2 聖域強化）・race_date 欠損も RuntimeError（L274）・WR-02 main が _configure_statement_timeout callback で pool 構築。 |
| `src/model/data.py` | registry derived FEATURE_COLUMNS allowlist | ✓ VERIFIED | 722 lines・FEATURE_COLUMNS = _derive_feature_columns()（registry 動的導出・79 自動追従・baseline は 35）・make_X_y 厳密一致 assert。 |
| `src/audit/report.py` | SAFE-01 聖域 report | ✓ VERIFIED | 359 lines・SC#4 SAFE-01 proxy 排除・PIT 保証・odds_snapshot_policy 検査を report 化。 |
| `reports/10-evaluation/{10-evaluation.json,10-evaluation.md}` | SC#5 gate 結果 | ✓ VERIFIED | gate_pass=True・3条件全 D-16 許容幅内・delta 基準 baseline 実測値。 |
| `reports/10-gap-closure/regen-verification.json` | **【新規・gap-closure 証拠】** | ✓ VERIFIED | verdict=PASS・sha256_unchanged=true・silent_nan_merge_absent=true・byte_reproducibility_sc3=PASS・feature_count=106・phase11_impact=none・step5c_field_strength_profile=725.7s。 |
| `tests/db/test_connection.py` | **【新規・gap-closure】** WR-02 make_pool configure forward | ✓ VERIFIED | test_make_pool_accepts_configure_callback・test_make_pool_forwards_configure_to_connection_pool・test_make_pool_default_configure_is_none の 3 テスト GREEN。 |
| `tests/features/test_run_phase10_evaluation.py` | **【新規・gap-closure】** CR-04 + WR-02 | ✓ VERIFIED | test_cr04_w2_diagnostics_raises_runtime_error_on_missing_required_columns・test_cr04_w2_diagnostics_raises_runtime_error_on_race_date_missing・test_wr02_main_uses_make_pool_with_configure_callback の 3 テスト GREEN。 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `builder.py` Step 5c | `field_strength.compute_field_strength_profile` | `raw_history` 第1引数・observations=feature_matrix | WIRED | builder.py L554-556・raw_history は Step 5b 前・obs_id 未展開・CYCLE-2 HIGH-C2-1 前提・test_builder_step5c_passes_raw_history_not_history で保証。**【gap-closure】** CR-02 merge 前に race_date 双方向 dtype 正規化・merge 後 JOIN率 fail-loud。 |
| `builder.py` Step 7 | `race_relative.compute_race_relative_features` | `feature_matrix` group-by race_nkey | WIRED | builder.py L685-687・test_builder_has_step7_race_relative_call で保証。 |
| `field_strength.py` | `compute_speed_figure_for_history` (Phase 9) | synth_obs (obs_id=SOURCE_ASOF_<race_nkey>_<kettonum>) | WIRED | field_strength.py L194-289・source-as-of full pipeline 再計算・test_obs_id_expanded_reuse_forbidden_and_available_at_derivation で保証。**【gap-closure】** CR-01 空 batch silent fallback 封印・WR-01 obs_id parse 契約 docstring 明文化 + adversarial テスト。 |
| `rolling.py` | `field_strength` profile 8値 | history 列 source・_FIELD_STRENGTH_AXES | WIRED | rolling.py L88-119・D-13 21 feature 生成・test_rolling.py 18 テスト GREEN。 |
| `data.py` | `feature_availability.yaml` registry | FEATURE_COLUMNS = _derive_feature_columns() | WIRED | data.py L214・test_feature_columns_allowlist_derived_from_registry で保証。 |
| `snapshot.py` | §12.4 Parquet metadata | feature_count / feature_cutoff_rule / dataset_version / sha256 | WIRED | snapshot.py L329/349/380/403/429・test_metadata_contains_12_4_keys・test_phase10_metadata_feature_availability_version GREEN。**【gap-closure】** WR-03 _FEAT03_NUMERIC_COLUMNS を race_relative._AXIS_TO_RANK_SUFFIX から動的導出（更新忘れ排除）。 |
| `run_phase10_evaluation.py` | `trainer/evaluator` | Brier/LogLoss/AUC 計算・D-16 許容幅判定 | WIRED | reports/10-evaluation/10-evaluation.json に baseline/phase10/delta/tolerance/gate_pass 全完備。**【gap-closure】** CR-04 W-2 証跡 RuntimeError 格上げ（§11.2 聖域）・WR-02 pool configure callback で statement_timeout。 |
| `connection.py` make_pool | psycopg_pool ConnectionPool | configure=configure forward | WIRED | **【gap-closure】** src/db/connection.py L27/L72・test_make_pool_forwards_configure_to_connection_pool で保証。 |
| `run_phase10_evaluation.py` main | `connection.make_pool` with configure | `_configure_statement_timeout` callback | WIRED | **【gap-closure】** scripts/run_phase10_evaluation.py main・test_wr02_main_uses_make_pool_with_configure_callback で保証。 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `feature_matrix_20260626-1a-opponentstrength-v1.parquet` | rolling_field_strength_mean_latest_1 | field_strength.py source-as-of recompute → rolling.py D-13 集約 | Yes (75,008 non-null / 100,000 row-group・実データ) | ✓ FLOWING |
| 同上 | speed_index_rank_mean5 | race_relative.py race_nkey group-by | Yes (36,921 non-null・rank median=5.0/max=18.0 = フィールドサイズ対応) | ✓ FLOWING |
| 同上 | field_strength_adjusted_rank | race_relative.py (mean5 + 0.25 * fs_mean5) の race_id 内 rank | Yes (33,010 non-null・rank median=5.0/max=18.0) | ✓ FLOWING |
| 同上 | gap_to_top / gap_to_3rd | race_relative.py race_id 内 top/3rd - self | Yes (36,921 / 35,633 non-null・gap_to_3rd は同着2位で rank==3 空位時に NaN・仕様通り) | ✓ FLOWING |
| **【gap-closure】** regen-verification.json | sha256_unchanged / silent_nan_merge_absent / byte_reproducibility_sc3 | live-DB 再生 → SHA256 比較 | Yes (true / true / PASS・Phase 11 入力不変) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| SC#1 PIT-correct adversarial lookahead | `pytest tests/features/test_field_strength.py::test_opponent_vs_source_pit_strict_less_adversarial + 3 invariant tests` | 4 passed in 0.20s | ✓ PASS |
| SC#2 tie/missing edge cases | `pytest tests/features/test_race_relative.py` | 18 passed in 0.08s | ✓ PASS |
| SC#3 byte-reproducibility + metadata | `pytest tests/features/test_snapshot_repro.py` | 16 passed in 0.12s | ✓ PASS |
| SC#4 SAFE-01 AST audit | `pytest tests/audit/test_audit_field_strength.py` | 7 passed in 1.29s | ✓ PASS |
| SC#4 odds/ninki proxy 0 件（直接 grep） | `grep -cE "odds\|ninki\|fukuodds" src/features/{field_strength,race_relative}.py` | 0 / 0 occurrences | ✓ PASS |
| SC#5 gate JSON | `python3 -c "import json; d=json.load(open('reports/10-evaluation/10-evaluation.json')); print(d['gate_pass'], d['delta'])"` | True, all 3 deltas in tolerance | ✓ PASS |
| W-3 cProfile 原理証明 | `KEIBA_RUN_PERF_TESTS=1 pytest test_field_strength.py::test_no_python_loop_hot_spot` | 1 passed in 26.77s | ✓ PASS |
| registry↔Parquet parity | `pyarrow pq.read_metadata().num_columns` vs manifest `feature_count` | 106 = 106 | ✓ PASS |
| Phase 10 features in Parquet schema | `pq.ParquetFile.schema_arrow.names` filter | 27 features present (rolling_field_strength 21 + race_relative 6) | ✓ PASS |
| builder Step 5c/7 wiring | `pytest tests/features/test_builder_phase10_integration.py` | 11 passed in 0.11s | ✓ PASS |
| **【gap-closure】** CR-01/02/03 fail-loud + WR-01 契約 | `pytest tests/features/test_field_strength.py tests/features/test_race_relative.py tests/features/test_builder_phase10_integration.py` | 55 passed, 4 skipped（性能 default skip） | ✓ PASS |
| **【gap-closure】** SC#1/SC#4 聖域回帰 | 同上 + tests/audit/test_audit_field_strength.py | GREEN 維持・聖域回帰なし | ✓ PASS |
| **【gap-closure】** WR-02/CR-04 + snapshot 動的導出 | `pytest tests/db/test_connection.py tests/features/test_run_phase10_evaluation.py tests/features/test_snapshot_repro.py tests/model/test_data.py` | 37 passed in 13.43s | ✓ PASS |
| **【gap-closure】** live-DB SHA256 完全一致 | `shasum -a 256 snapshots/...parquet` vs regen-verification.json | ea16f1e65b...daee70 = 完全一致 | ✓ PASS |
| **【gap-closure】** regen-verification.json verdict | `python3 -c "import json; d=json.load(open('reports/10-gap-closure/regen-verification.json')); print(d['verdict'], d['sha256_unchanged'], d['silent_nan_merge_absent'])"` | PASS True True | ✓ PASS |
| **【gap-closure】** 新規 fail-loud テスト存在 | `pytest --collect-only -q` grep cr01/cr02/cr03/cr04/wr01/wr02/wr04/wr05/wr06/production_scale_smoke_large/obs_id_parse | 10+ 新規テスト存在確認 | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — Phase 10 は conventional probe（`scripts/*/tests/probe-*.sh`）を宣言しておらず・検証は pytest behavioral spot-checks + adversarial tests で完結。**【gap-closure】** live-DB snapshot 再生成（Task 3 checkpoint:human-verify）は人間が承認して実行済み（commit a662c9c）・regen-verification.json に記録。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| FEAT-02 | 10-01, 10-02, 10-04, **【gap-closure】10-08** | 相手強度補正特徴量（field_strength as-of 能力平均・odds-free・PIT-safe） | ✓ SATISFIED | src/features/field_strength.py + rolling.py 21 feature + builder.py Step 5c/5d・SC#1 PIT gate GREEN・REQUIREMENTS.md で Complete マーク。**【gap-closure】** CR-01 silent fallback 封印・CR-02 silent NaN merge 封印で PIT 保証の周辺堅牢性を強化。 |
| FEAT-03 | 10-03, 10-04, **【gap-closure】10-08** | レース内相対特徴量（rank / gap_to_top / gap_to_3rd / field_strength_adjusted_rank） | ✓ SATISFIED | src/features/race_relative.py 6 feature + builder.py Step 7・SC#2 race_id group-by + tie/missing 仕様 GREEN・REQUIREMENTS.md で Complete マーク。**【gap-closure】** CR-03 境界防御（len<3 早返し）。 |
| SAFE-01 | 10-07（全 Phase 横断聖域）, **【gap-closure】10-08** | オッズ/人気 proxy を p モデル特徴量に入れない・adversarial audit で証明 | ✓ SATISFIED | tests/audit/test_audit_field_strength.py 7 テスト GREEN・AST 静的解析で odds/ninki proxy 0 件・lookahead 注入で PIT 保証逆証明・REQUIREMENTS.md で Complete マーク。**【gap-closure】** CR-04 §11.2 聖域強化（W-2 証跡 RuntimeError 格上げ）・WR-06 silent fallback mask 排除。 |
| **【gap-closure】** doc truth 整合 | 10-09 | PLAN truth 数値表記の実測値整合（10-06 baseline 79→35） | ✓ SATISFIED | commit ff34252・W-4 文脈判定基準（model FEATURE_COLUMNS vs Parquet 全列数）で機械置換・コード変更なし。 |

孤立要件（ORPHANED）: なし。FEAT-02/FEAT-03/SAFE-01 全て Phase 10 PLAN（10-01〜10-09 含む）で明示的に要求 ID を宣言し・REQUIREMENTS.md でも Phase 10 → Complete とマークされている。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | - | - | - | Phase 10 新モジュール（field_strength / race_relative / audit/report / run_phase10_evaluation）に TBD/FIXME/XXX marker 0 件・placeholder prose 0 件。odds/ninki proxy も 0 件（SC#4 SAFE-01 聖域）。**【gap-closure】** fail-loud 化で silent fallback 経路を RuntimeError で封印・core value「リーク防止」の鏡像「silent fallback 禁止」を機械保証。 |

### Human Verification Required

（なし）

全 truth が adversarial / behavioral テストで機械証明されており・人間確認が必要な視覚/UX/リアルタイム要素は存在しない。W-3 縮小版性能テスト・production-scale smoke・cProfile hot spot は default skip だが KEIBA_RUN_PERF_TESTS=1 で実行可能・cProfile 核心 GREEN は実証済み・**【gap-closure】** WR-04 で 1000 race smoke も追加（検出力向上・W-3 聖域遵守）。**【gap-closure】** Task 3（live-DB snapshot 再生成検証）は checkpoint:human-verify だったが・ユーザー承認済みで実行完了（commit a662c9c・regen-verification.json 記録）。

### Gaps Summary

（なし — status: passed）

核心のリーク防止機構（source-as-of full-pipeline 再計算・行レベル PIT filter・AST audit・adversarial value-invariance）はすべて機械証明され・SC#1–SC#5 全てが実データ・実テスト・実メトリクスで裏付けられた。

**【gap-closure による core value 強化の総括】**

10-REVIEW.md の指摘（4 Critical / 6 Warning / 5 Info）は核心バリュー（リーク防止）でなく周辺堅牢性（silent fallback / dtype merge / pandas 境界 / W-2 証跡）に関するものだったが・gap-closure plan 10-08 で採用された CR-01〜04 + WR-01〜06 を fail-loud 化・堅牢化し・core value「リーク防止」の鏡像である「silent fallback 禁止」を機械保証した。更に Task 3 で live-DB snapshot を再生し・SHA256 が修正前と完全一致したことで・(a) CR-02 の silent NaN merge は本番では発生していなかったこと・(b) WR-03 の直列化結果も不変であること・(c) §19.1 byte-reproducibility が完全証明されたこと・(d) Phase 11 入力 snapshot が不変であることを証明した。10-09 で PLAN truth の doc 不整合（10-06 baseline 79→35）も訂正し・コード変更なしで substantive 検証（SC#5 gate_pass=True）は 10-06 で達成済みのまま・文書正確性を確保した。

聖域回帰（gap-closure 後も GREEN 維持）:
- SC#1 PIT-correct (adversarial lookahead): GREEN
- SC#4 SAFE-01 (AST odds/ninki proxy 0件): GREEN
- §11.2 聖域 (W-2 候補 score diagnostic・test 窓 rank すり替え禁止): CR-04 で RuntimeError 格上げ・履行証跡欠損の構造的ブロック
- §19.1 byte-reproducibility: PASS（live-DB SHA256 完全一致）
- W-3 性能聖域 (per-race 予算 ≤0.30s/race + 準二次スケーリングガード・cProfile 上位3位 Python ループ無し): 緩和せず（WR-04 は検出力向上・既存テスト不変）
- FEATURE_COLUMNS 79/35 parity: GREEN（test_snapshot_repro + test_allowlist 32 passed）

残 deferred（本 phase 対象外・closed でない）: D-15 segment_eval（Phase 12 EVAL-01）・Info IN-01〜05（backlog 化）・WR-01 helper 大規模書き直し（backlog 化・docstring 契約 + adversarial テストで機械保証）・W-3 縮小版 5.0s 閾値（PLAN 01/07 で option-a 根拠再設定済み・NOT a gap）。

---

_Verified: 2026-06-27T09:30:00Z (re-verification after gap-closure 10-08/10-09)_
_Previous verified: 2026-06-27T08:30:00Z (initial verification)_
_Verifier: Claude (gsd-verifier)_
