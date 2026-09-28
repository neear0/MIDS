"""Slovak VAT rates by effective date (zákon č. 222/2004 Z. z. o DPH)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# (effective_from, allowed standard-category rates)
_SK_RATE_HISTORY: list[tuple[date, frozenset[Decimal]]] = [
    (date(2011, 1, 1), frozenset({Decimal("20"), Decimal("10")})),
    (date(2023, 1, 1), frozenset({Decimal("20"), Decimal("10"), Decimal("5")})),
    # Consolidation package (zákon č. 278/2024 Z. z.): 23 % standard, 19 % and 5 % reduced.
    (date(2025, 1, 1), frozenset({Decimal("23"), Decimal("19"), Decimal("5")})),
]

SK_STANDARD_RATE = Decimal("23")


def allowed_sk_rates(on: date | None) -> frozenset[Decimal]:
    on = on or date.today()
    allowed = _SK_RATE_HISTORY[0][1]
    for effective_from, rates in _SK_RATE_HISTORY:
        if on >= effective_from:
            allowed = rates
    return allowed
