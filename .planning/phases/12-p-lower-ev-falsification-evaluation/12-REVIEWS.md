---
phase: 12
reviewers: [codex]
cycle: 2
reviewed_at: 2026-06-27T20:37:00+09:00
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
  - 12-VALIDATION.md
  - (cycle 1) 12-REVIEWS.md (前 cycle の HIGH 4 + MEDIUM 12 findings・本 cycle は取り込みを検証)
source_grounding: "All reviewer findings cite file:line evidence verified by codex inside the git working tree at /Users/hart/develop/keiba-ai-v3. Claude re-verified each remaining actionable concern against the live source and PLAN.md text before consensus synthesis."
sanctuary_flags: [§11.2, §15.2, §19.1, SAFE-01, D-10, D-01 statistical rigor, D-05 clustered SE]
---

# Cross-AI Plan Review — Phase 12 (p_lower EV & Falsification Evaluation) — Cycle 2

**Reviewers invoked:** codex (codex-cli 0.142.1・`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`・model gpt-5.5 reasoning xhigh)

**Cycle 2 の目的:** Cycle 1 で挙がった HIGH 4 件 + MEDIUM 12 件の指摘が最新 PLAN.md に genuine に取り込まれたかを検証し・加えて revision が導入した新規問題・residual gap を抽出する。**既に取り込まれた指摘を再提出しないこと**を前提とする。

**Grounding:** codex はプロジェクトの git working tree でファイルを直接精査（PLAN.md 5件・前 cycle REVIEWS.md・CONTEXT.md・ROADMAP.md・REQUIREMENTS.md・ソースコード orchestrator/predict/evaluator/segment_eval/refund_accounting/ev_rank/report/run_apply_schema/run_phase11_evaluation 等）。Claude は codex の残件全点を PLAN.md とソースで再検証した。

---

## Codex Review

### 全体 Summary

Cycle 2 の評定: **未解決 HIGH 懸念は 0 件**。Cycle 1 の HIGH 4 件（C-12-01-1 / C-12-02-1 / C-12-03-1 / C-12-03-2 + 派生）および MEDIUM 12 件は・最新 PLAN.md の task / action / must_haves / verify / done / threat_model / artifacts / explicit-deferral の各所に tag (`[C-12-XX-X / HIGH]` or `/ MEDIUM]`) 付きで明示的に取り込まれており・取り込みは genuine。ただし revision で PLAN 内の **prohibition / threat model / artifact リスト / checkpoint** などの副次的セクションに古い記述が取り残され・action と矛盾する箇所が 5 件・チェックリスト漏れが 2 件ある。これらは実行時に誤誘導のリスク（MEDIUM）または検証時の整合同然（LOW）であり・core value 聖域を脅かすものではない。

---

### 12-01-PLAN（Cycle 2 評定: PARTIALLY RESOLVED・残件 LOW 2）

**Cycle 1 取り込み状況（FULLY相当）:**
- **C-12-01-1 / HIGH**（run_apply_schema.py migration step list）: `12-01-PLAN.md:14` files_modified, `:36` must_haves, `:46` artifacts, `:141` read_first, `:153` Test 8, `:163` action, `:178` done — 全段階で `("prediction_add_p_lower", schema_module.PREDICTION_ADD_P_LOWER_SQL)` 挿入を明示。ソース `scripts/run_apply_schema.py:117-146` は手動 step list で APPLY_ORDER 不参照という Cycle 1 の診断通りで・Plan 01 の両箇所修正（schema.py APPLY_ORDER + run_apply_schema.py 手動 list）は正しい。**FULLY RESOLVED.**
- **C-12-01-4 / MEDIUM**（race-relative 行で p_lower 非 NULL）: `:37` must_haves, `:154` Test 9, `:165` action, `:182` done — 機械保証の検証命令が含まれる。**FULLY RESOLVED.**
- **C-12-05-2 / MEDIUM**（psql -f 誤り → uv run python）: `:169` action で「psql でなく uv run python」と訂正・Plan 05 checkpoint と整合。**FULLY RESOLVED.**

**Residual / New Issues:**

- **[LOW・C2-12-01-1] statsmodels バージョン `>=` 追加と厳密 `0.14.6` verify の不一致（§19.1 byte-reproducible）**
  - 証拠: `12-01-PLAN.md:29` must_haves は `statsmodels>=0.14.6`・`:47` artifact も `statsmodels>=0.14.6 追加`・`:65/:69` objective/output も `>=0.14.6`。`:48` artifact は `uv.lock に statsmodels 0.14.6`（厳密）・`:111` action は `uv add "statsmodels>=0.14.6"`（`>=` 指定）・`:123` done は `version 0.14.6`（厳密）。
  - 機構: `>=` で追加すると uv は 0.14.6 以上の最新利用可能版を解決する（2026-06 時点で 0.14.6 が最新だが将来的に 0.14.7 等が出ると `0.14.6` 厳密 verify が false fail になる）。現在 `pyproject.toml:10-27` に statsmodels は未追加のため実害はないが・`>=` 指定と厳密 verify は論理的に矛盾。
  - 影響: §19.1 byte-reproducible の軽微な一貫性欠陥。実行時に 0.14.6 以外が解決された場合の false fail または verify skip リスク。

- **[LOW・C2-12-01-2] SAFE-01 unit scan が `inspect.getsource(race_relative)` 全体を走査すると既存 `_odds_band` 参照で false-red（SAFE-01 監査検出力）**
  - 証拠: `12-01-PLAN.md:108` Test 6 は「`inspect.getsource(race_relative)` に odds/ninki/fukuodds の Name/Attribute/Constant 出現 0件」と全体スキャンを指示。`src/model/race_relative.py:46` に `from src.model.segment_eval import _odds_band`（既存・評価専用の正当な binning 参照）・`:348-349` に `_odds_band(pd.Series(market_signal))` の呼出。既存 audit は `tests/audit/test_audit_race_relative.py:189-245` で `market_signal` allow-list marker と feature 経路非参照の併用でこの正当な評価専用参照を許容する仕組みを持つ。
  - 機構: Test 6 を文字通り実装すると・既存の正当な `_odds_band` 参照が `odds` Name として検出され false-red になる。allow-list marker と feature 経路（FEATURE_COLUMNS/build_training_frame/load_feature_matrix）非参照の検査に切り替えるか・スキャン対象を `compute_p_lower_conformal_shrinkage` のみに限定しないと実行不能。
  - 影響: Plan 01 Task 1 が false-red で止まるか・実装者がテストを skip する silent fallback の入口。SAFE-01 監査の検出力低下。

---

### 12-02-PLAN（Cycle 2 評定: FULLY RESOLVED・残件なし）

**Cycle 1 取り込み状況:**
- **C-12-02-1 / HIGH**（q_shrink test 窓外部注入 API）: `:25` must_haves, `:38` artifacts, `:114-116` Test 8-10, `:121-125` action — `p_lower_q_shrink: float | None = None` と `p_lower_q_level: float = 0.90` の keyword-only 追加・`score_split='test' + theta is not None + p_lower_q_shrink is None` で `RuntimeError` fail-loud。ソース `src/model/orchestrator.py:273-291` は現在これら引数を持たない（Plan 02 で追加）が・追加位置と契約は明確。**FULLY RESOLVED.**
- **C-12-02-2 / MEDIUM**（predict_p_fukusho pred_proba_lower）: `:28` must_haves, `:39` artifacts, `:117` Test 11, `:131` action (d)。**FULLY RESOLVED.**
- **C-12-02-3 / MEDIUM**（_rank p_col 伝播）: `:30` must_haves, `:44` artifacts, `:173` Test 8, `:176` action。**FULLY RESOLVED.**
- **C-12-02-4 / MEDIUM**（report regression）: `:32` must_haves, `:46` artifacts, `:171` Test 6, `:180` action（選択 A/B を明示）。**FULLY RESOLVED.**
- **C-12-02-5 / MEDIUM**（artifact allow_nan=False）: `:33` must_haves, `:42` artifacts, `:118` Test 12, `:135` action。**FULLY RESOLVED.**

**Residual / New Issues:** なし。

**Risk Assessment:** LOW（Cycle 1 全指摘を genuine に取り込み・revision による新規問題なし）。

---

### 12-03-PLAN（Cycle 2 評定: PARTIALLY RESOLVED・残件 MEDIUM 4）

**Cycle 1 取り込み状況（主経路は FULLY）:**
- **C-12-03-1 / HIGH**（falsification 正確な表現）: `:27` must_haves, `:110` Test 2, `:132` action・`:148` done・`:136` write_falsification_spec ヘルパー — 主経路の action と test は「旧来の不正確な否定表現を削除し・『事前登録評価回帰を test 窓に fit する最終検定』と表現」と訂正済み。**FULLY RESOLVED on main path.**
- **C-12-03-2 / HIGH**（check_acceptance_gate signature 不変）: `:28` must_haves, `:174` Test 8, `:177-185` action — 選択 A（`check_phase12_warn_gate` 分離）または選択 B（`phase12_metrics: dict | None = None` optional 追加）を明示。ソース `src/model/evaluator.py:888-891` の現行 signature `check_acceptance_gate(metrics_dict, sum_p_check)` を不変にする方針。**FULLY RESOLVED.**
- **C-12-03-3 / MEDIUM**（EV-decile/disagreement ROI 別関数化）: `:31` must_haves, `:170` Test 4, `:187` action, `:200` done — `compute_roi_by_bin` 別関数で `evaluate_segment_axis` は不変。ソース `src/model/segment_eval.py:166-173`（calibration curve 用）・`:293-368`（`evaluate_all_segments` も calibration curve 用）と整合。**FULLY RESOLVED on main path.**
- **C-12-03-4 / MEDIUM**（base/calibrator 2-window 分離）: `:32` must_haves, `:118` Test 10, `:130` action, `:143` done。ソース `src/utils/calibrator.py:12-15` の disjoint data 注記と整合。**FULLY RESOLVED.**
- **C-12-03-5 / MEDIUM**（slippage helper slot lookup）: `:33` must_haves, `:171` Test 5, `:189` action — row 受け取り版と payout_amount 受け取り版の 2 種類提供で二重 slot lookup 回避。ソース `src/ev/refund_accounting.py:38-75` の `_lookup_payfukusyo_pay` と整合。**FULLY RESOLVED.**
- **C-12-04-3 / MEDIUM**（constants 集約）: `:35` must_haves, `:126` action で falsification.py の constants block 集約を指示。**PARTIALLY（後述の矛盾あり）.**

**Residual / New Issues:**

- **[MEDIUM・C2-12-03-1] prohibition/threat に古い「学習を行わない」表現が残存（C-12-03-1 の取り込み不十分）**
  - 証拠: `12-03-PLAN.md:57` prohibitions は「run_falsification_test は model_p/market_implied の『学習』を行わない」・`:225` threat model T-12-12 は「run_falsification_test は fit（学習）を行わない」と記載。一方 `:132` action は `model = sm.Logit(...); result = model.fit(cov_type='cluster', ...)` と明示的に `fit` を呼ぶ評価回帰を指示。
  - 機構: 主経路（action/test）は正確に訂正されたが・prohibitions と threat_model の記述が古いまま残り・内部矛盾。実行時・「学習を行わない」という prohibition を厳格に読む実装者が `model.fit(...)` 呼出を控えるか別経路で `sm.OLS` 等にすり替える誘導リスク。さらに audit 設計（`tests/audit/test_audit_p_lower_falsification.py`）で「fit を呼んではいけない」という誤検知の温床。
  - 影響: §11.2 聖域監査の形骸化・D-01/D-05 統計的厳密さの監査弱体化。式は「`run_falsification_test` は予測モデル `p` の学習を行わない・事前登録評価回帰仕様を test 窓に fit する最終検定」と訂正するか prohibition/threat から「学習を行わない」を削除。
  - **Plan 03 の修正必要:** prohibition L57 / threat T-12-12 L225 を「`p` 予測モデルの再学習を行わない（test 窓 outcome で `p` モデルを再 fit しない）。事前登録評価回帰仕様を test 窓に fit する最終検定は許容・仕様は falsification-spec.json で事前書き出し」に訂正。

- **[MEDIUM・C2-12-03-2] artifacts/verification/threat に古い evaluate_segment_axis 拡張記述が残存（C-12-03-3 と内部矛盾）**
  - 証拠: `12-03-PLAN.md:43` artifacts は「`evaluate_segment_axis` の軸拡張（'ev_decile' / 'disagreement'）」・`:229` threat T-12-16 は「`evaluate_segment_axis` の 'ev_decile'/'disagreement' 軸」・`:236` verification は「`segment_eval.evaluate_segment_axis` に ev_decile/disagreement 軸（既存 binning 再利用）」。一方 `:31` must_haves・`:170` Test 4・`:187` action・`:200` done は「`evaluate_segment_axis` でなく別関数 `compute_roi_by_bin`」と訂正済み。
  - 機構: 主経路は訂正されたが artifacts/threat/verification セクションに古い API 拡張指示が残り内部矛盾。実行時・artifacts リストに従い `evaluate_segment_axis` に `axis='ev_decile'` を実装しようとして・既存 calibration curve 用契約（`src/model/segment_eval.py:166-173`）を破る regression リスク。または threat T-12-16 の mitigate を「evaluate_segment_axis で binning 再利用」と読んで二重実装。
  - 影響: `evaluate_segment_axis` 既存契約破壊の regression・bit-identical binning の崩れ。Codex Cycle 1 HIGH#2「独自 binning 作成禁止」の精神への潜反。
  - **Plan 03 の修正必要:** artifacts L43 / threat T-12-16 L229 / verification L236 をすべて「`segment_eval.py に compute_roi_by_bin 別関数追加（evaluate_segment_axis は不変）」に訂正。

- **[MEDIUM・C2-12-03-3] threat T-12-11 の market calibrator signature が古い calib-only のまま（C-12-03-4 2-window 分離と矛盾）**
  - 証拠: `12-03-PLAN.md:224` threat T-12-11 は「シグネチャを `{odds_calib, y_calib, calib_sample_size}` のみに固定」と古い calib-only を記載。一方 `:109` Test 1・`:130` action・`:143` done は `fit_market_implied_calibrator(odds_train, y_train, odds_calib, y_calib, *, calib_sample_size)` の train/calib 2-window に訂正済み。
  - 機構: 主経路は 2-window 分離で訂正されたが・threat T-12-11 の mitigate 文が古い calib-only のまま残り内部矛盾。実行時・audit 設計者が threat T-12-11 に従い「`{odds_calib, y_calib, calib_sample_size}` のみ」を検証しようとして・実際の 5 引数実装を false-red で検知するリスク。または実装者が threat に合わせ 2-window を諦めて calib-only 二重使用に戻る誘導リスク。
  - 影響: 校正データ二重使用（C-12-03-4 regression）・Pitfall 5 isotonic 過学習リスク再発。
  - **Plan 03 の修正必要:** threat T-12-11 L224 の signature 記載を `{odds_train, y_train, odds_calib, y_calib, calib_sample_size}` の train/calib 2-window に訂正。

- **[MEDIUM・C2-12-03-4] constants 集約が artifacts と矛盾（C-12-04-3 部分不整合）**
  - 証拠: `12-03-PLAN.md:35` must_haves は「Phase 12 定数 が evaluator.py / segment_eval.py / refund_accounting.py / scripts/run_phase12_evaluation.py（Plan 04）に重複定義されず・単一モジュール（例: src/eval/falsification.py の constants block）に集約」。`:126` action も falsification.py constants block 集約を指示。一方 `:42` artifacts は「`src/model/evaluator.py に PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD / PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD 事前登録定数追加」。
  - 機構: must_haves/action は集約を指示するが・artifacts は evaluator.py への定数追加を指示し矛盾。実行時・artifacts リストに従い evaluator.py に定数を書き・must_haves の「重複定義なし」検証で false-red。
  - 影響: 閾値 drift（事前登録値の不整合）・再現性 §19.1 低下。Codex Cycle 1 C-12-04-3 の精神への反。
  - **Plan 03 の修正必要:** artifacts L42 を「`src/model/evaluator.py` は falsification.py の `PHASE12_*_THRESHOLD` 定数を import（重複定義なし）」に訂正。

---

### 12-04-PLAN（Cycle 2 評定: PARTIALLY RESOLVED・残件 MEDIUM 2 + LOW 1）

**Cycle 1 取り込み状況:**
- **C-12-04-1 / HIGH**（label alignment）: `:34` must_haves, `:50` artifacts, `:132` Test 11, `:147` action — `_attach_label_to_pred`（L452-458・race_key+umaban fail-loud join）と同じ key-join 機構。ソース `scripts/run_phase11_evaluation.py:452-458` と整合。**FULLY RESOLVED.**
- **C-12-04-2 / HIGH**（q_shrink test 外部注入）: `:35` must_haves, `:51` artifacts, `:133` Test 12, `:149` action — `orchestrator.train_and_predict(score_split='test', theta=1.0, p_lower_q_shrink=<calibで計算した値>)` で Plan 02 の keyword-only 引数が唯一の受取経路。**FULLY RESOLVED.**
- **C-12-01-2 / HIGH**（値レベル adversarial）: `:37` must_haves, `:55` artifacts, `:135` Test 14, `:163` action — test labels 改変で `q_shrink.json` sha256 不変・calib labels 改変で変化。**FULLY RESOLVED.**
- **C-12-03-1 / HIGH**（falsification-spec.json 事前書き出し）: `:36` must_haves, `:52` artifacts, `:134` Test 13, `:151` action, `:174` done。**FULLY RESOLVED.**
- **C-12-04-5 / HIGH**（migration 適用経路）: `:45` must_haves, `:159` action。**FULLY RESOLVED.**
- **C-12-04-4 / MEDIUM**（docstring 正確性）: `:44` must_haves, `:136` Test 15, `:145` action — Phase 11 docstring「load_predictions を呼ばない」誤りを踏襲せず。**FULLY RESOLVED.**

**Residual / New Issues:**

- **[LOW・C2-12-04-1] reports ファイル数が 7 / 8 で不一致（falsification-spec.json の扱い）**
  - 証拠: `12-04-PLAN.md:80` Output は「reports/12-evaluation/*（7ファイル）」。`:13/:54` files_modified/artifacts は 8 ファイル（falsification-spec.json 含む）・`:129` Test 8 は「8ファイル」・`:179` done も「8ファイル構造」。
  - 機構: 主経路（test/done）は 8 ファイルで falsification-spec.json を含むが・Output 行だけが古い 7 ファイルのまま。
  - 影響: 軽微な記述揺れ・実行時の検証（test 8 で検知）で整合するため実害は限定的。§19.1 byte-reproducible には影響しないがドキュメント整合性の観点で要訂正。

- **[MEDIUM・C2-12-04-2] C-12-04-3 constants 集約が Q_LEVEL について自己矛盾（C-12-04-3 部分不整合）**
  - 証拠: `12-04-PLAN.md:43` must_haves・`:48` artifacts・`:131` Test 10 は「`Q_LEVEL / HOLM_ALPHA / ...` が src/eval/falsification.py から import され run_phase12_evaluation.py に重複定義なし」。一方 `:143` action は「`Q_LEVEL も falsification.py の Q_LEVEL_FALSIFICATION とは別物（q_shrink 用 0.90 vs falsification α 用 0.05）のため・run script 側で Q_LEVEL: float = 0.90 を定義」」と run script 内定義を指示。`:170` done も「`Q_LEVEL=0.90` のみ run script 固有」と例外規定。
  - 機構: must_haves は Q_LEVEL を含めて import 強制するが・action と done は run script 固有と例外規定し内部矛盾。実行時・Test 10 の `grep -cE '^(Q_LEVEL|...)\\b' scripts/run_phase12_evaluation.py` == 0（must_haves 重複定義検証）を・action に従い `Q_LEVEL: float = 0.90` を定義すると false-red。
  - 影響: 閾値 drift・事前登録値の不整合・再現性 §19.1 低下。Codex Cycle 1 C-12-04-3「重複定義回避」の精神が Q_LEVEL について損なわれる。設計上 Q_LEVEL は falsification.py の `Q_LEVEL_FALSIFICATION`（α 用 0.05）と別物だが・両者を falsification.py に集約（例: `Q_LEVEL_SHRINKAGE = 0.90` と `Q_LEVEL_FALSIFICATION = 0.05` に命名分け）して run script は import する形に統一するか・must_haves の Q_LEVEL を除外して action/done の「run script 固有」に揃える必要がある。
  - **Plan 04 の修正必要:** `Q_LEVEL` の取り扱いを must_haves / action / done / Test 10 で一貫させる。（推奨: falsification.py で `Q_LEVEL_SHRINKAGE: float = 0.90` を定義し run script は import・Cycle 1 C-12-04-3 の「重複定義回避」を完全に遵守。）

- **[MEDIUM・C2-12-04-3] threat T-12-22 に「学習しない」古い表現が残存（C2-12-03-1 と同根）**
  - 証拠: `12-04-PLAN.md:205` threat T-12-22 は「run_falsification_test は test 窓予測のみで評価（学習しない）」。一方 Plan 03 action `:132` は `model.fit(...)` で評価回帰 fit を明示。
  - 機構: Plan 04 は Plan 03 の訂正を引用するが・Plan 04 自身の threat T-12-22 に古い表現が残り内部矛盾。audit 設計時の誤検知リスク。
  - 影響: §11.2 聖域監査の形骸化。
  - **Plan 04 の修正必要:** threat T-12-22 L205 を「run_falsification_test は予測モデル `p` の再学習を行わない・事前登録評価回帰仕様を test 窓に fit する最終検定（仕様は falsification-spec.json で事前書き出し）」に訂正。

---

### 12-05-PLAN（Cycle 2 評定: FULLY RESOLVED on Cycle 1・残件 MEDIUM 1）

**Cycle 1 取り込み状況:**
- **C-12-05-1 / HIGH**（値レベル adversarial）: `:33` must_haves, `:116` Test 9, `:136` action, `:149` done。**FULLY RESOLVED.**
- **C-12-01-3 / MEDIUM**（SAFE-01 allow-list と feature 経路非参照の併用）: `:34` must_haves, `:117` Test 10, `:138` action, `:150` done。**FULLY RESOLVED.**
- **C-12-05-3 / MEDIUM**: `:35` must_haves（C-12-01-3 と同根）。**FULLY RESOLVED.**
- **C-12-05-2 / MEDIUM**（psql -f → uv run python）: `:168` checkpoint step 1 で `uv run python scripts/run_apply_schema.py` に訂正済み。**FULLY RESOLVED.**
- **C-12-05-4 / MEDIUM**（snapshot skip 依存回避）: `:40` must_haves, `:170` checkpoint step 2 で「live-DB フルスイートと reports JSON bit-identical を完了条件」に訂正済み。**FULLY RESOLVED.**
- **C-12-05-5 / MEDIUM**（run_apply_schema.py step list 反映）: Plan 01 側で検証済み・Plan 05 checkpoint は information_schema で列存在と pg_constraint で CHECK 制約存在を確認。**FULLY RESOLVED.**

**Residual / New Issues:**

- **[MEDIUM・C2-12-05-1] checkpoint:human-verify と Task 3 read_first が falsification-spec.json を漏れ（C-12-03-1 の伝播不備）**
  - 証拠: `12-05-PLAN.md:172` checkpoint step 3 は「reports/12-evaluation/ に 12-evaluation.md/.json・falsification.md/.json・switch-recommendation.md/.json・q_shrink.json の7ファイル」と 7 ファイル列挙・falsification-spec.json を含まず。`:200` Task 3 read_first も「reports/12-evaluation/12-evaluation.md・falsification.md・switch-recommendation.md・q_shrink.json（Task 2 checkpoint で生成・実データ結果を転記）」と 4 ファイルで falsification-spec.json を含まず。一方 Plan 04 `:13/:54` files_modified/artifacts・`:129` Test 8・`:179` done は 8 ファイルで falsification-spec.json を含む。
  - 機構: Plan 04 で test 窓評価前の byte-reproducible な事前書き出しを必須化した `falsification-spec.json` が・Plan 05 checkpoint（最終確認）と Task 3（VERIFICATION.md 転記）で検証対象から漏れている。人間が checkpoint で「7ファイル生成されたから OK」と見なすと falsification-spec.json の生成忘れ・byte-reproducible 性崩れを検知できない。Task 3 も falsification-spec.json の内容（回帰仕様）を VERIFICATION.md に転記しないと・§11.2 聖域の threshold dredging 監査の成果物が記録に残らない。
  - 影響: §11.2 聖域監査（falsification-spec.json の事前書き出し）の最終確認 fallback。Cycle 1 C-12-03-1 / HIGH の精神が最終 checkpoint で表面的にしか履行されない。
  - **Plan 05 の修正必要:** checkpoint step 3（`:172`）を「7ファイル」→「8ファイル（falsification-spec.json 含む）」に訂正・step 5 に「falsification-spec.json が test 窓評価前に byte-reproducible で書き出されているか確認」を追加。Task 3 read_first（`:200`）に falsification-spec.json を追加し VERIFICATION.md の SC#3 セクションで「falsification-spec.json が事前書き出しされた」旨を記載するよう指示。

---

## Consensus Summary

### 総合判定: 計画全体リスク LOW（HIGH 懸念 0 件・残件 MEDIUM 6 + LOW 2）

Phase 12 は Cycle 1 で挙がった HIGH 4 件（実質的・C-12-01-1 / C-12-02-1 / C-12-03-1 / C-12-03-2 + 派生）と MEDIUM 12 件のすべてを・最新 PLAN.md の task / action / must_haves / verify / done / threat_model / artifacts / explicit-deferral の各セクションに tag 付きで genuine に取り込んだ。Cycle 2 では codex と Claude の合意で・取り込みは「主経路（action と test と must_haves）」については FULLY RESOLVED と判定した。ただし revision 過程で副次的セクション（prohibitions / threat_model / artifacts リスト / verification / checkpoint read_first）に古い記述が取り残され・action と矛盾する 5 件（Plan 03 に 4 件・Plan 04 に 1 件）と・チェックリストや定数集約で不整合 3 件（Plan 04 に 2 件・Plan 05 に 1 件）が残る。これらは実行時に誤誘導のリスク（MEDIUM）または検証時の整合同然（LOW）であり・core value 聖域（§11.2 / §15.2 / SAFE-01 / §19.1 / D-10 / D-01 / D-05）を直接的に脅かすものではない。

### Agreed HIGH Concerns REMAINING UNRESOLVED

**0 件。** Cycle 1 の HIGH 4 件はすべて最新 PLAN.md に取り込まれ・Claude がソース (`scripts/run_apply_schema.py:117-146`, `src/model/orchestrator.py:273-291/449-455/493-495`, `src/model/segment_eval.py:166-173/293-368`, `src/model/evaluator.py:888-891`, `src/ev/refund_accounting.py:38-75`, `src/utils/calibrator.py:12-15`) と照合して genuine incorporation を確認した。

### Agreed MEDIUM/LOW Concerns REMAINING ACTIONABLE

**6 件 MEDIUM + 2 件 LOW = 計 8 件。** すべて最新 PLAN.md に取り込まれていない・または取り込みが一部矛盾し `/gsd-execute-phase` には見えない実行時リスク。

1. **[MEDIUM・C2-12-03-1] Plan 03 prohibition L57 / threat T-12-12 L225 の「学習を行わない」古い表現残存**（`12-03-PLAN.md:57, :225`）。Plan 03 action `:132` は `model.fit(...)` を明示し内部矛盾。 → prohibition/threat を「`p` モデル再学習を行わない・事前登録評価回帰の test 窓 fit は許容」に訂正。

2. **[MEDIUM・C2-12-03-2] Plan 03 artifacts L43 / threat T-12-16 L229 / verification L236 の `evaluate_segment_axis` 拡張記述残存**（`12-03-PLAN.md:43, :229, :236`）。Plan 03 action `:187` は `compute_roi_by_bin` 別関数を指示し内部矛盾。 → 該当セクションをすべて「`segment_eval.py に compute_roi_by_bin 別関数追加（evaluate_segment_axis は不変）」に訂正。

3. **[MEDIUM・C2-12-03-3] Plan 03 threat T-12-11 L224 の market calibrator signature が古い calib-only 残存**（`12-03-PLAN.md:224`）。Plan 03 action `:130` は train/calib 2-window を指示し内部矛盾。 → threat T-12-11 を `{odds_train, y_train, odds_calib, y_calib, calib_sample_size}` に訂正。

4. **[MEDIUM・C2-12-03-4] Plan 03 artifacts L42 の「evaluator.py に PHASE12_*_THRESHOLD 定数追加」が must_haves L35 / action L126 の集約指示と矛盾**（C-12-04-3 部分不整合）。 → artifacts L42 を「`evaluator.py` は falsification.py の定数を import」に訂正。

5. **[MEDIUM・C2-12-04-2] Plan 04 Q_LEVEL の取り扱いが must_haves L43 / Test 10 L131 と action L143 / done L170 で矛盾**（C-12-04-3 部分不整合）。 → falsification.py で `Q_LEVEL_SHRINKAGE: float = 0.90` を定義し run script は import（C-12-04-3 完全遵守）するか・must_haves の Q_LEVEL を除外して run script 固有に統一。

6. **[MEDIUM・C2-12-04-3] Plan 04 threat T-12-22 L205 の「学習しない」古い表現残存**（C2-12-03-1 と同根・`12-04-PLAN.md:205`）。 → threat T-12-22 を「予測モデル `p` の再学習を行わない・事前登録評価回帰の test 窓 fit は許容」に訂正。

7. **[MEDIUM・C2-12-05-1] Plan 05 checkpoint step 3 L172 / Task 3 read_first L200 が falsification-spec.json 漏れ**（C-12-03-1 の伝播不備・`12-05-PLAN.md:172, :200`）。 → checkpoint を「7ファイル」→「8ファイル」に訂正・step 5 に事前書き出し確認を追加。Task 3 read_first に falsification-spec.json を追加し VERIFICATION.md の SC#3 への転記を指示。

8. **[LOW・C2-12-01-1] Plan 01 statsmodels バージョン `>=` 追加と厳密 `0.14.6` verify の不一致**（`12-01-PLAN.md:29, :48, :111, :123`）。 → `>=` を `==0.14.6` に固定するか・verify を「>=0.14.6」に緩和して一致させる（推奨: byte-reproducible のため `==0.14.6` 固定）。

9. **[LOW・C2-12-01-2] Plan 01 Test 6 SAFE-01 scan が race_relative.py 全体を走査し既存 `_odds_band` 参照で false-red**（`12-01-PLAN.md:108`; `src/model/race_relative.py:46, :348-349`）。 → Test 6 のスキャン対象を `compute_p_lower_conformal_shrinkage` のみに限定するか・`tests/audit/test_audit_race_relative.py:189-245` の allow-list + feature 経路非参照の検査に再利用。

### Divergent Views

Cycle 2 は codex 単独 reviewer なので観点の相違はない。Claude は codex の残件 8 点すべてを PLAN.md とソースコードで再検証し・すべて genuine であることを確認した。Cycle 1 で「falsification は学習する（評価回帰）」と「学習しない」の表現揺れを HIGH C-12-03-1 として統一したが・主経路のみ訂正され副次セクション（prohibitions / threat_model）に古い表現が残った点は・Cycle 2 の MEDIUM 6 件中 2 件（C2-12-03-1 / C2-12-04-3）の根因である。revision 後の見直しで主経路だけ追って副次セクションを更新し忘れた形で・文書一貫性の観点から要改善。

---

## Verification Coverage (Source-Grounded Findings)

Cycle 2 の指摘はすべて codex が git working tree で直接確認し・Claude が再検証で裏付けた：

**Cycle 1 取り込み genuine 性の検証証拠:**
- `scripts/run_apply_schema.py:117-146`（手動 migration step list・APPLY_ORDER 不参照・C-12-01-1 HIGH Plan 01 で両側修正）
- `src/model/orchestrator.py:273-291`（train_and_predict signature・C-12-02-1 HIGH Plan 02 で p_lower_q_shrink/q_level keyword-only 追加位置）
- `src/model/orchestrator.py:449-455`（score_split guard・構造的聖域ブロック・Cycle 1 codex HIGH#1）
- `src/model/orchestrator.py:493-495`（y_calib/y_test 同時存在・C-12-01-2 / C-12-05-1 値レベル adversarial test で検出）
- `src/model/evaluator.py:888-891`（check_acceptance_gate signature・C-12-03-2 HIGH Plan 03 で分離関数または optional 引数）
- `src/model/segment_eval.py:166-173`（evaluate_segment_axis calibration curve 用・C-12-03-3 MEDIUM Plan 03 で別関数化）
- `src/model/segment_eval.py:293-368`（evaluate_all_segments も calibration 用）
- `src/ev/refund_accounting.py:38-75`（_lookup_payfukusyo_pay slot lookup・C-12-03-5 MEDIUM Plan 03 で 2 種類 signature）
- `src/utils/calibrator.py:12-15`（disjoint data 注記・C-12-03-4 MEDIUM Plan 03 で 2-window 分離）
- `scripts/run_phase11_evaluation.py:452-458`（_attach_label_to_pred race_key+umaban fail-loud join・C-12-04-1 HIGH Plan 04 で q_shrink label alignment）

**Cycle 2 残件の証拠:**
- `12-01-PLAN.md:29, :47-48, :65, :69, :111, :123`（statsmodels `>=0.14.6` vs `0.14.6` 不一致）
- `12-01-PLAN.md:108`（Test 6 全体スキャン指示）+ `src/model/race_relative.py:46, :348-349`（既存 _odds_band 参照・false-red リスク）
- `12-03-PLAN.md:57, :225`（prohibition/threat「学習を行わない」残存）vs `:132`（action model.fit 明示）
- `12-03-PLAN.md:43, :229, :236`（artifacts/threat/verification evaluate_segment_axis 拡張残存）vs `:31, :170, :187, :200`（must_haves/Test/action/done 別関数指示）
- `12-03-PLAN.md:224`（threat T-12-11 古い calib-only signature）vs `:109, :130, :143`（train/calib 2-window 訂正）
- `12-03-PLAN.md:42`（artifacts evaluator.py 定数追加）vs `:35, :126`（must_haves/action falsification.py 集約）
- `12-04-PLAN.md:43, :131`（must_haves/Test 10 Q_LEVEL import 強制）vs `:143, :170`（action/done Q_LEVEL run script 固有）
- `12-04-PLAN.md:205`（threat T-12-22「学習しない」残存）
- `12-04-PLAN.md:80`（Output 7ファイル）vs `:13, :54, :129, :179`（8ファイル）
- `12-05-PLAN.md:172`（checkpoint step 3・7ファイル）+ `:200`（Task 3 read_first・4ファイル）vs `12-04-PLAN.md:13, :54, :129, :179`（8ファイル）

**Plans to update via `/gsd-plan-phase 12 --reviews`:** 全 5 plan のうち 12-01 / 12-03 / 12-04 / 12-05 の 4 plan に上記 MEDIUM 6 件 + LOW 2 件を反映する必要がある。12-02 は残件なし。Cycle 1 全指摘（HIGH 4 + MEDIUM 12）は genuine に取り込まれており・今回の revision は文書一貫性の修正・副次セクション更新・チェックリスト追加のみ。core value 聖域への新規リスクはなし。
