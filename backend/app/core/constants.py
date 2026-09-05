"""Shared constants."""
from __future__ import annotations

SIGNAL_BUY_STANDARD = "BUY_STANDARD"
SIGNAL_BUY_DOJI_REVERSAL = "BUY_DOJI_REVERSAL"
SIGNAL_PUT = "PUT"
SIGNAL_TYPES = (SIGNAL_BUY_STANDARD, SIGNAL_BUY_DOJI_REVERSAL, SIGNAL_PUT)

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
