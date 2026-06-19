"""Feature availability registry loader / allowlist helpers（Phase 3 Plan 03-01）.

仕様（03-CONTEXT.md D-01/D-06/D-07 + 03-REVIEWS.md HIGH #2/#3/#4）:

  - **D-13 silent fallback 禁止:** ``load_feature_availability`` は必須キー（``cutoff_semantics``
      含む・HIGH #2）が1つでも欠損すれば ``ValueError`` で fail-fast（``fukusho_label.load_label_spec``
      / ``class_normalize.load_class_config`` パターン踏襲）。
  - **D-07 allowlist 境界:** ``BANNED_TIMINGS`` / ``ALLOWED_TIMINGS`` frozenset で timing を固定。
      ``banned_features(spec)`` が禁止 timing に該当する feature 名を返す（SC#2 fail-loud 入力）。
  - **REVIEWS HIGH #2 (cutoff semantics pinning):** ``CUTOFF_SEMANTICS`` 定数が strict
      ``<`` / JST midnight / boundary rule を文書化。YAML の ``cutoff_semantics`` ブロックと
      Parquet §12.4 metadata ``feature_cutoff_rule`` の唯一の真の源。
  - **REVIEWS HIGH #3 (出力カラム全登録検査):** ``assert_matrix_columns_registered(spec,
      output_columns)`` が registry 未登録の出力カラムを全て ``ValueError`` で reject。
      banned source カラムが allowed feature 名の alias で潜入するのを構造的に防止。
  - **REVIEWS HIGH #4 (target-obs vs history taxonomy):** ``TARGET_OBS_BANNED_COLUMNS`` /
      ``HISTORY_ALLOWED_POST_RACE_COLUMNS`` 定数が ``source_role`` 区分を定数化。
      ``sibababacd`` / ``dirtbabacd``（target_obs_banned）と ``babacd``（過去走 rolling source・
      history_allowed_post_race）を明示的に区別。両カラム集合は disjoint（Pitfall 3.6 厳守・
      ``harontimel4`` は target_obs_banned 側に分類し history SELECT にも絶対に許可しない）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("src/config/feature_availability.yaml")

# ---------------------------------------------------------------------------
# 必須キー（cutoff_semantics 含む・HIGH #2）
# ---------------------------------------------------------------------------
_REQUIRED_SPEC_KEYS = (
    "schema_version",
    "feature_schema",
    "features",
    "cutoff_semantics",
)

# ---------------------------------------------------------------------------
# REVIEWS HIGH #2: cutoff semantics 定数（strict < / JST midnight・単一不変量）
# ---------------------------------------------------------------------------
CUTOFF_SEMANTICS: dict[str, str] = {
    "comparison_operator": "strict_less_than",
    "timezone": "Asia/Tokyo",
    "cutoff_definition": (
        "feature_cutoff_datetime = pd.to_datetime(race_date) - pd.Timedelta(days=1) (JST midnight)"
    ),
    "pit_filter": "history.as_of_datetime < observation.feature_cutoff_datetime",
    "boundary_rule": (
        "a race whose as_of_datetime equals feature_cutoff_datetime midnight is "
        "EXCLUDED (strict <)"
    ),
}

# ---------------------------------------------------------------------------
# D-07: allowlist 境界（timing 集合）
# ---------------------------------------------------------------------------
BANNED_TIMINGS: frozenset[str] = frozenset({
    "race_day_morning",
    "body_weight_announced",
    "odds_snapshot_available",
    "post_race_only",
    "same_day_aggregate",
})

ALLOWED_TIMINGS: frozenset[str] = frozenset({
    "entry_confirmed",
    "post_position_confirmed",
})

# ---------------------------------------------------------------------------
# REVIEWS HIGH #4: target-obs vs history-allowed カラム taxonomy
# TARGET_OBS_BANNED_COLUMNS ∩ HISTORY_ALLOWED_POST_RACE_COLUMNS == ∅ （Pitfall 3.6 厳守・
# harontimel4 は target_obs_banned 側に分類し history SELECT にも絶対許可しない）
# ---------------------------------------------------------------------------
TARGET_OBS_BANNED_COLUMNS: frozenset[str] = frozenset({
    "kyakusitukubun",
    "bataijyu",
    "ninki",
    "odds",
    "sibababacd",
    "dirtbabacd",
    "tenkocd",
    "harontimel4",
})

HISTORY_ALLOWED_POST_RACE_COLUMNS: frozenset[str] = frozenset({
    "kakuteijyuni",
    "timediff",
    "harontimel3",
    "jyuni3c",
    "jyuni4c",
    "jyuni1c",
    "babacd",
    "datakubun",
})

# 高基数 ID カラム（category map で int32 _code 化される・Phase 4 モデルが raw ID で refit
# するのを防ぐため HIGH #5 で apply 後に drop される）
_CATEGORY_COLUMNS: frozenset[str] = frozenset({
    "jockey_id",
    "trainer_id",
    "sire_id",
    "bms_id",
    "horse_id",
})

# ---------------------------------------------------------------------------
# CYCLE-2 HIGH #5 (COPY-NOT-RENAME): 抽象 ID alias を追加する際、**元の raw ID 列**は
# 破壊的 rename されずそのまま保持される（``feature_matrix["jockey_id"] = kisyucode``
# copy・builder 参照）。これら raw ID 原列は Phase 4 が raw ID で refit する経路を**開いた
# ままにする意図的設計**（HIGH #5 contract・audit trail）。``_CATEGORY_COLUMNS`` は抽象
# alias のみ drop し raw 原列は保持。よってこれら raw 原列は出力カラム検査の allowlist に
# 明示的に含まれる必要がある（BUG B fix）。banned source（sibababacd/dirtbabacd/odds 等）
# はここに絶対に含めない・含めると HIGH #3 fail-loud が無意味化する。
_RAW_ID_KEPT_COLUMNS: frozenset[str] = frozenset({
    "kisyucode",                  # jockey_id の原列
    "chokyosicode",               # trainer_id の原列
    "ketto3infohansyokunum1",     # sire_id の原列
    "ketto3infohansyokunum2",     # bms_id の原列
    "kettonum",                   # horse_id の原列（canonical key でもある・reserved にも含まれる）
})

# rolling 8系統（Plan 03-03 rolling.py::_ROLLING_SYSTEMS と同一・二重定義の危険を下げるため
# import ではなく再定義・availability.py から features.rolling への循環依存を回避）
_ROLLING_SYSTEMS_FOR_RESERVED: tuple[str, ...] = (
    "kakuteijyuni",
    "timediff",
    "harontimel3",
    "jyuni3c_jyuni4c",
    "kyori",
    "babacd",
    "jyocd",
    "days_since_prev",
)

# ---------------------------------------------------------------------------
# feature でない管理 / key / audit カラム（registry 対象外・明示的に許可・HIGH #3）
# BLOCKER #1: rolling_<system>_count_5 計8列を具体名で展開して登録
# ---------------------------------------------------------------------------
_RESERVED_NON_FEATURE_COLUMNS: frozenset[str] = frozenset({
    "race_nkey",
    "kettonum",
    "year",
    "jyocd",
    "kaiji",
    "nichiji",
    "racenum",
    "race_date",
    "race_start_datetime",
    "as_of_datetime",
    "feature_cutoff_datetime",
    "feature_snapshot_id",
    "feature_availability_version",
    "label_generation_version",
    "prediction_timing",
}) | {f"rolling_{sys}_count_5" for sys in _ROLLING_SYSTEMS_FOR_RESERVED}


# ---------------------------------------------------------------------------
# loader 本体（fukusho_label.load_label_spec / class_normalize.load_class_config パターン）
# ---------------------------------------------------------------------------
def load_feature_availability(path: str | Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """``feature_availability.yaml`` を読込 dict で返す（D-13 silent fallback 禁止）。

    必須キー（``_REQUIRED_SPEC_KEYS``・``cutoff_semantics`` 含む・HIGH #2）が1つでも
    欠損した場合は ``ValueError`` で fail-fast する。``cutoff_semantics`` ブロックの
    必須サブキー（``comparison_operator`` / ``timezone``）も検査する。
    """
    with Path(path).open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(
            f"feature_availability.yaml は dict でなければなりません: {type(spec)!r}"
        )
    missing = [k for k in _REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(
            f"feature_availability.yaml に必須キーが欠損: {missing} (D-13 silent fallback 禁止)"
        )
    # cutoff_semantics ブロックの中身（HIGH #2）
    cutoff = spec.get("cutoff_semantics")
    if not isinstance(cutoff, dict):
        raise ValueError(
            "feature_availability.yaml の cutoff_semantics は dict でなければなりません (HIGH #2)"
        )
    for required_cutoff_key in ("comparison_operator", "timezone"):
        if required_cutoff_key not in cutoff:
            raise ValueError(
                f"cutoff_semantics に必須キーが欠損: {required_cutoff_key} (HIGH #2)"
            )
    return spec


# ---------------------------------------------------------------------------
# allowlist 検査ヘルパー（SC#2 fail-loud・D-07）
# ---------------------------------------------------------------------------
def banned_features(spec: dict[str, Any]) -> list[str]:
    """SC#2 fail-loud 検査用: 禁止 timing に該当する feature 名を返す（0件期待）。

    ``available_from_timing`` が ``BANNED_TIMINGS`` に含まれる feature の名前を
    出現順で返す。空リストであることが正常。
    """
    return [
        f["feature_name"]
        for f in spec.get("features", [])
        if f.get("available_from_timing") in BANNED_TIMINGS
    ]


def assert_all_entries_allowed(spec: dict[str, Any]) -> None:
    """全 feature の timing が ``ALLOWED_TIMINGS`` に属することを検査（防御層）。

    banned でなくても未知 timing（typo 等）も検出する。違反時 ``ValueError``。
    """
    offenders: list[tuple[str, str]] = []
    for f in spec.get("features", []):
        timing = f.get("available_from_timing")
        name = f.get("feature_name", "<unknown>")
        if timing not in ALLOWED_TIMINGS:
            offenders.append((name, repr(timing)))
    if offenders:
        raise ValueError(
            "feature_availability.yaml に許可されていない available_from_timing を持つ "
            f"feature があります: {offenders} (D-07 allowlist: {sorted(ALLOWED_TIMINGS)})"
        )


# ---------------------------------------------------------------------------
# REVIEWS HIGH #3: 出力カラム全登録検査
# ---------------------------------------------------------------------------
def registered_feature_columns(spec: dict[str, Any]) -> set[str]:
    """registry 登録済み ``feature_name`` の set を返す（HIGH #3 出力カラム検査入力）。"""
    return {f["feature_name"] for f in spec.get("features", []) if "feature_name" in f}


def assert_matrix_columns_registered(
    spec: dict[str, Any],
    output_columns: list[str] | set[str],
    *,
    reserved: frozenset[str] = _RESERVED_NON_FEATURE_COLUMNS,
    raw_id_kept: frozenset[str] = _RAW_ID_KEPT_COLUMNS,
) -> None:
    """出力 feature-matrix カラムが全て registry / reserved / category_map(_code) / kept-raw-ID
    由来であることを検査。

    1件でも未登録（registry に無い・reserved でない・``_code`` suffix で category map 由来でない・
    ``_RAW_ID_KEPT_COLUMNS`` でない）出力カラムがあれば ``ValueError`` で fail-loud（HIGH #3）。
    banned source カラムが allowed feature 名の alias で潜入するのを構造的に防止する。

    **CYCLE-2 HIGH #5 (COPY-NOT-RENAME)**: builder は抽象 alias を copy で追加し raw ID 原列
    （kisyucode/chokyosicode/ketto3infohansyokunum1/ketto3infohansyokunum2）を保持する。これら
    raw 原列は意図的に保持されるため ``raw_id_kept`` で明示的に許可する（BUG B fix）。ただし
    ``TARGET_OBS_BANNED_COLUMNS``（sibababacd/dirtbabacd/odds/ninki/...）は絶対に許可しない。
    """
    allowed = registered_feature_columns(spec) | set(reserved) | set(raw_id_kept)
    # category map 由来の <col>_code 形式を許可（HIGH #5: apply 後は raw ID alias は drop されるが
    # _code suffix 列は残る・Phase 4 モデルが消費）
    allowed |= {f"{c}_code" for c in _CATEGORY_COLUMNS}
    # banned source カラムが raw_id_kept / reserved 経由で潜入していないか二重防御
    banned_leak = TARGET_OBS_BANNED_COLUMNS & allowed
    assert not banned_leak, (
        f"banned source カラムが allowlist に混入: {banned_leak} (HIGH #3 fail-loud 無意味化・違反)"
    )
    for col in output_columns:
        if col not in allowed:
            raise ValueError(
                f"unregistered feature-matrix column: {col}; "
                "allowed = registry features + reserved keys + <col>_code from frozen category map "
                "+ COPY-NOT-RENAME kept raw-ID columns"
            )
