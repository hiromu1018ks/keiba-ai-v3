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

from src.features.availability import CUTOFF_SEMANTICS
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
}

# CR-02 (03-REVIEW): ``jyocd`` は JRA 競馬場コード（"01"=札幌, "05"=東京 等）の
# **カテゴリカル varchar(2)** であり、数値 mean/sd を取ると「平均競馬場コード = 5.8」の
# ような意味をなさない数値が生まれる。jyocd は categorical 系統として扱い、mean/sd で
# なく最頻値(mode)と直近値(latest)のみを算出する。
# 当日 jyocd は静的属性（feature_availability.yaml 別エントリ・本系統は「過去走の競馬場分布」
# を表現）。latest は「直近の競馬場」で意味論的に妥当なので保持・mean/sd は廃止。
_CATEGORICAL_SYSTEMS: frozenset[str] = frozenset({"jyocd"})

# 系統毎の出力 axis セット（mean/latest/sd/count または mode/latest/count）。
def _axes_for(system: str) -> tuple[str, ...]:
    """系統が出力すべき axis タプルを返す（categorical は mode/latest/count）。"""
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
    rolling_cols: list[str] = []
    for system in _ROLLING_SYSTEMS:
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

    # --- Step 1b: expanded history（各 observation に kettonum で inner-join） ---
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
    history_filtered = expanded[
        expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]
    ].copy()

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
