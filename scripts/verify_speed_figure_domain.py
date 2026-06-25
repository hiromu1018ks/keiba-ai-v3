#!/usr/bin/env python3
# ruff: noqa: E501  (長い docstring / SQL リテラルを保持するため行長は緩和)
"""Phase 9 SC#5 ドメイン整合性可視化スクリプト（snapshot 読み込み・DB 不要・run_feature_build.py で事前生成が必要）.

本スクリプトは ``scripts/run_feature_build.py`` が生成した Parquet snapshot を
``load_feature_matrix(snapshot_id)`` で読み込み・その過去集約値
``rolling_speed_figure_mean_5`` 分布を Plotly HTML で可視化し・以下のドメイン整合性を
目視確認する（D-08）:

  1. 同一馬の連続走 ``rolling_speed_figure_mean_5`` 推移（安定性・連続走で大きくブレない）
  2. ``class_code_normalized`` 毎の ``rolling_speed_figure_mean_5`` ボックスプロット
     （クラス昇格で指数上昇・降格で下降の単調性・D-08）
  3. ``rolling_speed_figure_mean_5`` 全体ヒストグラム（極端な外れ値がないこと・
     Pitfall 4・0-100 程度に収まる）

**事前要件（producer/consumer 分離）:** 本スクリプトは DB にアクセスせず・既存の
Parquet snapshot のみを読む（秒単位）。事前に producer 側で snapshot を生成しておくこと::

    uv run python scripts/run_feature_build.py \\
        --snapshot-id 20260625-1a-speedfigure-v1 \\
        --label-version v1 --fa-version 0.4.0

snapshot が未生成の場合は ``load_feature_matrix`` が ``FileNotFoundError`` を raise する
（``run_feature_build.py`` を先に実行するよう明示的に表面化・silent fallback しない）。

リーク防止上の制約（前修正 ee49e32 と同一・維持）: ``feature_matrix`` には生 ``speed_figure``
列は **構造上存在しない**。snapshot producer（``scripts/run_feature_build.py`` 経由の
feature 構築）は target race の **過去走 (history)** にのみ
生 ``speed_figure``（= 当日レースの指数・予測時点では未来情報 = リーク）を付与し
（src/features/builder.py Step 5b・compute_speed_figure_for_history）・``build_rolling_features``
がそれを過去集約値 ``rolling_speed_figure_*`` (6 feature・P02 登録済み) に変換して
``feature_matrix`` に merge する（未来情報が混入すると §13 PIT 不変量違反）。本スクリプトは
``rolling_speed_figure_mean_5``（過去5走平均・馬の最近能力軸）を domain-integrity proxy
として可視化する（同一馬安定性・クラス単調性 D-08・外れ値/points_per_second 健全性は
5走平均でも意味的に有効）。

cross-reference: .planning/phases/09-speed-figure-foundation/09-VALIDATION.md (SC#5・manual-only).
cross-reference: scripts/run_feature_build.py (snapshot producer・本スクリプトの前提).
cross-reference: src/model/data.py load_feature_matrix (SC#1 聖域・DB 引数を持たない・H1-a).
cross-reference: src/model/segment_eval.py (include_plotlyjs='directory' + div_id 固定 idiom・L444-452).

SAFE-01: speed_figure は odds-free・本スクリプトも odds/ninki/fukuodds proxy を一切
扱わない（診断層のみ・市場情報 proxy 除外）。出力 HTML/JSON に市場情報 proxy
列は含まれない。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# scripts/ から src.* を import するためリポジトリルートを sys.path に追加
# （scripts/run_evaluation.py L65-68 と同一 idiom）
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402

from src.model.data import load_feature_matrix  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("verify_speed_figure_domain")

# ---------------------------------------------------------------------------
# SC#5 可視化対象列: rolling_speed_figure_mean_5（過去5走平均・P02 登録済み）
# ---------------------------------------------------------------------------
# feature_matrix（target race の observation 行）には生 ``speed_figure`` 列は構造上
# 存在しない（src/features/builder.py Step 5b が history 側にのみ付与し・
# build_rolling_features が rolling_speed_figure_* 6 feature に変換して feature_matrix に
# merge する・生 speed_figure は当日の予測時点で未来情報 = §13 PIT リーク防止で混入不可）。
# SC#5 のドメイン整合性チェック（同一馬安定性・クラス単調性 D-08・外れ値/points_per_second
# 健全性）は過去5走平均でも馬の最近能力軸として意味的に有効なため・本定数を proxy に使う。
_SPEED_FIGURE_PLOT_COL = "rolling_speed_figure_mean_5"

# ---------------------------------------------------------------------------
# Plotly は重い依存なので main で遅延 import（スクリプト不使用時の import コスト回避）
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数をパースする。

    --snapshot-id: 速度指数 snapshot の feature_snapshot_id
        （P03 SUMMARY 候補・default: 20260625-1a-speedfigure-v1）
    --out-dir: HTML/JSON 出力ディレクトリ（default: reports）
    --sample-horses: 同一馬推移プロットのサンプル馬数（default: 20）
    """
    parser = argparse.ArgumentParser(
        description="SC#5 ドメイン整合性可視化（speed_figure distribution・D-08・snapshot 読込）"
    )
    parser.add_argument(
        "--snapshot-id",
        default="20260625-1a-speedfigure-v1",
        help="feature_snapshot_id（default: 20260625-1a-speedfigure-v1・P03 候補）",
    )
    parser.add_argument(
        "--out-dir",
        default="reports",
        help="HTML/JSON 出力ディレクトリ（default: reports）",
    )
    parser.add_argument(
        "--sample-horses",
        type=int,
        default=20,
        help="同一馬推移プロットのサンプル馬数（default: 20）",
    )
    return parser.parse_args(argv)


def _fetch_feature_matrix(snapshot_id: str) -> pd.DataFrame:
    """load_feature_matrix で Parquet snapshot を読込む（DB 不要・秒単位・SC#1 聖域）。

    ``scripts/run_feature_build.py`` が生成した ``snapshots/feature_matrix_{snapshot_id}.parquet``
    を ``src.model.data.load_feature_matrix(snapshot_id)`` で読込む。DB 接続は一切行わない
    （live-DB 再構築を廃止・producer/consumer 分離）。snapshot が未生成の場合は
    ``load_feature_matrix`` が ``FileNotFoundError`` を raise する（silent fallback 禁止・
    producer 側 ``run_feature_build.py`` の事前実行を明示的に要求）。

    注意（前修正 ee49e32 と同一・維持）: feature_matrix には生 ``speed_figure`` 列は
    存在しない（target race の指数は予測時点で未来情報 = §13 PIT リーク防止で混入不可・
    builder Step 5b は history 側にのみ付与し rolling_speed_figure_* 過去集約値のみ
    feature_matrix に残る）。本スクリプトは ``_SPEED_FIGURE_PLOT_COL``
    (rolling_speed_figure_mean_5) を可視化対象とする。
    """
    feature_matrix = load_feature_matrix(snapshot_id)
    logger.info(
        "load_feature_matrix: snapshot_id=%s rows=%d cols=%d",
        snapshot_id,
        len(feature_matrix),
        feature_matrix.shape[1],
    )
    return feature_matrix


def _build_trajectory_plot(
    feature_matrix: pd.DataFrame, sample_horses: int
) -> Any:
    """プロット1: 同一馬の連続走 rolling_speed_figure_mean_5 推移ラインプロット（安定性確認）。

    各馬1ライン・連続走で大きくブレしないことを目視。``_SPEED_FIGURE_PLOT_COL``
    (rolling_speed_figure_mean_5) は target race 時点での過去5走平均能力軸。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # 可視化対象列の存在確認（feature_matrix に生 speed_figure は非存在・未来情報 = リーク）
    if _SPEED_FIGURE_PLOT_COL not in feature_matrix.columns:
        raise ValueError(
            f"feature_matrix に '{_SPEED_FIGURE_PLOT_COL}' 列がない・snapshot 生成不正の疑い"
        )
    # kettonum / race_date が無ければ推移プロット不能
    required = ("kettonum", "race_date", _SPEED_FIGURE_PLOT_COL)
    missing = [c for c in required if c not in feature_matrix.columns]
    if missing:
        raise ValueError(f"feature_matrix に必須列が欠損: {missing}")

    df = feature_matrix.dropna(subset=[_SPEED_FIGURE_PLOT_COL]).copy()
    df["race_date_dt"] = pd.to_datetime(df["race_date"], errors="coerce")
    df = df.dropna(subset=["race_date_dt"]).sort_values(["kettonum", "race_date_dt"])

    # サンプル馬を選出：出走数上位 sample_horses 件（推移が見やすい・十分なレース数を持つ馬）
    start_counts = df.groupby("kettonum").size().sort_values(ascending=False)
    top_horses = start_counts.head(sample_horses).index.tolist()
    df_sample = df[df["kettonum"].isin(top_horses)]

    fig = make_subplots(
        rows=1,
        cols=1,
        subplot_titles=(
            f"同一馬連続走 {_SPEED_FIGURE_PLOT_COL} 推移（上位 {len(top_horses)} 馬・安定性確認）",
        ),
    )
    for horse_id in top_horses:
        horse_df = df_sample[df_sample["kettonum"] == horse_id]
        fig.add_trace(
            go.Scatter(
                x=horse_df["race_date_dt"],
                y=horse_df[_SPEED_FIGURE_PLOT_COL],
                mode="lines+markers",
                name=f"kettonum={horse_id}",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
    fig.update_xaxes(title_text="race_date", row=1, col=1)
    fig.update_yaxes(
        title_text=f"{_SPEED_FIGURE_PLOT_COL}（過去5走平均）", row=1, col=1
    )
    fig.update_layout(
        title=f"SC#5 プロット1: 同一馬連続走 {_SPEED_FIGURE_PLOT_COL} 安定性",
        width=1100,
        height=600,
    )
    return fig


def _build_class_box_plot(feature_matrix: pd.DataFrame) -> Any:
    """プロット2: class_code_normalized 毎の rolling_speed_figure_mean_5 ボックスプロット（単調性確認・D-08）。

    クラス昇格で過去5走平均能力が上昇・降格で下降の単調性を目視。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if "class_code_normalized" not in feature_matrix.columns:
        raise ValueError(
            "feature_matrix に 'class_code_normalized' 列がない・snapshot 生成不正の疑い"
        )
    df = feature_matrix.dropna(
        subset=[_SPEED_FIGURE_PLOT_COL, "class_code_normalized"]
    ).copy()

    # class_code_normalized 昇順で box プロット
    classes = sorted(df["class_code_normalized"].dropna().unique().tolist())
    fig = make_subplots(
        rows=1,
        cols=1,
        subplot_titles=(
            f"class_code_normalized 別 {_SPEED_FIGURE_PLOT_COL} 分布（D-08 単調性）",
        ),
    )
    for cls in classes:
        cls_df = df[df["class_code_normalized"] == cls]
        fig.add_trace(
            go.Box(
                y=cls_df[_SPEED_FIGURE_PLOT_COL],
                name=str(cls),
                boxmean="sd",
            ),
            row=1,
            col=1,
        )
    fig.update_xaxes(title_text="class_code_normalized", row=1, col=1)
    fig.update_yaxes(
        title_text=f"{_SPEED_FIGURE_PLOT_COL}（過去5走平均）", row=1, col=1
    )
    fig.update_layout(
        title=f"SC#5 プロット2: class_code_normalized × {_SPEED_FIGURE_PLOT_COL} 単調性（D-08）",
        width=1100,
        height=600,
        showlegend=False,
    )
    return fig


def _build_histogram(feature_matrix: pd.DataFrame) -> Any:
    """プロット3: rolling_speed_figure_mean_5 全体ヒストグラム（外れ値確認・Pitfall 4）。

    極端な外れ値（±1000 等・Pitfall 4）がないこと・分布がドメイン整合的
    （0-100 程度に収まる）ことを目視。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = feature_matrix.dropna(subset=[_SPEED_FIGURE_PLOT_COL]).copy()
    fig = make_subplots(
        rows=1,
        cols=1,
        subplot_titles=(
            f"{_SPEED_FIGURE_PLOT_COL} 全体分布（外れ値確認・Pitfall 4）",
        ),
    )
    fig.add_trace(
        go.Histogram(
            x=df[_SPEED_FIGURE_PLOT_COL],
            nbinsx=80,
            name=_SPEED_FIGURE_PLOT_COL,
        ),
        row=1,
        col=1,
    )
    fig.update_xaxes(title_text=_SPEED_FIGURE_PLOT_COL, row=1, col=1)
    fig.update_yaxes(title_text="count", row=1, col=1)
    fig.update_layout(
        title=f"SC#5 プロット3: {_SPEED_FIGURE_PLOT_COL} ヒストグラム（外れ値確認）",
        width=1100,
        height=600,
        showlegend=False,
    )
    return fig


def _write_combined_html(
    figs: list[Any], out_path: Path, div_id: str = "speed-figure-domain"
) -> None:
    """3プロットを1 HTML に統合出力（include_plotlyjs='directory'・div_id 固定・M3）。

    REVIEW C13 + M3: ``include_plotlyjs='directory'`` で plotly.min.js 共有1ファイル参照・
    ``div_id`` を固定文字列で指定して Plotly 既定の random HTML ID を回避・byte-reproducible
    HTML を保証（src/model/segment_eval.py L444-452 idiom と同一）。
    """
    from plotly.subplots import make_subplots

    # 3プロットを縦に並べた統合 figure を構築（簡易策: 最初の fig を base に残りを add_trace で
    # 積むのは複雑なので・各 fig を個別 HTML に書出した後・統合 HTML を手構築する）。
    # ここでは各プロットを独立 HTML 出力し・最終的な統合 HTML は最初の fig の full_html を
    # base にして残りを追記する方式（plotly v2 の make_subplots 3行1列 でより綺麗にできるが・
    # 各プロットが既に独立 legend/layout を持つため個別出力+インデックス HTML が見やすい）。
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 簡潔かつ byte-reproducible な実装: 3プロットを縦積みの make_subplots で統合
    combined = make_subplots(
        rows=3,
        cols=1,
        subplot_titles=(
            f"プロット1: 同一馬連続走 {_SPEED_FIGURE_PLOT_COL} 安定性",
            f"プロット2: class_code_normalized × {_SPEED_FIGURE_PLOT_COL} 単調性（D-08）",
            f"プロット3: {_SPEED_FIGURE_PLOT_COL} ヒストグラム（外れ値確認）",
        ),
        vertical_spacing=0.08,
    )
    # 各独立 fig の traces を combined に転写（row を 1,2,3 に振り分け）
    for row_idx, fig in enumerate(figs, start=1):
        for trace in fig.data:
            combined.add_trace(trace, row=row_idx, col=1)
        # 軸タイトル等の layout を転写（xaxis/yaxis タイトル）
        xaxis_key = f"xaxis{row_idx if row_idx > 1 else ''}"
        yaxis_key = f"yaxis{row_idx if row_idx > 1 else ''}"
        if fig.layout.xaxis.title.text:
            combined.update_layout(**{xaxis_key: {"title": fig.layout.xaxis.title.text}})
        if fig.layout.yaxis.title.text:
            combined.update_layout(**{yaxis_key: {"title": fig.layout.yaxis.title.text}})

    combined.update_layout(
        title="Phase 9 SC#5 ドメイン整合性可視化（speed_figure distribution）",
        height=1800,
        width=1100,
        showlegend=False,
    )

    # REVIEW C13 + M3: include_plotlyjs='directory' + div_id 固定で byte-reproducible
    combined.write_html(
        str(out_path),
        include_plotlyjs="directory",
        full_html=True,
        auto_open=False,
        div_id=div_id,
    )
    logger.info("SC#5 HTML 出力: %s (div_id=%s)", out_path, div_id)


def _write_stats_json(
    feature_matrix: pd.DataFrame, out_path: Path, snapshot_id: str
) -> dict[str, Any]:
    """rolling_speed_figure_mean_5 統計量を JSON 出力（HTML 本体とは別・byte-reproducible を保つため時刻は JSON のみ）。

    戻り値: JSON に書き出した stats dict（呼出元で stdout 表示に再利用）。
    """
    if _SPEED_FIGURE_PLOT_COL not in feature_matrix.columns:
        raise ValueError(
            f"feature_matrix に '{_SPEED_FIGURE_PLOT_COL}' 列がない"
        )
    sf = feature_matrix[_SPEED_FIGURE_PLOT_COL].dropna()
    stats: dict[str, Any] = {
        "feature_snapshot_id": snapshot_id,
        "row_count": int(len(feature_matrix)),
        "rolling_speed_figure_mean_5_non_null_count": int(len(sf)),
        "rolling_speed_figure_mean_5_min": float(sf.min()) if len(sf) > 0 else None,
        "rolling_speed_figure_mean_5_max": float(sf.max()) if len(sf) > 0 else None,
        "rolling_speed_figure_mean_5_mean": float(sf.mean()) if len(sf) > 0 else None,
        "rolling_speed_figure_mean_5_std": float(sf.std()) if len(sf) > 0 else None,
        "rolling_speed_figure_mean_5_median": float(sf.median()) if len(sf) > 0 else None,
        "outlier_check": {
            "abs_max_below_1000": bool(sf.abs().max() < 1000.0) if len(sf) > 0 else True,
            "domain_range_note": (
                f"{_SPEED_FIGURE_PLOT_COL} は 0-100 程度に収まることが期待"
                "（過去5走平均・Pitfall 4・外れ値 ±1000 は points_per_seconds 不正の疑い）"
            ),
        },
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("SC#5 stats JSON 出力: %s", out_path)
    return stats


def main(argv: list[str] | None = None) -> int:
    """SC#5 ドメイン整合性可視化のエントリポイント（snapshot 読込・DB 不要）。

    戻り: 0(成功) / 非0(失敗・FileNotFoundError/RuntimeError 伝搬）。
    """
    args = parse_args(argv)

    logger.info(
        "config: snapshot_id=%s out_dir=%s sample_horses=%d (DB-free・snapshot 読込)",
        args.snapshot_id,
        args.out_dir,
        args.sample_horses,
    )

    # snapshot を load_feature_matrix で読込（DB 不要・SC#1 聖域・秒単位）。
    # snapshot 未生成の場合は load_feature_matrix が FileNotFoundError を raise する
    # （producer 側 run_feature_build.py の事前実行を明示的に要求・silent fallback 禁止）。
    feature_matrix = _fetch_feature_matrix(args.snapshot_id)

    # SAFE-01: speed_figure は odds-free・本スクリプトも odds-free を維持（診断層のみ）
    # odds/ninki/fukuodds proxy 列は SELECT/特徴量化しない
    logger.info("SAFE-01: speed_figure は odds-free・本スクリプトも odds-free を維持")

    out_dir = Path(args.out_dir)
    html_path = out_dir / "09-speed-figure-domain.html"
    json_path = out_dir / "09-speed-figure-domain.json"

    # プロット構築
    fig1 = _build_trajectory_plot(feature_matrix, args.sample_horses)
    fig2 = _build_class_box_plot(feature_matrix)
    fig3 = _build_histogram(feature_matrix)

    # 統合 HTML 出力（M3: include_plotlyjs='directory' + div_id 固定・byte-reproducible）
    _write_combined_html(
        [fig1, fig2, fig3], html_path, div_id="speed-figure-domain"
    )

    # 統計量 JSON 出力（HTML 本体とは別・byte-reproducible を保つため時刻は JSON のみ）
    stats = _write_stats_json(feature_matrix, json_path, args.snapshot_id)

    # stdout に目視確認手順を表示（manual-only verification・VALIDATION.md 参照）
    print(
        f"SC#5 ドメイン整合性: {html_path} を開いて目視確認 "
        f"(同一馬安定・クラス単調・外れ値なし・target col={_SPEED_FIGURE_PLOT_COL})\n"
        f"  stats: min={stats['rolling_speed_figure_mean_5_min']} "
        f"max={stats['rolling_speed_figure_mean_5_max']} "
        f"mean={stats['rolling_speed_figure_mean_5_mean']:.4f} "
        f"std={stats['rolling_speed_figure_mean_5_std']:.4f} "
        f"median={stats['rolling_speed_figure_mean_5_median']}\n"
        f"  outlier_check: abs_max_below_1000={stats['outlier_check']['abs_max_below_1000']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
