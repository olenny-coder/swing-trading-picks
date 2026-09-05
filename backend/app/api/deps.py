"""Shared FastAPI dependencies (auth, db)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..core import security
from ..database import get_db
from ..models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


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
