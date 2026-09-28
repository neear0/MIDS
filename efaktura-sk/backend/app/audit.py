"""Hash-chained audit log: each event stores the hash of the previous one for its company."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, utcnow


def _aware(value: datetime) -> datetime:
    # SQLite drops tzinfo on read; timestamps are always written in UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _digest(prev_hash: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def record(db: Session, *, action: str, company_id: int | None = None, user_id: int | None = None,
           entity_type: str = "", entity_id: object = None, details: dict | None = None) -> AuditEvent:
    prev = db.scalar(
        select(AuditEvent.hash).where(AuditEvent.company_id == company_id).order_by(AuditEvent.id.desc()).limit(1)
    ) or ""
    created_at = utcnow()
    payload = {
        "action": action, "company_id": company_id, "user_id": user_id, "entity_type": entity_type,
        "entity_id": None if entity_id is None else str(entity_id), "details": details or {},
        "created_at": created_at.isoformat(),
    }
    event = AuditEvent(
        company_id=company_id, user_id=user_id, action=action, entity_type=entity_type,
        entity_id=payload["entity_id"], details=details or {}, prev_hash=prev,
        hash=_digest(prev, payload), created_at=created_at,
    )
    db.add(event)
    db.flush()
    return event


def verify_chain(db: Session, company_id: int) -> bool:
    prev = ""
    events = db.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id).order_by(AuditEvent.id))
    for ev in events:
        payload = {
            "action": ev.action, "company_id": ev.company_id, "user_id": ev.user_id,
            "entity_type": ev.entity_type, "entity_id": ev.entity_id, "details": ev.details,
            "created_at": _aware(ev.created_at).isoformat(),
        }
        if ev.prev_hash != prev or ev.hash != _digest(prev, payload):
            return False
        prev = ev.hash
    return True
