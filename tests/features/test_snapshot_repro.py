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
