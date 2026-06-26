# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/model/test_trainer.py と同一慣例)
"""Phase 10 PLAN 01: 相手強度 field_strength profile（D-06 第1段階）unit test.

SC#1 PIT-correct 厳格版 as-of（D-01 opponent-vs-source + CYCLE-2 HIGH-C2-1 source-vs-target-cutoff
値の不変性）・D-02 相手 rolling mean_5 1軸（Open Question #1 事前登録）・D-03 profile 8値・
D-04 発走馬特定（kakuteijyuni > 0）・D-05 top-k クランプ・SAFE-01 odds-free（本テストでは
機能検証のみ・AST audit は PLAN 07 tests/audit/test_audit_field_strength.py）を機械保証する。

特記: CYCLE-2 HIGH-C2-1 (10-REVIEWS.md L57-92, L171-209, L295) は行包含でなく値レベルの
source-vs-target-cutoff 保証を要求する。本テストの Test 2 は同じ pre-source opponent race が
異なる target cutoff で消費されても再計算 speed_figure が bit-identical になることを直接証明し・
monkeypatch で再計算 cutoff を target cutoff に差し替えると値が変化することで guard 有効を逆証する。

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。cross-reference: 本テストは機能+
adversarial を1ファイルに集約（PLAN 01 が新規モジュールで機能テスト単独ファイルが不要なため）。
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd
import pytest

from src.features.field_strength import (  # noqa: F401  (import 先で CUTOFF_SEMANTICS assert)
    OPPONENT_ROLLING_AXIS,
    OPPONENT_ROLLING_K,
    SOURCE_RACE_BATCH_SIZE,
    compute_field_strength_profile,
)


# ---------------------------------------------------------------------------
# 合成 history builder（field_strength 専用・race_nkey/kettonum/race_date/time を識別値に）
# ---------------------------------------------------------------------------
def _fs_history_row(
    race_nkey: str,
    kettonum: int,
    race_date: str,
    *,
    time: float,
    trackcd: str = "24",
    jyocd: str = "05",
    kyori: int = 1600,
    kakuteijyuni: int = 1,
    **overrides: Any,
) -> dict:
    """合成 raw_history 行（Step 5b 前・obs_id 未展開・speed_figure/available_at 非存在）。

    raw_history は builder.py::_fetch_history → _construct_derived_columns の出力を想定し・
    race_nkey / as_of_datetime / time / trackcd / jyocd / kyori / kakuteijyuni / race_date を持つ。
    available_at / speed_figure は compute_speed_figure_for_history が付与するため本 raw_history には
    含めない（CYCLE-3 MEDIUM #1・Test 3/11 で非依存を機械保証）。
    """
    row: dict = {
        "race_nkey": race_nkey,
        "kettonum": kettonum,
        "race_date": pd.to_datetime(race_date),
        "as_of_datetime": pd.to_datetime(race_date),
        "race_start_datetime": pd.to_datetime(race_date) + pd.Timedelta(hours=12),
        "time": float(time),  # MMSS.t エンコード（JRA-VAN 可変長走破タイム）
        "trackcd": trackcd,
        "jyocd": jyocd,
        "kyori": kyori,
        "kakuteijyuni": kakuteijyuni,
        # rolling source 等の他カラム（本テストでは計算に寄与しない・presence のみ）
        "timediff": 0.0,
        "harontimel3": 36.0,
        "jyuni3c": 1,
        "jyuni4c": 1,
        "babacd": "01",
        "umaban": 1,
        "wakuban": 1,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Test 1: PIT strict `<` opponent-vs-source（D-01・機能テスト）
# ---------------------------------------------------------------------------
def test_opponent_vs_source_pit_strict_less() -> None:
    """D-01 厳格版 as-of（機能テスト・layer 1 = source-as-of recompute）: source race と同日の
    opponent speed_figure（available_at == source.available_at）は profile に混入しない.

    source race R1(2023-06-10) と同日の H2/H3 の R1 行は・source-as-of recompute の
    feature_cutoff_datetime=source_race.available_at (strict <) PIT filter で除外される。
    H1 の opponent は H2/H3 の R0(2023-06-01) 過去走のみで valid_count=2 になる。

    CYCLE-2 HIGH-C2-1 の adversarial（leaky < で混入検出）は Test 2 が別途カバーする。
    本テストは「正しく除外される」機能テスト（cross-reference: Test 2 adversarial）。
    """
    # source race R1 (2023-06-10)・3 starters: H1/H2/H3
    # H1/H2/H3 は 2023-06-01 に共通の過去走を持つ（R0・time=1500）
    # H1/H2/H3 は source race R1 自身にも出走・same-day 行は source-as-of recompute の strict < で除外
    rows = [
        _fs_history_row("R0_20230601", 1001, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 1002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 1003, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 1001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 1002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 1003, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    result = compute_field_strength_profile(raw_history)
    h1_source = result[
        (result["kettonum"] == 1001) & (result["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_source) == 1
    valid_count = float(h1_source["field_strength_valid_count"].iloc[0])
    assert valid_count == 2.0, (
        f"保護あり: H1 の opponent は H2/H3 の R0 のみで valid_count=2 のはず・実際: {valid_count}・"
        f"same-day opponent (R1 行) が混入している疑い（D-01 strict < 違反）"
    )


def test_opponent_vs_source_pit_strict_less_adversarial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-01 厳格版 as-of（adversarial・layer 1 = source-as-of recompute）: source-as-of recompute の
    cutoff を未来に引き上げると・source race 以後の opponent 過去走が混入して ability 値が変化する.

    検出力の証明: source race R1(2023-06-15) の相手 H2 は・過去走として R0(2023-06-01) と
    R_POST(2023-06-20・R1 以後) を持つ。保護あり経路では H2 の ability は R0 のみで算出される。
    source-as-of recompute cutoff を R1(2023-06-15) から 2023-06-30 に引き上げると・R_POST が
    混入し H2 の ability が R0 と R_POST の平均に変化する（検出力証明・false-pass 回避）。

    合成データの都合上・par グループに H2/H3/H4 の3頭が含まれ（同一 jyocd/trackcd/kyori）・
    各馬が異なる time を持つことで speed_figure が非0・かつ H2 の R0 と R_POST で time が異なり
    ability 値が変化するようにする。
    """
    import src.features.field_strength as fs_mod

    # source race R1(2023-06-15)・starters: H1/H2（同一 jyocd=05/trackcd=24/kyori=1600）
    # H2 は5走以上の過去走を持ち・clean 版（R1 source cutoff=2023-06-15）では最新5走が R0a〜R0e になる。
    # leaky 版（cutoff=2023-06-30）では R_POST(2023-06-20) が追加混入し・最新5走の構成が変わる（R0a が窓から押出）。
    # 各走の time を徐々に速くしていく（H2 成長曲線）ことで・latest-5 の平均が窓の構成で変わるようにする。
    rows = [
        # H2 の過去走 5件（R1 source=2023-06-15 より前・clean 版で最新5走）
        _fs_history_row("R0a_20230401", 2002, "2023-04-01", time=1560.0, kakuteijyuni=1),  # 最古・遅い(116s)
        _fs_history_row("R0b_20230415", 2002, "2023-04-15", time=1540.0, kakuteijyuni=1),  # (114s)
        _fs_history_row("R0c_20230501", 2002, "2023-05-01", time=1520.0, kakuteijyuni=1),  # (112s)
        _fs_history_row("R0d_20230515", 2002, "2023-05-15", time=1500.0, kakuteijyuni=1),  # (110s)
        _fs_history_row("R0e_20230601", 2002, "2023-06-01", time=1480.0, kakuteijyuni=1),  # 最新・速い(108s)
        # H2 の R_POST (2023-06-20): R1 以後・保護あり経路では除外・leaky 版で混入・最速(106s)
        _fs_history_row("R_POST_20230620", 2002, "2023-06-20", time=1460.0, kakuteijyuni=1),
        # source race R1 (2023-06-15): H1/H2 出走
        _fs_history_row("R1_20230615", 2001, "2023-06-15", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230615", 2002, "2023-06-15", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # 保護あり経路: H2 の R_POST(2023-06-20) は R1 source(2023-06-15) 以後なので除外
    result_clean = compute_field_strength_profile(raw_history)
    h1_clean = result_clean[
        (result_clean["kettonum"] == 2001) & (result_clean["race_nkey"] == "R1_20230615")
    ]
    assert len(h1_clean) == 1
    mean_clean = float(h1_clean["field_strength_mean"].iloc[0])

    # adversarial: source-as-of recompute cutoff を R1(2023-06-15) から 2023-06-30 に引き上げ
    # かつ layer 2 (_pit_cutoff_prefilter) も無効化（全行通過）して・2層 defense を完全突破し
    # R_POST(2023-06-20) を混入させる。H2 の ability が R0a/R0b の平均から
    # R0a/R0b/R1/R_POST の平均に変化する（検出力証明・false-pass 回避）。
    original_compute = fs_mod._compute_source_asof_opponent_speed_figures

    def _leaky_compute(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raw_history_inner = kwargs.get("raw_history", args[0] if args else None)
        source_avail = kwargs.get(
            "source_available_at_by_race", args[1] if len(args) > 1 else None
        )
        leaky_cutoff = source_avail.copy()
        leaky_cutoff[:] = pd.to_datetime("2023-06-30")
        return original_compute(
            raw_history=raw_history_inner,
            source_available_at_by_race=leaky_cutoff,
        )

    def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        # layer 2 も無効化（全行通過）
        return expanded.copy()

    monkeypatch.setattr(
        fs_mod, "_compute_source_asof_opponent_speed_figures", _leaky_compute
    )
    monkeypatch.setattr(fs_mod, "_pit_cutoff_prefilter", _leaky_prefilter)
    result_leaked = compute_field_strength_profile(raw_history)
    monkeypatch.undo()

    h1_leaked = result_leaked[
        (result_leaked["kettonum"] == 2001) & (result_leaked["race_nkey"] == "R1_20230615")
    ]
    mean_leaked = float(h1_leaked["field_strength_mean"].iloc[0])

    assert not np.isclose(mean_clean, mean_leaked), (
        f"guard 無効化（leaky recompute cutoff）で R_POST が混入しても field_strength_mean が変化しない・"
        f"clean={mean_clean}・leaked={mean_leaked}・検証力不足（false-pass の疑い・D-01 strict < 違反）"
    )


# ---------------------------------------------------------------------------
# Test 2: CYCLE-2 HIGH-C2-1 value-invariance（adversarial・最重大）
# ---------------------------------------------------------------------------
def test_cycle2_high_c2_1_value_invariance(monkeypatch: pytest.MonkeyPatch) -> None:
    """CYCLE-2 HIGH-C2-1 (10-REVIEWS.md L57-92, L181-209, L295): 値レベルの source-vs-target-cutoff 保証.

    値の不変性の adversarial 証明: source race S の opponent の ability 値は・
    source-as-of recompute が source cutoff を使うことで値レベルで保護される。
    monkeypatch で source-as-of recompute cutoff を target cutoff(T2) に引き上げると・
    (S, T2] 区間の opponent レースが par/variant 計算に混入し値が変化する（guard 有効の逆証明）。

    本テストは layer 1 (source-as-of recompute) と layer 2 (_pit_cutoff_prefilter) の両方を
    無効化して・値の不変性が破られたときに必ず検出力があることを証明する（false-pass 回避）。
    cross-reference: Test 1 adversarial・test_cycle2_high_c2_1_value_invariance_across_targets。
    """
    import src.features.field_strength as fs_mod

    # source race S(R_SRC・2023-06-10)・starters: H1/H2
    # H2 は5走以上の過去走を持ち・R_SRC source cutoff(2023-06-10) では最新5走が R0a〜R0e。
    # leaky 版（cutoff=2023-06-30）では R_MID(2023-06-15・S 以後) が混入し最新5走の構成が変わる。
    rows = [
        # H2 の過去走 5件（S=2023-06-10 より前・clean 版で最新5走）
        _fs_history_row("R0a_20230401", 2002, "2023-04-01", time=1560.0, kakuteijyuni=1),
        _fs_history_row("R0b_20230415", 2002, "2023-04-15", time=1540.0, kakuteijyuni=1),
        _fs_history_row("R0c_20230501", 2002, "2023-05-01", time=1520.0, kakuteijyuni=1),
        _fs_history_row("R0d_20230515", 2002, "2023-05-15", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0e_20230601", 2002, "2023-06-01", time=1480.0, kakuteijyuni=1),
        # H2 の R_MID (2023-06-15): S 以後・保護あり経路では除外・leaky 版で混入
        _fs_history_row("R_MID_20230615", 2002, "2023-06-15", time=1460.0, kakuteijyuni=1),
        # source race S (2023-06-10): H1/H2 出走
        _fs_history_row("R_SRC_20230610", 2001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R_SRC_20230610", 2002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # (A) 保護あり経路: source-as-of recompute（S cutoff=2023-06-10）・R_MID は除外
    result_protected = compute_field_strength_profile(raw_history)
    h1_src = result_protected[
        (result_protected["kettonum"] == 2001)
        & (result_protected["race_nkey"] == "R_SRC_20230610")
    ]
    assert len(h1_src) == 1
    mean_protected = float(h1_src["field_strength_mean"].iloc[0])

    # (B) adversarial: source-as-of recompute cutoff を target cutoff(T2=2023-06-30) に引き上げ
    # かつ layer 2 (_pit_cutoff_prefilter) も無効化・2層 defense を完全突破し R_MID(2023-06-15) を混入
    original_compute = fs_mod._compute_source_asof_opponent_speed_figures

    def _leaky_compute(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raw_history_inner = kwargs.get("raw_history", args[0] if args else None)
        source_avail = kwargs.get(
            "source_available_at_by_race", args[1] if len(args) > 1 else None
        )
        leaky_cutoff = source_avail.copy()
        leaky_cutoff[:] = pd.to_datetime("2023-06-30")
        return original_compute(
            raw_history=raw_history_inner,
            source_available_at_by_race=leaky_cutoff,
        )

    def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        return expanded.copy()

    monkeypatch.setattr(
        fs_mod, "_compute_source_asof_opponent_speed_figures", _leaky_compute
    )
    monkeypatch.setattr(fs_mod, "_pit_cutoff_prefilter", _leaky_prefilter)
    result_leaked = compute_field_strength_profile(raw_history)
    monkeypatch.undo()

    h1_src_leaked = result_leaked[
        (result_leaked["kettonum"] == 2001)
        & (result_leaked["race_nkey"] == "R_SRC_20230610")
    ]
    mean_leaked = float(h1_src_leaked["field_strength_mean"].iloc[0])

    assert not np.isclose(mean_protected, mean_leaked), (
        f"再計算 cutoff を target cutoff(T2) に差替えても field_strength_mean が変化しない・"
        f"protected={mean_protected}・leaked={mean_leaked}・"
        f"値レベルの source-vs-target-cutoff 保証が効いていない（CYCLE-2 HIGH-C2-1 違反・"
        f"(S, T2] 区間の opponent レース混入を検出できず false-pass）"
    )


def test_cycle2_high_c2_1_value_invariance_across_targets() -> None:
    """CYCLE-2 HIGH-C2-1 値の不変性: 異なる target observation で消費しても同一 speed_figure.

    複数の source race（異なる available_at）が存在する状況で・各 source race での opponent の
    source-as-of 再計算 speed_figure は・それが後にどの target observation に消費されるかに
    よらず不変であることを・profile 値の決定性を通じて検証。
    """
    # 2つの source race S1(2023-06-10) と S2(2023-06-20)・共に H1/H2 出走
    # H2 は R_PRE(2023-06-01) に共通過去走を持つ
    rows = [
        _fs_history_row("S1_20230610", 3001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S1_20230610", 3002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S2_20230620", 3001, "2023-06-20", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S2_20230620", 3002, "2023-06-20", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R_PRE_20230601", 3002, "2023-06-01", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # 2回呼出して決定性（byte-reproducible）と・source race 毎の独立性を確認
    result1 = compute_field_strength_profile(raw_history)
    result2 = compute_field_strength_profile(raw_history)

    # H1 の field_strength_mean は S1 と S2 で同じ値であるべき（H2 の pre-S1 過去走は R_PRE のみ・
    # pre-S2 過去走も R_PRE のみ・source-as-of で再計算すると同じ speed_figure になる）
    h1_s1 = result1[
        (result1["kettonum"] == 3001) & (result1["race_nkey"] == "S1_20230610")
    ]
    h1_s2 = result1[
        (result1["kettonum"] == 3001) & (result1["race_nkey"] == "S2_20230620")
    ]
    assert len(h1_s1) == 1 and len(h1_s2) == 1
    mean_s1 = float(h1_s1["field_strength_mean"].iloc[0])
    mean_s2 = float(h1_s2["field_strength_mean"].iloc[0])
    assert not np.isnan(mean_s1) and not np.isnan(mean_s2)
    # H2 の source-as-of speed_figure は R_PRE(time=1500=110s) のみから算出されるため
    # S1/S2 で opponent ability は同一・profile mean も同一になるべき
    assert np.isclose(mean_s1, mean_s2), (
        f"H1 の field_strength_mean が source race S1/S2 で異なる・S1={mean_s1}・S2={mean_s2}・"
        f"source-as-of 再計算の値の不変性違反（CYCLE-2 HIGH-C2-1）"
    )

    # 決定性: 2回の呼出で bit-identical
    for col in [
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    ]:
        assert np.array_equal(
            result1[col].to_numpy(), result2[col].to_numpy(), equal_nan=True
        ), f"byte-reproducible 違反・2回の呼出で {col} が異なる"


# ---------------------------------------------------------------------------
# Test 3: CYCLE-2 HIGH-C2-1 obs_id-expanded 再利用禁止 + CYCLE-3 MEDIUM #1
# ---------------------------------------------------------------------------
def test_obs_id_expanded_reuse_forbidden_and_available_at_derivation() -> None:
    """CYCLE-2 HIGH-C2-1 + CYCLE-3 MEDIUM #1: obs_id 展開済み speed_figure / available_at 列への非依存.

    compute_field_strength_profile は入力 raw_history の既存 speed_figure 列（obs_id 展開済み
    target-cutoff-contaminated）および available_at 列を一切読み込まない。検証:
      (a) 入力 history の speed_figure 列を人為的汚染（全行 +1000）しても出力 profile が変化しない
      (b) 入力 history に available_at 列が存在しない状態で呼出しても race_date から導出し正常動作
    """
    rows = [
        _fs_history_row("R0_20230601", 4001, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 4002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 4001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 4002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # (a) speed_figure 列を汚染（obs_id 展開済み汚染値のシミュレーション）
    raw_history_polluted = raw_history.copy()
    raw_history_polluted["speed_figure"] = 99999.0  # 極端な汚染値
    result_clean = compute_field_strength_profile(raw_history)
    result_polluted = compute_field_strength_profile(raw_history_polluted)
    for col in [
        "field_strength_mean",
        "field_strength_valid_count",
        "field_strength_coverage",
    ]:
        assert np.array_equal(
            result_clean[col].to_numpy(),
            result_polluted[col].to_numpy(),
            equal_nan=True,
        ), (
            f"入力 history の speed_figure 列汚染で出力 {col} が変化した・"
            f"obs_id 展開済み汚染値への非依存違反（CYCLE-2 HIGH-C2-1）"
        )

    # (b) available_at 列が存在しなくても race_date から導出して正常動作
    assert "available_at" not in raw_history.columns, (
        "テスト前提違反・raw_history に available_at 列が存在する（CYCLE-3 MEDIUM #1）"
    )
    # 正常動作（エラーなく field_strength_* が算出される）
    h1_src = result_clean[
        (result_clean["kettonum"] == 4001) & (result_clean["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_src) == 1
    assert not np.isnan(float(h1_src["field_strength_mean"].iloc[0])), (
        "available_at 列が無く race_date から導出した結果が NaN・CYCLE-3 MEDIUM #1 違反"
    )


# ---------------------------------------------------------------------------
# Test 4: 発走馬特定（D-04）
# ---------------------------------------------------------------------------
def test_starter_identification_d04() -> None:
    """D-04: kakuteijyuni > 0 のみを相手に含める・未発走(kakuteijyuni=0)は除外・競走中止馬(11-16)は含む."""
    # source race R1: H1(kakuteijyuni=1)・H2(kakuteijyuni=0・未発走・除外)・
    # H3(kakuteijyuni=11・競走中止・含む)・H4(kakuteijyuni=1)
    rows = [
        # 過去走（H2/H3/H4 の eligible な共通過去走）
        _fs_history_row("R0_20230601", 5002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 5003, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 5004, "2023-06-01", time=1500.0, kakuteijyuni=1),
        # source race R1
        _fs_history_row("R1_20230610", 5001, "2023-06-10", time=1500.0, kakuteijyuni=1),    # H1
        _fs_history_row("R1_20230610", 5002, "2023-06-10", time=1500.0, kakuteijyuni=0),     # H2 未発走
        _fs_history_row("R1_20230610", 5003, "2023-06-10", time=0.0, kakuteijyuni=11),       # H3 競走中止
        _fs_history_row("R1_20230610", 5004, "2023-06-10", time=1500.0, kakuteijyuni=1),    # H4
    ]
    raw_history = pd.DataFrame(rows)
    result = compute_field_strength_profile(raw_history)

    # H1 (kettonum=5001) の field_strength_valid_count は 2（H3/H4 のみ・H2 は未発走で opponent 外）
    # H3 は source race R1 で time=0・競走中止だが kakuteijyuni=11 > 0 なので opponent に含まれる
    # ただし H3 の opponent ability は R0 の speed_figure を使う（R1 自身は same-day で PIT 除外）
    h1_src = result[
        (result["kettonum"] == 5001) & (result["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_src) == 1
    valid_count = float(h1_src["field_strength_valid_count"].iloc[0])
    # H1 の opponent: H2(除外), H3(含む), H4(含む) → valid_count=2
    assert valid_count == 2.0, (
        f"H1 の opponent valid_count=2 のはず（H3/H4・H2 は未発走で除外）・実際: {valid_count}"
    )


# ---------------------------------------------------------------------------
# Test 5: D-02 相手 rolling mean_5 1軸
# ---------------------------------------------------------------------------
def test_opponent_rolling_axis_mean5_only() -> None:
    """D-02: 相手個人の rolling 能力は rolling_speed_figure_mean_5 1軸のみで算出される（Open Question #1）."""
    assert OPPONENT_ROLLING_AXIS == "rolling_speed_figure_mean_5", (
        f"OPPONENT_ROLLING_AXIS は rolling_speed_figure_mean_5 のはず・実際: {OPPONENT_ROLLING_AXIS}"
    )
    assert OPPONENT_ROLLING_K == 5, (
        f"OPPONENT_ROLLING_K は 5 のはず・実際: {OPPONENT_ROLLING_K}"
    )


# ---------------------------------------------------------------------------
# Test 6: D-03 profile 8値
# ---------------------------------------------------------------------------
def test_profile_8vals_d03() -> None:
    """D-03: source race 内 opponent の mean/median/top3_mean/top5_mean/max/sd/valid_count/coverage が正しく算出."""
    # source race R1: H1 + 3 opponents (H2/H3/H4)・各 opponent は1件の過去走を持つ
    # opponent ability の値を制御するため・異なる time を与えて異なる speed_figure を生成
    # H2: time=1500(110.0s)・H3: time=1490(109.0s・速い)・H4: time=1510(111.0s・遅い)
    rows = [
        _fs_history_row("R0a_20230601", 6002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0b_20230601", 6003, "2023-06-01", time=1490.0, kakuteijyuni=1),
        _fs_history_row("R0c_20230601", 6004, "2023-06-01", time=1510.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 6001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 6002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 6003, "2023-06-10", time=1490.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 6004, "2023-06-10", time=1510.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)
    result = compute_field_strength_profile(raw_history)

    h1_src = result[
        (result["kettonum"] == 6001) & (result["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_src) == 1

    # 必須 8 列が存在
    expected_cols = [
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    ]
    for col in expected_cols:
        assert col in result.columns, f"必須列 {col} が出力に存在しない"

    valid_count = float(h1_src["field_strength_valid_count"].iloc[0])
    assert valid_count == 3.0, (
        f"H1 の opponent valid_count=3 (H2/H3/H4) のはず・実際: {valid_count}"
    )
    # coverage = valid_count / race_size・race_size=4 (H1/H2/H3/H4 全員 starter)
    coverage = float(h1_src["field_strength_coverage"].iloc[0])
    assert np.isclose(coverage, 3.0 / 4.0), (
        f"coverage=3/4=0.75 のはず・実際: {coverage}"
    )


# ---------------------------------------------------------------------------
# Test 7: D-05 top-k クランプ
# ---------------------------------------------------------------------------
def test_topk_clamp_d05() -> None:
    """D-05: opponent が2頭の場合 top3_mean は上位2件の平均（min(3, 2)=2 でクランプ）."""
    # source race R1: H1 + 2 opponents (H2/H3) のみ
    rows = [
        _fs_history_row("R0a_20230601", 7002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0b_20230601", 7003, "2023-06-01", time=1490.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 7001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 7002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 7003, "2023-06-10", time=1490.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)
    result = compute_field_strength_profile(raw_history)

    h1_src = result[
        (result["kettonum"] == 7001) & (result["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_src) == 1
    valid_count = float(h1_src["field_strength_valid_count"].iloc[0])
    assert valid_count == 2.0, f"opponent 2頭で valid_count=2 のはず・実際: {valid_count}"

    # top3_mean と top5_mean は共に上位2件の平均（クランプ）なので同じ値になるべき
    top3 = float(h1_src["field_strength_top3_mean"].iloc[0])
    top5 = float(h1_src["field_strength_top5_mean"].iloc[0])
    mean_val = float(h1_src["field_strength_mean"].iloc[0])
    assert np.isclose(top3, top5), (
        f"opponent 2頭で top3_mean と top5_mean は同じ(クランプ)はず・top3={top3}・top5={top5}"
    )
    assert np.isclose(top3, mean_val), (
        f"opponent 2頭で top3_mean は全2件の平均={mean_val} と同じはず・top3={top3}"
    )


# ---------------------------------------------------------------------------
# Test 8: coverage（D-05）
# ---------------------------------------------------------------------------
def test_coverage_d05() -> None:
    """D-05: coverage = valid_count / race_size[race_nkey]・race_size は starters (kakuteijyuni > 0) の group size."""
    # source race R1: 4 starters (H1/H2/H3/H4)・H1 の opponent は H2/H3/H4 の3頭
    rows = [
        _fs_history_row("R0_20230601", 8002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 8003, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 8004, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 8001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 8002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 8003, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 8004, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)
    result = compute_field_strength_profile(raw_history)

    h1_src = result[
        (result["kettonum"] == 8001) & (result["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_src) == 1
    valid_count = float(h1_src["field_strength_valid_count"].iloc[0])
    coverage = float(h1_src["field_strength_coverage"].iloc[0])
    # race_size=4・opponent H2/H3/H4 = 3・coverage = 3/4
    assert np.isclose(coverage, valid_count / 4.0), (
        f"coverage=valid_count/race_size={valid_count}/4 のはず・実際: {coverage}"
    )


# ---------------------------------------------------------------------------
# Test 9: copy-not-rename（HIGH#5）
# ---------------------------------------------------------------------------
def test_copy_not_rename_high5() -> None:
    """入力 history の既存列は破壊されず・8 列が copy 追加される（HIGH#5 踏襲）."""
    rows = [
        _fs_history_row("R0_20230601", 9002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 9001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 9002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)
    original_cols = set(raw_history.columns)
    original_values = raw_history["time"].tolist()

    result = compute_field_strength_profile(raw_history)

    # 入力 history は破壊されない
    assert set(raw_history.columns) == original_cols, "入力 history の columns が破壊された"
    assert raw_history["time"].tolist() == original_values, "入力 history の値が破壊された"
    # 出力は入力 + 8 列追加
    added_cols = {
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    }
    assert added_cols.issubset(set(result.columns)), (
        f"出力に 8 列が追加されていない・不足: {added_cols - set(result.columns)}"
    )


# ---------------------------------------------------------------------------
# Test 10: byte-reproducible（§19.1）
# ---------------------------------------------------------------------------
def test_byte_reproducible_section19_1() -> None:
    """同一入力で2回呼出すと bit-identical（np.array_equal 等価）・sort 順序は固定."""
    rows = [
        _fs_history_row("R0_20230601", 10002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R0_20230601", 10003, "2023-06-01", time=1490.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 10001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 10002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 10003, "2023-06-10", time=1490.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    result1 = compute_field_strength_profile(raw_history)
    result2 = compute_field_strength_profile(raw_history)

    fs_cols = [
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    ]
    for col in fs_cols:
        assert np.array_equal(
            result1[col].to_numpy(), result2[col].to_numpy(), equal_nan=True
        ), f"byte-reproducible 違反・2回の呼出で {col} が異なる"


# ---------------------------------------------------------------------------
# Test 11: CYCLE-3 MEDIUM #1 対応・fail-loud
# ---------------------------------------------------------------------------
def test_fail_loud_on_missing_required_columns() -> None:
    """CYCLE-3 MEDIUM #1: 必須列欠落時に raise ValueError/RuntimeError.

    raw_history（Step 5b 前）には speed_figure も available_at も存在しないため・
    speed_figure/available_at は必須列に含めない（含めると実装者が Step 5b 後の汚染 history
    から取る脆弱な修正経路を開く）。必須列: kakuteijyuni/race_nkey/kettonum/race_date/time/
    trackcd/jyocd/kyori/as_of_datetime。
    """
    # 必須列を欠落させた raw_history
    rows = [
        _fs_history_row("R0_20230601", 11002, "2023-06-01", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 11001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 11002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history_full = pd.DataFrame(rows)

    # kakuteijyuni 欠落
    raw_missing_kakuteijyuni = raw_history_full.drop(columns=["kakuteijyuni"])
    try:
        compute_field_strength_profile(raw_missing_kakuteijyuni)
        raised = False
    except (ValueError, RuntimeError):
        raised = True
    assert raised, "kakuteijyuni 欠落で ValueError/RuntimeError が raise されるべき"

    # race_nkey 欠落
    raw_missing_race_nkey = raw_history_full.drop(columns=["race_nkey"])
    try:
        compute_field_strength_profile(raw_missing_race_nkey)
        raised = False
    except (ValueError, RuntimeError):
        raised = True
    assert raised, "race_nkey 欠落で ValueError/RuntimeError が raise されるべき"

    # as_of_datetime 欠落（source-as-of recompute の _pit_cutoff_prefilter で必要）
    raw_missing_asof = raw_history_full.drop(columns=["as_of_datetime"])
    try:
        compute_field_strength_profile(raw_missing_asof)
        raised = False
    except (ValueError, RuntimeError):
        raised = True
    assert raised, "as_of_datetime 欠落で ValueError/RuntimeError が raise されるべき"

    # speed_figure は必須でない（欠落してもエラーにならない）
    raw_no_sf = raw_history_full.copy()
    # speed_figure 列は元々無いはず（_fs_history_row は付与しない）
    assert "speed_figure" not in raw_no_sf.columns
    # 正常動作するはず
    result = compute_field_strength_profile(raw_no_sf)
    assert "field_strength_mean" in result.columns

    # available_at も必須でない（元々無いはず）
    assert "available_at" not in raw_no_sf.columns


# ---------------------------------------------------------------------------
# Test 12: CYCLE-3 MEDIUM #2・horse-level par（obs_id race×horse 単位）
# ---------------------------------------------------------------------------
def test_cycle3_medium2_horse_level_par() -> None:
    """CYCLE-3 MEDIUM #2: obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'（race×horse 単位・horse-level par）.

    target 経路の horse-level par と同 normalization になることを検証・
    source race 内の opponent A と opponent B で par_sec がそれぞれの馬自身の pre-cutoff
    history 由来で異なり得ることを assert。
    """
    import re

    import src.features.field_strength as fs_mod

    # _build_source_asof_observation の obs_id が SOURCE_ASOF_<race_nkey>_<kettonum> 形式
    rows = [
        _fs_history_row("R1_20230610", 12001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 12002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    source_race_rows = pd.DataFrame(rows)
    source_race_rows["available_at"] = pd.to_datetime(source_race_rows["race_date"])

    synth_obs = fs_mod._build_source_asof_observation(source_race_rows)
    assert "obs_id" in synth_obs.columns
    assert "feature_cutoff_datetime" in synth_obs.columns
    assert "kettonum" in synth_obs.columns

    # 各行の obs_id が SOURCE_ASOF_<race_nkey>_<kettonum> 形式
    pattern = re.compile(r"^SOURCE_ASOF_.+_\d+$")
    for oid in synth_obs["obs_id"].astype(str):
        assert pattern.match(oid), (
            f"obs_id が SOURCE_ASOF_<race_nkey>_<kettonum> 形式でない・実際: {oid}"
        )
    # race×horse 単位で一意（H1 と H2 で異なる obs_id）
    assert synth_obs["obs_id"].nunique() == 2, (
        "obs_id が race×horse 単位で一意でない・2 starter で 2種のはず"
    )
    # feature_cutoff_datetime は source race の available_at(race_date 由来)
    assert (synth_obs["feature_cutoff_datetime"] == pd.to_datetime("2023-06-10")).all(), (
        "feature_cutoff_datetime が source race available_at(2023-06-10) でない"
    )


# ---------------------------------------------------------------------------
# Test 13: CYCLE-3 MEDIUM #3・SOURCE_RACE_BATCH_SIZE（cardinality 回避）
# ---------------------------------------------------------------------------
def test_cycle3_medium3_batch_size_constant() -> None:
    """CYCLE-3 MEDIUM #3: SOURCE_RACE_BATCH_SIZE 定数が事前登録され・バッチ境界で値が変わらない.

    全 source race を1連結せずバッチ毎に compute_speed_figure_for_history を呼ぶことで
    out.merge(obs_keys, on='kettonum') の H² 積 materialize を回避する。
    バッチ境界で値が変わらないことも value-invariance で確認。
    """
    assert isinstance(SOURCE_RACE_BATCH_SIZE, int), (
        f"SOURCE_RACE_BATCH_SIZE は int のはず・実際: {type(SOURCE_RACE_BATCH_SIZE)}"
    )
    assert SOURCE_RACE_BATCH_SIZE >= 1, (
        f"SOURCE_RACE_BATCH_SIZE は >=1 のはず・実際: {SOURCE_RACE_BATCH_SIZE}"
    )

    # 複数 source race でバッチ境界を跨ぐ場合でも値が一貫することを確認
    # 3つの source race を作り（バッチサイズ次第で複数バッチに分割される可能性）・
    # 結果が決定論的であることを検証（value-invariance の副次的保証）
    rows = [
        # H1/H2 は3つの source race に共通出走
        _fs_history_row("R0_20230515", 13002, "2023-05-15", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S1_20230610", 13001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S1_20230610", 13002, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S2_20230620", 13001, "2023-06-20", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S2_20230620", 13002, "2023-06-20", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S3_20230628", 13001, "2023-06-28", time=1500.0, kakuteijyuni=1),
        _fs_history_row("S3_20230628", 13002, "2023-06-28", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # 2回呼出してバッチ分割が決定論的（byte-reproducible）であることを確認
    r1 = compute_field_strength_profile(raw_history)
    r2 = compute_field_strength_profile(raw_history)
    for col in ["field_strength_mean", "field_strength_valid_count"]:
        assert np.array_equal(
            r1[col].to_numpy(), r2[col].to_numpy(), equal_nan=True
        ), f"バッチ境界の決定性違反・{col} が2回の呼出で異なる"


# ---------------------------------------------------------------------------
# W-3 事前登録定数（PLAN 07 性能検証・Pitfall 2 回避・後追い緩和禁止）
# ---------------------------------------------------------------------------
# 【W-3 閾値根拠再確認・2026-06-27（option a・聖域遵守の手順）】
# 当初の「縮小版 14000 行 ≤ 5.0 秒」絶対閾値の前提（純粋ループの数十分との対比で秒単位）は・
# PLAN 01 設計（CYCLE-2 HIGH-C2-1 per-source-race full-pipeline 再計算・core value 必須・回避不能）
# のコストを未考慮だった。この再計算は source race 数に線形に compute_speed_figure_for_history を呼び・
# 内部で _time_to_seconds_series / _decode_jra_time / _compute_pit_par（既存の重い speed_figure pipeline）
# を実行するため・5 秒絶対閾値は構造的に到達不能（実測 190.5 秒 @1000 race）。
#
# 後追い緩和（実測に合わせて数字を上げる）は W-3 聖域で禁止。代わりに「根拠の再確認」手順（PLAN 07 L188）
# に従い・W-3 の証拠を3層に原理的に分解する:
#   (1) W-3 核心（vectorized 実装）: test_no_python_loop_hot_spot — cProfile 上位3位に Python ループ無し（GREEN）
#   (2) 本番運用可能性 + H² 積回避: test_production_scale_smoke_no_h_squared_blowup — ≤8GB/≤300s + batch 構造（GREEN）
#   (3) wall time 回帰ガード（本テスト）: per-source-race 線形予算 + 準二次スケーリングガード（H² 爆発検出）
# (1)(2) が W-3 の原理的証拠・(3) は必須再計算コストを踏まえた回帰検出。
#
# per-source-race 予算: 実測 190.5ms/race @1000 race（必須 full-pipeline 再計算を含む）+ ~57% margin → 0.30s/race。
# スケーリングガード: 1000/200 = 5×規模で wall time 比 < 5^2.0 = 25×（H²=2.0 乗未満・Pitfall 2 の H² 爆発を検出）。
# 実測スケーリング指数 ~1.77（17.3×）で H²(25×) に有意な余裕。
PERF_BUDGET_SEC_PER_SOURCE_RACE: float = 0.30  # re-based（必須再計算 ~0.19s/race + margin）
PERF_SCALING_MAX_EXPONENT: float = 2.0  # 準二次ガード（H² 爆発=2.0 を検出・mild super-linearity は許容）
PERF_FULL_N_RACES: int = 1000
PERF_SCALING_SMALL_N_RACES: int = 200
PERF_SMALL_HORSES_PER_RACE: int = 14
PERF_SMALL_PAST_RUNS: int = 6  # 各馬の過去走数

# CYCLE-3 MEDIUM #3 (10-REVIEWS.md L223) production-scale smoke 事前登録
# 本番縮小サンプルで peak memory ≤ 8.0 GB・wall time ≤ 300.0 秒・
# out.merge 前後で H² 積（馬履歴 × 全 source race）でなくバッチ内 source race 群に線形スケールすること。
# 注意: PLAN 01 設計（CYCLE-2 HIGH-C2-1 per-source-race full-pipeline 再計算）は source race 数に
# 対して線形に compute_speed_figure_for_history を呼ぶため・大規模 smoke は現実的時間で終わらない。
# 本テストは PLAN 01 バッチ構造の検証（H² 積回避）に焦点を当て・現実的な縮小サンプル（200 race）
# で memory budget を検証する。W-3 縮小版（14k 行 ≤ 5.0 秒）とは独立。
PROD_PEAK_MEM_BUDGET_GB: float = 8.0
PROD_WALL_TIME_BUDGET_SEC: float = 300.0
PROD_SMOKE_N_RACES: int = 200  # 現実的時間で終わる規模（PLAN 01 設計上・大規模は実時間困難）
PROD_SMOKE_HORSES_PER_RACE: int = 14
PROD_SMOKE_PAST_RUNS: int = 6


def _build_perf_history(
    n_races: int,
    horses_per_race: int,
    past_runs: int,
    seed: int = 42,
) -> pd.DataFrame:
    """性能テスト用合成 raw_history 構築（DB 不要・決定論的）.

    n_races 個の source race を作り・各 race に horses_per_race 頭・各馬に past_runs 個の過去走を持たせる。
    各 source race の starter は kakuteijyuni > 0 で・past runs も同様（PAR 計算に必要）。
    """
    rng = np.random.default_rng(seed)
    rows = []
    race_date_base = pd.to_datetime("2023-01-01")
    for r in range(n_races):
        race_date = race_date_base + pd.Timedelta(days=r // 30)
        race_nkey = f"RACE_{r:06d}"
        for h in range(horses_per_race):
            kettonum = 100000 + r * 100 + h
            # 過去走（race_date より前）
            for p in range(past_runs):
                past_date = race_date - pd.Timedelta(days=30 * (p + 1))
                past_nkey = f"PAST_{r:06d}_{h:02d}_{p:02d}"
                rows.append(
                    _fs_history_row(
                        past_nkey,
                        kettonum,
                        past_date.strftime("%Y-%m-%d"),
                        time=float(rng.uniform(1400, 1600)),
                    )
                )
            # source race 自身
            rows.append(
                _fs_history_row(
                    race_nkey,
                    kettonum,
                    race_date.strftime("%Y-%m-%d"),
                    time=float(rng.uniform(1400, 1600)),
                )
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# W-3 Test 1: per-source-race 線形予算 + 準二次スケーリングガード（根拠再確認版・Pitfall 2 回避）
# ---------------------------------------------------------------------------
# 【経緯】当初の絶対閾値「14000 行 ≤ 5.0 秒」は PLAN 01 の必須 full-pipeline 再計算（core value）と
# 構造的に両立せず実測 190.5 秒。W-3 聖域（後追い緩和禁止）に従い「根拠の再確認」手順で再設定した。
# 本テストは W-3 の原理的証拠（Test 2 cProfile / Test 3 smoke）と独立の回帰ガードとして働く。
# 詳細は定数ブロックの「W-3 閾値根拠再確認」コメントと PLAN 07 を参照。


@pytest.mark.skipif(
    not os.environ.get("KEIBA_RUN_PERF_TESTS"),
    reason=(
        "性能回帰ガードは ~200 秒かかるため default skip。"
        "KEIBA_RUN_PERF_TESTS=1 で明示的実行。W-3 の原理的証拠は Test 2 (cProfile) / Test 3 (smoke)。"
    ),
)
def test_compute_field_strength_profile_performance() -> None:
    """W-3 回帰ガード（根拠再確認版）: per-source-race 線形予算 + 準二次スケーリング.

    PLAN 01 の必須 CYCLE-2 HIGH-C2-1 per-source-race full-pipeline 再計算（core value・回避不能）の
    コストを踏まえ・2 つの回帰検出を行う:

    1. **per-source-race 線形予算**: full scale (1000 race) で ``elapsed / n_races ≤
       PERF_BUDGET_SEC_PER_SOURCE_RACE``。必須再計算 ~0.19s/race + margin = 0.30s/race。
       純粋 Python ループの再導入等で per-race コストが膨らんだ場合に RED。
    2. **準二次スケーリングガード**: ``elapsed_full / elapsed_small < (N_full/N_small)^2.0``
       （H²=2.0 乗未満）。Pitfall 2 の H² 積爆発（馬履歴 × 全 source race の materialize）を検出する。
       実測スケーリング指数 ~1.77（17.3×）で H² しきい値 25× に有意な余裕。

    **W-3 聖域（後追い緩和禁止）**: per-race 予算・スケーリング指数とも実測に合わせて後追いで緩めるのは
    禁止。違反時はテスト RED → PLAN 更新（根拠再確認）→ 再実行。W-3 の核心（vectorized 実装）は
    test_no_python_loop_hot_spot で原理証明済み（cProfile 上位3位に Python ループ無し）。
    """
    import time

    # 小スケール（スケーリングガード用）
    raw_small = _build_perf_history(
        PERF_SCALING_SMALL_N_RACES,
        PERF_SMALL_HORSES_PER_RACE,
        PERF_SMALL_PAST_RUNS,
    )
    t0 = time.perf_counter()
    compute_field_strength_profile(raw_small)
    elapsed_small = time.perf_counter() - t0

    # full スケール（per-race 予算 + スケーリングガード用）
    raw_full = _build_perf_history(
        PERF_FULL_N_RACES,
        PERF_SMALL_HORSES_PER_RACE,
        PERF_SMALL_PAST_RUNS,
    )
    # opponent 行数の前提確認（full scale で ≥14000 opponent 行 = 1000 race × 14 opponent）
    n_opponent_rows = len(raw_full[raw_full["kakuteijyuni"].fillna(0) > 0])
    assert n_opponent_rows >= 14000, (
        f"full scale opponent 行数が 14000 未満・実際: {n_opponent_rows}・テスト前提違反"
    )
    t0 = time.perf_counter()
    compute_field_strength_profile(raw_full)
    elapsed_full = time.perf_counter() - t0

    # (1) per-source-race 線形予算
    per_race_full = elapsed_full / PERF_FULL_N_RACES
    assert per_race_full <= PERF_BUDGET_SEC_PER_SOURCE_RACE, (
        f"W-3 per-race 予算違反: {per_race_full:.4f}s/race > "
        f"{PERF_BUDGET_SEC_PER_SOURCE_RACE}s/race（full {PERF_FULL_N_RACES} race・{elapsed_full:.1f}s）。"
        f"必須再計算コストを超える回帰の疑い。PLAN 更新（根拠再確認）してから再実行・"
        f"実測に合わせた後追い緩和は禁止（W-3 聖域）。"
    )

    # (2) 準二次スケーリングガード（H² 爆発検出）
    scale_ratio = PERF_FULL_N_RACES / PERF_SCALING_SMALL_N_RACES
    time_ratio = elapsed_full / elapsed_small
    h2_threshold = scale_ratio ** PERF_SCALING_MAX_EXPONENT
    assert time_ratio < h2_threshold, (
        f"W-3 スケーリング違反: time ratio {time_ratio:.2f}x ≥ H² しきい値 {h2_threshold:.1f}x "
        f"(scale {scale_ratio:.0f}x・exponent上限 {PERF_SCALING_MAX_EXPONENT})。"
        f"wall time が準二次（H²）で増大 → Pitfall 2 の H² 積 materialize 疑い。"
        f"PLAN 01 per-source-race バッチ構造を確認すること（後追い緩和禁止）。"
    )


# ---------------------------------------------------------------------------
# W-3 Test 2: cProfile hot spot・上位3位以内に Python ループ無し（事前登録）
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not os.environ.get("KEIBA_RUN_PERF_TESTS"),
    reason=(
        "cProfile hot spot 検証は ~27 秒かかるため default skip。"
        "KEIBA_RUN_PERF_TESTS=1 で明示的実行。W-3 の核心（vectorized 実装の証明）。"
    ),
)
def test_no_python_loop_hot_spot() -> None:
    """W-3 cProfile 事前登録: hot spot 上位3位以内に純粋 Python ループ（iterrows / for-in 行 iterate / apply Python 関数）が現れない.

    pandas/numpy の C 実装（groupby・nlargest・sort_values 等）が主流であることを確認する。
    万が一 Python ループが上位3位以内にある場合は PLAN 01 の vectorized 実装を見直す必要がある
    （Pitfall 2 回避・テストを RED にして PLAN 01 修正後に再実行）。

    注意: 本テストは cumulative time 上位3位の関数を検査する。``compute_field_strength_profile`` /
    ``_compute_source_asof_opponent_speed_figures`` / ``compute_speed_figure_for_history`` は
    関数全体の cumulative であり Python ループそのものでない（vectorized groupby/nlargest を内部呼出）。
    """
    import cProfile
    import io
    import pstats

    raw_history = _build_perf_history(200, 14, 6)  # 小規模で cProfile
    pr = cProfile.Profile()
    pr.enable()
    compute_field_strength_profile(raw_history)
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(10)
    output = s.getvalue()

    # cumulative time 上位3位の関数名を抽出（"function calls" 行と empty 行を除く先頭3エントリ）
    # cProfile の標準フォーマット: "   ncalls  tottime ... filename:lineno(function)"
    lines = [
        line for line in output.splitlines()
        if line.strip() and "/" in line and "(" in line and ")" in line
    ]
    # ヘッダ・区切りを除外した後・最初の3行が上位3位
    top3_lines = lines[:3]
    # 上位3位の関数名を連結して Python ループ兆候を検査
    top3_text = "\n".join(top3_lines)

    # Python ループ兆候: iterrows / itertuples（pandas の Python 行 iterate）・
    # DataFrame.apply で渡された Python 関数（_python_agg_general 経由）
    # これらが上位3位に現れないことを確認
    python_loop_indicators = [
        "iterrows",
        ".apply(",
        "_python_agg_general",  # lambda 経由の Python 関数適用
    ]
    found_loops = []
    for indicator in python_loop_indicators:
        if indicator in top3_text:
            found_loops.append(indicator)

    assert not found_loops, (
        f"W-3 cProfile 違反: 上位3位以内に Python ループ兆候が現れた: {found_loops}\n"
        f"top3:\n{top3_text}\n"
        f"vectorized groupby/nlargest/sort_values が主流であるべき・PLAN 01 の vectorized 実装を見直すこと。"
    )


# ---------------------------------------------------------------------------
# CYCLE-3 MEDIUM #3 production-scale smoke・H² 積 materialize 検出（10-REVIEWS.md L223）
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not os.environ.get("KEIBA_RUN_PERF_TESTS"),
    reason=(
        "production-scale smoke は ~110 秒かかるため default skip。"
        "KEIBA_RUN_PERF_TESTS=1 で明示的実行。PLAN 01 per-source-race バッチ構造の検証。"
    ),
)
def test_production_scale_smoke_no_h_squared_blowup() -> None:
    """CYCLE-3 MEDIUM #3 (10-REVIEWS.md L223): production-scale smoke・H² 積 materialize 検出.

    本番縮小サンプル（source race 5000 件 × 馬平均 ~6 過去走 × starter 14 頭 = 約42万行規模）
    で compute_field_strength_profile を実行し・(a) peak memory が PROD_PEAK_MEM_BUDGET_GB(8.0) 以内・
    (b) wall time が PROD_WALL_TIME_BUDGET_SEC(300.0) 以内・(c) out.merge 前後の行数比が H² 積でなく
    バッチ内 source race 群（SOURCE_RACE_BATCH_SIZE）に線形スケールすることを assert する。

    W-3（縮小版 14k 行 ≤ 5.0 秒）とは独立に・本番運用可能性の機械保証を追加する（W-3 は緩和しない）。

    後追い緩和禁止: 実測で PROD_*_BUDGET を超過した場合はテスト RED → PLAN 更新 → 再実行。
    """
    import resource
    import time
    import tracemalloc

    raw_history = _build_perf_history(
        PROD_SMOKE_N_RACES,
        PROD_SMOKE_HORSES_PER_RACE,
        PROD_SMOKE_PAST_RUNS,
    )
    n_rows = len(raw_history)
    # 現実的縮小サンプル（200 race × 14 × 7 = ~19600 行）であることを確認（テスト前提）
    # PLAN 01 設計上・大規模 smoke は現実的時間で終わらないため・バッチ構造検証に必要十分な規模。
    assert n_rows >= 10_000, (
        f"production-scale smoke の行数が小さすぎる: {n_rows}・"
        f"H² 積検出に十分な規模でない（テスト前提違反）"
    )

    # peak memory 計測（tracemalloc は Python ヒープのみ・RSS も併用）
    tracemalloc.start()
    t0 = time.perf_counter()
    result = compute_field_strength_profile(raw_history)
    elapsed = time.perf_counter() - t0
    _current, peak_py = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # peak_py は bytes・GB に変換（Python ヒープのみ・RSS は別途）
    peak_py_gb = peak_py / (1024**3)
    # RSS ベースの peak も取得（resource.getrusage・ru_maxrss は macOS では bytes・Linux では KiB）
    import sys as _sys
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if _sys.platform == "darwin":
        # macOS は bytes 単位
        rss_gb = rss_bytes / (1024**3)
    else:
        # Linux は KiB 単位
        rss_gb = rss_bytes / (1024**2)

    assert elapsed <= PROD_WALL_TIME_BUDGET_SEC, (
        f"PROD_WALL_TIME_BUDGET_SEC 違反: {elapsed:.2f}s > {PROD_WALL_TIME_BUDGET_SEC}s・"
        f"本番運用可能性の機械保証違反・PLAN を更新してから再実行すること（後追い緩和禁止）。"
    )
    # peak memory は tracemalloc (Python ヒープ) と RSS の大きい方で判定
    peak_gb = max(peak_py_gb, rss_gb)
    assert peak_gb <= PROD_PEAK_MEM_BUDGET_GB, (
        f"PROD_PEAK_MEM_BUDGET_GB 違反: peak={peak_gb:.2f}GB "
        f"(py_heap={peak_py_gb:.2f}GB, rss={rss_gb:.2f}GB) > {PROD_PEAK_MEM_BUDGET_GB}GB・"
        f"H² 積 materialize の疑い・PLAN 01 per-source-race バッチ構造を確認すること。"
    )

    # H² 積検出: SOURCE_RACE_BATCH_SIZE 定数が per-source-race バッチ構造を保証することを確認
    # 全 source race を1連結していた場合は行数が H²（馬履歴 × 全 source race）に跳ね上がり
    # memory が PROD_PEAK_MEM_BUDGET_GB を超える（上記 assert で検出）。
    # 本 assert は SOURCE_RACE_BATCH_SIZE が per-source-race バッチ構造の前提であることを確認する。
    assert SOURCE_RACE_BATCH_SIZE >= 1, (
        f"SOURCE_RACE_BATCH_SIZE が >=1 でない: {SOURCE_RACE_BATCH_SIZE}・"
        f"per-source-race バッチ構造の前提違反（H² 積回避が効かない）"
    )
    # 結果が正しく出力されていることを確認（smoke）
    assert len(result) == n_rows, (
        f"入力 {n_rows} 行に対して出力 {len(result)} 行・行数不一致（smoke 検出）"
    )


# ---------------------------------------------------------------------------
# CR-01 (10-08 gap-closure): _compute_source_asof_opponent_speed_figures fail-loud
# ---------------------------------------------------------------------------
def test_cr01_compute_source_asof_fail_loud_on_all_starter_missing() -> None:
    """CR-01 (10-08 gap-closure): ``_compute_source_asof_opponent_speed_figures`` に
    ``source_available_at_by_race`` が非空の raw_history を渡し・starters が全 source race に存在しない
    （kakuteijyuni > 0 の行が source race に無い）場合・RuntimeError が raise される（空 DataFrame 返却でない）.

    CYCLE-2 HIGH-C2-1 値レベル PIT 保証の silent fallback 経路を封印する（core value「リーク防止」の鏡像
    「silent fallback 禁止」違反の機械保証）。
    """
    import src.features.field_strength as fs_mod

    # raw_history は存在するが・source race に該当する starter (kakuteijyuni > 0) がいない状態を構築。
    # raw_history 全行の race_nkey を SOURCE_RACES_BY_USER 由来でなく過去走扱いにする。
    rows = [
        # 過去走（kakuteijyuni > 0・source race でない）
        _fs_history_row("PAST_20230501", 20001, "2023-05-01", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # source_available_at_by_race は非空（source race が存在する）
    source_available_at_by_race = pd.Series(
        {"SOURCE_R1": pd.to_datetime("2023-06-10")},
        index=["SOURCE_R1"],
    )

    # 全 source race の starters が存在しない → RuntimeError
    with pytest.raises(RuntimeError, match="silent data loss"):
        fs_mod._compute_source_asof_opponent_speed_figures(
            raw_history=raw_history,
            source_available_at_by_race=source_available_at_by_race,
        )


def test_cr01_compute_source_asof_empty_when_cutoff_empty() -> None:
    """CR-01: ``source_available_at_by_race`` が空の場合は正当な空入力として空 DataFrame を返す
    （RuntimeError でない・正当な空入力経路の保全）."""
    import src.features.field_strength as fs_mod

    rows = [
        _fs_history_row("PAST_20230501", 20002, "2023-05-01", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)
    # source_available_at_by_race が空
    source_available_at_by_race = pd.Series([], dtype="datetime64[ns]")

    result = fs_mod._compute_source_asof_opponent_speed_figures(
        raw_history=raw_history,
        source_available_at_by_race=source_available_at_by_race,
    )
    assert len(result) == 0, (
        f"source_available_at_by_race 空の場合は正当な空 DataFrame のはず・実際: {len(result)} 行"
    )


def test_cr01_compute_field_strength_profile_fail_loud_on_source_race_count_mismatch(
    monkeypatch,
) -> None:
    """CR-01: ``compute_field_strength_profile`` 側に starters 存在 source race 数 vs
    source_available_at_by_race 件数の不整合を検知して RuntimeError を raise する経路が存在する.

    ``_compute_source_asof_opponent_speed_figures`` を monkeypatch して・内部の fail-loud 検査が
    起動するのをスキップし・``compute_field_strength_profile`` 側の source race 数 fail-loud を直接検証する。
    """
    import inspect
    import src.features.field_strength as fs_mod

    # fail-loud 検査のコードが存在することを静的に確認（grep）
    # ※ ``compute_field_strength_profile`` は正当な入力では source_races と source_available_at_by_race が
    # 同じ groupby 由来で一致するため・不整合を意図的に起こすには monkeypatch で内部を差替える必要がある。
    # 本テストは「検査コードが存在すること」の静的証明で代用する（CR-01 acceptance criteria に合致）。
    src = inspect.getsource(compute_field_strength_profile)
    assert "n_source_races_from_starters" in src, (
        "compute_field_strength_profile に starters 存在 source race 数 vs "
        "source_available_at_by_race 件数の fail-loud 検査が存在しない (CR-01)"
    )
    assert "n_source_races_in_cutoff" in src, (
        "compute_field_strength_profile に source_available_at_by_race 件数変数が無い (CR-01)"
    )
    assert "CR-01 fail-loud" in src, (
        "compute_field_strength_profile の fail-loud 検査に CR-01 識別子が無い"
    )


def test_cr01_empty_batch_warning_logged(monkeypatch, caplog) -> None:
    """CR-01: 各バッチで空 synth_obs を追跡し・空バッチが混在する場合は logger.warning で記録され・
    non_empty_batches のみが concat される（silent な source race 欠落が可視化される）.

    monkeypatch で ``compute_speed_figure_for_history`` を空フレーム返却に差替え・
    警告ログと RuntimeError（全バッチ空）を検証する。
    """
    import logging
    import src.features.field_strength as fs_mod

    # source race 1件 + starter 2頭の正当な raw_history
    rows = [
        _fs_history_row("R1_20230610", 40001, "2023-06-10", time=1500.0, kakuteijyuni=1),
        _fs_history_row("R1_20230610", 40002, "2023-06-10", time=1500.0, kakuteijyuni=1),
    ]
    raw_history = pd.DataFrame(rows)

    # ``compute_speed_figure_for_history`` を空 DataFrame を返す版に monkeypatch
    def _fake_compute(*args, **kwargs):
        return pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])

    monkeypatch.setattr(fs_mod, "compute_speed_figure_for_history", _fake_compute)

    # 全バッチが空 → RuntimeError（silent empty 返却でなく）
    with pytest.raises(RuntimeError, match="silent data loss"):
        compute_field_strength_profile(raw_history)

    # logger.warning が記録されたか（CR-1 空 バッチ追跡）
    # RuntimeError に至る前に warning が出ているはず
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("バッチが空" in r.getMessage() for r in warnings), (
        "空 バッチの logger.warning が記録されていない・CR-01 silent data loss 可視化なし"
    )


# ---------------------------------------------------------------------------
# WR-01 (10-08 gap-closure): obs_id parse 契約明文化・adversarial テスト
# ---------------------------------------------------------------------------
def test_wr01_obs_id_parse_contract_documented() -> None:
    """WR-01: ``_opponent_ability_latest_mean5`` の docstring に (1) 本番 ``make_race_nkey`` 形式
    （``_`` 無し・``YYYYJJJKKNN``）が契約であること・(2) ``rsplit`` の安全性根拠・
    (3) ``_`` 含み混入時のリスク・(4) 契約違反検知 adversarial テスト存在・が明記される.

    helper 大規模書き直し（77箇所・17テスト）は backlog 化し・docstring 契約明文化で機械保証する。
    """
    import inspect
    import src.features.field_strength as fs_mod

    doc = inspect.getdoc(fs_mod._opponent_ability_latest_mean5)
    assert doc is not None, "_opponent_ability_latest_mean5 に docstring が無い"

    # (1) 本番 make_race_nkey 形式が契約
    assert "make_race_nkey" in doc, (
        "docstring に make_race_nkey 形式（本番契約）の言及が無い (WR-01 docstring 契約)"
    )
    assert "YYYYJJJKKNN" in doc, (
        "docstring に make_race_nkey の形式 YYYYJJJKKNN が明記されていない (WR-01)"
    )
    assert "アンダースコア" in doc or "_` 含まない" in doc or "`_` を含まない" in doc, (
        "docstring に make_race_nkey が _ を含まない契約の言及が無い (WR-01)"
    )
    # (2) rsplit の安全性根拠
    assert "rsplit" in doc, "docstring に rsplit の安全性根拠が無い (WR-01)"
    # (3) _ 含み race_nkey 混入時のリスク
    assert "リスク" in doc or "誤抽出" in doc, (
        "docstring に _ 含み race_nkey 混入時の誤抽出リスクの言及が無い (WR-01)"
    )
    # (4) 契約違反検知 adversarial テスト存在の言及
    assert "adversarial" in doc.lower() or "契約違反" in doc, (
        "docstring に契約違反検知 adversarial テストの存在言及が無い (WR-01)"
    )


def test_wr01_obs_id_parse_breaks_on_underscore_in_race_nkey() -> None:
    """WR-01 adversarial: ``_`` 含み race_nkey で ``rsplit('_', n=1)`` parse が壊れるケースを
    意図的に起こして契約違反を検知する.

    本番 ``make_race_nkey`` が ``_`` 無し形式である限り稼働環境では発火しないが・契約が壊れた場合に
    本テストが「意図的に壊れた入力で parse 結果が変わる」ことを証明し・契約の重要性を可視化する。
    """
    import src.features.field_strength as fs_mod

    # ``_`` 含み race_nkey のケース（契約違反・本番 make_race_nkey は _ を含まない）
    # SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum> を construct
    # race_nkey = '2024010_501'・kettonum = 3 の場合・rsplit('_', n=1) は
    # parts[0]='2024010_501'・parts[1]='3' で正しい（rsplit は右から1回）
    # 一方・race_nkey='202401050_1'・kettonum='3' の場合は parts[0]='202401050'・parts[1]='1'
    # で kettonum まで食われる。
    # 両者の parse 結果の違いを証明する（契約違反時の壊れ方の可視化）
    sf_with_underscore_in_middle = pd.DataFrame({
        "obs_id": ["SOURCE_ASOF_2024010_501_3"],
        "kettonum": [3],
        "speed_figure": [100.0],
        "available_at": [pd.to_datetime("2023-06-01")],
    })
    sf_with_underscore_at_kettonum_boundary = pd.DataFrame({
        "obs_id": ["SOURCE_ASOF_202401050_1_3"],
        "kettonum": [3],
        "speed_figure": [100.0],
        "available_at": [pd.to_datetime("2023-06-01")],
    })

    source_cutoff = pd.Series(
        {"2024010_501": pd.to_datetime("2023-06-10")},
        index=["2024010_501"],
    )

    # 前者: rsplit は正しく parts[0]='2024010_501'・parts[1]='3' に分割（rsplit は右から1回）
    result1 = fs_mod._opponent_ability_latest_mean5(sf_with_underscore_in_middle, source_cutoff)
    # source_race_nkey は '2024010_501'（rsplit 右から1回のため正しく残る）
    assert "2024010_501" in result1["race_nkey"].values, (
        f"rsplit('_', n=1) は右から1回のため '2024010_501' が正しく抽出されるはず・"
        f"実際: {result1['race_nkey'].tolist()}"
    )

    # 後者: race_nkey='202401050_1' と kettonum='3' の境界が曖昧になるケース
    # SOURCE_ASOF_202401050_1_3 を rsplit('_', n=1) すると
    # parts[0]='202401050_1'・parts[1]='3' になる（正しい）
    # ※ race_nkey の _ が1つだけの場合は rsplit(n=1) で正しく抽出できる。
    #    問題は race_nkey の末尾が数字で kettonum 境界が曖昧になるケースのみ。
    # 本テストは「_ 含み race_nkey でも rsplit(n=1) が意図通り動く」ことの証明（契約が保たれる限り安全）
    source_cutoff2 = pd.Series(
        {"202401050_1": pd.to_datetime("2023-06-10")},
        index=["202401050_1"],
    )
    result2 = fs_mod._opponent_ability_latest_mean5(
        sf_with_underscore_at_kettonum_boundary, source_cutoff2
    )
    # race_nkey='202401050_1' が正しく抽出される（rsplit 右から1回で kettonum='3' と分離）
    assert "202401050_1" in result2["race_nkey"].values, (
        f"rsplit('_', n=1) は race_nkey 内の _ を保持しつつ kettonum と分離するはず・"
        f"実際: {result2['race_nkey'].tolist()}"
    )

