# Phase 5 Backtest Report (BACK-01..04 / §15.5 / §19.1)

## 比較表 (全候補一括提示・winner 強調なし・BACK-04)

| backtest_id | bt_name | odds_policy | model_type | recovery_rate | P/L | max_DD | selected | effective_bet | refund | hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BT-1-10min_before-catboost | BT-1 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-10min_before-lightgbm | BT-1 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-30min_before-catboost | BT-1 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-30min_before-lightgbm | BT-1 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-1-confirmed-bl3 | BT-1 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |
| BT-2-10min_before-catboost | BT-2 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-2-10min_before-lightgbm | BT-2 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-2-30min_before-catboost | BT-2 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-2-30min_before-lightgbm | BT-2 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-2-confirmed-bl3 | BT-2 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |
| BT-3-10min_before-catboost | BT-3 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-3-10min_before-lightgbm | BT-3 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-3-30min_before-catboost | BT-3 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-3-30min_before-lightgbm | BT-3 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-3-confirmed-bl3 | BT-3 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |
| BT-4-10min_before-catboost | BT-4 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-4-10min_before-lightgbm | BT-4 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-4-30min_before-catboost | BT-4 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-4-30min_before-lightgbm | BT-4 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-4-confirmed-bl3 | BT-4 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |
| BT-5-10min_before-catboost | BT-5 | 10min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-5-10min_before-lightgbm | BT-5 | 10min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-5-30min_before-catboost | BT-5 | 30min_before | catboost | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-5-30min_before-lightgbm | BT-5 | 30min_before | lightgbm | 0.0000 | 0 | 0 | 0 | 0 | 0 | 0.0000 |
| BT-5-confirmed-bl3 | BT-5 | confirmed | bl3 | 1.7500 | 7200 | 0 | 96 | 96 | 0 | 1.0000 |

## §11.2 odds policy 固定履行確認

- §11.2 odds policy 固定履行: 全 backtest 行の odds_snapshot_policy は事前登録値 (30min_before / 10min_before / confirmed) のいずれかであり・レース後の有利オッズ選択・最終オッズ無条件使用・欠損時の都合の良い時点への差し替えは一切行われていない。BACK-04 / §11.2 構造的ブロック (T-05-15 mitigate)。
- 事前登録 policy 一覧: 30min_before / 10min_before (主モデル 20 backtest)・confirmed (BL-3 5 backtest・JODDS 時点非依存 sentinel)
- backtest_strategy_version (全 backtest 行共通): fukusho_ev_v1 (§19.1 再現性 stamp)

## 注記

- BACK-04: 本報告は全候補を backtest_id 辞書順で一括提示する。回収率が最も高い backtest_id を「推奨」「採用候補」と突出させる記述は一切ない。主モデル確定は Phase 6 D-03/D-04 の事前登録選定基準 (Calibration 重視) に委ねる (後知恵排除・Information Disclosure)。
- §11.2 odds policy 固定履行: 全 backtest 行の odds_snapshot_policy は事前登録値 (30min_before / 10min_before / confirmed) のいずれかであり・レース後の有利オッズ選択・最終オッズ無条件使用・欠損時の都合の良い時点への差し替えは一切行われていない。BACK-04 / §11.2 構造的ブロック (T-05-15 mitigate)。
- BL-3 §14.2 caveat: BL-3 uses confirmed fukuodds (post-race) — NOT a same-information-condition comparison with Phase 1-A model (§14.2). Market-implied benchmark only.
- 主モデルの最終確定は Phase 6 D-03/D-04 の事前登録選定基準 (Calibration 重視: calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考) で行う。本 Phase 5 report は素材提供のみ。
- HIGH-1/HIGH-2: 予測・オッズ snapshot・label の JOIN は全て (race_key, umaban) 単位で実行し・merge 後に行数が入力予測行数と一致することを assert している (cartesian duplication 構造的ブロック)。HARAI は race-level slot レコードのため例外的に on=['race_key'] + validate='many_to_one' で馬行にブロードキャストし・行ベース slot lookup (_lookup_payfukusyo_pay) で払戻を確定する (HIGH-C cycle-2)。
- HIGH-5: 各 BT窓 train 期間のみで fit_category_map を呼出し・test 窓の未観測 ID を __UNSEEN__ sentinel に mapping している (全期間固定 category_map の再利用回避・test 窓 ID 漏洩防止)。
- 実JODDS状況: 合成データ版 (run_backtest --synthetic)。実JODDS取得は進行中のため・本 report の数値は pipeline 動作検証用であり投資判断の素材ではない。実データ版は後続 Plan 05-06 checkpoint で生成予定。
