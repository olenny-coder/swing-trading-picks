"""Fair Value Gap + breakout-structure strategy.

This is the screening brain behind the FVG screener:

1. Find the confirmed **breakout structure** (BOS, CHoCH, range, flag, trendline,
   supply/demand flip). It sets the direction.
2. Find the **Fair Value Gap** that the breakout leg left behind, in that same
   direction.
3. Wait for price to **retrace into that gap** and confirm. That is the entry.

Nothing here forces a trade. If there is no confirmed structure, no matching gap,
or the reward does not clear the minimum risk-to-reward, the result is
``NO_TRADE`` or ``WAIT`` with the levels stated — which is a legitimate answer.

**Closed candles only.** A daily bar dated today is treated as still forming and
is dropped before any analysis, so a zone can never appear and then vanish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .fvg import (
    BUY,
    SELL,
    FVG_FILLED_RATIO,
    FairValueGap,
    detect_fair_value_gaps,
    nearest_open_gap,
    open_gaps,
    price_in_gap,
)
from .indicators import atr as atr_series
from .indicators import ema
from .structure import BreakoutStructure, SwingPoints, detect_structures, swing_indices

#: A setup is only tradeable at or above this reward-to-risk.
DEFAULT_MIN_RR = 2.0
#: How far beyond the gap the stop sits, in Average True Range.
STOP_BUFFER_ATR = 0.25
#: The nearest acceptable target.
TARGET_MIN_RR = 1.5
#: The gap must have been left by the breakout leg, not months earlier.
FVG_MAX_AGE_BARS = 40

STATUS_BUY = "BUY"
STATUS_SELL = "SELL"
STATUS_WAIT = "WAIT"
STATUS_NO_TRADE = "NO_TRADE"


@dataclass
class FvgSettings:
    min_rr: float = DEFAULT_MIN_RR
    max_watchlist: int = 20
    risk_per_trade_pct: float = 1.0
    earnings_buffer_days: int = 7
    min_price: float = 5.0
    min_volume: float = 500_000.0
    min_market_cap: float = 2_000_000_000.0
    allow_earnings_plays: bool = False


@dataclass
class FvgCandidate:
    ticker: str
    name: str | None
    sector: str | None
    timeframe: str
    status: str
    direction: str | None
    setup_type: str
    structure: BreakoutStructure | None
    gap: FairValueGap | None
    entry: float | None
    entry_low: float | None
    entry_high: float | None
    stop: float | None
    target1: float | None
    target2: float | None
    rr1: float | None
    rr2: float | None
    confidence: float
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    invalidation: str = ""
    price: float = 0.0
    atr: float = 0.0

    @property
    def risk_per_share(self) -> float | None:
        if self.entry is None or self.stop is None:
            return None
        return abs(self.entry - self.stop)

    @property
    def is_actionable(self) -> bool:
        return self.status in (STATUS_BUY, STATUS_SELL)

    def as_row(self) -> dict:
        """The shortlist row, exactly the columns the screener promises."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "status": self.status,
            "setup_type": self.setup_type,
            "breakout_level": round(self.structure.level, 4) if self.structure else None,
            "breakout_kind": self.structure.kind if self.structure else None,
            "breakout_date": (
                self.structure.confirmed_date.isoformat() if self.structure else None
            ),
            "fvg_top": round(self.gap.top, 4) if self.gap else None,
            "fvg_bottom": round(self.gap.bottom, 4) if self.gap else None,
            "fvg_midpoint": round(self.gap.midpoint, 4) if self.gap else None,
            "fvg_date": self.gap.formed_date.isoformat() if self.gap else None,
            "fvg_mitigation": round(self.gap.mitigation, 3) if self.gap else None,
            "entry": _round(self.entry),
            "entry_low": _round(self.entry_low),
            "entry_high": _round(self.entry_high),
            "stop": _round(self.stop),
            "target1": _round(self.target1),
            "target2": _round(self.target2),
            "rr1": _round(self.rr1, 2),
            "rr2": _round(self.rr2, 2),
            "confidence": round(self.confidence, 1),
            "price": _round(self.price),
            "atr": _round(self.atr),
            "why": " · ".join(self.reasons[:4]) if self.reasons else "no confluence",
            "reasons": self.reasons,
            "blockers": self.blockers,
            "invalidation": self.invalidation,
        }


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def closed_only(bars: list, today: date | None = None) -> list:
    """Drop a candle that cannot have closed yet.

    A daily bar dated today is still forming, so including it would let a zone
    appear and then disappear. Weekly and monthly series are built from these
    bars, so removing it here keeps every timeframe honest.
    """
    if not bars:
        return bars
    today = today or date.today()
    if bars[-1].date >= today:
        return bars[:-1]
    return bars


def _at_least(value: float, threshold: float, direction: str) -> bool:
    return value >= threshold if direction == BUY else value <= threshold


def _swing_levels(bars: list, swings: SwingPoints, entry: float, direction: str) -> list[float]:
    """Prior swing levels beyond the entry, nearest first."""
    if direction == BUY:
        levels = {bars[j].high for j in swings.highs if bars[j].high > entry}
        return sorted(levels)
    levels = {bars[j].low for j in swings.lows if bars[j].low < entry}
    return sorted(levels, reverse=True)


def _confirmation(bars: list, direction: str, avg_volume: float) -> tuple[bool, str]:
    """Did the latest closed candle confirm the retracement?"""
    if not bars:
        return False, "no closed candle to confirm with"
    last = bars[-1]
    rng = last.high - last.low
    if rng <= 0:
        return False, "the latest candle has no range"

    body = abs(last.close - last.open)
    bullish = last.close > last.open

    if direction == BUY:
        # A rejection wick: the candle probed lower and closed back up.
        lower_wick = min(last.open, last.close) - last.low
        if lower_wick >= 0.5 * rng and last.close >= last.open:
            return True, "rejection wick: sold off into the gap and closed back up"
        if bullish and body >= 0.5 * rng:
            return True, "bullish candle closing back in the breakout direction"
    else:
        upper_wick = last.high - max(last.open, last.close)
        if upper_wick >= 0.5 * rng and last.close <= last.open:
            return True, "rejection wick: rallied into the gap and closed back down"
        if not bullish and body >= 0.5 * rng:
            return True, "bearish candle closing back in the breakout direction"

    if avg_volume > 0 and last.volume >= 1.5 * avg_volume:
        return True, "volume expansion on the retracement candle"

    return False, "no rejection, engulfing or volume expansion yet"


def analyze_fvg(
    ticker: str,
    name: str | None,
    sector: str | None,
    bars: list,
    timeframe: str,
    settings: FvgSettings | None = None,
    earnings_in_days: int | None = None,
    market_cap: float | None = None,
) -> FvgCandidate:
    """Screen one instrument on one timeframe. Never raises on thin data."""
    settings = settings or FvgSettings()
    bars = closed_only(bars)

    def blank(status: str, note: str) -> FvgCandidate:
        return FvgCandidate(
            ticker=ticker,
            name=name,
            sector=sector,
            timeframe=timeframe,
            status=status,
            direction=None,
            setup_type="No valid signal",
            structure=None,
            gap=None,
            entry=None,
            entry_low=None,
            entry_high=None,
            stop=None,
            target1=None,
            target2=None,
            rr1=None,
            rr2=None,
            confidence=0.0,
            blockers=[note],
            invalidation="—",
            price=bars[-1].close if bars else 0.0,
        )

    if len(bars) < 55:
        return blank(STATUS_NO_TRADE, f"only {len(bars)} closed candles, need at least 55")

    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    atr_values = atr_series(highs, lows, closes)
    atr_value = atr_values[-1] or 0.0
    if atr_value <= 0:
        return blank(STATUS_NO_TRADE, "Average True Range could not be computed")

    last_close = closes[-1]
    if last_close < settings.min_price:
        return blank(STATUS_NO_TRADE, f"price {last_close:.2f} is below the minimum")
    avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
    if avg_volume < settings.min_volume:
        return blank(STATUS_NO_TRADE, "average volume is below the liquidity minimum")

    earnings_risk = (
        earnings_in_days is not None
        and earnings_in_days <= settings.earnings_buffer_days
        and not settings.allow_earnings_plays
    )
    # A market-cap filter only applies when a source actually supplied one.
    if market_cap is not None and market_cap < settings.min_market_cap:
        return blank(STATUS_NO_TRADE, "market capitalisation is below the minimum")

    swings = swing_indices(highs, lows)
    structures = detect_structures(bars, atr_values, swings)
    gaps = detect_fair_value_gaps(bars, timeframe, atr_values)
    open_only = open_gaps(gaps)

    if not structures:
        candidate = blank(STATUS_NO_TRADE, "no confirmed breakout structure")
        candidate.gap = nearest_open_gap(open_only, last_close, BUY)
        return candidate

    context = _Context(
        ticker=ticker,
        name=name,
        sector=sector,
        timeframe=timeframe,
        bars=bars,
        closes=closes,
        volumes=volumes,
        atr_value=atr_value,
        last_close=last_close,
        avg_volume=avg_volume,
        swings=swings,
        all_gaps=gaps,
        open_gaps=open_only,
        ema20=ema(closes, 20),
        ema50=ema(closes, 50),
        earnings_in_days=earnings_in_days,
        earnings_risk=earnings_risk,
        settings=settings,
    )

    # Evaluate every candidate structure against the gaps it left behind, so a
    # loose detector cannot mask a better setup sitting next to it.
    built = [
        candidate
        for candidate in (
            _build_candidate(context, structure) for structure in structures[:3]
        )
        if candidate is not None
    ]
    if not built:
        candidate = blank(STATUS_NO_TRADE, "the breakout left no open Fair Value Gap")
        candidate.structure = structures[0]
        return candidate

    # An actionable setup wins; otherwise the most confident watchlist entry.
    built.sort(key=lambda c: (c.is_actionable, c.confidence), reverse=True)
    return built[0]


@dataclass
class _Context:
    """Everything the per-structure evaluation needs, computed once per ticker."""

    ticker: str
    name: str | None
    sector: str | None
    timeframe: str
    bars: list
    closes: list[float]
    volumes: list[float]
    atr_value: float
    last_close: float
    avg_volume: float
    swings: SwingPoints
    all_gaps: list[FairValueGap]
    open_gaps: list[FairValueGap]
    ema20: list[float | None]
    ema50: list[float | None]
    earnings_in_days: int | None
    earnings_risk: bool
    settings: FvgSettings


def _build_candidate(context: _Context, structure: BreakoutStructure) -> FvgCandidate | None:
    """Evaluate one breakout structure against the gaps it left behind.

    Returns ``None`` when the structure has no usable gap — the caller then tries
    the next structure rather than giving up on the instrument.
    """
    bars = context.bars
    direction = structure.direction
    last_close = context.last_close
    atr_value = context.atr_value
    settings = context.settings

    slow = context.ema50[-1] or 0.0
    fast = context.ema20[-1] or 0.0
    aligned = (
        last_close > slow and fast > slow
        if direction == BUY
        else last_close < slow and fast < slow
    )

    # The gap must belong to the breakout leg, not to ancient history.
    leg_start = max(0, structure.confirmed_index - FVG_MAX_AGE_BARS)
    leg_gaps = [
        g for g in context.open_gaps if g.direction == direction and g.formed_index >= leg_start
    ]
    if not leg_gaps:
        return None

    gap = nearest_open_gap(leg_gaps, last_close, direction) or leg_gaps[0]

    risk_buffer = STOP_BUFFER_ATR * atr_value
    entry = gap.midpoint
    entry_low, entry_high = gap.bottom, gap.top
    stop = gap.bottom - risk_buffer if direction == BUY else gap.top + risk_buffer
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    measured1 = entry + risk * TARGET_MIN_RR if direction == BUY else entry - risk * TARGET_MIN_RR
    measured2 = entry + risk * 3.0 if direction == BUY else entry - risk * 3.0
    levels = _swing_levels(bars, context.swings, entry, direction)
    target1 = next((l for l in levels if _at_least(l, measured1, direction)), measured1)
    target2 = next(
        (l for l in levels if _at_least(l, target1 + risk * 0.5, direction)), measured2
    )
    if not _at_least(target2, target1, direction):
        target2 = measured2
    rr1 = abs(target1 - entry) / risk
    rr2 = abs(target2 - entry) / risk

    in_zone = price_in_gap(gap, last_close)
    confirmed, confirmation_note = (
        _confirmation(bars, direction, context.avg_volume)
        if in_zone
        else (False, "price has not retraced into the gap")
    )

    blockers: list[str] = []
    if not gap.is_open:
        blockers.append("the gap is almost fully traded through")
    if context.earnings_risk:
        blockers.append(
            f"earnings in {context.earnings_in_days} day(s), inside the "
            f"{settings.earnings_buffer_days}-day buffer"
        )
        earnings_risk = True
    else:
        earnings_risk = False

    if rr1 < settings.min_rr:
        status = STATUS_NO_TRADE
        blockers.append(f"reward-to-risk at target 1 is {rr1:.2f}, below {settings.min_rr:.1f}")
    elif not aligned:
        status = STATUS_NO_TRADE
        blockers.append(
            "price and the 20/50 exponential moving averages are not aligned with the direction"
        )
    elif earnings_risk:
        status = STATUS_NO_TRADE
    elif not in_zone:
        status = STATUS_WAIT
        blockers.append(
            f"price {last_close:.2f} has not retraced into the "
            f"{gap.bottom:.2f}-{gap.top:.2f} zone yet"
        )
    elif not confirmed:
        status = STATUS_WAIT
        blockers.append(confirmation_note)
    else:
        status = STATUS_BUY if direction == BUY else STATUS_SELL

    volume_expansion = context.volumes[-1] / context.avg_volume if context.avg_volume else 1.0
    confidence = _confidence(
        structure=structure,
        gap=gap,
        aligned=aligned,
        volume_expansion=volume_expansion,
        rr1=rr1,
        confirmed=confirmed,
        bars_since_gap=len(bars) - 1 - gap.formed_index,
        earnings_risk=earnings_risk,
    )
    reasons = _reasons(structure, gap, aligned, volume_expansion, rr1)

    invalidation = (
        f"A close below {stop:.2f} cancels this setup"
        if direction == BUY
        else f"A close above {stop:.2f} cancels this setup"
    )
    if not gap.is_open:
        invalidation += "; the gap is almost fully traded through"

    return FvgCandidate(
        ticker=context.ticker,
        name=context.name,
        sector=context.sector,
        timeframe=context.timeframe,
        status=status,
        direction=direction,
        setup_type=structure.label,
        structure=structure,
        gap=gap,
        entry=entry,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        target1=target1,
        target2=target2,
        rr1=rr1,
        rr2=rr2,
        confidence=confidence,
        reasons=reasons,
        blockers=blockers,
        invalidation=invalidation,
        price=last_close,
        atr=atr_value,
    )


def _confidence(
    structure: BreakoutStructure,
    gap: FairValueGap,
    aligned: bool,
    volume_expansion: float,
    rr1: float,
    confirmed: bool,
    bars_since_gap: int,
    earnings_risk: bool,
) -> float:
    """0–100, built from the confluence the brief asks us to prefer."""
    score = 42.0
    score += structure.quality * 20.0                       # clean breakout
    score += min(1.0, gap.displacement_atr / 2.5) * 12.0    # displacement size
    score += 8.0 if aligned else 0.0                        # trend alignment
    score += min(1.0, max(0.0, (volume_expansion - 1.0) / 1.0)) * 6.0
    score += min(1.0, rr1 / 3.0) * 8.0                      # reward quality
    score += 4.0 if confirmed else 0.0                      # entry trigger present
    # A fresh, barely-touched gap is worth more than an old, worked-through one.
    score += max(0.0, 1.0 - bars_since_gap / FVG_MAX_AGE_BARS) * 4.0
    score -= gap.mitigation * 10.0
    score -= 10.0 if earnings_risk else 0.0
    return max(0.0, min(100.0, score))


def _reasons(
    structure: BreakoutStructure, gap: FairValueGap, aligned: bool, volume_expansion: float, rr1: float
) -> list[str]:
    out = [f"{structure.label}: {structure.detail}"]
    out.append(
        f"{gap.label} on {gap.timeframe} from {gap.formed_date.isoformat()} "
        f"({gap.bottom:.2f}–{gap.top:.2f}, {gap.displacement_atr:.1f}× Average True Range)"
    )
    if gap.mitigation <= 0.01:
        out.append("the gap is untouched")
    else:
        out.append(f"the gap is {gap.mitigation * 100:.0f}% mitigated")
    if aligned:
        out.append("price is aligned with the 20/50 exponential moving averages")
    if volume_expansion >= 1.2:
        out.append(f"volume is {volume_expansion:.1f}× its 20-candle average")
    out.append(f"reward-to-risk {rr1:.2f} to the first target")
    return out


# ---------------------------------------------------------------------------
# Drill-down: annotations, signal card and chart markup
# ---------------------------------------------------------------------------
_COLOURS = {
    "bullish_fvg": "#16a34a",
    "bearish_fvg": "#dc2626",
    "level": "#38bdf8",
    "stop": "#dc2626",
    "target": "#22c55e",
    "entry": "#f59e0b",
    "box": "#a78bfa",
    "trendline": "#f472b6",
}


def annotations(candidate: FvgCandidate, gaps: list[FairValueGap], bars: list) -> list[dict]:
    """The chart markup instructions, as data the UI can draw directly."""
    if not bars:
        return []
    last_date = bars[-1].date
    out: list[dict] = []

    if candidate.structure:
        structure = candidate.structure
        if structure.level_kind == "trendline" and structure.line:
            out.append(
                {
                    "kind": "trendline",
                    "label": structure.label,
                    "color": _COLOURS["trendline"],
                    "points": [
                        {"date": d.isoformat(), "price": round(p, 4)} for d, p in structure.line
                    ],
                }
            )
        else:
            out.append(
                {
                    "kind": "level",
                    "label": f"{structure.label} @ {structure.level:.2f}",
                    "color": _COLOURS["level"],
                    "price": round(structure.level, 4),
                    "from_date": structure.confirmed_date.isoformat(),
                    "to_date": last_date.isoformat(),
                }
            )
        if structure.box:
            out.append(
                {
                    "kind": "box",
                    "label": "Consolidation box",
                    "color": _COLOURS["box"],
                    "top": round(structure.box[2], 4),
                    "bottom": round(structure.box[3], 4),
                    "from_date": structure.box[0].isoformat(),
                    "to_date": structure.box[1].isoformat(),
                }
            )

    # Every open gap is shaded; the one being traded is emphasised.
    for gap in gaps:
        if not gap.is_open and gap is not candidate.gap:
            continue
        is_focus = gap is candidate.gap
        out.append(
            {
                "kind": "fvg",
                "label": gap.label,
                "color": _COLOURS["bullish_fvg" if gap.direction == BUY else "bearish_fvg"],
                "top": round(gap.top, 4),
                "bottom": round(gap.bottom, 4),
                "midpoint": round(gap.midpoint, 4),
                "from_date": gap.formed_date.isoformat(),
                "to_date": last_date.isoformat(),
                "emphasis": is_focus,
                "timeframe": gap.timeframe,
            }
        )

    if candidate.entry is not None:
        out.append(
            {
                "kind": "zone",
                "label": "Entry trigger zone",
                "color": _COLOURS["entry"],
                "top": round(candidate.entry_high or candidate.entry, 4),
                "bottom": round(candidate.entry_low or candidate.entry, 4),
                "from_date": last_date.isoformat(),
                "to_date": last_date.isoformat(),
            }
        )
        out.append(
            {
                "kind": "level",
                "label": f"Entry {candidate.entry:.2f}",
                "color": _COLOURS["entry"],
                "price": round(candidate.entry, 4),
                "style": "dashed",
            }
        )
        out.append(
            {
                "kind": "marker",
                "label": "Entry trigger",
                "date": last_date.isoformat(),
                "price": round(candidate.entry, 4),
                "position": "belowBar" if candidate.direction == BUY else "aboveBar",
                "shape": "arrowUp" if candidate.direction == BUY else "arrowDown",
                "color": _COLOURS["entry"],
            }
        )
    if candidate.stop is not None:
        out.append(
            {
                "kind": "level",
                "label": f"Stop {candidate.stop:.2f}",
                "color": _COLOURS["stop"],
                "price": round(candidate.stop, 4),
            }
        )
    for index, target in enumerate((candidate.target1, candidate.target2), start=1):
        if target is None:
            continue
        out.append(
            {
                "kind": "level",
                "label": f"Target {index} {target:.2f}",
                "color": _COLOURS["target"],
                "price": round(target, 4),
                "style": "dashed",
            }
        )
    return out


def signal_card(candidate: FvgCandidate, settings: FvgSettings | None = None) -> dict:
    """The trade card: direction, exact levels, conditions and invalidation."""
    settings = settings or FvgSettings()
    risk = candidate.risk_per_share
    return {
        "ticker": candidate.ticker,
        "timeframe": candidate.timeframe,
        "signal": candidate.status,
        "direction": candidate.direction,
        "setup_type": candidate.setup_type,
        "confidence": round(candidate.confidence, 1),
        "entry": _round(candidate.entry),
        "entry_zone": [_round(candidate.entry_low), _round(candidate.entry_high)],
        "stop": _round(candidate.stop),
        "target1": _round(candidate.target1),
        "target2": _round(candidate.target2),
        "rr1": _round(candidate.rr1, 2),
        "rr2": _round(candidate.rr2, 2),
        "risk_per_share": _round(risk),
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "reasons": candidate.reasons,
        "blockers": candidate.blockers,
        "invalidation": candidate.invalidation,
        "no_trade": candidate.status == STATUS_NO_TRADE,
        "waiting": candidate.status == STATUS_WAIT,
        "disclaimer": (
            "Educational and analytical output only. This is not financial advice."
        ),
    }


def chart_markup(
    candidate: FvgCandidate, gaps: list[FairValueGap], bars: list
) -> dict:
    """A portable description of the markup, so it can be redrawn or shared."""
    return {
        "ticker": candidate.ticker,
        "timeframe": candidate.timeframe,
        "as_of": bars[-1].date.isoformat() if bars else None,
        "signal": candidate.status,
        "annotations": annotations(candidate, gaps, bars),
    }
