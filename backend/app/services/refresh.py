"""On-demand data refresh (runs in a background thread).

Backs the "Refresh data" button: re-pulls bars / macro / earnings with the
current provider (Alpaca when keys are configured, MOCK otherwise) and
regenerates signals for the most recent completed trading day.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time as dtime, timedelta

from ..config import get_settings
from ..models import EarningsEvent, MacroEvent, Signal
from ..providers.registry import resolve_macro_provider, resolve_market_provider
from . import credentials as creds_svc
from . import data_service, outcome_service, signal_service

# ~6 years of daily bars: a monthly analysis needs 55 completed monthly candles
# plus a 30-candle structure lookback, so two years is not enough.
BAR_HISTORY_DAYS = 2200
CALENDAR_DAYS = 90
#: Days of hourly bars pulled for the 4-hour refinement chart.
INTRADAY_DAYS = get_settings().intraday_days

logger = logging.getLogger("app.refresh")

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


def _price_source(db, market):
    """The configured market provider, plus a key-free Yahoo fallback.

    An expired or rotated key should degrade the app to real prices from a free
    source rather than to nothing at all.
    """
    from ..providers.yahoo_provider import YahooMarketProvider

    return [(market, market.name), (YahooMarketProvider(), "yahoo")]


def _ingest_with_fallback(db, sources, ingest, *args) -> tuple[int, str]:
    """Run an ingestion over the sources in order, using the first that works."""
    last_error: Exception | None = None
    for provider, name in sources:
        try:
            count = ingest(db, provider, *args)
        except Exception as exc:
            last_error = exc
            db.rollback()
            logger.warning("ingestion via %s failed: %s", name, exc)
            continue
        if count:
            return count, name
    if last_error is not None:
        logger.warning("all data sources failed for this step: %s", last_error)
    return 0, sources[0][1]


def _do_refresh(db, user_id: int) -> dict:
    creds = creds_svc.resolve_credentials(db, user_id)
    market = resolve_market_provider(creds)
    macro = resolve_macro_provider(creds)
    sources = _price_source(db, market)

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

    n_bars, bars_source = _ingest_with_fallback(
        db, sources, data_service.ingest_bars, tickers, start, today
    )
    # Index futures (MES) come from a separate source and are best-effort.
    futures_info = data_service.ingest_index_futures(db, start, today)

    # 4-hour candles behind the refinement chart — Alpaca serves that interval
    # natively. Without them the strategy still runs, but it has to fall back to
    # refining on the daily chart, which is coarser.
    intraday_start = datetime.combine(today - timedelta(days=INTRADAY_DAYS), dtime.min)
    intraday_end = datetime.combine(today, dtime.max)
    n_intraday, intraday_source = _ingest_with_fallback(
        db, sources, data_service.ingest_refinement_bars, tickers, intraday_start, intraday_end
    )

    warnings: list[str] = []
    if n_intraday == 0:
        warnings.append(
            "No 4-hour candles could be loaded from any source, so setups are being refined "
            "on the daily chart and confidence is capped. Check the market-data keys under "
            "Settings."
        )
    if n_bars == 0:
        warnings.append(
            "No daily bars could be loaded from any source — the scan has nothing to analyse."
        )

    data_service.ingest_macro_events(
        db, macro, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    data_service.ingest_earnings(
        db, macro, tickers, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    counts = signal_service.generate_signals(db, market, macro)
    # Replay older picks so History can show whether they worked out.
    outcomes = outcome_service.update_outcomes(db)

    return {
        "provider": bars_source,
        "refinement_source": intraday_source,
        "tickers": len(tickers),
        "bars": n_bars,
        "intraday_bars": n_intraday,
        "warnings": warnings,
        "futures": futures_info,
        "signal_date": str(data_service.latest_trading_day(db) or today),
        "signals": counts,
        "outcomes": outcomes,
    }
