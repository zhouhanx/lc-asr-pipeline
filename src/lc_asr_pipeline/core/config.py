"""Typed environment configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from psycopg.conninfo import make_conninfo
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_AUTH_SECRET = "development-only-secret-change-before-production-1234"


class Settings(BaseSettings):
    """Application settings loaded from process environment and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "LC ASR Pipeline"
    app_env: str = "development"
    app_debug: bool = False
    app_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    api_prefix: str = "/api/v1"

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: SecretStr
    postgres_database: str

    auth_secret_key: SecretStr = Field(
        default=SecretStr(_DEVELOPMENT_AUTH_SECRET),
        min_length=32,
    )
    auth_access_token_minutes: int = 10
    auth_refresh_token_days: int = 7
    auth_refresh_cookie_name: str = "lc_asr_refresh"
    auth_csrf_cookie_name: str = "lc_asr_csrf"
    admin_login_account_max_failures: int = Field(default=5, ge=2, le=20)
    admin_login_source_max_attempts: int = Field(default=30, ge=5, le=200)
    admin_login_identity_source_max_attempts: int = Field(default=10, ge=3, le=100)
    admin_login_window_seconds: int = Field(default=300, ge=60, le=3600)
    admin_login_lock_seconds: int = Field(default=900, ge=60, le=86400)
    security_hsts_seconds: int = Field(default=31536000, ge=0, le=63072000)
    model_path: Path = Path("/model")
    data_path: Path = Path("data")
    upload_chunk_bytes: int = 8 * 1024 * 1024
    upload_batch_max_bytes: int = 5 * 1024 * 1024 * 1024
    retention_scan_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    retention_orphan_grace_seconds: int = Field(default=86400, ge=300, le=2592000)
    retention_batch_limit: int = Field(default=100, ge=1, le=1000)
    mlx_asr_base_url: str = "http://127.0.0.1:8765"
    mlx_asr_api_key: SecretStr = SecretStr("")
    mlx_asr_model: str = "qwen3-asr-1.7b-mlx-8bit"
    asr_request_timeout_seconds: float = 3600.0
    ocr_request_timeout_seconds: float = 120.0
    ocr_poll_timeout_seconds: float = 1800.0
    text_model_request_timeout_seconds: float = 600.0
    pdf_browser_path: Path | None = None
    migrations_path: Path = Path("migrations")

    @model_validator(mode="after")
    def reject_development_secret_in_production(self) -> Settings:
        if (
            self.app_env.casefold() == "production"
            and self.auth_secret_key.get_secret_value() == _DEVELOPMENT_AUTH_SECRET
        ):
            raise ValueError("AUTH_SECRET_KEY must be replaced in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized, non-empty CORS origins."""
        return [origin.strip() for origin in self.app_cors_origins.split(",") if origin.strip()]

    @property
    def postgres_conninfo(self) -> str:
        """Build a libpq connection string without exposing it in logs."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            user=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            dbname=self.postgres_database,
        )

    @property
    def model_secret_key(self) -> str:
        """Derive model-secret encryption from the server-owned auth root key."""
        return self.auth_secret_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide immutable settings instance."""
    return Settings()  # type: ignore[call-arg]
