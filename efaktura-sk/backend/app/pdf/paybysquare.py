"""PAY by square encoder — the Slovak Banking Association payment QR standard.

Payload: tab-separated fields → CRC32 prefix → raw LZMA1 compression →
2-byte header + 2-byte length → base32hex. Every Slovak banking app scans it.
"""

from __future__ import annotations

import binascii
import lzma
from datetime import date
from decimal import Decimal

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
_LZMA_FILTERS = [{"id": lzma.FILTER_LZMA1, "lc": 3, "lp": 0, "pb": 2, "dict_size": 128 * 1024}]


def _clean(value: str | None, limit: int) -> str:
    return (value or "").replace("\t", " ").replace("\n", " ")[:limit]


def encode(
    *,
    iban: str,
    amount: Decimal,
    currency: str = "EUR",
    due_date: date | None = None,
    variable_symbol: str = "",
    constant_symbol: str = "",
    specific_symbol: str = "",
    note: str = "",
    beneficiary_name: str = "",
    bic: str = "",
) -> str:
    fields = [
        "",  # invoice id (unused)
        "1",  # number of payments
        "1",  # payment options: 1 = payment order
        f"{Decimal(amount):.2f}",
        currency,
        (due_date or date.today()).strftime("%Y%m%d"),
        _clean(variable_symbol, 10),
        _clean(constant_symbol, 4),
        _clean(specific_symbol, 10),
        "",  # originator's reference (SEPA) — symbols above are used instead
        _clean(note, 140),
        "1",  # number of bank accounts
        iban.replace(" ", "").upper(),
        bic,
        "0",  # standing order extension: none
        "0",  # direct debit extension: none
        _clean(beneficiary_name, 70),
        "",  # beneficiary address line 1
        "",  # beneficiary address line 2
    ]
    data = "\t".join(fields).encode("utf-8")
    checksum = binascii.crc32(data).to_bytes(4, "little")
    payload = checksum + data
    compressed = lzma.compress(payload, format=lzma.FORMAT_RAW, filters=_LZMA_FILTERS)
    blob = b"\x00\x00" + len(payload).to_bytes(2, "little") + compressed
    bits = "".join(f"{byte:08b}" for byte in blob)
    bits += "0" * (-len(bits) % 5)
    return "".join(_ALPHABET[int(bits[i : i + 5], 2)] for i in range(0, len(bits), 5))


def decode(code: str) -> list[str]:
    """Inverse of :func:`encode` (used by tests and for reading received QR codes)."""
    bits = "".join(f"{_ALPHABET.index(ch):05b}" for ch in code)
    raw = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits) - len(bits) % 8, 8))
    length = int.from_bytes(raw[2:4], "little")
    decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=_LZMA_FILTERS)
    payload = decompressor.decompress(raw[4:], max_length=length)
    checksum, data = payload[:4], payload[4:]
    if binascii.crc32(data).to_bytes(4, "little") != checksum:
        raise ValueError("PAY by square checksum mismatch")
    return data.decode("utf-8").split("\t")
