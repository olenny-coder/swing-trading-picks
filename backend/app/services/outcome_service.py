"""Retrospective accuracy: did each pick reach its target, or its stop?

Every stored signal is walked forward against the daily bars that followed it.
The levels are checked bar by bar; when a single candle touches both the stop
and the target the **stop is assumed to have been hit first**, which is the
conservative reading and avoids flattering the win rate.

A pick that reaches neither level inside its horizon is marked ``EXPIRED`` and
scored on the last available close, while one still inside its horizon is
``OPEN`` and re-evaluated on the next run.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..core.constants import SIGNAL_BUY, SIGNAL_SELL
from ..core.timeframes import DAILY, normalise

logger = logging.getLogger(__name__)

TARGET_HIT = "TARGET_HIT"
STOP_HIT = "STOP_HIT"
OPEN = "OPEN"
EXPIRED = "EXPIRED"

#: How long a pick is given to work, expressed in daily bars.
HORIZON_DAYS: dict[str, int] = {
    DAILY: 10,
    "WEEKLY": 42,
    "MONTHLY": 90,
}


def horizon_days(timeframe: str) -> int:
    return HORIZON_DAYS.get(normalise(timeframe), HORIZON_DAYS[DAILY])


def _pct(direction: str, entry: float, price: float) -> float:
    if not entry:
        return 0.0
    move = (price - entry) / entry
    return round(move * 100.0 if direction == SIGNAL_BUY else -move * 100.0, 2)


def evaluate(
    direction: str,
    entry: float,
    target: float,
    stop: float,
    bars: list,
    timeframe: str = DAILY,
) -> dict | None:
    """Score one pick against the bars that followed it.

    ``bars`` must be chronological **daily** bars dated after the signal.
    Returns ``None`` when there is no data to judge with.
    """
    if not bars:
        return None

    limit = horizon_days(timeframe)
    window = bars[:limit]
    long_side = direction == SIGNAL_BUY

    best = worst = 0.0
    for index, bar in enumerate(window):
        favourable = (bar.high - entry) if long_side else (entry - bar.low)
        adverse = (entry - bar.low) if long_side else (bar.high - entry)
        best = max(best, favourable / entry * 100.0 if entry else 0.0)
        worst = max(worst, adverse / entry * 100.0 if entry else 0.0)

        hit_stop = bar.low <= stop if long_side else bar.high >= stop
        hit_target = bar.high >= target if long_side else bar.low <= target

        # Conservative: if one candle spans both levels, assume the stop first.
        if hit_stop:
            return {
                "status": STOP_HIT,
                "exit_price": round(stop, 2),
                "exit_date": bar.date.isoformat(),
                "bars_held": index + 1,
                "pnl_pct": _pct(direction, entry, stop),
                "max_favourable_pct": round(best, 2),
                "max_adverse_pct": round(worst, 2),
                "evaluated_at": date.today().isoformat(),
            }
        if hit_target:
            return {
                "status": TARGET_HIT,
                "exit_price": round(target, 2),
                "exit_date": bar.date.isoformat(),
                "bars_held": index + 1,
                "pnl_pct": _pct(direction, entry, target),
                "max_favourable_pct": round(best, 2),
                "max_adverse_pct": round(worst, 2),
                "evaluated_at": date.today().isoformat(),
            }

    last = window[-1]
    return {
        "status": OPEN if len(bars) <= limit else EXPIRED,
        "exit_price": round(last.close, 2),
        "exit_date": last.date.isoformat(),
        "bars_held": len(window),
        "pnl_pct": _pct(direction, entry, last.close),
        "max_favourable_pct": round(best, 2),
        "max_adverse_pct": round(worst, 2),
        "evaluated_at": date.today().isoformat(),
    }


def update_outcomes(db: Session, limit: int | None = None, only_missing: bool = False) -> dict:
    """Re-evaluate stored picks and persist their result.

    Picks whose outcome is already ``TARGET_HIT``/``STOP_HIT`` are left alone
    unless ``only_missing`` is false, so the settled history stays stable.
    """
    from ..models import Signal  # local import avoids a circular import
    from .data_service import load_bars

    query = db.query(Signal)
    if only_missing:
        query = query.filter(Signal.outcome.is_(None))
    query = query.order_by(Signal.date.desc())
    if limit:
        query = query.limit(limit)

    settled = {TARGET_HIT, STOP_HIT}
    updated = 0
    skipped = 0
    for signal in query.all():
        existing = signal.outcome or {}
        if existing.get("status") in settled:
            skipped += 1
            continue

        start = signal.date + timedelta(days=1)
        end = signal.date + timedelta(days=horizon_days(signal.timeframe) + 10)
        bars = load_bars(db, signal.ticker, start, end)
        outcome = evaluate(
            signal.type,
            float(signal.entry),
            float(signal.target),
            float(signal.stop),
            bars,
            signal.timeframe or DAILY,
        )
        if outcome is None:
            skipped += 1
            continue

        signal.outcome = outcome
        db.add(signal)
        updated += 1

    db.commit()
    return {"updated": updated, "skipped": skipped}


def accuracy_summary(db: Session, timeframe: str | None = None) -> dict:
    """Aggregate accuracy across evaluated picks, optionally per timeframe."""
    from ..models import Signal

    query = db.query(Signal).filter(Signal.outcome.isnot(None))
    if timeframe:
        query = query.filter(Signal.timeframe == normalise(timeframe))
    rows = query.all()

    counts = {TARGET_HIT: 0, STOP_HIT: 0, OPEN: 0, EXPIRED: 0}
    wins: list[float] = []
    losses: list[float] = []
    by_setup: dict[str, dict] = {}

    for signal in rows:
        outcome = signal.outcome or {}
        status = outcome.get("status") or OPEN
        counts[status] = counts.get(status, 0) + 1
        pnl = float(outcome.get("pnl_pct") or 0.0)
        if status == TARGET_HIT:
            wins.append(pnl)
        elif status == STOP_HIT:
            losses.append(pnl)

        bucket = by_setup.setdefault(
            signal.setup, {"setup": signal.setup, "total": 0, TARGET_HIT: 0, STOP_HIT: 0}
        )
        bucket["total"] += 1
        if status in (TARGET_HIT, STOP_HIT):
            bucket[status] += 1

    decided = counts[TARGET_HIT] + counts[STOP_HIT]
    every_pnl = [float((s.outcome or {}).get("pnl_pct") or 0.0) for s in rows]

    for bucket in by_setup.values():
        resolved = bucket[TARGET_HIT] + bucket[STOP_HIT]
        bucket["win_rate_pct"] = (
            round(bucket[TARGET_HIT] / resolved * 100.0, 1) if resolved else None
        )

    return {
        "timeframe": normalise(timeframe) if timeframe else None,
        "evaluated": len(rows),
        "target_hit": counts[TARGET_HIT],
        "stop_hit": counts[STOP_HIT],
        "open": counts[OPEN],
        "expired": counts[EXPIRED],
        "decided": decided,
        "win_rate_pct": round(counts[TARGET_HIT] / decided * 100.0, 1) if decided else None,
        "avg_pnl_pct": round(sum(every_pnl) / len(every_pnl), 2) if every_pnl else None,
        "avg_win_pct": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else None,
        "by_setup": sorted(by_setup.values(), key=lambda b: b["setup"]),
    }
