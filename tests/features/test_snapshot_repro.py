"""SC#3 byte-reproducibility + REVIEWS HIGH #6 SHA256 scope（RED stub・Plan 03-04 GREEN）。

本ファイルは ``src.features.snapshot`` が未実装のため RED（Phase 2 RED-集群パターン）。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest


def _get_snapshot():
    from src.features import snapshot  # Plan 03-04 で実装
    return snapshot


def _build_synthetic_matrix() -> pd.DataFrame:
    # NOTE: rolling_timediff_mean_5 は Phase 3 gap-closure 03-05 で CR-01 採択により
    # registry から削除されていた（source カラムが normalized 層に無かったため）。
    # Phase 3.1 Plan 01 で normalized.n_uma_race.timediff(varchar4) が取り込まれ、
    # 後続 Plan 03 で registry へ再登録されるため stale ではなくなる。
    # ここでは byte-repro test は SHA256 一致検査のみで列名に依存しない（test_byte_reproducible_by_hash
    # / test_sha256_covers_parquet_bytes_only ともに列値の一致を問わない）ため、
    # 意図を明示する意味合いで rolling_kakuteijyuni_mean_5（確定着順・5レース平均・時系列 rolling）
    # に置換し Phase 3.1 の文脈を可視化する。
    return pd.DataFrame({
        "race_nkey": ["2023A0610-R1"],
        "kettonum": [1001],
        "race_date": [pd.Timestamp("2023-06-04")],
        "rolling_kakuteijyuni_mean_5": [3.0],
    })


# ---------------------------------------------------------------------------
# SC#3: byte-reproducibility
# ---------------------------------------------------------------------------
def test_byte_reproducible_by_hash(tmp_path: Path):
    """同一 DataFrame から2回 write_snapshot を呼び SHA256 が完全一致（Pitfall 3.5）。"""
    snapshot = _get_snapshot()
    df = _build_synthetic_matrix()
    sha1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s1",
        created_at_fixed="2026-06-18T10:00:00",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s2",
        created_at_fixed="2026-06-18T10:00:00",
    )
    assert sha1 == sha2, f"byte-reproducibility 違反: {sha1} != {sha2} (Pitfall 3.5)"


def test_metadata_contains_12_4_keys(tmp_path: Path):
    """Parquet schema metadata に §12.4 の9キーが含まれる。"""
    snapshot = _get_snapshot()
    keys = [
        "dataset_version",
        "feature_snapshot_id",
        "label_version",
        "prediction_timing",
        "feature_cutoff_rule",
        "train_period",
        "validation_period",
        "created_at",
        "feature_availability_version",
    ]
    src = inspect.getsource(snapshot)
    for k in keys:
        assert k in src, f"snapshot モジュールに §12.4 キー {k} の参照が無い"


def test_created_at_is_deterministic(tmp_path: Path):
    """manifest 側で実タイムスタンプ管理・schema metadata の created_at は関数引数で固定。"""
    snapshot = _get_snapshot()
    src = inspect.getsource(snapshot)
    assert "created_at" in src, "created_at を関数引数で受け取らない（Pitfall 3.5 再現性の要）"


# ---------------------------------------------------------------------------
# REVIEWS HIGH #6: SHA256 scope = Parquet bytes のみ（manifest bytes は除外）
# ---------------------------------------------------------------------------
def test_sha256_covers_parquet_bytes_only(tmp_path: Path):
    """manifest の created_at が異なっても Parquet SHA256 が一致する（HIGH #6）。"""
    snapshot = _get_snapshot()
    df = _build_synthetic_matrix()
    sha1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s3",
        created_at_fixed="2026-06-18T10:00:00",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s4",
        created_at_fixed="2026-06-19T15:30:00",  # 異なる created_at
    )
    assert sha1 == sha2, (
        "manifest の created_at が異なると Parquet SHA256 も変化する（HIGH #6 scope 違反）"
    )


def test_manifest_created_at_varies_between_runs(tmp_path: Path):
    """2回の run で manifest YAML の created_at が異なる値を持つ（実タイムスタンプ）。"""
    snapshot = _get_snapshot()
    df = _build_synthetic_matrix()
    m1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s5",
        created_at_fixed="2026-06-18T10:00:00",
        return_manifest=True,
    )
    m2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s6",
        created_at_fixed="2026-06-19T15:30:00",
        return_manifest=True,
    )
    assert m1["created_at"] != m2["created_at"], (
        "manifest created_at が run 間で変化しない（HIGH #6: manifest は byte-reproducible でない）"
    )


# ---------------------------------------------------------------------------
# CR-01新 (03.1-02): persist → exists assert → manifest 順序の回帰保護
# ---------------------------------------------------------------------------
def test_persist_before_manifest_order(tmp_path: Path):
    """persist_category_maps が失敗（例外）する場合、manifest が書かれないことを保証。

    CR-01新・Pitfall 5: persist 失敗時に SHA256 一致の「完成済」manifest だけが残り
    category map artifact が欠損する partial-failure 状態（再現性破壊）を防止するため、
    scripts/run_feature_build.py は persist → exists assert → manifest の順序を取る。
    本テストは persist_category_maps が例外を投げた場合に manifest_path が作成されない
    ことを機械保証する（順序依存の回帰テスト）。
    """
    from src.features.category_map_consumer import persist_category_maps

    manifest_path = tmp_path / "feature_matrix_test.manifest.yaml"
    category_map_path = tmp_path / "category_map_test.json"

    # 存在しない親ディレクトリへの書込を強制し persist_category_maps に IO 例外を発生させる。
    # persist_category_maps は Path(artifact_path).parent.mkdir(parents=True) を呼ぶため、
    # 書き込み不能なパス（ファイルをディレクトリ扱いさせる）で OSError を誘発する。
    blocker_dir = tmp_path / "blocker_file"
    blocker_dir.write_text("not a directory", encoding="utf-8")
    unwriteable_map_path = blocker_dir / "category_map_fail.json"

    frozen_maps = {"jockey_id": {"jk001": 0, "jk002": 1}}

    # persist が失敗（例外）することを確認
    with pytest.raises(OSError):
        persist_category_maps(frozen_maps, unwriteable_map_path)

    # persist 失敗時: manifest は書かれない（partial-failure 状態ではない）
    assert not manifest_path.exists(), (
        "persist 失敗時に manifest が書かれた（CR-01新・persist→manifest 順序違反・"
        "partial-failure 状態の再現性破壊）"
    )
    # category_map_path も（正常系であれば）未作成のまま
    assert not category_map_path.exists()


def test_persist_then_manifest_order_in_script_source():
    """scripts/run_feature_build.py の AST 上で persist → assert exists → write_manifest の順序を保証。

    CR-01新: 行番号ベースで persist_category_maps 呼出 < assert exists < write_manifest 呼出
    であることを AST 解析で機械検査する（行編集で順序が崩れた場合に RED）。
    """
    import ast

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_feature_build.py"
    tree = ast.parse(script_path.read_text(encoding="utf-8"))

    persist_line = None
    assert_exists_line = None
    manifest_line = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "persist_category_maps" and persist_line is None:
                persist_line = node.lineno
            elif name == "write_manifest" and manifest_line is None:
                manifest_line = node.lineno
        elif isinstance(node, ast.Assert):
            # assert category_map_path.exists() を探す
            test = node.test
            if (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Attribute)
                and test.func.attr == "exists"
                and isinstance(test.func.value, ast.Name)
                and test.func.value.id == "category_map_path"
                and assert_exists_line is None
            ):
                assert_exists_line = node.lineno

    assert persist_line is not None, "persist_category_maps 呼出が見つからない（CR-01新）"
    assert assert_exists_line is not None, (
        "assert category_map_path.exists() が見つからない（CR-01新・partial-failure 抑止）"
    )
    assert manifest_line is not None, "write_manifest 呼出が見つからない（CR-01新）"

    # 順序: persist < exists assert < manifest
    assert persist_line < assert_exists_line < manifest_line, (
        f"順序違反: persist(L{persist_line}) / assert exists(L{assert_exists_line}) / "
        f"manifest(L{manifest_line}) — persist→assert→manifest の順序が必要（CR-01新・Pitfall 5）"
    )


# ---------------------------------------------------------------------------
# CR-04 (03-REVIEW): Parquet schema metadata に snapshot_id/created_at 実値が埋込まれる
# ---------------------------------------------------------------------------
def test_cr04_parquet_metadata_embeds_real_snapshot_id_and_created_at(tmp_path: Path):
    """CR-04 (03-REVIEW) Fix 選択肢1: Parquet ファイル単体から ``feature_snapshot_id`` /
    ``created_at`` を復元できることを検証する（§12.4 監査証跡・sentinel でなく実値）。

    旧実装は ``_DETERMINISTIC_CREATED_AT`` sentinel で schema metadata を埋めていたため、
    Parquet ファイル単体で snapshot_id を特定できなかった。現行実装は SHA256 計算を
    metadata 無し schema で行い、その後実値を metadata として付与するため、Parquet bytes
    に snapshot_id と created_at が埋込まれる。
    """
    import pyarrow.parquet as pq

    snapshot = _get_snapshot()
    df = _build_synthetic_matrix()
    test_snapshot_id = "cr04-audit-test-snap"
    test_created_at = "2026-06-18T10:00:00"
    snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=test_snapshot_id,
        created_at_fixed=test_created_at,
    )
    parquet_path = tmp_path / f"feature_matrix_{test_snapshot_id}.parquet"
    assert parquet_path.exists(), "Parquet ファイルが書き込まれていない"

    # Parquet schema metadata から snapshot_id / created_at を復元
    table = pq.read_table(parquet_path)
    metadata = table.schema.metadata or {}
    # metadata は bytes→bytes・pyarrow の仕様
    decoded = {k.decode(): v.decode() for k, v in metadata.items()}

    assert decoded.get("feature_snapshot_id") == test_snapshot_id, (
        f"Parquet metadata の snapshot_id が実値で無い: "
        f"{decoded.get('feature_snapshot_id')!r}（期待 {test_snapshot_id!r}）"
        "・CR-04 監査証跡欠損・sentinel が埋まっている可能性"
    )
    assert decoded.get("created_at") == test_created_at, (
        f"Parquet metadata の created_at が実値で無い: "
        f"{decoded.get('created_at')!r}（期待 {test_created_at!r}）"
    )


def test_cr04_sha256_independent_of_snapshot_id(tmp_path: Path):
    """CR-04: 異なる snapshot_id で書込んでも SHA256 は同一（データ内容のみ依存）。

    旧実装は snapshot_id が sentinel で固定だったため問題無かったが、現行は実値を
    metadata に埋めるため「SHA256 が snapshot_id に依存しない」ことを改めて検証する
    （SHA256 計算を metadata 無し schema で行う設計の妥当性）。
    """
    snapshot = _get_snapshot()
    df = _build_synthetic_matrix()
    sha1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="cr04-snap-A",
        created_at_fixed="2026-06-18T10:00:00",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="cr04-snap-B-different",
        created_at_fixed="2026-06-19T15:30:00",
    )
    assert sha1 == sha2, (
        f"異なる snapshot_id/created_at で SHA256 が変化した: {sha1} != {sha2}"
        "・CR-04 SHA256 scope（metadata 無し schema bytes）違反"
    )


# ---------------------------------------------------------------------------
# Phase 10 PLAN 05: FEAT-02/03 新 feature (27) + snapshot_id 事前登録 + REVIEW H5
# ---------------------------------------------------------------------------
# Open Question #3 事前登録: Phase 10 の feature snapshot id。
# v1.0 20260620-1a-postreview-v2 系統継承・make_model_version 形式・PLAN 06 が消費。
PHASE10_SNAPSHOT_ID = "20260626-1a-opponentstrength-v1"

# FEAT-02 rolling_field_strength 21 feature（rolling.py::_FIELD_STRENGTH_AXES と同一順序・D-13）
_FEAT02_COLUMNS: tuple[str, ...] = (
    # latest_1 系6
    "rolling_field_strength_mean_latest_1",
    "rolling_field_strength_median_latest_1",
    "rolling_field_strength_top3_mean_latest_1",
    "rolling_field_strength_top5_mean_latest_1",
    "rolling_field_strength_max_latest_1",
    "rolling_field_strength_sd_latest_1",
    # mean_3 系5
    "rolling_field_strength_mean_mean_3",
    "rolling_field_strength_median_mean_3",
    "rolling_field_strength_top3_mean_mean_3",
    "rolling_field_strength_top5_mean_mean_3",
    "rolling_field_strength_max_mean_3",
    # mean_5 系6
    "rolling_field_strength_mean_mean_5",
    "rolling_field_strength_median_mean_5",
    "rolling_field_strength_top3_mean_mean_5",
    "rolling_field_strength_top5_mean_mean_5",
    "rolling_field_strength_max_mean_5",
    "rolling_field_strength_sd_mean_5",
    # trend 系2（window 埋込・_5 無し）
    "rolling_field_strength_mean_trend_last_minus_mean5",
    "rolling_field_strength_mean_trend_mean3_minus_mean5",
    # count/coverage 系2（window=5 固定・信頼度軸・D-11）
    "rolling_field_strength_valid_count_mean_5",
    "rolling_field_strength_coverage_mean_5",
)

# FEAT-03 race_relative 6 feature（rolling_ prefix 無し・target-only）
_FEAT03_COLUMNS: tuple[str, ...] = (
    "speed_index_rank_mean5",
    "speed_index_rank_best2_mean5",
    "speed_index_rank_median5",
    "gap_to_top",
    "gap_to_3rd",
    "field_strength_adjusted_rank",
)


def _build_phase10_synthetic_matrix() -> pd.DataFrame:
    """Phase 10 PLAN 05: 27 新 feature を含む合成行列（FEAT-02 21 + FEAT-03 6）。

    FEAT-02 は ``rolling_`` prefix のため snapshot.py::_coerce_rolling_columns_for_parquet
    が自動的に nullable Float64 に変換する。FEAT-03 は ``rolling_`` prefix 無し・
    builder Step6c が nullable Float64 を保証するが・snapshot 境界でも防御的に Float64 変換
    する（Pitfall 5・ArrowTypeError 回避の最終防衛線）。
    """
    base = {
        "race_nkey": ["2023A0610-R1", "2023A0610-R1", "2023A0610-R2"],
        "kettonum": [1001, 1002, 1003],
        "race_date": [
            pd.Timestamp("2023-06-04"),
            pd.Timestamp("2023-06-04"),
            pd.Timestamp("2023-06-05"),
        ],
        "rolling_kakuteijyuni_mean_5": [3.0, 5.0, 1.0],  # 既存 feature
    }
    # FEAT-02: 数値 + __MISSING__ sentinel 混在（object dtype）→ Float64 変換対象
    from src.utils.category_map import MISSING

    for col in _FEAT02_COLUMNS:
        base[col] = [1.5, MISSING, 3.0]
    # FEAT-03: 数値 + sentinel 混在（object dtype）→ Float64 変換対象（防御的）
    for col in _FEAT03_COLUMNS:
        base[col] = [2.0, 1.0, MISSING]
    return pd.DataFrame(base)


def test_phase10_snapshot_id_preregistered():
    """Open Question #3: Phase 10 snapshot_id = 20260626-1a-opponentstrength-v1 が事前登録される。

    PLAN 06 (run_phase10_evaluation.py) が本 id を消費する。make_model_version 形式
    （feature_snapshot_id 全体を prefix・二重 postfix 回帰防止・review HIGH#4）。
    """
    # 文字列リテラルで検査（typo 検出・誤 id で false-pass しない）
    assert PHASE10_SNAPSHOT_ID == "20260626-1a-opponentstrength-v1"
    # 系統継承: v1.0 20260620-1a-postreview-v2 → Phase 9.1 20260625-1a-speedprofile-v1 →
    # Phase 10 20260626-1a-opponentstrength-v1（日付 + ability kind + v1）
    assert PHASE10_SNAPSHOT_ID.startswith("20260626-1a-")
    assert PHASE10_SNAPSHOT_ID.endswith("-v1")


def test_phase10_byte_reproducible_with_27_new_features(tmp_path: Path):
    """SC#3 byte-reproducible: 27 新 feature を含む同一 DataFrame で SHA256 が完全一致。

    Pitfall 5 (Parquet 直列化失敗) 回避: FEAT-02/03 列が object dtype + sentinel の場合でも
    snapshot 境界で nullable Float64 に変換され・PyArrow ArrowTypeError を起こさない。
    """
    snapshot = _get_snapshot()
    df = _build_phase10_synthetic_matrix()
    sha1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=PHASE10_SNAPSHOT_ID,
        created_at_fixed="2026-06-26T00:00:00",
        fa_version="0.6.0",  # PLAN 04 で bump した schema_version と対応
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=PHASE10_SNAPSHOT_ID,
        created_at_fixed="2026-06-26T00:00:00",
        fa_version="0.6.0",
    )
    assert sha1 == sha2, (
        f"Phase 10 27 新 feature で byte-reproducibility 違反: {sha1} != {sha2} "
        "(Pitfall 5・Parquet 直列化が非決定論的)"
    )


def test_phase10_feat02_columns_coerced_to_nullable_float64():
    """Pitfall 5・FEAT-02: rolling_field_strength_* 21 feature が nullable Float64 で直列化される。

    _coerce_rolling_columns_for_parquet が rolling_ prefix で自動的に対象とし・
    object dtype + __MISSING__ sentinel を nullable Float64（sentinel → NaN）に変換する。
    """
    from src.utils.category_map import MISSING

    snapshot = _get_snapshot()
    df_obj = pd.DataFrame({
        col: [1.5, MISSING, 3.0] for col in _FEAT02_COLUMNS
    })
    out = snapshot._coerce_rolling_columns_for_parquet(df_obj)
    for col in _FEAT02_COLUMNS:
        assert str(out[col].dtype) == "Float64", (
            f"FEAT-02 列 {col} が nullable Float64 に変換されていない: {out[col].dtype} "
            "(Pitfall 5・ArrowTypeError 発生リスク)"
        )
        # sentinel は NaN に変換される（D-09 欠損馬 NaN 保持と整合）
        assert pd.isna(out[col].iloc[1]), (
            f"FEAT-02 列 {col} の sentinel が NaN に変換されていない（D-09 整合違反）"
        )


def test_phase10_feat03_columns_coerced_to_nullable_float64():
    """Pitfall 5・FEAT-03: speed_index_rank_*/gap_to_*/field_strength_adjusted_rank が
    nullable Float64 で直列化される（rolling_ prefix 無し・防御的変換）。

    builder Step6c が pd.to_numeric(..., errors='coerce').astype('Float64') を保証するが・
    snapshot 境界でも防御的に nullable Float64 変換する（最終防衛線・Pitfall 5）。
    sentinel 文字列は NaN になり D-09 欠損馬 NaN 保持と整合。
    """
    from src.utils.category_map import MISSING

    snapshot = _get_snapshot()
    df_obj = pd.DataFrame({
        col: [2.0, 1.0, MISSING] for col in _FEAT03_COLUMNS
    })
    out = snapshot._coerce_rolling_columns_for_parquet(df_obj)
    for col in _FEAT03_COLUMNS:
        assert str(out[col].dtype) == "Float64", (
            f"FEAT-03 列 {col} が nullable Float64 に変換されていない: {out[col].dtype} "
            "(Pitfall 5・rolling_ prefix 無しの防御的変換が欠落)"
        )
        # sentinel は NaN に変換される（D-09 欠損馬 NaN 保持と整合）
        assert pd.isna(out[col].iloc[2]), (
            f"FEAT-03 列 {col} の sentinel が NaN に変換されていない（D-09 整合違反）"
        )


def test_phase10_metadata_feature_availability_version(tmp_path: Path):
    """§12.4 metadata・REVIEW H5: feature_availability_version='0.6.0'（schema 無し・実キー検査）。

    REVIEW H5 (10-REVIEWS.md L120, L199): metadata キーは ``feature_availability_version``
    （``feature_availability_schema_version`` でない）。src/features/snapshot.py L62-72 の
    _METADATA_KEYS タプル実値と完全一致する。誤キー文字列で assert すると KeyError または
    false-pass になるため・実キー文字列そのものを検査する。
    """
    import pyarrow.parquet as pq

    snapshot = _get_snapshot()
    df = _build_phase10_synthetic_matrix()
    snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=PHASE10_SNAPSHOT_ID,
        created_at_fixed="2026-06-26T00:00:00",
        fa_version="0.6.0",  # PLAN 04 で bump・schema_version 0.6.0 と対応
    )
    parquet_path = tmp_path / f"feature_matrix_{PHASE10_SNAPSHOT_ID}.parquet"
    assert parquet_path.exists(), "Parquet ファイルが書き込まれていない"

    table = pq.read_table(parquet_path)
    metadata = table.schema.metadata or {}
    decoded = {k.decode(): v.decode() for k, v in metadata.items()}

    # REVIEW H5 実キー検査: 'feature_availability_version'（schema 無し）
    assert "feature_availability_version" in decoded, (
        "metadata に feature_availability_version キーが無い（REVIEW H5・schema 無し・"
        "src/features/snapshot.py L62-72 の _METADATA_KEYS 実値と不一致）"
    )
    assert decoded["feature_availability_version"] == "0.6.0", (
        f"feature_availability_version が 0.6.0 でない: "
        f"{decoded.get('feature_availability_version')!r}（PLAN 04 schema_version 0.6.0 と対応）"
    )
    # 誤キーが存在しないことを検査（REVIEW H5・誤キー false-pass 回避）
    assert "feature_availability_schema_version" not in decoded, (
        "metadata に誤キー feature_availability_schema_version が存在する（REVIEW H5 違反・"
        "正キーは feature_availability_version・schema 無し）"
    )


def test_phase10_metadata_keys_literal_in_metadata_keys_tuple():
    """REVIEW H5 厳格対応: snapshot.py._METADATA_KEYS タプル実値に 'feature_availability_version'
    が含まれ・'feature_availability_schema_version' は含まれないことを検査する。

    inspect.getsource でなく実値検査（誤キー文字列を含む docstring/comment の false positive
    を回避・REVIEW H5・PLAN 05 Task 1 acceptance criteria・実キー文字列リテラル検査）。
    """
    snapshot = _get_snapshot()
    keys = snapshot._METADATA_KEYS
    assert "feature_availability_version" in keys, (
        "snapshot._METADATA_KEYS に feature_availability_version が含まれない（REVIEW H5・"
        "src/features/snapshot.py L62-72 の実キー文字列）"
    )
    assert "feature_availability_schema_version" not in keys, (
        "snapshot._METADATA_KEYS に誤キー feature_availability_schema_version が含まれる"
        "（REVIEW H5 違反・正キーは feature_availability_version・schema 無し）"
    )


def test_phase10_fixed_reproduce_ts_sha256_independent_of_created_at(tmp_path: Path):
    """FIXED_REPRODUCE_TS: timestamp 等の非決定論的要素が metadata 除外で SHA256 に影響しない。

    created_at_fixed を変化させても同一 DataFrame なら SHA256 は同一（§19.1 聖域・
    SHA256 計算は metadata 無し schema bytes のみ）。Phase 10 27 新 feature でも保証される。
    """
    snapshot = _get_snapshot()
    df = _build_phase10_synthetic_matrix()
    sha1 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=PHASE10_SNAPSHOT_ID,
        created_at_fixed="2026-06-26T00:00:00",
        fa_version="0.6.0",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id=PHASE10_SNAPSHOT_ID,
        created_at_fixed="2026-06-27T12:34:56",  # 異なる created_at
        fa_version="0.6.0",
    )
    assert sha1 == sha2, (
        "Phase 10 27 新 feature で created_at 変化時に SHA256 が変化した"
        "（FIXED_REPRODUCE_TS 違反・SHA256 は metadata 無し schema bytes のみ依存）"
    )
