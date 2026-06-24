# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/utils/test_group_split.py と同一慣例)
"""SC#2 ケース3: fold の train/test が race_id を共有すると ValueError で検出される adversarial。

本ファイルは SC#2 adversarial（注入型メタ検証）。SC#2 要件「3ケースそれぞれ独立 adversarial」を
docstring で明示するための再定式化（``tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak``
が既存・同一注入パターン）。機能テストは「正しく分割される」を検証するのに対し・本テストは
「BTWindow で train/test が race_id を共有するよう意図的に注入すると ``ValueError`` が raise される
（=リークがあれば検出される）」ことを実証する（T-08-01 mitigate・per D-02）。

注入手法: analog ``tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak`` L208-234 と
同一構造。``train_end == test_start`` で R2 を共有する ``BTWindow`` を注入し・
``get_bt_race_ids`` が ``ValueError(match='race_id')`` を raise することを検証する。

cross-reference: tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak（既存・同一注入パターン）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.utils.group_split import BTWindow, get_bt_race_ids


def test_fold_race_id_shared_detected_and_raises() -> None:
    """SC#2 adversarial: fold の train/test が race_id を共有すると ValueError で検出される。

    本テストは SC#2 adversarial（注入型メタ検証）。cross-reference: tests/utils/test_group_split.py
    （既存・同一注入パターン ``test_get_bt_race_ids_raises_on_leak``）。
    SC#2 要件「3ケースそれぞれ独立 adversarial」を docstring で明示するため再定式化。

    5段階鋳型（``test_no_target_encoding_leak`` 構造を fold race_id 共有に適用）:

      (1) 合成 races 構築（R0-R3・race_date/race_start_datetime 昇順・seed 固定相当）
      (2) BTWindow で ``train_end == test_start`` にして R2 を意図的に共有（リーク注入）
      (3) ``get_bt_race_ids(leak_races, bad_bt)`` が ``ValueError(match='race_id')`` を raise することを検証
      (4) 検証力証明: 共有しない正常 BTWindow では raise しない（false-pass 回避・T-08-01 mitigate）
    """
    # --- (1) 合成 races 構築（analog test_get_bt_race_ids_raises_on_leak と同一構造）---
    leak_races = pd.DataFrame(
        {
            "race_id": ["R0", "R1", "R2", "R3"],
            "race_date": pd.to_datetime(
                ["2022-12-30", "2022-12-31", "2023-01-01", "2023-01-02"]
            ),
            "race_start_datetime": pd.to_datetime(
                ["2022-12-30", "2022-12-31", "2023-01-01", "2023-01-02"]
            ),
        }
    )

    # --- (2) BTWindow で train_end == test_start にして R2 を意図的に共有（リーク注入）---
    bad_bt = BTWindow(
        name="BT-LEAK",
        train_start="2022-12-30",
        train_end="2023-01-01",   # R2 (race_date=2023-01-01) を含む
        test_start="2023-01-01",  # R2 を含む（train/test で共有＝リーク）
        test_end="2023-01-02",
        window_type="expanding",
    )

    # --- (3) get_bt_race_ids が ValueError(match='race_id') を raise することを検証 ---
    with pytest.raises(ValueError, match="race_id"):
        get_bt_race_ids(leak_races, bad_bt)

    # --- (4) 検証力証明: 共有しない正常 BTWindow では raise しない（false-pass 回避）---
    # R2 を train だけに含み・test は R3 単独に切り離す（race_id disjoint・strict chronological）
    good_bt = BTWindow(
        name="BT-OK",
        train_start="2022-12-30",
        train_end="2023-01-01",   # R0, R1, R2
        test_start="2023-01-02",  # R3 のみ（R2 と共有しない）
        test_end="2023-01-02",
        window_type="expanding",
    )
    train_ids, test_ids = get_bt_race_ids(leak_races, good_bt)
    train_set = set(train_ids)
    test_set = set(test_ids)
    assert train_set.isdisjoint(test_set), (
        f"正常 BTWindow で train/test が race_id を共有している (train={train_set}, test={test_set}・"
        "検証力証明 fail・false-pass 回避不能)"
    )
    assert "R2" in train_set and "R2" not in test_set, (
        "R2 が train のみに含まれない（正常分割の前提違反）"
    )
    assert test_set == {"R3"}, (
        f"正常 BTWindow の test が R3 単独でない (actual={test_set}・検証力証明の前提)"
    )


def test_fold_race_id_shared_docstring_cross_reference() -> None:
    """本テストモジュールの docstring が SC#2 adversarial + cross-reference を含む（T-08-04 mitigate）。

    重複回避: 既存 ``tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak`` が
    同一注入パターンを検証済み・本テストは SC#2「3ケース独立 adversarial」要件のための再定式化。
    """
    import sys

    module_doc = sys.modules[__name__].__doc__ or ""
    assert "SC#2 adversarial" in module_doc, (
        "モジュール docstring に SC#2 adversarial 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/utils/test_group_split.py" in module_doc, (
        "モジュール docstring に test_group_split.py cross-reference がない（T-08-04 違反）"
    )
    test_doc = test_fold_race_id_shared_detected_and_raises.__doc__ or ""
    assert "SC#2 adversarial" in test_doc, (
        "テスト docstring に SC#2 adversarial がない（T-08-04 違反）"
    )
    assert "cross-reference: tests/utils/test_group_split.py" in test_doc, (
        "テスト docstring に cross-reference がない（T-08-04 違反）"
    )
