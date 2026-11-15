"""Subscriber-monitor agent.

Keeps the operator's subscriber view and Google Sheet feed in step with the
account records. Every subscription change is written to an audit trail before
the live list is regenerated, so the spreadsheet can always be traced back to a
specific action.
"""

from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SubscriberEvent, User


def record_subscriber_event(
    db: Session,
    user: User,
    action: str,
    status: str | None = None,
    detail: str | None = None,
) -> SubscriberEvent:
    event = SubscriberEvent(
        user_id=user.id,
        name=user.name,
        email=user.email,
        action=action,
        status=status or user.subscription_status,
        detail=detail,
    )
    db.add(event)
    return event


def subscriber_rows(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.is_anonymous.is_(False))
            .order_by(User.created_at.desc())
        ).all()
    )


def subscriber_summary(users: list[User]) -> dict[str, int]:
    counts = {"total": len(users), "subscribed": 0, "pending": 0, "suspended": 0}
    for user in users:
        status = user.subscription_status if user.subscription_status in counts else "pending"
        counts[status] += 1
    return counts


def subscriber_csv(db: Session) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Email", "Status", "Plan", "Joined", "Last active"])
    for user in subscriber_rows(db):
        writer.writerow(
            [
                user.name,
                user.email or "",
                user.subscription_status,
                user.subscription_tier,
                user.created_at.isoformat() if user.created_at else "",
                user.last_active_at.isoformat() if user.last_active_at else "",
            ]
        )
    return buffer.getvalue()


def recent_events(db: Session, limit: int = 12) -> list[SubscriberEvent]:
    return list(
        db.scalars(
            select(SubscriberEvent)
            .order_by(SubscriberEvent.created_at.desc())
            .limit(limit)
        ).all()
    )
