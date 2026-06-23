"""Phase 6 segment 安定性評価（EVAL-03 / D-10 / D-11 / D-12）.

6軸（year/month/jyocd/entry_count/ninki/odds_band）の segment 別 calibration curve + scalar 指標
を生成し・Plotly 静的 HTML（include_plotlyjs='directory' で plotly.min.js 共有1ファイル参照）と
byte-reproducible な JSON で出力する。

**設計の核心（契約一元化・bit-identical）:**

binning 契約は :mod:`src.model.evaluator` の ``_compute_calibration_curve_bins`` /
``_compute_ece`` / ``_compute_mce`` / ``_compute_calibration_max_dev_guarded`` および定数
``CALIBRATION_CURVE_BINS=10`` / ``CALIBRATION_CURVE_MIN_BIN_COUNT=30`` を import して**再利用**する。
独自の binning パラメータ・独自の binning 実装は導入しない（bit-identical 保証・契約一元化・T-06-07）。

**REVIEW HIGH#4 対応（banding）:**

人気帯（ninki）・オッズ帯（fukuoddslower）は連続/高基数の生値で segment 軸とすると数千の segment に
分裂し MIN_BIN_COUNT=30 でほぼ全滅する（SC#3「per-人気帯/per-オッズ帯」の部分達成になる）。
:func:`_ninki_band` / :func:`_odds_band` で離散帯ラベルに変換してから segment 軸として使用する
（``np.digitize`` で決定論的・``pd.cut`` は index 依存で不使用）。

**REVIEW C12 対応（race_date dtype 正規化）:**

year/month 軸は ``pd.to_datetime(df["race_date"], errors="coerce")`` で datetime に正規化してから
``.dt.year`` / ``.dt.month`` を抽出する（run_backtest ``_filter_label_by_period`` パターン踏襲・
Python date object / object dtype / datetime64[ns] のいずれでも AttributeError を起こさない）。

**REVIEW C13 cycle-2 修正（N1 解消）:**

``fig.write_html(include_plotlyjs='directory')`` で plotly.min.js を reports/06-segments/ 直下に
1ファイル生成し・6 HTML は ``<script src="plotly.min.js">`` で共有参照する
（~3.5MB × 6 重複を解消・reports/ 全体 tracked ポリシー維持・.gitignore は変更しない）。

参照:
  - src/model/evaluator.py（binning 契約の提供元）
  - src/model/artifact.py（_atomic_write_text・byte-reproducible JSON 出力）
  - 06-CONTEXT.md D-10/D-11/D-12（JSON + Plotly HTML・curve 並列 + scalar 表・全6軸）
  - 06-RESEARCH.md Pattern 2（segment 別評価）+ Pattern 3（Plotly 静的 HTML）
  - 06-PATTERNS.md segment_eval.py セクション
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.model.artifact import _atomic_write_text
from src.model.evaluator import (
    CALIBRATION_CURVE_BINS,
    CALIBRATION_CURVE_MIN_BIN_COUNT,
    _compute_calibration_curve_bins,
    _compute_calibration_max_dev_guarded,
    _compute_ece,
    _compute_mce,
)

# ---------------------------------------------------------------------------
# 定数 — D-12 6軸 / REVIEW HIGH#4 banding
# ---------------------------------------------------------------------------

# 人気帯の離散化（SC#3「per-人気帯」履行・1-18 の ninki を4帯に集約）
# np.digitize で決定論的に bin index を計算（pd.cut は index 依存で不使用）
NINKI_BAND_EDGES: np.ndarray = np.array([0.0, 3.0, 6.0, 9.0, np.inf])
NINKI_BAND_LABELS: tuple[str, ...] = ("1-3", "4-6", "7-9", "10+")

# オッズ帯の離散化（SC#3「per-オッズ帯」履行・fukuoddslower 連続 float を4帯に集約）
# 閾値は JRA 複勝オッズの典型的分布（1.0-2.9=1番人気クラス・3.0-4.9=中位・5.0-9.9=穴・10+=大穴）
ODDS_BAND_EDGES: np.ndarray = np.array([0.0, 2.9, 4.9, 9.9, np.inf])
ODDS_BAND_LABELS: tuple[str, ...] = ("1.0-2.9", "3.0-4.9", "5.0-9.9", "10+")

# 6軸の segment 列名マッピング（D-12）
# - 値は DataFrame の入力列名
# - year/month は同じ race_date 列を共有（Info #6 一元化）
# - ninki/fukuoddslower は evaluate_all_segments 内で _ninki_band/_odds_band を適用して離散帯化
SEGMENT_AXES: dict[str, str] = {
    "year": "race_date",
    "month": "race_date",
    "jyocd": "jyocd",
    "entry_count": "entry_count",
    "ninki": "ninki",  # _ninki_band 適用で帯化
    "odds_band": "fukuoddslower",  # _odds_band 適用で帯化
}

# segment 欠損値ラベル（banding 関数で NaN をこのラベルに変換）
_MISSING_LABEL = "__MISSING__"


def _sanitize_nan_to_null(obj: Any) -> Any:
    """dict/list/float 再帰的に走査し NaN/Inf を None に正規化する（RFC 8259 strict JSON 化）。

    segment scalar はサンプル不足（MIN_BIN_COUNT 未満・bin 未構築）で NaN になる場合がある
    （例: ``odds_band.__MISSING__`` / ``entry_count.6.0``）。Python json.dumps はデフォルトで
    NaN を ``NaN`` リテラルとして出力するが・これは RFC 8259 strict 仕様違反で Phase 7 Streamlit
    や外部パーサで失敗するリスクがある。NaN は「データなし」の正しい意味論なので null に正規化する。

    ``allow_nan=False`` と組み合わせ・変換漏れがあれば json.dumps が ValueError で fail-loud。
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan_to_null(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# REVIEW HIGH#4 banding 関数
# ---------------------------------------------------------------------------


def _band_labels_from_edges(s: pd.Series, edges: np.ndarray, labels: tuple[str, ...]) -> np.ndarray:
    """np.digitize で bin index を計算し・ラベル文字列を返す共通ヘルパ（bit-identical）。

    ``np.digitize(s, edges[1:-1], right=True)`` で ``[0, len(labels)-1]`` の bin index を計算。
    ``right=True`` により区間は **上界閉区間** ``(edges[i-1], edges[i]]`` となる（PLAN 期待通り
    ninki=3 → "1-3"・odds=2.9 → "1.0-2.9"）。NaN/None は ``_MISSING_LABEL`` に変換
    （evaluator の missing reason 慣例と整合）。
    """
    arr = s.to_numpy(dtype=float)
    # NaN 判定（None も NaN に変換される）
    nan_mask = ~np.isfinite(arr)
    # np.digitize は NaN を 最大 bin に振るため・一旦 0 で埋めてから nan_mask で上書き
    arr_filled = np.where(nan_mask, 0.0, arr)
    bin_idx = np.digitize(arr_filled, bins=edges[1:-1], right=True)
    # 念のため clip（[0, len(labels)-1] に収める）
    bin_idx = np.clip(bin_idx, 0, len(labels) - 1)
    out = np.array([labels[i] for i in bin_idx], dtype=object)
    # NaN → _MISSING_LABEL
    out[nan_mask] = _MISSING_LABEL
    return out


def _ninki_band(s: pd.Series) -> np.ndarray:
    """人気帯（ninki）を離散帯ラベルに変換（REVIEW HIGH#4・np.digitize・決定論的）。

    区分: ``NINKI_BAND_EDGES = [0, 3, 6, 9, inf]`` / ``NINKI_BAND_LABELS = ("1-3","4-6","7-9","10+")``。
    1-18 の ninki を4帯に集約し・生値分割による segment 希薄化を回避。NaN/None は ``"__MISSING__"``。
    """
    return _band_labels_from_edges(s, NINKI_BAND_EDGES, NINKI_BAND_LABELS)


def _odds_band(s: pd.Series) -> np.ndarray:
    """オッズ帯（fukuoddslower）を離散帯ラベルに変換（REVIEW HIGH#4・np.digitize・決定論的）。

    区分: ``ODDS_BAND_EDGES = [0, 2.9, 4.9, 9.9, inf]`` /
    ``ODDS_BAND_LABELS = ("1.0-2.9","3.0-4.9","5.0-9.9","10+")``。
    連続 float を4帯に集約。NaN/None は ``"__MISSING__"``。
    """
    return _band_labels_from_edges(s, ODDS_BAND_EDGES, ODDS_BAND_LABELS)


# ---------------------------------------------------------------------------
# evaluate_segment_axis — 1軸の segment 別 calibration curve + scalar
# ---------------------------------------------------------------------------


def evaluate_segment_axis(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    segment_values: np.ndarray | pd.Series,
    *,
    axis_name: str,
    n_bins: int = CALIBRATION_CURVE_BINS,
) -> dict[str, Any]:
    """1つの segment 軸で全 segment 値の calibration curve + scalar 指標を生成（D-12・RESEARCH Pattern 2）。

    各 segment 値でマスクを作成し・mask.sum() < ``CALIBRATION_CURVE_MIN_BIN_COUNT`` (30) の場合は
    スキップ（Pitfall 6・極小 segment ノイズ回避）。curve の binning は
    :func:`src.model.evaluator._compute_calibration_curve_bins` を呼出し・evaluator.py の binning 契約
    （uniform/10bins/MIN_BIN_COUNT=30）を再利用する（bit-identical・契約一元化・T-06-07）。

    Parameters
    ----------
    y_true : array-like
        バイナリ真ラベル (0/1)。
    y_pred : array-like
        予測確率・[0,1] 区間。
    segment_values : array-like
        各行の segment 値。文字列ラベル（banding 済み）・整数値（year/month/jyocd/entry_count）のいずれ可。
        NaN/None の行はスキップされるが・文字列 ``"__MISSING__"`` ラベルは1つの segment 値として扱う。
    axis_name : str
        segment 軸名（結果 dict の trace 名表示用・戻り値には含まれない）。
    n_bins : int
        bin 数（``CALIBRATION_CURVE_BINS=10`` がデフォルト・evaluator.py と一致）。

    Returns
    -------
    dict
        ``{str(seg_val): {"curve": {"mean_pred": list, "frac_pos": list, "count": list},
        "scalar": {"ece_quantile": float, "ece_uniform": float, "mce_guarded": float,
        "max_dev_guarded": float, "n_samples": int}}}``。
        ``np.ndarray`` は ``.tolist()`` で JSON シリアライズ可能に・``count`` は ``.astype(int).tolist()``。
        single-class や bin 構築不能の segment 値は scalar が NaN・curve は空リスト。
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    seg_arr = np.asarray(segment_values, dtype=object)

    # NaN/None segment 値を除外（文字列 "__MISSING__" は除外せず1つの segment 値として扱う）
    # numeric NaN のみ除外・None/np.nan を pd.isna で検出・ただし文字列は保持
    if len(y_true_arr) != len(y_pred_arr) or len(y_true_arr) != len(seg_arr):
        raise ValueError(
            f"evaluate_segment_axis: 長さ不一致 y_true={len(y_true_arr)}, "
            f"y_pred={len(y_pred_arr)}, segment_values={len(seg_arr)}"
        )

    # segment 値ごとに処理（np.ndarray は順序依存しないよう sorted(unique) で決定論化）
    # unique は object dtype に対しても機能する（文字列ラベル含む）
    # NaN を除外: pd.isna を要素ごと適用（文字列は False）
    nan_mask = np.array([pd.isna(v) for v in seg_arr], dtype=bool)
    valid_mask = ~nan_mask
    seg_valid = seg_arr[valid_mask]
    y_true_valid = y_true_arr[valid_mask]
    y_pred_valid = y_pred_arr[valid_mask]

    unique_vals = pd.unique(seg_valid)
    # 決定論的な順序で処理（数値は昇順・文字列は辞書順・混在は str 変換後 辞書順）
    try:
        sorted_vals = sorted(unique_vals, key=lambda v: (str(type(v).__name__), v))
    except TypeError:
        sorted_vals = sorted(unique_vals, key=lambda v: str(v))

    results: dict[str, Any] = {}
    for seg_val in sorted_vals:
        mask = seg_valid == seg_val
        n_samples = int(mask.sum())
        if n_samples < CALIBRATION_CURVE_MIN_BIN_COUNT:
            # 極小 segment はスキップ（Pitfall 6）
            continue
        y_t_seg = y_true_valid[mask]
        y_p_seg = y_pred_valid[mask]

        # binning 契約の再利用（uniform/n_bins・curve 生成）
        bins = _compute_calibration_curve_bins(y_t_seg, y_p_seg, strategy="uniform", n_bins=n_bins)

        mean_pred_list = bins["mean_pred"].tolist()
        frac_pos_list = bins["frac_pos"].tolist()
        count_list = bins["counts"].astype(int).tolist()

        # scalar 指標（evaluator.py のヘルパを再利用・bit-identical）
        # single-class や bin 構築不能の場合は NaN
        if len(np.unique(y_t_seg)) < 2:
            ece_q = float("nan")
            ece_u = float("nan")
            mce_g = float("nan")
            max_dev_g = float("nan")
        else:
            ece_q = float(_compute_ece(y_t_seg, y_p_seg, strategy="quantile", n_bins=n_bins))
            ece_u = float(_compute_ece(y_t_seg, y_p_seg, strategy="uniform", n_bins=n_bins))
            mce_g = float(
                _compute_mce(
                    y_t_seg,
                    y_p_seg,
                    strategy="uniform",
                    n_bins=n_bins,
                    min_bin_count=CALIBRATION_CURVE_MIN_BIN_COUNT,
                )
            )
            max_dev_g = float(_compute_calibration_max_dev_guarded(y_t_seg, y_p_seg))

        results[str(seg_val)] = {
            "curve": {
                "mean_pred": [float(x) for x in mean_pred_list],
                "frac_pos": [float(x) for x in frac_pos_list],
                "count": [int(x) for x in count_list],
            },
            "scalar": {
                "ece_quantile": ece_q,
                "ece_uniform": ece_u,
                "mce_guarded": mce_g,
                "max_dev_guarded": max_dev_g,
                "n_samples": n_samples,
            },
        }

    return results


# ---------------------------------------------------------------------------
# evaluate_all_segments — 6軸の segment 評価（欠損軸 WARN skip・C12 race_date 正規化内包）
# ---------------------------------------------------------------------------


def evaluate_all_segments(
    df: pd.DataFrame,
    *,
    p_col: str = "p_fukusho_hit",
    y_true_col: str = "fukusho_hit",
    axes: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """6軸の segment 別 calibration curve + scalar を生成（D-12・欠損軸 WARN skip）。

    Parameters
    ----------
    df : pd.DataFrame
        prediction + label JOIN 済み DataFrame。``p_col`` / ``y_true_col`` と各軸の segment 列
        （``race_date`` / ``jyocd`` / ``entry_count`` / ``ninki`` / ``fukuoddslower``）を含む前提。
    p_col : str
        予測確率列名（デフォルト ``"p_fukusho_hit"``）。
    y_true_col : str
        バイナリ真ラベル列名（デフォルト ``"fukusho_hit"``）。
    axes : dict | None
        segment 軸マッピング。None の場合は :data:`SEGMENT_AXES` の全6軸。

    Returns
    -------
    dict
        ``{axis_name: evaluate_segment_axis(...) の結果}``。欠損軸（列不存在）は空 dict + WARN ログ。

    Notes
    -----
    - **REVIEW C12 (race_date dtype 正規化):** year/month 軸は事前に
      ``pd.to_datetime(df["race_date"], errors="coerce")`` で datetime に正規化してから
      ``.dt.year`` / ``.dt.month`` を抽出する（Python date object / object dtype /
      datetime64[ns] のいずれでも AttributeError を起こさない）。
    - **REVIEW HIGH#4 (banding):** ninki 軸は :func:`_ninki_band`・odds_band 軸は :func:`_odds_band`
      で離散帯ラベルに変換してから :func:`evaluate_segment_axis` に渡す（生値でない）。
    """
    if axes is None:
        axes = SEGMENT_AXES

    if p_col not in df.columns:
        raise ValueError(f"evaluate_all_segments: p_col={p_col!r} が df に存在しない")
    if y_true_col not in df.columns:
        raise ValueError(f"evaluate_all_segments: y_true_col={y_true_col!r} が df に存在しない")

    y_true = df[y_true_col].to_numpy()
    y_pred = df[p_col].to_numpy(dtype=float)

    results: dict[str, dict[str, Any]] = {}
    for axis_name, src_col in axes.items():
        if src_col not in df.columns:
            warnings.warn(
                f"evaluate_all_segments: segment 軸 {axis_name!r} のソース列 "
                f"{src_col!r} が df に存在しないため WARN skip します（Pitfall 6・D-12）",
                stacklevel=2,
            )
            results[axis_name] = {}
            continue

        # REVIEW C12: year/month 軸は race_date を datetime 正規化してから .dt.year/.dt.month 抽出
        if axis_name in ("year", "month") and src_col == "race_date":
            ts = pd.to_datetime(df[src_col], errors="coerce")
            if axis_name == "year":
                segment_values = ts.dt.year
            else:
                segment_values = ts.dt.month
            seg_arr = segment_values.to_numpy()
        elif axis_name == "ninki":
            # REVIEW HIGH#4: banding 適用
            seg_arr = _ninki_band(df[src_col])
        elif axis_name == "odds_band":
            # REVIEW HIGH#4: banding 適用
            seg_arr = _odds_band(df[src_col])
        else:
            # jyocd / entry_count はそのまま（既に離散的）
            seg_arr = df[src_col].to_numpy()

        results[axis_name] = evaluate_segment_axis(y_true, y_pred, seg_arr, axis_name=axis_name)

    return results


# ---------------------------------------------------------------------------
# Task 2 で追加: render_segment_curves_html / write_segment_reports
# ---------------------------------------------------------------------------


def render_segment_curves_html(
    segment_results: dict[str, Any],
    *,
    axis_name: str,
    out_path: str | Path,
) -> Path:
    """segment 別 calibration curve を重ね描きした Plotly 静的 HTML を生成（D-10/D-11・RESEARCH Pattern 3）。

    **REVIEW C13 cycle-2 修正（directory 共有参照・N1 解消）:**
    ``fig.write_html(include_plotlyjs='directory')`` を使用。plotly は out_path と同じディレクトリに
    ``plotly.min.js`` を1ファイル生成し・HTML は ``<script src="plotly.min.js">`` で参照する
    （同一ディレクトリの相対参照・6 HTML が1つの plotly.min.js を共有）。
    これにより (i) 6 HTML × ~3.5MB 埋込の重複（~21MB 肥大）を解消・(ii) reports/ 全体の
    tracked ポリシーを維持（.gitignore 変更なし）・(iii) D-10「Plotly 静的 HTML」要件を維持。

    Parameters
    ----------
    segment_results : dict
        :func:`evaluate_segment_axis` の戻り値（``{str(seg_val): {"curve": ..., "scalar": ...}}``）。
    axis_name : str
        segment 軸名（HTML title・trace 名に使用）。
    out_path : str | Path
        出力 HTML パス（``reports/06-segments/{axis_name}.html``）。

    Returns
    -------
    Path
        ``out_path``（Path）。
    """
    fig = go.Figure()
    # 完全キャリブ対角線（perfect・dash・gray）
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            name="perfect",
            line=dict(dash="dash", color="gray"),
        )
    )
    # 各 segment 値の curve（決定論的順序のため sorted）
    for seg_val, data in sorted(segment_results.items()):
        curve = data.get("curve", {})
        mean_pred = curve.get("mean_pred", [])
        frac_pos = curve.get("frac_pos", [])
        count = curve.get("count", [])
        n_samples = data.get("scalar", {}).get("n_samples", 0)
        fig.add_trace(
            go.Scatter(
                x=mean_pred,
                y=frac_pos,
                mode="lines+markers",
                name=f"{axis_name}={seg_val} (n={n_samples})",
                customdata=np.array(count).reshape(-1, 1) if len(count) > 0 else None,
                hovertemplate=("pred=%{x:.3f}<br>obs=%{y:.3f}<br>n=%{customdata}<extra></extra>"),
            )
        )
    fig.update_layout(
        title=f"Calibration Curve by {axis_name}",
        xaxis_title="mean predicted probability",
        yaxis_title="observed fraction",
        width=900,
        height=600,
    )
    out_path_obj = Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)
    # REVIEW C13 cycle-2: include_plotlyjs='directory' で plotly.min.js 共有1ファイル参照
    # §19.1 再現性: div_id を axis 固有の決定論的値に固定（Plotly 既定の random uuid だと
    # 再生成ごとに HTML バイト列が変わり tracked 報告書が churn する・div_id 指定で byte-reproducible 化）
    fig.write_html(
        str(out_path_obj),
        include_plotlyjs="directory",
        full_html=True,
        div_id=f"segment-{axis_name}",
    )
    return out_path_obj


def write_segment_reports(
    all_segment_results: dict[str, dict[str, Any]],
    *,
    out_dir: str | Path = "reports/06-segments",
) -> dict[str, Any]:
    """6軸の segment 評価結果を JSON + Plotly HTML + 共有 plotly.min.js として出力（D-10/D-11）。

    Parameters
    ----------
    all_segment_results : dict
        :func:`evaluate_all_segments` の戻り値（``{axis_name: {segment_value: {curve, scalar}}}``）。
    out_dir : str | Path
        出力ディレクトリ（デフォルト ``reports/06-segments``）。

    Returns
    -------
    dict
        ``{axis_name: {"json": Path, "html": Path}}`` + ``{"plotly_min_js": Path}``。
        生成ファイルパス（監査性）。

    Notes
    -----
    - JSON は ``json.dumps(sort_keys=True, ensure_ascii=False)`` + :func:`_atomic_write_text` で
      byte-reproducible（evaluator.write_eval_report パターン踏襲・Shared Pattern 2）。
    - HTML は :func:`render_segment_curves_html` で ``include_plotlyjs='directory'`` を使用。
      初回呼出で ``out_dir/plotly.min.js`` が生成され・2回目以降は同一ファイルが再利用される
      （plotly の標準挙動・idempotent）。
    """
    out_dir_obj = Path(out_dir)
    out_dir_obj.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Any] = {}
    plotly_min_js_path = out_dir_obj / "plotly.min.js"

    for axis_name, segment_results in all_segment_results.items():
        # JSON（byte-reproducible・sort_keys=True・RFC 8259 strict）
        # segment scalar はサンプル不足で NaN になる場合がある（odds_band.__MISSING__ 等）。
        # NaN は strict JSON 仕様違反のため null に正規化（run_evaluation._sanitize_nan_to_null と同一契約）。
        json_payload_dict = {
            "axis_name": axis_name,
            "segments": [
                {
                    "segment_value": seg_val,
                    "curve": _sanitize_nan_to_null(data.get("curve", {})),
                    "scalar": _sanitize_nan_to_null(data.get("scalar", {})),
                }
                for seg_val, data in sorted(segment_results.items())
            ],
        }
        json_payload = json.dumps(
            json_payload_dict,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,  # 変換漏れがあれば fail-loud で検出
        )
        json_path = out_dir_obj / f"{axis_name}.json"
        _atomic_write_text(json_path, json_payload)

        # HTML（Plotly・include_plotlyjs='directory'）
        html_path = render_segment_curves_html(
            segment_results,
            axis_name=axis_name,
            out_path=out_dir_obj / f"{axis_name}.html",
        )

        paths[axis_name] = {"json": json_path, "html": html_path}

    paths["plotly_min_js"] = plotly_min_js_path
    return paths


__all__ = [
    "SEGMENT_AXES",
    "NINKI_BAND_EDGES",
    "NINKI_BAND_LABELS",
    "ODDS_BAND_EDGES",
    "ODDS_BAND_LABELS",
    "_ninki_band",
    "_odds_band",
    "evaluate_segment_axis",
    "evaluate_all_segments",
    "render_segment_curves_html",
    "write_segment_reports",
]
