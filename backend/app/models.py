"""SQLAlchemy ORM models.

All models are deliberately portable between SQLite (demo/tests) and
PostgreSQL/TimescaleDB (production). Time-series heavy tables are indexed on
``(ticker, date)``; in production the ``daily_bars`` table can be converted to
a TimescaleDB hypertable with the SQL in ``deploy/timescale.sql``.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.constants import (
    SIGNAL_BUY_DOJI_REVERSAL,
    SIGNAL_BUY_STANDARD,
    SIGNAL_PUT,
    SIGNAL_SELL,
    SIGNAL_TYPES,
)
from .database import Base

# Re-export signal type constants (single source of truth: app.core.constants).
__all__ = [
    "SIGNAL_BUY_STANDARD",
    "SIGNAL_BUY_DOJI_REVERSAL",
    "SIGNAL_SELL",
    "SIGNAL_PUT",
    "SIGNAL_TYPES",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    credentials: Mapped[list["ApiCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiCredential(Base):
    """Encrypted-at-rest API credential for a data/execution provider."""

    __tablename__ = "api_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_credential_user_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # alpaca | finnhub | polygon | fred
    key_encrypted: Mapped[str] = mapped_column(Text)  # Fernet token
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)  # alpaca only
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="credentials")


class DailyBar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_bar_ticker_date"),
        Index("ix_bar_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "type", name="uq_signal_ticker_date_type"),
        Index("ix_signal_date_confidence", "date", "confidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)  # signal date
    type: Mapped[str] = mapped_column(String(32), index=True)

    entry: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, index=True)

    price: Mapped[float] = mapped_column(Float)  # reference close at signal time
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Structured payloads
    confidence_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    triggered_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    event_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    option_recommendation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MacroEvent(Base):
    __tablename__ = "macro_events"
    __table_args__ = (Index("ix_macro_event_datetime", "datetime"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    importance: Mapped[str] = mapped_column(String(16), default="medium")  # high | medium | low
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral")  # positive | negative | neutral
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="US")
    forecast: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)


class EarningsEvent(Base):
    __tablename__ = "earnings_events"
    __table_args__ = (
        UniqueConstraint("ticker", "report_date", name="uq_earnings_ticker_date"),
        Index("ix_earnings_report_date", "report_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(16), nullable=True)
    eps_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)


class MacroSnapshot(Base):
    __tablename__ = "macro_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    spy_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    spy_ma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str] = mapped_column(String(16), default="neutral")  # bullish|bearish|neutral
    vix: Mapped[float | None] = mapped_column(Float, nullable=True)
    vix_term_structure: Mapped[float | None] = mapped_column(Float, nullable=True)
    ten_year_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    fed_funds_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_relative_strength: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Position(Base):
    """Paper-trading position tracking (optional feature)."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))  # buy | put
    qty: Mapped[float] = mapped_column(Float, default=1.0)
    entry_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
