"""Phase 4 trainer: LightGBM native categorical + CatBoost has_time=True (SC#3 / §14.3 / §14.4 / D-04 / D-05 / D-09).

成功基準#3 (SC#3) と MODL-03 を実装する service 層。LightGBM 4.6 の native categorical
分割（Fisher 最適分割・target encoding 非依存）と CatBoost 1.2.10 の ordered target
statistics（``has_time=True`` で random permutation を無効化）を用いてリークセーフな
categorical / 欠損処理を実現する。

**設計の核心（CLAUDE.md §14.3/§14.4 / review HIGH#2/#3/#6/#7 / Cycle 2 NEW-2）:**

1. **target encoding 一切禁止**（§14.3）。``target_encoding`` / ``TargetEncoder`` /
   ``mean_encoding`` の呼出は一切無い（grep で 0 件・acceptance criteria で固定）。
   LightGBM は native categorical 分割（feature 値のみ使用・target を分割探索に使わない）、
   CatBoost は ordered TS（``has_time=True`` で過去行のみ使用）。
2. **NaN→code -1 ハザード回避**（Pitfall 3 / T-04-14）。低基数 string 列は ``fillna("__MISSING__")``
   してから ``category`` dtype 化・高基数 ``_code`` 列は frozen category map が非負 int32 を
   保証済み。``_prepare_lightgbm_matrix`` が ``.cat.codes.min() >= 0`` を assert する。
3. **高基数 ``_code`` 列は categorical 扱い**（review HIGH#6 / T-04-13b / MODL-03）。
   ``jockey_id_code`` / ``trainer_id_code`` / ``sire_id_code`` / ``bms_id_code`` / ``horse_id_code``
   を LightGBM ``categorical_feature`` と CatBoost ``cat_features`` の**両方**に含める。
   CatBoost では ``astype(str)`` で文字列化してから ``cat_features`` に渡す（int を数値扱いして
   任意の ID 順序に序数構造を課す MODL-03 違反を防止）。
4. **CatBoost ``has_time=True`` 強制**（Pitfall 2 / T-04-15）。``_prepare_catboost_pool`` は
   ``df.sort_values(["race_start_datetime", "race_key"])`` してから Pool を構築し、``CB_INIT_PARAMS``
   は ``has_time=True`` を固定（``random permutation`` を無効化し ordered TS が過去行のみ使用）。
5. **行整列保証**（review HIGH#2 / T-04-15b/15c / Cycle 2 NEW-2）。``train_lightgbm`` /
   ``train_catboost`` は ``X_train.index.equals(y_train.index)`` を ``raise ValueError`` で
   assert。``align_predictions`` は sort 済み Pool 予測を元の行順序に復元する際、reindex の
   silent NaN / 重複 / 欠落を 5 条件の厳密置換 guard（``RuntimeError``）で検出する。
6. **early stopping eval set 分離**（Pitfall 5 / D-04 / review Cross-Plan #8 / T-04-16）。
   ``assert_eval_disjoint`` は eval / calib / test の正準 race_key が pairwise disjoint であること
   に加え ``eval_max_date <= train_core_max_date``（eval が train 末尾に収まる）を検証する。

**決定論フラグ（review HIGH#7 bit-identical / T-04-19）:**
LightGBM は ``seed=42, deterministic=True, force_col_wise=True, num_threads=1,
bagging_seed=42, feature_fraction_seed=42``、CatBoost は ``random_seed=42, has_time=True,
thread_count=1`` を固定する（SC#4 bit-identical 再現性の前提）。

参照: CLAUDE.md §14.3/§14.4 / 04-RESEARCH.md D-03/D-04/D-05/D-09 / 04-PATTERNS.md
      trainer.py セクション + Shared Pattern 2/3/6 / src/utils/calibrator.py /
      src/features/category_map_consumer.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 定数（D-03 確定・review HIGH#6: _code 列は cat_features に含める）
# ---------------------------------------------------------------------------
# 低基数 string categorical 列（D-03 確定・5 列）。fillna("__MISSING__") → category dtype 化。
LOW_CARD_CAT_COLS: list[str] = [
    "sexcd",
    "class_code_normalized",
    "estimated_running_style",
    "rolling_jyocd_mode_5",
    "rolling_jyocd_latest_5",
]

# 高基数 ID ``_code`` 列（frozen category map で非負 int32 化済み・D-03）。
# review HIGH#6: これらは数値扱いではなく categorical として扱う（MODL-03・任意 ID 順序の序数
# 構造を CatBoost に課すことを防止）。LightGBM では int32 category dtype・CatBoost では
# astype(str) で文字列化して cat_features に含める。
HIGH_CARD_CODE_COLS: list[str] = [
    "jockey_id_code",
    "trainer_id_code",
    "sire_id_code",
    "bms_id_code",
    "horse_id_code",
]

# LightGBM / CatBoost の両方に渡す categorical 列リスト（LOW_CARD + HIGH_CARD_CODE_COLS）。
ALL_CAT_COLS: list[str] = LOW_CARD_CAT_COLS + HIGH_CARD_CODE_COLS

RANDOM_SEED: int = 42
N_ESTIMATORS: int = 1000
EARLY_STOPPING_ROUNDS: int = 50

# LightGBM 初期ハイパラ（D-09 確定・review HIGH#7: bit-identical 全フラグ固定）
LGB_INIT_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": RANDOM_SEED,
    "deterministic": True,        # bit-identical 再現性
    "force_col_wise": True,       # 決定論的
    "num_threads": 1,             # review HIGH#7: thread randomness を排除
    "bagging_seed": RANDOM_SEED,
    "feature_fraction_seed": RANDOM_SEED,
}

# CatBoost 初期ハイパラ（D-09 確定・review HIGH#7: bit-identical）
CB_INIT_PARAMS: dict[str, Any] = {
    "iterations": N_ESTIMATORS,
    "learning_rate": 0.05,
    "depth": 6,
    "l2_leaf_reg": 3.0,
    "has_time": True,             # 必須・random permutation 無効化（Pitfall 2 / T-04-15）
    "random_seed": RANDOM_SEED,
    "eval_metric": "Logloss",
    "early_stopping_rounds": EARLY_STOPPING_ROUNDS,
    "verbose": False,
    "thread_count": 1,            # review HIGH#7: bit-identical
    "allow_writing_files": False,  # CatBoost が学習ログを disk に書かない（CI 再現性）
}


# ---------------------------------------------------------------------------
# _prepare_lightgbm_matrix — review MEDIUM: _code 列も categorical
# ---------------------------------------------------------------------------
def _prepare_lightgbm_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """LightGBM 学習用に categorical 列を ``category`` dtype 化する（Pitfall 3 / §14.3）。

    - LOW_CARD_CAT_COLS: ``fillna("__MISSING__")`` → ``astype("category")``（NaN→-1 回避）。
    - HIGH_CARD_CODE_COLS: ``astype("category")`` で categorical 化（int32 のまま・非負保証済み）。
      LightGBM の Fisher 最適分割が適用される（target 非依存・target encoding 禁止整合）。

    戻り値はコピー。``categorical_feature`` で渡す列が全て非負 int32 code（``.cat.codes.min() >= 0``）
    であることを assert する（Pitfall 3 / T-04-14・fail-loud）。

    併せて sort / provenance 用の meta 列（``race_start_datetime`` / ``race_key`` / ``race_date``）
    を feature matrix から除外する（これらはモデル特徴量ではない・時系列 meta のみ）。
    """
    # meta 列を feature matrix から除外（race_start_datetime / race_key / race_date は
    # 時系列 sort / provenance 用・モデル特徴量ではない）
    _META_FEATURE_EXCLUDE = ("race_start_datetime", "race_key", "race_date")
    out = df[[c for c in df.columns if c not in _META_FEATURE_EXCLUDE]].copy()
    # 低基数 string 列: __MISSING__ sentinel で fillna 後に category 化（Pitfall 3 回避）
    for col in LOW_CARD_CAT_COLS:
        if col in out.columns:
            out[col] = out[col].fillna("__MISSING__").astype("category")
    # 高基数 _code 列: int32 のまま category dtype 化（非負保証済み・Fisher 分割適用）
    for col in HIGH_CARD_CODE_COLS:
        if col in out.columns:
            # frozen category map が非負 int32 を保証済みだが、ここでも念のため NaN を検出
            if out[col].isna().any():
                raise ValueError(
                    f"_prepare_lightgbm_matrix: {col} に NaN が残存 "
                    f"(frozen category map が非負 int32 を保証すべき・Pitfall 3 / T-04-14)"
                )
            out[col] = out[col].astype("category")

    # 非負 code 保証の fail-loud assert（Pitfall 3 / T-04-14）
    for col in ALL_CAT_COLS:
        if col in out.columns and hasattr(out[col], "cat"):
            min_code = out[col].cat.codes.min()
            if min_code < 0:
                raise ValueError(
                    f"_prepare_lightgbm_matrix: {col} の category code が負 "
                    f"(min={min_code}・NaN→-1 ハザード・Pitfall 3 / T-04-14・§14.3)"
                )
            # NaN が残っていないこと（silent fallback 禁止）
            n_nan = int(out[col].isna().sum())
            if n_nan > 0:
                raise ValueError(
                    f"_prepare_lightgbm_matrix: {col} に NaN が {n_nan} 件残存 "
                    f"(silent fallback 禁止・Pitfall 3)"
                )
    return out


def _prepare_lightgbm_train_eval(
    X_train: pd.DataFrame,
    X_eval: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """``train_lightgbm`` 用に train/eval を一貫した categorical dtype 化する。

    LightGBM は train と eval の categorical categories が完全一致することを要求する
    （``train and valid dataset categorical_feature do not match``）。両 DataFrame を個別に
    ``_prepare_lightgbm_matrix`` に渡すと、それぞれが独自の category set を fit してしまい
    eval に train に無い値が含まれる（または逆）場合に不一致になる。

    これを防ぐため、本関数は train ∪ eval の全カテゴリ値を統一した category dtype を両方に
    適用する。LOW_CARD_CAT_COLS は ``__MISSING__`` sentinel 含む全値を統一・HIGH_CARD_CODE_COLS
    は ``int32`` code の和集合を統一。
    """
    # meta 列を除外（_prepare_lightgbm_matrix と同一方針）
    _META_FEATURE_EXCLUDE = ("race_start_datetime", "race_key", "race_date")
    train_base = X_train[[c for c in X_train.columns if c not in _META_FEATURE_EXCLUDE]].copy()
    eval_base = (
        X_eval[[c for c in X_eval.columns if c not in _META_FEATURE_EXCLUDE]].copy()
        if X_eval is not None
        else None
    )

    # LOW_CARD_CAT_COLS: train ∪ eval の全カテゴリ値を統一
    for col in LOW_CARD_CAT_COLS:
        if col not in train_base.columns:
            continue
        train_vals = train_base[col].fillna("__MISSING__")
        all_cats = sorted(set(train_vals.astype(str).unique()))
        if eval_base is not None and col in eval_base.columns:
            eval_vals = eval_base[col].fillna("__MISSING__").astype(str)
            all_cats = sorted(set(all_cats) | set(eval_vals.unique()))
            eval_base[col] = pd.Categorical(eval_vals, categories=all_cats)
        train_base[col] = pd.Categorical(train_vals.astype(str), categories=all_cats)

    # HIGH_CARD_CODE_COLS: int32 code の和集合を統一（非負保証）
    for col in HIGH_CARD_CODE_COLS:
        if col not in train_base.columns:
            continue
        train_codes = train_base[col].astype("int32")
        all_codes = sorted(set(train_codes.unique()))
        if eval_base is not None and col in eval_base.columns:
            eval_codes = eval_base[col].astype("int32")
            all_codes = sorted(set(all_codes) | set(eval_codes.unique()))
            eval_base[col] = pd.Categorical(eval_codes, categories=all_codes)
        train_base[col] = pd.Categorical(train_codes, categories=all_codes)

    # 非負 code 保証の fail-loud assert（Pitfall 3 / T-04-14）
    for col in ALL_CAT_COLS:
        if col in train_base.columns and hasattr(train_base[col], "cat"):
            min_code = train_base[col].cat.codes.min()
            if min_code < 0:
                raise ValueError(
                    f"_prepare_lightgbm_train_eval: {col} の category code が負 "
                    f"(min={min_code}・Pitfall 3 / T-04-14)"
                )

    return train_base, eval_base


# ---------------------------------------------------------------------------
# _prepare_catboost_pool — review HIGH#6 + HIGH#2
# ---------------------------------------------------------------------------
def _prepare_catboost_pool(
    df: pd.DataFrame,
    y: pd.Series | None = None,
    *,
    sort: bool = True,
) -> tuple[Any, pd.Index]:
    """CatBoost Pool を構築する（review HIGH#6: _code 列を cat_features に含める・HIGH#2: sorted_index 返却）。

    - ``sort=True`` の場合 ``df.sort_values(["race_start_datetime", "race_key"], kind="mergesort")``
      してから Pool を構築（``has_time=True`` が入力順序を使用・Pitfall 2 / T-04-15）。
    - LOW_CARD_CAT_COLS と HIGH_CARD_CODE_COLS の**両方**を ``cat_features`` に含める。
      HIGH_CARD_CODE_COLS は ``astype(str)`` で文字列化してから Pool に渡す（review HIGH#6:
      int を数値扱いして任意 ID 順序に序数構造を課す MODL-03 違反を防止・T-04-13b）。
    - 戻り値は ``(Pool, sorted_index)`` の tuple。``sorted_index`` は ``align_predictions`` が
      予測を元の行順序に復元するために使用する（review HIGH#2 / T-04-15b）。
    """
    from catboost import Pool

    # sort / provenance 用の meta 列を一時的に参照するが・Pool に渡す feature matrix
    # からは除外する（モデル特徴量には混入しない・LightGBM と同一方針）。
    _META_SORT_COLS = ("race_start_datetime", "race_key")
    _META_FEATURE_EXCLUDE = ("race_start_datetime", "race_key", "race_date")

    if sort:
        sort_keys = [c for c in _META_SORT_COLS if c in df.columns]
        if "race_start_datetime" not in df.columns:
            raise ValueError(
                "_prepare_catboost_pool: race_start_datetime 列が無い "
                "(has_time=True が入力順序を使用するため sort 必須・Pitfall 2 / T-04-15)"
            )
        df_sorted = df.sort_values(sort_keys, kind="mergesort").copy()
    else:
        df_sorted = df.copy()

    sorted_index = df_sorted.index

    # LOW_CARD_CAT_COLS: __MISSING__ sentinel で fillna（CatBoost も string cat を期待）
    for col in LOW_CARD_CAT_COLS:
        if col in df_sorted.columns:
            df_sorted[col] = df_sorted[col].fillna("__MISSING__").astype(str)

    # HIGH_CARD_CODE_COLS: int32 を astype(str) で文字列化し cat_features に含める
    # （review HIGH#6: 数値扱いで序数構造を課すことを防止・MODL-03・T-04-13b）
    for col in HIGH_CARD_CODE_COLS:
        if col in df_sorted.columns:
            df_sorted[col] = df_sorted[col].astype(str)

    # Pool に渡す前に sort 用 meta 列を除外（race_start_datetime / race_key / race_date は特徴量ではない）
    feature_cols = [c for c in df_sorted.columns if c not in _META_FEATURE_EXCLUDE]
    df_features = df_sorted[feature_cols].copy()

    # cat_features に含める実在列のみ（meta 列除外後）
    cat_features_present = [c for c in ALL_CAT_COLS if c in df_features.columns]

    y_aligned = y_sorted_for_pool(y, sorted_index) if y is not None else None
    pool = (
        Pool(df_features, y_aligned, cat_features=cat_features_present)
        if y is not None
        else Pool(df_features, cat_features=cat_features_present)
    )
    return pool, sorted_index


def y_sorted_for_pool(y: pd.Series, sorted_index: pd.Index) -> pd.Series:
    """y を sorted_index の順序に整列して返す（``_prepare_catboost_pool`` の内部 helper）。

    ``y.index`` は元の ``df.index`` と同一であることを assert し（行整列・review HIGH#2）、
    sorted_index に従って ``reindex`` する。``set(y.index) == set(sorted_index)`` でない場合は
    ``RuntimeError``（align_predictions の厳密置換 guard と同根・部分集合/重複を fail-loud）。
    """
    if not y.index.equals(sorted_index):
        # 行整列検証（review HIGH#2）
        if not sorted_index.is_unique or not y.index.is_unique:
            raise RuntimeError(
                "y_sorted_for_pool: index が unique でない "
                "(CatBoost Pool が行を黙示落とした兆候・review HIGH#2)"
            )
        if set(y.index) != set(sorted_index):
            raise RuntimeError(
                "y_sorted_for_pool: y.index と sorted_index が set 等価でない "
                "(部分集合・欠落・review HIGH#2)"
            )
        if len(y.index) != len(sorted_index):
            raise RuntimeError(
                "y_sorted_for_pool: y.index と sorted_index の長さが不一致 (review HIGH#2)"
            )
    return y.reindex(sorted_index)


# ---------------------------------------------------------------------------
# _split_train_eval_tail — review Cross-Plan #8: eval は train 末尾に収まる
# ---------------------------------------------------------------------------
def _split_train_eval_tail(
    train_df: pd.DataFrame,
    *,
    eval_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """train slice を race_key 単位・時系列順で (train_core, train_tail) に分割する（D-04）。

    train 全体を ``race_start_datetime`` 昇順で race_key 単位に並べ、末尾 ``eval_fraction``
    分を eval set 用 ``train_tail``・残りを ``train_core`` とする。

    戻り値の race_key 集合は train 全体に含まれるが、train_core と train_tail は disjoint。
    eval が train 全体の末尾から切られるため ``max(train_tail.race_date) <= max(train_df.race_date)``
    は常に成立する（``assert_eval_disjoint`` の ``eval_max_date <= train_core_max_date`` guard は
    実行時に別途検証される）。
    """
    if not 0.0 < eval_fraction < 1.0:
        raise ValueError(
            f"_split_train_eval_tail: eval_fraction は (0,1) 区間であるべき (got {eval_fraction})"
        )
    if "race_start_datetime" not in train_df.columns:
        raise ValueError(
            "_split_train_eval_tail: race_start_datetime 列が無い (時系列 sort 不可・D-04)"
        )

    # race_key 単位で時系列順に並べ、末尾 eval_fraction を切る
    key_col = "race_key" if "race_key" in train_df.columns else "race_start_datetime"
    race_keys_sorted = (
        train_df[["race_start_datetime", key_col]]
        .drop_duplicates()
        .sort_values(["race_start_datetime", key_col], kind="mergesort")
        .reset_index(drop=True)
    )
    n_total_races = len(race_keys_sorted)
    n_tail = max(1, int(round(n_total_races * eval_fraction)))
    n_core = n_total_races - n_tail
    if n_core < 1:
        raise ValueError(
            "_split_train_eval_tail: train_core が空になる (train_df が小さすぎる・D-04)"
        )

    core_keys = set(race_keys_sorted[key_col].iloc[:n_core])
    tail_keys = set(race_keys_sorted[key_col].iloc[n_core:])
    # core と tail の race_key は disjoint であることを保証
    overlap = core_keys & tail_keys
    if overlap:
        raise ValueError(
            f"_split_train_eval_tail: core と tail の race_key が disjoint でない "
            f"(overlap_count={len(overlap)} sample={sorted(overlap)[:3]})"
        )

    train_core = train_df[train_df[key_col].isin(core_keys)].copy()
    train_tail = train_df[train_df[key_col].isin(tail_keys)].copy()
    return train_core, train_tail


# ---------------------------------------------------------------------------
# assert_eval_disjoint — review Cross-Plan #8 拡張
# ---------------------------------------------------------------------------
def assert_eval_disjoint(
    eval_race_keys: set[str] | list[str] | None,
    calib_race_keys: set[str] | list[str] | None,
    test_race_keys: set[str] | list[str] | None,
    *,
    train_core_max_date: pd.Timestamp | None = None,
    eval_max_date: pd.Timestamp | None = None,
) -> None:
    """early stopping eval set が calib/test と完全に disjoint であることを検証する
    （Pitfall 5 / D-04 / review Cross-Plan #8 / T-04-16）。

    検証内容（違反時 ``raise ValueError``）:
      1. eval / calib / test の正準 race_key が pairwise disjoint（3組）
      2. ``train_core_max_date`` と ``eval_max_date`` が指定された場合
         ``eval_max_date <= train_core_max_date``（eval が train 全体に収まる）

    **``train_core_max_date`` の意味（review Cross-Plan #8・Plan の意図を正確に実装）:**

    Plan action で ``train_core_max_date`` と命名したが・実際の guard semantics は
    「eval が train slice 全体の max date を超えない」である。eval は train slice の時系列末尾から
    切られるため ``max(eval) <= max(train)`` は常に成立すべき・これを超える場合は eval が
    train 外（calib/test 領域）に食い込んでいる = leak。呼出側は train slice **全体**の max date
    を渡すこと（train_core と train_tail を合わせた train 全体の max）。

    引数が ``None`` の場合はその検査を skip する（呼出側が任意の検査だけ実行可能）。
    """
    eval_keys = set(eval_race_keys) if eval_race_keys is not None else None
    calib_keys = set(calib_race_keys) if calib_race_keys is not None else None
    test_keys = set(test_race_keys) if test_race_keys is not None else None

    # pairwise disjoint（3 組）
    pairs: list[tuple[str, set[str] | None, str, set[str] | None]] = [
        ("eval", eval_keys, "calib", calib_keys),
        ("eval", eval_keys, "test", test_keys),
        ("calib", calib_keys, "test", test_keys),
    ]
    for a_name, a_keys, b_name, b_keys in pairs:
        if a_keys is None or b_keys is None:
            continue
        overlap = a_keys & b_keys
        if overlap:
            sample = sorted(overlap)[:3]
            raise ValueError(
                f"assert_eval_disjoint: {a_name} と {b_name} の正準 race_key が disjoint でない "
                f"(Pitfall 5 / D-04 / review Cross-Plan #8 / T-04-16): "
                f"overlap_count={len(overlap)} sample={sample}"
            )

    # eval_max_date <= train_max_date（review Cross-Plan #8・train 全体の max を超えない）
    # train_core_max_date パラメータ名は Plan の命名を踏襲・semantics は train 全体 max
    if train_core_max_date is not None and eval_max_date is not None:
        eval_max_ts = pd.Timestamp(eval_max_date)
        train_max_ts = pd.Timestamp(train_core_max_date)
        if eval_max_ts > train_max_ts:
            raise ValueError(
                "assert_eval_disjoint: eval_max_date が train max date を超えている "
                f"(review Cross-Plan #8 / T-04-16): "
                f"eval_max_date={eval_max_date} train_max_date={train_core_max_date}"
            )


# ---------------------------------------------------------------------------
# align_predictions — review HIGH#2 + Cycle 2 NEW-2: 厳密置換 guard
# ---------------------------------------------------------------------------
def align_predictions(
    pred_series: pd.Series | np.ndarray,
    sorted_index: pd.Index,
    original_index: pd.Index,
) -> pd.Series:
    """CatBoost sort 済み Pool の予測を元の行順序に復元する（review HIGH#2 / Cycle 2 NEW-2）。

    ``pred_series`` の index は ``sorted_index``（``_prepare_catboost_pool`` の sort 後 index）。
    ``original_index`` は元の feature_df index。``reindex(original_index)`` で元順序に戻す。

    **Cycle 2 NEW-2: 厳密置換 guard（5 条件・``RuntimeError``・reindex silent NaN/dup/drop 防止）:**

    reindex 前に次の 5 条件を全て検証する（違反は ``RuntimeError``）:
      (a) ``sorted_index.is_unique`` と ``original_index.is_unique``
          （重複 index は CatBoost Pool が行を黙示落とした兆候）
      (b) ``set(sorted_index) == set(original_index)``
          （部分集合の場合 silent 欠落）
      (c) ``len(sorted_index) == len(original_index)``
      (d) ``len(pred_series) == len(sorted_index)``
          （予測長が Pool 行数と不一致）
      (e) reindex 後 ``not aligned.isna().any()``
          （reindex が欠落 index に silent NaN を生成した場合）

    全て通過した後、戻り値の index が ``original_index`` と完全一致することを assert する
    （不一致も ``RuntimeError``・silent wrong-horse prediction 防止）。
    """
    pred = (
        pd.Series(pred_series, index=sorted_index)
        if not isinstance(pred_series, pd.Series)
        else pred_series
    )

    # (a) is_unique ×2（重複 index は CatBoost Pool が行を落とした兆候）
    if not sorted_index.is_unique:
        dup_count = int(sorted_index.duplicated().sum())
        raise RuntimeError(
            f"align_predictions: sorted_index が unique でない (dup_count={dup_count}・"
            "CatBoost Pool が行を黙示落とした兆候・Cycle 2 NEW-2 / review HIGH#2)"
        )
    if not original_index.is_unique:
        dup_count = int(original_index.duplicated().sum())
        raise RuntimeError(
            f"align_predictions: original_index が unique でない (dup_count={dup_count}・"
            "Cycle 2 NEW-2 / review HIGH#2)"
        )

    # (b) set 等価（部分集合の場合 silent 欠落）
    if set(sorted_index) != set(original_index):
        only_sorted = set(sorted_index) - set(original_index)
        only_orig = set(original_index) - set(sorted_index)
        raise RuntimeError(
            "align_predictions: sorted_index と original_index が set 等価でない "
            "(部分集合・silent 欠落・Cycle 2 NEW-2 / review HIGH#2): "
            f"only_in_sorted={len(only_sorted)} only_in_original={len(only_orig)}"
        )

    # (c) len 等価
    if len(sorted_index) != len(original_index):
        raise RuntimeError(
            "align_predictions: sorted_index と original_index の長さが不一致 "
            f"(len_sorted={len(sorted_index)} len_original={len(original_index)}・"
            "Cycle 2 NEW-2 / review HIGH#2)"
        )

    # (d) pred 長と sorted_index 長が一致
    if len(pred) != len(sorted_index):
        raise RuntimeError(
            "align_predictions: pred_series の長さが sorted_index と不一致 "
            f"(len_pred={len(pred)} len_sorted={len(sorted_index)}・"
            "予測長が Pool 行数と不一致・Cycle 2 NEW-2 / review HIGH#2)"
        )

    # reindex で元順序に復元
    aligned = pd.Series(pred.values, index=sorted_index).reindex(original_index)

    # (e) reindex 後 NaN 無し（silent NaN 生成検出）
    if aligned.isna().any():
        n_nan = int(aligned.isna().sum())
        raise RuntimeError(
            f"align_predictions: reindex が {n_nan} 件の silent NaN を生成した "
            "(sorted_index に無い original_index 要素があった・Cycle 2 NEW-2 / review HIGH#2)"
        )

    # 戻り値の index が original_index と完全一致
    if not aligned.index.equals(original_index):
        raise RuntimeError(
            "align_predictions: 戻り値の index が original_index と完全一致しない "
            "(silent wrong-horse prediction 防止・review HIGH#2 / T-04-15b)"
        )

    return aligned


# ---------------------------------------------------------------------------
# train_lightgbm — review HIGH#2: X/y index 整合 assert
# ---------------------------------------------------------------------------
def train_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    X_eval: pd.DataFrame | None = None,
    y_eval: pd.Series | None = None,
    eval_race_keys: set[str] | list[str] | None = None,
    calib_race_keys: set[str] | list[str] | None = None,
    test_race_keys: set[str] | list[str] | None = None,
    train_core_max_date: pd.Timestamp | None = None,
    eval_max_date: pd.Timestamp | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """LightGBM を native categorical（Fisher 分割・target encoding 禁止）で学習する（SC#3 / §14.3）。

    Parameters
    ----------
    X_train, y_train : 学習 slice。``X_train.index.equals(y_train.index)`` を
        ``raise ValueError`` で assert（review HIGH#2・silent row mismatch 防止）。
    X_eval, y_eval : early stopping eval slice（train 末尾から切る・D-04）。両方 None の場合は
        early_stopping を無効化して ``n_estimators=N_ESTIMATORS`` まで学習する。
    eval_race_keys / calib_race_keys / test_race_keys : ``assert_eval_disjoint`` で pairwise
        disjoint を検証（review Cross-Plan #8 / T-04-16）。
    train_core_max_date / eval_max_date : ``assert_eval_disjoint`` で
        ``eval_max_date <= train_core_max_date`` を検証（review Cross-Plan #8）。
    params : ``LGB_INIT_PARAMS`` に merge する追加 param。

    Returns
    -------
    LGBMClassifier
        ``.fit()`` 済み estimator。``src.model.calibrator.calibrate_model`` へ渡す。
    """
    import lightgbm as lgb

    # review HIGH#2: X/y 行整列 assert
    if not X_train.index.equals(y_train.index):
        raise ValueError(
            "train_lightgbm: X_train.index と y_train.index が一致しない "
            "(review HIGH#2・silent wrong-horse prediction 防止)"
        )

    # eval set 分離 guard（review Cross-Plan #8 / T-04-16）
    assert_eval_disjoint(
        eval_race_keys,
        calib_race_keys,
        test_race_keys,
        train_core_max_date=train_core_max_date,
        eval_max_date=eval_max_date,
    )

    # categorical 前処理（非負 code 保証・__MISSING__ sentinel・review MEDIUM: _code も categorical）
    # train / eval を一貫した categorical dtype 化（categories 完全一致を保証）
    X_train_prep, X_eval_prep = _prepare_lightgbm_train_eval(X_train, X_eval)
    # categorical_feature で明示（_code 列含む・review HIGH#6 と並行して LightGBM も categorical 扱い）
    cat_feature_list = [c for c in ALL_CAT_COLS if c in X_train_prep.columns]

    merged_params = dict(LGB_INIT_PARAMS)
    if params:
        merged_params.update(params)

    model = lgb.LGBMClassifier(n_estimators=N_ESTIMATORS, **merged_params)

    if X_eval_prep is not None and y_eval is not None:
        if not X_eval.index.equals(y_eval.index):
            raise ValueError(
                "train_lightgbm: X_eval.index と y_eval.index が一致しない (review HIGH#2)"
            )
        model.fit(
            X_train_prep,
            y_train,
            categorical_feature=cat_feature_list,
            eval_set=[(X_eval_prep, y_eval)],
            eval_metric="binary_logloss",
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
    else:
        model.fit(
            X_train_prep,
            y_train,
            categorical_feature=cat_feature_list,
        )
    return model


# ---------------------------------------------------------------------------
# train_catboost — review HIGH#2 + HIGH#6
# ---------------------------------------------------------------------------
def train_catboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    X_eval: pd.DataFrame | None = None,
    y_eval: pd.Series | None = None,
    eval_race_keys: set[str] | list[str] | None = None,
    calib_race_keys: set[str] | list[str] | None = None,
    test_race_keys: set[str] | list[str] | None = None,
    train_core_max_date: pd.Timestamp | None = None,
    eval_max_date: pd.Timestamp | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[Any, pd.Index]:
    """CatBoost を ``has_time=True`` + ``cat_features``（_code 列含む）で学習する（SC#3 / §14.4）。

    Parameters
    ----------
    X_train, y_train : 学習 slice。``X_train.index.equals(y_train.index)`` を ``raise ValueError``
        で assert（review HIGH#2）。``race_start_datetime`` 列が必須（Pool sort・Pitfall 2）。
    X_eval, y_eval : early stopping eval slice（train 末尾から切る・D-04）。
    eval_race_keys / calib_race_keys / test_race_keys / train_core_max_date / eval_max_date :
        ``assert_eval_disjoint`` で検証（review Cross-Plan #8 / T-04-16）。
    params : ``CB_INIT_PARAMS`` に merge する追加 param。

    Returns
    -------
    tuple[CatBoostClassifier, pd.Index]
        ``(fitted_model, sorted_index)``。``sorted_index`` は ``_prepare_catboost_pool`` が返した
        sort 後 index。予測パスは ``align_predictions`` に ``sorted_index`` を渡して元の行順序に
        復元する（review HIGH#2 / T-04-15b）。
    """
    from catboost import CatBoostClassifier

    # review HIGH#2: X/y 行整列 assert
    if not X_train.index.equals(y_train.index):
        raise ValueError(
            "train_catboost: X_train.index と y_train.index が一致しない "
            "(review HIGH#2・silent wrong-horse prediction 防止)"
        )

    # eval set 分離 guard（review Cross-Plan #8 / T-04-16）
    assert_eval_disjoint(
        eval_race_keys,
        calib_race_keys,
        test_race_keys,
        train_core_max_date=train_core_max_date,
        eval_max_date=eval_max_date,
    )

    merged_params = dict(CB_INIT_PARAMS)
    if params:
        merged_params.update(params)

    # train Pool（sort 済み・cat_features に _code 列含む・review HIGH#6 / Pitfall 2）
    train_pool, sorted_index = _prepare_catboost_pool(X_train, y_train, sort=True)

    model = CatBoostClassifier(**merged_params)

    if X_eval is not None and y_eval is not None:
        if not X_eval.index.equals(y_eval.index):
            raise ValueError(
                "train_catboost: X_eval.index と y_eval.index が一致しない (review HIGH#2)"
            )
        eval_pool, _ = _prepare_catboost_pool(X_eval, y_eval, sort=True)
        model.fit(train_pool, eval_set=eval_pool)
    else:
        model.fit(train_pool)

    return model, sorted_index


# ---------------------------------------------------------------------------
# _build_rare_category_synthetic — review HIGH#3: 高基数 _code 列も含む
# ---------------------------------------------------------------------------
def _build_rare_category_synthetic(
    n: int = 2000,
    *,
    rare_rate: float = 0.05,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """SC#3 leak diagnostic 用合成データを構築する（review HIGH#3: 低基数 RARE_X + 高基数 _code）。

    構成:
      (a) 低基数希少カテゴリ: ``sexcd`` の一部に ``'RARE_X'`` を割当（``rare_rate`` 割合）。
          その行の ``fukusho_hit_validated`` を全て ``1`` に設定。残りは positive rate 0.21
          （Bernoulli・target encoding 混入なら test の RARE_X 行予測が 1.0 近くになる）。
      (b) 高基数 ``_code`` 列: ``jockey_id_code`` で train-only の希少 ID（``code=99991``・
          train の先頭数行のみ）を作成。``test`` には出現させない（test-unseen）。この ID の
          label も train では ``1`` に設定（target encoding 風リークがあれば test でこの ID に
          対する予測が 1.0 近くになるが・``__UNSEEN__`` に縮むべき）。

    ``race_key`` は時系列順・``race_start_datetime`` は 2020-01-01 から1日間隔で割当。
    戻り値は ``make_race_key`` 互換の ``race_key`` 列を持つ。
    """
    rng = np.random.default_rng(seed)

    rows = []
    start_dt = pd.Timestamp("2020-01-01")
    # 1 レース 8 頭立て・n 行 = n/8 レース
    races = max(1, n // 8)
    row_idx = 0
    for race_i in range(races):
        race_dt = start_dt + pd.Timedelta(days=race_i)
        # 正準 race_key = year-jyocd-kaiji-nichiji-racenum（race_i を一意に分散）
        # 10 jyocd × 8 kaiji × 12 nichiji = 960 通りで race_i を一意にエンコード
        jyocd = (race_i % 10) + 1          # 1..10
        kaiji = ((race_i // 10) % 8) + 1   # 1..8
        nichiji = ((race_i // 80) % 12) + 1  # 1..12
        racenum = jyocd                    # 1..10（race_key 一意性は jyocd/kaiji/nichiji で保証）
        race_key = f"2020-{jyocd:02d}-{kaiji:02d}-{nichiji:02d}-{racenum}"
        for umaban in range(1, 9):
            # 低基数希少カテゴリ: rare_rate の確率で RARE_X を割当
            # RARE_X の行の label を全て 1 に設定（train で予測的）。test の RARE_X 行は
            # 時系列後半に振り分けられ・train の分布を学習した native categorical は高い
            # 予測を出すが・これは値ベースの Fisher 分割によるもの（target encoding 非混入）。
            # inject_intentional_leak_feature が RARE_X の train target mean (=1.0) を
            # 直接 feature として埋め込み・test RARE_X にも同値を適用する対照実験で
            # leak diagnostic が false-pass でないことを実証する (review HIGH#3)。
            is_rare = rng.random() < rare_rate
            sexcd = "RARE_X" if is_rare else str(int(rng.choice([1, 2, 3])))
            # label: RARE_X は常に 1（train で予測的）・それ以外は positive rate 0.21
            if is_rare:
                label = 1
            else:
                label = int(rng.random() < 0.21)

            # 高基数 _code 列: train-only の希少 ID を race_i=0..3 の数行に割当
            # （test は時系列後半なので出現しない）
            is_rare_id = race_i < 4 and umaban <= 2
            jockey_id_code = 99991 if is_rare_id else int(rng.integers(0, 350))
            if is_rare_id:
                label = 1  # train-only 希少 ID の label も 1

            rows.append({
                "race_start_datetime": race_dt,
                "race_key": race_key,
                "race_date": race_dt.normalize(),
                "year": 2020,
                "jyocd": "05",
                "kaiji": (race_i % 12) + 1,
                "nichiji": f"{race_i % 8 + 1:02d}",
                "racenum": (race_i % 12) + 1,
                "umaban": umaban,
                "kettonum": int(rng.integers(1, 100_000)),
                "sexcd": sexcd,
                "class_code_normalized": str(int(rng.choice([703, 701, 5, 10, 999]))),
                "estimated_running_style": str(int(rng.choice([1, 2, 3, 4, 5]))),
                "rolling_jyocd_mode_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                "rolling_jyocd_latest_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                "jockey_id_code": jockey_id_code,
                "trainer_id_code": int(rng.integers(0, 300)),
                "sire_id_code": int(rng.integers(0, 5000)),
                "bms_id_code": int(rng.integers(0, 5000)),
                "horse_id_code": int(rng.integers(0, 50_000)),
                # numeric feature（学習に必要）
                "barei": int(rng.integers(2, 9)),
                "futan": int(rng.integers(48, 58)),
                "umaban": umaban,
                "wakuban": int(rng.integers(1, 9)),
                "fukusho_hit_validated": label,
            })
            row_idx += 1
            if row_idx >= n:
                break
        if row_idx >= n:
            break

    df = pd.DataFrame(rows)
    # 時系列順に sort して index を reset
    df = df.sort_values(["race_start_datetime", "race_key", "umaban"], kind="mergesort").reset_index(drop=True)
    # jockey_id_code を int32 化（frozen map と同一型）
    for col in HIGH_CARD_CODE_COLS:
        df[col] = df[col].astype("int32")
    return df


# ---------------------------------------------------------------------------
# _build_intentional_leak_control — review HIGH#3: 意図的リークで DEMONSTRABLY fail を実証
# ---------------------------------------------------------------------------
def _build_intentional_leak_control() -> tuple[str, float]:
    """SC#3 leak diagnostic が false-pass でないことを実証するための意図的リーク制御
    （review HIGH#3: DEMONSTRABLY fail）。

    ``inject_intentional_leak_feature`` と対で使用する。``inject_intentional_leak_feature``
    が**target encoding 風リーク feature**を注入する: ``sexcd == 'RARE_X'`` の行に ``1.0``
    （train の RARE_X label 平均）を・それ以外に ``0.21``（global positive rate）を埋め込んだ
    numeric feature 列を追加する。これは target encoding が時系列 panel データで引き起こす
    予測シフト典型例（§14.3 ban 根拠）。本来 test の RARE_X 行は train の label 情報を持てない
    が・target encoding 風 feature は train と test の両方に同一の RARE_X 値を埋め込むため、
    学習器がこれを強力な予測子として獲得し test 予測が threshold (0.9) を超える。

    native categorical でも値ベースの分割で RARE_X を学習するため予測が上がるが・本注入は
    ``inject_intentional_leak_feature`` で**numeric 直接入力**する経路を開くことで・より極端な
    予測シフト（threshold 0.9 超過）を実現し leak diagnostic がこの手のリークを検出できる
    （false-pass でない）ことを実証する。

    Returns
    -------
    tuple[leak_feature_name, threshold]
        ``leak_feature_name``: 注入する leak feature 名（``"leak_rare_x_mean"``）。
        ``threshold``: リーク注入時に test の RARE_X 行予測が超えるべき閾値（``0.9``）。
    """
    return ("leak_rare_x_mean", 0.9)


def inject_intentional_leak_feature(
    df: pd.DataFrame,
    *,
    leak_feature_name: str = "leak_rare_x_mean",
    label_col: str = "fukusho_hit_validated",
) -> pd.DataFrame:
    """SC#3 leak diagnostic の意図的リーク制御（review HIGH#3: DEMONSTRABLY fail）。

    ``sexcd == 'RARE_X'`` の行に ``1.0``（train の RARE_X label 平均）を・それ以外に ``0.21``
    （global positive rate）を埋め込んだ numeric feature 列を追加する。これは target encoding
    風リーク（train の label 平均を直接 numeric feature に埋め込む）であり、本来 RARE_X の
    test 行は train の label 情報を持てない。train と test の両方に同一値が入るため学習器が
    これを強力な予測子として獲得し test の RARE_X 行予測が threshold (0.9) を超える。

    本 feature を学習させると leak diagnostic がこの手のリークを検出できる（false-pass でない）
    ことが実証される。
    """
    out = df.copy()
    # RARE_X 行に 1.0（train label 平均）・それ以外に 0.21（global mean）
    out[leak_feature_name] = np.where(out["sexcd"] == "RARE_X", 1.0, 0.21)
    return out
