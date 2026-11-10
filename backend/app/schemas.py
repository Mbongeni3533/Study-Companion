"""Pydantic request/response schemas (the public API contract)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TaskType = Literal["read", "practice", "quiz", "review", "write"]
TaskStatus = Literal["todo", "in_progress", "done"]
DocumentStatus = Literal["pending", "processing", "ready", "failed"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth/users
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="Student", max_length=120)
    university: str | None = Field(default=None, max_length=200)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AnonymousSessionCreate(BaseModel):
    name: str = Field(default="Guest student", max_length=120)
    university: str | None = Field(default=None, max_length=200)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    university: str | None = Field(default=None, max_length=200)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)


class UserResponse(ORMModel):
    id: str
    email: str | None
    name: str
    university: str | None
    is_anonymous: bool
    subscription_tier: str
    daily_study_minutes: int
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ------------------------------------------------------------------- courses
class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=60)
    subject: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    exam_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("title must be at least 2 characters")
        return cleaned


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=60)
    subject: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    exam_date: date | None = None


class CourseResponse(ORMModel):
    id: str
    title: str
    code: str | None
    subject: str | None
    description: str | None
    exam_date: date | None
    created_at: datetime

    document_count: int = 0
    topic_count: int = 0
    task_count: int = 0
    completed_task_count: int = 0
    minutes_studied: int = 0
    days_until_exam: int | None = None
    readiness_score: int = 0


# ----------------------------------------------------------------- documents
class DocumentResponse(ORMModel):
    id: str
    course_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    error_message: str | None
    word_count: int
    page_count: int
    extraction_warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    processed_at: datetime | None

    @field_validator("extraction_warnings", mode="before")
    @classmethod
    def _default_warnings(cls, value):
        return value or []


class DocumentUploadResult(BaseModel):
    document: DocumentResponse
    topics_created: int = 0
    chunks_created: int = 0
    message: str


class TextPasteCreate(BaseModel):
    """Ingest typed notes without a file upload."""

    text: str = Field(min_length=40, max_length=400_000)
    filename: str = Field(default="Pasted notes.txt", max_length=200)


class ChunkResponse(ORMModel):
    id: int
    document_id: str
    position: int
    text: str
    word_count: int
    heading: str | None
    topic_id: str | None


# -------------------------------------------------------------------- topics
class TopicResponse(ORMModel):
    id: str
    course_id: str
    title: str
    summary: str | None
    keywords: list[str] = Field(default_factory=list)
    difficulty: int
    weight: float
    order_index: int
    chunk_count: int = 0
    confidence: int = 0
    task_count: int = 0
    completed_task_count: int = 0

    @field_validator("keywords", mode="before")
    @classmethod
    def _default_keywords(cls, value):
        return value or []


# --------------------------------------------------------------------- tasks
class TaskResponse(ORMModel):
    id: str
    course_id: str
    topic_id: str | None
    title: str
    description: str | None
    task_type: str
    difficulty: int
    estimated_minutes: int
    due_date: date | None
    status: str
    hint: str | None
    created_at: datetime
    completed_at: datetime | None
    topic_title: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
    due_date: date | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=240)
    difficulty: int | None = Field(default=None, ge=1, le=5)


class TaskGenerateRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    focus: str | None = Field(default=None, max_length=300)
    minutes_per_day: int | None = Field(default=None, ge=10, le=480)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    replace_existing: bool = False


class TaskGenerateResult(BaseModel):
    tasks: list[TaskResponse]
    source: Literal["ai", "rules"]
    plan_note: str


# ---------------------------------------------------------------------- chat
class ChatSessionCreate(BaseModel):
    topic_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class MessageResponse(ORMModel):
    id: int
    role: str
    content: str
    hint_level: int
    created_at: datetime


class ChatSessionResponse(ORMModel):
    id: str
    course_id: str
    topic_id: str | None
    title: str
    created_at: datetime
    message_count: int = 0
    preview: str | None = None


class ChatSessionDetail(ChatSessionResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    hint_level: int = Field(default=1, ge=1, le=3)


class ChatReply(BaseModel):
    reply: MessageResponse
    user_message: MessageResponse
    source: Literal["ai", "rules"]
    hint_level: int
    citations: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ progress
class StudyLogCreate(BaseModel):
    course_id: str | None = None
    task_id: str | None = None
    minutes: int = Field(ge=1, le=600)
    focus: str = Field(default="study", max_length=60)
    note: str | None = Field(default=None, max_length=500)


class StudyLogResponse(ORMModel):
    id: int
    course_id: str | None
    task_id: str | None
    minutes: int
    focus: str
    note: str | None
    created_at: datetime


class CourseProgress(BaseModel):
    course_id: str
    course_title: str
    total_tasks: int
    completed_tasks: int
    minutes_studied: int
    streak_days: int
    readiness_score: int
    topics: list[TopicResponse] = Field(default_factory=list)


class ProgressSummary(BaseModel):
    minutes_today: int
    minutes_this_week: int
    minutes_total: int
    tasks_completed: int
    tasks_open: int
    streak_days: int
    daily_goal_minutes: int
    courses: list[CourseProgress] = Field(default_factory=list)
    recent_logs: list[StudyLogResponse] = Field(default_factory=list)


class SearchHit(BaseModel):
    chunk_id: int
    document_id: str
    document_name: str
    heading: str | None
    text: str
    score: float


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    ai_provider: str
    database: str
