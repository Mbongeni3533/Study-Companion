"""ORM models for the Study Companion.

The domain is deliberately small but complete:

User -> Course -> {Document -> Chunk, Topic, Task, ChatSession -> Message}
User -> StudyLog (study minutes, used for progress and exam readiness)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes; normalise before comparing."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="Student")
    university: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_tier: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    daily_study_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    courses: Mapped[list["Course"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", order_by="Course.created_at.desc()"
    )
    study_logs: Mapped[list["StudyLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(60))
    subject: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    exam_date: Mapped[date | None] = mapped_column(Date)

    owner: Mapped[User] = relationship(back_populates="courses")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    study_logs: Mapped[list["StudyLog"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extraction_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Live progress while a (possibly OCR'd) upload is being processed.
    progress_stage: Mapped[str | None] = mapped_column(String(32))
    progress_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")

    course: Mapped[Course] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(300))
    topic_id: Mapped[str | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    topic: Mapped["Topic | None"] = relationship(back_populates="chunks")


class Topic(TimestampMixin, Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source_document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    course: Mapped[Course] = relationship(back_populates="topics")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="topic")
    tasks: Mapped[list["Task"]] = relationship(back_populates="topic")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[str | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(24), default="read", nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="todo", nullable=False)
    hint: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped[Course] = relationship(back_populates="tasks")
    topic: Mapped[Topic | None] = relationship(back_populates="tasks")


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[str | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="Study session")

    course: Mapped[Course] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hint_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class StudyLog(Base):
    __tablename__ = "study_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[str | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(48))
    minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    focus: Mapped[str] = mapped_column(String(60), default="study", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="study_logs")
    course: Mapped[Course | None] = relationship(back_populates="study_logs")


class TopicProgress(Base):
    """Per-topic mastery, updated when tasks are completed."""

    __tablename__ = "topic_progress"
    __table_args__ = (UniqueConstraint("user_id", "topic_id", name="uq_topic_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[str] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    confidence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1..5
    minutes_studied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
