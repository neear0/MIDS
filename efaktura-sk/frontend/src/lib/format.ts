export function money(value: string | number, currency = "EUR"): string {
  const n = typeof value === "string" ? Number(value) : value;
  return new Intl.NumberFormat("sk-SK", { style: "currency", currency }).format(Number.isFinite(n) ? n : 0);
}

export function date(value: string | null | undefined): string {
  if (!value) return "–";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${Number(d)}. ${Number(m)}. ${y}`;
}

export const STATUS_LABELS: Record<string, { label: string; tone: "gray" | "green" | "red" | "amber" | "blue" }> = {
  draft: { label: "Koncept", tone: "gray" },
  valid: { label: "Pripravená", tone: "green" },
  invalid: { label: "Obsahuje chyby", tone: "red" },
  queued: { label: "Vo fronte", tone: "amber" },
  sent: { label: "Odoslaná", tone: "blue" },
  delivered: { label: "Doručená", tone: "green" },
  failed: { label: "Neodoslaná", tone: "red" },
  received: { label: "Prijatá", tone: "blue" },
};

export const DOC_TYPES: Record<string, string> = {
  "380": "Faktúra",
  "381": "Dobropis",
  "384": "Opravná faktúra",
  "386": "Zálohová faktúra",
};

export const VAT_CATEGORIES: { value: string; label: string }[] = [
  { value: "S", label: "S – s DPH" },
  { value: "O", label: "O – nepodlieha DPH" },
  { value: "AE", label: "AE – prenesenie daňovej povinnosti" },
  { value: "K", label: "K – dodanie do EÚ" },
  { value: "G", label: "G – vývoz" },
  { value: "E", label: "E – oslobodené" },
  { value: "Z", label: "Z – nulová sadzba" },
];

export const UNITS = [
  { value: "C62", label: "ks" },
  { value: "HUR", label: "hod" },
  { value: "DAY", label: "deň" },
  { value: "MON", label: "mesiac" },
  { value: "KGM", label: "kg" },
  { value: "MTR", label: "m" },
  { value: "LTR", label: "l" },
];
