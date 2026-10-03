"""Analysis timeframes: daily, weekly and monthly.

The setup engine always consumes one chronological series of bars. That series
may be daily bars, or daily bars aggregated into weekly or monthly candles, so
the same rules can be read on a higher timeframe.

Aggregation follows the usual convention: open is the first open of the period,
high and low are the period extremes, close is the last close, volume is the
sum, and the resulting candle carries the date of the period's **last trading
day** so a signal is stamped with the candle it completed.

An in-progress period is never analysed: a weekly setup must be confirmed by a
completed week, and a monthly setup by a completed month.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..providers.base import Bar

DAILY = "DAILY"
WEEKLY = "WEEKLY"
MONTHLY = "MONTHLY"

TIMEFRAMES = (DAILY, WEEKLY, MONTHLY)

TIMEFRAME_LABELS: dict[str, str] = {
    DAILY: "Daily",
    WEEKLY: "Weekly",
    MONTHLY: "Monthly",
}

TIMEFRAME_DESCRIPTIONS: dict[str, str] = {
    DAILY: "One candle per trading day — the fastest signals, the most noise.",
    WEEKLY: "One candle per week — fewer, more durable setups.",
    MONTHLY: "One candle per month — position-trading context.",
}

#: How many bars of each timeframe the engine needs. The setup engine computes a
#: 50-period simple moving average plus structure lookbacks, so higher
#: timeframes need the same lookback expressed in far fewer candles.
MIN_BARS_BY_TIMEFRAME: dict[str, int] = {
    DAILY: 80,
    WEEKLY: 60,
    MONTHLY: 55,
}

#: Daily-bar history that must be loaded (or stored) to build enough candles.
LOOKBACK_DAYS_BY_TIMEFRAME: dict[str, int] = {
    DAILY: 420,
    WEEKLY: 800,
    MONTHLY: 2000,
}


def min_bars(timeframe: str) -> int:
    return MIN_BARS_BY_TIMEFRAME.get(timeframe, MIN_BARS_BY_TIMEFRAME[DAILY])


def lookback_days(timeframe: str) -> int:
    return LOOKBACK_DAYS_BY_TIMEFRAME.get(timeframe, LOOKBACK_DAYS_BY_TIMEFRAME[DAILY])


def normalise(timeframe: str | None) -> str:
    """Coerce user input to a known timeframe (defaults to daily)."""
    if not timeframe:
        return DAILY
    value = str(timeframe).strip().upper()
    return value if value in TIMEFRAMES else DAILY


def _week_key(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return (iso[0], iso[1])


def _month_key(day: date) -> tuple[int, int]:
    return (day.year, day.month)


def _period_key(day: date, timeframe: str):
    return _month_key(day) if timeframe == MONTHLY else _week_key(day)


def is_complete_period(last_day: date, timeframe: str) -> bool:
    """Whether a period ending on ``last_day`` can be treated as finished."""
    if timeframe == WEEKLY:
        # A week is finished once its last session is Friday.
        return last_day.weekday() == 4
    if timeframe == MONTHLY:
        # A month is finished once the next calendar day starts a new month.
        return (last_day + timedelta(days=1)).month != last_day.month
    return True


def resample(bars: list[Bar], timeframe: str, drop_incomplete: bool = True) -> list[Bar]:
    """Aggregate daily ``bars`` into the requested timeframe."""
    timeframe = normalise(timeframe)
    if timeframe == DAILY or not bars:
        return list(bars)

    key = lambda day: _period_key(day, timeframe)  # noqa: E731 - small local helper

    out: list[Bar] = []
    current = None
    o = h = l = c = v = 0.0
    period_end = bars[0].date

    for bar in bars:
        bar_key = key(bar.date)
        if current is None:
            current = bar_key
            o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
        elif bar_key == current:
            h = max(h, bar.high)
            l = min(l, bar.low)
            c = bar.close
            v += bar.volume
        else:
            out.append(Bar(date=period_end, open=o, high=h, low=l, close=c, volume=v))
            current = bar_key
            o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
        period_end = bar.date

    if drop_incomplete and not is_complete_period(period_end, timeframe):
        # The final period is still forming; leave it for the next run.
        return out

    out.append(Bar(date=period_end, open=o, high=h, low=l, close=c, volume=v))
    return out
