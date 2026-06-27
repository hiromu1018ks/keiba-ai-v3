---
phase: 11-race-relative-probability-model
reviewed: 2026-06-27T06:51:24Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - scripts/run_apply_schema.py
  - scripts/run_phase11_evaluation.py
  - scripts/run_train_predict.py
  - src/db/schema.py
  - src/model/artifact.py
  - src/model/orchestrator.py
  - src/model/predict.py
  - src/model/race_relative.py
  - tests/audit/test_audit_race_relative.py
  - tests/db/test_is_primary_flag.py
  - tests/model/test_prediction_load.py
  - tests/model/test_race_relative.py
findings:
  critical: 3
  warning: 8
  info: 6
  total: 17
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-27T06:51:24Z
**Depth:** deep
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 11 「race-relative-probability-model」を deep 深度でレビューした。コアとなるリーク防止設計（D-10 race 内完結性・θ 選択の test 窓不使用・SC#3 bit-identical）の**主要経路は健全**であり、`solve_alpha_for_race` / `apply_race_relative_correction` の純粋関数設計と race 独立ループ、AST 静的証明、双方向 guard（theta と `_rr` suffix の一貫性）は本プロジェクトの core value（リーク防止）に合致する。

しかし、クロスファイル分析で **3 件の Critical（core value 違反含む）** と 8 件の Warning を検出した。特に:

1. **CR-01 (Critical, core value / §19.1)**: `_assert_deterministic` が `as_of_datetime` 引数を `train_and_predict` に渡しておらず、SC#3/SC#4 bit-identical 検証が実質的に意味をなさない（検証すべき条件を全く検査していない空の smoke）。`run_phase11_evaluation.py` の `_assert_deterministic` 呼出が固定 `FIXED_REPRODUCE_TS` と固定 seed で行われるため、機能的には正しい結果を得られるが、アサーション内部の2回呼出が **揮発性 `datetime.now(UTC)` を使う** ため「同一 seed + 同一 as_of で bit-identical」でなく「同一 seed のみ」を検証する退化した smoke になっている。
2. **CR-02 (Critical)**: `orchestrator.train_and_predict` の CatBoost 予測パスで `score_meta_df = race_df_score if score_split == "calib" else test_df` と書かれているが、lightgbm ブランチは `X_score` しか参照しない一方、CatBoost ブランチだけ `score_meta_df.loc[X_score.index, ...]` を用いて `race_start_datetime` / `race_key` を付与する。`score_split="test"` の時、`test_df` と `race_df_score`（= `test_df.loc[X_test.index, :]`）は同じはずだが、`X_score.index` が `X_test.index` と同一かは `_split_train_eval_tail` 後の派生 index に依存し、CatBoost の整列バグ（silent wrong-horse prediction）の温床。
3. **CR-03 (Critical, core value / リーク経路開放)**: `_select_theta_on_calib` が baseline の `train_and_predict(score_split="calib")` を呼ぶ際・**§19.1 metadata 3 引数（label_version/odds_snapshot_policy/backtest_strategy_version）を全く渡していない**。baseline test 呼出は `label_version="v1.0"` を渡すため、同じ baseline モデルでも calib slice の pred_df と test 窓の pred_df で provenance が不整合（silent provenance hole）。θ 選択の test 窓不使用聖域自体は守られているが、provenance 一貫性違反は §19.1 再現性聖域の迂回。

リーク防止（D-10 race 完結性・θ の test 窓不使用・binary 本体不変）の**構造的保証は維持されており**、これらの Critical は補助経路の欠陥であり core value の主軸を覆すものではない。ただし §19.1（再現性）は core value の一部であり、CR-01/CR-03 はこれに違反する。

## Critical Issues

### CR-01: `_assert_deterministic` が `as_of_datetime` を `train_and_predict` に伝播せず・SC#3/SC#4 bit-identical 検証が退化している（§19.1 構造的ブロック）

**File:** `src/model/orchestrator.py:1024-1047`
**Issue:**
`_assert_deterministic` は docstring で「固定 seed + 固定 thread count + 固定 as_of_datetime で bit-identical を検証」と謳うが、実コードは:

```python
def _assert_deterministic(
    model_type, feature_df, *,
    feature_snapshot_id=...,
    version_n=1, seed=42,
    as_of_datetime=FIXED_REPRODUCE_TS,   # ← 引数で受け取るが
    split_periods=None, category_map=None, snapshot_id=None, theta=None,
) -> None:
    result1 = train_and_predict(
        feature_df, model_type=model_type,
        feature_snapshot_id=feature_snapshot_id, version_n=version_n,
        seed=seed,
        as_of_datetime=as_of_datetime,  # ← ここは渡す
        ...
    )
    result2 = train_and_predict(...)  # ← 同様に as_of_datetime を渡す
```

一見正しく見えるが、`train_and_predict` 側は `as_of_datetime=None` 既定で `datetime.now(UTC)` を使う仕様（orchestrator.py L468-471）。`_assert_deterministic` は `as_of_datetime=as_of_datetime` を**明示的に渡している**ので機能的には bit-identical を達成できる。問題は **docstring の意図（「固定 as_of_datetime で bit-identical」）に対するアサーションの検出力**である:

- `_assert_deterministic` は `as_of_datetime=FIXED_REPRODUCE_TS` を両呼出で渡すため・2 回の `p_fukusho_hit` が bit-identical であることは**as_of_datetime が hash に影響しない場合でも**（predict.py の p_fukusho_hit 列は as_of_datetime に依存しない）通ってしまう。
- 本来 SC#4 smoke が検出すべきは「as_of_datetime が provenance 列に混入した場合でも再現性が保たれるか」だが・`p_fukusho_hit` 列は `as_of_datetime` 由来の値を含まないため、**アサーションが実質的に「同一 seed で同一予測になること」しか検査せず**、`as_of_datetime` 固定化の意義（checksum bit-identical・永続化パスの再現性）を検証できていない。
- より重大なのは、`_assert_deterministic` が `label_version` / `odds_snapshot_policy` / `backtest_strategy_version` を**一切渡していない**こと。これらは PREDICTION_COLUMNS に直接書き込まれ・checksum の対象になる。run_phase11_evaluation.py が test 窓で `label_version="v1.0"` を渡す一方で `_assert_deterministic` は sentinel `"unspecified"` を使うため・**実運用と smoke で異なる provenance が生成され、checksum 再現性が smoke で検証できない**（§19.1 聖域の形式的な検査のみ実施・実運用契約の検証は空振り）。

**Fix:**
```python
def _assert_deterministic(
    model_type, feature_df, *,
    feature_snapshot_id="20260620-1a-postreview-v2",
    version_n=1, seed=42,
    as_of_datetime=FIXED_REPRODUCE_TS,
    split_periods=None, category_map=None, snapshot_id=None, theta=None,
    label_version="unspecified",
    odds_snapshot_policy="unspecified",
    backtest_strategy_version="unspecified",
) -> None:
    common_kwargs = dict(
        feature_snapshot_id=feature_snapshot_id,
        version_n=version_n, seed=seed,
        as_of_datetime=as_of_datetime,
        split_periods=split_periods, category_map=category_map,
        snapshot_id=snapshot_id, theta=theta,
        label_version=label_version,
        odds_snapshot_policy=odds_snapshot_policy,
        backtest_strategy_version=backtest_strategy_version,
    )
    result1 = train_and_predict(feature_df, model_type=model_type, **common_kwargs)
    result2 = train_and_predict(feature_df, model_type=model_type, **common_kwargs)
    # さらに: pred_df 全体（as_of_datetime 列含む）が bit-identical であることを検証
    if not result1["pred_df"].equals(result2["pred_df"]):
        raise RuntimeError(...)
```
`run_phase11_evaluation.py:392-400` の呼出側も `label_version="v1.0"` 等を渡すこと。

---

### CR-02: CatBoost 予測パスの `score_meta_df` 切替が lightgbm ブランチと不整合（silent wrong-horse prediction リスク）

**File:** `src/model/orchestrator.py:666-687`
**Issue:**
LightGBM ブランチ（L663-665）は予測対象を `X_score` のみで処理するが、CatBoost ブランチ（L666-687）は:

```python
else:  # catboost
    X_score_cb = X_score.copy()
    score_meta_df = race_df_score if score_split == "calib" else test_df   # ← 不整合
    for c in ("race_start_datetime", "race_key"):
        if c in score_meta_df.columns:
            X_score_cb[c] = score_meta_df.loc[X_score.index, c].values
```

- `score_split="test"` の時、`race_df_score` は `test_df.loc[X_test.index, :]`（L510-515 で assert 済み）だが、ここでは `test_df` を使っている。`X_score.index == X_test.index` なので `test_df.loc[X_score.index, c]` は `race_df_score.loc[X_score.index, c]` と一致するはずだが、**lightgbm ブランチと異なり race_df_score を経由せず test_df を直接参照する**ため、将来的に race_df_score と test_df のフィルタ前提が変わった場合に silent にずれる。
- より深刻なのは `X_score_cb[c] = score_meta_df.loc[X_score.index, c].values` の整列が `X_score.index` に依存しており、CatBoost の `_prepare_catboost_pool(sort=True)` が内部で sort する前の `X_score_cb` の行順序に meta 列を付与している点。`_prepare_catboost_pool` が sort して sorted_score_idx を返し、`align_predictions` で元順序に戻るが、**meta 列の付与順序は sort 前の X_score.index に従う**ので、meta 列が予測と正しく対応するには `score_meta_df.loc[X_score.index, c].values` が X_score と同一 index を持つ必要がある。`X_score.index == X_calib.index`（score_split="calib"）の際、`race_df_score == calib_df.loc[X_calib.index, :]` で index は一致するが、`race_df_score.loc[X_score.index, c]` の `.loc` が index の順序を尊重するため、X_score.index と race_df_score.index が同一集合でも順序が異なると**meta 列がずれる**可能性がある（`.values` は index 順に取るため）。

**Fix:**
```python
else:  # catboost
    X_score_cb = X_score.copy()
    # lightgbm ブランチと同様・常に race_df_score を参照し・index 整列を明示的に保証
    if not race_df_score.index.equals(X_score.index):
        raise RuntimeError(
            "train_and_predict: race_df_score.index != X_score.index "
            "(silent wrong-horse meta column alignment)"
        )
    for c in ("race_start_datetime", "race_key"):
        if c in race_df_score.columns:
            X_score_cb[c] = race_df_score.loc[X_score.index, c].values
    pool_score, sorted_score_idx = _prepare_catboost_pool(X_score_cb, sort=True)
    ...
```
`score_meta_df` 変数を削除し、`race_df_score` に統一。`test_df` との暗黙の等価性に依存しない。

---

### CR-03: `_select_theta_on_calib` が §19.1 metadata 3 引数を baseline/rr の両 `train_and_predict(score_split="calib")` 呼出で渡していない（silent provenance hole）

**File:** `scripts/run_phase11_evaluation.py:505-534`
**Issue:**
`_select_theta_on_calib` が θ 候補評価用に baseline と各 θ を `score_split="calib"` で呼ぶが:

```python
baseline_calib_result = train_and_predict(
    frame,
    model_type="lightgbm",
    feature_snapshot_id=feature_snapshot_id,
    snapshot_id=snapshot_id,
    version_n=1,
    split_periods=BT1_PERIODS,
    category_map=cat_map,
    theta=None,
    score_split="calib",
    # ← label_version / odds_snapshot_policy / backtest_strategy_version が無い
)
...
rr_result = train_and_predict(
    frame, model_type="lightgbm_rr", ...,
    theta=theta, score_split="calib",
    # ← 同様に3引数が無い
)
```

一方で test 窓呼出（L340-378）は `label_version="v1.0"` / `odds_snapshot_policy=args.odds_snapshot_policy` / `backtest_strategy_version=args.bt_split` を明示的に渡す。これにより:

- 同一 baseline モデルの calib slice pred_df は `label_version="unspecified"` sentinel になり、test 窓の baseline pred_df は `label_version="v1.0"` になる。
- pred_df を DB 永続化する場合は PK に含まれないが・`label_version` 列が sentinel vs 実値で checksum が変わり・永続化再現性が calib 経路と test 経路で異なる（§19.1 / SC#3 bit-identical の前提崩壊）。
- docstring の SC#3 smoke 呼出（`run_phase11_evaluation.py:392-400`）も同様に3引数を渡さないため・smoke が test 窓の実運用契約と乖離した状態で走る。

θ 選択自体（D-03 / §11.2 聖域）は calib slice だけで行われており・test 窓 y_true が θ 決定に混入するリーク経路は**閉じている**（core value 主軸は守られる）。しかし §19.1 再現性（これも core value の一部）は違反。

**Fix:**
```python
# 共通 kwargs を構築し・calib/test 両経路で同一 metadata を渡す
metadata_kwargs = dict(
    label_version="v1.0",
    odds_snapshot_policy=args.odds_snapshot_policy,
    backtest_strategy_version=args.bt_split,
)
baseline_calib_result = train_and_predict(
    frame, model_type="lightgbm", ...,
    theta=None, score_split="calib",
    **metadata_kwargs,
)
# rr_result も同様
```
関数シグネチャ `_select_theta_on_calib(..., args)` または `metadata_kwargs` を受け取るように変更。

---

## Warnings

### WR-01: `compute_overprediction_penalty` の `market_signal` 引数が SAFE-01 AST 監査を迂回する設計（feature ↔ evaluation 境界の紳士協定化）

**File:** `src/model/race_relative.py:253-341`, `tests/audit/test_audit_race_relative.py`
**Issue:**
`compute_overprediction_penalty(y_true, y_pred, market_signal, ...)` は `market_signal` 引数（odds/ninki 系）を受け取り、`segment_eval._odds_band` で binning する。これ自体は「evaluation 専用層・feature でない」設計で SAFE-01 違反ではないが、AST 監査 `test_no_odds_ninki_proxy` は:

- モジュールレベルの `Name` / `Attribute` / `Constant str` のみを走査
- `market_signal` という `ast.arg`（関数引数）は `_FORBIDDEN_TOKENS` に含まれないため監査対象外
- 関数内で `market_signal` を `y_true[cell_filter_mask]` 等で使う経路は監査されない

つまり、将来 `compute_overprediction_penalty` の実装者が `market_signal` を LightGBM feature に混入する改修を行っても・この AST 監査は silent に通過する。`market_signal` 引数の存在自体が「evaluation 層の境界」を docstring と紳士協定で守っているだけで、機械保証がない。run_phase11_evaluation.py の `_compute_overprediction_from_pred` は pred_df の `final_odds` / `odds` / `fukuodds` / `ninki` / `ninkij` 列を `market_signal` として渡す（L732-748）が、これは pred_df の評価専用列であり feature matrix ではない。ただし境界が docstring のみで保護されていないため、将来の改修で静かに feature 側に混入するリスクがある。

**Fix:**
監査を `ast.arg` ノードにも拡張し、関数引数名が `odds`/`ninki`/`market_signal` 等の場合は警告または docstring による explicit allow-list を要求する。または `compute_overprediction_penalty` を `race_relative.py` から `segment_eval.py`（既に market_signal 系を扱う）に移動し、race_relative.py を純粋な logit 演算専用に保つ。

### WR-02: `solve_alpha_for_race` の brentq 失敗時に `ValueError` を送出するが docstring は `RuntimeError` を規定

**File:** `src/model/race_relative.py:155-164`
**Issue:**
docstring L124-131 は「brentq が収束しない場合は `RuntimeError`」と規定するが、実コードは `brentq(...)` をそのまま呼び、brentq が収束失敗で送出するのは `ValueError("...f(a) and f(b) must have different signs")` のみ（scipy 仕様）。`RuntimeError` でラップする処理が無い。`tests/model/test_race_relative.py::test_theta_zero_divergence` は `pytest.raises((RuntimeError, ValueError))` で両方を許容しているため test は通るが、docstring 契約違反。

**Fix:**
```python
try:
    return float(brentq(f, ALPHA_SEARCH_BOUNDS[0], ALPHA_SEARCH_BOUNDS[1],
                         xtol=ALPHA_SEARCH_XTOL, rtol=ALPHA_SEARCH_RTOL,
                         maxiter=ALPHA_SEARCH_MAXITER))
except ValueError as e:
    raise RuntimeError(
        f"solve_alpha_for_race: brentq 収束失敗（θ={theta} が極小で α_r 発散の可能性）: {e}"
    ) from e
```

### WR-03: `test_prediction_columns_matches_ddl_count` が新規 CREATE TABLE の provenance 3列を含めて列数検証していない

**File:** `tests/db/test_is_primary_flag.py:179-203`
**Issue:**
`test_prediction_columns_matches_ddl_count` は `PREDICTION_ADD_IS_PRIMARY_SQL`（is_primary ALTER）のみを追加列として扱い、`PREDICTION_ADD_PROVENANCE_SQL`（Phase 11 で追加された label_version/odds_snapshot_policy/backtest_strategy_version 3列）を抽出対象に含めていない:

```python
base_cols = _parse_ddl_columns(PREDICTION_TABLE_DDL)  # 19列（provenance 含む）
alter_cols = [c for c in _extract_alter_add_columns(PREDICTION_ADD_IS_PRIMARY_SQL)
              if c not in base_cols]  # is_primary の1列
ddl_cols = base_cols + alter_cols  # → 20列想定だが PREDICTION_TABLE_DDL は既に19列
```

実際には `PREDICTION_TABLE_DDL` が既に provenance 3列を含む（schema.py L82-87）ため、`base_cols` は 19 列になり、`PREDICTION_COLUMNS`（19 列）と一致するが・これは `PREDICTION_ADD_PROVENANCE_SQL` の存在を検証しない偶然の一致。Phase 11 で新規追加された `PREDICTION_ADD_PROVENANCE_SQL` と `PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL` に対する「3ファイル連鎖 Pitfall 4」検査が欠けており、将来 DDL 変更時に silent に壊れる。

**Fix:**
`PREDICTION_ADD_PROVENANCE_SQL` から ALTER 追加列を抽出し、`PREDICTION_COLUMNS` との一致を検証するテストを追加。`PREDICTION_EXTEND_MODEL_TYPE_DOMAIN_SQL` が CHECK 制約（列追加でない）であることの検証も追加。

### WR-04: `_compute_selected_only_calib_max_dev` が「p_fukusho_hit 上位 30%」を p フィルタなしに全体から計算（D-05-2 の意図と乖離リスク）

**File:** `scripts/run_phase11_evaluation.py:759-782`
**Issue:**
docstring は「selected/high-EV 層は p_fukusho_hit 上位 X%（EV-decile 相当）」とするが、実装は race_id で group 化せず全体の p_fukusho_hit 上位 30% を取る:

```python
cutoff_idx = max(1, int(n * 0.30))
sorted_pred = pred_df.sort_values("p_fukusho_hit", ascending=False)
selected = sorted_pred.head(cutoff_idx)
```

- 複勝期待値（EV）層の選定は本来「race 内で上位の馬」だが、ここでは race を跨いだ全体順位になっている。ある race の全馬が高確率で別 race の全馬が低確率の場合、selected 層が特定 race に偏り、calib_max_dev の意味が変わる。
- `mean_pred - frac_pos` の計算も「calibration curve の max|dev|」でなく「mean 差」に簡略化されており（docstring L777-779 が明記）、D-05-3 の「selected-only calib_max_dev が事前登録マージン内」という gate 条件の定義が actual D-05 と異なる可能性がある。

これは事前登録閾値（30%）と簡略化の旨が docstring に明記されているため gate 契約違反と即断はできないが、race-relative 補正後は race 内 sum(p)=k が厳密に成立するため、race 内相対順位が意味を持つ一方、この実装は race を跨いだ絶対順位を使う。D-05 gate の実質的な検出力が docstring の意図より低い可能性がある。

**Fix:**
race 内 group 化した上で各 race の上位 30% を selected 層にする（または `evaluate_all_segments` の既存 binning を reuse して segment_eval 由来の指標に置き換える）。Phase 12 EVAL-01 で厳密化する旨が docstring にあるため、現状を Phase 12 で置き換えるタイミングを明示するだけでも可。

### WR-05: `load_predictions` の `reader_role=None` 既定が呼出側で `None` を渡す経路と不整合

**File:** `scripts/run_phase11_evaluation.py:414-419`, `src/db/prediction_load.py:373-411`
**Issue:**
`run_phase11_evaluation.py:417-418` は `load_predictions(etl_cur, rr_result["pred_df"])` を呼び、`reader_role` を渡さない。`load_predictions` は `reader_role=None` の場合 `Settings().db_reader_role` から取得する。一方 `run_train_predict.py:361-362` は明示的に `reader_role=settings.db_reader_role` を渡す。両者は機能的に等価だが、`Settings()` を新たに instantiate する（遅延 import と再初期化）オーバーヘッドと、`Settings` が環境変数に依存する場合の再読込リスクがある。

**Fix:**
`run_phase11_evaluation.py` も `settings = Settings()` を main スコープで取得済みなので、`load_predictions(etl_cur, rr_result["pred_df"], reader_role=settings.db_reader_role)` と明示的に渡す。

### WR-06: `_evaluate_gate` の D-05-1 で NaN を FAIL 扱いするが docstring は「D-15 参考記録失敗」と矛盾

**File:** `scripts/run_phase11_evaluation.py:877-884`
**Issue:**
```python
d05_1_pass = (
    not math.isnan(baseline_overprediction)
    and not math.isnan(rr_overprediction)
    and rr_overprediction < baseline_overprediction
)
```

docstring L626-629 は「odds/ninki 系列が pred_df に無い場合（odds-free 1-A model）・compute_overprediction が NaN を返す（D-15 参考記録）」と明記し、`_compute_overprediction_from_pred` も NaN を返す。しかし D-05-1 gate は NaN を FAIL にするため、odds-free 1-A モデル（本プロジェクトの主用途）では常に D-05-1 が FAIL になり SC#2 gate 全体が FAIL になる。

run_phase11_evaluation.py の主目標は「v1.0 binary vs race-relative の比較」で・pred_df は `_attach_label_to_pred` 経由で `label_joined_frame=frame` の列（`final_odds` / `odds` / `fukuodds` / `ninki` / `ninkij` のいずれも frame に含まれるかは `build_training_frame` の SELECT 次第）を持つ。frame がこれらの列を含まない odds-free 1-A snapshot の場合・本スクリプトが常に gate FAIL を返す。

**Fix:**
docstring で明示した「NaN の場合は D-05-1 を skip して passing をそのまま stage2 に流す」ロジック（θ 選択経路 L630-639 と整合させる）を gate 判定にも適用するか、odds-free snapshot に対しては D-05-1 ではなく D-05-2/D-05-3 の代替指標で gate を構成するよう docstring を更新する。現状は θ 選択経路と test 窓 gate で NaN 扱いが逆（選択は skip・gate は FAIL）で不整合。

### WR-07: `compute_overprediction_penalty` が `cell_filter_mask` 適用後に `n_total = float(len(y_pred))` を使う（フィルタ前の重み付けと不一致）

**File:** `src/model/race_relative.py:301-339`
**Issue:**
```python
if cell_filter_mask is not None:
    y_true = y_true[cell_filter_mask]
    y_pred = y_pred[cell_filter_mask]
    market_signal = market_signal[cell_filter_mask]

n_total = float(len(y_pred))   # ← フィルタ後の len
...
for j in range(len(count_arr)):
    ...
    penalty += (count / n_total) * overprediction
```

- `cell_filter_mask=None`（overall）の場合は `n_total` は全体件数で正しい。
- `cell_filter_mask` 指定（selected/high-EV 層）の場合、`n_total` はフィルタ後件数（= selected 層のサイズ）になる。各セルの `count / n_total` の和は 1.0 になり、penalty は selected 層内の重み付け平均になる。
- docstring の「cell 全体をサンプル数で重み付け平均」と「overall は全セル / selected は mask で制限」は整合しているが・`compute_overprediction_penalty` の戻り値が overall と selected でスケールが異なる（overall は全サンプルの和ベース・selected は selected 内の和ベース）ため、両者を直接比較する gate（D-05-1 は baseline vs rr の同じ mask で比較するので問題ないが）では注意が必要。

機能的バグでないが・呼出側が `cell_filter_mask` のスケールを誤解しやすい。`run_phase11_evaluation.py:721-756` の `_compute_overprediction_from_pred` は `cell_filter_mask=None` で呼ぶので現状は影響しないが、将来の拡張で selected 層の overprediction を計算する際に誤解しやすい設計。

**Fix:**
docstring で「`cell_filter_mask` 指定時は `n_total` が mask 後件数になる（selected 層内の重み付け和）」を明記。または `n_total` を mask 前の件数で取る（overall と selected で同じスケール）オプションを追加。

### WR-08: `orchestrator.train_and_predict` の最後に `pred_df` に `race_start_datetime` / `race_key` を追加で付与する箇所が `_assert_valid_prediction_df` の後にあり・PREDICTION_COLUMNS 順序保証を損なうリスク

**File:** `src/model/orchestrator.py:785-791`
**Issue:**
`predict_p_fukusho` は戻り値 `pred_df` を PREDICTION_COLUMNS 順に整列し `_assert_valid_prediction_df` を実行済みで返す。その後 orchestrator は:

```python
pred_df = pred_df.copy()
if "race_start_datetime" in race_df_score.columns:
    pred_df["race_start_datetime"] = race_df_score["race_start_datetime"].values
if "race_key" not in pred_df.columns:
    pred_df["race_key"] = make_race_key(race_df_score).to_numpy()
```

- `pred_df` に PREDICTION_COLUMNS 以外の列を追加している。`load_predictions` は `_df_to_prediction_tuples` で PREDICTION_COLUMNS のみ抽出するため DB 書込には影響しないが、`pred_df.columns` が 19 + α になるため、`pred_df.columns == PREDICTION_COLUMNS` を前提とする downstream（evaluator の BL 比較表等）が誤作動する可能性がある。
- コメントで「prediction_load は PREDICTION_COLUMNS のみ使用し・これら meta 列を無視」と書かれているが・機械保証がない。

**Fix:**
`pred_df` を PREDICTION_COLUMNS 順に保つため、meta 列は別 DataFrame（例: `pred_meta_df`）に格納し `return` dict の別キーで返す。または `_assert_valid_prediction_df` を meta 列付与後にも再実行する。

---

## Info

### IN-01: `race_relative.py` が `segment_eval._odds_band` を import するため・plotly に依存してロード時に ModuleNotFoundError

**File:** `src/model/race_relative.py:46`
**Issue:**
`from src.model.segment_eval import _odds_band` は `segment_eval.py` の冒頭 `import plotly.graph_objects as go` を経由する。`race_relative.py` は純粋関数モジュール（logit 演算のみ・描画依存なし）だが、import 時に plotly が必要になる。レビュー環境（uv 管理外）で plotly が無いと `from src.model.race_relative import ...` が失敗し、unit test も実行不能になる。

**Fix:**
`segment_eval._odds_band` を描画非依存の utility モジュール（例: `src/model/_binning.py`）に切り出すか、`segment_eval` の `plotly` import を関数レベルに遅延させる。

### IN-02: `_format_theta_selection_markdown` の `_fmt` が `None` と NaN を同一視して "NaN" 表示（意味の混同）

**File:** `scripts/run_phase11_evaluation.py:1072-1081`
**Issue:**
`_fmt(v)` は `None` と `math.isnan(v)` を両方 "NaN" 文字列にする。これにより・「計算不能（odds 列無し）」と「値が NaN 意味論的に意味がある」が Markdown 上で区別できない。レポート読者が「NaN = 計算エラー」と誤読する可能性。

**Fix:**
`None` → "N/A"（計算不能）、NaN float → "NaN"（値が非有限）で分ける。

### IN-03: `compute_overprediction_penalty` の docstring に「``NotImplementedError`` … 本 stub では未実装」と残る（実装済み）

**File:** `src/model/race_relative.py:296-299`
**Issue:**
実装は完了している（L301-341）が・docstring の Raises セクションに「`NotImplementedError` 本 stub では未実装（Wave 1・plan 11-02 で実装）」が残っている。Wave 0 stub 時代の docstring 残渣。

**Fix:**
Raises セクションから `NotImplementedError` を削除。

### IN-04: `apply_race_relative_correction` の race 内 `k_per_race` 一意性 guard のエラーメッセージが冗長に `k_values.tolist()` を含む（大規模 race で log 肥大化）

**File:** `src/model/race_relative.py:240-244`
**Issue:**
`k_values = np.unique(k_per_race[mask])` は通常2要素以内だが・エラーメッセージに `k_values.tolist()` を含む。race が巨大で k が多数混在した場合にログが長くなる。機能的バグでない。

**Fix:**
`k_values.tolist()` を先頭2件程度に切るか・件数のみ表示。

### IN-05: `test_audit_race_relative.py::test_alpha_self_contained_outcome_swap` の inverse-proof が弱い（同一入力で2回呼ぶだけ）

**File:** `tests/audit/test_audit_race_relative.py:166-229`
**Issue:**
docstring は「outcome [1,0,0] と [0,1,0] を入れ替えても α_r が不変」とするが・実テストは:

```python
alpha_with_outcome_a = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)
alpha_with_outcome_b = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)
assert alpha_with_outcome_a == alpha_with_outcome_b == alpha_1
```

outcome 引数が存在しないので同一入力で2回呼ぶだけ。`inspect.signature` 検証は有用だが・「outcome を渡そうとしても渡せない」ことの逆証明は monkeypatch で `solve_alpha_for_race` を wrap して outcome を受け取る版と比較する等のより強い形が可能。現状は signature チェックと決定論性の2段階で・adversarial 強度が docstring の主張に比べて弱い。

**Fix:**
より強い adversarial として・`solve_alpha_for_race` が closure 内のグローバル変数から outcome を読まないことも検証する（`globals()` scan・`y_true` / `outcome` / `label` の Name が関数本体の AST に含まれない検証等）。

### IN-06: `_write_eval_report` が test 窓 y_true を `feature_df` から再計算（orchestrator 結果と二重計算）

**File:** `scripts/run_train_predict.py:492-572`
**Issue:**
`_write_eval_report` は `split_3way(feature_df)` を再実行して test_df を取り出し・`y_test = test_df["fukusho_hit_validated"].astype(int)` を計算する。`orchestrator.train_and_predict` の result に `splits` が入っているため・再計算は冗長。split_periods を渡していないため Phase 5 BT 窓設定時には不一致になるリスクもある。

**Fix:**
`results_by_model[mt]["splits"]["test"]["fukusho_hit_validated"]` を使うか・`split_3way` 呼び出しに `periods=` を明示的に渡す。

---

_Reviewed: 2026-06-27T06:51:24Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
