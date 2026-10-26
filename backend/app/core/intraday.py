"""Intraday candles and the 4-hour series built from them.

The strategy reads two clocks: market structure on the **daily** chart, and entry
refinement on the **4-hour** chart. Alpaca has no native 4-hour interval, so the
4-hour candles are aggregated from hourly bars, bucketed on the UTC clock.

Only **closed** candles are ever used: a bucket that could still be forming is
dropped, so the refinement can never repaint.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..providers.base import IntradayBar

#: Hours per refinement candle.
REFINEMENT_HOURS = 4
#: The interval requested from the provider. Alpaca accepts ``4Hour`` directly; a
#: provider without it returns hourly bars and the caller aggregates.
REFINEMENT_INTERVAL = "4Hour"
#: What to fall back to when the provider has no native 4-hour interval.
FALLBACK_INTERVAL = "1Hour"


def _naive(ts: datetime) -> datetime:
    """Drop tzinfo so every stored candle compares cleanly."""
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


def bucket_start(ts: datetime, hours: int = REFINEMENT_HOURS) -> datetime:
    """The start of the bucket a timestamp belongs to."""
    clean = _naive(ts).replace(minute=0, second=0, microsecond=0)
    return clean - timedelta(hours=clean.hour % hours)


def resample_intraday(
    bars: list[IntradayBar], hours: int = REFINEMENT_HOURS, drop_incomplete: bool = True
) -> list[IntradayBar]:
    """Aggregate intraday candles into ``hours``-hour candles.

    Open is the first open of the bucket, high and low are the bucket extremes,
    close is the last close and volume is the sum. The result is stamped with the
    bucket start.
    """
    if not bars:
        return []

    ordered = sorted(bars, key=lambda b: _naive(b.ts))
    buckets: dict[datetime, list[IntradayBar]] = {}
    for bar in ordered:
        buckets.setdefault(bucket_start(bar.ts, hours), []).append(bar)

    starts = sorted(buckets)
    if drop_incomplete and starts:
        # A bucket is complete once a later bucket exists. The final bucket may
        # still be forming, so it is only kept when it is clearly closed.
        last = _naive(starts[-1])
        now = datetime.utcnow()
        if now < last + timedelta(hours=hours):
            starts = starts[:-1]

    out: list[IntradayBar] = []
    for start in starts:
        group = buckets[start]
        out.append(
            IntradayBar(
                ts=start,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
            )
        )
    return out


def refinement_bars(native: list[IntradayBar], hourly: list[IntradayBar] | None = None):
    """Pick the best available 4-hour series.

    A provider that returns native 4-hour candles is used as-is — those are the
    exchange's own buckets. Otherwise hourly candles are aggregated into 4-hour
    ones, so the strategy still has a refinement chart.
    """
    if native:
        return native
    return resample_intraday(hourly or [])


def bars_to_chart(bars: list[IntradayBar]) -> list[dict]:
    """Serialise intraday candles for the chart component."""
    return [
        {
            "time": _naive(b.ts).isoformat(timespec="minutes"),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
