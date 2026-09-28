from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app import audit, services
from app.api.deps import DB, WRITE_ROLES, CurrentUser, company_for
from app.api.schemas import CreditNoteIn, InvoiceDetail, InvoiceSummary, ValidationOut
from app.domain.invoice import Invoice
from app.models import Direction, InvoiceRecord
from app.pdf.render import render_pdf
from app.ubl.parser import UblParseError
from app.validation.engine import validate_invoice

router = APIRouter(tags=["invoices"])

MAX_UPLOAD = 5 * 1024 * 1024


def _summary(r: InvoiceRecord) -> dict:
    v = r.validation or {}
    return dict(
        id=r.id, number=r.number, direction=r.direction, document_type=r.document_type, status=r.status,
        source=r.source, counterparty_name=r.counterparty_name, issue_date=r.issue_date, due_date=r.due_date,
        currency=r.currency, total_payable=r.total_payable, paid_at=r.paid_at,
        error_count=v.get("error_count", 0), warning_count=v.get("warning_count", 0), created_at=r.created_at,
    )


def _detail(r: InvoiceRecord) -> InvoiceDetail:
    return InvoiceDetail(
        **_summary(r), invoice=Invoice.model_validate(r.data), validation=r.validation, ubl_sha256=r.ubl_sha256,
        transmissions=[{"id": t.id, "provider": t.provider, "status": t.status, "message_id": t.message_id,
                        "tax_report_status": t.tax_report_status, "attempts": t.attempts,
                        "last_error": t.last_error, "updated_at": t.updated_at} for t in r.transmissions],
    )


def _record(db: DB, company_id: int, invoice_id: int) -> InvoiceRecord:
    r = db.get(InvoiceRecord, invoice_id)
    if r is None or r.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Faktúra neexistuje.")
    return r


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Súbor je väčší ako 5 MB.")
    return data


@router.post("/validate", response_model=ValidationOut)
async def validate_xml(user: CurrentUser, file: UploadFile = File(...)) -> dict:
    """Validate any UBL 2.1 invoice/credit note (EN 16931 + Peppol BIS 3.0 + SK rules)."""
    return services.full_validation(await _read_upload(file)).as_dict()


@router.post("/validate/draft", response_model=ValidationOut)
def validate_draft(invoice: Invoice, user: CurrentUser) -> dict:
    """Live validation while the user is filling in the form (no persistence)."""
    return validate_invoice(invoice).as_dict()


@router.get("/companies/{company_id}/invoices", response_model=list[InvoiceSummary])
def list_invoices(company_id: int, user: CurrentUser, db: DB, direction: Direction | None = None,
                  status_filter: str | None = Query(None, alias="status"), limit: int = Query(100, le=500),
                  offset: int = 0) -> list[dict]:
    company_for(db, user, company_id)
    q = select(InvoiceRecord).where(InvoiceRecord.company_id == company_id)
    if direction:
        q = q.where(InvoiceRecord.direction == direction)
    if status_filter:
        q = q.where(InvoiceRecord.status == status_filter)
    q = q.order_by(InvoiceRecord.issue_date.desc(), InvoiceRecord.id.desc()).limit(limit).offset(offset)
    return [_summary(r) for r in db.scalars(q)]


@router.post("/companies/{company_id}/invoices", response_model=InvoiceDetail, status_code=201)
def create_invoice(company_id: int, invoice: Invoice, user: CurrentUser, db: DB) -> InvoiceDetail:
    company = company_for(db, user, company_id, WRITE_ROLES)
    try:
        record = services.create_outgoing(db, company, invoice, user_id=user.id)
    except services.InvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _detail(record)


@router.post("/companies/{company_id}/invoices/import-ubl", response_model=InvoiceDetail, status_code=201)
async def import_ubl(company_id: int, user: CurrentUser, db: DB, file: UploadFile = File(...)) -> InvoiceDetail:
    """Store a received UBL invoice (e.g. delivered by e-mail before Peppol is mandatory)."""
    company = company_for(db, user, company_id, WRITE_ROLES)
    try:
        record = services.store_incoming(db, company, await _read_upload(file), source="ubl")
    except UblParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return _detail(record)


@router.get("/companies/{company_id}/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(company_id: int, invoice_id: int, user: CurrentUser, db: DB) -> InvoiceDetail:
    company_for(db, user, company_id)
    return _detail(_record(db, company_id, invoice_id))


@router.put("/companies/{company_id}/invoices/{invoice_id}", response_model=InvoiceDetail)
def update_invoice(company_id: int, invoice_id: int, invoice: Invoice, user: CurrentUser, db: DB) -> InvoiceDetail:
    company = company_for(db, user, company_id, WRITE_ROLES)
    record = _record(db, company_id, invoice_id)
    if record.direction != Direction.OUTGOING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Prijatú faktúru nemožno upravovať.")
    try:
        services.update_outgoing(db, company, record, invoice, user_id=user.id)
    except services.InvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _detail(record)


@router.post("/companies/{company_id}/invoices/{invoice_id}/credit-note", response_model=InvoiceDetail,
             status_code=201)
def credit_note(company_id: int, invoice_id: int, body: CreditNoteIn, user: CurrentUser, db: DB) -> InvoiceDetail:
    company = company_for(db, user, company_id, WRITE_ROLES)
    original = _record(db, company_id, invoice_id)
    if original.direction != Direction.OUTGOING or original.document_type == "381":
        raise HTTPException(status.HTTP_409_CONFLICT, "Dobropis sa dá vystaviť len k vlastnej faktúre.")
    record = services.create_credit_note(db, company, original, user_id=user.id, reason=body.reason)
    db.commit()
    return _detail(record)


@router.post("/companies/{company_id}/invoices/{invoice_id}/paid", response_model=InvoiceDetail)
def mark_paid(company_id: int, invoice_id: int, user: CurrentUser, db: DB, paid_on: date | None = None
              ) -> InvoiceDetail:
    company_for(db, user, company_id, WRITE_ROLES)
    record = _record(db, company_id, invoice_id)
    record.paid_at = paid_on or date.today()
    audit.record(db, action="invoice.paid", company_id=company_id, user_id=user.id, entity_type="invoice",
                 entity_id=record.id, details={"paid_at": record.paid_at.isoformat()})
    db.commit()
    return _detail(record)


@router.get("/companies/{company_id}/invoices/{invoice_id}/ubl")
def download_ubl(company_id: int, invoice_id: int, user: CurrentUser, db: DB) -> Response:
    company_for(db, user, company_id)
    record = _record(db, company_id, invoice_id)
    return Response(record.ubl_xml or "", media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{record.number}.xml"'})


@router.get("/companies/{company_id}/invoices/{invoice_id}/pdf")
def download_pdf(company_id: int, invoice_id: int, user: CurrentUser, db: DB) -> Response:
    company_for(db, user, company_id)
    record = _record(db, company_id, invoice_id)
    pdf = render_pdf(Invoice.model_validate(record.data))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{record.number}.pdf"'})
