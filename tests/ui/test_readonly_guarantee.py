# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・src/ev/report.py と同一慣例)
"""read-only 保証の構造的検証（AST・Phase 8 TEST-01 前提・D-03・REVIEW LOW-2 解決）。

``src/ui/`` 配下に書き込み/DDL SQL 経路が存在しないことを検証する。Phase 8（Adversarial
Audit）の TEST-01（書き込み経路不存在）の出発点となる契約 test。

**検査対象の絞り込み（REVIEW LOW-2 解決）:** comment/docstring に "update" 等の英単語が
現れる false positive を回避するため・**SQL 文字列リテラル（AST で ``ast.Constant`` の
value が str かつ親が ``cur.execute`` / ``cursor.execute`` Call の第一引数）のみ** を検査
対象とする。SQL リテラル抽出が困難な汎用ケースは ``# planner-discipline-allow: <kw>``
マーカー行で例外的に許容（本テストファイル自身の検査キーワード文字列はマーカーで許容）。

参照: 07-01-PLAN.md Task 2 / 07-PATTERNS.md §tests/ui/test_readonly_guarantee.py /
      07-RESEARCH.md §Code Examples L498-538
"""

from __future__ import annotations

import ast
from pathlib import Path

UI_DIR = Path("src/ui")

# 検査キーワード（小文字統一比較・SQL 文字列リテラル内の出現を検査）
# planner-discipline-allow マーカーは下位互換のため中央のキーワード形式で許容
# planner-discipline-allow: insert into
# planner-discipline-allow: update
# planner-discipline-allow: delete from
# planner-discipline-allow: truncate
# planner-discipline-allow: create table
# planner-discipline-allow: drop table
# planner-discipline-allow: alter table
_WRITE_DDL_KEYWORDS: tuple[str, ...] = (
    "insert into",
    "update ",  # UPDATE <table> SET 形式・末尾スペースで "update_at" 等の変数名 false positive 回避
    "delete from",
    "truncate ",  # TRUNCATE <table> 形式
    "create table",
    "drop table",
    "alter table",
)


def _extract_sql_literals(tree: ast.AST) -> list[str]:
    """AST から ``cur.execute`` / ``cursor.execute`` Call の第一引数の str 定数を抽出する。

    REVIEW LOW-2: SQL 文字列リテラルのみを検査対象とし・comment/docstring/変数名の
    false positive を回避する。
    """
    sql_literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # <name>.execute(...) 形式 (cur.execute / cursor.execute / conn.execute 等)
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        # execute("SQL literal", ...) と execute(SQL_CONSTANT, ...) の両方を拾う
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            sql_literals.append(first_arg.value)
    return sql_literals


def _allowed_keywords_for_file(py: Path) -> set[str]:
    """``# planner-discipline-allow: <kw>`` マーカー行で例外的に許容されるキーワード集合を返す。"""
    allowed: set[str] = set()
    for raw in py.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            marker = "planner-discipline-allow:"
            idx = line.find(marker)
            if idx >= 0:
                kw = line[idx + len(marker) :].strip().lower()
                if kw:
                    allowed.add(kw)
    return allowed


def test_ui_has_no_write_ddl_sql():
    """src/ui/ 配下の SQL 文字列リテラルに書き込み/DDL キーワードが含まれない（read-only 保証・D-03）。

    REVIEW LOW-2 解決: comment/docstring は検査対象外・execute() Call の第一引数 str 定数のみ検査。
    本テストファイル自身の検査キーワード文字列は planner-discipline-allow マーカーで許容済。
    """
    if not UI_DIR.exists():
        # src/ui が未作成の場合は skip 相当（0 ファイル = 検査対象なし・green）
        return
    py_files = sorted(UI_DIR.rglob("*.py"))
    for py in py_files:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        sql_literals = _extract_sql_literals(tree)
        allowed = _allowed_keywords_for_file(py)
        for sql in sql_literals:
            sql_lower = sql.lower()
            for kw in _WRITE_DDL_KEYWORDS:
                # 末尾スペース有りのキーワードは・マーカー許容時に strip 済みの bare キーワードと照合
                kw_bare = kw.rstrip()
                allowed_bare = kw_bare in allowed
                # "insert into" (スペース区切り・bare) と "insert into " (SQL 内出現) の両方を検出
                kw_in_sql = kw in sql_lower or kw_bare in sql_lower
                if kw_in_sql and not allowed_bare:
                    raise AssertionError(
                        f"{py}: SQL 文字列リテラルに書き込み/DDL キーワード '{kw_bare}' が含まれる"
                        f"（D-03 read-only 保証違反・Phase 8 TEST-01 前提）・SQL先頭: {sql[:80]!r}"
                    )


def test_ui_uses_only_readonly_pool():
    """src/ui/ 配下の ``make_pool`` Call の ``role`` 引数は ``'readonly'``（既定）または引数なしのみ許可（D-03）。

    Task 2 時点では ``src/ui`` 配下に ``make_pool`` 呼出がないため green（Plan 02/03 で実装時に検出）。
    """
    if not UI_DIR.exists():
        return
    py_files = sorted(UI_DIR.rglob("*.py"))
    for py in py_files:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "make_pool"):
                continue
            role_arg = next((kw.value for kw in node.keywords if kw.arg == "role"), None)
            if role_arg is None:
                continue  # role 引数なし = 既定 (readonly) のみ許可
            if not (isinstance(role_arg, ast.Constant) and role_arg.value == "readonly"):
                raise AssertionError(
                    f"{py}: make_pool(role=...) が 'readonly' でない（D-03 違反・"
                    f"keiba_readonly ロールのみ使用可能）"
                )
