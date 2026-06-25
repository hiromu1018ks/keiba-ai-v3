# Phase 9: Speed Figure Foundation - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 11（新規 4・拡張 5・新規テスト/スクリプト 5・うち scripts 2 は SC#5/SC#6 評価用）
**Analogs found:** 11 / 11（全ファイルにコードベース内 analog 存在）

## 聖域（不変事項・全新規ファイルに適用）

CLAUDE.md 最優先。各新規ファイルは以下を漏れなく適用すること。

| 聖域 | 適用内容 | 参照アナログ |
|------|----------|--------------|
| **odds-free 原則（SAFE-01）** | 特徴量に odds/ninki/過去オッズ proxy を一切入れない。FEATURE_COLUMNS allowlist 契約・`assert_matrix_columns_registered` で強制 | `src/model/data.py::_derive_feature_columns` / `availability.py::assert_matrix_columns_registered` |
| **PIT-correct（SC#2）** | `available_at < feature_cutoff_datetime`（strict `<`・JST midnight・`race_date - 1day`）。`merge_asof(direction='backward')` 相当 | `src/features/rolling.py::_pit_cutoff_prefilter` / `src/utils/pit_join.py` |
| **byte-reproducible snapshot（SC#1/SC#3）** | `FIXED_REPRODUCE_TS`・SHA256（metadata 除外 schema bytes のみ）・§12.4 metadata 9 keys・registry↔Parquet parity | `src/features/snapshot.py::write_snapshot` |
| **categorical leak-safe** | speed_figure 自身は float（categorical 分岐不要・numeric path）。素材 categorical は LightGBM native + CatBoost `has_time=True` 踏襲 | `src/model/trainer.py::LOW_CARD_CAT_COLS` / `_prepare_catboost_pool` |
| **copy-not-rename builder** | 新 feature 追加は破壊的 rename でなく拡張。FEATURE_COLUMNS allowlist で契約 | `src/features/builder.py::build_feature_matrix` |
| **staging-swap idempotent ETL** + raw read-only | par/variant 永続化先は中間成果物（Parquet）のみ・normalized 層は system of record（raw 素材）・raw は readonly SELECT（REVOKE+fingerprint） | `src/features/builder.py::_fetch_history` |

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/features/speed_figure.py` (NEW) | service / feature-engine | transform（PIT prefilter → par/variant → points 変換） | `src/features/rolling.py::build_rolling_features` + `src/utils/pit_join.py` | exact（PIT prefilter・obs_id group・strict `<` idiom 完全一致） |
| `src/features/rolling.py` (拡張) | feature-engine | per-observation latest-K 集約 | `src/features/rolling.py`（自己拡張・`_ROLLING_SYSTEMS` に `"speed_figure"` 追加） | exact（自己・1-2 行追加で numeric path 自動適用） |
| `src/features/builder.py` (拡張) | feature-engine orchestrator | request-response（readonly SELECT → feature matrix） | `src/features/builder.py::build_feature_matrix`（自己拡張） | exact（Step 5/6 挿入位置に speed_figure 計算を追加） |
| `src/features/snapshot.py` (拡張) | service / snapshot writer | file-I/O（byte-reproducible Parquet） | `src/features/snapshot.py::write_snapshot`（自己・`_coerce_rolling_columns_for_parquet` 自動適用） | exact（自己・Float64 numeric path で rolling_speed_figure_* を直列化） |
| `src/features/availability.py` + `src/config/feature_availability.yaml` (拡張) | config / registry | request-response（loader → assert） | `src/features/availability.py::_ROLLING_SYSTEMS_FOR_RESERVED` + yaml `features:[]` ブロック | exact（自己・6 feature エントリ + count_5 予約追加） |
| `tests/features/test_speed_figure.py` (NEW) | test | unit（par/variant/byte-reproducible/parity） | `tests/features/test_rolling.py` + `tests/features/test_snapshot_repro.py` | exact（pytest・conftest fixture・`build_rolling_features` 呼出 idiom） |
| `tests/features/test_speed_figure_pit.py` (NEW) | test / adversarial | event-driven（lookahead 注入メタ検証） | `tests/audit/test_audit_features.py`（5段階鋳型・guard monkeypatch） | exact（SC#2 adversarial 鋳型・false-pass 回避構造） |
| `tests/audit/test_audit_speed_figure.py` (NEW) | test / adversarial audit | AST read-only + allowlist grep | `tests/audit/test_audit_features.py` + `tests/audit/test_audit_label.py` | exact（SC#4 SAFE-01 proxy 排除証明・AST 静的解析） |
| `scripts/verify_speed_figure_domain.py` (NEW) | script / visualizer | file-I/O（Plotly HTML 出力） | `src/model/segment_eval.py::render_segment_curves_html`（`include_plotlyjs='directory'`） + `scripts/run_evaluation.py` | role-match（CLI 起動 + Plotly HTML・SC#5 ドメイン整合性） |
| `scripts/run_speed_figure_stopgate.py` (NEW) | script / evaluator CLI | request-response（v1.0 vs +speed_figure 比較） | `scripts/run_evaluation.py`（masked DSN・try/finally・atomic write・binning 契約再利用） | exact（SC#6 stop gate・`evaluator.py`/`segment_eval.py` 再利用） |
| （参考）`src/model/data.py` / `trainer.py` / `evaluator.py` / `segment_eval.py` | service / model | （拡張不要・registry derived で FEATURE_COLUMNS 自動拡張・binning 契約固定再利用） | — | — |

---

## Pattern Assignments

### `src/features/speed_figure.py` (service / feature-engine, transform)

**Analog:** `src/features/rolling.py` + `src/utils/pit_join.py`

**Imports pattern**（`src/features/rolling.py` L45-55・`availability.CUTOFF_SEMANTICS` 参照を踏襲）:
```python
from __future__ import annotations
import pandas as pd
from scipy.stats import trim_mean  # robust 統計量（evaluator.py と同一依存）
from src.features.availability import CUTOFF_SEMANTICS
# HIGH #2: cutoff semantics 不変量の実行時参照（strict_less_than / Asia/Tokyo）
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"
```

**PIT prefilter pattern**（`src/features/rolling.py` L104-116 `_pit_cutoff_prefilter` を踏襲・strict `<` は `availability.CUTOFF_SEMANTICS["pit_filter"]` と同一不変量）:
```python
def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    """defense-in-depth pre-filter: as_of_datetime < feature_cutoff_datetime (HIGH #1/#2).

    adversarial test (tests/features/test_speed_figure_pit.py) が monkeypatch で
    本関数を <= 版に差し替え・guard 無効化で T+1 データ混入を検証できるようにするため
    helper に切り出す（rolling.py と対称）。
    """
    return expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ].copy()
```

**obs_id group + kettonum expand pattern**（`src/features/rolling.py` L236-265・CYCLE-2 HIGH #1 cross-obs leak 回避 idiom をそのまま再利用）:
```python
# Step 1b: expanded history（各 observation に kettonum で inner-join）
obs_keys = observations[["obs_id", "kettonum", "feature_cutoff_datetime"]].copy()
expanded = history.merge(obs_keys, on="kettonum", how="inner", suffixes=("", "_obs"))
# Step 2: PIT pre-filter（strict < feature_cutoff_datetime）
history_filtered = _pit_cutoff_prefilter(expanded)
# Step 3: par 算出（jyocd×trackcd×kyori 粒度・robust median・fallback 階層）
# Step 4: variant 算出（source_race_date×jyocd×surface・leave-one-race-out）
# Step 5: speed_figure = (par_sec - time_sec + variant_sec) × points_per_second(kyori)
```

**time 単位変換 + 完走馬フィルタ pattern**（`src/features/builder.py::_construct_derived_columns` L249-258 timediff parse と同型・sentinel → NaN・vector 化 idiom）:
```python
# time は 0.1秒単位（decisecond）。time <= 0 は取消/競走中止（4882件）→ NaN
time_sec = pd.to_numeric(history["time"], errors="coerce").where(
    pd.to_numeric(history["time"], errors="coerce") > 0, np.nan
) / 10.0
# trackcd → surface 派生（builder.py::_construct_derived_columns L281-311 と完全一致ロジック）
tc_num = pd.to_numeric(history["trackcd"].astype(str).str.strip(), errors="coerce")
surface = pd.Series(["unknown"] * len(history))
surface[tc_num.between(10, 22)] = "turf"
surface[tc_num.between(23, 25)] = "dirt"
surface[tc_num.between(51, 59)] = "obstacle"
```

**fallback_level 監査列 pattern**（D-07・byte-reproducible・再現性聖域・silent 丸め込み禁止）:
```python
# 各 row に fallback_level / sample_count / par_sec / variant_sec 監査列を必ず付与
# （"jyocd_trackcd_kyori" / "trackcd_kyori" / "all_day"）
```

**エラー処理 pattern**（`src/features/builder.py` L470-474・WR-01 fail-loud・空結果の silent data loss 回避）:
```python
if len(history) == 0:
    raise RuntimeError(
        "speed_figure: history fetch が空・silent data loss を検知 (WR-01 fail-loud)"
    )
```

---

### `src/features/rolling.py` (拡張, per-observation latest-K)

**Analog:** 自己拡張（L71-80 `_ROLLING_SYSTEMS`）

**最小拡張 pattern**（L71-80 に `"speed_figure"` を1行追加するだけで numeric path が自動適用）:
```python
_ROLLING_SYSTEMS: tuple[str, ...] = (
    "kakuteijyuni", "harontimel3", "jyuni3c_jyuni4c", "kyori",
    "jyocd", "days_since_prev", "timediff", "babacd",
    "speed_figure",  # NEW Phase 9
)
_SYSTEM_SOURCE["speed_figure"] = ("speed_figure",)  # history 側で builder が付与した列
```

**axis 拡張（D-09 6 feature 対応）**（L120-124 `_axes_for`・D-09 は `last_1` / `mean_3` / `mean_5` / `max_5` / `sd_5` / `count_5` だが既存は `mean/latest/sd/count` axis で window=5 固定）:
```python
# D-09 6 feature のうち mean_3 / mean_5 / max_5 / last_1 は window=3 と window=5 の
# 2窓対応 + max axis が必要。_axes_for に ("mean","latest","sd","count","max") を追加、
# または speed_figure 専用に builder 側で別途算出（RESEARCH.md Pattern 3 採択）。
# 既存 LOOKBACK=5 は不変・窓 3 は lookback パラメータで対応可。
```

---

### `src/features/builder.py` (拡張, feature-engine orchestrator)

**Analog:** 自己拡張（L457-494 Step 5 rolling 統合）

**Step 挿入 pattern**（L494 Step 6 推定脚質の直前・Step 5 rolling の直後に speed_figure 計算を挿入・copy-not-rename で新列追加）:
```python
# --- Step 5b: speed_figure 計算（過去走 history に speed_figure 列を付与） ---
# history に time/trackcd/jyocd/kyori が揃った段階で src.features.speed_figure を呼出。
# PIT 保証は speed_figure.py 内の _pit_cutoff_prefilter で strict < で適用（rolling と対称）。
# copy-not-rename: history に "speed_figure" 列を追加（既存列は破壊しない）。
from src.features.speed_figure import compute_speed_figure_for_history
history = compute_speed_figure_for_history(history)  # available_at = race_date を付与
# Step 5 rolling は "speed_figure" 列を numeric 系統として自動集約（_ROLLING_SYSTEMS 拡張済み）
```

**obs_id 中間処理列の除去 pattern**（L560-564 Step 6b・PyArrow 直列化不能 tuple を最終 matrix から drop・rolling と共有 idiom）:
```python
# speed_figure も obs_id を経由する場合は Step 6b で obs_id を drop 継続
feature_matrix = feature_matrix.drop(columns=["obs_id"], errors="ignore")
```

---

### `src/features/snapshot.py` (拡張, byte-reproducible Parquet)

**Analog:** 自己拡張（L80-112 `_coerce_rolling_columns_for_parquet`）

**自動適用 pattern**（speed_figure は float → `_is_categorical_rolling_col` が False → numeric path で nullable Float64 化・変更不要）:
```python
# snapshot.py は拡張不要。_coerce_rolling_columns_for_parquet が rolling_speed_figure_*
# を自動的に numeric path（L111）で Float64 化する（categorical 分岐不要・D-05 float のため）。
# SHA256 は metadata 除外 schema bytes のみ（CR-04 踏襲・speed_figure 追加で自動再計算）。
```

**feature_snapshot_id 命名 pattern**（Claude's Discretion → planner・v1.0 `20260620-1a-postreview-v2` 系統継承）:
```python
# 候補: 20260625-1a-speedfigure-v1（v1.0 系統の継承形態・make_model_version の prefix 整合）
# write_snapshot(out_dir, snapshot_id="20260625-1a-speedfigure-v1", created_at_fixed=FIXED_REPRODUCE_TS)
```

---

### `src/features/availability.py` + `src/config/feature_availability.yaml` (拡張, registry)

**Analog:** 自己拡張（`availability.py` L143-152 `_ROLLING_SYSTEMS_FOR_RESERVED` + yaml L57-368 `features:` ブロック）

**availability.py 拡張 pattern**（L143-152 に `"speed_figure"` 追加で `rolling_speed_figure_count_5` が reserved 自動登録）:
```python
_ROLLING_SYSTEMS_FOR_RESERVED: tuple[str, ...] = (
    "kakuteijyuni", "harontimel3", "jyuni3c_jyuni4c", "kyori",
    "jyocd", "days_since_prev", "timediff", "babacd",
    "speed_figure",  # NEW Phase 9（rolling.py::_ROLLING_SYSTEMS と順序含め完全一致・二重定義の危険を下げる）
)
```

**feature_availability.yaml 拡張 pattern**（L295-315 rolling_babacd ブロックの直後に6エントリ追加・7項目スキーマ完全踏襲）:
```yaml
  # --- rolling_speed_figure (Phase 9・Beyer 型スピード指数) ---
  - feature_name: rolling_speed_figure_mean_5
    feature_group: rolling_speed_figure
    available_from_timing: entry_confirmed
    source_role: history_allowed_post_race
    source_table: normalized.n_uma_race (history) + derived speed_figure
    cutoff_rule: "race_date - 1 day (strict < cutoff, JST midnight)"
    leakage_risk_level: low
  # （同様に latest_5 / sd_5 / count_5 / mean_3 / max_5 を追加）
```

**course_kubun silent parity bug 修正 pattern**（yaml L129-135・RESEARCH.md Anti-Pattern・live-DB で normalized 層に不存在・削除または trackcd 統合）:
```yaml
# 削除候補: - feature_name: course_kubun （L129-135）
# trackcd 単独で jyocd×trackcd×kyori 粒度は完全表現可能（RESEARCH A4）
```

---

### `tests/features/test_speed_figure.py` (NEW, unit + integration)

**Analog:** `tests/features/test_rolling.py` + `tests/features/test_snapshot_repro.py`

**conftest fixture 再利用 pattern**（`tests/features/conftest.py::_build_adversarial_rolling_rows` L92-129・8行合成 history・識別値で機械検出）:
```python
from tests.features.conftest import _build_adversarial_rolling_rows, _build_race_obs_row
# speed_figure 用に time/kyori/trackcd 列を追加した fixture を build（識別値で par/variant 算出を検証）
```

**byte-reproducible 再生成 test pattern**（SC#1・`tests/features/test_snapshot_repro.py` の `test_byte_reproducible_by_hash` idiom・同一 DataFrame → 同一 SHA256）:
```python
def test_byte_reproducible_regeneration():
    # 同一 metadata で再生成 → SHA256 bit-identical（metadata 除外 schema bytes のみ依存）
    sha1 = write_snapshot(df, snapshot_id="test-v1", created_at_fixed=FIXED_REPRODUCE_TS)
    sha2 = write_snapshot(df, snapshot_id="test-v2", created_at_fixed=FIXED_REPRODUCE_TS)
    assert sha1 == sha2  # snapshot_id/created_at が異なっても SHA256 同一（CR-04）
```

**registry↔Parquet parity test pattern**（SC#3・`availability.assert_matrix_columns_registered`・KEIBA_SKIP_DB_TESTS unset で live-DB）:
```python
def test_registry_parquet_parity():
    spec = load_feature_availability()
    # rolling_speed_figure_* 6 feature が registry に登録されていることを検証
    feature_names = {f["feature_name"] for f in spec["features"]}
    assert "rolling_speed_figure_mean_5" in feature_names
```

---

### `tests/features/test_speed_figure_pit.py` (NEW, adversarial / SC#2)

**Analog:** `tests/audit/test_audit_features.py`（5段階鋳型・guard monkeypatch・false-pass 回避）

**5段階鋳型 pattern**（`tests/audit/test_audit_features.py` L35-125 の構造を speed_figure PIT に適用）:
```python
def test_lookahead_injection_detected_and_fails():
    """SC#2 adversarial: PIT guard を無効化すると T+1 データが混入する（false-pass 回避）。

    5段階鋳型:
      (1) 合成 history 構築（target / same_day_prior / same_day_later / previous_day / future + eligible）
      (2) guard 有効でベースライン取得（eligible のみの par/variant）
      (3) 意図的 T+1 リーク注入（guard monkeypatch で < を <= に緩める）
      (4) guard 有効なら混入検出 → 正しい結果（ベースライン一致）
      (5) guard 無効なら混入する（値変化）で検証力証明
    """
    import src.features.speed_figure as sf_mod
    original = sf_mod._pit_cutoff_prefilter
    def _leaky(expanded):
        return expanded[expanded["as_of_datetime"] <= expanded["feature_cutoff_datetime"]].copy()
    sf_mod._pit_cutoff_prefilter = _leaky
    try:
        result_leaked = sf_mod.compute_speed_figure_for_history(...)
    finally:
        sf_mod._pit_cutoff_prefilter = original  # 確実に戻す
```

**docstring cross-reference 義務 pattern**（`tests/audit/test_audit_features.py` L128-146・T-08-04 重複回避・機能テストとの棲み分け明記）:
```python
# モジュール docstring に "SC#2 adversarial" + "cross-reference: tests/features/test_speed_figure.py" を必ず含む
```

---

### `tests/audit/test_audit_speed_figure.py` (NEW, adversarial audit / SC#4)

**Analog:** `tests/audit/test_audit_features.py` + `tests/audit/test_audit_label.py`

**AST read-only + allowlist grep pattern**（SC#4・SAFE-01 proxy 排除証明・`src/features/speed_figure.py` のソースを静的解析）:
```python
import ast, inspect
import src.features.speed_figure as sf_mod

def test_no_odds_ninki_proxy_in_speed_figure():
    """SAFE-01: speed_figure に odds/ninki/過去オッズ proxy が混入しない（AST 静的解析）."""
    source = inspect.getsource(sf_mod)
    tree = ast.parse(source)
    # source から禁止トークン（odds/ninki/fukuodds/ninkij/過去人気 proxy）を grep
    forbidden = {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
    # AST body を走査し、禁止名の Name ノード / attr 参照が無いことを assert
```

**FEATURE_COLUMNS allowlist 完全一致 pattern**（`src/model/data.py::make_X_y` L427-431・registry derived で rolling_speed_figure_* が自動追加されることを検証）:
```python
def test_speed_figure_in_feature_columns():
    from src.model.data import FEATURE_COLUMNS
    # registry に追加すれば FEATURE_COLUMNS に rolling_speed_figure_* が自動含まれる
    assert any(c.startswith("rolling_speed_figure_") for c in FEATURE_COLUMNS)
```

---

### `scripts/verify_speed_figure_domain.py` (NEW, visualizer / SC#5)

**Analog:** `src/model/segment_eval.py::render_segment_curves_html`（Plotly HTML） + `scripts/run_evaluation.py`（CLI 起動）

**Plotly HTML 出力 pattern**（`segment_eval.py` L444-449・`include_plotlyjs='directory'` で byte-reproducible・plotly.min.js 共有1ファイル）:
```python
import plotly.graph_objects as go
fig = go.Figure()
# クラス別指数分布・同一馬連続走安定・外れ値なし を可視化
fig.write_html(
    out_path, include_plotlyjs="directory",  # REVIEW C13: plotly.min.js 共有参照
    full_html=True, auto_open=False,
)
```

**CLI 起動 pattern**（`scripts/run_evaluation.py` L65-68・sys.path にリポジトリルートを追加して `src.*` を import）:
```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# argparse + main() 構造・Phase 6 CLI と同一 idiom
```

---

### `scripts/run_speed_figure_stopgate.py` (NEW, evaluator CLI / SC#6)

**Analog:** `scripts/run_evaluation.py`（masked DSN・try/finally・atomic write・binning 契約再利用）

**masked DSN + try/finally pattern**（`scripts/run_evaluation.py` L1316-1441・`make_pool(role='readonly')`・pool close を finally で保証）:
```python
settings = Settings()
logger.info("readonly DSN: %s", settings.dsn_masked)  # 生 DSN 絶対禁止（T-06-15）
readonly_pool = make_pool(settings, role="readonly")
try:
    # Step 1-4: v1.0 baseline vs (v1.0+speed_figure) 同一 BT split/policy で比較
    # D-14 必須4指標 + D-15 軽量 residual proxy
    result = evaluate_speed_figure_stopgate(...)
finally:
    readonly_pool.close()
```

**binning 契約固定再利用 pattern**（D-14・§15.2 事前登録指標不変・`evaluator.py`/`segment_eval.py` の定数を直接 import・bit-identical）:
```python
from src.model.evaluator import (
    CALIBRATION_CURVE_BINS,  # = 10（固定・事前登録）
    CALIBRATION_CURVE_MIN_BIN_COUNT,  # = 30
    compute_metrics, check_acceptance_gate,
)
from src.model.segment_eval import (
    ODDS_BAND_EDGES, _odds_band, _ninki_band, evaluate_all_segments,
)
# odds_band×p_bin bucketing を v1.0 と +speed_figure で同一 bin edges で比較（T-06-07）
```

**model_version 採番 pattern**（`src/model/predict.py::make_model_version` L105-146・`{feature_snapshot_id}-{short}-v{N}` 形式・再 suffix 追加禁止）:
```python
from src.model.predict import make_model_version
# Phase 9 単体モデルは別 model_version
mv = make_model_version("20260625-1a-speedfigure-v1", "lightgbm", version_n=1)
# → "20260625-1a-speedfigure-v1-lgb-v1"（review HIGH#4: prefix 全体使用）
```

**atomic write + BLOCK 発火 pattern**（`scripts/run_evaluation.py` L1048-1306・`_atomic_write_text`・BLOCK でも reports 書込後に RuntimeError）:
```python
from src.model.artifact import _atomic_write_text
# json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False) で RFC 8259 strict
# D-16: 両方（calibration 改善 + residual proxy）が全く改善しない場合は継続可否をユーザー確認
```

---

## Shared Patterns（全関連ファイルに適用）

### 1. PIT-correct（`available_at < feature_cutoff_datetime`・strict `<`）
**Source:** `src/features/availability.py` L45-56 `CUTOFF_SEMANTICS` / `src/features/rolling.py` L104-116 `_pit_cutoff_prefilter`
**Apply to:** `src/features/speed_figure.py`・`tests/features/test_speed_figure_pit.py`
```python
# CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than" を assert で固定
# _pit_cutoff_prefilter を helper に切り出し（adversarial test が monkeypatch 可能にするため）
# JST midnight 境界: as_of == cutoff は除外（<= でない）
```

### 2. obs_id group（cross-obs leak 回避・CYCLE-2 HIGH #1）
**Source:** `src/features/rolling.py` L189-265・`src/features/builder.py` L502-556
**Apply to:** `src/features/speed_figure.py`・`src/features/builder.py` 拡張部
```python
# horse key でなく obs_id (= (race_nkey, kettonum)) で groupby・同一 horse が複数 observation
# に現れる場合の cross-obs leak を回避。obs_id 列は最終 matrix から drop（PyArrow 直列化不可）
```

### 3. byte-reproducible Parquet（SHA256 metadata 除外）
**Source:** `src/features/snapshot.py` L221-269（CR-04 / HIGH #6）
**Apply to:** `src/features/snapshot.py`（自動適用・拡張不要）・`tests/features/test_speed_figure.py`
```python
# use_dictionary=False, compression="zstd", write_statistics=True, row_group_size=100_000
# SHA256 は metadata 無し schema bytes のみ（snapshot_id/created_at は run 毎変動でも SHA256 不変）
# _BYTE_REPRODUCIBLE_SCOPE = "parquet_data_only_metadata_excluded"
```

### 4. FEATURE_COLUMNS allowlist（registry derived・完全一致 assert）
**Source:** `src/model/data.py` L149-176 `_derive_feature_columns` + L427-431 `make_X_y`
**Apply to:** `src/features/availability.py` 拡張・`src/config/feature_availability.yaml` 拡張
```python
# registry に rolling_speed_figure_* を追加すれば FEATURE_COLUMNS に自動反映
# make_X_y で X.columns == FEATURE_COLUMNS を完全一致 assert（review HIGH#9）
# banned feature の alias sneak-in を構造的防止
```

### 5. categorical leak-safe（target/mean encoding 禁止 §14.3）
**Source:** `src/model/trainer.py` L51-75 `LOW_CARD_CAT_COLS` / `HIGH_CARD_CODE_COLS` / `has_time=True`
**Apply to:** speed_figure は float（categorical 処理不要）・素材 categorical は踏襲
```python
# LightGBM: native category dtype + __MISSING__ sentinel（NaN→-1 回避）
# CatBoost: cat_features + has_time=True（random permutation 無効化・ordered TS）
# target/mean encoding は構造的禁止（§14.3）・LightGBM native で禁止は free
```

### 6. fail-loud（silent data loss/fallback 禁止・D-13）
**Source:** `src/features/builder.py` L423-427 / L470-474（WR-01/WR-02）
**Apply to:** `src/features/speed_figure.py`・全テスト・全スクリプト
```python
# 空 DataFrame・空 history・必須列欠損 は RuntimeError/ValueError で即 fail
# silent NaN fill 禁止・sentinel (__MISSING__) で明示的欠損表現
# fallback_level 監査列で「どの粒度で算出したか」を必ず記録（D-07）
```

### 7. binning 契約固定（§15.2 事前登録指標不変）
**Source:** `src/model/evaluator.py` L89-91 `CALIBRATION_CURVE_BINS=10` / `MIN_BIN_COUNT=30`・`src/model/segment_eval.py` L74 `ODDS_BAND_EDGES`
**Apply to:** `scripts/run_speed_figure_stopgate.py`（SC#6）
```python
# v1.0 baseline と +speed_figure を同一 bin edges で比較（bit-identical・T-06-07）
# CALIBRATION_CURVE_BINS / MIN_BIN_COUNT / ODDS_BAND_EDGES は import して再利用・再定義しない
```

---

## No Analog Found

**なし。** 全ファイルにコードベース内の強力な analog が存在する。これは v1.0 の「copy-not-rename builder + FEATURE_COLUMNS allowlist 契約」設計の意図通りの拡張性で、Phase 9 の新規実装は `src/features/speed_figure.py` のみで、集約/snapshot/registry/評価は全て既存 asset の 1-2 行追加で動作する（RESEARCH.md "Key insight"・HIGH 確度）。

---

## Metadata

**Analog search scope:**
- `src/features/`（rolling.py / builder.py / snapshot.py / availability.py）
- `src/utils/`（pit_join.py / category_map.py）
- `src/model/`（data.py / trainer.py / evaluator.py / segment_eval.py / predict.py）
- `src/config/`（feature_availability.yaml）
- `tests/features/`（test_rolling.py / test_pit_cutoff.py / test_snapshot_repro.py / conftest.py）
- `tests/audit/`（test_audit_features.py / test_audit_label.py）
- `scripts/`（run_evaluation.py / run_feature_build.py）

**Files scanned:** 14（実読 8・grep/部分読み 6）
**Pattern extraction date:** 2026-06-25
**RESEARCH.md Architecture Patterns 検証結果:** 全 Pattern 1-4 および Anti-Patterns は実コード読みで裏付け済み。`course_kubun` silent parity bug（yaml L129-135）は live-DB で確定済みの真 bug・Phase 9 で修正推奨。
