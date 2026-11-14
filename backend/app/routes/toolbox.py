"""Toolbox: CVs, cover letters, humanising, integrity checks and counselling.

Writing agents are authenticated and personalised, so they are not public. The
content they draw on (professions, counsellors, tones) ships with the app.
"""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Chunk, CounsellingSession, Document, User, as_utc
from ..schemas import (
    CVImportFields,
    CVImportResult,
    CVPDFRequest,
    CVRequest,
    CVResult,
    CounsellingBookingRequest,
    DictionaryDefinition,
    DictionaryResponse,
    CounsellingOverview,
    CounsellingSessionResponse,
    CounsellorResponse,
    CounsellingSlot,
    HumanizeRequest,
    HumanizeResult,
    IntegrityRequest,
    IntegrityResult,
    LetterRequest,
    LetterResult,
    ToolboxMeta,
)
import httpx

from ..services.cv_import import parse_cv_text
from ..services.cv_pdf import render_cv_pdf
from ..services.document_processor import DocumentProcessor, ExtractionError
from ..services.toolbox import (
    check_integrity,
    get_agents,
    next_slots,
    professions,
    toolbox_content,
)
from ..utils.auth import generate_booking_id
from ..utils.deps import get_current_user, get_owned_course

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/toolbox", tags=["toolbox"])

DURATION_MINUTES = 30
#: Cap the library scan so a huge course cannot stall the request.
MAX_PASSAGES = 400
#: CVs are small; a tighter limit than the general document library.
CV_IMPORT_MAX_BYTES = 10 * 1024 * 1024
CV_IMPORT_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md", ".markdown", ".text"})


def _counsellors() -> list[dict[str, Any]]:
    return list(toolbox_content()["counsellors"])


def _booked_slots(db: Session) -> set[tuple[str, str, str]]:
    rows = db.scalars(select(CounsellingSession).where(CounsellingSession.status == "booked"))
    booked: set[tuple[str, str, str]] = set()
    for row in rows:
        moment = as_utc(row.scheduled_for)
        if moment is None:
            continue
        booked.add((row.counsellor_id, moment.date().isoformat(), moment.strftime("%H:%M")))
    return booked


def _counsellor_name(counsellor_id: str) -> str:
    for counsellor in _counsellors():
        if counsellor["id"] == counsellor_id:
            return counsellor["name"]
    return "Counsellor"


def _session_response(row: CounsellingSession) -> CounsellingSessionResponse:
    moment = as_utc(row.scheduled_for) or row.scheduled_for
    return CounsellingSessionResponse(
        id=row.id,
        counsellor_id=row.counsellor_id,
        counsellor_name=_counsellor_name(row.counsellor_id),
        focus=row.focus,
        scheduled_for=moment,
        duration_minutes=row.duration_minutes,
        notes=row.notes,
        status=row.status,
        created_at=as_utc(row.created_at) or row.created_at,
    )


def _counsellor_cards(db: Session) -> list[CounsellorResponse]:
    """Counsellors with their next free slot."""
    slots = next_slots(_counsellors(), _booked_slots(db), start_date=date.today(), limit=4)
    next_by_counsellor: dict[str, str] = {}
    for slot in slots:
        next_by_counsellor.setdefault(slot["counsellor_id"], slot["label"])
    return [
        CounsellorResponse(
            id=item["id"],
            name=item["name"],
            title=item["title"],
            specialties=item["specialties"],
            languages=item["languages"],
            bio=item["bio"],
            next_slot=next_by_counsellor.get(item["id"]),
        )
        for item in _counsellors()
    ]


@router.get("/meta", response_model=ToolboxMeta)
def toolbox_meta(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolboxMeta:
    """Agents, tones, professions and counsellors for the toolbox page."""
    content = toolbox_content()
    return ToolboxMeta(
        agents=content["agents"],
        tones=content["tones"],
        professions=professions(),
        counselling_focus=content["counselling_focus"],
        counsellors=_counsellor_cards(db),
        ai_available=get_agents().ai_available,
    )


@router.post("/cv", response_model=CVResult)
async def build_cv(payload: CVRequest, user: User = Depends(get_current_user)) -> CVResult:
    data = payload.model_dump()
    if not data.get("full_name"):
        data["full_name"] = user.name
    if not data.get("email"):
        data["email"] = user.email
    result = await get_agents().cv(data)
    return CVResult(**result)


@router.post("/cv/import", response_model=CVImportResult)
async def import_cv(
    file: UploadFile = File(...), user: User = Depends(get_current_user)
) -> CVImportResult:
    """Read an existing CV and return fields for the builder to prefill.

    The file is temporary: it is parsed and deleted, never stored in the library.
    """
    del user  # authentication only; the import is not saved against the account
    filename = Path(file.filename or "cv").name
    suffix = Path(filename).suffix.lower()
    if suffix not in CV_IMPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, TXT or Markdown CV")

    raw = await file.read(CV_IMPORT_MAX_BYTES + 1)
    if len(raw) > CV_IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="That CV is too large - the limit is 10 MB")
    if not raw:
        raise HTTPException(status_code=400, detail="That file is empty")

    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.upload_dir)
    temp_path = Path(temporary.name)
    try:
        try:
            temporary.write(raw)
        finally:
            temporary.close()
        extraction = DocumentProcessor.extract(temp_path, filename, file.content_type)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - report a readable import failure
        logger.exception("CV import extraction failed")
        raise HTTPException(
            status_code=400, detail="Could not read that CV - try a text-based PDF or DOCX"
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    if len(extraction.text.split()) < 10:
        raise HTTPException(
            status_code=400, detail="That file does not contain enough readable text to import"
        )

    fields = CVImportFields(**parse_cv_text(extraction.text))
    warnings = list(extraction.warnings)
    warnings.append(
        "CV layouts vary, so check every imported field before building - some details may have landed in the wrong box."
    )
    return CVImportResult(
        filename=filename,
        text=extraction.text[:60000],
        fields=fields,
        warnings=warnings,
    )


@router.post(
    "/cv/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, 400: {"description": "Nothing to render"}},
)
def cv_pdf(payload: CVPDFRequest, user: User = Depends(get_current_user)) -> Response:
    """Render the CV the student is looking at as a styled A4 PDF.

    The client sends back the Markdown it already has, so this never regenerates
    (or re-bills) the draft and the download matches the preview exactly.
    """
    name = (payload.full_name or user.name or "CV").strip()
    try:
        pdf = render_cv_pdf(payload.document, full_name=name)
    except ValueError:
        raise HTTPException(status_code=400, detail="There is nothing to put in the PDF yet")
    except Exception:  # noqa: BLE001 - a render bug must not 500 silently in logs only
        logger.exception("CV PDF rendering failed")
        raise HTTPException(status_code=500, detail="Could not build the PDF - try again")

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "cv"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-cv.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/letters", response_model=LetterResult)
async def build_letter(payload: LetterRequest, user: User = Depends(get_current_user)) -> LetterResult:
    data = payload.model_dump()
    if not data.get("your_name"):
        data["your_name"] = user.name
    result = await get_agents().letter(data)
    return LetterResult(**result)


@router.post("/humanize", response_model=HumanizeResult)
async def humanize_text(payload: HumanizeRequest, user: User = Depends(get_current_user)) -> HumanizeResult:
    result = await get_agents().humanize(payload.text, payload.tone)
    return HumanizeResult(**result)


@router.post("/integrity", response_model=IntegrityResult)
def integrity_check(
    payload: IntegrityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrityResult:
    """Compare a submission with the student's own library.

    Deliberately honest about scope: this is text matching against uploaded
    material, not a web plagiarism database.
    """
    course_ids = [course.id for course in user.courses]
    if payload.course_id:
        get_owned_course(payload.course_id, db, user)  # 404s for someone else's course
        course_ids = [payload.course_id]

    sources: list[tuple[str, str]] = []
    if course_ids:
        rows = db.execute(
            select(Chunk.text, Chunk.heading, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.course_id.in_(course_ids), Document.status == "ready")
            .limit(MAX_PASSAGES)
        ).all()
        for text, heading, filename in rows:
            sources.append((f"{filename} · {heading or 'passage'}", text))

    return IntegrityResult(**check_integrity(payload.text, sources))


@router.get("/dictionary/{word}", response_model=DictionaryResponse)
async def dictionary_lookup(
    word: str,
    user: User = Depends(get_current_user),
) -> DictionaryResponse:
    """Look up an English word's definitions, phonetics and examples."""
    cleaned = (word or "").strip().lower()
    if not cleaned or len(cleaned) > 60 or not cleaned.replace("-", "").replace(" ", "").isalpha():
        raise HTTPException(status_code=400, detail="Enter a single English word.")
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{cleaned}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Dictionary service unavailable: {exc}") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"No definition found for '{cleaned}'.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Dictionary lookup failed.")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid dictionary response.") from exc

    entries = []
    phonetic = None
    for item in data if isinstance(data, list) else []:
        if not phonetic:
            phonetic = item.get("phonetic") or (item.get("phonetics") or [{}])[0].get("text")
        for meaning in item.get("meanings", []):
            part = meaning.get("partOfSpeech")
            for definition in meaning.get("definitions", []):
                entries.append(
                    DictionaryDefinition(
                        part_of_speech=part,
                        definition=definition.get("definition", ""),
                        example=definition.get("example"),
                        synonyms=list(definition.get("synonyms") or [])[:8],
                        antonyms=list(definition.get("antonyms") or [])[:8],
                    )
                )
    if not entries:
        raise HTTPException(status_code=404, detail=f"No definition found for '{cleaned}'.")
    return DictionaryResponse(word=cleaned, phonetic=phonetic, entries=entries[:12])


@router.get("/counselling", response_model=CounsellingOverview)
def counselling_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CounsellingOverview:
    mine = db.scalars(
        select(CounsellingSession)
        .where(CounsellingSession.user_id == user.id)
        .order_by(CounsellingSession.scheduled_for)
    ).all()
    return CounsellingOverview(
        counsellors=_counsellor_cards(db),
        sessions=[_session_response(row) for row in mine],
        slots=[CounsellingSlot(**slot) for slot in next_slots(
            _counsellors(), _booked_slots(db), start_date=date.today(), limit=8
        )],
        focus_options=list(toolbox_content()["counselling_focus"]),
    )


@router.post(
    "/counselling",
    response_model=CounsellingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def book_counselling(
    payload: CounsellingBookingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CounsellingSessionResponse:
    counsellor = next((item for item in _counsellors() if item["id"] == payload.counsellor_id), None)
    if counsellor is None:
        raise HTTPException(status_code=404, detail="Counsellor not found")
    if payload.time not in counsellor.get("slot_times", []):
        raise HTTPException(status_code=400, detail="That time is not offered by this counsellor")
    if payload.date < date.today():
        raise HTTPException(status_code=400, detail="Pick a future date")
    hour, minute = (int(part) for part in payload.time.split(":"))
    requested = datetime.combine(payload.date, time(hour=hour, minute=minute), tzinfo=timezone.utc)
    if requested <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="That time has already passed")
    if (payload.counsellor_id, payload.date.isoformat(), payload.time) in _booked_slots(db):
        raise HTTPException(status_code=409, detail="That slot has just been taken - pick another")

    row = CounsellingSession(
        id=generate_booking_id(),
        user_id=user.id,
        counsellor_id=payload.counsellor_id,
        focus=payload.focus.strip()[:120],
        scheduled_for=requested,
        duration_minutes=DURATION_MINUTES,
        notes=(payload.notes or "").strip()[:1000] or None,
        status="booked",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _session_response(row)


@router.post("/counselling/{booking_id}/cancel", response_model=CounsellingSessionResponse)
def cancel_counselling(
    booking_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CounsellingSessionResponse:
    row = db.get(CounsellingSession, booking_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if row.status != "booked":
        raise HTTPException(status_code=400, detail="This booking is no longer active")
    row.status = "cancelled"
    db.commit()
    db.refresh(row)
    return _session_response(row)
