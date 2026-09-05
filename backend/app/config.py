"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App / security
    app_name: str = "Swing Trading Picks"
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 720

    # Database
    database_url: str = "sqlite:///./swingtrader.db"

    # Data provider: "auto" | "alpaca" | "mock"
    data_provider: str = "auto"

    # Disable the in-process APScheduler (set true on serverless/free-tier hosts
    # where the process isn't always-on; use GitHub Actions cron instead).
    disable_scheduler: bool = False

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"  # iex (free) or sip

    # Optional macro / earnings / options providers
    finnhub_api_key: str = ""
    polygon_api_key: str = ""
    fred_api_key: str = ""

    # Scheduler cron expressions (UTC).
    # 12:30 UTC = 8:30 PM Singapore time (SGT, UTC+8). Ingest first, then macro,
    # then signal generation on the most recent completed US trading day.
    cron_ingest_daily: str = "30 12 * * *"
    cron_generate_signals: str = "40 12 * * *"
    cron_ingest_macro: str = "35 12 * * *"

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # First-run admin bootstrap
    admin_username: str = "admin"
    admin_password: str = "changeme"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
