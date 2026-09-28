"""Canonical invoice model, aligned with the EN 16931 semantic model.

Every field carries the EN 16931 business term (BT-/BG-) it maps to, so the
UBL generator, the validator and the AI extractor all speak the same language.
Amounts are ``Decimal`` and rounded half-up to 2 decimals, as EN 16931 requires.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

TWO_PLACES = Decimal("0.01")


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class DocumentType(StrEnum):
    INVOICE = "380"  # Commercial invoice
    CREDIT_NOTE = "381"  # Credit note (dobropis)
    CORRECTED_INVOICE = "384"  # Corrected invoice (opravná faktúra)
    PREPAYMENT_INVOICE = "386"  # Prepayment invoice (zálohová faktúra)


class VatCategory(StrEnum):
    """UNCL5305 subset used by Peppol BIS Billing 3.0 (BT-118 / BT-151)."""

    STANDARD = "S"
    ZERO = "Z"
    EXEMPT = "E"
    REVERSE_CHARGE = "AE"
    INTRA_COMMUNITY = "K"
    EXPORT = "G"
    NOT_SUBJECT = "O"


class Address(BaseModel):
    street: str | None = None  # BT-35 / BT-50
    additional_street: str | None = None  # BT-36 / BT-51
    city: str | None = None  # BT-37 / BT-52
    postal_code: str | None = None  # BT-38 / BT-53
    country_code: str = "SK"  # BT-40 / BT-55


class Party(BaseModel):
    """Seller (BG-4) or buyer (BG-7)."""

    name: str = ""  # BT-27 / BT-44
    trading_name: str | None = None  # BT-28 / BT-45
    ico: str | None = None  # IČO, legal registration id (BT-30 / BT-47)
    dic: str | None = None  # DIČ, tax id — Peppol endpoint under scheme 0245
    ic_dph: str | None = None  # IČ DPH, VAT id "SK" + 10 digits (BT-31 / BT-48)
    address: Address = Field(default_factory=Address)
    endpoint_id: str | None = None  # BT-34 / BT-49 (defaults to DIČ)
    endpoint_scheme: str | None = None  # EAS code (defaults to 0245 for SK)
    email: str | None = None
    phone: str | None = None
    registration_note: str | None = None  # e.g. "Zapísaná v OR OS Bratislava I"

    def resolved_endpoint(self) -> tuple[str | None, str | None]:
        if self.endpoint_id:
            return self.endpoint_scheme, self.endpoint_id
        if self.dic:
            return "0245", self.dic
        return None, None


class InvoiceLine(BaseModel):
    """Invoice line (BG-25)."""

    id: str = "1"  # BT-126
    name: str = ""  # BT-153
    description: str | None = None  # BT-154
    quantity: Decimal = Decimal("1")  # BT-129
    unit_code: str = "C62"  # BT-130, UN/ECE Rec 20 ("C62" = piece / ks)
    unit_price: Decimal = Decimal("0")  # BT-146 net price
    vat_category: VatCategory = VatCategory.STANDARD  # BT-151
    vat_rate: Decimal = Decimal("23")  # BT-152
    line_discount: Decimal = Decimal("0")  # BT-136 line allowance amount

    @property
    def net_amount(self) -> Decimal:  # BT-131
        return money(self.quantity * self.unit_price - self.line_discount)


class VatBreakdown(BaseModel):
    """VAT breakdown (BG-23)."""

    category: VatCategory
    rate: Decimal
    taxable_amount: Decimal  # BT-116
    tax_amount: Decimal  # BT-117
    exemption_reason: str | None = None  # BT-120
    exemption_reason_code: str | None = None  # BT-121


class Totals(BaseModel):
    """Document totals (BG-22)."""

    line_extension: Decimal  # BT-106
    tax_exclusive: Decimal  # BT-109
    tax_amount: Decimal  # BT-110
    tax_inclusive: Decimal  # BT-112
    prepaid: Decimal  # BT-113
    payable: Decimal  # BT-115
    tax_amount_in_tax_currency: Decimal | None = None  # BT-111


class Payment(BaseModel):
    means_code: str = "30"  # BT-81 (30 = credit transfer, 58 = SEPA credit transfer)
    iban: str | None = None  # BT-84
    bic: str | None = None  # BT-86
    account_name: str | None = None  # BT-85
    variable_symbol: str | None = None  # BT-83 remittance information (VS)
    constant_symbol: str | None = None
    specific_symbol: str | None = None
    terms: str | None = None  # BT-20


class PrecedingInvoice(BaseModel):
    """Reference to the invoice being corrected (BG-3)."""

    number: str  # BT-25
    issue_date: date | None = None  # BT-26


EXEMPTION_DEFAULTS: dict[VatCategory, tuple[str, str]] = {
    VatCategory.REVERSE_CHARGE: ("VATEX-EU-AE", "Prenesenie daňovej povinnosti"),
    VatCategory.INTRA_COMMUNITY: (
        "VATEX-EU-IC",
        "Dodanie tovaru oslobodené od dane podľa § 43 zákona o DPH",
    ),
    VatCategory.EXPORT: ("VATEX-EU-G", "Vývoz tovaru oslobodený od dane"),
    VatCategory.NOT_SUBJECT: ("VATEX-EU-O", "Nepodlieha DPH"),
    VatCategory.EXEMPT: ("VATEX-EU-132", "Oslobodené od dane"),
}


class Invoice(BaseModel):
    """An invoice or credit note (EN 16931 core invoice)."""

    number: str = ""  # BT-1
    document_type: DocumentType = DocumentType.INVOICE  # BT-3
    issue_date: date | None = None  # BT-2
    due_date: date | None = None  # BT-9
    delivery_date: date | None = None  # BT-72 (dátum dodania)
    currency: str = "EUR"  # BT-5
    tax_currency: str | None = None  # BT-6
    tax_amount_in_tax_currency: Decimal | None = None  # BT-111
    buyer_reference: str | None = None  # BT-10
    order_reference: str | None = None  # BT-13
    notes: list[str] = Field(default_factory=list)  # BT-22
    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)
    lines: list[InvoiceLine] = Field(default_factory=list)
    payment: Payment = Field(default_factory=Payment)
    prepaid_amount: Decimal = Decimal("0")  # BT-113
    preceding_invoice: PrecedingInvoice | None = None
    # Overrides when importing an existing document; normally computed.
    declared_totals: Totals | None = None

    @property
    def is_credit_note(self) -> bool:
        return self.document_type == DocumentType.CREDIT_NOTE

    def vat_breakdown(self) -> list[VatBreakdown]:
        groups: dict[tuple[VatCategory, Decimal], Decimal] = {}
        for line in self.lines:
            rate = Decimal("0") if line.vat_category != VatCategory.STANDARD else line.vat_rate
            key = (line.vat_category, money(rate))
            groups[key] = groups.get(key, Decimal("0")) + line.net_amount
        result = []
        for (category, rate), taxable in sorted(groups.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
            code, reason = EXEMPTION_DEFAULTS.get(category, (None, None))
            result.append(
                VatBreakdown(
                    category=category,
                    rate=rate,
                    taxable_amount=money(taxable),
                    tax_amount=money(taxable * rate / 100),
                    exemption_reason=reason,
                    exemption_reason_code=code,
                )
            )
        return result

    def computed_totals(self) -> Totals:
        line_extension = money(sum((line.net_amount for line in self.lines), Decimal("0")))
        tax = money(sum((b.tax_amount for b in self.vat_breakdown()), Decimal("0")))
        tax_inclusive = money(line_extension + tax)
        prepaid = money(self.prepaid_amount)
        return Totals(
            line_extension=line_extension,
            tax_exclusive=line_extension,
            tax_amount=tax,
            tax_inclusive=tax_inclusive,
            prepaid=prepaid,
            payable=money(tax_inclusive - prepaid),
            tax_amount_in_tax_currency=self.tax_amount_in_tax_currency,
        )

    def totals(self) -> Totals:
        return self.declared_totals or self.computed_totals()
