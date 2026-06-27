"""Phase 12 EVAL-02/EVAL-01 evaluation layer (falsification / market_implied calibrator).

本パッケージは Phase 12 の評価・診断専用層であり・予測モデル ``p`` の feature 構築経路
(``FEATURE_COLUMNS`` / ``build_training_frame`` / ``load_feature_matrix``) から完全に切り離されている
（SAFE-01・層分離・domain-analysis §5）。odds / market_implied / model_p 引数は evaluation 専用境界。
"""
