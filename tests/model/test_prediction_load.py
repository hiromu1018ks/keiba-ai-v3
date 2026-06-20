"""Phase 4 D-05 staging-swap idempotent 検証契約 (Wave 0 RED stub).

後続 PLAN 04 (prediction_load.py) が本 stub を GREEN 化する:
- D-05: _idempotent_load_prediction を2回実行で checksum 一致
  (advisory lock → CREATE staging INCLUDING ALL → TRUNCATE → executemany INSERT →
   SELECT count(*) verify → DELETE model_type+model_version scoped → INSERT (cols明示) → GRANT 再発行)

requires_db マーク付与: live DB 接続必須 (KEIBA_SKIP_DB_TESTS=1 で skip 可能).

参考: src/etl/fukusho_label.py::_idempotent_load_label パターン再利用・
      04-PATTERNS.md prediction_load.py セクション.
"""

from __future__ import annotations

import pytest


@pytest.mark.requires_db
def test_idempotent_checksum_match():
    """D-05: _idempotent_load_prediction を2回実行で checksum 一致 (staging-swap idempotent).

    同一 model_type+model_version の行を scoped で置換 (review Cycle 2 NEW-3: 列明示 INSERT).
    2回目の実行で1回目の行が残りつつ checksum が一致することを検証.
    """
    pytest.fail("Wave 0 RED stub - implemented in PLAN 04")
