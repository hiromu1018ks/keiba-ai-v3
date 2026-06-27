# ruff: noqa: E501
"""返還 / 競走中止 / dead-loss honest 会計決定表（D-05 / BACK-03 / §10.6 / §11.6）.

Phase 5 EV/backtest で「選択した馬の honest 会計」を決定する service 層。
返還（取消/除外/不成立/レース中止）は ``effective_stake=0``・競走中止（``is_dead_loss``）は
``effective_stake=100``（§10.6 除外禁止）で回収率の歪みを防止する（Core Value 直結）。

**設計の核心（RESEARCH §2.1-§2.5 / Plan 05-03）:**

1. **label フラグ一次ソース・HARAI cross-check（Pitfall A6）**: ``label.fukusho_label`` の
   既存フラグ（``is_scratch_cancel`` / ``is_race_excluded`` / ``is_dead_loss`` /
   ``is_race_cancelled`` / ``is_fukusho_sale_available`` / ``fukusho_payout_places`` /
   ``fukusho_hit_validated``・Phase 2 実装済み・READ のみ）を一次ソースとする。
   HARAI の ``FuseirituFlag2`` / ``TokubaraiFlag2`` / ``HenkanFlag2`` / ``PayFukusyoPay`` は
   cross-check/補助。``HenkanUma`` ビットマスクは直接見ない（label フラグが同等情報・A6）。
2. **6シナリオ決定表（§11.6・T-05-08/09 mitigate）**:
   - 複勝発売なし → ``stake=0``（選択対象外・事前 filter）
   - 取消/除外/不成立/レース中止 → ``effective_stake=0`` / ``refund=100``（返還系）
   - 競走中止（``is_dead_loss``）→ ``effective_stake=100`` / ``profit=-100``
     （§10.6 除外禁止・実運用の負けを消さない・T-05-08 mitigate・Pitfall 4）
   - 通常的中/不的中 → ``payout=_lookup_payfukusyo_pay(row)``（HARAI PayFukusyoPay 一次）
3. **特別払戻（TokubaraiFlag2='1'・§2.4・T-05-23 mitigate）**: ``PayFukusyoUmaban='00'``
   （的中馬番なし）でも ``PayFukusyoPay>0``（特払金額）の場合は payout に計上。
   特払は的中フラグ（``fukusho_hit_validated``）非依存・HARAI ``PayFukusyoPay`` が一次契約。
4. **``_lookup_payfukusyo_pay``**: row.umaban を ``PayFukusyoUmaban1..5`` slot と照合し・
   該当 slot の ``PayFukusyoPay1..5`` を返す。同着で slot 2-5 使用可。該当なしは 0（不的中）。

参照: 05-RESEARCH.md §2.1-§2.5 / 05-PATTERNS.md refund_accounting.py 節 /
      src/etl/fukusho_label.py (label フラグ READ のみ・変更なし) /
      src/model/baseline.py::_payout_places_from_row (行ベース決定 analog).
"""

from __future__ import annotations

import pandas as pd


def _lookup_payfukusyo_pay(row: pd.Series) -> int:
    """``row.umaban`` を ``PayFukusyoUmaban1..5`` slot と照合し・該当 slot の
    ``PayFukusyoPay1..5`` を返す（同着で slot 2-5 使用可・該当なしは 0）。

    RESEARCH §2.1: ``PayFukusyoUmaban1..5`` は varchar(2)（例 '03'）・
    ``PayFukusyoPay1..5`` は varchar(9)（例 '0000150' = 150円・100円あたり）。
    ``'00'`` は的中馬番なし（発売なし/特払/不成立）→ 該当 slot は payout source として
    使用しない（特払は determine_stake_payout 側で tokubaraiflag2 で判定して計上）。

    Returns
    -------
    int
        該当 slot の ``PayFukusyoPay`` 値（100円あたり）。該当なしは 0。
    """
    try:
        umaban = int(row.get("umaban"))
    except (TypeError, ValueError):
        return 0

    for slot in range(1, 6):
        umaban_col = f"payfukusyoumaban{slot}"
        pay_col = f"payfukusyopay{slot}"
        if umaban_col not in row.index or pay_col not in row.index:
            continue
        umaban_val = row.get(umaban_col)
        if umaban_val is None:
            continue
        try:
            # '03' → 3 / '00' は的中馬番なし（skip）
            slot_umaban = int(str(umaban_val).strip())
        except (ValueError, TypeError):
            continue
        if slot_umaban == umaban:
            try:
                return int(str(row.get(pay_col)).strip())
            except (ValueError, TypeError):
                return 0
    return 0


def determine_stake_payout(
    row: pd.Series,
    *,
    stake_per_bet: int = 100,
) -> dict[str, int]:
    """§11.6 honest 会計決定表（RESEARCH §2.2/§2.3）。

    label フラグ一次・HARAI ``PayFukusyoPay`` で payout 確定。返還系は
    ``effective_stake=0``・競走中止は ``effective_stake=100``（§10.6 除外禁止）。

    Parameters
    ----------
    row : prediction + label + HARAI join 済みの1行。必須列（存在しない場合は安全側に倒す）:
        - ``is_fukusho_sale_available`` (bool): 複勝発売あり
        - ``is_scratch_cancel`` / ``is_race_excluded`` / ``is_race_cancelled`` (bool): 返還系
        - ``is_dead_loss`` (bool): 競走中止（§10.6 除外禁止・effective_stake=100）
        - ``fuseirituflag2`` (str): '1'=複勝不成立（返還）
        - ``tokubaraiflag2`` (str): '1'=複勝特払（payout に PayFukusyoPay 計上）
        - ``umaban`` (int): 選択馬番（``_lookup_payfukusyo_pay`` で slot 照合）
        - ``payfukusyoumaban1..5`` / ``payfukusyopay1..5`` (str): 払戻 slot
    stake_per_bet : 1候補あたりの stake（円・既定 100）。

    Returns
    -------
    dict
        keys: ``stake, refund, payout, profit, effective_stake``。
        - ``stake``: 仮想購入 stake（0 or stake_per_bet）
        - ``refund``: 返還金額（返還系は stake_per_bet・それ以外は 0）
        - ``payout``: 払戻金額（100円あたり・``PayFukusyoPay``）
        - ``profit``: payout + refund - stake
        - ``effective_stake``: 回収率の分母（返還系は 0・それ以外は stake_per_bet）
    """
    # 複勝発売なしは選択対象外（事前 filter で到達しない前提・安全側に倒す）
    if not bool(row.get("is_fukusho_sale_available", False)):
        return {
            "stake": 0,
            "refund": 0,
            "payout": 0,
            "profit": 0,
            "effective_stake": 0,
        }

    # 返還系（取消/除外/不成立/レース中止）→ effective_stake=0（§11.6・T-05-09 mitigate）
    is_scratch_cancel = bool(row.get("is_scratch_cancel", False))
    is_race_excluded = bool(row.get("is_race_excluded", False))
    is_race_cancelled = bool(row.get("is_race_cancelled", False))
    fuseiritu = str(row.get("fuseirituflag2", "0")).strip() == "1"

    if is_scratch_cancel or is_race_excluded or is_race_cancelled or fuseiritu:
        return {
            "stake": stake_per_bet,
            "refund": stake_per_bet,
            "payout": 0,
            "profit": 0,
            "effective_stake": 0,
        }

    # 競走中止（is_dead_loss）→ effective_stake=100 / profit=-100
    # §10.6 除外禁止・Pitfall 4・T-05-08 mitigate（実運用の負けを消さない）
    if bool(row.get("is_dead_loss", False)):
        return {
            "stake": stake_per_bet,
            "refund": 0,
            "payout": 0,
            "profit": -stake_per_bet,
            "effective_stake": stake_per_bet,
        }

    # 通常 / 特払（TokubaraiFlag2='1'）: payout = _lookup_payfukusyo_pay(row)
    # 特払は PayFukusyoUmaban='00' でも PayFukusyoPay>0（特払金額）を payout に計上
    # （§2.4・T-05-23 mitigate・的中フラグ非依存・HARAI PayFukusyoPay 一次）
    # ※ _lookup_payfukusyo_pay は umaban='00' slot にはマッチしないため・特払時は
    #    determine_stake_payout が tokubaraiflag2 を見て PayFukusyoPay slot1 を計上する。
    # WR-06: 特払時は PayFukusyoUmaban1..5 全てが '00' (的中馬番無し) であることを検証し・
    # もし slot に選択馬番と一致する umaban があれば通常扱い (tokubarai flag と slot データ
    # が矛盾する場合) にフォールバック。特払金額は JRA ルール上 対象馬のオッズに拠らず
    # 一律のため slot1 を計上する。
    tokubarai = str(row.get("tokubaraiflag2", "0")).strip() == "1"
    if tokubarai:
        # 選択馬と一致する slot があるか確認 (矛盾時の安全フォールバック)
        normal_payout = _lookup_payfukusyo_pay(row)
        if normal_payout > 0:
            # tokubaraiflag=1 だが slot に選択馬番が入っている → 通常の中り扱い (安全側)
            payout = normal_payout
        else:
            # 特払: PayFukusyoUmaban1='00' の場合でも PayFukusyoPay1 を payout に計上
            try:
                payout = int(str(row.get("payfukusyopay1", "0")).strip())
            except (ValueError, TypeError):
                payout = 0
    else:
        payout = _lookup_payfukusyo_pay(row)

    return {
        "stake": stake_per_bet,
        "refund": 0,
        "payout": payout,
        "profit": payout - stake_per_bet,
        "effective_stake": stake_per_bet,
    }


# ---------------------------------------------------------------------------
# Phase 12 (Plan 03) snapshot→final payout slippage (D-07・C-12-03-5)
# ---------------------------------------------------------------------------
# CONTEXT D-07 / 12-CONTEXT.md Claude's Discretion「snapshot→final slippage の具体的測定」:
#   HARAI PayFukusyoPay (final payout) と odds_snapshot fuku_odds_lower の差分。
#   planner 事前登録測定式: payout/100 - fuku_odds_lower (100円あたり payout を odds 単位に揃える)。
#
# [C-12-03-5 / MEDIUM] 2種類の signature を提供し・呼出側が slot lookup を二重/欠落しないようにする:
#   (1) row ベース版 compute_snapshot_final_slippage_from_row は _lookup_payfukusyo_pay を呼んで
#       slot を解決する経路を持つ。
#   (2) payout_amount 受け取り版 compute_snapshot_final_slippage は呼出側が _lookup_payfukusyo_pay で
#       解決済みの payout_amount を渡す想定。
#   二重 slot lookup を避けるためどちらかを使う (silent バグ回避・docstring で明示)。


def compute_snapshot_final_slippage(
    *,
    payout_amount: float,
    fuku_odds_lower: float,
) -> float:
    """snapshot (fuku_odds_lower) → final payout (HARAI PayFukusyoPay) の slippage を計算 (D-07).

    planner 事前登録測定式 (CONTEXT Claude's Discretion): ``payout/100 - fuku_odds_lower``。
    HARAI ``PayFukusyoPay`` は 100 円あたりの払戻金額 (例 '200' = 200 円)・``fuku_odds_lower`` は
    JODDS snapshot の複勝オッズ下限 (例 1.5 倍)。``payout/100`` で倍率単位に揃えて差分を取る。

    **[C-12-03-5 / MEDIUM] payout_amount 受け取り版:**
        本関数は呼出側が :func:`_lookup_payfukusyo_pay` 等で slot 解決済みの ``payout_amount`` を
        受け取る想定。row から slot を解決する必要がある場合は
        :func:`compute_snapshot_final_slippage_from_row` を使う (二重 slot lookup を避けるため・
        どちらかを使う)。

    NaN 伝播 (payout=0 no_bet や odds=NaN) は呼出側で filter する想定。
    本関数は NaN をそのまま返す (silent fallback 禁止・Shared Pattern 4・0/100 - odds 等の計算結果を
    そのまま返すことで・呼出側が filter 条件を明示することを強要する)。

    Parameters
    ----------
    payout_amount : float
        HARAI ``PayFukusyoPay`` (100 円あたり・呼出側が slot 解決済み)。
    fuku_odds_lower : float
        JODDS snapshot の複勝オッズ下限 (倍率・例 1.5)。

    Returns
    -------
    float
        ``payout_amount / 100.0 - fuku_odds_lower`` (倍率単位の差分)。
        正: final payout が snapshot odds より高い (有利・slippage の恩恵)。
        負: final payout が snapshot odds より低い (不利・slippage の損失)。
    """
    return float(payout_amount) / 100.0 - float(fuku_odds_lower)


def compute_snapshot_final_slippage_from_row(
    row: pd.Series,
    fuku_odds_lower: float,
) -> float:
    """row から slot を解決して snapshot→final payout slippage を計算 (D-07・C-12-03-5 row ベース版).

    内部で :func:`_lookup_payfukusyo_pay` を呼んで ``row.umaban`` を
    ``PayFukusyoUmaban1..5`` slot と照合し・該当 slot の ``PayFukusyoPay`` を取得して
    :func:`compute_snapshot_final_slippage` に渡す。

    **[C-12-03-5 / MEDIUM] 二重 slot lookup 回避:**
        本関数は :func:`_lookup_payfukusyo_pay` を自動で呼ぶ。呼出側が既に ``_lookup_payfukusyo_pay``
        等で slot を解決済みの場合は :func:`compute_snapshot_final_slippage` (payout_amount 受け取り版)
        を使うこと (二重 slot lookup を避けるため・どちらかを使う)。docstring で経路を明示。

    Parameters
    ----------
    row : pd.Series
        ``umaban`` / ``payfukusyoumaban1..5`` / ``payfukusyopay1..5`` 列を含む prediction + HARAI join 済み row。
    fuku_odds_lower : float
        JODDS snapshot の複勝オッズ下限 (倍率)。

    Returns
    -------
    float
        ``_lookup_payfukusyo_pay(row) / 100.0 - fuku_odds_lower``。
        該当 slot なし (payout=0) の場合は ``0/100 - fuku_odds_lower`` (= ``-fuku_odds_lower``)。
    """
    payout_amount = _lookup_payfukusyo_pay(row)
    return compute_snapshot_final_slippage(
        payout_amount=payout_amount, fuku_odds_lower=fuku_odds_lower
    )
