# Phase 5 Backtest Report (BACK-01..04 / §15.5 / §19.1)

## 比較表 (全候補一括提示・winner 強調なし・BACK-04)

| backtest_id | bt_name | odds_policy | model_type | recovery_rate | P/L | max_DD | selected | effective_bet | refund | hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BT-1-10min_before-catboost | BT-1 | 10min_before | catboost | 0.5995 | -167000 | 167900 | 4170 | 4170 | 0 | 0.0731 |
| BT-1-10min_before-lightgbm | BT-1 | 10min_before | lightgbm | 0.6623 | -147090 | 147890 | 4355 | 4355 | 0 | 0.0886 |
| BT-1-30min_before-catboost | BT-1 | 30min_before | catboost | 0.6176 | -157300 | 157200 | 4114 | 4114 | 0 | 0.0858 |
| BT-1-30min_before-lightgbm | BT-1 | 30min_before | lightgbm | 0.6471 | -151870 | 154170 | 4304 | 4304 | 0 | 0.0990 |
| BT-1-confirmed-bl3 | BT-1 | confirmed | bl3 | 0.8240 | -121660 | 121740 | 6912 | 6912 | 0 | 0.5712 |
| BT-2-10min_before-catboost | BT-2 | 10min_before | catboost | 0.6994 | -127800 | 138140 | 4252 | 4252 | 0 | 0.0769 |
| BT-2-10min_before-lightgbm | BT-2 | 10min_before | lightgbm | 0.7413 | -110130 | 118070 | 4257 | 4257 | 0 | 0.0881 |
| BT-2-30min_before-catboost | BT-2 | 30min_before | catboost | 0.7216 | -117000 | 128500 | 4203 | 4203 | 0 | 0.0902 |
| BT-2-30min_before-lightgbm | BT-2 | 30min_before | lightgbm | 0.7270 | -114930 | 122850 | 4210 | 4210 | 0 | 0.0990 |
| BT-2-confirmed-bl3 | BT-2 | confirmed | bl3 | 0.8342 | -114540 | 114440 | 6908 | 6908 | 0 | 0.5876 |
| BT-3-10min_before-catboost | BT-3 | 10min_before | catboost | 0.7151 | -115210 | 117940 | 4044 | 4044 | 0 | 0.0779 |
| BT-3-10min_before-lightgbm | BT-3 | 10min_before | lightgbm | 0.6506 | -143080 | 146970 | 4095 | 4095 | 0 | 0.0842 |
| BT-3-30min_before-catboost | BT-3 | 30min_before | catboost | 0.6803 | -126870 | 129350 | 3968 | 3968 | 0 | 0.0877 |
| BT-3-30min_before-lightgbm | BT-3 | 30min_before | lightgbm | 0.6807 | -129270 | 131630 | 4049 | 4049 | 0 | 0.1074 |
| BT-3-confirmed-bl3 | BT-3 | confirmed | bl3 | 0.8214 | -123440 | 123360 | 6910 | 6910 | 0 | 0.5757 |
| BT-4-10min_before-catboost | BT-4 | 10min_before | catboost | 0.6580 | -136870 | 143130 | 4002 | 4002 | 0 | 0.0780 |
| BT-4-10min_before-lightgbm | BT-4 | 10min_before | lightgbm | 0.7290 | -112080 | 116890 | 4136 | 4136 | 0 | 0.0955 |
| BT-4-30min_before-catboost | BT-4 | 30min_before | catboost | 0.6614 | -133360 | 140530 | 3939 | 3939 | 0 | 0.0863 |
| BT-4-30min_before-lightgbm | BT-4 | 30min_before | lightgbm | 0.6790 | -132360 | 136260 | 4124 | 4124 | 0 | 0.0992 |
| BT-4-confirmed-bl3 | BT-4 | confirmed | bl3 | 0.8342 | -114540 | 114440 | 6908 | 6908 | 0 | 0.5876 |
| BT-5-10min_before-catboost | BT-5 | 10min_before | catboost | 0.6806 | -128480 | 140190 | 4022 | 4022 | 0 | 0.0823 |
| BT-5-10min_before-lightgbm | BT-5 | 10min_before | lightgbm | 0.6975 | -135110 | 143940 | 4466 | 4466 | 0 | 0.0797 |
| BT-5-30min_before-catboost | BT-5 | 30min_before | catboost | 0.6881 | -122860 | 134210 | 3939 | 3939 | 0 | 0.0937 |
| BT-5-30min_before-lightgbm | BT-5 | 30min_before | lightgbm | 0.6961 | -133260 | 142570 | 4385 | 4385 | 0 | 0.0940 |
| BT-5-confirmed-bl3 | BT-5 | confirmed | bl3 | 0.8342 | -114540 | 114440 | 6908 | 6908 | 0 | 0.5876 |

## §11.2 odds policy 固定履行確認

- §11.2 odds policy 固定履行: 全 backtest 行の odds_snapshot_policy は事前登録値 (30min_before / 10min_before / confirmed) のいずれかであり・レース後の有利オッズ選択・最終オッズ無条件使用・欠損時の都合の良い時点への差し替えは一切行われていない。BACK-04 / §11.2 構造的ブロック (T-05-15 mitigate)。
- 事前登録 policy 一覧: 30min_before / 10min_before (主モデル 20 backtest)・confirmed (BL-3 5 backtest・JODDS 時点非依存 sentinel)
- backtest_strategy_version (全 backtest 行共通): fukusho_ev_v1 (§19.1 再現性 stamp)

## MEDIUM-B JODDS coverage サマリ (horse-level usable-odds)

| bt_name | policy | horse_level_coverage | race_level_coverage | threshold | status |
| --- | --- | --- | --- | --- | --- |
| BT-1 | 30min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-1 | 10min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-2 | 30min_before | 1.0000 | 1.0000 | 0.9000 | pass |
| BT-2 | 10min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-3 | 30min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-3 | 10min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-4 | 30min_before | 1.0000 | 1.0000 | 0.9000 | pass |
| BT-4 | 10min_before | 0.9999 | 1.0000 | 0.9000 | pass |
| BT-5 | 30min_before | 1.0000 | 1.0000 | 0.9000 | pass |
| BT-5 | 10min_before | 0.9999 | 1.0000 | 0.9000 | pass |

## 注記

- BACK-04: 本報告は全候補を backtest_id 辞書順で一括提示する。回収率が最も高い backtest_id を「推奨」「採用候補」と突出させる記述は一切ない。主モデル確定は Phase 6 D-03/D-04 の事前登録選定基準 (Calibration 重視) に委ねる (後知恵排除・Information Disclosure)。
- §11.2 odds policy 固定履行: 全 backtest 行の odds_snapshot_policy は事前登録値 (30min_before / 10min_before / confirmed) のいずれかであり・レース後の有利オッズ選択・最終オッズ無条件使用・欠損時の都合の良い時点への差し替えは一切行われていない。BACK-04 / §11.2 構造的ブロック (T-05-15 mitigate)。
- BL-3 §14.2 caveat: BL-3 uses confirmed fukuodds (post-race) — NOT a same-information-condition comparison with Phase 1-A model (§14.2). Market-implied benchmark only.
- 主モデルの最終確定は Phase 6 D-03/D-04 の事前登録選定基準 (Calibration 重視: calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考) で行う。本 Phase 5 report は素材提供のみ。
- HIGH-1/HIGH-2: 予測・オッズ snapshot・label の JOIN は全て (race_key, umaban) 単位で実行し・merge 後に行数が入力予測行数と一致することを assert している (cartesian duplication 構造的ブロック)。HARAI は race-level slot レコードのため例外的に on=['race_key'] + validate='many_to_one' で馬行にブロードキャストし・行ベース slot lookup (_lookup_payfukusyo_pay) で払戻を確定する (HIGH-C cycle-2)。
- HIGH-5: 各 BT窓 train 期間のみで fit_category_map を呼出し・test 窓の未観測 ID を __UNSEEN__ sentinel に mapping している (全期間固定 category_map の再利用回避・test 窓 ID 漏洩防止)。
- 実JODDS状況: 取得完了 (全 BT窓 × policy で horse-level usable-odds coverage >= 閾値)。本 report の数値は Phase 6 主モデル確定に向けた素材として参照可能。
