"""Yahoo Finance providers.

``YahooMacroProvider`` fetches a real macro snapshot (SPY vs 200-day MA, VIX,
10-year Treasury yield, sector-ETF relative strength) from Yahoo's public chart
API using httpx — no API key and no third-party dependency (this is the same
source the ``yfinance`` library wraps).

``YahooFuturesProvider`` uses the same endpoint to supply daily bars for the
index futures in ``core.universe.FUTURES``, which the equity providers do not
carry. Every fetch degrades gracefully: if a symbol fails the field is left empty
for the composite provider (FRED/mock) to fill, and if Yahoo is unreachable the
futures are simply absent rather than failing a refresh.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx

from ..core.constants import SECTOR_ETFS
from ..core.regime import classify_regime, sector_relative_strength
from ..core.universe import (
    FUTURES,
    FUTURES_NAME_BY_TICKER,
    FUTURES_SECTOR_BY_TICKER,
    YAHOO_SYMBOL_BY_FUTURE,
)
from .base import (
    Bar,
    EarningsData,
    MacroDataProvider,
    MacroEventData,
    MacroSnapshotData,
    MarketDataProvider,
    Quote,
    UniverseMeta,
)

_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _chart(symbol: str, range_: str, client: httpx.Client) -> dict:
    resp = client.get(
        f"{_BASE}/{symbol}", params={"range": range_, "interval": "1d"}, headers=_HEADERS, timeout=25.0
    )
    resp.raise_for_status()
    return resp.json()["chart"]["result"][0]


def _closes(symbol: str, range_: str, client: httpx.Client) -> list[float]:
    result = _chart(symbol, range_, client)
    closes = result["indicators"]["quote"][0]["close"]
    return [float(c) for c in closes if c is not None]


def _bars(symbol: str, range_: str, client: httpx.Client) -> list[Bar]:
    """Full OHLCV daily candles for one Yahoo symbol."""
    result = _chart(symbol, range_, client)
    stamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    # Yahoo stamps each candle in exchange-local time; applying the offset keeps
    # the date on the correct session rather than rolling over in UTC.
    offset = int(result.get("meta", {}).get("gmtoffset") or 0)

    out: list[Bar] = []
    for i in range(len(stamps)):
        if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
            break
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if None in (o, h, l, c):
            continue
        volume = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
        out.append(
            Bar(
                date=datetime.utcfromtimestamp(stamps[i] + offset).date(),
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(volume),
            )
        )
    return out


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


class YahooFuturesProvider(MarketDataProvider):
    """Daily bars for index futures (MES and friends) from Yahoo Finance.

    The equity providers do not carry index futures, and Alpaca's stock feed
    certainly does not, so this small provider exists purely for the instruments
    listed in ``core.universe.FUTURES``. It needs no key, and every call is
    best-effort: an unreachable or unknown symbol returns no bars, which simply
    leaves that instrument out of the universe.
    """

    name = "yahoo-futures"

    def __init__(self) -> None:
        self._http: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            symbol = YAHOO_SYMBOL_BY_FUTURE.get(FUTURES[0][0], "")
            bars = _bars(symbol, "5d", self.client)
            if not bars:
                return False, "Yahoo returned no futures candles.", None
            return (
                True,
                "Connected to Yahoo Finance futures data.",
                {FUTURES[0][0]: bars[-1].close},
            )
        except Exception as exc:  # pragma: no cover - network
            return False, f"Yahoo futures unavailable: {exc}", None

    def get_universe(
        self, min_price: float = 5.0, min_volume: float = 500_000.0
    ) -> list[UniverseMeta]:
        return [
            UniverseMeta(ticker=ticker, name=name, sector=sector)
            for ticker, name, sector in FUTURES
        ]

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        symbol = YAHOO_SYMBOL_BY_FUTURE.get(ticker.upper())
        if not symbol:
            return []
        # Yahoo's chart API takes a range rather than a date window, so ask for
        # whole years covering the request and trim to it.
        years = max(1, min(10, (end - start).days // 365 + 1))
        try:
            bars = _bars(symbol, f"{years}y", self.client)
        except Exception:
            return []
        return [b for b in bars if start <= b.date <= end]

    def get_quote(self, ticker: str) -> Quote:
        end = date.today()
        try:
            bars = self.get_daily_bars(ticker, end - timedelta(days=14), end)
        except Exception:
            bars = []
        if not bars:
            return Quote(ticker=ticker, price=0.0)
        last = bars[-1]
        return Quote(ticker=ticker, price=last.close, volume=last.volume)
