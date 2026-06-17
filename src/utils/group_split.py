"""race_id 単位・時系列順 CV splitter（成功基準#4 / §8.4 / §15.4）。

``mlxtend.evaluate.GroupTimeSeriesSplit`` を副 API として露出しつつ、主 API
``race_id_time_series_split`` で race_id disjoint + **厳格時系列順序**
（``max(train_time) < min(test_time)``、strict ``<``）を強制する。

REVIEWS HIGH #2 / HIGH #3:
- HIGH #2: 同一 ``race_start_datetime`` を持つレース群が train と test に跨ることを禁止。
  等値タイムスタンプが fold 境界に掛かった場合 ``raise ValueError`` する。
- HIGH #3: リーク防止ガードは ``assert`` ではなく ``raise ValueError`` 形式
  （``python -O`` で削除されない）。

scikit-learn の ``TimeSeriesSplit`` は group 非対応（#19072 open）のため、
同一 ``race_id`` が train/test にまたぐ静かなリークを生む。本 splitter は
race_id 単位で分割しこれを構造的に防ぐ。
"""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd

# 副 API: 異なる policy が必要な場合（BT-1..BT-5 等）の fallback。
# mlxtend 0.25.0 の GroupTimeSeriesSplit は group-aware time-series CV を提供する。
from mlxtend.evaluate import GroupTimeSeriesSplit  # noqa: F401  (re-exported)


def race_id_time_series_split(
    races: pd.DataFrame,
    n_splits: int = 5,
) -> Iterator[tuple[list[str], list[str]]]:
    """race_id 単位・``race_start_datetime`` 昇順の **expanding-window** 時系列CV。

    同一 race_id の train/test またぎを禁止し（§8.4/§15.4）、かつ各 foldで
    ``max(train_time) < min(test_time)``（**strict ``<``、等値不可**）を強制する。

    **WR-04 honesty note（window semantics）:**
    本関数は **expanding-window** のみを生成する: 各 fold の train は常に
    ``unique_races[:test_start]`` で index 0 から始まり、test は後続区間。
    これは ``TimeSeriesSplit`` と同じ振舞いであり、CLAUDE.md §15.5 が規定する
    BT-1..BT-5（例: BT-1 train 2019-06→2022 / test 2023）のような**固定-window**
    または**rolling-window** backtestは表現できない。BT-* helper は Phase 4 で
    追加予定（``mlxtend.GroupTimeSeriesSplit`` を副 API として露出済み・必要なら
    そちらで組み立てる）。従来の docstring は §15.4/§15.5 coverage を過剰に主張
    していたため訂正。

    **strict chronological（HIGH #2）:**
    等値 ``race_start_datetime`` を持つレース群（例: 競馬場 A と B の第1レースが同時刻）
    が fold 境界に掛かる場合、本関数は ``raise ValueError`` する。等値タイムスタンプの
    跨ぎは許さない。呼出元は ``race_id`` を tie-break で安定ソート済みの前提で渡すこと
    （本関数は内部で ``sort_values(["race_start_datetime", "race_id"])`` で安定化する）。

    **すべてのガードは ``raise ValueError``（HIGH #3）:**
    ``assert`` を使わないため ``python -O`` でも有効。

    Parameters
    ----------
    races : pd.DataFrame
        列 ``race_id`` と ``race_start_datetime`` を含むこと。
        各行は1レースを表す（重複 race_id は最初の1件に圧縮される）。
    n_splits : int
        fold 数。``n_unique_races`` 未満であること。

    Yields
    ------
    (train_rids, test_rids) : tuple[list[str], list[str]]
        各 fold の train/test race_id リスト（共に時系列順・train は index 0 から拡張）。

    Raises
    ------
    ValueError
        必須列が欠損 / ``n_splits >= n_unique_races`` / race_id disjoint 違反 /
        厳格時系列順序違反（等値タイムスタンプ跨ぎ含む） / train or test が空。
    """
    # --- 事前バリデーション ---
    required = {"race_id", "race_start_datetime"}
    missing = required - set(races.columns)
    if missing:
        raise ValueError(
            f"races must contain 'race_id' and 'race_start_datetime' columns; "
            f"missing={sorted(missing)} (§8.4/§15.4/D-17)"
        )

    # タイスタンプの tie-break を race_id 辞書順で安定化
    unique_races = (
        races.sort_values(["race_start_datetime", "race_id"])
        .drop_duplicates("race_id")["race_id"]
        .tolist()
    )
    n = len(unique_races)
    if n_splits >= n:
        raise ValueError(f"n_splits ({n_splits}) must be < n unique races ({n}) (§15.4/D-17)")

    # race_id -> race_start_datetime の lookup（guard 評価用）
    rid_to_time = races.drop_duplicates("race_id").set_index("race_id")["race_start_datetime"]

    for k in range(1, n_splits + 1):
        test_start = int((k / (n_splits + 1)) * n)
        test_end = int(((k + 1) / (n_splits + 1)) * n)
        train_rids = unique_races[:test_start]
        test_rids = unique_races[test_start:test_end]

        # --- ガード1: race_id disjoint ---
        if not set(train_rids).isdisjoint(set(test_rids)):
            raise ValueError(
                f"race_id leakage across train/test in fold {k}: "
                f"intersection={sorted(set(train_rids) & set(test_rids))} (§8.4/D-17)"
            )

        # --- ガード2: strict chronological（HIGH #2。等値不可） ---
        train_time_max = rid_to_time.loc[train_rids].max()
        test_time_min = rid_to_time.loc[test_rids].min()
        if not (train_time_max < test_time_min):
            raise ValueError(
                f"chronological boundary violated in fold {k}: "
                f"train_max={train_time_max} >= test_min={test_time_min} "
                f"(strict < required; equal-timestamp races must not cross, "
                f"§8.4/§15.4/D-17 HIGH #2)"
            )

        # --- ガード3: non-empty ---
        if len(train_rids) == 0 or len(test_rids) == 0:
            raise ValueError(
                f"empty train or test in fold {k}: "
                f"train={len(train_rids)}, test={len(test_rids)} (§15.4/D-17)"
            )

        yield train_rids, test_rids
