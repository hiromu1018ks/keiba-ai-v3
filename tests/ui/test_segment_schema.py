# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・src/ev/report.py と同一慣例)
"""reports/06-segments/*.json 6軸スキーマ契約検証（Phase 6 D-10/D-11/D-12 生成済み stamped データ）。

Phase 7 Segment Calibration タブ（Plan 07-03）が消費する ``reports/06-segments/<axis>.json``
6軸（year/month/jyocd/entry_count/ninki/odds_band・06-CONTEXT D-12）のスキーマ契約を検証する。
各 JSON は ``axis_name`` + ``segments[]``（``curve``/``scalar``/``segment_value``）構造を持つ
（Phase 6 D-10 生成済み・stamped）。

参照: 07-01-PLAN.md Task 2 / 07-PATTERNS.md §tests/ui/test_segment_schema.py /
      07-RESEARCH.md §Validation Architecture L681
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SEGMENTS_DIR = Path("reports/06-segments")
AXES: tuple[str, ...] = ("year", "month", "jyocd", "entry_count", "ninki", "odds_band")
REQUIRED_CURVE_KEYS: set[str] = {"count", "frac_pos", "mean_pred"}
REQUIRED_SCALAR_KEYS: set[str] = {
    "ece_quantile",
    "ece_uniform",
    "max_dev_guarded",
    "mce_guarded",
    "n_samples",
}


def test_all_axes_present():
    """D-12: 6軸全ての JSON が存在する（stamped 成果物の前提検証・skip でなく素直に fail）。"""
    for axis in AXES:
        assert (SEGMENTS_DIR / f"{axis}.json").exists(), (
            f"{axis}.json が reports/06-segments/ に未生成（Phase 6 D-10 実行確認が必要）"
        )


def test_segment_schema_contract():
    """全6軸 JSON が axis_name + segments[] (curve/scalar/segment_value) 構造を持つ（部分集合検証）。

    curve: count / frac_pos / mean_pred の3キーが部分集合として含まれる
    scalar: ece_quantile / ece_uniform / max_dev_guarded / mce_guarded / n_samples の5キーが部分集合
    segment_value: 各 segment が値ラベルを持つ
    """
    for axis in AXES:
        json_path = SEGMENTS_DIR / f"{axis}.json"
        if not json_path.exists():
            pytest.fail(f"{axis}.json が未生成（test_all_axes_present と合わせて前提違反）")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "axis_name" in data, f"{axis}.json に 'axis_name' キーがない"
        assert "segments" in data, f"{axis}.json に 'segments' キーがない"
        assert isinstance(data["segments"], list) and len(data["segments"]) > 0, (
            f"{axis}.json の 'segments' が空リスト（calibration curve 描画不可）"
        )
        for i, seg in enumerate(data["segments"]):
            assert "curve" in seg, f"{axis}.json segments[{i}] に 'curve' キーがない"
            assert "scalar" in seg, f"{axis}.json segments[{i}] に 'scalar' キーがない"
            assert "segment_value" in seg, (
                f"{axis}.json segments[{i}] に 'segment_value' キーがない"
            )
            assert REQUIRED_CURVE_KEYS <= set(seg["curve"]), (
                f"{axis}.json segments[{i}] の 'curve' に必須キー {REQUIRED_CURVE_KEYS} が欠落"
            )
            assert REQUIRED_SCALAR_KEYS <= set(seg["scalar"]), (
                f"{axis}.json segments[{i}] の 'scalar' に必須キー {REQUIRED_SCALAR_KEYS} が欠落"
            )
