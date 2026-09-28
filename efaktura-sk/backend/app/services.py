"""Invoice lifecycle: numbering, validation, UBL generation, persistence."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.domain.invoice import DocumentType, Invoice, PrecedingInvoice
from app.models import Company, Direction, InvoiceRecord, InvoiceStatus
from app.ubl.generator import to_ubl_xml
from app.validation import schematron
from app.validation.engine import ValidationResult, validate_invoice, validate_ubl


class InvoiceError(ValueError):
    pass


def next_number(db: Session, company: Company, on: date | None = None) -> str:
    """Sequential numbering per company: <prefix><year><seq:04d>, e.g. 20270001."""
    on = on or date.today()
    seq = company.next_invoice_seq
    company.next_invoice_seq = seq + 1
    db.flush()
    return f"{company.invoice_prefix}{on.year}{seq:04d}"


def prepare_outgoing(db: Session, company: Company, invoice: Invoice) -> Invoice:
    """Fill in everything the company profile already knows."""
    inv = invoice.model_copy(deep=True)
    inv.seller = company.to_party()
    inv.issue_date = inv.issue_date or date.today()
    inv.delivery_date = inv.delivery_date or inv.issue_date
    if not inv.number:
        inv.number = next_number(db, company, inv.issue_date)
    if inv.due_date is None:  # BR-CO-25; for a credit note this is when the refund is due
        inv.due_date = inv.issue_date + timedelta(days=company.default_due_days)
    if not inv.payment.iban:
        inv.payment.iban, inv.payment.bic = company.iban, company.bic
    if not inv.payment.variable_symbol:
        inv.payment.variable_symbol = re.sub(r"\D", "", inv.number)[-10:] or None
    ids = [line.id for line in inv.lines]
    if "" in ids or len(set(ids)) != len(ids):
        for idx, line in enumerate(inv.lines, 1):
            line.id = str(idx)
    return inv


def full_validation(xml: bytes) -> ValidationResult:
    """Python rules, plus the official Schematron when installed (authoritative)."""
    result = validate_ubl(xml)
    directory = get_settings().schematron_dir
    if schematron.available(directory):
        known = {f.rule_id for f in result.findings}
        result.findings.extend(f for f in schematron.validate(xml, directory) if f.rule_id not in known)
    return result


def _apply(record: InvoiceRecord, inv: Invoice) -> ValidationResult:
    xml = to_ubl_xml(inv)
    result = full_validation(xml) if inv.lines else validate_invoice(inv)
    record.number = inv.number
    record.document_type = inv.document_type.value
    record.issue_date = inv.issue_date
    record.due_date = inv.due_date
    record.currency = inv.currency
    record.total_payable = inv.totals().payable
    record.seller_dic = inv.seller.dic or ""
    record.counterparty_name = (inv.buyer.name if record.direction == Direction.OUTGOING else inv.seller.name)
    record.data = inv.model_dump(mode="json")
    record.validation = result.as_dict()
    record.ubl_xml = xml.decode("utf-8")
    record.ubl_sha256 = hashlib.sha256(xml).hexdigest()
    if record.status in (InvoiceStatus.DRAFT, InvoiceStatus.VALID, InvoiceStatus.INVALID):
        record.status = InvoiceStatus.VALID if result.is_valid else InvoiceStatus.INVALID
    return result


def _ensure_unique(db: Session, company: Company, inv: Invoice, direction: Direction, exclude: int | None = None):
    query = select(InvoiceRecord.id).where(
        InvoiceRecord.company_id == company.id, InvoiceRecord.direction == direction,
        InvoiceRecord.number == inv.number, InvoiceRecord.seller_dic == (inv.seller.dic or ""),
    )
    existing = db.scalar(query)
    if existing and existing != exclude:
        raise InvoiceError(f"Faktúra s číslom {inv.number} už existuje.")


def create_outgoing(db: Session, company: Company, invoice: Invoice, *, user_id: int | None,
                    source: str = "manual", external_id: str | None = None) -> InvoiceRecord:
    inv = prepare_outgoing(db, company, invoice)
    _ensure_unique(db, company, inv, Direction.OUTGOING)
    record = InvoiceRecord(company_id=company.id, direction=Direction.OUTGOING, source=source,
                           external_id=external_id, status=InvoiceStatus.DRAFT)
    result = _apply(record, inv)
    db.add(record)
    db.flush()
    audit.record(db, action="invoice.created", company_id=company.id, user_id=user_id, entity_type="invoice",
                 entity_id=record.id, details={"number": inv.number, "source": source, "valid": result.is_valid})
    return record


def update_outgoing(db: Session, company: Company, record: InvoiceRecord, invoice: Invoice, *,
                    user_id: int | None) -> InvoiceRecord:
    if record.status not in (InvoiceStatus.DRAFT, InvoiceStatus.VALID, InvoiceStatus.INVALID):
        raise InvoiceError("Odoslanú faktúru nemožno meniť. Vystavte dobropis alebo opravnú faktúru.")
    inv = prepare_outgoing(db, company, invoice)
    _ensure_unique(db, company, inv, Direction.OUTGOING, exclude=record.id)
    result = _apply(record, inv)
    audit.record(db, action="invoice.updated", company_id=company.id, user_id=user_id, entity_type="invoice",
                 entity_id=record.id, details={"number": inv.number, "valid": result.is_valid})
    return record


def create_credit_note(db: Session, company: Company, original: InvoiceRecord, *, user_id: int | None,
                       reason: str | None = None) -> InvoiceRecord:
    """Full credit note (dobropis) for an existing invoice — the lines are credited as-is."""
    source = Invoice.model_validate(original.data)
    credit = source.model_copy(deep=True, update={
        "number": "", "document_type": DocumentType.CREDIT_NOTE, "issue_date": date.today(),
        "due_date": None, "delivery_date": source.delivery_date, "declared_totals": None,
        "preceding_invoice": PrecedingInvoice(number=source.number, issue_date=source.issue_date),
        "notes": [reason or f"Dobropis k faktúre č. {source.number}"], "prepaid_amount": Decimal("0"),
    })
    credit.payment.variable_symbol = source.payment.variable_symbol
    return create_outgoing(db, company, credit, user_id=user_id, source="credit_note")


def store_incoming(db: Session, company: Company, xml: bytes, *, source: str,
                   external_id: str | None = None) -> InvoiceRecord:
    from app.ubl.parser import parse_ubl

    inv = parse_ubl(xml)
    existing = db.scalar(select(InvoiceRecord).where(
        InvoiceRecord.company_id == company.id, InvoiceRecord.direction == Direction.INCOMING,
        InvoiceRecord.number == inv.number, InvoiceRecord.seller_dic == (inv.seller.dic or ""),
    ))
    if existing:
        return existing
    result = full_validation(xml)
    record = InvoiceRecord(
        company_id=company.id, direction=Direction.INCOMING, source=source, external_id=external_id,
        status=InvoiceStatus.RECEIVED, number=inv.number, document_type=inv.document_type.value,
        issue_date=inv.issue_date, due_date=inv.due_date, currency=inv.currency,
        total_payable=inv.totals().payable, seller_dic=inv.seller.dic or "", counterparty_name=inv.seller.name,
        data=inv.model_dump(mode="json"), validation=result.as_dict(), ubl_xml=xml.decode("utf-8"),
        ubl_sha256=hashlib.sha256(xml).hexdigest(),
    )
    db.add(record)
    db.flush()
    audit.record(db, action="invoice.received", company_id=company.id, entity_type="invoice",
                 entity_id=record.id, details={"number": inv.number, "from": inv.seller.name, "source": source})
    return record
