"""Event-aware backtesting engine.

Replays the signal engine across historical bars, simulates trades with
stop/target exits over a fixed maximum holding period, and computes standard
performance metrics (win rate, avg return, max drawdown, profit factor, Sharpe,
avg holding days).

Note: for very large universes/periods this is compute-bound (it re-evaluates
indicators on a rolling window per bar). The CLI defaults to a bounded horizon
and supports ``--tickers`` to subset the universe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .base_types import SignalContext
from .signal_engine import MIN_BARS, SignalDraft, analyze_ticker


@dataclass
class TradeResult:
    ticker: str
    signal_date: date
    type: str
    entry: float
    exit: float
    exit_date: date | None
    pnl_pct: float
    holding_days: int
    hit_target: bool
    hit_stop: bool


def simulate_trade(draft: SignalDraft, bars: list, signal_index: int, holding_days: int = 10) -> TradeResult | None:
    """Simulate a single trade entered at the bar after the signal bar."""
    if signal_index + 1 >= len(bars):
        return None
    entry_bar = bars[signal_index + 1]
    entry = entry_bar.open or entry_bar.close

    is_put = draft.type == "PUT"
    target, stop = draft.target, draft.stop

    for j in range(signal_index + 1, min(signal_index + 1 + holding_days, len(bars))):
        b = bars[j]
        if is_put:
            if b.low <= target:
                return _result(draft, entry, target, b.date, j - signal_index, True, False, is_put)
            if b.high >= stop:
                return _result(draft, entry, stop, b.date, j - signal_index, False, True, is_put)
        else:
            if b.low <= stop:
                return _result(draft, entry, stop, b.date, j - signal_index, False, True, is_put)
            if b.high >= target:
                return _result(draft, entry, target, b.date, j - signal_index, True, False, is_put)

    last = bars[min(signal_index + holding_days, len(bars) - 1)]
    return _result(draft, entry, last.close, last.date, holding_days, False, False, is_put)


def _result(draft, entry, exit_, exit_date, holding, hit_target, hit_stop, is_put) -> TradeResult:
    pnl = (entry - exit_) / entry if is_put else (exit_ - entry) / entry
    return TradeResult(
        ticker=draft.ticker,
        signal_date=date.min,  # overwritten by the caller with the signal bar date
        type=draft.type,
        entry=round(entry, 4),
        exit=round(exit_, 4),
        exit_date=exit_date,
        pnl_pct=round(pnl * 100.0, 4),
        holding_days=holding,
        hit_target=hit_target,
        hit_stop=hit_stop,
    )


def run_backtest(
    bars_by_ticker: dict[str, list],
    names: dict[str, str],
    sectors: dict[str, str],
    strategy: str,
    holding_days: int = 10,
    ctx: SignalContext | None = None,
) -> tuple[list[TradeResult], dict]:
    ctx = ctx or SignalContext()
    trades: list[TradeResult] = []
    for ticker, bars in bars_by_ticker.items():
        n = len(bars)
        for i in range(MIN_BARS, n):
            drafts = analyze_ticker(ticker, names.get(ticker, ticker), sectors.get(ticker), bars[: i + 1], ctx)
            for d in drafts:
                if strategy != "all" and d.type != strategy:
                    continue
                result = simulate_trade(d, bars, i, holding_days)
                if result is not None:
                    result.signal_date = bars[i].date
                    trades.append(result)
    return trades, compute_metrics(trades)


def compute_metrics(trades: list[TradeResult]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "avg_holding_days": 0.0,
        }
    wins = [t.pnl_pct for t in trades if t.pnl_pct > 0]
    losses = [t.pnl_pct for t in trades if t.pnl_pct <= 0]
    win_rate = len(wins) / len(trades) * 100.0
    avg_return = sum(t.pnl_pct for t in trades) / len(trades)

    # Profit factor
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    # Sharpe (annualized) from per-trade returns.
    if len(trades) > 1:
        mean = sum(t.pnl_pct for t in trades) / len(trades)
        var = sum((t.pnl_pct - mean) ** 2 for t in trades) / (len(trades) - 1)
        sd = math.sqrt(var)
        sharpe = (mean / sd) * math.sqrt(252.0) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown from a compounded equity curve.
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in trades:
        equity *= 1.0 + t.pnl_pct / 100.0
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100.0
        max_dd = max(max_dd, dd)

    avg_holding = sum(t.holding_days for t in trades) / len(trades)

    return {
        "trades": len(trades),
        "win_rate": round(win_rate, 2),
        "avg_return_pct": round(avg_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
        "sharpe": round(sharpe, 2),
        "avg_holding_days": round(avg_holding, 2),
    }
