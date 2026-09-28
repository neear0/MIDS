# Roadmap

Legislative anchor: **1 January 2027**, mandatory structured B2B e-invoicing between Slovak VAT
payers (EN 16931, Peppol, 5-corner model with simultaneous reporting to Finančná správa).

Legend: ✅ built and tested in this repo · 🟡 scaffolded / partial · ⬜ not started

---

## Phase 0 — Foundation ✅

| Item | Status | Where |
|---|---|---|
| Monorepo layout (`backend/`, `frontend/`, `docs/`) | ✅ | |
| Docker Compose (Postgres 16, API, worker, web) | ✅ | `docker-compose.yml` |
| CI: lint, tests, official Schematron conformance, Next build | ✅ | `.github/workflows/efaktura-sk.yml` |
| Settings via env (`EFAKTURA_*`), `.env.example` | ✅ | `backend/app/config.py` |
| DB migrations (Alembic) | ⬜ | `create_all` is used until the schema settles |

## Phase 1 — MVP core: compliant invoices (months 1–2) ✅

| Item | Status | Where |
|---|---|---|
| Canonical EN 16931 model (BT/BG-annotated), Decimal money, VAT breakdown | ✅ | `app/domain/invoice.py` |
| Slovak identifiers: IČO checksum, DIČ, IČ DPH (mod 11), IBAN | ✅ | `app/domain/identifiers.py` |
| SK VAT rates by date (23/19/5 from 2025; 20/10/5 before) | ✅ | `app/domain/vat.py` |
| UBL 2.1 Invoice + CreditNote generation, Peppol BIS Billing 3.0, endpoint `0245:DIČ` | ✅ | `app/ubl/generator.py` |
| UBL parser (inbound documents, uploaded XML) | ✅ | `app/ubl/parser.py` |
| Rules engine: EN 16931 + Peppol + SK rules, Slovak messages + fix hints | ✅ | `app/validation/` |
| Official CEN + OpenPeppol Schematron (Saxon-HE), run in CI on every generated variant | ✅ | `app/validation/schematron.py`, `scripts/` |
| Human-readable PDF with PAY by square QR | ✅ | `app/pdf/` |
| Registration/login (JWT), company profiles, roles (owner/accountant/member/viewer) | ✅ | `app/api/auth.py`, `companies.py` |
| Invoice CRUD, auto-numbering, credit notes (dobropis) referencing original | ✅ | `app/services.py`, `app/api/invoices.py` |
| Immutable after sending; corrections only via credit note | ✅ | `services.update_outgoing` |
| Hash-chained, tamper-evident audit log | ✅ | `app/audit.py` |
| Dashboard: 2027 readiness, compliance score, overdue/due-soon, deadlines | ✅ | `app/api/dashboard.py` |
| Corrected invoice (384) flow in UI | 🟡 | model + validation support it; no dedicated UI yet |
| Document-level allowances/charges (BG-20/21) | ⬜ | line discounts only |
| XSD validation (UBL 2.1 schemas) | ⬜ | Schematron covers business rules; add XSD for structure |

## Phase 2 — AI layer (month 2–3) ✅ / 🟡

| Item | Status | Where |
|---|---|---|
| Offline heuristic extraction from text PDFs (no data leaves the server) | ✅ | `app/ai/extraction.py` |
| Claude-based extraction for scans/photos with schema-validated output | ✅ (unit-tested mapping; needs live API key to exercise) | `ClaudeExtractor` |
| Plain-Slovak explanations: curated knowledge base + retrieval, optional LLM answer grounded in articles | ✅ | `app/ai/explain.py`, `app/ai/knowledge/` |
| Evaluation set of real Slovak invoices (accuracy per field) | ⬜ | needed before marketing AI accuracy |
| EU-hosted LLM option (e.g. Mistral) behind the same `Extractor` interface | ⬜ | |
| Legislative-change feed ("what changed this month") | ⬜ | |

## Phase 3 — SuperFaktúra integration (month 3) ✅ / 🟡

| Item | Status | Where |
|---|---|---|
| REST client (SFAPI auth header, retries, pagination) | ✅ (mock-transport tested) | `app/integrations/superfaktura.py` |
| SF → canonical mapping (units, % discounts, credit notes, non-VAT payers) | ✅ | `from_superfaktura` |
| Canonical → SF payload (push invoices created here) | ✅ | `to_superfaktura` |
| Idempotent import sync + token-authenticated webhook (re-fetches by id) | ✅ | `app/integrations/sync.py`, `app/api/integrations.py` |
| Credentials encrypted at rest (Fernet) | ✅ | `app/security.py` |
| Verification against the SuperFaktúra sandbox with a real account | ⬜ | **next step**: field names follow public docs but must be confirmed |
| Payment status sync back from SF | ⬜ | |

## Phase 4 — Peppol via partner Access Point (months 3–5) 🟡

| Item | Status | Where |
|---|---|---|
| `AccessPoint` interface (lookup/send/status/inbox/ack) | ✅ | `app/peppol/access_point.py` |
| Mock AP with loopback delivery between platform companies (demo & tests) | ✅ | `MockAccessPoint` |
| Generic HTTP partner adapter template | 🟡 | `HttpAccessPoint` — map to the contracted partner's real API |
| Outbox with exponential backoff, permanent vs retryable errors, status polling | ✅ | `app/peppol/service.py` |
| Inbox polling → stored, validated incoming invoices | ✅ | `poll_inbox` |
| Tracking of 5-corner tax reporting status per transmission | 🟡 | field + UI exist; semantics depend on partner/FS spec |
| Partner selection & contract (certified Slovak-capable AP with API) | ⬜ | business task |
| Finančná správa national specification (CIUS / extra fields) mirrored in `rules_sk.py` | ⬜ | track FS publications |

## Phase 5 — Web app (months 2–5) ✅

Next.js 16 + Tailwind, Slovak UI: login, company switcher, dashboard, invoice list (issued/received),
invoice form with live totals + live validation, invoice detail with "Vysvetliť" per finding,
PDF/XML download, Peppol send, credit note, upload → extraction → prefilled form, settings
(company, SuperFaktúra, members/roles, audit trail), help Q&A. Verified end-to-end in Chromium.

Still to do: i18n framework (UI is Slovak-only), offline draft queue (PWA) for small users,
accessibility audit, onboarding wizard.

---

## V1 (months 6–11)

- ⬜ **Money S3** export/import (XML import module; verify against Solitea XSD + test install) — interface stub in `app/integrations/accounting_exports.py`
- ⬜ Full Peppol send + receive with the contracted partner in production
- ⬜ Accountant mode UX: bulk actions across companies, client invitations by e-mail
- ⬜ Automated reminders (e-mail) for overdue receivables and upcoming payables — data already on the dashboard
- ⬜ Basic e-reporting exports (VAT ledger / kontrolný výkaz support)
- ⬜ Celery/RQ + Redis replacing the simple worker loop; rate limiting
- ⬜ Object storage (S3-compatible, EU region) for original uploads and archived XML/PDF (10-year retention)
- ⬜ Stripe subscriptions (EUR), plan limits
- ⬜ Sentry + structured logging

## Later

- ⬜ **Pohoda** (Stormware `dataPack` XML) — stub in `accounting_exports.py`
- ⬜ iDoklad, Omega and other connectors
- ⬜ Own Peppol Access Point certification (when volume justifies it)
- ⬜ Mobile app (photo capture → extraction)
- ⬜ White-label for accounting firms, advanced analytics

## Non-functional checklist

| Requirement | Current state |
|---|---|
| EU data residency | Deploy target EU region; heuristic extraction keeps documents on-server; Claude extraction is opt-in (needs DPA) |
| GDPR | Minimal personal data; credentials encrypted; audit trail; ⬜ data export/erasure endpoints |
| Audit logs | ✅ hash-chained per company, verifiable via API |
| Slovak error messages | ✅ every rule has SK message + hint; API errors in Slovak |
| Offline / delayed sync | ✅ server-side outbox; ⬜ client-side offline drafts |
| Grant evidence (SIEA vouchers) | Track: invoices validated, errors caught before sending, time per invoice |
