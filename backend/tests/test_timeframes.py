"""Timeframe aggregation tests (daily -> weekly -> monthly candles)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.timeframes import (  # noqa: E402
    DAILY,
    MIN_BARS_BY_TIMEFRAME,
    MONTHLY,
    TIMEFRAMES,
    WEEKLY,
    is_complete_period,
    min_bars,
    normalise,
    resample,
)
from app.providers.base import Bar  # noqa: E402


def _bar(day: date, o: float, h: float, l: float, c: float, v: float = 1_000.0) -> Bar:
    return Bar(date=day, open=o, high=h, low=l, close=c, volume=v)


def _week(start: date, prices: list[float]) -> list[Bar]:
    """Five consecutive sessions beginning on ``start`` (a Monday)."""
    return [_bar(start + timedelta(days=i), p, p + 1, p - 1, p + 0.5) for i, p in enumerate(prices)]


MONDAY = date(2026, 3, 2)   # a Monday
NEXT_MONDAY = MONDAY + timedelta(days=7)


class TestResample(unittest.TestCase):
    def test_daily_returns_the_original_series(self):
        bars = _week(MONDAY, [10, 11, 12, 13, 14])
        self.assertEqual(resample(bars, DAILY), bars)

    def test_unknown_timeframe_falls_back_to_daily(self):
        bars = _week(MONDAY, [10, 11, 12, 13, 14])
        self.assertEqual(resample(bars, "FORTNIGHTLY"), bars)

    def test_weekly_aggregates_open_high_low_close_and_volume(self):
        bars = _week(MONDAY, [10, 11, 12, 13, 14])
        weekly = resample(bars, WEEKLY)
        self.assertEqual(len(weekly), 1)
        candle = weekly[0]
        self.assertEqual(candle.open, bars[0].open)
        self.assertEqual(candle.high, max(b.high for b in bars))
        self.assertEqual(candle.low, min(b.low for b in bars))
        self.assertEqual(candle.close, bars[-1].close)
        self.assertEqual(candle.volume, sum(b.volume for b in bars))

    def test_weekly_candle_is_stamped_with_its_last_session(self):
        bars = _week(MONDAY, [10, 11, 12, 13, 14])  # Mon..Fri
        self.assertEqual(resample(bars, WEEKLY)[0].date, MONDAY + timedelta(days=4))

    def test_an_incomplete_week_is_not_analysed(self):
        # Monday..Wednesday only: the week has not finished.
        bars = _week(MONDAY, [10, 11, 12])
        self.assertEqual(resample(bars, WEEKLY), [])
        # ...unless explicitly asked for.
        self.assertEqual(len(resample(bars, WEEKLY, drop_incomplete=False)), 1)

    def test_monthly_aggregates_a_calendar_month(self):
        # Ends on 31 January, so the month counts as complete.
        bars = [_bar(date(2026, 1, d), d, d + 1, d - 1, d + 0.5) for d in (2, 15, 31)]
        monthly = resample(bars, MONTHLY)
        self.assertEqual(len(monthly), 1)
        candle = monthly[0]
        self.assertEqual(candle.open, bars[0].open)
        self.assertEqual(candle.close, bars[-1].close)
        self.assertEqual(candle.high, max(b.high for b in bars))
        self.assertEqual(candle.low, min(b.low for b in bars))
        self.assertEqual(candle.date, date(2026, 1, 31))

    def test_incomplete_month_is_dropped(self):
        # Ends mid-month: the next day is still January.
        bars = [_bar(date(2026, 1, d), d, d + 1, d - 1, d) for d in (2, 15, 20)]
        self.assertEqual(resample(bars, MONTHLY), [])

    def test_consecutive_weeks_produce_separate_candles(self):
        bars = _week(MONDAY, [10, 11, 12, 13, 14]) + _week(NEXT_MONDAY, [20, 21, 22, 23, 24])
        weekly = resample(bars, WEEKLY)
        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly[0].close, bars[4].close)
        self.assertEqual(weekly[1].close, bars[9].close)
        self.assertEqual(weekly[0].date, MONDAY + timedelta(days=4))
        self.assertEqual(weekly[1].date, NEXT_MONDAY + timedelta(days=4))

    def test_empty_input_is_safe(self):
        self.assertEqual(resample([], WEEKLY), [])
        self.assertEqual(resample([], MONTHLY), [])


class TestTimeframeMetadata(unittest.TestCase):
    def test_normalise_is_case_insensitive_and_defaults_to_daily(self):
        self.assertEqual(normalise("weekly"), WEEKLY)
        self.assertEqual(normalise(" Monthly "), MONTHLY)
        self.assertEqual(normalise("nonsense"), DAILY)
        self.assertEqual(normalise(None), DAILY)

    def test_every_timeframe_has_a_minimum_and_lookback(self):
        for timeframe in TIMEFRAMES:
            self.assertGreaterEqual(min_bars(timeframe), 55)
            self.assertGreaterEqual(MIN_BARS_BY_TIMEFRAME[timeframe], 55)

    def test_monthly_needs_the_most_history(self):
        from app.core.timeframes import lookback_days

        self.assertGreater(lookback_days(MONTHLY), lookback_days(WEEKLY))
        self.assertGreater(lookback_days(WEEKLY), lookback_days(DAILY))

    def test_period_completeness(self):
        friday = date(2026, 3, 6)
        thursday = date(2026, 3, 5)
        self.assertTrue(is_complete_period(friday, WEEKLY))
        self.assertFalse(is_complete_period(thursday, WEEKLY))
        self.assertTrue(is_complete_period(date(2026, 1, 31), MONTHLY))
        self.assertFalse(is_complete_period(date(2026, 1, 15), MONTHLY))
        self.assertTrue(is_complete_period(thursday, DAILY))


if __name__ == "__main__":
    unittest.main()
