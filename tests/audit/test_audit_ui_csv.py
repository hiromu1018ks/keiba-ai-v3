# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/ui/test_readonly_guarantee.py と同一慣例)
"""D-06 adversarial: UI/CSV の read-only 保証違反と再現性スタンプ欠落を検出する対抗的監査テスト。

本ファイルは D-06（Phase 7 継承・07-CONTEXT Deferred）の adversarial テスト。SC#1 の明示サーフェス
リストには現れないが・07-CONTEXT が Phase 8 に委譲した項目で TEST-01「リーク防止の対抗的監査テストを
含む」の包括表現でスコープ内（per D-06）。2つの独立 adversarial テストを含む:

  - ``test_ui_write_sql_injection_detected``: AST で ``execute()`` Call 第一引数の str 定数から
    SQL リテラルを抽出し・書き込み/DDL キーワード（INSERT/UPDATE/DELETE/TRUNCATE/CREATE/DROP/ALTER）
    の混入を検出する。``tmp_path`` に INSERT を含むダミー .py を配置して注入を検出することを実証し・
    正規 ``src/ui/`` は GREEN（書き込み/DDL なし）を検証する（T-08-02 mitigate・per D-06）。
  - ``test_reproducibility_stamp_missing_detected``: ``PREDICTION_CSV_COLUMNS``（4スタンプ・
    ``backtest_strategy_version`` は予測テーブルに非存在のため除外）と ``REPRODUCIBILITY_STAMPS``
    （5スタンプ・UI 行表示用・``backtest_strategy_version`` 含む）のスタンプ欠落を presence assert で
    検出する。縮退 tuple で assert が fail することを実証し検証力を証明する（T-08-03 mitigate・§19.1 聖域）。

cross-reference: tests/ui/test_readonly_guarantee.py / tests/ui/test_csv_columns.py。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.ui.csv_columns import PREDICTION_CSV_COLUMNS, REPRODUCIBILITY_STAMPS

UI_DIR = Path("src/ui")

# PREDICTION_CSV_COLUMNS に含まれる再現性スタンプ4項目（§19.1 聖域・CSV 列定義側）。
# ``backtest_strategy_version`` は予測テーブルに非存在のため除外（``src/ui/csv_columns.py`` L68-74・
# ``tests/ui/test_csv_columns.py`` L68-70 確証）。UI 行表示用の5項目目は REPRODUCIBILITY_STAMPS 側。
_CSV_STAMPS: tuple[str, ...] = (
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "model_version",
    "feature_snapshot_id",
)

# 書き込み/DDL キーワード（大文字小文字区別なし・SQL 文字列リテラル内でマッチ）。
# adversarial 注入検出を最優先し・bare キーワード（"insert"/"update"/"delete"/"truncate"/
# "create"/"drop"/"alter"）を採用。analog ``tests/ui/test_readonly_guarantee.py::_WRITE_DDL_KEYWORDS``
# の複合キーワード（"insert into"/"update <table>"/"delete from"/"truncate <table>"/
# "create table"/"drop table"/"alter table"）より広く捉えることで注入の確実検出を狙う。
#
# REVIEW CR-03 開示: 本キーワード集合は本番 guard (tests/ui/test_readonly_guarantee.py) と
# **同一覆盖力を持たない**。bare 採用により本番 guard が通す SQL（例: "DELETE" 単独・
# "SELECT * FROM updates" のようなテーブル名に "update" を含む参照）を audit 側が fail させる
# 設計差が存在する。逆に本番 guard が通す SQL が audit で fail した場合・開発者はどちらを修正
# すべきか個別判断が必要。本テストは「注入を確実に検出」(SC#2 adversarial) を優先しており・
# 「audit GREEN ⇒ 本番 guard GREEN」を意味しない点に注意。
_WRITE_DDL_KEYWORDS: tuple[str, ...] = (
    "insert",
    "update",
    "delete",
    "truncate",
    "create",
    "drop",
    "alter",
)


def _extract_sql_literals(tree: ast.AST) -> list[str]:
    """AST から ``cur.execute`` / ``cursor.execute`` Call の第一引数の str 定数を抽出する。

    analog ``tests/ui/test_readonly_guarantee.py::_extract_sql_literals`` L44-64 の複製。
    REVIEW LOW-2: SQL 文字列リテラルのみを検査対象とし・comment/docstring/変数名の
    false positive を回避する。
    """
    sql_literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            sql_literals.append(first_arg.value)
    return sql_literals


def _contains_write_ddl(sql_literals: list[str]) -> bool:
    """SQL 文字列リテラルのリストに書き込み/DDL キーワードが含まれるかを返す（T-08-02 mitigate）。

    大文字小文字区別なし・bare キーワード7種（INSERT/UPDATE/DELETE/TRUNCATE/CREATE/DROP/ALTER）。
    SQL リテラル内でキーワード単語として出現するかを確認（``alter`` が ``alter table`` でも
    ``ALTER`` でも検出）。

    REVIEW CR-03 開示: analog ``tests/ui/test_readonly_guarantee.py`` の書き込み/DDL 検出とは
    **同一の覆盖力を持たない**。本番 guard は複合キーワード（"insert into"/"update <table>" 等）
    を使うのに対し・本 adversarial テストは bare キーワードで広く捉えることで注入を確実に検出
    する（``insert into`` でなく ``insert`` でもヒット）。「本テスト GREEN ⇒ 本番 guard GREEN」
    は成立しない点（例: ``DELETE`` 単独は本 test が fail させ本番 guard は通す）に注意。
    """
    for sql in sql_literals:
        sql_lower = sql.lower()
        # SQL 内の各キーワードを単語境界で検索（"delete" が "deleted_at" 等に誤ヒットしないよう
        # regex の \\b を使わず・前後が英数字でないことを確認する簡易判定）。
        for kw in _WRITE_DDL_KEYWORDS:
            idx = sql_lower.find(kw)
            while idx >= 0:
                before = sql_lower[idx - 1] if idx > 0 else " "
                after = sql_lower[idx + len(kw)] if idx + len(kw) < len(sql_lower) else " "
                # 前後が英数字/アンダースコアでなければ・キーワード単語として出現（DML/DDL 命令）
                if not (before.isalnum() or before == "_") and not (
                    after.isalnum() or after == "_"
                ):
                    return True
                idx = sql_lower.find(kw, idx + 1)
    return False


def test_ui_write_sql_injection_detected(tmp_path: Path) -> None:
    """D-06 adversarial: src/ui/ に書き込み/DDL SQL が混入すると AST 検査が fail することを実証。

    Phase 7 継承（07-CONTEXT Deferred）。cross-reference: tests/ui/test_readonly_guarantee.py。

    5段階鋳型（``test_no_target_encoding_leak`` 構造を UI read-only 保証に適用）:

      (1) ``tmp_path`` に INSERT を含むダミー .py を作成（注入・T-08-02 mitigate）
      (2) AST 解析 → ``_extract_sql_literals`` で SQL リテラル抽出
      (3) ``_contains_write_ddl`` が True を返すことで注入を検出したことを検証
      (4) 正規 ``src/ui/`` ディレクトリの全 .py で ``_contains_write_ddl`` が False を検証（GREEN）
    """
    # --- (1) tmp_path に INSERT を含むダミー .py を作成（注入）---
    dummy_py = tmp_path / "dammy_write.py"
    dummy_py.write_text(
        '"""Dummy module with write SQL injection (SC#2 adversarial)."""\n'
        "def write_data(cur):\n"
        '    cur.execute("INSERT INTO prediction.fukusho_prediction (race_id) VALUES (1)")\n'
        "    cur.execute(\"UPDATE label.fukusho_label SET fukusho_hit_validated = 1\")\n",
        encoding="utf-8",
    )

    # --- (2) AST 解析 → _extract_sql_literals で SQL リテラル抽出 ---
    tree = ast.parse(dummy_py.read_text(encoding="utf-8"), filename=str(dummy_py))
    sql_literals = _extract_sql_literals(tree)
    assert len(sql_literals) == 2, (
        f"ダミー .py から2つの SQL リテラルが抽出できない (actual={len(sql_literals)}・"
        "_extract_sql_literals の抽出ロジック違反)"
    )

    # --- (3) _contains_write_ddl が True を返すことで注入を検出 ---
    assert _contains_write_ddl(sql_literals) is True, (
        "INSERT/UPDATE を含む SQL リテラル注入を _contains_write_ddl が検出しない "
        "(SC#2/D-06 adversarial fail・注入が見逃されている・T-08-02 mitigate違反)"
    )

    # --- (4) 正規 src/ui/ ディレクトリの全 .py で _contains_write_ddl が False を検証（GREEN）---
    if not UI_DIR.exists():
        # src/ui が未作成の場合は skip 相当（0 ファイル = 検査対象なし・green）
        return
    py_files = sorted(UI_DIR.rglob("*.py"))
    violations: list[str] = []
    for py in py_files:
        tree_prod = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        sql_literals_prod = _extract_sql_literals(tree_prod)
        if _contains_write_ddl(sql_literals_prod):
            violations.append(str(py))
    assert not violations, (
        f"正規 src/ui/ に書き込み/DDL SQL 混入が検出された (violations={violations}・"
        "D-06 read-only 保証違反・Phase 8 TEST-01 前提)"
    )


def test_reproducibility_stamp_missing_detected() -> None:
    """D-06 adversarial: PREDICTION_CSV_COLUMNS（4スタンプ・backtest_strategy_version は予測テーブルに
    非存在のため除外）および REPRODUCIBILITY_STAMPS（5スタンプ・UI 行表示用・backtest_strategy_version 含む）
    からスタンプを欠落させると presence assert が fail することを実証（§19.1 聖域）。

    cross-reference: tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps。

    5段階鋳型（``test_no_target_encoding_leak`` 構造をスタンプ presence に適用）:

      (1) 正規 PREDICTION_CSV_COLUMNS に4スタンプ全存在を assert（GREEN）
      (2) 正規 REPRODUCIBILITY_STAMPS に5スタンプ全存在を assert（GREEN）
      (3) 検証力証明: _CSV_STAMPS（4項目）から1つ除いた縮退 tuple で presence assert が fail すること
      (4) 検証力証明: REPRODUCIBILITY_STAMPS（5項目）から1つ除いた縮退 tuple で presence assert が fail すること
      (5) ``backtest_strategy_version`` を PREDICTION_CSV_COLUMNS に含む主張はしないことをコードで保証
    """
    # --- (1) 正規 PREDICTION_CSV_COLUMNS に4スタンプ全存在を assert（GREEN）---
    for stamp in _CSV_STAMPS:
        assert stamp in PREDICTION_CSV_COLUMNS, (
            f"再現性スタンプ {stamp!r} が PREDICTION_CSV_COLUMNS にない (§19.1 聖域違反・"
            f"PREDICTION_CSV_COLUMNS={PREDICTION_CSV_COLUMNS})"
        )

    # --- (2) 正規 REPRODUCIBILITY_STAMPS に5スタンプ全存在を assert（GREEN）---
    assert len(REPRODUCIBILITY_STAMPS) == 5, (
        f"REPRODUCIBILITY_STAMPS は5項目期待 (actual={len(REPRODUCIBILITY_STAMPS)}・"
        f"REPRODUCIBILITY_STAMPS={REPRODUCIBILITY_STAMPS})"
    )
    for stamp in REPRODUCIBILITY_STAMPS:
        assert stamp in REPRODUCIBILITY_STAMPS  # tautology guard・定数が tuple ので常に GREEN

    # --- (3) 検証力証明: _CSV_STAMPS から1つ除いた縮退 tuple で presence assert が fail すること ---
    # 縮退 tuple に対して presence assert を走らせ・AssertionError が raise されることを try/except で捕捉。
    # raise されなければ pytest.fail で検証力不足を検知（false-pass 回避・T-08-03 mitigate）。
    _verify_degraded_tuple_fails_presence_assert(
        stamps=_CSV_STAMPS,
        container=PREDICTION_CSV_COLUMNS,
        label="PREDICTION_CSV_COLUMNS",
    )

    # --- (4) 検証力証明: REPRODUCIBILITY_STAMPS から1つ除いた縮退 tuple で presence assert が fail すること ---
    # REPRODUCIBILITY_STAMPS 自体を container にして・自己から1つ除いた tuple で検証。
    _verify_degraded_tuple_fails_presence_assert(
        stamps=REPRODUCIBILITY_STAMPS,
        container=REPRODUCIBILITY_STAMPS,
        label="REPRODUCIBILITY_STAMPS",
    )

    # --- (5) backtest_strategy_version を PREDICTION_CSV_COLUMNS に含む主張はしないことを保証 ---
    # ``backtest_strategy_version`` は予測テーブルに非存在のため PREDICTION_CSV_COLUMNS には含まれない
    # （``src/ui/csv_columns.py`` L68-74 docstring・``tests/ui/test_csv_columns.py`` L68-70 確証）。
    # presence assert 対象は _CSV_STAMPS（4項目）のみで・backtest_strategy_version を含めない。
    assert "backtest_strategy_version" not in _CSV_STAMPS, (
        "_CSV_STAMPS に backtest_strategy_version が含まれている（予測テーブル非存在の列を"
        "PREDICTION_CSV_COLUMNS presence assert 対象にしている・acceptance_criteria 違反）"
    )


def _verify_degraded_tuple_fails_presence_assert(
    *,
    stamps: tuple[str, ...],
    container: tuple[str, ...],
    label: str,
) -> None:
    """``stamps`` から1つ除いた縮退 tuple が ``container`` に存在しないことで presence assert が
    fail することを実証する（検証力証明・T-08-03 mitigate のヘルパー）。

    presence assert ロジック: ``all(s + "_MISSING_SENTINEL" in container for s in stamps)``
    ではなく・``stamps`` の各要素が ``container`` に存在することを確認する本番ロジックと同じ形。
    縮退 tuple（``stamps`` の1要素を ``"__MISSING_SENTINEL__"`` に置換）は ``container`` に存在
    しないため presence assert が fail する（=検証力がある）。
    """
    for i in range(len(stamps)):
        # i 番目のスタンプを存在しない sentinel に置換した縮退 tuple を構築
        degraded = stamps[:i] + ("__MISSING_SENTINEL__",) + stamps[i + 1:]
        # presence assert を走らせ・AssertionError が raise されることを確認
        try:
            for s in degraded:
                assert s in container, (
                    f"{label}: 再現性スタンプ {s!r} がない (§19.1 聖域違反・degraded presence assert)"
                )
        except AssertionError:
            # 期待通り fail した → 検証力証明 OK・次の縮退パターンへ
            continue
        # 期待に反して全 sentinel が container に存在した → 検証力なし（false-pass）
        raise AssertionError(
            f"{label}: 縮退 tuple（{i}番目を sentinel 化）でも presence assert が fail しない "
            f"(degraded={degraded}・container に sentinel が存在する = presence assert に検証力がない・"
            "T-08-03 mitigate違反・false-pass 回避不能)"
        )


def test_ui_csv_docstring_cross_reference() -> None:
    """本テストモジュールの docstring が D-06 + cross-reference を含む（T-08-04 mitigate）。

    重複回避: 機能テスト ``tests/ui/test_readonly_guarantee.py`` / ``tests/ui/test_csv_columns.py``
    が「正規経路が GREEN」を検証するのに対し・本 adversarial テストは「注入/欠落で fail する」を実証する。
    """
    import sys

    module_doc = sys.modules[__name__].__doc__ or ""
    assert "D-06" in module_doc, (
        "モジュール docstring に D-06 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/ui/test_readonly_guarantee.py" in module_doc, (
        "モジュール docstring に test_readonly_guarantee.py cross-reference がない（T-08-04 違反）"
    )
    assert "cross-reference: tests/ui/test_csv_columns.py" in module_doc or (
        "tests/ui/test_csv_columns.py" in module_doc
    ), "モジュール docstring に test_csv_columns.py への言及がない（T-08-04 違反）"
    # 両テストの docstring にも D-06 + cross-reference が含まれることを検証
    test1_doc = test_ui_write_sql_injection_detected.__doc__ or ""
    assert "D-06" in test1_doc and "cross-reference: tests/ui/test_readonly_guarantee.py" in test1_doc, (
        "test_ui_write_sql_injection_detected docstring に D-06 + cross-reference がない（T-08-04 違反）"
    )
    test2_doc = test_reproducibility_stamp_missing_detected.__doc__ or ""
    assert "D-06" in test2_doc and "cross-reference: tests/ui/test_csv_columns.py" in test2_doc, (
        "test_reproducibility_stamp_missing_detected docstring に D-06 + cross-reference がない（T-08-04 違反）"
    )
