"""Operational email alerts for the admin/operator.

This module is deliberately independent of the admin UI: a background sweep
checks document state and system health, then emails only newly-seen issues.
Persisted fingerprints prevent the same failed document, stale job or health
problem from generating an email on every sweep.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import SessionLocal
from ..models import AdminNotificationState
from .email import send_admin_alert_email
from .executive_agents import collect_document_alerts

logger = logging.getLogger("study_companion.admin_notifications")

KINDS = ("failed_document", "stale_processing", "system_health")
MAX_ITEMS_PER_EMAIL = 20
DATABASE_ALERT_COOLDOWN = timedelta(hours=1)

_last_database_alert_at: datetime | None = None
_sweep_lock = threading.Lock()


def _recipients(settings: Settings) -> list[str]:
    return [
        address.strip()
        for address in settings.admin_notification_email.split(",")
        if address.strip()
    ]


def _storage_issue(settings: Settings) -> dict[str, str] | None:
    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.upload_dir / f".admin-healthcheck-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        logger.warning("Admin notification storage check failed: %s", exc)
        return {
            "fingerprint": "system_health:storage",
            "kind": "system_health",
            "title": "Document storage is unavailable",
            "detail": f"The upload directory cannot be written to: {exc.__class__.__name__}.",
        }
    return None


def collect_operational_issues(db: Session, settings: Settings) -> list[dict[str, str]]:
    """Return the current actionable issues that should reach the operator."""
    issues: list[dict[str, str]] = []

    for alert in collect_document_alerts(db):
        if alert.get("tracking", {}).get("status") in {"snoozed", "resolved"}:
            continue
        course = alert.get("course_title") or "Unknown course"
        filename = alert.get("filename") or "Untitled document"
        if alert.get("status") == "failed":
            error = (alert.get("error") or "No error message was recorded.").strip()
            issues.append(
                {
                    "fingerprint": f"document_failed:{alert['document_id']}",
                    "kind": "failed_document",
                    "title": filename,
                    "detail": f"{course} - {error[:500]}",
                }
            )
        elif alert.get("stale"):
            age = alert.get("age_minutes")
            age_text = f"no progress for {age} minutes" if age is not None else "no recent progress"
            issues.append(
                {
                    "fingerprint": f"document_stale:{alert['document_id']}",
                    "kind": "stale_processing",
                    "title": filename,
                    "detail": f"{course} - {age_text}.",
                }
            )

    storage = _storage_issue(settings)
    if storage is not None:
        issues.append(storage)

    if settings.environment.strip().lower() == "production" and not settings.beta_admin_key:
        issues.append(
            {
                "fingerprint": "system_health:admin_key",
                "kind": "system_health",
                "title": "Admin access is not configured",
                "detail": "BETA_ADMIN_KEY is empty, so the admin dashboard and controls are disabled.",
            }
        )

    return issues


def _subject(kind: str, count: int) -> tuple[str, str]:
    if kind == "failed_document":
        noun = "document" if count == 1 else "documents"
        return (
            f"Study Companion: {count} failed {noun}",
            "Document processing failures",
        )
    if kind == "stale_processing":
        noun = "document" if count == 1 else "documents"
        return (
            f"Study Companion: {count} stale processing {noun}",
            "Stale processing documents",
        )
    noun = "problem" if count == 1 else "problems"
    return (f"Study Companion: {count} system health {noun}", "System health problems")


def _send_group(
    settings: Settings,
    recipients: list[str],
    kind: str,
    issues: list[dict[str, str]],
) -> bool:
    subject, heading = _subject(kind, len(issues))
    shown = issues[:MAX_ITEMS_PER_EMAIL]
    hidden = len(issues) - len(shown)
    intro = (
        "The background health check found the following issue(s). "
        "Open the dashboard to retry, remediate, or review them."
    )
    if hidden:
        intro += f" Showing the first {len(shown)} of {len(issues)} issues."
    items = [{"title": issue["title"], "detail": issue["detail"]} for issue in shown]
    admin_url = f"{settings.public_app_url.rstrip('/')}/admin"
    sent = 0
    for recipient in recipients:
        try:
            send_admin_alert_email(
                recipient,
                subject,
                heading,
                intro,
                items,
                admin_url,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 - provider/network failure
            logger.warning("Admin document alert to %s failed: %s", recipient, exc)
    return sent > 0


def _notify_database_failure(
    settings: Settings, recipients: list[str], error: Exception
) -> None:
    """Email a database outage on a cooldown; it cannot use DB dedupe state."""
    global _last_database_alert_at
    now = datetime.now(timezone.utc)
    if _last_database_alert_at is not None:
        if now - _last_database_alert_at < DATABASE_ALERT_COOLDOWN:
            return
    issue = {
        "title": "Database health check failed",
        "detail": (
            f"The app cannot query its database ({error.__class__.__name__}). "
            "Check DATABASE_URL and database availability."
        ),
    }
    if _send_group(settings, recipients, "system_health", [issue]):
        _last_database_alert_at = now


def run_admin_notification_sweep() -> int:
    """Check for operational issues and email newly-seen ones.

    Returns the number of issues covered by successful emails. Existing active
    issues are skipped until they resolve; resolved rows are reactivated if the
    same issue returns later.
    """
    settings = get_settings()
    recipients = _recipients(settings)
    if not recipients:
        return 0

    # The startup loop and any future manual trigger must not race inside one
    # process. A database uniqueness check also protects cross-process races.
    with _sweep_lock:
        return _run_sweep(settings, recipients)


def _run_sweep(settings: Settings, recipients: list[str]) -> int:
    db = SessionLocal()
    try:
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - surface a database outage too
            db.rollback()
            _notify_database_failure(settings, recipients, exc)
            return 0

        issues = collect_operational_issues(db, settings)
        now = datetime.now(timezone.utc)
        states = list(
            db.scalars(
                select(AdminNotificationState).where(
                    AdminNotificationState.resolved_at.is_(None)
                )
            ).all()
        )
        active = {state.fingerprint for state in states}
        fresh = [issue for issue in issues if issue["fingerprint"] not in active]

        notified = 0
        for kind in KINDS:
            group = [issue for issue in fresh if issue["kind"] == kind]
            if not group or not _send_group(settings, recipients, kind, group):
                continue
            for issue in group:
                state = db.get(AdminNotificationState, issue["fingerprint"])
                if state is None:
                    state = AdminNotificationState(
                        fingerprint=issue["fingerprint"],
                        kind=kind,
                        first_seen_at=now,
                        last_notified_at=now,
                    )
                    db.add(state)
                else:
                    state.kind = kind
                    state.first_seen_at = now
                    state.last_notified_at = now
                    state.resolved_at = None
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                logger.info(
                    "Admin notification state was already recorded by another sweep"
                )
                continue
            notified += len(group)

        current = {issue["fingerprint"] for issue in issues}
        resolved = False
        for state in states:
            if state.fingerprint not in current and state.resolved_at is None:
                state.resolved_at = now
                resolved = True
        if resolved:
            db.commit()
        return notified
    finally:
        db.close()
