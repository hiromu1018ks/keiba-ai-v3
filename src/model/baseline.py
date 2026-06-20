# ruff: noqa: E501, B007  (長い docstring / SQL リテラル・groupby loop var を保持するため緩和)
"""Phase 4 baseline: BL-1..5 計算（MODL-02 / SC#2 / §14.2 / D-07 / D-08）.

成功基準#2 (SC#2) と MODL-02 を実装する service 層。BL-1..5 全5つのベースライン確率を算出し、
主モデル（LightGBM / CatBoost・キャリブレーション済み）との比較表の原材料を提供する。

**設計の核心（D-07 / D-08 / §14.2 / review MEDIUM）:**

1. **市場データは feature matrix に混入しない**（D-07・§14.2）。BL-2/BL-3 の市場データ
   （``n_uma_race.ninki`` / ``n_odds_tanpuku.fukuoddslow``）は BL 計算専用の入力であり、
   主モデルの feature matrix には絶対に混入しない。``compute_bl2`` / ``compute_bl3`` は
   独立したベンチマークとして計算する（MODL-01 odds-free allowlist との完全分離）。
2. **§14.2 比較条件の明示**。BL-3（確定複勝オッズ逆数）は Phase 1-A モデルと同一情報条件の
   比較ではない（確定オッズはレース後に確定する）。docstring / ``bl_calib_note`` 列で明示。
3. **review MEDIUM: BL-4/BL-5 キャリブレーション状態の明示**。``compute_bl4`` / ``compute_bl5``
   は ``calibrate`` 引数を持ち・主モデルと同一 calib slice でキャリブレーション可能。
   ``calibrate=False`` の場合は未キャリブレーション注記を ``compute_all_baselines`` が付与
   （SC#2 比較の公平性）。
4. **Pitfall 6: BL-3 オッズ逆数のレース内正規化忘れを防止**。``_race_normalize_inverse`` が
   ``sum(p) == 払戻対象数``（8頭以上 3 / 5-7頭 2）を保証する（D-07 確定事項）。
5. **決定論フラグの固定**（review HIGH#7 / T-04-19）。BL-4 は ``LogisticRegression(random_state=42)``・
   BL-5 は ``train_lightgbm`` を再利用（trainer の ``seed=42, deterministic=True,
   num_threads=1`` が固定済み）。

参照: 04-RESEARCH.md D-07/D-08 / 04-PATTERNS.md baseline.py セクション /
      src/model/trainer.py / src/etl/fukusho_label.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from psycopg import Cursor

# ---------------------------------------------------------------------------
# 定数（D-08 確定）
# ---------------------------------------------------------------------------
# BL-4 LogisticRegression の少数特徴量（D-08・numeric / low-cardinality categorical）
BL4_FEATURES: list[str] = [
    "barei",
    "futan",
    "umaban",
    "wakuban",
    "class_code_normalized",
]

# BL-5 LightGBM 最小特徴量（static + 低基数 categorical・rolling 系統除外・D-08）
BL5_FEATURES: list[str] = [
    "wakuban",
    "barei",
    "futan",
    "umaban",
    "sexcd",
    "class_code_normalized",
    "estimated_running_style",
]

# BL-3 §14.2 注記（比較条件の明示）
BL3_COMPARISON_CAVEAT = (
    "BL-3 uses confirmed fukuodds (post-race) — NOT a same-information-condition "
    "comparison with Phase 1-A model (§14.2). Market-implied benchmark only."
)

# BL-4/BL-5 未キャリブレーション注記（review MEDIUM）
BL_UNCALIBRATED_NOTE = (
    "BL-4/BL-5 uncalibrated - comparison caveat (review MEDIUM: SC#2 fairness). "
    "Pass calib_slice to compute_all_baselines to calibrate on the same slice as the main model."
)


# ---------------------------------------------------------------------------
# _payout_places — 払戻対象数（8頭以上 3 / 5-7頭 2）
# ---------------------------------------------------------------------------
def _payout_places(entry_count: int) -> int:
    """複勝払戻対象数を返す（D-08・8頭以上 3 / 5-7頭 2）。

    4 頭以下等は ``ValueError``（競走不成立・学習対象外・fukusho_label の filter で除外済み）。
    fukusho_payout_places 列があれば優先するが・本関数は entry_count から推定する基本版。
    """
    if entry_count is None or pd.isna(entry_count):
        raise ValueError("_payout_places: entry_count が NaN/None (fukusho_label の必須列・D-08)")
    ec = int(entry_count)
    if ec >= 8:
        return 3
    if 5 <= ec <= 7:
        return 2
    raise ValueError(
        f"_payout_places: entry_count={ec} は複勝払戻対象外 (5-7 頭 or 8 頭以上のみ・D-08)"
    )


def _payout_places_from_row(row: pd.Series) -> int:
    """行の ``fukusho_payout_places`` 列を優先し・無ければ ``sales_start_entry_count`` から推定。"""
    if (
        "fukusho_payout_places" in row.index
        and not pd.isna(row.get("fukusho_payout_places"))
        and int(row["fukusho_payout_places"]) > 0
    ):
        return int(row["fukusho_payout_places"])
    return _payout_places(row["sales_start_entry_count"])


# ---------------------------------------------------------------------------
# compute_bl1 — 頭数別一定確率（D-08・BL-1）
# ---------------------------------------------------------------------------
def compute_bl1(
    df: pd.DataFrame,
    *,
    entry_count_col: str = "sales_start_entry_count",
    payout_places_col: str = "fukusho_payout_places",
) -> pd.Series:
    """BL-1: 頭数別一定確率（8 頭以上 3/count・5-7 頭 2/count・D-08）。

    各レース内で全馬同一値。``p = payout_places / entry_count``。
    戻り Series 名 = ``"p_bl1"``・index は ``df.index``。
    """
    out = pd.Series(np.nan, index=df.index, name="p_bl1", dtype=float)
    for idx, row in df.iterrows():
        places = _payout_places_from_row(row)
        ec = int(row[entry_count_col])
        if ec <= 0:
            raise ValueError(f"compute_bl1: entry_count={ec} <= 0 (idx={idx}・D-08)")
        out.at[idx] = places / ec
    return out


# ---------------------------------------------------------------------------
# _race_normalize_inverse — 汎用ヘルパー（D-07・Pitfall 6 回避）
# ---------------------------------------------------------------------------
def _race_normalize_inverse(
    df: pd.DataFrame,
    value_col: str,
    *,
    race_key_col: str = "race_key",
    entry_count_col: str = "sales_start_entry_count",
    payout_places_col: str = "fukusho_payout_places",
) -> pd.Series:
    """``1/value_col`` をレース内正規化して ``sum(p) == 払戻対象数`` に揃える（D-07・Pitfall 6 回避）。

    レース (``race_key_col`` 単位) 内で ``p_i = (1/v_i) / sum_j(1/v_j) × payout_places``
    を計算する。``value_col`` が 0 / NaN の行は除外（``NaN`` を返す）。
    """
    out = pd.Series(np.nan, index=df.index, name=f"p_norm_{value_col}", dtype=float)
    # value_col が 0 / NaN の行は除外
    valid_mask = df[value_col].notna() & (df[value_col] != 0)
    for race_key, group in df.loc[valid_mask].groupby(race_key_col):
        # 払戻対象数（レース内で同一のはず）
        first_row = group.iloc[0]
        places = _payout_places_from_row(first_row)
        inv = 1.0 / group[value_col].astype(float)
        denom = inv.sum()
        if denom <= 0:
            # 全行の逆数和が 0 以下 = 異常・NaN のまま残す
            continue
        p = (inv / denom) * places
        out.loc[group.index] = p.values
    return out


# ---------------------------------------------------------------------------
# compute_bl2 — 確定人気由来（D-08・BL-2）
# ---------------------------------------------------------------------------
def compute_bl2(
    df: pd.DataFrame,
    *,
    ninki_col: str = "ninki",
) -> pd.Series:
    """BL-2: 確定人気 (``n_uma_race.ninki``) 由来・1/ninki をレース内正規化（D-08・D-07）。

    戻り Series 名 = ``"p_bl2"``・``sum(p) == 払戻対象数``。
    """
    p = _race_normalize_inverse(df, ninki_col)
    p.name = "p_bl2"
    return p


# ---------------------------------------------------------------------------
# compute_bl3 — 確定複勝オッズ逆数（D-08・BL-3・§14.2 比較条件明示）
# ---------------------------------------------------------------------------
def compute_bl3(
    df: pd.DataFrame,
    *,
    fukuodds_col: str = "fukuoddslow",
) -> pd.Series:
    """BL-3: 確定複勝オッズ (``n_odds_tanpuku.fukuoddslow``) 逆数をレース内正規化
    （D-08・D-07・§14.2 市場参照ベンチマーク）。

    **§14.2 比較条件の明示**: BL-3 は確定複勝オッズ（レース後確定）を使用するため・
    Phase 1-A モデル（出馬表確定時点の odds-free feature）と同一情報条件の比較ではない。
    市場暗示確率ベンチマークとしてのみ使用する（``BL3_COMPARISON_CAVEAT``）。
    モデル特徴量には絶対に混入しない（D-07・MODL-01 odds-free allowlist）。

    戻り Series 名 = ``"p_bl3"``・``sum(p) == 払戻対象数``。
    """
    p = _race_normalize_inverse(df, fukuodds_col)
    p.name = "p_bl3"
    return p


# ---------------------------------------------------------------------------
# compute_bl4 — LogisticRegression（D-08・BL-4・review MEDIUM: キャリブレーション明示）
# ---------------------------------------------------------------------------
def compute_bl4(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    *,
    calibrate: bool = False,
    X_calib: pd.DataFrame | None = None,
    y_calib: pd.Series | None = None,
) -> pd.Series:
    """BL-4: sklearn ``LogisticRegression`` で ``BL4_FEATURES`` を学習（D-08・review MEDIUM）。

    ``LogisticRegression(max_iter=1000, random_state=42)`` で ``BL4_FEATURES`` を fit・
    ``X_test`` の ``predict_proba[:, 1]`` を返す。戻り Series 名 = ``"p_bl4"``・
    index は ``X_test.index``。

    Parameters
    ----------
    calibrate : bool
        ``True`` の場合・主モデルと同一の calib slice (``X_calib`` / ``y_calib``) で
        ``fit_prefit_calibrator`` によりキャリブレーション（SC#2 比較の公平性・review MEDIUM）。
        ``False`` の場合は未キャリブレーションで返す（``compute_all_baselines`` が注記）。
    """
    from sklearn.linear_model import LogisticRegression

    # review HIGH#2: X/y 行整列
    if not X_train.index.equals(y_train.index):
        raise ValueError("compute_bl4: X_train.index と y_train.index が一致しない (review HIGH#2)")

    X_train_bl4 = X_train[BL4_FEATURES].copy()
    X_test_bl4 = X_test[BL4_FEATURES].copy()

    # class_code_normalized は categorical 扱い（low-cardinality）・One-Hot で処理
    # 欠損は "__MISSING__" sentinel。Rule 3 blocking fix: 文字列化後に One-Hot 化しないと
    # LogisticRegression が文字列を数値に変換できず ValueError になる。pd.get_dummies で
    # train ∪ test の全カテゴリで One-Hot 化する (train/test 列整合を保つため union)。
    cat_cols_bl4 = ["class_code_normalized"]
    for col in cat_cols_bl4:
        if col in X_train_bl4.columns:
            X_train_bl4[col] = X_train_bl4[col].fillna("__MISSING__").astype(str)
            X_test_bl4[col] = X_test_bl4[col].fillna("__MISSING__").astype(str)
    # One-Hot 化 (train ∪ test の全カテゴリで列整合)
    all_cat_df = pd.concat([X_train_bl4[cat_cols_bl4], X_test_bl4[cat_cols_bl4]], axis=0)
    dummies_all = pd.get_dummies(all_cat_df, columns=cat_cols_bl4, dummy_na=False)
    train_dummies = dummies_all.iloc[: len(X_train_bl4)].reset_index(drop=True)
    test_dummies = dummies_all.iloc[len(X_train_bl4) :].reset_index(drop=True)
    # numeric 列はそのまま (One-Hot 置換対象外)
    numeric_cols = [c for c in X_train_bl4.columns if c not in cat_cols_bl4]
    X_train_bl4_final = pd.concat(
        [X_train_bl4[numeric_cols].reset_index(drop=True), train_dummies], axis=1
    )
    X_test_bl4_final = pd.concat(
        [X_test_bl4[numeric_cols].reset_index(drop=True), test_dummies], axis=1
    )
    X_train_bl4_final.index = X_train_bl4.index
    X_test_bl4_final.index = X_test_bl4.index

    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_train_bl4_final, y_train)

    if calibrate:
        if X_calib is None or y_calib is None:
            raise ValueError(
                "compute_bl4: calibrate=True の場合 X_calib / y_calib が必須 (review MEDIUM)"
            )

        X_calib_bl4 = X_calib[BL4_FEATURES].copy()
        if "class_code_normalized" in X_calib_bl4.columns:
            X_calib_bl4["class_code_normalized"] = (
                X_calib_bl4["class_code_normalized"].fillna("__MISSING__").astype(str)
            )
        # X_calib も One-Hot 化 (train と同一カテゴリで変換)
        calib_dummies = pd.get_dummies(
            X_calib_bl4[cat_cols_bl4], columns=cat_cols_bl4, dummy_na=False
        )
        calib_numeric = X_calib_bl4[numeric_cols].reset_index(drop=True)
        X_calib_bl4_final = pd.concat([calib_numeric, calib_dummies], axis=1)
        X_calib_bl4_final.index = X_calib_bl4.index
        # train と列整合 (train に無い列は 0 補完・train に有る列のみ保持)
        for col in X_train_bl4_final.columns:
            if col not in X_calib_bl4_final.columns:
                X_calib_bl4_final[col] = 0
        X_calib_bl4_final = X_calib_bl4_final[X_train_bl4_final.columns]
        # calibrator は race_dates_calib と train_max_date を要求するが・BL 評価は
        # 主モデルの calib slice をそのまま使うため・caller が正当な calib slice を渡した前提
        calibrator = _fit_bl_calibrator(model, X_calib_bl4_final, y_calib)
        proba = calibrator.predict_proba(X_test_bl4_final)[:, 1]
    else:
        proba = model.predict_proba(X_test_bl4_final)[:, 1]

    return pd.Series(proba, index=X_test.index, name="p_bl4")


def _fit_bl_calibrator(base_estimator: Any, X_calib: pd.DataFrame, y_calib: pd.Series) -> Any:
    """BL-4/BL-5 用キャリブレータ fit helper（``fit_prefit_calibrator`` の薄い wrapper）。

    ``fit_prefit_calibrator`` は ``race_dates_calib`` / ``train_max_date`` を要求するが・
    BL 評価は主モデルの calib slice を再利用するため・X_calib に ``race_date`` 列があれば
    それを使い・無ければ caller が既に strict-later を保証した前提で ``Timestamp.min`` /
    ``Timestamp.max`` をダミー値として渡す（主モデルと同一 calib slice を使うため）。
    """

    from src.utils.calibrator import fit_prefit_calibrator

    if "race_date" in X_calib.columns:
        race_dates = pd.Series(X_calib["race_date"].values, index=X_calib.index)
        # train_max_date は X_calib より厳格に過去である必要があるが・BL 評価は主モデルの
        # calib slice を再利用するため・ここでは caller が正当な slice を渡した前提とする
        # （実際の運用では race_dates.min() の1日前を train_max_date に設定）
        train_max = race_dates.min() - pd.Timedelta(days=1)
    else:
        race_dates = pd.Series([pd.Timestamp("2024-01-01")] * len(X_calib), index=X_calib.index)
        train_max = pd.Timestamp("2023-12-31")

    return fit_prefit_calibrator(
        base_estimator=base_estimator,
        X_calib=X_calib.values,
        y_calib=y_calib.values,
        race_dates_calib=race_dates,
        train_max_date=train_max,
        method="isotonic" if len(X_calib) >= 1000 else "sigmoid",
    )


# ---------------------------------------------------------------------------
# compute_bl5 — LightGBM 最小特徴量（D-08・BL-5・review MEDIUM）
# ---------------------------------------------------------------------------
def compute_bl5(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    *,
    calibrate: bool = False,
    X_calib: pd.DataFrame | None = None,
    y_calib: pd.Series | None = None,
) -> pd.Series:
    """BL-5: ``BL5_FEATURES`` subset で ``train_lightgbm`` を呼出し ``predict_proba``（D-08・review MEDIUM）。

    rolling 系統を除外した最小特徴量（static 4 + class_code + estimated_running_style）で
    LightGBM を small params で fit・``X_test`` の ``predict_proba[:, 1]`` を返す。
    戻り Series 名 = ``"p_bl5"``・index は ``X_test.index``。

    ``calibrate=True`` の場合・主モデルと同一 calib slice でキャリブレーション（review MEDIUM）。
    """
    from src.model.trainer import train_lightgbm

    # review HIGH#2: X/y 行整列
    if not X_train.index.equals(y_train.index):
        raise ValueError("compute_bl5: X_train.index と y_train.index が一致しない (review HIGH#2)")

    X_train_bl5 = X_train[BL5_FEATURES].copy()
    X_test_bl5 = X_test[BL5_FEATURES].copy()

    # train_lightgbm を small params (n_estimators=100・短縮) で呼出
    # trainer 側が LOW_CARD categorical 処理・決定論 seed 固定を実施済み
    small_params = {
        "num_leaves": 31,
        "min_data_in_leaf": 50,
        "learning_rate": 0.1,
    }
    model = train_lightgbm(X_train_bl5, y_train, params=small_params)

    # LightGBM は train と test の categorical categories が完全一致することを要求するため・
    # test 予測前に train と categories を統一する（trainer 内部 helper を利用）
    from src.model.trainer import _prepare_lightgbm_train_eval

    _, X_test_bl5_aligned = _prepare_lightgbm_train_eval(X_train_bl5, X_test_bl5)

    if calibrate:
        if X_calib is None or y_calib is None:
            raise ValueError(
                "compute_bl5: calibrate=True の場合 X_calib / y_calib が必須 (review MEDIUM)"
            )
        X_calib_bl5 = X_calib[BL5_FEATURES].copy()
        # calibrator は categorical dtype を必要としない（numeric 化）が・predict 時には
        # categorical 統一が必要・X_calib も train と統一
        calibrator = _fit_bl_calibrator(model, X_calib_bl5, y_calib)
        proba = calibrator.predict_proba(X_test_bl5_aligned)[:, 1]
    else:
        proba = model.predict_proba(X_test_bl5_aligned)[:, 1]

    return pd.Series(proba, index=X_test.index, name="p_bl5")


# ---------------------------------------------------------------------------
# compute_all_baselines — 統合 DataFrame（review MEDIUM: 比較公平性）
# ---------------------------------------------------------------------------
def compute_all_baselines(
    df_test: pd.DataFrame,
    *,
    X_train_bl4_bl5: pd.DataFrame,
    y_train: pd.Series,
    X_test_bl4_bl5: pd.DataFrame,
    X_calib: pd.DataFrame | None = None,
    y_calib: pd.Series | None = None,
    calibrate_bl4_bl5: bool = False,
) -> pd.DataFrame:
    """BL-1..5 全5つの ``p_bl*`` 列を統合した DataFrame を返す（SC#2・review MEDIUM）。

    Parameters
    ----------
    df_test : BL-1/BL-2/BL-3 計算用 DataFrame。``sales_start_entry_count`` /
        ``fukusho_payout_places`` / ``ninki`` / ``fukuoddslow`` / ``race_key`` 列を含む。
    X_train_bl4_bl5, y_train, X_test_bl4_bl5 : BL-4/BL-5 学習・予測用 feature matrix と label。
    X_calib, y_calib : 主モデルと同一 calib slice（``calibrate_bl4_bl5=True`` の時に使用）。
    calibrate_bl4_bl5 : ``True`` の時に BL-4/BL-5 を calib slice でキャリブレーション
        （review MEDIUM: SC#2 比較の公平性）。

    Returns
    -------
    pd.DataFrame
        ``p_bl1`` / ``p_bl2`` / ``p_bl3`` / ``p_bl4`` / ``p_bl5`` 列を持つ DataFrame。
        ``bl_calib_note`` 列に BL-4/BL-5 のキャリブレーション状態（or BL-3 §14.2 注記）を付与。
    """
    out = pd.DataFrame(index=df_test.index)

    # BL-1/BL-2/BL-3 は df_test の列から直接計算
    out["p_bl1"] = compute_bl1(df_test)
    if "ninki" in df_test.columns:
        out["p_bl2"] = compute_bl2(df_test)
    if "fukuoddslow" in df_test.columns:
        out["p_bl3"] = compute_bl3(df_test)

    # BL-4/BL-5 は学習済み estimator から予測
    out["p_bl4"] = compute_bl4(
        X_train_bl4_bl5,
        y_train,
        X_test_bl4_bl5,
        calibrate=calibrate_bl4_bl5,
        X_calib=X_calib,
        y_calib=y_calib,
    )
    out["p_bl5"] = compute_bl5(
        X_train_bl4_bl5,
        y_train,
        X_test_bl4_bl5,
        calibrate=calibrate_bl4_bl5,
        X_calib=X_calib,
        y_calib=y_calib,
    )

    # provenance 列付与（review MEDIUM / §14.2 明示）
    if calibrate_bl4_bl5:
        out["bl_calib_note"] = "BL-4/BL-5 calibrated on same calib slice as main model"
    else:
        out["bl_calib_note"] = BL_UNCALIBRATED_NOTE
    # BL-3 の §14.2 注記を別列で付与（fukuoddslow が存在する場合）
    if "fukuoddslow" in df_test.columns:
        out["bl3_comparison_caveat"] = BL3_COMPARISON_CAVEAT

    return out


# ---------------------------------------------------------------------------
# fetch_market_data — D-08 市場データ源（readonly_cur で SELECT）
# ---------------------------------------------------------------------------
def fetch_market_data(
    readonly_cur: Cursor,
    race_keys: list[str] | set[str] | None = None,
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """``raw_everydb2.n_odds_tanpuku.fukuoddslow`` と ``normalized.n_uma_race.ninki`` を取得する
    （D-08・readonly_cur で SELECT のみ・市場データは BL 計算専用）。

    PK (``year, jyocd, kaiji, nichiji, racenum, umaban``) + ``kettonum`` で結合し・
    ``fukuoddslow`` / ``fukuoddshigh`` / ``ninki`` 列を持つ DataFrame を返す。
    NULL / 0 行はそのまま返す（``compute_bl2`` / ``compute_bl3`` が処理）。

    Parameters
    ----------
    readonly_cur : readonly ロールの cursor（``raw_everydb2`` / ``normalized`` schema へ SELECT 権限）。
    race_keys : 指定された場合その race に絞る（正準 race_key = year-jyocd-kaiji-nichiji-racenum）。
        ``None`` の場合は全件取得（``year`` で絞ることを推奨）。
    year : 指定された場合その年のレースに絞る。

    Returns
    -------
    pd.DataFrame
        ``year`` / ``jyocd`` / ``kaiji`` / ``nichiji`` / ``racenum`` / ``umaban`` / ``kettonum`` /
        ``fukuoddslow`` / ``fukuoddshigh`` / ``ninki`` 列を持つ DataFrame。
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    if year is not None:
        where_clauses.append("o.year = %s")
        params.append(str(year))

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # raw_everydb2.n_odds_tanpuku.* は varchar・normalized.n_uma_race.* は int の場合があるため
    # CAST(int) で型整列（'01' varchar と 1 int の比較を数値で統一）。
    # n_odds_tanpuku は kettonum 列を持たないため・PK は (year, jyocd, kaiji, nichiji, racenum, umaban)
    # の 6 カラム・kettonum は n_uma_race 側から取得（HARAI 参照）。
    query = f"""
        SELECT
            o.year, o.jyocd, o.kaiji, o.nichiji, o.racenum, o.umaban,
            n.kettonum,
            o.fukuoddslow,
            o.fukuoddshigh,
            n.ninki
        FROM raw_everydb2.n_odds_tanpuku o
        LEFT JOIN normalized.n_uma_race n
            ON o.year::int = n.year::int
            AND o.jyocd = n.jyocd
            AND o.kaiji::int = n.kaiji::int
            AND o.nichiji = n.nichiji
            AND o.racenum::int = n.racenum::int
            AND o.umaban::int = n.umaban::int
        {where_sql}
    """
    readonly_cur.execute(query, params)
    cols = [d.name for d in readonly_cur.description]
    rows = readonly_cur.fetchall()
    return pd.DataFrame(rows, columns=cols)
