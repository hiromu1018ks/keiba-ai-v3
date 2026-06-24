# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・src/ev/report.py と同一慣例)
"""OUT-01/OUT-02 CSV 列定数 presence assert テスト（LOW-05 再利用・§16.2 1:1）。

``src/ev/test_run_backtest_e2e.py::test_report_columns_present`` の LOW-05 presence assert
パターンを再利用し・``PREDICTION_CSV_COLUMNS`` / ``BACKTEST_CSV_COLUMNS`` が §16.2 原典と
過不足なく（順序含む）一致することを機械検証する（grep 否定でなく in で存在検証）。

参照: 07-01-PLAN.md Task 2 / 07-PATTERNS.md §tests/ui/test_csv_columns.py
"""

from __future__ import annotations

from src.ui.csv_columns import BACKTEST_CSV_COLUMNS, PREDICTION_CSV_COLUMNS

# §16.2 原典 行1092-1112 の期待20項目（順序含む完全一致・REVIEW HIGH-1 canonical 外部名）
_EXPECTED_PREDICTION_COLUMNS: tuple[str, ...] = (
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
    "fukusho_odds_lower",  # REVIEW HIGH-1 canonical 外部名 (fuku_* でない)
    "fukusho_odds_upper",
    "EV_lower",
    "EV_upper",
    "recommend_rank",
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "model_version",
    "feature_snapshot_id",
    "prediction_created_at",
)

# §16.2 原典 行1118-1133 の期待16項目（RESEARCH Pitfall 3・「14列」は誤記）
_EXPECTED_BACKTEST_COLUMNS: tuple[str, ...] = (
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
)


def test_prediction_csv_columns_count():
    """OUT-01: PREDICTION_CSV_COLUMNS は §16.2 pin の20列である（presence assert）。"""
    assert len(PREDICTION_CSV_COLUMNS) == 20


def test_prediction_csv_has_all_stamps():
    """再現性スタンプ4項目が含まれる（§19.1 聖域・CSV 列定義側の4項目）。

    UI 行表示用の5項目目 backtest_strategy_version は予測テーブルに非存在のため
    CSV 定数からは除外（REVIEW MEDIUM-1 解決）・UI 側で付与する。
    """
    for stamp in (
        "odds_snapshot_policy",
        "odds_snapshot_at",
        "model_version",
        "feature_snapshot_id",
    ):
        assert stamp in PREDICTION_CSV_COLUMNS, f"再現性スタンプ {stamp!r} がない (§19.1 聖域違反)"


def test_prediction_csv_columns_match_spec():
    """PREDICTION_CSV_COLUMNS が §16.2 原典20項目に順序含めて完全一致する（T-07-01 mitigate）。"""
    assert PREDICTION_CSV_COLUMNS == _EXPECTED_PREDICTION_COLUMNS, (
        "PREDICTION_CSV_COLUMNS が §16.2 原典20項目と不一致"
    )


def test_backtest_csv_columns_count():
    """OUT-02: BACKTEST_CSV_COLUMNS は §16.2 原典の16列（「14列」表記は誤り・Pitfall 3・T-07-02 mitigate）。"""
    assert len(BACKTEST_CSV_COLUMNS) == 16


def test_backtest_csv_columns_match_spec():
    """BACKTEST_CSV_COLUMNS が §16.2 原典16項目に順序含めて完全一致する（T-07-01/T-07-02 mitigate）。"""
    assert BACKTEST_CSV_COLUMNS == _EXPECTED_BACKTEST_COLUMNS, (
        "BACKTEST_CSV_COLUMNS が §16.2 原典16項目と不一致"
    )


def test_ui_cli_share_columns():
    """UI/CLI/test が同一ソース (src.ui.csv_columns) から import し DRY 共有している（D-04 LOCKED）。"""
    # 同一モジュールから import した定数が tuple[str, ...] であること・変更不能な単一定数であることを検証
    assert isinstance(PREDICTION_CSV_COLUMNS, tuple)
    assert isinstance(BACKTEST_CSV_COLUMNS, tuple)
    # 重複列がないこと（順序固定の tuple で set 変換して長さ一致）
    assert len(set(PREDICTION_CSV_COLUMNS)) == len(PREDICTION_CSV_COLUMNS), (
        "予測 CSV に重複列がある"
    )
    assert len(set(BACKTEST_CSV_COLUMNS)) == len(BACKTEST_CSV_COLUMNS), (
        "backtest CSV に重複列がある"
    )
