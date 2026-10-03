"""Macro dashboard endpoints: regime, economic calendar, earnings, sector heatmap."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EarningsEvent, MacroEvent, MacroSnapshot, User
from ..schemas import (
    EarningsEventOut,
    MacroDashboardOut,
    MacroEventOut,
    MacroSnapshotOut,
)
from ..services import demo_service
from .deps import get_optional_user

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/dashboard", response_model=MacroDashboardOut)
def dashboard(
    db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)
) -> MacroDashboardOut:
    if user is None:
        # Anonymous visitors get the synthetic demo calendar, not the real one.
        return MacroDashboardOut.model_validate(demo_service.macro_payload())

    snap = db.query(MacroSnapshot).order_by(MacroSnapshot.date.desc()).first()
    now = datetime.utcnow()
    today = date.today()

    macro_events = (
        db.query(MacroEvent)
        .filter(MacroEvent.datetime >= now)
        .order_by(MacroEvent.datetime.asc())
        .limit(30)
        .all()
    )
    earnings = (
        db.query(EarningsEvent)
        .filter(EarningsEvent.report_date >= today)
        .order_by(EarningsEvent.report_date.asc())
        .limit(30)
        .all()
    )

    return MacroDashboardOut(
        snapshot=MacroSnapshotOut.model_validate(snap) if snap else None,
        macro_events=[MacroEventOut.model_validate(e) for e in macro_events],
        earnings=[EarningsEventOut.model_validate(e) for e in earnings],
        sector_heatmap=snap.sector_relative_strength if snap and snap.sector_relative_strength else {},
        demo=False,
    )
