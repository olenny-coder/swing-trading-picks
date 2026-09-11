"""Shared constants."""
from __future__ import annotations

SIGNAL_BUY_STANDARD = "BUY_STANDARD"
SIGNAL_BUY_DOJI_REVERSAL = "BUY_DOJI_REVERSAL"
SIGNAL_SELL = "SELL"  # bearish signal, executed by buying put options
# Backwards-compatible alias (older data/code referenced "PUT").
SIGNAL_PUT = SIGNAL_SELL
SIGNAL_TYPES = (SIGNAL_BUY_STANDARD, SIGNAL_BUY_DOJI_REVERSAL, SIGNAL_SELL)
# Signal-type values used before the PUT -> SELL rename (for DB migration).
LEGACY_SIGNAL_PUT = "PUT"

CONFIDENCE_LOW = "Low"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_HIGH = "High"

# Sector ETF -> GICS sector name (used for sector-rotation / heatmap analysis).
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}
