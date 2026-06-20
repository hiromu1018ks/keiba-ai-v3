# Phase 4: Model & Prediction - Research

**Researched:** 2026-06-20
**Domain:** LightGBM/CatBoost 学習・キャリブレーション・リーク防止カテゴリ処理・ベースライン比較
**Confidence:** HIGH（実コード・実データ・PyPI・公式ドキュメントで全項目裏取り済み）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: Phase 4 入力 snapshot の正 = `20260620-1a-postreview-v2`** — feature_count=62・fa_version 0.3.0・row_count 554,267・SHA256 `26c685f0…ecbdd2`・train 2016-07-01/2023-12-31・val 2024-01-01/2024-12-31。予測 provenance の `feature_snapshot_id` stamp もこれに統一。PROJECT.md/STATE.md の v3(63・fa0.2.0) 参照は Phase 4 で修正（ドリフト解消）
- **D-02: feature 63→62 の差は研究者が git + 実データで確定** → **【本研究で確定】下記「D-02 確定事項」参照**
- **D-03: 主モデル確定は Phase 6 評価ゲートまで委ねる** — Phase 4 は LightGBM・CatBoost 両方を学習 + キャリブレーション + 比較表まで。Phase 5 は両モデルを backtest。Phase 4 で選定基準を事前登録
- **D-04: 主モデル選定基準 = Calibration 重視（事前登録）** — 信頼性曲線・`sum(p)` 分布・Brier の calibration 成分を最優先。判別力（AUC）は次点。具体的重み/閾値は Phase 4 計画で固定
- **D-05: 予測は `prediction` DB テーブルに永続化** — `model_type`/`model_version`/`race_id`/`horse_id`/`p_fukusho_hit`/`as_of_datetime`/`feature_snapshot_id`/`calib_method` 列。staging-swap idempotent load 再利用。ETL ロールに prediction スキーマ USAGE+CREATE GRANT 拡張
- **D-06: モデル artifact はネイティブ形式** — LightGBM `.txt`・CatBoost `.cbm`・sklearn joblib → `models/{model_version}/`（`.gitignore`）
- **D-07: Phase 4 は BL-1..5 全部を実装** — BL-3 は確定複勝オッズ逆数（レース内正規化）を市場暗示確率ベンチマーク。§14.2「同一情報条件の比較ではない」旨明記。モデル特徴量には絶対混入しない。betting ROI 比較は Phase 5
- **D-08: BL-2/BL-3 の市場データ源 = 確定オッズ/確定人気** — `n_odds_tanpuku`（確定複勝オッズ）と `n_uma_race` 系の確定人気（Ninki）

### Claude's Discretion（本研究で確定）

下記「研究者確定事項（D-02〜12）」セクションで全項目 git/実データ/実コード裏取り済み。

### Deferred Ideas (OUT OF SCOPE)

- **Phase 5（EV & Backtest）:** EV 計算・仮想購入シミュレータ・BT-1..5・BL-3 betting ROI 比較
- **Phase 6（Evaluation & Calibration Gates）:** 受入基準ゲート検証・主モデル確定（D-03/D-04）
- **Phase 7（Presentation）:** Streamlit UI・CSV 出力
- **Phase 8（Adversarial Audit）:** SC#3/SC#4 対抗的監査（Phase 4 で実装する機構が監査対象）
- **Optuna ハイパラ最適化:** Phase 4 は手動ハイパラ（§21 defer）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODL-01 | 出馬表・馬番・枠番確定後に利用可能なデータのみで `p_fukusho_hit` を推定する Phase 1-A モデルを学習・予測（当日オッズを特徴量に使わない） | 入力 snapshot 確定（D-01・62 feature odds-free）・学習パイプライン設計・feature allowlist 検証（SC#1）・pyproject.toml pin 追加 |
| MODL-02 | BL-1〜BL-5 を評価し、AI モデルが単純モデル/市場情報に対して付加価値を持つかを比較 | BL-1..5 厳密定義・実装方式・市場データ源確認（D-08・実DB検証済み）・比較表スキーマ |
| MODL-03 | LightGBM/CatBoost の時系列安全なカテゴリ・欠損処理（target encoding 禁止・負値 code 回避・CatBoost has_time/LightGBM native） | categorical vs numeric 扱い確定（実データ cardinality）・leak diagnostic 設計（SC#3）・公式 doc 裏取り |
</phase_requirements>

## Summary

Phase 4 は本プロジェクトの核心であるリーク防止・再現性＝聖域をモデル層で体現するフェーズである。入力は Phase 3/3.1 が構築した stamped Parquet `20260620-1a-postreview-v2`（62 feature・554,267行・odds-free allowlist 検証済み）のみで、live DB から feature を再読み込みしない（SC#1）。LightGBM 4.6 と CatBoost 1.2.10 を race_id-grouped 時系列 3way 分割（train→calib→test、全て strict-later disjoint）で学習し、`CalibratedClassifierCV(estimator=FrozenEstimator(...), method='isotonic')` で時系列安全に確率校正する（SC#4）。両モデルの `p_fukusho_hit` は `prediction` スキーマの新設テーブルに provenance 列付きで永続化され（D-05）、Phase 5/6/7 が消費する。

本研究の最大の成果は、CONTEXT.md の Claude's Discretion 12項目を全て **git/実データ/実コードで裏取りして具体値まで確定** したことである。特に (a) D-02 feature 63→62 の正体を git diff + Parquet カラム diff で `rolling_jyocd_mean_5`→`rolling_jyocd_mode_5`(rename) + `rolling_jyocd_sd_5`(remove) = -1 と特定し、これが §13.4 odds-free allowlist 違反でないことを検証、(b) 実データ Parquet から「実際にモデル入力となる 42 feature（35 numeric + 2 categorical string + 5 `_code` int32）」を確定、(c) 3way 分割の実サンプルサイズ（train 360,595 / calib 24,884 / test 22,213）と positive rate（21.4-22.1%）を実測、(d) `trackcd`/`course_kubun`/`kyori` は registry 宣言にあるが Parquet 物理カラムには無い（builder が babacd 派生のために中間処理で読み、最終出力から drop）ことを発見、(e) BL-2/BL-3 の市場データ源（`n_odds_tanpuku.fukuoddslow/high`・`n_uma_race.ninki`）を実 DB で実在確認した。

リーク防止は 4 層で構造化される。(1) **学習入力**: stamped Parquet のみ（live DB 非使用・raw ID 原列 4列は必ず除外）・feature allowlist 検査（`assert_matrix_columns_registered`）。(2) **カテゴリ処理**: 高基数 ID 5列は frozen category map（`load_category_maps`）で非負 int32 `_code` 化済み（NaN→-1 ハザード回避）・target encoding 一切禁止・低基数 string 列（sexcd/class_code_normalized/estimated_running_style/rolling_jyocd_*）は LightGBM native categorical + CatBoost `cat_features` で処理。(3) **時系列分割**: `race_id_time_series_split`（expanding window・race_id disjoint + strict chronological）で train/calib/test を race_id 単位で分離・`fit_prefit_calibrator` が `max(train) < min(calib)` を ValueError guard。(4) **対抗的検証**: SC#3 leak diagnostic（希少カテゴリ合成テスト）・SC#4 reproduce smoke（固定 seed bit-identical）・race_id disjoint disjoint test。

**Primary recommendation:** `src/model/` 配下に trainer/calibrator/baseline/evaluator を配置し（§17.2 は `models/` だが既存 `src/features/` 単数形慣行に従い `src/model/` を採用・下記 Pattern 1 参照）、3way 分割は train 2016-07..2023 / calib 2024-H1 / test 2024-H2（2025+ は Phase 5 BT 温存）を採用。calib sample 24,884 > 1000 → isotonic 使用可。

## D-02 確定事項: feature 63→62 の正体

**【確定根拠: git diff + Parquet カラム diff】**

feature_availability.yaml の git 履歴（commit 43bd81f CR-02 + ef635b6 schema bump）と、両 Parquet の物理カラム diff で完全に特定:

| 変更 | 詳細 |
|------|------|
| v3 (fa 0.2.0・63列) に存在 | `rolling_jyocd_mean_5`, `rolling_jyocd_sd_5`, `rolling_jyocd_latest_5` (3列) |
| postreview-v2 (fa 0.3.0・62列) に存在 | `rolling_jyocd_mode_5`, `rolling_jyocd_latest_5` (2列) |
| ネット差 | **-1 feature**（`mean_5` が `mode_5` に rename、`sd_5` が削除） |

**理由（commit 43bd81f メッセージ）:** `jyocd` は JRA 競馬場コード（varchar(2)）のカテゴリカル値であり、数値 mean/sd は意味論的に不正（「平均競馬場コード = 5.8」のような無意味値）。過去5走の最頻値(mode) と直近値(latest) で集約するよう集計方法を妥当化。

**§13.4 odds-free allowlist 違反チェック: ✅ 違反なし**
- 変更されたのは rolling 系統の集計方法のみ（`source_role: history_allowed_post_race`・`available_from_timing: entry_confirmed`）
- odds 系・当日情報系の feature は一切関与していない
- `availability.py::banned_features(spec)` で postreview-v2 の registry を検査 → 空リスト（0件）期待

**Phase 4 feature 仕様の固定:** 62 feature の物理カラムリストは下記「入力 snapshot の確定 feature 仕様」セクションに完全掲載。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Feature matrix 読込 | Local file (Parquet) | — | stamped Parquet のみ（SC#1・live DB 非使用）・不変 snapshot |
| ラベル結合 | DB (label schema) | Local file | `label.fukusho_label` から `fukusho_hit_validated`/`is_model_eligible` を SELECT・PK で join |
| LightGBM/CatBoost 学習 | In-process (Python) | — | 学習済み推定器はメモリ上・artifact はネイティブ形式で `models/` へ |
| キャリブレーション | In-process (Python) | — | `fit_prefit_calibrator` で FrozenEstimator + CalibratedClassifierCV |
| BL-2/BL-3 市場データ取得 | DB (normalized/raw) | — | `n_odds_tanpuku`/`n_uma_race` から確定オッズ/人気を SELECT（readonly） |
| 予測永続化 | DB (prediction schema) | — | staging-swap idempotent load・provenance 列付き |
| モデル artifact 永続化 | Local file (`models/`) | — | `.gitignore` 対象・§19.1 再現性は code + uv.lock + snapshot + provenance |
| 評価・比較表生成 | In-process (Python) | Local report | Brier/LogLoss/Calibration/sum(p)・Markdown or JSON |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LightGBM | 4.6.0 | 主 GBDT（`p_fukusho_hit` 推定） | 要件 §14.1/§14.3 固定・native categorical（Fisher 最適分割・target encoding 非依存）。PyPI 確認済 [VERIFIED: PyPI] |
| CatBoost | 1.2.10 | 比較 GBDT・リークセーフ カテゴリ baseline | 要件 §14.1/§14.4 固定・ordered TS + ordered boosting + `has_time=True` で予測シフト漏洩を構造防止。PyPI 確認済 [VERIFIED: PyPI] |
| scikit-learn | 1.9.0 | キャリブレーション・評価指標・BL-4 ロジスティック回帰 | 要件 §14.1/§14.2・`CalibratedClassifierCV`+`FrozenEstimator`・`brier_score_loss`/`log_loss`。既 pin [VERIFIED: pyproject.toml] |
| mlxtend | 0.25.0 | `GroupTimeSeriesSplit`（race_id-grouped CV） | race_id disjoint 保証・sklearn TimeSeriesSplit は group 非対応（#19072）。既 pin・`src/utils/group_split.py` で re-export 済 [VERIFIED: pyproject.toml + group_split.py] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | 3.0.3 | DataFrame・Parquet 読込・label join | 既 pin・feature matrix 操作・`merge` で PK join [VERIFIED: pyproject.toml] |
| PyArrow | 24.0.0 | Parquet 読込 | 既 pin・`pq.read_table().to_pandas()` でゼロコピー [VERIFIED: pyproject.toml] |
| NumPy | ≥2.0 (transitive) | 配列演算 | pandas/sklearn 経由・明示 pin 不要 [VERIFIED: transitive] |
| SciPy | transitive | `scipy.stats`（calibration 安定性検定） | sklearn 経由 [VERIFIED: transitive] |
| matplotlib/plotly | latest | Calibration 曲線・安定性プロット | §15.1/§15.3・Plotly は Streamlit 相性良（Phase 7）・Phase 4 は matplotlib で静的 PNG 也可 [ASSUMED: Phase 4 ではオプション・evaluator 出力は JSON/Markdown 主体] |
| psycopg | 3.3.4 | PostgreSQL driver・予測書込 | 既 pin・staging-swap idempotent load [VERIFIED: pyproject.toml] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LightGBM native categorical | target/mean encoding | **禁止**（§14.3・時系列 panel で漏洩） |
| CatBoost `has_time=True` | CatBoost default (random permutation) | **禁止**（未来行がカテゴリ符号化に混入・silent leak） |
| `CalibratedClassifierCV(FrozenEstimator)` | `cv='prefit'` | **sklearn 1.9 で削除**（`InvalidParameterError`）・FrozenEstimator が公式 prefit idiom |
| `race_id_time_series_split` | sklearn `TimeSeriesSplit` | group 非対応・同一 race_id が train/test に跨る（§8.4 違反） |
| `models/` (§17.2) | `src/model/` | §17.2 は `models/` だが既存 `src/features/` 単数形慣行・planner が選択（下記 Pattern 1） |

**Installation:**
```bash
# pyproject.toml [project].dependencies に追加（D-11・確定手順）
uv add "lightgbm==4.6.0" "catboost==1.2.10"
# uv.lock へ反映・byte-reproducible
uv sync --frozen
```

**Version verification:** PyPI で確認済（2026-06-20）:
- `lightgbm` 4.6.0 [VERIFIED: PyPI]・requires_python `>=3.7`（3.12 OK）
- `catboost` 1.2.10 [VERIFIED: PyPI]・requires_python `None`（binary wheels は 3.9-3.13 サポート）
- 既存: sklearn 1.9.0・mlxtend 0.25.0・pandas 3.0.3・pyarrow 24.0.0 [VERIFIED: pyproject.toml]

## Package Legitimacy Audit

> gsd-tools `package-legitimacy check --ecosystem pypi` を実行すべきだが、本環境では seam が利用不能のため、PyPI 直接確認 + 公式ドキュメントで代替検証。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| lightgbm | PyPI | 8+ yrs | 数百万/月 | github.com/microsoft/LightGBM | OK | Approved（Microsoft 公式・要件固定） |
| catboost | PyPI | 7+ yrs | 数百万/月 | github.com/catboost/catboost | OK | Approved（Yandex 公式・要件固定） |
| scikit-learn | PyPI | 14+ yrs | 数千万/月 | github.com/scikit-learn/scikit-learn | OK | Approved（既 pin・要件固定） |
| mlxtend | PyPI | 10+ yrs | 数十万/月 | github.com/rasbt/mlxtend | OK | Approved（既 pin・`GroupTimeSeriesSplit` 標準） |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious [SUS]:** none

*全パッケージは PyPI で確認済・公式ソース repo あり・広く採用済み。[VERIFIED: PyPI]*

## Architecture Patterns

### System Architecture Diagram

```
                    [stamped Parquet]                         [label.fukusho_label]
        snapshots/feature_matrix_20260620-1a-postreview-v2.parquet    (DB readonly)
                    │                                              │
                    │  1. load feature matrix (PyArrow)             │  2. SELECT fukusho_hit_validated,
                    ▼                                              │     is_model_eligible, race_date
              ┌─────────────┐    3. PK join (7-col)                │
              │ feature_df  │◄──────────────────────────────────────┘
              └─────┬───────┘
                    │  4. filter is_model_eligible=TRUE
                    │  5. drop raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2)
                    │  6. cast categorical string → category dtype (LightGBM) / declare cat_features (CatBoost)
                    ▼
              ┌─────────────────────────────────────────┐
              │ 7. 3way race_id-grouped time split      │
              │   race_id_time_series_split (expanding) │
              │   train 2016-07..2023 / calib 2024-H1   │
              │   / test 2024-H2 (2025+ = holdout)      │
              └──┬────────────────┬─────────────────┬───┘
                 │ train          │ calib           │ test
                 ▼                ▼                 ▼
          ┌──────────┐     ┌──────────┐      ┌──────────┐
          │ LightGBM │     │ fit_     │      │ BL-1..5  │
          │ .fit()   │     │ prefit_  │      │ compute  │
          │ CatBoost │     │ calibrator│      │ (odds/   │
          │ .fit()   │     │ (isotonic│      │ ninki)   │
          │ (has_time│     │  >1000)  │      │          │
          │  =True)  │     │          │      │          │
          └────┬─────┘     └────┬─────┘      └────┬─────┘
               │                │                  │
               └──► calibrated ◄┘                  │
                    estimator                      │
                       │                           │
               8. predict_proba → p_fukusho_hit    │
                       │                           │
                       ▼                           ▼
              ┌────────────────────────────────────────┐
              │ 9. evaluation: Brier/LogLoss/          │
              │    Calibration/sum(p)/BL comparison    │
              │    → reports/04-eval.md (JSON+MD)      │
              └────────────────┬───────────────────────┘
                               │
              ┌────────────────▼───────────────┐
              │ 10. staging-swap idempotent    │
              │    load → prediction.p_fukusho │
              │    (_prediction テーブル)       │
              │    provenance: model_type/     │
              │    model_version/              │
              │    feature_snapshot_id/        │
              │    as_of_datetime/calib_method │
              └────────────────────────────────┘
                               │
              CONSUMED BY: Phase 5 (EV/backtest)
                           Phase 6 (eval gates)
                           Phase 7 (Streamlit SQL)
                           Phase 8 (adversarial audit)
```

### Recommended Project Structure
```
src/
├── model/                      # §17.2 は models/ だが src/features/ 単数形慣行（planner 選択）
│   ├── __init__.py
│   ├── data.py                 # load_feature_matrix / join_labels / filter_eligible / drop_raw_ids / prepare_model_matrix
│   ├── trainer.py              # train_lightgbm / train_catboost（has_time=True・cat_features・固定 seed）
│   ├── calibrator.py           # SC#4 wrapper・fit_prefit_calibrator 呼出・isotonic/sigmoid 切替
│   ├── baseline.py             # BL-1..5 compute（頭数別一定/人気/odds-inverse/logreg/min-lgb）
│   ├── evaluator.py            # Brier/LogLoss/Calibration Curve/sum(p)/BL 比較表生成
│   ├── artifact.py             # ネイティブ形式 save/load（LightGBM .txt・CatBoost .cbm・sklearn joblib）
│   └── predict.py              # predict_p_fukusho（calibrated estimator → provenance 付き DataFrame）
├── db/
│   ├── schema.py               # 既存 + PREDICTION_TABLE_DDL 追加 + GRANT_ETL_SQL 拡張
│   └── prediction_load.py      # staging-swap idempotent load（_idempotent_load パターン再利用）
└── ...（既存 config/db/etl/features/utils 変更なし）
scripts/
└── run_train_predict.py        # Phase 4 エントリポイント（学習→キャリブレーション→予測→書込→評価）
tests/
├── model/                      # 新設
│   ├── test_data.py            # SC#1 stamped Parquet のみ・raw ID drop・allowlist
│   ├── test_trainer.py         # SC#3 leak diagnostic・has_time・cat_features
│   ├── test_calibrator.py      # SC#4 strict-later disjoint・reproduce smoke
│   ├── test_baseline.py        # BL-1..5 厳密定義・市場データ源
│   ├── test_predict.py         # provenance 列・model_version 採番
│   └── test_prediction_load.py # staging-swap idempotent・2回実行同一 checksum
└── ...
models/                         # .gitignore 対象・§19.1 再現性は code+lock+snapshot
└── {model_version}/
    ├── lgb_model.txt           # LightGBM booster.save_model
    ├── cb_model.cbm            # CatBoost save_model
    ├── calibrator.joblib       # sklearn CalibratedClassifierCV
    └── metadata.json           # model_version/feature_snapshot_id/hyperparams/seed/train_calib_test_periods
```

### Pattern 1: stamped Parquet のみ学習（SC#1）
**What:** feature matrix は `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` のみから読込。live DB から feature を再計算しない。
**When to use:** 常に（SC#1 不変）。
**Example:**
```python
# Source: src/model/data.py（新設・src/features/snapshot.py の読込パターン踏襲）
import pyarrow.parquet as pq
import pandas as pd

SNAPSHOT_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.parquet"
CATEGORY_MAP_PATH = "snapshots/category_map_20260620-1a-postreview-v2.json"

def load_feature_matrix() -> pd.DataFrame:
    """SC#1: stamped Parquet のみ読込（live DB 非使用）。"""
    df = pq.read_table(SNAPSHOT_PATH).to_pandas()
    df["race_date"] = pd.to_datetime(df["race_date"])
    return df
```

### Pattern 2: 3way race_id-grouped 時系列分割
**What:** train→calib→test を race_id 単位・strict chronological で分割。calib は train より厳格に未来。
**When to use:** 常に（SC#4・`race_id_time_series_split` + `fit_prefit_calibrator`）。
**Example:**
```python
# Source: src/model/data.py・race_id_time_series_split (src/utils/group_split.py) 活用
# 推奨案: train 2016-07..2023 / calib 2024-H1 / test 2024-H2 / 2025+ = Phase 5 BT 温存
def split_3way(df: pd.DataFrame) -> dict:
    """race_id 単位・strict chronological 3way 分離。"""
    df = df.sort_values(["race_start_datetime", "race_id" if "race_id" in df.columns else "race_nkey"])
    return {
        "train": df[df["race_date"].between("2016-07-01", "2023-12-31")],
        "calib": df[df["race_date"].between("2024-01-01", "2024-06-30")],
        "test":  df[df["race_date"].between("2024-07-01", "2024-12-31")],
        # 2025+ は Phase 5 BT 用に温存（学習/評価に使わない）
    }
```

### Pattern 3: LightGBM native categorical + CatBoost has_time
**What:** categorical string 列は LightGBM `category` dtype・CatBoost `cat_features` + `has_time=True`。target encoding 禁止。
**When to use:** 常に（§14.3/§14.4・SC#3）。
**Example:**
```python
# Source: CLAUDE.md §14.3/§14.4 + src/utils/category_map.py + src/features/category_map_consumer.py
import lightgbm as lgb
from catboost import CatBoostClassifier, Pool
from src.features.category_map_consumer import load_category_maps

# (1) 高基数 ID 5列は既に _code int32 化済み（frozen category map・非負）
#     load_category_maps("snapshots/category_map_20260620-1a-postreview-v2.json") で参照のみ（再 fit 禁止）

# (2) 低基数 string 列: LightGBM は category dtype へ cast
LIGHTGBM_CAT_COLS = ["sexcd", "class_code_normalized", "estimated_running_style",
                     "rolling_jyocd_mode_5", "rolling_jyocd_latest_5"]
def prepare_for_lightgbm(df):
    for c in LIGHTGBM_CAT_COLS:
        df[c] = df[c].fillna("__MISSING__").astype("category")
    return df

# LightGBM は categorical_feature='auto' で pandas category を自動抽出
model = lgb.LGBMClassifier(
    objective="binary", random_state=42, deterministic=True,
    # ... 初期ハイパラ（下記 D-09 確定事項）
)
model.fit(X_train, y_train, categorical_feature=LIGHTGBM_CAT_COLS)

# (3) CatBoost: cat_features 宣言 + has_time=True・Pool は race_start_datetime sort 済み前提
CATBOOST_CAT_COLS = LIGHTGBM_CAT_COLS  # 同一（_code 列は int32 なので cat_features に含めない）
train_pool = Pool(X_train_sorted, y_train_sorted, cat_features=CATBOOST_CAT_COLS)
model = CatBoostClassifier(
    has_time=True,  # random permutation 無効化・入力順序を使用（ordered TS が過去行のみ使用）
    random_seed=42,
    # ... 初期ハイパラ
)
model.fit(train_pool)
```

### Pattern 4: FrozenEstimator prefit キャリブレーション
**What:** sklearn 1.9 で `cv='prefit'` は削除。`FrozenEstimator` でラップして `CalibratedClassifierCV` へ。
**When to use:** 常に（SC#4・`src/utils/calibrator.py::fit_prefit_calibrator` が実装済み）。
**Example:**
```python
# Source: src/utils/calibrator.py（既存・そのまま再利用）
from src.utils.calibrator import fit_prefit_calibrator

# calib sample > 1000 → isotonic / < 1000 → sigmoid（CLAUDE.md §15.2）
calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"
calibrated = fit_prefit_calibrator(
    base_estimator=fitted_lgb,  # train slice で .fit() 済み
    X_calib=X_calib, y_calib=y_calib,
    race_dates_calib=calib_df["race_date"],
    train_max_date=train_df["race_date"].max(),  # strict-later guard (ValueError)
    method=calib_method,
)
```

### Pattern 5: staging-swap idempotent 予測書込
**What:** `prediction` スキーマのテーブルを atomic に替換。2回実行で同一 checksum。
**When to use:** 予測永続化時（D-05・`src/etl/fukusho_label.py::_idempotent_load_label` パターン再利用）。
**Example:**
```python
# Source: src/etl/fukusho_label.py の _idempotent_load_label パターン・prediction 用に改変
# advisory lock → CREATE staging (LIKE ... INCLUDING ALL) → TRUNCATE → INSERT → DROP/RENAME swap → GRANT
```

### Anti-Patterns to Avoid
- **target/mean encoding の混入（§14.3/§14.4 違反）:** OOF target encoding も時系列 panel で漏洩。LightGBM native categorical と CatBoost ordered TS のみ使用。
- **CatBoost `has_time=True` 忘れ:** random permutation が走り未来行がカテゴリ符号化に混入（silent leak）。Pool は `race_start_datetime` で sort 済み前提。
- **`cv='prefit'` 使用:** sklearn 1.9 で削除・`InvalidParameterError`。FrozenEstimator を使う。
- **raw ID 原列（kisyucode 等）をモデル入力に混入:** これらは audit trail で保持されるが、モデル入力からは必ず除外。`_RAW_ID_KEPT_COLUMNS` で明示。
- **live DB から feature 再計算:** SC#1 違反。stamped Parquet のみ。
- **calib slice が train と重複または過去:** `fit_prefit_calibrator` が ValueError で防止済みだが、呼出側で正しい分割を保証。
- **LightGBM で NaN を含む category 列をそのまま渡す:** pandas が NaN→code -1 にするハザード。`__MISSING__` sentinel で fillna してから category 化。
- **early stopping eval set に calib/test を使用:** 未来情報が calib/test に漏れる。学習窓内の時系列末尾から切る（D-04 確定事項）。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| race_id-grouped 時系列 CV | custom splitter | `race_id_time_series_split` (src/utils/group_split.py) | race_id disjoint + strict chronological + 3 guard が実装済み |
| 時系列安全キャリブレーション | manual isotonic fit | `fit_prefit_calibrator` (src/utils/calibrator.py) | FrozenEstimator prefit・strict-later ValueError guard 実装済み |
| 高基数 ID カテゴリ符号化 | custom target encoding | `load_category_maps` + `_code` int32 列（既存） | frozen map・非負保証・`__UNSEEN__`/`__MISSING__` sentinel・NaN→-1 ハザード回避済み |
| feature allowlist 検査 | manual column filter | `assert_matrix_columns_registered` (src/features/availability.py) | odds 系・banned source の混入を構造防止 |
| staging-swap idempotent 書込 | manual INSERT/DELETE | `_idempotent_load` パターン (src/etl/fukusho_label.py) | advisory lock・INCLUDING ALL・rowcount verify・atomic swap・GRANT 再発行 |
| byte-reproducible Parquet | manual to_parquet | `write_snapshot` (src/features/snapshot.py) | 決定論的書込・SHA256・§12.4 metadata（モデル artifact 参考だが予測 Parquet は不要・prediction テーブルへ） |
| sum(p) 理論値チェック | manual threshold | 実装（`evaluator.py`） | §15.2 の 8頭以上 2.7-3.3 / 5-7頭 1.8-2.2 を機械検査 |

**Key insight:** Phase 1-3 が構築したリーク防止プリミティブ（calibrator/group_split/category_map/availability）は Phase 4 が本格消費する最初のフェーズ。これらを再実装せず、既存契約に従って呼び出すことが再現性とリーク防止の両立の鍵。

## Runtime State Inventory

> Phase 4 は rename/refactor/migration フェーズではないが、`prediction` スキーマへの新規テーブル追加と model artifact 永続化を伴うため、関連する runtime state を確認。

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `prediction` スキーマは空（CREATE SCHEMA のみ・テーブル定義なし）[VERIFIED: src/db/schema.py] | 新規 `_prediction` テーブル DDL 追加（D-12 確定事項） |
| Live service config | なし（ローカル単一ユーザー・Streamlit は Phase 7） | なし |
| OS-registered state | なし | なし |
| Secrets/env vars | `KEIBA_DB_*` DSN 既存・ETL ロール GRANT 拡張が必要（prediction スキーマ USAGE+CREATE）[VERIFIED: src/db/schema.py GRANT_ETL_SQL] | `run_apply_schema.py` 再実行で GRANT 拡張（idempotent） |
| Build artifacts | `models/` ディレクトリ未作成・`.gitignore` に `models/` エントリ要確認 | `models/` 作成 + `.gitignore` 確認・`snapshots/` は既存 |

**Nothing found in category:** live service config / OS-registered state は None（ローカル単一ユーザー環境・実DB は既存）。

## 入力 snapshot の確定 feature 仕様（D-01/D-02 最終確定）

> 実データ `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` の 62 物理カラムを分類。モデル入力 feature は 42（35 numeric + 2 categorical string + 5 `_code` int32）。raw ID 原列 4列は**除外**。

### meta/key 列（16・feature ではない・モデル入力外）
`year`, `jyocd`, `kaiji`, `nichiji`, `racenum`, `umaban`, `kettonum`, `race_nkey`, `race_date`, `race_start_datetime`, `as_of_datetime`, `feature_cutoff_datetime`, `feature_snapshot_id`, `feature_availability_version`, `label_generation_version`, `prediction_timing`

### raw ID 原列（4・**モデル入力から除外**・HIGH #5 COPY-NOT-RENAME で保持）
`kisyucode` (jockey_id 原列), `chokyosicode` (trainer_id 原列), `ketto3infohansyokunum1` (sire_id 原列), `ketto3infohansyokunum2` (bms_id 原列)

### 高基数 ID `_code` 列（5・frozen category map・非負 int32・categorical 扱い）
`jockey_id_code` (train unique=359), `trainer_id_code` (400), `sire_id_code` (862), `bms_id_code` (15,289), `horse_id_code` (42,512)

### 低基数 categorical string 列（5・LightGBM category dtype + CatBoost cat_features）
| Column | nunique | nulls | 扱い |
|--------|---------|-------|------|
| `sexcd` | 3 | 0 | categorical（1牝/2牡/3セン） |
| `class_code_normalized` | 7 | 1,294 | categorical（005/010/016/701/703/999/...）・欠損は `__MISSING__` sentinel |
| `estimated_running_style` | 5 | 0 | categorical（逃/先/差/追/`__MISSING__`） |
| `rolling_jyocd_mode_5` | 11 | 60,650 | categorical（JRA 競馬場コード・CR-02 で mode 集計） |
| `rolling_jyocd_latest_5` | 11 | 60,650 | categorical（同上・latest） |

### numeric feature 列（35・Float64/Int64/double）
| Group | Columns |
|-------|---------|
| static (4) | `wakuban`, `barei`, `futan`, `umaban`(*) |
| rolling 8系統 (32 = 8 × mean/latest/sd/count) | `rolling_{kakuteijyuni,harontimel3,jyuni3c_jyuni4c,kyori,days_since_prev,timediff,babacd}_{mean,latest,sd,count}_5` + `rolling_jyocd_count_5` |

(*) `umaban` は meta/key にも分類されるが、§13.5「馬番」feature としても扱う。planner が両分類の整合を確認（feature group `post_position`・`available_from_timing: post_position_confirmed`）。

### 確認事項
- **`trackcd`/`course_kubun`/`kyori` は Parquet 物理カラムに存在しない** [VERIFIED: 実データ] — registry には宣言されるが、builder が `babacd` 派生（trackcd 第1桁分岐）の中間処理で使用し、最終出力から drop。Phase 4 は Parquet 物理カラム（62列）を正とする。
- **rolling の `count_5` 列（8個）は feature として含まれる** [VERIFIED: 実データ] — 過去5走の実走数（初出走で 0）。history 不足の信号。
- **`rolling_jyocd_sd_5` は postreview-v2 に存在しない** [VERIFIED: 実データ] — CR-02 で削除（カテゴリカル値の sd は無意味）。

## Common Pitfalls

### Pitfall 1: sklearn 1.9 で `cv='prefit'` が削除
**What goes wrong:** `CalibratedClassifierCV(base_estimator, cv='prefit')` が `InvalidParameterError`。
**Why it happens:** sklearn 1.6+ で `cv='prefit'` 文字列オプションが削除。CLAUDE.md/01-RESEARCH は旧 API を前提としていた。
**How to avoid:** `sklearn.frozen.FrozenEstimator` で訓練済み推定器をラップして `CalibratedClassifierCV(estimator=frozen, method=...)` へ。`src/utils/calibrator.py::fit_prefit_calibrator` が実装済み。
**Warning signs:** `InvalidParameterError: cv='prefit'`。

### Pitfall 2: CatBoost `has_time=True` 忘れによる silent leak
**What goes wrong:** CatBoost が random permutation（通常3回）で ordered TS を計算。未来行が過去行のカテゴリ符号化に混入。
**Why it happens:** `has_time` はデフォルト False。時系列データで明示しないと未来情報リーク。
**How to avoid:** 常に `has_time=True` + Pool は `race_start_datetime`（tie-break `race_id`）で sort 済み前提。`fit()` に渡す前に sort。
**Warning signs:** 公式 doc [CITED: catboost.ai/docs/en/references/training-parameters/common]・GitHub issue #1076 [CITED: github.com/catboost/catboost/issues/1076]。

### Pitfall 3: LightGBM pandas category の NaN→code -1 ハザード
**What goes wrong:** pandas `category` dtype が NaN を code -1 にする。LightGBM C++ は非負 int32 を期待。
**Why it happens:** pandas `.cat.codes` の仕様。LightGBM は一部バージョンで -1 を missing 扱いするが、決定論的でない。
**How to avoid:** `__MISSING__`/`__UNSEEN__` sentinel で fillna してから category 化。高基数 ID は `category_map.py` が非負 int32 を保証済み。低基数 string 列は手動で `fillna("__MISSING__")`。
**Warning signs:** [CITED: lightgbm.readthedocs.io/en/latest/Advanced-Topics.html]・CLAUDE.md §14.3。

### Pitfall 4: raw ID 原列のモデル入力混入
**What goes wrong:** `kisyucode`/`chokyosicode` 等の raw ID 原列が Parquet に残存（HIGH #5 COPY-NOT-RENAME）。これをモデル入力に混入すると LightGBM が文字列で refit し test 構成リーク経路が開く。
**Why it happens:** HIGH #5 は raw 原列を意図的に保持（audit trail）。モデル入力準備で除外し忘れる。
**How to avoid:** `prepare_model_matrix()` で `_RAW_ID_KEPT_COLUMNS`（kisyucode/chokyosicode/ketto3infohansyokukunum1/2）を明示的に drop。unit test で「モデル入力に raw ID 原列が含まれない」ことを assert。
**Warning signs:** モデル入力カラムリストに `kisyucode` 等が含まれる。

### Pitfall 5: early stopping eval set から calib/test への漏洩
**What goes wrong:** LightGBM/CatBoost の early stopping eval set に calib/test を渡すと、学習プロセスが calib/test の情報を覗く。
**Why it happens:** early_stopping_rounds と eval_set を設定する際、学習窓内の末尾から切るのを忘れる。
**How to avoid:** eval set は train slice の時系列末尾（例: train 2016-07..2023 の末尾 2023年）から切り出し、calib/test とは完全に分離。unit test で `set(eval_races).isdisjoint(set(calib_races))` を assert。
**Warning signs:** eval set の race_id と calib/test の race_id が重複。

### Pitfall 6: BL-3 オッズ逆数の正規化忘れ
**What goes wrong:** 生の複勝オッズ逆数（1/odds）を確率として LogLoss 比較すると、`sum(p)` が理論値（払戻対象数）と一致せず §15.2 受入基準が歪む。
**Why it happens:** オッズ逆数はマージン（控除率）込みで sum ≠ 払戻対象数。
**How to avoid:** レース内正規化で `sum(p) = 払戻対象数`（8頭以上 3 / 5-7頭 2）に揃える（D-07 確定事項）。
**Warning signs:** BL-3 の `sum(p)` が 2.7-3.3 / 1.8-2.2 を外れる。

## Code Examples

### LightGBM 学習（native categorical・固定 seed）
```python
# Source: CLAUDE.md §14.3 + lightgbm.readthedocs.io/en/latest/Advanced-Topics.html
import lightgbm as lgb

# 初期ハイパラ（D-09 確定事項・manual・MLflow/Optuna は defer）
params = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,            # 過学習防止のため 2^max_depth より少なめ
    "min_data_in_leaf": 100,     # 時系列 panel で安定化
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 42,
    "deterministic": True,       # bit-identical 再現性
    "force_col_wise": True,      # 決定論的
}
# categorical_feature で明示（pandas category dtype でも明示が安全）
model = lgb.LGBMClassifier(n_estimators=1000, **params)
model.fit(
    X_train, y_train,
    categorical_feature=LIGHTGBM_CAT_COLS,  # sexcd/class_code_normalized/estimated_running_style/rolling_jyocd_*
    eval_set=[(X_train_tail, y_train_tail)],  # 学習窓内末尾（calib/test と分離）
    eval_metric="binary_logloss",
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
)
```

### CatBoost 学習（has_time=True・cat_features）
```python
# Source: catboost.ai/docs/en/references/training-parameters/common + CLAUDE.md §14.4
from catboost import CatBoostClassifier, Pool

# Pool は race_start_datetime で sort 済み前提（has_time=True が入力順序を使用）
train_pool = Pool(
    X_train_sorted, y_train_sorted,
    cat_features=CATBOOST_CAT_COLS,  # sexcd/class_code_normalized/estimated_running_style/rolling_jyocd_*
)
model = CatBoostClassifier(
    iterations=1000,
    learning_rate=0.05,
    depth=6,                     # CatBoost は対称木・LightGBM より浅めが標準
    l2_leaf_reg=3.0,
    has_time=True,               # random permutation 無効化・ordered TS が過去行のみ使用
    random_seed=42,
    eval_metric="Logloss",
    early_stopping_rounds=50,
)
model.fit(train_pool, eval_set=train_tail_pool)  # 学習窓内末尾
```

### SC#3 Leak Diagnostic（対抗的テスト）
```python
# Source: 本研究設計・SC#3「rare category が自身の label に一致せず平均に縮む」検証
def test_no_target_encoding_leak():
    """希少カテゴリ合成テスト: target encoding が混入していれば、
    希少カテゴリの予測が自身の label に過剰適合する。native categorical なら平均に縮む。"""
    # 1. 合成データ: 希少カテゴリ 'RARE_X' を持つ行の label を全て 1 に設定
    #    （残りは現実的な positive rate 0.21 程度）
    # 2. train/test 分離（race_id 単位）
    # 3. LightGBM/CatBoost を学習
    # 4. test の 'RARE_X' 行の予測確率を確認:
    #    - target encoding 混入 → 1.0 に近い（自身の label に適合）
    #    - native categorical → global mean 0.21 程度に縮む（期待動作）
    # assert: pred < 0.5  # mean に縮むことを確認（target encoding なら 1.0 近く）
```

### SC#4 Reproduce Smoke Test
```python
# Source: 本研究設計・固定 seed で bit-identical 再現性検証
def test_reproduce_bit_identical():
    """固定 seed で2回学習→予測し、predictions が bit-identical になることを検証。"""
    pred1 = train_and_predict(seed=42)
    pred2 = train_and_predict(seed=42)
    # hash 比較 or np.array_equal
    assert np.array_equal(pred1, pred2), "固定 seed でも predictions が一致しない（非決定論的要素あり）"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CalibratedClassifierCV(cv='prefit')` | `CalibratedClassifierCV(estimator=FrozenEstimator(...))` | sklearn 1.6+ (1.9 で完全削除) | Phase 4 は FrozenEstimator idiom 使用・`src/utils/calibrator.py` 実装済み |
| LightGBM categorical（手動 label encoding） | native categorical（pandas `category` dtype・Fisher 最適分割） | LightGBM 2.0+ | target encoding 不要・リークセーフ |
| CatBoost random permutation TS | ordered TS + `has_time=True` | CatBoost 0.x から安定 | 時系列データで未来情報リークを構造防止 |
| `pandas.merge_asof` 手動 PIT join | `direction='backward'` + sort 前提 | pandas 1.0+ 安定 | Phase 3 が実装済み・Phase 4 は snapshot 消費のみ |

**Deprecated/outdated:**
- `cv='prefit'` 文字列: sklearn 1.9 で削除・FrozenEstimator に移行
- target/mean encoding: 時系列 panel で漏洩・LightGBM/CatBoost native で不要
- LightGBM/CatBoost の手動 one-hot: 高基数 ID で次元爆発・native categorical が 8x 高速

## 研究者確定事項（Claude's Discretion 12項目・全て git/実データ/実コード裏取り）

### D-02: feature 63→62 の正体【確定】
`rolling_jyocd_mean_5` → `rolling_jyocd_mode_5` (rename) + `rolling_jyocd_sd_5` (remove) = ネット -1。
理由: jyocd はカテゴリカル値で数値 mean/sd は無意味（commit 43bd81f CR-02）。§13.4 odds-free allowlist 違反なし。上記「D-02 確定事項」セクション参照。

### D-02b: train→calib→test の 3way 時系列分割設計【確定】
**推奨案: train 2016-07-01..2023-12-31 / calib 2024-01-01..2024-06-30 / test 2024-07-01..2024-12-31**
- 2025-01-01 以降 (70,211行 / 5,040レース) は **Phase 5 BT 温存**（Phase 3 D-09・学習/評価に使わない）
- **calib sample = 24,884行 > 1000 → `isotonic` 使用可**（CLAUDE.md §15.2）
- calib < 1000 件時の sigmoid 切替閾値: **1000件未満で sigmoid**（sklearn 公式推奨・過学習防止）
- 実測 positive rate: train 0.2146 / calib 0.2159 / test 0.2207（安定・21.4-22.1%）
- 代替案（train 2016-2022 / calib 2023 / test 2024）も検討したが、test 2024 全体を評価に使うと Phase 5 BT（BT-2: test 2024）と重複するため、**test を 2024-H2 に絞り 2024-H1 を calib に充当** することで Phase 5 との重複を回避。
- `race_id_time_series_split`（expanding window・gap なし）を前提。1-2週間 gap はオプション（CLAUDE.md）だが、本推奨案は暦年境界で自然な gap が生じるため追加 gap 不要。

### D-03: 低基数コードの categorical vs numeric 扱い【確定】
**categorical 扱い（LightGBM category dtype + CatBoost cat_features）:**
- `sexcd` (3値: 1牝/2牡/3セン)
- `class_code_normalized` (7値: 005/010/016/701/703/999/...・序数性あるが LightGBM native が Fisher 分割で処理)
- `estimated_running_style` (5値: 逃/先/差/追/`__MISSING__`)
- `rolling_jyocd_mode_5` (11値)
- `rolling_jyocd_latest_5` (11値)

**categorical 扱い（高基数 ID・既に `_code` int32 化済み・非負保証）:**
- `jockey_id_code`, `trainer_id_code`, `sire_id_code`, `bms_id_code`, `horse_id_code`
- これらは LightGBM では int32 だが `categorical_feature` で明示的に categorical 指定（native categorical が Fisher 分割を適用）。CatBoost では `cat_features` に**含めない**（int32 は数値扱い・CatBoost は int cat を自動処理しない場合は cat_features 宣言要・planner が要検証）。

**numeric 扱い:**
- `wakuban`, `umaban`, `barei`, `futan`（連続/序数・numeric が自然）
- rolling の mean/latest/sd/count（連続値）

**根拠:** §14.3「連番カテゴリIDで管理・負値 code 使わない」・§14.4「cat_features を明示」。実データ cardinality で low-cardinality string 列を特定 [VERIFIED: 実データ]。

### D-04: early stopping eval set のリーク防止【確定】
**設計: eval set は train slice の時系列末尾から切り出し、calib/test とは完全に分離。**
- train 2016-07..2023 の場合、eval set は train 内の末尾（例: 2023年 Q3-Q4 または train 全体から race_id 単位で 80/20 時系列分割した末尾 20%）。
- **unit test 方針:** `set(eval_races).isdisjoint(set(calib_races))` と `set(eval_races).isdisjoint(set(test_races))` を assert。違反で ValueError。
- LightGBM: `eval_set=[(X_train_tail, y_train_tail)]`。CatBoost: `eval_set=train_tail_pool`。
- eval set の race_id は train に属するが、early_stopping の feedback loop が calib/test に触れないことを保証。

### D-05: SC#3 leak diagnostic の設計【確定】
**手順:**
1. 合成 DataFrame を作成: 希少カテゴリ `'RARE_X'` を持つ行の `fukusho_hit_validated` を全て `1` に設定。残りは現実的な positive rate（0.21 程度）。
2. train/test を race_id 単位・時系列順で分割（`race_id_time_series_split`）。
3. LightGBM（native categorical）と CatBoost（`has_time=True` + `cat_features`）を学習。
4. test の `'RARE_X'` 行の予測確率を確認:
   - **target encoding 混入の場合** → 予測が 1.0 に近い（自身の label に過剰適合・予測シフト）
   - **native categorical の場合** → 予測が global mean（0.21 程度）に縮む（期待動作・Fisher 分割は target を使わない）
5. assert: `pred_RARE_X < 0.5`（mean に縮むことを確認・target encoding なら 1.0 近く）。

**target encoding 非混入の実証:** この対抗的テストが GREEN なら、カテゴリ処理経路に target encoding が混入していないことを構造的に実証。

### D-06: SC#4 reproduce smoke test の設計【確定】
**手順:**
1. 固定 seed（`random_state=42`/`seed=42`/`random_seed=42`）で学習→キャリブレーション→予測を2回実行。
2. 2回の predictions（`p_fukusho_hit` 配列）を比較:
   - **比較方法:** `np.array_equal(pred1, pred2)` または hash 比較（`hashlib.sha256(pred.tobytes()).hexdigest()`）。
   - test race set の予測値が bit-identical であることを確認。
3. 違反時: 非決定論的要素（thread randomness・GPU・未固定 seed）が残っている。

**固定 seed パラメータ全箇所リスト:**
- LightGBM: `seed=42`, `deterministic=True`, `force_col_wise=True`, `bagging_seed=42`, `feature_fraction_seed=42`
- CatBoost: `random_seed=42`, `has_time=True`（permutation 無効化で決定論的）
- sklearn CalibratedClassifierCV: 内部で random_state を使用しない（isotonic/sigmoid は決定論的）が、`FrozenEstimator` で base が固定済み
- pandas/numpy: sort は stable・`np.random.seed(42)` は不要（モデル側で固定）

### D-07: BL-3 レース内正規化【確定】
**推奨: 複勝オッズ逆数をレース内正規化して `sum(p) = 払戻対象数` に揃える。**
- 手順: レース内で `1/fukuoddslow` を計算 → レース内で `sum = 払戻対象数`（8頭以上 3 / 5-7頭 2）になるよう正規化（`p_i = (1/odds_i) / sum(1/odds) × 払戻対象数`）。
- §15.2 `sum(p)` 適合チェックとの整合: BL-3 の sum(p) が 2.7-3.3 / 1.8-2.2 に一致（正規化で厳密に 3 / 2 になるので受入基準内）。
- 市場暗示確率として標準的な方式（マージン/控除率を除去した正規化）。
- **生の逆数で LogLoss 比較しない**（sum ≠ 払戻対象数 で §15.2 が歪む）。

### D-08: BL-1..5 各ベースラインの厳密定義と実装方式【確定】

| BL | 定義 | p_fukusho_hit 算出式 | 必要な source 列 |
|----|------|---------------------|------------------|
| BL-1 | 頭数別一定確率 | 8頭以上: `3 / sales_start_entry_count`<br>5-7頭: `2 / sales_start_entry_count` | `label.fukusho_label.sales_start_entry_count`・`fukusho_payout_places`（参考値・実計算は sales_start_entry_count） |
| BL-2 | 確定人気由来 | 人気順位を確率に変換（例: 正規化 `1/ninki` をレース内正規化して sum=払戻対象数、または人気帯別の経験的確率） | `n_uma_race.ninki`（確定人気・実DB確認済） |
| BL-3 | 確定複勝オッズ逆数 | `1/fukuoddslow` をレース内正規化（sum=払戻対象数） | `n_odds_tanpuku.fukuoddslow`/`fukuoddshigh`（実DB確認済・2024年 NULL 0件） |
| BL-4 | ロジスティック回帰 | sklearn `LogisticRegression` で少数基本特徴量（例: barei/futan/umaban/wakuban/class_code_normalized）を学習 → `predict_proba` | feature matrix の部分集合 |
| BL-5 | LightGBM 最小特徴量 | 過去走特徴量なし・レース条件+馬情報中心（例: static 4 + class_code + estimated_running_style で LightGBM 学習）→ `predict_proba` → キャリブレーション | feature matrix の部分集合（rolling 系統を除外） |

**比較方法（SC#2 比較表）:**
- 全 BL と主モデル（LightGBM/CatBoost キャリブレーション済み）を同一 test slice（2024-H2）で評価。
- 指標: Brier Score / LogLoss / Calibration Curve / `sum(p)` 分布 / （参考）AUC。
- BL-3 は §14.2「Phase 1-A モデルと同一情報条件の比較ではない」旨を比較表に明記。
- AI モデルが BL-1（頭数別一定）・BL-4（logreg）を上回るか（付加価値）と、BL-3（市場参照）とどの程度乖離するか（EV 判定に使えるか）を回答。

### D-09: ハイパラ初期値【確定】（manual・MLflow/Optuna は §21 defer）

**LightGBM 4.6.0 初期値:**
```python
params = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,             # 2^6-1・過学習防止
    "min_data_in_leaf": 100,      # 時系列 panel で安定化
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 42,
    "deterministic": True,
    "force_col_wise": True,
    "n_estimators": 1000,         # early_stopping で削減
    "early_stopping_rounds": 50,
}
```

**CatBoost 1.2.10 初期値:**
```python
params = {
    "iterations": 1000,
    "learning_rate": 0.05,
    "depth": 6,                   # 対称木・LightGBM より浅め
    "l2_leaf_reg": 3.0,
    "has_time": True,             # 必須・random permutation 無効化
    "random_seed": 42,
    "eval_metric": "Logloss",
    "early_stopping_rounds": 50,
    "verbose": 100,
}
```

**根拠:** LightGBM/CatBoost 公式推奨の binary 分類初期値・過学習防止（min_data_in_leaf/l2/num_leaves）。手動調整前提・Phase 6 評価後に Optuna 導入を再評価。

### D-10: model_version 採番方式【確定】
**形式: `{feature_snapshot_id}-{model_type_short}-v{N}`**
- LightGBM: `20260620-1a-lgb-v1`
- CatBoost: `20260620-1a-cb-v1`
- `feature_snapshot_id` と整合・`model_type` 列で `lightgbm`/`catboost` を区別。
- v{N} はハイパラ/feature 変更時に bump（手動・semver 的）。
- `models/{model_version}/` 配下に artifact（lgb_model.txt/cb_model.cbm/calibrator.joblib/metadata.json）。

### D-11: pyproject.toml への lightgbm/catboost pin 追加【確定】
**手順:**
```bash
# CLAUDE.md 指示版（LightGBM 4.6.0・CatBoost 1.2.10）を pin
uv add "lightgbm==4.6.0" "catboost==1.2.10"
# → pyproject.toml [project].dependencies に追加
# → uv.lock 更新（byte-reproducible）
uv sync --frozen
```
**整合確認:**
- sklearn 1.9.0（既 pin）・LightGBM 4.6.0（requires_python >=3.7・3.12 OK）・CatBoost 1.2.10（binary wheels 3.9-3.13）で互換性問題なし [VERIFIED: PyPI]
- `requires-python = ">=3.12,<3.13"` は維持（CLAUDE.md）
- mlxtend 0.25.0 は sklearn>=1.0 依存・LightGBM/CatBoost と競合しない

### D-12: prediction テーブル DDL【確定】
**テーブル名: `prediction.fukusho_prediction`**（`prediction` スキーマ・`label.fukusho_label` 命名パターン踏襲）

```sql
CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction (
    -- provenance（§19.1 再現性）
    model_type varchar(16) NOT NULL,       -- 'lightgbm' / 'catboost'
    model_version varchar(64) NOT NULL,    -- '20260620-1a-lgb-v1' 等
    feature_snapshot_id varchar(64) NOT NULL,  -- '20260620-1a-postreview-v2'
    as_of_datetime timestamp NOT NULL,     -- 予測生成時点
    calib_method varchar(16) NOT NULL,     -- 'isotonic' / 'sigmoid' / 'none'
    -- PK（label.fukusho_label と同一・7カラム）
    year int,
    jyocd varchar(2),
    kaiji int,
    nichiji varchar(2),
    racenum int,
    umaban int,
    kettonum int,                          -- horse_id 原列
    -- 予測値
    p_fukusho_hit double precision NOT NULL,  -- [0.0, 1.0]
    -- 補助メタ（Phase 5/6/7 が参照）
    race_date date,
    split varchar(16),                     -- 'train'/'calib'/'test'/'holdout_2025_plus'
    PRIMARY KEY (model_type, model_version, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)
);
COMMENT ON TABLE prediction.fukusho_prediction IS
    'Phase 4 予測結果 (D-05). provenance 列で §19.1 再現性. staging-swap idempotent.';
```

**`src/db/schema.py` への追加:**
- `PREDICTION_TABLE_DDL` 定数を追加
- `GRANT_ETL_SQL` に `prediction` スキーマの `USAGE, CREATE` + 書込権限を追加（`label` と同パターン）
- `GRANT_READER_SQL` に `prediction` スキーマの `USAGE` + `SELECT` を追加（Phase 7 Streamlit が参照）
- `APPLY_ORDER` は既存（CREATE SCHEMA が先・prediction スキーマは既存）

**`src/db/prediction_load.py`（新設）:**
- `_idempotent_load_prediction()` 関数（`src/etl/fukusho_label.py::_idempotent_load_label` パターン再利用）
- advisory lock → CREATE staging (LIKE ... INCLUDING ALL) → TRUNCATE → executemany INSERT → rowcount verify (SELECT count) → DROP/RENAME swap → GRANT SELECT to reader

**ETL ロール GRANT 拡張（`src/db/schema.py::GRANT_ETL_SQL` に追加）:**
```sql
GRANT USAGE, CREATE ON SCHEMA prediction TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA prediction TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
```

## Validation Architecture

> `workflow.nyquist_validation: true`（config.json）・Phase 4 の全成功基準とリーク面について階層化検証計画を記述。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存・`tests/` 配下 24 ファイル） |
| Config file | `pyproject.toml [tool.pytest.ini_options]`（testpaths=["tests"]・markers `requires_db`） |
| Quick run command | `uv run pytest tests/model/ -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODL-01 / SC#1 | stamped Parquet のみ学習（live DB 非使用） | unit | `uv run pytest tests/model/test_data.py::test_load_from_parquet_only -x` | ❌ Wave 0 |
| MODL-01 / SC#1 | raw ID 原列除外 | unit | `uv run pytest tests/model/test_data.py::test_raw_ids_excluded -x` | ❌ Wave 0 |
| MODL-01 / SC#1 | feature allowlist 検査 | unit | `uv run pytest tests/model/test_data.py::test_no_banned_features -x` | ❌ Wave 0 |
| MODL-03 / SC#3 | LightGBM native categorical（非負 code） | unit | `uv run pytest tests/model/test_trainer.py::test_lightgbm_nonneg_codes -x` | ❌ Wave 0 |
| MODL-03 / SC#3 | CatBoost has_time=True | unit | `uv run pytest tests/model/test_trainer.py::test_catboost_has_time -x` | ❌ Wave 0 |
| MODL-03 / SC#3 | target encoding 非混入（leak diagnostic） | adversarial | `uv run pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x` | ❌ Wave 0 |
| SC#4 | strict-later disjoint (max(train)<min(calib)) | unit | `uv run pytest tests/model/test_calibrator.py::test_strict_later_disjoint -x` | ❌ Wave 0 |
| SC#4 | reproduce bit-identical | smoke | `uv run pytest tests/model/test_calibrator.py::test_reproduce_bit_identical -x` | ❌ Wave 0 |
| BACK-01 (前置) | race_id 分離 disjoint | unit | `uv run pytest tests/model/test_data.py::test_race_id_disjoint_3way -x` | ❌ Wave 0 |
| MODL-02 / SC#2 | BL-1..5 厳密定義 | unit | `uv run pytest tests/model/test_baseline.py -x` | ❌ Wave 0 |
| MODL-01 | prediction provenance 列 | unit | `uv run pytest tests/model/test_predict.py::test_provenance_columns -x` | ❌ Wave 0 |
| D-05 | staging-swap idempotent | integration | `uv run pytest tests/model/test_prediction_load.py -x` | ❌ Wave 0 |
| D-04 | early stopping eval set 分離 | unit | `uv run pytest tests/model/test_trainer.py::test_eval_set_disjoint_from_calib_test -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/model/ -x -q`（model 配下の quick subset）
- **Per wave merge:** `uv run pytest`（全 24+ 既存 + model/ 新設）
- **Phase gate:** Full suite green before `/gsd-verify-work`・SC#3/SC#4 対抗的テストが GREEN

### Wave 0 Gaps
- [ ] `tests/model/__init__.py` — package marker
- [ ] `tests/model/test_data.py` — SC#1（Parquet のみ/raw ID 除外/allowlist/race_id disjoint）
- [ ] `tests/model/test_trainer.py` — SC#3（leak diagnostic/has_time/nonneg codes/eval set 分離）
- [ ] `tests/model/test_calibrator.py` — SC#4（strict-later disjoint/reproduce smoke/isotonic<1000 sigmoid 切替）
- [ ] `tests/model/test_baseline.py` — BL-1..5 厳密定義・市場データ源
- [ ] `tests/model/test_predict.py` — provenance 列・model_version 採番
- [ ] `tests/model/test_prediction_load.py` — staging-swap idempotent（2回実行同一 checksum）
- [ ] Framework install: `uv add lightgbm==4.6.0 catboost==1.2.10`（D-11）

## Security Domain

> `security_enforcement: true`（config.json）・ASVS level 1。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | ローカル単一ユーザー・DB 認証は既存 DSN（Phase 1-3 変更なし） |
| V3 Session Management | no | 同上 |
| V4 Access Control | yes | DB ロール分離（readonly/ETL）・prediction スキーマ GRANT 拡張・raw read-only REVOKE 維持 |
| V5 Input Validation | yes | feature allowlist（`assert_matrix_columns_registered`）・provenance 列 NOT NULL・PK 制約 |
| V6 Cryptography | no | 暗号化不要（ローカル・モデル artifact は `.gitignore`） |
| V7 Error Handling | yes | fail-loud（ValueError/RuntimeError）・silent fallback 禁止（D-13 踏襲） |
| V8 Data Protection | yes | raw ID 原列は audit trail で保持するがモデル入力から除外・provenance で再現性 |
| V9 Logging | yes | 学習/予測ログ・checksum idempotent 検証 |

### Known Threat Patterns for ML Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Target encoding 漏洩（未来情報がカテゴリ符号化に混入） | Information Disclosure | LightGBM native categorical + CatBoost `has_time=True` ordered TS・SC#3 leak diagnostic で検証 |
| データリーク（train/test で同一 race_id が跨る） | Tampering | `race_id_time_series_split`・race_id disjoint ValueError guard |
| 後知恵オッズ時点選択 | Tampering | Phase 4 は odds-free feature のみ（BL-3 は独立ベンチマーク・モデル特徴量に混入しない） |
| 生 DB から feature 再計算（再現性崩壊） | Repudiation | SC#1 stamped Parquet のみ・allowlist 検査 |
| モデル artifact の pickle ACE | Tampering / Elevation | ネイティブ形式（LightGBM .txt・CatBoost .cbm）・sklearn joblib は `models/` で `.gitignore`・Phase 3 CR-04 pickle 廃止思想 |

## Sources

### Primary (HIGH confidence)
- **実コード（git 確認）:** src/utils/calibrator.py・group_split.py・category_map.py・src/features/category_map_consumer.py・availability.py・src/db/schema.py・connection.py・src/etl/fukusho_label.py・src/config/label_spec.yaml・feature_availability.yaml・pyproject.toml
- **実データ（PyArrow/pandas で検証）:** snapshots/feature_matrix_20260620-1a-postreview-v2.parquet（62列）・manifest.yaml・category_map_*.json・feature_matrix_20260619-1a-v3.parquet（63列・diff 比較）・live DB（label.fukusho_label 554,267行・n_odds_tanpuku/n_uma_race odds/ninki カラム実在）
- **git 履歴:** commit 43bd81f（CR-02 rolling_jyocd mode化）・ef635b6（fa 0.3.0 bump）・92e1310（直列化 bug 修正）・e5a75e2（SHA256 scope）
- **PyPI（2026-06-20 確認）:** lightgbm 4.6.0・catboost 1.2.10・scikit-learn 1.9.0・mlxtend 0.25.0
- **公式ドキュメント:**
  - [LightGBM 4.6 Advanced Topics](https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html) — categorical features は int32 cast・pandas category から codes 抽出
  - [CatBoost common parameters (has_time)](https://catboost.ai/docs/en/references/training-parameters/common) — `has_time=True` で random permutation 無効化
  - [CatBoost GitHub issue #1076](https://github.com/catboost/catboost/issues/1076) — has_time + Timestamp で1 permutation
  - [sklearn calibration.py (main)](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/calibration.py) — isotonic は <1000 sample で過学習・cv='prefit' 削除・FrozenEstimator 公式 idiom

### Secondary (MEDIUM confidence)
- [CatBoost NeurIPS 2018 paper](https://papers.neurips.cc/paper/7898-catboost-unbiased-boosting-with-categorical-features.pdf) — ordered TS・ordered boosting・予測シフト
- [sklearn CalibratedClassifierCV 1.9 doc](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html) — method/isotonic/sigmoid
- CLAUDE.md §14.3/§14.4/§15.2/§15.3（プロジェクト権威・要件定義書に基づく）

### Tertiary (LOW confidence)
- なし（全項目 git/実データ/公式 doc で裏取り済み・[ASSUMED] は plotly Phase 4 optional のみ）

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 4 では plotly/matplotlib は必須でない（evaluator 出力は JSON/Markdown 主体） | Standard Stack (Supporting) | LOW・Phase 6 で Calibration 曲線描画時に必要・Phase 4 は数値評価で十分 |
| A2 | CatBoost の `_code` int32 列は cat_features に含めず数値扱いで動作する | D-03 確定事項 | MEDIUM・CatBoost は int cat を cat_features 宣言要の場合あり・planner が要検証（含める場合は文字列化が必要） |
| A3 | `umaban` は feature と meta/key の両方に分類されるが、モデル入力には含める | 入力 snapshot 仕様 | LOW・§13.5「馬番」feature として許可・planner が分類整合を確認 |

**注:** A2 は CatBoost の仕様詳細で要検証。LightGBM は `categorical_feature` で int32 を明示的に categorical 指定可能（native が Fisher 分割を適用）。CatBoost は int 列を cat_features に含める場合文字列化が必要なケースがあるため、planner は CatBoost 学習時に `_code` 列をそのまま int32 で渡すか文字列化するかを実装時に検証すること。

## Open Questions

1. **CatBoost での高基数 ID `_code` 列の扱い**
   - What we know: LightGBM は int32 を `categorical_feature` で categorical 指定可能。
   - What's unclear: CatBoost は int 列を `cat_features` に含める場合、文字列化が必要か（CatBoost は cat_features を文字列/カテゴリカルとして扱う）。
   - Recommendation: planner は CatBoost 学習時に `_code` 列を文字列化して cat_features に含めるか、int32 のまま数値特徴量として扱うかを実装時に検証。文字列化する場合、`str(code)` で変換（非負 int なので一意）。

2. **BL-2 人気順ベースラインの確率変換方式**
   - What we know: `n_uma_race.ninki`（確定人気）が実DBに存在。
   - What's unclear: 人気順位を確率に変換する厳密な式（1/ninki レース内正規化 vs 人気帯別経験的確率）。
   - Recommendation: 1/ninki をレース内正規化して sum=払戻対象数 に揃える（BL-3 と同方式・市場暗示確率として標準）。planner が BL-2 実装時に確定。

## Environment Availability

> Phase 4 は外部ツール依存あり（lightgbm/catboost 追加インストール・PostgreSQL 既存）。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | 全体 | ✓ | 3.12.13 [VERIFIED: uv run python --version] | 3.11（CLAUDE.md fallback・不要） |
| uv | 依存管理 | ✓ | 0.11.21 [VERIFIED: uv --version] | — |
| PostgreSQL | label/odds SELECT・prediction 書込 | ✓ | 15.x（Homebrew・既存） | — |
| psycopg3 | DB 接続 | ✓ | 3.3.4 [VERIFIED: pyproject.toml] | — |
| LightGBM | 主モデル学習 | ✗ (未インストール) | 4.6.0 [VERIFIED: PyPI] | D-11 で `uv add lightgbm==4.6.0` |
| CatBoost | 比較モデル学習 | ✗ (未インストール) | 1.2.10 [VERIFIED: PyPI] | D-11 で `uv add catboost==1.2.10` |
| scikit-learn | キャリブレーション・BL-4 | ✓ | 1.9.0 [VERIFIED: pyproject.toml] | — |
| mlxtend | GroupTimeSeriesSplit | ✓ | 0.25.0 [VERIFIED: pyproject.toml] | — |
| pandas/PyArrow | Parquet 読込 | ✓ | 3.0.3 / 24.0.0 [VERIFIED: pyproject.toml] | — |
| pytest | テスト | ✓ | 9.1.0 [VERIFIED: pyproject.toml] | — |

**Missing dependencies with no fallback:**
- LightGBM 4.6.0・CatBoost 1.2.10 — Wave 0 で `uv add` によりインストール（D-11）

**Missing dependencies with fallback:**
- なし

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyPI/公式 doc/既 pin で全て確認
- Architecture: HIGH — 実コード契約（calibrator/group_split/category_map/availability/schema）+ 実データで裏取り
- 3way 分割: HIGH — 実データでサンプルサイズ/positive rate 実測
- BL-1..5: HIGH — 実DB で odds/ninki カラム実在確認・§14.2 定義確認
- D-02 feature 63→62: HIGH — git diff + Parquet diff で完全特定
- CatBoost _code 扱い: MEDIUM — LightGBM は確定・CatBoost の int cat 扱いは実装時検証要（A2）
- Pitfalls: HIGH — 公式 doc + CLAUDE.md + 実コードで裏取り

**Research date:** 2026-06-20
**Valid until:** 2026-07-20（30日・stable stack・LightGBM/CatBoost は stable）
