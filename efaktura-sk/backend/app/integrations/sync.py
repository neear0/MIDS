"""SuperFaktúra → eFaktúra SK import (one-way sync, idempotent by SuperFaktúra id)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, services
from app.config import get_settings
from app.integrations.superfaktura import Credentials, SuperFakturaClient, from_superfaktura
from app.models import Company, Direction, Integration, InvoiceRecord
from app.security import decrypt_json


def client_for(integration: Integration, transport: httpx.BaseTransport | None = None) -> SuperFakturaClient:
    creds = Credentials(**decrypt_json(integration.credentials))
    settings = get_settings()
    base = settings.superfaktura_sandbox_url if creds.sandbox else settings.superfaktura_base_url
    return SuperFakturaClient(creds, base, transport=transport)


def import_document(db: Session, company: Company, doc: dict) -> tuple[str, InvoiceRecord | None]:
    """Create or update one invoice. Returns ("created"|"updated"|"skipped", record)."""
    sf_id = str(doc.get("Invoice", {}).get("id") or "")
    invoice = from_superfaktura(doc, company.to_party())
    existing = db.scalar(select(InvoiceRecord).where(
        InvoiceRecord.company_id == company.id, InvoiceRecord.direction == Direction.OUTGOING,
        InvoiceRecord.source == "superfaktura", InvoiceRecord.external_id == sf_id,
    )) if sf_id else None
    try:
        if existing is None:
            return "created", services.create_outgoing(db, company, invoice, user_id=None, source="superfaktura",
                                                       external_id=sf_id or None)
        return "updated", services.update_outgoing(db, company, existing, invoice, user_id=None)
    except services.InvoiceError:
        return "skipped", existing


def sync(db: Session, integration: Integration, *, transport: httpx.BaseTransport | None = None,
         full: bool = False) -> dict:
    company = db.get(Company, integration.company_id)
    since = None if full or integration.last_sync_at is None else (
        integration.last_sync_at.date() - timedelta(days=1))
    stats = {"created": 0, "updated": 0, "skipped": 0}
    client = client_for(integration, transport)
    try:
        for item in client.iter_invoices(modified_since=since):
            outcome, _ = import_document(db, company, item)
            stats[outcome] += 1
        integration.last_sync_at = datetime.now(UTC)
        integration.last_error = None
    except Exception as exc:
        integration.last_error = str(exc)
        raise
    finally:
        client.close()
        audit.record(db, action="integration.sync", company_id=company.id, entity_type="integration",
                     entity_id=integration.id, details={"kind": integration.kind, **stats,
                                                        "error": integration.last_error})
        db.commit()
    return stats
