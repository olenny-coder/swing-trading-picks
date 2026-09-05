"""Signal endpoints: daily top-20 shortlist, filtered listing, summary, detail."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core import indicators as ta
from ..core.constants import SIGNAL_BUY_DOJI_REVERSAL, SIGNAL_BUY_STANDARD, SIGNAL_PUT
from ..database import get_db
from ..models import DailyBar, EarningsEvent, MacroEvent, MacroSnapshot, Signal, User
from ..providers.registry import resolve_market_provider
from ..schemas import (
    BarOut,
    OptionContractOut,
    SignalDetailOut,
    SignalFilters,
    SignalListResponse,
    SignalOut,
    SummaryResponse,
)
from ..services.credentials import resolve_credentials
from ..services.data_service import load_bars

router = APIRouter(prefix="/signals", tags=["signals"])

DIVERSITY_CAP_PER_SECTOR = 3


def latest_signal_date(db: Session) -> date | None:
    row = db.query(Signal.date).order_by(Signal.date.desc()).first()
    return row[0] if row else None


def _matches(sig: Signal, f: SignalFilters) -> bool:
    flags = sig.event_flags or {}
    if f.type and sig.type != f.type:
        return False
    if f.sector and sig.sector != f.sector:
        return False
    if f.min_confidence is not None and sig.confidence < f.min_confidence:
        return False
    if f.min_price is not None and sig.price < f.min_price:
        return False
    if f.max_price is not None and sig.price > f.max_price:
        return False
    if f.ticker and sig.ticker.upper() != f.ticker.upper():
        return False
    if f.exclude_earnings_week and flags.get("earnings_proximity"):
        return False
    if f.exclude_macro_risk and flags.get("macro_risk"):
        return False
    return True


def _diverse_shortlist(signals: list[Signal], limit: int) -> list[Signal]:
    selected: list[Signal] = []
    sector_count: dict[str, int] = {}
    for s in signals:  # pre-sorted by confidence desc
        if len(selected) >= limit:
            break
        sec = s.sector or "Unknown"
        if sector_count.get(sec, 0) >= DIVERSITY_CAP_PER_SECTOR:
            continue
        selected.append(s)
        sector_count[sec] = sector_count.get(sec, 0) + 1
    # Fill remaining slots with the highest-confidence not-yet-selected signals.
    if len(selected) < limit:
        for s in signals:
            if len(selected) >= limit:
                break
            if s not in selected:
                selected.append(s)
    return selected


def _summary(db: Session, signals: list[Signal]) -> SummaryResponse:
    total_buys = sum(1 for s in signals if s.type == SIGNAL_BUY_STANDARD)
    total_doji = sum(1 for s in signals if s.type == SIGNAL_BUY_DOJI_REVERSAL)
    total_puts = sum(1 for s in signals if s.type == SIGNAL_PUT)
    avg_conf = round(sum(s.confidence for s in signals) / len(signals), 1) if signals else 0.0
    high_count = sum(1 for s in signals if s.confidence >= 71)

    snap = db.query(MacroSnapshot).order_by(MacroSnapshot.date.desc()).first()
    today = date.today()
    upcoming = (
        db.query(MacroEvent)
        .filter(MacroEvent.datetime >= today)
        .count()
    )
    earnings_risk = sum(1 for s in signals if (s.event_flags or {}).get("earnings_proximity"))

    return SummaryResponse(
        total_buys=total_buys,
        total_puts=total_puts,
        total_doji=total_doji,
        avg_confidence=avg_conf,
        high_confidence_count=high_count,
        regime=snap.regime if snap else None,
        vix=snap.vix if snap else None,
        upcoming_macro_events=upcoming,
        earnings_risk_count=earnings_risk,
        generated_at=latest_signal_date(db),
    )


def _filters(
    type: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None),
    exclude_earnings_week: bool = Query(default=False),
    exclude_macro_risk: bool = Query(default=False),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    ticker: str | None = Query(default=None),
) -> SignalFilters:
    return SignalFilters(
        type=type,
        sector=sector,
        min_confidence=min_confidence,
        exclude_earnings_week=exclude_earnings_week,
        exclude_macro_risk=exclude_macro_risk,
        min_price=min_price,
        max_price=max_price,
        ticker=ticker,
    )


@router.get("/daily", response_model=SignalListResponse)
def daily_shortlist(
    all: bool = Query(default=False, description="Show all signals (no top-20 cap)"),
    filters: SignalFilters = Depends(_filters),
    db: Session = Depends(get_db),
) -> SignalListResponse:
    d = latest_signal_date(db)
    if d is None:
        return SignalListResponse(
            signals=[], total=0, limit=0, offset=0, summary=_summary(db, []).model_dump()
        )
    query = db.query(Signal).filter(Signal.date == d).order_by(Signal.confidence.desc())
    matched = [s for s in query.all() if _matches(s, filters)]
    limit = len(matched) if all else 20
    shortlist = matched if all else _diverse_shortlist(matched, limit)
    return SignalListResponse(
        signals=[SignalOut.model_validate(s) for s in shortlist],
        total=len(matched),
        limit=limit,
        offset=0,
        summary=_summary(db, matched).model_dump(),
    )


@router.get("", response_model=SignalListResponse)
def list_signals(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    date_: date | None = Query(default=None, alias="date"),
    filters: SignalFilters = Depends(_filters),
    db: Session = Depends(get_db),
) -> SignalListResponse:
    query = db.query(Signal)
    if date_ is not None:
        query = query.filter(Signal.date == date_)
    query = query.order_by(Signal.confidence.desc())
    matched = [s for s in query.all() if _matches(s, filters)]
    page = matched[offset : offset + limit]
    return SignalListResponse(
        signals=[SignalOut.model_validate(s) for s in page],
        total=len(matched),
        limit=limit,
        offset=offset,
        summary={},
    )


@router.get("/summary", response_model=SummaryResponse)
def summary(db: Session = Depends(get_db)) -> SummaryResponse:
    d = latest_signal_date(db)
    signals = db.query(Signal).filter(Signal.date == d).all() if d else []
    return _summary(db, signals)


@router.get("/{signal_id}", response_model=SignalDetailOut)
def signal_detail(
    signal_id: int,
    db: Session = Depends(get_db),
) -> SignalDetailOut:
    sig = db.query(Signal).filter(Signal.id == signal_id).first()
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    bars = load_bars(db, sig.ticker, sig.date - timedelta(days=180), sig.date)
    bar_outs = [BarOut(date=b.date, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume) for b in bars]

    closes = [b.close for b in bars]
    indicators = {
        "ema20": ta.ema(closes, 20),
        "ema50": ta.ema(closes, 50),
        "rsi": ta.rsi(closes),
        "atr": ta.atr([b.high for b in bars], [b.low for b in bars], closes),
    }
    macd_line, macd_signal, _ = ta.macd(closes)
    indicators["macd"] = macd_line
    indicators["macd_signal"] = macd_signal

    doji_highlight = False
    if len(bars) >= 2:
        last2 = bars[-2]
        doji_highlight = ta.is_doji(last2.open, last2.high, last2.low, last2.close)

    option_chain: list[OptionContractOut] = []
    if sig.type == SIGNAL_PUT:
        # Public read: use the primary (admin) user's credentials, falling back
        # to environment variables, so visitors still get the options chain.
        primary = db.query(User).order_by(User.id.asc()).first()
        creds = resolve_credentials(db, primary.id if primary else None)
        try:
            provider = resolve_market_provider(creds)
            option_chain = [
                OptionContractOut(
                    symbol=c.symbol,
                    strike=c.strike,
                    expiry=c.expiry,
                    bid=c.bid,
                    ask=c.ask,
                    last=c.last,
                    open_interest=c.open_interest,
                    implied_volatility=c.implied_volatility,
                )
                for c in provider.get_options_chain(sig.ticker, side="put")
            ]
        except Exception:
            option_chain = []

    return SignalDetailOut(
        signal=SignalOut.model_validate(sig),
        bars=bar_outs,
        indicators=indicators,
        doji_highlight=doji_highlight,
        option_chain=option_chain,
    )
