"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Company } from "@/lib/types";
import { CompanyForm } from "../../CompanyForm";

interface Integration { id: number; kind: string; last_sync_at: string | null; last_error: string | null; webhook_path: string }
interface Member { user_id: number; email: string; full_name: string; role: string }
interface AuditEvent { id: number; action: string; created_at: string; details: Record<string, unknown> }

const ROLES: Record<string, string> = { owner: "Vlastník", accountant: "Účtovník", member: "Člen", viewer: "Len čítanie" };

export default function SettingsPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [company, setCompany] = useState<Company | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [audit, setAudit] = useState<{ chain_intact: boolean; events: AuditEvent[] } | null>(null);
  const [message, setMessage] = useState<{ tone: "red" | "green"; text: string } | null>(null);
  const [sf, setSf] = useState({ email: "", api_key: "", company_id: "", sandbox: false });
  const [invite, setInvite] = useState({ email: "", role: "accountant" });

  const load = useCallback(() => {
    api.get<Company>(`/companies/${companyId}`).then(setCompany);
    api.get<Integration[]>(`/companies/${companyId}/integrations`).then(setIntegrations);
    api.get<Member[]>(`/companies/${companyId}/members`).then(setMembers);
    api.get<typeof audit>(`/companies/${companyId}/audit?limit=50`).then(setAudit).catch(() => setAudit(null));
  }, [companyId]);
  useEffect(load, [load]);

  async function act(fn: () => Promise<string>) {
    setMessage(null);
    try {
      setMessage({ tone: "green", text: await fn() });
      load();
    } catch (e) {
      setMessage({ tone: "red", text: (e as Error).message });
    }
  }

  const superfaktura = integrations.find((i) => i.kind === "superfaktura");

  return (
    <Shell companyId={companyId}>
      <h1 className="text-2xl font-bold">Nastavenia</h1>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {company && (
        <Card title="Údaje firmy">
          {company.identifier_warnings.map((w) => <Alert key={w} tone="amber">{w}</Alert>)}
          <div className="mt-3">
            <CompanyForm key={company.id} initial={company} submitLabel="Uložiť zmeny" onSubmit={async (data) => {
              await act(async () => { await api.put(`/companies/${companyId}`, data); return "Údaje firmy boli uložené."; });
            }} />
          </div>
        </Card>
      )}

      <Card title="SuperFaktúra" actions={superfaktura && <Badge tone="green">Pripojené</Badge>}>
        {superfaktura ? (
          <div className="space-y-3 text-sm">
            <p>Posledná synchronizácia: {superfaktura.last_sync_at ? new Date(superfaktura.last_sync_at).toLocaleString("sk-SK") : "ešte neprebehla"}</p>
            {superfaktura.last_error && <Alert>{superfaktura.last_error}</Alert>}
            <p className="text-slate-600">Webhook URL pre SuperFaktúru: <code className="break-all">{superfaktura.webhook_path}</code></p>
            <Button onClick={() => act(async () => {
              const r = await api.post<{ created: number; updated: number; skipped: number }>(`/companies/${companyId}/integrations/superfaktura/sync`);
              return `Nové: ${r.created}, aktualizované: ${r.updated}, preskočené: ${r.skipped}`;
            })}>Synchronizovať teraz</Button>
          </div>
        ) : (
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e: FormEvent) => {
            e.preventDefault();
            act(async () => { await api.put(`/companies/${companyId}/integrations/superfaktura`, { ...sf, company_id: sf.company_id || null }); return "SuperFaktúra je pripojená."; });
          }}>
            <Field label="E-mail v SuperFaktúre"><Input type="email" required value={sf.email} onChange={(e) => setSf({ ...sf, email: e.target.value })} /></Field>
            <Field label="API kľúč" hint="Nájdete ho v SuperFaktúre v Nástroje → API."><Input required value={sf.api_key} onChange={(e) => setSf({ ...sf, api_key: e.target.value })} /></Field>
            <Field label="ID firmy (nepovinné)"><Input value={sf.company_id} onChange={(e) => setSf({ ...sf, company_id: e.target.value })} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sf.sandbox} onChange={(e) => setSf({ ...sf, sandbox: e.target.checked })} /> Testovacie prostredie (sandbox)</label>
            <div><Button type="submit">Pripojiť</Button></div>
          </form>
        )}
      </Card>

      <Card title="Používatelia a účtovník">
        <ul className="divide-y divide-slate-100 text-sm">
          {members.map((m) => <li key={m.user_id} className="flex justify-between py-2"><span>{m.full_name || m.email} <span className="text-slate-500">{m.email}</span></span><Badge>{ROLES[m.role] ?? m.role}</Badge></li>)}
        </ul>
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(e: FormEvent) => {
          e.preventDefault();
          act(async () => { await api.post(`/companies/${companyId}/members`, invite); return "Používateľ bol pridaný."; });
        }}>
          <div className="flex-1"><Field label="E-mail registrovaného používateľa"><Input type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></Field></div>
          <Field label="Rola"><Select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>
            {Object.entries(ROLES).filter(([k]) => k !== "owner").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select></Field>
          <Button type="submit">Pridať</Button>
        </form>
      </Card>

      <Card title="Auditný záznam" actions={audit && <Badge tone={audit.chain_intact ? "green" : "red"}>{audit.chain_intact ? "Reťazec neporušený" : "Reťazec narušený!"}</Badge>}>
        <div id="audit" />
        {!audit ? <Empty>Auditný záznam vidí len vlastník a účtovník.</Empty> : (
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto text-sm">
            {audit.events.map((ev) => (
              <li key={ev.id} className="flex justify-between gap-4 py-2">
                <span className="font-mono text-xs">{ev.action}</span>
                <span className="text-slate-500">{new Date(ev.created_at).toLocaleString("sk-SK")}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Shell>
  );
}
