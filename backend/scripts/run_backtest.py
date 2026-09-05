"""Backtesting CLI.

Replays the signal engine across historical bars, simulates stop/target exits,
and writes a JSON + Markdown performance report.

Examples:
    python scripts/run_backtest.py --years 2 --strategy all
    python scripts/run_backtest.py --years 5 --tickers AAPL MSFT NVDA --strategy BUY_DOJI_REVERSAL
    python scripts/run_backtest.py --years 10 --holding-days 15
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.backtest import run_backtest  # noqa: E402
from app.core.constants import SIGNAL_TYPES  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.providers.registry import resolve_macro_provider, resolve_market_provider  # noqa: E402
from app.services import credentials as creds_svc  # noqa: E402
from app.services.data_service import load_bars, resolve_universe  # noqa: E402
from app.services.macro_service import build_signal_context  # noqa: E402

MIN_BARS = 60


def _to_markdown(report: dict) -> str:
    lines = [
        "# Backtest Report",
        "",
        f"- Generated: {report['generated']}",
        f"- Period: {report['start']} -> {report['end']}",
        "",
        "| Strategy | Trades | Win rate | Avg return | Max DD | Profit factor | Sharpe | Avg hold |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for strat, m in report["strategies"].items():
        pf = m["profit_factor"]
        pf_s = "inf" if pf >= 999 else f"{pf:.2f}"
        lines.append(
            f"| {strat} | {m['trades']} | {m['win_rate']:.1f}% | {m['avg_return_pct']:.2f}% "
            f"| {m['max_drawdown_pct']:.1f}% | {pf_s} | {m['sharpe']:.2f} | {m['avg_holding_days']:.1f}d |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run event-aware strategy backtests.")
    parser.add_argument("--years", type=int, default=2, help="History length in years")
    parser.add_argument("--tickers", nargs="*", default=None, help="Optional ticker subset")
    parser.add_argument("--strategy", default="all", choices=["all"] + list(SIGNAL_TYPES))
    parser.add_argument("--holding-days", type=int, default=10)
    parser.add_argument("--out", default="reports/backtest", help="Output path prefix")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        creds = creds_svc.resolve_credentials(db, None)
        market = resolve_market_provider(creds)
        macro = resolve_macro_provider(creds)

        end = date.today()
        start = end - timedelta(days=365 * args.years)

        metas = resolve_universe(market)
        if args.tickers:
            wanted = set(t.upper() for t in args.tickers)
            metas = [m for m in metas if m.ticker in wanted]

        names = {m.ticker: m.name for m in metas}
        sectors = {m.ticker: m.sector for m in metas}

        bars_by_ticker: dict[str, list] = {}
        for m in metas:
            bars = load_bars(db, m.ticker, start, end)
            if len(bars) < MIN_BARS:
                bars = market.get_daily_bars(m.ticker, start, end)
            if len(bars) >= MIN_BARS:
                bars_by_ticker[m.ticker] = bars

        ctx = build_signal_context(db, end, {}, allow_earnings_plays=False)
        strategies = SIGNAL_TYPES if args.strategy == "all" else [args.strategy]

        report = {
            "generated": str(date.today()),
            "start": str(start),
            "end": str(end),
            "strategies": {},
        }
        trades_out: dict[str, list] = {}
        for strat in strategies:
            trades, metrics = run_backtest(bars_by_ticker, names, sectors, strat, args.holding_days, ctx)
            report["strategies"][strat] = metrics
            trades_out[strat] = [t.__dict__ for t in trades]

        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump({"metrics": report, "trades": trades_out}, f, indent=2, default=str)
        md = _to_markdown(report)
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(md)

        print(md)
        print(f"Wrote {args.out}.json and {args.out}.md")
    finally:
        db.close()


if __name__ == "__main__":
    main()
