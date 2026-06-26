# ruff: noqa: E501
"""scripts/run_phase10_evaluation.py の unit test.

CR-04 (10-08 gap-closure): _compute_w2_diagnostics が必須列 missing で WARNING skip でなく
RuntimeError を raise することを検証する（§11.2 聖域・W-2 証跡履行の構造的ブロック）。
WR-02 (10-08 gap-closure): main が make_pool(settings, role='readonly', configure=_configure_statement_timeout)
で pool を構築することを検証する。

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし・pure unit test）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_run_phase10_evaluation_module():
    """scripts/run_phase10_evaluation.py をモジュールとして動的 import する.

    scripts/ は package でないため importlib.util を使う。
    """
    module_path = _REPO_ROOT / "scripts" / "run_phase10_evaluation.py"
    spec = importlib.util.spec_from_file_location(
        "run_phase10_evaluation", module_path
    )
    assert spec is not None and spec.loader is not None, (
        "run_phase10_evaluation.py の module spec が取得できない"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_phase10_evaluation"] = module
    spec.loader.exec_module(module)
    return module


def test_cr04_w2_diagnostics_raises_runtime_error_on_missing_required_columns(tmp_path) -> None:
    """CR-04 (10-08 gap-closure): ``_compute_w2_diagnostics`` が必須列
    (rolling_speed_figure_mean_5 / rolling_field_strength_mean_mean_5 等) 欠損時に
    RuntimeError を raise する（WARNING skip でない・§11.2 聖域・W-2 証跡履行の構造的ブロック）.
    """
    mod = _load_run_phase10_evaluation_module()

    # 必須列 (rolling_speed_figure_mean_5 / rolling_field_strength_mean_mean_5) が欠損した frame
    bad_frame = pd.DataFrame({
        "race_nkey": ["R1", "R2"],
        "race_date": ["2022-01-01", "2022-06-01"],
        # rolling_speed_figure_mean_5 / rolling_field_strength_mean_mean_5 が無い
    })

    with pytest.raises(RuntimeError, match="W-2 必須列"):
        mod._compute_w2_diagnostics(bad_frame, out_dir=tmp_path)


def test_cr04_w2_diagnostics_raises_runtime_error_on_race_date_missing(tmp_path) -> None:
    """CR-04: race_date 列欠損も RuntimeError に格上げ（mask 構築不能 = W-2 履行不能）."""
    mod = _load_run_phase10_evaluation_module()

    # 必須 rolling 系 feature はあるが race_date が無い
    bad_frame = pd.DataFrame({
        "race_nkey": ["R1", "R2"],
        "rolling_speed_figure_mean_5": [100.0, 95.0],
        "rolling_field_strength_mean_mean_5": [10.0, 9.0],
        # race_date が無い
    })

    with pytest.raises(RuntimeError, match="race_date 列がない"):
        mod._compute_w2_diagnostics(bad_frame, out_dir=tmp_path)


def test_wr02_main_uses_make_pool_with_configure_callback() -> None:
    """WR-02: ``main`` が ``make_pool(settings, role='readonly', configure=_configure_statement_timeout)``
    で pool を構築することを検証する（cursor 単位でなく connection checkout 毎に SET statement_timeout・
    memory subagent-db-query-statement-timeout）.

    ソース grep で ``configure=_configure_statement_timeout`` が存在することを検証する。
    """
    module_path = _REPO_ROOT / "scripts" / "run_phase10_evaluation.py"
    src = module_path.read_text(encoding="utf-8")

    assert "_configure_statement_timeout" in src, (
        "main に _configure_statement_timeout callback 定義が無い (WR-02)"
    )
    assert "configure=_configure_statement_timeout" in src, (
        "make_pool 呼出しに configure=_configure_statement_timeout が指定されていない (WR-02)"
    )
    assert "SET statement_timeout = '30s'" in src, (
        "_configure_statement_timeout callback 内に SET statement_timeout='30s' が無い (WR-02)"
    )
    # cursor 内の SET は二重防衛として残っているはず
    assert src.count("SET statement_timeout = '30s'") >= 2, (
        "SET statement_timeout='30s' が configure callback と cursor 内の両方に存在しない・"
        "二重防衛が崩れている (WR-02)"
    )
