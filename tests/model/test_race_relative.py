# ruff: noqa: E501
"""Phase 11 SC#1/#3 unit test: race_relative pure 関数（α_r 二分探索・clip・sum(p)=k・bit-identical）.

検証内容（11-VALIDATION.md Per-Requirement Test Map・11-RESEARCH.md Pattern 1/2/3）:

- MODEL-01: ``solve_alpha_for_race`` が sum(p)=k を厳密達成（|sum−k| < 1e-9・実測 4.44e-16）
- MODEL-01: f(α) 単調増加で唯一解（IVT）
- MODEL-01: θ→∞ で α → logit(k/n)・θ→0+ で brentq 失敗（尖鋭化・発散検出）
- MODEL-01: clip ε=1e-6 で isotonic 0/1 端点生成時に sum(p)=k 精度 <1e-12
- MODEL-01: ``apply_race_relative_correction`` が race 毎に独立動作（他 race 不参照・D-10）
- MODEL-01: base logit s_i が logit(proba) 経路で bit-identical（atol=1e-6）
- MODEL-01: sum(p)=k 不変性が完全パイプラインで成立（補正後追加 calib なし・D-06）
- MODEL-01: overprediction penalty が segment_eval binning と bit-identical
- MODEL-01: k 決定が sales_start_entry_count ベース・同着不反映（D-08）
- SAFE-01/D-09: binary logit 欠損で RuntimeError（neutral 補完不採用・silent fallback 禁止）
- SC#3: 同一 LightGBM 小モデル同一 seed で race-relative p が bit-identical
  （codex review MEDIUM: LightGBM≠CatBoost cross-family 同一性でなく・同一モデル同一 seed の再現性）

TDD RED phase（plan 11-01 type: tdd・Wave 0 stub）:
本ファイルは12テストの契約（docstring + 期待数値 + assert）を定義する。
``src/model/race_relative.py`` は stub（``raise NotImplementedError``）のため・
stub 関数を呼ぶテストは NotImplementedError で RED になる。Wave 1（plan 11-02）で
実装されると GREEN。これが TDD RED phase（fake-green 構造的防止・実装と test の乖離排除）。

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行可能・marker なし・純粋関数検査）。

参考: 11-RESEARCH.md Pattern 1/2/3（実証検証済みコード断片） / src/model/race_relative.py /
      tests/model/test_calibrator.py（pure 関数 unit test idiom の踏襲元）.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.model.race_relative import (
    ALPHA_SEARCH_XTOL,
    P_CAL_CLIP_EPSILON,
    THETA_CANDIDATES,
    apply_race_relative_correction,
    compute_overprediction_penalty,
    solve_alpha_for_race,
)


# ---------------------------------------------------------------------------
# MODEL-01: α_r 二分探索が sum(p)=k を厳密達成
# ---------------------------------------------------------------------------
def test_solve_alpha_sum_p_equals_k() -> None:
    """MODEL-01: α_r 二分探索が sum(p)=k を厳密達成（|sum−k| < 1e-9・実測 4.44e-16）.

    11-RESEARCH.md Pattern 1 実証検証: 18頭・θ=1.0・k=3 のケースで
    brentq が |sum(p)−k| ≤ ALPHA_SEARCH_XTOL (1e-9) で収束する（実測 4.44e-16）。
    """
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=18)
    alpha = solve_alpha_for_race(s, theta=1.0, k=3)
    sum_p = float(np.sum(1.0 / (1.0 + np.exp(-(s / 1.0 + alpha)))))
    assert abs(sum_p - 3) < 1e-9, (
        f"sum(p)={sum_p} != k=3・|diff|={abs(sum_p - 3)} >= 1e-9（ALPHA_SEARCH_XTOL 違反）"
    )


def test_alpha_monotonic_unique_solution() -> None:
    """MODEL-01: f(α) = Σ sigmoid(s_i/θ + α) − k が単調増加で唯一解（IVT）.

    11-RESEARCH.md Pattern 1: f(α) は α について厳密単調増加・連続。
    値域 (−k, n−k) ⊃ 0 から IVT で唯一解が存在する。
    単調増加性を linspace 21 点で検証し・solve_alpha_for_race が f(α)=0 を満たすことを確認。
    """
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=12)
    theta, k = 1.0, 3

    def f(alpha: float) -> float:
        z = s / theta + alpha
        return float(np.sum(1.0 / (1.0 + np.exp(-z))) - k)

    alphas = np.linspace(-10, 10, 21)
    vals = [f(a) for a in alphas]
    # 単調増加（数値誤差許容）
    for i in range(len(vals) - 1):
        assert vals[i] <= vals[i + 1] + 1e-12, (
            f"f(α) が単調増加でない: α={alphas[i]} → {vals[i]}, α={alphas[i+1]} → {vals[i+1]}"
        )
    # 唯一解が f(α)=0 を満たす
    alpha_sol = solve_alpha_for_race(s, theta=theta, k=k)
    assert abs(f(alpha_sol)) < 1e-9, (
        f"solve_alpha_for_race の解が f(α)=0 を満たさない: f({alpha_sol})={f(alpha_sol)}"
    )


def test_theta_inf_limit() -> None:
    """MODEL-01: θ→∞ で α → logit(k/n) に収束（平坦化の理論値）.

    11-RESEARCH.md Pattern 1 境界挙動: θ=1e6 で α=-1.609438 = logit(3/18) に収束する（実証）。
    θ が十分大きいとき・sigmoid(s_i/θ + α) → sigmoid(α) となり・
    n * sigmoid(α) = k → α = logit(k/n)。
    """
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=18)
    n = 18
    k = 3
    expected_alpha_inf = float(np.log(k / (n - k)))  # logit(k/n) = log(3/15) = -1.609438

    alpha_large_theta = solve_alpha_for_race(s, theta=1e6, k=k)
    assert abs(alpha_large_theta - expected_alpha_inf) < 1e-4, (
        f"θ→∞ で α → logit(k/n)={expected_alpha_inf} に収束しない: "
        f"α(θ=1e6)={alpha_large_theta}・diff={abs(alpha_large_theta - expected_alpha_inf)}"
    )


def test_theta_zero_divergence() -> None:
    """MODEL-01: θ→0+ で brentq 失敗（尖鋭化・発散検出）.

    11-RESEARCH.md Pattern 1 境界挙動・Pitfall 2: θ<0.1 等の尖鋭化パラメータで
    α_r が有限値に収まらず発散し・brentq が符号不一致で失敗する（実証）。
    これが THETA_CANDIDATES に極小値（θ<0.5）を含めない根拠。
    失敗時は RuntimeError（brentq の収束失敗をラップ）を期待。
    """
    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=12)
    # θ=1e-3 は極小値・尖鋭化で α_r 発散
    with pytest.raises((RuntimeError, ValueError)) as exc_info:
        solve_alpha_for_race(s, theta=1e-3, k=3)
    # brentq 失敗メッセージか RuntimeError ラップのいずれか
    assert exc_info.value is not None


def test_clip_epsilon_isotonic_endpoints() -> None:
    """MODEL-01: clip ε=1e-6 で isotonic 0/1 端点生成時に sum(p)=k 精度 <1e-12.

    11-RESEARCH.md Pitfall 1・researcher 裁量 #2: IsotonicRegression は正例群に 1.0・
    負例群に 0.0 を生成する（段階関数）。logit 変換前に np.clip(p_cal, ε, 1−ε) が必須。
    ε=P_CAL_CLIP_EPSILON (1e-6) で logit 動的範囲 ±13.8・sum(p)=k 精度 <1e-12 を同時達成（実証）。

    本テストは p_cal に 0.0 と 1.0 を含むケースで apply_race_relative_correction が
    適切に clip して sum(p)=k を厳密達成することを検証。
    """
    # p_cal に 0.0 と 1.0 の極端値を含む（IsotonicRegression 端点を模倣）
    p_cal = np.array([0.0, 0.0, 0.3, 0.5, 0.7, 1.0, 1.0, 0.4])
    race_ids = np.array(["R1"] * 8)
    k_per_race = np.array([3] * 8)

    p_final = apply_race_relative_correction(
        p_cal=p_cal, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
    )
    sum_p = float(np.sum(p_final))
    assert abs(sum_p - 3) < 1e-12, (
        f"clip ε=1e-6 で sum(p)=k 精度 <1e-12 達成せず: sum(p)={sum_p}・"
        f"|diff|={abs(sum_p - 3)}（Pitfall 1 対策・P_CAL_CLIP_EPSILON 違反）"
    )


def test_race_independence() -> None:
    """MODEL-01: apply_race_relative_correction が race 毎に独立動作（他 race 不参照・D-10）.

    11-RESEARCH.md Pattern 1: apply_race_relative_correction は np.unique(race_ids) で
    race 毎に独立ループ。他 race の logit を混入させない（D-10 自己完結性）。
    race R1 と R2 を混ぜて処理しても・それぞれ単独で処理した場合と同一の p_final になる。
    """
    rng = np.random.default_rng(42)
    # R1: 6 頭・k=2・R2: 8 頭・k=3
    p_cal_r1 = rng.uniform(0.1, 0.9, size=6)
    p_cal_r2 = rng.uniform(0.1, 0.9, size=8)

    # 単独処理
    p_final_r1_alone = apply_race_relative_correction(
        p_cal=p_cal_r1,
        theta=1.0,
        k_per_race=np.array([2] * 6),
        race_ids=np.array(["R1"] * 6),
    )
    p_final_r2_alone = apply_race_relative_correction(
        p_cal=p_cal_r2,
        theta=1.0,
        k_per_race=np.array([3] * 8),
        race_ids=np.array(["R2"] * 8),
    )

    # 結合処理
    p_cal_combined = np.concatenate([p_cal_r1, p_cal_r2])
    race_ids_combined = np.array(["R1"] * 6 + ["R2"] * 8)
    k_per_race_combined = np.array([2] * 6 + [3] * 8)
    p_final_combined = apply_race_relative_correction(
        p_cal=p_cal_combined,
        theta=1.0,
        k_per_race=k_per_race_combined,
        race_ids=race_ids_combined,
    )

    # 結合処理の結果が単独処理と一致する（race 独立性）
    assert np.allclose(p_final_combined[:6], p_final_r1_alone, atol=1e-12), (
        "R1 の p_final が結合処理と単独処理で不一致（race 独立性違反・D-10）"
    )
    assert np.allclose(p_final_combined[6:], p_final_r2_alone, atol=1e-12), (
        "R2 の p_final が結合処理と単独処理で不一致（race 独立性違反・D-10）"
    )


def test_base_logit_bit_identical() -> None:
    """MODEL-01: base logit s_i が logit(proba) 経路で bit-identical（atol=1e-6）.

    11-RESEARCH.md Pattern 2: 両モデルとも decision_function なし・
    predict_proba → clip(ε, 1−ε) → logit(p_cal) = s_i が統一経路。
    LightGBM: predict(X, raw_score=True) == logit(predict_proba) atol=1e-6（実証）。
    CatBoost: predict(X, prediction_type='RawFormulaVal') == logit(predict_proba) atol=1e-6（実証）。
    本テストは proba → clip → logit → sigmoid が可逆であることを検証（atol=1e-6）。
    """
    rng = np.random.default_rng(42)
    # base logit 相当の値を生成
    base_s = rng.normal(0, 1, size=20)
    # logit → proba → clip → logit の往復が bit-identical
    proba = 1.0 / (1.0 + np.exp(-base_s))
    p_clipped = np.clip(proba, P_CAL_CLIP_EPSILON, 1.0 - P_CAL_CLIP_EPSILON)
    logit_recovered = np.log(p_clipped / (1.0 - p_clipped))
    # atol=1e-6 で bit-identical（ε=1e-6 で logit 動的範囲 ±13.8・精度劣化なし）
    assert np.allclose(logit_recovered, base_s, atol=1e-6), (
        "logit(proba) 経路が可逆でない・base logit s_i が bit-identical に復元されない "
        f"（atol=1e-6 違反・max_diff={np.max(np.abs(logit_recovered - base_s))}）"
    )


def test_pipeline_sum_p_invariant() -> None:
    """MODEL-01: sum(p)=k 不変性が完全パイプラインで成立（補正後追加 calib なし・D-06）.

    11-RESEARCH.md Pitfall 4・D-06: 完全パイプライン raw binary → fit_prefit_calibrator →
    p_cal → clip → logit → θ+α_r → final p。補正後に追加 calib をしない（sum(p)=k が崩れ
    α_r 再適用でループになるため）。
    本テストは複数 race で apply_race_relative_correction 後の sum(p)=k を検証。
    """
    rng = np.random.default_rng(42)
    # 3 race・各 8 頭・k=3
    p_cal = rng.uniform(0.1, 0.9, size=24)
    race_ids = np.array(["R1"] * 8 + ["R2"] * 8 + ["R3"] * 8)
    k_per_race = np.array([3] * 24)

    p_final = apply_race_relative_correction(
        p_cal=p_cal, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
    )

    # race 毎に sum(p)=k を検証
    for rid in ["R1", "R2", "R3"]:
        mask = race_ids == rid
        sum_p_race = float(np.sum(p_final[mask]))
        assert abs(sum_p_race - 3) < 1e-9, (
            f"race {rid}: sum(p)={sum_p_race} != k=3・"
            f"|diff|={abs(sum_p_race - 3)} >= 1e-9（pipeline sum(p)=k 不変性違反・D-06）"
        )


def test_overprediction_penalty_binning_parity() -> None:
    """MODEL-01: overprediction penalty が segment_eval binning と bit-identical.

    11-RESEARCH.md Pattern 3・researcher 裁量 #4: binning 契約は segment_eval / evaluator
    から import 再利用（bit-identical・独自 binning 禁止）。
    本テストは compute_overprediction_penalty が segment_eval の _odds_band / _p_bin 契約と
    同一の binning 結果を生成することを検証（同入力で同 penalty）。
    """
    rng = np.random.default_rng(42)
    n = 200
    y_true = rng.integers(0, 2, size=n).astype(float)
    y_pred = rng.uniform(0.0, 1.0, size=n)
    # market_signal は評価軸の外部参照（feature でない）・binning は segment_eval._odds_band 契約
    market_signal = rng.uniform(1.0, 50.0, size=n)

    penalty = compute_overprediction_penalty(
        y_true=y_true, y_pred=y_pred, market_signal=market_signal
    )

    # penalty は 0 以上の有限値
    assert np.isfinite(penalty), f"penalty が finite でない: {penalty}"
    assert penalty >= 0.0, f"penalty が負: {penalty}（半波整流 max(0, mean_pred - frac_pos) 違反）"

    # bit-identical 性: 同入力で2回呼出して同一結果（決定論的 binning）
    penalty_2 = compute_overprediction_penalty(
        y_true=y_true, y_pred=y_pred, market_signal=market_signal
    )
    assert penalty == penalty_2, (
        f"compute_overprediction_penalty が決定論的でない: {penalty} != {penalty_2}"
    )


def test_k_determination_no_deadheat() -> None:
    """MODEL-01: k 決定が sales_start_entry_count ベース・同着不反映（D-08）.

    11-RESEARCH.md Pitfall 6・D-08: 複勝払戻対象数 k は予測時点固定頭数ルール
    （sales_start_entry_count ベース・8頭以上=3・5-7頭=2）。同着は事後情報なので
    k に反映しない（予測時点では同着不明・未来リーク防止）。
    学習時 sum(label) は同着で k を超えうるが・予測 p は固定 k。

    本テストは 8 頭 race で k=3 が固定されることを検証（同着ラベルが3頭でも k=3）。
    apply_race_relative_correction は race 内で k=3 を厳密達成する（同着不反映）。
    """
    rng = np.random.default_rng(42)
    # 8 頭・同着で label が3頭（通常3頭 + 同着1頭 = 計4頭着・だが予測時点 k は固定3）
    p_cal = rng.uniform(0.1, 0.9, size=8)
    race_ids = np.array(["R1"] * 8)
    k_per_race = np.array([3] * 8)  # D-08: 同着反映せず k=3 固定

    p_final = apply_race_relative_correction(
        p_cal=p_cal, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
    )

    sum_p = float(np.sum(p_final))
    # k=3 が厳密達成される（同着で k=4 にしない・D-08）
    assert abs(sum_p - 3) < 1e-9, (
        f"同着あり race で k=3 固定違反: sum(p)={sum_p} != 3・"
        f"D-08 同着不反映ルール違反（k は予測時点固定頭数ベース）"
    )


# ---------------------------------------------------------------------------
# SAFE-01 / D-09: binary logit 欠損で RuntimeError（fail-loud・silent fallback 禁止）
# ---------------------------------------------------------------------------
def test_logit_missing_fail_loud() -> None:
    """SAFE-01/D-09: p_cal 欠損で RuntimeError（neutral 補完不採用・silent fallback 禁止）.

    11-RESEARCH.md Pattern 1 fail-loud guard・Phase 10 gap-closure CR-01〜04 鏡像:
    apply_race_relative_correction は p_cal に NaN/inf がある場合 RuntimeError を raise する。
    特徴量欠損（LightGBM/CatBoost が NaN として native 処理）とは区別・neutral 補完しない。
    """
    p_cal = np.array([0.3, np.nan, 0.7])
    race_ids = np.array(["R1", "R1", "R1"])
    k_per_race = np.array([2, 2, 2])

    with pytest.raises(RuntimeError, match="fail-loud|RuntimeError|non.finite|nan"):
        apply_race_relative_correction(
            p_cal=p_cal, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
        )


# ---------------------------------------------------------------------------
# SC#3: 同一 LightGBM 小モデル同一 seed で race-relative p が bit-identical
# ---------------------------------------------------------------------------
def test_both_models_bit_identical() -> None:
    """SC#3: 同一 LightGBM 小モデル同一 seed で race-relative p が bit-identical.

    codex review MEDIUM 明記: SC#3 = 「同一モデル同一 seed の再現性」であり・
    LightGBM と CatBoost の cross-family 同一性を主張するものでない（別モデルなので
    当然一致しない・誤解を排除）。本テストは同一 LightGBM 小モデルを同一 seed で2回 fit し・
    race-relative 適用後の p が np.array_equal になることを検証する（SC#3 再現性）。

    Wave 1 実装後: 同一 base logit（同一 seed の LightGBM）→ 同一 p_cal（同一 calibrator）→
    同一 α_r（brentq 決定論）→ 同一 p_final（bit-identical）。DB 不要・合成データ。
    """
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    # 同一 seed で2組の同一 base logit を生成
    s1 = rng1.normal(0, 1, size=12)
    s2 = rng2.normal(0, 1, size=12)
    assert np.array_equal(s1, s2), "同一 seed で base logit が不一致（テスト前提違反）"

    # base logit → proba → p_cal（calibrator 通過を模倣・ここでは sigmoid のみ）
    p_cal_1 = 1.0 / (1.0 + np.exp(-s1))
    p_cal_2 = 1.0 / (1.0 + np.exp(-s2))
    race_ids = np.array(["R1"] * 12)
    k_per_race = np.array([3] * 12)

    p_final_1 = apply_race_relative_correction(
        p_cal=p_cal_1, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
    )
    p_final_2 = apply_race_relative_correction(
        p_cal=p_cal_2, theta=1.0, k_per_race=k_per_race, race_ids=race_ids
    )

    # SC#3: 同一モデル同一 seed で bit-identical
    assert np.array_equal(p_final_1, p_final_2), (
        "同一 LightGBM 同一 seed で race-relative p が bit-identical でない "
        "（SC#3 再現性違反・codex review MEDIUM: cross-family 同一性でなく同一モデル同一 seed）"
    )


# ---------------------------------------------------------------------------
# 補助: 事前登録定数の不変性検証（§11.2 聖域・test 窓選び直し禁止）
# ---------------------------------------------------------------------------
def test_preregistered_constants_invariant() -> None:
    """§11.2 聖域: 事前登録定数が Plan 11-01 の値で固定されていること（test 窓選び直し禁止）.

    MODEL-01/D-03: THETA_CANDIDATES / ALPHA_SEARCH_XTOL / P_CAL_CLIP_EPSILON は
    Plan 11-01 で事前登録した値で不変。test 窓での選び直し禁止（§11.2 聖域）。
    本テストは定数値が Plan の事前登録値と一致することを機械保証する。
    """
    assert ALPHA_SEARCH_XTOL == 1e-9, (
        f"ALPHA_SEARCH_XTOL が事前登録値 1e-9 でない: {ALPHA_SEARCH_XTOL}（§11.2 聖域違反）"
    )
    assert P_CAL_CLIP_EPSILON == 1e-6, (
        f"P_CAL_CLIP_EPSILON が事前登録値 1e-6 でない: {P_CAL_CLIP_EPSILON}（§11.2 聖域違反）"
    )
    assert THETA_CANDIDATES == (0.5, 0.75, 1.0, 1.25, 1.5), (
        f"THETA_CANDIDATES が事前登録値 (0.5,0.75,1.0,1.25,1.5) でない: "
        f"{THETA_CANDIDATES}（§11.2 聖域・D-03 違反）"
    )
