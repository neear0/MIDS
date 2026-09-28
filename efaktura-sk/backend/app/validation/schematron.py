"""Optional authoritative validation with the official Schematron artefacts.

The CEN/TC 434 EN 16931 UBL rules and the OpenPeppol BIS Billing 3.0 rules
are published as pre-compiled XSLT 2.0 stylesheets. Running them needs an
XSLT 2.0 processor, so this module uses Saxon-HE via ``saxonche`` when it is
installed and the stylesheets are in ``settings.schematron_dir``
(see ``scripts/fetch_validation_artifacts.sh``). Otherwise it reports itself
as unavailable and the Python rules remain the only check.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from app.validation.engine import Finding, Severity

SVRL = "http://purl.oclc.org/dsdl/svrl"
STYLESHEETS = ("CEN-EN16931-UBL.xslt", "PEPPOL-EN16931-UBL.xslt")


def available(schematron_dir: Path) -> bool:
    try:
        import saxonche  # noqa: F401
    except ImportError:
        return False
    return all((schematron_dir / name).exists() for name in STYLESHEETS)


def parse_svrl(svrl: bytes, source: str) -> list[Finding]:
    root = etree.fromstring(svrl)
    findings = []
    for failed in root.iter(f"{{{SVRL}}}failed-assert"):
        flag = (failed.get("flag") or "fatal").lower()
        severity = Severity.ERROR if flag in {"fatal", "error"} else Severity.WARNING
        text_el = failed.find(f"{{{SVRL}}}text")
        text = (text_el.text or "").strip() if text_el is not None else ""
        rule_id = failed.get("id") or "SCHEMATRON"
        findings.append(Finding(rule_id, severity, text, text, field=failed.get("location"), source=source))
    return findings


def validate(xml: bytes, schematron_dir: Path) -> list[Finding]:
    from saxonche import PySaxonProcessor

    findings: list[Finding] = []
    with PySaxonProcessor(license=False) as proc:
        xslt = proc.new_xslt30_processor()
        document = proc.parse_xml(xml_text=xml.decode("utf-8"))
        for name in STYLESHEETS:
            executable = xslt.compile_stylesheet(stylesheet_file=str(schematron_dir / name))
            result = executable.transform_to_string(xdm_node=document)
            findings.extend(parse_svrl(result.encode("utf-8"), source=name.split("-")[0]))
    return findings
