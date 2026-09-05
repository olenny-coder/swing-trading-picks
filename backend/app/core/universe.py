"""Curated liquid-US-equity universe (ticker, name, GICS sector).

This is the default universe used for ingestion and signal generation by BOTH
the MOCK and Alpaca providers, so the daily pull stays small (~115 well-known,
highly-liquid names) and well within Alpaca's free-tier rate limits. Extend this
list to track more names.
"""
from __future__ import annotations

UNIVERSE: list[tuple[str, str, str]] = [
    # Technology
    ("AAPL", "Apple Inc.", "Technology"), ("MSFT", "Microsoft Corp.", "Technology"),
    ("NVDA", "NVIDIA Corp.", "Technology"), ("GOOGL", "Alphabet Inc.", "Technology"),
    ("META", "Meta Platforms", "Technology"), ("AVGO", "Broadcom Inc.", "Technology"),
    ("ORCL", "Oracle Corp.", "Technology"), ("CRM", "Salesforce Inc.", "Technology"),
    ("ADBE", "Adobe Inc.", "Technology"), ("AMD", "Advanced Micro Devices", "Technology"),
    ("INTC", "Intel Corp.", "Technology"), ("CSCO", "Cisco Systems", "Technology"),
    ("QCOM", "Qualcomm Inc.", "Technology"), ("TXN", "Texas Instruments", "Technology"),
    ("AMAT", "Applied Materials", "Technology"), ("MU", "Micron Technology", "Technology"),
    ("NOW", "ServiceNow Inc.", "Technology"), ("IBM", "IBM Corp.", "Technology"),
    ("PLTR", "Palantir Technologies", "Technology"), ("SNOW", "Snowflake Inc.", "Technology"),
    # Financials
    ("JPM", "JPMorgan Chase", "Financials"), ("BAC", "Bank of America", "Financials"),
    ("WFC", "Wells Fargo", "Financials"), ("GS", "Goldman Sachs", "Financials"),
    ("MS", "Morgan Stanley", "Financials"), ("C", "Citigroup Inc.", "Financials"),
    ("SCHW", "Charles Schwab", "Financials"), ("BLK", "BlackRock Inc.", "Financials"),
    ("AXP", "American Express", "Financials"), ("V", "Visa Inc.", "Financials"),
    ("MA", "Mastercard Inc.", "Financials"), ("PYPL", "PayPal Holdings", "Financials"),
    ("COIN", "Coinbase Global", "Financials"),
    # Healthcare
    ("UNH", "UnitedHealth Group", "Healthcare"), ("JNJ", "Johnson & Johnson", "Healthcare"),
    ("LLY", "Eli Lilly & Co.", "Healthcare"), ("PFE", "Pfizer Inc.", "Healthcare"),
    ("MRK", "Merck & Co.", "Healthcare"), ("ABBV", "AbbVie Inc.", "Healthcare"),
    ("TMO", "Thermo Fisher", "Healthcare"), ("ABT", "Abbott Labs", "Healthcare"),
    ("DHR", "Danaher Corp.", "Healthcare"), ("ISRG", "Intuitive Surgical", "Healthcare"),
    ("BMY", "Bristol-Myers Squibb", "Healthcare"), ("GILD", "Gilead Sciences", "Healthcare"),
    ("AMGN", "Amgen Inc.", "Healthcare"), ("CVS", "CVS Health", "Healthcare"),
    # Energy
    ("XOM", "Exxon Mobil", "Energy"), ("CVX", "Chevron Corp.", "Energy"),
    ("COP", "ConocoPhillips", "Energy"), ("SLB", "Schlumberger", "Energy"),
    ("EOG", "EOG Resources", "Energy"), ("MPC", "Marathon Petroleum", "Energy"),
    ("PSX", "Phillips 66", "Energy"), ("OXY", "Occidental Petroleum", "Energy"),
    ("VLO", "Valero Energy", "Energy"), ("WMB", "Williams Companies", "Energy"),
    # Consumer Discretionary
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary"), ("TSLA", "Tesla Inc.", "Consumer Discretionary"),
    ("HD", "Home Depot", "Consumer Discretionary"), ("MCD", "McDonald's Corp.", "Consumer Discretionary"),
    ("NKE", "Nike Inc.", "Consumer Discretionary"), ("SBUX", "Starbucks Corp.", "Consumer Discretionary"),
    ("LOW", "Lowe's Companies", "Consumer Discretionary"), ("TJX", "TJX Companies", "Consumer Discretionary"),
    ("BKNG", "Booking Holdings", "Consumer Discretionary"), ("CMG", "Chipotle Mexican Grill", "Consumer Discretionary"),
    ("DIS", "Walt Disney Co.", "Consumer Discretionary"), ("RCL", "Royal Caribbean", "Consumer Discretionary"),
    # Consumer Staples
    ("WMT", "Walmart Inc.", "Consumer Staples"), ("PG", "Procter & Gamble", "Consumer Staples"),
    ("KO", "Coca-Cola Co.", "Consumer Staples"), ("PEP", "PepsiCo Inc.", "Consumer Staples"),
    ("COST", "Costco Wholesale", "Consumer Staples"), ("PM", "Philip Morris", "Consumer Staples"),
    ("MO", "Altria Group", "Consumer Staples"), ("CL", "Colgate-Palmolive", "Consumer Staples"),
    ("TGT", "Target Corp.", "Consumer Staples"), ("MDLZ", "Mondelez International", "Consumer Staples"),
    # Industrials
    ("CAT", "Caterpillar Inc.", "Industrials"), ("DE", "Deere & Co.", "Industrials"),
    ("GE", "GE Aerospace", "Industrials"), ("HON", "Honeywell Intl", "Industrials"),
    ("BA", "Boeing Co.", "Industrials"), ("UPS", "United Parcel Service", "Industrials"),
    ("RTX", "RTX Corp.", "Industrials"), ("LMT", "Lockheed Martin", "Industrials"),
    ("UNP", "Union Pacific", "Industrials"), ("EMR", "Emerson Electric", "Industrials"),
    ("ETN", "Eaton Corp.", "Industrials"),
    # Materials
    ("LIN", "Linde plc", "Materials"), ("FCX", "Freeport-McMoRan", "Materials"),
    ("NEM", "Newmont Corp.", "Materials"), ("DOW", "Dow Inc.", "Materials"),
    ("APD", "Air Products", "Materials"), ("SHW", "Sherwin-Williams", "Materials"),
    ("ECL", "Ecolab Inc.", "Materials"),
    # Utilities
    ("NEE", "NextEra Energy", "Utilities"), ("DUK", "Duke Energy", "Utilities"),
    ("SO", "Southern Company", "Utilities"), ("AEP", "American Electric Power", "Utilities"),
    ("EXC", "Exelon Corp.", "Utilities"), ("SRE", "Sempra Energy", "Utilities"),
    # Real Estate
    ("PLD", "Prologis Inc.", "Real Estate"), ("AMT", "American Tower", "Real Estate"),
    ("SPG", "Simon Property Group", "Real Estate"), ("EQIX", "Equinix Inc.", "Real Estate"),
    ("WELL", "Welltower Inc.", "Real Estate"),
    # Communication Services
    ("NFLX", "Netflix Inc.", "Communication Services"), ("T", "AT&T Inc.", "Communication Services"),
    ("VZ", "Verizon Communications", "Communication Services"), ("TMUS", "T-Mobile US", "Communication Services"),
    ("CMCSA", "Comcast Corp.", "Communication Services"), ("CHTR", "Charter Communications", "Communication Services"),
]

# Convenience lookups.
UNIVERSE_TICKERS: list[str] = [t for t, _, _ in UNIVERSE]
NAME_BY_TICKER: dict[str, str] = {t: n for t, n, _ in UNIVERSE}
SECTOR_BY_TICKER: dict[str, str] = {t: s for t, _, s in UNIVERSE}
