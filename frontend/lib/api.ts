const API_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  (typeof process !== "undefined" && process.env.VERCEL
    ? "https://private-iq-backend.onrender.com"
    : "http://localhost:8000");;

export function apiBase(): string {
  return API_URL.replace(/\/$/, "");
}

export async function apiGet<T = any>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export type LineItem = { value?: number | null; source?: string; estimated?: boolean; provenance?: any };
export type YearBlock = {
  period: string;
  filing_date?: string;
  parsing_status?: string;
  income_statement: Record<string, LineItem>;
  balance_sheet: Record<string, LineItem>;
  cash_flow: Record<string, LineItem>;
  warnings?: string[];
};
export type Financials = {
  company_number: string;
  years: YearBlock[];
  schema_version: string;
  message?: string;
};
export type CompanyProfile = {
  company_number: string;
  company_name?: string;
  title?: string;
  company_status?: string;
  company_type?: string;
  date_of_creation?: string;
  registered_office?: Record<string, string>;
  address_snippet?: string;
  sic_codes?: string[];
  officers_summary?: { name?: string; role?: string }[];
  demo?: boolean;
};
export type NewsItem = {
  title: string;
  link: string;
  published: string;
  source: string;
  valuation_data?: { amount_m: number; currency: string; raw: string };
};
