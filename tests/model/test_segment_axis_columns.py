"""segment 6軸カラム経路確認テスト（Phase 6 Wave 0・Plan 06-01 Task 2・Open Question #1 解決）。

Purpose:
  Phase 6 本体（Plan 06-05 run_evaluation.py で segment 評価を生成）を実装する前に、
  segment 6軸（year/month・競馬場・頭数・人気帯・オッズ帯）のデータ経路が label.fukusho_label +
  prediction.fukusho_prediction の JOIN で揃うかを実 DB で検証する（Open Question #1）。

  researcher が CONTEXT.md で「segment 軸が揃うことを確認」としたが・実コードで未検証だったため・
  本テストが GREEN になった時点で Open Question #1 を RESOLVED とする。

REVIEW HIGH#3 対応（fail-loud）:
  segment 軸カラムの欠損は WARN skip でなく pytest.fail で fail-loud とする
  （D-12「6軸全て生成」の前提検証・代替カラム確定不能ならテスト失敗）。

REVIEW C3 対応（label/market 二段階確認）:
  label.fukusho_label に ninki/fukuoddslower が存在しない場合・market データ
  （raw_everydb2.n_odds_tanpuku / normalized.n_uma_race）にフォールバック経路があるか確認。
  label/market 双方に欠損の場合のみ pytest.fail（真に SC#3 履行不能）。

検証結果（実 DB 確定・CONTEXT.md の「researcher 確定」を本テストが裏付け）:
  - race_date / jyocd / sales_start_entry_count / final_starter_count → label.fukusho_label に存在
  - ninki → normalized.n_uma_race に存在（label には不存在・market JOIN で補完）
  - fukuoddslow / fukuoddshigh → raw_everydb2.n_odds_tanpuku に存在（label には不存在・market JOIN で補完）
  - prediction.fukusho_prediction は RACE_KEY 7カラム + race_date + split を持ち・label と race_key で JOIN 可能

参照:
  - 06-CONTEXT.md specifics セクション（segment 軸のデータ経路）
  - 06-RESEARCH.md Open Question #1 / Pitfall 6
  - src/etl/fukusho_label.py（LABEL_INSERT_COLUMNS = label.fukusho_label のカラム定義）
  - src/db/schema.py（PREDICTION_TABLE_DDL・prediction.fukusho_prediction のカラム）
  - src/model/baseline.py::fetch_market_data（market データ JOIN 経路）
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _columns(cur: Any, schema: str, table: str) -> set[str]:
    """information_schema.columns から指定テーブルのカラム名集合を返す（SQL injection 防御・parameterized）。

    Parameters
    ----------
    cur : readonly cursor。
    schema : schema 名（例: "label", "prediction", "raw_everydb2", "normalized"）。
    table : テーブル名（例: "fukusho_label", "fukusho_prediction", "n_odds_tanpuku", "n_uma_race"）。

    Returns
    -------
    set[str]
        カラム名の集合。
    """
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return {r[0] for r in cur.fetchall()}


# RACE_KEY 7カラム（label/prediction/market 共通・HIGH-1/HIGH-2 JOIN 契約）
RACE_KEY_COLUMNS: set[str] = {"year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"}


# ---------------------------------------------------------------------------
# Test 1: prediction.fukusho_prediction の segment JOIN keys
# ---------------------------------------------------------------------------


def test_prediction_table_has_segment_join_keys(readonly_cur: Any) -> None:
    """prediction.fukusho_prediction に RACE_KEY 7カラム + race_date が存在する（segment JOIN 前提）。

    entry_count は prediction 側に無くても PASS（label JOIN 経路で補完・test_label 側で検証）。
    """
    cols = _columns(readonly_cur, "prediction", "fukusho_prediction")
    required = RACE_KEY_COLUMNS | {"race_date"}
    missing = required - cols
    assert not missing, (
        f"prediction.fukusho_prediction に segment JOIN 必須カラムが欠損: {sorted(missing)} "
        f"(存在カラム: {sorted(cols)})"
    )
    # split カラム（test split 抽出用）の存在も検証
    assert "split" in cols, (
        f"prediction.fukusho_prediction に 'split' カラムが不存在（test split 抽出不能）"
    )
    # 結果を出力（run_evaluation.py 側で参照可能・attrs 的な情報）
    entry_count_source = "label" if "entry_count" not in cols else "prediction"
    print(  # noqa: T201
        f"[segment_axis] prediction_join_keys={sorted(RACE_KEY_COLUMNS)}, "
        f"entry_count_source={entry_count_source} (label JOIN で補完)"
    )


# ---------------------------------------------------------------------------
# Test 2: label.fukusho_label の segment 軸（fail-loud・REVIEW HIGH#3）
# ---------------------------------------------------------------------------


def test_label_table_has_segment_axes(readonly_cur: Any) -> None:
    """label.fukusho_label に segment 軸カラム（race_date / jyocd / entry_count 系）が存在することを確認。

    REVIEW HIGH#3: 欠損カラムは WARN skip でなく pytest.fail で fail-loud。
    ninki / fukuoddslow 系は label 側に存在しないことが想定されるため・本 test では必須とせず・
    test_market_data_segment_axes_if_label_missing で market 経路の存在を検証する。
    """
    cols = _columns(readonly_cur, "label", "fukusho_label")

    # race_date（year/month 軸の元）: 必須
    if "race_date" not in cols:
        pytest.fail(
            f"label.fukusho_label.race_date 欠損: year/month segment 軸履行不能 "
            f"(存在カラム: {sorted(cols)})"
        )
    # jyocd（競馬場軸）: 必須
    if "jyocd" not in cols:
        pytest.fail(
            f"label.fukusho_label.jyocd 欠損: 競馬場 segment 軸履行不能 "
            f"(存在カラム: {sorted(cols)})"
        )
    # 頭数軸: sales_start_entry_count 又は final_starter_count のいずれか（両方不在なら fail）
    entry_count_candidates = {"sales_start_entry_count", "final_starter_count"}
    entry_count_present = entry_count_candidates & cols
    if not entry_count_present:
        pytest.fail(
            f"label.fukusho_label に頭数軸カラムが欠損: {sorted(entry_count_candidates)} のいずれも不存在 "
            f"(存在カラム: {sorted(cols)})"
        )

    # ninki / fukuoddslow（人気帯/オッズ帯軸）: label 側では必須とせず・market 経路で補完確認（次 test）
    axes_status: dict[str, str] = {
        "race_date": "label.fukusho_label.race_date",
        "jyocd": "label.fukusho_label.jyocd",
        "entry_count": f"label.fukusho_label.{sorted(entry_count_present)}",
        "ninki": "label_absent_check_market" if "ninki" not in cols else "label.fukusho_label.ninki",
        "odds_band": (
            "label_absent_check_market"
            if not ({"fukuoddslow", "fukuoddshigh"} & cols)
            else f"label.fukusho_label.{sorted({'fukuoddslow', 'fukuoddshigh'} & cols)}"
        ),
    }
    print(f"[segment_axis] label_axes_status={axes_status}")  # noqa: T201


# ---------------------------------------------------------------------------
# Test 3: prediction と label の JOIN 後行数一致（cartesian duplication なし）
# ---------------------------------------------------------------------------


def test_segment_join_coverage(readonly_cur: Any) -> None:
    """prediction.fukusho_prediction（test split）と label.fukusho_label を RACE_KEY 7カラムで JOIN した結果の
    行数が prediction test split 行数と一致することを検証（HIGH-1/HIGH-2 JOIN 契約）。

    JOIN 後行数減少 = label 欠損・JOIN 後行数増加 = cartesian duplication・いずれも pytest.fail。
    """
    # prediction test split 行数
    readonly_cur.execute("SELECT count(*) FROM prediction.fukusho_prediction WHERE split = 'test'")
    pred_test_count = readonly_cur.fetchone()[0]
    assert pred_test_count > 0, "prediction.fukusho_prediction test split が 0 行（Phase 4 予測未生成?）"

    # JOIN 後行数（parameterized query で構築・SQL injection 防御）
    join_sql = """
        SELECT count(*)
        FROM prediction.fukusho_prediction p
        INNER JOIN label.fukusho_label l
            ON p.year = l.year
           AND p.jyocd = l.jyocd
           AND p.kaiji = l.kaiji
           AND p.nichiji = l.nichiji
           AND p.racenum = l.racenum
           AND p.umaban = l.umaban
           AND p.kettonum = l.kettonum
        WHERE p.split = 'test'
    """
    readonly_cur.execute(join_sql)
    joined_count = readonly_cur.fetchone()[0]

    assert joined_count == pred_test_count, (
        f"prediction test split と label.fukusho_label の JOIN 後行数が不一致: "
        f"pred_test={pred_test_count}, joined={joined_count} "
        f"(減少={pred_test_count - joined_count} = label 欠損 / "
        f"増加={joined_count - pred_test_count} = cartesian duplication・HIGH-1/HIGH-2 JOIN 契約違反)"
    )
    print(  # noqa: T201
        f"[segment_axis] join_coverage: pred_test={pred_test_count}, joined={joined_count} (一致・JOIN 契約 OK)"
    )


# ---------------------------------------------------------------------------
# Test 4: market データの segment 軸フォールバック確認（REVIEW HIGH#3/C3）
# ---------------------------------------------------------------------------


def test_market_data_segment_axes_if_label_missing(readonly_cur: Any) -> None:
    """label.fukusho_label に ninki/fukuoddslow 系が存在しない場合の market データフォールバック経路確認。

    REVIEW HIGH#3/C3 対応:
      - label 側で ninki/odds が欠損していた場合・market データ
        （raw_everydb2.n_odds_tanpuku / normalized.n_uma_race）にフォールバック経路があるか確認。
      - label/market 双方に欠損の場合のみ pytest.fail（真に SC#3 履行不能）。

    market 経路（src/model/baseline.py::fetch_market_data と同一）:
      - raw_everydb2.n_odds_tanpuku: fukuoddslow / fukuoddshigh（複勝オッズ下限/上限）
      - normalized.n_uma_race: ninki（確定人気）
    """
    label_cols = _columns(readonly_cur, "label", "fukusho_label")
    odds_cols = _columns(readonly_cur, "raw_everydb2", "n_odds_tanpuku")
    uma_race_cols = _columns(readonly_cur, "normalized", "n_uma_race")

    # --- ninki（人気帯軸）---
    ninki_sources: list[str] = []
    if "ninki" in label_cols:
        ninki_sources.append("label.fukusho_label.ninki")
    if "ninki" in uma_race_cols:
        ninki_sources.append("normalized.n_uma_race.ninki")
    if not ninki_sources:
        pytest.fail(
            "SC#3 履行不能: ninki（人気帯 segment 軸）が label/market 双方で欠損 "
            f"(label: {sorted(label_cols)}, n_uma_race: {sorted(uma_race_cols)})"
        )

    # --- オッズ帯軸（fukuoddslow/fukuoddshigh 系）---
    odds_candidates = {"fukuoddslow", "fukuoddshigh", "fukuninki"}
    odds_sources: list[str] = []
    label_odds = odds_candidates & label_cols
    if label_odds:
        odds_sources.append(f"label.fukusho_label.{sorted(label_odds)}")
    market_odds = odds_candidates & odds_cols
    if market_odds:
        odds_sources.append(f"raw_everydb2.n_odds_tanpuku.{sorted(market_odds)}")
    if not odds_sources:
        pytest.fail(
            "SC#3 履行不能: オッズ帯 segment 軸（fukuoddslow/fukuoddshigh 系）が label/market 双方で欠損 "
            f"(label: {sorted(label_cols)}, n_odds_tanpuku: {sorted(odds_cols)})"
        )

    print(  # noqa: T201
        f"[segment_axis] market_fallback_resolved: ninki_source={ninki_sources}, "
        f"odds_source={odds_sources} "
        f"(Plan 06-05 run_evaluation.py が fetch_market_data JOIN 経路で補完可能)"
    )
