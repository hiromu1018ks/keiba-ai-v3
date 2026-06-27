# ruff: noqa: E501
"""Phase 11 SC#1/#3/#4/D-02〜D-10 race-relative 補正層（pure 関数・stub）.

本モジュールは Phase 11 で導入するレース内相対確率モデルの補正層であり・binary 本体
（``src/model/trainer.py`` の LightGBM/CatBoost・``objective='binary'``）は **一切変更しない**
（D-01・SC#3 bit-identical 維持）。その上に logit temperature θ と per-race intercept α_r の
二分探索（``scipy.optimize.brentq``）を乗せ・各 race で ``sum_i p_i = k``（複勝払戻対象数・
8頭以上=3・5-7頭=2）を厳密に満たすレース内相対確率を生成する（MODEL-01・D-02）。

設計の核心（CONTEXT D-01〜D-10・CLAUDE.md leak-prevention 設定）:

- **binary 本体不変（D-01）**: ``trainer.train_lightgbm`` / ``train_catboost`` は再利用するのみ。
  補正層は binary model の出力（``predict_proba → clip → logit`` 経路）を消費し・
  特徴量や学習ロジックには触れない。
- **補正層のみ追加**: logit temperature θ + per-race α_r 二分探索（D-02）。sigmoid + per-race
  intercept で ``p_i ∈ (0,1)`` を厳密に保ち・``k * softmax`` の ``p>1`` リスクを回避。
- **test 窓 outcome 不使用（D-10 自己完結性）**: α_r は各 race の base logit ``s_i`` と払戻対象数
  ``k`` のみから決定し・test 窓の outcome ラベルを使わない・他 race の情報を使わない。
  θ のみ calib slice（later-disjoint）で fit する。
- **市場情報 proxy 不使用（SAFE-01・SC#4）**: 本モジュールの AST に市場情報 proxy
  トークン（``tests/audit/test_audit_race_relative.py`` が定義する禁止集合）の
  Name/Attribute/string-constant は0件（静的証明）。レース内相対補正は純粋に logit 演算のみで行う。
- **fail-loud（D-09）**: ``p_cal`` に NaN/inf がある場合は ``RuntimeError``（neutral 補完・
  silent fallback 禁止・Phase 10 gap-closure CR-01〜04 鏡像）。

本 stub は Wave 0（本 plan 11-01）で公開 API の契約（定数 + 関数シグネチャ + docstring）のみを
固定し・実装は Wave 1（11-02）が埋める。関数本体は ``raise NotImplementedError`` のみ。

参考: 11-RESEARCH.md Pattern 1/2/3（実証検証済みコード断片）/ 11-PATTERNS.md /
      src/utils/calibrator.py（pure 関数 + sklearn/scipy idiom の踏襲元）.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# binning 契約の import 再利用（D-03/D-05・codex review HIGH#2 対応）。
# race_relative 内に np.linspace による独自 bin edge 再定義は持たない
# （true import-level parity・evaluator が binning 実装の唯一の正）。
from src.model.evaluator import (  # noqa: E402
    CALIBRATION_CURVE_BINS,
    _compute_calibration_curve_bins,
)
from src.model.segment_eval import _odds_band  # noqa: E402

# ---------------------------------------------------------------------------
# researcher 裁量 #1: α_r 二分探索の収束仕様（docstring で明示・test で検証）
# ---------------------------------------------------------------------------
# |sum(p) - k| の理論上界 ≈ 2 * ALPHA_SEARCH_XTOL（brentq の xtol 仕様）。
# 実測では 4.44e-16 に達する（RESEARCH Pattern 1 実証検証）。
ALPHA_SEARCH_XTOL: float = 1e-9
# brentq の rtol（相対許容誤差）・x のスケール不変性のため xtol より小さく設定。
ALPHA_SEARCH_RTOL: float = 1e-12
# brentq の反復数上限。理論反復数上限 < 50（brentq は superlinear 収束）・200 は safety margin。
ALPHA_SEARCH_MAXITER: int = 200
# brentq の探索区間。α_r = logit(k/n) を中心に十分な余裕を持たせる（n=頭数・最大18）。
# logit(3/18) ≈ -1.61・極端な k/n でも ±100 は十分な上界。
ALPHA_SEARCH_BOUNDS: tuple[float, float] = (-100.0, 100.0)

# ---------------------------------------------------------------------------
# researcher 裁量 #2: clip 閾値（logit 変換前の p_cal 用・Pitfall 1 対策）
# ---------------------------------------------------------------------------
# IsotonicRegression は正例群に 1.0・負例群に 0.0 を生成する（段階関数）。
# logit(0) = -inf / logit(1) = +inf で α_r 二分探索が NaN 伝播するため・
# logit 変換前に ``np.clip(p_cal, ε, 1-ε)`` を必須適用（D-09 fail-loud の前段）。
# ε=1e-6 で logit 動的範囲 ±13.8（base logit ±10 と同オーダー）・sum(p)=k 精度 <1e-12 を同時達成
# （RESEARCH Pattern 1 Pitfall 1 実証検証）。
P_CAL_CLIP_EPSILON: float = 1e-6

# ---------------------------------------------------------------------------
# D-03 事前登録 θ 候補集合（§11.2 聖域・test 窓での選び直し禁止）
# ---------------------------------------------------------------------------
# θ=1 が baseline（logit temperature なし・binary baseline と同一 logit スケール）。
# θ>1 が平坦化（logit を縮小・確率が 1/n に近づく）・θ<1 が尖鋭化（logit を拡大）。
# θ<0.5 では尖鋭化で α_r が発散し brentq が符号不一致で失敗するため候補に含めない
# （RESEARCH Pattern 1 境界挙動・Pitfall 2 実証）。
# この候補集合は Plan 11-01 で事前登録し・test 窓で選び直さない（§11.2 聖域・D-03）。
# 選択ルール（calib slice のみ）: (1) 足切り D-04 非劣化 → (2) overprediction penalty 最小 →
# (3) tie-break calib_max_dev → θ=1 に近い候補。
THETA_CANDIDATES: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5)


def solve_alpha_for_race(
    s_logits: np.ndarray,
    theta: float,
    k: int,
) -> float:
    """race 内で ``sum_i sigmoid(s_i/θ + α) = k`` を満たす α を brentq で解く（D-02・D-10 自己完結）.

    数学的健全性（RESEARCH Pattern 1 実証検証済み・HIGH confidence）:
      - ``f(α) = Σ sigmoid(s_i/θ + α) − k`` は α について厳密単調増加・連続
        （sigmoid 単調増加の和は単調増加）。
      - 値域: ``lim_{α→−∞} f(α) = −k``・``lim_{α→+∞} f(α) = n − k``（n=頭数）。
      - ``k ∈ (0, n)`` なので ``0 ∈ (−k, n−k) ⊂ 値域`` → IVT より唯一の解が存在。
      - brentq は ``|sum(p) − k| ≤ ALPHA_SEARCH_XTOL`` (1e-9) で収束（実測 4.44e-16）。

    境界挙動:
      - ``θ → ∞``: ``sigmoid(s_i/θ + α) → sigmoid(α)``（logit 平坦化）。
        解は ``α = logit(k/n)`` に収束（実証: θ=1e6 で α=-1.609438 = logit(3/18)）。
      - ``θ → 0+``: logit 尖鋭化・α_r 発散。brentq が符号不一致で失敗する。
        → 候補 θ に極小値（θ < 0.5 等）を含めない根拠（THETA_CANDIDATES 事前登録）。

    D-10 自己完結性: α_r 計算に test 窓 outcome は使わない・他 race 情報は使わない。
    ``s_logits`` と ``k`` のみから決定（adversarial test で逆証明・test_audit_race_relative.py）。

    Parameters
    ----------
    s_logits : np.ndarray
        race 内全馬の base logit（``apply_race_relative_correction`` で ``p_cal → clip → logit``
        変換済み・finite・D-09 fail-loud 前提）。
    theta : float
        logit temperature（θ=1 が baseline・θ>1 で平坦化・θ<1 で尖鋭化）。
        THETA_CANDIDATES のいずれか（calib slice で選択・test 窓選び直し禁止 §11.2）。
    k : int
        払戻対象数（8頭以上=3・5-7頭=2・D-08 予測時点固定頭数ルール・同着不反映）。

    Returns
    -------
    float
        ``sum_i sigmoid(s_i/θ + α) = k`` を満たす α_r（brentq 収束値・精度 ≤ 1e-9）。

    Raises
    ------
    RuntimeError
        brentq が収束しない（θ が極小で α_r 発散・候補 θ に極小値を含めないこと）。
        また ``s_logits`` に非 finite 値（NaN/inf）が含まれる場合も RuntimeError
        （D-09 fail-loud 鏡像・binary logit 欠損は許容しない）。
    ValueError
        ``theta <= 0`` の場合・または ``k`` が ``0 < k < n`` を満たさない場合。
    """
    # ---- brentq 前 fail-loud guard（D-09 鏡像・codex review MEDIUM 対応） ----
    # 構造的に不健全な入力が brentq に渡るのを防ぐ。これらは呼出側のバグであり
    # silent fallback しない（Phase 10 gap-closure CR-01〜04 と同じ方針）。
    if not np.all(np.isfinite(s_logits)):
        raise RuntimeError(
            "solve_alpha_for_race: s_logits に非 finite 値（NaN/inf）が含まれる・"
            "binary logit 欠損は許容しない（D-09 fail-loud 鏡像・silent fallback 禁止）"
        )
    if not (theta > 0):
        raise ValueError(
            f"solve_alpha_for_race: theta > 0 が必須・theta={theta}"
        )
    n = len(s_logits)
    if not (0 < int(k) < n):
        raise ValueError(
            f"solve_alpha_for_race: 0 < k < n が必須・k={int(k)} n={n}"
        )

    def f(alpha: float) -> float:
        z = s_logits / theta + alpha
        return float(np.sum(1.0 / (1.0 + np.exp(-z))) - k)

    # REVIEW WR-02: brentq が収束失敗で送出する ValueError (scipy 仕様) を
    # docstring 契約の RuntimeError でラップする（fail-loud・sentinel fallback なし）。
    # 発散の主因は θ が極小で α_r が ALPHA_SEARCH_BOUNDS を超える場合。
    try:
        return float(
            brentq(
                f,
                ALPHA_SEARCH_BOUNDS[0],
                ALPHA_SEARCH_BOUNDS[1],
                xtol=ALPHA_SEARCH_XTOL,
                rtol=ALPHA_SEARCH_RTOL,
                maxiter=ALPHA_SEARCH_MAXITER,
            )
        )
    except ValueError as e:
        raise RuntimeError(
            f"solve_alpha_for_race: brentq 収束失敗（θ={theta} が極小で α_r 発散の可能性・"
            f"候補 θ に極小値を含めないこと）: {e}"
        ) from e


def apply_race_relative_correction(
    p_cal: np.ndarray,
    theta: float,
    k_per_race: np.ndarray,
    race_ids: np.ndarray,
) -> np.ndarray:
    """race 毎に α_r 二分探索を適用し・``sum_i p_i = k`` を厳密に満たす final p を返す.

    D-06 パイプライン step 6-8（base calib → 補正の順序・補正後に追加 calib なし）:
      - step 6: ``p_cal`` を ``clip(ε, 1−ε)`` して logit 変換 → ``s_i``
        （Pitfall 1 対策・IsotonicRegression の 0/1 端点で logit(±inf) 回避）。
      - step 7: race 毎に ``solve_alpha_for_race(s_i, θ, k)`` で α_r を解く
        （race 自己完結・``np.unique(race_ids)`` で他 race 情報混入を構造的排除・D-10）。
      - step 8: ``p_final = sigmoid(s_i/θ + α_r)``（``sum(p)=k`` 厳密・D-10 自己完結）。

    D-09 fail-loud: ``p_cal`` に NaN/inf がある行は ``RuntimeError``（neutral 補完不採用・
    silent fallback 禁止・Phase 10 gap-closure CR-01〜04 鏡像）。特徴量欠損
    （LightGBM/CatBoost が NaN として native 処理して logit を出す）とは区別する。

    D-10 race 自己完結性（adversarial 5段階鋳型で逆証明）:
      - race_id 毎に独立ループ（``np.unique(race_ids)``）・他 race の logit は混入しない。
      - outcome（y_true）は引数に取らない・α_r 計算に使わない。

    補正後に追加 calib をしない（D-06・sum(p)=k が崩れ α_r 再適用でループになるため）。

    Parameters
    ----------
    p_cal : np.ndarray
        calibrated probability（``fit_prefit_calibrator`` 通過後・``predict_proba[:,1]``）。
        finite であること（D-09・NaN/inf は RuntimeError）。
    theta : float
        logit temperature（THETA_CANDIDATES のいずれか・calib slice で選択）。
    k_per_race : np.ndarray
        各行に対応する払戻対象数（race 内で一意・D-08 予測時点固定頭数ルール）。
    race_ids : np.ndarray
        各行に対応する race 識別子（race 毎に独立ループのために使用）。

    Returns
    -------
    np.ndarray
        ``p_cal`` と同一 shape の final probability 配列。race 内で ``sum(p) = k`` が厳密に成立。

    Raises
    ------
    RuntimeError
        ``p_cal`` に NaN/inf が含まれる（D-09 fail-loud）。また race 内で
        ``k_per_race`` が一意でない場合も RuntimeError（D-08/D-09・呼出側バグ）。
    """
    # D-09 fail-loud: p_cal の NaN/inf 検査（neutral 補完・silent fallback 禁止）。
    # src/utils/calibrator.py L86-94 の raise ValueError idiom と同一方針で・
    # `python -O` でも生存する（assert でない）。
    if not np.all(np.isfinite(p_cal)):
        n_bad = int(np.sum(~np.isfinite(p_cal)))
        raise RuntimeError(
            f"apply_race_relative_correction: p_cal に {n_bad} 件の非 finite 値 "
            f"(NaN/inf)・binary logit 欠損 fail-loud（D-09・silent fallback 禁止）"
        )

    # step 6: p_cal を clip(ε, 1−ε) して logit 変換 → s_i（Pitfall 1 対策・
    # IsotonicRegression の 0/1 端点で logit(±inf) 回避）。
    p_clipped = np.clip(p_cal, P_CAL_CLIP_EPSILON, 1.0 - P_CAL_CLIP_EPSILON)
    s_logits = np.log(p_clipped / (1.0 - p_clipped))

    p_final = np.empty_like(p_cal, dtype=float)

    # step 7-8: race 毎に α_r を解き final p を算出（race 自己完結・D-10）。
    # np.unique(race_ids) で他 race の logit が混入しないことを構造的に保証（Pitfall 5）。
    for rid in np.unique(race_ids):
        mask = race_ids == rid
        s_race = s_logits[mask]
        # race 内 k_per_race 一意性 guard（codex review MEDIUM・D-08/D-09）。
        # 呼出側が race 内一意を保証すべき値が混入した場合は silent fallback せず fail-loud。
        k_values = np.unique(k_per_race[mask])
        if len(k_values) != 1:
            raise RuntimeError(
                f"apply_race_relative_correction: race {rid!r} 内で k_per_race が一意でない"
                f"（D-08・予測時点固定頭数ルール違反）: k_values={k_values.tolist()}"
            )
        k = int(k_values[0])
        alpha_r = solve_alpha_for_race(s_race, theta, k)
        # step 8: p_final = sigmoid(s_i/θ + α_r)（sum(p)=k 厳密・D-10 自己完結）。
        p_final[mask] = 1.0 / (1.0 + np.exp(-(s_race / theta + alpha_r)))

    return p_final


def compute_overprediction_penalty(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    market_signal: np.ndarray,
    *,
    cell_filter_mask: np.ndarray | None = None,
) -> float:
    """overprediction penalty = Σ_cells (count_cell/N_total) × max(0, mean_pred − frac_pos)（D-03/D-05）.

    厳密定義（RESEARCH Pattern 3・researcher 裁量 #4 確定値）:
      - 市場シグナル帯 × 予測確率 bin の各セルで ``(mean_pred, frac_pos, count)`` を計算
        （binning 契約は ``src/model/segment_eval.py`` / ``src/model/evaluator.py`` から
        import 再利用・bit-identical・独自 binning 禁止）。
      - 各セルの overprediction = ``max(0, mean_pred_cell − frac_pos_cell)``（半波整流・
        予測率 > 実現率 の正方向誤差だけを重く見る）。
      - セル全体をサンプル数で重み付け平均（ECE 風・対称）。

    スケール切り替え（``cell_filter_mask``）:
      - overall: ``cell_filter_mask=None`` → 全セル。
      - selected/high-EV 層: ``cell_filter_mask`` で市場シグナル帯 in {high} AND 予測確率 bin
        in {top EV deciles} に制限。

    REVIEW WR-07 — ``n_total`` スケールの注意（呼出側が誤解しやすい点）:
      - ``cell_filter_mask=None`` (overall) の場合: ``n_total`` は全サンプル数。
        各セルの ``count / n_total`` の和は 1.0 になり・penalty は全サンプルの
        重み付け平均（全サンプルベースのスケール）。
      - ``cell_filter_mask`` 指定 (selected/high-EV 層) の場合: ``n_total`` は
        **mask 後件数（= selected 層のサイズ）** になる。各セルの ``count / n_total``
        の和は 1.0 になり・penalty は selected 層内の重み付け平均（selected 層内ベース）。
      - つまり戻り値のスケールが overall と selected で異なる（overall は全サンプル和ベース・
        selected は selected 内和ベース）。両者を直接比較する gate では注意が必要。
        現状の呼出側 (``_compute_overprediction_from_pred``) は ``cell_filter_mask=None`` で
        呼ぶため影響しないが・将来の拡張で selected 層の overprediction を計算する際は
        ``n_total`` が mask 後件数になることを前提に呼出側でスケール解釈すること。

    本関数は SC#2 改善 gate（D-05 必須条件 1）の主指標。θ 選択（D-03 step 2）でも使用。
    市場シグナル（人気帯相当）は feature でなく evaluation 専用の external signal であり・
    モデル特徴量には混入しない（SAFE-01・SC#4 は feature 側の聖域・evaluation は別層）。

    REVIEW WR-01 — SAFE-01 allow-list 明示宣言:
    本関数は ``market_signal`` 引数（市場シグナル外部参照）を受け取る。
    これは evaluation 専用層の境界であり・feature matrix 構築経路
    （build_training_frame / FEATURE_COLUMNS）から切り離されている。
    呼出側（``_compute_overprediction_from_pred``）は pred_df の評価専用列
    （市場情報参照系・SAFE-01 forbidden prefix に該当）から market_signal を構築し・
    feature snapshot の FEATURE_COLUMNS にはこれらの列は含まれない
    （test_audit_field_strength.py で forbidden prefix 0件を検証済み）。
    本 docstring の ``SAFE-01-ALLOW: market_signal`` マーカーは・AST 監査
    （test_audit_race_relative.py::test_market_signal_arg_has_allowlist）が
    本関数の ``market_signal`` 引数を検出した際の explicit な allow-list 宣言。
    本マーカーが無い場合・または market_signal が feature 構築経路に混入した場合は
    監査が fail-loud する（SAFE-01 聖域の機械保証・docstring 紳士協定でない）。
    ``SAFE-01-ALLOW: market_signal``

    Parameters
    ----------
    y_true : np.ndarray
        バイナリ実測ラベル（0/1）。
    y_pred : np.ndarray
        予測確率（race-relative 補正後の ``p_final`` または v1.0 binary baseline）。
    market_signal : np.ndarray
        市場シグナル（評価軸の外部参照・feature でない）。binning は ``segment_eval._odds_band``
        と同一契約で ``segment_eval`` から import 再利用。
    cell_filter_mask : np.ndarray | None
        ``None`` の場合は全行（overall）。selected/high-EV 層は呼出側で mask を構築。

    Returns
    -------
    float
        overprediction penalty（0 以上・小さいほど良い）。``n_total == 0`` の場合は NaN。

    Raises
    ------
    NotImplementedError
        本 stub では未実装（Wave 1・plan 11-02 で実装）。
    """
    # selected/high-EV 層の制限（呼出側が mask を構築・overall は None）。
    if cell_filter_mask is not None:
        y_true = y_true[cell_filter_mask]
        y_pred = y_pred[cell_filter_mask]
        market_signal = market_signal[cell_filter_mask]

    n_total = float(len(y_pred))
    if n_total == 0:
        return float("nan")

    # 市場シグナル帯: segment_eval._odds_band を import 再利用（bit-identical・codex HIGH#2）。
    odds_b = _odds_band(pd.Series(market_signal))

    penalty = 0.0
    # 各市場シグナル帯内で・予測確率 bin は evaluator._compute_calibration_curve_bins
    # (strategy='uniform', n_bins=CALIBRATION_CURVE_BINS) を呼出して bit-identical に算出。
    # race_relative 内に独自 bin edge（np.linspace 等）を再定義しない（codex HIGH#2）。
    for ob in np.unique(odds_b):
        cell_mask = odds_b == ob
        if int(cell_mask.sum()) == 0:
            continue
        y_true_cell = y_true[cell_mask]
        y_pred_cell = y_pred[cell_mask]
        bins = _compute_calibration_curve_bins(
            y_true_cell,
            y_pred_cell,
            strategy="uniform",
            n_bins=CALIBRATION_CURVE_BINS,
        )
        count_arr = bins["counts"]
        mean_pred_arr = bins["mean_pred"]
        frac_pos_arr = bins["frac_pos"]
        # 半波整流 ECE: max(0, mean_pred_cell - frac_pos_cell) のサンプル数重み付け和。
        for j in range(len(count_arr)):
            count = int(count_arr[j])
            if count == 0:
                continue
            overprediction = max(0.0, float(mean_pred_arr[j]) - float(frac_pos_arr[j]))
            penalty += (count / n_total) * overprediction

    return float(penalty)


__all__ = [
    "ALPHA_SEARCH_XTOL",
    "P_CAL_CLIP_EPSILON",
    "THETA_CANDIDATES",
    "solve_alpha_for_race",
    "apply_race_relative_correction",
    "compute_overprediction_penalty",
]
