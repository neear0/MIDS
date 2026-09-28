import httpx
import pytest

from app.peppol.access_point import (
    DOCTYPE_INVOICE,
    AccessPointError,
    HttpAccessPoint,
    MockAccessPoint,
    PermanentAccessPointError,
    participant,
)
from tests.conftest import register
from tests.factories import BUYER_DIC, COMPANY


def _invoice_body():
    return {
        "buyer_reference": "Jana", "seller": {},
        "buyer": {"name": "Odberateľ a.s.", "ico": "35757442", "dic": BUYER_DIC, "ic_dph": f"SK{BUYER_DIC}",
                  "address": {"street": "Mlynská 2", "city": "Košice", "postal_code": "04001"}},
        "lines": [{"name": "Služba", "quantity": "1", "unit_price": "100", "vat_rate": "23"}],
    }


def test_send_and_receive_between_platform_companies(client, auth, company_id):
    # Buyer is another customer of the platform with its own login.
    buyer_auth = register(client, "buyer@example.sk")
    buyer = client.post("/api/v1/companies", headers=buyer_auth, json={
        **COMPANY, "name": "Odberateľ a.s.", "ico": "35757442", "dic": BUYER_DIC, "ic_dph": f"SK{BUYER_DIC}"})
    buyer_id = buyer.json()["id"]

    created = client.post(f"/api/v1/companies/{company_id}/invoices", json=_invoice_body(), headers=auth).json()
    assert created["status"] == "valid", created["validation"]
    sent = client.post(f"/api/v1/companies/{company_id}/invoices/{created['id']}/send", headers=auth)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "delivered"
    assert body["transmissions"][0]["tax_report_status"] == "reported"

    # A sent invoice is immutable and cannot be sent twice.
    again = client.post(f"/api/v1/companies/{company_id}/invoices/{created['id']}/send", headers=auth)
    assert again.status_code == 409
    edit = client.put(f"/api/v1/companies/{company_id}/invoices/{created['id']}", json=_invoice_body(), headers=auth)
    assert edit.status_code == 409 and "dobropis" in edit.json()["detail"]

    received = client.post(f"/api/v1/companies/{buyer_id}/peppol/poll", headers=buyer_auth).json()
    assert received == {"received": 1}
    inbox = client.get(f"/api/v1/companies/{buyer_id}/invoices?direction=incoming", headers=buyer_auth).json()
    assert len(inbox) == 1 and inbox[0]["counterparty_name"] == "Dodávateľ s.r.o."
    assert inbox[0]["status"] == "received" and inbox[0]["error_count"] == 0
    assert client.post(f"/api/v1/companies/{buyer_id}/peppol/poll", headers=buyer_auth).json() == {"received": 0}


def test_invalid_invoice_cannot_be_sent(client, auth, company_id):
    body = _invoice_body()
    body["lines"][0]["vat_rate"] = "20"  # pre-2025 rate
    created = client.post(f"/api/v1/companies/{company_id}/invoices", json=body, headers=auth).json()
    assert created["status"] == "invalid"
    resp = client.post(f"/api/v1/companies/{company_id}/invoices/{created['id']}/send", headers=auth)
    assert resp.status_code == 409


def test_mock_rejects_unknown_receiver():
    ap = MockAccessPoint(accept_unknown_receivers=False)
    with pytest.raises(PermanentAccessPointError):
        ap.send(b"<x/>", sender="a", receiver=participant("0245", "1"), document_type=DOCTYPE_INVOICE)


def test_retry_then_failure_is_recorded(client, auth, company_id):
    from app.db import SessionLocal
    from app.models import InvoiceRecord, Transmission
    from app.peppol import service

    class FlakyAP(MockAccessPoint):
        def send(self, *a, **k):
            raise AccessPointError("timeout")

    created = client.post(f"/api/v1/companies/{company_id}/invoices", json=_invoice_body(), headers=auth).json()
    ap = FlakyAP()
    with SessionLocal() as db:
        record = db.get(InvoiceRecord, created["id"])
        service.queue(db, record, ap, user_id=None)
        db.commit()
        service.process_outbox(db, ap)
        t = db.query(Transmission).one()
        assert t.status == "queued" and t.attempts == 1 and t.last_error == "timeout"
        assert t.next_attempt_at is not None
        service.process_outbox(db, ap)  # backoff: not due yet
        assert db.query(Transmission).one().attempts == 1


def test_http_access_point_adapter():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.headers)))
        if request.url.path == "/documents":
            return httpx.Response(201, json={"id": "m-1", "status": "sent"})
        if request.url.path == "/documents/m-1":
            return httpx.Response(200, json={"status": "delivered", "tax_report_status": "reported"})
        return httpx.Response(503)

    ap = HttpAccessPoint("https://ap.example", "secret", transport=httpx.MockTransport(handler))
    receipt = ap.send(b"<Invoice/>", sender="s", receiver="r", document_type=DOCTYPE_INVOICE)
    assert receipt.message_id == "m-1"
    assert calls[0][2]["authorization"] == "Bearer secret"
    assert calls[0][2]["x-peppol-document-type"] == DOCTYPE_INVOICE
    assert ap.status("m-1").tax_report_status == "reported"
    with pytest.raises(AccessPointError):
        ap.fetch_inbox("p")
