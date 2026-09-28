"""Exports for desktop accounting systems (planned for V1 / later phases).

Money S3 (Solitea) imports documents through its XML import module and
Pohoda (Stormware) through ``dataPack`` XML. Both formats have published
XSDs; the exporters must be written and verified against those schemas and a
real test installation, so they are deliberately not guessed here.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.invoice import Invoice


class AccountingExporter(Protocol):
    kind: str

    def export(self, invoices: list[Invoice]) -> bytes: ...


class MoneyS3Exporter:
    kind = "money_s3"

    def export(self, invoices: list[Invoice]) -> bytes:
        raise NotImplementedError("Money S3 export is scheduled for V1 (see docs/ROADMAP.md).")


class PohodaExporter:
    kind = "pohoda"

    def export(self, invoices: list[Invoice]) -> bytes:
        raise NotImplementedError("Pohoda export is scheduled for the Later phase (see docs/ROADMAP.md).")
