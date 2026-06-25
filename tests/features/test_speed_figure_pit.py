# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/model/test_trainer.py と同一慣例)
"""SC#2 adversarial（注入型メタ検証）・speed_figure PIT cutoff の false-pass 回避（Phase 9 P01）。

本ファイルは SC#2 adversarial（注入型メタ検証）であり・``tests/features/test_speed_figure.py``
（機能テスト: 正しく除外される）とは独立層。機能テストは「guard 有効で正しく除外される」を
検証するのに対し・本テストは「guard を無効化すると T+1 データが混入する（=リークがあれば
検出される）」ことを5段階鋳型（``tests/audit/test_audit_features.py`` L35-125 構造）で実証し・
false-pass を構造的に排除する（T-09-01 mitigate・per D-03）。

更に REVIEW H4 (cross-observation PIT): cutoff の異なる2 observation で・集約キーに ``obs_id`` が
含まれるため・later observation 専用の介入行が earlier observation の par/variant に漏れないことを
実証する。guard monkeypatch + ``obs_id`` groupby 外しの hack で逆に混入が生じることも機械証明し・
H4 per-observation invariant が guard でなく集約キー仕様に依拠することを示す。

注入手法: ``tests/features/conftest.py::_build_speed_figure_history_rows`` で構築した history の
``previous_day`` 行（cutoff 同日・本来 strict ``<`` で除外されるべき）が・guard monkeypatch 無効化
（``<`` → ``<=``）で混入することを ``speed_figure`` / ``par_sec`` の値変化で機械検出する。

cross-reference: tests/features/test_speed_figure.py（機能テスト・正しく除外される）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.features.speed_figure import compute_speed_figure_for_history
from tests.features.conftest import (
    _build_race_obs_row,
    _build_se_history_row,
    _build_speed_figure_history_rows,
)


def test_lookahead_injection_detected_and_fails() -> None:
    """SC#2 adversarial: PIT guard を無効化すると T+1 データが混入する（false-pass 回避）。

    本テストは SC#2 adversarial（注入型メタ検証）であり・``tests/features/test_speed_figure.py``
    （機能テスト: 正しく除外される）とは独立層。guard を無効化すると T+1 データが混入する
    （=リークがあれば検出される）ことを実証する。cross-reference: tests/features/test_speed_figure.py。

    5段階鋳型（``tests/audit/test_audit_features.py`` L35-125 構造を speed_figure PIT に適用）:

      (1) 合成 history 構築（eligible 3行のみ + adversarial 5行・time 識別値・seed 固定相当）
      (2) guard 有効な通常経路でベースライン取得（eligible 3行の median par_sec=111.0）
      (3) 意図的 T+1 リーク注入（guard monkeypatch で ``<`` → ``<=`` に緩める）
      (4) guard 有効なら混入検出 → 正しい結果（par_sec=111.0 不変）
      (5) guard 無効なら混入する（par_sec 変化）で検証力証明（false-pass 回避・T-09-01 mitigate）
    """
    # --- (1) 合成 history 構築(_build_speed_figure_history_rows で8行・seed 固定相当) ---
    history = _build_speed_figure_history_rows(
        obs_race_date="2023-06-04", kettonum=1001
    )
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_LI")]
    )

    # --- (2) guard 有効な通常経路でベースライン取得 ---
    result_clean = compute_speed_figure_for_history(history, observations=obs)
    eligible_mask = result_clean["row_label"] == "eligible"
    baseline_par_vals = result_clean.loc[eligible_mask, "par_sec"].dropna().unique()
    assert len(baseline_par_vals) == 1, (
        f"baseline: eligible 3行の par_sec は同値・実際: {baseline_par_vals}"
    )
    baseline_par = float(baseline_par_vals[0])
    # eligible 3行: time=1100,1110,1120(ds) → 110.0, 111.0, 112.0 秒 → median 111.0
    assert abs(baseline_par - 111.0) < 1e-9, (
        f"guard 有効なベースライン par_sec が 111.0 でない (actual={baseline_par:.6f}・"
        f"eligible 3行のみ含むべき・previous_day time=996.0 が混入すると跳ね上がる)"
    )

    # --- (3) 意図的 T+1 リーク注入: PIT guard を monkeypatch で無効化(strict < を <= に緩める) ---
    # src/features/speed_figure.py の _pit_cutoff_prefilter を <= 版に差し替え・
    # cutoff 同日(previous_day: as_of == cutoff・time=996.0秒)が混入する経路を真正に作る。
    import src.features.speed_figure as sf_mod

    def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        """guard 無効化版: ``<`` を ``<=`` に緩めて previous_day (as_of == cutoff) を混入させる。"""
        return expanded[
            expanded["as_of_datetime"] <= expanded["feature_cutoff_datetime"]
        ].copy()

    original_prefilter = sf_mod._pit_cutoff_prefilter
    sf_mod._pit_cutoff_prefilter = _leaky_prefilter  # type: ignore[assignment]
    try:
        result_leaked = sf_mod.compute_speed_figure_for_history(history, observations=obs)
    finally:
        # monkeypatch を確実に戻す（test session の他テストに影響しないよう finally で復元）
        sf_mod._pit_cutoff_prefilter = original_prefilter  # type: ignore[assignment]

    # --- (4) guard 有効なら混入検出 → 正しい結果（baseline と一致・機能テストと同じ契約） ---
    result_guard_on = compute_speed_figure_for_history(history, observations=obs)
    par_guard_on_vals = result_guard_on.loc[eligible_mask, "par_sec"].dropna().unique()
    assert len(par_guard_on_vals) == 1, (
        f"guard 有効経路: eligible 3行の par_sec は同値・実際: {par_guard_on_vals}"
    )
    par_guard_on = float(par_guard_on_vals[0])
    assert abs(par_guard_on - baseline_par) < 1e-9, (
        f"guard 有効でも baseline と不一致・strict < feature_cutoff_datetime が効いていない "
        f"(par_guard_on={par_guard_on:.6f}・baseline={baseline_par:.6f}・"
        f"SC#2 adversarial fail・previous_day 混入の疑い)"
    )

    # --- (5) guard 無効（T+1 真正注入）なら混入する → 検証力証明（false-pass 回避） ---
    # previous_day (time=9960 ds → 996.0 秒) が par 算出に混入すると・median が 111.0 から外れる。
    # eligible 3行(110,111,112) + previous_day(996.0) の median = (111+112)/2 = 111.5 (4件の中央値)
    # leak された result は行数が多く（target 等も含む）・eligible_mask を再計算する
    eligible_mask_leaked = result_leaked["row_label"] == "eligible"
    par_leaked_vals: Any = result_leaked.loc[eligible_mask_leaked, "par_sec"].dropna().unique()
    # eligible row の par_sec が混入後の group median に置き換わっているはず
    assert len(par_leaked_vals) >= 1, (
        "T+1 注入で eligible の par_sec が全て NaN になった・検証力証明不能（SC#2 adversarial fail）"
    )
    par_leaked = float(par_leaked_vals[0])
    assert abs(par_leaked - baseline_par) > 1e-6, (
        f"T+1 リーク注入でも baseline (par_sec={baseline_par:.6f}) から変化しない "
        f"(leaked par_sec={par_leaked:.6f}・leak diagnostic が false-pass の疑い・"
        f"T-09-01 mitigate 違反・review HIGH#3 analog)"
    )

    # 最終 assert: guard 有効なら正規経路は GREEN（機能テストと同一契約・注入テストの存在意義）
    assert abs(par_guard_on - 111.0) < 1e-9, (
        "正規経路 (guard 有効) が SC#2 の期待 par_sec=111.0 を満たさない"
    )


def test_docstring_cross_reference() -> None:
    """本テストモジュールの docstring が SC#2 adversarial + cross-reference を含む（T-08-04 mitigate）。

    重複回避: 機能テスト ``tests/features/test_speed_figure.py`` が「正しく除外される」を検証する
    のに対し・本 adversarial テストは「guard 無効化で混入する」を実証する（独立層）。
    """
    import sys

    module_doc = sys.modules[__name__].__doc__ or ""
    assert "SC#2 adversarial" in module_doc, (
        "モジュール docstring に SC#2 adversarial 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/features/test_speed_figure.py" in module_doc, (
        "モジュール docstring に test_speed_figure.py cross-reference がない（T-08-04 違反）"
    )
    test_doc = test_lookahead_injection_detected_and_fails.__doc__ or ""
    assert "SC#2 adversarial" in test_doc and "cross-reference: tests/features/test_speed_figure.py" in test_doc, (
        "テスト docstring に SC#2 adversarial + cross-reference がない（T-08-04 違反）"
    )


def test_cross_observation_pit_no_leak() -> None:
    """REVIEW H4: cutoff の異なる2 observation で cross-observation leak が構造的不能。

    H4: 集約キー = obs_id + jyocd×trackcd×kyori(par)/obs_id + source_race_date×jyocd×surface(variant)。
    cutoff の異なる2 observation 間で・later obs 専用の介入行が earlier obs の par/variant に
    漏れないことを実証。更に guard monkeypatch + obs_id groupby 外し hack で逆に混入が生じることを
    機械証明し・H4 per-obs invariant が guard でなく集約キー仕様に依拠することを示す
    （T-09-28 mitigate・false-pass 回避）。
    """
    # --- 構築: cutoff の異なる2 observation × 同一 jyocd×trackcd×kyori の合成 history ---
    # O_early: race_date=2023-06-04, cutoff=2023-06-03
    # O_late:  race_date=2023-06-11, cutoff=2023-06-10
    # 介入行: race_date=2023-06-05 (as_of=2023-06-05)・time=1200.0 ds (極端な遅い値)
    #   - O_early に対しては as_of(06-05) >= cutoff(06-03) → ineligible
    #   - O_late に対しては  as_of(06-05) <  cutoff(06-10) → eligible
    # base 行: race_date=2023-05-20 (as_of=2023-05-20)・time=1100.0 ds → 両 obs で eligible
    common_kettonum = 4001
    rows = [
        _build_se_history_row(
            kettonum=common_kettonum,
            race_date="2023-05-20",
            as_of_datetime=pd.to_datetime("2023-05-20"),
            time=1100.0,
            trackcd="24",
            kyori=1600,
            jyocd="05",
            kakuteijyuni=1,
            row_label="base_both_pre",
        ),
        _build_se_history_row(
            kettonum=common_kettonum,
            race_date="2023-06-05",
            as_of_datetime=pd.to_datetime("2023-06-05"),
            time=1200.0,
            trackcd="24",
            kyori=1600,
            jyocd="05",
            kakuteijyuni=1,
            row_label="intervention_O_late_only",
        ),
    ]
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", common_kettonum, "2023-06-04", obs_id="O_early"),
        _build_race_obs_row("2023A0617-R1", common_kettonum, "2023-06-11", obs_id="O_late"),
    ])

    # --- (A) 保護あり経路: O_early の par_sec は介入行(120.0秒)の影響を受けない ---
    result = compute_speed_figure_for_history(history, observations=obs)
    # result は展開されているため・obs_id 毎に par_sec を確認
    # O_early の eligible 行は base_both_pre(time=110.0秒)のみ・par_sec = 110.0
    # O_late の eligible 行は base_both_pre(110.0) + intervention(120.0) → median = 115.0
    early_mask = result["obs_id"] == "O_early"
    late_mask = result["obs_id"] == "O_late"
    early_par_vals = result.loc[early_mask, "par_sec"].dropna().unique()
    late_par_vals = result.loc[late_mask, "par_sec"].dropna().unique()
    assert len(early_par_vals) == 1, (
        f"O_early の par_sec は1種類のはず・実際: {early_par_vals}"
    )
    assert abs(float(early_par_vals[0]) - 110.0) < 1e-9, (
        f"O_early の par_sec は base 行のみ(110.0秒)のはず・実際: {early_par_vals[0]}・"
        f"介入行(120.0秒・O_late 専用)が混入した cross-observation leak の疑い（H4 違反）"
    )
    # O_late は base(110.0) + intervention(120.0) → median 115.0
    assert len(late_par_vals) == 1, (
        f"O_late の par_sec は1種類のはず・実際: {late_par_vals}"
    )
    assert abs(float(late_par_vals[0]) - 115.0) < 1e-9, (
        f"O_late の par_sec は base(110.0)+intervention(120.0) の median=115.0 のはず・"
        f"実際: {late_par_vals[0]}"
    )

    # --- (B) obs_id groupby 外し hack で cross-observation leak が生じることを実証 ---
    # この hack は「PIT guard 有効 + 集約キー仕様(obs_id 必須)」の両方が揃って初めて H4 invariant
    # が成立することを示す。PIT guard は有効なまま（strict < を維持）・par groupby キーから
    # obs_id を外すと・PIT filter 後の展開フレーム上で同一 (jyocd,trackcd,kyori) group に
    # O_early と O_late の両 observation の eligible 行が混ざり cross-observation leak が生じる。
    #
    # 検出手段: sample_count の変化。保護あり経路では O_early の sample_count=1（base 行のみ）だが・
    # obs_id groupby 外し hack では O_early の sample_count=3（O_early base + O_late base + O_late intervention
    # が同一 group に混ざるため）。これが cross-observation leak の機械的証拠。
    import src.features.speed_figure as sf_mod

    original_compute_pit_par = sf_mod._compute_pit_par

    def _compute_pit_par_no_obs_id(expanded_filtered: pd.DataFrame) -> pd.DataFrame:
        """H4 違反 hack: par groupby キーから obs_id を外す・cross-observation leak を生じさせる。

        PIT filter 後の展開フレームで obs_id 無しの (jyocd,trackcd,kyori) groupby を行うと・
        O_early と O_late の両 observation の eligible 行が同一 group に混ざる。
        sample_count が observation 毎でなく全体サイズになるため・O_early の sample_count が
        1 → 3 に変化する。これが cross-observation leak の機械的証拠。
        """
        out = expanded_filtered.copy()
        if "time_sec" not in out.columns:
            out["time_sec"] = sf_mod._time_to_seconds_series(out["time"])
        # H4 違反: obs_id を含めない groupby キー
        group_cols = ["jyocd", "trackcd", "kyori"]
        out["par_sec"] = out.groupby(group_cols)["time_sec"].transform("median")
        out["sample_count"] = out.groupby(group_cols)["time_sec"].transform("size")
        out["fallback_level"] = "jyocd_trackcd_kyori"
        return out

    sf_mod._compute_pit_par = _compute_pit_par_no_obs_id  # type: ignore[assignment]
    try:
        result_leaked = sf_mod.compute_speed_figure_for_history(history, observations=obs)
    finally:
        sf_mod._compute_pit_par = original_compute_pit_par  # type: ignore[assignment]

    # 保護あり経路の O_early sample_count は 1（base 行のみ・obs_id group で独立）
    early_count_protected_vals = result.loc[
        result["obs_id"] == "O_early", "sample_count"
    ].dropna().unique()
    assert len(early_count_protected_vals) == 1
    early_count_protected = int(early_count_protected_vals[0])
    assert early_count_protected == 1, (
        f"保護あり O_early sample_count は 1(base 行のみ)のはず・実際: {early_count_protected}"
    )

    # hack 後: O_early sample_count は 3 に変化（cross-observation leak 発生）
    early_count_leaked_vals = result_leaked.loc[
        result_leaked["obs_id"] == "O_early", "sample_count"
    ].dropna().unique()
    assert len(early_count_leaked_vals) == 1, (
        f"hack 後 O_early sample_count は1種類のはず・実際: {early_count_leaked_vals}"
    )
    early_count_leaked = int(early_count_leaked_vals[0])
    assert early_count_leaked == 3, (
        f"hack 後 O_early sample_count は 3(O_early base 1 + O_late base 1 + O_late intervention 1 "
        f"が同一 group に混入)のはず・実際: {early_count_leaked}・"
        f"hack で sample_count が増えないなら H4 invariant の検証力が不十分（false-pass の疑い）"
    )
    # 保護あり/hack ありで sample_count が異なることを最終確認（cross-obs leak の証拠）
    assert early_count_leaked > early_count_protected, (
        f"hack 前後で O_early sample_count が変化しない・検証力証明不能"
        f"（H4 invariant の false-pass の疑い）"
    )
