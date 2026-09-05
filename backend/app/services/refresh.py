"""On-demand data refresh (runs in a background thread).

Backs the "Refresh data" button: re-pulls bars / macro / earnings with the
current provider (Alpaca when keys are configured, MOCK otherwise) and
regenerates signals for the most recent completed trading day.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

from ..models import EarningsEvent, MacroEvent, Signal
from ..providers.registry import resolve_macro_provider, resolve_market_provider
from . import credentials as creds_svc
from . import data_service, signal_service

BAR_HISTORY_DAYS = 730  # ~2 years of daily bars
CALENDAR_DAYS = 90

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def start_refresh(session_factory, user_id: int) -> bool:
    """Start a background refresh if one isn't already running.

    Returns True if a refresh was started, False if one is already in flight.
    """
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
        _state["started_at"] = datetime.utcnow()
        _state["finished_at"] = None
        _state["result"] = None
        _state["error"] = None

    def worker() -> None:
        try:
            db = session_factory()
            try:
                result = _do_refresh(db, user_id)
            finally:
                db.close()
            with _lock:
                _state["result"] = result
        except Exception as exc:  # pragma: no cover - defensive
            with _lock:
                _state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.utcnow()

    threading.Thread(target=worker, daemon=True).start()
    return True


def _do_refresh(db, user_id: int) -> dict:
    creds = creds_svc.resolve_credentials(db, user_id)
    market = resolve_market_provider(creds)
    macro = resolve_macro_provider(creds)

    universe = data_service.resolve_universe(market)
    tickers = [m.ticker for m in universe]
    today = date.today()
    start = today - timedelta(days=BAR_HISTORY_DAYS)

    # Clear stale signals/macro/earnings (e.g. a prior MOCK seed) so the switch
    # to real data doesn't leave synthetic rows behind. Bars are replaced
    # wholesale per-ticker by ingest_bars below.
    db.query(Signal).delete(synchronize_session=False)
    db.query(MacroEvent).delete(synchronize_session=False)
    db.query(EarningsEvent).delete(synchronize_session=False)
    db.commit()

    n_bars = data_service.ingest_bars(db, market, tickers, start, today)
    data_service.ingest_macro_events(
        db, macro, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    data_service.ingest_earnings(
        db, macro, tickers, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    counts = signal_service.generate_signals(db, market, macro)

    return {
        "provider": market.name,
        "tickers": len(tickers),
        "bars": n_bars,
        "signal_date": str(data_service.latest_trading_day(db) or today),
        "signals": counts,
    }
