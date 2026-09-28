"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { api, getToken, setToken } from "@/lib/api";
import type { Company } from "@/lib/types";

export function useCompany(companyId: string | undefined) {
  const [company, setCompany] = useState<Company | null>(null);
  useEffect(() => {
    if (companyId) api.get<Company>(`/companies/${companyId}`).then(setCompany).catch(() => setCompany(null));
  }, [companyId]);
  return company;
}

export function Shell({ companyId, children }: { companyId?: string; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const company = useCompany(companyId);

  useEffect(() => {
    if (!getToken()) router.replace("/prihlasenie");
  }, [router]);

  const nav = companyId
    ? [
        { href: `/firmy/${companyId}`, label: "Prehľad" },
        { href: `/firmy/${companyId}/faktury`, label: "Faktúry" },
        { href: `/firmy/${companyId}/faktury/nova`, label: "Nová faktúra" },
        { href: `/firmy/${companyId}/nahrat`, label: "Nahrať doklad" },
        { href: `/firmy/${companyId}/nastavenia`, label: "Nastavenia" },
      ]
    : [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link href="/firmy" className="text-lg font-bold text-brand-700">
            eFaktúra <span className="text-slate-400">SK</span>
          </Link>
          {company && (
            <Link href="/firmy" className="rounded-md bg-slate-100 px-2 py-1 text-sm text-slate-700 hover:bg-slate-200" title="Zmeniť firmu">
              {company.name} ▾
            </Link>
          )}
          <nav className="order-last -mx-1 flex w-full gap-1 overflow-x-auto whitespace-nowrap sm:order-none sm:mx-0 sm:w-auto sm:flex-1">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  pathname === item.href ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <Link href="/pomoc" className="text-sm text-slate-600 hover:text-slate-900">Pomoc</Link>
          <button
            className="text-sm text-slate-600 hover:text-slate-900"
            onClick={() => {
              setToken(null);
              router.replace("/prihlasenie");
            }}
          >
            Odhlásiť
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">{children}</main>
    </div>
  );
}
