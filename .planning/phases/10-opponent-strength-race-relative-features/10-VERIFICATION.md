---
phase: 10-opponent-strength-race-relative-features
verified: 2026-06-27T08:30:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "W-3 性能ゲート（絶対 5.0s 閾値）"
    addressed_in: "Phase 10 gap-closure（同一 Phase 内・PLAN 01/07 で 2026-06-27 option-a により根拠再設定で解決済み・NOT a gap）"
    evidence: "10-01-PLAN L217 / 10-07-PLAN L28-30, L181-193: 絶対閾値を per-source-race 線形予算(≤0.30s/race) + 準二次スケーリングガードに根拠再設定（緩和でなく根拠再設定・聖域遵守）。test_no_python_loop_hot_spot GREEN（cProfile 上位3位に Python ループ無し）で原理証明済み。"
  - truth: "10-REVIEW.md 4 Critical / 6 Warning / 5 Info"
    addressed_in: "Phase 10 gap-closure（`/gsd-plan-phase 10 --gaps`）"
    evidence: "10-REVIEW.md L442-444: 核心のリーク防止機構は手厚く・指摘4件は silent fallback / dtype merge / pandas 境界 / W-2 証跡など周辺堅牢性。ユーザー DEFER ALL 決定。"
  - truth: "D-15 segment_eval（10-06）column-name mismatch"
    addressed_in: "Phase 12 EVAL-01"
    evidence: "参照用 only・gate 判定に使わず（Brier/LogLoss/AUC の3条件のみ gate）・Phase 12 EVAL-01 で正式対応。"
  - truth: "PLAN truth doc 不整合（10-05 FEATURE_COLUMNS=106 vs 79・10-06 baseline 79 vs 35）"
    addressed_in: "documentation accuracy（substantive verification 達成済み）"
    evidence: "実装上は registry から動的導出される FEATURE_COLUMNS で 106 columns 自動追従・substantive 検証は達成。doc 表記の数値不正は gap-closure 対象。"
---

# Phase 10: Opponent Strength & Race-Relative Features Verification Report

**Phase Goal:** 過去走の相手の as-of 能力平均（`field_strength`）と、レース内相対特徴量（`speed_index_rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`）を、Phase 9 のスピード指数を前提として odds-free・PIT-safe に追加する。複勝の「相対競争・各馬独立事象でない」性質を特徴量層で表現する。
**Verified:** 2026-06-27T08:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (SC#1–SC#5)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC#1 | 相手強度特徴量が PIT-correct（as-of 定義明文化・当日結果不使用・未来能力の遡及注入なし・adversarial lookahead テスト GREEN） | ✓ VERIFIED | `src/features/field_strength.py` 621行・実質的実装。厳格版 D-01（strict `<`）採用・`_pit_cutoff_prefilter` L121 で行レベル PIT gate・`_compute_source_asof_opponent_speed_figures` で source-as-of full pipeline 再計算（CYCLE-2 HIGH-C2-1 値レベル保証・obs_id 展開済み speed_figure 再利用禁止・raw_history に合成 observation で再計算）。`tests/features/test_field_strength.py` 18 テスト（adversarial lookahead・value-invariance・same-day opponent 混入検出含む）全 GREEN。特に `test_opponent_vs_source_pit_strict_less_adversarial` / `test_cycle2_high_c2_1_value_invariance` / `test_cycle2_high_c2_1_value_invariance_across_targets` が load-bearing invariant を機械証明。 |
| SC#2 | レース内相対特徴量が race_id 単位で future-information なし・同着/欠損境界処理明文化 | ✓ VERIFIED | `src/features/race_relative.py` 404行・実質的実装。race_nkey group-by + transform で race_id 単位計算・target observation のみ（history 行混入禁止・test_target_only_no_history_rows）。同着 = competition ranking（"1224" 方式・D-10）・欠損 = `na_option="keep"` で母集団除外・最下位固定しない（D-09）・gap_to_3rd tie 仕様明文化（REVIEW MEDIUM-7・同着2位で rank==3 空位時は全馬 NaN）。`tests/features/test_race_relative.py` 18 テスト全 GREEN・tie/missing/tie-at-2nd/scale-compatibility を網羅。 |
| SC#3 | 追加特徴量を含む feature snapshot が byte-reproducible・registry↔Parquet parity・§12.4 metadata 反映 | ✓ VERIFIED | snapshot `feature_matrix_20260626-1a-opponentstrength-v1.parquet`（108MB・106 columns・554,267 rows）+ manifest（sha256=c25ae556...・feature_count=106・schema_version=0.6.0・feature_cutoff_rule='race_date - 1 day'・dataset_version v1.0.0）。registry `src/config/feature_availability.yaml` 711行・schema_version 0.6.0・Phase 10 の 27 feature（rolling_field_strength 21 + race_relative 6）を明示登録・cutoff_semantics（strict_less_than / Asia/Tokyo）仕様化。`tests/features/test_snapshot_repro.py` 16 テスト GREEN（test_byte_reproducible_by_hash・test_sha256_covers_parquet_bytes_only・test_phase10_byte_reproducible_with_27_new_features・test_phase10_metadata_feature_availability_version 含む）。Parquet schema が 106 列と manifest feature_count=106 と一致（registry↔Parquet parity）。Level-4 data-flow: 27 Phase 10 列に実際の非-null データが流れる（rolling_field_strength_mean_latest_1: 75,008 non-null・speed_index_rank_mean5: 36,921 non-null・rank 分布 median=5.0/max=18.0 = フィールドサイズ対応・妥当）。 |
| SC#4 | オッズ/人気 proxy 混入がないことを adversarial audit で証明（SAFE-01） | ✓ VERIFIED | `tests/audit/test_audit_field_strength.py` 7 テスト GREEN・5段階鋳型（AST Name/Attribute + SQL 文字列リテラル REVIEW H3 odds-in-SQL 拡張 + FEATURE_COLUMNS allowlist + false-pass 回避 + lookahead 注入・値の不変性）。Test 1/2 で `field_strength.py`/`race_relative.py` の AST から odds/ninki/fukuodds/ninkij/tansyouodds proxy 0件を静的証明（実際の proxy token 出現数 0・確認済み）。Test 4 false-pass detection power で意図的注入を guard が検出することを証明。Test 5/6 で 2層 PIT gate 完全突破 adversarial で guard 有効性を逆証明。src/audit/report.py 359行で SAFE-01 聖域を report 化。 |
| SC#5 | live-DB snapshot が v1.0 LightGBM 再学習で Brier/LogLoss/AUC 現行水準を悪化させない（D-16 許容幅内・SC#5 gate） | ✓ VERIFIED | `reports/10-evaluation/10-evaluation.json` + `10-evaluation.md`: gate_pass=True（3/3 D-16 許容幅内）。Brier delta=-0.00022 (tol ≤+0.002) PASS・LogLoss delta=+0.00487 (tol ≤+0.005) PASS・AUC delta=+0.00180 (tol ≥-0.005) PASS。W-3 category_map bit_identical=True（baseline/phase10 cat_map hash 同一）。W-2 candidate score diagnostics status=ok（0.25 canonical 妥当性証拠・train/calib 窓内のみ・§11.2 聖域）。§15.2 binning import 再利用確認（CALIBRATION_CURVE_BINS=10 等の定数再定義禁止）。 |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/features/field_strength.py` | SC#1 source-as-of field_strength profile 8値 | ✓ VERIFIED | 621 lines・compute_field_strength_profile + 5 helper（PIT prefilter・source-asof observation・source-asof recompute・opponent ability・top-k clamped）。 |
| `src/features/race_relative.py` | SC#2 race_id group-by rank/gap/adjusted_rank | ✓ VERIFIED | 404 lines・compute_race_relative_features + competition ranking helper（D-10・D-09・D-08・D-11/D-12 全決定反映）。 |
| `src/features/rolling.py` | D-13 21 feature rolling 集約 | ✓ VERIFIED | 949 lines・_FIELD_STRENGTH_AXES・D-13 (axis, window) 21 feature・strict < cutoff PIT gate。 |
| `src/features/builder.py` | Step 5c/5d/7/7b 統合 | ✓ VERIFIED | 892 lines・Step 5c raw_history → compute_field_strength_profile・Step 7 feature_matrix → compute_race_relative_features・registry derived FEATURE_COLUMNS。 |
| `src/config/feature_availability.yaml` | registry↔Parquet parity・schema_version 0.6.0 | ✓ VERIFIED | 711 lines・schema_version "0.6.0"・Phase 10 27 feature 明示登録・cutoff_semantics strict_less_than。 |
| `src/features/snapshot.py` | byte-reproducible snapshot | ✓ VERIFIED | 447 lines・sha256 (Parquet bytes only・metadata excluded)・feature_count・§12.4 metadata。 |
| `snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet` | live-DB snapshot・106 features | ✓ VERIFIED | 108MB・106 columns・554,267 rows・sha256 c25ae556...。 |
| `snapshots/feature_matrix_20260626-1a-opponentstrength-v1.manifest.yaml` | §12.4 metadata 完備 | ✓ VERIFIED | feature_count=106・schema_version 0.6.0・feature_cutoff_rule・dataset_version v1.0.0。 |
| `scripts/run_phase10_evaluation.py` | SC#5 非劣化 gate 実行 | ✓ VERIFIED | 820 lines・D-16 許容幅判定・W-3 cat_map bit-identity・W-2 candidate score diagnostics・§15.2 binning import。 |
| `src/model/data.py` | registry derived FEATURE_COLUMNS allowlist | ✓ VERIFIED | 722 lines・FEATURE_COLUMNS = _derive_feature_columns()（registry 動的導出・106 自動追従）・make_X_y 厳密一致 assert。 |
| `src/audit/report.py` | SAFE-01 聖域 report | ✓ VERIFIED | 359 lines・SC#4 SAFE-01 proxy 排除・PIT 保証・odds_snapshot_policy 検査を report 化。 |
| `reports/10-evaluation/{10-evaluation.json,10-evaluation.md}` | SC#5 gate 結果 | ✓ VERIFIED | gate_pass=True・3条件全 D-16 許容幅内・delta 基準 baseline 実測値。 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `builder.py` Step 5c | `field_strength.compute_field_strength_profile` | `raw_history` 第1引数・observations=feature_matrix | WIRED | builder.py L554-556・raw_history は Step 5b 前・obs_id 未展開・CYCLE-2 HIGH-C2-1 前提・test_builder_step5c_passes_raw_history_not_history で保証。 |
| `builder.py` Step 7 | `race_relative.compute_race_relative_features` | `feature_matrix` group-by race_nkey | WIRED | builder.py L685-687・test_builder_has_step7_race_relative_call で保証。 |
| `field_strength.py` | `compute_speed_figure_for_history` (Phase 9) | synth_obs (obs_id=SOURCE_ASOF_<race_nkey>_<kettonum>) | WIRED | field_strength.py L194-289・source-as-of full pipeline 再計算・test_obs_id_expanded_reuse_forbidden_and_available_at_derivation で保証。 |
| `rolling.py` | `field_strength` profile 8値 | history 列 source・_FIELD_STRENGTH_AXES | WIRED | rolling.py L88-119・D-13 21 feature 生成・test_rolling.py 18 テスト GREEN。 |
| `data.py` | `feature_availability.yaml` registry | FEATURE_COLUMNS = _derive_feature_columns() | WIRED | data.py L214・test_feature_columns_allowlist_derived_from_registry で保証。 |
| `snapshot.py` | §12.4 Parquet metadata | feature_count / feature_cutoff_rule / dataset_version / sha256 | WIRED | snapshot.py L329/349/380/403/429・test_metadata_contains_12_4_keys・test_phase10_metadata_feature_availability_version GREEN。 |
| `run_phase10_evaluation.py` | `trainer/evaluator` | Brier/LogLoss/AUC 計算・D-16 許容幅判定 | WIRED | reports/10-evaluation/10-evaluation.json に baseline/phase10/delta/tolerance/gate_pass 全完備。 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `feature_matrix_20260626-1a-opponentstrength-v1.parquet` | rolling_field_strength_mean_latest_1 | field_strength.py source-as-of recompute → rolling.py D-13 集約 | Yes (75,008 non-null / 100,000 row-group・実データ) | ✓ FLOWING |
| 同上 | speed_index_rank_mean5 | race_relative.py race_nkey group-by | Yes (36,921 non-null・rank median=5.0/max=18.0 = フィールドサイズ対応) | ✓ FLOWING |
| 同上 | field_strength_adjusted_rank | race_relative.py (mean5 + 0.25 * fs_mean5) の race_id 内 rank | Yes (33,010 non-null・rank median=5.0/max=18.0) | ✓ FLOWING |
| 同上 | gap_to_top / gap_to_3rd | race_relative.py race_id 内 top/3rd - self | Yes (36,921 / 35,633 non-null・gap_to_3rd は同着2位で rank==3 空位時に NaN・仕様通り) | ✓ FLOWING |

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
| builder Phase 10 step ordering + registry derivation | `pytest tests/features/test_allowlist.py + test_rolling.py` | 16 + 18 passed | ✓ PASS |
| snapshot.md gate verdict | cat reports/10-evaluation/10-evaluation.md | PASS (3条件全て D-16 許容幅内) | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — Phase 10 は conventional probe（`scripts/*/tests/probe-*.sh`）を宣言しておらず・検証は pytest behavioral spot-checks + adversarial tests で完結。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| FEAT-02 | 10-01, 10-02, 10-04 | 相手強度補正特徴量（field_strength as-of 能力平均・odds-free・PIT-safe） | ✓ SATISFIED | src/features/field_strength.py + rolling.py 21 feature + builder.py Step 5c/5d・SC#1 PIT gate GREEN・REQUIREMENTS.md で Complete マーク。 |
| FEAT-03 | 10-03, 10-04 | レース内相対特徴量（rank / gap_to_top / gap_to_3rd / field_strength_adjusted_rank） | ✓ SATISFIED | src/features/race_relative.py 6 feature + builder.py Step 7・SC#2 race_id group-by + tie/missing 仕様 GREEN・REQUIREMENTS.md で Complete マーク。 |
| SAFE-01 | 10-07（全 Phase 横断聖域） | オッズ/人気 proxy を p モデル特徴量に入れない・adversarial audit で証明 | ✓ SATISFIED | tests/audit/test_audit_field_strength.py 7 テスト GREEN・AST 静的解析で odds/ninki proxy 0 件・lookahead 注入で PIT 保証逆証明・REQUIREMENTS.md で Complete マーク。 |

孤立要件（ORPHANED）: なし。FEAT-02/FEAT-03/SAFE-01 全て Phase 10 PLAN で明示的に要求 ID を宣言し・REQUIREMENTS.md でも Phase 10 → Complete とマークされている。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | - | - | - | Phase 10 新モジュール 4 file（field_strength / race_relative / audit/report / run_phase10_evaluation）に TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER marker 0 件・placeholder prose 0 件。odds/ninki proxy も 0 件（SC#4 SAFE-01 聖域）。 |

### Human Verification Required

（なし）

全 truth が adversarial / behavioral テストで機械証明されており・人間確認が必要な視覚/UX/リアルタイム要素は存在しない。W-3 縮小版性能テスト（~190s @1000 race）・production-scale smoke（~110s）・cProfile hot spot（~27s）は default skip だが KEIBA_RUN_PERF_TESTS=1 で実行可能・cProfile 核心 GREEN は実証済み。

### Gaps Summary

（なし — status: passed）

核心のリーク防止機構（source-as-of full-pipeline 再計算・行レベル PIT filter・AST audit・adversarial value-invariance）はすべて機械証明され・SC#1–SC#5 全てが実データ・実テスト・実メトリクスで裏付けられた。10-REVIEW.md の 4 Critical / 6 Warning / 5 Info は核心バリュー（リーク防止）でなく周辺堅牢性（silent fallback / dtype merge / pandas 境界 / W-2 証跡）に関するもの・ユーザー決定で Phase 10 gap-closure へ DEFER 済み・本 verify の対象外（known_deferred_items で明示）。

---

_Verified: 2026-06-27T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
