"""Parse a UBL 2.1 Invoice / CreditNote back into the canonical model.

Used for inbound Peppol documents and for validating XML uploaded by users.
Declared totals are kept so the validator can compare them with recomputed ones.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from app.domain.invoice import (
    Address,
    DocumentType,
    Invoice,
    InvoiceLine,
    Party,
    Payment,
    PrecedingInvoice,
    Totals,
    VatCategory,
)
from app.ubl.generator import NS_CAC, NS_CBC, NS_CREDIT_NOTE, NS_INVOICE

NS = {"cac": NS_CAC, "cbc": NS_CBC}


class UblParseError(ValueError):
    pass


def _t(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _d(value: str | None, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    try:
        return Decimal(value)
    except InvalidOperation:
        return default


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _party(el: etree._Element | None) -> Party:
    if el is None:
        return Party()
    p = el.find("cac:Party", NS)
    if p is None:
        return Party()
    endpoint = p.find("cbc:EndpointID", NS)
    ic_dph = dic = None
    for ts in p.findall("cac:PartyTaxScheme", NS):
        scheme = _t(ts, "cac:TaxScheme/cbc:ID")
        if scheme == "VAT":
            ic_dph = _t(ts, "cbc:CompanyID")
        else:
            dic = _t(ts, "cbc:CompanyID")
    scheme_id = endpoint.get("schemeID") if endpoint is not None else None
    endpoint_id = endpoint.text.strip() if endpoint is not None and endpoint.text else None
    if dic is None and scheme_id == "0245":
        dic = endpoint_id
    addr = p.find("cac:PostalAddress", NS)
    return Party(
        name=_t(p, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(p, "cac:PartyName/cbc:Name") or "",
        trading_name=_t(p, "cac:PartyName/cbc:Name"),
        ico=_t(p, "cac:PartyLegalEntity/cbc:CompanyID") or _t(p, "cac:PartyIdentification/cbc:ID"),
        dic=dic,
        ic_dph=ic_dph,
        endpoint_id=endpoint_id,
        endpoint_scheme=scheme_id,
        email=_t(p, "cac:Contact/cbc:ElectronicMail"),
        phone=_t(p, "cac:Contact/cbc:Telephone"),
        address=Address(
            street=_t(addr, "cbc:StreetName"),
            additional_street=_t(addr, "cbc:AdditionalStreetName"),
            city=_t(addr, "cbc:CityName"),
            postal_code=_t(addr, "cbc:PostalZone"),
            country_code=_t(addr, "cac:Country/cbc:IdentificationCode") or "",
        ),
    )


def _category(value: str | None) -> VatCategory:
    try:
        return VatCategory(value or "S")
    except ValueError:
        return VatCategory.STANDARD


def parse_ubl(xml: bytes | str) -> Invoice:
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml.encode() if isinstance(xml, str) else xml, parser)
    except etree.XMLSyntaxError as exc:
        raise UblParseError(f"Neplatné XML: {exc}") from exc

    qname = etree.QName(root)
    if qname.namespace not in (NS_INVOICE, NS_CREDIT_NOTE):
        raise UblParseError("Dokument nie je UBL 2.1 Invoice ani CreditNote.")
    credit = qname.namespace == NS_CREDIT_NOTE
    currency = _t(root, "cbc:DocumentCurrencyCode") or ""

    type_code = _t(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode")
    try:
        doc_type = DocumentType(type_code) if type_code else (
            DocumentType.CREDIT_NOTE if credit else DocumentType.INVOICE)
    except ValueError:
        doc_type = DocumentType.CREDIT_NOTE if credit else DocumentType.INVOICE

    lines = []
    for line_el in root.findall("cac:CreditNoteLine" if credit else "cac:InvoiceLine", NS):
        qty_el = line_el.find("cbc:CreditedQuantity" if credit else "cbc:InvoicedQuantity", NS)
        discount = Decimal("0")
        for ac in line_el.findall("cac:AllowanceCharge", NS):
            if _t(ac, "cbc:ChargeIndicator") == "false":
                discount += _d(_t(ac, "cbc:Amount"), Decimal("0"))
        lines.append(
            InvoiceLine(
                id=_t(line_el, "cbc:ID") or "",
                name=_t(line_el, "cac:Item/cbc:Name") or "",
                description=_t(line_el, "cac:Item/cbc:Description"),
                quantity=_d(qty_el.text if qty_el is not None else None, Decimal("0")),
                unit_code=(qty_el.get("unitCode") if qty_el is not None else None) or "",
                unit_price=_d(_t(line_el, "cac:Price/cbc:PriceAmount"), Decimal("0")),
                vat_category=_category(_t(line_el, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID")),
                vat_rate=_d(_t(line_el, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"), Decimal("0")),
                line_discount=discount,
            )
        )

    pm = root.find("cac:PaymentMeans", NS)
    tax_amount = Decimal("0")
    tax_in_tax_currency = None
    for tt in root.findall("cac:TaxTotal", NS):
        amt = tt.find("cbc:TaxAmount", NS)
        if amt is None:
            continue
        if amt.get("currencyID") == currency:
            tax_amount = _d(amt.text, Decimal("0"))
        else:
            tax_in_tax_currency = _d(amt.text)

    lmt = root.find("cac:LegalMonetaryTotal", NS)
    declared = Totals(
        line_extension=_d(_t(lmt, "cbc:LineExtensionAmount"), Decimal("0")),
        tax_exclusive=_d(_t(lmt, "cbc:TaxExclusiveAmount"), Decimal("0")),
        tax_amount=tax_amount,
        tax_inclusive=_d(_t(lmt, "cbc:TaxInclusiveAmount"), Decimal("0")),
        prepaid=_d(_t(lmt, "cbc:PrepaidAmount"), Decimal("0")),
        payable=_d(_t(lmt, "cbc:PayableAmount"), Decimal("0")),
        tax_amount_in_tax_currency=tax_in_tax_currency,
    )

    preceding = None
    ref_id = _t(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID")
    if ref_id:
        preceding = PrecedingInvoice(
            number=ref_id,
            issue_date=_date(_t(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:IssueDate")),
        )

    due = _t(root, "cbc:DueDate") or _t(pm, "cbc:PaymentDueDate")
    return Invoice(
        number=_t(root, "cbc:ID") or "",
        document_type=doc_type,
        issue_date=_date(_t(root, "cbc:IssueDate")),
        due_date=_date(due),
        delivery_date=_date(_t(root, "cac:Delivery/cbc:ActualDeliveryDate")),
        currency=currency,
        tax_currency=_t(root, "cbc:TaxCurrencyCode"),
        tax_amount_in_tax_currency=tax_in_tax_currency,
        buyer_reference=_t(root, "cbc:BuyerReference"),
        order_reference=_t(root, "cac:OrderReference/cbc:ID"),
        notes=[n.text for n in root.findall("cbc:Note", NS) if n.text],
        seller=_party(root.find("cac:AccountingSupplierParty", NS)),
        buyer=_party(root.find("cac:AccountingCustomerParty", NS)),
        lines=lines,
        payment=Payment(
            means_code=_t(pm, "cbc:PaymentMeansCode") or "",
            iban=_t(pm, "cac:PayeeFinancialAccount/cbc:ID"),
            bic=_t(pm, "cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID"),
            account_name=_t(pm, "cac:PayeeFinancialAccount/cbc:Name"),
            variable_symbol=_t(pm, "cbc:PaymentID"),
            terms=_t(root, "cac:PaymentTerms/cbc:Note"),
        ),
        prepaid_amount=declared.prepaid,
        preceding_invoice=preceding,
        declared_totals=declared,
    )


def document_metadata(xml: bytes) -> dict[str, str | None]:
    """Header fields the rules engine checks that are not part of the canonical model."""
    root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
    return {
        "customization_id": _t(root, "cbc:CustomizationID"),
        "profile_id": _t(root, "cbc:ProfileID"),
    }
