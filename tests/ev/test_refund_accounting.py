"""返還 / 競走中止 / dead-loss honest 会計の unit test（BACK-03 / D-05 / §11.6）。

Wave 0 (Plan 05-01): RED stub。``src.ev.refund_accounting`` 未実装のため ImportError で RED。

検証内容（RESEARCH §2.5・9シナリオ）:
- ``test_refund_normal_hit`` / ``test_refund_normal_miss``: 通常会計
- ``test_refund_scratch_cancel`` / ``test_refund_race_excluded``: 返還 effective_stake=0
- ``test_refund_dead_loss``: 競走中止 effective_stake=100（§10.6 除外禁止）
- ``test_refund_fuseiritu``: 複勝不成立 → 返還
- ``test_refund_race_cancelled``: レース全体中止 → 返還
- ``test_refund_no_sale``: 複勝発売なし → 選択対象外
- ``test_refund_deadheat``: 同着拡張払戻で slot 2-5 使用
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests.ev.conftest import make_harai_mock, make_label_mock


# 9シナリオ parametrize 用 fixture（label + harai を1行に結合した row を生成）
SCENARIOS = [
    "normal_hit", "normal_miss", "scratch_cancel", "race_excluded",
    "dead_loss", "fuseiritu", "race_cancelled", "no_sale", "deadheat",
]


def _build_scenario_row(scenario: str) -> pd.Series:
    """``label.fukusho_label`` + ``n_harai`` を結合した1行 row を構築する。"""
    label_df = make_label_mock(scenario)
    harai_df = make_harai_mock(scenario)
    # race_key 6カラムで結合（race 単位）・umaban は label 側を採用
    merged = label_df.merge(
        harai_df.drop(columns=["umaban"]) if "umaban" in harai_df.columns else harai_df,
        on=["year", "jyocd", "kaiji", "nichiji", "racenum"],
        how="left",
    )
    return merged.iloc[0]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_refund_scenario(scenario: str):
    """9シナリオの determine_stake_payout を検証する parametrize エントリ。

    個別シナリオ assertion は下位テスト関数で実施。本関数は parametrize の集約エントリ。
    """
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row(scenario)
    result = determine_stake_payout(row)
    assert isinstance(result, dict)
    expected_keys = {"stake", "refund", "payout", "profit", "effective_stake"}
    assert expected_keys.issubset(result.keys())


def test_refund_normal_hit():
    """通常的中: payout=PayFukusyoPay, profit=payout-100, effective_stake=100。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("normal_hit")
    # umaban=3 が的中 → PayFukusyoPay1=150
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 100
    assert result["refund"] == 0
    assert result["payout"] > 0
    assert result["profit"] == result["payout"] - 100


def test_refund_normal_miss():
    """通常不的中: payout=0, profit=-100, effective_stake=100。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("normal_miss")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 100
    assert result["payout"] == 0
    assert result["profit"] == -100


def test_refund_scratch_cancel():
    """出走取消: refund=100, effective_stake=0（返還系・§11.6）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("scratch_cancel")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 0
    assert result["refund"] == 100
    assert result["payout"] == 0
    assert result["profit"] == 0


def test_refund_race_excluded():
    """競走除外: refund=100, effective_stake=0（返還系）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("race_excluded")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 0
    assert result["refund"] == 100


def test_refund_dead_loss():
    """競走中止: profit=-100, effective_stake=100（§10.6 除外禁止・実運用の負けを消さない）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("dead_loss")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 100  # 返還でなく loss
    assert result["refund"] == 0
    assert result["payout"] == 0
    assert result["profit"] == -100


def test_refund_fuseiritu():
    """複勝不成立: refund=100, effective_stake=0（FuseirituFlag2='1'）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("fuseiritu")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 0
    assert result["refund"] == 100


def test_refund_race_cancelled():
    """レース全体中止: refund=100, effective_stake=0（datakubun='9'）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("race_cancelled")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 0
    assert result["refund"] == 100


def test_refund_no_sale():
    """複勝発売なし: 選択対象外（stake=0・事前 filter で到達しない前提）。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("no_sale")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 0
    assert result["stake"] == 0


def test_refund_deadheat():
    """同着拡張: PayFukusyoUmaban slot 2-5 → 該当 slot の PayFukusyoPay。"""
    from src.ev.refund_accounting import determine_stake_payout

    row = _build_scenario_row("deadheat")
    result = determine_stake_payout(row, stake_per_bet=100)
    assert result["effective_stake"] == 100
    assert result["payout"] > 0


def test_refund_tokubarai_harai_fixture():
    """MEDIUM-D cycle-2: HARAI 実スキーマ形状の特払 fixture（TokubaraiFlag2='1'）。

    実DB観測値では tokubaraiflag2='1' が 0件のため合成必須。HARAI 実スキーマ形状の
    特払 fixture（row: race_key + FuseirituFlag2='0' + TokubaraiFlag2='1' + HenkanFlag2='0' +
    PayFukusyoUmaban1..5='00'(的中馬番なし・特払) + PayFukusyoPay1..5=70(特払金額) +
    label fukusho_hit_validated=0）を構築し・determine_stake_payout(row) が
    stake=100 / refund=0 / payout=70（特払 PayFukusyoPay） / profit=-30 / effective_stake=100
    を返すことを assert（公式に従う・§2.4 特払 semantics）。

    fukusho_hit_validated=0 でも PayFukusyoPay>0 の場合は payout>0 となる契約
    （特払は的中フラグ非依存・HARAI PayFukusyoPay 一次）。
    """
    from src.ev.refund_accounting import determine_stake_payout

    # HARAI 実スキーマ形状の特払 fixture を手構築（conftest の scenario に無いため）
    base = {
        "year": 2024, "jyocd": "05", "kaiji": 1, "nichiji": "06", "racenum": 1,
        "umaban": 1,
        # label フラグ（特払時は通常 sale_available=True・hit_validated=0・停止系フラグ全 False）
        "is_fukusho_sale_available": True,
        "is_scratch_cancel": False,
        "is_race_excluded": False,
        "is_race_cancelled": False,
        "is_dead_loss": False,
        "fukusho_hit_validated": 0,
        # HARAI 払戻系 flags（特払）
        "fuseirituflag2": "0",   # 不成立なし
        "henkanflag2": "0",      # 返還なし
        "tokubaraiflag2": "1",   # 複勝特払
        # 的中馬番なし（'00'）・PayFukusyoPay=70（特払金額・100円あたり）
        "payfukusyoumaban1": "00",
        "payfukusyoumaban2": "00",
        "payfukusyoumaban3": "00",
        "payfukusyoumaban4": "00",
        "payfukusyoumaban5": "00",
        "payfukusyopay1": "0000070",  # 特払 70円
        "payfukusyopay2": "0000000",
        "payfukusyopay3": "0000000",
        "payfukusyopay4": "0000000",
        "payfukusyopay5": "0000000",
    }
    row = pd.Series(base)
    result = determine_stake_payout(row, stake_per_bet=100)
    # 特払 semantics: stake=100 / refund=0 / payout=70 / profit=-30 / effective_stake=100
    assert result["stake"] == 100
    assert result["refund"] == 0
    assert result["payout"] == 70
    assert result["profit"] == -30
    assert result["effective_stake"] == 100
