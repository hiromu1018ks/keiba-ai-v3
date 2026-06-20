"""Phase 4 D-05 provenance / D-10 model_version 検証契約.

後続 PLAN 04 (predict.py) が本 stub を GREEN 化する:
- provenance 列 (model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method) が存在・NOT NULL
- D-10 model_version 採番: {feature_snapshot_id}-{model_type_short}-v{N} 形式
  例: 20260620-1a-postreview-v2-lgb-v1 / 20260620-1a-postreview-v2-cb-v1
  (Cycle 3 NEW-4 残渣: feature_snapshot_id 全体を prefix・再 suffix 追加禁止)
- NEW HIGH-1 (Cycle 2): pred_proba 注入で CatBoost の aligned 予測値が最終 DataFrame に伝播・
  再予測で整列が捨てられる silent wrong-horse prediction 回帰を閉塞

参考: 04-RESEARCH.md D-10 確定事項 / D-05 prediction provenance /
      04-04-PLAN.md Task 1 behavior/action.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.model.predict import (
    MODEL_TYPE_TO_SHORT,
    PREDICTION_COLUMNS,
    PK_COLUMNS,
    make_model_version,
    predict_p_fukusho,
)


# ---------------------------------------------------------------------------
# helpers — 合成 calibrated estimator と feature DataFrame
# ---------------------------------------------------------------------------


def _make_synthetic_estimator() -> LogisticRegression:
    """``predict_proba`` を持つ sklearn estimator を構築（PLAN 02 test と同様）.

    ``predict_p_fukusho`` は ``calibrated_estimator.predict_proba(X)[:, 1]`` を
    呼ぶため、学習済み sklearn estimator を返す。``CalibratedClassifierCV`` で
    なくとも ``predict_proba`` を持てば本契約の検証には十分。
    """
    rng = np.random.default_rng(42)
    X = rng.uniform(size=(40, 3))
    y = (X[:, 0] + rng.normal(scale=0.1, size=40) > 0.5).astype(int)
    est = LogisticRegression(max_iter=1000, random_state=42)
    est.fit(X, y)
    return est


def _make_synthetic_feature_df(n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """合成特徴量 X と race_df (PK + race_date + split) を返す.

    Returns
    -------
    (X, race_df) : X は estimator 入力 3 列・race_df は PK 7 カラム + race_date + split
        + race_start_datetime。両者とも同一 index (0..n-1)。
    """
    rng = np.random.default_rng(7)
    idx = pd.Index(range(n), name="row_id")
    X = pd.DataFrame(
        rng.uniform(size=(n, 3)),
        columns=["feat_a", "feat_b", "feat_c"],
        index=idx,
    )
    race_df = pd.DataFrame(
        {
            "year": [2024] * n,
            "jyocd": ["05"] * n,
            "kaiji": [1] * n,
            "nichiji": ["01"] * n,
            "racenum": list(range(1, n + 1)),
            "umaban": list(range(1, n + 1)),
            "kettonum": list(range(100, 100 + n)),
            "race_date": pd.date_range("2024-01-01", periods=n, freq="D").date,
            "race_start_datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
        },
        index=idx,
    )
    return X, race_df


# ---------------------------------------------------------------------------
# Test 1: provenance columns
# ---------------------------------------------------------------------------


def test_provenance_columns():
    """provenance 列 (model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method) が存在・NOT NULL.

    §19.1 再現性聖域. PK (model_type/model_version/feature_snapshot_id/as_of_datetime + RACE_KEY 7) に
    含まれることで NOT NULL 保証 (review HIGH#1・11カラム PK).

    検証項目:
      - 戻り df.columns == PREDICTION_COLUMNS (順序含む)
      - 5 provenance 列が NaN なし
      - p_fukusho_hit ∈ [0, 1]
      - PK 11 カラム (4 provenance + 7 RACE_KEY) で一意 (duplicated().sum()==0)
    """
    est = _make_synthetic_estimator()
    X, race_df = _make_synthetic_feature_df(n=10)

    fixed_as_of = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    df = predict_p_fukusho(
        est,
        X,
        model_type="lightgbm",
        model_version="20260620-1a-postreview-v2-lgb-v1",
        feature_snapshot_id="20260620-1a-postreview-v2",
        calib_method="isotonic",
        race_df=race_df,
        split_label="test",
        as_of_datetime=fixed_as_of,
    )

    # 列順序が PREDICTION_COLUMNS と完全一致
    assert list(df.columns) == list(PREDICTION_COLUMNS), (
        f"columns mismatch: got {list(df.columns)}, expected {list(PREDICTION_COLUMNS)}"
    )

    # 5 provenance 列が NOT NULL
    provenance_cols = [
        "model_type",
        "model_version",
        "feature_snapshot_id",
        "as_of_datetime",
        "calib_method",
    ]
    for col in provenance_cols:
        assert not df[col].isna().any(), f"provenance col {col!r} has NaN"

    # p_fukusho_hit ∈ [0, 1]
    assert (df["p_fukusho_hit"] >= 0).all() and (df["p_fukusho_hit"] <= 1).all()

    # PK 11 カラムで一意
    pk_11 = (
        ["model_type", "model_version", "feature_snapshot_id", "as_of_datetime"]
        + PK_COLUMNS
    )
    assert df.duplicated(subset=pk_11).sum() == 0, "PK 11 columns not unique"


# ---------------------------------------------------------------------------
# Test 2: NEW HIGH-1 pred_proba injection
# ---------------------------------------------------------------------------


def test_predict_uses_injected_pred_proba():
    """NEW HIGH-1: predict_p_fukusho に pred_proba 引数で渡した予測値が p_fukusho_hit に使われる.

    Cycle 2 NEW HIGH-1: orchestrator が算出した aligned pred_proba が最終 prediction
    DataFrame に伝播する。再予測で整列が捨てられる silent wrong-horse prediction
    回帰を閉塞。

    検証項目:
      1. ``pred_proba=expected`` を渡した場合の p_fukusho_hit が・渡さない場合と
         ``np.array_equal`` で完全一致 (注入値が使われる = 再予測されない)
      2. X.index と不一致の pred_proba (Series) を渡すと ``RuntimeError`` (silent
         wrong-horse prediction 防止)
    """
    est = _make_synthetic_estimator()
    X, race_df = _make_synthetic_feature_df(n=10)

    # 手動で expected 予測値を算出
    expected = est.predict_proba(X)[:, 1]

    fixed_as_of = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    common_kwargs = dict(
        model_type="lightgbm",
        model_version="20260620-1a-postreview-v2-lgb-v1",
        feature_snapshot_id="20260620-1a-postreview-v2",
        calib_method="isotonic",
        race_df=race_df,
        split_label="test",
        as_of_datetime=fixed_as_of,
    )

    # 1. pred_proba 渡さない場合
    df_no_inject = predict_p_fukusho(est, X, **common_kwargs)
    # 1b. pred_proba=expected を渡した場合
    df_inject = predict_p_fukusho(est, X, pred_proba=expected, **common_kwargs)

    # 両者の p_fukusho_hit が完全一致 (注入値が使われる = 再予測されない)
    assert np.array_equal(
        df_no_inject["p_fukusho_hit"].to_numpy(),
        df_inject["p_fukusho_hit"].to_numpy(),
    ), "injected pred_proba was not used as-is (re-predicted?)"

    # 2. index 不一致の pred_proba (Series) は RuntimeError
    shuffled_idx = pd.Index(reversed(list(X.index)))
    bad_pred_proba = pd.Series(expected, index=shuffled_idx)
    with pytest.raises(RuntimeError):
        predict_p_fukusho(est, X, pred_proba=bad_pred_proba, **common_kwargs)


# ---------------------------------------------------------------------------
# Test 3: D-10 model_version numbering (review HIGH#4)
# ---------------------------------------------------------------------------


def test_model_version_numbering():
    """D-10 model_version 採番: {feature_snapshot_id}-{model_type_short}-v{N} 形式.

    例: 20260620-1a-postreview-v2-lgb-v1 / 20260620-1a-postreview-v2-cb-v1.
    feature_snapshot_id 全体を prefix とし、再度 suffix を追加しない (Cycle 3 NEW-4 残渣解消 /
    review HIGH#4 / Cross-Plan #1).

    検証項目:
      - lightgbm v1 → "...-lgb-v1"
      - catboost v1 → "...-cb-v1"
      - version_n=2 → "...-lgb-v2"
      - feature_snapshot_id が "...-v2" で終わっても二重 suffix が現れない
        (例: "20260620-1a-postreview-v2-lgb-v1"・"postreview-v2-lgb" のような
        二重 version suffix は絶対に出力しない)
    """
    fsid = "20260620-1a-postreview-v2"

    assert make_model_version(fsid, "lightgbm", 1) == "20260620-1a-postreview-v2-lgb-v1"
    assert make_model_version(fsid, "catboost", 1) == "20260620-1a-postreview-v2-cb-v1"
    assert make_model_version(fsid, "lightgbm", 2) == "20260620-1a-postreview-v2-lgb-v2"

    # 二重 version suffix 回帰検査 (review HIGH#4 の核心)
    # 正しい形式: feature_snapshot_id 全体が1回だけ prefix として現れる。
    # 回帰形: snapshot_id の version 部分 (e.g. "postreview-v2") が model_type 短縮形の
    # 前後に2回現れる (旧版 "20260620-1a-postreview-v2-postreview-v2-lgb-v1" のような二重 postfix)。
    mv = make_model_version(fsid, "lightgbm", 1)
    # snapshot_id 全体が prefix として1回だけ現れる (startswith)
    assert mv.startswith(fsid + "-"), (
        f"model_version should start with feature_snapshot_id + '-': {mv!r}"
    )
    # snapshot_id の version token (postreview-v2) が model_type short の直前にもう一度
    # 現れない (二重 postfix 回帰検出)。正: "...-postreview-v2-lgb-v1" / 誤: "...-postreview-v2-postreview-v2-lgb-v1"
    # → "-postreview-v2-postreview-v2-" という2連続を含まない。
    assert "-postreview-v2-postreview-v2-" not in mv, (
        f"double version suffix detected: {mv!r} (review HIGH#4 violation)"
    )
    # model_type short は末尾の "-lgb-v1" の形で1回だけ現れる
    assert mv.endswith("-lgb-v1"), f"unexpected suffix: {mv!r}"
    # MODEL_TYPE_TO_SHORT が想定の短縮形を持つ
    assert MODEL_TYPE_TO_SHORT["lightgbm"] == "lgb"
    assert MODEL_TYPE_TO_SHORT["catboost"] == "cb"
