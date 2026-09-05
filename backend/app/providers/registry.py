"""Runtime provider resolution.

Given a dict of *decrypted* credentials (assembled by
``services.credentials``), this module picks concrete providers:

- Market data:  Alpaca -> Polygon -> MOCK, honoring ``DATA_PROVIDER``.
- Macro/event:  Finnhub + FRED (when keys exist) composed with MOCK as a
  deterministic fallback so every feature still works in the demo.
"""
from __future__ import annotations

from datetime import date

from ..config import get_settings
from .alpaca_provider import AlpacaProvider
from .base import (
    EarningsData,
    MacroDataProvider,
    MacroEventData,
    MacroSnapshotData,
    MarketDataProvider,
    ProviderError,
)
from .finnhub_provider import FinnhubMacroProvider
from .fred_provider import FredMacroProvider
from .mock_provider import MockMacroProvider, MockMarketDataProvider
from .polygon_provider import PolygonMarketDataProvider
from .yahoo_provider import YahooMacroProvider


class CompositeMacroProvider(MacroDataProvider):
    """Merges several macro providers: real calendars win, fields are filled
    left-to-right from the first provider that supplies them."""

    name = "composite"

    def __init__(self, providers: list[MacroDataProvider]) -> None:
        self.providers = providers

    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        for p in self.providers:
            events = p.get_economic_calendar(start, end)
            if events:
                return events
        return []

    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        for p in self.providers:
            events = p.get_earnings_calendar(tickers, start, end)
            if events:
                return events
        return []

    def get_macro_snapshot(self) -> MacroSnapshotData:
        snap = MacroSnapshotData(date=date.today())
        for p in self.providers:
            s = p.get_macro_snapshot()
            for field in (
                "spy_close",
                "spy_ma200",
                "vix",
                "vix_term_structure",
                "ten_year_yield",
                "fed_funds_rate",
            ):
                if getattr(snap, field) is None and getattr(s, field) is not None:
                    setattr(snap, field, getattr(s, field))
            if s.regime and s.regime != "neutral":
                snap.regime = s.regime
            if s.sector_relative_strength:
                snap.sector_relative_strength = {
                    **snap.sector_relative_strength,
                    **s.sector_relative_strength,
                }
        return snap


def resolve_market_provider(creds: dict) -> MarketDataProvider:
    settings = get_settings()
    mode = (settings.data_provider or "auto").lower()

    alpaca = creds.get("alpaca") or {}
    polygon = creds.get("polygon") or {}

    if mode == "mock":
        return MockMarketDataProvider()

    if mode == "alpaca":
        if alpaca.get("api_key"):
            return AlpacaProvider(
                alpaca["api_key"],
                alpaca.get("secret_key", ""),
                is_paper=alpaca.get("is_paper", True),
                data_feed=alpaca.get("data_feed", settings.alpaca_data_feed),
            )
        raise ProviderError("Alpaca credentials are required when DATA_PROVIDER=alpaca")

    if mode == "polygon":
        if polygon.get("api_key"):
            return PolygonMarketDataProvider(polygon["api_key"])
        raise ProviderError("Polygon credentials are required when DATA_PROVIDER=polygon")

    # "auto" — prefer Alpaca, then Polygon, then MOCK demo.
    if alpaca.get("api_key"):
        return AlpacaProvider(
            alpaca["api_key"],
            alpaca.get("secret_key", ""),
            is_paper=alpaca.get("is_paper", True),
            data_feed=alpaca.get("data_feed", settings.alpaca_data_feed),
        )
    if polygon.get("api_key"):
        return PolygonMarketDataProvider(polygon["api_key"])
    return MockMarketDataProvider()


def resolve_macro_provider(creds: dict) -> MacroDataProvider:
    providers: list[MacroDataProvider] = []
    finnhub = creds.get("finnhub") or {}
    fred = creds.get("fred") or {}

    # Yahoo Finance first for the real macro snapshot (SPY/VIX/yields/sectors);
    # it supplies no calendars, so those fall through to Finnhub/mock.
    providers.append(YahooMacroProvider())
    if fred.get("api_key"):
        providers.append(FredMacroProvider(fred["api_key"]))
    if finnhub.get("api_key"):
        providers.append(FinnhubMacroProvider(finnhub["api_key"]))
    providers.append(MockMacroProvider())
    return CompositeMacroProvider(providers)
