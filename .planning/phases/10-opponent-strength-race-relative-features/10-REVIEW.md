---
phase: 10-opponent-strength-race-relative-features
reviewed: 2026-06-27T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - scripts/run_phase10_evaluation.py
  - src/config/feature_availability.yaml
  - src/features/availability.py
  - src/features/builder.py
  - src/features/field_strength.py
  - src/features/race_relative.py
  - src/features/rolling.py
  - src/features/snapshot.py
  - tests/audit/test_audit_field_strength.py
  - tests/audit/test_audit_speed_figure.py
  - tests/features/test_builder.py
  - tests/features/test_builder_phase10_integration.py
  - tests/features/test_field_strength.py
  - tests/features/test_race_relative.py
  - tests/features/test_rolling.py
  - tests/features/test_snapshot_repro.py
  - tests/model/test_data.py
findings:
  critical: 4
  warning: 6
  info: 5
  total: 15
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 10 は FEAT-02 (相手強度 rolling profile 21 feature) と FEAT-03 (レース内相対 6 feature) を追加する。設計の聖域（リーク防止 / byte-reproducibility / SAFE-01 市場情報不使用）に対する多層防御（adversarial テスト + AST audit + monkeypatch lookahead 注入）は手厚く実装されており、PIT 保証の根幹（`_compute_source_asof_opponent_speed_figures` による source-as-of full-pipeline 再計算、行レベル `_pit_cutoff_prefilter`、copy-not-rename）は堅牢。

ただし、実装・テスト双方に **コアバリューを脅かす可能性のある実フィクスすべき不具合** が存在する。最も重大なのは (1) `compute_field_strength_profile` 内の `_compute_source_asof_opponent_speed_figures` が source race に1頭も starter を持たない場合（空 batch リスト）に `pd.concat([])` を呼んで暗黙の空 DataFrame を返す silent path、(2) builder Step 5c と Step 5 の間にある「`compute_field_strength_profile` が RuntimeError を raise する経路」と「builder が既に `len(history) == 0` で弾いている」という前提の暗黙依存、(3) `race_relative._gap_to_3rd_within_race` で rank==3 が存在しない場合に `pd.Series([np.nan] * len)` を生成するが index が正しく付与されない transform コンテキストでの挙動、(4) `run_phase10_evaluation.py` が `phase10_frame` / `baseline_frame` を `_compute_w2_diagnostics` に渡すが、その frame は orchestrator に渡す前の label 未 JOIN 状態であり `race_date` 列が残っているという暗黙前提、である。

加えて、テストには **本番では発覚するが unit test (KEIBA_SKIP_DB_TESTS=1) では検出されない** false-pass リスクが複数残っている（memory `phase7-ui-live-db-bugs` / `feature-snapshot-regen-required` と同系統）。例えば `test_data.py::test_phase10_*` は 554267 行の実 snapshot を前提とし、`test_builder.py::test_no_registered_feature_column_all_nan_end_to_end` は 1 頭だて合成データで `rolling_speed_figure_mean_5` / `rolling_field_strength_mean_mean_5` を検査対象から除外している（実データでは par 計算不能ケースが多くないか未検証）。

## Critical Issues

### CR-01: `field_strength._compute_source_asof_opponent_speed_figures` が全バッチ空のとき silent に空 DataFrame を返す（値レベル PIT 保証の抜け道）

**File:** `src/features/field_strength.py:282-286`
**Issue:**
`_compute_source_asof_opponent_speed_figures` は per-source-race バッチ（`SOURCE_RACE_BATCH_SIZE`）毎に `compute_speed_figure_for_history` を呼び `batches` リストに結果を蓄積する。バッチ内で source race に1頭も starter がいない場合、`batch_starters` が空になり `synth_obs` も空 → `compute_speed_figure_for_history` が空フレームを返す。その後:

```python
if not batches:
    return pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])
result = pd.concat(batches, ignore_index=True)
```

`batches` に空 DataFrame が含まれる場合 `pd.concat` は空 DataFrame を無視して結合するため、結果的に source race の一部が欠落しても例外を吐かずに後段に進む。これは CYCLE-2 HIGH-C2-1（値レベル PIT 保証）の根幹である「全 source race の opponent ability を full-pipeline 再計算する」前提を**黙Declareに破る** silent data loss 経路になる。

更に悪いことに、`compute_field_strength_profile` の Step 4 で `kakuteijyuni > 0` で starter を特定するが、`raw_history` に source race の starter 行が欠けている場合（例: EveryDB2 の一部競走中止データで `kakuteijyuni` が NULL）、当該 source race は opponent 母集団から丸ごと抜け落ち、`field_strength_*` profile 値が race 全体でNaNまたは過小評価される。これに気付かず feature をモデルに投入するとリークでなく silent data quality 低下を起こす（core value の「リーク防止最優先」の鏡像である「silent fallback 禁止」違反）。

`compute_field_strength_profile` は冒頭 `len(raw_history) == 0` で RuntimeError を raise するが、`_compute_source_asof_opponent_speed_figures` の「source race が存在するが starter が0頭」ケースは cover していない。

**Fix:**
```python
# _compute_source_asof_opponent_speed_figures のバッチループ後
if not batches:
    # source_available_at_by_race が空でないのに batches が空は全 source race が starter 不存在
    if len(source_available_at_by_race) > 0:
        raise RuntimeError(
            f"field_strength: source race {len(source_available_at_by_race)} 件中・"
            "全 source race が starter 不存在（kakuteijyuni > 0 の行が無い）・"
            "silent data loss を検知 (WR-01 fail-loud 踏襲・CYCLE-2 HIGH-C2-1)"
        )
    return pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])

# かつ各バッチで空 synth_obs をスキップせず・全バッチが空でないことを追跡
non_empty_batches = [b for b in batches if len(b) > 0]
if len(non_empty_batches) < len(batches):
    logger.warning(
        "field_strength: %d / %d バッチが空（source race starter 欠損の疑い）",
        len(batches) - len(non_empty_batches), len(batches),
    )
result = pd.concat(non_empty_batches, ignore_index=True) if non_empty_batches else \
    pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])
```

加えて `compute_field_strength_profile` 側で「starters が存在する source race 数 vs `source_available_at_by_race` の件数」を比較する fail-loud を追加すべき。

---

### CR-02: builder Step 5c が `compute_field_strength_profile` に raw_history を渡すが、profile の merge key `race_date` が history 側と profile 側で異なる dtype になる可能性（silent NaN merge）

**File:** `src/features/builder.py:556-577`
**Issue:**
builder Step 5c は以下を実行する:

```python
field_strength_profile = compute_field_strength_profile(raw_history, observations=feature_matrix)
...
history = history.merge(
    _profile_merge,
    on=["race_nkey", "kettonum", "race_date"],
    how="left",
    suffixes=("", "_fs_profile"),
)
```

merge key は `["race_nkey", "kettonum", "race_date"]`。しかし:
- `history` 側の `race_date` は DB から `nr.race_date AS race_date` で取得し、pandas で `pd.to_datetime` されて **datetime64[ns]** 型（`_construct_derived_columns` 内で `_rd_dt = pd.to_datetime(result["race_date"])` するが `result["race_date"]` 自体は元の型のまま残る。psycopg の `nr.race_date` は PostgreSQL `date` 型 → pandas では通常 `object` (Python `datetime.date`) または `datetime64`）
- `field_strength_profile` 側の `race_date` は `compute_field_strength_profile` 内で `raw_history.assign(available_at=pd.to_datetime(raw_history["race_date"]))` されるが、`out = raw_history.copy()` のまま返されるため `out["race_date"]` は入力 raw_history の型を保持する

両者が同じ raw_history 由来なので同じ型に見えるが、`history` は Step 5b の `compute_speed_figure_for_history` を経由して obs_id 展開済みフレームに変換されており、内部で race_date の再キャストやコピーが走る可能性がある。merge の結果、行が不一致（NaN profile）になった場合でも `if len(_fs_profile_cols) > 0 and len(history) > 0` のガードで黙にスルーされ、`field_strength_*` 列が history のみで NaN になる。これが rolling に渡ると「全 opponent の ability が NaN」→ rolling も全 `__MISSING__` となり、FEAT-02 21 feature が全行 sentinel になる silent data loss。

現実装では `_fetch_history` の SELECT で `nr.race_date AS race_date` を取り、psycopg3 は PostgreSQL `date` を Python `datetime.date` にマップする。pandas は object dtype として保持する。一方 `_construct_derived_columns` は `result["race_date"]` を上書きしない。よって両者 object (datetime.date) のはずだが、Step 5b 後の `history` が同じ object dtype を保持することは `compute_speed_figure_for_history` の実装依存であり、Phase 10 はこれを検証していない。

**Fix:**
merge 前に race_date の dtype を明示的に正規化する。また merge 結果の NaN 率を fail-loud 検査する。

```python
# Step 5c の merge 直前
history["race_date"] = pd.to_datetime(history["race_date"])
_profile_merge["race_date"] = pd.to_datetime(_profile_merge["race_date"])
history = history.merge(_profile_merge, on=["race_nkey", "kettonum", "race_date"], how="left", ...)
# profile が JOIN できた行の割合を fail-loud 検査（silent NaN merge 検知）
if "field_strength_mean" in history.columns and len(history) > 0:
    starter_mask = history["kakuteijyuni"].fillna(0) > 0
    if starter_mask.any():
        joined_ratio = history.loc[starter_mask, "field_strength_mean"].notna().mean()
        if joined_ratio < 0.5:
            raise RuntimeError(
                f"Step5c profile merge で field_strength_mean が {joined_ratio:.1%} しか JOIN できず "
                f"(silent data loss・dtype mismatch の疑い・core value 違反)"
            )
```

---

### CR-03: `race_relative._gap_to_3rd_within_race` が rank==3 不在時に index 不整合の NaN Series を返す（transform で正しく伝播しないケース）

**File:** `src/features/race_relative.py:159-192`
**Issue:**
`_gap_to_3rd_within_race` は `groupby.transform` から呼ばれる。rank==3 が存在しない場合:

```python
if not third_mask.any():
    return pd.Series([np.nan] * len(mean5), index=mean5.index)
```

これは関数単体では正しいが、`groupby.transform` の戻り値の index 整合性に依存する。pandas の `transform` は「戻り Series の index が group の index と一致」または「長さが group の行数と一致」のいずれかを要求する。本実装は `index=mean5.index` を明示するので安全に見えるが、`mean5` は transform に渡された group slice であり、その index は元 DataFrame の部分集合インデックス（非連続の可能性あり）。

実はこのパス自体は pandas 3.x で動作するが、より重大なのは **race が3頭未満で全馬 NaN になる仕様が文書化されているが、テストが `out["gap_to_3rd"].isna().all()` で検証しているのみ**で、`race_relative.py` の docstring D-08 「rank==3 が存在しない場合は race 内全馬 NaN」と競合する。実際、`_gap_to_top_within_race` は race size < 1 でも `top_val = mean5.max()` が NaN を返し `top_val - mean5` も全 NaN になる。しかし、race size が 1 馬のみの場合、`_gap_to_top_within_race` の `mean5.max()` は唯一の値を返し `top_val - mean5 = 0` になる（正しい）。問題は size=0 の transform 呼び出しで、`mean5.max()` は NaN だが `pd.Series([nan] * 0)` を返し transform の出力長と group size の整合性が担保されるかは pandas バージョン依存。

加えて、`_gap_to_3rd_within_race` は内部で `mean5[third_mask].iloc[0]` を使う。同着で複数行が rank==3 の場合（competition ranking `min` では rank 値が同じ馬が複数いることはないが、`rank==3` を満たす馬は最大1頭のはず）、`iloc[0]` は安全。しかし万が一 rank==3 の馬が複数いる場合（pandas `rank(method="min")` では理論上あり得ないが）、最初の1頭だけを使う挙動は REVIEW MEDIUM-7 仕様と整合する。このロジック自体は正しいが、ドキュメントとコードの仕様表明が弱い。

**Fix:**
本 Critical の本体は CR-01/CR-02 であり、本項は WARNING に近いが、race size 境界（0/1/2/3 馬）での transform 挙動が pandas バージョン依存のリスクを含むため明示防御を推奨。

```python
def _gap_to_3rd_within_race(mean5: pd.Series) -> pd.Series:
    # 早返し: race size < 3 は rank==3 が存在し得ない（competition ranking でも）
    if len(mean5) < 3:
        return pd.Series([np.nan] * len(mean5), index=mean5.index)
    ranks = mean5.rank(method="min", ascending=False, na_option="keep")
    third_mask = ranks == 3
    if not third_mask.any():
        return pd.Series([np.nan] * len(mean5), index=mean5.index)
    third_val = mean5[third_mask].iloc[0]
    return third_val - mean5
```

---

### CR-04: `run_phase10_evaluation.py::_compute_w2_diagnostics` が orchestrator 呼出し前の frame（label 未 JOIN）を使うが、`compute_candidate_score_diagnostics` は rolling 系 feature 列を前提とする（FEAT-02/03 未伝播で silent skip）

**File:** `scripts/run_phase10_evaluation.py:262-280, 406`
**Issue:**
`_compute_w2_diagnostics` は `phase10_frame`（`build_training_frame` の出力）を受け取る:

```python
w2_result = _compute_w2_diagnostics(phase10_frame, out_dir=out_dir)
```

`phase10_frame` は `build_training_frame(phase10_feature_df, label_df)` で生成される。しかし、`build_training_frame` の出力が `rolling_speed_figure_mean_5` / `rolling_field_strength_mean_mean_5` 列を含むかは `phase10_feature_df`（`load_feature_matrix(snapshot_id=args.phase10_snapshot_id)` の戻り値）の Parquet 実カラムに依存する。

`_compute_w2_diagnostics` は:

```python
required = ("race_nkey", "rolling_speed_figure_mean_5", "rolling_field_strength_mean_mean_5")
missing = [c for c in required if c not in phase10_frame.columns]
if missing:
    logger.warning("W-2 skip: phase10_frame に必須列 %s が無い・diagnostic は算出不能 (FEAT-02/03 未伝播?)", missing)
    return {"status": "skipped", "reason": f"missing cols: {missing}"}
```

この skip path は **W-2 acceptance criteria を満たさない** が、`_evaluate_gate` の gate 判定には影響しない（diagnostic は証跡であって gate 条件でない）。しかし SUMMRY レポートに `w2_result["status"] == "skipped"` が記録されるだけで、Phase 10 が W-2 未達で ship されるリスクがある。これは §11.2 聖域（test 窓 rank すり替え禁止・W-2 候補集合 diagnostic）の履行証跡を欠く状態での ship を許す。

加えて、`compute_candidate_score_diagnostics` は `feature_matrix` のコピーを取り split_mask で行抽出するが、`phase10_frame` には label 列（`fukusho_hit_validated` 等）が含まれる。これ自体は diagnostic に影響しないが、race_relative の feature 計算で `pd.to_numeric(..., errors="coerce")` が走り、もし Parquet 読込時の dtype が `Float64` でない（`object` + sentinel 等）場合に、`build_training_frame` を経た frame では既に NaN 化されている前提が暗黙。

**Fix:**
W-2 skip を WARNING でなく ERROR に格上げし、gate 実行前に必須列が揃っているかを fail-loud 検査する。また `_compute_w2_diagnostics` に渡す frame を orchestrator 後の `phase10_pred`（label JOIN 済み・FEATURE_COLUMNS 揃っていることが make_X_y で保証）ではなく、明示的に rolling 系 feature を含むことを assert する。

```python
def _compute_w2_diagnostics(phase10_frame, *, out_dir):
    ...
    missing = [c for c in required if c not in phase10_frame.columns]
    if missing:
        # WARNING でなく ERROR に格上げ・W-2 acceptance criteria 未達を明示
        raise RuntimeError(
            f"W-2 必須列が phase10_frame に無い: {missing}・FEAT-02/03 未伝播・"
            "Phase 10 acceptance_criteria W-2 が履行不能（§11.2 聖域）"
        )
    ...
```

## Warnings

### WR-01: `field_strength._opponent_ability_latest_mean5` で obs_id から `_source_race_nkey` を `rsplit("_", n=1)` で抽出するが、`race_nkey` に `_` が含まれる場合に誤抽出リスク

**File:** `src/features/field_strength.py:336-344`
**Issue:**
`obs_id` 形式は `SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum>`。`stripped = obs_id_str.str[len("SOURCE_ASOF_"):]` で `source_race_nkey + "_" + kettonum` になり、`rsplit("_", n=1)` で最後の `_` で分割して `parts[0]` を source_race_nkey とする。

しかし `race_nkey` は builder の `make_race_nkey` で `YYYYJJJKK< nichiji>NN` の零埋連結（`_` を含まない）のはずだが、テストデータでは `"R1_20230610"` のように `_` を含む race_nkey を使っている（`_fs_history_row("R1_20230610", ...)`）。本番の `make_race_nkey` は `_` を含まないため実害は無いが、adversarial テストが本番と異なる race_nkey 形式を使っているため、テストが GREEN でも本番で `_` 含み race_nkey が混入した場合に壊れるリスクを検出できない。

`kettonum` も整数想定だが、`astype(str)` した文字列に `_` が含まれることは無い。よって `rsplit("_", n=1)` は kettonum と race_nkey の境界を正しく取れるが、`parts[0]` が `source_race_nkey` 全体である保証は race_nkey 形式に依存する。

**Fix:**
本番の `make_race_nkey` が `_` を含まないことを文書化し、テストヘルパー `_fs_history_row` もそれに合わせる。または `obs_id` に区切り文字として `__` (double underscore) 等を使い、parse を堅牢にする。

```python
# テストヘルパを本番形式に揃える
def _fs_history_row(race_nkey, kettonum, ...):
    # 本番 make_race_nkey 形式（YYYYJJJKKNN・_ 含まない）を模擬
    # テスト識別性を保つため race_date を suffix にする場合は _ でなく別区切りを使う
    ...
```

---

### WR-02: `run_phase10_evaluation.py` が `make_pool(role="readonly")` で pool を作るが、`statement_timeout` が cursor 単位で SET され pool 再利用で残らない可能性

**File:** `scripts/run_phase10_evaluation.py:362-364`
**Issue:**
```python
readonly_pool = make_pool(settings, role="readonly")
try:
    with readonly_cursor(readonly_pool) as cur:
        cur.execute("SET statement_timeout = '30s'")
        # ... load_labels(cur), load_feature_matrix などを実行 ...
```

`SET statement_timeout` は session レベルで効くが、`readonly_cursor` が `with` ブロックを抜けた後に connection を pool に返す際、次の checkout で別 session になると `statement_timeout` が引き継がれない。実際には `with readonly_cursor(...)` のスコープ内で `load_labels(cur)` 等が実行されるが、`load_feature_matrix` は `cur` を使わず Parquet から読むので問題無い。

しかし、`W-3 category_map bit-identity` の `hash_canonical(baseline_cat_map)` と `hash_canonical(phase10_cat_map)` は cur を使わず JSON ファイルから読む。`orchestrator.train_and_predict` は別途 DB アクセスする可能性があり、その際に `statement_timeout = '30s'` が効いている保証がない（memory `subagent-db-query-statement-timeout` と同系統）。

**Fix:**
pool 作成時に `SET statement_timeout` を pool 全体に適用するか、`train_and_predict` 呼出しの前にも明示的に SET する。psycopg_pool なら `configure` callback で設定する。

```python
readonly_pool = make_pool(settings, role="readonly")
# pool 全体に statement_timeout を適用（connection checkout 毎に SET）
def _configure(conn):
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
        conn.commit()
readonly_pool.configure(_configure)  # psycopg_pool の API
```

---

### WR-03: `snapshot._coerce_rolling_columns_for_parquet` が `_FEAT03_NUMERIC_COLUMNS` のみを扱い、`field_strength_adjusted_rank` 等が object+sentinel の場合に Parquet 直列化で失敗する可能性（防御的だが完全でない）

**File:** `src/features/snapshot.py:84-137`
**Issue:**
`_coerce_rolling_columns_for_parquet` は:
- `rolling_` prefix 列 → numeric または categorical 判定して Float64 / string 変換
- `_FEAT03_NUMERIC_COLUMNS` (speed_index_rank_*, gap_to_*, field_strength_adjusted_rank) → Float64 変換

これは builder Step 6c が既に `pd.to_numeric(..., errors="coerce").astype("Float64")` で変換済みの frame を snapshot に渡す前提の「最終防衛線」。しかし:
- `_FEAT03_NUMERIC_COLUMNS` は `frozenset` でハードコード。新たな FEAT-03 系 feature が追加された場合、snapshot.py 側の対応を忘れると ArrowTypeError が実データでのみ発覚する（unit test は検出しない・memory `feature-snapshot-regen-required`）。
- `_coerce_rolling_columns_for_parquet` は `series.dtype != object` の場合 skip するが、builder が既に `Float64` に変換済みの frame を渡す場合、この防衛線は機能しない（既に object でないため）。よって snapshot 境界での防御は「builder が object で渡した場合」のみ有効。

両者が contract を満たしている限り安全だが、contract の一方が壊れた場合の二重防御が thin。

**Fix:**
`_FEAT03_NUMERIC_COLUMNS` を `race_relative._AXIS_TO_RANK_SUFFIX` 等の定数から動的導出するか、builder ↔ snapshot 間の contract を assert で明示する。

```python
# snapshot.py の冒頭で race_relative の定数を import して frozen set を動的構築
from src.features.race_relative import _AXIS_TO_RANK_SUFFIX
_FEAT03_NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {f"speed_index_rank_{suffix}" for suffix in _AXIS_TO_RANK_SUFFIX.values()}
) | {"gap_to_top", "gap_to_3rd", "field_strength_adjusted_rank"}
```

---

### WR-04: `field_strength.compute_field_strength_profile` が `_compute_source_asof_opponent_speed_figures` で source race 毎に `compute_speed_figure_for_history` を呼ぶが、raw_history 全体を毎回渡すため O(N²) のリスク（CYCLE-3 MEDIUM #3 は回避を主張するが数値根拠が弱い）

**File:** `src/features/field_strength.py:262-286`
**Issue:**
CYCLE-3 MEDIUM #3 は「per-source-race バッチ（`SOURCE_RACE_BATCH_SIZE=100`）で H² 積 materialize を回避」と主張する。実際 `compute_speed_figure_for_history(raw_history, observations=synth_obs)` を呼ぶたびに、`speed_figure.py` の内部で `out.merge(obs_keys, on='kettonum')` が走り、H の履歴行 × H を含む source race 数 の積を materialize する。

バッチサイズ 100 は「バッチ内 source race 数 = 100」を意味し、各バッチで「馬 H を含む source race が最大100」まで materialize される。本番規模（~1万頭 × ~50過去走 = 50万行 history、source race ~数千）で worst case は 100 * 50万 = 5000万行/バッチ × バッチ数 = 数億行規模の materialize。これは OOM リスク。

`test_production_scale_smoke_no_h_squared_blowup` は 200 race で検証（~19600 行）し、peak memory 8GB / wall time 300s を threshold とするが、本番規模（数千 source race）でのスモークは実行されていない（PLAN 01 設計上「大規模は現実的時間で終わらない」と明記）。

これは性能問題に見えるが、実は **core value に直結する silent data loss リスク** でもある：OOM で `compute_speed_figure_for_history` が MemoryError を吐いた場合、現状の try/except が OperationalError/InterfaceError/ConnectionError のみを catch するため MemoryError は伝播する。しかし `compute_field_strength_profile` は MemoryError を特別扱いせず、caller (builder) も同様。結果的に builder 全体が落ちるか、psycopg_pool が connection を返さず orphan になる（memory `subagent-db-query-statement-timeout` と同系統）。

**Fix:**
本番規模での memory profile を PLAN 07 で必ず実施する（既に W-3 Test 3 で smoke は走るが 200 race は小さすぎる）。`SOURCE_RACE_BATCH_SIZE=100` を本番規模で調整するか、メモリ上限を設定した上でバッチサイズを動的調整する。

```python
# 本番規模 smoke を KEIBA_RUN_PERF_TESTS=1 で 1000 race まで拡張
PROD_SMOKE_N_RACES_LARGE: int = 1000  # より本番に近い規模
# test_production_scale_smoke_large として追加
```

---

### WR-05: `test_field_strength.py::test_production_scale_smoke_no_h_squared_blowup` が `peak_py_gb` (tracemalloc) と `rss_gb` (getrusage) の大きい方で判定するが、macOS と Linux で ru_maxrss 単位が異なる分岐はあるものの、tracemalloc は Python ヒープのみで numpy/pandas の native buffer を含まない

**File:** `tests/features/test_field_strength.py:1041-1069`
**Issue:**
```python
tracemalloc.start()
...
_current, peak_py = tracemalloc.get_traced_memory()
...
rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
```

tracemalloc は Python オブジェクトのアロケーションのみ追跡し、pandas/numpy の内部 ndarray buffer（C レベルの malloc）は含まれない。`peak_py` は大幅に過小評価される。一方 `ru_maxrss` はプロセス全体の peak RSS だが、テストプロセスの **プロセス起動時から現在までの最大値** であり、テスト関数内の peak でない（他のテストが先に大量メモリを使った場合、その値が残る）。

よって `peak_gb = max(peak_py_gb, rss_gb)` は:
- pandas DataFrame の native buffer が支配的な場合 → tracemalloc は過小評価、rss_gb は他テストの peak を含む → 判定が不正確
- 実メモリ使用が PROD_PEAK_MEM_BUDGET_GB(8.0) を超えていても、rss_gb が他テストのピークを引継いでいなければ then 現プロセスのピークとして検出されるので「マシ」だが、CI runner のメモリ総量によっては検出漏れ

本テストは default skip (`KEIBA_RUN_PERF_TESTS`) なので CI では走らないが、手動実行時に false GREEN を出すリスクがある。

**Fix:**
psutil 等でプロセス RSS をプローブするか、tracemalloc を補完する。少なくとも docstring で「tracemalloc は Python ヒープのみ・numpy buffer 含まず」と明記し、rss_gb を主指標にする。

```python
# 主指標を rss_gb に・tracemalloc は参考記録
peak_gb = rss_gb  # tracemalloc は Python ヒープのみで不正確・RSS を主指標に
logger.info("PROD smoke: peak_rss=%.2fGB (py_heap=%.2fGB・参考)", rss_gb, peak_py_gb)
assert peak_gb <= PROD_PEAK_MEM_BUDGET_GB, ...
```

---

### WR-06: `test_audit_field_strength.py::test_feature_columns_contains_phase10_features_no_proxy` が snapshot 未生成時に `pytest.raises(FileNotFoundError)` で GREEN になるが、これは silent fallback で mask する経路（M2 主張と一部矛盾）

**File:** `tests/audit/test_audit_field_strength.py:214-269`
**Issue:**
```python
snapshot_path = Path(f"snapshots/feature_matrix_{_PHASE10_SNAPSHOT_ID}.parquet")
if snapshot_path.exists():
    p10_cols = _derive_feature_columns(snapshot_id=_PHASE10_SNAPSHOT_ID)
    # 27 feature 含有・forbidden prefix 0件を検査
else:
    with pytest.raises(FileNotFoundError):
        _derive_feature_columns(snapshot_id=_PHASE10_SNAPSHOT_ID)
```

`test_audit_speed_figure.py` の REVIEW M2 コメントは「snapshot 未生成時に v1.0 へ静かに fallback して Phase 9 feature 欠落を mask しない」ことを検証する。本テストも同様に `FileNotFoundError` を期待するが、この else 経路が実行されるのは CI（snapshot 無し）や unit test 実行時のみ。

実 snapshot が存在する環境（開発者の手元・本番 CI で snapshot 生成済み）では if 経路が走るが、存在しない環境では else 経路が走り、**両者が「同じテスト関数」で代替される**。これは「実データ検証」の網羅性を下げる：CI が常に else 経路を走らせる場合、27 feature 含有検査が一度も実行されず ship されるリスクがある。

test_data.py 側には `test_phase10_derive_feature_columns_new_and_baseline_regression` があり、実 snapshot に依存するが default skip マーカーが無く、snapshot が無いと `FileNotFoundError` で RED になる。よって test_audit_field_strength 側の else 経路は test_data.py と重複かつ弱い検証。

**Fix:**
test_audit_field_strength の else 経路を削除し、snapshot 未生成時は `pytest.skip("Phase 10 snapshot not generated・PLAN 05 で生成後に実行")` にするか、test_data.py に一本化する。現状は「silent fallback で mask しない」ことを検証するつもりだが、実 snapshot 環境で else 経路が走らないため検出力が偏る。

```python
if snapshot_path.exists():
    p10_cols = _derive_feature_columns(snapshot_id=_PHASE10_SNAPSHOT_ID)
    # 27 feature 含有・forbidden prefix 0件
else:
    pytest.skip(
        f"Phase 10 snapshot ({_PHASE10_SNAPSHOT_ID}) 未生成・"
        "実 snapshot 検証は test_data.py::test_phase10_* に一本化"
    )
```

## Info

### IN-01: `field_strength.compute_field_strength_profile` の docstring が `observations` 引数を「後方互換用（現在は未使用）」と宣言するが、実引数のデフォルト値が `None` で caller (builder) は `observations=feature_matrix` を渡している

**File:** `src/features/field_strength.py:387-414`
**Issue:**
docstring は「observations は後方互換用（現在は未使用）」と書くが、builder は `compute_field_strength_profile(raw_history, observations=feature_matrix)` を呼ぶ。引数が未使用なら builder 呼出から削除すべき。現状は「将来の拡張で使うかもしれない」意図の残骸で、コードリーディングを混乱させる。
**Fix:** 引数を削除するか、docstring で「将来拡張用・現未使用」を明示して caller も名前付き引数を残す意図を書く。

---

### IN-02: `race_relative.compute_candidate_score_diagnostics` が `score.std()` を `score.notna().sum() >= 2` の場合のみ計算するが、pandas `std()` は n=1 で NaN を返すため条件は冗長

**File:** `src/features/race_relative.py:388-396`
**Issue:**
```python
"std": float(score.std()) if score.notna().sum() >= 2 else float("nan"),
```
pandas の `Series.std()` は `ddof=1` デフォルトで、n<2 の場合 NaN を返す。よって `if score.notna().sum() >= 2` は不要だが、明示することで意図を示す。同じ idiom が `adjusted_rank_std` にもある。
**Fix:** そのままでも正しい（明示的）。docstring で「n<2 は std 定義不能」と書く程度。

---

### IN-03: `builder.py` の Step 5c が `import time as _time` を関数内で実行する（モジュール先頭でなく）

**File:** `src/features/builder.py:535-536`
**Issue:**
`import time as _time` が `build_feature_matrix` 関数内で実行される。Python は import を cache するので性能影響は無いが、PEP 8 / ruff の isort 規約では module-level import を推奨。同様に `from src.features.speed_figure import ...` / `from src.features.field_strength import ...` / `from src.features.race_relative import ...` も関数内 import。
これはおそらく循環 import 回避のための意図的な遅延 import だが、docstring で意図を明記すべき。
**Fix:** 関数内 import の意図（循環 import 回避・遅延ロード）をコメントで明記。

---

### IN-04: `rolling.py::_ROLLING_SYSTEMS` と `availability._ROLLING_SYSTEMS_FOR_RESERVED` が同一順序の tuple を二重定義する（drift リスク）

**File:** `src/features/rolling.py:75-92`, `src/features/availability.py:143-166`
**Issue:**
両者は意図的に再定義（循環依存回避）だが、`test_registry_rolling_systems_match_rolling_impl` が `tuple(_ROLLING_SYSTEMS_FOR_RESERVED) == _ROLLING_SYSTEMS` で順序含め一致を検査している。新系統追加時に両者を更新し忘れると RED になるので検出力はあるが、二重定義自体が IN-01 系の軽微な保守性低下。
**Fix:** 現状の機械検査で十分。docstring で「循環依存回避のため再定義・test で drift 検出」を明記済み（既にコメントにある）。

---

### IN-05: `run_phase10_evaluation.py` が `BT1_PERIODS` を `train/calib/test` の3キーで持つが、`test_compute_w2_diagnostics` は train と calib のみを使い test は無視する（W-2 が train/calib 窓のみという仕様通りだが、暗黙）

**File:** `scripts/run_phase10_evaluation.py:266-267`
**Issue:**
W-2 diagnostic は §11.2 聖域（test 窓 rank すり替え禁止）通り train/calib 窓のみ。しかし `BT1_PERIODS["test"]` が W-2 で使われないことが暗黙。test 窓の rank すり替えを防ぐため、W-2 diagnostic が test 窓 mask を誤って含まないことを assert するとより安全。
**Fix:** `_compute_w2_diagnostics` 内で `test_mask` を明示的に除外する assert を追加。

---

**Total findings: 4 Critical / 6 Warning / 5 Info**

核心のリーク防止機構（source-as-of full-pipeline 再計算・行レベル PIT filter・AST audit）は手厚く、本レビューで指摘した Critical 4件は「コアバリュー（リーク防止）を直接破る」ものでなく「silent data loss / merge dtype mismatch / W-2 履行証跡欠損 / race size 境界の pandas 依存」など、リーク防止の周辺の堅牢性に関わるもの。しかし Phase 10 は core value を最優先するプロジェクトであり、silent fallback 経路の fail-loud 化（CR-01/CR-02）と W-2 acceptance criteria の履行証跡（CR-04）は ship 前に対応すべき。

---

_Reviewed: 2026-06-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
