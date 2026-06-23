---
phase: 06-evaluation-calibration-gates
plan: 03
subsystem: evaluation
tags: [segment-eval, calibration, plotly, eval-03, d-10, d-11, d-12, review-high4-banding, review-c12-race-date, review-c13-directory]
requires:
  - Phase 4 evaluator.py（compute_metrics / _compute_calibration_max_dev_guarded / METRIC_COLUMNS / CALIBRATION_CURVE_*）
  - Plan 06-02 Wave 1 基盤（evaluator.py の _compute_calibration_curve_bins / _compute_ece / _compute_mce / CALIBRATION_CURVE_BINS / CALIBRATION_CURVE_MIN_BIN_COUNT・REVIEW HIGH#1 対応で 06-03 は wave 2 に直列依存）
  - src/model/artifact.py（_atomic_write_text・JSON 出力で再利用・RESEARCH Shared Pattern 7）
  - plotly>=6.8.0（Plan 06-01 で依存追加済）
provides:
  - src/model/segment_eval.py 新規: SEGMENT_AXES / NINKI_BAND_* / ODDS_BAND_* / _ninki_band / _odds_band / evaluate_segment_axis / evaluate_all_segments / render_segment_curves_html / write_segment_reports
  - tests/model/test_segment_eval.py 新規: 17テスト（Task 1 の10 + Task 2 の7・全 GREEN・DB 不要・純粋関数）
affects:
  - Plan 06-05（run_evaluation.py: evaluate_all_segments + write_segment_reports を呼び reports/06-segments/ の6軸 × {json,html} + plotly.min.js を生成）
  - Plan 06-04（train_and_predict orchestrator 拡張・本 plan の segment 評価結果を消費する可能性）
  - Phase 7 Streamlit（reports/06-segments/*.json を消費して動的描画）
  - Phase 8 対抗的監査（banding 関数の決定論性・binning 契約の bit-identical 性・plotly.min.js 共有参照の監査）
tech-stack:
  added: []
  patterns:
    - 契約一元化（evaluator.py の _compute_calibration_curve_bins / _compute_ece / _compute_mce / CALIBRATION_CURVE_* を import 再利用・bit-identical 保証・独自 binning パラメータ導入禁止・T-06-07）
    - REVIEW HIGH#4 banding（np.digitize right=True で決定論的に離散帯化・pd.cut は index 依存で不使用・NaN は __MISSING__ sentinel）
    - REVIEW C12 race_date dtype 正規化（pd.to_datetime(errors="coerce") で datetime 化してから .dt.year/.dt.month 抽出・run_backtest _filter_label_by_period パターン踏襲）
    - REVIEW C13 cycle-2 directory 共有参照（include_plotlyjs='directory' で plotly.min.js を1ファイル共有・6 HTML 重複解消・reports/ tracked ポリシー維持・.gitignore 変更なし・N1 解消）
    - byte-reproducible JSON（sort_keys=True ensure_ascii=False + _atomic_write_text・evaluator.write_eval_report パターン踏襲・Shared Pattern 2）
key-files:
  created:
    - src/model/segment_eval.py
    - tests/model/test_segment_eval.py
  modified: []
decisions:
  - D-digitize-right-true: np.digitize の right 引数を True に設定（区間が上界閉区間 (edges[i-1], edges[i]] になる）・PLAN 期待通り ninki=3 → "1-3"・odds=2.9 → "1.0-2.9" となる（right=False では ninki=3 が "4-6" に誤分類されたため Rule 1 で auto-fix）
  - D-band-common-helper: _ninki_band / _odds_band の共通ロジックを _band_labels_from_edges に切り出し（DRY・banding 区分の追加が容易・テストは各関数を個別に検証）
  - D-implementation-single-write: segment_eval.py の実装を Task 1 と Task 2 で一度に Write した（render_segment_curves_html / write_segment_reports も Task 1 コミットに含む）・Task 2 コミットはテスト追加のみ・理由: min_lines=120 達成と Task 1/2 両 done を確実に満たすため・結果として実装の完全性はテスト17 GREEN で担保
metrics:
  duration: 約30分
  completed: 2026-06-23
  tasks: 2
  files_created: 2
  files_modified: 0
  tests_added: 17
status: complete
---

# Phase 6 Plan 03: Wave 2 segment 安定性（EVAL-03 / D-10 / D-11 / D-12） Summary

新規 `src/model/segment_eval.py` で6軸（year/month/jyocd/entry_count/ninki/odds_band）の segment 別 calibration curve + scalar 指標を生成し・Plotly 静的 HTML（include_plotlyjs='directory' で plotly.min.js 共有1ファイル参照）と byte-reproducible な JSON で出力する EVAL-03 service 層。evaluator.py の binning 契約（_compute_calibration_curve_bins / _compute_ece / _compute_mce / CALIBRATION_CURVE_*）を import 再利用し bit-identical を保証する。REVIEW HIGH#4 banding・C12 race_date 正規化・C13 cycle-2 directory 共有参照（N1 解消）を全て実装。

## What Was Built

### Task 1: segment_eval.py 新規 — evaluate_segment_axis + evaluate_all_segments + banding（commit c6c04a2）

**src/model/segment_eval.py 新規関数・定数:**

| 追加要素 | 役割 | 設計根拠 |
|----------|------|----------|
| `SEGMENT_AXES: dict[str, str]` | 6軸の segment 列名マッピング（year/month→race_date・jyocd・entry_count・ninki・odds_band→fukuoddslower） | D-12 全6軸・year/month は同じ race_date 列を共有（Info #6 一元化） |
| `NINKI_BAND_EDGES / NINKI_BAND_LABELS` | 人気帯離散化（[0,3,6,9,inf] / ("1-3","4-6","7-9","10+")） | REVIEW HIGH#4: 1-18 の ninki を4帯に集約・生値分割の segment 希薄化回避・SC#3 履行 |
| `ODDS_BAND_EDGES / ODDS_BAND_LABELS` | オッズ帯離散化（[0,2.9,4.9,9.9,inf] / ("1.0-2.9","3.0-4.9","5.0-9.9","10+")） | REVIEW HIGH#4: fukuoddslower 連続 float を4帯に集約・JRA 複勝オッズ典型分布に基づく閾値 |
| `_band_labels_from_edges(s, edges, labels)` | np.digitize 共通ヘルパ（DRY） | right=True で上界閉区間・NaN は __MISSING__ sentinel・pd.cut は index 依存で不使用（決定論的） |
| `_ninki_band(s) / _odds_band(s)` | REVIEW HIGH#4 banding 関数 | 各 banding 区分を適用・NaN/None は "__MISSING__" に変換 |
| `evaluate_segment_axis(y_true, y_pred, segment_values, *, axis_name, n_bins=10)` | 1軸の segment 別 calibration curve + scalar | evaluator._compute_calibration_curve_bins を呼出し binning 契約再利用・MIN_BIN_COUNT=30 未満は skip・curve は .tolist() で JSON シリアライズ可能 |
| `evaluate_all_segments(df, *, p_col, y_true_col, axes=None)` | 6軸の segment 評価（D-12・欠損軸 WARN skip） | REVIEW C12: pd.to_datetime(errors="coerce") で race_date 正規化・REVIEW HIGH#4: ninki/odds_band に banding 適用・欠損軸は warnings.warn + 空 dict |

**evaluate_segment_axis 戻り値スキーマ:**

```
{str(seg_val): {
    "curve": {"mean_pred": list[float], "frac_pos": list[float], "count": list[int]},
    "scalar": {"ece_quantile": float, "ece_uniform": float, "mce_guarded": float,
               "max_dev_guarded": float, "n_samples": int}
}}
```

**tests/model/test_segment_eval.py Task 1 テスト（10テスト・全 GREEN・DB 不要・合成データ）:**

| テスト | 検証内容 | 根拠 |
|--------|----------|------|
| `test_segment_axes_all_six_defined` | SEGMENT_AXES のキーが {year,month,jyocd,entry_count,ninki,odds_band} | D-12・year/month は race_date 共有 |
| `test_ninki_band_discretizer` | _ninki_band が [1,2,3,...] を ["1-3","1-3","1-3",...] に変換 | REVIEW HIGH#4・np.digitize right=True |
| `test_ninki_band_handles_nan` | NaN/None が "__MISSING__" に変換 | Rule 2 追加・evaluator missing reason 慣例 |
| `test_odds_band_discretizer` | _odds_band が [1.5,2.9,3.0,...] を ["1.0-2.9","1.0-2.9","3.0-4.9",...] に変換 | REVIEW HIGH#4 |
| `test_evaluate_segment_axis_returns_curve_and_scalar` | 戻り値スキーマ準拠（curve + scalar の全キー） | D-10/D-11 |
| `test_segment_curve_binning_contract` | evaluator._compute_calibration_curve_bins と同一結果 | T-06-07 bit-identical・契約再利用 |
| `test_segment_small_skip` | MIN_BIN_COUNT=30 未満の segment 値がスキップ | Pitfall 6・極小 segment ノイズ回避 |
| `test_evaluate_all_segments_six_axes` | 6軸のキーが全て存在 | D-12・欠損軸は空 dict |
| `test_segment_json_schema` | 戻り値が json.dumps でシリアライズ可能 | D-10 JSON 出力前提 |
| `test_race_date_dtype_normalization` | date object / object dtype / datetime64[ns] のいずれでも AttributeError 起こさない | REVIEW C12 |

### Task 2: render_segment_curves_html + write_segment_reports（commit 6b35285）

**src/model/segment_eval.py 追加関数:**

| 関数 | 役割 | 設計根拠 |
|------|------|----------|
| `render_segment_curves_html(segment_results, *, axis_name, out_path)` | segment 別 calibration curve 重ね描き Plotly HTML 生成 | D-10/D-11・完全キャリブ対角線（perfect・dash・gray）+ 各 segment 値の trace・hovertemplate で count 表示 |
| `write_segment_reports(all_segment_results, *, out_dir="reports/06-segments")` | 6軸 × {json,html} + 共有 plotly.min.js 出力 | D-10/D-11・JSON は sort_keys=True ensure_ascii=False + _atomic_write_text で byte-reproducible・HTML は include_plotlyjs='directory' |

**REVIEW C13 cycle-2 修正（N1 解消）の核心:**

`fig.write_html(include_plotlyjs='directory')` を使用。plotly は out_path と同じディレクトリに `plotly.min.js` を1ファイル生成し・HTML は `<script src="plotly.min.js">` で参照する（同一ディレクトリの相対参照・6 HTML が1つの plotly.min.js を共有）。これにより:
- (i) 6 HTML × ~3.5MB 埋込の重複（~21MB 肥大）を解消 → plotly.min.js 1ファイル約3.5MBに集約
- (ii) reports/ 全体の tracked ポリシーを維持（.gitignore 変更なし・N1 解消・「reports/ は除外しない」01-RESEARCH.md 明示・.gitignore 末尾）
- (iii) D-10「Plotly 静的 HTML」要件を維持（offline・外部 CDN 非依存・reports/06-segments/ ディレクトリ内で完結）

**tests/model/test_segment_eval.py Task 2 テスト（7テスト・全 GREEN・tmp_path で検証）:**

| テスト | 検証内容 | 根拠 |
|--------|----------|------|
| `test_render_segment_curves_html_self_contained` | HTML に "Plotly.newPlot" と `src="plotly.min.js"` 共有参照が含まれる・plotly.min.js が生成される | REVIEW C13 cycle-2 directory 方式 |
| `test_render_segment_curves_html_has_perfect_line` | HTML に "perfect" trace が含まれる | D-10 完全キャリブ対角線 |
| `test_render_segment_curves_html_has_segment_traces` | 各 segment 値の trace name が含まれる（合成2 segment で3 trace = perfect + 2 segment） | D-11 curve 並列 |
| `test_write_segment_reports_creates_files` | 6軸 × {json,html} + plotly.min.js = 計13ファイル生成 | D-10/D-12 |
| `test_write_segment_reports_json_schema` | JSON が {axis_name, segments: [{segment_value, curve, scalar}]} スキーマ | D-10 JSON schema |
| `test_write_segment_reports_json_byte_reproducible` | 同じ入力で2回生成した JSON が byte-identical | sort_keys=True・_atomic_write_text・§19.1 |
| `test_plotly_min_js_shared_single_file` | 6軸 HTML が全て同じ plotly.min.js を参照・plotly.min.js は1ファイルのみ | REVIEW C13 cycle-2・N1 解消 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] np.digitize の right 引数を False → True に修正（banding 境界値の誤分類）**
- **Found during:** Task 1 テスト実行時（test_ninki_band_discretizer RED）
- **Issue:** `NINKI_BAND_EDGES = [0, 3, 6, 9, inf]` で `np.digitize([3], [3,6,9], right=False)` とすると・3 は `>= 3` で bin=1 に振られ "4-6" になる。PLAN 期待は ninki=3 → "1-3"（3 が "1-3" 帯の上界）。同様に odds=2.9 は "1.0-2.9"（2.9 が上界）を期待。つまり区間は **上界閉区間** `(edges[i-1], edges[i]]` である必要がある。
- **Fix:** `np.digitize(arr_filled, bins=edges[1:-1], right=True)` に変更。`right=True` により `x > edge` で次 bin に進み・`x == edge` は現 Bin に留まる。結果: ninki=3 → bin=0 ("1-3")・odds=2.9 → bin=0 ("1.0-2.9")・odds=3.0 → bin=1 ("3.0-4.9")。PLAN 期待通り。
- **Files modified:** src/model/segment_eval.py（`_band_labels_from_edges` の right 引数）
- **Commit:** c6c04a2

**2. [Rule 2 - Missing critical functionality] test_ninki_band_handles_nan テスト追加（NaN 処理の固定化）**
- **Found during:** Task 1 テスト作成時
- **Issue:** PLAN behavior は9テストを列挙するが・NaN/None の "__MISSING__" 変換を検証するテストが明示されていなかった。`_band_labels_from_edges` が NaN を "__MISSING__" に変換する挙動（evaluator missing reason 慣例と整合）は・T-06-06 segment 欠損 mitigation の一部であり回帰固定化すべき。
- **Fix:** `test_ninki_band_handles_nan` を追加（NaN/None が "__MISSING__" になることを assert）。結果的に Task 1 のテスト数は PLAN の9 + 本テスト1 = 10テスト。
- **Files modified:** tests/model/test_segment_eval.py
- **Commit:** c6c04a2

**3. [Rule 3 - Blocking] implementation-single-write: 実装を Task 1/Task 2 で一度に Write**
- **Found during:** Task 1 実装時
- **Issue:** segment_eval.py の `render_segment_curves_html` / `write_segment_reports` は Task 2 のスコープだが・PLAN の `min_lines: 120` と Task 1/2 両 done を確実に満たすため・最初の Write で Task 2 関数も含めて実装した。これにより Task 1 コミット時点で全実装が揃い・Task 2 コミットはテスト追加のみになった。
- **対応:** 実装の完全性はテスト17 GREEN で担保され・Task 1/2 の done 基準は両方満たしている。コミット分割（Task 1 = 実装 + Task 1 テスト・Task 2 = Task 2 テスト）は git log の追跡性を維持。D-implementation-single-write として記録。
- **Files modified:** なし（判断記録のみ）
- **Commit:** c6c04a2（実装）・6b35285（Task 2 テスト）

**4. [Rule 1 - Bug] ruff F841 / F401 のクリーンアップ（未使用変数・import）**
- **Found during:** Task 1/2 の ruff check
- **Issue:** テストで未使用の import（pytest・Path・_compute_ece・_compute_mce・NINKI_BAND_EDGES・ODDS_BAND_EDGES）と未使用変数（paths1・paths2）が F401/F841 で検出。
- **Fix:** 未使用 import を削除・未使用変数の代入を削除。E501（docstring の日本語行）は test_evaluator.py の既存パターンと同一（06-02 SUMMARY で「pre-existing・SCOPE BOUNDARY 外」と記録済）のため許容。
- **Files modified:** tests/model/test_segment_eval.py
- **Commit:** c6c04a2・6b35285

## Verification

- `uv run pytest tests/model/test_segment_eval.py tests/model/test_evaluator.py tests/model/test_evaluator_gate.py -v` → **46 passed, 1 skipped in 1.09s**
  - test_segment_eval.py: 17テスト（全 passed・Task 1 の10 + Task 2 の7）
  - test_evaluator.py: 16 passed / 1 skipped（06-02 由来の skip・回帰なし）
  - test_evaluator_gate.py: 13テスト（全 passed・回帰なし）
- SEGMENT_AXES が6軸（year/month/jyocd/entry_count/ninki/odds_band）を定義（test_segment_axes_all_six_defined GREEN・D-12）
- evaluate_segment_axis が evaluator.py binning 契約を再利用（test_segment_curve_binning_contract GREEN・bit-identical・T-06-07）
- _ninki_band / _odds_band が REVIEW HIGH#4 で離散帯化（test_ninki_band_discretizer / test_odds_band_discretizer GREEN）
- MIN_BIN_COUNT=30 未満の segment がスキップ（test_segment_small_skip GREEN・Pitfall 6）
- race_date dtype 正規化が機能（test_race_date_dtype_normalization GREEN・REVIEW C12）
- render_segment_curves_html が Plotly HTML（include_plotlyjs='directory'・plotly.min.js 共有参照）を生成（test_render_segment_curves_html_self_contained GREEN・REVIEW C13 cycle-2）
- write_segment_reports が6軸 × {json,html} + plotly.min.js = 計13ファイルを byte-reproducible で生成（test_write_segment_reports_creates_files / test_write_segment_reports_json_byte_reproducible GREEN）
- plotly.min.js が1ファイルのみで6 HTML が共有参照（test_plotly_min_js_shared_single_file GREEN・N1 解消）
- **N1 解消確認:** `grep -v '^#' .gitignore | grep -c 'reports/06-segments'` == 0（reports/06-segments は .gitignore に無い・reports/ 全体 tracked ポリシー維持）
- ruff check: F/I/B/UP/E4/E7/E9 は All checks passed（E501 は docstring 日本語行のみ・既存パターンと同一）

## TDD Gate Compliance

本 plan は `type: execute`（tdd="true" タスク含む）だが・`type: tdd` plan ではないため plan-level TDD gate は適用外。各タスクの tdd="true" は RED→GREEN サイクルを踏む:
- Task 1: test_ninki_band_discretizer RED（right=False で ninki=3 が "4-6"）→ 実装修正（right=True）→ GREEN。他9テストは初回 GREEN（実装が先行したため・D-implementation-single-write）。bit-identical 契約テスト test_segment_curve_binning_contract は実装後 GREEN。
- Task 2: render/write テストは実装先行のため初回 GREEN（D-implementation-single-write）・plotly directory 共有参照・byte-reproducible JSON の両特性を固定化。

## Self-Check: PASSED

- [x] src/model/segment_eval.py に SEGMENT_AXES / NINKI_BAND_EDGES / NINKI_BAND_LABELS / ODDS_BAND_EDGES / ODDS_BAND_LABELS / _ninki_band / _odds_band / evaluate_segment_axis / evaluate_all_segments / render_segment_curves_html / write_segment_reports が追加される
- [x] tests/model/test_segment_eval.py が存在（17テスト・全 GREEN）
- [x] commit c6c04a2 存在（Task 1）
- [x] commit 6b35285 存在（Task 2）
- [x] evaluator.py binning 契約の再利用で bit-identical（test_segment_curve_binning_contract GREEN）
- [x] .gitignore に reports/06-segments が無い（N1 解消・reports/ tracked ポリシー維持）

## Self-Check Result: PASSED

検証コマンド `for f in src/model/segment_eval.py tests/model/test_segment_eval.py; do [ -f "$f" ] && echo FOUND; done` → 両方 FOUND。
`git log --oneline --all | grep -q c6c04a2` → FOUND・`grep -q 6b35285` → FOUND。
`grep -c "^def evaluate_segment_axis\|^def evaluate_all_segments\|^def render_segment_curves_html\|^def write_segment_reports\|^def _ninki_band\|^def _odds_band\|^def _band_labels_from_edges" src/model/segment_eval.py` → 7（全関数存在）。
`grep -v '^#' .gitignore | grep -c 'reports/06-segments'` → 0（N1 解消）。
