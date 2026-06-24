---
phase: 8
reviewers: [codex]
reviewed_at: 2026-06-24T23:30:00Z
plans_reviewed:
  - 08-01-PLAN.md
  - 08-02-PLAN.md
  - 08-03-PLAN.md
cycle: 1
cycle_1_high_count: 3
cycle_1_actionable_count: 2
converged: false
---

# Cross-AI Plan Review — Phase 8 (Cycle 1 — NOT CONVERGED)

> **Cycle 1 of a plan-review-convergence loop.** Phase 8 "Adversarial Audit Suite" の 3 つの PLAN.md（08-01 tests/audit/ adversarial・08-02 reproducibility smoke + reports/08-audit・08-03 live-DB full suite GREEN checkpoint）を Codex が独立レビューし・オーケストレータ（Claude）が全指摘をライブコードベースで line-by-line 検証した。
>
> Reviewers invoked: Codex (codex-cli 0.139.0, model gpt-5.5・`codex exec --sandbox read-only`)。Gemini / Cursor / Qwen / Antigravity / CodeRabbit 未インストール。Claude self-CLI は独立性規則で skip。OpenCode は `--codex` flag のみ指定のため未起動。
>
> **Methodology:** Codex cycle-1 指摘 5 件（HIGH 3 / MEDIUM 2）を・オーケストレータが実際のソース契約（`src/ui/csv_columns.py`・`tests/ui/test_csv_columns.py`・`scripts/run_backtest.py`・`scripts/run_train_predict.py`・`src/model/orchestrator.py`・`src/etl/label_reconcile.py`・`src/etl/quality_gate.py`・`tests/utils/test_group_split.py`・`tests/ui/test_readonly_guarantee.py`・`reports/04-eval.json`・`reports/06-evaluation.json`・`.planning/REQUIREMENTS.md`）に対して全て検証した。Codex 指摘 5 件全てが事実として確認され・オーケストレータ独立スキャンで追加の HIGH/MEDIUM は発見されず（両パスが一致）。Cycle 1 は NOT CONVERGED — planner による修正待ち。

## Verdict

**Cycle 1 is NOT CONVERGED.** 3 つの HIGH は実行ブロック性の事実誤差（CSV スタンプ契約誤認 / `run_backtest --synthetic --check-reproduce` がラベル未結合で ValueError で exit nonzero / `run_train_predict` に `--synthetic` flag 非存在で live-DB 必須）。2 つの MEDIUM は実行不能な API 指示と TEST-01 必須サーフェスのマッピング欠落。Phase 8 は `/gsd-execute-phase` に入る前に planner がこれら 5 件を修正する必要がある。

## Codex Review (Cycle 1)

### Findings

#### [F-01] [HIGH] — Prediction CSV スタンプ監査が存在しない列契約（5スタンプ誤認）を assert する

- **Plan:** 08-01
- **Anchor:** `08-01-PLAN.md:25`（must_haves truths・「PREDICTION_CSV_COLUMNS から再現性スタンプを欠落させると presence assert が fail」）、`:184`（Task 3 read_first・`test_prediction_csv_has_all_stks L65: presence assert で ... の5スタンプ検証`・**cross-reference テスト名 typo**）、`:201`（action・「5スタンプ（odds_snapshot_policy / odds_snapshot_at / model_version / feature_snapshot_id / **backtest_strategy_version**）を定数 _REPRO_STAMPS で定義。正規 PREDICTION_CSV_COLUMNS に対して全スタンプ存在を assert」）
- **Claim:** `PREDICTION_CSV_COLUMNS` は 5 つの再現性スタンプ（`odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version`）を含む。cross-reference テストは `test_prediction_csv_has_all_stks`。
- **Reality:**
  - `tests/ui/test_csv_columns.py:65` の実テスト名は **`test_prediction_csv_has_all_stamps`**（`_stks` でない・PLAN L184 の `all_stks` は typo・PATTERNS.md L16/186/223 と RESEARCH.md L319/554 は既に正しく `_stamps`）。
  - `src/ui/csv_columns.py:52-74` の `PREDICTION_CSV_COLUMNS`（20列）は **4 スタンプのみ**を含む（`odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`・`prediction_created_at` はスタンプ別物）。**`backtest_strategy_version` は PREDICTION_CSV_COLUMNS に非存在**（予測テーブルに非存在のため・REVIEW MEDIUM-1 解決で意図的に除外）。
  - 5 スタンプ契約は別定数 **`REPRODUCIBILITY_STAMPS`**（`src/ui/csv_columns.py:106-112`・UI 行表示用・`backtest_strategy_version` 含む）。
  - `tests/ui/test_csv_columns.py:65-77` の docstring が明記: 「UI 行表示用の5項目目 backtest_strategy_version は予測テーブルに非存在のため CSV 定数からは除外・UI 側で付与する」。
- **Impact:** 計画された adversarial テスト `test_reproducibility_stamp_missing_detected` が「PREDICTION_CSV_COLUMNS に 5 スタンプ全存在を assert」すると・正規の（4 スタンプのみの）実装に対して常に fail する（false negative）・または planner が不正な CSV schema 変更を誘発する。SC#1「既存実装と整合」に違反。
- **Fix:** 2 つに分離: (a) `PREDICTION_CSV_COLUMNS` に対する presence assert は **4 スタンプ**（`backtest_strategy_version` を除く）で検証、(b) `REPRODUCIBILITY_STAMPS`（5 項目・UI 用）に対する presence assert を別途検証。cross-reference の typo `all_stks` → `all_stamps` に修正。must_haves truths の「5スタンプ」表記を「4 スタンプ（PREDICTION_CSV_COLUMNS）+ 5 スタンプ（REPRODUCIBILITY_STAMPS・UI 用）」に訂正。

#### [F-02] [HIGH] — `run_backtest --synthetic --bt-filter BT-1 --check-reproduce --no-write-db` は現状実行すると非零 exit になる

- **Plan:** 08-02
- **Anchor:** `08-02-PLAN.md:118`（action step 3・`run_backtest.py --synthetic --bt-filter BT-1 --check-reproduce --no-write-db`）、`:133`（acceptance・「4 step が順次 subprocess.run で実行される」）
- **Claim:** `uv run python scripts/run_backtest.py --synthetic --bt-filter BT-1 --check-reproduce --no-write-db` が backtest bit-identical 再現性を検証し GREEN で終わる。
- **Reality:**
  - `scripts/run_backtest.py:1071-1093` の `--check-reproduce` 経路は最初に `feature_df = _prepare_feature_df(args, readonly_pool)`（L1073）を呼ぶ。
  - `--synthetic` の場合 `readonly_pool = None`（`scripts/run_backtest.py:1031`・`None if args.synthetic else make_pool(...)`）。
  - `_prepare_feature_df`（L1308-1317）は `readonly_pool is None` だと `load_feature_matrix()` の生戻り値（ラベル未結合）を返す（L1313-1314）。
  - `_assert_deterministic`（L1078・`src/model/orchestrator.py:758`）は内部で `train_and_predict` を呼び・`src/model/orchestrator.py:341` で `if "fukusho_hit_validated" not in feature_df.columns: raise ValueError(...)` → **非零 exit**。
  - run_backtest.py 自身の header docstring（L29/L35/L43-45）にも `--synthetic ... --check-reproduce` の使用例があり・Phase 5 時点で「動く想定」で書かれた潜在不具合。Phase 8 PLAN はこれを採用しているため PLAN 修正が必要。
  - 補足: L1093 通過後も `--check-reproduce` ブロックを抜けて通常 pipeline が継続し・`reports/05-backtest` を上書きしうる（L1287）。
- **Impact:** SC#3 smoke の step 3 が必ず非零 exit し・smoke 全体が `return 1`。SC#3「フルパイプライン固定 seed 再現」が証明できない。Phase 8 success_criteria #3（D-03）が達成不能。`reports/05-backtest` を smoke が破壊する二次リスク。
- **Fix:** 以下のいずれか: (a) smoke step 3 を「ラベル付き真の合成再現経路」に差替（`_build_synthetic_feature_df` がラベル列を含むように拡張する等の Phase 5 側修正は重いので避ける）、(b) `_assert_deterministic` の前で early return するよう smoke 側で `--check-reproduce` を単独で呼ばず別の既存 bit-identical 検証（例: `tests/ev/test_run_backtest_e2e.py` の合成 bit-identical pytest）に置換、(c) smoke step 3 を廃止し SC#3 は `run_train_predict --check-reproduce`（step 1・実データ必要だが 08-03 で live-DB 証明）+ pytest bit-identical 群（step 2/4）で構成。推奨は (b) または (c)・smoke の出力 report は tmp dir に隔離。

#### [F-03] [HIGH] — `run_train_predict --check-reproduce --no-write-db` は live-DB 必須（`--synthetic` flag 非存在）・08-02 は autonomous/user_setup 空に反する

- **Plan:** 08-02
- **Anchor:** `08-02-PLAN.md:21`（must_haves truths・「run_reproducibility_smoke.py は ... 既存 CLI ... を subprocess で束ねる薄い orchestrator」）、`:115`（action step 1・`run_train_predict.py --check-reproduce --no-write-db`）、`:125`（action・「合成データ（--synthetic / --no-write-db）をデフォルトとし live-DB 全量は避ける」）、frontmatter `autonomous: true` / `user_setup: []`
- **Claim:** `run_reproducibility_smoke.py` は合成データ・no-write デフォルトで live-DB/full-data を回避し・autonomous（user_setup なし）で実行できる。
- **Reality:**
  - `scripts/run_train_predict.py:107-163` の argparse に **`--synthetic` flag は存在しない**（snapshot/model/version/reproduce/no-write/as-of のみ）。
  - `scripts/run_train_predict.py:225` で `settings = Settings()`（`.env` の KEIBA_DATABASE_URL 必須・未設定で Settings validation error で crash）。
  - `scripts/run_train_predict.py:253` で `readonly_pool = make_pool(settings, role="readonly")`（live PostgreSQL 必須）。
  - `scripts/run_train_predict.py:257-261` の `--check-reproduce` 経路は `_prepare_feature_df(readonly_pool)`（L261・`load_labels(cur)` で live-DB SELECT）を呼ぶ。
  - つまり step 1 は live-DB 必須・08-02 frontmatter の `autonomous: true` / `user_setup: []` と矛盾（live-DB は user_setup: postgresql + KEIBA_DATABASE_URL が必要・08-03 と重複）。
- **Impact:** 08-02 を autonomous（DB なし）で実行すると step 1 が Settings/pool 構築で crash し SC#3 smoke が exit nonzero。08-02 と 08-03 の live-DB 責任分界が曖昧化（08-03 は明示的に `user_setup: postgresql`・08-02 は隠れて live-DB 必須）。SC#3 の再現性証明が「DB 不要の薄い orchestrator」という D-03 設計意図に反する。
- **Fix:** 以下のいずれか: (a) 08-02 frontmatter に `user_setup: [postgresql]` を追加し step 1 が live-DB 必須であることを明示（08-03 と live-DB 責任を共有）、(b) step 1 を live-DB 不要の bit-identical pytest（例: `tests/model/test_calibrator.py::test_reproduce_bit_identical` を拡張した train/predict bit-identical・`tests/model/test_trainer.py` の合成データ系）に差替、(c) step 1 を 08-03 に移動し 08-02 は DB 不要 pytest のみで SC#3 の「合成データ層」を担う（live-DB 再現は 08-03 が証明）。推奨は (c)・D-03「薄い orchestrator・keep it simple」と整合。

#### [F-04] [MEDIUM] — payout 「DataFrame end-to-end」指示が存在しない API を対象にする

- **Plan:** 08-01
- **Anchor:** `08-01-PLAN.md:155`（Task 2 behavior・「合成 label/payout で『正の馬の欠落』を注入し end-to-end で verdict='fail' を実証」）、`:159`（action・「さらに合成 label/payout DataFrame（conftest.py の _build_label_row / _build_payout_row で構築・payout 正の馬 umaban=7 を label から欠落させる注入）で end-to-end の fail を実証」）
- **Claim:** 合成 label/payout DataFrame を構築し・欠落を注入して `reconcile` が end-to-end で `verdict='fail'` を返すことを実証する。
- **Reality:**
  - `src/etl/label_reconcile.py` で `reconcile_against_payout`（L933 付近）は **psycopg cursor のみ**を受け取り SQL チェックを実行（DataFrame を受け取らない）。
  - `_check_payout_recall`（L261）も cursor-only。
  - PLAN は同じ action 内で正しい経路（mock cursor で不一致件数注入・`_check_payout_recall.passed is False`）も併記（L159 前半）しているが・後半の「DataFrame end-to-end」は実行不能な API を指示。
- **Impact:** executor が DataFrame 受けの reconciliation API を新規に発明する（スコープ外実装）か・「end-to-end 実証」を放置する（acceptance criterion 未達の外れ）。
- **Fix:** action L159 の「さらに合成 label/payout DataFrame ... で end-to-end の fail を実証」を削除、または「mock cursor を返す helper で `reconcile_against_payout(cur)["verdict"] == "fail"` を検証」に修正（cursor ベースの end-to-end に再定義）。behavior L155 も同様に cursor ベースに統一。

#### [F-05] [MEDIUM] — 監査レポート surface map が TEST-01 必須サーフェス「評価指標計算」を欠落

- **Plan:** 08-02
- **Anchor:** `08-02-PLAN.md:160`（action・SURFACE_ROWS の surface リスト）
- **Claim:** `SURFACE_ROWS` は SC#1 #1-#8 の 8 サーフェス + 補足カテゴリ（categorical_missing・ui_csv_readonly）で TEST-01 全サーフェスをカバーする。
- **Reality:**
  - `.planning/REQUIREMENTS.md:65` の TEST-01 は「複勝ラベル生成・払戻テーブル突合・出走取消/競走除外/競走中止の扱い・オッズ時点固定・仮想購入ルール・`feature_cutoff_datetime`・**評価指標計算**・`race_id`単位分割・クラス正規化・カテゴリ/欠損処理」を明示。
  - 「評価指標計算」サーフェスに該当する既存テストが存在: `tests/ev/test_metrics.py`（`compute_backtest_metrics`・recovery_rate/refund/max_drawdown・L46+）・`tests/model/test_evaluator.py`（`compute_metrics`・calibration_max_dev 等・L93+）。
  - PLAN の SURFACE_ROWS 8 サーフェス（fukusho_label/payout_reconcile/refund_handling/odds_snapshot/virtual_purchase/feature_cutoff/race_id_split/class_normalization）は「評価指標計算」を含まない。
- **Impact:** `reports/08-audit` が「TEST-01 全サーフェス対応」と主張しながら必須サーフェス 1 つを欠き・トレーサビリティマップが不完全（出荷ゲート証憠としての完全性を欠く）。
- **Fix:** `SURFACE_ROWS` に `evaluation_metrics` サーフェスを追加し `tests/ev/test_metrics.py` + `tests/model/test_evaluator.py`（+ `test_evaluator_gate.py`）を existing_tests にマップ。`AUDIT_SURFACE_COLUMNS` は現状 6 要素で追加不要（surface 名を行追加するのみ）。

### Strengths

- SC#1 の中核リークサーフェスのコード契約 anchor は正確: `src/features/rolling.py` の strict `<` PIT guard・`src/etl/label_reconcile.py::_check_payout_recall`・`src/utils/group_split.py::get_bt_race_ids`（`ValueError(match='race_id')`）は全て実在し PLAN 記述と整合。
- Known Limitations の数値（回収率 LightGBM 0.7022 / CatBoost 0.6808・calibration_max_dev LGB 0.2308 vs BL-1 0.0014）は `reports/06-evaluation.json` / `reports/04-eval.json` と完全一致。
- adversarial テストの false-pass 回避設計（5段階鋳型・guard monkeypatch 無効化で「注入で結果が変わる」ことを補助 assert で実証）は `test_no_target_encoding_leak` の先例に忠実で妥当。
- D-04 checkpoint（08-03）の検証コマンドと期待値（skipped == 0・passed 491+）は `KEIBA_SKIP_DB_TESTS` skipif 機構・実際の 491 テスト収集数と整合。

### Cross-Plan Consistency

- **08-02 ↔ 08-03 live-DB 責任の衝突（F-03）:** 08-02 は `autonomous: true` / `user_setup: []` だが step 1（`run_train_predict --check-reproduce`）が live-DB 必須。08-03 は明示的に `user_setup: [postgresql]`。08-02 の step 1 が live-DB 必須なら 08-02 自身も user_setup を持つべきで・08-03 の checkpoint と責任が重複・08-03 の「SC#3 smoke も GREEN」という acceptance（08-03 L117）が循環依存になる（08-03 は 08-02 の成果物に依存するが 08-02 の step 1 が live-DB で落ちると 08-03 で再実行しても同じく落ちる）。
- **08-01 ↔ 既存実装の契約乖離（F-01）:** 08-01 のみ `test_prediction_csv_has_all_stks` typo と 5 スタンプ主張。PATTERNS.md / RESEARCH.md は既に正しい `_stamps` 表記・PLAN 08-01 単独の陳腐化。

### Overall Risk

**Overall risk: HIGH.** 3 つの HIGH（F-01/F-02/F-03）はいずれも `/gsd-execute-phase` が必ず失敗する実行ブロック性の事実誤差。SC#2 adversarial テスト（F-01）と SC#3 reproducibility smoke（F-02/F-03）の両方の中核成果物が影響を受け・Phase 8 の success_criteria #2/#3 が達成不能。ただし全て PLAN.md のテキスト修正（既存 CLI の再選択・スタンプ数の訂正・surface 行追加）で解決可能であり・src/ 実装の変更は不要。Core Value（リーク防止・再現性）への直接的侵害はなく・PLAN の正確性の問題。

---

## Consensus Summary

Single-reviewer cycle（Codex cycle 1 + orchestrator 独立検証）。オーケストレータの独立パスは Codex と同一の評決（NOT CONVERGED・HIGH 3 / MEDIUM 2・追加指摘なし）を・同じソース行証拠で Codex 出力を読む前に到達した。両パスは一致。

### Agreed Actionable Items（planner が Cycle 2 で対応すべき修正）

| ID | Severity | Plan | Required PLAN.md Change |
|---|---|---|---|
| F-01 | HIGH | 08-01 | L25 must_haves / L184 read_first / L201 action の「5スタンプ + backtest_strategy_version」を「PREDICTION_CSV_COLUMNS は 4 スタンプ（backtest_strategy_version 除く）+ REPRODUCIBILITY_STAMPS は 5 スタンプ（UI 用）」に訂正。typo `all_stks` → `all_stamps`。テスト本体も 4 スタンプ assert と 5 スタンプ assert に分割。 |
| F-02 | HIGH | 08-02 | smoke step 3（`run_backtest --synthetic --bt-filter BT-1 --check-reproduce`）を差替: (b) 合成 bit-identical pytest に置換 or (c) step 廃止で SC#3 は step 1+2+4 で構成。smoke の report 出力は tmp dir 隔離。acceptance L133 も更新。 |
| F-03 | HIGH | 08-02 | step 1（`run_train_predict --check-reproduce`）の live-DB 必須を解消: (c) step 1 を 08-03 に移動し 08-02 は DB 不要 pytest のみ（frontmatter `autonomous: true` / `user_setup: []` を維持）。または (a) frontmatter に `user_setup: [postgresql]` 追加で live-DB 必須を明示。 |
| F-04 | MEDIUM | 08-01 | L155 behavior / L159 action の「DataFrame end-to-end 実証」を cursor ベースに再定義（mock cursor で `reconcile_against_payout(cur)["verdict"] == "fail"`）または当該句を削除。 |
| F-05 | MEDIUM | 08-02 | L160 SURFACE_ROWS に `evaluation_metrics` サーフェスを追加（existing_tests: `tests/ev/test_metrics.py` + `tests/model/test_evaluator.py`）。 |

### Cycle-over-Cycle Delta

| Dimension | Cycle 1 |
|---|---|
| HIGHs at contract level | 3（F-01/F-02/F-03）|
| Actionable MEDIUM/LOW unresolved | 2（F-04/F-05）|
| Convergence status | NOT CONVERGED |

### Divergent Views

Not applicable（single reviewer + orchestrator 独立検証・unanimous）。

---

## Verification Coverage

The source-grounding requirement is satisfied by artifact paths and line references throughout. 全指摘は concrete なソース行 anchor で検証:

- **F-01:** `tests/ui/test_csv_columns.py:65-77`（実テスト名 `test_prediction_csv_has_all_stamps`・docstring で 4 スタンプ明記・`backtest_strategy_version` は UI 側で付与と明記）・`src/ui/csv_columns.py:52-74`（PREDICTION_CSV_COLUMNS 20列・4 スタンプ・`backtest_strategy_version` 非存在）・`src/ui/csv_columns.py:106-112`（REPRODUCIBILITY_STAMPS 5 項目・UI 用・`backtest_strategy_version` 含む）。PLAN typo 箇所: `08-01-PLAN.md:184`（`all_stks`）・PATTERNS.md L16/186/223 と RESEARCH.md L319/554 は既に正しく `_stamps`。
- **F-02:** `scripts/run_backtest.py:1071`（`--check-reproduce` が `_prepare_feature_df` を先呼び）・`:1031`（`readonly_pool = None if args.synthetic`）・`:1308-1317`（`_prepare_feature_df` が `readonly_pool is None` で `load_feature_matrix()` 生戻り値・ラベル未結合）・`src/model/orchestrator.py:341`（`fukusho_hit_validated` 無しで `raise ValueError`）・`:758`（`_assert_deterministic` が `train_and_predict` を呼ぶ）。run_backtest.py header docstring L29/L35/L43-45（既存使用例・潜在不具合の先行記述）。
- **F-03:** `scripts/run_train_predict.py:107-163`（argparse に `--synthetic` 非存在・確認済 flag: snapshot/model/version/reproduce/no-write/as-of）・`:225`（`Settings()` で `.env` 必須）・`:253`（`make_pool(role="readonly")` で live-DB 必須）・`:257-261`（`--check-reproduce` が `_prepare_feature_df(readonly_pool)` で `load_labels(cur)` 呼び）。08-02 frontmatter `autonomous: true` / `user_setup: []`（L7/L17）。
- **F-04:** `src/etl/label_reconcile.py:107`（`reconcile_against_payout` が cursor 受け）・`:261`（`_check_payout_recall(cur: Cursor)`）・`src/etl/quality_gate.py:92`（`class CheckResult`・cursor ベース検査の戻り型）・`tests/test_label_reconcile.py:61`（`_mock_cursor` ヘルパー・cursor ベース検証の正経路）。
- **F-05:** `.planning/REQUIREMENTS.md:65`（TEST-01 が「評価指標計算」を明示）・`tests/ev/test_metrics.py:46`（`compute_backtest_metrics` の既存テスト）・`tests/model/test_evaluator.py:93`（`compute_metrics` の既存テスト）・`08-02-PLAN.md:160`（SURFACE_ROWS の 8 サーフェス・evaluation_metrics 欠落）。
- **Strengths 検証:** `reports/06-evaluation.json`（`recovery_rate: lightgbm 0.7021532541 / catboost 0.6807827217`）・`reports/04-eval.json`（`calibration_max_dev: lightgbm 0.2307692308 / bl1 0.001425964`）・`src/features/rolling.py`（strict `<` cutoff）・`tests/utils/test_group_split.py:233`（`ValueError(match="race_id")`）・`KEIBA_SKIP_DB_TESTS=1 uv run pytest --collect-only`（491 tests collected・08-03 L87「passed 491+」と整合）。

**Codebase claims were verified line-by-line by both Codex and the orchestrator**（Codex は `codex exec --sandbox read-only` で read-only アクセス・オーケストレータは直接 Read/grep で二重検証）。両パスは 5 指摘全てで一致・追加 HIGH/MEDIUM なし。
