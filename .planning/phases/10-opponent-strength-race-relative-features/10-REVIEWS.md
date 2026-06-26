---
phase: 10
reviewers: [codex, claude]
reviewed_at: 2026-06-26T11:05:00Z
cycle: 3
plans_reviewed:
  - 10-01-PLAN.md
  - 10-02-PLAN.md
  - 10-03-PLAN.md
  - 10-04-PLAN.md
  - 10-05-PLAN.md
  - 10-06-PLAN.md
  - 10-07-PLAN.md
source_grounding: codex (default model, xhigh reasoning) AND claude (separate --print session) — both ran inside the project git working tree; all file:line citations were verified against the live repo. Both reviewers independently reached the same verdict: the Cycle-2 root-cause fix is GENUINE and all four Cycle-2 HIGHs are FULLY RESOLVED.
---

# Cross-AI Plan Review — Phase 10 (Cycle 3 — FINAL convergence cycle)

> Cycle 3 (final) of a convergence loop. Cycle 2 raised 3 HIGH (C2-1/C2-2/C2-3) +
> 1 MEDIUM (C2-4) on a single root cause: per-row `speed_figure` is target-cutoff-
> dependent via per-`obs_id` par/variant in `speed_figure.py`, so reusing it for
> source-race opponent ability leaks at the value level even when filtered by a
> row-level cutoff gate. The Cycle-2 revision replaced the flawed approach with a
> source-as-of full-pipeline recompute (`_compute_source_asof_opponent_speed_figures`
> + `_build_source_asof_observation`), captures `raw_history` before builder Step 5b's
> obs_id expansion (10-04), and changed adversarial tests from row-inclusion to
> VALUE-INVARIANCE assertions.
>
> **Cycle-3 outcome: the Cycle-2 root-cause fix is GENUINE.** Both reviewers (Codex +
> Claude) independently and unanimously confirm that C2-1/C2-2/C2-3/C2-4 are all
> **FULLY RESOLVED** at the plan level, with source-grounded evidence traced through
> `speed_figure.py` and `builder.py`. The value-invariance adversarial test would
> genuinely FAIL under the broken implementation. No HIGH remains. H3/H5/H6 from
> Cycle 1 are not regressed. The only residual findings are 3 non-leakage
> MEDIUM concerns about plan-level correctness/feasibility (KeyError on `available_at`,
> par-scale asymmetry, merge cardinality) that are invisible to `/gsd-execute-phase`
> until incorporated into PLAN.md.

---

## Cycle-2 HIGH resolution verdicts (at a glance)

| Cycle-2 HIGH | Cycle-3 verdict | Why |
|---|---|---|
| C2-1 (10-01 root cause: per-row speed_figure target-cutoff-dependent) | **FULLY RESOLVED** | The synth_obs approach (`obs_id='SOURCE_ASOF_<race_nkey>'`, `feature_cutoff_datetime=source_race.available_at`) reuses `compute_speed_figure_for_history` as-is; because par/variant groupby keys start with `obs_id` (`speed_figure.py:401-402, 509-510`), the resulting par/variant/speed_figure are a function of `source_race.available_at` only — no target cutoff enters. Batching all source races into one call preserves value-invariance (group keys are obs_id-scoped). Verified by both reviewers. |
| C2-2 (10-02 downstream: 21 rolling_field_strength_* inherit C2-1) | **FULLY RESOLVED** | 10-02 Test 9 verifies both polluted→polluted and clean→clean propagation; with C2-1 resolved the profile is clean so the 21 features inherit PIT-correctness via the existing `_pit_cutoff_prefilter` (strict `<`) + obs_id group. |
| C2-3 (10-04 integration order: builder Step 5b contaminates history before Step 5c) | **FULLY RESOLVED** | 10-04 L116 saves `raw_history = history.copy()` BEFORE Step 5b (builder.py:528 rebinds `history` to the obs_id-expanded frame); Step 5c passes `raw_history` not `history`. Copy semantics are correct (rebinding the name does not mutate the saved copy). Test 9 mechanically asserts the Step 5c input has no obs_id column. |
| C2-4 (10-07 audit blind spot: row-inclusion test misses value-level leak) | **FULLY RESOLVED** | 10-07 Test 7b + T-10-29b add a value-invariance assertion (same pre-source opponent race → bit-identical speed_figure across target cutoffs T1<T2) alongside the row-inclusion check. Paired with 10-01 Test 2. |

## Cycle-1 HIGH regression check

| Cycle-1 HIGH | Cycle-3 verdict | Evidence |
|---|---|---|
| H3 (10-07 odds-in-SQL scanner) | **RESOLVED — no regression** | Existing scanner excludes `odds` from SQL literal checks at `tests/audit/test_audit_speed_figure.py:39-48`. 10-07 Test 4 + T-10-28b add odds-in-SQL detection for field_strength/race_relative with whitelist `['odds-free','odds_snapshot_policy']`. |
| H5 (10-05 metadata key) | **RESOLVED — no regression** | Actual key is `feature_availability_version` (`snapshot.py:62,71`). 10-05 asserts the exact key + absence of the `schema` variant (L114, L129). |
| H6 (10-06 orchestrator API) | **RESOLVED — no regression** | `train_and_predict` requires label-joined `feature_df` + kwargs (`orchestrator.py:234-258`). 10-06 uses the correct 5-step chain (load_feature_matrix → load_labels → build_training_frame → load_frozen_maps → train_and_predict), mirroring `run_speed_figure_stopgate.py:583-622`. |

---

## Why the Cycle-2 fix is genuine (consensus, with code walkthrough)

Both reviewers independently traced the same evidence chain and reached the same
conclusion. The key mechanical facts, all in `src/features/speed_figure.py`:

1. **The leak mechanism was real (Cycle 2 was correct).** `compute_speed_figure_for_history(history, observations=feature_matrix)` returns an `obs_id`-expanded frame (`:635` `out.merge(obs_keys, on="kettonum")`; `:658` `result = with_variant`), where each row's par/variant/speed_figure depends on the target observation's `feature_cutoff_datetime` (par groupby `["obs_id","_jyocd","_trackcd","_kyori"]` `:401-402`; variant groupby `["obs_id","_source_race_date","_jyocd","_surface"]` `:509-510`; `speed_figure = (par_sec - time_sec + variant_sec) * pps_per_row` `:691`). `tests/features/test_speed_figure_pit.py:197-220` demonstrates O_early/O_late getting different `par_sec` under different cutoffs.

2. **The fix exploits that same structure.** `_build_source_asof_observation` constructs a synthetic observation with `obs_id='SOURCE_ASOF_<race_nkey>'` and `feature_cutoff_datetime=source_race.available_at`. Passing this to `compute_speed_figure_for_history(raw_history, observations=synth_obs)`:
   - The cutoff filter (`:116-118`, `as_of_datetime < feature_cutoff_datetime`) becomes `as_of_datetime < source_race.available_at` — source-race cutoff only, no target cutoff anywhere.
   - par/variant groupby keys are scoped by `obs_id=SOURCE_ASOF_<race_nkey>`, so each source race's par/variant/speed_figure is a function of **only** that source race's `available_at`. Target cutoff cannot enter the computation.

3. **Batching preserves value-invariance.** `_compute_pit_par` Stages 1/2/3 (`:402/:417/:437`) and `_compute_leave_one_out_variant` Stages 1/2 (`:510/:535`) all include `obs_id` in the groupby key (or use obs_id alone). No group spans multiple obs_ids. Concatenating all source races' synth_obs into one call therefore yields per-source-race results that are bit-identical to calling each source race alone. The plan's claim ("obs_id が source_race 毎に独立なので par/variant groupby が source cutoff 毎に独立", 10-01 L125) is **correct**.

4. **The adversarial tests genuinely catch the broken implementation.** Both reviewers walked through what would happen under a broken implementation (reusing obs_id-expanded target-cutoff-contaminated speed_figure):
   - **10-01 Test 3** (input-column non-dependence): asserts that corrupting the input `raw_history.speed_figure` column by +1000 does not change the output profile. A broken implementation reading the input column would change by +1000 and FAIL; the fixed recompute IGNORES the input column and PASSES. This test directly pokes "input-column reuse."
   - **10-01 Test 2** (value-invariance): asserts that a pre-source opponent race yields bit-identical speed_figure regardless of target cutoff, and that monkeypatching the recompute cutoff to target T2 changes the value (guard-effective reverse proof). Under a broken implementation the value already contains (S,T] contamination and the "excluded under S cutoff" assertion FAILS.

   Together these two tests close the leak vector that recurred through Cycle 1 and Cycle 2.

---

## Codex Review (Cycle 3)

**Summary**

The revised plans pass independent review on the leakage surface. C2-1/C2-2/C2-3/C2-4
are all FULLY RESOLVED at the plan level, with verifiable source grounding. H3/H5/H6
remain resolved with no regression. One residual MEDIUM (raw-history input-contract
contradiction on `available_at`/`speed_figure`) is a non-leakage correctness issue.

### C2-1 — FULLY RESOLVED

Current `compute_speed_figure_for_history(..., observations=...)` is target-cutoff-dependent: it expands by observation at `speed_figure.py:635`, filters with each observation cutoff at `:641`, groups par by `obs_id` at `:401`, groups variant by `obs_id` at `:509`, and computes `speed_figure` from those obs-specific values at `:691`. Plan 10-01 now explicitly recognizes this and requires raw-history full-pipeline recompute with `obs_id='SOURCE_ASOF_<race_nkey>'` and `feature_cutoff_datetime=source_race.available_at` (10-01-PLAN.md:122-131). Because par/variant group keys include `obs_id`, batching all source races into one call remains isolated by `SOURCE_ASOF_<race_nkey>`.

### C2-2 — FULLY RESOLVED

Plan 10-02 correctly treats the 21 `rolling_field_strength_*` features as downstream of Plan 01's source-as-of profile, and requires tests for both polluted-profile propagation and clean-profile propagation (10-02-PLAN.md:27, :99).

### C2-3 — FULLY RESOLVED

Current builder contaminates `history` at Step 5b via `history = compute_speed_figure_for_history(...)` at `builder.py:528`. Plan 10-04 now requires `raw_history = history.copy()` before Step 5b and requires Step 5c to call `compute_field_strength_profile(raw_history, ...)`, not the expanded frame (10-04-PLAN.md:116-117). It also adds a capture test for that input contract at 10-04-PLAN.md:109.

### C2-4 — FULLY RESOLVED

The audit no longer stops at row inclusion. Plan 10-01 requires a value-invariance adversarial test at 10-01-PLAN.md:99, and Plan 10-07 repeats that requirement in the audit layer at 10-07-PLAN.md:100 and :125-128.

Under the broken implementation, the same pre-source opponent race would carry different `speed_figure` values for target obs `T1` vs `T2`, because the `(S,T2]` strong race changes T2's par/variant but not T1's. The new value-invariance assertion would observe that mismatch and fail. Under the fixed implementation, both consumers use the same `SOURCE_ASOF_<source_race>` obs_id and cutoff `S`; the `(S,T2]` race is excluded from par/variant and the pre-source row's value is bit-identical.

### New Concern (Codex)

- **MEDIUM-C3-CODEX-1 (10-01, correctness, = Claude #1)**: raw-history input-contract contradiction. The fixed path says raw history is captured before Step 5b and has no `speed_figure` contamination, with required columns listed as raw race columns at 10-01-PLAN.md:123. But Test 11 still says `speed_figure/available_at` are required at 10-01-PLAN.md:108, and the main action builds `source_races` from `available_at` at 10-01-PLAN.md:145. Current builder only adds `available_at` inside Step 5b's speed-figure path (`builder.py:517-521`; `_fetch_history` → `_construct_derived_columns` derives only `race_nkey`/`as_of_datetime`/etc., not `available_at`). Plan change needed: explicitly derive `available_at = pd.to_datetime(race_date)` inside `compute_field_strength_profile` or before saving `raw_history`, and remove `speed_figure` from raw-history required columns/tests.

### Overall Risk Assessment (Codex)

**LOW on the leakage surface.** The central leakage vector (C2-1 root cause) is genuinely closed. The residual MEDIUM is a non-leakage correctness issue (KeyError risk) that will surface at implementation time and is easy to fix without compromising the leakage fix.

---

## Claude Review (Cycle 3 — deeper analysis, independent corroboration)

**Summary**

Cycle-2 の根本原因修正は GENUINE（真正）である。source-as-of full-pipeline 再計算は `obs_id` が par/variant の groupby 先頭キーであるという `speed_figure.py` の構造的性質を利用し、相手能力値を target cutoff から完全に独立させる。value-invariance adversarial test（Test 2 + Test 3）は壊れた実装を確実に捕捉する。C2-1/C2-2/C2-3/C2-4 はすべて計画書レベルで FULLY RESOLVED、H3/H5/H6 の回帰もない。残る懸念はすべて非リークの正確性/実現可能性の問題（3件、all MEDIUM）である。

### C2-1 — FULLY RESOLVED（最も深く検証）

**前提の確認（リーク機構は実在する）**: Cycle-2 の指摘通り、`compute_speed_figure_for_history(history, observations=feature_matrix)` は obs_id 展開フレームを返し（`speed_figure.py:635`/`:658`）、各行の par/variant/speed_figure が target obs の `feature_cutoff_datetime` に依存する（`:401-402`/`:509-510`/`:691`）。`tests/features/test_speed_figure_pit.py:197-220` が O_early/O_late で par_sec が 110.0 vs 115.0 と変わることを実証しており、汚染は実在する。

**修正の有効性（target-cutoff 非依存の機械的保証）**: 10-01 PLAN の `_build_source_asof_observation`（L128-131）が `obs_id='SOURCE_ASOF_<race_nkey>'`・`feature_cutoff_datetime=source_race.available_at` の合成 observation を構築する。これを `compute_speed_figure_for_history(raw_history, observations=synth_obs)` に渡すと: cutoff filter は `as_of_datetime < source_race.available_at`（`:116-118`）= source race の cutoff のみ。par/variant の groupby キーが `obs_id=SOURCE_ASOF_<race_nkey>` で区分されるため、各 source race の par/variant/speed_figure は **その source race の available_at のみの関数** となる。target cutoff が計算経路のどこにも入り込まないことは構造的に保証される。

**batch 化が値の不変性を損なわないか**: 損なわない。`_compute_pit_par` Stage1/2/3（`:402`/`:417`/`:437`）も `_compute_leave_one_out_variant` Stage1/2（`:510`/`:535`）も groupby キーに `obs_id` を含む（または obs_id 単独）。複数 obs_id にまたがる group は一つも存在しない。PLAN の "obs_id が source_race 毎に独立なので par/variant groupby が source cutoff 毎に独立"（L125）は **正しい**。

**value-invariance adversarial test がリークを捕まえるか**: 捕まえる。Test 3（入力 `raw_history.speed_figure` 列を +1000 汚染しても出力不変）は入力列の再利用を直接 poke し、壊れた実装なら +1000 で出力が変わり FAIL。Test 2（monkeypatch で再計算 cutoff を T2 に差替 → (S,T2] 強レース混入で値変化）は壊れた実装なら (S,T] 汚染が既に値に混入しており "S cutoff で除外" の assert が FAIL。この2つで壊れた実装は確実に捕捉される。

### C2-2 / C2-3 / C2-4 — all FULLY RESOLVED

- **C2-2**: 10-02 Test 9（L99）が両方向 gate を持ち、C2-1 解決により profile はクリーン。既存 `_pit_cutoff_prefilter`（strict `<`・obs_id group・`rolling.py:375-383`）の下で 21 feature への伝播経路も閉じる。
- **C2-3**: `builder.py:528` は名前の再束縛（非破壊）。10-04 L116 の `raw_history = history.copy()` は Step 5b 前に保存し、`.copy()` により再束縛後も raw_history は汚染されない（copy 意味論は正しい）。Test 9（L109）が Step 5c 入力の obs_id 列不在を機械保証。
- **C2-4**: 10-07 Test 7b（L128）+ T-10-29b（L231）が value-invariance assert を行包含に加えて機械保証。

### Cycle-1 H3/H5/H6 — RESOLVED・回帰なし

H3: `tests/audit/test_audit_speed_figure.py:43-48` の既存 gap を 10-07 Test 4 + T-10-28b が是正。H5: 実キー `feature_availability_version`（`snapshot.py:71`）を 10-05 が実キー検査。H6: `orchestrator.py:234-247, 253-258` の label-joined `feature_df` + kwargs を 10-06 が5-step chain で踏襲（`run_speed_figure_stopgate.py:583-622`）。

### New Concerns (Claude) — 3件・すべて非リーク MEDIUM

#### #1（MEDIUM・正確性）— `available_at` 列が raw_history に存在せず KeyError（= Codex MEDIUM-C3-CODEX-1）

10-01 PLAN は `available_at` を raw_history の列として複数箇所で参照する: L145 `source_races = starters[["race_nkey","available_at"]].drop_duplicates()`、L147 `source_available_at_by_race = source_races.set_index("race_nkey")["available_at"]`、L123 helper 入力説明。しかし raw_history（`builder.py:480` `_fetch_history` → `_construct_derived_columns` L206-323）が持つ派生列は `race_nkey`/`as_of_datetime`/`days_since_prev`/`timediff`/`babacd` のみで、**`available_at` は存在しない**。`available_at` は `compute_speed_figure_for_history` の出力でのみ付与される（`speed_figure.py:698`）= Step 5b 後の汚染フレームの列。実装時に `starters[["race_nkey","available_at"]]` で KeyError。リークではないが、計画書に導出ステップ（`available_at = pd.to_datetime(race_date)`・`speed_figure.py:698` と対称）が明記されていない。**リスク**: 不注意な実装者が「Step 5b 後の汚染 history から available_at を取る」で解消する余地がある（available_at=race_date 自体は target-cutoff 非依存なので即リークではないが、汚染フレームへの依存経路を開く脆弱な修正）。PLAN 改善: raw_history の race_date から明示導出し、導出元を race_date に固定して明記すること。

#### #2（MEDIUM・特徴量意味論）— source-asof は field-level par となり target 経路の horse-level par と scale 不一致

Cycle-1/2 が注目しなかった（リークでないため）修正の副産物としての意味論的非対称。

- **target 経路**: `observations=feature_matrix` で obs_id = `(race_nkey, kettonum)`（`builder.py:502-514`・race×horse 単位）。merge により各馬の履歴のみが obs に紐付くため、par は **その馬自身の pre-cutoff history の median**（horse-level par）。
- **source-asof 経路**: synth_obs の obs_id = `SOURCE_ASOF_<race_nkey>`（race 単位・10-01 L130）。source race S の全 starter が同一 obs_id を共有するため、par groupby `["obs_id",...]`（`speed_figure.py:402`）は **S の全 starter の pre-S history を合わせた median**（field-level par）。

両者は value-invariance を保ったまま異なり得る: obs_id を `SOURCE_ASOF_<S>_<kettonum>`（race×horse 単位）にすれば horse-level par となり target 経路と一致しつつ、依然 target-cutoff 非依存を保つ。PLAN は obs_id を race 単位に選んだ（L131 はこれを value-invariance の機構として説明するが、par 意味論の変更には言及しない）。結果として `field_strength_adjusted_rank = rank(rolling_speed_figure_mean_5 + 0.25 * rolling_field_strength_mean_mean_5)`（10-03 L26）が異なる scale の項を加算する。**リークではない**（どちらも PIT-correct・target-cutoff 非依存）。PLAN 改善: field-level par（race 単位 obs_id）が相手能力として意図的か、horse-level par（race×horse 単位 obs_id）が target 経路との整合に必要かを文書化し、adjusted_rank での scale 兼容性を確認すること。

#### #3（MEDIUM・実現可能性）— source-asof merge の cardinality 爆発が W-3 縮小閾値で検証されない

`_compute_source_asof_opponent_speed_figures` は全 source race の synth_obs を1連結して1回の `compute_speed_figure_for_history` を呼ぶ（10-01 L125）。source_races = history 全 race（L145・全 race に starter がいる）なので synth_obs ≈ 全 history 行（~48万）。merge `out.merge(obs_keys, on="kettonum")` は馬 H について「H の履歴行 × H が出た source race」の積を生成し、source race = H の全 race なので概ね H の出走数² になる。馬平均50走・~1万頭で expanded frame は **2500万行超** に達し得る（cutoff filter が走る **前** に全積が materialize・`speed_figure.py:635`→`:641` の順序）。10-07 の W-3 性能 gate（L176・縮小版 1000 race × 14 opponent = 14000 行 ≤ 5.0 秒）は 14k 行でしか検証せず、本番 48万行規模の merge メモリ/時間を直接検証しない。PLAN は「6.7M ペア規模への外挿で秒〜十数秒」（10-07 L206）と外挿で語るが 14k 実測からは証明されない。**リークではない**（機能正しさと無関係）。PLAN 改善: expanded frame の本番規模の行数/メモリを見積もるか、本番近傍での1回 smoke を実施するか、merge 前に cutoff pre-filter を入れて H² 積の materialize を回避する構造（per-source-race の都度呼に戻す等）を検討すること。W-3 自体（事前登録閾値・後追い緩和禁止）は健全。

---

## Consensus Summary (Cycle 3 — two reviewers, FINAL)

### Agreement

Both reviewers (Codex + Claude) independently and unanimously confirm:
1. **C2-1/C2-2/C2-3/C2-4 are all FULLY RESOLVED** at the plan level.
2. **The Cycle-2 root-cause fix is GENUINE** — the synth_obs approach exploits the
   `obs_id`-scoped groupby structure of `speed_figure.py` to make opponent ability a
   function of `source_race.available_at` only; no target cutoff enters.
3. **The value-invariance adversarial test genuinely catches the broken implementation**
   (10-01 Test 2 + Test 3; 10-07 Test 7b). Walked through both implementations.
4. **H3/H5/H6 (Cycle 1) are not regressed.**
5. **No HIGH remains. CYCLE_SUMMARY: current_high=0.**

### Residual actionable findings (3 MEDIUM, all non-leakage)

The 3 MEDIUMs are all raised by Claude; Codex's MEDIUM is the same as Claude #1.
All three are invisible to `/gsd-execute-phase` until incorporated into PLAN.md:
- **#1 / Codex MEDIUM-C3-CODEX-1** (KeyError on `available_at`): both reviewers agree.
- **#2** (par-scale asymmetry, field-level vs horse-level): Claude only. Non-leakage.
- **#3** (merge cardinality explosion, undetected by W-3): Claude only. Non-leakage.

### Why this is the right place to stop the automated loop

The core value (leakage prevention) is genuinely protected by the Cycle-2 revision
and verified by two independent reviewers tracing the source code. The residual
findings are plan-level correctness/feasibility issues (KeyError, feature semantics,
performance at production scale) — important to fix in PLAN.md, but none of them
reintroduce the target-cutoff leak that recurred through Cycle 1 and Cycle 2.
Further automated cycles would not surface new leakage vectors; the remaining work
is planner judgement on the 3 MEDIUMs.

---

## Verification coverage (Cycle 3)

| Plan | Source-grounded evidence re-cited this cycle | Leakage-relevant finding? |
|------|----------------------------------------------|---------------------------|
| 10-01 | `speed_figure.py:116-118/401-402/509-510/635/641/658/691/698`, `tests/features/test_speed_figure_pit.py:197-220`, `builder.py:480/502-514/517-521/528`, `10-01-PLAN.md:99/100/108/122-131/143/145/147` | YES (C2-1 FULLY RESOLVED; NEW MEDIUM #1/#2/#3 non-leakage) |
| 10-02 | `10-02-PLAN.md:27/99`, `rolling.py:375-383` | YES (C2-2 FULLY RESOLVED) |
| 10-03 | `10-03-PLAN.md:26` | no (par-scale note in #2, non-leakage) |
| 10-04 | `builder.py:528`, `10-04-PLAN.md:109/116/117` | YES (C2-3 FULLY RESOLVED) |
| 10-05 | `snapshot.py:62/71`, `10-05-PLAN.md:26/94/114/129` | no (H5 regression check PASS) |
| 10-06 | `orchestrator.py:234-258`, `run_speed_figure_stopgate.py:583-622`, `10-06-PLAN.md:50/201-210` | no (H6 regression check PASS) |
| 10-07 | `test_audit_speed_figure.py:39-48`, `speed_figure.py:635/641`, `10-07-PLAN.md:19/97/100/125-128/150/176/206` | YES (C2-4 FULLY RESOLVED; H3 PASS; #3 W-3 scope note) |

---

CYCLE_SUMMARY: current_high=0 current_actionable=3

## Current HIGH Concerns

None.

## Current Actionable Non-HIGH Concerns

- **#1 / MEDIUM-C3-CODEX-1 (10-01, correctness, raised by both Codex and Claude)**: `available_at` 列が raw_history（`builder.py:480` `_fetch_history` → `_construct_derived_columns` L206-323 の派生列は `race_nkey`/`as_of_datetime`/`days_since_prev`/`timediff`/`babacd` のみ）に存在せず・10-01 L145/L147 の `starters[["race_nkey","available_at"]]` が KeyError になる。また Test 11（L108）が `speed_figure` を必須列に挙げているが raw_history（Step 5b 前）は speed_figure 未付与。PLAN.md 変更点: `compute_field_strength_profile` 内で `available_at = pd.to_datetime(race_date)`（`speed_figure.py:698` と対称）を明示導出し・Test 11/threat-model の `speed_figure`/`available_at` 必須列表記を削除/修正すること。不注意な実装者が「Step 5b 後の汚染 history から available_at を取る」で解消するのを防ぐため・導出元を `race_date` に固定して明記。非リーク。
- **#2 (10-01, feature semantics, raised by Claude)**: source-asof の obs_id が race 単位（`SOURCE_ASOF_<race_nkey>`・10-01 L130）のため par が field-level（source race S の全 starter の pre-S history median）となり・target 経路の horse-level par（`(race_nkey,kettonum)` 単位・各馬自身の median・`builder.py:502-514`）と scale が不一致する。両者とも PIT-correct・target-cutoff 非依存（非リーク・実コード確認済）だが・`field_strength_adjusted_rank`（10-03 L26）が異なる normalization の項を加算する。PLAN.md 変更点: field-level par（race 単位 obs_id）を相手能力として意図的とするか・obs_id を `SOURCE_ASOF_<S>_<kettonum>`（race×horse 単位・horse-level par・value-invariance 保持）に改めるかを文書化し・adjusted_rank での scale 兼容性を確認すること。
- **#3 (10-01/10-07, feasibility, raised by Claude)**: source-asof の全 source race 一括 merge（10-01 L125）が・馬毎に概ね出走数² の expanded 行を生成し（source_races = 全 race・L145）・本番で2500万行超の materialize になり得る（`speed_figure.py:635`→`:641` で cutoff filter 前に全積が生成）。W-3 性能 gate（10-07 L176・縮小版 14k 行 ≤ 5.0 秒）は本番規模を検証しない。PLAN.md 変更点: 本番規模の expanded 行数/メモリの見積り・1回 smoke・または merge 前 cutoff pre-filter による H² 積回避構造（per-source-race 都度呼に戻す等）を検討すること。非リーク（機能正しさと無関係）・W-3 自体（事前登録閾値・後追い緩和禁止）は健全。
