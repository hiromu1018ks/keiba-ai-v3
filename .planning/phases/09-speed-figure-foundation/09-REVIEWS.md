---
phase: 09-speed-figure-foundation
reviewers: [codex]
reviewed_at: 2026-06-25T11:28:04Z
plans_reviewed:
  - 09-01-PLAN.md
  - 09-02-PLAN.md
  - 09-03-PLAN.md
  - 09-04-PLAN.md
  - 09-05-PLAN.md
---

# Cross-AI Plan Review — Phase 9 (Speed Figure Foundation)

Reviewer: **Codex CLI**（`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`・default model）。
Method: ソースコード（`src/features/rolling.py`, `availability.py`, `builder.py`, `snapshot.py`, `src/model/data.py`, `trainer.py`, `orchestrator.py`, `evaluator.py`, `segment_eval.py`, `predict.py`, `src/ev/odds_snapshot.py`, `tests/audit/test_audit_features.py`）を実読し・各 PLAN の claim を実コード契約と照合した source-grounded review。

 reviewer 全体所感: 方向性は妥当（P01/P03 の builder 挿入点・P04 の audit 方針は既存パターンを正しく踏襲）だが・**P05 stop gate の trainer/orchestrator API 誤解**と **P03/P05 の `data.py` SNAPSHOT_PATH 硬結合の見落とし**が **HIGH リスク**。これらが未修正だと・stop gate の比較が v1.0 と「非比較」になる（D-13 公平性違反）か・新 snapshot の FEATURE_COLUMNS が学習に使われず「正しく動くように見えて v1.0 のまま学習」になる恐れがある。

---

## Codex Review

### 09-01 Plan — speed_figure.py 新規（par/variant/PIT/float）

**Summary**
新 speed_figure モジュールの基盤計画としては良好だが・par/variant の PIT 設計がまだ source-safe でない。最大リスクは・広い cutoff filter を1回適用したあと history 全体で par/variant を「グローバルに」算出してしまうと・既存 rolling の `obs_id` per-observation window 不変量を破る点。

**Strengths**
- 正しい strict cutoff 契約を再利用: `CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"` は `src/features/availability.py:45` で共有不変量・`src/features/rolling.py:49-55` で強制済。
- 提案された adversarial test 形状は既存 false-pass パターンと整合: 現行 audit は `_pit_cutoff_prefilter` を `<` → `<=` に monkeypatch し値変化を証明（`tests/audit/test_audit_features.py:69-87`・同 `:100-119`）。

**Concerns**
- **HIGH:** par/variant は observation 毎に算出する必要がある・グローバルに filter された history frame 上でなく。既存 rolling は `obs_id` を window key にして明示的に cross-observation leak を回避（`src/features/rolling.py:39-42`）した上で・observation 毎に展開・filter（`src/features/rolling.py:236-265`）。もし `_compute_pit_par(history_filtered)` が filter 済み全行を一括集計すると・古い target observation が・より新しい target observation でのみ eligible な行を継承してしまう（同一 horse × 複数 observation での PIT leak）。
- **HIGH:** P01 の unit test は GREEN でも builder 統合時に失敗しうる・現 history SELECT が `time` を含まないため。`_HISTORY_DB_SELECT_COLUMNS` は `kakuteijyuni`/`harontimel3`/`kyori`/`trackcd` 等を持つが `ur.time AS time` は無い（`src/features/builder.py:101-121`）※ P03 で追加予定だが P01 単体では気づかない。
- **MEDIUM:** surface 派生は既存 track semantics に pin すべき。builder は `trackcd 51-59` を obstacle 扱いしつつ babacd には芝側 `hist_sibababacd` を使う（`src/features/builder.py:260-286`）・`surface="obstacle"` の独立 variant bucket が既存 baba semantics と divergence する恐れ。

**Suggestions**
- par/variant API が展開済み frame（`obs_id`, `feature_cutoff_datetime`, source race key 含む）を消費し・展開後に `as_of_datetime < feature_cutoff_datetime` を assert するよう設計（`src/features/rolling.py:237-252` と対称）。
- production path では `observations=None` を禁じ・unit test 専用と明示。builder は常に observations を渡す。
- P03 後に `ur.time AS time` が SELECT されるまで fail する builder-facing test を追加（現 `_fetch_history` 形状 `src/features/builder.py:664-688` 使用）。

**Risk Assessment:** **HIGH**（par/variant が明示的に per-observation PIT-safe になるまで）。

---

### 09-02 Plan — rolling.py / availability / yaml 拡張

**Summary**
rolling/registry 統合の target は概ね正しく・`course_kubun` 削除の根拠もソースで裏付けられる。しかし既存契約2点を見落とす: (1) count 列は現状 reserved/non-feature 扱い・(2) snapshot coercion は `rolling_*_*_5` しか解釈しない。

**Strengths**
- 正しい拡張点: rolling systems と source mappings は中央集約されている（`src/features/rolling.py:71-94`）。
- 既存 PIT 機構は再利用可能: strict filter が latest-K 選択の前に走る（`src/features/rolling.py:248-265`）。
- `course_kubun` 削除はソースで裏付け: YAML は登録する（`src/config/feature_availability.yaml:129-135`）が・builder は observations で SELECT せず（`src/features/builder.py:127-144`）・derived でも生成しない（`src/features/builder.py:195-312`）。

**Concerns**
- **HIGH:** `rolling_speed_figure_count_5` は `_ROLLING_SYSTEMS_FOR_RESERVED` に追加すると model feature にならない。count 列は reserved 扱い（`src/features/availability.py:158-179`）・`META_KEY_COLUMNS` が reserved 列を import し（`src/model/data.py:119-137`）・`_derive_feature_columns` がそれらを減算する（`src/model/data.py:169-172`）。機構: D-09 は count_5 を feature とするが・現 data layer はこれを `FEATURE_COLUMNS` から除外する。**silently**。
- **HIGH:** `rolling_speed_figure_last_1` と `rolling_speed_figure_mean_3` は Parquet 書込時に mixed object 列のまま残る可能性。Rolling は object + `__MISSING__` で初期化（`src/features/rolling.py:217-225`）し・snapshot coercion は `_5` で終わる列のみ分類（`src/features/snapshot.py:115-139`）。
- **LOW:** PLAN は「既存7系統」と書くが・現 rolling は8系統（`src/features/rolling.py:71-80`・最後の timediff/babacd 含む）。精度上の小問題だが・test/doc に誤カウントを刻まないこと。

**Suggestions**
- `rolling_speed_figure_count_5` が model input か audit/reserved か決定。model input なら `_RESERVED_NON_FEATURE_COLUMNS` に speed_figure を含めない・または data.py の除外ロジックを特例化。
- `src/features/snapshot.py::_is_categorical_rolling_col` を更新し・可変 window suffix（`_1`/`_3`/`_5`）を parse してから non-`_5` rolling 名を追加。
- rolling 出力だけでなく・speed 6列の Parquet 書込テストを追加。

**Risk Assessment:** **MEDIUM-HIGH**（parity が GREEN に見えて count_5 が silently除外・Parquet 書込が fail しうる）。

---

### 09-03 Plan — builder.py Step 5b 統合

**Summary**
builder 挿入点は正しいが・v1.0 snapshot/data-layer の硬結合を過小評価している。`src/model/data.py` を変更しない限り・Phase 9 の新カラムは training や stop-gate コードで利用できない。

**Strengths**
- 正しい挿入位置: builder は rolling の直前に history を fetch する（`src/features/builder.py:457-476`）ので・speed figure を `build_rolling_features` の前に足すのは正しい pipeline 点。
- 最終 registry guard は既存: `assert_matrix_columns_registered` が走る（`src/features/builder.py:580-581`）。
- copy-not-rename は builder の ID 周り既存スタイルと整合（`src/features/builder.py:444-455`）。

**Concerns**
- **HIGH:** `FEATURE_COLUMNS` は import 時に hard-code された v1.0 snapshot path から導出され・新 snapshot からではない。`SNAPSHOT_PATH` と `EXPECTED_FEATURE_COUNT` は固定（`src/model/data.py:77-79`）・`_derive_feature_columns` は当該 Parquet を読む（`src/model/data.py:160-163`）・`FEATURE_COLUMNS` は import 時に materialize（`src/model/data.py:176`）。機構: 参照 Parquet path が変わらない限り・新 registry entry は model input に入らない。
- **HIGH:** 既存 CLI が同一 hard-code を強制。`scripts/run_train_predict.py` は `--snapshot-id` が `data.py.SNAPSHOT_PATH` と異なると reject する（`scripts/run_train_predict.py:174-193`）。
- **MEDIUM:** Step 5b の `observations=feature_matrix` は既存の `obs_id` を前提としてはならない。builder は後で推定脚質用に `obs_id` を作る（`src/features/builder.py:502-517`）。rolling はこれを内部処理する（`src/features/rolling.py:204-215`）・speed_figure も同様にすべき。
- **MEDIUM:** 監査列は最終 `feature_matrix` に残ってはならない。builder は rolling 出力のうち `rolling_` で始まる列のみ merge し（`src/features/builder.py:475-493`）・最終未登録列は `src/features/builder.py:580-581` で fail する。

**Suggestions**
- `src/model/data.py` を P03 または P05 スコープに追加: snapshot path / manifest / category map を parameterize し・`FEATURE_COLUMNS` を選択 snapshot から導出。
- `compute_speed_figure_for_history` は `obs_id` が無い場合内部で構築（`src/features/rolling.py:204-215` と対称）。
- `write_snapshot` の hash 挙動だけでなく・実際の `build_feature_matrix` 出力列を test。

**Risk Assessment:** **HIGH**（正しい Parquet が生成されたのに training が v1.0 列を使い続ける状態を生む）。

---

### 09-04 Plan — SC#4 AST audit + SC#5 domain 可視化

**Summary**
audit・domain 可視化 PLAN は価値があるが・SAFE-01 静的 audit は source-string/SQL check を強化する必要があり・可視化 script は既存 Plotly 再現性ディテールに従うべき。

**Strengths**
- SAFE-01 は具体的ソースアンカーを持つ: `TARGET_OBS_BANNED_COLUMNS` は `ninki`/`odds` を含む（`src/features/availability.py:91-100`）・allowlist enforcement は banned name を拒否（`src/features/availability.py:324-328`）。
- 計画された false-pass audit 形式は既存 adversarial audit 規律と整合（`tests/audit/test_audit_features.py:35-49`）。
- Plotly external JS は既存パターン（`src/model/segment_eval.py:447-452`）。

**Concerns**
- **HIGH:** AST Name/Attribute check + 完全文字列一致では・SQL 文字列に埋め込まれた禁止トークンを見逃す。既存 builder SELECT 列は `nr.sibababacd AS hist_sibababacd`（`src/features/builder.py:116-120`）のような SQL 文字列定数。将来の `"ur.ninki AS prior_ninki"` は `ast.Constant` 文字列で `ninki` を含むが `"ninki"` と完全一致しない。
- **HIGH:** `data.py` が parameterize されない限り `FEATURE_COLUMNS` audit は v1.0 を指し続ける（`src/model/data.py:77-79`・`:160-176`）。
- **MEDIUM:** `build_feature_matrix` は DataFrame でなく dict を返す（`src/features/builder.py:590-596`）・domain script は `result["feature_matrix"]` を使う必要。
- **MEDIUM:** byte-reproducible HTML には `include_plotlyjs="directory"` だけでは不十分。既存コードは `div_id` も固定し random HTML ID を回避する（`src/model/segment_eval.py:445-452`）。

**Suggestions**
- audit を拡張し `_HISTORY_DB_SELECT_COLUMNS`, `_OBS_DB_SELECT_COLUMNS`, `_HISTORY_SELECT_COLUMNS`, `FEATURE_COLUMNS` を token substring / word-boundary check で検査。
- Plotly script で `div_id="speed-figure-domain"` または deterministic subplot ID を使用。
- domain script が plot 前に rolling speed 6列の存在を明示 assert。

**Risk Assessment:** **MEDIUM**（coverage intent は良いが・現 audit は SQL-string proxy leak を見逃す）。

---

### 09-05 Plan — SC#6 stop gate

**Summary**
この PLAN は運用リスクが最も高い。固定 binning と trainer 戻り値契約の識別は正しいが・提案された direct-training/load path は既存 orchestrator・hard-code snapshot 設計と衝突する。

**Strengths**
- 固定 binning 再利用はソースで裏付け: evaluator 定数は固定（`src/model/evaluator.py:88-91`）・segment odds band も固定（`src/model/segment_eval.py:72-75`）。
- `make_model_version` 使用は正しい: `{feature_snapshot_id}-{short}-v{N}` は実装済（`src/model/predict.py:105-146`）。
- trainer 戻り値契約は training 用としては正しく識別: LightGBM は fit 済み estimator（`src/model/trainer.py:545-629`）・CatBoost は `(model, sorted_index)`（`src/model/trainer.py:635-703`）。

**Concerns**
- **HIGH:** `load_feature_matrix()` は baseline/speed 両 snapshot をロードできない。引数を持たず `SNAPSHOT_PATH` のみを読む（`src/model/data.py:211-229`）・path は hard-code（`src/model/data.py:77-79`）。
- **HIGH:** 直接 `train_lightgbm(...).predict_proba(X_test)` は calibrated probability pipeline を skip する。現 production path は `train_and_predict` で train → calibrate → predict する: calibration は `src/model/orchestrator.py:478-507`・最終確率生成は `src/model/orchestrator.py:508-562`。**v1.0 baseline（calibration 済み）と speed_figure モデル（未 calibration）の比較は D-13 公平性違反**。
- **HIGH:** 直接 LightGBM 予測は categorical dtype mismatch を踏みうる。orchestrator は予測前に test category を明示的に再準備（`src/model/orchestrator.py:490-517`）・P05 の直接呼出はこれをしない。
- **HIGH:** CatBoost の alignment が・`train_catboost` が返す `sorted_index` を test 予測に使うと誤り。その index は training Pool 由来（`src/model/trainer.py:688-703`）・既存コードは test Pool を作り `sorted_test_idx` を使う（`src/model/orchestrator.py:519-538`）。
- **HIGH:** 診断用 odds 列名が誤り。現 odds snapshot 出力は `fuku_odds_lower`/`fuku_odds_upper`（`src/ev/odds_snapshot.py:210-215`・`:320-324`）・EV コードは `fukuodds` でなくこれらを消費（`src/ev/ev_rank.py:80-112`）。
- **MEDIUM:** `evaluate_all_segments` は one-axis-at-a-time で・`odds_band × p_bin × selected` の交差を計算しない。API は軸毎に独立 loop（`src/model/segment_eval.py:293-370`）。**D-14 指標1（odds_band×p_bin の selected/high-EV 層 calibration）を算出できない**。
- **MEDIUM:** JSON strict 出力は NaN sanitization が必要。evaluator は single-class AUC で NaN を出しうる（`src/model/evaluator.py:210-214`）・segment code は sanitizer パターンを持つ（`src/model/segment_eval.py:94-112`）。

**Suggestions**
- 両 snapshot で `src.model.orchestrator.train_and_predict` を使うか・calibration 済み予測 logic を再利用可能 helper に切り出す。raw trainer 予測を再実装しない。
- P05 の前に `data.py` で snapshot 読込を parameterize（manifest/category map path・`FEATURE_COLUMNS` 導出含む）。
- race-key disjoint・時系列 guard のため `split_3way(periods=...)` を再利用（checks は `src/model/data.py:601-629`）。
- `market_implied` に `fuku_odds_lower` を使い・diagnostic frame のみに厳格に留める。

**Risk Assessment:** **HIGH**（現状では stop-gate 結果が v1.0 と非比較になるか snapshot/model API mismatch で fail しうる）。

---

## Consensus Summary

### Agreed Strengths（单 reviewer だがソース裏付けあり）
- strict cutoff 契約（`CUTOFF_SEMANTICS`）・adversarial test 鋳型（`tests/audit/test_audit_features.py`）・`course_kubun` 削除根拠・`make_model_version` 形式など・既存パターンの再利用は概ね正確に識別されている。
- builder 挿入点（Step 5b・rolling 直前）・registry 拡張点（`_ROLLING_SYSTEMS`/yaml）は正しい。

### Agreed Concerns（最優先・複数 PLAN で反復するHIGHテーマ）
本 review で最も重要な HIGH テーマは **3 つの横断的仕掛け bug** で・複数 PLAN にまたがる:

1. **`data.py` SNAPSHOT_PATH 硬結合と FEATURE_COLUMNS の v1.0 固定**（P03 HIGH・P04 HIGH・P05 HIGH で反復）:
   - `SNAPSHOT_PATH`/`EXPECTED_FEATURE_COUNT` が hard-code（`src/model/data.py:77-79`）・`FEATURE_COLUMNS` は import 時に v1.0 Parquet から導出（`src/model/data.py:176`）・`load_feature_matrix()` が引数を持たない。
   - 影響: Phase 9 の speed_figure 6 feature が registry に追加されても・model input に入らない。stop gate が両 snapshot を比較できない。**「Parquet は正しく生成されたが学習は v1.0 のまま」**という静かな失敗。
   - **要対応**: P03 または P05 のスコープに `src/model/data.py` parameterization を明示的に追加（manifest/category_map path・`FEATURE_COLUMNS` 動的導出）。P03 must_haves に「`load_feature_matrix(snapshot_id)` が両 snapshot をロード可能」を追加。

2. **P05 stop gate が calibration pipeline を skip**（P05 HIGH）:
   - PLAN 09-05 は `train_lightgbm(...).predict_proba(X_test)[:, 1]` 直接呼出を指示するが・本番は `orchestrator.train_and_predict` で train → calibrate → predict する（`src/model/orchestrator.py:234, 478-562`）。CatBoost も同様（`sorted_test_idx` 必要・`src/model/orchestrator.py:519-538`）。
   - 影響: speed_figure モデルが未 calibration で・v1.0 baseline（calibration 済み）と比較される → **D-13 公平性違反・stop gate 結果が無意味**。
   - **要対応**: P05 acceptance_criteria に「`orchestrator.train_and_predict` または同等の calibration pipeline を使用」を追加。raw trainer 直接予測を禁じる。

3. **P02 snapshot.py coercion と count_5 reserved の二重 bug**（P02 HIGH×2）:
   - (a) `_is_categorical_rolling_col` が `endswith("_5")` で判定（`src/features/snapshot.py:126`）し・`rolling_speed_figure_last_1`/`mean_3`（`_5` で終わらない）は coercion パスから脱落。
   - (b) `_RESERVED_NON_FEATURE_COLUMNS` が `rolling_{sys}_count_5` を自動展開（`src/features/availability.py:179`）し・`rolling_speed_figure_count_5` が FEATURE_COLUMNS から **silently** 除外。D-09 はこれを feature とするので矛盾。
   - **要対応**: snapshot.py の suffix 判定を可変 window に拡張。count_5 を feature とする場合は reserved 展開ロジックを特例化（または D-09 を修正し count_5 を audit-only に格下げ）。

### Plan-固有の追加 HIGH
- **P01 HIGH**: par/variant を per-observation（`obs_id` window）で算出しないと cross-observation PIT leak。PLAN 09-01 Task1 (h)(i) は history_filtered 全体で集約する記述で・per-observation 不変量が不明確。rolling.py の obs_id expand idiom（L236-265）と対称にするよう must_haves を強化。
- **P04 HIGH**: AST Name/Attribute check + 完全文字列一致では SQL 文字列内の `ur.ninki AS prior_ninki` を見逃す。token substring/word-boundary check を追加。
- **P05 HIGH**: 診断用 odds 列名が `fukuodds` でなく `fuku_odds_lower`/`fuku_odds_upper`（`src/ev/odds_snapshot.py:210-215`）。
- **P05 MEDIUM（機能上 HIGH寄り）**: `evaluate_all_segments` は `odds_band × p_bin × selected` 交差を計算しない（`src/model/segment_eval.py:293-370`）→ D-14 指標1 が算出できない。新規 helper が必要。

### Divergent Views / Open Questions
- 本 review は单 reviewer（Codex）のため・divergence なし。Claude 自己レビューは意図的に skip（`--codex` 指定・SELF_CLI=claude）。別視点（Gemini 等）を求める場合は `--gemini` 追加で再実行可能。

### CYCLE_SUMMARY（暫定・planner 取込み後更新）
- **current_high**: 8（横断3テーマ + プラン固有5）
  - H1: data.py SNAPSHOT_PATH 硬結合・FEATURE_COLUMNS v1.0 固定（P03/P04/P05 横断）
  - H2: P05 stop gate calibration pipeline skip（D-13 公平性違反）
  - H3: P02 snapshot.py `_5` suffix coercion + count_5 reserved 二重 bug
  - H4: P01 par/variant per-observation PIT 不変量 明確化不足
  - H5: P04 AST audit が SQL string proxy を見逃す
  - H6: P05 odds 列名 `fukuodds` 誤り（正: `fuku_odds_lower`/`fuku_odds_upper`）
  - H7: P05 CatBoost `sorted_index` を test 予測に誤用（正: `sorted_test_idx`）
  - H8: P05 LightGBM 直接予測で categorical dtype mismatch リスク
- **current_actionable**: 4
  - M1（P02 LOW）: PLAN が「既存7系統」と書くが実際は8系統（`timediff`/`babacd` 含む）・test/doc のカウント訂正要
  - M2（P04 MEDIUM）: `build_feature_matrix` は dict を返す（`src/features/builder.py:590-596`）・domain script は `result["feature_matrix"]` を使うよう PLAN に明記要
  - M3（P04 MEDIUM）: byte-reproducible HTML には `include_plotlyjs="directory"` だけでなく `div_id` 固定も必要（`src/model/segment_eval.py:445-452`）
  - M4（P05 MEDIUM）: JSON strict 出力に NaN sanitization 要（single-class AUC で NaN・`src/model/segment_eval.py:94-112` の sanitizer pattern 踏襲）

---

## Verification Coverage（source-grounding 監査）

本 review が根拠として引用した実ソース（file:line・Codex が実読）:
- `src/features/availability.py:45, 91-100, 158-179, 324-328`
- `src/features/rolling.py:39-42, 49-55, 71-94, 204-225, 236-265`
- `src/features/builder.py:101-144, 195-312, 444-455, 457-493, 502-517, 580-596, 664-688`
- `src/features/snapshot.py:80-139, 115-139, 219`
- `src/model/data.py:77-79, 119-137, 149-176, 211-229, 405-430, 601-629`
- `src/model/trainer.py:545-629, 635-703`
- `src/model/orchestrator.py:234, 478-507, 508-562, 519-538`
- `src/model/evaluator.py:88-91, 210-214`
- `src/model/segment_eval.py:72-75, 94-112, 293-370, 445-452`
- `src/model/predict.py:105-146`
- `src/ev/odds_snapshot.py:210-215, 320-324`
- `src/ev/ev_rank.py:80-112`
- `src/config/feature_availability.yaml:129-135`
- `tests/audit/test_audit_features.py:35-49, 69-87, 100-119`
- `scripts/run_train_predict.py:174-193`
