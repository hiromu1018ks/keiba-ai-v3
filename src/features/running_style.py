"""推定脚質（逃/先/差/追）算出（Phase 3 Plan 03-03 Task 2 / D-05 / Pitfall 3.2）.

過去走の ``jyuni3c``（3コーナー通過順位）/ ``jyuni4c``（4コーナー通過順位）のみから
閾値ルールで推定脚質を算出する。**当日の脚質区分（SE #73・post_race_only・D-05）は
絶対に使わない**（当日情報リーク防止・regression guard 付）。

D-05 / Pitfall 3.2 の要点:
  - ``jyuni1c``（1コーナー通過順位）は短距離（芝1200m等）で約57% が 0/NULL（1コーナー
    不存在）のため**主軸にしない**。本 module は ``valid`` filter で ``jyuni3c``/``jyuni4c``
    が共に >0 の走のみを用いる。
  - 新馬（history 空）・全走で3/4コーナー位置不明の場合は ``__MISSING__`` sentinel を返す
    （D-13 silent fallback 禁止）。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.utils.category_map import MISSING

# 閾値（RESEARCH Example 2 line 444-481）・avg_position = (avg_jyuni3c + avg_jyuni4c) / 2
#   <= 2.0 -> 逃 / <= 3.5 -> 先 / <= 5.5 -> 差 / > 5.5 -> 追
_THRESHOLD_OOGE = 2.0      # 逃（逃げ）
_THRESHOLD_SEN = 3.5       # 先（先行）
_THRESHOLD_SASHI = 5.5     # 差（差し）


def classify_running_style(avg_position: float) -> str:
    """平均通過位置 ``avg_position`` を閾値ルールで脚質コードに分類する。

    閾値（RESEARCH Example 2）:
      - ``avg_position <= 2.0`` -> ``"逃"``（逃げ）
      - ``avg_position <= 3.5`` -> ``"先"``（先行）
      - ``avg_position <= 5.5`` -> ``"差"``（差し）
      - ``avg_position > 5.5``  -> ``"追"``（追い込み）

    Parameters
    ----------
    avg_position : float
        過去走の ``jyuni3c``/``jyuni4c`` 平均の更なる平均（両コーナー位置で安定化）。

    Returns
    -------
    str
        ``"逃"`` / ``"先"`` / ``"差"`` / ``"追"`` のいずれか。
    """
    if avg_position <= _THRESHOLD_OOGE:
        return "逃"
    if avg_position <= _THRESHOLD_SEN:
        return "先"
    if avg_position <= _THRESHOLD_SASHI:
        return "差"
    return "追"


def estimate_running_style(history_rows: Iterable[dict[str, Any]] | Any) -> str:
    """過去走 dict list から推定脚質を算出する。

    ``jyuni3c`` / ``jyuni4c`` が共に >0（短距離の ``jyuni1c=0`` は無視・Pitfall 3.2）
    の走のみを valid とし、両コーナー平均位置の更なる平均から ``classify_running_style``
    で閾値分類する。当日の脚質区分（SE #73・post_race_only）は絶対に使用しない（D-05）。

    Parameters
    ----------
    history_rows : iterable of dict
        過去走の辞書リスト（1走 = 1 dict）。各 dict は ``jyuni3c`` / ``jyuni4c`` を含むこと。
        ``jyuni1c`` が含まれていても無視（主軸にしない・Pitfall 3.2）。空 iterable は新馬。

    Returns
    -------
    str
        ``"逃"`` / ``"先"`` / ``"差"`` / ``"追"`` のいずれか、または ``__MISSING__``
        （新馬・全走で3/4コーナー位置不明・D-13）。
    """
    # 新馬（history 空）-> __MISSING__（D-13）
    rows = list(history_rows) if history_rows is not None else []
    if len(rows) == 0:
        return MISSING

    # valid filter: jyuni3c と jyuni4c が共に >0（0/NULL を除外・短距離 pitfall 回避）
    valid: list[tuple[float, float]] = []
    for r in rows:
        j3 = r.get("jyuni3c")
        j4 = r.get("jyuni4c")
        try:
            j3f = float(j3) if j3 is not None else 0.0
            j4f = float(j4) if j4 is not None else 0.0
        except (TypeError, ValueError):
            continue
        if j3f > 0 and j4f > 0:
            valid.append((j3f, j4f))

    # 全走で3/4コーナー位置不明 -> __MISSING__（Pitfall 3.2・稀）
    if len(valid) == 0:
        return MISSING

    avg_jyuni3c = sum(j3 for j3, _ in valid) / len(valid)
    avg_jyuni4c = sum(j4 for _, j4 in valid) / len(valid)
    avg_position = (avg_jyuni3c + avg_jyuni4c) / 2.0
    return classify_running_style(avg_position)


def estimate_running_style_batch(
    history_by_horse: Any,
) -> pd.Series:  # noqa: F821 (pandas import below for type only)
    """groupby 適用用 vectorized 版（builder で ``history.groupby("kettonum").apply(...)``）。

    各グループ（1馬の過去走 DataFrame）に ``estimate_running_style`` を適用し、
    脚質コード文字列（または ``__MISSING__``）を返す。戻り値は ``pd.Series``（index=kettonum）。

    Parameters
    ----------
    history_by_horse : pd.core.groupby.DataFrameGroupBy
        ``kettonum`` で group化された過去走 DataFrame groupby object。各 group は
        ``jyuni3c`` / ``jyuni4c`` 列を含むこと。

    Returns
    -------
    pd.Series
        index=kettonum・値は ``"逃"`` / ``"先"`` / ``"差"`` / ``"追"`` / ``__MISSING__``。
    """
    import pandas as pd

    def _per_group(group: pd.DataFrame) -> str:  # noqa: F821
        rows = group[["jyuni3c", "jyuni4c"]].to_dict(orient="records") if len(group) > 0 else []
        return estimate_running_style(rows)

    return history_by_horse.apply(_per_group)
