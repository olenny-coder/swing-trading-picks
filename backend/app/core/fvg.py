"""Fair Value Gap detection.

A Fair Value Gap (FVG) is a three-candle imbalance:

- **Bullish**: the gap between the *high of candle 1* and the *low of candle 3*,
  where candle 2 is a strong bullish displacement candle.
- **Bearish**: the gap between the *low of candle 1* and the *high of candle 3*,
  where candle 2 is a strong bearish displacement candle.

The middle candle is what creates the imbalance: it moves so decisively that the
market never traded fairly across part of its range, and price often returns to
that zone later. This module only ever reads **closed candles**, so a zone can
never appear and then vanish (no repainting).

The zone is not a signal on its own. It becomes one only when a confirmed
breakout structure agrees with it and price retraces into it — see
``fvg_strategy.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .indicators import atr as atr_series

#: The middle candle must have a body worth at least this share of its own range.
FVG_DISPLACEMENT_BODY = 0.55
#: ...and a range of at least this multiple of Average True Range...
FVG_DISPLACEMENT_ATR = 1.0
#: ...and the resulting gap must be at least this multiple of Average True Range,
#: so ordinary noise is not reported as an imbalance.
FVG_MIN_SIZE_ATR = 0.15
#: How many candles back still-open gaps are reported for.
FVG_LOOKBACK = 60
#: Once this share of a zone has been traded through it is treated as consumed.
FVG_FILLED_RATIO = 0.90

BUY = "BUY"
SELL = "SELL"


@dataclass
class FairValueGap:
    """One three-candle imbalance."""

    direction: str          # BUY = bullish imbalance, SELL = bearish
    top: float
    bottom: float
    formed_index: int       # index of candle 3, the candle that completes the gap
    formed_date: date
    timeframe: str
    displacement_atr: float  # size of the middle candle in Average True Range
    mitigation: float        # 0.0 untouched .. 1.0 traded all the way through

    @property
    def size(self) -> float:
        return self.top - self.bottom

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def proximal(self) -> float:
        """The edge price meets first when retracing into the zone."""
        return self.top if self.direction == BUY else self.bottom

    @property
    def distal(self) -> float:
        """The far edge — where the imbalance would be fully consumed."""
        return self.bottom if self.direction == BUY else self.top

    @property
    def is_open(self) -> bool:
        return self.mitigation < FVG_FILLED_RATIO

    @property
    def label(self) -> str:
        return "Bullish FVG" if self.direction == BUY else "Bearish FVG"

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "label": self.label,
            "top": round(self.top, 4),
            "bottom": round(self.bottom, 4),
            "midpoint": round(self.midpoint, 4),
            "size": round(self.size, 4),
            "formed_date": self.formed_date.isoformat(),
            "timeframe": self.timeframe,
            "displacement_atr": round(self.displacement_atr, 2),
            "mitigation": round(self.mitigation, 3),
            "open": self.is_open,
        }


def _displacement(o: float, h: float, l: float, c: float, a: float, direction: str) -> bool:
    """Is this candle a decisive move in ``direction``?"""
    rng = h - l
    if rng <= 0 or a <= 0:
        return False
    if abs(c - o) / rng < FVG_DISPLACEMENT_BODY:
        return False
    if rng < FVG_DISPLACEMENT_ATR * a:
        return False
    return c > o if direction == BUY else c < o


def _mitigation(direction: str, top: float, bottom: float, after) -> float:
    """How much of the zone later candles traded back through, 0..1."""
    size = top - bottom
    if size <= 0 or not after:
        return 0.0
    if direction == BUY:
        deepest = min(b.low for b in after)
        return max(0.0, min(1.0, (top - deepest) / size))
    highest = max(b.high for b in after)
    return max(0.0, min(1.0, (highest - bottom) / size))


def _fallback_range(bars: list, upto: int, window: int = 14) -> float:
    """Mean candle range up to ``upto``.

    Average True Range needs 14 candles to warm up, and on a short series it is
    ``None`` throughout. Falling back to the mean range keeps gap detection
    working on the earliest candles instead of silently returning nothing.
    """
    lo = max(0, upto - window + 1)
    ranges = [b.high - b.low for b in bars[lo : upto + 1]]
    ranges = [r for r in ranges if r > 0]
    return sum(ranges) / len(ranges) if ranges else 0.0


def detect_fair_value_gaps(
    bars: list,
    timeframe: str,
    atr_values: list[float | None] | None = None,
    lookback: int = FVG_LOOKBACK,
    direction: str | None = None,
) -> list[FairValueGap]:
    """All FVGs completed by ``bars``, oldest first.

    ``bars`` must contain **closed candles only**. ``direction`` restricts the
    search to bullish or bearish imbalances.
    """
    if len(bars) < 3:
        return []

    atr_values = atr_values if atr_values is not None else atr_series(
        [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
    )

    first = max(2, len(bars) - lookback)
    out: list[FairValueGap] = []

    for i in range(first, len(bars)):
        middle = bars[i - 1]
        a = atr_values[i - 1] or _fallback_range(bars, i - 1)
        if a <= 0:
            continue
        c1, c3 = bars[i - 2], bars[i]

        # Bullish imbalance: candle 3's low holds entirely above candle 1's high,
        # so the space between them was never traded.
        if direction in (None, BUY) and _displacement(
            middle.open, middle.high, middle.low, middle.close, a, BUY
        ):
            bottom, top = c1.high, c3.low
            if top > bottom and (top - bottom) >= FVG_MIN_SIZE_ATR * a:
                out.append(
                    FairValueGap(
                        direction=BUY,
                        top=top,
                        bottom=bottom,
                        formed_index=i,
                        formed_date=c3.date,
                        timeframe=timeframe,
                        displacement_atr=(middle.high - middle.low) / a,
                        mitigation=_mitigation(BUY, top, bottom, bars[i + 1 :]),
                    )
                )
                continue

        # Bearish imbalance: candle 3's high holds entirely below candle 1's low.
        if direction in (None, SELL) and _displacement(
            middle.open, middle.high, middle.low, middle.close, a, SELL
        ):
            bottom, top = c3.high, c1.low
            if top > bottom and (top - bottom) >= FVG_MIN_SIZE_ATR * a:
                out.append(
                    FairValueGap(
                        direction=SELL,
                        top=top,
                        bottom=bottom,
                        formed_index=i,
                        formed_date=c3.date,
                        timeframe=timeframe,
                        displacement_atr=(middle.high - middle.low) / a,
                        mitigation=_mitigation(SELL, top, bottom, bars[i + 1 :]),
                    )
                )

    return out


def open_gaps(gaps: list[FairValueGap]) -> list[FairValueGap]:
    """Still-unfilled imbalances, oldest first."""
    return [g for g in gaps if g.is_open]


def gaps_for_direction(gaps: list[FairValueGap], direction: str) -> list[FairValueGap]:
    return [g for g in gaps if g.direction == direction]


def nearest_open_gap(
    gaps: list[FairValueGap], price: float, direction: str
) -> FairValueGap | None:
    """The open gap price is closest to, preferring one it is sitting inside.

    For a long the interesting zone is at or below price (price retraces *down*
    into it); for a short it is at or above.
    """
    candidates = [g for g in gaps if g.direction == direction and g.is_open]
    if not candidates:
        return None

    if direction == BUY:
        below = [g for g in candidates if g.bottom <= price]
        pool = below or candidates
        return max(pool, key=lambda g: g.top)
    above = [g for g in candidates if g.top >= price]
    pool = above or candidates
    return min(pool, key=lambda g: g.bottom)


def price_in_gap(gap: FairValueGap, price: float) -> bool:
    return gap.bottom <= price <= gap.top
