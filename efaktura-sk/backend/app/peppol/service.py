"""Outbox-based sending and inbox polling.

``queue`` only writes a Transmission row, so a user can "send" while the AP
is down or while offline-first clients sync later; ``process_outbox`` does
the network work with exponential backoff and is safe to run repeatedly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit, services
from app.domain.invoice import Invoice
from app.models import Company, InvoiceRecord, InvoiceStatus, Transmission
from app.peppol.access_point import (
    DOCTYPE_CREDIT_NOTE,
    DOCTYPE_INVOICE,
    AccessPoint,
    AccessPointError,
    PermanentAccessPointError,
    participant,
)

MAX_ATTEMPTS = 8


class SendError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def queue(db: Session, record: InvoiceRecord, ap: AccessPoint, *, user_id: int | None) -> Transmission:
    if record.status == InvoiceStatus.INVALID:
        raise SendError("Faktúra obsahuje chyby. Opravte ich pred odoslaním.")
    if record.status not in (InvoiceStatus.VALID, InvoiceStatus.FAILED):
        raise SendError("Faktúru už nemožno odoslať (je odoslaná alebo sa odosiela).")
    inv = Invoice.model_validate(record.data)
    if not inv.buyer.resolved_endpoint()[1]:
        raise SendError("Odberateľ nemá Peppol adresu (DIČ).")
    t = Transmission(invoice_id=record.id, provider=ap.name, status="queued", next_attempt_at=_now())
    db.add(t)
    record.status = InvoiceStatus.QUEUED
    db.flush()
    audit.record(db, action="invoice.queued", company_id=record.company_id, user_id=user_id,
                 entity_type="invoice", entity_id=record.id, details={"transmission": t.id, "provider": ap.name})
    return t


def _send_one(db: Session, t: Transmission, ap: AccessPoint) -> None:
    record = t.invoice
    inv = Invoice.model_validate(record.data)
    s_scheme, s_id = inv.seller.resolved_endpoint()
    r_scheme, r_id = inv.buyer.resolved_endpoint()
    doc_type = DOCTYPE_CREDIT_NOTE if inv.is_credit_note else DOCTYPE_INVOICE
    t.attempts += 1
    try:
        receipt = ap.send(record.ubl_xml.encode("utf-8"), sender=participant(s_scheme, s_id),
                          receiver=participant(r_scheme, r_id), document_type=doc_type)
    except PermanentAccessPointError as exc:
        t.status, t.last_error, t.next_attempt_at = "failed", str(exc), None
        record.status = InvoiceStatus.FAILED
    except AccessPointError as exc:
        t.last_error = str(exc)
        if t.attempts >= MAX_ATTEMPTS:
            t.status, t.next_attempt_at = "failed", None
            record.status = InvoiceStatus.FAILED
        else:
            t.next_attempt_at = _now() + timedelta(minutes=2 ** t.attempts)
    else:
        t.message_id, t.status, t.last_error, t.next_attempt_at = receipt.message_id, receipt.status, None, None
        record.status = InvoiceStatus.DELIVERED if receipt.status == "delivered" else InvoiceStatus.SENT
        if receipt.status == "delivered":
            t.tax_report_status = ap.status(receipt.message_id).tax_report_status
    audit.record(db, action=f"transmission.{t.status}", company_id=record.company_id, entity_type="invoice",
                 entity_id=record.id, details={"attempt": t.attempts, "message_id": t.message_id,
                                               "error": t.last_error})


def process_outbox(db: Session, ap: AccessPoint, limit: int = 50) -> int:
    """Send due queued transmissions and refresh statuses of sent ones. Returns rows touched."""
    now = _now()
    due = [t for t in db.scalars(select(Transmission).where(Transmission.status == "queued").limit(limit * 2))
           if _aware(t.next_attempt_at) is None or _aware(t.next_attempt_at) <= now][:limit]
    for t in due:
        _send_one(db, t, ap)
    pending = list(db.scalars(select(Transmission).where(
        or_(Transmission.status == "sent",
            (Transmission.status == "delivered") & (Transmission.tax_report_status.is_distinct_from("reported")))
    ).limit(limit)))
    for t in pending:
        st = ap.status(t.message_id)
        t.tax_report_status = st.tax_report_status or t.tax_report_status
        if st.status != t.status:
            t.status, t.last_error = st.status, st.error
            t.invoice.status = {"delivered": InvoiceStatus.DELIVERED, "failed": InvoiceStatus.FAILED}.get(
                st.status, t.invoice.status)
    db.commit()
    return len(due) + len(pending)


def poll_inbox(db: Session, company: Company, ap: AccessPoint) -> int:
    if not company.dic:
        return 0
    count = 0
    for doc in ap.fetch_inbox(participant("0245", company.dic)):
        services.store_incoming(db, company, doc.xml, source="peppol", external_id=doc.message_id)
        db.commit()
        ap.acknowledge(doc.message_id)
        count += 1
    return count
