---
phase: 10-opponent-strength-race-relative-features
plan: 01
subsystem: features/field_strength
tags: [feature-engineering, leak-prevention, pit-correct, odds-free, speed-figure, opponent-strength]
requires:
  - Phase 9 speed_figure.py::compute_speed_figure_for_history（source-as-of full-pipeline 再計算の基盤）
  - src/features/availability.py::CUTOFF_SEMANTICS（strict < 不変量の単一真の源）
provides:
  - src/features/field_strength.py::compute_field_strength_profile（D-06 第1段階・raw_history 全行に field_strength profile 8値を付与）
  - OPPONENT_ROLLING_AXIS / OPPONENT_ROLLING_K / SOURCE_RACE_BATCH_SIZE 定数（D-02/D-05/MEDIUM#3 事前登録）
  - obs_id 名前空間 SOURCE_ASOF_<race_nkey>_<kettonum>（CYCLE-3 MEDIUM #2 race×horse 単位・horse-level par）
affects:
  - PLAN 02（rolling.py 拡張 第2段階）が history の field_strength_* profile 列を前提に 21 feature を生成
  - PLAN 03（race_relative.py）の field_strength_adjusted_rank が field_strength_mean_mean_5 を消費（PLAN 02 経由）
  - PLAN 04（builder.py Step 5c）が compute_field_strength_profile(raw_history) を呼出（Step 5b 前 raw_history capture）
tech-stack:
  added: []
  patterns:
    - source-as-of full-pipeline recompute（CYCLE-2 HIGH-C2-1・raw history に合成 observation で compute_speed_figure_for_history を再実行）
    - per-source-race batch（CYCLE-3 MEDIUM #3・H² 積 materialize 回避）
    - horse-level par via obs_id（CYCLE-3 MEDIUM #2・target 経路と同 normalization）
    - available_at 関数内導出（CYCLE-3 MEDIUM #1・race_date 由来・Step 5b 後汚染 history 非依存）
    - 2層 PIT gate（layer1 値レベル source-as-of recompute + layer2 行レベル _pit_cutoff_prefilter・adversarial monkeypatch 可能）
key-files:
  created:
    - src/features/field_strength.py
    - tests/features/test_field_strength.py
  modified: []
decisions:
  - CYCLE-2 HIGH-C2-1: 相手 ability 値は obs_id 展開済み target-cutoff-contaminated speed_figure を再利用せず・raw history に合成 observation（SOURCE_ASOF_<race_nkey>_<kettonum>・feature_cutoff_datetime=source_race.available_at）で compute_speed_figure_for_history を再実行し full par+variant+speed_figure pipeline を source-as-of で再計算する（値レベルの source-vs-target-cutoff 保証・値の不変性）
  - CYCLE-3 MEDIUM #1: available_at は raw_history の race_date から関数内導出（speed_figure/available_at は必須列に含めない・Step 5b 後汚染 history への依存経路を構造的に閉じる）
  - CYCLE-3 MEDIUM #2: obs_id は SOURCE_ASOF_<race_nkey>_<kettonum>（race×horse 単位）とし・par groupby キーが obs_id 先頭なので各馬の par が horse 自身の pre-cutoff history で決定（target 経路と同 horse-level par normalization）
  - CYCLE-3 MEDIUM #3: per-source-race batch（SOURCE_RACE_BATCH_SIZE=100）で compute_speed_figure_for_history を呼出し・out.merge の H² 積 materialize を回避
  - D-02 Open Question #1 解決: OPPONENT_ROLLING_AXIS='rolling_speed_figure_mean_5'・OPPONENT_ROLLING_K=5 の1軸のみ（17倍計算量抑制・Phase 9 D-09 安定能力代表値）
  - D-04 発走馬特定: kakuteijyuni > 0 単一条件（live-DB 実証・tozaicd 不使用・拡張中止コードは意味不明）
  - source_available_at_by_race が source-as-of cutoff の唯一の真の源（adversarial test が leaky cutoff を注入可能・_build_source_asof_observation は raw_history の available_at でなく source_available_at_by_race を使う）
metrics:
  duration: 23min
  completed: 2026-06-26
  tasks: 1
  files: 2
  tests: 15 unit tests GREEN
status: complete
---

# Phase 10 Plan 01: 相手強度 field_strength profile（D-06 第1段階）Summary

D-06 第1段階として compute_field_strength_profile を実装し・raw_history 全行に source race 内 opponent profile 8値（mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage）を付与する。CYCLE-2 HIGH-C2-1（値レベルの source-vs-target-cutoff 保証・full par+variant+speed_figure pipeline の source-as-of 再計算）と CYCLE-3 MEDIUM #1/#2/#3（available_at 関数内導出・horse-level par・per-source-race batch で H² 積回避）を全て実装し・15 unit tests（value-invariance adversarial 含む）が GREEN。

## What Was Built

### 新規モジュール src/features/field_strength.py

- **compute_field_strength_profile(raw_history, observations=None) -> pd.DataFrame**: D-06 第1段階の公開 API。raw_history 全行に field_strength profile 8値を付与する（copy-not-rename・HIGH#5）。
- **_pit_cutoff_prefilter(expanded)**: opponent-vs-source gate（D-01 厳格版 strict <）。adversarial test が monkeypatch で `<=` に差替可能（speed_figure.py L98-118 / rolling.py L114-126 と対称）。
- **_compute_source_asof_opponent_speed_figures(raw_history, source_available_at_by_race)**: CYCLE-2 HIGH-C2-1 root-cause fix。obs_id 展開済み target-cutoff-contaminated speed_figure を再利用せず・raw history に合成 observation で compute_speed_figure_for_history を再実行し full par+variant+speed_figure pipeline を source-as-of で再計算する。available_at は raw_history の race_date から導出（CYCLE-3 MEDIUM #1）。per-source-race batch で H² 積 materialize 回避（CYCLE-3 MEDIUM #3）。
- **_build_source_asof_observation(source_race_rows)**: CYCLE-2 HIGH-C2-1 + CYCLE-3 MEDIUM #2。obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'（race×horse 単位・horse-level par）・feature_cutoff_datetime=source_race.available_at の合成 observation を構築。source_available_at_by_race を唯一の cutoff 真の源とするため available_at 列は source_available_at_by_race から取る（adversarial test が leaky cutoff を注入可能）。
- **_opponent_ability_latest_mean5(source_asof_speed_figures, source_available_at_by_race)**: CYCLE-2 HIGH-C2-1。full-pipeline 再計算済み speed_figure から opponent 毎 latest-K=5 mean を算出。obs_id から source_race_nkey を抽出して groupby キーに使う（展開フレームの race_nkey 列は opponent 過去走の race_nkey・source race 情報は obs_id に含まれる）。layer 2 の _pit_cutoff_prefilter を経由して値レベル + 行レベルの 2層 PIT 保証。
- **_topk_mean_clamped(values, k)**: D-05 top-k クランプ（rolling.py L183-192 _best2_mean_of_group idiom・nlargest で vectorized・決定論的）。
- **定数**: OPPONENT_ROLLING_AXIS='rolling_speed_figure_mean_5'（D-02 Open Question #1 解決）・OPPONENT_ROLLING_K=5・SOURCE_RACE_BATCH_SIZE=100（CYCLE-3 MEDIUM #3・事前登録）。

### テスト tests/features/test_field_strength.py（15 tests GREEN）

- Test 1 機能: PIT strict < opponent-vs-source（D-01・layer 1 = source-as-of recompute で same-day opponent を除外）
- Test 1 adversarial: source-as-of recompute cutoff を未来に引き上げると source race 以後の opponent 過去走が混入し ability 値が変化（検出力証明・false-pass 回避）
- Test 2: CYCLE-2 HIGH-C2-1 value-invariance（adversarial・layer 1 + layer 2 完全突破で R_MID が混入し値が変化）
- Test 2 across-targets: 値の不変性・複数 source race で同一 opponent の ability が一致 + byte-reproducible
- Test 3: obs_id 展開済み speed_figure / available_at 列への非依存（CYCLE-2 HIGH-C2-1 + CYCLE-3 MEDIUM #1）
- Test 4: D-04 発走馬特定（kakuteijyuni > 0・未発走除外・競走中止馬含む）
- Test 5: D-02 相手 rolling mean_5 1軸（OPPONENT_ROLLING_AXIS/K 定数）
- Test 6: D-03 profile 8値
- Test 7: D-05 top-k クランプ（opponent 2頭で top3=top5=mean）
- Test 8: coverage = valid_count / race_size（D-05）
- Test 9: copy-not-rename（HIGH#5）
- Test 10: byte-reproducible（§19.1）
- Test 11: fail-loud on missing required columns（CYCLE-3 MEDIUM #1・speed_figure/available_at は必須でない）
- Test 12: CYCLE-3 MEDIUM #2 horse-level par（obs_id race×horse 単位・正規表現で検証）
- Test 13: CYCLE-3 MEDIUM #3 SOURCE_RACE_BATCH_SIZE（定数事前登録 + バッチ境界決定性）

## CYCLE-2 HIGH-C2-1 実装の核心

CYCLE-2 HIGH-C2-1（10-REVIEWS.md L57-92, L181-209, L295）は行包含でなく値レベルの source-vs-target-cutoff 保証を要求する。本実装の核心:

1. **obs_id 展開済み speed_figure 再利用禁止**: compute_speed_figure_for_history(history, observations=feature_matrix) の戻り値は obs_id 展開済みで・各行の par/variant/speed_figure が target obs の feature_cutoff_datetime に依存する（speed_figure.py L402/510/635/655-657）。これを source-race opponent 流用すると (source, target] 区間の opponent レースが値レベルで混入する。
2. **full-pipeline source-as-of 再計算**: raw history（Step 5b 前・obs_id 未展開）に対し・obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'・feature_cutoff_datetime=source_race.available_at の合成 observation で compute_speed_figure_for_history を再実行する。par/variant/speed_figure の FULL pipeline が source-as-of cutoff で再計算される。
3. **値の不変性**: 同じ pre-source opponent race の再計算済み speed_figure は・どの target observation がその source race を消費しても同一（値の不変性）。これが行包含でなく値レベルの保証。
4. **2層 PIT gate**: layer 1 (source-as-of recompute が source cutoff を使う) + layer 2 (_pit_cutoff_prefilter で opponent.available_at < source_available_at を行レベルで重畳)。adversarial test が layer 1 + layer 2 の両方を無効化すると値が変化し・検出力を機械証明（Test 1 adversarial・Test 2）。

## TDD Gate Compliance

- RED commit: 5027149 (test(10-01): add failing tests for field_strength profile (RED))
- GREEN commit: d4b7a86 (feat(10-01): implement field_strength profile (GREEN))
- REFACTOR: 不要（実装は RED→GREEN で既にクリーン・ruff F401 GREEN・重複なし）

RED→GREEN gate 順序を満たす。15 tests GREEN・ruff GREEN。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking fix] source_available_at_by_race を唯一の cutoff 真の源に修正**
- **Found during:** GREEN 実装中（Test 1 adversarial で leaky cutoff が効かない問題）
- **Issue:** _build_source_asof_observation が source_race_rows の available_at（raw_history の race_date 由来）を使っていたため・adversarial test が source_available_at_by_race 経由で leaky cutoff を注入しても synth_obs の feature_cutoff_datetime に反映されなかった。
- **Fix:** _compute_source_asof_opponent_speed_figures で・batch_starters の available_at を source_available_at_by_race（caller が渡した source-as-of cutoff・adversarial test が leaky 値を注入可能）から取るようにした。これにより source_available_at_by_race が source-as-of cutoff の唯一の真の源になり・adversarial test の検出力が保証される。
- **Files modified:** src/features/field_strength.py
- **Commit:** d4b7a86

**2. [Rule 3 - Blocking fix] _opponent_ability_latest_mean5 の groupby キー修正**
- **Found during:** GREEN 実装中（valid_count が NaN になる問題）
- **Issue:** 展開フレームの race_nkey 列は opponent 過去走の race_nkey（source race でない）・source race 情報は obs_id に含まれる。元実装は race_nkey で groupby していたため source race 毎の集約ができなかった。
- **Fix:** obs_id から source_race_nkey を抽出（SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum> を rsplit）し・_source_race_nkey を groupby キーに使うようにした（speed_figure.py の obs_id 展開 idiom と対称）。
- **Files modified:** src/features/field_strength.py
- **Commit:** d4b7a86

**3. [Rule 3 - Blocking fix] adversarial テストの検出力設計調整**
- **Found during:** GREEN 実装中（horse-level par で単一過去走の speed_figure が0になる問題）
- **Issue:** CYCLE-3 MEDIUM #2 により par は horse 自身の pre-cutoff history の中央値。各 opponent が単一過去走の場合・par=time で speed_figure=0 になり馬の能力差が反映されず・adversarial test の検出力がなかった。
- **Fix:** Test 1 adversarial / Test 2 の合成データを各 opponent が5走以上の過去走を持つように変更し・leaky 版で latest-5 窓の構成が変わることで ability 値が変化するようにした。これはテスト設計の調整で・実装の契約（Plan の truths/acceptance）は不変。
- **Files modified:** tests/features/test_field_strength.py
- **Commit:** d4b7a86

### SAFE-01 token 表現の調整

Plan の action (10) は docstring での tozaicd 警告明記を求めるが・acceptance criteria は `grep -c tozaicd == 0` を要求する（planner-discipline-allow マーカー付き）。この競合を解消するため・コメント内の tozaicd を「EveryDB2 独自拡張の中止コードフィールド」に一般的化し・acceptance criteria の grep == 0 を満たしつつ D-04 Pitfall 1 警告の意図を保持した。

## Verification

- 単体テスト: `uv run pytest tests/features/test_field_strength.py -x -q` → 15 passed
- lint: `uv run ruff check src/features/field_strength.py tests/features/test_field_strength.py` → All checks passed!
- 回帰: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q` → 112 passed（features 全体・回帰なし）
- SAFE-01 下地: src/features/field_strength.py に tozaicd/odds/ninki/fukuodds/ninkij/tansyouodds の token が現れない（grep -c == 0・AST audit 本体は PLAN 07）

## Known Stubs

なし。compute_field_strength_profile は完全実装・全値が source-as-of 再計算 pipeline から算出される。PLAN 02（rolling.py 拡張）が本 profile 列を入力に 21 feature を生成する前提が整った。

## Self-Check: PASSED

- src/features/field_strength.py: FOUND
- tests/features/test_field_strength.py: FOUND
- commit 5027149 (RED): FOUND
- commit d4b7a86 (GREEN): FOUND
