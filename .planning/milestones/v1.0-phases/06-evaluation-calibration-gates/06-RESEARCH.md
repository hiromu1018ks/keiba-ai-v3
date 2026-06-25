# Phase 6: Evaluation & Calibration Gates - Research

**Researched:** 2026-06-23
**Domain:** 確率品質評価・キャリブレーション指標・受入ゲート・segment 別安定性・主モデル確定（Python/NumPy/scikit-learn/Plotly/PostgreSQL）
**Confidence:** HIGH

## Summary

Phase 6 は Phase 4（モデル予測）と Phase 5（backtest）の stamped 成果物を消費する**評価専用フェーズ**である。モデル再学習・予測再生成は行わず（Phase 4 SC#4 bit-identical 維持・D-06）、確率品質受入ゲート（§15.2）と segment 別安定性評価（§15.3）を実装し、D-04 事前登録基準（Calibration 重視）で主モデルを確定して prediction テーブルに `is_primary` フラグを付与する。

CONTEXT.md が既に D-01〜D-12 の全ての意思決定を固定しているため、本研究は「決定の再考」でなく**実装アプローチと技術的落とし穴の調査**に特化した。特に (1) 新キャリブ指標（quantile max_dev / ECE / MCE）の純 NumPy bit-identical 実装、(2) 受入ゲート判定ロジック（構造的 BLOCK vs 曖昧 WARN）、(3) segment 別安定性評価モジュールのアーキテクチャ、(4) 統合評価経路の設計、(5) `is_primary` フラグ DB migration、(6) §17.3 テスト構成、を深く調査した。

**最大の発見:** 既存 `src/model/evaluator.py::_compute_calibration_max_dev_guarded`（commit 9fce782・debug: calib-maxdev-vs-baselines で実装）が既に純 NumPy（`np.linspace` + `np.digitize` + `np.clip` + `np.bincount`）で bit-identical binning を実装している。Phase 6 の quantile max_dev/ECE/MCE はこの**確立したパターンを直接拡張**すればよい — bin_edges 構築を `np.linspace(0,1,n+1)` から `np.quantile(y_pred, np.linspace(0,1,n+1))` に差し替えるだけで、bit-identical 保証・整列 assert・MIN_BIN_COUNT ガード・y_pred==1.0 clip の全てがそのまま適用できる。これにより Phase 6 の実装リスクは大幅に低下する。

**Primary recommendation:** `src/model/evaluator.py` を直接拡張（quantile/ECE/MCE 追加・ゲート判定関数追加）+ 新規 `src/model/segment_eval.py`（6軸 segment 評価）+ 新規 `scripts/run_evaluation.py`（統合 CLI）+ `prediction.fukusho_prediction` へ `is_primary` 列追加（DDL/PREDICTION_COLUMNS/prediction_load の3箇所更新）+ `reports/06-evaluation.{md,json}` + `reports/06-segments/`（JSON + Plotly HTML）。plotly を pyproject.toml 依存関係に追加（scipy は sklearn 推移依存で既に利用可能）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**受入ゲートの厳格さ（EVAL-02 / §15.2・Core Value 直結）**
- **D-01: 構造的 BLOCK のみ hard fail・それ以外は WARN（参考レポート）** — §15.2 受入基準のうち、モデルが本質的に破綻している場合のみ pytest/CI fail（出荷停止）。曖昧基準は WARN。hybrid gate（Phase 1 D-01 / Phase 2 D-02）の延長。
- **D-02: 構造的 BLOCK 対象 = LogLoss/Brier で baselines 全敗 ＋ `sum(p)` が理論値から著しく乖離** — 順序付け能力ゼロ（AI 付加価値ゼロ）と確率スケール破綻の両方を安全網。
- **D-03: 曖昧基準は参考レポート・数値併記・人間判定** — 「年次キャリブ反転」「bin 単調性」を反転数・単調違反 bin 数・Spearman 順位相関等の数値で併記するが、PASS/FAIL 判定は人間。

**キャリブ指標の再設計（debug calib-maxdev-vs-baselines の Phase 6 領域）**
- **D-04: 事前登録指標 `calibration_max_dev`（uniform・ガードなし）は不変で維持 + 新指標を併記** — Phase 4 事前登録の指標定義を温存（後知恵すり替え T-04-24 完全回避）。
- **D-05: 追加キャリブ指標 = quantile max_dev + ECE + MCE** — quantile bin（等頻度）の max_dev と ECE（bin 別 dev のサンプル重み付け平均）と MCE（Maximum Calibration Error・worst-case）。
- **D-06: 高確率域（pred>0.7）過信は可視化・記録のみ** — 根本対処は Optuna 導入（将来 Phase）に委ねる。Phase 4 SC#4 bit-identical 再現性を維持。

**主モデル確定と運用（Phase 4 D-03/D-04 事前登録基準の実体化）**
- **D-07: 主モデル選定は人間判断・理由記録** — 両モデルの全指標を並列提示し、D-04 基準（Calibration 重視）に照らして人間が決定。
- **D-08: 僅差・同点時はタイブレーク規則で1つ選ぶ** — 固定優先順位（backtest 回収率 → 計算コスト低=LightGBM）で1つに決定。主モデルは1つ。
- **D-09: 主モデル確定は prediction テーブルに `is_primary` フラグ付与** — 選定モデル=true、未選定=false（両モデル行は保持）。Phase 7 Streamlit は `is_primary=true` を表示。

**セグメント別安定性の成果物（EVAL-03 / §15.3）**
- **D-10: 成果物 = JSON データ + Plotly 静的 HTML の両方** — 機械可読 JSON と Plotly 静的 HTML。Phase 7 Streamlit は JSON を消費して動的描画。
- **D-11: segment 比較 = curve 並列表示 + scalar 表** — 各軸で segment ごとの calibration curve を重ね描きし、scalar 指標の segment 表を併記。
- **D-12: 6軸（year/month/競馬場/頭数/人気帯/オッズ帯）全て生成** — EVAL-03 を完全履行。

### Claude's Discretion
- 構造的 BLOCK 閾値の具体値（D-02 の「baselines 全敗」「sum(p) 著乖離」の定義）
- 新キャリブ指標の実装詳細（bin 数・MIN_BIN_COUNT・実装箇所・純 NumPy）
- タイブレーク規則の具体化（D-08 の固定優先順位）
- 統合評価経路の設計（`scripts/run_evaluation.py` 一本化 vs 既存スクリプト拡張）
- reports/06-evaluation.{md,json} 慣例・reports/06-segments/ ディレクトリ構成
- segment 評価モジュールの配置（`src/model/segment_eval.py` 仮）
- Plotly HTML のレイアウト
- テスト構成（§17.3）
- `is_primary` フラグの DB スキーマ影響

### Deferred Ideas (OUT OF SCOPE)
- Phase 7（Presentation）: Streamlit 動的 calibration curve 描画・`is_primary=true` 主モデル表示・CSV 出力（OUT-01/02）
- Phase 8（Adversarial Audit）: 受入ゲート判定ロジックの対抗的監査・`is_primary` フラグの後知恵すり替え検出・固定 seed 再現性（TEST-01）
- 高確率域過信の根本対処（将来 Optuna 導入時）: isotonic の高確率域 clip・sigmoid 併用・calib slice 拡大
- キャリブ指標の更なる拡張（将来）: bin 数チューニング・segment 別 ECE 重み付け最適化・Platt scaling 比較
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-01 | 複勝的中率/回収率/損益/最大ドローダウン/購入点数/Brier Score/LogLoss/Calibration Curve を算出 | 「統合評価経路の設計」節: Phase 5 `src/ev/metrics.py`（回収率/P/L/maxDD/購入点数）と Phase 4 `src/model/evaluator.py`（Brier/LogLoss/Calibration Curve）の統合。`scripts/run_evaluation.py` が両者を読込・reports/06-evaluation.{md,json} に出力。的中率（hit_rate）は既に `run_backtest.py:644` で計算済み |
| EVAL-02 | 確率品質受入基準（年別Calibration極端逆転なし・bin実測率単調増加・LogLoss/Brierのベースライン超過・sum(p)平均理論値適合・median/SD/p10/p90）を検証 | 「受入ゲート判定ロジック」節: D-01/D-02 の構造的 BLOCK（baselines 全敗 + sum(p) 著乖離）と D-03 の曖昧 WARN（Spearman 順位相関・反転数）を実装。`check_sum_p_distribution` 拡張 + 新規 `check_acceptance_gate` 関数 |
| EVAL-03 | 年/月/競馬場/頭数/人気帯/オッズ帯 別の安定性と、全体/各軸の Calibration Curve を評価 | 「segment 別安定性評価モジュール」節: `src/model/segment_eval.py` で6軸の calibration curve 生成（evaluator.py binning 契約再利用）+ JSON + Plotly HTML 出力（D-10/D-11/D-12） |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **応答言語**: 全ての応答・説明・コメント・コミットメッセージは必ず日本語（技術用語・コード識別子は原文可）
- **純 NumPy bit-identical**: キャリブ指標計算は `np.linspace`/`np.digitize`/`np.bincount`/`np.clip` で実装（pandas.groupby/sort は等値要素 index 依存で bit-identical リスク → 不使用）。debug Specialist SUGGEST_CHANGE (b)/(f) 準拠
- **Plotly 推奨**: キャリブ曲線・安定性プロットは Plotly を使用（matplotlib でなく Streamlit 連携も考慮）
- **MLflow/Optuna defer**: Phase 1 では導入しない（§21）。joblib.dump/pickle のみ
- **hybrid gate 慣例**: Phase 1 D-01 / Phase 2 D-02 の構造的 BLOCK + 量的 WARN パターン。Phase 6 D-01/D-02/D-03 はこの延長
- **リーク防止厳守**: target/mean encoding 禁止・PIT as-of・race_id-grouped split・CatBoost has_time=True。Phase 6 は評価専用（READ のみ + is_primary 更新）なので新規リーク面なし
- **再現性厳守**: Phase 4 SC#4 bit-identical（num_threads=1/seed=42/FIXED_REPRODUCE_TS）を維持。Phase 6 は予測再生成しない

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 確率品質指標計算（Brier/LogLoss/Calibration/ECE/MCE） | Python service 層（`src/model/evaluator.py` 拡張） | — | 純粋関数・純 NumPy bit-identical。DB 不要・入力は予測 DataFrame のみ |
| backtest 品質指標（回収率/P/L/maxDD/購入点数） | Python service 層（`src/ev/metrics.py` 既存） | — | 既存・Phase 5 実装済み。Phase 6 は統合読込のみ |
| 受入ゲート判定（構造的 BLOCK / 曖昧 WARN） | Python service 層（`src/model/evaluator.py` 新関数） | — | ゲート判定は純粋関数・入力は metrics dict + baselines dict |
| segment 別安定性評価（6軸） | Python service 層（`src/model/segment_eval.py` 新規） | — | evaluator.py binning 契約再利用・segment 軸で groupby して曲線生成 |
| Plotly 静的 HTML 生成 | Python service 層（`src/model/segment_eval.py` 内） | — | `fig.write_html(include_plotlyjs=True)` で自己完結。Local-only |
| 主モデル確定（is_primary フラグ） | Database（`prediction.fukusho_prediction` テーブル） | Python service 層（DDL + UPDATE） | queryable・Phase 7 SQL 照会可能。etl ロールで UPDATE |
| レポート出力（md + json 分離） | Filesystem（`reports/`） | — | `src/model/artifact.py::_atomic_write_text` + `json.dumps(sort_keys=True)` byte-reproducible |
| 統合評価 CLI | Python CLI（`scripts/run_evaluation.py` 新規） | — | Phase 4/5 成果物を統合読込 → ゲート判定 → segment 評価 → レポート生成 → is_primary 更新 |

## Standard Stack

### Core（既存・変更なし）
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| NumPy | ≥2.0（推移依存） | キャリブ指標の bit-identical binning 計算 | `np.linspace`/`np.digitize`/`np.bincount`/`np.clip`/`np.quantile`。既存 `_compute_calibration_max_dev_guarded` と同一パターン。pandas.groupby/sort は等値要素 index 依存で不使用 [CITED: numpy.org/doc/2.2/reference/generated/numpy.quantile.html] |
| pandas | 3.0.3（既存 pin） | segment 軸 groupby・DataFrame 結合 | `df.groupby(segment_col)` で segment 抽出・各 segment で evaluator binning 関数を適用。groupby 自体は行順序に依存しない（segment 値で分割のみ） |
| scikit-learn | 1.9.0（既存 pin） | `calibration_curve`（uniform/quantile 両 strategy）・brier/logloss/auc | 既存 evaluator.py が使用。`calibration_curve(strategy='quantile')` は等頻度 binning をサポートするが count を返さず空 bin を除外して整列するため、bit-identical には自前 NumPy 実装を使用 [CITED: scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html] |

### Supporting（Phase 6 で新規追加・要 pyproject.toml 更新）
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **plotly** | 6.x（最新安定）[ASSUMED - 版本未確認・planner が `uv add plotly` で最新を確認] | Plotly 静的 HTML 生成（segment 別 calibration curve 重ね描き・D-10/D-11） | `fig.write_html(path, include_plotlyjs=True)` で自己完結 offline HTML。D-10 必須・CLAUDE.md Plotly 推奨 [CITED: plotly.com/python/interactive-html-export/] |

### 既存（追加依存不要・推移依存で利用可能）
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **scipy** | ≥1.13（sklearn 推移依存） | `scipy.stats.spearmanr`（D-03 bin 単調性 WARN 指標） | `(frac_pos, mean_pred)` 配列の Spearman 順位相関。ties は `rankdata(method='average')` で決定論的・nan_policy='omit' で NaN bin を除外。pyproject.toml に明示的追加不要（sklearn 経由で既にインストール済み） [CITED: docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 純 NumPy binning | sklearn `calibration_curve(strategy='quantile')` | sklearn 版は count を返さず空 bin を除外して整列するため、bin と count の対応が自明でない。bit-identical 保証のため自前 NumPy 実装（既存 `_compute_calibration_max_dev_guarded` パターン）を採用 [CITED: scikit-learn.org] |
| scipy.stats.spearmanr | 純 NumPy rankdata + pearson | scipy は既に推移依存で利用可能・ties 処理が検証済み。自前実装は再発明。scipy を使用 |
| Plotly HTML | matplotlib PNG | CLAUDE.md が Plotly 推奨・Phase 7 Streamlit 連携を考慮。D-10 が JSON + Plotly HTML を固定 |
| pandas.qcut（quantile binning） | 純 NumPy `np.quantile` + `np.digitize` | pandas.qcut は等値要素の index 依存で bit-identical リスク（debug Specialist 指摘 (f)）。純 NumPy を使用・`np.unique` で重複 edge 対処 |

**Installation:**
```bash
# plotly のみ新規追加（scipy は sklearn 推移依存で既存）
uv add plotly
# 既存依存（NumPy/pandas/scikit-learn）は pyproject.toml に既存・変更不要
```

**Version verification:** planner は `uv add plotly` 実行時に最新版を確認し pyproject.toml を更新すること。

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| plotly | PyPI | 12+ 年 | 数千万/月 | github.com/plotly/plotly.py | OK | Approved |
| scipy | PyPI | 20+ 年 | 数千万/月（sklearn 推移依存） | github.com/scipy/scipy | OK | Approved（推移依存・明示的追加不要） |
| numpy | PyPI | 16+ 年 | 億/月（pandas/sklearn 推移依存） | github.com/numpy/numpy | OK | Approved（推移依存・明示的追加不要） |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious SUS:** none

*plotly は PyPI で長期間・高 download 数・公式 source repo あり・CLAUDE.md 推奨のため OK。planner は `uv add plotly` で最新版を確認後 pin すること。*

## Architecture Patterns

### System Architecture Diagram

```
[Phase 4/5 成果物（READ only・ stamped）
   prediction.fukusho_prediction (両モデル予渓・model_type/model_version/p_fukusho_hit/race_key/entry_count/split/jyocd/race_date)
   backtest.fukusho_backtest (実データ backtest・回収率/P/L/maxDD/購入点数)
   label.fukusho_label (的中判定 fukusho_hit_validated + race_date/entry_count/jyocd/segment 軸)
   reports/04-eval.{md,json} (D-04 事前登録素材)
   reports/05-backtest.{md,json} (backtest 成果)]
        │
        ▼
[scripts/run_evaluation.py（統合 CLI・新規）
   ├─ 1. 成果物読込（readonly ロール・READ only）
   │     prediction_df ← prediction.fukusho_prediction (両モデル test split)
   │     backtest_metrics ← reports/05-backtest.json or backtest.fukusho_backtest
   │     label_df ← label.fukusho_label (segment 軸: race_date/jyocd/entry_count/ninki/odds)
   │
   ├─ 2. 確率品質指標計算（src/model/evaluator.py 拡張）
   │     compute_metrics 拡張: quantile_max_dev + ECE + MCE 追加（純 NumPy）
   │     ├─ 各モデル × baselines で compute_metrics
   │     └─ build_comparison_table 拡張（新指標列追加）
   │
   ├─ 3. 受入ゲート判定（src/model/evaluator.py 新関数）
   │     check_acceptance_gate(metrics_dict) → gate_result
   │     ├─ 構造的 BLOCK（D-02）: baselines 全敗? + sum(p) 著乖離? → pytest/CI fail
   │     └─ 曖昧 WARN（D-03）: 年次反転数・bin 単調違反数・Spearman → 参考レポート
   │
   ├─ 4. segment 別安定性評価（src/model/segment_eval.py・新規）
   │     evaluate_segments(prediction_df, label_df, axes=6) → segment_results
   │     ├─ 各 segment 値で groupby → evaluator binning で calibration curve 生成
   │     ├─ scalar 指標（ECE/MCE/max_dev）per segment
   │     └─ Plotly HTML（curve 重ね描き + scalar 表）+ JSON 出力
   │
   ├─ 5. 主モデル確定（D-07/D-08/D-09）
   │     ├─ 両モデル全指標並列提示（reports/06-evaluation.md）
   │     ├─ 人間判断（D-04 基準: Calibration 重視）+ 理由記録
   │     ├─ タイブレーク規則（D-08）: backtest 回収率 → 計算コスト低=LightGBM
   │     └─ is_primary フラグ付与（etl ロール・UPDATE prediction.fukusho_prediction）
   │
   └─ 6. レポート出力（reports/06-evaluation.{md,json} + reports/06-segments/）
        ├─ md（人間確認）+ json（sort_keys=True byte-reproducible）
        └─ reports/06-segments/{axis}.{json,html} × 6軸
]
        │
        ▼
[Phase 7/8 下流（CONSUMED BY）
   Phase 7: Streamlit が is_primary=true 表示・segment JSON 消費
   Phase 8: ゲート判定ロジック対抗的監査・is_primary 後知恵すり替え検出]
```

### Recommended Project Structure
```
src/model/
├── evaluator.py          # 拡張: quantile_max_dev/ECE/MCE + check_acceptance_gate
├── segment_eval.py       # 新規: 6軸 segment 別 calibration curve + scalar + Plotly HTML
├── predict.py            # 拡張: PREDICTION_COLUMNS に is_primary 追加
├── artifact.py           # 既存（_atomic_write_text 再利用）
└── ...（既存）
src/db/
├── schema.py             # 拡張: PREDICTION_TABLE_DDL に is_primary 列追加
└── prediction_load.py    # 拡張: _df_to_prediction_tuples に is_primary 処理
scripts/
└── run_evaluation.py     # 新規: 統合評価 CLI
tests/model/
├── test_evaluator.py     # 新規: キャリブ指標・ゲート判定単体テスト
└── test_segment_eval.py  # 新規: segment 評価 contract テスト
tests/db/
└── test_is_primary_flag.py  # 新規: is_primary migration・backfill・idempotency テスト
reports/
├── 06-evaluation.md      # 新規: 統合評価レポート
├── 06-evaluation.json    # 新規: 機械可読（sort_keys=True）
└── 06-segments/          # 新規: segment 別成果物
    ├── year.json / year.html
    ├── month.json / month.html
    ├── jyocd.json / jyocd.html
    ├── entry_count.json / entry_count.html
    ├── ninki.json / ninki.html
    └── odds_band.json / odds_band.html
```

### Pattern 1: 純 NumPy bit-identical binning（既存パターンの拡張）
**What:** キャリブ指標（max_dev/ECE/MCE）を `np.linspace`/`np.quantile`/`np.digitize`/`np.bincount`/`np.clip` で計算。pandas.groupby/sort は等値要素 index 依存で bit-identical リスクのため不使用。
**When to use:** 全てのキャリブ指標計算。Phase 4 SC#4 bit-identical 再現性を維持。
**Example:**
```python
# Source: src/model/evaluator.py:259-335（既存 _compute_calibration_max_dev_guarded）
# Phase 6 拡張: strategy='quantile' の bin_edges 構築を追加

def _compute_calibration_curve_bins(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    strategy: str,  # 'uniform' | 'quantile'
    n_bins: int = CALIBRATION_CURVE_BINS,
    min_bin_count: int = CALIBRATION_CURVE_MIN_BIN_COUNT,
) -> dict[str, np.ndarray]:
    """bin ごとに (mean_pred, frac_pos, count) を純 NumPy で計算（bit-identical）。

    strategy='uniform': bin_edges = np.linspace(0, 1, n_bins+1)  [既存]
    strategy='quantile': bin_edges = np.quantile(y_pred, np.linspace(0, 1, n_bins+1))
                         重複 edge は np.unique で対処（pandas qcut duplicates='drop' 相当）
    """
    if strategy == "uniform":
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    elif strategy == "quantile":
        quantile_edges = np.quantile(y_pred, np.linspace(0.0, 1.0, n_bins + 1))
        # 重複 edge を削除（予測値に同値が多い場合・例: BL-1 の離散値）
        bin_edges = np.unique(quantile_edges)
        n_bins = len(bin_edges) - 1
        if n_bins < 1:
            return {"mean_pred": np.array([]), "frac_pos": np.array([]),
                    "counts": np.array([]), "bin_edges": bin_edges}
    else:
        raise ValueError(f"unsupported strategy: {strategy}")

    # y_pred==1.0 の out-of-range を clip で捕捉（既存 Specialist 指摘 (b)）
    bin_idx = np.digitize(y_pred, bins=bin_edges[1:-1], right=False)
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)

    counts = np.bincount(bin_idx, minlength=n_bins).astype(float)
    pos_sum = np.bincount(bin_idx, weights=y_true.astype(float), minlength=n_bins)
    pred_sum = np.bincount(bin_idx, weights=y_pred, minlength=n_bins)

    nonempty = counts > 0
    return {
        "mean_pred": pred_sum[nonempty] / counts[nonempty],
        "frac_pos": pos_sum[nonempty] / counts[nonempty],
        "counts": counts[nonempty],
        "bin_edges": bin_edges,
    }

def _compute_ece(y_true, y_pred, *, strategy="quantile", n_bins=10):
    """ECE = Σ(n_m/N) × |frac_pos - mean_pred|（Naeini 2015）。"""
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy=strategy, n_bins=n_bins)
    if len(bins["counts"]) == 0:
        return float("nan")
    N = float(len(y_pred))
    devs = np.abs(bins["frac_pos"] - bins["mean_pred"])
    return float(np.sum(bins["counts"] / N * devs))  # [CITED: Naeini 2015 / UW CSE493S]

def _compute_mce(y_true, y_pred, *, strategy="quantile", n_bins=10,
                 min_bin_count=CALIBRATION_CURVE_MIN_BIN_COUNT):
    """MCE = max|frac_pos - mean_pred|（worst-case・Naeini 2015）。MIN_BIN_COUNT ガード付き。"""
    bins = _compute_calibration_curve_bins(
        y_true, y_pred, strategy=strategy, n_bins=n_bins, min_bin_count=min_bin_count)
    if len(bins["counts"]) == 0:
        return float("nan")
    keep = bins["counts"] >= min_bin_count
    if not np.any(keep):
        return float("nan")
    devs = np.abs(bins["frac_pos"][keep] - bins["mean_pred"][keep])
    return float(np.max(devs))
```

### Pattern 2: segment 別評価（evaluator binning 契約再利用）
**What:** 6軸（year/month/jyocd/entry_count/ninki/odds_band）で予測 DataFrame を groupby し、各 segment 値で `_compute_calibration_curve_bins` を適用して calibration curve を生成。
**When to use:** EVAL-03 / D-10/D-11/D-12。
**Example:**
```python
# segment 軸の定義（label.fukusho_label + prediction.fukusho_prediction から導出）
SEGMENT_AXES = {
    "year": lambda df: df["race_date"].dt.year,        # 年別
    "month": lambda df: df["race_date"].dt.month,      # 月別
    "jyocd": lambda df: df["jyocd"],                   # 競馬場別
    "entry_count": lambda df: df["entry_count"],       # 頭数別
    "ninki": lambda df: _ninki_band(df["ninki"]),      # 人気帯別（1-3/4-6/7-9/10+ 等）
    "odds_band": lambda df: _odds_band(df["fukuoddslower"]),  # オッズ帯別
}

def evaluate_segment_axis(
    y_true: np.ndarray, y_pred: np.ndarray,
    segment_values: np.ndarray, *,
    axis_name: str, n_bins: int = CALIBRATION_CURVE_BINS,
) -> dict:
    """1つの segment 軸で全 segment 値の calibration curve + scalar を生成。"""
    results = {}
    unique_segments = np.unique(segment_values[np.isfinite(segment_values)]
                                if np.issubdtype(segment_values.dtype, np.number)
                                else segment_values)
    for seg_val in unique_segments:
        mask = segment_values == seg_val
        if mask.sum() < CALIBRATION_CURVE_MIN_BIN_COUNT:
            continue  # 極小 segment はスキップ
        bins = _compute_calibration_curve_bins(
            y_true[mask], y_pred[mask], strategy="uniform", n_bins=n_bins)
        results[str(seg_val)] = {
            "curve": {"mean_pred": bins["mean_pred"].tolist(),
                      "frac_pos": bins["frac_pos"].tolist(),
                      "count": bins["counts"].astype(int).tolist()},
            "scalar": {
                "ece_quantile": _compute_ece(y_true[mask], y_pred[mask], strategy="quantile"),
                "ece_uniform": _compute_ece(y_true[mask], y_pred[mask], strategy="uniform"),
                "mce_guarded": _compute_mce(y_true[mask], y_pred[mask], strategy="uniform"),
                "max_dev_guarded": _compute_calibration_max_dev_guarded(y_true[mask], y_pred[mask]),
                "n_samples": int(mask.sum()),
            },
        }
    return results
```

### Pattern 3: Plotly 静的 HTML（自己完結・D-10）
**What:** segment ごとの calibration curve を重ね描きした Plotly figure を `write_html(include_plotlyjs=True)` で自己完結 HTML として出力。
**When to use:** D-10/D-11。
**Example:**
```python
# Source: [CITED: plotly.com/python/interactive-html-export/]
import plotly.graph_objects as go

def render_segment_curves_html(
    segment_results: dict, *, axis_name: str, out_path: Path,
) -> Path:
    """segment 別 calibration curve を重ね描きした HTML を出力。"""
    fig = go.Figure()
    # 完全キャリブ対角線
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                            name="perfect", line=dict(dash="dash", color="gray")))
    # 各 segment 値の curve
    for seg_val, data in sorted(segment_results.items()):
        curve = data["curve"]
        fig.add_trace(go.Scatter(
            x=curve["mean_pred"], y=curve["frac_pos"], mode="lines+markers",
            name=f"{axis_name}={seg_val} (n={data['scalar']['n_samples']})",
            customdata=curve["count"],
            hovertemplate="pred=%{x:.3f}<br>obs=%{y:.3f}<br>n=%{customdata}<extra></extra>",
        ))
    fig.update_layout(
        title=f"Calibration Curve by {axis_name}",
        xaxis_title="mean predicted probability", yaxis_title="observed fraction",
        width=900, height=600,
    )
    # 自己完結（offline・~3MB plotly.js 埋込）
    fig.write_html(str(out_path), include_plotlyjs=True)
    return out_path
```

### Pattern 4: is_primary フラグ DB migration（3箇所更新）
**What:** `prediction.fukusho_prediction` に `is_primary` 列を追加（NULL 許容・DEFAULT false・CHECK 制約）。既存行 backfill + 新規 load 時のデフォルト。
**When to use:** D-09。
**更新箇所（3ファイル連鎖）:**
```python
# 1. src/db/schema.py: PREDICTION_TABLE_DDL に列追加
#    ALTER TABLE prediction.fukusho_prediction ADD COLUMN IF NOT EXISTS is_primary boolean DEFAULT false;
#    CONSTRAINT prediction_is_primary_domain CHECK (is_primary IN (true, false))
#    ※ 既存テーブルへの列追加は ALTER TABLE IF NOT EXISTS で idempotent

# 2. src/model/predict.py: PREDICTION_COLUMNS に "is_primary" 追加（末尾・既存 15→16 列）
#    ※ predict_p_fukusho は is_primary=None（未確定）で予測生成・Phase 6 が UPDATE で確定

# 3. src/db/prediction_load.py: _df_to_prediction_tuples に is_primary 型処理追加
#    ※ None → NULL・True/False → bool・既存行 backfill は UPDATE 別関数
```

### Anti-Patterns to Avoid
- **pandas.groupby/sort でキャリブ指標計算:** 等値要素の index 依存で bit-identical リスク。純 NumPy（bincount/digitize）を使用（debug Specialist 指摘 (f)）
- **sklearn `calibration_curve` の戻り値を直接 ECE/MCE 計算に使用:** count を返さず空 bin を除外して整列するため、bin と count の対応が不明。自前 NumPy 実装を使用
- **事前登録指標 `calibration_max_dev`（uniform・ガードなし）の変更:** T-04-24 後知恵すり替え。D-04 で不変維持・新指標を併記
- **Phase 6 でのモデル再学習・予測再生成:** Phase 4 SC#4 bit-identical 破壊。D-06 で禁止（READ only + is_primary UPDATE のみ）
- **曖昧基準（年次反転・bin 単調性）の機械的 PASS/FAIL 判定:** D-03 で人間判定に委ねる。数値併記のみ
- **quantile binning で重複 edge を無視:** 予測値に同値が多い場合（例: BL-1 の離散値）に `np.quantile` が重複 edge を返す → `np.unique` で対処必須

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| キャリブ指標 binning | pandas.groupby/sort 自前集計 | 純 NumPy `np.digitize`/`np.bincount`/`np.clip`/`np.quantile` | bit-identical 保証（既存 `_compute_calibration_max_dev_guarded` パターン） |
| Spearman 順位相関 | rankdata + pearson 自前実装 | `scipy.stats.spearmanr`（nan_policy='omit'） | ties 処理検証済み・決定論的・既に推移依存で利用可能 |
| Plotly HTML 出力 | 手動 HTML/JS 構築 | `fig.write_html(include_plotlyjs=True)` | 自己完結 offline HTML・~3MB plotly.js 埋込・検証済み API |
| segment groupby | 手動ループで segment 抽出 | `df.groupby(segment_col)` + evaluator binning 関数適用 | groupby 自体は行順序非依存（segment 値で分割のみ）・bit-identical 保証は binning 関数内 |
| is_primary migration | 手動 SQL 文字列組み立て | `psycopg.sql.Identifier` + `ALTER TABLE IF NOT EXISTS` | SQL injection 防御・idempotent・既存 prediction_load パターン踏襲 |
| レポート byte-reproducible | `json.dumps` デフォルト | `json.dumps(sort_keys=True, ensure_ascii=False)` + `_atomic_write_text` | 既存 evaluator.py/report.py パターン・LOW-05 列契約検証 |

**Key insight:** Phase 6 の実装リスクの大部分は、既存 `_compute_calibration_max_dev_guarded`（commit 9fce782）が既に解決している。quantile/ECE/MCE は bin_edges 構築を差し替えるだけで、bit-identical 保証・整列 assert・MIN_BIN_COUNT ガード・y_pred==1.0 clip の全てがそのまま適用できる。

## 受入ゲート判定ロジックの設計（EVAL-02 / D-01/D-02/D-03）

### 構造的 BLOCK（D-02・pytest/CI fail・出荷停止）

D-02 は「LogLoss/Brier で baselines 全敗 ＋ sum(p) が理論値から著しく乖離」を構造的 BLOCK とする。Claude's Discretion で以下の具体閾値を確定する:

**BLOCK 条件1: baselines 全敗（順序付け能力ゼロ = AI 付加価値ゼロ）**

主モデル（lightgbm/catboost 各々）が「LogLoss と Brier の両方で、比較可能な全 baselines より劣る」場合に BLOCK。具体定義:
- 比較対象 baselines: BL-1（頭数別一定）/ BL-4（LR）/ BL-5（LGB 最小）。**BL-2/BL-3 は除外** — BL-2 は reports/04-eval.json で NaN（市場データ merge 空・Phase 6 繰越）、BL-3 は §14.2 caveat「同一情報条件の比較でない」により不公平比較
- 判定: `main_logloss > max(bl1_logloss, bl4_logloss, bl5_logloss) AND main_brier > max(bl1_brier, bl4_brier, bl5_brier)` → BLOCK
- 理由: LogLoss と Brier の両方で全 baselines に劣る = 順序付け能力ゼロ = AI 付加価値ゼロ（SC#2 の本質）。片方のみ劣る場合は WARN（相補完の可能性）
- BL-1 caveat（debug Resolution #4）: BL-1 の calibration_max_dev 構造的極小は「順序付け能力ゼロ（AUC=0.574）の副産物」のため、**LogLoss/Brier 比較には BL-1 を含める**（順序付け性能の公平比較）が calibration_max_dev 比較では注記要

**BLOCK 条件2: sum(p) 著乖離（確率スケール破綻）**

`check_sum_p_distribution`（§15.2 機械検査・既存 evaluator.py:343-410）の violation_rate が閾値超過で BLOCK。具体閾値:
- large バケット（8頭以上）: `large_violation_rate > 0.30` → BLOCK（30% 超のレースが [2.7, 3.3] 範囲外 = 確率スケール破綻）
- small バケット（5-7頭）: `small_violation_rate > 0.30` → BLOCK
- 理由: §15.2 の理論値 [2.7, 3.3] / [1.8, 2.2] から「大きく外れない」の機械的定義。30% は「大きく外れる」の客観的閾値（CONTEXT.md D-02「著乖離」の具体化）。DEBUG Evidence で LightGBM sum_p_mean=3.04・ violation_rate は現状ほぼ 0% のため、この閾値は安全網（現データでは発火しない想定）
- median/SD/p10/p90 は参考レポート（WARN）・機械的 BLOCK 対象外（§15.2「大きく外れるレース条件がある場合は原因確認」は人間判定）

**BLOCK 発火実装:**
```python
# src/model/evaluator.py 新関数
def check_acceptance_gate(
    metrics_dict: dict[str, dict],
    sum_p_check: dict,  # check_sum_p_distribution の戻り値
) -> dict[str, Any]:
    """§15.2 受入ゲート判定（D-01/D-02/D-03）。

    Returns: {block_triggered: bool, block_reasons: list[str],
              warn_metrics: dict[str, float], gate_verdict: "BLOCK"|"WARN"|"PASS"}
    """
    block_reasons = []
    # BLOCK 条件1: baselines 全敗
    comparable_baselines = ["bl1", "bl4", "bl5"]  # BL-2/BL-3 除外
    for main_model in ("lightgbm", "catboost"):
        main_m = metrics_dict.get(main_model, {})
        if not main_m or pd.isna(main_m.get("logloss")):
            continue
        baseline_loglosses = [metrics_dict[b]["logloss"] for b in comparable_baselines
                              if b in metrics_dict and not pd.isna(metrics_dict[b].get("logloss"))]
        baseline_briers = [metrics_dict[b]["brier"] for b in comparable_baselines
                           if b in metrics_dict and not pd.isna(metrics_dict[b].get("brier"))]
        if not baseline_loglosses or not baseline_briers:
            continue
        loses_on_logloss = main_m["logloss"] > max(baseline_loglosses)
        loses_on_brier = main_m["brier"] > max(baseline_briers)
        if loses_on_logloss and loses_on_brier:
            block_reasons.append(
                f"{main_model}: LogLoss({main_m['logloss']:.4f}) and Brier({main_m['brier']:.4f}) "
                f"both worse than all comparable baselines "
                f"(max BL logloss={max(baseline_loglosses):.4f}, "
                f"max BL brier={max(baseline_briers):.4f})")
    # BLOCK 条件2: sum(p) 著乖離
    SUM_P_BLOCK_THRESHOLD = 0.30  # violation_rate 30% 超で BLOCK
    if sum_p_check["large_violation_rate"] > SUM_P_BLOCK_THRESHOLD:
        block_reasons.append(
            f"sum(p) large-bucket violation_rate={sum_p_check['large_violation_rate']:.2%} "
            f"> {SUM_P_BLOCK_THRESHOLD:.0%} (§15.2 [2.7,3.3])")
    if sum_p_check["small_violation_rate"] > SUM_P_BLOCK_THRESHOLD:
        block_reasons.append(
            f"sum(p) small-bucket violation_rate={sum_p_check['small_violation_rate']:.2%} "
            f"> {SUM_P_BLOCK_THRESHOLD:.0%} (§15.2 [1.8,2.2])")

    return {
        "block_triggered": len(block_reasons) > 0,
        "block_reasons": block_reasons,
        "gate_verdict": "BLOCK" if block_reasons else "WARN",  # PASS は WARN 指標も問題ない場合
        # warn_metrics は下記「曖昧 WARN」で計算
    }
```

### 曖昧 WARN（D-03・参考レポート・数値併記・人間判定）

D-03 は「年次キャリブ反転」「bin 単調性」を数値で併記するが PASS/FAIL は人間判定。以下の数値指標を算出して WARN レポートに記載:

**WARN 指標1: 年次 Calibration Curve 極端反転数**
- 年別（race_date.year）で各年の calibration curve を生成（segment_eval.evaluate_segment_axis）
- 各年で bin i と bin i+1 の frac_pos が逆転（frac_pos[i] > frac_pos[i+1]）する回数をカウント
- 全年の反転数の合計と最大を WARN レポートに記載（人間が「極端」か判断）

**WARN 指標2: bin 単調違反数（全体 curve）**
- 全体（test split 全体）の calibration curve で bin i と bin i+1 の frac_pos 逆転回数
- 10 bins で最大 9 回の逆転が可能

**WARN 指標3: Spearman 順位相関（frac_pos vs mean_pred）**
```python
from scipy.stats import spearmanr
# [CITED: docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html]
# frac_pos と mean_pred の Spearman 順位相関（1.0 = 完全単調）
corr, pvalue = spearmanr(bins["frac_pos"], bins["mean_pred"], nan_policy="omit")
# ties は rankdata(method='average') で決定論的・NaN bin は omit で除外
# corr < 0.9 等で参考コメント（閾値は人間判断・D-03 で機械判定しない）
```

### 現状データでの想定（debug レポート・reports/04-eval.json）
- BLOCK 条件1（baselines 全敗）: **発火しない想定** — LightGBM/CatBoost とも LogLoss/Brier で BL-1/BL-4/BL-5 を上回る（reports/04-eval.json: LightGBM logloss=0.47488 < BL-5 0.51305 < BL-4 0.51825 < BL-1 0.52101）
- BLOCK 条件2（sum(p) 著乖離）: **発火しない想定** — LightGBM sum_p_mean=3.04・ CatBoost 3.07 で §15.2 [2.7, 3.3] 範囲内・violation_rate は現状ほぼ 0%
- WARN 指標: bin 0-6 は良好（dev<0.06）・bin 7-8（pred>0.7）で高確率域過信が segment 評価で可視化される（D-06）

## 主モデル確定の実装（D-07/D-08/D-09）

### D-07: 両モデル全指標並列提示 + 人間判断

reports/06-evaluation.md に両モデル（lightgbm/catboost）の全指標を並列表で提示:
- 確率品質: Brier / LogLoss / AUC / quantile_max_dev / ECE / MCE / calibration_max_dev（事前登録）/ calibration_max_dev_guarded / sum(p) mean/median/p10/p90
- backtest 品質: 回収率 / 損益 / maxDD / 購入点数 / 的中率（reports/05-backtest.json から統合）
- D-04 事前登録基準（Calibration 重視）を comment 列で再明示

人間が D-04 基準に照らして主モデルを決定し、理由を reports/06-evaluation.md の所定セクションに記録。

### D-08: タイブレーク規則（Claude's Discretion で具体化）

両モデルが指標で接近（全指標の差が閾値以内）した場合の決定的優先順位:
1. **backtest 回収率（recovery_rate）が高い方** — EV 層（§11）での実効性が最終価値。reports/05-backtest.json の主モデル backtest で比較。30min_before/10min_before 両 policy の平均または優位 policy で比較
2. **計算コストが低い方 = LightGBM** — LightGBM は CatBoost より推論速度が高速（CLAUDE.md Recommended Stack: "~8x faster than one-hot"・CatBoost ordered boosting は計算重）。本番運用（将来 Phase）での推論レイテンシ有利
3. **Brier Score が低い方** — 確率品質の総合指標
4. **LogLoss が低い方** — 確率品質の総合指標
5. **AUC が高い方** — 順序付け能力

固定順序のため決定論的（人間介入なし・後知恵排除）。ただし「接近」の閾値は曖昧なため、reports/06-evaluation.md で「タイブレーク発火有無」と「発火した段階」を明記。

### D-09: is_primary フラグ DB migration

**3ファイル連鎖更新（必須・順序依存）:**

1. **`src/db/schema.py` PREDICTION_TABLE_DDL** — `is_primary boolean DEFAULT false` 列追加 + CHECK 制約。既存テーブルは `ALTER TABLE prediction.fukusho_prediction ADD COLUMN IF NOT EXISTS is_primary boolean DEFAULT false`（idempotent）。`run_apply_schema.py` の APPLY_ORDER に ALTER 追加
2. **`src/model/predict.py` PREDICTION_COLUMNS** — `"is_primary"` を末尾に追加（既存 15列 → 16列）。`predict_p_fukusho` は `is_primary=None`（未確定）で予測生成
3. **`src/db/prediction_load.py`** — `_df_to_prediction_tuples` に is_primary 型処理追加（None→NULL・bool はそのまま）。`_PK_ORDER_COLUMNS` は変更不要（is_primary は PK でない）

**is_primary UPDATE 実装（新関数・etl ロール）:**
```python
# src/db/prediction_load.py または新規 src/db/is_primary_set.py
def set_primary_model(write_cur, *, primary_model_type, primary_model_version,
                      feature_snapshot_id, as_of_datetime):
    """主モデルの is_primary フラグを設定（D-09）。

    選定モデル=true・未選定モデル=false。両モデル行は保持。
    model_type+model_version スコープで UPDATE（prediction_load の staging-swap と同方針）。
    """
    # 全予測行を一旦 false に（当該 feature_snapshot_id+as_of_datetime スコープ）
    write_cur.execute(
        SQL("UPDATE prediction.fukusho_prediction SET is_primary = false "
            "WHERE feature_snapshot_id = %s AND as_of_datetime = %s"),
        (feature_snapshot_id, as_of_datetime))
    # 選定モデルを true に
    write_cur.execute(
        SQL("UPDATE prediction.fukusho_prediction SET is_primary = true "
            "WHERE model_type = %s AND model_version = %s "
            "AND feature_snapshot_id = %s AND as_of_datetime = %s"),
        (primary_model_type, primary_model_version, feature_snapshot_id, as_of_datetime))
```

**既存行 backfill:** 現状の prediction.fukusho_prediction（22,213行 × 2モデル）は is_primary=NULL。ALTER TABLE ADD COLUMN DEFAULT false で既存行も false になる。Phase 6 の主モデル確定後に set_primary_model で選定モデルを true に UPDATE。

**GRANT 権限:** etl ロールは既に prediction スキーマに SELECT/INSERT/UPDATE/DELETE/TRUNCATE を持つ（schema.py GRANT_ETL_SQL）。is_primary UPDATE に追加権限不要。reader ロールは SELECT のみ（is_primary 読取可・Phase 7 Streamlit 用）。

## 統合評価経路の設計（EVAL-01）

### 推奨: 新規 `scripts/run_evaluation.py` で一本化

Phase 4 `run_train_predict.py::_write_eval_report` と Phase 5 `run_backtest.py` は別 CLI。Phase 6 は両者の**成果物**（reports/04-eval.{md,json} + reports/05-backtest.{md,json} + prediction/backtest/label テーブル）を統合読込するため、新規 `scripts/run_evaluation.py` で一本化する。

**理由:**
- Phase 6 は「評価専用フェーズ」・モデル再学習（run_train_predict）・backtest 再実行（run_backtest）を行わない（D-06・Phase 4 SC#4 維持）
- 既存 CLI に評価ステップを追加すると、誤ってモデル再学習/backtest 再実行をトリガーするリスク
- reports/04-eval.{md,json} と reports/05-backtest.{md,json} は JSON で機械可読のため、CLI 間でファイル経由で連携可能

**`scripts/run_evaluation.py` フロー:**
```
1. 成果物読込（readonly ロール）
   - prediction_df ← SELECT * FROM prediction.fukusho_prediction WHERE split='test'
     （両モデル・model_type/model_version/p_fukusho_hit/race_key/entry_count/jyocd/race_date）
   - backtest_metrics ← reports/05-backtest.json の comparison_table
     （または SELECT FROM backtest.fukusho_backtest で再集計）
   - label_df ← SELECT race_key, race_date, entry_count, jyocd, ninki, fukuoddslower,
                       fukusho_hit_validated FROM label.fukusho_label
   - eval_metrics_04 ← reports/04-eval.json の metrics（D-04 事前登録素材）

2. 確率品質指標計算（evaluator.py 拡張）
   - 各モデル × baselines で compute_metrics（quantile_max_dev/ECE/MCE 追加）
   - build_comparison_table 拡張（新指標列）

3. 受入ゲート判定（evaluator.py check_acceptance_gate）
   - 構造的 BLOCK（D-02）: baselines 全敗 + sum(p) 著乖離
   - 曖昧 WARN（D-03）: 年次反転数・bin 単調違反数・Spearman
   - BLOCK 発火時は RuntimeError（pytest/CI fail）

4. segment 別安定性評価（segment_eval.py）
   - 6軸（year/month/jyocd/entry_count/ninki/odds_band）× 各モデル
   - JSON + Plotly HTML 出力（reports/06-segments/）

5. 主モデル確定（D-07/D-08/D-09）
   - 両モデル全指標並列提示 → 人間判断（D-04 基準）+ 理由記録
   - タイブレーク規則（D-08）の適用有無
   - is_primary フラグ UPDATE（etl ロール・set_primary_model）

6. レポート出力
   - reports/06-evaluation.md（人間確認・ゲート判定・主モデル確定記録）
   - reports/06-evaluation.json（sort_keys=True byte-reproducible）
   - reports/06-segments/{axis}.{json,html} × 6軸

CLI 引数: --primary-model {lightgbm,catboost}（人間判断結果・省略時はタイブレーク規則 D-08 適用）
         --feature-snapshot-id（必須・postreview-v2 等）
         --skip-segments（開発時・segment 評価スキップ）
```

### reports/06-evaluation.{md,json} 慣例（Phase 4/5 踏襲）

- **md + json 分離**（review LOW）: md は人間確認・json は `json.dumps(sort_keys=True, ensure_ascii=False)` + `_atomic_write_text` で byte-reproducible
- **md 構造**: # Phase 6 Evaluation Report → ## 受入ゲート判定（BLOCK/WARN） → ## 主モデル比較表（全指標） → ## 主モデル確定（理由記録） → ## segment 安定性サマリ（6軸の scalar 表への参照） → ## 注記（D-04 事前登録基準・BL-1 caveat・BL-3 caveat）
- **json 構造**: `{gate_result, comparison_table, primary_model, segment_summary, constants, notes}`
- **REPORT_COLUMNS 相当**: evaluator.py METRIC_COLUMNS を拡張（quantile_max_dev/ece/mce 追加）・report.py REPORT_COLUMNS パターン踏襲（LOW-05 列契約検証）

## §17.3 テスト構成

### 新規テストファイル

**1. `tests/model/test_evaluator.py`（新規・現在存在しない）**
- `test_compute_metrics_uniform_max_dev`: 既存事前登録指標の不変性（reports/04-eval.json の値と一致）
- `test_quantile_max_dev_bit_identical`: 固定入力で2回呼出し np.array_equal（純 NumPy）
- `test_quantile_max_dev_bl1_bias_removed`: BL-1 の離散値で uniform max_dev と quantile max_dev の差を検証（debug 仮説1 対処）
- `test_ece_weighted_average`: ECE = Σ(n_m/N)|dev| の手計算との一致（Naeini 2015）
- `test_mce_worst_case`: MCE = max|dev| の検証
- `test_mce_min_bin_count_guard`: count<30 bin が除外されること
- `test_y_pred_1_clip`: y_pred==1.0 が正しく最終 bin に入る（Specialist 指摘 (b)）
- `test_quantile_duplicate_edges`: 予測値に同値が多い場合の np.unique 対処
- `test_alignment_assert`: 戻り値と count 配列の整列（Specialist 指摘 (c)）

**2. `tests/model/test_evaluator_gate.py`（新規・ゲート判定）**
- `test_block_baselines_all_lose`: 合成データで主モデルが全 baselines に LogLoss+Brier 両方で劣るケース → block_triggered=True
- `test_block_sum_p_divergence`: 合成データで sum(p) violation_rate>0.30 → block_triggered=True
- `test_block_not_triggered_normal`: reports/04-eval.json の実データ値（LightGBM 優位）→ block_triggered=False
- `test_warn_monotonicity_spearman`: frac_pos と mean_pred の Spearman 順位相関が計算されること
- `test_warn_yearly_inversions`: 年次反転数が正しくカウントされること
- `test_bl1_bl4_bl5_comparable_set`: BL-2/BL-3 が比較対象から除外されること

**3. `tests/model/test_segment_eval.py`（新規・segment 評価 contract）**
- `test_segment_axes_all_six`: 6軸（year/month/jyocd/entry_count/ninki/odds_band）が全て生成されること（D-12）
- `test_segment_curve_binning_contract`: evaluator.py binning 契約（uniform/10bins/MIN_BIN_COUNT=30）が再利用されること
- `test_segment_small_skip`: count<30 の segment 値がスキップされること
- `test_segment_json_schema`: JSON が {curve: {mean_pred, frac_pos, count}, scalar: {ece, mce, max_dev, n_samples}} スキーマに準拠
- `test_segment_plotly_html_self_contained`: HTML に plotly.js が埋込まれていること（include_plotlyjs=True）
- `test_segment_pit_validity`: segment 軸（race_date/jyocd 等）が label.fukusho_label と prediction.fukusho_prediction で一致すること（HIGH-1/HIGH-2 と同一 JOIN 契約）

**4. `tests/db/test_is_primary_flag.py`（新規・DB migration・requires_db）**
- `test_alter_adds_is_primary_column`: ALTER TABLE で is_primary 列が追加されること（idempotent）
- `test_default_false`: 既存行の is_primary=false であること（backfill）
- `test_set_primary_model`: set_primary_model で選定モデル=true・未選定=false になること
- `test_set_primary_model_idempotent`: 2回実行で同一状態（staging-swap と同様・既存 prediction_load パターン）
- `test_both_models_retained`: is_primary 更新後も両モデル行が保持されること（D-09・silent 履歴破壊防止）

### bit-identical 再現性回帰テスト
- `test_repro_quantile_ece_mce`: 固定 seed・固定入力で quantile_max_dev/ECE/MCE が2回呼出しで np.array_equal（Phase 4 SC#4 延長）
- 既存 `test_orchestrator.py::test_reproduce_bit_identical` は予測値レベル・Phase 6 は指標計算レベルで追加

## Common Pitfalls

### Pitfall 1: quantile binning の重複 edge
**What goes wrong:** 予測値に同値が多い場合（例: BL-1 の離散値 [0.167, 0.40]）、`np.quantile(y_pred, np.linspace(0,1,n+1))` が重複 edge を返す。`np.digitize` は重複 edge で誤作動し、bin 割当が不正になる。
**Why it happens:** BL-1 は頭数別の一定確率（13種類の離散値）のため、等頻度分割でも edge が重複する。debug Evidence で BL-1 は 10 bins 中 4 bins のみデータ入り。
**How to avoid:** `np.unique(np.quantile(...))` で重複 edge を削除してから `np.digitize` に渡す。pandas.qcut の `duplicates='drop'` と同効果。単体テスト `test_quantile_duplicate_edges` で検証。
**Warning signs:** quantile binning で bin 数が n_bins より少ない・bin count に 0 が混じる。

### Pitfall 2: y_pred==1.0 の out-of-range
**What goes wrong:** LightGBM の isotonic キャリブが高確率域を 1.0 に saturate する。`np.digitize(y_pred=1.0, bins=[0.1,...,0.9])` は out-of-range で n_bins 番目（範囲外）を返す。`np.bincount(minlength=n_bins)` で IndexError または count 漏れ。
**Why it happens:** debug Evidence: LightGBM worst bin は mean_pred=1.0000, count=13。isotonic 回帰の高確率域 saturate（仮説2 部分支持）。
**How to avoid:** `np.clip(bin_idx, 0, n_bins-1)` で強制的に最終 bin に割当（既存 `_compute_calibration_max_dev_guarded` Specialist 指摘 (b) と同一対処）。単体テスト `test_y_pred_1_clip` で count=13 が正しく拾われることを assert。
**Warning signs:** 最終 bin の count が 0・mean_pred=1.0 の bin が欠落。

### Pitfall 3: 事前登録指標の意図せぬ変更
**What goes wrong:** Phase 6 で `_compute_calibration_max_dev`（uniform・ガードなし・事前登録定義）を「改善」しようとして実装を変更すると、reports/04-eval.json の値と不一致になり T-04-24 後知恵すり替えが発生。
**Why it happens:** debug で判明した uniform max_dev の構造バイアス（BL-1 不当有利化）を「修正」したくなる。
**How to avoid:** D-04 で事前登録指標は不変維持・新指標（quantile/ECE/MCE）を併記。`_compute_calibration_max_dev` には一切触れない。単体テスト `test_compute_metrics_uniform_max_dev` で reports/04-eval.json の値（LightGBM 0.23077・CatBoost 0.25789）と一致を assert。
**Warning signs:** reports/04-eval.json 再生成で calibration_max_dev の値が変わる。

### Pitfall 4: PREDICTION_COLUMNS 更新忘れ（3ファイル連鎖）
**What goes wrong:** schema.py に is_primary 列を追加しても、predict.py PREDICTION_COLUMNS に追加しないと、prediction_load.py の `_df_to_prediction_tuples` が 15列 tuple を生成して INSERT で列数不一致エラー。
**Why it happens:** PREDICTION_COLUMNS は schema.py DDL と 1:1 対応の契約（predict.py docstring 明示）。
**How to avoid:** 3ファイル（schema.py / predict.py / prediction_load.py）を同時更新。単体テスト `test_prediction_columns_matches_ddl` で PREDICTION_COLUMNS と DDL 列数が一致を assert。test_prediction_load.py の既存 idempotent テストで INSERT が成功することを検証。
**Warning signs:** INSERT で "column count mismatch"・既存 idempotent テストの RED。

### Pitfall 5: BL-1 との比較公平性
**What goes wrong:** BL-1 の calibration_max_dev が構造的極小（0.0014）のため、主モデルが BL-1 に「劣る」ように見えるが、これは BL-1 の順序付け能力ゼロ（AUC=0.574）の副産物（debug Resolution #4）。
**Why it happens:** uniform binning が低分散予測を不当に有利化。BL-1 の予測値は [0.167, 0.40] の離散値に集中。
**How to avoid:** D-05 の quantile binning で BL-1 の bin 退化バイアスを解除。比較表議論では BL-1 caveat（「順序付け能力ゼロの副産物」）を明記。BLOCK 条件1（baselines 全敗）の比較対象には BL-1 を含めるが、calibration_max_dev 単独で BL-1 に劣ることは実用上の問題でない旨を注記。
**Warning signs:** 主モデルの calibration_max_dev が BL-1 より大きいが AUC/Brier/LogLoss で BL-1 を大幅に上回る。

### Pitfall 6: segment 軸データの欠損
**What goes wrong:** 人気帯（ninki）やオッズ帯（fukuoddslower）が label.fukusho_label に存在しない・または prediction.fukusho_prediction と JOIN できない。
**Why it happens:** segment 軸のデータ経路（CONTEXT.md specifics: year/month=race_date・競馬場=jyocd・頭数=entry_count・人気帯=ninki・オッズ帯=fukuoddslower 下限）が複数テーブルに分散。
**How to avoid:** researcher が segment 軸のデータ経路を確定（label.fukusho_label + prediction.fukusho_prediction の JOIN で軸が揃うことを確認）。Wave 0 で segment 軸カラムの存在確認テストを追加。欠損軸は WARN で skip（D-12 の「全6軸」は取得可能な軸が揃っている前提）。
**Warning signs:** segment 評価で特定軸が空・JOIN 後行数が減少。

## Code Examples

### ECE/MCE 計算（純 NumPy bit-identical・既存パターン拡張）
```python
# Source: src/model/evaluator.py:259-335 の _compute_calibration_max_dev_guarded を拡張
# [CITED: Naeini et al. 2015 / UW CSE493S calibration-error-comparison.pdf]

def _compute_calibration_metrics_extended(
    y_true: np.ndarray, y_pred: np.ndarray,
) -> dict[str, float]:
    """quantile_max_dev / ECE / MCE を計算（D-05）。

    既存 _compute_calibration_max_dev_guarded の binning ロジックを再利用し、
    strategy='quantile' の bin_edges 構築を追加。bit-identical 保証。
    """
    n_bins = CALIBRATION_CURVE_BINS
    min_bin_count = CALIBRATION_CURVE_MIN_BIN_COUNT

    if len(np.unique(y_true)) < 2:
        return {"quantile_max_dev": float("nan"), "ece": float("nan"),
                "mce": float("nan")}

    # quantile bin_edges（等頻度・重複 edge は np.unique で対処）
    quantile_edges = np.quantile(y_pred, np.linspace(0.0, 1.0, n_bins + 1))
    bin_edges = np.unique(quantile_edges)
    n_bins_actual = len(bin_edges) - 1
    if n_bins_actual < 1:
        return {"quantile_max_dev": float("nan"), "ece": float("nan"),
                "mce": float("nan")}

    # digitize + clip（y_pred==1.0 の out-of-range 対処・Specialist 指摘 (b)）
    bin_idx = np.digitize(y_pred, bins=bin_edges[1:-1], right=False)
    bin_idx = np.clip(bin_idx, 0, n_bins_actual - 1)

    # bincount で (count, pos_sum, pred_sum) を同時計算（bit-identical）
    counts = np.bincount(bin_idx, minlength=n_bins_actual).astype(float)
    pos_sum = np.bincount(bin_idx, weights=y_true.astype(float), minlength=n_bins_actual)
    pred_sum = np.bincount(bin_idx, weights=y_pred, minlength=n_bins_actual)

    nonempty = counts > 0
    counts_ne = counts[nonempty]
    frac_pos = pos_sum[nonempty] / counts_ne
    mean_pred = pred_sum[nonempty] / counts_ne

    # 整列 assert（Specialist 指摘 (c)）
    assert len(counts_ne) == len(frac_pos) == len(mean_pred)

    devs = np.abs(frac_pos - mean_pred)
    N = float(len(y_pred))

    # ECE = Σ(n_m/N)|dev|（重み付け平均）
    ece = float(np.sum(counts_ne / N * devs))

    # MCE = max|dev|（worst-case・MIN_BIN_COUNT ガード付き）
    keep = counts_ne >= min_bin_count
    mce = float(np.max(devs[keep])) if np.any(keep) else float("nan")

    # quantile_max_dev（ガード付き・uniform_max_dev_guarded と対比）
    quantile_max_dev = mce  # 同一（MCE と定義一致）

    return {"quantile_max_dev": quantile_max_dev, "ece": ece, "mce": mce}
```

### Spearman 順位相関（bin 単調性 WARN・D-03）
```python
# [CITED: docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html]
from scipy.stats import spearmanr

def compute_monotonicity_warn(bins: dict) -> dict[str, float]:
    """calibration curve の bin 単調性 WARN 指標（D-03・人間判定参考）。

    frac_pos と mean_pred の Spearman 順位相関・bin 逆転数を算出。
    ties は rankdata(method='average') で決定論的・NaN bin は omit で除外。
    """
    frac_pos = bins["frac_pos"]
    mean_pred = bins["mean_pred"]
    if len(frac_pos) < 2:
        return {"spearman_corr": float("nan"), "spearman_pvalue": float("nan"),
                "bin_inversions": 0}
    corr, pvalue = spearmanr(frac_pos, mean_pred, nan_policy="omit")
    # bin 逆転数（frac_pos[i] > frac_pos[i+1] の回数）
    inversions = int(np.sum(np.diff(frac_pos) < 0))
    return {"spearman_corr": float(corr), "spearman_pvalue": float(pvalue),
            "bin_inversions": inversions}
```

### is_primary DB migration（idempotent ALTER）
```python
# src/db/schema.py 追加（APPLY_ORDER に含める）
PREDICTION_ADD_IS_PRIMARY_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS is_primary boolean DEFAULT false;
ALTER TABLE prediction.fukusho_prediction
    ADD CONSTRAINT prediction_is_primary_domain
    CHECK (is_primary IN (true, false));
"""
# COMMENT ON COLUMN も追加（provenance 説明）
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| uniform binning のみ calibration_max_dev | uniform（事前登録維持）+ quantile/ECE/MCE 併記 | Phase 6（D-04/D-05） | BL-1 の bin 退化バイアス解除・robust 指標追加。事前登録指標は不変（T-04-24 回避） |
| calibration_max_dev 単独（worst-case 過敏） | ECE（重み付け平均・robust）+ MCE（worst-case）併記 | Phase 6（D-05・Naeini 2015） | 極小 bin ノイズの影響を ECE で緩和・MCE で worst-case 把握 |
| 全体 calibration curve のみ | 6軸 segment 別 calibration curve | Phase 6（EVAL-03/D-12） | aggregate 回収率に隠れる segment collapse を可視化 |

**Deprecated/outdated:**
- `calibration_max_dev`（uniform・ガードなし）の単独使用: 事前登録指標として温存するが、Phase 6 では quantile/ECE/MCE と併記し単独では判定基準にしない（debug 診断結果反映）

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | plotly の最新安定版が 6.x 系（planner が `uv add plotly` で確認要） | Standard Stack / Supporting | 版数の違いで API 互換性リスク。write_html API は安定（長期間変更なし）のため低リスク |
| A2 | segment 軸（ninki/odds_band）のデータが label.fukusho_label + prediction.fukusho_prediction の JOIN で揃う | segment 別安定性・Pitfall 6 | 軸が欠損すると D-12「全6軸」が履行不能。Wave 0 でカラム存在確認テスト必須。researcher が CONTEXT.md specifics で「揃うことを確認」と明記しているが実コードで未検証 |
| A3 | BLOCK 条件2 の sum(p) violation_rate 閾値 30% が適切 | 受入ゲート判定ロジック | 閾値が緩すぎると破綻モデルを通過・厳しすぎると正常モデルを BLOCK。現データ（LightGBM sum_p_mean=3.04）では violation_rate ほぼ 0% のため発火しない想定・planner とユーザーで最終確認要 |
| A4 | タイブレーク規則の「接近」閾値が客観的に定義可能 | 主モデル確定 D-08 | 閾値が曖昧だと人間判断に後退。reports/06-evaluation.md で「タイブレーク発火有無」を明記すれば低リスク（現データでは LightGBM が全指標で CatBoost を上回るため発火しない想定） |
| A5 | scipy が sklearn 推移依存で pyproject.toml 明示的追加不要 | Standard Stack / 既存 | scipy が利用不可の場合 spearmanr が ImportError。`uv pip show scipy` で確認要（sklearn 1.9.0 は scipy に依存） |

**If this table is empty:** 上記5件の ASSUMED クレームあり。planner は A1（plotly 版数）・A3（sum(p) 閾値）・A4（タイブレーク閾値）をユーザー確認または checkpoint:human-verify で確定すること。A2（segment 軸）は Wave 0 テストで検証。

## Open Questions (RESOLVED)

> 実質的全問解決済み。各問に RESOLVED マーカーで対応 Plan/Task を付記。

1. **segment 軸の ninki/odds_band データ経路の実コード確認** — RESOLVED: Plan 06-01 Task 2（test_segment_axis_columns・実 DB で information_schema.columns を確認・取得可能軸を記録済）+ Plan 06-03 SEGMENT_AXES で経路確定
   - What we know: CONTEXT.md specifics が「label.fukusho_label + prediction.fukusho_prediction にこれら軸が揃うことを確認（researcher 確定）」と記載
   - What's unclear: ninki（人気）と fukuoddslower（複勝オッズ下限）が具体的にどのテーブルのどのカラムに存在するか。prediction.fukusho_prediction の現 DDL（schema.py）には ninki/odds 列が**存在しない**（model_type/model_version/.../p_fukusho_hit/race_date/split のみ）
   - Recommendation: Wave 0 で `SELECT column_name FROM information_schema.columns WHERE table_name='fukusho_label'` と prediction テーブルで ninki/odds 系カラムの存在を確認。欠損時は label.fukusho_label から JOIN で取得（race_key 単位）。planner はこの確認タスクを Wave 0 に含める

2. **BLOCK 条件の閾値（sum(p) violation_rate 30%・baselines 全敗の BL 選択）の最終確認** — RESOLVED: Plan 06-02 Task 2（check_acceptance_gate 定数化: SUM_P_BLOCK_THRESHOLD=0.30 / COMPARABLE_BASELINES=("bl1","bl4","bl5")）+ CONTEXT D-02 で BL-2/BL-3 除外確定
   - What we know: D-02「baselines 全敗 + sum(p) 著乖離」を Claude's Discretion で具体化
   - What's unclear: 30% が適切か・BL-2/BL-3 除外が妥当か（BL-2 は NaN・BL-3 は §14.2 caveat）
   - Recommendation: planner が提案閾値を PLAN.md に明記し、ユーザーが discuss/execute で確認。現データでは発火しない安全網のため、閾値の正確性より「構造的 BLOCK が存在すること」が重要

3. **reports/06-evaluation.json の主モデル確定記録の形式** — RESOLVED: Plan 06-05 Task 1（json schema 設計: primary_model: {model_type, model_version, feature_snapshot_id, as_of_datetime, selection_reason, tiebreak_applied}）
   - What we know: D-07「人間判断・理由記録」・D-09「is_primary フラグ」
   - What's unclear: 人間が判断した主モデルと理由を json にどう記録するか（primary_model フィールド + selection_reason テキスト？）
   - Recommendation: planner が json schema を設計。`primary_model: {model_type, model_version, feature_snapshot_id, as_of_datetime, selection_reason: str, tiebreak_applied: str|null}`

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | 全体 | ✓ | 3.12.13 | — |
| PostgreSQL 15 | prediction/label/backtest テーブル READ・is_primary UPDATE | ✓ | 15.18 (Homebrew) | — |
| psycopg3 (psycopg[binary]) | DB 接続 | ✓ | 3.3.4 | — |
| NumPy ≥2.0 | キャリブ指標 bit-identical binning | ✓ | 推移依存（pandas/sklearn） | — |
| pandas 3.0.3 | DataFrame 処理・segment groupby | ✓ | 3.0.3 | — |
| scikit-learn 1.9.0 | calibration_curve・brier/logloss/auc | ✓ | 1.9.0 | — |
| scipy（推移依存） | spearmanr（bin 単調性 WARN） | ✓（要確認） | sklearn 推移依存 | 純 NumPy rankdata+pearson（再発明・非推奨） |
| **plotly** | segment 別 Plotly HTML 出力（D-10） | ✗ | — | matplotlib PNG（D-10 が Plotly HTML を固定のため fallback 不可・要 `uv add plotly`） |
| uv | 依存管理・lockfile | ✓ | 0.11.21 | — |
| pytest 9.1.0 | テスト実行 | ✓ | 9.1.0 | — |

**Missing dependencies with no fallback:**
- **plotly**: D-10 が JSON + Plotly HTML を固定。`uv add plotly` で追加必須（planner が Wave 0 で実行）

**Missing dependencies with fallback:**
- scipy が何らかの理由で利用不可の場合: 純 NumPy（`scipy.stats.rankdata` を自前実装 + pearson）で代用可能だが、ties 処理の検証コストが高いため非推奨。`uv pip show scipy` で確認後、利用可能なら scipy を使用

## Validation Architecture

> nyquist_validation が有効（config.json workflow.nyquist_validation=true）。このセクションは VALIDATION.md 生成の前提。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存・pyproject.toml pin） |
| Config file | pyproject.toml [tool.pytest.ini_options]（testpaths=["tests"]・markers=["requires_db"]） |
| Quick run command | `uv run pytest tests/model/test_evaluator.py tests/model/test_evaluator_gate.py tests/model/test_segment_eval.py -x` |
| Full suite command | `uv run pytest tests/`（KEIBA_SKIP_DB_TESTS=1 で DB テスト skip・unset で全実行） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EVAL-01 | 統合評価経路（的中率/回収率/P/L/maxDD/購入点数/Brier/LogLoss/Calib Curve） | integration | `uv run pytest tests/model/test_evaluator.py -x` | ❌ Wave 0 新規 |
| EVAL-01 | run_evaluation.py E2E（reports/06-evaluation.{md,json} 生成） | smoke | `uv run python scripts/run_evaluation.py --feature-snapshot-id 20260620-1a-postreview-v2 --primary-model lightgbm` | ❌ Wave 0 新規 |
| EVAL-02 | 構造的 BLOCK（baselines 全敗）正発火 | unit | `uv run pytest tests/model/test_evaluator_gate.py::test_block_baselines_all_lose -x` | ❌ Wave 0 新規 |
| EVAL-02 | 構造的 BLOCK（sum(p) 著乖離）正発火 | unit | `uv run pytest tests/model/test_evaluator_gate.py::test_block_sum_p_divergence -x` | ❌ Wave 0 新規 |
| EVAL-02 | 曖昧 WARN（Spearman・反転数）算出 | unit | `uv run pytest tests/model/test_evaluator_gate.py::test_warn_monotonicity_spearman -x` | ❌ Wave 0 新規 |
| EVAL-03 | 6軸 segment 評価全生成（D-12） | unit | `uv run pytest tests/model/test_segment_eval.py::test_segment_axes_all_six -x` | ❌ Wave 0 新規 |
| EVAL-03 | segment curve binning 契約（evaluator 再利用） | unit | `uv run pytest tests/model/test_segment_eval.py::test_segment_curve_binning_contract -x` | ❌ Wave 0 新規 |
| EVAL-03 | Plotly HTML 自己完結 | unit | `uv run pytest tests/model/test_segment_eval.py::test_segment_plotly_html_self_contained -x` | ❌ Wave 0 新規 |
| D-05 | quantile_max_dev/ECE/MCE bit-identical | unit | `uv run pytest tests/model/test_evaluator.py::test_quantile_max_dev_bit_identical -x` | ❌ Wave 0 新規 |
| D-05 | ECE 重み付け平均（Naeini 2015） | unit | `uv run pytest tests/model/test_evaluator.py::test_ece_weighted_average -x` | ❌ Wave 0 新規 |
| D-09 | is_primary migration idempotent | integration (requires_db) | `uv run pytest tests/db/test_is_primary_flag.py -x` | ❌ Wave 0 新規 |
| D-09 | is_primary set で両モデル保持 | integration (requires_db) | `uv run pytest tests/db/test_is_primary_flag.py::test_both_models_retained -x` | ❌ Wave 0 新規 |
| bit-identical | 指標計算再現性 | unit | `uv run pytest tests/model/test_evaluator.py::test_repro_quantile_ece_mce -x` | ❌ Wave 0 新規 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/model/test_evaluator.py tests/model/test_evaluator_gate.py tests/model/test_segment_eval.py -x`（quick・DB 不要）
- **Per wave merge:** `uv run pytest tests/`（full suite・KEIBA_SKIP_DB_TESTS=1 で quick・unset で DB 含む）
- **Phase gate:** Full suite green before `/gsd-verify-work`・`KEIBA_SKIP_DB_TESTS` unset で requires_db テスト全実行（is_primary migration は live DB 必須）

### Wave 0 Gaps
- [ ] `tests/model/test_evaluator.py` — covers EVAL-01/D-05（キャリブ指標・bit-identical）
- [ ] `tests/model/test_evaluator_gate.py` — covers EVAL-02（ゲート判定 BLOCK/WARN）
- [ ] `tests/model/test_segment_eval.py` — covers EVAL-03（segment 評価 6軸）
- [ ] `tests/db/test_is_primary_flag.py` — covers D-09（is_primary migration・requires_db）
- [ ] Framework install: `uv add plotly`（plotly が pyproject.toml に未追加）

*(test_evaluator.py が現在存在しないことは要注記 — evaluator.py は Phase 4 で実装されたが単体テストが未作成。Phase 6 で evaluator.py を拡張する際に必ず新設すること)*

## Security Domain

> security_enforcement が有効（config.json workflow.security_enforcement=true・security_asvs_level=1・security_block_on=high）。Phase 6 は評価専用フェーズ・新規ユーザ入力面なし・既存 DB ロール分離を踏襲。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local-only・Streamlit 認証なし（Phase 7）。Phase 6 は CLI・DB 認証は psycopg3 接続（既存） |
| V3 Session Management | no | CLI・session 概念なし |
| V4 Access Control | yes | DB ロール分離: readonly（READ prediction/label/backtest）+ etl（is_primary UPDATE）。schema.py GRANT_READER_SQL/GRANT_ETL_SQL 既存・追加権限不要 |
| V5 Input Validation | yes | CLI 引数（--primary-model）の検証・model_type domain CHECK 制約（既存 schema.py prediction_model_type_domain） |
| V6 Cryptography | no | 暗号化処理なし |
| V7 Error Handling | yes | 構造的 BLOCK は RuntimeError で fail-loud（silent でない）・空入力拒否（prediction_load パターン踏襲） |
| V9 Communications | no | ネットワーク通信なし（local PostgreSQL のみ） |

### Known Threat Patterns for Phase 6 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection（is_primary UPDATE） | Tampering | `psycopg.sql.Identifier` + parameterized query（既存 prediction_load.py パターン・文字列組み立て禁止） |
| 後知恵すり替え（is_primary フラグ） | Tampering/Elevation | D-07 人間判断・理由記録・Phase 8 対抗的監査（TEST-01）。reports/06-evaluation.md で選定理由を監査可能形で記録 |
| 事前登録指標の改変（T-04-24） | Tampering | D-04 事前登録指標不変・単体テスト test_compute_metrics_uniform_max_dev で reports/04-eval.json の値と一致 assert |
| silent 履歴破壊（is_primary UPDATE） | Tampering | model_type+model_version スコープ UPDATE（全行 UPDATE でなく）・set_primary_model の idempotent テスト・両モデル保持 assert（D-09） |

## Sources

### Primary (HIGH confidence)
- **既存コード契約（scout 確認済・実装の正）:**
  - `src/model/evaluator.py:148-335` — compute_metrics / _compute_calibration_max_dev / _compute_calibration_max_dev_guarded（純 NumPy binning テンプレート・bit-identical）
  - `src/model/evaluator.py:343-410` — check_sum_p_distribution（§15.2 機械検査・large/small バケット）
  - `src/ev/metrics.py:30-107` — compute_backtest_metrics（回収率/P/L/maxDD/購入点数・純粋関数）
  - `src/ev/report.py:41-53` — REPORT_COLUMNS（列契約・LOW-05 md/json 1:1 検証パターン）
  - `src/db/schema.py:59-94` — PREDICTION_TABLE_DDL（11カラム PK + 3 CHECK 制約）
  - `src/db/prediction_load.py:174-348` — _idempotent_load_prediction（model_version スコープ staging-swap・Identifier/Placeholder）
  - `src/model/predict.py:62-82` — PREDICTION_COLUMNS（15列・schema.py DDL と 1:1）
  - `scripts/run_train_predict.py:490-570` — _write_eval_report（統合評価パターン・evaluator 形式変換）
  - `reports/04-eval.json` — 実データ値（LightGBM/CatBoost/BL-1..5 の metrics・D-04 事前登録素材）
- **`.planning/debug/calib-maxdev-vs-baselines.md`** — uniform max_dev 構造バイアス診断 + Resolution（quantile/ECE/MCE 併記）+ Specialist SUGGEST_CHANGE 8点（純 NumPy・bit-identical・y_pred==1.0 clip・整列 assert）
- **`docs/keiba_ai_requirements_v1.3.md`** §15.1/§15.2/§15.3/§14.2 — 評価指標・受入基準・Calibration 評価軸・baselines 定義（正）

### Secondary (MEDIUM confidence)
- [scikit-learn 1.9.0 calibration_curve](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html) — strategy='quantile'（等頻度 binning）・count 返さず空 bin 除外（自前 NumPy の根拠） [CITED]
- [scipy.stats.spearmanr](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html) — nan_policy='omit'・ties は rankdata('average') で決定論的 [CITED]
- [plotly write_html](https://plotly.com/python/interactive-html-export/) — include_plotlyjs=True で自己完結 offline HTML [CITED]
- [Naeini et al. 2015 / UW CSE493S calibration-error-comparison.pdf](https://courses.cs.washington.edu/courses/cse493s/25au/calibration-error-comparison.pdf) — ECE/MCE 標準定義・MCE ≤ ECE ≤ m·MCE 関係式 [CITED]
- [numpy.quantile](https://numpy.org/doc/2.2/reference/generated/numpy.quantile.html) — quantile bin_edges 構築 [CITED]

### Tertiary (LOW confidence)
- [ICLR 2025 blog: Understanding Model Calibration](https://iclr-blogposts.github.io/2025/blog/calibration/) — ECE drawback・equal-frequency binning の解説（背景知識・実装には直接使用しない）
- [towardsdatascience: ECE step-by-step](https://towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d/) — ECE 実装例（参考・Naeini 定義と一致を確認）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 既存コード契約（evaluator.py/metrics.py/schema.py/prediction_load.py）が実装の正・plotly/scipy は WebSearch で API 検証済み
- Architecture: HIGH — Phase 4/5 の確立したパターン（staging-swap・md/json 分離・binning 契約）の直接拡張。新規アーキテクチャ概念なし
- Pitfalls: HIGH — debug calib-maxdev-vs-baselines.md で実データベースの落とし穴が全て診断済み（BL-1 バイアス・y_pred==1.0・MIN_BIN_COUNT・高確率域過信）。Specialist SUGGEST_CHANGE 8点が対処法を提示

**Research date:** 2026-06-23
**Valid until:** 2026-07-23（30日・安定ドメイン・既存コード契約ベースのため長め。plotly 版数のみ planner が `uv add` 時に確認要）
