"use client";

import { useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import { Alert, Button, Card, Input } from "@/components/ui";
import { api } from "@/lib/api";

const EXAMPLES = [
  "Kedy musím začať posielať e-faktúry?",
  "Čo je Peppol adresa?",
  "Ako opravím odoslanú faktúru?",
  "Aké sú sadzby DPH v roku 2027?",
  "Čo znamená prenesenie daňovej povinnosti?",
];

export default function HelpPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ answer: string; sources: { id: string; title: string }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    setQuestion(q);
    setError(null);
    try {
      setAnswer(await api.post("/explain", { question: q }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Shell>
      <h1 className="text-2xl font-bold">Pomoc s e-fakturáciou</h1>
      <Card>
        <form className="flex gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); ask(question); }}>
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Opýtajte sa po slovensky…" />
          <Button type="submit" disabled={!question.trim()}>Opýtať sa</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button key={q} onClick={() => ask(q)} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700 hover:bg-slate-200">{q}</button>
          ))}
        </div>
      </Card>
      <Alert>{error}</Alert>
      {answer && (
        <Card>
          <p className="whitespace-pre-line text-sm leading-relaxed">{answer.answer}</p>
          {answer.sources.length > 0 && <p className="mt-4 text-xs text-slate-500">Zdroje: {answer.sources.map((s) => s.title).join(" · ")}</p>}
          <p className="mt-2 text-xs text-slate-400">Informatívne vysvetlenie, nie daňové poradenstvo.</p>
        </Card>
      )}
    </Shell>
  );
}
