"""Alpaca market-data + account client.

Implemented with ``httpx`` directly against the Alpaca REST API so the project
has no hard dependency on the ``alpaca-py`` SDK (which can be swapped in later
without touching the rest of the code — everything depends on the base
``MarketDataProvider`` interface).

Credentials are injected at construction time (already decrypted by the
credential service) and are never logged or serialized.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from ..core.universe import UNIVERSE
from .base import Bar, IntradayBar, MarketDataProvider, ProviderError, Quote, UniverseMeta

_PAPER_API = "https://paper-api.alpaca.markets"
_LIVE_API = "https://api.alpaca.markets"
_DATA_API = "https://data.alpaca.markets"


def _daily_bar(row: dict) -> Bar:
    """Parse one daily bar from an Alpaca payload."""
    return Bar(
        date=date.fromisoformat(row["t"][:10]),
        open=float(row["o"]),
        high=float(row["h"]),
        low=float(row["l"]),
        close=float(row["c"]),
        volume=float(row["v"]),
    )


def _intraday_bar(row: dict) -> IntradayBar:
    """Parse one intraday bar, dropping the trailing Z so it stays naive UTC."""
    stamp = row["t"]
    if stamp.endswith("Z"):
        stamp = stamp[:-1]
    return IntradayBar(
        ts=datetime.fromisoformat(stamp),
        open=float(row["o"]),
        high=float(row["h"]),
        low=float(row["l"]),
        close=float(row["c"]),
        volume=float(row["v"]),
    )


def _rfc3339(stamp: datetime) -> str:
    """Format a timestamp the way Alpaca's bars endpoint requires.

    Alpaca accepts RFC-3339 with an explicit offset (``...T00:00:00Z``) or a bare
    ``YYYY-MM-DD``. A naive ``datetime.isoformat()`` produces ``...T00:00:00``,
    which is neither — and the request is rejected. That is why daily bars worked
    while every intraday request silently came back empty.
    """
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        stamp = stamp.astimezone(timezone.utc)
    return stamp.isoformat().replace("+00:00", "Z")


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
            bars.append(_daily_bar(b))
        return bars

    # -- batched endpoints ---------------------------------------------
    # ``StockBarsRequest`` takes ``symbol_or_symbols``, so the documented way to
    # pull a whole universe is ONE request carrying a symbol list. Fetching a name
    # at a time works, but it turns 114 symbols into 114 round trips per timeframe,
    # which is slow and needlessly rate-limit-hungry.
    def _multi_bars(
        self, tickers: list[str], start: str, end: str, timeframe: str
    ) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        token: str | None = None
        for _ in range(4):
            params = {
                "symbols": ",".join(tickers),
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": 10000,
                "adjustment": "split",
                "feed": self.data_feed,
            }
            if token:
                params["page_token"] = token
            data = self._get(_DATA_API, "/v2/stocks/bars", params)
            for symbol, rows in (data.get("bars") or {}).items():
                out.setdefault(symbol.upper(), []).extend(rows)
            token = data.get("next_page_token")
            if not token:
                break
        return out

    def get_daily_bars_multi(
        self, tickers: list[str], start: date, end: date
    ) -> dict[str, list[Bar]]:
        """Daily candles for many symbols in one request."""
        payload = self._multi_bars(tickers, start.isoformat(), end.isoformat(), "1Day")
        return {symbol: [_daily_bar(b) for b in rows] for symbol, rows in payload.items()}

    def get_intraday_bars_multi(
        self, tickers: list[str], start: datetime, end: datetime, interval: str = "4Hour"
    ) -> dict[str, list[IntradayBar]]:
        """Intraday candles for many symbols in one request.

        A refused timeframe falls back to hourly and is aggregated per symbol, the
        same contract as the single-symbol call.
        """
        try:
            payload = self._multi_bars(tickers, _rfc3339(start), _rfc3339(end), interval)
        except Exception as exc:
            if interval == "1Hour":
                raise
            try:
                payload = self._multi_bars(tickers, _rfc3339(start), _rfc3339(end), "1Hour")
            except Exception:
                raise exc
            from ..core.intraday import resample_intraday

            return {
                symbol: resample_intraday([_intraday_bar(b) for b in rows])
                for symbol, rows in payload.items()
            }
        return {symbol: [_intraday_bar(b) for b in rows] for symbol, rows in payload.items()}

    def get_snapshot(self, ticker: str) -> dict | None:
        """Latest trade, quote and daily bar for one symbol.

        ``/v2/stocks/{symbol}/snapshot`` returns ``latestTrade``, ``latestQuote``,
        ``minuteBar``, ``dailyBar`` and ``prevDailyBar``. Only the price context is
        surfaced: the strategy reads closed candles, so this is display data.
        """
        try:
            data = self._get(
                _DATA_API, f"/v2/stocks/{ticker}/snapshot", {"feed": self.data_feed}
            )
        except Exception:
            return None

        trade = data.get("latestTrade") or {}
        daily = data.get("dailyBar") or {}
        previous = data.get("prevDailyBar") or {}

        price = trade.get("p") or daily.get("c")
        if price is None:
            return None
        price = float(price)

        prev_close = previous.get("c")
        change_pct = None
        if prev_close:
            change_pct = round((price - float(prev_close)) / float(prev_close) * 100, 2)

        return {
            "price": round(price, 2),
            "change_pct": change_pct,
            "as_of": trade.get("t") or daily.get("t"),
            "session_open": round(float(daily["o"]), 2) if daily.get("o") else None,
            "session_high": round(float(daily["h"]), 2) if daily.get("h") else None,
            "session_low": round(float(daily["l"]), 2) if daily.get("l") else None,
            "prev_close": round(float(prev_close), 2) if prev_close else None,
            "feed": self.data_feed,
        }

    def get_intraday_bars(
        self, ticker: str, start: datetime, end: datetime, interval: str = "4Hour"
    ) -> list[IntradayBar]:
        """Candles at ``interval`` for the refinement chart.

        Alpaca accepts an ``amount + unit`` timeframe, so ``4Hour`` is a
        first-class interval — no need to aggregate hourly bars ourselves. If that
        request is refused (an unsupported timeframe, or a plan that will not serve
        it), hourly bars are fetched and aggregated instead. Only when **both** fail
        is the original error raised, so the caller still learns the real reason.
        """
        try:
            bars = self._intraday(ticker, start, end, interval)
        except Exception as exc:
            if interval == "1Hour":
                raise
            first_error: Exception = exc
        else:
            if bars or interval == "1Hour":
                return bars
            first_error = ProviderError(f"no candles returned for {interval}")

        try:
            hourly = self._intraday(ticker, start, end, "1Hour")
        except Exception:
            raise first_error

        if not hourly:
            raise first_error
        if interval == "4Hour":
            from ..core.intraday import resample_intraday

            return resample_intraday(hourly)
        return hourly

    def _intraday(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> list[IntradayBar]:
        bars: list[IntradayBar] = []
        token: str | None = None
        # Alpaca caps a page at 10,000 bars; two pages covers a long window.
        for _ in range(2):
            params = {
                "timeframe": interval,
                "start": _rfc3339(start),
                "end": _rfc3339(end),
                "limit": 10000,
                "adjustment": "split",
                "feed": self.data_feed,
            }
            if token:
                params["page_token"] = token
            # Errors propagate: the caller records them and the refresh reports
            # them, instead of reporting "no candles" and hiding the cause.
            data = self._get(_DATA_API, f"/v2/stocks/{ticker}/bars", params)
            for b in data.get("bars", []):
                stamp = b["t"]
                if stamp.endswith("Z"):
                    stamp = stamp[:-1]
                bars.append(
                    IntradayBar(
                        ts=datetime.fromisoformat(stamp),
                        open=float(b["o"]),
                        high=float(b["h"]),
                        low=float(b["l"]),
                        close=float(b["c"]),
                        volume=float(b["v"]),
                    )
                )
            token = data.get("next_page_token")
            if not token or len(data.get("bars", [])) < 10000:
                break
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
