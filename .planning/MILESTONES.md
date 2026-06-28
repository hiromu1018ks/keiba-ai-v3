# Milestones

## v1.1 Ability Feature v2 & Conditional Calibration (Shipped: 2026-06-28)

**Phases completed:** 5 phases (9/9.1/10/11/12), 25 plans, 21 tasks
**Shipped:** 2026-06-28
**Audit:** gaps_found → override closeout (gsd-audit-milestone・BLOCKER 0・integration 9/9 WIRED・E2E complete・7/8 requirements satisfied [FEAT-01 partial]・Core Value 完全保持)

**Delivered:** 機構（FEAT-01/02/03・MODEL-01・EV-01・EVAL-01/02・SAFE-01）全て完成。スピード指数（Phase 9・par/variant/PIT・float canonical）→ 相手強度 field_strength + レース内相対特徴量（Phase 10・source-as-of full-pipeline 再計算）→ レース内相対確率モデル（Phase 11・θ + α_r brentq・sum(p)=k 厳密）→ p_lower EV + falsification test（Phase 12・conformal shrinkage・race_id clustered SE・Holm・§11.2 聖域）。cross-phase 9/9 WIRED・E2E live-DB byte-reproducible・SAFE-01 AST audit 全フェーズ GREEN。**Spike 001 ablation で成功仮説（追加特徴量で黒字化）がデータで否定**: 黒字化したのは Phase 9 基本6（speed figure・binary）のみ（cross-window 5窓平均回収率1.14）・Phase 9.1 拡張/Phase 10/Phase 11 race-relative は回収率を下げる。A1（Phase 9 基本6・label v1.1.0・binary）は is_primary=True でデプロイ済み（ユーザー承認・backtest 反映済み）。

**Stats:** 期間 2026-06-25→2026-06-28（4日）・5 phases/25 plans・主モデル A1 cross-window 平均回収率1.14
**Known verification overrides:** 5（Phase 9/9.1 VERIFICATION gap・Phase 11/12 provisional results [label v1.0.0 universe]・Phase 09-05 stopgate incomplete・PREDICTION_COLUMNS doc mismatch・debug fukusho-recovery-070 RESOLVED・詳細は STATE.md Deferred Items）

**Key accomplishments:**

- 1. [Rule 3 - Blocking fix] source_available_at_by_race を唯一の cutoff 真の源に修正
- 1. [Rule 1 - Bug] テストデータの fs_mean 割当順序が「最新=最大」でない問題
- 1. `_gap_to_top_within_race` の実装
- 1. [Rule 1 - Bug] race_relative.py 入力の numeric 強制 cast
- 1. [Rule 1 - Bug] builder Step6d drop 条件が `field_strength_adjusted_rank` を誤 drop
- gate_pass: True (exit 0・3条件全て D-16 許容幅内・delta 基準は baseline snapshot 実測値・B-3・§11.2 聖域)
- 1. [Rule 1 - Bug] test_lookahead_injection_detected の layer 2 単独無効化では検出力が無かった
- 状態
- 1. `src/model/race_relative.py`（235 行・stub・pure 関数）
- `src/model/race_relative.py`
- 1. [Rule 1 - Bug] docstring 直接トークン名が audit AST scan で false-positive 検出
- 1. [Rule 1 - Bug] isotonic 単調性テストの確率軸が逆順だった
- 1. [Rule 3 - Blocking] check_acceptance_gate の正しい signature への対応
- Phase 12 全実装に対する 5段階鋳型 adversarial audit + 値レベル §11.2 leak 検出 (C-12-05-1 HIGH) で・SAFE-01 odds proxy 排除・§11.2 test 窓聖域・D-10 is_primary 自動変更禁止を機械保証 (Task 1 完了・Task 2/3 は orchestrator checkpoint 管轄)

---

## v1.0 Leak-Free Fukusho Pipeline (Shipped: 2026-06-25)

**Phases completed:** 9 phases (1-8 + 3.1), 40 plans, 82 tasks
**Shipped:** 2026-06-25
**Audit:** passed (gsd-audit-milestone・25/25 requirements satisfied・integration 7/7・flows 7/7・GAP-INT-01 resolved)

**Delivered:** leak-free odds-free 複勝 `p_fukusho_hit` pipeline。raw品質ゲート→normalized ETL→複勝ラベル（払戻突合100%・554,267行）→PIT-correct不変Parquet snapshot（62 features・byte-reproducible）→LightGBM/CatBoost学習（SC#1 Parquet-only・SC#3 leak diagnostic・SC#4 bit-identical）→race_id-grouped再現可能backtest（25 backtest・行レベルDB永続化1,184,052行・返還/中止honest会計）→確率品質ゲート（gate=WARN・主モデルLightGBM・SC#2達成）→read-only Streamlit UI/CSV（20/16列 BOM+CRLF）→対抗的監査（tests/audit/・499 passed）。コアバリュー（リーク防止・再現性）完全保持。回収率0.65-0.70天井は odds-free 1-A モデルの構造的限界（要件未達でなく正直な結論・debug fukusho-recovery-070 でROOT CAUSE確定・別計画フェーズで戦略判断）。

**Stats:** 449 commits・420 files changed・100,979 insertions・39,658 Python LOC・期間 2026-06-16→2026-06-25 (9日)
**Known deferred items at close:** 2（debug fukusho-recovery-070 [diagnosed]・Phase 07 verification [human_needed]・詳細は STATE.md Deferred Items）

**Key accomplishments:** (SUMMARY から機械抽出)

- 1. [Rule 3 - Blocking] hatchling ビルドバックエンドへの切替
- 1. [Rule 1 - Bug] futan カラムは n_race ではなく n_uma_race 側
- 1. [Rule 3 - Blocking] ETL ロールに normalized スキーマの CREATE 権限が無い
- 1. [Rule 3 - Blocking] sklearn 1.9.0 で `CalibratedClassifierCV(cv='prefit')` が削除
- label_spec.yaml でラベル定義を Git 管理化し（label_generation_version='v1.0.0'）、PostgreSQL label スキーマに対する明示的 reader/etl ロール GRANT と search_path 拡張を実DB まで反映（PUBLIC 不使用・HIGH #3）。
- 1. [Rule 1 - test typo] `test_is_model_eligible_class_below_minimum` の NameError 修正
- LABEL-03 acceptance gate implemented and PASSED on live DB: 100.0% race-set agreement (4063/4063 held-out races) on label.fukusho_label's 554,267 rows, all 6 §10.5 BLOCK checks green, drift demoted to INFO after live-DB discovery that drift is D-04-legitimate (not ETL bugs).
- 1. [Rule 1 - Bug] INSERT/SELECT positional mismatch (date/integer 型エラー)
- 1. [Rule 1 - Bug] running_style API 署名をテスト契約に合わせて調整
- 1. [Rule 1 - Bug] BUG A: race_nkey は DB カラムでない
- 1. [Rule 1 - Bug] docstring の直 `joblib` token が plan verify block の strict check に抵触
- 1. [Rule 3 - Blocking] staging-swap を LIKE から DDL 駆動に変更
- 1. [Rule 3 - Blocking] babacd 派生に使う sibababacd/dirtbabacd を alias で SELECT
- 1. [Rule 3 - Blocking] PLAN acceptance criteria の feature_count 24→63 修正
- LightGBM 4.6.0 / CatBoost 1.2.10 pin + prediction.fukusho_prediction DDL (11カラム PK + 3 CHECK 制約) + tests/model/ 20 RED stub + v3→postreview-v2 ドリフト修正
- stamped Parquet 読込 + label join + 3way 正準 race_key disjoint 分割 (SC#1/MODL-01/D-02b) + fit_prefit_calibrator 薄い wrapper (SC#4/§15.2) + CalibratedClassifierCV base/calibrator 分離保存 (review HIGH#5/D-06)・review HIGH#9/MEDIUM#5/MEDIUM#6 全対応
- LightGBM native categorical + CatBoost has_time=True (SC#3 / §14.3 / §14.4) + 高基数 _code cat_features 扱い (review HIGH#6 / MODL-03) + 行整列保証 (review HIGH#2 / Cycle 2 NEW-2) + eval set 分離 (review Cross-Plan #8) + SC#3 leak diagnostic (review HIGH#3)・BL-1..5 全5つ計算 (MODL-02 / SC#2 / D-07 / D-08)
- provenance 付き予測 DataFrame (MODL-01/D-05/D-10) + model_version スコープ staging-swap idempotent load (review HIGH#1/Cross-Plan #3) + Brier/LogLoss/Calibration/sum(p) BL比較表 (SC#2/§15.1/§15.2)
- train_and_predict orchestrator (review HIGH#12: calibrator.py でなく独立モジュール) + 行整列保証 (HIGH#2) + SC#4 bit-identical (HIGH#7・実データ両モデルで実証) + aligned pred_proba 注入 (Cycle 2 NEW HIGH-1) + データ API 境界明示 (Cycle 2 residual #13) + run_train_predict.py 両モデル E2E pipeline (HIGH#1 model_version スコープ swap)
- Phase 4 最終検証と完了宣言: 両モデル実データ E2E（DB 書込 + reports commit）・SC#3/SC#4 構造的ブロック GREEN・全テスト KEIBA_SKIP_DB_TESTS unset で 262 passed / 0 skipped（green-by-skip 防止）・SC#2 正直注記（AI 付加価値 部分証明: Brier/LogLoss/AUC で BL 上回るが D-04 主要基準 Calibration で BL に劣る）・ROADMAP/STATE 更新で Phase 5 引き渡し
- `tests/utils/test_group_split.py` に behavior 7テストを追記（実装前なので ImportError で RED）。
- `test_ev_rank.py` に `test_rank_no_bet_is_D` を追加（5テスト全て ModuleNotFoundError で RED）。
- `test_odds_snapshot.py` に cycle-2 テスト5件を追加（multi_race/0999/datakubun/snake_case/fukusyoflag）+ stub テストの HIGH-3 canonical 整合修正。11テスト全て ModuleNotFoundError で RED。
- `test_orchestrator_bt.py` に7テストを追加（periods injection / strict_later_guard / backward_compat / split_periods propagation / backward_compat signature / category_map_plumbing / category_map_none_default）。TypeError/ImportError で RED。
- scripts/run_backtest.py（約1100行）+ src/ev/report.py（約260行）を新設。
- prediction.fukusho_prediction に is_primary フラグ（NOT NULL DEFAULT false）を追加する 3ファイル連鎖 DB migration + set_primary_model 関数（model_version scoped・idempotent・0 行 UPDATE で RuntimeError post-condition）を実装し、REVIEW HIGH#7/HIGH#8/C10/C11/C17 を解消
- 1. [Rule 1 - Bug] model_version 推断偏差を修正（commit 86afe9f）
- 1. [Rule 1 - Bug] test_readonly_guarantee.py のインデント崩れ修正
- 1. [Rule 3 - Blocking] ruff F541 (f-string が placeholder を持たない) と isort 順序の自動修正
- 1. [Rule 1 - Bug] test_calibration_tab_six_axes が SEGMENT_AXES 変数渡しを拾えない
- SC#2 の3リーク注入ケース（lookahead / payout 正欠損 / fold race_id 共有）と D-06（UI 書き込み/DDL SQL 混入 + 再現性スタンプ欠落）を・リークを注入すると fail する独立 adversarial テスト9件として tests/audit/ に新設（KEIBA_SKIP_DB_TESTS=1 で全 GREEN・DB 不要・ruff GREEN）
- SC#3 合成層 orchestrator (scripts/run_reproducibility_smoke.py・DB 不要 pytest 2 step subprocess・live-DB 必須 CLI は 08-03 委譲) と reports/08-audit.{md,json} 生成ロジック (src/audit/report.py・AUDIT_SURFACE_COLUMNS presence assert・KNOWN_LIMITATIONS 3項目 honest 開示・byte-reproducible) を新設
- KEIBA_SKIP_DB_TESTS unset で live-DB フルスイート GREEN (499 passed / 1 skipped Phase 6 既知・failed 0) + SC#3 live-DB 必須 CLI 層 (run_train_predict / run_backtest --check-reproduce) bit-identical PASS を人間承認 (approved)・label race_date backfill 復元 (3度目の再発・raw 不変) で SC#3 backtest GREEN を確立

---
