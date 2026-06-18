-- Keiba AI v3 — 5層 PostgreSQL スキーマ DDL + raw read-only 二重保護
-- idempotent。実行は scripts/run_apply_schema.py 経由（ロール名は psycopg.sql.Identifier で quote）
--
-- プレースホルダ（run 側で Identifier 置換）:
--   {reader} = KEIBA_DB_USER   (raw 読取専用ロール・public.n_* と raw_everydb2 に SELECT-only)
--   {etl}    = KEIBA_ETL_DB_USER (normalized 書込ロール・normalized に INSERT/UPDATE/DELETE、raw は SELECT-only)
--
-- 適用順序: CREATE SCHEMA → CREATE ROLE → CREATE VIEW → GRANT → REVOKE

-- =========================================================================
-- 1. CREATE SCHEMA（5層・§12.2 に 1:1）
-- =========================================================================
CREATE SCHEMA IF NOT EXISTS raw_everydb2;
CREATE SCHEMA IF NOT EXISTS normalized;
CREATE SCHEMA IF NOT EXISTS label;
CREATE SCHEMA IF NOT EXISTS prediction;
CREATE SCHEMA IF NOT EXISTS backtest;

-- =========================================================================
-- 2. CREATE ROLE（idempotent・DO ブロックで存在確認）
-- =========================================================================
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

-- =========================================================================
-- 3. CREATE OR REPLACE VIEW: raw_everydb2.<t> AS SELECT * FROM public.<t>
--    主な5系統（n_race / n_uma_race / n_harai / n_hyosu / n_odds_tanpuku）。
--    実DB確認（2026-06-17）: n_odds_fukusho は存在せず、複勝オッズは
--    n_odds_tanpuku（単複共用）に含まれるため fukusho VIEW は作らない。
-- =========================================================================
CREATE OR REPLACE VIEW raw_everydb2.n_race AS SELECT * FROM public.n_race;
CREATE OR REPLACE VIEW raw_everydb2.n_uma_race AS SELECT * FROM public.n_uma_race;
CREATE OR REPLACE VIEW raw_everydb2.n_harai AS SELECT * FROM public.n_harai;
CREATE OR REPLACE VIEW raw_everydb2.n_hyosu AS SELECT * FROM public.n_hyosu;
CREATE OR REPLACE VIEW raw_everydb2.n_odds_tanpuku AS SELECT * FROM public.n_odds_tanpuku;

-- =========================================================================
-- 4. GRANT — raw 読取ロール（{reader}）
-- =========================================================================
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

-- =========================================================================
-- 5. GRANT — ETL 書込ロール（{etl}）: normalized に INSERT/UPDATE/DELETE、raw は SELECT-only（HIGH #6）
-- =========================================================================
GRANT USAGE ON SCHEMA public TO {etl};
GRANT USAGE ON SCHEMA raw_everydb2 TO {etl};
-- ETL は staging-table-swap で normalized に CREATE するため CREATE 権限も付与
-- (plan 01-03 HIGH #5 staging-swap が新規 _staging テーブル作成に必要)
GRANT USAGE, CREATE ON SCHEMA normalized TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {etl};
GRANT SELECT ON ALL TABLES IN SCHEMA raw_everydb2 TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA normalized TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA normalized
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
-- Phase 2 label schema: ETL ロールに label スキーマの USAGE+CREATE+書込を付与（Pitfall 6）
-- staging-table-swap idempotent load が新規 _staging テーブル作成に CREATE を必要とする
GRANT USAGE, CREATE ON SCHEMA label TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA label TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA label
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};

-- =========================================================================
-- 6. REVOKE — raw 不変性 二重保護（HIGH #4）
--    物理 public.n_* と raw_everydb2 VIEW の **両方** に対し、reader と etl の両方から
--    UPDATE / DELETE / TRUNCATE を剥奪。物理テーブル直接書込み経路も塞ぐ。
-- =========================================================================
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {reader};
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {etl};

REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM {reader};
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_everydb2 FROM {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2 REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA raw_everydb2 REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM {etl};

-- =========================================================================
-- 注記:
--   ALTER ROLE <etl>/<reader> WITH PASSWORD ... はパスワードを SQL ファイルに書かないため
--   このファイルには含めない。scripts/run_apply_schema.py が psycopg3 のパラメータ化実行で
--   別途設定する（MEDIUM #3・anti-pattern #20）。
-- =========================================================================
