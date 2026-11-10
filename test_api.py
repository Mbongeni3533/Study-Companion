"""Smoke test: imports, models, chunking and schemas.

Run from the repository root (or from backend/)::

    python test_api.py

Exits non-zero if any check fails.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

failures: list[str] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        print(f"✓ {name}" + (f": {detail}" if detail else ""))
    except Exception as exc:  # noqa: BLE001 - report and continue
        failures.append(f"{name}: {exc}")
        print(f"✗ {name}: {exc}")


def imports() -> str:
    from app.models import ChatSession, Course, Document, Task, Topic, User  # noqa: F401
    from app.schemas import Token, UserCreate, UserResponse  # noqa: F401
    from app.services.ai_coach import AIStudyCoach  # noqa: F401
    from app.services.ai_provider import ClaudeProvider  # noqa: F401
    from app.services.document_processor import ChunkProcessor, DocumentProcessor  # noqa: F401
    from app.services.payment_service import PaymentService  # noqa: F401
    from app.utils.auth import (  # noqa: F401
        generate_course_id,
        generate_document_id,
        generate_user_id,
    )

    return "models, schemas, services and utils import cleanly"


def ids() -> str:
    from app.utils.auth import generate_course_id, generate_document_id, generate_user_id

    user_id, course_id, document_id = generate_user_id(), generate_course_id(), generate_document_id()
    assert user_id.startswith("user_"), "user id prefix"
    assert course_id.startswith("course_"), "course id prefix"
    assert document_id.startswith("doc_"), "document id prefix"
    assert len({user_id, generate_user_id()}) == 2, "ids must be unique"
    return f"{user_id}, {course_id}, {document_id}"


def passwords() -> str:
    from app.utils.auth import hash_password, verify_password

    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored), "valid password rejected"
    assert not verify_password("wrong password", stored), "invalid password accepted"
    assert stored != hash_password("correct horse battery"), "hashes must be salted"
    return "hash + verify + salt"


def chunking() -> str:
    from app.services.document_processor import ChunkProcessor

    text = (
        "Cell Structure\n\n"
        "The cell membrane is a selectively permeable barrier made of a phospholipid bilayer. "
        "Proteins embedded in the membrane act as channels and receptors.\n\n"
        "Enzyme Kinetics\n\n"
        "Enzymes are biological catalysts that lower the activation energy of a reaction. "
        "The active site is the region where the substrate binds."
    )
    chunks = ChunkProcessor.chunk_text(text, chunk_size=10, overlap=2)
    assert chunks, "no chunks produced"
    assert all("text" in chunk and chunk["text"] for chunk in chunks), "chunk missing text"
    headings = {chunk["heading"] for chunk in chunks}
    assert {"Cell Structure", "Enzyme Kinetics"} <= headings, f"headings not carried: {headings}"
    return f"{len(chunks)} chunks, headings preserved"


def schemas() -> str:
    from app.schemas import UserCreate

    user = UserCreate(
        email="test@example.com",
        password="a-long-enough-password",
        name="Test User",
        university="Test University",
    )
    assert user.email == "test@example.com"
    assert user.daily_study_minutes is None
    return "UserCreate validation"


def topic_map() -> str:
    from app.services.topic_extractor import ChunkView, TopicExtractor

    chunks = [
        ChunkView(id=1, text="Diffusion moves molecules down a concentration gradient.", heading="Diffusion"),
        ChunkView(id=2, text="Osmosis is the diffusion of water across a membrane.", heading="Osmosis"),
        ChunkView(id=3, text="Active transport uses ATP to move ions against a gradient.", heading="Active transport"),
    ]
    topics = TopicExtractor.build_topics(chunks)
    assert len(topics) == 3, f"expected 3 topics, got {len(topics)}"
    assert all(1 <= topic["difficulty"] <= 5 for topic in topics), "difficulty out of range"
    assert abs(sum(topic["weight"] for topic in topics) - 1.0) < 0.05, "weights not normalised"
    return f"{len(topics)} topics from headings"


def coach_plan() -> str:
    import asyncio

    from app.services.ai_coach import AIStudyCoach, TopicBrief

    coach = AIStudyCoach(provider=None)  # force the rule engine
    assert coach.provider_name == "rules"
    plan = asyncio.run(
        coach.build_task_plan(
            course_title="Cell Biology",
            topics=[TopicBrief(title="Diffusion", difficulty=2), TopicBrief(title="Osmosis", difficulty=3)],
            excerpts=[],
            count=5,
            minutes_per_day=60,
        )
    )
    assert len(plan.items) == 5, f"expected 5 tasks, got {len(plan.items)}"
    assert plan.source == "rules"
    assert all(item.estimated_minutes > 0 for item in plan.items)
    return f"{len(plan.items)} tasks, {plan.note}"


def ocr_fallback() -> str:
    """A PDF with no text layer should come back through OCR."""
    import tempfile
    from pathlib import Path

    from PIL import Image, ImageDraw

    from app.services import ocr
    from app.services.document_processor import DocumentProcessor

    if not ocr.available():
        return "skipped - no OCR engine installed (pip install rapidocr-onnxruntime)"

    with tempfile.TemporaryDirectory() as tmp:
        image = Image.new("RGB", (1200, 600), "white")
        draw = ImageDraw.Draw(image)
        draw.text((60, 60), "Enzyme Kinetics", fill="black", font_size=40)
        draw.text((60, 140), "Enzymes lower the activation energy of a reaction.", fill="black", font_size=32)
        draw.text((60, 210), "The active site binds the substrate.", fill="black", font_size=32)
        pdf_path = Path(tmp) / "scan.pdf"
        image.save(pdf_path, "PDF", resolution=150)

        result = DocumentProcessor.extract(pdf_path, "scan.pdf", "application/pdf")
        assert result.word_count >= 8, f"OCR produced too little text: {result.text!r}"
        assert any("OCR" in warning for warning in result.warnings), result.warnings
        return f"{result.word_count} words recovered with {ocr.engine_name()}"


def models() -> str:
    from app.models import User

    user = User(
        id="user_smoke0001",
        email="test@example.com",
        name="Test User",
        university="Test University",
        created_at=datetime.now(timezone.utc),
    )
    assert user.name == "Test User"
    assert user.email == "test@example.com"
    assert User.__tablename__ == "users"
    return "User model instantiation"


for name, fn in [
    ("Imports", imports),
    ("ID generation", ids),
    ("Password hashing", passwords),
    ("Chunking", chunking),
    ("Schema validation", schemas),
    ("Topic mapping", topic_map),
    ("Study plan (rules)", coach_plan),
    ("OCR fallback", ocr_fallback),
    ("Models", models),
]:
    check(name, fn)

print("\n" + "=" * 50)
if failures:
    print(f"FAILED ({len(failures)} check{'s' if len(failures) != 1 else ''})")
    for failure in failures:
        print(f"  - {failure}")
    print("=" * 50)
    sys.exit(1)

print("All checks passed.")
print("=" * 50)
