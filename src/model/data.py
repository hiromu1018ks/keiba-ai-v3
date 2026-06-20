"""Phase 4 model data layer: stamped Parquet 読込 + label join + allowlist + 3way split.

成功基準#1 (SC#1) / §13.4 / D-01 / D-02b / D-07 / MODL-01 を実装する service 層。

**設計の核心（review HIGH#9: 契約混乱の解消・fake-green 防止）:**

データ API を明示的に5関数に分離する。各関数は単一責任を持ち、unit test は各純粋関数を
直接叩く（DB 依存をテストから排除し、合成 label DataFrame を inject 可能にする）:

  1. ``load_feature_matrix()``      — Parquet のみ読込（live DB 引数を持たない・SC#1 聖域）
  2. ``load_labels(readonly_cur)``  — DB readonly 読込（懸念分離・明示的 DB 依存）
  3. ``build_training_frame(feature_df, label_df)`` — 純粋 join（DB 非依存・テスト容易）
  4. ``make_X_y(frame)``            — 厳密 feature 選択（X.columns == FEATURE_COLUMNS 完全一致 assert）
  5. ``prepare_model_matrix(...)``  — 上記を統合する thin orchestrator（実ロジック持たず）

**FEATURE_COLUMNS allowlist（review HIGH#9 / T-04-12c）:**

``FEATURE_COLUMNS`` は ``feature_availability.yaml`` registry から導出する明示的 allowlist。
registry 登録 feature から metadata / raw-ID / label 系列を差し引き、決定的順序で固定する。
``make_X_y`` は ``X.columns == FEATURE_COLUMNS`` を**完全一致（集合 + 順序）**で assert する。
これにより metadata/label/raw-ID 列が X に混入し ``assert_matrix_columns_registered`` が
誤適用される silent leak を構造的に防止する。

**正準 race_key（review HIGH#9）:**

race 識別キーは ``race_key = (year,jyocd,kaiji,nichiji,racenum)`` 文字列表に統一する。
ad-hoc な ``race_nkey`` フォールバックは廃止（``race_nkey`` が Parquet に存在しても
disjoint 検査には使わない・docstring に「参考専用」と注記）。

**3way split 完全時系列条件（review MEDIUM#5）:**

``split_3way`` は D-02b 推奨案（train 2016-07..2023 / calib 2024-H1 / test 2024-H2 /
2025+ は Phase 5 BT 温存）の暦年 mask で分離し、完全条件
``train_max < calib_min < calib_max < test_min <= test_max`` を ``raise ValueError`` で保証
（``python -O`` で生存）。3way の ``race_key`` 集合が pairwise disjoint であることも
``raise ValueError`` で保証する。

**manifest 完全 SHA256 検証（review MEDIUM#6）:**

``verify_snapshot_sha256`` は manifest の**完全 SHA256**（64 hex・略記でない）と
``hashlib.sha256(file bytes)`` を ``secrets.compare_digest`` で比較する。
``byte_reproducible_scope`` が ``parquet_data_only_metadata_excluded``（Phase 3 D-08 と一致）
であることも assert する（fail-loud）。

参照: 04-RESEARCH.md D-01/D-02b/D-03/D-05/D-07 / 04-PATTERNS.md data.py セクション /
      Shared Pattern 2 (raise ValueError guard) / src/features/availability.py /
      src/utils/group_split.py.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow.parquet as pq
import yaml

from src.features.availability import (
    _CATEGORY_COLUMNS,
    _RAW_ID_KEPT_COLUMNS,
    _RESERVED_NON_FEATURE_COLUMNS,
    assert_matrix_columns_registered,
    banned_features,
    load_feature_availability,
    registered_feature_columns,
)

if TYPE_CHECKING:
    from psycopg import Cursor

# ---------------------------------------------------------------------------
# 定数（D-01 正 snapshot・review MEDIUM#6 完全 hash は manifest から読込）
# ---------------------------------------------------------------------------
SNAPSHOT_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.parquet"
SNAPSHOT_MANIFEST_PATH = "snapshots/feature_matrix_20260620-1a-postreview-v2.manifest.yaml"
EXPECTED_FEATURE_COUNT = 62  # manifest feature_count（Parquet 全列数・review HIGH#9 検証用）

# label.fukusho_label と同一 PK 先頭5カラム（fukusho_label.py:524 _RACE_KEY と同一）
LABEL_PK_COLUMNS = ["year", "jyocd", "kaiji", "nichiji", "racenum"]

# raw ID 原列（モデル入力から除外・Pitfall 4 / T-04-07）。
# availability._RAW_ID_KEPT_COLUMNS は kettonum も含むが kettonum は canonical key のため
# モデル入力除外対象は kisyucode/chokyosicode/ketto3infohansyokunum1/2 の4列のみ。
RAW_ID_COLUMNS: frozenset[str] = frozenset({
    "kisyucode",
    "chokyosicode",
    "ketto3infohansyokunum1",
    "ketto3infohansyokunum2",
})

# label 系列列名（build_training_frame で feature 側に付与・make_X_y で FEATURE から除外）
LABEL_COLUMNS: frozenset[str] = frozenset({
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
})

# metadata / key / provenance 列（FEATURE から除外・review HIGH#9: metadata/label/raw-ID 混入防止）
# 注意: registry 登録 feature (umaban/wakuban/barei/sexcd/futan/class_code_normalized) は
# 本集合に含めない（feature として扱う）。META_KEY_COLUMNS は registry 非登録の純粋 meta/key 列のみ。
META_KEY_COLUMNS: frozenset[str] = frozenset({
    "race_nkey",  # 参考専用・disjoint 検査には使わない（review HIGH#9）
    "as_of_datetime",
    "feature_cutoff_datetime",
    "feature_snapshot_id",
    "feature_availability_version",
    "label_generation_version",  # snapshot 側の stamp（label 側の同名列と同名・meta 扱い）
    "prediction_timing",
}) | _RESERVED_NON_FEATURE_COLUMNS  # race_nkey/kettonum/year/jyocd/kaiji/nichiji/racenum/
#   race_date/race_start_datetime/obs_id(削除) + rolling_*_count_5 8列
# (umaban/wakuban は _RESERVED_NON_FEATURE_COLUMNS に含まれないため feature 扱い)

# ---------------------------------------------------------------------------
# FEATURE_COLUMNS — review HIGH#9 明示的 allowlist（registry derived）
# ---------------------------------------------------------------------------
# registry 登録 feature 集合から、本 SNAPSHOT に実在しない抽象 alias（jockey_id 等・apply 段階で
# drop 済み・_code suffix 列のみ残存）を除いた上で、metadata / raw-ID / label 系列を差し引く。
# 残る列がモデル入力 feature。registry から導出することで「banned feature が alias で潜入」
# 「metadata/raw-ID/label 列が X に混入し assert_matrix_columns_registered が誤適用」を
# 構造的に防止する（review HIGH#9 / T-04-12c）。


def _derive_feature_columns() -> list[str]:
    """registry から FEATURE_COLUMNS allowlist を導出する（review HIGH#9）。

    手順:
      1. ``load_feature_availability()`` で registry 読込
      2. ``registered_feature_columns(spec)`` で登録 feature 集合を取得
      3. SNAPSHOT Parquet の実際の列集合との積を取る（実在する feature のみ）
      4. META_KEY_COLUMNS ∪ RAW_ID_COLUMNS ∪ LABEL_COLUMNS を差し引く
      5. category map 由来の ``<col>_code`` 列を追加（_CATEGORY_COLUMNS に対応する5列）
      6. 決定的順序で sort して返す（byte-reproducible な allowlist）
    """
    spec = load_feature_availability()
    reg = registered_feature_columns(spec)
    parq_cols = set(pq.read_table(SNAPSHOT_PATH).schema.names)
    # registry 登録 feature のうち SNAPSHOT に実在するもの
    reg_present = reg & parq_cols
    # category map 由来 _code 列（SNAPSHOT に実在するもの）
    code_cols = {f"{c}_code" for c in _CATEGORY_COLUMNS} & parq_cols
    # 候補 = (registry 実在 feature) ∪ (_code 列)
    candidates = reg_present | code_cols
    # 除外 = META_KEY ∪ RAW_ID ∪ LABEL（class_code_normalized は registry 登録だが
    # META_KEY_COLUMNS に含め feature から除外: 正規化枠でありモデル入力としない本 PLAN の判断）
    excluded = META_KEY_COLUMNS | RAW_ID_COLUMNS | LABEL_COLUMNS
    feature_set = candidates - excluded
    return sorted(feature_set)


FEATURE_COLUMNS: list[str] = _derive_feature_columns()


# ---------------------------------------------------------------------------
# 正準 race_key builder（review HIGH#9）
# ---------------------------------------------------------------------------
def make_race_key(df: pd.DataFrame) -> pd.Series:
    """正準 race_key = (year,jyocd,kaiji,nichiji,racenum) の ``-`` 結合文字列を返す。

    review HIGH#9: ad-hoc な ``race_nkey`` フォールバックを廃止し、正準 race_key で
    disjoint 検査を実施する。``race_nkey`` が SNAPSHOT に存在しても参考専用（本関数は
    それを使わない）。

    全カラムを ``astype(str)`` で文字列化してから結合する（int/varchar 混在の PK で
    merge key 型不一致を防ぐ・fukusho_label.py:641-644 パターン）。
    """
    return (
        df["year"].astype(str)
        + "-"
        + df["jyocd"].astype(str)
        + "-"
        + df["kaiji"].astype(str)
        + "-"
        + df["nichiji"].astype(str)
        + "-"
        + df["racenum"].astype(str)
    )


# ---------------------------------------------------------------------------
# 1. load_feature_matrix — SC#1: stamped Parquet のみ（live DB 引数を持たない）
# ---------------------------------------------------------------------------
def load_feature_matrix() -> pd.DataFrame:
    """SNAPSHOT_PATH の stamped Parquet のみを読込し DataFrame で返す（SC#1 聖域）。

    **live DB 引数を持たない**（シグネチャ arity 0）。feature を live DB から再計算する
    経路は構造的に存在しない（T-04-06 Information Disclosure mitigate）。

    戻り値に以下を付与する:
      - ``race_date`` を ``pd.to_datetime`` 化（時系列分割・calibrator の strict-later 検証用）
      - ``race_key`` 列（``make_race_key`` で導出した正準キー・disjoint 検査で使用）
      - ``feature_snapshot_id`` 列はそのまま保持（provenance 用）

    末尾で ``verify_snapshot_sha256`` を呼び、manifest の完全 SHA256 と hash scope を
    検証する（review MEDIUM#6）。
    """
    df = pq.read_table(SNAPSHOT_PATH).to_pandas()
    df["race_date"] = pd.to_datetime(df["race_date"])
    df["race_key"] = make_race_key(df)
    verify_snapshot_sha256()
    return df


def verify_snapshot_sha256() -> None:
    """SNAPSHOT manifest の完全 SHA256 と hash scope を検証する（review MEDIUM#6）。

    - manifest の ``sha256`` が 64 hex（完全 hash・略記でない）であることを assert
    - manifest の ``byte_reproducible_scope`` が ``parquet_data_only_metadata_excluded``
      （Phase 3 D-08 と一致）であることを assert
    - **``hashlib.sha256`` で再計算した hash が manifest の完全 hash と
      ``secrets.compare_digest`` で一致することを検証（fail-loud・``ValueError``）**

    **hash 計算方式（``byte_reproducible_scope=parquet_data_only_metadata_excluded`` の意味）:**

    生ファイル bytes の hash では**ない**。Phase 3 ``snapshot.write_snapshot``
    （src/features/snapshot.py:221-236）と同一の手順で再計算する:
      1. SNAPSHOT Parquet を読込（metadata 付き）
      2. ``pa.Schema.from_pandas(df, preserve_index=False)`` で metadata 無し schema を構築
         → ``base_table`` を構築（schema metadata に snapshot_id/created_at 等の run 毎可変
         値が入らない・データ内容のみ依存）
      3. 決定論的書込設定（``use_dictionary=False, compression="zstd",
         write_statistics=True, row_group_size=100_000``）で BufferOutputStream に書込
      4. その bytes の SHA256 を計算 → manifest ``sha256`` と ``secrets.compare_digest`` で比較

    これにより run 毎に変動する schema metadata を除外し、純粋に DataFrame データ内容 +
    PyArrow 決定論的書込設定のみで hash を決定する（byte-reproducible・Phase 3 HIGH #6 契約）。
    """
    with Path(SNAPSHOT_MANIFEST_PATH).open(encoding="utf-8") as f:
        manifest: dict[str, Any] = yaml.safe_load(f)

    expected_sha = manifest.get("sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError(
            f"manifest sha256 は完全 hash (64 hex) でなければなりません (review MEDIUM#6): "
            f"got={expected_sha!r}"
        )
    scope = manifest.get("byte_reproducible_scope")
    if scope != "parquet_data_only_metadata_excluded":
        raise ValueError(
            "manifest byte_reproducible_scope が Phase 3 D-08 と不一致 (review MEDIUM#6): "
            f"got={scope!r} expected='parquet_data_only_metadata_excluded'"
        )

    # Phase 3 snapshot.write_snapshot と同一の手順で hash 再計算（metadata 除外）
    import pyarrow as pa

    df = pq.read_table(SNAPSHOT_PATH).to_pandas()
    base_schema = pa.Schema.from_pandas(df, preserve_index=False)
    base_table = pa.Table.from_pandas(df, schema=base_schema, preserve_index=False)
    sha_buf = pa.BufferOutputStream()
    pq.write_table(
        base_table,
        sha_buf,
        use_dictionary=False,
        compression="zstd",
        write_statistics=True,
        row_group_size=100_000,
    )
    actual_sha = hashlib.sha256(sha_buf.getvalue().to_pybytes()).hexdigest()
    if not secrets.compare_digest(actual_sha, expected_sha):
        raise ValueError(
            "SNAPSHOT SHA256 不一致 (review MEDIUM#6 / §19.1 再現性聖域): "
            f"expected={expected_sha} actual={actual_sha}"
        )


# ---------------------------------------------------------------------------
# 2. load_labels — DB readonly 読込（review HIGH#9: 懸念分離）
# ---------------------------------------------------------------------------
def load_labels(readonly_cur: Cursor) -> pd.DataFrame:
    """``label.fukusho_label`` から label + 補助列を SELECT して DataFrame で返す。

    DB readonly cursor を明示的に取る（``load_feature_matrix`` は DB 引数を持たない・
    懸念分離）。戻り値は label DataFrame のみ（feature との join は
    ``build_training_frame`` で別途行う）。

    BL-1 用に ``sales_start_entry_count`` / ``fukusho_payout_places`` も取得する
    （PATTERNS baseline.py セクション）。

    readonly ロールの search_path は ``raw,public`` で ``label`` を含まないため、
    ``label.fukusho_label`` と schema 修飾する。
    """
    query = """
        SELECT
            year, jyocd, kaiji, nichiji, racenum, umaban, kettonum,
            race_date,
            fukusho_hit_validated,
            fukusho_hit_raw,
            is_model_eligible,
            label_validation_status,
            is_fukusho_sale_available,
            fukusho_payout_places,
            sales_start_entry_count,
            final_starter_count,
            sales_start_entry_count_source,
            sales_start_entry_count_confidence,
            ineligibility_reason,
            is_scratch_cancel,
            is_race_excluded,
            is_dead_loss,
            is_race_cancelled,
            is_dead_heat,
            label_generation_version
        FROM label.fukusho_label
    """
    readonly_cur.execute(query)
    cols = [d.name for d in readonly_cur.description]
    rows = readonly_cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# 3. build_training_frame — 純粋 join（DB 非依存・テスト容易）
# ---------------------------------------------------------------------------
def build_training_frame(
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame,
) -> pd.DataFrame:
    """feature_df と label_df を PK で left merge し訓練 frame を返す（純粋関数）。

    merge キー = ``_RACE_KEY + umaban + kettonum``（label.fukusho_label と同一7カラム PK）。
    merge 前に merge キーを ``astype(str)`` で両側型整列する（fukusho_label.py:641-644
    パターン・int/varchar 混在の silent 0 行 merge 防止）。

    silent NaN 禁止: label が無い行（feature 側にのみ存在）がある場合は ``ValueError``
    （fail-loud・§19.1 聖域）。``filter_eligible`` を内部呼出し
    ``is_model_eligible == True`` かつ ``label_validation_status in {'ok','computed'}``
    の行のみ残す。

    DB 引数を持たない（テスト容易性・fake-green 回避・review HIGH#9）。
    """
    merge_keys = ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"]
    f = feature_df.copy()
    l = label_df.copy()
    for k in merge_keys:
        if k in f.columns:
            f[k] = f[k].astype(str)
        if k in l.columns:
            l[k] = l[k].astype(str)

    n_before = len(f)
    merged = f.merge(l, on=merge_keys, how="left", suffixes=("", "_label"))
    # label 必須列が NaN の行 = label 側に存在しない = silent leak の温床
    if merged["fukusho_hit_validated"].isna().any():
        n_missing = int(merged["fukusho_hit_validated"].isna().sum())
        raise ValueError(
            f"build_training_frame: feature 側に label が無い行が {n_missing} 件存在 "
            f"(silent NaN 禁止・fail-loud・§19.1 聖域)"
        )
    return filter_eligible(merged)


def filter_eligible(frame: pd.DataFrame) -> pd.DataFrame:
    """``is_model_eligible == True`` かつ ``label_validation_status in {'ok','computed'}``
    の行のみ残す（label_spec.yaml / D-04）。"""
    mask = frame["is_model_eligible"].astype(bool) & (
        frame["label_validation_status"].astype(str).isin({"ok", "computed"})
    )
    out = frame[mask].copy()
    if len(out) == 0:
        raise ValueError(
            "filter_eligible: 全行が is_model_eligible/label_validation_status で除外された "
            "(入力 frame が空でない場合・data 契約違反の可能性)"
        )
    return out


# ---------------------------------------------------------------------------
# 4. make_X_y — 厳密 feature 選択（review HIGH#9: X.columns == FEATURE_COLUMNS）
# ---------------------------------------------------------------------------
def make_X_y(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """frame から厳密に FEATURE_COLUMNS のみを X として抽出し (X, y) を返す。

    **review HIGH#9 / T-04-12c**: ``X.columns == FEATURE_COLUMNS`` を完全一致（集合 + 順序）
    で assert する。metadata / raw-ID / label 列の混入を構造的に防止する。

    併せて ``load_feature_availability`` で spec を読み、``assert_matrix_columns_registered``
    を呼び FEATURE_COLUMNS が registry 登録済み（+ reserved/_code/raw-id）であることを
    二重検査する（SC#1・banned feature 混入防止）。``banned_features(spec)`` が空でなければ
    ``ValueError``。

    y = ``frame["fukusho_hit_validated"].astype(int)``。
    """
    spec = load_feature_availability()
    # FEATURE_COLUMNS が registry / reserved / _code / raw-id 由来であることの二重検査
    assert_matrix_columns_registered(spec, FEATURE_COLUMNS)
    banned = banned_features(spec)
    if banned:
        raise ValueError(
            f"banned features が混入 (D-07/§13.4 odds-free allowlist 違反): {banned}"
        )

    X = frame[FEATURE_COLUMNS].copy()
    # 完全一致（集合 + 順序）assert・review HIGH#9
    if list(X.columns) != FEATURE_COLUMNS:
        raise ValueError(
            "make_X_y: X.columns が FEATURE_COLUMNS と完全一致しない (review HIGH#9): "
            f"X.columns={list(X.columns)} FEATURE_COLUMNS={FEATURE_COLUMNS}"
        )
    y = frame["fukusho_hit_validated"].astype(int)
    return X, y


# ---------------------------------------------------------------------------
# 5. prepare_model_matrix — thin orchestrator（review HIGH#9）
# ---------------------------------------------------------------------------
def prepare_model_matrix(
    feature_df_or_frame: pd.DataFrame,
    *,
    readonly_cur: Cursor | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """``load_feature_matrix`` / ``load_labels`` / ``build_training_frame`` / ``make_X_y``
    を統合する thin orchestrator（review HIGH#9）。

    本関数は実ロジックを持たない。各純粋関数を順に呼出すのみ:

      (a) ``feature_df_or_frame`` が未 join の feature matrix（``fukusho_hit_validated``
          列を持たない）場合: ``load_labels(readonly_cur)`` で label を取得し
          ``build_training_frame`` で join してから ``make_X_y`` に渡す。
      (b) ``feature_df_or_frame`` が既に join 済み frame（``fukusho_hit_validated`` 列を持つ）
          場合: そのまま ``make_X_y`` に渡す。

    戻り値の ``X.columns == FEATURE_COLUMNS``（厳密）。
    """
    if "fukusho_hit_validated" in feature_df_or_frame.columns:
        frame = feature_df_or_frame
    else:
        if readonly_cur is None:
            raise ValueError(
                "prepare_model_matrix: 未 join の feature matrix には readonly_cur が必須 "
                "(review HIGH#9: DB 依存を明示)"
            )
        label_df = load_labels(readonly_cur)
        frame = build_training_frame(feature_df_or_frame, label_df)
    return make_X_y(frame)


# ---------------------------------------------------------------------------
# split_3way — review MEDIUM#5 完全時系列条件 + 正準 race_key disjoint
# ---------------------------------------------------------------------------
def split_3way(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """D-02b 推奨案で frame を train/calib/test/holdout_2025_plus に分割する。

    区間:
      - train:             race_date in [2016-07-01, 2023-12-31]
      - calib:             race_date in [2024-01-01, 2024-06-30]
      - test:              race_date in [2024-07-01, 2024-12-31]
      - holdout_2025_plus: race_date >= 2025-01-01（Phase 5 BT 温存・学習/評価に使わない）

    **完全時系列条件（review MEDIUM#5）** を ``raise ValueError`` で保証:
        ``train_max < calib_min < calib_max < test_min <= test_max``
    （``python -O`` で生存・``assert`` でない）。

    **正準 race_key pairwise disjoint（review HIGH#9）** を ``raise ValueError`` で保証:
    train/calib/test の ``race_key`` 集合は pairwise disjoint（``race_nkey`` でなく）。

    各戻り値 DataFrame は ``sort_values(["race_start_datetime","race_key"])`` 済み
    （CatBoost ``has_time=True`` 前提の入力整列・trainer.py が再 sort するが入力も整列済みを保証）。
    """
    train = frame[frame["race_date"].between("2016-07-01", "2023-12-31")].copy()
    calib = frame[frame["race_date"].between("2024-01-01", "2024-06-30")].copy()
    test = frame[frame["race_date"].between("2024-07-01", "2024-12-31")].copy()
    holdout = frame[frame["race_date"] >= "2025-01-01"].copy()

    for name, df_part in (
        ("train", train),
        ("calib", calib),
        ("test", test),
        ("holdout_2025_plus", holdout),
    ):
        if len(df_part) == 0:
            raise ValueError(
                f"split_3way: {name} 区間が空 (frame の race_date 分布異常の可能性)"
            )
        if "race_start_datetime" in df_part.columns:
            df_part.sort_values(
                ["race_start_datetime", "race_key"], kind="mergesort", inplace=True
            )
        else:
            df_part.sort_values(["race_key"], kind="mergesort", inplace=True)
        df_part.reset_index(drop=True, inplace=True)

    # --- 完全時系列条件 guard（review MEDIUM#5: raise ValueError・python -O で生存） ---
    train_max = train["race_date"].max()
    calib_min = calib["race_date"].min()
    calib_max = calib["race_date"].max()
    test_min = test["race_date"].min()
    test_max = test["race_date"].max()
    if not (train_max < calib_min < calib_max < test_min <= test_max):
        raise ValueError(
            "split_3way: 完全時系列条件違反 (review MEDIUM#5): "
            f"train_max={train_max} calib_min={calib_min} calib_max={calib_max} "
            f"test_min={test_min} test_max={test_max} "
            "(期待: train_max < calib_min < calib_max < test_min <= test_max)"
        )

    # --- 正準 race_key pairwise disjoint guard（review HIGH#9: raise ValueError） ---
    train_keys = set(train["race_key"])
    calib_keys = set(calib["race_key"])
    test_keys = set(test["race_key"])
    for a_name, a_keys, b_name, b_keys in (
        ("train", train_keys, "calib", calib_keys),
        ("train", train_keys, "test", test_keys),
        ("calib", calib_keys, "test", test_keys),
    ):
        overlap = a_keys & b_keys
        if overlap:
            raise ValueError(
                f"split_3way: {a_name} と {b_name} の正準 race_key が disjoint でない "
                f"(review HIGH#9): overlap_count={len(overlap)} sample={sorted(overlap)[:3]}"
            )

    return {
        "train": train,
        "calib": calib,
        "test": test,
        "holdout_2025_plus": holdout,
    }


# ---------------------------------------------------------------------------
# load_frozen_maps — trainer が消費する frozen category map helper
# ---------------------------------------------------------------------------
def load_frozen_maps() -> dict[str, Any]:
    """``snapshots/category_map_20260620-1a-postreview-v2.json`` を読込む helper。

    本 task では map 自体の適用は行わない（SNAPSHOT 内に既に ``_code`` int32 化済み・
    PATTERNS data.py 注意差分）。trainer.py が本 helper を消費して val/test の code 化に
    使用する。再 fit 禁止（``load_category_maps`` は frozen map を読むのみ）。
    """
    from src.features.category_map_consumer import load_category_maps

    return load_category_maps("snapshots/category_map_20260620-1a-postreview-v2.json")
