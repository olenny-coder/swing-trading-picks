"""Finnhub macro / earnings calendar adapter (optional provider)."""
from __future__ import annotations

from datetime import date, datetime, time

import httpx

from .base import EarningsData, MacroDataProvider, MacroEventData, MacroSnapshotData

_BASE = "https://finnhub.io/api/v1"

_IMPACT = {"high": "high", "medium": "medium", "low": "low"}

# Event categories where a LOWER reading is market-positive.
_LOWER_IS_GOOD = (
    "inflation", "cpi", "ppi", "pce", "rate", "interest", "unemployment",
    "claims", "deficit", "treasury",
)


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    s = v.strip().replace(",", "").rstrip("%")
    try:
        mult = 1.0
        low = s.lower()
        if low.endswith("k"):
            mult, s = 1e3, s[:-1]
        elif low.endswith("m"):
            mult, s = 1e6, s[:-1]
        elif low.endswith("b"):
            mult, s = 1e9, s[:-1]
        return float(s) * mult
    except ValueError:
        return None


def _sentiment(title: str, estimate: str | None, prev: str | None, actual: str | None) -> str:
    """Derive a market-sentiment label (positive/negative/neutral) from the
    actual-vs-forecast (released) or forecast-vs-previous (upcoming) delta."""
    val = actual if actual else estimate
    ref = estimate if actual else prev
    v, r = _num(val), _num(ref)
    if v is None or r is None or abs(v - r) < 1e-9:
        return "neutral"
    diff = v - r
    lower_good = any(k in title.lower() for k in _LOWER_IS_GOOD)
    positive = diff < 0 if lower_good else diff > 0
    return "positive" if positive else "negative"


class FinnhubMacroProvider(MacroDataProvider):
    name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._http: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "token": self.api_key}
        resp = self.client.get(f"{_BASE}{path}", params=params)
        if resp.status_code in (401, 403):
            raise RuntimeError("Invalid Finnhub API key")
        resp.raise_for_status()
        return resp.json()

    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            data = self._get("/quote", {"symbol": "AAPL"})
            return True, "Connected to Finnhub.", {"price": data.get("c")}
        except Exception as exc:
            return False, str(exc), None

    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        try:
            data = self._get("/calendar/economic", {"from": start.isoformat(), "to": end.isoformat()})
        except Exception:
            return []
        events: list[MacroEventData] = []
        for e in data.get("economicCalendar", []):
            d = e.get("date")
            t = e.get("time") or "08:00:00"
            try:
                hh, mm, ss = (t.split(":") + ["00", "00"])[:3]
                dt = datetime.combine(date.fromisoformat(d), time(int(hh), int(mm), int(ss)))
            except (ValueError, TypeError):
                continue
            events.append(
                MacroEventData(
                    title=e.get("event", "Economic Event"),
                    datetime=dt,
                    importance=_IMPACT.get((e.get("impact") or "low").lower(), "low"),
                    sentiment=_sentiment(
                        e.get("event", ""), e.get("estimate"), e.get("prev"), e.get("actual")
                    ),
                    country=e.get("country") or "US",
                    forecast=e.get("estimate"),
                    previous=e.get("prev"),
                    actual=e.get("actual"),
                    source="finnhub",
                )
            )
        return events

    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        wanted = set(tickers)
        try:
            data = self._get("/calendar/earnings", {"from": start.isoformat(), "to": end.isoformat()})
        except Exception:
            return []
        out: list[EarningsData] = []
        for e in data.get("earningsCalendar", []):
            symbol = e.get("symbol")
            if symbol not in wanted:
                continue
            try:
                d = date.fromisoformat(e.get("date"))
            except (ValueError, TypeError):
                continue
            quarter = f"Q{e.get('quarter') or ''} {e.get('year') or ''}".strip()
            out.append(
                EarningsData(
                    ticker=symbol,
                    report_date=d,
                    fiscal_quarter=quarter or None,
                    eps_estimate=_f(e.get("epsEstimate")),
                    eps_actual=_f(e.get("epsActual")),
                    revenue_estimate=_f(e.get("revenueEstimate")),
                    source="finnhub",
                )
            )
        return out

    def get_macro_snapshot(self) -> MacroSnapshotData:
        # Finnhub does not provide a compact regime/VIX bundle; the macro
        # service fills these from the market provider / other adapters.
        return MacroSnapshotData(date=date.today())


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
