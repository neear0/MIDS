"""Turn a PDF, scan or photo of an invoice into a draft canonical :class:`Invoice`.

Two providers share one interface:

* ``heuristic`` — offline, reads the PDF text layer and applies Slovak-invoice
  regexes. No data leaves the server; good for born-digital PDFs.
* ``anthropic`` — Claude reads the document (text or image) and returns a
  schema-validated structure. Handles scans and photos.

The result is always a *draft*: it goes through the validator and the user
confirms it before anything is stored or sent.
"""

from __future__ import annotations

import base64
import io
import re
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.identifiers import is_valid_iban, is_valid_ic_dph, is_valid_ico
from app.domain.invoice import (
    Address,
    DocumentType,
    Invoice,
    InvoiceLine,
    Party,
    Payment,
    PrecedingInvoice,
    VatCategory,
)
from app.domain.parsing import parse_amount, parse_date

PDF = "application/pdf"
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class ExtractionError(RuntimeError):
    pass


class ExtractionResult(BaseModel):
    invoice: Invoice
    provider: str
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = []
    warnings: list[str] = []


class Extractor(Protocol):
    name: str

    def extract(self, data: bytes, media_type: str) -> ExtractionResult: ...


# --------------------------------------------------------------------------- helpers

def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # pypdf raises many exception types on malformed input
        raise ExtractionError(f"PDF sa nepodarilo prečítať: {exc}") from exc


def _missing(inv: Invoice) -> list[str]:
    checks = {
        "number": inv.number, "issue_date": inv.issue_date, "seller.name": inv.seller.name,
        "seller.ico": inv.seller.ico, "buyer.name": inv.buyer.name, "lines": inv.lines,
        "payment.iban": inv.payment.iban,
    }
    return [k for k, v in checks.items() if not v]


# --------------------------------------------------------------------------- heuristic

_LABEL_VALUE = r"[:\s]*([^\n]+)"
_AMOUNT = r"(\d{1,3}(?:[ \u00a0.]\d{3})*[.,]\d{2}|\d+[.,]\d{2})"
# Between a label and its amount: no digits and at most one line break (PDF text layers often
# put the value on the next line, but a table header followed by row data must not match).
_SEP = r"[^\d\n]*\n?[^\d\n]*"
_RE = {
    "number": re.compile(r"(?:faktúr[ay]\s*(?:č\.|číslo)|číslo\s*faktúry|doklad\s*č\.)\s*[:\s]*([A-Z0-9/\-]+)", re.I),
    "issue": re.compile(r"dátum\s*(?:vyhotovenia|vystavenia)" + _LABEL_VALUE, re.I),
    "delivery": re.compile(r"dátum\s*(?:dodania|zdaniteľného\s*plnenia)" + _LABEL_VALUE, re.I),
    "due": re.compile(r"(?:dátum\s*splatnosti|splatnosť)" + _LABEL_VALUE, re.I),
    "ico": re.compile(r"IČO\s*[:\s]*(\d[\d ]{5,9}\d)"),
    "dic": re.compile(r"(?<!IČ )DIČ\s*[:\s]*(\d{10})"),
    "ic_dph": re.compile(r"IČ\s*DPH\s*[:\s]*([A-Z]{2}\s?\d{8,12})"),
    "iban": re.compile(r"\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?)\b"),
    "vs": re.compile(r"(?:variabilný\s*symbol|VS)\s*[:\s]*(\d{1,10})", re.I),
    "total": re.compile(r"(?:k\s*úhrade|celkom\s*k\s*úhrade|spolu\s*s\s*DPH)" + _SEP + _AMOUNT, re.I),
    "net": re.compile(r"(?:spolu\s*bez\s*DPH|základ\s*dane)" + _SEP + _AMOUNT, re.I),
    # VAT recap row: "23 %  500,00 EUR  115,00 EUR"
    "recap": re.compile(r"(\d{1,2})[ \t]*%" + _SEP + _AMOUNT + _SEP + _AMOUNT),
}
_SK_RATES = {Decimal(x) for x in (5, 10, 19, 20, 23)}


def _section(text: str, start: str, stop: str) -> str:
    m = re.search(start + r"(.*?)(?:" + stop + r"|$)", text, re.I | re.S)
    return m.group(1) if m else ""


def _party_from(block: str) -> Party:
    lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
    name = lines[0].strip(": ") if lines else ""
    def find(key: str) -> str | None:
        m = _RE[key].search(block)
        return re.sub(r"\s", "", m.group(1)) if m else None
    postal = re.search(r"\b(\d{3}\s?\d{2})\s+([^\d\n,]+)", block)
    street = next((ln for ln in lines[1:4] if re.search(r"\d", ln) and not re.search(r"IČO|DIČ|IČ DPH", ln)
                   and not (postal and postal.group(0).strip() in ln)), None)
    return Party(
        name=name, ico=find("ico"), dic=find("dic"), ic_dph=find("ic_dph"),
        address=Address(street=street, postal_code=postal.group(1).replace(" ", "") if postal else None,
                        city=postal.group(2).strip() if postal else None, country_code="SK"),
    )


def _last(pattern: re.Pattern[str], text: str) -> str | None:
    """Totals sit at the bottom of an invoice, so the last match is the most reliable."""
    matches = pattern.findall(text)
    return matches[-1] if matches else None


class HeuristicExtractor:
    name = "heuristic"

    def extract(self, data: bytes, media_type: str) -> ExtractionResult:
        if media_type != PDF:
            raise ExtractionError("Offline extrakcia podporuje len PDF s textovou vrstvou. "
                                  "Pre skeny a fotky zapnite AI extrakciu.")
        text = pdf_text(data)
        if len(text.strip()) < 20:
            raise ExtractionError("PDF neobsahuje text (pravdepodobne sken). Použite AI extrakciu.")
        return self.extract_text(text)

    @staticmethod
    def _lines_from_recap(text: str) -> list[InvoiceLine]:
        """One line per VAT rate from the recap, kept only when base × rate ≈ VAT (±1 cent)."""
        lines: list[InvoiceLine] = []
        seen: set[Decimal] = set()
        for rate_s, base_s, vat_s in _RE["recap"].findall(text):
            rate, base, vat = Decimal(rate_s), parse_amount(base_s), parse_amount(vat_s)
            if rate in _SK_RATES and rate not in seen and base is not None and vat is not None \
                    and abs(base * rate / 100 - vat) <= Decimal("0.01"):
                seen.add(rate)
                lines.append(InvoiceLine(id=str(len(lines) + 1), name=f"Plnenie so sadzbou {rate} %",
                                         unit_price=base, vat_rate=rate))
        return lines

    def extract_text(self, text: str) -> ExtractionResult:
        def first(key: str, src: str = text) -> str | None:
            m = _RE[key].search(src)
            return m.group(1).strip() if m else None

        seller = _party_from(_section(text, r"dodávateľ\s*:?", r"odberateľ"))
        buyer = _party_from(_section(text, r"odberateľ\s*:?", r"dátum|položk|popis|IBAN|$"))
        iban = next((re.sub(r"\s", "", m) for m in _RE["iban"].findall(text) if is_valid_iban(m)), None)
        warnings: list[str] = []
        category = VatCategory.STANDARD if seller.ic_dph else VatCategory.NOT_SUBJECT
        lines = self._lines_from_recap(text) if category == VatCategory.STANDARD else []
        if lines:
            warnings.append("Položky boli zlúčené podľa sadzieb DPH – doplňte ich podľa potreby.")
        else:
            total = parse_amount(_last(_RE["total"], text))
            net = parse_amount(_last(_RE["net"], text))
            rate = Decimal("23") if category == VatCategory.STANDARD else Decimal("0")
            if net is None and total is not None:
                net = (total / (1 + rate / 100)).quantize(Decimal("0.01"))
                warnings.append("Základ dane bol dopočítaný zo sumy s DPH – skontrolujte ho.")
            if net is not None:
                lines.append(InvoiceLine(id="1", name="Plnenie podľa faktúry", unit_price=net,
                                         vat_category=category, vat_rate=rate))
                warnings.append("Položky boli zlúčené do jedného riadku – doplňte ich podľa potreby.")
        credit = bool(re.search(r"dobropis", text, re.I))
        inv = Invoice(
            number=first("number") or "", issue_date=parse_date(first("issue")),
            delivery_date=parse_date(first("delivery")), due_date=parse_date(first("due")),
            document_type=DocumentType.CREDIT_NOTE if credit else DocumentType.INVOICE,
            seller=seller, buyer=buyer, lines=lines,
            payment=Payment(iban=iban, variable_symbol=first("vs")),
        )
        for label, party in (("dodávateľa", seller), ("odberateľa", buyer)):
            if party.ico and not is_valid_ico(party.ico):
                warnings.append(f"IČO {label} sa nepodarilo spoľahlivo prečítať.")
            if party.ic_dph and not is_valid_ic_dph(party.ic_dph):
                warnings.append(f"IČ DPH {label} vyzerá neplatne.")
        missing = _missing(inv)
        return ExtractionResult(invoice=inv, provider=self.name, confidence=round(1 - len(missing) / 7 * 0.8, 2),
                                missing_fields=missing, warnings=warnings)


# --------------------------------------------------------------------------- Claude

class _LlmParty(BaseModel):
    name: str
    ico: str | None = Field(None, description="IČO, 8 digits")
    dic: str | None = Field(None, description="DIČ, 10 digits")
    ic_dph: str | None = Field(None, description="IČ DPH / VAT id incl. country prefix, e.g. SK2020123457")
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country_code: str = Field("SK", description="ISO 3166-1 alpha-2")


class _LlmLine(BaseModel):
    name: str
    quantity: str = Field(description="decimal number, dot as separator")
    unit_code: str = Field(description="UN/ECE Rec 20 code: C62 piece, HUR hour, KGM kg, MTR metre, DAY day")
    unit_price: str = Field(description="net unit price without VAT, dot decimal separator")
    vat_rate: str = Field(description="VAT percentage, e.g. 23; 0 if no VAT")
    vat_category: str = Field(description="S standard, Z zero, E exempt, AE reverse charge, K intra-EU, "
                                           "G export, O not subject to VAT")


class _LlmInvoice(BaseModel):
    document_type: str = Field(description="380 invoice, 381 credit note, 384 corrected, 386 prepayment")
    number: str
    issue_date: str | None = Field(None, description="YYYY-MM-DD")
    delivery_date: str | None = Field(None, description="YYYY-MM-DD")
    due_date: str | None = Field(None, description="YYYY-MM-DD")
    currency: str = "EUR"
    seller: _LlmParty
    buyer: _LlmParty
    lines: list[_LlmLine]
    iban: str | None = None
    variable_symbol: str | None = None
    total_payable: str | None = Field(None, description="amount due as printed, dot decimal separator")
    preceding_invoice_number: str | None = Field(None, description="for credit notes: the corrected invoice number")
    notes: list[str] = []
    uncertain_fields: list[str] = Field(default_factory=list,
                                        description="fields that were illegible or guessed")


_SYSTEM = (
    "You extract data from Slovak invoices (faktúra, dobropis, zálohová faktúra) for an e-invoicing system. "
    "Return exactly what the document states; never invent values. Use null for anything not present. "
    "Dodávateľ is the seller, Odberateľ is the buyer. Amounts on lines are net (bez DPH) unit prices. "
    "List every field you had to guess or could not read clearly in uncertain_fields."
)


def _dec(value: str | None, default: str = "0") -> Decimal:
    return parse_amount(value) or Decimal(default)


def _llm_to_invoice(x: _LlmInvoice) -> Invoice:
    def party(p: _LlmParty) -> Party:
        return Party(name=p.name, ico=p.ico, dic=p.dic, ic_dph=p.ic_dph,
                     address=Address(street=p.street, city=p.city, postal_code=p.postal_code,
                                     country_code=(p.country_code or "SK").upper()[:2]))

    def category(code: str) -> VatCategory:
        try:
            return VatCategory(code)
        except ValueError:
            return VatCategory.STANDARD

    try:
        doc_type = DocumentType(x.document_type)
    except ValueError:
        doc_type = DocumentType.INVOICE

    return Invoice(
        number=x.number, document_type=doc_type, issue_date=parse_date(x.issue_date),
        delivery_date=parse_date(x.delivery_date), due_date=parse_date(x.due_date), currency=x.currency,
        seller=party(x.seller), buyer=party(x.buyer), notes=x.notes,
        lines=[InvoiceLine(id=str(i), name=ln.name, quantity=_dec(ln.quantity, "1"), unit_code=ln.unit_code or "C62",
                           unit_price=_dec(ln.unit_price), vat_rate=_dec(ln.vat_rate),
                           vat_category=category(ln.vat_category)) for i, ln in enumerate(x.lines, 1)],
        payment=Payment(iban=x.iban, variable_symbol=x.variable_symbol),
        preceding_invoice=PrecedingInvoice(number=x.preceding_invoice_number) if x.preceding_invoice_number else None,
    )


class ClaudeExtractor:
    """Uses the Claude API with a Pydantic output schema. Documents are sent to Anthropic —
    make sure the customer's DPA covers this before enabling it."""

    name = "anthropic"

    def __init__(self, api_key: str | None, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model

    def extract(self, data: bytes, media_type: str) -> ExtractionResult:
        import anthropic

        encoded = base64.standard_b64encode(data).decode()
        if media_type == PDF:
            block = {"type": "document", "source": {"type": "base64", "media_type": PDF, "data": encoded}}
        elif media_type in IMAGE_TYPES:
            block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}}
        else:
            raise ExtractionError("Podporované sú PDF, PNG, JPEG, WEBP a GIF.")
        try:
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=_SYSTEM,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": [block, {"type": "text", "text": "Extract this invoice."}]}],
                output_format=_LlmInvoice,
            )
        except anthropic.RateLimitError as exc:
            raise ExtractionError("AI služba je preťažená, skúste to o chvíľu.") from exc
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"AI služba vrátila chybu ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("AI služba je nedostupná.") from exc
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ExtractionError("AI nevedela dokument spracovať. Zadajte údaje ručne.")
        parsed: _LlmInvoice = response.parsed_output
        inv = _llm_to_invoice(parsed)
        warnings = [f"Neisté pole: {f}" for f in parsed.uncertain_fields]
        declared = parse_amount(parsed.total_payable)
        if declared is not None and inv.lines and declared != inv.computed_totals().payable:
            warnings.append(f"Suma k úhrade na doklade ({declared}) nesedí s prepočtom položiek "
                            f"({inv.computed_totals().payable}).")
        missing = _missing(inv)
        confidence = max(0.0, 1 - 0.1 * len(missing) - 0.05 * len(parsed.uncertain_fields))
        return ExtractionResult(invoice=inv, provider=self.name, confidence=round(confidence, 2),
                                missing_fields=missing, warnings=warnings)


def get_extractor(provider: str | None = None) -> Extractor:
    from app.config import get_settings

    settings = get_settings()
    provider = provider or settings.extraction_provider
    if provider == "anthropic":
        return ClaudeExtractor(settings.anthropic_api_key, settings.anthropic_model)
    return HeuristicExtractor()
