---
phase: 09-speed-figure-foundation
cycle: 3
reviewers: [codex]
reviewed_at: 2026-06-25T12:32:00Z
plans_reviewed:
  - 09-01-PLAN.md
  - 09-02-PLAN.md
  - 09-03-PLAN.md
  - 09-04-PLAN.md
  - 09-05-PLAN.md
prior_cycle:
  cycle: 2
  high_count: 2
  actionable_count: 2
  revision_commit: 050c827
---

# Cross-AI Plan Review — Phase 9 (Speed Figure Foundation) — CYCLE 3 (final convergence)

Reviewer: **Codex CLI**（`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`・codex-cli 0.142.1 default model）。起動プロンプト 1957 行・208KB・157,743 tokens 消費。
Method: コミット 050c827（Cycle 2 replan）後の PLAN.md を実コード契約（`src/model/orchestrator.py`, `src/model/data.py`, `src/features/builder.py`, `src/features/rolling.py`）と照合した source-grounded review。本 Cycle 3 の主眼は Cycle 2 で PARTIALLY RESOLVED だった 6 サブアイテム（H1-a/b/c・H4・M1・M2）が真正に解決されたかの最終判定と・改訂で新規導入された懸念の走査。

Cycle 3 全体所感: Cycle 2 の 4 PARTIALLY RESOLVED（H1・H4・M1・M2）の内訳 6 サブアイテムのうち **5 は FULLY RESOLVED**（H1-a・H1-b・H1-c・H4・M1・M2）。各修正は実コード契約の正確な file:line 引用と verify command を持ち・構造的にギャップを閉じている。ただし改訂自体が **P05 stop gate の `train_and_predict` 呼出に新規 HIGH を導入した**: P03 Task 3(k) で `train_and_predict` のシグネチャに追加された `snapshot_id` 引数（FEATURE_COLUMNS 選択用・feature_snapshot_id とは別）を P05 L138 の呼出例が明示的に渡していない。結果: speed_figure snapshot をロードしても orchestrator 内部の make_X_y が v1.0 FEATURE_COLUMNS を使い・stop gate が「v1.0 vs v1.0」の比較を静かに実施しうる。

---

## Codex Review (Cycle 3)

### 09-01-PLAN — H4 FULLY RESOLVED（per-observation PIT・集約キーに obs_id 明示化）

**Summary**
H4（per-observation PIT）は PLAN レベルで完全解決。par/variant の集約キーに obs_id が必須化され・2-observation adversarial テストが cross-observation leak の構造的不能を証明する。

**Strengths**
- par 算出の groupby キーが `obs_id + jyocd + trackcd + kyori` に明示（09-01-PLAN L22・L106）・variant が `obs_id + source_race_date + jyocd + surface` に明示（L22・L107）。これは既存の PIT-safe idiom である rolling.py L204-215・L236-264 と対称。
- 2-observation adversarial テスト `test_cross_observation_pit_no_leak`（L182-185）が・cutoff の異なる2 observation で later obs 専用の介入行が earlier obs の par/variant に漏れないことを実証し・さらに guard monkeypatch + obs_id groupby 外しで逆に混入が生じることを機械証明する（false-pass 回避）。これは H4 invariant が guard でなく集約キー仕様由来であることを実証する。

**Concerns**
- なし。par/variant の集約キー仕様が obs_id を含み・adversarial テストが構造的証明を持つ。

**Suggestions**
- なし。

**Risk Assessment:** LOW（cross-observation leak メカニズムは構造的に対処され・adversarial テストが走査を証明する）。

**Cycle 2 Resolution Status**
- **H4: FULLY RESOLVED** — par/variant 集約キーに obs_id を必須化（L22・L106・L107）+ 2-observation adversarial テスト（L182-185）+ 既存 rolling.py PIT idiom と対称。

---

### 09-02-PLAN — M1 FULLY RESOLVED（prose「7系統」残滓の除去）

**Summary**
M1（7系統 prose 残滓）は完全解決。文書・docstring・test が正確に 8 系統を列挙し・lint verify が古い表記を reject する。

**Strengths**
- 全 prose（L27・L41・L77・L137）が正確に 8 系統を明記。実コード `src/features/rolling.py:71-80` が 8 系統（kakuteijyuni/harontimel3/jyuni3c_jyuni4c/kyori/jyocd/days_since_prev/timediff/babacd）であることと一致。
- lint verify（L287）が `grep -n '既存7系統\|7系統が維持\|既存7' | grep -v 'M1 対応\|7系統でない' | wc -l` == 0 で古い表記の残滓を構造的に reject する。

**Concerns**
- なし。

**Suggestions**
- なし。

**Risk Assessment:** LOW。

**Cycle 2 Resolution Status**
- **M1: FULLY RESOLVED** — 全 prose が正確に 8 系統を列挙（L27・L41・L77・L137）+ lint verify（L287）が残滓を reject。

---

### 09-03-PLAN — H1-a/H1-b/H1-c FULLY RESOLVED（P03 自スコープ内）

**Summary**
H1-a（acceptance escape 削除）・H1-b（orchestrator snapshot_id 伝播）・H1-c（obs_id 早期構築）は P03 自スコープ内で完全解決。各修正は実コード契約の file:line を持ち・verify command が現 arity-0 関数を構造的に reject する。

**Strengths**
- **H1-a**: acceptance（L193）が `or list(sig.parameters)==[]` 逃げ道を削除し `'snapshot_id' in params` のみに厳格化。automated verify（L237）も `assert 'snapshot_id' in sig.parameters` のみで escape を許さない。現 arity-0 の `src/model/data.py:211-229` と一致し・古い関数が GREEN に通るのを構造的に拒否。
- **H1-b**: P03 Task 3(k)（L226-231）が `train_and_predict` シグネチャに `snapshot_id` 引数を追加し・内部3箇所の `make_X_y(train_df/calib_df/test_df)`（現 `src/model/orchestrator.py:373-375` bare call）を `make_X_y(..., snapshot_id=snapshot_id)` に書換。verify（L197・L237）が `grep -nE 'make_X_y\(' | grep -v 'snapshot_id=' | grep -v '^\s*#' | wc -l` == 0 で予測経路の bare call 残存を禁止し・`test_make_X_y_uses_snapshot_feature_columns`（L199）が新 snapshot の rolling_speed_figure_* が実際消費されることを機能証明する。H1-b の P03 内閉塞は完璧。
- **H1-c**: P03 Task 1(b)（L93・L102・L116）が Step 5b の直前に既存 idiom（race_nkey+kettonum or index+kettonum・現 Step 6 `src/features/builder.py:503-517` と同一）で `feature_matrix["obs_id"]` を早期構築。P01 API 契約（observations が obs_id を持つ）を充足し・Step 6 は再利用（"obs_id" in columns で skip）・Step 6b（`src/features/builder.py:560-564`）の drop は不変。

**Concerns**
- P03 自スコープ内の concern はなし。下游 P05 caller のギャップは 09-05 に掲載（後述・新規 HIGH）。

**Suggestions**
- P05 stop-gate caller を P03 の新 `snapshot_id` API と整合させること（09-05 HIGH で対処）。

**Risk Assessment:** MEDIUM（P05 がこの新 API を正しく消費すれば LOW に下落）。

**Cycle 2 Resolution Status**
- **H1-a: FULLY RESOLVED** — acceptance escape 削除（L193）+ inspect-only verify（L237）が arity-0 を構造的に拒否。現 arity-0 は `src/model/data.py:211`。
- **H1-b: FULLY RESOLVED for orchestrator internals** — `train_and_predict` シグネチャに snapshot_id 追加 + 内部3箇所の bare `make_X_y` を snapshot_id 伝播に書換（L226-230）+ grep verify（L197・L237）+ test_make_X_y_uses_snapshot_feature_columns（L199）。現 bare call は `src/model/orchestrator.py:373-375`。※下游 P05 caller の新規ギャップは 09-05 HIGH として別計上。
- **H1-c: FULLY RESOLVED** — Step 5b 前の obs_id 早期構築（L30・L93・L102・L116）が P01 API 契約を充足。現 obs_id 構築は Step 6 `src/features/builder.py:503-517`・drop は L560-564。

---

### 09-04-PLAN — M2 FULLY RESOLVED（verify 強化 + fallback mask 廃止）

**Summary**
M2（dict 戻り値と fallback mask）は完全解決。speed_figure snapshot 未生成時は v1.0 へ fallback せず AssertionError で FAIL し・`result["feature_matrix"]` の使用を AST/grep で検証する。

**Strengths**
- fallback mask 廃止（L103）: speed_figure snapshot が未生成の場合は `pytest.skip` でも v1.0 fallback でもなく・明示的に AssertionError で FAIL する（Phase 9 feature 欠落を mask しない・P03 で snapshot 生成が前提・docstring 明記）。
- dict 戻り値契約の遵守（L159）: `build_feature_matrix` が DataFrame でなく dict を返す現契約（`src/features/builder.py:590-596`・`result["feature_matrix"]`）に対応し・`result = build_feature_matrix(...); feature_matrix = result["feature_matrix"]` で取り出す。verify（L175-188）が AST で `ast.Subscript` + `node.slice.value == 'feature_matrix'` を検出し・subscript 使用を強制する。

**Concerns**
- なし。

**Suggestions**
- なし。

**Risk Assessment:** LOW。

**Cycle 2 Resolution Status**
- **M2: FULLY RESOLVED** — fallback mask を AssertionError に変更（L103）+ `result["feature_matrix"]` subscript 使用を AST verify で強制（L175-188）。現 dict 戻り値契約は `src/features/builder.py:590-596`。

---

### 09-05-PLAN — 新規 HIGH: P05 stop gate が train_and_predict に snapshot_id を渡さない

**Summary**
既存の H2/H6/H7/H8/M4 保護は堅牢だが・P03 Task 3(k) で `train_and_predict` のシグネチャに追加された新 `snapshot_id` 引数を P05 L138 の呼出例が明示的に渡していない。これにより stop gate が speed_figure snapshot をロードしても orchestrator 内部の make_X_y が v1.0 FEATURE_COLUMNS を使い・「v1.0 vs v1.0」の比較を静かに実施しうる。

**Strengths**
- 既存の H2/H7/H8 保護は強固: orchestrator 経由を AST で強制（L26・L111-119）・生 trainer（train_lightgbm/train_catboost/align_predictions/_prepare_catboost_pool）の直接呼出を禁止。
- H6: `fuku_odds_lower` 使用を grep/AST で検証（L28・L113-114）・誤列名 `fukuodds` を禁止。
- M4: `_sanitize_for_json` で NaN/Inf を処理し `allow_nan=False` で安全な JSON 出力（L121・L218）。

**Concerns**
- **HIGH（新規・P05 caller gap）**: P05 が `train_and_predict(...)` を呼ぶ際（L138）・`feature_snapshot_id=<snapshot_id>` と `category_map=load_frozen_maps(snapshot_id=<snapshot_id>)` は渡すが・P03 Task 3(k)（09-03-PLAN L227-228）で新設された `snapshot_id` 引数（FEATURE_COLUMNS 選択用・feature_snapshot_id とは別・デフォルト None は v1.0）を明示的に渡していない。現状では P03 の verify（09-03 L197・L237）で orchestrator 内部の bare `make_X_y` は排除されるが・P05 caller が `snapshot_id=None` を渡す（省略時デフォルト）と orchestrator 内部で `make_X_y(test_df, snapshot_id=None)` となり・speed_figure snapshot をロードしても v1.0 FEATURE_COLUMNS が選択される（H1-b の「機能証明」test_make_X_y_uses_snapshot_feature_columns は P03 スコープ内で通るが・P05 で実際に snapshot_id を渡さないと end-to-end で同じ静かな失敗が残る）。
  - 根拠: P03 09-03-PLAN L227-228（`snapshot_id` は `feature_snapshot_id` とは別・FEATURE_COLUMNS 選択用・デフォルト None は v1.0）+ L222（None は v1.0 デフォルト・後方互換）+ 09-05-PLAN L138（呼出例が `snapshot_id=` を欠く）。現実コードでも `feature_snapshot_id` は `src/model/orchestrator.py:238` に既存だが FEATURE_COLUMNS 選択には無関係・make_X_y は現在 bare（`src/model/orchestrator.py:373-375`）。

**Suggestions**
- P05 を更新し・両 snapshot（baseline と speed_figure）の `train_and_predict` 呼出に `snapshot_id=<対応する snapshot_id>` を明示的に渡す。
- AST テストを追加し・`scripts/run_speed_figure_stopgate.py` の全 `train_and_predict` 呼出が `snapshot_id=` keyword を持つことを検証。

**Risk Assessment:** HIGH（未修正のままでは stop gate が「v1.0 vs v1.0」の比較を静かに実施しうる・H1-b の cycle 2 指摘と同じ静かな失敗メカニズムが P05 呼出側で再生）。

**Cycle 2 Resolution Status**
- **(新規) P05 snapshot_id 伝播ギャップ**: PARTIALLY RESOLVED → 要対応。P03 で `train_and_predict` に `snapshot_id` 引数が追加されたが・P05 呼出例がそれを渡していない。

---

## Cycle 2 → Cycle 3 Resolution Table

| Sub-item | Cycle 2 Status | Cycle 3 Status | Evidence（PLAN line + real code line） |
|----------|----------------:|----------------:|----------------------------------------|
| H1-a acceptance escape | PARTIALLY | **FULLY RESOLVED** | 09-03 L193・L237 が `snapshot_id` を必須化（escape 削除）・現 arity-0 は `src/model/data.py:211` |
| H1-b orchestrator snapshot 伝播 | PARTIALLY | **FULLY RESOLVED for orchestrator internals**・P05 caller gap は新規 HIGH として別計上 | 09-03 L197・L226-230・L237 がシグネチャ + 内部伝播を要求・現 bare call は `src/model/orchestrator.py:373-375` |
| H1-c obs_id 構築タイミング | PARTIALLY | **FULLY RESOLVED** | 09-03 L30・L93・L102・L116 が早期 obs_id 構築を追加・現 Step 6 構築は `src/features/builder.py:503-517`・drop は L560-564 |
| H4 per-observation PIT | PARTIALLY | **FULLY RESOLVED** | 09-01 L22・L106-107・L182-185 が obs_id 必須 + adversarial・rolling 先例は `src/features/rolling.py:204-215`・L236-264 |
| M1 7系統 prose 残滓 | PARTIALLY | **FULLY RESOLVED** | 09-02 L27・L41・L77・L137・L287・実コードは `src/features/rolling.py:71-80` で 8 系統 |
| M2 verify 弱体 + fallback mask | PARTIALLY | **FULLY RESOLVED** | 09-04 L103（AssertionError）・L159・L175-188（AST subscript verify）・現 dict 戻り値は `src/features/builder.py:590-596` |

---

## Consensus Summary (Cycle 3)

### 達成（Cycle 2 → Cycle 3 で真正解決）
- **H1-a・H1-b・H1-c・H4・M1・M2 は FULLY RESOLVED**: 6 サブアイテム全てが concrete task + acceptance_criteria + verify command を持ち・実コード契約の file:line と合致。Cycle 2 の PARTIALLY RESOLVED 4 項目は・改訂（050c827）で構造的に閉じた。
  - H1-a: acceptance から `or list(sig.parameters)==[]` 逃げ道を削除（09-03 L193・L237）。
  - H1-b: P03 Task 3(k) で `train_and_predict` に `snapshot_id` 引数を追加し内部3箇所の bare `make_X_y` を伝播に書換 + grep/AST verify + test_make_X_y_uses_snapshot_feature_columns（09-03 L197・L226-230・L237・L199）。
  - H1-c: Step 5b 前の obs_id 早期構築を既存 idiom で追加（09-03 L30・L93・L102・L116）。
  - H4: par/variant groupby キーに obs_id を必須化 + 2-observation adversarial テスト（09-01 L22・L106-107・L182-185）。
  - M1: prose 全体を 8 系統に訂正 + lint verify（09-02 L27・L41・L77・L137・L287）。
  - M2: fallback を AssertionError に変更 + `result["feature_matrix"]` subscript 使用を AST verify で強制（09-04 L103・L159・L175-188）。

### 残存（最優先・未解決）

1. **(新規 HIGH) P05 stop gate の `train_and_predict` 呼出が `snapshot_id=` を欠く**:
   - 09-05-PLAN L138 の呼出例が `feature_snapshot_id=<snapshot_id>` と `category_map=load_frozen_maps(snapshot_id=<snapshot_id>)` は渡すが・P03 で新設された `snapshot_id` 引数（FEATURE_COLUMNS 選択用・09-03 L227-228）を明示的に渡していない。
   - 結果: speed_figure snapshot をロード（09-05 L137）しても orchestrator 内部で `make_X_y(test_df, snapshot_id=None)` となり v1.0 FEATURE_COLUMNS が選択され・stop gate が「v1.0 vs v1.0」を比較しうる（H1-b と同じ静かな失敗メカニズムが P05 呼出側で再生）。
   - **要対応**: P05 L138 の両 snapshot 呼出に `snapshot_id=<対応する snapshot_id>` を明示的に追加 + `scripts/run_speed_figure_stopgate.py` の全 `train_and_predict` 呼出が `snapshot_id=` keyword を持つことを検証する AST テストを P05 Task2 に追加。

### Divergent Views / Open Questions
- 本 review は単 reviewer（Codex）・Cycle 1/2 と同一。別視点（Gemini 等）を求める場合は `--gemini` 追加で再実行可能。
- H1-b は Cycle 2 で「P03 Task 3 を拡張すれば解決する」と予見されていたが・Cycle 3 で P03 内は完璧に閉じた一方・P05 caller が新 API を正しく消費していないという下游ギャップが浮上した。これは plan の階層的連鎖で・P05 L138 の呼出例を更新すれば閉じる（P05 の local 修正）。

---

## CYCLE_SUMMARY

- **current_high**: 1（P05 stop gate の `snapshot_id` 伝播ギャップ・新規）
  - **(新規) P05 snapshot_id 伝播ギャップ**: 09-05-PLAN L138 の `train_and_predict` 呼出例が `snapshot_id=` を欠く。P03 Task 3(k) で追加された `snapshot_id` 引数（FEATURE_COLUMNS 選択用・09-03 L227-228）を渡さないと speed_figure snapshot をロードしても orchestrator 内部で v1.0 FEATURE_COLUMNS が選択され・stop gate が「v1.0 vs v1.0」を比較しうる（H1-b と同じ静かな失敗メカニズム）。要対応: P05 L138 の両 snapshot 呼出に `snapshot_id=<対応する snapshot_id>` を追加 + AST テストで `snapshot_id=` keyword を検証。
- **current_actionable**: 0

（注: H1-a・H1-b・H1-c・H4・M1・M2 は FULLY RESOLVED につき count から除外。H1-b は P03 内部は FULLY RESOLVED・P05 caller の新規ギャップを新 HIGH として別計上。）

---

## Verification Coverage（Cycle 3 source-grounding 監査）

本 review が根拠として引用した実ソース（file:line・Codex 実読）:
- `src/model/orchestrator.py:234`（train_and_predict シグネチャ・現状 feature_snapshot_id のみで snapshot_id 未追加）
- `src/model/orchestrator.py:238`（feature_snapshot_id 引数・provenance/model_version 用・FEATURE_COLUMNS 選択とは無関係）
- `src/model/orchestrator.py:373-375`（bare `make_X_y(train_df/calib_df/test_df)`・H1-b が書換対象）
- `src/model/data.py:211-229`（load_feature_matrix 現 arity-0・H1-a が parameter化）
- `src/model/data.py:405`（make_X_y 現 arity-1・H1-b が snapshot_id 追加）
- `src/features/builder.py:503-517`（obs_id 現構築箇所・Step 6 内・H1-c が Step 5b 前に早期構築）
- `src/features/builder.py:560-564`（obs_id drop・Step 6b・契約不変）
- `src/features/builder.py:590-596`（build_feature_matrix の dict 戻り値・M2 対応）
- `src/features/rolling.py:71-80`（_ROLLING_SYSTEMS 8 系統・M1 訂正の根拠）
- `src/features/rolling.py:204-215`（obs_id expand idiom・H4 参照）
- `src/features/rolling.py:236-264`（per-observation PIT groupby idiom・H4 参照）

PLAN.md line 引用（改訂後 050c827）:
- `09-01-PLAN.md:22, 106, 107, 182-185`（H4 集約キー obs_id 必須 + 2-observation adversarial）
- `09-02-PLAN.md:27, 41, 77, 137, 287`（M1 8 系統訂正 + lint verify）
- `09-03-PLAN.md:30, 93, 102, 116, 193, 197, 199, 222, 226-230, 237`（H1-a/b/c task + acceptance + verify）
- `09-04-PLAN.md:103, 159, 175-188`（M2 AssertionError + AST subscript verify）
- `09-05-PLAN.md:26, 28, 111-119, 113-114, 121, 137, 138, 218`（H2/H6/H7/H8/M4 + 新規 HIGH L138 snapshot_id 欠落）
