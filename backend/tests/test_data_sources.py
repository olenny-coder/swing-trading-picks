"""Market-data request formatting and failure reporting.

These pin the bug that hid itself: intraday bars were requested with a naive
timestamp (``2026-09-01T00:00:00``), which is neither RFC-3339 nor a plain date, so
every intraday call was rejected while daily calls — which send a plain date —
worked. The ingestion then swallowed the rejection and reported "no candles".
"""
import os
import sys
import unittest
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(__import__('tempfile').mkdtemp(), 'ds.db')}"
os.environ["SECRET_KEY"] = "datasource-test-secret-key-longer-than-32-bytes"

from app.providers.alpaca_provider import _rfc3339  # noqa: E402
from app.providers.base import ProviderError  # noqa: E402


class TestAlpacaTimestamps(unittest.TestCase):
    def test_a_naive_datetime_gets_an_explicit_utc_offset(self):
        self.assertEqual(_rfc3339(datetime(2026, 9, 1)), "2026-09-01T00:00:00Z")

    def test_an_aware_datetime_is_normalised_to_utc(self):
        self.assertEqual(
            _rfc3339(datetime(2026, 9, 1, tzinfo=timezone.utc)), "2026-09-01T00:00:00Z"
        )

    def test_a_non_utc_offset_is_converted(self):
        from datetime import timedelta

        plus_two = timezone(timedelta(hours=2))
        self.assertEqual(_rfc3339(datetime(2026, 9, 1, 2, 0, tzinfo=plus_two)), "2026-09-01T00:00:00Z")

    def test_the_result_is_never_a_bare_naive_string(self):
        for stamp in (datetime(2026, 1, 1), datetime(2026, 6, 15, 23, 59)):
            formatted = _rfc3339(stamp)
            self.assertTrue(formatted.endswith("Z"), formatted)
            self.assertIn("T", formatted)

    def test_daily_dates_stay_plain(self):
        # The daily path passes a `date`, which Alpaca accepts as YYYY-MM-DD; the
        # helper is only for the intraday path.
        self.assertEqual(date(2026, 9, 1).isoformat(), "2026-09-01")


class TestIntradayFailureReporting(unittest.TestCase):
    """A total miss must raise, so the refresh reports the cause."""

    def setUp(self):
        from app import database

        database.init_db()
        self.db = database.SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_nothing_loaded_raises_with_the_underlying_error(self):
        from app.services import data_service

        class Broken:
            name = "broken"

            def get_intraday_bars(self, ticker, start, end, interval="4Hour"):
                raise ProviderError("Invalid Alpaca credentials (401/403)")

        with self.assertRaises(ProviderError) as caught:
            data_service.ingest_refinement_bars(
                self.db,
                Broken(),
                ["AAPL"],
                datetime(2026, 9, 1),
                datetime(2026, 10, 1),
            )
        self.assertIn("401", str(caught.exception))

    def test_an_empty_response_raises_too(self):
        from app.services import data_service

        class Empty:
            name = "empty"

            def get_intraday_bars(self, ticker, start, end, interval="4Hour"):
                return []

        with self.assertRaises(ProviderError):
            data_service.ingest_refinement_bars(
                self.db, Empty(), ["AAPL"], datetime(2026, 9, 1), datetime(2026, 10, 1)
            )


class TestDuplicateCandles(unittest.TestCase):
    """One duplicate must not poison the whole refresh.

    The observed failure was a UniqueViolation on the intraday unique constraint
    which left the session in a failed state; every later symbol then reported
    PendingRollbackError, blaming the 4-hour step for a daily-bar problem.
    """

    def setUp(self):
        from app import database

        database.init_db()
        self.db = database.SessionLocal()
        self.today = date.today()

    def tearDown(self):
        self.db.close()

    def _payload(self, ticker, count=20):
        from app.providers.mock_provider import MockMarketDataProvider

        market = MockMarketDataProvider()
        return market.get_intraday_bars(
            ticker,
            datetime.combine(self.today - timedelta(days=30), time.min),
            datetime.combine(self.today, time.max),
        )[:count]

    def test_duplicates_are_collapsed_before_the_insert(self):
        from app.services import data_service

        bars = self._payload("AAPL")

        class Triplicated:
            name = "triplicated"

            def get_intraday_bars_multi(self, tickers, start, end, interval="4Hour"):
                return {"AAPL": bars + bars + bars}

        stored = data_service.ingest_refinement_bars(
            self.db,
            Triplicated(),
            ["AAPL"],
            datetime.combine(self.today - timedelta(days=30), time.min),
            datetime.combine(self.today, time.max),
        )
        self.assertEqual(stored, len(bars))

    def test_a_collision_is_isolated_to_one_symbol(self):
        from app.models import IntradayBar as IntradayBarRow
        from app.services import data_service

        window_start = datetime.combine(self.today - timedelta(days=30), time.min)
        window_end = datetime.combine(self.today, time.max)

        # A row *outside* the delete window that the payload will try to insert again.
        outside = window_start - timedelta(hours=1)
        self.db.add(
            IntradayBarRow(
                ticker="AAPL", interval="4Hour", ts=outside,
                open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
            )
        )
        self.db.commit()

        good = self._payload("MSFT")
        colliding = [
            type(good[0])(
                ts=outside, open=2.0, high=2.0, low=2.0, close=2.0, volume=2.0
            )
        ] + good

        class Mixed:
            name = "mixed"

            def get_intraday_bars_multi(self, tickers, start, end, interval="4Hour"):
                return {"AAPL": colliding, "MSFT": good}

        stored = data_service.ingest_refinement_bars(
            self.db, Mixed(), ["AAPL", "MSFT"], window_start, window_end
        )
        # MSFT still lands; the session survives and stays usable.
        self.assertGreaterEqual(stored, len(good))
        self.assertGreater(self.db.query(IntradayBarRow).count(), 1)


class TestBatchedRequests(unittest.TestCase):
    """The documented request takes a symbol *list*, so one call serves many names."""

    def test_chunking_covers_everything_exactly_once(self):
        from app.services.data_service import BATCH_SIZE, _chunks

        tickers = [f"T{i}" for i in range(120)]
        chunks = list(_chunks(tickers, 50))
        self.assertEqual([len(c) for c in chunks], [50, 50, 20])
        self.assertEqual(sum(chunks, []), tickers)
        self.assertEqual(BATCH_SIZE, 50)

    def test_multi_payload_is_parsed_per_symbol(self):
        from app.providers.alpaca_provider import _daily_bar, _intraday_bar

        payload = {
            "bars": {
                "AAPL": [
                    {"t": "2026-09-01T04:00:00Z", "o": 100, "h": 105, "l": 99, "c": 104, "v": 1000}
                ],
                "MSFT": [
                    {"t": "2026-09-01T04:00:00Z", "o": 200, "h": 205, "l": 199, "c": 204, "v": 2000}
                ],
            }
        }
        rows = {symbol: [_daily_bar(b) for b in bars] for symbol, bars in payload["bars"].items()}
        self.assertEqual(set(rows), {"AAPL", "MSFT"})
        self.assertEqual(rows["AAPL"][0].date, date(2026, 9, 1))
        self.assertEqual(rows["MSFT"][0].close, 204.0)

        intraday = _intraday_bar(payload["bars"]["AAPL"][0])
        self.assertEqual(intraday.ts, datetime(2026, 9, 1, 4, 0))
        self.assertIsNone(intraday.ts.tzinfo)

    def test_the_batched_symbols_parameter_is_a_list(self):
        """Guard the documented contract: symbol_or_symbols, not one symbol."""
        import inspect

        from app.providers.alpaca_provider import AlpacaProvider

        self.assertTrue(hasattr(AlpacaProvider, "get_daily_bars_multi"))
        signature = inspect.signature(AlpacaProvider.get_daily_bars_multi)
        self.assertIn("tickers", signature.parameters)
        source = inspect.getsource(AlpacaProvider._multi_bars)
        self.assertIn('"symbols": ",".join(tickers)', source)
        self.assertIn("/v2/stocks/bars", source)


if __name__ == "__main__":
    unittest.main()
