"""SuperFaktúra REST API client and mapping to/from the canonical invoice.

API reference: https://github.com/superfaktura/docs. Authentication is a single
header ``Authorization: SFAPI email=…&apikey=…&company_id=…&module=…``.
Field names below follow those docs; verify them against the sandbox
(https://sandbox.superfaktura.sk) when onboarding a new account type.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.domain.invoice import (
    Address,
    DocumentType,
    Invoice,
    InvoiceLine,
    Party,
    Payment,
    PrecedingInvoice,
    VatCategory,
    money,
)
from app.domain.parsing import parse_amount, parse_date

UNIT_CODES = {
    "ks": "C62", "kus": "C62", "ks.": "C62", "hod": "HUR", "hod.": "HUR", "h": "HUR", "kg": "KGM", "g": "GRM",
    "m": "MTR", "m2": "MTK", "m3": "MTQ", "km": "KMT", "l": "LTR", "deň": "DAY", "dni": "DAY", "mes": "MON",
    "mesiac": "MON", "bal": "XPK", "balenie": "XPK", "set": "SET", "t": "TNE",
}
UNIT_NAMES = {"C62": "ks", "HUR": "hod", "KGM": "kg", "MTR": "m", "DAY": "deň", "MON": "mes", "LTR": "l"}


class SuperFakturaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credentials:
    email: str
    api_key: str
    company_id: str | None = None
    sandbox: bool = False


class SuperFakturaClient:
    def __init__(self, creds: Credentials, base_url: str, *, transport: httpx.BaseTransport | None = None,
                 module: str = "eFaktura SK") -> None:
        auth = {"email": creds.email, "apikey": creds.api_key, "module": module}
        if creds.company_id:
            auth["company_id"] = creds.company_id
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=httpx.Timeout(20.0), transport=transport,
            headers={"Authorization": "SFAPI " + urlencode(auth), "Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(3):
            try:
                resp = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise SuperFakturaError(f"SuperFaktúra je nedostupná: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if resp.status_code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(float(resp.headers.get("Retry-After", 2**attempt)))
                continue
            if resp.status_code == 401:
                raise SuperFakturaError("SuperFaktúra odmietla prihlásenie – skontrolujte e-mail a API kľúč.")
            if resp.status_code >= 400:
                raise SuperFakturaError(f"SuperFaktúra vrátila chybu {resp.status_code}.")
            data = resp.json()
            if isinstance(data, dict) and data.get("error") not in (None, 0, "0", False):
                raise SuperFakturaError(str(data.get("error_message") or data.get("message") or data["error"]))
            return data
        raise SuperFakturaError("SuperFaktúra neodpovedá.")

    def list_invoices(self, page: int = 1, per_page: int = 50, modified_since: date | None = None) -> dict:
        path = f"/invoices/index.json/listinfo:1/page:{page}/per_page:{per_page}/sort:id/direction:ASC"
        if modified_since:
            # "modified:5" = custom range; since/to in YYYY-MM-DD per SuperFaktúra filter docs.
            path += f"/modified:5/modified_since:{modified_since.isoformat()}"
        return self._request("GET", path)

    def iter_invoices(self, modified_since: date | None = None, max_pages: int = 100):
        for page in range(1, max_pages + 1):
            data = self.list_invoices(page=page, modified_since=modified_since)
            items = data.get("items", []) if isinstance(data, dict) else data
            yield from items
            if page >= int((data or {}).get("pageCount", 1) if isinstance(data, dict) else 1):
                break

    def get_invoice(self, invoice_id: str | int) -> dict:
        return self._request("GET", f"/invoices/view/{invoice_id}.json")

    def create_invoice(self, payload: dict) -> dict:
        return self._request("POST", "/invoices/create", json=payload)


# ---------------------------------------------------------------------------- mapping

def _vat_line(rate: Decimal, vat_payer: bool) -> tuple[VatCategory, Decimal]:
    if not vat_payer:
        return VatCategory.NOT_SUBJECT, Decimal("0")
    if rate == 0:
        return VatCategory.ZERO, Decimal("0")
    return VatCategory.STANDARD, rate


def from_superfaktura(doc: dict, seller: Party) -> Invoice:
    """Map a SuperFaktúra invoice (``/invoices/view`` shape) to the canonical model.

    The seller comes from our company profile: SuperFaktúra's MyData block is
    not always complete, and the profile has been validated.
    """
    inv = doc.get("Invoice", {})
    client = doc.get("Client", {}) or {}
    items = doc.get("InvoiceItem", []) or []
    vat_payer = bool(seller.ic_dph)

    lines = []
    for i, item in enumerate(items, 1):
        qty = parse_amount(str(item.get("quantity") or "1")) or Decimal("1")
        price = parse_amount(str(item.get("unit_price") or "0")) or Decimal("0")
        discount_pct = parse_amount(str(item.get("discount") or "0")) or Decimal("0")
        category, rate = _vat_line(parse_amount(str(item.get("tax") or "0")) or Decimal("0"), vat_payer)
        unit = str(item.get("unit") or "ks").strip().lower()
        lines.append(InvoiceLine(
            id=str(i), name=item.get("name") or "Položka", description=item.get("description") or None,
            quantity=qty, unit_code=UNIT_CODES.get(unit, "C62"), unit_price=price,
            line_discount=money(qty * price * discount_pct / 100), vat_category=category, vat_rate=rate,
        ))

    sf_type = (inv.get("type") or "regular").lower()
    doc_type = {"cancel": DocumentType.CREDIT_NOTE, "proforma": DocumentType.PREPAYMENT_INVOICE}.get(
        sf_type, DocumentType.INVOICE)
    preceding = None
    if doc_type == DocumentType.CREDIT_NOTE and (inv.get("parent_invoice_no") or inv.get("parent_id")):
        preceding = PrecedingInvoice(number=str(inv.get("parent_invoice_no") or inv.get("parent_id")))

    buyer = Party(
        name=client.get("name") or "", ico=client.get("ico") or None, dic=client.get("dic") or None,
        ic_dph=client.get("ic_dph") or None, email=client.get("email") or None,
        address=Address(street=client.get("address") or None, city=client.get("city") or None,
                        postal_code=(client.get("zip") or "").replace(" ", "") or None,
                        country_code=(client.get("country_iso_id") or "SK").upper()),
    )
    notes = [inv["comment"]] if inv.get("comment") else []
    return Invoice(
        number=str(inv.get("invoice_no_formatted") or inv.get("id") or ""),
        document_type=doc_type,
        issue_date=parse_date(inv.get("created")),
        delivery_date=parse_date(inv.get("delivery")),
        due_date=parse_date(inv.get("due")),
        currency=inv.get("invoice_currency") or inv.get("currency") or "EUR",
        order_reference=inv.get("order_no") or None,
        buyer_reference=inv.get("order_no") or client.get("name") or None,
        seller=seller, buyer=buyer, lines=lines, notes=notes,
        payment=Payment(variable_symbol=str(inv.get("variable") or "") or None,
                        constant_symbol=inv.get("constant") or None, specific_symbol=inv.get("specific") or None),
        preceding_invoice=preceding,
    )


def to_superfaktura(invoice: Invoice) -> dict:
    """Canonical invoice → ``/invoices/create`` payload (for pushing documents created here)."""
    buyer = invoice.buyer
    return {
        "Invoice": {
            "name": f"Faktúra {invoice.number}",
            "invoice_no_formatted": invoice.number,
            "created": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "delivery": invoice.delivery_date.isoformat() if invoice.delivery_date else None,
            "due": invoice.due_date.isoformat() if invoice.due_date else None,
            "variable": invoice.payment.variable_symbol,
            "invoice_currency": invoice.currency,
            "type": "cancel" if invoice.is_credit_note else "regular",
            "order_no": invoice.order_reference,
            "comment": "\n".join(invoice.notes) or None,
        },
        "Client": {
            "name": buyer.name, "ico": buyer.ico, "dic": buyer.dic, "ic_dph": buyer.ic_dph,
            "address": buyer.address.street, "city": buyer.address.city, "zip": buyer.address.postal_code,
            "country_iso_id": buyer.address.country_code, "email": buyer.email,
        },
        "InvoiceItem": [
            {
                "name": line.name, "description": line.description or "",
                "quantity": float(line.quantity), "unit": UNIT_NAMES.get(line.unit_code, "ks"),
                "unit_price": float(line.unit_price), "tax": float(line.vat_rate),
                "discount": float(round(line.line_discount / (line.quantity * line.unit_price) * 100, 4))
                if line.line_discount and line.quantity * line.unit_price else 0,
            }
            for line in invoice.lines
        ],
    }
