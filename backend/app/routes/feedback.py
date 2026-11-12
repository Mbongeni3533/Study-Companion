"""Student feedback collection for the beta.

Feedback is persisted in the database and also written to the application log so
the operator can see it in the running server output. Retrieval is protected by
the same admin key as the invite-code endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Feedback, User
from ..schemas import FeedbackCreate, FeedbackResponse
from ..utils.deps import get_current_user
from .admin import _require_admin

logger = logging.getLogger("study_companion.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    if payload.course_id is not None:
        course = db.get(Course, payload.course_id)
        if course is None or course.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    feedback = Feedback(
        user_id=user.id,
        course_id=payload.course_id,
        rating=payload.rating,
        category=payload.category.strip() or "general",
        message=payload.message.strip(),
        page=payload.page,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    logger.info(
        "student_feedback user=%s email=%s rating=%s category=%s page=%s: %s",
        user.id,
        user.email,
        feedback.rating,
        feedback.category,
        feedback.page,
        feedback.message,
    )
    return FeedbackResponse.model_validate(feedback)


@router.get("", response_model=list[FeedbackResponse])
def list_feedback(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[FeedbackResponse]:
    rows = db.scalars(
        select(Feedback).order_by(Feedback.created_at.desc()).offset(offset).limit(limit)
    ).all()
    result: list[FeedbackResponse] = []
    for row in rows:
        item = FeedbackResponse.model_validate(row)
        if row.user is not None:
            item.user_email = row.user.email
            item.user_name = row.user.name
        result.append(item)
    return result
