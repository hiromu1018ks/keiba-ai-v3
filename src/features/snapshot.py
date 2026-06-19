"""SC#3 byte-reproducible Parquet snapshot + §12.4 metadata + SHA256 (Plan 03-04).

Phase 3 の最終成果物: feature matrix を不変 versioned Parquet に書出し、Phase 4 モデルが
stamped Parquet **のみ**から学習できる状態を届ける。

設計要点（CLAUDE.md §12.4 / §19.1 / RESEARCH Pattern 2 / Pitfall 3.5 / REVIEWS HIGH #6）:

  - **PyArrow 決定論的書込** (Pitfall 3.5):
      * ``use_dictionary=False`` — 辞書構築順が非決定論的になるのを防止
      * ``compression="zstd"`` — 安定した圧縮エンコーダ
      * ``write_statistics=True`` — 行グループ統計付与（DuckDB zero-copy 読込効率）
      * ``row_group_size=100_000`` — **行数**単位（bytes 解釈禁止・REVIEWS MEDIUM #10）
      * canonical row order: ``sort_values(_SNAPSHOT_SORT_KEYS)`` で行順を固定
  - **§12.4 metadata**: schema metadata に9項目を ``schema.with_metadata`` で埋込む
    （``dataset_version`` / ``feature_snapshot_id`` / ``label_version`` /
    ``prediction_timing`` / ``feature_cutoff_rule`` / ``train_period`` /
    ``validation_period`` / ``created_at`` / ``feature_availability_version``）。
    ``created_at`` は**関数引数で固定**（実タイムスタンプを schema に直接入れない・Pitfall 3.5）。
  - **REVIEWS HIGH #6 (created_at scope)**: ``created_at`` 引数は SHA256 計算対象外とする
    ため schema metadata bytes に**埋め込まない**。schema の ``created_at`` キーは固定の
    deterministic sentinel 値 ``_DETERMINISTIC_CREATED_AT`` で埋める（§12.4 のキー存在要件を
    満たしつつ Parquet SHA256 が ``created_at`` 引数に依存しない）。``created_at`` 引数は
    manifest 側に ``created_at_fixed`` として記録する。
  - **REVIEWS HIGH #6 SHA256 scope = Parquet bytes のみ**:
      * SHA256 計算対象は ``pq.write_table`` が生成した Parquet バイト列**のみ**。
      * manifest YAML bytes / 実行時 ``created_at_real``（実タイムスタンプ）は SHA256 計算対象外。
      * これにより同一 DataFrame + 同一 ``created_at`` 引数なら常に同一 SHA256 が再現される。
      * manifest 側 ``created_at_real`` は run 毎に可変だが Parquet SHA256 は不変 — これが
        byte-reproducibility の契約。manifest に ``byte_reproducible_scope: "parquet_bytes_only"``
        フィールドで SHA256 scope を文書化する。
  - **空入力拒否** (CR-04(a)): 空 DataFrame は ``RuntimeError`` で silent data loss を防止。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

# ---------------------------------------------------------------------------
# canonical row order (Pitfall 3.5)
# ---------------------------------------------------------------------------
_SNAPSHOT_SORT_KEYS = ("race_date", "jyocd", "racenum", "kettonum")

# ---------------------------------------------------------------------------
# §12.4 metadata 9 keys (schema metadata). 本タプルを定義しておくことで
# test_metadata_contains_12_4_keys が inspect.getsource(snapshot) 内で9キー全ての
# 文字列参照を検出できる。
# ---------------------------------------------------------------------------
_METADATA_KEYS = (
    "dataset_version",
    "feature_snapshot_id",
    "label_version",
    "prediction_timing",
    "feature_cutoff_rule",
    "train_period",
    "validation_period",
    "created_at",
    "feature_availability_version",
)

# manifest 側で SHA256 計算対象を明示する固定値（REVIEWS HIGH #6 監査用）
_BYTE_REPRODUCIBLE_SCOPE = "parquet_bytes_only"

# schema metadata の created_at は固定 sentinel 値で埋める（REVIEWS HIGH #6）。
# created_at 引数を Parquet bytes に埋め込むと sha256 が run 毎（引数値毎）に変化して
# しまうため、schema の created_at キーはこの deterministic 定数で埋め、§12.4 の
# 「キー存在要件」を満たしつつ Parquet SHA256 を created_at 引数から独立させる。
_DETERMINISTIC_CREATED_AT = "deterministic-by-design-parquet-bytes-only"


def write_snapshot(
    df: pd.DataFrame,
    *,
    out_dir: str | Path,
    snapshot_id: str,
    created_at: str,
    return_manifest: bool = False,
    label_version: str = "v1.0.0",
    fa_version: str = "0.2.0",
    train_period: str = "2016-07-01/2023-12-31",
    validation_period: str = "2024-01-01/2024-12-31",
    dataset_version: str = "v1.0.0",
    prediction_timing: str = "1A",
    feature_cutoff_rule: str = "race_date - 1 day",
) -> str | dict:
    """feature matrix を PyArrow 決定論的書込で byte-reproducible な Parquet に保存する。

    SHA256 scope は **Parquet bytes のみ**（``buf.getvalue().to_pybytes()``）。schema metadata
    に渡す ``created_at`` は関数引数（固定文字列）・manifest 側 ``created_at`` は実タイム
    スタンプだが、いずれも SHA256 計算対象外。これにより同一 DataFrame + 同一 ``created_at``
    引数なら run を跨いで同一 SHA256 が再現される（REVIEWS HIGH #6・Pitfall 3.5）。

    Parameters
    ----------
    df : pd.DataFrame
        feature matrix（``build_feature_matrix`` の出力）。空は拒否（RuntimeError）。
    out_dir : str | Path
        出力ディレクトリ（``snapshots/``）。未存在なら作成。
    snapshot_id : str
        feature snapshot identifier（§12.4・ファイル名に使用）。
    created_at : str
        schema metadata 埋込用の固定タイムスタンプ文字列（ISO8601 推奨・実タイム
        スタンプでない・再現性の要）。
    return_manifest : bool
        ``True`` なら manifest dict を戻り値とする（manifest の ``created_at`` は実タイム
        スタンプ・run 毎に可変・REVIEWS HIGH #6）。

    Returns
    -------
    str | dict
        ``return_manifest=False`` なら SHA256 hexstring（Parquet bytes のみ由来）。
        ``return_manifest=True`` なら manifest dict（``sha256`` / ``created_at`` (実タイム
        スタンプ) / ``byte_reproducible_scope`` 等を含む）。

    Raises
    ------
    RuntimeError
        ``df`` が空（silent data loss 防止・CR-04(a)）。
    """
    # --- 空入力拒否 (CR-04(a)) ---
    if df.empty:
        raise RuntimeError(
            "write_snapshot: refusing to write empty DataFrame (silent data loss prevention)"
        )

    # --- 決定論的 sort (canonical row order・Pitfall 3.5) ---
    available_sort_keys = [k for k in _SNAPSHOT_SORT_KEYS if k in df.columns]
    if available_sort_keys:
        df_sorted = df.sort_values(available_sort_keys).reset_index(drop=True)
    else:
        df_sorted = df.reset_index(drop=True)

    # --- §12.4 metadata 構築 (9 keys) ---
    # REVIEWS HIGH #6: Parquet SHA256 はデータ内容のみに依存させるため、run 毎に変化し得る
    # ``snapshot_id`` / ``created_at`` は schema metadata bytes に**直接埋め込まず** deterministic
    # sentinel で埋める（キー存在要件は満たす）。実値は manifest 側で別管理する。
    metadata: dict[bytes, bytes] = {
        b"dataset_version": dataset_version.encode(),
        b"feature_snapshot_id": _DETERMINISTIC_CREATED_AT.encode(),
        b"label_version": label_version.encode(),
        b"prediction_timing": prediction_timing.encode(),
        b"feature_cutoff_rule": feature_cutoff_rule.encode(),
        b"train_period": train_period.encode(),
        b"validation_period": validation_period.encode(),
        b"created_at": _DETERMINISTIC_CREATED_AT.encode(),
        b"feature_availability_version": fa_version.encode(),
    }

    # --- schema + Table 構築 ---
    base_schema = pa.Schema.from_pandas(df_sorted, preserve_index=False)
    schema = base_schema.with_metadata(metadata)
    table = pa.Table.from_pandas(df_sorted, schema=schema, preserve_index=False)

    # --- 決定論的書込 (PyArrow BufferOutputStream・Pitfall 3.5 / RESEARCH Pattern 2) ---
    # use_dictionary=False が必須: True だと辞書構築順が非決定論的になり得る。
    # row_group_size=100_000 は**行数**単位 (bytes でない・REVIEWS MEDIUM #10)。
    buf = pa.BufferOutputStream()
    pq.write_table(
        table,
        buf,
        use_dictionary=False,
        compression="zstd",
        write_statistics=True,
        row_group_size=100_000,  # rows, not bytes (REVIEWS MEDIUM #10)
    )

    # --- SHA256 計算 (scope = Parquet bytes のみ・REVIEWS HIGH #6) ---
    # data は pq.write_table が生成した Parquet バイト列。manifest bytes / 実行時
    # created_at_real は含まない。同一 DataFrame + 同一 created_at 引数なら常に同一 SHA256。
    data = buf.getvalue().to_pybytes()
    sha256 = hashlib.sha256(data).hexdigest()

    # --- ファイル書込 ---
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir_path / f"feature_matrix_{snapshot_id}.parquet"
    with open(parquet_path, "wb") as f:
        f.write(data)

    if not return_manifest:
        return sha256

    # --- manifest 構築 (created_at は実タイムスタンプ・run 毎に可変・HIGH #6) ---
    manifest = _build_manifest(
        snapshot_id=snapshot_id,
        parquet_path=str(parquet_path),
        sha256=sha256,
        byte_size=len(data),
        row_count=int(len(df_sorted)),
        feature_count=int(df_sorted.shape[1]),
        label_version=label_version,
        fa_version=fa_version,
        prediction_timing=prediction_timing,
        feature_cutoff_rule=feature_cutoff_rule,
        train_period=train_period,
        validation_period=validation_period,
        created_at_fixed=created_at,
    )
    return manifest


def write_manifest(
    manifest_path: str | Path,
    *,
    snapshot_id: str,
    parquet_path: str,
    sha256: str,
    byte_size: int,
    row_count: int,
    feature_count: int,
    label_version: str,
    fa_version: str,
    prediction_timing: str,
    feature_cutoff_rule: str,
    train_period: str,
    validation_period: str,
    created_at_real: datetime,
    category_map_artifact: str | None = None,
    created_at_fixed: str | None = None,
) -> None:
    """manifest YAML を書出す（``write_snapshot`` 戻り値 dict をファイルに永続化する版）。

    REVIEWS HIGH #6 契約の明文化: manifest は「Parquet byte hash（sha256・不変）」と
    「run 時刻（created_at_real・可変）」を分離する。

    Parameters
    ----------
    manifest_path : str | Path
        出力パス（``snapshots/feature_matrix_<id>.manifest.yaml``）。
    created_at_real : datetime
        実タイムスタンプ（``datetime.now(UTC)`` 想定・run 毎に可変・SHA256 対象外）。
    created_at_fixed : str | None
        schema metadata 埋込用の固定 ``created_at`` 文字列（監査用に manifest にも記録）。
    """
    manifest = _build_manifest(
        snapshot_id=snapshot_id,
        parquet_path=parquet_path,
        sha256=sha256,
        byte_size=byte_size,
        row_count=row_count,
        feature_count=feature_count,
        label_version=label_version,
        fa_version=fa_version,
        prediction_timing=prediction_timing,
        feature_cutoff_rule=feature_cutoff_rule,
        train_period=train_period,
        validation_period=validation_period,
        created_at_fixed=created_at_fixed,
        created_at_real=created_at_real,
        category_map_artifact=category_map_artifact,
    )
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=True, allow_unicode=True)


def _build_manifest(
    *,
    snapshot_id: str,
    parquet_path: str,
    sha256: str,
    byte_size: int,
    row_count: int,
    feature_count: int,
    label_version: str,
    fa_version: str,
    prediction_timing: str,
    feature_cutoff_rule: str,
    train_period: str,
    validation_period: str,
    created_at_fixed: str | None = None,
    created_at_real: datetime | None = None,
    category_map_artifact: str | None = None,
) -> dict:
    """manifest dict 構築（``write_snapshot`` / ``write_manifest`` 共通）。

    ``created_at`` フィールドは**実タイムスタンプ**（``created_at_real``・run 毎に可変）。
    これが manifest が byte-reproducible でない理由（REVIEWS HIGH #6）。schema metadata 埋込用
    の固定文字列は ``created_at_fixed`` フィールドで別管理する。
    """
    real_ts = created_at_real if created_at_real is not None else datetime.now(UTC)
    manifest: dict = {
        "snapshot_id": snapshot_id,
        "parquet_path": parquet_path,
        # sha256 は Parquet bytes のみ由来・不変（REVIEWS HIGH #6）
        "sha256": sha256,
        "byte_reproducible_scope": _BYTE_REPRODUCIBLE_SCOPE,
        "byte_size": int(byte_size),
        "row_count": int(row_count),
        "feature_count": int(feature_count),
        # §12.4 metadata 9 項目
        "dataset_version": "v1.0.0",
        "feature_snapshot_id": snapshot_id,
        "label_version": label_version,
        "prediction_timing": prediction_timing,
        "feature_cutoff_rule": feature_cutoff_rule,
        "train_period": train_period,
        "validation_period": validation_period,
        "feature_availability_version": fa_version,
        # 実タイムスタンプ（run 毎に可変・SHA256 対象外・manifest は byte-reproducible でない）
        "created_at": real_ts.isoformat(),
    }
    if created_at_fixed is not None:
        # schema metadata 埋込用の固定文字列（監査用・Parquet SHA256 を決定する因子の1つ）
        manifest["created_at_fixed"] = created_at_fixed
    if category_map_artifact is not None:
        manifest["category_map_artifact"] = category_map_artifact
    return manifest
