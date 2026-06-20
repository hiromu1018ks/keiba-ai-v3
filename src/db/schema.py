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
CREATE_SCHEMAS_SQL = "\n".join(
    f"CREATE SCHEMA IF NOT EXISTS {schema};" for schema in SCHEMAS
)

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
    "APPLY_ORDER",
]
