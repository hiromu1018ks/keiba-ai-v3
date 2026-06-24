"""Phase 4 MODL-02/SC#2 BL-1..5 検証契約 (PLAN 03 GREEN 化).

検証内容:
- BL-1: 頭数別一定 (8頭以上 3/count・5-7頭 2/count)・境界 (7→8) で閾値切替
- BL-2: 確定人気 1/ninki レース内正規化・sum(p) == 払戻対象数
- BL-3: 確定複勝オッズ逆数 1/fukuoddslow レース内正規化・sum(p) == 払戻対象数
  (§14.2 比較条件明示・市場データは feature に混入しない)
- BL-4: LogisticRegression(max_iter=1000, random_state=42) で BL4_FEATURES 学習
- BL-5: train_lightgbm を BL5_FEATURES subset で呼出
- D-08: n_odds_tanpuku.fukuoddslow / n_uma_race.ninki が readonly_cur で SELECT 可能

参考: 04-RESEARCH.md D-07/D-08 / §14.2 BL-1..5 定義.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model.baseline import (
    BL3_COMPARISON_CAVEAT,
    BL4_FEATURES,
    BL5_FEATURES,
    BL_UNCALIBRATED_NOTE,
    _payout_places,
    _race_normalize_inverse,
    compute_all_baselines,
    compute_bl1,
    compute_bl2,
    compute_bl3,
    compute_bl4,
    compute_bl5,
    fetch_market_data,
)


# ---------------------------------------------------------------------------
# helper: 合成 BL 評価用 DataFrame（race 単位・8 頭立て）
# ---------------------------------------------------------------------------
def _build_bl_test_df(
    n_races: int = 5,
    *,
    entry_count: int = 8,
    seed: int = 42,
) -> pd.DataFrame:
    """BL-1/BL-2/BL-3 計算用の合成 DataFrame を構築する。

    ``sales_start_entry_count`` / ``fukusho_payout_places`` / ``ninki`` / ``fukuoddslow`` /
    ``race_key`` 列を持つ。各レース ``entry_count`` 頭立て。
    """
    rng = np.random.default_rng(seed)
    places = _payout_places(entry_count)
    rows = []
    for race_i in range(n_races):
        race_key = f"2024-05-{race_i + 1:02d}-01-{race_i + 1}"
        for umaban in range(1, entry_count + 1):
            rows.append({
                "race_key": race_key,
                "year": 2024,
                "jyocd": "05",
                "kaiji": race_i + 1,
                "nichiji": "01",
                "racenum": race_i + 1,
                "umaban": umaban,
                "kettonum": 1000 + race_i * 100 + umaban,
                "sales_start_entry_count": entry_count,
                "fukusho_payout_places": places,
                # ninki: 1..entry_count の人気順位
                "ninki": umaban,
                # fukuoddslow: 1.0..N のオッズ（人気順に低い）
                "fukuoddslow": 1.0 + 0.3 * (umaban - 1),
                # BL-4/BL-5 用 feature
                "barei": int(rng.integers(2, 9)),
                "futan": int(rng.integers(48, 58)),
                "wakuban": int(rng.integers(1, 9)),
                "class_code_normalized": str(int(rng.choice([703, 701, 5, 10, 999]))),
                "sexcd": str(int(rng.choice([1, 2, 3]))),
                "estimated_running_style": str(int(rng.choice([1, 2, 3, 4, 5]))),
                "fukusho_hit_validated": int(rng.random() < 0.3),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: test_bl1_field_size_constant
# ---------------------------------------------------------------------------
def test_bl1_field_size_constant():
    """BL-1 頭数別一定確率: 8頭以上 3/count・5-7頭 2/count・境界 (7→8) で閾値切替。"""
    # 8 頭立て: 3/8 = 0.375
    df8 = _build_bl_test_df(n_races=3, entry_count=8, seed=1)
    p_bl1_8 = compute_bl1(df8)
    assert p_bl1_8.name == "p_bl1"
    # 各レース内で全馬同一値
    for race_key, group in df8.groupby("race_key"):
        race_p = p_bl1_8.loc[group.index]
        assert race_p.nunique() == 1, f"BL-1 がレース {race_key} 内で同一値でない"
        assert abs(race_p.iloc[0] - 3.0 / 8.0) < 1e-12, (
            f"BL-1 (8 頭) が 3/8 でない (got {race_p.iloc[0]})"
        )

    # 5 頭立て: 2/5 = 0.4
    df5 = _build_bl_test_df(n_races=2, entry_count=5, seed=2)
    p_bl1_5 = compute_bl1(df5)
    for race_key, group in df5.groupby("race_key"):
        race_p = p_bl1_5.loc[group.index]
        assert abs(race_p.iloc[0] - 2.0 / 5.0) < 1e-12, (
            f"BL-1 (5 頭) が 2/5 でない (got {race_p.iloc[0]})"
        )

    # 境界値: 7 頭 → 2/7・8 頭 → 3/8
    df7 = _build_bl_test_df(n_races=1, entry_count=7, seed=3)
    p_bl1_7 = compute_bl1(df7)
    assert abs(p_bl1_7.iloc[0] - 2.0 / 7.0) < 1e-12

    # p_i in [0, 1]
    assert (p_bl1_8 >= 0).all() and (p_bl1_8 <= 1).all()


# ---------------------------------------------------------------------------
# Test 2: test_bl2_ninki_normalized
# ---------------------------------------------------------------------------
def test_bl2_ninki_normalized():
    """BL-2 確定人気由来: 1/ninki をレース内正規化して sum=払戻対象数 (D-07/D-08)。

    注: BL-2 の ``p_i`` は「払戻対象枠のシェア」であり厳密な確率ではない。1 番人気馬が
    払戻対象枠を複数取る可能性があるため ``p_i > 1`` となり得る（これは正規化の定義上正しい）。
    """
    df = _build_bl_test_df(n_races=4, entry_count=8, seed=11)
    p_bl2 = compute_bl2(df)
    assert p_bl2.name == "p_bl2"
    # レース内で sum(p) == 払戻対象数 (8 頭 → 3)
    for race_key, group in df.groupby("race_key"):
        race_p = p_bl2.loc[group.index]
        s = race_p.sum()
        assert abs(s - 3.0) < 1e-9, (
            f"BL-2 sum(p) が払戻対象数 (3) でない (race={race_key} sum={s:.6f}・Pitfall 6)"
        )
    # p_i >= 0（払戻対象シェアは非負）
    valid_mask = p_bl2.notna()
    assert (p_bl2[valid_mask] >= 0).all()


# ---------------------------------------------------------------------------
# Test 3: test_bl3_fukuodds_inverse_normalized
# ---------------------------------------------------------------------------
def test_bl3_fukuodds_inverse_normalized():
    """BL-3 確定複勝オッズ逆数: 1/fukuoddslow をレース内正規化 (D-07・§14.2 市場参照ベンチマーク)。

    注: BL-3 の ``p_i`` も「払戻対象枠のシェア」であり・BL-2 と同様に ``p_i > 1`` となり得る。
    """
    df = _build_bl_test_df(n_races=4, entry_count=8, seed=21)
    p_bl3 = compute_bl3(df)
    assert p_bl3.name == "p_bl3"
    # レース内で sum(p) == 払戻対象数
    for race_key, group in df.groupby("race_key"):
        race_p = p_bl3.loc[group.index]
        s = race_p.sum()
        assert abs(s - 3.0) < 1e-9, (
            f"BL-3 sum(p) が払戻対象数 (3) でない (race={race_key} sum={s:.6f}・Pitfall 6)"
        )
    # p_i >= 0
    valid_mask = p_bl3.notna()
    assert (p_bl3[valid_mask] >= 0).all()

    # odds 欠損 / 0 のレースは NaN
    df_bad = df.copy()
    df_bad.loc[df_bad["umaban"] == 1, "fukuoddslow"] = 0  # 1 行 0
    p_bl3_bad = compute_bl3(df_bad)
    # 0 の行は NaN になる
    bad_mask = df_bad["fukuoddslow"] == 0
    assert p_bl3_bad[bad_mask].isna().all(), "BL-3 が odds=0 行を NaN にしていない"


# ---------------------------------------------------------------------------
# Test 4: test_bl4_logreg
# ---------------------------------------------------------------------------
def test_bl4_logreg():
    """BL-4 LogisticRegression: sklearn LogisticRegression(max_iter=1000, random_state=42) で
    BL4_FEATURES を学習・predict_proba[:,1] を返す。
    """
    df = _build_bl_test_df(n_races=30, entry_count=8, seed=31)
    feature_cols = BL4_FEATURES + ["race_key"]
    train_df = df.iloc[: -8 * 5].copy()  # 末尾 5 レースを test
    test_df = df.iloc[-8 * 5 :].copy()
    X_train = train_df[BL4_FEATURES]
    y_train = train_df["fukusho_hit_validated"]
    X_test = test_df[BL4_FEATURES]

    p_bl4 = compute_bl4(X_train, y_train, X_test)
    assert p_bl4.name == "p_bl4"
    assert len(p_bl4) == len(X_test)
    assert p_bl4.index.equals(X_test.index)
    # predict_proba なので [0, 1]
    assert (p_bl4 >= 0).all() and (p_bl4 <= 1).all()

    # calibrate=False (デフォルト) で未キャリブレーション
    p_bl4_nocalib = compute_bl4(X_train, y_train, X_test, calibrate=False)
    assert p_bl4_nocalib.name == "p_bl4"


# ---------------------------------------------------------------------------
# Test 5: test_bl5_min_lightgbm
# ---------------------------------------------------------------------------
def test_bl5_min_lightgbm():
    """BL-5 LightGBM 最小特徴量: rolling 系統を除外した BL5_FEATURES で LightGBM 学習・
    predict_proba を返す・train_lightgbm を再利用。
    """
    df = _build_bl_test_df(n_races=30, entry_count=8, seed=41)
    train_df = df.iloc[: -8 * 5].copy()
    test_df = df.iloc[-8 * 5 :].copy()
    X_train = train_df[BL5_FEATURES]
    y_train = train_df["fukusho_hit_validated"]
    X_test = test_df[BL5_FEATURES]

    p_bl5 = compute_bl5(X_train, y_train, X_test)
    assert p_bl5.name == "p_bl5"
    assert len(p_bl5) == len(X_test)
    assert p_bl5.index.equals(X_test.index)
    # predict_proba なので [0, 1]
    assert (p_bl5 >= 0).all() and (p_bl5 <= 1).all()

    # BL5_FEATURES は rolling 系統を含まない
    assert not any("rolling" in c for c in BL5_FEATURES), (
        "BL5_FEATURES が rolling 系統を含んでいる (D-08: rolling 除外の最小特徴量であるべき)"
    )


# ---------------------------------------------------------------------------
# Test 6: test_market_data_source (D-08・@requires_db)
# ---------------------------------------------------------------------------


def test_fetch_market_data_race_keys_not_implemented():
    """CR-01: race_keys は未実装（NotImplementedError で fail-loud・以前の silent 無視を排除）。

    DB アクセス前に raise するため requires_db 不要。
    """
    with pytest.raises(NotImplementedError, match="race_keys"):
        fetch_market_data(None, race_keys=["2024-05-01-01-01"])  # type: ignore[arg-type]


@pytest.mark.requires_db
def test_market_data_source(readonly_cur):
    """D-08: n_odds_tanpuku.fukuoddslow (確定複勝オッズ) / n_uma_race.ninki (確定人気) が
    readonly_cur で SELECT 可能・2024年 test 期間に NULL が少ない。
    """
    # fukuoddslow / ninki を取得
    df_market = fetch_market_data(readonly_cur, year=2024)
    assert len(df_market) > 0, "fetch_market_data が 2024 年データを返さない (D-08)"

    # 必須列が存在
    required_cols = {
        "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban",
        "kettonum", "fukuoddslow", "ninki",
    }
    assert required_cols.issubset(set(df_market.columns)), (
        f"fetch_market_data の戻り値に必須列が無い (D-08): missing={required_cols - set(df_market.columns)}"
    )

    # 2024 年 test 期間 (2024-H2) に NULL が少ない (< 5%)
    df_market["year_int"] = df_market["year"].astype(int)
    df_2024 = df_market[df_market["year_int"] == 2024]
    assert len(df_2024) > 0, "2024 年データが空 (D-08)"

    n_total = len(df_2024)
    n_fuku_null = int(df_2024["fukuoddslow"].isna().sum() | (df_2024["fukuoddslow"] == "").sum() | (df_2024["fukuoddslow"] == "0").sum())
    n_ninki_null = int(df_2024["ninki"].isna().sum())
    fuku_null_rate = n_fuku_null / n_total
    ninki_null_rate = n_ninki_null / n_total
    assert fuku_null_rate < 0.05, (
        f"fukuoddslow の 2024 年 NULL/0 率が高すぎる ({fuku_null_rate:.3f} > 0.05・D-08)"
    )
    assert ninki_null_rate < 0.05, (
        f"ninki の 2024 年 NULL 率が高すぎる ({ninki_null_rate:.3f} > 0.05・D-08)"
    )


# ---------------------------------------------------------------------------
# 補助検証: BL-3 §14.2 注記定数 + review MEDIUM 未キャリブレーション注記
# ---------------------------------------------------------------------------
def test_bl3_and_uncalibrated_notes_present():
    """BL-3 §14.2 比較条件注記と BL-4/5 未キャリブレーション注記が定数として存在 (review MEDIUM)。"""
    assert "同一情報条件" in BL3_COMPARISON_CAVEAT or "same-information" in BL3_COMPARISON_CAVEAT.lower(), (
        "BL3_COMPARISON_CAVEAT が §14.2 比較条件の明示を含まない (review MEDIUM)"
    )
    assert "uncalibrated" in BL_UNCALIBRATED_NOTE.lower(), (
        "BL_UNCALIBRATED_NOTE が未キャリブレーション注記を含まない (review MEDIUM)"
    )


def test_compute_all_baselines_integrates_bl1_to_bl5():
    """compute_all_baselines が BL-1..5 全5つの p_bl* 列を統合 DataFrame として返す (SC#2)。"""
    df = _build_bl_test_df(n_races=30, entry_count=8, seed=51)
    train_df = df.iloc[: -8 * 5].copy()
    test_df = df.iloc[-8 * 5 :].copy()
    # df_test は BL-1/2/3 用・X_train/X_test は BL-4/5 用
    feature_cols_bl45 = list(set(BL4_FEATURES + BL5_FEATURES))
    X_train_bl45 = train_df[feature_cols_bl45]
    y_train = train_df["fukusho_hit_validated"]
    X_test_bl45 = test_df[feature_cols_bl45]

    result = compute_all_baselines(
        test_df,
        X_train_bl4_bl5=X_train_bl45,
        y_train=y_train,
        X_test_bl4_bl5=X_test_bl45,
    )
    # 全5 BL 列が存在
    for col in ["p_bl1", "p_bl2", "p_bl3", "p_bl4", "p_bl5"]:
        assert col in result.columns, f"compute_all_baselines に {col} 列が無い (SC#2)"
    # bl_calib_note 列が付与されている (review MEDIUM)
    assert "bl_calib_note" in result.columns
    # デフォルト (calibrate_bl4_bl5=False) で未キャリブレーション注記
    assert BL_UNCALIBRATED_NOTE in result["bl_calib_note"].iloc[0]
