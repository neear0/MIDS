"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Shell } from "@/components/Shell";
import { Badge, Card, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import type { Company } from "@/lib/types";
import { CompanyForm, EMPTY_COMPANY } from "./CompanyForm";

const ROLES: Record<string, string> = { owner: "Vlastník", accountant: "Účtovník", member: "Člen", viewer: "Len čítanie" };

export default function CompaniesPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[] | null>(null);

  useEffect(() => {
    api.get<Company[]>("/companies").then(setCompanies).catch(() => setCompanies([]));
  }, []);

  return (
    <Shell>
      <h1 className="text-2xl font-bold">Vaše firmy</h1>
      <Card>
        {companies === null ? (
          <Empty>Načítavam…</Empty>
        ) : companies.length === 0 ? (
          <Empty>Zatiaľ nemáte žiadnu firmu. Pridajte ju nižšie – stačí pár údajov.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {companies.map((c) => (
              <li key={c.id}>
                <Link href={`/firmy/${c.id}`} className="flex items-center justify-between py-3 hover:bg-slate-50">
                  <div>
                    <p className="font-medium">{c.name}</p>
                    <p className="text-sm text-slate-500">IČO {c.ico ?? "–"} · DIČ {c.dic ?? "–"}</p>
                  </div>
                  <Badge>{ROLES[c.role ?? ""] ?? c.role}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Pridať firmu">
        <CompanyForm
          initial={EMPTY_COMPANY}
          submitLabel="Pridať firmu"
          onSubmit={async (data) => {
            const created = await api.post<Company>("/companies", data);
            router.push(`/firmy/${created.id}`);
          }}
        />
      </Card>
    </Shell>
  );
}
