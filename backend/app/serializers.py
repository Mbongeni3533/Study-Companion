"""Shared response builders so route handlers stay thin."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from .models import Chunk, Course, Document, Task, Topic
from .schemas import (
    CourseResponse,
    DocumentResponse,
    TaskResponse,
    TopicResponse,
)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def compute_streak(days: Iterable[date]) -> int:
    unique = sorted(set(days), reverse=True)
    if not unique:
        return 0
    today = today_utc()
    if unique[0] not in (today, today - timedelta(days=1)):
        return 0
    streak = 1
    cursor = unique[0]
    for day in unique[1:]:
        if day == cursor:
            continue
        if day == cursor - timedelta(days=1):
            streak += 1
            cursor = day
        else:
            break
    return streak


def readiness_score(course: Course) -> int:
    topics: list[Topic] = list(course.topics)
    tasks: list[Task] = list(course.tasks)
    if not topics and not tasks:
        return 0

    completed_by_topic = Counter(t.topic_id for t in tasks if t.status == "done" and t.topic_id)
    topic_coverage = 0.0
    if topics:
        topic_coverage = sum(1 for tp in topics if completed_by_topic.get(tp.id, 0) > 0) / len(topics)
    task_rate = 0.0
    if tasks:
        task_rate = sum(1 for t in tasks if t.status == "done") / len(tasks)

    score = 100 * (0.55 * topic_coverage + 0.45 * task_rate)
    return max(0, min(100, round(score)))


def topic_response(topic: Topic, confidence: int = 0) -> TopicResponse:
    tasks = list(topic.tasks or [])
    return TopicResponse(
        id=topic.id,
        course_id=topic.course_id,
        title=topic.title,
        summary=topic.summary,
        keywords=list(topic.keywords or []),
        difficulty=topic.difficulty,
        weight=topic.weight,
        order_index=topic.order_index,
        chunk_count=len(topic.chunks or []),
        confidence=confidence,
        task_count=len(tasks),
        completed_task_count=sum(1 for t in tasks if t.status == "done"),
    )


def task_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        course_id=task.course_id,
        topic_id=task.topic_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        difficulty=task.difficulty,
        estimated_minutes=task.estimated_minutes,
        due_date=task.due_date,
        status=task.status,
        hint=task.hint,
        created_at=task.created_at,
        completed_at=task.completed_at,
        topic_title=task.topic.title if task.topic else None,
    )


def document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        course_id=document.course_id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        error_message=document.error_message,
        word_count=document.word_count,
        page_count=document.page_count,
        extraction_warnings=list(document.extraction_warnings or []),
        created_at=document.created_at,
        processed_at=document.processed_at,
    )


def course_response(course: Course, *, minutes_studied: int = 0) -> CourseResponse:
    tasks = list(course.tasks or [])
    days_until_exam = None
    if course.exam_date:
        days_until_exam = (course.exam_date - today_utc()).days
    return CourseResponse(
        id=course.id,
        title=course.title,
        code=course.code,
        subject=course.subject,
        description=course.description,
        exam_date=course.exam_date,
        created_at=course.created_at,
        document_count=len(course.documents or []),
        topic_count=len(course.topics or []),
        task_count=len(tasks),
        completed_task_count=sum(1 for t in tasks if t.status == "done"),
        minutes_studied=minutes_studied,
        days_until_exam=days_until_exam,
        readiness_score=readiness_score(course),
    )


def chunk_count_for_document(document: Document) -> int:
    return len(document.chunks or [])


def chunk_preview(chunk: Chunk, limit: int = 240) -> str:
    text = " ".join((chunk.text or "").split())
    return text[:limit]
