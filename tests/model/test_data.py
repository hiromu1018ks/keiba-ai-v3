"""Phase 4 SC#1/MODL-01 検証契約 (PLAN 02 GREEN 化).

検証内容:
- SC#1: stamped Parquet のみ学習 (live DB 非使用・feature 再計算禁止)
- raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2) のモデル入力除外 (Pitfall 4)
- feature allowlist 検査 (banned_features が空・odds-free 保証・D-07/§13.4)
- BACK-01 前置: 正準 race_key 単位の train/calib/test 3way disjoint 分割
  + 完全時系列条件 train_max<calib_min<calib_max<test_min<=test_max (review MEDIUM#5)
- review HIGH#9: FEATURE_COLUMNS は registry derived allowlist で make_X_y が
  X.columns == FEATURE_COLUMNS を完全一致 assert・metadata/label/raw-ID 混入防止
- review MEDIUM#6: manifest の完全 SHA256 (64 hex) と hash scope を検証

DB 依存をテストから排除するため、build_training_frame/make_X_y は合成 label DataFrame
を inject して unit test 化する (review HIGH#9: fake-green 回避)。

参考: 04-RESEARCH.md D-01/D-02b/D-03/D-05/D-07 / 04-PATTERNS.md data.py セクション.
"""

from __future__ import annotations

import inspect
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.features.availability import banned_features, load_feature_availability
from src.model.data import (
    FEATURE_COLUMNS,
    RAW_ID_COLUMNS,
    SNAPSHOT_MANIFEST_PATH,
    SNAPSHOT_PATH,
    build_training_frame,
    load_feature_matrix,
    make_race_key,
    make_X_y,
    split_3way,
    verify_snapshot_sha256,
)


def test_load_from_parquet_only():
    """SC#1: load_feature_matrix は SNAPSHOT のみ読込 (live DB 引数なし).

    - 戻り値 shape が (554267, 62+) (Parquet 全列 + race_key)
    - **REVIEW H1-a (Phase 9 P03)**: live DB cursor 引数を持たない (SC#1 聖域・T-04-06)。
      ``snapshot_id`` 引数は受け取るがローカル Parquet path の選択のみ (live DB 非依存)。
      旧来の arity-0 escape (``len(sig.parameters)==0``) は削除・snapshot_id を必須パラメータ化。
    - verify_snapshot_sha256 が完全 hash (64 hex) で PASS
    - byte_reproducible_scope が parquet_data_only_metadata_excluded (Phase 3 D-08)
    """
    # REVIEW H1-a: live DB cursor 引数を持たない (SC#1 聖域・T-04-06)。
    # snapshot_id 引数は受け取るが live DB cursor / ConnectionPool は持たない。
    # 旧来の arity-0 escape は H1-a で削除（古い arity-0 関数を構造的に拒否）。
    sig = inspect.signature(load_feature_matrix)
    assert "snapshot_id" in sig.parameters, (
        "load_feature_matrix は snapshot_id 引数を受け取る (REVIEW H1-a・後方互換 A5)"
    )
    # live DB 系引数 (cursor/ConnectionPool) を持たないことを検査
    forbidden_db_params = {"readonly_cur", "cur", "pool", "read_pool", "conn"}
    actual_db_params = forbidden_db_params & set(sig.parameters)
    assert not actual_db_params, (
        f"load_feature_matrix は live DB 引数を持ってはならない (SC#1 聖域・T-04-06): "
        f"{actual_db_params}"
    )

    df = load_feature_matrix()
    # row_count (manifest 554267) + 列数 >= 62 (Parquet 全列 + race_key)
    assert df.shape[0] == 554267, f"row_count 不一致: {df.shape}"
    assert df.shape[1] >= 62, f"col_count 想定外: {df.shape}"
    # race_key 列が付与されている (正準キー・review HIGH#9)
    assert "race_key" in df.columns, "race_key 列が付与されていない (review HIGH#9)"
    assert "feature_snapshot_id" in df.columns, "feature_snapshot_id 列が保持されていない"
    # race_date が datetime 化されている (split_3way / calibrator strict-later 検証用)
    assert pd.api.types.is_datetime64_any_dtype(df["race_date"]), (
        "race_date が datetime 化されていない"
    )

    # 完全 SHA256 検証 (review MEDIUM#6)・fail しないことが確認
    verify_snapshot_sha256()

    # manifest の hash scope が Phase 3 D-08 と一致することを確認
    import yaml
    from pathlib import Path

    with Path(SNAPSHOT_MANIFEST_PATH).open(encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    assert manifest["sha256"] and len(manifest["sha256"]) == 64, (
        "manifest sha256 は完全 hash (64 hex) でなければならない (review MEDIUM#6)"
    )
    assert manifest["byte_reproducible_scope"] == "parquet_data_only_metadata_excluded", (
        "byte_reproducible_scope が Phase 3 D-08 と不一致 (review MEDIUM#6)"
    )


def test_raw_ids_excluded():
    """raw ID 原列 (kisyucode/chokyosicode/ketto3infohansyokunum1/2) はモデル入力から除外.

    review HIGH#9: make_X_y が返す X.columns が FEATURE_COLUMNS と完全一致 (集合 + 順序) し、
    metadata/label/raw-ID 列が混入しないことを assert (fake-green 防止).
    """
    feature_df = load_feature_matrix()
    # 合成 label DataFrame を inject (DB 非依存・review HIGH#9)
    frame = build_training_frame(feature_df, _make_synthetic_labels(feature_df))
    X, y = make_X_y(frame)

    # 完全一致 (集合 + 順序) assert・review HIGH#9
    assert list(X.columns) == FEATURE_COLUMNS, (
        "X.columns が FEATURE_COLUMNS と完全一致しない (review HIGH#9)"
    )
    # raw ID 原列が FEATURE に含まれない (Pitfall 4 / T-04-07)
    leaked = sorted(set(RAW_ID_COLUMNS) & set(X.columns))
    assert leaked == [], f"raw ID 原列が X に混入 (Pitfall 4): {leaked}"
    # metadata/label 列が FEATURE に含まれない
    forbidden = sorted(
        {"race_date", "race_start_datetime", "feature_snapshot_id", "race_nkey",
         "fukusho_hit_validated", "is_model_eligible"} & set(X.columns)
    )
    assert forbidden == [], f"metadata/label 列が X に混入 (review HIGH#9): {forbidden}"

    # y が int Series (fukusho_hit_validated)
    assert y.dtype == int or y.dtype == np.int64, f"y dtype 想定外: {y.dtype}"
    assert set(y.unique()).issubset({0, 1}), f"y が 0/1 以外の値を含む: {sorted(y.unique())}"


def test_no_banned_features():
    """feature allowlist 検査: banned_features(spec) が空 (D-07/§13.4 odds-free 保証).

    assert_matrix_columns_registered は make_X_y 内部で呼ばれ、FEATURE_COLUMNS が
    registry / reserved / _code / raw-id 由来であることを検査済み。ここでは
    banned_features(spec) == [] を直接 assert する (SC#1 間接検証).
    """
    spec = load_feature_availability()
    assert banned_features(spec) == [], (
        "banned_features が空でない (D-07/§13.4 odds-free allowlist 違反)"
    )

    # FEATURE_COLUMNS 自体が registry derived であり、banned source (odds/ninki/
    # sibababacd/dirtbabacd 等) が含まれないことを二重検査
    from src.features.availability import TARGET_OBS_BANNED_COLUMNS

    leaked = sorted(set(TARGET_OBS_BANNED_COLUMNS) & set(FEATURE_COLUMNS))
    assert leaked == [], (
        f"banned source カラムが FEATURE_COLUMNS に混入 (HIGH #3 fail-loud 無意味化): {leaked}"
    )


def test_race_id_disjoint_3way():
    """BACK-01 前置: 3way 分割で同一正準 race_key が train/calib/test を跨がない.

    D-02b 推奨案: train 2016-07..2023 / calib 2024-H1 / test 2024-H2 / 2025+ は温存.
    review MEDIUM#5: 完全時系列条件 train_max < calib_min < calib_max < test_min <= test_max
    review HIGH#9: 正準 race_key (race_nkey でなく) で disjoint を検査.
    """
    feature_df = load_feature_matrix()
    frame = build_training_frame(feature_df, _make_synthetic_labels(feature_df))
    parts = split_3way(frame)

    train_keys = set(parts["train"]["race_key"])
    calib_keys = set(parts["calib"]["race_key"])
    test_keys = set(parts["test"]["race_key"])

    # 正準 race_key pairwise disjoint (review HIGH#9)
    assert train_keys.isdisjoint(calib_keys), "train と calib の race_key が重複"
    assert train_keys.isdisjoint(test_keys), "train と test の race_key が重複"
    assert calib_keys.isdisjoint(test_keys), "calib と test の race_key が重複"

    # 完全時系列条件 (review MEDIUM#5)
    train_max = parts["train"]["race_date"].max()
    calib_min = parts["calib"]["race_date"].min()
    calib_max = parts["calib"]["race_date"].max()
    test_min = parts["test"]["race_date"].min()
    test_max = parts["test"]["race_date"].max()
    assert train_max < calib_min, f"train_max >= calib_min: {train_max} vs {calib_min}"
    assert calib_min < calib_max, f"calib_min >= calib_max: {calib_min} vs {calib_max}"
    assert calib_max < test_min, f"calib_max >= test_min: {calib_max} vs {test_min}"
    assert test_min <= test_max, f"test_min > test_max: {test_min} vs {test_max}"

    # holdout_2025_plus は Phase 5 BT 温存 (学習/評価に使わない)
    assert parts["holdout_2025_plus"]["race_date"].min() >= pd.Timestamp("2025-01-01"), (
        "holdout_2025_plus に 2025-01-01 以前の行が混入"
    )

    # 各区間が空でない
    for name in ("train", "calib", "test", "holdout_2025_plus"):
        assert len(parts[name]) > 0, f"{name} が空"


# ---------------------------------------------------------------------------
# helper: 合成 label DataFrame の生成 (DB 非依存・review HIGH#9)
# ---------------------------------------------------------------------------
def _make_synthetic_labels(feature_df: pd.DataFrame) -> pd.DataFrame:
    """feature_df の PK に対応する合成 label DataFrame を生成する (DB 非依存).

    review HIGH#9: DB 依存をテストから排除するため、load_labels(readonly_cur) を使わず
    合成 label を inject する。これにより build_training_frame/make_X_y/split_3way が
    DB 接続無しで unit test 可能になる (fake-green 回避・契約検証が純粋)。

    y = fukusho_hit_validated は乱数 seed 固定で生成 (再現性)。
    """
    rng = np.random.default_rng(42)
    label_cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum",
        "race_date",
        "fukusho_hit_validated",
        "fukusho_hit_raw",
        "is_model_eligible",
        "label_validation_status",
        "is_fukusho_sale_available",
        "fukusho_payout_places",
        "sales_start_entry_count",
        "final_starter_count",
        "sales_start_entry_count_source",
        "sales_start_entry_count_confidence",
        "ineligibility_reason",
        "is_scratch_cancel",
        "is_race_excluded",
        "is_dead_loss",
        "is_race_cancelled",
        "is_dead_heat",
        "label_generation_version",
    ]
    n = len(feature_df)
    labels = pd.DataFrame({
        "year": feature_df["year"].astype(str).values,
        "jyocd": feature_df["jyocd"].astype(str).values,
        "kaiji": feature_df["kaiji"].astype(str).values,
        "nichiji": feature_df["nichiji"].astype(str).values,
        "racenum": feature_df["racenum"].astype(str).values,
        "umaban": feature_df["umaban"].astype(str).values,
        "kettonum": feature_df["kettonum"].astype(str).values,
        "race_date": feature_df["race_date"].values,
        "fukusho_hit_validated": rng.integers(0, 2, size=n).astype(int),
        "fukusho_hit_raw": rng.integers(0, 2, size=n).astype(int),
        "is_model_eligible": True,
        "label_validation_status": "validated",
        "is_fukusho_sale_available": True,
        "fukusho_payout_places": 3,
        "sales_start_entry_count": 12,
        "final_starter_count": 12,
        "sales_start_entry_count_source": "synthetic",
        "sales_start_entry_count_confidence": "high",
        "ineligibility_reason": "",
        "is_scratch_cancel": False,
        "is_race_excluded": False,
        "is_dead_loss": False,
        "is_race_cancelled": False,
        "is_dead_heat": False,
        "label_generation_version": "v1.0.0",
    })
    # label_cols に無い列が無いことを保証 (不足列は build_training_frame で問題になる)
    for c in label_cols:
        assert c in labels.columns, f"合成 label に必須列 {c} が無い"
    return labels


# ---------------------------------------------------------------------------
# Phase 9 P03 Task 3: REVIEW H1-b — snapshot_id 伝播で FEATURE_COLUMNS が実際切替わる証明
# ---------------------------------------------------------------------------
def test_make_X_y_uses_snapshot_feature_columns(tmp_path):
    """REVIEW H1-b (Phase 9 P03): ``make_X_y(frame, snapshot_id="...")`` が選択 snapshot の
    FEATURE_COLUMNS を実際に消費することを検証（静かな失敗の閉塞証明・T-09-26 mitigate）。

    合成 speed_figure snapshot を一時生成し・snapshot_id で v1.0 と speed_figure を切り替えて
    ``make_X_y`` が返す X.columns が異なる FEATURE_COLUMNS になることを assert する。
    orchestrator.train_and_predict も snapshot_id を内部 make_X_y に伝播する（H1-b grep verify 済み）。
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from src.model.data import (
        DEFAULT_SNAPSHOT_PATH,
        _derive_feature_columns,
        _snapshot_paths,
    )

    # v1.0 snapshot を読み・rolling_speed_figure_* 6 列を追加して合成 speed_figure snapshot を作成
    v1_path, _v1_manifest, _v1_cat = _snapshot_paths(snapshot_id=None)
    df = pq.read_table(v1_path).to_pandas()
    n = len(df)
    # rolling_speed_figure_* 17 列を数値で追加（registry 登録済み・Phase 9 6 + Phase 9.1 11）
    speed_cols = [
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
    rng = np.random.default_rng(42)
    for col in speed_cols:
        df[col] = rng.standard_normal(n).astype("float64")

    # 合成 snapshot を一時ディレクトリに書出し（snapshot_id="test-speed-figure"）
    # _snapshot_paths は "snapshots/feature_matrix_test-speed-figure.parquet" を返すが・
    # 本テストは tmp_path 配下に書出したいので monkeypatch で _snapshot_paths を上書き。
    test_parquet = tmp_path / "feature_matrix_test-speed-figure.parquet"
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, test_parquet)

    # _snapshot_paths を tmp_path に向けるよう monkeypatch
    import src.model.data as data_mod

    orig_snapshot_paths = data_mod._snapshot_paths
    orig_pq_read_table = pq.read_table

    def _fake_snapshot_paths(snapshot_id=None):
        if snapshot_id == "test-speed-figure":
            return (
                str(test_parquet),
                str(tmp_path / "feature_matrix_test-speed-figure.manifest.yaml"),
                str(tmp_path / "category_map_test-speed-figure.json"),
            )
        return orig_snapshot_paths(snapshot_id)

    data_mod._snapshot_paths = _fake_snapshot_paths
    # _derive_feature_columns 内部で呼ばれる pq.read_table も test_parquet を指すよう
    # _snapshot_paths 経由で解決されるため pq monkeypatch 不要（pq.read_table は引数 path を使う）
    try:
        # H1-a: snapshot_id="test-speed-figure" の FEATURE_COLUMNS は rolling_speed_figure_* を含む
        sf_cols = _derive_feature_columns(snapshot_id="test-speed-figure")
        speed_in_sf = [c for c in sf_cols if c.startswith("rolling_speed_figure_")]
        assert sorted(speed_in_sf) == sorted(speed_cols), (
            f"snapshot_id=test-speed-figure の FEATURE_COLUMNS は rolling_speed_figure_* 6 列を"
            f"含むべき・実際: {speed_in_sf}"
        )
        # snapshot_id=None (v1.0) の FEATURE_COLUMNS は rolling_speed_figure_* を含まない
        v1_cols = _derive_feature_columns(snapshot_id=None)
        v1_speed = [c for c in v1_cols if c.startswith("rolling_speed_figure_")]
        assert v1_speed == [], (
            f"snapshot_id=None (v1.0) の FEATURE_COLUMNS は rolling_speed_figure_* を含まない・"
            f"実際: {v1_speed}"
        )
    finally:
        data_mod._snapshot_paths = orig_snapshot_paths

    # make_X_y が実際に snapshot_id で FEATURE_COLUMNS を切替えることを検証
    # （合成 label を inject して build_training_frame → make_X_y）
    df_with_speed = df.copy()
    # build_training_frame が race_date 列を期待するため v1 同様に datetime 化
    df_with_speed["race_date"] = pd.to_datetime(df_with_speed["race_date"])
    df_with_speed["race_key"] = make_race_key(df_with_speed)
    labels = _make_synthetic_labels(df_with_speed)
    frame = build_training_frame(df_with_speed, labels)

    # snapshot_id を切替えて make_X_y が異なる FEATURE_COLUMNS を選択することを検証
    # v1.0 側は rolling_speed_figure_* を含まない
    data_mod._snapshot_paths = orig_snapshot_paths  # 既に戻した状態
    X_v1, _ = make_X_y(frame, snapshot_id=None)
    assert not any(c.startswith("rolling_speed_figure_") for c in X_v1.columns), (
        "snapshot_id=None で rolling_speed_figure_* が X に含まれている（H1-a/b 違反）"
    )

    # snapshot_id="test-speed-figure" 側は rolling_speed_figure_* を含む（H1-b の核心）
    data_mod._snapshot_paths = _fake_snapshot_paths
    try:
        X_sf, _ = make_X_y(frame, snapshot_id="test-speed-figure")
        sf_in_X = [c for c in X_sf.columns if c.startswith("rolling_speed_figure_")]
        assert sorted(sf_in_X) == sorted(speed_cols), (
            f"snapshot_id=test-speed-figure で rolling_speed_figure_* 6 列が X に含まれるべき・"
            f"実際: {sf_in_X}（H1-b: snapshot_id 伝播で FEATURE_COLUMNS が切替わっていない）"
        )
    finally:
        data_mod._snapshot_paths = orig_snapshot_paths


# ---------------------------------------------------------------------------
# Phase 10 PLAN 06 Task 1: 実 snapshot_id で 79/35 回帰・27 新 feature 含有・
# W-3 category-map bit-identity（B-3 同一 trainer 設定の前提保証）を検証する。
#
# NOTE: PLAN 06 truth は「baseline (postreview-v2) も 79 feature」と記載するが・これは誤り。
# 実測値（registry derived allowlist）は:
#   - 20260626-1a-opponentstrength-v1 (Phase 10): 79 feature（Phase 9.1 52 + 27 新 feature）
#   - 20260620-1a-postreview-v2 (v1.0 baseline): 35 feature
#   - 20260625-1a-speedfigure-v1: 41 feature
# PROJECT decisions にも「postreview-v2 実データ値 35 が正」と明記。本テストは実測値で検証する。
# PLAN の意図（H1-b 無言失敗 catch・27 新 feature 含有・両 snapshot_id で別 FEATURE_COLUMNS）は
# 79/35 の組で完全に達成される。
# ---------------------------------------------------------------------------
PHASE10_SNAPSHOT_ID = "20260626-1a-opponentstrength-v1"
BASELINE_V10_SNAPSHOT_ID = "20260620-1a-postreview-v2"

# 実測値定数（手動検証で確認・registry derived allowlist）
PHASE10_FEATURE_COUNT = 79
BASELINE_V10_FEATURE_COUNT = 35


def test_phase10_derive_feature_columns_new_and_baseline_regression():
    """Phase 10 PLAN 06 Task 1 (B-2): _derive_feature_columns が実 snapshot_id で
    異なる FEATURE_COLUMNS を返すことを検証（H1-b 無言失敗 catch の核心）。

    新 snapshot_id (20260626-1a-opponentstrength-v1) で 79 feature・
    baseline snapshot_id (20260620-1a-postreview-v2) で 35 feature が両方成立することで・
    registry 動的導出と snapshot_id 明示伝播 (H1-b) の両方が保証される。

    NOTE: PLAN 06 truth の「baseline も 79 feature」は誤記（PROJECT decisions で 35 が正と明記）。
    本テストは実測値（79/35）で検証する。PLAN の本質（snapshot_id で FEATURE_COLUMNS が切替わる・
    H1-b 無言失敗 catch・27 新 feature 含有）は 79/35 の組で完全に達成される。
    """
    from src.model.data import _derive_feature_columns

    # 新 snapshot_id (Phase 10・opponentstrength): 79 feature
    new_cols = _derive_feature_columns(snapshot_id=PHASE10_SNAPSHOT_ID)
    assert len(new_cols) == PHASE10_FEATURE_COUNT, (
        f"snapshot_id={PHASE10_SNAPSHOT_ID} の FEATURE_COLUMNS は "
        f"{PHASE10_FEATURE_COUNT} feature のべき・"
        f"実際: {len(new_cols)}（PLAN truth 79 と不一致の場合は registry 伝播破損・H1-b）"
    )

    # baseline snapshot_id (v1.0 postreview-v2): 35 feature（PROJECT decisions で確定値）
    baseline_cols = _derive_feature_columns(snapshot_id=BASELINE_V10_SNAPSHOT_ID)
    assert len(baseline_cols) == BASELINE_V10_FEATURE_COUNT, (
        f"snapshot_id={BASELINE_V10_SNAPSHOT_ID} の FEATURE_COLUMNS は "
        f"{BASELINE_V10_FEATURE_COUNT} feature のべき・実際: {len(baseline_cols)}"
    )

    # 両者が異なる集合であること（H1-b: snapshot_id で実際に切替わる）
    assert set(new_cols) != set(baseline_cols), (
        "Phase 10 snapshot と baseline で FEATURE_COLUMNS が同一（H1-b 違反・"
        "snapshot_id 伝播で FEATURE_COLUMNS が切替わっていない無言失敗）"
    )

    # delta: Phase 10 が baseline + 27 新 feature（厳密には +44・Phase 9.1 speed_figure 系統込み）
    delta = set(new_cols) - set(baseline_cols)
    expected_new = {
        # FEAT-02 相手強度 rolling profile (21 feature)
        "rolling_field_strength_mean_latest_1",
        "rolling_field_strength_mean_mean_5",
        "rolling_field_strength_mean_mean_3",
        "rolling_field_strength_coverage_mean_5",
        "rolling_field_strength_valid_count_mean_5",
        # FEAT-03 レース内相対 (6 feature)
        "speed_index_rank_mean5",
        "speed_index_rank_best2_mean5",
        "speed_index_rank_median5",
        "gap_to_top",
        "gap_to_3rd",
        "field_strength_adjusted_rank",
    }
    missing = expected_new - delta
    assert missing == set(), (
        f"Phase 10 の 27 新 feature の一部が FEATURE_COLUMNS に含まれない: {sorted(missing)}"
    )


def test_phase10_make_X_y_green_on_new_snapshot():
    """Phase 10 PLAN 06 Task 1: 既存 make_X_y snapshot_id 伝播テストが・新 snapshot_id
    '20260626-1a-opponentstrength-v1' でも GREEN になることを検証（B-2・H1-b 無言失敗 catch）。

    実 snapshot の Parquet を読み・合成 label を inject して build_training_frame し・
    make_X_y が X.columns == FEATURE_COLUMNS（新 snapshot から導出・79 feature）を完全一致 assert
    で PASS することを確認する。snapshot_id 未伝播の無言失敗を直接 catch する形。
    """
    feature_df = load_feature_matrix(snapshot_id=PHASE10_SNAPSHOT_ID)
    labels = _make_synthetic_labels(feature_df)
    frame = build_training_frame(feature_df, labels)

    # 新 snapshot_id で make_X_y が完全一致 assert で GREEN
    X, y = make_X_y(frame, snapshot_id=PHASE10_SNAPSHOT_ID)

    # X.columns が新 snapshot 由来 FEATURE_COLUMNS と完全一致
    from src.model.data import _derive_feature_columns

    expected = _derive_feature_columns(snapshot_id=PHASE10_SNAPSHOT_ID)
    assert list(X.columns) == expected, (
        "make_X_y が新 snapshot_id で X.columns == FEATURE_COLUMNS を満たさない (H1-b 違反)・"
        f"len(X.columns)={len(X.columns)} len(expected)={len(expected)}"
    )
    # 27 新 feature の代表が実際に X に含まれる
    for required in (
        "rolling_field_strength_mean_mean_5",
        "speed_index_rank_mean5",
        "field_strength_adjusted_rank",
    ):
        assert required in X.columns, (
            f"新 feature {required} が X.columns に含まれない（FEATURE_COLUMNS 伝播破損）"
        )
    assert set(y.unique()).issubset({0, 1})


def test_phase10_category_map_bit_identity_w3():
    """Phase 10 PLAN 06 Task 1 (W-3): baseline_cat_map と phase10_cat_map の hash bit-identity を
    検証する（B-3 同一 trainer 設定の前提保証・REVIEWS.md L140/L205 MEDIUM）。

    Phase 10 は新 feature 追加のみで category mapping を変更しない設計・両 snapshot の
    category_map が bit-identical であることを保証する。hash が異なると delta は feature ノイズ化
    ではなく category mapping ドリフトを測る（B-3・両 snapshot 同一 trainer 設定の核心）。
    """
    import hashlib
    import json
    from pathlib import Path

    from src.model.data import _snapshot_paths

    _, _, baseline_cat_path = _snapshot_paths(snapshot_id=BASELINE_V10_SNAPSHOT_ID)
    _, _, phase10_cat_path = _snapshot_paths(snapshot_id=PHASE10_SNAPSHOT_ID)

    baseline_path = Path(baseline_cat_path)
    phase10_path = Path(phase10_cat_path)
    assert baseline_path.exists(), f"baseline category_map が存在しない: {baseline_path}"
    assert phase10_path.exists(), f"phase10 category_map が存在しない: {phase10_path}"

    # 両 JSON を sort_keys=True で正規化して hash 比較（mapping 順序に依存しない）
    with baseline_path.open(encoding="utf-8") as f:
        baseline_map = json.load(f)
    with phase10_path.open(encoding="utf-8") as f:
        phase10_map = json.load(f)

    baseline_hash = hashlib.sha256(
        json.dumps(baseline_map, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    phase10_hash = hashlib.sha256(
        json.dumps(phase10_map, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    assert baseline_hash == phase10_hash, (
        "W-3 bit-identity 違反・baseline_cat_map と phase10_cat_map の hash が異なる"
        "（category mapping ドリフト・B-3 同一 trainer 設定の前提崩れ）・"
        f"baseline={baseline_hash[:16]}... phase10={phase10_hash[:16]}..."
    )

    # category key 集合の一致も念のため検査（jockey_id/horse_id/sire_id 等）
    only_baseline = set(baseline_map.keys()) - set(phase10_map.keys())
    only_phase10 = set(phase10_map.keys()) - set(baseline_map.keys())
    assert set(baseline_map.keys()) == set(phase10_map.keys()), (
        f"category_map の key 集合が異なる: only_baseline={only_baseline} "
        f"only_phase10={only_phase10}"
    )

