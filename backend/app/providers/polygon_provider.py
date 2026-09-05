"""Polygon.io adapter — used as an alternative market-data provider and/or
an options-chain fallback when Alpaca options data is unavailable."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from .base import Bar, MarketDataProvider, OptionContract, Quote, UniverseMeta

_BASE = "https://api.polygon.io"


class PolygonMarketDataProvider(MarketDataProvider):
    name = "polygon"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._http: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "apiKey": self.api_key}
        resp = self.client.get(f"{_BASE}{path}", params=params)
        if resp.status_code in (401, 403):
            raise RuntimeError("Invalid Polygon.io API key")
        resp.raise_for_status()
        return resp.json()

    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            data = self._get("/v2/aggs/ticker/AAPL/prev", {})
            res = (data.get("results") or [{}])[0]
            return True, "Connected to Polygon.io.", {"AAPL close": res.get("c")}
        except Exception as exc:
            return False, str(exc), None

    def get_universe(self, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
        try:
            data = self._get(
                "/v3/reference/tickers",
                {"market": "stocks", "active": "true", "type": "CS", "limit": 1000, "order": "asc", "sort": "ticker"},
            )
        except Exception:
            return []
        metas = [
            UniverseMeta(
                ticker=r["ticker"],
                name=r.get("name") or r["ticker"],
                sector="Unknown",  # liquidity filter runs during ingestion
            )
            for r in data.get("results", [])
        ]
        return metas

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        data = self._get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        bars: list[Bar] = []
        for r in data.get("results", []):
            bars.append(
                Bar(
                    date=date.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                    open=float(r["o"]),
                    high=float(r["h"]),
                    low=float(r["l"]),
                    close=float(r["c"]),
                    volume=float(r["v"]),
                )
            )
        return bars

    def get_quote(self, ticker: str) -> Quote:
        data = self._get(f"/v2/aggs/ticker/{ticker}/prev", {})
        res = (data.get("results") or [{}])[0]
        price = float(res.get("c") or 0.0)
        return Quote(ticker=ticker, price=price, volume=float(res.get("v") or 0.0))

    def get_options_chain(self, ticker: str, side: str = "put") -> list[OptionContract]:
        try:
            data = self._get(
                "/v3/reference/options/contracts",
                {"underlying_ticker": ticker, "contract_type": side, "expired": "false", "limit": 100},
            )
        except Exception:
            return []
        out: list[OptionContract] = []
        for r in data.get("results", []):
            try:
                expiry = date.fromisoformat(r["expiration_date"])
            except (ValueError, KeyError):
                expiry = None
            out.append(
                OptionContract(
                    symbol=r.get("ticker", ""),
                    strike=float(r.get("strike_price") or 0),
                    type=r.get("contract_type") or side,
                    expiry=expiry,
                )
            )
        return out
