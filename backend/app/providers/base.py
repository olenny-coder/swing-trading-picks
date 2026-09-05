"""Provider contracts and shared data types.

Every external data source (Alpaca, Finnhub, Polygon, FRED, and the built-in
MOCK generator) conforms to these interfaces. The signal engine and ingestion
service depend only on these types, never on a concrete provider, so providers
are fully pluggable and selected at runtime by ``registry``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


class ProviderError(Exception):
    """Raised when an external provider call fails or credentials are invalid."""


@dataclass
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Quote:
    ticker: str
    price: float
    volume: float = 0.0
    bid: float | None = None
    ask: float | None = None
    timestamp: datetime | None = None


@dataclass
class UniverseMeta:
    ticker: str
    name: str
    sector: str
    price: float = 0.0
    avg_volume: float = 0.0


@dataclass
class OptionContract:
    symbol: str
    strike: float
    type: str  # "call" | "put"
    expiry: date | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def spread_pct(self) -> float | None:
        if self.bid is not None and self.ask is not None and self.ask > 0:
            return (self.ask - self.bid) / self.ask * 100
        return None


@dataclass
class MacroEventData:
    title: str
    datetime: datetime
    importance: str = "medium"  # high | medium | low
    sentiment: str = "neutral"  # positive | negative | neutral (market impact)
    category: str | None = None
    country: str = "US"
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    source: str | None = None


@dataclass
class EarningsData:
    ticker: str
    report_date: date
    fiscal_quarter: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    source: str | None = None


@dataclass
class MacroSnapshotData:
    date: date
    regime: str = "neutral"  # bullish | bearish | neutral
    spy_close: float | None = None
    spy_ma200: float | None = None
    vix: float | None = None
    vix_term_structure: float | None = None
    ten_year_yield: float | None = None
    fed_funds_rate: float | None = None
    sector_relative_strength: dict[str, float] = field(default_factory=dict)


class MarketDataProvider(ABC):
    """Market data + execution capabilities (Alpaca, or MOCK for demo)."""

    name: str = "base"

    @abstractmethod
    def test_connection(self) -> tuple[bool, str, dict | None]:
        ...

    @abstractmethod
    def get_universe(self, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
        ...

    @abstractmethod
    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        ...

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        ...

    def get_options_chain(self, ticker: str, side: str = "put") -> list[OptionContract]:
        """Optional; returns [] when unavailable (e.g. no options subscription)."""
        return []


class MacroDataProvider(ABC):
    """Macro / earnings / regime data (Finnhub, Polygon, FRED, or MOCK)."""

    name: str = "base"

    def test_connection(self) -> tuple[bool, str, dict | None]:
        return True, "ok", None

    @abstractmethod
    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        ...

    @abstractmethod
    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        ...

    @abstractmethod
    def get_macro_snapshot(self) -> MacroSnapshotData:
        ...
