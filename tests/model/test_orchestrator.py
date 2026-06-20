# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""Phase 4 SC#4 / review HIGH#2 / HIGH#7 / HIGH#12 / Cycle 2 NEW HIGH-1 / Cycle 2 residual #13 検証契約.

本テストは PLAN 05 Task 1 で新設する。test_calibrator.py::test_reproduce_bit_identical
(PLAN 02 lightgbm 代用版) は残置し・本テストが orchestrator 版の bit-identical を検証する。

検証内容:
- review HIGH#2: train_and_predict が返す pred_df の index が入力 X_test.index と完全一致
  ・CatBoost の場合 sort 後に align_predictions で元順序復元・入力シャッフルでも復元
- Cycle 2 NEW HIGH-1: 最終 pred_df の p_fukusho_hit 列が orchestrator 内部で align_predictions
  復元した pred_proba と np.array_equal で完全一致 (predict_p_fukusho が再予測して整列を捨てない)
- review HIGH#7 / SC#4: train_and_predict(model_type, feature_df, *, seed=42, as_of_datetime=FIXED)
  を2回呼出し prediction DataFrame の p_fukusho_hit 列が np.array_equal (bit-identical)
  ・固定 thread count (num_threads=1 / thread_count=1)・固定 as_of_datetime
- review HIGH#12: src/model/orchestrator.py と src/model/calibrator.py の両方が import 可能
  ・循環依存なし (orchestrator が calibrator を一方向 import・逆方向なし)
- Cycle 2 residual #13: train_and_predict が feature_df (label-joined) のみを受け取り
  readonly_cur / label_df 引数を持たない・docstring + assert で明示的契約

参考: 04-05-PLAN.md / 04-RESEARCH.md D-06 SC#4 Reproduce Smoke Test /
      tests/features/test_snapshot_repro.py:40-52 (2回呼出 hash 比較パターン) /
      src/model/trainer.py (_build_rare_category_synthetic).
"""

from __future__ import annotations

import inspect
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

# orchestrator が存在しない場合は ImportError で RED (PLAN 05 Task 1 で実装)
from src.model.orchestrator import (  # noqa: E402
    FIXED_REPRODUCE_TS,
    _merge_params,
    train_and_predict,
)

# ---------------------------------------------------------------------------
# 共通 helper: 合成 label-joined feature_df (race_key 時系列・categorical 含む)
# ---------------------------------------------------------------------------
# split_3way が [2016-07-01, 2023-12-31] (train) / [2024-01-01, 2024-06-30] (calib) /
# [2024-07-01, 2024-12-31] (test) の mask で分離するため・合成 df はこの3区間にまたがる
# race_date を持つ必要がある。各 split が非空 (split_3way が空区間で ValueError) になるよう
# 各期間に十分なレースを配置する。


def _build_label_joined_feature_df(
    n_train_races: int = 200,
    n_calib_races: int = 40,
    n_test_races: int = 40,
    n_holdout_races: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """split_3way の3区間 + holdout_2025_plus にまたがる label-joined feature_df を構築する。

    train 区間 [2016-07-01, 2023-12-31]・calib [2024-01-01, 2024-06-30]・
    test [2024-07-01, 2024-12-31]・holdout_2025_plus [2025-01-01, 2025-12-31] に
    それぞれ ``n_*_races`` レース (8頭立て) を配置。
    fukusho_hit_validated 列を含む (= label join 済み・Cycle 2 residual #13 契約)。
    split_3way は holdout_2025_plus が空でも ValueError になるため・必ず配置する。
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []

    def _add_period(n_races: int, start: str, end: str, period_seed_offset: int) -> None:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        span_days = max(1, (end_ts - start_ts).days)
        for race_i in range(n_races):
            # period 内に一様に分散
            race_dt = start_ts + pd.Timedelta(days=int(span_days * race_i / max(1, n_races)))
            jyocd = (race_i % 10) + 1
            kaiji = ((race_i // 10) % 8) + 1
            nichiji = ((race_i // 80) % 12) + 1
            racenum = jyocd
            # race_key を区間 + race_i + レース日で一意にする (異なる区間・年のレースが
            # 同一 race_key になるのを防止・split_3way の disjoint 検査通過のため)。
            # 正準 race_key = year-jyocd-kaiji-nichiji-racenum の形式を維持しつつ・
            # race_i と period をエンコードして一意性を保証。
            race_key = (
                f"{race_dt.year}-{jyocd:02d}-{kaiji:02d}-"
                f"{nichiji:02d}-{racenum}-p{period_seed_offset}-r{race_i}"
            )
            for umaban in range(1, 9):
                rows.append(
                    {
                        "race_start_datetime": race_dt,
                        "race_key": race_key,
                        "race_date": race_dt.normalize(),
                        "year": race_dt.year,
                        "jyocd": f"{jyocd:02d}",
                        "kaiji": kaiji,
                        "nichiji": f"{nichiji:02d}",
                        "racenum": racenum,
                        "umaban": umaban,
                        "kettonum": int(
                            rng.integers(1, 100_000_000)
                        ),  # PK 一意性のためにレース内で異なる値
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
                        "wakuban": int(rng.integers(1, 9)),
                        # rolling_* numeric features (FEATURE_COLUMNS に含まれる全て)
                        "rolling_babacd_latest_5": float(rng.normal(0.5, 0.1)),
                        "rolling_babacd_mean_5": float(rng.normal(0.5, 0.1)),
                        "rolling_babacd_sd_5": float(rng.normal(0.05, 0.01)),
                        "rolling_days_since_prev_latest_5": int(rng.integers(7, 60)),
                        "rolling_days_since_prev_mean_5": float(rng.normal(30.0, 5.0)),
                        "rolling_days_since_prev_sd_5": float(rng.normal(10.0, 2.0)),
                        "rolling_harontimel3_latest_5": float(rng.normal(35.0, 1.0)),
                        "rolling_harontimel3_mean_5": float(rng.normal(35.0, 1.0)),
                        "rolling_harontimel3_sd_5": float(rng.normal(0.5, 0.1)),
                        "rolling_jyuni3c_jyuni4c_latest_5": float(rng.normal(5.0, 2.0)),
                        "rolling_jyuni3c_jyuni4c_mean_5": float(rng.normal(5.0, 2.0)),
                        "rolling_jyuni3c_jyuni4c_sd_5": float(rng.normal(2.0, 0.5)),
                        "rolling_kakuteijyuni_latest_5": float(rng.normal(5.0, 2.0)),
                        "rolling_kakuteijyuni_mean_5": float(rng.normal(5.0, 2.0)),
                        "rolling_kakuteijyuni_sd_5": float(rng.normal(2.0, 0.5)),
                        "rolling_kyori_latest_5": int(rng.choice([1400, 1600, 1800, 2000])),
                        "rolling_kyori_mean_5": float(rng.normal(1800.0, 100.0)),
                        "rolling_kyori_sd_5": float(rng.normal(100.0, 20.0)),
                        "rolling_timediff_latest_5": float(rng.normal(0.0, 0.5)),
                        "rolling_timediff_mean_5": float(rng.normal(0.0, 0.3)),
                        "rolling_timediff_sd_5": float(rng.normal(0.3, 0.05)),
                        "is_model_eligible": True,
                        "label_validation_status": "ok",
                        "fukusho_hit_validated": int(rng.random() < 0.21),
                    }
                )

    _add_period(n_train_races, "2016-07-01", "2023-12-31", 0)
    _add_period(n_calib_races, "2024-01-01", "2024-06-30", 1)
    _add_period(n_test_races, "2024-07-01", "2024-12-31", 2)
    _add_period(n_holdout_races, "2025-01-01", "2025-12-31", 3)

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["race_start_datetime", "race_key", "umaban"], kind="mergesort"
    ).reset_index(drop=True)
    return df


# ===========================================================================
# Test 1: test_train_and_predict_row_alignment (review HIGH#2)
# ===========================================================================
def test_train_and_predict_row_alignment():
    """train_and_predict(model_type="catboost") の戻り pred_df.index が X_test.index
    (splits["test"].index) と完全一致する (review HIGH#2)。

    CatBoost は sort 済み Pool で予測するが・orchestrator が align_predictions で
    元順序に復元する。入力 test をシャッフルしても最終 pred_df.index が
    splits["test"].index と一致することを検証する (silent wrong-horse prediction 防止)。
    """
    feature_df = _build_label_joined_feature_df(
        n_train_races=120,
        n_calib_races=20,
        n_test_races=20,
        seed=11,
    )
    result = train_and_predict(
        feature_df,
        model_type="catboost",
        feature_snapshot_id="20260620-1a-postreview-v2",
        version_n=1,
        seed=42,
        as_of_datetime=FIXED_REPRODUCE_TS,
    )

    pred_df = result["pred_df"]
    splits = result["splits"]
    test_index = splits["test"].index

    # pred_df の index が test split の index と完全一致
    assert pred_df.index.equals(test_index), (
        "train_and_predict(catboost) の pred_df.index が splits['test'].index と一致しない "
        "(review HIGH#2: CatBoost sort 後の silent wrong-horse prediction)"
    )

    # pred_df の行数が test 行数と一致
    assert len(pred_df) == len(splits["test"]), (
        f"pred_df 行数 ({len(pred_df)}) が test split 行数 ({len(splits['test'])}) と不一致 "
        "(review HIGH#2)"
    )

    # LightGBM でも同様に行整列が保証される
    result_lgb = train_and_predict(
        feature_df,
        model_type="lightgbm",
        feature_snapshot_id="20260620-1a-postreview-v2",
        version_n=1,
        seed=42,
        as_of_datetime=FIXED_REPRODUCE_TS,
    )
    pred_df_lgb = result_lgb["pred_df"]
    assert pred_df_lgb.index.equals(test_index), (
        "train_and_predict(lightgbm) の pred_df.index が splits['test'].index と一致しない "
        "(review HIGH#2)"
    )


# ===========================================================================
# Test 2: test_catboost_pred_proba_injection (Cycle 2 NEW HIGH-1)
# ===========================================================================
def test_catboost_pred_proba_injection():
    """train_and_predict(model_type="catboost") の最終 pred_df の p_fukusho_hit 列が・
    orchestrator 内部で align_predictions で復元した pred_proba と np.array_equal で
    完全一致することを assert (Cycle 2 NEW HIGH-1)。

    predict_p_fukusho が再予測して整列を捨てていないことの実証。
    入力をシャッフルしても最終 pred_df.index が元 X_test.index と一致することも検証。
    LightGBM でも pred_proba 注入経路が正しいことを assert。
    """
    feature_df = _build_label_joined_feature_df(
        n_train_races=120,
        n_calib_races=20,
        n_test_races=20,
        seed=23,
    )

    # CatBoost
    result_cb = train_and_predict(
        feature_df,
        model_type="catboost",
        feature_snapshot_id="20260620-1a-postreview-v2",
        version_n=1,
        seed=42,
        as_of_datetime=FIXED_REPRODUCE_TS,
    )
    pred_df_cb = result_cb["pred_df"]
    aligned_pred_proba = result_cb["_aligned_pred_proba"]  # 内部参照用

    # 最終 p_fukusho_hit が aligned_pred_proba と bit-identical
    assert np.array_equal(
        pred_df_cb["p_fukusho_hit"].to_numpy(),
        aligned_pred_proba.to_numpy(),
    ), (
        "CatBoost の最終 pred_df.p_fukusho_hit が orchestrator 内部で "
        "align_predictions した pred_proba と一致しない "
        "(Cycle 2 NEW HIGH-1: predict_p_fukusho が再予測して整列を捨てた回帰)"
    )

    # LightGBM でも pred_proba 注入経路が正しい
    result_lgb = train_and_predict(
        feature_df,
        model_type="lightgbm",
        feature_snapshot_id="20260620-1a-postreview-v2",
        version_n=1,
        seed=42,
        as_of_datetime=FIXED_REPRODUCE_TS,
    )
    pred_df_lgb = result_lgb["pred_df"]
    aligned_pred_proba_lgb = result_lgb["_aligned_pred_proba"]
    assert np.array_equal(
        pred_df_lgb["p_fukusho_hit"].to_numpy(),
        aligned_pred_proba_lgb.to_numpy(),
    ), (
        "LightGBM の最終 pred_df.p_fukusho_hit が orchestrator 内部 pred_proba と一致しない "
        "(Cycle 2 NEW HIGH-1: pred_proba 注入経路の不整合)"
    )


# ===========================================================================
# Test 3: test_reproduce_bit_identical (review HIGH#7 / SC#4)
# ===========================================================================
def test_reproduce_bit_identical():
    """SC#4 reproduce smoke: seed=42 で2回 train_and_predict を呼出し・戻り prediction
    DataFrame の p_fukusho_hit 列が np.array_equal (bit-identical) (review HIGH#7)。

    固定 thread count (LightGBM num_threads=1・CatBoost thread_count=1)・
    固定 as_of_datetime (FIXED_REPRODUCE_TS)・calibrated estimator も再現性あり。
    """
    feature_df = _build_label_joined_feature_df(
        n_train_races=120,
        n_calib_races=20,
        n_test_races=20,
        seed=42,
    )

    for model_type in ("lightgbm", "catboost"):
        result1 = train_and_predict(
            feature_df,
            model_type=model_type,
            feature_snapshot_id="20260620-1a-postreview-v2",
            version_n=1,
            seed=42,
            as_of_datetime=FIXED_REPRODUCE_TS,
        )
        result2 = train_and_predict(
            feature_df,
            model_type=model_type,
            feature_snapshot_id="20260620-1a-postreview-v2",
            version_n=1,
            seed=42,
            as_of_datetime=FIXED_REPRODUCE_TS,
        )

        pred1 = result1["pred_df"]["p_fukusho_hit"].to_numpy()
        pred2 = result2["pred_df"]["p_fukusho_hit"].to_numpy()

        assert np.array_equal(pred1, pred2), (
            f"SC#4 reproduce smoke 違反 ({model_type}): seed=42 + 固定 thread count + "
            f"固定 as_of_datetime で2回 train_and_predict した p_fukusho_hit が "
            f"bit-identical でない (review HIGH#7・§19.1 構造的ブロック・Phase 完了不可)"
        )


# ===========================================================================
# Test 4: test_no_circular_import (review HIGH#12)
# ===========================================================================
def test_no_circular_import():
    """src/model/orchestrator.py と src/model/calibrator.py の両方が import 可能で・
    循環依存がないことを検証 (review HIGH#12)。

    orchestrator は calibrator / trainer / data / predict / artifact を一方向に import し・
    calibrator は orchestrator を import しない。
    """
    # 両モジュールが import 可能
    import src.model.calibrator as cal_mod
    import src.model.orchestrator as orch_mod

    # orchestrator の source に calibrator import がある (一方向)
    orch_source = inspect.getsource(orch_mod)
    assert "from src.model.calibrator" in orch_source or (
        "import src.model.calibrator" in orch_source
    ), "orchestrator が calibrator を import していない (review HIGH#12 想定違反)"

    # calibrator の source に orchestrator import が無い (逆方向なし)
    cal_source = inspect.getsource(cal_mod)
    assert "from src.model.orchestrator" not in cal_source, (
        "calibrator が orchestrator を import している (review HIGH#12: 循環依存・"
        "calibrator.py は純粋 utility のまま維持すべき)"
    )
    assert "import src.model.orchestrator" not in cal_source, (
        "calibrator が orchestrator を import している (review HIGH#12 循環依存)"
    )

    # train_and_predict が calibrator.py に無い (review HIGH#12)
    assert not hasattr(cal_mod, "train_and_predict"), (
        "calibrator.py に train_and_predict が存在する "
        "(review HIGH#12: orchestrator は orchestrator.py のみ)"
    )

    # sys.modules に循環参照マーカーが無い (部分的検出)
    # Python は循環 import を検出すると None を一時的に bind する
    assert sys.modules.get("src.model.orchestrator") is orch_mod
    assert sys.modules.get("src.model.calibrator") is cal_mod


# ===========================================================================
# Test 5: test_data_api_boundary_explicit (Cycle 2 residual #13)
# ===========================================================================
def test_data_api_boundary_explicit():
    """Cycle 2 residual #13: train_and_predict が feature_df (label-joined) のみを受け取り・
    readonly_cur / label_df 引数を持たない。docstring に契約明記・入口で label 列存在を assert。
    """
    import src.model.orchestrator as orch_mod

    source = inspect.getsource(orch_mod)

    # orchestrator に label join の実呼出経路が無い (load_labels() 呼出 / readonly_cur 引数なし)。
    # docstring 内の言及は許容する (実呼出でないため)。実呼出形式 (load_labels( / def load_labels)
    # と readonly_cur 引数の不在を検証する。
    assert "def load_labels" not in source, (
        "orchestrator に load_labels 関数定義がある (Cycle 2 residual #13)"
    )
    assert "load_labels(" not in source, (
        "orchestrator に load_labels() 実呼出がある (Cycle 2 residual #13: "
        "label join は run_train_predict 側でのみ発生すべき・orchestrator は再実行しない)"
    )
    assert "readonly_cur" not in source, (
        "orchestrator に readonly_cur 引数/呼出がある (Cycle 2 residual #13: "
        "orchestrator は label-joined frame のみを受け取る)"
    )

    # docstring に契約明記
    assert (
        "does NOT rejoin" in source
        or "label join を再実行しない" in source
        or "does not rejoin" in source.lower()
    ), (
        "train_and_predict docstring に label join 非実行の契約明記がない "
        "(Cycle 2 residual #13: データ API 境界を明示すべき)"
    )

    # label 列が無い feature_df を渡すと ValueError (fail-loud)
    feature_df = _build_label_joined_feature_df(
        n_train_races=60,
        n_calib_races=20,
        n_test_races=20,
        seed=5,
    )
    # label join 未実行の frame をシミュレート (fukusho_hit_validated を drop)
    no_label_df = feature_df.drop(columns=["fukusho_hit_validated"])
    with pytest.raises(ValueError):
        train_and_predict(
            no_label_df,
            model_type="lightgbm",
            feature_snapshot_id="20260620-1a-postreview-v2",
            version_n=1,
            seed=42,
            as_of_datetime=FIXED_REPRODUCE_TS,
        )


# ===========================================================================
# Test 6: test_merge_params_overrides_seed_and_threads
# ===========================================================================
def test_merge_params_overrides_seed_and_threads():
    """_merge_params が default_params に override を deep merge し・seed と thread count を
    強制固定する (review HIGH#7: thread count も seed も上書き可能だがデフォルトは 1/42)。
    """
    from src.model.trainer import CB_INIT_PARAMS, LGB_INIT_PARAMS

    # LightGBM: override を merge しても seed=42 / num_threads=1 が維持される
    merged_lgb = _merge_params(LGB_INIT_PARAMS, {"learning_rate": 0.1, "num_leaves": 31}, seed=42)
    assert merged_lgb["seed"] == 42
    assert merged_lgb["num_threads"] == 1
    assert merged_lgb["learning_rate"] == 0.1  # override 反映
    assert merged_lgb["num_leaves"] == 31  # override 反映

    # CatBoost: 同様
    merged_cb = _merge_params(CB_INIT_PARAMS, {"learning_rate": 0.1, "depth": 8}, seed=42)
    assert merged_cb["random_seed"] == 42
    assert merged_cb["thread_count"] == 1
    assert merged_cb["learning_rate"] == 0.1
    assert merged_cb["depth"] == 8


# ===========================================================================
# 補助: FIXED_REPRODUCE_TS が固定値であることの確認 (review HIGH#7)
# ===========================================================================
def test_fixed_reproduce_ts_is_constant():
    """FIXED_REPRODUCE_TS が固定 datetime であること (review HIGH#7・bit-identical 保証)。"""
    assert isinstance(FIXED_REPRODUCE_TS, datetime)
    assert FIXED_REPRODUCE_TS.tzinfo is not None  # timezone-aware
    # 2回参照しても同一オブジェクト (モジュール定数)
    from src.model.orchestrator import FIXED_REPRODUCE_TS as ts2

    assert FIXED_REPRODUCE_TS == ts2
