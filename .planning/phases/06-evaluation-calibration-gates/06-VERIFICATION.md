---
phase: 06-evaluation-calibration-gates
verified: 2026-06-23T23:35:00Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 11/12
  previous_verified: "2026-06-23T16:30:00Z"
  gaps_closed:
    - "SC#1/EVAL-01 複勝的中率 (hit_rate) が reports/06-evaluation.{md,json} の backtest_summary + comparison_table に追加された（commit 15782cf）"
    - "reports/06-evaluation.json + reports/06-segments/*.json の NaN リテラルが null に正規化され・strict JSON (RFC 8259) 準拠（commit 15782cf）"
  gaps_remaining: []
  regressions: []
gaps: []
behavior_unverified_items: []
---

# Phase 6: Evaluation & Calibration Gates 検証レポート

**Phase Goal:** 確率品質受入基準（calibration, Brier, LogLoss, sum(p), stability-by-segment）がユーザーに結果を示す前に検証される — §15.2/§15.3 ゲート
**Verified:** 2026-06-23T23:35:00Z
**Status:** passed
**Re-verification:** Yes — gap closure (commit 15782cf) 後の再検証

## 目標達成 (Goal Achievement)

### Observable Truths（ROADMAP SC + PLAN must_haves 統合）

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | SC#1: 開発者が評価スイートを実行し 的中率/回収率/損益/maxDD/購入点数/Brier/LogLoss/Calibration Curve を受け取る | ✓ VERIFIED | commit 15782cf で解消。reports/06-evaluation.json backtest_summary.by_model.{lightgbm,catboost}.hit_rate 存在（lightgbm=0.0918748369・catboost=0.0867732706・reports/05-backtest.json の hit_rate≈0.0886 と整合）。reports/06-evaluation.md 比較表に bt_hit_rate 列追加（行46 ヘッダ・行53/54 値）。aggregate_backtest_for_model（run_evaluation.py 行541-552）で representatives の hit_rate 単純平均を集約 |
| 2   | SC#2: 受入ゲート通過（年次 Calibration 極端反転なし・bin 単調-ish・LogLoss/Brier が baselines 超過・sum(p) 理論値適合・median/SD/p10/p90 報告） | ✓ VERIFIED | gate_verdict=WARN（非 BLOCK）・condition_flags: baselines_all_lose=False / sum_p_violation=True（D-02 AND 条件未満で WARN 停留）。年次反転: 2024 bin_inversions=0/spearman=1.0。bin 単調: lightgbm inversions=0/spearman=1.0・catboost inversions=1/spearman=0.9833。LogLoss+Brier で BL-1/4/5 全てに勝利。sum(p) median/p10/p90 報告済（lightgbm: median=3.0004/p10=1.9317/p90=4.1548） |
| 3   | SC#3: segment 安定性評価が per-year/month/競馬場/頭数/人気帯/オッズ帯 Calibration Curve を生成 | ✓ VERIFIED | reports/06-segments/ に6軸×{json,html}=12ファイル + plotly.min.js 共有1ファイル。各 JSON の axis_name が6軸（year/month/jyocd/entry_count/ninki/odds_band）と一致。SEGMENT_AXES 定数（segment_eval.py 行80-87）定義通り |
| 4   | EVAL-01: Brier/LogLoss/AUC/calibration/sum(p)/backtest 指標（的中率含む）が計算される | ✓ VERIFIED | evaluator.compute_metrics + check_sum_p_distribution + src/ev/metrics.py（hit_rate 含む）+ aggregate_backtest_for_model で hit_rate を含む全指標が reports に集約。reports/06-evaluation.{md,json} に brier/logloss/auc/sum_p_*/calibration_max_dev と backtest_summary（hit_rate/recovery_rate/profit_loss/max_drawdown/effective_bet/selected）全て存在 |
| 5   | EVAL-02: 受入ゲート（年次反転・bin 単調・baseline 超過・sum(p) 適合）が検証される | ✓ VERIFIED | check_acceptance_gate（evaluator.py 行874）実装・D-02 AND 条件正確・compute_monotonicity_warn + compute_yearly_inversion_warn 実装。reports gate_result に全フィールド存在 |
| 6   | EVAL-03: 6軸 segment 安定性 + Calibration Curve 評価 | ✓ VERIFIED | Truth #3 と同一証拠。evaluate_segment_axis（segment_eval.py 行144）+ evaluate_all_segments（行271）実装。MIN_BIN_COUNT=30 未満 skip 実装 |
| 7   | D-04 事前登録指標 calibration_max_dev（uniform・ガードなし）が不変 | ✓ VERIFIED | reports/06-evaluation.json: lightgbm calibration_max_dev=0.2307692308・catboost=0.2578929877・bl1=0.001425964（ROADMAP 行170 / reports/04-eval.json と一致・回帰なし）。test_evaluator.py で回帰固定化 |
| 8   | D-07/D-09: 主モデル確定 = lightgbm・is_primary フラグ付与・両モデル行保持 | ✓ VERIFIED（live DB 実検証） | primary_model=lightgbm (model_version=20260620-1a-postreview-v2-lgb-v1)・tiebreak_applied=backtest_recovery_rate・comparison_table に両モデル行保持（7行: bl1-5/catboost/lightgbm）。実 DB クエリ: is_primary 列=boolean NOT NULL DEFAULT false・lightgbm=True(22213行)・catboost=False(22213行)・合計44426行（両モデル保持・D-09 完全履行・gap closure 前後で不変） |
| 9   | D-10/D-11/D-12: JSON + Plotly HTML 両方・curve 並列 + scalar 表・6軸全生成 | ✓ VERIFIED | reports/06-segments/{axis}.{json,html}×6 + 共有 plotly.min.js（include_plotlyjs='directory'・C13）。segment JSON に curve + scalar（ece_quantile/ece_uniform/mce_guarded/max_dev_guarded/n_samples）両方 |
| 10  | REVIEW HIGH#8 正直注記: 部分証明（主モデルは Brier/LogLoss/AUC で BL 優位だが Calibration では BL-1/BL-4 に劣る）が隠されず記録される | ✓ VERIFIED | reports/06-evaluation.md『BL-1 caveat: 順序付け能力ゼロ (AUC≈0.57) の副産物で calibration_max_dev が構造的極小・uniform max_dev 単独で BL-1 に劣ることは実用上の問題でない』・reports/06-evaluation.json bl1_caveat・ROADMAP 行170 の3箇所で正直記録（回帰なし） |
| 11  | BLOCK 発火時 fail-loud（REVIEW HIGH#6）・--primary-model 省略時は推奨のみ（REVIEW C7） | ✓ VERIFIED | run_evaluation.py generate_evaluation_reports で atomic write 後 RuntimeError。--primary-model 引数 + build_recommended_primary_model で推奨表。現データは WARN ため未発火だがコードパス実装済み・test_run_evaluation.py で BLOCK 発火検証 |
| 12  | reproducibility_checks.race_id_split_disjoint 記録（§8.4 聖域再検証・REVIEW Codex MEDIUM/N3） | ✓ VERIFIED | reports/06-evaluation.json gate_result.reproducibility_checks に race_id_split_disjoint='N/A'（split データ不足・train 空・Phase 4 GroupTimeSeriesSplit 担保の注記・vacuous check 回避）。check_race_id_split_disjoint（run_evaluation.py 行421）実装 |

**Score:** 12/12 truths verified（前回 11/12 → gap closure で SC#1/EVAL-01 解消）

### Re-verification Gap Closure 詳細

#### GAP #1 解消: SC#1/EVAL-01 複勝的中率 (hit_rate) 追加

**commit 15782cf** にて解消。検証結果:

| 検証項目 | 結果 | 証拠 |
| -------- | ---- | ---- |
| reports/06-evaluation.json backtest_summary.by_model.lightgbm.hit_rate | ✓ | 0.09187483687832393 |
| reports/06-evaluation.json backtest_summary.by_model.catboost.hit_rate | ✓ | 0.08677327057358354 |
| reports/06-evaluation.json comparison_table.{lightgbm,catboost}.bt_hit_rate | ✓ | lightgbm=0.0918748369 / catboost=0.0867732706 |
| reports/06-evaluation.md 比較表 bt_hit_rate 列 | ✓ | 行46 ヘッダ + 行53 (catboost=0.086773) + 行54 (lightgbm=0.091875) |
| scripts/run_evaluation.py hit_rate 集約実装 | ✓ | 行541-552: `hit_rate = sum(float(r.get("hit_rate", 0.0)) for r in representatives) / n`・戻り値 dict 行552 に `"hit_rate": hit_rate` 追加 |
| scripts/run_evaluation.py bt_hit_rate 列追加 | ✓ | 行984: `df["bt_hit_rate"] = float("nan")` 初期化・行994: `df.loc[mask, "bt_hit_rate"] = float(agg.get("hit_rate", ...))` |
| tests/model/test_run_evaluation.py hit_rate assertion | ✓ | 行152 synthetic fixture 0.09・行463-479 backtest_summary + comparison_table の bt_hit_rate 期待値 0.09 assertion |
| reports/05-backtest.json の hit_rate（元データ）との整合 | ✓ | reports/05-backtest.json ≈0.0886・Phase 6 集約値 0.0868-0.0919 は representative_policy (10min_before/30min_before) 別の平均として妥当 |

#### WARNING 解消: NaN リテラルの厳格 JSON 化 (RFC 8259)

**commit 15782cf** にて解消。検証結果:

| 検証項目 | 結果 | 証拠 |
| -------- | ---- | ---- |
| grep -wc NaN reports/06-evaluation.json | ✓ | 0 |
| grep NaN reports/06-segments/*.json（6ファイル全て） | ✓ | 全て 0 |
| strict JSON パース（parse_constant で NaN/Infinity 拒否） | ✓ | 06-evaluation.json + 6 segment JSON 全て strict parse OK |
| `: NaN` `: Infinity` `: -Infinity` リテラル grep | ✓ | 06-evaluation.json=0 / segment JSONs total=0 |
| scripts/run_evaluation.py _sanitize_nan_to_null ヘルパ | ✓ | 行928: dict/list/float 再帰走査・NaN/Inf→null 変換 |
| scripts/run_evaluation.py allow_nan=False | ✓ | 行1110: json.dumps(..., allow_nan=False)（変換漏れ時 fail-loud で ValueError） |
| src/model/segment_eval.py _sanitize_nan_to_null ヘルパ | ✓ | 行94: 同一契約・run_evaluation と対称 |
| src/model/segment_eval.py allow_nan=False | ✓ | 行502: json.dumps(..., allow_nan=False) |
| test_run_evaluation_json_strict_no_nan 新規テスト | ✓ | 行483-524: strict パーサ + NaN/Infinity リテラル grep 両方で assertion |

### 必須成果物 (Required Artifacts)

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/model/evaluator.py` | quantile_max_dev/ECE/MCE + check_acceptance_gate + compute_monotonicity_warn + compute_yearly_inversion_warn（D-04 事前登録指標不変） | ✓ VERIFIED | 1130行・全関数実装・METRIC_COLUMNS_EXTENDED・SUM_P_BLOCK_THRESHOLD=0.30・COMPARABLE_BASELINES=('bl1','bl4','bl5') |
| `src/model/segment_eval.py` | 6軸 segment 別 calibration curve + scalar + Plotly HTML（D-10/D-11/D-12）+ strict JSON | ✓ VERIFIED | 503行・SEGMENT_AXES 6軸・_sanitize_nan_to_null（行94）+ allow_nan=False（行502）追加・evaluator.py binning 契約 import |
| `scripts/run_evaluation.py` | 統合評価 CLI（EVAL-01/02/03・SC#1/2/3）・hit_rate 集約 + strict JSON | ✓ VERIFIED | 1343行・aggregate_backtest_for_model に hit_rate 追加（行541-552）・bt_hit_rate 列（行984/994）・_sanitize_nan_to_null（行928）+ allow_nan=False（行1110） |
| `reports/06-evaluation.md` | 統合評価レポート（ゲート判定・主モデル比較表・確定記録・segment サマリ・注記・bt_hit_rate） | ✓ VERIFIED | ゲート判定・比較表（bt_hit_rate 含む）・確定記録・segment サマリ・BL-1 caveat 注記全て存在 |
| `reports/06-evaluation.json` | 機械可読・byte-reproducible・strict JSON・Phase 7 消費 | ✓ VERIFIED | sort_keys/ensure_ascii=False・NaN=0・strict parse OK・backtest_summary に hit_rate 存在 |
| `reports/06-segments/` | 6軸×{json,html} + plotly.min.js・strict JSON | ✓ VERIFIED | 12ファイル + plotly.min.js（4.8MB・共有1ファイル・C13）・全 JSON で NaN=0・strict parse OK |
| `src/db/schema.py` | PREDICTION_ADD_IS_PRIMARY_SQL + APPLY_ORDER 拡張 | ✓ VERIFIED | 行109-119（idempotent ALTER・NOT NULL DEFAULT false・CHECK 制約）・行331 APPLY_ORDER 追加 |
| `src/model/predict.py` | PREDICTION_COLUMNS 16列（is_primary 末尾） | ✓ VERIFIED | 実行確認: len=16・is_primary in columns・last=is_primary |
| `src/db/prediction_load.py` | set_primary_model + _df_to_prediction_tuples の is_primary 型処理 | ✓ VERIFIED | 行96 _BOOL_COLS={'is_primary'}・行443 set_primary_model（post-condition assert・両モデル保持・idempotent） |
| `tests/model/test_evaluator.py` | evaluator.py Phase 4 契約固定化 | ✓ VERIFIED | 27KB・77 passed |
| `tests/model/test_evaluator_gate.py` | ゲート判定ロジック単体テスト | ✓ VERIFIED | 20KB・GREEN |
| `tests/model/test_segment_eval.py` | segment 評価 contract テスト | ✓ VERIFIED | 18KB・GREEN |
| `tests/model/test_segment_axis_columns.py` | segment 6軸カラム経路確認（実 DB） | ✓ VERIFIED | 12KB・GREEN |
| `tests/model/test_run_evaluation.py` | run_evaluation E2E smoke（hit_rate + strict JSON 含む） | ✓ VERIFIED | hit_rate assertion（行463-479）+ test_run_evaluation_json_strict_no_nan（行483-524）追加・GREEN |
| `tests/db/test_is_primary_flag.py` | is_primary migration・idempotency・両モデル保持（requires_db） | ✓ VERIFIED | 26KB・GREEN |
| `pyproject.toml` / `uv.lock` | plotly + scipy 明示依存 | ✓ VERIFIED | pyproject.toml 行28-29・uv.lock 行174/183 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `scripts/run_evaluation.py` | `src/model/evaluator.py` | evaluate_all_models / check_sum_p_distribution / check_acceptance_gate / compute_monotonicity_warn / build_comparison_table import | ✓ WIRED | 全関数呼出確認 |
| `scripts/run_evaluation.py` | `src/model/segment_eval.py` | evaluate_all_segments / write_segment_reports import | ✓ WIRED | evaluate_integrated で呼出 |
| `scripts/run_evaluation.py` | `src/db/prediction_load.py::set_primary_model` | --primary-model 引数で is_primary UPDATE | ✓ WIRED | live DB で lightgbm=True 確認済み |
| `scripts/run_evaluation.py::aggregate_backtest_for_model` | `reports/05-backtest.json` representatives[].hit_rate | hit_rate 単純平均（行541-552） | ✓ WIRED | gap closure で新規追加・reports/06-evaluation.json に伝達確認 |
| `scripts/run_evaluation.py::_sanitize_nan_to_null` | `json.dumps(..., allow_nan=False)` | gate_result/comparison_table/backtest_summary/segment_summary 等の NaN→null 変換 | ✓ WIRED | 行1070-1081 で全トップレベルキーに適用・行1111 allow_nan=False で fail-loud |
| `src/model/segment_eval.py::_sanitize_nan_to_null` | `json.dumps(..., allow_nan=False)` | segment JSON の curve/scalar NaN→null 変換 | ✓ WIRED | 行492-493 で curve/scalar に適用・行502 allow_nan=False |
| `src/model/segment_eval.py::evaluate_segment_axis` | `src/model/evaluator.py::_compute_calibration_curve_bins` | binning 契約再利用（uniform/10bins/MIN_BIN_COUNT=30） | ✓ WIRED | bit-identical 保証 |
| `src/model/segment_eval.py::render_segment_curves_html` | `plotly.graph_objects.Figure.write_html` | include_plotlyjs='directory' で共有 plotly.min.js | ✓ WIRED | 6 HTML 全て `src="plotly.min.js"` 参照確認 |
| `src/db/schema.py::PREDICTION_ADD_IS_PRIMARY_SQL` | `scripts/run_apply_schema.py::APPLY_ORDER` | idempotent ALTER 追加 | ✓ WIRED | live DB で列存在確認 |
| `src/model/predict.py::PREDICTION_COLUMNS` | `src/db/prediction_load.py::_df_to_prediction_tuples` | 16列順 tuple 構築 | ✓ WIRED | _BOOL_COLS={'is_primary'}・None→False 正規化実装 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `reports/06-evaluation.json` comparison_table | brier/logloss/auc/calibration_max_dev | evaluator.compute_metrics（実 DB prediction 22,213行） | ✓ 実データ（lightgbm brier=0.152216 等・reports/04-eval.json と一致） | ✓ FLOWING |
| `reports/06-evaluation.json` backtest_summary | hit_rate/recovery_rate/profit_loss/max_drawdown | reports/05-backtest.json comparison_table（実 backtest 25件）+ aggregate_backtest_for_model で hit_rate 集約 | ✓ 実データ（lightgbm hit_rate=0.091875 / recovery=0.702153 等） | ✓ FLOWING |
| `reports/06-segments/year.json` | curve.mean_pred/frac_pos/count | evaluator._compute_calibration_curve_bins（実 prediction+label JOIN） | ✓ 実データ（2024 n_samples=22213・9 bins・count 合計=22213） | ✓ FLOWING |
| `reports/06-evaluation.json` primary_model | model_type/selection_reason | --primary-model lightgbm（人間判断・D-07）→ set_primary_model | ✓ live DB に反映（lightgbm=True/22213行） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase 6 テストスイート GREEN（DB 有効） | `uv run pytest tests/model/test_run_evaluation.py tests/model/test_evaluator.py tests/model/test_evaluator_gate.py tests/model/test_segment_eval.py tests/db/test_is_primary_flag.py -q`（KEIBA_SKIP_DB_TESTS unset） | 74 passed, 1 skipped（reports/04-eval.json stale・Plan 06-05 run_evaluation.py で代替検証済み） | ✓ PASS |
| evaluator.check_acceptance_gate D-02 AND 条件 | コード確認（evaluator.py） | `block_triggered = baselines_all_lose and sum_p_violation` 正確・WARN 分離 | ✓ PASS |
| 実 DB is_primary 状態 | `uv run python` で `prediction.fukusho_prediction` を GROUP BY 検証 | catboost=False/22213・lightgbm=True/22213・合計44426・列=boolean NOT NULL DEFAULT false | ✓ PASS |
| hit_rate 値の妥当性 | reports/06-evaluation.json を python json.load で検証 | lightgbm=0.0918748369 / catboost=0.0867732706（reports/05-backtest.json ≈0.0886 と整合・representative_policy 別平均として妥当） | ✓ PASS |
| strict JSON パース（NaN/Infinity 拒否） | `json.loads(raw, parse_constant=reject)` for 06-evaluation.json + 6 segment JSON | 全ファイル strict parse OK | ✓ PASS |
| NaN リテラル grep | `grep -E ": NaN\|: Infinity\|: -Infinity"` for 06-evaluation.json + segment JSONs | 06-evaluation.json=0 / segment total=0 | ✓ PASS |
| segment HTML の plotly.min.js 共有参照 | `grep 'src="plotly' reports/06-segments/*.html` | 6ファイル全て `src="plotly.min.js"` | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| （該当なし） | Phase 6 は scripts/*/tests/probe-*.sh 形式の probe を宣言していない・runnable CLI（scripts/run_evaluation.py）は behavioral spot-check で検証済み | — | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| EVAL-01 | 06-02/06-05 | 複勝的中率/回収率/損益/最大ドローダウン/購入点数/Brier/LogLoss/Calibration Curve を算出 | ✓ SATISFIED | 全8指標が reports/06-evaluation.{md,json} に存在。hit_rate は commit 15782cf で追加（gap closure）・他7指標は前回から VERIFIED |
| EVAL-02 | 06-02/06-05 | 確率品質受入基準（年次Calibration・bin単調・LogLoss/Brier baseline超過・sum(p)適合・median/SD/p10/p90） | ✓ SATISFIED | gate_verdict=WARN（非 BLOCK）・全条件判定実装・reports gate_result に全フィールド・年次反転/単調 WARN 指標実測値記録 |
| EVAL-03 | 06-03/06-05 | 年/月/競馬場/頭数/人気帯/オッズ帯 別の安定性 + Calibration Curve | ✓ SATISFIED | reports/06-segments/ に6軸×{json,html}・SEGMENT_AXES 6軸定義・各 segment に curve + scalar |

**Orphaned requirements:** なし。REQUIREMENTS.md は EVAL-01/02/03 全てを Phase 6 にマッピング・PLAN も全てをカバー。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| （該当なし） | — | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER マーカー無し・NaN リテラル解消 | — | — |
| `src/model/evaluator.py` | 1090 | `return {}` | ℹ️ INFO | 正当なガード句（compute_yearly_inversion_warn 入力空時の安全網）・スタブでない |
| `scripts/run_evaluation.py` | 517 | `return {}` | ℹ️ INFO | 正当なガード句（aggregate_backtest_for_model 該当行無し時）・スタブでない |

### INFO 観察（非 gap）

- **reports/06-segments/*.html の非決定性（既知の Plotly 挙動）:** HTML には Plotly が生成するランダム `<div id="uuid">` と浮動小数点丸め差が含まれ・regeneration ごとに byte 非一致となる。これは Plotly の既知の挙動であり・PLAN（REVIEW C13）は意図的に `reports/` 全体（HTML 含む）を追跡対象とし・再現性の正準アーティファクトは JSON（byte-reproducible・確認済み）にある。gap ではない。

### Human Verification Required

（なし）— 全 must-haves が自動検証で VERIFIED。status=passed。

### Gaps Summary

**gap なし。** 前回の単一 gap（SC#1/EVAL-01 複勝的中率欠落）と副次 WARNING（NaN リテラル）は共に commit 15782cf で解消済み。回帰なし（11 must-haves 全て再確認・is_primary live DB 不変・D-04 事前登録指標不変・gate verdict WARN 維持・segment 6軸 intact・正直注記 intact）。

---

_Verified: 2026-06-23T23:35:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification of: 2026-06-23T16:30:00Z (gaps_found 11/12) → gap closure commit 15782cf_
