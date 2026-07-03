"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "OffiMesh"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/offimesh",
        description="Async PostgreSQL connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for caching",
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Redis URL for Celery broker",
    )

    # JWT Settings
    jwt_private_key: str = Field(
        default="",
        description="RS256 private key for JWT signing",
    )
    jwt_public_key: str = Field(
        default="",
        description="RS256 public key for JWT verification",
    )
    jwt_algorithm: str = "RS256"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7

    # Nomba API Configuration
    nomba_environment: Literal["sandbox", "production"] = "sandbox"
    nomba_base_url: str = Field(
        default="https://sandbox.api.nomba.com/v1",
        description="Nomba API base URL",
    )
    nomba_account_id: str = Field(
        default="",
        description="Nomba parent account ID",
    )
    nomba_subaccount_id: str = Field(
        default="",
        description="Nomba sub-account ID for transaction scoping",
    )
    nomba_client_id: str = Field(
        default="",
        description="Nomba OAuth client ID",
    )
    nomba_client_secret: str = Field(
        default="",
        description="Nomba OAuth client secret",
    )
    nomba_webhook_secret: str = Field(
        default="",
        description="Secret for verifying Nomba webhook signatures",
    )

    # Offline Token Settings
    offline_token_default_limit_kobo: int = 50_000
    offline_token_max_limit_kobo: int = 500_000
    offline_token_ttl_hours: int = 48
    offline_token_grace_hours: int = 2

    # Transaction Limits
    max_sync_batch_size: int = 100
    max_transaction_amount_kobo: int = 5_000_000

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # CORS
    cors_origins: str = "*"

    # SMS Gateway (for OTP)
    sms_gateway_url: str = ""
    sms_gateway_api_key: str = ""
    sms_gateway_sender_id: str = "OffiMesh"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
