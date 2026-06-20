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

Phase 5 追加（BACK-01 / §15.5）:
- ``BTWindow`` / ``BT_WINDOWS`` / ``get_bt_race_ids`` — BT-1..5 固定窓 helper。
  既存 ``race_id_time_series_split`` と同一のリーク防止ガード（race_id disjoint +
  strict chronological）を race_date 区間 filter の後段に適用する。

**MEDIUM-01a（固定 BT窓と mlxtend.GroupTimeSeriesSplit の等価性）:**
``get_bt_race_ids`` は race_date 区間で train/test を分離するが、race_id-level disjoint
と strict chronological（``max(train) < min(test)``）の本質的保証は
``mlxtend.evaluate.GroupTimeSeriesSplit`` が提供する group-aware 時系列分割と同一である。
§15.5 がレース日で明示的な窓を指定しているため固定区間を採用したが、リーク防止
（race_id 漏洩構造的不可・時系列逆転不可）の観点では両者は等価である。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

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


# =============================================================================
# Phase 5 BACK-01: BT-1..5 固定窓 helper（§15.5 完全準拠・2019-06 開始）
#
# 既存 ``race_id_time_series_split`` は expanding-window CV のみを生成するため、
# §15.5 が規定する BT-1..5（例: BT-1 train 2019-06→2022 / test 2023）のような
# 固定-window backtest を表現できない。本ヘルパは race_date 区間 filter + 既存3ガード
# （race_id disjoint / strict chronological / non-empty）と同一の ``raise ValueError``
# 形式でリーク防止を保証する。
#
# **MEDIUM-01a（固定 BT窓と mlxtend.GroupTimeSeriesSplit の等価性）:**
# 本ヘルパが行う race_date 区間分割と ``mlxtend.evaluate.GroupTimeSeriesSplit`` の
# group-aware 時系列分割は、どちらも race_id-level disjoint + strict chronological を
# 保証する。race_id が区間境界を跨ぐことは構造的に不可能であり、``max(train) < min(test)``
# も ``race_date`` 昇順で保証される。したがってリーク防止の観点で両者は等価である。
# §15.5 が明示的な暦日で窓を指定しているため固定区間を採用したが、これは GroupTimeSeriesSplit
# が担保する race_id disjoint / 時系列順序と同一の保証を持つ（T-05-01b mitigate）。
# =============================================================================


@dataclass(frozen=True)
class BTWindow:
    """§15.5 BT窓定義（不変・frozen）。

    Attributes
    ----------
    name : str
        窓名（``'BT-1'`` .. ``'BT-5'``）。
    train_start : str
        train 期間開始日（``'YYYY-MM-DD'``）。
    train_end : str
        train 期間終了日。
    test_start : str
        test 期間開始日。
    test_end : str
        test 期間終了日。
    window_type : str
        ``'expanding'``（BT-1..3）または ``'rolling'``（BT-4/5）。
    """

    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    window_type: str


# §15.5 完全準拠・BT-1..3 train_start='2019-06-01'（Phase 3 D-09 の 2016H2〜 でなく
# 要件正を適用・CLAUDE.md「要件定義書優先」・T-05-02 mitigate）
BT_WINDOWS: list[BTWindow] = [
    BTWindow(
        name="BT-1",
        train_start="2019-06-01",
        train_end="2022-12-31",
        test_start="2023-01-01",
        test_end="2023-12-31",
        window_type="expanding",
    ),
    BTWindow(
        name="BT-2",
        train_start="2019-06-01",
        train_end="2023-12-31",
        test_start="2024-01-01",
        test_end="2024-12-31",
        window_type="expanding",
    ),
    BTWindow(
        name="BT-3",
        train_start="2019-06-01",
        train_end="2024-12-31",
        test_start="2025-01-01",
        test_end="2025-12-31",
        window_type="expanding",
    ),
    # BT-4/5: rolling（test 年の直近3年/5年 train・D-03 + planner A2 で test 年を 2024 に揃える）
    BTWindow(
        name="BT-4",
        train_start="2021-01-01",
        train_end="2023-12-31",
        test_start="2024-01-01",
        test_end="2024-12-31",
        window_type="rolling",
    ),
    BTWindow(
        name="BT-5",
        train_start="2019-01-01",
        train_end="2023-12-31",
        test_start="2024-01-01",
        test_end="2024-12-31",
        window_type="rolling",
    ),
]


def get_bt_race_ids(
    races: pd.DataFrame,
    bt: BTWindow,
) -> tuple[list[str], list[str]]:
    """BT窓の ``(train_race_ids, test_race_ids)`` を返す（race_date filter + guard）。

    ``races`` を ``race_date`` で BT窓区間に filter し、既存
    ``race_id_time_series_split`` と同一の3ガード（race_id disjoint / strict
    chronological / non-empty）を ``raise ValueError`` 形式で保証する
    （``python -O`` で削除されない・HIGH #3 / T-05-01 mitigate）。

    **MEDIUM-01a（mlxtend.GroupTimeSeriesSplit との等価性）:**
    本関数の race_date 区間分割は、``mlxtend.evaluate.GroupTimeSeriesSplit`` が保証する
    group-aware 時系列分割（race_id disjoint + strict chronological）と本質的に等価である。
    race_id が区間境界を跨ぐことは構造的に不可能（同一 race_id は単一 race_date に属す）で
    あり、``max(train.race_start_datetime) < min(test.race_start_datetime)`` も race_date
    昇順で自動的に満たされる。§15.5 が明示的暦日で窓を指定しているため固定区間を採用したが、
    リーク防止保証は GroupTimeSeriesSplit と同一である（T-05-01b mitigate）。

    Parameters
    ----------
    races : pd.DataFrame
        列 ``race_id`` / ``race_date`` / ``race_start_datetime`` を含むこと。
        各行は1レースを表す（重複 race_id は最初の1件に圧縮される）。
    bt : BTWindow
        BT窓定義。

    Returns
    -------
    (train_race_ids, test_race_ids) : tuple[list[str], list[str]]
        ともに race_id 昇順（決定論的・再現性保証）。

    Raises
    ------
    ValueError
        必須列が欠損 / train と test で race_id が共有されている（漏洩） /
        ``max(train.race_start_datetime) >= min(test.race_start_datetime)``
        （strict chronological 違反） / train or test が空。
    """
    required = {"race_id", "race_date", "race_start_datetime"}
    missing = required - set(races.columns)
    if missing:
        raise ValueError(
            f"races must contain 'race_id', 'race_date' and 'race_start_datetime' columns; "
            f"missing={sorted(missing)} (§15.5/BACK-01)"
        )

    unique = races.drop_duplicates("race_id")
    train = unique[unique["race_date"].between(bt.train_start, bt.train_end)]
    test = unique[unique["race_date"].between(bt.test_start, bt.test_end)]

    train_ids = set(train["race_id"])
    test_ids = set(test["race_id"])

    # --- ガード1: race_id disjoint（T-05-01） ---
    if not train_ids.isdisjoint(test_ids):
        raise ValueError(
            f"{bt.name}: race_id leak across train/test: "
            f"intersection={sorted(train_ids & test_ids)} (§8.4/BACK-01/T-05-01)"
        )

    # --- ガード2: strict chronological（max(train) < min(test)・HIGH #2 と同一） ---
    if len(train) > 0 and len(test) > 0:
        train_max = train["race_start_datetime"].max()
        test_min = test["race_start_datetime"].min()
        if not (train_max < test_min):
            raise ValueError(
                f"{bt.name}: chronological boundary violated: "
                f"train_max={train_max} >= test_min={test_min} "
                f"(strict < required; §8.4/§15.5/BACK-01)"
            )

    # --- ガード3: non-empty ---
    if len(train_ids) == 0 or len(test_ids) == 0:
        raise ValueError(
            f"{bt.name}: empty train or test window: "
            f"train={len(train_ids)}, test={len(test_ids)} (§15.5/BACK-01)"
        )

    return sorted(train_ids), sorted(test_ids)
