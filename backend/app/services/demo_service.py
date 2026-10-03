"""Synthetic DEMO dataset for visitors who are not signed in.

Every public read endpoint serves this to anonymous callers, so a publicly
reachable deployment never exposes the operator's real signals. All values come
from the deterministic MOCK providers, and the dataset is built once and cached
in memory (it is pure CPU work over synthetic series — nothing is written to the
database).

Demo signals are given ids starting at ``DEMO_ID_BASE`` so they can never
collide with real rows.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

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
from ..core.universe import UNIVERSE
from ..providers.mock_provider import MockMacroProvider, MockMarketDataProvider
from .macro_service import lagging_sectors, leading_sectors

DEMO_ID_BASE = 900_000
DEMO_LIMIT = 20
HISTORY_DAYS = 540
CHART_BARS = 180
CALENDAR_DAYS = 60

_lock = threading.Lock()
_cache: dict | None = None


def is_demo_signal_id(signal_id: int) -> bool:
    return signal_id >= DEMO_ID_BASE


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------
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

    drafts = []
    bars_by_ticker: dict[str, list] = {}
    for ticker, name, sector in UNIVERSE:
        bars = market.get_daily_bars(ticker, start, today)
        if len(bars) < MIN_BARS:
            continue
        bars_by_ticker[ticker] = bars
        drafts.extend(analyze_ticker(ticker, name, sector, bars, ctx))

    drafts.sort(key=lambda d: d.confidence, reverse=True)
    drafts = drafts[:DEMO_LIMIT]

    signals = [
        {
            "id": DEMO_ID_BASE + i,
            "ticker": d.ticker,
            "name": d.name,
            "date": today,
            "type": d.direction,
            "setup": d.setup,
            "entry": d.entry,
            "target": d.target,
            "stop": d.stop,
            "confidence": d.confidence,
            "price": d.price,
            "sector": d.sector,
            "confidence_components": d.confidence_components,
            "triggered_rules": d.triggered_rules,
            "event_flags": d.event_flags,
            "option_recommendation": None,
            "annotation": None,
        }
        for i, d in enumerate(drafts)
    ]

    events = macro.get_economic_calendar(today, today + timedelta(days=CALENDAR_DAYS))
    earnings = macro.get_earnings_calendar(
        [t for t, _, _ in UNIVERSE], today, today + timedelta(days=CALENDAR_DAYS)
    )

    return {
        "generated_at": today,
        "signals": signals,
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
def signals_payload(filters=None, limit: int = 50, offset: int = 0, show_all: bool = False) -> dict:
    data = dataset()
    rows = [s for s in data["signals"] if _matches(s, filters)]
    page = rows if show_all else rows[:DEMO_LIMIT]
    page = page[offset : offset + limit]
    return {
        "signals": page,
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "summary": _summary(data["signals"], data["snapshot"]),
        "demo": True,
    }


def summary_payload() -> dict:
    data = dataset()
    return _summary(data["signals"], data["snapshot"])


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
    signal = next((s for s in data["signals"] if s["id"] == signal_id), None)
    if signal is None:
        return None

    bars = data["bars_by_ticker"].get(signal["ticker"], [])[-CHART_BARS:]
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
        "option_chain": [],
        "demo": True,
    }


def reset_cache() -> None:
    """Drop the cached dataset (used by tests)."""
    global _cache
    with _lock:
        _cache = None


__all__ = [
    "DEMO_ID_BASE",
    "dataset",
    "detail_payload",
    "is_demo_signal_id",
    "macro_payload",
    "reset_cache",
    "signals_payload",
    "summary_payload",
]
