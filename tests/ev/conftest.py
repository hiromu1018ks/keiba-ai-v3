"""Phase 5 EV/Backtest 用合成データ fixtures（RESEARCH §"Wave 0 Gaps" 設計指針）。

実JODDS取得が進行中（2026-06-20 時点 2015年25レース日分のみ）でも、合成データで
EV/backtest unit test を先行可能にするための fixtures。

設計（RESEARCH §1.1/§2.1/§Wave 0 Gaps）:
- ``make_jodds_mock``: JODDS snapshot（HappyoTime mmddHHMM / FukuOddsLow/High / Umaban /
  race_key 7カラム・PK は race_key 7 + Umaban = 8カラム）。
  ``umabans`` 指定で複数馬の per-horse snapshot を生成可能（HIGH-1 MEDIUM）。
  正常値/特殊値（``----``/``****``/``0000``/``0999``）混在可。
- ``make_harai_mock``: HARAI 払戻系 flags（6シナリオ）。
- ``make_label_mock``: label.fukusho_label フラグ（6シナリオ）。
- ``make_prediction_mock``: p_fukusho_hit + race_key 7カラム + umaban。

JODDS PK は race_key 7カラム + Umaban の 8カラム（RESEARCH §1.1 実証済み）のため、
全ての mock は必ず ``Umaban`` 列を持つ。
"""

from __future__ import annotations

import pandas as pd
import pytest

# RACE_KEY の 7 カラム（RESEARCH §1.1・n_race PK 6 + umaban で horse 単位）
RACE_KEY_COLUMNS: list[str] = ["year", "jyocd", "kaiji", "nichiji", "racenum"]
RACE_KEY_FULL_COLUMNS: list[str] = RACE_KEY_COLUMNS  # 6 カラム race 単位 PK


def _make_race_key_values(
    *,
    year: int = 2024,
    jyocd: str = "05",
    kaiji: int = 1,
    nichiji: str = "06",
    racenum: int = 1,
) -> dict[str, object]:
    """race_key 6カラム（race 単位）のデフォルト値を返す。"""
    return {
        "year": year,
        "jyocd": jyocd,
        "kaiji": kaiji,
        "nichiji": nichiji,
        "racenum": racenum,
    }


def make_jodds_mock(
    race_key: dict[str, object] | None = None,
    snapshots: list[dict[str, object]] | None = None,
    *,
    umabans: list[int] | None = None,
) -> pd.DataFrame:
    """JODDS snapshot の合成 DataFrame を構築する。

    RESEARCH §1.1 実証: ``n_jodds_tanpuku`` PK は race_key 7カラム + Umaban + HappyoTime = 8カラム。
    必ず ``Umaban`` 列を保持する（HIGH-1 MEDIUM: per-horse odds テスト用）。

    Parameters
    ----------
    race_key : dict, optional
        race_key 6カラム（year/jyocd/kaiji/nichiji/racenum）。省略時はデフォルト。
    snapshots : list[dict], optional
        各要素は ``{"happyotime": "01031833", "fukuoddslow": "0011",
        "fukuoddshigh": "0015", "fukusyoflag": "7", "datakubun": "1"}`` 形式。
        ``fukuoddslow``/``fukuoddshigh`` は ``----`` / ``****`` / ``0000`` / ``0999`` 等
        の特殊値も許可（RESEARCH §1.3）。
    umabans : list[int], optional
        複数馬の snapshot を生成する場合の Umaban リスト。省略時は ``[1, 2, 3]``。

    Returns
    -------
    pd.DataFrame
        ``year, jyocd, kaiji, nichiji, racenum, umaban, happyotime,
        fukuoddslow, fukuoddshigh, fukusyoflag, datakubun`` 列を持つ。
    """
    if race_key is None:
        race_key = _make_race_key_values()
    if snapshots is None:
        snapshots = [
            {
                "happyotime": "01031800",
                "fukuoddslow": "0011",
                "fukuoddshigh": "0015",
                "fukusyoflag": "7",
                "datakubun": "1",
            },
            {
                "happyotime": "01031830",
                "fukuoddslow": "0012",
                "fukuoddshigh": "0018",
                "fukusyoflag": "7",
                "datakubun": "1",
            },
        ]
    if umabans is None:
        umabans = [1, 2, 3]

    rows: list[dict[str, object]] = []
    for umaban in umabans:
        for snap in snapshots:
            row: dict[str, object] = {**race_key, "umaban": umaban}
            row.update(snap)
            rows.append(row)
    cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum",
        "umaban", "happyotime", "fukuoddslow", "fukuoddshigh",
        "fukusyoflag", "datakubun",
    ]
    return pd.DataFrame(rows, columns=cols)


def make_harai_mock(scenario: str = "normal_hit") -> pd.DataFrame:
    """HARAI 払戻系 flags の合成 DataFrame（6シナリオ）を構築する。

    RESEARCH §2.1 実証の ``n_harai`` 該当列を模倣:
    - ``FuseirituFlag2`` (varchar 1): ``'0'``/``'1'`` (複勝不成立)
    - ``HenkanFlag2`` (varchar 1): ``'0'``/``'1'`` (複勝返還あり)
    - ``TokubaraiFlag2`` (varchar 1): ``'0'``/``'1'`` (複勝特払)
    - ``PayFukusyoUmaban1..5`` (varchar 2): 複勝的中馬番
    - ``PayFukusyoPay1..5`` (varchar 9): 複勝払戻金（100円あたり）

    Parameters
    ----------
    scenario : str
        ``'normal_hit'`` / ``'normal_miss'`` / ``'scratch_cancel'`` /
        ``'race_excluded'`` / ``'dead_loss'`` / ``'fuseiritu'`` /
        ``'race_cancelled'`` / ``'no_sale'`` / ``'deadheat'``.

    Returns
    -------
    pd.DataFrame
        race_key 6カラム + 上記 HARAI 列を持つ1行 DataFrame。
    """
    base = _make_race_key_values()
    # 既定: 通常的中 (1着=3番・150円 / 2着=5番・200円 / 3着=7番・250円)
    default_pay = {
        "fuseirituflag2": "0",
        "henkanflag2": "0",
        "tokubaraiflag2": "0",
        "payfukusyoumaban1": "03",
        "payfukusyoumaban2": "05",
        "payfukusyoumaban3": "07",
        "payfukusyoumaban4": "00",
        "payfukusyoumaban5": "00",
        "payfukusyopay1": "0000150",
        "payfukusyopay2": "0000200",
        "payfukusyopay3": "0000250",
        "payfukusyopay4": "0000000",
        "payfukusyopay5": "0000000",
    }
    overrides: dict[str, dict[str, str]] = {
        "normal_hit": {},  # 既定と同一
        "normal_miss": {
            # 的中馬番が選択した馬(例:1番)と異なる
            "payfukusyoumaban1": "08",
            "payfukusyopay1": "0000100",
        },
        "scratch_cancel": {
            "henkanflag2": "1",  # 返還あり（個別馬）
        },
        "race_excluded": {
            "henkanflag2": "1",  # 除外で返還
        },
        "dead_loss": {
            # 競走中止: PayFukusyoUmaban は 00 slot（払戻無し）
            "payfukusyoumaban1": "00",
            "payfukusyopay1": "0000000",
            "payfukusyoumaban2": "00",
            "payfukusyopay2": "0000000",
            "payfukusyoumaban3": "00",
            "payfukusyopay3": "0000000",
        },
        "fuseiritu": {
            "fuseirituflag2": "1",  # 複勝不成立
            "payfukusyoumaban1": "00",
            "payfukusyopay1": "0000000",
            "payfukusyoumaban2": "00",
            "payfukusyopay2": "0000000",
            "payfukusyoumaban3": "00",
            "payfukusyopay3": "0000000",
        },
        "race_cancelled": {
            # レース全体中止: datakubun='9' は label flag 側で表現・HARAI は全 00
            "payfukusyoumaban1": "00",
            "payfukusyopay1": "0000000",
        },
        "no_sale": {
            "fukusyoflag": "0",  # 発売なし（head テーブル由来）
        },
        "deadheat": {
            # 同着: slot 2-3 を使用（例: 3着同着で slot 3 まで拡張）
            "payfukusyoumaban1": "03",
            "payfukusyopay1": "0000150",
            "payfukusyoumaban2": "05",
            "payfukusyopay2": "0000200",
            "payfukusyoumaban3": "07",
            "payfukusyopay3": "0000250",
            "payfukusyoumaban4": "09",  # 4着扱いで拡張払戻
            "payfukusyopay4": "0000300",
        },
    }
    row = {**base, **default_pay, **overrides.get(scenario, {})}
    cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum",
        "fuseirituflag2", "henkanflag2", "tokubaraiflag2",
        "payfukusyoumaban1", "payfukusyoumaban2", "payfukusyoumaban3",
        "payfukusyoumaban4", "payfukusyoumaban5",
        "payfukusyopay1", "payfukusyopay2", "payfukusyopay3",
        "payfukusyopay4", "payfukusyopay5",
    ]
    return pd.DataFrame([row], columns=cols)


def make_label_mock(scenario: str = "normal_hit") -> pd.DataFrame:
    """``label.fukusho_label`` フラグの合成 DataFrame（6シナリオ）を構築する。

    RESEARCH §2.1 実証のフラグ列を模倣:
    - ``is_scratch_cancel`` (bool): 出走取消
    - ``is_race_cancelled`` (bool): レース全体中止
    - ``is_race_excluded`` (bool): 発走前除外
    - ``is_dead_loss`` (bool): 競走中止
    - ``is_fukusho_sale_available`` (bool): 複勝発売あり
    - ``fukusho_payout_places`` (int): 払戻対象馬番数
    - ``fukusho_hit_validated`` (int 0/1): 的中判定

    Parameters
    ----------
    scenario : str
        ``make_harai_mock`` と同一のシナリオ名。

    Returns
    -------
    pd.DataFrame
        race_key 6カラム + ``umaban`` + 上記 label フラグ列を持つ1行 DataFrame。
    """
    base = _make_race_key_values()
    default = {
        "umaban": 1,
        "is_scratch_cancel": False,
        "is_race_cancelled": False,
        "is_race_excluded": False,
        "is_dead_loss": False,
        "is_fukusho_sale_available": True,
        "fukusho_payout_places": 3,
        "fukusho_hit_validated": 1,
    }
    overrides: dict[str, dict[str, object]] = {
        "normal_hit": {"umaban": 3, "fukusho_hit_validated": 1},
        "normal_miss": {"umaban": 1, "fukusho_hit_validated": 0},
        "scratch_cancel": {"umaban": 1, "is_scratch_cancel": True,
                            "fukusho_hit_validated": 0},
        "race_excluded": {"umaban": 1, "is_race_excluded": True,
                           "fukusho_hit_validated": 0},
        "dead_loss": {"umaban": 1, "is_dead_loss": True,
                       "fukusho_hit_validated": 0},
        "fuseiritu": {"umaban": 1, "fukusho_hit_validated": 0},
        "race_cancelled": {"umaban": 1, "is_race_cancelled": True,
                            "fukusho_hit_validated": 0},
        "no_sale": {"umaban": 1, "is_fukusho_sale_available": False,
                     "fukusho_hit_validated": 0},
        "deadheat": {"umaban": 9, "fukusho_payout_places": 4,
                      "fukusho_hit_validated": 1},  # 4着拡張で的中
    }
    row = {**base, **default, **overrides.get(scenario, {})}
    cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban",
        "is_scratch_cancel", "is_race_cancelled", "is_race_excluded",
        "is_dead_loss", "is_fukusho_sale_available",
        "fukusho_payout_places", "fukusho_hit_validated",
    ]
    return pd.DataFrame([row], columns=cols)


def make_prediction_mock(
    race_key: dict[str, object] | None = None,
    n_horses: int = 8,
    *,
    p_values: list[float] | None = None,
) -> pd.DataFrame:
    """予測値 + race_key 7カラム + umaban の合成 DataFrame を構築する。

    Parameters
    ----------
    race_key : dict, optional
        race_key 6カラム。省略時はデフォルト。
    n_horses : int
        出走頭数（``umaban`` 1..n_horses を生成）。
    p_values : list[float], optional
        各馬の ``p_fukusho_hit`` 値。省略時は ``[0.30, 0.25, 0.20, ...]`` の減衰値。

    Returns
    -------
    pd.DataFrame
        ``year, jyocd, kaiji, nichiji, racenum, umaban, race_key, p_fukusho_hit``
        列を持つ ``n_horses`` 行 DataFrame。
    """
    if race_key is None:
        race_key = _make_race_key_values()
    if p_values is None:
        # デフォルト: 0.30, 0.25, 0.20, ... の線形減衰
        p_values = [max(0.05, 0.30 - 0.05 * i) for i in range(n_horses)]
    if len(p_values) < n_horses:
        p_values = p_values + [0.05] * (n_horses - len(p_values))
    rows = []
    race_key_str = (
        f"{race_key['year']}-{race_key['jyocd']}-{race_key['kaiji']}-"
        f"{race_key['nichiji']}-{race_key['racenum']}"
    )
    for i in range(n_horses):
        row: dict[str, object] = {
            **race_key,
            "umaban": i + 1,
            "race_key": race_key_str,
            "p_fukusho_hit": p_values[i],
        }
        rows.append(row)
    cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum",
        "umaban", "race_key", "p_fukusho_hit",
    ]
    return pd.DataFrame(rows, columns=cols)


# --- pytest fixtures (関数としても直接呼出可能・parametrize 向け) ---


@pytest.fixture
def jodds_snapshots() -> pd.DataFrame:
    """標準的な JODDS snapshot（3頭 × 2時点 = 6行）。"""
    return make_jodds_mock()


@pytest.fixture
def harai_normal_hit() -> pd.DataFrame:
    """通常的中シナリオの HARAI 1行。"""
    return make_harai_mock("normal_hit")


@pytest.fixture
def label_normal_hit() -> pd.DataFrame:
    """通常的中シナリオの label 1行。"""
    return make_label_mock("normal_hit")


@pytest.fixture
def prediction_default() -> pd.DataFrame:
    """標準的な予測 DataFrame（8頭）。"""
    return make_prediction_mock()
