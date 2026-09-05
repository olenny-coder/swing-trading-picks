"""Data ingestion: pull bars / macro / earnings from providers into the DB.

Ingestion is idempotent: bars for a (ticker, window) are replaced wholesale on
re-run, and macro/earnings rows are upserted by natural key.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import DailyBar, EarningsEvent, MacroEvent
from ..providers.base import Bar, MacroDataProvider, MarketDataProvider, UniverseMeta


def ingest_bars(
    db: Session,
    provider: MarketDataProvider,
    tickers: list[str],
    start: date,
    end: date,
) -> int:
    """Fetch and store daily bars. Returns the number of rows inserted."""
    total = 0
    for ticker in tickers:
        bars = provider.get_daily_bars(ticker, start, end)
        if not bars:
            continue
        db.query(DailyBar).filter(
            DailyBar.ticker == ticker, DailyBar.date >= start, DailyBar.date <= end
        ).delete(synchronize_session=False)
        db.add_all(
            [
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
        )
        total += len(bars)
        if total % 10000 < len(bars):
            db.flush()
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


def resolve_universe(provider: MarketDataProvider, min_price: float = 5.0, min_volume: float = 500_000.0) -> list[UniverseMeta]:
    return provider.get_universe(min_price=min_price, min_volume=min_volume)


def latest_trading_day(db: Session) -> date | None:
    """Most recent bar date in the database (handles weekends/holidays)."""
    return db.query(func.max(DailyBar.date)).scalar()
