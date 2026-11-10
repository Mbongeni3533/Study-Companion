"""Study minutes, streaks and exam readiness."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, StudyLog, Task, TopicProgress, User
from ..schemas import CourseProgress, ProgressSummary, StudyLogCreate, StudyLogResponse
from ..serializers import (
    compute_streak,
    readiness_score,
    today_utc,
    topic_response,
)
from ..utils.deps import get_current_user, get_owned_course

router = APIRouter(prefix="/progress", tags=["progress"])


def _log_response(log: StudyLog) -> StudyLogResponse:
    return StudyLogResponse.model_validate(log)


def _minutes_total(db: Session, user_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(StudyLog.minutes), 0)).where(StudyLog.user_id == user_id)
    )
    return int(total or 0)


def _course_progress(db: Session, course: Course, user: User, logs: list[StudyLog]) -> CourseProgress:
    minutes = sum(log.minutes for log in logs if log.course_id == course.id)
    tasks = list(course.tasks)
    confidence = {
        row.topic_id: row.confidence
        for row in db.scalars(
            select(TopicProgress).where(TopicProgress.user_id == user.id)
        ).all()
    }
    topics = [
        topic_response(topic, confidence.get(topic.id, 0))
        for topic in sorted(course.topics, key=lambda t: t.order_index)
    ]
    streak_days = compute_streak(
        [log.created_at.date() for log in logs if log.course_id == course.id]
    )
    return CourseProgress(
        course_id=course.id,
        course_title=course.title,
        total_tasks=len(tasks),
        completed_tasks=sum(1 for t in tasks if t.status == "done"),
        minutes_studied=minutes,
        streak_days=streak_days,
        readiness_score=readiness_score(course),
        topics=topics,
    )


@router.get("/summary", response_model=ProgressSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProgressSummary:
    today = today_utc()
    week_start = today - timedelta(days=6)

    logs = list(
        db.scalars(
            select(StudyLog)
            .where(StudyLog.user_id == user.id)
            .order_by(StudyLog.created_at.desc())
            .limit(500)
        ).all()
    )

    minutes_today = sum(log.minutes for log in logs if log.created_at.date() == today)
    minutes_week = sum(log.minutes for log in logs if log.created_at.date() >= week_start)

    total_tasks = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .join(Course, Task.course_id == Course.id)
            .where(Course.user_id == user.id)
        )
        or 0
    )
    completed_tasks = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .join(Course, Task.course_id == Course.id)
            .where(Course.user_id == user.id, Task.status == "done")
        )
        or 0
    )

    courses = list(
        db.scalars(
            select(Course).where(Course.user_id == user.id).order_by(Course.created_at.desc())
        ).all()
    )

    return ProgressSummary(
        minutes_today=minutes_today,
        minutes_this_week=minutes_week,
        minutes_total=_minutes_total(db, user.id),
        tasks_completed=completed_tasks,
        tasks_open=max(0, total_tasks - completed_tasks),
        streak_days=compute_streak([log.created_at.date() for log in logs]),
        daily_goal_minutes=user.daily_study_minutes,
        courses=[_course_progress(db, course, user, logs) for course in courses],
        recent_logs=[_log_response(log) for log in logs[:10]],
    )


@router.get("/courses/{course_id}", response_model=CourseProgress)
def course_progress(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseProgress:
    course = get_owned_course(course_id, db, user)
    logs = list(
        db.scalars(
            select(StudyLog)
            .where(StudyLog.user_id == user.id, StudyLog.course_id == course.id)
            .order_by(StudyLog.created_at.desc())
        ).all()
    )
    return _course_progress(db, course, user, logs)


@router.post("/log", response_model=StudyLogResponse, status_code=201)
def log_study(
    payload: StudyLogCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StudyLogResponse:
    if payload.course_id:
        get_owned_course(payload.course_id, db, user)
    if payload.task_id:
        task = db.get(Task, payload.task_id)
        if task is None or task.course_id != payload.course_id:
            raise HTTPException(status_code=404, detail="Task not found for that course")

    log = StudyLog(
        user_id=user.id,
        course_id=payload.course_id,
        task_id=payload.task_id,
        minutes=payload.minutes,
        focus=payload.focus,
        note=payload.note,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return _log_response(log)
