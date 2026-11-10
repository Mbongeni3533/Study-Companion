"""Pre-assessment (the thinking check) for new students."""

from __future__ import annotations

import json

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AssessmentOverview, AssessmentResult, AssessmentSubmit, UserResponse
from ..services.thinking import assess, content, guide, public_questions
from ..utils.deps import get_current_user

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("", response_model=AssessmentOverview)
def get_assessment(user: User = Depends(get_current_user)) -> AssessmentOverview:
    data = content()
    profile = None
    if user.thinking_scores:
        try:
            profile = json.loads(user.thinking_scores)
        except (ValueError, TypeError):
            profile = None
    return AssessmentOverview(
        intro=data["intro"],
        questions=public_questions(),
        profile=profile,
    )


@router.post("/submit", response_model=AssessmentResult)
def submit_assessment(
    payload: AssessmentSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssessmentResult:
    if not payload.answers:
        raise HTTPException(status_code=422, detail="Please answer the questions first.")
    profile = assess(payload.answers)
    user.thinking_level = profile["level"]
    user.thinking_scores = json.dumps(profile)
    user.assessment_completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return AssessmentResult(profile=profile, user=UserResponse.model_validate(user))
