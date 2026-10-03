"""User management (admin only).

The bootstrap account is the first administrator. Admins can add **authorized
users** — accounts that can sign in and see live signals — and can disable,
promote, demote or delete them.

Safety guards:
- a username must be unique (case-insensitive),
- you cannot delete your own account,
- the last **active administrator** can never be demoted, disabled or deleted,
  so an admin cannot lock everyone out of the management screens.

Guests who are not signed in never reach these endpoints and only ever see the
synthetic demo dataset (see ``services/demo_service.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core import security
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from .deps import get_current_admin

router = APIRouter(prefix="/users", tags=["users"])


def _active_admins(db: Session, exclude_id: int | None = None) -> int:
    query = db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True))
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return query.count()


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db), _: User = Depends(get_current_admin)
) -> list[User]:
    """Every account, oldest first."""
    return db.query(User).order_by(User.id.asc()).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """Add an authorized user who can sign in and see live data."""
    username = body.username.strip()
    existing = (
        db.query(User).filter(func.lower(User.username) == username.lower()).first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Username '{username}' is already taken")

    user = User(
        username=username,
        hashed_password=security.hash_password(body.password),
        is_active=True,
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    """Change a password, or activate/deactivate or promote/demote an account."""
    user = _get_user(db, user_id)

    losing_admin = (
        user.is_admin
        and user.is_active
        and (body.is_admin is False or body.is_active is False)
    )
    if losing_admin and _active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(
            status_code=409,
            detail="At least one active administrator must remain",
        )

    if body.password is not None:
        user.hashed_password = security.hash_password(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_admin is not None:
        user.is_admin = body.is_admin

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    """Remove an account (and its stored API credentials)."""
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")

    user = _get_user(db, user_id)
    if user.is_admin and user.is_active and _active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(
            status_code=409,
            detail="At least one active administrator must remain",
        )

    db.delete(user)
    db.commit()
