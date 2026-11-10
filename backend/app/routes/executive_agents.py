"""Developer/admin-only executive agents.

All endpoints require the ``X-Admin-Key`` header and are never intended for
student-facing use.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    AIResearchResponse,
    ComplianceResponse,
    DiagnosticsResponse,
    ExecutiveReportResponse,
    RemediationAction,
    RemediationResponse,
)
from .admin import _require_admin
from ..services.executive_agents import (
    ai_research_briefing,
    ceo_report,
    collect_metrics,
    legal_compliance,
    sysadmin_diagnose,
    sysadmin_remediate,
)

router = APIRouter(prefix="/admin/agents", tags=["admin-agents"])


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
    findings, metrics, ai_used = await sysadmin_diagnose(db)
    from ..schemas import DiagnosticFinding

    return DiagnosticsResponse(
        generated_at=datetime.now(timezone.utc),
        findings=[DiagnosticFinding(**f) for f in findings],
        metrics=metrics,
        ai_used=ai_used,
    )


@router.post("/sysadmin/remediate", response_model=RemediationResponse)
def sysadmin_remediate_endpoint(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> RemediationResponse:
    actions, remaining = sysadmin_remediate(db)
    return RemediationResponse(
        generated_at=datetime.now(timezone.utc),
        actions=[RemediationAction(**a) for a in actions],
        remaining_issues=remaining,
    )


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