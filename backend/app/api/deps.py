"""Shared FastAPI dependencies (auth, db)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..core import security
from ..database import get_db
from ..models import User

# auto_error=False so the public read endpoints can treat "no token" as an
# anonymous visitor instead of returning 401.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        username = payload.get("sub")
    except Exception:
        raise credentials_error
    if not username:
        raise credentials_error
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_error
    return user


def get_optional_user(
    token: str | None = Depends(optional_oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    """Return the signed-in user, or ``None`` for an anonymous visitor.

    Used by the public read endpoints: anonymous callers get the synthetic DEMO
    dataset, signed-in admins get the real one. An invalid/expired token is
    treated as anonymous rather than an error, so a logged-out browser still
    sees the demo instead of a 401.
    """
    if not token:
        return None
    try:
        payload = security.decode_access_token(token)
        username = payload.get("sub")
    except Exception:
        return None
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None
    return user
