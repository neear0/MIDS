from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from app.domain.invoice import Address, Invoice, InvoiceLine, Party, Payment

SELLER_DIC = "2020123457"
BUYER_DIC = "2020261342"


def seller() -> Party:
    return Party(name="Dodávateľ s.r.o.", ico="36070963", dic=SELLER_DIC, ic_dph=f"SK{SELLER_DIC}",
                 address=Address(street="Hlavná 1", city="Bratislava", postal_code="81101"))


def buyer() -> Party:
    return Party(name="Odberateľ a.s.", ico="35757442", dic=BUYER_DIC, ic_dph=f"SK{BUYER_DIC}",
                 address=Address(street="Mlynská 2", city="Košice", postal_code="04001"))


def invoice(**overrides) -> Invoice:
    data = dict(
        number="20270001", issue_date=date(2027, 1, 5), due_date=date(2027, 1, 19), delivery_date=date(2027, 1, 5),
        buyer_reference="Jana Nováková", seller=seller(), buyer=buyer(),
        lines=[
            InvoiceLine(id="1", name="Konzultácie", quantity=D("10"), unit_code="HUR", unit_price=D("50")),
            InvoiceLine(id="2", name="Kniha o DPH", quantity=D("2"), unit_price=D("12.50"), vat_rate=D("5")),
        ],
        payment=Payment(iban="SK3112000000198742637541", variable_symbol="20270001"),
    )
    data.update(overrides)
    return Invoice(**data)


COMPANY = {
    "name": "Dodávateľ s.r.o.", "ico": "36070963", "dic": SELLER_DIC, "ic_dph": f"SK{SELLER_DIC}",
    "street": "Hlavná 1", "city": "Bratislava", "postal_code": "81101", "iban": "SK3112000000198742637541",
}
