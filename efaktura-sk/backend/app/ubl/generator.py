"""UBL 2.1 generation following Peppol BIS Billing 3.0.

Element order follows the UBL 2.1 XSD sequence, which the Peppol validators
enforce. Credit notes (381) are produced as a UBL ``CreditNote`` document.
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

from app.domain.invoice import Invoice, InvoiceLine, Party, VatCategory, money

CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


def _cbc(parent: etree._Element, tag: str, text: object | None = None, **attrs: str) -> etree._Element | None:
    if text is None or text == "":
        return None
    el = etree.SubElement(parent, f"{{{NS_CBC}}}{tag}", **attrs)
    el.text = str(text)
    return el


def _cac(parent: etree._Element, tag: str) -> etree._Element:
    return etree.SubElement(parent, f"{{{NS_CAC}}}{tag}")


def _amount(parent: etree._Element, tag: str, value: Decimal, currency: str) -> None:
    _cbc(parent, tag, f"{money(value):.2f}", currencyID=currency)


def _fmt_rate(rate: Decimal) -> str:
    return f"{Decimal(rate).normalize():f}"


def _party(parent: etree._Element, wrapper: str, party: Party, *, is_seller: bool, vat_ids: bool = True) -> None:
    outer = _cac(parent, wrapper)
    p = _cac(outer, "Party")
    scheme, endpoint = party.resolved_endpoint()
    if endpoint:
        _cbc(p, "EndpointID", endpoint, schemeID=scheme or "0245")
    if party.ico:
        ident = _cac(p, "PartyIdentification")
        _cbc(ident, "ID", party.ico)
    if party.trading_name:
        _cbc(_cac(p, "PartyName"), "Name", party.trading_name)
    addr = _cac(p, "PostalAddress")
    _cbc(addr, "StreetName", party.address.street)
    _cbc(addr, "AdditionalStreetName", party.address.additional_street)
    _cbc(addr, "CityName", party.address.city)
    _cbc(addr, "PostalZone", party.address.postal_code)
    _cbc(_cac(addr, "Country"), "IdentificationCode", party.address.country_code)
    if party.ic_dph and vat_ids:
        tax = _cac(p, "PartyTaxScheme")
        _cbc(tax, "CompanyID", party.ic_dph)
        _cbc(_cac(tax, "TaxScheme"), "ID", "VAT")
    if is_seller and party.dic:
        # BT-32 seller tax registration id (DIČ), carried as a non-VAT tax scheme.
        tax = _cac(p, "PartyTaxScheme")
        _cbc(tax, "CompanyID", party.dic)
        _cbc(_cac(tax, "TaxScheme"), "ID", "TAX")
    legal = _cac(p, "PartyLegalEntity")
    _cbc(legal, "RegistrationName", party.name)
    _cbc(legal, "CompanyID", party.ico)
    _cbc(legal, "CompanyLegalForm", party.registration_note)
    if party.email or party.phone:
        contact = _cac(p, "Contact")
        _cbc(contact, "Telephone", party.phone)
        _cbc(contact, "ElectronicMail", party.email)


def _tax_category(parent: etree._Element, tag: str, category: VatCategory, rate: Decimal,
                  reason_code: str | None = None, reason: str | None = None) -> None:
    cat = _cac(parent, tag)
    _cbc(cat, "ID", category.value)
    if category != VatCategory.NOT_SUBJECT:
        _cbc(cat, "Percent", _fmt_rate(rate))
    if tag == "TaxCategory":
        _cbc(cat, "TaxExemptionReasonCode", reason_code)
        _cbc(cat, "TaxExemptionReason", reason)
    _cbc(_cac(cat, "TaxScheme"), "ID", "VAT")


def _line(parent: etree._Element, line: InvoiceLine, currency: str, credit: bool) -> None:
    el = _cac(parent, "CreditNoteLine" if credit else "InvoiceLine")
    _cbc(el, "ID", line.id)
    _cbc(el, "CreditedQuantity" if credit else "InvoicedQuantity", f"{line.quantity.normalize():f}",
         unitCode=line.unit_code)
    _amount(el, "LineExtensionAmount", line.net_amount, currency)
    if line.line_discount:
        ac = _cac(el, "AllowanceCharge")
        _cbc(ac, "ChargeIndicator", "false")
        _cbc(ac, "AllowanceChargeReasonCode", "95")  # Discount
        _cbc(ac, "AllowanceChargeReason", "Zľava")
        _amount(ac, "Amount", line.line_discount, currency)
    item = _cac(el, "Item")
    _cbc(item, "Description", line.description)
    _cbc(item, "Name", line.name)
    rate = line.vat_rate if line.vat_category == VatCategory.STANDARD else Decimal("0")
    _tax_category(item, "ClassifiedTaxCategory", line.vat_category, rate)
    price = _cac(el, "Price")
    _cbc(price, "PriceAmount", f"{Decimal(line.unit_price).normalize():f}", currencyID=currency)


def build_ubl(invoice: Invoice) -> etree._Element:
    credit = invoice.is_credit_note
    ns_root = NS_CREDIT_NOTE if credit else NS_INVOICE
    root = etree.Element(
        f"{{{ns_root}}}{'CreditNote' if credit else 'Invoice'}",
        nsmap={None: ns_root, "cac": NS_CAC, "cbc": NS_CBC},
    )
    cur = invoice.currency
    totals = invoice.totals()

    _cbc(root, "CustomizationID", CUSTOMIZATION_ID)
    _cbc(root, "ProfileID", PROFILE_ID)
    _cbc(root, "ID", invoice.number)
    _cbc(root, "IssueDate", invoice.issue_date.isoformat() if invoice.issue_date else None)
    if not credit and invoice.due_date:
        _cbc(root, "DueDate", invoice.due_date.isoformat())
    _cbc(root, "CreditNoteTypeCode" if credit else "InvoiceTypeCode", invoice.document_type.value)
    for note in invoice.notes:
        _cbc(root, "Note", note)
    _cbc(root, "DocumentCurrencyCode", cur)
    if invoice.tax_currency and invoice.tax_currency != cur:
        _cbc(root, "TaxCurrencyCode", invoice.tax_currency)
    _cbc(root, "BuyerReference", invoice.buyer_reference)
    if invoice.order_reference:
        _cbc(_cac(root, "OrderReference"), "ID", invoice.order_reference)
    if invoice.preceding_invoice:
        ref = _cac(_cac(root, "BillingReference"), "InvoiceDocumentReference")
        _cbc(ref, "ID", invoice.preceding_invoice.number)
        if invoice.preceding_invoice.issue_date:
            _cbc(ref, "IssueDate", invoice.preceding_invoice.issue_date.isoformat())

    # BR-O-02..04: documents outside the scope of VAT must not carry VAT identifiers.
    vat_ids = not any(line.vat_category == VatCategory.NOT_SUBJECT for line in invoice.lines)
    _party(root, "AccountingSupplierParty", invoice.seller, is_seller=True, vat_ids=vat_ids)
    _party(root, "AccountingCustomerParty", invoice.buyer, is_seller=False, vat_ids=vat_ids)

    if invoice.delivery_date:
        _cbc(_cac(root, "Delivery"), "ActualDeliveryDate", invoice.delivery_date.isoformat())

    pay = invoice.payment
    if pay.iban or pay.variable_symbol or (credit and invoice.due_date):
        pm = _cac(root, "PaymentMeans")
        _cbc(pm, "PaymentMeansCode", pay.means_code)
        if credit and invoice.due_date:
            _cbc(pm, "PaymentDueDate", invoice.due_date.isoformat())
        _cbc(pm, "PaymentID", pay.variable_symbol)
        if pay.iban:
            acct = _cac(pm, "PayeeFinancialAccount")
            _cbc(acct, "ID", pay.iban)
            _cbc(acct, "Name", pay.account_name)
            if pay.bic:
                _cbc(_cac(acct, "FinancialInstitutionBranch"), "ID", pay.bic)
    if pay.terms:
        _cbc(_cac(root, "PaymentTerms"), "Note", pay.terms)

    tax_total = _cac(root, "TaxTotal")
    _amount(tax_total, "TaxAmount", totals.tax_amount, cur)
    for b in invoice.vat_breakdown():
        sub = _cac(tax_total, "TaxSubtotal")
        _amount(sub, "TaxableAmount", b.taxable_amount, cur)
        _amount(sub, "TaxAmount", b.tax_amount, cur)
        _tax_category(sub, "TaxCategory", b.category, b.rate, b.exemption_reason_code, b.exemption_reason)
    if invoice.tax_currency and invoice.tax_currency != cur and invoice.tax_amount_in_tax_currency is not None:
        # BT-111: VAT total in accounting currency (EUR for Slovak VAT).
        tt = _cac(root, "TaxTotal")
        _amount(tt, "TaxAmount", invoice.tax_amount_in_tax_currency, invoice.tax_currency)

    lmt = _cac(root, "LegalMonetaryTotal")
    _amount(lmt, "LineExtensionAmount", totals.line_extension, cur)
    _amount(lmt, "TaxExclusiveAmount", totals.tax_exclusive, cur)
    _amount(lmt, "TaxInclusiveAmount", totals.tax_inclusive, cur)
    if totals.prepaid:
        _amount(lmt, "PrepaidAmount", totals.prepaid, cur)
    _amount(lmt, "PayableAmount", totals.payable, cur)

    for line in invoice.lines:
        _line(root, line, cur, credit)
    return root


def to_ubl_xml(invoice: Invoice) -> bytes:
    return etree.tostring(build_ubl(invoice), xml_declaration=True, encoding="UTF-8", pretty_print=True)
