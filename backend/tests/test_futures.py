"""Index-futures support (MES) and the removal of the options layer.

Futures come from a separate, key-free Yahoo source, so these tests monkeypatch
the HTTP layer rather than touching the network. The contract under test is that
futures are included when their data is available and quietly skipped when it is
not — an equity refresh must never fail because a futures source is down.
"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'futures.db')}"
os.environ["SECRET_KEY"] = "futures-test-secret-key-longer-than-32-bytes-1"

from app.core.universe import (  # noqa: E402
    FUTURES,
    FUTURES_TICKERS,
    YAHOO_SYMBOL_BY_FUTURE,
)
from app.providers import yahoo_provider  # noqa: E402
from app.providers.yahoo_provider import YahooFuturesProvider  # noqa: E402


def _payload(rows: list[tuple[int, float, float, float, float, float]]) -> dict:
    """Shape a Yahoo chart response like the real endpoint does."""
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "MES=F", "gmtoffset": -18000},
                    "timestamp": [r[0] for r in rows],
                    "indicators": {
                        "quote": [
                            {
                                "open": [r[1] for r in rows],
                                "high": [r[2] for r in rows],
                                "low": [r[3] for r in rows],
                                "close": [r[4] for r in rows],
                                "volume": [r[5] for r in rows],
                            }
                        ]
                    },
                }
            ]
        }
    }


# 2026-01-05 12:00 UTC and the following session. Mid-day stamps keep the
# exchange offset (-05:00) from rolling the session date backwards.
_STAMPS = [1767614400, 1767700800]


class TestFuturesDefinitions(unittest.TestCase):
    def test_mes_is_defined_with_a_yahoo_symbol(self):
        self.assertIn("MES", FUTURES_TICKERS)
        self.assertEqual(YAHOO_SYMBOL_BY_FUTURE["MES"], "MES=F")

    def test_mes_is_labelled_as_an_index_future(self):
        name, sector = next((n, s) for t, n, s in FUTURES if t == "MES")
        self.assertIn("Micro E-mini", name)
        self.assertEqual(sector, "Index Futures")


class TestYahooFuturesProvider(unittest.TestCase):
    def setUp(self):
        self.provider = YahooFuturesProvider()

    def test_universe_lists_the_futures(self):
        tickers = [m.ticker for m in self.provider.get_universe()]
        self.assertEqual(tickers, FUTURES_TICKERS)

    def test_bars_are_parsed_from_the_chart_payload(self):
        rows = [
            (_STAMPS[0], 5000.0, 5050.0, 4990.0, 5040.0, 12000.0),
            (_STAMPS[1], 5040.0, 5100.0, 5030.0, 5090.0, 15000.0),
        ]
        original = yahoo_provider._chart
        yahoo_provider._chart = lambda symbol, range_, client: _payload(rows)["chart"]["result"][0]
        try:
            bars = self.provider.get_daily_bars("MES", date(2026, 1, 1), date(2026, 1, 31))
        finally:
            yahoo_provider._chart = original

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].open, 5000.0)
        self.assertEqual(bars[0].high, 5050.0)
        self.assertEqual(bars[0].low, 4990.0)
        self.assertEqual(bars[0].close, 5040.0)
        self.assertEqual(bars[0].volume, 12000.0)
        # The exchange offset is applied, so the date is the session date.
        self.assertEqual(bars[0].date, date(2026, 1, 5))
        self.assertEqual(bars[1].date, date(2026, 1, 6))

    def test_incomplete_candles_are_skipped(self):
        rows = [
            (_STAMPS[0], 5000.0, None, 4990.0, 5040.0, 12000.0),
            (_STAMPS[1], 5040.0, 5100.0, 5030.0, 5090.0, 15000.0),
        ]
        original = yahoo_provider._chart
        yahoo_provider._chart = lambda symbol, range_, client: _payload(rows)["chart"]["result"][0]
        try:
            bars = self.provider.get_daily_bars("MES", date(2026, 1, 1), date(2026, 1, 31))
        finally:
            yahoo_provider._chart = original
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].date, date(2026, 1, 6))

    def test_an_unknown_symbol_yields_no_bars(self):
        self.assertEqual(self.provider.get_daily_bars("NOTAFUTURE", date(2026, 1, 1), date(2026, 1, 31)), [])

    def test_a_network_failure_yields_no_bars(self):
        def boom(symbol, range_, client):
            raise RuntimeError("network down")

        original = yahoo_provider._chart
        yahoo_provider._chart = boom
        try:
            self.assertEqual(
                self.provider.get_daily_bars("MES", date(2026, 1, 1), date(2026, 1, 31)), []
            )
            ok, message, _ = self.provider.test_connection()
            self.assertFalse(ok)
            self.assertIn("unavailable", message.lower())
        finally:
            yahoo_provider._chart = original

    def test_quote_falls_back_to_zero(self):
        quote = self.provider.get_quote("NOTAFUTURE")
        self.assertEqual(quote.price, 0.0)


class TestFuturesUniverseIntegration(unittest.TestCase):
    """Futures join the universe only when their bars are actually stored."""

    def setUp(self):
        from app import database
        from app.models import DailyBar

        database.init_db()
        self.db = database.SessionLocal()
        self.db.query(DailyBar).filter(DailyBar.ticker.in_(FUTURES_TICKERS)).delete(
            synchronize_session=False
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_absent_without_bars(self):
        from app.services.data_service import futures_universe

        self.assertEqual(futures_universe(self.db), [])

    def test_present_once_bars_exist(self):
        from app.models import DailyBar
        from app.services.data_service import futures_universe

        self.db.add(
            DailyBar(
                ticker="MES",
                date=date.today() - timedelta(days=1),
                open=5000,
                high=5050,
                low=4990,
                close=5040,
                volume=12000,
            )
        )
        self.db.commit()

        universe = futures_universe(self.db)
        self.assertEqual([m.ticker for m in universe], ["MES"])
        self.assertEqual(universe[0].sector, "Index Futures")

    def test_ingestion_failure_is_reported_not_raised(self):
        from app.services import data_service

        original = data_service.ingest_bars

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        data_service.ingest_bars = boom
        try:
            result = data_service.ingest_index_futures(
                self.db, date.today() - timedelta(days=30), date.today()
            )
        finally:
            data_service.ingest_bars = original
        self.assertEqual(result["bars"], 0)
        self.assertIn("boom", result["error"])


if __name__ == "__main__":
    unittest.main()
