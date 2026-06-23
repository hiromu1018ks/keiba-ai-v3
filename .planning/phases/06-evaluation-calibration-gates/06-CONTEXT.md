# Phase 6: Evaluation & Calibration Gates - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning

<domain>
## Phase Boundary

確率品質受入基準（§15.2/§15.3）を検証する**評価スイートと受入ゲート**を実装し、Phase 4 のモデル予測と Phase 5 の backtest 結果を統合して受け取る。そして D-04 事前登録基準（Calibration 重視）で**主モデル（LightGBM vs CatBoost）を確定**する。Build-Order DAG step 7（evaluation）。

具体的には:

1. **統合評価スイート（EVAL-01 / §15.1 / SC#1）** — 複勝的中率/回収率/損益/最大ドローダウン/購入点数（Phase 5 `src/ev/metrics.py`）と Brier/LogLoss/Calibration Curve（Phase 4 `src/model/evaluator.py`）を統合し、開発者が単一の評価経路で受け取れるようにする
2. **確率品質受入ゲート（EVAL-02 / §15.2 / SC#2）** — 年次 Calibration Curve の極端反転なし・bin 実測率の単調-ish・LogLoss/Brier の baselines 超過・`sum(p)` 平均の理論値適合（8頭以上 2.7-3.3 / 5-7頭 1.8-2.2）・median/SD/p10/p90 を検証するゲート
3. **セグメント別安定性（EVAL-03 / §15.3 / SC#3）** — per-year/per-month/per-競馬場/per-頭数/per-人気帯/per-オッズ帯 の Calibration Curve + scalar 安定性指標を生成し、aggregate 回収率に隠れる segment collapse を可視化
4. **キャリブ指標の再設計（debug calib-maxdev-vs-baselines の Phase 6 領域）** — uniform `calibration_max_dev` の構造バイアス対処（quantile bin + ECE + MCE 併記）と高確率域（pred>0.7）過信の可視化
5. **主モデル確定（Phase 4 D-03/D-04 事前登録基準の実体化）** — Calibration 重視基準で LightGBM vs CatBoost を選定し、prediction テーブルに `is_primary` フラグを付与して Phase 7 に引き渡す

**境界＝検証ゲート。** Phase 6 は評価・ゲート判定・主モデル確定まで。Streamlit 動的描画・CSV 出力は Phase 7（Presentation）・受入ゲート自体の対抗的監査は Phase 8（Adversarial Audit）が明示的に後続。Phase 6 は**新規予測生成やモデル再学習を行わない**（Phase 4/5 の stamped 成果物を消費する評価専用フェーズ・Phase 4 SC#4 bit-identical 再現性を維持）。

### ⚠ 評価対象データの前提（Phase 4/5 成果・実在・§19.1 聖域）
- `prediction.fukusho_prediction`（lightgbm 22,213行 + catboost 22,213行・各 model_version スコープ）— Phase 4 SC#4 bit-identical
- `reports/04-eval.{md,json}`（モデル品質比較表・D-04 事前登録素材）・`reports/05-backtest.{md,json}`（実データ backtest 25件完走・BT期間 2019-2025）
- `backtest.fukusho_backtest`（実データ backtest 結果・5窓フル行列）
- `label.fukusho_label`（的中判定 `fukusho_hit_validated`・`race_date`/`entry_count`/`jyocd`/人気・オッズの segment 軸）
- `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet`（固定 feature matrix・segment 評価の入力元）

</domain>

<decisions>
## Implementation Decisions

### 受入ゲートの厳格さ（EVAL-02 / §15.2・Core Value 直結）
- **D-01: 構造的 BLOCK のみ hard fail・それ以外は WARN（参考レポート）** — §15.2 受入基準のうち、モデルが本質的に破綻している場合のみ pytest/CI fail（出荷停止）。曖昧基準（「極端な逆転なし」「単調-ish」「大きく外れない」）は WARN。hybrid gate（Phase 1 D-01 / Phase 2 D-02: 構造的欠陥=BLOCK・量的異常=参考）の延長。Core Value「リーク防止と再現性だけは守る」に整合（確率品質は改善指標・出荷停止の聖域は Phase 8 リーク/再現性ゲート）。ユーザー選択: 構造的BLOCKのみ。（WARN-only / §15.2 全基準 BLOCK は却下）
- **D-02: 構造的 BLOCK 対象 = LogLoss/Brier で baselines 全敗 ＋ `sum(p)` が理論値から著しく乖離** — 順序付け能力ゼロ（AI 付加価値ゼロ・SC#2 の本質）と確率スケール破綻（8頭レースで sum(p)<<2.7 or >>3.3 等）の両方を安全網。ユーザー選択: 両方。（baselines 全敗のみ / BLOCK 設けない は却下）
- **D-03: 曖昧基準は参考レポート・数値併記・人間判定** — 「年次キャリブ反転」「bin 単調性」を反転数・単調違反 bin 数・Spearman 順位相関等の数値で併記するが、PASS/FAIL 判定は人間。曖昧基準の過機械化を回避。ユーザー選択: 参考レポート。（緩い閾値 WARN / 厳格閾値 WARN は却下）

### キャリブ指標の再設計（debug calib-maxdev-vs-baselines の Phase 6 領域）
- **D-04: 事前登録指標 `calibration_max_dev`（uniform・ガードなし）は不変で維持 + 新指標を併記** — Phase 4 事前登録の指標定義を温存（後知恵すり替え T-04-24 完全回避）し、Phase 6 で新指標を補助として追加。debug 9fce782 の `calibration_max_dev_guarded` 併記パターンの延長。ユーザー選択: 事前登録維持+新指標併記。（Phase 6 で指標セット再登録 / uniform max_dev のみ継続 は却下）
- **D-05: 追加キャリブ指標 = quantile max_dev + ECE + MCE** — quantile bin（等頻度・BL-1 の bin 退化バイアス解除）の max_dev と ECE（bin別 dev のサンプル重み付け平均・robust）と MCE（Maximum Calibration Error・worst-case）の3指標を併記。uniform max_dev（事前登録）+ guarded（Phase 4）と合わせて網羅的。ユーザー選択: quantile+ECE+MCE。（quantile+ECE / ECEのみ は却下）
- **D-06: 高確率域（pred>0.7）過信は可視化・記録のみ** — 局所 miscalibration を segment 評価で可視化し、根本対処（キャリブ再調整・特徴量/ハイパラ見直し）は Optuna 導入（将来 Phase）に委ねる。Phase 4 の SC#4 bit-identical 再現性を維持（モデル再予測・再学習しない）。ユーザー選択: 可視化・記録のみ。（キャリブ方法再調整 / 両方 は却下）

### 主モデル確定と運用（Phase 4 D-03/D-04 事前登録基準の実体化）
- **D-07: 主モデル選定は人間判断・理由記録** — Phase 6 評価レポートで両モデルの全指標（quantile/ECE/MCE/guarded + Brier/LogLoss/AUC + `sum(p)` + backtest 回収率/損益/maxDD）を並列提示し、D-04 基準（Calibration 重視）に照らして人間が決定・理由を記録。事前登録基準の柔軟な適用・過機械化回避。ユーザー選択: 人間判断・記録。（段階的フィルタ / スコアリング関数 は却下）
- **D-08: 僅差・同点時はタイブレーク規則で1つ選ぶ** — 両モデルが指標で接近した場合、固定優先順位（候補: backtest 回収率 → 計算コスト低=LightGBM）で1つに決定。主モデルは1つ。ユーザー選択: タイブレークで1つ。（両方主モデル残す / ケースバイケース人間判断 は却下）
- **D-09: 主モデル確定は prediction テーブルに `is_primary` フラグ付与** — 選定モデルの行に `is_primary=true`、未選定モデルは `is_primary=false`（両モデル行は保持）。Phase 7 Streamlit は `is_primary=true` を表示。§19.1 再現性（versioned artefact・比較可能性維持）。ユーザー選択: is_primary フラグ付与。（version のみ記録 / 主モデル行のみ残す は却下）

### セグメント別安定性の成果物（EVAL-03 / §15.3）
- **D-10: 成果物 = JSON データ + Plotly 静的 HTML の両方** — 機械可読 JSON（curve の bin/mean_pred/frac_pos/count・scalar 指標）と Plotly 静的 HTML。Phase 7 Streamlit は JSON を消費して動的描画、HTML は単体確認用。CLAUDE.md Plotly 推奨に整合。ユーザー選択: JSON + Plotly HTML。（JSON のみ / matplotlib PNG は却下）
- **D-11: segment 比較 = curve 並列表示 + scalar 表** — 各軸で segment ごとの calibration curve を重ね描き（並列表示）し、ECE/MCE/calibration_max_dev 等 scalar 指標の segment 表を併記。segment collapse（aggregate で隠れる局所ズレ）を一目で可視化。ユーザー選択: curve 並列 + scalar 表。（scalar 表のみ / curve のみ は却下）
- **D-12: 6軸（year/month/競馬場/頭数/人気帯/オッズ帯）全て生成** — EVAL-03 を完全履行。計算量・レポート肥大は受容（segment 評価は軽量・評価専用フェーズ）。ユーザー選択: 全6軸。（優先3軸 / 全6軸scalar+優先軸curve は却下）

### Claude's Discretion（研究者/計画者に委ねる）
- **構造的 BLOCK 閾値の具体値** — D-02 の「baselines 全敗」の定義（全 baselines vs BL-1 のみ・LogLoss と Brier の両方か一方か）と「sum(p) 著乖離」の閾値（理論値の ±X%・large/small バケット別）を§15.2 と実データ分布に照らして確定
- **新キャリブ指標の実装詳細** — quantile max_dev/ECE/MCE の bin 数（CALIBRATION_CURVE_BINS 準拠 or 別途）・MIN_BIN_COUNT・実装箇所（`src/model/evaluator.py` 拡張 vs 新モジュール）。bit-identical 再現性のため純 NumPy（bincount/digitize）実装（debug Specialist 指摘 (b)/(f) 準拠）
- **タイブレーク規則の具体化** — D-08 の固定優先順位（backtest 回収率 → 計算コスト → その他）の決定的順序
- **統合評価経路の設計** — `scripts/run_evaluation.py`（仮）のような CLI で Phase 4/5 成果物を統合読込 → ゲート判定 → segment 評価 → レポート生成・主モデル確定を一本化するか、既存 `run_train_predict.py`/`run_backtest.py` に評価ステップを追加するか
- **reports/06-evaluation.{md,json} 慣例** — Phase 4 の `04-eval`/Phase 5 の `05-backtest` パターン踏襲・`reports/06-segments/`（JSON+HTML）のディレクトリ構成
- **segment 評価モジュールの配置** — `src/model/segment_eval.py`（仮）等。`evaluator.py` の calibration curve binning 契約を再利用
- **Plotly HTML のレイアウト** — curve 重ね描きの軸/凡例/色分け・scalar 表の併記形式
- **テスト構成（§17.3）** — ゲート判定ロジックの単体テスト（構造的 BLOCK が正しく発火・曖昧基準が WARN）・segment 評価の contract テスト・bit-identical 再現性の回帰テスト
- **`is_primary` フラグの DB スキーマ影響** — `prediction.fukusho_prediction` への `is_primary` 列追加（NULL 許容・DEFAULT false・既存行の backfill）・GRANT・CHECK 制約

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §15.1 — 評価指標（複勝的中率/回収率/損益/最大DD/購入点数/Brier/LogLoss/Calibration Curve + year/month/競馬場/頭数/人気帯/オッズ帯 安定性）。EVAL-01/03 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §15.2 — 確率品質受入基準（年別 Calibration 極端反転なし・bin 実測率単調-ish・LogLoss/Brier の baselines 超過・`sum(p)` 平均の理論値適合 8頭以上2.7-3.3/5-7頭1.8-2.2 + median/SD/p10/p90）。EVAL-02/D-01/D-02/D-03 の根拠
- `docs/keiba_ai_requirements_v1.3.md` §15.3 — Calibration 評価軸（全体/各 segment）。EVAL-03/D-10/D-11/D-12 の根拠
- `docs/keiba_ai_requirements_v1.3.md` §14.2 — baselines（BL-1..5）の定義・BL-3 §14.2 caveat（同一情報条件の比較でない）。D-02「baselines 全敗」の対象特定
- `docs/keiba_ai_requirements_v1.3.md` §19.1 — 再現性（モデルバージョン・特徴量スナップショット・ラベル定義バージョン・`odds_snapshot_policy`/`backtest_strategy_version` 保存）。D-09 `is_primary` provenance・Phase 4 SC#4 bit-identical 維持の根拠

### debug セッション（キャリブ指標再設計の直接的インプット・必読）
- `.planning/debug/calib-maxdev-vs-baselines.md` — **uniform `calibration_max_dev` の構造バイアス診断（BL-1 bin 退化・主モデル高確率域 pred>0.7 過信）+ Resolution（Phase 6 で quantile/ECE/MCE 併記・高確率域対策・BL-1 比較公平性明記）**。D-04/D-05/D-06 の全ての根拠。実データの bin 分布・count・max_dev 数値（LightGBM guarded 0.0987 / CatBoost 0.2579 不変）・Specialist SUGGEST_CHANGE 8点（純 NumPy bincount/digitize・y_pred==1.0 clip・整列 assert・bit-identical）

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/04-model-prediction/04-CONTEXT.md` — **D-03（主モデル確定は Phase 6 評価ゲートまで委ねる・両モデル backtest）/ D-04（主モデル選定基準=Calibration 重視・事前登録）** が Phase 6 の前提。prediction テーブル（model_type/model_version）・`calibration_max_dev_guarded` 併記（commit 9fce782）・SC#4 bit-identical（num_threads=1/seed=42/FIXED_REPRODUCE_TS）
- `.planning/phases/05-ev-backtest/05-CONTEXT.md` — **D-03（§15.5 フル行列 backtest・実データ完走）/ D-04（BL-3 投資ROI比較）/ D-05（返還・中止会計）**。`backtest.fukusho_backtest` テーブル・`reports/05-backtest.{md,json}`・BACK-04 全候補一括報告（後知恵 winner 単独禁止）。Phase 6 統合評価の入力

### コード契約（実装済み・Phase 6 が消費・拡張・scout 確認済み）
- `src/model/evaluator.py` — **`compute_metrics`（brier/logloss/auc/sum_p_mean/median/p10/p90/calibration_max_dev/guarded）/ `check_sum_p_distribution`（§15.2 機械検査・diagnostic warning）/ `build_comparison_table`（BL-1..5 + 主モデル・D-04 note）/ `evaluate_all_models`（統合エントリ）**。METRIC_COLUMNS・CALIBRATION_CURVE_BINS=10/STRATEGY=uniform/MIN_BIN_COUNT=30 定数。**全体評価のみ実装済み・segment 別・ゲート判定・quantile/ECE/MCE は Phase 6 拡張対象**
- `src/ev/metrics.py` — backtest metrics（回収率/損益/maxDD/購入点数/effective_bet_count/refund_count・`profit_loss` 集計式・`max_drawdown` cummax-cumsum）。EVAL-01 統合対象
- `src/ev/report.py` — backtest report（REPORT_COLUMNS 外部定数・md+json 分離・BACK-04 winner 強調禁止）。`reports/06-evaluation` 慣例の参考
- `src/model/calibrator.py` / `src/utils/calibrator.py` — `fit_prefit_calibrator`（FrozenEstimator prefit idiom・cv='prefit' isotonic/<1000件 sigmoid・strict-later disjoint guard）。D-06（キャリブ再調整しない）の対象外確認
- `src/model/orchestrator.py` / `src/model/predict.py` — `PREDICTION_COLUMNS`/`MODEL_TYPE_TO_SHORT`（lightgbm→lgb/catboost→cb）。prediction テーブル schema 理解
- `src/db/schema.py` — `SCHEMAS=[...,"prediction","backtest"]`。`is_primary` 列追加対象の prediction テーブル DDL
- `src/db/prediction_load.py` — `load_predictions`（model_version-scoped staging-swap）。`is_primary` フラグ付与の参考
- `reports/04-eval.{md,json}` / `reports/05-backtest.{md,json}` — Phase 6 統合評価の入力データ・レポート慣例

### プロジェクト計画・状態
- `.planning/ROADMAP.md` — Phase 6 成功基準 #1-#3（EVAL-01/02/03・§15.2/§15.3 ゲート）・8フェーズ strict DAG
- `.planning/REQUIREMENTS.md` — EVAL-01/02/03（Phase 6 割当）・全25要件トレーサビリティ
- `.planning/STATE.md` — Phase 6 移行状態・Phase 5 完了（実データ backtest 完走）・Decisions 履歴
- `CLAUDE.md` — §15.2 キャリブレーション・hybrid gate・stack patterns（Plotly 推奨・純 NumPy bit-identical・manual hyperparams・MLflow/Optuna defer）・リーク防止プリミティブ・プロジェクト指示として权威

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/model/evaluator.py`** — 確率品質評価の土台。`compute_metrics`（全体指標）・`_compute_calibration_max_dev`/`_compute_calibration_max_dev_guarded`（binning 契約固定・純 NumPy digitize/bincount/clip）・`check_sum_p_distribution`（§15.2 large/small バケット検査）・`build_comparison_table`（D-04 note 列）・`write_eval_report`（md+json 分離・byte-reproducible）。Phase 6 は quantile max_dev/ECE/MCE 追加・segment 別拡張・ゲート判定追加の直接拡張対象
- **`src/ev/metrics.py` + `src/ev/report.py`** — backtest 品質指標（回収率/損益/maxDD/購入点数）と report 生成。EVAL-01 統合の相手・REPORT_COLUMNS md/json 1:1 検証パターン（LOW-05）の再利用
- **`_df_to_markdown_table`（evaluator.py）** — tabulate 非依存の手動 Markdown 表生成。segment 表でも再利用
- **`src/utils/calibrator.py::fit_prefit_calibrator`** — キャリブの現状実装（D-06 で触らないが、高確率域過信の可視化で calib_method 列を参照）
- **`reports/04-eval.json` / `reports/05-backtest.json`** — 構造化データ。Phase 6 統合評価が読込・マージして `reports/06-evaluation.{md,json}` を生成

### Established Patterns
- **hybrid gate（Phase 1 D-01 / Phase 2 D-02）:** 構造的欠陥=BLOCK（pytest/CI fail）・量的異常=参考レポート。D-01/D-02/D-03 の受入ゲートはこの延長（モデル破綻のみ BLOCK・曖昧基準は WARN/人間判定）
- **binning 契約固定・純 NumPy bit-identical（debug Specialist 指摘）:** calibration curve の bin 数/strategy/MIN_BIN_COUNT を定数で固定し・`np.linspace`+`np.digitize`+`np.bincount`+`np.clip` で bin ごとに (mean_pred, frac_pos, count) を自前計算（pandas.groupby/sort は等値要素 index 依存で再現性リスク → 不使用）。quantile max_dev も同思想で data-driven bin_edges を構築
- **事前登録指標の不変（T-04-24 回避）:** 結果を見てから選定基準をすり替えない。D-04（uniform max_dev 温存）・D-07（D-04 事前登録基準で人間判断）の根拠
- **md + json 分離出力（review LOW）:** Markdown（人間確認）と JSON（`sort_keys=True` byte-reproducible・機械消費）を分離。`reports/06-evaluation.{md,json}` + `reports/06-segments/`（JSON+Plotly HTML）で踏襲
- **5層スキーマ分離（Phase 3 D-08 + Phase 4 D-05）:** feature=不変 Parquet・prediction/backtest=queryable Postgres（結果層）。D-09 `is_primary` フラグは prediction テーブル（queryable・Phase 7 SQL 照会）に付与
- **raw read-only / 評価専用フェーズ:** Phase 6 は READ のみ（readonly ロール）+ reports/ 出力 + prediction テーブルへの `is_primary` フラグ更新（etl ロール・model_version-scoped・staging-swap idempotent 慣例）。モデル再学習・予測再生成なし（Phase 4 SC#4 維持）

### Integration Points
- **READ（readonly ロール）:**
  - `prediction.fukusho_prediction`（両モデル予渓・`model_type`/`model_version`/`p_fukusho_hit`/`calib_method`/`race_key`/`entry_count`/`split`/`fukusho_hit`）
  - `backtest.fukusho_backtest`（実データ backtest 結果・5窓フル行列・回収率/損益/maxDD/購入点数）
  - `label.fukusho_label`（的中判定 `fukusho_hit_validated`・`race_date`/`entry_count`/`jyocd`/競馬場/人気/オッズ の segment 軸）
  - `reports/04-eval.{md,json}` / `reports/05-backtest.{md,json}`（統合評価の入力）
  - `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet`（必要時）
- **WRITE（etl ロール・search_path 拡張）:**
  - `prediction.fukusho_prediction` へ `is_primary` フラグ更新（D-09・選定モデル=true/未選定=false・既存行 backfill）
  - `reports/06-evaluation.{md,json}`（統合評価レポート・ゲート判定結果・主モデル確定記録）
  - `reports/06-segments/`（per-year/month/競馬場/頭数/人気帯/オッズ帯 の JSON + Plotly HTML）
- **CONSUMED BY（下流フェーズ）:**
  - Phase 7（Presentation）: Streamlit が `is_primary=true` の主モデルを表示・segment JSON を消費して動的 calibration curve 描画・OUT-01/02 CSV 出力
  - Phase 8（Adversarial Audit）: 受入ゲート判定ロジック（構造的 BLOCK 発火・曖昧基準 WARN）・`is_primary` フラグの後知恵すり替え検出・segment 評価の PIT 正当性の対抗的監査（TEST-01）

</code_context>

<specifics>
## Specific Ideas

- **現状データでの主モデル優位（debug レポート・reports/04-eval.json）** — LightGBM は Calibration（guarded 0.0987 vs CatBoost 0.2579 不変）・AUC(0.732 vs 0.718)・Brier(0.15222 vs 0.15453)・LogLoss(0.47488 vs 0.48243) 全てで CatBoost より優位。両モデルとも順序付け性能は baselines を上回る。D-04 基準（Calibration 重視）でも新指標（quantile/ECE/MCE）含めて LightGBM 優位の公算大だが、Phase 6 は事前登録基準を適用して確定するプロセス自体が対象（D-07 人間判断・理由記録）
- **高確率域過信の局所性（debug Evidence）** — LightGBM bin 0-6 は dev<0.05 で良好・bin 7-8（pred>0.7）で過信（isotonic が 1.0 に saturate）。CatBoost も bin 0-6 dev<0.06・bin 8（count=59>30・ガード対象外）に残存 dev=0.2579。D-06 で可視化のみ（キャリブ再調整は将来 Optuna）。segment 評価（D-10/D-11/D-12）でこの局所性を軸別に可視化
- **`calibration_max_dev_guarded` の非対称性（debug）** — LightGBM worst bin (count=13<30) はガードで除外され max_dev 0.2308→0.0987 に改善・CatBoost worst bin (count=59>30) はガード対象外で 0.2579 不変。比較表議論ではこの非対称性を明示（D-05 の新指標で両モデルを公平評価）
- **Phase 4 SC#4 bit-identical 維持** — Phase 6 は評価専用・モデル再学習・予測再生成を行わない（D-06）。`prediction.fukusho_prediction` は Phase 4 成果物をそのまま消費。`is_primary` フラグ追加のみ（D-09）
- **segment 軸のデータ経路** — year/month= `race_date`・競馬場= `jyocd`・頭数= `entry_count`・人気帯= `ninki`（人気）・オッズ帯= 複勝オッズ下限。`label.fukusho_label` と `prediction.fukusho_prediction` にこれら軸が揃うことを確認（researcher 確定）
- **BL-1 比較公平性（debug Resolution #4）** — BL-1 は「順序付け能力ゼロ（AUC=0.574）の副産物」で calibration_max_dev が構造的極小。D-02「baselines 全敗」の判定や比較表では BL-1 のこの性質を注記（uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない旨）

</specifics>

<deferred>
## Deferred Ideas

- **Phase 7（Presentation）:** Streamlit 動的 calibration curve 描画（segment JSON 消費）・`is_primary=true` 主モデル表示・予測/backtest CSV 出力（OUT-01/02）。Phase 6 は JSON+Plotly HTML データ生成まで（動的 UI なし）
- **Phase 8（Adversarial Audit）:** 受入ゲート判定ロジックの対抗的監査（構造的 BLOCK が正しく発火・曖昧基準が WARN に留まる）・`is_primary` フラグの後知恵すり替え検出・segment 評価の PIT 正当性・固定 seed 再現性（TEST-01）
- **高確率域過信の根本対処（将来 Optuna 導入時）:** isotonic の高確率域 clip（y_max<1.0）・sigmoid 併用・calib slice 拡大・特徴量/ハイパラ見直し。D-06 で可視化のみ・Phase 6 では手を付けない（Phase 4 SC#4 維持・§21 defer）
- **キャリブ指標の更なる拡張（将来）:** Binning-in-quantile の bin 数チューニング・segment 別 ECE の重み付け最適化・Platt scaling 比較。Phase 6 は標準的 quantile/ECE/MCE 併記（D-05）

</deferred>

---

*Phase: 6-Evaluation & Calibration Gates*
*Context gathered: 2026-06-23*
