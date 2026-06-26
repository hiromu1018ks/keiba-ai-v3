---
phase: 10-opponent-strength-race-relative-features
plan: 03
subsystem: features/race_relative
tags: [feature-engineering, leak-prevention, odds-free, target-only, race-relative, competition-ranking, additive-score]
requires:
  - Phase 9.1 rolling_speed_figure_mean_5 / best2_mean_5 / median_5（target 経路・horse-level par 由来）
  - Phase 10 PLAN 02 rolling.py::rolling_field_strength_mean_mean_5（PLAN 01 source-asof 経路・同一 horse-level par）
provides:
  - src/features/race_relative.py::compute_race_relative_features（FEAT-03 6 feature・target-only・race_id group-by）
  - src/features/race_relative.py::compute_candidate_score_diagnostics（W-2 係数妥当性証跡・PLAN 06 消費）
  - src/features/race_relative.py::_competition_rank_desc_within_race（D-10 min rank・na_option='keep'）
  - src/features/race_relative.py::_adjusted_score（D-11 additive score・D-12 coef）
  - src/features/race_relative.py::_gap_to_top_within_race / _gap_to_3rd_within_race（D-08 / REVIEW MEDIUM-7 tie 仕様）
  - 定数 ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5) / ADJUSTED_RANK_COEF_CANONICAL = 0.25（§11.2 聖域）
  - 定数 _SPEED_INDEX_AXES_FOR_RANK（D-07 3軸・mean5/best2_mean5/median5）
affects:
  - PLAN 04（builder.py）Step 7 で compute_race_relative_features(feature_matrix) を呼出（Step 6b drop 前に race_nkey が使える段階）
  - PLAN 06 run_phase10_evaluation.py が compute_candidate_score_diagnostics を消費し train/calib 窓の係数妥当性証跡を log 出力
tech-stack:
  added: []
  patterns:
    - target-only race_id group-by + transform（D-07・feature_matrix 上でのみ動作・過去走不適用）
    - competition ranking via pandas Series.rank(method='min', ascending=False, na_option='keep')（D-10・"1224" 方式・D-09 欠損 NaN 保持）
    - W-5 try/finally 一時列確実 drop（§11.2 聖域保護・候補別 score の feature 漏出機械防止）
    - W-2 diagnostic helper（copy 使用・feature_matrix 非破壊・純粋 dict 戻り値）
    - 3聖域 docstring（SAFE-01 odds-free / D-07 target-only / byte-reproducible）・speed_figure.py と対称
key-files:
  created:
    - src/features/race_relative.py
    - tests/features/test_race_relative.py
  modified: []
decisions:
  - D-10 competition ranking は pandas.Series.rank(method='min', ascending=False, na_option='keep') 標準 API で実装（同着同順位・"1224" 方式）
  - D-09 欠損馬は na_option='keep' で NaN 保持・母集団除外・最下位固定しない・sentinel 数値不使用
  - D-08 gap_to_3rd は REVIEW MEDIUM-7 tie 仕様（rank==3 の馬の mean_5 − self.mean_5・rank==3 が空位なら race 内全馬 NaN）で実装・3番目のソート値でない
  - D-08 gap_to_top は mean5 の max − self.mean5（competition ranking で1位確定後の1位馬の mean_5・同着1位は同値なので max で同等）
  - D-11/D-12 additive score 係数は ADJUSTED_RANK_COEF_CANONICAL=0.25 を事前登録公開定数・候補 {0.0,0.1,0.25,0.5} は train/calib 窓内のみ（W-2 diagnostic）
  - W-5 候補別 score の一時列（_rr_adjusted_score_canonical）は try/finally で確実 drop・Test 11 で戻り値 columns に残存しないことを機械保証
  - CYCLE-3 MEDIUM #2 scale 兼容性は docstring に明文化・horse-level par 同一前提（PLAN 01 の obs_id 設計選択に依存）
metrics:
  duration: 4min
  completed: 2026-06-26
  tasks: 1
  files: 2
  tests: 18 unit tests GREEN
status: complete
---

# Phase 10 Plan 03: レース内相対特徴量 FEAT-03（target-only・race_id group-by）Summary

FEAT-03 レース内相対特徴量 6 列（speed_index_rank 3軸・gap_to_top・gap_to_3rd・field_strength_adjusted_rank）を新規 `src/features/race_relative.py` に実装した。target observation のみ・`race_nkey` group-by + transform で competition ranking（D-10・"1224" 方式）を算出し・D-09 欠損馬は NaN 保持・D-08 gap（top/3rd・Open Question #2 + REVIEW MEDIUM-7 tie 仕様明文化）・D-11/D-12 additive score（coef=0.25 canonical 事前登録・候補 {0.0,0.1,0.25,0.5} 公開定数・§11.2 聖域）を実装した。W-5（候補別一時列の非残存・§11.2 聖域保護・Test 11 機械保証）・W-2（compute_candidate_score_diagnostics diagnostic helper・PLAN 06 消費）も完全実装した。18 unit tests GREEN・ruff GREEN。

## What Was Built

### 新規モジュール `src/features/race_relative.py`

- **モジュール docstring 3聖域**: SAFE-01 odds-free / D-07 target-only（feature_cutoff_datetime 時点で確定した rolling_speed_figure_mean_5 等のみ・当日結果不使用）/ byte-reproducible（決定論的 competition ranking）。speed_figure.py L1-32 と対称な形式。
- **imports + CUTOFF_SEMANTICS 実行時 assert**: `from src.features.availability import CUTOFF_SEMANTICS`・`assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"`（FEAT-03 は target-only で PIT は更に厳格・feature_cutoff_datetime 基準を明示）。
- **D-07 定数 `_SPEED_INDEX_AXES_FOR_RANK`**: 3軸 tuple（mean5 / best2_mean5 / median5）。各 axis が1つの rank 列を生成。
- **`_AXIS_TO_RANK_SUFFIX` mapping**: axis 列名から rank 列名の suffix を機械導出（rolling_speed_figure_mean_5 → mean5 等）。
- **D-12 事前登録定数（§11.2 聖域）**: `ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5)` 公開定数（0.0 は baseline・raw mean5 rank と同値）・`ADJUSTED_RANK_COEF_CANONICAL = 0.25` canonical 初期値。docstring で「test 窓で係数を選び直すのは禁止（§11.2 聖域）」を明記。
- **D-10 `_competition_rank_desc_within_race(s)` helper**: `s.rank(method="min", ascending=False, na_option="keep")`。docstring で [100, 95, 95, 90] → [1, 2, 2, 4] の例を明示（PAT§ L144-153 skeleton・D-09 欠損馬 NaN 保持・母集団除外）。
- **D-11/D-12 `_adjusted_score(mean5, fs_mean5, coef)` helper**: `mean5 + coef * fs_mean5`。docstring で「差/比は不採用（強い相手と走ってきた馬を不当に下げるため）」と CYCLE-3 MEDIUM #2 par-scale 兼容性（PLAN 01 horse-level par 設計依存）を明記。
- **D-08 `_gap_to_top_within_race(mean5)` helper**: `top_val = mean5.max()`・`return top_val - mean5`。competition ranking で1位確定後の1位馬の mean_5 を使う（同着1位は同値なので max で同等）。
- **D-08 `_gap_to_3rd_within_race(mean5)` helper（REVIEW MEDIUM-7 tie 仕様明文化）**: `ranks = mean5.rank(method="min", ascending=False, na_option="keep")`・`third_mask = ranks == 3`・rank==3 の馬が存在すればその mean_5 − self.mean_5・存在しなければ race 内全馬 NaN。[100, 95, 95, 90] は competition rank [1,2,2,4] で rank==3 が空位 → 全馬 NaN・tie 無し [100, 95, 90, 85] は rank [1,2,3,4] で算出。docstring に例明示。
- **`compute_race_relative_features(feature_matrix)` メイン関数**:
  - 入力検証: 必須列（race_nkey・_SPEED_INDEX_AXES_FOR_RANK の3列・rolling_field_strength_mean_mean_5）を assert（fail-loud・ValueError）。
  - copy-not-rename: `result = feature_matrix.copy()`（HIGH #5）。
  - D-07 rank 3軸: for axis_col in _SPEED_INDEX_AXES_FOR_RANK で speed_index_rank_{mean5,best2_mean5,median5} を `groupby("race_nkey").transform(_competition_rank_desc_within_race)` で付与。
  - D-08 gap: gap_to_top / gap_to_3rd を `groupby("race_nkey")["rolling_speed_figure_mean_5"].transform(...)` で付与。
  - D-11 adjusted_rank: canonical 0.25 の adjusted_score を一時列 `_rr_adjusted_score_canonical` に格納し rank 算出後・try/finally で確実 drop（W-5・§11.2 聖域保護）。
  - return result（6 列追加）。
- **W-2 `compute_candidate_score_diagnostics(feature_matrix, split_mask=None) -> dict`**: 候補 {0.0,0.1,0.25,0.5} の adjusted_score 分布統計（mean/std/min/max/p10/p50/p90 + adjusted_rank_mean/adjusted_rank_std）を dict で返す。feature_matrix に列を追加しない（copy 使用・戻り値は純粋 dict・FEATURE_COLUMNSを汚さない）。0.0 は baseline（raw mean5 rank と同値）。split_mask=None は全行対象。PLAN 06 run_phase10_evaluation.py が消費し train/calib 窓の分布を log 出力（§11.2 聖域・test 窓 rank すり替えではない）。
- **`__all__`**: `["compute_race_relative_features", "compute_candidate_score_diagnostics"]`。

### テスト `tests/features/test_race_relative.py`（18 tests GREEN）

- Test 1 D-10: competition ranking 同着（[100, 95, 95, 90] → [1, 2, 2, 4]・"1224" 方式・min rank・dense でない）
- Test 1b D-09: 欠損馬 NaN 保持・母集団除外（na_option='keep'・最下位固定でない）
- Test 2 D-07: speed_index_rank 3軸（mean5 / best2_mean5 / median5 列名）・race_id 内 rank
- Test 3 D-09: 欠損馬は rank も NaN・母集団から除外
- Test 4 D-08: gap_to_top = top(1位).mean5 − self.mean5（race_a: [0, 5, 5, 10]）
- Test 5 D-08: gap_to_3rd 同着無し・size>=3 で算出（[100, 95, 90, 85] → [−10, −5, 0, 5]）
- Test 5c D-08: gap_to_3rd size<3 は race 内全馬 NaN
- Test 5b REVIEW MEDIUM-7: gap_to_3rd tie 仕様（[100, 95, 95, 90] は rank==3 空位 → 全馬 NaN・tie 無し [100, 95, 90, 85] は算出）
- Test 6 D-11/D-12: field_strength_adjusted_rank coef=0.25 canonical（scores [105, 98, 100.5, 105] → rank [1, 4, 3, 1]）
- Test 6b CYCLE-3 MEDIUM #2: scale 兼容性（両項同 scale で加算が意味ある順序付け）
- Test 7a D-12: ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5)・0.0 baseline
- Test 7b D-07: _SPEED_INDEX_AXES_FOR_RANK 3軸定数
- Test 8 D-07: target-only（出力行数 == 入力行数・過去走誤適用防止）
- Test 9 HIGH#5: copy-not-rename（入力破壊せず・6 列 copy 追加・期待6列と一致）
- Test 10 fail-loud: 必須列欠落時 ValueError（race_nkey / rolling_field_strength_mean_mean_5）
- Test 11 W-5: 候補別一時列の非残存（戻り値 columns に候補別 score 列含まれない・§11.2 聖域保護）
- Test 12a W-2: compute_candidate_score_diagnostics dict 構造・0.0 は raw mean5 rank と一致・feature_matrix 非破壊
- Test 12b W-2: split_mask で行抽出した分布（全行と一部で値が変わる）

## CYCLE-3 MEDIUM #2 (par-scale 兼容性) 実装の核心

CYCLE-3 MEDIUM #2（10-REVIEWS.md L222）は rolling_speed_figure_mean_5（target 経路・horse-level par 由来）と rolling_field_strength_mean_mean_5（PLAN 01 source-asof 経路）が同一 horse-level par normalization 上にあることを前提として add が成立することを要求する。本実装の核心:

1. **PLAN 01 設計依存の明文化**: `_adjusted_score` docstring と module docstring で・両項の scale 整合は PLAN 01 が obs_id を `SOURCE_ASOF_<race_nkey>_<kettonum>` として target 経路と同 horse-level par に揊えたことに依存すると明示。race 単位 obs_id なら scale 不一致で加算が不正確化する。
2. **検証**: Test 6b で両項が同 scale の場合 adjusted_score が race_id 内で意味のある順序付けを与えることを assert。
3. **非リーク性**: 両項とも strict `<` PIT-correct 経路（target 経路は Phase 9.1・source-asof 経路は PLAN 01 の full pipeline 再計算）を経ており・市場情報 proxy 不使用（SAFE-01）・feature_cutoff_datetime 時点で確定した値のみを母集団とする。

## TDD Gate Compliance

- RED commit: 3a8ec5d (test(10-03): add failing tests for race_relative features (RED)・12 テスト枠 + 補助テスト)
- GREEN commit: 71099b0 (feat(10-03): implement race_relative features (GREEN))
- REFACTOR: 不要（実装は RED→GREEN で既にクリーン・ruff I001 auto-fix 適用済・重複なし）

RED→GREEN gate 順序を満たす。18 tests GREEN・ruff GREEN。

## Deviations from Plan

None - plan executed exactly as written. W-5 と W-2 は PLAN の `<must_haves>` truths と acceptance criteria で要求されていたが・本 PLAN 実装で完全に充足した（追加逸脱なし）。下記は設計上のメモ:

### 設計上のメモ（逸脱でなく・PLAN の明記の実現）

**1. `_gap_to_top_within_race` の実装**: PLAN action (7) は「race_id group で mean_5 降順1位・3位を特定（competition ranking 後）」と書くが・1位の mean_5 は max と同等（同着1位は同値なので max で OK）のため・`mean5.max() - mean5` で実装した。PLAN の意図（competition ranking で順位確定後の1位馬の mean_5）と機能的に同等。docstring で明示。

**2. `_gap_to_3rd_within_race` の空位検出**: REVIEW MEDIUM-7 仕様（rank==3 が空位なら race 内全馬 NaN）を実装するため・`ranks == 3` の any() で判定する。PLAN action (7) と Test 5b の両契約を満たす。

**3. diagnostic helper の rank 計算**: coef=0.0 の場合は raw mean5 rank・それ以外は score の rank とするため・`if coef == 0.0 ... else ...` の分岐で実装。PLAN が「0.0 は baseline（raw mean_5 rank と同値）」と明記する通りの挙動。

## SAFE-01 / core value 整合性

本 PLAN は `src/features/race_relative.py` と `tests/features/test_race_relative.py` のみ作成。race_relative.py は市場情報 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）を使用せず・入力は rolling_speed_figure_mean_5 / best2_mean_5 / median_5（Phase 9.1 target 経路・horse-level par）と rolling_field_strength_mean_mean_5（PLAN 01 source-asof 経路・同一 horse-level par）のみ。`grep -Ec "odds|ninki|fukuodds|ninkij|tansyouodds"` src/features/race_relative.py == 0（AC7 GREEN・SAFE-01 下地）。PLAN 07 adversarial AST audit が完全証明する前提が整った。

target-only（D-07）は feature_matrix 上でのみ動作・過去走 history には適用しない（Pitfall 4 回避・Test 8 機械保証）。rank 母集団は feature_cutoff_datetime 時点で確定した rolling_speed_figure_mean_5 等のみ・当日結果不使用。

## Verification

- 単体テスト: `uv run pytest tests/features/test_race_relative.py -x -q` → 18 passed
- lint: `uv run ruff check src/features/race_relative.py tests/features/test_race_relative.py` → All checks passed!（I001 auto-fix 適用後・手元コード clean）
- Phase 10 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/test_race_relative.py tests/features/test_field_strength.py tests/features/test_rolling.py -q` → 51 passed（PLAN 01/02/03 全て回帰 safe）
- audit suite 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q` → 16 passed（本 PLAN は audit 対象外だが回帰なし）
- AC1-7 機械検証 GREEN（関数存在・method='min' / ascending=False / na_option='keep'・候補定数・3軸定数・6出力列・W-2 diagnostic 関数・SAFE-01 0 件・__all__）

### Deferred Issues（PLAN 04 で解消される設計上の前提）

`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/` で3件が失敗する:

- `test_no_registered_feature_column_all_nan_end_to_end`（E2E・availability registry に FEAT-03 系統未登録）
- `test_registry_rolling_systems_match_rolling_impl`（3者 parity 検査・registry と availability._ROLLING_SYSTEMS_FOR_RESERVED に FEAT-03 が未登録）
- `test_cr01_rolling_aligned_by_canonical_key_across_distinct_cutoffs`（E2E・同上）

これらは PLAN 02 の段階で PLAN SUMMARY に「Deferred Issues」として既に記録済みの3件と同一で・PLAN 04（availability.yaml + availability.py 拡張 + builder.py Step 7/7b 挿入・FEATURE_COLUMNS 更新）で解消される設計上の前提。本 PLAN 03 の acceptance criteria（test_race_relative.py 全体 GREEN・ruff）の対象外・PLAN 03 単体の不完全さでなく Phase 10 DAG 内の PLAN 間依存の正常な振舞。

## Known Stubs

なし。compute_race_relative_features は完全実装・全6列が race_id group-by + transform で算出される。W-2 diagnostic helper も完全実装。PLAN 04（builder.py）Step 7 で `compute_race_relative_features(feature_matrix)` が呼ばれる前提が整った。

## Self-Check: PASSED

- src/features/race_relative.py: FOUND
- tests/features/test_race_relative.py: FOUND
- commit 3a8ec5d (RED): FOUND
- commit 71099b0 (GREEN): FOUND
