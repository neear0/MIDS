"""Generated UBL must pass the official CEN EN 16931 + Peppol BIS 3.0 Schematron.

Runs when SCHEMATRON_DIR points at compiled stylesheets (see
scripts/fetch_validation_artifacts.sh); CI always provides them.
"""

import os
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.domain.invoice import DocumentType, PrecedingInvoice, VatCategory
from app.ubl.generator import to_ubl_xml
from app.validation import schematron
from tests.factories import invoice

SCHEMATRON_DIR = Path(os.environ.get("SCHEMATRON_DIR", "validation-artifacts"))
pytestmark = pytest.mark.skipif(not schematron.available(SCHEMATRON_DIR), reason="Schematron artefacts not installed")


def _variants():
    yield "invoice", invoice()
    yield "credit-note", invoice(document_type=DocumentType.CREDIT_NOTE, number="D20270001",
                                 preceding_invoice=PrecedingInvoice(number="20270001"))
    rc = invoice(notes=["Prenesenie daňovej povinnosti"], prepaid_amount=D("100"))
    for line in rc.lines:
        line.vat_category = VatCategory.REVERSE_CHARGE
    rc.lines[0].line_discount = D("25")
    yield "reverse-charge", rc
    yield "foreign-currency", invoice(currency="CZK", tax_currency="EUR", tax_amount_in_tax_currency=D("4.62"))
    mixed = invoice()
    mixed.lines[1].vat_category = VatCategory.EXEMPT
    yield "mixed-exempt", mixed
    non_payer = invoice()
    non_payer.seller.ic_dph = None
    for line in non_payer.lines:
        line.vat_category = VatCategory.NOT_SUBJECT
    yield "non-vat-payer", non_payer


@pytest.mark.parametrize("name,inv", list(_variants()), ids=lambda v: v if isinstance(v, str) else "")
def test_official_rules_pass(name, inv):
    errors = [f for f in schematron.validate(to_ubl_xml(inv), SCHEMATRON_DIR) if f.severity == "error"]
    assert not errors, [(f.rule_id, f.message_en) for f in errors]


def test_official_rules_catch_errors():
    inv = invoice(buyer_reference=None)
    inv.payment.iban = None
    found = {f.rule_id for f in schematron.validate(to_ubl_xml(inv), SCHEMATRON_DIR)}
    assert {"BR-61", "PEPPOL-EN16931-R003"} <= found
