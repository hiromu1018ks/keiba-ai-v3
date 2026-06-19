"""Phase 3 features 共通 fixtures / synthetic DataFrame builder.

仕様（Plan 03-01 Task 2・03-REVIEWS.md HIGH #1 / CYCLE-2 HIGH #1 re-open）:

  - ``_build_se_history_row`` / ``_build_race_obs_row``: 合成 n_uma_race history /
    observations 行 builder（test_fukusho_label.py:_build_se_row パターン踏襲）。
  - ``_build_adversarial_rolling_rows``: 単一 observation × 5行 adversarial + 3行 eligible
    rolling history builder（target / same_day_prior / same_day_later / previous_day / future
    + eligible 3行・各 kakuteijyuni 区別値・HIGH #1・CR-01 で timediff→kakuteijyuni 切替）。
  - ``_build_two_observation_rolling_rows``: 同一 horse × 2 observation × 異 cutoff adversarial
    builder（CYCLE-2 HIGH #1 re-open・horse-grouped algorithm では検出不能な cross-obs leak）。
  - ``synthetic_availability`` / ``mock_readonly_cur``: fixtures。

合成行は ID のみを使用し、実馬名・騎手名等の PII は含まない（T-03-03 accept）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 合成 history 行 builder（normalized.n_uma_race shape）
# ---------------------------------------------------------------------------
def _build_se_history_row(kettonum: int, race_date: str, **overrides) -> dict:
    """合成 ``normalized.n_uma_race`` history 行（test_fukusho_label.py:_build_se_row analog）。

    デフォルトは正常出走馬の過去走。``**overrides`` で任意カラムを上書き。
    """
    row: dict = {
        "kettonum": kettonum,
        "race_date": pd.to_datetime(race_date),
        "as_of_datetime": pd.to_datetime(race_date),
        "race_start_datetime": pd.to_datetime(race_date) + pd.Timedelta(hours=12),
        "kakuteijyuni": 1,
        "timediff": 0.0,
        "harontimel3": 36.0,
        "jyuni3c": 1,
        "jyuni4c": 1,
        "jyuni1c": 0,            # 短距離 pitfall 再現用（1コーナー不存在）
        "kyori": 1600,
        "jyocd": "05",
        "babacd": "01",          # 過去走馬場状態（HIGH #4 history_allowed）
        "datakubun": "7",
        "umaban": 1,
        "wakuban": 1,
        "barei": 4,
        "sexcd": "1",
        "futan": 57.0,
    }
    row.update(overrides)
    return row


def _build_race_obs_row(race_nkey: str, kettonum: int, race_date: str, **overrides) -> dict:
    """合成 observations 行（対象レースの馬・D-06 + HIGH #2 semantics）。

    ``feature_cutoff_datetime = pd.to_datetime(race_date) - pd.Timedelta(days=1)``（JST midnight）。
    """
    rd = pd.to_datetime(race_date)
    row: dict = {
        "race_nkey": race_nkey,
        "kettonum": kettonum,
        "race_date": rd,
        "race_start_datetime": rd + pd.Timedelta(hours=12),
        "feature_cutoff_datetime": rd - pd.Timedelta(days=1),  # JST midnight (HIGH #2)
        "as_of_datetime": rd,
        "jyocd": "05",
        "kyori": 1600,
        "umaban": 1,
        "wakuban": 1,
        "barei": 4,
        "sexcd": "1",
        "futan": 57.0,
        "kisyucode": "01001",
        "chokyosicode": "01001",
        "ketto3infohansyokunum1": "SIRE001",
        "ketto3infohansyokunum2": "BMS001",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# REVIEWS HIGH #1: 5-row adversarial rolling builder（単一 observation）
# 対象レース + 同日別 + 同日午後 + 前日（cutoff 同日）+ 未来 + eligible 3行
# 各行 timediff を区別値で設定（rolling 結果が eligible 3行のみ含むことを機械的検出）
# ---------------------------------------------------------------------------
def _build_adversarial_rolling_rows(
    obs_race_date: str = "2023-06-04",
    kettonum: int = 1001,
) -> pd.DataFrame:
    """1頭の馬 × 1つの target observation に対する adversarial rolling history。

    戻り DataFrame は8行（5行 adversarial + 3行 eligible）。各 row の ``kakuteijyuni`` は
    区別可能な値を持ち、rolling 結果 ``rolling_kakuteijyuni_mean_5`` が eligible 3行の平均
    （=(1.0+2.0+3.0)/3 = 2.0）のみを含むことを test_rolling が機械的に検証する。

    ※ CR-01 (03-05): timediff/babacd 系統は rolling から削除されたため、本 fixture は
    残存系統 ``kakuteijyuni`` を識別値に使用する（PIT defense-in-depth の intent は不変）。
    """
    obs_rd = pd.to_datetime(obs_race_date)
    rows = [
        # (label, as_of_datetime offset from obs_rd, kakuteijyuni)
        ("target",          pd.Timedelta(days=0),  99),   # 当日・必ず除外
        ("same_day_prior",  pd.Timedelta(days=0),  88),   # 同日別レース・必ず除外
        ("same_day_later",  pd.Timedelta(days=0),  77),   # 同日午後・必ず除外
        ("previous_day",    pd.Timedelta(days=-1), 66),   # 前日==cutoff midnight・strict < で除外
        ("future",          pd.Timedelta(days=2),  55),   # 未来・必ず除外
        # eligible 3行（window に含まれるべき正当な過去走）
        ("eligible",        pd.Timedelta(days=-2), 1.0),
        ("eligible",        pd.Timedelta(days=-3), 2.0),
        ("eligible",        pd.Timedelta(days=-4), 3.0),
    ]
    history = []
    for label, offset, kakuteijyuni in rows:
        as_of = obs_rd + offset
        row = _build_se_history_row(
            kettonum=kettonum,
            race_date=as_of.strftime("%Y-%m-%d"),
            as_of_datetime=as_of,
            kakuteijyuni=kakuteijyuni,
        )
        row["row_label"] = label
        history.append(row)
    return pd.DataFrame(history)


# ---------------------------------------------------------------------------
# CYCLE-2 HIGH #1 re-open: 2-observation adversarial rolling builder
# 同一 horse が obs_A (cutoff=2023-06-03) と obs_B (cutoff=2023-06-10) の2つの
# target observation に現れるケース。history は3種の境界 race を含む。
# horse-grouped `groupby("kettonum").head(5)` では検出不能・obs_id-keyed のみ GREEN。
# ---------------------------------------------------------------------------
def _build_two_observation_rolling_rows(
    kettonum: int = 2002,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """同一 horse × 2 observation × 異 cutoff の adversarial rolling history。

    戻り値: ``(observations_df, history_df)``

    - obs_A: race_nkey="2023A0610-R1", race_date="2023-06-04",
      feature_cutoff_datetime="2023-06-03"
    - obs_B: race_nkey="2023A0617-R1", race_date="2023-06-11",
      feature_cutoff_datetime="2023-06-10"

    history は3種の境界 race:
      (a) both_pre:        as_of="2023-06-01"・kakuteijyuni=1・両 cutoff 以前・両 window 共通
      (b) obs_B_only_pre:  as_of="2023-06-05"・kakuteijyuni=7・obs_B の cutoff 以前だが
                           obs_A の cutoff 以降・obs_A には混入不可・obs_B のみに含まれるべき
      (c) both_post:       as_of="2023-06-12"・kakuteijyuni=99・両 cutoff 以降・両 window 除外

    ※ CR-01 (03-05): timediff/babacd 系統は rolling から削除されたため、本 fixture は
    残存系統 ``kakuteijyuni`` を識別値に使用する（PIT defense-in-depth の intent は不変）。
    """
    observations = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", kettonum, "2023-06-04", obs_id="A"),
        _build_race_obs_row("2023A0617-R1", kettonum, "2023-06-11", obs_id="B"),
    ])
    history_rows = [
        _build_se_history_row(
            kettonum=kettonum,
            race_date="2023-06-01",
            as_of_datetime=pd.to_datetime("2023-06-01"),
            kakuteijyuni=1,
            row_label="both_pre",
        ),
        _build_se_history_row(
            kettonum=kettonum,
            race_date="2023-06-05",
            as_of_datetime=pd.to_datetime("2023-06-05"),
            kakuteijyuni=7,
            row_label="obs_B_only_pre",
        ),
        _build_se_history_row(
            kettonum=kettonum,
            race_date="2023-06-12",
            as_of_datetime=pd.to_datetime("2023-06-12"),
            kakuteijyuni=99,
            row_label="both_post",
        ),
    ]
    history = pd.DataFrame(history_rows)
    return observations, history


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_availability() -> dict:
    """``load_feature_availability()`` の結果を返す（Plan 03-01 Task 1 で作成済）。"""
    from src.features.availability import load_feature_availability

    return load_feature_availability()


@pytest.fixture
def mock_readonly_cur():
    """``unittest.mock.MagicMock`` cursor（test_normalized_etl.py:29 パターン）。"""
    cur = MagicMock()
    cur.fetchall.return_value = []
    return cur
