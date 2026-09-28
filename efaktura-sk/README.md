# eFaktúra SK

AI-powered Slovak e-invoice & tax compliance platform, built for the mandatory B2B e-invoicing
that starts on **1 January 2027**: EN 16931 invoices in **UBL 2.1** / **Peppol BIS Billing 3.0**,
delivered through a certified Peppol Access Point, with Slovak identifiers (`0245:DIČ`), Slovak
VAT rules and plain-Slovak explanations. Target users: živnostníci, micro/small firms and their
accountants.

- **Phases and status:** [`docs/ROADMAP.md`](docs/ROADMAP.md)
- **Design:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## What works today

- Create invoices and credit notes → valid **UBL 2.1 / Peppol BIS 3.0** XML plus a PDF with a
  **PAY by square** QR code.
- **Validation**: EN 16931, Peppol and Slovak rules (IČO/DIČ/IČ DPH checks, 2025 VAT rates, credit
  note references, reverse-charge wording, VAT in EUR…). Messages and fix hints are in Slovak. When
  the **official CEN + OpenPeppol Schematron** is installed, it runs too. CI proves every generated
  document variant passes it.
- **AI extraction** from PDFs, scans and photos into a draft invoice. It runs offline (heuristic) or
  with Claude.
- **"Vysvetliť"** on every error, plus a help page. Answers come from a curated Slovak knowledge base.
- **SuperFaktúra** import sync, webhook and push.
- **Peppol**: send/receive through an Access Point adapter. It uses an outbox with retries, polls the
  inbox, and tracks the tax-report status. A mock AP delivers between companies on the platform for
  demos.
- **Multi-company, multi-user** with roles (owner, accountant, member, viewer), a tamper-evident
  audit trail, and a dashboard showing 2027 readiness, compliance score and overdue invoices.

## Quick start

```bash
# Backend (Python 3.11+)
cd backend
pip install -e ".[dev,schematron]"
scripts/fetch_validation_artifacts.sh            # optional: official Schematron → ./validation-artifacts
uvicorn app.main:app --reload                    # http://localhost:8000/docs
python -m app.worker                             # Peppol outbox/inbox + SuperFaktúra sync
pytest -q                                        # SCHEMATRON_DIR=validation-artifacts to run conformance tests

# Frontend (Node 22)
cd frontend
npm install
npm run dev                                      # http://localhost:3000

# Or everything at once
docker compose up --build
```

By default everything runs locally with SQLite, the offline extractor and the mock Access Point. See
`backend/.env.example` to switch to PostgreSQL, Claude extraction (`EFAKTURA_EXTRACTION_PROVIDER=anthropic`)
or a partner Access Point (`EFAKTURA_PEPPOL_PROVIDER=http`).

## Layout

```
backend/
  app/domain/        canonical EN 16931 model, SK identifiers, VAT rates
  app/ubl/           UBL 2.1 generator + parser
  app/validation/    rules engine (EN 16931, Peppol, SK) + official Schematron runner
  app/pdf/           PDF renderer + PAY by square encoder
  app/ai/            extraction (heuristic / Claude), explanations + knowledge base
  app/integrations/  SuperFaktúra client, mapping, sync; Money S3 / Pohoda stubs
  app/peppol/        Access Point adapters, outbox, inbox
  app/api/           FastAPI routers
  scripts/           Schematron download + compile
  tests/             55 tests incl. official Schematron conformance
frontend/            Next.js 16 + Tailwind, Slovak UI
docs/                roadmap, architecture
```

## Important caveats

- **Legal review needed.** Slovak rules in `rules_sk.py` are product checks, not an official national
  CIUS. When Finančná správa publishes its technical specification, mirror it there. Have a tax advisor
  review the knowledge base.
- **Partner APIs must be verified.** The SuperFaktúra field names follow its public docs. The
  `HttpAccessPoint` is a template to map onto the contracted Access Point's API. Neither has been run
  against a live account yet.
