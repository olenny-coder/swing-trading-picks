"""Signal generation orchestration.

Loads bars from the DB, builds the macro/event context, runs the signal engine
across the universe, attaches put-option recommendations, and persists results.
Runs are idempotent per signal date.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..core.constants import SIGNAL_SELL, SIGNAL_TYPES
from ..core.signal_engine import MIN_BARS, analyze_ticker
from ..models import BacktestRun, Signal
from ..providers.base import MacroDataProvider, MarketDataProvider
from .data_service import latest_trading_day, load_bars, resolve_universe
from .macro_service import build_and_store_snapshot, build_signal_context, days_to_earnings
from .options_service import recommend_put

_BAR_WINDOW = timedelta(days=420)


def load_backtest_win_rates(db: Session) -> dict[str, float]:
    rates: dict[str, float] = {}
    for stype in SIGNAL_TYPES:
        row = (
            db.query(BacktestRun)
            .filter(BacktestRun.strategy == stype)
            .order_by(BacktestRun.created_at.desc())
            .first()
        )
        if row and isinstance(row.metrics.get("win_rate"), (int, float)):
            rates[stype] = float(row.metrics["win_rate"])
    return rates


def generate_signals(
    db: Session,
    market_provider: MarketDataProvider,
    macro_provider: MacroDataProvider,
    signal_date: date | None = None,
    allow_earnings_plays: bool = False,
    min_price: float = 5.0,
    min_volume: float = 500_000.0,
) -> dict:
    signal_date = signal_date or latest_trading_day(db) or date.today()

    # (Re)build the macro snapshot + context for this date.
    build_and_store_snapshot(db, market_provider, macro_provider, signal_date)
    rates = load_backtest_win_rates(db)
    ctx = build_signal_context(db, signal_date, rates, allow_earnings_plays)

    universe = resolve_universe(market_provider, min_price=min_price, min_volume=min_volume)
    start = signal_date - _BAR_WINDOW

    # Idempotent: replace today's signals.
    db.query(Signal).filter(Signal.date == signal_date).delete(synchronize_session=False)

    counts = {"BUY_STANDARD": 0, "BUY_DOJI_REVERSAL": 0, "SELL": 0, "total": 0}
    for meta in universe:
        bars = load_bars(db, meta.ticker, start, signal_date)
        if len(bars) < MIN_BARS:
            continue
        ctx.earnings_in_days = days_to_earnings(db, meta.ticker, signal_date)
        drafts = analyze_ticker(meta.ticker, meta.name, meta.sector, bars, ctx)
        for d in drafts:
            option_rec = None
            if d.type == SIGNAL_SELL:
                option_rec = recommend_put(market_provider, d.ticker, d.price, d.target, d.stop)
                if option_rec is not None:
                    d.event_flags["options_liquid"] = True
                else:
                    # Keep the bearish setup even when no options chain is
                    # available (e.g. no options subscription); flag it so the
                    # UI can show the underlying levels without a contract.
                    d.event_flags["options_data"] = "unavailable"

            signal = Signal(
                ticker=d.ticker,
                name=d.name,
                date=signal_date,
                type=d.type,
                entry=d.entry,
                target=d.target,
                stop=d.stop,
                confidence=d.confidence,
                price=d.price,
                sector=d.sector,
                confidence_components=d.confidence_components,
                triggered_rules=d.triggered_rules,
                event_flags=d.event_flags,
                option_recommendation=option_rec,
            )
            db.add(signal)
            counts[d.type] = counts.get(d.type, 0) + 1
            counts["total"] += 1

    db.commit()
    return counts
