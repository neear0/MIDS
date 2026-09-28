export type Severity = "error" | "warning" | "info";

export interface Finding {
  rule_id: string;
  severity: Severity;
  field: string | null;
  message: string;
  message_en: string;
  hint: string | null;
  source: string;
}

export interface Validation {
  valid: boolean;
  error_count: number;
  warning_count: number;
  findings: Finding[];
}

export interface Address {
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country_code: string;
}

export interface Party {
  name: string;
  ico?: string | null;
  dic?: string | null;
  ic_dph?: string | null;
  email?: string | null;
  address: Address;
}

export type VatCategory = "S" | "Z" | "E" | "AE" | "K" | "G" | "O";

export interface InvoiceLine {
  id: string;
  name: string;
  description?: string | null;
  quantity: string;
  unit_code: string;
  unit_price: string;
  vat_category: VatCategory;
  vat_rate: string;
  line_discount: string;
}

export interface Invoice {
  number: string;
  document_type: "380" | "381" | "384" | "386";
  issue_date: string | null;
  due_date: string | null;
  delivery_date: string | null;
  currency: string;
  buyer_reference: string | null;
  order_reference: string | null;
  notes: string[];
  seller: Party;
  buyer: Party;
  lines: InvoiceLine[];
  payment: { iban?: string | null; variable_symbol?: string | null; means_code?: string };
  preceding_invoice?: { number: string; issue_date?: string | null } | null;
}

export interface InvoiceSummary {
  id: number;
  number: string;
  direction: "outgoing" | "incoming";
  document_type: string;
  status: string;
  source: string;
  counterparty_name: string;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  total_payable: string;
  paid_at: string | null;
  error_count: number;
  warning_count: number;
}

export interface Transmission {
  id: number;
  provider: string;
  status: string;
  message_id: string | null;
  tax_report_status: string | null;
  attempts: number;
  last_error: string | null;
}

export interface InvoiceDetail extends InvoiceSummary {
  invoice: Invoice;
  validation: Validation | null;
  ubl_sha256: string | null;
  transmissions: Transmission[];
}

export interface Company {
  id: number;
  name: string;
  ico?: string | null;
  dic?: string | null;
  ic_dph?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country_code: string;
  email?: string | null;
  iban?: string | null;
  bic?: string | null;
  registration_note?: string | null;
  invoice_prefix: string;
  default_due_days: number;
  role?: string;
  identifier_warnings: string[];
}
