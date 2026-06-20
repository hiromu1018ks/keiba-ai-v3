"""``backtest_load.load_backtest`` の統合テスト
（BACK-03 / §19.1 / RESEARCH §7.5 / MEDIUM-04 cycle-2）。

Wave 0 (Plan 05-01): RED stub。``src.db.backtest_load`` 未実装のため ImportError で RED。
Wave 3 (Plan 05-04): GREEN 実装で満たす。

``@pytest.mark.requires_db`` + ``write_cur`` fixture で ``KEIBA_SKIP_DB_TESTS`` skip policy
を継承する（``tests/conftest.py`` 参照）。本 plan では unit test（合成データ）で検証し・
live-DB への CREATE TABLE 適用は後続 Plan 05-06（checkpoint:human-verify）のスコープ。
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_backtest_df(backtest_id: str = "BT-1-30min_before-lightgbm") -> pd.DataFrame:
    """backtest 結果 DataFrame（1行）を構築する。

    BACKTEST_COLUMNS（schema DDL 列順）と 1:1。
    """
    return pd.DataFrame(
        [
            {
                "backtest_id": backtest_id,
                "backtest_strategy_version": "fukusho_ev_v1",
                "odds_snapshot_policy": "30min_before",
                "train_period_start": pd.to_datetime("2019-06-01"),
                "train_period_end": pd.to_datetime("2022-12-31"),
                "test_period_start": pd.to_datetime("2023-01-01"),
                "test_period_end": pd.to_datetime("2023-12-31"),
                "model_type": "lightgbm",
                "model_version": "20260620-1a-postreview-v2-lg-v1",
                "feature_snapshot_id": "20260620-1a-postreview-v2",
                "year": 2023,
                "jyocd": "05",
                "kaiji": 1,
                "nichiji": "06",
                "racenum": 1,
                "umaban": 3,
                "kettonum": 123,
                "selected_flag": True,
                "stake": 100,
                "refund_flag": False,
                "refund_amount": 0,
                "payout_amount": 150,
                "profit": 50,
                "effective_stake": 100,
                "fukusho_hit_validated": 1,
                "recommend_rank": "S",
                "EV_lower": 1.25,
                "EV_upper": 1.60,
                "odds_snapshot_at": pd.to_datetime("2023-01-03 09:30:00"),
                "odds_source_type": "jodds_tanpuku",
                "odds_missing_reason": None,
                "race_date": pd.to_datetime("2023-01-03"),
            }
        ]
    )


# ---------------------------------------------------------------------------
# BACKTEST_COLUMNS contract test（DB 非依存・列順 1:1 検証）
# ---------------------------------------------------------------------------


def test_backtest_load_columns_contract():
    """BACKTEST_COLUMNS が schema DDL 列順と 1:1（DB 非依存・source 検査）。

    schema.py の BACKTEST_TABLE_DDL に現れる列順と backtest_load.BACKTEST_COLUMNS が
    完全一致することを検証する（将来 DDL 変更で誤列挿入防止・Cycle 2 NEW-3 と同一規約）。
    """
    import re

    from src.db.backtest_load import BACKTEST_COLUMNS
    from src.db.schema import BACKTEST_TABLE_DDL

    # DDL テキストから CREATE TABLE ブロックの列定義部分のみを抽出し・列名をパース。
    # PRIMARY KEY / CONSTRAINT / CHECK / COMMENT 行は除外。
    # ``CREATE TABLE ... ( ... );`` の内側を抽出する。
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS \w+\.\w+\s*\((.*?)\);", BACKTEST_TABLE_DDL, re.DOTALL
    )
    assert match is not None, "BACKTEST_TABLE_DDL に CREATE TABLE ブロックが無い"
    inner = match.group(1)

    ddl_cols: list[str] = []
    # 列行は "    colname type ...," の形式。PRIMARY KEY / CONSTRAINT / CHECK はスキップ。
    # 行頭のホワイトスペース + 列名 + 型 (...) ... + 末尾カンマ、の行をパースする。
    for raw_line in inner.splitlines():
        stripped = raw_line.strip().rstrip(",").strip()
        if not stripped:
            continue
        upper = stripped.upper()
        # 制約・COMMENT・PRIMARY KEY は除外
        if upper.startswith(("PRIMARY", "CONSTRAINT", "CHECK", "COMMENT")):
            continue
        # 先頭トークンが列名
        first_token = stripped.split()[0]
        # 列名は SQL identifier（引用符でなければ英数字+アンダースコア）
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", first_token):
            ddl_cols.append(first_token)

    assert ddl_cols == list(BACKTEST_COLUMNS), (
        f"BACKTEST_COLUMNS が DDL 列順と不一致:\n"
        f"  DDL:      {ddl_cols}\n"
        f"  BACKTEST_COLUMNS: {list(BACKTEST_COLUMNS)}"
    )

    # 必須列が含まれることを検証（HIGH-1 umaban + MEDIUM-04 odds_missing_reason）
    assert "umaban" in BACKTEST_COLUMNS, "umaban 列が無い（HIGH-1 馬単位永続性違反）"
    assert "odds_missing_reason" in BACKTEST_COLUMNS, (
        "odds_missing_reason 列が無い（MEDIUM-04 監査性違反）"
    )


def test_backtest_load_empty_raises():
    """空入力 → RuntimeError（CR-04(a) silent data loss 防止・DB 非依存）。

    ``_df_to_backtest_tuples`` が空 DataFrame を渡されると空 list を返すが・
    ``_idempotent_load_backtest`` が空 list を RuntimeError で拒否することを検証する。
    DB 接続不要（advisory lock 取得後に空入力 RuntimeError が raise されるため・
    モック cursor で検証可能）。
    """
    from src.db.backtest_load import _df_to_backtest_tuples, _idempotent_load_backtest

    empty_rows = _df_to_backtest_tuples(pd.DataFrame())
    assert empty_rows == [], "空 DataFrame は空 list になるべき"

    # モック cursor: advisory lock (Step 0) は許容し・それ以降の SQL は発行されない
    # （空入力 RuntimeError が Step 1 で raise されるため）。
    class _NoopCursor:
        def __init__(self) -> None:
            self.lock_acquired = False

        def execute(self, sql, *args, **kwargs):
            sql_str = str(sql)
            if "pg_advisory_xact_lock" in sql_str:
                # Step 0: advisory lock は許容（実 DB ではロック取得）
                self.lock_acquired = True
                return
            # advisory lock 後の SQL が発行された場合・空入力チェックが機能していない
            raise AssertionError(
                f"空入力で advisory lock 以外の SQL が発行された（CR-04(a) 違反）: {sql_str[:80]}"
            )

        def fetchone(self):
            raise AssertionError("空入力で fetchone が呼ばれた")

    with pytest.raises(RuntimeError, match="empty|空入力|silent data loss"):
        _idempotent_load_backtest(_NoopCursor(), empty_rows, reader_role="keiba_readonly")


def test_backtest_load_df_to_tuples_odds_missing_reason_nan_to_none():
    """MEDIUM-04: ``odds_missing_reason`` が NaN の場合は NULL に変換される（DB 非依存）。

    ``_df_to_backtest_tuples`` が ``odds_missing_reason`` 列の NaN を None に変換することを
    検証する（normal 候補は NULL・no_bet/special-odds 等の sentinel 値はそのまま文字列）。
    """
    from src.db.backtest_load import BACKTEST_COLUMNS, _df_to_backtest_tuples

    df = _make_backtest_df()
    # odds_missing_reason が None（NaN 扱い）であることを確認
    rows = _df_to_backtest_tuples(df)
    assert len(rows) == 1
    reason_idx = list(BACKTEST_COLUMNS).index("odds_missing_reason")
    assert rows[0][reason_idx] is None, (
        f"odds_missing_reason が None でない: {rows[0][reason_idx]!r}（MEDIUM-04）"
    )


# ---------------------------------------------------------------------------
# DB 統合テスト（requires_db・KEIBA_SKIP_DB_TESTS skip policy 継承）
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_backtest_schema_apply(write_cur):
    """scripts/run_apply_schema.py 相当の BACKTEST_TABLE_DDL で backtest.fukusho_backtest テーブル
    + GRANT が作成される（requires_db）。

    本テストは ``BACKTEST_TABLE_DDL`` を直接実行してテーブル作成を検証する
    （scripts/run_apply_schema.py の完全適用は Plan 05-06 checkpoint で実施）。
    """
    from src.db.schema import BACKTEST_TABLE_DDL

    # staging クリーンアップ（前回テスト残留防止）
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest_staging")
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest")
    # DDL 実行
    write_cur.execute(BACKTEST_TABLE_DDL)
    # テーブル存在確認
    write_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='backtest' AND table_name='fukusho_backtest' "
        "ORDER BY ordinal_position"
    )
    cols = [r[0] for r in write_cur.fetchall()]
    # 必須列が含まれることを検証
    assert "backtest_id" in cols
    assert "umaban" in cols, "umaban 列が作成されていない（HIGH-1 馬単位永続性違反）"
    assert "odds_missing_reason" in cols, (
        "odds_missing_reason 列が作成されていない（MEDIUM-04 監査性違反）"
    )
    assert "model_type" in cols
    assert "recommend_rank" in cols


@pytest.mark.requires_db
def test_backtest_load_idempotent(write_cur):
    """2回連続実行で checksum が bit-identical（staging-swap idempotent・§19.1）。"""
    from src.db.backtest_load import load_backtest
    from src.db.schema import BACKTEST_TABLE_DDL

    # テーブル準備
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest_staging")
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest")
    write_cur.execute(BACKTEST_TABLE_DDL)

    df = _make_backtest_df()
    checksum1 = load_backtest(write_cur, df)
    checksum2 = load_backtest(write_cur, df)
    # 2回実行でも同一 backtest_id の行数が1行であることを検証（idempotent）
    write_cur.execute(
        "SELECT count(*) FROM backtest.fukusho_backtest WHERE backtest_id = %s",
        ("BT-1-30min_before-lightgbm",),
    )
    count = write_cur.fetchone()[0]
    assert count == 1, f"idempotent 違反: {count} 行（1行期待）"
    # checksum bit-identical
    assert checksum1 == checksum2, (
        f"idempotent checksum 不一致: {checksum1!r} != {checksum2!r}（§19.1 再現性聖域違反）"
    )


@pytest.mark.requires_db
def test_backtest_load_scoped_swap(write_cur):
    """backtest_id A 書込後 B 書込で A が残る（backtest_id scoped swap・他 scope 行は保持）。"""
    from src.db.backtest_load import load_backtest
    from src.db.schema import BACKTEST_TABLE_DDL

    # テーブル準備
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest_staging")
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest")
    write_cur.execute(BACKTEST_TABLE_DDL)

    df_a = _make_backtest_df("BT-1-30min_before-lightgbm")
    df_b = _make_backtest_df("BT-1-30min_before-catboost")
    load_backtest(write_cur, df_a)
    load_backtest(write_cur, df_b)
    # 両方の backtest_id が1行ずつ残っていることを検証
    write_cur.execute(
        "SELECT backtest_id, count(*) FROM backtest.fukusho_backtest "
        "WHERE backtest_id IN (%s, %s) GROUP BY backtest_id",
        ("BT-1-30min_before-lightgbm", "BT-1-30min_before-catboost"),
    )
    rows = dict(write_cur.fetchall())
    assert rows.get("BT-1-30min_before-lightgbm") == 1
    assert rows.get("BT-1-30min_before-catboost") == 1


@pytest.mark.requires_db
def test_backtest_load_carries_odds_missing_reason(write_cur):
    """MEDIUM-04: selected_flag=False の除外候補行も odds_missing_reason 埋めで永続化される。

    no_bet/special-odds 等で除外候補となった行（selected_flag=False）も backtest_id スコープで
    永続化され・odds_missing_reason 列が埋まっていることを検証する（§11.3 odds_missing_policy=
    no_bet の監査性担保・後続監査で除外理由別件数を SQL 集計可能）。
    """
    from src.db.backtest_load import load_backtest
    from src.db.schema import BACKTEST_TABLE_DDL

    # テーブル準備
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest_staging")
    write_cur.execute("DROP TABLE IF EXISTS backtest.fukusho_backtest")
    write_cur.execute(BACKTEST_TABLE_DDL)

    # selected_flag=True の的中行 + selected_flag=False の no_bet 除外候補行
    df_hit = _make_backtest_df("BT-1-30min_before-lightgbm")
    df_no_bet = _make_backtest_df("BT-1-30min_before-lightgbm").assign(
        umaban=7,
        kettonum=456,
        selected_flag=False,
        stake=0,
        refund_flag=False,
        refund_amount=0,
        payout_amount=0,
        profit=0,
        effective_stake=0,
        fukusho_hit_validated=0,
        recommend_rank="D",
        EV_lower=None,
        EV_upper=None,
        odds_missing_reason="no_bet",
    )
    df = pd.concat([df_hit, df_no_bet], ignore_index=True)
    load_backtest(write_cur, df)

    # 両行が永続化されていることを検証
    write_cur.execute(
        "SELECT umaban, selected_flag, odds_missing_reason FROM backtest.fukusho_backtest "
        "WHERE backtest_id = %s ORDER BY umaban",
        ("BT-1-30min_before-lightgbm",),
    )
    rows = write_cur.fetchall()
    assert len(rows) == 2, f"2行期待（hit + no_bet）・actual={len(rows)}行"
    # umaban=3 は selected_flag=True・odds_missing_reason=NULL
    assert rows[0][0] == 3
    assert rows[0][1] is True
    assert rows[0][2] is None
    # umaban=7 は selected_flag=False・odds_missing_reason='no_bet'
    assert rows[1][0] == 7
    assert rows[1][1] is False
    assert rows[1][2] == "no_bet", (
        f"no_bet 除外候補行の odds_missing_reason が 'no_bet' でない: {rows[1][2]!r}（MEDIUM-04）"
    )
