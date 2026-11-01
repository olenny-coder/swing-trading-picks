"""Smart Money Concepts multi-timeframe analysis.

The whole strategy in one place, in two steps:

**Step 1 — primary analysis (daily candles).**
Identify the market structure (bullish or bearish), look for a definitive **Break
of Structure** in the direction of that trend (a close above a significant prior
swing high, or below a significant prior swing low), then find the **Fair Value
Gap** left by the impulse move that broke it. No valid gap relative to the BOS
means confidence 0 — the analysis stops there.

**Step 2 — refinement (4-hour candles).**
Zoom into the daily gap. Entry is the gap's **50% mean threshold**; the stop goes
beyond the swing point that created the gap, so it sits at a structural
invalidation rather than at the gap edge where a wick can take it out; the target
is the next liquidity pool (the nearest swing high or low beyond the entry). The
trade is only valid at a risk-to-reward of **1:1.6 or better**.

The result renders as the exact plain-text block required by the brief — see
``SmcAnalysis.render``. Nothing outside that structure is ever emitted.

Only closed candles are read, so a zone can never appear and then vanish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .fvg import BUY, SELL, FairValueGap, closed_only, detect_fair_value_gaps, open_gaps
from .indicators import atr as atr_series
from .structure import SwingPoints, swing_indices

#: Bars either side needed to confirm a fractal pivot. Three makes a swing
#: "significant" rather than a one-bar blip.
SWING_K = 3
#: How far back a break of structure is still considered live.
STRUCTURE_LOOKBACK = 40
#: How many pivots back to search when the newest one was never broken.
PIVOT_SEARCH = 6
#: The gap must belong to the impulse that broke structure, so it has to form
#: within this many daily candles of the break.
FVG_IMPULSE_WINDOW = 4
#: A gap is only consumed once price has traded all the way through it. Partial
#: mitigation is normal — price being inside the zone is the entry condition, not
#: a reason to discard it.
FVG_MAX_MITIGATION = 0.99
#: Minimum risk-to-reward. Below this the answer is "No Trade".
MIN_RISK_REWARD = 1.6
#: Stop buffer beyond the structural swing, in 4-hour Average True Range.
STOP_BUFFER_ATR = 0.15
#: Candles needed before either chart can be judged.
MIN_DAILY_BARS = 60
MIN_REFINEMENT_BARS = 12
#: A setup refined on the daily chart instead of the 4-hour one is coarser, so its
#: confidence is capped below anything the full-fidelity path can produce.
DAILY_REFINEMENT_CONFIDENCE_CAP = 60.0

BULLISH = "Bullish"
BEARISH = "Bearish"
NEUTRAL = "Neutral"


@dataclass
class BreakOfStructure:
    """A confirmed close beyond a significant prior swing."""

    direction: str          # Bullish | Bearish
    level: float            # the swing that was broken
    index: int              # daily candle that closed beyond it
    when: date
    pivot_index: int
    close: float
    distance_atr: float     # how far beyond the level the close reached

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "level": round(self.level, 4),
            "date": self.when.isoformat(),
            "close": round(self.close, 4),
            "distance_atr": round(self.distance_atr, 2),
        }


@dataclass
class SmcAnalysis:
    """One symbol's verdict, plus everything needed to render and draw it."""

    symbol: str
    confidence: float = 0.0
    trend: str = NEUTRAL
    bos_confirmed: bool = False
    fvg_low: float | None = None
    fvg_high: float | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_reward: float | None = None
    reasoning: str = ""
    # --- diagnostics, not part of the plain-text block -------------------
    bos: BreakOfStructure | None = None
    gap: FairValueGap | None = None
    triggered: bool = False
    four_hour_available: bool = False
    #: Which chart the entry, stop and target were refined on: "4H" or "1D".
    refinement_timeframe: str = "4H"
    blockers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    price: float = 0.0
    as_of: date | None = None

    @property
    def tradeable(self) -> bool:
        return self.confidence > 0 and self.entry is not None

    # -- the required plain-text output ---------------------------------
    def render(self) -> str:
        """The exact block the brief specifies. No JSON, no code fences."""
        zone = (
            f"{self.fvg_low:.2f} - {self.fvg_high:.2f}"
            if self.fvg_low is not None and self.fvg_high is not None
            else "n/a"
        )
        entry = f"{self.entry:.2f}" if self.entry is not None else "n/a"
        stop = f"{self.stop:.2f}" if self.stop is not None else "n/a"
        target = f"{self.target:.2f}" if self.target is not None else "n/a"
        ratio = f"1:{self.risk_reward:.2f}" if self.risk_reward is not None else "n/a"
        return "\n".join(
            [
                f"Symbol: {self.symbol}",
                f"Confidence Score: {self.confidence:.0f}",
                f"Trend Direction: {self.trend}",
                f"1D BOS Confirmed: {'Yes' if self.bos_confirmed else 'No'}",
                f"1D FVG Zone: {zone}",
                "4H Refinement:",
                f"Entry Price: {entry}",
                f"Stop Loss: {stop}",
                f"Take Profit: {target}",
                f"Risk Reward Ratio: {ratio}",
                f"Reasoning: {self.reasoning}",
            ]
        )

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "text": self.render(),
            "confidence": round(self.confidence, 1),
            "trend": self.trend,
            "bos_confirmed": self.bos_confirmed,
            "fvg_low": _r(self.fvg_low),
            "fvg_high": _r(self.fvg_high),
            "entry": _r(self.entry),
            "stop": _r(self.stop),
            "target": _r(self.target),
            "risk_reward": _r(self.risk_reward, 2),
            "reasoning": self.reasoning,
            "tradeable": self.tradeable,
            "triggered": self.triggered,
            "four_hour_available": self.four_hour_available,
            "refinement_timeframe": self.refinement_timeframe,
            "price": _r(self.price),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "bos": self.bos.as_dict() if self.bos else None,
            "gap": self.gap.as_dict() if self.gap else None,
            "blockers": self.blockers,
            "reasons": self.reasons,
        }


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _atr(bars: list) -> list[float | None]:
    return atr_series([b.high for b in bars], [b.low for b in bars], [b.close for b in bars])


# ---------------------------------------------------------------------------
# Step 1 — daily structure, BOS and the gap it left
# ---------------------------------------------------------------------------
def classify_structure(bars: list, swings: SwingPoints) -> str:
    """Bullish / Bearish / Neutral from the swing sequence."""
    highs = [bars[i].high for i in swings.highs][-2:]
    lows = [bars[i].low for i in swings.lows][-2:]
    if len(highs) == 2 and len(lows) == 2:
        if highs[1] > highs[0] and lows[1] > lows[0]:
            return BULLISH
        if highs[1] < highs[0] and lows[1] < lows[0]:
            return BEARISH
    # Fall back to the raw extremes when the swings disagree.
    if len(bars) >= 40:
        recent = bars[-20:]
        prior = bars[-40:-20]
        if max(b.high for b in recent) > max(b.high for b in prior) and min(
            b.low for b in recent
        ) > min(b.low for b in prior):
            return BULLISH
        if max(b.high for b in recent) < max(b.high for b in prior) and min(
            b.low for b in recent
        ) < min(b.low for b in prior):
            return BEARISH
    return NEUTRAL


def find_bos(bars: list, swings: SwingPoints, direction: str, atr_values) -> BreakOfStructure | None:
    """Most recent definitive close beyond a significant prior swing."""
    bullish = direction == BULLISH
    pivots = swings.highs if bullish else swings.lows
    # Only pivots that price could not have broken on their confirmation bar.
    usable = [j for j in pivots if j <= len(bars) - SWING_K - 1][-PIVOT_SEARCH:]
    start = max(0, len(bars) - STRUCTURE_LOOKBACK)

    for j in reversed(usable):
        level = bars[j].high if bullish else bars[j].low
        for i in range(j + SWING_K + 1, len(bars)):
            broke = bars[i].close > level if bullish else bars[i].close < level
            if not broke:
                continue
            if i < start:
                return None  # the break is stale
            distance = (bars[i].close - level) if bullish else (level - bars[i].close)
            a = atr_values[i] or 0.0
            return BreakOfStructure(
                direction=direction,
                level=level,
                index=i,
                when=bars[i].date,
                pivot_index=j,
                close=bars[i].close,
                distance_atr=(distance / a) if a > 0 else 0.0,
            )
    return None


def find_gap_for_bos(bars: list, bos: BreakOfStructure, direction: str) -> FairValueGap | None:
    """The Fair Value Gap left by the impulse that broke structure.

    The impulse leg runs from the opposing swing that started the move, through the
    swing that was broken, to the candle that broke it. The gap has to have
    completed somewhere inside that leg — that is what makes it *the* gap behind
    the break rather than an unrelated imbalance that happens to be nearby — and it
    has to still be a live zone: a gap is only consumed once price has traded all
    the way through it, so a partially filled gap price is sitting inside is
    exactly where an entry belongs.
    """
    atr_values = _atr(bars)
    gaps = detect_fair_value_gaps(bars, "1D", atr_values, lookback=STRUCTURE_LOOKBACK + 20)
    expected = BUY if direction == BULLISH else SELL

    swings = swing_indices(
        [b.high for b in bars], [b.low for b in bars], k=SWING_K
    )
    # The leg begins at the last opposing swing before the one that got broken.
    opposing = swings.lows if direction == BULLISH else swings.highs
    prior = [i for i in opposing if i < bos.pivot_index]
    low = max(0, (prior[-1] if prior else bos.pivot_index - 1) - 1)
    high = bos.index + 2

    candidates = [
        g
        for g in gaps
        if g.direction == expected
        and low <= g.formed_index <= high
        and g.mitigation < FVG_MAX_MITIGATION
    ]
    if not candidates:
        return None
    # Prefer the gap closest to the breaking candle, then the larger one.
    candidates.sort(key=lambda g: (g.formed_index, g.size), reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Step 2 — 4-hour refinement
# ---------------------------------------------------------------------------
def _swing_before(swings: SwingPoints, index: int) -> int | None:
    prior = [i for i in swings.lows if i <= index]
    return prior[-1] if prior else None


def refine_on_four_hour(
    symbol: str,
    daily: list,
    four_hour: list,
    bos: BreakOfStructure,
    gap: FairValueGap,
    min_risk_reward: float = MIN_RISK_REWARD,
) -> SmcAnalysis:
    """Entry at the gap's mean threshold, stop behind the structural swing.

    The refinement runs on the 4-hour chart as specified. When no 4-hour candles are
    stored it degrades to the daily chart rather than refusing outright: the levels
    are still real structure, just coarser. That degradation is always stated in the
    Reasoning and it caps the confidence, so a daily-refined setup is never mistaken
    for a full-fidelity one.
    """
    bullish = bos.direction == BULLISH

    refined_on = "4H"
    series = list(four_hour)
    if len(series) < MIN_REFINEMENT_BARS:
        refined_on = "1D"
        series = list(daily)

    analysis = SmcAnalysis(
        symbol=symbol,
        trend=bos.direction,
        bos_confirmed=True,
        bos=bos,
        gap=gap,
        fvg_low=gap.bottom,
        fvg_high=gap.top,
        four_hour_available=refined_on == "4H",
        refinement_timeframe=refined_on,
        as_of=daily[-1].date if daily else None,
        price=daily[-1].close if daily else 0.0,
    )

    if len(series) < MIN_REFINEMENT_BARS:
        analysis.confidence = 0.0
        analysis.reasoning = (
            "No Trade — there are too few candles to place a stop and a target, and no "
            "4-hour refinement data is stored."
        )
        analysis.blockers.append("not enough candles to refine on either chart")
        return analysis

    if refined_on == "1D":
        analysis.blockers.append(
            "no 4-hour candles stored, so the levels are refined on the daily chart"
        )

    four_hour = series
    highs = [b.high for b in four_hour]
    lows = [b.low for b in four_hour]
    closes = [b.close for b in four_hour]
    atr_values = atr_series(highs, lows, closes)
    four_hour_atr = atr_values[-1] or 0.0

    # Prices are quoted to the cent and rounded once, here, so the plain-text block
    # and the structured fields can never disagree at the boundary.
    entry = round(gap.midpoint, 2)  # the 50% mean threshold of the gap

    # The structural invalidation: the 4-hour swing that created the gap, and the
    # far edge of the gap itself. The stop goes beyond whichever is further, so a
    # wick through the zone edge cannot take the trade out early.
    swings_4h = swing_indices(highs, lows, k=2)
    buffer = max(STOP_BUFFER_ATR * four_hour_atr, 0.0)

    if bullish:
        anchor = _swing_before(swings_4h, len(four_hour) - 1)
        structural = min(lows[anchor], gap.bottom) if anchor is not None else gap.bottom
        stop = round(min(structural, gap.bottom) - buffer, 2)
    else:
        prior_highs = [i for i in swings_4h.highs if i <= len(four_hour) - 1]
        anchor = prior_highs[-1] if prior_highs else None
        structural = max(highs[anchor], gap.top) if anchor is not None else gap.top
        stop = round(max(structural, gap.top) + buffer, 2)

    risk = abs(entry - stop)
    if risk <= 0:
        analysis.confidence = 0.0
        analysis.reasoning = "No Trade — the gap is too narrow to place a stop behind it."
        analysis.blockers.append("zero-width risk")
        return analysis

    # Target: the next liquidity pool beyond the entry, from either chart. It has
    # to be at least the stop distance away, otherwise it is not a target at all.
    target = next_liquidity_pool(
        daily, four_hour, entry, bullish, min_distance=max(risk, 0.5 * four_hour_atr)
    )
    if target is not None:
        target = round(target, 2)
    if target is None:
        analysis.confidence = 0.0
        analysis.reasoning = (
            "No Trade — there is no swing high or low beyond the entry to use as a target."
        )
        analysis.blockers.append("no liquidity pool for a target")
        return analysis

    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0.0

    analysis.entry = entry
    analysis.stop = stop
    analysis.target = target
    analysis.risk_reward = rr

    # Did price actually trade back into the zone?
    zone_low, zone_high = gap.bottom, gap.top
    analysis.triggered = any(
        b.low <= zone_high and b.high >= zone_low for b in four_hour[-min(len(four_hour), 60) :]
    )

    # -- validation -------------------------------------------------------
    if rr < min_risk_reward:
        analysis.confidence = 0.0
        analysis.reasoning = (
            f"No Trade — the next liquidity pool at {target:.2f} against a stop at {stop:.2f} "
            f"gives a risk-to-reward of 1:{rr:.2f}, below the 1:{min_risk_reward:.1f} minimum."
        )
        analysis.blockers.append(f"risk-to-reward 1:{rr:.2f} below 1:{min_risk_reward:.1f}")
        return analysis

    analysis.confidence = _confidence(bos, gap, rr, analysis.triggered, four_hour_atr, entry, risk)
    if refined_on == "1D":
        # A daily-refined setup is coarser, so it can never score like a 4-hour one.
        analysis.confidence = min(analysis.confidence, DAILY_REFINEMENT_CONFIDENCE_CAP)
    analysis.reasons = _reasons(bos, gap, rr, analysis.triggered)
    if not analysis.triggered:
        analysis.blockers.append("price has not yet traded back into the gap")
    analysis.reasoning = _reasoning(bos, gap, analysis, rr)
    return analysis


def next_liquidity_pool(
    daily: list,
    four_hour: list,
    entry: float,
    bullish: bool,
    min_distance: float = 0.0,
) -> float | None:
    """The nearest meaningful swing beyond the entry, across both charts.

    "Liquidity" means a confirmed swing point price is likely to reach for. A
    swing sitting inside the gap — or closer than the stop distance — is not a
    target, so those are filtered out before the nearest one is chosen.
    """
    pools: list[float] = []
    for bars, k in ((four_hour, 2), (daily, SWING_K)):
        if len(bars) < k * 2 + 1:
            continue
        swings = swing_indices([b.high for b in bars], [b.low for b in bars], k=k)
        indices = swings.highs if bullish else swings.lows
        for i in indices:
            price = bars[i].high if bullish else bars[i].low
            beyond = (price - entry) if bullish else (entry - price)
            if beyond >= max(min_distance, 0.0) and beyond > 0:
                pools.append(price)
    if not pools:
        return None
    return min(pools) if bullish else max(pools)


# ---------------------------------------------------------------------------
# Scoring and prose
# ---------------------------------------------------------------------------
def _confidence(
    bos: BreakOfStructure,
    gap: FairValueGap,
    rr: float,
    triggered: bool,
    four_hour_atr: float,
    entry: float,
    risk: float,
) -> float:
    """0–100, from the confluence the brief asks for."""
    score = 40.0
    # The break itself: decisive closes and fresh breaks score higher.
    score += min(1.0, max(0.0, bos.distance_atr) / 1.5) * 18.0
    # The gap: a violent impulse leaves a wide, obviously unfair zone.
    score += min(1.0, gap.displacement_atr / 2.5) * 14.0
    score += max(0.0, 1.0 - gap.mitigation / FVG_MAX_MITIGATION) * 10.0
    # A 4-hour reaction inside the zone is the entry trigger.
    score += 12.0 if triggered else 0.0
    # Reward quality above the minimum.
    score += min(1.0, max(0.0, (rr - MIN_RISK_REWARD) / 2.0)) * 16.0
    # Prefer a stop that is a sensible distance away, not a hair-trigger.
    if four_hour_atr > 0:
        score += 4.0 if risk >= 0.5 * four_hour_atr else 0.0
    # The score is reported as a whole number, so round it here: the plain-text
    # block and the structured field then render from exactly the same value.
    return float(max(0, min(100, round(score))))


def _reasons(
    bos: BreakOfStructure, gap: FairValueGap, rr: float, triggered: bool
) -> list[str]:
    direction = "above" if bos.direction == BULLISH else "below"
    out = [
        f"1D BOS: closed {direction} the significant swing at {bos.level:.2f} on "
        f"{bos.when.isoformat()} ({bos.distance_atr:.1f}x ATR beyond it)"
    ]
    out.append(
        f"1D FVG: {gap.label} {gap.bottom:.2f} - {gap.top:.2f}, formed "
        f"{gap.formed_date.isoformat()} by a {gap.displacement_atr:.1f}x ATR impulse"
    )
    out.append(f"Risk-to-reward 1:{rr:.2f} to the next liquidity pool")
    if triggered:
        out.append("price has traded into the zone on the 4-hour chart")
    else:
        out.append("price has not yet reached the zone on the 4-hour chart")
    return out


def _reasoning(
    bos: BreakOfStructure, gap: FairValueGap, analysis: SmcAnalysis, rr: float
) -> str:
    direction = "bullish" if bos.direction == BULLISH else "bearish"
    on_daily = analysis.refinement_timeframe == "1D"
    chart = "daily chart" if on_daily else "4-hour chart"
    trigger = (
        f"Price has already traded back into the gap on the {chart}, so the mean "
        "threshold is the working entry."
        if analysis.triggered
        else "Price has not yet reached the gap; the mean threshold is a resting entry."
    )
    caveat = (
        " No 4-hour candles are stored, so the levels are refined on the daily chart and "
        "the confidence is capped."
        if on_daily
        else ""
    )
    return (
        f"{bos.direction} structure confirmed by a 1D break of structure at {bos.level:.2f}. "
        f"The impulse left a {direction} fair value gap between {gap.bottom:.2f} and "
        f"{gap.top:.2f}. {trigger} Stop sits beyond the structural swing at "
        f"{analysis.stop:.2f} and the first liquidity pool is {analysis.target:.2f}, giving "
        f"1:{rr:.2f}.{caveat}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def analyze(
    symbol: str,
    daily: list,
    refinement: list | None = None,
    min_risk_reward: float = MIN_RISK_REWARD,
) -> SmcAnalysis:
    """Run the full two-step analysis for one symbol.

    ``daily`` must be closed daily candles. ``refinement`` must be closed **4-hour**
    candles — Alpaca serves that interval natively, and providers without it return
    already-aggregated candles, so no resampling happens here.
    """
    symbol = symbol.upper().strip()
    analysis = SmcAnalysis(symbol=symbol)

    if len(daily) < MIN_DAILY_BARS:
        analysis.reasoning = (
            f"No Trade — only {len(daily)} daily candles are available and at least "
            f"{MIN_DAILY_BARS} are needed to read structure."
        )
        analysis.blockers.append("insufficient daily history")
        return analysis

    analysis.price = daily[-1].close
    analysis.as_of = daily[-1].date

    highs = [b.high for b in daily]
    lows = [b.low for b in daily]
    atr_values = _atr(daily)
    swings = swing_indices(highs, lows, k=SWING_K)
    analysis.trend = classify_structure(daily, swings)

    if analysis.trend == NEUTRAL:
        analysis.reasoning = (
            "No Trade — the daily swing structure is unclear, so there is no direction to "
            "break in."
        )
        analysis.blockers.append("daily structure unclear")
        return analysis

    bos = find_bos(daily, swings, analysis.trend, atr_values)
    if bos is None:
        analysis.reasoning = (
            f"No Trade — no definitive 1D break of structure in the {analysis.trend.lower()} "
            "direction within the recent window."
        )
        analysis.blockers.append("no recent 1D break of structure")
        return analysis

    analysis.bos_confirmed = True
    analysis.bos = bos

    gap = find_gap_for_bos(daily, bos, analysis.trend)
    if gap is None:
        analysis.reasoning = (
            f"No Trade — the 1D break of structure at {bos.level:.2f} left no valid, "
            "unmitigated fair value gap, so there is no zone to trade from."
        )
        analysis.blockers.append("no valid 1D fair value gap behind the break")
        return analysis

    analysis.gap = gap
    analysis.fvg_low = gap.bottom
    analysis.fvg_high = gap.top

    four_hour = list(refinement or [])
    return refine_on_four_hour(symbol, daily, four_hour, bos, gap, min_risk_reward)
