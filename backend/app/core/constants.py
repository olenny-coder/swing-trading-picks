"""Shared constants."""
from __future__ import annotations

# --- Signal direction --------------------------------------------------------
SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_TYPES = (SIGNAL_BUY, SIGNAL_SELL)

# --- Setups (SMA 20/50 flow system) -----------------------------------------
SETUP_UC1 = "UC1"  # bullish continuation, shallow pullback
SETUP_UC2 = "UC2"  # bullish continuation, deeper pullback
SETUP_DC1 = "DC1"  # bearish continuation, shallow pullback
SETUP_DC2 = "DC2"  # bearish continuation, deeper pullback
SETUP_UR1 = "UR1"  # early upside reversal off a downside flush
SETUP_DR1 = "DR1"  # early downside reversal off a majority flush
SETUP_UR2 = "UR2"  # double-top reversal (bearish)
SETUP_DR2 = "DR2"  # double-bottom reversal (bullish)

SETUPS = (
    SETUP_UC1, SETUP_UC2, SETUP_DC1, SETUP_DC2,
    SETUP_UR1, SETUP_DR1, SETUP_UR2, SETUP_DR2,
)

CONTINUATION_SETUPS = (SETUP_UC1, SETUP_UC2, SETUP_DC1, SETUP_DC2)
REVERSAL_SETUPS = (SETUP_UR1, SETUP_DR1, SETUP_UR2, SETUP_DR2)

DIRECTION_BY_SETUP: dict[str, str] = {
    SETUP_UC1: SIGNAL_BUY,
    SETUP_UC2: SIGNAL_BUY,
    SETUP_DC1: SIGNAL_SELL,
    SETUP_DC2: SIGNAL_SELL,
    SETUP_UR1: SIGNAL_BUY,
    SETUP_DR1: SIGNAL_SELL,
    SETUP_UR2: SIGNAL_SELL,
    SETUP_DR2: SIGNAL_BUY,
}

SETUP_LABELS: dict[str, str] = {
    SETUP_UC1: "Bullish continuation (shallow pullback)",
    SETUP_UC2: "Bullish continuation (deep pullback)",
    SETUP_DC1: "Bearish continuation (shallow pullback)",
    SETUP_DC2: "Bearish continuation (deep pullback)",
    SETUP_UR1: "Early upside reversal",
    SETUP_DR1: "Early downside reversal",
    SETUP_UR2: "Double-top reversal",
    SETUP_DR2: "Double-bottom reversal",
}

# Values used by releases before the SMA-20/50 setup engine (DB migration only).
LEGACY_SIGNAL_TYPES = ("BUY_STANDARD", "BUY_DOJI_REVERSAL", "PUT")
LEGACY_SETUP = "LEGACY"

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
