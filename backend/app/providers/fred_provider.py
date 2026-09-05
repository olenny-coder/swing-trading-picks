"""FRED (Federal Reserve Economic Data) adapter for interest rates & VIX."""
from __future__ import annotations

from datetime import date

import httpx

from .base import EarningsData, MacroDataProvider, MacroEventData, MacroSnapshotData

_BASE = "https://api.stlouisfed.org/fred/series/observations"


class FredMacroProvider(MacroDataProvider):
    name = "fred"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._http: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=25.0)
        return self._http

    def _latest(self, series_id: str) -> float | None:
        resp = self.client.get(
            _BASE,
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 20,
            },
        )
        if resp.status_code in (400, 401, 403):
            raise RuntimeError("Invalid FRED API key")
        resp.raise_for_status()
        for obs in resp.json().get("observations", []):
            if obs.get("value") not in (None, "."):
                try:
                    return float(obs["value"])
                except (TypeError, ValueError):
                    continue
        return None

    def test_connection(self) -> tuple[bool, str, dict | None]:
        try:
            yield_10y = self._latest("DGS10")
            return True, "Connected to FRED.", {"DGS10": yield_10y}
        except Exception as exc:
            return False, str(exc), None

    def get_economic_calendar(self, start: date, end: date) -> list[MacroEventData]:
        return []

    def get_earnings_calendar(self, tickers: list[str], start: date, end: date) -> list[EarningsData]:
        return []

    def get_macro_snapshot(self) -> MacroSnapshotData:
        snapshot = MacroSnapshotData(date=date.today())
        try:
            snapshot.ten_year_yield = self._latest("DGS10")
            snapshot.fed_funds_rate = self._latest("DFF")
            snapshot.vix = self._latest("VIXCLS")
        except Exception:
            pass
        return snapshot
