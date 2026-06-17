"""リーク防止プリミティブ群（成功基準#4）。

Phase 3/4/5 が即座に import して利用可能な薄い wrapper:
- pit_join: pandas.merge_asof(direction='backward') + sortedness pre-check
- group_split: race_id 単位・時系列順の CV splitter
- category_map: 訓練窓 fit の frozen map（__UNSEEN__/__MISSING__ フォールバック）
- calibrator: CalibratedClassifierCV(cv='prefit') + 時系列順序 raise
"""
