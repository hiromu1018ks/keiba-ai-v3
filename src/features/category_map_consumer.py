"""SC#4 frozen category map consumer + REVIEWS HIGH #5 raw ID drop (Plan 03-04).

feature matrix 上で **train 窓（D-09: 2016H2-2023）でのみ** ``fit_category_map`` を呼び出し、
val/test には ``apply_category_map`` で **再 fit せず** 適用する。CLAUDE.md §14.3 / §14.5 の
leak-safe categorical handling を feature matrix 構築 end-to-end で担保する。

設計要点:
  - **train 窓 mask** (Pitfall 3.4 / D-09): ``build_frozen_category_maps`` は
    ``feature_matrix["race_date"].between("2016-07-01", "2023-12-31")`` で train 窓行のみを
    ``fit_category_map`` に渡す。val/test 行を fit に渡すと test 構成リーク。
  - **__UNSEEN__ sentinel** (§14.3): train 窓に現れなかった ID は ``apply_category_map`` が
    ``code[UNSEEN]`` にフォールバック。
  - **非負 int32** (§14.3 LightGBM): pandas ``category`` dtype が NaN を code ``-1`` にする
    ハザードを回避するため、戻り値は ``.astype("int32")`` で非負を保証。
  - **欠損理由区別** (§14.5): ``__MISSING__`` と ``__UNSEEN__`` は異なるコード。
  - **REVIEWS HIGH #5 / CYCLE-2 HIGH #5 raw ID drop**: ``apply_frozen_category_maps`` は
    coding 完了後に ``drop(columns=list(_CATEGORY_COLUMNS))`` で raw ID 文字列 alias 列を破棄。
    ``_CATEGORY_COLUMNS`` は抽象名5要素のみで ``kettonum`` を**含まない**（``kettonum`` は
    canonical key / snapshot sort key / rolling obs_id の要素・drop 対象外）。builder は
    copy-not-rename で ``horse_id`` alias を ``kettonum`` copy として追加済み・本モジュールは
    alias のみ drop し ``kettonum`` を保持する。

API (test contract):
  - ``fit_category_map(df, column)`` -> ``FrozenCategoryMap``
      dict access ``m["__UNSEEN__"]`` と attribute access ``m.codes[UNSEEN]`` の両方をサポート。
  - ``apply_category_map(df, column, frozen_map)`` -> ``df`` with ``f"{column}_code"`` (int32).
  - ``build_frozen_category_maps(feature_matrix)`` -> ``dict[str, FrozenCategoryMap]``.
  - ``apply_frozen_category_maps(feature_matrix, frozen_maps)`` -> ``df`` (raw IDs dropped).
  - ``persist_category_maps(maps, artifact_path)`` / ``load_category_maps(artifact_path)``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import joblib
import pandas as pd

from src.utils.category_map import apply_category_map as _apply_one
from src.utils.category_map import fit_category_map as _fit_one

# ---------------------------------------------------------------------------
# frozen category map 対象の高基数 ID 列（抽象名・D-02 horse_id 含む）
# CYCLE-2 HIGH #5: ``kettonum`` は含まない（canonical key / snapshot sort key / rolling
# obs_id の要素・drop 対象外）。builder が copy-not-rename で ``horse_id`` alias を追加済み。
# ---------------------------------------------------------------------------
_CATEGORY_COLUMNS = ("jockey_id", "trainer_id", "sire_id", "bms_id", "horse_id")

# train 窓（D-09・frozen category map fit 範囲）
_TRAIN_WINDOW = ("2016-07-01", "2023-12-31")


class FrozenCategoryMap:
    """``fit_category_map`` 戻り値の stable wrapper。

    ``src.utils.category_map.fit_category_map`` は ``dict[str, int]`` を返すが、本モジュールは
    test contract として **dict-style** access (``m["__UNSEEN__"]``) と **attribute-style**
    access (``m.codes[UNSEEN]``) の両方をサポートする必要がある。``FrozenCategoryMap`` は
    その両面を持つ軽量 wrapper。joblib 永続化も安全（``__getstate__`` / ``__setstate__`` は
    dict + codes を其のまま保存）。

    Parameters
    ----------
    code_map : dict[str, int]
        ``src.utils.category_map.fit_category_map`` の戻り値（``__UNSEEN__`` / ``__MISSING__``
        sentinel 含む・非負 int・両 sentinel は別コード）。
    """

    def __init__(self, code_map: dict[str, int]):
        self._code_map: dict[str, int] = dict(code_map)
        # ``.codes`` 属性 access に対応（test contract: ``frozen_map.codes[UNSEEN]``）。
        # 同一 dict への参照を返す（copy しない・frozen 扱い）。
        self.codes: dict[str, int] = self._code_map

    # --- dict-style access (test contract: ``frozen_map["__UNSEEN__"]``) ---
    def __getitem__(self, key: str) -> int:
        return self._code_map[key]

    def __contains__(self, key: object) -> bool:
        return key in self._code_map

    def __iter__(self) -> Iterator[str]:
        return iter(self._code_map)

    def __len__(self) -> int:
        return len(self._code_map)

    def keys(self):  # noqa: D401
        return self._code_map.keys()

    def items(self):  # noqa: D401
        return self._code_map.items()

    def get(self, key: str, default: int | None = None) -> int | None:
        return self._code_map.get(key, default)

    def __repr__(self) -> str:
        return f"FrozenCategoryMap(n_codes={len(self._code_map)})"

    # joblib / pickle 用
    def __getstate__(self) -> dict:
        return {"_code_map": self._code_map}

    def __setstate__(self, state: dict) -> None:
        self._code_map = state["_code_map"]
        self.codes = self._code_map


def fit_category_map(df: pd.DataFrame, *, column: str) -> FrozenCategoryMap:
    """``df[column]`` から frozen category map を fit する。

    **呼出側責任**: ``df`` は**訓練窓のみ**を渡すこと（Pitfall 3.4・test 構成リーク防止）。
    本関数自体は train 窓 filter を行わない（``build_frozen_category_maps`` が窓 filter して
    各カラム毎に本関数を呼ぶ）。低レベルな呼出（unit test 等）では全行を train 扱いで fit
    する。

    Parameters
    ----------
    df : pd.DataFrame
        ``column`` を含む DataFrame。train 窓行のみを渡すこと。
    column : str
        fit 対象の categorical ID 列名（``_CATEGORY_COLUMNS`` のいずれかを推奨）。

    Returns
    -------
    FrozenCategoryMap
        ``__getitem__`` と ``.codes`` の両方で sentinel / category に access 可能。
    """
    code_map = _fit_one(df[column])
    return FrozenCategoryMap(code_map)


def apply_category_map(
    df: pd.DataFrame,
    *,
    column: str,
    frozen_map: FrozenCategoryMap,
) -> pd.DataFrame:
    """frozen category map を ``df[column]`` に適用し ``f"{column}_code"`` 列を追加する。

    **再 fit 禁止**: ``frozen_map`` は ``fit_category_map`` の戻り値を其のまま渡す
    （``src.utils.category_map.apply_category_map`` のみ呼出・``fit_category_map`` は呼ばない）。
    未知値は ``code[UNSEEN]``・欠損は ``code[MISSING]`` へフォールバック（§14.5 欠損理由区別）。
    戻り値は**非負 int32**（LightGBM §14.3・pandas category code -1 ハザード回避）。
    """
    result = df.copy()
    result[f"{column}_code"] = _apply_one(df[column], frozen_map.codes)
    return result


def build_frozen_category_maps(
    feature_matrix: pd.DataFrame,
    *,
    train_window: tuple[str, str] = _TRAIN_WINDOW,
) -> dict[str, FrozenCategoryMap]:
    """feature matrix 上の train 窓（D-09）でのみ frozen category map を fit する。

    **train 窓 mask 計算** (Pitfall 3.4 / D-09・regression guard):
        ``train_mask = feature_matrix["race_date"].between(train_window[0], train_window[1])``
        絶対に val/test 行を fit に渡さない（test 構成リーク）。

    **race_date 必須** (CR-03 / 03-05 gap-closure / D-13 fail-loud):
        ``race_date`` 列が欠損する frame は ``ValueError`` を raise する
        （silent all-train fallback を禁止・将来の refactor で val/test 行が fit に
        混入する潜伏 leak を防止）。

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        ``race_date`` 列と ``_CATEGORY_COLUMNS`` 各カラムを含む feature matrix。
    train_window : tuple[str, str]
        train 窓 (start, end)。既定 ``("2016-07-01", "2023-12-31")`` (D-09)。

    Returns
    -------
    dict[str, FrozenCategoryMap]
        各 ``_CATEGORY_COLUMNS`` カラムの frozen map。

    Raises
    ------
    ValueError
        ``race_date`` 列が欠損している場合（CR-03 fail-loud・D-13 silent fallback 禁止）。
    """
    # --- CR-03 (03-05): race_date 欠損 frame は fail-loud（ValueError） ---
    if "race_date" not in feature_matrix.columns:
        raise ValueError(
            "build_frozen_category_maps: feature_matrix に race_date 列が無い "
            "(train 窓 mask を計算できない・Pitfall 3.4 / §14.3 / D-13 fail-loud・"
            "03-05 CR-03 fix)"
        )
    # --- train 窓 mask (D-09・race_date で train period filter・Pitfall 3.4) ---
    race_date_col = pd.to_datetime(feature_matrix["race_date"])
    train_mask = race_date_col.between(train_window[0], train_window[1])

    maps: dict[str, FrozenCategoryMap] = {}
    for col in _CATEGORY_COLUMNS:
        if col not in feature_matrix.columns:
            continue
        # 訓練窓 series のみ fit に渡す（val/test 行は絶対に含めない・Pitfall 3.4）
        train_series = feature_matrix.loc[train_mask, col]
        code_map = _fit_one(train_series)
        maps[col] = FrozenCategoryMap(code_map)
    return maps


def apply_frozen_category_maps(
    feature_matrix: pd.DataFrame,
    frozen_maps: dict[str, FrozenCategoryMap],
) -> pd.DataFrame:
    """frozen category maps を feature matrix 全体に適用し raw ID alias 列を drop する。

    **REVIEWS HIGH #5 / CYCLE-2 HIGH #5 raw ID drop**:
      - 各 ``_CATEGORY_COLUMNS`` に ``apply_category_map`` を呼出し ``f"{col}_code"`` (int32)
        列を追加する。
      - coding 完了後に ``drop(columns=list(_CATEGORY_COLUMNS))`` で raw ID 文字列 alias 列を
        破棄する。これにより Phase 4 モデルが raw ID で train/refit する経路を構造的に遮断。
      - ``_CATEGORY_COLUMNS`` は5抽象名（``jockey_id``/``trainer_id``/``sire_id``/``bms_id``/
        ``horse_id``）のみで ``kettonum`` を**含まない**。``kettonum`` は canonical key /
        snapshot sort key / rolling obs_id の要素であり apply 後も保持される。

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        ``_CATEGORY_COLUMNS`` 各カラムを含む feature matrix。
    frozen_maps : dict[str, FrozenCategoryMap]
        ``build_frozen_category_maps`` の戻り値。

    Returns
    -------
    pd.DataFrame
        ``_CATEGORY_COLUMNS`` を drop し ``f"{col}_code"`` 列（int32・非負）を追加した
        feature matrix。``kettonum`` は保持。
    """
    result = feature_matrix.copy()
    for col, frozen_map in frozen_maps.items():
        if col not in result.columns:
            continue
        # apply_category_map のみ呼出（再 fit 禁止・__UNSEEN__ / 非負 int32 保証）
        result[f"{col}_code"] = _apply_one(result[col], frozen_map.codes)

    # raw ID 文字列 alias 列を drop（_CATEGORY_COLUMNS は5抽象名のみ・kettonum 含まず）
    # Phase 4 モデルが raw ID で refit する経路を構造的に遮断 (HIGH #5 / CYCLE-2 HIGH #5)。
    cols_to_drop = [c for c in _CATEGORY_COLUMNS if c in result.columns]
    if cols_to_drop:
        result = result.drop(columns=cols_to_drop)
    return result


def persist_category_maps(
    maps: dict[str, FrozenCategoryMap],
    artifact_path: str | Path,
) -> None:
    """frozen category maps を joblib で永続化する。

    Parquet snapshot と同 snapshot_id で紐付け（例:
    ``snapshots/category_map_<snapshot_id>.joblib``）。Phase 4 モデルは本 artifact を
    ``load_category_maps`` で読込・val/test のコード化に使用する。
    """
    Path(artifact_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(maps, artifact_path)


def load_category_maps(artifact_path: str | Path) -> dict[str, FrozenCategoryMap]:
    """永続化された frozen category maps を読み込む（Phase 4 モデル学習時使用）。"""
    return joblib.load(artifact_path)
