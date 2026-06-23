---
phase: 06-evaluation-calibration-gates
verified: 2026-06-23T16:30:00Z
status: gaps_found
score: 11/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: null
  note: "初回検証（prior VERIFICATION.md なし）"
gaps:
  - truth: "SC#1/EVAL-01: 開発者が評価スイートを実行し 複勝的中率, 回収率, 損益, 最大ドローダウン, 購入点数, Brier Score, LogLoss, Calibration Curve を受け取る — うち『複勝的中率 (hit_rate)』が reports/06-evaluation.{md,json} の backtest_summary に欠落"
    status: failed
    reason: "scripts/run_evaluation.py::aggregate_backtest_for_model（行 547-555 の戻り値 dict）が hit_rate を集約対象から除外。reports/05-backtest.json の元データには hit_rate フィールドが存在する（LightGBM 行: hit_rate=0.0886 等・src/ev/metrics.py 行21 で計算済み）が・Phase 6 統合評価経路に伝達されず。要件定義書 §15.1 行964『複勝的中率』・EVAL-01『複勝的中率/回収率/損益/最大ドローダウン/購入点数/Brier/LogLoss/Calibration Curve』・ROADMAP SC#1 の8指標の最初に明示。"
    artifacts:
      - path: "scripts/run_evaluation.py"
        issue: "aggregate_backtest_for_model の戻り値 dict（行547-555）に hit_rate キーが無い。representatives 各行から hit_rate を平均して含める必要がある"
      - path: "reports/06-evaluation.md"
        issue: "主モデル比較表の bt_* 列に bt_hit_rate が無い"
      - path: "reports/06-evaluation.json"
        issue: "backtest_summary.by_model.{lightgbm,catboost} に hit_rate キーが無い"
    missing:
      - "aggregate_backtest_for_model の戻り値に hit_rate を追加（representatives の重み付き平均 or 単純平均・reports/05-backtest.json の hit_rate フィールドを消費）"
      - "reports/06-evaluation.md の主モデル比較表に bt_hit_rate 列を追加"
      - "reports/06-evaluation.json の backtest_summary.by_model に hit_rate を追加"
      - "tests/model/test_run_evaluation.py に backtest_summary に hit_rate が含まれることの assertion を追加"
warnings:
  - truth: "reports/06-evaluation.json が strict JSON 仕様（RFC 8259）に準拠"
    status: uncertain
    reason: "reports/06-evaluation.json に NaN リテラルが6箇所含まれる（segment odds_band.__MISSING__・entry_count.6.0 の max_dev_guarded/mce_guarded/ece_*）。Python 標準 json.loads はデフォルトで NaN を許容するためパース成功するが・strict JSON モードや JavaScript JSON.parse・一部の他言語 JSON パーサでは失敗する可能性。must_have truth『sort_keys=True ensure_ascii=False で byte-reproducible』自体は満たす（同一プロセスで再生成すれば同値）。PLAN の test_segment_json_schema（json.dumps でシリアライズ可能）も満たす。ただし Phase 7 Streamlit 消費時・外部ツール連携で strict パース失敗のリスクあり。"
    recommendation: "json.dump(..., allow_nan=False) + 欠損値は null に正規化するか・NaN を含む segment を出力から除外する。修正は小（segment_eval.write_segment_reports と run_evaluation.generate_evaluation_reports の json.dump 呼出に allow_nan=False 追加 + NaN→None 変換）"
---

# Phase 6: Evaluation & Calibration Gates 検証レポート

**Phase Goal:** 確率品質受入基準（calibration, Brier, LogLoss, sum(p), stability-by-segment）がユーザーに結果を示す前に検証される — §15.2/§15.3 ゲート
**Verified:** 2026-06-23T16:30:00Z
**Status:** gaps_found
**Re-verification:** No — 初回検証

## 目標達成 (Goal Achievement)

### Observable Truths（ROADMAP SC + PLAN must_haves 統合）

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | SC#1: 開発者が評価スイートを実行し 的中率/回収率/損益/maxDD/購入点数/Brier/LogLoss/Calibration Curve を受け取る | ✗ FAILED | 的中率(hit_rate)が reports/06-evaluation.{md,json} の backtest_summary に欠落（aggregate_backtest_for_model 行547-555 が hit_rate を集約対象外）。他7指標は全て存在。詳細は Gaps Summary |
| 2   | SC#2: 受入ゲート通過（年次 Calibration 極端反転なし・bin 単調-ish・LogLoss/Brier が baselines 超過・sum(p) 理論値適合・median/SD/p10/p90 報告） | ✓ VERIFIED | gate_verdict=WARN（非 BLOCK・baselines_all_lose=False・SC#2 達成）。年次反転: 2024 bin_inversions=0/spearman=1.0。bin 単調: lightgbm inversions=0/spearman=1.0・catboost inversions=1/spearman=0.983。LogLoss+Brier で BL-1/4/5 全てに勝利（reports/06-evaluation.md 行84 SC#2/BLOCK 対称性注記）。sum(p) median/p10/p90 報告済（lightgbm: median=3.0004/p10=1.9317/p90=4.1548）。注: sum_p_violation=True だが AND 条件未満で WARN 停留（D-02 正常動作） |
| 3   | SC#3: segment 安定性評価が per-year/month/競馬場/頭数/人気帯/オッズ帯 Calibration Curve を生成 | ✓ VERIFIED | reports/06-segments/ に6軸×{json,html}=12ファイル + plotly.min.js 共有1ファイル。各 JSON の axis_name が6軸（year/month/jyocd/entry_count/ninki/odds_band）と一致。SEGMENT_AXES 定数（segment_eval.py 行80-87）定義通り。ninki=4帯(1-3/4-6/7-9/10+)・odds_band=4帯(1.0-2.9/3.0-4.9/5.0-9.9/10+) の banding 関数実装済み |
| 4   | EVAL-01: Brier/LogLoss/AUC/calibration/sum(p)/backtest 指標が計算される | ✓ VERIFIED（的中率を除く） | evaluator.compute_metrics（行172）+ check_sum_p_distribution（行588）+ src/ev/metrics.py（hit_rate 含む）。reports/06-evaluation.{md,json} に brier/logloss/auc/sum_p_*/calibration_max_dev と backtest_summary（recovery_rate/profit_loss/max_drawdown/effective_bet/selected）存在。hit_rate は gap #1 参照 |
| 5   | EVAL-02: 受入ゲート（年次反転・bin 単調・baseline 超過・sum(p) 適合）が検証される | ✓ VERIFIED | check_acceptance_gate（evaluator.py 行874）実装・D-02 AND 条件（行964 block_triggered = baselines_all_lose and sum_p_violation）正確・compute_monotonicity_warn（行1018）+ compute_yearly_inversion_warn（行1058）実装。reports gate_result に全フィールド存在 |
| 6   | EVAL-03: 6軸 segment 安定性 + Calibration Curve 評価 | ✓ VERIFIED | Truth #3 と同一証拠。evaluate_segment_axis（segment_eval.py 行144）+ evaluate_all_segments（行271）実装。MIN_BIN_COUNT=30 未満 skip 実装 |
| 7   | D-04 事前登録指標 calibration_max_dev（uniform・ガードなし）が不変 | ✓ VERIFIED | reports/06-evaluation.json: lightgbm calibration_max_dev=0.2307692308・catboost=0.2578929877・bl1=0.001425964（ROADMAP 行170 / reports/04-eval.json と一致）。test_evaluator.py で回帰固定化（test_calibration_max_dev_report_value_match） |
| 8   | D-07/D-09: 主モデル確定 = lightgbm・is_primary フラグ付与・両モデル行保持 | ✓ VERIFIED（live DB 実検証） | reports/06-evaluation.{md,json} に primary_model=lightgbm・selection_reason・tiebreak_applied=backtest_recovery_rate。実 DB クエリ: is_primary 列=boolean NOT NULL DEFAULT false・lightgbm=True(22213行)・catboost=False(22213行)・合計44426行（両モデル保持・D-09 完全履行）。set_primary_model（prediction_load.py 行443）post-condition assert 実装 |
| 9   | D-10/D-11/D-12: JSON + Plotly HTML 両方・curve 並列 + scalar 表・6軸全生成 | ✓ VERIFIED | reports/06-segments/{axis}.{json,html}×6 + 共有 plotly.min.js（include_plotlyjs='directory'・C13）。segment JSON に curve + scalar（ece_quantile/ece_uniform/mce_guarded/max_dev_guarded/n_samples）両方 |
| 10  | REVIEW HIGH#8 正直注記: 部分証明（主モデルは Brier/LogLoss/AUC で BL 優位だが Calibration では BL-1/BL-4 に劣る）が隠されず記録される | ✓ VERIFIED | reports/06-evaluation.md 行80『BL-1 caveat: 順序付け能力ゼロ (AUC≈0.57) の副産物で calibration_max_dev が構造的極小・uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない』・reports/06-evaluation.json bl1_caveat・ROADMAP 行170『AI 付加価値: 部分証明…calibration_max_dev では BL-1=0.001426・BL-4=0.044928 に劣る（LightGBM=0.230769）』の3箇所で正直記録 |
| 11  | BLOCK 発火時 fail-loud（REVIEW HIGH#6）・--primary-model 省略時は推奨のみ（REVIEW C7） | ✓ VERIFIED | run_evaluation.py generate_evaluation_reports で atomic write 後 RuntimeError。--primary-model 引数（行148）+ build_recommended_primary_model（行558）で推奨表。現データは WARN ため未発火だがコードパス実装済み・test_run_evaluation.py で BLOCK 発火検証 |
| 12  | reproducibility_checks.race_id_split_disjoint 記録（§8.4 聖域再検証・REVIEW Codex MEDIUM/N3） | ✓ VERIFIED | reports/06-evaluation.json gate_result.reproducibility_checks に race_id_split_disjoint='N/A'（split データ不足・train 空・Phase 4 GroupTimeSeriesSplit 担保の注記）。check_race_id_split_disjoint（run_evaluation.py 行421）実装 |

**Score:** 11/12 truths verified（1 FAILED: SC#1 の複勝的中率欠落）

### 必須成果物 (Required Artifacts)

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/model/evaluator.py` | quantile_max_dev/ECE/MCE + check_acceptance_gate + compute_monotonicity_warn + compute_yearly_inversion_warn（D-04 事前登録指標不変） | ✓ VERIFIED | 1130行・全関数実装（行492/512/543/874/1018/1058）・METRIC_COLUMNS_EXTENDED（行100）・SUM_P_BLOCK_THRESHOLD=0.30（行110）・COMPARABLE_BASELINES=('bl1','bl4','bl5')（行114） |
| `src/model/segment_eval.py` | 6軸 segment 別 calibration curve + scalar + Plotly HTML（D-10/D-11/D-12） | ✓ VERIFIED | 503行・SEGMENT_AXES 6軸（行80）・_ninki_band/_odds_band banding（行120/129）・evaluate_segment_axis（行144）・evaluate_all_segments（行271）・render_segment_curves_html（行356）・write_segment_reports（行427）。evaluator.py binning 契約 import（行53-60） |
| `scripts/run_evaluation.py` | 統合評価 CLI（EVAL-01/02/03・SC#1/2/3） | ⚠️ PARTIAL | 1343行・CLI 実装済み。ただし aggregate_backtest_for_model（行495-555）が hit_rate を集約対象外 → SC#1 の複勝的中率が reports に欠落（gap #1） |
| `reports/06-evaluation.md` | 統合評価レポート（ゲート判定・主モデル比較表・確定記録・segment サマリ・注記） | ⚠️ PARTIAL | ゲート判定・比較表・確定記録・segment サマリ・注記（部分証明含む）全て存在。ただし bt_hit_rate 列欠落（gap #1） |
| `reports/06-evaluation.json` | 機械可読・byte-reproducible・Phase 7 消費 | ⚠️ PARTIAL | sort_keys/ensure_ascii=False で生成・Python json でパース成功。ただし (a) backtest_summary に hit_rate 欠落（gap #1）・(b) NaN リテラル6箇所で strict JSON 仕様違反（warning） |
| `reports/06-segments/` | 6軸×{json,html} + plotly.min.js | ✓ VERIFIED | 12ファイル + plotly.min.js（4.8MB・共有1ファイル・C13）。全6軸の axis_name 確認済み |
| `src/db/schema.py` | PREDICTION_ADD_IS_PRIMARY_SQL + APPLY_ORDER 拡張 | ✓ VERIFIED | 行109-119（idempotent ALTER・NOT NULL DEFAULT false・CHECK 制約）・行331 APPLY_ORDER 追加 |
| `src/model/predict.py` | PREDICTION_COLUMNS 16列（is_primary 末尾） | ✓ VERIFIED | 実行確認: len=16・is_primary in columns・last=is_primary |
| `src/db/prediction_load.py` | set_primary_model + _df_to_prediction_tuples の is_primary 型処理 | ✓ VERIFIED | 行96 _BOOL_COLS={'is_primary'}・行443 set_primary_model（post-condition assert・両モデル保持・idempotent） |
| `tests/model/test_evaluator.py` | evaluator.py Phase 4 契約固定化 | ✓ VERIFIED | 27KB・77 passed |
| `tests/model/test_evaluator_gate.py` | ゲート判定ロジック単体テスト | ✓ VERIFIED | 20KB・GREEN |
| `tests/model/test_segment_eval.py` | segment 評価 contract テスト | ✓ VERIFIED | 18KB・GREEN |
| `tests/model/test_segment_axis_columns.py` | segment 6軸カラム経路確認（実 DB） | ✓ VERIFIED | 12KB・GREEN |
| `tests/model/test_run_evaluation.py` | run_evaluation E2E smoke | ✓ VERIFIED | 29KB・GREEN |
| `tests/db/test_is_primary_flag.py` | is_primary migration・idempotency・両モデル保持（requires_db） | ✓ VERIFIED | 26KB・GREEN |
| `pyproject.toml` / `uv.lock` | plotly + scipy 明示依存 | ✓ VERIFIED | pyproject.toml 行28-29・uv.lock 行174/183（plotly>=6.8.0・scipy>=1.17.1） |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `scripts/run_evaluation.py` | `src/model/evaluator.py` | evaluate_all_models / check_sum_p_distribution / check_acceptance_gate / compute_monotonicity_warn / build_comparison_table import | ✓ WIRED | 行76-91 で import・全関数呼出確認 |
| `scripts/run_evaluation.py` | `src/model/segment_eval.py` | evaluate_all_segments / write_segment_reports import | ✓ WIRED | 行93-95 で import・evaluate_integrated（行686）で呼出 |
| `scripts/run_evaluation.py` | `src/db/prediction_load.py::set_primary_model` | --primary-model 引数で is_primary UPDATE | ✓ WIRED | 行73 import・行148 --primary-model 引数・live DB で lightgbm=True 確認済み |
| `src/model/segment_eval.py::evaluate_segment_axis` | `src/model/evaluator.py::_compute_calibration_curve_bins` | binning 契約再利用（uniform/10bins/MIN_BIN_COUNT=30） | ✓ WIRED | 行53-60 import・bit-identical 保証 |
| `src/model/segment_eval.py::render_segment_curves_html` | `plotly.graph_objects.Figure.write_html` | include_plotlyjs='directory' で共有 plotly.min.js | ✓ WIRED | 6 HTML 全て `src="plotly.min.js"` 参照確認 |
| `src/db/schema.py::PREDICTION_ADD_IS_PRIMARY_SQL` | `scripts/run_apply_schema.py::APPLY_ORDER` | idempotent ALTER 追加 | ✓ WIRED | schema.py 行331 に ('prediction_add_is_primary', ...) 追加・live DB で列存在確認 |
| `src/model/predict.py::PREDICTION_COLUMNS` | `src/db/prediction_load.py::_df_to_prediction_tuples` | 16列順 tuple 構築 | ✓ WIRED | _BOOL_COLS={'is_primary'}・None→False 正規化実装 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `reports/06-evaluation.json` comparison_table | brier/logloss/auc/calibration_max_dev | evaluator.compute_metrics（実 DB prediction 22,213行） | ✓ 実データ（lightgbm brier=0.152216 等・reports/04-eval.json と一致） | ✓ FLOWING |
| `reports/06-evaluation.json` backtest_summary | recovery_rate/profit_loss/max_drawdown | reports/05-backtest.json comparison_table（実 backtest 25件） | ✓ 実データ（lightgbm recovery=0.7022 等）・ただし hit_rate は伝達漏れ | ⚠️ PARTIAL |
| `reports/06-segments/year.json` | curve.mean_pred/frac_pos/count | evaluator._compute_calibration_curve_bins（実 prediction+label JOIN） | ✓ 実データ（2024 n_samples=22213・9 bins・count 合計=22213） | ✓ FLOWING |
| `reports/06-evaluation.json` primary_model | model_type/selection_reason | --primary-model lightgbm（人間判断・D-07）→ set_primary_model | ✓ live DB に反映（lightgbm=True/22213行） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase 6 テストスイート GREEN | `uv run pytest tests/model/test_evaluator*.py tests/model/test_segment*.py tests/model/test_run_evaluation.py tests/db/test_is_primary_flag.py -q` | 77 passed, 1 skipped（reports/04-eval.json stale・Plan 06-05 で代替検証済み注記） | ✓ PASS |
| evaluator.check_acceptance_gate D-02 AND 条件 | コード確認（evaluator.py 行964） | `block_triggered = baselines_all_lose and sum_p_violation` 正確・WARN 分離（行983-1002） | ✓ PASS |
| 実 DB is_primary 状態 | `psycopg3 で SELECT model_type, is_primary, count(*)` | catboost=False/22213・lightgbm=True/22213・合計44426・列=boolean NOT NULL DEFAULT false | ✓ PASS |
| JSON パース性（Python） | `python -c "import json; json.load(open('reports/06-evaluation.json'))"` | パース成功（Python json は NaN 許容） | ✓ PASS（strict では ⚠️） |
| segment HTML の plotly.min.js 共有参照 | `grep 'src="plotly' reports/06-segments/*.html` | 6ファイル全て `src="plotly.min.js"` | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| （該当なし） | Phase 6 は scripts/*/tests/probe-*.sh 形式の probe を宣言していない・runnable CLI（scripts/run_evaluation.py）は behavioral spot-check で検証済み | — | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| EVAL-01 | 06-02/06-05 | 複勝的中率/回収率/損益/最大ドローダウン/購入点数/Brier/LogLoss/Calibration Curve を算出 | ✗ BLOCKED | 的中率(hit_rate)が reports/06-evaluation.{md,json} に欠落（gap #1）。他7指標は全て算出・reports に存在。計算自体は src/ev/metrics.py で実装済み・reports/05-backtest.json に存在するが Phase 6 統合レイヤーで伝達漏れ |
| EVAL-02 | 06-02/06-05 | 確率品質受入基準（年次Calibration・bin単調・LogLoss/Brier baseline超過・sum(p)適合・median/SD/p10/p90） | ✓ SATISFIED | gate_verdict=WARN（非 BLOCK）・全条件判定実装・reports gate_result に全フィールド・年次反転/単調 WARN 指標実測値記録 |
| EVAL-03 | 06-03/06-05 | 年/月/競馬場/頭数/人気帯/オッズ帯 別の安定性 + Calibration Curve | ✓ SATISFIED | reports/06-segments/ に6軸×{json,html}・SEGMENT_AXES 6軸定義・各 segment に curve + scalar |

**Orphaned requirements:** なし。REQUIREMENTS.md は EVAL-01/02/03 全てを Phase 6 にマッピング（行132-134）・PLAN も全てをカバー。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| （該当なし） | — | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER マーカー無し | — | — |
| `reports/06-evaluation.json` | 1行目（単一行 JSON 内） | `NaN` リテラル6箇所（odds_band.__MISSING__・entry_count.6.0 の scalar） | ⚠️ WARNING | strict JSON 仕様違反・Phase 7 Streamlit や外部パーサで失敗のリスク。Python json ではパース成功。修正小（allow_nan=False + NaN→null） |
| `src/model/evaluator.py` | 1090 | `return {}` | ℹ️ INFO | 正当なガード句（compute_yearly_inversion_warn 入力空時の安全網）・スタブでない |
| `scripts/run_evaluation.py` | 517 | `return {}` | ℹ️ INFO | 正当なガード句（aggregate_backtest_for_model 該当行無し時）・スタブでない |

### Human Verification Required

本フェーズは gaps_found（SC#1 複勝的中率欠落）のため、human_verification セクションは gap 解消後に再検証で処理される。下記は参考情報（gap 解消後の確認項目）:

1. **SC#1 複勝的中率 追加後の確認** — gap #1 修正後、reports/06-evaluation.md の比較表に bt_hit_rate 列が表示され・lightgbm の hit_rate（~0.089）が catboost と比較できることを目視確認
   - Expected: lightgbm bt_hit_rate ≈ 0.07-0.09（reports/05-backtest.json の lightgbn 行と概ね一致）
   - Why human: 数値の表示形式・桁数の視認性は grep では判定困難

### Gaps Summary

**単一 gap（修正小）:** SC#1/EVAL-01 が要求する8指標の最初「複勝的中率 (hit_rate)」が reports/06-evaluation.{md,json} の backtest_summary に欠落。

**根本原因:** `scripts/run_evaluation.py::aggregate_backtest_for_model`（行495-555）が reports/05-backtest.json の comparison_table から集約する際、戻り値 dict（行547-555）に `hit_rate` を含めていない。reports/05-backtest.json の元行には `hit_rate` フィールドが存在し（LightGBM: 0.0886 等・src/ev/metrics.py 行21 で計算）、Phase 5 では正しく算出されている。Phase 6 の「統合評価経路」での伝達漏れ。

**影響範囲:**
- reports/06-evaluation.md の主モデル比較表に bt_hit_rate 列が無い
- reports/06-evaluation.json の backtest_summary.by_model に hit_rate キーが無い
- Phase 7 Streamlit が reports/06-evaluation.json を消費する際、複勝的中率を表示できない

**修正規模:** 小。`aggregate_backtest_for_model` の戻り値に `hit_rate` を追加（representatives の平均）+ reports の比較表/JSON に反映 + テスト assertion 追加。実装 ~30分。

**重要な注記:**
- この gap は Phase 6 の他の全成果物（ゲート判定・主モデル確定・segment 評価・部分証明の正直記録・is_primary live DB 反映）には影響しない。これらは全て VERIFIED。
- 主モデル選定（lightgbm）の妥当性にも影響しない（selection_reason は brier/logloss/auc/calibration/monotonicity/backtest 回収率の全指標に基づき・hit_rate は選定基準に含まれていない）。
- D-07 人間判断の記録・D-09 is_primary フラグの live DB 反映は完全に履行されている。

**副次的 WARNING（gap とは別）:** reports/06-evaluation.json に NaN リテラル6箇所。Python json ではパース成功するが strict JSON 仕様違反。Phase 7 消費時のリスクあり。修正は gap #1 と同時に対応推奨（allow_nan=False + NaN→null 変換）。

---

_Verified: 2026-06-23T16:30:00Z_
_Verifier: Claude (gsd-verifier)_
