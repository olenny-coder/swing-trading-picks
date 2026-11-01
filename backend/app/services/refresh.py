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
    #: Human-readable stage, so a five-minute pull is not a black box.
    "progress": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def _set_progress(step: str) -> None:
    """Record what the refresh is doing right now."""
    with _lock:
        _state["progress"] = step


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
        _state["progress"] = "starting"

    def worker() -> None:
        try:
            db = session_factory()
            try:
                result = _do_refresh(db, user_id)
            finally:
                db.close()
            with _lock:
                _state["result"] = result
                _state["progress"] = "finished"
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("refresh failed: %s", exc, exc_info=True)
            with _lock:
                _state["error"] = f"{type(exc).__name__}: {exc}"
                _state["progress"] = "failed"
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.utcnow()

    threading.Thread(target=worker, daemon=True).start()
    return True


def _price_source(db, market):
    """The configured market provider.

    Alpaca only: it serves daily and 4-hour candles natively, so there is no
    second source to fall back to. Keeping one source also means a failure is
    reported as a failure instead of being masked by a substitute.
    """
    return [(market, market.name)]


def _ingest_with_fallback(db, sources, ingest, *args) -> tuple[int, str, dict[str, str]]:
    """Run an ingestion over the sources in order, using the first that works.

    Returns the row count, the source that served it, and **why each source that
    failed did so**. Swallowing those reasons is what makes a refresh report
    "success" with no data, which is impossible to act on.
    """
    errors: dict[str, str] = {}
    for provider, name in sources:
        # Start every attempt from a clean transaction. A source that failed mid-way
        # leaves the session unusable, and the next step would then report a
        # PendingRollbackError that belongs to the step before it.
        try:
            db.rollback()
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            count = ingest(db, provider, *args)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"[:300]
            try:
                db.rollback()
            except Exception:  # pragma: no cover - defensive
                pass
            logger.warning("ingestion via %s failed: %s", name, exc)
            continue
        if count:
            return count, name, errors
        errors[name] = "returned no candles"
    return 0, sources[0][1], errors


def probe_sources(session_factory, user_id: int, ticker: str = "AAPL") -> dict:
    """Call every price source for one symbol and report exactly what happened.

    This exists because a hosted deployment swallows provider errors into logs the
    operator cannot see. Here each source is tried for daily and 4-hour candles and
    reports its status, row count, latency and the precise error.
    """
    import time as _time

    db = session_factory()
    try:
        creds = creds_svc.resolve_credentials(db, user_id)
        try:
            market = resolve_market_provider(creds)
        except Exception as exc:
            return {
                "ticker": ticker.upper(),
                "market_provider": None,
                "results": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        sources = _price_source(db, market)
    finally:
        db.close()

    today = date.today()
    daily_start = today - timedelta(days=30)
    intraday_start = datetime.combine(today - timedelta(days=10), dtime.min)
    intraday_end = datetime.combine(today, dtime.max)

    checks = [
        ("daily", "1Day", lambda p: p.get_daily_bars(ticker, daily_start, today)),
        (
            "4Hour",
            "4Hour",
            lambda p: p.get_intraday_bars(
                ticker, intraday_start, intraday_end, interval="4Hour"
            ),
        ),
        (
            "1Hour",
            "1Hour",
            lambda p: p.get_intraday_bars(
                ticker, intraday_start, intraday_end, interval="1Hour"
            ),
        ),
    ]

    results: list[dict] = []
    for provider, name in sources:
        for label, interval, call in checks:
            started = _time.time()
            try:
                bars = call(provider)
                results.append(
                    {
                        "source": name,
                        "interval": label,
                        "requested": interval,
                        "ok": bool(bars),
                        "bars": len(bars),
                        "ms": int((_time.time() - started) * 1000),
                        "error": None if bars else "returned no candles",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "source": name,
                        "interval": label,
                        "requested": interval,
                        "ok": False,
                        "bars": 0,
                        "ms": int((_time.time() - started) * 1000),
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
                )

    refine_ok = any(r["ok"] for r in results if r["interval"] in ("4Hour", "1Hour"))
    daily_ok = any(r["ok"] for r in results if r["interval"] == "daily")
    if daily_ok and refine_ok:
        verdict = "Both daily and 4-hour data are available from at least one source."
    elif daily_ok:
        verdict = (
            "Daily data works but no source returns intraday candles, so the refinement "
            "falls back to the daily chart. Check the market-data plan or key."
        )
    else:
        verdict = "No source returned any candles — the market-data key needs fixing."

    return {
        "ticker": ticker.upper(),
        "market_provider": sources[0][1] if sources else None,
        "results": results,
        "verdict": verdict,
    }


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
    _set_progress("clearing previous signals")
    db.query(Signal).delete(synchronize_session=False)
    db.query(MacroEvent).delete(synchronize_session=False)
    db.query(EarningsEvent).delete(synchronize_session=False)
    db.commit()

    _set_progress(f"downloading daily bars for {len(tickers)} symbols")
    n_bars, bars_source, bars_errors = _ingest_with_fallback(
        db, sources, data_service.ingest_bars, tickers, start, today
    )
    # Index futures (MES) come from a separate source and are best-effort.
    _set_progress("downloading index futures")
    futures_info = data_service.ingest_index_futures(db, start, today)

    # 4-hour candles behind the refinement chart — Alpaca serves that interval
    # natively. Without them the strategy still runs, but it has to fall back to
    # refining on the daily chart, which is coarser.
    intraday_start = datetime.combine(today - timedelta(days=INTRADAY_DAYS), dtime.min)
    intraday_end = datetime.combine(today, dtime.max)
    _set_progress(f"downloading 4-hour candles for {len(tickers)} symbols")
    n_intraday, intraday_source, intraday_errors = _ingest_with_fallback(
        db, sources, data_service.ingest_refinement_bars, tickers, intraday_start, intraday_end
    )

    warnings: list[str] = []
    if n_intraday == 0:
        detail = "; ".join(f"{name}: {err}" for name, err in intraday_errors.items())
        warnings.append(
            "No 4-hour candles were loaded, so every setup will be reported as No Trade — "
            "the entry, stop and target cannot be placed accurately without the 4-hour "
            f"refinement. {detail}".strip()
        )
    if n_bars == 0:
        detail = "; ".join(f"{name}: {err}" for name, err in bars_errors.items())
        warnings.append(
            f"No daily bars could be loaded from any source — nothing to analyse. {detail}".strip()
        )

    _set_progress("downloading the economic calendar")
    data_service.ingest_macro_events(
        db, macro, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    data_service.ingest_earnings(
        db, macro, tickers, today - timedelta(days=15), today + timedelta(days=CALENDAR_DAYS)
    )
    _set_progress("generating signals")
    counts = signal_service.generate_signals(db, market, macro)
    # Replay older picks so History can show whether they worked out.
    _set_progress("scoring past picks")
    outcomes = outcome_service.update_outcomes(db)

    # New data must not be masked by the scan cache, or the user refreshes and still
    # sees the payload built from the previous bars.
    try:
        from . import smc_service

        smc_service.clear_cache()
    except Exception:  # pragma: no cover - cache clearing is best-effort
        logger.warning("could not clear the analysis cache", exc_info=True)

    return {
        "provider": bars_source,
        "refinement_source": intraday_source,
        "source_errors": {"daily": bars_errors, "refinement": intraday_errors},
        "tickers": len(tickers),
        "bars": n_bars,
        "intraday_bars": n_intraday,
        "warnings": warnings,
        "futures": futures_info,
        "signal_date": str(data_service.latest_trading_day(db) or today),
        "signals": counts,
        "outcomes": outcomes,
    }
