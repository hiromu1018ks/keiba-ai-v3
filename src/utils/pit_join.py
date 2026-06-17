"""Point-in-Time (as-of) feature join のリーク防止 wrapper（成功基準#4 / §13）。

`pandas.merge_asof(direction="backward")` を薄く wrap し、呼出元が渡した
元の DataFrame 列の sortedness を **sort 前** に検証して違反時 ``raise ValueError`` する。

REVIEWS HIGH #1 / HIGH #3:
- HIGH #1: sortedness チェックは呼出元入力（sort 前）に対して行う。本関数内で
  入力を再ソートしない（契約違反を黙って吸収しない）。ソート後にチェックすると
  未ソート入力でも常に monotonic になり raise が到達不能になる。
- HIGH #3: リーク防止ガードは ``assert`` ではなく ``raise ValueError`` 形式
  （``python -O`` で削除されない）。
"""

from __future__ import annotations

import pandas as pd


def pit_join_backward(
    observations: pd.DataFrame,
    history: pd.DataFrame,
    on_cutoff: str = "feature_cutoff_datetime",
    on_asof: str = "as_of_datetime",
    by: str | list[str] = "horse_id",
    tolerance: pd.Timedelta | None = None,
) -> pd.DataFrame:
    """``merge_asof(direction="backward")`` のリーク防止 wrapper。

    各 observation 行に、``on_cutoff`` 時点以前の最新 history 値を付与する。
    未来情報が cutoff を跨がないことを構造的に保証する（§13）。

    **呼出元の契約（重要）:**
    - ``observations`` は ``on_cutoff`` 昇順に、``history`` は ``on_asof`` 昇順に
      **事前にソート** して渡す責任がある。
    - 本関数は呼出元入力を再ソートしない（ソート後にチェックすると未ソート入力が黙って
      通ってしまうため、REVIEWS HIGH #1）。未ソート入力は ``raise ValueError`` で即座に拒否する。

    Parameters
    ----------
    observations : pd.DataFrame
        結合先。列 ``on_cutoff``（feature_cutoff_datetime 相当）を含むこと。
    history : pd.DataFrame
        結合元。列 ``on_asof``（as_of_datetime 相当）を含むこと。
    on_cutoff : str
        observations 側の結合キー（時系列カットオフ）。
    on_asof : str
        history 側の結合キー（as-of タイムスタンプ）。
    by : str | list[str]
        エンティティ単位（``horse_id`` 等）。``merge_asof`` の ``by=`` に渡す。
        グループ内ソート済みかの追加検査は行わない（``on_cutoff`` / ``on_asof`` の
        **global sortedness** を検査すればグループ内も従属するため・CR-07）。
    tolerance : pd.Timedelta | None
        許容する履歴の古さ（これより古い履歴は付与しない）。

    Returns
    -------
    pd.DataFrame
        observations に cutoff 以前の最新 history 値が付与された DataFrame。

    Raises
    ------
    ValueError
        observations / history の ``on_cutoff`` / ``on_asof`` 列が **global に**
        （``is_monotonic_increasing`` で）ソートされていない場合。

    Notes
    -----
    ``pandas.merge_asof(by=...)`` は ``on=`` 列の **global sortedness**
    （``is_monotonic_increasing``）を要求する。per-group sortedness は global
    sortedness から従属するが、逆は成り立たない（per-group sorted ≠ global
    sorted）。従って本関数は global check のみを行い、per-group check は行わない
    （CR-07: 従来の per-group check は redundant であり、誤解を招く docstring が
    未来の maintainer に global check 削除を誘発する silent-leak リスクを回避する）。
    """
    # --- sortedness pre-check（呼出元入力・sort 前に検証・HIGH #1） ---
    # 注意: ここで入力を再ソートしてから is_monotonic_increasing を調べてはならない。
    # 再ソート後だと未ソート入力でも常に monotonic になり raise が到達不能になる。
    if on_cutoff not in observations.columns:
        raise ValueError(f"observations must have column '{on_cutoff}' (PIT join, §13/D-17)")
    if on_asof not in history.columns:
        raise ValueError(f"history must have column '{on_asof}' (PIT join, §13/D-17)")

    # CR-07: global sortedness が merge_asof の負担契約。per-group チェックは
    # redundant であり、誤 docstring が将来 global check 削除に繋がるのを防ぐため削除。
    if not observations[on_cutoff].is_monotonic_increasing:
        raise ValueError(
            f"observations must be sorted by {on_cutoff}; caller passed an unsorted "
            f"frame (PIT leak-prevention, §13/D-17)"
        )
    if not history[on_asof].is_monotonic_increasing:
        raise ValueError(
            f"history must be sorted by {on_asof}; caller passed an unsorted "
            f"frame (PIT leak-prevention, §13/D-17)"
        )

    return pd.merge_asof(
        observations,
        history,
        left_on=on_cutoff,
        right_on=on_asof,
        by=by,
        direction="backward",  # 過去の特徴量値のみ付与
        tolerance=tolerance,
    )
