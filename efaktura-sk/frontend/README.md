# eFaktúra SK — web

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. Slovak UI for the eFaktúra SK API.

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
npm run lint && npm run build
```

| Route | Screen |
|---|---|
| `/prihlasenie` | Login / registration |
| `/firmy` | Company switcher (accountants manage many companies) |
| `/firmy/[id]` | Dashboard: 2027 readiness, compliance score, overdue, deadlines |
| `/firmy/[id]/faktury` | Issued / received invoices, Peppol inbox poll, UBL import |
| `/firmy/[id]/faktury/nova` | Invoice form with live totals and live EN 16931 / SK validation |
| `/firmy/[id]/faktury/[invoiceId]` | Detail: findings + "Vysvetliť", PDF/XML, Peppol send, credit note |
| `/firmy/[id]/nahrat` | Upload PDF/scan → AI extraction → prefilled invoice |
| `/firmy/[id]/nastavenia` | Company profile, SuperFaktúra, members/roles, audit trail |
| `/pomoc` | Plain-Slovak Q&A over the knowledge base |
