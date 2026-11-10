"""Shared FastAPI dependencies: database session, current user, ownership guards."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, User, as_utc
from ..utils.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, payload.get("sub", ""))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Lightweight activity tracking (only persisted when it changes materially).
    now = datetime.now(timezone.utc)
    last = as_utc(user.last_active_at)
    if last is None or (now - last).total_seconds() > 300:
        user.last_active_at = now
        db.commit()
    return user


def get_owned_course(course_id: str, db: Session, user: User) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def course_dependency(course_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Course:
    return get_owned_course(course_id, db, user)
