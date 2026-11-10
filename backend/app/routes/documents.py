"""Courses, document uploads, the topic map and material search."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Chunk, Course, Document, StudyLog, User
from ..schemas import (
    ChunkResponse,
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    DocumentResponse,
    DocumentUploadResult,
    SearchHit,
    TextPasteCreate,
    TopicResponse,
)
from ..serializers import (
    chunk_preview,
    course_response,
    document_response,
    topic_response,
)
from ..services.document_processor import ChunkProcessor, DocumentProcessor, ExtractionError
from ..services.topic_service import rebuild_course_topics
from ..utils.auth import generate_course_id, generate_document_id
from ..utils.deps import get_current_user, get_owned_course
from ..utils.text import clean_text, rank_chunks, truncate, words

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_CHUNK = 1024 * 1024


def _minutes_by_course(db: Session, user_id: str) -> dict[str, int]:
    rows = db.execute(
        select(StudyLog.course_id, func.coalesce(func.sum(StudyLog.minutes), 0))
        .where(StudyLog.user_id == user_id, StudyLog.course_id.is_not(None))
        .group_by(StudyLog.course_id)
    ).all()
    return {course_id: int(total) for course_id, total in rows if course_id}


def _confidence_by_topic(db: Session, user_id: str) -> dict[str, int]:
    from ..models import TopicProgress

    rows = db.execute(
        select(TopicProgress.topic_id, TopicProgress.confidence).where(
            TopicProgress.user_id == user_id
        )
    ).all()
    return {topic_id: confidence for topic_id, confidence in rows}


# ------------------------------------------------------------------- courses
@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseResponse:
    course = Course(
        id=generate_course_id(),
        user_id=user.id,
        title=payload.title.strip(),
        code=(payload.code or "").strip() or None,
        subject=(payload.subject or "").strip() or None,
        description=(payload.description or "").strip() or None,
        exam_date=payload.exam_date,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course_response(course)


@router.get("/courses", response_model=list[CourseResponse])
def list_courses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    courses = list(
        db.scalars(
            select(Course).where(Course.user_id == user.id).order_by(Course.created_at.desc())
        ).all()
    )
    minutes = _minutes_by_course(db, user.id)
    return [course_response(c, minutes_studied=minutes.get(c.id, 0)) for c in courses]


@router.get("/courses/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseResponse:
    course = get_owned_course(course_id, db, user)
    minutes = _minutes_by_course(db, user.id)
    return course_response(course, minutes_studied=minutes.get(course.id, 0))


@router.patch("/courses/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: str,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseResponse:
    course = get_owned_course(course_id, db, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course_response(course, minutes_studied=_minutes_by_course(db, user.id).get(course.id, 0))


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    course = get_owned_course(course_id, db, user)
    for document in course.documents:
        if document.storage_path:
            Path(document.storage_path).unlink(missing_ok=True)
    db.delete(course)
    db.commit()


# ----------------------------------------------------------------- documents
def _store_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while True:
            block = file.file.read(UPLOAD_CHUNK)
            if not block:
                break
            size += len(block)
            if size > max_bytes:
                handle.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.",
                )
            handle.write(block)
    return size


def _ingest(
    db: Session,
    course: Course,
    *,
    filename: str,
    text: str,
    content_type: str | None,
    storage_path: str | None,
    size_bytes: int,
    page_count: int = 0,
    warnings: list[str] | None = None,
) -> tuple[Document, int, int]:
    """Persist a document, its chunks and the refreshed topic map."""
    settings = get_settings()
    document = Document(
        id=generate_document_id(),
        course_id=course.id,
        filename=filename[:255],
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        status="processing",
        page_count=page_count,
        extraction_warnings=warnings or [],
    )
    db.add(document)
    db.flush()

    cleaned = clean_text(text)
    document.word_count = len(words(cleaned))
    document.page_count = page_count
    document.status = "ready"

    pieces = ChunkProcessor.chunk_text(
        cleaned,
        chunk_size=ChunkProcessor.DEFAULT_CHUNK_SIZE,
        overlap=ChunkProcessor.DEFAULT_OVERLAP,
    )
    chunks: list[Chunk] = []
    for piece in pieces:
        chunk = Chunk(
            document_id=document.id,
            course_id=course.id,
            position=piece["index"],
            text=piece["text"],
            word_count=piece["word_count"],
            heading=(piece.get("heading") or "")[:300] or None,
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()

    document.processed_at = datetime.now(timezone.utc)
    db.flush()
    topics = rebuild_course_topics(db, course)
    db.commit()
    db.refresh(document)
    return document, len(chunks), len(topics)


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    course_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentUploadResult:
    settings = get_settings()
    course = get_owned_course(course_id, db, user)

    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in DocumentProcessor.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{suffix or filename}' is not a supported file type. "
                "Supported: PDF, DOCX, PPTX, TXT, MD, CSV, HTML and images."
            ),
        )

    destination = settings.upload_dir / f"{generate_document_id()}{suffix}"
    size = _store_upload(file, destination, settings.max_upload_bytes)

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        # Extraction (and OCR for scans) is CPU bound - keep the event loop free.
        extraction = await run_in_threadpool(
            DocumentProcessor.extract, destination, filename, file.content_type
        )
    except ExtractionError as exc:
        document = Document(
            id=generate_document_id(),
            course_id=course.id,
            filename=filename[:255],
            content_type=file.content_type,
            size_bytes=size,
            storage_path=str(destination),
            status="failed",
            error_message=str(exc),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return DocumentUploadResult(
            document=document_response(document),
            message=str(exc),
        )

    document, chunk_count, topic_count = _ingest(
        db,
        course,
        filename=filename,
        text=extraction.text,
        content_type=file.content_type,
        storage_path=str(destination),
        size_bytes=size,
        page_count=extraction.page_count,
        warnings=extraction.warnings,
    )

    warnings = " ".join(extraction.warnings)
    message = (
        f"Processed {document.word_count} words into {chunk_count} chunks "
        f"across {topic_count} topics."
    )
    if warnings:
        message = f"{message} {warnings}"

    return DocumentUploadResult(
        document=document_response(document),
        topics_created=topic_count,
        chunks_created=chunk_count,
        message=message,
    )


@router.post(
    "/courses/{course_id}/documents/paste",
    response_model=DocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
def paste_notes(
    course_id: str,
    payload: TextPasteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentUploadResult:
    """Ingest typed/pasted notes - the fastest way to try the app."""
    course = get_owned_course(course_id, db, user)
    text = clean_text(payload.text)
    if len(words(text)) < 20:
        raise HTTPException(
            status_code=400, detail="Paste at least 20 words so there is something to study."
        )

    document, chunk_count, topic_count = _ingest(
        db,
        course,
        filename=(payload.filename or "Pasted notes.txt")[:255],
        text=text,
        content_type="text/plain",
        storage_path=None,
        size_bytes=len(text.encode("utf-8")),
    )
    return DocumentUploadResult(
        document=document_response(document),
        topics_created=topic_count,
        chunks_created=chunk_count,
        message=(
            f"Added {document.word_count} words as {chunk_count} chunks "
            f"across {topic_count} topics."
        ),
    )


@router.get("/courses/{course_id}/documents", response_model=list[DocumentResponse])
def list_documents(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    course = get_owned_course(course_id, db, user)
    documents = sorted(course.documents, key=lambda d: d.created_at, reverse=True)
    return [document_response(document) for document in documents]


@router.get(
    "/courses/{course_id}/documents/{document_id}", response_model=DocumentResponse
)
def get_document(
    course_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    course = get_owned_course(course_id, db, user)
    document = db.get(Document, document_id)
    if document is None or document.course_id != course.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_response(document)


@router.get(
    "/courses/{course_id}/documents/{document_id}/chunks",
    response_model=list[ChunkResponse],
)
def list_document_chunks(
    course_id: str,
    document_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChunkResponse]:
    course = get_owned_course(course_id, db, user)
    document = db.get(Document, document_id)
    if document is None or document.course_id != course.id:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = list(
        db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document.id)
            .order_by(Chunk.position)
            .limit(limit)
        ).all()
    )
    return [ChunkResponse.model_validate(chunk) for chunk in chunks]


@router.delete(
    "/courses/{course_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    course_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    course = get_owned_course(course_id, db, user)
    document = db.get(Document, document_id)
    if document is None or document.course_id != course.id:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.storage_path:
        Path(document.storage_path).unlink(missing_ok=True)
    db.delete(document)
    db.flush()
    rebuild_course_topics(db, course)


# -------------------------------------------------------------------- topics
@router.get("/courses/{course_id}/topics", response_model=list[TopicResponse])
def list_topics(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TopicResponse]:
    course = get_owned_course(course_id, db, user)
    confidence = _confidence_by_topic(db, user.id)
    topics = sorted(course.topics, key=lambda t: t.order_index)
    return [topic_response(t, confidence.get(t.id, 0)) for t in topics]


@router.post("/courses/{course_id}/topics/rebuild", response_model=list[TopicResponse])
def rebuild_topics(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TopicResponse]:
    course = get_owned_course(course_id, db, user)
    topics = rebuild_course_topics(db, course)
    return [topic_response(topic) for topic in sorted(topics, key=lambda t: t.order_index)]


# -------------------------------------------------------------------- search
@router.get("/courses/{course_id}/search", response_model=list[SearchHit])
def search_material(
    course_id: str,
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SearchHit]:
    course = get_owned_course(course_id, db, user)
    chunks = list(
        db.scalars(select(Chunk).where(Chunk.course_id == course.id)).all()
    )
    if not chunks:
        return []

    document_names = {
        document.id: document.filename for document in course.documents
    }
    ranked = rank_chunks(q, chunks, top_k=limit)
    hits: list[SearchHit] = []
    for chunk, score in ranked:
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document_names.get(chunk.document_id, "material"),
                heading=chunk.heading,
                text=truncate(chunk_preview(chunk, 400), 320),
                score=round(float(score), 4),
            )
        )
    return hits
