"""Compliance dashboard, reminders and audit trail."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app import audit
from app.api.deps import ADMIN_ROLES, DB, CurrentUser, company_for
from app.config import get_settings
from app.domain.identifiers import is_valid_dic, is_valid_iban, is_valid_ic_dph
from app.models import AuditEvent, Direction, InvoiceRecord, InvoiceStatus

router = APIRouter(prefix="/companies/{company_id}", tags=["dashboard"])

LEGISLATIVE_DEADLINES = [
    {"date": "2027-01-01", "title": "Povinná e-fakturácia B2B v tuzemsku",
     "detail": "Faktúry medzi platiteľmi DPH sa posielajú štruktúrovane (EN 16931) cez sieť Peppol "
               "a údaje sa súčasne hlásia Finančnej správe."},
    {"date": "2030-07-01", "title": "ViDA – cezhraničná digitálna evidencia",
     "detail": "Balík EÚ VAT in the Digital Age zavádza e-fakturáciu a hlásenie pre cezhraničné plnenia."},
]


def _readiness(company, has_ap: bool) -> list[dict]:
    return [
        {"key": "dic", "ok": is_valid_dic(company.dic), "label": "Platné DIČ (Peppol adresa 0245)"},
        {"key": "ic_dph", "ok": not company.ic_dph or is_valid_ic_dph(company.ic_dph), "label": "Platné IČ DPH"},
        {"key": "iban", "ok": is_valid_iban(company.iban), "label": "IBAN pre platby a QR kód"},
        {"key": "address", "ok": bool(company.street and company.city and company.postal_code),
         "label": "Úplná adresa sídla"},
        {"key": "peppol", "ok": has_ap, "label": "Pripojenie k Peppol prístupovému bodu"},
    ]


@router.get("/dashboard")
def dashboard(company_id: int, user: CurrentUser, db: DB) -> dict:
    company = company_for(db, user, company_id)
    today = date.today()
    base = select(InvoiceRecord).where(InvoiceRecord.company_id == company_id)

    counts = dict(db.execute(
        select(InvoiceRecord.status, func.count()).where(InvoiceRecord.company_id == company_id)
        .group_by(InvoiceRecord.status)
    ).all())

    unpaid_out = base.where(InvoiceRecord.direction == Direction.OUTGOING, InvoiceRecord.paid_at.is_(None),
                            InvoiceRecord.document_type != "381")
    overdue = list(db.scalars(unpaid_out.where(InvoiceRecord.due_date < today).order_by(InvoiceRecord.due_date)))
    due_soon = list(db.scalars(unpaid_out.where(InvoiceRecord.due_date.between(today, today + timedelta(days=7)))
                               .order_by(InvoiceRecord.due_date)))
    payables = list(db.scalars(base.where(InvoiceRecord.direction == Direction.INCOMING,
                                          InvoiceRecord.paid_at.is_(None),
                                          InvoiceRecord.due_date <= today + timedelta(days=7))
                               .order_by(InvoiceRecord.due_date)))

    recent = list(db.scalars(base.where(InvoiceRecord.direction == Direction.OUTGOING)
                             .order_by(InvoiceRecord.id.desc()).limit(50)))
    checked = [r for r in recent if r.validation]
    valid = sum(1 for r in checked if r.validation.get("valid"))
    score = round(100 * valid / len(checked)) if checked else None

    ap_ready = get_settings().peppol_provider != "mock"

    def brief(r: InvoiceRecord) -> dict:
        return {"id": r.id, "number": r.number, "counterparty": r.counterparty_name,
                "due_date": r.due_date, "amount": r.total_payable, "currency": r.currency,
                "days_overdue": (today - r.due_date).days if r.due_date and r.due_date < today else 0}

    return {
        "company": {"id": company.id, "name": company.name},
        "counts": {s.value: counts.get(s.value, 0) for s in InvoiceStatus},
        "compliance_score": score,
        "readiness": _readiness(company, ap_ready),
        "receivables": {
            "overdue": [brief(r) for r in overdue],
            "overdue_total": sum((r.total_payable for r in overdue), Decimal("0")),
            "due_soon": [brief(r) for r in due_soon],
        },
        "payables_due": [brief(r) for r in payables],
        "invalid_invoices": [brief(r) for r in recent if r.status == InvoiceStatus.INVALID][:10],
        "deadlines": [d | {"days_left": (date.fromisoformat(d["date"]) - today).days}
                      for d in LEGISLATIVE_DEADLINES if date.fromisoformat(d["date"]) >= today],
    }


@router.get("/audit")
def audit_log(company_id: int, user: CurrentUser, db: DB, limit: int = Query(100, le=1000)) -> dict:
    company_for(db, user, company_id, ADMIN_ROLES)
    events = db.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id)
                        .order_by(AuditEvent.id.desc()).limit(limit))
    return {
        "chain_intact": audit.verify_chain(db, company_id),
        "events": [{"id": e.id, "action": e.action, "user_id": e.user_id, "entity_type": e.entity_type,
                    "entity_id": e.entity_id, "details": e.details, "created_at": e.created_at,
                    "hash": e.hash} for e in events],
    }
