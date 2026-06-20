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
    - live DB cursor 引数を持たない (シグネチャ arity 0)
    - verify_snapshot_sha256 が完全 hash (64 hex) で PASS
    - byte_reproducible_scope が parquet_data_only_metadata_excluded (Phase 3 D-08)
    """
    # シグネチャ arity 0 検査 (live DB 引数を持たない・SC#1 聖域)
    sig = inspect.signature(load_feature_matrix)
    assert len(sig.parameters) == 0, (
        "load_feature_matrix は live DB 引数を持ってはならない (SC#1 聖域・T-04-06)"
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
