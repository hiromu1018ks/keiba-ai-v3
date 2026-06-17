"""Shared JRA / project-window filters (CR-06 single source of truth).

Why this module exists
----------------------
CR-06 found that the "JRA filter" was defined three different ways in three
modules with three different scopes:

  - ``src/etl/raw_fingerprint.py``:  ``jyocd BETWEEN '01' AND '10'``
  - ``src/etl/quality_gate.py``:     ``jyocd BETWEEN '01' AND '10'``
  - ``src/etl/normalize.py``:        ``jyocd BETWEEN '01' AND '10' AND year::int >= 2015``

A future edit to one would not propagate to the others — exactly the risk
CLAUDE.md flags. This module is the single source of truth; downstream
modules import from here.

Two scopes are exposed deliberately:

  - :data:`JRA_FILTER` — JRA 10 courses only (jyocd 01-10). Use for raw-
    immutability fingerprints and code-value audits where the *full* JRA
    history (including any pre-2015 rows) must be observed.
  - :data:`PROJECT_WINDOW_FILTER` — JRA + the project data window per
    requirements §6.1 (2015-01-01 onwards). Use for ETL SELECTs that feed
    normalized/training data.
"""

from __future__ import annotations

# JRA 10 場限定（要件 §6.1 / Pitfall 2）。
# EveryDB2 には jyocd>=30 の NAR 行も含まれるため、全クエリでこのフィルタを適用
# して NAR 混入を排除する。
JRA_FILTER = "jyocd BETWEEN '01' AND '10'"

# プロジェクト対象期間（要件 §6.1: 2015-01-01 以降）。
# ETL で normalized.* に流す行を絞り込む。raw_fingerprint / quality_gate の
# 監査は JRA_FILTER を使う（学習対象外の pre-2015 JRA 行の改変も検知するため）。
PROJECT_WINDOW_FILTER = "jyocd BETWEEN '01' AND '10' AND year::int >= 2015"


__all__ = ["JRA_FILTER", "PROJECT_WINDOW_FILTER"]
