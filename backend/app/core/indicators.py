"""Technical indicator implementations.

Pure-Python and dependency-light so they are trivially unit-testable and work
identically in the demo and production paths. All functions return lists aligned
with their inputs, using ``None`` for the warm-up window (mirroring how the
values are consumed by the signal engine).
"""
from __future__ import annotations

from collections import deque


def sma(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = []
    window: deque[float] = deque()
    total = 0.0
    for i, v in enumerate(values):
        window.append(v)
        total += v
        if len(window) > period:
            total -= window.popleft()
        out.append(total / period if len(window) == period else None)
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return ``(macd_line, signal_line, histogram)`` lists."""
    n = len(closes)
    macd_line: list[float | None] = [None] * n
    signal_line: list[float | None] = [None] * n
    histogram: list[float | None] = [None] * n

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]  # type: ignore[operator]

    # Signal line = EMA over the defined macd values.
    valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    if len(valid) >= signal:
        vals = [v for _, v in valid]
        ema_sig = ema(vals, signal)
        for (idx, _), s in zip(valid, ema_sig):
            if s is not None:
                signal_line[idx] = s
                histogram[idx] = macd_line[idx] - s  # type: ignore[operator]

    return macd_line, signal_line, histogram


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_value(avg_gain, avg_loss)

    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    out[0] = highs[0] - lows[0]
    for i in range(1, n):
        out[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    tr = true_ranges(highs, lows, closes)
    prev = sum(t for t in tr[1 : period + 1] if t is not None) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + tr[i]) / period  # type: ignore[operator]
        out[i] = prev
    return out


def is_doji(
    open_: float,
    high: float,
    low: float,
    close: float,
    body_pct: float = 0.10,
    shadow_pct: float = 0.20,
) -> bool:
    """True when the candle is a textbook doji.

    - body <= 10% of the full range
    - both upper and lower shadows >= 20% of the range
    """
    rng = high - low
    if rng <= 0:
        return False
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    return body <= rng * body_pct and upper >= rng * shadow_pct and lower >= rng * shadow_pct


def rolling_max(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            out.append(None)
        else:
            out.append(max(values[i - window + 1 : i + 1]))
    return out


def rolling_min(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            out.append(None)
        else:
            out.append(min(values[i - window + 1 : i + 1]))
    return out


def support_resistance(
    highs: list[float], lows: list[float], closes: list[float], lookback: int = 20
) -> tuple[float | None, float | None]:
    """Nearest support/resistance from a trailing window of swing highs/lows."""
    if not closes:
        return None, None
    n = len(closes)
    lo = max(0, n - lookback)
    resistance = max(highs[lo:n]) if highs[lo:n] else None
    support = min(lows[lo:n]) if lows[lo:n] else None
    return support, resistance


def crossed_above(a: list[float | None], b: list[float | None], within: int = 3) -> bool:
    """True if series ``a`` crossed above series ``b`` within the last
    ``within`` bars (inclusive)."""
    n = len(a)
    for i in range(max(1, n - within), n):
        if a[i] is None or b[i] is None or a[i - 1] is None or b[i - 1] is None:
            continue
        if a[i - 1] <= b[i - 1] and a[i] > b[i]:  # type: ignore[operator]
            return True
    return False


def crossed_below(a: list[float | None], b: list[float | None], within: int = 3) -> bool:
    n = len(a)
    for i in range(max(1, n - within), n):
        if a[i] is None or b[i] is None or a[i - 1] is None or b[i - 1] is None:
            continue
        if a[i - 1] >= b[i - 1] and a[i] < b[i]:  # type: ignore[operator]
            return True
    return False
