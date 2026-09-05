"""Demo seeding: bootstrap the database with MOCK data so the app works with
zero configuration. Skips automatically when signals already exist."""
from __future__ import annotations

from datetime import date, timedelta

from .database import SessionLocal
from .models import Signal
from .providers.registry import resolve_macro_provider, resolve_market_provider
from .services import credentials as creds_svc
from .services import data_service, signal_service

BAR_HISTORY_DAYS = 540
CALENDAR_DAYS = 90


def seed_demo(signal_date: date | None = None) -> dict:
    signal_date = signal_date or date.today()
    db = SessionLocal()
    try:
        creds = creds_svc.resolve_credentials(db, None)  # env fallback only
        market = resolve_market_provider(creds)
        macro = resolve_macro_provider(creds)

        universe = data_service.resolve_universe(market)
        tickers = [m.ticker for m in universe]

        bar_start = signal_date - timedelta(days=BAR_HISTORY_DAYS)
        data_service.ingest_bars(db, market, tickers, bar_start, signal_date)

        cal_start = signal_date - timedelta(days=15)
        cal_end = signal_date + timedelta(days=CALENDAR_DAYS)
        data_service.ingest_macro_events(db, macro, cal_start, cal_end)
        data_service.ingest_earnings(db, macro, tickers, cal_start, cal_end)

        counts = signal_service.generate_signals(db, market, macro, signal_date)
        return counts
    finally:
        db.close()


def seed_if_empty() -> bool:
    """Seed only when the database has no signals yet. Returns whether seeded."""
    db = SessionLocal()
    try:
        if db.query(Signal).count() > 0:
            return False
    finally:
        db.close()
    seed_demo()
    return True
