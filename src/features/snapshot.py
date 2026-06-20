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
  - **CR-04 (03-REVIEW) Fix 選択肢1 + IN-03**: SHA256 は **metadata 無し schema bytes** のみ
    から計算する（データ内容のみ依存・snapshot_id/created_at 等の run 毎変動因子を除外）。
    その後 schema metadata（実際の ``snapshot_id`` と ``created_at_fixed`` 引数を含む）を
    付与して Parquet bytes を書込む。これにより:
      * **byte-reproducibility**: 同一 DataFrame なら snapshot_id/created_at が異なっても
        SHA256 は同一（データ内容のみ依存）。
      * **§12.4 監査証跡**: Parquet ファイル単体から ``feature_snapshot_id`` / ``created_at``
        を復元可能（sentinel でなく実値を埋込む）。
  - **REVIEWS HIGH #6 SHA256 scope = データ内容（metadata 無し schema）のみ**:
      * SHA256 計算対象は metadata 無し schema の Parquet バイト列**のみ**。
      * manifest YAML bytes / 実行時 ``created_at_real``（実タイムスタンプ）は SHA256 計算対象外。
      * これにより同一 DataFrame なら常に同一 SHA256 が再現される。
      * manifest 側 ``created_at_real`` は run 毎に可変だが SHA256 は不変 — これが
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

from src.features.rolling import _CATEGORICAL_SYSTEMS
from src.utils.category_map import MISSING

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
# CR-04 (03-REVIEW) 後: SHA256 scope は「metadata 無し schema bytes」に変更。
# snapshot_id/created_at は SHA256 計算後に metadata として付与されるため、
# SHA256 はこれら run 毎変動因子に依存しない（データ内容のみ依存）。
_BYTE_REPRODUCIBLE_SCOPE = "parquet_data_only_metadata_excluded"


def _coerce_rolling_columns_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """rolling 出力の object dtype 列を Parquet 直列化可能な nullable dtype に統一する。

    CR-02 (03-REVIEW) で categorical 系統（``jyocd`` mode/latest）が追加された。列が categorical
    系統か（``_is_categorical_rolling_col``）で分岐する:

      - **numeric 系統**（kakuteijyuni/harontimel3/jyuni3c_jyuni4c/kyori/days_since_prev/
        timediff/babacd の mean/latest/sd・全系統の count）: 数値 + ``__MISSING__`` sentinel →
        nullable ``Float64``（従来通り）。
      - **categorical 系統**（jyocd mode/latest）: 文字列値 + sentinel → nullable ``string``
        （sentinel → ``<NA>``）。varchar(2) 競馬場コードを ``"06"→6.0`` のように数値化しない
        （CR-02 の「文字列の最頻値」意図を完遂・実データ検証で ``_coerce`` の数値化副作用を発見）。

    値の「数値化可能性」では判定しない（``"06"`` は数字文字列で ``to_numeric`` 可能だが categorical）。
    rolling.py の ``_CATEGORICAL_SYSTEMS`` で系統を明示判定する。D-13 契約（object + sentinel）は
    不変・本関数は Parquet 出力前の直列化変換のみ。byte-reproducibility は維持（決定論的 cast）。
    """
    result = df.copy()
    for col in result.columns:
        if not col.startswith("rolling_"):
            continue
        series = result[col]
        if series.dtype != object:
            continue
        non_sentinel_mask = series.ne(MISSING)
        if _is_categorical_rolling_col(col):
            # categorical 列（jyocd mode/latest）→ sentinel を <NA> にして nullable string。
            # "06" 等の競馬場コードを数値化せず文字列カテゴリとして保持（Phase 4 categorical 制御用）。
            result[col] = series.where(non_sentinel_mask).astype("string")
        else:
            # numeric 列 → sentinel を NaN にして nullable Float64（従来通り）。
            result[col] = pd.to_numeric(series.where(non_sentinel_mask), errors="coerce").astype("Float64")
    return result


def _is_categorical_rolling_col(col: str) -> bool:
    """``rolling_{system}_{axis}_5`` 形式の列が categorical 系統（``jyocd`` 等）か判定する。

    rolling.py の ``_axes_for``: categorical 系統は ``(mode, latest, count)``・numeric 系統は
    ``(mean, latest, sd, count)``。categorical（文字列）なのは ``mode`` と categorical 系統の
    ``latest`` のみ・``count`` は出走回数（数値）で両系統とも ``Float64``。よって:

      - ``mode`` 軸 → categorical 専用（文字列） → True
      - ``mean`` / ``sd`` / ``count`` 軸 → numeric（数値） → False
      - ``latest`` 軸 → ``system`` が ``_CATEGORICAL_SYSTEMS`` かで判定
    """
    if not (col.startswith("rolling_") and col.endswith("_5")):
        return False
    core = col[len("rolling_"):-len("_5")]  # {system}_{axis}
    parts = core.split("_")
    if len(parts) < 2:
        return False
    *system_parts, axis = parts
    if axis == "mode":
        return True
    if axis in ("mean", "sd", "count"):
        return False
    # latest 軸: system が categorical 系統か（jyuni3c_jyuni4c 等 _ 含み対応）
    system = "_".join(system_parts)
    return system in _CATEGORICAL_SYSTEMS


def write_snapshot(
    df: pd.DataFrame,
    *,
    out_dir: str | Path,
    snapshot_id: str,
    created_at_fixed: str,
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

    CR-04 (03-REVIEW) / IN-03: SHA256 は **metadata 無し schema bytes** から計算する
    （データ内容のみに依存・snapshot_id/created_at 等の run 毎変動因子を除外）。その後
    schema metadata（実際の ``snapshot_id`` と ``created_at_fixed`` 引数を含む）を付与して
    Parquet bytes を書込む。これにより:

      - **byte-reproducibility**: 同一 DataFrame なら run/snapshot_id/created_at が異なって
        も SHA256 は同一（データ内容のみ依存・test_byte_reproducible_by_hash GREEN）。
      - **§12.4 監査証跡**: Parquet ファイル単体から ``feature_snapshot_id`` / ``created_at``
        を復元可能（sentinel でなく実値を埋込む・DuckDB ``read_parquet`` で参照可）。

    ``created_at_fixed`` 引数は schema metadata の ``created_at`` キーに埋め込む固定文字列
    （IN-03・旧 ``created_at`` から rename して役割を明示化）。manifest 側の ``created_at``
    フィールドは実タイムスタンプ（``datetime.now(UTC)``）で run 毎に可変。

    Parameters
    ----------
    df : pd.DataFrame
        feature matrix（``build_feature_matrix`` の出力）。空は拒否（RuntimeError）。
    out_dir : str | Path
        出力ディレクトリ（``snapshots/``）。未存在なら作成。
    snapshot_id : str
        feature snapshot identifier（§12.4・ファイル名 + schema metadata に埋込）。
    created_at_fixed : str
        schema metadata 埋込用の固定タイムスタンプ文字列（ISO8601 推奨・再現性の要・
        実タイムスタンプでない・IN-03 rename）。
    return_manifest : bool
        ``True`` なら manifest dict を戻り値とする（manifest の ``created_at`` は実タイム
        スタンプ・run 毎に可変・REVIEWS HIGH #6）。

    Returns
    -------
    str | dict
        ``return_manifest=False`` なら SHA256 hexstring（metadata 無し schema bytes 由来）。
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

    # --- rolling object 列の数値化（live-DB 整合・Parquet 直列化 fix） ---
    # rolling.py の D-13 契約は object dtype + ``__MISSING__`` sentinel で未観測/5走未満を
    # 表現するが、PyArrow は数値と文字列が混在する object 列を直列化できない
    # (ArrowTypeError: Expected bytes, got a 'float' object)。snapshot 境界で sentinel を
    # NaN に置換し nullable Float64 に統一する（rolling 内部契約は不変・Parquet 出力のみ変換）。
    # 既に数値の列は Float64 変換で等価・byte-reproducibility は維持（決定論的 cast）。
    df_sorted = _coerce_rolling_columns_for_parquet(df_sorted)

    # --- SHA256 計算 (CR-04: metadata 無し schema bytes のみ・データ内容のみ依存) ---
    # run 毎に変動し得る snapshot_id / created_at を含む schema metadata bytes を SHA256
    # 計算から除外し、純粋に DataFrame のデータ内容 + PyArrow 決定論的書込設定のみで
    # hash を決定する。これにより同一 DataFrame なら常に同一 SHA256（byte-reproducible）。
    base_schema = pa.Schema.from_pandas(df_sorted, preserve_index=False)
    base_table = pa.Table.from_pandas(df_sorted, schema=base_schema, preserve_index=False)
    sha_buf = pa.BufferOutputStream()
    pq.write_table(
        base_table,
        sha_buf,
        use_dictionary=False,
        compression="zstd",
        write_statistics=True,
        row_group_size=100_000,  # rows, not bytes (REVIEWS MEDIUM #10)
    )
    sha256 = hashlib.sha256(sha_buf.getvalue().to_pybytes()).hexdigest()

    # --- §12.4 metadata 構築 (9 keys・CR-04: sentinel でなく実値を埋込) ---
    # CR-04 (03-REVIEW) Fix 選択肢1: schema metadata に実際の snapshot_id / created_at_fixed
    # を埋め込み、Parquet ファイル単体で監査証跡を復元可能にする。SHA256 は上記の metadata
    # 無し schema で計算済みのため、ここで実値を埋め込んでも SHA256 は不変（データ内容のみ依存）。
    metadata: dict[bytes, bytes] = {
        b"dataset_version": dataset_version.encode(),
        b"feature_snapshot_id": snapshot_id.encode(),
        b"label_version": label_version.encode(),
        b"prediction_timing": prediction_timing.encode(),
        b"feature_cutoff_rule": feature_cutoff_rule.encode(),
        b"train_period": train_period.encode(),
        b"validation_period": validation_period.encode(),
        b"created_at": created_at_fixed.encode(),
        b"feature_availability_version": fa_version.encode(),
    }

    # --- schema + Table 構築（metadata 付き・書込用） ---
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

    data = buf.getvalue().to_pybytes()

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
        created_at_fixed=created_at_fixed,
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
