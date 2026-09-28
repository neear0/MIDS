"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Shell, useCompany } from "@/components/Shell";
import { Alert, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import type { Invoice, InvoiceDetail } from "@/lib/types";
import { DRAFT_KEY, emptyInvoice, InvoiceForm } from "./InvoiceForm";

export default function NewInvoicePage() {
  const { companyId } = useParams<{ companyId: string }>();
  const router = useRouter();
  const company = useCompany(companyId);
  // Draft handed over from the upload page (read once; removed after mount).
  const [draft] = useState<Partial<Invoice> | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const stored = window.sessionStorage.getItem(DRAFT_KEY);
      return stored ? (JSON.parse(stored) as Partial<Invoice>) : null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    try {
      window.sessionStorage.removeItem(DRAFT_KEY);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const initial = useMemo<Invoice | null>(() => {
    if (!company) return null;
    const base = emptyInvoice(company);
    if (!draft) return base;
    return { ...base, ...draft, lines: draft.lines?.length ? draft.lines : base.lines };
  }, [company, draft]);
  const fromDocument = Boolean(draft);

  return (
    <Shell companyId={companyId}>
      <h1 className="text-2xl font-bold">Nová faktúra</h1>
      {fromDocument && <Alert tone="amber">Údaje boli načítané z nahratého dokladu. Skontrolujte ich pred uložením.</Alert>}
      {company && initial ? (
        <InvoiceForm company={company} initial={initial} submitLabel="Uložiť faktúru" onSubmit={async (inv) => {
          const created = await api.post<InvoiceDetail>(`/companies/${companyId}/invoices`, inv);
          router.push(`/firmy/${companyId}/faktury/${created.id}`);
        }} />
      ) : <Empty>Načítavam…</Empty>}
    </Shell>
  );
}
