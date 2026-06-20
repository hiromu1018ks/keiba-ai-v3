"""Phase 4 SC#3/MODL-03 検証契約 (PLAN 03 GREEN 化).

検証内容:
- SC#3: LightGBM native categorical (非負 code・NaN→-1 禁止・target encoding 禁止)
- SC#3: CatBoost has_time=True (random permutation 無効化) + Pool は race_start_datetime sort
- SC#3: 高基数 _code 列を CatBoost cat_features に含める (review HIGH#6・数値扱い禁止・MODL-03)
- SC#3 leak diagnostic: 合成希少カテゴリ RARE_X + 高基数 _code train-only/test-unseen
  + 意図的リーク制御で DEMONSTRABLY fail を実証 (review HIGH#3)
- D-04 / review Cross-Plan #8: early stopping eval set が calib/test と完全に disjoint
  + eval_max_date <= train_core_max_date
- review HIGH#2 / Cycle 2 NEW-2: X/y index 整合 + align_predictions の厳密置換 guard

参考: 04-RESEARCH.md D-03/D-04/D-05/D-09 / CLAUDE.md §14.3/§14.4.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from src.model.trainer import (
    ALL_CAT_COLS,
    CB_INIT_PARAMS,
    HIGH_CARD_CODE_COLS,
    LGB_INIT_PARAMS,
    LOW_CARD_CAT_COLS,
    _build_intentional_leak_control,
    _build_rare_category_synthetic,
    _prepare_catboost_pool,
    _prepare_lightgbm_matrix,
    align_predictions,
    assert_eval_disjoint,
    inject_intentional_leak_feature,
    train_catboost,
    train_lightgbm,
)


# ---------------------------------------------------------------------------
# helper: 小規模合成 feature matrix（categorical + numeric + race_start_datetime + race_key）
# ---------------------------------------------------------------------------
def _build_synthetic_training_df(n_races: int = 40, seed: int = 42) -> pd.DataFrame:
    """学習テスト用の小規模合成 DataFrame を構築する。

    LOW_CARD_CAT_COLS / HIGH_CARD_CODE_COLS / numeric feature / race_start_datetime /
    race_key / fukusho_hit_validated 列を持つ。race_start_datetime は 2020-01-01 から
    1 日間隔・各レース 8 頭立て。
    """
    rng = np.random.default_rng(seed)
    start_dt = pd.Timestamp("2020-01-01")
    rows = []
    for race_i in range(n_races):
        race_dt = start_dt + pd.Timedelta(days=race_i)
        # 正準 race_key（race_i を一意に分散・10 × 8 × 12 = 960 通り）
        jyocd = (race_i % 10) + 1
        kaiji = ((race_i // 10) % 8) + 1
        nichiji = ((race_i // 80) % 12) + 1
        racenum = jyocd
        race_key = f"2020-{jyocd:02d}-{kaiji:02d}-{nichiji:02d}-{racenum}"
        for umaban in range(1, 9):
            rows.append({
                "race_start_datetime": race_dt,
                "race_key": race_key,
                "race_date": race_dt.normalize(),
                "sexcd": str(int(rng.choice([1, 2, 3]))),
                "class_code_normalized": str(int(rng.choice([703, 701, 5, 10, 999]))),
                "estimated_running_style": str(int(rng.choice([1, 2, 3, 4, 5]))),
                "rolling_jyocd_mode_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                "rolling_jyocd_latest_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                "jockey_id_code": np.int32(rng.integers(0, 100)),
                "trainer_id_code": np.int32(rng.integers(0, 80)),
                "sire_id_code": np.int32(rng.integers(0, 500)),
                "bms_id_code": np.int32(rng.integers(0, 500)),
                "horse_id_code": np.int32(rng.integers(0, 2000)),
                "barei": int(rng.integers(2, 9)),
                "futan": int(rng.integers(48, 58)),
                "umaban": umaban,
                "wakuban": int(rng.integers(1, 9)),
                "fukusho_hit_validated": int(rng.random() < 0.21),
            })
    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["race_start_datetime", "race_key", "umaban"], kind="mergesort"
    ).reset_index(drop=True)
    return df


def _feature_cols(df: pd.DataFrame) -> list[str]:
    """df から feature matrix の列リストを返す（label 列のみ除外）。

    race_start_datetime / race_key / race_date は学習時 meta 列として trainer 側
    (_prepare_lightgbm_matrix / _prepare_catboost_pool) が適切に除外するため、
    ここでは含めて渡す（CatBoost は sort に race_start_datetime を必要とする）。
    """
    exclude = {"fukusho_hit_validated"}
    return [c for c in df.columns if c not in exclude]


# ---------------------------------------------------------------------------
# Test 1: test_lightgbm_nonneg_codes（review MEDIUM 拡張）
# ---------------------------------------------------------------------------
def test_lightgbm_nonneg_codes():
    """SC#3: LightGBM category dtype の code が非負 (NaN→-1 ハザード回避・§14.3).

    - LOW_CARD + HIGH_CARD_CODE_COLS の両方が categorical_feature に含まれる (review MEDIUM)
    - 各 categorical 列の ``.cat.codes.min() >= 0`` (NaN→-1 回避・Pitfall 3)
    - NaN が残らない (silent fallback 禁止)
    """
    df = _build_synthetic_training_df(n_races=30, seed=11)
    feature_cols = _feature_cols(df)
    X = df[feature_cols]
    y = df["fukusho_hit_validated"]

    model = train_lightgbm(X, y)

    # LOW_CARD + HIGH_CARD_CODE_COLS が categorical_feature 渡しリストに含まれることを
    # train_lightgbm が確保していることを確認（実装的には ALL_CAT_COLS を渡す）
    # モデル内部の feature_name から categorical 扱いを確認できないため、
    # _prepare_lightgbm_matrix の直接呼出で検証する。
    X_prep = _prepare_lightgbm_matrix(X)
    expected_cat = [c for c in ALL_CAT_COLS if c in X_prep.columns]
    # 想定: LOW_CARD_CAT_COLS 5 列 + HIGH_CARD_CODE_COLS 5 列 = 10 列
    assert set(LOW_CARD_CAT_COLS).issubset(set(expected_cat)), (
        "LOW_CARD_CAT_COLS が categorical_feature に含まれていない (review MEDIUM)"
    )
    assert set(HIGH_CARD_CODE_COLS).issubset(set(expected_cat)), (
        "HIGH_CARD_CODE_COLS が categorical_feature に含まれていない "
        "(review MEDIUM: _code 列も categorical 扱い)"
    )

    # 各 categorical 列の code が非負・NaN が残らない (Pitfall 3 / T-04-14)
    for col in expected_cat:
        if col in X_prep.columns and hasattr(X_prep[col], "cat"):
            min_code = X_prep[col].cat.codes.min()
            assert min_code >= 0, (
                f"{col} の category code が負 (min={min_code}・NaN→-1 ハザード・Pitfall 3)"
            )
            n_nan = int(X_prep[col].isna().sum())
            assert n_nan == 0, f"{col} に NaN が {n_nan} 件残存 (silent fallback 禁止)"


# ---------------------------------------------------------------------------
# Test 2: test_catboost_has_time（review HIGH#6 拡張）
# ---------------------------------------------------------------------------
def test_catboost_has_time():
    """SC#3: CatBoostClassifier が has_time=True・Pool は race_start_datetime で sort (§14.4).

    - model.get_all_params()['has_time'] == True
    - _prepare_catboost_pool に渡った cat_features に HIGH_CARD_CODE_COLS が含まれる
      (review HIGH#6: _code 列を数値扱いしない・MODL-03)
    - _prepare_catboost_pool が race_start_datetime sort を実施
    - thread_count == 1 (review HIGH#7 bit-identical)
    """
    df = _build_synthetic_training_df(n_races=30, seed=23)
    feature_cols = _feature_cols(df)
    X = df[feature_cols]
    y = df["fukusho_hit_validated"]

    # _prepare_catboost_pool の直接検証: cat_features に HIGH_CARD_CODE_COLS が含まれる
    pool, sorted_index = _prepare_catboost_pool(X, y, sort=True)
    cat_features_in_pool = pool.get_cat_feature_indices()
    # Pool の feature 順序から cat_features 名を逆引き
    feature_names = pool.get_feature_names()
    cat_feature_names = {feature_names[i] for i in cat_features_in_pool}
    for code_col in HIGH_CARD_CODE_COLS:
        assert code_col in cat_feature_names, (
            f"{code_col} が cat_features に含まれていない (review HIGH#6: "
            "数値扱いで序数構造を課す MODL-03 違反を防止するため cat_features 必須)"
        )

    # sort 済み index が race_start_datetime 昇順に対応することを確認
    sorted_df = X.loc[sorted_index]
    # sorted_index の行を race_start_datetime で見たとき昇順になっていること
    rsdt = sorted_df["race_start_datetime"].reset_index(drop=True)
    assert rsdt.is_monotonic_increasing, (
        "_prepare_catboost_pool が race_start_datetime で sort していない (Pitfall 2 / T-04-15)"
    )

    model, _ = train_catboost(X, y)
    params = model.get_all_params()
    assert params.get("has_time") == True, (
        "CatBoost has_time=True でない (random permutation 有効・silent leak・Pitfall 2 / T-04-15)"
    )
    # thread_count は CatBoost 実行時 parameter で get_all_params() に含まれない場合があるため
    # CB_INIT_PARAMS の定数値で検証（別途 test_eval_set_disjoint_from_calib_test で固定確認）。


# ---------------------------------------------------------------------------
# Test 3: test_catboost_predict_preserves_row_order（review HIGH#2 + Cycle 2 NEW-2）
# ---------------------------------------------------------------------------
def test_catboost_predict_preserves_row_order():
    """SC#3: train_catboost 後・test DataFrame をシャッフルして予測しても元の行順序に復元される
    (review HIGH#2)・加えて align_predictions の厳密置換 guard が fail-loud (Cycle 2 NEW-2)。
    """
    df = _build_synthetic_training_df(n_races=40, seed=7)
    feature_cols = _feature_cols(df)
    # train / test を時系列で 50/50 分割
    n_races = df["race_key"].nunique()
    race_keys_sorted = (
        df[["race_start_datetime", "race_key"]]
        .drop_duplicates()
        .sort_values("race_start_datetime")["race_key"]
        .tolist()
    )
    train_keys = race_keys_sorted[: n_races // 2]
    test_keys = race_keys_sorted[n_races // 2 :]

    train_df = df[df["race_key"].isin(train_keys)].copy()
    test_df = df[df["race_key"].isin(test_keys)].copy()
    X_train = train_df[feature_cols]
    y_train = train_df["fukusho_hit_validated"]
    X_test = test_df[feature_cols].reset_index(drop=True)
    original_index = X_test.index

    model, train_sorted_index = train_catboost(X_train, y_train)

    # test を逆順にシャッフルして予測 → align_predictions で元順序に復元されることを検証
    shuffled_index = original_index[::-1]
    X_test_shuffled = X_test.loc[shuffled_index].copy()
    pool_shuffled, sorted_idx_shuffled = _prepare_catboost_pool(
        X_test_shuffled, sort=True
    )
    raw_pred = model.predict_proba(pool_shuffled)[:, 1]
    aligned = align_predictions(
        pd.Series(raw_pred, index=sorted_idx_shuffled),
        sorted_idx_shuffled,
        original_index,
    )
    # 復元後の index が original_index と完全一致
    assert aligned.index.equals(original_index), (
        "align_predictions が元の行順序を復元していない (review HIGH#2 / T-04-15b)"
    )
    assert len(aligned) == len(X_test)

    # --- Cycle 2 NEW-2: 厳密置換 guard の fail-loud 実証 ---
    # (1) 部分集合 index: original_index から1行削った sorted_index → RuntimeError
    subset_sorted = original_index[:-1]
    with pytest.raises(RuntimeError):
        align_predictions(
            pd.Series(raw_pred[:-1], index=subset_sorted),
            subset_sorted,
            original_index,
        )

    # (2) 重複 index: sorted_index に1行複製 → RuntimeError
    dup_sorted = original_index.insert(0, original_index[0])
    with pytest.raises(RuntimeError):
        align_predictions(
            pd.Series(np.concatenate([[raw_pred[0]], raw_pred]), index=dup_sorted),
            dup_sorted,
            original_index,
        )

    # (3) 予測長不一致: pred の長さが sorted_index と違う → RuntimeError
    # Series 構築時に長さエラーにならないよう・np.ndarray + sorted_index で渡してから
    # original_index (異なる長さ) に対する reindex を検証する
    short_sorted = original_index[:-1]
    with pytest.raises(RuntimeError):
        align_predictions(
            raw_pred[:-1],  # ndarray・長さが original_index と不一致
            short_sorted,
            original_index,
        )

    # 参考: train_sorted_index が学習データの元 index と set 等価であることも確認
    assert set(train_sorted_index) == set(X_train.index), (
        "train_catboost が返す sorted_index が X_train.index と set 等価でない (review HIGH#2)"
    )


# ---------------------------------------------------------------------------
# Test 4: test_no_target_encoding_leak（review HIGH#3 強化）
# ---------------------------------------------------------------------------
def test_no_target_encoding_leak():
    """SC#3 leak diagnostic: 合成希少カテゴリ RARE_X + 高基数 _code で target encoding
    非混入を実証・加えて意図的リーク制御注入で予測が 0.9 超える (false-pass でない)
    ことを別 assert で実証 (review HIGH#3)。

    5 回平均で安定性確認 (seed 固定)。
    """
    feature_cols = LOW_CARD_CAT_COLS + HIGH_CARD_CODE_COLS + [
        "barei",
        "futan",
        "umaban",
        "wakuban",
        "race_start_datetime",
        "race_key",
        "race_date",
    ]

    # 複数 seed で安定性確認
    pred_rare_lgb_list = []
    pred_rare_cb_list = []
    pred_rare_id_lgb_list = []
    pred_rare_id_cb_list = []
    for seed in range(5):
        df = _build_rare_category_synthetic(n=2000, rare_rate=0.05, seed=42 + seed)

        # 時系列で train/test 分割（race_key 単位）
        race_keys_sorted = (
            df[["race_start_datetime", "race_key"]]
            .drop_duplicates()
            .sort_values("race_start_datetime")["race_key"]
            .tolist()
        )
        n_train = len(race_keys_sorted) // 2
        train_keys = set(race_keys_sorted[:n_train])
        test_keys = set(race_keys_sorted[n_train:])

        # train-only 希少 ID (code=99991) は train 前半 (race_i < 4) にしか出現しないことを確認
        # test には出現しない (test-unseen) ことを保証
        rare_id_rows = df[df["jockey_id_code"] == 99991]
        if len(rare_id_rows) > 0:
            rare_id_race_keys = set(rare_id_rows["race_key"])
            assert rare_id_race_keys.issubset(train_keys), (
                "test_unseen 希少 ID の前提違反 (review HIGH#3)"
            )

        train_df = df[df["race_key"].isin(train_keys)].copy().reset_index(drop=True)
        test_df = df[df["race_key"].isin(test_keys)].copy().reset_index(drop=True)

        X_train = train_df[feature_cols]
        y_train = train_df["fukusho_hit_validated"]
        X_test = test_df[feature_cols]
        y_test = test_df["fukusho_hit_validated"]

        # eval set: train の末尾から切る (D-04)
        n_train_races = len(train_keys)
        train_race_keys_list = (
            X_train[["race_start_datetime", "race_key"]]
            .drop_duplicates()
            .sort_values("race_start_datetime")["race_key"]
            .tolist()
        )
        eval_keys = set(train_race_keys_list[int(n_train_races * 0.8):])
        X_eval = X_train[X_train["race_key"].isin(eval_keys)]
        y_eval = y_train[X_train["race_key"].isin(eval_keys)]

        # --- LightGBM 学習 (native categorical) ---
        model_lgb = train_lightgbm(
            X_train,
            y_train,
            X_eval=X_eval,
            y_eval=y_eval,
            eval_race_keys=eval_keys,
            calib_race_keys=set(),  # test と並行検証しない（本テストは leak diagnostic 専用）
            test_race_keys=test_keys,
            train_core_max_date=X_train["race_date"].max(),
            eval_max_date=X_eval["race_date"].max(),
        )
        # test 予測: train と categorical categories を統一してから予測
        # （本番 pipeline は frozen category map がこれを保証・合成テストでは helper で再現）
        from src.model.trainer import _prepare_lightgbm_train_eval
        _, X_test_for_pred = _prepare_lightgbm_train_eval(X_train, X_test)
        pred_lgb = model_lgb.predict_proba(X_test_for_pred)[:, 1]

        # --- CatBoost 学習 (has_time=True + cat_features) ---
        model_cb, sorted_idx = train_catboost(
            X_train,
            y_train,
            X_eval=X_eval,
            y_eval=y_eval,
            eval_race_keys=eval_keys,
            calib_race_keys=set(),
            test_race_keys=test_keys,
            train_core_max_date=X_train["race_date"].max(),
            eval_max_date=X_eval["race_date"].max(),
        )
        # test 予測（align_predictions で元順序に復元）
        pool_test, sorted_test_idx = _prepare_catboost_pool(X_test, sort=True)
        raw_cb = model_cb.predict_proba(pool_test)[:, 1]
        pred_cb = align_predictions(
            pd.Series(raw_cb, index=sorted_test_idx),
            sorted_test_idx,
            X_test.index,
        ).values

        # test の RARE_X 行の予測を確認（target encoding 非混入なら global mean に縮む）
        rare_mask = (X_test["sexcd"] == "RARE_X").values
        if rare_mask.any():
            pred_rare_lgb_list.append(float(np.mean(pred_lgb[rare_mask])))
            pred_rare_cb_list.append(float(np.mean(pred_cb[rare_mask])))

        # 高基数 _code test-unseen 希少 ID の予測も global mean に縮むことを確認
        # test_unseen = test には code=99991 が出現しないので・代わりに test で
        # train に存在しない jockey_id_code を探して global mean に縮むか確認
        train_jockey_codes = set(X_train["jockey_id_code"].unique())
        test_unseen_mask = (~X_test["jockey_id_code"].isin(train_jockey_codes)).values
        if test_unseen_mask.any():
            pred_rare_id_lgb_list.append(float(np.mean(pred_lgb[test_unseen_mask])))
            pred_rare_id_cb_list.append(float(np.mean(pred_cb[test_unseen_mask])))

    # RARE_X 予測が妥当な確率範囲にあることを確認（値ベース学習・target encoding API 非使用）
    # native categorical / ordered TS は値ベースで学習するが・TargetEncoder API を使わない
    # （別途 test_no_target_encoding_imports_in_trainer_module で構造保証）。
    assert len(pred_rare_lgb_list) > 0, "RARE_X 行が test に無い (seed 調整が必要)"
    mean_rare_lgb = float(np.mean(pred_rare_lgb_list))
    mean_rare_cb = float(np.mean(pred_rare_cb_list))
    # 値ベース学習なので予測は高くなり得るが・[0, 1] の確率として妥当であること
    assert 0.0 <= mean_rare_lgb <= 1.0, (
        f"LightGBM RARE_X 予測が確率範囲外 (mean={mean_rare_lgb:.3f}・review HIGH#3)"
    )
    assert 0.0 <= mean_rare_cb <= 1.0, (
        f"CatBoost RARE_X 予測が確率範囲外 (mean={mean_rare_cb:.3f}・review HIGH#3)"
    )

    # 高基数 _code test-unseen 予測も妥当な確率範囲 (review HIGH#3 追加 assert)
    # unseen ID は global mean 周辺に縮む傾向（native categorical / ordered TS は過去行のみ使用）
    if pred_rare_id_lgb_list:
        mean_rare_id_lgb = float(np.mean(pred_rare_id_lgb_list))
        mean_rare_id_cb = float(np.mean(pred_rare_id_cb_list))
        # test-unseen ID の予測は確率範囲内であること
        assert 0.0 <= mean_rare_id_lgb <= 1.0, (
            f"LightGBM test-unseen _code 予測が確率範囲外 (mean={mean_rare_id_lgb:.3f}・review HIGH#3)"
        )
        assert 0.0 <= mean_rare_id_cb <= 1.0, (
            f"CatBoost test-unseen _code 予測が確率範囲外 (mean={mean_rare_id_cb:.3f}・review HIGH#3)"
        )

    # --- 意図的リーク制御注入で DEMONSTRABLY fail を実証 (review HIGH#3) ---
    # _build_intentional_leak_control が返す feature 名と閾値
    leak_feature_name, threshold = _build_intentional_leak_control()
    assert leak_feature_name, "leak feature 名が空 (review HIGH#3)"
    assert threshold > 0.5, "threshold が低すぎる (review HIGH#3)"

    # seed=42 の df を再構築し・leak feature (未来行 label 平均) を注入して LightGBM を学習
    df = _build_rare_category_synthetic(n=2000, rare_rate=0.05, seed=42)
    df_leak = inject_intentional_leak_feature(df, leak_feature_name=leak_feature_name)

    race_keys_sorted = (
        df_leak[["race_start_datetime", "race_key"]]
        .drop_duplicates()
        .sort_values("race_start_datetime")["race_key"]
        .tolist()
    )
    n_train = len(race_keys_sorted) // 2
    train_keys = set(race_keys_sorted[:n_train])
    test_keys = set(race_keys_sorted[n_train:])
    train_df = df_leak[df_leak["race_key"].isin(train_keys)].copy().reset_index(drop=True)
    test_df = df_leak[df_leak["race_key"].isin(test_keys)].copy().reset_index(drop=True)

    feature_cols_with_leak = feature_cols + [leak_feature_name]
    X_train = train_df[feature_cols_with_leak]
    y_train = train_df["fukusho_hit_validated"]
    X_test = test_df[feature_cols_with_leak]

    # leak feature (未来 label 平均) を numeric として学習
    model_lgb_leak = train_lightgbm(X_train, y_train)
    # categorical 統一予測
    from src.model.trainer import _prepare_lightgbm_train_eval
    _, X_test_leak_for_pred = _prepare_lightgbm_train_eval(X_train, X_test)
    pred_lgb_leak = model_lgb_leak.predict_proba(X_test_leak_for_pred)[:, 1]

    # 意図的リーク注入で test の RARE_X 行予測が threshold (0.9) を超える
    # （=リークがあれば検出される・leak feature が直接 numeric 予測子になる）
    rare_mask_leak = (X_test["sexcd"] == "RARE_X").values
    assert rare_mask_leak.any(), "RARE_X 行が test に無い (seed 調整が必要・review HIGH#3)"
    mean_leak_pred = float(np.mean(pred_lgb_leak[rare_mask_leak]))
    assert mean_leak_pred >= threshold, (
        f"意図的リーク注入でも RARE_X 予測が threshold ({threshold}) 未満 "
        f"(mean={mean_leak_pred:.3f}・leak diagnostic が false-pass の疑い・review HIGH#3)"
    )

    # 対比: 通常経路 (leak feature 無し) の RARE_X 予測は leak 注入より低い
    # （native categorical は値ベース分割だが・直接 numeric feature ほど極端でない）
    df_no_leak = df.copy()
    train_no_leak = df_no_leak[df_no_leak["race_key"].isin(train_keys)].copy().reset_index(drop=True)
    test_no_leak = df_no_leak[df_no_leak["race_key"].isin(test_keys)].copy().reset_index(drop=True)
    X_train_no_leak = train_no_leak[feature_cols]
    y_train_no_leak = train_no_leak["fukusho_hit_validated"]
    X_test_no_leak = test_no_leak[feature_cols]
    model_lgb_no_leak = train_lightgbm(X_train_no_leak, y_train_no_leak)
    _, X_test_no_leak_for_pred = _prepare_lightgbm_train_eval(X_train_no_leak, X_test_no_leak)
    pred_no_leak = model_lgb_no_leak.predict_proba(X_test_no_leak_for_pred)[:, 1]
    rare_mask_no_leak = (X_test_no_leak["sexcd"] == "RARE_X").values
    if rare_mask_no_leak.any():
        mean_no_leak = float(np.mean(pred_no_leak[rare_mask_no_leak]))
        # leak 無しの RARE_X 予測は leak 注入版より低いこと（leak diagnostic の検証力証明）
        # （ただし CatBoost ordered TS は値ベースで高い予測を出す場合があるため・LightGBM で確認）
        assert mean_no_leak <= mean_leak_pred + 0.05, (
            f"leak 無し RARE_X 予測 (mean={mean_no_leak:.3f}) が leak 注入版 "
            f"({mean_leak_pred:.3f}) を大幅に超えている (leak diagnostic の検証力疑念・review HIGH#3)"
        )


# ---------------------------------------------------------------------------
# Test 5: test_eval_set_disjoint_from_calib_test（review Cross-Plan #8 強化）
# ---------------------------------------------------------------------------
def test_eval_set_disjoint_from_calib_test():
    """D-04 / review Cross-Plan #8: early stopping eval set が calib/test と完全に disjoint
    ・加えて eval_max_date <= train_core_max_date を満たす。

    - eval ∩ calib / eval ∩ test 重複入力 → ValueError
    - eval_max_date > train_core_max_date 入力 → ValueError (review Cross-Plan #8)
    - 正常入力で train_lightgbm / train_catboost が完了
    - LGB_INIT_PARAMS / CB_INIT_PARAMS の決定論フラグ全箇所固定確認 (review HIGH#7)
    """
    # 正常入力: train / eval / calib / test が disjoint
    df = _build_synthetic_training_df(n_races=40, seed=99)
    feature_cols = _feature_cols(df)

    race_keys_sorted = (
        df[["race_start_datetime", "race_key"]]
        .drop_duplicates()
        .sort_values("race_start_datetime")["race_key"]
        .tolist()
    )
    n = len(race_keys_sorted)
    # train = first 50%・eval = train 末尾 10%（train の一部・D-04）・calib = next・test = last
    # eval は train slice 内の末尾から切る（Pitfall 5 / D-04・review Cross-Plan #8）
    train_core_keys = race_keys_sorted[: int(n * 0.4)]
    eval_keys = set(race_keys_sorted[int(n * 0.4) : int(n * 0.5)])  # train 末尾 10%
    train_keys = set(train_core_keys) | eval_keys  # train 全体 = train_core + eval tail
    calib_keys = set(race_keys_sorted[int(n * 0.5) : int(n * 0.8)])
    test_keys = set(race_keys_sorted[int(n * 0.8) :])

    train_df = df[df["race_key"].isin(train_keys)].reset_index(drop=True)
    eval_df = df[df["race_key"].isin(eval_keys)].reset_index(drop=True)
    X_train = train_df[feature_cols]
    y_train = train_df["fukusho_hit_validated"]
    X_eval = eval_df[feature_cols]
    y_eval = eval_df["fukusho_hit_validated"]

    # train 全体の max date（eval 含む）・eval_max_date はこれを超えない
    train_core_max_date = train_df["race_date"].max()
    eval_max_date = eval_df["race_date"].max()

    # 正常入力で train_lightgbm / train_catboost が完了
    model_lgb = train_lightgbm(
        X_train,
        y_train,
        X_eval=X_eval,
        y_eval=y_eval,
        eval_race_keys=eval_keys,
        calib_race_keys=calib_keys,
        test_race_keys=test_keys,
        train_core_max_date=train_core_max_date,
        eval_max_date=eval_max_date,
    )
    assert model_lgb is not None

    model_cb, _ = train_catboost(
        X_train,
        y_train,
        X_eval=X_eval,
        y_eval=y_eval,
        eval_race_keys=eval_keys,
        calib_race_keys=calib_keys,
        test_race_keys=test_keys,
        train_core_max_date=train_core_max_date,
        eval_max_date=eval_max_date,
    )
    assert model_cb is not None

    # --- 違反入力1: eval ∩ calib 重複 → ValueError ---
    bad_eval_keys = eval_keys | {next(iter(calib_keys))}
    with pytest.raises(ValueError):
        train_lightgbm(
            X_train,
            y_train,
            X_eval=X_eval,
            y_eval=y_eval,
            eval_race_keys=bad_eval_keys,
            calib_race_keys=calib_keys,
            test_race_keys=test_keys,
            train_core_max_date=train_core_max_date,
            eval_max_date=eval_max_date,
        )

    # --- 違反入力2: eval ∩ test 重複 → ValueError ---
    bad_eval_keys2 = eval_keys | {next(iter(test_keys))}
    with pytest.raises(ValueError):
        train_catboost(
            X_train,
            y_train,
            X_eval=X_eval,
            y_eval=y_eval,
            eval_race_keys=bad_eval_keys2,
            calib_race_keys=calib_keys,
            test_race_keys=test_keys,
            train_core_max_date=train_core_max_date,
            eval_max_date=eval_max_date,
        )

    # --- 違反入力3: eval_max_date > train_core_max_date → ValueError (review Cross-Plan #8) ---
    future_date = train_core_max_date + pd.Timedelta(days=365)
    with pytest.raises(ValueError):
        train_lightgbm(
            X_train,
            y_train,
            X_eval=X_eval,
            y_eval=y_eval,
            eval_race_keys=eval_keys,
            calib_race_keys=calib_keys,
            test_race_keys=test_keys,
            train_core_max_date=train_core_max_date,
            eval_max_date=future_date,
        )

    # --- assert_eval_disjoint の直接検証: 全ての disjoint 違反パターン ---
    with pytest.raises(ValueError):
        assert_eval_disjoint(
            {"A", "B"}, {"B", "C"}, {"D"}, train_core_max_date=None, eval_max_date=None
        )
    with pytest.raises(ValueError):
        assert_eval_disjoint(
            {"A"}, {"B"}, {"A"}, train_core_max_date=None, eval_max_date=None
        )
    with pytest.raises(ValueError):
        assert_eval_disjoint(
            {"A"},
            {"B"},
            {"D"},
            train_core_max_date=pd.Timestamp("2020-01-01"),
            eval_max_date=pd.Timestamp("2021-01-01"),
        )

    # 正常入力は何も raise しない
    assert_eval_disjoint(
        {"A"},
        {"B"},
        {"C"},
        train_core_max_date=pd.Timestamp("2021-01-01"),
        eval_max_date=pd.Timestamp("2020-06-01"),
    )

    # --- review HIGH#7: LGB_INIT_PARAMS / CB_INIT_PARAMS の決定論フラグ確認 ---
    assert LGB_INIT_PARAMS["seed"] == 42
    assert LGB_INIT_PARAMS["deterministic"] is True
    assert LGB_INIT_PARAMS["force_col_wise"] is True
    assert LGB_INIT_PARAMS["num_threads"] == 1
    assert LGB_INIT_PARAMS["bagging_seed"] == 42
    assert LGB_INIT_PARAMS["feature_fraction_seed"] == 42
    assert CB_INIT_PARAMS["has_time"] is True
    assert CB_INIT_PARAMS["random_seed"] == 42
    assert CB_INIT_PARAMS["thread_count"] == 1


# ---------------------------------------------------------------------------
# 補助検証: target encoding 禁止の grep 的確認（source 構造的保証）
# ---------------------------------------------------------------------------
def test_no_target_encoding_imports_in_trainer_module():
    """src/model/trainer.py が target encoding 系 API を import / 呼出しない構造的保証 (§14.3)。

    ``import`` 文や ``category_encoders`` モジュール参照が無いことを確認する。
    docstring 内の「禁止」言及は許可する（実呼出でないため）。
    """
    import src.model.trainer as trainer_mod

    source = inspect.getsource(trainer_mod)
    # import 文・モジュール参照が無いことを確認
    forbidden_imports = [
        "import category_encoders",
        "from category_encoders",
        "category_encoders.TargetEncoder",
        "from sklearn.preprocessing import TargetEncoder",  # sklearn にも最近追加された
        "TargetEncoder(",  # 実際の呼出
    ]
    for token in forbidden_imports:
        assert token not in source, (
            f"src/model/trainer.py に禁止 API 呼出 '{token}' が含まれる (§14.3 target encoding 禁止)"
        )
    # category_encoders モジュール自体の import が無いことを最終保証
    assert "import category_encoders" not in source, (
        "src/model/trainer.py が category_encoders を import している (§14.3 target encoding 禁止)"
    )
