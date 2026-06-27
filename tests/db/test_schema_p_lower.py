# ruff: noqa: E501
"""Phase 12 Plan 01 Task 2 (EV-01): prediction p_fukusho_hit_lower 列 migration の
3ファイル連鎖（schema.py / predict.py / prediction_load.py）と run_apply_schema.py step list
反映を検証する（Pitfall 4・C-12-01-1 HIGH・C-12-01-4 MEDIUM）.

本テストは主に unit（KEIBA_SKIP_DB_TESTS=1 で GREEN）で検証する:
  - Test 1 (3ファイル列数一致・Pitfall 4): PREDICTION_COLUMNS len == 20・schema.py DDL 全列数と一致
  - Test 2 (p_fukusho_hit_lower の位置): p_fukusho_hit の直後 index（3ファイル全てで同位置）
  - Test 3 (_assert_valid_prediction_df NULL 許容 [0,1]): p_lower 全て NULL は valid・[0,1] 外で ValueError
  - Test 4 (_FLOAT_COLS 拡張): prediction_load._FLOAT_COLS に p_fukusho_hit_lower が含まれる
  - Test 5 (idempotent ALTER): PREDICTION_ADD_P_LOWER_SQL が ADD COLUMN IF NOT EXISTS + DROP CONSTRAINT IF EXISTS + ADD
  - Test 6 (CHECK 制約 prediction_p_lower_range): SQL 文字列に CHECK (p_fukusho_hit_lower IS NULL OR ...) が含まれる
  - Test 7 (合成 row helper 20列追従): 既存 helper が20列に対応する（test_prediction_load/test_is_primary_flag 経由）
  - Test 8 ([C-12-01-1 / HIGH] run_apply_schema.py step list 反映):
           scripts/run_apply_schema.py のハードコード手動 step list に prediction_add_p_lower が1件
  - Test 9 ([C-12-01-4 / MEDIUM] race-relative 行で p_lower 非 NULL / v1.0 binary 行で NULL):
           theta != None 経路で p_fukusho_hit_lower が常に非 NULL・theta=None で常に NULL

live-DB 適用（CHECK 制約実 INSERT 拒否等）は本 plan では行わない（owner/admin 権限必要・
memory: migration-privilege-admin-required・run_apply_schema.py に一本化）。
"""

from __future__ import annotations

import re

import ast
import inspect
import pandas as pd
import pytest

from src.db import schema as schema_module
from src.db.prediction_load import _FLOAT_COLS
from src.model.predict import (
    PREDICTION_COLUMNS,
    _assert_valid_prediction_df,
    predict_p_fukusho,
)

# ---------------------------------------------------------------------------
# Helpers — 合成 prediction DataFrame
# ---------------------------------------------------------------------------


def _make_prediction_row_20(
    *,
    model_type: str = "lightgbm_rr",
    model_version: str = "20260626-1a-opponentstrength-v1-lgbrr-v1",
    p_fukusho_hit: float = 0.42,
    p_fukusho_hit_lower: float | None = 0.30,
    umaban: int = 1,
    kettonum: int = 101,
) -> dict:
    """PREDICTION_COLUMNS 20列を埋めた1行分の dict を返す（p_fukusho_hit_lower 含む・Phase 12）.

    p_fukusho_hit_lower は race-relative 行を想定しデフォルトで非 None（C-12-01-4 検証用）。
    v1.0 binary 行は呼出側で p_fukusho_hit_lower=None を渡す。
    """
    return {
        "model_type": model_type,
        "model_version": model_version,
        "feature_snapshot_id": "20260626-1a-opponentstrength-v1",
        "as_of_datetime": pd.Timestamp("2026-06-26 12:00:00", tz="UTC").to_pydatetime(),
        "calib_method": "isotonic",
        "year": 2023,
        "jyocd": "05",
        "kaiji": 1,
        "nichiji": "06",
        "racenum": 1,
        "umaban": umaban,
        "kettonum": kettonum,
        "p_fukusho_hit": p_fukusho_hit,
        "p_fukusho_hit_lower": p_fukusho_hit_lower,
        "race_date": pd.Timestamp("2023-06-04"),
        "split": "test",
        "label_version": "test_label_v1",
        "odds_snapshot_policy": "test_30min",
        "backtest_strategy_version": "test_BT1",
        "is_primary": False,
    }


# ---------------------------------------------------------------------------
# Test 1: 3ファイル列数一致（Pitfall 4）
# ---------------------------------------------------------------------------


def test_prediction_columns_count_is_20():
    """Pitfall 4: PREDICTION_COLUMNS の len が 20（19 + p_fukusho_hit_lower 追加）。"""
    assert len(PREDICTION_COLUMNS) == 20, (
        f"PREDICTION_COLUMNS は20列期待（p_fukusho_hit_lower 追加）: got {len(PREDICTION_COLUMNS)}"
    )
    assert "p_fukusho_hit_lower" in PREDICTION_COLUMNS, (
        "PREDICTION_COLUMNS に p_fukusho_hit_lower が無い（Phase 12 SC#1 3ファイル連鎖違反）"
    )


def test_prediction_columns_match_ddl_count():
    """Pitfall 4: PREDICTION_COLUMNS(20) と DDL(create table + ALTER provenance + ALTER p_lower)
    の合計列数が一致する（3ファイル連鎖の機械保証）。
    """
    ddl_text = (
        schema_module.PREDICTION_TABLE_DDL
        + schema_module.PREDICTION_ADD_IS_PRIMARY_SQL
        + schema_module.PREDICTION_ADD_PROVENANCE_SQL
        + schema_module.PREDICTION_ADD_P_LOWER_SQL
    )

    # CREATE TABLE ブロックの列を抽出
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS \w+\.\w+\s*\((.*?)\);",
        ddl_text,
        re.DOTALL,
    )
    assert match is not None, "CREATE TABLE ブロックが見つからない"
    inner = match.group(1)
    ddl_cols: list[str] = []
    for raw_line in inner.splitlines():
        stripped = raw_line.strip().rstrip(",").strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith(("PRIMARY", "CONSTRAINT", "CHECK", "COMMENT")):
            continue
        # コメント行（-- ...）や SQL directive は識別子パターン不一致で除外
        first_token = stripped.split()[0]
        m_unquoted = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)$", first_token)
        if m_unquoted:
            ddl_cols.append(m_unquoted.group(1))

    # ALTER ADD COLUMN IF NOT EXISTS の列を抽出
    for m in re.finditer(
        r"ADD COLUMN IF NOT EXISTS\s+(\w+)\s+", ddl_text
    ):
        col = m.group(1)
        if col not in ddl_cols:
            ddl_cols.append(col)

    assert len(ddl_cols) == len(PREDICTION_COLUMNS), (
        f"DDL 列数({len(ddl_cols)}) と PREDICTION_COLUMNS({len(PREDICTION_COLUMNS)}) が不一致 "
        f"(Pitfall 4 3ファイル連鎖):\n  DDL: {ddl_cols}\n  COLS: {list(PREDICTION_COLUMNS)}"
    )
    assert ddl_cols == list(PREDICTION_COLUMNS), (
        f"DDL 列順と PREDICTION_COLUMNS が不一致:\n  DDL: {ddl_cols}\n  COLS: {list(PREDICTION_COLUMNS)}"
    )


# ---------------------------------------------------------------------------
# Test 2: p_fukusho_hit_lower の位置（p_fukusho_hit の直後）
# ---------------------------------------------------------------------------


def test_p_lower_position_right_after_p_fukusho_hit():
    """p_fukusho_hit_lower が p_fukusho_hit の直後 index にある（3ファイル整合）。"""
    p_idx = PREDICTION_COLUMNS.index("p_fukusho_hit")
    pl_idx = PREDICTION_COLUMNS.index("p_fukusho_hit_lower")
    assert pl_idx == p_idx + 1, (
        f"p_fukusho_hit_lower は p_fukusho_hit の直後であるべき: "
        f"p_fukusho_hit@{p_idx}, p_fukusho_hit_lower@{pl_idx}"
    )


# ---------------------------------------------------------------------------
# Test 3: _assert_valid_prediction_df NULL 許容 [0,1]
# ---------------------------------------------------------------------------


def test_assert_valid_prediction_df_p_lower_all_null_valid():
    """v1.0 binary 行互換: p_fukusho_hit_lower が全て None/NaN の df は valid。"""
    # 2行構築（同一 PK にならないよう umaban を変える）
    row1 = _make_prediction_row_20(p_fukusho_hit_lower=None, umaban=1)
    row2 = _make_prediction_row_20(p_fukusho_hit_lower=None, umaban=2)
    df = pd.DataFrame([row1, row2])
    df = df[list(PREDICTION_COLUMNS)]
    # 例外 raise なければ valid
    _assert_valid_prediction_df(df)


def test_assert_valid_prediction_df_p_lower_out_of_range_raises():
    """p_fukusho_hit_lower が [0,1] 外の値で ValueError（fail-loud）。"""
    # -0.1
    row = _make_prediction_row_20(p_fukusho_hit_lower=-0.1, umaban=1)
    df = pd.DataFrame([row])
    df = df[list(PREDICTION_COLUMNS)]
    with pytest.raises(ValueError):
        _assert_valid_prediction_df(df)

    # 1.5
    row = _make_prediction_row_20(p_fukusho_hit_lower=1.5, umaban=1)
    df = pd.DataFrame([row])
    df = df[list(PREDICTION_COLUMNS)]
    with pytest.raises(ValueError):
        _assert_valid_prediction_df(df)


def test_assert_valid_prediction_df_p_lower_in_range_valid():
    """p_fukusho_hit_lower が [0,1] 内の値（0.0 と 1.0 境界含む）は valid。"""
    for v in [0.0, 0.5, 1.0]:
        row = _make_prediction_row_20(p_fukusho_hit_lower=v, umaban=1)
        df = pd.DataFrame([row])
        df = df[list(PREDICTION_COLUMNS)]
        _assert_valid_prediction_df(df)  # raise なければ OK


# ---------------------------------------------------------------------------
# Test 4: _FLOAT_COLS 拡張
# ---------------------------------------------------------------------------


def test_float_cols_includes_p_lower():
    """prediction_load._FLOAT_COLS に p_fukusho_hit_lower が含まれる（3ファイル連鎖）。"""
    assert "p_fukusho_hit_lower" in _FLOAT_COLS, (
        f"_FLOAT_COLS に p_fukusho_hit_lower が無い: {_FLOAT_COLS}"
    )
    assert "p_fukusho_hit" in _FLOAT_COLS, "p_fukusho_hit も _FLOAT_COLS に必須"


# ---------------------------------------------------------------------------
# Test 5: idempotent ALTER
# ---------------------------------------------------------------------------


def test_prediction_add_p_lower_sql_is_idempotent():
    """PREDICTION_ADD_P_LOWER_SQL が idempotent: ADD COLUMN IF NOT EXISTS +
    DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT（2回適用可能）."""
    sql = schema_module.PREDICTION_ADD_P_LOWER_SQL
    assert "ADD COLUMN IF NOT EXISTS p_fukusho_hit_lower" in sql, (
        "ADD COLUMN IF NOT EXISTS p_fukusho_hit_lower が無い（idempotent ALTER 違反）"
    )
    assert "DROP CONSTRAINT IF EXISTS prediction_p_lower_range" in sql, (
        "DROP CONSTRAINT IF EXISTS prediction_p_lower_range が無い（idempotent 違反）"
    )
    assert "ADD CONSTRAINT prediction_p_lower_range" in sql, (
        "ADD CONSTRAINT prediction_p_lower_range が無い（CHECK 制約未定義）"
    )


# ---------------------------------------------------------------------------
# Test 6: CHECK 制約 prediction_p_lower_range
# ---------------------------------------------------------------------------


def test_prediction_add_p_lower_sql_has_check_constraint():
    """CHECK 制約 prediction_p_lower_range が [0,1]・NULL 許容を定義する。"""
    sql = schema_module.PREDICTION_ADD_P_LOWER_SQL
    # NULL 許容 OR [0,1] の CHECK が含まれる
    assert "p_fukusho_hit_lower IS NULL" in sql, (
        "CHECK 制約に p_fukusho_hit_lower IS NULL 条件が無い（v1.0 binary 行の NULL 許容）"
    )
    assert "p_fukusho_hit_lower >= 0" in sql, "p_fukusho_hit_lower >= 0 条件が無い"
    assert "p_fukusho_hit_lower <= 1" in sql, "p_fukusho_hit_lower <= 1 条件が無い"


# ---------------------------------------------------------------------------
# Test 7: 合成 row helper 20列追従（test_prediction_load / test_is_primary_flag 経由）
# ---------------------------------------------------------------------------


def test_prediction_load_helper_20_columns():
    """test_prediction_load._make_synthetic_prediction_df が20列（p_fukusho_hit_lower 含む）を返す。

    PREDICTION_COLUMNS に p_fukusho_hit_lower が追加されたため・既存 helper がこれを含まないと
    df[list(PREDICTION_COLUMNS)] で KeyError になる（Regression・helper 20列追従）。
    """
    from tests.model.test_prediction_load import _make_synthetic_prediction_df

    df = _make_synthetic_prediction_df(
        3,
        model_type="lightgbm",
        model_version="helper-test-v1",
        as_of=pd.Timestamp("2026-06-26 12:00:00", tz="UTC").to_pydatetime(),
    )
    assert list(df.columns) == list(PREDICTION_COLUMNS), (
        "test_prediction_load helper の列が PREDICTION_COLUMNS と不一致（20列追従 Regression）"
    )
    assert "p_fukusho_hit_lower" in df.columns


def test_is_primary_flag_helper_20_columns():
    """test_is_primary_flag._make_prediction_row が20列（p_fukusho_hit_lower 含む）を返す。

    PREDICTION_COLUMNS に p_fukusho_hit_lower が追加されたため・既存 helper がこれを含まないと
    pd.DataFrame([row])[list(PREDICTION_COLUMNS)] で KeyError になる（Regression）。
    """
    from tests.db.test_is_primary_flag import _make_prediction_row
    from datetime import UTC, datetime

    row = _make_prediction_row(
        model_type="lightgbm",
        model_version="helper-test-v1",
        feature_snapshot_id="test-snap",
        as_of_datetime=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
    )
    df = pd.DataFrame([row])
    # PREDICTION_COLUMNS の全列が row に存在する
    missing = [c for c in PREDICTION_COLUMNS if c not in df.columns]
    assert not missing, (
        f"test_is_primary_flag helper に列が欠落（20列追従 Regression）: missing={missing}"
    )
    # p_fukusho_hit_lower が明示的に含まれる
    assert "p_fukusho_hit_lower" in row, (
        "test_is_primary_flag helper に p_fukusho_hit_lower キーが無い（Phase 12 追加漏れ）"
    )


# ---------------------------------------------------------------------------
# Test 8: [C-12-01-1 / HIGH] run_apply_schema.py step list 反映
# ---------------------------------------------------------------------------


def test_run_apply_schema_step_list_includes_p_lower():
    """[C-12-01-1 / HIGH] scripts/run_apply_schema.py のハードコード手動 step list に
    prediction_add_p_lower が1件含まれる（APPLY_ORDER だけでなく step list も更新必須）。"""
    import scripts.run_apply_schema as mod

    # apply() 関数のソースを AST parse して ("prediction_add_p_lower", schema_module.PREDICTION_ADD_P_LOWER_SQL)
    # の tuple がリテラルとして含まれるか走査する。
    source = inspect.getsource(mod.apply)
    tree = ast.parse(source)

    found_step_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == "prediction_add_p_lower":
                found_step_names.append(node.value)
        # tuple 中の "prediction_add_p_lower" 文字列定数も捕捉（ast.Constant で共通）

    assert len(found_step_names) >= 1, (
        "[C-12-01-1 / HIGH] run_apply_schema.py の手動 step list に "
        "'prediction_add_p_lower' が含まれない（APPLY_ORDER だけでは適用されない）"
    )


def test_run_apply_schema_step_list_count_is_1(capsys=None):
    """grep -c 'prediction_add_p_lower' scripts/run_apply_schema.py == 1 の機械保証。

    schema_module.PREDICTION_ADD_P_LOWER_SQL の参照が1回のみ（重複挿入でない）。
    """
    import scripts.run_apply_schema as mod

    source = inspect.getsource(mod)
    count = source.count("prediction_add_p_lower")
    assert count == 1, (
        f"[C-12-01-1] run_apply_schema.py の 'prediction_add_p_lower' 出現回数が "
        f"1でない: got {count}（重複 step 挿入を検出）"
    )


def test_schema_apply_order_includes_p_lower():
    """schema.py APPLY_ORDER に prediction_add_p_lower が1件含まれる。"""
    found = [name for name, _ in schema_module.APPLY_ORDER if name == "prediction_add_p_lower"]
    assert len(found) == 1, (
        f"schema.py APPLY_ORDER の prediction_add_p_lower 出現回数が1でない: {len(found)}"
    )


def test_schema_all_exports_p_lower_sql():
    """schema.__all__ に PREDICTION_ADD_P_LOWER_SQL が含まれる（外部参照経路）。"""
    assert "PREDICTION_ADD_P_LOWER_SQL" in schema_module.__all__, (
        "schema.__all__ に PREDICTION_ADD_P_LOWER_SQL が無い"
    )
    assert hasattr(schema_module, "PREDICTION_ADD_P_LOWER_SQL"), (
        "schema module に PREDICTION_ADD_P_LOWER_SQL 属性が無い"
    )


# ---------------------------------------------------------------------------
# Test 9: [C-12-01-4 / MEDIUM] race-relative 行で p_lower 非 NULL / v1.0 binary で NULL
# ---------------------------------------------------------------------------


def test_predict_p_fukusho_p_lower_none_when_not_provided():
    """[C-12-01-4] predict_p_fukusho が pred_proba_lower を渡さない場合・
    p_fukusho_hit_lower が全て None になる（v1.0 binary 行・後方互換）。

    predict_p_fukusho に pred_proba_lower 引数を追加し・None の場合は df["p_fukusho_hit_lower"]
    を None で埋める。None 以外の silent NaN 混入を許さない（C-12-01-4）。
    """
    # sklearn estimator は不要・pred_proba 注入で回避（test_predict.py helper パターン）
    from datetime import UTC, datetime
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(42)
    X = pd.DataFrame(
        rng.uniform(size=(5, 3)),
        columns=["feat_a", "feat_b", "feat_c"],
    )
    race_df = pd.DataFrame(
        {
            "year": [2024] * 5,
            "jyocd": ["05"] * 5,
            "kaiji": [1] * 5,
            "nichiji": ["01"] * 5,
            "racenum": list(range(1, 6)),
            "umaban": list(range(1, 6)),
            "kettonum": list(range(100, 105)),
            "race_date": pd.date_range("2024-01-01", periods=5).date,
        },
        index=X.index,
    )

    # v1.0 binary 呼出: pred_proba_lower を渡さない → 全行 None
    est = LogisticRegression(max_iter=1000, random_state=42).fit(
        X, (X.iloc[:, 0] > 0.5).astype(int)
    )
    df = predict_p_fukusho(
        est,
        X,
        model_type="lightgbm",
        model_version="test-v1-20260626",
        feature_snapshot_id="test-snap",
        calib_method="isotonic",
        race_df=race_df,
        split_label="test",
        as_of_datetime=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
    )
    # p_fukusho_hit_lower が全て None であること（silent NaN でなく明示的な None）
    assert df["p_fukusho_hit_lower"].isna().all(), (
        "v1.0 binary 呼出（pred_proba_lower 未渡）で p_fukusho_hit_lower が非 None を含む "
        "(C-12-01-4 v1.0 binary NULL 保証違反)"
    )


def test_predict_p_fukusho_p_lower_non_null_when_provided():
    """[C-12-01-4] predict_p_fukusho が pred_proba_lower を渡した場合・
    p_fukusho_hit_lower が全て非 None になる（race-relative 行・C-12-01-4 機械保証）。

    race-relative 経路（theta != None・pred_proba_lower を受け取る）では p_fukusho_hit_lower
    が常に非 None になることを予測 DataFrame 構築で保証する。
    """
    from datetime import UTC, datetime
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(42)
    X = pd.DataFrame(
        rng.uniform(size=(5, 3)),
        columns=["feat_a", "feat_b", "feat_c"],
    )
    race_df = pd.DataFrame(
        {
            "year": [2024] * 5,
            "jyocd": ["05"] * 5,
            "kaiji": [1] * 5,
            "nichiji": ["01"] * 5,
            "racenum": list(range(1, 6)),
            "umaban": list(range(1, 6)),
            "kettonum": list(range(100, 105)),
            "race_date": pd.date_range("2024-01-01", periods=5).date,
        },
        index=X.index,
    )
    est = LogisticRegression(max_iter=1000, random_state=42).fit(
        X, (X.iloc[:, 0] > 0.5).astype(int)
    )
    pred_proba = est.predict_proba(X)[:, 1]
    # race-relative 経路: pred_proba_lower を明示的に渡す（p_lower の代用・妥当な [0,1] 値）
    pred_proba_lower = np.maximum(0.0, pred_proba - 0.1)

    df = predict_p_fukusho(
        est,
        X,
        model_type="lightgbm_rr",
        model_version="test-rr-20260626-lgbrr-v1",
        feature_snapshot_id="test-snap-rr",
        calib_method="isotonic",
        race_df=race_df,
        split_label="test",
        as_of_datetime=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
        pred_proba=pred_proba,
        pred_proba_lower=pred_proba_lower,
    )
    # race-relative 経路: 全行非 None であること（NULL 混入が EV 計算/selected-only calib で silent マスクされない）
    assert df["p_fukusho_hit_lower"].notna().all(), (
        "race-relative 呼出（pred_proba_lower 渡）で p_fukusho_hit_lower に NULL が混入 "
        "(C-12-01-4 race-relative 非 NULL 保証違反)"
    )
    # [0,1] 範囲
    pl = df["p_fukusho_hit_lower"]
    assert (pl >= 0).all() and (pl <= 1).all()
