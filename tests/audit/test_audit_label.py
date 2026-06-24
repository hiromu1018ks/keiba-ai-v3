# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/test_label_reconcile.py と同一慣例)
"""SC#2 ケース2: 払戻テーブルで複勝対象(正)の馬が label に欠落すると reconcile が fail する adversarial。

本ファイルは SC#2 adversarial（注入型メタ検証）。``tests/test_label_reconcile.py``（機能テスト:
mock cursor でロジック検証）とは独立層。機能テストは「ロジックが正しく動く」を検証するのに対し・
本テストは「payout 不一致件数 N>0 を注入すると ``_check_payout_recall.passed is False`` になり
``reconcile_against_payout`` の ``verdict=='fail'`` になる（=リークがあれば検出される）」ことを
cursor ベース end-to-end で実証し・false-pass を構造的に排除する（T-08-01 mitigate・per D-02）。

注入手法: analog ``tests/test_label_reconcile.py::_mock_cursor`` の SQL 部分文字列マッチで
``_check_payout_recall`` の SQL（``fukusho_hit_validated = 0`` を含む）が ``fetchone() -> (1,)`` を
返すよう不一致件数 1 件を注入する。``reconcile_against_payout`` は cursor のみ受け取り・DataFrame
受けの API は存在しない（``src/etl/label_reconcile.py`` L933 署名 ``cur: Cursor``）。

cross-reference: tests/test_label_reconcile.py。
DB 不要（mock cursor 使用・KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.etl.label_reconcile import (
    _check_payout_recall,
    reconcile_against_payout,
)
from src.etl.quality_gate import CheckResult


def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    """SQL 文字列を部分文字列マッチ（``in``）で分類し ``fetchone()`` の戻り値を返すモック cursor。

    analog ``tests/test_label_reconcile.py::_mock_cursor`` L61-87 の複製（adversarial 注入用）。
    ``fetch_map`` のキーは SQL 部分文字列・値は ``fetchone()`` が返す tuple。
    未知の SELECT には安全な ``(0,)`` を返す（他の BLOCK 検査が通過するように）。
    """
    cur = MagicMock()
    cur._fetch_map = fetch_map  # noqa: SLF001

    def _execute(sql: str, *args, **kwargs):  # noqa: ANN002
        cur._last_sql = sql  # noqa: SLF001
        return cur

    cur.execute.side_effect = _execute

    def _fetchone():
        sql = getattr(cur, "_last_sql", "")
        for key, val in cur._fetch_map.items():  # noqa: SLF001
            if key in sql:
                return val
        if sql.strip().upper().startswith("SELECT"):
            return (0,)
        return None

    cur.fetchone.side_effect = _fetchone
    return cur


def test_payout_positive_missing_from_labels_detected() -> None:
    """SC#2 adversarial: 払戻テーブルで複勝対象(正)の馬が label.fukusho_hit_validated に欠落している
    場合・reconcile が verdict='fail' を返すことを cursor ベース end-to-end で実証。

    本テストは SC#2 adversarial（注入型メタ検証）であり・``tests/test_label_reconcile.py``
    （機能テスト: mock cursor でロジック検証）とは独立層。
    cross-reference: tests/test_label_reconcile.py。

    5段階鋳型（``test_no_target_encoding_leak`` 構造を payout recall に適用）:

      (1) mock cursor で ``_check_payout_recall`` SQL が不一致件数 1 を返すよう注入
      (2) ``_check_payout_recall(cur).passed is False`` を検証（BLOCK 検査が fail）
      (3) ``.detail["count"] == 1`` で注入件数が伝播することを検証
      (4) cursor ベース end-to-end で ``reconcile_against_payout(cur)["verdict"] == "fail"`` を検証
      (5) 検証力証明: 不一致件数 0 を注入すると ``passed is True``・``verdict`` が "fail" でない
          （false-pass 回避・T-08-01 mitigate）
    """
    # --- (1) mock cursor で _check_payout_recall SQL が不一致件数 1 を返すよう注入 ---
    # _check_payout_recall の SQL は "l.fukusho_hit_validated = 0" を含む（src/etl/label_reconcile.py L289）。
    # この部分文字列を fetch_map のキーにして (1,) を返す → cnt=1 → passed=False。
    cur = _mock_cursor({"fukusho_hit_validated = 0": (1,)})

    # --- (2) _check_payout_recall.passed is False を検証 ---
    result = _check_payout_recall(cur)
    assert isinstance(result, CheckResult), (
        "_check_payout_recall が CheckResult を返さない（契約違反）"
    )
    assert result.passed is False, (
        "payout 正欠損注入（不一致件数=1）でも _check_payout_recall.passed が False にならない "
        "(SC#2 adversarial fail・注入が検出されていない)"
    )
    assert result.severity == "block", (
        f"_check_payout_recall.severity が 'block' でない (actual={result.severity!r}・verdict 影響のため)"
    )

    # --- (3) .detail["count"] == 1 で注入件数が伝播 ---
    assert result.detail.get("count") == 1, (
        f"_check_payout_recall.detail['count'] が 1 でない (actual={result.detail.get('count')!r}・"
        "注入件数が伝播していない)"
    )

    # --- (4) cursor ベース end-to-end で reconcile_against_payout(cur)["verdict"] == "fail" ---
    # reconcile_against_payout は cursor のみ受け取り DataFrame 受けの API は存在しない
    # (src/etl/label_reconcile.py L933 署名 cur: Cursor)。
    # 他の BLOCK 検査（precision/dead_heat/scratch/dead_loss/no_fukusho_sale/raw_validated_drift）は
    # 未知の SELECT に (0,) を返す mock cursor で passed=True になる。
    end_to_end = reconcile_against_payout(cur)
    assert end_to_end["verdict"] == "fail", (
        f"reconcile_against_payout verdict が 'fail' でない (actual={end_to_end['verdict']!r}・"
        "_check_payout_recall passed=False なのに verdict が pass は BLOCK 集計バグ)"
    )
    # verdict='fail' の根拠として payout_recall の passed=False が存在することを確認
    block_checks = [c for c in end_to_end["checks"] if c["severity"] == "block"]
    recall_check = next((c for c in block_checks if c["name"] == "payout_recall"), None)
    assert recall_check is not None, "reconcile checks に payout_recall が含まれない（契約違反）"
    assert recall_check["passed"] is False, (
        "end-to-end で payout_recall.passed が False でない（注入が伝播していない）"
    )

    # --- (5) 検証力証明: 不一致件数 0 を注入すると passed is True・verdict が "fail" でない ---
    cur_clean = _mock_cursor({"fukusho_hit_validated = 0": (0,)})
    result_clean = _check_payout_recall(cur_clean)
    assert result_clean.passed is True, (
        "不一致件数=0 でも passed=True でない（検証力証明 fail・T-08-01 mitigate）"
    )
    assert result_clean.detail.get("count") == 0
    # 注入ゼロの end-to-end verdict は他 BLOCK 検査依存だが・payout_recall 単体は passed=True なことは確認済


def test_payout_recall_docstring_cross_reference() -> None:
    """本テストモジュールの docstring が SC#2 adversarial + cross-reference を含む（T-08-04 mitigate）。

    重複回避: 機能テスト ``tests/test_label_reconcile.py`` が「ロジック検証」をするのに対し・
    本 adversarial テストは「不一致件数注入 → verdict fail を end-to-end 実証」する（独立層）。
    """
    import sys

    module_doc = sys.modules[__name__].__doc__ or ""
    assert "SC#2 adversarial" in module_doc, (
        "モジュール docstring に SC#2 adversarial 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/test_label_reconcile.py" in module_doc, (
        "モジュール docstring に test_label_reconcile.py cross-reference がない（T-08-04 違反）"
    )
    test_doc = test_payout_positive_missing_from_labels_detected.__doc__ or ""
    assert "SC#2 adversarial" in test_doc, (
        "テスト docstring に SC#2 adversarial がない（T-08-04 違反）"
    )
    assert "cross-reference: tests/test_label_reconcile.py" in test_doc, (
        "テスト docstring に cross-reference がない（T-08-04 違反）"
    )
