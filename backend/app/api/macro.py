"""Macro dashboard endpoints: regime, economic calendar, earnings, sector heatmap."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EarningsEvent, MacroEvent, MacroSnapshot
from ..schemas import (
    EarningsEventOut,
    MacroDashboardOut,
    MacroEventOut,
    MacroSnapshotOut,
)

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/dashboard", response_model=MacroDashboardOut)
def dashboard(db: Session = Depends(get_db)) -> MacroDashboardOut:
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
    )
