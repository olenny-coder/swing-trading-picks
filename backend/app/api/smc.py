"""SMC analysis endpoints.

The app's strategy, in two calls:

- ``GET /api/smc/scan`` — analyse the universe and return the ranked verdicts.
  Each result carries the exact plain-text block from the brief in its ``text``
  field, alongside structured fields the UI uses to draw the chart.
- ``GET /api/smc/{symbol}`` — one symbol's verdict plus its daily and 4-hour
  candles.

Both are public reads: visitors who are not signed in get the synthetic DEMO
dataset, the real rows go to a signed-in user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..providers.registry import resolve_market_provider
from ..schemas import SmcScanOut, SmcSymbolOut
from ..services import demo_service, smc_service
from ..services.credentials import resolve_credentials
from .deps import get_optional_user

router = APIRouter(prefix="/smc", tags=["smc"])


def _credentials(db: Session, user: User | None) -> dict:
    if user is not None:
        return resolve_credentials(db, user.id)
    primary = db.query(User).order_by(User.id.asc()).first()
    return resolve_credentials(db, primary.id if primary else None)


@router.get("/scan", response_model=SmcScanOut)
def scan(
    limit: int | None = Query(default=None, ge=1, le=50),
    refresh: bool = Query(default=False, description="Bypass the short-lived cache"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> SmcScanOut:
    """Analyse the universe with the 1D/4H strategy."""
    if user is None:
        return SmcScanOut.model_validate(demo_service.smc_scan_payload(limit))
    market = resolve_market_provider(_credentials(db, user))
    return SmcScanOut.model_validate(smc_service.scan(db, market, limit=limit, refresh=refresh))


@router.get("/{symbol}", response_model=SmcSymbolOut)
def symbol(
    symbol: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> SmcSymbolOut:
    """The plain-text verdict for one symbol, plus the candles behind it."""
    code = symbol.upper().strip()
    if user is None:
        payload = demo_service.smc_symbol_payload(code)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="Symbol not found in the demo dataset. Sign in to analyse live data.",
            )
        return SmcSymbolOut.model_validate(payload)

    market = resolve_market_provider(_credentials(db, user))
    payload = smc_service.drilldown(db, market, code)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No stored candles for {code}. It may not be in the universe, or an admin "
                "data refresh may be needed."
            ),
        )
    return SmcSymbolOut.model_validate(payload)
