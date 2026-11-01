"""Market-data request formatting and failure reporting.

These pin the bug that hid itself: intraday bars were requested with a naive
timestamp (``2026-09-01T00:00:00``), which is neither RFC-3339 nor a plain date, so
every intraday call was rejected while daily calls — which send a plain date —
worked. The ingestion then swallowed the rejection and reported "no candles".
"""
import os
import sys
import unittest
from datetime import date, datetime, timezone

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


if __name__ == "__main__":
    unittest.main()
