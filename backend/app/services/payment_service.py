"""Billing hooks (phase 3).

Stripe is optional. Nothing in the core study flow depends on it, so the service
reports configuration status instead of failing when keys are absent.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings

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


@dataclass
class CheckoutResult:
    configured: bool
    url: str | None = None
    message: str = ""


class PaymentService:
    """Thin wrapper around Stripe checkout, disabled unless configured."""

    def __init__(self) -> None:
        settings = get_settings()
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key)

    def plans(self) -> list[dict]:
        return PLANS

    def create_checkout_session(self, *, user_id: str, plan_id: str, success_url: str) -> CheckoutResult:
        if not self.is_configured:
            return CheckoutResult(
                configured=False,
                message="Payments are not configured. Set STRIPE_SECRET_KEY to enable checkout.",
            )
        if plan_id not in {p["id"] for p in PLANS}:
            return CheckoutResult(configured=True, message=f"Unknown plan '{plan_id}'.")
        return CheckoutResult(
            configured=True,
            message="Stripe checkout is configured but the paid tier is not launched yet.",
        )
