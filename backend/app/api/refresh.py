"""On-demand data refresh endpoints (for the UI 'Refresh data' button)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..database import SessionLocal
from ..models import User
from ..services import refresh as refresh_service
from .deps import get_current_admin

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("")
def trigger_refresh(user: User = Depends(get_current_admin)) -> dict:
    """Kick off a background data pull + signal regeneration."""
    started = refresh_service.start_refresh(SessionLocal, user.id)
    state = refresh_service.get_state()
    return {"started": started, "running": state["running"], "error": state["error"]}


@router.get("/status")
def refresh_status(user: User = Depends(get_current_admin)) -> dict:
    """Current refresh state: running flag, result, or error."""
    return refresh_service.get_state()


@router.get("/sources")
def probe_sources(
    ticker: str = Query(default="AAPL"),
    user: User = Depends(get_current_admin),
) -> dict:
    """Probe every price source for daily and 4-hour candles.

    Answers "why is my 4-hour data unavailable?" without reading container logs:
    each source is called for one symbol and reports its status, row count, timing
    and the exact error when it fails.
    """
    return refresh_service.probe_sources(SessionLocal, user.id, ticker)
