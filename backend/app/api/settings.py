"""Settings / API key management endpoints.

Keys are encrypted at rest (Fernet) in the DB, masked in responses, and never
sent back to the frontend in plaintext. Environment variables act as the
fallback when no UI credentials are set.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User
from ..providers.finnhub_provider import FinnhubMacroProvider
from ..providers.fred_provider import FredMacroProvider
from ..providers.polygon_provider import PolygonMarketDataProvider
from ..providers.registry import resolve_market_provider
from ..schemas import (
    CredentialOut,
    CredentialUpsert,
    SettingsResponse,
    TestConnectionRequest,
    TestConnectionResult,
)
from ..services.credentials import (
    masked_credentials,
    provider_statuses,
    resolve_credentials,
    upsert_credential,
    delete_credential,
)
from .deps import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SettingsResponse:
    masked = masked_credentials(db, user.id)
    alpaca = next((c for c in masked if c.provider == "alpaca"), None)
    settings = get_settings()
    return SettingsResponse(
        alpaca=alpaca,
        providers=provider_statuses(db, user.id),
        data_provider=settings.data_provider,
        environment_variables_present=bool(settings.alpaca_api_key),
    )


@router.put("/credentials/{provider}", response_model=CredentialOut)
def save_credential(
    provider: str,
    body: CredentialUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CredentialOut:
    if provider != body.provider:
        raise HTTPException(status_code=400, detail="Provider in path and body must match")
    if provider not in ("alpaca", "finnhub", "polygon", "fred"):
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    if provider == "alpaca" and not body.secret_key:
        raise HTTPException(status_code=422, detail="Alpaca requires an API secret key")

    upsert_credential(
        db,
        user.id,
        provider,
        body.api_key,
        secret_key=body.secret_key,
        is_paper=body.is_paper,
        extra=body.extra,
    )
    # Re-read masked representation (plaintext never leaves this endpoint).
    saved = next((c for c in masked_credentials(db, user.id) if c.provider == provider), None)
    return saved


@router.delete("/credentials/{provider}", status_code=204)
def remove_credential(
    provider: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    delete_credential(db, user.id, provider)


@router.post("/test", response_model=TestConnectionResult)
def test_connection(
    body: TestConnectionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TestConnectionResult:
    creds = resolve_credentials(db, user.id)
    provider = body.provider

    if provider == "alpaca":
        if not (creds.get("alpaca") or {}).get("api_key"):
            return TestConnectionResult(provider=provider, ok=False, message="No Alpaca credentials configured")
        ok, msg, detail = resolve_market_provider(creds).test_connection()
    elif provider == "polygon":
        key = (creds.get("polygon") or {}).get("api_key")
        if not key:
            return TestConnectionResult(provider=provider, ok=False, message="No Polygon API key configured")
        ok, msg, detail = PolygonMarketDataProvider(key).test_connection()
    elif provider == "finnhub":
        key = (creds.get("finnhub") or {}).get("api_key")
        if not key:
            return TestConnectionResult(provider=provider, ok=False, message="No Finnhub API key configured")
        ok, msg, detail = FinnhubMacroProvider(key).test_connection()
    elif provider == "fred":
        key = (creds.get("fred") or {}).get("api_key")
        if not key:
            return TestConnectionResult(provider=provider, ok=False, message="No FRED API key configured")
        ok, msg, detail = FredMacroProvider(key).test_connection()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    return TestConnectionResult(provider=provider, ok=ok, message=msg, detail=detail)
