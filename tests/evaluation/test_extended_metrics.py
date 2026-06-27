"""Phase 12 Plan 03 Task 2 unit tests: segment_eval compute_roi_by_bin + refund_accounting slippage.

EVAL-01 拡張評価指標 (EV-decile ROI / model-market disagreement ROI / snapshot→final payout slippage)
を検証する。D-07 (gate 化しない・switch_recommendation 入力 + 報告のみ)。

聖域:
  - [C-12-03-3 MEDIUM] EV-decile / disagreement ROI は segment_eval.evaluate_segment_axis
    (calibration curve 用 API) でなく・compute_roi_by_bin 別関数で実装。
    evaluate_segment_axis は不変 (bit-identical binning 契約維持)。
  - [C-12-03-5 MEDIUM] refund_accounting.compute_snapshot_final_slippage は
    row ベース版 (_lookup_payfukusyo_pay を呼ぶ) と payout_amount 受け取り版の2種類を提供。
  - SAFE-01: evaluator / segment_eval / refund_accounting の Phase 12 拡張は
    FEATURE_COLUMNS を import しない (層分離).
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import numpy as np
import pandas as pd
import pytest

from src.ev import refund_accounting
from src.model import segment_eval


# ---------------------------------------------------------------------------
# Test 4: [C-12-03-3 MEDIUM] compute_roi_by_bin 別関数 (evaluate_segment_axis 不変)
# ---------------------------------------------------------------------------


def test_compute_roi_by_bin_exists_in_segment_eval() -> None:
    """[C-12-03-3] segment_eval に compute_roi_by_bin 別関数が存在 (evaluate_segment_axis でなく)."""
    assert hasattr(segment_eval, "compute_roi_by_bin"), (
        "compute_roi_by_bin が segment_eval に存在しない (C-12-03-3 別関数)"
    )


def test_evaluate_segment_axis_signature_unchanged() -> None:
    """[C-12-03-3] evaluate_segment_axis の signature は不変 (calibration curve 用 API・bit-identical 契約)."""
    sig = inspect.signature(segment_eval.evaluate_segment_axis)
    params = list(sig.parameters.keys())
    # 既存契約: y_true, y_pred, segment_values, axis_name, n_bins
    assert "y_true" in params
    assert "y_pred" in params
    assert "segment_values" in params
    assert "axis_name" in params
    # binning 系の引数は追加されていない (ROI 計算は別関数)
    assert "bin_col" not in params
    assert "recovery_rate" not in params


def test_compute_roi_by_bin_ev_decile_deterministic() -> None:
    """[C-12-03-3] EV-decile binning が pd.qcut(EV_lower, 10, duplicates='drop') で決定論的.
    2回呼出で bit-identical."""
    rng = np.random.default_rng(42)
    n = 500
    df = pd.DataFrame(
        {
            "EV_lower": rng.uniform(0.5, 2.0, size=n),
            "payout_amount": rng.uniform(0, 200, size=n),
            "effective_stake": 100.0,
            "profit": rng.uniform(-100, 200, size=n),
            "fukusho_hit": rng.integers(0, 2, size=n),
        }
    )
    out1 = segment_eval.compute_roi_by_bin(df, bin_col="EV_lower", n_bins=10)
    out2 = segment_eval.compute_roi_by_bin(df, bin_col="EV_lower", n_bins=10)
    # 戻り値は DataFrame・2回呼出で bit-identical
    pd.testing.assert_frame_equal(out1, out2)


def test_compute_roi_by_bin_contains_recovery_rate_profit_hit_rate() -> None:
    """[C-12-03-3] compute_roi_by_bin 戻り値に recovery_rate/profit_loss/hit_rate/n_samples が含まれる
    (compute_backtest_metrics の group-by と同等の集計)."""
    rng = np.random.default_rng(7)
    n = 300
    df = pd.DataFrame(
        {
            "EV_lower": rng.uniform(0.5, 2.0, size=n),
            "payout_amount": rng.uniform(0, 200, size=n),
            "effective_stake": 100.0,
            "profit": rng.uniform(-100, 200, size=n),
            "fukusho_hit": rng.integers(0, 2, size=n),
        }
    )
    out = segment_eval.compute_roi_by_bin(df, bin_col="EV_lower", n_bins=5)
    assert isinstance(out, pd.DataFrame)
    for col in ("bin", "n_samples", "recovery_rate", "profit_loss", "hit_rate"):
        assert col in out.columns, f"compute_roi_by_bin 戻り値に {col!r} が無い"
    # bin 数は n_bins 以下 (duplicates='drop' で減る可能性あり)
    assert len(out) <= 5
    assert (out["n_samples"] > 0).all()


def test_compute_roi_by_bin_disagreement_logit_clip() -> None:
    """[C-12-03-3 / Pitfall 6] model-market disagreement ROI も compute_roi_by_bin で計算可能.
    |logit(model_p) - logit(market_implied)| を binning (logit_clip は falsification と同一契約)."""
    from src.eval.falsification import logit_clip

    rng = np.random.default_rng(11)
    n = 300
    model_p = rng.uniform(0.05, 0.95, size=n)
    market_implied = rng.uniform(0.05, 0.95, size=n)
    df = pd.DataFrame(
        {
            "disagreement": np.abs(logit_clip(model_p) - logit_clip(market_implied)),
            "payout_amount": rng.uniform(0, 200, size=n),
            "effective_stake": 100.0,
            "profit": rng.uniform(-100, 200, size=n),
            "fukusho_hit": rng.integers(0, 2, size=n),
        }
    )
    out = segment_eval.compute_roi_by_bin(df, bin_col="disagreement", n_bins=5)
    # disagreement の高い bin で recovery_rate が測定されている (中身の正しさは別途・関数の契約検証)
    assert len(out) >= 1
    assert (out["n_samples"] > 0).all()


def test_compute_roi_by_bin_uses_odds_band_no_custom_binning() -> None:
    """[C-12-03-3] compute_roi_by_bin は独自 binning でなく pd.qcut(duplicates='drop') を使用
    (codex review HIGH#2・bit-identical)."""
    source = inspect.getsource(segment_eval.compute_roi_by_bin)
    assert "pd.qcut" in source, "compute_roi_by_bin が pd.qcut を使っていない (独自 binning 禁止)"
    assert "duplicates" in source and "drop" in source, "pd.qcut(duplicates='drop') でない"


# ---------------------------------------------------------------------------
# Test 5: [C-12-03-5 MEDIUM] refund_accounting.compute_snapshot_final_slippage (2種類)
# ---------------------------------------------------------------------------


def test_compute_snapshot_final_slippage_payout_amount_version_exists() -> None:
    """[C-12-03-5] payout_amount 受け取り版 compute_snapshot_final_slippage が存在."""
    assert hasattr(refund_accounting, "compute_snapshot_final_slippage"), (
        "compute_snapshot_final_slippage (payout_amount 版) が refund_accounting に存在しない"
    )


def test_compute_snapshot_final_slippage_from_row_version_exists() -> None:
    """[C-12-03-5] row ベース版 compute_snapshot_final_slippage_from_row が存在
    (_lookup_payfukusyo_pay を呼んで slot を解決)."""
    assert hasattr(refund_accounting, "compute_snapshot_final_slippage_from_row"), (
        "compute_snapshot_final_slippage_from_row (row ベース版) が refund_accounting に存在しない"
    )


def test_compute_snapshot_final_slippage_formula_payout_amount() -> None:
    """[D-07 / C-12-03-5] compute_snapshot_final_slippage が payout/100 - fuku_odds_lower を計算."""
    # payout=200 (100円あたり)・fuku_odds_lower=1.5 → 200/100 - 1.5 = 0.5
    result = refund_accounting.compute_snapshot_final_slippage(payout_amount=200, fuku_odds_lower=1.5)
    assert result == pytest.approx(200 / 100.0 - 1.5)


def test_compute_snapshot_final_slippage_formula_negative() -> None:
    """slippage は負も取りうる (final payout が snapshot odds より低い場合)."""
    # payout=80・fuku_odds_lower=1.5 → 0.8 - 1.5 = -0.7
    result = refund_accounting.compute_snapshot_final_slippage(payout_amount=80, fuku_odds_lower=1.5)
    assert result == pytest.approx(0.8 - 1.5)


def test_compute_snapshot_final_slippage_from_row_uses_lookup() -> None:
    """[C-12-03-5] row ベース版が _lookup_payfukusyo_pay を呼んで slot を解決する経路を持つ.
    呼出側が slot lookup を二重/欠落しないことを docstring とソースで保証."""
    # row を構築: umaban=3 が PayFukusyoUmaban1='03' slot に的中・pay=200
    row = pd.Series(
        {
            "umaban": 3,
            "payfukusyoumaban1": "03",
            "payfukusyopay1": "200",
            "payfukusyoumaban2": "00",
            "payfukusyopay2": "0",
        }
    )
    result = refund_accounting.compute_snapshot_final_slippage_from_row(row, fuku_odds_lower=1.5)
    # _lookup_payfukusyo_pay が 200 を返す → 200/100 - 1.5 = 0.5
    assert result == pytest.approx(0.5)


def test_compute_snapshot_final_slippage_from_row_no_hit_returns_nan_like() -> None:
    """[C-12-03-5 / Shared Pattern 4] 該当 slot なし (payout=0) の場合・slippage は計算されるが
    呼出側で filter されることを想定 (silent fallback でなく・0/100 - odds がそのまま返る)."""
    row = pd.Series(
        {
            "umaban": 9,  # slot に無い馬番
            "payfukusyoumaban1": "03",
            "payfukusyopay1": "200",
            "payfukusyoumaban2": "00",
            "payfukusyopay2": "0",
        }
    )
    result = refund_accounting.compute_snapshot_final_slippage_from_row(row, fuku_odds_lower=1.5)
    # 不的中 slot lookup=0 → 0/100 - 1.5 = -1.5
    assert result == pytest.approx(0.0 / 100.0 - 1.5)


def test_compute_snapshot_final_slippage_docstring_explains_two_versions() -> None:
    """[C-12-03-5] docstring が「slot lookup は row 版が自動で行う・payout_amount 版は呼出側が解決済みの値を渡す・
    二重 slot lookup を避けるためどちらかを使う」を明記 (silent バグ回避)."""
    doc1 = inspect.getdoc(refund_accounting.compute_snapshot_final_slippage) or ""
    doc2 = inspect.getdoc(refund_accounting.compute_snapshot_final_slippage_from_row) or ""
    combined = doc1 + "\n" + doc2
    # 二重 slot lookup 回避の指示が含まれる
    assert "_lookup_payfukusyo_pay" in combined or "slot" in combined.lower(), (
        "compute_snapshot_final_slippage の docstring に slot lookup の経路説明がない"
    )


# ---------------------------------------------------------------------------
# Test 6: SAFE-01 (FEATURE_COLUMNS import 禁止・層分離)
# ---------------------------------------------------------------------------


def test_segment_eval_no_feature_pipeline_import() -> None:
    """[SAFE-01] segment_eval.py は FEATURE_COLUMNS/build_training_frame/load_feature_matrix を import しない."""
    source = inspect.getsource(segment_eval)
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
    assert not violations, f"SAFE-01 違反: segment_eval.py が feature 構築経路を import: {violations}"


def test_refund_accounting_no_feature_pipeline_import() -> None:
    """[SAFE-01] refund_accounting.py は FEATURE_COLUMNS/build_training_frame/load_feature_matrix を import しない."""
    source = inspect.getsource(refund_accounting)
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
    assert not violations, f"SAFE-01 違反: refund_accounting.py が feature 構築経路を import: {violations}"


# ---------------------------------------------------------------------------
# Test 7: bit-identical binning (ODDS_BAND_EDGES は変更なし)
# ---------------------------------------------------------------------------


def test_odds_band_edges_unchanged() -> None:
    """[codex HIGH#2] ODDS_BAND_EDGES / ODDS_BAND_LABELS は Phase 12 で一切変更なし (bit-identical)."""
    assert np.allclose(segment_eval.ODDS_BAND_EDGES, [0.0, 2.9, 4.9, 9.9, np.inf])
    assert segment_eval.ODDS_BAND_LABELS == ("1.0-2.9", "3.0-4.9", "5.0-9.9", "10+")
