from tests.conftest import register
from tests.factories import COMPANY


def _body(**kw):
    body = {
        "buyer_reference": "Jana",
        "buyer": {"name": "Odberateľ a.s.", "ico": "35757442", "dic": "2020261342", "ic_dph": "SK2020261342",
                  "address": {"street": "Mlynská 2", "city": "Košice", "postal_code": "04001"}},
        "lines": [{"name": "Konzultácie", "quantity": "10", "unit_code": "HUR", "unit_price": "50"},
                  {"name": "Kniha", "quantity": "2", "unit_price": "12.5", "vat_rate": "5"}],
    }
    body.update(kw)
    return body


def test_auth_flow(client):
    headers = register(client)
    assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == "jana@example.sk"
    assert client.post("/api/v1/auth/login", json={"email": "jana@example.sk", "password": "zle"}).status_code == 401
    assert client.get("/api/v1/companies").status_code == 401
    assert client.post("/api/v1/auth/register", json={"email": "jana@example.sk", "password": "tajneheslo1"}
                       ).status_code == 409


def test_company_identifier_warnings(client, auth):
    resp = client.post("/api/v1/companies", json={**COMPANY, "ico": "12345678", "iban": "SK00"}, headers=auth)
    warnings = resp.json()["identifier_warnings"]
    assert any("IČO" in w for w in warnings) and any("IBAN" in w for w in warnings)


def test_invoice_lifecycle(client, auth, company_id):
    base = f"/api/v1/companies/{company_id}"
    created = client.post(f"{base}/invoices", json=_body(issue_date="2027-01-05"), headers=auth)
    assert created.status_code == 201, created.text
    inv = created.json()
    # Defaults filled in from the company profile.
    assert inv["number"] == "20270001" and inv["status"] == "valid"
    assert inv["invoice"]["seller"]["dic"] == COMPANY["dic"]
    assert inv["invoice"]["payment"]["iban"] == COMPANY["iban"]
    assert inv["invoice"]["payment"]["variable_symbol"] == "20270001"
    assert inv["due_date"] == "2027-01-19" and inv["total_payable"] == "641.25"

    second = client.post(f"{base}/invoices", json=_body(issue_date="2027-01-06"), headers=auth).json()
    assert second["number"] == "20270002"
    dup = client.post(f"{base}/invoices", json=_body(number="20270001"), headers=auth)
    assert dup.status_code == 409

    ubl = client.get(f"{base}/invoices/{inv['id']}/ubl", headers=auth)
    assert ubl.headers["content-type"].startswith("application/xml") and b"<cbc:ID>20270001</cbc:ID>" in ubl.content
    pdf = client.get(f"{base}/invoices/{inv['id']}/pdf", headers=auth)
    assert pdf.content.startswith(b"%PDF")

    credit = client.post(f"{base}/invoices/{inv['id']}/credit-note", json={"reason": "Vrátenie tovaru"},
                         headers=auth).json()
    assert credit["document_type"] == "381" and credit["status"] == "valid", credit["validation"]
    assert credit["invoice"]["preceding_invoice"]["number"] == "20270001"

    paid = client.post(f"{base}/invoices/{inv['id']}/paid?paid_on=2027-01-10", headers=auth).json()
    assert paid["paid_at"] == "2027-01-10"

    validation = client.post("/api/v1/validate", files={"file": ("f.xml", ubl.content, "application/xml")},
                             headers=auth).json()
    assert validation["valid"]

    audit = client.get(f"{base}/audit", headers=auth).json()
    assert audit["chain_intact"]
    assert {"invoice.created", "invoice.paid", "company.created"} <= {e["action"] for e in audit["events"]}


def test_live_draft_validation(client, auth):
    resp = client.post("/api/v1/validate/draft", json=_body(), headers=auth).json()
    assert not resp["valid"]  # no seller, number or dates in a bare draft
    assert any(f["rule_id"] == "BR-02" for f in resp["findings"])


def test_import_received_ubl(client, auth, company_id):
    from app.ubl.generator import to_ubl_xml
    from tests.factories import invoice

    xml = to_ubl_xml(invoice())
    resp = client.post(f"/api/v1/companies/{company_id}/invoices/import-ubl",
                       files={"file": ("in.xml", xml, "application/xml")}, headers=auth)
    assert resp.status_code == 201 and resp.json()["direction"] == "incoming"
    bad = client.post(f"/api/v1/companies/{company_id}/invoices/import-ubl",
                      files={"file": ("in.xml", b"<nope/>", "application/xml")}, headers=auth)
    assert bad.status_code == 422


def test_roles_and_tenant_isolation(client, auth, company_id):
    base = f"/api/v1/companies/{company_id}"
    viewer = register(client, "viewer@example.sk")
    other = register(client, "other@example.sk")
    assert client.post(f"{base}/members", json={"email": "viewer@example.sk", "role": "viewer"},
                       headers=auth).status_code == 201
    assert client.get(f"{base}/invoices", headers=viewer).status_code == 200
    assert client.post(f"{base}/invoices", json=_body(), headers=viewer).status_code == 403
    assert client.get(f"{base}/invoices", headers=other).status_code == 404
    assert client.get(f"{base}/audit", headers=viewer).status_code == 403


def test_dashboard(client, auth, company_id):
    base = f"/api/v1/companies/{company_id}"
    client.post(f"{base}/invoices", json=_body(issue_date="2025-03-01"), headers=auth)  # long overdue
    bad = _body()
    bad["lines"][0]["vat_rate"] = "21"
    client.post(f"{base}/invoices", json=bad, headers=auth)
    dash = client.get(f"{base}/dashboard", headers=auth).json()
    assert dash["counts"]["valid"] == 1 and dash["counts"]["invalid"] == 1
    assert dash["compliance_score"] == 50
    assert dash["receivables"]["overdue"][0]["days_overdue"] > 365
    assert len(dash["invalid_invoices"]) == 1
    assert {r["key"] for r in dash["readiness"]} >= {"dic", "iban", "peppol"}


def test_extract_and_explain(client, auth, company_id):
    from app.pdf.render import render_pdf
    from tests.factories import invoice

    pdf = render_pdf(invoice())
    resp = client.post(f"/api/v1/companies/{company_id}/extract",
                       files={"file": ("f.pdf", pdf, "application/pdf")}, headers=auth)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "heuristic" and data["invoice"]["number"] == "20270001"
    assert data["direction_guess"] == "outgoing"

    explained = client.post("/api/v1/explain", json={"rule_id": "SK-07"}, headers=auth).json()
    assert explained["sources"][0]["id"] == "dobropis"
