"""SMC analysis service: scan the universe, and drill into one symbol.

The app's whole job now: read the daily chart for structure, break of structure and
the fair value gap behind it, then refine the entry on the 4-hour chart. The
result is the plain-text block from ``SmcAnalysis.render`` â€” that text is the
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
    """The 4-hour candles behind the refinement step."""
    start = datetime.combine(anchor - timedelta(days=INTRADAY_WINDOW_DAYS), dtime.min)
    end = datetime.combine(anchor, dtime.max)
    return data_service.load_refinement_bars(db, ticker, start, end)


def _settings() -> tuple[float, int]:
    settings = get_settings()
    return settings.smc_min_risk_reward, settings.smc_max_results


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


def clear_cache() -> None:
    with _lock:
        _cache.clear()
