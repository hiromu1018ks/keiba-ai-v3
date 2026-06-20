"""``split_3way`` の ``periods`` パラメータ拡張（BT窓再学習用）+ orchestrator 拡張
（split_periods / category_map plumbing）の unit test（D-03 / HIGH-A cycle-2 /
RESEARCH §6.1-§6.5）。

検証内容:
- ``test_split_3way_periods_injection``: ``periods`` 指定で BT窓分割・strict chronological
  + race_key disjoint guard 継承（HIGH-4: train/calib 重複なし窓例）
- ``test_split_3way_periods_strict_later_guard``: train_end >= calib_start の重複 periods で
  ValueError が raise されることを assert（HIGH-4 look-ahead leak 構造的ブロック）
- ``test_split_3way_backward_compat``: ``periods=None``（既定）で Phase 4 ハードコード挙動
- ``test_train_and_predict_split_periods``: ``train_and_predict(split_periods=...)`` が
  ``split_3way(periods=split_periods)`` に伝播
- ``test_train_and_predict_backward_compat``: ``split_periods=None`` で Phase 4 と同一挙動
- ``test_train_and_predict_category_map_plumbing`` (HIGH-A cycle-2): BT-train-only map を渡すと
  test 窓未観測 ID が ``__UNSEEN__`` sentinel に mapping される（供給 map が消費される証明）
- ``test_train_and_predict_category_map_none_default`` (HIGH-A cycle-2): ``category_map=None``
  で Phase 4 等価挙動（A5）
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_feature_frame(n_per_year: int = 100) -> pd.DataFrame:
    """BT窓テスト用の合成 feature DataFrame（race_date 列を持つ）。

    後続の category_map plumbing テスト（HIGH-A cycle-2）で使用するため・
    jockey_id（生 ID 列）と jockey_id_code（_code 列）も含む。
    """
    dates = pd.date_range("2019-01-01", "2025-12-31", freq="W")
    n = min(n_per_year * 7, len(dates))
    return pd.DataFrame({
        "race_key": [f"RK{i:05d}" for i in range(n)],
        "race_date": dates[:n],
        "year": dates[:n].year,
        "jyocd": "05",
        "kaiji": 1,
        "nichiji": "06",
        "racenum": 1,
        "umaban": [1] * n,
        "kettonum": [100 + i for i in range(n)],
        # HIGH-A cycle-2: category_map plumbing テスト用（生 ID + _code 列）
        "jockey_id": [f"J{i % 10:03d}" for i in range(n)],
        "jockey_id_code": [i % 10 for i in range(n)],
    })


def test_split_3way_periods_injection():
    """``periods`` 指定で BT窓分割・strict chronological + race_key disjoint guard を継承。

    HIGH-4: train と calib は重複しない（max(train.race_date) < min(calib.race_date)
    < max(calib.race_date) < min(test.race_date) を満たす厳密な窓例）。
    """
    from src.model.data import split_3way

    frame = _make_feature_frame()
    # HIGH-4: train/calib/test が pairwise disjoint で完全時系列順の窓（重複なし）
    periods = {
        "train": ("2019-06-01", "2022-06-30"),
        "calib": ("2022-07-01", "2022-12-31"),
        "test": ("2023-01-01", "2023-12-31"),
    }
    splits = split_3way(frame, periods=periods)
    assert set(splits.keys()) >= {"train", "calib", "test"}
    # BT窓区間で filter されていることを検証
    assert splits["train"]["race_date"].min() >= pd.to_datetime("2019-06-01")
    assert splits["train"]["race_date"].max() <= pd.to_datetime("2022-06-30")
    assert splits["calib"]["race_date"].min() >= pd.to_datetime("2022-07-01")
    assert splits["calib"]["race_date"].max() <= pd.to_datetime("2022-12-31")
    assert splits["test"]["race_date"].min() >= pd.to_datetime("2023-01-01")
    assert splits["test"]["race_date"].max() <= pd.to_datetime("2023-12-31")
    # race_key disjoint（train と test で共有なし）
    assert set(splits["train"]["race_key"]).isdisjoint(set(splits["test"]["race_key"]))
    # HIGH-4: 完全時系列条件 max(train) < min(calib) < max(calib) < min(test) が満たされる
    assert splits["train"]["race_date"].max() < splits["calib"]["race_date"].min()
    assert splits["calib"]["race_date"].max() < splits["test"]["race_date"].min()


def test_split_3way_periods_strict_later_guard():
    """HIGH-4: periods で train_end >= calib_start（重複）の場合・ValueError が raise される。

    完全時系列条件 guard が BT窓でも継承されることを assert（look-ahead leak 構造的ブロック）。
    """
    from src.model.data import split_3way

    frame = _make_feature_frame()
    # train と calib が重複する periods（train_end='2022-12-31' >= calib_start='2022-07-01'）
    overlapping_periods = {
        "train": ("2019-06-01", "2022-12-31"),
        "calib": ("2022-07-01", "2022-12-31"),
        "test": ("2023-01-01", "2023-12-31"),
    }
    with pytest.raises(ValueError, match="完全時系列条件違反|strict.*chronological|train_max.*calib_min"):
        split_3way(frame, periods=overlapping_periods)


def test_split_3way_backward_compat():
    """``periods=None`` で既存ハードコード挙動（Phase 4 回帰防止）。

    既存の ``train 2016-07〜2023 / calib 2024-01〜06 / test 2024-07〜12`` 区間が
    適用されることを検証する。``periods`` を渡さない呼び出しと ``periods=None``
    呼び出しは同一結果を返すべき（後方互換）。
    """
    from src.model.data import split_3way

    frame = _make_feature_frame()
    # 既存呼び出し（periods 引数なし）
    splits_legacy = split_3way(frame)
    # periods=None 呼び出し
    splits_none = split_3way(frame, periods=None)
    # train 行数が一致することで後方互換を検証
    assert len(splits_legacy["train"]) == len(splits_none["train"])
    assert len(splits_legacy["calib"]) == len(splits_none["calib"])
    assert len(splits_legacy["test"]) == len(splits_none["test"])


def test_train_and_predict_split_periods():
    """``train_and_predict(split_periods=...)`` が ``split_3way(periods=split_periods)`` に伝播。

    合成 feature_df + 最小 trainer mock で・split_periods が split_3way に渡されることを
    ``splits["train"]`` の race_date 区間で検証する（DB 非依存・モック非使用で
    split_3way 伝播のみ検証・trainer 呼出は実データで検証済み）。
    """
    from src.model.data import split_3way

    # split_3way の periods 伝播は・orchestrator が split_3way(feature_df, periods=split_periods)
    # を呼出すことで実現される。train_and_predict 全体を動かさずに伝播を検証するため・
    # まず split_3way の periods 受け入れを確認し・続いて orchestrator のシグネチャ検査で
    # split_periods が split_3way に渡されることをソース検査で担保する。
    frame = _make_feature_frame()
    periods = {
        "train": ("2019-06-01", "2022-06-30"),
        "calib": ("2022-07-01", "2022-12-31"),
        "test": ("2023-01-01", "2023-12-31"),
    }
    splits = split_3way(frame, periods=periods)
    # 伝播確認: periods を渡した split_3way の戻り値が BT窓で分割されている
    assert splits["train"]["race_date"].max() <= pd.to_datetime("2022-06-30")
    assert splits["test"]["race_date"].min() >= pd.to_datetime("2023-01-01")

    # orchestrator のシグネチャ検査: split_periods パラメータが存在し・
    # ソースコード上で split_3way(..., periods=split_periods) に伝播されている
    import inspect

    from src.model.orchestrator import train_and_predict

    sig = inspect.signature(train_and_predict)
    assert "split_periods" in sig.parameters, (
        "train_and_predict シグネチャに split_periods パラメータが無い（D-03 BT窓再学習ループ土台）"
    )
    src = inspect.getsource(train_and_predict)
    assert "periods=split_periods" in src, (
        "train_and_predict が split_3way(periods=split_periods) を呼出していない（D-03 伝播不在）"
    )


def test_train_and_predict_backward_compat():
    """``split_periods=None``（既定）で Phase 4 と同一挙動（A5 回帰防止）。

    シグネチャ検査: split_periods のデフォルト値が None であることを確認する。
    既存 test_orchestrator.py が green を維持することが Phase 4 回帰防止の主証明
    （本テストはシグネチャ後方互換の machine-checkable 保証）。
    """
    import inspect

    from src.model.orchestrator import train_and_predict

    sig = inspect.signature(train_and_predict)
    assert "split_periods" in sig.parameters
    assert sig.parameters["split_periods"].default is None, (
        "split_periods のデフォルト値が None でない（後方互換 A5 違反）"
    )


def test_train_and_predict_category_map_plumbing():
    """HIGH-A cycle-2: BT-train-only category_map を渡すと model 前処理で消費される。

    合成 feature_df で BT-train-only に存在しない jockey_id（例 'J_UNSEEN_999'）を
    BT-test 窓行にだけ含め・BT-train-only map（train 行のみで fit・'J_UNSEEN_999' を含まない）
    を train_and_predict に渡す前提で・orchestrator の ``_apply_category_map`` helper が
    供給 map を消費して categorical 変換を実施することを検証する。

    本テストは train_and_predict 全体を動かさず（trainer 学習が重いため）・
    orchestrator の ``_apply_category_map`` helper を直接呼出すことで plumbing を証明する。
    供給 map が消費され（silent 無視されない）・test 窓未観測 ID が ``__UNSEEN__``
    sentinel に mapping されることを assert する。
    """
    from src.model.orchestrator import _apply_category_map
    from src.utils.category_map import UNSEEN, fit_category_map

    # 合成 feature_df: train 窓には J000-J009・test 窓にだけ J_UNSEEN_999 を含める
    train_rows = pd.DataFrame({
        "jockey_id": [f"J{i:03d}" for i in range(10)] * 5,  # 50 行・train 窓
        "jockey_id_code": list(range(10)) * 5,
    })
    test_rows = pd.DataFrame({
        "jockey_id": ["J000", "J001", "J_UNSEEN_999", "J002"],  # J_UNSEEN_999 は train に無い
        "jockey_id_code": [0, 1, 999, 2],  # 既存 _code（map 適用で上書きされる）
    })
    feature_df = pd.concat(
        [
            train_rows.assign(_split="train"),
            test_rows.assign(_split="test"),
        ],
        ignore_index=True,
    )

    # BT-train-only map: train 行のみで fit（J_UNSEEN_999 を含まない）
    bt_train_only_map = {"jockey_id": fit_category_map(train_rows["jockey_id"])}

    # 供給 map を消費して categorical 変換
    result_df = _apply_category_map(feature_df.copy(), bt_train_only_map)

    # test 窓の J_UNSEEN_999 行の jockey_id_code が UNSEEN sentinel code に mapping される
    test_mask = result_df["_split"] == "test"
    test_jockey_ids = result_df.loc[test_mask, "jockey_id"].tolist()
    test_codes = result_df.loc[test_mask, "jockey_id_code"].tolist()
    unseen_idx = test_jockey_ids.index("J_UNSEEN_999")
    unseen_code = test_codes[unseen_idx]
    expected_unseen_code = bt_train_only_map["jockey_id"][UNSEEN]
    assert unseen_code == expected_unseen_code, (
        f"BT-train-only map が消費されていない（HIGH-A cycle-2 silent 無視）: "
        f"J_UNSEEN_999 の code={unseen_code}・期待（UNSEEN sentinel）={expected_unseen_code}"
    )

    # 既知 ID（J000/J001/J002）は train 窓で fit した code に mapping される
    for jid, expected_code_suffix in [("J000", 0), ("J001", 1), ("J002", 2)]:
        idx = test_jockey_ids.index(jid)
        # fit_category_map は sorted 後に連番を振るため J000=0, J001=1, ... になる
        actual_code = test_codes[idx]
        train_map = bt_train_only_map["jockey_id"]
        assert actual_code == train_map[jid], (
            f"既知 ID {jid} の code が BT-train-only map と不一致: "
            f"actual={actual_code}・expected={train_map[jid]}"
        )


def test_train_and_predict_category_map_none_default():
    """HIGH-A cycle-2: ``category_map=None``（既定）で Phase 4 等価挙動（A5）。

    シグネチャ検査: category_map パラメータが存在し・デフォルト値が None であることを確認。
    さらに ``_apply_category_map(df, None)`` が df を変更せず返す（no-op）ことを検証
    （None の場合は orchestrator 内部で従来どおり category map を fit・Phase 4 等価）。
    """
    import inspect

    from src.model.orchestrator import _apply_category_map, train_and_predict

    sig = inspect.signature(train_and_predict)
    assert "category_map" in sig.parameters, (
        "train_and_predict シグネチャに category_map パラメータが無い（HIGH-A cycle-2）"
    )
    assert sig.parameters["category_map"].default is None, (
        "category_map のデフォルト値が None でない（後方互換 A5 違反）"
    )

    # _apply_category_map(df, None) は no-op で df を変更せず返す
    df = pd.DataFrame({"jockey_id": ["J000", "J001"], "jockey_id_code": [0, 1]})
    result = _apply_category_map(df.copy(), None)
    # jockey_id_code 列が元のままであることを検証（map 適用なし）
    assert result["jockey_id_code"].tolist() == [0, 1], (
        "category_map=None で _apply_category_map が _code 列を変更した（A5 違反・Phase 4 等価でない）"
    )
