"""Slovak business identifier checks (IČO, DIČ, IČ DPH) and IBAN."""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\D")

# Peppol Electronic Address Scheme used for Slovak DIČ endpoints.
SK_DIC_SCHEME = "0245"


def normalize_digits(value: str | None) -> str:
    return _DIGITS.sub("", value or "")


def normalize_ic_dph(value: str | None) -> str:
    return re.sub(r"\s", "", value or "").upper()


def is_valid_ico(value: str | None) -> bool:
    """IČO: 8 digits with a weighted mod-11 check digit (older 6-digit ones are zero-padded)."""
    digits = normalize_digits(value)
    if len(digits) == 6:
        digits = "00" + digits
    if len(digits) != 8:
        return False
    total = sum(int(d) * w for d, w in zip(digits[:7], range(8, 1, -1), strict=True))
    check = (11 - total % 11) % 10
    return check == int(digits[7])


def is_valid_dic(value: str | None) -> bool:
    """DIČ: 10 digits, no leading zero (legal entities typically 20xx, sole traders 10xx)."""
    raw = (value or "").strip()
    return bool(re.fullmatch(r"[1-9]\d{9}", raw))


def is_valid_ic_dph(value: str | None) -> bool:
    """IČ DPH: "SK" + 10 digits, first digit non-zero, third digit in {2,3,4,7,8,9}, divisible by 11."""
    v = normalize_ic_dph(value)
    if not re.fullmatch(r"SK[1-9]\d{9}", v):
        return False
    number = v[2:]
    if number[2] not in "234789":
        return False
    return int(number) % 11 == 0


def ic_dph_matches_dic(ic_dph: str | None, dic: str | None) -> bool:
    """For Slovak payers the IČ DPH is almost always "SK" + DIČ."""
    return normalize_ic_dph(ic_dph) == f"SK{normalize_digits(dic)}"


def is_valid_iban(value: str | None) -> bool:
    iban = re.sub(r"\s", "", value or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    if iban.startswith("SK") and len(iban) != 24:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def normalize_iban(value: str | None) -> str:
    return re.sub(r"\s", "", value or "").upper()
