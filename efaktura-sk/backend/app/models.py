"""Persistence model. Invoices keep the canonical JSON *and* the exact UBL bytes sent."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.invoice import Address, Party, Payment


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    OWNER = "owner"  # company owner / živnostník
    ACCOUNTANT = "accountant"  # external accountant with full access
    MEMBER = "member"  # can create and send invoices
    VIEWER = "viewer"  # read-only


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"


class Direction(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    ico: Mapped[str | None] = mapped_column(String(16))
    dic: Mapped[str | None] = mapped_column(String(16), index=True)
    ic_dph: Mapped[str | None] = mapped_column(String(16))
    street: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="SK")
    email: Mapped[str | None] = mapped_column(String(255))
    iban: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))
    registration_note: Mapped[str | None] = mapped_column(String(255))
    invoice_prefix: Mapped[str] = mapped_column(String(16), default="")
    next_invoice_seq: Mapped[int] = mapped_column(Integer, default=1)
    default_due_days: Mapped[int] = mapped_column(Integer, default=14)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list[Membership]] = relationship(back_populates="company", cascade="all, delete-orphan")

    def to_party(self) -> Party:
        return Party(
            name=self.name, ico=self.ico, dic=self.dic, ic_dph=self.ic_dph, email=self.email,
            registration_note=self.registration_note,
            address=Address(street=self.street, city=self.city, postal_code=self.postal_code,
                            country_code=self.country_code),
        )

    def default_payment(self, variable_symbol: str | None = None) -> Payment:
        return Payment(iban=self.iban, bic=self.bic, variable_symbol=variable_symbol)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16), default=Role.OWNER)

    user: Mapped[User] = relationship(back_populates="memberships")
    company: Mapped[Company] = relationship(back_populates="memberships")


class InvoiceRecord(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("company_id", "direction", "number", "seller_dic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(16), default=Direction.OUTGOING)
    number: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str] = mapped_column(String(3), default="380")
    status: Mapped[str] = mapped_column(String(16), default=InvoiceStatus.DRAFT, index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual|ai|superfaktura|peppol|ubl
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    seller_dic: Mapped[str] = mapped_column(String(16), default="")
    counterparty_name: Mapped[str] = mapped_column(String(255), default="")
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    total_payable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    paid_at: Mapped[date | None] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSON)  # canonical Invoice as JSON
    validation: Mapped[dict | None] = mapped_column(JSON)
    ubl_xml: Mapped[str | None] = mapped_column(Text)
    ubl_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    transmissions: Mapped[list[Transmission]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class Transmission(Base):
    """One attempt to deliver a document through the Peppol Access Point (outbox pattern)."""

    __tablename__ = "transmissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|sent|delivered|failed
    message_id: Mapped[str | None] = mapped_column(String(128))
    tax_report_status: Mapped[str | None] = mapped_column(String(32))  # 5-corner reporting to Finančná správa
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    invoice: Mapped[InvoiceRecord] = relationship(back_populates="transmissions")


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("company_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # superfaktura | money_s3 | pohoda
    credentials: Mapped[str] = mapped_column(Text)  # encrypted JSON
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    webhook_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only, hash-chained audit trail (tamper-evident)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32), default="")
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
