from app.ai.explain import explain, search
from app.ai.extraction import HeuristicExtractor, _llm_to_invoice, _LlmInvoice
from app.domain.parsing import parse_amount, parse_date
from app.pdf.render import render_pdf
from tests.factories import invoice


def test_parse_helpers():
    from datetime import date
    from decimal import Decimal

    assert parse_amount("1 234,50 €") == Decimal("1234.50")
    assert parse_amount("1.234,50") == Decimal("1234.50")
    assert parse_amount("1,234.50") == Decimal("1234.50")
    assert parse_date("5. 1. 2027") == date(2027, 1, 5)
    assert parse_date("2027-01-19") == date(2027, 1, 19)
    assert parse_date("32.13.2027") is None


def test_heuristic_extracts_our_own_pdf():
    """Render → read back: the offline extractor must recover the key fields."""
    result = HeuristicExtractor().extract(render_pdf(invoice()), "application/pdf")
    inv = result.invoice
    assert inv.number == "20270001"
    assert str(inv.issue_date) == "2027-01-05" and str(inv.due_date) == "2027-01-19"
    assert inv.seller.ico == "36070963" and inv.seller.ic_dph == "SK2020123457"
    assert inv.buyer.dic == "2020261342"
    assert inv.payment.iban == "SK3112000000198742637541"
    assert inv.payment.variable_symbol == "20270001"
    assert result.confidence > 0.5
    # Lines rebuilt from the VAT recap: 500 € at 23 % and 25 € at 5 % → same totals as the original.
    rates = sorted((str(line.vat_rate), str(line.unit_price)) for line in inv.lines)
    assert rates == [("23", "500.00"), ("5", "25.00")]
    assert inv.computed_totals().payable == invoice().computed_totals().payable


def test_heuristic_single_rate_fallback():
    text = ("Faktúra č. 7\nDodávateľ: A s.r.o.\nIČ DPH: SK2020123457\nOdberateľ: B\n"
            "Spolu bez DPH\n1 Položka\nK úhrade: 1 230,00 €")
    inv = HeuristicExtractor().extract_text(text).invoice
    assert [str(line.unit_price) for line in inv.lines] == ["1000.00"]


def test_heuristic_rejects_images():
    import pytest

    from app.ai.extraction import ExtractionError

    with pytest.raises(ExtractionError):
        HeuristicExtractor().extract(b"\x89PNG", "image/png")


def test_llm_schema_mapping():
    parsed = _LlmInvoice.model_validate({
        "document_type": "381", "number": "D-7", "issue_date": "2027-02-01", "currency": "EUR",
        "seller": {"name": "A s.r.o.", "dic": "2020123457", "ic_dph": "SK2020123457"},
        "buyer": {"name": "B a.s.", "country_code": "sk"},
        "lines": [{"name": "Vrátenie", "quantity": "2", "unit_code": "C62", "unit_price": "10,50",
                   "vat_rate": "23", "vat_category": "S"}],
        "preceding_invoice_number": "2027001",
    })
    inv = _llm_to_invoice(parsed)
    assert inv.is_credit_note and inv.preceding_invoice.number == "2027001"
    assert inv.buyer.address.country_code == "SK"
    assert str(inv.computed_totals().payable) == "25.83"


def test_explain_by_rule_and_question():
    assert search("", rule_id="SK-07")[0].id == "dobropis"
    assert search("Kedy musím začať posielať e-faktúry?")[0].id == "e-fakturacia-2027"
    assert search("danova povinnost prenesenie")[0].id == "prenesenie"
    answer = explain("Aká je sadzba DPH na knihy?")
    assert "5 %" in answer["answer"] and not answer["generated"]
