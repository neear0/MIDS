"""Company profiles and members — multi-company support for accountants."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import audit
from app.api.deps import ADMIN_ROLES, DB, CurrentUser, company_for, membership
from app.api.schemas import CompanyIn, CompanyOut, MemberIn, MemberOut
from app.domain.identifiers import (
    is_valid_dic,
    is_valid_iban,
    is_valid_ic_dph,
    is_valid_ico,
)
from app.models import Company, Membership, Role, User

router = APIRouter(prefix="/companies", tags=["companies"])


def _warnings(body: CompanyIn) -> list[str]:
    out = []
    if body.ico and not is_valid_ico(body.ico):
        out.append("IČO nemá platný kontrolný súčet.")
    if body.dic and not is_valid_dic(body.dic):
        out.append("DIČ musí mať 10 číslic.")
    if body.ic_dph and body.ic_dph.upper().startswith("SK") and not is_valid_ic_dph(body.ic_dph):
        out.append("IČ DPH nie je platné.")
    if body.iban and not is_valid_iban(body.iban):
        out.append("IBAN nie je platný.")
    return out


def _out(company: Company, role: str | None) -> CompanyOut:
    data = CompanyIn.model_validate(company, from_attributes=True)
    return CompanyOut(id=company.id, role=role, identifier_warnings=_warnings(data), **data.model_dump())


@router.get("", response_model=list[CompanyOut])
def list_companies(user: CurrentUser, db: DB) -> list[CompanyOut]:
    rows = db.scalars(select(Membership).where(Membership.user_id == user.id).order_by(Membership.company_id))
    return [_out(m.company, m.role) for m in rows]


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, user: CurrentUser, db: DB) -> CompanyOut:
    company = Company(**body.model_dump())
    db.add(company)
    db.flush()
    db.add(Membership(user_id=user.id, company_id=company.id, role=Role.OWNER))
    audit.record(db, action="company.created", company_id=company.id, user_id=user.id, entity_type="company",
                 entity_id=company.id, details={"name": company.name})
    db.commit()
    return _out(company, Role.OWNER)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, user: CurrentUser, db: DB) -> CompanyOut:
    m = membership(db, user, company_id)
    return _out(m.company, m.role)


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn, user: CurrentUser, db: DB) -> CompanyOut:
    company = company_for(db, user, company_id, ADMIN_ROLES)
    for key, value in body.model_dump().items():
        setattr(company, key, value)
    audit.record(db, action="company.updated", company_id=company.id, user_id=user.id, entity_type="company",
                 entity_id=company.id)
    db.commit()
    return _out(company, membership(db, user, company_id).role)


@router.get("/{company_id}/members", response_model=list[MemberOut])
def list_members(company_id: int, user: CurrentUser, db: DB) -> list[MemberOut]:
    company = company_for(db, user, company_id)
    return [MemberOut(user_id=m.user_id, email=m.user.email, full_name=m.user.full_name, role=m.role)
            for m in company.memberships]


@router.post("/{company_id}/members", response_model=MemberOut, status_code=201)
def add_member(company_id: int, body: MemberIn, user: CurrentUser, db: DB) -> MemberOut:
    company = company_for(db, user, company_id, ADMIN_ROLES)
    if body.role not in set(Role):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Neznáma rola.")
    invitee = db.scalar(select(User).where(User.email == body.email.lower()))
    if invitee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Používateľ sa musí najprv zaregistrovať.")
    if db.scalar(select(Membership).where(Membership.user_id == invitee.id, Membership.company_id == company.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Používateľ už je členom firmy.")
    db.add(Membership(user_id=invitee.id, company_id=company.id, role=body.role))
    audit.record(db, action="member.added", company_id=company.id, user_id=user.id, entity_type="user",
                 entity_id=invitee.id, details={"role": body.role})
    db.commit()
    return MemberOut(user_id=invitee.id, email=invitee.email, full_name=invitee.full_name, role=body.role)
