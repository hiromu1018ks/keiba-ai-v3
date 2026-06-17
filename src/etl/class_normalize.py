"""DATA-03 クラス正規化: ``class_normalization.yaml`` を適用し、機械導出する。

仕様（01-CONTEXT.md D-09/D-10/D-11/D-12/D-13 / Pitfall 7 / REVIEWS MEDIUM #3/#4）:

  - ``jyokencd5`` × ``gradecd`` × ``race_date`` の3軸で ``class_*`` / ``is_grade_race`` /
    ``post_2019_class_system_flag`` 等を機械導出する。
  - **Pitfall 7:** ``hondai``（レース名）の regex マッチは**一切使用しない**。レース名は
    改革（2019-06-08）で改名されるため、名称マッチは制度改革を跨ぐコード連続性を破る。
  - **D-11:** ``post_2019_class_system_flag`` は ``race_date >= 2019-06-08``（実測: 夏季競馬
    開催初日 = 新クラス体系適用開始）で True。**MEDIUM #4:** unresolved 分岐でも race_date
    から独立に計算し、None にしない。
  - **D-13:** ``jyokencd5`` / ``gradecd`` が対応表に無い場合は silent fallback せず
    ``class_normalization_status='unresolved'`` として隔離する。未知コードを勝手に '999' 等
    にマップしない。
  - **MEDIUM #3:** ``date.fromisoformat`` を使用する（``fromisoconfig`` は typo）。

RESEARCH Open Question #1（gradecd='D' の平地 vs 障害 G3 判定）は
``audit_gradecd_d_by_syubetucd`` で実測し、Phase 4 特徴量設計での再調整判断材料とする。
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from psycopg import Cursor

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("src/config/class_normalization.yaml")


def load_class_config(path: str | Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """``class_normalization.yaml`` を読み込み dict で返す。

    ``post_2019_class_system_reform_date`` 文字列は ``date.fromisoformat`` で parse する
    （MEDIUM #3: ``date.fromisoconfig`` は typo・存在しない）。
    """
    with Path(path).open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    reform_str = cfg.get("post_2019_class_system_reform_date")
    if reform_str is None:
        raise ValueError(
            "class_normalization.yaml に post_2019_class_system_reform_date が未設定"
        )
    # MEDIUM #3: date.fromisoformat（fromisoconfig ではない）
    cfg["_post_2019_reform_date_parsed"] = date.fromisoformat(str(reform_str))
    return cfg


def _compute_post_2019_flag(race_date: date, *, config: dict[str, Any]) -> bool:
    """D-11 + MEDIUM #4: race_date から ``post_2019_class_system_flag`` を計算する。

    unresolved 分岐からも呼ばれ、race_date が与えられる限り常に計算する（None にしない）。
    """
    reform_date: date = config["_post_2019_reform_date_parsed"]
    return race_date >= reform_date


def normalize_class(
    jyokencd5: str,
    gradecd: str,
    race_date: date,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``jyokencd5`` + ``gradecd`` + ``race_date`` からクラス正規化結果を機械導出する。

    Pitfall 7: ``hondai`` 等のレース名は**一切使用しない**。
    D-13: 未知コードは ``class_normalization_status='unresolved'`` として隔離。
    MEDIUM #4: unresolved 時も ``post_2019_class_system_flag`` は race_date から計算。

    Returns:
        以下のキーを持つ dict:
          - ``class_code_normalized`` (str | None)
          - ``class_name_normalized`` (str | None)
          - ``class_level_numeric`` (int | None)
          - ``post_2019_class_system_flag`` (bool) — 常に計算（MEDIUM #4）
          - ``is_grade_race`` (bool | None)
          - ``is_listed`` (bool | None)
          - ``is_open_class`` (bool | None)
          - ``grade_numeric`` (int | None)
          - ``class_normalization_status`` ("resolved" | "unresolved")
    """
    if config is None:
        config = load_class_config()

    # MEDIUM #4: unresolved どうかにかかわらず常に計算
    post_2019_flag = _compute_post_2019_flag(race_date, config=config)

    j5_str = "" if jyokencd5 is None else str(jyokencd5)
    g_str = "" if gradecd is None else str(gradecd)

    jyokencd5_map: dict[str, Any] = config.get("jyokencd5_map", {})
    gradecd_map: dict[str, Any] = config.get("gradecd_map", {})

    j5_entry = jyokencd5_map.get(j5_str)
    g_entry = gradecd_map.get(g_str)

    # gradecd エントリが ``class_normalization_status: unresolved`` を持つ場合は D-13 で隔離
    gradecd_unresolved = isinstance(g_entry, dict) and (
        g_entry.get("class_normalization_status") == "unresolved"
    )

    base = {
        "class_code_normalized": None,
        "class_name_normalized": None,
        "class_level_numeric": None,
        "post_2019_class_system_flag": post_2019_flag,
        "is_grade_race": None,
        "is_listed": None,
        "is_open_class": None,
        "grade_numeric": None,
        "class_normalization_status": "unresolved",
    }

    if j5_entry is None or g_entry is None or gradecd_unresolved:
        # D-13: unresolved 隔離。ただし post_2019_flag は保持（MEDIUM #4）
        missing: list[str] = []
        if j5_entry is None:
            missing.append(f"jyokencd5={j5_str!r}")
        if g_entry is None:
            missing.append(f"gradecd={g_str!r}")
        elif gradecd_unresolved:
            missing.append(f"gradecd={g_str!r}（unresolved エントリ・01-RESEARCH.md で未検証）")
        logger.warning(
            "class_normalize unresolved: %s (race_date=%s) — silent fallback せず隔離",
            ", ".join(missing),
            race_date.isoformat(),
        )
        return base

    # 両方 resolved の対応表エントリが存在
    class_level_numeric = j5_entry.get("class_level_numeric")
    class_name_normalized = j5_entry.get("class_name_normalized")
    is_grade_race = bool(g_entry.get("is_grade_race", False))
    is_listed = bool(g_entry.get("is_listed", False))
    is_open_class = bool(g_entry.get("is_open_class", False))
    grade_numeric = g_entry.get("grade_numeric")

    return {
        "class_code_normalized": j5_str,
        "class_name_normalized": class_name_normalized,
        "class_level_numeric": class_level_numeric,
        "post_2019_class_system_flag": post_2019_flag,
        "is_grade_race": is_grade_race,
        "is_listed": is_listed,
        "is_open_class": is_open_class,
        "grade_numeric": grade_numeric,
        "class_normalization_status": "resolved",
    }


def normalize_race_classes(
    df: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """pandas DataFrame に ``normalize_class`` を行適用し ``class_*`` 列を追加する。

    必須列: ``jyokencd5``, ``gradecd``, ``year``, ``monthday``。
    ``race_date`` は ``(year, monthday)`` から ``datetime.strptime(..., '%Y%m%d').date()``
    で構築する（Pitfall 1: 文字列ソートではなく date オブジェクトで比較）。
    """
    if config is None:
        config = load_class_config()

    out = df.copy()
    # race_date 構築（行毎）
    race_dates: list[date | None] = []
    for _, row in out.iterrows():
        try:
            y = int(row["year"])
            md = str(row["monthday"]).zfill(4)
            race_dates.append(date.fromisoformat(f"{y:04d}{md}"))
        except (ValueError, TypeError, KeyError):
            race_dates.append(None)

    class_cols = [
        "class_code_normalized",
        "class_name_normalized",
        "class_level_numeric",
        "post_2019_class_system_flag",
        "is_grade_race",
        "is_listed",
        "is_open_class",
        "grade_numeric",
        "class_normalization_status",
    ]
    for col in class_cols:
        out[col] = None

    unresolved_count = 0
    for i, rd in enumerate(race_dates):
        if rd is None:
            unresolved_count += 1
            out.at[i, "class_normalization_status"] = "unresolved"
            continue
        result = normalize_class(
            str(out.at[i, "jyokencd5"]),
            str(out.at[i, "gradecd"]),
            rd,
            config=config,
        )
        for col in class_cols:
            out.at[i, col] = result[col]
        if result["class_normalization_status"] == "unresolved":
            unresolved_count += 1

    if unresolved_count > 0:
        logger.warning(
            "normalize_race_classes: %d/%d 行が unresolved（D-13 隔離）",
            unresolved_count,
            len(out),
        )

    return out


def audit_gradecd_d_by_syubetucd(
    read_cur: Cursor,
    *,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> dict[str, Any]:
    """RESEARCH Open Question #1: ``gradecd IN ('C','D')`` の ``syubetucd`` 分布を実測する。

    plan 01-01 で ``gradecd='D'`` を暫定 ``grade_numeric=3`` として扱ったが、D が平地G3 か
    障害G3（``syubetucd='18'/'19'``）かで``is_grade_race`` の意味が変わる。本 cross-check の
    実測結果（平地 vs 障害の混在比率）を 01-03 SUMMARY で報告し、必要に応じて Phase 4
    特徴量設計で再調整する。

    クエリは JRA 限定（``jyocd BETWEEN '01' AND '10'``・Pitfall 2）。

    Returns:
        ``{"rows": [{"gradecd": "C", "syubetucd": "00", "count": N}, ...]}``
    """
    sql = (
        "SELECT gradecd, syubetucd, count(*) AS count "
        "FROM public.n_race "
        "WHERE jyocd BETWEEN '01' AND '10' AND gradecd IN ('C','D') "
        "GROUP BY 1, 2 ORDER BY 1, 2"
    )
    read_cur.execute(sql)
    rows = [
        {"gradecd": r[0], "syubetucd": r[1], "count": int(r[2])}
        for r in read_cur.fetchall()
    ]
    return {"rows": rows}


__all__ = [
    "load_class_config",
    "normalize_class",
    "normalize_race_classes",
    "audit_gradecd_d_by_syubetucd",
]
