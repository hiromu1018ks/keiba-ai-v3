# Phase 10: Opponent Strength & Race-Relative Features - Pattern Map

**Mapped:** 2026-06-26
**Files analyzed:** 13（新規 2・拡張 8・新規テスト 3・拡張テスト 4・新規スクリプト 1）
**Analogs found:** 13 / 13（全ファイルに既存 idiom の強い analog あり・新規アルゴリズムは competition ranking のみ）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/features/field_strength.py` (NEW) | service (feature 構築) | transform (per-source-race batch + vectorized groupby) | `src/features/speed_figure.py::compute_speed_figure_for_history` | exact（obs_id 展開 + `_pit_cutoff_prefilter` strict `<` + history copy-not-rename + 監査列付与・全 idiom 対称） |
| `src/features/race_relative.py` (NEW) | service (feature 構築) | transform (target-only race_id group-by) | `src/features/rolling.py::build_rolling_features` (race_id group) + `src/features/builder.py` Step 6 推定脚質（race 内 group-by idiom） | role-match（target-only と過去走 rolling は data flow が違うが group-by + transform idiom は共通） |
| `src/features/rolling.py` (拡張) | service (feature 構築) | batch (per-observation latest-K rolling) | `src/features/rolling.py::_SPEED_FIGURE_AXES` 17 feature 拡張（自身・09.1-01-PLAN.md D-09.1-01/02 idioms） | exact（同ファイル内拡張・`_ROLLING_SYSTEMS` + `_SPEED_FIGURE_AXES` + best2_mean vectorized idiom の直接踏襲） |
| `src/features/builder.py` (拡張) | controller (feature matrix pipeline) | request-response (pipeline Step 挿入) | `src/features/builder.py` Step 5b speed_figure 挿入 + Step 6b 中間列 drop（自身・09-01-PLAN.md idiom） | exact（同ファイル内 Step 挿入・obs_id 早期構築 idiom の直接踏襲） |
| `src/features/snapshot.py` (拡張確認) | utility (Parquet 直列化) | file-I/O (byte-reproducible) | `src/features/snapshot.py::_coerce_rolling_columns_for_parquet` + `_is_categorical_rolling_col`（自身） | exact（同ファイル・`rolling_` prefix 自動対象・FEAT-03 rank/gap は別途 nullable Float64 扱い） |
| `src/features/availability.py` (拡張) | config (registry loader) | request-response (allowlist 検査) | `src/features/availability.py::_ROLLING_SYSTEMS_FOR_RESERVED` + `assert_matrix_columns_registered`（自身・09.1 で `speed_figure` 追加 idiom） | exact（同ファイル内・系統追加 + `assert_matrix_columns_registered` は自動追従） |
| `src/config/feature_availability.yaml` (拡張) | config | request-response (7項目スキーマ) | `src/config/feature_availability.yaml` rolling_speed_figure 17 feature エントリ（自身・L336-468） | exact（同一ファイル・7項目スキーマ + schema_version bump idiom） |
| `src/model/data.py` (拡張確認) | service (model data) | request-response (FEATURE_COLUMNS 動的導出) | `src/model/data.py::_derive_feature_columns` + `make_X_y`（自身・REVIEW H1） | exact（同ファイル・registry から動的導出・snapshot_id 明示伝播で新 feature 自動対応・手動変更不要想定） |
| `src/model/trainer.py` (拡張確認) | service (model training) | batch (LightGBM 再学習) | `src/model/trainer.py`（自身・v1.0 LightGBM 単体モデル再利用） | exact（同ファイル・FEATURE_COLUMNS 拡張で自動追従・SC#5 v1.0 LightGBM 再学習） |
| `src/model/evaluator.py` (拡張確認) | service (evaluation) | request-response (metrics 算出) | `src/model/evaluator.py::compute_metrics`（自身） | exact（同ファイル・事前登録指標不変・D-07 水準比較） |
| `src/model/segment_eval.py` (拡張確認) | service (evaluation) | request-response (binning 固定) | `src/model/segment_eval.py::evaluate_all_segments` + binning 定数（自身） | exact（同ファイル・binning 契約固定・参考記録） |
| `src/audit/report.py` (拡張・任意) | utility (audit report) | file-I/O (md + json) | `src/audit/report.py::SURFACE_ROWS`（自身） | role-match（Phase 10 feature 追加は任意・SC#4 SAFE-01 証明が主目的） |
| `tests/features/test_field_strength.py` (NEW) | test | unit (合成データ) | `tests/features/test_speed_figure.py` + `tests/features/test_speed_figure_pit.py` | exact（PIT strict `<` + 発走馬特定 + profile 8値 unit test 鋳型） |
| `tests/features/test_race_relative.py` (NEW) | test | unit (合成データ) | `tests/features/test_speed_figure.py`（機能 unit test 鋳型） | role-match（rank/gap/adjusted_rank の競馬分析 unit test・competition ranking は新規） |
| `tests/features/test_rolling.py` (拡張) | test | unit (合成データ) | `tests/features/test_rolling.py`（自身・speed_figure 17 feature unit test） | exact（同ファイル・`rolling_field_strength_*` 21 feature unit test 追加） |
| `tests/audit/test_audit_field_strength.py` (NEW) | test (adversarial) | adversarial (AST + lookahead 注入) | `tests/audit/test_audit_speed_figure.py`（5段階鋳型・`_FORBIDDEN_TOKENS` + `_scan_module_for_forbidden_tokens`） | exact（SC#4 SAFE-01 静的証明・AST Name/Attribute/Constant 検査 + `_pit_cutoff_prefilter` monkeypatch の直接踏襲） |
| `tests/features/test_speed_figure_builder_integration.py` (拡張) | test | integration (hardcode feature list) | 自身・09.1 で 17 feature に拡張済み | exact（同ファイル・hardcode リスト 79 → 106 更新） |
| `tests/audit/test_audit_speed_figure.py` (拡張) | test (adversarial) | adversarial (AST allowlist) | 自身・L219-238 `expected_speed_features` hardcode リスト | exact（同ファイル・Phase 10 feature 追加で SAFE-01 検査対象拡張） |
| `scripts/run_phase10_evaluation.py` (NEW) | service (SC#5 evaluation) | batch (3-way 比較) | `scripts/run_speed_figure_stopgate.py` | exact（D-16 非劣化 gate・許容幅 + Brier/LogLoss/AUC delta 算出・orchestrator.train_and_predict snapshot_id 明示伝播 idiom の直接踏襲） |

---

## Pattern Assignments

### `src/features/field_strength.py` (service, transform・D-06 第1段階)

**Analog:** `src/features/speed_figure.py::compute_speed_figure_for_history` (L566-700)

**モジュール docstring 聖域 3点セット** (speed_figure.py L1-32 idiom・対称):
```python
"""Phase 10・相手強度 field_strength profile（D-06 第1段階・FEAT-02・SC#1/SC#2・D-01〜D-06）.

3聖域（本 module の不変事項・adversarial テスト + AST audit で機械保証）:

1. **市場情報不使用（SAFE-01）**: オッズ/人気/過去人気/過去オッズ proxy は feature に一切入れない。
2. **PIT-correct 厳格版 as-of（SC#1・D-01）**: opponent.available_at < source_race.available_at
   (strict `<`）・source race 当日結果は混入しない。
3. **byte-reproducible（§19.1）**: 決定論的アルゴリズム（vectorized groupby + nlargest・固定順序）。
"""
```

**Imports + CUTOFF_SEMANTICS 実行時 assert** (speed_figure.py L34-46 idiom・対称):
```python
from __future__ import annotations
import numpy as np
import pandas as pd
from src.features.availability import CUTOFF_SEMANTICS

# HIGH #2 / SC#2: cutoff semantics 不変量の実行時参照（strict_less_than / Asia/Tokyo）。
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"
```

**`_pit_cutoff_prefilter` helper（adversarial test が monkeypatch で差替可能）** (speed_figure.py L98-118 / rolling.py L114-126 と対称):
```python
def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    """defense-in-depth pre-filter: opponent.available_at < source_race.available_at (strict <).

    adversarial test (tests/audit/test_audit_field_strength.py) が monkeypatch で ``<=`` 版に
    差し替え・guard 無効化で T+1 opponent データ混入を検証するため helper 化（speed_figure.py
    L98-118 と対称）。
    """
    return expanded[
        expanded["_opp_available_at"] < expanded["available_at"]
    ].copy()
```

**D-04 発走馬特定** (RESEARCH Pitfall 1・live-DB 実証済・`kakuteijyuni > 0` 単一条件):
```python
# D-04: 発走馬特定（live-DB 実証・time=0 と kakuteijyuni=0 が1516件完全一致＝未発走）
# tozaicd は EveryDB2 独自拡張で意味不明（1/2=完走馬大多数・3=中止・4=失格）・使わない。
starters_mask = history["kakuteijyuni"].fillna(0) > 0
starters = history[starters_mask].copy()
race_size = starters.groupby("race_nkey").size().to_dict()  # coverage 計算用
```

**D-05 top-k クランプヘルパ** (rolling.py L183-192 `_best2_mean_of_group` idiom・nlargest で vectorized):
```python
def _topk_mean_clamped(values: pd.Series, k: int) -> float:
    """top-k mean・k = min(k, valid_opponents) でクランプ（D-05）。

    rolling.py L183-192 _best2_mean_of_group と対称・nlargest で vectorized・決定論的。
    """
    valid = values.dropna()
    if len(valid) == 0:
        return float("nan")
    actual_k = min(k, len(valid))
    return float(valid.nlargest(actual_k).mean())
```

**D-03 profile 8値 vectorized 集約** (rolling.py L537-609 same_surface/distance_bucket conditional 集約 idiom・groupby + mean/max/count):
```python
# D-03: source race 内 opponent profile 8値（per-source-race batch + vectorized groupby）
# rolling.py L316-324 groupby("obs_id").agg idiom と対称・6.7M ペアを秒単位処理
profile = expanded.groupby(["race_nkey", "kettonum"]).agg(
    field_strength_mean=("_opp_rolling_ability", "mean"),
    field_strength_median=("_opp_rolling_ability", "median"),
    field_strength_top3_mean=("_opp_rolling_ability", lambda s: _topk_mean_clamped(s, 3)),
    field_strength_top5_mean=("_opp_rolling_ability", lambda s: _topk_mean_clamped(s, 5)),
    field_strength_max=("_opp_rolling_ability", "max"),
    field_strength_sd=("_opp_rolling_ability", "std"),
    field_strength_valid_count=("_opp_rolling_ability", "count"),
).reset_index()
# coverage = valid_count / race_size[race_nkey]（D-05 信頼度軸・Phase 9.1 count/sentinel 踏襲）
```

**copy-not-rename + 監査列付与** (speed_figure.py L616-621, L681-698 idiom・対称):
```python
out = history.copy()  # copy-not-rename（HIGH #5・入力列は破壊しない）
# ... profile 計算後 ...
# out に field_strength_{mean,median,top3_mean,top5_mean,max,sd,valid_count,coverage} 列を copy 追加
```

**RESEARCH Pattern 1 参照**: 詳細な vectorized 実装（per-source-race batch + starter × starter join・6.7M ペア）は 10-RESEARCH.md L268-327 に skelton あり・PLAN で詰める。

---

### `src/features/race_relative.py` (service, transform・FEAT-03 target-only)

**Analog:** `src/features/rolling.py::build_rolling_features` (race_id group) + `src/features/builder.py` Step 6 推定脚質（obs_id group-by idiom）

**モジュール docstring 聖域** (speed_figure.py L1-32 idiom・対称・FEAT-03 は target-only なので PIT は更に厳格):
```python
"""Phase 10・レース内相対特徴量（FEAT-03・target-only・D-07〜D-12）.

3聖域:
1. **SAFE-01**: odds/ninki proxy 不使用（adversarial AST 証明）。
2. **target-only（D-07）**: FEAT-03 は target observation のみ・過去走には適用しない。
   rank 母集団は feature_cutoff_datetime 時点で確定した rolling_speed_figure_mean_5 等
   （当日結果不使用・出馬表確定時点）。
3. **byte-reproducible**: 決定論的 competition ranking（pandas Series.rank・min rank・"1224"）。
"""
```

**D-10 competition ranking（pandas 標準 API・新規アルゴリズム・RESEARCH Pattern 3）**:
```python
def _competition_rank_desc_within_race(s: pd.Series) -> pd.Series:
    """competition ranking（min rank・同着同順位・"1224" 方式・D-10）。

    降順（速いほど上位）・rank 1 から開始・同着は同じ rank・次は同着数だけ飛ぶ。
    例: values [100, 95, 95, 90] desc → ranks [1, 2, 2, 4]
    D-09: 欠損は NaN のまま（na_option="keep"・母集団除外・最下位固定しない）。
    """
    return s.rank(method="min", ascending=False, na_option="keep")
```

**D-07 speed_index_rank 3軸** (target observation のみ・`race_nkey` group-by + transform):
```python
_SPEED_INDEX_AXES_FOR_RANK: tuple[str, ...] = (
    "rolling_speed_figure_mean_5",       # canonical（D-08 gap 主軸・D-11 additive score 主軸）
    "rolling_speed_figure_best2_mean_5", # 潜在能力の尖り
    "rolling_speed_figure_median_5",     # 外れ値頑健
)

def compute_race_relative_features(feature_matrix: pd.DataFrame) -> pd.DataFrame:
    """FEAT-03: target observation のみ・race_id（race_nkey）group-by で rank/gap/adjusted_rank を算出。

    D-07: target observation のみ（過去走には適用しない・feature_matrix 上で計算）。
    D-09: speed_index 欠損馬は NaN 保持・母集団除外。
    """
    result = feature_matrix.copy()  # copy-not-rename
    for i, axis_col in enumerate(_SPEED_INDEX_AXES_FOR_RANK, start=1):
        # D-10 competition ranking・race_id group-by + transform
        rank_col = f"speed_index_rank_{i}"  # 命名は PLAN で確定（例: speed_index_rank_mean5 等）
        result[rank_col] = result.groupby("race_nkey")[axis_col].transform(
            _competition_rank_desc_within_race
        )
    # ... gap_to_top / gap_to_3rd / adjusted_rank ...
    return result
```

**D-08 gap_to_top / gap_to_3rd（mean_5 主軸・指数 point 差）**:
```python
# D-08: top/3位の mean_5 − self・competition ranking で順位確定後・欠損馬は母集団除外
# gap_to_top = top(1位).mean5 - self.mean5
# gap_to_3rd = 3位.mean5 - self.mean5（出走馬 < 3 の場合は NaN）
```

**D-11/D-12 additive score + rank** (RESEARCH L544-568):
```python
ADJUSTED_RANK_COEF_CANDIDATES = (0.0, 0.1, 0.25, 0.5)
ADJUSTED_RANK_COEF_CANONICAL = 0.25  # D-12 事前登録 canonical 初期値

def _adjusted_score(mean5: pd.Series, fs_mean5: pd.Series, coef: float) -> pd.Series:
    """D-11: additive score = mean5 + coef * field_strength_mean_mean_5（正の補正）。

    差/比は不採用（強い相手と走ってきた馬を不当に下げるため）。
    """
    return mean5 + coef * fs_mean5

# 候補別 score は train/calib 窓内のみ（D-12・test 窓選び直し禁止・§11.2 聖域）
# 最終 feature_matrix には coef=0.25 canonical の rank のみ出力
```

---

### `src/features/rolling.py` (拡張・D-06 第2段階・21 feature)

**Analog:** 自身・`_SPEED_FIGURE_AXES` 17 feature 拡張（L136-180）+ best2_mean vectorized idiom（L464-487）+ same_surface/distance_bucket conditional 集約（L537-609）

**`_ROLLING_SYSTEMS` に `field_strength` 系統追加** (L74-87 idiom):
```python
_ROLLING_SYSTEMS: tuple[str, ...] = (
    "kakuteijyuni",
    "harontimel3",
    "jyuni3c_jyuni4c",
    "kyori",
    "jyocd",
    "days_since_prev",
    "timediff",
    "babacd",
    "speed_figure",
    # NEW Phase 10: 相手強度 profile（D-06 第2段階・D-13 21 feature）
    # source 列 = field_strength.py が history に付与した field_strength_{mean,median,top3_mean,
    # top5_mean,max,sd,valid_count,coverage} の8値（第1段階中間値）
    "field_strength",
)
```

**`_SYSTEM_SOURCE` 拡張** (L92-104 idiom):
```python
_SYSTEM_SOURCE: dict[str, tuple[str, ...]] = {
    # ... 既存 ...
    "speed_figure": ("speed_figure",),
    # NEW Phase 10: field_strength profile 8値を source とする（D-13 21 feature 生成）
    "field_strength": (
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    ),
}
```

**`_FIELD_STRENGTH_AXES` 定義** (D-13・21 feature・`_SPEED_FIGURE_AXES` L136-152 idiom と対称):
```python
# D-13: target 馬の過去走 field_strength profile を latest-K rolling で集約 = 21 feature
# rolling_field_strength_{axis}_{window} 命名（rolling_speed_figure_{axis}_{window} と対称）
_FIELD_STRENGTH_AXES: tuple[tuple[str, int], ...] = (
    # latest_1 系 (6): 直近1件の profile
    ("mean", 1), ("median", 1), ("top3_mean", 1), ("top5_mean", 1), ("max", 1), ("sd", 1),
    # mean_3 系 (5): 直近3件の profile平均（sd は定義不能なので除く・D-09.1-01 best2_mean 踏襲）
    ("mean", 3), ("median", 3), ("top3_mean", 3), ("top5_mean", 3), ("max", 3),
    # mean_5 系 (6): 直近5件の profile 平均
    ("mean", 5), ("median", 5), ("top3_mean", 5), ("top5_mean", 5), ("max", 5), ("sd", 5),
    # trend 系 (2): axis 名に window 埋込（_speed_figure_col_name idiom 踏襲）
    ("trend_last_minus_mean5", 5), ("trend_mean3_minus_mean5", 5),
    # count/coverage 系 (2): 信頼度軸（D-11・Phase 9.1 count/sentinel 踏襲）
    # → 列名生成で特別扱い（rolling_field_strength_valid_count_mean_5 / coverage_mean_5）
    ("valid_count_mean", 5), ("coverage_mean", 5),
)
```

**集約ブロック分岐** (L403-609 `if system == "speed_figure":` idiom・対称に `if system == "field_strength":` を追加):
```python
if system == "field_strength":
    # recent_sf ならぬ recent_fs（PIT filter + head(5) 済み LOOKBACK=5 窓）
    # _FIELD_STRENGTH_AXES の各 (axis, window) で windowed = groupby("obs_id").head(window)
    # rolling.py L408-507 speed_figure axis 分岐（mean/median/max/sd/best2_mean/trend_*）と
    # 対称な分岐を field_strength profile 8値に適用
    # ... 実装詳細は PLAN で詰める（RESEARCH Pattern 2 L336-358 参照） ...
    continue
```

**sentinel ルール** (L525-535 idiom・axis 毎の threshold・D-09/D-09.1-01 踏襲):
```python
# count 軸は常に実際 count（0〜window）を出力（D-11 信頼度軸・speed_figure L515-517 と対称）
# mean/median/top3_mean/top5_mean/max/sd/trend_* は count>=window で算出（sentinel MISSING）
# D-13 命名: rolling_field_strength_{axis}_{window}
```

---

### `src/features/builder.py` (拡張・Step 5c/5d/7/7b 挿入)

**Analog:** 自身・Step 5b speed_figure 挿入（L516-529）+ Step 6b 中間列 drop（L625-627）

**Step 5c: 相手強度 field_strength profile（D-06 第1段階・新）** (L516-529 Step 5b idiom と対称):
```python
# --- Step 5c: 相手強度 field_strength profile 計算（D-06 第1段階・新） ---
# Step 5b で history に speed_figure/available_at が揃った段階で呼出。
# copy-not-rename: history に field_strength_* profile 列を追加（HIGH #5 踏襲）。
from src.features.field_strength import compute_field_strength_profile
history = compute_field_strength_profile(history, observations=feature_matrix)
```

**注意: Step 5 rolling 呼出位置の移動** (RESEARCH Open Questions #6・A6・構成変更):
```python
# Step 5（build_rolling_features）は Step 5c の後に移動する必要がある
# （field_strength profile が history に揃った後で rolling するため・L531-551 を Step 5c の後に移動）
# copy-not-rename + hardcode feature list 更新で既存テスト（test_speed_figure_builder_integration.py）対応
```

**Step 7: レース内相対特徴量（FEAT-03・target-only・新）** (L625 drop 前に挿入・obs_id/race_nkey が使える段階):
```python
# --- Step 7: レース内相対特徴量（FEAT-03・target-only・新・D-07） ---
# Step 6b で obs_id を drop する前・race_nkey が使える段階で計算。
from src.features.race_relative import compute_race_relative_features
feature_matrix = compute_race_relative_features(feature_matrix)
```

**Step 7b: 中間列 drop** (L625-627 idiom・`errors="ignore"` で安全):
```python
# --- Step 7b: 中間列 drop（09-01-PLAN.md L625-627 と対称） ---
# field_strength profile 生値（field_strength_mean 等・rolling_ prefix 無し）は
# rolling_field_strength_* の計算用中間値・feature_matrix に出力しない。
# D-11 raw rank/profile と別保持: rolling_field_strength_* / speed_index_rank_* は残す。
feature_matrix = feature_matrix.drop(
    columns=[
        "obs_id", "trackcd", "kyori",  # 既存 Step 6b drop 維持
        # field_strength profile 中間値（第1段階）・rolling_ prefix 無しを明示 drop
        *[c for c in feature_matrix.columns
          if c.startswith("field_strength_") and not c.startswith("rolling_field_strength_")],
    ],
    errors="ignore",
)
```

**FEATURE_COLUMNS allowlist 契約** (L644 `assert_matrix_columns_registered`・Step 9 で自動追従):
```python
# Step 9 で assert_matrix_columns_registered(spec, list(feature_matrix.columns))
# 新 feature が registry に登録されていれば自動的に parity GREEN（drop すれば中間値は違反にならない）
```

---

### `src/features/snapshot.py` (拡張確認・新 feature は nullable Float64 自動対応)

**Analog:** 自身・`_coerce_rolling_columns_for_parquet` (L81-113) + `_is_categorical_rolling_col` (L116-154)

**Pitfall 5 対策** (RESEARCH L455-461・`rolling_field_strength_*` は自動対象・FEAT-03 は別途):
```python
# rolling_field_strength_* は "rolling_" prefix なので _coerce_rolling_columns_for_parquet が
# 自動的に nullable Float64 に変換（L100-101 `if not col.startswith("rolling_"): continue`）
# FEAT-03 の rank/gap 列（speed_index_rank_*・gap_to_top・gap_to_3rd・field_strength_adjusted_rank）は
# "rolling_" prefix でないため _is_categorical_rolling_col の対象外・別途 nullable Float64 扱いを
# builder 側で保証（sentinel → NaN・D-09 欠損馬 NaN 保持と整合）
```

**`_is_categorical_rolling_col` 拡張確認** (L116-154・REVIEW H3a の可変 window 対応済み):
```python
# rolling_field_strength_valid_count_mean_5 / coverage_mean_5 等の axis が numeric として
# 正しく扱われるか確認・必要なら L150 の numeric axis リストに追加
# （mean/sd/count/last/max/median 等は既出・valid_count/coverage/top3_mean/top5_mean は要確認）
```

---

### `src/features/availability.py` (拡張・registry parity)

**Analog:** 自身・`_ROLLING_SYSTEMS_FOR_RESERVED` (L143-159) に `speed_figure` 追加 idiom

**`_ROLLING_SYSTEMS_FOR_RESERVED` 拡張** (L143-159 idiom):
```python
_ROLLING_SYSTEMS_FOR_RESERVED: tuple[str, ...] = (
    "kakuteijyuni",
    "harontimel3",
    "jyuni3c_jyuni4c",
    "kyori",
    "jyocd",
    "days_since_prev",
    "timediff",
    "babacd",
    "speed_figure",
    # NEW Phase 10: field_strength 系統（D-06 第2段階・D-13 21 feature）
    # rolling_field_strength_valid_count_mean_5 / coverage_mean_5 は feature(信頼度) として
    # 扱うため reserved 自動展開から除外（speed_figure count_5 と同様・REVIEW H3b idiom）
    "field_strength",
)

# reserved 自動展開の field_strength count_5 除外（L188-192 idiom・speed_figure と対称）:
# } | {
#     f"rolling_{sys}_count_5"
#     for sys in _ROLLING_SYSTEMS_FOR_RESERVED
#     if sys != "speed_figure" and sys != "field_strength"  # 両系統の count_5 は feature 扱い
# }
```

**`assert_matrix_columns_registered`** (L314-348・新 feature は registry 登録で自動追従):
```python
# 新 feature（rolling_field_strength_* 21 + speed_index_rank_* 3 + gap_to_top/3rd +
# field_strength_adjusted_rank）が feature_availability.yaml に登録されていれば自動的に parity GREEN
# 中間値（field_strength_mean 等）は builder Step 7b で drop されるため違反にならない
```

---

### `src/config/feature_availability.yaml` (拡張・7項目スキーマ + schema_version bump)

**Analog:** 自身・rolling_speed_figure 17 feature エントリ（L336-468）

**schema_version bump** (L19 idiom・09.1 で 0.4.0 → 0.5.0):
```yaml
# Phase 10: schema_version 0.5.0 → 0.6.0（rolling_field_strength 21 feature + FEAT-03 6 feature 追加:
#            rolling_field_strength_{mean,median,top3_mean,top5_mean,max,sd}_{latest_1,mean_3,mean_5}
#            + trend_{last_minus_mean5,mean3_minus_mean5} + valid_count_mean_5 + coverage_mean_5
#            + speed_index_rank_{mean5,best2_mean5,median5}
#            + gap_to_top + gap_to_3rd + field_strength_adjusted_rank）
schema_version: "0.6.0"
```

**エントリ鋳型** (L340-381 rolling_speed_figure_last_1 等・7項目スキーマ):
```yaml
  # --- rolling_field_strength Phase 10（D-06 第2段階・D-13 21 feature）---
  # field_strength.py が history に付与した field_strength profile（8値中間値）を
  # rolling source とする。target 馬の過去走 profile を latest-K で集約。
  # odds-free・PIT-correct（過去走のみ集約・当日情報不使用・D-01 厳格版 as-of）。
  - feature_name: rolling_field_strength_mean_latest_1
    feature_group: rolling_field_strength
    available_from_timing: entry_confirmed
    source_role: history_allowed_post_race
    source_table: "normalized.n_uma_race (history) + derived field_strength profile"
    cutoff_rule: "race_date - 1 day (strict < cutoff, JST midnight)"
    leakage_risk_level: low
  # ... 残り 20 feature も同一スキーマ ...
```

**FEAT-03 エントリ** (race_relative・target-only・source_role: both_allowed・09.1 same_surface と同様に target + history):
```yaml
  # --- FEAT-03 Phase 10: レース内相対特徴量（target-only・race_id group-by）---
  # D-07: target observation のみ・race_id（race_nkey）group-by で算出。
  # D-09: speed_index 欠損馬は NaN 保持・母集団除外。
  # D-11: field_strength_adjusted_rank は additive score（mean5 + 0.25 * fs_mean5）の rank。
  - feature_name: speed_index_rank_mean5
    feature_group: race_relative
    available_from_timing: entry_confirmed
    source_role: both_allowed
    source_table: "derived from rolling_speed_figure_mean_5 (target obs group-by)"
    cutoff_rule: "race_date - 1 day (strict < cutoff, JST midnight)"
    leakage_risk_level: low
  # ... best2_mean5 / median5 / gap_to_top / gap_to_3rd / field_strength_adjusted_rank ...
```

---

### `src/model/data.py` (拡張確認・FEATURE_COLUMNS 動的導出)

**Analog:** 自身・`_derive_feature_columns` (L179-211) + `make_X_y` (L455-527)

**手動変更不要想定** (REVIEW H1・registry から動的導出):
```python
# _derive_feature_columns(snapshot_id) は registry 登録 feature ∩ snapshot 実カラム を返す
# Phase 10 で feature_availability.yaml に新 feature 27 個を登録すれば・自動的に FEATURE_COLUMNS に含まれる
# make_X_y(frame, snapshot_id="20260626-1a-opponentstrength-v1") で完全一致 assert が新 feature 含む形で GREEN
# snapshot_id 明示伝播が必須（H1-b・省略すると v1.0 FEATURE_COLUMNS が選択され stop gate が無意味化）
```

**`make_X_y` 完全一致 assert** (L489-493・新 feature 自動追従):
```python
if list(X.columns) != feature_columns:
    raise ValueError(
        "make_X_y: X.columns が FEATURE_COLUMNS と完全一致しない (review HIGH#9): ..."
    )
```

---

### `src/model/trainer.py` (拡張確認・SC#5 v1.0 LightGBM 再学習)

**Analog:** 自身・v1.0 LightGBM 単体モデル（FEATURE_COLUMNS 拡張で自動追従）

**手動変更不要想定**:
```python
# trainer は FEATURE_COLUMNS を X として受け取る（data.py 経由）
# Phase 10 snapshot で train_and_predict(snapshot_id="20260626-1a-opponentstrength-v1") を呼べば
# 自動的に 106 feature で LightGBM が再学習される・コード変更不要
# SC#5: v1.0 LightGBM baseline と Phase 10 snapshot の 3-way 比較（run_phase10_evaluation.py）
```

---

### `src/model/evaluator.py` + `src/model/segment_eval.py` (拡張確認・SC#5 非劣化 gate)

**Analog:** 自身・`compute_metrics` (evaluator.py L172-) + `evaluate_all_segments` (segment_eval.py)

**§15.2 事前登録指標不変** (evaluator.py L89 CALIBRATION_CURVE_BINS 等・binning 契約固定):
```python
# evaluator.compute_metrics が Brier/LogLoss/AUC/calibration_max_dev/sum_p 分布を算出
# Phase 6 D-07 水準（Brier=0.15222 / LogLoss=0.47488 / AUC=0.73230）と比較
# binning 定数（CALIBRATION_CURVE_BINS / ODDS_BAND_EDGES / NINKI_BAND_EDGES）は import 再利用・再定義禁止
```

**D-15/D-16 非劣化 gate** (run_speed_figure_stopgate.py L96-98 TOLERANCE_* idiom・直接踏襲):
```python
# Phase 10 許容幅は D-16 で planner が Plan 内で事前登録（候補例: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005）
# TOLERANCE_BRIER / TOLERANCE_LOGLOSS / TOLERANCE_AUC を run_phase10_evaluation.py に定義
# brier_delta <= TOLERANCE_BRIER and logloss_delta <= TOLERANCE_LOGLOSS and auc_delta >= -TOLERANCE_AUC
```

---

### `src/audit/report.py` (拡張・任意・SC#4 SAFE-01 証明)

**Analog:** 自身・`SURFACE_ROWS` (L77-168) + `AUDIT_SURFACE_COLUMNS` (L36-43)

**Phase 10 feature 追加は任意** (RESEARCH Architectural Responsibility Map L105):
```python
# SC#4 SAFE-01 証明は tests/audit/test_audit_field_strength.py が主（AST 検査）
# report.py の SURFACE_ROWS に Phase 10 行を追加するのは任意（SC#1 supplement 的位置づけ）
# 追加する場合は AUDIT_SURFACE_COLUMNS 7項目スキーマに従う（LOW-05 analog・presence assert 対象）
```

---

### `tests/features/test_field_strength.py` (NEW・unit test)

**Analog:** `tests/features/test_speed_figure.py` + `tests/features/test_speed_figure_pit.py`

**PIT strict `<` adversarial** (test_speed_figure_pit.py idiom・`_pit_cutoff_prefilter` monkeypatch):
```python
def test_opponent_ability_pit_strict_less(monkeypatch):
    """D-01 厳格版 as-of: opponent.available_at < source_race.available_at (strict <)。

    monkeypatch で _pit_cutoff_prefilter を <= 版に差替・T+1 opponent データ混入を検出する
    adversarial（test_speed_figure_pit.py と対称・guard 無効化で lookahead 検出）。
    """
    # source race と同日の opponent speed_figure が rolling に混入しないことを検証
```

**D-04 発走馬特定** (RESEARCH Pitfall 1・live-DB 実証):
```python
def test_starter_identification():
    """D-04: kakuteijyuni > 0 のみを opponent に含める・未発走馬は除外・競走中止馬は含む。"""
    # kakuteijyuni=0（未発走）は除外・kakuteijyuni=11-16（競走中止）は含むことを検証
```

**D-03 profile 8値** (機能 unit test):
```python
def test_profile_8vals():
    """D-03: source race 内 opponent profile 8値（mean/median/top3_mean/top5_mean/max/sd/
    valid_count/coverage）が正しく算出される・top-k クランプ（D-05）動作。"""
```

---

### `tests/features/test_race_relative.py` (NEW・unit test)

**Analog:** `tests/features/test_speed_figure.py`（機能 unit test 鋳型）

**D-10 competition ranking** (新規アルゴリズム・pandas.Series.rank):
```python
def test_competition_ranking_ties():
    """D-10: 同着が "1224" 方式（min rank）で同順位・次は飛ぶ。

    values [100, 95, 95, 90] desc → ranks [1, 2, 2, 4]（dense でない・min rank）。
    """
```

**D-07/D-09/D-11/D-12** (rank 3軸・gap・adjusted_rank・欠損馬除外):
```python
def test_speed_index_rank_3axes():
    """D-07: race_id 内 competition ranking が mean_5 / best2_mean_5 / median_5 の3軸で算出・target のみ。"""

def test_gap_to_top_3rd():
    """D-08: mean_5 主軸・top/3位との差・D-09 欠損馬は母集団除外・出走馬 < 3 は gap_to_3rd NaN。"""

def test_adjusted_rank_additive_score():
    """D-11/D-12: additive score（mean5 + 0.25*fs_mean5）の race_id 内 rank。
    候補 {0.0, 0.1, 0.25, 0.5} は train/calib 窓のみ・test 窓は canonical(0.25) のみ。"""
```

---

### `tests/audit/test_audit_field_strength.py` (NEW・adversarial)

**Analog:** `tests/audit/test_audit_speed_figure.py`（5段階鋳型・`_FORBIDDEN_TOKENS` + `_scan_module_for_forbidden_tokens`）

**直接コピー可能な構造** (test_audit_speed_figure.py L35-48・`_FORBIDDEN_TOKENS` は共通定数として再定義か import):
```python
from src.features import field_strength, race_relative  # 新モジュール
from src.audit...  # 必要に応じて _FORBIDDEN_TOKENS を共通化（現状は test_audit_speed_figure.py に定義）

_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)
```

**(a)(b)(c) AST audit** (test_audit_speed_figure.py L123-172 idiom・対称に field_strength / race_relative を検査):
```python
def test_no_odds_ninki_proxy_in_field_strength_source() -> None:
    """SC#4 AST: src.features.field_strength ソースが odds/ninki proxy を含まない。"""
    name_attr, const_str = _scan_module_for_forbidden_tokens(field_strength)
    assert not name_attr, f"field_strength.py に forbidden Name/Attribute: {name_attr}"
    assert not const_str, f"field_strength.py に SQL 文字列 proxy: {const_str}"

def test_no_odds_ninki_proxy_in_race_relative_source() -> None:
    """SC#4 AST: src.features.race_relative ソースが odds/ninki proxy を含まない。"""
    name_attr, const_str = _scan_module_for_forbidden_tokens(race_relative)
    assert not name_attr, ...
    assert not const_str, ...
```

**(d) FEATURE_COLUMNS allowlist** (test_audit_speed_figure.py L178-256 idiom・`_SPEED_FIGURE_SNAPSHOT_ID` を Phase 10 版に):
```python
_PHASE10_SNAPSHOT_ID = "20260626-1a-opponentstrength-v1"

def test_feature_columns_contains_phase10_features_no_proxy() -> None:
    """SC#4 allowlist: rolling_field_strength_* 21 + FEAT-03 6 feature 含有・forbidden prefix 0件。"""
    # test_audit_speed_figure.py L216-256 と同一構造・expected_features を Phase 10 27 feature に拡張
```

**(g) false-pass 回避** (test_audit_speed_figure.py L309-384 idiom・そのまま再利用可能):
```python
def test_false_pass_detection_power() -> None:
    """SC#4 false-pass 回避: guard が意図的注入(Name/Attribute/SQL 文字列 proxy)を検出することを証明。"""
    # 5段階鋳型(5)・test_audit_features.py / test_audit_speed_figure.py と同一・そのまま再利用
```

---

### `scripts/run_phase10_evaluation.py` (NEW・SC#5 非劣化 gate)

**Analog:** `scripts/run_speed_figure_stopgate.py`

**直接コピー可能な構造** (run_speed_figure_stopgate.py idiom・全体的に踏襲):
```python
"""Phase 10 SC#5 非劣化 gate: v1.0 baseline vs Phase 10 snapshot（opponentstrength）3-way 比較.

D-15: Brier/LogLoss/AUC が Phase 6 D-07 水準を悪化させないことを必須 gate。
D-16: 許容幅は事前登録（候補: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005・Phase 11 SC#2 と整合）。
selected-only calibration / odds_band×p_bin は参考記録（Phase 12 EVAL-01 先行指標）。

§15.2 事前登録指標不変: evaluator/segment_eval の binning 定数を import 再利用（再定義禁止）。
REVIEW H2/H7/H8: orchestrator.train_and_predict を呼び・生 trainer API は直接呼ばない。
REVIEW H-new: snapshot_id を明示伝播（省略すると v1.0 FEATURE_COLUMNS が選択され stop gate が無意味化）。

Usage::

    uv run python scripts/run_phase10_evaluation.py \\
        --baseline-snapshot-id 20260620-1a-postreview-v2 \\
        --phase10-snapshot-id 20260626-1a-opponentstrength-v1 \\
        --bt-split BT-1 \\
        --odds-snapshot-policy 30min_before \\
        --out-dir reports
"""
```

**許容幅定数** (run_speed_figure_stopgate.py L96-98 idiom・D-16 事前登録値で上書き):
```python
# D-16 事前登録（planner が決定・候補例: Brier 悪化 ≤0.002 / AUC 悪化 ≤0.005）
TOLERANCE_BRIER: float = 0.002   # D-16（run_speed_figure_stopgate の 0.005 から更に厳格化候補）
TOLERANCE_LOGLOSS: float = 0.01  # D-16
TOLERANCE_AUC: float = 0.005     # D-16
```

**make_model_version 形式** (predict.py L105-118 idiom・feature_snapshot_id 全体を prefix に):
```python
# feature_snapshot_id = "20260626-1a-opponentstrength-v1"
# make_model_version("20260626-1a-opponentstrength-v1", "lightgbm", 1)
#   → "20260626-1a-opponentstrength-v1-lgb-v1"
```

---

## Shared Patterns

### 1. PIT 厳格 `<`（core value・リーク防止最優先）

**Source:** `src/features/availability.py::CUTOFF_SEMANTICS` (L45-56) + `src/features/speed_figure.py::_pit_cutoff_prefilter` (L98-118) + `src/features/rolling.py::_pit_cutoff_prefilter` (L114-126)

**Apply to:** `src/features/field_strength.py`（D-01 厳格版 as-of）・`src/features/race_relative.py`（target-only・feature_cutoff_datetime 基準）

```python
# availability.py L45-56（単一不変量・全 feature 層が共有）
CUTOFF_SEMANTICS: dict[str, str] = {
    "comparison_operator": "strict_less_than",
    "timezone": "Asia/Tokyo",
    "cutoff_definition": (
        "feature_cutoff_datetime = pd.to_datetime(race_date) - pd.Timedelta(days=1) (JST midnight)"
    ),
    "pit_filter": "history.as_of_datetime < observation.feature_cutoff_datetime",
    "boundary_rule": (
        "a race whose as_of_datetime equals feature_cutoff_datetime midnight is "
        "EXCLUDED (strict <)"
    ),
}
```

```python
# speed_figure.py L98-118 / rolling.py L114-126（adversarial test が monkeypatch で <= に差替可能）
def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    return expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ].copy()
```

**実行時 assert** (speed_figure.py L46 / rolling.py L58・全 feature モジュールが共有):
```python
from src.features.availability import CUTOFF_SEMANTICS
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"
```

### 2. odds-free SAFE-01（adversarial AST 証明）

**Source:** `tests/audit/test_audit_speed_figure.py::_FORBIDDEN_TOKENS` (L35-37) + `_scan_module_for_forbidden_tokens` (L63-108)

**Apply to:** `tests/audit/test_audit_field_strength.py`（field_strength.py / race_relative.py の AST 検査）

```python
_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)
# AST Name ノード(id) / Attribute ノード(attr) で厳密判定・docstring の "odds-free" は false positive 回避
# REVIEW H5: SQL 文字列リテラル内 proxy は word-boundary 部分一致で検出
```

### 3. per-observation latest-K rolling（CYCLE-2 HIGH#1・cross-obs leak 回避）

**Source:** `src/features/rolling.py::build_rolling_features` (L209-713) + `_ROLLING_SYSTEMS` (L74-87) + `_SPEED_FIGURE_AXES` (L136-152)

**Apply to:** `src/features/rolling.py` 拡張（`_FIELD_STRENGTH_AXES` 追加・D-13 21 feature）

```python
# rolling.py L375-383（obs_id group・strict <cutoff・sort_values + groupby.head(5)）
recent = (
    history_filtered
    .sort_values(["obs_id", "race_start_datetime"], ascending=[True, False])
    .groupby("obs_id", sort=False)
    .head(5)
)
```

```python
# rolling.py L183-192（best2_mean vectorized・nlargest + kind="mergesort"・WR-01 対策）
def _best2_mean_of_group(values: pd.Series) -> float:
    vals = values.dropna()
    if len(vals) < 2:
        return float("nan")
    return float(vals.nlargest(2).mean())
```

### 4. byte-reproducible snapshot（§19.1 聖域）

**Source:** `src/features/snapshot.py::write_snapshot` (L157-314) + `_coerce_rolling_columns_for_parquet` (L81-113) + FIXED_REPRODUCE_TS / SHA256（metadata 除外）

**Apply to:** 全 feature 追加（`rolling_field_strength_*` は `rolling_` prefix で自動対象・FEAT-03 は nullable Float64 扱い）

```python
# snapshot.py L240-251（SHA256 は metadata 無し schema bytes のみ・データ内容のみ依存）
base_schema = pa.Schema.from_pandas(df_sorted, preserve_index=False)
base_table = pa.Table.from_pandas(df_sorted, schema=base_schema, preserve_index=False)
# pq.write_table(use_dictionary=False, compression="zstd", write_statistics=True, row_group_size=100_000)
sha256 = hashlib.sha256(sha_buf.getvalue().to_pybytes()).hexdigest()
```

### 5. registry↔Parquet parity（HIGH#3・fake-green 防止）

**Source:** `src/features/availability.py::assert_matrix_columns_registered` (L314-348) + `_ROLLING_SYSTEMS_FOR_RESERVED` (L143-159)

**Apply to:** `src/features/availability.py` 拡張（`field_strength` 系統追加）+ `src/config/feature_availability.yaml`（27 feature エントリ）

```python
# availability.py L333-348（出力カラムが全て registry / reserved / _code / raw-id 由来か検査）
allowed = registered_feature_columns(spec) | set(reserved) | set(raw_id_kept)
allowed |= {f"{c}_code" for c in _CATEGORY_COLUMNS}
banned_leak = TARGET_OBS_BANNED_COLUMNS & allowed
assert not banned_leak, f"banned source カラムが allowlist に混入: {banned_leak}"
for col in output_columns:
    if col not in allowed:
        raise ValueError(f"unregistered feature-matrix column: {col}")
```

### 6. copy-not-rename + FEATURE_COLUMNS allowlist（§14.3・CYCLE-2 HIGH#5）

**Source:** `src/features/builder.py` Step 4b (L461-472) + `src/model/data.py::_derive_feature_columns` (L179-211) + `make_X_y` 完全一致 assert (L489-493)

**Apply to:** `src/features/field_strength.py`（history に profile 列を copy 追加）・`src/features/builder.py` Step 7b（中間列 drop）

```python
# builder.py L461-472（抽象名 alias を copy で追加・元列は保持・HIGH#5）
feature_matrix["horse_id"] = feature_matrix["kettonum"]
```

```python
# data.py L487-493（X.columns == FEATURE_COLUMNS 完全一致 assert・review HIGH#9）
X = frame[feature_columns].copy()
if list(X.columns) != feature_columns:
    raise ValueError("make_X_y: X.columns が FEATURE_COLUMNS と完全一致しない (review HIGH#9)")
```

### 7. profile 化集約 + count/coverage 信頼度（Phase 9.1 idiom・単一代表値に潰さない）

**Source:** `src/features/rolling.py::_SPEED_FIGURE_AXES` 17 feature 拡張（L136-180）+ same_surface/distance_bucket count>=1 sentinel（L537-609・D-09.1-03）

**Apply to:** `src/features/field_strength.py`（D-03 profile 8値）+ `src/features/rolling.py`（D-13 21 feature・`_FIELD_STRENGTH_AXES`）

```python
# rolling.py L525-535（axis 毎の sentinel threshold・D-09/D-09.1-01 踏襲）
if axis == "last":
    threshold = 1
elif axis == "best2_mean":
    threshold = 2
else:  # mean/max/median/sd/trend_* は count>=window
    threshold = window
valid = (count_series >= threshold) & val_series.notna()
result[col] = pd.Series(np.where(valid, val_series, MISSING), ...)
```

---

## No Analog Found

全ファイルに強い analog が存在する。新規アルゴリズムは下記のみ（いずれも pandas 標準 API で対応・「Don't Hand-Roll」参照）:

| File / Algorithm | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `race_relative.py::_competition_rank_desc_within_race` | service | transform | competition ranking（"1224" 方式）はコードベックに未実装・ただし `pandas.Series.rank(method="min", ascending=False, na_option="keep")` 標準 API で対応（RESEARCH Pattern 3・CITED: pandas.pydata.org） |
| `race_relative.py::field_strength_adjusted_score` | service | transform | additive score（mean5 + 0.25 * fs_mean5）は新規・ただし pandas Series 四則演算の1行・D-11/D-12 で完全指定済 |
| `field_strength.py::compute_field_strength_profile` の vectorized 実装詳細 | service | transform | per-source-race batch + starter × starter join はコードベックに直接の先例なし・ただし rolling.py L378-383 `groupby + head` idiom + L537-609 conditional 集約 idiom の合成で対応（RESEARCH Pattern 1・詳細は PLAN で詰める） |

---

## Metadata

**Analog search scope:**
- `src/features/`（speed_figure.py・rolling.py・builder.py・snapshot.py・availability.py）
- `src/config/feature_availability.yaml`
- `src/model/`（data.py・trainer.py・evaluator.py・segment_eval.py・predict.py）
- `src/audit/report.py`
- `tests/audit/test_audit_speed_figure.py`（5段階鋳型）
- `tests/features/test_speed_figure*.py`（機能 unit test 鋳型）
- `scripts/run_speed_figure_stopgate.py`（SC#5 評価鋳型）
- `.planning/phases/09.1-speed-ability-profile-expansion/09.1-01-PLAN.md`（直前 Phase の idiom 参照元）
- `.planning/phases/09-speed-figure-foundation/09-01-PLAN.md`（Step 5b 挿入 idiom）

**Files scanned:** 18（実コード読込）+ 3（PLAN/research ドキュメント）
**Pattern extraction date:** 2026-06-26
**Key insight:** 全ての基盤プリミティブ（PIT strict `<`・`merge_asof(direction='backward')`・per-observation latest-K rolling・byte-reproducible snapshot・registry parity・adversarial AST audit・FEATURE_COLUMNS allowlist）は Phase 9/9.1 で確立済み。本 Phase は「既存 idiom をどう組み合わせて拡張するか」に集約され・新規アルゴリズムは competition ranking（pandas 標準 API）のみ。core value「リーク防止」は既存の strict `<` / adversarial audit の再利用で機械保証される。
