from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app import audit
from app.api.deps import ADMIN_ROLES, DB, WRITE_ROLES, CurrentUser, company_for
from app.api.invoices import _detail, _record
from app.domain.invoice import Invoice
from app.integrations import sync as sf_sync
from app.integrations.superfaktura import SuperFakturaError, to_superfaktura
from app.models import Company, Integration
from app.security import encrypt_json

router = APIRouter(tags=["integrations"])


class SuperFakturaIn(BaseModel):
    email: EmailStr
    api_key: str
    company_id: str | None = None
    sandbox: bool = False


def _integration(db: DB, company_id: int, kind: str) -> Integration:
    integ = db.scalar(select(Integration).where(Integration.company_id == company_id, Integration.kind == kind))
    if integ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integrácia nie je nastavená.")
    return integ


def _out(i: Integration) -> dict:
    return {"id": i.id, "kind": i.kind, "last_sync_at": i.last_sync_at, "last_error": i.last_error,
            "webhook_path": f"/api/v1/webhooks/{i.kind}/{i.webhook_token}"}


@router.get("/companies/{company_id}/integrations")
def list_integrations(company_id: int, user: CurrentUser, db: DB) -> list[dict]:
    company_for(db, user, company_id)
    return [_out(i) for i in db.scalars(select(Integration).where(Integration.company_id == company_id))]


@router.put("/companies/{company_id}/integrations/superfaktura")
def connect_superfaktura(company_id: int, body: SuperFakturaIn, user: CurrentUser, db: DB) -> dict:
    company_for(db, user, company_id, ADMIN_ROLES)
    integ = db.scalar(select(Integration).where(Integration.company_id == company_id,
                                                Integration.kind == "superfaktura"))
    if integ is None:
        integ = Integration(company_id=company_id, kind="superfaktura", webhook_token=secrets.token_urlsafe(24))
        db.add(integ)
    integ.credentials = encrypt_json(body.model_dump())
    db.flush()
    audit.record(db, action="integration.connected", company_id=company_id, user_id=user.id,
                 entity_type="integration", entity_id=integ.id, details={"kind": "superfaktura",
                                                                          "sandbox": body.sandbox})
    db.commit()
    return _out(integ)


@router.delete("/companies/{company_id}/integrations/{kind}", status_code=204)
def disconnect(company_id: int, kind: str, user: CurrentUser, db: DB) -> None:
    company_for(db, user, company_id, ADMIN_ROLES)
    integ = _integration(db, company_id, kind)
    db.delete(integ)
    audit.record(db, action="integration.disconnected", company_id=company_id, user_id=user.id,
                 entity_type="integration", details={"kind": kind})
    db.commit()


@router.post("/companies/{company_id}/integrations/superfaktura/sync")
def sync_superfaktura(company_id: int, user: CurrentUser, db: DB, full: bool = False) -> dict:
    company_for(db, user, company_id, WRITE_ROLES)
    integ = _integration(db, company_id, "superfaktura")
    try:
        return sf_sync.sync(db, integ, full=full)
    except SuperFakturaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/companies/{company_id}/invoices/{invoice_id}/push-superfaktura")
def push_superfaktura(company_id: int, invoice_id: int, user: CurrentUser, db: DB) -> dict:
    company_for(db, user, company_id, WRITE_ROLES)
    record = _record(db, company_id, invoice_id)
    integ = _integration(db, company_id, "superfaktura")
    client = sf_sync.client_for(integ)
    try:
        result = client.create_invoice(to_superfaktura(Invoice.model_validate(record.data)))
    except SuperFakturaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        client.close()
    sf_id = str(((result or {}).get("data") or {}).get("Invoice", {}).get("id") or "") or None
    record.external_id = record.external_id or sf_id
    audit.record(db, action="integration.pushed", company_id=company_id, user_id=user.id, entity_type="invoice",
                 entity_id=record.id, details={"kind": "superfaktura", "external_id": sf_id})
    db.commit()
    return {"external_id": sf_id, "invoice": _detail(record)}


@router.post("/webhooks/superfaktura/{token}", include_in_schema=False)
async def superfaktura_webhook(token: str, request: Request, db: DB) -> dict:
    """SuperFaktúra calls this when an invoice changes; we re-fetch it by id (never trust the payload)."""
    integ = db.scalar(select(Integration).where(Integration.webhook_token == token,
                                                Integration.kind == "superfaktura"))
    if integ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        payload = await request.json()
    except ValueError:
        payload = dict(await request.form())
    invoice_id = (payload.get("invoice_id") or payload.get("id")
                  or (payload.get("Invoice") or {}).get("id") if isinstance(payload, dict) else None)
    if not invoice_id:
        return {"ok": True, "imported": 0}
    client = sf_sync.client_for(integ)
    try:
        outcome, _ = sf_sync.import_document(db, db.get(Company, integ.company_id), client.get_invoice(invoice_id))
    except SuperFakturaError as exc:
        integ.last_error = str(exc)
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        client.close()
    db.commit()
    return {"ok": True, "outcome": outcome}
