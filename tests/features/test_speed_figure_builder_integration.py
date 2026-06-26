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

    # Phase 9.1 の17 feature が全て出力される（D-09 6 + Phase 9.1 11）
    expected_cols = [
        "rolling_speed_figure_last_1",
        "rolling_speed_figure_mean_3",
        "rolling_speed_figure_mean_5",
        "rolling_speed_figure_max_5",
        "rolling_speed_figure_sd_5",
        "rolling_speed_figure_count_5",
        # Phase 9.1 (D-09.1-01): 分布形状・趨勢
        "rolling_speed_figure_median_3",
        "rolling_speed_figure_median_5",
        "rolling_speed_figure_best2_mean_5",
        "rolling_speed_figure_trend_last_minus_mean5",
        "rolling_speed_figure_trend_mean3_minus_mean5",
        # Phase 9.1 (D-09.1-02): 条件適性
        "rolling_speed_figure_same_surface_mean_5",
        "rolling_speed_figure_same_surface_max_5",
        "rolling_speed_figure_same_surface_count_5",
        "rolling_speed_figure_same_distance_bucket_mean_5",
        "rolling_speed_figure_same_distance_bucket_max_5",
        "rolling_speed_figure_same_distance_bucket_count_5",
    ]
    for col in expected_cols:
        assert col in result.columns, (
            f"{col} が rolling 出力に含まれない（Phase 9.1 _SPEED_FIGURE_AXES 拡張不備の可能性）"
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


# ===========================================================================
# Phase 9.1 (D-09.1-01/02/03): speed profile 17 feature 拡張の単体テスト
# median/best2_mean/trend sentinel ルール + same_surface/same_distance_bucket
# 条件 match + PIT 保証（adversarial 行が conditional feature に混入しない）
# ===========================================================================
def test_phase91_speed_profile_sentinel_and_conditional() -> None:
    """Phase 9.1: speed profile 17 feature の sentinel/count ルール + same_surface/
    same_distance_bucket の条件 match + PIT 保護。

    eligible 3行（dirt/mile）で count=3:
      - median_3 / best2_mean_5 / same_surface_* / same_distance_bucket_* は算出
      - median_5 / trend_last_minus_mean5 / trend_mean3_minus_mean5 は count<5 で MISSING
      - same_surface_count_5 == 3（adversarial 行が PIT 混入すると >3 で検出）
    """
    M = "__MISSING__"
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS91",
                            trackcd="24", kyori=1600)  # target: dirt / mile
    ])
    history_sf = compute_speed_figure_for_history(history, observations=obs)
    result = build_rolling_features(obs, history_sf)
    row = result.iloc[0]

    # eligible 3行（adversarial 5行は PIT strict < で除外）
    assert int(row["rolling_speed_figure_count_5"]) == 3
    # median_3: count>=3 で算出
    assert row["rolling_speed_figure_median_3"] != M, "median_3 は count=3>=3 で算出されるべき"
    # median_5: count>=5 → count=3 なので MISSING（D-09.1-01 sentinel）
    assert row["rolling_speed_figure_median_5"] == M, "median_5 は count=3<5 で MISSING のべき"
    # best2_mean_5: count>=2 で算出（D-09.1-01）
    assert row["rolling_speed_figure_best2_mean_5"] != M, "best2_mean_5 は count=3>=2 で算出されるべき"
    # trend_*: count>=5 → MISSING（D-09.1-01・mean5 必要）
    assert row["rolling_speed_figure_trend_last_minus_mean5"] == M
    assert row["rolling_speed_figure_trend_mean3_minus_mean5"] == M
    # same_surface: target dirt・過去走も全行 dirt → eligible 3行 match
    # （adversarial 行も dirt だが PIT 除外・same_surface_count_5==3 で PIT 保証を機械検出）
    assert int(row["rolling_speed_figure_same_surface_count_5"]) == 3, (
        "same_surface_count_5 は eligible 3行（同 dirt）・adversarial が PIT 混入すると >3"
    )
    assert row["rolling_speed_figure_same_surface_mean_5"] != M
    assert row["rolling_speed_figure_same_surface_max_5"] != M
    # same_distance_bucket: target mile(1600)・過去走も全行 mile(1600) → 3行 match
    assert int(row["rolling_speed_figure_same_distance_bucket_count_5"]) == 3
    assert row["rolling_speed_figure_same_distance_bucket_mean_5"] != M
    assert row["rolling_speed_figure_same_distance_bucket_max_5"] != M


def test_phase91_best2_and_trend_with_5_eligible() -> None:
    """5行 eligible で median_5 / max_5 / mean_5 / best2_mean_5 / trend_* が算出される（count>=5）。

    値の正確性:
      - ``best2_mean_5`` は上位2件（速い=speed_figure 大）の平均 → ``mean_5 <= best2 <= max_5``
      - ``trend_last_minus_mean5`` == ``last_1 - mean_5``（直近1件 - 5走平均）
    """
    M = "__MISSING__"
    obs_rd = pd.to_datetime("2023-06-04")
    times = [1500, 1510, 1520, 1530, 1540]  # MMSS.t 110-114s（速い順に最新）
    rows = []
    for i, t in enumerate(times):
        as_of = obs_rd - pd.Timedelta(days=i + 2)  # -2,-3,-4,-5,-6 day
        rows.append(_build_se_history_row(
            kettonum=1001, race_date=as_of.strftime("%Y-%m-%d"),
            as_of_datetime=as_of, time=float(t), trackcd="24", kyori=1600,
        ))
    history = pd.DataFrame(rows)
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS91",
                            trackcd="24", kyori=1600)
    ])
    history_sf = compute_speed_figure_for_history(history, observations=obs)
    result = build_rolling_features(obs, history_sf)
    row = result.iloc[0]

    # count=5（5行 eligible・adversarial 無し）
    assert int(row["rolling_speed_figure_count_5"]) == 5
    # median_5/max_5/mean_5/best2/trend 全て count>=5 で算出
    for col in [
        "rolling_speed_figure_median_5", "rolling_speed_figure_max_5",
        "rolling_speed_figure_mean_5", "rolling_speed_figure_best2_mean_5",
        "rolling_speed_figure_trend_last_minus_mean5",
        "rolling_speed_figure_trend_mean3_minus_mean5",
    ]:
        assert row[col] != M, f"{col} は count=5 で算出されるべき"

    # best2_mean_5 は上位2件の平均 → mean_5 <= best2 <= max_5
    max5 = float(row["rolling_speed_figure_max_5"])
    mean5 = float(row["rolling_speed_figure_mean_5"])
    best2 = float(row["rolling_speed_figure_best2_mean_5"])
    assert mean5 - 1e-9 <= best2 <= max5 + 1e-9, (
        f"best2_mean_5({best2}) は mean_5({mean5}) と max_5({max5}) の間にあるべき"
    )
    # trend_last_minus_mean5 == last_1 - mean_5（D-09.1-01 定義の検証）
    last1 = float(row["rolling_speed_figure_last_1"])
    trend_last = float(row["rolling_speed_figure_trend_last_minus_mean5"])
    assert abs(trend_last - (last1 - mean5)) < 1e-6, (
        f"trend_last_minus_mean5({trend_last}) == last_1({last1}) - mean_5({mean5})={last1 - mean5}"
    )


def test_phase91_distance_bucket_conditional_filter() -> None:
    """same_distance_bucket は target と同 bucket の過去走のみ（D-09.1-02 条件 match）。
    target=mile(1600)・過去走 eligible 3行のうち1行を short(1200) に変更すると:
      - same_distance_bucket_count_5 == 2（mile の2行のみ・short 1行は mismatch）
      - same_surface_count_5 == 3（全行 dirt で変わらず・surface と bucket は独立 filter）
    これで conditional filter が bucket 別に正しく働くことを検証。
    """
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS91",
                            trackcd="24", kyori=1600)  # target: dirt / mile
    ])
    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    # eligible 最終行（time=1520=112.0s・1600m）を short(1200m) に変更・time も 1200m 範囲(65-95s)に
    history.loc[history.index[-1], "kyori"] = 1200   # short bucket
    history.loc[history.index[-1], "time"] = 720.0   # MMSS.t 72.0s（1200m 物理妥持範囲内）
    history_sf = compute_speed_figure_for_history(history, observations=obs)
    result = build_rolling_features(obs, history_sf)
    row = result.iloc[0]
    # eligible 3行（count=3）・うち mile 2行・short 1行
    assert int(row["rolling_speed_figure_count_5"]) == 3
    # same_distance_bucket: target mile → 2行のみ match（short 1行は mismatch）
    assert int(row["rolling_speed_figure_same_distance_bucket_count_5"]) == 2, (
        "same_distance_bucket は target(mile) と同 bucket の2行のみ・short 1行は mismatch のべき"
    )
    # same_surface: 全行 dirt（bucket 変更で surface は変わらない）→ 3行 match
    assert int(row["rolling_speed_figure_same_surface_count_5"]) == 3, (
        "same_surface は bucket と独立・全行 dirt で 3行 match のべき"
    )


def test_phase91_same_surface_pit_guard_dependency(monkeypatch) -> None:
    """same_surface / same_distance_bucket は PIT filter (strict ``<``) に依存する
    （adversarial・SAFE-01/PIT 聖域）。``compute_speed_figure_for_history`` が PIT filter
    済みの history_sf を返すため・same_surface の PIT 保証は speed_figure 側の
    ``_pit_cutoff_prefilter`` に一次依存する。guard を ``<=`` に monkeypatch して history_sf を
    再生成すると cutoff 同日行（previous_day）が混入し ``same_surface_count_5`` が増える。
    """
    import src.features.speed_figure as sf_mod

    history = _build_speed_figure_history_rows(obs_race_date="2023-06-04", kettonum=1001)
    obs = pd.DataFrame([
        _build_race_obs_row("2023A0610-R1", 1001, "2023-06-04", obs_id="OBS91",
                            trackcd="24", kyori=1600)
    ])

    # guard 有効: same_surface_count_5 == 3（adversarial 5行は PIT strict < で除外）
    history_sf_guarded = compute_speed_figure_for_history(history, observations=obs)
    result_guarded = build_rolling_features(obs, history_sf_guarded)
    assert int(result_guarded.iloc[0]["rolling_speed_figure_same_surface_count_5"]) == 3

    # guard 無効化: speed_figure と rolling の両方の _pit_cutoff_prefilter を <= に差し替え
    # （same_surface は二重 PIT filter に依存・両方無効化で cutoff 同日 previous_day が混入）
    def _leak_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        return expanded[expanded["as_of_datetime"] <= expanded["feature_cutoff_datetime"]].copy()

    monkeypatch.setattr(sf_mod, "_pit_cutoff_prefilter", _leak_prefilter)
    import src.features.rolling as rolling_mod
    monkeypatch.setattr(rolling_mod, "_pit_cutoff_prefilter", _leak_prefilter)
    history_sf_leaked = compute_speed_figure_for_history(history, observations=obs)
    result_leaked = build_rolling_features(obs, history_sf_leaked)
    n_leaked = int(result_leaked.iloc[0]["rolling_speed_figure_same_surface_count_5"])
    assert n_leaked > 3, (
        f"guard 無効化で cutoff 同日行が same_surface に混入し count>3 になるべき・実際: {n_leaked} "
        f"(same_surface が PIT filter に依存していることの証明・D-09.1-02)"
    )
