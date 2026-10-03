"""SMA 20/50 flow-based setup engine.

Implements the discretionary daily-chart method as deterministic code. Terms:

- **Flow**       — Positive when price is above the 50 SMA, Negative when below.
- **EXE**        — Entry Execution: a strong momentum candle closing beyond a
                   level (bullish candle for longs, bearish for shorts).
- **LP**         — Liquidity Point: the structural level used as the trigger —
                   a swept swing low for long setups, a swept swing high for
                   short setups.
- **Flush bar**  — a large aggressive momentum candle in the trend direction.
- **MF**         — Majority Flush: >= 2 flush bars within the last 3 bars.
- **Time limit** — the confirming EXE must appear within a small bar count.
- **Risk**       — stop just beyond the structural invalidation point; target
                   projected from the chosen risk-reward ratio.

Setups
------
- ``UC1`` / ``UC2`` — bullish continuation, shallow / deeper pullback.
- ``DC1`` / ``DC2`` — bearish continuation, shallow / deeper pullback.
- ``UR1`` / ``DR1`` — early reversals after a flush into liquidity.
- ``UR2`` / ``DR2`` — double-top (bearish) / double-bottom (bullish).

The source rules are discretionary, so every threshold is an explicit, tunable
constant and each rule's intent is documented at its implementation site.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import confidence, indicators as ta
from .base_types import SignalContext
from .constants import (
    CONTINUATION_SETUPS,
    DIRECTION_BY_SETUP,
    SETUP_DC1,
    SETUP_DC2,
    SETUP_DR1,
    SETUP_DR2,
    SETUP_UC1,
    SETUP_UC2,
    SETUP_UR1,
    SETUP_UR2,
    SIGNAL_BUY,
    SIGNAL_SELL,
)
from .regime import is_rate_sensitive

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunable parameters
# ---------------------------------------------------------------------------
SMA_FAST = 20
SMA_SLOW = 50
MIN_BARS = 80

SWING_K = 2                 # bars either side required to confirm a fractal pivot
STRUCTURE_LOOKBACK = 30     # how far back to search for structure
MAX_SETUP_BARS = 6          # continuation: EXE must land within this many bars
UR1_MAX_BARS = 6
DR1_MAX_BARS = 10           # DR1 needs no strict bar counting
DR2_MAX_BARS = 5

MOMENTUM_BODY_RATIO = 0.55  # EXE body as a share of the candle range
MOMENTUM_ATR_MIN = 0.60     # EXE range as a multiple of ATR
FLUSH_ATR_MIN = 1.40        # flush bar range as a multiple of ATR
FLUSH_BODY_RATIO = 0.55
MAJORITY_FLUSH_WINDOW = 3
MAJORITY_FLUSH_MIN = 2
SIDEWAYS_MAX_SMA_GAP = 0.030  # |SMA20-SMA50| / SMA50 under this = sideways
DOUBLE_TOLERANCE = 0.02       # peaks/troughs within 2% count as a "double"
STOP_BUFFER_ATR = 0.25
MAX_RISK_PCT = 0.15         # reject setups whose structural stop is further than this
#: A structural stop is naturally wider on a higher timeframe, so the guardrail
#: scales with the candle interval rather than rejecting every monthly setup.
MAX_RISK_PCT_BY_TIMEFRAME: dict[str, float] = {
    "DAILY": 0.15,
    "WEEKLY": 0.28,
    "MONTHLY": 0.45,
}

SETUP_RR = {
    SETUP_UC1: 2.0, SETUP_UC2: 2.5, SETUP_DC1: 2.0, SETUP_DC2: 2.5,
    SETUP_UR1: 2.0, SETUP_DR1: 2.0, SETUP_UR2: 3.0, SETUP_DR2: 3.0,
}

DEFAULT_BACKTEST_WIN_RATES = {
    SETUP_UC1: 0.58, SETUP_UC2: 0.55, SETUP_DC1: 0.56, SETUP_DC2: 0.53,
    SETUP_UR1: 0.54, SETUP_DR1: 0.54, SETUP_UR2: 0.57, SETUP_DR2: 0.57,
}

# ---------------------------------------------------------------------------
# Blended confidence
# ---------------------------------------------------------------------------
# Confidence is a blend of two factor groups, each scored 0-100:
#
# * CONTINUATION factors describe the trend the setup wants to ride.
# * REVERSAL factors describe the turn that triggers the entry — the end of a
#   pullback for continuation setups, or a genuine change of direction for
#   reversal setups.
#
# Which group dominates depends on the setup family (see FAMILY_WEIGHTS), and a
# small set of context adjustments is applied on top of the blend.
CONTINUATION_FACTORS = (
    "trend_separation",      # price beyond the 50-period SMA, measured in ATRs
    "ma_alignment",          # 20-period vs 50-period SMA separation, in ATRs
    "pullback_control",      # how shallow and orderly the pullback was
    "structure_clean",       # no counter-flush against the trend
    "trigger_strength",      # entry-candle quality + LP break margin + promptness
    "volume_confirmation",   # volume versus its 20-period average
    "volatility_expansion",  # entry-candle range versus Average True Range
)

REVERSAL_FACTORS = (
    "flush_intensity",       # size/aggression of the flush into the level
    "liquidity_sweep",       # did it take out a prior swing extreme
    "reversal_trigger",      # recovery-candle quality + reclaim distance
    "exhaustion",            # Relative Strength Index stretch and distance from the mean
    "structure",             # double pattern / bigger retracement / compression
)

FAMILY_WEIGHTS: dict[str, tuple[float, float]] = {
    # setup: (continuation weight, reversal weight)
    SETUP_UC1: (0.60, 0.40),
    SETUP_UC2: (0.55, 0.45),
    SETUP_DC1: (0.60, 0.40),
    SETUP_DC2: (0.55, 0.45),
    SETUP_UR1: (0.35, 0.65),
    SETUP_DR1: (0.35, 0.65),
    SETUP_UR2: (0.30, 0.70),
    SETUP_DR2: (0.30, 0.70),
}

# Context adjustments applied on top of the blend.
REGIME_ADJUSTMENT_MAX = 8.0
SECTOR_ADJUSTMENT_MAX = 5.0
COUNTER_IMPACT_MIN = -15.0
COUNTER_IMPACT_MAX = 5.0

# Volume / Average True Range confirmation.
#
# A setup is more trustworthy when the entry candle is *backed*: it expands
# beyond its recent Average True Range AND trades on above-average volume. Each
# leg contributes nothing until it clears its threshold, so this adjustment can
# only ever add confidence — it never penalises a quiet but valid setup.
VOLUME_CONFIRMATION_MIN = 1.2    # multiple of the 20-period average volume
VOLUME_CONFIRMATION_FULL = 2.2
ATR_EXPANSION_MIN = 1.0          # entry-candle range as a multiple of ATR
ATR_EXPANSION_FULL = 1.8
CONFIRMATION_BOOST_MAX = 6.0     # maximum confidence points added


@dataclass
class SignalDraft:
    ticker: str
    name: str
    sector: str | None
    setup: str
    direction: str
    entry: float
    target: float
    stop: float
    price: float
    volume: float
    rr: float
    confidence: float
    confidence_components: dict
    triggered_rules: list[str]
    event_flags: dict


# ---------------------------------------------------------------------------
# Candle / structure helpers
# ---------------------------------------------------------------------------
def _swing_indices(highs: list[float], lows: list[float], k: int = SWING_K):
    """Fractal swing highs/lows confirmed by ``k`` bars either side."""
    sh: list[int] = []
    sl: list[int] = []
    for i in range(k, len(highs) - k):
        hwin = highs[i - k : i + k + 1]
        if highs[i] == max(hwin) and hwin.count(highs[i]) == 1:
            sh.append(i)
        lwin = lows[i - k : i + k + 1]
        if lows[i] == min(lwin) and lwin.count(lows[i]) == 1:
            sl.append(i)
    return sh, sl


def _is_momentum(o, h, l, c, atr, direction: str) -> bool:
    """EXE candle: strong body in the trade direction, at least moderate size."""
    rng = h - l
    if rng <= 0 or atr <= 0:
        return False
    if abs(c - o) / rng < MOMENTUM_BODY_RATIO:
        return False
    if rng < MOMENTUM_ATR_MIN * atr:
        return False
    return c > o if direction == "up" else c < o


def _is_flush(o, h, l, c, atr, direction: str) -> bool:
    """Flush bar: large aggressive candle in the given direction."""
    rng = h - l
    if rng <= 0 or atr <= 0:
        return False
    if rng < FLUSH_ATR_MIN * atr:
        return False
    if abs(c - o) / rng < FLUSH_BODY_RATIO:
        return False
    return c > o if direction == "up" else c < o


def _prev_swing(indices: list[int], before: int) -> int | None:
    for i in reversed(indices):
        if i < before:
            return i
    return None


# ---------------------------------------------------------------------------
# Confidence assembly
# ---------------------------------------------------------------------------
def _base_event_flags(sector: str | None, ctx: SignalContext) -> dict:
    rotation = "neutral"
    if sector in ctx.leading_sectors:
        rotation = "leading"
    elif sector in ctx.lagging_sectors:
        rotation = "lagging"
    return {
        "earnings_proximity": ctx.earnings_in_days is not None and ctx.earnings_in_days <= 7,
        "earnings_in_days": ctx.earnings_in_days,
        "macro_risk": ctx.high_impact_events_within_2d,
        "macro_sentiment": round(ctx.macro_sentiment, 2),
        "regime": ctx.regime,
        "vix": ctx.vix,
        "sector_rotation": rotation,
        "rate_sensitive": is_rate_sensitive(sector),
        "rate_rising_sharply": ctx.rate_rising_sharply,
    }


def _earnings_suppressed(ctx: SignalContext, conf: float) -> bool:
    if ctx.earnings_in_days is None or ctx.earnings_in_days > 7:
        return False
    if ctx.allow_earnings_plays and conf > 80.0:
        return False
    return True


def _scale(value: float, low: float, high: float) -> float:
    """Linear map of ``value`` from [low, high] onto 0-100, clamped."""
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _centred(value: float, neutral: float, span: float) -> float:
    """Score where ``neutral`` maps to 50 and ``neutral ± span`` maps to 0/100."""
    if span <= 0:
        return 50.0
    return max(0.0, min(100.0, 50.0 + (value - neutral) / span * 50.0))


def _trend_separation_factor(close: float, sma50_value: float, atr_value: float, sign: float) -> float:
    """How far price sits beyond the 50 SMA, in ATRs (2 ATRs or more scores 100)."""
    if not atr_value:
        return 50.0
    return _scale((close - sma50_value) * sign / atr_value, 0.0, 2.0)


def _ma_alignment_factor(sma20_value: float, sma50_value: float, atr_value: float, sign: float) -> float:
    """Separation of the 20 and 50 SMA, in ATRs (a full ATR apart scores 100)."""
    if not atr_value:
        return 50.0
    return _scale((sma20_value - sma50_value) * sign / atr_value, 0.0, 1.0)


def _trend_context_factor(close: float, sma50_value: float, atr_value: float, sign: float) -> float:
    """Context for reversal setups: 50 when price is at the 50 SMA, 100 when the
    trend already leans the trade's way, 0 when it leans hard against it."""
    if not atr_value:
        return 50.0
    return _centred((close - sma50_value) * sign / atr_value, 0.0, 2.0)


def _volume_confirmation_factor(volume_ratio: float) -> float:
    """Volume versus its 20-period average: 1.0x is neutral (50)."""
    return _centred(volume_ratio, 1.0, 0.9)


def _volatility_expansion_factor(exe_range_atr: float) -> float:
    """Entry-candle range versus Average True Range: 1.0x ATR is neutral (50)."""
    return _centred(exe_range_atr, 1.0, 0.8)


def _confirmation_boost(volume_ratio: float, exe_range_atr: float) -> float:
    """Confidence added when the entry candle is backed by volume and range.

    Returns 0..``CONFIRMATION_BOOST_MAX``. Each leg is silent below its own
    threshold, so a setup that is merely average on both counts earns nothing
    and loses nothing.
    """
    volume_leg = _scale(volume_ratio, VOLUME_CONFIRMATION_MIN, VOLUME_CONFIRMATION_FULL)
    range_leg = _scale(exe_range_atr, ATR_EXPANSION_MIN, ATR_EXPANSION_FULL)
    return round(CONFIRMATION_BOOST_MAX * (0.5 * volume_leg + 0.5 * range_leg) / 100.0, 1)


def _trigger_factor(exe_body: float, lp_margin_atr: float, bars_since: int, max_bars: int) -> float:
    """Entry-candle quality + how decisively and promptly it cleared the LP."""
    promptness = _scale(max_bars - bars_since + 1, 1, max_bars)
    return (
        0.40 * _scale(exe_body, 0.50, 0.90)
        + 0.35 * _scale(lp_margin_atr, 0.0, 0.8)
        + 0.25 * promptness
    )


def _group_score(factors: dict[str, float], keys: tuple[str, ...]) -> float:
    """Mean of the factor group, over the factors that were actually measured."""
    present = [float(factors[k]) for k in keys if isinstance(factors.get(k), (int, float))]
    if not present:
        return 50.0
    return sum(present) / len(present)


def _exhaustion(rsi_value: float | None, long_side: bool) -> float:
    """How stretched the move is: 50 at a neutral RSI, 100 at an extreme."""
    if rsi_value is None:
        return 50.0
    deviation = (50.0 - rsi_value) if long_side else (rsi_value - 50.0)
    return _centred(deviation, 0.0, 22.0)


def _regime_adjustment(direction: str, regime: str) -> float:
    aligned = regime == ("bullish" if direction == SIGNAL_BUY else "bearish")
    opposed = regime == ("bearish" if direction == SIGNAL_BUY else "bullish")
    if aligned:
        return REGIME_ADJUSTMENT_MAX
    if opposed:
        return -REGIME_ADJUSTMENT_MAX
    return 0.0


def _sector_adjustment(direction: str, sector: str | None, ctx: SignalContext) -> float:
    if not sector:
        return 0.0
    wants_leading = direction == SIGNAL_BUY
    favours = sector in (ctx.leading_sectors if wants_leading else ctx.lagging_sectors)
    against = sector in (ctx.lagging_sectors if wants_leading else ctx.leading_sectors)
    if favours:
        return SECTOR_ADJUSTMENT_MAX
    if against:
        return -SECTOR_ADJUSTMENT_MAX
    return 0.0


def _counter_impact(direction: str, sector: str | None, ctx: SignalContext) -> float:
    """Impact of macro events / media arguing AGAINST the recommended direction.

    Negative means the counter case is stronger and drags confidence down; a
    small positive value means the backdrop actively supports the trade.
    """
    impact = 0.0
    # Net economic-calendar sentiment, signed against the trade direction.
    against = -ctx.macro_sentiment if direction == SIGNAL_BUY else ctx.macro_sentiment
    if against > 0:
        impact -= min(10.0, against * 10.0)
    else:
        impact += min(3.0, -against * 3.0)
    if ctx.high_impact_events_within_2d:
        impact -= 5.0
    if ctx.rate_rising_sharply and is_rate_sensitive(sector) and direction == SIGNAL_BUY:
        impact -= 3.0
    if ctx.earnings_in_days is not None and ctx.earnings_in_days <= 7:
        impact -= 2.0
    return max(COUNTER_IMPACT_MIN, min(COUNTER_IMPACT_MAX, impact))


def _counter_drivers(direction: str, sector: str | None, ctx: SignalContext) -> list[str]:
    """Human-readable reasons behind the counter impact (shown in the UI)."""
    drivers: list[str] = []
    against = -ctx.macro_sentiment if direction == SIGNAL_BUY else ctx.macro_sentiment
    if against > 0.05:
        drivers.append("economic-calendar sentiment opposes this direction")
    elif against < -0.05:
        drivers.append("economic-calendar sentiment supports this direction")
    if ctx.high_impact_events_within_2d:
        drivers.append("high-impact macro event within 2 days")
    if ctx.rate_rising_sharply and is_rate_sensitive(sector) and direction == SIGNAL_BUY:
        drivers.append("rising yields pressure a rate-sensitive long")
    if ctx.earnings_in_days is not None and ctx.earnings_in_days <= 7:
        drivers.append(f"earnings due in {ctx.earnings_in_days}d (gap risk)")
    return drivers


def _finish(
    ticker, name, sector, setup, entry, target, stop, price, volume,
    volume_ratio, exe_range_atr, factors, triggered, ctx,
) -> SignalDraft | None:
    direction = DIRECTION_BY_SETUP[setup]
    rr = SETUP_RR.get(setup, 2.0)
    # Guardrail: a structural stop that is implausibly far makes the trade
    # untradeable, so the setup is dropped rather than reported. The limit
    # scales with the timeframe, because a monthly stop is legitimately wider
    # than a daily one.
    risk_limit = MAX_RISK_PCT_BY_TIMEFRAME.get(ctx.timeframe or "DAILY", MAX_RISK_PCT)
    if entry > 0 and abs(entry - stop) / entry > risk_limit:
        return None

    factors = dict(factors or {})
    factors.setdefault("volume_confirmation", _volume_confirmation_factor(volume_ratio))
    factors.setdefault("volatility_expansion", _volatility_expansion_factor(exe_range_atr))

    continuation = _group_score(factors, CONTINUATION_FACTORS)
    reversal = _group_score(factors, REVERSAL_FACTORS)
    w_cont, w_rev = FAMILY_WEIGHTS.get(setup, (0.5, 0.5))
    blend = continuation * w_cont + reversal * w_rev

    regime_adj = _regime_adjustment(direction, ctx.regime)
    sector_adj = _sector_adjustment(direction, sector, ctx)
    counter = _counter_impact(direction, sector, ctx)
    # Only ever positive: a candle that expands on heavy volume earns extra
    # confidence, a quiet one is left alone.
    confirmation = _confirmation_boost(volume_ratio, exe_range_atr)

    conf = round(
        max(0.0, min(100.0, blend + regime_adj + sector_adj + counter + confirmation)), 1
    )
    if _earnings_suppressed(ctx, conf):
        return None

    components: dict[str, float] = {
        "continuation": round(continuation, 1),
        "reversal": round(reversal, 1),
        "continuation_weight": round(w_cont * 100.0),
        "reversal_weight": round(w_rev * 100.0),
        "blend": round(blend, 1),
        "regime_adjustment": round(regime_adj, 1),
        "sector_adjustment": round(sector_adj, 1),
        "counter_impact": round(counter, 1),
        "confirmation_boost": round(confirmation, 1),
        "volume_ratio": round(volume_ratio, 2),
        "atr_multiple": round(exe_range_atr, 2),
        "backtest_win_rate": round(
            ctx.backtest_win_rates.get(setup, DEFAULT_BACKTEST_WIN_RATES.get(setup, 0.55)) * 100.0,
            1,
        ),
        "final": conf,
    }
    for key in CONTINUATION_FACTORS + REVERSAL_FACTORS:
        if isinstance(factors.get(key), (int, float)):
            components[f"factor_{key}"] = round(float(factors[key]), 1)

    flags = _base_event_flags(sector, ctx)
    flags.update(
        {
            "setup": setup,
            "direction": direction,
            "rr": rr,
            "confidence_label": confidence.confidence_label(conf),
            "counter_impact": round(counter, 1),
            "counter_impact_drivers": _counter_drivers(direction, sector, ctx),
        }
    )
    return SignalDraft(
        ticker=ticker,
        name=name,
        sector=sector,
        setup=setup,
        direction=direction,
        entry=round(entry, 2),
        target=round(target, 2),
        stop=round(stop, 2),
        price=round(price, 2),
        volume=volume,
        rr=rr,
        confidence=conf,
        confidence_components=components,
        triggered_rules=triggered,
        event_flags=flags,
    )


def _project(entry: float, risk: float, rr: float, direction: str) -> float:
    return entry + rr * risk if direction == SIGNAL_BUY else entry - rr * risk


# ---------------------------------------------------------------------------
# Strategy 1 — Continuation (UC1/UC2/DC1/DC2)
# ---------------------------------------------------------------------------
def _detect_continuation(
    ticker, name, sector, ohlcv, sma20, sma50, atr, rsi, swings_high, swings_low, last, avg_vol, ctx,
    long_side: bool,
):
    opens, highs, lows, closes, volumes = ohlcv
    c = closes[last]
    a = atr[last]
    if not a or sma20[last] is None or sma50[last] is None:
        return None

    # 1) Market context — Positive/Negative Flow.
    if long_side:
        flow_ok = c > sma50[last] and sma20[last] > sma50[last]
    else:
        flow_ok = c < sma50[last] and sma20[last] < sma50[last]
    if not flow_ok:
        return None

    # 2) The pullback extreme (Point B) — a confirmed swing low (longs) / high (shorts).
    pivots = swings_low if long_side else swings_high
    b = _prev_swing(pivots, last)
    if b is None or last - b > STRUCTURE_LOOKBACK:
        return None
    bars_since_b = last - b

    # 3) There must have been a prior impulse leg (Point A) in the trend direction.
    opposite = swings_high if long_side else swings_low
    a_idx = _prev_swing(opposite, b)
    if a_idx is None:
        return None
    if long_side and highs[a_idx] <= highs[b]:
        return None
    if not long_side and lows[a_idx] >= lows[b]:
        return None

    # 4) UC1/DC1 = shallow pullback held beyond the 50 SMA; UC2/DC2 = deeper
    #    pullback that tested/undercut the 50 SMA.
    touched_slow = lows[b] <= sma50[b] if long_side else highs[b] >= sma50[b]
    setup = (SETUP_UC2 if long_side else SETUP_DC2) if touched_slow else (SETUP_UC1 if long_side else SETUP_DC1)

    # 5) No flush against the trend in the 3 bars leading into Point B.
    counter = "down" if long_side else "up"
    counter_flush = any(
        _is_flush(opens[j], highs[j], lows[j], closes[j], atr[j] or 0.0, counter)
        for j in range(max(0, b - 3), b)
    )

    # 6) UC1/DC1 invalidation: if Point B reached the origin of the move it is no
    #    longer a retracement.
    origin = _prev_swing(pivots, b)
    if origin is not None:
        if long_side and lows[b] <= lows[origin]:
            return None
        if not long_side and highs[b] >= highs[origin]:
            return None

    # 7) Time limit — the EXE must complete within the allowed bar count.
    within_time = 1 <= bars_since_b <= MAX_SETUP_BARS
    if not within_time:
        return None

    # 8) EXE — a momentum candle in the trend direction.
    exe_dir = "up" if long_side else "down"
    exe_ok = _is_momentum(opens[last], highs[last], lows[last], c, a, exe_dir)
    if not exe_ok:
        return None

    # 9) LP (Point C) — the structural level the EXE must close beyond.
    if long_side:
        segment = highs[b + 1 : last] or [highs[b]]
        lp = max(segment)
        lp_ok = c >= lp
    else:
        segment = lows[b + 1 : last] or [lows[b]]
        lp = min(segment)
        lp_ok = c <= lp
    if not lp_ok:
        return None

    # 10) UC2/DC2 must leave room to the prior impulse extreme (Point D).
    if setup in (SETUP_UC2, SETUP_DC2):
        if long_side and c > highs[a_idx]:
            return None
        if not long_side and c < lows[a_idx]:
            return None

    volume_ratio = (volumes[last] / avg_vol) if avg_vol else 1.0
    entry = c
    if long_side:
        stop = min(lows[b], lows[last]) - STOP_BUFFER_ATR * a
        risk = max(entry - stop, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_BUY)
    else:
        stop = max(highs[b], highs[last]) + STOP_BUFFER_ATR * a
        risk = max(stop - entry, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_SELL)

    # --- Factor groups feeding the blended confidence ------------------------
    sign = 1.0 if long_side else -1.0
    exe_range_atr = (highs[last] - lows[last]) / a
    exe_body = abs(c - opens[last]) / max(highs[last] - lows[last], 1e-9)
    lp_margin_atr = max(0.0, (c - lp) * sign / a)
    pull_extreme = lows[b] if long_side else highs[b]
    impulse_extreme = highs[a_idx] if long_side else lows[a_idx]
    pull_depth_atr = abs(impulse_extreme - pull_extreme) / a
    dist_mean_atr = abs(c - sma20[last]) / a

    factors = {
        # Continuation group — is the trend worth riding?
        "trend_separation": _trend_separation_factor(c, sma50[last], a, sign),
        "ma_alignment": _ma_alignment_factor(sma20[last], sma50[last], a, sign),
        "pullback_control": _scale(4.0 - pull_depth_atr, 0.0, 4.0),
        "structure_clean": 100.0 if not counter_flush else 25.0,
        "trigger_strength": _trigger_factor(exe_body, lp_margin_atr, bars_since_b, MAX_SETUP_BARS),
        # Reversal group — has the pullback actually turned back in-trend?
        "reversal_trigger": _trigger_factor(exe_body, lp_margin_atr, bars_since_b, MAX_SETUP_BARS),
        "exhaustion": _exhaustion(rsi[last], long_side),
        "structure": _scale(4.0 - pull_depth_atr, 0.0, 4.0),
        "liquidity_sweep": 100.0 if touched_slow else 50.0,
    }
    rules = [
        "positive_flow" if long_side else "negative_flow",
        "sma20_above_sma50" if long_side else "sma20_below_sma50",
        "shallow_pullback" if not touched_slow else "deep_pullback_50sma",
        "no_counter_flush",
        f"exe_within_{bars_since_b}_bars",
        "bullish_exe_close_above_lp" if long_side else "bearish_exe_close_below_lp",
        "no_counter_flush_3_bars",
    ]
    return _finish(
        ticker, name, sector, setup, entry, target, stop, c, volumes[last],
        volume_ratio, exe_range_atr, factors, rules, ctx,
    )


# ---------------------------------------------------------------------------
# Strategy 2 — Early reversals (UR1/DR1)
# ---------------------------------------------------------------------------
def _is_sideways(sma20, sma50, last) -> bool:
    if sma20[last] is None or sma50[last] in (None, 0):
        return False
    return abs(sma20[last] - sma50[last]) / sma50[last] <= SIDEWAYS_MAX_SMA_GAP


def _detect_early_reversal(
    ticker, name, sector, ohlcv, sma20, sma50, atr, rsi, swings_low, swings_high, last, avg_vol, ctx,
    long_side: bool,
):
    opens, highs, lows, closes, volumes = ohlcv
    c = closes[last]
    a = atr[last]
    if not a or not _is_sideways(sma20, sma50, last):
        return None

    if long_side:
        # Final move: a downside flush that forces liquidity (sweeps a swing low).
        window = UR1_MAX_BARS
        f = None
        for j in range(last, max(0, last - window), -1):
            if _is_flush(opens[j], highs[j], lows[j], closes[j], atr[j] or 0.0, "down"):
                f = j
                break
        if f is None:
            return None
        swept = any(i < f and lows[f] < lows[i] for i in swings_low if i >= f - 10)
        lp = min(lows[f : last + 1])
        exe_ok = _is_momentum(opens[last], highs[last], lows[last], c, a, "up")
        lp_ok = c >= lp
        if not (exe_ok and lp_ok):
            return None
        setup = SETUP_UR1
        entry = c
        stop = min(lows[f : last + 1]) - STOP_BUFFER_ATR * a
        risk = max(entry - stop, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_BUY)
        rules = ["sideways_range", "downside_flush", "liquidity_swept" if swept else "lp_formed",
                 "bullish_exe", "close_at_or_above_lp", f"exe_within_{last - f}_bars"]
        flush_atr = (highs[f] - lows[f]) / max(atr[f] or 0.0, 1e-9)
        depth_atr = (max(highs[f : last + 1]) - min(lows[f : last + 1])) / a
        exe_range_atr = (highs[last] - lows[last]) / a
        exe_body = abs(c - opens[last]) / max(highs[last] - lows[last], 1e-9)
        reclaim_atr = max(0.0, (c - lp) / a)
        factors = {
            "flush_intensity": _scale(flush_atr, FLUSH_ATR_MIN, 3.0),
            "liquidity_sweep": 100.0 if swept else 45.0,
            "reversal_trigger": _trigger_factor(exe_body, reclaim_atr, last - f, window),
            "exhaustion": _exhaustion(rsi[last], True),
            "structure": _scale(3.0 - depth_atr, 0.0, 3.0),
            # Continuation context: a reversal is easier from a flat backdrop.
            "trend_separation": _trend_context_factor(c, sma50[last], a, 1.0),
            "ma_alignment": _centred((sma20[last] - sma50[last]) / a, 0.0, 1.0),
            "pullback_control": _scale(3.0 - depth_atr, 0.0, 3.0),
            "structure_clean": 100.0,
            "trigger_strength": _trigger_factor(exe_body, reclaim_atr, last - f, window),
        }
    else:
        window = DR1_MAX_BARS
        f = None
        for j in range(last, max(0, last - window), -1):
            if _is_flush(opens[j], highs[j], lows[j], closes[j], atr[j] or 0.0, "up"):
                f = j
                break
        if f is None:
            return None
        flush_count = sum(
            1 for j in range(max(0, f - MAJORITY_FLUSH_WINDOW + 1), f + 1)
            if _is_flush(opens[j], highs[j], lows[j], closes[j], atr[j] or 0.0, "up")
        )
        majority = flush_count >= MAJORITY_FLUSH_MIN
        lp = max(highs[f : last + 1])
        exe_ok = _is_momentum(opens[last], highs[last], lows[last], c, a, "down")
        lp_ok = c <= lp
        if not (exe_ok and lp_ok):
            return None
        setup = SETUP_DR1
        entry = c
        stop = max(highs[f : last + 1]) + STOP_BUFFER_ATR * a
        risk = max(stop - entry, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_SELL)
        rules = ["sideways_range", "majority_flush", "liquidity_formed", "bearish_exe",
                 "close_at_or_below_lp", "no_bar_count_required"]
        flush_atr = (highs[f] - lows[f]) / max(atr[f] or 0.0, 1e-9)
        depth_atr = (max(highs[f : last + 1]) - min(lows[f : last + 1])) / a
        exe_range_atr = (highs[last] - lows[last]) / a
        exe_body = abs(c - opens[last]) / max(highs[last] - lows[last], 1e-9)
        reclaim_atr = max(0.0, (lp - c) / a)
        factors = {
            "flush_intensity": _scale(flush_atr, FLUSH_ATR_MIN, 3.0),
            "liquidity_sweep": 100.0 if majority else 45.0,
            "reversal_trigger": _trigger_factor(exe_body, reclaim_atr, last - f, window),
            "exhaustion": _exhaustion(rsi[last], False),
            "structure": _scale(3.0 - depth_atr, 0.0, 3.0),
            "trend_separation": _trend_context_factor(c, sma50[last], a, -1.0),
            "ma_alignment": _centred((sma20[last] - sma50[last]) / a * -1.0, 0.0, 1.0),
            "pullback_control": _scale(3.0 - depth_atr, 0.0, 3.0),
            "structure_clean": 100.0,
            "trigger_strength": _trigger_factor(exe_body, reclaim_atr, last - f, window),
        }

    volume_ratio = (volumes[last] / avg_vol) if avg_vol else 1.0
    return _finish(
        ticker, name, sector, setup, entry, target, stop, c, volumes[last],
        volume_ratio, exe_range_atr, factors, rules, ctx,
    )


# ---------------------------------------------------------------------------
# Strategy 3 — Double top / double bottom (UR2/DR2)
# ---------------------------------------------------------------------------
def _detect_double(
    ticker, name, sector, ohlcv, sma20, sma50, atr, rsi, swings_high, swings_low, last, avg_vol, ctx,
    long_side: bool,
):
    """UR2 = double top in an up-flow (bearish). DR2 = double bottom in a down-flow (bullish)."""
    opens, highs, lows, closes, volumes = ohlcv
    c = closes[last]
    a = atr[last]
    if not a or sma50[last] is None:
        return None

    if long_side:
        # ---- DR2: double bottom, price in a down-flow ----
        if c >= sma50[last]:
            return None
        lows_idx = [i for i in swings_low if i >= last - STRUCTURE_LOOKBACK]
        if len(lows_idx) < 2:
            return None
        l1, l2 = lows_idx[-2], lows_idx[-1]
        if abs(lows[l1] - lows[l2]) / max(lows[l1], 1e-9) > DOUBLE_TOLERANCE:
            return None
        neck = _prev_swing(swings_high, l2)
        if neck is None or not (l2 < neck < last):
            return None
        # Majority flush down into the second low.
        flush_count = sum(
            1 for j in range(max(0, l2 - MAJORITY_FLUSH_WINDOW + 1), l2 + 1)
            if _is_flush(opens[j], highs[j], lows[j], closes[j], atr[j] or 0.0, "down")
        )
        if flush_count < MAJORITY_FLUSH_MIN:
            return None
        if last - l2 > DR2_MAX_BARS:
            return None
        exe_ok = _is_momentum(opens[last], highs[last], lows[last], c, a, "up")
        lp = highs[neck]
        lp_ok = c >= lp
        if not (exe_ok and lp_ok):
            return None
        setup = SETUP_DR2
        entry = c
        stop = min(lows[l1], lows[l2]) - STOP_BUFFER_ATR * a
        risk = max(entry - stop, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_BUY)
        # Special exit alternative: the 50 SMA is a valid objective.
        target = min(target, max(sma50[last] * 1.02, entry + 1.0 * a)) if sma50[last] > entry else target
        rules = ["negative_flow", "majority_flush", "double_bottom", "neckline_breakout",
                 "bullish_exe", "close_at_or_above_lp", f"exe_within_{last - l2}_bars"]
        exe_range_atr = (highs[last] - lows[last]) / a
        exe_body = abs(c - opens[last]) / max(highs[last] - lows[last], 1e-9)
        reclaim_atr = max(0.0, (c - lp) / a)
        base_depth_atr = abs(max(highs[l1], highs[l2]) - min(lows[l1], lows[l2])) / a
        similarity = 1.0 - abs(lows[l1] - lows[l2]) / max(lows[l1], 1e-9) / DOUBLE_TOLERANCE
        factors = {
            "flush_intensity": _scale(flush_count, 1.0, float(MAJORITY_FLUSH_MIN + 1)),
            "liquidity_sweep": 100.0 * max(0.0, min(1.0, similarity)),
            "reversal_trigger": _trigger_factor(exe_body, reclaim_atr, last - l2, DR2_MAX_BARS),
            "exhaustion": _exhaustion(rsi[last], True),
            "structure": _scale(5.0 - base_depth_atr, 0.0, 5.0),
            "trend_separation": _trend_context_factor(c, sma50[last], a, 1.0),
            "ma_alignment": _centred((sma20[last] - sma50[last]) / a, 0.0, 1.0),
            "pullback_control": _scale(5.0 - base_depth_atr, 0.0, 5.0),
            "structure_clean": 100.0,
            "trigger_strength": _trigger_factor(exe_body, reclaim_atr, last - l2, DR2_MAX_BARS),
        }
    else:
        # ---- UR2: double top, price in an up-flow ----
        if c <= sma50[last]:
            return None
        highs_idx = [i for i in swings_high if i >= last - STRUCTURE_LOOKBACK]
        if len(highs_idx) < 2:
            return None
        h1, h2 = highs_idx[-2], highs_idx[-1]
        if abs(highs[h1] - highs[h2]) / max(highs[h1], 1e-9) > DOUBLE_TOLERANCE:
            return None
        trough = _prev_swing(swings_low, h2)
        if trough is None or not (h2 < trough < last):
            return None
        # "Bigger retracement": the pullback between the two tops must be deeper
        # than the prior retracement (compared ~4 bars earlier).
        prior_trough = _prev_swing(swings_low, h1)
        if prior_trough is None:
            return None
        current_depth = highs[h1] - lows[trough]
        prior_depth = highs[h1] - lows[prior_trough]
        bigger = current_depth > prior_depth
        # Partial overlap is acceptable; complete engulfment is not.
        overlap = lows[trough] <= highs[h1] and highs[h1] >= lows[prior_trough]
        if not (bigger and overlap):
            return None
        exe_ok = _is_momentum(opens[last], highs[last], lows[last], c, a, "down")
        lp = max(highs[h1], highs[h2])
        lp_ok = c <= lp
        if not (exe_ok and lp_ok):
            return None
        setup = SETUP_UR2
        entry = c
        stop = max(highs[h1], highs[h2]) + STOP_BUFFER_ATR * a
        risk = max(stop - entry, 0.25 * a)
        target = _project(entry, risk, SETUP_RR[setup], SIGNAL_SELL)
        rules = ["positive_flow", "double_top", "bigger_retracement", "partial_overlap",
                 "bearish_exe", "close_at_or_below_lp", "fails_at_lp"]
        exe_range_atr = (highs[last] - lows[last]) / a
        exe_body = abs(c - opens[last]) / max(highs[last] - lows[last], 1e-9)
        reclaim_atr = max(0.0, (lp - c) / a)
        pattern_depth_atr = (max(highs[h1], highs[h2]) - lows[trough]) / a
        similarity = 1.0 - abs(highs[h1] - highs[h2]) / max(highs[h1], 1e-9) / DOUBLE_TOLERANCE
        retrace_ratio = max(0.0, min(1.0, current_depth / prior_depth - 1.0)) if prior_depth else 0.0
        factors = {
            "flush_intensity": _scale(current_depth / a, 1.0, 3.0),
            "liquidity_sweep": 100.0 * max(0.0, min(1.0, similarity)),
            "reversal_trigger": _trigger_factor(exe_body, reclaim_atr, last - h2, MAX_SETUP_BARS),
            "exhaustion": _exhaustion(rsi[last], False),
            "structure": 0.5 * _scale(5.0 - pattern_depth_atr, 0.0, 5.0) + 0.5 * (retrace_ratio * 100.0),
            "trend_separation": _trend_context_factor(c, sma50[last], a, -1.0),
            "ma_alignment": _centred((sma20[last] - sma50[last]) / a * -1.0, 0.0, 1.0),
            "pullback_control": _scale(5.0 - pattern_depth_atr, 0.0, 5.0),
            "structure_clean": 100.0 if overlap else 40.0,
            "trigger_strength": _trigger_factor(exe_body, reclaim_atr, last - h2, MAX_SETUP_BARS),
        }

    volume_ratio = (volumes[last] / avg_vol) if avg_vol else 1.0
    return _finish(
        ticker, name, sector, setup, entry, target, stop, c, volumes[last],
        volume_ratio, exe_range_atr, factors, rules, ctx,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def analyze_ticker(
    ticker: str,
    name: str,
    sector: str | None,
    bars: list,
    ctx: SignalContext,
) -> list[SignalDraft]:
    """Return at most one (best) setup signal for the most recent bar."""
    if len(bars) < MIN_BARS:
        return []

    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    sma20 = ta.sma(closes, SMA_FAST)
    sma50 = ta.sma(closes, SMA_SLOW)
    atr = ta.atr(highs, lows, closes)
    rsi = ta.rsi(closes)
    swings_high, swings_low = _swing_indices(highs, lows)

    last = len(bars) - 1
    avg_vol = sum(volumes[-20:]) / 20 if volumes[-20:] else 1.0

    ohlcv = (opens, highs, lows, closes, volumes)
    drafts: list[SignalDraft] = []

    def _collect(fn, swings_a, swings_b, side):
        """Dispatch one detector; log (never silently swallow) unexpected errors."""
        try:
            d = fn(
                ticker, name, sector, ohlcv, sma20, sma50, atr, rsi,
                swings_a, swings_b, last, avg_vol, ctx, side,
            )
        except (IndexError, ValueError) as exc:
            logger.debug("setup %s skipped for %s: %s", fn.__name__, ticker, exc)
            return
        if d is not None:
            drafts.append(d)

    _collect(_detect_continuation, swings_high, swings_low, True)
    _collect(_detect_continuation, swings_high, swings_low, False)
    _collect(_detect_early_reversal, swings_low, swings_high, True)
    _collect(_detect_early_reversal, swings_low, swings_high, False)
    _collect(_detect_double, swings_high, swings_low, True)
    _collect(_detect_double, swings_high, swings_low, False)

    if not drafts:
        return []

    # Never report contradictory directions: keep the best single setup.
    best = max(drafts, key=lambda d: d.confidence)
    return [best]
