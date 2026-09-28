"use client";

import { useEffect, useMemo, useState } from "react";

import { Findings } from "@/components/Findings";
import { Alert, Button, Card, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { money, UNITS, VAT_CATEGORIES } from "@/lib/format";
import type { Company, Invoice, InvoiceLine, Validation } from "@/lib/types";

export const DRAFT_KEY = "efaktura.draft";

const today = () => new Date().toISOString().slice(0, 10);
const addDays = (iso: string, days: number) => {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

export function emptyLine(id = "1", payer = true): InvoiceLine {
  return { id, name: "", quantity: "1", unit_code: "C62", unit_price: "0", vat_category: payer ? "S" : "O", vat_rate: payer ? "23" : "0", line_discount: "0" };
}

export function emptyInvoice(company: Company): Invoice {
  const issue = today();
  return {
    number: "", document_type: "380", issue_date: issue, delivery_date: issue, due_date: addDays(issue, company.default_due_days),
    currency: "EUR", buyer_reference: "", order_reference: "", notes: [],
    seller: { name: company.name, address: { country_code: "SK" } },
    buyer: { name: "", ico: "", dic: "", ic_dph: "", address: { street: "", city: "", postal_code: "", country_code: "SK" } },
    lines: [emptyLine("1", Boolean(company.ic_dph))], payment: {},
  };
}

const ADDRESS_KEYS = ["street", "city", "postal_code", "country_code"];

const round2 =(n: number) => Math.round((n + Number.EPSILON) * 100) / 100;

function totals(lines: InvoiceLine[]) {
  const groups = new Map<string, number>();
  let net = 0;
  for (const l of lines) {
    const lineNet = round2(Number(l.quantity) * Number(l.unit_price) - Number(l.line_discount || 0));
    net += lineNet;
    const rate = l.vat_category === "S" ? Number(l.vat_rate) : 0;
    groups.set(`${l.vat_category}|${rate}`, (groups.get(`${l.vat_category}|${rate}`) ?? 0) + lineNet);
  }
  let vat = 0;
  for (const [key, base] of groups) vat += round2((base * Number(key.split("|")[1])) / 100);
  return { net: round2(net), vat: round2(vat), total: round2(net + vat) };
}

function sellerParty(company: Company) {
  return {
    name: company.name, ico: company.ico, dic: company.dic, ic_dph: company.ic_dph,
    address: { street: company.street, city: company.city, postal_code: company.postal_code, country_code: company.country_code },
  };
}

export function InvoiceForm({ company, initial, submitLabel, onSubmit }: {
  company: Company;
  initial: Invoice;
  submitLabel: string;
  onSubmit: (invoice: Invoice) => Promise<void>;
}) {
  const [inv, setInv] = useState<Invoice>(initial);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [peppol, setPeppol] = useState<string | null>(null);
  const t = useMemo(() => totals(inv.lines), [inv.lines]);

  // Live validation with the same defaults the server will fill in on save.
  useEffect(() => {
    const timer = setTimeout(() => {
      const draft: Invoice = {
        ...inv,
        number: inv.number || "AUTO",
        seller: sellerParty(company),
        payment: { ...inv.payment, iban: inv.payment.iban || company.iban, variable_symbol: inv.payment.variable_symbol || "1" },
      };
      api.post<Validation>("/validate/draft", draft).then(setValidation).catch(() => undefined);
    }, 600);
    return () => clearTimeout(timer);
  }, [inv, company]);

  const setBuyer = (key: string, value: string) =>
    setInv({ ...inv, buyer: ADDRESS_KEYS.includes(key)
      ? { ...inv.buyer, address: { ...inv.buyer.address, [key]: value } }
      : { ...inv.buyer, [key]: value } });
  const setLine = (idx: number, patch: Partial<InvoiceLine>) =>
    setInv({ ...inv, lines: inv.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) });

  async function checkPeppol() {
    setPeppol(null);
    try {
      const r = await api.get<{ registered: boolean }>(`/peppol/lookup?dic=${encodeURIComponent(inv.buyer.dic ?? "")}`);
      setPeppol(r.registered ? "✓ Odberateľ je v sieti Peppol." : "Odberateľ zatiaľ nie je v sieti Peppol.");
    } catch (e) {
      setPeppol((e as Error).message);
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ ...inv, seller: sellerParty(company) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card title="Odberateľ">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Obchodné meno *"><Input value={inv.buyer.name} onChange={(e) => setBuyer("name", e.target.value)} /></Field>
            <Field label="IČO"><Input value={inv.buyer.ico ?? ""} onChange={(e) => setBuyer("ico", e.target.value)} /></Field>
            <div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Field label="DIČ"><Input value={inv.buyer.dic ?? ""} onChange={(e) => setBuyer("dic", e.target.value)} /></Field>
                </div>
                <Button type="button" variant="secondary" onClick={checkPeppol} disabled={!inv.buyer.dic}>Overiť v Peppol</Button>
              </div>
              <p className="mt-1 text-xs text-slate-500">{peppol ?? "Z DIČ sa odvodí Peppol adresa odberateľa."}</p>
            </div>
            <Field label="IČ DPH"><Input value={inv.buyer.ic_dph ?? ""} onChange={(e) => setBuyer("ic_dph", e.target.value)} /></Field>
            <Field label="Ulica"><Input value={inv.buyer.address.street ?? ""} onChange={(e) => setBuyer("street", e.target.value)} /></Field>
            <div className="grid grid-cols-3 gap-2">
              <Field label="PSČ"><Input value={inv.buyer.address.postal_code ?? ""} onChange={(e) => setBuyer("postal_code", e.target.value)} /></Field>
              <div className="col-span-2"><Field label="Mesto"><Input value={inv.buyer.address.city ?? ""} onChange={(e) => setBuyer("city", e.target.value)} /></Field></div>
            </div>
          </div>
        </Card>

        <Card title="Položky">
          <div className="space-y-3">
            {inv.lines.map((line, idx) => (
              <div key={idx} className="grid grid-cols-12 items-end gap-2 rounded-lg bg-slate-50 p-3">
                <div className="col-span-12 sm:col-span-5"><Field label="Názov"><Input value={line.name} onChange={(e) => setLine(idx, { name: e.target.value })} /></Field></div>
                <div className="col-span-4 sm:col-span-2"><Field label="Množ."><Input inputMode="decimal" value={line.quantity} onChange={(e) => setLine(idx, { quantity: e.target.value.replace(",", ".") })} /></Field></div>
                <div className="col-span-4 sm:col-span-2">
                  <Field label="MJ"><Select value={line.unit_code} onChange={(e) => setLine(idx, { unit_code: e.target.value })}>
                    {UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
                  </Select></Field>
                </div>
                <div className="col-span-4 sm:col-span-3"><Field label="Cena bez DPH"><Input inputMode="decimal" value={line.unit_price} onChange={(e) => setLine(idx, { unit_price: e.target.value.replace(",", ".") })} /></Field></div>
                <div className="col-span-8 sm:col-span-5">
                  <Field label="DPH"><Select value={line.vat_category} onChange={(e) => setLine(idx, { vat_category: e.target.value as InvoiceLine["vat_category"], vat_rate: e.target.value === "S" ? "23" : "0" })}>
                    {VAT_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </Select></Field>
                </div>
                <div className="col-span-4 sm:col-span-2">
                  <Field label="Sadzba %"><Select value={line.vat_rate} disabled={line.vat_category !== "S"} onChange={(e) => setLine(idx, { vat_rate: e.target.value })}>
                    {["23", "19", "5", "0"].map((r) => <option key={r} value={r}>{r}</option>)}
                  </Select></Field>
                </div>
                <div className="col-span-12 pb-2 text-right sm:col-span-5">
                  <button type="button" className="text-sm text-rose-600 hover:underline disabled:text-slate-300" disabled={inv.lines.length === 1}
                    onClick={() => setInv({ ...inv, lines: inv.lines.filter((_, i) => i !== idx) })}>Zmazať</button>
                </div>
              </div>
            ))}
            <Button type="button" variant="secondary" onClick={() => setInv({ ...inv, lines: [...inv.lines, emptyLine(String(inv.lines.length + 1), Boolean(company.ic_dph))] })}>
              + Pridať položku
            </Button>
          </div>
        </Card>

        <Card title="Údaje faktúry">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Číslo" hint="Nechajte prázdne – pridelí sa automaticky."><Input value={inv.number} onChange={(e) => setInv({ ...inv, number: e.target.value })} /></Field>
            <Field label="Dátum vyhotovenia"><Input type="date" value={inv.issue_date ?? ""} onChange={(e) => setInv({ ...inv, issue_date: e.target.value })} /></Field>
            <Field label="Dátum dodania"><Input type="date" value={inv.delivery_date ?? ""} onChange={(e) => setInv({ ...inv, delivery_date: e.target.value })} /></Field>
            <Field label="Splatnosť"><Input type="date" value={inv.due_date ?? ""} onChange={(e) => setInv({ ...inv, due_date: e.target.value })} /></Field>
            <Field label="Referencia odberateľa" hint="Napr. číslo objednávky alebo meno kontaktu (Peppol ju vyžaduje).">
              <Input value={inv.buyer_reference ?? ""} onChange={(e) => setInv({ ...inv, buyer_reference: e.target.value })} />
            </Field>
            <Field label="Poznámka"><Input value={inv.notes[0] ?? ""} onChange={(e) => setInv({ ...inv, notes: e.target.value ? [e.target.value] : [] })} /></Field>
          </div>
        </Card>
      </div>

      <div className="space-y-6">
        <Card title="Súhrn">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt>Bez DPH</dt><dd>{money(t.net)}</dd></div>
            <div className="flex justify-between"><dt>DPH</dt><dd>{money(t.vat)}</dd></div>
            <div className="flex justify-between border-t border-slate-200 pt-2 text-base font-semibold"><dt>K úhrade</dt><dd>{money(t.total)}</dd></div>
          </dl>
          <div className="mt-4 space-y-2">
            <Alert>{error}</Alert>
            <Button className="w-full" onClick={submit} disabled={busy}>{submitLabel}</Button>
          </div>
        </Card>
        <Card title="Kontrola v reálnom čase">
          <Findings validation={validation} />
        </Card>
      </div>
    </div>
  );
}
