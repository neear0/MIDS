"""Validation rules engine.

Rules are small Python functions registered with :func:`rule`. Each yields
:class:`Finding` objects carrying a Slovak message (shown to users), an
English message (for logs/support) and an optional plain-Slovak hint on how
to fix the problem. Rule ids reuse official EN 16931 (``BR-*``) and Peppol
(``PEPPOL-*``) identifiers where they exist; Slovak-specific checks use ``SK-*``.

The Python rules give fast, explainable feedback while the user is typing.
For a legally authoritative check, :mod:`app.validation.schematron` runs the
official EN 16931 + Peppol Schematron artefacts when they are installed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.invoice import Invoice


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    message_sk: str
    message_en: str
    field: str | None = None  # EN 16931 business term, e.g. "BT-1"
    hint_sk: str | None = None
    source: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message_sk,
            "message_en": self.message_en,
            "hint": self.hint_sk,
            "source": self.source,
        }


@dataclass
class ValidationContext:
    """Extra facts not in the canonical model (e.g. raw XML header values)."""

    customization_id: str | None = None
    profile_id: str | None = None
    from_xml: bool = False


@dataclass
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [f.as_dict() for f in self.findings],
        }


RuleFn = Callable[[Invoice, ValidationContext], Iterable["Issue"]]


@dataclass(frozen=True)
class Issue:
    """What a rule function yields; the decorator fills in id/severity/source."""

    message_sk: str
    message_en: str
    field: str | None = None
    hint_sk: str | None = None
    severity: Severity | None = None  # override the rule's default


@dataclass(frozen=True)
class RegisteredRule:
    rule_id: str
    severity: Severity
    source: str
    fn: RuleFn


_REGISTRY: list[RegisteredRule] = []


def rule(rule_id: str, severity: Severity = Severity.ERROR, source: str = "EN16931") -> Callable[[RuleFn], RuleFn]:
    def decorator(fn: RuleFn) -> RuleFn:
        _REGISTRY.append(RegisteredRule(rule_id, severity, source, fn))
        return fn

    return decorator


def registered_rules() -> list[RegisteredRule]:
    _load_rule_modules()
    return list(_REGISTRY)


def _load_rule_modules() -> None:
    # Importing registers the rules via the decorator.
    from app.validation import rules_en16931, rules_peppol, rules_sk  # noqa: F401


def _run(invoice: Invoice, ctx: ValidationContext) -> Iterator[Finding]:
    for r in registered_rules():
        for issue in r.fn(invoice, ctx) or ():
            yield Finding(
                rule_id=r.rule_id,
                severity=issue.severity or r.severity,
                message_sk=issue.message_sk,
                message_en=issue.message_en,
                field=issue.field,
                hint_sk=issue.hint_sk,
                source=r.source,
            )


_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


def validate_invoice(invoice: Invoice, ctx: ValidationContext | None = None) -> ValidationResult:
    findings = list(_run(invoice, ctx or ValidationContext()))
    findings.sort(key=lambda f: (_ORDER[f.severity], f.rule_id))
    return ValidationResult(findings)


def validate_ubl(xml: bytes) -> ValidationResult:
    from app.ubl.parser import UblParseError, document_metadata, parse_ubl

    try:
        invoice = parse_ubl(xml)
        meta = document_metadata(xml)
    except UblParseError as exc:
        return ValidationResult([
            Finding("XML-01", Severity.ERROR, str(exc), "Document is not well-formed UBL 2.1", source="UBL")
        ])
    ctx = ValidationContext(customization_id=meta["customization_id"], profile_id=meta["profile_id"], from_xml=True)
    return validate_invoice(invoice, ctx)
