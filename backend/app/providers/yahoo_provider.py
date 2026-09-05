"""Yahoo Finance macro provider.

Fetches a real macro snapshot (SPY vs 200-day MA, VIX, 10-year Treasury yield,
sector-ETF relative strength) from Yahoo's public chart API using httpx — no API
key and no third-party dependency (this is the same source the ``yfinance``
library wraps). Every fetch degrades gracefully: if a symbol fails, the field is
left empty for the composite provider (FRED/mock) to fill.
"""
from __future__ import annotations

from datetime import date

import httpx

from ..core.constants import SECTOR_ETFS
from ..core.regime import classify_regime, sector_relative_strength
from .base import EarningsData, MacroDataProvider, MacroEventData, MacroSnapshotData

_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _closes(symbol: str, range_: str, client: httpx.Client) -> list[float]:
    resp = client.get(
        f"{_BASE}/{symbol}", params={"range": range_, "interval": "1d"}, headers=_HEADERS, timeout=20.0
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    return [float(c) for c in closes if c is not None]


class YahooMacroProvider(MacroDataProvider):
    name = "yahoo"

    def __init__(self) -> None:
        self._http: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            closes = _closes("SPY", "5d", self.client)
            return True, "Connected to Yahoo Finance.", {"SPY": closes[-1]}
        except Exception as exc:  # pragma: no cover - network
            return False, f"Yahoo Finance unavailable: {exc}", None

    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        return []

    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        return []

    def get_macro_snapshot(self) -> MacroSnapshotData:
        snap = MacroSnapshotData(date=date.today())

        try:
            spy = _closes("SPY", "2y", self.client)
            if spy:
                snap.spy_close = spy[-1]
                if len(spy) >= 200:
                    snap.spy_ma200 = sum(spy[-200:]) / 200.0
        except Exception:
            pass

        try:
            vix = _closes("^VIX", "1mo", self.client)
            if vix:
                snap.vix = vix[-1]
        except Exception:
            pass

        try:
            tnx = _closes("^TNX", "1mo", self.client)
            if tnx:
                # ^TNX is quoted directly in percent (e.g. 4.67 = 4.67%).
                snap.ten_year_yield = tnx[-1]
        except Exception:
            pass

        sector_closes: dict[str, list[float]] = {}
        for etf, name in SECTOR_ETFS.items():
            try:
                closes = _closes(etf, "3mo", self.client)
                if closes:
                    sector_closes[name] = closes
            except Exception:
                continue
        if sector_closes:
            snap.sector_relative_strength = sector_relative_strength(sector_closes)

        snap.regime = classify_regime(snap.spy_close, snap.spy_ma200, snap.vix)
        return snap
