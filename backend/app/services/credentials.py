"""Credential resolution and management.

- Environment variables are the *fallback* for single-user / initial setups.
- UI-provided credentials are stored encrypted (Fernet) in the DB and take
  precedence over the environment.
- Decrypted secrets only ever exist server-side; the REST layer exposes
  masked values via ``schemas.CredentialOut``.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import security
from ..models import ApiCredential
from ..schemas import CredentialOut, ProviderStatus

PROVIDERS = ("alpaca", "finnhub", "polygon", "fred")


def _env_credentials() -> dict:
    s = get_settings()
    creds: dict = {}
    if s.alpaca_api_key:
        creds["alpaca"] = {
            "api_key": s.alpaca_api_key,
            "secret_key": s.alpaca_secret_key,
            "is_paper": s.alpaca_paper,
            "data_feed": s.alpaca_data_feed,
        }
    if s.finnhub_api_key:
        creds["finnhub"] = {"api_key": s.finnhub_api_key}
    if s.polygon_api_key:
        creds["polygon"] = {"api_key": s.polygon_api_key}
    if s.fred_api_key:
        creds["fred"] = {"api_key": s.fred_api_key}
    return creds


def resolve_credentials(db: Session, user_id: int | None = None) -> dict:
    """Return decrypted credentials, DB (UI) values overriding env fallbacks."""
    creds = _env_credentials()
    if user_id is None:
        return creds

    rows = db.query(ApiCredential).filter(ApiCredential.user_id == user_id).all()
    for row in rows:
        try:
            api_key = security.decrypt_secret(row.key_encrypted)
        except ValueError:
            continue  # SECRET_KEY rotated -> treat as absent

        entry: dict = {"api_key": api_key}
        if row.secret_encrypted:
            try:
                entry["secret_key"] = security.decrypt_secret(row.secret_encrypted)
            except ValueError:
                pass
        if row.provider == "alpaca":
            entry["is_paper"] = row.is_paper
            entry["data_feed"] = (row.extra or {}).get("data_feed", get_settings().alpaca_data_feed)
        if row.extra:
            for k, v in row.extra.items():
                entry.setdefault(k, v)
        creds[row.provider] = entry

    return creds


def upsert_credential(
    db: Session,
    user_id: int,
    provider: str,
    api_key: str,
    secret_key: str | None = None,
    is_paper: bool = True,
    extra: dict | None = None,
) -> ApiCredential:
    """Encrypt and store a provider credential (upsert by user+provider)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")

    row = (
        db.query(ApiCredential)
        .filter(ApiCredential.user_id == user_id, ApiCredential.provider == provider)
        .first()
    )
    if row is None:
        row = ApiCredential(user_id=user_id, provider=provider)
        db.add(row)

    row.key_encrypted = security.encrypt_secret(api_key)
    row.secret_encrypted = security.encrypt_secret(secret_key) if secret_key else None
    row.is_paper = is_paper if provider == "alpaca" else True
    row.extra = extra or {}
    db.commit()
    db.refresh(row)
    return row


def delete_credential(db: Session, user_id: int, provider: str) -> bool:
    row = (
        db.query(ApiCredential)
        .filter(ApiCredential.user_id == user_id, ApiCredential.provider == provider)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def masked_credentials(db: Session, user_id: int) -> list[CredentialOut]:
    rows = db.query(ApiCredential).filter(ApiCredential.user_id == user_id).all()
    out: list[CredentialOut] = []
    for row in rows:
        try:
            key = security.decrypt_secret(row.key_encrypted)
        except ValueError:
            key = ""
        secret = ""
        if row.secret_encrypted:
            try:
                secret = security.decrypt_secret(row.secret_encrypted)
            except ValueError:
                secret = ""
        out.append(
            CredentialOut(
                provider=row.provider,
                has_key=bool(key),
                key_masked=security.mask_key(key),
                secret_masked=security.mask_key(secret) if secret else None,
                is_paper=row.is_paper if row.provider == "alpaca" else None,
                updated_at=row.updated_at,
            )
        )
    return out


def provider_statuses(db: Session, user_id: int | None = None) -> list[ProviderStatus]:
    env = _env_credentials()
    db_map: dict[str, bool] = {}
    if user_id is not None:
        rows = db.query(ApiCredential).filter(ApiCredential.user_id == user_id).all()
        db_map = {r.provider: True for r in rows}

    out: list[ProviderStatus] = []
    for provider in PROVIDERS:
        in_db = db_map.get(provider, False)
        in_env = provider in env
        source = "database" if in_db else ("env" if in_env else "none")
        out.append(ProviderStatus(provider=provider, configured=in_db or in_env, source=source))
    return out
