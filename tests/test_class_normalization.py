"""DATA-03 クラス正規化の unit / integration test（Pitfall 7 / D-11 / D-13 / MEDIUM #3/#4）。

本テストは 01-VALIDATION.md §Phase Requirements → Test Map に準拠し、以下を保証する:
  - Pitfall 7: hondai（レース名）の regex マッチを使わず、jyokencd5+gradecd+year で
    機械導出する。コード '005' が 2018年（500万下）と 2019年後半（1勝クラス）で
    同じ class_level_numeric=1 になる（制度改革を跨ぐコード連続性）。
  - D-11: post_2019_class_system_flag は 2019-06-08 基準日（実測・夏季競馬開催初日）。
  - D-13: 未知コードは class_normalization_status='unresolved' で隔離（silent fallback 禁止）。
  - MEDIUM #3: ``date.fromisoformat`` を使用（``fromisoconfig`` typo ではない）。
  - MEDIUM #4: unresolved 時も ``post_2019_class_system_flag`` は race_date から計算（null 化しない）。

`@pytest.mark.requires_db` 付きテストは ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ skip される
（plan 01-01 conftest の fail-by-default policy と同一・HIGH #8）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


def test_module_loads_fromisoformat_not_typo() -> None:
    """MEDIUM #3 直接検証: ``date.fromisoformat`` 呼び出しを含み typo ``date.fromisoconfig`` は含まない。"""
    from src.etl import class_normalize

    import inspect

    src = inspect.getsource(class_normalize)
    # 実装内で date.fromisoformat 呼び出しが存在（docstring での言及は OK）
    assert "date.fromisoformat(" in src, (
        "class_normalize.py は date.fromisoformat を呼び出すべき（MEDIUM #3）"
    )
    # typo である date.fromisoconfig 関数呼び出しは存在しない
    assert "date.fromisoconfig(" not in src, (
        "date.fromisoconfig は typo・呼び出してはならない（MEDIUM #3）"
    )


def test_normalize_class_signature_and_no_hondai_match() -> None:
    """normalize_class が存在し、hondai の regex/match 操作を使わない（Pitfall 7 核心）。"""
    from src.etl import class_normalize

    import inspect

    assert hasattr(class_normalize, "normalize_class")
    assert hasattr(class_normalize, "load_class_config")
    # Pitfall 7 核心: 実装コード（normalize_class 関数本体内）で hondai を re.match / str.match /
    # str.contains 等の名称マッチに使わない。docstring での注意書きは許容（「hondai 名称マッチ
    # 不使用」という設計意図の記述）。
    src = inspect.getsource(class_normalize.normalize_class)
    forbidden = ("re.match", "re.search", "str.match", "str.contains", ".match(")
    for tok in forbidden:
        assert tok not in src, (
            f"normalize_class 本体は {tok} のような名称マッチを使ってはならない（Pitfall 7）"
        )


def test_code_005_spans_reform() -> None:
    """Pitfall 7 核心: jyokencd5='005' が 2018 でも 2019 後半でも class_level_numeric=1。"""
    from src.etl.class_normalize import normalize_class

    before = normalize_class("005", "", date(2018, 6, 1))
    after = normalize_class("005", "", date(2019, 7, 1))
    assert before["class_level_numeric"] == 1, "2018年（500万下）は class_level_numeric=1"
    assert after["class_level_numeric"] == 1, "2019年後半（1勝クラス）も class_level_numeric=1"


def test_reform_date_boundary() -> None:
    """D-11 境界: 2019-06-07 で False、2019-06-08 で True、2019-06-09 で True。"""
    from src.etl.class_normalize import normalize_class

    assert normalize_class("005", "", date(2019, 6, 7))["post_2019_class_system_flag"] is False
    assert normalize_class("005", "", date(2019, 6, 8))["post_2019_class_system_flag"] is True
    assert normalize_class("005", "", date(2019, 6, 9))["post_2019_class_system_flag"] is True


def test_grade_derivation_a_g1() -> None:
    """gradecd='A'（G1）→ is_grade_race=True, grade_numeric=1。"""
    from src.etl.class_normalize import normalize_class

    r = normalize_class("999", "A", date(2020, 1, 1))
    assert r["is_grade_race"] is True
    assert r["grade_numeric"] == 1


def test_grade_derivation_l_listed() -> None:
    """gradecd='L'（Listed）→ is_listed=True, is_grade_race=False。"""
    from src.etl.class_normalize import normalize_class

    r = normalize_class("999", "L", date(2020, 1, 1))
    assert r["is_listed"] is True
    assert r["is_grade_race"] is False


def test_grade_derivation_general_empty() -> None:
    """gradecd=''（一般条件戦）→ 全 flag False。"""
    from src.etl.class_normalize import normalize_class

    r = normalize_class("005", "", date(2020, 1, 1))
    assert r["is_grade_race"] is False
    assert r["is_listed"] is False
    assert r["is_open_class"] is False


def test_unresolved_unknown_jyokencd5_still_returns_post_2019_flag() -> None:
    """D-13 + MEDIUM #4: 未知 jyokencd5 は unresolved・ただし post_2019_flag は race_date から計算。"""
    from src.etl.class_normalize import normalize_class

    r = normalize_class("ZZZ", "", date(2020, 1, 1))
    assert r["class_normalization_status"] == "unresolved"
    assert r["class_level_numeric"] is None
    # MEDIUM #4: unresolved でも post_2019_flag は計算済み
    assert r["post_2019_class_system_flag"] is True, (
        "unresolved 時も post_2019_class_system_flag は race_date から計算すること（MEDIUM #4）"
    )


def test_unresolved_unknown_gradecd_still_returns_post_2019_flag() -> None:
    """D-13: 未知 gradecd も unresolved・post_2019_flag は計算済み。"""
    from src.etl.class_normalize import normalize_class

    r = normalize_class("005", "Z", date(2018, 1, 1))
    assert r["class_normalization_status"] == "unresolved"
    assert r["post_2019_class_system_flag"] is False


def test_unresolved_gradecd_fgh() -> None:
    """plan 01-01 MEDIUM #2 と整合: F/G/H は明示 unresolved として扱われる。"""
    from src.etl.class_normalize import normalize_class

    for g in ("F", "G", "H"):
        r = normalize_class("999", g, date(2020, 1, 1))
        assert r["class_normalization_status"] == "unresolved", (
            f"gradecd={g} は unresolved 扱い（plan 01-01 MEDIUM #2）"
        )


def test_normalize_race_classes_adds_columns() -> None:
    """DataFrame に class_* 列が追加される（複数行）。"""
    from src.etl.class_normalize import normalize_race_classes

    df = pd.DataFrame(
        {
            "jyokencd5": ["005", "999", "ZZZ"],
            "gradecd": ["", "A", ""],
            "year": [2018, 2020, 2020],
            "monthday": ["0601", "0101", "0101"],
        }
    )
    out = normalize_race_classes(df)
    for col in (
        "class_code_normalized",
        "class_name_normalized",
        "class_level_numeric",
        "post_2019_class_system_flag",
        "is_grade_race",
        "is_listed",
        "is_open_class",
        "grade_numeric",
        "class_normalization_status",
    ):
        assert col in out.columns, f"normalize_race_classes は {col} を追加すべき"

    # 1行目（2018年・005）は resolved
    assert out.loc[0, "class_normalization_status"] == "resolved"
    assert out.loc[0, "class_level_numeric"] == 1
    # 2行目（2020年・999/A）は resolved で grade G1
    assert out.loc[1, "is_grade_race"] == True  # noqa: E712
    # 3行目（ZZZ・未知）は unresolved
    assert out.loc[2, "class_normalization_status"] == "unresolved"


@pytest.mark.requires_db
def test_audit_gradecd_d_by_syubetucd() -> None:
    """RESEARCH Open Question #1: gradecd='D' が平地G3 か障害 かを交差確認（実DB）。

    syubetucd='18'/'19' は障害（§7.3 モデル除外）。件数分布を INFO として検証する。
    """
    from src.etl.class_normalize import audit_gradecd_d_by_syubetucd

    result = audit_gradecd_d_by_syubetucd.__doc__  # doc 存在確認用（dumy）
    # conftest の readonly_cur fixture を使うため、関数は cursor を取る
    # ここでは pytest fixture 経由で渡す
    # ※ このテストは下の parametrized 版で実DB呼出を行う
    # （マーク重複を避けるため、ここでは関数の存在だけ検証）
    assert callable(audit_gradecd_d_by_syubetucd)


@pytest.mark.requires_db
def test_audit_gradecd_d_by_syubetucd_on_db(readonly_cur) -> None:  # noqa: ANN001
    """実DB で audit を実行し、戻り値 rows が空でないこと・gradecd∈{C,D} のみを含むこと。"""
    from src.etl.class_normalize import audit_gradecd_d_by_syubetucd

    result = audit_gradecd_d_by_syubetucd(readonly_cur)
    assert "rows" in result
    rows = result["rows"]
    assert len(rows) > 0, "gradecd IN ('C','D') の実データが存在するはず"
    for row in rows:
        assert row["gradecd"] in {"C", "D"}, f"gradecd は C/D のみ想定: {row}"
        assert "syubetucd" in row
        assert "count" in row
