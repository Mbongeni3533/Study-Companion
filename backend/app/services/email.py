"""Email delivery helpers for Study Companion.

Currently uses Resend's REST API (https://resend.com) for transactional email.
Set RESEND_API_KEY and optionally RESEND_FROM_EMAIL in the environment.
"""

from __future__ import annotations

import html
import logging

import httpx

from ..config import get_settings

logger = logging.getLogger("study_companion.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _send_email(to_email: str, subject: str, text: str, html: str) -> dict:
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    payload = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning("Resend email failed: %s %s", response.status_code, response.text)
            response.raise_for_status()
        return response.json()


def send_invite_email(to_email: str, invite_code: str) -> dict:
    """Send a beta invite code to a student. Returns Resend's response JSON."""
    return _send_email(
        to_email,
        "Your Study Companion beta invite",
        (
            "You've been invited to the Study Companion beta.\n\n"
            f"Your invite code: {invite_code}\n\n"
            "Create your account at the app and enter this code during registration.\n"
        ),
        (
            "<p>You've been invited to the Study Companion beta.</p>"
            f"<p><strong>Your invite code:</strong> <code>{invite_code}</code></p>"
            "<p>Create your account in the app and enter this code during registration.</p>"
        ),
    )


def send_subscription_cancelled_email(to_email: str, settings_url: str) -> dict:
    return _send_email(
        to_email,
        "Your Study Companion subscription was cancelled",
        (
            "Your Study Companion Plus subscription has been cancelled.\n\n"
            "Your account is now on the Free plan. You can reactivate at any time from Settings:\n"
            f"{settings_url}\n\n"
            "If you did not request this change, reply to this email so we can help.\n"
        ),
        (
            "<p>Your Study Companion Plus subscription has been cancelled.</p>"
            "<p>Your account is now on the Free plan. You can reactivate at any time from Settings:</p>"
            f'<p><a href="{settings_url}">Open subscription settings</a></p>'
            "<p>If you did not request this change, reply to this email so we can help.</p>"
        ),
    )


def send_admin_subscription_event_email(
    to_email: str,
    action: str,
    subscriber_name: str,
    subscriber_email: str,
    detail: str,
    admin_url: str,
) -> dict:
    safe_name = html.escape(subscriber_name or "Subscriber")
    safe_email = html.escape(subscriber_email or "no email")
    safe_detail = html.escape(detail)
    safe_action = html.escape(action)
    return _send_email(
        to_email,
        f"Study Companion: {action} - {subscriber_name or 'Subscriber'}",
        (
            f"A subscriber {action}.\n\n"
            f"Name: {subscriber_name or 'Subscriber'}\n"
            f"Email: {subscriber_email or 'no email'}\n"
            f"Detail: {detail}\n\n"
            f"Open the admin dashboard: {admin_url}\n"
        ),
        (
            f"<p>A subscriber {safe_action}.</p>"
            f"<p><strong>Name:</strong> {safe_name}<br>"
            f"<strong>Email:</strong> {safe_email}<br>"
            f"<strong>Detail:</strong> {safe_detail}</p>"
            f'<p><a href="{html.escape(admin_url)}">Open the admin dashboard</a></p>'
        ),
    )


def send_billing_details_updated_email(to_email: str, settings_url: str) -> dict:
    return _send_email(
        to_email,
        "Your Study Companion billing details were updated",
        (
            "The billing details for your Study Companion subscription were updated.\n\n"
            "If you made this change, no action is needed. If you did not, review your billing settings:\n"
            f"{settings_url}\n\n"
            "You can also reply to this email so we can help.\n"
        ),
        (
            "<p>The billing details for your Study Companion subscription were updated.</p>"
            "<p>If you made this change, no action is needed. If you did not, review your billing settings:</p>"
            f'<p><a href="{settings_url}">Open billing settings</a></p>'
            "<p>You can also reply to this email so we can help.</p>"
        ),
    )
