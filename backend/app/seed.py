"""Demo seeding: bootstrap the database with MOCK data so the app works with
zero configuration. Skips automatically when signals already exist, and never
runs against a database configured for real market data."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from .database import SessionLocal
from .models import Signal
from .providers.registry import resolve_macro_provider, resolve_market_provider
from .services import credentials as creds_svc
from .services import data_service, signal_service

logger = logging.getLogger("app.seed")

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
    """Seed the synthetic dataset, but only when it is safe to do so.

    Guarded twice, because this runs unattended at startup:

    - **Only on the MOCK provider.** A deployment configured with real
      credentials must never have synthetic bars written into its database. If
      ``DATA_PROVIDER`` names a real provider that is not configured yet,
      resolving it raises — which previously took the whole service down at boot.
    - **Only when there are no signals yet**, so it is a one-time bootstrap.

    Returns whether it seeded.
    """
    from .config import get_settings

    if get_settings().data_provider not in ("auto", "mock"):
        logger.info(
            "not seeding demo data: DATA_PROVIDER=%s", get_settings().data_provider
        )
        return False

    db = SessionLocal()
    try:
        if db.query(Signal).count() > 0:
            return False
        creds = creds_svc.resolve_credentials(db, None)
    finally:
        db.close()

    try:
        market = resolve_market_provider(creds)
    except Exception as exc:
        # e.g. DATA_PROVIDER=alpaca with no keys on this host. Not fatal: the
        # operator signs in and enters keys, which is a normal first-run state.
        logger.warning("skipping demo seed, no usable market provider: %s", exc)
        return False
    if market.name != "mock":
        logger.info("not seeding demo data: resolved provider is %s", market.name)
        return False

    seed_demo()
    return True
