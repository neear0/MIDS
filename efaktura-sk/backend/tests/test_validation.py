from datetime import date
from decimal import Decimal as D

from app.domain.invoice import DocumentType, PrecedingInvoice, Totals, VatCategory
from app.ubl.generator import to_ubl_xml
from app.validation.engine import Severity, validate_invoice, validate_ubl
from tests.factories import invoice


def ids(result, severity=Severity.ERROR):
    return {f.rule_id for f in result.findings if f.severity == severity}


def test_valid_invoice_has_no_errors():
    result = validate_invoice(invoice())
    assert result.is_valid, [f.as_dict() for f in result.errors]


def test_generated_xml_is_valid():
    assert validate_ubl(to_ubl_xml(invoice())).is_valid


def test_missing_core_fields():
    inv = invoice(number="", issue_date=None, lines=[], buyer_reference=None)
    inv.buyer.name = ""
    assert {"BR-02", "BR-03", "BR-07", "BR-16", "PEPPOL-EN16931-R003"} <= ids(validate_invoice(inv))


def test_slovak_messages_and_hints():
    inv = invoice()
    inv.seller.ic_dph = "SK2020123456"
    finding = next(f for f in validate_invoice(inv).findings if f.rule_id == "SK-01")
    assert "IČ DPH dodávateľa" in finding.message_sk
    assert finding.hint_sk and "deliteľné 11" in finding.hint_sk


def test_old_vat_rate_rejected_after_2025():
    inv = invoice()
    inv.lines[0].vat_rate = D("20")
    assert "SK-05" in ids(validate_invoice(inv))
    inv.delivery_date = inv.issue_date = date(2024, 12, 20)
    inv.lines[1].vat_rate = D("10")
    assert "SK-05" not in ids(validate_invoice(inv))


def test_credit_note_requires_reference():
    inv = invoice(document_type=DocumentType.CREDIT_NOTE)
    assert "SK-07" in ids(validate_invoice(inv))
    inv.preceding_invoice = PrecedingInvoice(number="20260099")
    assert "SK-07" not in ids(validate_invoice(inv))


def test_reverse_charge_requires_wording():
    inv = invoice()
    for line in inv.lines:
        line.vat_category = VatCategory.REVERSE_CHARGE
    assert "SK-08" in ids(validate_invoice(inv), Severity.WARNING)
    inv.notes = ["Prenesenie daňovej povinnosti"]
    assert "SK-08" not in ids(validate_invoice(inv), Severity.WARNING)
    assert validate_invoice(inv).is_valid


def test_declared_totals_mismatch_detected():
    inv = invoice()
    t = inv.computed_totals()
    inv.declared_totals = Totals(**{**t.model_dump(), "line_extension": D("500.00"), "tax_amount": D("116.30")})
    errors = ids(validate_invoice(inv))
    assert {"BR-CO-10", "BR-CO-14", "BR-CO-15"} <= errors


def test_non_vat_payer():
    inv = invoice()
    inv.seller.ic_dph = None
    assert "BR-S-02" in ids(validate_invoice(inv))
    for line in inv.lines:
        line.vat_category = VatCategory.NOT_SUBJECT
    assert validate_invoice(inv).is_valid


def test_foreign_currency_needs_eur_vat():
    inv = invoice(currency="CZK")
    assert "SK-06" in ids(validate_invoice(inv))
    inv.tax_currency, inv.tax_amount_in_tax_currency = "EUR", D("4.62")
    assert validate_invoice(inv).is_valid


def test_malformed_xml_reported():
    result = validate_ubl(b"<Invoice>")
    assert not result.is_valid and result.findings[0].rule_id == "XML-01"
