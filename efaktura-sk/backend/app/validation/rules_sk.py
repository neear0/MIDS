"""Slovak-specific checks (zákon o DPH č. 222/2004 Z. z., e-fakturácia od 1. 1. 2027).

These are product rules layered on top of EN 16931/Peppol; they are *not* an
official national CIUS. Where the Finančná správa publishes one, mirror it here.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from app.domain.identifiers import (
    SK_DIC_SCHEME,
    ic_dph_matches_dic,
    is_valid_dic,
    is_valid_iban,
    is_valid_ic_dph,
    is_valid_ico,
)
from app.domain.invoice import DocumentType, Invoice, Party, VatCategory
from app.domain.vat import allowed_sk_rates
from app.validation.engine import Issue, Severity, ValidationContext, rule

SK_EINVOICING_START = date(2027, 1, 1)


def _is_sk(party: Party) -> bool:
    return (party.address.country_code or "").upper() == "SK"


def _party_label(role: str) -> str:
    return "dodávateľa" if role == "seller" else "odberateľa"


def _party_ids(inv: Invoice) -> Iterator[tuple[str, Party]]:
    yield "seller", inv.seller
    yield "buyer", inv.buyer


@rule("SK-01", source="SK")
def ic_dph_format(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for role, party in _party_ids(inv):
        if party.ic_dph and party.ic_dph.upper().startswith("SK") and not is_valid_ic_dph(party.ic_dph):
            yield Issue(f"IČ DPH {_party_label(role)} „{party.ic_dph}“ nie je platné.",
                        f"Invalid Slovak VAT id for {role}.", "BT-31" if role == "seller" else "BT-48",
                        "Slovenské IČ DPH má tvar SK + 10 číslic a musí byť deliteľné 11. Overte ho v registri FS.")


@rule("SK-02", source="SK")
def dic_format(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for role, party in _party_ids(inv):
        if _is_sk(party) and party.dic and not is_valid_dic(party.dic):
            yield Issue(f"DIČ {_party_label(role)} „{party.dic}“ musí mať 10 číslic.",
                        f"Slovak tax id (DIČ) for {role} must be 10 digits.")


@rule("SK-03", Severity.WARNING, source="SK")
def ico_checksum(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for role, party in _party_ids(inv):
        if _is_sk(party) and party.ico and not is_valid_ico(party.ico):
            yield Issue(f"IČO {_party_label(role)} „{party.ico}“ nemá platný kontrolný súčet.",
                        f"IČO checksum failed for {role}.", "BT-30" if role == "seller" else "BT-47",
                        "Skontrolujte IČO v Obchodnom alebo Živnostenskom registri.")


@rule("SK-04", source="SK")
def ic_dph_consistent_with_dic(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for role, party in _party_ids(inv):
        if (_is_sk(party) and party.dic and party.ic_dph and is_valid_ic_dph(party.ic_dph)
                and not ic_dph_matches_dic(party.ic_dph, party.dic)):
            yield Issue(f"IČ DPH {_party_label(role)} nezodpovedá jeho DIČ.",
                        f"{role} VAT id does not match DIČ.", severity=Severity.WARNING,
                        hint_sk="Pri slovenských platiteľoch býva IČ DPH = SK + DIČ.")


@rule("SK-05", source="SK")
def sk_vat_rates(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if not _is_sk(inv.seller):
        return
    on = inv.delivery_date or inv.issue_date
    allowed = allowed_sk_rates(on)
    for line in inv.lines:
        if line.vat_category == VatCategory.STANDARD and line.vat_rate not in allowed:
            rates = ", ".join(f"{r} %" for r in sorted(allowed, reverse=True))
            yield Issue(f"Položka {line.id}: sadzba DPH {line.vat_rate} % sa k dátumu {on} na Slovensku "
                        f"nepoužíva (platné: {rates}).",
                        f"Line {line.id}: VAT rate {line.vat_rate}% not valid in SK on {on}.", "BT-152",
                        "Od 1. 1. 2025 platí základná sadzba 23 % a znížené sadzby 19 % a 5 %.")


@rule("SK-06", source="SK")
def vat_in_eur(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _is_sk(inv.seller) and inv.currency != "EUR" and inv.seller.ic_dph:
        if inv.tax_currency != "EUR" or inv.tax_amount_in_tax_currency is None:
            yield Issue("Pri faktúre v cudzej mene musí byť DPH uvedená aj v eurách.",
                        "Foreign-currency invoice must state VAT amount in EUR.", "BT-6/BT-111",
                        "Nastavte menu účtovania DPH na EUR a doplňte sumu DPH prepočítanú kurzom ECB/NBS.")


@rule("SK-07", source="SK")
def corrections_reference_original(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.document_type in (DocumentType.CREDIT_NOTE, DocumentType.CORRECTED_INVOICE) and not inv.preceding_invoice:
        yield Issue("Dobropis alebo opravná faktúra musí odkazovať na pôvodnú faktúru.",
                    "Credit note / corrected invoice must reference the original invoice.", "BG-3",
                    "Doplňte číslo a dátum pôvodnej faktúry, ktorú opravujete.")


@rule("SK-08", source="SK")
def reverse_charge_wording(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if any(line.vat_category == VatCategory.REVERSE_CHARGE for line in inv.lines):
        texts = " ".join(inv.notes).lower()
        if "prenesenie daňovej povinnosti" not in texts:
            yield Issue("Pri prenesení daňovej povinnosti musí faktúra obsahovať text „prenesenie daňovej "
                        "povinnosti“.", "Reverse-charge invoice must carry the statutory wording.", "BT-22",
                        severity=Severity.WARNING,
                        hint_sk="Tento text sa doplní aj do dôvodu oslobodenia; odporúčame ho uviesť aj v poznámke.")


@rule("SK-09", source="SK")
def sk_endpoint_scheme(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for role, party in _party_ids(inv):
        scheme, endpoint = party.resolved_endpoint()
        if _is_sk(party) and endpoint and scheme == SK_DIC_SCHEME:
            if not is_valid_dic(endpoint):
                yield Issue(f"Peppol adresa {_party_label(role)} (0245) musí byť platné DIČ.",
                            f"{role} endpoint under 0245 must be a valid DIČ.",
                            "BT-34" if role == "seller" else "BT-49")
            elif party.dic and endpoint != party.dic:
                yield Issue(f"Peppol adresa {_party_label(role)} sa nezhoduje s DIČ.",
                            f"{role} endpoint differs from DIČ.", severity=Severity.WARNING)


@rule("SK-10", source="SK")
def iban_valid(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.payment.iban and not is_valid_iban(inv.payment.iban):
        yield Issue(f"IBAN „{inv.payment.iban}“ nie je platný.", "Invalid IBAN.", "BT-84",
                    "Slovenský IBAN má 24 znakov a začína SK.")


@rule("SK-11", Severity.WARNING, source="SK")
def variable_symbol(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    vs = inv.payment.variable_symbol
    if vs and not (vs.isdigit() and len(vs) <= 10):
        yield Issue("Variabilný symbol môže obsahovať najviac 10 číslic.", "Variable symbol must be ≤10 digits.",
                    "BT-83")


@rule("SK-12", source="SK")
def delivery_date(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.delivery_date is None and inv.document_type != DocumentType.PREPAYMENT_INVOICE:
        yield Issue("Chýba dátum dodania tovaru alebo služby.", "Delivery date is missing.", "BT-72",
                    "Dátum dodania je povinný údaj faktúry podľa § 74 ods. 1 zákona o DPH.")


@rule("SK-13", Severity.WARNING, source="SK")
def due_after_issue(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.due_date and inv.issue_date and inv.due_date < inv.issue_date:
        yield Issue("Dátum splatnosti je skôr ako dátum vyhotovenia.", "Due date precedes issue date.", "BT-9")


@rule("SK-14", Severity.INFO, source="SK")
def mandate_notice(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if (_is_sk(inv.seller) and _is_sk(inv.buyer) and inv.issue_date
            and inv.issue_date >= SK_EINVOICING_START and not inv.buyer.resolved_endpoint()[1]):
        yield Issue("Od 1. 1. 2027 sa tuzemské faktúry medzi platiteľmi posielajú cez sieť Peppol. "
                    "Odberateľ zatiaľ nemá Peppol adresu.",
                    "Domestic B2B invoices go via Peppol from 2027; buyer has no endpoint.", "BT-49")
