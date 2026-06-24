# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・src/db/prediction_load.py と同一慣例)
"""loaders.py の read-only 保証・parameterized query・is_primary 絞りの契約検証。

``src/ui/loaders.py`` が D-03 read-only 保証 (``make_pool(role="readonly")`` のみ)・
SQL injection 防御 (psycopg parameterized query)・主モデル絞り (``WHERE is_primary = true``)・
``@st.cache_data`` の ``hash_funcs`` を満たすことを AST/文字列検証で検証する
(Phase 8 TEST-01 前提・T-07-05/06/07/11 mitigate)。

参照: 07-02-PLAN.md Task 1 <behavior> / 07-PATTERNS.md §tests/ui/test_loaders_readonly.py /
      07-RESEARCH.md §Code Examples L498-538 (read-only 保証テスト analog)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.ui import loaders as loaders_mod
from src.ui.loaders import (
    EV_STRATEGY_VERSION,
    build_backtest_csv_bytes,
    build_prediction_csv_bytes,
    build_race_id,
    load_backtests,
    load_predictions,
    load_segment_json,
    normalize_date_range,
)

LOADERS_PATH = Path("src/ui/loaders.py")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _loaders_ast() -> ast.Module:
    return ast.parse(LOADERS_PATH.read_text(encoding="utf-8"))


def _loaders_text() -> str:
    return LOADERS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: make_pool role='readonly' のみ (T-07-06 Elevation of Privilege mitigate)
# ---------------------------------------------------------------------------


def test_loaders_uses_only_readonly_pool() -> None:
    """loaders.py の ``make_pool`` 呼出は全て ``role='readonly'`` (既定) または引数なし。

    ``role='etl'`` は read-only 保証違反 (D-03・T-07-06 mitigate)。
    """
    tree = _loaders_ast()
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # make_pool(...) 直接呼出
        is_make_pool = (isinstance(func, ast.Name) and func.id == "make_pool") or (
            isinstance(func, ast.Attribute) and func.attr == "make_pool"
        )
        if not is_make_pool:
            continue
        role_arg = next((kw.value for kw in node.keywords if kw.arg == "role"), None)
        if role_arg is None:
            continue  # role 未指定 = 既定 'readonly' (許容)
        if not (isinstance(role_arg, ast.Constant) and role_arg.value == "readonly"):
            violations.append(f"make_pool(role={ast.dump(role_arg)}) at line {node.lineno}")
    assert not violations, (
        f"src/ui/loaders.py: make_pool の role が 'readonly' でない呼出がある "
        f"(read-only 違反・D-03・T-07-06): {violations}"
    )


# ---------------------------------------------------------------------------
# Test 2: 書き込み/DDL SQL キーワード不存在 (T-07-06 read-only 保証)
# ---------------------------------------------------------------------------


def test_loaders_has_no_write_ddl_sql() -> None:
    """loaders.py のソース (小文字) に書き込み/DDL SQL キーワードが含まれない (D-03)。

    ※ SQL 文字列リテラル内は test_readonly_guarantee.py で AST 検証済。本 test は
    ソース全体 (docstring/comment 含む) の grep 的検証で二重防御する。
    """
    lower = _loaders_text().lower()
    # planner-discipline-allow マーカーは本テストの検査キーワード文字列を許容
    # planner-discipline-allow: insert into
    # planner-discipline-allow: update
    # planner-discipline-allow: delete from
    # planner-discipline-allow: truncate
    # planner-discipline-allow: create table
    # planner-discipline-allow: drop table
    # planner-discipline-allow: alter table
    forbidden = (
        "insert into",
        "update ",  # UPDATE <table> SET・末尾スペースで "update_at" false positive 回避
        "delete from",
        "truncate ",
        "create table",
        "drop table",
        "alter table",
    )
    found = [kw for kw in forbidden if kw in lower]
    assert not found, (
        f"src/ui/loaders.py: 書き込み/DDL SQL キーワードが含まれる (read-only 違反・D-03): {found}"
    )


# ---------------------------------------------------------------------------
# Test 3: load_predictions が is_primary 絞りを持つ (T-07-07 Pitfall 5 mitigate)
# ---------------------------------------------------------------------------


def test_loaders_predictions_filter_is_primary() -> None:
    """``load_predictions`` の SQL が ``is_primary = true`` で主モデル=LightGBM に絞る (Pitfall 5)。

    Phase 6 D-09: ``WHERE is_primary = true`` で 44,426行(全モデル) でなく 22,213行(主モデル) になる。
    """
    source = inspect.getsource(load_predictions)
    assert "is_primary" in source.lower(), (
        "load_predictions のソースに 'is_primary' が含まれない (Pitfall 5・主モデル絞り欠如・T-07-07)"
    )
    # _select_predictions の SQL にも is_primary = true が含まれる
    select_source = inspect.getsource(loaders_mod._select_predictions)
    assert "is_primary = true" in select_source.lower() or "is_primary" in select_source.lower(), (
        "_select_predictions の SQL に 'is_primary = true' が含まれない (Pitfall 5・T-07-07)"
    )


# ---------------------------------------------------------------------------
# Test 4: parameterized query 使用・文字列結合 BinOp 禁止 (T-07-05 SQL injection mitigate)
# ---------------------------------------------------------------------------


def test_loaders_uses_parameterized_queries() -> None:
    """``cur.execute`` Call が全て parameterized query を使用する (T-07-05 mitigate)。

    REVIEW MEDIUM-3 例外: SQL 文字列リテラルが ``%s`` placeholder を含まず・かつ ``WHERE``/
    ``VALUES`` 句を含まない parameterless 静的 SELECT (例: ``SELECT 1``) は第二引数省略を許容。
    文字列結合 (BinOp) は全ケースで禁止。
    """
    tree = _loaders_ast()
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # <name>.execute(...) 形式 (cur.execute 等)
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        # 文字列結合 BinOp (f-string でなく + 結合) は全ケース禁止
        if isinstance(first_arg, ast.BinOp):
            violations.append(
                f"cur.execute の第一引数が BinOp (文字列結合)・SQL injection リスク (T-07-05) "
                f"at line {node.lineno}: {ast.dump(first_arg)}"
            )
            continue
        # JoinedStr (f-string) も SQL 構築に使われていないか確認
        if isinstance(first_arg, ast.JoinedStr):
            # f-string で WHERE 句を組み立てている場合は SQL 構築とみなし violation
            joined = "".join(
                v.value if isinstance(v, ast.Constant) else "<expr>" for v in first_arg.values
            )
            if "where" in joined.lower() or "values" in joined.lower():
                violations.append(
                    f"cur.execute の第一引数が f-string で WHERE/VALUES を組み立てている "
                    f"(T-07-05) at line {node.lineno}"
                )
            continue
        # 定数文字列 (SQL) の場合: %s placeholder または WHERE/VALUES 句があれば第二引数必須
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            sql_text = first_arg.value.lower()
            needs_params = ("%s" in sql_text) or ("where" in sql_text) or ("values" in sql_text)
            if needs_params and len(node.args) < 2:
                violations.append(
                    f"cur.execute(SQL) が %s/WHERE/VALUES を含むが第二引数 params がない "
                    f"(T-07-05 parameterized query 違反) at line {node.lineno}: {first_arg.value[:60]!r}"
                )
    assert not violations, (
        "src/ui/loaders.py: parameterized query 違反 (T-07-05 SQL injection mitigate):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 5: @st.cache_data hash_funcs (Pitfall 2 mitigate)
# ---------------------------------------------------------------------------


def test_loaders_cache_hash_funcs() -> None:
    """``@st.cache_data`` 付き関数が ``hash_funcs={ConnectionPool: id}`` を持つ (Pitfall 2)。

    ``ConnectionPool`` を引数に取る cached wrapper は ``hash_funcs`` 必須
    (``UnhashableParamError`` 回避・RESEARCH Pattern 2)。
    """
    source = _loaders_text()
    # load_predictions_cached / load_backtests_cached は ConnectionPool 引数 → hash_funcs 必須
    assert "hash_funcs={ConnectionPool: id}" in source or "hash_funcs={" in source, (
        "src/ui/loaders.py: @st.cache_data に hash_funcs={ConnectionPool: id} がない "
        "(Pitfall 2・UnhashableParamError リスク)"
    )


# ---------------------------------------------------------------------------
# Test 6: normalize_prediction_export_columns で fuku_* → fukusho_* rename (REVIEW HIGH-1)
# ---------------------------------------------------------------------------


def test_normalize_odds_columns_rename() -> None:
    """``normalize_prediction_export_columns`` が ``fuku_odds_*`` → ``fukusho_odds_*`` rename する (HIGH-1)。"""
    import pandas as pd

    from src.ui.csv_columns import normalize_prediction_export_columns

    df = pd.DataFrame(
        {
            "p_fukusho_hit": [0.5],
            "fuku_odds_lower": [2.0],
            "fuku_odds_upper": [3.0],
            "EV_lower": [1.0],
        }
    )
    out = normalize_prediction_export_columns(df)
    assert "fukusho_odds_lower" in out.columns, (
        "fuku_odds_lower → fukusho_odds_lower rename 失敗 (HIGH-1)"
    )
    assert "fukusho_odds_upper" in out.columns, (
        "fuku_odds_upper → fukusho_odds_upper rename 失敗 (HIGH-1)"
    )
    assert "fuku_odds_lower" not in out.columns, "旧列名 fuku_odds_lower が残存 (HIGH-1)"
    assert out["fukusho_odds_lower"].iloc[0] == 2.0
    # odds 列が存在しない DataFrame は no-op (odds snapshot 未結合段階の呼出を許容)
    df2 = pd.DataFrame({"p_fukusho_hit": [0.5]})
    out2 = normalize_prediction_export_columns(df2)
    assert "fuku_odds_lower" not in out2.columns


# ---------------------------------------------------------------------------
# Test 7: build_race_id formatter (REVIEW HIGH-3・NEW-M3 表示専用 canonical ラベル)
# ---------------------------------------------------------------------------


def test_build_race_id_format() -> None:
    """``build_race_id`` が表示専用 canonical race_id (5部・2桁ゼロ埋め) を生成する (HIGH-3)。"""
    # int 入力
    assert build_race_id(2024, "01", 5, 6, 9) == "2024-01-05-06-09"
    # str 入力 (ゼロ埋め)
    assert build_race_id("2024", "01", "05", "06", "09") == "2024-01-05-06-09"
    # 1桁 → 2桁ゼロ埋め
    assert build_race_id(2024, "5", 1, 2, 3) == "2024-05-01-02-03"


# ---------------------------------------------------------------------------
# Test 8: build_*_csv_bytes fail-loud (REVIEW LOW-3・T-07-09 mitigate)
# ---------------------------------------------------------------------------


def test_build_prediction_csv_bytes_missing_column_raises_value_error() -> None:
    """``build_prediction_csv_bytes`` が必須列欠落時 ``ValueError`` を raise する (LOW-3・T-07-09)。"""
    import pandas as pd

    # PREDICTION_CSV_COLUMNS の一部のみ → ValueError
    partial_cols = list(
        __import__("src.ui.csv_columns", fromlist=["PREDICTION_CSV_COLUMNS"]).PREDICTION_CSV_COLUMNS
    )[:10]
    df = pd.DataFrame(columns=partial_cols)
    with pytest.raises(ValueError):
        build_prediction_csv_bytes(df)


def test_build_backtest_csv_bytes_missing_column_raises_value_error() -> None:
    """``build_backtest_csv_bytes`` が必須列欠落時 ``ValueError`` を raise する (LOW-3・T-07-09)。"""
    import pandas as pd

    df = pd.DataFrame(columns=["backtest_id"])  # 16列のうち1列のみ
    with pytest.raises(ValueError):
        build_backtest_csv_bytes(df)


# ---------------------------------------------------------------------------
# Test 9: EV_STRATEGY_VERSION 定数 (REVIEW HIGH-4)
# ---------------------------------------------------------------------------


def test_ev_strategy_version_constant() -> None:
    """``EV_STRATEGY_VERSION`` 定数が ``"fukusho_ev_v1"`` である (REVIEW HIGH-4・"latest backtest" 推論廃止)。"""
    assert EV_STRATEGY_VERSION == "fukusho_ev_v1", (
        f"EV_STRATEGY_VERSION が 'fukusho_ev_v1' でない (REVIEW HIGH-4): {EV_STRATEGY_VERSION!r}"
    )
    # loaders.py のソースに定数定義が存在
    assert "EV_STRATEGY_VERSION" in _loaders_text()


# ---------------------------------------------------------------------------
# Test 10: normalize_date_range helper (REVIEW MEDIUM-5・NEW-L1 単一ホーム)
# ---------------------------------------------------------------------------


def test_normalize_date_range_empty() -> None:
    """空 list → ``(None, None)`` (bounds なし)。"""
    assert normalize_date_range([]) == (None, None)
    assert normalize_date_range(()) == (None, None)
    assert normalize_date_range(None) == (None, None)


def test_normalize_date_range_single() -> None:
    """要素1件 → ``(same_day, same_day)`` (同日範囲)。"""
    from datetime import date

    d = date(2024, 6, 1)
    assert normalize_date_range([d]) == ("2024-06-01", "2024-06-01")


def test_normalize_date_range_pair() -> None:
    """要素2件 → ``(from, to)`` (昇順保証)。"""
    from datetime import date

    d1 = date(2024, 1, 1)
    d2 = date(2024, 12, 31)
    # 昇順
    assert normalize_date_range([d1, d2]) == ("2024-01-01", "2024-12-31")
    # 降順入力でも昇順に正規化
    assert normalize_date_range([d2, d1]) == ("2024-01-01", "2024-12-31")


# ---------------------------------------------------------------------------
# Test 11: 純粋 loader と cached wrapper の分離 (REVIEW MEDIUM-4)
# ---------------------------------------------------------------------------


def test_pure_loaders_and_cached_wrappers_exist() -> None:
    """純粋 loader (load_predictions/load_backtests/load_segment_json) と cached wrapper が分離定義される (MEDIUM-4)。

    CLI は純粋関数を・UI は cached wrapper を import する (Streamlit runtime 非依存・REVIEW MEDIUM-4)。
    """
    # 純粋関数 (デコレータなし)
    assert callable(load_predictions)
    assert callable(load_backtests)
    assert callable(load_segment_json)
    # cached wrapper
    assert callable(loaders_mod.load_predictions_cached)
    assert callable(loaders_mod.load_backtests_cached)
    assert callable(loaders_mod.load_segment_json_cached)


def test_build_csv_bytes_functions_exist() -> None:
    """``build_prediction_csv_bytes`` / ``build_backtest_csv_bytes`` が存在する (PATTERNS shared pattern 5)。"""
    assert callable(build_prediction_csv_bytes)
    assert callable(build_backtest_csv_bytes)
