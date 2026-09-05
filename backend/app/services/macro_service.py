"""Macro snapshot, market-regime, and signal-context assembly.

The macro snapshot aggregates: index levels (SPY vs 200-day MA), VIX, yield
curve, and sector relative strength. Regime and sector rotation then drive the
signal engine's buy/put bias and confidence adjustments.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..core.base_types import SignalContext
from ..core.constants import SECTOR_ETFS
from ..core.regime import (
    classify_regime,
    lagging_sectors,
    leading_sectors,
    sector_relative_strength,
)
from ..models import EarningsEvent, MacroEvent, MacroSnapshot
from ..providers.base import MacroDataProvider, MarketDataProvider, MacroSnapshotData

_LOOKBACK = timedelta(days=420)
_SECTOR_LOOKBACK = timedelta(days=120)


def build_and_store_snapshot(
    db: Session,
    market_provider: MarketDataProvider,
    macro_provider: MacroDataProvider,
    as_of: date,
) -> MacroSnapshotData:
    snap = macro_provider.get_macro_snapshot()

    # Fill SPY close / 200-day MA from market data if the provider lacks it.
    if snap.spy_close is None or snap.spy_ma200 is None:
        spy_bars = _safe_bars(market_provider, "SPY", as_of - _LOOKBACK, as_of)
        if spy_bars:
            closes = [b.close for b in spy_bars]
            if snap.spy_close is None:
                snap.spy_close = closes[-1]
            if snap.spy_ma200 is None and len(closes) >= 200:
                snap.spy_ma200 = sum(closes[-200:]) / 200.0

    # Sector relative strength: prefer what the macro provider already supplied
    # (Yahoo Finance); only fall back to market-provider ETF bars when absent.
    if snap.sector_relative_strength:
        snap.sector_relative_strength = _normalize_strength_keys(snap.sector_relative_strength)
    else:
        sector_closes: dict[str, list[float]] = {}
        for etf, sector_name in SECTOR_ETFS.items():
            bars = _safe_bars(market_provider, etf, as_of - _SECTOR_LOOKBACK, as_of)
            if bars:
                sector_closes[sector_name] = [b.close for b in bars]
        if sector_closes:
            snap.sector_relative_strength = sector_relative_strength(sector_closes)

    snap.regime = classify_regime(snap.spy_close, snap.spy_ma200, snap.vix)
    snap.date = as_of

    row = db.query(MacroSnapshot).filter(MacroSnapshot.date == as_of).first()
    if row is None:
        row = MacroSnapshot(date=as_of)
        db.add(row)
    row.spy_close = snap.spy_close
    row.spy_ma200 = snap.spy_ma200
    row.regime = snap.regime
    row.vix = snap.vix
    row.vix_term_structure = snap.vix_term_structure
    row.ten_year_yield = snap.ten_year_yield
    row.fed_funds_rate = snap.fed_funds_rate
    row.sector_relative_strength = snap.sector_relative_strength
    db.commit()
    return snap


def _safe_bars(provider: MarketDataProvider, symbol: str, start: date, end: date) -> list:
    try:
        return provider.get_daily_bars(symbol, start, end)
    except Exception:
        return []


def _normalize_strength_keys(strength: dict[str, float]) -> dict[str, float]:
    """Translate ETF-ticker keys (e.g. XLK) to GICS sector names."""
    return {SECTOR_ETFS.get(k, k): v for k, v in strength.items()}


def get_latest_snapshot(db: Session) -> MacroSnapshot | None:
    return db.query(MacroSnapshot).order_by(MacroSnapshot.date.desc()).first()


def days_to_earnings(db: Session, ticker: str, signal_date: date) -> int | None:
    row = (
        db.query(EarningsEvent)
        .filter(EarningsEvent.ticker == ticker, EarningsEvent.report_date >= signal_date)
        .order_by(EarningsEvent.report_date.asc())
        .first()
    )
    if row is None:
        return None
    return (row.report_date - signal_date).days


def high_impact_events_near(db: Session, as_of: date, days: int = 3) -> bool:
    """True if a high-impact macro event lands within ``days`` calendar days."""
    row = (
        db.query(MacroEvent)
        .filter(
            MacroEvent.importance == "high",
            MacroEvent.datetime >= as_of,
            MacroEvent.datetime <= as_of + timedelta(days=days),
        )
        .first()
    )
    return row is not None


def rate_rising_sharply(db: Session) -> bool:
    snapshots = (
        db.query(MacroSnapshot)
        .filter(MacroSnapshot.ten_year_yield.isnot(None))
        .order_by(MacroSnapshot.date.desc())
        .limit(2)
        .all()
    )
    if len(snapshots) < 2:
        return False
    latest, prev = snapshots[0], snapshots[1]
    return (latest.ten_year_yield - prev.ten_year_yield) >= 0.20


_SENTIMENT_WEIGHT = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
_IMPORTANCE_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.5}


def net_macro_sentiment(db: Session, as_of: date, days: int = 7) -> float:
    """Net sentiment of upcoming economic events, normalized to -1.0 .. 1.0.

    Positive events (e.g. cooling inflation) nudge confidence up; negative
    events nudge it down. Importance-weighted.
    """
    events = (
        db.query(MacroEvent)
        .filter(MacroEvent.datetime >= as_of, MacroEvent.datetime <= as_of + timedelta(days=days))
        .all()
    )
    if not events:
        return 0.0
    weighted = sum(
        _SENTIMENT_WEIGHT.get(e.sentiment, 0.0) * _IMPORTANCE_WEIGHT.get(e.importance, 1.0)
        for e in events
    )
    denom = sum(_IMPORTANCE_WEIGHT.get(e.importance, 1.0) for e in events) or 1.0
    return max(-1.0, min(1.0, weighted / denom))


def build_signal_context(
    db: Session,
    as_of: date,
    backtest_win_rates: dict[str, float],
    allow_earnings_plays: bool = False,
) -> SignalContext:
    snap = get_latest_snapshot(db)
    regime = snap.regime if snap else "neutral"
    vix = snap.vix if snap else None
    strength = snap.sector_relative_strength if snap else {}
    strength = _normalize_strength_keys(strength) if strength else {}

    return SignalContext(
        regime=regime,
        vix=vix,
        leading_sectors=leading_sectors(strength),
        lagging_sectors=lagging_sectors(strength),
        rate_rising_sharply=rate_rising_sharply(db),
        high_impact_events_within_2d=high_impact_events_near(db, as_of),
        macro_sentiment=net_macro_sentiment(db, as_of),
        allow_earnings_plays=allow_earnings_plays,
        backtest_win_rates=backtest_win_rates,
    )
