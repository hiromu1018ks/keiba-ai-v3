---
phase: 12
reviewers: [codex, claude]
cycle: 3
reviewed_at: 2026-06-27T21:15:00+09:00
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
  - (cycle 2) 12-REVIEWS.md (前 cycle の残件 MEDIUM 6 + LOW 2・本 cycle は取り込みを検証)
source_grounding: "All reviewer findings cite file:line evidence verified by codex (codex-cli 0.142.1・gpt-5.5 reasoning xhigh) and Claude inside the git working tree at /Users/hart/develop/keiba-ai-v3. Both reviewers independently identified the same C3-12-03-1 cross-plan Q_LEVEL_SHRINKAGE definition gap introduced by the cycle-2 revision."
sanctuary_flags: [§11.2, §15.2, §19.1, SAFE-01, D-10, D-01 statistical rigor, D-05 clustered SE]
---

# Cross-AI Plan Review — Phase 12 (p_lower EV & Falsification Evaluation) — Cycle 3 (FINAL)

**Reviewers invoked:** codex (codex-cli 0.142.1・`codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check`・model gpt-5.5 reasoning xhigh) + Claude (this session・自己検証で codex と同じ新規問題を独立発見)

**Cycle 3 (final・max=3) の目的:** Cycle 2 で挙がった残件 8 点（MEDIUM 6 + LOW 2）が commit `5c836de` で genuine に解決されたかを検証し・revision が新しく導入した問題（文献参照の行番号ズレ・新規セルフコントラディクション・副次セクション取り残し）をスキャンする。**Cycle 1・2 の既取り込み指摘は再提出しない。**

**Grounding:** codex はプロジェクトの git working tree で PLAN.md 5件・cycle 2 REVIEWS.md・ソース（race_relative/segment_eval/evaluator/orchestrator/refund_accounting/calibrator/run_phase11_evaluation 等）を直接精査。Claude は codex の探索結果をうけ・cycle-2 残件 8 点の解決と revision 由来の新規問題を PLAN.md とソースで再検証した。codex・Claude ともに独立に **同一の C3-12-03-1（Q_LEVEL_SHRINKAGE の cross-plan 定義欠落）** を発見し合意形成した。

---

## Codex Review (要約)

### 全体 Summary

Cycle 3 の評定: **未解決 HIGH 懸念は 0 件**。Cycle 2 で指摘した残件 8 点（MEDIUM 6 + LOW 2）は commit `5c836de` で副次セクション（prohibitions / threat_model / artifacts リスト / verification / checkpoint read_first / Output 行）にまで論理的に整合するよう genuine に修正された。ただし revision 過程で・Cycle 2 C2-12-04-2 を解決する際に **Plan 04 側の must_haves / action / done / imports は `Q_LEVEL_SHRINKAGE` を falsification.py から import するよう訂正した一方で・Plan 03 側の constants block 定義リスト（L126）に `Q_LEVEL_SHRINKAGE = 0.90` の追加が漏れ・producer/consumer の間に新規の不整合が生じた**。このため Plan 04 実行時に `from src.eval.falsification import Q_LEVEL_SHRINKAGE` が ImportError で停止する実行時ブロッカーになる（MEDIUM）。それ以外は Cycle 2 残件すべて RESOLVED・文献参照の行番号ズレ・副次セクション取り残しは見当たらない。

---

### Cycle 3 評定（Plan 別）

- **Plan 01 (12-01-PLAN.md):** FULLY RESOLVED. Cycle 2 残件 C2-12-01-1（statsmodels `==0.14.6` 厳密固定）・C2-12-01-2（SAFE-01 AST scan を `inspect.getsource(compute_p_lower_conformal_shrinkage)` 関数限定 + feature 経路 import 検査の併用）は must_haves / action / done / threat T-12-SC の全段階で整合。`src/model/race_relative.py:381` `__all__`（Plan01 L99 参照の L383 は2行差だが grep で解決するため実害なし）。
- **Plan 02 (12-02-PLAN.md):** FULLY RESOLVED. Cycle 2 で残件なし（Cycle 1 指摘は genuine に取り込み済み）。
- **Plan 03 (12-03-PLAN.md):** PARTIALLY RESOLVED. Cycle 2 残件 C2-12-03-1（prohibition L57 / threat T-12-12 L225「予測モデル p の再学習を行わない・事前登録評価回帰 fit は許容」に訂正）・C2-12-03-2（artifacts L43 / threat T-12-16 L229 / verification L236 で `compute_roi_by_bin` 別関数化）・C2-12-03-3（threat T-12-11 L224 を train/calib 2-window に訂正）・C2-12-03-4（artifacts L42 を falsification.py から import に訂正）はすべて解決。**ただし C3-12-03-1（後述）で constants block 定義 L126 に `Q_LEVEL_SHRINKAGE = 0.90` の追加が欠落し・Plan 04 との間に新規 cross-plan 不整合が発生。**
- **Plan 04 (12-04-PLAN.md):** PARTIALLY RESOLVED. Cycle 2 残件 C2-12-04-2（must_haves L43 / artifacts L48 / action L143 / done L170 / imports L141 ですべて `Q_LEVEL_SHRINKAGE` を falsification.py から import する形に統一）・C2-12-04-3（threat T-12-22 L205 を「予測モデル p の再学習を行わない・事前登録評価回帰 fit は許容」に訂正）は解決。Plan-04 reports 7→8 files typo（Output L80）も 8 ファイルに訂正済み。**ただし C3-12-03-1 の consumer 側として・import 先の定義が Plan 03 に存在しない。**
- **Plan 05 (12-05-PLAN.md):** FULLY RESOLVED. Cycle 2 残件 C2-12-05-1（checkpoint step 3 を 8 ファイル表記に・step 5 に falsification-spec.json の事前書き出し確認を追加・Task 3 read_first に falsification-spec.json を追加・SC#3 転記指示を追加）はすべて解決。

---

## Cycle 2 残件の解決検証（8 点）

1. **[LOW・C2-12-01-1] statsmodels `>=` vs `0.14.6` 不一致** → **RESOLVED.** `12-01-PLAN.md:29,47,48,65,111,123,212,224` がすべて `statsmodels==0.14.6`（厳密固定）に統一。threat T-12-SC の mitigate も `version==0.14.6（厳密固定・[C2-12-01-1]）` に訂正。
2. **[LOW・C2-12-01-2] Plan01 Test 6 が race_relative 全体 AST scan で _odds_band false-red** → **RESOLVED.** `12-01-PLAN.md:108`（Test 6）と `:126`（done）が `inspect.getsource(compute_p_lower_conformal_shrinkage)` 関数限定に変更。`src/model/race_relative.py:46,348-349` の既存 `_odds_band`（`compute_overprediction_penalty` 内）参照で false-red にならない。加えて `tests/audit/test_audit_race_relative.py:189-245` の allow-list + feature 経路非参照の併用検査を再利用し・Plan 05 の完全 AST scan と二重保証。
3. **[MEDIUM・C2-12-03-1] Plan03 prohibition L57 / threat T-12-12 L225「学習を行わない」残存** → **RESOLVED.** `12-03-PLAN.md:57`（prohibition）は「`予測モデル p の再学習を行わない`・事前登録評価回帰仕様を test 窓に fit する最終検定は許容」に訂正。`:216`（Trust Boundaries）と `:225`（threat T-12-12）も「`予測モデル p の再学習`」に訂正され・action L132 の `sm.Logit(...).fit(cov_type='cluster', cov_kwds={'groups': race_id_test})` と整合。action L132 と矛盾しない。
4. **[MEDIUM・C2-12-03-2] Plan03 artifacts L43 / threat T-12-16 L229 / verification L236 の evaluate_segment_axis 拡張記述残存** → **RESOLVED.** `12-03-PLAN.md:43`（artifacts）・`:229`（threat T-12-16）・`:236`（verification）がすべて「`compute_roi_by_bin` 別関数追加・`evaluate_segment_axis`（`src/model/segment_eval.py:166-173`）は不変」に訂正。must_haves L31 / action L187 / done L200 と完全一致。
5. **[MEDIUM・C2-12-03-3] Plan03 threat T-12-11 L224 が古い calib-only signature** → **RESOLVED.** `12-03-PLAN.md:224`（threat T-12-11）が `[C2-12-03-3]` tag 付きで `{odds_train, y_train, odds_calib, y_calib, calib_sample_size}` の train/calib 2-window に訂正。action L130・Test 1 L109・done L143 と完全一致。
6. **[MEDIUM・C2-12-03-4] Plan03 artifacts L42 が evaluator.py 定数追加で must_haves と矛盾** → **RESOLVED.** `12-03-PLAN.md:42`（artifacts）が `[C2-12-03-4 / C-12-04-3]` tag 付きで「`src/model/evaluator.py` は PHASE12_*_THRESHOLD を falsification.py の constants block から import し重複定義しない」に訂正。must_haves L35 / action L126 と完全一致。**ただし L126 の定数リストに `Q_LEVEL_SHRINKAGE` が含まれておらず・後述 C3-12-03-1 で新規不整合。**
7. **[MEDIUM・C2-12-04-2] Plan04 Q_LEVEL が must_haves と action で矛盾** → **RESOLVED on Plan04 side.** `12-04-PLAN.md:43,48,131,141,143,147,170` がすべて「`Q_LEVEL_SHRINKAGE` を falsification.py から import」に統一。Test 10 L131 の `grep -cE '^(Q_LEVEL|...)\\b' scripts/run_phase12_evaluation.py == 0` 検査と整合。done L170 の `<!-- planner-discipline-allow: Q_LEVEL -->` allow-list マーカーで grep 検査時の誤検知を回避。**ただし後述 C3-12-03-1 の consumer 側として import 元の定義が Plan 03 に存在しない。**
8. **[MEDIUM・C2-12-04-3] Plan04 threat T-12-22 L205「学習しない」残存** → **RESOLVED.** `12-04-PLAN.md:205`（threat T-12-22）が `[C2-12-04-3]` tag 付きで「`run_falsification_test は予測モデル p の再学習を行わない`・事前登録評価回帰仕様を test 窓に fit する最終検定は許容」に訂正。Plan 03 action L132 と Plan 03 prohibition L57 / threat T-12-12 L225 と三方整合。

追加:
9. **[LOW・派生] Plan-04 reports 7 vs 8 files typo** → **RESOLVED.** `12-04-PLAN.md:80`（Output）が「reports/12-evaluation/*（8ファイル）」に訂正。`:13/:54`（files_modified/artifacts）・`:129`（Test 8）・`:179`（done）の 8 ファイル表記と整合。
10. **[MEDIUM・C2-12-05-1] Plan05 checkpoint + Task3 falsification-spec.json 漏れ** → **RESOLVED.** `12-05-PLAN.md:172`（checkpoint step 3）が「8ファイル（falsification-spec.json 含む）」に訂正。`:176`（step 5）に falsification-spec.json の事前書き出し確認を追加。`:200`（Task 3 read_first）に falsification-spec.json を追加。`:208`（SC#3 転記指示）にも [C2-12-05-1] tag で事前書き出しの転記を明示。

---

## 新規問題（revision commit `5c836de` が導入）

### [MEDIUM・C3-12-03-1] Plan03 constants block L126 に `Q_LEVEL_SHRINKAGE = 0.90` の定義が欠落（C2-12-04-2 修正に伴う producer/consumer 不整合）

- **証拠:**
  - `12-03-PLAN.md:126`（Task 1 action・falsification.py constants block 集約指示）の定数リスト: `Q_LEVEL_FALSIFICATION = 0.05` / `HOLM_ALPHA = 0.05` / `LOGIT_CLIP_EPS = 1e-6` / `ODDS_CLIP_MIN = 1.0` / `ODDS_CLIP_MAX = 100.0` / `MARKET_CALIB_SAMPLE_THRESHOLD = 1000` / `PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD = 0.10` / `PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD = 0.15` — **`Q_LEVEL_SHRINKAGE` は含まれない**（`12-03-PLAN.md` 全文 grep で該当語 0 件）。
  - `12-04-PLAN.md:43`（must_haves）・`:48`（artifacts）・`:141`（action imports）・`:143`（action Q_LEVEL 集約指示）・`:147`（action _compute_q_shrink_on_calib）・`:170`（done）はすべて `Q_LEVEL_SHRINKAGE` を falsification.py から import する形で統一。
  - `12-04-PLAN.md:141` の imports 行: `from src.eval.falsification import run_falsification_test, fit_market_implied_calibrator, write_falsification_spec, LOGIT_CLIP_EPS, HOLM_ALPHA, MARKET_CALIB_SAMPLE_THRESHOLD, ODDS_CLIP_MIN, ODDS_CLIP_MAX, Q_LEVEL_FALSIFICATION, Q_LEVEL_SHRINKAGE, PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD, PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD`。

- **機構:** Cycle 2 C2-12-04-2 修正で Plan04 側は「`Q_LEVEL_SHRINKAGE: float = 0.90` を falsification.py に集約し run script は import」という方針に訂正されたが・**Plan03 側の constants block 定義リスト（L126）への `Q_LEVEL_SHRINKAGE` 追加が漏れた**。実行時・Plan03 を実行して falsification.py を作成すると `Q_LEVEL_SHRINKAGE` は定義されず・その後 Plan04 の imports 行（`from src.eval.falsification import ..., Q_LEVEL_SHRINKAGE, ...`）が `ImportError: cannot import name 'Q_LEVEL_SHRINKAGE' from 'src.eval.falsification'` で停止する。Wave 3 → Wave 4 の依存チェーン（`depends_on: [03]`）で実行されるため・Plan03 の実装者が L126 の定数リストだけを見てコードを書くと Plan04 で必須のシンボルが未定義になる。

- **影響:** §19.1 byte-reproducible の前提である「事前登録定数の一元化」が表面上は守られるが・実行時ブロッカー（ImportError）を引き起こす。閾値 drift ではなく単純な定義欠落（producer 側のシンボル未定義）のため・core value 聖域（§11.2 / SAFE-01 / §15.2 / D-10 / D-01 / D-05）を直接的に脅かすものではないが・`/gsd-execute-phase` が Plan04 で止まり Phase 12 全体が停止する実行可能 MEDIUM。

- **修正案（Plan03 側）:** `12-03-PLAN.md:126`（Task 1 action・falsification.py constants block 集約指示）の定数リストに `Q_LEVEL_SHRINKAGE: float = 0.90`（q_shrink 用・D-02・§11.2 聖域・Cycle 2 C2-12-04-2 で Plan04 側と合意した値）を追加。`Q_LEVEL_FALSIFICATION = 0.05`（falsification α 用）と命名で区別（q_shrink 用 0.90 vs falsification α 用 0.05）。これにより Plan04 の imports 行 `from src.eval.falsification import ..., Q_LEVEL_FALSIFICATION, Q_LEVEL_SHRINKAGE, ...` が解決可能になり・Cycle 1 C-12-04-3「重複定義回避」と Cycle 2 C2-12-04-2「Q_LEVEL も falsification.py 集約」が producer/consumer 両側で完全に遵守される。

---

### その他の revision 影響確認（問題なし）

- **文献参照行番号:** Plan03 prohibition L57 → action L132・artifacts L42 → must_haves L35/action L126・artifacts L43 → action L187・threat T-12-11 L224 → action L130・threat T-12-12 L225 → action L132・threat T-12-16 L229 → `src/model/segment_eval.py:166-173`・verification L236 → action L187/done L200。revision 前後で行番号ズレなし。Plan04 imports L141 → action L143・Test 10 L131 → must_haves L43 ズレなし。
- **副次セクション取り残し:** Plan03 L42-43（artifacts）/ L57（prohibition）/ L126（action constants）/ L130（action fit_market_implied_calibrator signature）/ L132（action run_falsification_test）/ L187（action compute_roi_by_bin）/ L216（Trust Boundaries）/ L224-225（threat T-12-11/12）/ L229（threat T-12-16）/ L236（verification）すべてが主経路（must_haves/Test/action/done）と一致。Plan04 L43/L48/L80/L131/L141/L143/L147/L170/L205 も同様。Plan05 L172/L176/L200/L208 も同様。
- **既存 _odds_band 参照:** `src/model/race_relative.py:46,348-349` の `_odds_band` は `compute_overprediction_penalty` 内（L262-381）に存在し・Plan01 L108/L126 で `inspect.getsource(compute_p_lower_conformal_shrinkage)` 関数限定に変更されたため false-red にならない（Plan01 の新規関数は L70 P_CAL_CLIP_EPSILON 周辺に追加予定で・`_odds_band` を参照しない）。
- **Q_LEVEL_FALSIFICATION と Q_LEVEL_SHRINKAGE の命名分離:** 修正案の命名（0.90 vs 0.05）は falsification.py 内で共存可能。`Q_LEVEL_FALSIFICATION` は既に Plan03 L126 で定義済み・`Q_LEVEL_SHRINKAGE` のみが未定義。

---

## Consensus Summary

### 総合判定: 計画全体リスク LOW（HIGH 懸念 0 件・残件 MEDIUM 1 件・新規 LOW 0 件）

Phase 12 は Cycle 2 で指摘した残件 8 点（MEDIUM 6 + LOW 2）を commit `5c836de` で副次セクションにまで論理的に整合するよう genuine に解決した。ただし C2-12-04-2 を解決する際に Plan04 側だけを訂正し・Plan03 側の constants block 定義リスト（L126）への `Q_LEVEL_SHRINKAGE` 追加が漏れたことで・producer/consumer 間に新規の MEDIUM 不整合（C3-12-03-1）が発生した。これは core value 聖域（§11.2 / SAFE-01 / §15.2 / D-10 / D-01 / D-05）を直接的に脅かすものでなく・実行時の ImportError で Plan04 が停止するだけの実装上の定義欠落であり・修正は Plan03 L126 の定数リストに `Q_LEVEL_SHRINKAGE: float = 0.90` を1行追加するのみ（極小）。

### Agreed HIGH Concerns REMAINING UNRESOLVED

**0 件。** Cycle 1 で挙がった HIGH 4 件（C-12-01-1 / C-12-02-1 / C-12-03-1 / C-12-03-2 + 派生）はすべて最新 PLAN.md に取り込まれ・Cycle 2・3 を通じて Claude と codex がソースコードと PLAN.md で照合して genuine incorporation を確認した。聖域（§11.2・SAFE-01・§15.2・§19.1・D-10・D-01・D-05）への直接的脅威は存在しない。

### Agreed MEDIUM/LOW Concerns REMAINING ACTIONABLE

**1 件 MEDIUM・0 件 LOW = 計 1 件。**

1. **[MEDIUM・C3-12-03-1] Plan03 constants block L126 に `Q_LEVEL_SHRINKAGE = 0.90` の定義が欠落**（`12-03-PLAN.md:126`）。Cycle 2 C2-12-04-2 修正に伴う producer/consumer 不整合。Plan04 L141 の imports 行 `from src.eval.falsification import ..., Q_LEVEL_SHRINKAGE, ...` が解決できず Plan04 実行時 ImportError で停止。 → Plan03 L126 の定数リストに `Q_LEVEL_SHRINKAGE: float = 0.90`（q_shrink 用・D-02・§11.2 聖域）を1行追加。`Q_LEVEL_FALSIFICATION = 0.05`（falsification α 用）と命名で区別。

### Divergent Views

Cycle 3 は codex と Claude が独立に同一の C3-12-03-1 を発見したため観点の相違はない。codex は `rg -n` 探索中に `src/eval: No such file or directory` エラー（Phase 12 未実行のため src/eval/ が未作成）で最終評定セクションを出力する前に処理を終えたが・それまでの思考ブロック（L2480「Cycle 2 の 8 件はほぼ全て該当箇所で解決済みです。一方で、今回の修正で Plan 04 が要求する `Q_LEVEL_SHRINKAGE` と Plan 03 が実際に作る定数リストの間に新しい producer/consumer 不整合が出ているので、その影響を確認しています。」）で明確に C3-12-03-1 を認識していた。Claude は codex の思考を確認する前に独立に grep で `Q_LEVEL_SHRINKAGE` の Plan03 内言及 0 件を発見し・producer 側定義欠落を確定させた。両者の評定は完全に合意。

---

## Verification Coverage (Source-Grounded Findings)

**Cycle 2 残件 8 点の解決検証証拠:**
- `12-01-PLAN.md:29,47,48,65,111,123,208,212,224`（statsmodels `==0.14.6` 厳密固定統一・C2-12-01-1）
- `12-01-PLAN.md:108,126`（inspect.getsource 関数限定 + feature 経路検査併用・C2-12-01-2）+ `src/model/race_relative.py:46,348-349`（_odds_band は compute_overprediction_penalty 内）
- `12-03-PLAN.md:57,216,225`（prohibition/Trust Boundary/threat T-12-12「予測モデル p の再学習を行わない」・C2-12-03-1）
- `12-03-PLAN.md:43,229,236`（artifacts/threat T-12-16/verification compute_roi_by_bin 別関数・C2-12-03-2）+ `src/model/segment_eval.py:166-173`（evaluate_segment_axis 不変）
- `12-03-PLAN.md:224`（threat T-12-11 train/calib 2-window signature・C2-12-03-3）
- `12-03-PLAN.md:42`（artifacts evaluator.py は falsification.py から import・C2-12-03-4）
- `12-04-PLAN.md:43,48,131,141,143,147,170`（Q_LEVEL_SHRINKAGE を falsification.py から import・C2-12-04-2）
- `12-04-PLAN.md:205`（threat T-12-22「予測モデル p の再学習を行わない」・C2-12-04-3）
- `12-04-PLAN.md:80`（Output 8 ファイル表記・Plan-04 reports typo）
- `12-05-PLAN.md:172,176,200,208`（checkpoint 8 ファイル + step 5 + Task 3 read_first + SC#3 転記・C2-12-05-1）

**Cycle 3 新規残件の証拠:**
- `12-03-PLAN.md:126`（Task 1 action・falsification.py constants block 集約指示の定数リスト）に `Q_LEVEL_SHRINKAGE` が含まれない（`grep -nE "Q_LEVEL_SHRINKAGE" 12-03-PLAN.md` == 0 件）
- `12-04-PLAN.md:43,48,141,147,170` が `Q_LEVEL_SHRINKAGE` を falsification.py から import する形で統一（consumer 側）
- `12-04-PLAN.md:141` の imports 行に `Q_LEVEL_SHRINKAGE` が明示的に含まれる（実行時 ImportError の発生箇所）

**Plans to update via `/gsd-plan-phase 12 --reviews`:** `12-03-PLAN.md` のみ。L126 の定数リストに `Q_LEVEL_SHRINKAGE: float = 0.90`（q_shrink 用・D-02・§11.2 聖域）を1行追加し・Plan04 の consumer 側と producer 側を整合させる。Cycle 1・2 の全指摘（HIGH 4 + MEDIUM 12 + MEDIUM 6 + LOW 2 = 計 24 件）は genuine に取り込まれており・今回の revision は1行の定義追加のみ。core value 聖域への新規リスクはなし。
