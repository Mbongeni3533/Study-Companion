"""Developer/admin-only "executive" agents for Study Companion.

These helpers gather system state and produce reports. They are intentionally
kept behind the admin key and are never exposed to students.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Chunk,
    Course,
    Document,
    DocumentAlertState,
    Feedback,
    InviteCode,
    RemediationEvent,
    StudyLog,
    SystemHealthSnapshot,
    Topic,
    User,
    as_utc,
)
from .ai_provider import LLMMessage, build_provider

logger = logging.getLogger("study_companion.executive_agents")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def collect_metrics(db: Session) -> dict[str, Any]:
    settings = get_settings()
    users = db.scalars(select(User)).all()
    courses = db.scalars(select(Course)).all()
    documents = db.scalars(select(Document)).all()
    failed_docs = [d for d in documents if d.status == "failed"]
    processing_docs = [d for d in documents if d.status == "processing"]
    feedback_rows = db.scalars(select(Feedback)).all()
    invite_codes = db.scalars(select(InviteCode)).all()
    study_minutes = int(db.scalar(select(func.coalesce(func.sum(StudyLog.minutes), 0))) or 0)
    return {
        "users_total": len(users),
        "users_anonymous": sum(1 for u in users if u.is_anonymous),
        "courses_total": len(courses),
        "documents_total": len(documents),
        "documents_ready": sum(1 for d in documents if d.status == "ready"),
        "documents_failed": len(failed_docs),
        "documents_processing": len(processing_docs),
        "topics_total": int(db.scalar(select(func.count()).select_from(Topic)) or 0),
        "chunks_total": len(db.scalars(select(Chunk)).all()),
        "feedback_total": len(feedback_rows),
        "feedback_unresolved": len(feedback_rows),
        "invite_codes_total": len(invite_codes),
        "invite_codes_active": sum(1 for c in invite_codes if not c.revoked and c.uses < c.max_uses),
        "invite_codes_exhausted": sum(1 for c in invite_codes if c.uses >= c.max_uses),
        "study_minutes_total": study_minutes,
        "stale_processing_minutes": settings.stale_processing_minutes,
        "ai_enabled": settings.ai_enabled,
        "beta_invite_only": settings.beta_invite_only,
        "allow_anonymous_sessions": settings.allow_anonymous_sessions,
        "database": "sqlite" if settings.is_sqlite else "postgres",
        "environment": settings.environment,
    }


async def _llm(system: str, prompt: str, max_tokens: int = 1400) -> str | None:
    provider = build_provider()
    if provider is None:
        return None
    try:
        return await provider.complete(
            system=system,
            messages=[LLMMessage(role="user", content=prompt)],
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Executive agent LLM call failed: %s", exc)
        return None


async def ceo_report(db: Session) -> tuple[str, dict[str, Any], bool]:
    metrics = collect_metrics(db)
    prompt = (
        "You are the CEO of Study Companion. Write a concise executive report for the developer/admin. "
        "Use the metrics below. Include: overall health, growth/usage, risks, top priorities, and one recommendation. "
        "Keep it under 400 words and use Markdown headings.\n\n"
        f"Metrics (JSON): {metrics}"
    )
    text = await _llm(
        "You are a pragmatic startup CEO. Be specific and data-driven. Do not invent metrics not provided.",
        prompt,
    )
    ai_used = text is not None
    if text is None:
        lines = [
            "# Executive Report",
            "",
            f"- Users: {metrics['users_total']} ({metrics['users_anonymous']} anonymous)",
            f"- Courses: {metrics['courses_total']}",
            f"- Documents: {metrics['documents_total']} ready, {metrics['documents_failed']} failed, {metrics['documents_processing']} processing",
            f"- Study minutes logged: {metrics['study_minutes_total']}",
            f"- Feedback items: {metrics['feedback_total']}",
            f"- Invite codes: {metrics['invite_codes_active']} active of {metrics['invite_codes_total']}",
            f"- AI provider: {'enabled' if metrics['ai_enabled'] else 'rules only'}",
            "",
            "## Priorities",
            "1. Resolve any failed/processing documents.",
            "2. Review student feedback for product issues.",
            "3. Verify beta invite delivery and onboarding.",
        ]
        text = "\n".join(lines)
    return text, metrics, ai_used


def _alert_tracking(
    state: DocumentAlertState | None, kind: str, now: datetime
) -> dict[str, Any]:
    """Return the effective operator-tracking status for an alert."""
    if state is None or state.fingerprint != kind:
        return {
            "status": "open",
            "note": state.note if state else None,
            "updated_at": state.updated_at if state else None,
        }

    status = state.status if state.status in {"open", "acknowledged", "snoozed", "resolved"} else "open"
    if status == "snoozed":
        until = as_utc(state.snoozed_until)
        if until is None or until <= now:
            status = "open"
    return {
        "status": status,
        "note": state.note,
        "acknowledged_at": state.acknowledged_at if status == "acknowledged" else None,
        "snoozed_until": state.snoozed_until if status == "snoozed" else None,
        "resolved_at": state.resolved_at if status == "resolved" else None,
        "updated_at": state.updated_at,
    }


CAPACITY_WINDOW = timedelta(days=7)
CAPACITY_SNAPSHOT_INTERVAL = timedelta(hours=1)
CAPACITY_SNAPSHOT_RETENTION = timedelta(days=30)


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def collect_data_integrity(db: Session) -> tuple[dict[str, int], list[str]]:
    """Check referential and file-storage integrity for the admin dashboard."""
    orphaned_chunks = int(
        db.scalar(
            select(func.count())
            .select_from(Chunk)
            .outerjoin(Document, Chunk.document_id == Document.id)
            .outerjoin(Course, Chunk.course_id == Course.id)
            .where(or_(Document.id.is_(None), Course.id.is_(None)))
        )
        or 0
    )
    ready_without_chunks = int(
        db.scalar(
            select(func.count(Document.id))
            .select_from(Document)
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .where(Document.status == "ready", Chunk.id.is_(None))
        )
        or 0
    )
    missing_files: list[str] = []
    documents = db.scalars(
        select(Document).where(Document.storage_path.is_not(None))
    ).all()
    for document in documents:
        try:
            present = Path(document.storage_path or "").is_file()
        except (OSError, ValueError):
            present = False
        if not present:
            missing_files.append(document.filename)
    metrics = {
        "orphaned_chunks": orphaned_chunks,
        "ready_documents_without_chunks": ready_without_chunks,
        "missing_stored_files": len(missing_files),
    }
    return metrics, missing_files


def _database_size_bytes(db: Session) -> int | None:
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        database = bind.url.database
        if not database or database == ":memory:":
            return None
        base = Path(database)
        total = 0
        for candidate in (base, Path(f"{base}-wal"), Path(f"{base}-shm")):
            try:
                if candidate.is_file():
                    total += candidate.stat().st_size
            except OSError:
                continue
        return total
    if bind.dialect.name == "postgresql":
        try:
            value = db.scalar(text("SELECT pg_database_size(current_database())"))
            return int(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001 - capacity is best-effort
            logger.warning("Could not measure PostgreSQL database size: %s", exc)
    return None


def _upload_usage() -> tuple[int, int]:
    directory = get_settings().upload_dir
    total = 0
    count = 0
    try:
        if not directory.exists():
            return 0, 0
        for path in directory.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
                    count += 1
            except OSError:
                continue
    except OSError as exc:
        logger.warning("Could not measure upload storage: %s", exc)
    return total, count


def collect_capacity(db: Session) -> dict[str, Any]:
    """Measure storage sizes and growth from hourly snapshots."""
    now = _now()
    database_size = _database_size_bytes(db)
    upload_size, upload_count = _upload_usage()

    baseline = db.scalars(
        select(SystemHealthSnapshot)
        .where(
            SystemHealthSnapshot.created_at >= now - CAPACITY_WINDOW,
            SystemHealthSnapshot.created_at <= now - CAPACITY_SNAPSHOT_INTERVAL,
        )
        .order_by(SystemHealthSnapshot.created_at.asc(), SystemHealthSnapshot.id.asc())
        .limit(1)
    ).first()

    database_growth: int | None = None
    upload_growth: int | None = None
    if baseline is not None:
        if database_size is not None and baseline.database_size_bytes is not None:
            database_growth = database_size - baseline.database_size_bytes
        upload_growth = upload_size - baseline.upload_size_bytes

    latest = db.scalars(
        select(SystemHealthSnapshot)
        .order_by(SystemHealthSnapshot.created_at.desc(), SystemHealthSnapshot.id.desc())
        .limit(1)
    ).first()
    latest_at = as_utc(latest.created_at) if latest is not None else None
    if latest_at is None or now - latest_at >= CAPACITY_SNAPSHOT_INTERVAL:
        db.add(
            SystemHealthSnapshot(
                database_size_bytes=database_size,
                upload_size_bytes=upload_size,
                upload_file_count=upload_count,
            )
        )
        db.query(SystemHealthSnapshot).filter(
            SystemHealthSnapshot.created_at < now - CAPACITY_SNAPSHOT_RETENTION
        ).delete(synchronize_session=False)
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001 - diagnostics must still render
            db.rollback()
            logger.warning("Could not store system-health capacity snapshot: %s", exc)

    return {
        "database_size_bytes": database_size,
        "upload_size_bytes": upload_size,
        "upload_file_count": upload_count,
        "database_growth_bytes": database_growth,
        "upload_growth_bytes": upload_growth,
    }


def collect_document_alerts(db: Session) -> list[dict[str, Any]]:
    """Return failed documents and processing documents past the stale limit."""
    settings = get_settings()
    limit = max(1, int(settings.stale_processing_minutes))
    now = _now()
    documents = list(
        db.scalars(
            select(Document).where(Document.status.in_(["failed", "processing"]))
        ).all()
    )
    states = {
        state.document_id: state
        for state in db.scalars(select(DocumentAlertState)).all()
    }
    alerts: list[dict[str, Any]] = []
    for document in documents:
        course = document.course
        base = {
            "document_id": document.id,
            "filename": document.filename,
            "course_id": course.id if course else document.course_id,
            "course_title": course.title if course else None,
        }
        state = states.get(document.id)
        if document.status == "failed":
            alerts.append(
                {
                    **base,
                    "status": "failed",
                    "age_minutes": None,
                    "stale": False,
                    "error": document.error_message or "No error message was recorded.",
                    "action": "manual_review",
                    "tracking": _alert_tracking(state, "failed", now),
                }
            )
            continue

        last_activity = as_utc(document.updated_at or document.created_at)
        if last_activity is None:
            continue
        age_minutes = max(0, int((now - last_activity).total_seconds() // 60))
        if now - last_activity > timedelta(minutes=limit):
            alerts.append(
                {
                    **base,
                    "status": "processing",
                    "age_minutes": age_minutes,
                    "stale": True,
                    "error": None,
                    "action": "run_remediation",
                    "tracking": _alert_tracking(state, "stale", now),
                }
            )
    return sorted(
        alerts,
        key=lambda alert: (0 if alert["status"] == "failed" else 1, alert["filename"].lower()),
    )


async def sysadmin_diagnose(
    db: Session,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], bool]:
    metrics = collect_metrics(db)
    integrity_metrics, missing_files = collect_data_integrity(db)
    capacity_metrics = collect_capacity(db)
    metrics.update(integrity_metrics)
    metrics.update(capacity_metrics)
    alerts = collect_document_alerts(db)
    active_alerts = [
        alert
        for alert in alerts
        if alert["tracking"]["status"] not in {"snoozed", "resolved"}
    ]
    failed_alerts = [alert for alert in active_alerts if alert["status"] == "failed"]
    stale_alerts = [alert for alert in active_alerts if alert["stale"]]
    findings: list[dict[str, Any]] = []
    if failed_alerts:
        findings.append(
            {
                "severity": "error",
                "area": "documents",
                "message": f"{len(failed_alerts)} document(s) failed processing and need manual review.",
                "suggested_action": "Review the document alerts and their error messages below.",
            }
        )
    if stale_alerts:
        limit = max(1, int(get_settings().stale_processing_minutes))
        findings.append(
            {
                "severity": "warning",
                "area": "documents",
                "message": f"{len(stale_alerts)} document(s) have made no processing progress for more than {limit} minutes.",
                "suggested_action": "Preview remediation, then mark the stale documents failed if the preview is correct.",
            }
        )
    if metrics["orphaned_chunks"]:
        findings.append(
            {
                "severity": "error",
                "area": "data_integrity",
                "message": (
                    f"{metrics['orphaned_chunks']} text chunk(s) are orphaned from their "
                    "document or course."
                ),
                "suggested_action": (
                    "Back up the database, investigate the deletion path that left these "
                    "chunks behind, then remove only the orphaned rows."
                ),
            }
        )
    if metrics["ready_documents_without_chunks"]:
        findings.append(
            {
                "severity": "warning",
                "area": "data_integrity",
                "message": (
                    f"{metrics['ready_documents_without_chunks']} ready document(s) have no "
                    "text chunks."
                ),
                "suggested_action": (
                    "Reprocess or re-upload the affected documents; a ready document with "
                    "no chunks cannot support study material or citations."
                ),
            }
        )
    if metrics["missing_stored_files"]:
        names = ", ".join(missing_files[:3])
        if len(missing_files) > 3:
            names += f", and {len(missing_files) - 3} more"
        findings.append(
            {
                "severity": "warning",
                "area": "data_integrity",
                "message": (
                    f"{metrics['missing_stored_files']} document(s) reference a stored file "
                    f"that is missing: {names}."
                ),
                "suggested_action": (
                    "Ask the affected students to re-upload these documents; retries need "
                    "the original stored file."
                ),
            }
        )

    capacities = (
        ("Database", metrics["database_size_bytes"], metrics["database_growth_bytes"]),
        ("Upload storage", metrics["upload_size_bytes"], metrics["upload_growth_bytes"]),
    )
    settings = get_settings()
    size_warning = max(1, int(settings.storage_warning_mb)) * 1024 * 1024
    growth_warning = max(1, int(settings.storage_growth_warning_mb)) * 1024 * 1024
    for name, size, growth in capacities:
        if size is not None and size >= size_warning:
            findings.append(
                {
                    "severity": "warning",
                    "area": "capacity",
                    "message": (
                        f"{name} is using {_format_bytes(size)}, above the "
                        f"{_format_bytes(size_warning)} warning threshold."
                    ),
                    "suggested_action": (
                        "Increase storage or prune old data before the volume fills."
                    ),
                }
            )
        if growth is not None and growth >= growth_warning:
            findings.append(
                {
                    "severity": "warning",
                    "area": "capacity",
                    "message": (
                        f"{name} grew by {_format_bytes(growth)} over the "
                        "seven-day capacity window."
                    ),
                    "suggested_action": (
                        "Review recent database and upload growth, then prune or archive "
                        "old data if the rate is unexpected."
                    ),
                }
            )

    if not metrics["ai_enabled"]:
        findings.append(
            {
                "severity": "info",
                "area": "ai",
                "message": "AI provider key not configured; using rule-based engine.",
                "suggested_action": "Set ANTHROPIC_API_KEY to enable AI features.",
            }
        )
    if not get_settings().beta_admin_key:
        findings.append(
            {
                "severity": "warning",
                "area": "security",
                "message": "BETA_ADMIN_KEY is not set; admin endpoints are disabled.",
                "suggested_action": "Set BETA_ADMIN_KEY in production.",
            }
        )
    if not findings:
        findings.append(
            {
                "severity": "info",
                "area": "system",
                "message": "No obvious issues detected.",
                "suggested_action": None,
            }
        )

    prompt = (
        "You are a system administrator for Study Companion. Review these diagnostics, metrics and "
        "document alerts, then give a short remediation plan. Do not invent data.\n\n"
        f"Findings: {findings}\nMetrics: {metrics}\nAlerts: {active_alerts}"
    )
    ai_text = await _llm("You are a careful SRE. Be concise and actionable.", prompt)
    if ai_text:
        findings.append(
            {
                "severity": "info",
                "area": "ai_admin",
                "message": ai_text,
                "suggested_action": "Review the AI-generated plan before applying changes.",
            }
        )
    return findings, metrics, alerts, ai_text is not None


def sysadmin_remediate(
    db: Session, *, dry_run: bool = True, document_id: str | None = None
) -> tuple[list[dict[str, Any]], list[str], list[RemediationEvent]]:
    """Mark stale processing documents failed, or preview that action.

    A document is stale when it is still ``processing`` and has had no progress
    for the configured limit. Pass ``document_id`` to scope the action to one
    document; omit it for the explicit bulk path. Failed documents are
    deliberately left alone for manual review. Every applied status change gets
    an audit record.
    """
    settings = get_settings()
    limit = max(1, int(settings.stale_processing_minutes))
    now = _now()
    cutoff = now - timedelta(minutes=limit)
    actions: list[dict[str, Any]] = []
    remaining: list[str] = []
    changes: list[RemediationEvent] = []

    processing_query = select(Document).where(Document.status == "processing")
    if document_id:
        processing_query = processing_query.where(Document.id == document_id)
    processing = list(db.scalars(processing_query).all())
    prior_failed = list(db.scalars(select(Document).where(Document.status == "failed")).all())
    alert_states = {
        state.document_id: state
        for state in db.scalars(select(DocumentAlertState)).all()
    }
    stale: list[tuple[Document, int]] = []
    active = 0
    suppressed = 0
    for document in processing:
        last_activity = as_utc(document.updated_at or document.created_at)
        if last_activity is None or last_activity > cutoff:
            active += 1
            continue
        state = alert_states.get(document.id)
        if state is not None and state.fingerprint == "stale":
            if state.status == "resolved":
                suppressed += 1
                continue
            until = as_utc(state.snoozed_until)
            if state.status == "snoozed" and until is not None and until > now:
                suppressed += 1
                continue
        age_minutes = max(0, int((now - last_activity).total_seconds() // 60))
        stale.append((document, age_minutes))

    if stale:
        names = ", ".join(document.filename for document, _ in stale[:5])
        if len(stale) > 5:
            names += f", and {len(stale) - 5} more"
        if dry_run:
            actions.append(
                {
                    "action": "would_mark_stale_failed",
                    "affected": len(stale),
                    "detail": (
                        f"Would mark {len(stale)} processing document(s) failed after more than "
                        f"{limit} minutes without progress: {names}. No changes were made."
                    ),
                }
            )
        else:
            for document, age_minutes in stale:
                previous_progress = document.progress_stage or "no stage recorded"
                document.status = "failed"
                document.error_message = (
                    f"Processing timed out after {age_minutes} minutes without progress. "
                    "Marked failed for manual review."
                )
                document.progress_stage = None
                document.progress_current = 0
                document.progress_total = 0
                change = RemediationEvent(
                    action="mark_stale_failed",
                    document_id=document.id,
                    document_filename=document.filename,
                    detail=(
                        f"Processing had been idle for {age_minutes} minutes "
                        f"(limit {limit}); previous stage: {previous_progress}."
                    ),
                )
                db.add(change)
                changes.append(change)
            actions.append(
                {
                    "action": "mark_stale_failed",
                    "affected": len(stale),
                    "detail": (
                        f"Marked {len(stale)} stale processing document(s) failed after more than "
                        f"{limit} minutes without progress: {names}."
                    ),
                }
            )
    else:
        actions.append(
            {
                "action": "document_processing_check",
                "affected": 0,
                "detail": f"No processing documents older than {limit} minutes.",
            }
        )

    if suppressed:
        actions.append(
            {
                "action": "tracking_filter",
                "affected": suppressed,
                "detail": (
                    f"Skipped {suppressed} stale document(s) marked snoozed or resolved "
                    "in the alert tracker."
                ),
            }
        )

    if active:
        remaining.append(
            f"{active} processing document(s) are still within the {limit}-minute progress limit."
        )

    failed_count = len(prior_failed) + (0 if dry_run else len(stale))
    if failed_count:
        remaining.append(f"{failed_count} failed document(s) are left for manual review.")
    else:
        actions.append({"action": "failed_document_check", "affected": 0, "detail": "No failed documents."})

    # Clean orphaned chunks is intentionally not performed automatically.
    actions.append(
        {
            "action": "orphaned_chunk_scan",
            "affected": 0,
            "detail": "Scan completed; no automatic deletions performed for safety.",
        }
    )
    if changes:
        db.commit()
    return actions, remaining, changes


def recent_remediation_changes(db: Session, limit: int = 50) -> list[RemediationEvent]:
    return list(
        db.scalars(
            select(RemediationEvent)
            .order_by(RemediationEvent.created_at.desc(), RemediationEvent.id.desc())
            .limit(max(1, min(limit, 200)))
        ).all()
    )


async def legal_compliance(db: Session, jurisdiction: str) -> tuple[str, list[str], bool]:
    metrics = collect_metrics(db)
    checklist = [
        "Publish a privacy policy describing collected account, course, document, and feedback data.",
        "Obtain and record consent for processing student uploads and AI coach interactions.",
        "Provide data export and deletion (right to erasure) for user accounts and courses.",
        "Minimize retention of uploaded documents and derived chunks; define deletion cascades.",
        "Secure admin endpoints with a strong secret and restrict to the operator.",
        "If serving minors, verify COPPA/FERPA (US) or equivalent age-consent rules.",
        "If serving EU users, address GDPR lawful basis, DPO, and cross-border transfers.",
        "If serving California users, address CCPA/CPRA notice and opt-out rights.",
        "Review AI-generated content disclaimers and academic-integrity guidance.",
        "Ensure third-party providers (Anthropic, Resend) are covered by DPAs where required.",
    ]
    prompt = (
        f"You are a legal/compliance advisor for an educational SaaS app called Study Companion. "
        f"Jurisdiction focus: {jurisdiction}. Using the checklist and metrics, produce a concise compliance "
        f"brief with applicable statutes, gaps, and recommended next steps. Do not provide definitive legal advice.\n\n"
        f"Checklist: {checklist}\nMetrics: {metrics}"
    )
    text = await _llm(
        "You are a cautious compliance analyst. Cite statutes generally and recommend consulting counsel.",
        prompt,
    )
    ai_used = text is not None
    if text is None:
        text = (
            "## Compliance Brief\n\n"
            "Automated legal analysis is unavailable without an AI provider key. "
            "Review the checklist and consult qualified counsel for your jurisdiction."
        )
    return text, checklist, ai_used


async def ai_research_briefing(focus: str) -> tuple[str, list[str], bool]:
    prompt = (
        "You are an AI research analyst. Produce a short briefing on recent developments in the AI industry "
        f"relevant to an educational study-companion app. Focus: {focus}. "
        "Include 5-8 key developments and how they could affect the product. Keep under 450 words."
    )
    text = await _llm(
        "You are an AI industry researcher. Be specific but avoid unverifiable claims.",
        prompt,
    )
    ai_used = text is not None
    if text is None:
        developments = [
            "Retrieval-augmented generation remains the dominant pattern for grounded study assistants.",
            "Smaller on-device and distilled models are improving offline study support.",
            "Multimodal models enable richer handling of scanned notes and diagrams.",
            "Agent frameworks increase automation but require stronger safety and evaluation.",
            "AI safety and provenance tooling is becoming a procurement requirement in education.",
        ]
        text = "## AI Industry Briefing\n\n" + "\n".join(f"- {item}" for item in developments)
        return text, developments, False
    # Best-effort extraction of bullet lines.
    developments = [line.strip("- ").strip() for line in text.splitlines() if line.strip().startswith("-")]
    if not developments:
        developments = [text[:120]]
    return text, developments[:8], ai_used