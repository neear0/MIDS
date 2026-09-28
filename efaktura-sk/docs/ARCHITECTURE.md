# Architecture

```
 Browser (Next.js, Slovak UI)
        │  JWT
        ▼
 FastAPI  /api/v1 ─────────────┬───────────────────────────────┐
   auth · companies · invoices │ dashboard · audit · ai · peppol│ integrations/webhooks
        │                      │                               │
        ▼                      ▼                               ▼
  services.py  ──►  domain (EN 16931 model) ──► ubl.generator ──► UBL 2.1 XML (legal document)
        │                 ▲         │                                   │
        │           ubl.parser      └──► validation engine ◄────────────┘
        │                 ▲               ├─ rules_en16931 / rules_peppol / rules_sk (fast, SK messages)
        │                 │               └─ schematron (official CEN + OpenPeppol XSLT, authoritative)
        │                 │
        │      ai.extraction (heuristic | Claude) ──► draft Invoice ──► validation ──► user confirms
        │      ai.explain (knowledge/*.md retrieval ± Claude)
        │
        ├──► PostgreSQL: users, companies, memberships, invoices(JSON + exact XML + SHA-256),
        │                transmissions (outbox), integrations (encrypted creds), audit_events (hash chain)
        │
 worker.py (loop; Celery/RQ in V1)
        ├── peppol.service.process_outbox ──► AccessPoint (mock | partner HTTP) ──► Peppol network
        │                                                        └──► tax data reported to Finančná správa
        ├── peppol.service.poll_inbox  ◄── incoming invoices
        └── integrations.sync (SuperFaktúra, every 30 min + webhooks)
```

## Key decisions

**One canonical model.** `app/domain/invoice.py` mirrors the EN 16931 semantic model and annotates
each field with its business term. Every input (form, AI extraction, SuperFaktúra, inbound Peppol
XML) becomes this model; every output (UBL, PDF, SuperFaktúra payload, future Money S3/Pohoda
exports) is produced from it. Adding a connector means writing two mapping functions.

**The XML is the legal document.** The exact UBL bytes are stored with a SHA-256 hash and are what
gets transmitted. The PDF is re-rendered on demand as a visual copy. Sent invoices are immutable;
corrections go through credit notes that reference the original (BG-3).

**Two validation layers.**
1. Python rules give instant, explainable feedback in Slovak (used by the live form).
2. The official CEN EN 16931 and OpenPeppol BIS 3.0 Schematron, compiled to XSLT and run with
   Saxon-HE, is authoritative. CI generates every supported document variant (invoice, credit note,
   reverse charge, foreign currency, exempt, non-VAT payer) and requires zero official errors.
   This caught a real bug during development: a non-VAT-payer invoice must not carry VAT IDs (BR-O-02).

**Peppol behind an interface.** MVP uses a certified partner Access Point; the `AccessPoint`
protocol (lookup/send/status/inbox/ack) is all the platform depends on. Sending goes through an
outbox table, so "send" works while the AP is down, retries back off exponentially, and permanent
failures (unknown receiver, rejected document) surface to the user instead of retrying forever.

**AI is optional and bounded.** Extraction produces a *draft* that is validated and confirmed by the
user; nothing AI-produced is stored or sent automatically. The offline heuristic extractor keeps
documents on-server for customers who do not consent to third-party processing. Explanations are
grounded in a curated Slovak knowledge base and cite their sources.

**Multi-tenancy.** Every query is scoped by `company_id` through a membership check
(`api/deps.company_for`), which also enforces roles. Accountants are simply members of many
companies.

## Data retention & GDPR notes

- Store in an EU region; keep the XML for the statutory retention period (10 years for invoices).
- SuperFaktúra/AP credentials are Fernet-encrypted (`EFAKTURA_SECRETS_KEY`).
- Enabling Claude extraction sends documents to Anthropic; cover it in the DPA and let each
  company opt in.
