"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { Finding, Validation } from "@/lib/types";
import { Badge, Empty } from "./ui";

const TONE = { error: "red", warning: "amber", info: "blue" } as const;
const LABEL = { error: "Chyba", warning: "Upozornenie", info: "Info" };

function FindingRow({ f }: { f: Finding }) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function explain() {
    setLoading(true);
    try {
      const res = await api.post<{ answer: string }>("/explain", { question: f.message, rule_id: f.rule_id, context: f.message });
      setExplanation(res.answer);
    } catch {
      setExplanation("Vysvetlenie sa nepodarilo načítať.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <Badge tone={TONE[f.severity]}>{LABEL[f.severity]}</Badge>
        <div className="flex-1 text-sm">
          <p className="text-slate-900">{f.message}</p>
          {f.hint && <p className="mt-1 text-slate-600">💡 {f.hint}</p>}
          <p className="mt-1 text-xs text-slate-400">
            {f.rule_id}
            {f.field && !f.field.startsWith("/") ? ` · ${f.field}` : ""}
          </p>
          {explanation && <p className="mt-2 whitespace-pre-line rounded-lg bg-slate-50 p-3 text-slate-700">{explanation}</p>}
        </div>
        {!explanation && (
          <button onClick={explain} disabled={loading} className="text-xs font-medium text-brand-600 hover:underline">
            {loading ? "…" : "Vysvetliť"}
          </button>
        )}
      </div>
    </li>
  );
}

export function Findings({ validation }: { validation: Validation | null }) {
  if (!validation) return <Empty>Faktúra ešte nebola skontrolovaná.</Empty>;
  if (validation.findings.length === 0) {
    return <p className="text-sm text-emerald-700">✓ Faktúra spĺňa EN 16931, Peppol BIS 3.0 aj slovenské pravidlá.</p>;
  }
  return (
    <ul className="divide-y divide-slate-100">
      {validation.findings.map((f, i) => (
        <FindingRow key={`${f.rule_id}-${i}`} f={f} />
      ))}
    </ul>
  );
}
