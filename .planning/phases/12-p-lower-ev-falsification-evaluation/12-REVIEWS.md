---
phase: 12
reviewers: [codex]
reviewed_at: 2026-06-27T19:55:00+09:00
plans_reviewed:
  - 12-01-PLAN.md
  - 12-02-PLAN.md
  - 12-03-PLAN.md
  - 12-04-PLAN.md
  - 12-05-PLAN.md
context_files:
  - 12-CONTEXT.md
  - 12-RESEARCH.md
  - 12-PATTERNS.md
source_grounding: "All reviewer findings cite file:line evidence verified by codex inside the git working tree at /Users/hart/develop/keiba-ai-v3. Claude re-verified each HIGH concern against the live source before consensus synthesis."
sanctuary_flags: [§11.2, §15.2, §19.1, SAFE-01, D-10, D-01 statistical rigor, D-05 clustered SE]
---

# Cross-AI Plan Review — Phase 12 (p_lower EV & Falsification Evaluation)

**Reviewers invoked:** codex (codex-cli 0.142.1・`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`)

**Grounding:** codex はプロジェクトの git working tree でファイルを直接精査（src/model/orchestrator.py・src/model/predict.py・src/db/schema.py・scripts/run_apply_schema.py・src/model/evaluator.py・src/ev/ev_rank.py・src/model/segment_eval.py・src/model/artifact.py・tests/audit/*.py 等）。Claude は codex の指摘全点を再検証しソース行で裏付けを取得済み。

**Phase 12 の位置づけ（core-value phase・聖域密度最高）:** §11.2 test 窓聖域（q_shrink / market_implied calibrator fit / falsification 回帰設計）・§15.2 事前登録指標不変・SAFE-01（odds/ninki proxy 排除・feature 構築経路と評価層の層分離）・§19.1 byte-reproducible・D-10（set_primary_model Call 0件・AST check）・D-01 統計的厳密さ（split conformal 過度な保証主張禁止）・D-05（race_id clustered SE・Holm 範囲）。リークリスク・閾値ドレッジングリスク・後知恵すり替えリスクは HIGH で扱う。

---

## Codex Review

### 全体 Summary

ソース照合の結果、Phase 12 の方向性は妥当。特に `p` モデルと odds/evaluation 層の分離設計、§15.2 指標を上書きしない方針、D-10 の `set_primary_model` 禁止はよく押さえている。一方で、現行コードとの接合部に数点の重大リスクがある。最大の論点は、(1) `q_shrink` を test 窓へどう注入するか、(2) `run_apply_schema.py` が新 migration を実際に適用するか、(3) Phase 12 WARN gate に必要な selected/odds-band 指標を `check_acceptance_gate` へどう渡すか、(4) falsification を「学習しない」と誤表現して監査を弱めないか、の4点。

### 12-01-PLAN

**Summary:** 基盤計画としては良い。`statsmodels` 追加、`p_lower` 純粋関数、3ファイル列連鎖はいずれも必要。ただし migration 適用経路と SAFE-01 監査設計に実装上の落とし穴がある。

**Strengths:**
- `statsmodels` 追加は必要。現状 `pyproject.toml` の dependencies には `scipy>=1.17.1` まであり、`statsmodels` は未追加（`pyproject.toml:10-27`）。
- 3ファイル連鎖を対象にしている点は正しい。`PREDICTION_COLUMNS` は現在19列で `p_fukusho_hit` 直後に追加余地があり（`src/model/predict.py:68-98`）、列順序は `_assert_valid_prediction_df` で完全一致検証されている（`src/model/predict.py:360-365`）。loader も `PREDICTION_COLUMNS` の明示列で INSERT する（`src/db/prediction_load.py:241-337`）。
- `race_relative.py` に置く純粋関数設計は既存の fail-loud 方針と合う。既存補正は `P_CAL_CLIP_EPSILON=1e-6` を持ち（`src/model/race_relative.py:70`）、非 finite を RuntimeError にしている（`src/model/race_relative.py:224-232`）。

**Concerns:**

- **[HIGH・C-12-01-1] `run_apply_schema.py` への migration step 追加が Plan 01 の files_modified に無く live-DB 適用が成立しない（§19.1 / memory: migration-privilege-admin-required）**
  - 証拠: `scripts/run_apply_schema.py:117-146` は `schema.APPLY_ORDER` を回さず手動リスト（`create_schemas / create_roles / create_raw_views / prediction_table / prediction_add_is_primary / prediction_add_provenance / prediction_extend_model_type_domain / backtest_table / grant_*`）で Step を適用している。
  - 機構: `12-01-PLAN.md` の `files_modified` に `scripts/run_apply_schema.py` が無く・Task 2 action は「schema.py の APPLY_ORDER に prediction_add_p_lower を追加」とだけ書く。しかし `run_apply_schema.py` は APPLY_ORDER を見ない。結果として Plan 12-05 checkpoint「owner/admin 権限で `run_apply_schema.py` 経由で適用」が成立せず・live-DB 上の `prediction.fukusho_prediction` に `p_fukusho_hit_lower` 列と `prediction_p_lower_range` CHECK 制約が追加されない。`prediction_load` の INSERT が列不足で失敗する silent or loud 破綻。
  - 影響: Phase 12 全体が live-DB で実行不能。SC#5 byte-reproducible スモークも不能。

- **[HIGH・C-12-01-2] §11.2 聖域は pure function シグネチャだけでは守り切れない（後続 Wave で値レベル adversarial test が必須）**
  - 証拠: `src/model/orchestrator.py:493-495` で `y_calib` と `y_test` が `make_X_y` の戻り値として同一スコープに同時に存在する。
  - 機構: 12-01 のテストが「`compute_p_lower_conformal_shrinkage` に `y_test` 引数がない」だけだと・12-02/12-04 側で呼出側が test outcome を混ぜる実装（例: `np.quantile(np.maximum(0, p_final_all - np.concatenate([y_calib, y_test])))` 等の全データ quantile）を検出できない。
  - 影響: §11.2 test 窓聖域違反（後知恵リーク）が silently 入り込む。falsification は test 窓 outcome を使って評価するが q_shrink 設計は train/calib のみなので・設計と監査の聖域が同一形状でないと機械保証が効かない。

- **[MEDIUM・C-12-01-3] SAFE-01 AST テストが単純な forbidden token 0件だと false red/false green になりやすい**
  - 証拠: `tests/audit/test_audit_race_relative.py:168-245` は `market_signal` を evaluation 専用として allow-list する仕組みを持つ。`src/model/race_relative.py:301-314` も `SAFE-01-ALLOW: market_signal` を明示。
  - 機構: falsification 層は正当に odds/market_implied を消費するが・既存 scanner は文字列定数も厳しく検出する（`tests/audit/test_audit_race_relative.py:118-130`）。allow-list marker と feature 構築経路非参照の検査を併用しないと false red（正しいコードが怒られる）または false green（feature への混入を見逃す）になる。
  - 影響: SAFE-01 監査の検出力低下。

- **[MEDIUM・C-12-01-4] race-relative / Phase 12 行で `p_fukusho_hit_lower` が非 NULL になる機構が必要**
  - 証拠: loader は欠損列を `row.get(c)` で None 化できる（`src/db/prediction_load.py:137-161`）。
  - 機構: NULL 許容は v1.0 binary 行の後方互換としては妥当だが・race-relative 行で p_lower が常に非 NULL になることの検証（race-relative 行の p_lower NULL は 0 件等）が Plan 01 に無い。
  - 影響: NULL の混入が EV 計算や selected-only calib gate で silent にマスクされる。

**Suggestions:**
- `PREDICTION_ADD_P_LOWER_SQL` を `schema.py` だけでなく `run_apply_schema.py` の手動 step list にも追加（files_modified に `scripts/run_apply_schema.py` を追加）。
- `p_lower` 監査は signature 検査に加え「test label を改変しても `q_shrink.json` が不変・calib label を改変すると変わる」値レベル adversarial test を 12-04/12-05 で必須化。
- SAFE-01 監査は既存 `market_signal` allow-list パターンを拡張し・market 参照と FEATURE_COLUMNS 混入を分けて検査。

**Risk Assessment:** MEDIUM（HIGH 2件を修正しないと live-DB で停止または §11.2 違反）。

---

### 12-02-PLAN

**Summary:** 挿入位置と EV 層の切替方針は妥当。ただし test 窓に適用する `q_shrink` の受け渡しが現計画では曖昧で・ここは Phase 12 最大の HIGH リスク。

**Strengths:**
- `p_lower` の挿入位置は正しい。race-relative 補正後に `p_final` が `pred_proba` へ戻される地点が明確（`src/model/orchestrator.py:747-754`）。
- artifact metadata 拡張は既存パターンに沿う（`src/model/artifact.py:98-110`, `src/model/artifact.py:202-216`）。
- EV 層の `p_col` 化は必要。現状 `compute_ev_and_rank` は `p_fukusho_hit` 固定で EV を計算し（`src/ev/ev_rank.py:80-113`）、`select_bets` も `p_fukusho_hit >= 0.15` 固定（`src/ev/purchase_simulator.py:93-98`）。

**Concerns:**

- **[HIGH・C-12-02-1] `score_split="test"` 経路で使う `q_shrink` の外部注入 API が未定義（§11.2 聖域違反に滑る・core value 最大リスク）**
  - 証拠: `src/model/orchestrator.py:273-291` の現行 `train_and_predict` signature に `p_lower_q_level` も `q_shrink` も無い。Plan 02 action は `p_lower_q_level` keyword-only 追加を明記するが・**test 窓で calib 済み `q_shrink` を受ける引数が不明**。
  - 機構: ここが曖昧だと test 窓で `y_test`（`src/model/orchestrator.py:493-495` に存在）を使った再計算に滑り・§11.2 聖域違反になる。Plan 02 Task 1 action (a) は「score_split='test' 経路では『θ選択経路で計算済みの q_shrink』を受け取る」と書くが・受け取り経路（orchestrator 引数・呼出側で外部 wrap・`pred_proba_lower` を直接渡す等）が未規定。
  - 影響: Phase 12 全体の EV 計算・falsification・switch_recommendation が §11.2 聖域違反を起こす可能性が高い。falsification と異なり q_shrink 設計は聖域なので test 窓使用は即 reject。

- **[MEDIUM・C-12-02-2] `predict_p_fukusho` への `pred_proba_lower` 注入が 12-02 の files_modified に入っていない（Wave 間コンパイル不整合）**
  - 証拠: 現行 `predict_p_fukusho` signature は `pred_proba` しか受けない（`src/model/predict.py:180-195`）。Plan 02 Task 1 action (d) は「`predict_p_fukusho` の呼出（L764-781）に `pred_proba_lower` を新引数で注入」と書くが・files_modified に `predict.py` が無い。
  - 機構: 12-01 で `PREDICTION_COLUMNS` 拡張だけを行い 12-02 で orchestrator 側から `pred_proba_lower` を注入しようとすると・`predict_p_fukusho` の引数が無く RuntimeError または silent 無視になる。
  - 影響: Wave 1→2 の境界でコンパイル不整合・または p_lower 列が常に None になる silent バグ。

- **[MEDIUM・C-12-02-3] `_rank` が旧 `p_fukusho_hit` を読み続けると EV は p_lower・ランク条件は点推定 p の混在になる**
  - 証拠: `src/ev/ev_rank.py:37-70` の `_rank` は `row.get("p_fukusho_hit")` 固定。S/A/B rank の判定に `p >= RANK_THRESHOLDS[...]["p_min"]` を使う。
  - 機構: Plan 02 Task 2 action は `compute_ev_and_rank` に `p_col` を追加するが・`_rank` に `p_col` を渡す経路が「`apply で渡す形も可（planner 裁量）」と曖昧。
  - 影響: 投票層（SC#4 WARN gate の対象）の定義が EV 計算と rank で分裂し・投票層 miscalibration の定量化が不正確になる。

- **[MEDIUM・C-12-02-4] `report.REPORT_COLUMNS` への p_lower/q_shrink 追加は Phase 5 report への影響が大きい**
  - 証拠: `src/ev/report.py:176-189` の `generate_report` は各 backtest dict が `REPORT_COLUMNS` 全キーを持つ前提。
  - 機構: 既存 backtest dict（v1.0 binary・Phase 11 race-relative）に p_lower 系キーが無いと KeyError または NaN 表示になる。
  - 影響: 既存 report 出力の regression。

- **[MEDIUM・C-12-02-5] artifact metadata JSON が `allow_nan=False` でない**
  - 証拠: `src/model/artifact.py:72-94` は `json.dumps(metadata_dict, sort_keys=True, ensure_ascii=False)` で `allow_nan=False` が無い。
  - 機構: `q_shrink` が NaN のまま JSON 化されると §19.1 byte-reproducible 厳密性が落ち、JSON 仕様違反の `NaN` リテラルが入る。
  - 影響: §19.1 再現性・JSON 厳密性低下。

**Suggestions:**
- `train_and_predict(..., p_lower_q_shrink: float | None = None, p_lower_q_level: float = 0.90)` のように test 経路の外部注入を明示し・`score_split="test"` で `theta is not None` かつ `p_lower_q_shrink is None` なら RuntimeError で fail-loud。
- `predict_p_fukusho` の `pred_proba_lower` 引数追加は 12-01 または 12-02 のどちらで行うかを固定（files_modified を更新）。
- `_rank` にも `p_col` を渡し・EV と rank の確率基準を一致させる。
- artifact metadata は `_sanitize_for_json` 相当・または `allow_nan=False` で fail-loud。

**Risk Assessment:** HIGH（`q_shrink` test 適用契約が未確定だと §11.2 違反または実装不能）。

---

### 12-03-PLAN

**Summary:** falsification・Phase 12 WARN gate・segment/slippage 拡張は必要な要素を押さえている。ただし現在の `evaluator` / `segment_eval` API とは食い違いがあり・falsification の統計表現にも修正が必要。

**Strengths:**
- odds band 再利用方針は正しい（`src/model/segment_eval.py:72-75`, `src/model/segment_eval.py:151-158`）。
- §15.2 指標を不変にする方針は既存構造と合う（`src/model/evaluator.py:172-263`）。
- sklearn 1.9 の prefit 方式として `FrozenEstimator` を使う計画は現行 idiom と一致（`src/utils/calibrator.py:1-15`, `src/utils/calibrator.py:96-102`）。

**Concerns:**

- **[HIGH・C-12-03-1] falsification を「学習しない」と書くのは統計的に危険・回帰仕様の後知恵変更を検出できなくなる（§11.2 / D-05 / D-01 統計的厳密さ）**
  - 証拠: `statsmodels.Logit.fit` は test 窓 outcome を使って係数と p 値を推定する評価回帰。Phase 11 は test 窓評価前に選択経路を JSON 出力（`scripts/run_phase11_evaluation.py:29-34`, `:338-341`）。
  - 機構: falsification は test 窓で fit する評価回帰（`run_falsification_test` が `model.fit(...)` を呼ぶ）。これは事前登録された最終検定なら許容されるが・Plan 03 が「学習しない」と監査すると・回帰仕様（共変量・clip・subgroup）を test 評価後に変更しても聖域違反として検出できない。
  - 影響: §11.2 聖域の監査が弱くなり・threshold dredging（test 窓で仕様を練る）が見逃される。D-05 統計的厳密さ違反。

- **[HIGH・C-12-03-2] `check_acceptance_gate` は `metrics_dict`/`sum_p_check` しか受けず selected-only/odds-band conditional calib 入力が無い（§15.2 不変リスク）**
  - 証拠: `src/model/evaluator.py:888-891` の signature は `def check_acceptance_gate(metrics_dict, sum_p_check) -> dict`。
  - 機構: Plan 03 Task 2 action は「warn_reasons に selected-only/odds-band conditional calib を追加」と書くが・それらを計算する入力 DataFrame / selected_mask / odds_band が `check_acceptance_gate` に渡らない。結果として §15.2 指標の `metrics_dict` に混ぜる実装になりやすく・§15.2 不変性（D-06）が崩れる。
  - 影響: §15.2 事前登録指標の後知恵すり替え（D-06 違反）。SC#2 regression test も不十分になる。

- **[MEDIUM・C-12-03-3] `evaluate_segment_axis(axis='ev_decile')` 計画は現行 signature と合わない**
  - 証拠: `src/model/segment_eval.py:166-173` の `evaluate_segment_axis` は `segment_values` と `axis_name` を受ける低レベル関数。`evaluate_all_segments` は calibration curve 用で ROI 集計ではない（`src/model/segment_eval.py:293-368`）。
  - 機構: Plan 03 Task 2 action「`evaluate_segment_axis` に `axis='ev_decile'`/`'disagreement'` 軸を追加」は現行 API と整合しない。EV-decile ROI は calibration curve でなく `compute_backtest_metrics` の group-by 集計なので別関数が適切。
  - 影響: 実装不能または segment_eval の既存契約を破る regression。

- **[MEDIUM・C-12-03-4] market calibrator で base `LogisticRegression` と calibrator を同一 calib slice に fit すると校正データ二重使用**
  - 証拠: `src/utils/calibrator.py:12-15` docstring は model fitting と calibration data を手動で disjoint にする必要を明記。
  - 機構: Plan 03 Task 1 action の `fit_market_implied_calibrator` 実装は base.fit(X_calib, y_calib) と calibrator.fit(X_calib, y_calib) の両方を calib slice で行い二重使用。
  - 影響: market_implied 再校正の統計的有効性低下。Pitfall 5 (isotonic 過学習) のリスク増大。

- **[MEDIUM・C-12-03-5] slippage helper 提案 signature が既存 slot lookup を呼ばない**
  - 証拠: `src/ev/refund_accounting.py:38-75` の `_lookup_payfukusyo_pay` は row から払戻 slot を解決する。
  - 機構: Plan 03 Task 2 action の `compute_snapshot_final_slippage(payout_amount, fuku_odds_lower)` は slot lookup を経由せず・呼出側が slot 解決済みの payout_amount を渡す前提になる。「`_lookup_payfukusyo_pay` 再利用」とコメントと実装が不一致。
  - 影響: 実装時に slot lookup 経路が二重または欠落する silent バグ。

**Suggestions:**
- falsification は「pre-registered evaluation regression fitted on the test window」と明記し・仕様・共変量・clip・subgroup を test 評価前に JSON 出力（falsification-spec.json・q_shrink.json と同じく事前書き出し idiom）。
- `check_acceptance_gate` を無理に拡張せず・`phase12_metrics: dict | None = None` optional 引数か `check_phase12_warn_gate(...)` を分離（§15.2 gate の signature 不変）。
- EV-decile/disagreement ROI は `segment_eval` の calibration API でなく別関数で `compute_backtest_metrics` group-by に寄せる。
- market calibrator は train で base・calib で calibration の 2-window 分離、または `1/odds` をそのまま出す FrozenEstimator 相当の単純 estimator。

**Risk Assessment:** HIGH（統計表現と gate 入力設計を修正しないと §11.2/§15.2/D-05 の監査が弱くなる）。

---

### 12-04-PLAN

**Summary:** run script 統合計画としては Phase 11 の良い慣習を継承している。ただし 12-02/12-03 の未解決契約を引き継ぐため現時点では HIGH リスク。

**Strengths:**
- Phase 11 の構造を踏襲（`scripts/run_phase11_evaluation.py:271-280` statement_timeout・`:286-290` migration admin 経由分離）。
- q/selection の事前書き出しパターンは強い（`scripts/run_phase11_evaluation.py:338-341`, `:1084-1101`）。
- D-10 AST check は必要（`set_primary_model` は実際に `is_primary` を UPDATE する関数・`src/db/prediction_load.py:447-519`）。

**Concerns:**

- **[HIGH・C-12-04-1] `_compute_q_shrink_on_calib` の label alignment が曖昧（§11.2 / q_shrink 計算正確性）**
  - 証拠: `src/model/orchestrator.py:828-846` の `train_and_predict` 戻り値は `pred_df / splits / _aligned_pred_proba / race_relative_theta / score_split / ...` で `y_calib` を含まない。
  - 機構: Phase 11 は label 付与を `race_key + umaban` で fail-loud に行う（`scripts/run_phase11_evaluation.py:452-458`）。q_shrink も index 前提ではなく同等の機械的 join が必要。
  - 影響: q_shrink 計算の label/pred_proba alignment が silent にズレる。後知恵でなく計算自体が誤るリスク。

- **[HIGH・C-12-04-2] 12-02 の `q_shrink` 注入 API が未確定だと `score_split="test"` の p_lower 生成が成立しない（C-12-02-1 と同根・最大リスク）**
  - 証拠: `src/model/orchestrator.py:517-536` の score_split 切替ブロック・`:493-495` の `y_calib`/`y_test` 同時存在。
  - 機構: Plan 04 は `_compute_q_shrink_on_calib`（calib slice のみ）→ test 窓評価、という 2 段階を書くが・test 窓の p_lower 生成に必要な「calib 済み q_shrink を orchestrator へ渡す」経路が未定義（C-12-02-1 と同じ）。
  - 影響: Phase 12 の EV 計算・falsification が §11.2 違反または実装不能。

- **[MEDIUM・C-12-04-3] Phase 12 定数を `falsification.py` / `evaluator.py` / `run_phase12_evaluation.py` に重複定義すると閾値 drift の温床**
  - 証拠: Phase 11 は評価 script 側で evaluator/segment_eval の定数を import して契約を共有（`scripts/run_phase11_evaluation.py:101-118`）。
  - 機構: Plan 03 と Plan 04 で `Q_LEVEL`/`HOLM_ALPHA`/`MARKET_CALIB_SAMPLE_THRESHOLD`/`PHASE12_*_THRESHOLD` が重複定義される。
  - 影響: 閾値 drift・事前登録値の不整合・再現性（§19.1）低下。

- **[MEDIUM・C-12-04-4] Phase 11 docstring「load_predictions を呼ばない」は実際は呼んでいる・Phase 12 docstring の正確性要請**
  - 証拠: `scripts/run_phase11_evaluation.py:36-44` docstring は「`load_predictions` も `set_primary_model` も呼出しない」と書くが・`:418-440` で実際に `load_predictions` を呼ぶ。
  - 機構: Phase 12 に流用する際、D-10 対象を `set_primary_model` に限定し・永続化の有無を正確に書かないと AST check の根拠が曖昧になる。
  - 影響: doctruth 違反・監査の説明責任低下。

- **[MEDIUM・C-12-04-5] p_lower 列 migration の実適用は 12-01 の `run_apply_schema.py` 修正に依存（C-12-01-1 と同根）**
  - 証拠: `scripts/run_apply_schema.py:117-146` に p_lower step が無い。
  - 機構: Plan 04 の user_setup「owner/admin 権限で run_apply_schema.py を実行し PREDICTION_ADD_P_LOWER_SQL を適用」は・run_apply_schema.py に当該 step が無いと成立しない。
  - 影響: Plan 04 live-DB 実行が prediction_load INSERT 失敗で停止。

**Suggestions:**
- q_shrink 計算は `_attach_label_to_pred` と同じ key join パターンを使い・`q_shrink.json` を test 評価前に `allow_nan=False` で書く。
- Phase 12 の定数は単一モジュールに集約し run script は import。
- `set_primary_model` AST 0件は Call node のみを数え・docstring mention は許容する Phase 11 パターンを踏襲（`:36-44`）。

**Risk Assessment:** HIGH（統合 script は中核だが q_shrink の受け渡しと label alignment が未解決）。

---

### 12-05-PLAN

**Summary:** 監査・live DB checkpoint の設計は必要かつ概ね良い。ただし signature 検査中心では §11.2 リークを十分に検出できず・migration 検証手順にも実務上の誤りがある。

**Strengths:**
- 既存 audit mold を使う方針は強い（`tests/audit/test_audit_race_relative.py:11-27`, `:89-132`, `:383-471`）。
- D-10 の AST Call node 0件検査は適切（`src/db/prediction_load.py:447-519` に `set_primary_model` 実体が存在）。
- SAFE-01 の feature 側保証は既存構造に乗せられる（`src/model/data.py:17-23`, `:179-214`, `:455-510` が FEATURE_COLUMNS allowlist と列順序を固定）。

**Concerns:**

- **[HIGH・C-12-05-1] signature-only の leakage audit は不十分・値レベル adversarial test が必須（C-12-01-2 と同根・§11.2 聖域）**
  - 証拠: `src/model/orchestrator.py:493-495` の `y_calib`/`y_test` 同時存在。既存 audit は `tests/audit/test_audit_race_relative.py:250-314` で値レベル adversarial（α_r swap で出力変化）を検証。
  - 機構: 関数シグネチャに `y_test` がなくても・呼出側で test outcome を混ぜる実装は可能。signature 検査だけでは「呼出側が `compute_p_lower_conformal_shrinkage(p_final, np.concatenate([y_calib, y_test]), ...)` を呼ぶ」のを検出できない。
  - 影響: §11.2 聖域の実リーク検出力不足。Phase 12 の core value 保証が形骸化。

- **[MEDIUM・C-12-05-2] checkpoint:human-verify の `psql -f scripts/run_apply_schema.py` は誤り**
  - 証拠: `scripts/run_apply_schema.py:1-17` は Python script・Usage も `uv run python scripts/run_apply_schema.py`。
  - 機構: Plan 05 Task 2 how-to-verify step 1 の `psql -h <host> -U <admin_user> -d everydb2 -f scripts/run_apply_schema.py` は Python ファイルを psql で走らせようとし Syntax error になる。
  - 影響: 人間が手順通りに動かしても失敗する。checkpoint が実行不能。

- **[MEDIUM・C-12-05-3] falsification 層は正当に odds/market_implied を消費・allow-list marker と feature 経路非参照の検査併用が必須**
  - 証拠: `tests/audit/test_audit_race_relative.py:118-130` は文字列定数も厳しく検出。`:189-245` は market_signal allow-list 検証。
  - 機構: 評価層の allow-list marker と feature 構築経路非参照の検査を併用しないと false red/false green になる。
  - 影響: SAFE-01 監査の検出力低下。

- **[MEDIUM・C-12-05-4] `test_audit_field_strength.py` の snapshot 依存部分は snapshot 無いと skip**
  - 証拠: `tests/audit/test_audit_field_strength.py:214-276` は snapshot_path.exists() で skip する。
  - 機構: Phase 12 完了判定をこの skip 可能テストだけに依存させると弱い。
  - 影響: SC#5 GREEN の証明が不十分。

- **[MEDIUM・C-12-05-5] live DB migration 確認は列存在だけでなく `run_apply_schema.py` の step list 反映も検証対象にすべき**
  - 証拠: `scripts/run_apply_schema.py:117-146` に p_lower step が無い（C-12-01-1 と同根）。
  - 機構: information_schema.columns で列存在を確認しても・run_apply_schema.py の step list に予測値を入れていないと次回の再適用で消える or 適用されない。
  - 影響: 再現性（§19.1）の破壊。

**Suggestions:**
- adversarial audit に「test labels を改変しても `q_shrink.json` は不変・calib labels を改変すると `q_shrink` が変わる」を追加。
- `run_phase12_evaluation.py` の 2回実行 diff に加えて・`information_schema.columns` と `pg_constraint` で `p_fukusho_hit_lower` / `prediction_p_lower_range` を確認。
- 12-VERIFICATION は unit GREEN でなく live DB full suite と reports JSON bit-identical を完了条件にする。

**Risk Assessment:** MEDIUM-HIGH（監査の方向は良いが signature 中心では §11.2 実リーク検出力不足・live DB checkpoint 必須）。

---

## Consensus Summary

### 総合判定: 計画全体リスク HIGH

Phase 12 は core-value phase（§11.2 / §15.2 / SAFE-01 / §19.1 / D-10 / D-01 / D-05 の聖域密度が v1.1 で最高）。codex は 270KB のプロンプトに対しソースコード行番号付きで照合し・HIGH 6件（再帰的に 4 件の独立問題に集約）と MEDIUM 12件を提示。Claude は codex 指摘全点をソース再検証で裏付けた。**本 cycle では 1 reviewer（codex 指定）なので「複数 reviewer の合意」形成ではなく・codex の指摘を Claude が source で証明した形で consensus を構成する。**

### Agreed HIGH Concerns（優先修正 4 点）

1. **[HIGH] `q_shrink` の test 窓適用契約が未定義（C-12-02-1 / C-12-04-2）**
   - `train_and_predict(..., p_lower_q_shrink: float | None = None)` 等の外部注入 API を明示し・`score_split="test" and theta is not None and p_lower_q_shrink is None` で RuntimeError で fail-loud する契約を Plan 02/04 に固定。
   - これが無いと §11.2 test 窓聖域違反（test outcome で q_shrink 再計算）に滑るか・実装不能になる。

2. **[HIGH] `run_apply_schema.py` への migration step 追加が Plan 01 files_modified に無い（C-12-01-1 / C-12-04-5 / C-12-05-5）**
   - `scripts/run_apply_schema.py` を 12-01 の files_modified に追加し・手動 step list に `("prediction_add_p_lower", schema_module.PREDICTION_ADD_P_LOWER_SQL)` を挿入。
   - これが無いと live-DB に `p_fukusho_hit_lower` 列が追加されず Phase 12 全体が停止。

3. **[HIGH] `check_acceptance_gate` signature 拡張方針が現行 API と不一致（C-12-03-2）**
   - `check_acceptance_gate(metrics_dict, sum_p_check)` に手を入れず・`phase12_metrics: dict | None = None` optional 引数か `check_phase12_warn_gate(...)` 分離関数で実装。§15.2 gate の signature 不変。
   - これが無いと §15.2 事前登録指標の後知恵すり替え（D-06 違反）リスク。

4. **[HIGH] signature-only 監査では §11.2 実リークを検出できない・値レベル adversarial test 必須（C-12-01-2 / C-12-05-1）**
   - 「test labels を改変しても q_shrink は不変・calib labels を改変すると変わる」値レベル adversarial test を 12-04/12-05 に必須化。falsification は「pre-registered evaluation regression fitted on the test window」と正確に表現し仕様を事前 JSON 書き出し（C-12-03-1）。

### Agreed MEDIUM Concerns（PLAN 反映必要）

- **C-12-01-3**: SAFE-01 AST 監査は allow-list marker × feature 経路非参照の併用（false red/green 回避）。
- **C-12-01-4**: race-relative 行で p_lower が常に非 NULL になる検証。
- **C-12-02-2**: `predict_p_fukusho` への `pred_proba_lower` 注入を 12-01/02 のいずれかの files_modified に固定（Wave 間整合）。
- **C-12-02-3**: `_rank` にも `p_col` を渡し EV と rank の確率基準を一致。
- **C-12-02-4**: report.REPORT_COLUMNS 拡張は Phase 5 report 影響を避けるため Phase 12 専用 reports に閉じる。
- **C-12-02-5**: artifact metadata JSON `allow_nan=False`（§19.1 厳密性）。
- **C-12-03-3**: EV-decile/disagreement ROI は segment_eval の calibration API でなく別関数（`compute_backtest_metrics` group-by）。
- **C-12-03-4**: market calibrator の base と calibrator を train/calib で 2-window 分離（校正データ二重使用回避）。
- **C-12-03-5**: slippage helper は `_lookup_payfukusyo_pay` slot lookup を実際に呼ぶよう signature 整合。
- **C-12-04-3**: Phase 12 定数は単一モジュールに集約し重複定義回避。
- **C-12-04-4**: Phase 12 docstring は D-10 対象を `set_primary_model` に限定し正確に（Phase 11 docstring の「load_predictions 呼ばない」誤りを踏襲しない）。
- **C-12-05-2**: checkpoint:human-verify step 1 の `psql -f scripts/run_apply_schema.py` を `uv run python scripts/run_apply_schema.py` に修正。
- **C-12-05-4**: `test_audit_field_strength.py` snapshot skip 依存の完了判定を避け・live-DB full suite を完了条件に。

### Divergent Views

- 今 cycle は codex 単独 reviewer なので観点の相違は無い。ただし codex 内部で「falsification は学習する（評価回帰）」と「学習しない」の表現揺れが Plan 03 にあった結果・HIGH C-12-03-1 に統一して「事前登録評価回帰」とするよう suggestion を出した点は重要（統計的厳密さ D-01/D-05 の核心）。

---

## Verification Coverage (Source-Grounded Findings)

下記 `path:line` 証拠は codex が git working tree で直接確認し・Claude が再検証で裏付けた：

- `scripts/run_apply_schema.py:117-146`（手動 migration step list・APPLY_ORDER 不参照・p_lower step 欠如）
- `src/model/orchestrator.py:273-291`（`train_and_predict` signature・`p_lower_q_shrink`/`p_lower_q_level` 引数なし）
- `src/model/orchestrator.py:493-495`（`y_calib`/`y_test` 同時存在）
- `src/model/orchestrator.py:517-536`（score_split 切替ブロック）
- `src/model/orchestrator.py:747-754`（race-relative 補正後の pred_proba 復元点・p_lower 挿入位置は正しい）
- `src/model/orchestrator.py:828-846`（return dict・y_calib 含まない）
- `src/model/predict.py:68-98`（PREDICTION_COLUMNS 19列・p_fukusho_hit 直後の追加余地）
- `src/model/predict.py:180-195`（`predict_p_fukusho` signature・`pred_proba` のみで `pred_proba_lower` なし）
- `src/model/predict.py:360-365`（`_assert_valid_prediction_df` 列順序一致検証）
- `src/db/schema.py:380-403`（APPLY_ORDER・prediction_add_p_lower 欠如）
- `src/db/prediction_load.py:137-161`（`row.get(c)` で None 化）
- `src/db/prediction_load.py:447-519`（`set_primary_model` 実体）
- `src/db/prediction_load.py:241-337`（PREDICTION_COLUMNS ループ INSERT）
- `src/ev/ev_rank.py:37-70`（`_rank` が `row.get("p_fukusho_hit")` 固定）
- `src/ev/ev_rank.py:80-113`（compute_ev_and_rank EV_lower=p×odds_lower）
- `src/ev/purchase_simulator.py:93-98`（select_bets p_min=0.15 filter）
- `src/ev/report.py:176-189`（generate_report REPORT_COLUMNS 全キー前提）
- `src/ev/refund_accounting.py:38-75`（`_lookup_payfukusyo_pay` slot lookup）
- `src/model/segment_eval.py:72-75`（ODDS_BAND_EDGES/LABELS）
- `src/model/segment_eval.py:151-158`（`_odds_band`）
- `src/model/segment_eval.py:166-173`（`evaluate_segment_axis` 低レベル signature）
- `src/model/segment_eval.py:293-368`（`evaluate_all_segments` calibration curve 用）
- `src/model/evaluator.py:172-263`（compute_metrics §15.2 指標）
- `src/model/evaluator.py:888-891`（`check_acceptance_gate` signature）
- `src/model/artifact.py:72-94`（metadata JSON `allow_nan=False` なし）
- `src/model/artifact.py:98-110`/`:202-216`（save_native_artifact race_relative_theta idiom）
- `src/model/race_relative.py:70`（`P_CAL_CLIP_EPSILON=1e-6`）
- `src/model/race_relative.py:224-232`（非 finite RuntimeError）
- `src/model/race_relative.py:301-314`（SAFE-01-ALLOW: market_signal marker）
- `src/utils/calibrator.py:1-15`/`:96-102`（FrozenEstimator + CalibratedClassifierCV prefit idiom・disjoint data 注記）
- `src/model/data.py:17-23`/`:179-214`/`:455-510`（FEATURE_COLUMNS allowlist・列順序固定）
- `scripts/run_phase11_evaluation.py:29-34`/`:338-341`/`:1084-1101`（theta 選択経路事前書き出し idiom）
- `scripts/run_phase11_evaluation.py:36-44`（docstring「load_predictions 呼ばない」言及・実際は呼ぶ）
- `scripts/run_phase11_evaluation.py:101-118`（評価 script 側で evaluator/segment_eval 定数を import する idiom）
- `scripts/run_phase11_evaluation.py:271-280`（statement_timeout）
- `scripts/run_phase11_evaluation.py:286-290`（migration run_apply_schema.py 一本化注記）
- `scripts/run_phase11_evaluation.py:418-440`（load_predictions 呼出）
- `scripts/run_phase11_evaluation.py:452-458`（`_attach_label_to_pred` race_key+umaban fail-loud join）
- `tests/audit/test_audit_race_relative.py:11-27`/`:89-132`/`:118-130`/`:168-245`/`:250-314`/`:383-471`（5段階鋳型・forbidden scanner・allow-list marker・self-contained swap・false-pass detection）
- `tests/audit/test_audit_field_strength.py:214-276`（snapshot exists check で skip）
- `pyproject.toml:10-27`（dependencies・statsmodels 未追加・scipy>=1.17.1 まで）

**Plans to update via `/gsd-plan-phase 12 --reviews`:** 全 5 plan（12-01〜12-05）に上記 HIGH 4 点と MEDIUM 12 点を反映する必要がある。
