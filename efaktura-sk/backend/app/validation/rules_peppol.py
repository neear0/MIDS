"""Peppol BIS Billing 3.0 rules (subset)."""

from __future__ import annotations

from collections.abc import Iterator

from app.domain.invoice import Invoice
from app.ubl.generator import CUSTOMIZATION_ID, PROFILE_ID
from app.validation.engine import Issue, Severity, ValidationContext, rule


@rule("PEPPOL-EN16931-R001", source="PEPPOL")
def business_process(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if ctx.from_xml and not ctx.profile_id:
        yield Issue("Chýba identifikátor obchodného procesu (ProfileID).", "Business process (BT-23) missing.",
                    "BT-23")
    elif ctx.from_xml and ctx.profile_id != PROFILE_ID:
        yield Issue("Neznámy obchodný proces (ProfileID) pre Peppol BIS Billing 3.0.",
                    f"Unexpected ProfileID {ctx.profile_id}.", "BT-23", severity=Severity.WARNING)


@rule("PEPPOL-EN16931-R004", source="PEPPOL")
def specification_identifier(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if ctx.from_xml and ctx.customization_id != CUSTOMIZATION_ID:
        yield Issue("Dokument nedeklaruje súlad s Peppol BIS Billing 3.0 (CustomizationID).",
                    "Specification identifier must be the Peppol BIS Billing 3.0 id.", "BT-24")


@rule("PEPPOL-EN16931-R003", source="PEPPOL")
def buyer_or_order_reference(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if not (inv.buyer_reference or inv.order_reference):
        yield Issue("Chýba referencia odberateľa alebo číslo objednávky.",
                    "A buyer reference or purchase order reference must be provided.", "BT-10/BT-13",
                    "Ak odberateľ nič nepožaduje, stačí uviesť napr. meno kontaktnej osoby alebo číslo zmluvy.")


@rule("PEPPOL-EN16931-R020", source="PEPPOL")
def seller_endpoint(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if not inv.seller.resolved_endpoint()[1]:
        yield Issue("Chýba elektronická adresa dodávateľa v sieti Peppol.", "Seller electronic address missing.",
                    "BT-34", "Pre slovenské firmy sa používa DIČ so schémou 0245.")


@rule("PEPPOL-EN16931-R010", source="PEPPOL")
def buyer_endpoint(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if not inv.buyer.resolved_endpoint()[1]:
        yield Issue("Chýba elektronická adresa odberateľa v sieti Peppol.", "Buyer electronic address missing.",
                    "BT-49", "Doplňte DIČ odberateľa – z neho sa odvodí adresa 0245:DIČ.")


@rule("PEPPOL-EN16931-R053", source="PEPPOL")
def single_tax_total(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.tax_currency and inv.tax_currency != inv.currency and inv.tax_amount_in_tax_currency is None:
        yield Issue(f"Pri mene účtovania {inv.tax_currency} musí byť uvedená celková DPH aj v tejto mene.",
                    "VAT total in tax currency (BT-111) required when BT-6 is set.", "BT-111")
