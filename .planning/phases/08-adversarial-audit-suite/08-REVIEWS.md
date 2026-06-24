---
phase: 8
reviewers: [codex]
reviewed_at: 2026-06-25T10:30:00Z
plans_reviewed:
  - 08-01-PLAN.md
  - 08-02-PLAN.md
  - 08-03-PLAN.md
cycle: 3
cycle_1_high_count: 3
cycle_1_actionable_count: 2
cycle_2_high_count: 0
cycle_2_actionable_count: 3
cycle_3_high_count: 0
cycle_3_actionable_count: 0
converged: true
---

# Cross-AI Plan Review — Phase 8 (Cycle 3 — CONVERGED, final cycle)

> **Cycle 3 of a plan-review-convergence loop（max-cycles cap 到達・最終 cycle）。** Phase 8 "Adversarial Audit Suite" の commit 731f679 改訂後 3 PLAN.md を Codex が再レビューし・オーケストレータ（Claude）が全指摘をライブコードベースで検証した。Cycle 2 の 3 actionable 指摘（NC-01 MEDIUM / NC-02 LOW / NC-03 LOW）の解決確認 + 改訂で新規導入された懸念の抽出が目的。F-01..F-05（Cycle 1）の regression チェックも実施。
>
> Reviewers invoked: Codex（codex-cli 0.139.0・model gpt-5.5・`codex exec --ephemeral --dangerously-bypass-hook-trust --sandbox read-only`）。Gemini / Cursor / Qwen / Antigravity / CodeRabbit 未インストール。Claude self-CLI は独立性規則で skip。OpenCode は `--codex` flag のみ指定のため未起動。
>
> **Methodology:** Codex cycle-3 指摘（NC-01..NC-03 解決判定 + 新規 LOW 1 件 C3-01）を・オーケストレータが `scripts/run_backtest.py`・`scripts/run_train_predict.py`・`src/model/orchestrator.py`・`tests/model/test_trainer.py`・改訂 3 PLAN.md に対して検証した。Codex の解決判定 3 件全てが事実として確認され・新規 LOW 1 件（stale "3 step" text）も live ソースで再現確認後・本 cycle 中に修正済み（C3-01 を含む 4 箇所の stale text を 2 step 表記に訂正）。両パス一致。Cycle 3 は **CONVERGED**（残存 HIGH ゼロ・残存 actionable ゼロ・C3-01 修正により）。

## Verdict

**Cycle 3 is CONVERGED（最終 cycle）。** Cycle 2 の 3 指摘（NC-01 MEDIUM / NC-02 LOW / NC-03 LOW）は commit 731f679 改訂で全て解決（live ソースと完全整合）。F-01..F-05（Cycle 1）に regression なし。改訂で新規導入された懸念は C3-01（LOW・08-02/08-03 の verification/success_criteria/artifacts セクションに残る stale "3 step" text）のみで・本 cycle 中に 4 箇所とも "2 step" 表記に修正し解決。残存 HIGH ゼロ・残存 actionable ゼロ。Phase 8 は `/gsd-execute-phase` に進める。

## Codex Review (Cycle 3)

### Resolution Verdicts for Cycle 2 Findings

| Finding | Verdict | Evidence（commit 731f679 改訂 PLAN + live ソース整合） |
|---|:---:|---|
| **NC-01** [MEDIUM] 08-03 委譲 CLI の reports/05-backtest 上書き副作用 | **RESOLVED** | 改訂 08-03 が how-to-verify step 5（`08-03-PLAN.md:94-116`）に reports/05-backtest の退避→実行→復元→SHA byte-identical 検証の手順を追加。acceptance L145 が「実行前後で reports/05-backtest.{md,json} の SHA が byte-identical」を硬い条件化。live ソース整合: `run_backtest.py:1070`（`--check-reproduce` ブロック開始）・`:1090`（`logger.info("SC#4 reproduce smoke: 全 BT窓 PASS")` で block 終了・return なし）・`:1093`（`is_synthetic = bool(args.synthetic)` で通常 pipeline 継続）・`:1098`（通常 BT窓ループ）・`:1287-1295`（`generate_report` で reports/05-backtest 書込）。`--no-write-db` は DB 書込 skip のみでレポート書込は skip しない。退避/復元手順がこの副作用を構造的に中和する。 |
| **NC-02** [LOW] 08-02 acceptance の grep -c が docstring 由来マッチを弾けない | **RESOLVED** | 改訂 08-02 acceptance L135 が `grep -n "subprocess.run.*run_train_predict\|subprocess.run.*run_backtest"` に修正（subprocess.run 呼出に限定）。docstring/key_links の委譲説明（L22/L55-56/L112/L126）に含まれる `run_train_predict`/`run_backtest` 文字列は `subprocess.run` を伴わないため弾かれる。検証基準として正確。 |
| **NC-03** [LOW] 08-02 trainer smoke step の除外明記不足 | **RESOLVED** | 改訂 08-02 が trainer bit-identical step を当初から外し 2 step 構成に简化（action L116-120・acceptance L134）。live ソース整合: `tests/model/test_trainer.py` の6テスト（L105/148/194/277/492/645）はいずれも `reproduce/bit_identical/deterministic` キーワード非含。オーケストレータ実機検証 `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_trainer.py -q --collect-only -k "reproduce or bit_identical or deterministic"` → `no tests collected (6 deselected)`。将来 trainer に bit-identical テスト追加時に戻す旨を明記。 |

**Cycle 2 全 3 指摘が FULLY RESOLVED。**

### Regression Check — F-01..F-05（Cycle 1）

commit 731f679 改訂は NC-01..NC-03 対応が中心で・F-01..F-05 に関わる契約（CSV 4/5スタンプ分離・cursor ベース payout・08-02/08-03 責任分離・evaluation_metrics サーフェス）には触れていない。Cycle 2 で FULLY RESOLVED 判定の 5 件全てに regression なし。live ソース行参照（`src/ui/csv_columns.py:52-74/106-112`・`src/etl/label_reconcile.py:261/933`・`run_backtest.py:1031/1308-1317`・`run_train_predict.py:107-142/225/253`・`orchestrator.py:341-346`・`REQUIREMENTS.md:65`）は全て不変。

### New Concerns（commit 731f679 改訂で導入された懸念）

#### [C3-01] [LOW] — NC-03 修正（trainer step 外し・2 step 化）に伴う stale "3 step" text が verification/success_criteria/artifacts セクションに残存 → **本 cycle 中に修正済み**

- **Plan:** 08-02 / 08-03
- **Anchor:** `08-02-PLAN.md:231`（verification）・`:253`（Artifacts）・`08-03-PLAN.md:93`（how-to-verify step 4 期待結果）・`:143`（acceptance）
- **Claim:** NC-03 修正で action（08-02 L116-120）と acceptance（08-02 L134）は 2 step に正しく訂正されたが・verification / success_criteria / Artifacts / how-to-verify の各セクションに「3 step 全 PASS」「3 step subprocess」の古い記述が残った。
- **Reality（live ソース検証）:** 改訂直後の 4 箇所に "3 step" 文字列が残存（grep で確認）。実行ブロック性はない（action/acceptance が正しい 2 step を指定するため executor が組むコードは正しい）が・checkpoint:human-verify で人間が期待結果を照合する際の混乱源になる。
- **Disposition:** **本 cycle 中に修正済み。** 08-02 L231/L253 と 08-03 L93/L143 の 4 箇所を "2 step" 表記に訂正し・NC-03 の trainer 除外理由も併記。修正後 grep で "3 step" 残存 0 件を確認。
- **Severity rationale:** LOW — 実行ブロック性なし・Core Value（リーク防止・再現性）への侵害なし・純粋な documentation 整合性の取り残し。本 cycle で修正したため actionable 残存なし。

### Cross-Plan Consistency（commit 731f679 改訂後）

- **08-02 ↔ 08-03 live-DB 責任分離（F-02/F-03 + NC-01 の整合）:** 08-02 は DB 不要 2 step pytest のみ（autonomous/user_setup なし）・08-03 は live-DB CLI を集約し reports/05-backtest 副作用を退避/復元手順で中和。責任分界は一貫。
- **08-02 内部の step 数表記の一貫性（C3-01 修正後）:** action/acceptance/verification/success_criteria/artifacts 全てが 2 step 表記に統一。

### Overall Risk

**Overall risk: LOW（MEDIUM から更に改善）。** Cycle 1 の実行ブロック性 HIGH 3 件（Cycle 2 で RESOLVED）・Cycle 2 の MEDIUM 1 + LOW 2（Cycle 3 で RESOLVED）・Cycle 3 の LOW 1（C3-11・本 cycle 中に修正）。残存 HIGH ゼロ・残存 actionable ゼロ。Core Value（リーク防止・再現性）への侵害なし。

### Convergence

**CONVERGE（最終 cycle）。** 残存 HIGH ゼロ・残存 actionable ゼロ。max-cycles cap 到達。Phase 8 は `/gsd-execute-phase` に進める。

---

## Cycle 2 Record（参考・変更なし）

> **Cycle 2 of a plan-review-convergence loop.** Phase 8 "Adversarial Audit Suite" の改訂後（commit eff76c6）3 PLAN.md を Codex が再レビューし・オーケストレータ（Claude）が全指摘をライブコードベースで検証した。Cycle 1 の 5 指摘（HIGH 3 / MEDIUM 2）の解決確認 + 改訂で新規導入された懸念の抽出が目的。
>
> Reviewers invoked: Codex（codex-cli 0.139.0・model gpt-5.5・`codex exec --ephemeral --dangerously-bypass-hook-trust --sandbox read-only`）。Gemini / Cursor / Qwen / Antigravity / CodeRabbit 未インストール。Claude self-CLI は独立性規則で skip。OpenCode は `--codex` flag のみ指定のため未起動。
>
> **Methodology:** Codex cycle-2 指摘（F-01..F-05 解決判定 5 件 + 新規 MEDIUM 1 / LOW 2）を・オーケストレータが `scripts/run_backtest.py`・`scripts/run_train_predict.py`・`src/model/orchestrator.py`・`src/ui/csv_columns.py`・`src/etl/label_reconcile.py`・`tests/ui/test_csv_columns.py`・`tests/model/test_trainer.py`・`.planning/REQUIREMENTS.md` に対して検証した。Codex の解決判定 5 件全てが事実として確認され・新規 MEDIUM 1 / LOW 2 も live ソースで再現確認。両パス一致。Cycle 2 は **CONVERGED**（残存 HIGH ゼロ）。

## Verdict

**Cycle 2 is CONVERGED.** Cycle 1 の HIGH 3 件（F-01/F-02/F-03）は全て改訂で解決（live ソースと完全整合）・MEDIUM 2 件（F-04/F-05）も解決。改訂で新規導入された HIGH は無し。残るは MEDIUM 1 件（08-03 委譲 CLI の reports/05-backtest 上書き副作用）+ LOW 2 件（grep 受け入れ基準の表現・trainer smoke step の除外明記）で・いずれも追加 review cycle を要求しない運用上の改善点。Phase 8 は `/gsd-execute-phase` に進める。MEDIUM は 08-03 実行時にレポート破壊の二次リスクがあるため・推奨として 08-03 PLAN に反映することが望ましい（必須ではない）。

## Codex Review (Cycle 2)

### Resolution Verdicts for Cycle 1 Findings

| Finding | Verdict | Evidence（改訂 PLAN + live ソース整合） |
|---|:---:|---|
| **F-01** [HIGH] 08-01 CSV スタンプ契約 | **RESOLVED** | 改訂 08-01 が契約を分離: `PREDICTION_CSV_COLUMNS（4スタンプ...除外）および REPRODUCIBILITY_STAMPS（5スタンプ...含む）`（`08-01-PLAN.md:25`）。Task 3 read-first が `test_prediction_csv_has_all_stamps` を正しく引用し4スタンプ明記（`:185`）。action が `backtest_strategy_version を PREDICTION_CSV_COLUMNS に含む主張はしない`（`:202`）。live ソース整合: `src/ui/csv_columns.py:52-74` は4スタンプ + `prediction_created_at`（スタンプ別物）・`:106-112` の `REPRODUCIBILITY_STAMPS` は5項目で `backtest_strategy_version` 含む。`tests/ui/test_csv_columns.py:65` の実テスト名 `test_prediction_csv_has_all_stamps`（`_stks` typo は改訂で消失・`grep "all_stks" 08-01-PLAN.md` = 0 件）。 |
| **F-02** [HIGH] 08-02 synthetic backtest reproduce 非零 exit | **RESOLVED** | 08-02 は backtest CLI を呼ばない: `live-DB 必須 CLI は 08-03 checkpoint で証明`（`08-02-PLAN.md:21-22`）・key link が `run_backtest --synthetic --check-reproduce ... ValueError ... 08-02 では使用しない`（`:54-57`）。08-03 が `--synthetic` なしで live-DB 実行: `uv run python scripts/run_backtest.py --bt-filter BT-1 --check-reproduce --no-write-db`（`08-03-PLAN.md:94-100`）。live ソース整合: `run_backtest.py:1031`（`readonly_pool = None if args.synthetic`）・`:1308-1317`（`_prepare_feature_df` が `readonly_pool is None` でラベル未結合を返す）・`orchestrator.py:341-346`（`fukusho_hit_validated` 欠落で `raise ValueError`）。`--synthetic` なしの場合 `readonly_pool` は非None（live-DB）で `_prepare_feature_df` が `load_labels` でラベル結合するため ValueError 回路を回避。 |
| **F-03** [HIGH] 08-02 run_train_predict live-DB 衝突 | **RESOLVED** | 08-02 が live-DB CLI を明示的に 08-03 に委譲しつつ `autonomous: true / user_setup: []` を維持（`:21-22`・`:68-71`・`:125`）。08-03 は `autonomous: false`・PostgreSQL user_setup・`run_train_predict.py --check-reproduce --no-write-db` を実行（`08-03-PLAN.md:10-18`・`:94-100`・`:128`）。live ソース整合: `run_train_predict.py:107-142` の argparse に `--synthetic` 非存在・`:225` の `Settings()` で `.env` 必須・`:253` の `make_pool(role="readonly")` で live-DB 必須。 |
| **F-04** [MEDIUM] 08-01 payout DataFrame API 不一致 | **RESOLVED** | 改訂 08-01 が cursor-only を明記: `DataFrame 受けの API は存在しない`（`:148`）。behavior/action が mock cursor と `reconcile_against_payout(cur)["verdict"] == "fail"` を要求（`:155`・`:159`）・acceptance が DataFrame API 使用を禁止（`:171`）。live ソース整合: `_check_payout_recall(cur: Cursor)`（`label_reconcile.py:261`）・`reconcile_against_payout(cur: Cursor)`（`:933`）。`tests/test_label_reconcile.py:61` の `_mock_cursor` helper が cursor ベース検証の先例。 |
| **F-05** [MEDIUM] 08-02 evaluation_metrics サーフェス欠落 | **RESOLVED** | 08-02 must_haves が `SC#1 #1-#8 + 評価指標計算` を含む（`:23`）。Task 2 が `evaluation_metrics` を `SURFACE_ROWS` に明示追加し `tests/ev/test_metrics.py`・`tests/model/test_evaluator.py`・`tests/model/test_evaluator_gate.py` をマップ（`:164-166`）・acceptance が検証（`:201-202`）。live ソース整合: `REQUIREMENTS.md:65` の TEST-01 が「評価指標計算」を明示・3 テストファイル全て存在（28k/20k/7.1k）。 |

**Cycle 1 全 5 指摘が FULLY RESOLVED。** HIGH 3 件は実行ブロック性の事実誤差が改訂で修正され・live ソース行参照で整合確認済み。MEDIUM 2 件も修正。

### Strengths（改訂が改善した点）

- DB 不要合成層（08-02）と live-DB CLI 層（08-03）の責任分離が明確。08-02 は `autonomous: true / user_setup: []` を維持し SC#3 の合成層を担い・live-DB 必須 CLI は人間承認付き checkpoint に集約。
- 最も危険な契約誤り（CSV 5スタンプ・DataFrame API）を糊塗せず正しく修正: CSV スタンプを4列 export 契約と5スタンプ UI 表示契約に分離・payout reconciliation を cursor ベースに再定義。
- 08-03 checkpoint が 08-02 から委譲された正確なコマンド（`run_backtest` の `--synthetic` なし等）を明記し・`0 skipped` を live-DB suite の硬い条件化。

### New Concerns（改訂で導入された懸念）

#### [NC-01] [MEDIUM] — 08-03 委譲 CLI `run_backtest --bt-filter BT-1 --check-reproduce` が --check-reproduce 後に pipeline を継続し reports/05-backtest を上書きする

- **Plan:** 08-03
- **Anchor:** `08-03-PLAN.md:94-100`（how-to-verify step 5・`uv run python scripts/run_backtest.py --bt-filter BT-1 --check-reproduce --no-write-db`）・`:9`（`files_modified: []`）・`:40`（「検証のみ・files_modified 空」）・`:178-184`（Artifacts「新規ファイルパス: なし」）
- **Claim:** 08-03 の委譲 CLI は「検証のみ」で files_modified 空・レポート副作用なし。
- **Reality（live ソース検証）:**
  - `scripts/run_backtest.py:1070-1090` の `--check-reproduce` ブロックは `logger.info("SC#4 reproduce smoke: 全 BT窓 PASS")` で終わるが・**`return` しない**。
  - L1093 で `is_synthetic = bool(args.synthetic)` に進み・通常 BT窓ループ（train_and_predict 呼出・フル行列 backtest・`generate_report` による reports/05-backtest 生成）に継続。
  - L1287-1295 で reports/05-backtest.{md,json} を書込。
  - `--no-write-db` は DB 書込を skip するのみで**レポートファイル書込は skip しない**。
- **Impact:** 08-03 checkpoint 実行で既存の reports/05-backtest（Phase 5 成果物）が BT-1 単窓の結果で上書きされる。08-03「検証のみ・files_modified 空」の設計意図と矛盾。レポート破壊の二次リスク。
- **Note:** これは F-02 修正の副作用として現れた。F-02 は 08-02 から当該 CLI を除外して 08-03 に委譲したが・委譲先で CLI の副作用（pipeline 継続）が考慮されていない。
- **Severity rationale:** HIGH でない理由 — Phase 8 の success_criteria には直接影響しない（SC#3 は CLI の exit=0 で証明可能）・reports/05-backtest は Phase 5 の再生成可能 artefact（git 管理外想定）・Phase 8 の Core Value（リーク防止・再現性）への侵害なし。ただし運用上の副作用があり・08-03 PLAN への反映が望ましい。

#### [NC-02] [LOW] — 08-02 acceptance L134 の `grep -c` が docstring 由来のマッチを弾けない

- **Plan:** 08-02
- **Anchor:** `08-02-PLAN.md:134`（acceptance・「`grep -c "run_train_predict\|run_backtest" scripts/run_reproducibility_smoke.py` で subprocess 呼出箇所は0・docstring の委譲説明のみ」）
- **Claim:** `grep -c` で subprocess 呼出箇所が0であることを検証する。
- **Reality:** PLAN action L112 が docstring に「live-DB 必須の run_train_predict --check-reproduce / run_backtest --check-reproduce は本スクリプトでは呼ばず Plan 08-03 checkpoint が実行する」との委譲説明を**必須**化している。この docstring が `run_train_predict` / `run_backtest` 文字列を含むため `grep -c` は >=1 を返す。acceptance の注記「docstring の委譲説明のみ」は意図を正しく示すが・`grep -c` 自体は行数を返すため純粋な「subprocess 呼出 = 0」チェックとしては不正確。
- **Impact:** executor が acceptance を「`grep -c` の戻り値 == 0」と文字通り解釈すると・必須 docstring を書いた時点で acceptance が fail する（自己矛盾）。または executor が docstring を削って acceptance を通すと委譲説明が失われる。
- **Fix:** acceptance を「`grep -n "subprocess.run.*run_train_predict\|subprocess.run.*run_backtest" scripts/run_reproducibility_smoke.py` のマッチ行数 == 0」に修正（`subprocess.run` 呼出に限定）。これで docstring の言及は弾かれる。

#### [NC-03] [LOW] — 08-02 trainer smoke step（step 2）は現状該当テスト0件で必ず除外されるべきだが明記不足

- **Plan:** 08-02
- **Anchor:** `08-02-PLAN.md:118`（action step 2・`["uv", "run", "pytest", "tests/model/test_trainer.py", "-q", "-k", "reproduce or bit_identical or deterministic"]`・「※ 該当テストが存在する場合のみ（存在しない場合は step から除外・collect-only で確認）」）
- **Claim:** step 2 は条件付きで trainer bit-identical 群を実行する。
- **Reality（live ソース検証）:** `tests/model/test_trainer.py` の6テスト（`test_lightgbm_nonneg_codes` / `test_catboost_has_time` / `test_catboost_predict_preserves_row_order` / `test_no_target_encoding_leak` / `test_eval_set_disjoint_from_calib_test` / `test_no_target_encoding_imports_in_trainer_module`）はいずれも `reproduce/bit_identical/deterministic` キーワードを含まない。`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_trainer.py -q --collect-only -k "reproduce or bit_identical or deterministic"` は `no tests collected (6 deselected)` を返す。
- **Impact:** executor が collect-only を実際に実行しないと・step 2 は常に no-op（pytest は0件で exit=0 だが実質検証なし）。PLAN は「存在する場合のみ」と条件付きだが・現状必ず除外されることを明記すれば executor の判断コストが減る。
- **Fix:** action に「**現状（commit eff76c6 時点）tests/model/test_trainer.py に該当テストなし・collect-only で 0 件確認済み・step 2 は除外される**」を追記。または step 2 を当初から外し SC#4 calibrator bit-identical（step 1）+ tests/audit/（step 3）の2 step構成に简化。

### Cross-Plan Consistency（改訂後）

- **08-02 ↔ 08-03 live-DB 責任の分離（F-02/F-03 修正の成果）:** 改訂で 08-02 は `autonomous: true / user_setup: []` を維持し DB 不要 pytest のみ・08-03 は `autonomous: false / user_setup: postgresql` で live-DB CLI を集約。責任分界は明確になり循環依存は解消。ただし NC-01 の副作用（08-03 委譲 CLI の reports 上書き）が新たな一貫性課題。
- **08-01 ↔ 既存実装の契約整合（F-01/F-04 修正の成果）:** CSV 4/5スタンプ分離・cursor ベース payout で・`src/ui/csv_columns.py`・`src/etl/label_reconcile.py` と完全整合。typo `all_stks` 消失。

### Overall Risk

**Overall risk: MEDIUM（HIGH から改善）。** Cycle 1 の実行ブロック性 HIGH 3 件は全て解決し・live ソースと完全整合。新規 HIGH なし。残る MEDIUM 1 件（NC-01）は 08-03 実行時の reports/05-backtest 上書き副作用で・Phase 8 success_criteria に直接影響しないが運用上の注意が必要。LOW 2 件は表現の改善点。Core Value（リーク防止・再現性）への侵害なし。

### Convergence

**CONVERGE.** 残存 HIGH ゼロ。NC-01（MEDIUM）は 08-03 の実行メモに持ち込むことが望ましいが・追加 plan-review cycle を要求しない（「検証のみ」が厳密に「レポート書込なし」を意味するかをチームが決定したい場合を除く）。

---

## Consensus Summary

Single-reviewer cycle（Codex cycle 2 + orchestrator 独立検証）。オーケストレータの独立パスは Codex と同一の評決（CONVERGED・HIGH 0 / MEDIUM 1 / LOW 2・F-01..F-05 全て RESOLVED）を・同じソース行証拠で確認。両パスは一致。

### Resolution Status of Cycle 1 Findings

| ID | Cycle 1 Severity | Cycle 2 Verdict | Live Source Verification |
|---|---|---|---|
| F-01 | HIGH | **FULLY RESOLVED** | `src/ui/csv_columns.py:52-74`（4スタンプ）・`:106-112`（5スタンプ）・`tests/ui/test_csv_columns.py:65`（`_all_stamps`・typo 消失） |
| F-02 | HIGH | **FULLY RESOLVED** | `run_backtest.py:1031/1308-1317`・`orchestrator.py:341-346`（synthetic 経路の ValueError 確認・08-02 は呼ばない・08-03 は --synthetic なしで回避） |
| F-03 | HIGH | **FULLY RESOLVED** | `run_train_predict.py:107-142`（--synthetic 非存在）・`:225/253`（live-DB 必須・08-03 委譲） |
| F-04 | MEDIUM | **FULLY RESOLVED** | `label_reconcile.py:261/933`（cursor-only・PLAN が cursor ベースに再定義） |
| F-05 | MEDIUM | **FULLY RESOLVED** | `REQUIREMENTS.md:65`（評価指標計算）・3 テストファイル存在・SURFACE_ROWS に evaluation_metrics 追加 |

### New Concerns from Cycle 2

| ID | Severity | Plan | Required PLAN.md Change（推奨・必須でない） |
|---|---|---|---|
| NC-01 | MEDIUM | 08-03 | 08-03 の委譲 CLI 実行で reports/05-backtest が上書きされる副作用を PLAN に明記（「検証のみ・files_modified 空」の枠組みと調整）。実行前に reports/05-backtest を退避するか・tmp dir に隔離する手順を how-to-verify に追加することを推奨。 |
| NC-02 | LOW | 08-02 | acceptance L134 の `grep -c` を `grep -n "subprocess.run.*run_train_predict\|subprocess.run.*run_backtest"` に修正（docstring 由来のマッチを弾く）。 |
| NC-03 | LOW | 08-02 | action L118 に「現状 tests/model/test_trainer.py に該当テストなし（collect-only 0 件確認済み）・step 2 は除外される」を追記。または step 2 を当初から外す。 |

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 | Cycle 2 |
|---|---|---|
| HIGHs at contract level | 3（F-01/F-02/F-03） | **0**（全て RESOLVED） |
| Actionable MEDIUM/LOW unresolved | 2（F-04/F-05） | **0**（F-04/F-05 RESOLVED・新規 NC-01/NC-02/NC-03 は推奨改善・必須でない） |
| Convergence status | NOT CONVERGED | **CONVERGED** |

### Divergent Views

Not applicable（single reviewer + orchestrator 独立検証・unanimous）。

---

## Cycle 2 Verification Coverage（参考・Cycle 2 時点の記録）

The source-grounding requirement is satisfied by artifact paths and line references throughout. 全指摘は concrete なソース行 anchor で検証:

- **F-01 RESOLVED 検証:** `src/ui/csv_columns.py:52-74`（PREDICTION_CSV_COLUMNS 20列・4スタンプ odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id・`prediction_created_at` はスタンプ別物・`backtest_strategy_version` 非存在）・`src/ui/csv_columns.py:106-112`（REPRODUCIBILITY_STAMPS 5項目・UI 用・`backtest_strategy_version` 含む）・`tests/ui/test_csv_columns.py:65`（実テスト名 `test_prediction_csv_has_all_stamps`・docstring L68-70 で4スタンプ明記）。PLAN typo 箇所 `grep "all_stks" 08-01-PLAN.md` = 0 件（改訂で消失）。
- **F-02 RESOLVED 検証:** `scripts/run_backtest.py:1070`（`--check-reproduce` ブロック開始）・`:1090`（`logger.info("SC#4 reproduce smoke: 全 BT窓 PASS")` で block 終了・return なし）・`:1031`（`readonly_pool = None if args.synthetic`）・`:1308-1317`（`_prepare_feature_df` が `readonly_pool is None` で `load_feature_matrix()` 生戻り値・ラベル未結合）・`src/model/orchestrator.py:341-346`（`fukusho_hit_validated` 欠落で `raise ValueError`）。08-02 は当該 CLI を呼ばない（`08-02-PLAN.md:125`）・08-03 は `--synthetic` なしで live-DB 経由でラベル結合して回避。
- **F-03 RESOLVED 検証:** `scripts/run_train_predict.py:107-142`（argparse に `--synthetic` 非存在・確認済 flag: snapshot/model/version/reproduce/no-write/bt-filter/as-of）・`:225`（`Settings()` で `.env` 必須）・`:253`（`make_pool(role="readonly")` で live-DB 必須）・`:257-261`（`--check-reproduce` が `_prepare_feature_df(readonly_pool)` → `load_labels(cur)` を呼ぶ）。08-02 frontmatter `autonomous: true / user_setup: []` 維持（L14/L17）・08-03 frontmatter `autonomous: false / user_setup: postgresql`（L10/L13-18）。
- **F-04 RESOLVED 検証:** `src/etl/label_reconcile.py:261`（`_check_payout_recall(cur: Cursor)`）・`:933`（`reconcile_against_payout(cur: Cursor)`）・`tests/test_label_reconcile.py:61`（`_mock_cursor(fetch_map)` helper・cursor ベース検証の先例）。PLAN 08-01 L148/155/159/171 が cursor ベースに再定義。
- **F-05 RESOLVED 検証:** `.planning/REQUIREMENTS.md:65`（TEST-01 が「評価指標計算」を明示）・`tests/ev/test_metrics.py`（7.1k・存在）・`tests/model/test_evaluator.py`（28k・存在）・`tests/model/test_evaluator_gate.py`（20k・存在）。PLAN 08-02 L164-166/201-202 が evaluation_metrics サーフェス追加。
- **NC-01 検証（新規 MEDIUM）:** `scripts/run_backtest.py:1070-1090`（`--check-reproduce` ブロック・return なし）・`:1093`（`is_synthetic = bool(args.synthetic)` で通常 pipeline 継続）・`:1287-1295`（reports/05-backtest 書込）・`--no-write-db` は DB 書込 skip のみでレポート書込は skip しない。08-03 PLAN L9/L40/L178-184 が「検証のみ・files_modified 空」を主張し矛盾。
- **NC-02 検証（新規 LOW）:** 08-02 L112 が docstring の委譲説明（`run_train_predict`/`run_backtest` 文字列含む）を必須化・L134 の `grep -c` は行数を返すため docstring 由来マッチを弾けない（意図は注記済みだが機械検査としては不正確）。
- **NC-03 検証（新規 LOW）:** `tests/model/test_trainer.py` の6テスト（L105/148/194/277/492/645）はいずれも `reproduce/bit_identical/deterministic` キーワード非含。`KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_trainer.py -q --collect-only -k "reproduce or bit_identical or deterministic"` → `no tests collected (6 deselected)`。08-02 L118 は「存在する場合のみ」と条件付きだが現状必ず除外。

**Codebase claims were verified line-by-line by both Codex and the orchestrator**（Codex は `codex exec --ephemeral --dangerously-bypass-hook-trust --sandbox read-only` で read-only アクセス・オーケストレータは直接 Read/grep で二重検証）。両パスは F-01..F-05 RESOLVED 判定・NC-01/NC-02/NC-03 新規指摘全てで一致。

---

## Cycle 3 Consensus Summary

Single-reviewer cycle（Codex cycle 3 + orchestrator 独立検証）。オーケストレータの独立パスは Codex と同一の評決（CONVERGED・HIGH 0 / actionable 0・NC-01..NC-03 全て RESOLVED・F-01..F-05 regression なし・新規 C3-01 LOW は本 cycle 中に修正）を・同じソース行証拠で確認。両パスは一致。

### Resolution Status of Cycle 2 Findings

| ID | Cycle 2 Severity | Cycle 3 Verdict | Live Source Verification |
|---|---|---|---|
| NC-01 | MEDIUM | **FULLY RESOLVED** | `run_backtest.py:1070/1090/1093/1098/1287-1295`（--check-reproduce 後 pipeline 継続・reports/05-backtest 書込）・08-03 PLAN L94-116（退避→実行→復元→SHA 検証手順）・L145（acceptance・byte-identical 条件） |
| NC-02 | LOW | **FULLY RESOLVED** | 08-02 PLAN L135（`grep -n "subprocess.run.*..."` に修正・docstring マッチを弾く） |
| NC-03 | LOW | **FULLY RESOLVED** | 08-02 PLAN L116-120/L134（2 step 構成に简化）・`tests/model/test_trainer.py:105/148/194/277/492/645`（6テスト・キーワード非含）・実機 `--collect-only -k "reproduce or bit_identical or deterministic"` → `no tests collected (6 deselected)` |

### Cycle 1 Regression Check

| ID | Cycle 1 Severity | Cycle 3 Status | Notes |
|---|---|---|---|
| F-01 | HIGH | 仍 RESOLVED・regression なし | CSV 4/5スタンプ契約不変 |
| F-02 | HIGH | 仍 RESOLVED・regression なし | 08-02/08-03 責任分離不変 |
| F-03 | HIGH | 仍 RESOLVED・regression なし | 08-02 autonomous 維持・08-03 live-DB 委譲不変 |
| F-04 | MEDIUM | 仍 RESOLVED・regression なし | cursor ベース payout 不変 |
| F-05 | MEDIUM | 仍 RESOLVED・regression なし | evaluation_metrics サーフェス不変 |

### New Concerns from Cycle 3

| ID | Severity | Plan | Disposition |
|---|---|---|---|
| C3-01 | LOW | 08-02 / 08-03 | **本 cycle 中に修正済み** — verification/success_criteria/artifacts/how-to-verify の 4 箇所の stale "3 step" text を "2 step" 表記に訂正（NC-03 修正の取り残し） |

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 | Cycle 2 | Cycle 3 |
|---|---|---|---|
| HIGHs at contract level | 3（F-01/F-02/F-03） | 0（RESOLVED） | **0** |
| Actionable MEDIUM/LOW unresolved | 2（F-04/F-05） | 3（NC-01/NC-02/NC-03・推奨） | **0**（NC-01..NC-03 RESOLVED・C3-01 修正済み） |
| Convergence status | NOT CONVERGED | CONVERGED | **CONVERGED（最終）** |

### Divergent Views

Not applicable（single reviewer + orchestrator 独立検証・unanimous）。

---

## Cycle 3 Verification Coverage

The source-grounding requirement is satisfied by artifact paths and line references throughout. 全指摘は concrete なソース行 anchor で検証:

- **NC-01 RESOLVED 検証:** `scripts/run_backtest.py:1070`（`if args.check_reproduce:` ブロック開始）・`:1090`（`logger.info("SC#4 reproduce smoke: 全 BT窓 PASS")`・block 終了・**return なし**）・`:1093`（`is_synthetic = bool(args.synthetic)` で通常 pipeline 継続）・`:1098`（通常 BT窓ループ）・`:1287-1295`（`generate_report` で reports/05-backtest.{md,json} 書込）。`--no-write-db` は DB 書込 skip のみでレポート書込は skip しない。08-03 PLAN L94-116 の退避（`cp reports/05-backtest.{md,json} /tmp/...${STAMP}.bak`）→ CLI 実行 → 復元 → SHA byte-identical 検証（`test "$(shasum ...)" = "$ORIG_..."`）手順がこの副作用を構造的に中和。acceptance L145 が「実行前後で reports/05-backtest.{md,json} の SHA が byte-identical」を硬い条件化。
- **NC-02 RESOLVED 検証:** 08-02 PLAN L135 の acceptance が `grep -n "subprocess.run.*run_train_predict\|subprocess.run.*run_backtest" scripts/run_reproducibility_smoke.py` のマッチ行数 == 0 を要求。docstring（L112）・key_links（L22/L55-56/L126）の委譲説明は `subprocess.run` を伴わないため grep から弾かれる。subprocess 呼出に限定した正確な機械検査。
- **NC-03 RESOLVED 検証:** 08-02 PLAN action L116-120 が steps リストを (1) calibrator bit-identical / (2) tests/audit/ の 2 step に簡素化（trainer bit-identical 群は step から外す）。acceptance L134 も 2 step を明記。live ソース: `tests/model/test_trainer.py` の6テスト（`test_lightgbm_nonneg_codes` L105 / `test_catboost_has_time` L148 / `test_catboost_predict_preserves_row_order` L194 / `test_no_target_encoding_leak` L277 / `test_eval_set_disjoint_from_calib_test` L492 / `test_no_target_encoding_imports_in_trainer_module` L645）。実機検証: `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_trainer.py -q --collect-only -k "reproduce or bit_identical or deterministic"` → `no tests collected (6 deselected) in 0.20s`。将来 trainer に bit-identical テスト追加時に戻す旨を action/acceptance に明記。
- **C3-01 修正検証:** 修正前 4 箇所（`08-02-PLAN.md:231` verification・`:253` Artifacts・`08-03-PLAN.md:93` how-to-verify step 4・`:143` acceptance）に "3 step" 文字列が残存。修正後: `grep -n "3 step\|3 steps\|3step"` で 08-02/08-03 ともに 0 件。`grep -cn "2 step"` で 08-02=4 / 08-03=2 件に統一。
- **F-01..F-05 regression 検証:** commit 731f679 は NC-01..NC-03 対応が中心で F-01..F-05 契約には不触及。live ソース行参照（`src/ui/csv_columns.py:52-74/106-112`・`src/etl/label_reconcile.py:261/933`・`run_backtest.py:1031/1308-1317`・`run_train_predict.py:107-142/225/253`・`orchestrator.py:341-346`・`REQUIREMENTS.md:65`）は全て不変。regression なし。

**Codebase claims were verified line-by-line by both Codex and the orchestrator**（Codex は `codex exec --ephemeral --dangerously-bypass-hook-trust --sandbox read-only` で read-only アクセス・オーケストレータは直接 Read/grep/pytest で二重検証）。両パスは NC-01..NC-03 RESOLVED 判定・F-01..F-05 regression なし・C3-01 新規 LOW 指摘全てで一致。C3-01 は本 cycle 中に修正し解決。
