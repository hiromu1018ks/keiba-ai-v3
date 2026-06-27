# ruff: noqa: E501
"""Phase 12 EVAL-02 falsification test + market_implied 再校正 (D-04/D-05・§11.2 sanctuary).

本モジュールは Phase 12 の評価・診断専用層であり・以下を提供する:

1. :func:`run_falsification_test` — **事前登録評価回帰 (pre-registered evaluation regression)
   を test 窓に fit する最終検定**。``logit(outcome) ~ logit(market_implied) + logit(model_p)``
   のロジット回帰を :mod:`statsmodels` で race_id clustered SE で fit し・model_p 係数の
   有意性を α=0.05 で検定する (D-05・EVAL-02)。bin/odds_band サブ解析では Holm 補正
   (multipletests method='holm') を適用する (主検定 model_p 単一係数は Holm 不要・D-05)。

2. :func:`fit_market_implied_calibrator` — train/calib 窓で ``1/odds`` を outcome に
   :class:`sklearn.calibration.CalibratedClassifierCV` で calibration し・overround・FLB・
   複勝プール歪みを除去した「真の市場暗示確率」を構築する (D-04)。model_p 係数が「市場に
   ない純粋な residual」を測るための前処理。

3. :func:`write_falsification_spec` — 回帰仕様 (共変量・logit clipping・subgroup・2係数モデル・
   clustered SE・α) を ``reports/12-evaluation/falsification-spec.json`` として byte-reproducible
   に書き出すヘルパー (theta/q_shrink.json 事前書き出し idiom・§11.2 聖域の threshold dredging
   監査)。**実際の書き出し実行は Plan 04 run_phase12_evaluation.py が行う** (test 窓評価前)。

聖域 (CONTEXT.md / 12-CONTEXT.md / 12-RESEARCH.md):
  - **§11.2 test 窓 sanctuary**: :func:`fit_market_implied_calibrator` は train/calib 窓のみで
    fit し・test 窓 outcome 系引数 (``y_test`` / ``outcome_test`` / ``y_outcome_test``) を
    取らない (Shared Pattern 6・シグネチャ検証)。:func:`run_falsification_test` は test 窓 の
    予測のみで評価する最終検定 (予測モデル ``p`` の再学習は行わない)。
  - **[C-12-03-4 MEDIUM] base/calibrator 2-window 分離**: base (LogisticRegression) を
    ``odds_train``/``y_train`` で fit し・calibrator (CalibratedClassifierCV) を
    ``odds_calib``/``y_calib`` で fit する。同一 calib slice で base と calibrator を二重 fit
    しない (:mod:`src.utils.calibrator` の disjoint data 注記・Pitfall 5 過学習リスク低減)。
  - **[C-12-03-1 HIGH] 事前登録評価回帰**: ``run_falsification_test`` の docstring は
    「事前登録された評価回帰仕様を test 窓に fit する最終検定」と正確に表現する。回帰仕様
    (共変量 field_size・logit clipping eps・subgroup odds_band・2係数モデル・clustered SE
    groups=race_id・α=0.05) は test 評価後に変更する経路を持たない (threshold dredging 監査)。
  - **SAFE-01**: 本モジュールは ``FEATURE_COLUMNS`` / ``build_training_frame`` /
    ``load_feature_matrix`` 等 feature 構築経路を import しない。``odds`` / ``market_implied``
    / ``model_p`` 引数は evaluation 専用層の境界 (SAFE-01-ALLOW マーカー・
    :func:`src.model.race_relative.compute_overprediction_penalty` と同一 idiom)。

参照:
  - 12-RESEARCH.md Pattern 5 (falsification L386-447) / Pattern 6 (market_implied L449-496)
  - 12-RESEARCH.md Pitfall 4 (cov_kwds API) / Pitfall 5 (isotonic 1000 rule) / Pitfall 6 (logit clip)
  - 12-PATTERNS.md falsification.py Pattern (L599-654)
  - src/utils/calibrator.py (FrozenEstimator + CalibratedClassifierCV idiom)
  - src/model/segment_eval.py (ODDS_BAND_EDGES / _odds_band import・bit-identical binning)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from statsmodels.stats.multitest import multipletests

# binning 契約の import 再利用 (codex review HIGH#2・bit-identical・独自 binning 禁止)。
from src.model.segment_eval import ODDS_BAND_EDGES, ODDS_BAND_LABELS, _odds_band

# ---------------------------------------------------------------------------
# [C-12-04-3 / C3-12-03-1] Phase 12 事前登録定数 (本モジュールに集約)
# ---------------------------------------------------------------------------
# §11.2 聖域・test 窓で変更不可・事前登録パターン Phase 10 D-12 / 11 D-03 踏襲。
# evaluator.py / segment_eval.py / refund_accounting.py / scripts/run_phase12_evaluation.py
# (Plan 04) は本 constants block から import して使用する (重複定義回避・閾値 drift 防止・§19.1)。

# q_shrink 用下側信頼水準 (D-02・§11.2 聖域・Plan 01 compute_p_lower_conformal_shrinkage が消費・
# Plan 04 run_phase12_evaluation.py が import)。C3-12-03-1 で Plan 03 constants block に追加。
Q_LEVEL_SHRINKAGE: float = 0.90

# falsification α (D-05・主検定 model_p 単一係数)。
Q_LEVEL_FALSIFICATION: float = 0.05

# bin/odds_band サブ解析の Holm 補正 α (D-05・FWER 制御)。
HOLM_ALPHA: float = 0.05

# logit clipping eps (Pitfall 6・race_relative.P_CAL_CLIP_EPSILON と同一契約・inf 回避)。
LOGIT_CLIP_EPS: float = 1e-6

# odds clipping 範囲 (D-05 (c)・planner 事前登録・JRA 複勝オッズ典型範囲)。
ODDS_CLIP_MIN: float = 1.0
ODDS_CLIP_MAX: float = 100.0

# isotonic vs sigmoid 切替閾値 (Pitfall 5・sklearn docs・calib sample size ≥ 1000 で isotonic)。
MARKET_CALIB_SAMPLE_THRESHOLD: int = 1000

# Phase 12 SC#4 WARN gate 閾値 (evaluator と共有・D-06・投票層過大予測の許容幅)。
PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD: float = 0.10
PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD: float = 0.15


def logit_clip(p: np.ndarray, eps: float = LOGIT_CLIP_EPS) -> np.ndarray:
    """logit 変換を inf 回避付きで行う (Pitfall 6・race_relative.P_CAL_CLIP_EPSILON と同一契約).

    ``np.clip(p, eps, 1-eps)`` してから ``log(p/(1-p))`` を計算する。``p=0`` / ``p=1`` でも
    ``±13.8`` 範囲 (``logit(1e-6) ≈ -13.815``) に収まる。statsmodels Logit 収束の NaN 伝播を防ぐ。

    Parameters
    ----------
    p : np.ndarray
        確率配列・[0, 1] 区間。
    eps : float
        clipping 端値 (既定 ``LOGIT_CLIP_EPS=1e-6``)。

    Returns
    -------
    np.ndarray
        ``logit(p)`` 配列 (有限・inf なし)。
    """
    p_arr = np.asarray(p, dtype=float)
    p_clipped = np.clip(p_arr, eps, 1.0 - eps)
    return np.log(p_clipped / (1.0 - p_clipped))


# ---------------------------------------------------------------------------
# market_implied 再校正 (D-04・train/calib 窓のみ・§11.2 sanctuary・C-12-03-4 2-window 分離)
# ---------------------------------------------------------------------------


def fit_market_implied_calibrator(
    odds_train: np.ndarray,
    y_train: np.ndarray,
    odds_calib: np.ndarray,
    y_calib: np.ndarray,
    *,
    calib_sample_size: int,
) -> CalibratedClassifierCV:
    """train/calib 窓で ``1/odds`` を outcome に calibration し・真の市場暗示確率を構築する (D-04).

    ``1/odds`` には overround (控除率)・FLB (favorite-longshot bias)・複勝プール歪みが混入するため・
    これを :class:`CalibratedClassifierCV` で calibration して「真の市場暗示確率」を得る。
    これにより :func:`run_falsification_test` の ``model_p`` 係数が「市場にない純粋な residual」
    を測るようになる (D-04)。falsification は train/calib 窓で設計し・test 窓は適用のみ (§11.2 聖域)。

    **SAFE-01-ALLOW: odds / market_implied**
        本関数は ``odds_train`` / ``odds_calib`` 引数 (市場情報系外部参照) を受け取る。
        evaluation 専用層の境界であり・``FEATURE_COLUMNS`` / ``build_training_frame`` /
        ``load_feature_matrix`` 等 feature 構築経路から切り離されている (SAFE-01)。

    **[C-12-03-4 MEDIUM] base/calibrator 2-window 分離:**
        base (LogisticRegression) を ``odds_train``/``y_train`` で fit し・calibrator
        (CalibratedClassifierCV) を ``odds_calib``/``y_calib`` で fit する。同一 calib slice で
        base と calibrator を二重 fit しない (:mod:`src.utils.calibrator` L12-15 disjoint 注記・
        Pitfall 5 isotonic 過学習リスク低減)。``FrozenEstimator`` で base を凍結してから
        ``CalibratedClassifierCV`` に渡すことで・calibrator の fit が base を再 fit しないことを
        構造的保証する (sklearn 1.9.0 prefit idiom・C-12-03-4 2-window 分離)。

    **method 選択 (sklearn docs・Pitfall 5):**
        - ``calib_sample_size >= MARKET_CALIB_SAMPLE_THRESHOLD=1000`` → ``method='isotonic'``
          (non-parametric・柔軟・過学習リスク低)
        - ``calib_sample_size < 1000`` → ``method='sigmoid'`` (Platt・parametric・安定)

    **odds clipping (D-05 (c)・planner 事前登録):**
        極端オッズの ``1/odds`` が ``1.0`` に飽和 (``odds=1.0`` → ``1.0``) あるいは ``0.0`` に
        近づくのを防ぐため ``[ODDS_CLIP_MIN, ODDS_CLIP_MAX] = [1.0, 100.0]`` で clipping する。

    §11.2 聖域 (test 窓 sanctuary):
        本関数は ``odds_train`` / ``y_train`` / ``odds_calib`` / ``y_calib`` のみを消費し・
        test 窓 outcome 系引数 (``y_test`` / ``outcome_test`` / ``y_outcome_test``) を取らない
        (Shared Pattern 6・シグネチャ検証)。test 窓は戻り値の calibrator を ``predict_proba``
        で適用するのみ。

    Parameters
    ----------
    odds_train : np.ndarray
        train 窓の fuku_odds_lower (1/odds を base 確率に)。
    y_train : np.ndarray
        train 窓の binary outcome (0/1)。
    odds_calib : np.ndarray
        calib 窓の fuku_odds_lower。
    y_calib : np.ndarray
        calib 窓の binary outcome (0/1)。
    calib_sample_size : int
        calib slice のサンプル数。method (isotonic/sigmoid) 切替に使用 (Pitfall 5)。

    Returns
    -------
    CalibratedClassifierCV
        ``.fit()`` 済み calibrator。base は ``odds_train``/``y_train`` で学習済み・calibrator は
        ``odds_calib``/``y_calib`` で校正済み (2-window 分離)。
    """
    # --- base (LogisticRegression) を train 窓で fit (C-12-03-4 2-window 分離) ---
    odds_train_clipped = np.clip(np.asarray(odds_train, dtype=float), ODDS_CLIP_MIN, ODDS_CLIP_MAX)
    market_base_p_train = (1.0 / odds_train_clipped).reshape(-1, 1)
    y_train_int = np.asarray(y_train).astype(int)
    base = LogisticRegression(C=1e6, max_iter=1000)  # ほぼ正則化なし・1/odds をそのまま通す
    base.fit(market_base_p_train, y_train_int)

    # --- calibrator (CalibratedClassifierCV) を calib 窓で fit ---
    # sklearn 1.9.0 prefit idiom: FrozenEstimator で base を凍結してから CalibratedClassifierCV へ。
    # これで calibrator.fit が base を再 fit しない (2-window 分離の構造的保証・utils/calibrator.py 参照・C-12-03-4)。
    method = "isotonic" if calib_sample_size >= MARKET_CALIB_SAMPLE_THRESHOLD else "sigmoid"
    frozen = FrozenEstimator(base)
    calibrator = CalibratedClassifierCV(estimator=frozen, method=method)
    odds_calib_clipped = np.clip(np.asarray(odds_calib, dtype=float), ODDS_CLIP_MIN, ODDS_CLIP_MAX)
    market_base_p_calib = (1.0 / odds_calib_clipped).reshape(-1, 1)
    y_calib_int = np.asarray(y_calib).astype(int)
    calibrator.fit(market_base_p_calib, y_calib_int)
    return calibrator


# ---------------------------------------------------------------------------
# run_falsification_test (事前登録評価回帰・D-05・EVAL-02・§11.2 sanctuary)
# ---------------------------------------------------------------------------


def run_falsification_test(
    y_outcome_test: np.ndarray,
    market_implied_test: np.ndarray,
    model_p_test: np.ndarray,
    race_id_test: np.ndarray,
    *,
    field_size_test: np.ndarray | None = None,
    odds_band_test: np.ndarray | None = None,
    holm_alpha: float = HOLM_ALPHA,
    alpha: float = Q_LEVEL_FALSIFICATION,
) -> dict[str, Any]:
    """**事前登録評価回帰 (pre-registered evaluation regression) を test 窓に fit する最終検定**.

    ``logit(outcome) ~ logit(market_implied) + logit(model_p)`` のロジット回帰を
    :mod:`statsmodels` で race_id clustered SE で test 窓に fit し・``model_p`` 係数の有意性を
    α=0.05 で検定する (D-05・EVAL-02)。bin/odds_band サブ解析では Holm 補正を適用する
    (主検定 ``model_p`` 単一係数は Holm 不要・D-05)。

    本関数は **事前登録評価回帰仕様 (pre-registered evaluation regression)** を test 窓に fit
    する最終検定であり・予測モデル ``p`` の再学習は行わない (§11.2 聖域)。回帰仕様
    (共変量 ``field_size``・logit clipping ``eps=1e-6``・subgroup ``odds_band``・2係数モデル
    ``logit(market_implied)+logit(model_p)``・clustered SE ``groups=race_id``・α=0.05) は
    test 評価前に :func:`write_falsification_spec` で ``reports/12-evaluation/falsification-spec.json``
    として byte-reproducible に事前書き出しされる (theta/q_shrink.json 事前書き出し idiom・
    §11.2 聖域の threshold dredging 監査)。回帰仕様を test 評価後に変更する経路を持たない。

    **SAFE-01-ALLOW: odds / market_implied / model_p**
        本関数は ``market_implied_test`` / ``model_p_test`` 引数 (市場情報・予測確率系外部参照) を
        受け取る。evaluation 専用層の境界であり・feature 構築経路から切り離されている (SAFE-01)。

    **§11.2 聖域 (test 窓 sanctuary):**
        ``market_implied`` calibrator は :func:`fit_market_implied_calibrator` で train/calib 窓で
        fit 済みのものを外部から受け取る (本関数は test 窓に適用のみ)。本関数の test 窓 fit は
        事前登録評価回帰の最終検定であり・予測モデル ``p`` の再学習でない。

    **統計的厳密さ (D-05・D-01 修正文・Pitfall 4):**
        - α=0.05 は事前登録・race_id clustered SE で race 内相関を統制。
        - bin/odds_band サブ解析は Holm 補正 (``multipletests method='holm'``)。
        - :func:`logit_clip` で logit clipping ``eps=1e-6`` (Pitfall 6・inf 回避)。
        - ``statsmodels`` 収束失敗 (``ConvergenceWarning``) や ``cov_kwds`` groups 長不一致は
          :class:`RuntimeError` (silent fallback 禁止・Shared Pattern 4)。

    **verdict (D-05・EVAL-02・鏡像 D-01 修正文):**
        - ``model_p_pvalue < α`` → ``'feature_gap'``: 市場 residual が残る (特徴量不足候補)。
          「モデルが市場を打つ保証」でなく・α=0.05 で market 条件付きでも model_p に residual が
          観測されたという正直な統計的所見。
        - ``model_p_pvalue >= α`` → ``'structural_limit'``: core value 維持での黒字化棄却候補。
          market 係数が model を包摂 (model が市場 BIAS 補正程度しか残していない可能性)。

    Parameters
    ----------
    y_outcome_test : np.ndarray
        test 窓の binary outcome (0/1)。
    market_implied_test : np.ndarray
        test 窓の market 暗示確率 (:func:`fit_market_implied_calibrator` の ``predict_proba`` 出力)。
    model_p_test : np.ndarray
        test 窓の予測確率 ``p_fukusho_hit`` (race-relative 補正後)。
    race_id_test : np.ndarray
        test 窓の race_id (clustered SE の groups・race 内 outcome 相関を統制)。
    field_size_test : np.ndarray | None
        共変量 (D-05 (c)・planner 事前登録・field size strata 統制)。None の場合は共変量なし。
    odds_band_test : np.ndarray | None
        odds_band サブ解析用の odds 値 (:func:`src.model.segment_eval._odds_band` が適用される)。
        None の場合は odds_band サブ解析をスキップ。
    holm_alpha : float
        Holm 補正 α (既定 ``HOLM_ALPHA=0.05``・bin/odds_band サブ解析のみ)。
    alpha : float
        主検定 α (既定 ``Q_LEVEL_FALSIFICATION=0.05``)。

    Returns
    -------
    dict
        ``model_p_coef`` (float) / ``model_p_pvalue`` (float) / ``model_p_significant`` (bool) /
        ``verdict`` ('feature_gap' | 'structural_limit') /
        ``sub_analyses_odds_band`` (dict: ``{band: {pvalue, coef, corrected_pvalue}}``)。
    """
    # 入力の整合性検証 (fail-loud・Shared Pattern 4)
    y = np.asarray(y_outcome_test).astype(int)
    market = np.asarray(market_implied_test, dtype=float)
    model_p = np.asarray(model_p_test, dtype=float)
    race_ids = np.asarray(race_id_test)
    n = len(y)
    if len(market) != n or len(model_p) != n or len(race_ids) != n:
        raise RuntimeError(
            f"run_falsification_test: 入力長不一致 y={n}, market={len(market)}, "
            f"model_p={len(model_p)}, race_id={len(race_ids)} (Shared Pattern 4)"
        )

    # --- 事前登録評価回帰の設計行列構築 (logit clipping・Pitfall 6) ---
    logit_market = logit_clip(market)
    logit_model_p = logit_clip(model_p)
    X = np.column_stack([logit_market, logit_model_p])
    if field_size_test is not None:
        fs = np.asarray(field_size_test, dtype=float)
        if len(fs) != n:
            raise RuntimeError(
                f"run_falsification_test: field_size 長不一致 n={n}, field_size={len(fs)}"
            )
        X = np.column_stack([X, fs])
    X = sm.add_constant(X)

    # --- 主検定: model_p 係数の race_id clustered SE (Pitfall 4・cov_kwds API) ---
    # ★ Pitfall 4 対応: cov_type='cluster', cov_kwds={'groups': race_id_array}
    # groups= 直接渡しは error (GitHub statsmodels#6287)・cov_kwds={'groups': array} が正しい API。
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # ConvergenceWarning を catch して RuntimeError に変換
        try:
            model = sm.Logit(y, X)
            result = model.fit(
                cov_type="cluster",
                cov_kwds={"groups": race_ids},
                disp=0,
                maxiter=200,
            )
        except Warning as warn:
            raise RuntimeError(
                f"run_falsification_test: statsmodels 収束失敗 (ConvergenceWarning 等)・"
                f"silent fallback 禁止 (Shared Pattern 4): {warn!r}"
            ) from warn
        except Exception as exc:
            # cov_kwds groups 長不一致等の statsmodels 内部エラーを RuntimeError で wrap
            raise RuntimeError(
                f"run_falsification_test: statsmodels Logit.fit 失敗・"
                f"silent fallback 禁止 (Shared Pattern 4): {exc!r}"
            ) from exc

    # model_p 係数 index: [const, logit_market, logit_model_p, (field_size)]
    model_p_idx = 2
    model_p_coef = float(result.params[model_p_idx])
    model_p_pvalue = float(result.pvalues[model_p_idx])
    model_p_significant = bool(model_p_pvalue < alpha)
    verdict = "feature_gap" if model_p_significant else "structural_limit"

    # --- bin/odds_band サブ解析 (Holm 補正・主検定とは別・D-05) ---
    sub_analyses_odds_band: dict[str, Any] = {}
    if odds_band_test is not None:
        odds_arr = np.asarray(odds_band_test, dtype=float)
        if len(odds_arr) != n:
            raise RuntimeError(
                f"run_falsification_test: odds_band 長不一致 n={n}, odds_band={len(odds_arr)}"
            )
        band_labels = _odds_band(pd.Series(odds_arr))
        band_pvalues: list[float] = []
        band_entries: list[tuple[str, float, float]] = []
        for label in ODDS_BAND_LABELS:
            mask = band_labels == label
            if int(np.sum(mask)) < 30:  # min bin count (segment_eval の CALIBRATION_CURVE_MIN_BIN_COUNT と同一契約)
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error")
                    sub_model = sm.Logit(y[mask], X[mask])
                    sub_result = sub_model.fit(
                        cov_type="cluster",
                        cov_kwds={"groups": race_ids[mask]},
                        disp=0,
                        maxiter=200,
                    )
                sub_pvalue = float(sub_result.pvalues[model_p_idx])
                sub_coef = float(sub_result.params[model_p_idx])
            except Warning as warn:
                raise RuntimeError(
                    f"run_falsification_test: odds_band={label!r} サブ解析で statsmodels 収束失敗: {warn!r}"
                ) from warn
            except Exception as exc:
                raise RuntimeError(
                    f"run_falsification_test: odds_band={label!r} サブ解析失敗: {exc!r}"
                ) from exc
            band_pvalues.append(sub_pvalue)
            band_entries.append((label, sub_coef, sub_pvalue))

        # Holm 補正 (multipletests method='holm'・bin/odds_band サブ解析のみ・D-05)
        if band_pvalues:
            reject, corrected, _, _ = multipletests(
                band_pvalues, alpha=holm_alpha, method="holm"
            )
            for (label, coef, raw_p), corr_p, rej in zip(band_entries, corrected, reject, strict=True):
                sub_analyses_odds_band[label] = {
                    "pvalue": raw_p,
                    "coef": coef,
                    "corrected_pvalue": float(corr_p),
                    "significant_after_holm": bool(rej),
                }

    return {
        "model_p_coef": model_p_coef,
        "model_p_pvalue": model_p_pvalue,
        "model_p_significant": model_p_significant,
        "verdict": verdict,
        "alpha": alpha,
        "holm_alpha": holm_alpha,
        "sub_analyses_odds_band": sub_analyses_odds_band,
    }


# ---------------------------------------------------------------------------
# write_falsification_spec (事前書き出しヘルパー・theta/q_shrink.json idiom・§11.2 聖域)
# ---------------------------------------------------------------------------


def write_falsification_spec(out_path: str | Path) -> Path:
    """事前登録評価回帰仕様を byte-reproducible な JSON として書き出すヘルパー.

    本ヘルパーは :func:`run_falsification_test` の回帰仕様 (共変量 ``field_size``・logit clipping
    ``eps=1e-6``・subgroup ``odds_band``・2係数モデル ``logit(market_implied)+logit(model_p)``・
    clustered SE ``groups=race_id``・α=0.05) を ``reports/12-evaluation/falsification-spec.json``
    として byte-reproducible に書き出す (theta/q_shrink.json 事前書き出し idiom・§11.2 聖域の
    threshold dredging 監査)。

    **実際の書き出し実行は Plan 04 ``run_phase12_evaluation.py`` が行う** (test 窓評価前)。
    本ヘルパーは byte-reproducible であること (``sort_keys=True, ensure_ascii=False,
    allow_nan=False``) と回帰仕様が事前登録値として固定されていることを提供する。

    Parameters
    ----------
    out_path : str | Path
        出力 JSON パス (``reports/12-evaluation/falsification-spec.json``)。

    Returns
    -------
    Path
        ``out_path`` (Path)。
    """
    spec: dict[str, Any] = {
        "spec_version": "1.0",
        "phase": 12,
        "test": "falsification_evaluation_regression",
        "description": (
            "Pre-registered evaluation regression fitted on the test window "
            "(事前登録評価回帰を test 窓に fit する最終検定)"
        ),
        "regression": {
            "formula": "logit(outcome) ~ logit(market_implied) + logit(model_p) [+ field_size]",
            "predictors": ["logit_market_implied", "logit_model_p"],
            "covariates": ["field_size"],
            "logit_clip_eps": LOGIT_CLIP_EPS,
            "subgroup": "odds_band",
            "odds_band_edges": [float(x) if np.isfinite(x) else "inf" for x in ODDS_BAND_EDGES],
            "odds_band_labels": list(ODDS_BAND_LABELS),
            "cov_type": "cluster",
            "cluster_groups": "race_id",
            "alpha": Q_LEVEL_FALSIFICATION,
            "sub_analysis_correction": "holm",
            "holm_alpha": HOLM_ALPHA,
            "sub_analysis_scope": "odds_band bins (主検定 model_p 単一係数は Holm 不要)",
            "odds_clip_min": ODDS_CLIP_MIN,
            "odds_clip_max": ODDS_CLIP_MAX,
            "market_calib_sample_threshold": MARKET_CALIB_SAMPLE_THRESHOLD,
        },
        "market_implied_calibrator": {
            "method": "CalibratedClassifierCV (FrozenEstimator + isotonic/sigmoid)",
            "fit_windows": ["train (base)", "calib (calibrator)"],
            "two_window_separation": True,
            "sanctuary": "§11.2 test 窓 sanctuary: fit は train/calib 窓のみ・test 窓は適用のみ",
        },
        "verdict_semantics": {
            "feature_gap": "model_p pvalue < α → 市場 residual が残る (特徴量不足候補)",
            "structural_limit": "model_p pvalue >= α → core value 維持での黒字化棄却候補 (market が model を包摂)",
            "statistical_rigor": "α=0.05 は事前登録・market 条件付き residual の検出 (過度な保証主張でない)",
        },
        "constants_source": "src/eval/falsification.py constants block (C-12-04-3 集約)",
    }
    payload = json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(out)
    return out


__all__ = [
    # constants block (C-12-04-3・C3-12-03-1 集約)
    "Q_LEVEL_SHRINKAGE",
    "Q_LEVEL_FALSIFICATION",
    "HOLM_ALPHA",
    "LOGIT_CLIP_EPS",
    "ODDS_CLIP_MIN",
    "ODDS_CLIP_MAX",
    "MARKET_CALIB_SAMPLE_THRESHOLD",
    "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD",
    "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD",
    # helpers
    "logit_clip",
    "fit_market_implied_calibrator",
    "run_falsification_test",
    "write_falsification_spec",
]
