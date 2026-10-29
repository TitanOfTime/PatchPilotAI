from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_daily_request_budget: int = 20
    gemini_max_calls_per_analysis: int = 4
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "patchpilot_ai"
    database_user: str = "patchpilot_user"
    database_password: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_remote_write_enabled: bool = False
    local_test_execution_enabled: bool = False
    banking_repository_url: str = "https://github.com/TitanOfTime/TestBankingApp"
    cors_allowed_origins: str = "http://localhost:3000"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def db_url(self):
        return URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @property
    def conninfo(self):
        from psycopg.conninfo import make_conninfo

        return make_conninfo(
            host=self.database_host,
            port=self.database_port,
            dbname=self.database_name,
            user=self.database_user,
            password=self.database_password.get_secret_value(),
        )


@lru_cache
def settings():
    return Settings()


def redact(value: str) -> str:
    for secret in (settings().gemini_api_key, settings().github_token, settings().database_password):
        if secret.get_secret_value():
            value = value.replace(secret.get_secret_value(), "[REDACTED]")
    return value[:30000]
