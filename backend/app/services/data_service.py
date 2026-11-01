"""Data ingestion: pull bars / macro / earnings from providers into the DB.

Ingestion is idempotent: bars for a (ticker, window) are replaced wholesale on
re-run, and macro/earnings rows are upserted by natural key.
"""
from __future__ import annotations

import logging

from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import DailyBar, EarningsEvent, MacroEvent
from ..providers.base import (
    Bar,
    IntradayBar,
    MacroDataProvider,
    MarketDataProvider,
    UniverseMeta,
)


#: Symbols per batched Alpaca request. ``StockBarsRequest`` takes a symbol list, so
#: one call can serve many names; this keeps the URL comfortably short.
log = logging.getLogger("app.data")

BATCH_SIZE = 50


def _dedupe(rows: list, key) -> list:
    """Drop duplicate rows before they reach a unique constraint.

    A batched multi-symbol response can repeat a candle (paginated pages may
    overlap), and one duplicate poisons the whole transaction: Postgres raises
    UniqueViolation, the session goes into a failed state, and every later symbol
    then fails with PendingRollbackError — which hides the real cause.
    """
    seen: dict = {}
    for row in rows:
        seen[key(row)] = row
    return list(seen.values())


def _replace(db: Session, model, filters: list, build_rows) -> int:
    """Replace one symbol's rows inside a savepoint.

    The savepoint matters: if a single symbol still violates a constraint, only
    that symbol is rolled back and the rest of the batch survives. Without it, one
    bad row aborts the entire refresh *and* leaves the session unusable, which is
    what produced a PendingRollbackError reported against the wrong step.
    """
    rows = build_rows()
    with db.begin_nested():
        db.query(model).filter(*filters).delete(synchronize_session=False)
        db.add_all(rows)
    return len(rows)


def _chunks(items: list, size: int = BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _daily_rows(ticker: str, bars: list) -> list:
    return [
        DailyBar(
            ticker=ticker,
            date=b.date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ]


def ingest_bars(
    db: Session,
    provider: MarketDataProvider,
    tickers: list[str],
    start: date,
    end: date,
) -> int:
    """Fetch and store daily bars. Returns the number of rows inserted.

    Uses the provider's batched endpoint when it has one, so a 114-name universe
    costs a handful of requests instead of 114. Duplicate dates are dropped and each
    symbol is written inside a savepoint, so one bad row cannot abort the refresh.
    """
    total = 0
    multi = getattr(provider, "get_daily_bars_multi", None)

    for chunk in _chunks(list(tickers)):
        if callable(multi):
            try:
                payload = multi(chunk, start, end)
            except Exception as exc:
                log.warning("batched daily fetch failed (%s); trying per-symbol", exc)
                payload = {}
        else:
            payload = {}

        for ticker in chunk:
            bars = payload.get(ticker) or []
            if not bars and not callable(multi):
                try:
                    bars = provider.get_daily_bars(ticker, start, end)
                except Exception as exc:
                    log.warning("daily fetch failed for %s: %s", ticker, exc)
                    continue
            if not bars:
                continue

            bars = _dedupe(bars, key=lambda b: b.date)
            try:
                total += _replace(
                    db,
                    DailyBar,
                    [
                        DailyBar.ticker == ticker,
                        DailyBar.date >= start,
                        DailyBar.date <= end,
                    ],
                    lambda t=ticker, r=bars: _daily_rows(t, r),
                )
            except Exception as exc:
                log.warning("could not store daily bars for %s: %s", ticker, exc)
                continue

    db.commit()
    return total


def load_bars(db: Session, ticker: str, start: date, end: date) -> list[Bar]:
    rows = (
        db.query(DailyBar)
        .filter(DailyBar.ticker == ticker, DailyBar.date >= start, DailyBar.date <= end)
        .order_by(DailyBar.date.asc())
        .all()
    )
    return [
        Bar(date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]


def load_intraday_bars(
    db: Session, ticker: str, start: datetime, end: datetime, interval: str = "1Hour"
) -> list[IntradayBar]:
    from ..models import IntradayBar as IntradayBarRow

    rows = (
        db.query(IntradayBarRow)
        .filter(
            IntradayBarRow.ticker == ticker,
            IntradayBarRow.interval == interval,
            IntradayBarRow.ts >= start,
            IntradayBarRow.ts <= end,
        )
        .order_by(IntradayBarRow.ts.asc())
        .all()
    )
    return [
        IntradayBar(
            ts=r.ts.replace(tzinfo=None) if r.ts.tzinfo else r.ts,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in rows
    ]


def ingest_macro_events(db: Session, provider: MacroDataProvider, start: date, end: date) -> int:
    events = provider.get_economic_calendar(start, end)
    # Idempotent: replace events within the window (no duplicate accumulation).
    db.query(MacroEvent).filter(
        MacroEvent.datetime >= datetime.combine(start, time.min),
        MacroEvent.datetime < datetime.combine(end, time.min) + timedelta(days=1),
    ).delete(synchronize_session=False)
    count = 0
    for e in events:
        db.add(
            MacroEvent(
                title=e.title,
                datetime=e.datetime,
                importance=e.importance,
                sentiment=e.sentiment,
                category=e.category,
                country=e.country,
                forecast=e.forecast,
                previous=e.previous,
                actual=e.actual,
                source=e.source,
            )
        )
        count += 1
    db.commit()
    return count


def ingest_earnings(
    db: Session, provider: MacroDataProvider, tickers: list[str], start: date, end: date
) -> int:
    events = provider.get_earnings_calendar(tickers, start, end)
    count = 0
    for e in events:
        row = (
            db.query(EarningsEvent)
            .filter(EarningsEvent.ticker == e.ticker, EarningsEvent.report_date == e.report_date)
            .first()
        )
        if row is None:
            row = EarningsEvent(ticker=e.ticker, report_date=e.report_date)
            db.add(row)
        row.fiscal_quarter = e.fiscal_quarter
        row.eps_estimate = e.eps_estimate
        row.eps_actual = e.eps_actual
        row.revenue_estimate = e.revenue_estimate
        row.source = e.source
        count += 1
    db.commit()
    return count


def _refinement_rows(ticker: str, bars: list, interval: str) -> list:
    from ..models import IntradayBar as IntradayBarRow

    return [
        IntradayBarRow(
            ticker=ticker,
            interval=interval,
            ts=b.ts.replace(tzinfo=None) if b.ts.tzinfo else b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ]


def ingest_refinement_bars(
    db: Session, provider: MarketDataProvider, tickers: list[str], start: datetime, end: datetime
) -> int:
    """Fetch and store the 4-hour refinement candles.

    The provider contract is that ``interval="4Hour"`` returns 4-hour candles —
    native where the feed supports it, aggregated from hourly where it does not.

    Two failure modes are handled explicitly, both of which previously surfaced as a
    PendingRollbackError blamed on the wrong step:

    - **Duplicate candles** in a batched payload would violate the
      ``(ticker, interval, timestamp)`` unique constraint. They are deduplicated
      first.
    - **One bad symbol** would abort the whole transaction and leave the session
      unusable. Each symbol is written inside a savepoint, so it is isolated.

    If nothing at all was stored, the first error is raised so the refresh reports
    why instead of quietly claiming success with no data.
    """
    from ..core.intraday import REFINEMENT_INTERVAL
    from ..models import IntradayBar as IntradayBarRow
    from ..providers.base import ProviderError

    total = 0
    errors: list[str] = []
    multi = getattr(provider, "get_intraday_bars_multi", None)

    for chunk in _chunks(list(tickers)):
        if callable(multi):
            try:
                payload = multi(chunk, start, end, interval=REFINEMENT_INTERVAL)
            except Exception as exc:
                log.warning("batched %s fetch failed (%s); trying per-symbol", REFINEMENT_INTERVAL, exc)
                payload = {}
        else:
            payload = {}

        for ticker in chunk:
            bars = payload.get(ticker) or []
            if not bars and not callable(multi):
                try:
                    bars = provider.get_intraday_bars(
                        ticker, start, end, interval=REFINEMENT_INTERVAL
                    )
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}"[:200])
                    continue
            if not bars:
                errors.append("provider returned no candles")
                continue

            bars = _dedupe(
                bars, key=lambda b: b.ts.replace(tzinfo=None) if b.ts.tzinfo else b.ts
            )
            try:
                total += _replace(
                    db,
                    IntradayBarRow,
                    [
                        IntradayBarRow.ticker == ticker,
                        IntradayBarRow.interval == REFINEMENT_INTERVAL,
                        IntradayBarRow.ts >= start,
                        IntradayBarRow.ts <= end,
                    ],
                    lambda t=ticker, r=bars: _refinement_rows(t, r, REFINEMENT_INTERVAL),
                )
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:200])
                continue

    db.commit()

    if total == 0 and errors:
        raise ProviderError(f"no 4-hour candles returned — {errors[0]}")
    return total


def load_refinement_bars(
    db: Session, ticker: str, start: datetime, end: datetime
) -> list[IntradayBar]:
    """The 4-hour series for one symbol."""
    from ..core.intraday import REFINEMENT_INTERVAL

    return load_intraday_bars(db, ticker, start, end, REFINEMENT_INTERVAL)


def resolve_universe(provider: MarketDataProvider, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
    return provider.get_universe(min_price=min_price, min_volume=min_volume)


def ingest_index_futures(db: Session, start: date, end: date) -> dict:
    """Best-effort ingestion of the index futures in ``core.universe.FUTURES``.

    Index futures are not carried by the equity providers, so they come from a
    separate key-free source. Any failure is reported rather than raised: a
    futures outage must never fail an equity refresh.
    """
    from ..core.universe import FUTURES_TICKERS
    from ..providers.registry import resolve_futures_provider

    try:
        provider = resolve_futures_provider()
    except Exception as exc:  # pragma: no cover - defensive
        return {"provider": None, "bars": 0, "error": f"{type(exc).__name__}: {exc}"}
    if provider is None:
        return {"provider": None, "bars": 0, "error": "index futures are disabled"}
    try:
        return {
            "provider": provider.name,
            "bars": ingest_bars(db, provider, FUTURES_TICKERS, start, end),
        }
    except Exception as exc:
        return {"provider": provider.name, "bars": 0, "error": f"{type(exc).__name__}: {exc}"}


def futures_universe(db: Session) -> list[UniverseMeta]:
    """Futures instruments that actually have stored bars, so they join the
    universe only when their data is available."""
    from ..core.universe import FUTURES

    out: list[UniverseMeta] = []
    for ticker, name, sector in FUTURES:
        exists = db.query(DailyBar.id).filter(DailyBar.ticker == ticker).first()
        if exists is not None:
            out.append(UniverseMeta(ticker=ticker, name=name, sector=sector))
    return out


def full_universe(
    db: Session, provider: MarketDataProvider, min_price: float = 5.0, min_volume: float = 500_000.0
) -> list[UniverseMeta]:
    """The equity universe plus any index futures that have stored bars.

    De-duplicated by ticker: the MOCK provider already lists the futures, and a
    ticker appearing twice would collide with the signal uniqueness constraint.
    """
    universe = list(resolve_universe(provider, min_price=min_price, min_volume=min_volume))
    known = {meta.ticker for meta in universe}
    universe += [meta for meta in futures_universe(db) if meta.ticker not in known]
    return universe


def latest_trading_day(db: Session) -> date | None:
    """Most recent bar date in the database (handles weekends/holidays)."""
    return db.query(func.max(DailyBar.date)).scalar()
