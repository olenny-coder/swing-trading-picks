"""Synthetic DEMO dataset for visitors who are not signed in.

Every public read endpoint serves this to anonymous callers, so a publicly
reachable deployment never exposes the operator's real signals. All values come
from the deterministic MOCK providers, and the dataset is built once and cached
in memory (it is pure CPU work over synthetic series — nothing is written to the
database).

The demo carries a live list per timeframe (daily, weekly, monthly) **and** a set
of earlier picks whose outcomes have already resolved, so History and the
accuracy view are meaningful without signing in.

Demo signals are given ids starting at ``DEMO_ID_BASE`` so they can never
collide with real rows.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

from ..core.base_types import SignalContext
from ..core.constants import (
    CONTINUATION_SETUPS,
    REVERSAL_SETUPS,
    SETUPS,
    SIGNAL_BUY,
    SIGNAL_SELL,
)
from ..core.indicators import ema
from ..core.sma_strategy import MIN_BARS, analyze_ticker
from ..core.timeframes import (
    DAILY,
    TIMEFRAMES,
    chart_window,
    is_complete_period,
    min_bars,
    normalise,
    resample,
)
from ..core.universe import UNIVERSE
from ..providers.mock_provider import MockMacroProvider, MockMarketDataProvider
from .macro_service import lagging_sectors, leading_sectors
from .outcome_service import OPEN, STOP_HIT, TARGET_HIT, evaluate

DEMO_ID_BASE = 900_000
DEMO_LIMIT = 20
HISTORY_DAYS = 2200
CHART_BARS = 180
CALENDAR_DAYS = 60

#: How many earlier candles per timeframe are replayed to build history.
HISTORY_STEPS = {DAILY: 14, "WEEKLY": 12, "MONTHLY": 6}
#: Cap on stored historical picks per timeframe, so the demo stays responsive.
HISTORY_CAP = {DAILY: 60, "WEEKLY": 40, "MONTHLY": 20}

_lock = threading.Lock()
_cache: dict | None = None


def is_demo_signal_id(signal_id: int) -> bool:
    return signal_id >= DEMO_ID_BASE


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------
def _history_indices(bars: list, timeframe: str, steps: int) -> list[int]:
    """Indices of earlier bars that end a *completed* candle of this timeframe."""
    out: list[int] = []
    for index in range(len(bars) - 2, -1, -1):
        if timeframe == DAILY or is_complete_period(bars[index].date, timeframe):
            out.append(index)
        if len(out) >= steps:
            break
    return out


def _to_signal(draft, timeframe: str, candle_date: date, signal_id: int) -> dict:
    return {
        "id": signal_id,
        "ticker": draft.ticker,
        "name": draft.name,
        "date": candle_date,
        "type": draft.direction,
        "setup": draft.setup,
        "timeframe": timeframe,
        "entry": draft.entry,
        "target": draft.target,
        "stop": draft.stop,
        "confidence": draft.confidence,
        "price": draft.price,
        "sector": draft.sector,
        "confidence_components": draft.confidence_components,
        "triggered_rules": draft.triggered_rules,
        "event_flags": draft.event_flags,
        "annotation": None,
        "outcome": None,
    }


def _build() -> dict:
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS)

    market = MockMarketDataProvider()
    macro = MockMacroProvider(today)
    snapshot = macro.get_macro_snapshot()
    strength = snapshot.sector_relative_strength or {}

    ctx = SignalContext(
        regime=snapshot.regime,
        vix=snapshot.vix,
        leading_sectors=leading_sectors(strength),
        lagging_sectors=lagging_sectors(strength),
        macro_sentiment=0.0,
    )

    next_id = DEMO_ID_BASE
    live: dict[str, list[dict]] = {tf: [] for tf in TIMEFRAMES}
    history: dict[str, list[dict]] = {tf: [] for tf in TIMEFRAMES}
    bars_by_ticker: dict[str, list] = {}

    for ticker, name, sector in UNIVERSE:
        daily = market.get_daily_bars(ticker, start, today)
        if len(daily) < MIN_BARS:
            continue
        bars_by_ticker[ticker] = daily

        for timeframe in TIMEFRAMES:
            ctx.timeframe = timeframe
            series = resample(daily, timeframe)
            if len(series) < min_bars(timeframe):
                continue

            # The live list: the most recently completed candle.
            for draft in analyze_ticker(ticker, name, sector, series, ctx):
                live[timeframe].append(_to_signal(draft, timeframe, series[-1].date, next_id))
                next_id += 1

            # Replay earlier candles so History and the accuracy view have
            # results that have already resolved.
            for index in _history_indices(daily, timeframe, HISTORY_STEPS[timeframe]):
                past_series = resample(daily[: index + 1], timeframe)
                if len(past_series) < min_bars(timeframe):
                    continue
                for draft in analyze_ticker(ticker, name, sector, past_series, ctx):
                    record = _to_signal(draft, timeframe, past_series[-1].date, next_id)
                    next_id += 1
                    record["outcome"] = evaluate(
                        draft.direction,
                        draft.entry,
                        draft.target,
                        draft.stop,
                        daily[index + 1 :],
                        timeframe,
                    )
                    history[timeframe].append(record)

    picks: dict[str, list[dict]] = {}
    for timeframe in TIMEFRAMES:
        newest = sorted(live[timeframe], key=lambda s: s["confidence"], reverse=True)[:DEMO_LIMIT]
        past = sorted(history[timeframe], key=lambda s: s["date"], reverse=True)
        picks[timeframe] = newest + past[: HISTORY_CAP[timeframe]]

    events = macro.get_economic_calendar(today, today + timedelta(days=CALENDAR_DAYS))
    earnings = macro.get_earnings_calendar(
        [t for t, _, _ in UNIVERSE], today, today + timedelta(days=CALENDAR_DAYS)
    )

    return {
        "generated_at": today,
        "signals": picks,
        "bars_by_ticker": bars_by_ticker,
        "snapshot": {
            "date": snapshot.date,
            "regime": snapshot.regime,
            "spy_close": snapshot.spy_close,
            "spy_ma200": snapshot.spy_ma200,
            "vix": snapshot.vix,
            "vix_term_structure": snapshot.vix_term_structure,
            "ten_year_yield": snapshot.ten_year_yield,
            "fed_funds_rate": snapshot.fed_funds_rate,
            "sector_relative_strength": strength,
        },
        "macro_events": [
            {
                "id": 1_000_000 + i,
                "title": e.title,
                "datetime": e.datetime,
                "importance": e.importance,
                "sentiment": e.sentiment,
                "category": e.category,
                "country": e.country,
                "forecast": e.forecast,
                "previous": e.previous,
                "actual": e.actual,
            }
            for i, e in enumerate(events)
        ],
        "earnings": [
            {
                "id": 2_000_000 + i,
                "ticker": e.ticker,
                "report_date": e.report_date,
                "fiscal_quarter": e.fiscal_quarter,
                "eps_estimate": e.eps_estimate,
                "eps_actual": e.eps_actual,
                "revenue_estimate": e.revenue_estimate,
            }
            for i, e in enumerate(earnings)
        ],
    }


def dataset() -> dict:
    """Return the cached demo dataset, building it on first use."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _build()
        return _cache


def _rows(timeframe: str | None) -> list[dict]:
    return dataset()["signals"].get(normalise(timeframe), [])


def _live_rows(timeframe: str | None) -> list[dict]:
    """Only the most recently completed candle's picks — the 'daily view' list."""
    rows = _rows(timeframe)
    newest = max((s["date"] for s in rows), default=None)
    return [s for s in rows if s["date"] == newest] if newest else []


def _summary(signals: list[dict], snapshot: dict) -> dict:
    def count(pred) -> int:
        return sum(1 for s in signals if pred(s))

    confidences = [s["confidence"] for s in signals]
    return {
        "total_buys": count(lambda s: s["type"] == SIGNAL_BUY),
        "total_sells": count(lambda s: s["type"] == SIGNAL_SELL),
        "total_continuation": count(lambda s: s["setup"] in CONTINUATION_SETUPS),
        "total_reversal": count(lambda s: s["setup"] in REVERSAL_SETUPS),
        "setup_counts": {code: count(lambda s, c=code: s["setup"] == c) for code in SETUPS},
        "avg_confidence": round(sum(confidences) / len(confidences), 1) if confidences else 0.0,
        "high_confidence_count": count(lambda s: s["confidence"] >= 71),
        "regime": snapshot.get("regime"),
        "vix": snapshot.get("vix"),
        "upcoming_macro_events": 0,
        "earnings_risk_count": count(lambda s: (s["event_flags"] or {}).get("earnings_proximity")),
        "generated_at": None,
    }


def _matches(signal: dict, filters) -> bool:
    if filters is None:
        return True
    flags = signal.get("event_flags") or {}
    if filters.type and signal["type"] != filters.type:
        return False
    if filters.setup and signal["setup"] != filters.setup:
        return False
    if filters.sector and signal["sector"] != filters.sector:
        return False
    if filters.min_confidence is not None and signal["confidence"] < filters.min_confidence:
        return False
    if filters.min_price is not None and signal["price"] < filters.min_price:
        return False
    if filters.max_price is not None and signal["price"] > filters.max_price:
        return False
    if filters.ticker and signal["ticker"].upper() != filters.ticker.upper():
        return False
    if filters.exclude_earnings_week and flags.get("earnings_proximity"):
        return False
    if filters.exclude_macro_risk and flags.get("macro_risk"):
        return False
    return True


# ---------------------------------------------------------------------------
# Public payloads
# ---------------------------------------------------------------------------
def _requested_timeframe(filters, timeframe: str | None) -> str:
    return normalise(timeframe or getattr(filters, "timeframe", None))


def signals_payload(
    filters=None,
    limit: int = 50,
    offset: int = 0,
    show_all: bool = False,
    timeframe: str | None = None,
) -> dict:
    """The live shortlist: only the most recent completed candle's picks."""
    data = dataset()
    resolved = _requested_timeframe(filters, timeframe)
    rows = [s for s in _live_rows(resolved) if _matches(s, filters)]
    return {
        "signals": rows[:limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "summary": _summary(rows, data["snapshot"]),
        "demo": True,
    }


def history_payload(
    filters=None, limit: int = 200, offset: int = 0, timeframe: str | None = None
) -> dict:
    """Every stored pick of the timeframe, most recent first."""
    data = dataset()
    resolved = _requested_timeframe(filters, timeframe)
    rows = [s for s in data["signals"].get(resolved, []) if _matches(s, filters)]
    rows.sort(key=lambda s: s["date"], reverse=True)
    return {
        "signals": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "summary": _summary(rows, data["snapshot"]),
        "demo": True,
    }


def summary_payload(timeframe: str | None = None) -> dict:
    """Summary of the live shortlist, matching what the daily view displays."""
    data = dataset()
    return _summary(_live_rows(timeframe), data["snapshot"])


def accuracy_from(rows: list[dict], timeframe: str) -> dict:
    """Same shape as ``outcome_service.accuracy_summary``."""
    evaluated = [s for s in rows if s.get("outcome")]
    counts = {TARGET_HIT: 0, STOP_HIT: 0, OPEN: 0, "EXPIRED": 0}
    wins: list[float] = []
    losses: list[float] = []
    by_setup: dict[str, dict] = {}

    for signal in evaluated:
        outcome = signal["outcome"]
        status = outcome.get("status") or OPEN
        counts[status] = counts.get(status, 0) + 1
        pnl = float(outcome.get("pnl_pct") or 0.0)
        if status == TARGET_HIT:
            wins.append(pnl)
        elif status == STOP_HIT:
            losses.append(pnl)
        bucket = by_setup.setdefault(
            signal["setup"], {"setup": signal["setup"], "total": 0, TARGET_HIT: 0, STOP_HIT: 0}
        )
        bucket["total"] += 1
        if status in (TARGET_HIT, STOP_HIT):
            bucket[status] += 1

    decided = counts[TARGET_HIT] + counts[STOP_HIT]
    every = [float(s["outcome"].get("pnl_pct") or 0.0) for s in evaluated]
    for bucket in by_setup.values():
        resolved = bucket[TARGET_HIT] + bucket[STOP_HIT]
        bucket["win_rate_pct"] = round(bucket[TARGET_HIT] / resolved * 100.0, 1) if resolved else None

    return {
        "timeframe": timeframe,
        "evaluated": len(evaluated),
        "target_hit": counts[TARGET_HIT],
        "stop_hit": counts[STOP_HIT],
        "open": counts[OPEN],
        "expired": counts["EXPIRED"],
        "decided": decided,
        "win_rate_pct": round(counts[TARGET_HIT] / decided * 100.0, 1) if decided else None,
        "avg_pnl_pct": round(sum(every) / len(every), 2) if every else None,
        "avg_win_pct": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else None,
        "by_setup": sorted(by_setup.values(), key=lambda b: b["setup"]),
    }


def accuracy_payload(timeframe: str | None = None) -> dict:
    resolved = normalise(timeframe)
    return accuracy_from(_rows(resolved), resolved)


def macro_payload() -> dict:
    data = dataset()
    return {
        "snapshot": data["snapshot"],
        "macro_events": data["macro_events"],
        "earnings": data["earnings"],
        "sector_heatmap": data["snapshot"].get("sector_relative_strength") or {},
        "demo": True,
    }


def detail_payload(signal_id: int) -> dict | None:
    data = dataset()
    signal = None
    for rows in data["signals"].values():
        signal = next((s for s in rows if s["id"] == signal_id), None)
        if signal is not None:
            break
    if signal is None:
        return None

    timeframe = normalise(signal.get("timeframe"))
    daily = data["bars_by_ticker"].get(signal["ticker"], [])
    bars = resample(daily[-chart_window(timeframe) :], timeframe)
    closes = [b.close for b in bars]
    return {
        "signal": signal,
        "bars": [
            {
                "date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ],
        "indicators": {"ema20": ema(closes, 20), "ema50": ema(closes, 50)},
        "doji_highlight": False,
        "demo": True,
    }


def reset_cache() -> None:
    """Drop the cached dataset (used by tests)."""
    global _cache
    with _lock:
        _cache = None


__all__ = [
    "DEMO_ID_BASE",
    "accuracy_payload",
    "dataset",
    "detail_payload",
    "history_payload",
    "is_demo_signal_id",
    "macro_payload",
    "reset_cache",
    "signals_payload",
    "summary_payload",
]
