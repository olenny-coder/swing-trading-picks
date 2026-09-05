"""On-demand data refresh endpoints (for the UI 'Refresh data' button)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..database import SessionLocal
from ..models import User
from ..services import refresh as refresh_service
from .deps import get_current_user

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("")
def trigger_refresh(user: User = Depends(get_current_user)) -> dict:
    """Kick off a background data pull + signal regeneration."""
    started = refresh_service.start_refresh(SessionLocal, user.id)
    state = refresh_service.get_state()
    return {"started": started, "running": state["running"], "error": state["error"]}


@router.get("/status")
def refresh_status(user: User = Depends(get_current_user)) -> dict:
    """Current refresh state: running flag, result, or error."""
    return refresh_service.get_state()
