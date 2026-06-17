"""Keiba AI v3 ETL（品質ゲート / normalized ETL / class normalize）。

本パッケージは Phase 1 では以下を提供する:
  - ``quality_gate``: everydb2.public.n_* に対するハイブリッド品質ゲート（D-01）
    （plan 01-02・構造的欠陥=BLOCK / 量的異常=INFO を分離）
  - ``class_normalize`` / ``normalized_etl`` は後続 plan 01-03 で追加予定
"""
