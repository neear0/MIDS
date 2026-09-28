"""Compile the official EN 16931 / Peppol Schematron files to XSLT with SchXslt + Saxon-HE.

Usage:
    python scripts/build_schematron.py <peppol-bis-invoice-3/rules/sch> <schxslt-dir> <out-dir>

`schxslt-dir` is the unpacked SchXslt jar (name.dmaus.schxslt:schxslt on Maven
Central); it must contain xslt/2.0/pipeline-for-svrl.xsl. See
scripts/fetch_validation_artifacts.sh for the full download recipe.
"""

from __future__ import annotations

import sys
from pathlib import Path

from saxonche import PySaxonProcessor

NAMES = ("CEN-EN16931-UBL", "PEPPOL-EN16931-UBL")


def main(sch_dir: Path, schxslt_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline = schxslt_dir / "xslt" / "2.0" / "pipeline-for-svrl.xsl"
    with PySaxonProcessor(license=False) as proc:
        compiler = proc.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(pipeline))
        for name in NAMES:
            result = compiler.transform_to_string(source_file=str(sch_dir / f"{name}.sch"))
            (out_dir / f"{name}.xslt").write_text(result, encoding="utf-8")
            print(f"compiled {name}.xslt")


if __name__ == "__main__":
    main(*(Path(arg) for arg in sys.argv[1:4]))
