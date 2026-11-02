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
#: How far ahead the macro flags look for things that could invalidate a pick.
MACRO_LOOKAHEAD_DAYS = 7
#: Cap on how many macro items are attached to one pick.
MAX_MACRO_FLAGS = 4
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

    # What could invalidate each pick in the next few sessions.
    flags_by_symbol = macro_flags_for(db, selected, anchor)

    rows = []
    for result in selected:
        row = result.as_dict()
        row["macro_flags"] = flags_by_symbol.get(result.symbol, [])
        rows.append(row)

    # History is these picks, so they have to be stored, not just displayed.
    try:
        persist_picks(db, selected, anchor, flags_by_symbol)
    except Exception:  # pragma: no cover - never fail the screen on a write
        logger.warning("could not store the screen's picks", exc_info=True)

    payload = {
        "generated_at": anchor.isoformat(),
        "scanned": len(universe),
        "analysed": len(results),
        "tradeable": sum(1 for r in results if r.tradeable),
        "min_risk_reward": min_rr,
        "refinement_interval": "4H",
        "intraday_available": any(r.four_hour_available for r in results),
        "results": rows,
        "data_status": data_status(db),
        "demo": False,
    }
    with _lock:
        _cache[cache_key] = (time.time(), payload)
    return payload


def macro_flags_for(db: Session, results: list, as_of: date) -> dict[str, list[dict]]:
    """What to look out for on each pick: macro events and the ticker's earnings.

    A fair value gap is invalidated by a surprise, not by time. These flags answer
    "what could change this view in the next few sessions" using the events already
    stored for the calendar and earnings tables.
    """
    from ..models import EarningsEvent, MacroEvent

    lookahead = as_of + timedelta(days=MACRO_LOOKAHEAD_DAYS)
    window_start = datetime.combine(as_of, dtime.min)
    window_end = datetime.combine(lookahead, dtime.max)

    events = (
        db.query(MacroEvent)
        .filter(MacroEvent.datetime >= window_start, MacroEvent.datetime <= window_end)
        .order_by(MacroEvent.datetime.asc())
        .all()
    ) if events_table_exists(db) else []

    flags: dict[str, list[dict]] = {}
    for result in results:
        symbol = result.symbol
        picked: list[dict] = []

        # High-importance data always matters; medium is included because a run of
        # medium prints still moves the tape. Low-importance events are noise.
        for event in events:
            importance = (event.importance or "").lower()
            if importance not in ("high", "medium"):
                continue
            if len(picked) >= MAX_MACRO_FLAGS:
                break
            picked.append(
                {
                    "kind": "macro",
                    "title": event.title,
                    "when": event.datetime.date().isoformat(),
                    "importance": importance,
                    "sentiment": event.sentiment,
                    "impact": (
                        "High-importance data can gap the open straight through the entry or "
                        "the stop."
                        if importance == "high"
                        else "A scheduled release — expect wider ranges around it."
                    ),
                }
            )

        earnings = (
            db.query(EarningsEvent)
            .filter(
                EarningsEvent.ticker == symbol,
                EarningsEvent.report_date >= as_of,
                EarningsEvent.report_date <= lookahead,
            )
            .order_by(EarningsEvent.report_date.asc())
            .first()
        )
        if earnings is not None:
            days = (earnings.report_date - as_of).days
            picked.append(
                {
                    "kind": "earnings",
                    "title": f"{symbol} reports earnings",
                    "when": earnings.report_date.isoformat(),
                    "importance": "high",
                    "sentiment": "neutral",
                    "impact": (
                        f"Reports in {days} day{'s' if days != 1 else ''} — the gap will not "
                        "survive a surprise, so size down or wait for the reaction."
                    ),
                }
            )

        # Nothing scheduled is not the same as nothing to watch: name the next risk.
        if not any(f["kind"] == "macro" for f in picked):
            upcoming = (
                db.query(MacroEvent)
                .filter(MacroEvent.datetime > window_end)
                .filter(MacroEvent.importance == "high")
                .order_by(MacroEvent.datetime.asc())
                .first()
            )
            if upcoming is not None:
                picked.append(
                    {
                        "kind": "macro_next",
                        "title": upcoming.title,
                        "when": upcoming.datetime.date().isoformat(),
                        "importance": "high",
                        "sentiment": upcoming.sentiment,
                        "impact": (
                            f"Nothing scheduled in the next {MACRO_LOOKAHEAD_DAYS} days. The next "
                            "high-importance release is this one — plan the hold around it."
                        ),
                    }
                )

        flags[symbol] = picked
    return flags


def events_table_exists(db: Session) -> bool:
    """The macro calendar table may not exist on a brand-new database."""
    try:
        from ..models import MacroEvent

        db.query(MacroEvent.id).limit(1).all()
        return True
    except Exception:
        db.rollback()
        return False


def persist_picks(
    db: Session, results: list, as_of: date, flags: dict[str, list[dict]] | None = None
) -> int:
    """Store the tradeable picks as signals, so History shows what the screen said.

    Idempotent per (ticker, date, setup): re-running the screen updates the row
    rather than duplicating it. Outcome scoring then runs over these like any other
    signal, which is what keeps History aligned with the screener.
    """
    from ..core.constants import SIGNAL_BUY, SIGNAL_SELL, SETUP_SMC
    from ..core.timeframes import DAILY
    from ..models import Signal

    flags = flags or {}
    written = 0
    for result in results:
        if not result.tradeable or result.confidence <= 0:
            continue
        if result.entry is None or result.stop is None or result.target is None:
            continue

        row = (
            db.query(Signal)
            .filter(
                Signal.ticker == result.symbol,
                Signal.date == as_of,
                Signal.setup == SETUP_SMC,
            )
            .one_or_none()
        )
        if row is None:
            row = Signal(ticker=result.symbol, date=as_of, setup=SETUP_SMC)
            db.add(row)

        row.type = SIGNAL_BUY if result.trend == "Bullish" else SIGNAL_SELL
        row.timeframe = DAILY
        row.entry = result.entry
        row.target = result.target
        row.stop = result.stop
        row.confidence = result.confidence
        row.price = result.price or result.entry
        # ``event_flags`` is a dict on the stored signal (the UI reads named keys),
        # so the rich list of scheduled risks rides under "items".
        todo = flags.get(result.symbol) or []
        earnings_flag = next((f for f in todo if f["kind"] == "earnings"), None)
        earnings_in_days = None
        if earnings_flag is not None:
            try:
                earnings_in_days = (
                    date.fromisoformat(earnings_flag["when"]) - as_of
                ).days
            except ValueError:
                earnings_in_days = None
        row.event_flags = {
            "items": todo,
            "earnings_in_days": earnings_in_days,
            "high_importance_count": sum(1 for f in todo if f["importance"] == "high"),
        }
        row.confidence_components = {
            "risk_reward": result.risk_reward,
            "bos_level": result.bos.level if result.bos else None,
            "gap": result.gap.as_dict() if result.gap else None,
            "refinement": result.refinement_timeframe,
        }
        row.annotation = {
            "trend": result.trend,
            "reasoning": result.reasoning,
            "text": result.render(),
        }
        written += 1

    db.commit()
    return written


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
            "macro_flags": macro_flags_for(db, [analysis], anchor).get(symbol, []),
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
