"""src.etl.quality_gate の unit + integration test（plan 01-02）。

REVIEWS HIGH #7: ``test_mojibake_detection`` と ``test_code_value_anomaly_detection``
を必須テストとして含む。

REVIEWS HIGH #8: DB-test skip policy は conftest.py の autouse に従い
``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ skip。本ファイル内に skip ロジックは書かない
（plan 01-01 Task 2 と完全一致）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.etl.quality_gate import (
    _check_code_value_anomalies,
    _check_mojibake,
    _check_n_uma_race_natural_key_unique,
    _check_table_exists,
    _load_allowed_codes,
    run_quality_gate,
)

# ---------------------------------------------------------------------------
# Helpers: モック cursor を構築するファクトリ
# ---------------------------------------------------------------------------


def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    """SQL の先頭キーワードで分類せず、実行 SQL 文字列をそのままキーにして
    fetchone() の戻り値を返すモック cursor。

    fetch_map のキーは部分文字列マッチ（in）で判定する。
    """

    cur = MagicMock()
    cur._fetch_map = fetch_map  # noqa: SLF001

    def _execute(sql: str, *args, **kwargs):  # noqa: ANN002
        cur._last_sql = sql  # noqa: SLF001
        return cur

    cur.execute.side_effect = _execute

    def _fetchone():
        sql = getattr(cur, "_last_sql", "")
        for key, val in cur._fetch_map.items():  # noqa: SLF001
            if key in sql:
                return val
        # フォールバック: 未知の SELECT には安全なゼロ値を返す（INFO チェックの
        # 件数参照が unit test で落ちないようにする）
        if sql.strip().upper().startswith("SELECT"):
            return (0,)
        return None

    cur.fetchone.side_effect = _fetchone
    return cur


# ---------------------------------------------------------------------------
# RED: BLOCK チェック — 失敗時に verdict="fail"
# ---------------------------------------------------------------------------


def test_blocking_checks_fail_when_no_2015_data() -> None:
    """2015-01-01 以降の JRA データが0件の場合、verdict=="fail"・該当 check は
    severity="block" で passed=False となる。"""

    # _check_jra_since_2015 の SELECT count(*) が 0 を返す状況を模擬。
    # 他の BLOCK チェックは成功するように設定。
    cur = _mock_cursor(
        {
            # 2015 以降件数 = 0 → fail
            "20150101": (0,),
            # PK 重複 diff = 0 → pass
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum))": (40035, 40035),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum))": (
                1000000,
                1000000,
            ),
            # information_schema.tables ヒット数 = 1（存在）
            "information_schema.tables": (1,),
        }
    )

    result = run_quality_gate(cur)
    assert result["verdict"] == "fail"
    block_checks = [c for c in result["checks"] if c["severity"] == "block"]
    assert block_checks, "BLOCK check が少なくとも1つ存在する"
    failed_blocks = [c for c in block_checks if not c["passed"]]
    assert any(
        "2015" in c["name"] or "jra_since" in c["name"].lower() for c in failed_blocks
    ), f"2015 check が fail しているはず: {[c['name'] for c in failed_blocks]}"


def test_n_race_pk_duplicate_fails() -> None:
    """n_race PK 重複が存在する場合、verdict=="fail"・該当 check は
    severity="block" で passed=False となる。"""

    cur = _mock_cursor(
        {
            "20150101": (39593,),
            # PK: total - distinct = 5（重複あり）
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum))": (40040, 40035),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum))": (
                1000000,
                1000000,
            ),
            "information_schema.tables": (1,),
        }
    )

    result = run_quality_gate(cur)
    assert result["verdict"] == "fail"
    pk_check = next(
        c for c in result["checks"] if "pk" in c["name"].lower() and "n_race" in c["name"]
    )
    assert pk_check["severity"] == "block"
    assert pk_check["passed"] is False


def test_table_missing_fails() -> None:
    """主要5系統テーブルのいずれかが存在しない場合、verdict=="fail"。"""

    cur = _mock_cursor(
        {
            "20150101": (39593,),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum))": (40035, 40035),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum))": (
                1000000,
                1000000,
            ),
            # 全テーブル存在しない
            "information_schema.tables": (0,),
        }
    )

    result = run_quality_gate(cur)
    assert result["verdict"] == "fail"
    exists_checks = [c for c in result["checks"] if "table_exists" in c["name"]]
    assert exists_checks, "table_exists check が存在する"
    assert all(not c["passed"] for c in exists_checks)


# ---------------------------------------------------------------------------
# RED: HIGH #7 — mojibake / code-value-anomaly 検出
# ---------------------------------------------------------------------------


def test__load_allowed_codes_from_yaml() -> None:
    """_load_allowed_codes が class_normalization.yaml と code_tables.yaml から
    allowed-code-set を正しく構築する。"""
    codes = _load_allowed_codes()

    # jyokencd5: 6 値（701/703/005/010/016/999）
    assert "jyokencd5" in codes
    assert codes["jyokencd5"] == {"701", "703", "005", "010", "016", "999"}

    # gradecd: A/B/C/D/L/E/F/G/H + ''（空文字）
    assert "gradecd" in codes
    assert codes["gradecd"] >= {"A", "B", "C", "D", "L", "E", "F", "G", "H", ""}

    # jyocd: 01..10
    assert "jyocd" in codes
    assert codes["jyocd"] == {f"{i:02d}" for i in range(1, 11)}

    # syubetucd: code_tables.yaml の値
    assert "syubetucd" in codes
    assert codes["syubetucd"] >= {"00", "11", "12", "13", "14", "15", "16", "17", "18", "19"}


def test_mojibake_detection() -> None:
    """_check_mojibake が U+FFFD を含む行を検出して件数 > 0 を報告する。

    モック cursor は各 varchar カラム検査で `count(*) AS cnt` を fetchone する。
    """

    # U+FFFD を含む件数として 3 を返す（一部カラム）
    cur = _mock_cursor(
        {
            # mojibake 検出 SQL の本文に含まれる文字列で判定
            "FFFD": (3,),
        }
    )

    result = _check_mojibake(cur)
    assert result.severity == "info"
    assert "columns" in result.detail
    # 少なくとも1カラムで件数 > 0
    assert any(v.get("count", 0) > 0 for v in result.detail["columns"].values()), (
        f"mojibake 件数 > 0 が報告されるはず: {result.detail}"
    )


def test_code_value_anomaly_detection() -> None:
    """_check_code_value_anomalies が allowed-code-set 外の値を検出して件数 > 0 を報告する。

    例: jyokencd5='ZZZ', gradecd='Z', jyocd='99' を含むデータで件数 > 0。
    """

    # 実装の SQL は `NOT ({col} = ANY(%s::text[]))` 形式。
    # モック fetch_map は部分文字列マッチなので、各 col 名でヒットさせる。
    cur = _mock_cursor(
        {
            # code_columns の3つは JRA フィルタ内で異常件数を返す
            # （3つとも同じ (5,) を返すと全部同じ戻り値になるが、anomaly>0 を確認できればよい）
            "jyokencd5": (5,),
            "gradecd": (2,),
            "syubetucd": (0,),
            # jyocd_non_jra（全体・BETWEEN 無し）
            "jyocd IS NOT NULL": (7,),
            # 全体件数（JRA 限定）
            "FROM n_race WHERE jyocd BETWEEN": (40035,),
        }
    )

    allowed = _load_allowed_codes()
    result = _check_code_value_anomalies(cur, allowed)
    assert result.severity == "info"
    assert "columns" in result.detail
    flagged = {k: v for k, v in result.detail["columns"].items() if v.get("count", 0) > 0}
    assert flagged, f"anomaly 件数 > 0 が報告されるはず: {result.detail}"


# ---------------------------------------------------------------------------
# GREEN 検証: pass-when-clean
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_pass_when_clean(readonly_cur) -> None:  # noqa: ANN001
    """実 everydb2 DB に接続し verdict=="pass" を確認する integration test。

    .env 未設定時は Settings() の validation error で fail（HIGH #8）。
    KEIBA_SKIP_DB_TESTS=1 設定時のみ conftest が skip する。
    """
    result = run_quality_gate(readonly_cur)
    assert result["verdict"] in ("pass", "fail"), f"verdict は pass/fail のいずれか: {result}"
    # 実 DB は 01-01 SUMMARY で 2015 以降 39593 件・重複0 を確認済み → pass を期待
    assert result["verdict"] == "pass", (
        f"実DBは構造的欠陥無しを期待: {[c for c in result['checks'] if not c['passed']]}"
    )


@pytest.mark.requires_db
def test_jra_only_filter(readonly_cur) -> None:  # noqa: ANN001
    """実 DB で WHERE jyocd BETWEEN '01' AND '10' が全体より件数を減らすことを確認。

    これにより NAR（jyocd>=30）混入の検知能力を検証する（Pitfall 2）。
    """
    readonly_cur.execute("SELECT count(*) FROM n_race")
    total = readonly_cur.fetchone()[0]
    readonly_cur.execute("SELECT count(*) FROM n_race WHERE jyocd BETWEEN '01' AND '10'")
    jra_only = readonly_cur.fetchone()[0]
    assert jra_only <= total, "JRA 絞り込みは全体以下のはず"
    assert jra_only > 0, "JRA データが存在する"


def test_verdict_logic_all_block_pass() -> None:
    """全 BLOCK check が passed の場合、verdict=="pass"。"""

    cur = _mock_cursor(
        {
            "20150101": (39593,),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum))": (40035, 40035),
            "count(DISTINCT (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum))": (
                1000000,
                1000000,
            ),
            "information_schema.tables": (1,),
            "FFFD": (0,),
            "NOT IN": (0,),
            "FROM n_race WHERE jyocd BETWEEN": (40035,),
        }
    )

    result = run_quality_gate(cur)
    assert result["verdict"] == "pass"
    assert isinstance(result["checks"], list)
    assert all(set(c.keys()) <= {"name", "passed", "severity", "detail"} for c in result["checks"])


# ---------------------------------------------------------------------------
# contract: 個別 helper の smoke test（モックで ok/no を分離）
# ---------------------------------------------------------------------------


def test__check_table_exists_present() -> None:
    cur = _mock_cursor({"information_schema.tables": (1,)})
    r = _check_table_exists(cur, "n_race")
    assert r.passed is True
    assert r.severity == "block"


def test__check_table_exists_absent() -> None:
    cur = _mock_cursor({"information_schema.tables": (0,)})
    r = _check_table_exists(cur, "n_hoge")
    assert r.passed is False
    assert r.severity == "block"


def test__check_n_uma_race_natural_key_unique_pass() -> None:
    cur = _mock_cursor(
        {"count(DISTINCT (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum))": (100, 100)}
    )
    r = _check_n_uma_race_natural_key_unique(cur)
    assert r.passed is True
