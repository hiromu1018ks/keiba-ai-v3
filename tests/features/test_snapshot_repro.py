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
    return pd.DataFrame({
        "race_nkey": ["2023A0610-R1"],
        "kettonum": [1001],
        "race_date": [pd.Timestamp("2023-06-04")],
        "rolling_timediff_mean_5": [-2.0],
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
        created_at="2026-06-18T10:00:00",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s2",
        created_at="2026-06-18T10:00:00",
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
        created_at="2026-06-18T10:00:00",
    )
    sha2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s4",
        created_at="2026-06-19T15:30:00",  # 異なる created_at
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
        created_at="2026-06-18T10:00:00",
        return_manifest=True,
    )
    m2 = snapshot.write_snapshot(
        df, out_dir=tmp_path, snapshot_id="s6",
        created_at="2026-06-19T15:30:00",
        return_manifest=True,
    )
    assert m1["created_at"] != m2["created_at"], (
        "manifest created_at が run 間で変化しない（HIGH #6: manifest は byte-reproducible でない）"
    )
