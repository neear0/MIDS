import json
from decimal import Decimal as D
from urllib.parse import parse_qs

import httpx
import pytest

from app.domain.invoice import DocumentType, VatCategory
from app.integrations.superfaktura import (
    Credentials,
    SuperFakturaClient,
    SuperFakturaError,
    from_superfaktura,
    to_superfaktura,
)
from app.validation.engine import validate_invoice
from tests.factories import invoice, seller

SF_DOC = {
    "Invoice": {"id": "812", "invoice_no_formatted": "2027005", "created": "2027-01-10", "delivery": "2027-01-10",
                "due": "2027-01-24", "variable": "2027005", "invoice_currency": "EUR", "type": "regular",
                "order_no": "OBJ-44", "comment": "Ďakujeme"},
    "Client": {"name": "Odberateľ a.s.", "ico": "35757442", "dic": "2020261342", "ic_dph": "SK2020261342",
               "address": "Mlynská 2", "city": "Košice", "zip": "040 01", "country_iso_id": "SK"},
    "InvoiceItem": [
        {"name": "Webstránka", "quantity": "1", "unit": "ks", "unit_price": "800", "tax": "23", "discount": "10"},
        {"name": "Hosting", "quantity": "12", "unit": "mes", "unit_price": "5.5", "tax": "23", "discount": "0"},
    ],
}


def test_mapping_from_superfaktura():
    inv = from_superfaktura(SF_DOC, seller())
    assert inv.number == "2027005" and inv.order_reference == "OBJ-44"
    assert inv.buyer.address.postal_code == "04001"
    assert inv.lines[0].line_discount == D("80.00") and inv.lines[1].unit_code == "MON"
    assert inv.computed_totals().line_extension == D("786.00")
    assert inv.lines[0].vat_category == VatCategory.STANDARD
    inv.payment.iban = "SK3112000000198742637541"
    assert validate_invoice(inv).is_valid, validate_invoice(inv).as_dict()


def test_credit_note_type():
    doc = json.loads(json.dumps(SF_DOC))
    doc["Invoice"].update(type="cancel", parent_invoice_no="2027001")
    inv = from_superfaktura(doc, seller())
    assert inv.document_type == DocumentType.CREDIT_NOTE and inv.preceding_invoice.number == "2027001"


def test_non_vat_payer_lines():
    s = seller()
    s.ic_dph = None
    inv = from_superfaktura(SF_DOC, s)
    assert all(line.vat_category == VatCategory.NOT_SUBJECT for line in inv.lines)


def test_to_superfaktura_payload():
    payload = to_superfaktura(invoice())
    assert payload["Client"]["ic_dph"] == "SK2020261342"
    assert payload["InvoiceItem"][0] == {"name": "Konzultácie", "description": "", "quantity": 10.0, "unit": "hod",
                                         "unit_price": 50.0, "tax": 23.0, "discount": 0}


def test_client_auth_header_and_pagination():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = 1 if "page:1/" in request.url.path else 2
        return httpx.Response(200, json={"items": [SF_DOC] if page == 1 else [], "pageCount": 2})

    client = SuperFakturaClient(Credentials("a@b.sk", "KEY", "7"), "https://sandbox.superfaktura.sk",
                                transport=httpx.MockTransport(handler))
    items = list(client.iter_invoices())
    assert len(items) == 1 and len(seen) == 2
    auth = seen[0].headers["Authorization"]
    assert auth.startswith("SFAPI ")
    assert parse_qs(auth[6:]) == {"email": ["a@b.sk"], "apikey": ["KEY"], "module": ["eFaktura SK"],
                                  "company_id": ["7"]}


def test_client_errors():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={}))
    client = SuperFakturaClient(Credentials("a@b.sk", "bad"), "https://x", transport=transport)
    with pytest.raises(SuperFakturaError, match="API kľúč"):
        client.get_invoice(1)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"error": 1, "error_message": "Zlé dáta"}))
    client = SuperFakturaClient(Credentials("a@b.sk", "k"), "https://x", transport=transport)
    with pytest.raises(SuperFakturaError, match="Zlé dáta"):
        client.create_invoice({})


def test_sync_is_idempotent(client, auth, company_id):
    from app.db import SessionLocal
    from app.integrations import sync as sf_sync
    from app.models import Integration

    resp = client.put(f"/api/v1/companies/{company_id}/integrations/superfaktura",
                      json={"email": "a@b.sk", "api_key": "KEY", "sandbox": True}, headers=auth)
    assert resp.status_code == 200 and resp.json()["webhook_path"].startswith("/api/v1/webhooks/superfaktura/")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"items": [SF_DOC], "pageCount": 1}))
    with SessionLocal() as db:
        integ = db.query(Integration).one()
        assert "KEY" not in integ.credentials  # stored encrypted
        assert sf_sync.sync(db, integ, transport=transport) == {"created": 1, "updated": 0, "skipped": 0}
        assert sf_sync.sync(db, integ, transport=transport) == {"created": 0, "updated": 1, "skipped": 0}
    invoices = client.get(f"/api/v1/companies/{company_id}/invoices", headers=auth).json()
    assert len(invoices) == 1 and invoices[0]["source"] == "superfaktura" and invoices[0]["status"] == "valid"
