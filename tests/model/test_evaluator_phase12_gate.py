"""Phase 12 Plan 03 Task 2 unit tests: evaluator Phase 12 WARN gate (SC#4・D-06・§15.2 不変).

CONTEXT.md D-06 / 12-CONTEXT.md の核心:
  - §15.2 既存 BLOCK/WARN gate (calibration_max_dev/Brier/LogLoss/sum(p)) は一切不変 (後知恵すり替え禁止・聖域)。
  - selected-only calibration / odds-band conditional calibration = Phase 12 専用 WARN gate
    (core value 再定式化の直接的測定・報告のみでなく gate 化)。
  - BLOCK にはしない (Phase 12 は切替判断材料フェーズ・WARN が適切・v1.0 の4倍過大を catch)。

[C-12-03-2 / HIGH] check_acceptance_gate signature は不変 (metrics_dict, sum_p_check) のまま。
Phase 12 WARN gate は分離関数 check_phase12_warn_gate (選択 A・推奨) で実装。
"""

from __future__ import annotations

import inspect

import pytest

from src.model import evaluator


# ---------------------------------------------------------------------------
# Test 1: §15.2 gate 不変 (regression test)
# ---------------------------------------------------------------------------


def test_check_acceptance_gate_signature_unchanged() -> None:
    """[C-12-03-2 / HIGH] check_acceptance_gate の signature は不変 (metrics_dict, sum_p_check) の2つ.
    Phase 12 WARN gate は metrics_dict への混入でなく・分離関数で提供される."""
    sig = inspect.signature(evaluator.check_acceptance_gate)
    params = list(sig.parameters.keys())
    assert params == ["metrics_dict", "sum_p_check"], (
        f"§15.2 gate signature が変更された: {params} (期待 ['metrics_dict', 'sum_p_check'])"
    )


def test_check_acceptance_gate_block_unchanged_on_identical_input() -> None:
    """[D-06・regression test] §15.2 BLOCK gate が同一入力で同一判定 (calibration_max_dev/Brier/LogLoss/sum(p)).
    構造的 BLOCK 条件1 (baselines_all_lose) + 条件2 (sum_p_violation) の AND は一切変更なし."""
    # BLOCK 条件1+2 両立 → BLOCK
    metrics_block = {
        "lightgbm": {"logloss": 1.0, "brier": 0.4},  # 全敗
        "catboost": {"logloss": 1.0, "brier": 0.4},
        "bl1": {"logloss": 0.3, "brier": 0.1},
        "bl4": {"logloss": 0.35, "brier": 0.12},
        "bl5": {"logloss": 0.4, "brier": 0.15},
    }
    sum_p_block = {"large_violation_rate": 0.5, "small_violation_rate": 0.0}  # 条件2 成立
    result_block = evaluator.check_acceptance_gate(metrics_block, sum_p_block)
    assert result_block["block_triggered"] is True
    assert result_block["gate_verdict"] == "BLOCK"
    assert len(result_block["block_reasons"]) >= 1

    # WARN (片方だけ) も不変
    metrics_warn = {
        "lightgbm": {"logloss": 0.2, "brier": 0.08},  # SC#2 達成 (全 baselines に勝つ)
        "catboost": {"logloss": 0.2, "brier": 0.08},
        "bl1": {"logloss": 0.3, "brier": 0.1},
        "bl4": {"logloss": 0.35, "brier": 0.12},
        "bl5": {"logloss": 0.4, "brier": 0.15},
    }
    sum_p_clean = {"large_violation_rate": 0.0, "small_violation_rate": 0.0}
    result_warn = evaluator.check_acceptance_gate(metrics_warn, sum_p_clean)
    assert result_warn["block_triggered"] is False
    assert result_warn["gate_verdict"] == "WARN"
    # §15.2 keys が全て存在
    for key in ("block_triggered", "block_reasons", "warn_reasons", "gate_verdict",
                "comparable_baselines", "sum_p_block_threshold", "condition_flags"):
        assert key in result_warn, f"§15.2 return key {key!r} が欠損"


def test_check_acceptance_gate_return_keys_no_phase12_keys() -> None:
    """[C-12-03-2 / HIGH] check_acceptance_gate の return dict に Phase 12 専用 keys が混入しない.
    Phase 12 keys (phase12_warn_triggered/phase12_warn_reasons 等) は分離関数にのみ存在."""
    metrics = {
        "lightgbm": {"logloss": 0.2, "brier": 0.08},
        "bl1": {"logloss": 0.3, "brier": 0.1},
        "bl4": {"logloss": 0.35, "brier": 0.12},
        "bl5": {"logloss": 0.4, "brier": 0.15},
    }
    sum_p = {"large_violation_rate": 0.0, "small_violation_rate": 0.0}
    result = evaluator.check_acceptance_gate(metrics, sum_p)
    forbidden_phase12_keys = {
        "phase12_warn_triggered",
        "phase12_warn_reasons",
        "phase12_selected_only_calib_max_dev",
        "phase12_odds_band_calib_max_dev",
    }
    actual_keys = set(result.keys())
    leak = actual_keys & forbidden_phase12_keys
    assert not leak, (
        f"§15.2 gate return に Phase 12 専用 keys が混入: {leak} (D-06 違反・分離関数を使うべき)"
    )


# ---------------------------------------------------------------------------
# Test 2: Phase 12 WARN gate 追加 (selected-only calib_max_dev > threshold → WARN)
# ---------------------------------------------------------------------------


def test_check_phase12_warn_gate_exists() -> None:
    """[C-12-03-2 / 選択 A] check_phase12_warn_gate 分離関数が存在する."""
    assert hasattr(evaluator, "check_phase12_warn_gate"), (
        "check_phase12_warn_gate 分離関数が不在 (選択 A・推奨)"
    )


def test_check_phase12_warn_gate_selected_only_warn() -> None:
    """selected-only calib_max_dev が PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD を超えると
    phase12_warn_triggered=True / WARN reason 追加 (BLOCK でなく WARN・D-06)."""
    from src.eval.falsification import PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD

    result = evaluator.check_phase12_warn_gate(
        selected_only_calib_max_dev=0.20,  # threshold 0.10 を超過
        odds_band_calib_max_dev={"1.0-2.9": 0.05, "3.0-4.9": 0.04, "5.0-9.9": 0.06, "10+": 0.08},
    )
    assert result["phase12_warn_triggered"] is True
    assert len(result["phase12_warn_reasons"]) >= 1
    assert any("selected_only" in r or "selected-only" in r for r in result["phase12_warn_reasons"])
    # BLOCK でなく WARN
    assert "phase12_block_triggered" not in result or result.get("phase12_block_triggered") is False
    # 閾値定数の一致 (falsification.py から import)
    assert result.get("selected_only_threshold") == PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD


def test_check_phase12_warn_gate_selected_only_pass_when_below_threshold() -> None:
    """selected-only calib_max_dev が threshold 以下 → WARN なし."""
    result = evaluator.check_phase12_warn_gate(
        selected_only_calib_max_dev=0.05,  # threshold 0.10 以下
        odds_band_calib_max_dev={"1.0-2.9": 0.05, "3.0-4.9": 0.04, "5.0-9.9": 0.06, "10+": 0.08},
    )
    # selected-only は PASS (odds_band も threshold 0.15 以下なので全体 PASS)
    assert result["phase12_warn_triggered"] is False


# ---------------------------------------------------------------------------
# Test 3: odds-band conditional calib (各 band の calib_max_dev > threshold → WARN)
# ---------------------------------------------------------------------------


def test_check_phase12_warn_gate_odds_band_warn() -> None:
    """odds_band 別 conditional calib_max_dev が PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD を超えると
    該当 band の WARN reason が追加 (投票層 高オッズ域・SC#4)."""
    from src.eval.falsification import PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD

    result = evaluator.check_phase12_warn_gate(
        selected_only_calib_max_dev=0.05,
        odds_band_calib_max_dev={
            "1.0-2.9": 0.05,
            "3.0-4.9": 0.20,  # threshold 0.15 を超過 (中位オッズ域)
            "5.0-9.9": 0.06,
            "10+": 0.30,  # threshold 0.15 を超過 (大穴域)
        },
    )
    assert result["phase12_warn_triggered"] is True
    # 超過した band の reason が含まれる
    reasons_joined = " | ".join(result["phase12_warn_reasons"])
    assert "3.0-4.9" in reasons_joined
    assert "10+" in reasons_joined
    assert "1.0-2.9" not in reasons_joined  # 閾値以下の band は reason なし
    assert result.get("odds_band_threshold") == PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD


def test_check_phase12_warn_gate_odds_band_partial_dict() -> None:
    """odds_band dict が一部 band 欠損でも動作 (欠損 band は WARN 判定から skip)."""
    result = evaluator.check_phase12_warn_gate(
        selected_only_calib_max_dev=0.05,
        odds_band_calib_max_dev={"1.0-2.9": 0.05, "5.0-9.9": 0.20},  # 2 band のみ
    )
    assert result["phase12_warn_triggered"] is True
    reasons_joined = " | ".join(result["phase12_warn_reasons"])
    assert "5.0-9.9" in reasons_joined


# ---------------------------------------------------------------------------
# Test 4: WARN gate は BLOCK でなく WARN (D-06)
# ---------------------------------------------------------------------------


def test_phase12_warn_gate_never_blocks() -> None:
    """[D-06] Phase 12 gate は WARN のみ・BLOCK にはしない (Phase 12 は切替判断材料フェーズ).
    いかに過大予測があっても phase12_block_triggered は False."""
    result = evaluator.check_phase12_warn_gate(
        selected_only_calib_max_dev=0.99,  # 極端に過大
        odds_band_calib_max_dev={"1.0-2.9": 0.99, "3.0-4.9": 0.99, "5.0-9.9": 0.99, "10+": 0.99},
    )
    assert result["phase12_warn_triggered"] is True
    # BLOCK key が存在しても常に False
    assert result.get("phase12_block_triggered", False) is False


# ---------------------------------------------------------------------------
# Test 5: byte-reproducible (2回呼出で同一結果・deterministic)
# ---------------------------------------------------------------------------


def test_check_phase12_warn_gate_byte_reproducible() -> None:
    """WARN gate 判定が2回呼出で同一結果 (deterministic・byte-reproducible)."""
    args = dict(
        selected_only_calib_max_dev=0.20,
        odds_band_calib_max_dev={"1.0-2.9": 0.05, "3.0-4.9": 0.20, "5.0-9.9": 0.30, "10+": 0.10},
    )
    r1 = evaluator.check_phase12_warn_gate(**args)
    r2 = evaluator.check_phase12_warn_gate(**args)
    assert r1 == r2, "Phase 12 WARN gate が deterministic でない (byte-reproducible 違反)"


# ---------------------------------------------------------------------------
# Test 6: SAFE-01 (FEATURE_COLUMNS import 禁止)
# ---------------------------------------------------------------------------


def test_evaluator_no_feature_pipeline_import() -> None:
    """[SAFE-01] evaluator.py は FEATURE_COLUMNS/build_training_frame/load_feature_matrix を import しない."""
    import ast
    import inspect as insp
    import textwrap

    source = insp.getsource(evaluator)
    tree = ast.parse(textwrap.dedent(source))
    forbidden = {"FEATURE_COLUMNS", "build_training_frame", "load_feature_matrix"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden:
                    violations.append(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden:
                    violations.append(f"import {alias.name}")
    assert not violations, f"SAFE-01 違反: evaluator.py が feature 構築経路を import: {violations}"


# ---------------------------------------------------------------------------
# Test 7: constants import (C-12-04-3 集約・重複定義回避)
# ---------------------------------------------------------------------------


def test_evaluator_imports_phase12_thresholds_from_falsification() -> None:
    """[C-12-04-3 / C2-12-03-4] evaluator.py は PHASE12_*_THRESHOLD を falsification.py から import
    (重複定義回避・閾値 drift 防止)."""
    import ast
    import inspect as insp
    import textwrap

    source = insp.getsource(evaluator)
    # PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD / PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD が
    # falsification から import されている (再定義でない)
    assert "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD" in source
    assert "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD" in source
    # 再定義 (代入) がないことを AST で検証
    tree = ast.parse(textwrap.dedent(source))
    redefinitions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD",
                    "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD",
                ):
                    redefinitions.append(target.id)
    assert not redefinitions, (
        f"evaluator.py が閾値を再定義している (C-12-04-3 重複定義回避違反): {redefinitions}"
    )
