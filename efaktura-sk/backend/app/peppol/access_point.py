"""Peppol Access Point ("digitálny poštár") adapters.

MVP strategy: partner with a certified Access Point that exposes a REST API.
Everything the platform needs from it is captured by :class:`AccessPoint`, so
switching partners — or becoming a certified AP ourselves later — only means
adding another implementation.

* :class:`MockAccessPoint` — development/demo. Delivers instantly and routes
  documents between companies registered on this same platform (loopback).
* :class:`HttpAccessPoint` — template for a partner REST API. Endpoint paths and
  field names are placeholders to map onto the chosen partner's documentation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

# Peppol identifiers for BIS Billing 3.0 (Peppol Policy for use of Identifiers).
PROCESS_ID = "cenbii-procid-ubl::urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
_DOC_SUFFIX = "##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"
DOCTYPE_INVOICE = "busdox-docid-qns::urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice" + _DOC_SUFFIX
DOCTYPE_CREDIT_NOTE = (
    "busdox-docid-qns::urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote" + _DOC_SUFFIX
)


class AccessPointError(RuntimeError):
    """Raised for failures worth retrying (network, 5xx)."""


class PermanentAccessPointError(AccessPointError):
    """Raised when retrying cannot help (receiver not in Peppol, document rejected)."""


@dataclass(frozen=True)
class SendReceipt:
    message_id: str
    status: str  # "sent" | "delivered"


@dataclass(frozen=True)
class DeliveryStatus:
    status: str  # "sent" | "delivered" | "failed"
    tax_report_status: str | None = None  # "reported" | "pending" | "rejected"
    error: str | None = None


@dataclass(frozen=True)
class InboundDocument:
    message_id: str
    receiver: str
    xml: bytes


def participant(scheme: str, value: str) -> str:
    return f"iso6523-actorid-upis::{scheme}:{value}"


class AccessPoint(Protocol):
    name: str

    def lookup(self, participant_id: str) -> bool: ...
    def send(self, xml: bytes, *, sender: str, receiver: str, document_type: str) -> SendReceipt: ...
    def status(self, message_id: str) -> DeliveryStatus: ...
    def fetch_inbox(self, participant_id: str) -> list[InboundDocument]: ...
    def acknowledge(self, message_id: str) -> None: ...


@dataclass
class MockAccessPoint:
    """In-process AP. ``registered`` holds participant ids known to the network."""

    name: str = "mock"
    registered: set[str] = field(default_factory=set)
    inboxes: dict[str, list[InboundDocument]] = field(default_factory=dict)
    statuses: dict[str, DeliveryStatus] = field(default_factory=dict)
    accept_unknown_receivers: bool = True

    def lookup(self, participant_id: str) -> bool:
        return self.accept_unknown_receivers or participant_id in self.registered

    def send(self, xml: bytes, *, sender: str, receiver: str, document_type: str) -> SendReceipt:
        if not self.lookup(receiver):
            raise PermanentAccessPointError(f"Príjemca {receiver} nie je registrovaný v sieti Peppol.")
        message_id = str(uuid.uuid4())
        self.inboxes.setdefault(receiver, []).append(InboundDocument(message_id, receiver, xml))
        self.statuses[message_id] = DeliveryStatus("delivered", tax_report_status="reported")
        return SendReceipt(message_id, "delivered")

    def status(self, message_id: str) -> DeliveryStatus:
        return self.statuses.get(message_id, DeliveryStatus("failed", error="Neznáma správa"))

    def fetch_inbox(self, participant_id: str) -> list[InboundDocument]:
        return list(self.inboxes.get(participant_id, []))

    def acknowledge(self, message_id: str) -> None:
        for docs in self.inboxes.values():
            docs[:] = [d for d in docs if d.message_id != message_id]


class HttpAccessPoint:
    """Generic partner REST adapter. Adjust paths/fields to the contracted partner's API."""

    name = "http"

    def __init__(self, base_url: str, api_key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0, transport=transport,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise AccessPointError(f"Prístupový bod je nedostupný: {exc}") from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            raise AccessPointError(f"Prístupový bod vrátil {resp.status_code}")
        if resp.status_code >= 400:
            raise PermanentAccessPointError(f"Prístupový bod odmietol požiadavku ({resp.status_code}): "
                                            f"{resp.text[:300]}")
        return resp

    def lookup(self, participant_id: str) -> bool:
        try:
            return self._call("GET", f"/participants/{participant_id}").status_code == 200
        except PermanentAccessPointError:
            return False

    def send(self, xml: bytes, *, sender: str, receiver: str, document_type: str) -> SendReceipt:
        resp = self._call("POST", "/documents", content=xml, headers={
            "Content-Type": "application/xml", "X-Peppol-Sender": sender, "X-Peppol-Receiver": receiver,
            "X-Peppol-Document-Type": document_type, "X-Peppol-Process": PROCESS_ID,
        })
        body = resp.json()
        return SendReceipt(body["id"], body.get("status", "sent"))

    def status(self, message_id: str) -> DeliveryStatus:
        body = self._call("GET", f"/documents/{message_id}").json()
        return DeliveryStatus(body.get("status", "sent"), body.get("tax_report_status"), body.get("error"))

    def fetch_inbox(self, participant_id: str) -> list[InboundDocument]:
        items = self._call("GET", "/inbox", params={"participant": participant_id}).json()
        docs = []
        for item in items:
            xml = self._call("GET", f"/inbox/{item['id']}/document").content
            docs.append(InboundDocument(item["id"], participant_id, xml))
        return docs

    def acknowledge(self, message_id: str) -> None:
        self._call("POST", f"/inbox/{message_id}/ack")


_mock_singleton: MockAccessPoint | None = None


def get_access_point() -> AccessPoint:
    global _mock_singleton
    from app.config import get_settings

    settings = get_settings()
    if settings.peppol_provider == "http":
        if not (settings.peppol_api_url and settings.peppol_api_key):
            raise RuntimeError("EFAKTURA_PEPPOL_API_URL and EFAKTURA_PEPPOL_API_KEY must be set")
        return HttpAccessPoint(settings.peppol_api_url, settings.peppol_api_key)
    if _mock_singleton is None:
        _mock_singleton = MockAccessPoint()
    return _mock_singleton
