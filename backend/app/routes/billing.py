"""Self-serve subscription activation and Stripe billing callbacks."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import BillingEvent, User
from ..schemas import (
    BillingStatusResponse,
    CheckoutConfirmRequest,
    CheckoutSessionResponse,
    UserResponse,
)
from ..services.payment_service import PaymentService
from ..services.subscriber_agent import record_subscriber_event
from ..utils.deps import get_current_user

logger = logging.getLogger("study_companion.billing")

router = APIRouter(prefix="/billing", tags=["billing"])


def _service() -> PaymentService:
    return PaymentService()


def _activate_user(
    db: Session,
    user: User,
    detail: str,
    *,
    customer_id: str | None = None,
    subscription_id: str | None = None,
) -> None:
    already_active = user.subscription_status == "subscribed" and user.subscription_tier == "plus"
    user.subscription_status = "subscribed"
    user.subscription_tier = "plus"
    if customer_id:
        user.stripe_customer_id = customer_id
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    if not already_active:
        record_subscriber_event(db, user, "subscribed", "subscribed", detail)


def _deactivate_user(db: Session, user: User, detail: str) -> None:
    already_pending = user.subscription_status == "pending" and user.subscription_tier == "free"
    user.subscription_status = "pending"
    user.subscription_tier = "free"
    if not already_pending:
        record_subscriber_event(db, user, "subscription_ended", "pending", detail)


def _verify_stripe_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    if not signature_header:
        return False
    parts: dict[str, str] = {}
    for item in signature_header.split(","):
        key, _, value = item.partition("=")
        if key:
            parts[key.strip()] = value.strip()
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return secrets.compare_digest(expected, signature)


def _subscription_user(db: Session, obj: dict[str, Any]) -> User | None:
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        user_id = obj.get("client_reference_id")
    if user_id:
        user = db.get(User, user_id)
        if user is not None:
            return user
    subscription_id = obj.get("subscription") or obj.get("id")
    if subscription_id:
        return db.scalar(select(User).where(User.stripe_subscription_id == subscription_id))
    return None


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(user: User = Depends(get_current_user)) -> BillingStatusResponse:
    service = _service()
    settings = get_settings()
    return BillingStatusResponse(
        subscription_status=user.subscription_status,
        subscription_tier=user.subscription_tier,
        checkout_configured=service.is_configured,
        activation_available=(
            settings.allow_beta_self_activation
            and not service.is_configured
            and user.subscription_status == "pending"
        ),
        portal_available=(
            user.subscription_status == "subscribed"
            and bool(service.secret_key and user.stripe_customer_id)
        ),
        cancel_available=(
            user.subscription_status == "subscribed"
            and not user.stripe_subscription_id
        ),
        price_label=service.price_label,
    )


@router.post("/checkout", response_model=CheckoutSessionResponse)
def create_checkout(
    request: Request,
    user: User = Depends(get_current_user),
) -> CheckoutSessionResponse:
    if user.subscription_status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is suspended.")
    if user.subscription_status == "subscribed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your subscription is already active.")
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add an email address to your account before subscribing.",
        )

    service = _service()
    if not service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured yet.",
        )
    base_url = get_settings().public_app_url or str(request.base_url)
    result = service.create_checkout_session(
        user_id=user.id,
        email=user.email,
        base_url=base_url,
    )
    if not result.url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.message or "Could not start checkout.",
        )
    return CheckoutSessionResponse(url=result.url)


@router.post("/portal", response_model=CheckoutSessionResponse)
def create_billing_portal(
    request: Request,
    user: User = Depends(get_current_user),
) -> CheckoutSessionResponse:
    if user.subscription_status != "subscribed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active subscribers can manage billing.",
        )
    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This subscription has no payment details to manage.",
        )

    result = _service().create_portal_session(
        customer_id=user.stripe_customer_id,
        base_url=get_settings().public_app_url or str(request.base_url),
    )
    if not result.url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.message or "Could not open the billing portal.",
        )
    return CheckoutSessionResponse(url=result.url)


@router.post("/cancel", response_model=UserResponse)
def cancel_beta_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if user.subscription_status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is suspended.")
    if user.subscription_status != "subscribed":
        return UserResponse.model_validate(user)
    if user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Manage this subscription in the billing portal.",
        )

    _deactivate_user(db, user, "Beta subscription cancelled from Settings.")
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/activate", response_model=UserResponse)
def activate_beta_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if user.subscription_status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is suspended.")
    if user.subscription_status == "subscribed":
        return UserResponse.model_validate(user)

    service = _service()
    if service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Billing is configured for this account. Use checkout to subscribe.",
        )
    if not get_settings().allow_beta_self_activation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-activation is disabled. Contact the administrator.",
        )

    _activate_user(db, user, "Beta subscription activated from Settings.")
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/checkout/confirm", response_model=UserResponse)
def confirm_checkout(
    payload: CheckoutConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if user.subscription_status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is suspended.")

    service = _service()
    session, error = service.retrieve_checkout_session(payload.session_id)
    if error or session is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error or "Unknown checkout session.")

    metadata = session.get("metadata") or {}
    if metadata.get("user_id") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This checkout does not belong to you.")
    if session.get("payment_status") not in {"paid", "no_payment_required"} and session.get("status") != "complete":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment is not complete yet.")

    _activate_user(
        db,
        user,
        "Subscription activated after Stripe checkout.",
        customer_id=session.get("customer"),
        subscription_id=session.get("subscription"),
    )
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    settings = get_settings()
    secret = settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhooks are not configured.",
        )

    payload = await request.body()
    if not _verify_stripe_signature(payload, request.headers.get("stripe-signature"), secret):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature.")

    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.") from exc

    event_id = event.get("id")
    event_type = event.get("type") or ""
    if not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stripe event id is missing.")
    if db.scalar(select(BillingEvent).where(BillingEvent.stripe_event_id == event_id)):
        return {"received": True}

    obj = (event.get("data") or {}).get("object") or {}
    user = _subscription_user(db, obj)

    if user is not None:
        if event_type == "checkout.session.completed":
            if obj.get("payment_status") in {"paid", "no_payment_required"} or obj.get("status") == "complete":
                _activate_user(
                    db,
                    user,
                    "Subscription activated by Stripe checkout webhook.",
                    customer_id=obj.get("customer"),
                    subscription_id=obj.get("subscription"),
                )
        elif event_type == "customer.subscription.created":
            if obj.get("status") in {"active", "trialing"}:
                _activate_user(
                    db,
                    user,
                    "Subscription confirmed by Stripe webhook.",
                    customer_id=obj.get("customer"),
                    subscription_id=obj.get("id"),
                )
        elif event_type == "customer.subscription.updated":
            if obj.get("status") in {"active", "trialing"}:
                _activate_user(
                    db,
                    user,
                    "Subscription confirmed by Stripe webhook.",
                    customer_id=obj.get("customer"),
                    subscription_id=obj.get("id"),
                )
            elif obj.get("status") in {"canceled", "unpaid", "past_due"}:
                _deactivate_user(db, user, f"Stripe subscription is {obj.get('status')}.")
        elif event_type == "customer.subscription.deleted":
            _deactivate_user(db, user, "Stripe subscription was cancelled.")

    db.add(
        BillingEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            user_id=user.id if user is not None else None,
        )
    )
    db.commit()
    return {"received": True}
