"""Phase 5 EV / Backtest モジュール。

本パッケージは Phase 5 (ev-backtest) で新設される EV 計算・推奨ランク・
仮想購入ルール・回収率指標・BL-3 betting ROI の純粋関数群を提供する。

Plan 05-02 で実装されるモジュール:
- ``ev_rank``: EV_lower/EV_upper 計算 + 推奨ランク S/A/B/C/D (§11.1/§11.5)
- ``purchase_simulator``: 仮想購入ルール fukusho_ev_v1 (§11.4)
- ``metrics``: 回収率/P/L/max drawdown 指標 (§11.6)
- ``bl3_betting``: BL-3 投資 ROI 比較 (D-04/§14.2)

Plan 05-03 で実装されるモジュール（本 plan では未実装・test は RED のまま）:
- ``odds_snapshot``: JODDS 時点選択 (D-01/D-02/BACK-04)
- ``refund_accounting``: 返還/中止 honest 会計決定表 (D-05/BACK-03)
"""
