from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, WRITE_ROLES, CurrentUser, company_for
from app.api.invoices import _detail, _record
from app.domain.identifiers import SK_DIC_SCHEME, is_valid_dic
from app.peppol import service
from app.peppol.access_point import get_access_point, participant

router = APIRouter(tags=["peppol"])


@router.post("/companies/{company_id}/invoices/{invoice_id}/send")
def send_invoice(company_id: int, invoice_id: int, user: CurrentUser, db: DB) -> dict:
    """Queue for Peppol delivery and try immediately; failures are retried by the worker."""
    company_for(db, user, company_id, WRITE_ROLES)
    record = _record(db, company_id, invoice_id)
    ap = get_access_point()
    try:
        service.queue(db, record, ap, user_id=user.id)
    except service.SendError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    service.process_outbox(db, ap)
    db.refresh(record)
    return _detail(record).model_dump(mode="json")


@router.post("/companies/{company_id}/peppol/poll")
def poll(company_id: int, user: CurrentUser, db: DB) -> dict:
    company = company_for(db, user, company_id, WRITE_ROLES)
    return {"received": service.poll_inbox(db, company, get_access_point())}


@router.get("/peppol/lookup")
def lookup(dic: str, user: CurrentUser) -> dict:
    if not is_valid_dic(dic):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "DIČ musí mať 10 číslic.")
    pid = participant(SK_DIC_SCHEME, dic)
    return {"participant": pid, "registered": get_access_point().lookup(pid)}
