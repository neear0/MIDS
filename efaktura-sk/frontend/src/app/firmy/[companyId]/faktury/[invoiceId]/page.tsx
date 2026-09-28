"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Findings } from "@/components/Findings";
import { Shell } from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import { date, DOC_TYPES, money, STATUS_LABELS } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";

const TX_STATUS: Record<string, string> = { queued: "čaká na odoslanie", sent: "odoslaná", delivered: "doručená", failed: "zlyhala" };

export default function InvoiceDetailPage() {
  const { companyId, invoiceId } = useParams<{ companyId: string; invoiceId: string }>();
  const router = useRouter();
  const base = `/companies/${companyId}/invoices/${invoiceId}`;
  const [inv, setInv] = useState<InvoiceDetail | null>(null);
  const [message, setMessage] = useState<{ tone: "red" | "green"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<InvoiceDetail>(base).then(setInv).catch((e) => setMessage({ tone: "red", text: e.message }));
  }, [base]);
  useEffect(load, [load]);

  async function act(fn: () => Promise<string | void>) {
    setBusy(true);
    setMessage(null);
    try {
      const text = await fn();
      if (text) setMessage({ tone: "green", text });
      load();
    } catch (e) {
      setMessage({ tone: "red", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (!inv) return <Shell companyId={companyId}>{message ? <Alert>{message.text}</Alert> : <Empty>Načítavam…</Empty>}</Shell>;

  const d = inv.invoice;
  const status = STATUS_LABELS[inv.status] ?? { label: inv.status, tone: "gray" as const };
  const outgoing = inv.direction === "outgoing";
  const canSend = outgoing && ["valid", "failed"].includes(inv.status);

  return (
    <Shell companyId={companyId}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">{DOC_TYPES[inv.document_type]} · {outgoing ? "vydaná" : "prijatá"}</p>
          <h1 className="text-2xl font-bold">{inv.number} <Badge tone={status.tone}>{status.label}</Badge></h1>
          {d.preceding_invoice && <p className="text-sm text-slate-600">K faktúre č. {d.preceding_invoice.number}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => act(() => api.download(`${base}/pdf`, `${inv.number}.pdf`, true))}>PDF</Button>
          <Button variant="secondary" onClick={() => act(() => api.download(`${base}/ubl`, `${inv.number}.xml`))}>XML (UBL)</Button>
          {outgoing && !inv.paid_at && inv.document_type !== "381" && (
            <Button variant="secondary" disabled={busy} onClick={() => act(async () => { await api.post(`${base}/paid`); return "Faktúra je označená ako uhradená."; })}>Uhradená</Button>
          )}
          {outgoing && inv.document_type !== "381" && (
            <Button variant="secondary" disabled={busy} onClick={() => act(async () => {
              const cn = await api.post<InvoiceDetail>(`${base}/credit-note`, {});
              router.push(`/firmy/${companyId}/faktury/${cn.id}`);
            })}>Vystaviť dobropis</Button>
          )}
          {canSend && (
            <Button disabled={busy} onClick={() => act(async () => {
              const r = await api.post<InvoiceDetail>(`${base}/send`);
              return r.status === "delivered" ? "Faktúra bola doručená cez sieť Peppol." : "Faktúra je vo fronte na odoslanie.";
            })}>Odoslať cez Peppol</Button>
          )}
        </div>
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {inv.status === "invalid" && <Alert>Faktúra obsahuje chyby a nemôže byť odoslaná. Opravte ich podľa zoznamu nižšie.</Alert>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <div className="grid gap-6 sm:grid-cols-2 text-sm">
              {[{ t: "Dodávateľ", p: d.seller }, { t: "Odberateľ", p: d.buyer }].map(({ t, p }) => (
                <div key={t}>
                  <p className="font-semibold">{t}</p>
                  <p>{p.name}</p>
                  <p className="text-slate-600">{p.address.street}, {p.address.postal_code} {p.address.city}</p>
                  <p className="text-slate-600">IČO {p.ico ?? "–"} · DIČ {p.dic ?? "–"} {p.ic_dph ? `· IČ DPH ${p.ic_dph}` : ""}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <p><span className="text-slate-500">Vystavená</span><br />{date(d.issue_date)}</p>
              <p><span className="text-slate-500">Dodanie</span><br />{date(d.delivery_date)}</p>
              <p><span className="text-slate-500">Splatnosť</span><br />{date(d.due_date)}</p>
              <p><span className="text-slate-500">VS</span><br />{d.payment.variable_symbol ?? "–"}</p>
            </div>
          </Card>
          <Card title="Položky">
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500"><tr><th>Názov</th><th className="text-right">Množstvo</th><th className="text-right">Cena</th><th className="text-right">DPH</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {d.lines.map((l) => (
                  <tr key={l.id}><td className="py-2">{l.name}</td><td className="text-right">{l.quantity}</td><td className="text-right">{money(l.unit_price, d.currency)}</td><td className="text-right">{l.vat_category === "S" ? `${Number(l.vat_rate)} %` : l.vat_category}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-right text-lg font-semibold">K úhrade {money(inv.total_payable, inv.currency)}</p>
          </Card>
          {inv.transmissions.length > 0 && (
            <Card title="Doručenie cez Peppol">
              <ul className="space-y-2 text-sm">
                {inv.transmissions.map((t) => (
                  <li key={t.id}>
                    {TX_STATUS[t.status] ?? t.status}
                    {t.tax_report_status === "reported" && " · nahlásená Finančnej správe"}
                    {t.last_error && <span className="text-rose-600"> · {t.last_error}</span>}
                    <span className="text-slate-400"> · pokusy: {t.attempts}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card title="Kontrola súladu"><Findings validation={inv.validation} /></Card>
          <Card title="Audit">
            <p className="break-all text-xs text-slate-500">SHA-256 XML: {inv.ubl_sha256}</p>
            <Link href={`/firmy/${companyId}/nastavenia#audit`} className="mt-2 inline-block text-sm text-brand-600 hover:underline">Auditný záznam →</Link>
          </Card>
        </div>
      </div>
    </Shell>
  );
}
