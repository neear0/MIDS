#!/usr/bin/env bash
# Download the official EN 16931 + Peppol BIS Billing 3.0 Schematron and compile
# it to XSLT so the API can run authoritative validation (app/validation/schematron.py).
#
#   pip install -e ".[schematron]"
#   scripts/fetch_validation_artifacts.sh [out-dir]   # default: ./validation-artifacts
set -euo pipefail

OUT="${1:-validation-artifacts}"
PEPPOL_REF="${PEPPOL_REF:-master}"
SCHXSLT_VERSION="${SCHXSLT_VERSION:-1.10.1}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --quiet --depth 1 --branch "$PEPPOL_REF" https://github.com/OpenPEPPOL/peppol-bis-invoice-3 "$WORK/peppol"
curl -fsSL -o "$WORK/schxslt.jar" \
  "https://repo1.maven.org/maven2/name/dmaus/schxslt/schxslt/${SCHXSLT_VERSION}/schxslt-${SCHXSLT_VERSION}.jar"
mkdir -p "$WORK/schxslt"
python -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$WORK/schxslt.jar" "$WORK/schxslt"

python "$(dirname "$0")/build_schematron.py" "$WORK/peppol/rules/sch" "$WORK/schxslt" "$OUT"
git -C "$WORK/peppol" rev-parse HEAD > "$OUT/PEPPOL_COMMIT"
echo "Validation artefacts written to $OUT"
