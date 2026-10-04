"""Signal generation orchestration.

Loads bars from the DB, builds the macro/event context, runs the signal engine
across the universe for each requested timeframe (daily, weekly, monthly),
replays recent candles so History has a record to score, and persists results.

Picks are read from **stock prices alone** — no options layer — and index futures
(MES) join the universe when their price history is available. Runs are
idempotent per (timeframe, candle date).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..core.constants import SETUPS, SIGNAL_SELL
from ..core.signal_engine import analyze_ticker
from ..core.timeframes import (
    DAILY,
    MONTHLY,
    TIMEFRAMES,
    WEEKLY,
    lookback_days,
    min_bars,
    normalise,
    resample,
)
from ..models import BacktestRun, Signal
from ..providers.base import MacroDataProvider, MarketDataProvider
from . import data_service
from .data_service import latest_trading_day, load_bars, resolve_universe
from .macro_service import build_and_store_snapshot, build_signal_context, days_to_earnings

#: How many earlier completed candles per timeframe are replayed so History has
#: a record to show and score. Repeat runs skip dates already stored.
BACKFILL_CANDLES: dict[str, int] = {DAILY: 15, WEEKLY: 12, MONTHLY: 6}


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


def _analyse(meta, bars, timeframe: str, ctx) -> list:
    """Run the engine over one series.

    Picks are derived from **stock prices alone** — the engine reads OHLCV bars
    and nothing else. There is no options layer: a bearish setup is reported as
    the underlying's own entry, target and stop.
    """
    return list(analyze_ticker(meta.ticker, meta.name, meta.sector, bars, ctx))


def _persist(db: Session, drafts, timeframe: str, candle_date: date) -> dict:
    """Store one candle's drafts, returning per-setup and per-direction counts."""
    counts = {s: 0 for s in SETUPS}
    counts.update({"BUY": 0, "SELL": 0, "total": 0})
    for draft in drafts:
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
            )
        )
        counts[draft.setup] = counts.get(draft.setup, 0) + 1
        counts[draft.direction] = counts.get(draft.direction, 0) + 1
        counts["total"] += 1
    return counts


def backfill_history(
    db: Session,
    ctx,
    universe,
    timeframes: tuple[str, ...] = TIMEFRAMES,
    steps: dict[str, int] | None = None,
    anchor: date | None = None,
) -> dict:
    """Replay recent completed candles so History has a real record to judge.

    A run only produces picks for the newest candle, so a fresh install has no
    history — and therefore nothing to score. This walks back over the last few
    completed candles of each timeframe, analysing the series **as it stood at
    that candle**, and stores whatever fires. Dates already stored are skipped,
    so repeat runs are cheap.

    Results are evaluated separately by ``outcome_service``.
    """
    steps = steps or BACKFILL_CANDLES
    anchor = anchor or latest_trading_day(db) or date.today()
    written: dict[str, int] = {}

    for timeframe in timeframes:
        timeframe = normalise(timeframe)
        ctx.timeframe = timeframe
        minimum = min_bars(timeframe)
        start = anchor - timedelta(days=lookback_days(timeframe))
        wanted = steps.get(timeframe, 0)
        if wanted <= 0:
            written[timeframe] = 0
            continue

        # The completed candle dates come from a reference ticker, since every
        # ticker shares the same trading calendar.
        reference = None
        for meta in universe:
            bars = load_bars(db, meta.ticker, start, anchor)
            if len(resample(bars, timeframe)) >= minimum:
                reference = resample(bars, timeframe)
                break
        if reference is None:
            written[timeframe] = 0
            continue

        # Oldest first, and never the newest candle (that is the live list).
        candle_dates = [bar.date for bar in reference][-wanted - 1 : -1]

        # Skip per instrument, not per date: a symbol added later (an index
        # future, or a new name in the universe) still fills in on dates that
        # other tickers already cover.
        already: set[tuple[str, date]] = {
            (row[0], row[1])
            for row in db.query(Signal.ticker, Signal.date)
            .filter(Signal.timeframe == timeframe, Signal.date.in_(candle_dates))
            .all()
        }
        total = 0
        for candle_date in candle_dates:
            pending: list = []
            for meta in universe:
                if (meta.ticker, candle_date) in already:
                    continue
                daily_bars = [b for b in load_bars(db, meta.ticker, start, anchor) if b.date <= candle_date]
                series = resample(daily_bars, timeframe)
                if len(series) < minimum:
                    continue
                pending.extend(_analyse(meta, series, timeframe, ctx))
            if not pending:
                continue
            counts = _persist(db, pending, timeframe, candle_date)
            total += counts["total"]
        written[timeframe] = total

    db.commit()
    return written


def generate_signals(
    db: Session,
    market_provider: MarketDataProvider,
    macro_provider: MacroDataProvider,
    signal_date: date | None = None,
    allow_earnings_plays: bool = False,
    min_price: float = 5.0,
    min_volume: float = 500_000.0,
    timeframes: tuple[str, ...] = TIMEFRAMES,
    backfill: bool = True,
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

    universe = list(resolve_universe(market_provider, min_price=min_price, min_volume=min_volume))
    # Index futures (MES) join only when their price history is present. The
    # MOCK provider already lists them, so de-duplicate by ticker — a repeated
    # ticker would collide with the (ticker, date, setup, timeframe) constraint.
    known = {meta.ticker for meta in universe}
    universe += [meta for meta in data_service.futures_universe(db) if meta.ticker not in known]

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
        pending: list = []
        stamp: date | None = None
        for meta in universe:
            daily_bars = load_bars(db, meta.ticker, start, anchor)
            bars = resample(daily_bars, timeframe)
            if len(bars) < minimum:
                continue
            candle_date = bars[-1].date
            stamp = stamp or candle_date
            ctx.earnings_in_days = days_to_earnings(db, meta.ticker, candle_date)
            pending.extend(_analyse(meta, bars, timeframe, ctx))

        if stamp is not None:
            db.query(Signal).filter(
                Signal.timeframe == timeframe, Signal.date == stamp
            ).delete(synchronize_session=False)

        tf_counts = _persist(db, pending, timeframe, stamp) if stamp else tf_counts
        by_timeframe[timeframe] = tf_counts
        for key, value in tf_counts.items():
            counts[key] = counts.get(key, 0) + value

    db.commit()

    # A run only covers the newest candle, so replay recent ones too — otherwise
    # History has nothing to show and nothing to score.
    if backfill:
        counts["backfilled"] = backfill_history(db, ctx, universe, requested, anchor=anchor)

    counts["by_timeframe"] = by_timeframe
    return counts
