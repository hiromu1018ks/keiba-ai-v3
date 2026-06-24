# ruff: noqa: E501  (列定義 docstring が長いため行長は緩和・実装は tuple 定数のみ)
"""Phase 7 OUT-01/OUT-02 CSV 列定数（D-04 LOCKED・§16.2 pin・UI/CLI/test で DRY 共有）.

本モジュールは UI (Streamlit) と CLI (``scripts/run_export_*.py``) と test が同一の
列定義を import し・列揺れを構造的に排除する (D-04 LOCKED・UI-SPEC CSV Export Contract)。
``src/ev/report.py::REPORT_COLUMNS`` の LOW-05 presence assert パターンと同思想・
``tuple[str, ...]`` で固定順序を定義する。

**odds 列名 canonical 方針 (REVIEW HIGH-1 解決):**

外部公開（CSV ヘッダ・UI 表示）は ``fukusho_odds_lower`` / ``fukusho_odds_upper`` を
canonical とする。loaders 内部の JODDS snapshot 由来 DataFrame 列名
(``src/ev/odds_snapshot.py::select_odds_snapshot`` が返す ``fuku_odds_lower`` /
``fuku_odds_upper``) は ``normalize_prediction_export_columns(df)`` helper で外部名に
rename してから CSV/UI に渡す (rename map: ``{"fuku_odds_lower": "fukusho_odds_lower",
"fuku_odds_upper": "fukusho_odds_upper"}``)。

**odds_snapshot_at 取得元 (REVIEW MEDIUM-2 解決):**

``odds_snapshot_at`` は **JODDS snapshot の ``happyo_datetime``** (選択 snapshot の
発表日時 Timestamp・``src/ev/odds_snapshot.py::select_odds_snapshot`` 戻り値) から取得する
(07-02 loaders で取得・``merge_asof(direction='backward')`` で未来リーク構造的不可・D-02)。
backtest テーブル JOIN からは取得しない（backtest テーブル ``BACKTEST_COLUMNS`` に odds 値
カラム ``fuku_odds_lower``/``fuku_odds_upper`` が不存在のため構造的不可能・07-02 revision で確定）。

**prediction_created_at:** ``prediction.fukusho_prediction.as_of_datetime`` を代用
（予測生成時点タイムスタンプ・``src/db/schema.py`` L65）。

**列数 (W4 errata・RESEARCH Pitfall 3):**

- PREDICTION_CSV_COLUMNS = 20列（§16.2 原典 行1092-1112 と 1:1）
- BACKTEST_CSV_COLUMNS = 16列（§16.2 原典 行1118-1133・CONTEXT D-04 の「14列」は誤記・
  要件§16.2 原典優先・CLAUDE.md「本ファイルと要件に乖離がある場合は要件定義書を優先する」）

参照: 07-01-PLAN.md must_haves / 07-UI-SPEC.md §CSV Export Contract /
      src/db/backtest_load.py::BACKTEST_COLUMNS (DB 列順の正) /
      src/ev/report.py::REPORT_COLUMNS (tuple 定数の analog)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# ---------------------------------------------------------------------------
# OUT-01: 予測CSV 列定数（§16.2 pin・20列・原典 行1092-1112 と 1:1）
# ---------------------------------------------------------------------------
# 順序は §16.2 原典どおり。列名に日本語（競馬場/レース番号/枠番/馬番）を含むのは原典どおり・OUT-01 pin。
# fukusho_odds_lower/fukusho_odds_upper は REVIEW HIGH-1 canonical 外部名（fuku_* でない）。
PREDICTION_CSV_COLUMNS: tuple[str, ...] = (
    "race_id",
    "race_date",
    "race_start_datetime",
    "競馬場",
    "レース番号",
    "horse_id",
    "horse_name",
    "枠番",
    "馬番",
    "p_fukusho_hit",
    "fukusho_odds_lower",
    "fukusho_odds_upper",
    "EV_lower",
    "EV_upper",
    "recommend_rank",
    # §19.1 再現性聖域スタンプ（4項目+prediction_created_at=5項目）
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "model_version",
    "feature_snapshot_id",
    "prediction_created_at",
)  # 20列

# ---------------------------------------------------------------------------
# OUT-02: backtest CSV 列定数（§16.2 原典 行1118-1133・RESEARCH Pitfall 3 で16列確定）
# ---------------------------------------------------------------------------
# CONTEXT.md D-04 の「14列」は初期ドラフト由来の誤記。CLAUDE.md「要件優先」で 16 を正とする。
# UI 行表示用の5項目（odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/
#   backtest_strategy_version）と使い分けるため backtest_strategy_version は本 CSV にも含まれる
#   （backtest テーブルに非存在の列は CSV 定数からは除外し UI 側で付与、とする方針に対し
#   backtest_strategy_version は BACKTEST_COLUMNS L80 に存在するため CSV に含めてよい）。
BACKTEST_CSV_COLUMNS: tuple[str, ...] = (
    "backtest_id",
    "backtest_strategy_version",
    "train_period",
    "validation_period",
    "odds_snapshot_policy",
    "race_id",
    "horse_id",
    "selected_flag",
    "stake",
    "refund_flag",
    "payout_amount",
    "profit",
    "fukusho_hit_validated",
    "recommend_rank",
    "EV_lower",
    "EV_upper",
)  # 16列（「14列」表記は誤り・RESEARCH Pitfall 3）

# UI 行表示用 再現性スタンプ5項目（§19.1 聖域）。
# 予測テーブル由来4項目 + backtest_strategy_version（UI 側で付与分も含めた完全5項目）。
# この定数は UI 行表示で使い・CSV 列定義とは独立（REVIEW MEDIUM-1 解決）。
REPRODUCIBILITY_STAMPS: tuple[str, ...] = (
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "model_version",
    "feature_snapshot_id",
    "backtest_strategy_version",
)  # 5項目（§19.1 聖域）

# JODDS snapshot 内部列名 → 外部 canonical 名 の rename map（REVIEW HIGH-1）
_ODDS_RENAME_MAP: dict[str, str] = {
    "fuku_odds_lower": "fukusho_odds_lower",
    "fuku_odds_upper": "fukusho_odds_upper",
}


def normalize_prediction_export_columns(df: pd.DataFrame) -> pd.DataFrame:
    """JODDS snapshot 内部列名 (fuku_odds_*) を外部 canonical 名 (fukusho_odds_*) に rename する。

    loaders が ``src/ev/odds_snapshot.py::select_odds_snapshot`` 戻り値を予測 DataFrame に結合した後・
    CSV/UI に渡す前に本 helper を呼出して列名を canonical 化する (REVIEW HIGH-1 解決)。

    ``fuku_odds_lower`` / ``fuku_odds_upper`` が DataFrame に存在しない場合は何もしない
    （odds snapshot が未結合の段階での呼出を許容・no-op）。
    """
    return df.rename(columns={k: v for k, v in _ODDS_RENAME_MAP.items() if k in df.columns})


__all__ = [
    "PREDICTION_CSV_COLUMNS",
    "BACKTEST_CSV_COLUMNS",
    "REPRODUCIBILITY_STAMPS",
    "normalize_prediction_export_columns",
]
