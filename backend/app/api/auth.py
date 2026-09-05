"""Authentication endpoints (single-user, JWT)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import security
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, Token, UserOut
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not security.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    return Token(access_token=security.create_access_token(user.username))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


def bootstrap_admin(db: Session) -> None:
    """Create the initial admin user on first run if none exists."""
    settings = get_settings()
    if db.query(User).count() == 0:
        user = User(
            username=settings.admin_username,
            hashed_password=security.hash_password(settings.admin_password),
            is_active=True,
        )
        db.add(user)
        db.commit()
