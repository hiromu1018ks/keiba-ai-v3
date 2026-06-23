"""5層 PostgreSQL スキーマ DDL と raw read-only 二重保護 SQL 定数（REVIEWS HIGH #4/#6）。

論理層（§12.2 に 1:1）:
  - raw_everydb2  : 物理 public.n_* への VIEW 層（read-only）
  - normalized    : ETL ロール（KEIBA_ETL_DB_USER）が INSERT/UPDATE/DELETE を持つ書込層
  - label, prediction, backtest : 後続 Phase で定義（本 plan では空 SCHEMA のみ）

D-06 二重保護（REVIEWS HIGH #4）:
  KEIBA_DB_USER（raw 読取ロール）に対し、物理 public.n_* と raw_everydb2 VIEW の
  **両方** に REVOKE UPDATE, DELETE, TRUNCATE を発行する。後続 plan は public.n_* を
  直接読むため、VIEW の REVOKE だけでは不十分。

ETL ロール（REVIEWS HIGH #6）:
  KEIBA_ETL_DB_USER に対し normalized スキーマにのみ INSERT/UPDATE/DELETE/TRUNCATE を
  GRANT、public / raw_everydb2 には SELECT-only を GRANT し、念のため UPDATE/DELETE/
  TRUNCATE を REVOKE する。

SQL 文字列内の ``{reader}`` / ``{etl}`` プレースホルダは scripts/run_apply_schema.py が
psycopg.sql.Identifier で安全に置換する（MEDIUM #3）。
"""
# ruff: noqa: E501  (本ファイルは SQL リテラル文字列を定数として保持するため行長は緩和)

from __future__ import annotations

# §12.2 論理層に 1:1 の5層スキーマ
SCHEMAS = ["raw_everydb2", "normalized", "label", "prediction", "backtest"]

# EveryDB2 主要5系統（01-CONTEXT.md D-02 / 01-RESEARCH.md Sources で実測）。
# 実DBでは n_odds_fukusho は存在せず、複勝オッズは n_odds_tanpuku（単勝・複勝共用）に
# 含まれる（JRA の単複は同テーブル）。従って VIEW 対象から n_odds_fukusho は除外。
RAW_VIEW_TABLES = [
    "n_race",
    "n_uma_race",
    "n_harai",
    "n_hyosu",
    "n_odds_tanpuku",
]

# ---------------------------------------------------------------------------
# CREATE SCHEMA（idempotent・5層分）
# ---------------------------------------------------------------------------
CREATE_SCHEMAS_SQL = "\n".join(f"CREATE SCHEMA IF NOT EXISTS {schema};" for schema in SCHEMAS)

# ---------------------------------------------------------------------------
# Phase 4 prediction.fukusho_prediction テーブル DDL（D-05/D-12・review HIGH#1/Cross-Plan #3）
#
# PK は model_type / model_version / feature_snapshot_id / as_of_datetime + 7カラム RACE_KEY
#   (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum) の **11カラム** とする。
#   review HIGH#1: feature_snapshot_id と as_of_datetime を PK に含めない形式では、
#   異 snapshot / 再実行（as_of_datetime が変わる）の provenance 履歴が互いに上書きされ
#   §19.1 再現性聖域（provenance 履歴の不可視化）を破る。PK に含めることで履歴破壊を防止。
#
# 3つの CHECK 制約で不正レコード挿入を DB 側で拒否（review HIGH#1/Cross-Plan #3）:
#   (1) p_fukusho_hit ∈ [0, 1]   — 確率値の範囲
#   (2) model_type IN ('lightgbm','catboost','logreg')  — 既知の model_type のみ
#   (3) calib_method IN ('isotonic','sigmoid')          — 既知の calib_method のみ
#       （将来の未キャリブレーション baseline は別テーブル/別 model_type で扱う・Cycle 3 NEW-L2）
# ---------------------------------------------------------------------------
PREDICTION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction (
    -- provenance（§19.1 再現性・NOT NULL）
    model_type varchar(16) NOT NULL,
    model_version varchar(64) NOT NULL,
    feature_snapshot_id varchar(64) NOT NULL,
    as_of_datetime timestamp NOT NULL,
    calib_method varchar(16) NOT NULL,
    -- PK（label.fukusho_label と同一7カラム RACE_KEY + kettonum = horse_id 原列）
    year int,
    jyocd varchar(2),
    kaiji int,
    nichiji varchar(2),
    racenum int,
    umaban int,
    kettonum int,
    -- 予測値
    p_fukusho_hit double precision NOT NULL,
    -- 補助メタ（Phase 5/6/7 が参照）
    race_date date,
    split varchar(16),
    PRIMARY KEY (model_type, model_version, feature_snapshot_id, as_of_datetime,
                 year, jyocd, kaiji, nichiji, racenum, umaban, kettonum),
    CONSTRAINT prediction_fukusho_hit_range CHECK (p_fukusho_hit >= 0 AND p_fukusho_hit <= 1),
    CONSTRAINT prediction_model_type_domain CHECK (model_type IN ('lightgbm','catboost','logreg')),
    CONSTRAINT prediction_calib_method_domain CHECK (calib_method IN ('isotonic','sigmoid'))
);
COMMENT ON TABLE prediction.fukusho_prediction IS
    'Phase 4 予測結果 (D-05). provenance 列 (model_type/model_version/feature_snapshot_id/'
    'as_of_datetime/calib_method) で §19.1 再現性. staging-swap idempotent load で永続化. '
    'PK は model_type+model_version+feature_snapshot_id+as_of_datetime+RACE_KEY(7) の11カラム: '
    'review HIGH#1 により feature_snapshot_id と as_of_datetime を PK に含める '
    '（異 snapshot/再実行で provenance 履歴を不可視に上書きする §19.1 聖域違反を防止）. '
    '3 CHECK 制約 (p_fukusho_hit ∈ [0,1] / model_type IN (...) / calib_method IN (...)) で '
    '不正レコード挿入を DB 側で拒否 (review HIGH#1/Cross-Plan #3).';
"""

# ---------------------------------------------------------------------------
# Phase 6 Plan 06-04: prediction.fukusho_prediction へ is_primary 列追加 ALTER
# (D-09 / REVIEW HIGH#8: NOT NULL DEFAULT false 明示 / CHECK は NOT NULL の二重防御)
#
# - idempotent ALTER（ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF EXISTS + ADD）
# - boolean NOT NULL DEFAULT false（REVIEW HIGH#8・CHECK 制約 is_primary IN (true,false) は
#   PostgreSQL の boolean 型に対しては NULL 許容を禁止しないvacuous な制約だが・
#   NOT NULL と併用することで「主モデルフラグは true/false いずれか必須」の二重防御として機能。
#   C16 注記: 実質的な NULL 拒否は NOT NULL 制約が担う）
# - GRANT は既存 GRANT_ETL_SQL（lines 248-253）が prediction スキーマの
#   SELECT/INSERT/UPDATE/DELETE/TRUNCATE を etl ロールに付与済・is_primary UPDATE に
#   追加権限不要。reader も SELECT 済（lines 222-224）。
# ---------------------------------------------------------------------------
PREDICTION_ADD_IS_PRIMARY_SQL = """
ALTER TABLE prediction.fukusho_prediction
    ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;
ALTER TABLE prediction.fukusho_prediction
    DROP CONSTRAINT IF EXISTS prediction_is_primary_domain;
ALTER TABLE prediction.fukusho_prediction
    ADD CONSTRAINT prediction_is_primary_domain CHECK (is_primary IN (true, false));
COMMENT ON COLUMN prediction.fukusho_prediction.is_primary IS
    'Phase 6 D-09: 主モデル確定フラグ. 選定モデル=true/未選定=false. '
    'NOT NULL DEFAULT false (REVIEW HIGH#8 明示). '
    'CHECK 制約 prediction_is_primary_domain は NOT NULL の二重防御 (REVIEW C16). '
    'etl ロールで model_type+model_version+feature_snapshot_id+as_of_datetime スコープ UPDATE '
    '(src/db/prediction_load.py::set_primary_model・0 行 UPDATE は RuntimeError post-condition). '
    'GRANT: reader SELECT / etl SELECT+INSERT+UPDATE+DELETE は GRANT_ETL_SQL で既に付与済.';
"""

# ---------------------------------------------------------------------------
# Phase 5 backtest.fukusho_backtest テーブル DDL（BACK-03 / D-03 / §16.2 / §19.1）
#
# PK は backtest_id + 7カラム RACE_KEY (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)
#   の **8カラム** とする。backtest_id を PK 先頭に含めることで同一 backtest_id の行のみが
#   DELETE→INSERT 置換の対象となり・他 backtest_id 行は保持される（review HIGH#1 と同一方針・
#   RESEARCH §7.4）。これにより 20 backtest（2policy × 2model × 5窓）の provenance 履歴が
#   互いに上書きされる silent 履歴破壊を防止する（§19.1 再現性聖域）。
#
# 2つの CHECK 制約で不正レコード挿入を DB 側で拒否:
#   (1) model_type IN ('lightgbm','catboost','bl3')  — BL-3 含む既知の model_type のみ（D-04）
#   (2) backtest_strategy_version = 'fukusho_ev_v1'   — §11.4 戦略バージョン固定
#
# HIGH-1（馬単位永続性）: umaban 列を含む（race_key 単位でなく馬単位の backtest 行）。
# MEDIUM-04（監査性）: odds_missing_reason 列を含む（NULL 可能・normal 候補は NULL・
#   no_bet/special-odds/no-sale/scratch-cancel の各 sentinel 値で埋まる）。
#   load_backtest は selected_flag=True 行だけでなく selected_flag=False の除外候補行も
#   永続化する設計（§11.3 odds_missing_policy=no_bet の監査性担保）。
# ---------------------------------------------------------------------------
BACKTEST_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS backtest.fukusho_backtest (
    -- provenance（§19.1 再現性・NOT NULL）
    backtest_id varchar(64) NOT NULL,
    backtest_strategy_version varchar(32) NOT NULL,
    odds_snapshot_policy varchar(16) NOT NULL,
    train_period_start date NOT NULL,
    train_period_end date NOT NULL,
    test_period_start date NOT NULL,
    test_period_end date NOT NULL,
    model_type varchar(16) NOT NULL,
    model_version varchar(64) NOT NULL,
    feature_snapshot_id varchar(64) NOT NULL,
    -- PK RACE_KEY (7カラム・prediction/label と同一・HIGH-1: umaban 含む馬単位)
    year int,
    jyocd varchar(2),
    kaiji int,
    nichiji varchar(2),
    racenum int,
    umaban int,
    kettonum int,
    -- 選択・会計（MEDIUM-04: selected_flag=False の除外候補行も永続化）
    selected_flag boolean NOT NULL,
    stake int NOT NULL,
    refund_flag boolean NOT NULL,
    refund_amount int NOT NULL,
    payout_amount int NOT NULL,
    profit int NOT NULL,
    effective_stake int NOT NULL,
    -- 的中・rank・EV
    fukusho_hit_validated int,
    recommend_rank varchar(2),
    -- EV_lower/EV_upper は引用符付きで大文字を保持（BACKTEST_COLUMNS / Identifier / DataFrame
    -- 列名と整合させるため・Plan 05-06 Rule 1 fix: PostgreSQL は引用符なし識別子を小文字化するが
    -- ビジネスロジック全般（ev_rank/purchase_simulator/report）が "EV_lower" を使うため DDL 側で保持）
    "EV_lower" double precision,
    "EV_upper" double precision,
    -- odds provenance（§11.2 保持項目・MEDIUM-04: NULL 可能）
    odds_snapshot_at timestamp,
    odds_source_type varchar(16),
    odds_missing_reason varchar(32),
    -- 補助
    race_date date,
    PRIMARY KEY (backtest_id, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum),
    CONSTRAINT backtest_model_type_domain CHECK (model_type IN ('lightgbm','catboost','bl3')),
    CONSTRAINT backtest_strategy_domain CHECK (backtest_strategy_version = 'fukusho_ev_v1')
);
COMMENT ON TABLE backtest.fukusho_backtest IS
    'Phase 5 backtest 結果 (BACK-03). provenance 列 (backtest_id/backtest_strategy_version/'
    'odds_snapshot_policy/train_period_start/end/test_period_start/end/model_type/'
    'model_version/feature_snapshot_id) で §19.1 再現性. backtest_id scoped staging-swap '
    'idempotent load で永続化 (src/db/backtest_load.py). PK は backtest_id+RACE_KEY(7) の8カラム: '
    '同一 backtest_id のみ DELETE→INSERT 置換され・他 backtest_id 行は保持される '
    '(review HIGH#1 と同一方針・RESEARCH §7.4・silent 履歴破壊防止). '
    'umaban 列で馬単位永続化 (HIGH-1). odds_missing_reason 列で no_bet 除外候補の監査性担保 '
    '(MEDIUM-04・selected_flag=False 行も永続化). '
    '2 CHECK 制約 (model_type IN (...) / backtest_strategy_version=''fukusho_ev_v1'') で '
    '不正レコード挿入を DB 側で拒否 (T-05-13).';
"""

# ---------------------------------------------------------------------------
# CREATE VIEW: raw_everydb2.<table> AS SELECT * FROM public.<table>
# idempotent にするため CREATE OR REPLACE VIEW を使用
# ---------------------------------------------------------------------------
CREATE_RAW_VIEWS_SQL = "\n".join(
    f"CREATE OR REPLACE VIEW raw_everydb2.{table} AS SELECT * FROM public.{table};"
    for table in RAW_VIEW_TABLES
)

# ---------------------------------------------------------------------------
# CREATE ROLE: ETL 書込ロール（KEIBA_ETL_DB_USER）と raw 読取ロール
# idempotent を保証するため DO ブロックで存在確認（role は CREATE ROLE IF NOT EXISTS 非対応）
# プレースホルダ {reader} / {etl} は run_apply_schema.py で psycopg.sql.Identifier 置換
# ---------------------------------------------------------------------------
CREATE_ROLES_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {reader_literal}) THEN
        CREATE ROLE {reader} WITH LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {etl_literal}) THEN
        CREATE ROLE {etl} WITH LOGIN;
    END IF;
END
$$;
"""

# ---------------------------------------------------------------------------
# GRANT: raw 読取ロール と ETL ロール に public / raw_everydb2 への SELECT を付与
# ---------------------------------------------------------------------------
GRANT_READER_SQL = """
GRANT USAGE ON SCHEMA public TO {reader};
GRANT USAGE ON SCHEMA raw_everydb2 TO {reader};
GRANT USAGE ON SCHEMA normalized TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA raw_everydb2 TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA normalized TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2 GRANT SELECT ON TABLES TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA normalized GRANT SELECT ON TABLES TO {reader};
-- Phase 2 label schema: reader ロール明示付与（REVIEWS HIGH #3: 汎用ロールへの付与は一切しない）
-- 下流 Phase 3-5 の readonly ロールが label.fukusho_label を schema 修飾 SELECT するため（T-02-03）
GRANT USAGE ON SCHEMA label TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA label TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA label GRANT SELECT ON TABLES TO {reader};
-- Phase 4 prediction schema: reader ロールに prediction スキーマの USAGE+SELECT を付与（D-05）
-- Phase 7 Streamlit が prediction.fukusho_prediction を schema 修飾 SELECT するため（T-04-02）
GRANT USAGE ON SCHEMA prediction TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA prediction TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction GRANT SELECT ON TABLES TO {reader};
-- Phase 5 backtest schema: reader ロールに backtest スキーマの USAGE+SELECT を付与（BACK-03）
-- Phase 7 Streamlit が backtest.fukusho_backtest を schema 修飾 SELECT するため
GRANT USAGE ON SCHEMA backtest TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA backtest TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA backtest GRANT SELECT ON TABLES TO {reader};
"""

GRANT_ETL_SQL = """
GRANT USAGE ON SCHEMA public TO {etl};
GRANT USAGE ON SCHEMA raw_everydb2 TO {etl};
GRANT USAGE, CREATE ON SCHEMA normalized TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA raw_everydb2 TO {etl};
-- normalized スキーマに対する書込権限（HIGH #6）
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA normalized TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA normalized
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
-- Phase 2 label schema: ETL ロールに label スキーマの USAGE+CREATE+書込を付与（Pitfall 6）
-- staging-table-swap idempotent load が新規 _staging テーブル作成に CREATE を必要とする
GRANT USAGE, CREATE ON SCHEMA label TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA label TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA label
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
-- Phase 4 prediction schema: ETL ロールに prediction スキーマの USAGE+CREATE+書込を付与（D-05/D-12）
-- staging-swap idempotent load が prediction.fukusho_prediction_staging 作成に CREATE を必要とする
GRANT USAGE, CREATE ON SCHEMA prediction TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA prediction TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
-- Phase 5 backtest schema: ETL ロールに backtest スキーマの USAGE+CREATE+書込を付与（BACK-03）
-- backtest_id scoped staging-swap idempotent load が backtest.fukusho_backtest_staging 作成に CREATE を必要とする
GRANT USAGE, CREATE ON SCHEMA backtest TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA backtest TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA backtest
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
"""

# ---------------------------------------------------------------------------
# REVOKE: raw 不変性 二重保護（HIGH #4）
# 物理 public.n_* と raw_everydb2 VIEW の **両方** に対し、reader と etl の両方から
# UPDATE / DELETE / TRUNCATE を剥奪
# ---------------------------------------------------------------------------
REVOKE_RAW_WRITES_PUBLIC_SQL = """
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {reader};
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {etl};
"""

REVOKE_RAW_WRITES_VIEW_SQL = """
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM {reader};
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2 REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2 REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {etl};
"""

# ---------------------------------------------------------------------------
# ALTER ROLE PASSWORD: ETL ロールのパスワード設定（HIGH #6）
# パスワードは SQL ファイルに書かず run_apply_schema.py が psycopg3 のパラメータ化で実行
# ここではテンプレート文字列のみ定義（{etl} は Identifier 置換、PASSWORD は run 側で別途）
# ---------------------------------------------------------------------------
ALTER_ETL_PASSWORD_TEMPLATE = "ALTER ROLE {etl} WITH PASSWORD {password};"
ALTER_READER_PASSWORD_TEMPLATE = "ALTER ROLE {reader} WITH PASSWORD {password};"

# ---------------------------------------------------------------------------
# 適用順序: CREATE SCHEMA → CREATE ROLE → CREATE VIEW → GRANT → REVOKE
# apply_schema.sql に吐き出す際の順序
# ---------------------------------------------------------------------------
APPLY_ORDER = [
    ("create_schemas", CREATE_SCHEMAS_SQL),
    ("create_roles", CREATE_ROLES_SQL),
    ("create_raw_views", CREATE_RAW_VIEWS_SQL),
    # Phase 4: prediction_table DDL は GRANT の直前に適用（CREATE SCHEMA で prediction
    # スキーマ自体は既に作成済・GRANT が GRANT SELECT ON ALL TABLES で本テーブルを拾えるように）
    ("prediction_table", PREDICTION_TABLE_DDL),
    # Phase 6 Plan 06-04: is_primary 列追加 ALTER（idempotent・REVIEW HIGH#8 NOT NULL 明示）。
    # prediction_table の直後・backtest_table の前（GRANT が両テーブルを拾うように）。
    ("prediction_add_is_primary", PREDICTION_ADD_IS_PRIMARY_SQL),
    # Phase 5: backtest_table DDL も GRANT の直前に適用（CREATE SCHEMA で backtest
    # スキーマ自体は既に作成済・GRANT が GRANT SELECT ON ALL TABLES で本テーブルを拾えるように）
    ("backtest_table", BACKTEST_TABLE_DDL),
    ("grant_reader", GRANT_READER_SQL),
    ("grant_etl", GRANT_ETL_SQL),
    ("revoke_raw_writes_public", REVOKE_RAW_WRITES_PUBLIC_SQL),
    ("revoke_raw_writes_view", REVOKE_RAW_WRITES_VIEW_SQL),
]


__all__ = [
    "SCHEMAS",
    "RAW_VIEW_TABLES",
    "CREATE_SCHEMAS_SQL",
    "CREATE_RAW_VIEWS_SQL",
    "CREATE_ROLES_SQL",
    "GRANT_READER_SQL",
    "GRANT_ETL_SQL",
    "REVOKE_RAW_WRITES_PUBLIC_SQL",
    "REVOKE_RAW_WRITES_VIEW_SQL",
    "ALTER_ETL_PASSWORD_TEMPLATE",
    "ALTER_READER_PASSWORD_TEMPLATE",
    "PREDICTION_TABLE_DDL",
    "PREDICTION_ADD_IS_PRIMARY_SQL",
    "BACKTEST_TABLE_DDL",
    "APPLY_ORDER",
]
