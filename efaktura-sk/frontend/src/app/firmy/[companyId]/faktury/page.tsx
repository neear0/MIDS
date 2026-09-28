"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Shell } from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import { date, DOC_TYPES, money, STATUS_LABELS } from "@/lib/format";
import type { InvoiceSummary } from "@/lib/types";

export default function InvoicesPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [direction, setDirection] = useState<"outgoing" | "incoming">("outgoing");
  const [items, setItems] = useState<InvoiceSummary[] | null>(null);
  const [message, setMessage] = useState<{ tone: "red" | "green"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.get<InvoiceSummary[]>(`/companies/${companyId}/invoices?direction=${direction}`).then(setItems);
  }, [companyId, direction]);
  useEffect(load, [load]);

  async function run(action: () => Promise<string>) {
    setMessage(null);
    try {
      setMessage({ tone: "green", text: await action() });
      load();
    } catch (e) {
      setMessage({ tone: "red", text: (e as Error).message });
    }
  }

  return (
    <Shell companyId={companyId}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Faktúry</h1>
        <div className="flex gap-2">
          {direction === "incoming" ? (
            <>
              <Button variant="secondary" onClick={() => run(async () => {
                const r = await api.post<{ received: number }>(`/companies/${companyId}/peppol/poll`);
                return `Prijatých nových faktúr: ${r.received}`;
              })}>Skontrolovať Peppol</Button>
              <Button variant="secondary" onClick={() => fileRef.current?.click()}>Importovať XML</Button>
              <input ref={fileRef} type="file" accept=".xml,application/xml" hidden onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const form = new FormData();
                form.append("file", file);
                run(async () => {
                  const r = await api.post<InvoiceSummary>(`/companies/${companyId}/invoices/import-ubl`, form);
                  return `Faktúra ${r.number} bola uložená.`;
                });
                e.target.value = "";
              }} />
            </>
          ) : (
            <Link href={`/firmy/${companyId}/faktury/nova`}><Button>+ Nová faktúra</Button></Link>
          )}
        </div>
      </div>
      <div className="flex gap-2">
        {(["outgoing", "incoming"] as const).map((d) => (
          <button key={d} onClick={() => setDirection(d)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${direction === d ? "bg-brand-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"}`}>
            {d === "outgoing" ? "Vydané" : "Prijaté"}
          </button>
        ))}
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      <Card>
        {items === null ? <Empty>Načítavam…</Empty> : items.length === 0 ? (
          <Empty>{direction === "outgoing" ? "Zatiaľ ste nevystavili žiadnu faktúru." : "Zatiaľ nemáte žiadne prijaté faktúry."}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr><th className="py-2">Číslo</th><th>{direction === "outgoing" ? "Odberateľ" : "Dodávateľ"}</th><th>Vystavená</th><th>Splatná</th><th className="text-right">Suma</th><th>Stav</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((inv) => {
                  const status = STATUS_LABELS[inv.status] ?? { label: inv.status, tone: "gray" as const };
                  return (
                    <tr key={inv.id} className="hover:bg-slate-50">
                      <td className="py-2">
                        <Link href={`/firmy/${companyId}/faktury/${inv.id}`} className="font-medium text-brand-700 hover:underline">{inv.number}</Link>
                        {inv.document_type !== "380" && <span className="ml-2 text-xs text-slate-500">{DOC_TYPES[inv.document_type]}</span>}
                      </td>
                      <td>{inv.counterparty_name}</td>
                      <td>{date(inv.issue_date)}</td>
                      <td>{inv.paid_at ? <span className="text-emerald-700">uhradená</span> : date(inv.due_date)}</td>
                      <td className="text-right">{money(inv.total_payable, inv.currency)}</td>
                      <td><Badge tone={status.tone}>{status.label}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </Shell>
  );
}
