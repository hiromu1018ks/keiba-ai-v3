# ruff: noqa: E501  (docstring / 日本語コメント行長は緩和・tests/features/conftest.py と同一慣例)
"""Phase 8 audit 共通 fixtures / synthetic DataFrame builder.

仕様（Plan 08-01・SC#2 adversarial 注入ヘルパー・per D-01/D-02）:

  - ``_build_label_row`` / ``_build_payout_row`` / ``_build_history_row``: 合成 label /
    payout / history 行 builder（``tests/features/conftest.py`` の ``_build_se_history_row``
    / ``_build_race_obs_row`` パターン踏襲）。``**overrides`` で任意カラム上書き（注入制御用）。
  - SC#2 adversarial（注入型メタ検証）3ケース（lookahead / payout 正欠損 / fold race_id 共有）
    で共通して使う合成データ構築関数。

合成行は ID のみを使用し、実馬名・騎手名等の PII は含まない（T-03-03 accept 踏襲）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 でも実行される・marker なし）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 合成 label 行 builder（label.fukusho_label shape・test_fukusho_label.py analog）
# ---------------------------------------------------------------------------
def _build_label_row(race_key: str, umaban: int, **overrides) -> dict:
    """合成 ``label.fukusho_label`` 行（test_fukusho_label.py パターン踏襲）。

    デフォルトは「複勝払戻対象=正（hit=1）」の正常出走馬。``**overrides`` で任意カラムを
    上書き（注入制御用・SC#2 ケース2 で ``fukusho_hit_validated=0`` に上書きして欠落を注入）。
    PII なし・ID のみ。
    """
    row: dict = {
        "race_key": race_key,
        "umaban": umaban,
        "kettonum": 10000000 + umaban,  # 安定した合成馬 ID
        "fukusho_hit_validated": 1,     # デフォルト: 払戻対象正
        "label_validation_status": "ok",
        "is_scratch_cancel": False,
        "is_dead_heat": False,
        "is_dead_loss": False,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 合成 payout 行 builder（public.n_harai PayFukusyoUmaban shape）
# ---------------------------------------------------------------------------
def _build_payout_row(race_key: str, umaban: int, **overrides) -> dict:
    """合成 ``public.n_harai`` 払戻行（race-level slot・1レース1行）。

    デフォルトは ``payfukusyoumaban1..3`` に umaban=1,2,3 を含む正常払戻。
    ``**overrides`` で任意カラムを上書き（注入制御用・SC#2 ケース2 で payout set と
    label を不一致させるために使う）。PII なし・ID のみ。
    """
    row: dict = {
        "race_key": race_key,
        "payfukusyoumaban1": f"{1:02d}",  # "01"
        "payfukusyoumaban2": f"{2:02d}",  # "02"
        "payfukusyoumaban3": f"{3:02d}",  # "03"
        "payfukusyoumaban4": "00",        # 3着同着なし
        "payfukusyoumaban5": "00",
        "datakubun": "2",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 合成 history 行 builder（normalized.n_uma_race shape・tests/features/conftest.py analog）
# ---------------------------------------------------------------------------
def _build_history_row(
    race_key: str,
    kettonum: int,
    as_of: str,
    **overrides,
) -> dict:
    """合成 ``normalized.n_uma_race`` 過去走行（``tests/features/conftest.py::_build_se_history_row``
    analog）。

    デフォルトは正常出走馬の過去走。``**overrides`` で任意カラムを上書き（注入制御用・
    SC#2 ケース1 で ``as_of_datetime`` を cutoff 直後に偽装して lookahead を注入する）。
    PII なし・ID のみ。
    """
    row: dict = {
        "race_key": race_key,
        "kettonum": kettonum,
        "race_date": pd.to_datetime(as_of),
        "as_of_datetime": pd.to_datetime(as_of),
        "race_start_datetime": pd.to_datetime(as_of) + pd.Timedelta(hours=12),
        "kakuteijyuni": 1,
        "timediff": 0.0,
        "harontimel3": 36.0,
        "jyuni3c": 1,
        "jyuni4c": 1,
        "jyuni1c": 0,
        "kyori": 1600,
        "jyocd": "05",
        "babacd": "01",
        "datakubun": "7",
        "umaban": 1,
        "wakuban": 1,
        "barei": 4,
        "sexcd": "1",
        "futan": 57.0,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Fixtures（必要に応じて後続 Task で拡張）
# ---------------------------------------------------------------------------
@pytest.fixture
def audit_mock_cursor() -> MagicMock:
    """``unittest.mock.MagicMock`` cursor（test_label_reconcile.py analog の空 cursor）。"""
    cur = MagicMock()
    cur.fetchall.return_value = []
    return cur
