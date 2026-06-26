"""過去走 rolling feature 構築（Phase 3 Plan 03-03 Task 1 / D-03/D-04/D-13）.

REVIEWS HIGH #1 (per-observation latest-K algorithm) / HIGH #2 (strict < cutoff) /
HIGH #4 (babacd history-allowed vs sibababacd/dirtbababd target-obs-banned) 対応。

8系統の rolling feature を構築する。numeric 系統は mean/latest/sd + count の 4 軸、
categorical 系統は mode/latest + count の 3 軸。
``rolling_kakuteijyuni / rolling_harontimel3 / rolling_jyuni3c_jyuni4c /
rolling_kyori / rolling_jyocd / rolling_days_since_prev / rolling_timediff /
rolling_babacd`` の 8 系統。

CR-02 (03-REVIEW): ``jyocd`` は JRA 競馬場コード（varchar(2)）のカテゴリカル値で
あるため、mean/sd でなく最頻値(mode)と直近値(latest)で集約する（数値平均は意味論的
に不正）。``_CATEGORICAL_SYSTEMS`` で categorical 扱いを明示。

CR-01 (03-VERIFICATION.md / gap-closure 03-05): ``rolling_timediff_*`` /
``rolling_babacd_*`` 計6エントリは normalized 層に source カラム
（``timediff`` / ``babacd``）が存在しないため全行 ``__MISSING__`` → NaN となり
registry↔実体 silent 乖離が生じていた。本 module から当該2系統を削除し、
Phase 3.1（Timediff/Babacd Rolling Restoration・Phase 2 ETL 拡張）で source
カラムが normalized 層に揃った後に再登録する。Phase 4 は 18 rolling features
（6系統×3軸）で学習する。
本 module は **明示的 observation 単位 latest-K algorithm** を採り、単一の後方 ``merge_asof``
（cutoff 以前の最新1件しか返さない）は使わない。

CLAUDE.md §3 idiom からの文書化された逸脱（WARNING #4・監査証跡は 03-RESEARCH.md
「Open Questions (RESOLVED)」#3 に記録）:

  - CLAUDE.md §3 は ``merge_asof(direction="backward")`` を PIT プリミティブと規定するが、
    同 API は cutoff 以前の最新 **1件** しか返さず latest-5 rolling window は取得できない。
  - 従って rolling.py は明示的 per-observation latest-K algorithm
    （strict ``< cutoff`` pre-filter + ``sort_values DESC`` + ``groupby("obs_id").head(5)``）
    を採用する。strict ``< cutoff`` pre-filter が leak-safety invariant（未来情報混入防止）
    を保持し、CLAUDE.md §3 の ``direction="backward"`` と同等の PIT-correctness を保証する。
  - 5-row adversarial テスト（target / same_day_prior / same_day_later / previous_day / future
    が全て除外されること）と 2-observation テスト（同一 horse × 異 cutoff で異なる window）
    で leak-safety を機械的に検証する（HIGH #1/#2 GREEN）。

CYCLE-2 HIGH #1 (re-open): horse 単位の groupby+head は horse 毎に1つの window
しか作らず、同一 horse が複数の target observation に現れた場合に cross-observation leak
を引き起こす。本 module は ``obs_id`` (= ``(race_nkey, kettonum)``・既存ならそのまま使用)
を window の group key にし、observation 毎に独立した window を構築する。
"""

from __future__ import annotations

import pandas as pd

import numpy as np

from src.features.availability import CUTOFF_SEMANTICS
from src.features.speed_figure import _derive_surface, derive_distance_bucket
from src.utils.category_map import MISSING

# HIGH #2: cutoff semantics 不変量の実行時参照（strict_less_than / Asia/Tokyo）。
# strict < filter は CUTOFF_SEMANTICS["pit_filter"] と同一不変量・本 module は
# 同定数を re-export し builder/snapshot と単一の真の源を共有する。
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"

# ---------------------------------------------------------------------------
# D-03: lookback window size
# ---------------------------------------------------------------------------
LOOKBACK: int = 5

# ---------------------------------------------------------------------------
# rolling 対象8系統。target race 当日の芝/ダート馬場状態（sibababacd/dirtbabacd:
# TARGET_OBS_BANNED_COLUMNS）は含めず、過去走の babacd（HISTORY_ALLOWED_POST_RACE）
# のみを rolling source とする（HIGH #4 taxonomy）。
# Phase 3.1 (Plan 03 Task 2): ``timediff`` / ``babacd`` 系統を再登録（CR-01 03-05 で
# 一時削除・normalized 層に source カラムが揃ったため復元・D-01 完全復元・SC#2 rolling 18→24）。
#   - timediff: builder 側で real parse 済み（sentinel 0000/9999 → NaN）・数値系と同一 path
#   - babacd:   builder 側で trackcd 第1桁分岐から派生（序数 varchar→to_numeric で int 化・D-02）
# ---------------------------------------------------------------------------
_ROLLING_SYSTEMS: tuple[str, ...] = (
    "kakuteijyuni",
    "harontimel3",
    "jyuni3c_jyuni4c",
    "kyori",
    "jyocd",
    "days_since_prev",
    "timediff",
    "babacd",
    # NEW Phase 9・Beyer 型スピード指数（history 側で builder が
    # compute_speed_figure_for_history で付与・float）。既存8系統とは異なり
    # _SPEED_FIGURE_AXES で (axis, window) ペアを明示指定し window 1/3/5 が混在。
    "speed_figure",
)

# 各系統が ``history`` から読む source 列の対応表。target race 当日の後半3ハロン
# （Pitfall 3.6 で禁止・TARGET_OBS_BANNED）は系統にも source にも含めない。
# Phase 3.1: timediff / babacd は builder 側で派生済みの history 列名を指す（単一 source）。
_SYSTEM_SOURCE: dict[str, tuple[str, ...]] = {
    "kakuteijyuni": ("kakuteijyuni",),
    "harontimel3": ("harontimel3",),
    "jyuni3c_jyuni4c": ("jyuni3c", "jyuni4c"),
    "kyori": ("kyori",),
    "jyocd": ("jyocd",),
    "days_since_prev": ("days_since_prev",),
    "timediff": ("timediff",),
    "babacd": ("babacd",),
    # NEW Phase 9: speed_figure は builder が compute_speed_figure_for_history で
    # history に付与済みの float 列をそのまま source とする（単一 source）。
    "speed_figure": ("speed_figure",),
}

# CR-02 (03-REVIEW): ``jyocd`` は JRA 競馬場コード（"01"=札幌, "05"=東京 等）の
# **カテゴリカル varchar(2)** であり、数値 mean/sd を取ると「平均競馬場コード = 5.8」の
# ような意味をなさない数値が生まれる。jyocd は categorical 系統として扱い、mean/sd で
# なく最頻値(mode)と直近値(latest)のみを算出する。
# 当日 jyocd は静的属性（feature_availability.yaml 別エントリ・本系統は「過去走の競馬場分布」
# を表現）。latest は「直近の競馬場」で意味論的に妥当なので保持・mean/sd は廃止。
_CATEGORICAL_SYSTEMS: frozenset[str] = frozenset({"jyocd"})

def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    """defense-in-depth pre-filter: ``as_of_datetime < feature_cutoff_datetime`` (HIGH #1/#2).

    本 helper に切り出した意図: adversarial test (``tests/audit/test_audit_features.py``) が
    ``monkeypatch`` で本関数を ``<=`` 版に差し替え・guard 無効化で T+1 データ混入を検証できる
    ようにするため。filter 式は byte-identical (``<`` strict) で振舞は不変。

    ``src/etl/label_reconcile.py`` 等・他モジュールから参照される公开 API ではなく・本 module 内の
    ``build_rolling_features`` 専用の private helper。
    """
    return expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ].copy()


# ---------------------------------------------------------------------------
# Phase 9/9.1: speed_figure 系統は D-09 6 feature + Phase 9.1 11 feature = 17 feature で
# window が混在するため (axis, window) ペアで明示指定。既存8系統（kakuteijyuni/harontimel3/
# jyuni3c_jyuni4c/kyori/jyocd/days_since_prev/timediff/babacd・M1 訂正）は
# 従来通り axis 名のみで window=5 固定（_axes_for 経由・本仕組みは使わない）。
# D-09 命名の正は rolling_speed_figure_{axis}_{window}（latest_5 でない・P03/P04 と完全一致）。
# ---------------------------------------------------------------------------
_SPEED_FIGURE_AXES: tuple[tuple[str, int], ...] = (
    ("last", 1),    # rolling_speed_figure_last_1   (直近状態・window=1)
    ("mean", 3),    # rolling_speed_figure_mean_3   (安定能力・window=3)
    ("mean", 5),    # rolling_speed_figure_mean_5   (window=5)
    ("max", 5),     # rolling_speed_figure_max_5    (潜在能力・window=5)
    ("sd", 5),      # rolling_speed_figure_sd_5     (不安定性・window=5)
    ("count", 5),   # rolling_speed_figure_count_5  (信頼度・window=5)
    # NEW Phase 9.1 (D-09.1-01): 分布形状・趨勢。sentinel は count>=window 踏襲（best2_mean のみ count>=2）
    ("median", 3),               # rolling_speed_figure_median_3   (外れ値頑健・中央値・window=3)
    ("median", 5),               # rolling_speed_figure_median_5   (window=5)
    ("best2_mean", 5),           # rolling_speed_figure_best2_mean_5 (上位2件の平均・count>=2)
    # trend 系: axis 名に window 埋込（rolling_speed_figure_trend_last_minus_mean5 等）。
    # 列名生成は _speed_figure_col_name で trend_ プレフィックスを特別扱い（_{window} を付けない）。
    # window=5 は「mean5 を使う」意味・sentinel も count>=window(5) で mean5 必要。
    ("trend_last_minus_mean5", 5),   # rolling_speed_figure_trend_last_minus_mean5  (last_1 - mean_5)
    ("trend_mean3_minus_mean5", 5),  # rolling_speed_figure_trend_mean3_minus_mean5 (mean_3 - mean_5)
)


def _speed_figure_col_name(axis: str, window: int) -> str:
    """``_SPEED_FIGURE_AXES`` の (axis, window) → 出力列名（D-09.1-01 命名）。

    通常: ``rolling_speed_figure_{axis}_{window}``（D-09 踏襲）。
    trend 系: axis 名に window が埋込（``trend_last_minus_mean5`` 等）のため ``_{window}``
    を付与しない（ユーザー指定命名 ``rolling_speed_figure_trend_last_minus_mean5`` を正とする）。
    """
    if axis.startswith("trend_"):
        return f"rolling_speed_figure_{axis}"
    return f"rolling_speed_figure_{axis}_{window}"


# ---------------------------------------------------------------------------
# Phase 9.1 (D-09.1-02): same_surface / same_distance_bucket 系統。
# 条件適性 profile・target race と同条件（surface / distance bucket）の過去走のみで集約。
# _SPEED_FIGURE_AXES でなく別管理（count>=1 sentinel・D-09.1-03）。window=5 は直近5走窓固定。
# ---------------------------------------------------------------------------
_SPEED_FIGURE_CONDITIONAL_AXES: tuple[tuple[str, str], ...] = (
    # (condition, stat_axis) → rolling_speed_figure_{condition}_{stat_axis}_5
    ("same_surface", "mean"),
    ("same_surface", "max"),
    ("same_surface", "count"),
    ("same_distance_bucket", "mean"),
    ("same_distance_bucket", "max"),
    ("same_distance_bucket", "count"),
)


def _best2_mean_of_group(values: pd.Series) -> float:
    """group 内の上位2件（速い = ``speed_figure`` 大）の平均（best2_mean 軸・D-09.1-01）。

    ``count < 2`` は ``NaN``（上位2件不能・sentinel 側で ``__MISSING__`` 化）。
    決定論的: ``nlargest(2)`` は同値の場合安定順序で2件選ぶ（byte-reproducible）。
    """
    vals = values.dropna()
    if len(vals) < 2:
        return float("nan")
    return float(vals.nlargest(2).mean())


# 系統毎の出力 axis セット（mean/latest/sd/count または mode/latest/count）。
# **既存8系統専用**（speed_figure には使わない・speed_figure は _SPEED_FIGURE_AXES で別経路）。
def _axes_for(system: str) -> tuple[str, ...]:
    """系統が出力すべき axis タプルを返す（categorical は mode/latest/count）。

    **既存8系統専用**。speed_figure 系統は呼出側で別途 _SPEED_FIGURE_AXES を参照すること
    （本関数は速度低下回避と明示的分離のため speed_figure を扱わない・window 1/3/5 混在は
    _SPEED_FIGURE_AXES の (axis, window) 形式でのみ表現）。
    """
    if system in _CATEGORICAL_SYSTEMS:
        return ("mode", "latest", "count")
    return ("mean", "latest", "sd", "count")


def build_rolling_features(
    observations: pd.DataFrame,
    history: pd.DataFrame,
    *,
    lookback: int = LOOKBACK,
) -> pd.DataFrame:
    """8系統 rolling feature を observation 単位で構築する（numeric は mean/latest/sd+count・
    categorical は mode/latest+count）。

    明示的 **per-observation latest-K algorithm** （HIGH #1・CYCLE-2: ``obs_id`` 単位・
    horse 単位でない・単一後方 join 不使用）で cutoff 以前の直近 ``lookback`` 走を取得し、
    系統毎の軸集約（D-04）と5走未満 ``__MISSING__`` sentinel（D-13）を適用する。

    CR-02 (03-REVIEW): categorical 系統（``_CATEGORICAL_SYSTEMS``・現在は ``jyocd``）は
    mean/sd でなく最頻値(mode)を算出する（varchar 競馬場コードの数値平均は意味論的バグ）。

    Pipeline
    --------
    1. **入力検証 + obs_id 構築** — ``observations`` に ``feature_cutoff_datetime`` /
       ``kettonum`` / ``race_nkey`` が存在すること、``history`` に ``as_of_datetime`` /
       ``kettonum`` / source 列が存在することを assert。``observations`` に ``obs_id`` 列が
       無ければ ``obs_id = list(zip(race_nkey, kettonum))`` で生成（既存ならそのまま使用）。
    1b. **expanded history** — ``history`` を各 observation に ``kettonum`` で inner-join
        （1 history 行が複数 obs_id に複製され得る・同一 horse の異 observation で独立 window）。
    2. **defense-in-depth pre-filter（HIGH #1/#2・CYCLE-2 per-obs cutoff・Pitfall 3.1）** —
        expanded history 上で ``history.as_of_datetime < feature_cutoff_datetime`` を適用
        （厳格 ``<``・CUTOFF_SEMANTICS["pit_filter"] と整合・``<=`` でない）。
    3. **per-observation latest-K window（HIGH #1・CYCLE-2: ``obs_id`` 単位）** —
        ``sort_values(["obs_id","race_start_datetime"], ascending=[True,False])
        でソート後 ``.groupby("obs_id").head(lookback)`` で observation 毎に直近5走を取得。
        horse key での groupby は cross-observation leak を起こすため**使わない**（HIGH #1）。
    4. **3軸集約（D-04）** — mean / latest / sd / count。5走未満 sentinel（D-13）。
    5. **8系統全てに3軸 + count 適用**。``jyuni3c_jyuni4c`` は両コーナー平均から rolling。

    Parameters
    ----------
    observations : pd.DataFrame
        対象レースの馬（1行 = 1 target observation）。``feature_cutoff_datetime`` /
        ``kettonum`` / ``race_nkey`` は必須。``obs_id`` 列があれば再利用（無ければ内部生成）。
        ``race_start_datetime`` があれば latest 値算出の sort 補助に使用する。
    history : pd.DataFrame
        過去走。``kettonum`` / ``as_of_datetime`` / source 列（kakuteijyuni/timediff/
        harontimel3/jyuni3c/jyuni4c/kyori/babacd/jyocd/days_since_prev）は必須。
        ``race_start_datetime`` が無ければ ``as_of_datetime`` で代用。
    lookback : int
        window size（D-03 既定 ``LOOKBACK = 5``）。

    Returns
    -------
    pd.DataFrame
        ``observations`` に rolling 列を付与した DataFrame。行 key は ``(race_nkey, kettonum)``
        で一意。``obs_id`` 列は結果に伝播（呼出側が observation 毎に結果を取り出せる）。

        - numeric 系統: ``rolling_<system>_{mean,latest,sd,count}_5`` （7系統 × 4 = 28 列）
        - categorical 系統: ``rolling_<system>_{mode,latest,count}_5`` （jyocd 1系統 × 3 = 3 列）
        - 計 31 列（CR-02 で jyocd を mode/latest/count に変更・numeric 32→28 + categorical 3 = 31）

        Phase 9/9.1 で追加: speed_figure 系統は D-09 6 feature + Phase 9.1 11 feature = 17 feature。
        ``_SPEED_FIGURE_AXES`` で (axis, window) を明示指定し window 1/3/5 が混在。列名形式は
        ``rolling_speed_figure_{axis}_{window}``（``latest_5`` でない・D-09 命名の正）。
        Phase 9.1 (D-09.1-01) 追加: median_3/median_5/best2_mean_5/trend_last_minus_mean5/
        trend_mean3_minus_mean5（trend 系は axis 名に window 埋込・_speed_figure_col_name で
        ``_{window}`` 付与なし・ユーザー指定命名）。
        Phase 9.1 (D-09.1-02) 追加: same_surface/same_distance_bucket の mean/max/count
        （``_SPEED_FIGURE_CONDITIONAL_AXES``・target と同条件の過去走のみ・count>=1 sentinel・
        D-09.1-03 文書化）。既存8系統の ``rolling_<sys>_<axis>_5`` 形式は不変（回帰回避）。
        5走未満は ``__MISSING__`` sentinel（count_5 のみ実際 count を出力・D-11 信頼度軸）。

    Raises
    ------
    ValueError
        必須列が欠損、または入力型が不正の場合。
    """
    # --- Step 1: 入力検証 + obs_id 構築（CYCLE-2 HIGH #1: window group key） ---
    _required_obs_cols = ("feature_cutoff_datetime", "kettonum")
    missing_obs = [c for c in _required_obs_cols if c not in observations.columns]
    if missing_obs:
        raise ValueError(
            f"observations に必須列が欠損: {missing_obs} (rolling 構築・HIGH #1/#2)"
        )
    missing_hist = [c for c in ("as_of_datetime", "kettonum") if c not in history.columns]
    if missing_hist:
        raise ValueError(
            f"history に必須列が欠損: {missing_hist} (rolling 構築・HIGH #1)"
        )
    # history source 列は系統毎に optional（欠損系統は該当 rolling 出力が sentinel になる・
    # 5走未満 sentinel と同等の D-13 挙動・silent fill ではない）。

    result = observations.copy()
    # obs_id: 既存あれば再利用、無ければ (race_nkey, kettonum) が両方あればそれを、
    # さもなくば DataFrame index から生成（テスト用単一 obs 等で race_nkey が無い場合）。
    if "obs_id" not in result.columns:
        if "race_nkey" in result.columns:
            result["obs_id"] = list(
                zip(result["race_nkey"].tolist(), result["kettonum"].tolist(), strict=False)
            )
        else:
            result["obs_id"] = list(
                zip(result.index.tolist(), result["kettonum"].tolist(), strict=False)
            )

    # rolling 出力列を object dtype で初期化（数値と __MISSING__ sentinel 文字列が混在・
    # silent fill 禁止・D-13）。pandas が str dtype を推論して数値代入を拒否するのを避ける。
    # CR-02: categorical 系統（jyocd）は mean/sd でなく mode/latest を出力。
    # Phase 9: speed_figure 系統は _SPEED_FIGURE_AXES から列名を生成
    # （rolling_speed_figure_{axis}_{window}・window 1/3/5 混在）。既存8系統は
    # _axes_for(system) で window=5 固定（rolling_<sys>_<axis>_5）。
    rolling_cols: list[str] = []
    for system in _ROLLING_SYSTEMS:
        if system == "speed_figure":
            for axis, window in _SPEED_FIGURE_AXES:
                col = _speed_figure_col_name(axis, window)
                rolling_cols.append(col)
                result[col] = pd.Series(
                    [MISSING] * len(result), dtype=object, index=result.index
                )
            # NEW Phase 9.1 (D-09.1-02): same_surface / same_distance_bucket（条件適性 profile）
            for cond, stat_axis in _SPEED_FIGURE_CONDITIONAL_AXES:
                col = f"rolling_speed_figure_{cond}_{stat_axis}_5"
                rolling_cols.append(col)
                result[col] = pd.Series(
                    [MISSING] * len(result), dtype=object, index=result.index
                )
            continue
        for axis in _axes_for(system):
            col = f"rolling_{system}_{axis}_5"
            rolling_cols.append(col)
            result[col] = pd.Series([MISSING] * len(result), dtype=object, index=result.index)

    # history が空（新馬のみ）なら sentinel 初期値のまま返す（D-13）
    if len(history) == 0:
        return result

    # race_start_datetime が無ければ as_of_datetime を sort key に使う
    hist = history.copy()
    if "race_start_datetime" not in hist.columns:
        hist["race_start_datetime"] = hist["as_of_datetime"]

    # --- Step 1b: expanded history（各 observation に過去走を紐付け） ---
    # history が既に obs_id + feature_cutoff_datetime を持つ場合（Phase 9 以降・
    # compute_speed_figure_for_history が observation 毎に PIT filter 済みの obs_id 展開
    # フレームを返す）は obs_keys merge をスキップする。merge すると同一馬が複数 observation
    # に現れる際に history 行が observation 数だけ複製され行数が爆発（数十万 observation ×
    # 過去走 で致命的低速化・Phase 9.1 で顕在化）。未展開 history（unit test 等）は従来通り merge。
    if "obs_id" in hist.columns and "feature_cutoff_datetime" in hist.columns:
        expanded = hist.copy()
    else:
        obs_keys = result[["obs_id", "kettonum", "feature_cutoff_datetime"]].copy()
        expanded = hist.merge(obs_keys, on="kettonum", how="inner", suffixes=("", "_obs"))
        # 同名列衝突回避: feature_cutoff_datetime は obs_keys 由来のみ使用
        if "feature_cutoff_datetime_obs" in expanded.columns:
            expanded["feature_cutoff_datetime"] = expanded["feature_cutoff_datetime_obs"]
            expanded = expanded.drop(columns=["feature_cutoff_datetime_obs"])

    if len(expanded) == 0:
        return result  # 全 observation が新馬 → sentinel のまま

    # --- Step 2: defense-in-depth pre-filter（HIGH #1/#2: strict < feature_cutoff_datetime） ---
    # CUTOFF_SEMANTICS["pit_filter"]: history.as_of_datetime < observation.feature_cutoff_datetime
    # 本 filter は module-private helper に切り出し・adversarial test (tests/audit/test_audit_features.py)
    # が monkeypatch で guard を無効化（``<`` → ``<=``）して T+1 データ混入を検証できるようにする。
    history_filtered = _pit_cutoff_prefilter(expanded)

    if len(history_filtered) == 0:
        return result

    # --- Step 3: per-observation latest-K window（HIGH #1・CYCLE-2: obs_id group） ---
    # ``groupby("obs_id").head(5)`` で observation 毎に直近5走（CYCLE-2 HIGH #1:
    # horse key でない・cross-observation leak 回避）。
    recent = (
        history_filtered
        .sort_values(["obs_id", "race_start_datetime"], ascending=[True, False])
        .groupby("obs_id", sort=False)
        .head(5)
    )

    # --- Step 4/5: 3軸集約 + count + 5走未満 sentinel（D-04/D-13・Pitfall 3.3） ---
    # 各 obs_id 毎に system 列を集約
    # CR-02 (03-REVIEW): categorical 系統（jyocd 等）は数値 mean/sd でなく最頻値(mode) を算出。
    # varchar 競馬場コードを to_numeric すると意味をなさない数値平均になるため、
    # categorical 扱いとして source 列の生値を集約対象にする。
    for system in _ROLLING_SYSTEMS:
        source_cols = _SYSTEM_SOURCE[system]
        # 系統の source 列が history に無ければ全系統 sentinel 初期値のまま（D-13 相当）
        if not all(c in recent.columns for c in source_cols):
            # speed_figure 列が無い場合は次系統へ（sentinel 初期値維持・回帰安全和）
            continue

        # --- Phase 9/9.1: speed_figure 系統専用集約ブロック（D-09 6 + Phase 9.1 11 = 17 feature） ---
        # 既存8系統のロジック（categorical/numeric）は維持し・speed_figure は別経路で処理。
        # Phase 9.1: median/best2_mean/trend_* は _SPEED_FIGURE_AXES 拡張・same_surface/
        # same_distance_bucket は集約後の conditional 別サブブロック（D-09.1-02・count>=1 sentinel）。
        # recent は既に groupby("obs_id").head(5) 済み（LOOKBACK=5 窓）・
        # さらに head(window) で window<=5 に切詰める（PIT filter 後なので安全）。
        if system == "speed_figure":
            speed_series = pd.to_numeric(recent["speed_figure"], errors="coerce")
            recent_sf = recent.assign(_sf_value=speed_series)
            # 各 (axis, window) 毎に window 上位 K 件で集約（race_start_datetime DESC sort 済み）
            # head(window) は sort 済み recent で時系列降順の上位 K 件を取る（groupby head）。
            for axis, window in _SPEED_FIGURE_AXES:
                # window 上位 K 件に切替（obs_id 毎に独立・window<=5 なので recent を起点に安全）
                windowed = (
                    recent_sf
                    .groupby("obs_id", sort=False)
                    .head(window)
                )
                if axis == "last":
                    # first が最新1件（race_start_datetime DESC sort 済み）
                    val_per_obs = (
                        windowed.groupby("obs_id", sort=False)["_sf_value"].first().to_dict()
                    )
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "mean":
                    val_per_obs = (
                        windowed.groupby("obs_id")["_sf_value"].mean().to_dict()
                    )
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "max":
                    val_per_obs = (
                        windowed.groupby("obs_id")["_sf_value"].max().to_dict()
                    )
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "sd":
                    val_per_obs = (
                        windowed.groupby("obs_id")["_sf_value"].std(ddof=1).to_dict()
                    )
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "count":
                    # count 軸は常に实际 count（0〜window）を出力（D-11・信頼度軸）
                    val_per_obs = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                    count_check = None  # count 自身は sentinel 不要
                # NEW Phase 9.1 (D-09.1-01): 分布形状・趨勢
                elif axis == "median":
                    val_per_obs = (
                        windowed.groupby("obs_id")["_sf_value"].median().to_dict()
                    )
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "best2_mean":
                    # 上位2件（速い = speed_figure 大）の平均・count>=2 で算出（D-09.1-01）。
                    # vectorized: apply+nlargest は55万 group で致命的低速（cProfile で83%占有）・
                    # sort 降順→groupby.head(2)→mean で置換（byte-reproducible・同一結果）。
                    valid_windowed = windowed[windowed["_sf_value"].notna()]
                    if len(valid_windowed) > 0:
                        top2 = (
                            valid_windowed.sort_values(
                                ["obs_id", "_sf_value"], ascending=[True, False]
                            )
                            .groupby("obs_id", sort=False).head(2)
                        )
                        val_per_obs = top2.groupby("obs_id")["_sf_value"].mean().to_dict()
                    else:
                        val_per_obs = {}
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "trend_last_minus_mean5":
                    # last(直近1件) - mean(5件)・window=5（mean5 必要・count>=5 で算出）
                    first_per_obs = windowed.groupby("obs_id", sort=False)["_sf_value"].first()
                    mean_per_obs = windowed.groupby("obs_id")["_sf_value"].mean()
                    val_per_obs = (first_per_obs - mean_per_obs).to_dict()
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                elif axis == "trend_mean3_minus_mean5":
                    # mean(直近3件) - mean(5件)・window=5（mean5 必要・count>=5 で算出）
                    mean5_per_obs = windowed.groupby("obs_id")["_sf_value"].mean()
                    # head(3): obs_id 毎に直近3件（recent_sf は race_start_datetime DESC sort 済み）
                    windowed3 = recent_sf.groupby("obs_id", sort=False).head(3)
                    mean3_per_obs = windowed3.groupby("obs_id")["_sf_value"].mean()
                    val_per_obs = (mean3_per_obs - mean5_per_obs).to_dict()
                    count_check = (
                        windowed["_sf_value"].notna()
                        .groupby(windowed["obs_id"]).sum().astype(int).to_dict()
                    )
                else:  # pragma: no cover - D-09 設計上到達不能
                    continue

                col = _speed_figure_col_name(axis, window)
                # vectorized 設定（result.at 行ごと設定は数十万行で致命的に低速化・Phase 9.1 最適化）。
                # byte-reproducibility 維持: map + np.where で axis 毎の sentinel ルールを一括適用。
                val_series = result["obs_id"].map(val_per_obs)
                if axis == "count":
                    # count 軸は常に実際 count（0〜window・D-11）・MISSING でなく数値
                    result[col] = val_series.fillna(0).astype(int)
                else:
                    count_series = (
                        result["obs_id"].map(count_check).fillna(0).astype(int)
                        if count_check is not None
                        else pd.Series([0] * len(result), index=result.index, dtype=int)
                    )
                    # sentinel threshold（axis 毎・D-09/D-09.1-01）
                    if axis == "last":
                        threshold = 1
                    elif axis == "best2_mean":
                        threshold = 2
                    else:  # mean/max/median/sd/trend_* は count>=window
                        threshold = window
                    valid = (count_series >= threshold) & val_series.notna()
                    result[col] = pd.Series(
                        np.where(valid, val_series, MISSING),
                        index=result.index, dtype=object,
                    )

            # --- NEW Phase 9.1 (D-09.1-02/03): same_surface / same_distance_bucket ---
            # recent_sf は PIT filter + head(5) 済み（LOOKBACK=5 窓）。target race と同条件の
            # 過去走のみで mean/max/count を集約。PIT 保証: recent の部分集合なので維持。
            # target surface/bucket は observations（result）の trackcd/kyori から派生
            # （_derive_surface / derive_distance_bucket・過去走と同一関数で一貫性保証）。
            # sentinel: mean/max は count>=1（同条件走が少ない・D-09.1-03 文書化）。
            # count_5 は直近5走窓での同条件走数（実際 count 0-5・D-11 信頼度軸）。
            _has_target_cond = (
                "trackcd" in result.columns
                and "kyori" in result.columns
                and "obs_id" in result.columns
                and "surface" in recent_sf.columns
                and "kyori" in recent_sf.columns
            )
            if _has_target_cond and len(recent_sf) > 0:
                tgt_surface = _derive_surface(result["trackcd"])
                tgt_bucket = derive_distance_bucket(result["kyori"])
                target_surface_map = dict(zip(
                    result["obs_id"].tolist(), tgt_surface.tolist(), strict=False
                ))
                target_bucket_map = dict(zip(
                    result["obs_id"].tolist(), tgt_bucket.tolist(), strict=False
                ))
                cond_frame = recent_sf.copy()
                cond_frame["_target_surface"] = cond_frame["obs_id"].map(target_surface_map)
                cond_frame["_target_bucket"] = cond_frame["obs_id"].map(target_bucket_map)
                cond_frame["_past_bucket"] = derive_distance_bucket(cond_frame["kyori"])
                # match mask（過去走条件 == target 条件・None/NaN は除外）
                same_surface_mask = (
                    cond_frame["surface"].notna()
                    & cond_frame["_target_surface"].notna()
                    & (cond_frame["surface"].astype(str) == cond_frame["_target_surface"].astype(str))
                )
                same_bucket_mask = (
                    cond_frame["_past_bucket"].notna()
                    & cond_frame["_target_bucket"].notna()
                    & (cond_frame["_past_bucket"].astype(str) == cond_frame["_target_bucket"].astype(str))
                )
                for cond_name, cond_mask in (
                    ("same_surface", same_surface_mask),
                    ("same_distance_bucket", same_bucket_mask),
                ):
                    matched = cond_frame[cond_mask.fillna(False)]
                    count_col = f"rolling_speed_figure_{cond_name}_count_5"
                    mean_col = f"rolling_speed_figure_{cond_name}_mean_5"
                    max_col = f"rolling_speed_figure_{cond_name}_max_5"
                    if len(matched) > 0:
                        matched_count = (
                            matched["_sf_value"].notna()
                            .groupby(matched["obs_id"]).sum().astype(int).to_dict()
                        )
                        matched_mean = matched.groupby("obs_id")["_sf_value"].mean().to_dict()
                        matched_max = matched.groupby("obs_id")["_sf_value"].max().to_dict()
                    else:
                        matched_count, matched_mean, matched_max = {}, {}, {}
                    # vectorized 設定（result.at 行ごと設定は数十万行で致命的に低速化）
                    count_series = result["obs_id"].map(matched_count).fillna(0).astype(int)
                    result[count_col] = count_series  # count_5: 常に実際同条件走数（D-11）
                    has_match = count_series >= 1
                    mean_series = result["obs_id"].map(matched_mean)
                    max_series = result["obs_id"].map(matched_max)
                    # count>=1 で算出（D-09.1-03）・未満 or NaN は MISSING
                    mean_valid = has_match & mean_series.notna()
                    max_valid = has_match & max_series.notna()
                    result[mean_col] = pd.Series(
                        np.where(mean_valid, mean_series, MISSING),
                        index=result.index, dtype=object,
                    )
                    result[max_col] = pd.Series(
                        np.where(max_valid, max_series, MISSING),
                        index=result.index, dtype=object,
                    )
            continue

        is_categorical = system in _CATEGORICAL_SYSTEMS

        if is_categorical:
            # categorical 系統: source 列の生値（文字列）を集約対象にする・to_numeric しない。
            # 欠損/NaN/None は有効値扱いから除外するため mask で管理。
            raw_series = recent[system].astype(object)
            recent_sys = recent.assign(_sys_value=raw_series)
            # count: 欠損（None/NaN/空文字）を除外した有効値数
            valid_mask = recent_sys["_sys_value"].notna() & (
                recent_sys["_sys_value"].astype(str).str.strip() != ""
            )
            count_per_obs = (
                valid_mask.groupby(recent_sys["obs_id"]).sum().astype(int).to_dict()
            )
            # mode: 各 obs_id 毎の最頻値（同数の場合先頭・pandas mode は昇順値で最初を返す）。
            # vector 形: groupby + agg で各 group の mode.iloc[0] を取得（apply 廃止・WR-03 対称）。
            mode_per_obs: dict[Any, object] = {}
            latest_per_obs_cat: dict[Any, object] = {}
            for obs_id, group in recent_sys.groupby("obs_id", sort=False):
                gv = group["_sys_value"].dropna()
                gv = gv[gv.astype(str).str.strip() != ""]
                if len(gv) == 0:
                    continue
                # mode: 最頻値（同票の場合値昇順で最小・決定論的）。複数ある場合 .iloc[0]。
                modes = gv.astype(str).mode()
                mode_per_obs[obs_id] = modes.iloc[0] if len(modes) > 0 else MISSING
                # latest: sort 済みなので first が最新（race_start_datetime DESC）
                latest_per_obs_cat[obs_id] = str(gv.iloc[0])

            for idx, obs_id in zip(result.index, result["obs_id"], strict=False):
                n = count_per_obs.get(obs_id, 0)
                mode_col = f"rolling_{system}_mode_5"
                latest_col = f"rolling_{system}_latest_5"
                count_col = f"rolling_{system}_count_5"

                result.at[idx, count_col] = n
                if n == 0:
                    result.at[idx, mode_col] = MISSING
                    result.at[idx, latest_col] = MISSING
                else:
                    result.at[idx, mode_col] = mode_per_obs.get(obs_id, MISSING)
                    result.at[idx, latest_col] = latest_per_obs_cat.get(obs_id, MISSING)
            continue

        # --- numeric 系統（既存ロジック） ---
        if system == "jyuni3c_jyuni4c":
            # 合成系統: jyuni3c と jyuni4c の平均（両方必要・片方欠損なら当該走は除外）
            j3 = pd.to_numeric(recent["jyuni3c"], errors="coerce")
            j4 = pd.to_numeric(recent["jyuni4c"], errors="coerce")
            sys_values = (j3 + j4) / 2.0
            recent_sys = recent.assign(_sys_value=sys_values)
        else:
            recent_sys = recent.assign(
                _sys_value=pd.to_numeric(recent[system], errors="coerce")
            )

        # count: non-NaN の走数（何走分で集約したか）
        # WR-03 (Phase 3.1 advisory hardening): groupby().apply(lambda) を vector 形に置換
        # （pandas 3.x 推奨・apply 廃止・Pitfall 4 SHA256 drift 対策・同一入力で count 値完全一致）。
        count_per_obs = (
            recent_sys["_sys_value"].notna()
            .groupby(recent_sys["obs_id"]).sum().astype(int).to_dict()
        )

        mean_per_obs = (
            recent_sys.groupby("obs_id")["_sys_value"].mean().to_dict()
        )
        # latest: race_start_datetime 最新の1件（sort 済みなので groupby().first で OK）
        latest_per_obs = (
            recent_sys.groupby("obs_id", sort=False)["_sys_value"].first().to_dict()
        )
        # sd: n<2 は定義不能（pandas std が NaN になるのを sentinel で明示・Pitfall 3.3）
        sd_per_obs = (
            recent_sys.groupby("obs_id")["_sys_value"].std(ddof=1).to_dict()
        )

        for idx, obs_id in zip(result.index, result["obs_id"], strict=False):
            n = count_per_obs.get(obs_id, 0)
            mean_col = f"rolling_{system}_mean_5"
            latest_col = f"rolling_{system}_latest_5"
            sd_col = f"rolling_{system}_sd_5"
            count_col = f"rolling_{system}_count_5"

            result.at[idx, count_col] = n

            if n == 0:
                # 新馬: 3軸とも __MISSING__（D-13・Pitfall 3.3）
                result.at[idx, mean_col] = MISSING
                result.at[idx, latest_col] = MISSING
                result.at[idx, sd_col] = MISSING
            else:
                m = mean_per_obs.get(obs_id)
                result.at[idx, mean_col] = m if pd.notna(m) else MISSING
                lt = latest_per_obs.get(obs_id)
                result.at[idx, latest_col] = lt if pd.notna(lt) else MISSING
                # sd は n<2 で定義不能 → sentinel（silent NaN fill 禁止）
                if n < 2:
                    result.at[idx, sd_col] = MISSING
                else:
                    sd = sd_per_obs.get(obs_id)
                    result.at[idx, sd_col] = sd if pd.notna(sd) else MISSING

    return result
