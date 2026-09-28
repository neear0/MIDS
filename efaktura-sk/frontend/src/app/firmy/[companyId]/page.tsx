"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Shell } from "@/components/Shell";
import { Alert, Card, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";

interface Brief { id: number; number: string; counterparty: string; due_date: string | null; amount: string; currency: string; days_overdue: number }
interface Dashboard {
  counts: Record<string, number>;
  compliance_score: number | null;
  readiness: { key: string; ok: boolean; label: string }[];
  receivables: { overdue: Brief[]; overdue_total: string; due_soon: Brief[] };
  payables_due: Brief[];
  invalid_invoices: Brief[];
  deadlines: { date: string; title: string; detail: string; days_left: number }[];
}

function Stat({ label, value, tone = "text-slate-900" }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function BriefList({ items, companyId, empty }: { items: Brief[]; companyId: string; empty: string }) {
  if (!items.length) return <Empty>{empty}</Empty>;
  return (
    <ul className="divide-y divide-slate-100 text-sm">
      {items.map((b) => (
        <li key={b.id}>
          <Link href={`/firmy/${companyId}/faktury/${b.id}`} className="flex justify-between py-2 hover:bg-slate-50">
            <span>
              <span className="font-medium">{b.number}</span> · {b.counterparty}
              {b.days_overdue > 0 && <span className="ml-2 text-rose-600">{b.days_overdue} dní po splatnosti</span>}
            </span>
            <span>{money(b.amount, b.currency)} · {date(b.due_date)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Dashboard>(`/companies/${companyId}/dashboard`).then(setData).catch((e) => setError(e.message));
  }, [companyId]);

  return (
    <Shell companyId={companyId}>
      <h1 className="text-2xl font-bold">Prehľad</h1>
      <Alert>{error}</Alert>
      {data && (
        <>
          {data.deadlines.map((d) => (
            <Alert key={d.date} tone="blue">
              <strong>{d.title}</strong> – o {d.days_left} dní ({date(d.date)}). {d.detail}
            </Alert>
          ))}
          <div className="grid gap-4 sm:grid-cols-4">
            <Stat label="Súlad faktúr" value={data.compliance_score === null ? "–" : `${data.compliance_score} %`}
              tone={data.compliance_score !== null && data.compliance_score < 100 ? "text-amber-600" : "text-emerald-600"} />
            <Stat label="Doručené cez Peppol" value={data.counts.delivered ?? 0} />
            <Stat label="S chybami" value={data.counts.invalid ?? 0} tone={data.counts.invalid ? "text-rose-600" : undefined} />
            <Stat label="Po splatnosti" value={money(data.receivables.overdue_total)} tone={data.receivables.overdue.length ? "text-rose-600" : undefined} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Pripravenosť na e-fakturáciu 2027">
              <ul className="space-y-2 text-sm">
                {data.readiness.map((r) => (
                  <li key={r.key} className="flex items-center gap-2">
                    <span className={r.ok ? "text-emerald-600" : "text-rose-600"}>{r.ok ? "✓" : "✗"}</span>
                    {r.label}
                  </li>
                ))}
              </ul>
              {data.readiness.some((r) => !r.ok) && (
                <Link href={`/firmy/${companyId}/nastavenia`} className="mt-3 inline-block text-sm text-brand-600 hover:underline">
                  Doplniť údaje →
                </Link>
              )}
            </Card>
            <Card title="Faktúry na opravu">
              <BriefList items={data.invalid_invoices} companyId={companyId} empty="Všetky faktúry sú v poriadku." />
            </Card>
            <Card title="Pohľadávky po splatnosti">
              <BriefList items={data.receivables.overdue} companyId={companyId} empty="Nikto vám nedlží. 🎉" />
            </Card>
            <Card title="Splatné tento týždeň">
              <BriefList items={[...data.receivables.due_soon, ...data.payables_due]} companyId={companyId} empty="Tento týždeň nič nesplatné." />
            </Card>
          </div>
        </>
      )}
    </Shell>
  );
}
