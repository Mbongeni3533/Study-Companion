"""Beta administration endpoints.

These are intentionally small and protected by a shared admin key supplied via
the ``BETA_ADMIN_KEY`` environment variable. They let the operator create,
list and revoke invite codes without redeploying.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
import logging

from ..models import InviteCode
from ..schemas import InviteCodeCreate, InviteCodeResponse
from ..services.email import send_invite_email

logger = logging.getLogger("study_companion.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    settings = get_settings()
    if not settings.beta_admin_key or not x_admin_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access disabled.")
    if x_admin_key != settings.beta_admin_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key.")


@router.get("/invite-codes", response_model=list[InviteCodeResponse])
def list_invite_codes(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> list[InviteCodeResponse]:
    codes = db.scalars(select(InviteCode).order_by(InviteCode.created_at.desc())).all()
    return [InviteCodeResponse.model_validate(code) for code in codes]


@router.post("/invite-codes", response_model=InviteCodeResponse, status_code=status.HTTP_201_CREATED)
def create_invite_code(
    payload: InviteCodeCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> InviteCodeResponse:
    code = (payload.code or "").strip() or f"BETA-{secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10].upper()}"
    existing = db.scalar(select(InviteCode).where(InviteCode.code == code))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite code already exists.")
    if payload.expires_at is not None and payload.expires_at.tzinfo is None:
        payload.expires_at = payload.expires_at.replace(tzinfo=timezone.utc)
    invite = InviteCode(
        code=code,
        email=payload.email.lower().strip() if payload.email else None,
        max_uses=payload.max_uses,
        expires_at=payload.expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    response = InviteCodeResponse.model_validate(invite)
    if payload.send_email and invite.email:
        try:
            send_invite_email(invite.email, code)
            response.email_sent = True
        except Exception as exc:  # pragma: no cover - network/provider failure
            logger.warning("Failed to send invite email to %s: %s", invite.email, exc)
            response.email_sent = False
    return response


@router.delete("/invite-codes/{code}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite_code(
    code: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> None:
    invite = db.scalar(select(InviteCode).where(InviteCode.code == code))
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found.")
    invite.revoked = True
    db.commit()


@router.post("/invite-codes/{code}/send", response_model=InviteCodeResponse)
def send_invite_code(
    code: str,
    email: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> InviteCodeResponse:
    invite = db.scalar(select(InviteCode).where(InviteCode.code == code))
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found.")
    to_email = (email or invite.email or "").strip()
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email address is required to send this invite.",
        )
    try:
        send_invite_email(to_email, invite.code)
    except Exception as exc:
        logger.warning("Failed to send invite email to %s: %s", to_email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invite code was not emailed. Check RESEND_API_KEY and sender settings.",
        ) from exc
    response = InviteCodeResponse.model_validate(invite)
    response.email_sent = True
    return response
