---
phase: 09-speed-figure-foundation
cycle: 2
reviewers: [codex]
reviewed_at: 2026-06-25T13:42:00Z
plans_reviewed:
  - 09-01-PLAN.md
  - 09-02-PLAN.md
  - 09-03-PLAN.md
  - 09-04-PLAN.md
  - 09-05-PLAN.md
prior_cycle:
  cycle: 1
  high_count: 8
  actionable_count: 4
  revision_commit: 9bddc31
---

# Cross-AI Plan Review — Phase 9 (Speed Figure Foundation) — CYCLE 2

Reviewer: **Codex CLI**（`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`・codex-cli 0.142.1 default model）。
Method: ソースコード（`src/features/rolling.py`, `availability.py`, `snapshot.py`, `builder.py`, `src/model/data.py`, `orchestrator.py`, `trainer.py`, `evaluator.py`, `segment_eval.py`, `src/ev/odds_snapshot.py`, `src/ev/ev_rank.py`）を実読し・改訂後 PLAN.md の claim を実コード契約と照合した source-grounded review。本 Cycle 2 の主眼は Cycle 1 の 8 HIGH + 4 actionable が「実行可能な PLAN 内容（task + acceptance_criteria + verify command）」として真正に解決されたかの検証。

Cycle 2 全体所感: Cycle 1 の 8 HIGH のうち 6 は FULLY RESOLVED（H2/H3a/H3b/H5/H6/H7/H8・acceptance_criteria と verify command が実コード契約に合致）。しかし **H1（data.py parameterization）と H4（per-observation PIT）の 2 HIGH は PARTIALLY RESOLVED**・それぞれ実行可能記述に残存ギャップがある。さらに P03/P05 にまたがる新規懸念（orchestrator.train_and_predict が make_X_y に snapshot_id を伝播しない・obs_id 構築順序の builder↔speed_figure API 不整合）が浮上した。M1/M2 は実行基準は正しいが prose/verify に残滓。

---

## Codex Review (Cycle 2)

### 09-01-PLAN — H4 PARTIALLY RESOLVED（per-observation PIT 集約キーに obs_id が明示されず）

**Summary**
H4 は acknowledge され must_haves/task/verify が存在するが・実行可能な集約記述がまだ PIT-safe でない完全性に達していない。`_compute_pit_par` の groupby キーが `jyocd×trackcd×kyori`（PLAN L105）・variant が `(source_race_date, jyocd, surface)`（L106）と記述されており・**obs_id が集約キーに含まれていない**。もし展開済みフレームが異なる cutoff を持つ複数 observation を含む場合・後続 observation で eligible な行が Earlier observation の par/variant median に漏れ込む（cross-observation leak）。

**Strengths**
- 既存 rolling PIT パターンの参照は正確: expand by observation → strict `<` → per-`obs_id` groupby（`src/features/rolling.py:236`, `:252`, `:260`）。
- 5 段階 adversarial test の docstring/verify（PLAN L123, L180）は rolling と対称。

**Concerns**
- **HIGH（H4 未完）**: `_compute_pit_par` の groupby が `jyocd×trackcd×kyori`（PLAN L105）のみだと・展開済みフレーム上で observation 毎に独立した par 算出にならない。par fallback 階層も `obs_id + (jyocd×trackcd×kyori)` であるべき。variant も `obs_id + source_race_date + jyocd + surface` であるべき。現在の PLAN 記述では「展開済みフレーム上で算出」と言葉で書いてあるが・groupby キーの仕様として obs_id が明示されないため・実装者が observation 横断漏れを踏む余地が残る。
- **MEDIUM（leave-one-out 近似の不正確さ）**: variant の「自レースを除く residual median」を `(group_median - (self_residual - group_median)/(n-1))` の一次近似（PLAN L106）で算出するのは mean ベースの公式であり・**真の leave-one-out median とは一致しない**（median は外れ値に頑健だが self の寄与は線形でない）。docstring に「近似」と明記されているが D-02 が要求する leave-one-race-out の厳密性に対して精度保証が薄い。

**Suggestions**
- par fallback group を `obs_id + keys`・variant group を `obs_id + source_race_date + jyocd + surface` と PLAN に明記し・acceptance_criteria に「2 つの observation で intervening race が片方にだけ legal な adversarial ケースで par/variant が変化する」テストを追加。
- leave-one-out は真の median(`group.transform(lambda s: np.median(np.delete(s.values, s.index.get_loc(self_idx))))`) または近似の誤差上限を docstring/test で明示。

**Risk Assessment:** **HIGH**（PIT 集約キーに obs_id が明示されない限り cross-observation leak の可能性が残る）。

**Cycle 1 Resolution Status**
- **H4: PARTIALLY RESOLVED** — must_haves（L22）+ task（L104）+ verify（L123, L180）は存在するが・実行可能な集約キー仕様に obs_id が含まれず・実装者が cross-observation leak を踏む余地が残る。

---

### 09-02-PLAN — H3a/H3b FULLY RESOLVED（残滓: prose の「7系統」表記）

**Summary**
H3a/H3b は具象 task + acceptance_criteria + verify command で真正に解決。M1 は実行基準は正しい（8 系統）が objective/examples の prose に「既存7系統」の古い表記が残る。

**Strengths**
- **H3b** は現リスクに正確に合致: `_RESERVED_NON_FEATURE_COLUMNS` が全 `rolling_{sys}_count_5` を自動展開（`src/features/availability.py:158`, `:179`）し・data.py がこれを FEATURE_COLUMNS から減算（`src/model/data.py:122`, `:171`）。PLAN Task 2 は L179 set comprehension を `if sys != "speed_figure"` で条件付きにし・verify（L207）で `rolling_speed_figure_count_5 not in _RESERVED_NON_FEATURE_COLUMNS` を assert。
- **H3a** は現リスクに正確に合致: `_is_categorical_rolling_col` は現状 `_5` suffix のみ受理（`src/features/snapshot.py:115`, `:126`）。PLAN Task 3 は `_1/_3/_5` の可変 window に拡張し・verify（L232）で `rolling_speed_figure_last_1` が numeric(False) となることを assert。

**Concerns**
- **LOW（M1 prose 残滓）**: objective（L41）・Task1 action（L77, L88, L98）に「既存7系統」表記が残る。acceptance_criteria（L137）・done（L144）は正確に 8 系統を列挙しているため実行には影響しないが・doc/test の誤カウントを残す。

**Suggestions**
- plan-lint acceptance check 追加: `rg -n '7系統' .planning/phases/09-speed-figure-foundation/09-02-PLAN.md` が無候補返却。

**Risk Assessment:** **MEDIUM**（H3a/H3b は解決・M1 prose は実行無影響だが文書正確性に残滓）。

**Cycle 1 Resolution Status**
- **H3a: FULLY RESOLVED** — Task 3 の acceptance（L230）+ verify（L232, L248）が `_1/_3/_5` suffix を実コード契約と合致。
- **H3b: FULLY RESOLVED** — Task 2 の action（L175, L177）+ verify（L207, L285）が reserved 除外を D-09 契約と合致。
- **M1: PARTIALLY RESOLVED** — 実行基準（L137, L144）は 8 系統で正確だが・prose（L41, L77, L88, L98）に「7系統」残滓。

---

### 09-03-PLAN — H1 PARTIALLY RESOLVED（acceptance 弱体 + orchestrator 伝播未完 + obs_id 構築順序矛盾）★最重要

**Summary**
H1 への data.py parameterization task は存在するが・(a) acceptance が古い arity-0 関数を通過させてしまう・(b) orchestrator.train_and_predict が make_X_y に snapshot_id を伝播しない・(c) P03 Step 5b の observations=feature_matrix と P01 の observations[["obs_id",...]] 期待が builder の現 obs_id 構築タイミングと矛盾する。3 点とも HIGH。

**Strengths**
- 現硬結合の正確な特定: `SNAPSHOT_PATH`/manifest は固定（`src/model/data.py:77`）・`_derive_feature_columns()` が固定 path を読む（`:149`, `:162`）・`load_feature_matrix()` は arity 0（`:211`）。PLAN はこれらを正しく parameter化する task を持つ。

**Concerns**
- **HIGH（H1-a: acceptance の弱体）**: `assert 'snapshot_id' in sig.parameters or list(sig.parameters)==[]`（PLAN L185）は `or` の後節で古い arity-0 関数をそのまま通す。この acceptance では「何も変更しなくても GREEN」になり・H1 解決の証明にならない。
- **HIGH（H1-b: orchestrator 伝播ギャップ・新規懸念）**: `orchestrator.train_and_predict` は現状 `make_X_y(train_df)` / `make_X_y(calib_df)` / `make_X_y(test_df)` を snapshot_id なしで呼ぶ（`src/model/orchestrator.py:372`）。P03 Task 3 は make_X_y/prepare_model_matrix に snapshot_id 引数を追加する（PLAN L205, L207）だけ・orchestrator 内部の make_X_y 呼出を snapshot_id 渡しに変更しない。P05 は `train_and_predict(..., feature_snapshot_id=...)`（PLAN L138）を呼ぶが・現 orchestrator では feature_snapshot_id は provenance/model_version 用であり feature column 選択には伝播しない。結果: speed_figure snapshot で学習しても orchestrator 内部の make_X_y が v1.0 FEATURE_COLUMNS を使う静かな失敗が残る。
- **HIGH（H1-c: obs_id 構築順序矛盾・新規懸念）**: P03 Task 1 は Step 5 rolling の直前に `compute_speed_figure_for_history(history, observations=feature_matrix)`（PLAN L94, L102）を挿入するが・P01 は `observations[["obs_id","kettonum","feature_cutoff_datetime"]]`（09-01 L114）を期待する。現 builder は obs_id を rolling/Step 6 内部（`src/features/builder.py:457`, `:503`）で構築するため・Step 5b 挿入時点では feature_matrix に obs_id が無い可能性がある。P03 Task1 (d)（L108）は「compute_speed_figure_for_history 側が observations=None を許容し内部で obs_id を構成」を許すが・これは P01 の API 契約（observations は obs_id を持つ前提・L114）と矛盾。

**Suggestions**
- H1-a: acceptance を `'snapshot_id' in sig.parameters` のみ（`or` 後節削除）に厳格化。
- H1-b: P03 Task 3 に orchestrator.train_and_predict の内部 make_X_y 呼出へ snapshot_id を伝播する変更を含めるか・P05 が orchestrator を経由せず直接 make_X_y(snapshot_id=...) + calibrated predict の helper を呼ぶよう分離。前者が望ましい（D-13 公平性の単一経路維持）。
- H1-c: P03 Task 1 で Step 5b の前に obs_id を早期構築する既存 idiom（`builder.py:505-517` と同一ロジック）を明示的に実行するか・P01 の compute_speed_figure_for_history が observations なしでも内部で obs_id を構築する idiom（rolling `src/features/rolling.py:204-215` と対称）を持つよう PLAN を整合。

**Risk Assessment:** **HIGH**（acceptance 弱体・orchestrator 伝播ギャップ・obs_id 矛盾の 3 点が揃うと「Parquet は正しく生成されたが学習は v1.0 のまま」の静かな失敗が再発しうる）。

**Cycle 1 Resolution Status**
- **H1: PARTIALLY RESOLVED** — 具象 Task 3（L172）+ verify は存在するが・acceptance が古いコードを通過させ・orchestrator 伝播が閉じず・obs_id API 矛盾が残る。

---

### 09-04-PLAN — H5 FULLY RESOLVED / M3 FULLY RESOLVED / M2 PARTIALLY RESOLVED

**Summary**
H5（word-boundary SQL proxy 検出）と M3（div_id 固定）は FULLY RESOLVED。M2（dict 戻り値）は action/done に組み込まれたが verify が syntax parse のみで実機検証がない。

**Strengths**
- **H5** は `ast.Constant` の str リテラルを word-boundary 部分一致で走査（PLAN L86, L97）し・builder の実際の SQL 文字列サーフェス（`src/features/builder.py:101`, `:116`）に対する proxy 埋込み検出を真正に実装する。false-pass 回避テスト（test_false_pass_detection_power・L109）で SQL proxy 注入を検出力証明。
- **M3** は既存の byte-reproducible Plotly idiom と正確に合致: `include_plotlyjs="directory"` + 固定 `div_id`（`src/model/segment_eval.py:444`, `:447`）。

**Concerns**
- **MEDIUM（新規・M2 検証不足）**: `test_feature_columns_contains_speed_figure_no_proxy`（L103）は speed_figure snapshot が存在しない場合 v1.0 に fallback し・Phase 9 feature 欠落を mask しうる（P03 で snapshot 生成前はテスト不能）。また M2（dict 戻り値）は action/done（L158, L179）に書かれたが automated verify（L173）は `ast.parse` のみで `result["feature_matrix"]` 使用を検証しない。

**Suggestions**
- P04 で speed snapshot が存在しない場合は fail にする（fallback で mask しない）。
- `result["feature_matrix"]` の使用を AST/grep check で検証。

**Risk Assessment:** **MEDIUM**（H5/M3 は堅牢・M2 の verify 弱体と snapshot fallback が残課題）。

**Cycle 1 Resolution Status**
- **H5: FULLY RESOLVED** — word-boundary 部分一致検出 + false-pass 回避テストで SQL proxy も検出。
- **M2: PARTIALLY RESOLVED** — action/done に組み込み済みだが verify が syntax のみ。
- **M3: FULLY RESOLVED** — `div_id="speed-figure-domain"` 固定 + `include_plotlyjs="directory"`。

---

### 09-05-PLAN — H2/H6/H7/H8/M4 FULLY RESOLVED（ただし H1-b orchestrator 伝播に依存）

**Summary**
H2/H6/H7/H8/M4 は stopgate plan で実行可能な task + acceptance_criteria + verify command として真正に解決。ただし P03 の H1-b orchestrator 伝播ギャップが解決されない限り stopgate が v1.0 FEATURE_COLUMNS で学習する静かな失敗が残る。

**Strengths**
- **H2/H7/H8** は `train_and_predict` 経由を正確にルーティング（PLAN L111, L138）。ソース確認: orchestrator は later-disjoint calibration（`src/model/orchestrator.py:478`）・LightGBM categorical 準備（`:490`, `:516`）・CatBoost test 予測整列（`:525`, `:534`）を実施。生 trainer 直接呼出は AST テスト（test_orchestrator_path_not_raw_trainer・L220）で禁止。
- **H6** は実 odds 列を使用: `fuku_odds_lower`/`fuku_odds_upper`（`src/ev/odds_snapshot.py:210`, `:323`）・EV コードと合致（`src/ev/ev_rank.py:87`, `:109`）。
- **M4** は strict JSON + sanitizer（PLAN L121, L162）で single-class AUC NaN（`src/model/evaluator.py:210`）と segment_eval sanitizer pattern（`:94`）に対処。

**Concerns**
- **HIGH（H1-b 伝播ギャップへの依存）**: stopgate は P03 の H1 parameterization を前提とするが・orchestrator が内部 make_X_y に snapshot_id を渡さない限り（`src/model/orchestrator.py:372`）・speed_figure snapshot で学習しても v1.0 FEATURE_COLUMNS が使われる。P05 単体ではこのギャップを閉じられない。

**Suggestions**
- stopgate smoke テストで make_X_y を monkeypatch/inspect し speed snapshot path が `rolling_speed_figure_*` を選択することを assert。

**Risk Assessment:** **MEDIUM, rising to HIGH** — H1-b（P03 orchestrator 伝播）が解決されれば LOW に下落。

**Cycle 1 Resolution Status**
- **H2: FULLY RESOLVED** — orchestrator.train_and_predict 経由・生 trainer 直接呼出 AST で禁止。
- **H6: FULLY RESOLVED** — `fuku_odds_lower` 使用・`fukuodds` 禁止を grep/AST で検証。
- **H7/H8: FULLY RESOLVED** — orchestrator 経由で `sorted_test_idx` と `_prepare_lightgbm_train_eval` を再利用。
- **M4: FULLY RESOLVED** — `_sanitize_for_json` + `allow_nan=False` で NaN/Inf 処理。

---

## Consensus Summary (Cycle 2)

### Agreed Strengths（Cycle 1 → Cycle 2 で真正解決した HIGH 群）
- **H2/H3a/H3b/H5/H6/H7/H8/M3/M4 は FULLY RESOLVED**: それぞれ具象 task + acceptance_criteria + verify command を持ち・実コード契約（`src/features/availability.py:179`, `src/features/snapshot.py:126`, `src/model/orchestrator.py:478-538`, `src/ev/odds_snapshot.py:210-215`, `src/model/segment_eval.py:444-447` 等）と合致。
- H1（data.py parameterization）と H4（per-observation PIT）は方向性は正しいが実行可能記述に残存ギャップ。

### Agreed Concerns（最優先・未解決）

1. **H1（data.py parameterization）PARTIALLY RESOLVED・3 つの実行ギャップ**:
   - (a) acceptance の `or` 後節で古い arity-0 関数が通過（09-03 L185）。
   - (b) **新規**: orchestrator.train_and_predict が内部 make_X_y 呼出に snapshot_id を伝播しない（`src/model/orchestrator.py:372`）。P03 Task 3 が make_X_y に引数を追加するだけでは閉じない。
   - (c) **新規**: P03 Step 5b の observations=feature_matrix と P01 の observations[["obs_id",...]] 期待が builder 現 obs_id 構築タイミング（`src/features/builder.py:503`）と矛盾。
   - **要対応**: P03 Task 3 の acceptance 厳格化 + orchestrator.train_and_predict 内部の make_X_y 呼出の snapshot_id 伝播 + P03 Step 5b 前の obs_id 早期構築（または P01 API の observations=None 内部構築許容）。

2. **H4（per-observation PIT）PARTIALLY RESOLVED・集約キーに obs_id が明示されず**:
   - par の groupby が `jyocd×trackcd×kyori`（09-01 L105）のみで obs_id 抜き・variant も `obs_id` 抜き（L106）。展開済みフレーム上で算出すると書いても groupby キー仕様に obs_id がないため cross-observation leak の余地。
   - **要対応**: par fallback group を `obs_id + keys`・variant group を `obs_id + source_race_date + jyocd + surface` と PLAN に明示 + 2-observation adversarial テスト。

### 新規懸念（Cycle 2 で浮上・Cycle 1 にはなかった）
- **H1-b（orchestrator 伝播ギャップ）**: P03 Task 3 が make_X_y を parameterize しても orchestrator.train_and_predict が snapshot_id を make_X_y に渡さないと・stop gate が v1.0 FEATURE_COLUMNS で学習する。P03 Task 3 のスコープ拡張または P05 での orchestrator ラッパー分離が必要。
- **H1-c（obs_id 構築順序矛盾）**: builder Step 5b 挿入位置と P01 API 契約の整合。P03 Task 1 (d)（L108）で言及されているが・「compute_speed_figure_for_history 側が observations=None を許容」は P01 L114 の「observations は obs_id を持つ前提」と整合しない。P01 側で observations=None 時の obs_id 内部構築を明示する idiom（rolling `src/features/rolling.py:204-215` と対称）を持つべき。
- **P04 fallback mask**: speed snapshot 未生成時に v1.0 へ fallback すると Phase 9 feature 欠落が mask される（09-04 L103）。

### Divergent Views / Open Questions
- 本 review は単 reviewer（Codex）・Cycle 1 と同一。別視点（Gemini 等）を求める場合は `--gemini` 追加で再実行可能。
- H1-b（orchestrator 伝播）は Cycle 1 時点では個別 trainer API 問題として捉えられていたが・Cycle 2 で parameterization の「伝播の閉じ具合」として再構造化された。これは plan の階層的な問題で・P03 Task 3 を拡張すれば解決する（P05 単体では不可能）。

---

## Cycle 1 → Cycle 2 Resolution Table

| Finding | Cycle 1 Severity | Cycle 2 Status | 根拠 |
|---------|------------------|----------------|------|
| H1 | HIGH | **PARTIALLY RESOLVED** | P03 Task 3 存在するが acceptance 弱体 + orchestrator 伝播ギャップ(H1-b 新規) + obs_id 矛盾(H1-c 新規) |
| H2 | HIGH | FULLY RESOLVED | orchestrator.train_and_predict 経由 + 生 trainer AST 禁止（09-05 L111, L138, L220） |
| H3a | HIGH | FULLY RESOLVED | snapshot.py `_1/_3/_5` suffix 拡張 + verify（09-02 Task3 L230, L232） |
| H3b | HIGH | FULLY RESOLVED | reserved 条件付き除外 + verify（09-02 Task2 L175, L207） |
| H4 | HIGH | **PARTIALLY RESOLVED** | must_haves/task/verify 存するが par/variant groupby キーに obs_id 未明示（09-01 L105, L106） |
| H5 | HIGH | FULLY RESOLVED | word-boundary 部分一致 + false-pass 回避（09-04 L86, L97, L109） |
| H6 | HIGH | FULLY RESOLVED | fuku_odds_lower 使用 + fukuodds 禁止（09-05 L113, L114, L216） |
| H7/H8 | HIGH | FULLY RESOLVED | orchestrator 経由 sorted_test_idx + _prepare_lightgbm_train_eval（09-05 L111, L119） |
| M1 | LOW | **PARTIALLY RESOLVED** | 実行基準は 8 系統で正確だが prose（L41/L77/L88/L98）に「7系統」残滓 |
| M2 | MEDIUM | **PARTIALLY RESOLVED** | action/done に組み込み済み・verify が syntax parse のみ（09-04 L173） |
| M3 | MEDIUM | FULLY RESOLVED | div_id 固定 + include_plotlyjs='directory'（09-04 L165） |
| M4 | MEDIUM | FULLY RESOLVED | _sanitize_for_json + allow_nan=False（09-05 L162, L218） |

---

## CYCLE_SUMMARY

- **current_high**: 2（H1・H4 とも PARTIALLY RESOLVED）
  - **H1**: data.py parameterization の実行ギャップ（acceptance 弱体・orchestrator 伝播 H1-b 新規・obs_id 矛盾 H1-c 新規）
  - **H4**: par/variant per-observation PIT の groupby キーに obs_id 未明示・cross-observation leak 余地
- **current_actionable**: 2
  - **M1（LOW）**: 09-02 prose の「7系統」表記を 8 系統に訂正（実行基準は既に正確）
  - **M2（MEDIUM）**: 09-04 Task2 の verify が `ast.parse` のみ・`result["feature_matrix"]` 使用を AST/grep 検証に強化 + speed snapshot 未生成時の v1.0 fallback を fail に変更

（注: H2/H3a/H3b/H5/H6/H7/H8/M3/M4 は FULLY RESOLVED につき count から除外。H1-b/H1-c は H1 の PARTIALLY RESOLVED の内訳として扱い・H1 のみ count。新規懸念 P04 fallback mask は M2 の fallback 指摘と重なるため M2 に集約。）

---

## Verification Coverage（Cycle 2 source-grounding 監査）

本 review が根拠として引用した実ソース（file:line・Codex が実読）:
- `src/features/rolling.py:204-215, 236, 252, 260`（obs_id expand idiom・H4 参照）
- `src/features/availability.py:158, 179`（_RESERVED_NON_FEATURE_COLUMNS 自動展開・H3b）
- `src/features/snapshot.py:115, 126`（_is_categorical_rolling_col `_5` 固定・H3a）
- `src/features/builder.py:101, 116, 457, 503`（SQL 文字列・obs_id 構築タイミング・H1-c）
- `src/model/data.py:77, 122, 149, 162, 171, 211`（SNAPSHOT_PATH 硬結合・FEATURE_COLUMNS 減算・H1）
- `src/model/orchestrator.py:372, 478, 490, 516, 525, 534`（make_X_y snapshot_id 伝播ギャップ・H1-b・calibration・CatBoost sorted_test_idx・H7・LightGBM categorical・H8）
- `src/model/evaluator.py:210`（single-class AUC NaN・M4）
- `src/model/segment_eval.py:94, 444, 447`（sanitizer pattern・M4・div_id idiom・M3）
- `src/ev/odds_snapshot.py:210, 323`（fuku_odds_lower/upper・H6）
- `src/ev/ev_rank.py:87, 109`（EV コード odds 列消費・H6）

PLAN.md line 引用（改訂後）:
- `09-01-PLAN.md:22, 104, 105, 106, 114, 123, 180`（H4 task/verify・par/variant groupby・observations API）
- `09-02-PLAN.md:41, 77, 88, 98, 137, 144, 175, 177, 207, 230, 232, 248`（H3a/H3b task/verify・M1 prose）
- `09-03-PLAN.md:94, 102, 108, 172, 185, 205, 207`（H1 task3・acceptance 弱体・Step 5b・obs_id 矛盾）
- `09-04-PLAN.md:86, 97, 103, 109, 158, 165, 173, 179`（H5 word-boundary・M2 dict・M3 div_id・fallback mask）
- `09-05-PLAN.md:111, 113, 114, 119, 121, 138, 162, 216, 218, 220`（H2/H6/H7/H8/M4 task/verify）
