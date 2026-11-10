"""Registration, login and anonymous sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User
from ..schemas import (
    AnonymousSessionCreate,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from ..utils.auth import (
    create_access_token,
    generate_user_id,
    hash_password,
    verify_password,
)
from ..utils.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_for(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower().strip()
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists. Try logging in.",
        )

    settings = get_settings()
    user = User(
        id=generate_user_id(),
        email=email,
        name=payload.name.strip() or "Student",
        university=(payload.university or "").strip() or None,
        password_hash=hash_password(payload.password),
        is_anonymous=False,
        daily_study_minutes=payload.daily_study_minutes or settings.default_daily_study_minutes,
        last_active_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_active_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/anonymous-session", response_model=Token, status_code=status.HTTP_201_CREATED)
def anonymous_session(
    payload: AnonymousSessionCreate | None = None,
    db: Session = Depends(get_db),
) -> Token:
    """Start studying without an account. The token is the only credential."""
    settings = get_settings()
    payload = payload or AnonymousSessionCreate()
    user = User(
        id=generate_user_id(),
        email=None,
        name=(payload.name or "Guest student").strip()[:120] or "Guest student",
        university=(payload.university or "").strip() or None,
        is_anonymous=True,
        daily_study_minutes=payload.daily_study_minutes or settings.default_daily_study_minutes,
        last_active_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.get("/me", response_model=UserResponse)
def read_me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if payload.name is not None:
        user.name = payload.name.strip()[:120] or user.name
    if payload.university is not None:
        user.university = payload.university.strip()[:200] or None
    if payload.daily_study_minutes is not None:
        user.daily_study_minutes = payload.daily_study_minutes
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)
