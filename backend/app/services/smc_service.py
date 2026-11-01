"""SMC analysis service: scan the universe, and drill into one symbol.

The app's whole job now: read the daily chart for structure, break of structure and
the fair value gap behind it, then refine the entry on the 4-hour chart. The
result is the plain-text block from ``SmcAnalysis.render`` — that text is the
product, and the structured fields beside it exist only so the UI can draw the
chart.

Results are cached briefly: the scan is pure CPU work over stored bars and every
visitor would otherwise repeat it.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.intraday import bars_to_chart
from ..core.smc import MIN_DAILY_BARS, SmcAnalysis, analyze
from ..core.fvg import closed_only
from ..core.timeframes import lookback_days
from ..providers.base import MarketDataProvider
from . import data_service

logger = logging.getLogger("app.smc")

#: How long a scan stays cached, in seconds.
CACHE_TTL = 300
#: Days of hourly bars loaded for the refinement chart.
INTRADAY_WINDOW_DAYS = 60
#: Daily candles kept for the structure chart in the drill-down.
CHART_DAILY_BARS = 180
#: 4-hour candles kept for the refinement chart.
CHART_REFINEMENT_BARS = 200

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


def _daily_bars(db: Session, ticker: str, anchor: date) -> list:
    start = anchor - timedelta(days=lookback_days("DAILY") * 2)
    return closed_only(data_service.load_bars(db, ticker, start, anchor))


def _refinement_bars(db: Session, ticker: str, anchor: date) -> list:
    """The 4-hour candles behind the refinement step.

    The window is anchored on the latest *daily* bar, which is normally right. If the
    stored 4-hour candles sit outside it — a stale daily table beside fresh intraday
    data — a second, today-anchored attempt finds them instead of silently reporting
    "no 4-hour data" while the rows are sitting right there.
    """
    start = datetime.combine(anchor - timedelta(days=INTRADAY_WINDOW_DAYS), dtime.min)
    end = datetime.combine(anchor, dtime.max)
    bars = data_service.load_refinement_bars(db, ticker, start, end)
    if bars:
        return bars

    today = date.today()
    if today == anchor:
        return []
    start = datetime.combine(today - timedelta(days=INTRADAY_WINDOW_DAYS), dtime.min)
    end = datetime.combine(today, dtime.max)
    return data_service.load_refinement_bars(db, ticker, start, end)


def _settings() -> tuple[float, int]:
    settings = get_settings()
    return settings.smc_min_risk_reward, settings.smc_max_results


def data_status(db: Session) -> dict:
    """What price data is actually stored, in plain language.

    An empty screen must be able to say *why* it is empty. The two things that
    silently produce "no trades" are a database with no daily candles and one with
    no 4-hour candles — the second is normal right after an upgrade, because the
    refinement table starts empty.
    """
    from sqlalchemy import func

    from ..core.intraday import REFINEMENT_INTERVAL
    from ..models import DailyBar, IntradayBar
    from . import refresh as refresh_service

    # Why the last refresh could not load something, straight from its own report —
    # this is the difference between a mystery and an instruction.
    last_refresh = refresh_service.get_state().get("result") or {}
    refresh_warnings = list(last_refresh.get("warnings") or [])
    refresh_errors = last_refresh.get("source_errors") or {}

    daily_count = db.query(func.count(DailyBar.id)).scalar() or 0
    daily_latest = db.query(func.max(DailyBar.date)).scalar()
    refinement_count = (
        db.query(func.count(IntradayBar.id))
        .filter(IntradayBar.interval == REFINEMENT_INTERVAL)
        .scalar()
        or 0
    )
    refinement_latest = (
        db.query(func.max(IntradayBar.ts))
        .filter(IntradayBar.interval == REFINEMENT_INTERVAL)
        .scalar()
    )

    if daily_count == 0:
        ready = False
        message = (
            "No price data is stored yet. Sign in as an administrator and press Refresh "
            "to load the market data."
        )
    elif refinement_count == 0:
        ready = False
        detail = "; ".join(
            f"{name}: {err}" for name, err in (refresh_errors.get("refinement") or {}).items()
        )
        message = (
            "No 4-hour candles are stored, so every setup is refused: without the 4-hour "
            "refinement the entry, stop and target cannot be placed accurately. Press "
            "Refresh to download them. Re-analyse only re-reads the bars already stored — "
            "it cannot fetch data."
        )
        if detail:
            message += f" Last refresh error — {detail}."
    else:
        ready = True
        message = (
            f"Data is loaded: {daily_count:,} daily bars through {daily_latest} and "
            f"{refinement_count:,} 4-hour candles through "
            f"{refinement_latest:%Y-%m-%d %H:%M} UTC."
        )

    return {
        "ready": ready,
        "daily_bars": daily_count,
        "daily_latest": daily_latest.isoformat() if daily_latest else None,
        "refinement_bars": refinement_count,
        "refinement_latest": refinement_latest.isoformat() if refinement_latest else None,
        "message": message,
        "last_refresh_warnings": refresh_warnings,
        "last_refresh_errors": refresh_errors,
        "market_day_note": (
            "Analysis always reads the most recent *closed* candle, so a weekend or a "
            "holiday shows the last completed session — it does not blank the screen."
        ),
    }


def scan(
    db: Session,
    market_provider: MarketDataProvider,
    limit: int | None = None,
    refresh: bool = False,
) -> dict:
    """Analyse the whole universe and return the ranked results."""
    min_rr, max_results = _settings()
    limit = limit or max_results
    cache_key = f"smc:{min_rr}:{limit}"
    if not refresh:
        with _lock:
            cached = _cache.get(cache_key)
            if cached and (time.time() - cached[0]) < CACHE_TTL:
                return cached[1]

    anchor = data_service.latest_trading_day(db) or date.today()
    universe = data_service.full_universe(db, market_provider)

    results: list[SmcAnalysis] = []
    for meta in universe:
        try:
            daily = _daily_bars(db, meta.ticker, anchor)
            if len(daily) < MIN_DAILY_BARS:
                continue
            hourly = _refinement_bars(db, meta.ticker, anchor)
            results.append(analyze(meta.ticker, daily, hourly, min_risk_reward=min_rr))
        except Exception:  # pragma: no cover - defensive per instrument
            logger.debug("smc analysis failed for %s", meta.ticker, exc_info=True)
            continue

    # Tradeable setups first, then by confidence.
    results.sort(key=lambda r: (r.tradeable, r.confidence), reverse=True)
    selected = results[:limit]

    payload = {
        "generated_at": anchor.isoformat(),
        "scanned": len(universe),
        "analysed": len(results),
        "tradeable": sum(1 for r in results if r.tradeable),
        "min_risk_reward": min_rr,
        "refinement_interval": "4H",
        "intraday_available": any(r.four_hour_available for r in results),
        "results": [r.as_dict() for r in selected],
        "data_status": data_status(db),
        "demo": False,
    }
    with _lock:
        _cache[cache_key] = (time.time(), payload)
    return payload


def drilldown(
    db: Session, market_provider: MarketDataProvider, symbol: str
) -> dict | None:
    """One symbol's plain-text verdict plus the candles to draw it."""
    symbol = symbol.upper().strip()
    anchor = data_service.latest_trading_day(db) or date.today()

    daily = _daily_bars(db, symbol, anchor)
    if len(daily) < 3:
        return None

    four_hour = _refinement_bars(db, symbol, anchor)
    min_rr, _ = _settings()
    analysis = analyze(symbol, daily, four_hour, min_risk_reward=min_rr)

    meta = next(
        (m for m in data_service.full_universe(db, market_provider) if m.ticker == symbol),
        None,
    )

    payload = analysis.as_dict()
    payload.update(
        {
            "name": meta.name if meta else None,
            "sector": meta.sector if meta else None,
            "timeframe": "1D structure / 4H refinement",
            "live": _live_context(market_provider, symbol, payload),
            "daily_bars": [
                {
                    "date": b.date.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in daily[-CHART_DAILY_BARS:]
            ],
            "refinement_bars": bars_to_chart(four_hour[-CHART_REFINEMENT_BARS:]),
            "demo": False,
        }
    )
    return payload


def _live_context(market_provider: MarketDataProvider, symbol: str, payload: dict) -> dict:
    """Where price is *now* relative to the entry, for display only.

    The trade levels come from closed candles and never move. The snapshot answers
    the user's next question — "is price near my entry yet?" — and says plainly when
    a resting entry has already been passed.
    """
    snapshot = None
    try:
        snapshot = market_provider.get_snapshot(symbol)
    except Exception:
        logger.debug("snapshot failed for %s", symbol, exc_info=True)

    entry = payload.get("entry")
    if not snapshot or not entry:
        return {"available": False}

    price = snapshot.get("price")
    distance_pct = None
    if price and entry:
        distance_pct = round((price - entry) / entry * 100, 2)

    zone_low = payload.get("fvg_low")
    zone_high = payload.get("fvg_high")
    in_zone = bool(
        price and zone_low is not None and zone_high is not None
        and min(zone_low, zone_high) <= price <= max(zone_low, zone_high)
    )

    if in_zone:
        status = "Price is inside the fair value gap — the entry zone is live."
    elif distance_pct is not None and distance_pct > 0:
        status = f"Price is {distance_pct:.2f}% above the entry, waiting for a pullback into the gap."
    elif distance_pct is not None and distance_pct < 0:
        status = (
            f"Price is {abs(distance_pct):.2f}% below the entry — the zone has already been "
            "traded through on the way here."
        )
    else:
        status = "Live price unavailable."

    return {
        "available": True,
        "price": price,
        "change_pct": snapshot.get("change_pct"),
        "prev_close": snapshot.get("prev_close"),
        "session_high": snapshot.get("session_high"),
        "session_low": snapshot.get("session_low"),
        "as_of": snapshot.get("as_of"),
        "feed": snapshot.get("feed"),
        "distance_pct": distance_pct,
        "in_zone": in_zone,
        "status": status,
    }


def clear_cache() -> None:
    with _lock:
        _cache.clear()
