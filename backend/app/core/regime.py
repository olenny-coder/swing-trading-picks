"""Market-regime classification and sector-rotation helpers.

Regime drives the buy/put bias and the confidence system; sector relative
strength adds a rotation bonus/penalty.
"""
from __future__ import annotations

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

# Sectors most sensitive to a sharp rise in long-end yields.
RATE_SENSITIVE_SECTORS = {"Utilities", "Real Estate", "Technology", "Consumer Discretionary"}


def classify_regime(
    spy_close: float | None, spy_ma200: float | None, vix: float | None = None
) -> str:
    """bullish / bearish / neutral from SPY vs its 200-day MA and VIX."""
    if spy_close is None or spy_ma200 is None:
        return NEUTRAL
    above = spy_close > spy_ma200
    if vix is None:
        return BULLISH if above else BEARISH
    if above and vix <= 20:
        return BULLISH
    if (not above) or vix >= 28:
        return BEARISH
    return NEUTRAL


def yield_curve_slope(ten_year_yield: float | None, fed_funds_rate: float | None) -> float | None:
    """10Y minus Fed Funds (positive = normal/steep, negative = inverted)."""
    if ten_year_yield is None or fed_funds_rate is None:
        return None
    return ten_year_yield - fed_funds_rate


def sector_relative_strength(
    sector_closes: dict[str, list[float]], lookback: int = 20
) -> dict[str, float]:
    """Return percentage change over ``lookback`` bars for each sector."""
    out: dict[str, float] = {}
    for name, closes in sector_closes.items():
        if len(closes) < 2:
            out[name] = 0.0
            continue
        start = closes[max(0, len(closes) - lookback)]
        end = closes[-1]
        out[name] = (end - start) / start * 100.0 if start else 0.0
    return out


def leading_sectors(strength: dict[str, float], n: int = 3) -> set[str]:
    return {k for k, _ in sorted(strength.items(), key=lambda kv: kv[1], reverse=True)[:n]}


def lagging_sectors(strength: dict[str, float], n: int = 3) -> set[str]:
    return {k for k, _ in sorted(strength.items(), key=lambda kv: kv[1])[:n]}


def is_rate_sensitive(sector: str | None) -> bool:
    return sector in RATE_SENSITIVE_SECTORS
