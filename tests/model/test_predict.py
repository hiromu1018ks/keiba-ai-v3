"""Phase 4 D-05 provenance / D-10 model_version 検証契約 (Wave 0 RED stub).

後続 PLAN 04 (predict.py) が本 stub を GREEN 化する:
- provenance 列 (model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method) が存在・NOT NULL
- D-10 model_version 採番: {feature_snapshot_id}-{model_type_short}-v{N} 形式
  例: 20260620-1a-postreview-v2-lgb-v1 / 20260620-1a-postreview-v2-cb-v1
  (Cycle 3 NEW-4 残渣: feature_snapshot_id 全体を prefix・再 suffix 追加禁止)

参考: 04-RESEARCH.md D-10 確定事項 / D-05 prediction provenance.
"""

from __future__ import annotations

import pytest


def test_provenance_columns():
    """provenance 列 (model_type/model_version/feature_snapshot_id/as_of_datetime/calib_method) が存在・NOT NULL.

    §19.1 再現性聖域. PK (model_type/model_version/feature_snapshot_id/as_of_datetime + RACE_KEY 7) に
    含まれることで NOT NULL 保証 (review HIGH#1・11カラム PK).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 04")


def test_model_version_numbering():
    """D-10 model_version 採番: {feature_snapshot_id}-{model_type_short}-v{N} 形式.

    例: 20260620-1a-postreview-v2-lgb-v1 / 20260620-1a-postreview-v2-cb-v1.
    feature_snapshot_id 全体を prefix とし、再度 suffix を追加しない (Cycle 3 NEW-4 残渣解消).
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 04")
