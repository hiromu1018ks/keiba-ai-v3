# Phase 8 Adversarial Audit Report (TEST-01 / SC#1・SC#2・SC#3)

## サーフェス別カバレッジマップ (SC#1 #1-#8)

| surface | sc_id | existing_tests | adversarial_test | status | evidence |
| --- | --- | --- | --- | --- | --- |
| fukusho_label | SC#1 #1 | tests/test_fukusho_label.py (複勝払戻対象ラベル生成) |  | COVERED | REQUIREMENTS.md TEST-01 複勝ラベル・§10.5 払戻テーブル |
| payout_reconcile | SC#1 #2 | tests/test_label_reconcile.py (_check_payout_recall・払戻テーブル突合 6検査) | tests/audit/test_audit_label.py::test_payout_positive_missing_from_labels_detected | COVERED+ADVERSARIAL | SC#2 ケース2 payout 正欠損注入 adversarial (Plan 08-01) |
| refund_handling | SC#1 #3 | tests/test_refund_accounting.py (取消/除外/中止・返金 |  | COVERED | REQUIREMENTS.md TEST-01 取消/除外/中止・§10.5 返金 |
| odds_snapshot | SC#1 #4 | tests/ev/test_odds_snapshot.py (odds_snapshot_policy 時点固定・§11.2) |  | COVERED | REQUIREMENTS.md TEST-01 オッズ時点固定・§11.2/§19.1 |
| virtual_purchase | SC#1 #5 | tests/ev/test_metrics.py (compute_backtest_metrics: recovery_rate/refund/max_drawdown/effective_stake) |  | COVERED | REQUIREMENTS.md TEST-01 仮想購入・§11.4/§11.6 回収率 |
| feature_cutoff | SC#1 #6 | tests/features/test_pit_cutoff.py (feature_cutoff_datetime enforcement・merge_asof direction='backward'・§13.2/§13.4 禁止列) | tests/audit/test_audit_features.py::test_lookahead_injection_detected_and_fails | COVERED+ADVERSARIAL | SC#2 ケース1 lookahead 注入 adversarial (Plan 08-01) |
| race_id_split | SC#1 #7 | tests/utils/test_group_split.py (get_bt_race_ids・race_id disjoint guard・§8.4) | tests/audit/test_audit_split.py::test_fold_race_id_shared_detected_and_raises | COVERED+ADVERSARIAL | SC#2 ケース3 fold race_id 共有注入 adversarial (Plan 08-01) |
| class_normalization | SC#1 #8 | tests/test_class_normalization.py (クラス正規化) |  | COVERED | REQUIREMENTS.md TEST-01 クラス正規化 |
| categorical_missing | SC#1 supplement | tests/model/test_trainer.py (LightGBM category dtype・__MISSING__/__UNSEEN__ sentinel・CatBoost has_time・§14.3/§14.4/§14.5) | tests/model/test_trainer.py::test_no_target_encoding_leak (Phase 4 adversarial 鋳型) | COVERED+ADVERSARIAL | REQUIREMENTS.md TEST-01 カテゴリ/欠損処理・§14.3 target encoding 禁止 |
| ui_csv_readonly | D-06 (Phase 7 継承) | tests/ui/test_readonly_guarantee.py (AST SQL 検査)・tests/ui/test_csv_columns.py (presence assert・§19.1 スタンプ) | tests/audit/test_audit_ui_csv.py (UI 書込/DDL SQL 混入検出 + 再現性スタンプ欠落検出) | COVERED+ADVERSARIAL | 07-CONTEXT Deferred → Phase 8 委譲 (D-06)・TEST-01 対抗的監査 |
| evaluation_metrics | TEST-01 | tests/ev/test_metrics.py (compute_backtest_metrics: recovery_rate/refund/max_drawdown)・tests/model/test_evaluator.py (compute_metrics: calibration_max_dev/brier/logloss/auc/sum_p)・tests/model/test_evaluator_gate.py (評価指標 gate) |  | COVERED | REQUIREMENTS.md L65 TEST-01 評価指標計算・F-05 対応・§15.1/§15.2/§15.3 |

## SC#1/#2/#3 対応表

| sc | scope | coverage | evidence |
| --- | --- | --- | --- |
| SC#1 | 機能テスト (リーク防止 8サーフェス + 補足 + 評価指標) | 既存476テストで COVERED (SURFACE_ROWS status 参照) | tests/{test_fukusho_label,test_label_reconcile,test_refund_accounting,test_odds_snapshot,test_pit_cutoff,test_group_split,test_class_normalization}.py + tests/model/test_trainer.py + tests/ui/ + tests/ev/test_metrics.py + tests/model/test_evaluator*.py |
| SC#2 | 対抗的 (注入型) テスト 3ケース (lookahead/payout正欠損/fold race_id共有) | ADVERSARIAL (Plan 08-01 で tests/audit/ に新設・KEIBA_SKIP_DB_TESTS=1 で GREEN) | tests/audit/test_audit_features.py (ケース1)・tests/audit/test_audit_label.py (ケース2)・tests/audit/test_audit_split.py (ケース3)・D-06 として tests/audit/test_audit_ui_csv.py (UI/CSV) |
| SC#3 | フルパイプライン固定 seed 再現 (snapshot→train→predict→backtest→eval) | 合成層: scripts/run_reproducibility_smoke.py (Plan 08-02)・live-DB 必須層: 08-03 checkpoint | 合成層 = calibrator bit-identical pytest + tests/audit/ (DB 不要)・live-DB 必須 CLI (run_train_predict/run_backtest --check-reproduce) は 08-03 で人間承認付き実行 |

## Known Limitations ("Looks Done But Isn't" honest 開示)

- 回収率天井 ~0.65-0.70: odds-free 1-A モデルの構造的限界 (LightGBM 0.7022・CatBoost 0.6808)。閾値調整では改善しない・Phase 1-B (odds 特徴量) か評価リフレームで対処。memory fukusho-recovery-070-structural-ceiling 整合。
- Calibration BL 劣位: 主モデル (LGB calibration_max_dev=0.2308) が BL-1 (0.0014)/BL-4 に劣位。Phase 4 SC#2 で確定・Phase 6 キャリブ指標再設計 (quantile/ECE/MCE 併記) の文脈。
- odds JODDS再検証 subject: Phase 5 実データ backtest 25件完走だが・odds 正確性はJODDS取得完了後に再検証。manual-only 分離。

## フルスイート GREEN 証明 (D-04)

KEIBA_SKIP_DB_TESTS unset で全 requires_db テストを実行（conftest.py fail-by-default policy 確証）。checkpoint 08-03 実績: 499 passed / 1 skipped (test_evaluator.py:490・reports/04-eval.json の calibration_max_dev_guarded 列欠損・Phase 6 C6 stale 既知・Plan 06-05 委譲・非 KEIBA_SKIP_DB_TESTS 由来) / failed 0・人間承認済み (approved)。詳細は 08-03-SUMMARY.md 参照。
