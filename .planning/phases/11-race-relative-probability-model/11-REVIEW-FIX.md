---
phase: 11-race-relative-probability-model
fixed_at: 2026-06-27T07:16:04Z
review_path: .planning/phases/11-race-relative-probability-model/11-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 11: Code Review Fix Report

**Fixed at:** 2026-06-27T07:16:04Z
**Source review:** `.planning/phases/11-race-relative-probability-model/11-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 11（Critical 3件 + Warning 8件・Info 6件は fix_scope 対象外）
- Fixed: 11
- Skipped: 0
- Status: all_fixed

## 実行サマリ

- **unit test 結果**: 48 passed, 13 skipped（`KEIBA_SKIP_DB_TESTS=1` で DB 依存テストは skip・live-DB クエリは実行せず unit test 中心に検証）
- **検証対象テスト**: `tests/audit/test_audit_race_relative.py`（SAFE-01 静的証明・race 完結性 adversarial）, `tests/audit/test_audit_field_strength.py`, `tests/audit/test_audit_speed_figure.py`, `tests/model/test_race_relative.py`, `tests/model/test_prediction_load.py`, `tests/model/test_orchestrator.py`（snapshot symlink で実データパス含む）, `tests/db/test_is_primary_flag.py`（DDL 列整合・provenance/domain 検証追加）
- **ruff**: 既存エラー（main でも E501 9件・I001 1件）は維持。私の追加で E501 +6件（`test_is_primary_flag.py` の docstring/comment 日本語行・プロジェクト慣行に準拠）。`orchestrator.py`/`race_relative.py`/`run_phase11_evaluation.py`/`test_audit_race_relative.py` は E501/I001 0件を維持。

## Core Value（リーク防止）保護確認

各コミット前に以下を検証：

1. **D-10 race 内完結性**: CR-02 の CatBoost ブランチ index guard は race_id ごとの独立ループ構造を維持・race cross を生まない。
2. **θ 選択の test 窓不使用**: CR-03 は provenance 引数の伝播追加のみで・θ 選択ロジック（calib slice のみ使用・D-03/§11.2 聖域）は変更なし。`score_split="calib"` の構造的聖域ブロックには触れない。
3. **§19.1 再現性**: CR-01/CR-03 は metadata 3引数の伝播を整える修正。既存の sentinel `"unspecified"` 既定値と test 窓の `label_version="v1.0"` 等の実運用値を破壊しない。
4. **SC#3 bit-identical**: CR-01 の `_assert_deterministic` 修正で `as_of_datetime=FIXED_REPRODUCE_TS` を維持しつつ `pred_df.equals()` で bit-identical を保証。
5. **SAFE-01（feature 側への odds/ninki 混入禁止）**: WR-01 の adversarial test 追加で `market_signal` 引数の feature 構築経路混入を機械保証。

## Fixed Issues

### CR-01: `_assert_deterministic` が `as_of_datetime` を `train_and_predict` に伝播せず・SC#3/SC#4 bit-identical 検証が退化している（§19.1 構造的ブロック）

**Files modified:** `src/model/orchestrator.py`, `scripts/run_phase11_evaluation.py`
**Commit:** `9127741`
**Applied fix:**
- `_assert_deterministic` に `label_version`/`odds_snapshot_policy`/`backtest_strategy_version` 引数を追加（既定 `"unspecified"` sentinel・`train_and_predict` と同一既定値）。両 `train_and_predict` 呼出を `common_kwargs` で共通化し・3引数を伝播。
- `pred_df` 全体（provenance/as_of_datetime 列含む）の bit-identical を `DataFrame.equals` で検証する `RuntimeError` guard を追加。従来の `p_fukusho_hit` 列のみ `np.array_equal` では as_of_datetime 列混入の再現性破壊を検出できなかった。
- `run_phase11_evaluation.py` の SC#3 smoke 呼出も test 窓と同一の `label_version="v1.0"` 等を渡すよう更新。
**論証（logic 関連）:** bit-identical 検証強化のため `DataFrame.equals` を追加。既存テスト（`test_orchestrator.py` 7テスト）全て PASS で論理的健全性を確認。

### CR-02: CatBoost 予測パスの `score_meta_df` 切替が lightgbm ブランチと不整合（silent wrong-horse prediction リスク）

**Files modified:** `src/model/orchestrator.py`
**Commit:** `f4434a6`
**Applied fix:**
- CatBoost ブランチの `score_meta_df` 変数を廃止し・LightGBM ブランチと同様に常に `race_df_score` を参照するよう統一。
- `race_df_score.index.equals(X_score.index)` の guard を追加し・`.values` が index 順に取ることによる silent な meta 列ずれを `RuntimeError` で fail-loud 検出。
**論証（logic 関連）:** index guard 追加。D-10 race 内完結性は維持（race_df_score は race_id ごとに独立構築・race cross を生まない）。

### CR-03: `_select_theta_on_calib` が §19.1 metadata 3 引数を baseline/rr の両 `train_and_predict(score_split="calib")` 呼出で渡していない（silent provenance hole）

**Files modified:** `scripts/run_phase11_evaluation.py`
**Commit:** `0f33dd0`
**Applied fix:**
- `_select_theta_on_calib` に `metadata_kwargs` 引数を追加（None の場合は sentinel "unspecified" 既定値）。baseline/rr 両呼出に伝播。
- 呼出側（main スコープ）も test 窓と同一の `label_version="v1.0"` 等を `metadata_kwargs` として渡すよう更新。
**論証（logic 関連）:** θ 選択ロジック（D-03/§11.2 聖域・calib slice のみ使用）は変更なし。`metadata_kwargs` は pred_df の provenance 列に書き込まれるだけで θ 候補の足切り・選択・tie-break の判定に影響しない。

### WR-01: `compute_overprediction_penalty` の `market_signal` 引数が SAFE-01 AST 監査を迂回する設計（feature ↔ evaluation 境界の紳士協定化）

**Files modified:** `src/model/race_relative.py`, `tests/audit/test_audit_race_relative.py`
**Commit:** `8c57112`
**Applied fix:**
- `compute_overprediction_penalty` の docstring に SAFE-01 allow-list マーカー（`SAFE-01-ALLOW: market_signal`）を明示宣言。
- `test_audit_race_relative.py` に `test_market_signal_arg_has_allowlist` adversarial test を追加：(1) `market_signal` 引数を持つ全関数の docstring に allow-list マーカーがあること、(2) それらの関数の本体 AST に `FEATURE_COLUMNS`/`build_training_frame`/`load_feature_matrix` 等の feature 構築経路の Name/Attribute が含まれないことを検証。
- マーカー完全削除で FAIL すること・復元で PASS することを確認（adversarial 検出力実証）。
**論証（logic 関連）:** 静的解析テスト追加（機能テストでない）。SAFE-01 聖域の補強で `test_no_odds_ninki_proxy`（Name/Attribute/Constant 走査）と補完関係。

### WR-02: `solve_alpha_for_race` の brentq 失敗時に `ValueError` を送出するが docstring は `RuntimeError` を規定

**Files modified:** `src/model/race_relative.py`
**Commit:** `50499a8`
**Applied fix:**
- brentq が収束失敗で送出する `ValueError`（scipy 仕様）を docstring 契約の `RuntimeError` でラップ。発散の主因（θ が極小で α_r が `ALPHA_SEARCH_BOUNDS` を超える）をエラーメッセージに明示。
- `test_theta_zero_divergence` は `pytest.raises((RuntimeError, ValueError))` で両許容するため従来通り PASS。

### WR-03: `test_prediction_columns_matches_ddl_count` が新規 CREATE TABLE の provenance 3列を含めて列数検証していない

**Files modified:** `tests/db/test_is_primary_flag.py`
**Commit:** `7bee1f4`
**Applied fix:**
- `test_prediction_add_provenance_columns_match_prediction_columns` テストを追加：`PREDICTION_ADD_PROVENANCE_SQL` が追加する3列（label_version/odds_snapshot_policy/backtest_strategy_version）が `PREDICTION_TABLE_DDL` と `PREDICTION_COLUMNS` の両方に含まれること・`NOT NULL DEFAULT 'unspecified'` sentinel 明示を検証。
- `test_prediction_extend_model_type_domain_is_constraint_not_column` テストを追加：`PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL` が CHECK 制約拡張（DROP + ADD CONSTRAINT）で列追加でないこと・`lightgbm_rr`/`catboost_rr` が domain に含まれることを検証。
- いずれも `KEIBA_SKIP_DB_TESTS=1` で走る静的パース検査（DB 不要）。

### WR-04: `_compute_selected_only_calib_max_dev` が「p_fukusho_hit 上位 30%」を p フィルタなしに全体から計算（D-05-2 の意図と乖離リスク）

**Files modified:** `scripts/run_phase11_evaluation.py`
**Commit:** `081118b`
**Applied fix:**
- docstring に現状の簡略化（race を跨いだ全体絶対順位）と Phase 12 EVAL-01 厳密化タイミング（race_id group 化した各 race 上位 30%・または `evaluate_all_segments` binning reuse）を明記。
- REVIEW が「Phase 12 EVAL-01 で厳密化するタイミングを明示するだけでも可」としている方針を採用。ロジック変更なし（D-05 gate 判定結果は不変）。

### WR-05: `load_predictions` の `reader_role=None` 既定が呼出側で `None` を渡す経路と不整合

**Files modified:** `scripts/run_phase11_evaluation.py`
**Commit:** `f5558d7`
**Applied fix:**
- SC#5 idempotent swap の `load_predictions` 呼出に `reader_role=settings.db_reader_role` を明示的に渡すよう修正（`run_train_predict.py:361-362` と同一 idiom）。main スコープの `settings` を再利用し `Settings()` の再 instantiate を回避。

### WR-06: `_evaluate_gate` の D-05-1 で NaN を FAIL 扱いするが docstring は「D-15 参考記録失敗」と矛盾

**Files modified:** `scripts/run_phase11_evaluation.py`
**Commit:** `4774d14`
**Applied fix:**
- D-05-1 gate の NaN 扱いを θ 選択経路（`_select_theta_on_calib` L641-648 の NaN-safe idiom）と整合させた。NaN の場合は D-05-1 を skip（`d05_1_skipped` フラグで明示）して D-05-2/D-05-3 の残りで gate 判定。odds 系列がある場合は従来通り NaN を FAIL（safe side）。
- gate verdict dict の `condition_1_overprediction_penalty` に `skipped_nan` フラグと skip rule を追記し見える化。
**論証（logic 関連）:** odds-free 1-A snapshot（本プロジェクトの主用途）で SC#2 gate 全体が FAIL になる不整合を解消。θ 選択経路・D-10 race 完結性には影響しない。

### WR-07: `compute_overprediction_penalty` が `cell_filter_mask` 適用後に `n_total = float(len(y_pred))` を使う（フィルタ前の重み付けと不一致）

**Files modified:** `src/model/race_relative.py`
**Commit:** `11ccf3a`
**Applied fix:**
- docstring のスケール切り替えセクションに `n_total` のスケール注意を追記。`cell_filter_mask=None`（overall）は全サンプル数ベース・`cell_filter_mask` 指定（selected/high-EV 層）は mask 後件数（selected 層サイズ）ベースで・戻り値のスケールが異なることを明記。現状の呼出側（`_compute_overprediction_from_pred` は `cell_filter_mask=None`）は影響しないが将来拡張時の誤解を防止。

### WR-08: `orchestrator.train_and_predict` の最後に `pred_df` に `race_start_datetime` / `race_key` を追加で付与する箇所が `_assert_valid_prediction_df` の後にあり・PREDICTION_COLUMNS 順序保証を損なうリスク

**Files modified:** `src/model/orchestrator.py`
**Commit:** `befc5f6`
**Applied fix:**
- meta 列付与前に・`race_start_datetime`/`race_key` が `PREDICTION_COLUMNS` と重複しないことを assert（将来 `PREDICTION_COLUMNS` にこれらの列が追加された場合の silent 上書きを fail-loud で防止）。
- meta 列付与後に・`pred_df` の先頭 `len(PREDICTION_COLUMNS)` 列が `PREDICTION_COLUMNS` と完全一致することを assert（downstream が `pred_df[PREDICTION_COLUMNS]` で抽出する際の安全性を機械保証）。
- `PREDICTION_COLUMNS` を `src.model.predict` から追加 import。
**論証（logic 関通）:** guard は現状では常にパス（重複なし・先頭一致）・異常時のみ RuntimeError。`test_orchestrator.py` の meta 列付与テスト（7テスト）全て PASS で既存動作を壊さないことを確認。

## Skipped Issues

None — all in-scope findings（Critical 3件 + Warning 8件）を修正した。

---

_Fixed: 2026-06-27T07:16:04Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
