"use client";

import { useState, type FormEvent } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import type { Company } from "@/lib/types";

export type CompanyInput = Omit<Company, "id" | "role" | "identifier_warnings">;

export const EMPTY_COMPANY: CompanyInput = {
  name: "", ico: "", dic: "", ic_dph: "", street: "", city: "", postal_code: "", country_code: "SK",
  email: "", iban: "", bic: "", registration_note: "", invoice_prefix: "", default_due_days: 14,
};

export function CompanyForm({ initial, submitLabel, onSubmit }: {
  initial: CompanyInput;
  submitLabel: string;
  onSubmit: (data: CompanyInput) => Promise<void>;
}) {
  const [data, setData] = useState<CompanyInput>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof CompanyInput) => (e: { target: { value: string } }) =>
    setData({ ...data, [key]: key === "default_due_days" ? Number(e.target.value) : e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v === "" ? null : v])) as CompanyInput;
      await onSubmit({ ...clean, invoice_prefix: data.invoice_prefix ?? "", country_code: data.country_code || "SK" });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Obchodné meno *"><Input required value={data.name} onChange={set("name")} /></Field>
        <Field label="IČO"><Input value={data.ico ?? ""} onChange={set("ico")} inputMode="numeric" /></Field>
        <Field label="DIČ" hint="Slúži aj ako vaša Peppol adresa (0245:DIČ)."><Input value={data.dic ?? ""} onChange={set("dic")} inputMode="numeric" /></Field>
        <Field label="IČ DPH" hint="Len ak ste platiteľ DPH, napr. SK2020123457."><Input value={data.ic_dph ?? ""} onChange={set("ic_dph")} /></Field>
        <Field label="Ulica a číslo"><Input value={data.street ?? ""} onChange={set("street")} /></Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label="PSČ"><Input value={data.postal_code ?? ""} onChange={set("postal_code")} /></Field>
          <div className="col-span-2"><Field label="Mesto"><Input value={data.city ?? ""} onChange={set("city")} /></Field></div>
        </div>
        <Field label="IBAN"><Input value={data.iban ?? ""} onChange={set("iban")} placeholder="SK.." /></Field>
        <Field label="E-mail"><Input type="email" value={data.email ?? ""} onChange={set("email")} /></Field>
        <Field label="Zápis v registri" hint="Napr. Zapísaná v OR OS Bratislava I, oddiel Sro, vl. č. 12345/B">
          <Input value={data.registration_note ?? ""} onChange={set("registration_note")} />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Predpona čísla faktúry"><Input value={data.invoice_prefix} onChange={set("invoice_prefix")} /></Field>
          <Field label="Splatnosť (dni)"><Input type="number" min={0} value={data.default_due_days} onChange={set("default_due_days")} /></Field>
        </div>
      </div>
      <Alert>{error}</Alert>
      <Button type="submit" disabled={busy}>{submitLabel}</Button>
    </form>
  );
}
