const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "efaktura.token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    }
  }
  return status >= 500 ? "Nastala chyba servera. Skúste to znova o chvíľu." : `Požiadavka zlyhala (${status}).`;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Server je nedostupný. Skontrolujte pripojenie na internet.");
  }
  if (resp.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    setToken(null);
    // Outside React (no router available here): a full reload to the login page is intended.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/prihlasenie";
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new ApiError(resp.status, detailMessage(body, resp.status));
  }
  return resp;
}

export const api = {
  async get<T>(path: string): Promise<T> {
    return (await request(path)).json();
  },
  async post<T>(path: string, body?: unknown): Promise<T> {
    const init: RequestInit = { method: "POST" };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) init.body = JSON.stringify(body);
    return (await request(path, init)).json();
  },
  async put<T>(path: string, body: unknown): Promise<T> {
    return (await request(path, { method: "PUT", body: JSON.stringify(body) })).json();
  },
  async download(path: string, filename: string, open = false) {
    const blob = await (await request(path)).blob();
    const url = URL.createObjectURL(blob);
    if (open) {
      window.open(url, "_blank");
    } else {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
