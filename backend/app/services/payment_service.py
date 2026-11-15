"""Billing hooks for the optional paid subscription.

Stripe Checkout is used when a secret key and price ID are configured. The app
still boots and remains usable without them; during that period registered beta
users can activate their own subscription from Settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger("study_companion.payments")

PLANS: list[dict] = [
    {
        "id": "free",
        "name": "Free",
        "price_cents": 0,
        "interval": None,
        "features": [
            "3 courses",
            "Document uploads up to 10 MB",
            "Rule-based study coach",
            "Daily task plans",
        ],
    },
    {
        "id": "plus",
        "name": "Plus",
        "price_cents": 4900,
        "interval": "month",
        "features": [
            "Unlimited courses",
            "AI study coach",
            "Exam readiness tracking",
            "Offline notes",
        ],
    },
    {
        "id": "campus",
        "name": "Campus",
        "price_cents": 0,
        "interval": "contact",
        "features": [
            "Institution licensing",
            "Lecturer dashboards",
            "SSO and roster sync",
            "Priority support",
        ],
    },
]

PLUS_PLAN = next(plan for plan in PLANS if plan["id"] == "plus")


@dataclass
class CheckoutResult:
    configured: bool
    url: str | None = None
    message: str = ""


class PaymentService:
    """Thin wrapper around Stripe Checkout, disabled unless configured."""

    def __init__(self) -> None:
        settings = get_settings()
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret
        self.price_id = settings.stripe_price_id

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key and self.price_id)

    def plans(self) -> list[dict]:
        return PLANS

    @property
    def price_label(self) -> str:
        return f"${PLUS_PLAN['price_cents'] / 100:.0f} / {PLUS_PLAN['interval']}"

    def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str | None,
        base_url: str,
    ) -> CheckoutResult:
        if not self.is_configured:
            return CheckoutResult(
                configured=False,
                message="Billing is not configured. Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID to enable checkout.",
            )

        base = base_url.rstrip("/")
        payload = {
            "mode": "subscription",
            "success_url": f"{base}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base}/?billing=cancelled",
            "client_reference_id": user_id,
            "line_items[0][price]": self.price_id,
            "line_items[0][quantity]": 1,
            "metadata[user_id]": user_id,
            "subscription_data[metadata][user_id]": user_id,
        }
        if email:
            payload["customer_email"] = email

        try:
            response = httpx.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(self.secret_key or "", ""),
                timeout=20,
            )
        except httpx.HTTPError as exc:
            logger.warning("Stripe checkout request failed: %s", exc)
            return CheckoutResult(configured=True, message="Could not reach the payment provider.")

        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("error", {}).get("message") if isinstance(data, dict) else None
            logger.warning("Stripe checkout rejected: %s", message or response.status_code)
            return CheckoutResult(
                configured=True,
                message=message or "The payment provider rejected the checkout request.",
            )
        url = data.get("url") if isinstance(data, dict) else None
        if not url:
            return CheckoutResult(configured=True, message="Stripe did not return a checkout URL.")
        return CheckoutResult(configured=True, url=url)

    def retrieve_checkout_session(self, session_id: str) -> tuple[dict[str, Any] | None, str]:
        if not self.is_configured:
            return None, "Billing is not configured."
        try:
            response = httpx.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                auth=(self.secret_key or "", ""),
                timeout=20,
            )
        except httpx.HTTPError as exc:
            logger.warning("Stripe session lookup failed: %s", exc)
            return None, "Could not reach the payment provider."

        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("error", {}).get("message") if isinstance(data, dict) else None
            return None, message or "Could not verify the checkout session."
        return data, ""
