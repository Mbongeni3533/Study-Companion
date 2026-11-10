"""AI study coach conversations, grounded in the course material."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ChatSession, Chunk, Course, Document, Message, User
from ..schemas import (
    ChatReply,
    ChatRequest,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionResponse,
    MessageResponse,
)
import json

from ..services.ai_coach import Excerpt, TopicBrief, get_coach
from ..services.thinking import guide as learner_guide
from ..utils.auth import generate_session_id
from ..utils.deps import get_current_user, get_owned_course
from ..utils.text import rank_chunks, truncate

router = APIRouter(prefix="/chat", tags=["chat"])


def _load_session(db: Session, user: User, session_id: str) -> tuple[ChatSession, Course]:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    course = db.get(Course, session.course_id)
    if course is None or course.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return session, course


def _session_response(session: ChatSession) -> ChatSessionResponse:
    messages = list(session.messages)
    preview = None
    if messages:
        preview = truncate(messages[-1].content, 120)
    return ChatSessionResponse(
        id=session.id,
        course_id=session.course_id,
        topic_id=session.topic_id,
        title=session.title,
        created_at=session.created_at,
        message_count=len(messages),
        preview=preview,
    )


@router.post(
    "/courses/{course_id}/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    course_id: str,
    payload: ChatSessionCreate | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    course = get_owned_course(course_id, db, user)
    payload = payload or ChatSessionCreate()

    title = (payload.title or "").strip()
    if not title:
        if payload.topic_id:
            topic = next((t for t in course.topics if t.id == payload.topic_id), None)
            title = f"Focus: {topic.title}" if topic else "Study session"
        else:
            title = "Study session"

    session = ChatSession(
        id=generate_session_id(),
        course_id=course.id,
        topic_id=payload.topic_id,
        title=title[:200],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_response(session)


@router.get("/courses/{course_id}/sessions", response_model=list[ChatSessionResponse])
def list_sessions(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatSessionResponse]:
    course = get_owned_course(course_id, db, user)
    sessions = sorted(course.chat_sessions, key=lambda s: s.created_at, reverse=True)
    return [_session_response(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    session, _course = _load_session(db, user, session_id)
    base = _session_response(session)
    return ChatSessionDetail(
        **base.model_dump(),
        messages=[MessageResponse.model_validate(m) for m in session.messages],
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatReply)
async def send_message(
    session_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatReply:
    session, course = _load_session(db, user, session_id)

    user_message = Message(
        session_id=session.id,
        role="user",
        content=payload.message.strip(),
        hint_level=payload.hint_level,
    )
    db.add(user_message)
    db.flush()

    topics = sorted(course.topics, key=lambda t: t.order_index)
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

    chunks = list(
        db.scalars(select(Chunk).where(Chunk.course_id == course.id)).all()
    )
    if session.topic_id:
        focused = [chunk for chunk in chunks if chunk.topic_id == session.topic_id]
        chunks = focused or chunks

    document_names = {doc.id: doc.filename for doc in course.documents}
    # Rank against the question, but always keep some material in context: a
    # question like "quiz me" has no keyword overlap yet still needs grounding.
    ranked = rank_chunks(payload.message, chunks, top_k=4) if chunks else []
    excerpts = [
        Excerpt(
            text=truncate(chunk.text, 800),
            heading=chunk.heading,
            document_name=document_names.get(chunk.document_id),
        )
        for chunk, _score in ranked[:4]
    ]

    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages
        if m.id != user_message.id
    ][-8:]

    answer = await get_coach().reply(
        course_title=course.title,
        course_code=course.code,
        topics=briefs,
        excerpts=excerpts,
        history=history,
        message=payload.message.strip(),
        hint_level=payload.hint_level,
        learner=learner_guide(
            json.loads(user.thinking_scores) if user.thinking_scores else None
        ),
    )

    reply = Message(
        session_id=session.id,
        role="assistant",
        content=answer.text,
        hint_level=payload.hint_level,
        meta={"source": answer.source, "citations": answer.citations},
    )
    db.add(reply)

    if session.title in {"Study session", ""}:
        session.title = truncate(payload.message, 60)
    db.commit()
    db.refresh(reply)
    db.refresh(user_message)

    return ChatReply(
        reply=MessageResponse.model_validate(reply),
        user_message=MessageResponse.model_validate(user_message),
        source=answer.source,  # type: ignore[arg-type]
        hint_level=payload.hint_level,
        citations=answer.citations,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session, _course = _load_session(db, user, session_id)
    db.delete(session)
    db.commit()
