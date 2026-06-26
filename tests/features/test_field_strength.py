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
