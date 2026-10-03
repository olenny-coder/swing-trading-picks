"""Signal engine entrypoint.

The engine was replaced by the SMA 20/50 flow-based setup system; this module
re-exports its public surface so existing imports keep working.
"""
from __future__ import annotations

from .sma_strategy import (  # noqa: F401
    DEFAULT_BACKTEST_WIN_RATES,
    MAX_RISK_PCT,
    MIN_BARS,
    SETUP_RR,
    SMA_FAST,
    SMA_SLOW,
    SignalDraft,
    analyze_ticker,
)

__all__ = [
    "DEFAULT_BACKTEST_WIN_RATES",
    "MAX_RISK_PCT",
    "MIN_BARS",
    "SETUP_RR",
    "SMA_FAST",
    "SMA_SLOW",
    "SignalDraft",
    "analyze_ticker",
]
