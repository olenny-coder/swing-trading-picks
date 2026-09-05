"""Core types shared across the analytical modules (no DB / provider deps)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignalContext:
    """Market/event context that modulates signal generation and confidence."""

    regime: str = "neutral"  # bullish | bearish | neutral
    vix: float | None = None
    leading_sectors: set[str] = field(default_factory=set)
    lagging_sectors: set[str] = field(default_factory=set)
    rate_rising_sharply: bool = False
    high_impact_events_within_2d: bool = False
    macro_sentiment: float = 0.0  # net upcoming economic sentiment, -1.0 .. 1.0
    earnings_in_days: int | None = None  # days to next earnings, None if unknown
    allow_earnings_plays: bool = False
    backtest_win_rates: dict[str, float] = field(default_factory=dict)
