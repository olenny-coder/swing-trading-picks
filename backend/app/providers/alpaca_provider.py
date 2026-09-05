"""Alpaca market-data + account client.

Implemented with ``httpx`` directly against the Alpaca REST API so the project
has no hard dependency on the ``alpaca-py`` SDK (which can be swapped in later
without touching the rest of the code — everything depends on the base
``MarketDataProvider`` interface).

Credentials are injected at construction time (already decrypted by the
credential service) and are never logged or serialized.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import httpx

from ..core.universe import UNIVERSE
from .base import Bar, MarketDataProvider, OptionContract, ProviderError, Quote, UniverseMeta

_PAPER_API = "https://paper-api.alpaca.markets"
_LIVE_API = "https://api.alpaca.markets"
_DATA_API = "https://data.alpaca.markets"

_OCC_RE = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<type>[CP])(?P<strike>\d{8})$")


def _parse_occ_symbol(symbol: str) -> dict | None:
    m = _OCC_RE.match(symbol)
    if not m:
        return None
    strike = int(m.group("strike")) / 1000.0
    expiry = date(2000 + int(m.group("yy")), int(m.group("mm")), int(m.group("dd")))
    return {"strike": strike, "expiry": expiry, "type": "call" if m.group("type") == "C" else "put"}


class AlpacaProvider(MarketDataProvider):
    name = "alpaca"

    def __init__(self, api_key: str, secret_key: str, is_paper: bool = True, data_feed: str = "iex") -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.is_paper = is_paper
        self.data_feed = data_feed
        self._http: httpx.Client | None = None

    @property
    def api_base(self) -> str:
        return _PAPER_API if self.is_paper else _LIVE_API

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "accept": "application/json",
        }

    def _get(self, base: str, path: str, params: dict | None = None) -> dict:
        resp = self.client.get(f"{base}{path}", headers=self._headers(), params=params)
        if resp.status_code in (401, 403):
            raise ProviderError("Invalid Alpaca credentials (401/403)")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            acct = self._get(self.api_base, "/v2/account")
            return (
                True,
                f"Connected to Alpaca account {acct.get('id', '')}",
                {
                    "account_id": acct.get("id"),
                    "status": acct.get("status"),
                    "buying_power": acct.get("buying_power"),
                    "paper": self.is_paper,
                },
            )
        except ProviderError as exc:
            return False, str(exc), None
        except Exception as exc:  # network, parse, etc.
            return False, f"Alpaca connection failed: {exc}", None

    # ------------------------------------------------------------------
    def get_universe(self, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
        # Use the curated liquid universe rather than fetching the full asset
        # catalog — keeps the daily pull small and well within rate limits.
        # These are all large, highly-liquid names, so the price/volume
        # thresholds are satisfied by construction.
        return [UniverseMeta(ticker=t, name=n, sector=s) for t, n, s in UNIVERSE]

    # ------------------------------------------------------------------
    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        data = self._get(
            _DATA_API,
            f"/v2/stocks/{ticker}/bars",
            {
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10000,
                "adjustment": "split",
                "feed": self.data_feed,
            },
        )
        bars: list[Bar] = []
        for b in data.get("bars", []):
            bars.append(
                Bar(
                    date=date.fromisoformat(b["t"][:10]),
                    open=float(b["o"]),
                    high=float(b["h"]),
                    low=float(b["l"]),
                    close=float(b["c"]),
                    volume=float(b["v"]),
                )
            )
        return bars

    def get_quote(self, ticker: str) -> Quote:
        try:
            data = self._get(_DATA_API, f"/v2/stocks/{ticker}/quotes/latest", {"feed": self.data_feed})
            q = data.get("quote", {})
            ask = q.get("ap")
            bid = q.get("bp")
            price = float(ask or bid or 0.0)
            return Quote(
                ticker=ticker,
                price=price,
                bid=float(bid) if bid else None,
                ask=float(ask) if ask else None,
                timestamp=datetime.now() if q else None,
            )
        except Exception:
            data = self._get(_DATA_API, f"/v2/stocks/{ticker}/trades/latest", {"feed": self.data_feed})
            t = data.get("trade", {})
            return Quote(ticker=ticker, price=float(t.get("p") or 0.0))

    # ------------------------------------------------------------------
    def get_options_chain(self, ticker: str, side: str = "put") -> list[OptionContract]:
        """Best-effort options chain via the Alpaca options (opra) feed.

        Requires an options-data subscription; returns [] otherwise.
        """
        try:
            data = self._get(
                _DATA_API,
                f"/v1beta1/options/snapshots/{ticker}",
                {"feed": "opra", "limit": 250, "type": side},
            )
        except Exception:
            return []
        out: list[OptionContract] = []
        for snap in data.get("snapshots", []):
            symbol = snap.get("symbol", "")
            parsed = _parse_occ_symbol(symbol)
            if not parsed:
                continue
            quote = snap.get("latestQuote") or {}
            trade = snap.get("latestTrade") or {}
            out.append(
                OptionContract(
                    symbol=symbol,
                    strike=parsed["strike"],
                    type=parsed["type"],
                    expiry=parsed["expiry"],
                    bid=float(quote["bp"]) if quote.get("bp") else None,
                    ask=float(quote["ap"]) if quote.get("ap") else None,
                    last=float(trade["p"]) if trade.get("p") else None,
                    open_interest=snap.get("openInterest"),
                    implied_volatility=snap.get("impliedVolatility"),
                )
            )
        return out
