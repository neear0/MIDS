from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.domain.invoice import Invoice


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str


class CompanyIn(BaseModel):
    name: str
    ico: str | None = None
    dic: str | None = None
    ic_dph: str | None = None
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country_code: str = "SK"
    email: str | None = None
    iban: str | None = None
    bic: str | None = None
    registration_note: str | None = None
    invoice_prefix: str = ""
    default_due_days: int = 14


class CompanyOut(CompanyIn):
    id: int
    role: str | None = None
    identifier_warnings: list[str] = []


class MemberIn(BaseModel):
    email: EmailStr
    role: str = "accountant"


class MemberOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: str


class InvoiceSummary(BaseModel):
    id: int
    number: str
    direction: str
    document_type: str
    status: str
    source: str
    counterparty_name: str
    issue_date: date | None
    due_date: date | None
    currency: str
    total_payable: Decimal
    paid_at: date | None
    error_count: int = 0
    warning_count: int = 0
    created_at: datetime


class InvoiceDetail(InvoiceSummary):
    invoice: Invoice
    validation: dict | None
    ubl_sha256: str | None
    transmissions: list[dict] = []


class CreditNoteIn(BaseModel):
    reason: str | None = None


class ValidationOut(BaseModel):
    valid: bool
    error_count: int
    warning_count: int
    findings: list[dict]
