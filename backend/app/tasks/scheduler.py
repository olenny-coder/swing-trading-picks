"""APScheduler background jobs: daily ingestion and signal generation.

Runs in-process (simple single-user deployment). For multi-instance production,
swap to Celery + Redis (documented in README) and trigger these same service
functions from workers.
"""
from __future__ import annotations

from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..database import SessionLocal
from ..models import User
from ..providers.registry import resolve_macro_provider, resolve_market_provider
from ..services import credentials as creds_svc
from ..services import data_service, signal_service

_scheduler: BackgroundScheduler | None = None

BAR_HISTORY_DAYS = 540
CALENDAR_DAYS = 90


def _primary_user_id(db) -> int | None:
    user = db.query(User).order_by(User.id.asc()).first()
    return user.id if user else None


def _providers(db):
    user_id = _primary_user_id(db)
    creds = creds_svc.resolve_credentials(db, user_id)
    return resolve_market_provider(creds), resolve_macro_provider(creds)


def ingest_daily_job() -> dict:
    db = SessionLocal()
    try:
        market, macro = _providers(db)
        universe = data_service.resolve_universe(market)
        tickers = [m.ticker for m in universe]
        today = date.today()
        n_bars = data_service.ingest_bars(db, market, tickers, today - timedelta(days=BAR_HISTORY_DAYS), today)
        data_service.ingest_macro_events(db, macro, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS))
        data_service.ingest_earnings(db, macro, tickers, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS))
        return {"bars": n_bars}
    finally:
        db.close()


def generate_signals_job() -> dict:
    db = SessionLocal()
    try:
        market, macro = _providers(db)
        # signal_date=None -> uses the latest bar in the DB (handles weekends).
        return signal_service.generate_signals(db, market, macro)
    finally:
        db.close()


def ingest_macro_job() -> None:
    db = SessionLocal()
    try:
        market, macro = _providers(db)
        data_service.ingest_macro_events(
            db, macro, date.today() - timedelta(days=15), date.today() + timedelta(days=CALENDAR_DAYS)
        )
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    s = get_settings()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(ingest_daily_job, CronTrigger.from_crontab(s.cron_ingest_daily), id="ingest_daily", replace_existing=True)
    _scheduler.add_job(generate_signals_job, CronTrigger.from_crontab(s.cron_generate_signals), id="generate_signals", replace_existing=True)
    _scheduler.add_job(ingest_macro_job, CronTrigger.from_crontab(s.cron_ingest_macro), id="ingest_macro", replace_existing=True)
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
