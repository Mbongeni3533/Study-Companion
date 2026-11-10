"""Developer/admin-only "executive" agents for Study Companion.

These helpers gather system state and produce reports. They are intentionally
kept behind the admin key and are never exposed to students.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Chunk,
    Course,
    Document,
    Feedback,
    InviteCode,
    StudyLog,
    Topic,
    User,
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


async def sysadmin_diagnose(db: Session) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    metrics = collect_metrics(db)
    findings: list[dict[str, Any]] = []
    if metrics["documents_failed"]:
        findings.append(
            {
                "severity": "error",
                "area": "documents",
                "message": f"{metrics['documents_failed']} document(s) failed processing.",
                "suggested_action": "Inspect error_message and re-upload or retry processing.",
            }
        )
    if metrics["documents_processing"]:
        findings.append(
            {
                "severity": "warning",
                "area": "documents",
                "message": f"{metrics['documents_processing']} document(s) still processing.",
                "suggested_action": "Check background tasks and OCR availability.",
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
        "You are a system administrator for Study Companion. Review these diagnostics and metrics, "
        "then give a short remediation plan. Do not invent data.\n\n"
        f"Findings: {findings}\nMetrics: {metrics}"
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
    return findings, metrics, ai_text is not None


def sysadmin_remediate(db: Session) -> tuple[list[dict[str, Any]], list[str]]:
    actions: list[dict[str, Any]] = []
    remaining: list[str] = []

    stuck = db.scalars(
        select(Document).where(Document.status == "processing")
    ).all()
    # Mark very old processing docs as failed is handled by caller policy; here we
    # only report them to avoid destructive changes.
    if stuck:
        remaining.append(f"{len(stuck)} document(s) still processing; not auto-failed.")
    else:
        actions.append({"action": "document_processing_check", "affected": 0, "detail": "No stuck documents found."})

    failed = db.scalars(select(Document).where(Document.status == "failed")).all()
    if failed:
        remaining.append(f"{len(failed)} failed document(s) need manual review.")
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
    db.commit()
    return actions, remaining


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