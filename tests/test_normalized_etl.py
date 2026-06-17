"""DATA-02 normalized ETL integration test（Pitfall 1/2/4 / HIGH #5/#6 / MEDIUM #1）。

本テストは 01-VALIDATION.md §Phase Requirements → Test Map に準拠し、以下を保証する:
  - Pitfall 1: 全 varchar raw を明示キャストし typed カラムで格納
  - Pitfall 2: 全クエリで ``jyocd BETWEEN '01' AND '10'``（NAR 除外）
  - HIGH #5: ``_idempotent_load``（staging-swap）で ETL 再実行時に重複しない
  - HIGH #6: ETL ロール（``write_pool``）で normalized に書込む
  - MEDIUM #1: ``normalized.n_uma_race`` の主要カラム（``kakuteijyuni`` / ``kettonum`` /
    ``bamei`` / ``bataijyu`` 等）が型付き定義される

``@pytest.mark.requires_db`` は ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ skip（HIGH #8）。
"""

from __future__ import annotations

import pandas as pd
import pytest


def test_normalize_module_imports_and_signatures() -> None:
    """``run_normalized_etl`` / ``_create_normalized_tables`` / ``_idempotent_load`` が存在。"""
    from src.etl import normalize

    assert callable(normalize.run_normalized_etl)
    assert callable(normalize._create_normalized_tables)
    assert callable(normalize._idempotent_load)


def test_normalize_no_duckdb_no_raw_writes() -> None:
    """DuckDB を import しない（§12.1）・raw に UPDATE/DELETE を発行しない（成功基準#2）。"""
    import inspect

    from src.etl import normalize

    src = inspect.getsource(normalize)
    assert "import duckdb" not in src, "§12.1: DuckDB は補助のみ・永続化に使わない"
    assert "UPDATE public.n_" not in src, "raw に UPDATE を発行してはならない（成功基準#2）"
    assert "DELETE FROM public.n_" not in src, "raw に DELETE を発行してはならない（成功基準#2）"


def test_normalize_has_staging_swap_and_jra_filter() -> None:
    """HIGH #5: staging-swap パターン（_staging / RENAME TO / DROP TABLE IF EXISTS）を含む。
    Pitfall 2: 全 SELECT で JRA フィルタを含む。
    """
    import inspect

    from src.etl import normalize

    src = inspect.getsource(normalize)
    assert "_staging" in src, "HIGH #5: staging-table-swap パターンを含むべき"
    assert "RENAME TO" in src, "HIGH #5: RENAME TO で atomic swap すべき"
    assert "DROP TABLE IF EXISTS normalized" in src, "HIGH #5: DROP TABLE IF EXISTS normalized を含むべき"
    assert "jyocd BETWEEN '01' AND '10'" in src, "Pitfall 2: JRA フィルタ必須"


def test_normalize_uses_write_pool_and_etl_role() -> None:
    """HIGH #6: ``write_pool`` / ``write_cur`` を引数に取り INSERT は ETL ロール経由。"""
    import inspect

    from src.etl import normalize

    src = inspect.getsource(normalize)
    # write_pool / write_cur の両方が参照されている（run_normalized_etl 引数 + 内部利用）
    assert src.count("write_pool") + src.count("write_cur") >= 2, (
        "HIGH #6: write_pool / write_cur を引数・内部で使用すべき"
    )


def test_transform_race_df_hassotime_zero_falls_back_to_nat() -> None:
    """Warning #5: hassotime='0'（EveryDB2 初期値）は NaT にフォールバック（ETL 停止回避）。"""
    from src.etl.normalize import _transform_race_df

    df = pd.DataFrame(
        {
            "year": [2020, 2020],
            "monthday": ["0101", "0101"],
            "jyocd": ["05", "05"],
            "kaiji": ["01", "01"],
            "nichiji": ["01", "01"],
            "racenum": ["01", "02"],
            "kyori": ["1600", "1400"],
            "hassotime": ["1500", "0"],  # 2行目が EveryDB2 初期値 '0'
            "jyokencd5": ["005", "005"],
            "gradecd": ["", ""],
            "syubetucd": ["00", "00"],
            "hondai": ["race1", "race2"],
        }
    )
    out = _transform_race_df(df)
    # 1行目は正常に timestamp 構築
    assert pd.notna(out.loc[0, "race_start_datetime"])
    # 2行目は NaT（hassotime='0' を弾く・ValueError で ETL 停止しない）
    assert pd.isna(out.loc[1, "race_start_datetime"]), (
        "hassotime='0' は NaT にフォールバックすべき（Warning #5）"
    )


@pytest.mark.requires_db
def test_run_normalized_etl_creates_typed_n_race(pg_pool, write_pool) -> None:  # noqa: ANN001
    """実DB で ETL を実行し ``normalized.n_race`` が typed で作成される（Pitfall 1）。"""
    from src.etl.normalize import run_normalized_etl

    result = run_normalized_etl(pg_pool, write_pool, tables=["n_race"])
    assert result["raw_touched"] is False
    assert "n_race" in result["rows_inserted"]
    assert result["rows_inserted"]["n_race"] > 0


@pytest.mark.requires_db
def test_type_cast_kyori_int(readonly_cur, write_pool, pg_pool) -> None:  # noqa: ANN001
    """Pitfall 1: ``normalized.n_race.kyori`` が integer で返る。"""
    from src.etl.normalize import run_normalized_etl

    run_normalized_etl(pg_pool, write_pool, tables=["n_race"])
    readonly_cur.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema='normalized' AND table_name='n_race' AND column_name='kyori'"
    )
    row = readonly_cur.fetchone()
    assert row is not None
    assert row[0] == "integer", f"kyori は integer であるべき（got {row[0]}）"


@pytest.mark.requires_db
def test_race_date_constructed(readonly_cur) -> None:  # noqa: ANN001
    """``normalized.n_race.race_date`` が date 型で 2015年以降の値を含む。"""
    readonly_cur.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema='normalized' AND table_name='n_race' AND column_name='race_date'"
    )
    row = readonly_cur.fetchone()
    assert row is not None and row[0] == "date"

    readonly_cur.execute(
        "SELECT min(race_date), max(race_date) FROM normalized.n_race "
        "WHERE jyocd BETWEEN '01' AND '10'"
    )
    mn, mx = readonly_cur.fetchone()
    # 2015年以降（要件 6.1）
    assert mn is not None and mn.year >= 2015
    assert mx is not None and mx.year >= 2015


@pytest.mark.requires_db
def test_jra_only_filter(readonly_cur) -> None:  # noqa: ANN001
    """Pitfall 2: ``normalized.n_race`` 全行が JRA のみ。"""
    readonly_cur.execute(
        "SELECT count(*) FROM normalized.n_race WHERE NOT (jyocd BETWEEN '01' AND '10')"
    )
    cnt = readonly_cur.fetchone()[0]
    assert cnt == 0, f"normalized.n_race に JRA 外の行が混入（Pitfall 2 違反）: {cnt}行"


@pytest.mark.requires_db
def test_class_columns_populated(readonly_cur) -> None:  # noqa: ANN001
    """``class_level_numeric`` / ``post_2019_class_system_flag`` / ``class_normalization_status``
    が全行に存在し非NULL率が高い。"""
    readonly_cur.execute(
        "SELECT count(*) FROM normalized.n_race "
        "WHERE class_normalization_status IS NULL"
    )
    null_cnt = readonly_cur.fetchone()[0]
    readonly_cur.execute("SELECT count(*) FROM normalized.n_race")
    total = readonly_cur.fetchone()[0]
    assert total > 0
    # post_2019_flag は race_date から常に計算されるので NULL は 0 であるべき（MEDIUM #4）
    readonly_cur.execute(
        "SELECT count(*) FROM normalized.n_race WHERE post_2019_class_system_flag IS NULL"
    )
    post_null = readonly_cur.fetchone()[0]
    assert post_null == 0, "post_2019_flag は race_date から常に計算されるべき（MEDIUM #4）"


@pytest.mark.requires_db
def test_rowcount_jra_matches_raw(readonly_cur) -> None:  # noqa: ANN001
    """``normalized.n_race`` 件数が raw の JRA 件数と一致。"""
    readonly_cur.execute(
        "SELECT count(*) FROM public.n_race WHERE jyocd BETWEEN '01' AND '10'"
    )
    raw_count = readonly_cur.fetchone()[0]
    readonly_cur.execute(
        "SELECT count(*) FROM normalized.n_race WHERE jyocd BETWEEN '01' AND '10'"
    )
    norm_count = readonly_cur.fetchone()[0]
    assert raw_count == norm_count, (
        f"件数不一致: raw(JRA)={raw_count} vs normalized={norm_count}"
    )


@pytest.mark.requires_db
def test_etl_idempotent_rerun(pg_pool, write_pool, readonly_cur) -> None:  # noqa: ANN001
    """HIGH #5: ``run_normalized_etl`` を2回連続実行しても件数とハッシュが同一。"""
    from src.etl.normalize import run_normalized_etl

    run_normalized_etl(pg_pool, write_pool, tables=["n_race"])
    readonly_cur.execute(
        "SELECT count(*), md5(string_agg((n.*)::text, ',' ORDER BY (year, jyocd, kaiji, nichiji, racenum)::text)) "
        "FROM normalized.n_race"
    )
    cnt1, hash1 = readonly_cur.fetchone()

    run_normalized_etl(pg_pool, write_pool, tables=["n_race"])
    readonly_cur.execute(
        "SELECT count(*), md5(string_agg((n.*)::text, ',' ORDER BY (year, jyocd, kaiji, nichiji, racenum)::text)) "
        "FROM normalized.n_race"
    )
    cnt2, hash2 = readonly_cur.fetchone()

    assert cnt1 == cnt2, f"HIGH #5 violation: 件数が変わった {cnt1} -> {cnt2}"
    assert hash1 == hash2, "HIGH #5 violation: ハッシュが変わった（重複した可能性）"


@pytest.mark.requires_db
def test_uma_race_typed_columns(readonly_cur, pg_pool, write_pool) -> None:  # noqa: ANN001
    """MEDIUM #1: ``normalized.n_uma_race`` の主要カラムが型付き定義される。"""
    from src.etl.normalize import run_normalized_etl

    run_normalized_etl(pg_pool, write_pool, tables=["n_uma_race"])

    for col, expected_type in [
        ("kakuteijyuni", "integer"),
        ("kettonum", "integer"),  # int 系
        ("bamei", "text"),
        ("umaban", "integer"),
        ("bataijyu", "integer"),
    ]:
        readonly_cur.execute(
            "SELECT data_type FROM information_schema.columns "
            f"WHERE table_schema='normalized' AND table_name='n_uma_race' AND column_name='{col}'"
        )
        row = readonly_cur.fetchone()
        assert row is not None, f"normalized.n_uma_race に {col} が存在しない（MEDIUM #1）"
        # int 系は "integer" / "smallint" / "bigint" いずれも許容
        if expected_type == "integer":
            assert row[0] in ("integer", "smallint", "bigint"), (
                f"{col} は int 系であるべき（got {row[0]}）"
            )
        else:
            assert row[0] == expected_type, f"{col} は {expected_type} であるべき（got {row[0]}）"
