"""Phase 9 SC#6 stop gate 合成データ E2E smoke テスト + binning 契約固定再利用確認.

DB 不要 (KEIBA_SKIP_DB_TESTS=1 で実行可)。スクリプトの module-level 純粋ヘルパー関数を直接
import して合成データで検証する。

検証対象:
  - evaluator/segment_eval の binning 定数を import 再利用し・再定義していない (§15.2 不変)
  - REVIEW H2/H7/H8: スクリプトが orchestrator.train_and_predict を使用し・生 trainer を直接呼ばない
  - REVIEW H-new: スクリプトの全 train_and_predict Call ノードが snapshot_id= keyword を持つ
  - REVIEW H6: market_implied が fuku_odds_lower から算出 (fukuodds でない)
  - REVIEW M4: _sanitize_for_json が NaN/Inf を処理し json が RFC 8259 strict
  - D-16 両シナリオ (構造的限界寄り / 有効性シグナルあり) のフラグが正しく立つ

cross-reference: scripts/run_speed_figure_stopgate.py
                 .planning/phases/09-speed-figure-foundation/09-05-PLAN.md Task 2
"""

from __future__ import annotations

import ast
import inspect
import json
import math

import numpy as np
import pandas as pd
import pytest

from scripts.run_speed_figure_stopgate import (
    VERDICT_EFFECTIVE_SIGNAL,
    VERDICT_STRUCTURAL_LIMIT,
    _compute_global_metric_delta,
    _compute_residual_proxy,
    _compute_selected_calibration,
    _compute_selected_roi,
    _decide_stopgate_verdict,
    _sanitize_for_json,
)
from src.model.predict import make_model_version


# ---------------------------------------------------------------------------
# テスト用 fixture: 合成予測 DataFrame
# ---------------------------------------------------------------------------


def _make_synthetic_pred(
    *,
    n: int = 500,
    p_bias: float = 0.0,
    odds_seed: int = 42,
    hit_seed: int = 7,
) -> pd.DataFrame:
    """合成予測 DataFrame を生成するヘルパー.

    ``p_bias`` > 0 で p を全体的に高く (過大予測) する。投票層 (odds>=4.9 かつ p∈[0.15,0.20])
    に十分なサンプルが入るように odds と p を分散させる。
    """
    rng = np.random.default_rng(odds_seed)
    # fuku_odds_lower: 1.0〜20.0 の一様分布
    odds_lower = 1.0 + rng.uniform(0.0, 19.0, size=n)
    # p_fukusho_hit: odds に反比例するベース + ノイズ + bias
    base_p = np.clip(0.9 / odds_lower + rng.normal(0.0, 0.05, size=n) + p_bias, 0.01, 0.95)
    # 実際の的中: odds に反比例 (現実的)
    rng_y = np.random.default_rng(hit_seed)
    true_p = np.clip(0.9 / odds_lower, 0.01, 0.95)
    y = (rng_y.uniform(0.0, 1.0, size=n) < true_p).astype(int)
    # race_key: n を 14 で割った商だけレースを作り・余りは最後のレースに追加 (長さを n に揃える)
    n_full_races = n // 14
    remainder = n % 14
    race_keys_list = [np.full(14, r) for r in range(n_full_races)]
    if remainder > 0:
        race_keys_list.append(np.full(remainder, n_full_races))
    race_keys = np.concatenate(race_keys_list) if race_keys_list else np.zeros(n, dtype=int)
    return pd.DataFrame(
        {
            "p_fukusho_hit": base_p,
            "fuku_odds_lower": odds_lower,
            "fuku_odds_upper": odds_lower + 0.5,
            "fukusho_hit_validated": y,
            "race_key": race_keys,
            "entry_count": np.full(n, 14),
        }
    )


# ---------------------------------------------------------------------------
# (a) binning 契約固定再利用確認 (§15.2 不変)
# ---------------------------------------------------------------------------


def test_binning_constants_imported_not_redefined() -> None:
    """スクリプトが evaluator/segment_eval の binning 定数を import 再利用し・再定義していないことを
    AST で証明する (§15.2 事前登録指標不変・T-09-17 mitigate)."""
    import scripts.run_speed_figure_stopgate as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)

    # import 文で CALIBRATION_CURVE_BINS / ODDS_BAND_EDGES が import されているか
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
    assert "CALIBRATION_CURVE_BINS" in imported_names, (
        "CALIBRATION_CURVE_BINS が import されていない (§15.2 不変違反)"
    )
    assert "ODDS_BAND_EDGES" in imported_names, (
        "ODDS_BAND_EDGES が import されていない (§15.2 不変違反)"
    )

    # ast.Assign の target にこれらの名前が含まれていないか (再定義禁止)
    forbidden_targets = {
        "CALIBRATION_CURVE_BINS",
        "CALIBRATION_CURVE_MIN_BIN_COUNT",
        "ODDS_BAND_EDGES",
        "NINKI_BAND_EDGES",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in forbidden_targets:
                    pytest.fail(
                        f"binning 定数 {tgt.id} がスクリプト内で再代入されている (§15.2 不変違反・T-09-17)"
                    )


# ---------------------------------------------------------------------------
# (b)(c) D-16 verdict 両シナリオ
# ---------------------------------------------------------------------------


def test_d16_structural_limit_flag() -> None:
    """D-16: 両方 (selected calibration 改善・residual proxy シグナル) が改善しない場合
    「構造的限界寄り」フラグが立つ."""
    verdict = _decide_stopgate_verdict(
        selected_calibration_improved=False,
        residual_proxy_signal=False,
    )
    assert verdict == VERDICT_STRUCTURAL_LIMIT
    assert "構造的限界寄り" in verdict


def test_d16_effective_signal_flag() -> None:
    """D-16 対称: 片方でも改善があれば「Phase 10 進行候補」フラグが立つ."""
    # selected calibration 改善のみ
    v1 = _decide_stopgate_verdict(
        selected_calibration_improved=True,
        residual_proxy_signal=False,
    )
    assert v1 == VERDICT_EFFECTIVE_SIGNAL
    # residual proxy シグナルのみ
    v2 = _decide_stopgate_verdict(
        selected_calibration_improved=False,
        residual_proxy_signal=True,
    )
    assert v2 == VERDICT_EFFECTIVE_SIGNAL
    # 両方
    v3 = _decide_stopgate_verdict(
        selected_calibration_improved=True,
        residual_proxy_signal=True,
    )
    assert v3 == VERDICT_EFFECTIVE_SIGNAL


# ---------------------------------------------------------------------------
# (d) make_model_version Phase 9 形式
# ---------------------------------------------------------------------------


def test_make_model_version_phase9_format() -> None:
    """make_model_version が Phase 9 形式 {snapshot_id}-lgb-v1 を返す (review HIGH#4・二重 postfix 回避)."""
    mv = make_model_version("20260625-1a-speedfigure-v1", "lightgbm", 1)
    assert mv == "20260625-1a-speedfigure-v1-lgb-v1", f"想定外の model_version: {mv}"
    # catboost 形式も確認
    mv_cb = make_model_version("20260625-1a-speedfigure-v1", "catboost", 1)
    assert mv_cb == "20260625-1a-speedfigure-v1-cb-v1"


# ---------------------------------------------------------------------------
# (e) REVIEW H6: market_implied 診断層のみ + 正しい odds 列名
# ---------------------------------------------------------------------------


def test_market_implied_diagnostic_only_and_correct_column() -> None:
    """SAFE-01 + REVIEW H6: market_implied が fuku_odds_lower から算出され・診断層のみで使用される.

    FEATURE_COLUMNS に market 系カラムが混入しないことは・スクリプトの import 文に
    FEATURE_COLUMNS が無いこと・および _compute_residual_proxy が market_implied を
    ローカル変数 (_market_implied) として扱うことで確認する。
    """
    import scripts.run_speed_figure_stopgate as mod

    source = inspect.getsource(mod)

    # REVIEW H6: fuku_odds_lower が使用されている (正しい列名)
    assert "fuku_odds_lower" in source, "fuku_odds_lower が使用されていない (REVIEW H6 違反)"

    # REVIEW H6: 誤略称 fukuodds (word boundary) が使用されていない
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "fukuodds":
            pytest.fail("誤 odds 列名 'fukuodds' がコードで参照されている (REVIEW H6 違反)")
        if isinstance(node, ast.Attribute) and node.attr == "fukuodds":
            pytest.fail("誤 odds 列名 'fukuodds' が属性参照されている (REVIEW H6 違反)")

    # SAFE-01: FEATURE_COLUMNS を import していない (market 系を feature に入れない)
    # ※ FEATURE_COLUMNS は src.model.data にあるが・stop gate スクリプトは FEATURES を
    # 選択する役目を持たず (orchestrator の make_X_y が snapshot_id で選択)・
    # market_implied を FEATURE_COLUMNS に混入する経路は構造的に存在しない。
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "FEATURE_COLUMNS", (
                    "FEATURE_COLUMNS を直接 import している (market 混入リスク・SAFE-01)"
                )

    # _compute_residual_proxy が market_implied をローカル変数 (_market_implied) で扱う
    residual_src = inspect.getsource(_compute_residual_proxy)
    assert "_market_implied" in residual_src, (
        "_compute_residual_proxy が market_implied をローカル変数で扱っていない (SAFE-01)"
    )

    # 機能証明: 合成データで _compute_residual_proxy が動作する
    df = _make_synthetic_pred()
    result = _compute_residual_proxy(df)
    assert "signal_present" in result
    assert "n_valid_cells" in result
    assert isinstance(result["signal_present"], bool)


# ---------------------------------------------------------------------------
# (f) REVIEW M4: JSON sanitizer + RFC 8259 strict
# ---------------------------------------------------------------------------


def test_json_output_strict_with_sanitizer() -> None:
    """REVIEW M4: _sanitize_for_json が NaN/Inf を処理し・json が allow_nan=False で成功する.

    sanitizer を通さずに NaN を含む dict を allow_nan=False で dumps すると ValueError に
    なることも assert し・sanitizer の必要性を証明する (RFC 8259 strict).
    """
    # NaN/Inf を含む結果 dict (single-class AUC 等で発生しうる)
    raw = {
        "brier": 0.15,
        "auc": float("nan"),  # single-class で発生
        "roi": float("inf"),  # stake=0 等
        "delta": float("-inf"),
        "nested": {"x": float("nan"), "y": 1.0},
        "lst": [float("nan"), 2.0],
    }

    # sanitizer 無し: allow_nan=False で ValueError
    with pytest.raises(ValueError):
        json.dumps(raw, allow_nan=False)

    # sanitizer 適用後: allow_nan=False で成功
    sanitized = _sanitize_for_json(raw)
    text = json.dumps(sanitized, sort_keys=True, ensure_ascii=False, allow_nan=False)
    assert "NaN" not in text  # Python の NaN リテラルが混入しない
    parsed = json.loads(text)
    assert parsed["auc"] is None  # NaN → None
    assert parsed["roi"] == "Infinity"
    assert parsed["delta"] == "-Infinity"
    assert parsed["nested"]["x"] is None
    assert parsed["lst"][0] is None

    # 正常 float は維持される
    assert parsed["brier"] == 0.15
    assert parsed["nested"]["y"] == 1.0
    assert parsed["lst"][1] == 2.0


# ---------------------------------------------------------------------------
# (g) REVIEW H2/H7/H8: orchestrator.train_and_predict 経由・生 trainer 直接呼出禁止
# ---------------------------------------------------------------------------


def test_orchestrator_path_not_raw_trainer() -> None:
    """REVIEW H2/H7/H8: スクリプトが orchestrator.train_and_predict を使用し・
    生 trainer (train_lightgbm/train_catboost/align_predictions/_prepare_catboost_pool) を
    Call ノードとして直接呼ばないことを AST で証明する."""
    import scripts.run_speed_figure_stopgate as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)

    # orchestrator.train_and_predict の import が存在するか
    found_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "orchestrator" in node.module:
                for alias in node.names:
                    if alias.name == "train_and_predict":
                        found_import = True
    assert found_import, "orchestrator.train_and_predict が import されていない (REVIEW H2/H7/H8)"

    # train_and_predict の呼出 (ast.Name Call) が存在するか
    found_call = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "train_and_predict"
        ):
            found_call = True
            break
    assert found_call, "train_and_predict が呼出されていない (REVIEW H2/H7/H8)"

    # 生 trainer API の直接呼出 (Call ノード) が存在しないことを検証
    # ※ docstring 内の文字列表現は Call ノードにならないため false positive なし
    forbidden_call_names = {
        "train_lightgbm",
        "train_catboost",
        "align_predictions",
        "_prepare_catboost_pool",
        "_prepare_lightgbm_train_eval",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_call_names, (
                f"生 trainer {node.func.id} が直接呼ばれている "
                f"(REVIEW H2/H7/H8 違反・orchestrator.train_and_predict 経由でなければならない)"
            )


# ---------------------------------------------------------------------------
# (h) REVIEW H-new (Cycle 3): 全 train_and_predict Call が snapshot_id= keyword を持つ
# ---------------------------------------------------------------------------


def test_train_and_predict_calls_pass_snapshot_id() -> None:
    """REVIEW H-new (Cycle 3・P05 caller gap): スクリプトの全 train_and_predict( Call ノードが
    snapshot_id= keyword を持つことを AST で証明する.

    省略すると orchestrator 内部の make_X_y(test_df, snapshot_id=None) で v1.0 FEATURE_COLUMNS
    が選択され・stop gate が「v1.0 vs v1.0」を比較する (H1-b と同じ静かな失敗・SC#6 完全無意味化).

    bad fixture で false-pass でないことも証明する (guard が違反を検出できることの確認).
    """
    import scripts.run_speed_figure_stopgate as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)

    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "train_and_predict"
    ]
    assert len(calls) >= 1, (
        "train_and_predict の呼出が存在しない (stop gate が実装されていないか・シグネチャ変更が必要)"
    )
    for i, c in enumerate(calls):
        kw_names = [kw.arg for kw in c.keywords]
        assert "snapshot_id" in kw_names, (
            f"train_and_predict 呼出 #{i} が snapshot_id= keyword を持たない "
            f"(REVIEW H-new・silent-failure・SC#6 無意味化・keywords={kw_names})"
        )

    # bad fixture: snapshot_id= keyword を持たない呼出を意図的に混ぜたソースで guard が FAIL することを証明
    bad_source = """
import ast
def f():
    train_and_predict(df, model_type='lightgbm')  # snapshot_id 省略 → bad
"""
    bad_tree = ast.parse(bad_source)
    bad_calls = [
        n
        for n in ast.walk(bad_tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "train_and_predict"
    ]
    bad_missing = [
        i for i, c in enumerate(bad_calls)
        if not any(kw.arg == "snapshot_id" for kw in c.keywords)
    ]
    assert len(bad_missing) == 1, (
        "bad fixture で guard が違反を検出できない (false-pass・guard が壊れている)"
    )


# ---------------------------------------------------------------------------
# 補助テスト: D-14 指標算出ヘルパーの smoke (合成データ)
# ---------------------------------------------------------------------------


def test_d14_metric_helpers_smoke() -> None:
    """D-14 指標算出ヘルパー (_compute_selected_calibration / _compute_selected_roi /
    _compute_global_metric_delta) が合成データで動作する smoke テスト (E2E 補完)."""
    baseline_pred = _make_synthetic_pred(p_bias=0.05, odds_seed=1, hit_seed=1)
    speedfig_pred = _make_synthetic_pred(p_bias=-0.02, odds_seed=2, hit_seed=2)

    # 指標1: selected calibration
    base_calib = _compute_selected_calibration(baseline_pred)
    spd_calib = _compute_selected_calibration(speedfig_pred)
    assert not math.isnan(base_calib) or not math.isnan(spd_calib), (
        "selected calibration が両方とも NaN (合成データ不備の可能性)"
    )

    # 指標2: selected ROI
    base_roi = _compute_selected_roi(baseline_pred)
    spd_roi = _compute_selected_roi(speedfig_pred)
    assert "roi" in base_roi and "roi" in spd_roi
    assert "n_selected" in base_roi and "n_selected" in spd_roi

    # 指標3: global metric delta (簡易 metrics dict)
    baseline_metrics = {"brier": 0.15222, "logloss": 0.47488, "auc": 0.73230}
    speedfig_metrics = {"brier": 0.15300, "logloss": 0.48000, "auc": 0.73000}
    delta = _compute_global_metric_delta(baseline_metrics, speedfig_metrics)
    assert delta["brier_delta"] == pytest.approx(0.00078, abs=1e-5)
    assert delta["logloss_delta"] == pytest.approx(0.00512, abs=1e-5)
    assert delta["auc_delta"] == pytest.approx(-0.00230, abs=1e-5)
    # 許容幅内 (Brier +0.005 / LogLoss +0.02 / AUC -0.005)
    assert delta["non_degraded"] is True

    # 許容幅外のケース
    worst_metrics = {"brier": 0.17000, "logloss": 0.50000, "auc": 0.70000}
    delta2 = _compute_global_metric_delta(baseline_metrics, worst_metrics)
    assert delta2["non_degraded"] is False
