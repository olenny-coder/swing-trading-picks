"""FVG screener service: the ranked shortlist and the per-ticker drill-down.

Two distinct jobs, deliberately kept apart:

- ``scan`` / ``build_shortlist`` screen instruments and return **only** a ranked
  shortlist. They never return chart annotations, because the drill-down must wait
  until the user picks a ticker.
- ``drilldown`` / ``build_drilldown`` are for one ticker and return the
  annotations, the signal card and the markup.

The two builders take plain ``(ticker, name, sector, bars)`` entries rather than a
database session, so the anonymous DEMO dataset and the live database run through
exactly the same analysis.

Everything reads **closed candles**: a daily bar dated today is treated as still
forming and is dropped, so a zone can never appear and then vanish. Results are
cached briefly, since the scan is pure CPU work over stored bars.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.fvg import detect_fair_value_gaps, open_gaps
from ..core.fvg_strategy import (
    STATUS_NO_TRADE,
    FvgCandidate,
    FvgSettings,
    analyze_fvg,
    annotations,
    chart_markup,
    closed_only,
    signal_card,
)
from ..core.indicators import atr as atr_series
from ..core.indicators import ema
from ..core.structure import detect_structures, swing_indices
from ..core.timeframes import TIMEFRAMES, lookback_days, normalise, resample
from ..providers.base import MarketDataProvider
from . import data_service
from .macro_service import days_to_earnings

logger = logging.getLogger("app.fvg")

#: How long a scan stays cached, in seconds.
CACHE_TTL = 300
#: The shortest history worth analysing.
MIN_BARS = 55
#: A setup that is waiting on a retrace outranks one that already failed a gate.
_STATUS_RANK = {"BUY": 3, "SELL": 3, "WAIT": 2, "NO_TRADE": 1}

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


@dataclass
class Instrument:
    """One instrument's bars, ready for analysis."""

    ticker: str
    name: str | None
    sector: str | None
    bars: list
    earnings_in_days: int | None = None
    market_cap: float | None = None


def settings_from_config() -> FvgSettings:
    settings = get_settings()
    return FvgSettings(
        min_rr=settings.fvg_min_rr,
        max_watchlist=settings.fvg_max_watchlist,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        earnings_buffer_days=settings.earnings_buffer_days,
        min_price=settings.min_price,
        min_volume=settings.min_volume,
        min_market_cap=settings.fvg_min_market_cap,
        allow_earnings_plays=settings.allow_earnings_plays,
    )


def configured_timeframes() -> tuple[str, ...]:
    """Intervals the screener reads, from ``FVG_TIMEFRAMES``."""
    raw = (get_settings().fvg_timeframes or "DAILY").split(",")
    wanted = {normalise(item) for item in raw if item.strip()}
    ordered = [tf for tf in TIMEFRAMES if tf in wanted]
    return tuple(ordered) or ("DAILY",)


def intraday_note() -> dict:
    """The brief asks for 4H/1H/15m entry timing. State plainly whether we have it."""
    return {
        "available": False,
        "intervals": ["4H", "1H", "15M"],
        "note": (
            "Intraday intervals need an intraday bar feed. This deployment ingests "
            "daily bars only, so structure and entry timing are read on closed daily, "
            "weekly and monthly candles."
        ),
    }


def _rank_key(candidate: FvgCandidate) -> tuple[int, float]:
    return (_STATUS_RANK.get(candidate.status, 0), candidate.confidence)


# ---------------------------------------------------------------------------
# Builders — shared by the live database and the DEMO dataset
# ---------------------------------------------------------------------------
def build_shortlist(
    entries: list[Instrument],
    timeframe: str,
    limit: int | None = None,
    generated_at: date | None = None,
    screened: int | None = None,
    settings: FvgSettings | None = None,
    demo: bool = False,
    market_caps: dict[str, float] | None = None,
    market_cap_note: str | None = None,
) -> dict:
    """Rank instruments and return the shortlist. No chart annotations."""
    settings = settings or settings_from_config()
    limit = limit or settings.max_watchlist

    candidates: list[FvgCandidate] = []
    for entry in entries:
        try:
            candidate = analyze_fvg(
                entry.ticker,
                entry.name,
                entry.sector,
                entry.bars,
                timeframe,
                settings,
                earnings_in_days=entry.earnings_in_days,
                market_cap=entry.market_cap,
            )
        except Exception:  # pragma: no cover - defensive per instrument
            logger.debug("fvg screen failed for %s", entry.ticker, exc_info=True)
            continue
        if candidate is not None:
            candidates.append(candidate)

    # Only instruments with a real breakout structure *and* a matching gap are
    # shortlisted. A screener that lists everything it looked at is not a
    # screener, and signals must never be forced.
    matched = [c for c in candidates if c.structure is not None and c.gap is not None]

    caps = market_caps or {}
    if caps:
        below = [c.ticker for c in matched if (caps.get(c.ticker) or 0) < settings.min_market_cap]
        matched = [c for c in matched if c.ticker not in set(below)]
        if below:
            market_cap_note = f"{len(below)} name(s) dropped below the market-cap floor"

    matched.sort(key=_rank_key, reverse=True)
    # Near-misses are informative, but the watchlist should be mostly setups that
    # are genuinely waiting on a retrace.
    ready = [c for c in matched if c.status != STATUS_NO_TRADE]
    missed = [c for c in matched if c.status == STATUS_NO_TRADE]
    rows = [c.as_row() for c in (ready + missed[: max(3, limit // 4)])[:limit]]

    return {
        "timeframe": timeframe,
        "generated_at": (generated_at or date.today()).isoformat(),
        "screened": screened if screened is not None else len(entries),
        "matched": len(matched),
        "max_watchlist": limit,
        "rows": rows,
        "settings": {
            "min_rr": settings.min_rr,
            "risk_per_trade_pct": settings.risk_per_trade_pct,
            "earnings_buffer_days": settings.earnings_buffer_days,
            "min_price": settings.min_price,
            "min_volume": settings.min_volume,
            "min_market_cap": settings.min_market_cap,
            "market_cap_applied": bool(caps),
            "market_cap_note": market_cap_note
            or (
                None
                if caps
                else "Market capitalisation is not filtered: no market-cap source is configured."
            ),
            "allow_earnings_plays": settings.allow_earnings_plays,
        },
        "timeframes_available": list(configured_timeframes()),
        "intraday": intraday_note(),
        "method": (
            "A confirmed breakout structure sets the direction; a Fair Value Gap left by "
            "that leg sets the entry. The setup only becomes actionable once price "
            "retraces into the gap and the candle confirms."
        ),
        "demo": demo,
    }


def build_drilldown(
    ticker: str,
    name: str | None,
    sector: str | None,
    bars: list,
    timeframe: str,
    settings: FvgSettings | None = None,
    earnings_in_days: int | None = None,
    demo: bool = False,
) -> dict | None:
    """Chart annotations, structures and the signal card for one selected ticker.

    Returns ``None`` only when there are too few bars to say anything. An
    instrument with no valid setup still returns a card marked ``NO_TRADE`` with
    the levels and the reason, because that is a useful answer.
    """
    settings = settings or settings_from_config()
    if len(bars) < 3:
        return None

    candidate = analyze_fvg(
        ticker, name, sector, bars, timeframe, settings, earnings_in_days=earnings_in_days
    )

    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    atr_values = atr_series(highs, lows, closes)
    gaps = detect_fair_value_gaps(bars, timeframe, atr_values)
    swings = swing_indices(highs, lows)
    structures = detect_structures(bars, atr_values, swings)

    return {
        "ticker": ticker.upper(),
        "name": name,
        "sector": sector,
        "timeframe": timeframe,
        "as_of": bars[-1].date.isoformat(),
        "signal_card": signal_card(candidate, settings),
        "annotations": annotations(candidate, gaps, bars),
        "chart_markup": chart_markup(candidate, gaps, bars),
        "structures": [s.as_dict() for s in structures],
        "fvg_gaps": [g.as_dict() for g in gaps if g.is_open][:12],
        "open_gap_count": len(open_gaps(gaps)),
        "bars": [
            {
                "date": b.date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ],
        "indicators": {"ema20": ema(closes, 20), "ema50": ema(closes, 50), "atr": atr_values},
        "timeframes_available": list(configured_timeframes()),
        "intraday": intraday_note(),
        "demo": demo,
    }


# ---------------------------------------------------------------------------
# Live database
# ---------------------------------------------------------------------------
def _daily_bars(db: Session, ticker: str, timeframe: str, anchor: date) -> list:
    """Closed candles for one timeframe.

    The possibly-unfinished current session is removed *before* resampling, so a
    weekly or monthly candle built from a part-formed day can never be analysed.
    """
    start = anchor - timedelta(days=lookback_days(timeframe))
    daily = closed_only(data_service.load_bars(db, ticker, start, anchor))
    if not daily:
        return []
    return resample(daily, timeframe)


def _entries(db: Session, market_provider: MarketDataProvider, timeframe: str, anchor: date) -> list[Instrument]:
    out: list[Instrument] = []
    for meta in data_service.full_universe(db, market_provider):
        bars = _daily_bars(db, meta.ticker, timeframe, anchor)
        if len(bars) < MIN_BARS:
            continue
        out.append(
            Instrument(
                ticker=meta.ticker,
                name=meta.name,
                sector=meta.sector,
                bars=bars,
                earnings_in_days=days_to_earnings(db, meta.ticker, anchor),
            )
        )
    return out


def scan(
    db: Session,
    market_provider: MarketDataProvider,
    timeframe: str | None = None,
    limit: int | None = None,
    refresh: bool = False,
) -> dict:
    """Screen the universe and return the shortlist. No chart annotations."""
    settings = settings_from_config()
    tf = normalise(timeframe)
    limit = limit or settings.max_watchlist

    cache_key = f"{tf}:{limit}"
    if not refresh:
        with _lock:
            cached = _cache.get(cache_key)
            if cached and (time.time() - cached[0]) < CACHE_TTL:
                return cached[1]

    anchor = data_service.latest_trading_day(db) or date.today()
    entries = _entries(db, market_provider, tf, anchor)
    caps, cap_note = _market_caps(db, [e.ticker for e in entries])

    payload = build_shortlist(
        entries,
        tf,
        limit=limit,
        generated_at=anchor,
        screened=len(data_service.full_universe(db, market_provider)),
        settings=settings,
        market_caps=caps,
        market_cap_note=cap_note,
    )

    with _lock:
        _cache[cache_key] = (time.time(), payload)
    return payload


def drilldown(
    db: Session,
    market_provider: MarketDataProvider,
    ticker: str,
    timeframe: str | None = None,
) -> dict | None:
    """Annotations and the signal card for one selected ticker."""
    tf = normalise(timeframe)
    ticker = ticker.upper().strip()
    anchor = data_service.latest_trading_day(db) or date.today()

    meta = next(
        (m for m in data_service.full_universe(db, market_provider) if m.ticker == ticker),
        None,
    )
    bars = _daily_bars(db, ticker, tf, anchor)
    if len(bars) < 3:
        return None

    return build_drilldown(
        ticker,
        meta.name if meta else None,
        meta.sector if meta else None,
        bars,
        tf,
        settings_from_config(),
        earnings_in_days=days_to_earnings(db, ticker, anchor),
    )


def _market_caps(db: Session, tickers: list[str]) -> tuple[dict[str, float], str | None]:
    """Market caps when a source is configured.

    Bounded on purpose: a profile request per instrument across the whole universe
    would be slow and rate-limited, so the lookup is capped.
    """
    if not tickers:
        return {}, None
    try:
        from ..providers.registry import resolve_market_cap_provider

        provider = resolve_market_cap_provider(db)
    except Exception as exc:
        return {}, f"market-cap source unavailable: {exc}"
    if provider is None:
        return {}, None
    try:
        return provider.fetch(tickers[:25]), None
    except Exception as exc:
        return {}, f"market-cap lookup failed: {exc}"


def clear_cache() -> None:
    with _lock:
        _cache.clear()
