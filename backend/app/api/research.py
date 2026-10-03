"""LLM research-agent endpoints.

- ``GET  /api/research/status`` — public: is the agent configured, how many
  signals are annotated, and what the last pass did.
- ``POST /api/research/run``    — admin: annotate signals in a background thread
  (Groq free-tier calls are sequential, so this can take a minute).
- ``DELETE /api/research``      — admin: clear every annotation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import ApiCredential, Signal, User
from ..providers.groq_provider import GroqError
from ..schemas import ResearchRequest, ResearchStatusResponse
from ..services import research_service
from .deps import get_current_admin

router = APIRouter(prefix="/research", tags=["research"])


def _is_configured(db: Session) -> bool:
    settings = get_settings()
    if settings.groq_api_key:
        return True
    return (
        db.query(ApiCredential).filter(ApiCredential.provider == "groq").count() > 0
    )


@router.get("/status", response_model=ResearchStatusResponse)
def research_status(db: Session = Depends(get_db)) -> ResearchStatusResponse:
    settings = get_settings()
    state = research_service.get_state()
    total = db.query(Signal).count()
    annotated = db.query(Signal).filter(Signal.annotation.isnot(None)).count()
    return ResearchStatusResponse(
        enabled=settings.llm_research_enabled,
        configured=_is_configured(db),
        model=settings.groq_model,
        running=bool(state.get("running")),
        total_signals=total,
        annotated_signals=annotated,
        pending_signals=max(0, total - annotated),
        max_confidence_delta=settings.llm_max_confidence_delta,
        max_signals_per_run=settings.llm_research_max_signals,
        sentiments=list(research_service.SENTIMENTS),
        risk_flags=list(research_service.RISK_FLAGS),
        started_at=state.get("started_at"),
        finished_at=state.get("finished_at"),
        last_result=state.get("result"),
        error=state.get("error"),
    )


@router.post("/run", response_model=ResearchStatusResponse)
def run_research(
    body: ResearchRequest | None = None,
    user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ResearchStatusResponse:
    settings = get_settings()
    if not settings.llm_research_enabled:
        raise HTTPException(status_code=409, detail="The research agent is disabled")
    if not _is_configured(db):
        raise HTTPException(
            status_code=409,
            detail=(
                "No Groq API key configured. Set GROQ_API_KEY or add the key in "
                "Settings to enable the research agent."
            ),
        )

    req = body or ResearchRequest()
    started = research_service.start_run(
        SessionLocal,
        user.id,
        signal_ids=req.signal_ids,
        limit=req.limit,
        force=req.force,
    )
    if not started:
        raise HTTPException(status_code=409, detail="A research pass is already running")

    return research_status(db)


@router.post("/test")
def test_research(
    user: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> dict:
    """One tiny round-trip so the Settings page can verify the key."""
    provider = research_service.resolve_provider(db, user.id)
    if provider is None:
        raise HTTPException(status_code=409, detail="No Groq API key configured")
    try:
        ok, message, detail = provider.test_connection()
    except GroqError as exc:
        return {"ok": False, "message": str(exc), "detail": {}}
    return {"ok": ok, "message": message, "detail": detail}


@router.delete("", response_model=ResearchStatusResponse)
def clear_research(
    user: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> ResearchStatusResponse:
    research_service.clear_annotations(db)
    return research_status(db)
