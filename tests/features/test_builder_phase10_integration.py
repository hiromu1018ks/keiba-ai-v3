# ruff: noqa: E501
"""Phase 10 Plan 04: builder.py パイプライン統合（FEAT-02 21 + FEAT-03 6 = 27 feature）テスト.

本ファイルは PLAN 01/02/03 の 3 モジュール（field_strength.py / rolling.py 拡張 / race_relative.py）が
builder.py に正しく統合されていること・feature_availability.yaml registry に 27 新 feature が登録され
schema_version 0.6.0 に bump されていることを検証する機能テスト。

cover:
  - Test 1: registry 27 新 feature + schema_version 0.6.0 (SC#3 registry↔Parquet parity)
  - Test 2: availability._ROLLING_SYSTEMS_FOR_RESERVED に "field_strength" 追加
  - Test 3: builder.py に Step 5c/5d/7/7b が挿入されていること（ソース grep）
  - Test 4: CYCLE-2 HIGH-C2-3 – Step 5c が history でなく raw_history を第1引数に受けること
  - Test 5: assert_matrix_columns_registered が 27 新 feature で GREEN（registry parity）
  - Test 6: FEATURE_COLUMNS allowlist (model/data.py) が registry derived で新 feature を自動追従

SAFE-01 / core value: 本テストは builder と registry の契約を検証し・市場情報 proxy 不使用。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.features.availability import (
    _ROLLING_SYSTEMS_FOR_RESERVED,
    assert_matrix_columns_registered,
    load_feature_availability,
    registered_feature_columns,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILDER_PATH = _REPO_ROOT / "src" / "features" / "builder.py"


def _spec() -> dict:
    return load_feature_availability()


# 27 新 feature の代表点（必須エントリ）
_FEAT02_REPRESENTATIVE = [
    "rolling_field_strength_mean_latest_1",
    "rolling_field_strength_mean_mean_5",
    "rolling_field_strength_valid_count_mean_5",
    "rolling_field_strength_coverage_mean_5",
]
_FEAT03_REPRESENTATIVE = [
    "speed_index_rank_mean5",
    "speed_index_rank_best2_mean5",
    "speed_index_rank_median5",
    "gap_to_top",
    "gap_to_3rd",
    "field_strength_adjusted_rank",
]


# ===========================================================================
# Test 1: registry 27 新 feature + schema_version 0.6.0 (SC#3)
# ===========================================================================
def test_registry_has_27_new_features_and_schema_060():
    """feature_availability.yaml に rolling_field_strength 21 + FEAT-03 6 = 27 新 feature が
    登録され・schema_version が 0.6.0 に bumpされていること（SC#3 registry parity）。"""
    spec = _spec()
    assert spec["schema_version"] == "0.6.0", (
        f"schema_version は 0.6.0 のべき・実際: {spec['schema_version']} (PLAN 04 schema bump)"
    )
    names = registered_feature_columns(spec)
    # FEAT-02 代表4列（21 feature の代表点）
    for col in _FEAT02_REPRESENTATIVE:
        assert col in names, (
            f"{col} が registry に存在しない（FEAT-02 rolling_field_strength 21 feature 未登録・SC#3）"
        )
    # FEAT-03 全6列
    for col in _FEAT03_REPRESENTATIVE:
        assert col in names, (
            f"{col} が registry に存在しない（FEAT-03 6 feature 未登録・SC#3）"
        )


def test_registry_rolling_field_strength_has_21_entries():
    """registry の rolling_field_strength_* エントリが正確に 21 個であること（D-13 完全性）。"""
    spec = _spec()
    fs_entries = [
        e for e in spec["features"]
        if e["feature_name"].startswith("rolling_field_strength_")
    ]
    assert len(fs_entries) == 21, (
        f"rolling_field_strength_* エントリは21個のべき・実際: {len(fs_entries)} (D-13 21 feature)"
    )


# ===========================================================================
# Test 2: availability._ROLLING_SYSTEMS_FOR_RESERVED に field_strength 追加
# ===========================================================================
def test_availability_reserved_includes_field_strength():
    """availability._ROLLING_SYSTEMS_FOR_RESERVED に "field_strength" が含まれること
    （registry parity 前提・rolling_field_strength_valid_count_mean_5/coverage_mean_5 は
    feature 扱いで reserved 自動展開から除外されるが・系統自体は reserved に登録）。"""
    assert "field_strength" in _ROLLING_SYSTEMS_FOR_RESERVED, (
        "_ROLLING_SYSTEMS_FOR_RESERVED に field_strength が無い（PLAN 04 action 2・registry parity）"
    )
    # speed_figure も維持（回帰）
    assert "speed_figure" in _ROLLING_SYSTEMS_FOR_RESERVED


def test_reserved_excludes_field_strength_count_from_auto_expansion():
    """reserved 自動展開の rolling_{sys}_count_5 に field_strength が含まれないこと
    （rolling_field_strength_valid_count_mean_5 / coverage_mean_5 は feature 扱い・
    D-11 信頼度軸・speed_figure count_5 と同様 idiom）。"""
    from src.features.availability import _RESERVED_NON_FEATURE_COLUMNS

    # field_strength の count_5 は reserved 自動展開に含まれない（feature 扱い）
    assert "rolling_field_strength_count_5" not in _RESERVED_NON_FEATURE_COLUMNS, (
        "rolling_field_strength_count_5 は feature 扱い・reserved 自動展開から除外されるべき"
    )
    # speed_figure count_5 も除外維持（回帰）
    assert "rolling_speed_figure_count_5" not in _RESERVED_NON_FEATURE_COLUMNS


# ===========================================================================
# Test 3 & 4: builder.py の Step 5c/5d/7/7b 挿入（ソース検査）
# ===========================================================================
def _read_builder_source() -> str:
    return _BUILDER_PATH.read_text(encoding="utf-8")


def test_builder_has_step5c_field_strength_profile_call():
    """builder.py に compute_field_strength_profile の import と呼出が存在すること（Step 5c）。"""
    src = _read_builder_source()
    assert "from src.features.field_strength import compute_field_strength_profile" in src, (
        "Step 5c: compute_field_strength_profile の import が builder.py に無い"
    )
    assert "compute_field_strength_profile(" in src, (
        "Step 5c: compute_field_strength_profile 呼出が builder.py に無い"
    )


def test_builder_has_step7_race_relative_call():
    """builder.py に compute_race_relative_features の import と呼出が存在すること（Step 7）。"""
    src = _read_builder_source()
    assert "from src.features.race_relative import compute_race_relative_features" in src, (
        "Step 7: compute_race_relative_features の import が builder.py に無い"
    )
    assert "compute_race_relative_features(feature_matrix)" in src, (
        "Step 7: compute_race_relative_features(feature_matrix) 呼出が builder.py に無い"
    )


def test_builder_step5c_passes_raw_history_not_history():
    """**CYCLE-2 HIGH-C2-3 (10-REVIEWS.md L108-114, L219-226, L297)**:
    builder.py の Step 5c compute_field_strength_profile が第1引数に history でなく
    raw_history を受け取ること。これにより PLAN 01 の C2-1 full-pipeline source-as-of
    再計算が統合時にも適用される（obs_id 展開済み target-cutoff-contaminated history でなく
    Step 5b 前に保存した raw_history を渡す）。
    """
    import re

    src = _read_builder_source()
    # raw_history 保存（Step 5b 前）
    assert "raw_history = history.copy()" in src, (
        "CYCLE-2 HIGH-C2-3: Step 5b 前の raw_history = history.copy() が builder.py に無い"
    )
    # Step 5c は raw_history を第1引数に取る（実装は改行を挟み得るため正規表現で許容）
    pattern = re.compile(
        r"compute_field_strength_profile\(\s*raw_history\b"
    )
    assert pattern.search(src), (
        "CYCLE-2 HIGH-C2-3: compute_field_strength_profile が raw_history でなく history を"
        "第1引数に取っている可能性・PLAN 01 C2-1 fix が統合時に迂回される (10-REVIEWS.md L297)"
    )


def test_builder_step7b_drops_intermediate_field_strength_columns():
    """builder.py の Step 7b で field_strength_* prefix（rolling_field_strength_* 無し）の中間列が
    feature_matrix から drop されること（registry parity 違反回避・T-10-16 mitigate）。"""
    src = _read_builder_source()
    # field_strength_ prefix かつ rolling_field_strength_ prefix 無しを drop する処理
    assert 'c.startswith("field_strength_")' in src, (
        "Step 7b: field_strength_ prefix 中間列 drop 処理が builder.py に無い (T-10-16)"
    )
    assert 'c.startswith("rolling_field_strength_")' in src, (
        "Step 7b: rolling_field_strength_ prefix 除外条件が builder.py に無い (T-10-16)"
    )


def test_builder_step5c_precedes_step5_rolling_call():
    """A6 構成変更: build_rolling_features 呼出 が compute_field_strength_profile 呼出の後に
    位置すること（field_strength profile が history に揃った後で rolling する）。"""
    import re

    src = _read_builder_source()
    fs_match = re.compile(r"compute_field_strength_profile\(\s*raw_history\b").search(src)
    rolling_match = re.compile(r"build_rolling_features\(feature_matrix").search(src)
    assert fs_match is not None, "Step 5c compute_field_strength_profile(raw_history ...) が見つからない"
    assert rolling_match is not None, "Step 5 build_rolling_features(feature_matrix, ...) が見つからない"
    assert fs_match.start() < rolling_match.start(), (
        f"A6: Step 5c (pos={fs_match.start()}) が Step 5 rolling (pos={rolling_match.start()}) の後にある・"
        "field_strength profile が history に揃う前に rolling している (PLAN 04 A6 違反)"
    )


# ===========================================================================
# CR-02 (10-08 gap-closure): builder Step5c dtype 正規化 + JOIN 率 fail-loud
# ===========================================================================
def test_builder_step5c_has_race_date_dtype_normalization():
    """CR-02 (10-08 gap-closure): builder.py Step5c の profile merge 実行前に・
    ``history['race_date']`` と ``_profile_merge['race_date']`` の両者が pd.to_datetime で正規化される.

    dtype mismatch 由来の silent NaN merge を構造的に排除する（FEAT-02 21 feature 全行 sentinel 化の
    silent data loss 封印・core value「リーク防止」の鏡像「silent fallback 禁止」）。
    """
    src = _read_builder_source()
    assert 'pd.to_datetime(history["race_date"])' in src, (
        "CR-02: Step5c merge 前の history['race_date'] pd.to_datetime 正規化が builder.py に無い"
    )
    assert 'pd.to_datetime(_profile_merge["race_date"])' in src, (
        "CR-02: Step5c merge 前の _profile_merge['race_date'] pd.to_datetime 正規化が builder.py に無い"
    )


def test_builder_step5c_has_join_ratio_fail_loud():
    """CR-02 (10-08 gap-closure): builder.py Step5c の merge 後に・starter_mask 上の field_strength_mean の
    notna 率が 0.5 未満の場合に RuntimeError を raise する fail-loud 検査が存在する.

    FEAT-02 21 feature 全行 sentinel 化の silent data loss を検知する（core value「リーク防止」の鏡像）。
    """
    src = _read_builder_source()
    assert "joined_ratio" in src, (
        "CR-02: Step5c の field_strength_mean notna 率 (joined_ratio) 計算が builder.py に無い"
    )
    assert "0.5" in src, (
        "CR-02: Step5c の joined_ratio < 0.5 閾値が builder.py に無い"
    )
    assert "RuntimeError" in src, (
        "CR-02: Step5c の joined_ratio < 0.5 で raise する RuntimeError が builder.py に無い"
    )
    assert "CR-02 fail-loud" in src, (
        "CR-02: Step5c の fail-loud 検査に CR-02 識別子が無い"
    )



# ===========================================================================
# Test 5: assert_matrix_columns_registered が 27 新 feature で GREEN
# ===========================================================================
def test_assert_matrix_columns_registered_accepts_27_new_features():
    """registry 27 新 feature + reserved keys を assert_matrix_columns_registered に渡すと
    GREEN になること（SC#3 registry↔Parquet parity 機械保証）。"""
    spec = _spec()
    names = registered_feature_columns(spec)
    # 27 新 feature を含む registry 全 feature を渡して raise しない
    new_27 = [c for c in names if c.startswith("rolling_field_strength_")] + _FEAT03_REPRESENTATIVE
    assert len([c for c in new_27 if c in names]) == 21 + 6, (
        f"27 新 feature が registry に揃ってない・実際: {len(new_27)} (SC#3)"
    )
    # raise しなければ合格
    assert_matrix_columns_registered(spec, sorted(names))


# ===========================================================================
# Test 6: FEATURE_COLUMNS allowlist (model/data.py) が registry derived
# ===========================================================================
def test_feature_columns_allowlist_derived_from_registry():
    """FEATURE_COLUMNS allowlist (src/model/data.py) は registry から動的導出されるため・
    27 新 feature を含む（REVIEW H1・PLAN 06 LightGBM 再学習前提）。

    注意: FEATURE_COLUMNS は選択 snapshot_id の Parquet 実カラムと registry の積（H1-a）。
    よって本テストは「registry の 27 新 feature が _derive_feature_columns の候補に入る」ことのみ
    機械保証する（実際の Parquet 列は PLAN 05 で生成される）。
    """
    spec = _spec()
    reg = registered_feature_columns(spec)
    # 27 新 feature が registry 登録済み（_derive_feature_columns の入力に含まれる）
    new_27 = [c for c in reg if c.startswith("rolling_field_strength_")]
    assert len(new_27) == 21
    for feat in _FEAT03_REPRESENTATIVE:
        assert feat in reg, f"{feat} が registry に無い（FEATURE_COLUMNS 入力欠損）"
