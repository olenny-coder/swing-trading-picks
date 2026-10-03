"""LLM research agent.

Annotates **existing** signals with:

- ``sentiment``          — the model's near-term view of the stock,
- ``risk_flags``         — a fixed vocabulary of concrete risks,
- ``confidence_delta``   — a **bounded** adjustment to the engine's confidence,
- ``rationale``          — a short, specific justification.

Design constraints
------------------
- **Groq free tier.** Prompts are deliberately compact (a few hundred tokens)
  and calls are sequential with a configurable pause, because the binding limit
  is tokens-per-minute.
- **The model's reply is untrusted data.** It is validated against a strict
  schema here: enums are whitelisted, flag names are whitelisted, the delta is
  clamped to ``llm_max_confidence_delta``, and the rationale is length-capped
  and stripped of newlines. Nothing from the reply is ever executed, imported,
  or used as an instruction.
- **Additive only.** The engine's own ``confidence`` is never overwritten; the
  adjusted value is stored alongside it so both remain auditable.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import indicators as ta
from ..core.constants import SETUP_LABELS
from ..models import Signal
from ..providers.groq_provider import GroqError, GroqProvider
from . import credentials as creds_svc

logger = logging.getLogger(__name__)

SENTIMENTS = ("bullish", "bearish", "neutral", "mixed")

RISK_FLAGS = (
    "earnings_soon",
    "macro_event",
    "extended_move",
    "chasing_entry",
    "wide_stop",
    "weak_volume",
    "counter_trend",
    "overbought",
    "oversold",
    "sector_weakness",
    "sector_strength",
    "event_gap_risk",
    "low_liquidity",
    "news_risk",
)

MAX_FLAGS = 4
MAX_RATIONALE = 280
BRIEF_BARS = 8

SYSTEM_PROMPT = (
    "You are a risk analyst on a swing-trading desk. You are given ONE candidate "
    "setup on a US equity, computed from daily bars. Judge how likely that setup is "
    "to work IN ITS STATED DIRECTION over the next 5-15 sessions.\n\n"
    "Reply with JSON only, exactly this shape:\n"
    '{"sentiment":"bullish|bearish|neutral|mixed",'
    '"risk_flags":["flag"],'
    '"confidence_delta":0,'
    '"rationale":"..."}\n\n'
    "Rules:\n"
    "- sentiment: your near-term view of the STOCK, not of the trade.\n"
    "- confidence_delta: integer from -15 to 15. Positive means you are MORE "
    "confident the setup works as stated; negative means LESS. Use 0 when the "
    "data adds nothing.\n"
    "- risk_flags: 0-4 items, each chosen ONLY from this list: "
    + ", ".join(RISK_FLAGS)
    + ".\n"
    f"- rationale: at most {MAX_RATIONALE} characters, one or two sentences, "
    "concrete and tied to the numbers you were given. Do not give advice and do "
    "not address the reader.\n"
    "- Use ONLY the supplied data. Do not invent news, prices, events or "
    "fundamentals that are not present. If the data is insufficient, say so in "
    "the rationale and use a small delta."
)


# ---------------------------------------------------------------------------
# Brief construction
# ---------------------------------------------------------------------------
def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f}%"


def build_brief(db: Session, signal: Signal) -> str:
    """Render one signal as a compact, self-contained prompt (few hundred tokens)."""
    from .data_service import load_bars  # local import avoids a circular import

    flags = signal.event_flags or {}
    components = signal.confidence_components or {}

    lines = [
        f"TICKER: {signal.ticker}"
        + (f" ({signal.name})" if signal.name else "")
        + (f" | sector {signal.sector}" if signal.sector else ""),
        f"SETUP: {signal.setup} ({SETUP_LABELS.get(signal.setup, signal.setup)})"
        f" | direction {signal.type}",
    ]

    entry = float(signal.entry or 0.0)
    stop = float(signal.stop or 0.0)
    target = float(signal.target or 0.0)
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = (reward / risk) if risk else 0.0
    stop_pct = (risk / entry) if entry else 0.0
    target_pct = (reward / entry) if entry else 0.0
    lines.append(
        f"LEVELS: entry {entry:.2f}, stop {stop:.2f} ({stop_pct * 100:.1f}% risk), "
        f"target {target:.2f} ({target_pct * 100:.1f}% reward) | RR {rr:.1f}"
    )

    flag_delta = (signal.annotation or {}).get("confidence_delta")
    lines.append(
        f"ENGINE CONFIDENCE: {signal.confidence:.1f}"
        + (f" (previous LLM delta {flag_delta:+g})" if isinstance(flag_delta, (int, float)) else "")
        + " | components: "
        + ", ".join(f"{k} {v:.0f}" for k, v in components.items() if isinstance(v, (int, float)))
    )

    rules = signal.triggered_rules or []
    if rules:
        lines.append("TRIGGERED: " + ", ".join(str(r) for r in rules[:8]))

    # Recent price action + indicators from stored bars.
    try:
        bars = load_bars(db, signal.ticker, signal.date - timedelta(days=160), signal.date)
    except Exception:  # pragma: no cover - defensive; brief still works without bars
        bars = []

    if bars:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        volumes = [b.volume for b in bars]
        last = len(bars) - 1

        recent = ", ".join(f"{c:.2f}" for c in closes[-BRIEF_BARS:])
        lines.append(f"PRICE: {closes[last]:.2f} | last {len(closes[-BRIEF_BARS:])} closes: {recent}")

        sma20 = ta.sma(closes, 20)
        sma50 = ta.sma(closes, 50)
        rsi = ta.rsi(closes)
        atr = ta.atr(highs, lows, closes)
        avg_vol = (sum(volumes[-20:]) / 20) if volumes[-20:] else 0.0

        vs20 = (closes[last] / sma20[last] - 1) if sma20[last] else None
        vs50 = (closes[last] / sma50[last] - 1) if sma50[last] else None
        change5 = (closes[last] / closes[-6] - 1) if len(closes) > 6 and closes[-6] else None
        change20 = (closes[last] / closes[-21] - 1) if len(closes) > 21 and closes[-21] else None
        atr_pct = (atr[last] / closes[last]) if atr[last] and closes[last] else None
        vol_ratio = (volumes[last] / avg_vol) if avg_vol else None

        if rsi[last] is not None and vol_ratio is not None and atr_pct is not None:
            lines.append(
                f"INDICATORS: RSI14 {rsi[last]:.0f} | ATR {atr_pct * 100:.1f}%"
                f" | vs SMA20 {_pct(vs20)} | vs SMA50 {_pct(vs50)}"
                f" | 5d {_pct(change5)} | 20d {_pct(change20)}"
                f" | volume x{vol_ratio:.1f}"
            )
        else:
            lines.append("INDICATORS: insufficient history")

    vix = flags.get("vix")
    vix_txt = f"{float(vix):.1f}" if isinstance(vix, (int, float)) else "n/a"
    earnings_days = flags.get("earnings_in_days")
    earnings_txt = f"in {earnings_days}d" if isinstance(earnings_days, int) else "not near"
    lines.append(
        "CONTEXT: "
        f"regime {flags.get('regime', 'unknown')}"
        f" | VIX {vix_txt}"
        f" | earnings {earnings_txt}"
        f" | macro sentiment {flags.get('macro_sentiment', 0)}"
        f" | high-impact event within 2d: {'yes' if flags.get('macro_risk') else 'no'}"
        f" | options chain: {'yes' if flags.get('options_liquid') else 'unavailable'}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation (the LLM reply is untrusted)
# ---------------------------------------------------------------------------
def validate_annotation(raw: dict, base_confidence: float, max_delta: float) -> dict:
    """Coerce an untrusted model reply into a safe, bounded annotation."""
    if not isinstance(raw, dict):
        raw = {}

    sentiment = str(raw.get("sentiment", "")).strip().lower()
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"

    flags_in = raw.get("risk_flags")
    if isinstance(flags_in, str):
        flags_in = [flags_in]
    if not isinstance(flags_in, (list, tuple)):
        flags_in = []
    flags: list[str] = []
    for item in flags_in:
        name = str(item).strip().lower().replace(" ", "_").replace("-", "_")
        if name in RISK_FLAGS and name not in flags:
            flags.append(name)
        if len(flags) >= MAX_FLAGS:
            break

    try:
        delta = float(raw.get("confidence_delta", 0) or 0)
    except (TypeError, ValueError):
        delta = 0.0
    if delta != delta or delta in (float("inf"), float("-inf")):  # NaN / inf guard
        delta = 0.0
    delta = round(max(-max_delta, min(max_delta, delta)), 1)

    rationale = " ".join(str(raw.get("rationale", "")).split())[:MAX_RATIONALE]

    adjusted = round(max(0.0, min(100.0, base_confidence + delta)), 1)
    return {
        "sentiment": sentiment,
        "risk_flags": flags,
        "confidence_delta": delta,
        "base_confidence": round(float(base_confidence), 1),
        "adjusted_confidence": adjusted,
        "supports_setup": delta > 0,
        "rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Running the agent
# ---------------------------------------------------------------------------
def resolve_provider(db: Session, user_id: int | None = None) -> GroqProvider | None:
    """Build a Groq client from UI-stored (encrypted) or env credentials."""
    settings = get_settings()
    if not settings.llm_research_enabled:
        return None
    try:
        creds = creds_svc.resolve_credentials(db, user_id)
    except Exception:  # pragma: no cover - defensive
        creds = {}
    entry = creds.get("groq") or {}
    api_key = entry.get("api_key") or settings.groq_api_key
    if not api_key:
        return None
    return GroqProvider(
        api_key=api_key,
        model=entry.get("model") or settings.groq_model,
        base_url=settings.groq_base_url,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )


def annotate_signal(db: Session, signal: Signal, provider: GroqProvider) -> dict:
    """One LLM call -> a validated annotation (does not persist)."""
    settings = get_settings()
    brief = build_brief(db, signal)
    completion = provider.complete_json(
        system=SYSTEM_PROMPT,
        user=brief,
        max_tokens=settings.llm_research_max_tokens,
        temperature=0.2,
    )
    annotation = validate_annotation(
        completion.data, float(signal.confidence), settings.llm_max_confidence_delta
    )
    annotation.update(
        {
            "model": completion.model,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "usage": completion.usage,
        }
    )
    return annotation


def select_signals(
    db: Session,
    signal_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[Signal]:
    """Highest-confidence signals first; skips already-annotated ones unless forced."""
    settings = get_settings()
    cap = limit or settings.llm_research_max_signals
    query = db.query(Signal)
    if signal_ids:
        query = query.filter(Signal.id.in_(signal_ids))
    elif not force:
        query = query.filter(Signal.annotation.is_(None))
    return query.order_by(Signal.confidence.desc(), Signal.ticker.asc()).limit(cap).all()


def run_once(
    db: Session,
    user_id: int,
    signal_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict:
    """Annotate a batch of signals. Returns a summary suitable for the API."""
    provider = resolve_provider(db, user_id)
    if provider is None:
        raise GroqError(
            "No Groq API key configured. Add GROQ_API_KEY (or set it in Settings) "
            "to enable the research agent."
        )

    settings = get_settings()
    signals = select_signals(db, signal_ids=signal_ids, limit=limit, force=force)
    annotated: list[dict] = []
    errors: list[dict] = []

    for index, signal in enumerate(signals):
        if index and settings.llm_research_pause_seconds > 0:
            # Spread the batch out: Groq's free plan is capped on tokens/minute.
            time.sleep(settings.llm_research_pause_seconds)
        try:
            annotation = annotate_signal(db, signal, provider)
        except GroqError as exc:
            logger.warning("research agent failed for %s: %s", signal.ticker, exc)
            errors.append({"id": signal.id, "ticker": signal.ticker, "error": str(exc)})
            continue
        signal.annotation = annotation
        db.add(signal)
        annotated.append(
            {
                "id": signal.id,
                "ticker": signal.ticker,
                "sentiment": annotation["sentiment"],
                "risk_flags": annotation["risk_flags"],
                "confidence_delta": annotation["confidence_delta"],
                "adjusted_confidence": annotation["adjusted_confidence"],
            }
        )
        db.commit()  # commit per signal so a later failure keeps earlier work

    return {
        "model": provider.model,
        "requested": len(signals),
        "annotated": len(annotated),
        "failed": len(errors),
        "results": annotated,
        "errors": errors[:5],
        "max_confidence_delta": settings.llm_max_confidence_delta,
    }


# ---------------------------------------------------------------------------
# Background runner (mirrors services/refresh.py)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def start_run(
    session_factory,
    user_id: int,
    signal_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> bool:
    """Start a background annotation pass. False if one is already running."""
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
        _state["started_at"] = datetime.utcnow()
        _state["finished_at"] = None
        _state["result"] = None
        _state["error"] = None

    def worker() -> None:
        try:
            db = session_factory()
            try:
                result = run_once(
                    db, user_id, signal_ids=signal_ids, limit=limit, force=force
                )
            finally:
                db.close()
            with _lock:
                _state["result"] = result
        except Exception as exc:  # pragma: no cover - defensive
            with _lock:
                _state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.utcnow()

    threading.Thread(target=worker, daemon=True).start()
    return True


def clear_annotations(db: Session) -> int:
    rows = db.query(Signal).filter(Signal.annotation.isnot(None)).all()
    for row in rows:
        row.annotation = None
        db.add(row)
    db.commit()
    return len(rows)
