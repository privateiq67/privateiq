"use client";
import React, { useState } from "react";
import { Eye, TrendingUp, Building2, MapPin, Hash, Calendar } from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import {
  apiGet,
  CompanyProfile,
  Financials,
  NewsItem,
  YearBlock,
} from "../lib/api";

type Tab = "all" | "income" | "balance" | "cash";

const INCOME_ROWS = [
  "Revenue",
  "Cost of Sales",
  "Gross Profit",
  "Operating Profit",
  "EBIT",
  "EBITDA (Est)",
  "Profit Before Tax",
  "Net Income",
];
const BALANCE_ROWS = [
  "Current Assets",
  "Non-Current Assets",
  "Total Assets",
  "Current Liabilities",
  "Non-Current Liabilities",
  "Total Liabilities",
  "Equity",
  "Net Assets",
];
const CASH_ROWS = ["Operating CF", "Investing CF", "Financing CF", "Net Change in Cash"];

export default function Terminal() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [company, setCompany] = useState<CompanyProfile | null>(null);
  const [financials, setFinancials] = useState<Financials | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [valuation, setValuation] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("all");

  const fmt = (val: any) => {
    if (val === null || val === undefined) return <span className="text-slate-700">-</span>;
    return Number(val).toLocaleString("en-GB", {
      style: "currency",
      currency: "GBP",
      maximumFractionDigits: 0,
    });
  };

  const pct = (num: any, den: any) => {
    if (num == null || den == null || den === 0) return <span className="text-slate-700">-</span>;
    return ((num / den) * 100).toFixed(1) + "%";
  };

  const mul = (num: any, den: any) => {
    if (num == null || den == null || den === 0) return <span className="text-slate-700">-</span>;
    return (num / den).toFixed(1) + "x";
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setSearching(true);
    setError(null);
    try {
      const data = await apiGet<{ items: any[] }>(`/api/search?q=${encodeURIComponent(query)}`);
      setResults(data.items || []);
      if (!(data.items || []).length) setError("No companies matched that query.");
    } catch (err: any) {
      setError(err.message || "Search failed");
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const loadCompany = async (c: any) => {
    setLoading(true);
    setError(null);
    setResults([]);
    setValuation(null);
    setFinancials(null);
    setCompany(null);
    setTab("all");

    try {
      let profile: CompanyProfile;
      try {
        profile = await apiGet<CompanyProfile>(`/api/company/${c.company_number}`);
      } catch {
        profile = {
          company_number: c.company_number,
          company_name: c.title,
          title: c.title,
          company_status: c.company_status,
          address_snippet: c.address_snippet,
          date_of_creation: c.date_of_creation,
        };
      }
      setCompany(profile);

      const finData = await apiGet<Financials>(
        `/api/company/${c.company_number}/financials`
      );
      setFinancials(finData);

      const name = profile.company_name || profile.title || c.title;
      if (name) {
        try {
          const newsData = await apiGet<{ news: NewsItem[] }>(
            `/api/news?${new URLSearchParams({ name }).toString()}`
          );
          setNews(newsData.news || []);
          const valNews = (newsData.news || []).find((n) => n.valuation_data);
          if (valNews?.valuation_data) {
            setValuation({
              amount_m: valNews.valuation_data.amount_m,
              raw: valNews.valuation_data.raw,
              source: valNews.link,
              currency: valNews.valuation_data.currency,
            });
          }
        } catch {
          setNews([]);
        }
      }
    } catch (err: any) {
      setError(err.message || "Error loading company data");
    } finally {
      setLoading(false);
    }
  };

  const years: YearBlock[] = financials?.years || [];

  const renderSection = (title: string, rows: string[], accessor: (y: YearBlock) => Record<string, any>) => (
    <>
      <tr className="bg-slate-950">
        <td colSpan={10} className="p-2 font-bold text-blue-400 text-xs uppercase tracking-wider">
          {title}
        </td>
      </tr>
      {rows.map((row) => (
        <tr key={row} className="hover:bg-slate-800/30">
          <td className="p-2 text-slate-300 pl-4">{row}</td>
          {years.map((y, i) => {
            const cell = accessor(y)?.[row];
            return (
              <td key={i} className="text-right p-2 font-mono">
                {fmt(cell?.value)}
                {cell?.estimated && (
                  <span className="ml-1 text-[9px] text-slate-500" title="Derived / estimated">
                    est
                  </span>
                )}
                {cell?.source && (
                  <a
                    href={cell.source}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 text-blue-500 hover:text-white"
                  >
                    <Eye size={12} className="inline" />
                  </a>
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-7xl mx-auto">
        <form onSubmit={search} className="flex gap-2 mb-6">
          <input
            className="flex-1 bg-slate-900 border border-slate-700 p-3 rounded text-white focus:border-blue-500 outline-none"
            placeholder="Search UK Companies (e.g. Gymshark, Monzo)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            className="bg-blue-600 px-6 rounded font-bold hover:bg-blue-500 disabled:opacity-50"
            disabled={searching || !query.trim()}
          >
            {searching ? "..." : "Search"}
          </button>
        </form>

        {error && (
          <div className="mb-4 border border-red-900/50 bg-red-950/30 text-red-300 p-3 rounded text-sm">
            {error}
          </div>
        )}

        {results.length > 0 && (
          <div className="bg-slate-900 rounded mb-8 border border-slate-700 overflow-hidden">
            {results.map((r: any) => (
              <div
                key={r.company_number}
                onClick={() => loadCompany(r)}
                className="p-3 hover:bg-blue-600/80 cursor-pointer border-b border-slate-800 flex justify-between items-center gap-4"
              >
                <div>
                  <div className="font-bold text-white">{r.title}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {r.company_status || "—"}
                    {r.address_snippet ? ` · ${r.address_snippet}` : ""}
                  </div>
                </div>
                <div className="text-xs text-slate-400 font-mono">{r.company_number}</div>
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div className="text-center text-blue-400 animate-pulse mt-12 font-bold">
            Fetching filings · preferring iXBRL · normalising statements...
          </div>
        )}

        {!loading && financials && company && (
          <div className="grid grid-cols-12 gap-6">
            <div className="col-span-12 lg:col-span-8 space-y-6">
              {/* Profile header */}
              <div className="bg-slate-900 border border-slate-800 p-5 rounded">
                <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                  <div>
                    <h2 className="text-2xl font-bold text-white">
                      {company.company_name || company.title}
                    </h2>
                    <div className="flex flex-wrap gap-3 mt-2 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <Hash size={12} /> {company.company_number}
                      </span>
                      <span className="flex items-center gap-1 uppercase">
                        <Building2 size={12} /> {company.company_status || "unknown"}
                      </span>
                      {company.date_of_creation && (
                        <span className="flex items-center gap-1">
                          <Calendar size={12} /> Inc. {company.date_of_creation}
                        </span>
                      )}
                      {company.demo && (
                        <span className="text-violet-300 border border-violet-700/50 px-1.5 rounded">
                          DEMO DATA
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 uppercase tracking-widest">Figures in GBP (£)</div>
                </div>
                {(company.address_snippet || company.registered_office) && (
                  <div className="text-sm text-slate-400 flex items-start gap-2">
                    <MapPin size={14} className="mt-0.5 shrink-0" />
                    {company.address_snippet ||
                      [
                        company.registered_office?.address_line_1,
                        company.registered_office?.locality,
                        company.registered_office?.postal_code,
                      ]
                        .filter(Boolean)
                        .join(", ")}
                  </div>
                )}
                {!!(company.sic_codes || []).length && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {company.sic_codes!.map((s) => (
                      <span
                        key={s}
                        className="text-[10px] font-mono bg-slate-950 border border-slate-800 px-1.5 py-0.5 rounded text-slate-400"
                      >
                        SIC {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {valuation && years[0] && (
                <div className="bg-slate-900 border border-blue-900/50 p-4 rounded flex items-center justify-between bg-gradient-to-r from-blue-900/20 to-transparent">
                  <div>
                    <div className="text-xs text-blue-400 uppercase font-bold tracking-wider mb-1">
                      Implied Valuation (from News)
                    </div>
                    <div className="text-2xl font-bold text-white">{valuation.raw}</div>
                    <a
                      href={valuation.source}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-slate-500 hover:text-white underline"
                    >
                      Source Article
                    </a>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400 uppercase font-bold tracking-wider mb-1">
                      Implied P/S Ratio
                    </div>
                    <div className="text-2xl font-mono text-green-400">
                      {mul(
                        valuation.amount_m * 1_000_000,
                        years[0].income_statement?.Revenue?.value
                      )}
                    </div>
                    <div className="text-xs text-slate-500">Based on latest revenue</div>
                  </div>
                </div>
              )}

              {!years.length && (
                <div className="bg-slate-900 border border-slate-800 p-8 rounded text-center text-slate-500 text-sm">
                  {financials.message || "No financial years available for this company."}
                </div>
              )}

              {!!years.length && (
                <div className="bg-slate-900 border border-slate-800 p-6 rounded">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div className="flex gap-1 bg-slate-950 p-1 rounded border border-slate-800">
                      {(
                        [
                          ["all", "All"],
                          ["income", "Income"],
                          ["balance", "Balance"],
                          ["cash", "Cash Flow"],
                        ] as [Tab, string][]
                      ).map(([id, label]) => (
                        <button
                          key={id}
                          onClick={() => setTab(id)}
                          className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                            tab === id
                              ? "bg-blue-600 text-white"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {years.map((y, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-xs text-slate-400">
                          <span className="font-mono text-slate-300">{y.period}</span>
                          <StatusBadge status={y.parsing_status} />
                        </div>
                      ))}
                    </div>
                  </div>

                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-800">
                        <th className="text-left p-2 w-1/3">Item</th>
                        {years.map((y, i) => (
                          <th key={i} className="text-right p-2">
                            <div>{y.period}</div>
                            <div className="mt-1 flex justify-end">
                              <StatusBadge status={y.parsing_status} />
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                      {(tab === "all" || tab === "income") &&
                        renderSection("Income Statement", INCOME_ROWS, (y) => y.income_statement)}
                      {(tab === "all" || tab === "balance") &&
                        renderSection("Balance Sheet", BALANCE_ROWS, (y) => y.balance_sheet)}
                      {(tab === "all" || tab === "cash") &&
                        renderSection("Cash Flow", CASH_ROWS, (y) => y.cash_flow)}

                      {tab === "all" && (
                        <>
                          <tr className="bg-blue-900/20">
                            <td
                              colSpan={10}
                              className="p-2 font-bold text-green-400 text-xs uppercase border-t border-blue-800"
                            >
                              Financial Ratios
                            </td>
                          </tr>
                          <tr>
                            <td className="p-2 text-slate-300 pl-4">Net Margin %</td>
                            {years.map((y, i) => (
                              <td key={i} className="text-right p-2 font-mono font-bold text-slate-200">
                                {pct(
                                  y.income_statement?.["Net Income"]?.value,
                                  y.income_statement?.Revenue?.value
                                )}
                              </td>
                            ))}
                          </tr>
                          <tr>
                            <td className="p-2 text-slate-300 pl-4">Current Ratio (x)</td>
                            {years.map((y, i) => (
                              <td key={i} className="text-right p-2 font-mono text-slate-400">
                                {mul(
                                  y.balance_sheet?.["Current Assets"]?.value,
                                  y.balance_sheet?.["Current Liabilities"]?.value
                                    ? Math.abs(y.balance_sheet["Current Liabilities"].value as number)
                                    : null
                                )}
                              </td>
                            ))}
                          </tr>
                        </>
                      )}
                    </tbody>
                  </table>

                  {years.some((y) => y.warnings?.length) && (
                    <div className="mt-4 text-xs text-amber-400/90 space-y-1">
                      {years.flatMap((y) =>
                        (y.warnings || []).map((w, i) => (
                          <div key={`${y.period}-${i}`}>
                            {y.period}: {w}
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="col-span-12 lg:col-span-4">
              <div className="bg-slate-900 border border-slate-800 p-4 rounded h-fit sticky top-20">
                <h3 className="font-bold text-slate-500 mb-4 text-xs tracking-wider flex items-center gap-2">
                  <TrendingUp size={14} /> MARKET INTEL
                </h3>
                {!news.length && (
                  <div className="text-slate-600 text-sm py-6 text-center">No related headlines.</div>
                )}
                {news.map((n, i) => (
                  <a
                    key={i}
                    href={n.link}
                    target="_blank"
                    rel="noreferrer"
                    className="block mb-3 p-3 bg-slate-950 hover:bg-slate-800 rounded border border-slate-800/50 transition group"
                  >
                    <div className="flex justify-between text-xs text-blue-400 mb-1 gap-2">
                      <span>
                        {n.published ? new Date(n.published).toLocaleDateString("en-GB") : n.source}
                      </span>
                      {n.valuation_data && (
                        <span className="text-green-400 font-bold bg-green-900/30 px-1 rounded">
                          VALUATION
                        </span>
                      )}
                    </div>
                    <div className="text-sm font-semibold text-slate-300 leading-snug group-hover:text-white">
                      {n.title}
                    </div>
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}

        {!loading && !financials && !results.length && !error && (
          <div className="text-center text-slate-600 mt-20 text-sm">
            Search Companies House (or demo fixtures) to load multi-year statements.
          </div>
        )}
      </div>
    </div>
  );
}
