"""Backtesting endpoint (bounded; the CLI runs full historical reports)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.backtest import run_backtest
from ..core.base_types import SignalContext
from ..core.constants import SIGNAL_TYPES
from ..core.signal_engine import MIN_BARS
from ..database import get_db
from ..models import BacktestRun, User
from ..schemas import BacktestMetrics, BacktestRequest, BacktestResultOut
from ..services.data_service import load_bars, resolve_universe
from ..services.macro_service import build_signal_context
from ..providers.registry import resolve_macro_provider, resolve_market_provider
from ..services.credentials import resolve_credentials
from .deps import get_current_user

router = APIRouter(prefix="/backtest", tags=["backtest"])

_DEFAULT_TICKER_SAMPLE = 30


@router.post("", response_model=BacktestResultOut)
def run(
    req: BacktestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestResultOut:
    creds = resolve_credentials(db, user.id)
    market = resolve_market_provider(creds)
    macro = resolve_macro_provider(creds)

    end = req.end_date or date.today()
    start = req.start_date or (end.replace(year=end.year - 1))

    metas = resolve_universe(market)
    if req.tickers:
        metas = [m for m in metas if m.ticker in set(req.tickers)]
    metas = metas[:_DEFAULT_TICKER_SAMPLE]

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

    strategies = SIGNAL_TYPES if req.strategy == "all" else [req.strategy]
    metrics_out: list[BacktestMetrics] = []
    run_id: int | None = None

    for strat in strategies:
        trades, metrics = run_backtest(
            bars_by_ticker, names, sectors, strat, holding_days=req.holding_days, ctx=ctx
        )
        metrics_out.append(
            BacktestMetrics(strategy=strat, start_date=start, end_date=end, **metrics)
        )
        db.add(
            BacktestRun(
                strategy=strat,
                start_date=start,
                end_date=end,
                metrics=metrics,
            )
        )
    db.commit()

    return BacktestResultOut(run_id=run_id, strategies=metrics_out)
