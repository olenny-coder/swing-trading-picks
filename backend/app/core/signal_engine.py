"""Signal generation engine.

Pure, deterministic, and independent of the database or any concrete provider:
``analyze_ticker`` consumes a chronological list of daily ``Bar`` objects plus a
``SignalContext`` and returns zero or one ``SignalDraft``.

Signal types:
- BUY_STANDARD      — trend/momentum breakout.
- BUY_DOJI_REVERSAL — doji after a downtrend, confirmed by a bullish reversal.
- SELL              — bearish breakdown (executed by buying put options).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import confidence, indicators as ta
from .base_types import SignalContext
from .constants import SIGNAL_BUY_DOJI_REVERSAL, SIGNAL_BUY_STANDARD, SIGNAL_SELL
from .regime import is_rate_sensitive

DEFAULT_BACKTEST_WIN_RATES = {
    SIGNAL_BUY_STANDARD: 0.58,
    SIGNAL_BUY_DOJI_REVERSAL: 0.55,
    SIGNAL_SELL: 0.52,
}

MIN_BARS = 60

# RSI bands. The spec's guidance is 40-70 (buy) / 30-60 (put); the upper/lower
# edge is relaxed by 2 points so genuine 20-day-high momentum breakouts are not
# excluded purely for being mildly overbought/oversold. Tunable per strategy.
BUY_RSI_LOW = 40.0
BUY_RSI_HIGH = 72.0
PUT_RSI_LOW = 28.0
PUT_RSI_HIGH = 60.0

# Minimum confluence for a candidate to be emitted. Signals are score-based:
# a candidate only needs a MINIMUM number of conditions (not all) to surface, so
# real market data always produces a ranked shortlist. Confidence scales with
# how many conditions are met.
MIN_BUY_CONDITIONS = 3  # of 6
MIN_PUT_CONDITIONS = 3  # of 6
MIN_DOJI_CONDITIONS = 3  # of 6 (the doji candle itself is one of them)


@dataclass
class SignalDraft:
    ticker: str
    name: str
    sector: str | None
    type: str
    entry: float
    target: float
    stop: float
    price: float
    volume: float
    confidence: float
    confidence_components: dict
    triggered_rules: list[str]
    event_flags: dict


def analyze_ticker(
    ticker: str,
    name: str,
    sector: str | None,
    bars: list,
    ctx: SignalContext,
) -> list[SignalDraft]:
    """Return any signal triggered on the most recent bar (may be empty)."""
    if len(bars) < MIN_BARS:
        return []

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    opens = [b.open for b in bars]

    ema20 = ta.ema(closes, 20)
    ema50 = ta.ema(closes, 50)
    macd_line, signal_line, hist = ta.macd(closes)
    rsi14 = ta.rsi(closes)
    atr14 = ta.atr(highs, lows, closes)

    n = len(bars)
    last = n - 1
    avg_vol = sum(volumes[-20:]) / 20 if volumes[-20:] else 1.0
    atr = atr14[last] or (closes[last] * 0.02)

    drafts: list[SignalDraft] = []

    # --- BUY_STANDARD -------------------------------------------------------
    buy = _evaluate_buy_standard(
        ticker, name, sector, closes, highs, lows, opens, volumes,
        ema20, ema50, macd_line, signal_line, hist, rsi14, atr, avg_vol, last, ctx,
    )
    if buy is not None:
        drafts.append(buy)

    # --- BUY_DOJI_REVERSAL --------------------------------------------------
    doji = _evaluate_doji(
        ticker, name, sector, closes, highs, lows, opens, volumes,
        ema20, macd_line, signal_line, rsi14, atr, avg_vol, last, ctx,
    )
    if doji is not None:
        drafts.append(doji)

    # --- SELL (bearish) ------------------------------------------------------
    sell = _evaluate_sell(
        ticker, name, sector, closes, highs, lows, opens, volumes,
        ema20, ema50, macd_line, signal_line, hist, rsi14, atr, avg_vol, last, ctx,
    )
    if sell is not None:
        drafts.append(sell)

    return drafts


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------
def _regime_subscore(signal_type: str, regime: str) -> float:
    if signal_type == SIGNAL_SELL:
        return 90.0 if regime == "bearish" else (70.0 if regime == "neutral" else 30.0)
    return 90.0 if regime == "bullish" else (70.0 if regime == "neutral" else 30.0)


def _sector_subscore(signal_type: str, sector: str | None, ctx: SignalContext) -> float:
    if not sector:
        return 60.0
    if signal_type == SIGNAL_SELL:
        if sector in ctx.lagging_sectors:
            return 85.0
        if sector in ctx.leading_sectors:
            return 40.0
        return 60.0
    if sector in ctx.leading_sectors:
        return 85.0
    if sector in ctx.lagging_sectors:
        return 40.0
    return 60.0


def _volume_subscore(ratio: float) -> float:
    return min(100.0, ratio / 2.0 * 100.0)


def _macro_subscore(sector: str | None, ctx: SignalContext) -> float:
    score = 100.0
    if ctx.high_impact_events_within_2d:
        score -= 20.0
    if ctx.rate_rising_sharply and is_rate_sensitive(sector):
        score -= 20.0
    if ctx.earnings_in_days is not None and ctx.earnings_in_days <= 7:
        score -= 20.0
    # Economic-calendar sentiment: net positive/negative upcoming events nudge
    # the score by up to +/-15 points.
    score += max(-15.0, min(15.0, ctx.macro_sentiment * 15.0))
    return max(0.0, min(100.0, score))


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
    """Suppress a signal inside the earnings window unless it is high-conviction
    and the user opted into earnings plays."""
    if ctx.earnings_in_days is None or ctx.earnings_in_days > 7:
        return False
    if ctx.allow_earnings_plays and conf > 80.0:
        return False
    return True


def _finish(
    ticker, name, sector, type_, entry, target, stop, price, volume,
    technical, volume_ratio, triggered, ctx,
) -> SignalDraft | None:
    subs = {
        "technical": technical,
        "backtest": ctx.backtest_win_rates.get(type_, DEFAULT_BACKTEST_WIN_RATES[type_]) * 100.0,
        "regime": _regime_subscore(type_, ctx.regime),
        "sector": _sector_subscore(type_, sector, ctx),
        "volume": _volume_subscore(volume_ratio),
        "macro": _macro_subscore(sector, ctx),
    }
    conf = confidence.compute_confidence(subs)
    if _earnings_suppressed(ctx, conf):
        return None
    flags = _base_event_flags(sector, ctx)
    flags["confidence_label"] = confidence.confidence_label(conf)
    return SignalDraft(
        ticker=ticker,
        name=name,
        sector=sector,
        type=type_,
        entry=round(entry, 2),
        target=round(target, 2),
        stop=round(stop, 2),
        price=round(price, 2),
        volume=volume,
        confidence=conf,
        confidence_components=subs,
        triggered_rules=triggered,
        event_flags=flags,
    )


# ---------------------------------------------------------------------------
# BUY_STANDARD
# ---------------------------------------------------------------------------
def _evaluate_buy_standard(
    ticker, name, sector, closes, highs, lows, opens, volumes,
    ema20, ema50, macd_line, signal_line, hist, rsi14, atr, avg_vol, last, ctx,
) -> SignalDraft | None:
    c = closes[last]
    e20, e50 = ema20[last], ema50[last]
    if e20 is None or e50 is None or rsi14[last] is None or hist[last] is None:
        return None

    prior_highs = highs[last - 20 : last]
    if not prior_highs:
        return None
    prior_20d_high = max(prior_highs)

    conditions = {
        "price_above_ema50": c > e50,
        "ema20_above_ema50": e20 > e50,
        "macd_bullish_cross": ta.crossed_above(macd_line, signal_line, within=3),
        "rsi_in_40_70": BUY_RSI_LOW <= rsi14[last] <= BUY_RSI_HIGH,
        "volume_surge": volumes[last] > 1.5 * avg_vol,
        "breakout_20d_high": c > prior_20d_high,
    }
    met = sum(1 for v in conditions.values() if v)
    if met < MIN_BUY_CONDITIONS:
        return None

    volume_ratio = volumes[last] / avg_vol if avg_vol else 1.0
    technical = met / len(conditions) * 100.0

    entry = c
    stop = min(lows[last - 10 : last + 1]) if lows[last - 10 : last + 1] else entry - 1.5 * atr
    stop = min(stop, entry - 1.5 * atr)
    resistance = max(highs[last - 20 : last + 1]) if highs[last - 20 : last + 1] else entry + 2.5 * atr
    target = entry + 2.5 * atr
    if resistance > entry:
        target = min(target, resistance)
    if target <= entry:
        target = entry + 2.5 * atr

    triggered = [k for k, v in conditions.items() if v]
    return _finish(
        ticker, name, sector, SIGNAL_BUY_STANDARD, entry, target, stop,
        c, volumes[last], technical, volume_ratio, triggered, ctx,
    )


# ---------------------------------------------------------------------------
# BUY_DOJI_REVERSAL
# ---------------------------------------------------------------------------
def _evaluate_doji(
    ticker, name, sector, closes, highs, lows, opens, volumes,
    ema20, macd_line, signal_line, rsi14, atr, avg_vol, last, ctx,
) -> SignalDraft | None:
    if last < 1:
        return None
    doji_idx = last - 1
    doji_bar_open = opens[doji_idx]
    doji_high = highs[doji_idx]
    doji_low = lows[doji_idx]
    doji_close = closes[doji_idx]

    is_doji_candle = ta.is_doji(doji_bar_open, doji_high, doji_low, doji_close)
    if not is_doji_candle:
        return None

    e20_doji = ema20[doji_idx]
    downtrend = (e20_doji is not None and doji_close < e20_doji) or lows[doji_idx] < lows[doji_idx - 1]

    conf_low = lows[last]
    conf_close = closes[last]
    conf_high = highs[last]
    conf_open = opens[last]
    dips_below_doji_low = conf_low <= doji_low
    closes_above_doji_low = conf_close > doji_low
    upper_half_close = conf_close >= (conf_high + conf_low) / 2.0
    volume_ok = volumes[last] > 1.2 * avg_vol

    conditions = {
        "doji_candle": is_doji_candle,
        "after_downtrend": downtrend,
        "dips_below_doji_low": dips_below_doji_low,
        "closes_above_doji_low": closes_above_doji_low,
        "close_in_upper_half": upper_half_close,
        "reversal_volume": volume_ok,
    }
    met = sum(1 for v in conditions.values() if v)
    if met < MIN_DOJI_CONDITIONS:
        return None

    volume_ratio = volumes[last] / avg_vol if avg_vol else 1.0
    technical = met / len(conditions) * 100.0

    entry = doji_low + 0.01
    swing_low = min(lows[last - 5 : last + 1]) if lows[last - 5 : last + 1] else entry - 1.5 * atr
    stop = max(swing_low, entry - 1.5 * atr)
    resistance = max(highs[last - 20 : last + 1]) if highs[last - 20 : last + 1] else entry + 3.0 * atr
    target = entry + 2.5 * atr
    if resistance > entry:
        target = min(target, resistance)
    target = max(target, entry + 2.0 * atr)

    triggered = [k for k, v in conditions.items() if v]
    return _finish(
        ticker, name, sector, SIGNAL_BUY_DOJI_REVERSAL, entry, target, stop,
        conf_close, volumes[last], technical, volume_ratio, triggered, ctx,
    )


# ---------------------------------------------------------------------------
# SELL (bearish; executed by buying put options)
# ---------------------------------------------------------------------------
def _evaluate_sell(
    ticker, name, sector, closes, highs, lows, opens, volumes,
    ema20, ema50, macd_line, signal_line, hist, rsi14, atr, avg_vol, last, ctx,
) -> SignalDraft | None:
    c = closes[last]
    e20, e50 = ema20[last], ema50[last]
    if e20 is None or e50 is None or rsi14[last] is None or hist[last] is None:
        return None

    prior_lows = lows[last - 20 : last]
    if not prior_lows:
        return None
    prior_20d_low = min(prior_lows)

    conditions = {
        "price_below_ema50": c < e50,
        "ema20_below_ema50": e20 < e50,
        "macd_bearish_cross": ta.crossed_below(macd_line, signal_line, within=3),
        "rsi_in_30_60": PUT_RSI_LOW <= rsi14[last] <= PUT_RSI_HIGH,
        "volume_surge": volumes[last] > 1.5 * avg_vol,
        "breakdown_20d_low": c < prior_20d_low,
    }
    met = sum(1 for v in conditions.values() if v)
    if met < MIN_PUT_CONDITIONS:
        return None

    volume_ratio = volumes[last] / avg_vol if avg_vol else 1.0
    technical = met / len(conditions) * 100.0

    entry = c
    stop = max(highs[last - 10 : last + 1]) if highs[last - 10 : last + 1] else entry + 1.5 * atr
    stop = max(stop, entry + 1.5 * atr)
    support = min(lows[last - 20 : last + 1]) if lows[last - 20 : last + 1] else entry - 2.5 * atr
    target = entry - 2.5 * atr
    if support < entry:
        target = max(target, support)
    if target >= entry:
        target = entry - 2.5 * atr

    triggered = [k for k, v in conditions.items() if v]
    return _finish(
        ticker, name, sector, SIGNAL_SELL, entry, target, stop,
        c, volumes[last], technical, volume_ratio, triggered, ctx,
    )
