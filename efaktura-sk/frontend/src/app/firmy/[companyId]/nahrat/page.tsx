"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Findings } from "@/components/Findings";
import { Shell } from "@/components/Shell";
import { Alert, Button, Card } from "@/components/ui";
import { api } from "@/lib/api";
import type { Invoice, Validation } from "@/lib/types";
import { DRAFT_KEY } from "../faktury/nova/InvoiceForm";

interface Extraction {
  invoice: Invoice;
  provider: string;
  confidence: number;
  missing_fields: string[];
  warnings: string[];
  direction_guess: "incoming" | "outgoing" | "unknown";
  validation: Validation;
}

export default function UploadPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const router = useRouter();
  const [result, setResult] = useState<Extraction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      setResult(await api.post<Extraction>(`/companies/${companyId}/extract`, form));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function useAsInvoice() {
    if (!result) return;
    const { buyer, lines, notes, buyer_reference, order_reference } = result.invoice;
    try {
      window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ buyer, lines, notes, buyer_reference, order_reference }));
    } catch {
      /* storage unavailable – the form simply starts empty */
    }
    router.push(`/firmy/${companyId}/faktury/nova`);
  }

  const inv = result?.invoice;
  return (
    <Shell companyId={companyId}>
      <h1 className="text-2xl font-bold">Nahrať doklad</h1>
      <Card>
        <p className="mb-4 text-sm text-slate-600">
          Nahrajte PDF, sken alebo fotku faktúry. Údaje z nej vytiahneme a skontrolujeme – nič sa neuloží, kým to nepotvrdíte.
        </p>
        <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center hover:border-brand-500">
          <span className="text-sm font-medium text-slate-700">{busy ? "Spracúvam…" : "Kliknite a vyberte súbor"}</span>
          <span className="mt-1 text-xs text-slate-500">PDF, PNG, JPG · max. 5 MB</span>
          <input type="file" accept="application/pdf,image/*" hidden disabled={busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
        </label>
      </Card>
      <Alert>{error}</Alert>
      {inv && result && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Rozpoznané údaje" className="lg:col-span-2">
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-slate-500">Číslo</dt><dd>{inv.number || "–"}</dd></div>
              <div><dt className="text-slate-500">Dátum vyhotovenia</dt><dd>{inv.issue_date ?? "–"}</dd></div>
              <div><dt className="text-slate-500">Dodávateľ</dt><dd>{inv.seller.name || "–"} ({inv.seller.ico ?? "?"})</dd></div>
              <div><dt className="text-slate-500">Odberateľ</dt><dd>{inv.buyer.name || "–"} ({inv.buyer.ico ?? "?"})</dd></div>
              <div><dt className="text-slate-500">IBAN</dt><dd>{inv.payment.iban ?? "–"}</dd></div>
              <div><dt className="text-slate-500">Položiek</dt><dd>{inv.lines.length}</dd></div>
            </dl>
            <p className="mt-4 text-xs text-slate-500">
              Spoľahlivosť {Math.round(result.confidence * 100)} % · metóda: {result.provider === "anthropic" ? "AI (Claude)" : "offline čítanie textu"}
            </p>
            {result.warnings.map((w) => <p key={w} className="mt-1 text-sm text-amber-700">⚠ {w}</p>)}
            <div className="mt-4 flex gap-2">
              {result.direction_guess !== "incoming" && <Button onClick={useAsInvoice}>Vytvoriť faktúru z týchto údajov</Button>}
              {result.direction_guess === "incoming" && <Alert tone="blue">Toto je faktúra, ktorú ste prijali. Po zavedení Peppolu ju dostanete elektronicky automaticky.</Alert>}
            </div>
          </Card>
          <Card title="Kontrola"><Findings validation={result.validation} /></Card>
        </div>
      )}
    </Shell>
  );
}
