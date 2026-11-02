"""Shared constants."""
from __future__ import annotations

# --- Signal direction --------------------------------------------------------
SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_TYPES = (SIGNAL_BUY, SIGNAL_SELL)

# --- Setups -----------------------------------------------------------------
#: The only strategy the app runs: a 1D break of structure with a fair value gap
#: behind it, refined on the 4-hour chart. Picks are stored under this setup, so
#: History is exactly what the screener raised.
SETUP_SMC = "SMC"

#: The SMA 20/50 flow-system codes (UC1/DC1/UR1/DR1 …) were retired with that
#: engine. They are not listed, filtered on, or counted anywhere any more — the
#: four names below exist only so the retired ``sma_strategy`` module still imports.
SETUP_UC1 = "UC1"
SETUP_UC2 = "UC2"
SETUP_DC1 = "DC1"
SETUP_DC2 = "DC2"
SETUP_UR1 = "UR1"
SETUP_DR1 = "DR1"
SETUP_UR2 = "UR2"
SETUP_DR2 = "DR2"

SETUPS = (SETUP_SMC,)

CONTINUATION_SETUPS: tuple[str, ...] = ()
REVERSAL_SETUPS: tuple[str, ...] = ()

#: Only the retired SMA engine reads this; SMC direction comes from the break of
#: structure, per pick.
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
    SETUP_SMC: "SMC — 1D break of structure + fair value gap, 4H refinement",
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
