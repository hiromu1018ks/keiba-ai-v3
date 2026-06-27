# ruff: noqa: E501
"""Phase 12 Plan 01 (EV-01) compute_p_lower_conformal_shrinkage 契約テスト.

本テストは §11.2 聖域（test 窓 outcome を q_shrink 計算関数の引数に取らない構造的機械保証）
と byte-reproducible §19.1・SAFE-01（odds/ninki proxy 排除）を機械保証する。

Test 1-6 は 12-01-PLAN.md の <behavior> に対応する:
  - Test 1 (byte-reproducible): 2回呼出しで (p_lower, q_shrink) が np.array_equal で完全一致
  - Test 2 (§11.2 聖域・シグネチャ検証): test 窓 outcome 系引数を取らない
  - Test 3 (D-01 overprediction residual): y_calib=0, p_final_calib=0.8 で r=0.8・p_lower<=p_final
  - Test 4 (D-02 q_level 事前登録): q_level=0.90 で呼出可能・境界外で ValueError
  - Test 5 (Shared Pattern 4 fail-loud): NaN/inf 混入で RuntimeError
  - Test 6 (SAFE-01 odds proxy 排除): 本関数のみ AST scan で odds/ninki/fukuodds 出現 0件

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行・純粋 numpy 関数の契約検査）.
"""

from __future__ import annotations

import ast
import inspect

import numpy as np
import pytest

from src.model.race_relative import compute_p_lower_conformal_shrinkage


# ---------------------------------------------------------------------------
# Test 1: byte-reproducible（2回呼出しで完全一致・seed 非依存）
# ---------------------------------------------------------------------------


def test_p_lower_byte_reproducible():
    """compute_p_lower_conformal_shrinkage が byte-reproducible (§19.1).

    np.quantile は default linear interpolation で seed 非依存・決定論的。
    2回呼出しで (p_lower, q_shrink) が np.array_equal で完全一致する。
    """
    p_final = np.array([0.6, 0.3, 0.8, 0.1, 0.45])
    y_calib = np.array([0, 1, 0, 1, 0], dtype=float)
    p_final_calib = np.array([0.6, 0.3, 0.8, 0.1, 0.45])

    p_lower_1, q_shrink_1 = compute_p_lower_conformal_shrinkage(
        p_final, y_calib, p_final_calib, q_level=0.90
    )
    p_lower_2, q_shrink_2 = compute_p_lower_conformal_shrinkage(
        p_final, y_calib, p_final_calib, q_level=0.90
    )

    assert np.array_equal(p_lower_1, p_lower_2), (
        "p_lower が2回呼出しで不一致（byte-reproducible §19.1 違反）"
    )
    assert q_shrink_1 == q_shrink_2, (
        f"q_shrink が2回呼出しで不一致: {q_shrink_1} != {q_shrink_2}"
    )
    # 戻り型の契約
    assert isinstance(p_lower_1, np.ndarray), "p_lower は np.ndarray であること"
    assert isinstance(q_shrink_1, float), f"q_shrink は float であること: {type(q_shrink_1)}"


# ---------------------------------------------------------------------------
# Test 2: §11.2 聖域・シグネチャ検証（test 窓 outcome 系引数を取らない）
# ---------------------------------------------------------------------------


def test_p_lower_signature_no_test_outcome():
    """§11.2 聖域: inspect.signature が test 窓 outcome 系引数を取らない.

    構造的聖域ブロック（docstring 紳士協定でない）。引数 = {p_final, y_calib,
    p_final_calib, q_level} のみ。y_test/outcome_test/y_outcome_test を含まない。
    """
    sig = inspect.signature(compute_p_lower_conformal_shrinkage)
    params = set(sig.parameters.keys())
    forbidden = {"y_test", "outcome_test", "y_outcome_test", "outcome", "y_true", "labels"}
    leak = params & forbidden
    assert not leak, (
        f"§11.2 聖域違反: q_shrink 計算関数が test 窓 outcome 系引数を取る: {leak}"
    )
    # 期待する引数が過不足なく存在
    expected = {"p_final", "y_calib", "p_final_calib", "q_level"}
    assert params == expected, (
        f"引数セットが期待と不一致: got={params}, expected={expected}"
    )
    # q_level は keyword-only（*, の後）かつデフォルト 0.90
    q_param = sig.parameters["q_level"]
    assert q_param.default == 0.90, (
        f"q_level のデフォルトが 0.90 でない: {q_param.default}（D-02 事前登録値）"
    )
    assert q_param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "q_level は keyword-only（*, の後）であること（誤呼出防止）"
    )


# ---------------------------------------------------------------------------
# Test 3: D-01 overprediction residual
# ---------------------------------------------------------------------------


def test_p_lower_overprediction_residual_semantics():
    """D-01: r_calib = max(0, p_final_calib - y_calib) の過大予測残差ベース.

    y_calib=0, p_final_calib=0.8 → r_calib=0.8。q_shrink > 0 かつ
    p_lower = max(0, p_final - q_shrink) <= p_final になる。
    """
    y_calib = np.array([0.0, 0.0])
    p_final_calib = np.array([0.8, 0.8])
    p_final = np.array([0.6, 0.3, 0.8])

    p_lower, q_shrink = compute_p_lower_conformal_shrinkage(
        p_final, y_calib, p_final_calib, q_level=0.90
    )

    # r_calib = max(0, 0.8-0) = 0.8 の q_level 分位 = 0.8（要素2個・0.90 分位は線形補間で0.8）
    assert q_shrink > 0, f"q_shrink が正でない: {q_shrink}（r=0.8 期待）"
    # p_lower <= p_final（保守的 shrinkage）
    assert np.all(p_lower <= p_final), (
        f"p_lower が p_final を超える: p_lower={p_lower}, p_final={p_final}"
    )
    # 全て非負
    assert np.all(p_lower >= 0), f"p_lower が負: {p_lower}"


# ---------------------------------------------------------------------------
# Test 4: D-02 q_level 事前登録（境界 guard）
# ---------------------------------------------------------------------------


def test_p_lower_q_level_bounds():
    """D-02: q_level=0.90 で呼出可能・q_level <= 0 or >= 1 で ValueError."""
    p_final = np.array([0.5, 0.3])
    y_calib = np.array([0.0, 1.0])
    p_final_calib = np.array([0.5, 0.3])

    # 正常系: 0 < q_level < 1
    compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=0.90)
    compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=0.5)
    compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=0.05)

    # 異常系: q_level <= 0
    with pytest.raises(ValueError):
        compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=0.0)
    with pytest.raises(ValueError):
        compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=-0.1)

    # 異常系: q_level >= 1
    with pytest.raises(ValueError):
        compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=1.0)
    with pytest.raises(ValueError):
        compute_p_lower_conformal_shrinkage(p_final, y_calib, p_final_calib, q_level=1.5)


# ---------------------------------------------------------------------------
# Test 5: Shared Pattern 4 fail-loud（NaN/inf で RuntimeError・silent fallback 禁止）
# ---------------------------------------------------------------------------


def test_p_lower_fail_loud_on_non_finite():
    """Shared Pattern 4: y_calib/p_final_calib の NaN/inf は RuntimeError（silent fallback 禁止）.

    apply_race_relative_correction L227-232 と同一 idiom（D-09 fail-loud 鏡像）。
    """
    p_final = np.array([0.5, 0.3])
    p_final_calib_ok = np.array([0.5, 0.3])
    y_calib_ok = np.array([0.0, 1.0])

    # y_calib に NaN
    with pytest.raises(RuntimeError):
        compute_p_lower_conformal_shrinkage(
            p_final,
            np.array([0.0, np.nan]),
            p_final_calib_ok,
            q_level=0.90,
        )

    # y_calib に inf
    with pytest.raises(RuntimeError):
        compute_p_lower_conformal_shrinkage(
            p_final,
            np.array([0.0, np.inf]),
            p_final_calib_ok,
            q_level=0.90,
        )

    # p_final_calib に NaN
    with pytest.raises(RuntimeError):
        compute_p_lower_conformal_shrinkage(
            p_final,
            y_calib_ok,
            np.array([0.5, np.nan]),
            q_level=0.90,
        )

    # p_final_calib に inf
    with pytest.raises(RuntimeError):
        compute_p_lower_conformal_shrinkage(
            p_final,
            y_calib_ok,
            np.array([0.5, np.inf]),
            q_level=0.90,
        )


# ---------------------------------------------------------------------------
# Test 6: SAFE-01 odds proxy 排除（compute_p_lower_conformal_shrinkage 関数限定 AST scan）
# ---------------------------------------------------------------------------


def test_p_lower_no_odds_proxy_in_function_source():
    """SAFE-01 [C2-12-01-2]: 本関数のソース（モジュール全体でなく関数のみ）に
    odds/ninki/fukuodds の Name/Attribute 出現 0件.

    src/model/race_relative.py:46,348-349 の既存 _odds_band（compute_overprediction_penalty 内）
    評価専用正当参照で false-red にならないよう・関数限定スコープで走査する
    （test_audit_race_relative.py のモジュール全体 AST と二重保証）。
    """
    source = inspect.getsource(compute_p_lower_conformal_shrinkage)
    tree = ast.parse(source)

    forbidden = {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            violations.append(f"Name({node.id}) @ line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            violations.append(f"Attribute({node.attr}) @ line {node.lineno}")
    assert not violations, (
        f"SAFE-01 違反: compute_p_lower_conformal_shrinkage のソースに odds/ninki proxy が存在: {violations}"
    )


def test_p_lower_no_feature_pipeline_import():
    """SAFE-01 併用検証: race_relative モジュール全体が FEATURE_COLUMNS 構築経路を import しない.

    tests/audit/test_audit_race_relative.py の allow-list marker + feature 構築経路
    非参照の検査パターンを再利用し・p_lower 関数が feature 構築経路から独立していることを
    二重保証する（false red と false green の両方を回避）。
    """
    from src.model import race_relative

    source = inspect.getsource(race_relative)
    tree = ast.parse(source)

    forbidden_import_names = {
        "FEATURE_COLUMNS",
        "build_training_frame",
        "load_feature_matrix",
    }
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    violations.append(
                        f"ImportFrom({alias.name}) @ line {node.lineno}"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    violations.append(f"Import({alias.name}) @ line {node.lineno}")
        elif isinstance(node, ast.Name) and node.id in forbidden_import_names:
            violations.append(f"Name({node.id}) @ line {node.lineno}")
    assert not violations, (
        f"SAFE-01 違反: race_relative モジュールが feature 構築経路を参照: {violations}"
    )
