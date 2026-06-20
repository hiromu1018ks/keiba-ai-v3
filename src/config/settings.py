"""Keiba AI v3 DB 接続設定（pydantic-settings BaseSettings・2ロール対応）。

`.env`（gitignore 対象）から KEIBA_ prefix 付き環境変数を読込、以下の2ロールを扱う:
  - raw 読取専用ロール（KEIBA_DB_USER / KEIBA_DB_PASSWORD）→ Settings.dsn / Settings.dsn_masked
  - normalized 書込ロール（KEIBA_ETL_DB_USER / KEIBA_ETL_DB_PASSWORD）→ Settings.etl_dsn /
    Settings.etl_dsn_masked（REVIEWS HIGH #6）

ログ出力ルール（REVIEWS MEDIUM #1 / T-01-01 / ASVS V8 Information Disclosure）:
  - Settings.dsn / Settings.etl_dsn は生パスワードを含むため **ログ出力厳禁**
  - ログ出力可能なのは Settings.dsn_masked / Settings.etl_dsn_masked のみ（パスワード=***）
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keiba AI v3 の DB 接続設定。

    `.env` から KEIBA_ prefix 付きで読込。機密値（db_password / etl_db_password）は
    SecretStr で保持し、repr/str でマスクされる（anti-pattern #20 / ASVS V8）。
    """

    model_config = SettingsConfigDict(
        env_prefix="KEIBA_",
        env_file=".env",
        extra="ignore",
    )

    # === raw 読取ロール（public.n_* と raw_everydb2 に SELECT-only） ===
    db_name: str
    db_user: str
    db_password: SecretStr
    db_host: str = "localhost"
    db_port: int = 5432
    db_schema_raw: str = "public"
    db_schema_normalized: str = "normalized"
    # Phase 2 label schema（db_schema_raw / db_schema_normalized と対称）
    db_schema_label: str = "label"
    # Phase 4 prediction schema（D-05・db_schema_label と対称）
    # src/db/prediction_load.py の staging-swap idempotent load が
    # prediction.fukusho_prediction を schema 修飾で書込む（MEDIUM#2: search_path 暗黙解決不可）
    db_schema_prediction: str = "prediction"
    # Phase 5 backtest schema（BACK-03・db_schema_prediction と対称）
    # src/db/backtest_load.py の backtest_id scoped staging-swap idempotent load が
    # backtest.fukusho_backtest を schema 修飾で書込む（RESEARCH §7.3・Pitfall A5）
    db_schema_backtest: str = "backtest"
    # REVIEWS HIGH #3 支援: Plan 03 _idempotent_load_label が staging RENAME 後に
    # GRANT SELECT ON label.fukusho_label TO {reader_role} を発行する際のロール名。
    # TO PUBLIC ではなく明示的 reader ロール付与をコード上でも保証。
    # デフォルト値は .env の KEIBA_DB_USER と一致すること（本プロジェクトでは keiba_readonly）。
    db_reader_role: str = "keiba_readonly"

    # === normalized 書込ロール（REVIEWS HIGH #6） ===
    etl_db_user: str
    etl_db_password: SecretStr

    # ------------------------------------------------------------------
    # DSN（psycopg3 接続専用・ログ出力厳禁）
    # ------------------------------------------------------------------
    @property
    def dsn(self) -> str:
        """raw 読取ロールの DSN（生パスワードを含む・ログ出力厳禁）。

        psycopg3 の connect() / ConnectionPool(conninfo=...) にのみ渡すこと。
        ログには必ず ``dsn_masked`` を使用すること（anti-pattern #20 / ASVS V8）。
        """
        pw = self.db_password.get_secret_value()
        return f"postgresql://{self.db_user}:{pw}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def etl_dsn(self) -> str:
        """normalized 書込ロールの DSN（生パスワードを含む・ログ出力厳禁・HIGH #6）。"""
        pw = self.etl_db_password.get_secret_value()
        return f"postgresql://{self.etl_db_user}:{pw}@{self.db_host}:{self.db_port}/{self.db_name}"

    # ------------------------------------------------------------------
    # masked DSN（ログ出力可能）
    # ------------------------------------------------------------------
    @property
    def dsn_masked(self) -> str:
        """パスワードを ``***`` でマスクした raw 読取ロール DSN（ログ出力用・MEDIUM #1）。"""
        return f"postgresql://{self.db_user}:***@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def etl_dsn_masked(self) -> str:
        """パスワードを ``***`` でマスクした ETL ロール DSN（ログ出力用・MEDIUM #1 / HIGH #6）。"""
        return f"postgresql://{self.etl_db_user}:***@{self.db_host}:{self.db_port}/{self.db_name}"
