"""Lenient parsing of amounts and dates as printed on Slovak documents."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_amount(text: str | None) -> Decimal | None:
    """'1 234,50 €' / '1.234,50' / '1234.50' → Decimal('1234.50')."""
    if not text:
        return None
    t = re.sub(r"[^\d,.\-]", "", text.replace(" ", ""))
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not m:
            return None
        y, mo, d = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None
