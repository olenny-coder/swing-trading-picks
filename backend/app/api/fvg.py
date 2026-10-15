"""FVG screener endpoints.

Deliberately two calls, matching the two steps of the workflow:

- ``GET /api/fvg/shortlist`` — step 1, the ranked screen. It returns **no chart
  annotations at all**.
- ``GET /api/fvg/{ticker}`` — step 2, the drill-down. The client only calls this
  once the user has picked a ticker, which is what keeps annotated charts off the
  screen until then.

Both are public reads. Visitors who are not signed in get the synthetic DEMO
dataset; the real rows are served to a signed-in user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..providers.registry import resolve_market_provider
from ..schemas import FvgDrilldownOut, FvgShortlistOut
from ..services import demo_service, fvg_service
from ..services.credentials import resolve_credentials
from .deps import get_optional_user

router = APIRouter(prefix="/fvg", tags=["fvg"])


def _credentials(db: Session, user: User | None) -> dict:
    """Credentials for the read.

    A signed-in caller uses their own keys; a visitor uses the primary (admin)
    account's, so the public screener still works on a hosted deployment.
    """
    if user is not None:
        return resolve_credentials(db, user.id)
    primary = db.query(User).order_by(User.id.asc()).first()
    return resolve_credentials(db, primary.id if primary else None)


@router.get("/shortlist", response_model=FvgShortlistOut)
def shortlist(
    timeframe: str | None = Query(default=None, description="DAILY | WEEKLY | MONTHLY"),
    limit: int | None = Query(default=None, ge=1, le=50),
    refresh: bool = Query(default=False, description="Bypass the short-lived cache"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> FvgShortlistOut:
    """Step 1 — screen and shortlist. No chart annotations are returned here."""
    if user is None:
        return FvgShortlistOut.model_validate(
            demo_service.fvg_shortlist_payload(timeframe, limit)
        )
    market = resolve_market_provider(_credentials(db, user))
    return FvgShortlistOut.model_validate(
        fvg_service.scan(db, market, timeframe=timeframe, limit=limit, refresh=refresh)
    )


@router.get("/{ticker}", response_model=FvgDrilldownOut)
def drilldown(
    ticker: str,
    timeframe: str | None = Query(default=None, description="DAILY | WEEKLY | MONTHLY"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> FvgDrilldownOut:
    """Step 2 — chart annotations and the trade card for one selected ticker."""
    symbol = ticker.upper().strip()
    if user is None:
        payload = demo_service.fvg_detail_payload(symbol, timeframe)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="Ticker not found in the demo screener. Sign in to screen live data.",
            )
        return FvgDrilldownOut.model_validate(payload)

    market = resolve_market_provider(_credentials(db, user))
    payload = fvg_service.drilldown(db, market, symbol, timeframe=timeframe)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No stored candles for {symbol} on this interval. It may not be in the "
                "universe, or a data refresh may be needed."
            ),
        )
    return FvgDrilldownOut.model_validate(payload)
