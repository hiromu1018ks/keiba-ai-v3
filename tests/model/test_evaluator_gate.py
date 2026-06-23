"""Phase 6 Plan 06-02 Task 2: check_acceptance_gate / compute_monotonicity_warn /
compute_yearly_inversion_warn のゲート判定ロジック単体テスト（D-01/D-02/D-03・hybrid gate）。

Purpose:
  §15.2 確率品質受入基準ゲート（EVAL-02）の純粋関数テスト。DB 不要・合成データで検証。

設計方針（06-02-PLAN.md Task 2 behavior 準拠）:
  - REVIEW HIGH#2 (D-02 AND 条件): BLOCK は「baselines 全敗 AND sum(p) 著乖離」の両立でのみ発火。
    片方だけでは warn_reasons 記録で WARN（出荷停止しない）。
  - D-03 曖昧基準（Spearman・反転数・年次反転）は WARN 参考レポート（人間判定）。
  - COMPARABLE_BASELINES=(bl1, bl4, bl5) から BL-2(NaN)/BL-3(§14.2 caveat) を除外。
  - check_acceptance_gate は純粋関数（block_triggered フラグを返すのみ・
    RuntimeError 送出は呼出側）。

参照:
  - src/model/evaluator.py（check_acceptance_gate / compute_monotonicity_warn /
    compute_yearly_inversion_warn / COMPARABLE_BASELINES / SUM_P_BLOCK_THRESHOLD）
  - 06-CONTEXT.md D-01/D-02/D-03（hybrid gate・構造的 BLOCK のみ hard fail）
  - reports/04-eval.json（実データ値・test_block_not_triggered_normal で使用）
"""

from __future__ import annotations

import numpy as np

from src.model.evaluator import (
    COMPARABLE_BASELINES,
    SUM_P_BLOCK_THRESHOLD,
    check_acceptance_gate,
    compute_monotonicity_warn,
    compute_yearly_inversion_warn,
)

# ---------------------------------------------------------------------------
# helpers — 合成 metrics_dict / sum_p_check
# ---------------------------------------------------------------------------


def _metrics(logloss: float, brier: float) -> dict[str, float]:
    """compute_metrics 戻り値の必要キーのみ抽出した合成 metrics。"""
    return {"logloss": logloss, "brier": brier}


def _sum_p_check(large: float = 0.0, small: float = 0.0) -> dict[str, float]:
    """check_sum_p_distribution 戻り値の必要キーのみ抽出した合成 sum_p_check。"""
    return {
        "large_violation_rate": large,
        "small_violation_rate": small,
        "total_races": 100,
        "diagnostic_note": "test",
    }


# reports/04-eval.json の実データ値（test_block_not_triggered_normal で使用）
_LGB_LOSS = 0.4748831925590833
_LGB_BRIER = 0.15221602476018015
_BL1_LOSS = 0.5210148456609544
_BL1_BRIER = 0.1695304309957974
_BL4_LOSS = 0.5182457131489694
_BL4_BRIER = 0.16869955178081578
_BL5_LOSS = 0.5130483177244112
_BL5_BRIER = 0.16709709333923806


# ===========================================================================
# Test 1 (REVIEW HIGH#2): baselines 全敗単独では BLOCK しない（AND 条件）
# ===========================================================================


def test_block_baselines_all_lose_AND_sum_p_ok() -> None:
    """主モデルが LogLoss+Brier 両方で BL-1/BL-4/BL-5 全てに劣るが sum(p) 正常の場合 →
    block_triggered==False・gate_verdict=="WARN"・warn_reasons に baselines_all_lose を記録。

    D-02 は両条件の同時満たしのみ BLOCK（REVIEW HIGH#2 AND 条件）。
    """
    metrics = {
        "lightgbm": _metrics(logloss=0.6, brier=0.2),  # BL 全てより劣る
        "bl1": _metrics(logloss=0.5, brier=0.18),
        "bl4": _metrics(logloss=0.52, brier=0.19),
        "bl5": _metrics(logloss=0.51, brier=0.185),
    }
    result = check_acceptance_gate(metrics, _sum_p_check(large=0.0, small=0.0))
    assert result["block_triggered"] is False, (
        "baselines 全敗単独で BLOCK 発火（D-02 AND 条件違反・REVIEW HIGH#2）"
    )
    assert result["gate_verdict"] == "WARN"
    assert result["condition_flags"]["baselines_all_lose"] is True
    assert result["condition_flags"]["sum_p_violation"] is False
    # warn_reasons に baselines_all_lose が記録されること
    assert any("baselines" in r.lower() or "lose" in r.lower() for r in result["warn_reasons"]), (
        f"warn_reasons に baselines_all_lose が記録されていない: {result['warn_reasons']}"
    )
    assert result["block_reasons"] == []


# ===========================================================================
# Test 2 (REVIEW HIGH#2): sum(p) 著乖離単独では BLOCK しない（AND 条件）
# ===========================================================================


def test_block_sum_p_divergence_AND_baselines_ok() -> None:
    """sum(p) large_violation_rate=0.5（>0.30）だが baselines には勝っている場合 →
    block_triggered==False・gate_verdict=="WARN"・warn_reasons に sum_p_violation を記録。
    """
    metrics = {
        "lightgbm": _metrics(logloss=_LGB_LOSS, brier=_LGB_BRIER),  # baselines に勝る
        "bl1": _metrics(logloss=_BL1_LOSS, brier=_BL1_BRIER),
        "bl4": _metrics(logloss=_BL4_LOSS, brier=_BL4_BRIER),
        "bl5": _metrics(logloss=_BL5_LOSS, brier=_BL5_BRIER),
    }
    result = check_acceptance_gate(metrics, _sum_p_check(large=0.5, small=0.0))
    assert result["block_triggered"] is False, (
        "sum(p) 著乖離単独で BLOCK 発火（D-02 AND 条件違反・REVIEW HIGH#2）"
    )
    assert result["gate_verdict"] == "WARN"
    assert result["condition_flags"]["baselines_all_lose"] is False
    assert result["condition_flags"]["sum_p_violation"] is True
    assert any("sum(p)" in r.lower() or "sum_p" in r.lower() for r in result["warn_reasons"]), (
        f"warn_reasons に sum_p_violation が記録されていない: {result['warn_reasons']}"
    )
    assert result["block_reasons"] == []


# ===========================================================================
# Test 3: 両条件成立時のみ BLOCK（D-02 AND 条件の忠実な実装）
# ===========================================================================


def test_block_triggered_when_both_conditions_met() -> None:
    """baselines_all_lose AND sum_p_violation の両方が成立 → block_triggered==True・
    block_reasons に両条件を含む・gate_verdict=="BLOCK"。
    """
    metrics = {
        "lightgbm": _metrics(logloss=0.6, brier=0.2),  # baselines 全敗
        "bl1": _metrics(logloss=0.5, brier=0.18),
        "bl4": _metrics(logloss=0.52, brier=0.19),
        "bl5": _metrics(logloss=0.51, brier=0.185),
    }
    result = check_acceptance_gate(metrics, _sum_p_check(large=0.5, small=0.4))
    assert result["block_triggered"] is True, (
        "両条件成立時に BLOCK 発火せず（D-02 AND 条件の忠実な実装違反）"
    )
    assert result["gate_verdict"] == "BLOCK"
    assert result["condition_flags"]["baselines_all_lose"] is True
    assert result["condition_flags"]["sum_p_violation"] is True
    # block_reasons に両条件が含まれる
    assert len(result["block_reasons"]) >= 1, (
        f"block_triggered=True だが block_reasons が空"
        f"（T-06-05 監査性違反）: {result['block_reasons']}"
    )


# ===========================================================================
# Test 4: reports/04-eval.json 実データで BLOCK 発火しない
# ===========================================================================


def test_block_not_triggered_normal() -> None:
    """reports/04-eval.json の実データ値（lightgbm 優位・sum_p violation_rate ほぼ 0%）→
    block_triggered==False・gate_verdict=="WARN"・warn_reasons は空。
    """
    metrics = {
        "lightgbm": _metrics(logloss=_LGB_LOSS, brier=_LGB_BRIER),
        "catboost": _metrics(logloss=0.48243, brier=0.15453),
        "bl1": _metrics(logloss=_BL1_LOSS, brier=_BL1_BRIER),
        "bl4": _metrics(logloss=_BL4_LOSS, brier=_BL4_BRIER),
        "bl5": _metrics(logloss=_BL5_LOSS, brier=_BL5_BRIER),
    }
    result = check_acceptance_gate(metrics, _sum_p_check(large=0.0, small=0.0))
    assert result["block_triggered"] is False
    assert result["gate_verdict"] == "WARN"
    assert result["condition_flags"]["baselines_all_lose"] is False
    assert result["condition_flags"]["sum_p_violation"] is False
    assert result["warn_reasons"] == [], (
        f"両条件とも非該当だが warn_reasons が空でない: {result['warn_reasons']}"
    )
    assert result["block_reasons"] == []


# ===========================================================================
# Test 5: BL-2/BL-3 が比較対象から除外される（COMPARABLE_BASELINES）
# ===========================================================================


def test_bl2_bl3_excluded_from_comparable() -> None:
    """metrics_dict に bl2/bl3 を入れても block/warn 判定に影響しない（COMPARABLE_BASELINES は
    bl1/bl4/bl5 のみ）。
    """
    base_metrics = {
        "lightgbm": _metrics(logloss=_LGB_LOSS, brier=_LGB_BRIER),
        "bl1": _metrics(logloss=_BL1_LOSS, brier=_BL1_BRIER),
        "bl4": _metrics(logloss=_BL4_LOSS, brier=_BL4_BRIER),
        "bl5": _metrics(logloss=_BL5_LOSS, brier=_BL5_BRIER),
    }
    # BL-2 (NaN) / BL-3 (極小値で主モデルを下回る偽陽性) を追加
    with_bl23 = dict(base_metrics)
    with_bl23["bl2"] = _metrics(logloss=float("nan"), brier=float("nan"))
    with_bl23["bl3"] = _metrics(logloss=0.3, brier=0.1)  # 主モデルより優秀（市場暗示確率）

    r1 = check_acceptance_gate(base_metrics, _sum_p_check())
    r2 = check_acceptance_gate(with_bl23, _sum_p_check())
    assert r1["block_triggered"] == r2["block_triggered"]
    r1_lose = r1["condition_flags"]["baselines_all_lose"]
    r2_lose = r2["condition_flags"]["baselines_all_lose"]
    assert r1_lose == r2_lose
    assert r1["condition_flags"]["baselines_all_lose"] is False, (
        "BL-3 が比較対象に入り baselines_all_lose=True になった疑い（COMPARABLE_BASELINES 違反）"
    )


# ===========================================================================
# Test 6: LogLoss のみ劣る（Brier は優位）→ baselines_all_lose=False・warn も空
# ===========================================================================


def test_bl1_single_loss_not_block_nor_warn() -> None:
    """主モデルが LogLoss のみ劣る（Brier は優位）ケース → baselines_all_lose=False
    （両方劣る必要）・warn_reasons も空。
    """
    metrics = {
        "lightgbm": _metrics(logloss=0.6, brier=0.1),  # LogLoss のみ劣る・Brier は優位
        "bl1": _metrics(logloss=0.5, brier=0.18),
        "bl4": _metrics(logloss=0.52, brier=0.19),
        "bl5": _metrics(logloss=0.51, brier=0.185),
    }
    result = check_acceptance_gate(metrics, _sum_p_check())
    assert result["block_triggered"] is False
    assert result["condition_flags"]["baselines_all_lose"] is False, (
        "LogLoss のみ劣る（Brier 優位）で baselines_all_lose=True（両方劣る必要がある・D-02 違反）"
    )
    assert result["warn_reasons"] == [], (
        f"片方のみ劣るケースで warn_reasons が空でない: {result['warn_reasons']}"
    )


# ===========================================================================
# Test 7: compute_monotonicity_warn が Spearman + bin 逆転数を返す
# ===========================================================================


def test_warn_monotonicity_spearman() -> None:
    """compute_monotonicity_warn が frac_pos と mean_pred の Spearman 順位相関 +
    bin 逆転数を返す（D-03 曖昧 WARN・人間判定参考）。
    """
    # 単調増加（理想的キャリブレーション）: frac_pos も mean_pred も単調増加
    bins_good = {
        "frac_pos": np.array([0.1, 0.3, 0.5, 0.7, 0.9]),
        "mean_pred": np.array([0.1, 0.3, 0.5, 0.7, 0.9]),
    }
    result_good = compute_monotonicity_warn(bins_good)
    assert "spearman_corr" in result_good
    assert "spearman_pvalue" in result_good
    assert "bin_inversions" in result_good
    assert result_good["bin_inversions"] == 0, (
        f"単調増加で bin_inversions!=0: {result_good['bin_inversions']}"
    )
    assert result_good["spearman_corr"] > 0.99, (
        f"単調増加で spearman_corr が低い: {result_good['spearman_corr']}"
    )

    # 単調減少（極端 miscalibration）: bin_inversions が増える
    bins_bad = {
        "frac_pos": np.array([0.9, 0.7, 0.5, 0.3, 0.1]),
        "mean_pred": np.array([0.1, 0.3, 0.5, 0.7, 0.9]),
    }
    result_bad = compute_monotonicity_warn(bins_bad)
    assert result_bad["bin_inversions"] == 4, (
        f"単調減少で bin_inversions!=4: {result_bad['bin_inversions']}"
    )
    assert result_bad["spearman_corr"] < -0.99, (
        f"単調減少で spearman_corr が -1 に近くない: {result_bad['spearman_corr']}"
    )


# ===========================================================================
# Test 8: frac_pos が短すぎる場合 NaN spearman
# ===========================================================================


def test_warn_monotonicity_short_array() -> None:
    """frac_pos が長さ1以下の場合 spearman_corr=NaN・bin_inversions=0。"""
    bins_short = {"frac_pos": np.array([0.5]), "mean_pred": np.array([0.5])}
    result = compute_monotonicity_warn(bins_short)
    assert np.isnan(result["spearman_corr"]), (
        f"長さ1で spearman_corr が NaN でない: {result['spearman_corr']}"
    )
    assert result["bin_inversions"] == 0

    # 完全に空の場合
    bins_empty = {"frac_pos": np.array([]), "mean_pred": np.array([])}
    result_empty = compute_monotonicity_warn(bins_empty)
    assert np.isnan(result_empty["spearman_corr"])
    assert result_empty["bin_inversions"] == 0


# ===========================================================================
# Test 9: gate_verdict が "BLOCK" または "WARN" のいずれか
# ===========================================================================


def test_gate_verdict_field() -> None:
    """gate_verdict が 'BLOCK'（block_reasons 非空）/'WARN'（block_reasons 空）のいずれか。"""
    # WARN ケース
    r_warn = check_acceptance_gate(
        {
            "lightgbm": _metrics(logloss=_LGB_LOSS, brier=_LGB_BRIER),
            "bl1": _metrics(logloss=_BL1_LOSS, brier=_BL1_BRIER),
            "bl4": _metrics(logloss=_BL4_LOSS, brier=_BL4_BRIER),
            "bl5": _metrics(logloss=_BL5_LOSS, brier=_BL5_BRIER),
        },
        _sum_p_check(),
    )
    assert r_warn["gate_verdict"] == "WARN"
    assert r_warn["gate_verdict"] in {"BLOCK", "WARN"}

    # BLOCK ケース
    r_block = check_acceptance_gate(
        {
            "lightgbm": _metrics(logloss=0.6, brier=0.2),
            "bl1": _metrics(logloss=0.5, brier=0.18),
            "bl4": _metrics(logloss=0.52, brier=0.19),
            "bl5": _metrics(logloss=0.51, brier=0.185),
        },
        _sum_p_check(large=0.5, small=0.4),
    )
    assert r_block["gate_verdict"] == "BLOCK"
    # T-06-05: BLOCK の場合は block_reasons が必ず非空
    assert len(r_block["block_reasons"]) > 0


# ===========================================================================
# Test 10: compute_yearly_inversion_warn が各年 curve に monotonicity を適用
# ===========================================================================


def test_yearly_inversion_warn_applies_monotonicity_per_year() -> None:
    """compute_yearly_inversion_warn が各年 curve に compute_monotonicity_warn を適用し
    {year: {spearman_corr, spearman_pvalue, bin_inversions}} を返す。
    """
    year_results = {
        "2021": {
            "curve": {
                "mean_pred": [0.1, 0.3, 0.5, 0.7, 0.9],
                "frac_pos": [0.1, 0.3, 0.5, 0.7, 0.9],
                "count": [100, 100, 100, 100, 100],
            },
            "scalar": {"ece": 0.05},
        },
        "2022": {
            "curve": {
                "mean_pred": [0.1, 0.3, 0.5, 0.7, 0.9],
                "frac_pos": [0.9, 0.7, 0.5, 0.3, 0.1],  # 単調減少（極端 miscalibration）
                "count": [80, 80, 80, 80, 80],
            },
            "scalar": {"ece": 0.3},
        },
    }
    result = compute_yearly_inversion_warn(year_results)
    assert "2021" in result and "2022" in result
    assert result["2021"]["bin_inversions"] == 0
    assert result["2021"]["spearman_corr"] > 0.99
    assert result["2022"]["bin_inversions"] == 4
    assert result["2022"]["spearman_corr"] < -0.99
    for year in ("2021", "2022"):
        assert "spearman_corr" in result[year]
        assert "spearman_pvalue" in result[year]
        assert "bin_inversions" in result[year]


# ===========================================================================
# Test 11: compute_yearly_inversion_warn が空入力で空 dict を返す
# ===========================================================================


def test_yearly_inversion_warn_handles_empty() -> None:
    """year_segment_results が空 dict の場合・空 dict を返す（欠損軍 WARN skip 時の安全網）。"""
    result = compute_yearly_inversion_warn({})
    assert result == {}


# ===========================================================================
# Test 12 (REVIEW HIGH#2): block_reasons と warn_reasons の分離
# ===========================================================================


def test_block_reasons_vs_warn_reasons_separation() -> None:
    """block_reasons（BLOCK 発火要因・D-02 両条件成立時のみ）と warn_reasons（参考記録・
    baselines_all_lose 単独・sum_p_violation 単独等）が分離されて戻り値に含まれる。
    """
    # baselines 全敗単独（warn に記録・block は空）
    metrics_baselines_only = {
        "lightgbm": _metrics(logloss=0.6, brier=0.2),
        "bl1": _metrics(logloss=0.5, brier=0.18),
        "bl4": _metrics(logloss=0.52, brier=0.19),
        "bl5": _metrics(logloss=0.51, brier=0.185),
    }
    r1 = check_acceptance_gate(metrics_baselines_only, _sum_p_check())
    assert len(r1["warn_reasons"]) > 0, "baselines_all_lose 単独で warn_reasons 空"
    assert r1["block_reasons"] == [], (
        f"baselines_all_lose 単独で block_reasons 非空（AND 条件違反）: {r1['block_reasons']}"
    )
    assert r1["block_triggered"] is False

    # 両条件成立（block に記録・warn にも記録または空）
    r2 = check_acceptance_gate(metrics_baselines_only, _sum_p_check(large=0.5, small=0.4))
    assert len(r2["block_reasons"]) > 0
    assert r2["block_triggered"] is True

    # 戻り値に condition_flags が含まれる（監査性）
    assert "condition_flags" in r2
    assert "baselines_all_lose" in r2["condition_flags"]
    assert "sum_p_violation" in r2["condition_flags"]


# ===========================================================================
# Test 13: condition_flags と comparable_baselines / sum_p_block_threshold の監査性
# ===========================================================================


def test_audit_fields_present() -> None:
    """戻り値に comparable_baselines / sum_p_block_threshold / condition_flags が含まれる
    （Phase 8 対抗的監査で再現可能・T-06-04/T-06-05 監査性担保）。
    """
    result = check_acceptance_gate(
        {"lightgbm": _metrics(logloss=_LGB_LOSS, brier=_LGB_BRIER)}, _sum_p_check()
    )
    assert result["comparable_baselines"] == list(COMPARABLE_BASELINES)
    assert result["sum_p_block_threshold"] == SUM_P_BLOCK_THRESHOLD
    assert isinstance(result["condition_flags"], dict)
    assert set(result["condition_flags"].keys()) == {"baselines_all_lose", "sum_p_violation"}
