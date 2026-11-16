"""Developer/admin-only executive agents.

All endpoints require the ``X-Admin-Key`` header and are never intended for
student-facing use.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Course, Document, DocumentAlertState, RemediationEvent, as_utc
from ..schemas import (
    AIResearchResponse,
    ComplianceResponse,
    DiagnosticFinding,
    DiagnosticsResponse,
    DocumentAlert,
    DocumentAlertActionRequest,
    DocumentAlertTracking,
    DocumentDeleteResponse,
    DocumentRetryResponse,
    ExecutiveReportResponse,
    RemediationAction,
    RemediationCandidate,
    RemediationChange,
    RemediationRequest,
    RemediationResponse,
)
from .admin import _require_admin
from .documents import _process_upload
from ..services.topic_service import rebuild_course_topics
from ..services.executive_agents import (
    _format_bytes,
    ai_research_briefing,
    ceo_report,
    collect_document_alerts,
    collect_metrics,
    legal_compliance,
    recent_remediation_changes,
    sysadmin_diagnose,
    sysadmin_remediate,
)

router = APIRouter(prefix="/admin/agents", tags=["admin-agents"])
logger = logging.getLogger("study_companion.admin_agents")


def _md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").strip()


def _report_metric_label(key: str) -> str:
    labels = {
        "ai_enabled": "AI provider",
        "database": "Database engine",
        "beta_invite_only": "Invite-only beta",
        "allow_anonymous_sessions": "Guest sessions",
    }
    if key in labels:
        return labels[key]
    return key.removesuffix("_bytes").replace("_", " ").strip().title()


def _report_metric_value(key: str, value: Any) -> str:
    if key.endswith("_bytes"):
        return _format_bytes(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _markdown_report(
    diagnostics: DiagnosticsResponse,
    changes: list[RemediationChange],
    history_limit: int,
) -> str:
    lines = [
        "# Study Companion System Health Report",
        "",
        f"- Generated: {diagnostics.generated_at.isoformat()}",
        f"- AI-assisted plan: {'Yes' if diagnostics.ai_used else 'No'}",
        f"- Remediation history limit: {history_limit} most recent record(s)",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key, value in diagnostics.metrics.items():
        lines.append(f"| {_md_cell(_report_metric_label(key))} | {_md_cell(_report_metric_value(key, value))} |")

    lines.extend(["", "## Findings", ""])
    if not diagnostics.findings:
        lines.append("No findings were returned.")
    for index, finding in enumerate(diagnostics.findings, start=1):
        lines.extend(
            [
                f"### {index}. {finding.severity.title()} · {_md_cell(finding.area.replace('_', ' ').title())}",
                "",
                finding.message,
                "",
            ]
        )
        if finding.suggested_action:
            lines.extend([f"Suggested action: {finding.suggested_action}", ""])

    lines.extend(["## Document Alerts", ""])
    if not diagnostics.alerts:
        lines.append("No document alerts.")
    for index, alert in enumerate(diagnostics.alerts, start=1):
        tracking = alert.tracking
        lines.extend(
            [
                f"### {index}. {_md_cell(alert.filename)}",
                "",
                f"- Document ID: `{alert.document_id}`",
                f"- Status: {alert.status}{' (stale)' if alert.stale else ''}",
                f"- Course: {_md_cell(alert.course_title or alert.course_id or '—')}",
                f"- Idle: {f'{alert.age_minutes} min' if alert.age_minutes is not None else '—'}",
                f"- Alert action: {alert.action}",
                f"- Error: {_md_cell(alert.error or '—')}",
                f"- Tracking: {tracking.status}",
                f"- Tracking updated: {tracking.updated_at.isoformat() if tracking.updated_at else '—'}",
            ]
        )
        if tracking.acknowledged_at:
            lines.append(f"- Acknowledged: {tracking.acknowledged_at.isoformat()}")
        if tracking.snoozed_until:
            lines.append(f"- Snoozed until: {tracking.snoozed_until.isoformat()}")
        if tracking.resolved_at:
            lines.append(f"- Resolved: {tracking.resolved_at.isoformat()}")
        if tracking.note:
            lines.append(f"- Internal note: {_md_cell(tracking.note)}")
        lines.append("")

    lines.extend(["## Remediation History", ""])
    if not changes:
        lines.append("No remediation history recorded.")
    else:
        lines.extend(
            [
                "| Timestamp | Action | Document | Detail |",
                "| --- | --- | --- | --- |",
            ]
        )
        for change in changes:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(change.created_at.isoformat()),
                        _md_cell(change.action),
                        _md_cell(change.document_filename or change.document_id or "—"),
                        _md_cell(change.detail or "—"),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


@router.get("/sysadmin/report")
async def sysadmin_diagnostic_report(
    report_format: Literal["markdown", "json"] = Query(default="markdown", alias="format"),
    history_limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> Response:
    """Download the current system-health report as Markdown or JSON."""
    findings, metrics, alerts, ai_used = await sysadmin_diagnose(db)
    diagnostics = DiagnosticsResponse(
        generated_at=datetime.now(timezone.utc),
        findings=[DiagnosticFinding(**finding) for finding in findings],
        metrics=metrics,
        alerts=[DocumentAlert(**alert) for alert in alerts],
        ai_used=ai_used,
    )
    changes = [
        RemediationChange.model_validate(change)
        for change in recent_remediation_changes(db, limit=history_limit)
    ]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    if report_format == "markdown":
        content = _markdown_report(diagnostics, changes, history_limit)
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    else:
        payload = diagnostics.model_dump(mode="json")
        payload["document_alerts"] = payload.pop("alerts")
        payload["report_type"] = "study_companion_system_health"
        payload["stale_after_minutes"] = get_settings().stale_processing_minutes
        payload["remediation_history"] = [change.model_dump(mode="json") for change in changes]
        payload["remediation_history_limit"] = history_limit
        content = json.dumps(payload, indent=2, ensure_ascii=False)
        media_type = "application/json; charset=utf-8"
        extension = "json"
    filename = f"study-companion-diagnostics-{timestamp}.{extension}"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/ceo/report", response_model=ExecutiveReportResponse)
async def ceo_executive_report(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> ExecutiveReportResponse:
    report, metrics, ai_used = await ceo_report(db)
    return ExecutiveReportResponse(
        generated_at=datetime.now(timezone.utc),
        report=report,
        metrics=metrics,
        ai_used=ai_used,
    )


@router.get("/sysadmin/diagnostics", response_model=DiagnosticsResponse)
async def sysadmin_diagnostics(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DiagnosticsResponse:
    findings, metrics, alerts, ai_used = await sysadmin_diagnose(db)

    return DiagnosticsResponse(
        generated_at=datetime.now(timezone.utc),
        findings=[DiagnosticFinding(**f) for f in findings],
        metrics=metrics,
        alerts=[DocumentAlert(**alert) for alert in alerts],
        ai_used=ai_used,
    )


@router.post("/sysadmin/remediate", response_model=RemediationResponse)
def sysadmin_remediate_endpoint(
    payload: RemediationRequest | None = Body(default=None),
    dry_run: bool = Query(
        default=True,
        description="Preview stale-document changes without applying them.",
    ),
    document_id: str | None = Query(
        default=None,
        max_length=48,
        description="Scope remediation to one document; omit for the bulk path.",
    ),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> RemediationResponse:
    if document_id and payload and payload.document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose either one document or a selected list, not both.",
        )
    if document_id:
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if document.status != "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That document is no longer processing.",
            )
    selected_ids = payload.document_ids if payload and payload.document_ids else None
    actions, remaining, changes, candidates = sysadmin_remediate(
        db, dry_run=dry_run, document_id=document_id, document_ids=selected_ids
    )
    return RemediationResponse(
        generated_at=datetime.now(timezone.utc),
        dry_run=dry_run,
        document_id=document_id,
        stale_after_minutes=get_settings().stale_processing_minutes,
        actions=[RemediationAction(**a) for a in actions],
        candidates=[RemediationCandidate(**candidate) for candidate in candidates],
        remaining_issues=remaining,
        changes=[RemediationChange.model_validate(change) for change in changes],
    )


@router.post(
    "/sysadmin/documents/{document_id}/retry", response_model=DocumentRetryResponse
)
def retry_failed_document(
    document_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DocumentRetryResponse:
    """Requeue one failed document from its saved original file."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed documents can be retried.",
        )

    source = Path(document.storage_path) if document.storage_path else None
    if source is None or not source.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The original file is no longer available. Re-upload the document instead.",
        )

    course = db.get(Course, document.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")

    previous_error = (document.error_message or "No error message was recorded.").strip()
    document.status = "processing"
    document.error_message = None
    document.processed_at = None
    document.progress_stage = "queued"
    document.progress_current = 0
    document.progress_total = 0
    document.updated_at = datetime.now(timezone.utc)
    alert_state = db.get(DocumentAlertState, document.id)
    if alert_state is not None:
        alert_state.status = "open"
        alert_state.fingerprint = None
        alert_state.acknowledged_at = None
        alert_state.snoozed_until = None
        alert_state.resolved_at = None
    db.add(
        RemediationEvent(
            action="retry_failed_document",
            document_id=document.id,
            document_filename=document.filename,
            detail=f"Manual retry queued by admin; previous error: {previous_error[:500]}",
        )
    )
    db.commit()

    background.add_task(
        _process_upload,
        document.id,
        course.id,
        document.filename,
        document.content_type,
        source,
    )
    return DocumentRetryResponse(
        generated_at=datetime.now(timezone.utc),
        document_id=document.id,
        filename=document.filename,
        message=f"Retry queued for {document.filename}. Processing has restarted.",
    )


@router.delete(
    "/sysadmin/documents/{document_id}", response_model=DocumentDeleteResponse
)
def delete_failed_document(
    document_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DocumentDeleteResponse:
    """Permanently delete one failed document and its stored original."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed documents can be deleted from this control.",
        )

    course = db.get(Course, document.course_id)
    filename = document.filename
    previous_error = (document.error_message or "No error message was recorded.").strip()
    had_chunks = bool(document.chunks)
    source = Path(document.storage_path) if document.storage_path else None
    source_status = "no stored source"
    if source is not None:
        try:
            source.unlink(missing_ok=True)
            source_status = "source removed" if not source.exists() else "source still present"
        except OSError as exc:
            source_status = "source cleanup failed"
            logger.warning("Could not remove failed document source %s: %s", source, exc)

    db.add(
        RemediationEvent(
            action="delete_failed_document",
            document_id=document.id,
            document_filename=filename,
            detail=(
                f"Manual delete of failed document; {source_status}; "
                f"previous error: {previous_error[:500]}"
            ),
        )
    )
    alert_state = db.get(DocumentAlertState, document.id)
    if alert_state is not None:
        db.delete(alert_state)
    db.delete(document)
    db.flush()
    if had_chunks and course is not None:
        rebuild_course_topics(db, course)
    else:
        db.commit()

    return DocumentDeleteResponse(
        generated_at=datetime.now(timezone.utc),
        document_id=document_id,
        filename=filename,
        message=f"Deleted {filename}. The audit record was kept.",
    )


@router.patch(
    "/sysadmin/documents/{document_id}/alert", response_model=DocumentAlertTracking
)
def update_document_alert(
    document_id: str,
    payload: DocumentAlertActionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DocumentAlertTracking:
    """Acknowledge, snooze, resolve, reopen, or annotate a document alert."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    alert = next(
        (
            item
            for item in collect_document_alerts(db)
            if item["document_id"] == document_id
        ),
        None,
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document does not currently have an alert.",
        )
    if payload.action is None and payload.note is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide an action or an internal note.",
        )
    if payload.action == "snooze" and payload.snooze_minutes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A snooze duration is required.",
        )

    kind = "failed" if document.status == "failed" else "stale"
    now = datetime.now(timezone.utc)
    state = db.get(DocumentAlertState, document_id)
    if state is None:
        state = DocumentAlertState(document_id=document_id, status="open")
        db.add(state)
    else:
        snoozed_until = as_utc(state.snoozed_until)
        expired_snooze = state.status == "snoozed" and (
            snoozed_until is None or snoozed_until <= now
        )
        if state.fingerprint != kind or expired_snooze:
            state.status = "open"
            state.acknowledged_at = None
            state.snoozed_until = None
            state.resolved_at = None
    state.fingerprint = kind

    if payload.note is not None:
        state.note = payload.note.strip() or None

    detail = "Internal note updated."
    if payload.action == "acknowledge":
        state.status = "acknowledged"
        state.acknowledged_at = now
        state.snoozed_until = None
        state.resolved_at = None
        detail = "Alert acknowledged."
    elif payload.action == "snooze":
        until = now + timedelta(minutes=int(payload.snooze_minutes or 0))
        state.status = "snoozed"
        state.snoozed_until = until
        state.resolved_at = None
        detail = f"Alert snoozed until {until.isoformat()}."
    elif payload.action == "resolve":
        state.status = "resolved"
        state.resolved_at = now
        state.snoozed_until = None
        detail = "Alert resolved; document status was not changed."
    elif payload.action == "reopen":
        state.status = "open"
        state.acknowledged_at = None
        state.snoozed_until = None
        state.resolved_at = None
        detail = "Alert reopened."

    audit_action = (
        {
            "acknowledge": "acknowledge_document_alert",
            "snooze": "snooze_document_alert",
            "resolve": "resolve_document_alert",
            "reopen": "reopen_document_alert",
            "note": "note_document_alert",
        }[payload.action]
        if payload.action
        else "note_document_alert"
    )
    db.add(
        RemediationEvent(
            action=audit_action,
            document_id=document.id,
            document_filename=document.filename,
            detail=detail,
        )
    )
    db.commit()
    db.refresh(state)

    effective_status = state.status if state.status in {"open", "acknowledged", "snoozed", "resolved"} else "open"
    return DocumentAlertTracking(
        status=effective_status,
        note=state.note,
        acknowledged_at=state.acknowledged_at if effective_status == "acknowledged" else None,
        snoozed_until=state.snoozed_until if effective_status == "snoozed" else None,
        resolved_at=state.resolved_at if effective_status == "resolved" else None,
        updated_at=state.updated_at,
    )


@router.get("/sysadmin/remediation-log", response_model=list[RemediationChange])
def sysadmin_remediation_log(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> list[RemediationChange]:
    return [
        RemediationChange.model_validate(change)
        for change in recent_remediation_changes(db, limit=limit)
    ]


@router.get("/legal/compliance", response_model=ComplianceResponse)
async def legal_compliance_report(
    jurisdiction: str = "general",
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> ComplianceResponse:
    report, checklist, ai_used = await legal_compliance(db, jurisdiction)
    return ComplianceResponse(
        generated_at=datetime.now(timezone.utc),
        jurisdiction=jurisdiction,
        report=report,
        checklist=checklist,
        ai_used=ai_used,
    )


@router.get("/ai-research/briefing", response_model=AIResearchResponse)
async def ai_research_report(
    focus: str = "education and study tools",
    _: None = Depends(_require_admin),
) -> AIResearchResponse:
    briefing, developments, ai_used = await ai_research_briefing(focus)
    return AIResearchResponse(
        generated_at=datetime.now(timezone.utc),
        focus=focus,
        briefing=briefing,
        key_developments=developments,
        ai_used=ai_used,
    )