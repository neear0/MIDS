from decimal import Decimal as D

from lxml import etree

from app.domain.invoice import DocumentType, PrecedingInvoice, VatCategory
from app.ubl.generator import CUSTOMIZATION_ID, NS_CAC, NS_CBC, to_ubl_xml
from app.ubl.parser import parse_ubl
from tests.factories import invoice

NS = {"cac": NS_CAC, "cbc": NS_CBC}


def test_totals_and_vat_breakdown():
    inv = invoice()
    t = inv.computed_totals()
    assert t.line_extension == D("525.00")
    assert t.tax_amount == D("116.25")  # 500 × 23 % + 25 × 5 %
    assert t.payable == D("641.25")
    rates = {(b.category, b.rate): b.tax_amount for b in inv.vat_breakdown()}
    assert rates == {(VatCategory.STANDARD, D("23.00")): D("115.00"), (VatCategory.STANDARD, D("5.00")): D("1.25")}


def test_generates_peppol_invoice():
    root = etree.fromstring(to_ubl_xml(invoice()))
    assert root.findtext("cbc:CustomizationID", namespaces=NS) == CUSTOMIZATION_ID
    assert root.findtext("cbc:InvoiceTypeCode", namespaces=NS) == "380"
    endpoint = root.find("cac:AccountingSupplierParty/cac:Party/cbc:EndpointID", NS)
    assert endpoint.get("schemeID") == "0245" and endpoint.text == "2020123457"
    assert root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS) == "641.25"
    assert len(root.findall("cac:InvoiceLine", NS)) == 2


def test_credit_note_uses_creditnote_document():
    inv = invoice(document_type=DocumentType.CREDIT_NOTE, number="D1",
                  preceding_invoice=PrecedingInvoice(number="20270001"))
    root = etree.fromstring(to_ubl_xml(inv))
    assert etree.QName(root).localname == "CreditNote"
    assert root.findtext("cbc:CreditNoteTypeCode", namespaces=NS) == "381"
    assert root.find("cbc:DueDate", NS) is None  # not allowed in UBL CreditNote; goes to PaymentMeans
    assert root.findtext("cac:PaymentMeans/cbc:PaymentDueDate", namespaces=NS) == "2027-01-19"
    assert root.findtext("cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID", namespaces=NS) == "20270001"
    assert root.findall("cac:CreditNoteLine", NS)


def test_roundtrip():
    original = invoice(notes=["Ďakujeme za nákup"])
    parsed = parse_ubl(to_ubl_xml(original))
    assert parsed.number == original.number
    assert parsed.seller.dic == original.seller.dic and parsed.buyer.ic_dph == original.buyer.ic_dph
    assert parsed.lines[0].unit_code == "HUR"
    assert parsed.totals() == original.computed_totals()
    assert parsed.notes == ["Ďakujeme za nákup"]


def test_parser_rejects_non_ubl():
    import pytest

    from app.ubl.parser import UblParseError

    with pytest.raises(UblParseError):
        parse_ubl(b"<foo/>")
    with pytest.raises(UblParseError):
        parse_ubl(b"not xml")
