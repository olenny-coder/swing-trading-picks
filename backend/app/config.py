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

    # Directory holding the exported frontend (built by `npm run build` in
    # frontend/). When present, FastAPI serves the UI at "/" so the app runs as
    # one service (Render + Neon, no Vercel).
    static_dir: str = "static"

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

    # --- LLM research agent (Groq free tier) ---------------------------------
    # Groq's OpenAI-compatible endpoint. Free plan: 30 RPM / 1K RPD and a tight
    # tokens-per-minute budget, so prompts are kept small and calls sequential.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 45.0
    groq_max_retries: int = 2

    # Research agent behaviour
    llm_research_enabled: bool = True
    llm_research_max_signals: int = 20      # per run
    llm_research_max_tokens: int = 700      # completion budget per signal
    llm_max_confidence_delta: float = 15.0  # hard clamp on the LLM's adjustment
    # Pause between per-signal calls; keeps a batch inside Groq's free TPM budget.
    llm_research_pause_seconds: float = 1.0

    # Index futures (MES and friends). Their bars come from Yahoo rather than the
    # equity provider, and are skipped entirely when unavailable.
    index_futures_enabled: bool = True

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

    @property
    def sqlalchemy_database_url(self) -> str:
        """``database_url`` with an explicit, installed PostgreSQL driver.

        Neon and Render hand out bare ``postgresql://`` URLs (Heroku-style
        ``postgres://`` too) with no driver named. SQLAlchemy then picks its own
        default, which varies by version — and fails with
        ``ModuleNotFoundError: No module named 'psycopg'`` when that default is
        psycopg3 (``psycopg``) while only psycopg2 is installed.

        We standardise on psycopg2 so the driver never depends on the installed
        SQLAlchemy version.
        """
        url = (self.database_url or "").strip()
        for prefix in ("postgres://", "postgresql://", "postgresql+psycopg://"):
            if url.startswith(prefix):
                return "postgresql+psycopg2://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
