"""Signal generation orchestration.

Loads bars from the DB, builds the macro/event context, runs the signal engine
across the universe for each requested timeframe (daily, weekly, monthly),
attaches put-option recommendations, and persists results. Runs are idempotent
per (timeframe, candle date).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..core.constants import SETUPS, SIGNAL_SELL
from ..core.signal_engine import analyze_ticker
from ..core.timeframes import TIMEFRAMES, lookback_days, min_bars, normalise, resample
from ..models import BacktestRun, Signal
from ..providers.base import MacroDataProvider, MarketDataProvider
from .data_service import latest_trading_day, load_bars, resolve_universe
from .macro_service import build_and_store_snapshot, build_signal_context, days_to_earnings
from .options_service import recommend_put


def load_backtest_win_rates(db: Session) -> dict[str, float]:
    rates: dict[str, float] = {}
    for stype in SETUPS:
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
    timeframes: tuple[str, ...] = TIMEFRAMES,
) -> dict:
    """Generate picks for each requested timeframe.

    The same rules are read on daily, weekly and monthly candles, so a single
    refresh produces three independent lists. ``signal_date`` anchors the daily
    pass; higher timeframes are stamped with the date of the completed candle
    they were read from.
    """
    requested = tuple(normalise(tf) for tf in (timeframes or TIMEFRAMES))
    anchor = signal_date or latest_trading_day(db) or date.today()

    # (Re)build the macro snapshot + context once, from the anchor date.
    build_and_store_snapshot(db, market_provider, macro_provider, anchor)
    rates = load_backtest_win_rates(db)
    ctx = build_signal_context(db, anchor, rates, allow_earnings_plays)

    universe = resolve_universe(market_provider, min_price=min_price, min_volume=min_volume)

    counts = {s: 0 for s in SETUPS}
    counts.update({"BUY": 0, "SELL": 0, "total": 0})
    by_timeframe: dict[str, dict] = {}

    for timeframe in requested:
        window = timedelta(days=lookback_days(timeframe))
        start = anchor - window
        minimum = min_bars(timeframe)
        ctx.timeframe = timeframe
        tf_counts = {s: 0 for s in SETUPS}
        tf_counts.update({"BUY": 0, "SELL": 0, "total": 0})

        # Analyse first, then replace this timeframe's rows in one go: the
        # DELETE must not race the new rows, and it is scoped to (timeframe,
        # date) so a weekly and a daily list sharing a date never clobber each
        # other.
        pending: list[tuple[object, dict | None, date]] = []
        stamp: date | None = None
        for meta in universe:
            daily_bars = load_bars(db, meta.ticker, start, anchor)
            bars = resample(daily_bars, timeframe)
            if len(bars) < minimum:
                continue
            candle_date = bars[-1].date
            stamp = stamp or candle_date
            ctx.earnings_in_days = days_to_earnings(db, meta.ticker, candle_date)
            for draft in analyze_ticker(meta.ticker, meta.name, meta.sector, bars, ctx):
                option_rec = None
                if draft.direction == SIGNAL_SELL:
                    option_rec = recommend_put(
                        market_provider, draft.ticker, draft.price, draft.target, draft.stop
                    )
                    if option_rec is not None:
                        draft.event_flags["options_liquid"] = True
                    else:
                        # Keep the bearish setup even when no options chain is
                        # available (e.g. no options subscription); flag it so
                        # the UI can show the underlying levels without a
                        # contract.
                        draft.event_flags["options_data"] = "unavailable"
                pending.append((draft, option_rec, candle_date))

        if stamp is not None:
            db.query(Signal).filter(
                Signal.timeframe == timeframe, Signal.date == stamp
            ).delete(synchronize_session=False)

        for draft, option_rec, candle_date in pending:
            db.add(
                Signal(
                    ticker=draft.ticker,
                    name=draft.name,
                    date=candle_date,
                    type=draft.direction,
                    setup=draft.setup,
                    timeframe=timeframe,
                    entry=draft.entry,
                    target=draft.target,
                    stop=draft.stop,
                    confidence=draft.confidence,
                    price=draft.price,
                    sector=draft.sector,
                    confidence_components=draft.confidence_components,
                    triggered_rules=draft.triggered_rules,
                    event_flags=draft.event_flags,
                    option_recommendation=option_rec,
                )
            )
            tf_counts[draft.setup] = tf_counts.get(draft.setup, 0) + 1
            tf_counts[draft.direction] = tf_counts.get(draft.direction, 0) + 1
            tf_counts["total"] += 1

        by_timeframe[timeframe] = tf_counts
        for key, value in tf_counts.items():
            counts[key] = counts.get(key, 0) + value

    db.commit()
    counts["by_timeframe"] = by_timeframe
    return counts
