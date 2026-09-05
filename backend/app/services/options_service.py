"""Options recommendation for bearish (PUT) signals.

Finds the most liquid near-the-money put, applies the liquidity filter
(open interest > 100, bid/ask spread < 5%), and derives option-level
entry/target/stop from the underlying signal.
"""
from __future__ import annotations

from ..providers.base import MarketDataProvider, OptionContract


def is_liquid(contract: OptionContract, min_oi: int = 100, max_spread_pct: float = 5.0) -> bool:
    if contract.open_interest is None or contract.open_interest <= min_oi:
        return False
    if contract.spread_pct is None or contract.spread_pct > max_spread_pct:
        return False
    return True


def recommend_put(
    provider: MarketDataProvider,
    ticker: str,
    underlying_price: float,
    underlying_target: float,
    underlying_stop: float,
) -> dict | None:
    """Return a recommended put contract dict, or None if no liquid contract."""
    chain = provider.get_options_chain(ticker, side="put")
    liquid = [c for c in chain if is_liquid(c)]
    if not liquid:
        return None

    # Nearest strike at/below the underlying (ATM or one step OTM).
    target_strike = min(liquid, key=lambda c: abs(c.strike - underlying_price))
    liquid_below = [c for c in liquid if c.strike <= underlying_price]
    chosen = min(liquid_below, key=lambda c: underlying_price - c.strike) if liquid_below else target_strike

    premium = chosen.mid or chosen.last or 0.05
    premium = max(premium, 0.01)
    option_target = premium * 2.0
    option_stop = premium * 0.5

    return {
        "symbol": chosen.symbol,
        "strike": chosen.strike,
        "expiry": chosen.expiry.isoformat() if chosen.expiry else None,
        "bid": chosen.bid,
        "ask": chosen.ask,
        "premium": round(premium, 2),
        "open_interest": chosen.open_interest,
        "implied_volatility": chosen.implied_volatility,
        "option_entry": round(premium, 2),
        "option_target": round(option_target, 2),
        "option_stop": round(option_stop, 2),
        "underlying_entry": round(underlying_price, 2),
        "underlying_target": round(underlying_target, 2),
        "underlying_stop": round(underlying_stop, 2),
        "liquid": True,
    }
