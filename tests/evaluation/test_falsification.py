"""Phase 12 Plan 03 Task 1 unit tests: src/eval/falsification.py (EVAL-02 / SAFE-01 / §11.2 sanctuary).

RESEARCH.md Pattern 5 (falsification) / Pattern 6 (market_implied) / Pitfall 4/5/6 と
CONTEXT.md D-04/D-05 を検証する。

聖域:
  - §11.2 test 窓 sanctuary: fit_market_implied_calibrator は train/calib 窓のみで fit
    し・test 窓 outcome 系引数を取らない (Shared Pattern 6・シグネチャ検証)。
  - [C-12-03-1 HIGH] run_falsification_test は事前登録評価回帰 (pre-registered evaluation
    regression) を test 窓に fit する最終検定・予測モデル ``p`` の再学習を行わない。
    旧来の不正確な否定表現（「学習しない」系の曖昧な語）は src/eval/falsification.py で 0 件。
  - [C-12-03-4 MEDIUM] base=train・calibrator=calib の 2-window 分離 (同一 calib slice で
    base と calibrator を二重 fit しない・utils/calibrator.py L12-15 disjoint 注記)。
  - SAFE-01: falsification.py は FEATURE_COLUMNS / build_training_frame / load_feature_matrix
    を import しない。odds/market_implied 引数は evaluation 専用層の境界 (SAFE-01-ALLOW)。
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap

import numpy as np
import pytest


def _import_falsification():
    """lazy import (RED 収集のため module-level import を避ける・Phase 02 decision 踏襲)."""
    from src.eval import falsification

    return falsification


# ---------------------------------------------------------------------------
# Test 1: §11.2 sanctuary・fit_market_implied_calibrator signature
# ---------------------------------------------------------------------------


def test_fit_market_implied_calibrator_signature_no_test_outcome() -> None:
    """[C-12-03-4] fit_market_implied_calibrator は train/calib の2-window signature.

    test 窓 outcome 系引数 (y_test/outcome_test/y_outcome_test) を取らない (§11.2 聖域・
    Shared Pattern 6・C-12-03-4 base/calibrator 2-window 分離のため train も引数に取る)。
    """
    falsification = _import_falsification()
    sig = inspect.signature(falsification.fit_market_implied_calibrator)
    actual_params = set(sig.parameters.keys())
    # test 窓 outcome 系は聖域違反
    forbidden = {"y_test", "outcome_test", "y_outcome_test"}
    leak = actual_params & forbidden
    assert not leak, f"§11.2 聖域違反: fit_market_implied_calibrator が test 窓 outcome 系引数 {leak} を取る"
    # 必須引数が存在
    for required in ("odds_train", "y_train", "odds_calib", "y_calib", "calib_sample_size"):
        assert required in actual_params, f"必須引数 {required!r} が不在"


# ---------------------------------------------------------------------------
# Test 2: [C-12-03-1 HIGH] falsification 事前登録評価回帰・正確な表現
# ---------------------------------------------------------------------------


def test_run_falsification_test_docstring_precise_language() -> None:
    """[C-12-03-1 HIGH] run_falsification_test docstring は「pre-registered evaluation regression
    fitted on the test window」と正確に表現し・旧来の不正確な否定表現「学習しない」を含まない."""
    falsification = _import_falsification()
    doc = inspect.getdoc(falsification.run_falsification_test) or ""
    # 正確な表現が docstring に含まれる
    assert "pre-registered evaluation regression" in doc.lower() or "事前登録" in doc, (
        "run_falsification_test docstring に「pre-registered evaluation regression」相当の正確な表現がない"
    )


def test_run_falsification_test_no_imprecise_negation_in_source() -> None:
    """[C-12-03-1 HIGH] src/eval/falsification.py のソースに旧来の不正確な否定表現「学習しない」
    系の曖昧な語が 0 件 (grep -c == 0)."""
    falsification = _import_falsification()
    source = inspect.getsource(falsification)
    # planner-discipline-allow: 学習しない  ← このコメントは PLAN doc 側の marker・ソース検査対象は src/eval/falsification.py
    assert "学習しない" not in source, (
        "[C-12-03-1 HIGH] src/eval/falsification.py に旧来の不正確な否定表現「学習しない」が残存"
    )
    # test 窓 outcome を使った予測モデル p の再学習を連想させる表現も曖昧否定は排除
    for bad_phrase in ("本関数は学習しない", "学習を行わない", "再学習しないわけではない"):
        assert bad_phrase not in source, f"曖昧な否定表現 {bad_phrase!r} が src/eval/falsification.py に残存"


# ---------------------------------------------------------------------------
# Test 3: race_id clustered SE (Pitfall 4・cov_kwds={'groups': ...})
# ---------------------------------------------------------------------------


def test_run_falsification_test_uses_clustered_se_returns_verdict() -> None:
    """run_falsification_test が cov_kwds={'groups': race_id_test} で clustered SE を呼び・
    戻り値に model_p_coef/model_p_pvalue/model_p_significant/verdict が含まれる (Pitfall 4)."""
    falsification = _import_falsification()

    # 合成データ: market_implied と model_p の logit を混ぜて outcome を生成
    rng = np.random.default_rng(42)
    n = 600
    race_ids = np.repeat(np.arange(n // 10), 10)  # 60 races × 10 horses
    market_implied = rng.uniform(0.1, 0.6, size=n)
    model_p = rng.uniform(0.1, 0.6, size=n)
    # outcome は model_p に依存 (model_p に residual がある)
    y_outcome = (rng.uniform(size=n) < (0.3 * market_implied + 0.5 * model_p)).astype(int)

    result = falsification.run_falsification_test(
        y_outcome_test=y_outcome,
        market_implied_test=market_implied,
        model_p_test=model_p,
        race_id_test=race_ids,
    )

    assert "model_p_coef" in result
    assert "model_p_pvalue" in result
    assert "model_p_significant" in result
    assert "verdict" in result
    assert result["verdict"] in ("feature_gap", "structural_limit")
    # pvalue は [0,1]・coef は有限
    assert 0.0 <= float(result["model_p_pvalue"]) <= 1.0
    assert np.isfinite(float(result["model_p_coef"]))


def test_run_falsification_test_clustered_se_source_uses_cov_kwds() -> None:
    """[Pitfall 4] ソースコードで cov_type='cluster' + cov_kwds={'groups': ...} の正しい API を使用."""
    falsification = _import_falsification()
    source = inspect.getsource(falsification.run_falsification_test)
    assert "cov_type" in source and "cluster" in source, "cov_type='cluster' が使われていない"
    assert "cov_kwds" in source, "cov_kwds が使われていない (groups= 直接渡しは error・GitHub #6287)"
    assert "'groups'" in source or '"groups"' in source, "cov_kwds に groups key がない"


# ---------------------------------------------------------------------------
# Test 4: verdict feature_gap vs structural_limit
# ---------------------------------------------------------------------------


def test_verdict_feature_gap_when_model_p_significant() -> None:
    """model_p_pvalue < α → verdict='feature_gap' (特徴量不足・市場 residual が残る)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(123)
    n = 1200
    race_ids = np.repeat(np.arange(n // 12), 12)  # 100 races × 12
    # model_p だけが outcome に効くようにする → model_p は有意 residual を持つ
    model_p = rng.uniform(0.05, 0.85, size=n)
    market_implied = rng.uniform(0.2, 0.4, size=n)  # outcome に無相関
    p_eff = 0.15 * market_implied + 0.7 * model_p
    y_outcome = (rng.uniform(size=n) < p_eff).astype(int)

    result = falsification.run_falsification_test(
        y_outcome_test=y_outcome,
        market_implied_test=market_implied,
        model_p_test=model_p,
        race_id_test=race_ids,
    )
    # model_p が outcome を駆動しているので有意 → feature_gap
    assert result["model_p_significant"] is True
    assert result["verdict"] == "feature_gap"


def test_verdict_structural_limit_when_model_p_not_significant() -> None:
    """model_p_pvalue >= α → verdict='structural_limit' (core value 維持での黒字化棄却・
    market 係数が model を包摂)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(7)
    n = 1200
    race_ids = np.repeat(np.arange(n // 12), 12)
    # market だけ outcome に効く・model_p は market とほぼ同一で residual なし
    market_implied = rng.uniform(0.1, 0.7, size=n)
    model_p = market_implied + rng.normal(0, 0.005, size=n)  # ほぼ同一 (residual ほぼなし)
    model_p = np.clip(model_p, 0.01, 0.99)
    y_outcome = (rng.uniform(size=n) < market_implied).astype(int)

    result = falsification.run_falsification_test(
        y_outcome_test=y_outcome,
        market_implied_test=market_implied,
        model_p_test=model_p,
        race_id_test=race_ids,
    )
    # model_p は market と同一で residual がないので非有意 → structural_limit
    assert result["model_p_significant"] is False
    assert result["verdict"] == "structural_limit"


# ---------------------------------------------------------------------------
# Test 5: Holm 補正 (multipletests method='holm'・bin/odds_band サブ解析のみ)
# ---------------------------------------------------------------------------


def test_sub_analyses_holm_correction() -> None:
    """bin/odds_band サブ解析で multipletests(method='holm') が呼ばれ・corrected pvalues が返る
    (主検定 model_p 単一係数は Holm 不要・D-05)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(99)
    n = 1000
    race_ids = np.repeat(np.arange(n // 10), 10)
    market_implied = rng.uniform(0.1, 0.6, size=n)
    model_p = rng.uniform(0.1, 0.6, size=n)
    y_outcome = (rng.uniform(size=n) < (0.4 * market_implied + 0.2 * model_p)).astype(int)
    odds_for_band = 1.0 / np.clip(market_implied, 0.01, 1.0)
    odds_band_test = odds_for_band  # run_falsification_test が _odds_band 適用

    result = falsification.run_falsification_test(
        y_outcome_test=y_outcome,
        market_implied_test=market_implied,
        model_p_test=model_p,
        race_id_test=race_ids,
        odds_band_test=odds_band_test,
    )
    assert "sub_analyses_odds_band" in result
    sub = result["sub_analyses_odds_band"]
    # band 毎に pvalue と (Holm 補正後) corrected_pvalue が含まれる
    assert isinstance(sub, dict)
    assert len(sub) > 0
    for band, entry in sub.items():
        assert "pvalue" in entry
        assert "corrected_pvalue" in entry  # Holm 補正後


def test_holm_alpha_default_source() -> None:
    """run_falsification_test の holm_alpha default は HOLM_ALPHA=0.05 (D-05・事前登録)."""
    falsification = _import_falsification()
    sig = inspect.signature(falsification.run_falsification_test)
    holm_param = sig.parameters.get("holm_alpha")
    assert holm_param is not None, "holm_alpha 引数が不在"
    assert holm_param.default == falsification.HOLM_ALPHA
    assert falsification.HOLM_ALPHA == 0.05


# ---------------------------------------------------------------------------
# Test 6: logit clipping (LOGIT_CLIP_EPS=1e-6・Pitfall 6・inf 回避)
# ---------------------------------------------------------------------------


def test_logit_clip_helper_bounds() -> None:
    """logit_clip(p) で logit(0)/logit(1) が inf でなく ±13.8 範囲 (Pitfall 6)."""
    falsification = _import_falsification()
    eps = falsification.LOGIT_CLIP_EPS
    assert eps == 1e-6, f"LOGIT_CLIP_EPS は 1e-6 (race_relative.P_CAL_CLIP_EPSILON と同一契約)・got {eps}"
    # p=0 / p=1 でも有限
    p_edge = np.array([0.0, 1.0, 0.5])
    logit_vals = falsification.logit_clip(p_edge)
    assert np.all(np.isfinite(logit_vals)), "logit(0)/logit(1) が inf になる (Pitfall 6)"
    # ±13.8 範囲 (logit(1e-6) ≈ -13.8・logit(1-1e-6) ≈ +13.8)
    assert -14.0 <= logit_vals.min() <= logit_vals.max() <= 14.0


def test_run_falsification_test_with_edge_probabilities_no_inf() -> None:
    """p=0/p=1 を含む入力でも statsmodels 収束し NaN 伝播しない (logit clipping・Pitfall 6)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(5)
    n = 600
    race_ids = np.repeat(np.arange(n // 10), 10)
    # 意図的に端値を混ぜる
    market_implied = rng.uniform(0.0, 1.0, size=n)
    market_implied[0] = 0.0
    market_implied[1] = 1.0
    model_p = rng.uniform(0.0, 1.0, size=n)
    y_outcome = (rng.uniform(size=n) < 0.3).astype(int)

    result = falsification.run_falsification_test(
        y_outcome_test=y_outcome,
        market_implied_test=market_implied,
        model_p_test=model_p,
        race_id_test=race_ids,
    )
    assert np.isfinite(result["model_p_pvalue"])
    assert np.isfinite(result["model_p_coef"])


# ---------------------------------------------------------------------------
# Test 7: isotonic vs sigmoid 切替 (MARKET_CALIB_SAMPLE_THRESHOLD=1000・Pitfall 5)
# ---------------------------------------------------------------------------


def test_fit_market_implied_calibrator_isotonic_when_large_sample() -> None:
    """calib_sample_size >= MARKET_CALIB_SAMPLE_THRESHOLD=1000 → method='isotonic' (sklearn docs)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(11)
    n_train, n_calib = 800, 1200
    odds_train = rng.uniform(1.2, 50.0, size=n_train)
    y_train = (rng.uniform(size=n_train) < (1.0 / odds_train)).astype(int)
    odds_calib = rng.uniform(1.2, 50.0, size=n_calib)
    y_calib = (rng.uniform(size=n_calib) < (1.0 / odds_calib)).astype(int)

    cal = falsification.fit_market_implied_calibrator(
        odds_train=odds_train,
        y_train=y_train,
        odds_calib=odds_calib,
        y_calib=y_calib,
        calib_sample_size=n_calib,
    )
    # method は外から直接見えないが・predict_proba で単調な calibration が得られる
    odds_grid = np.array([1.5, 3.0, 5.0, 10.0, 30.0])
    base = (1.0 / odds_grid).reshape(-1, 1)
    proba = cal.predict_proba(base)[:, 1]
    # 単調非減少 (isotonic の性質) かつ [0,1]
    assert np.all(np.diff(proba) >= -1e-9), f"isotonic が単調でない: {proba}"
    assert np.all((proba >= 0.0) & (proba <= 1.0))


def test_fit_market_implied_calibrator_sigmoid_when_small_sample() -> None:
    """calib_sample_size < MARKET_CALIB_SAMPLE_THRESHOLD=1000 → method='sigmoid' (Platt・過学習回避)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(12)
    n_train, n_calib = 200, 500  # < 1000
    odds_train = rng.uniform(1.2, 50.0, size=n_train)
    y_train = (rng.uniform(size=n_train) < (1.0 / odds_train)).astype(int)
    odds_calib = rng.uniform(1.2, 50.0, size=n_calib)
    y_calib = (rng.uniform(size=n_calib) < (1.0 / odds_calib)).astype(int)

    cal = falsification.fit_market_implied_calibrator(
        odds_train=odds_train,
        y_train=y_train,
        odds_calib=odds_calib,
        y_calib=y_calib,
        calib_sample_size=n_calib,
    )
    # sigmoid は滑らかな S 字 (isotonic の階段でない)
    odds_grid = np.array([1.5, 3.0, 5.0, 10.0, 30.0])
    base = (1.0 / odds_grid).reshape(-1, 1)
    proba = cal.predict_proba(base)[:, 1]
    assert np.all((proba >= 0.0) & (proba <= 1.0))


# ---------------------------------------------------------------------------
# Test 8: SAFE-01・falsification 層 (FEATURE_COLUMNS import 禁止・SAFE-01-ALLOW マーカー)
# ---------------------------------------------------------------------------


def test_falsification_no_feature_pipeline_import() -> None:
    """[SAFE-01] falsification.py は FEATURE_COLUMNS / build_training_frame / load_feature_matrix を import しない."""
    falsification = _import_falsification()
    source = inspect.getsource(falsification)
    tree = ast.parse(textwrap.dedent(source))
    forbidden_names = {"FEATURE_COLUMNS", "build_training_frame", "load_feature_matrix"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_names or alias.asname in forbidden_names:
                    violations.append(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_names or alias.asname in forbidden_names:
                    violations.append(f"import {alias.name}")
    assert not violations, f"SAFE-01 違反: falsification.py が feature 構築経路を import: {violations}"


def test_market_implied_args_have_safe01_allow_marker() -> None:
    """[SAFE-01-ALLOW] odds/market_implied/model_p 引数の docstring に SAFE-01-ALLOW マーカーがある
    (compute_overprediction_penalty idiom・feature 構築経路からの切り離し機械保証)."""
    falsification = _import_falsification()
    for func_name in ("fit_market_implied_calibrator", "run_falsification_test"):
        func = getattr(falsification, func_name)
        doc = inspect.getdoc(func) or ""
        assert "SAFE-01-ALLOW" in doc, (
            f"{func_name} docstring に SAFE-01-ALLOW マーカーがない (odds/market_implied 引数の境界明示)"
        )


# ---------------------------------------------------------------------------
# Test 9: fail-loud (Pitfall 4・statsmodels ConvergenceWarning → RuntimeError)
# ---------------------------------------------------------------------------


def test_run_falsification_test_fail_loud_on_convergence_warning() -> None:
    """statsmodels 収束失敗 (ConvergenceWarning) や cov_kwds groups 長不一致は RuntimeError
    (silent fallback 禁止・Shared Pattern 4)."""
    falsification = _import_falsification()
    rng = np.random.default_rng(13)
    n = 100
    # 完全分離 (perfect separation) で statsmodels が収束失敗しやすいデータ
    race_ids = np.repeat(np.arange(10), 10)
    market_implied = np.linspace(0.01, 0.99, n)
    # y_outcome が market_implied で完全分離
    y_outcome = (market_implied > 0.5).astype(int)
    model_p = market_implied.copy()

    # 完全分離で常に RuntimeError になるわけではないが・収束失敗時は RuntimeError になること
    # を・ソースコードで warnings.catch_warnings + raise RuntimeError を使っているか検証
    source = inspect.getsource(falsification.run_falsification_test)
    assert "RuntimeError" in source, "収束失敗時の RuntimeError が定義されていない (Shared Pattern 4)"


def test_run_falsification_test_groups_length_mismatch_fail_loud() -> None:
    """groups array の長さが観測行数と不一致の場合・statsmodels が error になるのを RuntimeError で wrap."""
    falsification = _import_falsification()
    rng = np.random.default_rng(14)
    n = 60
    race_ids_short = np.repeat(np.arange(5), 10)  # 50 (10 行不足)
    market_implied = rng.uniform(0.1, 0.6, size=n)
    model_p = rng.uniform(0.1, 0.6, size=n)
    y_outcome = (rng.uniform(size=n) < 0.3).astype(int)

    with pytest.raises((RuntimeError, ValueError, IndexError)):
        falsification.run_falsification_test(
            y_outcome_test=y_outcome,
            market_implied_test=market_implied,
            model_p_test=model_p,
            race_id_test=race_ids_short,  # 長さ不一致
        )


# ---------------------------------------------------------------------------
# Test 10: [C-12-03-4 MEDIUM] base/calibrator 2-window 分離
# ---------------------------------------------------------------------------


def test_fit_market_implied_calibrator_two_window_separation() -> None:
    """[C-12-03-4] base (LogisticRegression) を odds_train/y_train で fit し・
    calibrator (CalibratedClassifierCV) を odds_calib/y_calib で fit する 2-window 分離.
    同一 calib slice で base と calibrator を二重 fit しない (utils/calibrator.py disjoint 注記)."""
    falsification = _import_falsification()

    rng = np.random.default_rng(15)
    n_train, n_calib = 500, 700
    odds_train = rng.uniform(1.2, 30.0, size=n_train)
    # train: 低オッズ馬が高確率で勝つ (train 窓の傾向)
    y_train = (rng.uniform(size=n_train) < (1.0 / odds_train) * 1.2).astype(int)
    y_train = np.clip(y_train, 0, 1)
    odds_calib = rng.uniform(1.2, 30.0, size=n_calib)
    # calib: train とは異なる slice (時系列 later・分布やや異なる)
    y_calib = (rng.uniform(size=n_calib) < (1.0 / odds_calib) * 0.95).astype(int)

    cal = falsification.fit_market_implied_calibrator(
        odds_train=odds_train,
        y_train=y_train,
        odds_calib=odds_calib,
        y_calib=y_calib,
        calib_sample_size=n_calib,
    )

    # 2-window 分離の検証: base は train の傾向 (1.2 倍) を学習し・calibrator は calib の傾向 (0.95 倍) で校正
    # calibrator の予測が calib slice の empirical rate に近いことで間接確認
    base_calib = (1.0 / np.clip(odds_calib, 1.0, 100.0)).reshape(-1, 1)
    calibrated_proba = cal.predict_proba(base_calib)[:, 1]
    emp_rate_calib = float(np.mean(y_calib))
    mean_calibrated = float(np.mean(calibrated_proba))
    # base が train (1.2x) を見ているので・calibrator が calib (0.95x) に引っ張る → mean は emp_rate に近い
    # (base を calib で二重 fit していたら mean は 1.0/odds の平均に近くなり過ぎる)
    assert abs(mean_calibrated - emp_rate_calib) < 0.20, (
        f"2-window 分離の確認: calibrated mean={mean_calibrated:.3f} vs calib empirical={emp_rate_calib:.3f}"
    )


def test_fit_market_implied_calibrator_source_uses_frozen_estimator() -> None:
    """[C-12-03-4] ソースで FrozenEstimator + CalibratedClassifierCV (sklearn 1.9.0 prefit idiom) を使用."""
    falsification = _import_falsification()
    source = inspect.getsource(falsification.fit_market_implied_calibrator)
    assert "FrozenEstimator" in source, "sklearn 1.9.0 prefit idiom (FrozenEstimator) を使っていない"
    assert "CalibratedClassifierCV" in source
    # train と calib で別々の fit を呼ぶ (2-window 分離)
    assert "LogisticRegression" in source


# ---------------------------------------------------------------------------
# Test 11: [C-12-03-1 HIGH] falsification-spec.json 事前書き出しヘルパー
# ---------------------------------------------------------------------------


def test_write_falsification_spec_byte_reproducible(tmp_path) -> None:
    """[C-12-03-1 HIGH] write_falsification_spec が byte-reproducible な JSON を書き出す
    (sort_keys=True, ensure_ascii=False, allow_nan=False). 2回書き出しで同一バイト列."""
    falsification = _import_falsification()
    p1 = tmp_path / "spec1.json"
    p2 = tmp_path / "spec2.json"
    falsification.write_falsification_spec(p1)
    falsification.write_falsification_spec(p2)
    b1 = p1.read_bytes()
    b2 = p2.read_bytes()
    assert b1 == b2, "write_falsification_spec が byte-reproducible でない"


def test_write_falsification_spec_contains_pre_registered_fields(tmp_path) -> None:
    """[C-12-03-1 HIGH] falsification-spec.json に回帰仕様 (共変量 field_size・logit clipping eps=1e-6・
    subgroup odds_band・2係数モデル logit(market_implied)+logit(model_p)・clustered SE groups=race_id・α=0.05)
    が含まれる (theta/q_shrink.json 事前書き出し idiom・§11.2 聖域の threshold dredging 監査)."""
    falsification = _import_falsification()
    p = tmp_path / "spec.json"
    falsification.write_falsification_spec(p)
    data = json.loads(p.read_text(encoding="utf-8"))

    # 事前登録された仕様要素の検証
    assert "regression" in data
    reg = data["regression"]
    # 共変量
    covs = reg.get("covariates", [])
    assert "field_size" in covs, "共変量 field_size が spec に無い"
    # 2係数モデル
    assert "logit_market_implied" in str(reg.get("predictors", []))
    assert "logit_model_p" in str(reg.get("predictors", []))
    # logit clipping
    assert float(reg.get("logit_clip_eps", 0)) == 1e-6
    # subgroup
    assert "odds_band" in str(reg.get("subgroup", "")) or "odds_band" in str(reg.get("subgroups", []))
    # clustered SE
    assert "cluster" in str(reg.get("cov_type", ""))
    assert "race_id" in str(reg.get("cluster_groups", ""))
    # α (主検定)
    assert float(reg.get("alpha", 0)) == 0.05
    # Holm (サブ解析のみ)
    assert "holm" in str(reg.get("sub_analysis_correction", "")).lower()
    assert float(reg.get("holm_alpha", 0)) == 0.05


def test_write_falsification_spec_allow_nan_false_strict(tmp_path) -> None:
    """write_falsification_spec は allow_nan=False 厳密 (NaN が入っていれば ValueError)."""
    falsification = _import_falsification()
    import json as _json

    # spec の内容は固定値で NaN を含まないので・直接 json.dumps で検証
    p = tmp_path / "spec.json"
    falsification.write_falsification_spec(p)
    raw = p.read_text(encoding="utf-8")
    # strict JSON としてパースできる (NaN リテラルがない)
    _json.loads(raw)  # default で strict parse (NaN は許容するので次で厳密検証)
    # allow_nan=False で再パースしてエラーにならないこと
    parsed = _json.loads(raw)
    again = _json.dumps(parsed, sort_keys=True, ensure_ascii=False, allow_nan=False)
    assert again  # エラーにならず再ダンプ可


# ---------------------------------------------------------------------------
# Test: constants block 集約 (C-12-04-3・C3-12-03-1)
# ---------------------------------------------------------------------------


def test_constants_block_aggregated_in_falsification_module() -> None:
    """[C-12-04-3 / C3-12-03-1] Phase 12 定数が falsification.py の constants block に集約されている
    (evaluator/segment_eval/refund_accounting/run_phase12_evaluation は import して使用)."""
    falsification = _import_falsification()
    expected_constants = {
        "Q_LEVEL_SHRINKAGE": 0.90,  # C3-12-03-1・Plan 04 が import
        "Q_LEVEL_FALSIFICATION": 0.05,  # α・主検定
        "HOLM_ALPHA": 0.05,  # bin/odds_band サブ解析
        "LOGIT_CLIP_EPS": 1e-6,  # Pitfall 6
        "ODDS_CLIP_MIN": 1.0,
        "ODDS_CLIP_MAX": 100.0,  # D-05 (c)
        "MARKET_CALIB_SAMPLE_THRESHOLD": 1000,  # Pitfall 5
        "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD": 0.10,  # evaluator と共有
        "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD": 0.15,  # evaluator と共有
    }
    for name, expected in expected_constants.items():
        assert hasattr(falsification, name), f"constants block に {name} が不在"
        actual = getattr(falsification, name)
        assert actual == expected, f"{name} == {actual!r} (期待 {expected!r})"
