"""Email delivery helpers for Study Companion.

Currently uses Resend's REST API (https://resend.com) for transactional email.
Set RESEND_API_KEY and optionally RESEND_FROM_EMAIL in the environment.
"""

from __future__ import annotations

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger("study_companion.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_invite_email(to_email: str, invite_code: str) -> dict:
    """Send a beta invite code to a student. Returns Resend's response JSON."""
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    payload = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": "Your Study Companion beta invite",
        "text": (
            f"You've been invited to the Study Companion beta.\n\n"
            f"Your invite code: {invite_code}\n\n"
            f"Create your account at the app and enter this code during registration.\n"
        ),
        "html": (
            "<p>You've been invited to the Study Companion beta.</p>"
            f"<p><strong>Your invite code:</strong> <code>{invite_code}</code></p>"
            "<p>Create your account in the app and enter this code during registration.</p>"
        ),
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning("Resend invite failed: %s %s", response.status_code, response.text)
            response.raise_for_status()
        return response.json()