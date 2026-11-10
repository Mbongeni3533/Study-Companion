"""Study plan generation and task tracking."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Chunk, Course, Document, StudyLog, Task, TopicProgress, User
from ..schemas import (
    TaskGenerateRequest,
    TaskGenerateResult,
    TaskResponse,
    TaskUpdate,
)
from ..serializers import task_response, today_utc
from ..services.ai_coach import Excerpt, TopicBrief, get_coach
from ..utils.auth import generate_task_id
from ..utils.deps import get_current_user, get_owned_course
from ..utils.text import truncate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _load_task(db: Session, user: User, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    course = db.get(Course, task.course_id)
    if course is None or course.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _record_completion(db: Session, user: User, task: Task) -> None:
    """Log the study minutes and nudge topic mastery when a task is finished."""
    db.add(
        StudyLog(
            user_id=user.id,
            course_id=task.course_id,
            task_id=task.id,
            minutes=max(5, task.estimated_minutes),
            focus=task.task_type,
            note=f"Completed: {task.title}"[:500],
        )
    )
    if not task.topic_id:
        return

    progress = db.scalar(
        select(TopicProgress).where(
            TopicProgress.user_id == user.id, TopicProgress.topic_id == task.topic_id
        )
    )
    if progress is None:
        progress = TopicProgress(
            user_id=user.id,
            topic_id=task.topic_id,
            confidence=2,
            minutes_studied=max(5, task.estimated_minutes),
            last_reviewed_at=datetime.now(timezone.utc),
        )
        db.add(progress)
    else:
        progress.confidence = min(5, progress.confidence + 1)
        progress.minutes_studied += max(5, task.estimated_minutes)
        progress.last_reviewed_at = datetime.now(timezone.utc)


@router.post("/courses/{course_id}/generate", response_model=TaskGenerateResult)
async def generate_tasks(
    course_id: str,
    payload: TaskGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskGenerateResult:
    course = get_owned_course(course_id, db, user)

    topics = sorted(course.topics, key=lambda t: t.order_index)
    if not topics and not course.documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload study material first so the plan can be based on your course.",
        )

    briefs = [
        TopicBrief(
            title=topic.title,
            summary=topic.summary,
            keywords=list(topic.keywords or []),
            difficulty=topic.difficulty,
            order_index=topic.order_index,
        )
        for topic in topics
    ]

    # Ground the AI plan in a handful of representative chunks.
    excerpts = _course_excerpts(db, course, limit=6)

    plan = await get_coach().build_task_plan(
        course_title=course.title,
        topics=briefs,
        excerpts=excerpts,
        count=payload.count,
        focus=payload.focus,
        minutes_per_day=payload.minutes_per_day or user.daily_study_minutes,
        difficulty=payload.difficulty,
    )

    if payload.replace_existing:
        for existing in list(course.tasks):
            if existing.status != "done":
                db.delete(existing)
        db.flush()

    today = today_utc()
    created: list[Task] = []
    for index, item in enumerate(plan.items):
        topic = topics[item.topic_index] if item.topic_index is not None else None
        task = Task(
            id=generate_task_id(),
            course_id=course.id,
            topic_id=topic.id if topic else None,
            title=item.title,
            description=item.description,
            task_type=item.task_type,
            difficulty=item.difficulty,
            estimated_minutes=item.estimated_minutes,
            due_date=today + timedelta(days=item.day_offset),
            status="todo",
            hint=item.hint,
        )
        db.add(task)
        created.append(task)

    db.commit()
    for task in created:
        db.refresh(task)

    return TaskGenerateResult(
        tasks=[task_response(task) for task in created],
        source=plan.source,  # type: ignore[arg-type]
        plan_note=plan.note,
    )


def _course_excerpts(db: Session, course: Course, limit: int = 6) -> list[Excerpt]:
    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.course_id == course.id)
        .order_by(Document.created_at, Chunk.position)
        .limit(limit)
    ).all()
    return [
        Excerpt(
            text=truncate(chunk.text, 700),
            heading=chunk.heading,
            document_name=document.filename,
        )
        for chunk, document in rows
    ]


@router.get("/today", response_model=list[TaskResponse])
def tasks_due_today(
    course_id: str | None = Query(default=None),
    include_upcoming: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    today = today_utc()
    query = (
        select(Task)
        .join(Course, Task.course_id == Course.id)
        .where(Course.user_id == user.id, Task.status != "done")
    )
    if course_id:
        query = query.where(Task.course_id == course_id)
    if not include_upcoming:
        query = query.where(Task.due_date.is_not(None), Task.due_date <= today)
    query = query.order_by(Task.due_date, Task.created_at)
    tasks = list(db.scalars(query).all())
    return [task_response(task) for task in tasks]


@router.get("/courses/{course_id}", response_model=list[TaskResponse])
def list_course_tasks(
    course_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    course = get_owned_course(course_id, db, user)
    tasks = sorted(
        course.tasks,
        key=lambda t: (t.status == "done", t.due_date or date.max, t.created_at),
    )
    if status_filter:
        tasks = [t for t in tasks if t.status == status_filter]
    return [task_response(task) for task in tasks]


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    task = _load_task(db, user, task_id)
    data = payload.model_dump(exclude_unset=True)

    previous_status = task.status
    for field, value in data.items():
        setattr(task, field, value)

    if "status" in data:
        if task.status == "done" and previous_status != "done":
            task.completed_at = datetime.now(timezone.utc)
            _record_completion(db, user, task)
        elif task.status != "done":
            task.completed_at = None

    db.commit()
    db.refresh(task)
    return task_response(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    task = _load_task(db, user, task_id)
    db.delete(task)
    db.commit()
