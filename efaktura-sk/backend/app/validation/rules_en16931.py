"""EN 16931 business rules (subset relevant to the canonical model)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from app.domain.invoice import Invoice, VatCategory, money
from app.validation.engine import Issue, Severity, ValidationContext, rule


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@rule("BR-02")
def invoice_number(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.number):
        yield Issue("Chýba číslo faktúry.", "Invoice number is missing.", "BT-1",
                    "Každá faktúra musí mať jedinečné poradové číslo, napr. 2027001.")


@rule("BR-03")
def issue_date(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.issue_date is None:
        yield Issue("Chýba dátum vyhotovenia faktúry.", "Invoice issue date is missing.", "BT-2")


@rule("BR-05")
def currency(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.currency) or len(inv.currency) != 3:
        yield Issue("Chýba alebo je neplatný kód meny (napr. EUR).", "Invoice currency code missing/invalid.", "BT-5")


@rule("BR-06")
def seller_name(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.seller.name):
        yield Issue("Chýba obchodné meno dodávateľa.", "Seller name is missing.", "BT-27")


@rule("BR-07")
def buyer_name(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.buyer.name):
        yield Issue("Chýba obchodné meno odberateľa.", "Buyer name is missing.", "BT-44")


@rule("BR-09")
def seller_country(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.seller.address.country_code):
        yield Issue("Chýba krajina v adrese dodávateľa.", "Seller country code is missing.", "BT-40")


@rule("BR-11")
def buyer_country(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if _missing(inv.buyer.address.country_code):
        yield Issue("Chýba krajina v adrese odberateľa.", "Buyer country code is missing.", "BT-55")


@rule("BR-16")
def at_least_one_line(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if not inv.lines:
        yield Issue("Faktúra musí obsahovať aspoň jednu položku.", "Invoice must have at least one line.", "BG-25")


@rule("BR-21")
def line_ids(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    seen: set[str] = set()
    for idx, line in enumerate(inv.lines, 1):
        if _missing(line.id):
            yield Issue(f"Položka č. {idx} nemá identifikátor.", f"Line {idx} has no identifier.", "BT-126")
        elif line.id in seen:
            yield Issue(f"Identifikátor položky „{line.id}“ je duplicitný.", f"Duplicate line id {line.id}.",
                        "BT-126")
        seen.add(line.id)


@rule("BR-23")
def line_unit(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for line in inv.lines:
        if _missing(line.unit_code):
            yield Issue(f"Položka {line.id}: chýba merná jednotka.", f"Line {line.id}: unit code missing.", "BT-130",
                        "Použite kód UN/ECE Rec 20, napr. C62 (ks), HUR (hodina), KGM (kg).")


@rule("BR-25")
def line_item_name(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for line in inv.lines:
        if _missing(line.name):
            yield Issue(f"Položka {line.id}: chýba názov tovaru alebo služby.",
                        f"Line {line.id}: item name missing.", "BT-153")


@rule("BR-27")
def line_price_not_negative(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for line in inv.lines:
        if line.unit_price < 0:
            yield Issue(f"Položka {line.id}: jednotková cena nesmie byť záporná.",
                        f"Line {line.id}: item net price must not be negative.", "BT-146",
                        "Zľavu zadajte ako zľavu na položke, nie zápornou cenou.")


@rule("BR-CO-10")
def sum_of_lines(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    declared = inv.totals().line_extension
    computed = money(sum((line.net_amount for line in inv.lines), Decimal("0")))
    if declared != computed:
        yield Issue(f"Súčet položiek ({computed}) nesedí so sumou na faktúre ({declared}).",
                    f"Sum of line net amounts {computed} != declared {declared}.", "BT-106")


@rule("BR-CO-15")
def total_with_vat(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    t = inv.totals()
    if money(t.tax_exclusive + t.tax_amount) != money(t.tax_inclusive):
        yield Issue("Suma s DPH sa nerovná sume bez DPH plus DPH.",
                    "Total with VAT != total without VAT + VAT.", "BT-112")


@rule("BR-CO-16")
def amount_due(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    t = inv.totals()
    if money(t.tax_inclusive - t.prepaid) != money(t.payable):
        yield Issue("Suma na úhradu nesedí (suma s DPH mínus uhradené zálohy).",
                    "Amount due != total with VAT - paid amount.", "BT-115")


@rule("BR-CO-14")
def vat_total_matches_breakdown(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    breakdown_total = money(sum((b.tax_amount for b in inv.vat_breakdown()), Decimal("0")))
    if money(inv.totals().tax_amount) != breakdown_total:
        yield Issue(f"Celková DPH ({inv.totals().tax_amount}) nesedí s rekapituláciou DPH ({breakdown_total}).",
                    "Invoice VAT total != sum of VAT category amounts.", "BT-110",
                    "DPH sa počíta zo súčtu základov za každú sadzbu, nie z jednotlivých riadkov.")


@rule("BR-CO-25")
def due_date_or_terms(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.totals().payable > 0 and inv.due_date is None and _missing(inv.payment.terms):
        yield Issue("Pri kladnej sume na úhradu musí byť uvedený dátum splatnosti alebo platobné podmienky.",
                    "Positive amount due requires a due date or payment terms.", "BT-9")


@rule("BR-61")
def account_for_credit_transfer(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.payment.means_code in {"30", "58"} and _missing(inv.payment.iban) and inv.totals().payable > 0:
        yield Issue("Pri úhrade prevodom musí byť uvedený IBAN dodávateľa.",
                    "Credit transfer requires the payment account identifier.", "BT-84")


@rule("BR-S-02")
def seller_vat_for_standard_rate(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if any(line.vat_category == VatCategory.STANDARD for line in inv.lines) and _missing(inv.seller.ic_dph):
        yield Issue("Faktúra s DPH musí obsahovať IČ DPH dodávateľa.",
                    "Standard-rated invoice requires seller VAT identifier.", "BT-31",
                    "Ak nie ste platiteľ DPH, zvoľte kategóriu „O – nepodlieha DPH“.")


@rule("BR-S-05")
def standard_rate_positive(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    for line in inv.lines:
        if line.vat_category == VatCategory.STANDARD and line.vat_rate <= 0:
            yield Issue(f"Položka {line.id}: štandardná kategória DPH (S) vyžaduje sadzbu vyššiu ako 0 %.",
                        f"Line {line.id}: category S requires rate > 0.", "BT-152")


@rule("BR-AE-02")
def reverse_charge_ids(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if any(line.vat_category == VatCategory.REVERSE_CHARGE for line in inv.lines):
        if _missing(inv.seller.ic_dph) or _missing(inv.buyer.ic_dph):
            yield Issue("Pri prenesení daňovej povinnosti musia byť uvedené IČ DPH dodávateľa aj odberateľa.",
                        "Reverse charge requires both seller and buyer VAT identifiers.", "BT-31/BT-48")


@rule("BR-IC-02")
def intra_community_ids(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if any(line.vat_category == VatCategory.INTRA_COMMUNITY for line in inv.lines):
        if _missing(inv.seller.ic_dph) or _missing(inv.buyer.ic_dph):
            yield Issue("Pri dodaní do iného členského štátu EÚ musia byť uvedené IČ DPH oboch strán.",
                        "Intra-community supply requires both VAT identifiers.", "BT-31/BT-48")


@rule("BR-55", Severity.ERROR)
def preceding_invoice_reference(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if inv.preceding_invoice is not None and _missing(inv.preceding_invoice.number):
        yield Issue("Odkaz na pôvodnú faktúru musí obsahovať jej číslo.",
                    "Preceding invoice reference requires an invoice number.", "BT-25")


@rule("BR-O-11")
def not_subject_exclusive(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    categories = {line.vat_category for line in inv.lines}
    if VatCategory.NOT_SUBJECT in categories and len(categories) > 1:
        yield Issue("Položky „nepodlieha DPH“ (O) nemožno kombinovať s inými kategóriami DPH na jednej faktúre.",
                    "Category O cannot be combined with other VAT categories.", "BT-151",
                    "Vystavte na tieto položky samostatnú faktúru.")


@rule("BR-O-02", Severity.INFO)
def not_subject_vat_ids(inv: Invoice, ctx: ValidationContext) -> Iterator[Issue]:
    if any(line.vat_category == VatCategory.NOT_SUBJECT for line in inv.lines) and (
            inv.seller.ic_dph or inv.buyer.ic_dph):
        yield Issue("Pri plnení, ktoré nepodlieha DPH, sa IČ DPH do e-faktúry nezapisuje – vynecháme ho.",
                    "VAT identifiers are omitted from the XML for category O invoices.", "BT-31/BT-48")
