"""Keiba AI v3 feature engineering package.

Phase 3 で新設（§17.2 レイアウト）。本 package は特徴量マトリクス構築と snapshot 書込を担う:

  - ``availability``: feature_availability.yaml loader / allowlist helpers / cutoff semantics 定数
  - ``builder`` (Plan 03-03): PIT-correct feature matrix 構築（readonly SELECT のみ）
  - ``rolling`` (Plan 03-03): per-observation latest-5 rolling features
  - ``running_style`` (Plan 03-03): 推定脚質（過去走通過順のみ）
  - ``snapshot`` (Plan 03-04): PyArrow 決定論的 Parquet 書込（§12.4 metadata 埋込）
  - ``category_map_consumer`` (Plan 03-04): train-only fit + frozen map apply

明示的 import を強制するため ``__all__`` は空（``from src.features.builder import build_feature_matrix`` 形式）。
"""

from __future__ import annotations

__all__: list[str] = []
