# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""Feature matrix 構築 + snapshot 生成エントリポイント（Phase 3 Plan 03-04 Task 3）。

readonly pool から ``build_feature_matrix`` で feature matrix を構築し、
``build_frozen_category_maps`` → ``apply_frozen_category_maps`` → ``write_snapshot``
→ ``write_manifest`` → ``persist_category_maps`` の順で不変 Parquet スナップショット +
manifest YAML + frozen category map artifact を生成する。

起動フロー（run_label_etl.py:46-127 と同一構造・masked DSN・raw_touched 検査）:
  1. ``Settings`` から ``dsn_masked`` をログ出力（生 DSN は絶対に出さない・T-03-25）
  2. ``make_pool(role='readonly')`` を構築（feature matrix 構築は read-only）
  3. ``build_feature_matrix`` で全期間 feature matrix を構築
  4. ``build_frozen_category_maps`` (train 窓 D-09 で fit) → ``apply_frozen_category_maps``
     で raw ID をコード化（REVIEWS HIGH #5 / CYCLE-2 HIGH #5）
  5. ``write_snapshot`` を **2回呼出**し SHA256 が完全一致することを assert（SC#3 byte-reproducibility）
  6. ``write_manifest`` で manifest YAML を書出（sha256 / §12.4 metadata / category_map_artifact）
  7. ``persist_category_maps`` で frozen category map を JSON（byte-reproducible・CR-04・pickle ACE 解消）で永続化

Usage::

    uv run python scripts/run_feature_build.py \\
        --snapshot-id 20260618-1a-v1 \\
        --label-version v1.0.0 \\
        --fa-version 0.2.0
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool  # noqa: E402
from src.features.builder import build_feature_matrix  # noqa: E402
from src.features.category_map_consumer import (  # noqa: E402
    apply_frozen_category_maps,
    build_frozen_category_maps,
    persist_category_maps,
)
from src.features.snapshot import write_manifest, write_snapshot  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_feature_build")

# snapshots/ 出力ディレクトリ（リポジトリルート直下・.gitignore 対象）
_SNAPSHOTS_DIR = _REPO_ROOT / "snapshots"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する。"""
    parser = argparse.ArgumentParser(
        description="Build feature matrix snapshot + manifest + frozen category map",
    )
    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="feature snapshot identifier (e.g. 20260618-1a-v1) — §12.4 metadata",
    )
    parser.add_argument(
        "--label-version",
        default="v1.0.0",
        help="label generation version (§12.4 metadata, default: v1.0.0)",
    )
    parser.add_argument(
        "--fa-version",
        default="0.2.0",
        help="feature_availability.yaml schema_version (§12.4 metadata, default: 0.2.0)",
    )
    parser.add_argument(
        "--train-period",
        default="2016-07-01/2023-12-31",
        help="train window (D-09, default: 2016-07-01/2023-12-31)",
    )
    parser.add_argument(
        "--validation-period",
        default="2024-01-01/2024-12-31",
        help="validation window (default: 2024-01-01/2024-12-31)",
    )
    parser.add_argument(
        "--created-at",
        default=None,
        help=(
            "fixed created_at string for schema metadata (ISO8601). 指定無し場合は "
            "本日 00:00:00Z の固定値を使用（run 毎に変化させない・Pitfall 3.5）。"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """feature matrix snapshot + manifest + category map を生成する。

    SC#3 byte-reproducibility を自己検証するため ``write_snapshot`` を2回呼出し、
    SHA256 が完全一致することを assert する（同一 DataFrame から同一 bytes が生成される）。
    raw DB には一切書込まない（readonly pool のみ・raw_touched=False・D-06）。
    """
    args = parse_args(argv)
    settings = Settings()

    # T-03-25: 生 DSN は絶対に出力しない（masked のみ）
    logger.info("readonly DSN: %s", settings.dsn_masked)

    # created_at 固定値: 指定無ければ本日 00:00:00Z（run 毎に変化させない・Pitfall 3.5）
    if args.created_at is not None:
        created_at_fixed = args.created_at
    else:
        today = datetime.now(UTC).date()
        created_at_fixed = f"{today.isoformat()}T00:00:00Z"

    read_pool = make_pool(settings, role="readonly")

    try:
        # --- Step 1: feature matrix 構築 (readonly pool・D-06) ---
        logger.info(
            "building feature matrix: snapshot_id=%s label_version=%s fa_version=%s",
            args.snapshot_id,
            args.label_version,
            args.fa_version,
        )
        build_result = build_feature_matrix(
            read_pool,
            snapshot_id=args.snapshot_id,
            label_version=args.label_version,
            fa_version=args.fa_version,
            train_period=tuple(args.train_period.split("/")),
            validation_period=tuple(args.validation_period.split("/")),
        )
        feature_matrix = build_result["feature_matrix"]
        assert build_result["raw_touched"] is False, (
            "raw_touched=True: build_feature_matrix が raw に書込んだ (D-06 違反)"
        )
        logger.info(
            "feature matrix: rows=%d features=%d raw_touched=False",
            len(feature_matrix),
            feature_matrix.shape[1],
        )

        # --- Step 2: frozen category maps (train 窓 D-09 で fit) ---
        # build_frozen_category_maps は feature_matrix 上の train 窓 (race_date between
        # 2016-07-01 / 2023-12-31) のみで fit する（Pitfall 3.4・test 構成リーク防止）。
        frozen_maps = build_frozen_category_maps(feature_matrix)
        cardinalities = {col: len(fm) for col, fm in frozen_maps.items()}
        logger.info(
            "category maps: jockey=%s trainers=%s sires=%s bms=%s horses=%s",
            cardinalities.get("jockey_id"),
            cardinalities.get("trainer_id"),
            cardinalities.get("sire_id"),
            cardinalities.get("bms_id"),
            cardinalities.get("horse_id"),
        )

        # --- Step 3: apply frozen maps (raw ID alias を _code 化して drop・HIGH #5) ---
        coded_matrix = apply_frozen_category_maps(feature_matrix, frozen_maps)

        # --- Step 4: write_snapshot 2回呼出 (SC#3 byte-reproducibility verify) ---
        # SHA256 は Parquet bytes のみ由来（REVIEWS HIGH #6）。同一 DataFrame から同一 bytes
        # が生成されることを2回書込で機械的に証明する。
        sha1 = write_snapshot(
            coded_matrix,
            out_dir=_SNAPSHOTS_DIR,
            snapshot_id=args.snapshot_id,
            created_at=created_at_fixed,
            label_version=args.label_version,
            fa_version=args.fa_version,
            train_period=args.train_period,
            validation_period=args.validation_period,
        )
        logger.info("snapshot write #1: sha256=%s", sha1)

        sha2 = write_snapshot(
            coded_matrix,
            out_dir=_SNAPSHOTS_DIR,
            snapshot_id=args.snapshot_id,
            created_at=created_at_fixed,
            label_version=args.label_version,
            fa_version=args.fa_version,
            train_period=args.train_period,
            validation_period=args.validation_period,
        )
        logger.info("snapshot write #2 (byte-repro verify): sha256=%s", sha2)

        assert sha1 == sha2, (
            f"byte-reproducibility 違反: write #1 sha256={sha1} != write #2 sha256={sha2} "
            "(同一 DataFrame から異なる Parquet bytes が生成された・SC#3 / Pitfall 3.5)"
        )
        logger.info("byte-reproducibility verify: PASS (SC#3・Pitfall 3.5)")

        # --- Step 5: manifest YAML 書出 (sha256 / §12.4 metadata / category_map_artifact) ---
        parquet_path = _SNAPSHOTS_DIR / f"feature_matrix_{args.snapshot_id}.parquet"
        manifest_path = _SNAPSHOTS_DIR / f"feature_matrix_{args.snapshot_id}.manifest.yaml"
        category_map_artifact = f"snapshots/category_map_{args.snapshot_id}.json"

        write_manifest(
            manifest_path,
            snapshot_id=args.snapshot_id,
            parquet_path=str(parquet_path),
            sha256=sha1,
            byte_size=parquet_path.stat().st_size,
            row_count=int(len(coded_matrix)),
            feature_count=int(coded_matrix.shape[1]),
            label_version=args.label_version,
            fa_version=args.fa_version,
            prediction_timing="1A",
            feature_cutoff_rule="race_date - 1 day",
            train_period=args.train_period,
            validation_period=args.validation_period,
            created_at_real=datetime.now(UTC),
            category_map_artifact=category_map_artifact,
            created_at_fixed=created_at_fixed,
        )
        logger.info("manifest written: %s", manifest_path)

        # --- Step 6: frozen category map artifact 永続化 (JSON・CR-04 pickle ACE 解消) ---
        category_map_path = _SNAPSHOTS_DIR / f"category_map_{args.snapshot_id}.json"
        persist_category_maps(frozen_maps, category_map_path)
        logger.info("category map artifact written: %s", category_map_path)

        logger.info(
            "feature build complete: raw_touched=False sha256=%s row_count=%d "
            "feature_count=%d category_map=%s",
            sha1,
            len(coded_matrix),
            coded_matrix.shape[1],
            category_map_artifact,
        )
        return 0
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    except MemoryError as e:
        # W-5 OOM escape hatch: 554267行 × 80-100 feature 列で MemoryError の場合は
        # chunk-based write または DuckDB postgres_scanner 経由の direct materialize に
        # 切替が必要（SUMMARY.md に escape hatch 適用を記録）。
        logger.error(
            "MemoryError (OOM): feature matrix が大きすぎる・W-5 escape hatch 要適用: %s",
            e,
        )
        return 4
    finally:
        read_pool.close()


if __name__ == "__main__":
    sys.exit(main())
