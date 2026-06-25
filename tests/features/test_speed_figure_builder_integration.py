# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/model/test_trainer.py と同一慣例)
"""Phase 9 P03 builder Step 5b と rolling の統合テスト（SC#1/SC#2/SC#3 統合レイヤ）.

本ファイルは ``src/features/builder.py`` の Step 5b 挿入（``compute_speed_figure_for_history``
呼出）と・それが rolling に連鎖して ``rolling_speed_figure_*`` 6 feature を出力する契約を検証する
機能統合テスト。SC#2 adversarial（注入型メタ検証）は ``tests/features/test_speed_figure_pit.py``
に独立層として存在し・本ファイルは PIT 正しさの機能側契約（guard 有効での検証）を担う
（T-08-04 踏襲・機能テストと adversarial の棲み分け）。

cover:
  - builder Step 5b が history に speed_figure 列を追加し rolling が 6 feature を出力（統合）
  - copy-not-rename（既存 history 列は破壊されず speed_figure 追加・HIGH #5）
  - PIT correct（5段階 adversarial history で eligible 3行のみで算出・SC#2 機能側）

cross-reference: tests/features/test_speed_figure.py（SC#1 byte-reproducible・SC#3 parity）。
cross-reference: tests/features/test_speed_figure_pit.py（SC#2 adversarial・guard 無効化で混入実証）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.rolling import build_rolling_features
from src.features.speed_figure import compute_speed_figure_for_history
from tests.features.conftest import (
    _build_race_obs_row,
    _build_se_history_row,
    _build_speed_figure_history_rows,
)


def test_builder_step5b_adds_speed_figure_to_history() -> None:
    """Step 5b: compute_speed_figure_for_history が history に speed_figure 列を付与し・
    build_rolling_features が rolling_speed_figure_* の6列を出力する（統合 GREEN）。"""
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_INT1")]
    )

    # Step 5b 相当: compute_speed_figure_for_history 呼出
    history_with_sf = compute_speed_figure_for_history(history, observations=obs)
    assert "speed_figure" in history_with_sf.columns, (
        "compute_speed_figure_for_history が history に speed_figure 列を追加していない"
    )

    # Step 5 rolling 相当: build_rolling_features が speed_figure 列を numeric 系統として集約
    result = build_rolling_features(obs, history_with_sf)

    # D-09 の6 feature が全て出力される（P02 拡張契約）
    expected_cols = [
        "rolling_speed_figure_last_1",
        "rolling_speed_figure_mean_3",
        "rolling_speed_figure_mean_5",
        "rolling_speed_figure_max_5",
        "rolling_speed_figure_sd_5",
        "rolling_speed_figure_count_5",
    ]
    for col in expected_cols:
        assert col in result.columns, (
            f"{col} が rolling 出力に含まれない（P02 _SPEED_FIGURE_AXES 拡張不備の可能性）"
        )

    # 対象 observation の rolling_speed_figure_count_5 は eligible 3行カウント=3
    # （5段階 adversarial は PIT で除外・eligible 3行のみ window に含まれる）
    row = result.iloc[0]
    # count_5 は実際 count（D-11）・adversarial 5行除外で eligible 3行
    assert int(row["rolling_speed_figure_count_5"]) == 3, (
        f"rolling_speed_figure_count_5 は eligible 3行で 3 の期待・実際: "
        f"{row['rolling_speed_figure_count_5']}（adversarial 5行が PIT 除外されていない可能性）"
    )


def test_builder_step5b_copy_not_rename() -> None:
    """Step 5b copy-not-rename（HIGH #5）: history の既存列（time/trackcd/jyocd/kyori/
    kakuteijyuni/harontimel3 等）が compute_speed_figure_for_history 呼出後も保持される。"""
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_COPY")]
    )

    # 既存列を記録
    original_cols = set(history.columns)
    history_with_sf = compute_speed_figure_for_history(history, observations=obs)

    # 既存列は全て保持される（破壊的 rename でない）
    missing = original_cols - set(history_with_sf.columns)
    assert missing == set(), (
        f"compute_speed_figure_for_history が既存列を破壊した（HIGH #5 copy-not-rename 違反）: "
        f"missing={missing}"
    )
    # speed_figure 列が追加されている
    assert "speed_figure" in history_with_sf.columns, "speed_figure 列が追加されていない"
    # time/trackcd/jyocd/kyori は speed_figure の素材として特に保持されるべき
    for required_source in ("time", "trackcd", "jyocd", "kyori"):
        assert required_source in history_with_sf.columns, (
            f"speed_figure 素材列 {required_source} が破壊された（copy-not-rename 違反・T-09-10）"
        )


def test_builder_step5b_pit_correct() -> None:
    """Step 5b PIT correct（SC#2 機能側）: 5段階 adversarial history で compute_speed_figure_for_history
    が eligible 3行のみで算出された値になる（guard 有効での検証・adversarial は test_speed_figure_pit.py）。

    adversarial 5行 (target/same_day_prior/same_day_later/previous_day/future) は PIT prefilter
    (strict < feature_cutoff_datetime) で除外される。結果フレームに含まれる eligible 行の par_sec は
    eligible 3行 (time=1100/1110/1120 deciseconds → 110.0/111.0/112.0 秒) の median = 111.0 になる。
    もし adversarial 行（time=9990 等で time_sec=999.0）が混入すると median が跳ね上がる。
    """
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS_PIT")]
    )

    result = compute_speed_figure_for_history(history, observations=obs)

    # 結果フレームは eligible 行のみ（adversarial 5行は PIT 除外）
    labels = set(result["row_label"].dropna().unique())
    assert labels == {"eligible"}, (
        f"結果は eligible 行のみ含むべき（adversarial 5行は PIT strict < で除外）・実際: {labels}"
    )

    # eligible 3行の par_sec は median(110.0, 111.0, 112.0) = 111.0
    # もし adversarial(time_sec=999.0 等)が混入すると median が 111.0 でなくなる
    par_vals = result["par_sec"].dropna().unique()
    assert len(par_vals) == 1, (
        f"eligible 3行の par_sec は同値(同一 observation)・実際: {par_vals}"
    )
    assert abs(float(par_vals[0]) - 111.0) < 1e-9, (
        f"par_sec は eligible 3行の median=111.0・実際: {par_vals[0]}・"
        f"adversarial time_sec(999.0 等) が混入した可能性（PIT 違反）"
    )

    # speed_figure が NaN でない（adversarial 混入で極端な値にならない）
    sf_values = result["speed_figure"].dropna()
    assert len(sf_values) > 0, "speed_figure に非 NaN 値が1つも無い（par/variant 算出不全）"
    # adversarial の time_sec=999.0 が混入すると speed_figure が極端に大きな負値になる
    # eligible の time_sec(110-112) に対する speed_figure は適度な範囲に収まるはず
    assert (sf_values.abs() < 1000.0).all(), (
        f"speed_figure に極端な値がある（adversarial 混入の可能性）: max={sf_values.abs().max()}"
    )
