"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = mode === "login" ? { email, password } : { email, password, full_name: fullName };
      const res = await api.post<{ access_token: string }>(`/auth/${mode}`, body);
      setToken(res.access_token);
      router.replace("/firmy");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-brand-700">eFaktúra SK</h1>
          <p className="mt-1 text-sm text-slate-600">Elektronické faktúry pripravené na rok 2027 – bez starostí.</p>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          {mode === "register" && (
            <Field label="Meno a priezvisko">
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="E-mail">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </Field>
          <Field label="Heslo" hint={mode === "register" ? "Aspoň 8 znakov." : undefined}>
            <Input
              type="password"
              required
              minLength={mode === "register" ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </Field>
          <Alert>{error}</Alert>
          <Button type="submit" disabled={busy} className="w-full">
            {mode === "login" ? "Prihlásiť sa" : "Vytvoriť účet"}
          </Button>
          <button
            type="button"
            className="w-full text-center text-sm text-brand-600 hover:underline"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Nemáte účet? Zaregistrujte sa" : "Už máte účet? Prihláste sa"}
          </button>
        </form>
      </div>
    </div>
  );
}
