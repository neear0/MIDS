"""Human-readable PDF companion with a PAY by square QR code.

The UBL XML is the legal document; this PDF is the visual copy for people.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from app.domain.invoice import DocumentType, Invoice, Party
from app.pdf import paybysquare

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]

TITLES = {
    DocumentType.INVOICE: "FAKTÚRA",
    DocumentType.CREDIT_NOTE: "DOBROPIS",
    DocumentType.CORRECTED_INVOICE: "OPRAVNÁ FAKTÚRA",
    DocumentType.PREPAYMENT_INVOICE: "ZÁLOHOVÁ FAKTÚRA",
}


def _fonts() -> tuple[str, str]:
    """Register a TTF with full Slovak diacritics; Helvetica cannot render ľ, ť, ô…"""
    if "Doc" in pdfmetrics.getRegisteredFontNames():
        return "Doc", "Doc-Bold"
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("Doc", regular))
            pdfmetrics.registerFont(TTFont("Doc-Bold", bold if Path(bold).exists() else regular))
            return "Doc", "Doc-Bold"
    return "Helvetica", "Helvetica-Bold"


def _fmt(amount: Decimal, currency: str = "") -> str:
    text = f"{Decimal(amount):,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {currency}".strip()


def _party_lines(party: Party) -> list[str]:
    a = party.address
    lines = [party.name, a.street or "", f"{a.postal_code or ''} {a.city or ''}".strip(), a.country_code]
    if party.ico:
        lines.append(f"IČO: {party.ico}")
    if party.dic:
        lines.append(f"DIČ: {party.dic}")
    if party.ic_dph:
        lines.append(f"IČ DPH: {party.ic_dph}")
    if party.registration_note:
        lines.append(party.registration_note)
    return [line for line in lines if line]


def render_pdf(invoice: Invoice) -> bytes:
    font, bold = _fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{TITLES[invoice.document_type]} {invoice.number}")
    width, height = A4
    left, right = 18 * mm, width - 18 * mm
    y = height - 20 * mm

    c.setFont(bold, 18)
    c.drawString(left, y, f"{TITLES[invoice.document_type]} č. {invoice.number}")
    c.setFont(font, 8)
    c.drawRightString(right, y, "Právne záväzná je elektronická faktúra vo formáte UBL 2.1 (Peppol BIS 3.0).")
    y -= 12 * mm

    col2 = left + (right - left) / 2
    for x, title, party in ((left, "Dodávateľ", invoice.seller), (col2, "Odberateľ", invoice.buyer)):
        c.setFont(bold, 10)
        c.drawString(x, y, title)
        c.setFont(font, 9)
        for i, text in enumerate(_party_lines(party)):
            c.drawString(x, y - (i + 1) * 4.5 * mm, text[:60])
    y -= 45 * mm

    c.setFont(font, 9)
    meta = [
        ("Dátum vyhotovenia", invoice.issue_date),
        ("Dátum dodania", invoice.delivery_date),
        ("Dátum splatnosti", invoice.due_date),
        ("Variabilný symbol", invoice.payment.variable_symbol),
        ("IBAN", invoice.payment.iban),
    ]
    if invoice.preceding_invoice:
        meta.append(("K faktúre č.", invoice.preceding_invoice.number))
    for i, (label, value) in enumerate(m for m in meta if m[1]):
        c.drawString(left, y - i * 4.5 * mm, f"{label}:")
        c.drawString(left + 40 * mm, y - i * 4.5 * mm, str(value))
    y -= (len(meta) + 1) * 4.5 * mm

    cur = invoice.currency
    rows = [["#", "Názov", "Množstvo", "Cena/j.", "DPH", "Spolu bez DPH"]]
    for line in invoice.lines:
        rows.append([line.id, line.name[:48], f"{line.quantity.normalize():f} {line.unit_code}",
                     _fmt(line.unit_price), f"{line.vat_category.value} {line.vat_rate.normalize():f} %",
                     _fmt(line.net_amount, cur)])
    table = Table(rows, colWidths=[8 * mm, 72 * mm, 24 * mm, 24 * mm, 20 * mm, 26 * mm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font, 8),
        ("FONT", (0, 0), (-1, 0), bold, 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
    ]))
    _, th = table.wrapOn(c, right - left, y)
    table.drawOn(c, left, y - th)
    y -= th + 8 * mm

    totals = invoice.totals()
    c.setFont(bold, 9)
    c.drawString(col2, y, "Rekapitulácia DPH")
    c.setFont(font, 8)
    for b in invoice.vat_breakdown():
        y -= 4.5 * mm
        c.drawString(col2, y, f"{b.category.value} {b.rate.normalize():f} %")
        c.drawRightString(right - 30 * mm, y, _fmt(b.taxable_amount, cur))
        c.drawRightString(right, y, _fmt(b.tax_amount, cur))
    y -= 7 * mm
    c.setFont(font, 9)
    for label, value in (("Spolu bez DPH", totals.tax_exclusive), ("DPH", totals.tax_amount),
                         ("Spolu s DPH", totals.tax_inclusive), ("Uhradené zálohy", totals.prepaid)):
        if label == "Uhradené zálohy" and not value:
            continue
        c.drawString(col2, y, label)
        c.drawRightString(right, y, _fmt(value, cur))
        y -= 4.5 * mm
    c.setFont(bold, 12)
    c.drawString(col2, y - 2 * mm, "K úhrade")
    c.drawRightString(right, y - 2 * mm, _fmt(totals.payable, cur))

    if invoice.payment.iban and totals.payable > 0 and invoice.document_type != DocumentType.CREDIT_NOTE:
        code = paybysquare.encode(
            iban=invoice.payment.iban, amount=totals.payable, currency=cur, due_date=invoice.due_date,
            variable_symbol=invoice.payment.variable_symbol or "", bic=invoice.payment.bic or "",
            beneficiary_name=invoice.seller.name, note=f"Faktúra {invoice.number}",
        )
        size = 38 * mm
        widget = QrCodeWidget(code, barLevel="M")
        x0, y0, x1, y1 = widget.getBounds()
        drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
        drawing.add(widget)
        qr_y = y - 2 * mm - size + 12 * mm
        renderPDF.draw(drawing, c, left, qr_y)
        c.setFont(bold, 8)
        c.drawString(left + 2 * mm, qr_y - 3 * mm, "PAY by square")

    for i, note in enumerate(invoice.notes[:4]):
        c.setFont(font, 8)
        c.drawString(left, 30 * mm - i * 4 * mm, note[:110])
    c.setFont(font, 7)
    c.drawString(left, 12 * mm, "Vystavené v eFaktúra SK · EN 16931 · Peppol BIS Billing 3.0")
    c.showPage()
    c.save()
    return buf.getvalue()
