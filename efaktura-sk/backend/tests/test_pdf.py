from io import BytesIO

from pypdf import PdfReader

from app.pdf import paybysquare
from app.pdf.render import render_pdf
from tests.factories import invoice


def test_paybysquare_roundtrip():
    from datetime import date
    from decimal import Decimal

    code = paybysquare.encode(iban="SK3112000000198742637541", amount=Decimal("641.25"),
                              due_date=date(2027, 1, 19), variable_symbol="20270001", beneficiary_name="Ďateľ s.r.o.")
    fields = paybysquare.decode(code)
    assert set(code) <= set("0123456789ABCDEFGHIJKLMNOPQRSTUV")
    assert fields[3] == "641.25" and fields[5] == "20270119" and fields[6] == "20270001"
    assert fields[12] == "SK3112000000198742637541" and fields[16] == "Ďateľ s.r.o."


def test_pdf_contains_slovak_text():
    pdf = render_pdf(invoice())
    assert pdf.startswith(b"%PDF")
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "FAKTÚRA č. 20270001" in text
    assert "Košice" in text and "641,25 EUR" in text
